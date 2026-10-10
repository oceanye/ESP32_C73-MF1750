"""Model virtual colours across waveform profiles and history sequences."""

from __future__ import annotations

import math
import re
from typing import Any, Mapping, Sequence


VIRTUAL_COLOR_KIND = "mf1750-virtual-color-address"
PALETTE_PLAN_KIND = "mf1750-virtual-color-palette-plan"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COLOR_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_COLOR_KEYS = {
    "schema_version",
    "kind",
    "color_id",
    "waveform_profile_sha256",
    "target_code",
    "primer_code",
    "expected_lab",
    "qualification",
}
_LAB_KEYS = {"l", "a", "b"}
_QUALIFICATIONS = {"unmeasured_candidate", "measured_candidate", "qualified"}


class VirtualPaletteError(ValueError):
    """Raised when virtual colour addressing is ambiguous or unsafe."""


def _number(
    value: Any,
    *,
    label: str,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise VirtualPaletteError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < minimum or result > maximum:
        raise VirtualPaletteError(f"{label} is outside its finite range")
    return result


def _code(value: Any, *, label: str, nullable: bool) -> int | None:
    if value is None and nullable:
        return None
    if type(value) is not int or value < 0 or value > 7:
        raise VirtualPaletteError(f"{label} must be a 3-bit code")
    return value


def validate_virtual_color(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one virtual address; this never asserts optical distinctness."""

    if not isinstance(value, Mapping) or set(value) != _COLOR_KEYS:
        raise VirtualPaletteError("virtual color keys differ")
    if value["schema_version"] != 1 or value["kind"] != VIRTUAL_COLOR_KIND:
        raise VirtualPaletteError("virtual color identity differs")
    color_id = value["color_id"]
    if not isinstance(color_id, str) or _COLOR_ID.fullmatch(color_id) is None:
        raise VirtualPaletteError("virtual color_id is invalid")
    profile = value["waveform_profile_sha256"]
    if not isinstance(profile, str) or _SHA256.fullmatch(profile) is None:
        raise VirtualPaletteError("waveform profile identity is invalid")
    target = _code(value["target_code"], label="target_code", nullable=False)
    primer = _code(value["primer_code"], label="primer_code", nullable=True)
    qualification = value["qualification"]
    if qualification not in _QUALIFICATIONS:
        raise VirtualPaletteError("virtual color qualification is invalid")
    lab = value["expected_lab"]
    if lab is None:
        if qualification != "unmeasured_candidate":
            raise VirtualPaletteError("measured/qualified virtual color requires Lab")
    else:
        if not isinstance(lab, Mapping) or set(lab) != _LAB_KEYS:
            raise VirtualPaletteError("expected_lab keys differ")
        _number(lab["l"], label="expected_lab.l", minimum=0.0, maximum=100.0)
        _number(lab["a"], label="expected_lab.a", minimum=-200.0, maximum=200.0)
        _number(lab["b"], label="expected_lab.b", minimum=-200.0, maximum=200.0)
    return {
        "color_id": color_id,
        "profile": profile,
        "target_code": target,
        "primer_code": primer,
        "qualification": qualification,
    }


def compile_virtual_palette(colors: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compile addressing facts without claiming all colours can coexist.

    A single waveform profile still has exactly eight direct target symbols.
    More virtual addresses are possible by adding profiles or primer sequences,
    but that implies multi-pass/state-control requirements.
    """

    if isinstance(colors, (str, bytes)) or not isinstance(colors, Sequence) or not colors:
        raise VirtualPaletteError("virtual palette must contain at least one color")
    validated = [validate_virtual_color(color) for color in colors]
    color_ids = [item["color_id"] for item in validated]
    if len(set(color_ids)) != len(color_ids):
        raise VirtualPaletteError("virtual color_id values must be unique")
    addresses = [
        (item["profile"], item["primer_code"], item["target_code"])
        for item in validated
    ]
    if len(set(addresses)) != len(addresses):
        raise VirtualPaletteError("virtual color addresses must be unique")

    profiles = sorted({item["profile"] for item in validated})
    direct = [item for item in validated if item["primer_code"] is None]
    sequence = [item for item in validated if item["primer_code"] is not None]
    per_profile: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        subset = [item for item in validated if item["profile"] == profile]
        direct_codes = sorted(
            item["target_code"] for item in subset if item["primer_code"] is None
        )
        sequence_pairs = sorted(
            [item["primer_code"], item["target_code"]]
            for item in subset
            if item["primer_code"] is not None
        )
        per_profile[profile] = {
            "virtual_color_count": len(subset),
            "direct_target_codes": direct_codes,
            "direct_target_count": len(direct_codes),
            "direct_capacity": 8,
            "sequence_addresses": sequence_pairs,
        }

    blockers: list[str] = []
    if len(profiles) > 1:
        blockers.append("cross_profile_coexistence_not_proven")
    if sequence:
        blockers.append("primer_history_state_control_required")
    if any(item["qualification"] != "qualified" for item in validated):
        blockers.append("contains_unqualified_virtual_colors")
    single_refresh = len(profiles) == 1 and not sequence and len(direct) <= 8
    return {
        "schema_version": 1,
        "kind": PALETTE_PLAN_KIND,
        "virtual_color_count": len(validated),
        "waveform_profile_count": len(profiles),
        "direct_color_count": len(direct),
        "sequence_color_count": len(sequence),
        "direct_capacity_per_profile": 8,
        "single_refresh_all_colors_possible_by_addressing": single_refresh,
        "multi_pass_or_profile_switch_required": not single_refresh,
        "per_profile": per_profile,
        "blocker_codes": blockers,
        "optical_distinctness_inferred": False,
        "hardware_io_performed": False,
        "visible_refresh_authorized": False,
    }
