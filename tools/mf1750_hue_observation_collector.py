#!/usr/bin/env python3
"""Generate, validate, or summarize MF1750 hue/lightness observations.

All commands are offline-only.  The tool imports immutable recipe identities
but contains no serial, network, relay, flashing, or display-refresh path.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.extended_color.mf1750_hue_observations import (  # noqa: E402
    HueObservationError,
    build_observation_template,
    canonical_json,
    summarize_observation_document,
    validate_observation_document,
)
from tools import mf1750_runtime_lut_hue_brightness_blue_v1_pack as blue  # noqa: E402
from tools.mf1750_target_hue_catalog import describe as describe_catalog  # noqa: E402


class _DuplicateKeyError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def source_template() -> dict[str, Any]:
    """Return the template bound to the current reviewed catalog and pack."""

    return build_observation_template(describe_catalog(), blue.build_report())


def load_document(path: str | Path) -> Mapping[str, Any]:
    source = Path(path)
    try:
        raw = source.read_text(encoding="utf-8")
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError, _DuplicateKeyError) as error:
        raise HueObservationError(f"cannot load observation JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise HueObservationError("observation JSON root must be an object")
    return value


def generate() -> dict[str, Any]:
    return source_template()


def validate(path: str | Path) -> dict[str, Any]:
    return validate_observation_document(load_document(path), source_template())


def summary(path: str | Path) -> dict[str, Any]:
    return summarize_observation_document(load_document(path), source_template())


def _add_output_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output",
        type=Path,
        help="write JSON to this new file; omit to print to stdout",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace --output if it already exists",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="indent JSON for human editing (identity remains canonical)",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)

    generate_parser = commands.add_parser(
        "generate", help="create a blank 64-recipe observation template"
    )
    _add_output_options(generate_parser)

    validate_parser = commands.add_parser(
        "validate", help="validate a filled template and derive qualification"
    )
    validate_parser.add_argument("input", type=Path)
    _add_output_options(validate_parser)

    summary_parser = commands.add_parser(
        "summary", help="summarize collection progress and qualification blockers"
    )
    summary_parser.add_argument("input", type=Path)
    _add_output_options(summary_parser)
    return parser


def _json_text(value: object, *, pretty: bool) -> str:
    if not pretty:
        return canonical_json(value).decode("utf-8") + "\n"
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )


def _emit(value: object, *, output: Path | None, force: bool, pretty: bool) -> None:
    rendered = _json_text(value, pretty=pretty)
    if output is None:
        sys.stdout.buffer.write(rendered.encode("utf-8"))
        return
    if output.exists() and not force:
        raise HueObservationError(f"refusing to overwrite {output}")
    if not output.parent.is_dir():
        raise HueObservationError(f"output parent is not a directory: {output.parent}")
    try:
        output.write_text(rendered, encoding="utf-8", newline="\n")
    except OSError as error:
        raise HueObservationError(f"cannot write output: {error}") from error


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "generate":
            value = generate()
        elif args.command == "validate":
            value = validate(args.input)
        else:
            value = summary(args.input)
        _emit(value, output=args.output, force=args.force, pretty=args.pretty)
    except HueObservationError as error:
        failure = {
            "schema_version": 1,
            "kind": "mf1750-target-hue-lightness-observation-error-v1",
            "valid": False,
            "offline_only": True,
            "hardware_accessed_by_tool": False,
            "error": str(error),
        }
        sys.stderr.buffer.write(_json_text(failure, pretty=False).encode("utf-8"))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
