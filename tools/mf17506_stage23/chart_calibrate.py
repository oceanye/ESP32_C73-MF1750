"""Generate an offline camera-session calibration from 1 or 3 chart photos."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from host.static_photo.chart_calibration import (
    ChartCalibrationError,
    ChartCapture,
    calibrate_chart,
)
from host.static_photo.chart_spec import ChartSpecError, load_chart_spec


def _corners(text: str) -> tuple[tuple[float, float], ...]:
    parts = text.replace(";", " ").split()
    if len(parts) != 4:
        raise ChartCalibrationError("each --corners requires TL TR BR BL")
    try:
        return tuple(
            tuple(float(value) for value in part.split(",", 1)) for part in parts
        )
    except ValueError as error:
        raise ChartCalibrationError(
            "--corners contains an invalid coordinate"
        ) from error


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--photo", type=Path, action="append", required=True)
    parser.add_argument(
        "--corners",
        action="append",
        required=True,
        help='repeat for each photo: "TLx,TLy TRx,TRy BRx,BRy BLx,BLy"',
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if len(args.photo) != len(args.corners):
            raise ChartCalibrationError("--photo and --corners counts must match")
        spec = load_chart_spec(args.spec)
        captures = tuple(
            ChartCapture(photo, _corners(corners))  # type: ignore[arg-type]
            for photo, corners in zip(args.photo, args.corners)
        )
        result = calibrate_chart(spec, captures, output_dir=args.output_dir)
    except (ChartCalibrationError, ChartSpecError) as error:
        print(f"chart calibration error: {error}")
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
