#!/usr/bin/env python3
"""Adapt the frozen Red/Pink 8x8 photo sampler to the P1 recipe layout.

The geometry and pixel sampling remain delegated to the already-tested V2
analyzer.  This adapter changes only the campaign identity and the mapping
from physical row/column to the deliberately permuted recipe identity.
It is offline-only and never accesses the panel or a camera device.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

from tools import mf1750_redpink_v2_grid_photo_analyzer as base


SCHEMA_VERSION = 1
KIND = "mf1750-redpink-recipe-permutation-dual-8x8-camera-relative-grid-analysis"
LAYOUT_ID = "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_RECIPE_PERMUTATION_V1"
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
SOURCE_COLUMN_SHIFT = 3
MIDDLE_ROW_REVERSED = True
TARGET_CODE = 0


class PermutedGridAnalysisError(RuntimeError):
    """Raised when source analysis or exclusive output is invalid."""


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
        raise PermutedGridAnalysisError(
            f"record contains a non-canonical JSON value: {exc}"
        ) from exc


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def recipe_for_physical(row: int, column: int) -> tuple[int, int, int, str]:
    """Return the fixed P1 source/middle/target identity for one cell."""

    if row not in range(8) or column not in range(8):
        raise PermutedGridAnalysisError("physical row/column must be in range 0..7")
    source = (column + SOURCE_COLUMN_SHIFT) % 8
    middle = 7 - row if MIDDLE_ROW_REVERSED else row
    recipe = f"REDPINK-A{source}-B{middle}-A{TARGET_CODE}"
    return source, middle, TARGET_CODE, recipe


def adapt_base_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return a P1-semantic report from one in-memory V2 geometry report."""

    cells = report.get("cells")
    if not isinstance(cells, list) or len(cells) != 128:
        raise PermutedGridAnalysisError("base report must contain exactly 128 cells")

    mapped_cells: list[dict[str, Any]] = []
    mapping: list[dict[str, Any]] = []
    seen: set[tuple[int, int, int]] = set()
    for index, item in enumerate(cells):
        if not isinstance(item, dict):
            raise PermutedGridAnalysisError(f"cells[{index}] must be an object")
        controller = item.get("controller")
        row = item.get("row")
        column = item.get("column")
        if type(controller) is not int or controller not in (0, 1):
            raise PermutedGridAnalysisError(f"cells[{index}].controller differs")
        if type(row) is not int or type(column) is not int:
            raise PermutedGridAnalysisError(f"cells[{index}] coordinates differ")
        key = (controller, row, column)
        if key in seen:
            raise PermutedGridAnalysisError(f"duplicate physical cell {key}")
        seen.add(key)
        source, middle, target, recipe = recipe_for_physical(row, column)
        mapped = dict(item)
        mapped["cell_id"] = f"C{controller}-R{row}-K{column}"
        mapped["recipe_id"] = recipe
        mapped["recipe_codes"] = {
            "source": source,
            "middle": middle,
            "target": target,
        }
        mapped_cells.append(mapped)
        mapping.append(
            {
                "controller": controller,
                "physical_row": row,
                "physical_column": column,
                "source_code": source,
                "middle_code": middle,
                "target_code": target,
                "recipe_id": recipe,
            }
        )
    if len(seen) != 128:
        raise PermutedGridAnalysisError("base report does not cover the dual 8x8 grid")

    judgement = report.get("grid_judgement")
    if not isinstance(judgement, dict):
        raise PermutedGridAnalysisError("base report grid judgement is missing")
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source_photo": report.get("source_photo"),
        "campaign_layout": {
            "id": LAYOUT_ID,
            "action_ordinal": 3,
            "controllers_are_not_assumed_colour_equivalent": True,
            "source_column_shift_mod8": SOURCE_COLUMN_SHIFT,
            "middle_row_reversed": MIDDLE_ROW_REVERSED,
            "fixed_target_code": TARGET_CODE,
        },
        "method": {
            "geometry_sampler": "mf1750_redpink_v2_grid_photo_analyzer",
            "geometry_sampler_report_kind": report.get("kind"),
            "geometry_sampler_report_schema": report.get("schema_version"),
            "geometry_sampler_forced_layout_ordinal": 4,
            "semantic_adapter": "redpink-recipe-permutation-p1-v1",
            "perspective_rectified": True,
            "physical_colour_calibrated": False,
            "device_io_performed": False,
        },
        "geometry_quality": report.get("geometry_quality"),
        "grid_judgement": judgement,
        "cells": mapped_cells,
        "recipe_physical_mapping": mapping,
        "physical_axis_diagnostics": report.get("row_column_differences"),
        "evidence_boundaries": {
            "camera_relative_only": True,
            "single_permuted_capture_does_not_qualify_a_colour": True,
            "comparison_with_bound_p0_is_required": True,
            "compiled_mapping_does_not_prove_bus_reception": True,
        },
        "output_write_contract": "O_EXCL",
    }
    unsigned["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": _sha256_bytes(_canonical_json(unsigned)),
    }
    return unsigned


def analyze(photo_path: Path) -> dict[str, Any]:
    """Analyze one already-captured P1 photograph without device I/O."""

    try:
        report = base.analyze(Path(photo_path), ordinal=4)
    except base.GridPhotoAnalysisError as exc:
        raise PermutedGridAnalysisError(str(exc)) from exc
    return adapt_base_report(report)


def _write_exclusive(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, flags, 0o644)
    except FileExistsError as exc:
        raise PermutedGridAnalysisError(
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
    parser.add_argument("--photo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = analyze(args.photo)
        payload = (
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False).encode(
                "utf-8"
            )
            + b"\n"
        )
        _write_exclusive(args.output, payload)
        sys.stdout.buffer.write(payload)
        return 0
    except PermutedGridAnalysisError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
