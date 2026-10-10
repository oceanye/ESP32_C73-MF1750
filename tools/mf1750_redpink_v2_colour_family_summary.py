#!/usr/bin/env python3
"""Derive camera-relative colour-family evidence from one Red/Pink V2 grid.

This companion deliberately consumes the immutable output of
``mf1750_redpink_v2_grid_photo_analyzer.py`` instead of changing that
analyzer's behaviour.  Broad family names and Lab clusters are exploratory
camera-relative descriptions.  They are never an absolute colour
calibration, a discrete colour count, or proof of a stable new colour.
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


SCHEMA_VERSION = 1
KIND = "mf1750-redpink-v2-camera-relative-colour-family-summary"
GRID_KIND = "mf1750-redpink-v2-dual-8x8-camera-relative-grid-photo-analysis"
GRID_SCHEMA_VERSION = 1
GRID_LAYOUT_ID = "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_V2"
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
CLUSTER_K_VALUES = tuple(range(2, 7))
CLUSTER_MIN_MEMBERS = 4
CLUSTER_MIN_SILHOUETTE = 0.50
STRUCTURED_LSTAR_RANGE_FLOOR = 6.0
STRUCTURED_CROSS_CONTROLLER_CORRELATION_FLOOR = 0.80


class ColourFamilySummaryError(RuntimeError):
    """Raised when input evidence or a requested output is invalid."""


class _DuplicateKeyError(ValueError):
    pass


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ColourFamilySummaryError(
            f"record contains a non-canonical JSON value: {exc}"
        ) from exc


def _sha256_bytes(payload: bytes) -> str:
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
            raise ColourFamilySummaryError(
                f"{label} must be a regular non-symlink file: {path}"
            )
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise ColourFamilySummaryError(f"cannot read {label}: {exc}") from exc
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_identity != after_identity or len(payload) != after.st_size:
        raise ColourFamilySummaryError(f"{label} changed while it was read")
    return payload


def _load_strict_json(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
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
        raise ColourFamilySummaryError(
            f"{label} is not strict UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise ColourFamilySummaryError(f"{label} root must be an object")
    return payload, value


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ColourFamilySummaryError(f"{label} must be an object")
    return value


def _text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ColourFamilySummaryError(f"{label} must be a non-empty string")
    return value


def _integer(value: Any, *, label: str) -> int:
    if type(value) is not int:
        raise ColourFamilySummaryError(f"{label} must be an integer")
    return value


def _number(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ColourFamilySummaryError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ColourFamilySummaryError(f"{label} must be a finite number")
    return result


def _vector(value: Any, *, length: int, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise ColourFamilySummaryError(f"{label} must contain {length} numbers")
    return [
        _number(item, label=f"{label}[{index}]") for index, item in enumerate(value)
    ]


def _verify_integrity(root: Mapping[str, Any], *, label: str) -> str:
    integrity = _mapping(root.get("integrity"), label=f"{label}.integrity")
    if set(integrity) != {"algorithm", "sha256"}:
        raise ColourFamilySummaryError(f"{label}.integrity keys differ")
    if integrity.get("algorithm") != INTEGRITY_ALGORITHM:
        raise ColourFamilySummaryError(f"{label}.integrity algorithm differs")
    declared = _text(integrity.get("sha256"), label=f"{label}.integrity.sha256")
    if len(declared) != 64 or any(
        character not in "0123456789abcdef" for character in declared
    ):
        raise ColourFamilySummaryError(f"{label}.integrity SHA-256 is malformed")
    unsigned = dict(root)
    unsigned.pop("integrity", None)
    if _sha256_bytes(_canonical_json(unsigned)) != declared:
        raise ColourFamilySummaryError(f"{label}.integrity SHA-256 differs")
    return declared


def _validate_source_photo_metadata(root: Mapping[str, Any]) -> dict[str, Any]:
    source_photo = _mapping(root.get("source_photo"), label="source_photo")
    photo_sha = _text(source_photo.get("sha256"), label="source_photo.sha256")
    if len(photo_sha) != 64 or any(
        character not in "0123456789abcdef" for character in photo_sha
    ):
        raise ColourFamilySummaryError("source_photo.sha256 is malformed")
    byte_count = _integer(source_photo.get("bytes"), label="source_photo.bytes")
    width = _integer(source_photo.get("width"), label="source_photo.width")
    height = _integer(source_photo.get("height"), label="source_photo.height")
    if byte_count < 1 or width < 1 or height < 1:
        raise ColourFamilySummaryError("source_photo size metadata is invalid")
    return {
        "path": _text(source_photo.get("path"), label="source_photo.path"),
        "bytes": byte_count,
        "sha256": photo_sha,
        "width": width,
        "height": height,
    }


def _validate_grid_report(root: Mapping[str, Any]) -> tuple[list[dict[str, Any]], str]:
    if (
        root.get("schema_version") != GRID_SCHEMA_VERSION
        or root.get("kind") != GRID_KIND
    ):
        raise ColourFamilySummaryError("grid-analysis schema identity differs")
    canonical_integrity = _verify_integrity(root, label="grid analysis")
    layout = _mapping(root.get("campaign_layout"), label="campaign_layout")
    if (
        layout.get("id") != GRID_LAYOUT_ID
        or layout.get("action_ordinal") != 4
        or layout.get("controllers_are_not_assumed_colour_equivalent") is not True
    ):
        raise ColourFamilySummaryError("grid-analysis Action4 layout identity differs")
    judgement = _mapping(root.get("grid_judgement"), label="grid_judgement")
    if judgement.get("enough_to_interpret_grid_camera_relatively") is not True:
        raise ColourFamilySummaryError(
            "grid analysis is insufficient for interpretation"
        )
    _validate_source_photo_metadata(root)
    raw_cells = root.get("cells")
    if not isinstance(raw_cells, list) or len(raw_cells) != 128:
        raise ColourFamilySummaryError("grid analysis must contain exactly 128 cells")

    cells: list[dict[str, Any]] = []
    observed: set[tuple[int, int, int]] = set()
    for index, raw_cell in enumerate(raw_cells):
        cell = _mapping(raw_cell, label=f"cells[{index}]")
        controller = _integer(
            cell.get("controller"), label=f"cells[{index}].controller"
        )
        row = _integer(cell.get("row"), label=f"cells[{index}].row")
        column = _integer(cell.get("column"), label=f"cells[{index}].column")
        key = (controller, row, column)
        if controller not in (0, 1) or row not in range(8) or column not in range(8):
            raise ColourFamilySummaryError(
                f"cells[{index}] coordinates are outside the dual 8x8 grid"
            )
        if key in observed:
            raise ColourFamilySummaryError(f"duplicate cell coordinate {key}")
        observed.add(key)
        expected_cell_id = f"C{controller}-R{row}-K{column}"
        expected_recipe = f"REDPINK-A{column}-B{row}-A0"
        if (
            cell.get("cell_id") != expected_cell_id
            or cell.get("recipe_id") != expected_recipe
        ):
            raise ColourFamilySummaryError(f"cells[{index}] identity differs")
        rgb = _vector(
            cell.get("robust_rgb_median"),
            length=3,
            label=f"cells[{index}].robust_rgb_median",
        )
        rgb_mad = _vector(
            cell.get("robust_rgb_mad"), length=3, label=f"cells[{index}].robust_rgb_mad"
        )
        lab = _vector(
            cell.get("camera_relative_lab"),
            length=3,
            label=f"cells[{index}].camera_relative_lab",
        )
        hsv_root = _mapping(
            cell.get("camera_relative_hsv"), label=f"cells[{index}].camera_relative_hsv"
        )
        if set(hsv_root) != {"hue_degrees", "saturation_percent", "value_percent"}:
            raise ColourFamilySummaryError(
                f"cells[{index}].camera_relative_hsv keys differ"
            )
        hsv = [
            _number(hsv_root.get("hue_degrees"), label=f"cells[{index}].hsv.hue"),
            _number(
                hsv_root.get("saturation_percent"),
                label=f"cells[{index}].hsv.saturation",
            ),
            _number(hsv_root.get("value_percent"), label=f"cells[{index}].hsv.value"),
        ]
        cells.append(
            {
                "cell_id": expected_cell_id,
                "recipe_id": expected_recipe,
                "controller": controller,
                "row": row,
                "column": column,
                "rgb": rgb,
                "rgb_mad": rgb_mad,
                "lab": lab,
                "hsv": hsv,
            }
        )
    expected = {
        (controller, row, column)
        for controller in range(2)
        for row in range(8)
        for column in range(8)
    }
    if observed != expected:
        raise ColourFamilySummaryError(
            "grid-analysis cell coordinate set is incomplete"
        )
    cells.sort(key=lambda item: (item["controller"], item["row"], item["column"]))
    return cells, canonical_integrity


def _lab_polar(lab: Sequence[float]) -> tuple[float, float]:
    a_star = float(lab[1])
    b_star = float(lab[2])
    chroma = math.hypot(a_star, b_star)
    hue = math.degrees(math.atan2(b_star, a_star)) % 360.0
    return chroma, hue


def _family_label(lab: Sequence[float]) -> str:
    chroma, hue = _lab_polar(lab)
    if chroma < 8.0:
        return "neutral-grey-white-direction"
    if hue >= 345.0 or hue < 25.0:
        return "red-pink-direction"
    if hue < 75.0:
        return "orange-ochre-warm-pink-direction"
    if hue < 125.0:
        return "yellow-olive-direction"
    if hue < 175.0:
        return "yellow-green-direction"
    if hue < 225.0:
        return "green-cyan-direction"
    if hue < 265.0:
        return "cyan-blue-direction"
    if hue < 305.0:
        return "blue-violet-direction"
    return "violet-magenta-direction"


def _silhouette(points: np.ndarray, labels: np.ndarray) -> float:
    unique = np.unique(labels)
    if len(unique) < 2:
        return 0.0
    distances = np.linalg.norm(points[:, None, :] - points[None, :, :], axis=2)
    scores: list[float] = []
    for index in range(len(points)):
        own = labels == labels[index]
        own[index] = False
        if not np.any(own):
            scores.append(0.0)
            continue
        within = float(np.mean(distances[index, own]))
        between = min(
            float(np.mean(distances[index, labels == other]))
            for other in unique
            if other != labels[index]
        )
        denominator = max(within, between)
        scores.append(0.0 if denominator == 0.0 else (between - within) / denominator)
    return float(np.mean(scores))


def _cluster_controller(cells: list[dict[str, Any]], controller: int) -> dict[str, Any]:
    group = [cell for cell in cells if cell["controller"] == controller]
    points = np.asarray([cell["lab"] for cell in group], dtype=np.float32)
    diagnostics: list[dict[str, Any]] = []
    fitted: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for cluster_count in CLUSTER_K_VALUES:
        cv2.setRNGSeed(1750 + controller * 100 + cluster_count)
        _compactness, labels_raw, centers = cv2.kmeans(
            points,
            cluster_count,
            None,
            (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-5),
            20,
            cv2.KMEANS_PP_CENTERS,
        )
        labels = labels_raw.reshape(-1).astype(np.int32)
        counts = np.bincount(labels, minlength=cluster_count)
        score = _silhouette(points.astype(np.float64), labels)
        eligible = int(np.min(counts)) >= CLUSTER_MIN_MEMBERS
        diagnostics.append(
            {
                "k": cluster_count,
                "silhouette": score,
                "minimum_cluster_size": int(np.min(counts)),
                "passes_minimum_cluster_size_guard": eligible,
            }
        )
        fitted[cluster_count] = (labels, centers.astype(np.float64))

    eligible_diagnostics = [
        item for item in diagnostics if item["passes_minimum_cluster_size_guard"]
    ]
    best = max(
        eligible_diagnostics,
        key=lambda item: (item["silhouette"], -item["k"]),
        default=None,
    )
    if best is None or float(best["silhouette"]) < CLUSTER_MIN_SILHOUETTE:
        selected_k = 1
        labels = np.zeros(len(group), dtype=np.int32)
        centers = np.median(points.astype(np.float64), axis=0, keepdims=True)
        selection_reason = "no-k-passed-both-silhouette-and-minimum-cluster-size-guards"
        selected_silhouette = None if best is None else float(best["silhouette"])
    else:
        selected_k = int(best["k"])
        labels, centers = fitted[selected_k]
        selection_reason = (
            "exploratory-best-silhouette-passing-minimum-cluster-size-guard"
        )
        selected_silhouette = float(best["silhouette"])

    raw_clusters: list[dict[str, Any]] = []
    for original_label in range(selected_k):
        member_indices = np.flatnonzero(labels == original_label)
        center = centers[original_label]
        member_points = points[member_indices].astype(np.float64)
        distances = np.linalg.norm(member_points - center, axis=1)
        medoid_local = min(
            range(len(member_indices)),
            key=lambda item: (
                float(distances[item]),
                group[int(member_indices[item])]["cell_id"],
            ),
        )
        medoid = group[int(member_indices[medoid_local])]
        chroma, hue = _lab_polar(center)
        raw_clusters.append(
            {
                "original_kmeans_label": original_label,
                "center_camera_relative_lab": center.astype(float).tolist(),
                "center_lstar": float(center[0]),
                "center_chroma_ab": chroma,
                "center_hue_ab_degrees": hue,
                "camera_relative_family_label": _family_label(center),
                "member_count": len(member_indices),
                "within_cluster_de76_p95": float(np.percentile(distances, 95)),
                "medoid_cell_id": medoid["cell_id"],
                "medoid_recipe_id": medoid["recipe_id"],
                "member_cell_ids": sorted(
                    group[int(item)]["cell_id"] for item in member_indices
                ),
                "member_recipe_ids": sorted(
                    {group[int(item)]["recipe_id"] for item in member_indices}
                ),
            }
        )
    raw_clusters.sort(
        key=lambda item: (
            item["center_lstar"],
            item["center_chroma_ab"],
            item["center_hue_ab_degrees"],
        )
    )
    assignments: list[dict[str, Any]] = []
    clusters: list[dict[str, Any]] = []
    label_to_band: dict[int, int] = {}
    for band_index, cluster in enumerate(raw_clusters):
        original_label = int(cluster.pop("original_kmeans_label"))
        label_to_band[original_label] = band_index
        clusters.append({"band_id": f"C{controller}-BAND-{band_index}", **cluster})
    for index, cell in enumerate(group):
        band_index = label_to_band[int(labels[index])]
        assignments.append(
            {
                "cell_id": cell["cell_id"],
                "recipe_id": cell["recipe_id"],
                "relative_appearance_band_id": f"C{controller}-BAND-{band_index}",
            }
        )
    return {
        "controller": controller,
        "k_sweep": diagnostics,
        "selected_exploratory_k": selected_k,
        "selected_silhouette": selected_silhouette,
        "selection_reason": selection_reason,
        "cluster_count_is_not_colour_count": True,
        "relative_appearance_bands": clusters,
        "cell_assignments": assignments,
    }


def _controller_envelope(
    cells: list[dict[str, Any]], controller: int
) -> dict[str, Any]:
    group = [cell for cell in cells if cell["controller"] == controller]
    rgb = np.asarray([cell["rgb"] for cell in group], dtype=np.float64)
    lab = np.asarray([cell["lab"] for cell in group], dtype=np.float64)
    hsv = np.asarray([cell["hsv"] for cell in group], dtype=np.float64)
    median_rgb = np.median(rgb, axis=0)
    median_lab = np.median(lab, axis=0)
    median_hsv = np.median(hsv, axis=0)
    chroma, hue = _lab_polar(median_lab)
    return {
        "controller": controller,
        "cell_count": len(group),
        "camera_relative_family_label": _family_label(median_lab),
        "median_rgb": median_rgb.astype(float).tolist(),
        "rgb_min": np.min(rgb, axis=0).astype(float).tolist(),
        "rgb_max": np.max(rgb, axis=0).astype(float).tolist(),
        "median_camera_relative_lab": median_lab.astype(float).tolist(),
        "camera_relative_lab_min": np.min(lab, axis=0).astype(float).tolist(),
        "camera_relative_lab_max": np.max(lab, axis=0).astype(float).tolist(),
        "median_lstar": float(median_lab[0]),
        "median_chroma_ab": chroma,
        "median_hue_ab_degrees": hue,
        "median_camera_relative_hsv": {
            "hue_degrees": float(median_hsv[0]),
            "saturation_percent": float(median_hsv[1]),
            "value_percent": float(median_hsv[2]),
        },
    }


def _pearson(left: np.ndarray, right: np.ndarray) -> float | None:
    if float(np.ptp(left)) == 0.0 or float(np.ptp(right)) == 0.0:
        return None
    value = float(np.corrcoef(left, right)[0, 1])
    return value if math.isfinite(value) else None


def _axis_effect(cells: list[dict[str, Any]], axis: str) -> dict[str, Any]:
    profiles: list[dict[str, Any]] = []
    lightness_profiles: list[np.ndarray] = []
    for controller in range(2):
        indices: list[dict[str, Any]] = []
        lightness: list[float] = []
        for index in range(8):
            group = [
                cell
                for cell in cells
                if cell["controller"] == controller and cell[axis] == index
            ]
            labs = np.asarray([cell["lab"] for cell in group], dtype=np.float64)
            center = np.median(labs, axis=0)
            chroma, hue = _lab_polar(center)
            lightness.append(float(center[0]))
            indices.append(
                {
                    "index": index,
                    "camera_relative_lab_median": center.astype(float).tolist(),
                    "lstar": float(center[0]),
                    "chroma_ab": chroma,
                    "hue_ab_degrees": hue,
                }
            )
        lightness_array = np.asarray(lightness, dtype=np.float64)
        lightness_profiles.append(lightness_array)
        profiles.append(
            {
                "controller": controller,
                "indices": indices,
                "lstar_range": float(np.ptp(lightness_array)),
            }
        )
    correlation = _pearson(lightness_profiles[0], lightness_profiles[1])
    both_ranges_pass = all(
        profile["lstar_range"] >= STRUCTURED_LSTAR_RANGE_FLOOR for profile in profiles
    )
    structured = bool(
        both_ranges_pass
        and correlation is not None
        and correlation >= STRUCTURED_CROSS_CONTROLLER_CORRELATION_FLOOR
    )
    return {
        "axis": axis,
        "profiles": profiles,
        "cross_controller_lstar_pearson": correlation,
        "structured_effect_detected": structured,
        "effect_state": (
            f"STRUCTURED_{axis.upper()}_EFFECT_CANDIDATE_POSITION_CONFOUNDED"
            if structured
            else f"NO_CROSS_CONTROLLER_STRUCTURED_{axis.upper()}_EFFECT_AT_FIXED_GUARDS"
        ),
    }


def _axis_lstar_profile(
    cells: list[dict[str, Any]], controller: int, axis: str
) -> np.ndarray:
    return np.asarray(
        [
            np.median(
                np.asarray(
                    [
                        cell["lab"][0]
                        for cell in cells
                        if cell["controller"] == controller and cell[axis] == index
                    ],
                    dtype=np.float64,
                )
            )
            for index in range(8)
        ],
        dtype=np.float64,
    )


def _repeatability_comparison(
    primary_cells: list[dict[str, Any]],
    repeat_cells: list[dict[str, Any]],
    *,
    repeat_path: Path,
    repeat_payload: bytes,
    repeat_root: Mapping[str, Any],
    repeat_integrity: str,
) -> dict[str, Any]:
    comparisons: list[dict[str, Any]] = []
    for controller in range(2):
        for axis in ("row", "column"):
            primary = _axis_lstar_profile(primary_cells, controller, axis)
            repeated = _axis_lstar_profile(repeat_cells, controller, axis)
            comparisons.append(
                {
                    "controller": controller,
                    "axis": axis,
                    "primary_lstar_profile": primary.astype(float).tolist(),
                    "repeat_lstar_profile": repeated.astype(float).tolist(),
                    "primary_repeat_lstar_pearson": _pearson(primary, repeated),
                }
            )
    repeat_photo = _validate_source_photo_metadata(repeat_root)
    return {
        "available": True,
        "source_repeat_grid_analysis": {
            "path": str(repeat_path),
            "bytes": len(repeat_payload),
            "file_sha256": _sha256_bytes(repeat_payload),
            "canonical_integrity_sha256": repeat_integrity,
            "source_photo": repeat_photo,
        },
        "axis_lstar_profile_comparisons": comparisons,
        "position_confounded_in_both_fixed_layout_captures": True,
        "repeat_correlation_does_not_qualify_a_colour_or_brightness_level": True,
    }


def summarize(
    grid_analysis_path: Path,
    photo_path: Path,
    repeat_grid_analysis_path: Path | None = None,
) -> dict[str, Any]:
    """Return one deterministic derived summary without writing a file."""

    grid_analysis_path = Path(grid_analysis_path)
    photo_path = Path(photo_path)
    grid_payload, grid_root = _load_strict_json(
        grid_analysis_path, label="grid analysis"
    )
    cells, grid_canonical_integrity = _validate_grid_report(grid_root)

    source_photo = _validate_source_photo_metadata(grid_root)
    declared_photo_sha = source_photo["sha256"]
    declared_photo_bytes = source_photo["bytes"]
    photo_payload = _read_stable_regular(photo_path, label="source photo")
    observed_photo_sha = _sha256_bytes(photo_payload)
    if (
        len(photo_payload) != declared_photo_bytes
        or observed_photo_sha != declared_photo_sha
    ):
        raise ColourFamilySummaryError(
            "source photo bytes or SHA-256 differ from grid analysis"
        )

    envelopes = [_controller_envelope(cells, controller) for controller in range(2)]
    clusters = [_cluster_controller(cells, controller) for controller in range(2)]
    effects = [_axis_effect(cells, axis) for axis in ("row", "column")]
    detected_axes = [
        item["axis"] for item in effects if item["structured_effect_detected"]
    ]
    if detected_axes:
        structured_state = (
            "STRUCTURED_"
            + "_AND_".join(axis.upper() for axis in detected_axes)
            + "_EFFECT_CANDIDATE_POSITION_CONFOUNDED"
        )
    else:
        structured_state = "NO_STRUCTURED_CROSS_CONTROLLER_EFFECT_AT_FIXED_GUARDS"

    ranking = _mapping(
        grid_root.get("candidate_ranking_metadata"), label="candidate_ranking_metadata"
    )
    repeatability: dict[str, Any] = {
        "available": False,
        "reason": "no repeat grid analysis supplied",
        "position_confounded_in_primary_fixed_layout_capture": True,
    }
    repeat_file_sha: str | None = None
    if repeat_grid_analysis_path is not None:
        repeat_path = Path(repeat_grid_analysis_path)
        if repeat_path.resolve() == grid_analysis_path.resolve():
            raise ColourFamilySummaryError(
                "repeat grid analysis must differ from primary grid analysis"
            )
        repeat_payload, repeat_root = _load_strict_json(
            repeat_path, label="repeat grid analysis"
        )
        repeat_cells, repeat_integrity = _validate_grid_report(repeat_root)
        repeat_file_sha = _sha256_bytes(repeat_payload)
        repeatability = _repeatability_comparison(
            cells,
            repeat_cells,
            repeat_path=repeat_path,
            repeat_payload=repeat_payload,
            repeat_root=repeat_root,
            repeat_integrity=repeat_integrity,
        )
    capture_count = 2 if repeat_grid_analysis_path is not None else 1
    stability_status = (
        "UNPROVEN_REPEAT_POSITION_CONFOUNDED"
        if repeat_grid_analysis_path is not None
        else "UNPROVEN_SINGLE_CAPTURE"
    )
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary_id": _sha256_bytes(
            _canonical_json(
                {
                    "grid_analysis_file_sha256": _sha256_bytes(grid_payload),
                    "grid_analysis_canonical_integrity_sha256": grid_canonical_integrity,
                    "photo_sha256": observed_photo_sha,
                    "repeat_grid_analysis_file_sha256": repeat_file_sha,
                    "method_revision": "redpink-v2-colour-family-summary-v1",
                }
            )
        ),
        "source_grid_analysis": {
            "path": str(grid_analysis_path),
            "bytes": len(grid_payload),
            "file_sha256": _sha256_bytes(grid_payload),
            "canonical_integrity_sha256": grid_canonical_integrity,
            "kind": GRID_KIND,
            "schema_version": GRID_SCHEMA_VERSION,
            "action_ordinal": 4,
        },
        "source_photo": {
            "path": str(photo_path),
            "bytes": len(photo_payload),
            "sha256": observed_photo_sha,
        },
        "method": {
            "physical_colour_calibrated": False,
            "absolute_colour_family_qualified": False,
            "broad_family_labels": "camera-relative nominal Lab hue/chroma sectors",
            "relative_clustering": "deterministic controller-local Lab k-means sweep",
            "k_values": list(CLUSTER_K_VALUES),
            "minimum_cluster_members": CLUSTER_MIN_MEMBERS,
            "minimum_selected_silhouette": CLUSTER_MIN_SILHOUETTE,
            "cluster_count_is_not_colour_count": True,
            "position_and_recipe_are_confounded_in_this_single_fixed_layout": True,
        },
        "controller_family_envelopes": envelopes,
        "controller_relative_lab_clustering": clusters,
        "structured_factor_effects": {
            "guards": {
                "minimum_lstar_range_each_controller": STRUCTURED_LSTAR_RANGE_FLOOR,
                "minimum_cross_controller_lstar_pearson": STRUCTURED_CROSS_CONTROLLER_CORRELATION_FLOOR,
            },
            "axes": effects,
            "structured_effect_state": structured_state,
            "cannot_distinguish_recipe_effect_from_physical_position_or_lighting": True,
        },
        "repeatability_comparison": repeatability,
        "existing_spatial_outlier_screen": {
            "camera_relative_spatial_assessment": ranking.get(
                "camera_relative_spatial_assessment"
            ),
            "obvious_spatial_outlier_cell_count": ranking.get(
                "obvious_spatial_outlier_cell_count"
            ),
            "obvious_paired_recipe_count": ranking.get("obvious_paired_recipe_count"),
            "scope": ranking.get("scope"),
            "does_not_exclude_smooth_row_or_column_effect": True,
        },
        "evidence_classification": {
            "capture_count": capture_count,
            "stability_status": stability_status,
            "structured_candidate_status": structured_state,
            "qualified_new_colour": False,
            "qualified_brightness_level": False,
            "repeat_or_persistence_proven": False,
            "absolute_colour_proven": False,
            "reasons": [
                "one uncalibrated camera capture cannot establish stability",
                "relative Lab clusters are exploratory appearance bands, not discrete physical colours",
                "recipe row and column are confounded with physical position in this layout",
                "a permuted repeat campaign is required before qualification",
            ],
        },
        "output_write_contract": "O_EXCL",
    }
    unsigned["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": _sha256_bytes(_canonical_json(unsigned)),
    }
    return unsigned


def _write_exclusive(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, flags, 0o644)
    except FileExistsError as exc:
        raise ColourFamilySummaryError(
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
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("summarize")
    command.add_argument("--grid-analysis", type=Path, required=True)
    command.add_argument("--photo", type=Path, required=True)
    command.add_argument("--repeat-grid-analysis", type=Path)
    command.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = summarize(
            args.grid_analysis,
            args.photo,
            repeat_grid_analysis_path=args.repeat_grid_analysis,
        )
        payload = (
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False).encode(
                "utf-8"
            )
            + b"\n"
        )
        _write_exclusive(args.output, payload)
        sys.stdout.buffer.write(payload)
        return 0
    except ColourFamilySummaryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
