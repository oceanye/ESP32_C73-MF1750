#!/usr/bin/env python3
"""Capture and seal the daylight W3-white + three-frame T3 camera pack.

Importing this module is offline-only.  Only ``setup-view`` and ``acquire`` open
a camera.  ``setup-view`` has its own two-attempt, non-formal ledger and can
only support a human framing/lighting check.  ``acquire`` permanently consumes
one formal attempt before opening the camera and seals the JPEG, sidecar, and
action snapshot without accepting the frame.
``admit`` is a separate offline-only command: after an operator has inspected
that exact JPEG it binds explicit TL,TR,BR,BL corners, performs the 64-cell,
illumination, alignment, and drift gates, and writes the terminal result.

The former one-phase ``capture`` command is deliberately disabled.  It required
the current frame's corners before the frame existed and therefore could not
truthfully meet the per-frame-corner evidence contract.  Neither two-phase
command exposes a camera index, instance, or settings override: the exact
DirectShow 48MP device and fixed profile from ``README camera.md`` remain
enforced by :mod:`mf1750_camera_capture_evidence`.

This core pack ends after W3 white + three T3 frames.  Its successful seal
unlocks the separately authorized W4 factory-white containment action.  The
optional post-W4 white photograph is an independent fifth frame, not part of
this four-frame bundle, and camera classification never blocks safe W4 white
containment.

One ``acquire`` invocation performs at most one acquisition.  A permanent
O_EXCL claim is written before it, so a failed acquisition consumes one of the
small frozen attempt budgets and is never retried automatically.  One
successful acquisition may be submitted to ``admit`` exactly once.  Its O_EXCL
admission claim is written before corner parsing or image analysis, so neither
invalid corners nor a failed gate can be silently corrected by retry/fallback.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import statistics
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_camera_capture_evidence as camera  # noqa: E402
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_position_balanced_photo_analyzer as geometry,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_profile_following_human_observation as human,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t3_ac_profile_following_successor_pack as t3_pack,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t3_ac_profile_following_successor_v2_pack as t3_v2_pack,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w3_discovery_successor_v2_white_pack as w3_pack,
)
from tools import mf1750_raw_p16_retained_atlas_photo_analyzer as frozen  # noqa: E402


SCHEMA_VERSION = 2
CONTRACT_KIND = "mf1750-raw-p16-crossover-t3-camera-capture-contract-v2"
CLAIM_KIND = "mf1750-raw-p16-crossover-t3-camera-capture-claim-v2"
ACQUISITION_KIND = "mf1750-raw-p16-crossover-t3-camera-acquisition-v2"
ADMISSION_KIND = "mf1750-raw-p16-crossover-t3-camera-admission-claim-v2"
RESULT_KIND = "mf1750-raw-p16-crossover-t3-camera-capture-result-v2"
BUNDLE_KIND = "mf1750-raw-p16-crossover-t3-camera-capture-bundle-v2"
SETUP_CONTRACT_KIND = "mf1750-raw-p16-crossover-t3-camera-setup-contract-v1"
SETUP_CLAIM_KIND = "mf1750-raw-p16-crossover-t3-camera-setup-claim-v1"
SETUP_RESULT_KIND = "mf1750-raw-p16-crossover-t3-camera-setup-result-v1"
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
PACK_REVISION = "w3-white-one-plus-t3-retained-three-exp6-two-phase-v2"

# The partial path is deliberately a separate evidence family.  None of these
# identifiers are aliases for the full-panel v2 kinds above: a partial result
# must never validate as, or be promoted to, legacy full-panel evidence.
PARTIAL_MODE = "PARTIAL_DUAL_3X8_TOP_ROWS_V1"
PARTIAL_CONTRACT_KIND = (
    "mf1750-raw-p16-crossover-t3-camera-partial-dual-3x8-contract-v1"
)
PARTIAL_CLAIM_KIND = (
    "mf1750-raw-p16-crossover-t3-camera-partial-dual-3x8-claim-v1"
)
PARTIAL_ACQUISITION_KIND = (
    "mf1750-raw-p16-crossover-t3-camera-partial-dual-3x8-acquisition-v1"
)
PARTIAL_ADMISSION_KIND = (
    "mf1750-raw-p16-crossover-t3-camera-partial-dual-3x8-admission-v1"
)
PARTIAL_RESULT_KIND = (
    "mf1750-raw-p16-crossover-t3-camera-partial-dual-3x8-result-v1"
)
PARTIAL_BUNDLE_KIND = (
    "mf1750-raw-p16-crossover-t3-camera-partial-dual-3x8-bundle-v1"
)
PARTIAL_PACK_REVISION = "w3-white-one-plus-t3-three-exp6-partial-dual-3x8-v1"
PARTIAL_SELECTED_ROWS = (0, 1, 2)
PARTIAL_SELECTED_COLUMNS = tuple(range(8))
PARTIAL_SELECTED_CELL_COUNT = 48
PARTIAL_REPLICATES_PER_CODE_PER_CONTROLLER_PER_FRAME = 3
PARTIAL_T3_LIGHT_GUARD_SAMPLES = 6
PARTIAL_MAXIMUM_CORNER_RMS_DRIFT_PX = 8.0
PARTIAL_MAXIMUM_CORNER_DRIFT_PX = 15.0

WHITE_SLOT = "w3-white-reference"
T3_SLOT = "t3-retained-atlas"
SLOTS = (WHITE_SLOT, T3_SLOT)
REQUIRED_ACCEPTED = {WHITE_SLOT: 1, T3_SLOT: 3}
MAXIMUM_ATTEMPTS = {WHITE_SLOT: 2, T3_SLOT: 5}
MAXIMUM_TOTAL_ATTEMPTS = sum(MAXIMUM_ATTEMPTS.values())
SETUP_VIEW_MAXIMUM_ATTEMPTS = 2

TARGET_CAMERA = {
    "logical_id": camera.TARGET_CAMERA_LOGICAL_ID,
    "friendly_name": camera.TARGET_CAMERA_FRIENDLY_NAME,
    "required_directshow_token": camera.TARGET_CAMERA_USB_TOKEN,
    "excluded_directshow_token": camera.EXCLUDED_BINOCULAR_USB_TOKEN,
}
CAMERA_PROFILE = deepcopy(frozen.EXPECTED_CAMERA_PROFILE)
WARMUP_FRAMES = 8
JPEG_QUALITY = 95
PHOTO_WIDTH = 4000
PHOTO_HEIGHT = 3000
WHITE_REFERENCE_MIN_LSTAR = 25.0
EXPECTED_T3_WHITE_CODE = 3
MAXIMUM_CROSS_CAPTURE_CORNER_DRIFT_PX = 30.0
DEFAULT_OUTPUT_ROOT = Path(
    ".test-output/hardware/"
    "MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_CAMERA_DAYLIGHT_V1"
)
DEFAULT_PARTIAL_OUTPUT_ROOT = Path(
    ".test-output/hardware/"
    "MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_"
    "CAMERA_PARTIAL_DUAL_3X8_V1"
)


class T3CameraCapturePackError(RuntimeError):
    """Raised when capture-pack evidence fails closed."""


class _DuplicateKeyError(ValueError):
    pass


CaptureFunction = Callable[..., dict[str, Any]]


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    root = dict(value)
    root.pop("integrity", None)
    root["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": _sha256_bytes(_canonical_json(root)),
    }
    return root


def _verify_seal(value: Mapping[str, Any], *, label: str) -> str:
    integrity = value.get("integrity")
    if not isinstance(integrity, Mapping) or set(integrity) != {
        "algorithm",
        "sha256",
    }:
        raise T3CameraCapturePackError(f"{label} integrity keys differ")
    unsigned = dict(value)
    unsigned.pop("integrity")
    expected = _sha256_bytes(_canonical_json(unsigned))
    if (
        integrity.get("algorithm") != INTEGRITY_ALGORITHM
        or integrity.get("sha256") != expected
    ):
        raise T3CameraCapturePackError(f"{label} integrity differs")
    return expected


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_stable_regular(path: Path, *, label: str) -> bytes:
    path = Path(path)
    try:
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise T3CameraCapturePackError(f"cannot read {label}: {error}") from error
    if not path.is_file() or path.is_symlink():
        raise T3CameraCapturePackError(f"{label} must be a regular non-symlink file")
    if (
        before.st_size != len(payload)
        or after.st_size != len(payload)
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise T3CameraCapturePackError(f"{label} changed while being read")
    return payload


def _load_json(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    payload = _read_stable_regular(path, label=label)
    try:
        root = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {item}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise T3CameraCapturePackError(
            f"{label} is not strict UTF-8 JSON: {error}"
        ) from error
    if not isinstance(root, dict):
        raise T3CameraCapturePackError(f"{label} root must be an object")
    return payload, root


def _write_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    payload = (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
    except FileExistsError as error:
        raise T3CameraCapturePackError(
            f"refusing to overwrite existing evidence: {path}"
        ) from error
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _copy_exclusive(source: Path, target: Path) -> dict[str, Any]:
    payload = _read_stable_regular(source, label="action result source")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
    except FileExistsError as error:
        raise T3CameraCapturePackError(
            f"refusing to overwrite action snapshot: {target}"
        ) from error
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    persisted = _read_stable_regular(target, label="action result snapshot")
    if persisted != payload:
        raise T3CameraCapturePackError("action result snapshot bytes differ")
    return {
        "path": target.resolve().as_posix(),
        "bytes": len(payload),
        "sha256": _sha256_bytes(payload),
    }


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def _normalise_panel_corners(value: str | Any) -> list[list[float]]:
    try:
        corners = geometry._coerce_panel_corners(value)  # noqa: SLF001
        _homography, report = geometry._fit_panel_homography(  # noqa: SLF001
            corners,
            photo_width=PHOTO_WIDTH,
            photo_height=PHOTO_HEIGHT,
        )
    except geometry.CrossoverPhotoAnalysisError as error:
        raise T3CameraCapturePackError(
            f"panel geometry rejected before capture: {error}"
        ) from error
    if report.get("sampling_geometry_admitted") is not True:
        raise T3CameraCapturePackError("panel geometry was not admitted")
    return [
        [round(float(component), 6) for component in row] for row in corners.tolist()
    ]


def _expected_action_identity(slot: str, *, partial: bool = False) -> dict[str, Any]:
    if slot == WHITE_SLOT:
        report = w3_pack.build_white_report()
        action = report["action"]
        artifacts = w3_pack.WHITE_ARTIFACTS[w3_pack.STAGE]
        config = w3_pack.CONFIG
        return {
            "stage": w3_pack.STAGE,
            "campaign_id": config.campaign_id,
            "test_id": config.test_id,
            "contract_id": report["contract_id"],
            "firmware_sha256": artifacts["bin_sha256"],
            "action_id": action["action_id"],
            "descriptor_id": action["descriptor_id"],
            "role": action["role"],
            "frame_sha256": action["frame_sha256"],
        }
    if slot == T3_SLOT:
        selected_pack = t3_v2_pack if partial else t3_pack
        report = selected_pack.build_report()
        action = report["actions"][0]
        artifacts = selected_pack.ARTIFACTS[selected_pack.STAGE]
        config = selected_pack.CONFIG
        return {
            "stage": selected_pack.STAGE,
            "campaign_id": config.campaign_id,
            "test_id": config.test_id,
            "contract_id": report["contract_id"],
            "firmware_sha256": artifacts["bin_sha256"],
            "action_id": action["action_id"],
            "descriptor_id": action["descriptor_id"],
            "role": action["role"],
            "frame_sha256": action["frame"]["sha256"],
        }
    raise T3CameraCapturePackError(f"unsupported capture slot {slot!r}")


def _validate_action_source(
    slot: str, path: Path, *, partial: bool = False
) -> dict[str, Any]:
    try:
        if slot == WHITE_SLOT:
            actual = human._validate_w3_white_action_result(path)  # noqa: SLF001
        elif slot == T3_SLOT:
            actual = human._validate_action_result(  # noqa: SLF001
                path,
                stage=(human.AC_V2_STAGE if partial else human.AC_STAGE),
            )
        else:
            raise T3CameraCapturePackError(f"unsupported capture slot {slot!r}")
    except human.HumanObservationError as error:
        raise T3CameraCapturePackError(
            f"{slot} action result rejected: {error}"
        ) from error
    expected = _expected_action_identity(slot, partial=partial)
    for field, value in expected.items():
        if field == "frame_sha256" and field not in actual:
            continue
        if actual.get(field) != value:
            raise T3CameraCapturePackError(
                f"{slot} action result {field} differs from frozen identity"
            )
    return {**expected, "source": actual}


def build_contract(
    *, mount_id: str, panel_corners: str | Any | None = None
) -> dict[str, Any]:
    if not isinstance(mount_id, str) or not mount_id.strip():
        raise T3CameraCapturePackError("mount_id must be non-empty")
    if CAMERA_PROFILE != {
        "fourcc": "MJPG",
        "frame_width": 4000,
        "frame_height": 3000,
        "fps": 15.0,
        "autofocus": 0.0,
        "focus": 79.0,
        "auto_exposure": 0.25,
        "exposure": -6.0,
        "auto_white_balance": 0.0,
        "white_balance_temperature": 4600.0,
    }:
        raise T3CameraCapturePackError(
            "camera profile differs from README camera.md exposure=-6 contract"
        )
    if panel_corners is not None:
        _normalise_panel_corners(panel_corners)
    root = {
        "schema_version": SCHEMA_VERSION,
        "kind": CONTRACT_KIND,
        "pack_revision": PACK_REVISION,
        "camera": {
            "target": TARGET_CAMERA,
            "profile": CAMERA_PROFILE,
            "warmup_frames": WARMUP_FRAMES,
            "jpeg_quality": JPEG_QUALITY,
            "require_all_setting_writes": True,
            "capture_binding": camera.BINDING_LOCKED_RETAINED,
            "coverage_scope": camera.COVERAGE_FULL,
            "mount_id": mount_id.strip(),
            "full_panel_visible": True,
            "full_panel_uncropped": True,
            "instance_and_effective_settings_frozen_by_white_reference": True,
        },
        "geometry": {
            "photo_width": PHOTO_WIDTH,
            "photo_height": PHOTO_HEIGHT,
            "two_phase_acquire_then_admit_required": True,
            "corners_forbidden_during_acquire": True,
            "corners_bound_to_sealed_photo_during_admit": True,
            "explicit_current_photo_corners_required_for_every_frame": True,
            "per_frame_corners_recorded_independently": True,
            "same_corners_reused_by_assumption": False,
            "maximum_cross_capture_corresponding_corner_drift_px": (
                MAXIMUM_CROSS_CAPTURE_CORNER_DRIFT_PX
            ),
            "failure_policy": "FAIL_CLOSED_NO_CAPTURE_ACCEPTANCE",
        },
        "illumination": {
            "white_reference_min_lstar": WHITE_REFERENCE_MIN_LSTAR,
            "white_reference_samples": "ALL_64_INNER_CELL_ROIS",
            "t3_light_guard_code": EXPECTED_T3_WHITE_CODE,
            "t3_light_guard_expected_samples": 8,
            "automatic_threshold_relaxation": False,
            "exposure_change_on_low_light": False,
            "failure_policy": "FAIL_CLOSED_CONSUME_ATTEMPT_KEEP_EVIDENCE",
        },
        "slots": {
            WHITE_SLOT: {
                "required_accepted": REQUIRED_ACCEPTED[WHITE_SLOT],
                "maximum_attempts": MAXIMUM_ATTEMPTS[WHITE_SLOT],
                "action": _expected_action_identity(WHITE_SLOT),
            },
            T3_SLOT: {
                "required_accepted": REQUIRED_ACCEPTED[T3_SLOT],
                "maximum_attempts": MAXIMUM_ATTEMPTS[T3_SLOT],
                "action": _expected_action_identity(T3_SLOT),
                "requires_accepted_white_reference": True,
            },
        },
        "attempt_boundary": {
            "maximum_total_attempts": MAXIMUM_TOTAL_ATTEMPTS,
            "one_camera_acquisition_per_process_invocation": True,
            "claim_written_before_camera_open": True,
            "successful_acquisition_requires_one_offline_admission": True,
            "admission_claim_written_before_corner_parsing": True,
            "one_admission_maximum_per_acquisition": True,
            "failed_attempt_permanently_consumed": True,
            "automatic_retry": False,
            "automatic_fallback": False,
            "automatic_chaining": False,
        },
        "evidence": {
            "photo_action_sidecar_hashes_required": True,
            "camera_metadata_and_effective_readbacks_required": True,
            "all_outputs_o_excl": True,
            "distinct_t3_capture_ids_required": True,
            "distinct_t3_photo_hashes_required": True,
            "camera_relative_screening_only": True,
            "absolute_colour_qualification": False,
            "qualified_colour_count": 0,
        },
        "w4_following_boundary": {
            "core_four_frame_bundle_success_unlocks_w4": True,
            "camera_classification_required_before_safe_w4_white": False,
            "w4_post_white_is_independent_fifth_frame": True,
            "w4_post_white_included_in_this_bundle": False,
            "analysis_may_continue_after_white_containment": True,
        },
    }
    return _seal(root)


def _contract_path(output_root: Path) -> Path:
    return Path(output_root) / "capture-contract.json"


def ensure_contract(
    *,
    output_root: Path,
    mount_id: str,
    panel_corners: str | Any | None = None,
) -> dict[str, Any]:
    # Compatibility-only validation for offline callers of the old helper.
    # Acquisition never supplies corners; describe may still preflight them.
    if panel_corners is not None:
        _normalise_panel_corners(panel_corners)
    expected = build_contract(mount_id=mount_id)
    path = _contract_path(output_root)
    if path.exists():
        _payload, actual = _load_json(path, label="capture contract")
        _verify_seal(actual, label="capture contract")
        if actual != expected:
            raise T3CameraCapturePackError(
                "existing capture contract differs from requested mount"
            )
        return actual
    _write_exclusive(path, expected)
    return expected


def _normalise_partial_blocks(value: str | Mapping[str, Any]) -> dict[str, list[list[float]]]:
    """Validate the two exact-photo controller blocks for the partial mode."""

    candidate: Any = value
    if isinstance(value, str):
        try:
            candidate = json.loads(
                value,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=lambda item: (_ for _ in ()).throw(
                    ValueError(f"non-finite JSON constant {item}")
                ),
            )
        except (json.JSONDecodeError, ValueError, _DuplicateKeyError) as error:
            raise T3CameraCapturePackError(
                f"partial blocks are not strict JSON: {error}"
            ) from error
    if not isinstance(candidate, Mapping) or set(candidate) != {"CS1", "CS2"}:
        raise T3CameraCapturePackError(
            "partial blocks must contain exactly CS1 and CS2"
        )
    try:
        _homographies, report = geometry._fit_partial_dual_controller_blocks(  # noqa: SLF001
            candidate,
            photo_width=PHOTO_WIDTH,
            photo_height=PHOTO_HEIGHT,
        )
    except geometry.CrossoverPhotoAnalysisError as error:
        raise T3CameraCapturePackError(
            f"partial dual-controller geometry rejected: {error}"
        ) from error
    if (
        report.get("sampling_geometry_admitted") is not True
        or report.get("selected_rows") != list(PARTIAL_SELECTED_ROWS)
        or report.get("selected_cell_count") != PARTIAL_SELECTED_CELL_COUNT
    ):
        raise T3CameraCapturePackError("partial geometry admission report differs")
    supplied = report.get("supplied_block_corners_tl_tr_br_bl")
    if not isinstance(supplied, Mapping) or set(supplied) != {"CS1", "CS2"}:
        raise T3CameraCapturePackError("partial geometry supplied-corner report differs")
    return {
        controller: [
            [round(float(component), 6) for component in row]
            for row in supplied[controller]
        ]
        for controller in ("CS1", "CS2")
    }


def build_partial_contract(*, mount_id: str) -> dict[str, Any]:
    """Build the independent partial-dual-3x8 capture contract."""

    full = build_contract(mount_id=mount_id)
    camera_contract = deepcopy(full["camera"])
    camera_contract.update(
        {
            "capture_binding": camera.BINDING_LOCKED_RETAINED,
            "coverage_scope": camera.COVERAGE_PARTIAL,
            "full_panel_visible": False,
            "full_panel_uncropped": False,
            "selected_roi_visible_required": True,
            "both_controller_rois_required": True,
        }
    )
    partial_slots = deepcopy(full["slots"])
    partial_slots[T3_SLOT]["action"] = _expected_action_identity(
        T3_SLOT, partial=True
    )
    root = {
        "schema_version": SCHEMA_VERSION,
        "kind": PARTIAL_CONTRACT_KIND,
        "pack_revision": PARTIAL_PACK_REVISION,
        "mode": PARTIAL_MODE,
        "camera": camera_contract,
        "geometry": {
            "photo_width": PHOTO_WIDTH,
            "photo_height": PHOTO_HEIGHT,
            "geometry_mode": PARTIAL_MODE,
            "full_panel_corners_required": False,
            "two_phase_acquire_then_admit_required": True,
            "blocks_forbidden_during_acquire": True,
            "blocks_bound_to_sealed_photo_during_admit": True,
            "each_frame_uses_its_own_exact_photo_blocks": True,
            "controllers": ["CS1", "CS2"],
            "selected_rows": list(PARTIAL_SELECTED_ROWS),
            "selected_columns": list(PARTIAL_SELECTED_COLUMNS),
            "selected_cells_per_controller": 24,
            "selected_cell_count": PARTIAL_SELECTED_CELL_COUNT,
            "replicates_per_code_per_controller_per_frame": (
                PARTIAL_REPLICATES_PER_CODE_PER_CONTROLLER_PER_FRAME
            ),
            "row_codes": [
                list(t3_v2_pack.CODE_ROWS[row]) for row in PARTIAL_SELECTED_ROWS
            ],
            "maximum_cross_capture_corner_rms_drift_px": (
                PARTIAL_MAXIMUM_CORNER_RMS_DRIFT_PX
            ),
            "maximum_cross_capture_corner_drift_px": (
                PARTIAL_MAXIMUM_CORNER_DRIFT_PX
            ),
            "full_64_cell_lattice_evaluated": False,
            "fourth_row_evaluated": False,
            "bottom_edge_evaluated": False,
            "outside_roi_status": "NOT_EVALUATED_OUTSIDE_SELECTED_ROI",
            "failure_policy": "FAIL_CLOSED_NO_PARTIAL_CAPTURE_ACCEPTANCE",
        },
        "illumination": {
            "normalization": (
                "SAME_CONTROLLER_SAME_CELL_W3_WHITE_REFERENCE_PER_ROI"
            ),
            "raw_cross_side_rgb_equality_gate": False,
            "white_reference_min_lstar": WHITE_REFERENCE_MIN_LSTAR,
            "white_reference_samples": PARTIAL_SELECTED_CELL_COUNT,
            "t3_light_guard_code": EXPECTED_T3_WHITE_CODE,
            "t3_light_guard_expected_samples": PARTIAL_T3_LIGHT_GUARD_SAMPLES,
            "automatic_threshold_relaxation": False,
            "exposure_change_on_low_light": False,
            "failure_policy": "FAIL_CLOSED_CONSUME_ATTEMPT_KEEP_EVIDENCE",
        },
        "slots": partial_slots,
        "attempt_boundary": deepcopy(full["attempt_boundary"]),
        "evidence": {
            **deepcopy(full["evidence"]),
            "partial_dual_controller_screening_only": True,
            "formal_full_panel_evidence": False,
            "full_panel_geometry_evaluated": False,
            "profile_code_pair_comparison_available": True,
            "profile_following_decision_earned": False,
        },
        "w4_following_boundary": {
            "partial_bundle_may_precede_safe_w4_white_containment": True,
            "camera_classification_required_before_safe_w4_white": False,
            "w4_post_white_full_screen_seal_earned": False,
            "partial_roi_may_be_promoted_to_w4_full_white_seal": False,
            "w4_post_white_included_in_this_bundle": False,
        },
    }
    return _seal(root)


def ensure_partial_contract(*, output_root: Path, mount_id: str) -> dict[str, Any]:
    expected = build_partial_contract(mount_id=mount_id)
    path = _contract_path(output_root)
    if path.exists():
        _payload, actual = _load_json(path, label="partial capture contract")
        _verify_seal(actual, label="partial capture contract")
        if actual != expected:
            raise T3CameraCapturePackError(
                "existing partial capture contract differs from requested mount"
            )
        return actual
    _write_exclusive(path, expected)
    return expected


def _setup_contract_path(output_root: Path) -> Path:
    return Path(output_root) / "setup-view-contract.json"


def build_setup_view_contract(*, mount_id: str) -> dict[str, Any]:
    if not isinstance(mount_id, str) or not mount_id.strip():
        raise T3CameraCapturePackError("mount_id must be non-empty")
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": SETUP_CONTRACT_KIND,
            "target_camera": TARGET_CAMERA,
            "camera_profile": CAMERA_PROFILE,
            "warmup_frames": WARMUP_FRAMES,
            "jpeg_quality": JPEG_QUALITY,
            "mount_id": mount_id.strip(),
            "maximum_attempts": SETUP_VIEW_MAXIMUM_ATTEMPTS,
            "action": _expected_action_identity(WHITE_SLOT),
            "formal_evidence": False,
            "eligible_for_core_bundle": False,
            "panel_corners_accepted_or_exported": False,
            "purpose": "SETUP_ONLY_HUMAN_FULL_PANEL_AND_LIGHTING_VIEW",
            "claim_written_before_camera_open": True,
            "automatic_retry": False,
            "automatic_fallback": False,
            "automatic_chaining": False,
        }
    )


def ensure_setup_view_contract(*, output_root: Path, mount_id: str) -> dict[str, Any]:
    expected = build_setup_view_contract(mount_id=mount_id)
    path = _setup_contract_path(output_root)
    if path.exists():
        _payload, actual = _load_json(path, label="setup-view contract")
        _verify_seal(actual, label="setup-view contract")
        if actual != expected:
            raise T3CameraCapturePackError("existing setup-view contract differs")
        return actual
    _write_exclusive(path, expected)
    return expected


def _claim_paths(output_root: Path, slot: str) -> list[Path]:
    return sorted((Path(output_root) / "claims").glob(f"{slot}-attempt-*.claim.json"))


def _result_paths(output_root: Path, slot: str) -> list[Path]:
    return sorted((Path(output_root) / "results").glob(f"{slot}-attempt-*.result.json"))


def _acquisition_paths(output_root: Path, slot: str) -> list[Path]:
    return sorted(
        (Path(output_root) / "acquisitions").glob(f"{slot}-attempt-*.acquisition.json")
    )


def _admission_paths(output_root: Path, slot: str) -> list[Path]:
    return sorted(
        (Path(output_root) / "admissions").glob(f"{slot}-attempt-*.admission.json")
    )


def _acquisition_path(output_root: Path, slot: str, attempt: int) -> Path:
    return (
        Path(output_root)
        / "acquisitions"
        / f"{slot}-attempt-{attempt:02d}.acquisition.json"
    )


def _admission_path(output_root: Path, slot: str, attempt: int) -> Path:
    return (
        Path(output_root)
        / "admissions"
        / f"{slot}-attempt-{attempt:02d}.admission.json"
    )


def _result_path(output_root: Path, slot: str, attempt: int) -> Path:
    return Path(output_root) / "results" / f"{slot}-attempt-{attempt:02d}.result.json"


def _load_claims(
    output_root: Path,
    slot: str,
    *,
    contract_integrity_sha256: str | None = None,
) -> list[tuple[Path, dict[str, Any]]]:
    loaded: list[tuple[Path, dict[str, Any]]] = []
    for expected_attempt, path in enumerate(_claim_paths(output_root, slot), start=1):
        _payload, root = _load_json(path, label=f"{slot} attempt claim")
        _verify_seal(root, label=f"{slot} attempt claim")
        expected_name = f"{slot}-attempt-{expected_attempt:02d}.claim.json"
        if (
            set(root)
            != {
                "schema_version",
                "kind",
                "slot",
                "attempt",
                "maximum_attempts",
                "claimed_at",
                "contract_integrity_sha256",
                "action_source",
                "state",
                "two_phase_state",
                "panel_corners_bound_during_acquire",
                "offline_admission_required_after_acquisition",
                "one_camera_acquisition_maximum",
                "automatic_retry",
                "automatic_fallback",
                "automatic_chaining",
                "integrity",
            }
            or root.get("schema_version") != SCHEMA_VERSION
            or path.name != expected_name
            or root.get("kind") != CLAIM_KIND
            or root.get("slot") != slot
            or root.get("attempt") != expected_attempt
            or root.get("maximum_attempts") != MAXIMUM_ATTEMPTS[slot]
            or root.get("state") != "PERMANENTLY_CONSUMED_BEFORE_CAMERA_OPEN"
            or root.get("two_phase_state") != "ACQUIRE_CLAIMED_NO_CORNERS_BOUND"
            or root.get("panel_corners_bound_during_acquire") is not False
            or root.get("offline_admission_required_after_acquisition") is not True
            or root.get("one_camera_acquisition_maximum") is not True
            or root.get("automatic_retry") is not False
            or root.get("automatic_fallback") is not False
            or root.get("automatic_chaining") is not False
        ):
            raise T3CameraCapturePackError(f"{slot} attempt claim differs")
        if "panel_corners_tl_tr_br_bl" in root:
            raise T3CameraCapturePackError(
                f"{slot} attempt claim must not contain pre-acquisition corners"
            )
        if (
            contract_integrity_sha256 is not None
            and root.get("contract_integrity_sha256") != contract_integrity_sha256
        ):
            raise T3CameraCapturePackError(
                f"{slot} attempt claim contract binding differs"
            )
        loaded.append((path, root))
    if len(loaded) > MAXIMUM_ATTEMPTS[slot]:
        raise T3CameraCapturePackError(f"{slot} claim count exceeds budget")
    return loaded


def _sealed_file_binding(
    path: Path, value: Mapping[str, Any], *, label: str
) -> dict[str, Any]:
    payload = _read_stable_regular(path, label=label)
    integrity = _verify_seal(value, label=label)
    return {
        "path": path.resolve().as_posix(),
        "sha256": _sha256_bytes(payload),
        "integrity_sha256": integrity,
    }


def _load_acquisition(
    *, output_root: Path, slot: str, attempt: int, contract_integrity_sha256: str
) -> tuple[Path, dict[str, Any]]:
    path = _acquisition_path(output_root, slot, attempt).resolve()
    _payload, root = _load_json(path, label=f"{slot} acquisition")
    _verify_seal(root, label=f"{slot} acquisition")
    if (
        root.get("schema_version") != SCHEMA_VERSION
        or root.get("kind") != ACQUISITION_KIND
        or root.get("slot") != slot
        or root.get("attempt") != attempt
        or root.get("contract_integrity_sha256") != contract_integrity_sha256
        or root.get("automatic_retry_count") != 0
        or root.get("automatic_fallback") is not False
        or root.get("automatic_chaining") is not False
        or root.get("camera_invocations") not in (0, 1)
        or "panel_corners_tl_tr_br_bl" in root
        or "evaluation" in root
    ):
        raise T3CameraCapturePackError(f"{slot} acquisition identity differs")
    _validate_result_claim(output_root=output_root, result=root, slot=slot)
    acquired = root.get("acquired")
    if acquired is True:
        if (
            root.get("outcome") != "ACQUIRED_SEALED_AWAITING_MANUAL_CORNERS"
            or root.get("camera_invocations") != 1
            or root.get("offline_admission_required") is not True
            or not isinstance(root.get("capture"), Mapping)
            or not isinstance(root.get("action_snapshot"), Mapping)
        ):
            raise T3CameraCapturePackError(
                f"{slot} successful acquisition state differs"
            )
    elif acquired is False:
        if root.get("outcome") != "ACQUISITION_REJECTED_FAIL_CLOSED":
            raise T3CameraCapturePackError(f"{slot} failed acquisition state differs")
    else:
        raise T3CameraCapturePackError(f"{slot} acquisition flag differs")
    return path, root


def _load_admission(
    *,
    output_root: Path,
    slot: str,
    attempt: int,
    contract_integrity_sha256: str,
    acquisition_path: Path,
    acquisition: Mapping[str, Any],
) -> tuple[Path, dict[str, Any]]:
    path = _admission_path(output_root, slot, attempt).resolve()
    _payload, root = _load_json(path, label=f"{slot} admission claim")
    _verify_seal(root, label=f"{slot} admission claim")
    corners_text = root.get("panel_corners_tl_tr_br_bl_text")
    if (
        root.get("schema_version") != SCHEMA_VERSION
        or root.get("kind") != ADMISSION_KIND
        or root.get("slot") != slot
        or root.get("attempt") != attempt
        or root.get("contract_integrity_sha256") != contract_integrity_sha256
        or root.get("state")
        != "PERMANENTLY_CONSUMED_BEFORE_CORNER_PARSING_AND_ANALYSIS"
        or not isinstance(corners_text, str)
        or not corners_text.strip()
        or root.get("automatic_retry") is not False
        or root.get("automatic_fallback") is not False
        or root.get("automatic_chaining") is not False
        or root.get("camera_invocations_during_admit") != 0
    ):
        raise T3CameraCapturePackError(f"{slot} admission claim differs")
    expected_acquisition = _sealed_file_binding(
        acquisition_path, acquisition, label=f"{slot} acquisition"
    )
    if root.get("acquisition") != expected_acquisition:
        raise T3CameraCapturePackError(
            f"{slot} admission-to-acquisition binding differs"
        )
    return path, root


def _validate_result_claim(
    *, output_root: Path, result: Mapping[str, Any], slot: str
) -> None:
    attempt = result.get("attempt")
    if type(attempt) is not int or attempt < 1:
        raise T3CameraCapturePackError(f"{slot} capture result attempt differs")
    expected_path = (
        Path(output_root) / "claims" / f"{slot}-attempt-{attempt:02d}.claim.json"
    ).resolve()
    claim_record = result.get("claim")
    if not isinstance(claim_record, Mapping):
        raise T3CameraCapturePackError(f"{slot} capture result claim is missing")
    claim_payload, claim = _load_json(expected_path, label=f"{slot} attempt claim")
    claim_integrity = _verify_seal(claim, label=f"{slot} attempt claim")
    if dict(claim_record) != {
        "path": expected_path.as_posix(),
        "sha256": _sha256_bytes(claim_payload),
        "integrity_sha256": claim_integrity,
    }:
        raise T3CameraCapturePackError(f"{slot} result-to-claim binding differs")


def _accepted_results(
    output_root: Path,
    slot: str,
    *,
    contract_integrity_sha256: str | None = None,
) -> list[dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    seen_attempts: set[int] = set()
    prefix = f"{slot}-attempt-"
    suffix = ".result.json"
    for path in _result_paths(output_root, slot):
        _payload, root = _load_json(path, label=f"{slot} capture result")
        _verify_seal(root, label=f"{slot} capture result")
        attempt_text = path.name.removeprefix(prefix).removesuffix(suffix)
        try:
            filename_attempt = int(attempt_text)
        except ValueError as error:
            raise T3CameraCapturePackError(
                f"{slot} capture result filename is malformed"
            ) from error
        if (
            path.name != f"{slot}-attempt-{filename_attempt:02d}.result.json"
            or root.get("schema_version") != SCHEMA_VERSION
            or root.get("kind") != RESULT_KIND
            or root.get("slot") != slot
            or root.get("attempt") != filename_attempt
            or filename_attempt in seen_attempts
            or not 1 <= filename_attempt <= MAXIMUM_ATTEMPTS[slot]
            or root.get("phase") != "OFFLINE_ADMISSION"
            or root.get("automatic_retry_count") != 0
            or root.get("automatic_fallback") is not False
            or root.get("automatic_chaining") is not False
            or root.get("camera_invocations") != 1
            or root.get("camera_invocations_during_admit") != 0
        ):
            raise T3CameraCapturePackError(f"{slot} capture result identity differs")
        seen_attempts.add(filename_attempt)
        if (
            contract_integrity_sha256 is not None
            and root.get("contract_integrity_sha256") != contract_integrity_sha256
        ):
            raise T3CameraCapturePackError(
                f"{slot} capture result contract binding differs"
            )
        _validate_result_claim(output_root=output_root, result=root, slot=slot)
        acquisition_path, acquisition = _load_acquisition(
            output_root=output_root,
            slot=slot,
            attempt=filename_attempt,
            contract_integrity_sha256=str(root["contract_integrity_sha256"]),
        )
        if acquisition.get("acquired") is not True:
            raise T3CameraCapturePackError(
                f"{slot} result is bound to a failed acquisition"
            )
        admission_path, admission = _load_admission(
            output_root=output_root,
            slot=slot,
            attempt=filename_attempt,
            contract_integrity_sha256=str(root["contract_integrity_sha256"]),
            acquisition_path=acquisition_path,
            acquisition=acquisition,
        )
        if root.get("acquisition") != _sealed_file_binding(
            acquisition_path, acquisition, label=f"{slot} acquisition"
        ) or root.get("admission") != _sealed_file_binding(
            admission_path, admission, label=f"{slot} admission claim"
        ):
            raise T3CameraCapturePackError(
                f"{slot} result two-phase evidence binding differs"
            )
        if root.get("accepted") is True:
            if root.get("outcome") != "ACCEPTED":
                raise T3CameraCapturePackError(
                    f"{slot} accepted result outcome/camera count differs"
                )
            accepted.append(root)
        elif root.get("outcome") != "REJECTED_FAIL_CLOSED_DO_NOT_AUTO_RETRY":
            raise T3CameraCapturePackError(f"{slot} rejected result outcome differs")
    return accepted


def _alignment(capture: Mapping[str, Any]) -> dict[str, Any]:
    camera_record = capture["camera"]
    return {
        "camera_id": camera_record["camera_id"],
        "instance_id": camera_record["instance_id"],
        "backend": camera_record["backend"],
        "mount_id": capture["coverage"]["mount_id"],
        "requested_settings": camera_record["requested_settings"],
        "effective_settings_before_frame": camera_record[
            "effective_settings_before_frame"
        ],
        "effective_settings_after_frame": camera_record[
            "effective_settings_after_frame"
        ],
        "photo_width": capture["photo"]["width"],
        "photo_height": capture["photo"]["height"],
    }


def _corresponding_corner_drift(
    first_geometry: Mapping[str, Any], second_geometry: Mapping[str, Any]
) -> dict[str, Any]:
    first = first_geometry.get("supplied_panel_corners_tl_tr_br_bl")
    second = second_geometry.get("supplied_panel_corners_tl_tr_br_bl")
    if (
        not isinstance(first, list)
        or not isinstance(second, list)
        or len(first) != 4
        or len(second) != 4
        or any(not isinstance(row, list) or len(row) != 2 for row in (*first, *second))
    ):
        raise T3CameraCapturePackError("capture geometry corner metadata differs")
    distances = [
        math.dist([float(value) for value in left], [float(value) for value in right])
        for left, right in zip(first, second, strict=True)
    ]
    maximum = max(distances)
    if maximum > MAXIMUM_CROSS_CAPTURE_CORNER_DRIFT_PX:
        raise T3CameraCapturePackError(
            "cross-capture panel corner drift rejected: maximum "
            f"{maximum:.6f}px exceeds {MAXIMUM_CROSS_CAPTURE_CORNER_DRIFT_PX:.1f}px"
        )
    return {
        "corresponding_corner_distances_px": [
            round(float(value), 6) for value in distances
        ],
        "maximum_corresponding_corner_drift_px": round(float(maximum), 6),
        "maximum_allowed_px": MAXIMUM_CROSS_CAPTURE_CORNER_DRIFT_PX,
        "passed": True,
    }


def _sample_gate(
    *, slot: str, photo_payload: bytes, panel_corners: Any
) -> dict[str, Any]:
    try:
        rgb = geometry.base._decode_rgb(photo_payload)  # noqa: SLF001
        if rgb.shape[1] != PHOTO_WIDTH or rgb.shape[0] != PHOTO_HEIGHT:
            raise T3CameraCapturePackError("captured JPEG is not exact 4000x3000")
        homography, geometry_report = geometry._fit_panel_homography(  # noqa: SLF001
            panel_corners,
            photo_width=rgb.shape[1],
            photo_height=rgb.shape[0],
        )
        sampled = [
            geometry.base._sample_cell(rgb, homography, cell)  # noqa: SLF001
            for cell in geometry._all_logical_cells()  # noqa: SLF001
        ]
    except geometry.CrossoverPhotoAnalysisError as error:
        raise T3CameraCapturePackError(f"capture geometry rejected: {error}") from error
    if len(sampled) != 64:
        raise T3CameraCapturePackError("capture geometry did not produce 64 cells")
    if slot == WHITE_SLOT:
        light_samples = sampled
        light_guard = "ALL_64_WHITE_REFERENCE_CELLS"
    elif slot == T3_SLOT:
        light_samples = [
            item
            for item in sampled
            if t3_pack.CODE_ROWS[item["row"]][item["column"]] == EXPECTED_T3_WHITE_CODE
        ]
        light_guard = f"T3_CODE_{EXPECTED_T3_WHITE_CODE}_EIGHT_POSITIONS"
        if len(light_samples) != 8:
            raise T3CameraCapturePackError(
                "T3 white-code illumination guard does not have eight samples"
            )
    else:
        raise T3CameraCapturePackError(f"unsupported capture slot {slot!r}")
    lstars = [
        float(item["camera_relative_lab_d65_from_rgb_median"][0])
        for item in light_samples
    ]
    minimum = min(lstars)
    if minimum < WHITE_REFERENCE_MIN_LSTAR:
        raise T3CameraCapturePackError(
            "low illumination rejected: minimum white-reference L* "
            f"{minimum:.6f} is below {WHITE_REFERENCE_MIN_LSTAR:.1f}"
        )
    return {
        "geometry": geometry_report,
        "illumination": {
            "guard": light_guard,
            "sample_count": len(lstars),
            "minimum_lstar": round(minimum, 6),
            "median_lstar": round(float(statistics.median(lstars)), 6),
            "minimum_required_lstar": WHITE_REFERENCE_MIN_LSTAR,
            "automatic_threshold_relaxation": False,
            "passed": True,
        },
    }


def _evaluate_capture(
    *,
    slot: str,
    capture: Mapping[str, Any],
    photo_payload: bytes,
    panel_corners: Any,
    expected_action: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        camera_lock = frozen._validate_fixed_capture(capture)  # noqa: SLF001
    except frozen.RawP16PhotoAnalysisError as error:
        raise T3CameraCapturePackError(
            f"exact README camera lock rejected: {error}"
        ) from error
    for field in (
        "campaign_id",
        "test_id",
        "contract_id",
        "firmware_sha256",
        "action_id",
        "descriptor_id",
        "role",
        "frame_sha256",
    ):
        if capture.get(field) != expected_action[field]:
            raise T3CameraCapturePackError(
                f"capture {field} differs from exact {slot} action"
            )
    if capture.get("capture_binding") != camera.BINDING_LOCKED_RETAINED:
        raise T3CameraCapturePackError("capture is not locked-retained")
    sample_gate = _sample_gate(
        slot=slot,
        photo_payload=photo_payload,
        panel_corners=panel_corners,
    )
    return {
        "camera_lock": camera_lock,
        "alignment": _alignment(capture),
        **sample_gate,
    }


def _validate_acquired_capture(
    *, slot: str, capture: Mapping[str, Any], expected_action: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate camera/action identity without claiming image geometry."""

    try:
        camera_lock = frozen._validate_fixed_capture(capture)  # noqa: SLF001
    except frozen.RawP16PhotoAnalysisError as error:
        raise T3CameraCapturePackError(
            f"exact README camera lock rejected: {error}"
        ) from error
    for field in (
        "campaign_id",
        "test_id",
        "contract_id",
        "firmware_sha256",
        "action_id",
        "descriptor_id",
        "role",
        "frame_sha256",
    ):
        if capture.get(field) != expected_action[field]:
            raise T3CameraCapturePackError(
                f"capture {field} differs from exact {slot} action"
            )
    if capture.get("capture_binding") != camera.BINDING_LOCKED_RETAINED:
        raise T3CameraCapturePackError("capture is not locked-retained")
    alignment = _alignment(capture)
    if (
        alignment["photo_width"] != PHOTO_WIDTH
        or alignment["photo_height"] != PHOTO_HEIGHT
    ):
        raise T3CameraCapturePackError("captured JPEG is not exact 4000x3000")
    return {"camera_lock": camera_lock, "alignment": alignment}


def _claim_attempt(
    *,
    output_root: Path,
    slot: str,
    contract: Mapping[str, Any],
    action_path: Path,
    action_payload: bytes,
) -> tuple[int, Path, dict[str, Any]]:
    existing = _load_claims(
        output_root,
        slot,
        contract_integrity_sha256=str(contract["integrity"]["sha256"]),
    )
    maximum = MAXIMUM_ATTEMPTS[slot]
    if len(existing) >= maximum:
        raise T3CameraCapturePackError(
            f"{slot} maximum attempt budget {maximum} is exhausted"
        )
    attempt = len(existing) + 1
    claim_path = (
        Path(output_root) / "claims" / f"{slot}-attempt-{attempt:02d}.claim.json"
    )
    claim = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": CLAIM_KIND,
            "slot": slot,
            "attempt": attempt,
            "maximum_attempts": maximum,
            "claimed_at": _now(),
            "contract_integrity_sha256": contract["integrity"]["sha256"],
            "action_source": {
                "path": Path(action_path).resolve().as_posix(),
                "bytes": len(action_payload),
                "sha256": _sha256_bytes(action_payload),
            },
            "state": "PERMANENTLY_CONSUMED_BEFORE_CAMERA_OPEN",
            "two_phase_state": "ACQUIRE_CLAIMED_NO_CORNERS_BOUND",
            "panel_corners_bound_during_acquire": False,
            "offline_admission_required_after_acquisition": True,
            "one_camera_acquisition_maximum": True,
            "automatic_retry": False,
            "automatic_fallback": False,
            "automatic_chaining": False,
        }
    )
    _write_exclusive(claim_path, claim)
    return attempt, claim_path, claim


def setup_view_once(
    *,
    output_root: Path,
    action_result_path: Path,
    mount_id: str,
    capture_function: CaptureFunction = camera.capture_locked_retained,
) -> dict[str, Any]:
    """Take one exact-camera setup-only view; never create formal evidence."""

    output_root = Path(output_root).resolve()
    action_result_path = Path(action_result_path).resolve()
    _validate_action_source(WHITE_SLOT, action_result_path)
    expected_action = _expected_action_identity(WHITE_SLOT)
    contract = ensure_setup_view_contract(output_root=output_root, mount_id=mount_id)
    claim_dir = output_root / "setup-claims"
    claim_paths = sorted(claim_dir.glob("setup-view-attempt-*.claim.json"))
    for expected_attempt, path in enumerate(claim_paths, start=1):
        _payload, prior = _load_json(path, label="setup-view claim")
        _verify_seal(prior, label="setup-view claim")
        if (
            path.name != f"setup-view-attempt-{expected_attempt:02d}.claim.json"
            or prior.get("schema_version") != SCHEMA_VERSION
            or prior.get("kind") != SETUP_CLAIM_KIND
            or prior.get("attempt") != expected_attempt
            or prior.get("maximum_attempts") != SETUP_VIEW_MAXIMUM_ATTEMPTS
            or prior.get("state") != "PERMANENTLY_CONSUMED_BEFORE_CAMERA_OPEN"
            or prior.get("formal_evidence") is not False
            or prior.get("panel_corners_accepted_or_exported") is not False
            or prior.get("automatic_retry") is not False
        ):
            raise T3CameraCapturePackError("setup-view claim ledger differs")
        prior_result_path = (
            output_root
            / "setup-results"
            / f"setup-view-attempt-{expected_attempt:02d}.result.json"
        )
        if not prior_result_path.is_file():
            raise T3CameraCapturePackError(
                f"setup-view attempt {expected_attempt} has an unresolved claim-only "
                "state; refusing to open the camera again"
            )
        _result_payload, prior_result = _load_json(
            prior_result_path, label="setup-view result"
        )
        _verify_seal(prior_result, label="setup-view result")
        if (
            prior_result.get("schema_version") != SCHEMA_VERSION
            or prior_result.get("kind") != SETUP_RESULT_KIND
            or prior_result.get("attempt") != expected_attempt
            or prior_result.get("formal_evidence") is not False
            or prior_result.get("eligible_for_core_bundle") is not False
            or prior_result.get("panel_corners_accepted_or_exported") is not False
            or prior_result.get("camera_invocations") not in (0, 1)
            or prior_result.get("automatic_retry_count") != 0
        ):
            raise T3CameraCapturePackError("setup-view result ledger differs")
    if len(claim_paths) >= SETUP_VIEW_MAXIMUM_ATTEMPTS:
        raise T3CameraCapturePackError(
            "setup-view maximum attempt budget 2 is exhausted"
        )
    attempt = len(claim_paths) + 1
    action_payload = _read_stable_regular(
        action_result_path, label="setup-view action result"
    )
    claim_path = claim_dir / f"setup-view-attempt-{attempt:02d}.claim.json"
    claim = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": SETUP_CLAIM_KIND,
            "attempt": attempt,
            "maximum_attempts": SETUP_VIEW_MAXIMUM_ATTEMPTS,
            "claimed_at": _now(),
            "state": "PERMANENTLY_CONSUMED_BEFORE_CAMERA_OPEN",
            "setup_contract_integrity_sha256": contract["integrity"]["sha256"],
            "action_source": {
                "path": action_result_path.as_posix(),
                "bytes": len(action_payload),
                "sha256": _sha256_bytes(action_payload),
            },
            "formal_evidence": False,
            "eligible_for_core_bundle": False,
            "panel_corners_accepted_or_exported": False,
            "one_camera_acquisition_maximum": True,
            "automatic_retry": False,
            "automatic_fallback": False,
            "automatic_chaining": False,
        }
    )
    _write_exclusive(claim_path, claim)
    evidence_dir = output_root / "setup-evidence" / f"setup-view-attempt-{attempt:02d}"
    snapshot_path = evidence_dir / "action-result.json"
    photo_path = evidence_dir / "camera.jpg"
    sidecar_path = evidence_dir / "camera.capture.json"
    result_path = (
        output_root / "setup-results" / f"setup-view-attempt-{attempt:02d}.result.json"
    )
    camera_invocations = 0
    capture: dict[str, Any] | None = None
    try:
        action_snapshot = _copy_exclusive(action_result_path, snapshot_path)
        camera_invocations = 1
        capture_function(
            action_result_path=snapshot_path,
            photo_path=photo_path,
            sidecar_path=sidecar_path,
            camera_id=camera.TARGET_CAMERA_LOGICAL_ID,
            camera_instance_id=None,
            camera_index=None,
            mount_id=contract["mount_id"],
            coverage_scope=camera.COVERAGE_FULL,
            coverage_note="setup-only human view; not formal T3 camera evidence",
            requested_settings=CAMERA_PROFILE,
            warmup_frames=WARMUP_FRAMES,
            jpeg_quality=JPEG_QUALITY,
            require_all_setting_writes=True,
            automated_verdict="INCONCLUSIVE",
            assessment_confidence="low",
            limitations=(
                "setup-only view",
                "not formal evidence",
                "no panel corners accepted or exported",
            ),
            analysis_source="t3-camera-setup-view-gate-v1",
        )
        capture = camera.validate_capture_evidence(sidecar_path)
        validation = _validate_acquired_capture(
            slot=WHITE_SLOT,
            capture=capture,
            expected_action=expected_action,
        )
        photo_payload = _read_stable_regular(photo_path, label="setup-view photo")
        sidecar_payload = _read_stable_regular(
            sidecar_path, label="setup-view capture sidecar"
        )
        result = _seal(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": SETUP_RESULT_KIND,
                "attempt": attempt,
                "captured": True,
                "outcome": "CAPTURED_AWAITING_HUMAN_SETUP_REVIEW",
                "recorded_at": _now(),
                "claim": _sealed_file_binding(
                    claim_path, claim, label="setup-view claim"
                ),
                "setup_contract_integrity_sha256": contract["integrity"]["sha256"],
                "action_identity": expected_action,
                "action_snapshot": action_snapshot,
                "capture": {
                    "capture_id": capture["capture_id"],
                    "captured_at": capture["captured_at"],
                    "sidecar_path": sidecar_path.resolve().as_posix(),
                    "sidecar_bytes": len(sidecar_payload),
                    "sidecar_sha256": _sha256_bytes(sidecar_payload),
                    "photo_path": photo_path.resolve().as_posix(),
                    "photo_bytes": len(photo_payload),
                    "photo_sha256": _sha256_bytes(photo_payload),
                },
                "camera_lock": validation["camera_lock"],
                "alignment": validation["alignment"],
                "formal_evidence": False,
                "eligible_for_core_bundle": False,
                "panel_corners_accepted_or_exported": False,
                "human_panel_and_lighting_review_required": True,
                "camera_invocations": 1,
                "automatic_retry_count": 0,
            }
        )
    except Exception as error:
        result = _seal(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": SETUP_RESULT_KIND,
                "attempt": attempt,
                "captured": False,
                "outcome": "SETUP_CAPTURE_REJECTED_FAIL_CLOSED",
                "recorded_at": _now(),
                "claim": _sealed_file_binding(
                    claim_path, claim, label="setup-view claim"
                ),
                "setup_contract_integrity_sha256": contract["integrity"]["sha256"],
                "action_identity": expected_action,
                "formal_evidence": False,
                "eligible_for_core_bundle": False,
                "panel_corners_accepted_or_exported": False,
                "camera_invocations": camera_invocations,
                "automatic_retry_count": 0,
                "error": {"type": type(error).__name__, "message": str(error)},
                "capture_metadata_if_validated": (
                    None
                    if capture is None
                    else {
                        "capture_id": capture["capture_id"],
                        "captured_at": capture["captured_at"],
                    }
                ),
            }
        )
    _write_exclusive(result_path, result)
    return result


def acquire_one(
    *,
    slot: str,
    output_root: Path,
    action_result_path: Path,
    mount_id: str,
    capture_function: CaptureFunction = camera.capture_locked_retained,
) -> dict[str, Any]:
    """Acquire one frame under a permanent claim, without image admission."""

    if slot not in SLOTS:
        raise T3CameraCapturePackError(f"unsupported capture slot {slot!r}")
    output_root = Path(output_root).resolve()
    action_result_path = Path(action_result_path).resolve()
    _validate_action_source(slot, action_result_path)
    expected_action = _expected_action_identity(slot)
    contract = ensure_contract(
        output_root=output_root,
        mount_id=mount_id,
    )
    contract_sha = str(contract["integrity"]["sha256"])
    accepted = _accepted_results(
        output_root,
        slot,
        contract_integrity_sha256=contract_sha,
    )
    if len(accepted) >= REQUIRED_ACCEPTED[slot]:
        raise T3CameraCapturePackError(
            f"{slot} already has its required accepted captures"
        )
    white_accepted = _accepted_results(
        output_root,
        WHITE_SLOT,
        contract_integrity_sha256=contract_sha,
    )
    if slot == T3_SLOT and len(white_accepted) != 1:
        raise T3CameraCapturePackError(
            "T3 acquisition requires exactly one accepted W3 white reference"
        )
    for claim_path, claim in _load_claims(
        output_root,
        slot,
        contract_integrity_sha256=contract_sha,
    ):
        acquisition_path = _acquisition_path(output_root, slot, int(claim["attempt"]))
        result_path = _result_path(output_root, slot, int(claim["attempt"]))
        if not acquisition_path.is_file():
            raise T3CameraCapturePackError(
                f"{slot} attempt {claim['attempt']} has an unresolved claim-only state; "
                "refusing to open the camera again"
            )
        if not result_path.exists():
            _path, acquisition = _load_acquisition(
                output_root=output_root,
                slot=slot,
                attempt=int(claim["attempt"]),
                contract_integrity_sha256=contract_sha,
            )
            if acquisition.get("acquired") is True:
                raise T3CameraCapturePackError(
                    f"{slot} attempt {claim['attempt']} awaits offline admission"
                )
    action_payload = _read_stable_regular(
        action_result_path, label=f"{slot} action result"
    )
    attempt, claim_path, claim = _claim_attempt(
        output_root=output_root,
        slot=slot,
        contract=contract,
        action_path=action_result_path,
        action_payload=action_payload,
    )
    evidence_dir = output_root / "evidence" / f"{slot}-attempt-{attempt:02d}"
    snapshot_path = evidence_dir / "action-result.json"
    photo_path = evidence_dir / "camera.jpg"
    sidecar_path = evidence_dir / "camera.capture.json"
    acquisition_path = _acquisition_path(output_root, slot, attempt)
    camera_invocations = 0
    capture: dict[str, Any] | None = None
    try:
        action_snapshot = _copy_exclusive(action_result_path, snapshot_path)
        camera_invocations = 1
        capture = capture_function(
            action_result_path=snapshot_path,
            photo_path=photo_path,
            sidecar_path=sidecar_path,
            camera_id=camera.TARGET_CAMERA_LOGICAL_ID,
            camera_instance_id=None,
            camera_index=None,
            mount_id=contract["camera"]["mount_id"],
            coverage_scope=camera.COVERAGE_FULL,
            coverage_note=(
                "full MF1750 panel; fixed mount; T3 camera-relative screening only"
            ),
            requested_settings=CAMERA_PROFILE,
            warmup_frames=WARMUP_FRAMES,
            jpeg_quality=JPEG_QUALITY,
            require_all_setting_writes=True,
            automated_verdict="INCONCLUSIVE",
            assessment_confidence="low",
            limitations=(
                "camera-relative screening only",
                "manual panel corners are not an automatic lattice proof",
                "no absolute colour or qualification claim",
            ),
            analysis_source="t3-camera-capture-pack-acquisition-gates-v1",
        )
        capture = camera.validate_capture_evidence(sidecar_path)
        photo_payload = _read_stable_regular(photo_path, label="captured photo")
        acquisition_validation = _validate_acquired_capture(
            slot=slot,
            capture=capture,
            expected_action=expected_action,
        )
        sidecar_payload = _read_stable_regular(sidecar_path, label="capture sidecar")
        acquisition = _seal(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": ACQUISITION_KIND,
                "slot": slot,
                "attempt": attempt,
                "acquired": True,
                "outcome": "ACQUIRED_SEALED_AWAITING_MANUAL_CORNERS",
                "recorded_at": _now(),
                "claim": {
                    "path": claim_path.resolve().as_posix(),
                    "sha256": _sha256_bytes(
                        _read_stable_regular(claim_path, label="attempt claim")
                    ),
                    "integrity_sha256": claim["integrity"]["sha256"],
                },
                "contract_integrity_sha256": contract["integrity"]["sha256"],
                "action_identity": expected_action,
                "action_snapshot": action_snapshot,
                "capture": {
                    "capture_id": capture["capture_id"],
                    "captured_at": capture["captured_at"],
                    "sidecar_path": sidecar_path.resolve().as_posix(),
                    "sidecar_bytes": len(sidecar_payload),
                    "sidecar_sha256": _sha256_bytes(sidecar_payload),
                    "sidecar_integrity_sha256": capture["integrity"]["sha256"],
                    "photo_path": photo_path.resolve().as_posix(),
                    "photo_bytes": len(photo_payload),
                    "photo_sha256": _sha256_bytes(photo_payload),
                },
                "camera_lock": acquisition_validation["camera_lock"],
                "alignment": acquisition_validation["alignment"],
                "offline_admission_required": True,
                "camera_invocations": camera_invocations,
                "automatic_retry_count": 0,
                "automatic_fallback": False,
                "automatic_chaining": False,
                "hardware_actions_other_than_one_camera_read": False,
            }
        )
    except Exception as error:
        partial_files: dict[str, Any] = {}
        for name, path in (
            ("action_snapshot", snapshot_path),
            ("photo", photo_path),
            ("capture_sidecar", sidecar_path),
        ):
            if path.is_file() and not path.is_symlink():
                payload = _read_stable_regular(path, label=f"partial {name}")
                partial_files[name] = {
                    "path": path.resolve().as_posix(),
                    "bytes": len(payload),
                    "sha256": _sha256_bytes(payload),
                }
        acquisition = _seal(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": ACQUISITION_KIND,
                "slot": slot,
                "attempt": attempt,
                "acquired": False,
                "outcome": "ACQUISITION_REJECTED_FAIL_CLOSED",
                "recorded_at": _now(),
                "claim": {
                    "path": claim_path.resolve().as_posix(),
                    "sha256": _sha256_bytes(
                        _read_stable_regular(claim_path, label="attempt claim")
                    ),
                    "integrity_sha256": claim["integrity"]["sha256"],
                },
                "contract_integrity_sha256": contract["integrity"]["sha256"],
                "action_identity": expected_action,
                "camera_invocations": camera_invocations,
                "automatic_retry_count": 0,
                "automatic_fallback": False,
                "automatic_chaining": False,
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                },
                "partial_evidence_directory": evidence_dir.resolve().as_posix(),
                "partial_evidence": partial_files,
                "capture_metadata_if_validated": (
                    None
                    if capture is None
                    else {
                        "capture_id": capture["capture_id"],
                        "captured_at": capture["captured_at"],
                        "camera": capture.get("camera"),
                        "photo": capture.get("photo"),
                    }
                ),
            }
        )
    _write_exclusive(acquisition_path, acquisition)
    return acquisition


def _deep_validate_acquisition_evidence(
    *,
    output_root: Path,
    slot: str,
    attempt: int,
    acquisition: Mapping[str, Any],
) -> dict[str, Any]:
    """Replay one sealed successful acquisition without using a camera."""

    if acquisition.get("acquired") is not True:
        raise T3CameraCapturePackError("only a successful acquisition can be admitted")
    evidence_dir = (
        Path(output_root).resolve() / "evidence" / f"{slot}-attempt-{attempt:02d}"
    )
    snapshot_path = (evidence_dir / "action-result.json").resolve()
    photo_path = (evidence_dir / "camera.jpg").resolve()
    sidecar_path = (evidence_dir / "camera.capture.json").resolve()
    snapshot_payload = _read_stable_regular(
        snapshot_path, label="action result snapshot"
    )
    photo_payload = _read_stable_regular(photo_path, label="captured photo")
    sidecar_payload = _read_stable_regular(sidecar_path, label="capture sidecar")
    expected_snapshot = {
        "path": snapshot_path.as_posix(),
        "bytes": len(snapshot_payload),
        "sha256": _sha256_bytes(snapshot_payload),
    }
    if acquisition.get("action_snapshot") != expected_snapshot:
        raise T3CameraCapturePackError("acquisition action snapshot binding differs")
    _validate_action_source(slot, snapshot_path)
    capture = camera.validate_capture_evidence(sidecar_path)
    expected_capture = {
        "capture_id": capture["capture_id"],
        "captured_at": capture["captured_at"],
        "sidecar_path": sidecar_path.as_posix(),
        "sidecar_bytes": len(sidecar_payload),
        "sidecar_sha256": _sha256_bytes(sidecar_payload),
        "sidecar_integrity_sha256": capture["integrity"]["sha256"],
        "photo_path": photo_path.as_posix(),
        "photo_bytes": len(photo_payload),
        "photo_sha256": _sha256_bytes(photo_payload),
    }
    if acquisition.get("capture") != expected_capture:
        raise T3CameraCapturePackError("acquisition capture file binding differs")
    validation = _validate_acquired_capture(
        slot=slot,
        capture=capture,
        expected_action=_expected_action_identity(slot),
    )
    if (
        acquisition.get("camera_lock") != validation["camera_lock"]
        or acquisition.get("alignment") != validation["alignment"]
    ):
        raise T3CameraCapturePackError("acquisition camera validation differs")
    return {
        "capture": capture,
        "capture_record": expected_capture,
        "photo_payload": photo_payload,
        "action_snapshot": expected_snapshot,
        **validation,
    }


def _get_or_create_admission(
    *,
    output_root: Path,
    slot: str,
    attempt: int,
    contract: Mapping[str, Any],
    acquisition_path: Path,
    acquisition: Mapping[str, Any],
    panel_corners: str,
) -> tuple[Path, dict[str, Any]]:
    if not isinstance(panel_corners, str) or not panel_corners.strip():
        raise T3CameraCapturePackError(
            "panel corners must be a non-empty TL,TR,BR,BL string"
        )
    path = _admission_path(output_root, slot, attempt).resolve()
    if path.exists():
        loaded_path, loaded = _load_admission(
            output_root=output_root,
            slot=slot,
            attempt=attempt,
            contract_integrity_sha256=str(contract["integrity"]["sha256"]),
            acquisition_path=acquisition_path,
            acquisition=acquisition,
        )
        if loaded.get("panel_corners_tl_tr_br_bl_text") != panel_corners:
            raise T3CameraCapturePackError(
                "admission already claimed with different panel corners"
            )
        return loaded_path, loaded
    admission = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": ADMISSION_KIND,
            "slot": slot,
            "attempt": attempt,
            "claimed_at": _now(),
            "state": "PERMANENTLY_CONSUMED_BEFORE_CORNER_PARSING_AND_ANALYSIS",
            "contract_integrity_sha256": contract["integrity"]["sha256"],
            "acquisition": _sealed_file_binding(
                acquisition_path, acquisition, label=f"{slot} acquisition"
            ),
            "panel_corners_tl_tr_br_bl_text": panel_corners,
            "camera_invocations_during_admit": 0,
            "automatic_retry": False,
            "automatic_fallback": False,
            "automatic_chaining": False,
        }
    )
    _write_exclusive(path, admission)
    return path, admission


def admit_one(
    *,
    slot: str,
    attempt: int,
    output_root: Path,
    panel_corners: str,
) -> dict[str, Any]:
    """Bind corners to one sealed JPEG and perform offline admission once."""

    if slot not in SLOTS:
        raise T3CameraCapturePackError(f"unsupported capture slot {slot!r}")
    if type(attempt) is not int or not 1 <= attempt <= MAXIMUM_ATTEMPTS[slot]:
        raise T3CameraCapturePackError("attempt is outside the frozen slot budget")
    output_root = Path(output_root).resolve()
    _contract_payload, contract = _load_json(
        _contract_path(output_root), label="capture contract"
    )
    _verify_seal(contract, label="capture contract")
    expected_contract = build_contract(mount_id=str(contract["camera"]["mount_id"]))
    if contract != expected_contract:
        raise T3CameraCapturePackError("capture contract differs from current pack")
    claims = _load_claims(
        output_root,
        slot,
        contract_integrity_sha256=str(contract["integrity"]["sha256"]),
    )
    if attempt not in {int(claim["attempt"]) for _path, claim in claims}:
        raise T3CameraCapturePackError(
            f"{slot} attempt {attempt} does not have a frozen acquire claim"
        )
    result_path = _result_path(output_root, slot, attempt).resolve()
    if result_path.exists():
        raise T3CameraCapturePackError(
            f"{slot} attempt {attempt} already has a terminal result"
        )
    acquisition_path, acquisition = _load_acquisition(
        output_root=output_root,
        slot=slot,
        attempt=attempt,
        contract_integrity_sha256=str(contract["integrity"]["sha256"]),
    )
    if acquisition.get("acquired") is not True:
        raise T3CameraCapturePackError("failed acquisition cannot be admitted")
    admission_path, admission = _get_or_create_admission(
        output_root=output_root,
        slot=slot,
        attempt=attempt,
        contract=contract,
        acquisition_path=acquisition_path,
        acquisition=acquisition,
        panel_corners=panel_corners,
    )
    acquisition_binding = _sealed_file_binding(
        acquisition_path, acquisition, label=f"{slot} acquisition"
    )
    admission_binding = _sealed_file_binding(
        admission_path, admission, label=f"{slot} admission claim"
    )
    normalised_corners: list[list[float]] | None = None
    try:
        # This is intentionally after the permanent admission claim.
        normalised_corners = _normalise_panel_corners(panel_corners)
        replay = _deep_validate_acquisition_evidence(
            output_root=output_root,
            slot=slot,
            attempt=attempt,
            acquisition=acquisition,
        )
        evaluation = _evaluate_capture(
            slot=slot,
            capture=replay["capture"],
            photo_payload=replay["photo_payload"],
            panel_corners=normalised_corners,
            expected_action=_expected_action_identity(slot),
        )
        if evaluation["alignment"] != replay["alignment"]:
            raise T3CameraCapturePackError(
                "admission camera alignment differs from acquisition"
            )
        cross_capture_geometry: dict[str, Any] | None = None
        if slot == T3_SLOT:
            white_accepted = _accepted_results(
                output_root,
                WHITE_SLOT,
                contract_integrity_sha256=str(contract["integrity"]["sha256"]),
            )
            if len(white_accepted) != 1:
                raise T3CameraCapturePackError(
                    "T3 admission requires exactly one accepted W3 white reference"
                )
            white_alignment = white_accepted[0]["evaluation"]["alignment"]
            if evaluation["alignment"] != white_alignment:
                raise T3CameraCapturePackError(
                    "T3 camera instance/mount/settings/dimensions differ from white"
                )
            cross_capture_geometry = _corresponding_corner_drift(
                white_accepted[0]["evaluation"]["geometry"],
                evaluation["geometry"],
            )
        result = _seal(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": RESULT_KIND,
                "phase": "OFFLINE_ADMISSION",
                "slot": slot,
                "attempt": attempt,
                "accepted": True,
                "outcome": "ACCEPTED",
                "recorded_at": _now(),
                "claim": acquisition["claim"],
                "acquisition": acquisition_binding,
                "admission": admission_binding,
                "contract_integrity_sha256": contract["integrity"]["sha256"],
                "action_identity": _expected_action_identity(slot),
                "action_snapshot": replay["action_snapshot"],
                "capture": replay["capture_record"],
                "panel_corners_tl_tr_br_bl": normalised_corners,
                "evaluation": evaluation,
                "cross_capture_geometry_to_white": cross_capture_geometry,
                "camera_invocations": 1,
                "camera_invocations_during_admit": 0,
                "automatic_retry_count": 0,
                "automatic_fallback": False,
                "automatic_chaining": False,
                "offline_only_admission": True,
                "hardware_io_performed_during_admit": False,
            }
        )
    except Exception as error:
        result = _seal(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": RESULT_KIND,
                "phase": "OFFLINE_ADMISSION",
                "slot": slot,
                "attempt": attempt,
                "accepted": False,
                "outcome": "REJECTED_FAIL_CLOSED_DO_NOT_AUTO_RETRY",
                "recorded_at": _now(),
                "claim": acquisition["claim"],
                "acquisition": acquisition_binding,
                "admission": admission_binding,
                "contract_integrity_sha256": contract["integrity"]["sha256"],
                "action_identity": _expected_action_identity(slot),
                "panel_corners_tl_tr_br_bl": normalised_corners,
                "camera_invocations": 1,
                "camera_invocations_during_admit": 0,
                "automatic_retry_count": 0,
                "automatic_fallback": False,
                "automatic_chaining": False,
                "offline_only_admission": True,
                "hardware_io_performed_during_admit": False,
                "error": {"type": type(error).__name__, "message": str(error)},
            }
        )
    _write_exclusive(result_path, result)
    return result


def capture_one(
    *,
    slot: str,
    output_root: Path,
    action_result_path: Path,
    mount_id: str,
    panel_corners: str | Any,
    capture_function: CaptureFunction = camera.capture_locked_retained,
) -> dict[str, Any]:
    """Reject the unsafe legacy one-phase API before any camera access."""

    del slot, output_root, action_result_path, mount_id, panel_corners, capture_function
    raise T3CameraCapturePackError(
        "legacy capture is disabled: use acquire, inspect that sealed JPEG, then admit"
    )


def _deep_validate_accepted_result(
    *,
    output_root: Path,
    result: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    slot = result.get("slot")
    if slot not in SLOTS or result.get("accepted") is not True:
        raise T3CameraCapturePackError("bundle input is not an accepted capture")
    attempt = int(result["attempt"])
    acquisition_path, acquisition = _load_acquisition(
        output_root=output_root,
        slot=slot,
        attempt=attempt,
        contract_integrity_sha256=str(contract["integrity"]["sha256"]),
    )
    admission_path, admission = _load_admission(
        output_root=output_root,
        slot=slot,
        attempt=attempt,
        contract_integrity_sha256=str(contract["integrity"]["sha256"]),
        acquisition_path=acquisition_path,
        acquisition=acquisition,
    )
    replay = _deep_validate_acquisition_evidence(
        output_root=output_root,
        slot=slot,
        attempt=attempt,
        acquisition=acquisition,
    )
    panel_corners = _normalise_panel_corners(
        admission["panel_corners_tl_tr_br_bl_text"]
    )
    if result.get("panel_corners_tl_tr_br_bl") != panel_corners:
        raise T3CameraCapturePackError("accepted result panel corners differ")
    if (
        result.get("capture") != replay["capture_record"]
        or result.get("action_snapshot") != replay["action_snapshot"]
    ):
        raise T3CameraCapturePackError("accepted result acquisition replay differs")
    recomputed = _evaluate_capture(
        slot=slot,
        capture=replay["capture"],
        photo_payload=replay["photo_payload"],
        panel_corners=panel_corners,
        expected_action=_expected_action_identity(slot),
    )
    if recomputed != result.get("evaluation"):
        raise T3CameraCapturePackError("accepted capture evaluation differs on replay")
    if slot == WHITE_SLOT and result.get("cross_capture_geometry_to_white") is not None:
        raise T3CameraCapturePackError(
            "white reference must not claim cross-capture geometry"
        )
    return {
        "slot": slot,
        "attempt": attempt,
        "capture_id": replay["capture"]["capture_id"],
        "captured_at": replay["capture"]["captured_at"],
        "photo_sha256": replay["capture_record"]["photo_sha256"],
        "sidecar_sha256": replay["capture_record"]["sidecar_sha256"],
        "sidecar_integrity_sha256": replay["capture"]["integrity"]["sha256"],
        "alignment": recomputed["alignment"],
        "geometry": recomputed["geometry"],
        "illumination": recomputed["illumination"],
    }


def build_bundle(*, output_root: Path) -> dict[str, Any]:
    """Deep-replay and build the immutable four-frame evidence bundle."""

    output_root = Path(output_root).resolve()
    _payload, contract = _load_json(
        _contract_path(output_root), label="capture contract"
    )
    _verify_seal(contract, label="capture contract")
    claims = {
        slot: _load_claims(
            output_root,
            slot,
            contract_integrity_sha256=str(contract["integrity"]["sha256"]),
        )
        for slot in SLOTS
    }
    accepted = {
        slot: _accepted_results(
            output_root,
            slot,
            contract_integrity_sha256=str(contract["integrity"]["sha256"]),
        )
        for slot in SLOTS
    }
    for slot in SLOTS:
        expected_acquisition_paths = [
            _acquisition_path(output_root, slot, int(claim["attempt"])).resolve()
            for _claim_path, claim in claims[slot]
        ]
        if [path.resolve() for path in _acquisition_paths(output_root, slot)] != (
            expected_acquisition_paths
        ):
            raise T3CameraCapturePackError(
                f"{slot} claim/acquisition ledger is not one-to-one"
            )
        expected_admission_paths: list[Path] = []
        expected_result_paths: list[Path] = []
        for _claim_path, claim in claims[slot]:
            attempt = int(claim["attempt"])
            acquisition_path, acquisition = _load_acquisition(
                output_root=output_root,
                slot=slot,
                attempt=attempt,
                contract_integrity_sha256=str(contract["integrity"]["sha256"]),
            )
            admission_path = _admission_path(output_root, slot, attempt).resolve()
            result_path = _result_path(output_root, slot, attempt).resolve()
            if acquisition.get("acquired") is True:
                if not admission_path.is_file() or not result_path.is_file():
                    raise T3CameraCapturePackError(
                        f"{slot} successful acquisition {attempt} is not terminal"
                    )
                expected_admission_paths.append(admission_path)
                expected_result_paths.append(result_path)
                _load_admission(
                    output_root=output_root,
                    slot=slot,
                    attempt=attempt,
                    contract_integrity_sha256=str(contract["integrity"]["sha256"]),
                    acquisition_path=acquisition_path,
                    acquisition=acquisition,
                )
            elif admission_path.exists() or result_path.exists():
                raise T3CameraCapturePackError(
                    f"{slot} failed acquisition {attempt} has forbidden later phases"
                )
        if [path.resolve() for path in _admission_paths(output_root, slot)] != (
            expected_admission_paths
        ) or [path.resolve() for path in _result_paths(output_root, slot)] != (
            expected_result_paths
        ):
            raise T3CameraCapturePackError(
                f"{slot} two-phase terminal ledger contains an orphan"
            )
        if len(accepted[slot]) != REQUIRED_ACCEPTED[slot]:
            raise T3CameraCapturePackError(
                f"{slot} requires exactly {REQUIRED_ACCEPTED[slot]} accepted captures"
            )
    replayed = [
        _deep_validate_accepted_result(
            output_root=output_root, result=result, contract=contract
        )
        for slot in SLOTS
        for result in accepted[slot]
    ]
    white = next(item for item in replayed if item["slot"] == WHITE_SLOT)
    t3_frames = [item for item in replayed if item["slot"] == T3_SLOT]
    if any(item["alignment"] != white["alignment"] for item in t3_frames):
        raise T3CameraCapturePackError(
            "white and T3 captures do not share exact camera/mount/settings/dimensions"
        )
    if len({item["capture_id"] for item in t3_frames}) != 3:
        raise T3CameraCapturePackError("T3 capture IDs are not three distinct values")
    if len({item["photo_sha256"] for item in t3_frames}) != 3:
        raise T3CameraCapturePackError("T3 photo hashes are not three distinct frames")
    if len({item["captured_at"] for item in t3_frames}) != 3:
        raise T3CameraCapturePackError("T3 capture timestamps are not distinct")
    if any(item["captured_at"] <= white["captured_at"] for item in t3_frames):
        raise T3CameraCapturePackError("T3 frames do not follow the white reference")
    white_to_t3 = [
        _corresponding_corner_drift(white["geometry"], item["geometry"])
        for item in t3_frames
    ]
    for result, drift in zip(accepted[T3_SLOT], white_to_t3, strict=True):
        if result.get("cross_capture_geometry_to_white") != drift:
            raise T3CameraCapturePackError(
                "T3 result-to-white geometry drift metadata differs"
            )
    pairwise_geometry = []
    for left, right in itertools.combinations([white, *t3_frames], 2):
        pairwise_geometry.append(
            {
                "left_capture_id": left["capture_id"],
                "right_capture_id": right["capture_id"],
                **_corresponding_corner_drift(left["geometry"], right["geometry"]),
            }
        )
    contract_payload = _read_stable_regular(
        _contract_path(output_root), label="capture contract"
    )
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": BUNDLE_KIND,
            "pack_revision": PACK_REVISION,
            "output_root": output_root.as_posix(),
            "contract": {
                "path": _contract_path(output_root).resolve().as_posix(),
                "bytes": len(contract_payload),
                "sha256": _sha256_bytes(contract_payload),
                "integrity_sha256": contract["integrity"]["sha256"],
            },
            "attempt_counts": {slot: len(claims[slot]) for slot in SLOTS},
            "accepted_counts": {slot: len(accepted[slot]) for slot in SLOTS},
            "white_reference": white,
            "t3_frames": t3_frames,
            "same_exact_camera_mount_settings_and_dimensions": True,
            "per_frame_panel_corners_recorded_independently": True,
            "pairwise_cross_capture_geometry": pairwise_geometry,
            "geometry_fail_closed": True,
            "low_illumination_fail_closed": True,
            "maximum_attempt_bound_respected": True,
            "camera_relative_screening_only": True,
            "absolute_colour_qualification": False,
            "qualified_colour_count": 0,
            "w4_following_boundary": contract["w4_following_boundary"],
            "hardware_io_performed_by_bundle_builder": False,
            "camera_access_performed_by_bundle_builder": False,
            "output_write_contract": "O_EXCL",
        }
    )


def seal_bundle(
    *, output_root: Path, output_path: Path | None = None
) -> dict[str, Any]:
    bundle = build_bundle(output_root=output_root)
    target = (
        Path(output_path)
        if output_path is not None
        else Path(output_root) / "capture-bundle.json"
    )
    _write_exclusive(target, bundle)
    return bundle


def validate_bundle(path: Path) -> dict[str, Any]:
    _payload, actual = _load_json(path, label="capture bundle")
    _verify_seal(actual, label="capture bundle")
    if actual.get("kind") != BUNDLE_KIND:
        raise T3CameraCapturePackError("capture bundle kind differs")
    expected = build_bundle(output_root=Path(str(actual.get("output_root"))))
    if actual != expected:
        raise T3CameraCapturePackError("capture bundle differs from deep replay")
    return actual


def _load_partial_claims(
    output_root: Path,
    slot: str,
    *,
    contract_integrity_sha256: str | None = None,
) -> list[tuple[Path, dict[str, Any]]]:
    loaded: list[tuple[Path, dict[str, Any]]] = []
    for expected_attempt, path in enumerate(_claim_paths(output_root, slot), start=1):
        _payload, root = _load_json(path, label=f"{slot} partial attempt claim")
        _verify_seal(root, label=f"{slot} partial attempt claim")
        if (
            path.name != f"{slot}-attempt-{expected_attempt:02d}.claim.json"
            or root.get("schema_version") != SCHEMA_VERSION
            or root.get("kind") != PARTIAL_CLAIM_KIND
            or root.get("slot") != slot
            or root.get("attempt") != expected_attempt
            or root.get("maximum_attempts") != MAXIMUM_ATTEMPTS[slot]
            or root.get("state") != "PERMANENTLY_CONSUMED_BEFORE_CAMERA_OPEN"
            or root.get("two_phase_state")
            != "PARTIAL_ACQUIRE_CLAIMED_NO_BLOCKS_BOUND"
            or root.get("partial_blocks_bound_during_acquire") is not False
            or root.get("offline_admission_required_after_acquisition") is not True
            or root.get("one_camera_acquisition_maximum") is not True
            or root.get("automatic_retry") is not False
            or root.get("automatic_fallback") is not False
            or root.get("automatic_chaining") is not False
            or "panel_corners_tl_tr_br_bl" in root
            or "partial_blocks_cs1_cs2" in root
        ):
            raise T3CameraCapturePackError(f"{slot} partial attempt claim differs")
        if (
            contract_integrity_sha256 is not None
            and root.get("contract_integrity_sha256")
            != contract_integrity_sha256
        ):
            raise T3CameraCapturePackError(
                f"{slot} partial claim contract binding differs"
            )
        loaded.append((path, root))
    if len(loaded) > MAXIMUM_ATTEMPTS[slot]:
        raise T3CameraCapturePackError(f"{slot} partial claim count exceeds budget")
    return loaded


def _load_partial_acquisition(
    *, output_root: Path, slot: str, attempt: int, contract_integrity_sha256: str
) -> tuple[Path, dict[str, Any]]:
    path = _acquisition_path(output_root, slot, attempt).resolve()
    _payload, root = _load_json(path, label=f"{slot} partial acquisition")
    _verify_seal(root, label=f"{slot} partial acquisition")
    if (
        root.get("schema_version") != SCHEMA_VERSION
        or root.get("kind") != PARTIAL_ACQUISITION_KIND
        or root.get("mode") != PARTIAL_MODE
        or root.get("slot") != slot
        or root.get("attempt") != attempt
        or root.get("contract_integrity_sha256") != contract_integrity_sha256
        or root.get("automatic_retry_count") != 0
        or root.get("automatic_fallback") is not False
        or root.get("automatic_chaining") is not False
        or root.get("camera_invocations") not in (0, 1)
        or "partial_blocks_cs1_cs2" in root
        or "evaluation" in root
    ):
        raise T3CameraCapturePackError(f"{slot} partial acquisition identity differs")
    _validate_result_claim(output_root=output_root, result=root, slot=slot)
    if root.get("acquired") is True:
        if (
            root.get("outcome")
            != "ACQUIRED_PARTIAL_SEALED_AWAITING_MANUAL_BLOCKS"
            or root.get("camera_invocations") != 1
            or root.get("offline_admission_required") is not True
            or not isinstance(root.get("capture"), Mapping)
            or not isinstance(root.get("action_snapshot"), Mapping)
        ):
            raise T3CameraCapturePackError(
                f"{slot} successful partial acquisition state differs"
            )
    elif root.get("acquired") is False:
        if root.get("outcome") != "PARTIAL_ACQUISITION_REJECTED_FAIL_CLOSED":
            raise T3CameraCapturePackError(
                f"{slot} failed partial acquisition state differs"
            )
    else:
        raise T3CameraCapturePackError(f"{slot} partial acquisition flag differs")
    return path, root


def _load_partial_admission(
    *,
    output_root: Path,
    slot: str,
    attempt: int,
    contract_integrity_sha256: str,
    acquisition_path: Path,
    acquisition: Mapping[str, Any],
) -> tuple[Path, dict[str, Any]]:
    path = _admission_path(output_root, slot, attempt).resolve()
    _payload, root = _load_json(path, label=f"{slot} partial admission claim")
    _verify_seal(root, label=f"{slot} partial admission claim")
    blocks_text = root.get("partial_blocks_cs1_cs2_text")
    if (
        root.get("schema_version") != SCHEMA_VERSION
        or root.get("kind") != PARTIAL_ADMISSION_KIND
        or root.get("mode") != PARTIAL_MODE
        or root.get("slot") != slot
        or root.get("attempt") != attempt
        or root.get("contract_integrity_sha256") != contract_integrity_sha256
        or root.get("state")
        != "PERMANENTLY_CONSUMED_BEFORE_BLOCK_PARSING_AND_ANALYSIS"
        or not isinstance(blocks_text, str)
        or not blocks_text.strip()
        or root.get("automatic_retry") is not False
        or root.get("automatic_fallback") is not False
        or root.get("automatic_chaining") is not False
        or root.get("camera_invocations_during_admit") != 0
        or "panel_corners_tl_tr_br_bl_text" in root
    ):
        raise T3CameraCapturePackError(f"{slot} partial admission claim differs")
    expected_acquisition = _sealed_file_binding(
        acquisition_path, acquisition, label=f"{slot} partial acquisition"
    )
    if root.get("acquisition") != expected_acquisition:
        raise T3CameraCapturePackError(
            f"{slot} partial admission-to-acquisition binding differs"
        )
    return path, root


def _accepted_partial_results(
    output_root: Path,
    slot: str,
    *,
    contract_integrity_sha256: str | None = None,
) -> list[dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    seen_attempts: set[int] = set()
    for path in _result_paths(output_root, slot):
        _payload, root = _load_json(path, label=f"{slot} partial result")
        _verify_seal(root, label=f"{slot} partial result")
        attempt = root.get("attempt")
        if (
            type(attempt) is not int
            or path.name != f"{slot}-attempt-{attempt:02d}.result.json"
            or root.get("schema_version") != SCHEMA_VERSION
            or root.get("kind") != PARTIAL_RESULT_KIND
            or root.get("mode") != PARTIAL_MODE
            or root.get("slot") != slot
            or attempt in seen_attempts
            or not 1 <= attempt <= MAXIMUM_ATTEMPTS[slot]
            or root.get("phase") != "OFFLINE_PARTIAL_ADMISSION"
            or root.get("automatic_retry_count") != 0
            or root.get("automatic_fallback") is not False
            or root.get("automatic_chaining") is not False
            or root.get("camera_invocations") != 1
            or root.get("camera_invocations_during_admit") != 0
        ):
            raise T3CameraCapturePackError(f"{slot} partial result identity differs")
        seen_attempts.add(attempt)
        if (
            contract_integrity_sha256 is not None
            and root.get("contract_integrity_sha256")
            != contract_integrity_sha256
        ):
            raise T3CameraCapturePackError(
                f"{slot} partial result contract binding differs"
            )
        _validate_result_claim(output_root=output_root, result=root, slot=slot)
        acquisition_path, acquisition = _load_partial_acquisition(
            output_root=output_root,
            slot=slot,
            attempt=attempt,
            contract_integrity_sha256=str(root["contract_integrity_sha256"]),
        )
        if acquisition.get("acquired") is not True:
            raise T3CameraCapturePackError(
                f"{slot} partial result is bound to a failed acquisition"
            )
        admission_path, admission = _load_partial_admission(
            output_root=output_root,
            slot=slot,
            attempt=attempt,
            contract_integrity_sha256=str(root["contract_integrity_sha256"]),
            acquisition_path=acquisition_path,
            acquisition=acquisition,
        )
        if root.get("acquisition") != _sealed_file_binding(
            acquisition_path, acquisition, label=f"{slot} partial acquisition"
        ) or root.get("admission") != _sealed_file_binding(
            admission_path, admission, label=f"{slot} partial admission claim"
        ):
            raise T3CameraCapturePackError(
                f"{slot} partial result two-phase binding differs"
            )
        if root.get("accepted") is True:
            if root.get("outcome") != "PARTIAL_ACCEPTED":
                raise T3CameraCapturePackError(
                    f"{slot} accepted partial result outcome differs"
                )
            accepted.append(root)
        elif root.get("outcome") != "PARTIAL_REJECTED_FAIL_CLOSED_DO_NOT_AUTO_RETRY":
            raise T3CameraCapturePackError(f"{slot} rejected partial result differs")
    return accepted


def _validate_partial_acquired_capture(
    *, slot: str, capture: Mapping[str, Any], expected_action: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate the exact camera lock while requiring truthful partial coverage."""

    try:
        camera_lock = frozen._validate_fixed_capture(  # noqa: SLF001
            capture, expected_coverage_scope=camera.COVERAGE_PARTIAL
        )
    except frozen.RawP16PhotoAnalysisError as error:
        raise T3CameraCapturePackError(
            f"exact README partial camera lock rejected: {error}"
        ) from error
    for field in (
        "campaign_id",
        "test_id",
        "contract_id",
        "firmware_sha256",
        "action_id",
        "descriptor_id",
        "role",
        "frame_sha256",
    ):
        if capture.get(field) != expected_action[field]:
            raise T3CameraCapturePackError(
                f"partial capture {field} differs from exact {slot} action"
            )
    if capture.get("capture_binding") != camera.BINDING_LOCKED_RETAINED:
        raise T3CameraCapturePackError("partial capture is not locked-retained")
    alignment = _alignment(capture)
    if (
        alignment["photo_width"] != PHOTO_WIDTH
        or alignment["photo_height"] != PHOTO_HEIGHT
    ):
        raise T3CameraCapturePackError("partial capture is not exact 4000x3000")
    return {"camera_lock": camera_lock, "alignment": alignment}


def _partial_sample_gate(
    *, slot: str, photo_payload: bytes, partial_blocks: Mapping[str, Any]
) -> dict[str, Any]:
    try:
        rgb = geometry.base._decode_rgb(photo_payload)  # noqa: SLF001
        if rgb.shape[1] != PHOTO_WIDTH or rgb.shape[0] != PHOTO_HEIGHT:
            raise T3CameraCapturePackError("partial JPEG is not exact 4000x3000")
        homographies, geometry_report = (
            geometry._fit_partial_dual_controller_blocks(  # noqa: SLF001
                partial_blocks,
                photo_width=rgb.shape[1],
                photo_height=rgb.shape[0],
            )
        )
        cells = [
            cell
            for cell in geometry._all_logical_cells()  # noqa: SLF001
            if cell["row"] in PARTIAL_SELECTED_ROWS
        ]
        sampled = [
            geometry.base._sample_cell(  # noqa: SLF001
                rgb,
                homographies[f"CS{cell['controller'] + 1}"],
                cell,
            )
            for cell in cells
        ]
    except geometry.CrossoverPhotoAnalysisError as error:
        raise T3CameraCapturePackError(
            f"partial capture geometry rejected: {error}"
        ) from error
    if len(sampled) != PARTIAL_SELECTED_CELL_COUNT:
        raise T3CameraCapturePackError("partial geometry did not produce 48 cells")
    counts: dict[tuple[int, int], int] = {}
    for item in sampled:
        key = (int(item["controller"]), int(item["code"]))
        counts[key] = counts.get(key, 0) + 1
    if any(counts.get((controller, code)) != 3 for controller in (0, 1) for code in range(8)):
        raise T3CameraCapturePackError(
            "partial geometry does not contain three samples per controller/code"
        )
    if slot == WHITE_SLOT:
        light_samples = sampled
        light_guard = "ALL_48_SELECTED_W3_WHITE_CELLS"
    elif slot == T3_SLOT:
        light_samples = [
            item for item in sampled if int(item["code"]) == EXPECTED_T3_WHITE_CODE
        ]
        light_guard = "T3_CODE_3_SIX_SELECTED_POSITIONS"
        if len(light_samples) != PARTIAL_T3_LIGHT_GUARD_SAMPLES:
            raise T3CameraCapturePackError(
                "partial T3 white-code guard does not have six samples"
            )
    else:
        raise T3CameraCapturePackError(f"unsupported partial slot {slot!r}")
    lstars = [
        float(item["camera_relative_lab_d65_from_rgb_median"][0])
        for item in light_samples
    ]
    minimum = min(lstars)
    if minimum < WHITE_REFERENCE_MIN_LSTAR:
        raise T3CameraCapturePackError(
            "partial low illumination rejected: minimum local white L* "
            f"{minimum:.6f} is below {WHITE_REFERENCE_MIN_LSTAR:.1f}"
        )
    return {
        "geometry": geometry_report,
        "illumination": {
            "guard": light_guard,
            "sample_count": len(lstars),
            "minimum_lstar": round(minimum, 6),
            "median_lstar": round(float(statistics.median(lstars)), 6),
            "minimum_required_lstar": WHITE_REFERENCE_MIN_LSTAR,
            "side_specific_white_normalization_required": True,
            "raw_cross_side_rgb_equality_gate": False,
            "passed": True,
        },
    }


def _evaluate_partial_capture(
    *,
    slot: str,
    capture: Mapping[str, Any],
    photo_payload: bytes,
    partial_blocks: Mapping[str, Any],
    expected_action: Mapping[str, Any],
) -> dict[str, Any]:
    validation = _validate_partial_acquired_capture(
        slot=slot, capture=capture, expected_action=expected_action
    )
    return {
        **validation,
        **_partial_sample_gate(
            slot=slot,
            photo_payload=photo_payload,
            partial_blocks=partial_blocks,
        ),
        "evidence_scope": {
            "mode": PARTIAL_MODE,
            "formal_full_panel_evidence": False,
            "full_panel_geometry_evaluated": False,
            "profile_following_decision_earned": False,
            "outside_roi": "NOT_EVALUATED_OUTSIDE_SELECTED_ROI",
        },
    }


def _partial_corresponding_block_drift(
    first_geometry: Mapping[str, Any], second_geometry: Mapping[str, Any]
) -> dict[str, Any]:
    first = first_geometry.get("supplied_block_corners_tl_tr_br_bl")
    second = second_geometry.get("supplied_block_corners_tl_tr_br_bl")
    if (
        not isinstance(first, Mapping)
        or not isinstance(second, Mapping)
        or set(first) != {"CS1", "CS2"}
        or set(second) != {"CS1", "CS2"}
    ):
        raise T3CameraCapturePackError("partial block drift metadata differs")
    labels: list[str] = []
    distances: list[float] = []
    for controller in ("CS1", "CS2"):
        left = first[controller]
        right = second[controller]
        if (
            not isinstance(left, list)
            or not isinstance(right, list)
            or len(left) != 4
            or len(right) != 4
            or any(
                not isinstance(row, list) or len(row) != 2
                for row in (*left, *right)
            )
        ):
            raise T3CameraCapturePackError("partial block corner metadata differs")
        for index, (a, b) in enumerate(zip(left, right, strict=True)):
            labels.append(f"{controller}:{('TL', 'TR', 'BR', 'BL')[index]}")
            distances.append(
                math.dist(
                    [float(component) for component in a],
                    [float(component) for component in b],
                )
            )
    maximum = max(distances)
    rms = math.sqrt(sum(value * value for value in distances) / len(distances))
    if (
        maximum > PARTIAL_MAXIMUM_CORNER_DRIFT_PX
        or rms > PARTIAL_MAXIMUM_CORNER_RMS_DRIFT_PX
    ):
        raise T3CameraCapturePackError(
            "partial cross-capture block drift rejected: "
            f"rms={rms:.6f}px max={maximum:.6f}px"
        )
    return {
        "labels": labels,
        "corresponding_corner_distances_px": [
            round(float(value), 6) for value in distances
        ],
        "rms_corresponding_corner_drift_px": round(float(rms), 6),
        "maximum_corresponding_corner_drift_px": round(float(maximum), 6),
        "maximum_allowed_rms_px": PARTIAL_MAXIMUM_CORNER_RMS_DRIFT_PX,
        "maximum_allowed_px": PARTIAL_MAXIMUM_CORNER_DRIFT_PX,
        "passed": True,
    }


def _claim_partial_attempt(
    *,
    output_root: Path,
    slot: str,
    contract: Mapping[str, Any],
    action_path: Path,
    action_payload: bytes,
) -> tuple[int, Path, dict[str, Any]]:
    existing = _load_partial_claims(
        output_root,
        slot,
        contract_integrity_sha256=str(contract["integrity"]["sha256"]),
    )
    maximum = MAXIMUM_ATTEMPTS[slot]
    if len(existing) >= maximum:
        raise T3CameraCapturePackError(
            f"{slot} partial maximum attempt budget {maximum} is exhausted"
        )
    attempt = len(existing) + 1
    claim_path = (
        Path(output_root) / "claims" / f"{slot}-attempt-{attempt:02d}.claim.json"
    )
    claim = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": PARTIAL_CLAIM_KIND,
            "mode": PARTIAL_MODE,
            "slot": slot,
            "attempt": attempt,
            "maximum_attempts": maximum,
            "claimed_at": _now(),
            "contract_integrity_sha256": contract["integrity"]["sha256"],
            "action_source": {
                "path": Path(action_path).resolve().as_posix(),
                "bytes": len(action_payload),
                "sha256": _sha256_bytes(action_payload),
            },
            "state": "PERMANENTLY_CONSUMED_BEFORE_CAMERA_OPEN",
            "two_phase_state": "PARTIAL_ACQUIRE_CLAIMED_NO_BLOCKS_BOUND",
            "partial_blocks_bound_during_acquire": False,
            "offline_admission_required_after_acquisition": True,
            "one_camera_acquisition_maximum": True,
            "automatic_retry": False,
            "automatic_fallback": False,
            "automatic_chaining": False,
        }
    )
    _write_exclusive(claim_path, claim)
    return attempt, claim_path, claim


def acquire_partial_one(
    *,
    slot: str,
    output_root: Path,
    action_result_path: Path,
    mount_id: str,
    capture_function: CaptureFunction = camera.capture_locked_retained,
) -> dict[str, Any]:
    """Acquire one truthful partial-panel frame; perform no ROI admission."""

    if slot not in SLOTS:
        raise T3CameraCapturePackError(f"unsupported partial slot {slot!r}")
    output_root = Path(output_root).resolve()
    action_result_path = Path(action_result_path).resolve()
    _validate_action_source(slot, action_result_path, partial=True)
    expected_action = _expected_action_identity(slot, partial=True)
    contract = ensure_partial_contract(output_root=output_root, mount_id=mount_id)
    contract_sha = str(contract["integrity"]["sha256"])
    accepted = _accepted_partial_results(
        output_root, slot, contract_integrity_sha256=contract_sha
    )
    if len(accepted) >= REQUIRED_ACCEPTED[slot]:
        raise T3CameraCapturePackError(
            f"{slot} already has required accepted partial captures"
        )
    white_accepted = _accepted_partial_results(
        output_root, WHITE_SLOT, contract_integrity_sha256=contract_sha
    )
    if slot == T3_SLOT and len(white_accepted) != 1:
        raise T3CameraCapturePackError(
            "partial T3 acquisition requires exactly one accepted partial W3 white"
        )
    for _claim_path, claim in _load_partial_claims(
        output_root, slot, contract_integrity_sha256=contract_sha
    ):
        prior_attempt = int(claim["attempt"])
        acquisition_path = _acquisition_path(output_root, slot, prior_attempt)
        result_path = _result_path(output_root, slot, prior_attempt)
        if not acquisition_path.is_file():
            raise T3CameraCapturePackError(
                f"{slot} partial attempt {prior_attempt} has unresolved claim-only state"
            )
        if not result_path.exists():
            _path, acquisition = _load_partial_acquisition(
                output_root=output_root,
                slot=slot,
                attempt=prior_attempt,
                contract_integrity_sha256=contract_sha,
            )
            if acquisition.get("acquired") is True:
                raise T3CameraCapturePackError(
                    f"{slot} partial attempt {prior_attempt} awaits offline admission"
                )
    action_payload = _read_stable_regular(
        action_result_path, label=f"{slot} partial action result"
    )
    attempt, claim_path, claim = _claim_partial_attempt(
        output_root=output_root,
        slot=slot,
        contract=contract,
        action_path=action_result_path,
        action_payload=action_payload,
    )
    evidence_dir = output_root / "evidence" / f"{slot}-attempt-{attempt:02d}"
    snapshot_path = evidence_dir / "action-result.json"
    photo_path = evidence_dir / "camera.jpg"
    sidecar_path = evidence_dir / "camera.capture.json"
    acquisition_path = _acquisition_path(output_root, slot, attempt)
    camera_invocations = 0
    capture: dict[str, Any] | None = None
    try:
        action_snapshot = _copy_exclusive(action_result_path, snapshot_path)
        camera_invocations = 1
        capture = capture_function(
            action_result_path=snapshot_path,
            photo_path=photo_path,
            sidecar_path=sidecar_path,
            camera_id=camera.TARGET_CAMERA_LOGICAL_ID,
            camera_instance_id=None,
            camera_index=None,
            mount_id=contract["camera"]["mount_id"],
            coverage_scope=camera.COVERAGE_PARTIAL,
            coverage_note=(
                "both controller top-three-row ROIs only; full panel not evaluated"
            ),
            requested_settings=CAMERA_PROFILE,
            warmup_frames=WARMUP_FRAMES,
            jpeg_quality=JPEG_QUALITY,
            require_all_setting_writes=True,
            automated_verdict="INCONCLUSIVE",
            assessment_confidence="low",
            limitations=(
                "partial dual-controller 3x8 screening only",
                "outside selected rows 0..2 is not evaluated",
                "no formal full-panel or profile-following claim",
            ),
            analysis_source="t3-partial-dual-3x8-acquisition-v1",
        )
        capture = camera.validate_capture_evidence(sidecar_path)
        photo_payload = _read_stable_regular(photo_path, label="partial captured photo")
        validation = _validate_partial_acquired_capture(
            slot=slot, capture=capture, expected_action=expected_action
        )
        sidecar_payload = _read_stable_regular(
            sidecar_path, label="partial capture sidecar"
        )
        acquisition = _seal(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": PARTIAL_ACQUISITION_KIND,
                "mode": PARTIAL_MODE,
                "slot": slot,
                "attempt": attempt,
                "acquired": True,
                "outcome": "ACQUIRED_PARTIAL_SEALED_AWAITING_MANUAL_BLOCKS",
                "recorded_at": _now(),
                "claim": _sealed_file_binding(
                    claim_path, claim, label=f"{slot} partial attempt claim"
                ),
                "contract_integrity_sha256": contract["integrity"]["sha256"],
                "action_identity": expected_action,
                "action_snapshot": action_snapshot,
                "capture": {
                    "capture_id": capture["capture_id"],
                    "captured_at": capture["captured_at"],
                    "sidecar_path": sidecar_path.resolve().as_posix(),
                    "sidecar_bytes": len(sidecar_payload),
                    "sidecar_sha256": _sha256_bytes(sidecar_payload),
                    "sidecar_integrity_sha256": capture["integrity"]["sha256"],
                    "photo_path": photo_path.resolve().as_posix(),
                    "photo_bytes": len(photo_payload),
                    "photo_sha256": _sha256_bytes(photo_payload),
                },
                "camera_lock": validation["camera_lock"],
                "alignment": validation["alignment"],
                "offline_admission_required": True,
                "camera_invocations": 1,
                "automatic_retry_count": 0,
                "automatic_fallback": False,
                "automatic_chaining": False,
                "hardware_actions_other_than_one_camera_read": False,
                "formal_full_panel_evidence": False,
            }
        )
    except Exception as error:
        partial_files: dict[str, Any] = {}
        for name, path in (
            ("action_snapshot", snapshot_path),
            ("photo", photo_path),
            ("capture_sidecar", sidecar_path),
        ):
            if path.is_file() and not path.is_symlink():
                payload = _read_stable_regular(path, label=f"partial {name}")
                partial_files[name] = {
                    "path": path.resolve().as_posix(),
                    "bytes": len(payload),
                    "sha256": _sha256_bytes(payload),
                }
        acquisition = _seal(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": PARTIAL_ACQUISITION_KIND,
                "mode": PARTIAL_MODE,
                "slot": slot,
                "attempt": attempt,
                "acquired": False,
                "outcome": "PARTIAL_ACQUISITION_REJECTED_FAIL_CLOSED",
                "recorded_at": _now(),
                "claim": _sealed_file_binding(
                    claim_path, claim, label=f"{slot} partial attempt claim"
                ),
                "contract_integrity_sha256": contract["integrity"]["sha256"],
                "action_identity": expected_action,
                "camera_invocations": camera_invocations,
                "automatic_retry_count": 0,
                "automatic_fallback": False,
                "automatic_chaining": False,
                "error": {"type": type(error).__name__, "message": str(error)},
                "partial_evidence_directory": evidence_dir.resolve().as_posix(),
                "partial_evidence": partial_files,
                "capture_metadata_if_validated": (
                    None
                    if capture is None
                    else {
                        "capture_id": capture["capture_id"],
                        "captured_at": capture["captured_at"],
                        "camera": capture.get("camera"),
                        "photo": capture.get("photo"),
                    }
                ),
                "formal_full_panel_evidence": False,
            }
        )
    _write_exclusive(acquisition_path, acquisition)
    return acquisition


def _deep_validate_partial_acquisition_evidence(
    *,
    output_root: Path,
    slot: str,
    attempt: int,
    acquisition: Mapping[str, Any],
) -> dict[str, Any]:
    """Replay one sealed partial acquisition without opening a camera."""

    if acquisition.get("acquired") is not True:
        raise T3CameraCapturePackError(
            "only a successful partial acquisition can be admitted"
        )
    evidence_dir = (
        Path(output_root).resolve() / "evidence" / f"{slot}-attempt-{attempt:02d}"
    )
    snapshot_path = (evidence_dir / "action-result.json").resolve()
    photo_path = (evidence_dir / "camera.jpg").resolve()
    sidecar_path = (evidence_dir / "camera.capture.json").resolve()
    snapshot_payload = _read_stable_regular(
        snapshot_path, label="partial action result snapshot"
    )
    photo_payload = _read_stable_regular(photo_path, label="partial captured photo")
    sidecar_payload = _read_stable_regular(
        sidecar_path, label="partial capture sidecar"
    )
    expected_snapshot = {
        "path": snapshot_path.as_posix(),
        "bytes": len(snapshot_payload),
        "sha256": _sha256_bytes(snapshot_payload),
    }
    if acquisition.get("action_snapshot") != expected_snapshot:
        raise T3CameraCapturePackError(
            "partial acquisition action snapshot binding differs"
        )
    _validate_action_source(slot, snapshot_path, partial=True)
    capture = camera.validate_capture_evidence(sidecar_path)
    expected_capture = {
        "capture_id": capture["capture_id"],
        "captured_at": capture["captured_at"],
        "sidecar_path": sidecar_path.as_posix(),
        "sidecar_bytes": len(sidecar_payload),
        "sidecar_sha256": _sha256_bytes(sidecar_payload),
        "sidecar_integrity_sha256": capture["integrity"]["sha256"],
        "photo_path": photo_path.as_posix(),
        "photo_bytes": len(photo_payload),
        "photo_sha256": _sha256_bytes(photo_payload),
    }
    if acquisition.get("capture") != expected_capture:
        raise T3CameraCapturePackError(
            "partial acquisition capture file binding differs"
        )
    validation = _validate_partial_acquired_capture(
        slot=slot,
        capture=capture,
        expected_action=_expected_action_identity(slot, partial=True),
    )
    if (
        acquisition.get("camera_lock") != validation["camera_lock"]
        or acquisition.get("alignment") != validation["alignment"]
    ):
        raise T3CameraCapturePackError(
            "partial acquisition camera validation differs"
        )
    return {
        "capture": capture,
        "capture_record": expected_capture,
        "photo_payload": photo_payload,
        "action_snapshot": expected_snapshot,
        **validation,
    }


def _get_or_create_partial_admission(
    *,
    output_root: Path,
    slot: str,
    attempt: int,
    contract: Mapping[str, Any],
    acquisition_path: Path,
    acquisition: Mapping[str, Any],
    partial_blocks: str,
) -> tuple[Path, dict[str, Any]]:
    if not isinstance(partial_blocks, str) or not partial_blocks.strip():
        raise T3CameraCapturePackError(
            "partial blocks must be a non-empty strict JSON object"
        )
    path = _admission_path(output_root, slot, attempt).resolve()
    if path.exists():
        loaded_path, loaded = _load_partial_admission(
            output_root=output_root,
            slot=slot,
            attempt=attempt,
            contract_integrity_sha256=str(contract["integrity"]["sha256"]),
            acquisition_path=acquisition_path,
            acquisition=acquisition,
        )
        if loaded.get("partial_blocks_cs1_cs2_text") != partial_blocks:
            raise T3CameraCapturePackError(
                "partial admission already claimed with different blocks"
            )
        return loaded_path, loaded
    admission = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": PARTIAL_ADMISSION_KIND,
            "mode": PARTIAL_MODE,
            "slot": slot,
            "attempt": attempt,
            "claimed_at": _now(),
            "state": "PERMANENTLY_CONSUMED_BEFORE_BLOCK_PARSING_AND_ANALYSIS",
            "contract_integrity_sha256": contract["integrity"]["sha256"],
            "acquisition": _sealed_file_binding(
                acquisition_path,
                acquisition,
                label=f"{slot} partial acquisition",
            ),
            "partial_blocks_cs1_cs2_text": partial_blocks,
            "camera_invocations_during_admit": 0,
            "automatic_retry": False,
            "automatic_fallback": False,
            "automatic_chaining": False,
        }
    )
    _write_exclusive(path, admission)
    return path, admission


def admit_partial_one(
    *,
    slot: str,
    attempt: int,
    output_root: Path,
    partial_blocks: str,
) -> dict[str, Any]:
    """Bind dual 3x8 blocks to one sealed JPEG and admit it offline once."""

    if slot not in SLOTS:
        raise T3CameraCapturePackError(f"unsupported partial slot {slot!r}")
    if type(attempt) is not int or not 1 <= attempt <= MAXIMUM_ATTEMPTS[slot]:
        raise T3CameraCapturePackError(
            "partial attempt is outside the frozen slot budget"
        )
    output_root = Path(output_root).resolve()
    _contract_payload, contract = _load_json(
        _contract_path(output_root), label="partial capture contract"
    )
    _verify_seal(contract, label="partial capture contract")
    if contract.get("kind") != PARTIAL_CONTRACT_KIND:
        raise T3CameraCapturePackError("capture contract is not partial mode")
    expected_contract = build_partial_contract(
        mount_id=str(contract["camera"]["mount_id"])
    )
    if contract != expected_contract:
        raise T3CameraCapturePackError(
            "partial capture contract differs from current pack"
        )
    claims = _load_partial_claims(
        output_root,
        slot,
        contract_integrity_sha256=str(contract["integrity"]["sha256"]),
    )
    if attempt not in {int(claim["attempt"]) for _path, claim in claims}:
        raise T3CameraCapturePackError(
            f"{slot} partial attempt {attempt} has no frozen acquire claim"
        )
    result_path = _result_path(output_root, slot, attempt).resolve()
    if result_path.exists():
        raise T3CameraCapturePackError(
            f"{slot} partial attempt {attempt} already has a terminal result"
        )
    acquisition_path, acquisition = _load_partial_acquisition(
        output_root=output_root,
        slot=slot,
        attempt=attempt,
        contract_integrity_sha256=str(contract["integrity"]["sha256"]),
    )
    if acquisition.get("acquired") is not True:
        raise T3CameraCapturePackError("failed partial acquisition cannot be admitted")
    admission_path, admission = _get_or_create_partial_admission(
        output_root=output_root,
        slot=slot,
        attempt=attempt,
        contract=contract,
        acquisition_path=acquisition_path,
        acquisition=acquisition,
        partial_blocks=partial_blocks,
    )
    acquisition_binding = _sealed_file_binding(
        acquisition_path, acquisition, label=f"{slot} partial acquisition"
    )
    admission_binding = _sealed_file_binding(
        admission_path, admission, label=f"{slot} partial admission claim"
    )
    normalised_blocks: dict[str, list[list[float]]] | None = None
    try:
        # Parsing is intentionally after the permanent O_EXCL admission claim.
        normalised_blocks = _normalise_partial_blocks(partial_blocks)
        replay = _deep_validate_partial_acquisition_evidence(
            output_root=output_root,
            slot=slot,
            attempt=attempt,
            acquisition=acquisition,
        )
        evaluation = _evaluate_partial_capture(
            slot=slot,
            capture=replay["capture"],
            photo_payload=replay["photo_payload"],
            partial_blocks=normalised_blocks,
            expected_action=_expected_action_identity(slot, partial=True),
        )
        if evaluation["alignment"] != replay["alignment"]:
            raise T3CameraCapturePackError(
                "partial admission camera alignment differs from acquisition"
            )
        cross_capture_geometry: dict[str, Any] | None = None
        if slot == T3_SLOT:
            white_accepted = _accepted_partial_results(
                output_root,
                WHITE_SLOT,
                contract_integrity_sha256=str(contract["integrity"]["sha256"]),
            )
            if len(white_accepted) != 1:
                raise T3CameraCapturePackError(
                    "partial T3 admission requires one accepted W3 white reference"
                )
            white_evaluation = white_accepted[0]["evaluation"]
            if evaluation["alignment"] != white_evaluation["alignment"]:
                raise T3CameraCapturePackError(
                    "partial T3 camera/mount/settings/dimensions differ from white"
                )
            cross_capture_geometry = _partial_corresponding_block_drift(
                white_evaluation["geometry"], evaluation["geometry"]
            )
        result = _seal(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": PARTIAL_RESULT_KIND,
                "mode": PARTIAL_MODE,
                "phase": "OFFLINE_PARTIAL_ADMISSION",
                "slot": slot,
                "attempt": attempt,
                "accepted": True,
                "outcome": "PARTIAL_ACCEPTED",
                "recorded_at": _now(),
                "claim": acquisition["claim"],
                "acquisition": acquisition_binding,
                "admission": admission_binding,
                "contract_integrity_sha256": contract["integrity"]["sha256"],
                "action_identity": _expected_action_identity(slot, partial=True),
                "action_snapshot": replay["action_snapshot"],
                "capture": replay["capture_record"],
                "partial_blocks_cs1_cs2": normalised_blocks,
                "evaluation": evaluation,
                "cross_capture_geometry_to_white": cross_capture_geometry,
                "camera_invocations": 1,
                "camera_invocations_during_admit": 0,
                "automatic_retry_count": 0,
                "automatic_fallback": False,
                "automatic_chaining": False,
                "offline_only_admission": True,
                "hardware_io_performed_during_admit": False,
                "formal_full_panel_evidence": False,
                "profile_following_decision_earned": False,
                "outside_roi": "NOT_EVALUATED_OUTSIDE_SELECTED_ROI",
            }
        )
    except Exception as error:
        result = _seal(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": PARTIAL_RESULT_KIND,
                "mode": PARTIAL_MODE,
                "phase": "OFFLINE_PARTIAL_ADMISSION",
                "slot": slot,
                "attempt": attempt,
                "accepted": False,
                "outcome": "PARTIAL_REJECTED_FAIL_CLOSED_DO_NOT_AUTO_RETRY",
                "recorded_at": _now(),
                "claim": acquisition["claim"],
                "acquisition": acquisition_binding,
                "admission": admission_binding,
                "contract_integrity_sha256": contract["integrity"]["sha256"],
                "action_identity": _expected_action_identity(slot, partial=True),
                "partial_blocks_cs1_cs2": normalised_blocks,
                "camera_invocations": 1,
                "camera_invocations_during_admit": 0,
                "automatic_retry_count": 0,
                "automatic_fallback": False,
                "automatic_chaining": False,
                "offline_only_admission": True,
                "hardware_io_performed_during_admit": False,
                "formal_full_panel_evidence": False,
                "profile_following_decision_earned": False,
                "outside_roi": "NOT_EVALUATED_OUTSIDE_SELECTED_ROI",
                "error": {"type": type(error).__name__, "message": str(error)},
            }
        )
    _write_exclusive(result_path, result)
    return result


def _deep_validate_partial_accepted_result(
    *,
    output_root: Path,
    result: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    slot = result.get("slot")
    if slot not in SLOTS or result.get("accepted") is not True:
        raise T3CameraCapturePackError(
            "partial bundle input is not an accepted capture"
        )
    attempt = int(result["attempt"])
    acquisition_path, acquisition = _load_partial_acquisition(
        output_root=output_root,
        slot=slot,
        attempt=attempt,
        contract_integrity_sha256=str(contract["integrity"]["sha256"]),
    )
    admission_path, admission = _load_partial_admission(
        output_root=output_root,
        slot=slot,
        attempt=attempt,
        contract_integrity_sha256=str(contract["integrity"]["sha256"]),
        acquisition_path=acquisition_path,
        acquisition=acquisition,
    )
    replay = _deep_validate_partial_acquisition_evidence(
        output_root=output_root,
        slot=slot,
        attempt=attempt,
        acquisition=acquisition,
    )
    blocks = _normalise_partial_blocks(admission["partial_blocks_cs1_cs2_text"])
    if result.get("partial_blocks_cs1_cs2") != blocks:
        raise T3CameraCapturePackError("accepted partial result blocks differ")
    if (
        result.get("capture") != replay["capture_record"]
        or result.get("action_snapshot") != replay["action_snapshot"]
    ):
        raise T3CameraCapturePackError(
            "accepted partial result acquisition replay differs"
        )
    recomputed = _evaluate_partial_capture(
        slot=slot,
        capture=replay["capture"],
        photo_payload=replay["photo_payload"],
        partial_blocks=blocks,
        expected_action=_expected_action_identity(slot, partial=True),
    )
    if recomputed != result.get("evaluation"):
        raise T3CameraCapturePackError(
            "accepted partial evaluation differs on replay"
        )
    if (
        result.get("formal_full_panel_evidence") is not False
        or result.get("profile_following_decision_earned") is not False
        or result.get("outside_roi") != "NOT_EVALUATED_OUTSIDE_SELECTED_ROI"
    ):
        raise T3CameraCapturePackError("accepted partial evidence boundary differs")
    if slot == WHITE_SLOT and result.get("cross_capture_geometry_to_white") is not None:
        raise T3CameraCapturePackError(
            "partial white reference must not claim cross-capture geometry"
        )
    return {
        "slot": slot,
        "attempt": attempt,
        "capture_id": replay["capture"]["capture_id"],
        "captured_at": replay["capture"]["captured_at"],
        "photo_sha256": replay["capture_record"]["photo_sha256"],
        "sidecar_sha256": replay["capture_record"]["sidecar_sha256"],
        "sidecar_integrity_sha256": replay["capture"]["integrity"]["sha256"],
        "alignment": recomputed["alignment"],
        "geometry": recomputed["geometry"],
        "illumination": recomputed["illumination"],
        "evidence_scope": recomputed["evidence_scope"],
    }


def build_partial_bundle(*, output_root: Path) -> dict[str, Any]:
    """Deep-replay and build a four-frame partial-only evidence bundle."""

    output_root = Path(output_root).resolve()
    contract_payload, contract = _load_json(
        _contract_path(output_root), label="partial capture contract"
    )
    _verify_seal(contract, label="partial capture contract")
    if contract.get("kind") != PARTIAL_CONTRACT_KIND:
        raise T3CameraCapturePackError("capture contract is not partial mode")
    expected_contract = build_partial_contract(
        mount_id=str(contract["camera"]["mount_id"])
    )
    if contract != expected_contract:
        raise T3CameraCapturePackError(
            "partial capture contract differs from current pack"
        )
    claims = {
        slot: _load_partial_claims(
            output_root,
            slot,
            contract_integrity_sha256=str(contract["integrity"]["sha256"]),
        )
        for slot in SLOTS
    }
    accepted = {
        slot: _accepted_partial_results(
            output_root,
            slot,
            contract_integrity_sha256=str(contract["integrity"]["sha256"]),
        )
        for slot in SLOTS
    }
    for slot in SLOTS:
        expected_acquisition_paths = [
            _acquisition_path(output_root, slot, int(claim["attempt"])).resolve()
            for _path, claim in claims[slot]
        ]
        if [path.resolve() for path in _acquisition_paths(output_root, slot)] != (
            expected_acquisition_paths
        ):
            raise T3CameraCapturePackError(
                f"{slot} partial claim/acquisition ledger is not one-to-one"
            )
        expected_admission_paths: list[Path] = []
        expected_result_paths: list[Path] = []
        for _path, claim in claims[slot]:
            attempt = int(claim["attempt"])
            acquisition_path, acquisition = _load_partial_acquisition(
                output_root=output_root,
                slot=slot,
                attempt=attempt,
                contract_integrity_sha256=str(contract["integrity"]["sha256"]),
            )
            admission_path = _admission_path(output_root, slot, attempt).resolve()
            result_path = _result_path(output_root, slot, attempt).resolve()
            if acquisition.get("acquired") is True:
                if not admission_path.is_file() or not result_path.is_file():
                    raise T3CameraCapturePackError(
                        f"{slot} successful partial acquisition {attempt} is not terminal"
                    )
                expected_admission_paths.append(admission_path)
                expected_result_paths.append(result_path)
                _load_partial_admission(
                    output_root=output_root,
                    slot=slot,
                    attempt=attempt,
                    contract_integrity_sha256=str(
                        contract["integrity"]["sha256"]
                    ),
                    acquisition_path=acquisition_path,
                    acquisition=acquisition,
                )
            elif admission_path.exists() or result_path.exists():
                raise T3CameraCapturePackError(
                    f"{slot} failed partial acquisition {attempt} has later phases"
                )
        if [path.resolve() for path in _admission_paths(output_root, slot)] != (
            expected_admission_paths
        ) or [path.resolve() for path in _result_paths(output_root, slot)] != (
            expected_result_paths
        ):
            raise T3CameraCapturePackError(
                f"{slot} partial terminal ledger contains an orphan"
            )
        if len(accepted[slot]) != REQUIRED_ACCEPTED[slot]:
            raise T3CameraCapturePackError(
                f"{slot} requires exactly {REQUIRED_ACCEPTED[slot]} accepted partial captures"
            )

    replayed = [
        _deep_validate_partial_accepted_result(
            output_root=output_root, result=result, contract=contract
        )
        for slot in SLOTS
        for result in accepted[slot]
    ]
    white = next(item for item in replayed if item["slot"] == WHITE_SLOT)
    t3_frames = [item for item in replayed if item["slot"] == T3_SLOT]
    if any(item["alignment"] != white["alignment"] for item in t3_frames):
        raise T3CameraCapturePackError(
            "partial white and T3 captures do not share camera lock"
        )
    if len({item["capture_id"] for item in t3_frames}) != 3:
        raise T3CameraCapturePackError("partial T3 capture IDs are not distinct")
    if len({item["photo_sha256"] for item in t3_frames}) != 3:
        raise T3CameraCapturePackError("partial T3 photo hashes are not distinct")
    if len({item["captured_at"] for item in t3_frames}) != 3:
        raise T3CameraCapturePackError(
            "partial T3 capture timestamps are not distinct"
        )
    if any(item["captured_at"] <= white["captured_at"] for item in t3_frames):
        raise T3CameraCapturePackError(
            "partial T3 frames do not follow the white reference"
        )
    white_to_t3 = [
        _partial_corresponding_block_drift(white["geometry"], item["geometry"])
        for item in t3_frames
    ]
    for result, drift in zip(accepted[T3_SLOT], white_to_t3, strict=True):
        if result.get("cross_capture_geometry_to_white") != drift:
            raise T3CameraCapturePackError(
                "partial T3 result-to-white drift metadata differs"
            )
    pairwise_geometry = []
    for left, right in itertools.combinations([white, *t3_frames], 2):
        pairwise_geometry.append(
            {
                "left_capture_id": left["capture_id"],
                "right_capture_id": right["capture_id"],
                **_partial_corresponding_block_drift(
                    left["geometry"], right["geometry"]
                ),
            }
        )
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": PARTIAL_BUNDLE_KIND,
            "pack_revision": PARTIAL_PACK_REVISION,
            "mode": PARTIAL_MODE,
            "output_root": output_root.as_posix(),
            "contract": {
                "path": _contract_path(output_root).resolve().as_posix(),
                "bytes": len(contract_payload),
                "sha256": _sha256_bytes(contract_payload),
                "integrity_sha256": contract["integrity"]["sha256"],
            },
            "attempt_counts": {slot: len(claims[slot]) for slot in SLOTS},
            "accepted_counts": {slot: len(accepted[slot]) for slot in SLOTS},
            "white_reference": white,
            "t3_frames": t3_frames,
            "same_exact_camera_mount_settings_and_dimensions": True,
            "each_capture_uses_its_own_partial_blocks": True,
            "pairwise_cross_capture_partial_geometry": pairwise_geometry,
            "selected_rows": list(PARTIAL_SELECTED_ROWS),
            "selected_columns": list(PARTIAL_SELECTED_COLUMNS),
            "selected_cell_count_per_frame": PARTIAL_SELECTED_CELL_COUNT,
            "replicates_per_code_per_controller_per_frame": 3,
            "profile_code_pair_comparison_available": True,
            "side_specific_white_normalization_required": True,
            "outside_roi": "NOT_EVALUATED_OUTSIDE_SELECTED_ROI",
            "formal_full_panel_evidence": False,
            "full_panel_geometry_evaluated": False,
            "profile_following_decision_earned": False,
            "w4_post_white_full_screen_seal_earned": False,
            "partial_roi_may_be_promoted_to_full_panel_evidence": False,
            "absolute_colour_qualification": False,
            "qualified_colour_count": 0,
            "w4_following_boundary": contract["w4_following_boundary"],
            "hardware_io_performed_by_bundle_builder": False,
            "camera_access_performed_by_bundle_builder": False,
            "output_write_contract": "O_EXCL",
        }
    )


def seal_partial_bundle(
    *, output_root: Path, output_path: Path | None = None
) -> dict[str, Any]:
    bundle = build_partial_bundle(output_root=output_root)
    target = (
        Path(output_path)
        if output_path is not None
        else Path(output_root) / "partial-capture-bundle.json"
    )
    _write_exclusive(target, bundle)
    return bundle


def validate_partial_bundle(path: Path) -> dict[str, Any]:
    _payload, actual = _load_json(path, label="partial capture bundle")
    _verify_seal(actual, label="partial capture bundle")
    if (
        actual.get("kind") != PARTIAL_BUNDLE_KIND
        or actual.get("mode") != PARTIAL_MODE
    ):
        raise T3CameraCapturePackError("partial capture bundle identity differs")
    expected = build_partial_bundle(output_root=Path(str(actual.get("output_root"))))
    if actual != expected:
        raise T3CameraCapturePackError(
            "partial capture bundle differs from deep replay"
        )
    return actual


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    describe = commands.add_parser("describe")
    describe.add_argument("--mount-id", required=True)
    describe.add_argument("--panel-corners", required=True)
    setup_parser = commands.add_parser("setup-view")
    setup_parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    setup_parser.add_argument("--action-result", type=Path, required=True)
    setup_parser.add_argument("--mount-id", required=True)
    acquire_parser = commands.add_parser("acquire")
    acquire_parser.add_argument("--slot", choices=SLOTS, required=True)
    acquire_parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    acquire_parser.add_argument("--action-result", type=Path, required=True)
    acquire_parser.add_argument("--mount-id", required=True)
    admit_parser = commands.add_parser("admit")
    admit_parser.add_argument("--slot", choices=SLOTS, required=True)
    admit_parser.add_argument("--attempt", type=int, required=True)
    admit_parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    admit_parser.add_argument("--panel-corners", required=True)
    capture_parser = commands.add_parser(
        "capture", help="disabled legacy command; migrate to acquire then admit"
    )
    capture_parser.add_argument("--slot", choices=SLOTS, required=True)
    capture_parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    capture_parser.add_argument("--action-result", type=Path, required=True)
    capture_parser.add_argument("--mount-id", required=True)
    capture_parser.add_argument("--panel-corners", required=True)
    seal_parser = commands.add_parser("seal")
    seal_parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    seal_parser.add_argument("--output", type=Path)
    validate_parser = commands.add_parser("validate")
    validate_parser.add_argument("bundle", type=Path)
    describe_partial = commands.add_parser("describe-partial")
    describe_partial.add_argument("--mount-id", required=True)
    acquire_partial = commands.add_parser("acquire-partial")
    acquire_partial.add_argument("--slot", choices=SLOTS, required=True)
    acquire_partial.add_argument(
        "--output-root", type=Path, default=DEFAULT_PARTIAL_OUTPUT_ROOT
    )
    acquire_partial.add_argument("--action-result", type=Path, required=True)
    acquire_partial.add_argument("--mount-id", required=True)
    admit_partial = commands.add_parser("admit-partial")
    admit_partial.add_argument("--slot", choices=SLOTS, required=True)
    admit_partial.add_argument("--attempt", type=int, required=True)
    admit_partial.add_argument(
        "--output-root", type=Path, default=DEFAULT_PARTIAL_OUTPUT_ROOT
    )
    admit_partial.add_argument(
        "--partial-blocks",
        required=True,
        help='strict JSON: {"CS1":[TL,TR,BR,BL],"CS2":[TL,TR,BR,BL]}',
    )
    seal_partial = commands.add_parser("seal-partial")
    seal_partial.add_argument(
        "--output-root", type=Path, default=DEFAULT_PARTIAL_OUTPUT_ROOT
    )
    seal_partial.add_argument("--output", type=Path)
    validate_partial = commands.add_parser("validate-partial")
    validate_partial.add_argument("bundle", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "describe":
            result = build_contract(
                mount_id=args.mount_id,
                panel_corners=args.panel_corners,
            )
        elif args.command == "setup-view":
            result = setup_view_once(
                output_root=args.output_root,
                action_result_path=args.action_result,
                mount_id=args.mount_id,
            )
        elif args.command == "acquire":
            result = acquire_one(
                slot=args.slot,
                output_root=args.output_root,
                action_result_path=args.action_result,
                mount_id=args.mount_id,
            )
        elif args.command == "admit":
            result = admit_one(
                slot=args.slot,
                attempt=args.attempt,
                output_root=args.output_root,
                panel_corners=args.panel_corners,
            )
        elif args.command == "capture":
            result = capture_one(
                slot=args.slot,
                output_root=args.output_root,
                action_result_path=args.action_result,
                mount_id=args.mount_id,
                panel_corners=args.panel_corners,
            )
        elif args.command == "seal":
            result = seal_bundle(
                output_root=args.output_root,
                output_path=args.output,
            )
        elif args.command == "validate":
            result = validate_bundle(args.bundle)
        elif args.command == "describe-partial":
            result = build_partial_contract(mount_id=args.mount_id)
        elif args.command == "acquire-partial":
            result = acquire_partial_one(
                slot=args.slot,
                output_root=args.output_root,
                action_result_path=args.action_result,
                mount_id=args.mount_id,
            )
        elif args.command == "admit-partial":
            result = admit_partial_one(
                slot=args.slot,
                attempt=args.attempt,
                output_root=args.output_root,
                partial_blocks=args.partial_blocks,
            )
        elif args.command == "seal-partial":
            result = seal_partial_bundle(
                output_root=args.output_root,
                output_path=args.output,
            )
        else:
            result = validate_partial_bundle(args.bundle)
    except T3CameraCapturePackError as error:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "kind": "mf1750-t3-camera-capture-pack-error",
                    "valid": False,
                    "error": str(error),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    if args.command == "setup-view" and result.get("captured") is not True:
        return 3
    if args.command == "acquire" and result.get("acquired") is not True:
        return 3
    if args.command == "admit" and result.get("accepted") is not True:
        return 3
    if args.command == "acquire-partial" and result.get("acquired") is not True:
        return 3
    if args.command == "admit-partial" and result.get("accepted") is not True:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
