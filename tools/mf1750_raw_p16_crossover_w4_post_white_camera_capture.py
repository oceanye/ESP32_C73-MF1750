#!/usr/bin/env python3
"""Capture, admit, and seal one optional W4 post-white camera screen.

Only ``acquire`` may open the camera.  It writes a permanent O_EXCL attempt
claim before invoking the capture backend, invokes that backend at most once,
and never retries, falls back, or chains another command.  ``admit`` is an
offline second phase: it binds TL,TR,BR,BL corners to the JPEG already sealed
by ``acquire`` and performs a camera-relative full-white/residual screen.

The screen is deliberately coarse.  PASS means only that this exact locked
JPEG is a usable camera-relative clean-white candidate.  It is not absolute
colour qualification and does not retroactively qualify the T3 observation.
Importing this module performs no camera, device, relay, serial, or network IO.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
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

from host.color_pipeline.color import (  # noqa: E402
    delta_e_ciede2000,
    srgb8_to_lab,
)
from tools import mf1750_camera_capture_evidence as camera  # noqa: E402
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_position_balanced_photo_analyzer as geometry,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w4_t3_ac_profile_following_successor_white_pack as w4,
)
from tools import mf1750_raw_p16_retained_atlas_photo_analyzer as frozen  # noqa: E402


SCHEMA_VERSION = 1
CONTRACT_KIND = "mf1750-raw-p16-crossover-w4-post-white-camera-contract-v1"
CLAIM_KIND = "mf1750-raw-p16-crossover-w4-post-white-camera-attempt-claim-v1"
ACQUISITION_KIND = "mf1750-raw-p16-crossover-w4-post-white-camera-acquisition-v1"
ADMISSION_CLAIM_KIND = (
    "mf1750-raw-p16-crossover-w4-post-white-camera-admission-claim-v1"
)
RESULT_KIND = "mf1750-raw-p16-crossover-w4-post-white-camera-terminal-result-v1"
SEAL_KIND = "mf1750-raw-p16-crossover-w4-post-white-camera-seal-v1"
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
PACK_REVISION = "w4-exact-exp6-48mp-one-frame-two-phase-post-white-v2"

W4_STAGE = "w4-after-t3-ac-profile-following-successor-v1"
W4_CAMPAIGN_ID = (
    "EC5_RAW_P16_CROSSOVER_W4_AFTER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_WHITE_V1"
)
W4_TEST_ID = "EC5-RAW-P16-CROSSOVER-W4-AFTER-T3-AC-PROFILE-FOLLOWING-SUCCESSOR-WHITE-V1"
W4_BUILD_TAG = (
    "MF1750_EC5_RAW_P16_CROSSOVER_W4_AFTER_T3_AC_PROFILE_FOLLOWING_"
    "SUCCESSOR_WHITE_V1_2026-08-30"
)
W4_CONTRACT_ID = "7edf2e1916d536aa8b7d6d77be19899aab4fc6816e8c48de1e1b621bff0b7d52"
W4_ACTION_ID = "e621ea9a05da45da4a120c2b68fbdefcad5f4a48274a5ac5290f5fcc25d7c55b"
W4_DESCRIPTOR_ID = "398b8a86224185b6c6ca7b2d49bc83861f64f2a8c69afa03fbb430b9077c1f45"
W4_FIRMWARE_SHA256 = "9f3ab672c214cdf128a01a51b2803d5a586f72fab1cad065373eead30ee63bf7"
W4_FRAME_SHA256 = "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
W4_ACTION_ROLE = "FACTORY_OTP_WHITE_CONTAINMENT"

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
MAXIMUM_ATTEMPTS = 2
WHITE_REFERENCE_MIN_LSTAR = 25.0

# Camera-relative coarse residual boundaries.  These retain the established
# W2/W3 residual-screen scale; they are not an absolute white calibration.
CELL_P95_PASS_DE00 = 6.0
CELL_P95_REVIEW_DE00 = 10.0
CELL_MAX_PASS_DE00 = 10.0
CELL_MAX_REVIEW_DE00 = 16.0
GRID_P95_PASS_DE00 = 6.0
GRID_P95_REVIEW_DE00 = 10.0
GRID_MAX_PASS_DE00 = 10.0
GRID_MAX_REVIEW_DE00 = 16.0
STRIPE_ROW_PASS_DE00 = 4.0
STRIPE_ROW_REVIEW_DE00 = 8.0
BOTTOM_P95_PASS_DE00 = 6.0
BOTTOM_P95_REVIEW_DE00 = 10.0
BOTTOM_MAX_PASS_DE00 = 10.0
BOTTOM_MAX_REVIEW_DE00 = 16.0
HIGH_CLIP_PASS_MAX = 0.005
HIGH_CLIP_REVIEW_MAX = 0.02
GRID_COLUMNS = 24
GRID_ROWS = 12
GRID_MARGIN_X = 24
GRID_MARGIN_Y = 24

DEFAULT_OUTPUT_ROOT = Path(
    ".test-output/hardware/"
    "MF1750_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_"
    "WHITE_CAMERA_DAYLIGHT_V1"
)

PASS = "PASS"
REVIEW = "REVIEW"
FAIL = "FAIL"
_RANK = {PASS: 0, REVIEW: 1, FAIL: 2}


class W4PostWhiteCameraError(RuntimeError):
    """Raised when a W4 camera record fails closed."""


class _DuplicateKeyError(ValueError):
    pass


CaptureFunction = Callable[..., dict[str, Any]]


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise W4PostWhiteCameraError(f"non-canonical JSON value: {error}") from error


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
        raise W4PostWhiteCameraError(f"{label} integrity keys differ")
    unsigned = dict(value)
    unsigned.pop("integrity")
    expected = _sha256_bytes(_canonical_json(unsigned))
    if (
        integrity.get("algorithm") != INTEGRITY_ALGORITHM
        or integrity.get("sha256") != expected
    ):
        raise W4PostWhiteCameraError(f"{label} integrity differs")
    return expected


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_stable_regular(path: Path, *, label: str) -> bytes:
    path = Path(path)
    try:
        before = path.lstat()
        if path.is_symlink() or not path.is_file():
            raise W4PostWhiteCameraError(
                f"{label} must be a regular non-symlink file: {path}"
            )
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise W4PostWhiteCameraError(f"cannot read {label}: {error}") from error
    before_id = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_id = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_id != after_id or len(payload) != after.st_size:
        raise W4PostWhiteCameraError(f"{label} changed while being read")
    return payload


def _load_json(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    payload = _read_stable_regular(path, label=label)
    try:
        root = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise W4PostWhiteCameraError(
            f"{label} is not strict UTF-8 JSON: {error}"
        ) from error
    if not isinstance(root, dict):
        raise W4PostWhiteCameraError(f"{label} root must be an object")
    return payload, root


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _write_bytes_exclusive(path: Path, payload: bytes, *, label: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
    except FileExistsError as error:
        raise W4PostWhiteCameraError(
            f"refusing to overwrite existing {label}: {path}"
        ) from error
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _write_exclusive(path: Path, value: Mapping[str, Any], *, label: str) -> None:
    _write_bytes_exclusive(path, _json_bytes(value), label=label)


def _copy_exclusive(source: Path, target: Path) -> dict[str, Any]:
    payload = _read_stable_regular(source, label="W4 action result source")
    _write_bytes_exclusive(target, payload, label="W4 action snapshot")
    persisted = _read_stable_regular(target, label="W4 action snapshot")
    if persisted != payload:
        raise W4PostWhiteCameraError("W4 action snapshot bytes differ")
    return {
        "path": target.resolve().as_posix(),
        "bytes": len(payload),
        "sha256": _sha256_bytes(payload),
    }


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def _expected_action_identity() -> dict[str, Any]:
    report = w4.build_white_report()
    action = report["action"]
    artifact = w4.WHITE_ARTIFACTS[w4.STAGE]
    generated = {
        "stage": w4.STAGE,
        "campaign_id": w4.CONFIG.campaign_id,
        "test_id": w4.CONFIG.test_id,
        "build_tag": w4.CONFIG.build_tag,
        "contract_id": report["contract_id"],
        "firmware_sha256": artifact["bin_sha256"],
        "action_id": action["action_id"],
        "descriptor_id": action["descriptor_id"],
        "role": action["role"],
        "frame_sha256": action["frame_sha256"],
        "ordinal": action["ordinal"],
    }
    frozen_literal = {
        "stage": W4_STAGE,
        "campaign_id": W4_CAMPAIGN_ID,
        "test_id": W4_TEST_ID,
        "build_tag": W4_BUILD_TAG,
        "contract_id": W4_CONTRACT_ID,
        "firmware_sha256": W4_FIRMWARE_SHA256,
        "action_id": W4_ACTION_ID,
        "descriptor_id": W4_DESCRIPTOR_ID,
        "role": W4_ACTION_ROLE,
        "frame_sha256": W4_FRAME_SHA256,
        "ordinal": 1,
    }
    if generated != frozen_literal:
        raise W4PostWhiteCameraError(
            "W4 pack identity differs from the wrapper's exact frozen constants"
        )
    return frozen_literal


def _validate_action_source(path: Path) -> dict[str, Any]:
    try:
        payload, _root, actual = camera._load_action_result(Path(path).resolve())  # noqa: SLF001
    except camera.CameraCaptureEvidenceError as error:
        raise W4PostWhiteCameraError(f"W4 action result rejected: {error}") from error
    expected = _expected_action_identity()
    for field in (
        "campaign_id",
        "test_id",
        "build_tag",
        "contract_id",
        "firmware_sha256",
        "action_id",
        "descriptor_id",
        "role",
        "frame_sha256",
        "ordinal",
    ):
        if actual.get(field) != expected[field]:
            raise W4PostWhiteCameraError(
                f"W4 action result {field} differs from exact frozen identity"
            )
    if actual.get("visible_refreshes") != 1:
        raise W4PostWhiteCameraError(
            "W4 action result must bind exactly one visible white refresh"
        )
    return {
        **expected,
        "source_bytes": len(payload),
        "source_sha256": _sha256_bytes(payload),
        "canonical_integrity_sha256": actual["canonical_integrity_sha256"],
        "boot_nonce": actual["boot_nonce"],
        "visible_refreshes": actual["visible_refreshes"],
    }


def _assert_camera_profile() -> None:
    expected = {
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
    }
    if CAMERA_PROFILE != expected:
        raise W4PostWhiteCameraError(
            "camera profile differs from exact README camera.md daylight profile"
        )


def build_description() -> dict[str, Any]:
    """Return the immutable wrapper description without writing evidence."""

    _assert_camera_profile()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-raw-p16-crossover-w4-post-white-camera-description-v1",
        "pack_revision": PACK_REVISION,
        "default_output_root": DEFAULT_OUTPUT_ROOT.as_posix(),
        "w4_action": _expected_action_identity(),
        "camera": {
            "target": TARGET_CAMERA,
            "profile": deepcopy(CAMERA_PROFILE),
            "warmup_frames": WARMUP_FRAMES,
            "jpeg_quality": JPEG_QUALITY,
            "capture_binding": camera.BINDING_LOCKED_RETAINED,
            "coverage_scope": camera.COVERAGE_FULL,
        },
        "lifecycle": ["acquire", "admit", "seal", "validate"],
        "maximum_attempts": MAXIMUM_ATTEMPTS,
        "one_camera_frame_maximum_per_acquire_invocation": True,
        "attempt_claim_o_excl_before_camera_open": True,
        "admission_claim_o_excl_before_corner_parse_or_analysis": True,
        "every_admission_claim_has_terminal_accepted_or_rejected_result": True,
        "panel_corners_forbidden_during_acquire": True,
        "panel_corners_bound_to_same_jpeg_during_admit": True,
        "automatic_retry": False,
        "automatic_fallback": False,
        "automatic_chaining": False,
        "screen": {
            "minimum_lstar_hard_boundary": WHITE_REFERENCE_MIN_LSTAR,
            "all_64_cells_required": True,
            "camera_relative_only": True,
            "absolute_colour_qualification": False,
            "terminal_accepted_classification": PASS,
            "terminal_rejected_classifications": [REVIEW, FAIL],
            "thresholds": _thresholds(),
        },
        "hardware_accessed": False,
    }


def build_contract(*, mount_id: str) -> dict[str, Any]:
    _assert_camera_profile()
    if not isinstance(mount_id, str) or not mount_id.strip():
        raise W4PostWhiteCameraError("mount_id must be non-empty")
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": CONTRACT_KIND,
            "pack_revision": PACK_REVISION,
            "default_output_root": DEFAULT_OUTPUT_ROOT.as_posix(),
            "w4_action": _expected_action_identity(),
            "camera": {
                "target": TARGET_CAMERA,
                "profile": deepcopy(CAMERA_PROFILE),
                "warmup_frames": WARMUP_FRAMES,
                "jpeg_quality": JPEG_QUALITY,
                "require_all_setting_writes": True,
                "capture_binding": camera.BINDING_LOCKED_RETAINED,
                "coverage_scope": camera.COVERAGE_FULL,
                "mount_id": mount_id.strip(),
                "full_panel_visible": True,
                "full_panel_uncropped": True,
            },
            "attempt_boundary": {
                "maximum_attempts": MAXIMUM_ATTEMPTS,
                "one_camera_frame_maximum_per_acquire_invocation": True,
                "claim_o_excl_before_camera_open": True,
                "failed_claim_permanently_consumed": True,
                "automatic_retry": False,
                "automatic_fallback": False,
                "automatic_chaining": False,
            },
            "two_phase_boundary": {
                "acquire_has_no_panel_corners": True,
                "admit_has_no_camera_access": True,
                "admission_claim_o_excl_before_corner_parse_or_analysis": True,
                "every_claim_has_terminal_accepted_or_rejected_result": True,
                "corners_apply_to_exact_acquired_jpeg": True,
                "one_admission_maximum_per_acquisition": True,
            },
            "coarse_screen": {
                "all_64_cells_required": True,
                "minimum_lstar_hard_boundary": WHITE_REFERENCE_MIN_LSTAR,
                "thresholds": _thresholds(),
                "classification_values": [PASS, REVIEW, FAIL],
                "terminal_accepted_classification": PASS,
                "terminal_rejected_classifications": [REVIEW, FAIL],
                "rejected_attempt_allows_explicit_next_acquire_within_budget": True,
                "camera_relative_only": True,
                "absolute_colour_qualification": False,
                "qualified_colour_count": 0,
            },
            "all_outputs_o_excl": True,
        }
    )


def _contract_path(output_root: Path) -> Path:
    return Path(output_root) / "post-white-camera-contract.json"


def ensure_contract(*, output_root: Path, mount_id: str) -> dict[str, Any]:
    expected = build_contract(mount_id=mount_id)
    path = _contract_path(output_root)
    if path.exists():
        _payload, actual = _load_json(path, label="post-white camera contract")
        _verify_seal(actual, label="post-white camera contract")
        if actual != expected:
            raise W4PostWhiteCameraError(
                "existing post-white camera contract differs from requested mount"
            )
        return actual
    _write_exclusive(path, expected, label="post-white camera contract")
    return expected


def _claim_path(output_root: Path, attempt: int) -> Path:
    return Path(output_root) / "claims" / f"attempt-{attempt:02d}.claim.json"


def _acquisition_path(output_root: Path, attempt: int) -> Path:
    return (
        Path(output_root) / "acquisitions" / f"attempt-{attempt:02d}.acquisition.json"
    )


def _admission_path(output_root: Path, attempt: int) -> Path:
    return Path(output_root) / "admissions" / f"attempt-{attempt:02d}.claim.json"


def _result_path(output_root: Path, attempt: int) -> Path:
    return Path(output_root) / "results" / f"attempt-{attempt:02d}.result.json"


def _load_contract(output_root: Path) -> dict[str, Any]:
    _payload, contract = _load_json(
        _contract_path(output_root), label="post-white camera contract"
    )
    _verify_seal(contract, label="post-white camera contract")
    if contract.get("kind") != CONTRACT_KIND:
        raise W4PostWhiteCameraError("post-white camera contract kind differs")
    expected = build_contract(
        mount_id=str(contract.get("camera", {}).get("mount_id", ""))
    )
    if contract != expected:
        raise W4PostWhiteCameraError("post-white camera contract differs on replay")
    return contract


def _load_claims(
    output_root: Path, contract: Mapping[str, Any]
) -> list[dict[str, Any]]:
    paths = sorted((Path(output_root) / "claims").glob("attempt-*.claim.json"))
    claims: list[dict[str, Any]] = []
    for attempt, path in enumerate(paths, start=1):
        if path != _claim_path(output_root, attempt):
            raise W4PostWhiteCameraError("attempt claim filenames are not contiguous")
        _payload, claim = _load_json(path, label="attempt claim")
        _verify_seal(claim, label="attempt claim")
        if (
            claim.get("kind") != CLAIM_KIND
            or claim.get("attempt") != attempt
            or claim.get("contract_integrity_sha256") != contract["integrity"]["sha256"]
            or claim.get("w4_action_id") != W4_ACTION_ID
            or claim.get("state") != "PERMANENTLY_CONSUMED_BEFORE_CAMERA_OPEN"
            or claim.get("one_camera_frame_maximum") is not True
            or claim.get("panel_corners_present") is not False
            or claim.get("automatic_retry") is not False
            or claim.get("automatic_fallback") is not False
            or claim.get("automatic_chaining") is not False
        ):
            raise W4PostWhiteCameraError("attempt claim identity/boundary differs")
        claims.append(claim)
    if len(claims) > MAXIMUM_ATTEMPTS:
        raise W4PostWhiteCameraError("attempt claims exceed frozen maximum")
    return claims


def _file_binding(path: Path, payload: bytes) -> dict[str, Any]:
    return {
        "path": Path(path).resolve().as_posix(),
        "bytes": len(payload),
        "sha256": _sha256_bytes(payload),
    }


def _sealed_file_binding(
    path: Path, record: Mapping[str, Any], *, label: str
) -> dict[str, Any]:
    payload = _read_stable_regular(path, label=label)
    return {
        **_file_binding(path, payload),
        "integrity_sha256": record["integrity"]["sha256"],
    }


def _load_acquisition(
    output_root: Path,
    attempt: int,
    *,
    contract: Mapping[str, Any],
) -> dict[str, Any] | None:
    path = _acquisition_path(output_root, attempt)
    if not path.exists():
        return None
    _payload, acquisition = _load_json(path, label="post-white acquisition")
    _verify_seal(acquisition, label="post-white acquisition")
    if (
        acquisition.get("kind") != ACQUISITION_KIND
        or acquisition.get("attempt") != attempt
        or acquisition.get("contract_integrity_sha256")
        != contract["integrity"]["sha256"]
        or acquisition.get("phase") != "CAMERA_ACQUISITION_NO_CORNERS"
        or acquisition.get("camera_invocations") not in {0, 1}
        or acquisition.get("automatic_retry_count") != 0
        or acquisition.get("automatic_fallback") is not False
        or acquisition.get("automatic_chaining") is not False
    ):
        raise W4PostWhiteCameraError("post-white acquisition identity differs")
    claim_path = _claim_path(output_root, attempt)
    _claim_payload, claim = _load_json(claim_path, label="attempt claim")
    _verify_seal(claim, label="attempt claim")
    if (
        claim.get("kind") != CLAIM_KIND
        or claim.get("attempt") != attempt
        or claim.get("contract_integrity_sha256") != contract["integrity"]["sha256"]
        or claim.get("w4_action_id") != W4_ACTION_ID
        or claim.get("state") != "PERMANENTLY_CONSUMED_BEFORE_CAMERA_OPEN"
        or claim.get("one_camera_frame_maximum") is not True
        or claim.get("panel_corners_present") is not False
        or claim.get("automatic_retry") is not False
        or claim.get("automatic_fallback") is not False
        or claim.get("automatic_chaining") is not False
    ):
        raise W4PostWhiteCameraError("canonical attempt claim identity differs")
    expected_claim = _sealed_file_binding(
        claim_path, claim, label="canonical attempt claim"
    )
    if (
        acquisition.get("claim") != expected_claim
        or acquisition.get("claim_integrity_sha256") != claim["integrity"]["sha256"]
    ):
        raise W4PostWhiteCameraError("post-white acquisition claim binding differs")
    return acquisition


def _load_admission(
    output_root: Path,
    attempt: int,
    *,
    contract: Mapping[str, Any],
) -> dict[str, Any] | None:
    path = _admission_path(output_root, attempt)
    if not path.exists():
        return None
    _payload, admission = _load_json(path, label="post-white admission claim")
    _verify_seal(admission, label="post-white admission claim")
    if (
        admission.get("kind") != ADMISSION_CLAIM_KIND
        or admission.get("attempt") != attempt
        or admission.get("contract_integrity_sha256") != contract["integrity"]["sha256"]
        or admission.get("state")
        != "PERMANENTLY_CONSUMED_BEFORE_CORNER_PARSE_OR_ANALYSIS"
        or admission.get("one_admission_maximum") is not True
        or admission.get("camera_invocations_during_admit") != 0
    ):
        raise W4PostWhiteCameraError("post-white admission claim identity differs")
    acquisition = _load_acquisition(output_root, attempt, contract=contract)
    if acquisition is None:
        raise W4PostWhiteCameraError(
            "post-white admission claim lacks its canonical acquisition"
        )
    acquisition_path = _acquisition_path(output_root, attempt)
    expected_acquisition = _sealed_file_binding(
        acquisition_path,
        acquisition,
        label="canonical post-white acquisition",
    )
    if (
        admission.get("acquisition") != expected_acquisition
        or admission.get("acquisition_integrity_sha256")
        != acquisition["integrity"]["sha256"]
    ):
        raise W4PostWhiteCameraError("post-white admission acquisition binding differs")
    return admission


def _load_result(
    output_root: Path,
    attempt: int,
    *,
    contract: Mapping[str, Any],
) -> dict[str, Any] | None:
    path = _result_path(output_root, attempt)
    if not path.exists():
        return None
    _payload, result = _load_json(path, label="post-white terminal result")
    _verify_seal(result, label="post-white terminal result")
    if (
        result.get("kind") != RESULT_KIND
        or result.get("attempt") != attempt
        or result.get("contract_integrity_sha256") != contract["integrity"]["sha256"]
        or result.get("phase") != "OFFLINE_GEOMETRY_AND_WHITE_SCREEN"
        or result.get("terminal_state") not in {"ACCEPTED", "REJECTED"}
        or result.get("camera_invocations_during_admit") != 0
        or result.get("automatic_retry") is not False
        or result.get("automatic_fallback") is not False
        or result.get("automatic_chaining") is not False
    ):
        raise W4PostWhiteCameraError("post-white terminal result identity differs")
    if (result.get("terminal_state") == "ACCEPTED") != (result.get("accepted") is True):
        raise W4PostWhiteCameraError("terminal state and accepted flag differ")
    admission_claim = _load_admission(output_root, attempt, contract=contract)
    if admission_claim is None:
        raise W4PostWhiteCameraError("terminal result lacks its admission claim")
    claim_path = _admission_path(output_root, attempt)
    claim_payload = _read_stable_regular(claim_path, label="post-white admission claim")
    expected_claim_binding = {
        **_file_binding(claim_path, claim_payload),
        "integrity_sha256": admission_claim["integrity"]["sha256"],
    }
    if result.get("admission_claim") != expected_claim_binding:
        raise W4PostWhiteCameraError("terminal result admission-claim binding differs")
    if result.get("accepted") is True:
        if (
            result.get("evidence_admitted") is not True
            or result.get("panel_corners_tl_tr_br_bl") is None
            or not isinstance(result.get("evaluation"), Mapping)
            or result.get("classification") != PASS
            or result["evaluation"].get("classification") != PASS
        ):
            raise W4PostWhiteCameraError("accepted terminal result payload differs")
    else:
        evaluation = result.get("evaluation")
        if (
            result.get("evidence_admitted") is not False
            or result.get("classification") not in {REVIEW, FAIL}
            or (
                isinstance(evaluation, Mapping)
                and evaluation.get("classification") != result.get("classification")
            )
        ):
            raise W4PostWhiteCameraError("rejected terminal result payload differs")
    return result


def _claim_attempt(
    *,
    output_root: Path,
    contract: Mapping[str, Any],
    action_result_path: Path,
    action_payload: bytes,
) -> tuple[int, Path, dict[str, Any]]:
    claims = _load_claims(output_root, contract)
    if len(claims) >= MAXIMUM_ATTEMPTS:
        raise W4PostWhiteCameraError(
            f"maximum attempt budget {MAXIMUM_ATTEMPTS} is exhausted"
        )
    for attempt in range(1, len(claims) + 1):
        acquisition = _load_acquisition(output_root, attempt, contract=contract)
        admission_claim = _load_admission(output_root, attempt, contract=contract)
        result = _load_result(output_root, attempt, contract=contract)
        if acquisition is not None and acquisition.get("acquired") is True:
            if admission_claim is None:
                raise W4PostWhiteCameraError(
                    f"attempt {attempt} is acquired and must be admitted before another acquisition"
                )
            if result is None:
                raise W4PostWhiteCameraError(
                    f"attempt {attempt} has a permanent admission claim without a terminal result"
                )
            if result.get("accepted") is True:
                raise W4PostWhiteCameraError(
                    "an exact W4 post-white camera frame is already admitted"
                )
    attempt = len(claims) + 1
    claim_path = _claim_path(output_root, attempt)
    claim = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": CLAIM_KIND,
            "attempt": attempt,
            "claimed_at": _now(),
            "contract_integrity_sha256": contract["integrity"]["sha256"],
            "w4_action_id": W4_ACTION_ID,
            "action_source": {
                "path": action_result_path.resolve().as_posix(),
                "bytes": len(action_payload),
                "sha256": _sha256_bytes(action_payload),
            },
            "state": "PERMANENTLY_CONSUMED_BEFORE_CAMERA_OPEN",
            "one_camera_frame_maximum": True,
            "panel_corners_present": False,
            "automatic_retry": False,
            "automatic_fallback": False,
            "automatic_chaining": False,
        }
    )
    _write_exclusive(claim_path, claim, label="attempt claim")
    return attempt, claim_path, claim


def acquire_one(
    *,
    output_root: Path,
    action_result_path: Path,
    mount_id: str,
    capture_function: CaptureFunction = camera.capture_locked_retained,
) -> dict[str, Any]:
    """Claim and acquire at most one frame; never analyze or retry it."""

    output_root = Path(output_root).resolve()
    action_result_path = Path(action_result_path).resolve()
    _validate_action_source(action_result_path)
    contract = ensure_contract(output_root=output_root, mount_id=mount_id)
    action_payload = _read_stable_regular(action_result_path, label="W4 action result")
    attempt, claim_path, claim = _claim_attempt(
        output_root=output_root,
        contract=contract,
        action_result_path=action_result_path,
        action_payload=action_payload,
    )
    evidence_dir = output_root / "evidence" / f"attempt-{attempt:02d}"
    action_snapshot_path = evidence_dir / "action-result.json"
    photo_path = evidence_dir / "post-white.jpg"
    sidecar_path = evidence_dir / "post-white.capture.json"
    acquisition_path = _acquisition_path(output_root, attempt)
    camera_invocations = 0
    capture: dict[str, Any] | None = None
    try:
        action_snapshot = _copy_exclusive(action_result_path, action_snapshot_path)
        # The O_EXCL claim has already been fsync'd before this sole backend call.
        camera_invocations = 1
        capture_function(
            action_result_path=action_snapshot_path,
            photo_path=photo_path,
            sidecar_path=sidecar_path,
            camera_id=camera.TARGET_CAMERA_LOGICAL_ID,
            camera_instance_id=None,
            camera_index=None,
            mount_id=contract["camera"]["mount_id"],
            coverage_scope=camera.COVERAGE_FULL,
            coverage_note=(
                "full MF1750 panel after exact W4 white; fixed mount; "
                "camera-relative post-white screen only"
            ),
            requested_settings=deepcopy(CAMERA_PROFILE),
            warmup_frames=WARMUP_FRAMES,
            jpeg_quality=JPEG_QUALITY,
            require_all_setting_writes=True,
            automated_verdict="INCONCLUSIVE",
            assessment_confidence="low",
            limitations=(
                "pending same-JPEG panel corners and offline admission",
                "camera-relative clean-white screen only",
                "no absolute colour qualification",
            ),
            analysis_source="w4-post-white-two-phase-camera-acquisition-v1",
        )
        capture = camera.validate_capture_evidence(sidecar_path)
        photo_payload = _read_stable_regular(photo_path, label="post-white JPEG")
        sidecar_payload = _read_stable_regular(sidecar_path, label="capture sidecar")
        _validate_capture_lock(
            capture=capture,
            photo_payload=photo_payload,
            contract=contract,
        )
        acquisition = _seal(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": ACQUISITION_KIND,
                "attempt": attempt,
                "phase": "CAMERA_ACQUISITION_NO_CORNERS",
                "acquired": True,
                "outcome": "ACQUIRED_PENDING_OFFLINE_ADMISSION",
                "recorded_at": _now(),
                "contract_integrity_sha256": contract["integrity"]["sha256"],
                "claim": _sealed_file_binding(
                    claim_path,
                    claim,
                    label="attempt claim",
                ),
                "claim_integrity_sha256": claim["integrity"]["sha256"],
                "action_snapshot": action_snapshot,
                "capture": {
                    "capture_id": capture["capture_id"],
                    "captured_at": capture["captured_at"],
                    "photo": _file_binding(photo_path, photo_payload),
                    "sidecar": _file_binding(sidecar_path, sidecar_payload),
                    "sidecar_integrity_sha256": capture["integrity"]["sha256"],
                },
                "panel_corners_present": False,
                "camera_invocations": camera_invocations,
                "automatic_retry_count": 0,
                "automatic_fallback": False,
                "automatic_chaining": False,
            }
        )
    except Exception as error:
        partial: dict[str, Any] = {}
        for name, path in (
            ("action_snapshot", action_snapshot_path),
            ("photo", photo_path),
            ("sidecar", sidecar_path),
        ):
            if path.is_file() and not path.is_symlink():
                payload = _read_stable_regular(path, label=f"partial {name}")
                partial[name] = _file_binding(path, payload)
        acquisition = _seal(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": ACQUISITION_KIND,
                "attempt": attempt,
                "phase": "CAMERA_ACQUISITION_NO_CORNERS",
                "acquired": False,
                "outcome": "REJECTED_FAIL_CLOSED_DO_NOT_RETRY_AUTOMATICALLY",
                "recorded_at": _now(),
                "contract_integrity_sha256": contract["integrity"]["sha256"],
                "claim": _sealed_file_binding(
                    claim_path,
                    claim,
                    label="attempt claim",
                ),
                "claim_integrity_sha256": claim["integrity"]["sha256"],
                "camera_invocations": camera_invocations,
                "automatic_retry_count": 0,
                "automatic_fallback": False,
                "automatic_chaining": False,
                "error": {"type": type(error).__name__, "message": str(error)},
                "partial_evidence": partial,
                "capture_id_if_validated": (
                    None if capture is None else capture.get("capture_id")
                ),
            }
        )
    _write_exclusive(acquisition_path, acquisition, label="post-white acquisition")
    return acquisition


def _validate_capture_lock(
    *,
    capture: Mapping[str, Any],
    photo_payload: bytes,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        lock = frozen._validate_fixed_capture(capture)  # noqa: SLF001
    except frozen.RawP16PhotoAnalysisError as error:
        raise W4PostWhiteCameraError(
            f"exact README camera lock rejected: {error}"
        ) from error
    expected = _expected_action_identity()
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
        if capture.get(field) != expected[field]:
            raise W4PostWhiteCameraError(
                f"capture {field} differs from exact W4 action"
            )
    if capture.get("capture_binding") != camera.BINDING_LOCKED_RETAINED:
        raise W4PostWhiteCameraError("capture is not locked-retained")
    coverage = capture.get("coverage")
    if not isinstance(coverage, Mapping) or (
        coverage.get("scope") != camera.COVERAGE_FULL
        or coverage.get("mount_id") != contract["camera"]["mount_id"]
        or coverage.get("full_panel_visible") is not True
    ):
        raise W4PostWhiteCameraError("capture full-panel/mount binding differs")
    photo = capture.get("photo")
    if not isinstance(photo, Mapping) or (
        photo.get("width") != PHOTO_WIDTH
        or photo.get("height") != PHOTO_HEIGHT
        or photo.get("sha256") != _sha256_bytes(photo_payload)
        or photo.get("bytes") != len(photo_payload)
    ):
        raise W4PostWhiteCameraError("capture JPEG dimensions/hash binding differs")
    return lock


def _normalise_panel_corners(value: str | Any) -> list[list[float]]:
    try:
        corners = geometry._coerce_panel_corners(value)  # noqa: SLF001
        _homography, report = geometry._fit_panel_homography(  # noqa: SLF001
            corners,
            photo_width=PHOTO_WIDTH,
            photo_height=PHOTO_HEIGHT,
        )
    except geometry.CrossoverPhotoAnalysisError as error:
        raise W4PostWhiteCameraError(f"panel geometry rejected: {error}") from error
    if report.get("sampling_geometry_admitted") is not True:
        raise W4PostWhiteCameraError("panel geometry was not admitted")
    return [
        [round(float(component), 6) for component in row] for row in corners.tolist()
    ]


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        raise W4PostWhiteCameraError("cannot take percentile of no values")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _classification(value: float, *, pass_max: float, review_max: float) -> str:
    if value <= pass_max:
        return PASS
    if value <= review_max:
        return REVIEW
    return FAIL


def _metric(value: float, *, pass_max: float, review_max: float) -> dict[str, Any]:
    return {
        "value": round(float(value), 6),
        "pass_max": pass_max,
        "review_max": review_max,
        "state": _classification(value, pass_max=pass_max, review_max=review_max),
    }


def _thresholds() -> dict[str, Any]:
    return {
        "cell_p95_delta_e00": [CELL_P95_PASS_DE00, CELL_P95_REVIEW_DE00],
        "cell_max_delta_e00": [CELL_MAX_PASS_DE00, CELL_MAX_REVIEW_DE00],
        "grid_p95_delta_e00": [GRID_P95_PASS_DE00, GRID_P95_REVIEW_DE00],
        "grid_max_delta_e00": [GRID_MAX_PASS_DE00, GRID_MAX_REVIEW_DE00],
        "horizontal_row_max_delta_e00": [
            STRIPE_ROW_PASS_DE00,
            STRIPE_ROW_REVIEW_DE00,
        ],
        "bottom_p95_delta_e00": [BOTTOM_P95_PASS_DE00, BOTTOM_P95_REVIEW_DE00],
        "bottom_max_delta_e00": [BOTTOM_MAX_PASS_DE00, BOTTOM_MAX_REVIEW_DE00],
        "high_clip_fraction": [HIGH_CLIP_PASS_MAX, HIGH_CLIP_REVIEW_MAX],
    }


def _rgb_median_lab(pixels: Any) -> tuple[list[float], list[float]]:
    _cv2, np = geometry.base._import_cv()  # noqa: SLF001
    flat = np.asarray(pixels, dtype=np.float64).reshape(-1, 3)
    if len(flat) == 0 or not np.all(np.isfinite(flat)):
        raise W4PostWhiteCameraError("empty or non-finite pixel sample")
    rgb = np.median(flat, axis=0)
    rgb_list = [round(float(value), 6) for value in rgb.tolist()]
    rgb8 = tuple(int(round(float(np.clip(value, 0, 255)))) for value in rgb)
    lab = [round(float(value), 6) for value in srgb8_to_lab(rgb8)]
    return rgb_list, lab


def _warp_panel(rgb: Any, homography: Any) -> Any:
    cv2, np = geometry.base._import_cv()  # noqa: SLF001
    inverse = np.linalg.inv(np.asarray(homography, dtype=np.float64))
    panel = cv2.warpPerspective(
        np.asarray(rgb),
        inverse,
        (geometry.LOGICAL_WIDTH, geometry.LOGICAL_HEIGHT),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    if panel.shape != (geometry.LOGICAL_HEIGHT, geometry.LOGICAL_WIDTH, 3):
        raise W4PostWhiteCameraError("rectified logical panel shape differs")
    return panel


def _evaluate_photo(photo_payload: bytes, panel_corners: Any) -> dict[str, Any]:
    try:
        rgb = geometry.base._decode_rgb(photo_payload)  # noqa: SLF001
        if rgb.shape != (PHOTO_HEIGHT, PHOTO_WIDTH, 3):
            raise W4PostWhiteCameraError("post-white JPEG is not exact 4000x3000 RGB")
        homography, geometry_report = geometry._fit_panel_homography(  # noqa: SLF001
            panel_corners,
            photo_width=PHOTO_WIDTH,
            photo_height=PHOTO_HEIGHT,
        )
        sampled = [
            geometry.base._sample_cell(rgb, homography, cell)  # noqa: SLF001
            for cell in geometry._all_logical_cells()  # noqa: SLF001
        ]
    except geometry.CrossoverPhotoAnalysisError as error:
        raise W4PostWhiteCameraError(
            f"post-white sampling rejected: {error}"
        ) from error
    if len(sampled) != 64:
        raise W4PostWhiteCameraError("post-white geometry did not yield 64 cells")

    cell_labs = [
        [
            float(component)
            for component in item["camera_relative_lab_d65_from_rgb_median"]
        ]
        for item in sampled
    ]
    reference_lab = [
        statistics.median(item[index] for item in cell_labs) for index in range(3)
    ]
    cell_deltas = [float(delta_e_ciede2000(lab, reference_lab)) for lab in cell_labs]
    cell_lstars = [lab[0] for lab in cell_labs]
    cell_records = []
    for item, delta in zip(sampled, cell_deltas, strict=True):
        cell_records.append(
            {
                "cell_id": item["cell_id"],
                "controller": f"CS{item['controller'] + 1}",
                "row": item["row"],
                "column": item["column"],
                "code": item["code"],
                "camera_relative_rgb_median": item["robust_rgb_median"],
                "camera_relative_lab_d65": item[
                    "camera_relative_lab_d65_from_rgb_median"
                ],
                "delta_e00_to_panel_white_center": round(delta, 6),
            }
        )

    panel = _warp_panel(rgb, homography)
    _cv2, np = geometry.base._import_cv()  # noqa: SLF001
    tiles: list[dict[str, Any]] = []
    tile_labs: list[list[float]] = []
    for row in range(GRID_ROWS):
        y0 = (
            GRID_MARGIN_Y
            + row * (geometry.LOGICAL_HEIGHT - 2 * GRID_MARGIN_Y) // GRID_ROWS
        )
        y1 = (
            GRID_MARGIN_Y
            + (row + 1) * (geometry.LOGICAL_HEIGHT - 2 * GRID_MARGIN_Y) // GRID_ROWS
        )
        for column in range(GRID_COLUMNS):
            x0 = (
                GRID_MARGIN_X
                + column * (geometry.LOGICAL_WIDTH - 2 * GRID_MARGIN_X) // GRID_COLUMNS
            )
            x1 = (
                GRID_MARGIN_X
                + (column + 1)
                * (geometry.LOGICAL_WIDTH - 2 * GRID_MARGIN_X)
                // GRID_COLUMNS
            )
            tile_rgb, tile_lab = _rgb_median_lab(panel[y0:y1, x0:x1])
            tile_labs.append(tile_lab)
            tiles.append(
                {
                    "row": row,
                    "column": column,
                    "logical_bounds": [x0, y0, x1, y1],
                    "camera_relative_rgb_median": tile_rgb,
                    "camera_relative_lab_d65": tile_lab,
                }
            )
    tile_reference = [
        statistics.median(item[index] for item in tile_labs) for index in range(3)
    ]
    grid_deltas = [float(delta_e_ciede2000(lab, tile_reference)) for lab in tile_labs]
    for tile, delta in zip(tiles, grid_deltas, strict=True):
        tile["delta_e00_to_dense_grid_center"] = round(delta, 6)

    row_labs = []
    for row in range(GRID_ROWS):
        row_pixels = panel[
            GRID_MARGIN_Y
            + row
            * (geometry.LOGICAL_HEIGHT - 2 * GRID_MARGIN_Y)
            // GRID_ROWS : GRID_MARGIN_Y
            + (row + 1) * (geometry.LOGICAL_HEIGHT - 2 * GRID_MARGIN_Y) // GRID_ROWS,
            GRID_MARGIN_X : geometry.LOGICAL_WIDTH - GRID_MARGIN_X,
        ]
        _row_rgb, row_lab = _rgb_median_lab(row_pixels)
        row_labs.append(row_lab)
    row_deltas = [float(delta_e_ciede2000(lab, tile_reference)) for lab in row_labs]

    bottom_start = int(round(geometry.LOGICAL_HEIGHT * 0.88))
    bottom = panel[
        bottom_start : geometry.LOGICAL_HEIGHT - GRID_MARGIN_Y,
        GRID_MARGIN_X : geometry.LOGICAL_WIDTH - GRID_MARGIN_X,
    ]
    bottom_labs = []
    for column in range(GRID_COLUMNS):
        x0 = column * bottom.shape[1] // GRID_COLUMNS
        x1 = (column + 1) * bottom.shape[1] // GRID_COLUMNS
        _bottom_rgb, bottom_lab = _rgb_median_lab(bottom[:, x0:x1])
        bottom_labs.append(bottom_lab)
    bottom_deltas = [
        float(delta_e_ciede2000(lab, tile_reference)) for lab in bottom_labs
    ]
    high_clip_fraction = float(np.mean(np.asarray(panel) >= 250))

    metrics = {
        "cell_p95_delta_e00": _metric(
            _percentile(cell_deltas, 0.95),
            pass_max=CELL_P95_PASS_DE00,
            review_max=CELL_P95_REVIEW_DE00,
        ),
        "cell_max_delta_e00": _metric(
            max(cell_deltas),
            pass_max=CELL_MAX_PASS_DE00,
            review_max=CELL_MAX_REVIEW_DE00,
        ),
        "grid_p95_delta_e00": _metric(
            _percentile(grid_deltas, 0.95),
            pass_max=GRID_P95_PASS_DE00,
            review_max=GRID_P95_REVIEW_DE00,
        ),
        "grid_max_delta_e00": _metric(
            max(grid_deltas),
            pass_max=GRID_MAX_PASS_DE00,
            review_max=GRID_MAX_REVIEW_DE00,
        ),
        "horizontal_row_max_delta_e00": _metric(
            max(row_deltas),
            pass_max=STRIPE_ROW_PASS_DE00,
            review_max=STRIPE_ROW_REVIEW_DE00,
        ),
        "bottom_p95_delta_e00": _metric(
            _percentile(bottom_deltas, 0.95),
            pass_max=BOTTOM_P95_PASS_DE00,
            review_max=BOTTOM_P95_REVIEW_DE00,
        ),
        "bottom_max_delta_e00": _metric(
            max(bottom_deltas),
            pass_max=BOTTOM_MAX_PASS_DE00,
            review_max=BOTTOM_MAX_REVIEW_DE00,
        ),
        "high_clip_fraction_rgb_channels_at_or_above_250": _metric(
            high_clip_fraction,
            pass_max=HIGH_CLIP_PASS_MAX,
            review_max=HIGH_CLIP_REVIEW_MAX,
        ),
    }
    minimum_lstar = min(cell_lstars)
    metric_state = max((item["state"] for item in metrics.values()), key=_RANK.get)
    classification = FAIL if minimum_lstar < WHITE_REFERENCE_MIN_LSTAR else metric_state
    return {
        "geometry": geometry_report,
        "full_screen_white_gate": {
            "sample_count": len(cell_lstars),
            "expected_sample_count": 64,
            "minimum_cell_lstar": round(minimum_lstar, 6),
            "median_cell_lstar": round(float(statistics.median(cell_lstars)), 6),
            "minimum_required_lstar": WHITE_REFERENCE_MIN_LSTAR,
            "passed": minimum_lstar >= WHITE_REFERENCE_MIN_LSTAR,
            "cells": cell_records,
        },
        "coarse_no_residual_gate": {
            "method": (
                "CAMERA_RELATIVE_64_CELL_PLUS_24X12_GRID_HORIZONTAL_STRIPE_"
                "AND_BOTTOM_EDGE_SCREEN"
            ),
            "panel_white_center_lab_d65": [round(value, 6) for value in reference_lab],
            "dense_grid_center_lab_d65": [round(value, 6) for value in tile_reference],
            "metrics": metrics,
            "horizontal_row_delta_e00": [round(value, 6) for value in row_deltas],
            "bottom_edge_delta_e00": [round(value, 6) for value in bottom_deltas],
            "dense_grid_tiles": tiles,
            "classification": classification,
            "clean_white_candidate": classification == PASS,
            "camera_relative_only": True,
            "absolute_colour_qualification": False,
            "low_confidence_is_not_promoted_to_pass": True,
        },
        "classification": classification,
    }


def _deep_validate_acquisition(
    *, output_root: Path, attempt: int, contract: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    acquisition = _load_acquisition(output_root, attempt, contract=contract)
    if acquisition is None or acquisition.get("acquired") is not True:
        raise W4PostWhiteCameraError("attempt is not a successful acquisition")
    acquisition_capture = acquisition.get("capture")
    if not isinstance(acquisition_capture, Mapping):
        raise W4PostWhiteCameraError("acquisition capture binding is missing")
    evidence_dir = Path(output_root).resolve() / "evidence" / f"attempt-{attempt:02d}"
    photo_path = (evidence_dir / "post-white.jpg").resolve()
    sidecar_path = (evidence_dir / "post-white.capture.json").resolve()
    snapshot_path = (evidence_dir / "action-result.json").resolve()
    photo_payload = _read_stable_regular(photo_path, label="post-white JPEG")
    sidecar_payload = _read_stable_regular(sidecar_path, label="capture sidecar")
    try:
        capture = camera.validate_capture_evidence(sidecar_path)
    except camera.CameraCaptureEvidenceError as error:
        raise W4PostWhiteCameraError(f"capture sidecar rejected: {error}") from error
    _validate_capture_lock(
        capture=capture,
        photo_payload=photo_payload,
        contract=contract,
    )
    expected_capture = {
        "capture_id": capture["capture_id"],
        "captured_at": capture["captured_at"],
        "photo": _file_binding(photo_path, photo_payload),
        "sidecar": _file_binding(sidecar_path, sidecar_payload),
        "sidecar_integrity_sha256": capture["integrity"]["sha256"],
    }
    if dict(acquisition_capture) != expected_capture:
        raise W4PostWhiteCameraError(
            "acquisition canonical JPEG/sidecar binding differs"
        )
    action_snapshot = acquisition.get("action_snapshot")
    if not isinstance(action_snapshot, Mapping):
        raise W4PostWhiteCameraError("action snapshot binding is missing")
    snapshot_payload = _read_stable_regular(snapshot_path, label="W4 action snapshot")
    if dict(action_snapshot) != _file_binding(snapshot_path, snapshot_payload):
        raise W4PostWhiteCameraError("W4 action snapshot binding differs")
    _validate_action_source(snapshot_path)
    claim_path = _claim_path(output_root, attempt)
    _claim_payload, claim = _load_json(claim_path, label="attempt claim")
    _verify_seal(claim, label="attempt claim")
    action_source = claim.get("action_source")
    if not isinstance(action_source, Mapping) or {
        "bytes": action_source.get("bytes"),
        "sha256": action_source.get("sha256"),
    } != {
        "bytes": len(snapshot_payload),
        "sha256": _sha256_bytes(snapshot_payload),
    }:
        raise W4PostWhiteCameraError(
            "attempt claim action source differs from canonical action snapshot"
        )
    return acquisition, capture, photo_payload


def _admission_claim(
    *,
    output_root: Path,
    attempt: int,
    contract: Mapping[str, Any],
    acquisition: Mapping[str, Any],
    panel_corners: Any,
) -> tuple[Path, dict[str, Any]]:
    """Permanently consume admission before corner parsing or image analysis."""

    acquisition_path = _acquisition_path(output_root, attempt)
    acquisition_payload = _read_stable_regular(
        acquisition_path, label="post-white acquisition"
    )
    claim_path = _admission_path(output_root, attempt)
    claim = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": ADMISSION_CLAIM_KIND,
            "attempt": attempt,
            "claimed_at": _now(),
            "contract_integrity_sha256": contract["integrity"]["sha256"],
            "acquisition": {
                **_file_binding(acquisition_path, acquisition_payload),
                "integrity_sha256": acquisition["integrity"]["sha256"],
            },
            "acquisition_integrity_sha256": acquisition["integrity"]["sha256"],
            # Verbatim input is evidence, not a parsed or accepted geometry claim.
            "panel_corners_input_verbatim": (
                panel_corners if isinstance(panel_corners, str) else repr(panel_corners)
            ),
            "state": "PERMANENTLY_CONSUMED_BEFORE_CORNER_PARSE_OR_ANALYSIS",
            "one_admission_maximum": True,
            "camera_invocations_during_admit": 0,
            "automatic_retry": False,
            "automatic_fallback": False,
            "automatic_chaining": False,
        }
    )
    _write_exclusive(claim_path, claim, label="post-white admission claim")
    return claim_path, claim


def _accepted_terminal_result(
    *,
    attempt: int,
    contract: Mapping[str, Any],
    admission_claim_path: Path,
    admission_claim: Mapping[str, Any],
    capture_record: Mapping[str, Any],
    photo_payload: bytes,
    corners: list[list[float]],
    evaluation: Mapping[str, Any],
    recorded_at: str,
) -> dict[str, Any]:
    if (
        evaluation.get("classification") != PASS
        or evaluation.get("full_screen_white_gate", {}).get("passed") is not True
    ):
        raise W4PostWhiteCameraError(
            "only a PASS evaluation may produce an accepted terminal result"
        )
    claim_payload = _read_stable_regular(
        admission_claim_path, label="post-white admission claim"
    )
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": RESULT_KIND,
            "attempt": attempt,
            "phase": "OFFLINE_GEOMETRY_AND_WHITE_SCREEN",
            "recorded_at": recorded_at,
            "contract_integrity_sha256": contract["integrity"]["sha256"],
            "admission_claim": {
                **_file_binding(admission_claim_path, claim_payload),
                "integrity_sha256": admission_claim["integrity"]["sha256"],
            },
            "capture_id": capture_record["capture_id"],
            "photo_sha256": _sha256_bytes(photo_payload),
            "panel_corners_tl_tr_br_bl": corners,
            "corners_apply_to_exact_acquired_jpeg": True,
            "evaluation": dict(evaluation),
            "evidence_admitted": True,
            "accepted": True,
            "terminal_state": "ACCEPTED",
            "classification": evaluation["classification"],
            "outcome": (
                "ACCEPTED_CAMERA_RELATIVE_POST_WHITE_SCREEN_"
                + str(evaluation["classification"])
            ),
            "camera_invocations_during_admit": 0,
            "automatic_retry": False,
            "automatic_fallback": False,
            "automatic_chaining": False,
        }
    )


def _rejected_terminal_result(
    *,
    attempt: int,
    contract: Mapping[str, Any],
    admission_claim_path: Path,
    admission_claim: Mapping[str, Any],
    capture_record: Mapping[str, Any],
    photo_payload: bytes,
    corners: list[list[float]] | None,
    evaluation: Mapping[str, Any] | None,
    classification: str,
    error_type: str,
    error_message: str,
    outcome: str | None = None,
) -> dict[str, Any]:
    if classification not in {REVIEW, FAIL}:
        raise W4PostWhiteCameraError(
            "rejected terminal classification must be REVIEW or FAIL"
        )
    if evaluation is not None and evaluation.get("classification") != classification:
        raise W4PostWhiteCameraError(
            "rejected evaluation and terminal classifications differ"
        )
    claim_payload = _read_stable_regular(
        admission_claim_path, label="post-white admission claim"
    )
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": RESULT_KIND,
            "attempt": attempt,
            "phase": "OFFLINE_GEOMETRY_AND_WHITE_SCREEN",
            "recorded_at": _now(),
            "contract_integrity_sha256": contract["integrity"]["sha256"],
            "admission_claim": {
                **_file_binding(admission_claim_path, claim_payload),
                "integrity_sha256": admission_claim["integrity"]["sha256"],
            },
            "capture_id": capture_record["capture_id"],
            "photo_sha256": _sha256_bytes(photo_payload),
            "panel_corners_tl_tr_br_bl": corners,
            "corners_apply_to_exact_acquired_jpeg": corners is not None,
            "evaluation": None if evaluation is None else dict(evaluation),
            "evidence_admitted": False,
            "accepted": False,
            "terminal_state": "REJECTED",
            "classification": classification,
            "outcome": outcome
            or (
                "REJECTED_CAMERA_RELATIVE_POST_WHITE_SCREEN_"
                f"{classification}_NO_SAME_ATTEMPT_READMISSION"
            ),
            "error": {"type": error_type, "message": error_message},
            "camera_invocations_during_admit": 0,
            "automatic_retry": False,
            "automatic_fallback": False,
            "automatic_chaining": False,
        }
    )


def _canonical_evaluation_or_none(
    evaluation: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    if evaluation is None:
        return None
    try:
        _canonical_json(evaluation)
    except W4PostWhiteCameraError:
        return None
    return evaluation


def admit_one(
    *, output_root: Path, attempt: int, panel_corners: str | Any
) -> dict[str, Any]:
    """Consume one admission and always write its terminal result."""

    output_root = Path(output_root).resolve()
    contract = _load_contract(output_root)
    if type(attempt) is not int or not 1 <= attempt <= MAXIMUM_ATTEMPTS:
        raise W4PostWhiteCameraError("attempt must be 1 or 2")
    # Validate only the acquired evidence before the permanent admission claim.
    # Corner parsing and all pixel analysis occur strictly after this O_EXCL write.
    acquisition, capture_record, photo_payload = _deep_validate_acquisition(
        output_root=output_root,
        attempt=attempt,
        contract=contract,
    )
    claim_path, admission_claim = _admission_claim(
        output_root=output_root,
        attempt=attempt,
        contract=contract,
        acquisition=acquisition,
        panel_corners=panel_corners,
    )
    result_path = _result_path(output_root, attempt)
    corners: list[list[float]] | None = None
    evaluation: dict[str, Any] | None = None
    fatal_error: BaseException | None = None
    try:
        corners = _normalise_panel_corners(panel_corners)
        evaluation = _evaluate_photo(photo_payload, corners)
        classification = evaluation.get("classification")
        if classification not in {PASS, REVIEW, FAIL}:
            raise W4PostWhiteCameraError(
                "post-white evaluation classification is invalid"
            )
        white_passed = evaluation.get("full_screen_white_gate", {}).get("passed")
        if white_passed is not True and classification != FAIL:
            raise W4PostWhiteCameraError(
                "a failed minimum L* boundary must classify as FAIL"
            )
        if classification == PASS:
            result = _accepted_terminal_result(
                attempt=attempt,
                contract=contract,
                admission_claim_path=claim_path,
                admission_claim=admission_claim,
                capture_record=capture_record,
                photo_payload=photo_payload,
                corners=corners,
                evaluation=evaluation,
                recorded_at=_now(),
            )
        else:
            result = _rejected_terminal_result(
                attempt=attempt,
                contract=contract,
                admission_claim_path=claim_path,
                admission_claim=admission_claim,
                capture_record=capture_record,
                photo_payload=photo_payload,
                corners=corners,
                evaluation=evaluation,
                classification=classification,
                error_type="CameraRelativePostWhiteClassification",
                error_message=(
                    f"{classification} is not eligible for terminal acceptance"
                ),
            )
    except BaseException as error:
        if not isinstance(error, Exception):
            fatal_error = error
        safe_evaluation = _canonical_evaluation_or_none(evaluation)
        if (
            safe_evaluation is not None
            and safe_evaluation.get("classification") != FAIL
        ):
            safe_evaluation = None
        result = _rejected_terminal_result(
            attempt=attempt,
            contract=contract,
            admission_claim_path=claim_path,
            admission_claim=admission_claim,
            capture_record=capture_record,
            photo_payload=photo_payload,
            corners=corners,
            evaluation=safe_evaluation,
            classification=FAIL,
            error_type=type(error).__name__,
            error_message=str(error),
            outcome="REJECTED_FAIL_CLOSED_NO_READMISSION",
        )
    _write_exclusive(result_path, result, label="post-white terminal result")
    if fatal_error is not None:
        raise fatal_error
    return result


def build_seal(*, output_root: Path) -> dict[str, Any]:
    """Deep-replay the unique admitted frame and build its independent seal."""

    output_root = Path(output_root).resolve()
    contract = _load_contract(output_root)
    claims = _load_claims(output_root, contract)
    admitted: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
    for attempt in range(1, len(claims) + 1):
        admission_claim = _load_admission(output_root, attempt, contract=contract)
        result = _load_result(output_root, attempt, contract=contract)
        if admission_claim is not None and result is None:
            raise W4PostWhiteCameraError(
                f"attempt {attempt} admission claim lacks a terminal result"
            )
        if result is not None and result.get("accepted") is True:
            if admission_claim is None:
                raise W4PostWhiteCameraError(
                    "accepted terminal result lacks an admission claim"
                )
            admitted.append((attempt, admission_claim, result))
    if len(admitted) != 1:
        raise W4PostWhiteCameraError(
            "seal requires exactly one full-screen-white admitted capture"
        )
    attempt, admission_claim, result = admitted[0]
    _acquisition, capture_record, photo_payload = _deep_validate_acquisition(
        output_root=output_root,
        attempt=attempt,
        contract=contract,
    )
    corners = result.get("panel_corners_tl_tr_br_bl")
    evaluation = _evaluate_photo(photo_payload, corners)
    if evaluation["full_screen_white_gate"]["passed"] is not True:
        raise W4PostWhiteCameraError("accepted post-white result now fails minimum L*")
    replayed = _accepted_terminal_result(
        attempt=attempt,
        contract=contract,
        admission_claim_path=_admission_path(output_root, attempt),
        admission_claim=admission_claim,
        capture_record=capture_record,
        photo_payload=photo_payload,
        corners=corners,
        evaluation=evaluation,
        recorded_at=str(result.get("recorded_at")),
    )
    if replayed != result:
        raise W4PostWhiteCameraError(
            "post-white terminal result differs on deep replay"
        )
    contract_payload = _read_stable_regular(
        _contract_path(output_root), label="post-white camera contract"
    )
    admission_path = _admission_path(output_root, attempt)
    admission_payload = _read_stable_regular(
        admission_path, label="post-white admission claim"
    )
    result_path = _result_path(output_root, attempt)
    result_payload = _read_stable_regular(
        result_path, label="post-white terminal result"
    )
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": SEAL_KIND,
            "pack_revision": PACK_REVISION,
            "output_root": output_root.as_posix(),
            "contract": {
                **_file_binding(_contract_path(output_root), contract_payload),
                "integrity_sha256": contract["integrity"]["sha256"],
            },
            "attempt_count": len(claims),
            "maximum_attempts": MAXIMUM_ATTEMPTS,
            "admitted_attempt": attempt,
            "admission_claim": {
                **_file_binding(admission_path, admission_payload),
                "integrity_sha256": admission_claim["integrity"]["sha256"],
            },
            "terminal_result": {
                **_file_binding(result_path, result_payload),
                "integrity_sha256": result["integrity"]["sha256"],
            },
            "w4_action_id": W4_ACTION_ID,
            "capture_id": result["capture_id"],
            "photo_sha256": result["photo_sha256"],
            "panel_corners_tl_tr_br_bl": result["panel_corners_tl_tr_br_bl"],
            "classification": result["classification"],
            "clean_white_candidate": result["classification"] == PASS,
            "camera_relative_only": True,
            "absolute_colour_qualification": False,
            "qualified_colour_count": 0,
            "hardware_io_performed_by_seal": False,
            "camera_access_performed_by_seal": False,
            "output_write_contract": "O_EXCL",
        }
    )


def seal_capture(
    *, output_root: Path, output_path: Path | None = None
) -> dict[str, Any]:
    result = build_seal(output_root=output_root)
    target = (
        Path(output_path)
        if output_path is not None
        else Path(output_root) / "post-white-camera-seal.json"
    )
    _write_exclusive(target, result, label="post-white camera seal")
    return result


def validate_seal(path: Path) -> dict[str, Any]:
    _payload, actual = _load_json(path, label="post-white camera seal")
    _verify_seal(actual, label="post-white camera seal")
    if actual.get("kind") != SEAL_KIND:
        raise W4PostWhiteCameraError("post-white camera seal kind differs")
    expected = build_seal(output_root=Path(str(actual.get("output_root"))))
    if actual != expected:
        raise W4PostWhiteCameraError("post-white camera seal differs on deep replay")
    return actual


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("describe")
    acquire = commands.add_parser("acquire")
    acquire.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    acquire.add_argument("--action-result", type=Path, required=True)
    acquire.add_argument("--mount-id", required=True)
    admit = commands.add_parser("admit")
    admit.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    admit.add_argument("--attempt", type=int, required=True)
    admit.add_argument("--panel-corners", required=True)
    seal_parser = commands.add_parser("seal")
    seal_parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    seal_parser.add_argument("--output", type=Path)
    validate = commands.add_parser("validate")
    validate.add_argument("seal", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "describe":
            result = build_description()
        elif args.command == "acquire":
            result = acquire_one(
                output_root=args.output_root,
                action_result_path=args.action_result,
                mount_id=args.mount_id,
            )
        elif args.command == "admit":
            result = admit_one(
                output_root=args.output_root,
                attempt=args.attempt,
                panel_corners=args.panel_corners,
            )
        elif args.command == "seal":
            result = seal_capture(
                output_root=args.output_root,
                output_path=args.output,
            )
        else:
            result = validate_seal(args.seal)
    except W4PostWhiteCameraError as error:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "kind": "mf1750-w4-post-white-camera-error-v1",
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
    if args.command == "acquire" and result.get("acquired") is not True:
        return 3
    if args.command == "admit":
        if result.get("accepted") is not True:
            return 4
        if result.get("classification") == REVIEW:
            return 3
        if result.get("classification") == FAIL:
            return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
