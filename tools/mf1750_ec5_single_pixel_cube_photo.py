#!/usr/bin/env python3
"""Rectify and compare the 528 uniform ROIs in a D1-512 target photo.

This is camera-relative evidence only.  It detects the rotated 22-by-24 cell
lattice, maps it back to the logical 1024-by-600 frame, and looks for Lab
outliers within each final transport code after removing a smooth spatial
lighting trend.  It does not claim calibrated physical colour.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np


WIDTH = 1024
HEIGHT = 600
BANDS = 22
POSITIONS = 24


class PhotoAnalysisError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cell_contours(image: np.ndarray) -> list[tuple[float, float]]:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    scale = image.shape[1] / 3024.0
    mask = ((hsv[:, :, 1] > 45) & (hsv[:, :, 2] > 35)).astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    points: list[tuple[float, float]] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        x, y, w, h = cv2.boundingRect(contour)
        if not 3000 * scale**2 < area < 22000 * scale**2:
            continue
        if not 45 * scale < w < 135 * scale or not 70 * scale < h < 210 * scale:
            continue
        if not 0.06 * image.shape[1] < x < 0.92 * image.shape[1]:
            continue
        if not 0.04 * image.shape[0] < y < 0.99 * image.shape[0]:
            continue
        points.append((x + w / 2.0, y + h / 2.0))
    if len(points) < 300:
        raise PhotoAnalysisError(f"only {len(points)} coloured cells detected")
    return points


def _cluster_bands(
    points: list[tuple[float, float]],
) -> list[list[tuple[float, float]]]:
    cv2.setRNGSeed(1750)
    data = np.float32([[point[1]] for point in points])
    _, labels, centers = cv2.kmeans(
        data,
        BANDS,
        None,
        (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 0.01),
        30,
        cv2.KMEANS_PP_CENTERS,
    )
    order = np.argsort(centers[:, 0])
    result: list[list[tuple[float, float]]] = []
    for cluster in order:
        members = [points[index] for index in np.where(labels[:, 0] == cluster)[0]]
        members.sort()
        if not 12 <= len(members) <= POSITIONS:
            raise PhotoAnalysisError(
                f"band {len(result)} contains {len(members)} detected cells"
            )
        result.append(members)
    return result


def _fit_one_lattice(xs: np.ndarray) -> tuple[float, float, np.ndarray]:
    gaps = np.diff(np.sort(xs))
    base = float(np.percentile(gaps, 30))
    best: tuple[float, float, float, np.ndarray] | None = None
    for spacing in np.linspace(base * 0.88, base * 1.12, 161):
        for anchor in xs:
            for index in range(POSITIONS):
                origin = float(anchor - index * spacing)
                assigned = np.rint((xs - origin) / spacing).astype(int)
                if assigned.min() < 0 or assigned.max() >= POSITIONS:
                    continue
                if len(np.unique(assigned)) != len(assigned):
                    continue
                residual = xs - (origin + assigned * spacing)
                score = float(np.mean(residual**2))
                if best is None or score < best[0]:
                    best = (score, origin, float(spacing), assigned)
    if best is None:
        raise PhotoAnalysisError("could not assign a 24-position lattice")
    _, origin, spacing, assigned = best
    return origin, spacing, assigned


def _logical_to_photo(
    points: list[tuple[float, float]],
) -> tuple[np.ndarray, dict[str, Any]]:
    bands = _cluster_bands(points)
    logical: list[tuple[float, float]] = []
    photo: list[tuple[float, float]] = []
    assignments: list[dict[str, Any]] = []
    for band_index, members in enumerate(bands):
        xs = np.array([point[0] for point in members], dtype=np.float64)
        origin, spacing, indices = _fit_one_lattice(xs)
        controller = 0 if band_index < 11 else 1
        column = band_index if controller == 0 else band_index - 11
        logical_x = controller * 512 + 36 + column * 44
        for point, left_index in zip(members, indices, strict=True):
            row = 23 - int(left_index)
            logical_y = 24 + row * 24
            logical.append((logical_x, logical_y))
            photo.append(point)
        assignments.append(
            {
                "band": band_index,
                "detected_cells": len(members),
                "photo_x_origin": origin,
                "photo_x_spacing": spacing,
            }
        )
    logical_array = np.float32(logical)
    photo_array = np.float32(photo)
    matrix, inlier_mask = cv2.findHomography(
        logical_array, photo_array, cv2.RANSAC, 10.0
    )
    if matrix is None or inlier_mask is None:
        raise PhotoAnalysisError("homography fit failed")
    projected = cv2.perspectiveTransform(logical_array[None, :, :], matrix)[0]
    errors = np.linalg.norm(projected - photo_array, axis=1)
    inliers = inlier_mask[:, 0].astype(bool)
    if int(inliers.sum()) < 300:
        raise PhotoAnalysisError(f"only {int(inliers.sum())} homography inliers")
    evidence = {
        "detected_coloured_cells": len(points),
        "homography_points": len(logical),
        "homography_inliers": int(inliers.sum()),
        "inlier_rmse_photo_px": float(np.sqrt(np.mean(errors[inliers] ** 2))),
        "inlier_max_error_photo_px": float(errors[inliers].max()),
        "bands": assignments,
    }
    return matrix, evidence


def _lab_from_bgr(values: np.ndarray) -> np.ndarray:
    patch = np.uint8(values.reshape(1, -1, 3))
    lab = cv2.cvtColor(patch, cv2.COLOR_BGR2LAB)[0].astype(np.float64)
    lab[:, 0] *= 100.0 / 255.0
    lab[:, 1:] -= 128.0
    return lab


def _oriented_rectified(
    rectified: np.ndarray,
    *,
    swap_controllers: bool,
    flip_controller_1: bool,
    flip_controller_2: bool,
    flip_rows: bool,
) -> np.ndarray:
    left = rectified[:, : WIDTH // 2]
    right = rectified[:, WIDTH // 2 :]
    if swap_controllers:
        left, right = right, left
    if flip_controller_1:
        left = cv2.flip(left, 1)
    if flip_controller_2:
        right = cv2.flip(right, 1)
    result = np.concatenate((left, right), axis=1)
    return cv2.flip(result, 0) if flip_rows else result


def _sample_records(
    rectified: np.ndarray, template: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    records = [dict(record) for record in template]
    for record in records:
        x0, x1 = int(record["x0"]), int(record["x1_exclusive"])
        y0, y1 = int(record["y0"]), int(record["y1_exclusive"])
        margin_x = max(3, int((x1 - x0) * 0.22))
        margin_y = max(2, int((y1 - y0) * 0.22))
        patch = rectified[
            y0 + margin_y : y1 - margin_y,
            x0 + margin_x : x1 - margin_x,
        ]
        median_bgr = np.median(patch.reshape(-1, 3), axis=0)
        median_lab = _lab_from_bgr(median_bgr)[0]
        record["center_x"] = (x0 + x1) / 2.0
        record["center_y"] = (y0 + y1) / 2.0
        record["median_rgb"] = [float(value) for value in median_bgr[::-1]]
        record["median_lab"] = [float(value) for value in median_lab]
    return records


def _orientation_score(records: list[dict[str, Any]]) -> float:
    score = 0.0
    for code in range(8):
        values = np.array(
            [record["median_lab"] for record in records if record["target"] == code]
        )
        center = np.median(values, axis=0)
        distance = np.linalg.norm(values - center, axis=1)
        score += float(np.median(distance) + np.percentile(distance, 90))
    return score


def _select_orientation(
    base_rectified: np.ndarray, template: list[dict[str, Any]]
) -> tuple[np.ndarray, list[dict[str, Any]], dict[str, Any]]:
    trials: list[dict[str, Any]] = []
    best: tuple[float, np.ndarray, list[dict[str, Any]], dict[str, bool]] | None = None
    for swap_controllers in (False, True):
        for flip_controller_1 in (False, True):
            for flip_controller_2 in (False, True):
                for flip_rows in (False, True):
                    settings = {
                        "swap_controllers": swap_controllers,
                        "flip_controller_1": flip_controller_1,
                        "flip_controller_2": flip_controller_2,
                        "flip_rows": flip_rows,
                    }
                    candidate = _oriented_rectified(base_rectified, **settings)
                    records = _sample_records(candidate, template)
                    score = _orientation_score(records)
                    trials.append({**settings, "within_code_dispersion_score": score})
                    if best is None or score < best[0]:
                        best = (score, candidate, records, settings)
    assert best is not None
    trials.sort(key=lambda trial: trial["within_code_dispersion_score"])
    return (
        best[1],
        best[2],
        {
            **best[3],
            "within_code_dispersion_score": best[0],
            "runner_up_score": trials[1]["within_code_dispersion_score"],
            "all_trials": trials,
        },
    )


def _spatial_residuals(records: list[dict[str, Any]]) -> None:
    for controller in (1, 2):
        for code in range(8):
            _spatial_residuals_for_group(records, controller, code)


def _spatial_residuals_for_group(
    records: list[dict[str, Any]], controller: int, code: int
) -> None:
    indices = [
        index
        for index, record in enumerate(records)
        if record["controller"] == controller and record["target"] == code
    ]
    x = np.array(
        [
            [
                1.0,
                records[index]["center_x"] / WIDTH,
                records[index]["center_y"] / HEIGHT,
                (records[index]["center_x"] / WIDTH) ** 2,
                (records[index]["center_y"] / HEIGHT) ** 2,
                records[index]["center_x"]
                * records[index]["center_y"]
                / (WIDTH * HEIGHT),
            ]
            for index in indices
        ]
    )
    y = np.array([records[index]["median_lab"] for index in indices])
    keep = np.ones(len(indices), dtype=bool)
    prediction = np.zeros_like(y)
    for _ in range(4):
        coefficients = np.linalg.lstsq(x[keep], y[keep], rcond=None)[0]
        prediction = x @ coefficients
        distance = np.linalg.norm(y - prediction, axis=1)
        median = float(np.median(distance[keep]))
        mad = float(np.median(np.abs(distance[keep] - median)))
        limit = max(3.0, median + 4.5 * max(mad, 0.25))
        next_keep = distance <= limit
        if np.array_equal(next_keep, keep):
            break
        keep = next_keep
    distance = np.linalg.norm(y - prediction, axis=1)
    median = float(np.median(distance))
    mad = float(np.median(np.abs(distance - median)))
    threshold = max(4.0, median + 5.0 * max(mad, 0.25))
    for local_index, record_index in enumerate(indices):
        records[record_index]["spatial_lab_residual_de76"] = float(
            distance[local_index]
        )
        records[record_index]["photo_outlier"] = bool(distance[local_index] > threshold)
        records[record_index]["photo_outlier_threshold_de76"] = threshold
        records[record_index]["spatial_model_group"] = {
            "controller": controller,
            "target_code": code,
        }


def analyze(photo_path: Path, roi_path: Path, output_dir: Path) -> dict[str, Any]:
    image = cv2.imread(str(photo_path), cv2.IMREAD_COLOR)
    if image is None:
        raise PhotoAnalysisError(f"cannot read {photo_path}")
    records = json.loads(roi_path.read_text("utf-8"))
    if not isinstance(records, list) or len(records) != 528:
        raise PhotoAnalysisError("ROI map must contain exactly 528 entries")
    matrix, geometry = _logical_to_photo(_cell_contours(image))
    inverse = np.linalg.inv(matrix)
    base_rectified = cv2.warpPerspective(image, inverse, (WIDTH, HEIGHT))
    rectified, records, orientation = _select_orientation(base_rectified, records)
    _spatial_residuals(records)
    candidates = sorted(
        (record for record in records if record["photo_outlier"]),
        key=lambda record: record["spatial_lab_residual_de76"],
        reverse=True,
    )
    summaries: list[dict[str, Any]] = []
    for code in range(8):
        group = [record for record in records if record["target"] == code]
        residuals = np.array([record["spatial_lab_residual_de76"] for record in group])
        summaries.append(
            {
                "target_code": code,
                "roi_count": len(group),
                "residual_de76_median": float(np.median(residuals)),
                "residual_de76_p95": float(np.percentile(residuals, 95)),
                "residual_de76_max": float(residuals.max()),
                "outlier_count": sum(bool(record["photo_outlier"]) for record in group),
            }
        )
    annotated = rectified.copy()
    for record in candidates:
        cv2.rectangle(
            annotated,
            (int(record["x0"]), int(record["y0"])),
            (int(record["x1_exclusive"] - 1), int(record["y1_exclusive"] - 1)),
            (255, 0, 255),
            2,
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    rectified_path = output_dir / "target-photo-rectified.png"
    annotated_path = output_dir / "target-photo-outliers.png"
    cv2.imwrite(str(rectified_path), rectified)
    cv2.imwrite(str(annotated_path), annotated)
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "mf1750-ec5-single-pixel-cube-camera-relative-photo-analysis",
        "source_photo": {
            "path": str(photo_path),
            "bytes": photo_path.stat().st_size,
            "sha256": _sha256(photo_path),
            "width": int(image.shape[1]),
            "height": int(image.shape[0]),
        },
        "geometry": geometry,
        "orientation": orientation,
        "method": {
            "perspective_rectified": True,
            "roi_count": 528,
            "uniform_roi_inner_crop_fraction": 0.56,
            "comparison": "within-target-code Lab residual after quadratic spatial trend",
            "calibrated_physical_colour": False,
        },
        "target_code_summaries": summaries,
        "candidate_count": len(candidates),
        "candidates": [
            {
                key: record[key]
                for key in (
                    "roi_index",
                    "controller",
                    "row",
                    "column",
                    "kind",
                    "recipe_index",
                    "source",
                    "mid",
                    "target",
                    "median_rgb",
                    "median_lab",
                    "spatial_lab_residual_de76",
                    "photo_outlier_threshold_de76",
                )
            }
            for record in candidates
        ],
        "interpretation": (
            "PHOTO_CANDIDATES_REQUIRE_REPEAT_AND_CONTROL; absence of candidates is "
            "not absolute colour proof"
            if candidates
            else "NO_CAMERA_RELATIVE_WITHIN_CODE_OUTLIER_IN_THIS_PHOTO"
        ),
        "artifacts": {
            "rectified": str(rectified_path),
            "outlier_overlay": str(annotated_path),
        },
    }
    report_path = output_dir / "target-photo-analysis.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), "utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--photo", type=Path, required=True)
    parser.add_argument("--roi-map", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.photo, args.roi_map, args.output_dir)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
