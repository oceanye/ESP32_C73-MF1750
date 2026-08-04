#!/usr/bin/env python3
"""Generate an offline controller-neutral MF-1750 partial-update plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional, Sequence

if __package__ in (None, ""):
    # ``python tools/mf1750_partial_plan.py`` puts tools/, not the repository
    # root, on sys.path. Keep the documented direct-script invocation working.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from host.epd_frame import ControllerMapping, FrameContractError
from host.partial_update import PartialUpdateContractError, build_transition_plan


def _parse_u32(value: str) -> int:
    try:
        parsed = int(value, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected an integer such as 1234 or 0x04D2") from error
    if not 0 <= parsed <= 0xFFFFFFFF:
        raise argparse.ArgumentTypeError("hash must fit in an unsigned 32-bit integer")
    return parsed


def _parse_mapping(value: str) -> ControllerMapping:
    fields = [field.strip() for field in value.split(",")]
    if len(fields) != 4:
        raise argparse.ArgumentTypeError(
            "mapping must be SOURCE_HALF,FLIP_X,FLIP_Y,NIBBLE_SWAP using 0 or 1"
        )
    try:
        numbers = [int(field) for field in fields]
    except ValueError as error:
        raise argparse.ArgumentTypeError("mapping fields must be 0 or 1") from error
    if any(number not in (0, 1) for number in numbers):
        raise argparse.ArgumentTypeError("mapping fields must be 0 or 1")
    try:
        return ControllerMapping(
            source_half=numbers[0],
            flip_x=bool(numbers[1]),
            flip_y=bool(numbers[2]),
            nibble_swap=bool(numbers[3]),
        )
    except FrameContractError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("new_frame", type=Path, help="canonical 1024x600 4bpp new frame")
    parser.add_argument(
        "--old-frame",
        type=Path,
        help="candidate previous frame; this file alone does not establish panel state",
    )
    parser.add_argument(
        "--last-success-operation-id",
        help="operation ID recorded after the last successful physical display update",
    )
    parser.add_argument(
        "--last-success-frame-fnv1a",
        type=_parse_u32,
        help="FNV-1a of that successful frame (decimal or 0x-prefixed)",
    )
    parser.add_argument(
        "--trust-last-success",
        action="store_true",
        help="explicitly trust the operation record; requires matching ID, hash, and --old-frame",
    )
    parser.add_argument(
        "--neighbor-radius",
        type=int,
        default=1,
        help="cardinal-neighbor protection radius in pixels, 0..32 (default: 1)",
    )
    parser.add_argument(
        "--frozen-controller-mapping",
        action="append",
        type=_parse_mapping,
        metavar="SOURCE_HALF,FLIP_X,FLIP_Y,NIBBLE_SWAP",
        help=(
            "optional frozen mapping; repeat exactly twice in physical-controller order "
            "to add physical coordinates (example: 0,0,0,0)"
        ),
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise PartialUpdateContractError(f"cannot read {path}: {error}") from error


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        old_frame = _read(args.old_frame) if args.old_frame else None
        plan = build_transition_plan(
            old_frame,
            _read(args.new_frame),
            neighbor_radius=args.neighbor_radius,
            last_success_operation_id=args.last_success_operation_id,
            last_success_frame_fnv1a=args.last_success_frame_fnv1a,
            last_success_trusted=args.trust_last_success,
            frozen_controller_mappings=args.frozen_controller_mapping,
        ).to_dict()
    except PartialUpdateContractError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    rendered = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
