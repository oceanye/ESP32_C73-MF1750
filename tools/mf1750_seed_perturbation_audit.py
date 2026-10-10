#!/usr/bin/env python3
"""Run the zero-I/O MF-1750 seed + perturbation audit."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.runtime_waveform import seed_perturbation  # noqa: E402


def _load_axis(path: Path) -> dict[str, Any]:
    payload = Path(path).read_bytes()
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise seed_perturbation.SeedPerturbationError("axis evidence is invalid JSON") from error
    if not isinstance(value, dict):
        raise seed_perturbation.SeedPerturbationError("axis evidence must be an object")
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "--created-at",
        default=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    )
    parser.add_argument("--axis-evidence", type=Path)
    parser.add_argument("--value", action="append", type=float, dest="values", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        axis = _load_axis(args.axis_evidence) if args.axis_evidence else None
        report = seed_perturbation.build_report(
            created_at=args.created_at,
            axis=axis,
            values=args.values,
        )
        seed_perturbation.validate_report(report)
        if args.output:
            seed_perturbation.write_report(args.output, report)
    except (OSError, seed_perturbation.SeedPerturbationError) as error:
        print(f"seed perturbation audit error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=None if args.compact else 2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
