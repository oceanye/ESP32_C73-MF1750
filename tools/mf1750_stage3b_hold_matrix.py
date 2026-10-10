#!/usr/bin/env python3
"""Describe and evaluate the Stage III-B palette-preservation matrix.

This module performs no hardware, relay, serial, network, flash or refresh
operation.  It evaluates registered camera measurements only after the caller
explicitly states that camera calibration is complete.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


BASE_FRAME_SHA256 = "06be3a9df65efdf86dc1552015daf16d6e2c59c06747a5291957c9c816d746e3"
OVERLAY_FRAME_SHA256 = "c645344fa4daa0429d47626ca35e9be770e78684fac47f7bc9ebdb2fa10b85f8"


class HoldMatrixError(ValueError):
    """The matrix geometry or calibrated measurement contract differs."""


def build_frame(role: str) -> bytes:
    if role not in {"base_rows", "overlay_columns"}:
        raise HoldMatrixError("role must be base_rows or overlay_columns")
    frame = bytearray(1024 * 600 // 2)
    for y in range(600):
        source = y // 75
        for x in range(0, 1024, 2):
            target = (x % 512) // 64
            code = source if role == "base_rows" else target
            frame[(y * 1024 + x) // 2] = (code << 4) | code
    return bytes(frame)


def describe() -> dict[str, Any]:
    base = build_frame("base_rows")
    overlay = build_frame("overlay_columns")
    if hashlib.sha256(base).hexdigest() != BASE_FRAME_SHA256:
        raise HoldMatrixError("base frame identity differs")
    if hashlib.sha256(overlay).hexdigest() != OVERLAY_FRAME_SHA256:
        raise HoldMatrixError("overlay frame identity differs")
    return {
        "schema_version": 1,
        "kind": "mf1750-stage3b-hold-matrix-plan",
        "goal": "FULL_SCAN_MASKED_LOCAL_COLOUR_OVERLAY",
        "claim_is_true_controller_partial_refresh": False,
        "sequence": [
            "PALETTE_A_BASE_ROWS",
            "FIXED_CAMERA_CAPTURE_BEFORE",
            "PALETTE_B_OVERLAY_COLUMNS",
            "FIXED_CAMERA_CAPTURE_AFTER",
            "CALIBRATED_8X8_PRESERVATION_CLASSIFICATION",
        ],
        "geometry_per_controller": {
            "rows": 8,
            "columns": 8,
            "cell_width": 64,
            "cell_height": 75,
            "transitions": 64,
        },
        "full_screen_transition_observations": 128,
        "base_frame_sha256": BASE_FRAME_SHA256,
        "overlay_frame_sha256": OVERLAY_FRAME_SHA256,
        "universal_hold_definition": (
            "one palette-B target code preserves all eight palette-A source states"
        ),
        "source_specific_hold_definition": (
            "each palette-A source state has at least one preserving palette-B target code"
        ),
        "release_gate": "ONLY_AFTER_A_STABLE_PALETTE_B_IS_OBSERVED",
        "camera_calibration_required": True,
        "automatic_chaining": False,
        "unknown_window_commands": False,
        "partial_refresh": False,
        "raw_runtime_ingress": False,
        "device_requests": 0,
        "visible_refreshes": 0,
    }


def _matrix(value: Any, label: str) -> list[list[float]]:
    if not isinstance(value, list) or len(value) != 8:
        raise HoldMatrixError(f"{label} must have eight source rows")
    result = []
    for row in value:
        if not isinstance(row, list) or len(row) != 8:
            raise HoldMatrixError(f"{label} rows must have eight target columns")
        converted = [float(item) for item in row]
        if any(item < 0 for item in converted):
            raise HoldMatrixError(f"{label} cannot contain negative values")
        result.append(converted)
    return result


def evaluate(
    value: Mapping[str, Any], *, delta_e_limit: float, within_std_limit: float
) -> dict[str, Any]:
    if value.get("schema_version") != 1 or value.get("kind") != (
        "mf1750-stage3b-calibrated-hold-measurements"
    ):
        raise HoldMatrixError("measurement schema/kind differs")
    if value.get("camera_calibrated") is not True:
        raise HoldMatrixError("camera must be explicitly calibrated")
    controllers = value.get("controllers")
    if not isinstance(controllers, Mapping) or set(controllers) != {"CS1", "CS2"}:
        raise HoldMatrixError("measurements require exact CS1 and CS2 matrices")
    output: dict[str, Any] = {}
    for controller, measurement in controllers.items():
        if not isinstance(measurement, Mapping):
            raise HoldMatrixError(f"{controller} measurement must be an object")
        delta = _matrix(measurement.get("delta_e_from_before"), f"{controller} delta")
        std = _matrix(measurement.get("within_cell_delta_e_std"), f"{controller} std")
        passing = [
            [delta[source][target] <= delta_e_limit and std[source][target] <= within_std_limit
             for target in range(8)]
            for source in range(8)
        ]
        universal = [target for target in range(8) if all(row[target] for row in passing)]
        source_specific = []
        all_sources_preservable = True
        for source in range(8):
            candidates = [target for target in range(8) if passing[source][target]]
            if not candidates:
                all_sources_preservable = False
                source_specific.append(None)
            else:
                source_specific.append(min(candidates, key=lambda target: delta[source][target]))
        output[controller] = {
            "universal_hold_codes": universal,
            "source_specific_hold_codes": source_specific,
            "all_source_states_preservable": all_sources_preservable,
            "masked_local_overlay_candidate": bool(universal) or all_sources_preservable,
        }
    return {
        "schema_version": 1,
        "kind": "mf1750-stage3b-hold-evaluation",
        "delta_e_limit": delta_e_limit,
        "within_cell_delta_e_std_limit": within_std_limit,
        "controllers": output,
        "both_controllers_masked_overlay_candidate": all(
            item["masked_local_overlay_candidate"] for item in output.values()
        ),
        "true_partial_refresh_proven": False,
        "automatic_next_request_authorized": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("describe")
    evaluate_parser = commands.add_parser("evaluate")
    evaluate_parser.add_argument("--measurements", type=Path, required=True)
    evaluate_parser.add_argument("--delta-e-limit", type=float, required=True)
    evaluate_parser.add_argument("--within-std-limit", type=float, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "describe":
            result = describe()
        else:
            value = json.loads(args.measurements.read_text(encoding="utf-8"))
            result = evaluate(
                value,
                delta_e_limit=args.delta_e_limit,
                within_std_limit=args.within_std_limit,
            )
    except (HoldMatrixError, OSError, ValueError) as error:
        print(f"hold-matrix error: {error}")
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

