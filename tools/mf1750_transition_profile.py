#!/usr/bin/env python3
"""Emit an empty 6x6 MF-1750 profile; all unmeasured values remain null."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from host.extended_color import (  # noqa: E402
    build_empty_transition_profile,
    validate_transition_profile,
)
from tools.mf1750_extended_color import (  # noqa: E402
    OutputSafetyError,
    validate_output_path,
)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "--output",
        type=Path,
        help="optional new JSON file; existing and protected paths are rejected",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    profile = build_empty_transition_profile()
    validate_transition_profile(profile)
    rendered = (
        json.dumps(
            profile,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )
    try:
        output = validate_output_path(args.output) if args.output is not None else None
        if output is not None:
            with output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(rendered)
    except (OSError, OutputSafetyError) as error:
        sys.stderr.write(f"ERROR: {error}\n")
        return 2
    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
