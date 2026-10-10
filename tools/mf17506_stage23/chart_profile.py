"""Create a layout-only 24-patch template or validate an exact chart profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from host.static_photo.chart_spec import (
    ChartPatch,
    ChartSpec,
    ChartSpecError,
    ReferenceGrade,
    load_chart_spec,
)
from host.static_photo.common import canonical_json_bytes


def _template(args: argparse.Namespace) -> dict[str, object]:
    output = Path(args.output)
    if output.exists():
        raise ChartSpecError("output file already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    patches = tuple(
        ChartPatch(f"P{row * 6 + column + 1:02d}", row, column, None)
        for row in range(4)
        for column in range(6)
    )
    spec = ChartSpec(
        args.chart_id,
        args.brand,
        args.model,
        4,
        6,
        ReferenceGrade.LAYOUT_ONLY,
        "layout template only; reference values not supplied",
        None,
        "D65",
        "2deg",
        0.22,
        patches,
    )
    payload = canonical_json_bytes(spec.mapping()) + b"\n"
    output.write_bytes(payload)
    return {
        "file": str(output.resolve()),
        "bytes": len(payload),
        "chart_id": spec.chart_id,
        "reference_grade": spec.reference_grade.value,
        "device_io_performed": False,
    }


def _validate(args: argparse.Namespace) -> dict[str, object]:
    spec = load_chart_spec(args.spec)
    return {
        "file": str(Path(args.spec).resolve()),
        "chart_id": spec.chart_id,
        "brand": spec.brand,
        "model": spec.model,
        "reference_grade": spec.reference_grade.value,
        "has_reference_values": spec.has_reference_values,
        "patch_count": len(spec.patches),
        "canonical_sha256": spec.mapping()["integrity"]["canonical_sha256"],
        "device_io_performed": False,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    template = subparsers.add_parser("template", allow_abbrev=False)
    template.add_argument("--chart-id", required=True)
    template.add_argument("--brand", required=True)
    template.add_argument("--model", required=True)
    template.add_argument("--output", type=Path, required=True)
    validate = subparsers.add_parser("validate", allow_abbrev=False)
    validate.add_argument("--spec", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = _template(args) if args.command == "template" else _validate(args)
    except ChartSpecError as error:
        print(f"chart profile error: {error}")
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
