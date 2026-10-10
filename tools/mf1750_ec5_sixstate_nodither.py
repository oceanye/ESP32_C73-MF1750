#!/usr/bin/env python3
"""Build and deeply validate offline EC5 six-initial-state assets.

The generated frames are data-only fixtures.  This module has no network,
serial, GPIO, device, firmware-upload, or display-refresh path.  Each bundle
contains exactly one compile-time candidate (0x4 or 0x7) in its own directory.
The PNG files are synthetic code visualizations, not predictions of the
physical colour that an undocumented code may produce.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any, Mapping, Optional, Sequence
import zlib


SCHEMA_VERSION = 1
KIND = "mf1750-ec5-sixstate-nodither-assets"
LAYOUT_ID = "EC5_SIXSTATE_MIRROR24_NODITHER_V1"

WIDTH = 1024
HEIGHT = 600
ROW_BYTES = WIDTH // 2
FRAME_BYTES = ROW_BYTES * HEIGHT
CONTROLLER_WIDTH = WIDTH // 2
CONTROLLER_ROW_BYTES = CONTROLLER_WIDTH // 2
CONTROLLER_FRAME_BYTES = CONTROLLER_ROW_BYTES * HEIGHT

WHITE_CODE = 0x1
CANDIDATES = (0x4, 0x7)
ROI_SIDE = 24
ROI_PIXELS = ROI_SIDE * ROI_SIDE
ROI_COUNT = 12
CANDIDATE_PIXELS = ROI_PIXELS * ROI_COUNT
PILOT_PIXEL_LIMIT = 8192

# Each 24-pixel rectangle is centred at the centre of its 512-pixel logical
# controller half.  Thus CS2 is both a full-frame mirror of CS1 and has the
# same controller-local coordinates.  Half-open coordinates are used.
LEFT_X0 = 244
RIGHT_X0 = 756
Y_STARTS = (48, 144, 240, 336, 432, 528)
INITIAL_STATES = (
    ("white", 0x1),
    ("black", 0x0),
    ("red", 0x3),
    ("yellow", 0x2),
    ("blue", 0x5),
    ("green", 0x6),
)

MAPPINGS = {
    "CS1": {
        "source_half": 0,
        "flip_x": False,
        "flip_y": False,
        "nibble_swap": False,
    },
    "CS2": {
        "source_half": 1,
        "flip_x": False,
        "flip_y": False,
        "nibble_swap": False,
    },
}

# Raw-frame and transmitted-controller identities are deliberately literal.
# A layout, packing, colour-order, or mapping change must not silently mint a
# new experiment under the existing layout ID.
FROZEN_IDENTITIES: Mapping[int, Mapping[str, Mapping[str, tuple[str, int]]]] = {
    0x4: {
        "primer": {
            "full": (
                "94ee82ae66fe8372e8c1d977a158dc60d55c36da86fc44f8b2a9a01c6d47ab0e",
                0xE4F04785,
            ),
            "CS1": (
                "f5bb17a5726f851da2bf322ffea8f0ea791f70788184ada4261b89aa43dc39af",
                0x58214425,
            ),
            "CS2": (
                "f5bb17a5726f851da2bf322ffea8f0ea791f70788184ada4261b89aa43dc39af",
                0x58214425,
            ),
        },
        "target": {
            "full": (
                "81b0ed1b715551ddb2546d4f123c5c3d479bc8802ff9d2570e38d9b57b4645e6",
                0x263BD845,
            ),
            "CS1": (
                "c4efd83606b72c49b7c0d67865e4df98ef31e5d40f071299558e10c5a212dd0f",
                0xEF6ED905,
            ),
            "CS2": (
                "c4efd83606b72c49b7c0d67865e4df98ef31e5d40f071299558e10c5a212dd0f",
                0xEF6ED905,
            ),
        },
    },
    0x7: {
        "primer": {
            "full": (
                "94ee82ae66fe8372e8c1d977a158dc60d55c36da86fc44f8b2a9a01c6d47ab0e",
                0xE4F04785,
            ),
            "CS1": (
                "f5bb17a5726f851da2bf322ffea8f0ea791f70788184ada4261b89aa43dc39af",
                0x58214425,
            ),
            "CS2": (
                "f5bb17a5726f851da2bf322ffea8f0ea791f70788184ada4261b89aa43dc39af",
                0x58214425,
            ),
        },
        "target": {
            "full": (
                "149ba0f5c3fd779d6870f655b53d726d6d1297e016331de4d394e411410e0e21",
                0xF93BD8C5,
            ),
            "CS1": (
                "139a0aa919d78a1aa572db49a7c90fe3a4f29476ab4d80ba3bb0f439f0191b3d",
                0xE4D43B45,
            ),
            "CS2": (
                "139a0aa919d78a1aa572db49a7c90fe3a4f29476ab4d80ba3bb0f439f0191b3d",
                0xE4D43B45,
            ),
        },
    },
}

FROZEN_HISTOGRAMS: Mapping[int, Mapping[str, tuple[int, ...]]] = {
    0x4: {
        "primer": (
            1152,
            608640,
            1152,
            1152,
            0,
            1152,
            1152,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ),
        "target": (
            0,
            607488,
            0,
            0,
            6912,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ),
    },
    0x7: {
        "primer": (
            1152,
            608640,
            1152,
            1152,
            0,
            1152,
            1152,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ),
        "target": (
            0,
            607488,
            0,
            0,
            0,
            0,
            0,
            6912,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ),
    },
}

KNOWN_RGB = {
    0x0: (0, 0, 0),
    0x1: (255, 255, 255),
    0x2: (255, 230, 0),
    0x3: (220, 0, 0),
    0x5: (0, 80, 210),
    0x6: (0, 150, 70),
}
UNKNOWN_PREVIEW_RGB = {0x4: (255, 0, 255), 0x7: (0, 220, 220)}

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_MANIFEST_BYTES = 512 * 1024
MAX_PNG_BYTES = 4 * 1024 * 1024


class SixStateAssetError(ValueError):
    """The frozen offline asset contract was not satisfied."""


def _candidate(value: object) -> int:
    if type(value) is not int or value not in CANDIDATES:
        raise SixStateAssetError("candidate must be the integer 4 or 7")
    return value


def _candidate_arg(value: str) -> int:
    try:
        parsed = int(value, 0)
        return _candidate(parsed)
    except (ValueError, SixStateAssetError) as error:
        raise argparse.ArgumentTypeError("candidate must be 4, 7, 0x4, or 0x7") from error


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fnv1a(data: bytes) -> int:
    value = 0x811C9DC5
    for byte in data:
        value ^= byte
        value = (value * 0x01000193) & 0xFFFFFFFF
    return value


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
        raise SixStateAssetError(f"value is not canonical JSON: {error}") from error


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SixStateAssetError(f"JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _read_regular(path: Path, *, label: str, maximum: int) -> bytes:
    if not isinstance(path, Path):
        raise SixStateAssetError(f"{label} path must be pathlib.Path")
    try:
        if path.is_symlink() or not path.is_file():
            raise SixStateAssetError(f"{label} must be a regular non-symlink file")
        size = path.stat().st_size
        if size > maximum:
            raise SixStateAssetError(f"{label} is larger than {maximum} bytes")
        data = path.read_bytes()
    except OSError as error:
        raise SixStateAssetError(f"could not read {label}: {error}") from error
    if len(data) != size:
        raise SixStateAssetError(f"{label} changed while it was being read")
    return data


def _write_new(path: Path, data: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(data)
    except FileExistsError as error:
        raise SixStateAssetError(f"refusing to overwrite {path.name}") from error
    except OSError as error:
        raise SixStateAssetError(f"could not write {path.name}: {error}") from error


def _set_pixel(frame: bytearray, x: int, y: int, code: int) -> None:
    offset = y * ROW_BYTES + x // 2
    if x & 1:
        frame[offset] = (frame[offset] & 0xF0) | code
    else:
        frame[offset] = (frame[offset] & 0x0F) | (code << 4)


def _pixel(frame: bytes, x: int, y: int) -> int:
    value = frame[y * ROW_BYTES + x // 2]
    return value & 0x0F if x & 1 else value >> 4


def frozen_rois(candidate: int) -> list[dict[str, Any]]:
    """Return the twelve frozen half-open ROI records for one candidate."""

    candidate = _candidate(candidate)
    result: list[dict[str, Any]] = []
    for pair_index, ((name, initial_code), y0) in enumerate(
        zip(INITIAL_STATES, Y_STARTS), start=1
    ):
        for controller, x0 in (("CS1", LEFT_X0), ("CS2", RIGHT_X0)):
            result.append(
                {
                    "roi_id": f"{name.upper()}-{controller}",
                    "pair_index": pair_index,
                    "controller": controller,
                    "initial_name": name,
                    "initial_code": initial_code,
                    "target_code": candidate,
                    "rect": {
                        "x0": x0,
                        "y0": y0,
                        "x1_exclusive": x0 + ROI_SIDE,
                        "y1_exclusive": y0 + ROI_SIDE,
                        "width": ROI_SIDE,
                        "height": ROI_SIDE,
                    },
                    "pixels": ROI_PIXELS,
                }
            )
    return result


def build_frames(candidate: int) -> tuple[bytes, bytes]:
    """Return deterministic ``(primer, target)`` packed 4bpp frames."""

    candidate = _candidate(candidate)
    primer = bytearray([0x11]) * FRAME_BYTES
    target = bytearray([0x11]) * FRAME_BYTES
    for roi in frozen_rois(candidate):
        rect = roi["rect"]
        for y in range(rect["y0"], rect["y1_exclusive"]):
            for x in range(rect["x0"], rect["x1_exclusive"]):
                _set_pixel(primer, x, y, roi["initial_code"])
                _set_pixel(target, x, y, candidate)
    return bytes(primer), bytes(target)


def _controller_stream(frame: bytes, source_half: int) -> bytes:
    if len(frame) != FRAME_BYTES:
        raise SixStateAssetError("packed frame length is not 307200 bytes")
    if source_half not in (0, 1):
        raise SixStateAssetError("source_half must be 0 or 1")
    output = bytearray(CONTROLLER_FRAME_BYTES)
    source_x = source_half * CONTROLLER_ROW_BYTES
    for y in range(HEIGHT):
        source = y * ROW_BYTES + source_x
        destination = y * CONTROLLER_ROW_BYTES
        output[destination : destination + CONTROLLER_ROW_BYTES] = frame[
            source : source + CONTROLLER_ROW_BYTES
        ]
    return bytes(output)


def _histogram(frame: bytes) -> tuple[int, ...]:
    if len(frame) != FRAME_BYTES:
        raise SixStateAssetError("packed frame length is not 307200 bytes")
    counts = [0] * 16
    for value in frame:
        counts[value >> 4] += 1
        counts[value & 0x0F] += 1
    return tuple(counts)


def _histogram_manifest(counts: tuple[int, ...]) -> dict[str, int]:
    return {f"0x{code:x}": count for code, count in enumerate(counts)}


def _identity(data: bytes) -> dict[str, Any]:
    fnv = _fnv1a(data)
    return {
        "bytes": len(data),
        "sha256": _sha256(data),
        "fnv1a_u32": fnv,
        "fnv1a_hex": f"0x{fnv:08x}",
    }


def _check_frozen_frame(candidate: int, role: str, frame: bytes) -> None:
    expected = FROZEN_IDENTITIES[candidate][role]
    streams = {
        "full": frame,
        "CS1": _controller_stream(frame, 0),
        "CS2": _controller_stream(frame, 1),
    }
    for name, data in streams.items():
        expected_sha, expected_fnv = expected[name]
        if (_sha256(data), _fnv1a(data)) != (expected_sha, expected_fnv):
            raise SixStateAssetError(
                f"internal frozen identity drift for candidate 0x{candidate:x} "
                f"{role} {name}"
            )
    if _histogram(frame) != FROZEN_HISTOGRAMS[candidate][role]:
        raise SixStateAssetError(
            f"internal frozen histogram drift for candidate 0x{candidate:x} {role}"
        )


def _preview_rgb(frame: bytes, candidate: int) -> bytes:
    palette = dict(KNOWN_RGB)
    palette[candidate] = UNKNOWN_PREVIEW_RGB[candidate]
    rgb = bytearray(WIDTH * HEIGHT * 3)
    output = 0
    for packed in frame:
        for code in (packed >> 4, packed & 0x0F):
            try:
                colour = palette[code]
            except KeyError as error:
                raise SixStateAssetError(
                    f"preview encountered unsupported code 0x{code:x}"
                ) from error
            rgb[output : output + 3] = bytes(colour)
            output += 3
    return bytes(rgb)


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = zlib.crc32(kind)
    checksum = zlib.crc32(payload, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


def _encode_png(rgb: bytes) -> bytes:
    expected = WIDTH * HEIGHT * 3
    if len(rgb) != expected:
        raise SixStateAssetError(f"RGB preview has {len(rgb)} bytes; expected {expected}")
    scanlines = bytearray((WIDTH * 3 + 1) * HEIGHT)
    row_size = WIDTH * 3
    for y in range(HEIGHT):
        destination = y * (row_size + 1)
        scanlines[destination] = 0
        source = y * row_size
        scanlines[destination + 1 : destination + 1 + row_size] = rgb[
            source : source + row_size
        ]
    header = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)
    return b"".join(
        (
            PNG_SIGNATURE,
            _png_chunk(b"IHDR", header),
            _png_chunk(b"IDAT", zlib.compress(bytes(scanlines), level=9)),
            _png_chunk(b"IEND", b""),
        )
    )


def _decode_png(png: bytes) -> bytes:
    if len(png) > MAX_PNG_BYTES or not png.startswith(PNG_SIGNATURE):
        raise SixStateAssetError("preview is not a bounded PNG file")
    offset = len(PNG_SIGNATURE)
    chunks: list[tuple[bytes, bytes]] = []
    while offset < len(png):
        if offset + 12 > len(png):
            raise SixStateAssetError("preview PNG has a truncated chunk")
        length = struct.unpack(">I", png[offset : offset + 4])[0]
        if length > MAX_PNG_BYTES or offset + 12 + length > len(png):
            raise SixStateAssetError("preview PNG chunk length is invalid")
        kind = png[offset + 4 : offset + 8]
        payload = png[offset + 8 : offset + 8 + length]
        reported_crc = struct.unpack(">I", png[offset + 8 + length : offset + 12 + length])[0]
        actual_crc = zlib.crc32(payload, zlib.crc32(kind)) & 0xFFFFFFFF
        if reported_crc != actual_crc:
            raise SixStateAssetError("preview PNG chunk CRC mismatch")
        chunks.append((kind, payload))
        offset += 12 + length
    if [kind for kind, _ in chunks] != [b"IHDR", b"IDAT", b"IEND"]:
        raise SixStateAssetError("preview PNG chunk sequence is not frozen")
    expected_header = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)
    if chunks[0][1] != expected_header or chunks[2][1] != b"":
        raise SixStateAssetError("preview PNG format is not frozen RGB8 1024x600")
    expected_scanline_bytes = (WIDTH * 3 + 1) * HEIGHT
    decompressor = zlib.decompressobj()
    try:
        scanlines = decompressor.decompress(
            chunks[1][1], expected_scanline_bytes + 1
        )
        scanlines += decompressor.flush()
    except zlib.error as error:
        raise SixStateAssetError(f"preview PNG DEFLATE data is invalid: {error}") from error
    if (
        not decompressor.eof
        or decompressor.unused_data
        or decompressor.unconsumed_tail
        or len(scanlines) != expected_scanline_bytes
    ):
        raise SixStateAssetError("preview PNG expands outside the frozen size")
    rgb = bytearray(WIDTH * HEIGHT * 3)
    row_size = WIDTH * 3
    for y in range(HEIGHT):
        source = y * (row_size + 1)
        if scanlines[source] != 0:
            raise SixStateAssetError("preview PNG uses a non-frozen row filter")
        destination = y * row_size
        rgb[destination : destination + row_size] = scanlines[
            source + 1 : source + 1 + row_size
        ]
    return bytes(rgb)


def _frame_manifest(
    candidate: int,
    role: str,
    frame: bytes,
    png: bytes,
) -> dict[str, Any]:
    prefix = f"u0{candidate}_{role}"
    return {
        "role": role,
        "raw_file": f"{prefix}.raw",
        "preview_file": f"{prefix}.preview.png",
        "histogram_all_16_codes": _histogram_manifest(_histogram(frame)),
        "full": _identity(frame),
        "controller_streams": {
            "CS1": _identity(_controller_stream(frame, 0)),
            "CS2": _identity(_controller_stream(frame, 1)),
        },
        "preview": {
            "bytes": len(png),
            "sha256": _sha256(png),
            "format": "PNG-RGB8-1024x600-filter0",
            "semantic": "synthetic-code-visualization-not-physical-colour-prediction",
        },
    }


def build_bundle(candidate: int) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Build the complete deterministic manifest and in-memory asset mapping."""

    candidate = _candidate(candidate)
    primer, target = build_frames(candidate)
    _check_frozen_frame(candidate, "primer", primer)
    _check_frozen_frame(candidate, "target", target)
    primer_png = _encode_png(_preview_rgb(primer, candidate))
    target_png = _encode_png(_preview_rgb(target, candidate))
    tag = f"U0{candidate}"
    assets = {
        f"u0{candidate}_primer.raw": primer,
        f"u0{candidate}_target.raw": target,
        f"u0{candidate}_primer.preview.png": primer_png,
        f"u0{candidate}_target.preview.png": target_png,
    }
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "layout_id": LAYOUT_ID,
        "candidate": {
            "id": tag,
            "code": candidate,
            "code_hex": f"0x{candidate:x}",
            "firmware_compile_parameter": (
                f"MF1750_UNKNOWN_PROBE_CODE={candidate}"
            ),
            "bundle_directory": tag,
        },
        "geometry": {
            "width": WIDTH,
            "height": HEIGHT,
            "bits_per_pixel": 4,
            "packed_bytes": FRAME_BYTES,
            "pixel_packing": "row-major-high-nibble-left-low-nibble-right",
            "background_code": WHITE_CODE,
            "roi_width": ROI_SIDE,
            "roi_height": ROI_SIDE,
            "roi_count": ROI_COUNT,
            "candidate_pixels": CANDIDATE_PIXELS,
            "existing_pilot_pixel_limit": PILOT_PIXEL_LIMIT,
            "within_existing_pilot_pixel_limit": CANDIDATE_PIXELS
            <= PILOT_PIXEL_LIMIT,
        },
        "controller_mapping": {
            name: dict(mapping) for name, mapping in MAPPINGS.items()
        },
        "rois": frozen_rois(candidate),
        "frames": {
            "primer": _frame_manifest(
                candidate, "primer", primer, primer_png
            ),
            "target": _frame_manifest(
                candidate, "target", target, target_png
            ),
        },
        "preview_palette": {
            "known_codes_rgb": {
                f"0x{code:x}": list(rgb) for code, rgb in KNOWN_RGB.items()
            },
            "candidate_pseudocolor_rgb": list(UNKNOWN_PREVIEW_RGB[candidate]),
            "candidate_pseudocolor_is_not_a_colour_prediction": True,
        },
        "safety": {
            "offline_data_only": True,
            "network_path_present": False,
            "serial_path_present": False,
            "device_path_present": False,
            "refresh_path_present": False,
            "hardware_execution_authorized": False,
            "dithering_present": False,
            "spatial_mixing_present": False,
            "every_roi_is_one_uniform_code": True,
            "one_candidate_per_directory": True,
            "candidate_0x4_and_0x7_assets_are_separate": True,
        },
    }
    manifest["integrity"] = {
        "algorithm": "sha256",
        "scope": "canonical manifest excluding integrity",
        "payload_sha256": _sha256(_canonical_json(manifest)),
    }
    assets[f"u0{candidate}_manifest.json"] = (
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    return manifest, assets


def generate_bundle(output_root: Path, candidate: int) -> Path:
    """Create one new U04 or U07 directory without overwriting anything."""

    candidate = _candidate(candidate)
    if not isinstance(output_root, Path):
        raise SixStateAssetError("output root must be pathlib.Path")
    try:
        if output_root.is_symlink() or not output_root.is_dir():
            raise SixStateAssetError(
                "output root must be an existing regular non-symlink directory"
            )
        output_root = output_root.resolve(strict=True)
    except OSError as error:
        raise SixStateAssetError(f"could not resolve output root: {error}") from error
    tag = f"U0{candidate}"
    destination = output_root / tag
    if destination.exists() or destination.is_symlink():
        raise SixStateAssetError(f"candidate directory {tag} already exists")
    _, assets = build_bundle(candidate)
    try:
        destination.mkdir()
    except OSError as error:
        raise SixStateAssetError(f"could not create candidate directory: {error}") from error
    for filename, data in assets.items():
        _write_new(destination / filename, data)
    return destination / f"u0{candidate}_manifest.json"


def validate_bundle(manifest_path: Path) -> dict[str, Any]:
    """Deeply validate one bundle and return a compact read-only report."""

    encoded = _read_regular(
        manifest_path, label="manifest", maximum=MAX_MANIFEST_BYTES
    )
    try:
        manifest = json.loads(
            encoded.decode("utf-8"), object_pairs_hook=_strict_object
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SixStateAssetError(f"manifest is not strict UTF-8 JSON: {error}") from error
    if not isinstance(manifest, dict):
        raise SixStateAssetError("manifest root must be an object")
    candidate_block = manifest.get("candidate")
    if not isinstance(candidate_block, dict):
        raise SixStateAssetError("manifest candidate must be an object")
    candidate = _candidate(candidate_block.get("code"))
    expected, expected_assets = build_bundle(candidate)
    if manifest != expected:
        raise SixStateAssetError("manifest differs from the frozen candidate contract")
    expected_manifest_name = f"u0{candidate}_manifest.json"
    if manifest_path.name != expected_manifest_name:
        raise SixStateAssetError("manifest filename does not match its candidate")
    directory = manifest_path.parent
    if directory.name != f"U0{candidate}":
        raise SixStateAssetError("candidate bundle is not in its isolated directory")
    for filename, expected_data in expected_assets.items():
        if filename == expected_manifest_name:
            continue
        maximum = FRAME_BYTES if filename.endswith(".raw") else MAX_PNG_BYTES
        actual = _read_regular(
            directory / filename, label=filename, maximum=maximum
        )
        if actual != expected_data:
            raise SixStateAssetError(f"{filename} differs from frozen bytes")
        if filename.endswith(".preview.png"):
            role = "primer" if "primer" in filename else "target"
            frame = expected_assets[f"u0{candidate}_{role}.raw"]
            if _decode_png(actual) != _preview_rgb(frame, candidate):
                raise SixStateAssetError(
                    f"{filename} pixels do not match the packed frame"
                )
    # Explicitly demonstrate the scientific condition beyond byte identity.
    primer = expected_assets[f"u0{candidate}_primer.raw"]
    target = expected_assets[f"u0{candidate}_target.raw"]
    for roi in frozen_rois(candidate):
        rect = roi["rect"]
        primer_codes: set[int] = set()
        target_codes: set[int] = set()
        for y in range(rect["y0"], rect["y1_exclusive"]):
            for x in range(rect["x0"], rect["x1_exclusive"]):
                primer_codes.add(_pixel(primer, x, y))
                target_codes.add(_pixel(target, x, y))
        if primer_codes != {roi["initial_code"]} or target_codes != {candidate}:
            raise SixStateAssetError("ROI is not a pure single-code region")
    return {
        "valid": True,
        "kind": KIND,
        "layout_id": LAYOUT_ID,
        "candidate_id": f"U0{candidate}",
        "candidate_code": candidate,
        "candidate_pixels": CANDIDATE_PIXELS,
        "roi_count": ROI_COUNT,
        "dithering_present": False,
        "spatial_mixing_present": False,
        "hardware_execution_authorized": False,
        "manifest_payload_sha256": expected["integrity"]["payload_sha256"],
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate", allow_abbrev=False)
    generate.add_argument("--candidate", type=_candidate_arg, required=True)
    generate.add_argument("--output-root", type=Path, required=True)
    validate = subparsers.add_parser("validate", allow_abbrev=False)
    validate.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "generate":
            manifest_path = generate_bundle(args.output_root, args.candidate)
            report = validate_bundle(manifest_path)
            report["manifest"] = str(manifest_path)
        else:
            report = validate_bundle(args.manifest)
    except SixStateAssetError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
