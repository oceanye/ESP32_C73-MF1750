#!/usr/bin/env python3
"""Generate exact pseudocolour previews for the fixed EC5 Stage-A pilots.

The candidate pseudocolour only marks which pixels carry 0x4 or 0x7; it is
not a prediction of the physical colour produced by the panel.
"""

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

from host.epd_frame import controller_stream, fnv1a  # noqa: E402
from host.extended_color.offline import (  # noqa: E402
    DEFAULT_CONTROLLER_MAPPINGS,
    generate_unknown_probe_frame,
    validate_unknown_probe_frame,
)
from tools.mf1750_ec5_sixstate_nodither import (  # noqa: E402
    _decode_png,
    _encode_png,
    _preview_rgb,
)


KIND = "mf1750-ec5-stage-a-pilot-preview"
LAYOUT_ID = "EC5_MIRROR64_CENTER_V1"
CANDIDATES = (4, 7)
FROZEN = {
    4: {
        "frame_sha256": "5a2e797ea058797f01fefe6d073bbb28f39bbbf71c078c1af72dbb8fc3e5877e",
        "frame_fnv1a": 0x68533DC5,
        "dtm_sha256": "a8056cdd450f70709ec75a0a04000dfbfb1f06000ae596420902156bec7bab00",
        "dtm_fnv1a": 0x15B7EDC5,
    },
    7: {
        "frame_sha256": "d9d43888c68b483776bb43a53cc1084b8549d00d9ff70ef2f1227fafe0ac7b3e",
        "frame_fnv1a": 0xA1C5ADC5,
        "dtm_sha256": "2e21712aeca3eeec9e24d9312f4a601c7b0212792f7d3419a150442cc80ea6ac",
        "dtm_fnv1a": 0x97F125C5,
    },
}


class PilotPreviewError(ValueError):
    """The exact Stage-A preview bundle failed closed."""


def _candidate(value: int) -> int:
    if type(value) is not int or value not in CANDIDATES:
        raise PilotPreviewError("candidate must be 4 or 7")
    return value


def _candidate_arg(value: str) -> int:
    try:
        return _candidate(int(value, 0))
    except (ValueError, PilotPreviewError) as error:
        raise argparse.ArgumentTypeError("candidate must be 4, 7, 0x4, or 0x7") from error


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def build_bundle(candidate: int) -> tuple[dict[str, Any], dict[str, bytes]]:
    candidate = _candidate(candidate)
    frame = generate_unknown_probe_frame(candidate)
    validate_unknown_probe_frame(frame, candidate)
    streams = tuple(
        controller_stream(frame, mapping, allowed_colors=(0, 1, 2, 3, 4, 5, 6, 7))
        for mapping in DEFAULT_CONTROLLER_MAPPINGS
    )
    frozen = FROZEN[candidate]
    if (
        _sha(frame) != frozen["frame_sha256"]
        or fnv1a(frame) != frozen["frame_fnv1a"]
        or any(_sha(stream) != frozen["dtm_sha256"] for stream in streams)
        or any(fnv1a(stream) != frozen["dtm_fnv1a"] for stream in streams)
    ):
        raise PilotPreviewError("Stage-A frame or DTM identity drifted")
    png = _encode_png(_preview_rgb(frame, candidate))
    tag = f"U0{candidate}"
    raw_name = f"u0{candidate}_pilot.raw"
    png_name = f"u0{candidate}_pilot.preview.png"
    manifest_name = f"u0{candidate}_pilot.preview.json"
    unsigned = {
        "schema_version": 1,
        "kind": KIND,
        "layout_id": LAYOUT_ID,
        "candidate_id": tag,
        "candidate_code": candidate,
        "raw": {
            "file": raw_name,
            "bytes": len(frame),
            "sha256": _sha(frame),
            "fnv1a": fnv1a(frame),
        },
        "controller_streams": {
            name: {
                "bytes": len(stream),
                "sha256": _sha(stream),
                "fnv1a": fnv1a(stream),
            }
            for name, stream in zip(("CS1", "CS2"), streams)
        },
        "preview": {
            "file": png_name,
            "bytes": len(png),
            "sha256": _sha(png),
            "semantic": "candidate-pseudocolour-marker-not-physical-colour-prediction",
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
    }
    manifest = {**unsigned, "integrity": {"sha256": _sha(_canonical(unsigned))}}
    return manifest, {
        raw_name: frame,
        png_name: png,
        manifest_name: _canonical(manifest),
    }


def generate(output_root: Path, candidate: int) -> Path:
    candidate = _candidate(candidate)
    if output_root.is_symlink() or not output_root.is_dir():
        raise PilotPreviewError("output root must be an existing local directory")
    destination = output_root.resolve(strict=True) / f"U0{candidate}"
    try:
        destination.mkdir(exist_ok=False)
        _, assets = build_bundle(candidate)
        for filename, payload in assets.items():
            with (destination / filename).open("xb") as stream:
                stream.write(payload)
    except OSError as error:
        raise PilotPreviewError(f"could not publish pilot preview: {error}") from error
    return destination / f"u0{candidate}_pilot.preview.json"


def validate(manifest_path: Path) -> dict[str, Any]:
    try:
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise PilotPreviewError("manifest must be a regular file")
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PilotPreviewError(f"could not read manifest: {error}") from error
    if not isinstance(value, Mapping):
        raise PilotPreviewError("manifest root must be an object")
    candidate = _candidate(value.get("candidate_code"))
    expected, assets = build_bundle(candidate)
    if value != expected or manifest_path.name != f"u0{candidate}_pilot.preview.json":
        raise PilotPreviewError("manifest differs from frozen preview contract")
    for filename, payload in assets.items():
        path = manifest_path.parent / filename
        if path.is_symlink() or not path.is_file() or path.read_bytes() != payload:
            raise PilotPreviewError(f"asset {filename} differs")
    png = assets[f"u0{candidate}_pilot.preview.png"]
    raw = assets[f"u0{candidate}_pilot.raw"]
    if _decode_png(png) != _preview_rgb(raw, candidate):
        raise PilotPreviewError("PNG pixels differ from the exact raw frame")
    return {
        "valid": True,
        "candidate_id": f"U0{candidate}",
        "frame_sha256": expected["raw"]["sha256"],
        "preview_sha256": expected["preview"]["sha256"],
        "hardware_execution_authorized": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate_parser = subparsers.add_parser("generate", allow_abbrev=False)
    generate_parser.add_argument("--candidate", type=_candidate_arg, required=True)
    generate_parser.add_argument("--output-root", type=Path, required=True)
    validate_parser = subparsers.add_parser("validate", allow_abbrev=False)
    validate_parser.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "generate":
            manifest = generate(args.output_root, args.candidate)
            report = validate(manifest)
            report["manifest"] = str(manifest)
        else:
            report = validate(args.manifest)
    except PilotPreviewError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
