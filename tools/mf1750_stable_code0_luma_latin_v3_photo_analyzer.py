#!/usr/bin/env python3
"""Seal a camera-relative readout of the stable-code0 Latin V3 L3 grid.

The analyzer is deliberately offline.  It deep-validates an existing 48 MP
capture sidecar, reuses the already tested dual-8x8 homography fitter, and
samples every cell after perspective rectification.  Illumination correction
is controller-local: each cell is referenced to the four adjacent white
separator bands and then recentered on that controller's median separator
white.  CS1 and CS2 are never compared as if they shared a colour profile.

The resulting Lab values are camera-relative screening values only.  They do
not establish absolute colour, a qualified gray level, persistence, or a
production palette entry.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

import cv2
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_camera_capture_evidence as capture_evidence  # noqa: E402
from tools import mf1750_redpink_v2_grid_photo_analyzer as grid  # noqa: E402
from tools import mf1750_stable_code0_luma_latin_v3_observation as observation  # noqa: E402
from tools import mf1750_stable_code0_luma_latin_v3_pack as pack  # noqa: E402


class V3PhotoAnalysisError(RuntimeError):
    """Raised when evidence or image quality cannot support this analysis."""


SCHEMA_VERSION = 1
KIND = "mf1750-stable-code0-luma-latin-v3-camera-relative-photo-analysis"
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
RECTIFICATION_SCALE = 2
INNER_CROP_FRACTION = 0.54
WHITE_BAND_INSET = 2
WHITE_BAND_OUTSET = 6
EDGE_INSET_NEAR = 3
EDGE_INSET_FAR = 7

QUALITY_THRESHOLDS = {
    "maximum_homography_rmse_px": 2.0,
    "maximum_homography_p95_px": 3.0,
    "minimum_projected_cell_dimension_px": 20.0,
    "minimum_separator_white_l_star": 20.0,
    "maximum_separator_white_l_star": 95.0,
    "maximum_all_channels_low_clip_fraction": 0.02,
    "maximum_any_channel_high_clip_fraction": 0.005,
    "maximum_center_rgb_mad": 6.0,
    "bottom_stripe_present_dark_delta_l_star": -4.0,
    "bottom_stripe_present_de76_excess": 2.0,
    "bottom_stripe_uncertain_dark_delta_l_star": -2.5,
    "bottom_stripe_uncertain_de76_excess": 1.0,
    "maximum_centered_cell_delta_l_star_p95": 3.0,
    "maximum_centered_middle_median_delta_l_star": 2.0,
    "minimum_middle_median_lightness_pearson": 0.80,
}


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


def _read_json(path: Path, *, label: str) -> tuple[bytes, Mapping[str, Any]]:
    try:
        payload = Path(path).read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise V3PhotoAnalysisError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, Mapping):
        raise V3PhotoAnalysisError(f"{label} root is not an object")
    return payload, value


def _resolve_sidecar_photo(sidecar_path: Path, sidecar: Mapping[str, Any]) -> Path:
    photo = sidecar.get("photo")
    if not isinstance(photo, Mapping) or not isinstance(photo.get("path"), str):
        raise V3PhotoAnalysisError("capture sidecar photo path is missing")
    path = Path(photo["path"])
    if not path.is_absolute():
        path = sidecar_path.parent / path
    return path.resolve()


def _validate_capture_binding(
    photo_path: Path, sidecar_path: Path
) -> tuple[Mapping[str, Any], dict[str, Any], str]:
    try:
        sidecar = capture_evidence.validate_capture_evidence(sidecar_path)
    except (OSError, ValueError, RuntimeError) as exc:
        raise V3PhotoAnalysisError(f"capture sidecar validation failed: {exc}") from exc
    ordinal = sidecar.get("ordinal")
    if ordinal not in (3, 4):
        raise V3PhotoAnalysisError("capture is not a V3 L3 or L4 action")
    stage = f"L{ordinal}"
    expected = {
        "campaign_id": pack.CAMPAIGN_ID,
        "test_id": pack.TEST_ID,
        "contract_id": pack.build_report()["contract_id"],
        "ordinal": ordinal,
        "role": pack.ROLES[ordinal - 1],
        "firmware_sha256": pack.ARTIFACTS[pack.VARIANT_KEY]["bin_sha256"],
        "capture_binding": capture_evidence.BINDING_LIVE,
    }
    mismatches = [key for key, wanted in expected.items() if sidecar.get(key) != wanted]
    if mismatches:
        raise V3PhotoAnalysisError(
            f"capture sidecar V3 L3 identity differs: {mismatches!r}"
        )
    camera = sidecar.get("camera")
    if not isinstance(camera, Mapping):
        raise V3PhotoAnalysisError("capture camera record is missing")
    instance = str(camera.get("instance_id", "")).casefold()
    if "vid_32e4&pid_4801" not in instance or "vid_1bcf&pid_0b15" in instance:
        raise V3PhotoAnalysisError("capture is not bound to the 48MP project camera")
    if _resolve_sidecar_photo(sidecar_path, sidecar) != photo_path.resolve():
        raise V3PhotoAnalysisError("requested photo differs from capture sidecar photo")
    sidecar_payload = sidecar_path.read_bytes()
    return sidecar, {
        "path": sidecar_path.relative_to(REPO_ROOT).as_posix()
        if sidecar_path.is_relative_to(REPO_ROOT)
        else str(sidecar_path),
        "bytes": len(sidecar_payload),
        "sha256": _sha256_bytes(sidecar_payload),
        "canonical_integrity_sha256": sidecar["integrity"]["sha256"],
        "capture_id": sidecar["capture_id"],
        "camera_id": camera["camera_id"],
        "camera_instance_id": camera["instance_id"],
        "camera_usb_identity": "VID_32E4:PID_4801",
        "capture_binding": sidecar["capture_binding"],
        "requested_settings": deepcopy(camera["requested_settings"]),
        "effective_settings_before_frame": deepcopy(
            camera["effective_settings_before_frame"]
        ),
        "effective_settings_after_frame": deepcopy(
            camera["effective_settings_after_frame"]
        ),
    }, stage


def _rectify(
    image: np.ndarray, homography: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    scale = float(RECTIFICATION_SCALE)
    scaled = np.array([[scale, 0.0, 0.0], [0.0, scale, 0.0], [0.0, 0.0, 1.0]])
    transform = scaled @ np.linalg.inv(homography)
    size = (grid.LOGICAL_WIDTH * RECTIFICATION_SCALE, grid.LOGICAL_HEIGHT * RECTIFICATION_SCALE)
    rectified = cv2.warpPerspective(
        image,
        transform,
        size,
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )
    valid_source = np.full(image.shape[:2], 255, dtype=np.uint8)
    validity = cv2.warpPerspective(
        valid_source,
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
    scale = RECTIFICATION_SCALE
    x0, y0, x1, y1 = bounds
    ix0, iy0 = int(round(x0 * scale)), int(round(y0 * scale))
    ix1, iy1 = int(round(x1 * scale)), int(round(y1 * scale))
    patch = rectified[iy0:iy1, ix0:ix1]
    valid = validity[iy0:iy1, ix0:ix1] > 0
    if patch.size == 0 or valid.size == 0:
        raise V3PhotoAnalysisError(f"{label} sampling box is empty")
    pixels = patch[valid][:, ::-1].astype(np.float64)
    if len(pixels) < 32:
        raise V3PhotoAnalysisError(f"{label} has too few valid pixels")
    return pixels


def _robust_rgb(pixels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    median = np.median(pixels, axis=0)
    mad = np.median(np.abs(pixels - median), axis=0)
    return median, mad


def _lab(rgb: np.ndarray) -> np.ndarray:
    return grid._lab_from_rgb(rgb)  # noqa: SLF001 - shared frozen camera conversion


def _de76(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.linalg.norm(left - right))


def _hue_degrees(lab: np.ndarray) -> float:
    return math.degrees(math.atan2(float(lab[2]), float(lab[1]))) % 360.0


def _angle_delta(left: float, right: float) -> float:
    return abs((left - right + 180.0) % 360.0 - 180.0)


def _cell_bounds(controller: int, row: int, column: int) -> tuple[int, int, int, int]:
    x0 = (
        controller * grid.CONTROLLER_WIDTH
        + grid.GRID_X0
        + column * grid.CELL_STEP_X
    )
    y0 = grid.GRID_Y0 + row * grid.CELL_STEP_Y
    return x0, y0, x0 + grid.CELL_WIDTH, y0 + grid.CELL_HEIGHT


def _sample_cell_raw(
    rectified: np.ndarray,
    validity: np.ndarray,
    *,
    controller: int,
    row: int,
    column: int,
) -> dict[str, Any]:
    x0, y0, x1, y1 = _cell_bounds(controller, row, column)
    margin_x = grid.CELL_WIDTH * (1.0 - INNER_CROP_FRACTION) / 2.0
    margin_y = grid.CELL_HEIGHT * (1.0 - INNER_CROP_FRACTION) / 2.0
    center_pixels = _box_pixels_rgb(
        rectified,
        validity,
        (x0 + margin_x, y0 + margin_y, x1 - margin_x, y1 - margin_y),
        label=f"CS{controller + 1} R{row} C{column} center",
    )
    center_rgb, center_mad = _robust_rgb(center_pixels)

    white_boxes = (
        (x0 + margin_x, y0 - WHITE_BAND_OUTSET, x1 - margin_x, y0 - WHITE_BAND_INSET),
        (x0 + margin_x, y1 + WHITE_BAND_INSET, x1 - margin_x, y1 + WHITE_BAND_OUTSET),
        (x0 - WHITE_BAND_OUTSET, y0 + margin_y, x0 - WHITE_BAND_INSET, y1 - margin_y),
        (x1 + WHITE_BAND_INSET, y0 + margin_y, x1 + WHITE_BAND_OUTSET, y1 - margin_y),
    )
    white_pixels = np.concatenate(
        [
            _box_pixels_rgb(
                rectified,
                validity,
                bounds,
                label=f"CS{controller + 1} R{row} C{column} separator {index}",
            )
            for index, bounds in enumerate(white_boxes)
        ]
    )
    white_rgb, white_mad = _robust_rgb(white_pixels)

    edge_boxes = {
        "top": (x0 + 10, y0 + EDGE_INSET_NEAR, x1 - 10, y0 + EDGE_INSET_FAR),
        "bottom": (x0 + 10, y1 - EDGE_INSET_FAR, x1 - 10, y1 - EDGE_INSET_NEAR),
        "left": (x0 + EDGE_INSET_NEAR, y0 + 12, x0 + EDGE_INSET_FAR, y1 - 12),
        "right": (x1 - EDGE_INSET_FAR, y0 + 12, x1 - EDGE_INSET_NEAR, y1 - 12),
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
        for name, bounds in edge_boxes.items()
    }
    edge_de76 = {name: _de76(value, center_lab) for name, value in edge_labs.items()}
    other_edge_median = float(
        np.median([edge_de76["top"], edge_de76["left"], edge_de76["right"]])
    )
    bottom_excess = edge_de76["bottom"] - other_edge_median
    bottom_delta_l = float(edge_labs["bottom"][0] - center_lab[0])
    stripe = classify_bottom_edge_stripe(
        bottom_delta_l_star=bottom_delta_l,
        bottom_de76_excess=bottom_excess,
    )
    all_low = float(np.mean(np.all(center_pixels <= 5.0, axis=1)))
    any_high = float(np.mean(np.any(center_pixels >= 250.0, axis=1)))
    return {
        "controller": controller,
        "row": row,
        "column": column,
        "center_rgb": center_rgb,
        "center_rgb_mad": center_mad,
        "center_lab": center_lab,
        "separator_rgb": white_rgb,
        "separator_rgb_mad": white_mad,
        "separator_lab": _lab(white_rgb),
        "center_all_channels_low_clip_fraction": all_low,
        "center_any_channel_high_clip_fraction": any_high,
        "edge_labs": edge_labs,
        "edge_de76_to_center": edge_de76,
        "bottom_de76_excess_over_other_edges": bottom_excess,
        "bottom_l_star_delta_to_center": bottom_delta_l,
        "bottom_edge_stripe": stripe,
    }


def classify_bottom_edge_stripe(
    *, bottom_delta_l_star: float, bottom_de76_excess: float
) -> str:
    """Classify a dark bottom-only edge against the other three cell edges."""

    if (
        bottom_delta_l_star
        <= QUALITY_THRESHOLDS["bottom_stripe_present_dark_delta_l_star"]
        and bottom_de76_excess
        >= QUALITY_THRESHOLDS["bottom_stripe_present_de76_excess"]
    ):
        return "PRESENT"
    if (
        bottom_delta_l_star
        <= QUALITY_THRESHOLDS["bottom_stripe_uncertain_dark_delta_l_star"]
        and bottom_de76_excess
        >= QUALITY_THRESHOLDS["bottom_stripe_uncertain_de76_excess"]
    ):
        return "UNCERTAIN"
    return "CLEAR"


def _normalise_controller_cells(raw_cells: list[dict[str, Any]]) -> dict[str, Any]:
    separator_labs = np.array([item["separator_lab"] for item in raw_cells])
    controller_white_lab = np.median(separator_labs, axis=0)
    records: list[dict[str, Any]] = []
    for item in raw_cells:
        # Lab subtraction is deliberately local and controller-scoped.  It is
        # an observer normalization, not a calibrated colour transform.
        normalised = item["center_lab"] - item["separator_lab"] + controller_white_lab
        normalised[0] = float(np.clip(normalised[0], 0.0, 100.0))
        records.append(
            {
                **item,
                "illumination_normalized_camera_relative_lab": normalised,
            }
        )
    return {
        "controller_separator_white_lab": controller_white_lab,
        "separator_white_l_star_range": float(np.ptp(separator_labs[:, 0])),
        "cells": records,
    }


def _json_cell(item: Mapping[str, Any]) -> dict[str, Any]:
    recipe = next(
        value
        for value in pack.recipe_map()
        if value["controller"] == item["controller"]
        and value["physical_row"] == item["row"]
        and value["physical_column"] == item["column"]
    )
    return {
        "controller": f"CS{int(item['controller']) + 1}",
        "controller_role": recipe["controller_role"],
        "physical_row": item["row"],
        "physical_column": item["column"],
        "logical_row": recipe["decoder"]["logical_row"],
        "logical_column": recipe["decoder"]["logical_column"],
        "decoder_transform": recipe["decoder"]["transform"],
        "recipe_id": recipe["recipe_id"],
        "middle_code": recipe["middle"]["code"],
        "center_rgb_median": np.asarray(item["center_rgb"]).astype(float).tolist(),
        "center_rgb_mad": np.asarray(item["center_rgb_mad"]).astype(float).tolist(),
        "separator_rgb_median": np.asarray(item["separator_rgb"]).astype(float).tolist(),
        "separator_rgb_mad": np.asarray(item["separator_rgb_mad"]).astype(float).tolist(),
        "raw_camera_relative_lab": np.asarray(item["center_lab"]).astype(float).tolist(),
        "local_separator_camera_relative_lab": np.asarray(item["separator_lab"])
        .astype(float)
        .tolist(),
        "illumination_normalized_camera_relative_lab": np.asarray(
            item["illumination_normalized_camera_relative_lab"]
        )
        .astype(float)
        .tolist(),
        "center_all_channels_low_clip_fraction": item[
            "center_all_channels_low_clip_fraction"
        ],
        "center_any_channel_high_clip_fraction": item[
            "center_any_channel_high_clip_fraction"
        ],
        "edge_de76_to_center": deepcopy(item["edge_de76_to_center"]),
        "bottom_de76_excess_over_other_edges": item[
            "bottom_de76_excess_over_other_edges"
        ],
        "bottom_l_star_delta_to_center": item["bottom_l_star_delta_to_center"],
        "bottom_edge_stripe": item["bottom_edge_stripe"],
    }


def _controller_summary(controller: int, cells: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[int, list[np.ndarray]] = {code: [] for code in range(8)}
    for item in cells:
        code = pack.middle_code(controller, int(item["row"]), int(item["column"]))
        groups[code].append(item["illumination_normalized_camera_relative_lab"])
    medians = {code: np.median(np.array(values), axis=0) for code, values in groups.items()}
    ranges = {
        code: float(np.ptp(np.array(values)[:, 0])) for code, values in groups.items()
    }
    l_values = [float(medians[code][0]) for code in range(8)]
    hue_codes = [
        code
        for code in range(8)
        if math.hypot(float(medians[code][1]), float(medians[code][2]))
        >= observation.DEFAULT_THRESHOLDS["minimum_chroma_for_hue_gate"]
    ]
    hues = {code: _hue_degrees(medians[code]) for code in hue_codes}
    hue_span = max(
        (_angle_delta(hues[left], hues[right]) for left in hue_codes for right in hue_codes),
        default=0.0,
    )
    repeat_pass = all(
        value <= observation.DEFAULT_THRESHOLDS["maximum_repeat_l_star_range"]
        for value in ranges.values()
    )
    luma_span = max(l_values) - min(l_values)
    hue_pass = hue_span <= observation.DEFAULT_THRESHOLDS["maximum_same_hue_angle_degrees"]
    strict_candidate = (
        luma_span >= observation.DEFAULT_THRESHOLDS["minimum_between_middle_delta_l_star"]
        and repeat_pass
        and hue_pass
    )
    stripe_counts = {
        state: sum(item["bottom_edge_stripe"] == state for item in cells)
        for state in observation.STRIPE_STATES
    }
    return {
        "controller": f"CS{controller + 1}",
        "interpretation": (
            "CS1_CONTROLLER_SPECIFIC_INTERNAL_CONTROL"
            if controller == 0
            else "CS2_RED_FAMILY_PRIMARY_OBSERVATION"
        ),
        "controller_local_only": True,
        "middle_code_median_normalized_lab": {
            str(code): medians[code].astype(float).tolist() for code in range(8)
        },
        "middle_code_l_star_range_across_eight_positions": {
            str(code): ranges[code] for code in range(8)
        },
        "between_middle_median_delta_l_star": luma_span,
        "same_hue_angle_span_degrees": hue_span,
        "same_hue_gate_pass": hue_pass,
        "position_repeat_gate_pass": repeat_pass,
        "strict_luma_mechanism_review_candidate": strict_candidate,
        "lightness_signal_for_repeat_review": (
            luma_span
            >= observation.DEFAULT_THRESHOLDS["minimum_between_middle_delta_l_star"]
            and repeat_pass
            and stripe_counts["PRESENT"] == 0
        ),
        "bottom_edge_stripe_counts": stripe_counts,
    }


def _fill_l3_observation(
    *,
    photo_path: Path,
    photo_bytes: bytes,
    cells: list[dict[str, Any]],
    capture_quality: Mapping[str, str],
) -> dict[str, Any]:
    document = observation.observation_template(include_l4=False)
    capture = document["captures"]["L3"]
    capture["image_path"] = (
        photo_path.relative_to(REPO_ROOT).as_posix()
        if photo_path.is_relative_to(REPO_ROOT)
        else str(photo_path)
    )
    capture["image_bytes"] = len(photo_bytes)
    capture["image_sha256"] = _sha256_bytes(photo_bytes)
    capture["quality"] = dict(capture_quality)
    index = {
        (f"CS{int(item['controller']) + 1}", int(item["row"]), int(item["column"])): item
        for item in cells
    }
    for measurement in document["measurements"]:
        item = index[
            (
                measurement["controller"],
                measurement["physical_row"],
                measurement["physical_column"],
            )
        ]
        lab = item["illumination_normalized_camera_relative_lab"]
        measurement["lab"] = {
            "l_star": float(lab[0]),
            "a_star": float(lab[1]),
            "b_star": float(lab[2]),
        }
        measurement["bottom_edge_stripe"] = item["bottom_edge_stripe"]
    document["operator_notes"] = (
        "Automatically filled from one sealed 48MP JPEG using controller-local "
        "separator-white normalization; camera-relative review only."
    )
    return document


def _geometry_from_l3_reference(
    image: np.ndarray, reference_report_path: Path
) -> dict[str, Any]:
    _payload, reference = _validate_analysis_report(reference_report_path, stage="L3")
    reference_geometry = reference["geometry_quality"]
    homography = np.array(
        reference_geometry["homography_logical_to_photo"], dtype=np.float64
    )
    attempts: list[tuple[float, float, str, tuple[int, int], list[dict[str, Any]]]] = []
    for colour_space, thresholds in grid._EDGE_DETECTION_CONFIGS:  # noqa: SLF001
        rectangles = grid._detect_edge_rectangles(  # noqa: SLF001
            image, thresholds, colour_space
        )
        assignments = grid._assign_with_homography(rectangles, homography)  # noqa: SLF001
        if len(assignments) != 128 or [
            sum(item["controller"] == controller for item in assignments)
            for controller in range(2)
        ] != [64, 64]:
            continue
        errors = np.array(
            [item["reprojection_error_px"] for item in assignments], dtype=float
        )
        attempts.append(
            (
                float(np.percentile(errors, 95)),
                float(np.sqrt(np.mean(errors**2))),
                colour_space,
                thresholds,
                assignments,
            )
        )
    if not attempts:
        raise V3PhotoAnalysisError(
            "L4 cannot be bound to all 128 L3 reference-grid cells"
        )
    attempts.sort(key=lambda item: (item[0], item[1]))
    p95, rmse, colour_space, thresholds, assignments = attempts[0]
    if rmse > QUALITY_THRESHOLDS["maximum_homography_rmse_px"] or p95 > QUALITY_THRESHOLDS[
        "maximum_homography_p95_px"
    ]:
        raise V3PhotoAnalysisError(
            "L4 reference-grid reprojection exceeds the frozen quality gate"
        )
    reference_path = Path(reference_report_path).resolve()
    reference_payload = reference_path.read_bytes()
    return {
        "mapping_basis": (
            "sealed L3 homography reused on fixed camera; L4 independently "
            "supports all 128 expected closed-cell edges"
        ),
        "geometry_origin": "L3_SEALED_REFERENCE_WITH_L4_EXACT_128_EDGE_SUPPORT",
        "geometry_reference_report": {
            "path": reference_path.relative_to(REPO_ROOT).as_posix()
            if reference_path.is_relative_to(REPO_ROOT)
            else str(reference_path),
            "bytes": len(reference_payload),
            "sha256": _sha256_bytes(reference_payload),
            "canonical_integrity_sha256": reference["integrity"]["sha256"],
        },
        "rectangle_detection_method": "strict-canny-closed-cell-contours-v1",
        "edge_colour_space": colour_space,
        "edge_canny_thresholds": list(thresholds),
        "unique_cell_contour_support": 128,
        "support_by_controller": [64, 64],
        "homography_inlier_fraction": 1.0,
        "homography_inlier_rmse_px": rmse,
        "homography_inlier_p95_px": p95,
        "homography_logical_to_photo": homography.astype(float).tolist(),
        "sampling": deepcopy(reference_geometry["sampling"]),
        "reference_assignments": len(assignments),
    }


def analyze(
    photo_path: Path,
    capture_sidecar_path: Path,
    *,
    geometry_reference_report_path: Path | None = None,
) -> dict[str, Any]:
    """Analyze one already captured L3 or L4 JPEG; never access live hardware."""

    photo_path = Path(photo_path).resolve()
    capture_sidecar_path = Path(capture_sidecar_path).resolve()
    sidecar, sidecar_binding, stage = _validate_capture_binding(
        photo_path, capture_sidecar_path
    )
    try:
        photo_bytes = photo_path.read_bytes()
        image = cv2.imdecode(np.frombuffer(photo_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    except OSError as exc:
        raise V3PhotoAnalysisError(f"cannot read photo: {photo_path}") from exc
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        raise V3PhotoAnalysisError("photo is not a decodable colour image")

    try:
        base = grid.analyze(photo_path, ordinal=3)
    except grid.GridPhotoAnalysisError as exc:
        if stage != "L4" or geometry_reference_report_path is None:
            raise V3PhotoAnalysisError(f"dual-grid geometry is not sufficient: {exc}") from exc
        geometry = _geometry_from_l3_reference(
            image, Path(geometry_reference_report_path)
        )
    else:
        geometry = deepcopy(base["geometry_quality"])
        geometry["geometry_origin"] = "INDEPENDENT_DUAL_8X8_FIT"
        geometry["geometry_reference_report"] = None
        if (
            base["grid_judgement"]["enough_to_interpret_grid_camera_relatively"]
            is not True
        ):
            raise V3PhotoAnalysisError("dual-grid geometry is not sufficient")
    homography = np.array(geometry["homography_logical_to_photo"], dtype=np.float64)
    rectified, validity = _rectify(image, homography)

    all_cells: list[dict[str, Any]] = []
    controller_normalization: dict[str, Any] = {}
    for controller in range(2):
        raw = [
            _sample_cell_raw(
                rectified,
                validity,
                controller=controller,
                row=row,
                column=column,
            )
            for row in range(8)
            for column in range(8)
        ]
        normalized = _normalise_controller_cells(raw)
        all_cells.extend(normalized["cells"])
        controller_normalization[f"CS{controller + 1}"] = {
            "separator_white_median_camera_relative_lab": normalized[
                "controller_separator_white_lab"
            ]
            .astype(float)
            .tolist(),
            "separator_white_l_star_range_before_normalization": normalized[
                "separator_white_l_star_range"
            ],
            "cross_controller_pooling": False,
        }

    summaries = {
        f"CS{controller + 1}": _controller_summary(
            controller,
            [item for item in all_cells if item["controller"] == controller],
        )
        for controller in range(2)
    }
    white_labs = [item["separator_lab"] for item in all_cells]
    minimum_white_l = min(float(value[0]) for value in white_labs)
    maximum_white_l = max(float(value[0]) for value in white_labs)
    maximum_low_clip = max(
        float(item["center_all_channels_low_clip_fraction"]) for item in all_cells
    )
    maximum_high_clip = max(
        float(item["center_any_channel_high_clip_fraction"]) for item in all_cells
    )
    maximum_mad = max(float(np.max(item["center_rgb_mad"])) for item in all_cells)
    purity_pass = maximum_mad <= QUALITY_THRESHOLDS["maximum_center_rgb_mad"]
    quality = {
        "both_controller_rois_visible": "PASS",
        "exposure_usable": (
            "PASS"
            if minimum_white_l >= QUALITY_THRESHOLDS["minimum_separator_white_l_star"]
            and maximum_white_l <= QUALITY_THRESHOLDS["maximum_separator_white_l_star"]
            and maximum_low_clip
            <= QUALITY_THRESHOLDS["maximum_all_channels_low_clip_fraction"]
            and maximum_high_clip
            <= QUALITY_THRESHOLDS["maximum_any_channel_high_clip_fraction"]
            else "FAIL"
        ),
        "focus_usable": (
            "PASS"
            if geometry["homography_inlier_rmse_px"]
            <= QUALITY_THRESHOLDS["maximum_homography_rmse_px"]
            and geometry["homography_inlier_p95_px"]
            <= QUALITY_THRESHOLDS["maximum_homography_p95_px"]
            and geometry["unique_cell_contour_support"] == 128
            else "FAIL"
        ),
        "glare_not_material": (
            "PASS"
            if maximum_high_clip
            <= QUALITY_THRESHOLDS["maximum_any_channel_high_clip_fraction"]
            else "FAIL"
        ),
    }
    observation_document = None
    observation_evaluation = None
    if stage == "L3":
        observation_document = _fill_l3_observation(
            photo_path=photo_path,
            photo_bytes=photo_bytes,
            cells=all_cells,
            capture_quality=quality,
        )
        observation_evaluation = observation.evaluate_observations(
            observation_document,
            verify_terminal=True,
        )
    strict_candidates = [
        key
        for key, value in summaries.items()
        if value["strict_luma_mechanism_review_candidate"]
    ]
    repeat_review = [
        key for key, value in summaries.items() if value["lightness_signal_for_repeat_review"]
    ]
    any_present = any(
        value["bottom_edge_stripe_counts"]["PRESENT"] for value in summaries.values()
    )
    any_uncertain = any(
        value["bottom_edge_stripe_counts"]["UNCERTAIN"] for value in summaries.values()
    )
    if any_present:
        decision = "REJECT_BOTTOM_EDGE_STRIPE_PRESENT"
    elif (
        not all(value == "PASS" for value in quality.values())
        or not purity_pass
        or any_uncertain
    ):
        decision = "REVIEW_CAPTURE_OR_EDGE_QUALITY"
    elif strict_candidates:
        decision = "REVIEW_STRICT_LUMA_MECHANISM_CANDIDATE"
    elif repeat_review:
        decision = "REVIEW_CONTROLLER_LOCAL_LIGHTNESS_SIGNAL_REPEAT_NEEDED"
    else:
        decision = "NO_SIGNIFICANT_CONTROLLER_LOCAL_LIGHTNESS_SIGNAL"

    ordinal = int(sidecar["ordinal"])
    terminal_path = observation.once.ACTION_OUTPUTS[ordinal]
    terminal_payload = terminal_path.read_bytes()
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "campaign_id": pack.CAMPAIGN_ID,
        "test_id": pack.TEST_ID,
        "contract_id": pack.build_report()["contract_id"],
        "stage": stage,
        "decision": decision,
        "source_photo": {
            "path": photo_path.relative_to(REPO_ROOT).as_posix()
            if photo_path.is_relative_to(REPO_ROOT)
            else str(photo_path),
            "bytes": len(photo_bytes),
            "sha256": _sha256_bytes(photo_bytes),
            "width": int(image.shape[1]),
            "height": int(image.shape[0]),
        },
        "source_capture_sidecar": sidecar_binding,
        "source_terminal_evidence": {
            "path": terminal_path.relative_to(REPO_ROOT).as_posix(),
            "bytes": len(terminal_payload),
            "sha256": _sha256_bytes(terminal_payload),
            "action_id": sidecar["action_id"],
            "terminal_state": "COMPLETE",
        },
        "geometry_quality": {
            "mapping_basis": geometry["mapping_basis"],
            "geometry_origin": geometry["geometry_origin"],
            "geometry_reference_report": geometry["geometry_reference_report"],
            "rectangle_detection_method": geometry.get(
                "rectangle_detection_method", "hsv-saturation-contours-v1"
            ),
            "unique_cell_contour_support": geometry["unique_cell_contour_support"],
            "support_by_controller": geometry["support_by_controller"],
            "homography_inlier_fraction": geometry["homography_inlier_fraction"],
            "homography_inlier_rmse_px": geometry["homography_inlier_rmse_px"],
            "homography_inlier_p95_px": geometry["homography_inlier_p95_px"],
            "homography_logical_to_photo": geometry["homography_logical_to_photo"],
            "sampling": deepcopy(geometry["sampling"]),
        },
        "method": {
            "rectification_scale": RECTIFICATION_SCALE,
            "central_inset_fraction": INNER_CROP_FRACTION,
            "local_illumination_reference": (
                "four adjacent white separator bands per cell; Lab difference "
                "recentered on controller-local median separator white"
            ),
            "robust_statistic": "per-channel median and median absolute deviation",
            "controllers_pooled": False,
            "cs1_cs2_colour_equivalence_claimed": False,
            "absolute_colour_claimed": False,
        },
        "quality_thresholds": deepcopy(QUALITY_THRESHOLDS),
        "capture_quality": {
            **quality,
            "minimum_separator_white_l_star": minimum_white_l,
            "maximum_separator_white_l_star": maximum_white_l,
            "maximum_center_all_channels_low_clip_fraction": maximum_low_clip,
            "maximum_center_any_channel_high_clip_fraction": maximum_high_clip,
            "maximum_center_rgb_mad": maximum_mad,
            "single_pixel_fill_coarse_uniformity_pass": purity_pass,
        },
        "controller_normalization": controller_normalization,
        "controller_results": summaries,
        "cells": [_json_cell(item) for item in all_cells],
        "existing_observation_schema": {
            "document": observation_document,
            "evaluation": observation_evaluation,
            "l4_fragment_requires_l3_for_evaluation": stage == "L4",
        },
        "repeat_recommendation": {
            "run_optional_l4": bool(
                stage == "L3" and repeat_review and not any_present
            ),
            "controllers_requiring_repeat_review": repeat_review,
            "strict_candidate_controllers": strict_candidates,
            "reason": (
                "L4 may test reproducibility only; it cannot qualify a gray level "
                "or repair a same-hue/position/edge failure."
                if stage == "L3"
                else "L4 has already run; use the sealed L3-vs-L4 comparator."
            ),
        },
        "qualification_boundary": {
            "review_candidates_only": True,
            "qualified_colour_count": 0,
            "qualified_gray_levels": 0,
            "persistence_proven": False,
            "cross_controller_equivalence_proven": False,
            "camera_relative_only": True,
        },
        "hardware_accessed": False,
        "camera_accessed": False,
        "network_requests": 0,
    }
    report["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": _sha256_bytes(_canonical_json(report)),
    }
    return report


def _resolve_report_source(path_text: Any, *, label: str) -> Path:
    if not isinstance(path_text, str) or not path_text:
        raise V3PhotoAnalysisError(f"{label} path is missing")
    path = Path(path_text)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def _validate_analysis_report(path: Path, *, stage: str) -> tuple[bytes, Mapping[str, Any]]:
    payload, value = _read_json(path, label=f"{stage} analysis report")
    integrity = value.get("integrity")
    if not isinstance(integrity, Mapping) or integrity.get("algorithm") != INTEGRITY_ALGORITHM:
        raise V3PhotoAnalysisError(f"{stage} analysis integrity is missing")
    body = dict(value)
    body.pop("integrity", None)
    if integrity.get("sha256") != _sha256_bytes(_canonical_json(body)):
        raise V3PhotoAnalysisError(f"{stage} analysis canonical integrity differs")
    expected = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "campaign_id": pack.CAMPAIGN_ID,
        "test_id": pack.TEST_ID,
        "contract_id": pack.build_report()["contract_id"],
        "stage": stage,
        "hardware_accessed": False,
        "camera_accessed": False,
        "network_requests": 0,
    }
    mismatches = [key for key, wanted in expected.items() if value.get(key) != wanted]
    if mismatches:
        raise V3PhotoAnalysisError(f"{stage} analysis identity differs: {mismatches!r}")
    for key in ("source_photo", "source_capture_sidecar", "source_terminal_evidence"):
        record = value.get(key)
        if not isinstance(record, Mapping):
            raise V3PhotoAnalysisError(f"{stage} {key} binding is missing")
        source = _resolve_report_source(record.get("path"), label=f"{stage} {key}")
        try:
            source_payload = source.read_bytes()
        except OSError as exc:
            raise V3PhotoAnalysisError(f"cannot read {stage} {key}: {source}") from exc
        if record.get("bytes") != len(source_payload) or record.get("sha256") != _sha256_bytes(
            source_payload
        ):
            raise V3PhotoAnalysisError(f"{stage} {key} file binding differs")
    cells = value.get("cells")
    if not isinstance(cells, list) or len(cells) != 128:
        raise V3PhotoAnalysisError(f"{stage} analysis does not contain 128 cells")
    keys = {
        (item.get("controller"), item.get("physical_row"), item.get("physical_column"))
        for item in cells
        if isinstance(item, Mapping)
    }
    expected_keys = {
        (controller, row, column)
        for controller in observation.CONTROLLERS
        for row in range(8)
        for column in range(8)
    }
    if keys != expected_keys:
        raise V3PhotoAnalysisError(f"{stage} cell coordinate coverage differs")
    return payload, value


def _pearson(left: np.ndarray, right: np.ndarray) -> float | None:
    if left.shape != right.shape or left.ndim != 1:
        raise V3PhotoAnalysisError("repeat Pearson input shape differs")
    if float(np.ptp(left)) <= 1e-12 or float(np.ptp(right)) <= 1e-12:
        return None
    return float(np.corrcoef(left, right)[0, 1])


def _controller_repeat_comparison(
    controller: str,
    l3_cells: Sequence[Mapping[str, Any]],
    l4_cells: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    def index(values: Sequence[Mapping[str, Any]]) -> dict[tuple[int, int], np.ndarray]:
        result: dict[tuple[int, int], np.ndarray] = {}
        for item in values:
            if item.get("controller") != controller:
                continue
            key = (int(item["physical_row"]), int(item["physical_column"]))
            lab = np.array(item["illumination_normalized_camera_relative_lab"], dtype=float)
            if lab.shape != (3,) or not np.all(np.isfinite(lab)):
                raise V3PhotoAnalysisError(f"{controller} repeat Lab is invalid")
            result[key] = lab
        if set(result) != {(row, column) for row in range(8) for column in range(8)}:
            raise V3PhotoAnalysisError(f"{controller} repeat cell coverage differs")
        return result

    left, right = index(l3_cells), index(l4_cells)
    coordinates = [(row, column) for row in range(8) for column in range(8)]
    l3 = np.array([left[key] for key in coordinates])
    l4 = np.array([right[key] for key in coordinates])
    l3_center = np.median(l3, axis=0)
    l4_center = np.median(l4, axis=0)
    centered_l3 = l3 - l3_center
    centered_l4 = l4 - l4_center
    centered_delta = centered_l4 - centered_l3
    centered_abs_l = np.abs(centered_delta[:, 0])
    centered_de76 = np.linalg.norm(centered_delta, axis=1)

    controller_index = 0 if controller == "CS1" else 1
    code_l3: list[float] = []
    code_l4: list[float] = []
    code_records: dict[str, Any] = {}
    for code in range(8):
        positions = [
            index
            for index, (row, column) in enumerate(coordinates)
            if pack.middle_code(controller_index, row, column) == code
        ]
        value_l3 = float(np.median(centered_l3[positions, 0]))
        value_l4 = float(np.median(centered_l4[positions, 0]))
        code_l3.append(value_l3)
        code_l4.append(value_l4)
        code_records[str(code)] = {
            "l3_centered_median_l_star": value_l3,
            "l4_centered_median_l_star": value_l4,
            "absolute_delta_l_star": abs(value_l4 - value_l3),
        }
    code_l3_array = np.array(code_l3)
    code_l4_array = np.array(code_l4)
    code_abs_delta = np.abs(code_l4_array - code_l3_array)
    correlation = _pearson(code_l3_array, code_l4_array)
    l3_code_span = float(np.ptp(code_l3_array))
    l4_code_span = float(np.ptp(code_l4_array))
    span_retention = l4_code_span / l3_code_span if l3_code_span > 1e-12 else None
    centered_gate = (
        float(np.percentile(centered_abs_l, 95))
        <= QUALITY_THRESHOLDS["maximum_centered_cell_delta_l_star_p95"]
        and float(np.max(code_abs_delta))
        <= QUALITY_THRESHOLDS["maximum_centered_middle_median_delta_l_star"]
        and correlation is not None
        and correlation >= QUALITY_THRESHOLDS["minimum_middle_median_lightness_pearson"]
    )
    return {
        "controller": controller,
        "controller_local_only": True,
        "l3_controller_median_lab": l3_center.astype(float).tolist(),
        "l4_controller_median_lab": l4_center.astype(float).tolist(),
        "raw_controller_median_delta_lab": (l4_center - l3_center).astype(float).tolist(),
        "centered_cell_absolute_delta_l_star": {
            "median": float(np.median(centered_abs_l)),
            "p95": float(np.percentile(centered_abs_l, 95)),
            "maximum": float(np.max(centered_abs_l)),
        },
        "centered_cell_delta_e76": {
            "median": float(np.median(centered_de76)),
            "p95": float(np.percentile(centered_de76, 95)),
            "maximum": float(np.max(centered_de76)),
        },
        "middle_code_centered_lightness": code_records,
        "maximum_middle_code_centered_median_delta_l_star": float(np.max(code_abs_delta)),
        "middle_code_centered_lightness_pearson": correlation,
        "l3_middle_code_median_lightness_span": l3_code_span,
        "l4_middle_code_median_lightness_span": l4_code_span,
        "l4_over_l3_middle_code_span_retention": span_retention,
        "centered_lightness_repeat_gate_pass": centered_gate,
        "raw_absolute_lab_repeat_claimed": False,
    }


def _fill_repeat_observation(
    l3: Mapping[str, Any], l4: Mapping[str, Any]
) -> dict[str, Any]:
    document = observation.observation_template(include_l4=True)
    reports = {"L3": l3, "L4": l4}
    for stage, report in reports.items():
        source = report["source_photo"]
        quality = report["capture_quality"]
        capture = document["captures"][stage]
        capture["image_path"] = source["path"]
        capture["image_bytes"] = source["bytes"]
        capture["image_sha256"] = source["sha256"]
        capture["quality"] = {
            key: quality[key]
            for key in (
                "both_controller_rois_visible",
                "exposure_usable",
                "focus_usable",
                "glare_not_material",
            )
        }
    cell_index = {
        (
            stage,
            item["controller"],
            item["physical_row"],
            item["physical_column"],
        ): item
        for stage, report in reports.items()
        for item in report["cells"]
    }
    for item in document["measurements"]:
        source = cell_index[
            (
                item["stage"],
                item["controller"],
                item["physical_row"],
                item["physical_column"],
            )
        ]
        lab = source["illumination_normalized_camera_relative_lab"]
        item["lab"] = {"l_star": lab[0], "a_star": lab[1], "b_star": lab[2]}
        item["bottom_edge_stripe"] = source["bottom_edge_stripe"]
    l3_exposure = l3["source_capture_sidecar"]["requested_settings"]["exposure"]
    l4_exposure = l4["source_capture_sidecar"]["requested_settings"]["exposure"]
    document["operator_notes"] = (
        "L3 and L4 filled from sealed 48MP captures. Requested exposures are "
        f"L3={l3_exposure} and L4={l4_exposure}. The separate repeat report also "
        "uses controller-local centering and never pools CS1 with CS2."
    )
    return document


def _camera_settings_comparability(
    l3_binding: Mapping[str, Any], l4_binding: Mapping[str, Any]
) -> dict[str, Any]:
    fields = (
        "requested_settings",
        "effective_settings_before_frame",
        "effective_settings_after_frame",
    )
    for field in fields:
        if not isinstance(l3_binding.get(field), Mapping) or not isinstance(
            l4_binding.get(field), Mapping
        ):
            raise V3PhotoAnalysisError(f"camera {field} binding is missing")
    exact_by_field = {
        field: dict(l3_binding[field]) == dict(l4_binding[field]) for field in fields
    }
    except_exposure_by_field = {
        field: {
            key: value for key, value in l3_binding[field].items() if key != "exposure"
        }
        == {
            key: value for key, value in l4_binding[field].items() if key != "exposure"
        }
        for field in fields
    }
    exposure_by_field = {
        field: l3_binding[field].get("exposure") == l4_binding[field].get("exposure")
        for field in fields
    }
    return {
        "exact_by_field": exact_by_field,
        "except_exposure_equal_by_field": except_exposure_by_field,
        "exposure_equal_by_field": exposure_by_field,
        "camera_settings_exactly_equal": all(exact_by_field.values()),
        "camera_settings_except_exposure_equal": all(
            except_exposure_by_field.values()
        ),
        "camera_exposure_equal": all(exposure_by_field.values()),
        "l3_requested_exposure": l3_binding["requested_settings"].get("exposure"),
        "l4_requested_exposure": l4_binding["requested_settings"].get("exposure"),
    }


def compare_repeat(l3_report_path: Path, l4_report_path: Path) -> dict[str, Any]:
    """Compare sealed L3/L4 analyses after controller-local Lab centering."""

    l3_payload, l3 = _validate_analysis_report(Path(l3_report_path), stage="L3")
    l4_payload, l4 = _validate_analysis_report(Path(l4_report_path), stage="L4")
    method_equal = l3["method"] == l4["method"]
    thresholds_equal = l3["quality_thresholds"] == l4["quality_thresholds"]
    camera_comparability = _camera_settings_comparability(
        l3["source_capture_sidecar"], l4["source_capture_sidecar"]
    )
    controllers = {
        controller: _controller_repeat_comparison(
            controller,
            l3["cells"],
            l4["cells"],
        )
        for controller in observation.CONTROLLERS
    }
    combined_observation = _fill_repeat_observation(l3, l4)
    raw_observation_evaluation = observation.evaluate_observations(
        combined_observation,
        verify_terminal=True,
    )
    stripe_counts = {
        state: sum(
            report["controller_results"][controller]["bottom_edge_stripe_counts"][
                state
            ]
            for report in (l3, l4)
            for controller in observation.CONTROLLERS
        )
        for state in observation.STRIPE_STATES
    }
    stripe_clear = stripe_counts["PRESENT"] == 0 and stripe_counts["UNCERTAIN"] == 0
    no_confirmed_stripe = stripe_counts["PRESENT"] == 0
    quality_pass = all(
        report["capture_quality"][key] == "PASS"
        for report in (l3, l4)
        for key in (
            "both_controller_rois_visible",
            "exposure_usable",
            "focus_usable",
            "glare_not_material",
        )
    )
    cs2_signal = (
        l3["controller_results"]["CS2"]["lightness_signal_for_repeat_review"]
        and l4["controller_results"]["CS2"]["lightness_signal_for_repeat_review"]
    )
    if (
        not method_equal
        or not thresholds_equal
        or not camera_comparability["camera_settings_except_exposure_equal"]
    ):
        decision = "REVIEW_METHOD_OR_NON_EXPOSURE_CAMERA_SETTINGS_DIFFER"
    elif not quality_pass or not no_confirmed_stripe:
        decision = "REVIEW_CAPTURE_OR_EDGE_QUALITY"
    elif cs2_signal and controllers["CS2"]["centered_lightness_repeat_gate_pass"]:
        decision = (
            "REVIEW_REPEATABLE_CS2_CONTROLLER_LOCAL_LIGHTNESS_SIGNAL_"
            "NONQUALIFYING"
        )
    elif not stripe_clear:
        decision = (
            "REVIEW_CS2_LIGHTNESS_SIGNAL_NOT_REPEATABLE_OR_NOT_PRESENT_"
            "WITH_EDGE_UNCERTAINTY"
        )
    else:
        decision = "REVIEW_CS2_LIGHTNESS_SIGNAL_NOT_REPEATABLE_OR_NOT_PRESENT"
    l3_report_resolved = Path(l3_report_path).resolve()
    l4_report_resolved = Path(l4_report_path).resolve()
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "mf1750-stable-code0-luma-latin-v3-l3-l4-camera-relative-repeat-comparison",
        "campaign_id": pack.CAMPAIGN_ID,
        "test_id": pack.TEST_ID,
        "contract_id": pack.build_report()["contract_id"],
        "decision": decision,
        "source_reports": {
            "L3": {
                "path": l3_report_resolved.relative_to(REPO_ROOT).as_posix()
                if l3_report_resolved.is_relative_to(REPO_ROOT)
                else str(l3_report_resolved),
                "bytes": len(l3_payload),
                "sha256": _sha256_bytes(l3_payload),
                "canonical_integrity_sha256": l3["integrity"]["sha256"],
            },
            "L4": {
                "path": l4_report_resolved.relative_to(REPO_ROOT).as_posix()
                if l4_report_resolved.is_relative_to(REPO_ROOT)
                else str(l4_report_resolved),
                "bytes": len(l4_payload),
                "sha256": _sha256_bytes(l4_payload),
                "canonical_integrity_sha256": l4["integrity"]["sha256"],
            },
        },
        "comparability": {
            "analysis_method_equal": method_equal,
            "analysis_thresholds_equal": thresholds_equal,
            **camera_comparability,
            "raw_absolute_lab_repeat_comparable": camera_comparability[
                "camera_settings_exactly_equal"
            ],
            "controller_local_centered_lightness_comparison_used": True,
            "cross_controller_comparison_used": False,
        },
        "controller_results": controllers,
        "raw_existing_observation_evaluation": raw_observation_evaluation,
        "quality_gate_pass": quality_pass,
        "bottom_edge_clear_in_both_captures": stripe_clear,
        "bottom_edge_no_confirmed_stripe_in_either_capture": no_confirmed_stripe,
        "bottom_edge_stripe_counts_across_256_cells": stripe_counts,
        "qualification_boundary": {
            "repeatable_signal_is_not_a_qualified_gray_level": True,
            "qualified_colour_count": 0,
            "qualified_gray_levels": 0,
            "absolute_colour_claimed": False,
            "cross_controller_equivalence_claimed": False,
            "same_exposure_repeat_proven": camera_comparability[
                "camera_settings_exactly_equal"
            ],
            "persistence_proven": False,
        },
        "hardware_accessed": False,
        "camera_accessed": False,
        "network_requests": 0,
    }
    report["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
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
        raise V3PhotoAnalysisError(f"refusing to overwrite existing output: {path}") from exc
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
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    command = subparsers.add_parser("analyze")
    command.add_argument("--photo", type=Path, required=True)
    command.add_argument("--capture-sidecar", type=Path, required=True)
    command.add_argument(
        "--geometry-reference-report",
        type=Path,
        help=(
            "sealed L3 analysis used only when an L4 independent grid fit fails; "
            "L4 must still independently support all 128 expected cell edges"
        ),
    )
    command.add_argument("--output", type=Path)
    compare = subparsers.add_parser("compare-repeat")
    compare.add_argument("--l3-report", type=Path, required=True)
    compare.add_argument("--l4-report", type=Path, required=True)
    compare.add_argument("--output", type=Path)
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
        else:
            result = compare_repeat(args.l3_report, args.l4_report)
        payload = json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        if args.output is not None:
            _write_exclusive(args.output, payload)
        else:
            sys.stdout.buffer.write(payload)
    except (V3PhotoAnalysisError, observation.ObservationError, OSError, ValueError) as exc:
        print(f"stable-code0 V3 photo analysis error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
