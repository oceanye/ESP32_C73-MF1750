#!/usr/bin/env python3
"""Generate auditable MF-1750 extended-colour fixtures without device I/O."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional, Sequence

if __package__ in (None, ""):
    # Direct script execution adds tools/, rather than the repository root, to
    # sys.path.  This adjustment imports only the offline host package.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from host.extended_color import (  # noqa: E402
    PATTERN_NAMES,
    ExtendedColorContractError,
    build_artifact,
)
from tools.local_path_safety import (  # noqa: E402
    LocalPathSafetyError,
    require_local_regular_path_syntax,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
FROZEN_PRODUCTION_DIR = REPO_ROOT / "hardware" / "mf1750_production_v1" / "production"
FORBIDDEN_LOCAL_DIRECTORY = ".test-output"


class OutputSafetyError(ValueError):
    """Raised before an unsafe or destructive output path can be opened."""


def _is_relative_to(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def _contains_forbidden_component(path: Path) -> bool:
    return any(part.casefold() == FORBIDDEN_LOCAL_DIRECTORY for part in path.parts)


def validate_output_path(path: Path) -> Path:
    """Resolve one new output path and reject protected locations or overwrite."""

    if not isinstance(path, Path):
        raise OutputSafetyError("output path must be a pathlib.Path")
    try:
        require_local_regular_path_syntax(path, label="output path")
    except LocalPathSafetyError as error:
        raise OutputSafetyError(str(error)) from error
    lexical = path.absolute()
    if _contains_forbidden_component(lexical):
        raise OutputSafetyError(f"output must not be inside {FORBIDDEN_LOCAL_DIRECTORY}/")
    try:
        resolved = path.resolve(strict=False)
        frozen = FROZEN_PRODUCTION_DIR.resolve(strict=True)
    except OSError as error:
        raise OutputSafetyError(f"could not resolve output safety boundary: {error}") from error
    if _contains_forbidden_component(resolved):
        raise OutputSafetyError(f"output must not resolve inside {FORBIDDEN_LOCAL_DIRECTORY}/")
    try:
        require_local_regular_path_syntax(resolved, label="resolved output path")
    except LocalPathSafetyError as error:
        raise OutputSafetyError(str(error)) from error
    if resolved == frozen or _is_relative_to(resolved, frozen):
        raise OutputSafetyError("output must not be inside the frozen production directory")
    if resolved.exists() or resolved.is_symlink():
        raise OutputSafetyError("output already exists; overwrite is not supported")
    if not resolved.parent.exists() or not resolved.parent.is_dir():
        raise OutputSafetyError("output parent directory must already exist")
    return resolved


def _positive_repetition(value: str) -> int:
    try:
        repetition = int(value, 10)
    except ValueError as error:
        raise argparse.ArgumentTypeError("repetition must be an integer") from error
    if not 1 <= repetition <= 999:
        raise argparse.ArgumentTypeError("repetition must be from 1 through 999")
    return repetition


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--pattern", choices=PATTERN_NAMES, required=True)
    parser.add_argument("--repetition", type=_positive_repetition, default=1)
    parser.add_argument(
        "--output",
        type=Path,
        help="optionally write the packed 307200-byte frame to a new file",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        help="optionally write the machine-readable JSON report to a new file",
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


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        artifact = build_artifact(args.pattern, args.repetition)
        report = artifact.report()
        rendered = (
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            + "\n"
        ).encode("utf-8")

        if args.output is not None and args.report_output is None:
            raise OutputSafetyError(
                "--output requires --report-output so every frame has an auditable sidecar"
            )
        frame_path = validate_output_path(args.output) if args.output is not None else None
        report_path = (
            validate_output_path(args.report_output)
            if args.report_output is not None
            else None
        )
        if frame_path is not None and report_path is not None and frame_path == report_path:
            raise OutputSafetyError("frame and report outputs must be different files")

        # Both destinations are checked before either is opened.  Persist the
        # identity and safety sidecar first so a later frame-write failure can
        # never leave an unlabelled frame artifact behind.  Exclusive creation
        # provides the final race-safe no-overwrite gate for each destination.
        if report_path is not None:
            _write_new(report_path, rendered)
        if frame_path is not None:
            _write_new(frame_path, artifact.frame)
    except (ExtendedColorContractError, OutputSafetyError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    sys.stdout.write(rendered.decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
