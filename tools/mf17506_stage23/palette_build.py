"""Build a screening-only history palette from A/A-prime analyses."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from host.static_photo.palette_builder import PaletteBuildError, build_screening_palette


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--analysis", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--palette-id", required=True)
    parser.add_argument("--primer-dwell-ms", type=int, default=2000)
    parser.add_argument("--temperature-min-c", type=float, required=True)
    parser.add_argument("--temperature-max-c", type=float, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = build_screening_palette(
            args.analysis,
            output_file=args.output,
            palette_id=args.palette_id,
            primer_dwell_ms=args.primer_dwell_ms,
            temperature_min_c=args.temperature_min_c,
            temperature_max_c=args.temperature_max_c,
        )
    except PaletteBuildError as error:
        print(f"palette build error: {error}")
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
