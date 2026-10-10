#!/usr/bin/env python3
"""Generate and validate the exact technical-only U07T pseudocolour preview."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.epd_frame import ControllerMapping, controller_stream, fnv1a  # noqa: E402
from host.extended_color.offline import (  # noqa: E402
    generate_unknown_probe_frame,
    validate_unknown_probe_frame,
)
from tools import mf1750_ec5_u07t_identity as identity  # noqa: E402
from tools.mf1750_ec5_sixstate_nodither import (  # noqa: E402
    _decode_png,
    _encode_png,
    _preview_rgb,
)


SCHEMA_VERSION = 1
KIND = "mf1750-ec5-u07t-technical-preview"
RAW_FILE = "u07t-pilot.raw"
PNG_FILE = "u07t-pilot.preview.png"
MANIFEST_FILE = "u07t-pilot.preview.json"


class U07TPreviewError(ValueError):
    """The fixed U07T preview or one of its assets differed."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256(payload: bytes | Mapping[str, Any]) -> str:
    data = payload if isinstance(payload, bytes) else canonical_json_bytes(payload)
    return hashlib.sha256(data).hexdigest()


def generate_frame() -> bytes:
    frame = generate_unknown_probe_frame(7)
    validate_unknown_probe_frame(frame, 7)
    if sha256(frame) != identity.FRAME_SHA256 or fnv1a(frame) != identity.FRAME_FNV1A:
        raise U07TPreviewError("U07T frame identity drifted")
    return frame


def build_bundle() -> tuple[dict[str, Any], dict[str, bytes]]:
    frame = generate_frame()
    streams = tuple(
        controller_stream(
            frame,
            ControllerMapping(source_half),
            allowed_colors=tuple(range(8)),
        )
        for source_half in (0, 1)
    )
    if any(
        sha256(stream) != identity.DTM_SHA256
        or fnv1a(stream) != identity.DTM_FNV1A
        for stream in streams
    ):
        raise U07TPreviewError("U07T controller stream identity drifted")
    png = _encode_png(_preview_rgb(frame, 7))
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "classification": "TECHNICAL_DESCRIPTIVE_NOT_QUALIFIED",
        "candidate_id": "U07T",
        "candidate_code": 7,
        "action_id": identity.FROZEN_ACTION_ID,
        "layout_id": identity.LAYOUT_ID,
        "raw": {
            "file": RAW_FILE,
            "bytes": len(frame),
            "sha256": sha256(frame),
            "fnv1a": fnv1a(frame),
        },
        "controller_streams": {
            name: {
                "bytes": len(stream),
                "sha256": sha256(stream),
                "fnv1a": fnv1a(stream),
            }
            for name, stream in zip(("CS1", "CS2"), streams)
        },
        "preview": {
            "file": PNG_FILE,
            "bytes": len(png),
            "sha256": sha256(png),
            "semantic": (
                "candidate-pseudocolour-marker-not-physical-colour-prediction"
            ),
        },
        "geometry": {
            "width": 1024,
            "height": 600,
            "background_code": 1,
            "roi_cs1": {"x0": 224, "x1": 288, "y0": 268, "y1": 332},
            "roi_cs2": {"x0": 736, "x1": 800, "y0": 268, "y1": 332},
            "candidate_pixels": 8192,
            "dithering_present": False,
            "spatial_mixing_present": False,
        },
        "hardware_execution_authorized": False,
        "formal_u07_qualification_inferred": False,
    }
    manifest = {
        **unsigned,
        "integrity": {"canonical_sha256": sha256(unsigned)},
    }
    return manifest, {
        RAW_FILE: frame,
        PNG_FILE: png,
        MANIFEST_FILE: canonical_json_bytes(manifest),
    }


def generate(output: Path) -> Path:
    output = Path(output)
    if output.is_symlink() or not output.is_dir():
        raise U07TPreviewError("output must be an existing local directory")
    destination = output.resolve(strict=True) / "U07T"
    try:
        destination.mkdir(exist_ok=False)
        _manifest, assets = build_bundle()
        for name, payload in assets.items():
            with (destination / name).open("xb") as stream:
                stream.write(payload)
    except OSError as error:
        raise U07TPreviewError(f"could not publish U07T preview: {error}") from error
    return destination / MANIFEST_FILE


def validate(manifest_file: Path) -> dict[str, Any]:
    manifest_file = Path(manifest_file)
    try:
        if manifest_file.is_symlink() or not manifest_file.is_file():
            raise U07TPreviewError("manifest must be a regular file")
        root = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise U07TPreviewError(f"could not read U07T manifest: {error}") from error
    expected, assets = build_bundle()
    if root != expected or manifest_file.name != MANIFEST_FILE:
        raise U07TPreviewError("U07T preview manifest differs")
    for name, payload in assets.items():
        path = manifest_file.parent / name
        if path.is_symlink() or not path.is_file() or path.read_bytes() != payload:
            raise U07TPreviewError(f"U07T preview asset {name} differs")
    if _decode_png(assets[PNG_FILE]) != _preview_rgb(assets[RAW_FILE], 7):
        raise U07TPreviewError("U07T PNG pixels differ from exact raw frame")
    return {
        "valid": True,
        "candidate_id": "U07T",
        "action_id": identity.FROZEN_ACTION_ID,
        "classification": "TECHNICAL_DESCRIPTIVE_NOT_QUALIFIED",
        "frame_sha256": identity.FRAME_SHA256,
        "preview_sha256": expected["preview"]["sha256"],
        "hardware_execution_authorized": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("generate", allow_abbrev=False)
    build.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("validate", allow_abbrev=False)
    check.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "generate":
            manifest = generate(args.output)
            report = validate(manifest)
            report["manifest"] = str(manifest)
        else:
            report = validate(args.manifest)
    except U07TPreviewError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
