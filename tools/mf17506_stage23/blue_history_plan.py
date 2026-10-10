"""Build the immutable offline A/A-prime 16-blue-recipe test bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from host.static_photo.blue_history import (
    BlueHistoryPlanError,
    build_blue_history_bundle,
)
from host.static_photo.common import StaticPhotoContractError


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("build", nargs="?")
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = build_blue_history_bundle(args.output_dir)
    except (BlueHistoryPlanError, StaticPhotoContractError) as error:
        print(f"blue history plan error: {error}")
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
