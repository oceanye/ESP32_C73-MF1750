#!/usr/bin/env python3
"""Compile the offline N5 optical-atlas and measurement campaign.

The default output is descriptive and hardware-blocked.  It declares one
shared P0 containing 11 supervised sessions / 22 fixed actions for the six
solid-code, three spatial-mix, optical-edge/kernel, and one 6x6 transition
atlas pass.  It performs no network, serial, GPIO, claim, authorization, or
device I/O.

Formal palette acquisition is a separate, stricter materialization: vertical
and horizontal fixtures, two excluded pilots, then three alternating formal
runs per orientation.  It can only be added to the same P0 when a reviewed
panel-cold profile is supplied.  Formal EC4 remains a frozen template until a
qualified recovery profile exists; a one-pass transition atlas can never emit
a measured transition profile.
"""

from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Optional, Sequence
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.epd_frame import (  # noqa: E402
    HEIGHT,
    WIDTH,
    generate_fixture,
    pack_pixels,
    pixel_counts,
    unpack_pixels,
    validate_frame,
)
from host.extended_color.aggregation import (  # noqa: E402
    PALETTE_PLAN_KIND,
    SCHEMA_VERSION as AGGREGATION_SCHEMA_VERSION,
    TRANSITION_FORMAL_PLAN_KIND,
    TRANSITION_PLAN_KIND,
    seal_measurement_plan,
    validate_measurement_plan,
)
from host.extended_color.offline import (  # noqa: E402
    COLOR_NAME_BY_CODE,
    COLOR_ORDER,
    build_artifact,
    frame_identity,
    generate_transition_matrix_frames,
)
from host.visible_refresh_campaign import (  # noqa: E402
    CampaignContractError,
    build_fixed_action_declaration,
    build_session_contract,
    canonical_json_bytes,
    seal_campaign_contract,
    validate_campaign_contract,
)
from tools.g1_s1_rc2g_n2_photo_campaign import FIRMWARE_CONTRACT  # noqa: E402


SCHEMA_VERSION = 1
KIND = "mf1750-n5-optical-atlas-campaign-manifest"
HASH_SCOPE = (
    "entire N5 manifest excluding integrity; UTF-8 JSON sorted keys, no "
    "whitespace, ensure_ascii=false, allow_nan=false"
)
SESSION_PROFILE_KIND = "mf1750-n5-session-power-profile"
RECOVERY_PROFILE_KIND = "mf1750-n5-reviewed-transition-recovery-profile"
RECOVERY_PROFILE_HASH_SCOPE = HASH_SCOPE.replace("N5 manifest", "transition recovery profile")
COMPILE_PROFILE_KIND = "mf1750-n5-production-compile-profile"
COMPILE_PROFILE_HASH_SCOPE = HASH_SCOPE.replace("N5 manifest", "production compile profile")
CAMPAIGN_ID = "mf1750-n5-optical-atlas-p0-v1"

MIX_RATIOS = ((1, 4), (1, 2), (3, 4))
MIX_PERIODS_PX = (4, 8, 16)
MIX_PAIR_GROUP_SIZE = 5
MIX_PIXEL_ROI_WIDTH = 64
MIX_PIXEL_ROI_HEIGHT = 48
PALETTE_CODE_ORDER = (1, 0, 3, 2, 5, 6)

DEFAULT_PANEL = {
    "model": "MF-17506-M009F-T",
    "serial": "UNBOUND-N5-OFFLINE",
    "board_id": "ESP32-C73",
    "pcb_revision": "rev-a1",
}
DEFAULT_FIRMWARE = dict(FIRMWARE_CONTRACT)

EXPECTED_DEFAULT_MANIFEST_CANONICAL_SHA256: Optional[str] = (
    "608ddc072f433fdce53c126508e2ba7d79ac83f19ee6e13dcd023035c804f4c3"
)
EXPECTED_DEFAULT_MANIFEST_FILE_SHA256: Optional[str] = (
    "578d9b0b1438fbb2a8a0df2d9053db961b96bbfa8de5d47cdc42f70b03b06065"
)

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class N5CampaignError(ValueError):
    """An N5 offline campaign, atlas, or formal template failed closed."""


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (CampaignContractError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N5CampaignError(f"value is not canonical JSON: {error}") from error


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _require_hash(value: Any, *, label: str, nullable: bool = False) -> Optional[str]:
    if value is None and nullable:
        return None
    if (
        not isinstance(value, str)
        or _SHA256_RE.fullmatch(value) is None
        or value == "0" * 64
    ):
        suffix = " or null" if nullable else ""
        raise N5CampaignError(f"{label} must be a non-placeholder lowercase SHA-256{suffix}")
    return value


_COMPILE_PROFILE_FIELDS = {
    "schema_version",
    "kind",
    "panel",
    "firmware",
    "formal_palette_cold_profile",
    "formal_transition_recovery_profile",
    "formal_transition_power_profile",
    "waveform_id",
    "waveform_sha256",
    "temperature_c",
    "relative_humidity_percent",
    "environment_record_sha256",
    "standard_table_canonical_sha256",
    "instrument_qualification_canonical_sha256",
    "pixel_pitch_review_artifact_sha256",
    "roi_aperture_fit_review_artifact_sha256",
    "orientation_bias_max_delta_e00",
    "u95_max_delta_e00",
    "acceptance_span_delta_e00",
    "acceptance_review_artifact_sha256",
    "acquisition_feasibility_review_artifact_sha256",
}


def _strict_json_file(path: Path, *, label: str) -> tuple[Mapping[str, Any], bytes]:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise N5CampaignError(f"cannot read {label}: {error}") from error

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise N5CampaignError(f"{label} contains duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                N5CampaignError(f"{label} contains unsupported constant {token}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise N5CampaignError(f"{label} is invalid JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise N5CampaignError(f"{label} must contain a JSON object")
    return value, payload


def seal_compile_profile(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Seal caller-reviewed N5 production compiler inputs without I/O."""

    if not isinstance(payload, Mapping) or "integrity" in payload:
        raise N5CampaignError("N5 compile profile payload must omit integrity")
    unsigned = _snapshot(payload)
    profile = {
        **unsigned,
        "integrity": {
            "canonical_sha256": _sha256(unsigned),
            "canonical_sha256_scope": COMPILE_PROFILE_HASH_SCOPE,
        },
    }
    validate_compile_profile(profile)
    return profile


def validate_compile_profile(profile: Mapping[str, Any]) -> Mapping[str, Any]:
    """Fail closed unless every full 73-action compiler input is explicit."""

    if not isinstance(profile, Mapping) or set(profile) != {
        *_COMPILE_PROFILE_FIELDS,
        "integrity",
    }:
        raise N5CampaignError("N5 production compile profile keys changed")
    if (
        profile["schema_version"] != SCHEMA_VERSION
        or profile["kind"] != COMPILE_PROFILE_KIND
    ):
        raise N5CampaignError("N5 production compile profile identity changed")
    for field in (
        "panel",
        "firmware",
        "formal_palette_cold_profile",
        "formal_transition_recovery_profile",
        "formal_transition_power_profile",
    ):
        if not isinstance(profile[field], Mapping):
            raise N5CampaignError(f"N5 compile profile {field} must be an object")
    panel = profile["panel"]
    if not isinstance(panel.get("serial"), str) or not panel["serial"] or "UNBOUND" in panel["serial"]:
        raise N5CampaignError("N5 production compile profile requires a physical panel serial")
    if not isinstance(profile["waveform_id"], str) or not profile["waveform_id"]:
        raise N5CampaignError("N5 production compile profile requires waveform_id")
    for field in (
        "waveform_sha256",
        "environment_record_sha256",
        "standard_table_canonical_sha256",
        "instrument_qualification_canonical_sha256",
        "pixel_pitch_review_artifact_sha256",
        "roi_aperture_fit_review_artifact_sha256",
        "acceptance_review_artifact_sha256",
        "acquisition_feasibility_review_artifact_sha256",
    ):
        _require_hash(profile[field], label=f"compile profile {field}")
    for field in (
        "temperature_c",
        "relative_humidity_percent",
        "orientation_bias_max_delta_e00",
        "u95_max_delta_e00",
        "acceptance_span_delta_e00",
    ):
        value = profile[field]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise N5CampaignError(f"compile profile {field} must be finite")
    if not 0 <= float(profile["relative_humidity_percent"]) <= 100:
        raise N5CampaignError("compile profile relative humidity is outside 0..100 percent")
    if any(
        float(profile[field]) <= 0
        for field in (
            "orientation_bias_max_delta_e00",
            "u95_max_delta_e00",
            "acceptance_span_delta_e00",
        )
    ):
        raise N5CampaignError("N5 reviewed acceptance thresholds must be positive")
    _validate_session_profile(profile["formal_palette_cold_profile"])
    _validate_session_profile(profile["formal_transition_power_profile"])
    validate_transition_recovery_profile(profile["formal_transition_recovery_profile"])
    unsigned = dict(profile)
    integrity = unsigned.pop("integrity")
    if integrity != {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": COMPILE_PROFILE_HASH_SCOPE,
    }:
        raise N5CampaignError("N5 production compile profile integrity is invalid")
    return profile


def compile_manifest_from_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Materialize and deeply validate the immutable 73-action production plan."""

    root = validate_compile_profile(profile)
    manifest = compile_campaign_manifest(
        **{field: _snapshot(root[field]) for field in _COMPILE_PROFILE_FIELDS if field not in {"schema_version", "kind"}}
    )
    validate_compiled_manifest(manifest)
    if (
        manifest["counts"]["declared_actions"] != 73
        or manifest["counts"]["declared_sessions"] != 26
        or manifest["formal_palette_plan"] is None
        or manifest["formal_transition_plan"] is None
        or not manifest["formal_palette_plan"]["readiness"]["measurement_ready"]
        or not manifest["formal_transition_plan"]["readiness"]["measurement_ready"]
    ):
        raise N5CampaignError("production compile profile did not materialize ready 73-action N5")
    from host.extended_color.execution import (  # local import avoids compiler cycle
        compile_execution_contract,
        validate_execution_contract,
    )

    contract = compile_execution_contract(manifest)
    validate_execution_contract(contract)
    counts = {
        plan_class: sum(action["plan_class"] == plan_class for action in contract["actions"])
        for plan_class in ("descriptive", "formal_palette", "formal_transition")
    }
    if counts != {"descriptive": 22, "formal_palette": 9, "formal_transition": 42}:
        raise N5CampaignError("N5 production execution identities/counts changed")
    return manifest


def _publish_new_bytes(destination: Path, payload: bytes) -> None:
    """Atomically publish fully flushed bytes without ever replacing a target."""

    parent = destination.parent
    if not parent.is_dir():
        raise N5CampaignError("N5 compile output parent directory does not exist")
    temporary = parent / f".{destination.name}.{uuid.uuid4().hex}.tmp"
    try:
        try:
            with temporary.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, destination)
            except FileExistsError as error:
                raise N5CampaignError(
                    "N5 compile output already exists; refusing overwrite"
                ) from error
            except OSError as error:
                if destination.exists():
                    raise N5CampaignError(
                        "N5 compile output publish lost an exclusive-create race; "
                        "refusing overwrite"
                    ) from error
                raise N5CampaignError(
                    f"cannot atomically publish N5 compile output: {error}"
                ) from error
        except N5CampaignError:
            raise
        except OSError as error:
            raise N5CampaignError(
                f"cannot stage N5 compile output for atomic publication: {error}"
            ) from error
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


def compile_manifest_file(profile_file: Path, output_file: Path) -> dict[str, Any]:
    """Strict compile CLI implementation with exclusive atomic publication."""

    profile, profile_payload = _strict_json_file(
        profile_file, label="N5 production compile profile"
    )
    manifest = compile_manifest_from_profile(profile)
    payload = canonical_json_bytes(manifest)
    _publish_new_bytes(output_file, payload)
    stored, stored_payload = _strict_json_file(output_file, label="stored N5 production manifest")
    if stored_payload != payload or stored_payload != canonical_json_bytes(stored):
        raise N5CampaignError("stored N5 production manifest bytes are not canonical/exact")
    validate_compiled_manifest(stored)
    if manifest_file_sha256(stored) != hashlib.sha256(stored_payload).hexdigest():
        raise N5CampaignError("stored N5 production manifest whole-file hash changed")
    from host.extended_color.execution import compile_execution_contract, validate_execution_contract

    contract = compile_execution_contract(stored)
    validate_execution_contract(contract)
    if len(contract["actions"]) != 73 or len(contract["sessions"]) != 26:
        raise N5CampaignError("stored N5 production execution contract count changed")
    return {
        "manifest": stored,
        "compile_profile_canonical_sha256": profile["integrity"][
            "canonical_sha256"
        ],
        "compile_profile_file_sha256": hashlib.sha256(profile_payload).hexdigest(),
        "manifest_canonical_sha256": stored["integrity"]["canonical_sha256"],
        "manifest_file_sha256": hashlib.sha256(stored_payload).hexdigest(),
        "declared_actions": 73,
        "declared_sessions": 26,
        "output": str(output_file.resolve()),
        "atomic_exclusive_create": True,
        "deep_validation_passed": True,
        "network_io_performed": False,
        "device_io_performed": False,
        "claim_created": False,
        "authorization_created": False,
    }


def ordinary_session_profile() -> dict[str, Any]:
    """Ordinary supervised work; neither controller nor J2 cycling is required."""

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": SESSION_PROFILE_KIND,
        "profile_id": "n5-supervised-continuous-j2-retained-v1",
        "power_mode": "supervised_continuous",
        "minimum_panel_power_off_seconds": None,
        "review_artifact_sha256": None,
        "reviewed": False,
    }


def reviewed_panel_cold_profile(
    *, minimum_panel_power_off_seconds: int | float, review_artifact_sha256: str
) -> dict[str, Any]:
    """Bind formal independent runs to an externally reviewed cold profile."""

    if (
        isinstance(minimum_panel_power_off_seconds, bool)
        or not isinstance(minimum_panel_power_off_seconds, (int, float))
        or not math.isfinite(float(minimum_panel_power_off_seconds))
        or float(minimum_panel_power_off_seconds) <= 0
    ):
        raise N5CampaignError("reviewed panel-cold dwell must be positive and finite")
    review_sha = _require_hash(
        review_artifact_sha256, label="panel-cold review artifact"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": SESSION_PROFILE_KIND,
        "profile_id": "n5-reviewed-panel-cold-independent-run-v1",
        "power_mode": "panel_cold_cycle",
        "minimum_panel_power_off_seconds": float(minimum_panel_power_off_seconds),
        "review_artifact_sha256": review_sha,
        "reviewed": True,
    }


def _validate_session_profile(value: Mapping[str, Any]) -> Mapping[str, Any]:
    expected_keys = {
        "schema_version",
        "kind",
        "profile_id",
        "power_mode",
        "minimum_panel_power_off_seconds",
        "review_artifact_sha256",
        "reviewed",
    }
    if not isinstance(value, Mapping) or set(value) != expected_keys:
        raise N5CampaignError("session power profile keys changed")
    if value["schema_version"] != SCHEMA_VERSION or value["kind"] != SESSION_PROFILE_KIND:
        raise N5CampaignError("session power profile schema or kind changed")
    if value["power_mode"] == "supervised_continuous":
        if value != ordinary_session_profile():
            raise N5CampaignError("ordinary sessions must not imply a J2 or boot cycle")
    elif value["power_mode"] == "panel_cold_cycle":
        if value["reviewed"] is not True:
            raise N5CampaignError("panel-cold profile must be explicitly reviewed")
        dwell = value["minimum_panel_power_off_seconds"]
        if (
            isinstance(dwell, bool)
            or not isinstance(dwell, (int, float))
            or not math.isfinite(float(dwell))
            or float(dwell) <= 0
        ):
            raise N5CampaignError("panel-cold profile requires positive measured dwell")
        _require_hash(value["review_artifact_sha256"], label="panel-cold review artifact")
    else:
        raise N5CampaignError("unsupported N5 session power mode")
    return value


def _frame_record(frame: bytes) -> dict[str, Any]:
    identity = frame_identity(frame)
    return {
        "width": WIDTH,
        "height": HEIGHT,
        "bits_per_pixel": 4,
        "bytes": identity.frame_bytes,
        "sha256": identity.frame_sha256,
        "fnv1a": f"0x{identity.frame_fnv1a:08X}",
        "controllers": [
            {
                "controller": controller.controller,
                "mapping": {
                    "source_half": controller.mapping.source_half,
                    "flip_x": controller.mapping.flip_x,
                    "flip_y": controller.mapping.flip_y,
                    "nibble_swap": controller.mapping.nibble_swap,
                },
                "dtm_bytes": controller.dtm_bytes,
                "dtm_sha256": controller.dtm_sha256,
                "dtm_fnv1a": f"0x{controller.dtm_fnv1a:08X}",
            }
            for controller in identity.controllers
        ],
    }


def _histogram(frame: bytes) -> dict[str, int]:
    counts = pixel_counts(frame)
    if sum(counts) != WIDTH * HEIGHT:
        raise N5CampaignError("frame histogram does not cover the panel")
    if any(counts[code] for code in range(16) if code not in COLOR_ORDER):
        raise N5CampaignError("N5 atlas contains a non-formal physical code")
    return {str(code): counts[code] for code in COLOR_ORDER}


def _is_mirrored(frame: bytes) -> bool:
    pixels = unpack_pixels(frame)
    return all(
        pixels[y * WIDTH + x] == pixels[y * WIDTH + (WIDTH - 1 - x)]
        for y in range(HEIGHT)
        for x in range(WIDTH // 2)
    )


def _bounds(index: int, count: int, extent: int) -> tuple[int, int]:
    return (
        (index * extent + count - 1) // count,
        ((index + 1) * extent + count - 1) // count,
    )


def _rect(x0: int, y0: int, x1: int, y1: int) -> dict[str, int]:
    return {
        "x0": x0,
        "y0": y0,
        "x1": x1,
        "y1": y1,
        "width": x1 - x0,
        "height": y1 - y0,
    }


def _measurement_roi(
    *, x0: int, y0: int, x1: int, y1: int, width: int, height: int
) -> dict[str, int]:
    if width > x1 - x0 or height > y1 - y0:
        raise N5CampaignError("measurement ROI does not fit inside its atlas cell")
    roi_x0 = x0 + ((x1 - x0) - width) // 2
    roi_y0 = y0 + ((y1 - y0) - height) // 2
    guard = min(roi_x0 - x0, x1 - (roi_x0 + width), roi_y0 - y0, y1 - (roi_y0 + height))
    return {
        "x0": roi_x0,
        "y0": roi_y0,
        "x1": roi_x0 + width,
        "y1": roi_y0 + height,
        "width": width,
        "height": height,
        "guard_pixels": guard,
    }


def _mix_cells(group_index: int) -> list[dict[str, Any]]:
    pairs = list(itertools.combinations(COLOR_ORDER, 2))
    group_pairs = pairs[
        group_index * MIX_PAIR_GROUP_SIZE : (group_index + 1) * MIX_PAIR_GROUP_SIZE
    ]
    result: list[dict[str, Any]] = []
    for pair_index, pair in enumerate(group_pairs):
        local_x0, local_x1 = _bounds(pair_index, 5, WIDTH // 2)
        for ratio_index, ratio in enumerate(MIX_RATIOS):
            for period_index, period in enumerate(MIX_PERIODS_PX):
                row = ratio_index * len(MIX_PERIODS_PX) + period_index
                y0, y1 = _bounds(row, 9, HEIGHT)
                for half_index, controller in enumerate(("CS1", "CS2")):
                    if half_index == 0:
                        x0, x1 = local_x0, local_x1
                    else:
                        x0, x1 = WIDTH - local_x1, WIDTH - local_x0
                    result.append(
                        {
                            "roi_id": (
                                f"mix-g{group_index + 1}-{controller.lower()}-"
                                f"{pair[0]}-{pair[1]}-r{ratio[0]}of{ratio[1]}-p{period}"
                            ),
                            "controller": controller,
                            "pair_codes": list(pair),
                            "pair_names": [COLOR_NAME_BY_CODE[code] for code in pair],
                            "second_code_area_ratio": ratio[0] / ratio[1],
                            "ratio_fraction": list(ratio),
                            "spatial_period_pixels": period,
                            "cell": _rect(x0, y0, x1, y1),
                            "pixel_roi": _measurement_roi(
                                x0=x0,
                                y0=y0,
                                x1=x1,
                                y1=y1,
                                width=MIX_PIXEL_ROI_WIDTH,
                                height=MIX_PIXEL_ROI_HEIGHT,
                            ),
                        }
                    )
    if len(result) != 90:
        raise N5CampaignError("each mix atlas must have 45 cells on both controller halves")
    return result


@lru_cache(maxsize=3)
def _generate_mix_frame(group_index: int) -> bytes:
    if type(group_index) is not int or not 0 <= group_index < 3:
        raise N5CampaignError("mix atlas group must be 0, 1, or 2")
    pairs = list(itertools.combinations(COLOR_ORDER, 2))[
        group_index * MIX_PAIR_GROUP_SIZE : (group_index + 1) * MIX_PAIR_GROUP_SIZE
    ]

    def pixel_at(x: int, y: int) -> int:
        local_x = x if x < WIDTH // 2 else WIDTH - 1 - x
        pair_index = min(4, local_x * 5 // (WIDTH // 2))
        row = min(8, y * 9 // HEIGHT)
        ratio = MIX_RATIOS[row // 3]
        period = MIX_PERIODS_PX[row % 3]
        cell_x0, _ = _bounds(pair_index, 5, WIDTH // 2)
        phase = (local_x - cell_x0) % period
        second_pixels = ratio[0] * period // ratio[1]
        return pairs[pair_index][1] if phase < second_pixels else pairs[pair_index][0]

    frame = pack_pixels(pixel_at(x, y) for y in range(HEIGHT) for x in range(WIDTH))
    validate_frame(frame)
    if not _is_mirrored(frame):
        raise N5CampaignError("mix atlas controller halves are not mirrored")
    return frame


def _kernel_cells() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for color_index, code in enumerate(COLOR_ORDER):
        local_x0, local_x1 = _bounds(color_index, 6, WIDTH // 2)
        for row_index, mode in enumerate(("vertical-edge-esf", "square-impulse-psf")):
            y0, y1 = _bounds(row_index, 2, HEIGHT)
            for half_index, controller in enumerate(("CS1", "CS2")):
                if half_index == 0:
                    x0, x1 = local_x0, local_x1
                else:
                    x0, x1 = WIDTH - local_x1, WIDTH - local_x0
                result.append(
                    {
                        "roi_id": f"kernel-{controller.lower()}-{mode}-code-{code}",
                        "controller": controller,
                        "mode": mode,
                        "target_code": code,
                        "target_name": COLOR_NAME_BY_CODE[code],
                        "background_code": 1 if code == 0 else 0,
                        "cell": _rect(x0, y0, x1, y1),
                        "imaging_roi": _measurement_roi(
                            x0=x0,
                            y0=y0,
                            x1=x1,
                            y1=y1,
                            width=64,
                            height=128 if mode == "vertical-edge-esf" else 64,
                        ),
                    }
                )
    return result


@lru_cache(maxsize=1)
def _generate_kernel_frame() -> bytes:
    def pixel_at(x: int, y: int) -> int:
        local_x = x if x < WIDTH // 2 else WIDTH - 1 - x
        color_index = min(5, local_x * 6 // (WIDTH // 2))
        x0, x1 = _bounds(color_index, 6, WIDTH // 2)
        code = COLOR_ORDER[color_index]
        background = 1 if code == 0 else 0
        if y < HEIGHT // 2:
            return code if local_x >= (x0 + x1) // 2 else background
        center_x = (x0 + x1) // 2
        center_y = 3 * HEIGHT // 4
        return code if abs(local_x - center_x) < 8 and abs(y - center_y) < 8 else background

    frame = pack_pixels(pixel_at(x, y) for y in range(HEIGHT) for x in range(WIDTH))
    validate_frame(frame)
    if not _is_mirrored(frame):
        raise N5CampaignError("optical kernel atlas controller halves are not mirrored")
    return frame


def _solid_rois(code: int) -> list[dict[str, Any]]:
    return [
        {
            "roi_id": f"solid-{COLOR_NAME_BY_CODE[code]}-{controller.lower()}",
            "controller": controller,
            "code": code,
            "pixel_roi": _measurement_roi(
                x0=0 if controller == "CS1" else WIDTH // 2,
                y0=0,
                x1=WIDTH // 2 if controller == "CS1" else WIDTH,
                y1=HEIGHT,
                width=128,
                height=128,
            ),
        }
        for controller in ("CS1", "CS2")
    ]


@lru_cache(maxsize=1)
def build_atlas() -> dict[str, Any]:
    """Build deterministic formal-code-only atlas identities and pixel ROIs."""

    assets: list[dict[str, Any]] = []
    for code in COLOR_ORDER:
        artifact = build_artifact(f"solid-{COLOR_NAME_BY_CODE[code]}")
        assets.append(
            {
                "asset_id": f"n5-solid-code-{code}",
                "category": "solid-physical-code",
                "evidence_level": "descriptive-atlas-not-calibrated-palette",
                "frame": _frame_record(artifact.frame),
                "physical_code_histogram": _histogram(artifact.frame),
                "mirrored_controller_halves": _is_mirrored(artifact.frame),
                "rois": _solid_rois(code),
                "measurement_semantics": "point spectral reflectance candidate",
            }
        )
    for group_index in range(3):
        frame = _generate_mix_frame(group_index)
        assets.append(
            {
                "asset_id": f"n5-mix-atlas-{group_index + 1}",
                "category": "spatial-area-mix-atlas",
                "evidence_level": "descriptive-spatial-atlas",
                "frame": _frame_record(frame),
                "physical_code_histogram": _histogram(frame),
                "mirrored_controller_halves": True,
                "rois": _mix_cells(group_index),
                "measurement_semantics": (
                    "64x48 is a pixel ROI only; physical size and aperture fit are unbound"
                ),
            }
        )
    kernel = _generate_kernel_frame()
    assets.append(
        {
            "asset_id": "n5-optical-edge-kernel-atlas",
            "category": "imaging-esf-psf-atlas",
            "evidence_level": "descriptive-imaging-only",
            "frame": _frame_record(kernel),
            "physical_code_histogram": _histogram(kernel),
            "mirrored_controller_halves": True,
            "rois": _kernel_cells(),
            "measurement_semantics": (
                "camera imaging ESF/PSF asset; a single-point Lab reading is not an optical kernel"
            ),
        }
    )
    matrix = generate_transition_matrix_frames(1)
    for role, frame in (("initial", matrix.initial), ("target", matrix.target)):
        assets.append(
            {
                "asset_id": f"n5-transition-{role}-r1",
                "category": "six-by-six-transition-atlas",
                "evidence_level": "descriptive-pilot-only",
                "frame": _frame_record(frame),
                "physical_code_histogram": _histogram(frame),
                "mirrored_controller_halves": _is_mirrored(frame),
                "rois": [roi.to_dict() for roi in matrix.rois],
                "measurement_semantics": f"EC4 {role} frame, one descriptive pass only",
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-n5-optical-atlas",
        "formal_physical_codes": list(COLOR_ORDER),
        "unknown_codes_present": False,
        "asset_count": len(assets),
        "assets": assets,
        "mix_contract": {
            "unordered_pair_count": 15,
            "frames": 3,
            "pairs_per_frame": 5,
            "ratios": [list(value) for value in MIX_RATIOS],
            "spatial_periods_pixels": list(MIX_PERIODS_PX),
            "cells_per_controller_per_frame": 45,
            "pixel_roi": {"width": 64, "height": 48},
            "measurement_ready": False,
            "blockers": [
                "pixel_pitch_or_physical_roi_size_not_reviewed",
                "instrument_aperture_fit_not_reviewed",
            ],
        },
        "kernel_contract": {
            "asset_type": "camera-imaging-ESF-PSF",
            "single_point_lab_is_kernel": False,
            "measurement_ready": False,
            "blockers": [
                "pixel_pitch_not_bound",
                "camera_MTF_ESF_PSF_analysis_contract_not_reviewed",
                "external_RAW_spatial_illumination_not_bound",
            ],
        },
    }


def _atlas_asset(atlas: Mapping[str, Any], asset_id: str) -> Mapping[str, Any]:
    matches = [asset for asset in atlas["assets"] if asset["asset_id"] == asset_id]
    if len(matches) != 1:
        raise N5CampaignError(f"atlas asset {asset_id!r} is not unique")
    return matches[0]


def _build_pair(
    *,
    campaign_id: str,
    session_id: str,
    cell_id: str,
    map_frame: Mapping[str, Any],
    target_frame: Mapping[str, Any],
    session_profile: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    primer = build_fixed_action_declaration(
        campaign_id=campaign_id,
        session_id=session_id,
        cell_id=cell_id,
        action_id=f"{cell_id}-map-primer",
        phase="known-map-primer",
        frame=map_frame,
    )
    target = build_fixed_action_declaration(
        campaign_id=campaign_id,
        session_id=session_id,
        cell_id=cell_id,
        action_id=f"{cell_id}-target",
        phase="descriptive-atlas-target",
        frame=target_frame,
        prior_action_identity_sha256=primer["action_identity_sha256"],
        prior_scope="same_cell",
    )
    profile = _validate_session_profile(session_profile)
    session = build_session_contract(
        session_id=session_id,
        cell_id=cell_id,
        power_mode=profile["power_mode"],
        planned_cooldown_seconds=0,
        final_power_off_required=False,
        action_identity_sha256s=[
            primer["action_identity_sha256"],
            target["action_identity_sha256"],
        ],
        minimum_panel_power_off_seconds=profile["minimum_panel_power_off_seconds"],
    )
    route = {
        "session_id": session_id,
        "cell_id": cell_id,
        "primer_action_identity_sha256": primer["action_identity_sha256"],
        "target_action_identity_sha256": target["action_identity_sha256"],
    }
    return [primer, target], session, route


def _build_transition_pair(
    *, campaign_id: str, initial_frame: Mapping[str, Any], target_frame: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    session_id = "n5-transition-descriptive-session"
    cell_id = "n5-transition-descriptive"
    initial = build_fixed_action_declaration(
        campaign_id=campaign_id,
        session_id=session_id,
        cell_id=cell_id,
        action_id="n5-transition-known-initial",
        phase="transition-known-initial",
        frame=initial_frame,
    )
    target = build_fixed_action_declaration(
        campaign_id=campaign_id,
        session_id=session_id,
        cell_id=cell_id,
        action_id="n5-transition-target",
        phase="transition-target",
        frame=target_frame,
        prior_action_identity_sha256=initial["action_identity_sha256"],
        prior_scope="same_cell",
    )
    session = build_session_contract(
        session_id=session_id,
        cell_id=cell_id,
        power_mode="supervised_continuous",
        planned_cooldown_seconds=0,
        final_power_off_required=False,
        action_identity_sha256s=[
            initial["action_identity_sha256"],
            target["action_identity_sha256"],
        ],
    )
    return [initial, target], session, {
        "session_id": session_id,
        "cell_id": cell_id,
        "primer_action_identity_sha256": initial["action_identity_sha256"],
        "target_action_identity_sha256": target["action_identity_sha256"],
    }


def _measurement_context(
    *,
    panel: Mapping[str, Any],
    firmware: Mapping[str, Any],
    waveform_id: Optional[str],
    waveform_sha256: Optional[str],
    temperature_c: Optional[float],
    relative_humidity_percent: Optional[float],
    environment_record_sha256: Optional[str],
    standard_table_canonical_sha256: Optional[str],
    instrument_qualification_canonical_sha256: Optional[str],
    pixel_pitch_review_artifact_sha256: Optional[str],
    roi_aperture_fit_review_artifact_sha256: Optional[str],
) -> dict[str, Any]:
    return {
        "panel": _snapshot(panel),
        "firmware": _snapshot(firmware),
        "waveform": {
            "waveform_id": waveform_id,
            "waveform_sha256": waveform_sha256,
        },
        "environment": {
            "temperature_c": temperature_c,
            "relative_humidity_percent": relative_humidity_percent,
            "record_sha256": environment_record_sha256,
        },
        "condition": {
            "geometry": "45/0",
            "illuminant": "D65",
            "observer": "2deg",
            "standard_table_canonical_sha256": standard_table_canonical_sha256,
            "instrument_qualification_canonical_sha256": (
                instrument_qualification_canonical_sha256
            ),
            "pixel_pitch_review_artifact_sha256": pixel_pitch_review_artifact_sha256,
            "roi_aperture_fit_review_artifact_sha256": (
                roi_aperture_fit_review_artifact_sha256
            ),
        },
    }


def _roi_for_transition(value: Mapping[str, Any]) -> dict[str, int]:
    measurement = value["measurement"]
    cell = value["cell"]
    return {
        "x0": measurement["x0"],
        "y0": measurement["y0"],
        "x1": measurement["x1"],
        "y1": measurement["y1"],
        "width": measurement["width"],
        "height": measurement["height"],
        "guard_pixels": min(
            measurement["x0"] - cell["x0"],
            cell["x1"] - measurement["x1"],
            measurement["y0"] - cell["y0"],
            cell["y1"] - measurement["y1"],
        ),
    }


def build_descriptive_transition_plan(
    *, context: Mapping[str, Any], route: Mapping[str, Any]
) -> dict[str, Any]:
    from host.extended_color.aggregation import measurement_context_blockers

    matrix = generate_transition_matrix_frames(1)
    slots = [
        {
            "slot_id": roi.roi_id,
            "controller": roi.controller,
            "old_code": roi.old_code,
            "new_code": roi.target_code,
            "roi": _roi_for_transition(roi.to_dict()),
            "primer_action_identity_sha256": route[
                "primer_action_identity_sha256"
            ],
            "target_action_identity_sha256": route[
                "target_action_identity_sha256"
            ],
        }
        for roi in matrix.rois
    ]
    context_snapshot = _snapshot(context)
    blockers = [
        *measurement_context_blockers(context_snapshot),
        "descriptive_transition_atlas_cannot_emit_measured_profile",
    ]
    return seal_measurement_plan(
        {
            "schema_version": AGGREGATION_SCHEMA_VERSION,
            "kind": TRANSITION_PLAN_KIND,
            "plan_id": "n5-transition-descriptive-r1",
            "context": context_snapshot,
            "design": {
                "evidence_level": "descriptive-pilot-only",
                "pilot_required": True,
                "pilot_repeats_per_pair": 2,
                "pilot_excluded_from_formal_n": True,
                "formal_repeats": 1,
                "rotation_algorithm": (
                    "opposed-cyclic-old-and-target-orders-repetition-offset-v1"
                ),
                "recovery_actions_per_formal_repeat": 0,
                "recovery_sequence": [],
                "recovery_profile_canonical_sha256": None,
                "recovery_profile_review_artifact_sha256": None,
            },
            "required_samples_per_cell": 2,
            "expected_slots": slots,
            "readiness": {
                "measurement_ready": not blockers,
                "blockers": blockers,
            },
        }
    )


def _palette_fixture_rois(orientation: str) -> dict[int, dict[str, Any]]:
    if orientation not in {"vertical", "horizontal"}:
        raise N5CampaignError("palette orientation must be vertical or horizontal")
    result: dict[int, dict[str, Any]] = {}
    for index, code in enumerate(PALETTE_CODE_ORDER):
        if orientation == "vertical":
            x0, x1 = _bounds(index, 6, WIDTH)
            y0, y1 = 0, HEIGHT
            controller = "CS1" if x1 <= WIDTH // 2 else "CS2"
            cell_x0, cell_x1 = x0, x1
        else:
            y0, y1 = _bounds(index, 6, HEIGHT)
            # Choose the controller opposite the vertical fixture so every
            # code receives exactly 0.5 CS1 / 0.5 CS2 weight over six runs.
            vertical_controller = "CS1" if index < 3 else "CS2"
            controller = "CS2" if vertical_controller == "CS1" else "CS1"
            cell_x0 = 0 if controller == "CS1" else WIDTH // 2
            cell_x1 = WIDTH // 2 if controller == "CS1" else WIDTH
        result[code] = {
            "controller": controller,
            "roi": _measurement_roi(
                x0=cell_x0,
                y0=y0,
                x1=cell_x1,
                y1=y1,
                width=64,
                height=48,
            ),
        }
    return result


def build_formal_palette_plan(
    *,
    context: Mapping[str, Any],
    formal_routes: Sequence[Mapping[str, Any]],
    orientation_bias_max_delta_e00: Optional[float] = None,
    u95_max_delta_e00: Optional[float] = None,
    acceptance_span_delta_e00: Optional[float] = None,
    acceptance_review_artifact_sha256: Optional[str] = None,
    acquisition_feasibility_review_artifact_sha256: Optional[str] = None,
) -> dict[str, Any]:
    """Seal the only plan kind allowed to produce calibrated=true."""

    route_by_key = {
        (route["orientation"], route["formal_run"]): route
        for route in formal_routes
    }
    expected_keys = {
        (orientation, formal_run)
        for orientation in ("vertical", "horizontal")
        for formal_run in range(1, 4)
    }
    if set(route_by_key) != expected_keys or len(formal_routes) != 6:
        raise N5CampaignError("formal palette requires six unique orientation/run routes")
    slots = []
    for orientation in ("vertical", "horizontal"):
        rois = _palette_fixture_rois(orientation)
        for formal_run in range(1, 4):
            route = route_by_key[(orientation, formal_run)]
            for order, code in enumerate(PALETTE_CODE_ORDER, start=1):
                slots.append(
                    {
                        "slot_id": (
                            f"palette-{orientation}-formal-{formal_run:02d}-"
                            f"code-{code}"
                        ),
                        "controller": rois[code]["controller"],
                        "code": code,
                        "orientation": orientation,
                        "formal_run": formal_run,
                        "measurement_order": order,
                        "orientation_weight": 0.5,
                        "controller_weight": 0.5,
                        "roi": rois[code]["roi"],
                        "primer_action_identity_sha256": route[
                            "primer_action_identity_sha256"
                        ],
                        "target_action_identity_sha256": route[
                            "target_action_identity_sha256"
                        ],
                    }
                )
    design = {
        "fixture_orientations": ["vertical", "horizontal"],
        "pilot_sequence": ["vertical-pilot", "horizontal-pilot"],
        "pilot_excluded_from_formal_n": True,
        "formal_runs_per_orientation": 3,
        "formal_run_sequence": [
            "vertical-formal-01",
            "horizontal-formal-01",
            "vertical-formal-02",
            "horizontal-formal-02",
            "vertical-formal-03",
            "horizontal-formal-03",
        ],
        "readings_per_run": 6,
        "measurement_code_order": list(PALETTE_CODE_ORDER),
        "controller_assignment_by_orientation": {
            orientation: {
                str(code): _palette_fixture_rois(orientation)[code]["controller"]
                for code in COLOR_ORDER
            }
            for orientation in ("vertical", "horizontal")
        },
        "acquisition_window_after_pof_busy_high_seconds": {
            "minimum": 55.0,
            "maximum": 65.0,
            "anchor": "POF_BUSY_N_low_to_high",
        },
        "aggregation": {
            "orientation_weights": {"vertical": 0.5, "horizontal": 0.5},
            "controller_weights_by_code": {
                str(code): {"CS1": 0.5, "CS2": 0.5} for code in COLOR_ORDER
            },
            "run_level_method": (
                "arithmetic mean of three preregistered runs within each orientation/code"
            ),
            "between_run_method": (
                "equal-weight mean of vertical and horizontal orientation means"
            ),
            "missing_value_rule": "reject-entire-palette-no-imputation",
            "outlier_rule": "report-all-preregistered-observations-never-delete",
            "u95_method": (
                "k=2*sqrt((instrument_expanded_uncertainty_delta_e00/2)^2+"
                "sample_sd_delta_e00_about_final_mean^2)"
            ),
            "orientation_bias_max_delta_e00": orientation_bias_max_delta_e00,
            "u95_max_delta_e00": u95_max_delta_e00,
            "acceptance_span_delta_e00": acceptance_span_delta_e00,
            "gage_rr_max_percent_of_acceptance_span": 10.0,
            "acceptance_review_artifact_sha256": acceptance_review_artifact_sha256,
            "acquisition_feasibility_review_artifact_sha256": (
                acquisition_feasibility_review_artifact_sha256
            ),
        },
    }
    context_snapshot = _snapshot(context)
    blockers = []
    # The plan validator calculates exact blockers.  Seed the same readiness
    # payload via a temporary local derivation from nullable context/design.
    from host.extended_color.aggregation import measurement_context_blockers

    blockers.extend(measurement_context_blockers(context_snapshot))
    for field, value in design["aggregation"].items():
        if field in {
            "orientation_bias_max_delta_e00",
            "u95_max_delta_e00",
            "acceptance_span_delta_e00",
            "acceptance_review_artifact_sha256",
            "acquisition_feasibility_review_artifact_sha256",
        } and value is None:
            blockers.append(f"formal_palette.{field}_missing")
    return seal_measurement_plan(
        {
            "schema_version": AGGREGATION_SCHEMA_VERSION,
            "kind": PALETTE_PLAN_KIND,
            "plan_id": "n5-formal-palette-v1",
            "context": context_snapshot,
            "design": design,
            "required_samples_per_cell": 6,
            "expected_slots": slots,
            "readiness": {
                "measurement_ready": not blockers,
                "blockers": blockers,
            },
        }
    )


def build_formal_transition_plan(
    *,
    context: Mapping[str, Any],
    formal_repeat_routes: Sequence[Mapping[str, Any]],
    recovery_profile_canonical_sha256: Optional[str] = None,
    recovery_profile_review_artifact_sha256: Optional[str] = None,
) -> dict[str, Any]:
    """Seal the five-repeat/360-slot EC4 plan after route preregistration."""

    from host.extended_color.aggregation import measurement_context_blockers

    route_by_repeat = {
        route["formal_repeat"]: route for route in formal_repeat_routes
    }
    if set(route_by_repeat) != set(range(1, 6)) or len(formal_repeat_routes) != 5:
        raise N5CampaignError("formal transition plan requires five unique repeat routes")
    slots = []
    for repeat in range(1, 6):
        route = route_by_repeat[repeat]
        matrix = generate_transition_matrix_frames(repeat)
        for roi in matrix.rois:
            slots.append(
                {
                    "slot_id": f"formal-r{repeat}-{roi.roi_id}",
                    "controller": roi.controller,
                    "old_code": roi.old_code,
                    "new_code": roi.target_code,
                    "formal_repeat": repeat,
                    "roi": _roi_for_transition(roi.to_dict()),
                    "primer_action_identity_sha256": route[
                        "initial_action_identity_sha256"
                    ],
                    "target_action_identity_sha256": route[
                        "target_action_identity_sha256"
                    ],
                }
            )
    design = {
        "evidence_level": "formal-profile",
        "pilot_required": True,
        "pilot_repeats_per_pair": 2,
        "pilot_excluded_from_formal_n": True,
        "formal_repeats": 5,
        "rotation_algorithm": (
            "opposed-cyclic-old-and-target-orders-repetition-offset-v1"
        ),
        "recovery_actions_per_formal_repeat": 4,
        "recovery_sequence": [
            "solid-black",
            "solid-white",
            "solid-black",
            "solid-white",
        ],
        "recovery_profile_canonical_sha256": recovery_profile_canonical_sha256,
        "recovery_profile_review_artifact_sha256": (
            recovery_profile_review_artifact_sha256
        ),
    }
    context_snapshot = _snapshot(context)
    blockers = measurement_context_blockers(context_snapshot)
    for field in (
        "recovery_profile_canonical_sha256",
        "recovery_profile_review_artifact_sha256",
    ):
        if design[field] is None:
            blockers.append(f"formal_transition.{field}_missing")
    return seal_measurement_plan(
        {
            "schema_version": AGGREGATION_SCHEMA_VERSION,
            "kind": TRANSITION_FORMAL_PLAN_KIND,
            "plan_id": "n5-formal-transition-five-repeat-v1",
            "context": context_snapshot,
            "design": design,
            "required_samples_per_cell": 10,
            "expected_slots": slots,
            "readiness": {
                "measurement_ready": not blockers,
                "blockers": blockers,
            },
        }
    )


def seal_transition_recovery_profile(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Seal reviewed external evidence; this never qualifies a recovery by itself."""

    if not isinstance(payload, Mapping) or "integrity" in payload:
        raise N5CampaignError("transition recovery profile payload must omit integrity")
    unsigned = _snapshot(payload)
    profile = {
        **unsigned,
        "integrity": {
            "canonical_sha256": _sha256(unsigned),
            "canonical_sha256_scope": RECOVERY_PROFILE_HASH_SCOPE,
        },
    }
    validate_transition_recovery_profile(profile)
    return profile


def build_reviewed_transition_recovery_profile(
    *,
    panel: Mapping[str, Any],
    firmware: Mapping[str, Any],
    waveform_id: str,
    waveform_sha256: str,
    qualification_artifact_sha256: str,
    reviewer_id: str,
    reviewed_at: str,
    review_artifact_sha256: str,
    supplier_limit_profile_sha256: str,
    usage_limit_contract_sha256: str,
    temperature_chain_sha256: str,
) -> dict[str, Any]:
    """Build a profile only from caller-supplied reviewed evidence identities."""

    sequence = []
    for step, code in enumerate((0, 1, 0, 1), start=1):
        artifact = build_artifact(f"solid-{COLOR_NAME_BY_CODE[code]}")
        sequence.append(
            {
                "step": step,
                "code": code,
                "pattern": artifact.pattern,
                "frame": _frame_record(artifact.frame),
            }
        )
    return seal_transition_recovery_profile(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": RECOVERY_PROFILE_KIND,
            "profile_id": "n5-reviewed-bwbw-transition-recovery-v1",
            "panel": _snapshot(panel),
            "firmware": _snapshot(firmware),
            "waveform": {
                "waveform_id": waveform_id,
                "waveform_sha256": waveform_sha256,
            },
            "sequence": sequence,
            "qualification": {
                "qualified": True,
                "known_initial_codes": list(COLOR_ORDER),
                "all_known_initial_states_passed": True,
                "qualification_artifact_sha256": qualification_artifact_sha256,
                "reviewed": True,
                "reviewer_id": reviewer_id,
                "reviewed_at": reviewed_at,
                "review_artifact_sha256": review_artifact_sha256,
            },
            "safety": {
                "pof_required_after_each_step": True,
                "j2_remains_on_during_six_action_repeat": True,
                "manual_j2_cut_and_rail_release_required_after_target": True,
                "temperature_gate_required_before_each_step": True,
                "stop_on_any_abnormal_or_missing_evidence": True,
                "automatic_retry": False,
                "automatic_recovery": False,
                "supplier_limit_profile_sha256": supplier_limit_profile_sha256,
                "usage_limit_contract_sha256": usage_limit_contract_sha256,
                "temperature_chain_sha256": temperature_chain_sha256,
            },
        }
    )


def validate_transition_recovery_profile(
    profile: Mapping[str, Any],
) -> Mapping[str, Any]:
    keys = {
        "schema_version",
        "kind",
        "profile_id",
        "panel",
        "firmware",
        "waveform",
        "sequence",
        "qualification",
        "safety",
        "integrity",
    }
    if not isinstance(profile, Mapping) or set(profile) != keys:
        raise N5CampaignError("transition recovery profile keys changed")
    if profile["schema_version"] != SCHEMA_VERSION or profile["kind"] != RECOVERY_PROFILE_KIND:
        raise N5CampaignError("transition recovery profile schema or kind changed")
    if profile["profile_id"] != "n5-reviewed-bwbw-transition-recovery-v1":
        raise N5CampaignError("transition recovery profile_id changed")
    panel = profile["panel"]
    if (
        not isinstance(panel, Mapping)
        or set(panel) != {"model", "serial", "board_id", "pcb_revision"}
        or panel["model"] != "MF-17506-M009F-T"
        or not all(isinstance(value, str) and value for value in panel.values())
        or any(
            value.upper().startswith(("UNBOUND", "UNKNOWN", "TBD", "MISSING"))
            for value in panel.values()
        )
    ):
        raise N5CampaignError("transition recovery profile panel is not exactly bound")
    firmware = profile["firmware"]
    if not isinstance(firmware, Mapping) or set(firmware) != {
        "source_commit",
        "build_tag",
        "binary_sha256",
        "driver_api",
    }:
        raise N5CampaignError("transition recovery profile firmware keys changed")
    if (
        not isinstance(firmware["source_commit"], str)
        or re.fullmatch(r"[0-9a-f]{40}", firmware["source_commit"]) is None
        or firmware["source_commit"] == "0" * 40
        or not isinstance(firmware["build_tag"], str)
        or not firmware["build_tag"]
        or not isinstance(firmware["driver_api"], str)
        or not firmware["driver_api"]
    ):
        raise N5CampaignError("transition recovery profile firmware is not bound")
    _require_hash(firmware["binary_sha256"], label="recovery firmware binary")
    waveform = profile["waveform"]
    if (
        not isinstance(waveform, Mapping)
        or set(waveform) != {"waveform_id", "waveform_sha256"}
        or not isinstance(waveform["waveform_id"], str)
        or not waveform["waveform_id"]
    ):
        raise N5CampaignError("transition recovery waveform is not bound")
    _require_hash(waveform["waveform_sha256"], label="recovery waveform")
    expected_codes = (0, 1, 0, 1)
    sequence = profile["sequence"]
    if not isinstance(sequence, list) or len(sequence) != 4:
        raise N5CampaignError("transition recovery sequence must contain four steps")
    for index, (step, expected_code) in enumerate(zip(sequence, expected_codes), start=1):
        if not isinstance(step, Mapping) or set(step) != {
            "step",
            "code",
            "pattern",
            "frame",
        }:
            raise N5CampaignError("transition recovery step keys changed")
        expected_artifact = build_artifact(
            f"solid-{COLOR_NAME_BY_CODE[expected_code]}"
        )
        if step != {
            "step": index,
            "code": expected_code,
            "pattern": expected_artifact.pattern,
            "frame": _frame_record(expected_artifact.frame),
        }:
            raise N5CampaignError("transition recovery step/frame identity changed")
    qualification = profile["qualification"]
    if not isinstance(qualification, Mapping) or set(qualification) != {
        "qualified",
        "known_initial_codes",
        "all_known_initial_states_passed",
        "qualification_artifact_sha256",
        "reviewed",
        "reviewer_id",
        "reviewed_at",
        "review_artifact_sha256",
    }:
        raise N5CampaignError("transition recovery qualification keys changed")
    if (
        qualification["qualified"] is not True
        or qualification["known_initial_codes"] != list(COLOR_ORDER)
        or qualification["all_known_initial_states_passed"] is not True
        or qualification["reviewed"] is not True
        or not isinstance(qualification["reviewer_id"], str)
        or not qualification["reviewer_id"]
        or not isinstance(qualification["reviewed_at"], str)
        or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
            qualification["reviewed_at"],
        )
        is None
    ):
        raise N5CampaignError("transition recovery qualification is incomplete")
    for field in ("qualification_artifact_sha256", "review_artifact_sha256"):
        _require_hash(qualification[field], label=f"recovery qualification.{field}")
    safety = profile["safety"]
    if not isinstance(safety, Mapping) or set(safety) != {
        "pof_required_after_each_step",
        "j2_remains_on_during_six_action_repeat",
        "manual_j2_cut_and_rail_release_required_after_target",
        "temperature_gate_required_before_each_step",
        "stop_on_any_abnormal_or_missing_evidence",
        "automatic_retry",
        "automatic_recovery",
        "supplier_limit_profile_sha256",
        "usage_limit_contract_sha256",
        "temperature_chain_sha256",
    }:
        raise N5CampaignError("transition recovery safety keys changed")
    if any(
        safety[field] is not True
        for field in (
            "pof_required_after_each_step",
            "j2_remains_on_during_six_action_repeat",
            "manual_j2_cut_and_rail_release_required_after_target",
            "temperature_gate_required_before_each_step",
            "stop_on_any_abnormal_or_missing_evidence",
        )
    ) or safety["automatic_retry"] is not False or safety[
        "automatic_recovery"
    ] is not False:
        raise N5CampaignError("transition recovery safety gates changed")
    for field in (
        "supplier_limit_profile_sha256",
        "usage_limit_contract_sha256",
        "temperature_chain_sha256",
    ):
        _require_hash(safety[field], label=f"transition recovery safety.{field}")
    unsigned = dict(profile)
    integrity = unsigned.pop("integrity")
    if integrity != {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": RECOVERY_PROFILE_HASH_SCOPE,
    }:
        raise N5CampaignError("transition recovery profile integrity is invalid")
    return profile


def formal_transition_template() -> dict[str, Any]:
    repetitions = []
    for repeat in range(1, 6):
        matrix = generate_transition_matrix_frames(repeat)
        repetitions.append(
            {
                "formal_repeat": repeat,
                "old_order": list(matrix.old_order),
                "target_order": list(matrix.target_order),
                "initial_frame": _frame_record(matrix.initial),
                "target_frame": _frame_record(matrix.target),
                "actions": [
                    "recovery-solid-black",
                    "recovery-solid-white",
                    "recovery-solid-black",
                    "recovery-solid-white",
                    "transition-initial",
                    "transition-target",
                ],
                "raw_measurement_slots": 72,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-n5-formal-transition-template",
        "formal_plan_kind": TRANSITION_FORMAL_PLAN_KIND,
        "evidence_level": "formal-profile-after-all-gates-only",
        "pilot_repeats_per_pair": 2,
        "pilot_raw_slots": 144,
        "pilot_actions": 12,
        "pilot_excluded_from_formal_n": True,
        "formal_repeats": 5,
        "actions_per_formal_repeat": 6,
        "formal_actions": 30,
        "formal_raw_slots": 360,
        "profile_cells": 36,
        "profile_samples_per_cell": 5,
        "rotation_algorithm": (
            "opposed-cyclic-old-and-target-orders-repetition-offset-v1"
        ),
        "recovery_candidate_sequence": [
            "solid-black",
            "solid-white",
            "solid-black",
            "solid-white",
        ],
        "recovery_is_qualified": False,
        "p0_materialized": False,
        "materialized_sessions": 0,
        "materialized_actions": 0,
        "blockers": [
            "reviewed_recovery_profile_missing",
            "recovery_profile_not_qualified_for_each_known_initial_state",
            "reviewed_panel_cold_or_recovery_step_power_profile_missing",
            "supplier_limits_usage_temperature_chain_not_bound",
            "exact_per_action_authorizations_not_created",
        ],
        "repetitions": repetitions,
    }


def _formal_palette_template() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-n5-formal-palette-template",
        "calibrated_palette_eligible": True,
        "sequence": [
            "vertical-pilot",
            "horizontal-pilot",
            "vertical-formal-01",
            "horizontal-formal-01",
            "vertical-formal-02",
            "horizontal-formal-02",
            "vertical-formal-03",
            "horizontal-formal-03",
        ],
        "pilot_actions": 2,
        "pilot_excluded_from_formal_n": True,
        "formal_actions": 6,
        "formal_runs_per_orientation": 3,
        "acquisition_window": {
            "anchor": "POF_BUSY_N_low_to_high",
            "minimum_seconds": 55.0,
            "maximum_seconds": 65.0,
        },
        "measurement_code_order": list(PALETTE_CODE_ORDER),
        "controller_assignment_rationale": (
            "global-v-bars contains each colour on only one controller; horizontal "
            "sampling uses the opposite controller, yielding CS1=3 and CS2=3 per code"
        ),
        "formal_logical_strata": 36,
        "formal_raw_observations": 36,
        "fixture_identities": {
            "vertical": _frame_record(generate_fixture("global-v-bars")),
            "horizontal": _frame_record(generate_fixture("global-h-bars")),
        },
        "formal_plan_materialization_requires": [
            "reviewed_panel_cold_profile",
            "bound_panel_and_firmware",
            "authoritative_external_CIE_D65_and_1931_2deg_tables",
            "qualified_45_0_spectral_instrument",
            "waveform_and_environment",
            "pixel_pitch_and_aperture_fit_reviews",
            "reviewed_orientation_bias_U95_and_acceptance_span_limits",
            "six_measurements_feasible_inside_55_to_65_second_window",
        ],
    }


def _append_formal_palette_actions(
    *,
    campaign_id: str,
    actions: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    cold_profile: Mapping[str, Any],
    map_frame: Mapping[str, Any],
) -> list[dict[str, Any]]:
    profile = _validate_session_profile(cold_profile)
    if profile["power_mode"] != "panel_cold_cycle":
        raise N5CampaignError("formal palette actions require reviewed panel-cold profile")
    frames = {
        "vertical": _frame_record(generate_fixture("global-v-bars")),
        "horizontal": _frame_record(generate_fixture("global-h-bars")),
    }
    sequence = [
        ("vertical", "pilot", 0),
        ("horizontal", "pilot", 0),
        ("vertical", "formal", 1),
        ("horizontal", "formal", 1),
        ("vertical", "formal", 2),
        ("horizontal", "formal", 2),
        ("vertical", "formal", 3),
        ("horizontal", "formal", 3),
    ]
    prior_identity: Optional[str] = None
    routes: list[dict[str, Any]] = []
    for index, (orientation, role, run_number) in enumerate(sequence):
        suffix = "pilot" if role == "pilot" else f"formal-{run_number:02d}"
        session_id = f"n5-palette-{orientation}-{suffix}-session"
        cell_id = f"n5-palette-{orientation}-{suffix}"
        session_action_identities = []
        if index == 0:
            primer = build_fixed_action_declaration(
                campaign_id=campaign_id,
                session_id=session_id,
                cell_id=cell_id,
                action_id="n5-palette-initial-map-primer",
                phase="known-map-primer",
                frame=map_frame,
            )
            actions.append(primer)
            session_action_identities.append(primer["action_identity_sha256"])
            prior_identity = primer["action_identity_sha256"]
        assert prior_identity is not None
        target = build_fixed_action_declaration(
            campaign_id=campaign_id,
            session_id=session_id,
            cell_id=cell_id,
            action_id=f"n5-palette-{orientation}-{suffix}",
            phase=f"palette-{role}",
            frame=frames[orientation],
            prior_action_identity_sha256=prior_identity,
            prior_scope="same_cell" if index == 0 else "campaign",
        )
        actions.append(target)
        session_action_identities.append(target["action_identity_sha256"])
        sessions.append(
            build_session_contract(
                session_id=session_id,
                cell_id=cell_id,
                power_mode="panel_cold_cycle",
                planned_cooldown_seconds=0,
                final_power_off_required=False,
                action_identity_sha256s=session_action_identities,
                minimum_panel_power_off_seconds=profile[
                    "minimum_panel_power_off_seconds"
                ],
            )
        )
        if role == "formal":
            routes.append(
                {
                    "orientation": orientation,
                    "formal_run": run_number,
                    "primer_action_identity_sha256": prior_identity,
                    "target_action_identity_sha256": target[
                        "action_identity_sha256"
                    ],
                }
            )
        prior_identity = target["action_identity_sha256"]
    return routes


def _append_formal_transition_actions(
    *,
    campaign_id: str,
    actions: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    recovery_profile: Mapping[str, Any],
    power_profile: Mapping[str, Any],
    panel: Mapping[str, Any],
    firmware: Mapping[str, Any],
    first_prior_action_identity_sha256: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    recovery = validate_transition_recovery_profile(recovery_profile)
    power = _validate_session_profile(power_profile)
    if power["power_mode"] != "panel_cold_cycle":
        raise N5CampaignError("formal transition requires reviewed panel-cold power profile")
    if recovery["panel"] != panel or recovery["firmware"] != firmware:
        raise N5CampaignError("formal transition recovery panel/firmware differs from shared P0")
    prior_identity = _require_hash(
        first_prior_action_identity_sha256,
        label="formal transition initial known prior",
    )
    routes: list[dict[str, Any]] = []
    formal_routes: list[dict[str, Any]] = []
    session_count_before = len(sessions)
    run_specs = [
        *(('pilot', repeat) for repeat in range(1, 3)),
        *(('formal', repeat) for repeat in range(1, 6)),
    ]
    for role, repeat in run_specs:
        matrix = generate_transition_matrix_frames(repeat)
        session_id = f"n5-transition-{role}-r{repeat}-session"
        cell_id = f"n5-transition-{role}-r{repeat}"
        phase_frames = [
            *(
                (f"recovery-{step['step']}", step["frame"])
                for step in recovery["sequence"]
            ),
            ("initial", _frame_record(matrix.initial)),
            ("target", _frame_record(matrix.target)),
        ]
        route_actions = []
        session_action_identities = []
        initial_identity: Optional[str] = None
        target_identity: Optional[str] = None
        for sequence_index, (phase_name, frame) in enumerate(phase_frames, start=1):
            action = build_fixed_action_declaration(
                campaign_id=campaign_id,
                session_id=session_id,
                cell_id=cell_id,
                action_id=f"n5-transition-{role}-r{repeat}-{phase_name}",
                phase=f"transition-{role}-{phase_name}",
                frame=frame,
                prior_action_identity_sha256=prior_identity,
                prior_scope="campaign" if sequence_index == 1 else "same_cell",
            )
            actions.append(action)
            session_action_identities.append(action["action_identity_sha256"])
            route_actions.append(
                {
                    "sequence_index": sequence_index,
                    "phase": phase_name,
                    "action_identity_sha256": action["action_identity_sha256"],
                    "immediate_prior_action_identity_sha256": prior_identity,
                    "required_prior_result_state": "PASS",
                    "required_prior_result_whole_file_sha256_at_runtime": True,
                    "missing_or_nonpass_prior_action": "STOP_NO_RETRY_NO_RECOVERY",
                }
            )
            prior_identity = action["action_identity_sha256"]
            if phase_name == "initial":
                initial_identity = prior_identity
            elif phase_name == "target":
                target_identity = prior_identity
        sessions.append(
            build_session_contract(
                session_id=session_id,
                cell_id=cell_id,
                power_mode="panel_cold_cycle",
                planned_cooldown_seconds=0,
                final_power_off_required=True,
                action_identity_sha256s=session_action_identities,
                minimum_panel_power_off_seconds=power[
                    "minimum_panel_power_off_seconds"
                ],
            )
        )
        assert initial_identity is not None and target_identity is not None
        route = {
            "role": role,
            "repeat": repeat,
            "recovery_profile_canonical_sha256": recovery["integrity"][
                "canonical_sha256"
            ],
            "power_profile_review_artifact_sha256": power[
                "review_artifact_sha256"
            ],
            "action_count": 6,
            "actions": route_actions,
            "power_semantics": {
                "reviewed_panel_cold_start_once_before_repeat": True,
                "j2_remains_on_within_six_action_chain": True,
                "manual_j2_cut_after_target_required": True,
            },
            "abnormal_stop_contract": {
                "stop_on_any_nonpass_or_missing_whole_file_result": True,
                "automatic_advance": False,
                "automatic_retry": False,
                "automatic_recovery": False,
                "remaining_actions_become_ineligible": True,
            },
        }
        routes.append(route)
        if role == "formal":
            formal_routes.append(
                {
                    "formal_repeat": repeat,
                    "initial_action_identity_sha256": initial_identity,
                    "target_action_identity_sha256": target_identity,
                }
            )
    if (
        len(routes) != 7
        or len(sessions) - session_count_before != 7
        or sum(route["action_count"] for route in routes) != 42
    ):
        raise N5CampaignError("formal transition materializer count changed")
    return routes, formal_routes


def compile_campaign_manifest(
    *,
    panel: Mapping[str, Any] = DEFAULT_PANEL,
    firmware: Mapping[str, Any] = DEFAULT_FIRMWARE,
    formal_palette_cold_profile: Optional[Mapping[str, Any]] = None,
    formal_transition_recovery_profile: Optional[Mapping[str, Any]] = None,
    formal_transition_power_profile: Optional[Mapping[str, Any]] = None,
    waveform_id: Optional[str] = None,
    waveform_sha256: Optional[str] = None,
    temperature_c: Optional[float] = None,
    relative_humidity_percent: Optional[float] = None,
    environment_record_sha256: Optional[str] = None,
    standard_table_canonical_sha256: Optional[str] = None,
    instrument_qualification_canonical_sha256: Optional[str] = None,
    pixel_pitch_review_artifact_sha256: Optional[str] = None,
    roi_aperture_fit_review_artifact_sha256: Optional[str] = None,
    orientation_bias_max_delta_e00: Optional[float] = None,
    u95_max_delta_e00: Optional[float] = None,
    acceptance_span_delta_e00: Optional[float] = None,
    acceptance_review_artifact_sha256: Optional[str] = None,
    acquisition_feasibility_review_artifact_sha256: Optional[str] = None,
) -> dict[str, Any]:
    """Compile data only.  No claim or runtime authorization is created."""

    atlas = _snapshot(build_atlas())
    map_frame = _frame_record(generate_fixture("map-orient-v1"))
    actions: list[dict[str, Any]] = []
    sessions: list[dict[str, Any]] = []
    routes: dict[str, Any] = {}
    ordinary = ordinary_session_profile()
    descriptive_asset_ids = [
        *(f"n5-solid-code-{code}" for code in COLOR_ORDER),
        "n5-mix-atlas-1",
        "n5-mix-atlas-2",
        "n5-mix-atlas-3",
        "n5-optical-edge-kernel-atlas",
    ]
    for asset_id in descriptive_asset_ids:
        asset = _atlas_asset(atlas, asset_id)
        cell_id = asset_id.replace("_", "-")
        pair_actions, session, route = _build_pair(
            campaign_id=CAMPAIGN_ID,
            session_id=f"{cell_id}-session",
            cell_id=cell_id,
            map_frame=map_frame,
            target_frame=asset["frame"],
            session_profile=ordinary,
        )
        actions.extend(pair_actions)
        sessions.append(session)
        routes[asset_id] = route
    transition_actions, transition_session, transition_route = _build_transition_pair(
        campaign_id=CAMPAIGN_ID,
        initial_frame=_atlas_asset(atlas, "n5-transition-initial-r1")["frame"],
        target_frame=_atlas_asset(atlas, "n5-transition-target-r1")["frame"],
    )
    actions.extend(transition_actions)
    sessions.append(transition_session)
    routes["n5-transition-descriptive-r1"] = transition_route

    transition_requested = (
        formal_transition_recovery_profile is not None
        or formal_transition_power_profile is not None
    )
    if transition_requested and (
        formal_transition_recovery_profile is None
        or formal_transition_power_profile is None
    ):
        raise N5CampaignError(
            "formal transition materialization requires both recovery and power profiles"
        )
    if formal_transition_recovery_profile is not None:
        recovery_root = validate_transition_recovery_profile(
            formal_transition_recovery_profile
        )
        if waveform_id is None:
            waveform_id = recovery_root["waveform"]["waveform_id"]
        if waveform_sha256 is None:
            waveform_sha256 = recovery_root["waveform"]["waveform_sha256"]
        if (
            waveform_id != recovery_root["waveform"]["waveform_id"]
            or waveform_sha256 != recovery_root["waveform"]["waveform_sha256"]
        ):
            raise N5CampaignError(
                "formal transition waveform differs from reviewed recovery profile"
            )
    context = _measurement_context(
        panel=panel,
        firmware=firmware,
        waveform_id=waveform_id,
        waveform_sha256=waveform_sha256,
        temperature_c=temperature_c,
        relative_humidity_percent=relative_humidity_percent,
        environment_record_sha256=environment_record_sha256,
        standard_table_canonical_sha256=standard_table_canonical_sha256,
        instrument_qualification_canonical_sha256=(
            instrument_qualification_canonical_sha256
        ),
        pixel_pitch_review_artifact_sha256=pixel_pitch_review_artifact_sha256,
        roi_aperture_fit_review_artifact_sha256=(
            roi_aperture_fit_review_artifact_sha256
        ),
    )
    descriptive_transition_plan = build_descriptive_transition_plan(
        context=context, route=transition_route
    )
    formal_palette_routes: list[dict[str, Any]] = []
    formal_palette_plan = None
    if formal_palette_cold_profile is not None:
        formal_palette_routes = _append_formal_palette_actions(
            campaign_id=CAMPAIGN_ID,
            actions=actions,
            sessions=sessions,
            cold_profile=formal_palette_cold_profile,
            map_frame=map_frame,
        )
        formal_palette_plan = build_formal_palette_plan(
            context=context,
            formal_routes=formal_palette_routes,
            orientation_bias_max_delta_e00=orientation_bias_max_delta_e00,
            u95_max_delta_e00=u95_max_delta_e00,
            acceptance_span_delta_e00=acceptance_span_delta_e00,
            acceptance_review_artifact_sha256=acceptance_review_artifact_sha256,
            acquisition_feasibility_review_artifact_sha256=(
                acquisition_feasibility_review_artifact_sha256
            ),
        )
    formal_transition_routes: list[dict[str, Any]] = []
    formal_transition_plan = None
    if formal_transition_recovery_profile is not None:
        assert formal_transition_power_profile is not None
        formal_transition_routes, formal_repeat_routes = (
            _append_formal_transition_actions(
                campaign_id=CAMPAIGN_ID,
                actions=actions,
                sessions=sessions,
                recovery_profile=formal_transition_recovery_profile,
                power_profile=formal_transition_power_profile,
                panel=panel,
                firmware=firmware,
                first_prior_action_identity_sha256=actions[-1][
                    "action_identity_sha256"
                ],
            )
        )
        formal_transition_plan = build_formal_transition_plan(
            context=context,
            formal_repeat_routes=formal_repeat_routes,
            recovery_profile_canonical_sha256=formal_transition_recovery_profile[
                "integrity"
            ]["canonical_sha256"],
            recovery_profile_review_artifact_sha256=formal_transition_recovery_profile[
                "qualification"
            ]["review_artifact_sha256"],
        )
    p0 = seal_campaign_contract(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": "mf1750-visible-refresh-campaign-contract",
            "campaign_id": CAMPAIGN_ID,
            "panel": _snapshot(panel),
            "firmware": _snapshot(firmware),
            "actions": actions,
            "sessions": sessions,
            "classification": {
                "offline_compiled": True,
                "hardware_execution_authorized": False,
                "automatic_execution": False,
                "automatic_retry": False,
                "automatic_recovery": False,
                "network_io_performed": False,
                "device_io_performed": False,
            },
        }
    )
    missing_hardware = [
        "physical_panel_serial_not_bound",
        "reviewed_supplier_limit_profile_missing",
        "usage_counters_not_bound",
        "temperature_measurement_chain_not_bound",
        "authoritative_external_CIE_tables_not_bound",
        "qualified_45_0_spectral_instrument_not_bound",
        "waveform_environment_and_aperture_context_not_complete",
        "runtime_preflight_and_exact_authorizations_not_created",
    ]
    transition_template = formal_transition_template()
    if formal_transition_plan is not None:
        transition_template.update(
            {
                "p0_materialized": True,
                "recovery_is_qualified": True,
                "materialized_sessions": 7,
                "materialized_actions": 42,
                "blockers": [
                    "optical_measurement_context_may_remain_incomplete",
                    "runtime_preflight_and_exact_per_action_authorizations_not_created",
                ],
            }
        )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "campaign_id": CAMPAIGN_ID,
        "atlas": atlas,
        "measurement_modalities": {
            "spectral_palette": {
                "result_illuminant": "computational CIE D65",
                "observer": "CIE 1931 2deg",
                "geometry": "45/0",
                "external_5000K_RAW_lighting_required": False,
            },
            "camera_spatial": {
                "purpose": "uniformity, edge, ESF/PSF, and spatial fidelity only",
                "RAW_required": True,
                "external_lighting_cct_kelvin": {"target": 5000, "tolerance": 100},
                "may_create_calibrated_palette": False,
            },
        },
        "session_profiles": {
            "ordinary": ordinary,
            "formal_palette_cold": (
                None
                if formal_palette_cold_profile is None
                else _snapshot(formal_palette_cold_profile)
            ),
        },
        "shared_p0": p0,
        "routes": routes,
        "descriptive_transition_plan": descriptive_transition_plan,
        "formal_palette_template": _formal_palette_template(),
        "formal_palette_routes": formal_palette_routes,
        "formal_palette_plan": formal_palette_plan,
        "formal_transition_recovery_profile": (
            None
            if formal_transition_recovery_profile is None
            else _snapshot(formal_transition_recovery_profile)
        ),
        "formal_transition_power_profile": (
            None
            if formal_transition_power_profile is None
            else _snapshot(formal_transition_power_profile)
        ),
        "formal_transition_routes": formal_transition_routes,
        "formal_transition_plan": formal_transition_plan,
        "formal_transition_template": transition_template,
        "counts": {
            "declared_sessions": len(sessions),
            "declared_actions": len(actions),
            "default_descriptive_sessions": 11,
            "default_descriptive_actions": 22,
            "formal_palette_additional_sessions": 8,
            "formal_palette_additional_actions": 9,
            "formal_transition_actions_after_recovery_qualification": 30,
            "formal_transition_pilot_actions": 12,
            "formal_transition_additional_sessions": 7,
            "formal_transition_additional_actions": 42,
        },
        "readiness": {
            "software_compiler_ready": True,
            "hardware_ready": False,
            "blockers": missing_hardware,
        },
        "classification": {
            "offline_compiled": True,
            "descriptive_atlas_ready": True,
            "calibrated_palette_created": False,
            "measured_transition_profile_created": False,
            "hardware_execution_authorized": False,
            "authorization_created": False,
            "claim_created": False,
            "real_executor_present": False,
            "unknown_code_relaxation": False,
            "network_io_performed": False,
            "device_io_performed": False,
            "automatic_retry": False,
            "automatic_recovery": False,
        },
    }
    manifest = {
        **unsigned,
        "integrity": {
            "canonical_sha256": _sha256(unsigned),
            "canonical_sha256_scope": HASH_SCOPE,
        },
    }
    validate_compiled_manifest(manifest)
    return manifest


def validate_compiled_manifest(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    required = {
        "schema_version",
        "kind",
        "campaign_id",
        "atlas",
        "measurement_modalities",
        "session_profiles",
        "shared_p0",
        "routes",
        "descriptive_transition_plan",
        "formal_palette_template",
        "formal_palette_routes",
        "formal_palette_plan",
        "formal_transition_recovery_profile",
        "formal_transition_power_profile",
        "formal_transition_routes",
        "formal_transition_plan",
        "formal_transition_template",
        "counts",
        "readiness",
        "classification",
        "integrity",
    }
    if not isinstance(manifest, Mapping) or set(manifest) != required:
        raise N5CampaignError("N5 manifest top-level keys changed")
    if manifest["schema_version"] != SCHEMA_VERSION or manifest["kind"] != KIND:
        raise N5CampaignError("N5 manifest schema or kind changed")
    if manifest["campaign_id"] != CAMPAIGN_ID:
        raise N5CampaignError("N5 campaign_id changed")
    validate_campaign_contract(manifest["shared_p0"])
    validate_measurement_plan(manifest["descriptive_transition_plan"])
    if manifest["descriptive_transition_plan"]["kind"] != TRANSITION_PLAN_KIND:
        raise N5CampaignError("descriptive transition plan kind changed")
    if manifest["formal_palette_plan"] is not None:
        validate_measurement_plan(manifest["formal_palette_plan"])
        if manifest["formal_palette_plan"]["kind"] != PALETTE_PLAN_KIND:
            raise N5CampaignError("formal palette plan kind changed")
    transition_materialized = manifest["formal_transition_plan"] is not None
    if transition_materialized:
        validate_transition_recovery_profile(
            manifest["formal_transition_recovery_profile"]
        )
        _validate_session_profile(manifest["formal_transition_power_profile"])
        validate_measurement_plan(manifest["formal_transition_plan"])
        if manifest["formal_transition_plan"]["kind"] != TRANSITION_FORMAL_PLAN_KIND:
            raise N5CampaignError("formal transition plan kind changed")
        routes = manifest["formal_transition_routes"]
        if (
            not isinstance(routes, list)
            or len(routes) != 7
            or sum(route.get("action_count", 0) for route in routes) != 42
            or sum(route["role"] == "pilot" for route in routes) != 2
            or sum(route["role"] == "formal" for route in routes) != 5
        ):
            raise N5CampaignError("formal transition route count changed")
        for route in routes:
            if route["power_semantics"] != {
                "reviewed_panel_cold_start_once_before_repeat": True,
                "j2_remains_on_within_six_action_chain": True,
                "manual_j2_cut_after_target_required": True,
            }:
                raise N5CampaignError("formal transition intra-repeat power semantics changed")
            if route["abnormal_stop_contract"] != {
                "stop_on_any_nonpass_or_missing_whole_file_result": True,
                "automatic_advance": False,
                "automatic_retry": False,
                "automatic_recovery": False,
                "remaining_actions_become_ineligible": True,
            }:
                raise N5CampaignError("formal transition abnormal-stop contract changed")
            route_actions = route["actions"]
            if len(route_actions) != 6:
                raise N5CampaignError("formal transition repeat must contain six actions")
            for index, action in enumerate(route_actions):
                if (
                    action["sequence_index"] != index + 1
                    or action["required_prior_result_state"] != "PASS"
                    or action["required_prior_result_whole_file_sha256_at_runtime"]
                    is not True
                    or action["missing_or_nonpass_prior_action"]
                    != "STOP_NO_RETRY_NO_RECOVERY"
                    or (
                        index > 0
                        and action["immediate_prior_action_identity_sha256"]
                        != route_actions[index - 1]["action_identity_sha256"]
                    )
                ):
                    raise N5CampaignError(
                        "formal transition result dependency is not adjacent/fail-closed"
                    )
    elif any(
        manifest[field] is not None and manifest[field] != []
        for field in (
            "formal_transition_recovery_profile",
            "formal_transition_power_profile",
            "formal_transition_routes",
        )
    ):
        raise N5CampaignError("partial formal transition materialization is invalid")
    p0 = manifest["shared_p0"]
    counts = manifest["counts"]
    if (
        counts["declared_sessions"] != len(p0["sessions"])
        or counts["declared_actions"] != len(p0["actions"])
        or counts["default_descriptive_sessions"] != 11
        or counts["default_descriptive_actions"] != 22
        or counts["formal_palette_additional_sessions"] != 8
        or counts["formal_palette_additional_actions"] != 9
        or counts["formal_transition_actions_after_recovery_qualification"] != 30
        or counts["formal_transition_pilot_actions"] != 12
        or counts["formal_transition_additional_sessions"] != 7
        or counts["formal_transition_additional_actions"] != 42
    ):
        raise N5CampaignError("N5 session/action counts changed")
    formal_materialized = manifest["formal_palette_plan"] is not None
    expected_sessions = 11 + (8 if formal_materialized else 0) + (
        7 if transition_materialized else 0
    )
    expected_actions = 22 + (9 if formal_materialized else 0) + (
        42 if transition_materialized else 0
    )
    if len(p0["sessions"]) != expected_sessions or len(p0["actions"]) != expected_actions:
        raise N5CampaignError("N5 P0 count differs from materialization state")
    if manifest["atlas"] != build_atlas():
        raise N5CampaignError("N5 deterministic atlas changed or was tampered")
    for asset in manifest["atlas"]["assets"]:
        if set(asset["physical_code_histogram"]) != {
            str(code) for code in COLOR_ORDER
        } or sum(asset["physical_code_histogram"].values()) != WIDTH * HEIGHT:
            raise N5CampaignError("N5 atlas histogram is invalid")
        if any(
            roi.get("pixel_roi", roi.get("imaging_roi", roi.get("measurement", {}))).get(
                "x0", 0
            )
            < WIDTH // 2
            < roi.get(
                "pixel_roi", roi.get("imaging_roi", roi.get("measurement", {}))
            ).get("x1", 0)
            for roi in asset["rois"]
        ):
            raise N5CampaignError("N5 atlas ROI crosses the controller seam")
    if manifest["atlas"]["mix_contract"]["measurement_ready"] is not False:
        raise N5CampaignError("unbound pixel ROI was promoted to measurement-ready")
    if manifest["atlas"]["kernel_contract"] != {
        "asset_type": "camera-imaging-ESF-PSF",
        "single_point_lab_is_kernel": False,
        "measurement_ready": False,
        "blockers": [
            "pixel_pitch_not_bound",
            "camera_MTF_ESF_PSF_analysis_contract_not_reviewed",
            "external_RAW_spatial_illumination_not_bound",
        ],
    }:
        raise N5CampaignError("N5 optical-kernel semantics changed")
    expected_classification = {
        "offline_compiled": True,
        "descriptive_atlas_ready": True,
        "calibrated_palette_created": False,
        "measured_transition_profile_created": False,
        "hardware_execution_authorized": False,
        "authorization_created": False,
        "claim_created": False,
        "real_executor_present": False,
        "unknown_code_relaxation": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "automatic_retry": False,
        "automatic_recovery": False,
    }
    if manifest["classification"] != expected_classification:
        raise N5CampaignError("N5 fail-closed classification changed")
    if manifest["readiness"]["hardware_ready"] is not False:
        raise N5CampaignError("N5 compiler cannot claim hardware readiness")
    transition_template = manifest["formal_transition_template"]
    if transition_template["p0_materialized"] != transition_materialized:
        raise N5CampaignError("formal transition template/materialization state differs")
    if transition_template["materialized_actions"] != (
        42 if transition_materialized else 0
    ) or transition_template["materialized_sessions"] != (
        7 if transition_materialized else 0
    ):
        raise N5CampaignError("formal transition materialized counts changed")
    unsigned = dict(manifest)
    integrity = unsigned.pop("integrity")
    if integrity != {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": HASH_SCOPE,
    }:
        raise N5CampaignError("N5 manifest canonical integrity is invalid")
    return manifest


def manifest_file_sha256(manifest: Mapping[str, Any]) -> str:
    validate_compiled_manifest(manifest)
    return _sha256(manifest)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    compile_parser = subparsers.add_parser(
        "compile", help="compile one reviewed 73-action production manifest"
    )
    compile_parser.add_argument("--profile", type=Path, required=True)
    compile_parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    selected = list(sys.argv[1:] if argv is None else argv)
    if not selected:
        manifest = compile_campaign_manifest()
        print(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
        return 0
    args = parse_args(selected)
    try:
        result = compile_manifest_file(args.profile, args.output)
    except N5CampaignError as error:
        print(str(error), file=sys.stderr)
        return 2
    summary = {key: value for key, value in result.items() if key != "manifest"}
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CAMPAIGN_ID",
    "COMPILE_PROFILE_HASH_SCOPE",
    "COMPILE_PROFILE_KIND",
    "DEFAULT_FIRMWARE",
    "DEFAULT_PANEL",
    "EXPECTED_DEFAULT_MANIFEST_CANONICAL_SHA256",
    "EXPECTED_DEFAULT_MANIFEST_FILE_SHA256",
    "KIND",
    "N5CampaignError",
    "build_atlas",
    "build_descriptive_transition_plan",
    "build_formal_palette_plan",
    "build_formal_transition_plan",
    "build_reviewed_transition_recovery_profile",
    "compile_manifest_file",
    "compile_manifest_from_profile",
    "compile_campaign_manifest",
    "formal_transition_template",
    "manifest_file_sha256",
    "ordinary_session_profile",
    "reviewed_panel_cold_profile",
    "seal_compile_profile",
    "seal_transition_recovery_profile",
    "validate_compiled_manifest",
    "validate_compile_profile",
    "validate_transition_recovery_profile",
]
