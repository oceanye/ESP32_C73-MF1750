#!/usr/bin/env python3
"""Offline 48MP analyzer for the position-balanced LUMA/GRAY V3 grid.

The analyzer consumes a *completed* G3 or G4 action, its sealed camera
sidecar, and the exact JPEG named by that sidecar.  It never opens a camera,
relay, serial port, network socket, or display.  Every one of the 128 uniform
cells is sampled after a dedicated dual-controller 8x8 homography fit.  Lab
normalisation and all recipe screening remain controller-local.

The generated observation document is accepted by
``mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_observation``.
All results are coarse camera-relative review candidates.  This module can
never qualify a colour, neutral gray, brightness level, or production LUT.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
from typing import Any, Mapping, Sequence

import cv2
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_camera_capture_evidence as capture_evidence  # noqa: E402
from tools import mf1750_redpink_v2_grid_photo_analyzer as grid  # noqa: E402
from tools import (  # noqa: E402
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_observation as observation,
)
from tools import (  # noqa: E402
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_once as runner,
)
from tools import (  # noqa: E402
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_pack as pack,
)
from tools import mf1750_stable_code0_luma_latin_v3_once as latin_runner  # noqa: E402
from tools import mf1750_stable_code0_luma_latin_v3_pack as latin_pack  # noqa: E402


class PhotoAnalysisError(RuntimeError):
    """Raised when immutable evidence or camera-relative geometry is invalid."""


SCHEMA_VERSION = 1
KIND = "mf1750-luma-gray-mechanism-position-balanced-v3-photo-analysis"
REPEAT_KIND = f"{KIND}-g3-g4-repeat-comparison"
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
CONTROLLERS = ("CS1", "CS2")
CONTROLLER_WIDTH = 512
LOGICAL_WIDTH = 1024
LOGICAL_HEIGHT = 600
RECTIFICATION_SCALE = 2
INNER_CROP_FRACTION = 0.60
WHITE_BAND_INSET = 2
WHITE_BAND_OUTSET = 6
EDGE_INSET_NEAR = 3
EDGE_INSET_FAR = 7

QUALITY_THRESHOLDS = {
    "minimum_geometry_assignments": 48,
    "minimum_geometry_assignments_per_controller": 24,
    "minimum_geometry_inlier_fraction": 0.90,
    "maximum_geometry_rmse_px": 3.0,
    "maximum_geometry_p95_px": 4.0,
    "minimum_projected_cell_side_px": 20.0,
    "minimum_separator_white_l_star": 20.0,
    "maximum_separator_white_l_star": 95.0,
    "maximum_all_channels_low_clip_fraction": 0.02,
    "maximum_any_channel_high_clip_fraction": 0.005,
    "maximum_center_rgb_mad": 6.0,
    "stripe_present_dark_delta_l_star": -4.0,
    "stripe_present_de76_excess": 2.0,
    "stripe_uncertain_dark_delta_l_star": -2.5,
    "stripe_uncertain_de76_excess": 1.0,
    "maximum_repeat_recipe_median_delta_l_star": 2.0,
    "maximum_repeat_centered_cell_delta_l_star_p95": 3.0,
}


@dataclass
class _Geometry:
    homography: np.ndarray
    rectangles: list[Any]
    assignments: list[dict[str, Any]]
    errors: np.ndarray
    inliers: np.ndarray
    method: str
    saturation_threshold: int | None
    edge_colour_space: str | None
    edge_canny_thresholds: tuple[int, int] | None


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    body = deepcopy(dict(value))
    body["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": _sha(_canonical(body)),
    }
    return body


def _write_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    payload = (
        json.dumps(
            value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
        ).encode("utf-8")
        + b"\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise PhotoAnalysisError(f"refusing to overwrite output: {path}") from exc
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _read_stable(path: Path, *, label: str) -> bytes:
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise PhotoAnalysisError(f"{label} must be a regular non-symlink file")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise PhotoAnalysisError(f"cannot read {label}: {path}") from exc
    before_id = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_id = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_id != after_id or len(payload) != after.st_size:
        raise PhotoAnalysisError(f"{label} changed while read")
    return payload


def _relative_or_absolute(path: Path) -> str:
    resolved = path.resolve()
    return (
        resolved.relative_to(REPO_ROOT).as_posix()
        if resolved.is_relative_to(REPO_ROOT)
        else str(resolved)
    )


def _resolve_sidecar_path(sidecar_path: Path, value: Any, *, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise PhotoAnalysisError(f"{label} path is missing")
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = sidecar_path.parent / candidate
    return candidate.resolve()


def _camera_lock(sidecar: Mapping[str, Any]) -> dict[str, Any]:
    camera = sidecar.get("camera")
    if not isinstance(camera, Mapping):
        raise PhotoAnalysisError("capture camera record is missing")
    instance = str(camera.get("instance_id", "")).casefold()
    if "vid_32e4&pid_4801" not in instance or "vid_1bcf&pid_0b15" in instance:
        raise PhotoAnalysisError("capture is not the 48MP VID_32E4:PID_4801 camera")
    if camera.get("camera_id") != capture_evidence.TARGET_CAMERA_FRIENDLY_NAME:
        raise PhotoAnalysisError("capture camera friendly name differs")
    if str(camera.get("backend", "")).casefold() != "dshow":
        raise PhotoAnalysisError("capture backend is not DirectShow")
    requested = camera.get("requested_settings")
    before = camera.get("effective_settings_before_frame")
    after = camera.get("effective_settings_after_frame")
    if not all(isinstance(item, Mapping) for item in (requested, before, after)):
        raise PhotoAnalysisError("camera setting evidence is incomplete")
    manual = capture_evidence.LOCKED_RETAINED_MANUAL_CONTROLS
    manual_gate = all(requested.get(key) == value for key, value in manual.items())
    value_fields = capture_evidence.LOCKED_RETAINED_VALUE_FIELDS
    value_gate = all(
        isinstance(requested.get(key), (int, float))
        and not isinstance(requested.get(key), bool)
        and math.isfinite(float(requested[key]))
        for key in value_fields
    )
    if not manual_gate or not value_gate:
        raise PhotoAnalysisError("capture did not freeze focus/exposure/white balance")
    set_results = camera.get("set_results")
    if not isinstance(set_results, Mapping) or not set_results:
        raise PhotoAnalysisError("capture has no camera setting-write evidence")
    required_writes = {key for key, value in requested.items() if value is not None}
    if any(set_results.get(key) is not True for key in required_writes):
        raise PhotoAnalysisError(
            "one or more requested camera settings were not written"
        )
    coverage = sidecar.get("coverage")
    if (
        not isinstance(coverage, Mapping)
        or coverage.get("scope") != capture_evidence.COVERAGE_FULL
        or coverage.get("full_panel_visible") is not True
        or coverage.get("full_panel_uncropped") is not True
    ):
        raise PhotoAnalysisError("capture does not show the complete panel")
    return {
        "camera_id": camera["camera_id"],
        "camera_instance_id": camera["instance_id"],
        "camera_usb_identity": "VID_32E4:PID_4801",
        "camera_index": camera["index"],
        "backend": camera["backend"],
        "requested_settings": deepcopy(dict(requested)),
        "effective_settings_before_frame": deepcopy(dict(before)),
        "effective_settings_after_frame": deepcopy(dict(after)),
        "setting_write_results": deepcopy(dict(set_results)),
        "manual_focus_exposure_white_balance_gate": True,
        "mount_id": coverage["mount_id"],
        "full_panel_visible": True,
    }


def _validate_capture_binding(
    photo_path: Path, sidecar_path: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    try:
        sidecar = capture_evidence.validate_capture_evidence(sidecar_path)
    except (OSError, ValueError, RuntimeError) as exc:
        raise PhotoAnalysisError(f"capture sidecar validation failed: {exc}") from exc
    if sidecar.get("capture_binding") != capture_evidence.BINDING_LIVE:
        raise PhotoAnalysisError(
            "formal mechanism scan requires live-synchronized capture"
        )
    ordinal = sidecar.get("ordinal")
    if ordinal not in (3, 4):
        raise PhotoAnalysisError("capture must bind G3 or optional G4")
    expected_action = pack.build_report()["actions"][ordinal - 1]
    expected = {
        "campaign_id": pack.CAMPAIGN_ID,
        "test_id": pack.TEST_ID,
        "contract_id": pack.build_report()["contract_id"],
        "firmware_sha256": pack.ARTIFACTS["bin_sha256"],
        "ordinal": ordinal,
        "action_id": expected_action["action_id"],
        "descriptor_id": expected_action["descriptor_id"],
        "role": expected_action["role"],
        "frame_sha256": expected_action["frame"]["sha256"],
    }
    mismatches = [key for key, wanted in expected.items() if sidecar.get(key) != wanted]
    if mismatches:
        raise PhotoAnalysisError(f"capture V3 identity differs: {mismatches!r}")
    sidecar_photo = sidecar.get("photo")
    sidecar_action = sidecar.get("action_result")
    if not isinstance(sidecar_photo, Mapping) or not isinstance(
        sidecar_action, Mapping
    ):
        raise PhotoAnalysisError("capture photo/action binding is missing")
    if (
        _resolve_sidecar_path(
            sidecar_path, sidecar_photo.get("path"), label="capture photo"
        )
        != photo_path.resolve()
    ):
        raise PhotoAnalysisError("requested JPEG differs from capture sidecar")
    action_path = _resolve_sidecar_path(
        sidecar_path, sidecar_action.get("path"), label="capture action"
    )
    try:
        terminal = runner.validate_terminal_evidence(action_path)
    except (OSError, ValueError, RuntimeError) as exc:
        raise PhotoAnalysisError(f"terminal action validation failed: {exc}") from exc
    if terminal.get("ordinal") != ordinal:
        raise PhotoAnalysisError("terminal action ordinal differs from capture")
    action_payload = _read_stable(action_path, label="terminal action")
    if (
        sidecar_action.get("bytes") != len(action_payload)
        or sidecar_action.get("file_sha256") != _sha(action_payload)
        or sidecar_action.get("canonical_integrity_sha256")
        != terminal["canonical_integrity_sha256"]
    ):
        raise PhotoAnalysisError("terminal action byte/hash binding differs")
    photo_payload = _read_stable(photo_path, label="bound JPEG")
    if sidecar_photo.get("bytes") != len(photo_payload) or sidecar_photo.get(
        "sha256"
    ) != _sha(photo_payload):
        raise PhotoAnalysisError("JPEG byte/hash binding differs")
    sidecar_payload = _read_stable(sidecar_path, label="capture sidecar")
    evidence = {
        "action": {
            **terminal,
            "path": _relative_or_absolute(action_path),
            "bytes": len(action_payload),
            "file_sha256": _sha(action_payload),
        },
        "capture_sidecar": {
            "path": _relative_or_absolute(sidecar_path),
            "bytes": len(sidecar_payload),
            "file_sha256": _sha(sidecar_payload),
            "canonical_integrity_sha256": sidecar["integrity"]["sha256"],
            "capture_id": sidecar["capture_id"],
        },
        "photo": {
            "path": _relative_or_absolute(photo_path),
            "bytes": len(photo_payload),
            "file_sha256": _sha(photo_payload),
        },
    }
    return dict(sidecar), evidence, _camera_lock(sidecar), action_path


def _logical_center(controller: int, row: int, column: int) -> tuple[float, float]:
    return (
        controller * CONTROLLER_WIDTH
        + pack.GRID_X0
        + column * (pack.CELL_WIDTH + pack.GAP_X)
        + pack.CELL_WIDTH / 2.0,
        pack.GRID_Y0 + row * (pack.CELL_HEIGHT + pack.GAP_Y) + pack.CELL_HEIGHT / 2.0,
    )


def _cell_bounds(controller: int, row: int, column: int) -> tuple[int, int, int, int]:
    x0 = (
        controller * CONTROLLER_WIDTH
        + pack.GRID_X0
        + column * (pack.CELL_WIDTH + pack.GAP_X)
    )
    y0 = pack.GRID_Y0 + row * (pack.CELL_HEIGHT + pack.GAP_Y)
    return x0, y0, x0 + pack.CELL_WIDTH, y0 + pack.CELL_HEIGHT


def _initial_correspondences(
    rectangles: list[Any], row_labels: list[int], side_labels: list[int]
) -> tuple[np.ndarray, np.ndarray]:
    groups = grid._row_side_members(  # noqa: SLF001
        rectangles, row_labels, side_labels
    )
    logical: list[tuple[float, float]] = []
    photo: list[tuple[float, float]] = []
    complete_groups = 0
    for row in range(8):
        for controller in range(2):
            indices = groups[(row, controller)]
            if len(indices) != 8:
                continue
            complete_groups += 1
            for column, rectangle_index in enumerate(indices):
                logical.append(_logical_center(controller, row, column))
                rectangle = rectangles[rectangle_index]
                photo.append((rectangle.center_x, rectangle.center_y))
    if len(logical) < 32 or complete_groups < 4:
        raise PhotoAnalysisError("too few complete row/controller groups")
    return np.float32(logical), np.float32(photo)


def _assign(rectangles: list[Any], homography: np.ndarray) -> list[dict[str, Any]]:
    inverse = np.linalg.inv(homography)
    photo = np.float32(
        [[[rectangle.center_x, rectangle.center_y] for rectangle in rectangles]]
    )
    logical = cv2.perspectiveTransform(photo, inverse)[0]
    selected: dict[tuple[int, int, int], dict[str, Any]] = {}
    for rectangle_index, (logical_x, logical_y) in enumerate(logical):
        controller = int(logical_x >= CONTROLLER_WIDTH)
        local_x = float(logical_x - controller * CONTROLLER_WIDTH)
        column = int(
            round(
                (local_x - (pack.GRID_X0 + pack.CELL_WIDTH / 2.0))
                / (pack.CELL_WIDTH + pack.GAP_X)
            )
        )
        row = int(
            round(
                (float(logical_y) - (pack.GRID_Y0 + pack.CELL_HEIGHT / 2.0))
                / (pack.CELL_HEIGHT + pack.GAP_Y)
            )
        )
        if controller not in (0, 1) or row not in range(8) or column not in range(8):
            continue
        expected = np.float32([[_logical_center(controller, row, column)]])
        projected = cv2.perspectiveTransform(expected, homography)[0, 0]
        rectangle = rectangles[rectangle_index]
        error = float(
            np.linalg.norm(
                projected - np.float32([rectangle.center_x, rectangle.center_y])
            )
        )
        if error > max(8.0, 0.28 * min(rectangle.width, rectangle.height)):
            continue
        key = (controller, row, column)
        record = {
            "rectangle_index": rectangle_index,
            "controller": controller,
            "row": row,
            "column": column,
            "photo_center": [rectangle.center_x, rectangle.center_y],
            "reprojection_error_px": error,
        }
        if key not in selected or error < selected[key]["reprojection_error_px"]:
            selected[key] = record
    return sorted(
        selected.values(),
        key=lambda item: (item["controller"], item["row"], item["column"]),
    )


def _refine(
    rectangles: list[Any], homography: np.ndarray
) -> tuple[np.ndarray, list[dict[str, Any]], np.ndarray, np.ndarray]:
    assignments: list[dict[str, Any]] = []
    inliers = np.zeros(0, dtype=bool)
    for _ in range(3):
        assignments = _assign(rectangles, homography)
        if len(assignments) < QUALITY_THRESHOLDS["minimum_geometry_assignments"]:
            raise PhotoAnalysisError("too few unique V3 grid assignments")
        logical = np.float32(
            [
                _logical_center(item["controller"], item["row"], item["column"])
                for item in assignments
            ]
        )
        photo = np.float32([item["photo_center"] for item in assignments])
        try:
            homography, inliers = grid._fit_homography(logical, photo)  # noqa: SLF001
        except (grid.GridPhotoAnalysisError, cv2.error) as exc:
            raise PhotoAnalysisError(f"V3 homography refinement failed: {exc}") from exc
    projected = cv2.perspectiveTransform(logical[None, :, :], homography)[0]
    return homography, assignments, np.linalg.norm(projected - photo, axis=1), inliers


def _geometry_attempt(
    image: np.ndarray,
    *,
    saturation_threshold: int | None = None,
    edge_config: tuple[str, tuple[int, int]] | None = None,
) -> _Geometry:
    if edge_config is None:
        assert saturation_threshold is not None
        rectangles = grid._detect_rectangles(  # noqa: SLF001
            image, saturation_threshold
        )
        row_centers, row_labels = grid._cluster_rows(rectangles)  # noqa: SLF001
        method = "hsv-saturation-contours-v1"
        colour_space = None
        canny = None
    else:
        colour_space, canny = edge_config
        rectangles = grid._detect_edge_rectangles(  # noqa: SLF001
            image, canny, colour_space
        )
        row_centers, row_labels = grid._cluster_edge_rows(rectangles)  # noqa: SLF001
        method = "strict-canny-closed-cell-contours-v1"
    _ = row_centers
    _split, side_labels = grid._side_split(rectangles)  # noqa: SLF001
    logical, photo = _initial_correspondences(rectangles, row_labels, side_labels)
    try:
        homography, _initial_inliers = grid._fit_homography(  # noqa: SLF001
            logical, photo
        )
    except (grid.GridPhotoAnalysisError, cv2.error) as exc:
        raise PhotoAnalysisError(f"initial V3 homography failed: {exc}") from exc
    homography, assignments, errors, inliers = _refine(rectangles, homography)
    return _Geometry(
        homography=homography,
        rectangles=rectangles,
        assignments=assignments,
        errors=errors,
        inliers=inliers,
        method=method,
        saturation_threshold=saturation_threshold,
        edge_colour_space=colour_space,
        edge_canny_thresholds=canny,
    )


def _projected_minimum_cell_side(homography: np.ndarray) -> float:
    minimum = math.inf
    for controller in range(2):
        for row in range(8):
            for column in range(8):
                x0, y0, x1, y1 = _cell_bounds(controller, row, column)
                points = np.float32([[[x0, y0], [x1, y0], [x1, y1], [x0, y1]]])
                projected = cv2.perspectiveTransform(points, homography)[0]
                minimum = min(
                    minimum,
                    *(
                        float(
                            np.linalg.norm(
                                projected[(index + 1) % 4] - projected[index]
                            )
                        )
                        for index in range(4)
                    ),
                )
    return float(minimum)


def _geometry_quality(fit: _Geometry) -> dict[str, Any]:
    errors = fit.errors[fit.inliers]
    support = [
        sum(item["controller"] == controller for item in fit.assignments)
        for controller in range(2)
    ]
    coordinate_coverage = {
        f"CS{controller + 1}": {
            "rows": sorted(
                {
                    item["row"]
                    for item in fit.assignments
                    if item["controller"] == controller
                }
            ),
            "columns": sorted(
                {
                    item["column"]
                    for item in fit.assignments
                    if item["controller"] == controller
                }
            ),
        }
        for controller in range(2)
    }
    rmse = float(np.sqrt(np.mean(errors**2)))
    p95 = float(np.percentile(errors, 95))
    inlier_fraction = float(np.mean(fit.inliers))
    minimum_side = _projected_minimum_cell_side(fit.homography)
    pass_gate = (
        len(fit.assignments) >= QUALITY_THRESHOLDS["minimum_geometry_assignments"]
        and all(
            count >= QUALITY_THRESHOLDS["minimum_geometry_assignments_per_controller"]
            for count in support
        )
        and inlier_fraction >= QUALITY_THRESHOLDS["minimum_geometry_inlier_fraction"]
        and rmse <= QUALITY_THRESHOLDS["maximum_geometry_rmse_px"]
        and p95 <= QUALITY_THRESHOLDS["maximum_geometry_p95_px"]
        and minimum_side >= QUALITY_THRESHOLDS["minimum_projected_cell_side_px"]
        and all(
            value["rows"] == list(range(8)) and value["columns"] == list(range(8))
            for value in coordinate_coverage.values()
        )
    )
    return {
        "gate_pass": pass_gate,
        "method": fit.method,
        "saturation_threshold": fit.saturation_threshold,
        "edge_colour_space": fit.edge_colour_space,
        "edge_canny_thresholds": (
            list(fit.edge_canny_thresholds)
            if fit.edge_canny_thresholds is not None
            else None
        ),
        "detected_rectangle_count": len(fit.rectangles),
        "unique_assignment_count": len(fit.assignments),
        "support_by_controller": support,
        "coordinate_coverage": coordinate_coverage,
        "homography_inlier_fraction": inlier_fraction,
        "homography_inlier_rmse_px": rmse,
        "homography_inlier_p95_px": p95,
        "minimum_projected_cell_side_px": minimum_side,
        "homography_logical_to_photo": fit.homography.astype(float).tolist(),
        "undetected_cells_sampled_from_fitted_lattice": 128 - len(fit.assignments),
    }


def _fit_geometry(image: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    candidates: list[tuple[tuple[int, float, float], _Geometry, dict[str, Any]]] = []
    failures: list[str] = []
    for threshold in grid._THRESHOLDS:  # noqa: SLF001
        try:
            fit = _geometry_attempt(image, saturation_threshold=threshold)
            quality = _geometry_quality(fit)
        except (
            PhotoAnalysisError,
            grid.GridPhotoAnalysisError,
            cv2.error,
            np.linalg.LinAlgError,
        ) as exc:
            failures.append(f"S>{threshold}: {exc}")
            continue
        if quality["gate_pass"]:
            candidates.append(
                (
                    (
                        quality["unique_assignment_count"],
                        quality["homography_inlier_fraction"],
                        -quality["homography_inlier_rmse_px"],
                    ),
                    fit,
                    quality,
                )
            )
    if not candidates:
        for colour_space, canny in grid._EDGE_DETECTION_CONFIGS:  # noqa: SLF001
            try:
                fit = _geometry_attempt(image, edge_config=(colour_space, canny))
                quality = _geometry_quality(fit)
            except (
                PhotoAnalysisError,
                grid.GridPhotoAnalysisError,
                cv2.error,
                np.linalg.LinAlgError,
            ) as exc:
                failures.append(f"{colour_space}:{canny}: {exc}")
                continue
            if quality["gate_pass"]:
                candidates.append(
                    (
                        (
                            quality["unique_assignment_count"],
                            quality["homography_inlier_fraction"],
                            -quality["homography_inlier_rmse_px"],
                        ),
                        fit,
                        quality,
                    )
                )
    if not candidates:
        raise PhotoAnalysisError(
            "no V3-specific dual-grid geometry passed: " + "; ".join(failures)
        )
    candidates.sort(key=lambda item: item[0], reverse=True)
    _score, fit, quality = candidates[0]
    return fit.homography, quality


def _strict_sealed_json(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    payload = _read_stable(path, label=label)
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhotoAnalysisError(f"{label} is not UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise PhotoAnalysisError(f"{label} root differs")
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    if (
        not isinstance(integrity, Mapping)
        or integrity.get("algorithm") != INTEGRITY_ALGORITHM
        or integrity.get("sha256") != _sha(_canonical(body))
    ):
        raise PhotoAnalysisError(f"{label} integrity differs")
    return payload, value


def _bound_report_source(
    binding: Mapping[str, Any], *, label: str
) -> tuple[Path, bytes]:
    value = binding.get("path")
    if not isinstance(value, str) or not value:
        raise PhotoAnalysisError(f"{label} path is missing")
    path = Path(value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    path = path.resolve()
    payload = _read_stable(path, label=label)
    expected_sha = binding.get("file_sha256", binding.get("sha256"))
    if binding.get("bytes") != len(payload) or expected_sha != _sha(payload):
        raise PhotoAnalysisError(f"{label} file binding differs")
    return path, payload


def _reference_alignment_support(
    image: np.ndarray, homography: np.ndarray
) -> dict[str, Any]:
    """Require current-frame cell support before reusing a fixed-mount fit."""

    attempts: list[tuple[int, float, str, list[dict[str, Any]]]] = []
    configurations: list[tuple[str, Any]] = [
        ("saturation", threshold)
        for threshold in grid._THRESHOLDS  # noqa: SLF001
    ] + [
        ("edge", (colour_space, canny))
        for colour_space, canny in grid._EDGE_DETECTION_CONFIGS  # noqa: SLF001
    ]
    for method, config in configurations:
        try:
            if method == "saturation":
                rectangles = grid._detect_rectangles(image, config)  # noqa: SLF001
                label = f"hsv-saturation-contours-v1:S>{config}"
            else:
                colour_space, canny = config
                rectangles = grid._detect_edge_rectangles(  # noqa: SLF001
                    image, canny, colour_space
                )
                label = f"strict-canny:{colour_space}:{canny}"
            assignments = _assign(rectangles, homography)
        except (grid.GridPhotoAnalysisError, cv2.error, np.linalg.LinAlgError):
            continue
        if not assignments:
            continue
        errors = [float(item["reprojection_error_px"]) for item in assignments]
        attempts.append(
            (len(assignments), -float(np.percentile(errors, 95)), label, assignments)
        )
    if not attempts:
        raise PhotoAnalysisError(
            "reference homography has no current-frame cell support"
        )
    attempts.sort(key=lambda item: (item[0], item[1]), reverse=True)
    _count, _negative_p95, method, assignments = attempts[0]
    support = [
        sum(item["controller"] == controller for item in assignments)
        for controller in range(2)
    ]
    errors = [float(item["reprojection_error_px"]) for item in assignments]
    coverage = {
        f"CS{controller + 1}": {
            "rows": sorted(
                {
                    item["row"]
                    for item in assignments
                    if item["controller"] == controller
                }
            ),
            "columns": sorted(
                {
                    item["column"]
                    for item in assignments
                    if item["controller"] == controller
                }
            ),
        }
        for controller in range(2)
    }
    pass_gate = (
        len(assignments) >= 24
        and all(value >= 8 for value in support)
        and float(np.percentile(errors, 95)) <= 6.0
        and all(
            len(value["rows"]) >= 4 and len(value["columns"]) >= 6
            for value in coverage.values()
        )
    )
    if not pass_gate:
        raise PhotoAnalysisError(
            "reference homography current-frame support gate failed"
        )
    return {
        "gate_pass": True,
        "method": method,
        "unique_assignment_count": len(assignments),
        "support_by_controller": support,
        "coordinate_coverage": coverage,
        "reprojection_error_p95_px": float(np.percentile(errors, 95)),
        "reprojection_error_maximum_px": max(errors),
    }


def _geometry_from_latin_reference(
    image: np.ndarray,
    reference_report_path: Path,
    *,
    current_camera_lock: Mapping[str, Any],
) -> tuple[np.ndarray, dict[str, Any]]:
    """Reuse one exact Latin V3 full-panel fit on an unchanged camera mount."""

    reference_report_path = Path(reference_report_path).resolve()
    reference_payload, reference = _strict_sealed_json(
        reference_report_path, label="Latin V3 geometry reference"
    )
    expected = {
        "schema_version": 1,
        "kind": "mf1750-stable-code0-luma-latin-v3-camera-relative-photo-analysis",
        "campaign_id": latin_pack.CAMPAIGN_ID,
        "test_id": latin_pack.TEST_ID,
        "contract_id": latin_pack.build_report()["contract_id"],
        "stage": "L3",
        "hardware_accessed": False,
        "camera_accessed": False,
        "network_requests": 0,
    }
    mismatches = [
        key for key, wanted in expected.items() if reference.get(key) != wanted
    ]
    if mismatches:
        raise PhotoAnalysisError(f"Latin V3 reference identity differs: {mismatches!r}")
    source_photo = reference.get("source_photo")
    source_sidecar = reference.get("source_capture_sidecar")
    source_action = reference.get("source_terminal_evidence")
    if not all(
        isinstance(value, Mapping)
        for value in (source_photo, source_sidecar, source_action)
    ):
        raise PhotoAnalysisError("Latin V3 reference source bindings are missing")
    reference_photo_path, _reference_photo_payload = _bound_report_source(
        source_photo, label="Latin V3 reference photo"
    )
    reference_sidecar_path, _reference_sidecar_payload = _bound_report_source(
        source_sidecar, label="Latin V3 reference capture sidecar"
    )
    reference_action_path, _reference_action_payload = _bound_report_source(
        source_action, label="Latin V3 reference terminal action"
    )
    try:
        reference_sidecar = capture_evidence.validate_capture_evidence(
            reference_sidecar_path
        )
        reference_terminal = latin_runner.validate_terminal_evidence(
            reference_action_path
        )
    except (OSError, ValueError, RuntimeError) as exc:
        raise PhotoAnalysisError(
            f"Latin V3 reference deep validation failed: {exc}"
        ) from exc
    if reference_terminal.get("ordinal") != 3 or reference_sidecar.get("ordinal") != 3:
        raise PhotoAnalysisError("Latin V3 reference is not L3")
    reference_lock = _camera_lock(reference_sidecar)
    lock_fields = (
        "camera_id",
        "camera_instance_id",
        "camera_index",
        "backend",
        "requested_settings",
        "effective_settings_before_frame",
        "effective_settings_after_frame",
        "mount_id",
    )
    if any(reference_lock[key] != current_camera_lock[key] for key in lock_fields):
        raise PhotoAnalysisError("Latin V3 reference camera settings or mount differ")
    if source_photo.get("width") != int(image.shape[1]) or source_photo.get(
        "height"
    ) != int(image.shape[0]):
        raise PhotoAnalysisError("Latin V3 reference image dimensions differ")
    geometry = reference.get("geometry_quality")
    if not isinstance(geometry, Mapping):
        raise PhotoAnalysisError("Latin V3 reference geometry is missing")
    homography = np.asarray(
        geometry.get("homography_logical_to_photo"), dtype=np.float64
    )
    if (
        homography.shape != (3, 3)
        or not np.all(np.isfinite(homography))
        or abs(float(np.linalg.det(homography))) < 1e-12
        or geometry.get("geometry_origin") != "INDEPENDENT_DUAL_8X8_FIT"
        or geometry.get("unique_cell_contour_support") != 128
        or geometry.get("support_by_controller") != [64, 64]
        or float(geometry.get("homography_inlier_rmse_px", math.inf)) > 2.0
        or float(geometry.get("homography_inlier_p95_px", math.inf)) > 3.0
    ):
        raise PhotoAnalysisError("Latin V3 reference geometry quality differs")
    alignment = _reference_alignment_support(image, homography)
    minimum_side = _projected_minimum_cell_side(homography)
    if minimum_side < QUALITY_THRESHOLDS["minimum_projected_cell_side_px"]:
        raise PhotoAnalysisError("referenced V3 cells are too small")
    return homography, {
        "gate_pass": True,
        "method": "SEALED_LATIN_V3_FIXED_MOUNT_FULL_PANEL_REFERENCE",
        "reference_report": {
            "path": _relative_or_absolute(reference_report_path),
            "bytes": len(reference_payload),
            "file_sha256": _sha(reference_payload),
            "canonical_integrity_sha256": reference["integrity"]["sha256"],
        },
        "reference_photo_path": _relative_or_absolute(reference_photo_path),
        "reference_geometry_origin": geometry["geometry_origin"],
        "homography_logical_to_photo": homography.astype(float).tolist(),
        "minimum_projected_cell_side_px": minimum_side,
        "current_frame_alignment_support": alignment,
        "undetected_cells_sampled_from_fitted_lattice": 128
        - alignment["unique_assignment_count"],
    }


def _rectify(
    image: np.ndarray, homography: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    scale = float(RECTIFICATION_SCALE)
    scaled = np.array([[scale, 0.0, 0.0], [0.0, scale, 0.0], [0.0, 0.0, 1.0]])
    transform = scaled @ np.linalg.inv(homography)
    size = (LOGICAL_WIDTH * RECTIFICATION_SCALE, LOGICAL_HEIGHT * RECTIFICATION_SCALE)
    rectified = cv2.warpPerspective(
        image,
        transform,
        size,
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )
    source_valid = np.full(image.shape[:2], 255, dtype=np.uint8)
    validity = cv2.warpPerspective(
        source_valid,
        transform,
        size,
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    return rectified, validity


def _box_pixels_rgb(
    rectified: np.ndarray,
    validity: np.ndarray,
    bounds: tuple[float, float, float, float],
    *,
    label: str,
) -> np.ndarray:
    x0, y0, x1, y1 = bounds
    scale = RECTIFICATION_SCALE
    ix0, iy0 = int(round(x0 * scale)), int(round(y0 * scale))
    ix1, iy1 = int(round(x1 * scale)), int(round(y1 * scale))
    patch = rectified[iy0:iy1, ix0:ix1]
    valid = validity[iy0:iy1, ix0:ix1] > 0
    if patch.size == 0 or valid.size == 0:
        raise PhotoAnalysisError(f"{label} sampling box is empty")
    pixels = patch[valid][:, ::-1].astype(np.float64)
    if len(pixels) < 32:
        raise PhotoAnalysisError(f"{label} has too few valid pixels")
    return pixels


def _robust_rgb(pixels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    median = np.median(pixels, axis=0)
    return median, np.median(np.abs(pixels - median), axis=0)


def _lab(rgb: np.ndarray) -> np.ndarray:
    return grid._lab_from_rgb(rgb)  # noqa: SLF001 - shared camera conversion


def classify_edge_stripe(*, delta_l_star: float, de76_excess: float) -> str:
    """Return PRESENT/UNCERTAIN/CLEAR for one dark edge-local stripe."""

    if (
        delta_l_star <= QUALITY_THRESHOLDS["stripe_present_dark_delta_l_star"]
        and de76_excess >= QUALITY_THRESHOLDS["stripe_present_de76_excess"]
    ):
        return "PRESENT"
    if (
        delta_l_star <= QUALITY_THRESHOLDS["stripe_uncertain_dark_delta_l_star"]
        and de76_excess >= QUALITY_THRESHOLDS["stripe_uncertain_de76_excess"]
    ):
        return "UNCERTAIN"
    return "CLEAR"


def _sample_cell(
    rectified: np.ndarray,
    validity: np.ndarray,
    *,
    controller: int,
    row: int,
    column: int,
) -> dict[str, Any]:
    x0, y0, x1, y1 = _cell_bounds(controller, row, column)
    margin_x = pack.CELL_WIDTH * (1.0 - INNER_CROP_FRACTION) / 2.0
    margin_y = pack.CELL_HEIGHT * (1.0 - INNER_CROP_FRACTION) / 2.0
    center_pixels = _box_pixels_rgb(
        rectified,
        validity,
        (x0 + margin_x, y0 + margin_y, x1 - margin_x, y1 - margin_y),
        label=f"CS{controller + 1} R{row} C{column} center",
    )
    center_rgb, center_mad = _robust_rgb(center_pixels)
    separator_bounds = (
        (x0 + margin_x, y0 - WHITE_BAND_OUTSET, x1 - margin_x, y0 - WHITE_BAND_INSET),
        (x0 + margin_x, y1 + WHITE_BAND_INSET, x1 - margin_x, y1 + WHITE_BAND_OUTSET),
        (x0 - WHITE_BAND_OUTSET, y0 + margin_y, x0 - WHITE_BAND_INSET, y1 - margin_y),
        (x1 + WHITE_BAND_INSET, y0 + margin_y, x1 + WHITE_BAND_OUTSET, y1 - margin_y),
    )
    separator_pixels = np.concatenate(
        [
            _box_pixels_rgb(
                rectified,
                validity,
                bounds,
                label=f"CS{controller + 1} R{row} C{column} separator {index}",
            )
            for index, bounds in enumerate(separator_bounds)
        ]
    )
    separator_rgb, separator_mad = _robust_rgb(separator_pixels)
    edge_bounds = {
        "top": (x0 + 8, y0 + EDGE_INSET_NEAR, x1 - 8, y0 + EDGE_INSET_FAR),
        "bottom": (x0 + 8, y1 - EDGE_INSET_FAR, x1 - 8, y1 - EDGE_INSET_NEAR),
        "left": (x0 + EDGE_INSET_NEAR, y0 + 10, x0 + EDGE_INSET_FAR, y1 - 10),
        "right": (x1 - EDGE_INSET_FAR, y0 + 10, x1 - EDGE_INSET_NEAR, y1 - 10),
    }
    center_lab = _lab(center_rgb)
    edge_labs = {
        name: _lab(
            _robust_rgb(
                _box_pixels_rgb(
                    rectified,
                    validity,
                    bounds,
                    label=f"CS{controller + 1} R{row} C{column} {name} edge",
                )
            )[0]
        )
        for name, bounds in edge_bounds.items()
    }
    edge_de = {
        name: float(np.linalg.norm(value - center_lab))
        for name, value in edge_labs.items()
    }
    edge_states: dict[str, str] = {}
    for name, edge_lab in edge_labs.items():
        other = [value for key, value in edge_de.items() if key != name]
        edge_states[name] = classify_edge_stripe(
            delta_l_star=float(edge_lab[0] - center_lab[0]),
            de76_excess=edge_de[name] - float(np.median(other)),
        )
    return {
        "controller_index": controller,
        "row": row,
        "column": column,
        "center_rgb": center_rgb,
        "center_rgb_mad": center_mad,
        "center_lab": center_lab,
        "separator_rgb": separator_rgb,
        "separator_rgb_mad": separator_mad,
        "separator_lab": _lab(separator_rgb),
        "edge_states": edge_states,
        "edge_de76_to_center": edge_de,
        "center_all_channels_low_clip_fraction": float(
            np.mean(np.all(center_pixels <= 5.0, axis=1))
        ),
        "center_any_channel_high_clip_fraction": float(
            np.mean(np.any(center_pixels >= 250.0, axis=1))
        ),
    }


def _normalise_controller(cells: list[dict[str, Any]]) -> dict[str, Any]:
    separator_labs = np.array([item["separator_lab"] for item in cells])
    controller_white = np.median(separator_labs, axis=0)
    normalized = []
    for item in cells:
        relative = item["center_lab"] - item["separator_lab"] + controller_white
        relative[0] = float(np.clip(relative[0], 0.0, 100.0))
        normalized.append({**item, "normalized_lab": relative})
    return {
        "controller_separator_white_lab": controller_white,
        "separator_l_star_range": float(np.ptp(separator_labs[:, 0])),
        "cells": normalized,
    }


def _measurement_index() -> dict[tuple[str, int, int], dict[str, Any]]:
    return {
        (item["controller"], item["row"], item["column"]): item
        for item in observation.roi_manifest()["samples"]
    }


def _observation_document(
    *,
    cells: list[dict[str, Any]],
    evidence: Mapping[str, Any],
    stage: str,
) -> dict[str, Any]:
    sample_index = _measurement_index()
    measurements = []
    for item in cells:
        controller = f"CS{int(item['controller_index']) + 1}"
        identity = sample_index[(controller, int(item["row"]), int(item["column"]))]
        states = item["edge_states"]
        measurements.append(
            {
                **identity,
                "lab": np.asarray(item["normalized_lab"]).astype(float).tolist(),
                "bottom_edge_clean": states["bottom"] == "CLEAR",
                "horizontal_stripe_absent": states["top"]
                == states["bottom"]
                == "CLEAR",
                "vertical_stripe_absent": states["left"] == states["right"] == "CLEAR",
                "roi_visible": True,
                "operator_note": (
                    "automatic 48MP controller-local camera-relative sample; "
                    f"edge states={states}"
                ),
            }
        )
    measurements.sort(key=lambda item: item["sample_id"])
    manifest = observation.roi_manifest()
    action = evidence["action"]
    sidecar = evidence["capture_sidecar"]
    photo = evidence["photo"]
    document = {
        "schema_version": 1,
        "kind": observation.KIND,
        "state": "AUTOMATED_CAMERA_RELATIVE_OBSERVATION",
        "offline_only": True,
        "action_evidence": deepcopy(dict(action)),
        "capture": {
            "path": photo["path"],
            "bytes": photo["bytes"],
            "file_sha256": photo["file_sha256"],
        },
        "capture_sidecar": deepcopy(dict(sidecar)),
        "roi_manifest_sha256": _sha(_canonical(manifest)),
        "measurements": measurements,
        "thresholds": {
            "max_position_delta_e76": observation.MAX_POSITION_DELTA_E76,
            "max_g3_g4_repeat_delta_e76": observation.MAX_REPEAT_DELTA_E76,
            "max_neutral_chroma": observation.MAX_NEUTRAL_CHROMA,
            "min_mechanism_delta_l": observation.MIN_MECHANISM_DELTA_L,
        },
        "required_defect_gates": [
            "bottom_edge_clean",
            "horizontal_stripe_absent",
            "vertical_stripe_absent",
        ],
        "stage": stage,
        "controller_policy": "CS1_AND_CS2_EVALUATED_SEPARATELY",
        "spatial_dither": False,
        "qualified_colour_count": 0,
        "qualified_gray_levels": 0,
        "qualified_brightness_levels": 0,
        "automatic_colour_qualification": False,
    }
    return _seal(document)


def _delta_e(left: Sequence[float], right: Sequence[float]) -> float:
    return math.sqrt(
        sum((float(a) - float(b)) ** 2 for a, b in zip(left, right, strict=True))
    )


def screen_observation(document: Mapping[str, Any]) -> dict[str, Any]:
    """Screen 16 recipes x four positions independently on each controller."""

    values = document.get("measurements")
    if not isinstance(values, list) or len(values) != 128:
        raise PhotoAnalysisError("observation must contain exactly 128 measurements")
    indexed = {
        item.get("sample_id"): item for item in values if isinstance(item, Mapping)
    }
    expected = {item["sample_id"] for item in observation.roi_manifest()["samples"]}
    if set(indexed) != expected:
        raise PhotoAnalysisError("observation sample identity differs")
    recipe_results = []
    for controller in CONTROLLERS:
        for recipe in range(16):
            cells = [
                indexed[f"{controller}-R{recipe:02d}-P{repeat}"] for repeat in range(4)
            ]
            labs = [list(map(float, cell["lab"])) for cell in cells]
            mean_lab = [sum(lab[channel] for lab in labs) / 4.0 for channel in range(3)]
            maximum_position_de = max(
                _delta_e(left, right) for left in labs for right in labs
            )
            defects_clear = all(
                cell[key] is True
                for cell in cells
                for key in (
                    "bottom_edge_clean",
                    "horizontal_stripe_absent",
                    "vertical_stripe_absent",
                    "roi_visible",
                )
            )
            recipe_results.append(
                {
                    "controller": controller,
                    "recipe": recipe,
                    "sample_ids": [cell["sample_id"] for cell in cells],
                    "mean_camera_relative_lab": mean_lab,
                    "mean_chroma": math.hypot(mean_lab[1], mean_lab[2]),
                    "maximum_position_delta_e76": maximum_position_de,
                    "position_gate_pass": maximum_position_de
                    <= observation.MAX_POSITION_DELTA_E76,
                    "edge_and_visibility_gates_pass": defects_clear,
                    "neutral_review_candidate": math.hypot(mean_lab[1], mean_lab[2])
                    <= observation.MAX_NEUTRAL_CHROMA,
                    "qualified_level": False,
                }
            )
    groups = []
    for controller in CONTROLLERS:
        for target_code, recipes in ((3, range(8)), (7, range(8, 16))):
            rows = [
                item
                for item in recipe_results
                if item["controller"] == controller and item["recipe"] in recipes
            ]
            l_values = [item["mean_camera_relative_lab"][0] for item in rows]
            span = max(l_values) - min(l_values)
            gate = (
                span >= observation.MIN_MECHANISM_DELTA_L
                and all(item["position_gate_pass"] for item in rows)
                and all(item["edge_and_visibility_gates_pass"] for item in rows)
            )
            groups.append(
                {
                    "controller": controller,
                    "target_code": target_code,
                    "recipes": list(recipes),
                    "camera_relative_l_star_span": span,
                    "coarse_lightness_mechanism_review_candidate": gate,
                    "absolute_gray_or_brightness_claimed": False,
                }
            )
    candidates = [
        {"controller": item["controller"], "target_code": item["target_code"]}
        for item in groups
        if item["coarse_lightness_mechanism_review_candidate"]
    ]
    return {
        "controller_policy": "CS1_AND_CS2_NEVER_POOLED",
        "recipes_per_controller": 16,
        "replicates_per_recipe": 4,
        "recipe_results": recipe_results,
        "target_groups": groups,
        "coarse_candidate_groups": candidates,
        "decision": (
            "COARSE_CONTROLLER_LOCAL_LIGHTNESS_REVIEW_CANDIDATE"
            if candidates
            else "REVIEW_NO_CONTROLLER_LOCAL_MECHANISM_CANDIDATE"
        ),
        "qualified_colour_count": 0,
        "qualified_gray_levels": 0,
        "qualified_brightness_levels": 0,
    }


def analyze(
    photo_path: Path,
    capture_sidecar_path: Path,
    *,
    geometry_reference_report_path: Path | None = None,
) -> dict[str, Any]:
    """Analyze one sealed G3/G4 frame without accessing live hardware."""

    photo_path = Path(photo_path).resolve()
    capture_sidecar_path = Path(capture_sidecar_path).resolve()
    sidecar, evidence, camera_lock, _action_path = _validate_capture_binding(
        photo_path, capture_sidecar_path
    )
    photo_payload = _read_stable(photo_path, label="bound JPEG")
    image = cv2.imdecode(np.frombuffer(photo_payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        raise PhotoAnalysisError("bound JPEG is not a decodable colour image")
    if geometry_reference_report_path is None:
        homography, geometry = _fit_geometry(image)
    else:
        homography, geometry = _geometry_from_latin_reference(
            image,
            Path(geometry_reference_report_path),
            current_camera_lock=camera_lock,
        )
    rectified, validity = _rectify(image, homography)
    all_cells: list[dict[str, Any]] = []
    normalization: dict[str, Any] = {}
    for controller in range(2):
        raw = [
            _sample_cell(
                rectified,
                validity,
                controller=controller,
                row=row,
                column=column,
            )
            for row in range(8)
            for column in range(8)
        ]
        normalized = _normalise_controller(raw)
        all_cells.extend(normalized["cells"])
        normalization[f"CS{controller + 1}"] = {
            "separator_white_median_camera_relative_lab": normalized[
                "controller_separator_white_lab"
            ]
            .astype(float)
            .tolist(),
            "separator_white_l_star_range": normalized["separator_l_star_range"],
            "cross_controller_pooling": False,
        }
    stage = f"G{sidecar['ordinal']}"
    document = _observation_document(cells=all_cells, evidence=evidence, stage=stage)
    screen = screen_observation(document)
    separator_l = [float(item["separator_lab"][0]) for item in all_cells]
    maximum_low_clip = max(
        float(item["center_all_channels_low_clip_fraction"]) for item in all_cells
    )
    maximum_high_clip = max(
        float(item["center_any_channel_high_clip_fraction"]) for item in all_cells
    )
    maximum_mad = max(float(np.max(item["center_rgb_mad"])) for item in all_cells)
    edge_counts = {
        edge: {
            state: sum(item["edge_states"][edge] == state for item in all_cells)
            for state in ("PRESENT", "UNCERTAIN", "CLEAR")
        }
        for edge in ("top", "bottom", "left", "right")
    }
    capture_quality = {
        "geometry_gate_pass": geometry["gate_pass"],
        "full_panel_visible": True,
        "manual_camera_lock_gate_pass": True,
        "exposure_gate_pass": (
            min(separator_l) >= QUALITY_THRESHOLDS["minimum_separator_white_l_star"]
            and max(separator_l) <= QUALITY_THRESHOLDS["maximum_separator_white_l_star"]
            and maximum_low_clip
            <= QUALITY_THRESHOLDS["maximum_all_channels_low_clip_fraction"]
            and maximum_high_clip
            <= QUALITY_THRESHOLDS["maximum_any_channel_high_clip_fraction"]
        ),
        "coarse_uniformity_gate_pass": maximum_mad
        <= QUALITY_THRESHOLDS["maximum_center_rgb_mad"],
        "minimum_separator_white_l_star": min(separator_l),
        "maximum_separator_white_l_star": max(separator_l),
        "maximum_center_all_channels_low_clip_fraction": maximum_low_clip,
        "maximum_center_any_channel_high_clip_fraction": maximum_high_clip,
        "maximum_center_rgb_mad": maximum_mad,
        "edge_state_counts": edge_counts,
    }
    quality_pass = all(
        capture_quality[key] is True
        for key in (
            "geometry_gate_pass",
            "full_panel_visible",
            "manual_camera_lock_gate_pass",
            "exposure_gate_pass",
            "coarse_uniformity_gate_pass",
        )
    )
    any_edge_problem = any(
        edge_counts[edge][state] > 0
        for edge in edge_counts
        for state in ("PRESENT", "UNCERTAIN")
    )
    if not quality_pass or any_edge_problem:
        decision = "REVIEW_CAPTURE_OR_CELL_EDGE_QUALITY"
    else:
        decision = screen["decision"]
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "campaign_id": pack.CAMPAIGN_ID,
        "test_id": pack.TEST_ID,
        "contract_id": pack.build_report()["contract_id"],
        "stage": stage,
        "decision": decision,
        "source_evidence": evidence,
        "camera_lock": camera_lock,
        "geometry": geometry,
        "capture_quality": capture_quality,
        "controller_normalization": normalization,
        "observation_document": document,
        "controller_local_screen": screen,
        "method": {
            "camera": "48MP VID_32E4:PID_4801 only",
            "rectification_scale": RECTIFICATION_SCALE,
            "central_inset_fraction": (1.0 - INNER_CROP_FRACTION) / 2.0,
            "lab": "camera JPEG RGB interpreted as sRGB D65/2deg Lab",
            "illumination_normalization": (
                "four adjacent separator bands, recentered only to that "
                "controller's median separator white"
            ),
            "controllers_pooled": False,
            "spatial_dither": False,
        },
        "quality_thresholds": deepcopy(QUALITY_THRESHOLDS),
        "qualification_boundary": {
            "camera_relative_coarse_screen_only": True,
            "absolute_colour_claimed": False,
            "cross_controller_equivalence_claimed": False,
            "qualified_colour_count": 0,
            "qualified_gray_levels": 0,
            "qualified_brightness_levels": 0,
            "repeat_required": stage == "G3",
        },
        "hardware_accessed": False,
        "camera_accessed": False,
        "network_requests": 0,
    }
    return _seal(report)


def _read_report(path: Path, *, expected_stage: str) -> tuple[bytes, dict[str, Any]]:
    payload = _read_stable(path, label=f"{expected_stage} analysis report")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhotoAnalysisError(f"{expected_stage} analysis is not JSON") from exc
    if not isinstance(value, dict):
        raise PhotoAnalysisError(f"{expected_stage} analysis root differs")
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    if (
        not isinstance(integrity, Mapping)
        or integrity.get("algorithm") != INTEGRITY_ALGORITHM
        or integrity.get("sha256") != _sha(_canonical(body))
    ):
        raise PhotoAnalysisError(f"{expected_stage} analysis integrity differs")
    expected = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "campaign_id": pack.CAMPAIGN_ID,
        "test_id": pack.TEST_ID,
        "contract_id": pack.build_report()["contract_id"],
        "stage": expected_stage,
        "hardware_accessed": False,
        "camera_accessed": False,
        "network_requests": 0,
    }
    mismatches = [key for key, wanted in expected.items() if value.get(key) != wanted]
    if mismatches:
        raise PhotoAnalysisError(
            f"{expected_stage} analysis identity differs: {mismatches!r}"
        )
    resolved_sources: dict[str, Path] = {}
    for label in ("action", "capture_sidecar", "photo"):
        binding = value.get("source_evidence", {}).get(label)
        if not isinstance(binding, Mapping):
            raise PhotoAnalysisError(f"{expected_stage} {label} binding missing")
        source = Path(str(binding.get("path")))
        if not source.is_absolute():
            source = REPO_ROOT / source
        source_payload = _read_stable(
            source.resolve(), label=f"{expected_stage} {label}"
        )
        if binding.get("bytes") != len(source_payload) or binding.get(
            "file_sha256"
        ) != _sha(source_payload):
            raise PhotoAnalysisError(f"{expected_stage} {label} binding differs")
        resolved_sources[label] = source.resolve()
    _sidecar, derived_evidence, derived_lock, derived_action_path = (
        _validate_capture_binding(
            resolved_sources["photo"], resolved_sources["capture_sidecar"]
        )
    )
    if derived_action_path != resolved_sources["action"]:
        raise PhotoAnalysisError(
            f"{expected_stage} action path differs after revalidation"
        )
    if value.get("camera_lock") != derived_lock:
        raise PhotoAnalysisError(f"{expected_stage} camera lock differs from sidecar")
    for label in ("action", "capture_sidecar", "photo"):
        stored = value["source_evidence"][label]
        derived = derived_evidence[label]
        for key in ("bytes", "file_sha256"):
            if stored.get(key) != derived.get(key):
                raise PhotoAnalysisError(
                    f"{expected_stage} {label} deep binding differs"
                )
    screen = value.get("controller_local_screen")
    document = value.get("observation_document")
    if not isinstance(screen, Mapping) or not isinstance(document, Mapping):
        raise PhotoAnalysisError(f"{expected_stage} screen/observation missing")
    if len(document.get("measurements", [])) != 128:
        raise PhotoAnalysisError(f"{expected_stage} observation count differs")
    unsigned_document = deepcopy(dict(document))
    document_integrity = unsigned_document.pop("integrity", None)
    if (
        not isinstance(document_integrity, Mapping)
        or document_integrity.get("algorithm") != INTEGRITY_ALGORITHM
        or document_integrity.get("sha256") != _sha(_canonical(unsigned_document))
    ):
        raise PhotoAnalysisError(f"{expected_stage} observation integrity differs")
    wanted_ordinal = 3 if expected_stage == "G3" else 4
    if (
        document.get("stage") != expected_stage
        or document.get("action_evidence", {}).get("ordinal") != wanted_ordinal
    ):
        raise PhotoAnalysisError(f"{expected_stage} observation action differs")
    if dict(screen) != screen_observation(document):
        raise PhotoAnalysisError(f"{expected_stage} stored screen differs on recompute")
    return payload, value


def compare_repeat(g3_report_path: Path, g4_report_path: Path) -> dict[str, Any]:
    """Compare exact-settings G3/G4 results without pooling controllers."""

    g3_payload, g3 = _read_report(Path(g3_report_path), expected_stage="G3")
    g4_payload, g4 = _read_report(Path(g4_report_path), expected_stage="G4")
    lock_fields = (
        "camera_id",
        "camera_instance_id",
        "camera_index",
        "backend",
        "requested_settings",
        "effective_settings_before_frame",
        "effective_settings_after_frame",
        "mount_id",
    )
    exact_settings = all(
        g3["camera_lock"][key] == g4["camera_lock"][key] for key in lock_fields
    )
    if not exact_settings:
        raise PhotoAnalysisError("G3/G4 camera identity, settings, or mount differ")
    left = {
        item["sample_id"]: item for item in g3["observation_document"]["measurements"]
    }
    right = {
        item["sample_id"]: item for item in g4["observation_document"]["measurements"]
    }
    if set(left) != set(right) or len(left) != 128:
        raise PhotoAnalysisError("G3/G4 sample identity differs")
    controller_results = {}
    for controller in CONTROLLERS:
        sample_ids = sorted(sample for sample in left if sample.startswith(controller))
        l3_labs = np.array([left[sample]["lab"] for sample in sample_ids], dtype=float)
        l4_labs = np.array([right[sample]["lab"] for sample in sample_ids], dtype=float)
        l3_center = np.median(l3_labs, axis=0)
        l4_center = np.median(l4_labs, axis=0)
        centered_delta = (l4_labs - l4_center) - (l3_labs - l3_center)
        centered_abs_l = np.abs(centered_delta[:, 0])
        recipe_deltas = {}
        for recipe in range(16):
            ids = [f"{controller}-R{recipe:02d}-P{repeat}" for repeat in range(4)]
            l3_recipe = np.array([left[sample]["lab"] for sample in ids], dtype=float)
            l4_recipe = np.array([right[sample]["lab"] for sample in ids], dtype=float)
            l3_value = float(np.median(l3_recipe[:, 0] - l3_center[0]))
            l4_value = float(np.median(l4_recipe[:, 0] - l4_center[0]))
            recipe_deltas[str(recipe)] = {
                "g3_centered_median_l_star": l3_value,
                "g4_centered_median_l_star": l4_value,
                "absolute_delta_l_star": abs(l4_value - l3_value),
            }
        maximum_recipe_delta = max(
            item["absolute_delta_l_star"] for item in recipe_deltas.values()
        )
        p95 = float(np.percentile(centered_abs_l, 95))
        gate = (
            p95 <= QUALITY_THRESHOLDS["maximum_repeat_centered_cell_delta_l_star_p95"]
            and maximum_recipe_delta
            <= QUALITY_THRESHOLDS["maximum_repeat_recipe_median_delta_l_star"]
        )
        controller_results[controller] = {
            "controller_local_only": True,
            "centered_cell_absolute_delta_l_star_p95": p95,
            "maximum_recipe_centered_median_delta_l_star": maximum_recipe_delta,
            "recipe_centered_lightness": recipe_deltas,
            "coarse_repeat_gate_pass": gate,
            "qualified_level": False,
        }
    repeat_candidates = [
        controller
        for controller, value in controller_results.items()
        if value["coarse_repeat_gate_pass"]
        and any(
            item["controller"] == controller
            and item["coarse_lightness_mechanism_review_candidate"]
            for item in g3["controller_local_screen"]["target_groups"]
        )
    ]
    report = {
        "schema_version": 1,
        "kind": REPEAT_KIND,
        "campaign_id": pack.CAMPAIGN_ID,
        "test_id": pack.TEST_ID,
        "contract_id": pack.build_report()["contract_id"],
        "decision": (
            "COARSE_REPEATABLE_CONTROLLER_LOCAL_LIGHTNESS_REVIEW_CANDIDATE"
            if repeat_candidates
            else "REVIEW_NO_REPEATABLE_CONTROLLER_LOCAL_LIGHTNESS_CANDIDATE"
        ),
        "source_reports": {
            "G3": {
                "path": _relative_or_absolute(Path(g3_report_path)),
                "bytes": len(g3_payload),
                "file_sha256": _sha(g3_payload),
                "canonical_integrity_sha256": g3["integrity"]["sha256"],
            },
            "G4": {
                "path": _relative_or_absolute(Path(g4_report_path)),
                "bytes": len(g4_payload),
                "file_sha256": _sha(g4_payload),
                "canonical_integrity_sha256": g4["integrity"]["sha256"],
            },
        },
        "comparability": {
            "same_48mp_camera": True,
            "same_mount": True,
            "requested_and_effective_settings_exactly_equal": True,
            "controllers_pooled": False,
        },
        "controller_results": controller_results,
        "coarse_repeat_candidate_controllers": repeat_candidates,
        "qualification_boundary": {
            "camera_relative_coarse_screen_only": True,
            "qualified_colour_count": 0,
            "qualified_gray_levels": 0,
            "qualified_brightness_levels": 0,
            "fresh_white_reconstruction_still_required": True,
            "hold_coexistence_still_required": True,
        },
        "hardware_accessed": False,
        "camera_accessed": False,
        "network_requests": 0,
    }
    return _seal(report)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    analyze_command = commands.add_parser("analyze", allow_abbrev=False)
    analyze_command.add_argument("--photo", type=Path, required=True)
    analyze_command.add_argument("--capture-sidecar", type=Path, required=True)
    analyze_command.add_argument(
        "--geometry-reference-report",
        type=Path,
        help=(
            "sealed stable-code0 Latin V3 L3 analysis from the exact same "
            "48MP camera settings and fixed mount"
        ),
    )
    analyze_command.add_argument("--observation-output", type=Path, required=True)
    analyze_command.add_argument("--output", type=Path, required=True)
    compare = commands.add_parser("compare-repeat", allow_abbrev=False)
    compare.add_argument("--g3-report", type=Path, required=True)
    compare.add_argument("--g4-report", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "analyze":
            result = analyze(
                args.photo,
                args.capture_sidecar,
                geometry_reference_report_path=args.geometry_reference_report,
            )
            _write_exclusive(args.observation_output, result["observation_document"])
        else:
            result = compare_repeat(args.g3_report, args.g4_report)
        _write_exclusive(args.output, result)
    except (PhotoAnalysisError, OSError, ValueError, RuntimeError) as exc:
        print(f"LUMA/GRAY V3 photo analysis error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
