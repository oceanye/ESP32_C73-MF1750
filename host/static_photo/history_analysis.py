"""Measure one blue-history panel photo using a referenced camera session."""

from __future__ import annotations

import json
from pathlib import Path
import stat
from typing import Any, Mapping

import cv2
import numpy as np

from host.color_pipeline.color import delta_e_ciede2000, lab_to_srgb8
from host.epd_frame import HEIGHT, WIDTH

from .common import (
    StaticPhotoContractError,
    attach_integrity,
    canonical_json_bytes,
    file_sha256,
    prepare_empty_output_dir,
    verify_integrity,
)


class HistoryAnalysisError(StaticPhotoContractError):
    """Raised when a panel photo or bound evidence differs."""


def _load_verified(path: str | Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        payload = Path(path).read_bytes()
        raw = json.loads(payload)
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryAnalysisError(f"cannot load {label}: {error}") from error
    if not isinstance(raw, Mapping):
        raise HistoryAnalysisError(f"{label} must be an object")
    try:
        verify_integrity(raw, label)
    except StaticPhotoContractError as error:
        raise HistoryAnalysisError(str(error)) from error
    return dict(raw), payload


def _read_photo(path: Path) -> tuple[bytes, np.ndarray]:
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise HistoryAnalysisError("photo must be a regular non-symlink")
        payload = path.read_bytes()
    except OSError as error:
        raise HistoryAnalysisError(f"photo cannot be read: {error}") from error
    image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        raise HistoryAnalysisError("photo is not a supported three-channel image")
    return payload, image


def _parse_corners(corners: object, width: int, height: int) -> np.ndarray:
    result = np.asarray(corners, dtype=np.float32)
    if result.shape != (4, 2) or not np.all(np.isfinite(result)):
        raise HistoryAnalysisError("panel corners must contain finite TL TR BR BL")
    if (
        np.any(result[:, 0] < 0)
        or np.any(result[:, 0] >= width)
        or np.any(result[:, 1] < 0)
        or np.any(result[:, 1] >= height)
    ):
        raise HistoryAnalysisError("panel corners escape the photo")
    contour = result.reshape((-1, 1, 2))
    if not cv2.isContourConvex(contour) or abs(cv2.contourArea(contour)) < 1000:
        raise HistoryAnalysisError(
            "panel corners are not a sufficiently large convex quad"
        )
    return result


def _srgb_to_linear(values: np.ndarray) -> np.ndarray:
    normalized = values.astype(np.float64) / 255.0
    return np.where(
        normalized <= 0.04045,
        normalized / 12.92,
        ((normalized + 0.055) / 1.055) ** 2.4,
    )


def _xyz_to_lab_array(values: np.ndarray) -> np.ndarray:
    d65 = np.asarray((0.95047, 1.0, 1.08883), dtype=np.float64)
    scaled = values / d65
    delta = 6.0 / 29.0
    transformed = np.where(
        scaled > delta**3,
        np.cbrt(scaled),
        scaled / (3.0 * delta**2) + 4.0 / 29.0,
    )
    result = np.empty_like(values)
    result[:, 0] = 116.0 * transformed[:, 1] - 16.0
    result[:, 1] = 500.0 * (transformed[:, 0] - transformed[:, 1])
    result[:, 2] = 200.0 * (transformed[:, 1] - transformed[:, 2])
    return result


def _corrected_lab(rgb8: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    original_shape = rgb8.shape[:-1]
    linear = _srgb_to_linear(rgb8.reshape(-1, 3))
    design = np.column_stack((linear, np.ones(linear.shape[0])))
    xyz = design @ matrix.T
    return _xyz_to_lab_array(xyz).reshape(*original_shape, 3)


def analyze_history_photo(
    photo: str | Path,
    *,
    panel_corners: object,
    calibration_file: str | Path,
    plan_manifest_file: str | Path,
    batch_id: str,
    timepoint_seconds: int,
    output_dir: str | Path,
) -> dict[str, Any]:
    if batch_id not in ("A", "A-prime"):
        raise HistoryAnalysisError("batch_id must be A or A-prime")
    if type(timepoint_seconds) is not int or timepoint_seconds not in (5, 60, 600):
        raise HistoryAnalysisError("timepoint_seconds must be 5, 60, or 600")
    calibration, calibration_payload = _load_verified(calibration_file, "calibration")
    if (
        calibration.get("kind") != "MF17506_CAMERA_SESSION_CALIBRATION"
        or calibration.get("calibration_mode") != "REFERENCED_CALIBRATION"
        or calibration.get("quality", {}).get("qualified") is not True
    ):
        raise HistoryAnalysisError(
            "history analysis requires a qualified referenced calibration"
        )
    raw_matrix = calibration.get("model", {}).get(
        "matrix_rows_xyz_from_linear_rgb_plus_one"
    )
    matrix = np.asarray(raw_matrix, dtype=np.float64)
    if matrix.shape != (3, 4) or not np.all(np.isfinite(matrix)):
        raise HistoryAnalysisError("calibration affine matrix differs")
    manifest, manifest_payload = _load_verified(
        plan_manifest_file, "blue history manifest"
    )
    if (
        manifest.get("kind") != "MF17506_BLUE_HISTORY_16_RECIPE_OFFLINE_BUNDLE"
        or manifest.get("live_authorized") is not False
        or manifest.get("recipe_count") != 16
    ):
        raise HistoryAnalysisError("blue history manifest boundary differs")
    batch = next(
        (
            item
            for item in manifest.get("batches", [])
            if item.get("batch_id") == batch_id
        ),
        None,
    )
    if not isinstance(batch, Mapping) or len(batch.get("rois", [])) != 16:
        raise HistoryAnalysisError("selected batch ROI layout differs")
    photo_payload, source = _read_photo(Path(photo))
    source_height, source_width = source.shape[:2]
    corners = _parse_corners(panel_corners, source_width, source_height)
    target = np.asarray(
        [[0, 0], [WIDTH - 1, 0], [WIDTH - 1, HEIGHT - 1], [0, HEIGHT - 1]],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(corners, target)
    rectified = cv2.warpPerspective(
        source, transform, (WIDTH, HEIGHT), flags=cv2.INTER_LINEAR
    )
    annotated = rectified.copy()
    measurements: list[dict[str, Any]] = []
    for roi in batch["rois"]:
        rectangle = roi["rectangle"]
        inset = 16
        x0 = int(rectangle["x"]) + inset
        y0 = int(rectangle["y"]) + inset
        x1 = int(rectangle["x1_exclusive"]) - inset
        y1 = int(rectangle["y1_exclusive"]) - inset
        if not (0 <= x0 < x1 <= WIDTH and 0 <= y0 < y1 <= HEIGHT):
            raise HistoryAnalysisError("ROI rectangle differs")
        pixels_rgb = rectified[y0:y1:2, x0:x1:2, ::-1]
        median_rgb = np.median(pixels_rgb, axis=(0, 1))
        corrected = _corrected_lab(pixels_rgb, matrix)
        median_lab = np.median(corrected, axis=(0, 1))
        std_lab = np.std(corrected, axis=(0, 1))
        preview = lab_to_srgb8(tuple(float(value) for value in median_lab))
        measurements.append(
            {
                "recipe_id": roi["recipe_id"],
                "batch_id": batch_id,
                "controller": roi["controller"],
                "source_code": roi["source_code"],
                "target_code": roi["target_code"],
                "rectangle": dict(rectangle),
                "camera_median_rgb8": [round(float(value), 4) for value in median_rgb],
                "corrected_median_lab": [
                    round(float(value), 6) for value in median_lab
                ],
                "corrected_std_lab": [round(float(value), 6) for value in std_lab],
                "preview_rgb": list(preview),
                "high_clip_fraction": round(
                    float(np.mean(np.any(pixels_rgb >= 252, axis=2))), 8
                ),
                "low_clip_fraction": round(
                    float(np.mean(np.any(pixels_rgb <= 3, axis=2))), 8
                ),
            }
        )
        cv2.rectangle(annotated, (x0, y0), (x1 - 1, y1 - 1), (0, 0, 0), 1)
        cv2.putText(
            annotated,
            f"s{roi['source_code']}t{roi['target_code']}",
            (x0 + 3, y0 + 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
    target_groups: dict[str, list[dict[str, Any]]] = {}
    for measurement in measurements:
        target_groups.setdefault(str(measurement["target_code"]), []).append(
            measurement
        )
    summaries: dict[str, Any] = {}
    for target_code, group in target_groups.items():
        labs = [item["corrected_median_lab"] for item in group]
        deltas = [
            delta_e_ciede2000(labs[left], labs[right])
            for left in range(len(labs))
            for right in range(left + 1, len(labs))
        ]
        lightness = [float(lab[0]) for lab in labs]
        summaries[target_code] = {
            "source_count": len(group),
            "lightness_min": round(min(lightness), 6),
            "lightness_max": round(max(lightness), 6),
            "lightness_span": round(max(lightness) - min(lightness), 6),
            "maximum_pairwise_delta_e00": round(max(deltas), 6),
            "history_dependence_candidate": max(deltas) >= 2.0,
            "threshold_is_screening_only": True,
        }
    output = prepare_empty_output_dir(output_dir)
    ok, rectified_encoded = cv2.imencode(".png", rectified)
    ok_annotated, annotated_encoded = cv2.imencode(".png", annotated)
    if not ok or not ok_annotated:
        raise HistoryAnalysisError("cannot encode derived panel images")
    rectified_payload = rectified_encoded.tobytes()
    annotated_payload = annotated_encoded.tobytes()
    (output / "panel-rectified.png").write_bytes(rectified_payload)
    (output / "panel-annotated.png").write_bytes(annotated_payload)
    report_unsigned = {
        "schema_version": 1,
        "kind": "MF17506_BLUE_HISTORY_PHOTO_ANALYSIS",
        "batch_id": batch_id,
        "timepoint_seconds": timepoint_seconds,
        "source_photo": {
            "file": str(Path(photo).resolve()),
            "bytes": len(photo_payload),
            "sha256": file_sha256(photo_payload),
            "width": source_width,
            "height": source_height,
        },
        "calibration": {
            "file": str(Path(calibration_file).resolve()),
            "file_sha256": file_sha256(calibration_payload),
            "canonical_sha256": calibration["integrity"]["canonical_sha256"],
        },
        "plan_manifest": {
            "file": str(Path(plan_manifest_file).resolve()),
            "file_sha256": file_sha256(manifest_payload),
            "canonical_sha256": manifest["integrity"]["canonical_sha256"],
        },
        "registration": {
            "corners_tl_tr_br_bl": corners.astype(float).tolist(),
            "perspective_transform": transform.astype(float).tolist(),
        },
        "measurements": measurements,
        "target_summaries": summaries,
        "evidence_boundaries": {
            "camera_is_not_a_colorimeter": True,
            "candidate_classification_only": True,
            "qualified_history_palette_created": False,
            "new_pigment_colour_claimed": False,
            "device_io_performed": False,
        },
    }
    report = attach_integrity(report_unsigned)
    payload = canonical_json_bytes(report) + b"\n"
    report_file = output / "HISTORY-PHOTO-ANALYSIS.json"
    report_file.write_bytes(payload)
    return {
        "report_file": str(report_file.resolve()),
        "batch_id": batch_id,
        "timepoint_seconds": timepoint_seconds,
        "measurement_count": len(measurements),
        "target_summaries": summaries,
        "canonical_sha256": report["integrity"]["canonical_sha256"],
        "device_io_performed": False,
    }
