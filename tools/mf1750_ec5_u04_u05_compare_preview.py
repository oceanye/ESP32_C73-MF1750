#!/usr/bin/env python3
"""Generate and deeply validate the fixed U04-vs-U05 comparison preview."""

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

from tools import mf1750_ec5_u04_u05_compare_identity as identity  # noqa: E402
from tools.mf1750_ec5_sixstate_nodither import (  # noqa: E402
    _decode_png,
    _encode_png,
)


SCHEMA_VERSION = 1
KIND = "mf1750-ec5-u04-u05-compare-preview"
RAW_FILE = "u04-u05-compare.raw"
PNG_FILE = "u04-u05-compare.preview.png"
MANIFEST_FILE = "u04-u05-compare.preview.json"
PSEUDOCOLOUR = {
    1: (255, 255, 255),
    4: (0, 190, 220),
    5: (0, 70, 210),
}


class ComparePreviewError(ValueError):
    """The frozen comparison preview failed closed."""


def _canonical(value: Any) -> bytes:
    return identity.canonical_json_bytes(value)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def preview_rgb(frame: bytes) -> bytes:
    identity.validate_exact_frame(frame)
    rgb = bytearray(1024 * 600 * 3)
    output = 0
    for packed in frame:
        for code in (packed >> 4, packed & 0x0F):
            try:
                colour = PSEUDOCOLOUR[code]
            except KeyError as error:
                raise ComparePreviewError(
                    f"preview encountered unsupported code 0x{code:x}"
                ) from error
            rgb[output : output + 3] = bytes(colour)
            output += 3
    return bytes(rgb)


def build_bundle() -> tuple[dict[str, Any], dict[str, bytes]]:
    frame = identity.generate_frame()
    generated = identity.generated_identity()
    png = _encode_png(preview_rgb(frame))
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "identity_revision": identity.IDENTITY_REVISION,
        "layout_id": identity.LAYOUT_ID,
        "action_id": identity.action_id(),
        "raw": {
            "file": RAW_FILE,
            "bytes": len(frame),
            "sha256": generated["frame_sha256"],
            "fnv1a": generated["frame_fnv1a"],
        },
        "controller_streams": {
            "CS1": {
                "bytes": generated["cs1_dtm_bytes"],
                "sha256": generated["cs1_dtm_sha256"],
                "fnv1a": generated["cs1_dtm_fnv1a"],
            },
            "CS2": {
                "bytes": generated["cs2_dtm_bytes"],
                "sha256": generated["cs2_dtm_sha256"],
                "fnv1a": generated["cs2_dtm_fnv1a"],
            },
        },
        "preview": {
            "file": PNG_FILE,
            "bytes": len(png),
            "sha256": _sha(png),
            "semantic": (
                "code-location-pseudocolour-only-not-physical-colour-prediction"
            ),
            "legend": {
                "white_background": list(PSEUDOCOLOUR[1]),
                "U04_marker": list(PSEUDOCOLOUR[4]),
                "U05_known_blue_marker": list(PSEUDOCOLOUR[5]),
            },
        },
        "geometry": {
            "width": 1024,
            "height": 600,
            "background_code": 1,
            "rois": [dict(roi) for roi in identity.ROIS],
            "histogram": generated["histogram"],
            "dithering_present": False,
            "spatial_mixing_present": False,
        },
        "hardware_execution_authorized": False,
    }
    manifest = {
        **unsigned,
        "integrity": {"canonical_sha256": _sha(_canonical(unsigned))},
    }
    return manifest, {
        RAW_FILE: frame,
        PNG_FILE: png,
        MANIFEST_FILE: _canonical(manifest),
    }


def generate(output_root: Path) -> Path:
    output_root = Path(output_root)
    if output_root.is_symlink() or not output_root.is_dir():
        raise ComparePreviewError("output root must be an existing local directory")
    destination = output_root.resolve(strict=True) / "U04_U05_COMPARE"
    try:
        destination.mkdir(exist_ok=False)
        _, assets = build_bundle()
        for filename, payload in assets.items():
            with (destination / filename).open("xb") as stream:
                stream.write(payload)
    except OSError as error:
        raise ComparePreviewError(f"could not publish preview: {error}") from error
    return destination / MANIFEST_FILE


def validate(manifest_path: Path) -> dict[str, Any]:
    path = Path(manifest_path)
    try:
        if path.is_symlink() or not path.is_file() or path.name != MANIFEST_FILE:
            raise ComparePreviewError("manifest path is not the frozen regular file")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ComparePreviewError(f"could not read preview manifest: {error}") from error
    if not isinstance(value, Mapping):
        raise ComparePreviewError("preview manifest root must be an object")
    expected, assets = build_bundle()
    if value != expected:
        raise ComparePreviewError("preview manifest differs from frozen contract")
    for filename, payload in assets.items():
        asset = path.parent / filename
        if asset.is_symlink() or not asset.is_file() or asset.read_bytes() != payload:
            raise ComparePreviewError(f"preview asset {filename} differs")
    if _decode_png(assets[PNG_FILE]) != preview_rgb(assets[RAW_FILE]):
        raise ComparePreviewError("preview PNG pixels differ from raw fixture")
    return {
        "valid": True,
        "action_id": identity.action_id(),
        "frame_sha256": identity.FRAME_SHA256,
        "preview_sha256": expected["preview"]["sha256"],
        "hardware_execution_authorized": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("generate", allow_abbrev=False)
    build.add_argument("--output-root", type=Path, required=True)
    check = sub.add_parser("validate", allow_abbrev=False)
    check.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "generate":
            manifest = generate(args.output_root)
            report = validate(manifest)
            report["manifest"] = str(manifest)
        else:
            report = validate(args.manifest)
    except ComparePreviewError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

