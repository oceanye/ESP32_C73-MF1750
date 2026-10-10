"""Generate four offline static-photo candidates from a qualified history palette."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from host.application.images import FitPolicy
from host.static_photo.photo_render import PhotoRenderError, build_photo_bundle


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--palette", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--fit", choices=tuple(item.value for item in FitPolicy), default="cover"
    )
    parser.add_argument("--recipe-cell-px", type=int, choices=(1, 2, 4, 8), default=1)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = build_photo_bundle(
            args.source,
            args.palette,
            output_dir=args.output_dir,
            fit=args.fit,
            recipe_cell_px=args.recipe_cell_px,
        )
    except PhotoRenderError as error:
        print(f"static photo render error: {error}")
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
