#!/usr/bin/env python3
"""Analyze three OFF-white and three retained same-R20 4x8 photographs.

The result is camera-relative.  It uses the locked G1 homography, local
background contrast, and a same-position OFF-white residual.  It cannot prove
absolute colour, waveform bytes on the bus, or electrical controller parity.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
from typing import Any

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_same_r20_parity_4x8_v2_pack as pack  # noqa: E402


SCHEMA_VERSION = 1
KIND = "mf1750-same-r20-position-balanced-4x8-camera-relative-analysis"
G1_KIND = "mf1750-redpink-v2-dual-8x8-camera-relative-grid-photo-analysis"
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
THRESHOLD_DE76 = 6.603186815816113
BASELINE_NOISE_P95_DE76 = 2.2010622719387043
INNER_CROP_FRACTION = 0.56
MIN_VALID_FRACTION = 0.98
MIN_BACKGROUND_PIXELS = 96
PANEL_EXPOSURE_RIM_PX = 10
MIN_PANEL_MEDIAN_LSTAR = 25.0
MIN_ATLAS_PANEL_P95_P05_RANGE_LSTAR = 12.0
LOCKED_G0_MIN_PANEL_MEDIAN_LSTAR = 67.84313725490196
LOCKED_G1_PANEL_MEDIAN_LSTAR = 54.11764705882353
LOCKED_G1_PANEL_P95_P05_RANGE_LSTAR = 42.745098039215684

LOW_EXPOSURE_OR_DYNAMIC_RANGE_INVALID = "LOW_EXPOSURE_OR_DYNAMIC_RANGE_INVALID"
WHITE_BASELINE_OR_GEOMETRY_INVALID = "WHITE_BASELINE_OR_GEOMETRY_INVALID"
POSITION_DEPENDENT_INCONCLUSIVE = "POSITION_DEPENDENT_INCONCLUSIVE"
CODE_DEPENDENT_CONTROLLER_MISMATCH_CANDIDATE = (
    "CODE_DEPENDENT_CONTROLLER_MISMATCH_CANDIDATE"
)
RELATIVE_PALETTE_PARITY_PASS_SIDE_OFFSET_INCONCLUSIVE = (
    "RELATIVE_PALETTE_PARITY_PASS_SIDE_OFFSET_INCONCLUSIVE"
)
POSITION_OR_ILLUMINATION_DOMINATED = "POSITION_OR_ILLUMINATION_DOMINATED"
CAMERA_RELATIVE_PARITY_CANDIDATE = "CAMERA_RELATIVE_PARITY_CANDIDATE"
NORMALIZED_RESIDUAL_INCONCLUSIVE = "NORMALIZED_RESIDUAL_INCONCLUSIVE"


class PositionBalancedAnalysisError(RuntimeError):
    """Raised for invalid, mutable, or inconsistent evidence."""


class _DuplicateKeyError(ValueError):
    pass


def canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PositionBalancedAnalysisError(
            f"record contains a non-canonical JSON value: {exc}"
        ) from exc


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_stable_regular(path: Path, *, label: str) -> bytes:
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise PositionBalancedAnalysisError(
                f"{label} must be a regular non-symlink file: {path}"
            )
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise PositionBalancedAnalysisError(f"cannot read {label}: {exc}") from exc
    before_id = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_id = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_id != after_id or len(payload) != after.st_size:
        raise PositionBalancedAnalysisError(f"{label} changed while read")
    return payload


def _load_json(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    payload = _read_stable_regular(path, label=label)
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {item}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise PositionBalancedAnalysisError(
            f"{label} is not strict UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise PositionBalancedAnalysisError(f"{label} root must be an object")
    return payload, value


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PositionBalancedAnalysisError(f"{label} must be an object")
    return value


def _verify_integrity(root: Mapping[str, Any], *, label: str) -> str:
    integrity = _mapping(root.get("integrity"), label=f"{label}.integrity")
    if set(integrity) != {"algorithm", "sha256"}:
        raise PositionBalancedAnalysisError(f"{label} integrity keys differ")
    declared = integrity.get("sha256")
    if (
        integrity.get("algorithm") != INTEGRITY_ALGORITHM
        or not isinstance(declared, str)
        or len(declared) != 64
    ):
        raise PositionBalancedAnalysisError(f"{label} integrity differs")
    unsigned = dict(root)
    unsigned.pop("integrity", None)
    if sha256_bytes(canonical_json(unsigned)) != declared:
        raise PositionBalancedAnalysisError(f"{label} integrity SHA differs")
    return declared


def _load_g1(path: Path) -> tuple[dict[str, Any], np.ndarray]:
    payload, root = _load_json(path, label="G1 analysis")
    _verify_integrity(root, label="G1 analysis")
    if root.get("kind") != G1_KIND:
        raise PositionBalancedAnalysisError("G1 analysis kind differs")
    quality = _mapping(root.get("geometry_quality"), label="G1 geometry_quality")
    if (
        quality.get("homography_inliers") != 128
        or quality.get("homography_correspondences") != 128
        or float(quality.get("homography_inlier_fraction", 0.0)) != 1.0
        or float(quality.get("homography_inlier_rmse_px", math.inf)) > 2.0
        or float(quality.get("homography_inlier_p95_px", math.inf)) > 3.0
    ):
        raise PositionBalancedAnalysisError("G1 homography quality gate failed")
    matrix = np.asarray(quality.get("homography_logical_to_photo"), dtype=np.float64)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise PositionBalancedAnalysisError("G1 homography matrix is invalid")
    if abs(float(np.linalg.det(matrix))) < 1e-12:
        raise PositionBalancedAnalysisError("G1 homography matrix is singular")
    return {
        "path": path.as_posix(),
        "bytes": len(payload),
        "file_sha256": sha256_bytes(payload),
        "integrity_sha256": root["integrity"]["sha256"],
        "homography_inliers": 128,
        "homography_rmse_px": quality["homography_inlier_rmse_px"],
        "homography_p95_px": quality["homography_inlier_p95_px"],
    }, matrix


def _decode_photo(path: Path, *, label: str) -> tuple[dict[str, Any], np.ndarray]:
    payload = _read_stable_regular(path, label=label)
    image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        raise PositionBalancedAnalysisError(f"{label} is not a colour image")
    return {
        "path": path.as_posix(),
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
        "width": int(image.shape[1]),
        "height": int(image.shape[0]),
    }, image


def _lab_from_rgb(rgb: np.ndarray) -> np.ndarray:
    sample = np.uint8(np.clip(np.rint(rgb), 0, 255)).reshape(1, 1, 3)
    lab = cv2.cvtColor(sample, cv2.COLOR_RGB2LAB)[0, 0].astype(np.float64)
    lab[0] *= 100.0 / 255.0
    lab[1:] -= 128.0
    return lab


def _delta(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.linalg.norm(left - right))


def _lab_list(value: np.ndarray) -> list[float]:
    return [float(item) for item in value]


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        raise PositionBalancedAnalysisError("cannot take percentile of no samples")
    return float(np.percentile(np.asarray(values, dtype=np.float64), percentile))


def _rectified(
    image: np.ndarray, homography: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    inverse = np.linalg.inv(homography)
    result = cv2.warpPerspective(
        image,
        inverse,
        (pack.base.WIDTH, pack.base.HEIGHT),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )
    valid_source = np.full(image.shape[:2], 255, dtype=np.uint8)
    valid = cv2.warpPerspective(
        valid_source,
        inverse,
        (pack.base.WIDTH, pack.base.HEIGHT),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    return result, valid


def _panel_exposure_metrics(
    image: np.ndarray, homography: np.ndarray, *, frame_index: int, role: str
) -> dict[str, Any]:
    """Measure camera-relative panel lightness without adapting any threshold."""

    rectified, valid = _rectified(image, homography)
    rim = PANEL_EXPOSURE_RIM_PX
    interior = np.zeros(valid.shape, dtype=bool)
    interior[rim : pack.base.HEIGHT - rim, rim : pack.base.WIDTH - rim] = True
    expected_pixels = int(np.count_nonzero(interior))
    mask = interior & (valid > 0)
    valid_pixels = int(np.count_nonzero(mask))
    valid_fraction = valid_pixels / expected_pixels if expected_pixels else 0.0
    if valid_pixels < 1024 or valid_fraction < MIN_VALID_FRACTION:
        raise PositionBalancedAnalysisError(
            f"{role} frame {frame_index} panel exposure region is not fully visible"
        )
    lab = cv2.cvtColor(rectified, cv2.COLOR_BGR2LAB)
    lightness = lab[:, :, 0][mask].astype(np.float64) * (100.0 / 255.0)
    p05 = float(np.percentile(lightness, 5.0))
    median = float(np.median(lightness))
    p95 = float(np.percentile(lightness, 95.0))
    dynamic_range = p95 - p05
    return {
        "role": role,
        "frame_index": frame_index,
        "valid_pixel_count": valid_pixels,
        "valid_fraction": valid_fraction,
        "panel_lightness_p05_lstar": p05,
        "panel_lightness_median_lstar": median,
        "panel_lightness_p95_lstar": p95,
        "panel_lightness_p95_minus_p05_lstar": dynamic_range,
        "panel_median_floor_pass": median >= MIN_PANEL_MEDIAN_LSTAR,
        "atlas_dynamic_range_floor_applicable": role == "atlas",
        "atlas_dynamic_range_floor_pass": (
            dynamic_range >= MIN_ATLAS_PANEL_P95_P05_RANGE_LSTAR
            if role == "atlas"
            else None
        ),
    }


def _patch_lab(
    image: np.ndarray,
    valid: np.ndarray,
    bounds: tuple[int, int, int, int],
    *,
    label: str,
    minimum_pixels: int = 64,
) -> tuple[np.ndarray, float, int]:
    x0, y0, x1, y1 = bounds
    if not (0 <= x0 < x1 <= image.shape[1] and 0 <= y0 < y1 <= image.shape[0]):
        raise PositionBalancedAnalysisError(f"{label} bounds are invalid")
    patch = image[y0:y1, x0:x1]
    mask = valid[y0:y1, x0:x1] > 0
    count = int(np.count_nonzero(mask))
    fraction = float(np.mean(mask))
    if count < minimum_pixels or fraction < MIN_VALID_FRACTION:
        raise PositionBalancedAnalysisError(f"{label} is not fully visible")
    rgb = patch[mask][:, ::-1].astype(np.float64)
    return _lab_from_rgb(np.median(rgb, axis=0)), fraction, count


def _cell_and_background(
    image: np.ndarray,
    valid: np.ndarray,
    controller: int,
    row: int,
    column: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    local_x, y, width, height = pack.cell_bounds(row, column)
    x = controller * pack.base.CONTROLLER_WIDTH + local_x
    mx = round(width * (1.0 - INNER_CROP_FRACTION) / 2.0)
    my = round(height * (1.0 - INNER_CROP_FRACTION) / 2.0)
    cell, cell_valid, cell_pixels = _patch_lab(
        image,
        valid,
        (x + mx, y + my, x + width - mx, y + height - my),
        label="cell patch",
    )
    strips: list[np.ndarray] = []
    strip_valid: list[float] = []
    strip_pixels = 0
    candidates = (
        (x + 4, max(0, y - 14), x + width - 4, max(0, y - 4)),
        (
            x + 4,
            min(pack.base.HEIGHT, y + height + 4),
            x + width - 4,
            min(pack.base.HEIGHT, y + height + 14),
        ),
        (
            max(controller * 512, x - 6),
            y + 8,
            max(controller * 512, x - 2),
            y + height - 8,
        ),
        (
            min((controller + 1) * 512, x + width + 2),
            y + 8,
            min((controller + 1) * 512, x + width + 6),
            y + height - 8,
        ),
    )
    for index, bounds in enumerate(candidates):
        if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            continue
        lab, fraction, pixels = _patch_lab(
            image,
            valid,
            bounds,
            label=f"background strip {index}",
            minimum_pixels=16,
        )
        strips.append(lab)
        strip_valid.append(fraction)
        strip_pixels += pixels
    if len(strips) < 2 or strip_pixels < MIN_BACKGROUND_PIXELS:
        raise PositionBalancedAnalysisError("local background support is invalid")
    background = np.median(np.stack(strips), axis=0)
    return (
        cell,
        background,
        {
            "cell_valid_fraction": cell_valid,
            "cell_pixels": cell_pixels,
            "background_strip_count": len(strips),
            "background_min_valid_fraction": min(strip_valid),
            "background_pixels": strip_pixels,
        },
    )


def _sample_frame(
    image: np.ndarray, homography: np.ndarray, *, frame_index: int, role: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rectified, valid = _rectified(image, homography)
    samples: list[dict[str, Any]] = []
    min_cell_valid = 1.0
    min_background_valid = 1.0
    min_background_pixels = 1 << 30
    for controller in range(2):
        for row in range(pack.GRID_ROWS):
            for column in range(pack.GRID_COLUMNS):
                cell, background, quality = _cell_and_background(
                    rectified, valid, controller, row, column
                )
                min_cell_valid = min(min_cell_valid, quality["cell_valid_fraction"])
                min_background_valid = min(
                    min_background_valid, quality["background_min_valid_fraction"]
                )
                min_background_pixels = min(
                    min_background_pixels, quality["background_pixels"]
                )
                samples.append(
                    {
                        "role": role,
                        "frame_index": frame_index,
                        "controller": controller,
                        "row": row,
                        "column": column,
                        "code": pack.CODE_ROWS[row][column],
                        "cell_lab": _lab_list(cell),
                        "background_lab": _lab_list(background),
                        "local_contrast_lab": _lab_list(cell - background),
                        "quality": quality,
                    }
                )
    return samples, {
        "sample_count": len(samples),
        "minimum_cell_valid_fraction": min_cell_valid,
        "minimum_background_valid_fraction": min_background_valid,
        "minimum_background_pixels": min_background_pixels,
    }


def _key(sample: Mapping[str, Any]) -> tuple[int, int, int]:
    return int(sample["controller"]), int(sample["row"]), int(sample["column"])


def _vector(sample: Mapping[str, Any], field: str) -> np.ndarray:
    value = np.asarray(sample[field], dtype=np.float64)
    if value.shape != (3,) or not np.all(np.isfinite(value)):
        raise PositionBalancedAnalysisError(f"invalid Lab vector in {field}")
    return value


def analyze(
    *,
    g1_analysis: Path,
    white_photos: Sequence[Path],
    atlas_photos: Sequence[Path],
) -> dict[str, Any]:
    if len(white_photos) != 3 or len(atlas_photos) != 3:
        raise PositionBalancedAnalysisError(
            "exactly three OFF white and three OFF retained-atlas photos are required"
        )
    g1_binding, homography = _load_g1(g1_analysis)
    identities: dict[str, list[dict[str, Any]]] = {"white": [], "atlas": []}
    sampled: dict[str, list[list[dict[str, Any]]]] = {"white": [], "atlas": []}
    frame_quality: dict[str, list[dict[str, Any]]] = {"white": [], "atlas": []}
    exposure_frames: dict[str, list[dict[str, Any]]] = {"white": [], "atlas": []}
    expected_shape: tuple[int, int] | None = None
    geometry_error: str | None = None
    for role, paths in (("white", white_photos), ("atlas", atlas_photos)):
        for index, path in enumerate(paths, 1):
            identity, image = _decode_photo(path, label=f"{role} photo {index}")
            shape = (image.shape[1], image.shape[0])
            if expected_shape is None:
                expected_shape = shape
            elif shape != expected_shape:
                raise PositionBalancedAnalysisError("six photo dimensions differ")
            identities[role].append(identity)
            try:
                exposure = _panel_exposure_metrics(
                    image, homography, frame_index=index, role=role
                )
                frame_samples, quality = _sample_frame(
                    image, homography, frame_index=index, role=role
                )
            except PositionBalancedAnalysisError as exc:
                geometry_error = str(exc)
                frame_samples = []
                quality = {"valid": False, "error": str(exc)}
                exposure = {
                    "role": role,
                    "frame_index": index,
                    "valid": False,
                    "error": str(exc),
                }
            sampled[role].append(frame_samples)
            frame_quality[role].append(quality)
            exposure_frames[role].append(exposure)

    white_noise: list[float] = []
    white_position_contrast: dict[tuple[int, int, int], np.ndarray] = {}
    if geometry_error is None:
        for controller in range(2):
            for row in range(pack.GRID_ROWS):
                for column in range(pack.GRID_COLUMNS):
                    key = (controller, row, column)
                    records = [
                        next(item for item in frame if _key(item) == key)
                        for frame in sampled["white"]
                    ]
                    raw = np.stack([_vector(item, "cell_lab") for item in records])
                    center = np.median(raw, axis=0)
                    white_noise.extend(_delta(value, center) for value in raw)
                    contrasts = np.stack(
                        [_vector(item, "local_contrast_lab") for item in records]
                    )
                    white_position_contrast[key] = np.median(contrasts, axis=0)
    white_noise_p95 = _percentile(white_noise, 95.0) if white_noise else math.inf

    records_by_code_controller: dict[tuple[int, int], list[dict[str, Any]]] = {}
    position_medians: dict[tuple[int, int], list[np.ndarray]] = {}
    if geometry_error is None:
        for controller in range(2):
            for code in range(8):
                records_by_code_controller[(controller, code)] = []
                position_medians[(controller, code)] = []
        for frame in sampled["atlas"]:
            for item in frame:
                key = _key(item)
                normalized = (
                    _vector(item, "local_contrast_lab") - white_position_contrast[key]
                )
                enriched = dict(item)
                enriched["white_residual_lab"] = _lab_list(white_position_contrast[key])
                enriched["normalized_lab"] = _lab_list(normalized)
                records_by_code_controller[(key[0], int(item["code"]))].append(enriched)
        for controller in range(2):
            for code in range(8):
                for row in range(pack.GRID_ROWS):
                    columns = [
                        column
                        for column in range(pack.GRID_COLUMNS)
                        if pack.CODE_ROWS[row][column] == code
                    ]
                    for column in columns:
                        values = [
                            _vector(item, "normalized_lab")
                            for item in records_by_code_controller[(controller, code)]
                            if int(item["row"]) == row and int(item["column"]) == column
                        ]
                        if len(values) != 3:
                            raise PositionBalancedAnalysisError(
                                "one code position does not have three retained frames"
                            )
                        position_medians[(controller, code)].append(
                            np.median(np.stack(values), axis=0)
                        )

    per_code: list[dict[str, Any]] = []
    position_p95_values: list[float] = []
    raw_differences: list[float] = []
    normalized_side_vectors: list[np.ndarray] = []
    centers: dict[tuple[int, int, str], np.ndarray] = {}
    if geometry_error is None:
        for code in range(8):
            controller_records: list[dict[str, Any]] = []
            for controller in range(2):
                records = records_by_code_controller[(controller, code)]
                if len(records) != 12 or len(position_medians[(controller, code)]) != 4:
                    raise PositionBalancedAnalysisError(
                        "each code/controller must contribute 12 samples at four positions"
                    )
                raw_center = np.median(
                    np.stack([_vector(item, "cell_lab") for item in records]), axis=0
                )
                normalized_center = np.median(
                    np.stack([_vector(item, "normalized_lab") for item in records]),
                    axis=0,
                )
                centers[(controller, code, "raw")] = raw_center
                centers[(controller, code, "normalized")] = normalized_center
                dispersions = [
                    _delta(value, normalized_center)
                    for value in position_medians[(controller, code)]
                ]
                position_p95 = _percentile(dispersions, 95.0)
                position_p95_values.append(position_p95)
                controller_records.append(
                    {
                        "controller": controller,
                        "sample_count": 12,
                        "position_count": 4,
                        "raw_center_lab": _lab_list(raw_center),
                        "normalized_center_lab": _lab_list(normalized_center),
                        "position_median_dispersion_de76": dispersions,
                        "position_median_dispersion_p95_de76": position_p95,
                    }
                )
            raw = _delta(centers[(0, code, "raw")], centers[(1, code, "raw")])
            raw_differences.append(raw)
            side_vector = (
                centers[(0, code, "normalized")] - centers[(1, code, "normalized")]
            )
            normalized_side_vectors.append(side_vector)
            per_code.append(
                {
                    "code": code,
                    "controllers": controller_records,
                    "raw_left_right_de76": raw,
                    "normalized_left_minus_right_lab": _lab_list(side_vector),
                    "normalized_left_right_de76": float(np.linalg.norm(side_vector)),
                }
            )

    common_side = (
        np.median(np.stack(normalized_side_vectors), axis=0)
        if normalized_side_vectors
        else np.full(3, math.nan)
    )
    common_side_magnitude = (
        float(np.linalg.norm(common_side))
        if np.all(np.isfinite(common_side))
        else math.inf
    )
    interactions: list[float] = []
    for item, vector in zip(per_code, normalized_side_vectors, strict=True):
        interaction = float(np.linalg.norm(vector - common_side))
        interactions.append(interaction)
        item["interaction_after_common_side_offset_lab"] = _lab_list(
            vector - common_side
        )
        item["interaction_after_common_side_offset_de76"] = interaction

    max_position = max(position_p95_values, default=math.inf)
    max_interaction = max(interactions, default=math.inf)
    max_raw = max(raw_differences, default=math.inf)
    max_normalized = max(
        (item["normalized_left_right_de76"] for item in per_code),
        default=math.inf,
    )
    valid_exposure_frames = [
        item
        for role in ("white", "atlas")
        for item in exposure_frames[role]
        if item.get("valid") is not False
    ]
    minimum_panel_median = min(
        (float(item["panel_lightness_median_lstar"]) for item in valid_exposure_frames),
        default=-math.inf,
    )
    minimum_atlas_dynamic_range = min(
        (
            float(item["panel_lightness_p95_minus_p05_lstar"])
            for item in exposure_frames["atlas"]
            if item.get("valid") is not False
        ),
        default=-math.inf,
    )
    exposure_gate_pass = (
        len(valid_exposure_frames) == 6
        and minimum_panel_median >= MIN_PANEL_MEDIAN_LSTAR
        and minimum_atlas_dynamic_range >= MIN_ATLAS_PANEL_P95_P05_RANGE_LSTAR
    )
    if geometry_error is None and not exposure_gate_pass:
        classification = LOW_EXPOSURE_OR_DYNAMIC_RANGE_INVALID
    elif geometry_error is not None or white_noise_p95 > THRESHOLD_DE76:
        classification = WHITE_BASELINE_OR_GEOMETRY_INVALID
    elif max_position > THRESHOLD_DE76:
        classification = POSITION_DEPENDENT_INCONCLUSIVE
    elif max_interaction > THRESHOLD_DE76:
        classification = CODE_DEPENDENT_CONTROLLER_MISMATCH_CANDIDATE
    elif common_side_magnitude > THRESHOLD_DE76:
        classification = RELATIVE_PALETTE_PARITY_PASS_SIDE_OFFSET_INCONCLUSIVE
    elif max_raw > THRESHOLD_DE76:
        classification = POSITION_OR_ILLUMINATION_DOMINATED
    elif max_normalized <= THRESHOLD_DE76:
        classification = CAMERA_RELATIVE_PARITY_CANDIDATE
    else:
        classification = NORMALIZED_RESIDUAL_INCONCLUSIVE

    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "classification": classification,
        "candidate_only": True,
        "absolute_colour_proven": False,
        "electrical_controller_equivalence_proven": False,
        "controller_bus_capture_proven": False,
        "layout_id": pack.VARIANT_KEY,
        "campaign_id": pack.CAMPAIGN_ID,
        "contract_id": pack.build_report()["contract_id"],
        "threshold_contract": {
            "prior_locked_white_temporal_noise_p95_de76": BASELINE_NOISE_P95_DE76,
            "formula": "max(4.0,3*prior_locked_white_temporal_noise_p95_de76)",
            "threshold_de76": THRESHOLD_DE76,
            "automatic_relaxation": False,
        },
        "exposure_quality": {
            "method": (
                "OpenCV camera-relative Lab over the rectified valid logical panel "
                "excluding a fixed 10-pixel rim"
            ),
            "fixed_panel_median_floor_lstar": MIN_PANEL_MEDIAN_LSTAR,
            "fixed_atlas_p95_minus_p05_floor_lstar": (
                MIN_ATLAS_PANEL_P95_P05_RANGE_LSTAR
            ),
            "reference_evidence": {
                "locked_g0_three_frame_minimum_panel_median_lstar": (
                    LOCKED_G0_MIN_PANEL_MEDIAN_LSTAR
                ),
                "locked_g1_panel_median_lstar": LOCKED_G1_PANEL_MEDIAN_LSTAR,
                "locked_g1_panel_p95_minus_p05_lstar": (
                    LOCKED_G1_PANEL_P95_P05_RANGE_LSTAR
                ),
                "floor_policy": (
                    "fixed conservative floors below the locked G0/G1 observations; "
                    "never recomputed or relaxed from candidate frames"
                ),
            },
            "minimum_observed_panel_median_lstar": minimum_panel_median,
            "minimum_observed_atlas_p95_minus_p05_lstar": (minimum_atlas_dynamic_range),
            "frames": exposure_frames,
            "pass": exposure_gate_pass,
        },
        "algorithm": {
            "colour_space": "camera-relative CIE Lab via OpenCV",
            "cell_estimator": "per-channel median over inner 56 percent",
            "local_background_estimator": "median of four adjacent background strips",
            "white_residual": (
                "same-position median OFF-white local contrast subtracted from "
                "retained-atlas local contrast"
            ),
            "code_controller_center": "componentwise median of 12 normalized samples",
            "position_dispersion": (
                "P95 of four three-frame position-median Lab distances to "
                "the code/controller center"
            ),
            "common_side_offset": (
                "componentwise median across eight code left-minus-right vectors"
            ),
            "interaction": "code side vector minus common side offset",
        },
        "g1_binding": g1_binding,
        "photo_sets": identities,
        "geometry": {
            "valid": geometry_error is None,
            "error": geometry_error,
            "frame_quality": frame_quality,
            "expected_photo_dimensions": list(expected_shape or (0, 0)),
        },
        "white_temporal_noise": {
            "sample_distance_count": len(white_noise),
            "p95_de76": white_noise_p95,
            "threshold_de76": THRESHOLD_DE76,
            "pass": white_noise_p95 <= THRESHOLD_DE76,
        },
        "position_balance": {
            "required_samples_per_code_per_controller": 12,
            "required_positions_per_code_per_controller": 4,
            "maximum_position_dispersion_p95_de76": max_position,
            "threshold_de76": THRESHOLD_DE76,
            "pass": max_position <= THRESHOLD_DE76,
        },
        "controller_comparison": {
            "common_side_offset_lab": _lab_list(common_side),
            "common_side_offset_de76": common_side_magnitude,
            "maximum_raw_left_right_de76": max_raw,
            "maximum_normalized_left_right_de76": max_normalized,
            "maximum_code_dependent_interaction_de76": max_interaction,
            "threshold_de76": THRESHOLD_DE76,
            "per_code": per_code,
        },
        "decision_order": [
            LOW_EXPOSURE_OR_DYNAMIC_RANGE_INVALID,
            WHITE_BASELINE_OR_GEOMETRY_INVALID,
            POSITION_DEPENDENT_INCONCLUSIVE,
            CODE_DEPENDENT_CONTROLLER_MISMATCH_CANDIDATE,
            RELATIVE_PALETTE_PARITY_PASS_SIDE_OFFSET_INCONCLUSIVE,
            POSITION_OR_ILLUMINATION_DOMINATED,
            CAMERA_RELATIVE_PARITY_CANDIDATE,
        ],
        "output_write_contract": "O_EXCL",
    }
    result["analysis_id"] = sha256_bytes(canonical_json(result))
    result["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": sha256_bytes(canonical_json(result)),
    }
    return result


def write_new(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(
            value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
        ).encode("utf-8")
        + b"\n"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise PositionBalancedAnalysisError(f"output already exists: {path}") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--g1-analysis", type=Path, required=True)
    parser.add_argument("--white-photo", type=Path, action="append", required=True)
    parser.add_argument("--atlas-photo", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = analyze(
            g1_analysis=args.g1_analysis,
            white_photos=args.white_photo,
            atlas_photos=args.atlas_photo,
        )
        write_new(args.output, result)
    except PositionBalancedAnalysisError as exc:
        print(f"same-R20 4x8 analysis error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
