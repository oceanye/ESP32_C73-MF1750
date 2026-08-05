"""Empty, optimizer-readable 6x6 transition profile scaffolding."""

from __future__ import annotations

from datetime import datetime
import math
import re
from typing import Any, Mapping

from .offline import COLOR_ORDER


NULL_MEASUREMENT_FIELDS = (
    "initial_lab_mean",
    "final_lab_mean",
    "delta_e00_mean",
    "delta_e00_sd",
    "cs1_minus_cs2_delta_e00",
    "position_effect_delta_e00",
    "ghosting_metric_mean",
    "busy_ms_mean",
    "peak_current_a_mean",
    "energy_j_mean",
    "temperature_rise_c_mean",
    "recovery_pass_rate",
)

CELL_PROVENANCE_FIELDS = (
    "source_run_sha256s",
    "asset_manifest_sha256s",
    "authorization_ids",
)

_PROFILE_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "panel_model",
        "color_codes",
        "hardware_tested",
        "generated_at",
        "panel_serial",
        "firmware_git_commit",
        "firmware_binary_sha256",
        "waveform_id",
        "waveform_sha256",
        "environment",
        "illuminant",
        "observer",
        "geometry",
        "cells",
    }
)
_CELL_KEYS = frozenset(
    {
        "old_code",
        "new_code",
        "sample_count",
        *NULL_MEASUREMENT_FIELDS,
        *CELL_PROVENANCE_FIELDS,
    }
)
_ENVIRONMENT_KEYS = frozenset(
    {"temperature_c", "relative_humidity_percent", "record_ref"}
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)

_NONNEGATIVE_FIELDS = (
    "delta_e00_mean",
    "delta_e00_sd",
    "position_effect_delta_e00",
    "ghosting_metric_mean",
    "busy_ms_mean",
    "peak_current_a_mean",
    "energy_j_mean",
)


def _require_finite_number(
    value: Any,
    *,
    label: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a JSON number")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{label} must be finite")
    if minimum is not None and numeric < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    if maximum is not None and numeric > maximum:
        raise ValueError(f"{label} must be at most {maximum}")
    return numeric


def _require_timestamp(value: Any, *, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty RFC 3339 timestamp")
    if _RFC3339.fullmatch(value) is None:
        raise ValueError(f"{label} must be a strict RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be a valid RFC 3339 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a UTC offset")


def _require_text(value: Any, *, label: str, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _require_hash(
    value: Any,
    *,
    label: str,
    pattern: re.Pattern[str] = _SHA256,
) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ValueError(f"{label} has an invalid digest identity")
    return value


def _validate_lab(value: Any, *, label: str) -> None:
    if not isinstance(value, Mapping) or set(value) != {"l", "a", "b"}:
        raise ValueError(f"{label} must contain exactly l, a and b")
    _require_finite_number(value["l"], label=f"{label}.l", minimum=0.0, maximum=100.0)
    _require_finite_number(value["a"], label=f"{label}.a", minimum=-200.0, maximum=200.0)
    _require_finite_number(value["b"], label=f"{label}.b", minimum=-200.0, maximum=200.0)


def _validate_measured_cell(cell: Mapping[str, Any], *, index: int) -> None:
    for field in ("initial_lab_mean", "final_lab_mean"):
        if cell[field] is None:
            raise ValueError(
                f"transition profile cell {index} with samples must provide {field}"
            )
        _validate_lab(cell[field], label=f"transition profile cell {index} {field}")

    for field in _NONNEGATIVE_FIELDS:
        if cell[field] is None:
            raise ValueError(
                f"transition profile cell {index} with samples must provide {field}"
            )
        _require_finite_number(
            cell[field],
            label=f"transition profile cell {index} {field}",
            minimum=0.0,
        )

    if cell["cs1_minus_cs2_delta_e00"] is None:
        raise ValueError(
            f"transition profile cell {index} with samples must provide "
            "cs1_minus_cs2_delta_e00"
        )
    _require_finite_number(
        cell["cs1_minus_cs2_delta_e00"],
        label=f"transition profile cell {index} cs1_minus_cs2_delta_e00",
        minimum=-200.0,
        maximum=200.0,
    )

    if cell["temperature_rise_c_mean"] is None:
        raise ValueError(
            f"transition profile cell {index} with samples must provide "
            "temperature_rise_c_mean"
        )
    _require_finite_number(
        cell["temperature_rise_c_mean"],
        label=f"transition profile cell {index} temperature_rise_c_mean",
        minimum=-200.0,
        maximum=200.0,
    )

    if cell["recovery_pass_rate"] is None:
        raise ValueError(
            f"transition profile cell {index} with samples must provide recovery_pass_rate"
        )
    _require_finite_number(
        cell["recovery_pass_rate"],
        label=f"transition profile cell {index} recovery_pass_rate",
        minimum=0.0,
        maximum=1.0,
    )

    sample_count = cell["sample_count"]
    for field in CELL_PROVENANCE_FIELDS:
        values = cell[field]
        if not isinstance(values, list) or len(values) != sample_count:
            raise ValueError(
                f"transition profile cell {index} {field} must contain one identity per sample"
            )
        if len(set(values)) != len(values):
            raise ValueError(
                f"transition profile cell {index} {field} must contain unique identities"
            )
        for item_index, value in enumerate(values):
            label = f"transition profile cell {index} {field}[{item_index}]"
            if field.endswith("sha256s"):
                _require_hash(value, label=label)
            else:
                _require_text(value, label=label)


def build_empty_transition_profile() -> dict[str, Any]:
    """Return all 36 transitions with every unmeasured value explicitly null."""

    cells = []
    for old_code in COLOR_ORDER:
        for new_code in COLOR_ORDER:
            cell: dict[str, Any] = {
                "old_code": old_code,
                "new_code": new_code,
                "sample_count": 0,
            }
            cell.update({field: None for field in NULL_MEASUREMENT_FIELDS})
            cell.update({field: None for field in CELL_PROVENANCE_FIELDS})
            cells.append(cell)
    return {
        "schema_version": 2,
        "kind": "mf1750-six-by-six-transition-profile",
        "panel_model": "MF-17506-M009F-T",
        "color_codes": list(COLOR_ORDER),
        "hardware_tested": False,
        "generated_at": None,
        "panel_serial": None,
        "firmware_git_commit": None,
        "firmware_binary_sha256": None,
        "waveform_id": None,
        "waveform_sha256": None,
        "environment": {
            "temperature_c": None,
            "relative_humidity_percent": None,
            "record_ref": None,
        },
        "illuminant": None,
        "observer": None,
        "geometry": None,
        "cells": cells,
    }


def validate_transition_profile(profile: Mapping[str, Any]) -> None:
    """Apply semantic checks JSON Schema cannot compactly express across 36 cells."""

    if not isinstance(profile, Mapping) or set(profile) != _PROFILE_KEYS:
        raise ValueError("transition profile has missing or unknown top-level keys")
    if profile["schema_version"] != 2:
        raise ValueError("transition profile schema_version must be 2")
    if profile["kind"] != "mf1750-six-by-six-transition-profile":
        raise ValueError("transition profile kind is invalid")
    if profile["panel_model"] != "MF-17506-M009F-T":
        raise ValueError("transition profile panel_model is invalid")
    if (
        not isinstance(profile["color_codes"], list)
        or any(type(code) is not int for code in profile["color_codes"])
        or profile["color_codes"] != list(COLOR_ORDER)
    ):
        raise ValueError("transition profile color_codes are not frozen")
    if type(profile["hardware_tested"]) is not bool:
        raise ValueError("transition profile hardware_tested must be a boolean")

    environment = profile["environment"]
    if not isinstance(environment, Mapping) or set(environment) != _ENVIRONMENT_KEYS:
        raise ValueError("transition profile environment has invalid keys")

    generated_at = profile["generated_at"]
    if profile["hardware_tested"]:
        _require_timestamp(generated_at, label="transition profile generated_at")
    elif generated_at is not None:
        raise ValueError(
            "transition profile generated_at must be null when hardware_tested is false"
        )

    expected = {(old, new) for old in COLOR_ORDER for new in COLOR_ORDER}
    cells = profile["cells"]
    if not isinstance(cells, list) or len(cells) != len(expected):
        raise ValueError("transition profile must contain exactly 36 cells")
    seen: set[tuple[int, int]] = set()
    measured_cell_count = 0
    for index, cell in enumerate(cells):
        if not isinstance(cell, Mapping) or set(cell) != _CELL_KEYS:
            raise ValueError(f"transition profile cell {index} has invalid keys")
        if type(cell["old_code"]) is not int or type(cell["new_code"]) is not int:
            raise ValueError(f"transition profile cell {index} color codes must be integers")
        pair = (cell["old_code"], cell["new_code"])
        if pair not in expected:
            raise ValueError(f"transition profile cell {index} has an invalid color pair")
        if pair in seen:
            raise ValueError(f"transition profile contains duplicate pair {pair}")
        seen.add(pair)
        sample_count = cell["sample_count"]
        if type(sample_count) is not int or not 0 <= sample_count <= 1_000_000:
            raise ValueError(f"transition profile cell {index} has invalid sample_count")
        if sample_count == 0:
            if any(
                cell[field] is not None
                for field in (*NULL_MEASUREMENT_FIELDS, *CELL_PROVENANCE_FIELDS)
            ):
                raise ValueError(
                    f"transition profile cell {index} must keep unmeasured values null and provenance null"
                )
        else:
            measured_cell_count += 1
            _validate_measured_cell(cell, index=index)
    if seen != expected:
        raise ValueError("transition profile does not contain every old/new pair exactly once")
    if profile["hardware_tested"] != (measured_cell_count > 0):
        raise ValueError(
            "transition profile hardware_tested must be true exactly when sampled cells exist"
        )

    context_fields = (
        "panel_serial",
        "firmware_git_commit",
        "firmware_binary_sha256",
        "waveform_id",
        "waveform_sha256",
        "illuminant",
        "observer",
        "geometry",
    )
    environment_values = tuple(environment[key] for key in _ENVIRONMENT_KEYS)
    if not profile["hardware_tested"]:
        if any(profile[field] is not None for field in context_fields) or any(
            value is not None for value in environment_values
        ):
            raise ValueError(
                "unmeasured transition profile must keep hardware provenance explicitly null"
            )
        return

    _require_text(profile["panel_serial"], label="transition profile panel_serial")
    _require_hash(
        profile["firmware_git_commit"],
        label="transition profile firmware_git_commit",
        pattern=_HEX40,
    )
    _require_hash(
        profile["firmware_binary_sha256"],
        label="transition profile firmware_binary_sha256",
    )
    _require_text(profile["waveform_id"], label="transition profile waveform_id")
    _require_hash(
        profile["waveform_sha256"], label="transition profile waveform_sha256"
    )
    if profile["illuminant"] != "D65":
        raise ValueError("transition profile illuminant must be D65")
    if profile["observer"] != "2deg":
        raise ValueError("transition profile observer must be 2deg")
    if profile["geometry"] != "45/0":
        raise ValueError("transition profile geometry must be 45/0")
    _require_finite_number(
        environment["temperature_c"],
        label="transition profile environment.temperature_c",
        minimum=-100,
        maximum=200,
    )
    _require_finite_number(
        environment["relative_humidity_percent"],
        label="transition profile environment.relative_humidity_percent",
        minimum=0,
        maximum=100,
    )
    _require_text(
        environment["record_ref"], label="transition profile environment.record_ref"
    )
