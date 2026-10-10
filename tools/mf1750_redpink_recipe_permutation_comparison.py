#!/usr/bin/env python3
"""Compare Red/Pink P0 and P1 grids in recipe and physical coordinates."""

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


SCHEMA_VERSION = 1
KIND = "mf1750-redpink-recipe-permutation-comparison"
BASE_KIND = "mf1750-redpink-v2-dual-8x8-camera-relative-grid-photo-analysis"
BASE_LAYOUT_ID = "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_V2"
PERMUTED_KIND = (
    "mf1750-redpink-recipe-permutation-dual-8x8-camera-relative-grid-analysis"
)
PERMUTED_LAYOUT_ID = (
    "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_RECIPE_PERMUTATION_V1"
)
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
RECIPE_CORRELATION_FLOOR = 0.80
RECIPE_OVER_POSITION_MARGIN = 0.25


class RecipePermutationComparisonError(RuntimeError):
    """Raised when input evidence or exclusive output is invalid."""


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
        raise RecipePermutationComparisonError(
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
            raise RecipePermutationComparisonError(
                f"{label} must be a regular non-symlink file: {path}"
            )
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise RecipePermutationComparisonError(f"cannot read {label}: {exc}") from exc
    before_id = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_id = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_id != after_id or len(payload) != after.st_size:
        raise RecipePermutationComparisonError(f"{label} changed while read")
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
        raise RecipePermutationComparisonError(
            f"{label} is not strict UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise RecipePermutationComparisonError(f"{label} root must be an object")
    return payload, value


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RecipePermutationComparisonError(f"{label} must be an object")
    return value


def _number(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RecipePermutationComparisonError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise RecipePermutationComparisonError(f"{label} must be a finite number")
    return result


def _verify_integrity(root: Mapping[str, Any], *, label: str) -> str:
    integrity = _mapping(root.get("integrity"), label=f"{label}.integrity")
    if set(integrity) != {"algorithm", "sha256"}:
        raise RecipePermutationComparisonError(f"{label}.integrity keys differ")
    if integrity.get("algorithm") != INTEGRITY_ALGORITHM:
        raise RecipePermutationComparisonError(f"{label}.integrity algorithm differs")
    declared = integrity.get("sha256")
    if not isinstance(declared, str) or len(declared) != 64:
        raise RecipePermutationComparisonError(f"{label}.integrity SHA differs")
    unsigned = dict(root)
    unsigned.pop("integrity", None)
    if _sha256_bytes(_canonical_json(unsigned)) != declared:
        raise RecipePermutationComparisonError(f"{label}.integrity SHA differs")
    return declared


def _validate_cells(
    root: Mapping[str, Any], *, permuted: bool
) -> dict[tuple[int, int, int], dict[str, Any]]:
    judgement = _mapping(root.get("grid_judgement"), label="grid_judgement")
    if judgement.get("enough_to_interpret_grid_camera_relatively") is not True:
        raise RecipePermutationComparisonError("grid evidence is insufficient")
    raw_cells = root.get("cells")
    if not isinstance(raw_cells, list) or len(raw_cells) != 128:
        raise RecipePermutationComparisonError("grid must contain exactly 128 cells")
    cells: dict[tuple[int, int, int], dict[str, Any]] = {}
    recipes: dict[int, set[str]] = {0: set(), 1: set()}
    for index, raw in enumerate(raw_cells):
        cell = _mapping(raw, label=f"cells[{index}]")
        controller = cell.get("controller")
        row = cell.get("row")
        column = cell.get("column")
        if (
            type(controller) is not int
            or controller not in (0, 1)
            or type(row) is not int
            or row not in range(8)
            or type(column) is not int
            or column not in range(8)
        ):
            raise RecipePermutationComparisonError(f"cells[{index}] coordinate differs")
        key = (controller, row, column)
        if key in cells:
            raise RecipePermutationComparisonError(f"duplicate cell {key}")
        expected_source = (column + 3) % 8 if permuted else column
        expected_middle = 7 - row if permuted else row
        expected_recipe = f"REDPINK-A{expected_source}-B{expected_middle}-A0"
        if cell.get("cell_id") != f"C{controller}-R{row}-K{column}":
            raise RecipePermutationComparisonError(f"cells[{index}] id differs")
        if cell.get("recipe_id") != expected_recipe:
            raise RecipePermutationComparisonError(f"cells[{index}] recipe differs")
        lab = cell.get("camera_relative_lab")
        if not isinstance(lab, list) or len(lab) != 3:
            raise RecipePermutationComparisonError(f"cells[{index}] Lab differs")
        parsed = [_number(item, label=f"cells[{index}].Lab") for item in lab]
        cells[key] = {"recipe_id": expected_recipe, "lab": parsed}
        recipes[controller].add(expected_recipe)
    if any(len(items) != 64 for items in recipes.values()):
        raise RecipePermutationComparisonError("recipe coverage is not bijective")
    return cells


def _pearson(first: list[float], second: list[float]) -> float | None:
    if len(first) != len(second) or len(first) < 2:
        raise RecipePermutationComparisonError("correlation vectors differ")
    mean_first = sum(first) / len(first)
    mean_second = sum(second) / len(second)
    centered_first = [item - mean_first for item in first]
    centered_second = [item - mean_second for item in second]
    denominator = math.sqrt(
        sum(item * item for item in centered_first)
        * sum(item * item for item in centered_second)
    )
    if denominator <= 1e-12:
        return None
    return (
        sum(
            left * right
            for left, right in zip(centered_first, centered_second, strict=True)
        )
        / denominator
    )


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 9)


def _mean_defined(values: Sequence[float | None]) -> float | None:
    defined = [value for value in values if value is not None]
    return None if not defined else sum(defined) / len(defined)


def _plane_diagnostics(
    samples: Sequence[tuple[int, int, float]],
) -> dict[str, Any]:
    """Describe a balanced row/column plane without adding a fit dependency."""

    if not samples:
        raise RecipePermutationComparisonError("illumination plane samples are empty")
    rows = [float(row) for row, _, _ in samples]
    columns = [float(column) for _, column, _ in samples]
    values = [value for _, _, value in samples]
    row_mean = sum(rows) / len(rows)
    column_mean = sum(columns) / len(columns)
    value_mean = sum(values) / len(values)
    row_denominator = sum((value - row_mean) ** 2 for value in rows)
    column_denominator = sum((value - column_mean) ** 2 for value in columns)
    if row_denominator <= 0 or column_denominator <= 0:
        raise RecipePermutationComparisonError("illumination plane geometry differs")
    row_slope = (
        sum((row - row_mean) * (value - value_mean) for row, value in zip(rows, values))
        / row_denominator
    )
    column_slope = (
        sum(
            (column - column_mean) * (value - value_mean)
            for column, value in zip(columns, values)
        )
        / column_denominator
    )
    residuals = [
        value
        - (
            value_mean
            + row_slope * (row - row_mean)
            + column_slope * (column - column_mean)
        )
        for row, column, value in samples
    ]
    row_groups = {
        row: [value for item_row, _, value in samples if item_row == row]
        for row in sorted({row for row, _, _ in samples})
    }
    column_groups = {
        column: [value for _, item_column, value in samples if item_column == column]
        for column in sorted({column for _, column, _ in samples})
    }
    row_means = [sum(group) / len(group) for group in row_groups.values()]
    column_means = [sum(group) / len(group) for group in column_groups.values()]
    return {
        "intercept_at_grid_centre": _rounded(value_mean),
        "row_slope_per_cell": _rounded(row_slope),
        "column_slope_per_cell": _rounded(column_slope),
        "residual_rmse": _rounded(
            math.sqrt(sum(value * value for value in residuals) / len(residuals))
        ),
        "row_mean_span": _rounded(max(row_means) - min(row_means)),
        "column_mean_span": _rounded(max(column_means) - min(column_means)),
    }


def compare(baseline_path: Path, permuted_path: Path) -> dict[str, Any]:
    """Return one deterministic comparison without touching hardware."""

    baseline_payload, baseline = _load_json(baseline_path, label="baseline grid")
    permuted_payload, permuted = _load_json(permuted_path, label="permuted grid")
    if Path(baseline_path).resolve() == Path(permuted_path).resolve():
        raise RecipePermutationComparisonError(
            "baseline and permuted files must differ"
        )
    if baseline.get("schema_version") != 1 or baseline.get("kind") != BASE_KIND:
        raise RecipePermutationComparisonError("baseline schema identity differs")
    if permuted.get("schema_version") != 1 or permuted.get("kind") != PERMUTED_KIND:
        raise RecipePermutationComparisonError("permuted schema identity differs")
    baseline_layout = _mapping(baseline.get("campaign_layout"), label="baseline layout")
    permuted_layout = _mapping(permuted.get("campaign_layout"), label="permuted layout")
    if (
        baseline_layout.get("id") != BASE_LAYOUT_ID
        or baseline_layout.get("action_ordinal") != 4
    ):
        raise RecipePermutationComparisonError("baseline layout identity differs")
    if (
        permuted_layout.get("id") != PERMUTED_LAYOUT_ID
        or permuted_layout.get("action_ordinal") != 3
    ):
        raise RecipePermutationComparisonError("permuted layout identity differs")
    baseline_integrity = _verify_integrity(baseline, label="baseline grid")
    permuted_integrity = _verify_integrity(permuted, label="permuted grid")
    baseline_cells = _validate_cells(baseline, permuted=False)
    permuted_cells = _validate_cells(permuted, permuted=True)

    controller_results: list[dict[str, Any]] = []
    recipe_linked_count = 0
    for controller in range(2):
        baseline_by_recipe = {
            value["recipe_id"]: {"lab": value["lab"], "row": row, "column": column}
            for (item_controller, row, column), value in baseline_cells.items()
            if item_controller == controller
        }
        permuted_by_recipe = {
            value["recipe_id"]: {"lab": value["lab"], "row": row, "column": column}
            for (item_controller, row, column), value in permuted_cells.items()
            if item_controller == controller
        }
        recipe_ids = sorted(baseline_by_recipe)
        if recipe_ids != sorted(permuted_by_recipe):
            raise RecipePermutationComparisonError("recipe sets differ")
        recipe_components: list[float | None] = []
        physical_components: list[float | None] = []
        for component in range(3):
            recipe_components.append(
                _pearson(
                    [baseline_by_recipe[item]["lab"][component] for item in recipe_ids],
                    [permuted_by_recipe[item]["lab"][component] for item in recipe_ids],
                )
            )
            positions = [
                (controller, row, column) for row in range(8) for column in range(8)
            ]
            physical_components.append(
                _pearson(
                    [baseline_cells[item]["lab"][component] for item in positions],
                    [permuted_cells[item]["lab"][component] for item in positions],
                )
            )
        recipe_lab = _mean_defined(recipe_components)
        physical_lab = _mean_defined(physical_components)
        lab_margin = (
            None
            if recipe_lab is None or physical_lab is None
            else recipe_lab - physical_lab
        )
        linked = (
            recipe_lab is not None
            and physical_lab is not None
            and recipe_lab >= RECIPE_CORRELATION_FLOOR
            and lab_margin is not None
            and lab_margin >= RECIPE_OVER_POSITION_MARGIN
        )
        delta_plane_by_component = {}
        for component, name in enumerate(("lstar", "astar", "bstar")):
            delta_plane_by_component[name] = _plane_diagnostics(
                [
                    (
                        int(permuted_by_recipe[item]["row"]),
                        int(permuted_by_recipe[item]["column"]),
                        float(permuted_by_recipe[item]["lab"][component])
                        - float(baseline_by_recipe[item]["lab"][component]),
                    )
                    for item in recipe_ids
                ]
            )
        recipe_linked_count += int(linked)
        controller_results.append(
            {
                "controller": controller,
                "recipe_coordinate_pearson": {
                    "lstar": _rounded(recipe_components[0]),
                    "astar": _rounded(recipe_components[1]),
                    "bstar": _rounded(recipe_components[2]),
                },
                "physical_coordinate_pearson": {
                    "lstar": _rounded(physical_components[0]),
                    "astar": _rounded(physical_components[1]),
                    "bstar": _rounded(physical_components[2]),
                },
                "lab_equal_component_pearson": {
                    "recipe_aligned": _rounded(recipe_lab),
                    "physical_position": _rounded(physical_lab),
                    "recipe_over_position_margin": _rounded(lab_margin),
                    "defined_recipe_components": sum(
                        value is not None for value in recipe_components
                    ),
                    "defined_physical_components": sum(
                        value is not None for value in physical_components
                    ),
                },
                "recipe_aligned_delta_plane_by_p1_position": delta_plane_by_component,
                "colour_family_label": "UNASSIGNED_CAMERA_RELATIVE_ONLY",
                "recipe_linked_candidate": linked,
            }
        )
    state = (
        "BOTH_CONTROLLERS_RECIPE_LINKED_CANDIDATE"
        if recipe_linked_count == 2
        else (
            "ONE_CONTROLLER_RECIPE_LINKED_CANDIDATE"
            if recipe_linked_count == 1
            else "NO_RECIPE_LINKED_CANDIDATE"
        )
    )
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "comparison_id": _sha256_bytes(
            _canonical_json(
                {
                    "baseline_file_sha256": _sha256_bytes(baseline_payload),
                    "permuted_file_sha256": _sha256_bytes(permuted_payload),
                    "method": "redpink-p0-p1-recipe-vs-position-v1",
                }
            )
        ),
        "inputs": {
            "baseline": {
                "path": str(baseline_path),
                "bytes": len(baseline_payload),
                "file_sha256": _sha256_bytes(baseline_payload),
                "canonical_integrity_sha256": baseline_integrity,
            },
            "permuted": {
                "path": str(permuted_path),
                "bytes": len(permuted_payload),
                "file_sha256": _sha256_bytes(permuted_payload),
                "canonical_integrity_sha256": permuted_integrity,
            },
        },
        "mapping": {
            "source_at_physical_column": "(column + 3) mod 8",
            "middle_at_physical_row": "7 - row",
            "target_code": 0,
            "bijection_verified": True,
        },
        "thresholds": {
            "minimum_recipe_lab_equal_component_pearson": RECIPE_CORRELATION_FLOOR,
            "minimum_recipe_over_physical_lab_equal_component_margin": RECIPE_OVER_POSITION_MARGIN,
        },
        "controllers": controller_results,
        "classification": {
            "state": state,
            "recipe_linked_controller_count": recipe_linked_count,
            "qualified_new_colour": False,
            "qualified_brightness_level": False,
            "requires_second_independent_permutation_and_repeat": recipe_linked_count
            > 0,
        },
        "evidence_boundaries": {
            "camera_relative_only": True,
            "lab_correlation_is_equal_weight_mean_of_defined_l_a_b_component_pearsons": True,
            "row_column_plane_is_diagnostic_not_a_colour_calibration": True,
            "pearson_is_invariant_to_global_offset_and_scale": True,
            "one_permutation_can_only_create_a_candidate": True,
            "absolute_colour_not_proven": True,
            "device_io_performed": False,
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
        raise RecipePermutationComparisonError(
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
    parser.add_argument("--baseline-grid", type=Path, required=True)
    parser.add_argument("--permuted-grid", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = compare(args.baseline_grid, args.permuted_grid)
        payload = (
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False).encode(
                "utf-8"
            )
            + b"\n"
        )
        _write_exclusive(args.output, payload)
        sys.stdout.buffer.write(payload)
        return 0
    except RecipePermutationComparisonError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
