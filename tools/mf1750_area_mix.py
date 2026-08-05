#!/usr/bin/env python3
"""Rank and render formal six-colour MF-1750 area-mix recipes offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from host.color_pipeline import (  # noqa: E402
    ColorValueError,
    PaletteError,
    load_palette,
    reference_palette,
    srgb8_to_lab,
)
from host.extended_color import (  # noqa: E402
    DEFAULT_RESULT_LIMIT,
    DEFAULT_TILE_SIDE,
    MAX_RESULT_LIMIT,
    SUPPORTED_TILE_SIDES,
    AreaMixError,
    analyze_area_mixes,
)
from tools.mf1750_extended_color import (  # noqa: E402
    FORBIDDEN_LOCAL_DIRECTORY,
    OutputSafetyError,
    validate_output_path,
)
from tools.local_path_safety import (  # noqa: E402
    LocalPathSafetyError,
    require_local_regular_path_syntax,
)


def _rgb_channel(value: str) -> int:
    try:
        channel = int(value, 10)
    except ValueError as error:
        raise argparse.ArgumentTypeError("sRGB channels must be integers") from error
    if not 0 <= channel <= 255:
        raise argparse.ArgumentTypeError("sRGB channels must be in [0, 255]")
    return channel


def _limit(value: str) -> int:
    try:
        result = int(value, 10)
    except ValueError as error:
        raise argparse.ArgumentTypeError("limit must be an integer") from error
    if not 1 <= result <= MAX_RESULT_LIMIT:
        raise argparse.ArgumentTypeError(f"limit must be in [1, {MAX_RESULT_LIMIT}]")
    return result


def _rank(value: str) -> int:
    try:
        result = int(value, 10)
    except ValueError as error:
        raise argparse.ArgumentTypeError("candidate rank must be an integer") from error
    if result < 1:
        raise argparse.ArgumentTypeError("candidate rank must be positive")
    return result


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--target-lab",
        nargs=3,
        type=float,
        metavar=("L", "A", "B"),
        help="target CIELAB value under D65/2deg",
    )
    target.add_argument(
        "--target-srgb",
        nargs=3,
        type=_rgb_channel,
        metavar=("R", "G", "B"),
        help="target 8-bit sRGB preview value",
    )
    parser.add_argument(
        "--palette",
        type=Path,
        help="calibrated six-colour palette JSON; required for non-simulation use",
    )
    parser.add_argument(
        "--allow-uncalibrated-simulation",
        action="store_true",
        help="explicitly permit the bundled non-panel reference palette for planning only",
    )
    parser.add_argument(
        "--tile-side",
        type=int,
        choices=SUPPORTED_TILE_SIDES,
        default=DEFAULT_TILE_SIDE,
    )
    parser.add_argument("--limit", type=_limit, default=DEFAULT_RESULT_LIMIT)
    parser.add_argument(
        "--candidate-rank",
        type=_rank,
        default=1,
        help="rank to render when --frame-output is supplied",
    )
    parser.add_argument(
        "--frame-output",
        type=Path,
        help="optionally create one packed 307200-byte formal six-colour frame",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        help="optionally create the complete machine-readable JSON report",
    )
    return parser.parse_args(argv)


def _write_new(path: Path, content: bytes) -> None:
    try:
        with path.open("xb") as destination:
            destination.write(content)
    except FileExistsError as error:
        raise OutputSafetyError("output appeared before write; refusing overwrite") from error
    except OSError as error:
        raise OutputSafetyError(f"could not write output: {error}") from error


def validate_palette_path(path: Path) -> Path:
    """Resolve one palette file without ever reading protected local test data."""

    if not isinstance(path, Path):
        raise OutputSafetyError("palette path must be a pathlib.Path")
    try:
        require_local_regular_path_syntax(path, label="palette path")
    except LocalPathSafetyError as error:
        raise OutputSafetyError(str(error)) from error
    lexical = path.absolute()
    if any(part.casefold() == FORBIDDEN_LOCAL_DIRECTORY for part in lexical.parts):
        raise OutputSafetyError(
            f"palette must not be read from {FORBIDDEN_LOCAL_DIRECTORY}/"
        )
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise OutputSafetyError(f"could not resolve palette path: {error}") from error
    if any(part.casefold() == FORBIDDEN_LOCAL_DIRECTORY for part in resolved.parts):
        raise OutputSafetyError(
            f"palette must not resolve inside {FORBIDDEN_LOCAL_DIRECTORY}/"
        )
    try:
        require_local_regular_path_syntax(resolved, label="resolved palette path")
    except LocalPathSafetyError as error:
        raise OutputSafetyError(str(error)) from error
    if not resolved.is_file():
        raise OutputSafetyError("palette path must be a regular file")
    return resolved


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        palette = (
            load_palette(validate_palette_path(args.palette))
            if args.palette is not None
            else reference_palette()
        )
        if args.target_lab is not None:
            target_lab = tuple(args.target_lab)
            input_space = "Lab"
            input_values = tuple(args.target_lab)
        else:
            input_values = tuple(args.target_srgb)
            target_lab = srgb8_to_lab(input_values)
            input_space = "sRGB8"

        if args.candidate_rank > args.limit:
            raise AreaMixError("candidate rank cannot exceed the requested result limit")
        if args.frame_output is not None and args.report_output is None:
            raise AreaMixError(
                "--frame-output requires --report-output so the selected frame has an auditable sidecar"
            )
        if args.frame_output is None and args.candidate_rank != 1:
            raise AreaMixError("--candidate-rank is only meaningful with --frame-output")
        analysis = analyze_area_mixes(
            palette,
            target_lab,
            tile_side=args.tile_side,
            limit=args.limit,
            allow_uncalibrated_simulation=args.allow_uncalibrated_simulation,
            target_input_space=input_space,
            target_input_values=input_values,
        )
        report = analysis.report(
            rendered_candidate_rank=(
                args.candidate_rank if args.frame_output is not None else None
            )
        )
        rendered_report = (
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            + "\n"
        ).encode("utf-8")

        frame_path = (
            validate_output_path(args.frame_output)
            if args.frame_output is not None
            else None
        )
        report_path = (
            validate_output_path(args.report_output)
            if args.report_output is not None
            else None
        )
        if frame_path is not None and report_path is not None and frame_path == report_path:
            raise OutputSafetyError("frame and report outputs must be different files")
        # Persist the identity sidecar first. A later frame write error can then
        # never leave an unlabelled frame artifact behind.
        if report_path is not None:
            _write_new(report_path, rendered_report)
        if frame_path is not None:
            _write_new(frame_path, analysis.recipes[args.candidate_rank - 1].frame())
    except (AreaMixError, ColorValueError, PaletteError, OutputSafetyError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    sys.stdout.write(rendered_report.decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
