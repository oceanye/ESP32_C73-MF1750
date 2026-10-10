#!/usr/bin/env python3
"""Compare three sealed T1-AC and three sealed T2-CA crossover analyses.

This tool is deliberately offline.  It accepts only the fresh RAW-P16
position-balanced single-frame analysis schema defined below, verifies every
stage/campaign/contract/action/frame/DTM binding, recomputes all four-position
statistics, and compares two symmetric explanations:

* the observed endpoint follows the active/commented profile when it swaps
  controllers; or
* the observed endpoint remains attached to physical CS1/CS2.

All labels are camera-relative diagnostics.  They never qualify an absolute,
stable, repeatable, or new colour.
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


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_position_balanced_pack as pack,
)


SCHEMA_VERSION = 1
KIND = "mf1750-raw-p16-crossover-t1-t2-profile-comparison-v1"
PREFLIGHT_SCHEMA_VERSION = 2
PREFLIGHT_V1_KIND = (
    "mf1750-raw-p16-crossover-position-balanced-t1-position-temporal-preflight-v1"
)
PREFLIGHT_KIND = (
    "mf1750-raw-p16-crossover-position-balanced-t1-position-temporal-preflight-v2"
)
INPUT_SCHEMA_VERSION = 1
INPUT_KIND = "mf1750-raw-p16-crossover-position-balanced-single-frame-analysis-v1"
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
METHOD_ID = "raw-p16-t1-ac-vs-t2-ca-position-balanced-profile-side-model-v1"

T1_STAGE = "t1-ac"
T2_STAGE = "t2-ca"
INPUTS_PER_STAGE = 3
CONTROLLER_COUNT = 2
CODE_COUNT = 8
POSITIONS_PER_CODE_CONTROLLER = 4

PRIOR_LOCKED_WHITE_TEMPORAL_NOISE_P95_DE76 = 2.2010622719387043
POSITION_AND_REPEAT_TOLERANCE_DE76 = 6.603186815816113
EFFECT_MULTIPLIER = 2.0
MIN_PANEL_AREA_FRACTION = 0.08
MIN_PROJECTED_CELL_SIDE_PX = 20.0

PRIMARY_CODES = (3, 5, 6, 7)
GUARD_CODES = (4,)
CONTROL_CODES = (0, 1, 2)
PRIORITY_ORDER = (*PRIMARY_CODES, *GUARD_CODES, *CONTROL_CODES)

INCONCLUSIVE = "INCONCLUSIVE"
PROFILE_FOLLOWING_CANDIDATE = "PROFILE_FOLLOWING_CANDIDATE"
SIDE_FOLLOWING_CANDIDATE = "SIDE_FOLLOWING_CANDIDATE"


class CrossoverProfileComparisonError(RuntimeError):
    """Raised for invalid inputs or a non-exclusive output."""


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
        raise CrossoverProfileComparisonError(
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
            raise CrossoverProfileComparisonError(
                f"{label} must be a regular non-symlink file: {path}"
            )
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise CrossoverProfileComparisonError(f"cannot read {label}: {exc}") from exc
    before_id = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_id = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_id != after_id or len(payload) != after.st_size:
        raise CrossoverProfileComparisonError(f"{label} changed while read")
    return payload


def _load_json(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    payload = _read_stable_regular(path, label=label)
    try:
        root = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {item}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise CrossoverProfileComparisonError(
            f"{label} is not strict UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(root, dict):
        raise CrossoverProfileComparisonError(f"{label} root must be an object")
    return payload, root


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CrossoverProfileComparisonError(f"{label} must be an object")
    return value


def _integer(value: Any, *, label: str) -> int:
    if type(value) is not int:
        raise CrossoverProfileComparisonError(f"{label} must be an integer")
    return value


def _number(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CrossoverProfileComparisonError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise CrossoverProfileComparisonError(f"{label} must be a finite number")
    return result


def _sha256(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CrossoverProfileComparisonError(f"{label} must be a lowercase SHA-256")
    return value


def _vector(value: Any, *, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise CrossoverProfileComparisonError(f"{label} must contain three numbers")
    result = [
        _number(item, label=f"{label}[{index}]") for index, item in enumerate(value)
    ]
    if not 0.0 <= result[0] <= 100.0 or any(
        not -128.0 <= component <= 127.0 for component in result[1:]
    ):
        raise CrossoverProfileComparisonError(f"{label} is outside CIE Lab bounds")
    return result


def _close(first: float, second: float) -> bool:
    return math.isclose(first, second, rel_tol=1e-9, abs_tol=1e-6)


def _same_vector(first: Sequence[float], second: Sequence[float]) -> bool:
    return len(first) == len(second) and all(
        _close(left, right) for left, right in zip(first, second, strict=True)
    )


def _difference(first: Sequence[float], second: Sequence[float]) -> list[float]:
    return [left - right for left, right in zip(first, second, strict=True)]


def _norm(vector: Sequence[float]) -> float:
    return math.sqrt(sum(component * component for component in vector))


def _distance(first: Sequence[float], second: Sequence[float]) -> float:
    return _norm(_difference(first, second))


def _median_vector(vectors: Sequence[Sequence[float]]) -> list[float]:
    if not vectors:
        raise CrossoverProfileComparisonError("cannot take a median of no vectors")
    return [
        float(statistics.median(vector[index] for vector in vectors))
        for index in range(3)
    ]


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        raise CrossoverProfileComparisonError("cannot take a percentile of no values")
    ordered = sorted(float(value) for value in values)
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
        raise CrossoverProfileComparisonError(f"{label}.integrity keys differ")
    if integrity.get("algorithm") != INTEGRITY_ALGORITHM:
        raise CrossoverProfileComparisonError(f"{label}.integrity algorithm differs")
    declared = _sha256(integrity.get("sha256"), label=f"{label}.integrity.sha256")
    unsigned = dict(root)
    unsigned.pop("integrity", None)
    if sha256_bytes(canonical_json(unsigned)) != declared:
        raise CrossoverProfileComparisonError(f"{label}.integrity SHA differs")
    return declared


def _expected_binding(stage: str) -> dict[str, Any]:
    report = pack.build_report(stage)
    action = report["actions"][0]
    return {
        "stage": stage,
        "campaign_id": report["contract"]["campaign_id"],
        "contract_id": report["contract_id"],
        "action_id": action["action_id"],
        "frame_sha256": action["frame"]["sha256"],
        "cs1_dtm_sha256": action["cs1_dtm"]["sha256"],
        "cs2_dtm_sha256": action["cs2_dtm"]["sha256"],
    }


def _expected_profiles(stage: str) -> dict[int, str]:
    cfg = pack.STAGES[stage]
    return {0: cfg.cs1_profile, 1: cfg.cs2_profile}


def _expected_positions(code: int) -> list[tuple[int, int]]:
    return [
        (row, column)
        for row, codes in enumerate(pack.CODE_ROWS)
        for column, observed in enumerate(codes)
        if observed == code
    ]


def _validate_layout(value: Any, *, label: str) -> dict[str, Any]:
    layout = _mapping(value, label=f"{label}.layout")
    expected = {
        "id": pack.layout.VARIANT_KEY,
        "controller_count": CONTROLLER_COUNT,
        "rows": pack.GRID_ROWS,
        "columns_per_controller": pack.GRID_COLUMNS,
        "row_codes": [list(row) for row in pack.CODE_ROWS],
        "positions_per_code_per_controller": POSITIONS_PER_CODE_CONTROLLER,
        "same_dtm_both_controllers": True,
    }
    if dict(layout) != expected:
        raise CrossoverProfileComparisonError(f"{label}.layout differs")
    return expected


def _validate_geometry(value: Any, *, label: str) -> dict[str, Any]:
    geometry = _mapping(value, label=f"{label}.geometry")
    expected_keys = {
        "valid",
        "fixed_camera",
        "camera_lock_id",
        "homography_logical_to_photo",
        "sampling_geometry_admitted",
        "historical_g1_homography_reused",
        "all_projected_cells_inside_photo",
        "automatic_cell_lattice_reprojection_proven",
        "panel_area_fraction_of_photo",
        "minimum_required_panel_area_fraction",
        "minimum_projected_cell_side_px",
        "minimum_required_projected_cell_side_px",
    }
    if set(geometry) != expected_keys:
        raise CrossoverProfileComparisonError(f"{label}.geometry keys differ")
    if geometry.get("valid") is not True or geometry.get("fixed_camera") is not True:
        raise CrossoverProfileComparisonError(f"{label}.geometry did not pass")
    camera_lock_id = _sha256(
        geometry.get("camera_lock_id"), label=f"{label}.geometry.camera_lock_id"
    )
    matrix = geometry.get("homography_logical_to_photo")
    if not isinstance(matrix, list) or len(matrix) != 3:
        raise CrossoverProfileComparisonError(
            f"{label}.geometry homography must be 3x3"
        )
    normalized_matrix: list[list[float]] = []
    for row_index, raw_row in enumerate(matrix):
        if not isinstance(raw_row, list) or len(raw_row) != 3:
            raise CrossoverProfileComparisonError(
                f"{label}.geometry homography must be 3x3"
            )
        normalized_matrix.append(
            [
                _number(
                    item,
                    label=(
                        f"{label}.geometry.homography_logical_to_photo"
                        f"[{row_index}][{column_index}]"
                    ),
                )
                for column_index, item in enumerate(raw_row)
            ]
        )
    determinant = (
        normalized_matrix[0][0]
        * (
            normalized_matrix[1][1] * normalized_matrix[2][2]
            - normalized_matrix[1][2] * normalized_matrix[2][1]
        )
        - normalized_matrix[0][1]
        * (
            normalized_matrix[1][0] * normalized_matrix[2][2]
            - normalized_matrix[1][2] * normalized_matrix[2][0]
        )
        + normalized_matrix[0][2]
        * (
            normalized_matrix[1][0] * normalized_matrix[2][1]
            - normalized_matrix[1][1] * normalized_matrix[2][0]
        )
    )
    panel_area = _number(
        geometry.get("panel_area_fraction_of_photo"),
        label=f"{label}.geometry.panel_area_fraction_of_photo",
    )
    required_panel_area = _number(
        geometry.get("minimum_required_panel_area_fraction"),
        label=f"{label}.geometry.minimum_required_panel_area_fraction",
    )
    minimum_side = _number(
        geometry.get("minimum_projected_cell_side_px"),
        label=f"{label}.geometry.minimum_projected_cell_side_px",
    )
    required_side = _number(
        geometry.get("minimum_required_projected_cell_side_px"),
        label=f"{label}.geometry.minimum_required_projected_cell_side_px",
    )
    if (
        abs(determinant) < 1e-12
        or geometry.get("sampling_geometry_admitted") is not True
        or geometry.get("historical_g1_homography_reused") is not False
        or geometry.get("all_projected_cells_inside_photo") is not True
        or geometry.get("automatic_cell_lattice_reprojection_proven") is not False
        or not _close(required_panel_area, MIN_PANEL_AREA_FRACTION)
        or not required_panel_area <= panel_area <= 1.0
        or not _close(required_side, MIN_PROJECTED_CELL_SIDE_PX)
        or minimum_side < required_side
    ):
        raise CrossoverProfileComparisonError(f"{label}.geometry diagnostics failed")
    return {
        "camera_lock_id": camera_lock_id,
        "panel_area_fraction_of_photo": panel_area,
        "minimum_projected_cell_side_px": minimum_side,
        "automatic_cell_lattice_reprojection_proven": False,
    }


def _validate_codes(
    value: Any, *, stage: str, label: str
) -> dict[tuple[int, int], dict[str, Any]]:
    if not isinstance(value, list) or len(value) != CODE_COUNT:
        raise CrossoverProfileComparisonError(
            f"{label}.codes must contain exactly eight codes"
        )
    profiles = _expected_profiles(stage)
    result: dict[tuple[int, int], dict[str, Any]] = {}
    seen_codes: set[int] = set()
    for code_index, raw_code in enumerate(value):
        code_record = _mapping(raw_code, label=f"{label}.codes[{code_index}]")
        if set(code_record) != {"code", "controllers"}:
            raise CrossoverProfileComparisonError(
                f"{label}.codes[{code_index}] keys differ"
            )
        code = _integer(
            code_record.get("code"), label=f"{label}.codes[{code_index}].code"
        )
        if code not in range(CODE_COUNT) or code in seen_codes or code != code_index:
            raise CrossoverProfileComparisonError(
                f"{label}.codes[{code_index}] identity/order differs"
            )
        seen_codes.add(code)
        raw_controllers = code_record.get("controllers")
        if not isinstance(raw_controllers, list) or len(raw_controllers) != 2:
            raise CrossoverProfileComparisonError(
                f"{label}.codes[{code_index}].controllers must contain CS1 and CS2"
            )
        for controller_index, raw_controller in enumerate(raw_controllers):
            controller_record = _mapping(
                raw_controller,
                label=f"{label}.codes[{code_index}].controllers[{controller_index}]",
            )
            expected_keys = {
                "controller",
                "profile",
                "positions",
                "center_lab",
                "position_dispersion_de76",
                "position_dispersion_p95_de76",
            }
            if set(controller_record) != expected_keys:
                raise CrossoverProfileComparisonError(
                    f"{label}.codes[{code_index}].controllers[{controller_index}] "
                    "keys differ"
                )
            controller = _integer(
                controller_record.get("controller"),
                label=(
                    f"{label}.codes[{code_index}].controllers"
                    f"[{controller_index}].controller"
                ),
            )
            if controller != controller_index:
                raise CrossoverProfileComparisonError(
                    f"{label} code {code} controller identity/order differs"
                )
            if controller_record.get("profile") != profiles[controller]:
                raise CrossoverProfileComparisonError(
                    f"{label} code {code} controller profile differs"
                )
            raw_positions = controller_record.get("positions")
            expected_positions = _expected_positions(code)
            if (
                not isinstance(raw_positions, list)
                or len(raw_positions) != POSITIONS_PER_CODE_CONTROLLER
            ):
                raise CrossoverProfileComparisonError(
                    f"{label} code {code} controller {controller} must have four positions"
                )
            positions: list[dict[str, Any]] = []
            for position_index, raw_position in enumerate(raw_positions):
                position = _mapping(
                    raw_position,
                    label=(
                        f"{label}.codes[{code_index}].controllers"
                        f"[{controller_index}].positions[{position_index}]"
                    ),
                )
                if set(position) != {"row", "column", "camera_relative_lab"}:
                    raise CrossoverProfileComparisonError(
                        f"{label} code {code} controller {controller} position keys differ"
                    )
                row = _integer(position.get("row"), label=f"{label} position row")
                column = _integer(
                    position.get("column"), label=f"{label} position column"
                )
                if (row, column) != expected_positions[position_index]:
                    raise CrossoverProfileComparisonError(
                        f"{label} code {code} position identity/order differs"
                    )
                positions.append(
                    {
                        "row": row,
                        "column": column,
                        "camera_relative_lab": _vector(
                            position.get("camera_relative_lab"),
                            label=f"{label} code {code} position Lab",
                        ),
                    }
                )
            center = _median_vector([item["camera_relative_lab"] for item in positions])
            declared_center = _vector(
                controller_record.get("center_lab"),
                label=f"{label} code {code} controller {controller} center_lab",
            )
            if not _same_vector(center, declared_center):
                raise CrossoverProfileComparisonError(
                    f"{label} code {code} controller {controller} center is forged"
                )
            dispersions = [
                _distance(item["camera_relative_lab"], center) for item in positions
            ]
            raw_dispersions = controller_record.get("position_dispersion_de76")
            if not isinstance(raw_dispersions, list) or len(raw_dispersions) != 4:
                raise CrossoverProfileComparisonError(
                    f"{label} code {code} controller {controller} dispersions differ"
                )
            declared_dispersions = [
                _number(item, label=f"{label} declared position dispersion")
                for item in raw_dispersions
            ]
            if any(
                not _close(observed, declared)
                for observed, declared in zip(
                    dispersions, declared_dispersions, strict=True
                )
            ):
                raise CrossoverProfileComparisonError(
                    f"{label} code {code} controller {controller} dispersions are forged"
                )
            position_p95 = _percentile(dispersions, 0.95)
            declared_p95 = _number(
                controller_record.get("position_dispersion_p95_de76"),
                label=f"{label} declared position dispersion p95",
            )
            if not _close(position_p95, declared_p95):
                raise CrossoverProfileComparisonError(
                    f"{label} code {code} controller {controller} p95 is forged"
                )
            result[(controller, code)] = {
                "profile": profiles[controller],
                "positions": positions,
                "center_lab": center,
                "position_dispersion_p95_de76": position_p95,
            }
    expected_keys = {
        (controller, code)
        for controller in range(CONTROLLER_COUNT)
        for code in range(CODE_COUNT)
    }
    if set(result) != expected_keys:
        raise CrossoverProfileComparisonError(f"{label}.codes coverage differs")
    return result


def _expected_action_binding(stage: str) -> dict[str, Any]:
    report = pack.build_report(stage)
    action = report["actions"][0]
    cfg = pack.STAGES[stage]
    return {
        "stage": stage,
        "campaign_id": cfg.campaign_id,
        "test_id": cfg.test_id,
        "contract_id": report["contract_id"],
        "action_id": action["action_id"],
        "descriptor_id": action["descriptor_id"],
        "role": action["role"],
        "frame_sha256": action["frame"]["sha256"],
        "cs1_dtm_sha256": action["cs1_dtm"]["sha256"],
        "cs2_dtm_sha256": action["cs2_dtm"]["sha256"],
        "firmware_sha256": pack.ARTIFACTS[stage]["bin_sha256"],
        "profile_id": action["profile_id"],
        "global_tuple_id": action["global_tuple_id"],
        "waveform_binding": action["waveform_binding"],
        "global_header": action["global_header"],
    }


def _validate_source_evidence(value: Any, *, label: str) -> dict[str, str]:
    evidence = _mapping(value, label=f"{label}.source_evidence")
    if set(evidence) != {"photo", "capture_sidecar", "action_result"}:
        raise CrossoverProfileComparisonError(f"{label}.source_evidence keys differ")
    expected_keys = {
        "photo": {"path", "bytes", "sha256", "width", "height"},
        "capture_sidecar": {
            "path",
            "bytes",
            "sha256",
            "canonical_integrity_sha256",
        },
        "action_result": {
            "path",
            "bytes",
            "sha256",
            "canonical_integrity_sha256",
        },
    }
    hashes: dict[str, str] = {}
    for name, keys in expected_keys.items():
        record = _mapping(evidence.get(name), label=f"{label}.source_evidence.{name}")
        if set(record) != keys:
            raise CrossoverProfileComparisonError(
                f"{label}.source_evidence.{name} keys differ"
            )
        if not isinstance(record.get("path"), str) or not record.get("path"):
            raise CrossoverProfileComparisonError(
                f"{label}.source_evidence.{name}.path differs"
            )
        if (
            _integer(record.get("bytes"), label=f"{label}.source_evidence.{name}.bytes")
            <= 0
        ):
            raise CrossoverProfileComparisonError(
                f"{label}.source_evidence.{name}.bytes differs"
            )
        hashes[name] = _sha256(
            record.get("sha256"), label=f"{label}.source_evidence.{name}.sha256"
        )
        if name == "photo":
            for dimension in ("width", "height"):
                if (
                    _integer(
                        record.get(dimension),
                        label=f"{label}.source_evidence.photo.{dimension}",
                    )
                    <= 0
                ):
                    raise CrossoverProfileComparisonError(
                        f"{label}.source_evidence.photo.{dimension} differs"
                    )
        else:
            _sha256(
                record.get("canonical_integrity_sha256"),
                label=(f"{label}.source_evidence.{name}.canonical_integrity_sha256"),
            )
    return hashes


def _validate_rich_evidence(
    root: Mapping[str, Any],
    *,
    stage: str,
    label: str,
    projection_geometry: Mapping[str, Any],
    projection_codes: Mapping[tuple[int, int], Mapping[str, Any]],
) -> dict[str, Any]:
    source_hashes = _validate_source_evidence(root.get("source_evidence"), label=label)

    expected_action = _expected_action_binding(stage)
    action_binding = _mapping(
        root.get("action_binding"), label=f"{label}.action_binding"
    )
    if dict(action_binding) != expected_action:
        raise CrossoverProfileComparisonError(f"{label}.action_binding differs")

    camera_lock = _mapping(root.get("camera_lock"), label=f"{label}.camera_lock")
    camera_lock_id = sha256_bytes(canonical_json(dict(camera_lock)))
    if camera_lock_id != projection_geometry["camera_lock_id"]:
        raise CrossoverProfileComparisonError(f"{label}.camera_lock binding differs")

    rich_layout = _mapping(root.get("layout"), label=f"{label}.layout")
    expected_layout_fields = {
        "logical_width": 1024,
        "logical_height": 600,
        "controller_count": 2,
        "controller_width": 512,
        "rows_per_controller": pack.GRID_ROWS,
        "columns_per_controller": pack.GRID_COLUMNS,
        "row_codes": [list(row) for row in pack.CODE_ROWS],
        "samples_per_code_per_controller": 4,
        "same_layout_both_controllers": True,
        "spatial_dither": False,
        "legacy_endpoint_4x2_analyzer_used": False,
    }
    if dict(rich_layout) != expected_layout_fields:
        raise CrossoverProfileComparisonError(f"{label}.rich layout differs")

    rich_geometry = _mapping(root.get("geometry"), label=f"{label}.geometry")
    geometry_pairs = {
        "homography_logical_to_current_photo": "homography_logical_to_photo",
        "historical_g1_homography_reused": "historical_g1_homography_reused",
        "sampling_geometry_admitted": "sampling_geometry_admitted",
        "all_projected_cells_inside_photo": "all_projected_cells_inside_photo",
        "automatic_cell_lattice_reprojection_proven": (
            "automatic_cell_lattice_reprojection_proven"
        ),
        "panel_area_fraction_of_photo": "panel_area_fraction_of_photo",
        "minimum_required_panel_area_fraction": (
            "minimum_required_panel_area_fraction"
        ),
        "minimum_projected_cell_side_px": "minimum_projected_cell_side_px",
        "minimum_required_projected_cell_side_px": (
            "minimum_required_projected_cell_side_px"
        ),
    }
    for rich_key, projection_key in geometry_pairs.items():
        if (
            rich_geometry.get(rich_key)
            != _mapping(
                root.get("comparison_projection"),
                label=f"{label}.comparison_projection",
            )["geometry"][projection_key]
        ):
            raise CrossoverProfileComparisonError(
                f"{label}.geometry {rich_key} projection binding differs"
            )

    expected_cell_keys = {
        "cell_id",
        "controller",
        "row",
        "column",
        "position_index_for_code",
        "code",
        "logical_bounds",
        "logical_center",
        "projected_inner_roi_corners",
        "inner_fraction",
        "sample_count",
        "robust_rgb_median",
        "robust_rgb_mad",
        "camera_relative_lab_d65_from_rgb_median",
    }
    raw_cells = root.get("cells")
    if not isinstance(raw_cells, list) or len(raw_cells) != 64:
        raise CrossoverProfileComparisonError(f"{label}.cells must contain 64 cells")
    cells: dict[tuple[int, int, int], list[float]] = {}
    for index, raw_cell in enumerate(raw_cells):
        cell = _mapping(raw_cell, label=f"{label}.cells[{index}]")
        if set(cell) != expected_cell_keys:
            raise CrossoverProfileComparisonError(f"{label}.cells[{index}] keys differ")
        controller = _integer(cell.get("controller"), label=f"{label} cell controller")
        row = _integer(cell.get("row"), label=f"{label} cell row")
        column = _integer(cell.get("column"), label=f"{label} cell column")
        code = _integer(cell.get("code"), label=f"{label} cell code")
        if (
            controller not in range(2)
            or row not in range(pack.GRID_ROWS)
            or column not in range(pack.GRID_COLUMNS)
            or code != pack.CODE_ROWS[row][column]
        ):
            raise CrossoverProfileComparisonError(
                f"{label}.cells[{index}] identity differs"
            )
        key = (controller, row, column)
        if key in cells:
            raise CrossoverProfileComparisonError(f"{label}.cells duplicate identity")
        cells[key] = _vector(
            cell.get("camera_relative_lab_d65_from_rgb_median"),
            label=f"{label}.cells[{index}] Lab",
        )
    for (controller, code), record in projection_codes.items():
        for position in record["positions"]:
            key = (controller, position["row"], position["column"])
            if not _same_vector(cells[key], position["camera_relative_lab"]):
                raise CrossoverProfileComparisonError(
                    f"{label}.cells and comparison_projection differ"
                )

    summary = _mapping(
        root.get("position_balanced_summary"),
        label=f"{label}.position_balanced_summary",
    )
    raw_groups = summary.get("controller_code_groups")
    if not isinstance(raw_groups, list) or len(raw_groups) != 16:
        raise CrossoverProfileComparisonError(
            f"{label}.position_balanced_summary groups differ"
        )
    seen_groups: set[tuple[int, int]] = set()
    for index, raw_group in enumerate(raw_groups):
        group = _mapping(raw_group, label=f"{label}.summary.groups[{index}]")
        controller = _integer(
            group.get("controller"), label=f"{label} group controller"
        )
        code = _integer(group.get("code"), label=f"{label} group code")
        key = (controller, code)
        if (
            key in seen_groups
            or key not in projection_codes
            or group.get("sample_count") != 4
        ):
            raise CrossoverProfileComparisonError(
                f"{label}.summary group identity differs"
            )
        seen_groups.add(key)
        if not _same_vector(
            _vector(
                group.get("camera_relative_lab_component_median"),
                label=f"{label}.summary group median",
            ),
            projection_codes[key]["center_lab"],
        ):
            raise CrossoverProfileComparisonError(
                f"{label}.summary and comparison_projection centers differ"
            )

    classification = _mapping(
        root.get("classification"), label=f"{label}.classification"
    )
    expected_classification = {
        "state": "CAMERA_RELATIVE_CROSSOVER_POSITION_COMPARISON_ONLY",
        "camera_relative_candidates_only": True,
        "absolute_colour_proven": False,
        "stable_colour_proven": False,
        "repeatable_colour_proven": False,
        "qualified_new_colour": False,
        "qualified_colour_count": 0,
        "cross_stage_equivalence_proven": False,
    }
    if dict(classification) != expected_classification:
        raise CrossoverProfileComparisonError(
            f"{label}.classification boundary differs"
        )
    if (
        root.get("hardware_io_performed_by_analyzer") is not False
        or root.get("camera_access_performed_by_analyzer") is not False
        or root.get("visible_refresh_authorized") is not False
        or root.get("output_write_contract") != "O_EXCL"
    ):
        raise CrossoverProfileComparisonError(
            f"{label}.offline safety boundary differs"
        )
    return {"source_evidence_sha256": source_hashes, "camera_lock_id": camera_lock_id}


def _validate_analysis(
    path: Path, *, expected_stage: str, index: int
) -> dict[str, Any]:
    label = f"{expected_stage} analysis {index}"
    payload, root = _load_json(path, label=label)
    expected_keys = {
        "schema_version",
        "kind",
        "stage",
        "campaign_id",
        "contract_id",
        "action_id",
        "frame_sha256",
        "cs1_dtm_sha256",
        "cs2_dtm_sha256",
        "source_evidence",
        "action_binding",
        "camera_lock",
        "layout",
        "geometry",
        "measurement_method",
        "cells",
        "position_balanced_summary",
        "comparison_projection",
        "classification",
        "hardware_io_performed_by_analyzer",
        "camera_access_performed_by_analyzer",
        "visible_refresh_authorized",
        "output_write_contract",
        "integrity",
    }
    if set(root) != expected_keys:
        raise CrossoverProfileComparisonError(f"{label} top-level keys differ")
    if (
        root.get("schema_version") != INPUT_SCHEMA_VERSION
        or root.get("kind") != INPUT_KIND
    ):
        raise CrossoverProfileComparisonError(f"{label} schema identity differs")
    integrity = _verify_integrity(root, label=label)
    projection = _mapping(
        root.get("comparison_projection"), label=f"{label}.comparison_projection"
    )
    projection_keys = {
        "stage",
        "campaign_id",
        "contract_id",
        "action_id",
        "frame_sha256",
        "cs1_dtm_sha256",
        "cs2_dtm_sha256",
        "layout",
        "geometry",
        "codes",
    }
    if set(projection) != projection_keys:
        raise CrossoverProfileComparisonError(
            f"{label}.comparison_projection keys differ"
        )
    expected_binding = _expected_binding(expected_stage)
    for field, expected in expected_binding.items():
        if root.get(field) != expected or projection.get(field) != expected:
            raise CrossoverProfileComparisonError(f"{label} {field} binding differs")
    layout = _validate_layout(projection.get("layout"), label=f"{label}.projection")
    geometry = _validate_geometry(
        projection.get("geometry"), label=f"{label}.projection"
    )
    codes = _validate_codes(
        projection.get("codes"),
        stage=expected_stage,
        label=f"{label}.projection",
    )
    rich = _validate_rich_evidence(
        root,
        stage=expected_stage,
        label=label,
        projection_geometry=geometry,
        projection_codes=codes,
    )
    return {
        "path": path.resolve(),
        "bytes": len(payload),
        "file_sha256": sha256_bytes(payload),
        "integrity_sha256": integrity,
        "stage": expected_stage,
        "binding": expected_binding,
        "layout": layout,
        "geometry": geometry,
        "codes": codes,
        **rich,
    }


def _load_stage(paths: Sequence[Path], *, stage: str) -> list[dict[str, Any]]:
    if len(paths) != INPUTS_PER_STAGE:
        raise CrossoverProfileComparisonError(
            f"{stage} requires exactly three single-frame analyses"
        )
    resolved = [Path(path).resolve() for path in paths]
    if len(set(resolved)) != INPUTS_PER_STAGE:
        raise CrossoverProfileComparisonError(f"{stage} analysis paths must be unique")
    frames = [
        _validate_analysis(path, expected_stage=stage, index=index)
        for index, path in enumerate(resolved, 1)
    ]
    file_hashes = [frame["file_sha256"] for frame in frames]
    if len(set(file_hashes)) != INPUTS_PER_STAGE:
        raise CrossoverProfileComparisonError(
            f"{stage} analyses must be three distinct sealed records"
        )
    camera_locks = {frame["geometry"]["camera_lock_id"] for frame in frames}
    if len(camera_locks) != 1:
        raise CrossoverProfileComparisonError(
            f"{stage} analyses use different camera locks"
        )
    return frames


def _aggregate_controller_code(
    frames: Sequence[Mapping[str, Any]], *, controller: int, code: int
) -> dict[str, Any]:
    expected_positions = _expected_positions(code)
    position_medians: list[list[float]] = []
    for position_index, _identity in enumerate(expected_positions):
        position_medians.append(
            _median_vector(
                [
                    frame["codes"][(controller, code)]["positions"][position_index][
                        "camera_relative_lab"
                    ]
                    for frame in frames
                ]
            )
        )
    center = _median_vector(position_medians)
    position_dispersions = [
        _distance(position, center) for position in position_medians
    ]
    frame_centers = [
        list(frame["codes"][(controller, code)]["center_lab"]) for frame in frames
    ]
    temporal_dispersions = [_distance(value, center) for value in frame_centers]
    single_frame_position_p95 = [
        float(frame["codes"][(controller, code)]["position_dispersion_p95_de76"])
        for frame in frames
    ]
    position_p95 = _percentile(position_dispersions, 0.95)
    temporal_p95 = _percentile(temporal_dispersions, 0.95)
    consistency_maximum = max(position_p95, temporal_p95, *single_frame_position_p95)
    return {
        "controller": controller,
        "controller_label": "CS1" if controller == 0 else "CS2",
        "profile": frames[0]["codes"][(controller, code)]["profile"],
        "stage_center_lab": center,
        "position_median_labs": position_medians,
        "position_dispersion_de76": position_dispersions,
        "position_dispersion_p95_de76": position_p95,
        "frame_center_labs": frame_centers,
        "temporal_center_dispersion_de76": temporal_dispersions,
        "temporal_center_dispersion_p95_de76": temporal_p95,
        "maximum_single_frame_position_dispersion_p95_de76": max(
            single_frame_position_p95
        ),
        "consistency_maximum_de76": consistency_maximum,
        "consistency_pass": consistency_maximum <= POSITION_AND_REPEAT_TOLERANCE_DE76,
    }


def _code_result(
    code: int,
    t1_frames: Sequence[Mapping[str, Any]],
    t2_frames: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    t1_cs1 = _aggregate_controller_code(t1_frames, controller=0, code=code)
    t1_cs2 = _aggregate_controller_code(t1_frames, controller=1, code=code)
    t2_cs1 = _aggregate_controller_code(t2_frames, controller=0, code=code)
    t2_cs2 = _aggregate_controller_code(t2_frames, controller=1, code=code)
    groups = (t1_cs1, t1_cs2, t2_cs1, t2_cs2)
    consistency_maximum = max(
        float(group["consistency_maximum_de76"]) for group in groups
    )
    match_tolerance = max(POSITION_AND_REPEAT_TOLERANCE_DE76, consistency_maximum)
    effect_threshold = EFFECT_MULTIPLIER * match_tolerance

    t1_active = t1_cs1["stage_center_lab"]
    t1_commented = t1_cs2["stage_center_lab"]
    t2_commented = t2_cs1["stage_center_lab"]
    t2_active = t2_cs2["stage_center_lab"]

    active_profile_match = _distance(t1_active, t2_active)
    commented_profile_match = _distance(t1_commented, t2_commented)
    cs1_side_match = _distance(t1_active, t2_commented)
    cs2_side_match = _distance(t1_commented, t2_active)
    t1_profile_vector = _difference(t1_active, t1_commented)
    t2_profile_vector = _difference(t2_active, t2_commented)
    profile_vector_disagreement = _distance(t1_profile_vector, t2_profile_vector)
    t1_side_vector = _difference(t1_active, t1_commented)
    t2_side_vector = _difference(t2_commented, t2_active)
    side_vector_disagreement = _distance(t1_side_vector, t2_side_vector)
    profile_separations = [
        _distance(t1_active, t1_commented),
        _distance(t2_active, t2_commented),
    ]

    consistency_pass = all(group["consistency_pass"] is True for group in groups)
    profile_gate = (
        consistency_pass
        and max(
            active_profile_match,
            commented_profile_match,
            profile_vector_disagreement,
        )
        <= match_tolerance
        and min(profile_separations) > effect_threshold
        and min(cs1_side_match, cs2_side_match) > effect_threshold
    )
    side_gate = (
        consistency_pass
        and max(cs1_side_match, cs2_side_match, side_vector_disagreement)
        <= match_tolerance
        and min(profile_separations) > effect_threshold
        and min(active_profile_match, commented_profile_match) > effect_threshold
    )
    if not consistency_pass:
        classification = INCONCLUSIVE
        reason = "POSITION_OR_TEMPORAL_INCONSISTENCY"
    elif profile_gate and not side_gate:
        classification = PROFILE_FOLLOWING_CANDIDATE
        reason = "ACTIVE_AND_COMMENTED_ENDPOINTS_FOLLOW_PROFILE_SWAP"
    elif side_gate and not profile_gate:
        classification = SIDE_FOLLOWING_CANDIDATE
        reason = "APPEARANCE_REMAINS_ATTACHED_TO_PHYSICAL_CONTROLLER_SIDE"
    elif max(profile_separations) <= effect_threshold:
        classification = INCONCLUSIVE
        reason = "NO_RESOLVED_ACTIVE_COMMENTED_SEPARATION"
    else:
        classification = INCONCLUSIVE
        reason = "AMBIGUOUS_OR_MIXED_PROFILE_SIDE_PATTERN"

    priority_role = (
        "PRIMARY"
        if code in PRIMARY_CODES
        else "GUARD"
        if code in GUARD_CODES
        else "CONTROL"
    )
    return {
        "code": code,
        "priority_role": priority_role,
        "classification": classification,
        "diagnostic_reason": reason,
        "candidate_only": classification != INCONCLUSIVE,
        "absolute_colour_proven": False,
        "stable_colour_proven": False,
        "repeatable_colour_proven": False,
        "qualified_new_colour": False,
        "stage_controller_statistics": {
            T1_STAGE: [t1_cs1, t1_cs2],
            T2_STAGE: [t2_cs1, t2_cs2],
        },
        "model_metrics": {
            "fixed_match_tolerance_de76": POSITION_AND_REPEAT_TOLERANCE_DE76,
            "observed_consistency_maximum_de76": consistency_maximum,
            "effective_match_tolerance_de76": match_tolerance,
            "effect_threshold_de76": effect_threshold,
            "active_profile_t1_to_t2_de76": active_profile_match,
            "commented_profile_t1_to_t2_de76": commented_profile_match,
            "cs1_fixed_side_t1_to_t2_de76": cs1_side_match,
            "cs2_fixed_side_t1_to_t2_de76": cs2_side_match,
            "profile_vector_disagreement_de76": profile_vector_disagreement,
            "side_vector_disagreement_de76": side_vector_disagreement,
            "t1_active_commented_separation_de76": profile_separations[0],
            "t2_active_commented_separation_de76": profile_separations[1],
            "profile_model_pass": profile_gate,
            "side_model_pass": side_gate,
        },
    }


def _input_binding_records(
    frames: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "path": frame["path"].as_posix(),
            "bytes": frame["bytes"],
            "file_sha256": frame["file_sha256"],
            "canonical_integrity_sha256": frame["integrity_sha256"],
            "source_evidence_sha256": frame["source_evidence_sha256"],
            **frame["binding"],
        }
        for frame in frames
    ]


def _validate_superseded_preflight(
    path: Path,
    *,
    expected_input_bindings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    resolved = Path(path).resolve()
    payload, root = _load_json(resolved, label="superseded T1 preflight")
    integrity = _verify_integrity(root, label="superseded T1 preflight")
    if (
        root.get("schema_version") != 1
        or root.get("kind") != PREFLIGHT_V1_KIND
        or root.get("stage") != T1_STAGE
        or root.get("input_bindings") != list(expected_input_bindings)
    ):
        raise CrossoverProfileComparisonError(
            "superseded T1 preflight identity/input binding differs"
        )
    summary = _mapping(root.get("summary"), label="superseded T1 preflight.summary")
    if (
        summary.get("state")
        not in {
            "PASS_T1_POSITION_TEMPORAL_PREFLIGHT",
            "FAIL_T1_POSITION_TEMPORAL_PREFLIGHT",
        }
        or not isinstance(summary.get("advance_to_w1_then_t2_permitted"), bool)
        or "w1_containment_required" in summary
        or "advance_to_t2_permitted" in summary
    ):
        raise CrossoverProfileComparisonError(
            "superseded T1 preflight is not the exact v1 W1/T2 semantic record"
        )
    return {
        "supersedes_source_path": resolved.as_posix(),
        "supersedes_file_sha256": sha256_bytes(payload),
        "supersedes_canonical_integrity_sha256": integrity,
        "supersession_reason": (
            "CORRECT_V1_W1_T2_COMBINED_GATE_TO_REQUIRED_W1_AND_SEPARATE_T2_GATE"
        ),
    }


def preflight_t1(
    t1_analyses: Sequence[Path],
    *,
    supersedes_preflight: Path | None = None,
) -> dict[str, Any]:
    """Seal the mandatory three-frame T1 position/temporal admission gate."""

    frames = _load_stage(t1_analyses, stage=T1_STAGE)
    code_results: list[dict[str, Any]] = []
    failed_groups: list[dict[str, Any]] = []
    for code in range(CODE_COUNT):
        groups = [
            _aggregate_controller_code(frames, controller=controller, code=code)
            for controller in range(CONTROLLER_COUNT)
        ]
        for group in groups:
            if group["consistency_pass"] is not True:
                failed_groups.append(
                    {
                        "code": code,
                        "controller": group["controller"],
                        "controller_label": group["controller_label"],
                        "consistency_maximum_de76": group["consistency_maximum_de76"],
                    }
                )
        code_results.append(
            {
                "code": code,
                "priority_role": (
                    "PRIMARY"
                    if code in PRIMARY_CODES
                    else "GUARD"
                    if code in GUARD_CODES
                    else "CONTROL"
                ),
                "position_temporal_gate_pass": all(
                    group["consistency_pass"] is True for group in groups
                ),
                "controller_statistics": groups,
                "candidate_only": False,
                "absolute_colour_proven": False,
                "stable_colour_proven": False,
                "repeatable_colour_proven": False,
                "qualified_new_colour": False,
            }
        )
    passed = not failed_groups
    input_bindings = _input_binding_records(frames)
    supersession = (
        _validate_superseded_preflight(
            supersedes_preflight, expected_input_bindings=input_bindings
        )
        if supersedes_preflight is not None
        else {
            "supersedes_source_path": None,
            "supersedes_file_sha256": None,
            "supersedes_canonical_integrity_sha256": None,
            "supersession_reason": None,
        }
    )
    result: dict[str, Any] = {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "kind": PREFLIGHT_KIND,
        "method_id": METHOD_ID,
        "stage": T1_STAGE,
        "input_contract": {
            "kind": INPUT_KIND,
            "schema_version": INPUT_SCHEMA_VERSION,
            "exact_analyses": INPUTS_PER_STAGE,
            "three_distinct_paths_and_file_sha256_required": True,
            "same_camera_lock_required": True,
            "exact_stage_contract_action_frame_and_dtm_binding_required": True,
        },
        "input_bindings": input_bindings,
        **supersession,
        "layout": _validate_layout(frames[0]["layout"], label="T1 preflight input"),
        "threshold_contract": {
            "prior_locked_white_temporal_noise_p95_de76": (
                PRIOR_LOCKED_WHITE_TEMPORAL_NOISE_P95_DE76
            ),
            "position_and_repeat_tolerance_de76": (POSITION_AND_REPEAT_TOLERANCE_DE76),
            "automatic_relaxation": False,
        },
        "priority": {
            "primary_codes": list(PRIMARY_CODES),
            "guard_codes": list(GUARD_CODES),
            "control_codes": list(CONTROL_CODES),
            "review_order": list(PRIORITY_ORDER),
        },
        "code_results": code_results,
        "summary": {
            "state": (
                "PASS_T1_POSITION_TEMPORAL_PREFLIGHT"
                if passed
                else "FAIL_T1_POSITION_TEMPORAL_PREFLIGHT"
            ),
            "position_temporal_gate_pass": passed,
            "w1_containment_required": True,
            "advance_to_t2_permitted": passed,
            "diagnostic_reason": (
                "POSITION_TEMPORAL_PREFLIGHT_PASS"
                if passed
                else "POSITION_DEPENDENT_INCONCLUSIVE"
            ),
            "failed_controller_code_group_count": len(failed_groups),
            "failed_controller_code_groups": failed_groups,
            "profile_or_side_following_classified": False,
            "absolute_colour_proven": False,
            "stable_colour_proven": False,
            "repeatable_colour_proven": False,
            "qualified_new_colour": False,
            "qualified_colour_count": 0,
        },
        "evidence_boundaries": {
            "t1_position_temporal_admission_only": True,
            "t2_profile_swap_evidence_present": False,
            "profile_following_not_yet_testable": True,
            "device_io_performed": False,
            "network_accessed": False,
            "camera_accessed": False,
            "serial_or_com_accessed": False,
            "relay_accessed": False,
            "firmware_flashed": False,
            "display_refreshed": False,
        },
        "output_write_contract": "O_EXCL",
    }
    result["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": sha256_bytes(canonical_json(result)),
    }
    return result


def compare(t1_analyses: Sequence[Path], t2_analyses: Sequence[Path]) -> dict[str, Any]:
    """Return a sealed offline T1-vs-T2 diagnostic report."""

    t1_frames = _load_stage(t1_analyses, stage=T1_STAGE)
    t2_frames = _load_stage(t2_analyses, stage=T2_STAGE)
    all_paths = [frame["path"] for frame in (*t1_frames, *t2_frames)]
    all_hashes = [frame["file_sha256"] for frame in (*t1_frames, *t2_frames)]
    if len(set(all_paths)) != 6 or len(set(all_hashes)) != 6:
        raise CrossoverProfileComparisonError(
            "T1 and T2 must bind six distinct single-frame analyses"
        )
    camera_locks = {
        frame["geometry"]["camera_lock_id"] for frame in (*t1_frames, *t2_frames)
    }
    if len(camera_locks) != 1:
        raise CrossoverProfileComparisonError(
            "T1 and T2 analyses use different camera locks"
        )
    code_results = [
        _code_result(code, t1_frames, t2_frames) for code in range(CODE_COUNT)
    ]
    counts = {
        state: sum(item["classification"] == state for item in code_results)
        for state in (
            INCONCLUSIVE,
            PROFILE_FOLLOWING_CANDIDATE,
            SIDE_FOLLOWING_CANDIDATE,
        )
    }
    lists = {
        state: [
            item["code"] for item in code_results if item["classification"] == state
        ]
        for state in counts
    }
    if counts[PROFILE_FOLLOWING_CANDIDATE] and counts[SIDE_FOLLOWING_CANDIDATE]:
        overall = "MIXED_PROFILE_AND_SIDE_DIAGNOSTICS"
    elif counts[PROFILE_FOLLOWING_CANDIDATE]:
        overall = "PROFILE_FOLLOWING_CANDIDATES_PRESENT"
    elif counts[SIDE_FOLLOWING_CANDIDATE]:
        overall = "SIDE_FOLLOWING_CANDIDATES_PRESENT"
    else:
        overall = INCONCLUSIVE

    input_bindings: dict[str, list[dict[str, Any]]] = {}
    for stage, frames in ((T1_STAGE, t1_frames), (T2_STAGE, t2_frames)):
        input_bindings[stage] = _input_binding_records(frames)

    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "method_id": METHOD_ID,
        "input_contract": {
            "kind": INPUT_KIND,
            "schema_version": INPUT_SCHEMA_VERSION,
            "exact_analyses_per_stage": INPUTS_PER_STAGE,
            "stages": [T1_STAGE, T2_STAGE],
            "six_distinct_paths_and_file_sha256_required": True,
            "same_camera_lock_required": True,
        },
        "input_bindings": input_bindings,
        "layout": _validate_layout(t1_frames[0]["layout"], label="comparison input"),
        "threshold_contract": {
            "prior_locked_white_temporal_noise_p95_de76": (
                PRIOR_LOCKED_WHITE_TEMPORAL_NOISE_P95_DE76
            ),
            "position_and_repeat_tolerance_de76": (POSITION_AND_REPEAT_TOLERANCE_DE76),
            "effect_multiplier": EFFECT_MULTIPLIER,
            "effect_threshold_formula": (
                "2*max(fixed_position_repeat_tolerance,observed_consistency_maximum)"
            ),
            "automatic_relaxation": False,
        },
        "priority": {
            "primary_codes": list(PRIMARY_CODES),
            "guard_codes": list(GUARD_CODES),
            "control_codes": list(CONTROL_CODES),
            "review_order": list(PRIORITY_ORDER),
        },
        "code_results": code_results,
        "summary": {
            "state": overall,
            "classification_counts": counts,
            "classification_code_lists": lists,
            "candidate_only": True,
            "absolute_colour_proven": False,
            "stable_colour_proven": False,
            "repeatable_colour_proven": False,
            "qualified_new_colour": False,
            "qualified_colour_count": 0,
        },
        "evidence_boundaries": {
            "camera_relative_lab_only": True,
            "profile_following_is_not_absolute_colour": True,
            "profile_following_is_not_stable_new_colour": True,
            "side_following_requires_controller_optical_electrical_investigation": True,
            "device_io_performed": False,
            "network_accessed": False,
            "camera_accessed": False,
            "serial_or_com_accessed": False,
            "relay_accessed": False,
            "firmware_flashed": False,
            "display_refreshed": False,
        },
        "output_write_contract": "O_EXCL",
    }
    result["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": sha256_bytes(canonical_json(result)),
    }
    return result


def _serialized(report: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def write_exclusive(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise CrossoverProfileComparisonError(
            f"refusing to overwrite output: {path}"
        ) from exc
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "--t1-analysis", type=Path, nargs=3, required=True, metavar="JSON"
    )
    parser.add_argument("--t2-analysis", type=Path, nargs=3, metavar="JSON")
    parser.add_argument(
        "--t1-only-preflight",
        action="store_true",
        help="emit the mandatory three-frame T1 position/temporal admission gate",
    )
    parser.add_argument(
        "--supersedes-preflight",
        type=Path,
        metavar="V1_JSON",
        help="bind a sealed v1 preflight superseded by corrected W1/T2 semantics",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.t1_only_preflight and args.t2_analysis is not None:
        parser.error("--t1-only-preflight cannot be combined with --t2-analysis")
    if not args.t1_only_preflight and args.t2_analysis is None:
        parser.error("comparison mode requires --t2-analysis with exactly three JSONs")
    if not args.t1_only_preflight and args.supersedes_preflight is not None:
        parser.error("--supersedes-preflight is only valid with --t1-only-preflight")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = (
            preflight_t1(
                args.t1_analysis,
                supersedes_preflight=args.supersedes_preflight,
            )
            if args.t1_only_preflight
            else compare(args.t1_analysis, args.t2_analysis)
        )
        payload = _serialized(report)
        write_exclusive(args.output, payload)
    except CrossoverProfileComparisonError as exc:
        print(f"RAW-P16 crossover comparison error: {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(payload)
    if (
        args.t1_only_preflight
        and report["summary"]["position_temporal_gate_pass"] is not True
    ):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
