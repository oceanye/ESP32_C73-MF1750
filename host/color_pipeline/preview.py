"""Minimal deterministic RGB PNG encoder for palette previews."""

from __future__ import annotations

import binascii
import struct
import zlib


class PreviewError(ValueError):
    """Raised when preview dimensions or RGB data are invalid."""


def _chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = binascii.crc32(kind)
    checksum = binascii.crc32(payload, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


def encode_rgb_png(width: int, height: int, rgb: bytes | bytearray | memoryview) -> bytes:
    """Encode 8-bit RGB pixels as a deterministic, non-interlaced PNG."""

    if not isinstance(width, int) or isinstance(width, bool) or width <= 0:
        raise PreviewError("PNG width must be a positive integer")
    if not isinstance(height, int) or isinstance(height, bool) or height <= 0:
        raise PreviewError("PNG height must be a positive integer")
    try:
        view = memoryview(rgb).cast("B")
    except (TypeError, ValueError) as error:
        raise PreviewError("PNG RGB data must be contiguous bytes") from error
    expected = width * height * 3
    if len(view) != expected:
        raise PreviewError(f"PNG RGB data has {len(view)} bytes; expected {expected}")
    scanlines = bytearray(height * (width * 3 + 1))
    source_row = width * 3
    target_row = source_row + 1
    for y in range(height):
        target = y * target_row
        scanlines[target] = 0  # PNG filter type: None
        start = y * source_row
        scanlines[target + 1 : target + target_row] = view[start : start + source_row]
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    compressed = zlib.compress(bytes(scanlines), level=9)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", compressed)
        + _chunk(b"IEND", b"")
    )
