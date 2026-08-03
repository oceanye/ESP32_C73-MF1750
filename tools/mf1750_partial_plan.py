#!/usr/bin/env python3
"""Generate an offline controller-neutral MF-1750 partial-update plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional, Sequence

from host.partial_update import PartialUpdateContractError, build_transition_plan


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("new_frame", type=Path, help="canonical 1024x600 4bpp new frame")
    parser.add_argument("--old-frame", type=Path, help="canonical previous frame; omit if unknown")
    parser.add_argument(
        "--neighbor-radius",
        type=int,
        default=1,
        help="cardinal-neighbor protection radius in pixels (default: 1)",
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

