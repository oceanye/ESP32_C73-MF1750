#!/usr/bin/env python3
"""Compare sealed Batch-1 AA and CC same-R20 paired-atlas analyses.

This tool is deliberately offline.  It verifies both upstream canonical
seals, their shared layout/reference-geometry/noise bindings, all 16 cells,
all eight left/right pairs, and both controller-match gates before deriving
camera-relative AA-to-CC Lab changes.  Its exploratory labels are neither
absolute-colour measurements nor claims that a new colour was discovered.
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
import statistics
import sys
from typing import Any


SCHEMA_VERSION = 1
KIND = "mf1750-same-r20-aa-cc-paired-atlas-comparison-v1"
ANALYSIS_SCHEMA_VERSION = 1
ANALYSIS_KIND = "mf1750-same-r20-dual-controller-2x4-camera-relative-atlas-analysis"
ANALYSIS_METHOD_ID = "same-r20-reference-homography-paired-atlas-v1"
LAYOUT_ID = "L535_SAME_R20_DUAL_CONTROLLER_PARITY_2X4_V1"
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
METHOD_ID = "same-r20-aa-to-cc-controller-paired-camera-relative-lab-v1"

CONTROLLER_COUNT = 2
GRID_ROWS = 2
GRID_COLUMNS = 4
CODE_COUNT = GRID_ROWS * GRID_COLUMNS
LOGICAL_WIDTH = 1024
CONTROLLER_WIDTH = 512
GRID_X0 = 40
GRID_Y0 = 120
CELL_WIDTH = 96
CELL_HEIGHT = 120
GAP_X = 20
GAP_Y = 40
MINIMUM_REQUIRED_CONTRASTING_CELLS = 8
MINIMUM_VALID_FRACTION = 0.98
ALIGNMENT_CONTRAST_FLOOR_DE76 = 5.0

R20_LINKED_EXPLORATORY_EFFECT = "R20_LINKED_EXPLORATORY_EFFECT"
NO_RESOLVED_EFFECT = "NO_RESOLVED_EFFECT"
CONTROLLER_INCONSISTENT = "CONTROLLER_INCONSISTENT"


class SameR20AACCComparisonError(RuntimeError):
    """Raised when sealed inputs or an exclusive output are invalid."""


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
        raise SameR20AACCComparisonError(
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
            raise SameR20AACCComparisonError(
                f"{label} must be a regular non-symlink file: {path}"
            )
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise SameR20AACCComparisonError(f"cannot read {label}: {exc}") from exc
    before_id = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_id = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_id != after_id or len(payload) != after.st_size:
        raise SameR20AACCComparisonError(f"{label} changed while read")
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
        raise SameR20AACCComparisonError(
            f"{label} is not strict UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise SameR20AACCComparisonError(f"{label} root must be an object")
    return payload, value


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SameR20AACCComparisonError(f"{label} must be an object")
    return value


def _number(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SameR20AACCComparisonError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise SameR20AACCComparisonError(f"{label} must be a finite number")
    return result


def _integer(value: Any, *, label: str) -> int:
    if type(value) is not int:
        raise SameR20AACCComparisonError(f"{label} must be an integer")
    return value


def _sha256(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise SameR20AACCComparisonError(f"{label} must be a lowercase SHA-256")
    return value


def _vector(value: Any, *, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise SameR20AACCComparisonError(f"{label} must contain three numbers")
    return [
        _number(item, label=f"{label}[{index}]") for index, item in enumerate(value)
    ]


def _close(first: float, second: float) -> bool:
    return math.isclose(first, second, rel_tol=1e-12, abs_tol=1e-9)


def _same_vector(first: Sequence[float], second: Sequence[float]) -> bool:
    return len(first) == len(second) and all(
        _close(left, right) for left, right in zip(first, second, strict=True)
    )


def _norm(vector: Sequence[float]) -> float:
    return math.sqrt(sum(component * component for component in vector))


def _difference(first: Sequence[float], second: Sequence[float]) -> list[float]:
    return [left - right for left, right in zip(first, second, strict=True)]


def _clean_vector(vector: Sequence[float]) -> list[float]:
    return [
        0.0 if abs(component) <= 1e-12 else float(component) for component in vector
    ]


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        raise SameR20AACCComparisonError("percentile values are empty")
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _verify_integrity(root: Mapping[str, Any], *, label: str) -> str:
    integrity = _mapping(root.get("integrity"), label=f"{label}.integrity")
    if set(integrity) != {"algorithm", "sha256"}:
        raise SameR20AACCComparisonError(f"{label}.integrity keys differ")
    if integrity.get("algorithm") != INTEGRITY_ALGORITHM:
        raise SameR20AACCComparisonError(f"{label}.integrity algorithm differs")
    declared = _sha256(integrity.get("sha256"), label=f"{label}.integrity.sha256")
    unsigned = dict(root)
    unsigned.pop("integrity", None)
    if _sha256_bytes(_canonical_json(unsigned)) != declared:
        raise SameR20AACCComparisonError(f"{label}.integrity SHA differs")
    return declared


def _logical_bounds(controller: int, row: int, column: int) -> list[int]:
    x0 = controller * CONTROLLER_WIDTH + GRID_X0 + column * (CELL_WIDTH + GAP_X)
    y0 = GRID_Y0 + row * (CELL_HEIGHT + GAP_Y)
    return [x0, y0, x0 + CELL_WIDTH, y0 + CELL_HEIGHT]


def _validate_layout(root: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    layout = _mapping(root.get("layout"), label=f"{label}.layout")
    expected = {
        "id": LAYOUT_ID,
        "controller_count": CONTROLLER_COUNT,
        "rows": GRID_ROWS,
        "columns_per_controller": GRID_COLUMNS,
        "code_mapping": "code = row * 4 + column",
        "same_dtm_both_controllers": True,
    }
    if dict(layout) != expected:
        raise SameR20AACCComparisonError(f"{label}.layout differs")
    return expected


def _validate_source_photo(root: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    source = _mapping(root.get("source_photo"), label=f"{label}.source_photo")
    if set(source) != {"path", "bytes", "sha256", "width", "height"}:
        raise SameR20AACCComparisonError(f"{label}.source_photo keys differ")
    path = source.get("path")
    size = _integer(source.get("bytes"), label=f"{label}.source_photo.bytes")
    width = _integer(source.get("width"), label=f"{label}.source_photo.width")
    height = _integer(source.get("height"), label=f"{label}.source_photo.height")
    if not isinstance(path, str) or not path or size <= 0 or width <= 0 or height <= 0:
        raise SameR20AACCComparisonError(f"{label}.source_photo metadata differs")
    return {
        "path": path,
        "bytes": size,
        "sha256": _sha256(source.get("sha256"), label=f"{label}.source_photo.sha256"),
        "width": width,
        "height": height,
    }


def _validate_reference_geometry(
    root: Mapping[str, Any], *, label: str
) -> dict[str, Any]:
    geometry = _mapping(
        root.get("reference_geometry"), label=f"{label}.reference_geometry"
    )
    expected_keys = {
        "path",
        "bytes",
        "file_sha256",
        "canonical_integrity_sha256",
        "camera_must_not_have_moved",
    }
    if set(geometry) != expected_keys:
        raise SameR20AACCComparisonError(f"{label}.reference_geometry keys differ")
    path = geometry.get("path")
    size = _integer(geometry.get("bytes"), label=f"{label}.reference_geometry.bytes")
    if not isinstance(path, str) or not path or size <= 0:
        raise SameR20AACCComparisonError(f"{label}.reference_geometry metadata differs")
    if geometry.get("camera_must_not_have_moved") is not True:
        raise SameR20AACCComparisonError(
            f"{label}.reference_geometry fixed-camera contract differs"
        )
    return {
        "path": path,
        "bytes": size,
        "file_sha256": _sha256(
            geometry.get("file_sha256"),
            label=f"{label}.reference_geometry.file_sha256",
        ),
        "canonical_integrity_sha256": _sha256(
            geometry.get("canonical_integrity_sha256"),
            label=f"{label}.reference_geometry.canonical_integrity_sha256",
        ),
        "camera_must_not_have_moved": True,
    }


def _validate_geometry_guard(
    root: Mapping[str, Any],
    *,
    minimum_cell_valid_fraction: float,
    contrasting_cell_count: int,
    label: str,
) -> None:
    guard = _mapping(root.get("geometry_guard"), label=f"{label}.geometry_guard")
    expected_keys = {
        "minimum_inner_patch_valid_fraction",
        "contrasting_cell_count",
        "minimum_required_contrasting_cells",
        "reference_homography_alignment_guard_pass",
    }
    if set(guard) != expected_keys:
        raise SameR20AACCComparisonError(f"{label}.geometry_guard keys differ")
    valid_fraction = _number(
        guard.get("minimum_inner_patch_valid_fraction"),
        label=f"{label}.geometry_guard.minimum_inner_patch_valid_fraction",
    )
    contrasting = _integer(
        guard.get("contrasting_cell_count"),
        label=f"{label}.geometry_guard.contrasting_cell_count",
    )
    required = _integer(
        guard.get("minimum_required_contrasting_cells"),
        label=f"{label}.geometry_guard.minimum_required_contrasting_cells",
    )
    recomputed = valid_fraction >= MINIMUM_VALID_FRACTION and contrasting >= required
    if (
        not 0.0 <= valid_fraction <= 1.0
        or not 0 <= contrasting <= CONTROLLER_COUNT * CODE_COUNT
        or required != MINIMUM_REQUIRED_CONTRASTING_CELLS
        or not _close(valid_fraction, minimum_cell_valid_fraction)
        or contrasting != contrasting_cell_count
        or guard.get("reference_homography_alignment_guard_pass") is not recomputed
        or recomputed is not True
    ):
        raise SameR20AACCComparisonError(f"{label}.geometry_guard did not pass")


def _validate_cells(
    root: Mapping[str, Any], *, label: str
) -> tuple[dict[tuple[int, int], list[float]], float, int]:
    raw_cells = root.get("cells")
    if not isinstance(raw_cells, list) or len(raw_cells) != 16:
        raise SameR20AACCComparisonError(f"{label}.cells must contain exactly 16 cells")
    expected_keys = {
        "cell_id",
        "controller",
        "row",
        "column",
        "code",
        "logical_bounds",
        "inner_patch_valid_fraction",
        "robust_rgb_median",
        "robust_rgb_mad",
        "camera_relative_lab",
        "cell_to_top_separator_de76",
    }
    cells: dict[tuple[int, int], list[float]] = {}
    valid_fractions: list[float] = []
    contrasting_cell_count = 0
    for index, raw_cell in enumerate(raw_cells):
        cell = _mapping(raw_cell, label=f"{label}.cells[{index}]")
        if set(cell) != expected_keys:
            raise SameR20AACCComparisonError(f"{label}.cells[{index}] keys differ")
        controller = _integer(
            cell.get("controller"), label=f"{label}.cells[{index}].controller"
        )
        row = _integer(cell.get("row"), label=f"{label}.cells[{index}].row")
        column = _integer(cell.get("column"), label=f"{label}.cells[{index}].column")
        code = _integer(cell.get("code"), label=f"{label}.cells[{index}].code")
        if (
            controller not in range(CONTROLLER_COUNT)
            or row not in range(GRID_ROWS)
            or column not in range(GRID_COLUMNS)
            or code != row * GRID_COLUMNS + column
            or cell.get("cell_id") != f"C{controller}-CODE{code}"
            or cell.get("logical_bounds") != _logical_bounds(controller, row, column)
        ):
            raise SameR20AACCComparisonError(
                f"{label}.cells[{index}] identity or coordinate differs"
            )
        key = (controller, code)
        if key in cells:
            raise SameR20AACCComparisonError(f"{label}.cells duplicate {key}")
        valid_fraction = _number(
            cell.get("inner_patch_valid_fraction"),
            label=f"{label}.cells[{index}].inner_patch_valid_fraction",
        )
        rgb = _vector(
            cell.get("robust_rgb_median"),
            label=f"{label}.cells[{index}].robust_rgb_median",
        )
        mad = _vector(
            cell.get("robust_rgb_mad"),
            label=f"{label}.cells[{index}].robust_rgb_mad",
        )
        lab = _vector(
            cell.get("camera_relative_lab"),
            label=f"{label}.cells[{index}].camera_relative_lab",
        )
        separator = _number(
            cell.get("cell_to_top_separator_de76"),
            label=f"{label}.cells[{index}].cell_to_top_separator_de76",
        )
        if (
            not MINIMUM_VALID_FRACTION <= valid_fraction <= 1.0
            or any(not 0.0 <= component <= 255.0 for component in rgb)
            or any(not 0.0 <= component <= 255.0 for component in mad)
            or not 0.0 <= lab[0] <= 100.0
            or any(not -128.0 <= component <= 127.0 for component in lab[1:])
            or separator < 0.0
        ):
            raise SameR20AACCComparisonError(
                f"{label}.cells[{index}] sampled value differs"
            )
        cells[key] = lab
        valid_fractions.append(valid_fraction)
        contrasting_cell_count += int(separator >= ALIGNMENT_CONTRAST_FLOOR_DE76)
    expected = {
        (controller, code)
        for controller in range(CONTROLLER_COUNT)
        for code in range(CODE_COUNT)
    }
    if set(cells) != expected:
        raise SameR20AACCComparisonError(f"{label}.cells coverage differs")
    return cells, min(valid_fractions), contrasting_cell_count


def _validate_pairs(
    root: Mapping[str, Any],
    cells: Mapping[tuple[int, int], Sequence[float]],
    *,
    label: str,
) -> list[float]:
    raw_pairs = root.get("left_right_pairs")
    if not isinstance(raw_pairs, list) or len(raw_pairs) != CODE_COUNT:
        raise SameR20AACCComparisonError(
            f"{label}.left_right_pairs must contain exactly eight pairs"
        )
    expected_keys = {
        "code",
        "camera_relative_de76",
        "absolute_lstar_difference",
        "cs1_lab",
        "cs2_lab",
    }
    deltas: dict[int, float] = {}
    for index, raw_pair in enumerate(raw_pairs):
        pair = _mapping(raw_pair, label=f"{label}.left_right_pairs[{index}]")
        if set(pair) != expected_keys:
            raise SameR20AACCComparisonError(
                f"{label}.left_right_pairs[{index}] keys differ"
            )
        code = _integer(
            pair.get("code"), label=f"{label}.left_right_pairs[{index}].code"
        )
        if code not in range(CODE_COUNT) or code in deltas:
            raise SameR20AACCComparisonError(
                f"{label}.left_right_pairs[{index}] code differs"
            )
        cs1 = _vector(
            pair.get("cs1_lab"), label=f"{label}.left_right_pairs[{index}].cs1_lab"
        )
        cs2 = _vector(
            pair.get("cs2_lab"), label=f"{label}.left_right_pairs[{index}].cs2_lab"
        )
        if not _same_vector(cs1, cells[(0, code)]) or not _same_vector(
            cs2, cells[(1, code)]
        ):
            raise SameR20AACCComparisonError(
                f"{label}.left_right_pairs[{index}] Lab binding differs"
            )
        computed_delta = _norm(_difference(cs1, cs2))
        declared_delta = _number(
            pair.get("camera_relative_de76"),
            label=f"{label}.left_right_pairs[{index}].camera_relative_de76",
        )
        declared_lstar = _number(
            pair.get("absolute_lstar_difference"),
            label=f"{label}.left_right_pairs[{index}].absolute_lstar_difference",
        )
        if not _close(declared_delta, computed_delta) or not _close(
            declared_lstar, abs(cs1[0] - cs2[0])
        ):
            raise SameR20AACCComparisonError(
                f"{label}.left_right_pairs[{index}] derived metric differs"
            )
        deltas[code] = computed_delta
    if set(deltas) != set(range(CODE_COUNT)):
        raise SameR20AACCComparisonError(f"{label}.left_right_pairs coverage differs")
    return [deltas[code] for code in range(CODE_COUNT)]


def _validate_summary_and_gate(
    root: Mapping[str, Any], deltas: Sequence[float], *, label: str
) -> tuple[float, float]:
    summary = _mapping(root.get("paired_summary"), label=f"{label}.paired_summary")
    expected_keys = {
        "camera_relative_de76_median",
        "camera_relative_de76_p95",
        "camera_relative_de76_max",
        "repeat_noise_p95_de76",
        "exploratory_threshold_de76",
        "all_pairs_within_exploratory_threshold",
    }
    if set(summary) != expected_keys:
        raise SameR20AACCComparisonError(f"{label}.paired_summary keys differ")
    noise = _number(
        summary.get("repeat_noise_p95_de76"),
        label=f"{label}.paired_summary.repeat_noise_p95_de76",
    )
    threshold = _number(
        summary.get("exploratory_threshold_de76"),
        label=f"{label}.paired_summary.exploratory_threshold_de76",
    )
    expected_threshold = max(4.0, 3.0 * noise)
    declared_median = _number(
        summary.get("camera_relative_de76_median"),
        label=f"{label}.paired_summary.camera_relative_de76_median",
    )
    declared_p95 = _number(
        summary.get("camera_relative_de76_p95"),
        label=f"{label}.paired_summary.camera_relative_de76_p95",
    )
    declared_maximum = _number(
        summary.get("camera_relative_de76_max"),
        label=f"{label}.paired_summary.camera_relative_de76_max",
    )
    recomputed_gate = all(delta <= expected_threshold for delta in deltas)
    if (
        noise < 0.0
        or not _close(threshold, expected_threshold)
        or not _close(declared_median, statistics.median(deltas))
        or not _close(declared_p95, _percentile(deltas, 0.95))
        or not _close(declared_maximum, max(deltas))
        or summary.get("all_pairs_within_exploratory_threshold") is not recomputed_gate
        or recomputed_gate is not True
    ):
        raise SameR20AACCComparisonError(f"{label}.paired_summary gate did not pass")
    classification = _mapping(
        root.get("classification"), label=f"{label}.classification"
    )
    expected_classification = {
        "state": "CAMERA_RELATIVE_CONTROLLER_MATCH_CANDIDATE",
        "controller_equivalence_proven": False,
        "absolute_colour_proven": False,
        "qualified_new_colour": False,
    }
    if dict(classification) != expected_classification:
        raise SameR20AACCComparisonError(f"{label}.classification gate did not pass")
    return noise, expected_threshold


def _validate_boundaries(root: Mapping[str, Any], *, label: str) -> None:
    boundaries = _mapping(
        root.get("evidence_boundaries"), label=f"{label}.evidence_boundaries"
    )
    required = {
        "camera_relative_de76_not_calibrated_de00": True,
        "reference_homography_reuse_requires_fixed_camera": True,
        "compiled_identical_payload_does_not_prove_bus_reception": True,
        "device_io_performed": False,
    }
    if any(boundaries.get(key) is not value for key, value in required.items()):
        raise SameR20AACCComparisonError(f"{label}.evidence_boundaries differ")
    if root.get("output_write_contract") != "O_EXCL":
        raise SameR20AACCComparisonError(f"{label}.output write contract differs")


def _validate_analysis(path: Path, *, expected_role: str) -> dict[str, Any]:
    label = f"{expected_role} analysis"
    payload, root = _load_json(path, label=label)
    if (
        root.get("schema_version") != ANALYSIS_SCHEMA_VERSION
        or root.get("kind") != ANALYSIS_KIND
        or root.get("role") != expected_role
    ):
        raise SameR20AACCComparisonError(f"{label} schema identity or role differs")
    integrity = _verify_integrity(root, label=label)
    layout = _validate_layout(root, label=label)
    source_photo = _validate_source_photo(root, label=label)
    reference_geometry = _validate_reference_geometry(root, label=label)
    declared_analysis_id = _sha256(
        root.get("analysis_id"), label=f"{label}.analysis_id"
    )
    expected_analysis_id = _sha256_bytes(
        _canonical_json(
            {
                "photo_sha256": source_photo["sha256"],
                "reference_file_sha256": reference_geometry["file_sha256"],
                "role": expected_role,
                "method": ANALYSIS_METHOD_ID,
            }
        )
    )
    if declared_analysis_id != expected_analysis_id:
        raise SameR20AACCComparisonError(f"{label}.analysis_id binding differs")
    cells, minimum_valid_fraction, contrasting_count = _validate_cells(
        root, label=label
    )
    _validate_geometry_guard(
        root,
        minimum_cell_valid_fraction=minimum_valid_fraction,
        contrasting_cell_count=contrasting_count,
        label=label,
    )
    deltas = _validate_pairs(root, cells, label=label)
    noise, threshold = _validate_summary_and_gate(root, deltas, label=label)
    _validate_boundaries(root, label=label)
    return {
        "payload": payload,
        "analysis_id": declared_analysis_id,
        "integrity": integrity,
        "layout": layout,
        "source_photo": source_photo,
        "reference_geometry": reference_geometry,
        "cells": cells,
        "noise": noise,
        "threshold": threshold,
    }


def _cross_validate(
    aa: Mapping[str, Any], cc: Mapping[str, Any]
) -> tuple[float, float]:
    if aa["layout"] != cc["layout"]:
        raise SameR20AACCComparisonError("AA and CC layouts differ")
    aa_reference = aa["reference_geometry"]
    cc_reference = cc["reference_geometry"]
    for key in ("bytes", "file_sha256", "canonical_integrity_sha256"):
        if aa_reference[key] != cc_reference[key]:
            raise SameR20AACCComparisonError(
                "AA and CC reference geometry bindings differ"
            )
    aa_photo = aa["source_photo"]
    cc_photo = cc["source_photo"]
    if (aa_photo["width"], aa_photo["height"]) != (
        cc_photo["width"],
        cc_photo["height"],
    ):
        raise SameR20AACCComparisonError("AA and CC photo geometries differ")
    if float(aa["noise"]) != float(cc["noise"]):
        raise SameR20AACCComparisonError("AA and CC repeat-noise baselines differ")
    if not _close(float(aa["threshold"]), float(cc["threshold"])):
        raise SameR20AACCComparisonError("AA and CC exploratory thresholds differ")
    return float(aa["noise"]), float(aa["threshold"])


def compare(aa_analysis: Path, cc_analysis: Path) -> dict[str, Any]:
    """Return one sealed AA-vs-CC comparison without device or network I/O."""

    if aa_analysis.resolve() == cc_analysis.resolve():
        raise SameR20AACCComparisonError("AA and CC analysis files must differ")
    aa = _validate_analysis(aa_analysis, expected_role="AA")
    cc = _validate_analysis(cc_analysis, expected_role="CC")
    noise, threshold = _cross_validate(aa, cc)

    controller_code_deltas: list[dict[str, Any]] = []
    by_key: dict[tuple[int, int], dict[str, Any]] = {}
    for controller in range(CONTROLLER_COUNT):
        for code in range(CODE_COUNT):
            aa_lab = list(aa["cells"][(controller, code)])
            cc_lab = list(cc["cells"][(controller, code)])
            change = _difference(cc_lab, aa_lab)
            magnitude = _norm(change)
            record = {
                "delta_id": f"C{controller}-CODE{code}-AA-TO-CC",
                "controller": controller,
                "controller_label": "CS1" if controller == 0 else "CS2",
                "code": code,
                "aa_camera_relative_lab": aa_lab,
                "cc_camera_relative_lab": cc_lab,
                "aa_to_cc_lab_change_vector": _clean_vector(change),
                "aa_to_cc_camera_relative_de76": magnitude,
                "exceeds_exploratory_threshold": magnitude > threshold,
            }
            controller_code_deltas.append(record)
            by_key[(controller, code)] = record

    code_results: list[dict[str, Any]] = []
    counts = {
        R20_LINKED_EXPLORATORY_EFFECT: 0,
        NO_RESOLVED_EFFECT: 0,
        CONTROLLER_INCONSISTENT: 0,
    }
    code_lists = {key: [] for key in counts}
    for code in range(CODE_COUNT):
        left = by_key[(0, code)]
        right = by_key[(1, code)]
        left_magnitude = float(left["aa_to_cc_camera_relative_de76"])
        right_magnitude = float(right["aa_to_cc_camera_relative_de76"])
        vector_disagreement = _norm(
            _difference(
                left["aa_to_cc_lab_change_vector"],
                right["aa_to_cc_lab_change_vector"],
            )
        )
        if (
            left_magnitude > threshold
            and right_magnitude > threshold
            and vector_disagreement <= threshold
        ):
            state = R20_LINKED_EXPLORATORY_EFFECT
        elif left_magnitude <= threshold and right_magnitude <= threshold:
            state = NO_RESOLVED_EFFECT
        else:
            state = CONTROLLER_INCONSISTENT
        counts[state] += 1
        code_lists[state].append(code)
        code_results.append(
            {
                "code": code,
                "controller_delta_ids": [left["delta_id"], right["delta_id"]],
                "cs1_aa_to_cc_camera_relative_de76": left_magnitude,
                "cs2_aa_to_cc_camera_relative_de76": right_magnitude,
                "left_right_change_vector_de76": vector_disagreement,
                "classification": state,
                "r20_linked_effect_is_exploratory_only": state
                == R20_LINKED_EXPLORATORY_EFFECT,
            }
        )

    if counts[CONTROLLER_INCONSISTENT]:
        overall_state = "CONTROLLER_INCONSISTENT_CODES_PRESENT"
    elif counts[R20_LINKED_EXPLORATORY_EFFECT]:
        overall_state = "R20_LINKED_EXPLORATORY_EFFECT_CODES_PRESENT"
    else:
        overall_state = "NO_RESOLVED_AA_TO_CC_EFFECT"

    aa_payload = aa["payload"]
    cc_payload = cc["payload"]
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "comparison_id": _sha256_bytes(
            _canonical_json(
                {
                    "aa_file_sha256": _sha256_bytes(aa_payload),
                    "cc_file_sha256": _sha256_bytes(cc_payload),
                    "method": METHOD_ID,
                    "repeat_noise_p95_de76": noise,
                }
            )
        ),
        "inputs": {
            "aa": {
                "path": str(aa_analysis),
                "bytes": len(aa_payload),
                "file_sha256": _sha256_bytes(aa_payload),
                "canonical_integrity_sha256": aa["integrity"],
                "analysis_id": aa["analysis_id"],
                "role": "AA",
                "source_photo_sha256": aa["source_photo"]["sha256"],
            },
            "cc": {
                "path": str(cc_analysis),
                "bytes": len(cc_payload),
                "file_sha256": _sha256_bytes(cc_payload),
                "canonical_integrity_sha256": cc["integrity"],
                "analysis_id": cc["analysis_id"],
                "role": "CC",
                "source_photo_sha256": cc["source_photo"]["sha256"],
            },
        },
        "shared_bindings": {
            "layout": aa["layout"],
            "reference_geometry": {
                "bytes": aa["reference_geometry"]["bytes"],
                "file_sha256": aa["reference_geometry"]["file_sha256"],
                "canonical_integrity_sha256": aa["reference_geometry"][
                    "canonical_integrity_sha256"
                ],
                "camera_must_not_have_moved": True,
            },
            "photo_geometry": {
                "width": aa["source_photo"]["width"],
                "height": aa["source_photo"]["height"],
            },
            "repeat_noise_p95_de76": noise,
            "aa_controller_pair_gate_pass": True,
            "cc_controller_pair_gate_pass": True,
        },
        "thresholds": {
            "exploratory_threshold_de76": threshold,
            "formula": "max(4.0, 3.0 * repeat_noise_p95_de76)",
            "effect_rule": "both controller magnitudes > threshold",
            "change_vector_consistency_rule": (
                "left_right_change_vector_de76 <= threshold"
            ),
        },
        "controller_code_deltas": controller_code_deltas,
        "code_results": code_results,
        "summary": {
            "code_count": CODE_COUNT,
            "controller_code_delta_count": CONTROLLER_COUNT * CODE_COUNT,
            "classification_counts": counts,
            "classification_code_lists": code_lists,
        },
        "classification": {
            "state": overall_state,
            "absolute_colour_proven": False,
            "qualified_new_colour": False,
            "r20_causality_proven": False,
        },
        "evidence_boundaries": {
            "camera_relative_lab_only": True,
            "delta_e76_is_not_calibrated_delta_e00": True,
            "r20_linked_label_is_exploratory_not_causal_proof": True,
            "absolute_colour_not_proven": True,
            "new_colour_not_proven": True,
            "input_controller_match_gates_are_candidates_not_equivalence_proofs": True,
            "device_io_performed": False,
            "network_io_performed": False,
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
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, flags, 0o644)
    except FileExistsError as exc:
        raise SameR20AACCComparisonError(
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
    parser.add_argument("--aa-analysis", type=Path, required=True)
    parser.add_argument("--cc-analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = compare(args.aa_analysis, args.cc_analysis)
        payload = (
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False).encode(
                "utf-8"
            )
            + b"\n"
        )
        _write_exclusive(args.output, payload)
        sys.stdout.buffer.write(payload)
        return 0
    except SameR20AACCComparisonError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
