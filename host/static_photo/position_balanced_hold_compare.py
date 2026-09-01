"""Offline T0/T1/T2 review for the position-balanced HOLD successor.

T0 is the exact F1 V3 G3 construction, T1 is the final H1 action, and T2 is
the final H2 action.  This module performs no image capture or hardware I/O.
It consumes sealed, already-produced camera analyses and emits review drafts
only; it can never create passed ``ControllerPaletteEvidence``.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import stat
from typing import Any, Mapping, Sequence

from .common import (
    StaticPhotoContractError,
    attach_integrity,
    canonical_sha256,
    require_exact_keys,
    require_sha256,
    require_text,
    verify_integrity,
)


SCHEMA_VERSION = 1
COMPARISON_KIND = "MF1750_POSITION_BALANCED_HOLD_T0_T1_T2_CAMERA_COMPARISON"
IDENTITY_CONTRACT_KIND = (
    "MF1750_POSITION_BALANCED_HOLD_T0_T1_T2_EXACT_IDENTITY_CONTRACT"
)
V3_ANALYSIS_KIND = "mf1750-luma-gray-mechanism-position-balanced-v3-photo-analysis"
HOLD_ANALYSIS_KIND = "mf1750-position-balanced-gray-hold-successor-v1-photo-analysis"
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
PROJECT_CAMERA_USB_ID = "VID_32E4:PID_4801"
CONTROLLERS = ("CS1", "CS2")
RECIPE_COUNT = 16
REPLICAS_PER_RECIPE = 4

T0_LABEL = "T0_F1_G3_BASELINE"
T1_LABEL = "T1_H1_ACTIVE_CODE5_TOP_WHITE_BAND"
T2_LABEL = "T2_H2_COMMENTED_CODE6_BOTTOM_WHITE_BAND"

_T0_ACTION_ID = "f6c6bb92ae708ac325c4bca53ed12d82f19f41fa84adb1ddd8c68e35c40b86ee"
_H1_ACTION_ID = "366e5e3f337ec2cbe713f906af0f79a083e531de836e80b9b38066c7951255f5"

FROZEN_SNAPSHOTS: dict[str, dict[str, Any]] = {
    "t0": {
        "label": T0_LABEL,
        "campaign_id": "EC5_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3",
        "test_id": "EC5-LUMA-GRAY-MECHANISM-POSITION-BALANCED-V3",
        "contract_id": "a114a46bec02b5de80c1f63757723e90cf8e101a81429a8f47eabadc471e3b88",
        "stage": "G3",
        "analysis_kind": V3_ANALYSIS_KIND,
        "result_kind": "mf1750-ec5-luma-gray-mechanism-position-balanced-v3-result",
        "firmware_sha256": "f19eca9e771dedb1c62c25ae017e602bf25ef31f0086aeb26f65bd4575353b22",
        "ordinal": 3,
        "descriptor_id": "094f11ac566bf1f2d4fd0105ad52f1b463cb85605a41c1969b560dcb1982d775",
        "action_id": _T0_ACTION_ID,
        "prior_action_id": "76d277a2d3833e6d208331b5eafea98eadb90ca90329fd4fca25864eb0de3866",
        "role": "G3_ACTIVE_C3_C7_TARGET",
        "total_driver_call_count": 3,
    },
    "t1": {
        "label": T1_LABEL,
        "campaign_id": "EC5_POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1",
        "test_id": "EC5-POSITION-BALANCED-GRAY-HOLD-SUCCESSOR-V1",
        "contract_id": "329e0bb6075291cc2bbdc1045a642b055b06fb8d312d2a7761b1332358e04229",
        "stage": "H1",
        "analysis_kind": HOLD_ANALYSIS_KIND,
        "result_kind": "mf1750-ec5-position-balanced-gray-hold-successor-v1-result",
        "firmware_sha256": "5a0d80b7391ae8f171747a1505521ff7193757bef86bf5e34bfb1f5be2d95db8",
        "ordinal": 1,
        "descriptor_id": "74f7b9b1dc91314425d2b7af485202a8d3c4ad9caef4ea000c5ef22225fec1cf",
        "action_id": _H1_ACTION_ID,
        "prior_action_id": _T0_ACTION_ID,
        "role": "H1_ACTIVE_CODE5_TOP_WHITE_BAND_HOLD_RETAIN_ALL_G3",
        "total_driver_call_count": 1,
    },
    "t2": {
        "label": T2_LABEL,
        "campaign_id": "EC5_POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1",
        "test_id": "EC5-POSITION-BALANCED-GRAY-HOLD-SUCCESSOR-V1",
        "contract_id": "329e0bb6075291cc2bbdc1045a642b055b06fb8d312d2a7761b1332358e04229",
        "stage": "H2",
        "analysis_kind": HOLD_ANALYSIS_KIND,
        "result_kind": "mf1750-ec5-position-balanced-gray-hold-successor-v1-result",
        "firmware_sha256": "5a0d80b7391ae8f171747a1505521ff7193757bef86bf5e34bfb1f5be2d95db8",
        "ordinal": 2,
        "descriptor_id": "0110a55422874ffb3294af146be5e4955e226617624f20f20a653fb515f1d186",
        "action_id": "ba7557595d9780f8ef0354abf0083b43735b5a642411aa63ce08a247f40e253c",
        "prior_action_id": _H1_ACTION_ID,
        "role": "H2_COMMENTED_CODE6_BOTTOM_WHITE_BAND_HOLD_RETAIN_ALL_G3_AND_H1",
        "total_driver_call_count": 2,
    },
}

PROBE_SPEC = {
    "H1": {"x": 64, "y": 8, "width": 320, "height": 24, "target_code": 5},
    "H2": {"x": 64, "y": 568, "width": 320, "height": 24, "target_code": 6},
}

DEFAULT_REVIEW_THRESHOLDS = {
    "maximum_controller_cell_centered_abs_delta_l_star_p95": 3.0,
    "maximum_controller_cell_centered_delta_e76_p95": 5.0,
    "maximum_recipe_median_abs_delta_l_star": 2.0,
    "maximum_recipe_median_delta_e76": 4.0,
    "maximum_within_recipe_position_delta_e76": 8.0,
    "minimum_probe_appearance_delta_e76": 4.0,
    "maximum_probe_retention_delta_e76": 5.0,
}


class PositionBalancedHoldCompareError(ValueError):
    """Raised when sealed T0/T1/T2 evidence is missing or incomparable."""


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PositionBalancedHoldCompareError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    try:
        return require_text(value, label)
    except StaticPhotoContractError as error:
        raise PositionBalancedHoldCompareError(str(error)) from error


def _sha(value: object, label: str) -> str:
    try:
        return require_sha256(value, label)
    except StaticPhotoContractError as error:
        raise PositionBalancedHoldCompareError(str(error)) from error


def _finite(value: object, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PositionBalancedHoldCompareError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise PositionBalancedHoldCompareError(f"{label} must be finite and positive")
    return result


def _lab(value: object, label: str) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise PositionBalancedHoldCompareError(f"{label} must contain three values")
    result = tuple(
        _finite(item, f"{label}[{index}]") for index, item in enumerate(value)
    )
    if not 0 <= result[0] <= 100:
        raise PositionBalancedHoldCompareError(f"{label} L* is outside 0..100")
    return result  # type: ignore[return-value]


def _median(values: Sequence[float]) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise PositionBalancedHoldCompareError("cannot take median of empty values")
    middle = len(ordered) // 2
    return (
        ordered[middle]
        if len(ordered) % 2
        else (ordered[middle - 1] + ordered[middle]) / 2
    )


def _p95(values: Sequence[float]) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise PositionBalancedHoldCompareError("cannot take p95 of empty values")
    rank = 0.95 * (len(ordered) - 1)
    low, high = math.floor(rank), math.ceil(rank)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - rank) + ordered[high] * (rank - low)


def _delta_e(left: Sequence[float], right: Sequence[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def _read_stable(path: Path, label: str) -> bytes:
    resolved = Path(path).resolve()
    try:
        before = resolved.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise PositionBalancedHoldCompareError(
                f"{label} must be a regular non-symlink file"
            )
        payload = resolved.read_bytes()
        after = resolved.lstat()
    except OSError as error:
        raise PositionBalancedHoldCompareError(
            f"cannot read {label}: {resolved}"
        ) from error
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or after.st_size != len(payload):
        raise PositionBalancedHoldCompareError(f"{label} changed while read")
    return payload


def _json(payload: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PositionBalancedHoldCompareError(f"{label} is not UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise PositionBalancedHoldCompareError(f"{label} root must be an object")
    return value


def _verify_seal(value: Mapping[str, Any], label: str) -> str:
    body = deepcopy(dict(value))
    integrity = body.pop("integrity", None)
    expected = canonical_sha256(body)
    if (
        not isinstance(integrity, Mapping)
        or integrity.get("algorithm") != INTEGRITY_ALGORITHM
        or integrity.get("sha256") != expected
    ):
        raise PositionBalancedHoldCompareError(f"{label} canonical integrity differs")
    return expected


def _resolve(base: Path, value: object, label: str) -> Path:
    candidate = Path(_text(value, f"{label}.path"))
    if not candidate.is_absolute():
        repository = Path(__file__).resolve().parents[2]
        repository_candidate = (repository / candidate).resolve()
        local_candidate = (base.parent / candidate).resolve()
        candidate = (
            repository_candidate if repository_candidate.exists() else local_candidate
        )
    return candidate.resolve()


def _file_identity(value: object, label: str, keys: set[str]) -> dict[str, Any]:
    item = _mapping(value, label)
    try:
        require_exact_keys(item, keys, label)
    except StaticPhotoContractError as error:
        raise PositionBalancedHoldCompareError(str(error)) from error
    return {key: _sha(item.get(key), f"{label}.{key}") for key in keys}


def _snapshot_contract(value: object, key: str) -> dict[str, Any]:
    item = _mapping(value, key)
    exact = {
        "label",
        "campaign_id",
        "test_id",
        "contract_id",
        "stage",
        "analysis_kind",
        "analysis",
        "action",
        "capture_sidecar",
        "jpeg",
    }
    try:
        require_exact_keys(item, exact, key)
    except StaticPhotoContractError as error:
        raise PositionBalancedHoldCompareError(str(error)) from error
    frozen = FROZEN_SNAPSHOTS[key]
    for field in (
        "label",
        "campaign_id",
        "test_id",
        "contract_id",
        "stage",
        "analysis_kind",
    ):
        if item.get(field) != frozen[field]:
            raise PositionBalancedHoldCompareError(
                f"{key}.{field} differs from frozen identity"
            )
    analysis = _file_identity(
        item.get("analysis"),
        key + ".analysis",
        {"file_sha256", "canonical_integrity_sha256"},
    )
    action = _mapping(item.get("action"), key + ".action")
    action_keys = {
        "ordinal",
        "action_id",
        "descriptor_id",
        "prior_action_id",
        "role",
        "firmware_sha256",
        "result_kind",
        "file_sha256",
        "canonical_integrity_sha256",
    }
    try:
        require_exact_keys(action, action_keys, key + ".action")
    except StaticPhotoContractError as error:
        raise PositionBalancedHoldCompareError(str(error)) from error
    for field in (
        "ordinal",
        "action_id",
        "descriptor_id",
        "prior_action_id",
        "role",
        "firmware_sha256",
        "result_kind",
    ):
        if action.get(field) != frozen[field]:
            raise PositionBalancedHoldCompareError(f"{key}.action.{field} differs")
    sidecar = _file_identity(
        item.get("capture_sidecar"),
        key + ".capture_sidecar",
        {"file_sha256", "canonical_integrity_sha256", "capture_id"},
    )
    jpeg = _file_identity(item.get("jpeg"), key + ".jpeg", {"file_sha256"})
    return {
        **{
            field: frozen[field]
            for field in (
                "label",
                "campaign_id",
                "test_id",
                "contract_id",
                "stage",
                "analysis_kind",
            )
        },
        "total_driver_call_count": frozen["total_driver_call_count"],
        "analysis": analysis,
        "action": {
            **{
                field: frozen[field]
                for field in (
                    "ordinal",
                    "action_id",
                    "descriptor_id",
                    "prior_action_id",
                    "role",
                    "firmware_sha256",
                    "result_kind",
                )
            },
            "file_sha256": _sha(action.get("file_sha256"), key + ".action.file_sha256"),
            "canonical_integrity_sha256": _sha(
                action.get("canonical_integrity_sha256"),
                key + ".action.canonical_integrity_sha256",
            ),
        },
        "capture_sidecar": sidecar,
        "jpeg": jpeg,
    }


def _validate_contract(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "kind",
        "comparison_id",
        "snapshots",
        "review_thresholds",
        "probe_spec",
        "qualification_boundary",
    }
    try:
        require_exact_keys(unsigned, expected, "identity contract")
    except StaticPhotoContractError as error:
        raise PositionBalancedHoldCompareError(str(error)) from error
    if (
        unsigned.get("schema_version") != SCHEMA_VERSION
        or unsigned.get("kind") != IDENTITY_CONTRACT_KIND
    ):
        raise PositionBalancedHoldCompareError("identity contract kind/schema differs")
    snapshots_raw = _mapping(unsigned.get("snapshots"), "snapshots")
    try:
        require_exact_keys(snapshots_raw, {"t0", "t1", "t2"}, "snapshots")
    except StaticPhotoContractError as error:
        raise PositionBalancedHoldCompareError(str(error)) from error
    snapshots = {
        key: _snapshot_contract(snapshots_raw.get(key), key)
        for key in ("t0", "t1", "t2")
    }
    if len({snapshots[key]["analysis"]["file_sha256"] for key in snapshots}) != 3:
        raise PositionBalancedHoldCompareError("T0/T1/T2 analysis files must differ")
    if len({snapshots[key]["capture_sidecar"]["capture_id"] for key in snapshots}) != 3:
        raise PositionBalancedHoldCompareError("T0/T1/T2 capture IDs must differ")
    thresholds_raw = _mapping(unsigned.get("review_thresholds"), "review_thresholds")
    try:
        require_exact_keys(
            thresholds_raw, set(DEFAULT_REVIEW_THRESHOLDS), "review_thresholds"
        )
    except StaticPhotoContractError as error:
        raise PositionBalancedHoldCompareError(str(error)) from error
    thresholds = {
        key: _finite(thresholds_raw.get(key), f"review_thresholds.{key}", positive=True)
        for key in DEFAULT_REVIEW_THRESHOLDS
    }
    if unsigned.get("probe_spec") != PROBE_SPEC:
        raise PositionBalancedHoldCompareError("probe geometry/target codes differ")
    wanted_boundary = {
        "camera_relative_review_only": True,
        "controller_palette_evidence_pass_forbidden": True,
        "direct_passed_evidence_generation_forbidden": True,
        "qualified_colour_count": 0,
        "qualified_gray_levels": 0,
        "qualified_brightness_levels": 0,
    }
    if unsigned.get("qualification_boundary") != wanted_boundary:
        raise PositionBalancedHoldCompareError("qualification boundary differs")
    return {
        "comparison_id": _text(unsigned.get("comparison_id"), "comparison_id"),
        "snapshots": snapshots,
        "thresholds": thresholds,
    }


def seal_position_balanced_hold_identity_contract(
    unsigned: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate and canonically seal the exact T0/T1/T2 source contract."""

    if "integrity" in unsigned:
        raise PositionBalancedHoldCompareError("unsigned contract contains integrity")
    _validate_contract(unsigned)
    try:
        return attach_integrity(unsigned)
    except StaticPhotoContractError as error:
        raise PositionBalancedHoldCompareError(str(error)) from error


def _camera_lock(
    sidecar: Mapping[str, Any], expected_ordinal: int, label: str
) -> dict[str, Any]:
    camera = _mapping(sidecar.get("camera"), label + ".camera")
    coverage = _mapping(sidecar.get("coverage"), label + ".coverage")
    requested = _mapping(
        camera.get("requested_settings"), label + ".camera.requested_settings"
    )
    before = _mapping(
        camera.get("effective_settings_before_frame"),
        label + ".camera.effective_settings_before_frame",
    )
    after = _mapping(
        camera.get("effective_settings_after_frame"),
        label + ".camera.effective_settings_after_frame",
    )
    writes = _mapping(camera.get("set_results"), label + ".camera.set_results")
    instance = _text(camera.get("instance_id"), label + ".camera.instance_id")
    if (
        camera.get("camera_id") != "48MP USB Camera"
        or "vid_32e4&pid_4801" not in instance.casefold()
        or "vid_1bcf&pid_0b15" in instance.casefold()
        or str(camera.get("backend", "")).casefold() != "dshow"
        or type(camera.get("index")) is not int
        or sidecar.get("ordinal") != expected_ordinal
        or sidecar.get("capture_binding") != "live_synchronized"
    ):
        raise PositionBalancedHoldCompareError(f"{label} 48MP/action binding differs")
    for name, settings in (
        ("requested", requested),
        ("before", before),
        ("after", after),
    ):
        if settings.get("frame_width") != 4000 or settings.get("frame_height") != 3000:
            raise PositionBalancedHoldCompareError(f"{label} {name} is not 4000x3000")
    required_writes = {key for key, value in requested.items() if value is not None}
    if not required_writes or any(
        writes.get(key) is not True for key in required_writes
    ):
        raise PositionBalancedHoldCompareError(f"{label} camera setting writes differ")
    scope = coverage.get("scope")
    full = scope == "full_panel"
    if (
        scope not in {"full_panel", "partial_panel"}
        or coverage.get("full_panel_visible") is not full
        or coverage.get("full_panel_uncropped") is not full
    ):
        raise PositionBalancedHoldCompareError(f"{label} coverage boundary differs")
    return {
        "camera_id": camera["camera_id"],
        "camera_instance_id": camera["instance_id"],
        "camera_usb_identity": PROJECT_CAMERA_USB_ID,
        "camera_index": camera["index"],
        "backend": camera["backend"],
        "requested_settings": deepcopy(dict(requested)),
        "effective_settings_before_frame": deepcopy(dict(before)),
        "effective_settings_after_frame": deepcopy(dict(after)),
        "setting_write_results": deepcopy(dict(writes)),
        "manual_focus_exposure_white_balance_gate": True,
        "mount_id": _text(coverage.get("mount_id"), label + ".coverage.mount_id"),
        "full_panel_visible": full,
        "coverage_scope": scope,
    }


def _bound_file(
    analysis_path: Path,
    record: object,
    expected_sha: str,
    label: str,
) -> tuple[Path, bytes, Mapping[str, Any]]:
    item = _mapping(record, label)
    path = _resolve(analysis_path, item.get("path"), label)
    payload = _read_stable(path, label)
    digest = hashlib.sha256(payload).hexdigest()
    if (
        item.get("bytes") != len(payload)
        or item.get("file_sha256") != digest
        or digest != expected_sha
    ):
        raise PositionBalancedHoldCompareError(f"{label} byte/hash binding differs")
    return path, payload, item


def _validate_action_result(
    root: Mapping[str, Any], expected: Mapping[str, Any], label: str
) -> tuple[str, str]:
    canonical = _verify_seal(root, label)
    action = _mapping(root.get("action"), label + ".action")
    for field in ("ordinal", "action_id", "descriptor_id", "prior_action_id", "role"):
        if action.get(field) != expected[field]:
            raise PositionBalancedHoldCompareError(
                f"{label} action chain {field} differs"
            )
    terminal = _mapping(root.get("terminal_report"), label + ".terminal_report")
    fixed = {
        "campaign_id": expected["campaign_id"],
        "contract_id": expected["contract_id"],
        "terminal_state": "COMPLETE",
        "result": True,
        "ordinal": expected["ordinal"],
        "descriptor_id": expected["descriptor_id"],
        "action_id": expected["action_id"],
        "role": expected["role"],
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": expected["total_driver_call_count"],
        "no_retry": True,
        "no_recovery": True,
    }
    if any(terminal.get(key) != value for key, value in fixed.items()):
        raise PositionBalancedHoldCompareError(
            f"{label} terminal COMPLETE chain differs"
        )
    if (
        root.get("kind") != expected["result_kind"]
        or root.get("firmware_sha256") != expected["firmware_sha256"]
        or root.get("outcome") != "complete_pass"
        or root.get("visible_refreshes") != 1
        or root.get("no_retry") is not True
        or root.get("no_recovery") is not True
        or root.get("no_autochain") is not True
    ):
        raise PositionBalancedHoldCompareError(f"{label} result semantics differ")
    boot_nonce = root.get("boot_nonce")
    if not isinstance(boot_nonce, str) or not boot_nonce:
        raise PositionBalancedHoldCompareError(f"{label} boot nonce missing")
    return canonical, boot_nonce


def _candidate_cells(
    observation: Mapping[str, Any], stage: str, label: str
) -> dict[str, dict[str, Any]]:
    if (
        observation.get("stage") != stage
        or observation.get("controller_policy") != "CS1_AND_CS2_EVALUATED_SEPARATELY"
        or observation.get("spatial_dither") is not False
        or observation.get("qualified_colour_count") != 0
        or observation.get("qualified_gray_levels") != 0
        or observation.get("qualified_brightness_levels") != 0
        or observation.get("automatic_colour_qualification") is not False
    ):
        raise PositionBalancedHoldCompareError(f"{label} observation boundary differs")
    values = observation.get("measurements")
    if not isinstance(values, list) or not 24 <= len(values) <= 128:
        raise PositionBalancedHoldCompareError(f"{label} visible-cell count differs")
    result: dict[str, dict[str, Any]] = {}
    physical: set[tuple[str, int, int]] = set()
    for index, raw in enumerate(values):
        cell = _mapping(raw, f"{label}.measurements[{index}]")
        controller = cell.get("controller")
        recipe = cell.get("recipe")
        repeat = cell.get("repeat_position")
        row, column = cell.get("row"), cell.get("column")
        if (
            controller not in CONTROLLERS
            or type(recipe) is not int
            or recipe not in range(RECIPE_COUNT)
            or type(repeat) is not int
            or repeat not in range(REPLICAS_PER_RECIPE)
            or type(row) is not int
            or row not in range(8)
            or type(column) is not int
            or column not in range(8)
        ):
            raise PositionBalancedHoldCompareError(f"{label} cell identity differs")
        sample_id = f"{controller}-R{recipe:02d}-P{repeat}"
        if cell.get("sample_id") != sample_id or sample_id in result:
            raise PositionBalancedHoldCompareError(f"{label} sample identity differs")
        position = (str(controller), row, column)
        if position in physical:
            raise PositionBalancedHoldCompareError(f"{label} duplicate physical cell")
        physical.add(position)
        flags = (
            "bottom_edge_clean",
            "horizontal_stripe_absent",
            "vertical_stripe_absent",
            "roi_visible",
        )
        if any(type(cell.get(flag)) is not bool for flag in flags):
            raise PositionBalancedHoldCompareError(f"{label} four-edge flag differs")
        identity = {
            key: deepcopy(cell.get(key))
            for key in (
                "sample_id",
                "controller",
                "recipe",
                "repeat_position",
                "row",
                "column",
                "local_roi",
                "panel_roi",
                "central_inset_fraction",
            )
        }
        result[sample_id] = {
            "identity": identity,
            "lab": _lab(cell.get("lab"), f"{label}.{sample_id}.lab"),
            "four_edge_purity_gate_pass": all(cell.get(flag) is True for flag in flags),
        }
    for controller in CONTROLLERS:
        if (
            sum(
                cell["identity"]["controller"] == controller for cell in result.values()
            )
            < 8
        ):
            raise PositionBalancedHoldCompareError(
                f"{label} has fewer than 8 {controller} cells"
            )
    return result


def _probe_cells(
    observation: Mapping[str, Any], label: str
) -> dict[str, dict[str, Any]]:
    values = observation.get("hold_probe_measurements", [])
    if not isinstance(values, list) or len(values) > 4:
        raise PositionBalancedHoldCompareError(
            f"{label} HOLD probe measurements differ"
        )
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(values):
        cell = _mapping(raw, f"{label}.hold_probe_measurements[{index}]")
        controller, probe = cell.get("controller"), cell.get("probe")
        if controller not in CONTROLLERS or probe not in PROBE_SPEC:
            raise PositionBalancedHoldCompareError(
                f"{label} HOLD probe identity differs"
            )
        sample_id = f"{controller}-{probe}"
        if cell.get("sample_id") != sample_id or sample_id in result:
            raise PositionBalancedHoldCompareError(f"{label} HOLD probe sample differs")
        if cell.get("local_roi") != {
            key: PROBE_SPEC[str(probe)][key] for key in ("x", "y", "width", "height")
        }:
            raise PositionBalancedHoldCompareError(f"{label} HOLD probe ROI differs")
        flags = (
            "top_edge_clean",
            "right_edge_clean",
            "bottom_edge_clean",
            "left_edge_clean",
            "central_inset_purity_pass",
            "roi_visible",
        )
        if any(type(cell.get(flag)) is not bool for flag in flags):
            raise PositionBalancedHoldCompareError(
                f"{label} HOLD probe edge/purity flag differs"
            )
        result[sample_id] = {
            "controller": controller,
            "probe": probe,
            "lab": _lab(cell.get("lab"), f"{label}.{sample_id}.lab"),
            "four_edge_purity_gate_pass": all(cell.get(flag) is True for flag in flags),
        }
    return result


def _validate_snapshot(
    path: Path, expected: Mapping[str, Any], label: str
) -> dict[str, Any]:
    path = Path(path).resolve()
    payload = _read_stable(path, label)
    root = _json(payload, label)
    canonical = _verify_seal(root, label)
    if (
        hashlib.sha256(payload).hexdigest() != expected["analysis"]["file_sha256"]
        or canonical != expected["analysis"]["canonical_integrity_sha256"]
    ):
        raise PositionBalancedHoldCompareError(f"{label} analysis hash differs")
    fixed = {
        "schema_version": 1,
        "kind": expected["analysis_kind"],
        "campaign_id": expected["campaign_id"],
        "test_id": expected["test_id"],
        "contract_id": expected["contract_id"],
        "stage": expected["stage"],
        "hardware_accessed": False,
        "camera_accessed": False,
        "network_requests": 0,
    }
    if any(root.get(key) != value for key, value in fixed.items()):
        raise PositionBalancedHoldCompareError(f"{label} analysis identity differs")
    source = _mapping(root.get("source_evidence"), label + ".source_evidence")
    action_path, action_payload, action_record = _bound_file(
        path, source.get("action"), expected["action"]["file_sha256"], label + " action"
    )
    action_root = _json(action_payload, label + " action")
    action_canonical, boot_nonce = _validate_action_result(
        action_root, {**expected, **expected["action"]}, label + " action"
    )
    if (
        action_canonical != expected["action"]["canonical_integrity_sha256"]
        or action_record.get("canonical_integrity_sha256") != action_canonical
    ):
        raise PositionBalancedHoldCompareError(f"{label} action canonical hash differs")
    sidecar_path, sidecar_payload, sidecar_record = _bound_file(
        path,
        source.get("capture_sidecar"),
        expected["capture_sidecar"]["file_sha256"],
        label + " sidecar",
    )
    sidecar = _json(sidecar_payload, label + " sidecar")
    sidecar_canonical = _verify_seal(sidecar, label + " sidecar")
    if (
        sidecar_canonical != expected["capture_sidecar"]["canonical_integrity_sha256"]
        or sidecar_record.get("canonical_integrity_sha256") != sidecar_canonical
        or sidecar.get("capture_id") != expected["capture_sidecar"]["capture_id"]
        or sidecar_record.get("capture_id") != expected["capture_sidecar"]["capture_id"]
    ):
        raise PositionBalancedHoldCompareError(
            f"{label} sidecar canonical binding differs"
        )
    for field in ("campaign_id", "test_id", "contract_id"):
        if sidecar.get(field) != expected[field]:
            raise PositionBalancedHoldCompareError(f"{label} sidecar {field} differs")
    for field in ("ordinal", "action_id", "descriptor_id", "role"):
        if sidecar.get(field) != expected["action"][field]:
            raise PositionBalancedHoldCompareError(f"{label} sidecar action differs")
    photo_path, _photo_payload, photo_record = _bound_file(
        path, source.get("photo"), expected["jpeg"]["file_sha256"], label + " JPEG"
    )
    sidecar_action = _mapping(
        sidecar.get("action_result"), label + ".sidecar.action_result"
    )
    sidecar_photo = _mapping(sidecar.get("photo"), label + ".sidecar.photo")
    if (
        _resolve(sidecar_path, sidecar_action.get("path"), label + ".action_result")
        != action_path
        or sidecar_action.get("file_sha256") != expected["action"]["file_sha256"]
        or sidecar_action.get("canonical_integrity_sha256")
        != expected["action"]["canonical_integrity_sha256"]
        or _resolve(sidecar_path, sidecar_photo.get("path"), label + ".photo")
        != photo_path
        or sidecar_photo.get("sha256") != expected["jpeg"]["file_sha256"]
        or photo_record.get("file_sha256") != expected["jpeg"]["file_sha256"]
    ):
        raise PositionBalancedHoldCompareError(
            f"{label} action/JPEG deep binding differs"
        )
    lock = _camera_lock(sidecar, int(expected["action"]["ordinal"]), label + " sidecar")
    legacy_lock = dict(lock)
    legacy_lock.pop("coverage_scope")
    if root.get("camera_lock") not in (lock, legacy_lock):
        raise PositionBalancedHoldCompareError(f"{label} analysis camera lock differs")
    observation = _mapping(
        root.get("observation_document"), label + ".observation_document"
    )
    _verify_seal(observation, label + ".observation_document")
    cells = _candidate_cells(observation, str(expected["stage"]), label)
    probes = _probe_cells(observation, label)
    if lock["coverage_scope"] == "full_panel" and len(cells) != 128:
        raise PositionBalancedHoldCompareError(
            f"{label} full-panel capture must contain all 128 cells"
        )
    if lock["coverage_scope"] == "partial_panel" and len(cells) == 128:
        raise PositionBalancedHoldCompareError(
            f"{label} partial capture cannot claim all 128 cells"
        )
    quality = _mapping(root.get("capture_quality"), label + ".capture_quality")
    if any(
        quality.get(key) is not True
        for key in (
            "geometry_gate_pass",
            "manual_camera_lock_gate_pass",
            "exposure_gate_pass",
            "coarse_uniformity_gate_pass",
        )
    ):
        raise PositionBalancedHoldCompareError(f"{label} capture quality failed")
    geometry = _mapping(root.get("geometry"), label + ".geometry")
    method = _mapping(root.get("method"), label + ".method")
    if (
        geometry.get("gate_pass") is not True
        or method.get("controllers_pooled") is not False
        or method.get("spatial_dither") is not False
    ):
        raise PositionBalancedHoldCompareError(
            f"{label} geometry/method boundary differs"
        )
    geometry_signature = {
        "geometry_method": geometry.get("method"),
        "method": deepcopy(dict(method)),
        "quality_thresholds": deepcopy(
            dict(
                _mapping(root.get("quality_thresholds"), label + ".quality_thresholds")
            )
        ),
        "roi_manifest_sha256": _sha(
            observation.get("roi_manifest_sha256"), label + ".roi_manifest_sha256"
        ),
        "logical_cells": [cells[key]["identity"] for key in sorted(cells)],
    }
    return {
        "path": path,
        "payload": payload,
        "canonical_sha256": canonical,
        "camera_lock": lock,
        "source_paths": {
            "action": action_path,
            "capture_sidecar": sidecar_path,
            "photo": photo_path,
        },
        "boot_nonce": boot_nonce,
        "cells": cells,
        "probes": probes,
        "geometry_signature": geometry_signature,
    }


def _compare_sources(snapshots: Mapping[str, Mapping[str, Any]]) -> None:
    t0, t1, t2 = snapshots["t0"], snapshots["t1"], snapshots["t2"]
    lock_fields = (
        "camera_id",
        "camera_instance_id",
        "camera_usb_identity",
        "camera_index",
        "backend",
        "requested_settings",
        "effective_settings_before_frame",
        "effective_settings_after_frame",
        "mount_id",
        "coverage_scope",
    )
    for key in ("t1", "t2"):
        current = snapshots[key]
        if any(
            current["camera_lock"][field] != t0["camera_lock"][field]
            for field in lock_fields
        ):
            raise PositionBalancedHoldCompareError(
                "camera instance/index/backend/mount/settings differ"
            )
        if set(current["cells"]) != set(t0["cells"]):
            raise PositionBalancedHoldCompareError(
                "T0/T1/T2 visible-cell key sets differ"
            )
        if any(
            current["cells"][sample]["identity"] != t0["cells"][sample]["identity"]
            for sample in t0["cells"]
        ):
            raise PositionBalancedHoldCompareError("T0/T1/T2 cell geometry differs")
        if current["geometry_signature"] != t0["geometry_signature"]:
            raise PositionBalancedHoldCompareError("T0/T1/T2 logical geometry differs")
        if set(current["probes"]) != set(t0["probes"]):
            raise PositionBalancedHoldCompareError(
                "T0/T1/T2 visible probe key sets differ"
            )
    if t1["boot_nonce"] != t2["boot_nonce"]:
        raise PositionBalancedHoldCompareError("H1/H2 action chain boot nonce differs")
    for source in ("action", "capture_sidecar", "photo"):
        if len({snapshots[key]["source_paths"][source] for key in snapshots}) != 3:
            raise PositionBalancedHoldCompareError(f"T0/T1/T2 reuse a {source} file")


def _centers(
    cells: Mapping[str, Mapping[str, Any]],
) -> dict[str, tuple[float, float, float]]:
    return {
        controller: tuple(
            _median(
                [
                    cell["lab"][channel]
                    for cell in cells.values()
                    if cell["identity"]["controller"] == controller
                ]
            )
            for channel in range(3)
        )
        for controller in CONTROLLERS
    }  # type: ignore[return-value]


def _transition(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    name: str,
    thresholds: Mapping[str, float],
) -> dict[str, Any]:
    before_center, after_center = _centers(before["cells"]), _centers(after["cells"])
    cell_results = []
    for sample_id in sorted(before["cells"]):
        left, right = before["cells"][sample_id], after["cells"][sample_id]
        controller = left["identity"]["controller"]
        left_centered = tuple(
            left["lab"][i] - before_center[controller][i] for i in range(3)
        )
        right_centered = tuple(
            right["lab"][i] - after_center[controller][i] for i in range(3)
        )
        delta = tuple(right_centered[i] - left_centered[i] for i in range(3))
        cell_results.append(
            {
                **left["identity"],
                "centered_delta_lab": list(delta),
                "centered_delta_l_star": delta[0],
                "absolute_centered_delta_l_star": abs(delta[0]),
                "centered_delta_e76": math.sqrt(sum(value * value for value in delta)),
                "before_four_edge_purity_gate_pass": left["four_edge_purity_gate_pass"],
                "after_four_edge_purity_gate_pass": right["four_edge_purity_gate_pass"],
                "qualified_level": False,
            }
        )
    recipes = []
    for controller in CONTROLLERS:
        for recipe in range(RECIPE_COUNT):
            cells = [
                item
                for item in cell_results
                if item["controller"] == controller and item["recipe"] == recipe
            ]
            if len(cells) != REPLICAS_PER_RECIPE:
                recipes.append(
                    {
                        "controller": controller,
                        "recipe": recipe,
                        "replica_count": len(cells),
                        "required_replica_count": REPLICAS_PER_RECIPE,
                        "status": "UNTESTED_MISSING_REPLICAS",
                        "four_edge_purity_gate_pass": False,
                        "metric_gate_pass": False,
                        "review_gate_pass": False,
                        "qualified_level": False,
                    }
                )
                continue
            ids = [item["sample_id"] for item in cells]
            before_labs = [before["cells"][item]["lab"] for item in ids]
            after_labs = [after["cells"][item]["lab"] for item in ids]
            within = max(
                max(_delta_e(a, b) for a in before_labs for b in before_labs),
                max(_delta_e(a, b) for a in after_labs for b in after_labs),
            )
            edge_pass = all(
                item["before_four_edge_purity_gate_pass"]
                and item["after_four_edge_purity_gate_pass"]
                for item in cells
            )
            median_abs_l = _median(
                [item["absolute_centered_delta_l_star"] for item in cells]
            )
            median_de = _median([item["centered_delta_e76"] for item in cells])
            metric_pass = (
                median_abs_l <= thresholds["maximum_recipe_median_abs_delta_l_star"]
                and median_de <= thresholds["maximum_recipe_median_delta_e76"]
                and within <= thresholds["maximum_within_recipe_position_delta_e76"]
            )
            recipes.append(
                {
                    "controller": controller,
                    "recipe": recipe,
                    "sample_ids": sorted(ids),
                    "replica_count": 4,
                    "required_replica_count": 4,
                    "status": "REVIEWED_COMPLETE_REPLICA_SET",
                    "median_centered_delta_l_star": _median(
                        [item["centered_delta_l_star"] for item in cells]
                    ),
                    "median_absolute_centered_delta_l_star": median_abs_l,
                    "median_centered_delta_e76": median_de,
                    "maximum_within_recipe_position_delta_e76": within,
                    "four_edge_purity_gate_pass": edge_pass,
                    "metric_gate_pass": metric_pass,
                    "review_gate_pass": edge_pass and metric_pass,
                    "qualified_level": False,
                }
            )
    controller_results = {}
    for controller in CONTROLLERS:
        cells = [item for item in cell_results if item["controller"] == controller]
        local_recipes = [item for item in recipes if item["controller"] == controller]
        aggregate = (
            _p95([item["absolute_centered_delta_l_star"] for item in cells])
            <= thresholds["maximum_controller_cell_centered_abs_delta_l_star_p95"]
            and _p95([item["centered_delta_e76"] for item in cells])
            <= thresholds["maximum_controller_cell_centered_delta_e76_p95"]
        )
        controller_results[controller] = {
            "visible_cell_count": len(cells),
            "reviewed_complete_recipe_count": sum(
                item["status"] == "REVIEWED_COMPLETE_REPLICA_SET"
                for item in local_recipes
            ),
            "untested_missing_replica_recipe_count": sum(
                item["status"] == "UNTESTED_MISSING_REPLICAS" for item in local_recipes
            ),
            "cell_centered_absolute_delta_l_star_p95": _p95(
                [item["absolute_centered_delta_l_star"] for item in cells]
            ),
            "cell_centered_delta_e76_p95": _p95(
                [item["centered_delta_e76"] for item in cells]
            ),
            "aggregate_metric_gate_pass": aggregate,
            "all_complete_recipe_gates_pass": all(
                item["review_gate_pass"]
                for item in local_recipes
                if item["status"] == "REVIEWED_COMPLETE_REPLICA_SET"
            ),
            "qualified_level_count": 0,
        }
    return {
        "name": name,
        "cell_results": cell_results,
        "recipe_results": recipes,
        "controller_results": controller_results,
    }


def _centered_probe_lab(
    snapshot: Mapping[str, Any], sample_id: str
) -> tuple[float, float, float]:
    probe = snapshot["probes"][sample_id]
    center = _centers(snapshot["cells"])[probe["controller"]]
    return tuple(probe["lab"][index] - center[index] for index in range(3))  # type: ignore[return-value]


def _probe_review(
    snapshots: Mapping[str, Mapping[str, Any]], thresholds: Mapping[str, float]
) -> dict[str, Any]:
    expected = {
        f"{controller}-{probe}" for controller in CONTROLLERS for probe in PROBE_SPEC
    }
    visible = set(snapshots["t0"]["probes"])
    if visible != expected:
        return {
            "status": "UNTESTED_PROBES_NOT_ALL_VISIBLE",
            "visible_probe_keys": sorted(visible),
            "required_probe_keys": sorted(expected),
            "h1_retained_at_t2": None,
            "h1_appeared_at_t1": None,
            "h2_appeared_at_t2": None,
            "t2_probe_four_edge_purity_gate_pass": None,
            "cross_lut_probe_review_pass": False,
        }
    results = []
    for controller in CONTROLLERS:
        h1 = f"{controller}-H1"
        h2 = f"{controller}-H2"
        t0_h1, t1_h1, t2_h1 = (
            _centered_probe_lab(snapshots[key], h1) for key in ("t0", "t1", "t2")
        )
        t1_h2, t2_h2 = (_centered_probe_lab(snapshots[key], h2) for key in ("t1", "t2"))
        appearance_h1 = _delta_e(t0_h1, t1_h1)
        retention_h1 = _delta_e(t1_h1, t2_h1)
        appearance_h2 = _delta_e(t1_h2, t2_h2)
        t2_edges = (
            snapshots["t2"]["probes"][h1]["four_edge_purity_gate_pass"]
            and snapshots["t2"]["probes"][h2]["four_edge_purity_gate_pass"]
        )
        results.append(
            {
                "controller": controller,
                "h1_t1_vs_t0_centered_delta_e76": appearance_h1,
                "h1_t2_vs_t1_centered_delta_e76": retention_h1,
                "h2_t2_vs_t1_centered_delta_e76": appearance_h2,
                "h1_appeared_at_t1": appearance_h1
                >= thresholds["minimum_probe_appearance_delta_e76"],
                "h1_retained_at_t2": retention_h1
                <= thresholds["maximum_probe_retention_delta_e76"],
                "h2_appeared_at_t2": appearance_h2
                >= thresholds["minimum_probe_appearance_delta_e76"],
                "t2_probe_four_edge_purity_gate_pass": t2_edges,
            }
        )
    passed = all(
        item["h1_appeared_at_t1"]
        and item["h1_retained_at_t2"]
        and item["h2_appeared_at_t2"]
        and item["t2_probe_four_edge_purity_gate_pass"]
        for item in results
    )
    return {
        "status": "REVIEWED_ALL_PROBES_VISIBLE",
        "visible_probe_keys": sorted(visible),
        "required_probe_keys": sorted(expected),
        "controllers": results,
        "h1_appeared_at_t1": all(item["h1_appeared_at_t1"] for item in results),
        "h1_retained_at_t2": all(item["h1_retained_at_t2"] for item in results),
        "h2_appeared_at_t2": all(item["h2_appeared_at_t2"] for item in results),
        "t2_probe_four_edge_purity_gate_pass": all(
            item["t2_probe_four_edge_purity_gate_pass"] for item in results
        ),
        "cross_lut_probe_review_pass": passed,
    }


def compare_position_balanced_hold(
    t0_analysis_path: str | Path,
    t1_analysis_path: str | Path,
    t2_analysis_path: str | Path,
    *,
    identity_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Produce sealed same-profile and directional cross-LUT review drafts."""

    try:
        unsigned_contract = verify_integrity(
            identity_contract, "position-balanced HOLD identity contract"
        )
    except StaticPhotoContractError as error:
        raise PositionBalancedHoldCompareError(str(error)) from error
    contract = _validate_contract(unsigned_contract)
    paths = {
        "t0": Path(t0_analysis_path),
        "t1": Path(t1_analysis_path),
        "t2": Path(t2_analysis_path),
    }
    snapshots = {
        key: _validate_snapshot(
            paths[key], contract["snapshots"][key], FROZEN_SNAPSHOTS[key]["label"]
        )
        for key in ("t0", "t1", "t2")
    }
    _compare_sources(snapshots)
    transitions = {
        "t1_vs_t0": _transition(
            snapshots["t0"], snapshots["t1"], "T1_H1_VS_T0_G3", contract["thresholds"]
        ),
        "t2_vs_t0": _transition(
            snapshots["t0"], snapshots["t2"], "T2_H2_VS_T0_G3", contract["thresholds"]
        ),
        "t2_vs_t1": _transition(
            snapshots["t1"], snapshots["t2"], "T2_H2_VS_T1_H1", contract["thresholds"]
        ),
    }
    probes = _probe_review(snapshots, contract["thresholds"])
    full = len(snapshots["t0"]["cells"]) == 128
    complete_t1 = all(
        item["status"] == "REVIEWED_COMPLETE_REPLICA_SET" and item["review_gate_pass"]
        for item in transitions["t1_vs_t0"]["recipe_results"]
    )
    complete_t2 = all(
        item["status"] == "REVIEWED_COMPLETE_REPLICA_SET" and item["review_gate_pass"]
        for item in transitions["t2_vs_t1"]["recipe_results"]
    )
    same_profile_status = (
        "REVIEW_DRAFT_SUPPORTS_SAME_PROFILE_LOCAL_HOLD_CANDIDATE"
        if (
            full
            and complete_t1
            and probes["status"] == "REVIEWED_ALL_PROBES_VISIBLE"
            and probes["h1_appeared_at_t1"]
        )
        else "REVIEW_DRAFT_PARTIAL_OR_GATE_FAILED"
    )
    if probes["status"] == "UNTESTED_PROBES_NOT_ALL_VISIBLE":
        cross_status = "UNTESTED_PROBES_NOT_VISIBLE"
    elif full and complete_t2 and probes["cross_lut_probe_review_pass"]:
        cross_status = "REVIEW_DRAFT_SUPPORTS_COMMENTED_RETAINS_ACTIVE_DIRECTION"
    else:
        cross_status = "REVIEW_DRAFT_GATE_FAILED"
    source_reports = {
        key: {
            "path": str(snapshots[key]["path"]),
            "bytes": len(snapshots[key]["payload"]),
            "file_sha256": hashlib.sha256(snapshots[key]["payload"]).hexdigest(),
            "canonical_integrity_sha256": snapshots[key]["canonical_sha256"],
            "campaign_id": contract["snapshots"][key]["campaign_id"],
            "action_id": contract["snapshots"][key]["action"]["action_id"],
        }
        for key in ("t0", "t1", "t2")
    }
    binding = canonical_sha256(
        {
            "identity_contract_canonical_sha256": canonical_sha256(unsigned_contract),
            "source_reports": source_reports,
        }
    )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": COMPARISON_KIND,
        "comparison_id": contract["comparison_id"],
        "decision": "REVIEW_DRAFTS_EMITTED_NO_QUALIFICATION",
        "offline_only": True,
        "identity_contract": {
            "canonical_sha256": canonical_sha256(unsigned_contract),
            "comparison_id": contract["comparison_id"],
        },
        "source_reports": source_reports,
        "action_chain": {
            "t0_g3_action_id": _T0_ACTION_ID,
            "t1_h1_prior_action_id": _T0_ACTION_ID,
            "t1_h1_action_id": _H1_ACTION_ID,
            "t2_h2_prior_action_id": _H1_ACTION_ID,
            "t2_h2_action_id": FROZEN_SNAPSHOTS["t2"]["action_id"],
            "h1_h2_same_boot": True,
            "deep_file_and_canonical_hashes_verified": True,
        },
        "comparability": {
            "same_48mp_camera_instance_index_backend_mount": True,
            "image_dimensions": [4000, 3000],
            "requested_and_effective_settings_exactly_equal": True,
            "visible_cell_key_sets_exactly_equal": True,
            "visible_probe_key_sets_exactly_equal": True,
            "coverage_scope": snapshots["t0"]["camera_lock"]["coverage_scope"],
            "visible_cell_count": len(snapshots["t0"]["cells"]),
            "full_128_cell_coverage": full,
            "controllers_pooled": False,
            "cross_controller_equivalence_used": False,
            "spatial_dithering_used": False,
        },
        "review_thresholds": contract["thresholds"],
        "candidate_comparisons": transitions,
        "probe_review": probes,
        "same_profile_local_hold_review_draft": {
            "kind": "MF1750_SAME_PROFILE_LOCAL_HOLD_REVIEW_DRAFT",
            "status": same_profile_status,
            "comparison": "T1_H1_ACTIVE_VS_T0_G3_ACTIVE",
            "comparison_input_binding_sha256": binding,
            "direct_controller_palette_evidence_conversion_allowed": False,
            "controller_palette_evidence_passed": False,
            "qualified_level_count": 0,
        },
        "commented_retains_active_directional_cross_lut_review_draft": {
            "kind": "MF1750_COMMENTED_RETAINS_ACTIVE_DIRECTIONAL_CROSS_LUT_REVIEW_DRAFT",
            "status": cross_status,
            "direction": "T2_COMMENTED_CODE6_RETAINS_T1_ACTIVE_CODE5_AND_G3_CANDIDATES",
            "comparison_input_binding_sha256": binding,
            "direct_controller_palette_evidence_conversion_allowed": False,
            "controller_palette_evidence_passed": False,
            "qualified_level_count": 0,
        },
        "qualification_boundary": {
            "review_drafts_are_not_controller_palette_evidence": True,
            "controller_palette_evidence_passed": False,
            "automatic_local_hold_claimed": False,
            "automatic_cross_lut_hold_claimed": False,
            "qualified_colour_count": 0,
            "qualified_gray_levels": 0,
            "qualified_brightness_levels": 0,
            "spatial_dithering_used": False,
        },
        "execution_boundary": {
            "hardware_accessed": False,
            "camera_accessed": False,
            "network_accessed": False,
            "relay_or_j2_operated": False,
            "display_refresh_requested": False,
        },
    }
    return attach_integrity(unsigned)


def verify_position_balanced_hold_comparison(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify canonical integrity and immutable no-qualification boundaries."""

    try:
        unsigned = verify_integrity(value, "position-balanced HOLD comparison")
    except StaticPhotoContractError as error:
        raise PositionBalancedHoldCompareError(str(error)) from error
    if (
        unsigned.get("schema_version") != SCHEMA_VERSION
        or unsigned.get("kind") != COMPARISON_KIND
        or unsigned.get("decision") != "REVIEW_DRAFTS_EMITTED_NO_QUALIFICATION"
    ):
        raise PositionBalancedHoldCompareError("comparison identity differs")
    boundary = _mapping(
        unsigned.get("qualification_boundary"), "qualification_boundary"
    )
    if (
        boundary.get("controller_palette_evidence_passed") is not False
        or boundary.get("qualified_colour_count") != 0
        or boundary.get("qualified_gray_levels") != 0
        or boundary.get("qualified_brightness_levels") != 0
        or boundary.get("spatial_dithering_used") is not False
    ):
        raise PositionBalancedHoldCompareError(
            "comparison qualification boundary differs"
        )
    for name in (
        "same_profile_local_hold_review_draft",
        "commented_retains_active_directional_cross_lut_review_draft",
    ):
        draft = _mapping(unsigned.get(name), name)
        if (
            draft.get("direct_controller_palette_evidence_conversion_allowed")
            is not False
            or draft.get("controller_palette_evidence_passed") is not False
            or draft.get("qualified_level_count") != 0
        ):
            raise PositionBalancedHoldCompareError(
                f"{name} qualification boundary differs"
            )
    execution = _mapping(unsigned.get("execution_boundary"), "execution_boundary")
    if any(value is not False for value in execution.values()):
        raise PositionBalancedHoldCompareError("comparison execution boundary differs")
    return unsigned


def export_position_balanced_hold_comparison(
    value: Mapping[str, Any], path: str | Path
) -> Path:
    """Write verified review JSON with exclusive-create semantics."""

    verify_position_balanced_hold_comparison(value)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        ).encode("utf-8")
        + b"\n"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(output, flags, 0o600)
    except FileExistsError as error:
        raise PositionBalancedHoldCompareError("output already exists") from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return output


__all__ = [
    "COMPARISON_KIND",
    "DEFAULT_REVIEW_THRESHOLDS",
    "FROZEN_SNAPSHOTS",
    "HOLD_ANALYSIS_KIND",
    "IDENTITY_CONTRACT_KIND",
    "PROBE_SPEC",
    "PositionBalancedHoldCompareError",
    "compare_position_balanced_hold",
    "export_position_balanced_hold_comparison",
    "seal_position_balanced_hold_identity_contract",
    "verify_position_balanced_hold_comparison",
]
