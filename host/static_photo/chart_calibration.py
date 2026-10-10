"""Manual-corner, camera-relative or referenced 24-patch calibration."""

from __future__ import annotations

from dataclasses import dataclass
import csv
import io
import math
from pathlib import Path
import stat
from typing import Any, Sequence

import cv2
import numpy as np

from host.color_pipeline.color import delta_e_ciede2000, lab_to_xyz, xyz_to_lab

from .chart_spec import ChartSpec
from .common import (
    StaticPhotoContractError,
    attach_integrity,
    canonical_json_bytes,
    file_sha256,
    prepare_empty_output_dir,
)


CALIBRATION_SCHEMA_VERSION = 1
RECTIFIED_CELL_PIXELS = 160
HIGH_CLIP = 252
LOW_CLIP = 3


class ChartCalibrationError(StaticPhotoContractError):
    """Raised when chart geometry, captures, or colour fitting differs."""


@dataclass(frozen=True)
class ChartCapture:
    photo: Path
    corners: tuple[
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
    ]


def parse_corners(text: str, width: int, height: int) -> np.ndarray:
    parts = text.replace(";", " ").split()
    if len(parts) != 4:
        raise ChartCalibrationError("corners require four x,y points: TL TR BR BL")
    points: list[tuple[float, float]] = []
    try:
        for part in parts:
            x_text, y_text = part.split(",", maxsplit=1)
            point = (float(x_text), float(y_text))
            if not all(math.isfinite(value) for value in point):
                raise ValueError("non-finite")
            points.append(point)
    except ValueError as error:
        raise ChartCalibrationError("corners contain an invalid x,y point") from error
    result = np.asarray(points, dtype=np.float32)
    if (
        np.any(result[:, 0] < 0)
        or np.any(result[:, 0] >= width)
        or np.any(result[:, 1] < 0)
        or np.any(result[:, 1] >= height)
    ):
        raise ChartCalibrationError("corners escape the source photo")
    if (
        not cv2.isContourConvex(result.reshape((-1, 1, 2)))
        or abs(cv2.contourArea(result.reshape((-1, 1, 2)))) < 1000
    ):
        raise ChartCalibrationError("corners are not a sufficiently large convex quad")
    return result


def _read_photo(path: Path) -> tuple[bytes, np.ndarray]:
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ChartCalibrationError("photo must be a regular non-symlink")
        payload = path.read_bytes()
    except OSError as error:
        raise ChartCalibrationError(f"photo cannot be read: {error}") from error
    image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        raise ChartCalibrationError("photo is not a supported three-channel image")
    if image.shape[0] < 100 or image.shape[1] < 100:
        raise ChartCalibrationError("photo is too small")
    return payload, image


def _srgb_to_linear(values: np.ndarray) -> np.ndarray:
    normalized = values.astype(np.float64) / 255.0
    return np.where(
        normalized <= 0.04045,
        normalized / 12.92,
        ((normalized + 0.055) / 1.055) ** 2.4,
    )


def _fit_affine(camera_linear: np.ndarray, reference_xyz: np.ndarray) -> np.ndarray:
    design = np.column_stack((camera_linear, np.ones(camera_linear.shape[0])))
    weights = np.ones(camera_linear.shape[0], dtype=np.float64)
    solution = np.zeros((4, 3), dtype=np.float64)
    for _ in range(8):
        root = np.sqrt(weights)[:, None]
        solution = np.linalg.lstsq(design * root, reference_xyz * root, rcond=None)[0]
        residual = np.linalg.norm(design @ solution - reference_xyz, axis=1)
        scale = max(float(np.median(residual)) * 1.4826, 1e-8)
        cutoff = 1.5 * scale
        weights = np.where(
            residual <= cutoff, 1.0, cutoff / np.maximum(residual, 1e-12)
        )
    return solution.T


def _apply_affine(matrix: np.ndarray, camera_linear: np.ndarray) -> np.ndarray:
    design = np.column_stack((camera_linear, np.ones(camera_linear.shape[0])))
    return design @ matrix.T


def _xyz_rows_to_lab(values: np.ndarray) -> list[tuple[float, float, float]]:
    return [xyz_to_lab(tuple(float(item) for item in row)) for row in values]


def _encode_png(image: np.ndarray, label: str) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise ChartCalibrationError(f"cannot encode {label}")
    return encoded.tobytes()


def calibrate_chart(
    spec: ChartSpec,
    captures: Sequence[ChartCapture],
    *,
    output_dir: str | Path,
) -> dict[str, Any]:
    if not isinstance(spec, ChartSpec):
        raise ChartCalibrationError("spec must be a ChartSpec")
    if not isinstance(captures, (list, tuple)) or not captures:
        raise ChartCalibrationError("at least one chart capture is required")
    if len(captures) not in (1, 3):
        raise ChartCalibrationError(
            "capture count must be 1 for setup or 3 for qualification"
        )
    output = prepare_empty_output_dir(output_dir)
    rectified_width = spec.columns * RECTIFIED_CELL_PIXELS
    rectified_height = spec.rows * RECTIFIED_CELL_PIXELS
    target = np.asarray(
        [
            [0, 0],
            [rectified_width - 1, 0],
            [rectified_width - 1, rectified_height - 1],
            [0, rectified_height - 1],
        ],
        dtype=np.float32,
    )

    capture_records: list[dict[str, Any]] = []
    per_capture_rgb: list[np.ndarray] = []
    per_capture_qc: list[list[dict[str, float]]] = []
    first_rectified: np.ndarray | None = None
    for ordinal, capture in enumerate(captures, start=1):
        if not isinstance(capture, ChartCapture):
            raise ChartCalibrationError("captures must contain ChartCapture values")
        payload, source = _read_photo(Path(capture.photo))
        height, width = source.shape[:2]
        corners = np.asarray(capture.corners, dtype=np.float32)
        if corners.shape != (4, 2):
            raise ChartCalibrationError("capture corners must contain TL TR BR BL")
        checked = parse_corners(
            " ".join(f"{float(x)},{float(y)}" for x, y in corners), width, height
        )
        transform = cv2.getPerspectiveTransform(checked, target)
        rectified = cv2.warpPerspective(
            source,
            transform,
            (rectified_width, rectified_height),
            flags=cv2.INTER_LINEAR,
        )
        if first_rectified is None:
            first_rectified = rectified.copy()
        patch_values: list[np.ndarray] = []
        patch_qc: list[dict[str, float]] = []
        inset = spec.patch_inset_fraction
        for patch in spec.patches:
            cell_x0 = patch.column * RECTIFIED_CELL_PIXELS
            cell_y0 = patch.row * RECTIFIED_CELL_PIXELS
            margin = int(round(RECTIFIED_CELL_PIXELS * inset))
            pixels_bgr = rectified[
                cell_y0 + margin : cell_y0 + RECTIFIED_CELL_PIXELS - margin,
                cell_x0 + margin : cell_x0 + RECTIFIED_CELL_PIXELS - margin,
            ]
            pixels_rgb = pixels_bgr[:, :, ::-1]
            median = np.median(pixels_rgb, axis=(0, 1))
            patch_values.append(median)
            patch_qc.append(
                {
                    "high_clip_fraction": float(
                        np.mean(np.any(pixels_rgb >= HIGH_CLIP, axis=2))
                    ),
                    "low_clip_fraction": float(
                        np.mean(np.any(pixels_rgb <= LOW_CLIP, axis=2))
                    ),
                    "maximum_channel_std_rgb8": float(
                        np.max(np.std(pixels_rgb, axis=(0, 1)))
                    ),
                }
            )
        per_capture_rgb.append(np.asarray(patch_values, dtype=np.float64))
        per_capture_qc.append(patch_qc)
        capture_records.append(
            {
                "ordinal": ordinal,
                "file": str(Path(capture.photo).resolve()),
                "bytes": len(payload),
                "sha256": file_sha256(payload),
                "width": width,
                "height": height,
                "corners_tl_tr_br_bl": checked.astype(float).tolist(),
                "perspective_transform": transform.astype(float).tolist(),
            }
        )

    assert first_rectified is not None
    aggregate_rgb = np.median(np.stack(per_capture_rgb, axis=0), axis=0)
    capture_spread = np.max(np.ptp(np.stack(per_capture_rgb, axis=0), axis=0), axis=1)
    camera_linear = _srgb_to_linear(aggregate_rgb)
    reference_labs = [patch.reference_lab for patch in spec.patches]
    calibration_mode = (
        "REFERENCED_CALIBRATION" if spec.has_reference_values else "CAMERA_RELATIVE"
    )
    matrix: np.ndarray | None = None
    fitted_labs: list[tuple[float, float, float]] | None = None
    delta_e00: list[float] | None = None
    loo_delta_e00: list[float] | None = None
    if spec.has_reference_values:
        references = [lab for lab in reference_labs if lab is not None]
        if len(references) != 24:
            raise ChartCalibrationError("referenced chart has missing Lab values")
        reference_xyz = np.asarray([lab_to_xyz(lab) for lab in references])
        matrix = _fit_affine(camera_linear, reference_xyz)
        fitted_labs = _xyz_rows_to_lab(_apply_affine(matrix, camera_linear))
        delta_e00 = [
            delta_e_ciede2000(reference, measured)
            for reference, measured in zip(references, fitted_labs)
        ]
        loo_delta_e00 = []
        for held in range(24):
            keep = np.asarray([index != held for index in range(24)])
            held_matrix = _fit_affine(camera_linear[keep], reference_xyz[keep])
            held_xyz = _apply_affine(held_matrix, camera_linear[held : held + 1])[0]
            held_lab = xyz_to_lab(tuple(float(item) for item in held_xyz))
            loo_delta_e00.append(delta_e_ciede2000(references[held], held_lab))

    maximum_high_clip = max(
        item["high_clip_fraction"] for capture in per_capture_qc for item in capture
    )
    maximum_patch_std = max(
        item["maximum_channel_std_rgb8"]
        for capture in per_capture_qc
        for item in capture
    )
    maximum_capture_spread = float(np.max(capture_spread))
    quality_flags = {
        "all_24_patches_measured": True,
        "highlights_not_substantially_clipped": maximum_high_clip <= 0.05,
        "patches_spatially_uniform": maximum_patch_std <= 18.0,
        "three_capture_qualification_set": len(captures) == 3,
        "capture_repeatability_rgb8": len(captures) == 3
        and maximum_capture_spread <= 8.0,
        "reference_values_available": spec.has_reference_values,
    }
    qualified = all(quality_flags.values())
    annotated = first_rectified.copy()
    for patch in spec.patches:
        x0 = patch.column * RECTIFIED_CELL_PIXELS
        y0 = patch.row * RECTIFIED_CELL_PIXELS
        x1 = x0 + RECTIFIED_CELL_PIXELS
        y1 = y0 + RECTIFIED_CELL_PIXELS
        cv2.rectangle(annotated, (x0, y0), (x1 - 1, y1 - 1), (0, 0, 0), 2)
        cv2.putText(
            annotated,
            patch.patch_id,
            (x0 + 5, y0 + 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
    rectified_payload = _encode_png(first_rectified, "rectified chart")
    annotated_payload = _encode_png(annotated, "annotated chart")
    (output / "chart-rectified.png").write_bytes(rectified_payload)
    (output / "chart-annotated.png").write_bytes(annotated_payload)

    patch_records: list[dict[str, Any]] = []
    for index, patch in enumerate(spec.patches):
        patch_records.append(
            {
                "patch_id": patch.patch_id,
                "row": patch.row,
                "column": patch.column,
                "camera_median_rgb8": [
                    round(float(value), 4) for value in aggregate_rgb[index]
                ],
                "capture_spread_max_rgb8": round(float(capture_spread[index]), 4),
                "reference_lab": None
                if patch.reference_lab is None
                else list(patch.reference_lab),
                "fitted_lab": None
                if fitted_labs is None
                else [round(float(value), 6) for value in fitted_labs[index]],
                "delta_e00": None if delta_e00 is None else round(delta_e00[index], 6),
                "leave_one_out_delta_e00": None
                if loo_delta_e00 is None
                else round(loo_delta_e00[index], 6),
                "capture_qc": [capture[index] for capture in per_capture_qc],
            }
        )

    report_unsigned: dict[str, Any] = {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "kind": "MF17506_CAMERA_SESSION_CALIBRATION",
        "calibration_mode": calibration_mode,
        "chart_spec": {
            "chart_id": spec.chart_id,
            "canonical_sha256": spec.mapping()["integrity"]["canonical_sha256"],
            "reference_grade": spec.reference_grade.value,
        },
        "captures": capture_records,
        "registration": {
            "corner_order": "TL_TR_BR_BL",
            "rectified_width": rectified_width,
            "rectified_height": rectified_height,
            "patch_inset_fraction": spec.patch_inset_fraction,
        },
        "model": {
            "input": "camera JPEG/PNG sRGB decoded to linear RGB",
            "output": "CIE XYZ D65/2deg",
            "type": None if matrix is None else "robust affine 3x4",
            "matrix_rows_xyz_from_linear_rgb_plus_one": None
            if matrix is None
            else [[round(float(value), 12) for value in row] for row in matrix],
            "higher_order_polynomial_used": False,
        },
        "quality": {
            "maximum_high_clip_fraction": round(maximum_high_clip, 8),
            "maximum_patch_channel_std_rgb8": round(maximum_patch_std, 6),
            "maximum_capture_spread_rgb8": round(maximum_capture_spread, 6),
            "flags": quality_flags,
            "qualified": qualified,
            "delta_e00_summary": None
            if delta_e00 is None
            else {
                "median_fit": round(float(np.median(delta_e00)), 6),
                "maximum_fit": round(float(np.max(delta_e00)), 6),
                "median_leave_one_out": round(float(np.median(loo_delta_e00)), 6),
                "maximum_leave_one_out": round(float(np.max(loo_delta_e00)), 6),
                "threshold_is_reporting_only": True,
            },
        },
        "patches": patch_records,
        "derived_images": {
            "rectified": {
                "file": "chart-rectified.png",
                "bytes": len(rectified_payload),
                "sha256": file_sha256(rectified_payload),
            },
            "annotated": {
                "file": "chart-annotated.png",
                "bytes": len(annotated_payload),
                "sha256": file_sha256(annotated_payload),
            },
        },
        "evidence_boundaries": {
            "camera_is_not_a_colorimeter": True,
            "a4_white_is_not_a_calibration_reference": True,
            "absolute_metrology_claimed": False,
            "panel_colour_state_inferred": False,
            "device_io_performed": False,
        },
    }
    report = attach_integrity(report_unsigned)
    report_payload = canonical_json_bytes(report) + b"\n"
    (output / "CAMERA-CALIBRATION.json").write_bytes(report_payload)

    csv_buffer = io.StringIO(newline="")
    writer = csv.writer(csv_buffer, lineterminator="\n")
    writer.writerow(
        [
            "patch_id",
            "row",
            "column",
            "camera_r",
            "camera_g",
            "camera_b",
            "delta_e00",
            "loo_delta_e00",
        ]
    )
    for record in patch_records:
        writer.writerow(
            [
                record["patch_id"],
                record["row"],
                record["column"],
                *record["camera_median_rgb8"],
                record["delta_e00"],
                record["leave_one_out_delta_e00"],
            ]
        )
    (output / "patch-measurements.csv").write_text(
        csv_buffer.getvalue(), encoding="utf-8", newline=""
    )
    return {
        "output_dir": str(output.resolve()),
        "calibration_mode": calibration_mode,
        "qualified": qualified,
        "capture_count": len(captures),
        "canonical_sha256": report["integrity"]["canonical_sha256"],
        "device_io_performed": False,
    }
