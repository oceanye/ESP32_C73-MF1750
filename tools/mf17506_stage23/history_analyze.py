"""Analyze one A/A-prime blue-history photo without device I/O."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from host.static_photo.history_analysis import (
    HistoryAnalysisError,
    analyze_history_photo,
)


def _corners(text: str) -> tuple[tuple[float, float], ...]:
    parts = text.replace(";", " ").split()
    if len(parts) != 4:
        raise HistoryAnalysisError("--panel-corners requires TL TR BR BL")
    try:
        return tuple(
            tuple(float(value) for value in part.split(",", 1)) for part in parts
        )
    except ValueError as error:
        raise HistoryAnalysisError(
            "--panel-corners contains an invalid coordinate"
        ) from error


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--photo", type=Path, required=True)
    parser.add_argument("--panel-corners", required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--plan-manifest", type=Path, required=True)
    parser.add_argument("--batch", choices=("A", "A-prime"), required=True)
    parser.add_argument(
        "--timepoint-seconds", type=int, choices=(5, 60, 600), required=True
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = analyze_history_photo(
            args.photo,
            panel_corners=_corners(args.panel_corners),
            calibration_file=args.calibration,
            plan_manifest_file=args.plan_manifest,
            batch_id=args.batch,
            timepoint_seconds=args.timepoint_seconds,
            output_dir=args.output_dir,
        )
    except HistoryAnalysisError as error:
        print(f"history photo analysis error: {error}")
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
