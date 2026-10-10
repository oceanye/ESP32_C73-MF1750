#!/usr/bin/env python3
"""Print the offline MF1750 target-hue and lightness collection catalogue."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.extended_color.mf1750_target_hues import build_catalog  # noqa: E402


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def describe() -> dict[str, object]:
    catalogue = build_catalog()
    catalogue["catalog_id"] = hashlib.sha256(_canonical(catalogue)).hexdigest()
    return catalogue


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="pretty-print UTF-8 JSON instead of canonical single-line JSON",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(
        json.dumps(
            describe(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
