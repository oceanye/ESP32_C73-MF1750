#!/usr/bin/env python3
"""Build a camera-assisted human observation input for the fresh T3 AC atlas.

The tool is offline-only: it reads four already-sealed 48MP captures (the
current W3 clean-white reference followed by exactly three retained T3 atlas
frames), checks their exact action/camera/mount/settings bindings, samples the
fixed 64-cell layout, and emits a camera screening report.  It never opens a
camera, device, relay, serial port, or network connection.

The selected camera profile is the formal profile in ``README camera.md`` and
the frozen retained-atlas validator: VID_32E4:PID_4801, MJPG 4000x3000@15,
manual focus 79, white balance 4600, and exposure=-6.  The fresh-V2
exposure=-3 profile is deliberately not admitted for T3.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime
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
    mf1750_raw_p16_crossover_profile_following_human_observation as human,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t1_t2_profile_comparison as strict,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t3_ac_profile_following_successor_pack as t3_pack,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t3_camera_w4_daylight_plan as daylight_plan,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w3_discovery_successor_v2_white_pack as w3_pack,
)
from tools import mf1750_raw_p16_retained_atlas_photo_analyzer as frozen  # noqa: E402


SCHEMA_VERSION = 1
KIND = "mf1750-raw-p16-crossover-t3-camera-assisted-human-screen-v1"
SEED_KIND = "mf1750-raw-p16-crossover-t3-camera-human-seed-v1"
OFFLINE_CONTRACT_KIND = (
    "mf1750-raw-p16-crossover-t3-camera-assisted-offline-contract-v1"
)
METHOD_ID = "w3-white-plus-three-t3-exp6-48mp-human-camera-screen-v1"
PARTIAL_KIND = (
    "mf1750-raw-p16-crossover-t3-partial-dual-3x8-camera-screen-v1"
)
PARTIAL_METHOD_ID = "w3-white-plus-three-t3-exp6-partial-dual-3x8-v1"
PARTIAL_MODE = "PARTIAL_DUAL_3X8_TOP_ROWS_V1"
PARTIAL_SELECTED_ROWS = (0, 1, 2)
PARTIAL_SELECTED_COLUMNS = tuple(range(8))
PARTIAL_SELECTED_CELL_COUNT = 48
PARTIAL_REPLICATES_PER_CODE_PER_CONTROLLER_PER_FRAME = 3
INTEGRITY_ALGORITHM = strict.INTEGRITY_ALGORITHM

EXPECTED_CAMERA_PROFILE = deepcopy(frozen.EXPECTED_CAMERA_PROFILE)
EXPECTED_EXPOSURE = -6.0
EXPECTED_PHOTO_WIDTH = 4000
EXPECTED_PHOTO_HEIGHT = 3000
EXPECTED_FRAME_COUNT = 3
WHITE_REFERENCE_MIN_LSTAR = 25.0
WHITE_REFERENCE_REVIEW_LSTAR = 35.0
NORMALIZATION_TARGET_RGB = 220.0

PASS = "PASS"
REVIEW = "REVIEW"
FAIL = "FAIL"
RANK = {PASS: 0, REVIEW: 1, FAIL: 2}

# The frozen 5.4A daylight plan owns the decisive four-copy 8/12 boundary.
# The old single-frame 3/5 position heuristic is not a decision gate here.
POSITION_PASS_MAX_DE00 = 8.0
POSITION_REVIEW_MAX_DE00 = 12.0
TEMPORAL_PASS_MAX_DE00 = 3.0
TEMPORAL_REVIEW_MAX_DE00 = 6.0
CONTROL_PASS_MAX_DE00 = frozen.PAIR_SIMILAR_DE00
CONTROL_REVIEW_MAX_DE00 = frozen.PAIR_OBVIOUS_DE00
STRIPE_PASS_MAX_DE00 = 3.0
STRIPE_REVIEW_MAX_DE00 = 5.0
RESIDUAL_P95_PASS_MAX_DE00 = 3.0
RESIDUAL_P95_REVIEW_MAX_DE00 = 5.0
RESIDUAL_MAX_PASS_MAX_DE00 = 5.0
RESIDUAL_MAX_REVIEW_MAX_DE00 = 8.0
BOTTOM_P95_PASS_MAX_DE00 = 3.0
BOTTOM_P95_REVIEW_MAX_DE00 = 5.0
BOTTOM_MAX_PASS_MAX_DE00 = 5.0
BOTTOM_MAX_REVIEW_MAX_DE00 = 8.0
WHITE_HIGH_CLIP_PASS_MAX = 0.005
WHITE_HIGH_CLIP_REVIEW_MAX = 0.02
WHITE_MAD_PASS_MAX = 10.0
WHITE_MAD_REVIEW_MAX = 20.0
ALIGNMENT_SHIFT_PASS_MAX_PX = 0.75
ALIGNMENT_SHIFT_REVIEW_MAX_PX = 2.0
ALIGNMENT_RESPONSE_PASS_MIN = 0.50
ALIGNMENT_RESPONSE_REVIEW_MIN = 0.20
CORNER_DRIFT_PASS_MAX_PHOTO_PX = 12.0
CORNER_DRIFT_REVIEW_MAX_PHOTO_PX = 30.0

SEED_KEYS = {
    "schema_version",
    "kind",
    "stage",
    "observed_at",
    "operator",
    "supervision",
    "controls_verbatim",
    "artifacts",
    "controllers",
}
SEED_CONTROLLER_KEYS = {
    "code_labels_verbatim",
    "all_four_replicates_human_confirmed",
    "all_labels_stable_human_confirmed",
}


class T3CameraObservationError(RuntimeError):
    """Raised when camera evidence or output cannot satisfy the exact screen."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise T3CameraObservationError(message)


def _classification(value: float, *, pass_max: float, review_max: float) -> str:
    if value <= pass_max:
        return PASS
    if value <= review_max:
        return REVIEW
    return FAIL


def _minimum_classification(value: float, *, pass_min: float, review_min: float) -> str:
    if value >= pass_min:
        return PASS
    if value >= review_min:
        return REVIEW
    return FAIL


def _p95(values: Sequence[float]) -> float:
    _require(bool(values), "cannot calculate p95 of an empty sequence")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * 0.95
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _median_vector(values: Sequence[Sequence[float]]) -> list[float]:
    _require(bool(values), "cannot calculate a vector median of no values")
    return [statistics.median(row[index] for row in values) for index in range(3)]


def _rounded_vector(value: Sequence[float], digits: int = 9) -> list[float]:
    return [round(float(component), digits) for component in value]


def _serialize(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _read_json(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        return strict._load_json(Path(path), label=label)  # noqa: SLF001
    except strict.CrossoverProfileComparisonError as error:
        raise T3CameraObservationError(str(error)) from error


def _read_bytes(path: Path, *, label: str) -> bytes:
    try:
        return strict._read_stable_regular(Path(path), label=label)  # noqa: SLF001
    except strict.CrossoverProfileComparisonError as error:
        raise T3CameraObservationError(str(error)) from error


def _file_binding(path: Path, payload: bytes) -> dict[str, Any]:
    return {
        "path": Path(path).resolve().as_posix(),
        "bytes": len(payload),
        "file_sha256": strict.sha256_bytes(payload),
    }


def _parse_time(value: Any, *, label: str) -> datetime:
    _require(isinstance(value, str) and bool(value), f"{label} is missing")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise T3CameraObservationError(f"{label} is not RFC3339") from error
    _require(parsed.tzinfo is not None, f"{label} has no timezone")
    return parsed


def _capture_alignment(capture: Mapping[str, Any]) -> dict[str, Any]:
    record = capture["camera"]
    return {
        "camera_id": record["camera_id"],
        "instance_id": record["instance_id"],
        "backend": record["backend"],
        "mount_id": capture["coverage"]["mount_id"],
        "requested_settings": record["requested_settings"],
        "effective_settings_before_frame": record["effective_settings_before_frame"],
        "effective_settings_after_frame": record["effective_settings_after_frame"],
        "photo_width": capture["photo"]["width"],
        "photo_height": capture["photo"]["height"],
    }


def _resolve_sidecar_path(sidecar_path: Path, declared: Any, *, label: str) -> Path:
    _require(isinstance(declared, str) and bool(declared), f"{label} path is missing")
    return (Path(sidecar_path).resolve().parent / declared).resolve()


def _validate_camera_profile_choice() -> None:
    _require(
        EXPECTED_CAMERA_PROFILE
        == {
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
        },
        "T3 camera profile no longer matches README/frozen exposure=-6",
    )


def _action_context(path: Path, *, stage: str) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved = Path(path).resolve()
    _payload, root = _read_json(resolved, label=f"{stage} action result")
    if stage in (human.AC_STAGE, human.AC_V2_STAGE):
        binding = human._validate_action_result(resolved, stage=stage)  # noqa: SLF001
        binding["frame_sha256"] = root["action"]["frame_sha256"]
        return binding, root
    if stage == w3_pack.STAGE:
        binding = human._validate_w3_white_action_result(resolved)  # noqa: SLF001
        binding["frame_sha256"] = root["action"]["frame_sha256"]
        return binding, root
    raise T3CameraObservationError(f"unsupported action stage {stage!r}")


def _load_capture(
    *,
    photo_path: Path,
    sidecar_path: Path,
    action_result_path: Path,
    expected_action: Mapping[str, Any],
    label: str,
    expected_coverage_scope: str = camera.COVERAGE_FULL,
) -> tuple[dict[str, Any], Any]:
    photo_path = Path(photo_path).resolve()
    sidecar_path = Path(sidecar_path).resolve()
    action_result_path = Path(action_result_path).resolve()
    try:
        capture = camera.validate_capture_evidence(sidecar_path)
        camera_lock = frozen._validate_fixed_capture(  # noqa: SLF001
            capture, expected_coverage_scope=expected_coverage_scope
        )
    except (
        camera.CameraCaptureEvidenceError,
        frozen.RawP16PhotoAnalysisError,
    ) as error:
        raise T3CameraObservationError(
            f"{label} exact README exposure=-6 capture rejected: {error}"
        ) from error
    sidecar_action = capture["action_result"]
    sidecar_photo = capture["photo"]
    _require(
        _resolve_sidecar_path(
            sidecar_path, sidecar_action["path"], label=f"{label} action"
        )
        == action_result_path,
        f"{label} action path differs from explicit input",
    )
    _require(
        _resolve_sidecar_path(
            sidecar_path, sidecar_photo["path"], label=f"{label} photo"
        )
        == photo_path,
        f"{label} photo path differs from explicit input",
    )
    photo_payload = _read_bytes(photo_path, label=f"{label} photo")
    action_payload = _read_bytes(action_result_path, label=f"{label} action")
    _require(
        sidecar_photo["sha256"] == strict.sha256_bytes(photo_payload)
        and sidecar_action["file_sha256"] == strict.sha256_bytes(action_payload),
        f"{label} sidecar photo/action SHA-256 differs",
    )
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
        _require(
            capture.get(field) == expected_action.get(field),
            f"{label} capture {field} differs from exact action",
        )
    try:
        rgb = geometry.base._decode_rgb(photo_payload)  # noqa: SLF001
    except geometry.CrossoverPhotoAnalysisError as error:
        raise T3CameraObservationError(
            f"{label} JPEG decode failed: {error}"
        ) from error
    _require(
        rgb.shape[1] == EXPECTED_PHOTO_WIDTH and rgb.shape[0] == EXPECTED_PHOTO_HEIGHT,
        f"{label} is not exact 4000x3000",
    )
    sidecar_payload = _read_bytes(sidecar_path, label=f"{label} sidecar")
    binding = {
        "label": label,
        "capture_id": capture["capture_id"],
        "captured_at": capture["captured_at"],
        "photo": _file_binding(photo_path, photo_payload),
        "capture_sidecar": {
            **_file_binding(sidecar_path, sidecar_payload),
            "canonical_integrity_sha256": capture["integrity"]["sha256"],
        },
        "action_id": capture["action_id"],
        "camera_lock": camera_lock,
        "capture_alignment": _capture_alignment(capture),
    }
    return binding, rgb


def _exact_keys(value: Any, keys: set[str], *, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    _require(set(value) == keys, f"{label} keys differ")
    return value


def _text(value: Any, *, label: str, maximum: int = 4096) -> str:
    _require(isinstance(value, str), f"{label} must be text")
    _require(bool(value.strip()), f"{label} must not be blank")
    _require(len(value) <= maximum, f"{label} is too long")
    return value


def _validate_seed(root: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the small human card without inventing any operator facts."""

    source = _exact_keys(root, SEED_KEYS, label="human seed")
    _require(source["schema_version"] == SCHEMA_VERSION, "human seed schema differs")
    _require(source["kind"] == SEED_KIND, "human seed kind differs")
    _require(source["stage"] == human.AC_STAGE, "human seed stage differs")
    if source["observed_at"] is not None:
        _parse_time(source["observed_at"], label="human seed observed_at")

    operator = _exact_keys(
        source["operator"], human.OPERATOR_KEYS, label="human seed operator"
    )
    _text(operator["operator_id"], label="operator.operator_id", maximum=128)
    _text(operator["operator_verbatim"], label="operator.operator_verbatim")
    _text(source["controls_verbatim"], label="controls_verbatim")
    _require(
        not operator["operator_id"].startswith("FILL_")
        and not operator["operator_verbatim"].startswith("FILL_")
        and not source["controls_verbatim"].startswith("FILL_"),
        "human seed still contains an unfilled template sentinel",
    )

    supervision = _exact_keys(
        source["supervision"],
        human.SUPERVISION_KEYS,
        label="human seed supervision",
    )
    _text(supervision["supervisor_id"], label="supervision.supervisor_id", maximum=128)
    _text(
        supervision["supervision_verbatim"],
        label="supervision.supervision_verbatim",
    )
    for field in human.SUPERVISION_KEYS - {
        "supervisor_id",
        "j2_state_during_observation",
        "supervision_verbatim",
    }:
        _require(
            type(supervision[field]) is bool or supervision[field] is None,
            f"supervision.{field} must be boolean or null",
        )
    _require(
        supervision["j2_state_during_observation"] in {"ON", "OFF", "UNKNOWN"},
        "supervision.j2_state_during_observation differs",
    )

    artifacts = _exact_keys(
        source["artifacts"], set(human.ARTIFACT_FIELDS), label="human seed artifacts"
    )
    for field in human.ARTIFACT_FIELDS:
        item = _exact_keys(
            artifacts[field],
            {"observed", "operator_verbatim"},
            label=f"human seed artifacts.{field}",
        )
        _require(
            type(item["observed"]) is bool or item["observed"] is None,
            f"artifacts.{field}.observed must be boolean or null",
        )
        _text(item["operator_verbatim"], label=f"artifacts.{field}.operator_verbatim")

    controllers = _exact_keys(
        source["controllers"], set(human.CONTROLLERS), label="human seed controllers"
    )
    for controller in human.CONTROLLERS:
        item = _exact_keys(
            controllers[controller],
            SEED_CONTROLLER_KEYS,
            label=f"human seed controllers.{controller}",
        )
        labels = item["code_labels_verbatim"]
        _require(
            isinstance(labels, list) and len(labels) == 8,
            f"controllers.{controller}.code_labels_verbatim must contain eight labels",
        )
        for code, label in enumerate(labels):
            _text(
                label,
                label=f"controllers.{controller}.code_labels_verbatim[{code}]",
                maximum=128,
            )
            _require(
                not label.startswith("FILL_"),
                f"controllers.{controller}.code_labels_verbatim[{code}] is unfilled",
            )
        for field in (
            "all_four_replicates_human_confirmed",
            "all_labels_stable_human_confirmed",
        ):
            _require(
                type(item[field]) is bool or item[field] is None,
                f"controllers.{controller}.{field} must be boolean or null",
            )
    return deepcopy(dict(source))


def _compact_from_seed(seed: Mapping[str, Any]) -> dict[str, Any] | None:
    for controller in human.CONTROLLERS:
        item = seed["controllers"][controller]
        if (
            item["all_four_replicates_human_confirmed"] is not True
            or item["all_labels_stable_human_confirmed"] is not True
        ):
            return None
    compact = {
        "schema_version": human.SCHEMA_VERSION,
        "kind": human.COMPACT_INPUT_KIND,
        "stage": human.AC_STAGE,
        "observed_at": seed["observed_at"],
        "operator": deepcopy(seed["operator"]),
        "supervision": deepcopy(seed["supervision"]),
        "controls_verbatim": seed["controls_verbatim"],
        "artifacts": deepcopy(seed["artifacts"]),
        "controllers": {
            controller: {
                "code_labels_verbatim": list(
                    seed["controllers"][controller]["code_labels_verbatim"]
                ),
                "all_four_replicates_consistent": True,
                "four_replicates_consistent_by_code": None,
                "all_labels_stable": True,
                "stable_by_code": None,
            }
            for controller in human.CONTROLLERS
        },
    }
    try:
        expanded, expansion = human._expand_compact_operator_input(  # noqa: SLF001
            compact, expected_stage=human.AC_STAGE
        )
    except human.HumanObservationError as error:
        raise T3CameraObservationError(
            f"generated compact human input is invalid: {error}"
        ) from error
    _require(len(expanded["cells"]) == 64, "compact input did not expand to 64 cells")
    _require(
        expansion["expanded_cell_count"] == 64,
        "compact expansion accounting differs",
    )
    return compact


def _validate_offline_contract() -> dict[str, Any]:
    _validate_camera_profile_choice()
    _require(
        camera.TARGET_CAMERA_LOGICAL_ID == "USB_VID_32E4_PID_4801"
        and camera.TARGET_CAMERA_FRIENDLY_NAME == "48MP USB Camera"
        and camera.TARGET_CAMERA_USB_TOKEN == "vid_32e4&pid_4801"
        and camera.EXCLUDED_BINOCULAR_USB_TOKEN == "vid_1bcf&pid_0b15",
        "48MP camera identity contract differs",
    )
    plan = t3_pack.HUMAN_OBSERVATION_PLAN
    _require(
        plan.get("camera_required_for_decision") is False
        and plan.get("camera_evidence_optional") is True
        and plan.get("required_retained_camera_frame_count") == 0,
        "T3 human-primary optional-camera boundary differs",
    )
    report = t3_pack.build_report()
    geometry_contract = report["contract"]["geometry"]
    _require(
        geometry_contract.get("grid_rows") == 4
        and geometry_contract.get("grid_columns_per_controller") == 8
        and geometry_contract.get("row_codes") == [list(row) for row in human.CODE_ROWS]
        and geometry_contract.get("samples_per_code_per_controller_per_frame") == 4
        and geometry_contract.get("same_layout_both_controllers") is True
        and geometry_contract.get("background_code") == 7,
        "T3 fixed 64-cell geometry contract differs",
    )
    try:
        frozen_daylight = daylight_plan.build_plan()
    except daylight_plan.DaylightPlanError as error:
        raise T3CameraObservationError(
            f"frozen daylight plan rejected: {error}"
        ) from error
    coarse = frozen_daylight["camera_screening"]["coarse_thresholds"]
    _require(
        coarse["white_reference_min_lstar"] == WHITE_REFERENCE_MIN_LSTAR
        and coarse["position_delta_e00_pass_max"] == POSITION_PASS_MAX_DE00
        and coarse["position_delta_e00_review_max"] == POSITION_REVIEW_MAX_DE00
        and coarse["temporal_delta_e76_pass_max"] == TEMPORAL_PASS_MAX_DE00
        and coarse["temporal_delta_e76_review_max"] == TEMPORAL_REVIEW_MAX_DE00,
        "camera analyzer thresholds differ from frozen 5.4A daylight plan",
    )
    plan_profile = frozen_daylight["camera_contract"]["profile"]
    _require(
        all(
            plan_profile.get(field) == value
            for field, value in EXPECTED_CAMERA_PROFILE.items()
        )
        and plan_profile.get("fresh_v2_exposure_minus_3_profile_permitted") is False,
        "camera analyzer profile differs from frozen daylight plan",
    )
    return {
        "profile_authority": "README camera.md + frozen retained-atlas schema-v2 validator",
        "camera_id": camera.TARGET_CAMERA_LOGICAL_ID,
        "friendly_name": camera.TARGET_CAMERA_FRIENDLY_NAME,
        "required_usb_token": camera.TARGET_CAMERA_USB_TOKEN.upper(),
        "excluded_usb_token": camera.EXCLUDED_BINOCULAR_USB_TOKEN.upper(),
        "backend": "DSHOW",
        "requested_profile": deepcopy(EXPECTED_CAMERA_PROFILE),
        "selected_exposure": EXPECTED_EXPOSURE,
        "fresh_v2_exposure_minus_3_admitted": False,
        "white_and_atlas_complete_setting_equality_required": True,
        "retained_atlas_frame_count_for_this_optional_screen": EXPECTED_FRAME_COUNT,
        "t3_pack_camera_required_for_decision": False,
        "camera_screen_is_supplemental_to_human_primary_observation": True,
        "frozen_daylight_plan_revision": frozen_daylight["plan_revision"],
        "decisive_four_replicate_delta_e00_thresholds": {
            "pass_max": POSITION_PASS_MAX_DE00,
            "review_max": POSITION_REVIEW_MAX_DE00,
        },
        "legacy_single_frame_position_3_5_is_decisive": False,
    }


def _validate_white_authority(path: Path) -> dict[str, Any]:
    resolved = Path(path).resolve()
    try:
        authority, payload = human.validate_clean_white_observation(resolved)
    except human.HumanObservationError as error:
        raise T3CameraObservationError(
            f"current W3 clean-white human authority rejected: {error}"
        ) from error
    _require(
        authority["stage"] == w3_pack.STAGE
        and authority["authority"]["operator_reported_clean_white"] is True
        and authority["authority"]["operator_verbatim_preserved"] is True
        and authority["authority"]["action_complete_exactly_bound"] is True,
        "current W3 authority does not bind the clean-white human report",
    )
    return {
        **_file_binding(resolved, payload),
        "canonical_integrity_sha256": authority["integrity"]["sha256"],
        "action_id": authority["action_result_binding"]["action_id"],
        "operator_id": authority["raw_operator_report"]["operator_id"],
        "operator_verbatim": authority["raw_operator_report"]["operator_verbatim"],
        "camera_confirmation_claimed_by_authority": authority["authority"][
            "camera_confirmation_claimed"
        ],
    }


def _roi(panel: Any, cell: Mapping[str, Any], *, inner_fraction: float = 0.6) -> Any:
    x, y, width, height = cell["logical_bounds"]
    margin_x = width * (1.0 - inner_fraction) / 2.0
    margin_y = height * (1.0 - inner_fraction) / 2.0
    x0 = int(math.ceil(x + margin_x))
    x1 = int(math.floor(x + width - margin_x))
    y0 = int(math.ceil(y + margin_y))
    y1 = int(math.floor(y + height - margin_y))
    _require(x1 > x0 and y1 > y0, f"{cell['cell_id']} logical ROI is empty")
    return panel[y0:y1, x0:x1]


def _rgb_lab_summary(pixels: Any) -> tuple[list[float], list[float], list[float]]:
    _cv2, np = geometry.base._import_cv()  # noqa: SLF001
    flat = np.asarray(pixels, dtype=np.float64).reshape(-1, 3)
    _require(
        len(flat) > 0 and np.all(np.isfinite(flat)), "pixel ROI is empty or non-finite"
    )
    median = np.median(flat, axis=0)
    mad = np.median(np.abs(flat - median), axis=0)
    rgb8 = tuple(int(round(float(np.clip(value, 0.0, 255.0)))) for value in median)
    lab = srgb8_to_lab(rgb8)
    return _rounded_vector(median, 6), _rounded_vector(mad, 6), _rounded_vector(lab, 6)


def _tile_labs(pixels: Any, *, rows: int = 3, columns: int = 3) -> list[list[float]]:
    _cv2, np = geometry.base._import_cv()  # noqa: SLF001
    height, width = pixels.shape[:2]
    result: list[list[float]] = []
    for row in range(rows):
        y0 = row * height // rows
        y1 = (row + 1) * height // rows
        for column in range(columns):
            x0 = column * width // columns
            x1 = (column + 1) * width // columns
            _median, _mad, lab = _rgb_lab_summary(np.asarray(pixels)[y0:y1, x0:x1])
            result.append(lab)
    return result


def _band_labs(pixels: Any, *, axis: int) -> list[list[float]]:
    _cv2, np = geometry.base._import_cv()  # noqa: SLF001
    height, width = pixels.shape[:2]
    result: list[list[float]] = []
    for index in range(3):
        if axis == 0:
            part = np.asarray(pixels)[
                index * height // 3 : (index + 1) * height // 3, :
            ]
        else:
            part = np.asarray(pixels)[:, index * width // 3 : (index + 1) * width // 3]
        _median, _mad, lab = _rgb_lab_summary(part)
        result.append(lab)
    return result


def _warp_panel(rgb: Any, homography_logical_to_photo: Any) -> Any:
    cv2, np = geometry.base._import_cv()  # noqa: SLF001
    inverse = np.linalg.inv(np.asarray(homography_logical_to_photo, dtype=np.float64))
    warped = cv2.warpPerspective(
        np.asarray(rgb),
        inverse,
        (geometry.LOGICAL_WIDTH, geometry.LOGICAL_HEIGHT),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    _require(
        warped.shape == (geometry.LOGICAL_HEIGHT, geometry.LOGICAL_WIDTH, 3),
        "logical panel warp shape differs",
    )
    return warped


def _warp_partial_panel(
    rgb: Any, homographies_logical_to_photo: Mapping[str, Any]
) -> Any:
    """Warp only the selected controller blocks into logical coordinates."""

    cv2, np = geometry.base._import_cv()  # noqa: SLF001
    _require(
        isinstance(homographies_logical_to_photo, Mapping)
        and set(homographies_logical_to_photo) == {"CS1", "CS2"},
        "partial homographies must contain exactly CS1 and CS2",
    )
    panel = np.zeros(
        (geometry.LOGICAL_HEIGHT, geometry.LOGICAL_WIDTH, 3), dtype=np.uint8
    )
    y0 = t3_pack.GRID_Y_BY_ROW[PARTIAL_SELECTED_ROWS[0]]
    y1 = (
        t3_pack.GRID_Y_BY_ROW[PARTIAL_SELECTED_ROWS[-1]]
        + geometry.pack.CELL_HEIGHT
    )
    for controller_index, controller in enumerate(("CS1", "CS2")):
        inverse = np.linalg.inv(
            np.asarray(
                homographies_logical_to_photo[controller], dtype=np.float64
            )
        )
        warped = cv2.warpPerspective(
            np.asarray(rgb),
            inverse,
            (geometry.LOGICAL_WIDTH, geometry.LOGICAL_HEIGHT),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        x0 = controller_index * geometry.CONTROLLER_WIDTH + geometry.pack.GRID_X0
        x1 = (
            x0
            + (geometry.pack.GRID_COLUMNS - 1)
            * (geometry.pack.CELL_WIDTH + geometry.pack.GAP_X)
            + geometry.pack.CELL_WIDTH
        )
        panel[y0:y1, x0:x1] = warped[y0:y1, x0:x1]
    return panel


def _alignment_screen(atlas_panels: Sequence[Any]) -> dict[str, Any]:
    cv2, np = geometry.base._import_cv()  # noqa: SLF001
    reference = cv2.cvtColor(
        np.asarray(atlas_panels[0], dtype=np.uint8), cv2.COLOR_RGB2GRAY
    ).astype(np.float32)
    pairs = []
    states = []
    for frame_index in range(1, len(atlas_panels)):
        candidate = cv2.cvtColor(
            np.asarray(atlas_panels[frame_index], dtype=np.uint8),
            cv2.COLOR_RGB2GRAY,
        ).astype(np.float32)
        (shift_x, shift_y), response = cv2.phaseCorrelate(reference, candidate)
        magnitude = math.hypot(float(shift_x), float(shift_y))
        shift_state = _classification(
            magnitude,
            pass_max=ALIGNMENT_SHIFT_PASS_MAX_PX,
            review_max=ALIGNMENT_SHIFT_REVIEW_MAX_PX,
        )
        response_state = _minimum_classification(
            float(response),
            pass_min=ALIGNMENT_RESPONSE_PASS_MIN,
            review_min=ALIGNMENT_RESPONSE_REVIEW_MIN,
        )
        state = max((shift_state, response_state), key=RANK.get)
        states.append(state)
        pairs.append(
            {
                "reference_frame_index": 0,
                "candidate_frame_index": frame_index,
                "shift_logical_px": [
                    round(float(shift_x), 6),
                    round(float(shift_y), 6),
                ],
                "shift_magnitude_logical_px": round(magnitude, 6),
                "phase_correlation_response": round(float(response), 9),
                "diagnostic_state": state,
            }
        )
    state = max(states, key=RANK.get) if states else FAIL
    return {
        "method": "OPENCV_PHASE_CORRELATION_ON_SHARED_HOMOGRAPHY_LOGICAL_PANELS",
        "pairs": pairs,
        "thresholds": {
            "shift_pass_max_logical_px": ALIGNMENT_SHIFT_PASS_MAX_PX,
            "shift_review_max_logical_px": ALIGNMENT_SHIFT_REVIEW_MAX_PX,
            "response_pass_min": ALIGNMENT_RESPONSE_PASS_MIN,
            "response_review_min": ALIGNMENT_RESPONSE_REVIEW_MIN,
        },
        "diagnostic_state": state,
    }


def _geometry_drift_screen(
    geometry_reports: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    _cv2, np = geometry.base._import_cv()  # noqa: SLF001
    _require(len(geometry_reports) == 4, "white plus three geometry reports required")
    corners = [
        np.asarray(item["supplied_panel_corners_tl_tr_br_bl"], dtype=np.float64)
        for item in geometry_reports
    ]
    pairs = []
    maximum = 0.0
    labels = ("WHITE", "ATLAS_1", "ATLAS_2", "ATLAS_3")
    for first in range(len(corners)):
        for second in range(first + 1, len(corners)):
            distances = np.linalg.norm(corners[first] - corners[second], axis=1)
            pair_maximum = float(np.max(distances))
            maximum = max(maximum, pair_maximum)
            pairs.append(
                {
                    "first": labels[first],
                    "second": labels[second],
                    "corresponding_corner_distances_photo_px": [
                        round(float(value), 6) for value in distances.tolist()
                    ],
                    "maximum_photo_px": round(pair_maximum, 6),
                }
            )
    return {
        "method": "PAIRWISE_TL_TR_BR_BL_DISTANCE_IN_4000X3000_PHOTO_COORDINATES",
        "pairs": pairs,
        "maximum_corresponding_corner_drift_photo_px": _metric(
            maximum,
            pass_max=CORNER_DRIFT_PASS_MAX_PHOTO_PX,
            review_max=CORNER_DRIFT_REVIEW_MAX_PHOTO_PX,
        ),
        "independent_cell_lattice_reprojection_proven": False,
    }


def _partial_geometry_drift_screen(
    geometry_reports: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Require fixed-mount stability across the eight selected block corners."""

    _cv2, np = geometry.base._import_cv()  # noqa: SLF001
    _require(len(geometry_reports) == 4, "white plus three geometry reports required")
    blocks = []
    for report in geometry_reports:
        supplied = report.get("supplied_block_corners_tl_tr_br_bl")
        _require(
            isinstance(supplied, Mapping) and set(supplied) == {"CS1", "CS2"},
            "partial geometry block metadata differs",
        )
        blocks.append(
            np.concatenate(
                [
                    np.asarray(supplied[controller], dtype=np.float64)
                    for controller in ("CS1", "CS2")
                ],
                axis=0,
            )
        )
    pairs = []
    states = []
    labels = ("WHITE", "ATLAS_1", "ATLAS_2", "ATLAS_3")
    for first in range(len(blocks)):
        for second in range(first + 1, len(blocks)):
            distances = np.linalg.norm(blocks[first] - blocks[second], axis=1)
            maximum = float(np.max(distances))
            rms = math.sqrt(float(np.mean(distances * distances)))
            state = PASS if rms <= 8.0 and maximum <= 15.0 else FAIL
            states.append(state)
            pairs.append(
                {
                    "first": labels[first],
                    "second": labels[second],
                    "eight_corresponding_corner_distances_photo_px": [
                        round(float(value), 6) for value in distances.tolist()
                    ],
                    "rms_photo_px": round(rms, 6),
                    "maximum_photo_px": round(maximum, 6),
                    "maximum_allowed_rms_photo_px": 8.0,
                    "maximum_allowed_photo_px": 15.0,
                    "diagnostic_state": state,
                }
            )
    return {
        "method": "PAIRWISE_EIGHT_SELECTED_BLOCK_CORNER_DISTANCE",
        "pairs": pairs,
        "diagnostic_state": max(states, key=RANK.get),
        "fixed_mount_drift_gate_passed": all(state == PASS for state in states),
        "automatic_roi_expansion": False,
        "full_panel_geometry_evaluated": False,
        "outside_roi": "NOT_EVALUATED_OUTSIDE_SELECTED_ROI",
    }


def _metric(value: float, *, pass_max: float, review_max: float) -> dict[str, Any]:
    return {
        "value": round(float(value), 6),
        "pass_max": pass_max,
        "review_max": review_max,
        "diagnostic_state": _classification(
            float(value), pass_max=pass_max, review_max=review_max
        ),
    }


def _screen_logical_panels(
    white_panel: Any,
    atlas_panels: Sequence[Any],
    *,
    selected_rows: Sequence[int],
    partial_mode: bool,
) -> dict[str, Any]:
    """Screen already-warped logical panels; useful for deterministic tests."""

    _cv2, np = geometry.base._import_cv()  # noqa: SLF001
    _require(
        len(atlas_panels) == EXPECTED_FRAME_COUNT, "exactly three atlas panels required"
    )
    expected_shape = (geometry.LOGICAL_HEIGHT, geometry.LOGICAL_WIDTH, 3)
    panels = [np.asarray(white_panel)] + [np.asarray(item) for item in atlas_panels]
    _require(
        all(item.shape == expected_shape for item in panels),
        "logical panel shape differs",
    )
    _require(
        all(np.all(np.isfinite(item.astype(np.float64))) for item in panels),
        "logical panel contains non-finite pixels",
    )
    white = np.asarray(white_panel, dtype=np.float64)
    atlases = [np.asarray(item, dtype=np.float64) for item in atlas_panels]
    normalized = [
        np.clip(NORMALIZATION_TARGET_RGB * atlas / np.maximum(white, 1.0), 0.0, 255.0)
        for atlas in atlases
    ]
    all_cells = geometry._all_logical_cells()  # noqa: SLF001
    _require(len(all_cells) == 64, "fixed logical layout no longer has 64 cells")
    rows = tuple(selected_rows)
    expected_rows = PARTIAL_SELECTED_ROWS if partial_mode else tuple(range(4))
    _require(rows == expected_rows, "selected logical rows differ from mode")
    cells = [cell for cell in all_cells if cell["row"] in rows]
    expected_cell_count = 48 if partial_mode else 64
    expected_replicates = 3 if partial_mode else 4
    _require(
        len(cells) == expected_cell_count,
        "selected logical layout cell count differs",
    )

    white_cells: list[dict[str, Any]] = []
    white_lstar_values: list[float] = []
    white_mad_values: list[float] = []
    white_clip_values: list[float] = []
    for cell in cells:
        pixels = _roi(white, cell)
        median, mad, lab = _rgb_lab_summary(pixels)
        clip_fraction = float(np.mean(np.asarray(pixels) >= 250.0))
        white_lstar_values.append(lab[0])
        white_mad_values.append(max(mad))
        white_clip_values.append(clip_fraction)
        white_cells.append(
            {
                "cell_id": cell["cell_id"],
                "controller": f"CS{cell['controller'] + 1}",
                "row": cell["row"],
                "column": cell["column"],
                "code": cell["code"],
                "camera_relative_rgb_median": median,
                "camera_relative_rgb_mad": mad,
                "camera_relative_lab_d65": lab,
                "high_clip_fraction_rgb_at_or_above_250": round(clip_fraction, 9),
            }
        )
    minimum_white_lstar = min(white_lstar_values)
    if minimum_white_lstar < WHITE_REFERENCE_MIN_LSTAR:
        white_lstar_state = FAIL
    elif minimum_white_lstar < WHITE_REFERENCE_REVIEW_LSTAR:
        white_lstar_state = REVIEW
    else:
        white_lstar_state = PASS
    white_quality = {
        "minimum_cell_lstar": round(minimum_white_lstar, 6),
        "minimum_lstar_hard_boundary": WHITE_REFERENCE_MIN_LSTAR,
        "minimum_lstar_review_boundary": WHITE_REFERENCE_REVIEW_LSTAR,
        "minimum_lstar_diagnostic_state": white_lstar_state,
        "maximum_cell_rgb_mad": _metric(
            max(white_mad_values),
            pass_max=WHITE_MAD_PASS_MAX,
            review_max=WHITE_MAD_REVIEW_MAX,
        ),
        "maximum_cell_high_clip_fraction": _metric(
            max(white_clip_values),
            pass_max=WHITE_HIGH_CLIP_PASS_MAX,
            review_max=WHITE_HIGH_CLIP_REVIEW_MAX,
        ),
        "cells": white_cells,
    }

    frame_cells: list[list[dict[str, Any]]] = []
    labs_by_frame_key: list[dict[tuple[int, int, int], list[float]]] = []
    normalized_clip_values: list[float] = []
    residual_values: list[float] = []
    horizontal_values: list[float] = []
    vertical_values: list[float] = []
    for frame_index, (atlas, normalized_panel) in enumerate(zip(atlases, normalized)):
        current: list[dict[str, Any]] = []
        by_key: dict[tuple[int, int, int], list[float]] = {}
        for cell in cells:
            raw_pixels = _roi(atlas, cell)
            normalized_pixels = _roi(normalized_panel, cell)
            raw_median, raw_mad, _raw_lab = _rgb_lab_summary(raw_pixels)
            median, mad, lab = _rgb_lab_summary(normalized_pixels)
            by_key[(cell["controller"], cell["row"], cell["column"])] = lab
            normalized_clip_values.append(
                float(np.mean(np.asarray(normalized_pixels) >= 254.5))
            )
            tile_de00 = [
                float(delta_e_ciede2000(tile_lab, lab))
                for tile_lab in _tile_labs(normalized_pixels)
            ]
            horizontal_de00 = [
                float(delta_e_ciede2000(band_lab, lab))
                for band_lab in _band_labs(normalized_pixels, axis=0)
            ]
            vertical_de00 = [
                float(delta_e_ciede2000(band_lab, lab))
                for band_lab in _band_labs(normalized_pixels, axis=1)
            ]
            residual_values.extend(tile_de00)
            horizontal_values.extend(horizontal_de00)
            vertical_values.extend(vertical_de00)
            current.append(
                {
                    "cell_id": cell["cell_id"],
                    "controller": f"CS{cell['controller'] + 1}",
                    "row": cell["row"],
                    "column": cell["column"],
                    "position_index_for_code": cell["position_index_for_code"],
                    "code": cell["code"],
                    "raw_camera_relative_rgb_median": raw_median,
                    "raw_camera_relative_rgb_mad": raw_mad,
                    "white_normalized_rgb_median": median,
                    "white_normalized_rgb_mad": mad,
                    "white_normalized_camera_relative_lab_d65": lab,
                    "within_cell_tile_maximum_delta_e00": round(max(tile_de00), 6),
                    "horizontal_band_maximum_delta_e00": round(max(horizontal_de00), 6),
                    "vertical_band_maximum_delta_e00": round(max(vertical_de00), 6),
                }
            )
        frame_cells.append(current)
        labs_by_frame_key.append(by_key)

    replicate_groups: list[dict[str, Any]] = []
    replicate_maximum = 0.0
    for frame_index, records in enumerate(frame_cells):
        grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            grouped[(record["controller"], record["code"])].append(record)
        for controller in human.CONTROLLERS:
            for code in range(8):
                group = grouped[(controller, code)]
                _require(
                    len(group) == expected_replicates,
                    f"{controller} code {code} replicate count differs",
                )
                center = _median_vector(
                    [item["white_normalized_camera_relative_lab_d65"] for item in group]
                )
                deltas = [
                    float(
                        delta_e_ciede2000(
                            item["white_normalized_camera_relative_lab_d65"], center
                        )
                    )
                    for item in group
                ]
                maximum = max(deltas)
                replicate_maximum = max(replicate_maximum, maximum)
                replicate_groups.append(
                    {
                        "frame_index": frame_index,
                        "controller": controller,
                        "code": code,
                        "replicate_count": expected_replicates,
                        "group_center_lab_d65": _rounded_vector(center, 6),
                        "position_delta_e00": [round(value, 6) for value in deltas],
                        "maximum_delta_e00": round(maximum, 6),
                        "diagnostic_state": _classification(
                            maximum,
                            pass_max=POSITION_PASS_MAX_DE00,
                            review_max=POSITION_REVIEW_MAX_DE00,
                        ),
                    }
                )
    replicate_summary = {
        "group_count": len(replicate_groups),
        "expected_group_count": 48,
        "maximum_delta_e00": _metric(
            replicate_maximum,
            pass_max=POSITION_PASS_MAX_DE00,
            review_max=POSITION_REVIEW_MAX_DE00,
        ),
        "groups": replicate_groups,
    }

    temporal_cells: list[dict[str, Any]] = []
    temporal_maximum = 0.0
    for cell in cells:
        key = (cell["controller"], cell["row"], cell["column"])
        labs = [mapping[key] for mapping in labs_by_frame_key]
        center = _median_vector(labs)
        deltas = [math.dist(lab, center) for lab in labs]
        maximum = max(deltas)
        temporal_maximum = max(temporal_maximum, maximum)
        temporal_cells.append(
            {
                "cell_id": cell["cell_id"],
                "frame_delta_e76_to_temporal_median": [
                    round(value, 6) for value in deltas
                ],
                "maximum_delta_e76": round(maximum, 6),
                "diagnostic_state": _classification(
                    maximum,
                    pass_max=TEMPORAL_PASS_MAX_DE00,
                    review_max=TEMPORAL_REVIEW_MAX_DE00,
                ),
            }
        )
    temporal_summary = {
        "cell_count": len(temporal_cells),
        "expected_cell_count": expected_cell_count,
        "maximum_delta_e76": _metric(
            temporal_maximum,
            pass_max=TEMPORAL_PASS_MAX_DE00,
            review_max=TEMPORAL_REVIEW_MAX_DE00,
        ),
        "cells": temporal_cells,
    }

    all_records = [record for frame in frame_cells for record in frame]
    controls = []
    control_maximum = 0.0
    for code in human.CONTROL_CODES:
        centers = {}
        for controller in human.CONTROLLERS:
            values = [
                item["white_normalized_camera_relative_lab_d65"]
                for item in all_records
                if item["controller"] == controller and item["code"] == code
            ]
            _require(
                len(values) == expected_replicates * EXPECTED_FRAME_COUNT,
                f"{controller} control code {code} sample count differs",
            )
            centers[controller] = _median_vector(values)
        delta = float(delta_e_ciede2000(centers["CS1"], centers["CS2"]))
        control_maximum = max(control_maximum, delta)
        controls.append(
            {
                "code": code,
                "cs1_center_lab_d65": _rounded_vector(centers["CS1"], 6),
                "cs2_center_lab_d65": _rounded_vector(centers["CS2"], 6),
                "cross_controller_delta_e00": round(delta, 6),
                "diagnostic_state": _classification(
                    delta,
                    pass_max=CONTROL_PASS_MAX_DE00,
                    review_max=CONTROL_REVIEW_MAX_DE00,
                ),
            }
        )
    control_summary = {
        "control_codes": list(human.CONTROL_CODES),
        "threshold_basis": (
            "existing camera-relative cross-controller control heuristic 3/5 deltaE00; "
            "separate from the frozen four-replicate 8/12 gate"
        ),
        "maximum_cross_controller_delta_e00": _metric(
            control_maximum,
            pass_max=CONTROL_PASS_MAX_DE00,
            review_max=CONTROL_REVIEW_MAX_DE00,
        ),
        "controls": controls,
    }

    bottom_values: list[float] = []
    bottom_records = []
    if not partial_mode:
        for frame_index, (records, normalized_panel) in enumerate(
            zip(frame_cells, normalized)
        ):
            for controller_index, controller in enumerate(human.CONTROLLERS):
                code7_labs = [
                    item["white_normalized_camera_relative_lab_d65"]
                    for item in records
                    if item["controller"] == controller and item["code"] == 7
                ]
                center = _median_vector(code7_labs)
                x0 = controller_index * geometry.CONTROLLER_WIDTH + 20
                x1 = (controller_index + 1) * geometry.CONTROLLER_WIDTH - 20
                bottom = normalized_panel[566:590, x0:x1]
                labs = _tile_labs(bottom, rows=1, columns=8)
                deltas = [float(delta_e_ciede2000(lab, center)) for lab in labs]
                bottom_values.extend(deltas)
                bottom_records.append(
                    {
                        "frame_index": frame_index,
                        "controller": controller,
                        "logical_band": [x0, 566, x1 - x0, 24],
                        "reference": "SAME_CONTROLLER_CODE7_BACKGROUND",
                        "tile_delta_e00": [round(value, 6) for value in deltas],
                        "p95_delta_e00": round(_p95(deltas), 6),
                        "maximum_delta_e00": round(max(deltas), 6),
                    }
                )

    artifacts = {
        "within_cell_residual": {
            "p95_delta_e00": _metric(
                _p95(residual_values),
                pass_max=RESIDUAL_P95_PASS_MAX_DE00,
                review_max=RESIDUAL_P95_REVIEW_MAX_DE00,
            ),
            "maximum_delta_e00": _metric(
                max(residual_values),
                pass_max=RESIDUAL_MAX_PASS_MAX_DE00,
                review_max=RESIDUAL_MAX_REVIEW_MAX_DE00,
            ),
        },
        "horizontal_stripe": {
            "maximum_band_delta_e00": _metric(
                max(horizontal_values),
                pass_max=STRIPE_PASS_MAX_DE00,
                review_max=STRIPE_REVIEW_MAX_DE00,
            )
        },
        "vertical_stripe": {
            "maximum_band_delta_e00": _metric(
                max(vertical_values),
                pass_max=STRIPE_PASS_MAX_DE00,
                review_max=STRIPE_REVIEW_MAX_DE00,
            )
        },
        "bottom_edge": (
            {
                "diagnostic_state": "NOT_EVALUATED",
                "scope": "NOT_EVALUATED_OUTSIDE_SELECTED_ROI",
                "samples": [],
            }
            if partial_mode
            else {
                "p95_delta_e00": _metric(
                    _p95(bottom_values),
                    pass_max=BOTTOM_P95_PASS_MAX_DE00,
                    review_max=BOTTOM_P95_REVIEW_MAX_DE00,
                ),
                "maximum_delta_e00": _metric(
                    max(bottom_values),
                    pass_max=BOTTOM_MAX_PASS_MAX_DE00,
                    review_max=BOTTOM_MAX_REVIEW_MAX_DE00,
                ),
                "samples": bottom_records,
            }
        ),
    }
    normalization_clip = _metric(
        max(normalized_clip_values),
        pass_max=WHITE_HIGH_CLIP_PASS_MAX,
        review_max=WHITE_HIGH_CLIP_REVIEW_MAX,
    )
    alignment_inputs = list(atlas_panels)
    if partial_mode:
        alignment_inputs = []
        for panel in atlas_panels:
            masked = np.zeros_like(np.asarray(panel))
            y0 = t3_pack.GRID_Y_BY_ROW[PARTIAL_SELECTED_ROWS[0]]
            y1 = (
                t3_pack.GRID_Y_BY_ROW[PARTIAL_SELECTED_ROWS[-1]]
                + geometry.pack.CELL_HEIGHT
            )
            for controller_index in range(2):
                x0 = (
                    controller_index * geometry.CONTROLLER_WIDTH
                    + geometry.pack.GRID_X0
                )
                x1 = (
                    x0
                    + (geometry.pack.GRID_COLUMNS - 1)
                    * (geometry.pack.CELL_WIDTH + geometry.pack.GAP_X)
                    + geometry.pack.CELL_WIDTH
                )
                masked[y0:y1, x0:x1] = np.asarray(panel)[y0:y1, x0:x1]
            alignment_inputs.append(masked)
    alignment = _alignment_screen(alignment_inputs)

    hard_states = [
        white_lstar_state,
        replicate_summary["maximum_delta_e00"]["diagnostic_state"],
        temporal_summary["maximum_delta_e76"]["diagnostic_state"],
        control_summary["maximum_cross_controller_delta_e00"]["diagnostic_state"],
        artifacts["within_cell_residual"]["p95_delta_e00"]["diagnostic_state"],
        artifacts["within_cell_residual"]["maximum_delta_e00"]["diagnostic_state"],
        artifacts["horizontal_stripe"]["maximum_band_delta_e00"]["diagnostic_state"],
        artifacts["vertical_stripe"]["maximum_band_delta_e00"]["diagnostic_state"],
    ]
    if not partial_mode:
        hard_states.extend(
            [
                artifacts["bottom_edge"]["p95_delta_e00"]["diagnostic_state"],
                artifacts["bottom_edge"]["maximum_delta_e00"][
                    "diagnostic_state"
                ],
            ]
        )
    confidence_states = [
        alignment["diagnostic_state"],
        white_quality["maximum_cell_rgb_mad"]["diagnostic_state"],
        white_quality["maximum_cell_high_clip_fraction"]["diagnostic_state"],
        normalization_clip["diagnostic_state"],
    ]
    hard_worst = max(hard_states, key=RANK.get)
    confidence_worst = max(confidence_states, key=RANK.get)
    machine_confidence = {PASS: "HIGH", REVIEW: "MEDIUM", FAIL: "LOW"}[confidence_worst]
    if hard_worst == FAIL:
        state = FAIL
    elif hard_worst == REVIEW or machine_confidence != "HIGH":
        state = REVIEW
    else:
        state = PASS
    _require(
        not (machine_confidence == "LOW" and state == PASS),
        "low-confidence camera screen cannot pass",
    )
    result = {
        "diagnostic_state": state,
        "machine_confidence": machine_confidence,
        "white_reference": white_quality,
        "frames": [
            {"frame_index": index, "cells": records}
            for index, records in enumerate(frame_cells)
        ],
        "four_replicate_consistency": replicate_summary,
        "three_frame_temporal_stability": temporal_summary,
        "controls": control_summary,
        "artifacts": artifacts,
        "three_frame_alignment": alignment,
        "normalization_high_clip_fraction": normalization_clip,
        "normalization": {
            "formula": "clip(220 * atlas_rgb / current_white_rgb, 0, 255)",
            "target_rgb": NORMALIZATION_TARGET_RGB,
            "camera_relative_only": True,
        },
    }
    if partial_mode:
        comparison = []
        for code in range(8):
            centers: dict[str, list[float]] = {}
            for controller in human.CONTROLLERS:
                values = [
                    item["white_normalized_camera_relative_lab_d65"]
                    for item in all_records
                    if item["controller"] == controller and item["code"] == code
                ]
                _require(
                    len(values)
                    == PARTIAL_REPLICATES_PER_CODE_PER_CONTROLLER_PER_FRAME
                    * EXPECTED_FRAME_COUNT,
                    f"{controller} partial code {code} sample count differs",
                )
                centers[controller] = _median_vector(values)
            comparison.append(
                {
                    "code": code,
                    "samples_per_profile": 9,
                    "cs1_profile_alias": "A",
                    "cs1_profile": "active",
                    "cs2_profile_alias": "C",
                    "cs2_profile": "commented",
                    "cs1_center_lab_d65": _rounded_vector(centers["CS1"], 6),
                    "cs2_center_lab_d65": _rounded_vector(centers["CS2"], 6),
                    "cross_profile_delta_e00": round(
                        float(
                            delta_e_ciede2000(
                                centers["CS1"], centers["CS2"]
                            )
                        ),
                        6,
                    ),
                    "interpretation": "CAMERA_RELATIVE_DESCRIPTIVE_ONLY",
                    "formal_profile_following_effect": "NONE",
                }
            )
        result["three_replicate_consistency"] = result.pop(
            "four_replicate_consistency"
        )
        result.update(
            {
                "mode": PARTIAL_MODE,
                "selected_rows": list(PARTIAL_SELECTED_ROWS),
                "selected_columns": list(PARTIAL_SELECTED_COLUMNS),
                "selected_cell_count_per_frame": PARTIAL_SELECTED_CELL_COUNT,
                "profile_code_comparison": comparison,
                "outside_roi": "NOT_EVALUATED_OUTSIDE_SELECTED_ROI",
                "full_panel_geometry_evaluated": False,
                "formal_full_panel_evidence": False,
                "profile_following_decision_earned": False,
                "w4_post_white_full_screen_seal_earned": False,
            }
        )
    return result


def screen_logical_panels(
    white_panel: Any, atlas_panels: Sequence[Any]
) -> dict[str, Any]:
    """Screen the unchanged full 4x8 logical layout."""

    return _screen_logical_panels(
        white_panel,
        atlas_panels,
        selected_rows=tuple(range(4)),
        partial_mode=False,
    )


def screen_partial_logical_panels(
    white_panel: Any, atlas_panels: Sequence[Any]
) -> dict[str, Any]:
    """Screen both controller ROIs for rows 0..2 without a full-panel claim."""

    return _screen_logical_panels(
        white_panel,
        atlas_panels,
        selected_rows=PARTIAL_SELECTED_ROWS,
        partial_mode=True,
    )


def _screen_human_seed(seed: Mapping[str, Any]) -> dict[str, Any]:
    states: list[str] = []
    reasons: list[str] = []
    confirmations = []
    for controller in human.CONTROLLERS:
        item = seed["controllers"][controller]
        for field in (
            "all_four_replicates_human_confirmed",
            "all_labels_stable_human_confirmed",
        ):
            value = item[field]
            if value is True:
                state = PASS
            elif value is False:
                state = FAIL
                reasons.append(f"{controller}.{field}=false")
            else:
                state = REVIEW
                reasons.append(f"{controller}.{field}=unknown")
            states.append(state)
            confirmations.append(
                {
                    "controller": controller,
                    "field": field,
                    "value": value,
                    "state": state,
                }
            )

    control_labels = []
    for code in human.CONTROL_CODES:
        left = seed["controllers"]["CS1"]["code_labels_verbatim"][code]
        right = seed["controllers"]["CS2"]["code_labels_verbatim"][code]
        equal = left.strip().casefold() == right.strip().casefold()
        state = PASS if equal else FAIL
        states.append(state)
        if not equal:
            reasons.append(f"human control code {code} labels differ")
        control_labels.append(
            {
                "code": code,
                "cs1_label_verbatim": left,
                "cs2_label_verbatim": right,
                "normalized_labels_equal": equal,
                "state": state,
            }
        )

    artifact_results = []
    for field in human.ARTIFACT_FIELDS:
        observed = seed["artifacts"][field]["observed"]
        if observed is True:
            state = FAIL
            reasons.append(f"operator reported {field}")
        elif observed is None:
            state = REVIEW
            reasons.append(f"operator did not resolve {field}")
        else:
            state = PASS
        states.append(state)
        artifact_results.append({"field": field, "observed": observed, "state": state})

    supervision = seed["supervision"]
    supervision_results = []
    expected_true = (
        "continuous_supervision",
        "action_complete_reviewed",
        "no_intervening_visible_refresh",
        "ambient_light_stable",
        "viewing_angle_stable",
        "display_stable_through_observation",
        "four_replicates_checked",
        "electrical_state_normal",
    )
    for field in expected_true:
        value = supervision[field]
        if value is True:
            state = PASS
        elif value is False:
            state = FAIL
            reasons.append(f"supervision.{field}=false")
        else:
            state = REVIEW
            reasons.append(f"supervision.{field}=unknown")
        states.append(state)
        supervision_results.append(
            {"field": field, "value": value, "expected": True, "state": state}
        )
    restart = supervision["esp32_restart_observed"]
    if restart is False:
        restart_state = PASS
    elif restart is True:
        restart_state = FAIL
        reasons.append("supervision.esp32_restart_observed=true")
    else:
        restart_state = REVIEW
        reasons.append("supervision.esp32_restart_observed=unknown")
    states.append(restart_state)
    supervision_results.append(
        {
            "field": "esp32_restart_observed",
            "value": restart,
            "expected": False,
            "state": restart_state,
        }
    )
    state = max(states, key=RANK.get)
    return {
        "diagnostic_state": state,
        "reasons": reasons,
        "controller_confirmations": confirmations,
        "control_label_checks": control_labels,
        "artifact_checks": artifact_results,
        "supervision_checks": supervision_results,
        "j2_state_recorded_without_camera_gate": supervision[
            "j2_state_during_observation"
        ],
    }


def _missing_human_seed_screen() -> dict[str, Any]:
    return {
        "diagnostic_state": REVIEW,
        "reasons": [
            "no operator seed was supplied; camera-only screening cannot produce PASS"
        ],
        "controller_confirmations": [],
        "control_label_checks": [],
        "artifact_checks": [],
        "supervision_checks": [],
        "j2_state_recorded_without_camera_gate": None,
        "operator_seed_supplied": False,
    }


def _combine_screen(
    *,
    pixel_screen: Mapping[str, Any],
    geometry_screen: Mapping[str, Any],
    human_seed_screen: Mapping[str, Any],
) -> tuple[str, list[str]]:
    geometry_state = geometry_screen["maximum_corresponding_corner_drift_photo_px"][
        "diagnostic_state"
    ]
    states = [
        pixel_screen["diagnostic_state"],
        geometry_state,
        human_seed_screen["diagnostic_state"],
    ]
    worst = max(states, key=RANK.get)
    if pixel_screen["machine_confidence"] == "LOW" and worst == PASS:
        worst = REVIEW
    reasons = list(human_seed_screen["reasons"])
    if pixel_screen["diagnostic_state"] != PASS:
        reasons.append(
            "camera pixel diagnostics require "
            + pixel_screen["diagnostic_state"].lower()
        )
    if pixel_screen["machine_confidence"] == "LOW":
        reasons.append("camera evidence confidence is low; PASS is prohibited")
    if geometry_state != PASS:
        reasons.append(
            "cross-capture panel-corner drift requires " + geometry_state.lower()
        )
    if not reasons:
        reasons.append(
            "all supplemental camera and supplied human-card diagnostics pass"
        )
    conclusion = f"HUMAN_CAMERA_SCREEN_{worst}"
    _require(
        conclusion
        in {
            "HUMAN_CAMERA_SCREEN_PASS",
            "HUMAN_CAMERA_SCREEN_REVIEW",
            "HUMAN_CAMERA_SCREEN_FAIL",
        },
        "automatic conclusion left the three-state vocabulary",
    )
    return conclusion, reasons


def build_report(
    *,
    white_photo_path: Path,
    white_capture_sidecar_path: Path,
    white_action_result_path: Path,
    white_human_authority_path: Path,
    atlas_photo_paths: Sequence[Path],
    atlas_capture_sidecar_paths: Sequence[Path],
    atlas_action_result_path: Path,
    white_panel_corners: str | Any,
    atlas_panel_corners: Sequence[str | Any],
    human_seed_path: Path | None = None,
) -> dict[str, Any]:
    """Deep-read all sealed inputs and build one supplemental screen report."""

    offline_contract = _validate_offline_contract()
    _require(
        len(atlas_photo_paths) == EXPECTED_FRAME_COUNT
        and len(atlas_capture_sidecar_paths) == EXPECTED_FRAME_COUNT,
        "exactly three atlas photo/sidecar pairs are required",
    )
    _require(
        len(atlas_panel_corners) == EXPECTED_FRAME_COUNT,
        "exactly three atlas panel-corner sets are required",
    )
    if human_seed_path is None:
        seed_path = None
        seed_payload = None
        seed = None
        compact = None
        seed_screen = _missing_human_seed_screen()
    else:
        seed_path = Path(human_seed_path).resolve()
        seed_payload, seed_root = _read_json(seed_path, label="camera human seed")
        seed = _validate_seed(seed_root)
        compact = _compact_from_seed(seed)
        seed_screen = _screen_human_seed(seed)
        seed_screen["operator_seed_supplied"] = True

    white_action, _white_action_root = _action_context(
        white_action_result_path, stage=w3_pack.STAGE
    )
    atlas_action, _atlas_action_root = _action_context(
        atlas_action_result_path, stage=human.AC_STAGE
    )
    white_authority = _validate_white_authority(white_human_authority_path)
    _require(
        white_authority["action_id"] == white_action["action_id"],
        "clean-white authority and white capture action differ",
    )

    white_binding, white_rgb = _load_capture(
        photo_path=white_photo_path,
        sidecar_path=white_capture_sidecar_path,
        action_result_path=white_action_result_path,
        expected_action=white_action,
        label="current W3 white reference",
    )
    atlas_bindings = []
    atlas_rgb = []
    for index, (photo, sidecar) in enumerate(
        zip(atlas_photo_paths, atlas_capture_sidecar_paths)
    ):
        binding, rgb = _load_capture(
            photo_path=photo,
            sidecar_path=sidecar,
            action_result_path=atlas_action_result_path,
            expected_action=atlas_action,
            label=f"T3 atlas retained frame {index + 1}",
        )
        atlas_bindings.append(binding)
        atlas_rgb.append(rgb)

    capture_ids = [white_binding["capture_id"]] + [
        item["capture_id"] for item in atlas_bindings
    ]
    _require(
        len(set(capture_ids)) == 4, "white plus atlas capture IDs are not distinct"
    )
    atlas_photo_resolved = [Path(path).resolve() for path in atlas_photo_paths]
    atlas_sidecar_resolved = [
        Path(path).resolve() for path in atlas_capture_sidecar_paths
    ]
    _require(
        len(set(atlas_photo_resolved)) == 3 and len(set(atlas_sidecar_resolved)) == 3,
        "three atlas frames must use distinct photo and sidecar paths",
    )
    fingerprints = [white_binding["capture_alignment"]] + [
        item["capture_alignment"] for item in atlas_bindings
    ]
    _require(
        all(item == fingerprints[0] for item in fingerprints[1:]),
        "white and atlas camera instance/mount/settings/dimensions differ",
    )
    white_time = _parse_time(white_binding["captured_at"], label="white captured_at")
    atlas_times = [
        _parse_time(item["captured_at"], label=f"atlas[{index}] captured_at")
        for index, item in enumerate(atlas_bindings)
    ]
    _require(
        all(white_time < item for item in atlas_times),
        "current white reference must precede all three T3 atlas captures",
    )
    _require(
        atlas_times == sorted(atlas_times),
        "atlas capture inputs must be supplied in chronological order",
    )

    try:
        white_homography, white_geometry = geometry._fit_panel_homography(  # noqa: SLF001
            white_panel_corners,
            photo_width=EXPECTED_PHOTO_WIDTH,
            photo_height=EXPECTED_PHOTO_HEIGHT,
        )
        atlas_geometry_pairs = [
            geometry._fit_panel_homography(  # noqa: SLF001
                corners,
                photo_width=EXPECTED_PHOTO_WIDTH,
                photo_height=EXPECTED_PHOTO_HEIGHT,
            )
            for corners in atlas_panel_corners
        ]
    except geometry.CrossoverPhotoAnalysisError as error:
        raise T3CameraObservationError(
            f"current panel geometry rejected: {error}"
        ) from error
    atlas_homographies = [item[0] for item in atlas_geometry_pairs]
    atlas_geometries = [item[1] for item in atlas_geometry_pairs]
    geometry_screen = _geometry_drift_screen([white_geometry, *atlas_geometries])
    white_panel = _warp_panel(white_rgb, white_homography)
    atlas_panels = [
        _warp_panel(rgb, homography)
        for rgb, homography in zip(atlas_rgb, atlas_homographies)
    ]
    pixel_screen = screen_logical_panels(white_panel, atlas_panels)
    conclusion, reasons = _combine_screen(
        pixel_screen=pixel_screen,
        geometry_screen=geometry_screen,
        human_seed_screen=seed_screen,
    )

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "method_id": METHOD_ID,
        "stage": human.AC_STAGE,
        "automatic_conclusion": conclusion,
        "automatic_conclusion_vocabulary": [
            "HUMAN_CAMERA_SCREEN_PASS",
            "HUMAN_CAMERA_SCREEN_REVIEW",
            "HUMAN_CAMERA_SCREEN_FAIL",
        ],
        "screen_reasons": reasons,
        "camera_contract": offline_contract,
        "action_result_bindings": {
            "current_w3_white": white_action,
            "t3_ac_profile_following_atlas": atlas_action,
        },
        "current_white_human_authority_binding": white_authority,
        "capture_bindings": {
            "current_w3_white": white_binding,
            "t3_atlas_frames": atlas_bindings,
            "alignment_fingerprint": fingerprints[0],
            "all_four_complete_settings_and_mount_equal": True,
            "white_precedes_all_atlas_frames": True,
            "three_atlas_inputs_chronological": True,
        },
        "human_seed_binding": (
            None
            if seed_path is None or seed_payload is None
            else _file_binding(seed_path, seed_payload)
        ),
        "human_seed_preserved": seed,
        "generated_compact_human_input": {
            "available": compact is not None,
            "unavailable_reason": (
                None
                if compact is not None
                else (
                    "no operator seed was supplied, or the compact schema cannot expand "
                    "until the operator explicitly confirms all four copies and stability "
                    "on both sides"
                )
            ),
            "content": compact,
            "expansion_rule_when_available": (
                "FIXED_CODE_ROWS_FOUR_REPLICATES_PER_CONTROLLER_CODE"
                if compact is not None
                else None
            ),
            "expanded_cell_count_when_available": 64 if compact is not None else None,
            "human_labels_derived_from_pixels": False,
        },
        "layout": {
            "controller_count": 2,
            "controllers": list(human.CONTROLLERS),
            "rows": 4,
            "columns_per_controller": 8,
            "row_codes": [list(row) for row in human.CODE_ROWS],
            "cell_count": 64,
            "replicates_per_controller_code_per_frame": 4,
            "control_codes": list(human.CONTROL_CODES),
            "background_code": 7,
        },
        "geometry": {
            "current_w3_white": white_geometry,
            "t3_atlas_frames": atlas_geometries,
            "cross_capture_corner_drift": geometry_screen,
            "each_capture_uses_its_own_explicit_current_photo_corners": True,
        },
        "camera_pixel_screen": pixel_screen,
        "human_seed_screen": seed_screen,
        "classification_boundary": {
            "human_primary_camera_supplemental": True,
            "camera_evidence_required_by_t3_pack": False,
            "camera_relative_screening_only": True,
            "absolute_colour_calibrated": False,
            "absolute_colour_claimed": False,
            "human_labels_inferred_or_rewritten": False,
            "automatic_cell_lattice_reprojection_proven": False,
            "formal_gate_evaluated": False,
            "profile_following_formally_proven": False,
            "qualified_colour_count": 0,
            "automatic_next_action_authorized": False,
            "low_machine_confidence_can_pass": False,
        },
        "offline_execution": {
            "hardware_accessed": False,
            "camera_accessed": False,
            "network_accessed": False,
            "serial_or_com_accessed": False,
            "relay_accessed": False,
            "firmware_flashed": False,
            "display_refreshed": False,
        },
        "output_write_contract": "O_EXCL",
    }
    report["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": strict.sha256_bytes(strict.canonical_json(report)),
    }
    return report


def _partial_blocks_argument(value: str | Mapping[str, Any]) -> Mapping[str, Any]:
    candidate: Any = value
    if isinstance(value, str):
        try:
            candidate = json.loads(
                value,
                parse_constant=lambda item: (_ for _ in ()).throw(
                    ValueError(f"non-finite JSON constant {item}")
                ),
            )
        except (json.JSONDecodeError, ValueError) as error:
            raise T3CameraObservationError(
                f"partial blocks are not strict JSON: {error}"
            ) from error
    _require(
        isinstance(candidate, Mapping) and set(candidate) == {"CS1", "CS2"},
        "partial blocks must contain exactly CS1 and CS2",
    )
    return candidate


def _partial_offline_contract() -> dict[str, Any]:
    _validate_camera_profile_choice()
    return {
        "mode": PARTIAL_MODE,
        "camera_profile_authority": (
            "README camera.md + frozen retained-atlas exposure=-6 validator"
        ),
        "coverage_scope": camera.COVERAGE_PARTIAL,
        "full_panel_visible": False,
        "full_panel_uncropped": False,
        "selected_rows": list(PARTIAL_SELECTED_ROWS),
        "selected_columns": list(PARTIAL_SELECTED_COLUMNS),
        "selected_cell_count_per_frame": PARTIAL_SELECTED_CELL_COUNT,
        "replicates_per_code_per_controller_per_frame": (
            PARTIAL_REPLICATES_PER_CODE_PER_CONTROLLER_PER_FRAME
        ),
        "retained_atlas_frame_count": EXPECTED_FRAME_COUNT,
        "normalization": "SAME_SIDE_SAME_CELL_CURRENT_W3_WHITE",
        "raw_cross_side_rgb_equality_gate": False,
        "profile_code_pair_comparison_required": True,
        "formal_full_panel_evidence": False,
        "profile_following_decision_earned": False,
        "w4_post_white_full_screen_seal_earned": False,
        "outside_roi": "NOT_EVALUATED_OUTSIDE_SELECTED_ROI",
    }


def build_partial_report(
    *,
    white_photo_path: Path,
    white_capture_sidecar_path: Path,
    white_action_result_path: Path,
    white_human_authority_path: Path,
    atlas_photo_paths: Sequence[Path],
    atlas_capture_sidecar_paths: Sequence[Path],
    atlas_action_result_paths: Sequence[Path],
    white_partial_blocks: str | Mapping[str, Any],
    atlas_partial_blocks: Sequence[str | Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the independent dual-side partial camera screen offline."""

    contract = _partial_offline_contract()
    _require(
        len(atlas_photo_paths) == EXPECTED_FRAME_COUNT
        and len(atlas_capture_sidecar_paths) == EXPECTED_FRAME_COUNT
        and len(atlas_action_result_paths) == EXPECTED_FRAME_COUNT
        and len(atlas_partial_blocks) == EXPECTED_FRAME_COUNT,
        "partial mode requires exactly three atlas photos, sidecars, actions, and block sets",
    )
    resolved_action_paths = {
        os.path.normcase(str(Path(path).resolve()))
        for path in atlas_action_result_paths
    }
    _require(
        len(resolved_action_paths) == EXPECTED_FRAME_COUNT,
        "partial mode requires three distinct atlas action snapshot paths",
    )
    white_action, _white_action_root = _action_context(
        white_action_result_path, stage=w3_pack.STAGE
    )
    atlas_action_contexts = [
        _action_context(path, stage=human.AC_V2_STAGE)
        for path in atlas_action_result_paths
    ]
    atlas_actions = [item[0] for item in atlas_action_contexts]
    atlas_action = atlas_actions[0]
    atlas_action_identity = {
        key: value for key, value in atlas_action.items() if key != "path"
    }
    _require(
        all(
            {key: value for key, value in item.items() if key != "path"}
            == atlas_action_identity
            for item in atlas_actions[1:]
        ),
        "partial atlas action snapshots do not bind the same exact action",
    )
    white_authority = _validate_white_authority(white_human_authority_path)
    _require(
        white_authority["action_id"] == white_action["action_id"],
        "clean-white authority and partial white capture action differ",
    )
    white_binding, white_rgb = _load_capture(
        photo_path=white_photo_path,
        sidecar_path=white_capture_sidecar_path,
        action_result_path=white_action_result_path,
        expected_action=white_action,
        label="current W3 partial white reference",
        expected_coverage_scope=camera.COVERAGE_PARTIAL,
    )
    atlas_bindings = []
    atlas_rgb = []
    for index, (photo, sidecar, action_path, expected_action) in enumerate(
        zip(
            atlas_photo_paths,
            atlas_capture_sidecar_paths,
            atlas_action_result_paths,
            atlas_actions,
            strict=True,
        )
    ):
        binding, rgb = _load_capture(
            photo_path=photo,
            sidecar_path=sidecar,
            action_result_path=action_path,
            expected_action=expected_action,
            label=f"T3 partial atlas retained frame {index + 1}",
            expected_coverage_scope=camera.COVERAGE_PARTIAL,
        )
        atlas_bindings.append(binding)
        atlas_rgb.append(rgb)
    capture_ids = [white_binding["capture_id"]] + [
        item["capture_id"] for item in atlas_bindings
    ]
    _require(len(set(capture_ids)) == 4, "partial capture IDs are not distinct")
    _require(
        len({Path(path).resolve() for path in atlas_photo_paths}) == 3
        and len({Path(path).resolve() for path in atlas_capture_sidecar_paths}) == 3,
        "partial atlas frames must use distinct photo and sidecar paths",
    )
    fingerprints = [white_binding["capture_alignment"]] + [
        item["capture_alignment"] for item in atlas_bindings
    ]
    _require(
        all(item == fingerprints[0] for item in fingerprints[1:]),
        "partial white and atlas camera/mount/settings/dimensions differ",
    )
    white_time = _parse_time(white_binding["captured_at"], label="white captured_at")
    atlas_times = [
        _parse_time(item["captured_at"], label=f"atlas[{index}] captured_at")
        for index, item in enumerate(atlas_bindings)
    ]
    _require(
        all(white_time < item for item in atlas_times),
        "partial white reference must precede all atlas captures",
    )
    _require(
        atlas_times == sorted(atlas_times),
        "partial atlas captures must be chronological",
    )

    try:
        white_homographies, white_geometry = (
            geometry._fit_partial_dual_controller_blocks(  # noqa: SLF001
                _partial_blocks_argument(white_partial_blocks),
                photo_width=EXPECTED_PHOTO_WIDTH,
                photo_height=EXPECTED_PHOTO_HEIGHT,
            )
        )
        atlas_geometry_pairs = [
            geometry._fit_partial_dual_controller_blocks(  # noqa: SLF001
                _partial_blocks_argument(blocks),
                photo_width=EXPECTED_PHOTO_WIDTH,
                photo_height=EXPECTED_PHOTO_HEIGHT,
            )
            for blocks in atlas_partial_blocks
        ]
    except geometry.CrossoverPhotoAnalysisError as error:
        raise T3CameraObservationError(
            f"partial current-photo geometry rejected: {error}"
        ) from error
    atlas_homographies = [item[0] for item in atlas_geometry_pairs]
    atlas_geometries = [item[1] for item in atlas_geometry_pairs]
    geometry_screen = _partial_geometry_drift_screen(
        [white_geometry, *atlas_geometries]
    )
    white_panel = _warp_partial_panel(white_rgb, white_homographies)
    atlas_panels = [
        _warp_partial_panel(rgb, homographies)
        for rgb, homographies in zip(atlas_rgb, atlas_homographies, strict=True)
    ]
    pixel_screen = screen_partial_logical_panels(white_panel, atlas_panels)
    states = [pixel_screen["diagnostic_state"], geometry_screen["diagnostic_state"]]
    state = max(states, key=RANK.get)
    if pixel_screen["machine_confidence"] == "LOW" and state == PASS:
        state = REVIEW
    conclusion = f"PARTIAL_CAMERA_SCREEN_{state}"
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": PARTIAL_KIND,
        "method_id": PARTIAL_METHOD_ID,
        "mode": PARTIAL_MODE,
        "stage": human.AC_V2_STAGE,
        "automatic_conclusion": conclusion,
        "automatic_conclusion_vocabulary": [
            "PARTIAL_CAMERA_SCREEN_PASS",
            "PARTIAL_CAMERA_SCREEN_REVIEW",
            "PARTIAL_CAMERA_SCREEN_FAIL",
        ],
        "automatic_conclusion_effect": "DESCRIPTIVE_PARTIAL_ROI_ONLY",
        "camera_contract": contract,
        "action_result_bindings": {
            "current_w3_white": white_action,
            "t3_ac_profile_following_atlas": atlas_action,
            "t3_ac_profile_following_atlas_frames": atlas_actions,
        },
        "current_white_human_authority_binding": white_authority,
        "capture_bindings": {
            "current_w3_white": white_binding,
            "t3_atlas_frames": atlas_bindings,
            "alignment_fingerprint": fingerprints[0],
            "all_four_complete_settings_and_mount_equal": True,
            "white_precedes_all_atlas_frames": True,
            "three_atlas_inputs_chronological": True,
        },
        "layout": {
            "controller_count": 2,
            "controllers": list(human.CONTROLLERS),
            "selected_rows": list(PARTIAL_SELECTED_ROWS),
            "columns_per_controller": 8,
            "selected_row_codes": [
                list(human.CODE_ROWS[row]) for row in PARTIAL_SELECTED_ROWS
            ],
            "selected_cell_count": PARTIAL_SELECTED_CELL_COUNT,
            "replicates_per_controller_code_per_frame": 3,
            "replicates_per_profile_code_across_three_frames": 9,
        },
        "geometry": {
            "current_w3_white": white_geometry,
            "t3_atlas_frames": atlas_geometries,
            "cross_capture_block_drift": geometry_screen,
            "each_capture_uses_its_own_explicit_current_photo_blocks": True,
            "full_panel_geometry_evaluated": False,
        },
        "camera_pixel_screen": pixel_screen,
        "profile_code_comparison": pixel_screen["profile_code_comparison"],
        "outside_selected_roi": {
            "status": "NOT_EVALUATED_OUTSIDE_SELECTED_ROI",
            "row_3": "NOT_EVALUATED",
            "bottom_edge": "NOT_EVALUATED",
            "full_panel_corners": "NOT_REQUIRED_AND_NOT_EVALUATED",
        },
        "classification_boundary": {
            "camera_relative_screening_only": True,
            "absolute_colour_calibrated": False,
            "formal_gate_evaluated": False,
            "formal_full_panel_evidence": False,
            "full_panel_geometry_evaluated": False,
            "profile_code_comparison_available": True,
            "profile_following_formally_proven": False,
            "profile_following_decision_earned": False,
            "w4_post_white_full_screen_seal_earned": False,
            "partial_roi_may_be_promoted_to_full_panel_evidence": False,
            "qualified_colour_count": 0,
            "automatic_next_action_authorized": False,
        },
        "offline_execution": {
            "hardware_accessed": False,
            "camera_accessed": False,
            "network_accessed": False,
            "serial_or_com_accessed": False,
            "relay_accessed": False,
            "firmware_flashed": False,
            "display_refreshed": False,
        },
        "output_write_contract": "O_EXCL",
    }
    report["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": strict.sha256_bytes(strict.canonical_json(report)),
    }
    return report


def validate_partial_report(path: Path) -> tuple[dict[str, Any], bytes]:
    """Deep-recompute a partial report from its immutable input paths."""

    payload, root = _read_json(Path(path), label="T3 partial camera report")
    try:
        strict._verify_integrity(root, label="T3 partial camera report")  # noqa: SLF001
    except strict.CrossoverProfileComparisonError as error:
        raise T3CameraObservationError(str(error)) from error
    _require(
        root.get("schema_version") == SCHEMA_VERSION
        and root.get("kind") == PARTIAL_KIND
        and root.get("mode") == PARTIAL_MODE,
        "T3 partial camera report identity differs",
    )
    captures = root["capture_bindings"]
    white = captures["current_w3_white"]
    atlases = captures["t3_atlas_frames"]
    _require(isinstance(atlases, list) and len(atlases) == 3, "partial bindings differ")
    recomputed = build_partial_report(
        white_photo_path=Path(white["photo"]["path"]),
        white_capture_sidecar_path=Path(white["capture_sidecar"]["path"]),
        white_action_result_path=Path(
            root["action_result_bindings"]["current_w3_white"]["path"]
        ),
        white_human_authority_path=Path(
            root["current_white_human_authority_binding"]["path"]
        ),
        atlas_photo_paths=[Path(item["photo"]["path"]) for item in atlases],
        atlas_capture_sidecar_paths=[
            Path(item["capture_sidecar"]["path"]) for item in atlases
        ],
        atlas_action_result_paths=[
            Path(item["path"])
            for item in root["action_result_bindings"][
                "t3_ac_profile_following_atlas_frames"
            ]
        ],
        white_partial_blocks=root["geometry"]["current_w3_white"][
            "supplied_block_corners_tl_tr_br_bl"
        ],
        atlas_partial_blocks=[
            item["supplied_block_corners_tl_tr_br_bl"]
            for item in root["geometry"]["t3_atlas_frames"]
        ],
    )
    _require(recomputed == root, "T3 partial report differs from deep recomputation")
    return root, payload


def validate_report(path: Path) -> tuple[dict[str, Any], bytes]:
    """Deep-recompute a report from every immutable source path it binds."""

    payload, root = _read_json(Path(path), label="T3 camera-assisted report")
    try:
        strict._verify_integrity(root, label="T3 camera-assisted report")  # noqa: SLF001
    except strict.CrossoverProfileComparisonError as error:
        raise T3CameraObservationError(str(error)) from error
    _require(
        root.get("schema_version") == SCHEMA_VERSION and root.get("kind") == KIND,
        "T3 camera-assisted report schema or kind differs",
    )
    captures = root["capture_bindings"]
    white = captures["current_w3_white"]
    atlases = captures["t3_atlas_frames"]
    _require(
        isinstance(atlases, list) and len(atlases) == 3, "report atlas bindings differ"
    )
    recomputed = build_report(
        white_photo_path=Path(white["photo"]["path"]),
        white_capture_sidecar_path=Path(white["capture_sidecar"]["path"]),
        white_action_result_path=Path(
            root["action_result_bindings"]["current_w3_white"]["path"]
        ),
        white_human_authority_path=Path(
            root["current_white_human_authority_binding"]["path"]
        ),
        atlas_photo_paths=[Path(item["photo"]["path"]) for item in atlases],
        atlas_capture_sidecar_paths=[
            Path(item["capture_sidecar"]["path"]) for item in atlases
        ],
        atlas_action_result_path=Path(
            root["action_result_bindings"]["t3_ac_profile_following_atlas"]["path"]
        ),
        white_panel_corners=root["geometry"]["current_w3_white"][
            "supplied_panel_corners_tl_tr_br_bl"
        ],
        atlas_panel_corners=[
            item["supplied_panel_corners_tl_tr_br_bl"]
            for item in root["geometry"]["t3_atlas_frames"]
        ],
        human_seed_path=(
            None
            if root["human_seed_binding"] is None
            else Path(root["human_seed_binding"]["path"])
        ),
    )
    _require(
        recomputed == root, "T3 camera-assisted report differs from deep recomputation"
    )
    return root, payload


def validate_compact_output(
    *, report: Mapping[str, Any], compact_path: Path
) -> tuple[dict[str, Any], bytes]:
    payload, compact = _read_json(
        Path(compact_path), label="generated compact human input"
    )
    expected = report["generated_compact_human_input"]["content"]
    _require(expected is not None, "report does not authorize a compact output")
    _require(compact == expected, "compact output differs from report-bound content")
    try:
        expanded, expansion = human._expand_compact_operator_input(  # noqa: SLF001
            compact, expected_stage=human.AC_STAGE
        )
    except human.HumanObservationError as error:
        raise T3CameraObservationError(
            f"compact human output rejected: {error}"
        ) from error
    _require(
        len(expanded["cells"]) == 64 and expansion["expanded_cell_count"] == 64,
        "compact human output does not expand to the exact 64 cells",
    )
    return compact, payload


def seed_template() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": SEED_KIND,
        "stage": human.AC_STAGE,
        "observed_at": None,
        "operator": {
            "operator_id": "FILL_OPERATOR_ID",
            "operator_verbatim": "FILL_ONE_VERBATIM_SENTENCE",
        },
        "supervision": {
            "supervisor_id": "FILL_SUPERVISOR_ID_OR_NOT_REPORTED",
            "continuous_supervision": None,
            "action_complete_reviewed": None,
            "no_intervening_visible_refresh": None,
            "ambient_light_stable": None,
            "viewing_angle_stable": None,
            "display_stable_through_observation": None,
            "four_replicates_checked": None,
            "electrical_state_normal": None,
            "esp32_restart_observed": None,
            "j2_state_during_observation": "UNKNOWN",
            "supervision_verbatim": "FILL_VERBATIM_OR_NOT_REPORTED",
        },
        "controls_verbatim": "FILL_CODES_2_3_5_CROSS_SIDE_OBSERVATION",
        "artifacts": {
            field: {"observed": None, "operator_verbatim": "FILL_VERBATIM"}
            for field in human.ARTIFACT_FIELDS
        },
        "controllers": {
            controller: {
                "code_labels_verbatim": [f"FILL_CODE_{code}" for code in range(8)],
                "all_four_replicates_human_confirmed": None,
                "all_labels_stable_human_confirmed": None,
            }
            for controller in human.CONTROLLERS
        },
    }


def write_exclusive(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(Path(path), flags, 0o600)
    except FileExistsError as error:
        raise T3CameraObservationError(
            f"refusing to overwrite output: {path}"
        ) from error
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def write_report_and_compact_exclusive(
    *, report_path: Path, compact_path: Path | None, report: Mapping[str, Any]
) -> None:
    report_path = Path(report_path)
    compact = report["generated_compact_human_input"]["content"]
    if compact is not None:
        _require(
            compact_path is not None,
            "available compact input requires --compact-output",
        )
        compact_path = Path(compact_path)
        _require(
            report_path.resolve() != compact_path.resolve(),
            "report and compact paths collide",
        )
    else:
        # A requested compact path is intentionally left untouched when the
        # operator seed is absent/incomplete.  The camera report still seals.
        compact_path = None
    _require(not report_path.exists(), f"refusing to overwrite output: {report_path}")
    if compact_path is not None:
        _require(
            not compact_path.exists(), f"refusing to overwrite output: {compact_path}"
        )

    compact_created = False
    try:
        if compact_path is not None:
            write_exclusive(compact_path, _serialize(compact))
            compact_created = True
        write_exclusive(report_path, _serialize(report))
    except Exception:
        if compact_created and compact_path is not None:
            compact_path.unlink(missing_ok=True)
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("describe-contract", allow_abbrev=False)
    template = subparsers.add_parser("write-seed-template", allow_abbrev=False)
    template.add_argument("--output", type=Path, required=True)
    generate = subparsers.add_parser("generate", allow_abbrev=False)
    generate.add_argument("--white-photo", type=Path, required=True)
    generate.add_argument("--white-sidecar", type=Path, required=True)
    generate.add_argument("--white-action-result", type=Path, required=True)
    generate.add_argument(
        "--white-human-authority",
        type=Path,
        default=t3_pack.W3_HUMAN_CLEAN_WHITE_AUTHORITY_PATH,
    )
    generate.add_argument("--atlas-photo", type=Path, nargs=3, required=True)
    generate.add_argument("--atlas-sidecar", type=Path, nargs=3, required=True)
    generate.add_argument("--atlas-action-result", type=Path, required=True)
    generate.add_argument(
        "--white-panel-corners",
        required=True,
        metavar="TLx,TLy;TRx,TRy;BRx,BRy;BLx,BLy",
    )
    generate.add_argument(
        "--atlas-panel-corners",
        nargs=3,
        required=True,
        metavar=("FRAME1_CORNERS", "FRAME2_CORNERS", "FRAME3_CORNERS"),
    )
    generate.add_argument(
        "--human-seed",
        type=Path,
        help=(
            "optional truthful operator card; without it the full camera report is "
            "still generated but PASS and compact output are unavailable"
        ),
    )
    generate.add_argument("--report-output", type=Path, required=True)
    generate.add_argument("--compact-output", type=Path)
    validate = subparsers.add_parser("validate", allow_abbrev=False)
    validate.add_argument("--report", type=Path, required=True)
    validate.add_argument("--compact-input", type=Path)
    subparsers.add_parser("describe-partial-contract", allow_abbrev=False)
    generate_partial = subparsers.add_parser(
        "generate-partial", allow_abbrev=False
    )
    generate_partial.add_argument("--white-photo", type=Path, required=True)
    generate_partial.add_argument("--white-sidecar", type=Path, required=True)
    generate_partial.add_argument("--white-action-result", type=Path, required=True)
    generate_partial.add_argument(
        "--white-human-authority",
        type=Path,
        default=t3_pack.W3_HUMAN_CLEAN_WHITE_AUTHORITY_PATH,
    )
    generate_partial.add_argument("--atlas-photo", type=Path, nargs=3, required=True)
    generate_partial.add_argument(
        "--atlas-sidecar", type=Path, nargs=3, required=True
    )
    generate_partial.add_argument(
        "--atlas-action-result", type=Path, nargs=3, required=True
    )
    generate_partial.add_argument("--white-partial-blocks", required=True)
    generate_partial.add_argument(
        "--atlas-partial-blocks", nargs=3, required=True
    )
    generate_partial.add_argument("--report-output", type=Path, required=True)
    validate_partial = subparsers.add_parser(
        "validate-partial", allow_abbrev=False
    )
    validate_partial.add_argument("--report", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "describe-contract":
            print(
                json.dumps(_validate_offline_contract(), ensure_ascii=False, indent=2)
            )
            return 0
        if args.command == "write-seed-template":
            write_exclusive(args.output, _serialize(seed_template()))
            print(args.output)
            return 0
        if args.command == "generate":
            report = build_report(
                white_photo_path=args.white_photo,
                white_capture_sidecar_path=args.white_sidecar,
                white_action_result_path=args.white_action_result,
                white_human_authority_path=args.white_human_authority,
                atlas_photo_paths=args.atlas_photo,
                atlas_capture_sidecar_paths=args.atlas_sidecar,
                atlas_action_result_path=args.atlas_action_result,
                white_panel_corners=args.white_panel_corners,
                atlas_panel_corners=args.atlas_panel_corners,
                human_seed_path=args.human_seed,
            )
            write_report_and_compact_exclusive(
                report_path=args.report_output,
                compact_path=args.compact_output,
                report=report,
            )
            print(report["automatic_conclusion"])
            state = report["automatic_conclusion"].rsplit("_", 1)[-1]
            return {PASS: 0, REVIEW: 3, FAIL: 4}[state]
        if args.command == "validate":
            report, _payload = validate_report(args.report)
            if args.compact_input is not None:
                validate_compact_output(report=report, compact_path=args.compact_input)
            print(report["automatic_conclusion"])
            return 0
        if args.command == "describe-partial-contract":
            print(json.dumps(_partial_offline_contract(), ensure_ascii=False, indent=2))
            return 0
        if args.command == "generate-partial":
            report = build_partial_report(
                white_photo_path=args.white_photo,
                white_capture_sidecar_path=args.white_sidecar,
                white_action_result_path=args.white_action_result,
                white_human_authority_path=args.white_human_authority,
                atlas_photo_paths=args.atlas_photo,
                atlas_capture_sidecar_paths=args.atlas_sidecar,
                atlas_action_result_paths=args.atlas_action_result,
                white_partial_blocks=args.white_partial_blocks,
                atlas_partial_blocks=args.atlas_partial_blocks,
            )
            write_exclusive(args.report_output, _serialize(report))
            print(report["automatic_conclusion"])
            state = report["automatic_conclusion"].rsplit("_", 1)[-1]
            return {PASS: 0, REVIEW: 3, FAIL: 4}[state]
        report, _payload = validate_partial_report(args.report)
        print(report["automatic_conclusion"])
        return 0
    except T3CameraObservationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
