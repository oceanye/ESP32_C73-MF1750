#!/usr/bin/env python3
"""Compare a factory-white candidate to a locked-camera white reference.

This is an offline, camera-relative gate.  It samples a panel-wide patch grid
through a previously sealed logical-to-photo homography; it does not open a
camera or touch the display.  Passing means the candidate matches the bound
factory-white reference within the measured repeat-noise envelope, not that
an absolute calibrated white point has been established.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

import numpy as np

from tools import mf1750_same_r20_atlas_photo_analyzer as common
from tools import mf1750_true_r20_hold_photo_gate as static_gate


SCHEMA_VERSION = 1
KIND = "mf1750-factory-white-locked-camera-reference-gate"
LAYOUT_ID = "MF1750_LOGICAL_PANEL_WIDE_WHITE_PATCH_GRID_V1"
INTEGRITY_ALGORITHM = common.INTEGRITY_ALGORITHM
ROWS = 6
COLUMNS_PER_CONTROLLER = 5
X_MARGIN = 32
Y_MARGIN = 32
PATCH_WIDTH = 48
PATCH_HEIGHT = 48


class FactoryWhiteReferencePhotoGateError(RuntimeError):
    """Raised when white/reference evidence or output is invalid."""


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
        raise FactoryWhiteReferencePhotoGateError(
            f"record contains a non-canonical JSON value: {exc}"
        ) from exc


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _bounds(controller: int, row: int, column: int) -> tuple[int, int, int, int]:
    usable_width = common.CONTROLLER_WIDTH - 2 * X_MARGIN
    usable_height = common.LOGICAL_HEIGHT - 2 * Y_MARGIN
    centre_x = X_MARGIN + (column + 0.5) * usable_width / COLUMNS_PER_CONTROLLER
    centre_y = Y_MARGIN + (row + 0.5) * usable_height / ROWS
    x = controller * common.CONTROLLER_WIDTH + round(centre_x - PATCH_WIDTH / 2)
    y = round(centre_y - PATCH_HEIGHT / 2)
    return x, y, PATCH_WIDTH, PATCH_HEIGHT


def analyze(
    candidate_photo: Path,
    white_reference_photo: Path,
    reference_grid_path: Path,
    *,
    repeat_noise_p95_de76: float | None = None,
) -> dict[str, Any]:
    """Return a sealed panel-wide, camera-relative white comparison."""

    if Path(candidate_photo).resolve() == Path(white_reference_photo).resolve():
        raise FactoryWhiteReferencePhotoGateError(
            "candidate and white reference photos must differ"
        )
    if repeat_noise_p95_de76 is not None and (
        not math.isfinite(repeat_noise_p95_de76) or repeat_noise_p95_de76 < 0
    ):
        raise FactoryWhiteReferencePhotoGateError(
            "repeat noise must be finite and nonnegative"
        )
    try:
        reference_payload, _, homography, dimensions = static_gate._load_reference(
            reference_grid_path
        )
        candidate_payload, candidate_image = static_gate._decode(
            candidate_photo, dimensions, label="candidate white photo"
        )
        white_payload, white_image = static_gate._decode(
            white_reference_photo, dimensions, label="factory-white reference photo"
        )
        candidate = static_gate._rectify(candidate_image, homography)
        white = static_gate._rectify(white_image, homography)
    except static_gate.TrueR20HoldPhotoGateError as exc:
        raise FactoryWhiteReferencePhotoGateError(str(exc)) from exc

    patches: list[dict[str, Any]] = []
    deltas: list[float] = []
    for controller in range(2):
        for row in range(ROWS):
            for column in range(COLUMNS_PER_CONTROLLER):
                bounds = _bounds(controller, row, column)
                candidate_lab = static_gate._median_lab(candidate, bounds)
                white_lab = static_gate._median_lab(white, bounds)
                delta = static_gate._distance(candidate_lab, white_lab)
                deltas.append(delta)
                patches.append(
                    {
                        "controller": controller,
                        "row": row,
                        "column": column,
                        "logical_bounds": list(bounds),
                        "candidate_lab": candidate_lab.astype(float).tolist(),
                        "reference_lab": white_lab.astype(float).tolist(),
                        "camera_relative_de76": delta,
                    }
                )

    threshold = (
        None if repeat_noise_p95_de76 is None else max(4.0, 3.0 * repeat_noise_p95_de76)
    )
    maximum_threshold = None if threshold is None else max(8.0, 1.5 * threshold)
    observed_p95 = float(np.percentile(deltas, 95))
    observed_max = float(max(deltas))
    gate = (
        None
        if threshold is None
        else observed_p95 <= threshold and observed_max <= maximum_threshold
    )
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "analysis_id": _sha256_bytes(
            _canonical_json(
                {
                    "candidate_sha256": _sha256_bytes(candidate_payload),
                    "white_reference_sha256": _sha256_bytes(white_payload),
                    "geometry_reference_sha256": _sha256_bytes(reference_payload),
                    "method": "locked-camera-panel-wide-white-patch-grid-v1",
                }
            )
        ),
        "layout": {
            "id": LAYOUT_ID,
            "controllers": 2,
            "rows": ROWS,
            "columns_per_controller": COLUMNS_PER_CONTROLLER,
            "patch_count": len(patches),
            "full_logical_width": common.LOGICAL_WIDTH,
            "full_logical_height": common.LOGICAL_HEIGHT,
            "panel_wide_discrete_patch_sampling": True,
        },
        "inputs": {
            "candidate": {
                "path": str(candidate_photo),
                "bytes": len(candidate_payload),
                "sha256": _sha256_bytes(candidate_payload),
            },
            "factory_white_reference": {
                "path": str(white_reference_photo),
                "bytes": len(white_payload),
                "sha256": _sha256_bytes(white_payload),
            },
            "geometry_reference": {
                "path": str(reference_grid_path),
                "bytes": len(reference_payload),
                "sha256": _sha256_bytes(reference_payload),
            },
        },
        "thresholds": {
            "repeat_noise_p95_de76": repeat_noise_p95_de76,
            "patch_grid_p95_de76": threshold,
            "patch_grid_max_de76": maximum_threshold,
        },
        "summary": {
            "patch_count": len(patches),
            "camera_relative_de76_median": float(np.median(deltas)),
            "camera_relative_de76_p95": observed_p95,
            "camera_relative_de76_max": observed_max,
            "all_panel_regions_match_reference": gate,
        },
        "patches": patches,
        "classification": {
            "state": (
                "PANEL_WIDE_CAMERA_RELATIVE_FACTORY_WHITE_MATCH"
                if gate is True
                else (
                    "PANEL_WIDE_CAMERA_RELATIVE_FACTORY_WHITE_MISMATCH"
                    if gate is False
                    else "INCONCLUSIVE_NEEDS_REPEAT_NOISE_BASELINE"
                )
            ),
            "pass": gate,
            "absolute_white_proven": False,
        },
        "evidence_boundaries": {
            "camera_must_remain_locked": True,
            "camera_relative_de76_not_calibrated_de00": True,
            "discrete_patch_grid_not_every_pixel": True,
            "device_io_performed": False,
        },
        "output_write_contract": "O_EXCL",
    }
    unsigned["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": _sha256_bytes(_canonical_json(unsigned)),
    }
    return unsigned


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--candidate-photo", type=Path, required=True)
    parser.add_argument("--factory-white-reference-photo", type=Path, required=True)
    parser.add_argument("--reference-grid-analysis", type=Path, required=True)
    parser.add_argument("--repeat-noise-p95-de76", type=float)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = analyze(
            args.candidate_photo,
            args.factory_white_reference_photo,
            args.reference_grid_analysis,
            repeat_noise_p95_de76=args.repeat_noise_p95_de76,
        )
        payload = (
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False).encode(
                "utf-8"
            )
            + b"\n"
        )
        common._write_exclusive(args.output, payload)
        sys.stdout.buffer.write(payload)
        return 0
    except (
        FactoryWhiteReferencePhotoGateError,
        common.SameR20AtlasAnalysisError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
