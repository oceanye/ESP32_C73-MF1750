#!/usr/bin/env python3
"""Rectify and measure a photograph of the fixed MF1750 dither Atlas.

This is a camera-relative analysis only.  It never accesses a device and does
not infer a new single-pixel pigment state, a calibrated colour, or a waveform
effect.  Four optional photo corner points are ordered TL, TR, BR, BL.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import stat
from typing import Any, Mapping, Sequence

import cv2
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LAYOUT = (
    REPO_ROOT
    / ".test-output"
    / "offline"
    / "MF1750_EC5_DITHER_COLOR_ATLAS_OFFLINE_20260810_V1"
    / "layout.json"
)
SCHEMA_VERSION = 2
REPORT_KIND = "mf1750-ec5-dither-atlas-camera-relative-photo-analysis"
RECTIFIED_WIDTH = 1024
RECTIFIED_HEIGHT = 600
INNER_MARGIN = 6
WHITE_REFERENCE_MIN_SIDE = 10
WHITE_REFERENCE_MIN_AREA = 400
HIGH_CLIP_THRESHOLD = 250


class PhotoAnalysisError(RuntimeError):
    """The photo, registration, layout, or output boundary is invalid."""


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: bytes | Mapping[str, Any]) -> str:
    payload = _canonical_json_bytes(value) if isinstance(value, Mapping) else value
    return hashlib.sha256(payload).hexdigest()


def _strict_json(path: Path, *, label: str) -> tuple[bytes, Mapping[str, Any]]:
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise PhotoAnalysisError(f"{label} must be a regular non-symlink")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise PhotoAnalysisError(f"{label} cannot be read: {error}") from error
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or len(payload) != after.st_size:
        raise PhotoAnalysisError(f"{label} changed while read")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {item}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise PhotoAnalysisError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(value, Mapping):
        raise PhotoAnalysisError(f"{label} root must be an object")
    return payload, value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _load_layout(path: Path) -> tuple[Mapping[str, Any], bytes]:
    payload, root = _strict_json(path, label="dither Atlas layout")
    integrity = root.get("integrity")
    unsigned = dict(root)
    unsigned.pop("integrity", None)
    expected_integrity = {
        "canonical_sha256": _sha256(unsigned),
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }
    if not isinstance(integrity, Mapping) or dict(integrity) != expected_integrity:
        raise PhotoAnalysisError("dither Atlas layout integrity differs")
    dimensions = root.get("dimensions")
    grid = root.get("grid")
    rois = root.get("rois")
    if (
        not isinstance(dimensions, Mapping)
        or dimensions.get("width") != RECTIFIED_WIDTH
        or dimensions.get("height") != RECTIFIED_HEIGHT
        or not isinstance(grid, Mapping)
        or grid.get("rows") != 7
        or grid.get("columns") != 5
        or not isinstance(rois, list)
        or len(rois) != 70
        or root.get("profile_source") != "factory_otp"
        or root.get("runtime_lut_or_waveform_changed") is not False
        or root.get("spatial_mixing_only") is not True
    ):
        raise PhotoAnalysisError("dither Atlas layout contract differs")
    return root, payload


def _parse_corners(text: str | None, width: int, height: int) -> np.ndarray:
    if text is None:
        return np.array(
            [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
            dtype=np.float32,
        )
    parts = text.replace(";", " ").split()
    if len(parts) != 4:
        raise PhotoAnalysisError("--corners requires four x,y points: TL TR BR BL")
    points: list[tuple[float, float]] = []
    try:
        for part in parts:
            x_text, y_text = part.split(",", maxsplit=1)
            point = (float(x_text), float(y_text))
            if not all(math.isfinite(item) for item in point):
                raise ValueError("non-finite corner")
            points.append(point)
    except ValueError as error:
        raise PhotoAnalysisError("--corners contains an invalid x,y point") from error
    result = np.asarray(points, dtype=np.float32)
    if (
        np.any(result[:, 0] < 0)
        or np.any(result[:, 0] >= width)
        or np.any(result[:, 1] < 0)
        or np.any(result[:, 1] >= height)
    ):
        raise PhotoAnalysisError("--corners escapes the source photo")
    contour = result.reshape((-1, 1, 2))
    if not cv2.isContourConvex(contour) or abs(cv2.contourArea(contour)) < 1000:
        raise PhotoAnalysisError("--corners are not a sufficiently large convex quad")
    return result


def _parse_white_reference(
    text: str | None, width: int, height: int
) -> tuple[int, int, int, int] | None:
    if text is None:
        return None
    parts = text.replace(",", " ").replace(";", " ").split()
    if len(parts) != 4:
        raise PhotoAnalysisError(
            "--white-reference requires x0,y0,x1,y1 in source-photo pixels"
        )
    try:
        values = [float(item) for item in parts]
    except ValueError as error:
        raise PhotoAnalysisError(
            "--white-reference contains an invalid coordinate"
        ) from error
    if not all(math.isfinite(item) for item in values):
        raise PhotoAnalysisError("--white-reference contains a non-finite coordinate")
    raw_x0, raw_y0, raw_x1, raw_y1 = values
    if not (0 <= raw_x0 < raw_x1 <= width and 0 <= raw_y0 < raw_y1 <= height):
        raise PhotoAnalysisError("--white-reference escapes the source photo")
    x0 = math.floor(raw_x0)
    y0 = math.floor(raw_y0)
    x1 = math.ceil(raw_x1)
    y1 = math.ceil(raw_y1)
    if (
        x1 - x0 < WHITE_REFERENCE_MIN_SIDE
        or y1 - y0 < WHITE_REFERENCE_MIN_SIDE
        or (x1 - x0) * (y1 - y0) < WHITE_REFERENCE_MIN_AREA
    ):
        raise PhotoAnalysisError("--white-reference rectangle is too small")
    return x0, y0, x1, y1


def _read_image(path: Path) -> tuple[bytes, np.ndarray]:
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise PhotoAnalysisError("photo must be a regular non-symlink")
        payload = path.read_bytes()
    except OSError as error:
        raise PhotoAnalysisError(f"photo cannot be read: {error}") from error
    image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        raise PhotoAnalysisError("photo is not a supported three-channel image")
    if image.shape[0] < 100 or image.shape[1] < 100:
        raise PhotoAnalysisError("photo is too small")
    return payload, image


def _lab_image(bgr: np.ndarray) -> np.ndarray:
    encoded = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float64)
    encoded[:, :, 0] *= 100.0 / 255.0
    encoded[:, :, 1:] -= 128.0
    return encoded


def _round_vector(values: np.ndarray, digits: int = 4) -> list[float]:
    return [round(float(item), digits) for item in values.tolist()]


def _measure_white_reference(
    source: np.ndarray, rectangle: tuple[int, int, int, int] | None
) -> tuple[dict[str, Any], tuple[np.ndarray, np.ndarray, np.ndarray] | None]:
    if rectangle is None:
        return {
            "provided": False,
            "source_rectangle": None,
            "uncalibrated_white_paper": True,
            "usable_for_camera_relative_normalization": False,
        }, None

    x0, y0, x1, y1 = rectangle
    pixels_bgr = source[y0:y1, x0:x1]
    pixels_rgb = pixels_bgr[:, :, ::-1]
    pixels_lab = _lab_image(pixels_bgr)
    mean_rgb = np.mean(pixels_rgb, axis=(0, 1))
    median_rgb = np.median(pixels_rgb, axis=(0, 1))
    mean_lab = np.mean(pixels_lab, axis=(0, 1))
    std_lab = np.std(pixels_lab, axis=(0, 1))
    channel_clipped = np.mean(pixels_rgb >= HIGH_CLIP_THRESHOLD, axis=(0, 1))
    any_channel_clipped = float(
        np.mean(np.any(pixels_rgb >= HIGH_CLIP_THRESHOLD, axis=2))
    )
    neutral_target = float(np.mean(median_rgb))
    nonzero_channels = bool(np.all(median_rgb > 1.0))
    neutral_gains = np.divide(
        neutral_target,
        median_rgb,
        out=np.ones(3, dtype=np.float64),
        where=median_rgb > 1.0,
    )
    highlights_not_substantially_clipped = any_channel_clipped <= 0.05
    usable = nonzero_channels and highlights_not_substantially_clipped
    report = {
        "provided": True,
        "source_rectangle": {
            "x": x0,
            "y": y0,
            "x1_exclusive": x1,
            "y1_exclusive": y1,
            "pixel_count": int((x1 - x0) * (y1 - y0)),
        },
        "camera_mean_rgb": _round_vector(mean_rgb),
        "camera_median_rgb": _round_vector(median_rgb, digits=2),
        "camera_mean_lab": _round_vector(mean_lab),
        "camera_std_lab": _round_vector(std_lab),
        "high_clip_threshold_8bit": HIGH_CLIP_THRESHOLD,
        "per_channel_high_clipped_fraction_rgb": _round_vector(
            channel_clipped, digits=6
        ),
        "any_channel_high_clipped_fraction": round(any_channel_clipped, 6),
        "neutral_white_balance_gains_rgb": _round_vector(neutral_gains, digits=6),
        "quality_flags": {
            "nonzero_reference_channels": nonzero_channels,
            "highlights_not_substantially_clipped": (
                highlights_not_substantially_clipped
            ),
        },
        "uncalibrated_white_paper": True,
        "usable_for_camera_relative_normalization": usable,
    }
    return report, (mean_lab, median_rgb, neutral_gains)


def _roi_measurements(
    rectified: np.ndarray,
    layout: Mapping[str, Any],
    white_reference_values: tuple[np.ndarray, np.ndarray, np.ndarray] | None,
) -> list[dict[str, Any]]:
    lab = _lab_image(rectified)
    gray = cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY)
    measurements: list[dict[str, Any]] = []
    for roi in layout["rois"]:
        rectangle = roi["rectangle"]
        x0 = int(rectangle["x"]) + INNER_MARGIN
        x1 = int(rectangle["x1_exclusive"]) - INNER_MARGIN
        y0 = int(rectangle["y"]) + INNER_MARGIN
        y1 = int(rectangle["y1_exclusive"]) - INNER_MARGIN
        if not (0 <= x0 < x1 <= RECTIFIED_WIDTH and 0 <= y0 < y1 <= RECTIFIED_HEIGHT):
            raise PhotoAnalysisError(f"ROI {roi['roi_id']} rectangle differs")
        pixels_bgr = rectified[y0:y1, x0:x1]
        pixels_lab = lab[y0:y1, x0:x1]
        pixels_gray = gray[y0:y1, x0:x1]
        mean_lab = np.mean(pixels_lab, axis=(0, 1))
        std_lab = np.std(pixels_lab, axis=(0, 1))
        median_bgr = np.median(pixels_bgr, axis=(0, 1))
        laplacian = cv2.Laplacian(pixels_gray, cv2.CV_64F)
        measurement = {
            "roi_id": roi["roi_id"],
            "controller": roi["controller"],
            "display_row": roi["display_row"],
            "display_column": roi["display_column"],
            "row_id": roi["row_id"],
            "appearance_hypothesis": roi["appearance_hypothesis"],
            "recipe": deepcopy(roi["recipe"]),
            "analysis_rectangle": {
                "x": x0,
                "y": y0,
                "x1_exclusive": x1,
                "y1_exclusive": y1,
            },
            "camera_mean_lab": _round_vector(mean_lab),
            "camera_std_lab": _round_vector(std_lab),
            "camera_median_rgb": _round_vector(median_bgr[::-1], digits=2),
            "grayscale_laplacian_variance": round(float(np.var(laplacian)), 4),
            "white_reference_relative": None,
        }
        if white_reference_values is not None:
            reference_mean_lab, reference_median_rgb, neutral_gains = (
                white_reference_values
            )
            median_rgb = median_bgr[::-1]
            lab_offset = mean_lab - reference_mean_lab
            rgb_ratio = np.divide(
                median_rgb,
                reference_median_rgb,
                out=np.zeros(3, dtype=np.float64),
                where=reference_median_rgb > 1.0,
            )
            measurement["white_reference_relative"] = {
                "camera_mean_lab_offset_from_white_reference": _round_vector(
                    lab_offset
                ),
                "camera_delta_e76_from_white_reference": round(
                    float(np.linalg.norm(lab_offset)), 4
                ),
                "camera_median_rgb_ratio_to_white_reference": _round_vector(
                    rgb_ratio, digits=6
                ),
                "camera_neutralized_median_rgb": _round_vector(
                    median_rgb * neutral_gains, digits=2
                ),
            }
        measurements.append(measurement)
    return measurements


def _relative_summaries(measurements: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    indexed = {
        (item["controller"], item["display_row"], item["display_column"]): item
        for item in measurements
    }
    deltas: list[float] = []
    corresponding: list[dict[str, Any]] = []
    for row in range(7):
        for column in range(5):
            left = np.asarray(indexed[("CS1", row, column)]["camera_mean_lab"])
            right = np.asarray(indexed[("CS2", row, column)]["camera_mean_lab"])
            delta = float(np.linalg.norm(left - right))
            deltas.append(delta)
            corresponding.append(
                {
                    "display_row": row,
                    "display_column": column,
                    "camera_delta_e76": round(delta, 4),
                }
            )

    expected_b_fractions = np.asarray([0.0, 0.25, 0.5, 0.75, 1.0])
    projections: list[dict[str, Any]] = []
    for controller in ("CS1", "CS2"):
        for row in range(7):
            values = [
                np.asarray(indexed[(controller, row, column)]["camera_mean_lab"])
                for column in range(5)
            ]
            vector = values[-1] - values[0]
            denominator = float(np.dot(vector, vector))
            if denominator <= 1e-9:
                fractions = np.full(5, np.nan)
                rmse = None
                monotonic = None
            else:
                fractions = np.asarray(
                    [
                        float(np.dot(value - values[0], vector) / denominator)
                        for value in values
                    ]
                )
                rmse = float(np.sqrt(np.mean((fractions - expected_b_fractions) ** 2)))
                monotonic = bool(np.all(np.diff(fractions) >= -0.05))
            projections.append(
                {
                    "controller": controller,
                    "display_row": row,
                    "projected_b_fractions": [
                        None
                        if not math.isfinite(float(item))
                        else round(float(item), 4)
                        for item in fractions
                    ],
                    "expected_b_fractions": expected_b_fractions.tolist(),
                    "projection_rmse": None if rmse is None else round(rmse, 4),
                    "monotonic_with_tolerance_0_05": monotonic,
                }
            )
    return {
        "left_right_corresponding_roi_camera_delta_e76": corresponding,
        "left_right_summary": {
            "count": len(deltas),
            "mean_camera_delta_e76": round(float(np.mean(deltas)), 4),
            "maximum_camera_delta_e76": round(float(np.max(deltas)), 4),
        },
        "row_endpoint_projection": projections,
    }


def _encode_png(image: np.ndarray, *, label: str) -> bytes:
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise PhotoAnalysisError(f"could not encode {label}")
    return encoded.tobytes()


def _annotated_image(rectified: np.ndarray, layout: Mapping[str, Any]) -> np.ndarray:
    annotated = rectified.copy()
    for roi in layout["rois"]:
        rectangle = roi["rectangle"]
        x0, y0 = int(rectangle["x"]), int(rectangle["y"])
        x1, y1 = int(rectangle["x1_exclusive"]), int(rectangle["y1_exclusive"])
        color = (0, 0, 0) if roi["controller"] == "CS1" else (255, 255, 255)
        cv2.rectangle(annotated, (x0, y0), (x1 - 1, y1 - 1), color, 1)
        label = f"{roi['display_row'] + 1}-{roi['display_column'] + 1}"
        cv2.putText(
            annotated,
            label,
            (x0 + 3, y0 + 14),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            color,
            1,
            cv2.LINE_AA,
        )
    return annotated


def analyze(
    photo: Path,
    *,
    layout_file: Path = DEFAULT_LAYOUT,
    output_dir: Path,
    corners_text: str | None = None,
    white_reference_text: str | None = None,
) -> dict[str, Any]:
    layout, layout_payload = _load_layout(layout_file)
    photo_payload, source = _read_image(photo)
    source_height, source_width = source.shape[:2]
    corners = _parse_corners(corners_text, source_width, source_height)
    white_reference_rectangle = _parse_white_reference(
        white_reference_text, source_width, source_height
    )
    white_reference, white_reference_values = _measure_white_reference(
        source, white_reference_rectangle
    )
    target = np.asarray(
        [
            [0, 0],
            [RECTIFIED_WIDTH - 1, 0],
            [RECTIFIED_WIDTH - 1, RECTIFIED_HEIGHT - 1],
            [0, RECTIFIED_HEIGHT - 1],
        ],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(corners, target)
    rectified = cv2.warpPerspective(
        source,
        transform,
        (RECTIFIED_WIDTH, RECTIFIED_HEIGHT),
        flags=cv2.INTER_LINEAR,
    )
    measurements = _roi_measurements(rectified, layout, white_reference_values)
    summaries = _relative_summaries(measurements)

    output_dir = Path(output_dir)
    if output_dir.exists():
        if output_dir.is_symlink() or not output_dir.is_dir():
            raise PhotoAnalysisError("output directory boundary differs")
        if any(output_dir.iterdir()):
            raise PhotoAnalysisError("output directory must not already contain files")
    else:
        output_dir.mkdir(parents=True)

    rectified_payload = _encode_png(rectified, label="rectified photo")
    annotated_payload = _encode_png(
        _annotated_image(rectified, layout), label="annotated photo"
    )
    rectified_file = output_dir / "rectified.png"
    annotated_file = output_dir / "annotated.png"
    rectified_file.write_bytes(rectified_payload)
    annotated_file.write_bytes(annotated_payload)

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "source_photo": {
            "file": str(Path(photo).resolve()),
            "bytes": len(photo_payload),
            "sha256": _sha256(photo_payload),
            "width": source_width,
            "height": source_height,
        },
        "registration": {
            "corner_order": "TL_TR_BR_BL",
            "source_corners_xy": [
                [round(float(x), 4), round(float(y), 4)] for x, y in corners
            ],
            "rectified_width": RECTIFIED_WIDTH,
            "rectified_height": RECTIFIED_HEIGHT,
            "perspective_transform": [
                [round(float(item), 10) for item in row] for row in transform
            ],
        },
        "layout": {
            "file": str(Path(layout_file).resolve()),
            "bytes": len(layout_payload),
            "file_sha256": _sha256(layout_payload),
            "canonical_sha256": layout["integrity"]["canonical_sha256"],
            "roi_count": len(layout["rois"]),
        },
        "white_reference": white_reference,
        "derived_images": {
            "rectified": {
                "file": str(rectified_file.resolve()),
                "bytes": len(rectified_payload),
                "sha256": _sha256(rectified_payload),
            },
            "annotated": {
                "file": str(annotated_file.resolve()),
                "bytes": len(annotated_payload),
                "sha256": _sha256(annotated_payload),
            },
        },
        "roi_measurements": measurements,
        "relative_summaries": summaries,
        "evidence_boundaries": {
            "camera_relative_only": True,
            "camera_is_not_a_colorimeter": True,
            "white_reference_provided": white_reference["provided"],
            "white_reference_is_uncalibrated_paper": True,
            "white_reference_enables_absolute_colour_qualification": False,
            "absolute_colour_qualification": False,
            "new_single_pixel_pigment_state_inferred": False,
            "new_waveform_or_lut_state_inferred": False,
            "spatial_dither_may_create_distance_dependent_visual_mixes": True,
            "operator_near_and_mid_distance_observation_still_required": True,
        },
    }
    report["integrity"] = {
        "canonical_sha256": _sha256(report),
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }
    report_payload = _canonical_json_bytes(report) + b"\n"
    report_file = output_dir / "photo-analysis.json"
    report_file.write_bytes(report_payload)
    return {
        "report_file": str(report_file.resolve()),
        "report_bytes": len(report_payload),
        "report_file_sha256": _sha256(report_payload),
        "report_canonical_sha256": report["integrity"]["canonical_sha256"],
        "roi_count": len(measurements),
        "left_right_summary": summaries["left_right_summary"],
        "evidence_boundaries": report["evidence_boundaries"],
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--photo", type=Path, required=True)
    parser.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--corners",
        help='four panel corners as "TLx,TLy TRx,TRy BRx,BRy BLx,BLy"',
    )
    parser.add_argument(
        "--white-reference",
        help="source-photo A4 region as x0,y0,x1,y1 (x1/y1 exclusive)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = analyze(
            args.photo,
            layout_file=args.layout,
            output_dir=args.output_dir,
            corners_text=args.corners,
            white_reference_text=args.white_reference,
        )
    except PhotoAnalysisError as error:
        print(f"dither Atlas photo analysis error: {error}")
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
