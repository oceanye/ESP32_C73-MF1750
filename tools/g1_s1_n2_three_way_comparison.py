#!/usr/bin/env python3
"""Build the deterministic Q1/Q3/Q4 centre-crop comparison frame.

This module is offline-only.  It deeply validates the three frozen N2 photo
candidate bundles, copies the same 336x600 source-coordinate crop from each
frame at 1:1 pixel scale, and separates the three columns with two 8-pixel
white rules.  It never performs device I/O and does not create a visible
refresh authorization or claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.color_pipeline import encode_rgb_png, reference_palette  # noqa: E402
from host.epd_frame import (  # noqa: E402
    HEIGHT,
    WIDTH,
    fnv1a,
    pack_pixels,
    pixel_counts,
    unpack_pixels,
    validate_frame,
)
from tools.g1_s1_panel_candidate import (  # noqa: E402
    validate_candidate_directory,
)


SCHEMA_VERSION = 1
MANIFEST_KIND = "mf1750-g1-s1-n2-q134-three-way-comparison-offline-bundle"
ARTIFACT_ID = "G1S1_N2_Q134_CENTER_THREE_WAY_20260809_V1"
MANIFEST_HASH_SCOPE = (
    "entire manifest excluding manifest_integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
OUTPUT_FILES = frozenset({"frame.bin", "final.png", "manifest.json"})

CROP_X = 344
CROP_Y = 0
CROP_WIDTH = 336
CROP_HEIGHT = HEIGHT
SEPARATOR_WIDTH = 8
SEPARATOR_CODE = 1


class ThreeWayComparisonError(RuntimeError):
    """The frozen comparison bundle could not be generated or validated."""


SOURCE_SPECS = (
    {
        "position": "left",
        "cell_id": "Q1",
        "algorithm": "atkinson",
        "directory": "G1S1_N2P_WINDMILL_ATKINSON_OFFLINE_20260807_V2",
        "frame_sha256": "7aa33f337903b93ba094265e212909f5986ab48eebb0a2dd352b7571a6ea7c96",
        "preview_sha256": "5960506add9e75beb622a2c84d56e34966514d7b01c051ced00e6f83191a3551",
        "manifest_file_sha256": "7d4ccd683f0be4d0c32d4692bc2d9beab88526c36a7624d2c3a1d0865e9eb6ff",
        "destination_x": 0,
    },
    {
        "position": "middle",
        "cell_id": "Q3",
        "algorithm": "multicolor-dbs-262k",
        "directory": "G1S1_N2P_WINDMILL_MULTICOLOR_DBS_262K_OFFLINE_20260807_V2",
        "frame_sha256": "0a9e2da80ced18ad7f7345906a78c53e7b720468c254365a5fc44502576b1a77",
        "preview_sha256": "2be45e01cef4ad09aacad187868d954bbd2617666b3a3fc89f57c6aa8b3ccbab",
        "manifest_file_sha256": "2a429eee18396fbd7a36b27be049fe18686914d1496b7ade4a64c08599548f0a",
        "destination_x": CROP_WIDTH + SEPARATOR_WIDTH,
    },
    {
        "position": "right",
        "cell_id": "Q4",
        "algorithm": "overlap-aware-dbs-262k",
        "directory": "G1S1_N2P_WINDMILL_OVERLAP_DBS_262K_OFFLINE_20260807_V2",
        "frame_sha256": "4183b84b40578589938531076eb92845aa53f533c6e29ee5a54986903c7e8f86",
        "preview_sha256": "c76a3969b1935a5f10b9a48b8ba47b5642454af1124847e9eb43364b407f1ff5",
        "manifest_file_sha256": "9b4ce4a73457c34d09e9fddfcc0272e3c0f0d472cd4d46a0faa712ba4dfb9505",
        "destination_x": 2 * (CROP_WIDTH + SEPARATOR_WIDTH),
    },
)


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ThreeWayComparisonError(
            f"value cannot be represented as canonical JSON: {error}"
        ) from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _source_dir(spec: Mapping[str, Any]) -> Path:
    return REPO_ROOT / ".test-output" / "hardware" / str(spec["directory"])


def _read_frozen_sources() -> list[tuple[Mapping[str, Any], bytes]]:
    snapshots: list[tuple[Mapping[str, Any], bytes]] = []
    for spec in SOURCE_SPECS:
        directory = _source_dir(spec)
        try:
            manifest = validate_candidate_directory(directory)
            frame = bytes(validate_frame((directory / "frame.bin").read_bytes()))
            preview = (directory / "final.png").read_bytes()
            manifest_bytes = (directory / "manifest.json").read_bytes()
        except (OSError, ValueError, RuntimeError) as error:
            raise ThreeWayComparisonError(
                f"{spec['cell_id']} frozen candidate validation failed: {error}"
            ) from error
        expected = {
            "frame_sha256": _sha256(frame),
            "preview_sha256": _sha256(preview),
            "manifest_file_sha256": _sha256(manifest_bytes),
        }
        for field, observed in expected.items():
            if observed != spec[field]:
                raise ThreeWayComparisonError(
                    f"{spec['cell_id']} {field} changed: {observed}"
                )
        integrity = manifest.get("manifest_integrity")
        if not isinstance(integrity, Mapping) or not isinstance(
            integrity.get("canonical_sha256"), str
        ):
            raise ThreeWayComparisonError(
                f"{spec['cell_id']} candidate manifest integrity is missing"
            )
        snapshots.append((manifest, frame))
    return snapshots


def _compose_codes(frames: Sequence[bytes]) -> bytes:
    if len(frames) != len(SOURCE_SPECS):
        raise ThreeWayComparisonError("exactly three frozen frames are required")
    source_codes = [unpack_pixels(frame, WIDTH, HEIGHT) for frame in frames]
    output = bytearray([SEPARATOR_CODE]) * (WIDTH * HEIGHT)
    for spec, codes in zip(SOURCE_SPECS, source_codes):
        destination_x = int(spec["destination_x"])
        for y in range(CROP_HEIGHT):
            source_start = (CROP_Y + y) * WIDTH + CROP_X
            destination_start = y * WIDTH + destination_x
            output[destination_start : destination_start + CROP_WIDTH] = codes[
                source_start : source_start + CROP_WIDTH
            ]
    return bytes(output)


def _render_preview(codes: bytes) -> bytes:
    palette = reference_palette()
    rgb_by_code = {entry.code: bytes(entry.preview_rgb) for entry in palette.entries}
    try:
        rgb = b"".join(rgb_by_code[code] for code in codes)
    except KeyError as error:
        raise ThreeWayComparisonError(
            f"comparison uses unsupported physical color code {error.args[0]}"
        ) from error
    return encode_rgb_png(WIDTH, HEIGHT, rgb)


def compile_bundle() -> dict[str, bytes]:
    snapshots = _read_frozen_sources()
    frames = [frame for _, frame in snapshots]
    codes = _compose_codes(frames)
    frame = pack_pixels(codes, WIDTH, HEIGHT)
    preview = _render_preview(codes)
    palette = reference_palette()
    counts = pixel_counts(frame, WIDTH, HEIGHT)
    sources = []
    for spec, (source_manifest, source_frame) in zip(SOURCE_SPECS, snapshots):
        source_integrity = source_manifest["manifest_integrity"]
        sources.append(
            {
                "position": spec["position"],
                "cell_id": spec["cell_id"],
                "algorithm": spec["algorithm"],
                "workspace_relative_directory": (
                    f".test-output/hardware/{spec['directory']}"
                ),
                "source_manifest_file_sha256": spec["manifest_file_sha256"],
                "source_manifest_canonical_sha256": source_integrity[
                    "canonical_sha256"
                ],
                "source_frame_sha256": _sha256(source_frame),
                "source_preview_sha256": spec["preview_sha256"],
                "source_crop": {
                    "x": CROP_X,
                    "y": CROP_Y,
                    "width": CROP_WIDTH,
                    "height": CROP_HEIGHT,
                },
                "destination": {
                    "x": spec["destination_x"],
                    "y": 0,
                    "width": CROP_WIDTH,
                    "height": CROP_HEIGHT,
                },
                "pixel_scale": "1:1",
            }
        )
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "artifact_id": ARTIFACT_ID,
        "purpose": (
            "supplemental human side-by-side comparison of the three visually "
            "acceptable N2 candidates"
        ),
        "scope": {
            "part_of_original_n2_eight_actions": False,
            "changes_original_n2_scores_or_winner_gate": False,
            "hardware_tested": False,
            "device_io_performed": False,
            "visible_refresh_authorized": False,
        },
        "geometry": {
            "width": WIDTH,
            "height": HEIGHT,
            "crop_coordinate_space": "same-original-1024x600-frame",
            "source_crop": {
                "x": CROP_X,
                "y": CROP_Y,
                "width": CROP_WIDTH,
                "height": CROP_HEIGHT,
            },
            "separators": [
                {"x": CROP_WIDTH, "width": SEPARATOR_WIDTH},
                {
                    "x": 2 * CROP_WIDTH + SEPARATOR_WIDTH,
                    "width": SEPARATOR_WIDTH,
                },
            ],
            "separator_color_code": SEPARATOR_CODE,
            "separator_color_name": "white",
        },
        "legend": ["left=Q1 Atkinson", "middle=Q3 multicolor DBS", "right=Q4 overlap-aware DBS"],
        "sources": sources,
        "palette": {
            "palette_id": palette.palette_id,
            "canonical_sha256": palette.canonical_sha256,
            "calibrated": palette.calibrated,
        },
        "frame": {
            "file": "frame.bin",
            "encoding": "canonical-row-major-two-4bit-codes-per-byte",
            "bytes": len(frame),
            "sha256": _sha256(frame),
            "fnv1a": f"0x{fnv1a(frame):08X}",
            "codes_sha256": _sha256(codes),
            "physical_code_counts": {
                str(code): counts[code] for code in (0, 1, 2, 3, 5, 6)
            },
        },
        "preview": {
            "file": "final.png",
            "bytes": len(preview),
            "sha256": _sha256(preview),
            "rendering": "exact-reference-palette-rendering-of-frame.bin",
        },
        "manifest_integrity": None,
    }
    integrity_payload = dict(manifest)
    integrity_payload.pop("manifest_integrity")
    manifest["manifest_integrity"] = {
        "canonical_sha256": _sha256(_canonical_json(integrity_payload)),
        "canonical_sha256_scope": MANIFEST_HASH_SCOPE,
    }
    return {
        "frame.bin": frame,
        "final.png": preview,
        "manifest.json": _canonical_json(manifest),
    }


def write_bundle(output_dir: Path) -> dict[str, Any]:
    payloads = compile_bundle()
    try:
        output_dir.mkdir(parents=True, exist_ok=False)
        for name, payload in payloads.items():
            (output_dir / name).write_bytes(payload)
    except OSError as error:
        raise ThreeWayComparisonError(f"could not write comparison bundle: {error}") from error
    return validate_bundle(output_dir)


def validate_bundle(output_dir: Path) -> dict[str, Any]:
    expected = compile_bundle()
    try:
        actual_names = {item.name for item in output_dir.iterdir() if item.is_file()}
    except OSError as error:
        raise ThreeWayComparisonError(f"could not inspect comparison bundle: {error}") from error
    if actual_names != OUTPUT_FILES:
        raise ThreeWayComparisonError(
            f"comparison bundle files differ: expected {sorted(OUTPUT_FILES)}, got {sorted(actual_names)}"
        )
    for name, expected_payload in expected.items():
        try:
            observed = (output_dir / name).read_bytes()
        except OSError as error:
            raise ThreeWayComparisonError(f"could not read {name}: {error}") from error
        if observed != expected_payload:
            raise ThreeWayComparisonError(f"{name} differs from deep regeneration")
    manifest = json.loads(expected["manifest.json"].decode("utf-8"))
    return {
        "valid": True,
        "artifact_id": ARTIFACT_ID,
        "output_dir": str(output_dir),
        "frame_sha256": manifest["frame"]["sha256"],
        "frame_fnv1a": manifest["frame"]["fnv1a"],
        "preview_sha256": manifest["preview"]["sha256"],
        "manifest_file_sha256": _sha256(expected["manifest.json"]),
        "device_io_performed": False,
        "visible_refresh_authorized": False,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "validate"):
        subparser = subparsers.add_parser(command, allow_abbrev=False)
        subparser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        result = (
            write_bundle(args.output_dir)
            if args.command == "build"
            else validate_bundle(args.output_dir)
        )
    except ThreeWayComparisonError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
