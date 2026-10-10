#!/usr/bin/env python3
"""Camera-relative analysis of the MF1750 red/pink V2 dual 8x8 grid.

The red/pink V2 firmware renders the same logical 8-by-8 recipe lattice on
both 512-pixel controllers.  This module detects enough coloured rectangles
to fit that frozen geometry, rectifies the photograph, and samples every
logical cell (including cells whose colour is too close to the separator to
form a contour).

Results are deliberately camera-relative.  They do not establish absolute
colour, a new physical hue, the state of the whole panel edge, or persistence.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any

import cv2
import numpy as np


LOGICAL_WIDTH = 1024
LOGICAL_HEIGHT = 600
CONTROLLER_WIDTH = 512
GRID_ROWS = 8
GRID_COLUMNS = 8
GRID_X0 = 20
GRID_Y0 = 40
CELL_WIDTH = 52
CELL_HEIGHT = 58
GAP_X = 8
GAP_Y = 8
CELL_STEP_X = CELL_WIDTH + GAP_X
CELL_STEP_Y = CELL_HEIGHT + GAP_Y
INNER_CROP_FRACTION = 0.54
_ORDINAL_RE = re.compile(r"camera-action-(\d{2})", re.IGNORECASE)
_THRESHOLDS = (30, 35, 40, 45, 50, 55, 60)
_EDGE_CANNY_THRESHOLDS = ((15, 45), (20, 60), (25, 75), (30, 90), (40, 120))
_EDGE_DETECTION_CONFIGS = (
    ("camera-lab-three-channel-or", (5, 15)),
    *(("grayscale-luminance", item) for item in _EDGE_CANNY_THRESHOLDS),
)
_SATURATION_DETECTION_METHOD = "hsv-saturation-contours-v1"
_EDGE_DETECTION_METHOD = "strict-canny-closed-cell-contours-v1"


class GridPhotoAnalysisError(RuntimeError):
    """Raised when a photograph cannot support the requested grid analysis."""


@dataclass(frozen=True)
class _Rectangle:
    center_x: float
    center_y: float
    width: float
    height: float
    area: float
    rectangularity: float


@dataclass
class _GeometryFit:
    homography: np.ndarray
    rectangles: list[_Rectangle]
    threshold: int | None
    ordinal: int | None
    visible_columns_per_side: int
    assignments: list[dict[str, Any]]
    row_centers: list[float]
    side_split_x: float
    reprojection_errors: np.ndarray
    inlier_mask: np.ndarray
    mapping_basis: str
    detection_method: str = _SATURATION_DETECTION_METHOD
    edge_canny_thresholds: tuple[int, int] | None = None
    edge_colour_space: str | None = None


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _logical_center(controller: int, row: int, column: int) -> tuple[float, float]:
    return (
        controller * CONTROLLER_WIDTH
        + GRID_X0
        + column * CELL_STEP_X
        + CELL_WIDTH / 2.0,
        GRID_Y0 + row * CELL_STEP_Y + CELL_HEIGHT / 2.0,
    )


def _logical_bounds(
    controller: int, row: int, column: int
) -> tuple[int, int, int, int]:
    x0 = controller * CONTROLLER_WIDTH + GRID_X0 + column * CELL_STEP_X
    y0 = GRID_Y0 + row * CELL_STEP_Y
    return x0, y0, x0 + CELL_WIDTH, y0 + CELL_HEIGHT


def _decode_jpeg(path: Path) -> tuple[bytes, np.ndarray]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise GridPhotoAnalysisError(f"cannot read photo: {path}") from exc
    image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        raise GridPhotoAnalysisError(f"photo is not a decodable colour image: {path}")
    return payload, image


def _infer_ordinal(path: Path, requested: int | None) -> int | None:
    if requested is not None:
        if requested not in (2, 3, 4, 5):
            raise GridPhotoAnalysisError("ordinal must be one of 2, 3, 4, or 5")
        return requested
    match = _ORDINAL_RE.search(path.stem)
    if match is None:
        return None
    ordinal = int(match.group(1))
    return ordinal if ordinal in (2, 3, 4, 5) else None


def _detect_rectangles(
    image: np.ndarray, saturation_threshold: int
) -> list[_Rectangle]:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    mask = ((saturation > saturation_threshold) & (value > 18)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        np.ones((3, 3), dtype=np.uint8),
    )
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    image_area = float(image.shape[0] * image.shape[1])
    min_dimension = float(min(image.shape[:2]))
    result: list[_Rectangle] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        x, y, width, height = cv2.boundingRect(contour)
        rectangularity = area / max(float(width * height), 1.0)
        aspect = width / max(float(height), 1.0)
        if not image_area * 0.00032 < area < image_area * 0.0055:
            continue
        if not min_dimension * 0.019 < min(width, height):
            continue
        if not max(width, height) < min_dimension * 0.16:
            continue
        if not 0.43 < aspect < 1.85 or rectangularity < 0.67:
            continue
        result.append(
            _Rectangle(
                center_x=x + width / 2.0,
                center_y=y + height / 2.0,
                width=float(width),
                height=float(height),
                area=area,
                rectangularity=rectangularity,
            )
        )
    return result


def _detect_edge_rectangles(
    image: np.ndarray,
    canny_thresholds: tuple[int, int],
    colour_space: str,
) -> list[_Rectangle]:
    """Detect closed cell outlines when hue/chroma cannot separate the cells.

    This is intentionally a strict fallback. It keeps the original size and
    aspect envelope, requires a closed rectangular contour, and de-duplicates
    the inner/outer Canny contours before any lattice fitting. The caller
    subsequently requires an exact 2x8x8 assignment and a tighter homography
    gate than the general camera-relative readout.
    """

    low, high = canny_thresholds
    if colour_space == "camera-lab-three-channel-or":
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        edges = np.zeros(image.shape[:2], dtype=np.uint8)
        for channel in range(3):
            blurred = cv2.GaussianBlur(lab[:, :, channel], (3, 3), 0)
            edges = cv2.bitwise_or(edges, cv2.Canny(blurred, low, high))
    elif colour_space == "grayscale-luminance":
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, low, high)
        edges = cv2.dilate(edges, np.ones((3, 3), dtype=np.uint8), iterations=1)
    else:  # pragma: no cover - internal configuration invariant
        raise GridPhotoAnalysisError(f"unknown edge colour space {colour_space!r}")
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    image_area = float(image.shape[0] * image.shape[1])
    min_dimension = float(min(image.shape[:2]))
    candidates: list[_Rectangle] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        x, y, width, height = cv2.boundingRect(contour)
        rectangularity = area / max(float(width * height), 1.0)
        aspect = width / max(float(height), 1.0)
        if colour_space == "camera-lab-three-channel-or":
            if not image_area / 3000.0 < area < image_area / 300.0:
                continue
            if not min_dimension * 0.020 < min(width, height):
                continue
            if not max(width, height) < min_dimension * 0.080:
                continue
            if not 0.55 < aspect < 1.60 or rectangularity < 0.65:
                continue
        else:
            if not image_area * 0.00032 < area < image_area * 0.0055:
                continue
            if not min_dimension * 0.019 < min(width, height):
                continue
            if not max(width, height) < min_dimension * 0.16:
                continue
            if not 0.43 < aspect < 1.85 or rectangularity < 0.55:
                continue
        if colour_space == "camera-lab-three-channel-or":
            moments = cv2.moments(contour)
            if abs(float(moments["m00"])) <= 1e-9:
                continue
            center_x = float(moments["m10"] / moments["m00"])
            center_y = float(moments["m01"] / moments["m00"])
        else:
            center_x = x + width / 2.0
            center_y = y + height / 2.0
        candidates.append(
            _Rectangle(
                center_x=center_x,
                center_y=center_y,
                width=float(width),
                height=float(height),
                area=area,
                rectangularity=rectangularity,
            )
        )

    # A dilated closed edge normally yields nearly coincident inner and outer
    # contours. Retain the larger one while keeping the radius far below one
    # physical cell pitch at both 1080p and 4000x3000.
    if colour_space == "camera-lab-three-channel-or":
        # LAB edges yield nested contours for the same physical patch. Build
        # connected 15-pixel center clusters, then average their moment
        # centroids and dimensions. Picking only the largest bounding box
        # biases the center enough to lose the strict high-resolution
        # homography residual gate.
        parents = list(range(len(candidates)))

        def find(index: int) -> int:
            while parents[index] != index:
                parents[index] = parents[parents[index]]
                index = parents[index]
            return index

        def union(left: int, right: int) -> None:
            left_root, right_root = find(left), find(right)
            if left_root != right_root:
                parents[right_root] = left_root

        for left, candidate in enumerate(candidates):
            for right in range(left):
                prior = candidates[right]
                if (
                    math.hypot(
                        candidate.center_x - prior.center_x,
                        candidate.center_y - prior.center_y,
                    )
                    <= 15.0
                ):
                    union(left, right)
        grouped: dict[int, list[_Rectangle]] = {}
        for index, candidate in enumerate(candidates):
            grouped.setdefault(find(index), []).append(candidate)
        return [
            _Rectangle(
                center_x=float(np.mean([item.center_x for item in group])),
                center_y=float(np.mean([item.center_y for item in group])),
                width=float(np.mean([item.width for item in group])),
                height=float(np.mean([item.height for item in group])),
                area=float(np.mean([item.area for item in group])),
                rectangularity=float(np.mean([item.rectangularity for item in group])),
            )
            for group in grouped.values()
        ]

    candidates.sort(key=lambda rectangle: rectangle.area, reverse=True)
    minimum_center_separation = max(12.0, min_dimension * 0.012)
    result: list[_Rectangle] = []
    for candidate in candidates:
        if all(
            math.hypot(
                candidate.center_x - prior.center_x,
                candidate.center_y - prior.center_y,
            )
            > minimum_center_separation
            for prior in result
        ):
            result.append(candidate)
    return result


def _cluster_rows(rectangles: list[_Rectangle]) -> tuple[list[float], list[int]]:
    if len(rectangles) < 32:
        raise GridPhotoAnalysisError(
            f"only {len(rectangles)} plausible coloured rectangles detected"
        )
    median_height = float(np.median([rectangle.height for rectangle in rectangles]))
    maximum_gap = max(12.0, median_height * 0.54)
    indexed = sorted(enumerate(rectangles), key=lambda item: item[1].center_y)
    groups: list[list[tuple[int, _Rectangle]]] = [[indexed[0]]]
    for item in indexed[1:]:
        if item[1].center_y - groups[-1][-1][1].center_y > maximum_gap:
            groups.append([item])
        else:
            groups[-1].append(item)
    groups = [group for group in groups if len(group) >= 4]
    if len(groups) != GRID_ROWS:
        raise GridPhotoAnalysisError(
            f"detected {len(groups)} supported grid rows instead of 8"
        )
    centers = [
        float(np.median([item[1].center_y for item in group])) for group in groups
    ]
    labels = [-1] * len(rectangles)
    for row, group in enumerate(groups):
        for index, _ in group:
            labels[index] = row
    if any(label < 0 for label in labels):
        # Small isolated shapes are harmless; bind them to the nearest row and
        # let the homography residual reject them later.
        for index, rectangle in enumerate(rectangles):
            if labels[index] < 0:
                labels[index] = int(
                    np.argmin(np.abs(np.array(centers) - rectangle.center_y))
                )
    return centers, labels


def _cluster_edge_rows(
    rectangles: list[_Rectangle],
) -> tuple[list[float], list[int]]:
    """Cluster strict edge candidates into eight perspective row bands.

    The legacy saturation path deliberately keeps its historical gap-based
    clustering unchanged. High-resolution 4:3 captures can have enough
    horizontal keystone that adjacent row y-ranges overlap; deterministic
    one-dimensional k-means is used only by the exact-support edge fallback.
    """

    if len(rectangles) < 64:
        raise GridPhotoAnalysisError(
            f"only {len(rectangles)} plausible closed edge rectangles detected"
        )
    values = np.float32([[rectangle.center_y] for rectangle in rectangles])
    cv2.setRNGSeed(1750)
    _compactness, raw_labels, raw_centers = cv2.kmeans(
        values,
        GRID_ROWS,
        None,
        (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.01),
        20,
        cv2.KMEANS_PP_CENTERS,
    )
    order = np.argsort(raw_centers[:, 0])
    remap = {int(raw): row for row, raw in enumerate(order)}
    labels = [remap[int(raw)] for raw in raw_labels[:, 0]]
    centers = [float(raw_centers[index, 0]) for index in order]
    counts = [labels.count(row) for row in range(GRID_ROWS)]
    if min(counts) < 8:
        raise GridPhotoAnalysisError(
            f"closed edge row support is too sparse: {counts!r}"
        )
    if any(right <= left for left, right in zip(centers, centers[1:])):
        raise GridPhotoAnalysisError("closed edge row centers are not ordered")
    return centers, labels


def _side_split(rectangles: list[_Rectangle]) -> tuple[float, list[int]]:
    values = np.float32([[rectangle.center_x] for rectangle in rectangles])
    cv2.setRNGSeed(1750)
    _, labels, centers = cv2.kmeans(
        values,
        2,
        None,
        (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.01),
        20,
        cv2.KMEANS_PP_CENTERS,
    )
    order = np.argsort(centers[:, 0])
    remap = {int(order[0]): 0, int(order[1]): 1}
    side_labels = [remap[int(label)] for label in labels[:, 0]]
    left = [
        rectangle.center_x
        for rectangle, label in zip(rectangles, side_labels, strict=True)
        if label == 0
    ]
    right = [
        rectangle.center_x
        for rectangle, label in zip(rectangles, side_labels, strict=True)
        if label == 1
    ]
    if min(len(left), len(right)) < 20 or max(left) >= min(right):
        raise GridPhotoAnalysisError("could not separate the two controller grids")
    return (max(left) + min(right)) / 2.0, side_labels


def _row_side_members(
    rectangles: list[_Rectangle],
    row_labels: list[int],
    side_labels: list[int],
) -> dict[tuple[int, int], list[int]]:
    groups = {(row, side): [] for row in range(8) for side in range(2)}
    for index, (row, side) in enumerate(zip(row_labels, side_labels, strict=True)):
        groups[(row, side)].append(index)
    for indices in groups.values():
        indices.sort(key=lambda index: rectangles[index].center_x)
    return groups


def _visible_columns(
    groups: dict[tuple[int, int], list[int]], ordinal: int | None
) -> int:
    maximum = max(len(indices) for indices in groups.values())
    if ordinal == 2:
        return 7
    if ordinal in (3, 4, 5):
        return 8
    if maximum >= 8:
        return 8
    if maximum >= 7:
        return 7
    raise GridPhotoAnalysisError(
        "no row contains enough cells to initialize the lattice"
    )


def _initial_correspondences(
    rectangles: list[_Rectangle],
    groups: dict[tuple[int, int], list[int]],
    visible_columns: int,
    ordinal: int | None,
) -> tuple[np.ndarray, np.ndarray, str]:
    logical: list[tuple[float, float]] = []
    photo: list[tuple[float, float]] = []
    complete_groups = 0
    for row in range(8):
        for controller in range(2):
            indices = groups[(row, controller)]
            if len(indices) != visible_columns:
                continue
            complete_groups += 1
            for column, index in enumerate(indices):
                logical.append(_logical_center(controller, row, column))
                rectangle = rectangles[index]
                photo.append((rectangle.center_x, rectangle.center_y))
    if len(logical) < 24 or complete_groups < 4:
        raise GridPhotoAnalysisError(
            "too few complete row/controller groups to initialize homography"
        )
    if visible_columns == 7:
        basis = (
            "ordinal-2 frozen source layout: saturated columns map in order to "
            "source codes 0..6; source code 7 is inferred geometrically"
            if ordinal == 2
            else "seven visible columns provisionally mapped to logical columns 0..6"
        )
    else:
        basis = "eight ordered visible columns mapped to frozen logical columns 0..7"
    return np.float32(logical), np.float32(photo), basis


def _fit_homography(
    logical: np.ndarray, photo: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    homography, mask = cv2.findHomography(logical, photo, cv2.RANSAC, 5.0)
    if homography is None or mask is None:
        raise GridPhotoAnalysisError("homography fit failed")
    if int(mask[:, 0].sum()) < max(20, int(0.65 * len(logical))):
        raise GridPhotoAnalysisError("homography has too few inliers")
    return homography, mask[:, 0].astype(bool)


def _assign_with_homography(
    rectangles: list[_Rectangle], homography: np.ndarray
) -> list[dict[str, Any]]:
    inverse = np.linalg.inv(homography)
    photo = np.float32(
        [[[rectangle.center_x, rectangle.center_y] for rectangle in rectangles]]
    )
    logical = cv2.perspectiveTransform(photo, inverse)[0]
    assignments_by_cell: dict[tuple[int, int, int], dict[str, Any]] = {}
    for rectangle_index, (logical_x, logical_y) in enumerate(logical):
        controller = int(logical_x >= CONTROLLER_WIDTH)
        local_x = float(logical_x - controller * CONTROLLER_WIDTH)
        column = int(round((local_x - (GRID_X0 + CELL_WIDTH / 2.0)) / CELL_STEP_X))
        row = int(
            round((float(logical_y) - (GRID_Y0 + CELL_HEIGHT / 2.0)) / CELL_STEP_Y)
        )
        if not (0 <= controller < 2 and 0 <= row < 8 and 0 <= column < 8):
            continue
        expected = np.float32(
            [
                [
                    [
                        _logical_center(controller, row, column)[0],
                        _logical_center(controller, row, column)[1],
                    ]
                ]
            ]
        )
        projected = cv2.perspectiveTransform(expected, homography)[0, 0]
        rectangle = rectangles[rectangle_index]
        error = float(
            np.linalg.norm(
                projected - np.float32([rectangle.center_x, rectangle.center_y])
            )
        )
        scale = max(1.0, min(rectangle.width, rectangle.height))
        if error > max(8.0, 0.28 * scale):
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
        prior = assignments_by_cell.get(key)
        if prior is None or error < prior["reprojection_error_px"]:
            assignments_by_cell[key] = record
    return sorted(
        assignments_by_cell.values(),
        key=lambda item: (item["controller"], item["row"], item["column"]),
    )


def _refine_homography(
    rectangles: list[_Rectangle], homography: np.ndarray
) -> tuple[np.ndarray, list[dict[str, Any]], np.ndarray, np.ndarray]:
    assignments: list[dict[str, Any]] = []
    for _ in range(3):
        assignments = _assign_with_homography(rectangles, homography)
        if len(assignments) < 32:
            raise GridPhotoAnalysisError("too few unique grid-cell assignments")
        logical = np.float32(
            [
                _logical_center(item["controller"], item["row"], item["column"])
                for item in assignments
            ]
        )
        photo = np.float32([item["photo_center"] for item in assignments])
        homography, inliers = _fit_homography(logical, photo)
    projected = cv2.perspectiveTransform(logical[None, :, :], homography)[0]
    errors = np.linalg.norm(projected - photo, axis=1)
    return homography, assignments, errors, inliers


def _fit_geometry(
    image: np.ndarray, ordinal: int | None, saturation_threshold: int
) -> _GeometryFit:
    rectangles = _detect_rectangles(image, saturation_threshold)
    row_centers, row_labels = _cluster_rows(rectangles)
    split_x, side_labels = _side_split(rectangles)
    groups = _row_side_members(rectangles, row_labels, side_labels)
    visible_columns = _visible_columns(groups, ordinal)
    logical, photo, basis = _initial_correspondences(
        rectangles, groups, visible_columns, ordinal
    )
    homography, _ = _fit_homography(logical, photo)
    homography, assignments, errors, inliers = _refine_homography(
        rectangles, homography
    )
    return _GeometryFit(
        homography=homography,
        rectangles=rectangles,
        threshold=saturation_threshold,
        ordinal=ordinal,
        visible_columns_per_side=visible_columns,
        assignments=assignments,
        row_centers=row_centers,
        side_split_x=split_x,
        reprojection_errors=errors,
        inlier_mask=inliers,
        mapping_basis=basis,
    )


def _fit_edge_geometry(
    image: np.ndarray,
    ordinal: int | None,
    canny_thresholds: tuple[int, int],
    colour_space: str,
) -> _GeometryFit:
    rectangles = _detect_edge_rectangles(image, canny_thresholds, colour_space)
    row_centers, row_labels = _cluster_edge_rows(rectangles)
    split_x, side_labels = _side_split(rectangles)
    groups = _row_side_members(rectangles, row_labels, side_labels)
    visible_columns = _visible_columns(groups, ordinal)
    logical, photo, legacy_basis = _initial_correspondences(
        rectangles, groups, visible_columns, ordinal
    )
    homography, _ = _fit_homography(logical, photo)
    homography, assignments, errors, inliers = _refine_homography(
        rectangles, homography
    )
    basis = (
        "strict closed-edge 2x8x8 fallback; both controllers require exact "
        f"64-cell support after deduplication; {legacy_basis}"
    )
    return _GeometryFit(
        homography=homography,
        rectangles=rectangles,
        threshold=None,
        ordinal=ordinal,
        visible_columns_per_side=visible_columns,
        assignments=assignments,
        row_centers=row_centers,
        side_split_x=split_x,
        reprojection_errors=errors,
        inlier_mask=inliers,
        mapping_basis=basis,
        detection_method=_EDGE_DETECTION_METHOD,
        edge_canny_thresholds=canny_thresholds,
        edge_colour_space=colour_space,
    )


def _choose_geometry(image: np.ndarray, ordinal: int | None) -> _GeometryFit:
    attempts: list[tuple[tuple[float, float, float], _GeometryFit]] = []
    failures: list[str] = []
    for threshold in _THRESHOLDS:
        try:
            fit = _fit_geometry(image, ordinal, threshold)
        except (GridPhotoAnalysisError, cv2.error, np.linalg.LinAlgError) as exc:
            failures.append(f"S>{threshold}: {exc}")
            continue
        unique_support = len(fit.assignments)
        inlier_fraction = float(np.mean(fit.inlier_mask))
        rmse = float(np.sqrt(np.mean(fit.reprojection_errors**2)))
        score = (float(unique_support), inlier_fraction, -rmse)
        attempts.append((score, fit))
    if attempts:
        attempts.sort(key=lambda item: item[0], reverse=True)
        return attempts[0][1]

    # Do not relax or perturb the historical saturation path. Only after it
    # has failed completely may a closed-edge fit qualify, and that fit must
    # cover every cell on both controllers with G-1-grade residuals.
    edge_attempts: list[tuple[tuple[float, float, float], _GeometryFit]] = []
    edge_failures: list[str] = []
    for colour_space, canny_thresholds in _EDGE_DETECTION_CONFIGS:
        try:
            fit = _fit_edge_geometry(image, ordinal, canny_thresholds, colour_space)
            support_by_controller = [
                sum(item["controller"] == controller for item in fit.assignments)
                for controller in range(2)
            ]
            inlier_errors = fit.reprojection_errors[fit.inlier_mask]
            inlier_fraction = float(np.mean(fit.inlier_mask))
            rmse = float(np.sqrt(np.mean(inlier_errors**2)))
            p95 = float(np.percentile(inlier_errors, 95))
            if len(fit.assignments) != 128 or support_by_controller != [64, 64]:
                raise GridPhotoAnalysisError(
                    "closed edge fallback lacks exact 64+64 cell support"
                )
            if inlier_fraction != 1.0 or rmse > 2.0 or p95 > 3.0:
                raise GridPhotoAnalysisError(
                    "closed edge fallback exceeds the exact G-1 residual gate"
                )
        except (GridPhotoAnalysisError, cv2.error, np.linalg.LinAlgError) as exc:
            edge_failures.append(f"{colour_space}:Canny{canny_thresholds}: {exc}")
            continue
        score = (float(len(fit.assignments)), inlier_fraction, -rmse)
        edge_attempts.append((score, fit))
    if edge_attempts:
        edge_attempts.sort(key=lambda item: item[0], reverse=True)
        return edge_attempts[0][1]

    saturation_detail = "; ".join(failures[-3:])
    edge_detail = "; ".join(edge_failures[-3:])
    raise GridPhotoAnalysisError(
        "no saturation threshold fit the 8x8 grids and no strict closed-edge "
        f"fallback qualified: saturation=[{saturation_detail}]; edge=[{edge_detail}]"
    )


def _lab_from_rgb(rgb: np.ndarray) -> np.ndarray:
    sample = np.uint8(np.clip(np.rint(rgb), 0, 255)).reshape(1, 1, 3)
    lab = cv2.cvtColor(sample, cv2.COLOR_RGB2LAB)[0, 0].astype(np.float64)
    lab[0] *= 100.0 / 255.0
    lab[1:] -= 128.0
    return lab


def _hsv_from_rgb(rgb: np.ndarray) -> np.ndarray:
    sample = np.uint8(np.clip(np.rint(rgb), 0, 255)).reshape(1, 1, 3)
    hsv = cv2.cvtColor(sample, cv2.COLOR_RGB2HSV)[0, 0].astype(np.float64)
    return np.array([hsv[0] * 2.0, hsv[1] * 100.0 / 255.0, hsv[2] * 100.0 / 255.0])


def _projected_cell_geometry(
    homography: np.ndarray, controller: int, row: int, column: int
) -> np.ndarray:
    x0, y0, x1, y1 = _logical_bounds(controller, row, column)
    logical = np.float32([[[x0, y0], [x1, y0], [x1, y1], [x0, y1]]])
    return cv2.perspectiveTransform(logical, homography)[0]


def _sample_cells(
    image: np.ndarray, fit: _GeometryFit
) -> tuple[np.ndarray, list[dict[str, Any]], dict[str, Any]]:
    inverse = np.linalg.inv(fit.homography)
    rectified = cv2.warpPerspective(
        image,
        inverse,
        (LOGICAL_WIDTH, LOGICAL_HEIGHT),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )
    valid_source = np.full(image.shape[:2], 255, dtype=np.uint8)
    validity = cv2.warpPerspective(
        valid_source,
        inverse,
        (LOGICAL_WIDTH, LOGICAL_HEIGHT),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    detected_keys = {
        (item["controller"], item["row"], item["column"]): item
        for item in fit.assignments
    }
    records: list[dict[str, Any]] = []
    validity_fractions: list[float] = []
    projected_min_width = math.inf
    projected_min_height = math.inf
    all_cell_corners_inside = True
    height, width = image.shape[:2]
    for controller, row, column in itertools.product(range(2), range(8), range(8)):
        x0, y0, x1, y1 = _logical_bounds(controller, row, column)
        margin_x = int(round(CELL_WIDTH * (1.0 - INNER_CROP_FRACTION) / 2.0))
        margin_y = int(round(CELL_HEIGHT * (1.0 - INNER_CROP_FRACTION) / 2.0))
        patch = rectified[y0 + margin_y : y1 - margin_y, x0 + margin_x : x1 - margin_x]
        valid_patch = validity[
            y0 + margin_y : y1 - margin_y, x0 + margin_x : x1 - margin_x
        ]
        if patch.size == 0:
            raise GridPhotoAnalysisError(
                "logical cell produced an empty sampling patch"
            )
        valid = valid_patch > 0
        valid_fraction = float(np.mean(valid))
        validity_fractions.append(valid_fraction)
        if not np.any(valid):
            pixels_rgb = np.empty((0, 3), dtype=np.float64)
        else:
            pixels_rgb = patch[valid][:, ::-1].astype(np.float64)
        if len(pixels_rgb) < 64:
            raise GridPhotoAnalysisError(
                f"cell C{controller} R{row} K{column} has too few visible pixels"
            )
        median_rgb = np.median(pixels_rgb, axis=0)
        mad_rgb = np.median(np.abs(pixels_rgb - median_rgb), axis=0)
        lab = _lab_from_rgb(median_rgb)
        hsv = _hsv_from_rgb(median_rgb)
        projected = _projected_cell_geometry(fit.homography, controller, row, column)
        top_width = float(np.linalg.norm(projected[1] - projected[0]))
        bottom_width = float(np.linalg.norm(projected[2] - projected[3]))
        left_height = float(np.linalg.norm(projected[3] - projected[0]))
        right_height = float(np.linalg.norm(projected[2] - projected[1]))
        projected_min_width = min(projected_min_width, top_width, bottom_width)
        projected_min_height = min(projected_min_height, left_height, right_height)
        corners_inside = bool(
            np.all(projected[:, 0] >= -1.0)
            and np.all(projected[:, 0] <= width)
            and np.all(projected[:, 1] >= -1.0)
            and np.all(projected[:, 1] <= height)
        )
        all_cell_corners_inside &= corners_inside
        support = detected_keys.get((controller, row, column))
        record: dict[str, Any] = {
            "cell_id": f"C{controller}-R{row}-K{column}",
            "controller": controller,
            "row": row,
            "column": column,
            "recipe_id": f"REDPINK-A{column}-B{row}-A0",
            "logical_bounds": [x0, y0, x1, y1],
            "projected_photo_corners": projected.astype(float).tolist(),
            "all_corners_inside_photo": corners_inside,
            "inner_patch_valid_fraction": valid_fraction,
            "contour_support_detected": support is not None,
            "contour_reprojection_error_px": (
                None if support is None else support["reprojection_error_px"]
            ),
            "robust_rgb_median": median_rgb.astype(float).tolist(),
            "robust_rgb_mad": mad_rgb.astype(float).tolist(),
            "camera_relative_lab": lab.astype(float).tolist(),
            "camera_relative_hsv": {
                "hue_degrees": float(hsv[0]),
                "saturation_percent": float(hsv[1]),
                "value_percent": float(hsv[2]),
            },
        }
        if fit.detection_method == _EDGE_DETECTION_METHOD and support is not None:
            rectangle = fit.rectangles[support["rectangle_index"]]
            record["contour_observation"] = {
                "detection_method": fit.detection_method,
                "edge_colour_space": fit.edge_colour_space,
                "edge_canny_thresholds": list(fit.edge_canny_thresholds or ()),
                "photo_center": [rectangle.center_x, rectangle.center_y],
                "width_px": rectangle.width,
                "height_px": rectangle.height,
                "contour_area_px2": rectangle.area,
                "rectangularity": rectangle.rectangularity,
                "independent_detected_contour": True,
                "not_geometry_inferred": True,
            }
        records.append(record)
    sampling = {
        "inner_crop_fraction": INNER_CROP_FRACTION,
        "minimum_inner_patch_valid_fraction": float(min(validity_fractions)),
        "all_cell_corners_inside_photo": all_cell_corners_inside,
        "minimum_projected_cell_width_px": projected_min_width,
        "minimum_projected_cell_height_px": projected_min_height,
    }
    return rectified, records, sampling


def _axis_summaries(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for controller in range(2):
        for axis in ("row", "column"):
            for index in range(8):
                group = [
                    cell
                    for cell in cells
                    if cell["controller"] == controller and cell[axis] == index
                ]
                labs = np.array([cell["camera_relative_lab"] for cell in group])
                center = np.median(labs, axis=0)
                distances = np.linalg.norm(labs - center, axis=1)
                summaries.append(
                    {
                        "controller": controller,
                        "axis": axis,
                        "index": index,
                        "cell_count": len(group),
                        "camera_relative_lab_median": center.astype(float).tolist(),
                        "lightness_range": float(np.ptp(labs[:, 0])),
                        "de76_to_axis_median_median": float(np.median(distances)),
                        "de76_to_axis_median_max": float(np.max(distances)),
                    }
                )
    return summaries


def _apply_spatial_models(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove only a smooth quadratic camera/lighting trend per controller.

    This is a conservative observer aid, not a physical-panel correction.  Raw
    Lab values remain in every cell and the report explicitly records both the
    fitted trend and residual.  A coherent recipe change can itself be smooth,
    so residuals are only candidate-screening evidence.
    """

    summaries: list[dict[str, Any]] = []
    for controller in range(2):
        group = [cell for cell in cells if cell["controller"] == controller]
        design = np.array(
            [
                [
                    1.0,
                    (cell["column"] - 3.5) / 3.5,
                    (cell["row"] - 3.5) / 3.5,
                    ((cell["column"] - 3.5) / 3.5) ** 2,
                    ((cell["row"] - 3.5) / 3.5) ** 2,
                    (cell["column"] - 3.5) * (cell["row"] - 3.5) / (3.5**2),
                ]
                for cell in group
            ],
            dtype=np.float64,
        )
        observed = np.array(
            [cell["camera_relative_lab"] for cell in group], dtype=np.float64
        )
        keep = np.ones(len(group), dtype=bool)
        prediction = np.zeros_like(observed)
        coefficients = np.zeros((design.shape[1], 3), dtype=np.float64)
        for _ in range(6):
            coefficients = np.linalg.lstsq(design[keep], observed[keep], rcond=None)[0]
            prediction = design @ coefficients
            distance = np.linalg.norm(observed - prediction, axis=1)
            median = float(np.median(distance[keep]))
            mad = float(np.median(np.abs(distance[keep] - median)))
            iterative_limit = max(3.0, median + 4.5 * max(0.20, mad))
            next_keep = distance <= iterative_limit
            if int(next_keep.sum()) < 48 or np.array_equal(next_keep, keep):
                break
            keep = next_keep
        coefficients = np.linalg.lstsq(design[keep], observed[keep], rcond=None)[0]
        prediction = design @ coefficients
        residual = observed - prediction
        distance = np.linalg.norm(residual, axis=1)
        median = float(np.median(distance))
        mad = float(np.median(np.abs(distance - median)))
        threshold = max(4.0, median + 6.0 * max(0.20, mad))
        for index, cell in enumerate(group):
            cell["smooth_spatial_trend_lab"] = prediction[index].astype(float).tolist()
            cell["spatial_residual_lab"] = residual[index].astype(float).tolist()
            cell["spatial_residual_de76"] = float(distance[index])
            cell["spatial_residual_lightness"] = float(residual[index, 0])
            cell["spatial_outlier_threshold_de76"] = threshold
            cell["obvious_spatial_outlier"] = bool(distance[index] > threshold)
        summaries.append(
            {
                "controller": controller,
                "model": "robust quadratic in normalized row and column",
                "terms": ["1", "column", "row", "column^2", "row^2", "column*row"],
                "fit_cell_count": int(keep.sum()),
                "residual_de76_median": median,
                "residual_de76_p95": float(np.percentile(distance, 95)),
                "residual_de76_max": float(np.max(distance)),
                "obvious_outlier_threshold_de76": threshold,
                "obvious_outlier_count": int(np.sum(distance > threshold)),
                "coefficients_by_term_for_lab": coefficients.astype(float).tolist(),
            }
        )
    return summaries


def _candidate_rankings(
    cells: list[dict[str, Any]], ordinal: int | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    controller_centers: dict[int, np.ndarray] = {}
    controller_scales: dict[int, float] = {}
    for controller in range(2):
        labs = np.array(
            [
                cell["camera_relative_lab"]
                for cell in cells
                if cell["controller"] == controller
            ]
        )
        center = np.median(labs, axis=0)
        lightness = labs[:, 0]
        mad = float(np.median(np.abs(lightness - np.median(lightness))))
        controller_centers[controller] = center
        controller_scales[controller] = max(1.0, 1.4826 * mad)
    ranked_cells: list[dict[str, Any]] = []
    by_key: dict[tuple[int, int, int], dict[str, Any]] = {}
    for cell in cells:
        controller = int(cell["controller"])
        lab = np.array(cell["camera_relative_lab"])
        center = controller_centers[controller]
        delta = lab - center
        de76 = float(np.linalg.norm(delta))
        lightness_z = float(delta[0] / controller_scales[controller])
        spatial_threshold = float(cell["spatial_outlier_threshold_de76"])
        spatial_de76 = float(cell["spatial_residual_de76"])
        score = spatial_de76 / max(spatial_threshold, 1.0)
        entry = {
            "cell_id": cell["cell_id"],
            "controller": controller,
            "row": cell["row"],
            "column": cell["column"],
            "recipe_id": cell["recipe_id"],
            "camera_relative_lightness_delta_from_controller_median": float(delta[0]),
            "camera_relative_lightness_robust_z": lightness_z,
            "camera_relative_de76_from_controller_median": de76,
            "spatial_residual_lightness": cell["spatial_residual_lightness"],
            "spatial_residual_de76": spatial_de76,
            "spatial_outlier_threshold_de76": spatial_threshold,
            "obvious_spatial_outlier": cell["obvious_spatial_outlier"],
            "candidate_score": score,
        }
        ranked_cells.append(entry)
        by_key[(controller, int(cell["row"]), int(cell["column"]))] = entry
    ranked_cells.sort(key=lambda entry: entry["candidate_score"], reverse=True)
    ranked_recipes: list[dict[str, Any]] = []
    for row in range(8):
        for column in range(8):
            left = by_key[(0, row, column)]
            right = by_key[(1, row, column)]
            scores = [left["candidate_score"], right["candidate_score"]]
            paired_obvious = bool(
                left["obvious_spatial_outlier"] and right["obvious_spatial_outlier"]
            )
            ranked_recipes.append(
                {
                    "recipe_id": f"REDPINK-A{column}-B{row}-A0",
                    "row": row,
                    "column": column,
                    "controller_cell_ids": [left["cell_id"], right["cell_id"]],
                    "controller_candidate_scores": scores,
                    "paired_candidate_score": float(np.mean(scores)),
                    "paired_obvious_spatial_outlier": paired_obvious,
                }
            )
    ranked_recipes.sort(key=lambda entry: entry["paired_candidate_score"], reverse=True)
    applicable = ordinal in (4, 5)
    obvious_cells = sum(
        bool(entry["obvious_spatial_outlier"]) for entry in ranked_cells
    )
    obvious_pairs = sum(
        bool(entry["paired_obvious_spatial_outlier"]) for entry in ranked_recipes
    )
    metadata = {
        "screening_applicable": applicable,
        "scope": (
            "camera-relative post-target history candidate ranking"
            if applicable
            else "diagnostic ranking only; source/middle actions intentionally vary colour"
        ),
        "score_definition": "spatial residual DE76 divided by its controller threshold",
        "obvious_spatial_outlier_cell_count": obvious_cells,
        "obvious_paired_recipe_count": obvious_pairs,
        "camera_relative_spatial_assessment": (
            "OBVIOUS_PAIRED_CELL_OUTLIER_BEYOND_SMOOTH_SPATIAL_TREND"
            if applicable and obvious_pairs
            else (
                "NO_OBVIOUS_PAIRED_CELL_OUTLIER_BEYOND_SMOOTH_SPATIAL_TREND"
                if applicable
                else "NOT_APPLICABLE_BEFORE_FIXED_TARGET_ACTION"
            )
        ),
        "not_a_claim_of": [
            "absolute colour",
            "new physical hue",
            "qualified brightness level",
            "persistence",
        ],
    }
    return ranked_cells, ranked_recipes, metadata


def _geometry_report(
    fit: _GeometryFit, image: np.ndarray, sampling: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    errors = fit.reprojection_errors
    inlier_errors = errors[fit.inlier_mask]
    support_by_controller = [
        sum(item["controller"] == controller for item in fit.assignments)
        for controller in range(2)
    ]
    expected_coloured_support = 112 if fit.ordinal == 2 else 128
    geometry = {
        "frozen_layout": {
            "logical_width": LOGICAL_WIDTH,
            "logical_height": LOGICAL_HEIGHT,
            "controller_width": CONTROLLER_WIDTH,
            "controllers": 2,
            "rows": GRID_ROWS,
            "columns_per_controller": GRID_COLUMNS,
            "grid_x0_local": GRID_X0,
            "grid_y0": GRID_Y0,
            "cell_width": CELL_WIDTH,
            "cell_height": CELL_HEIGHT,
            "gap_x": GAP_X,
            "gap_y": GAP_Y,
        },
        "saturation_contour_threshold": fit.threshold,
        "plausible_rectangle_count": len(fit.rectangles),
        "unique_cell_contour_support": len(fit.assignments),
        "expected_coloured_contour_support_for_action": expected_coloured_support,
        "support_fraction_of_action_expectation": min(
            1.0, len(fit.assignments) / expected_coloured_support
        ),
        "support_by_controller": support_by_controller,
        "detected_row_centers_photo_y": fit.row_centers,
        "controller_split_photo_x": fit.side_split_x,
        "visible_columns_used_to_initialize_each_side": fit.visible_columns_per_side,
        "mapping_basis": fit.mapping_basis,
        "homography_logical_to_photo": fit.homography.astype(float).tolist(),
        "homography_inliers": int(np.sum(fit.inlier_mask)),
        "homography_correspondences": len(fit.assignments),
        "homography_inlier_fraction": float(np.mean(fit.inlier_mask)),
        "homography_inlier_rmse_px": float(np.sqrt(np.mean(inlier_errors**2))),
        "homography_inlier_p95_px": float(np.percentile(inlier_errors, 95)),
        "sampling": sampling,
    }
    if fit.detection_method == _EDGE_DETECTION_METHOD:
        geometry.update(
            {
                "rectangle_detection_method": fit.detection_method,
                "saturation_contour_threshold": None,
                "edge_canny_thresholds": list(fit.edge_canny_thresholds or ()),
                "edge_colour_space": fit.edge_colour_space,
                "edge_fallback_exact_support_contract": {
                    "total_cells": 128,
                    "support_by_controller": [64, 64],
                    "homography_inlier_fraction": 1.0,
                    "maximum_inlier_rmse_px": 2.0,
                    "maximum_inlier_p95_px": 3.0,
                    "legacy_saturation_path_changed": False,
                },
            }
        )
    reasons: list[str] = []
    if len(fit.assignments) < int(0.72 * expected_coloured_support):
        reasons.append("insufficient coloured-cell contour support")
    if float(np.mean(fit.inlier_mask)) < 0.80:
        reasons.append("homography inlier fraction below 0.80")
    if float(np.sqrt(np.mean(inlier_errors**2))) > 5.0:
        reasons.append("homography RMSE exceeds 5 px")
    if sampling["minimum_inner_patch_valid_fraction"] < 0.98:
        reasons.append("one or more cell center patches are partly outside the photo")
    if not sampling["all_cell_corners_inside_photo"]:
        reasons.append("one or more complete cell rectangles are outside the photo")
    if sampling["minimum_projected_cell_width_px"] < 20.0:
        reasons.append("projected cells are too narrow for robust sampling")
    if sampling["minimum_projected_cell_height_px"] < 20.0:
        reasons.append("projected cells are too short for robust sampling")
    enough = not reasons
    judgement = {
        "enough_to_interpret_grid_camera_relatively": enough,
        "verdict": (
            "SUFFICIENT_CAMERA_RELATIVE_GRID_READOUT"
            if enough
            else "INSUFFICIENT_CAMERA_RELATIVE_GRID_READOUT"
        ),
        "blocking_reasons": reasons,
        "camera_relative_only": True,
        "limitations": [
            "not an absolute colour measurement",
            "not proof of a new physical hue or qualified brightness level",
            "not a full-panel-edge or persistence inspection",
            "candidate ranking requires repeat/control evidence before qualification",
        ],
        "photo_dimensions": [int(image.shape[1]), int(image.shape[0])],
    }
    return geometry, judgement


def analyze(photo_path: Path, *, ordinal: int | None = None) -> dict[str, Any]:
    """Analyze one JPEG without writing files or touching hardware."""

    photo_path = Path(photo_path)
    payload, image = _decode_jpeg(photo_path)
    resolved_ordinal = _infer_ordinal(photo_path, ordinal)
    fit = _choose_geometry(image, resolved_ordinal)
    _, cells, sampling = _sample_cells(image, fit)
    axis_summaries = _axis_summaries(cells)
    spatial_models = _apply_spatial_models(cells)
    cell_ranking, recipe_ranking, ranking_metadata = _candidate_rankings(
        cells, resolved_ordinal
    )
    geometry, judgement = _geometry_report(fit, image, sampling)
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "mf1750-redpink-v2-dual-8x8-camera-relative-grid-photo-analysis",
        "source_photo": {
            "path": str(photo_path),
            "bytes": len(payload),
            "sha256": _sha256_bytes(payload),
            "width": int(image.shape[1]),
            "height": int(image.shape[0]),
        },
        "campaign_layout": {
            "id": "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_V2",
            "action_ordinal": resolved_ordinal,
            "controllers_are_not_assumed_colour_equivalent": True,
        },
        "method": {
            "perspective_rectified": True,
            "all_128_logical_cells_sampled": True,
            "center_sampling": "per-channel median over inner 54 percent",
            "robust_spread": "per-channel median absolute deviation",
            "colour_spaces": ["camera RGB", "camera-relative CIE Lab", "HSV"],
            "physical_colour_calibrated": False,
        },
        "geometry_quality": geometry,
        "grid_judgement": judgement,
        "cells": cells,
        "row_column_differences": axis_summaries,
        "smooth_spatial_models": spatial_models,
        "candidate_ranking_metadata": ranking_metadata,
        "cell_candidate_ranking": cell_ranking,
        "recipe_candidate_ranking": recipe_ranking,
    }
    report["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": _sha256_bytes(_canonical_json(report)),
    }
    return report


def _write_exclusive(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        descriptor = os.open(path, flags, 0o644)
    except FileExistsError as exc:
        raise GridPhotoAnalysisError(
            f"refusing to overwrite existing output: {path}"
        ) from exc
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze the MF1750 red/pink V2 dual 8x8 grid photograph"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("--photo", type=Path, required=True)
    analyze_parser.add_argument("--ordinal", type=int, choices=(2, 3, 4, 5))
    analyze_parser.add_argument(
        "--output",
        type=Path,
        help="optional new JSON path; creation is O_EXCL and never overwrites",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = analyze(args.photo, ordinal=args.ordinal)
        payload = (
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False).encode(
                "utf-8"
            )
            + b"\n"
        )
        if args.output is not None:
            _write_exclusive(args.output, payload)
        sys.stdout.buffer.write(payload)
        return 0
    except GridPhotoAnalysisError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
