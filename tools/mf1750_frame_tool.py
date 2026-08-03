#!/usr/bin/env python3
"""Generate and verify deterministic MF-1750 1024x600 4bpp test frames.

The default operation is offline and cannot refresh the panel. Supplying --url
posts to the non-refreshing frame-ingress endpoint. A real refresh additionally
requires both --refresh and --confirm-cold-start.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request


WIDTH = 1024
HEIGHT = 600
ROW_BYTES = WIDTH // 2
CONTROLLER_ROW_BYTES = ROW_BYTES // 2
FRAME_BYTES = ROW_BYTES * HEIGHT

BLACK = 0x0
WHITE = 0x1
YELLOW = 0x2
RED = 0x3
BLUE = 0x5
GREEN = 0x6
COLORS = (WHITE, BLACK, RED, YELLOW, BLUE, GREEN)

EXPECTED = {
    "map-orient-v1": (0x9D04142D, 0xF26832DD, 0xFE199FF5),
    "global-v-bars": (0x908478A5, 0x61BCF1C5, 0xA3446735),
    "global-h-bars": (0x7DD055C5, 0x855679C5, 0x855679C5),
}
MAP_ORIENT_V1_COUNTS = (39536, 425808, 29280, 47072, 0, 44192, 28512)


def fnv1a(data: bytes | bytearray) -> int:
    value = 0x811C9DC5
    for byte in data:
        value ^= byte
        value = (value * 0x01000193) & 0xFFFFFFFF
    return value


def pack_pixels(pixel_at) -> bytes:
    frame = bytearray(FRAME_BYTES)
    for y in range(HEIGHT):
        row = y * ROW_BYTES
        for x in range(0, WIDTH, 2):
            frame[row + x // 2] = ((pixel_at(x, y) & 0xF) << 4) | (pixel_at(x + 1, y) & 0xF)
    return bytes(frame)


def generate_map_orient_v1() -> bytes:
    pixels = bytearray([WHITE]) * (WIDTH * HEIGHT)

    def rect(x0: int, x1: int, y0: int, y1: int, color: int) -> None:
        fill = bytes([color]) * (x1 - x0)
        for y in range(y0, y1):
            pixels[y * WIDTH + x0 : y * WIDTH + x1] = fill

    edge_colors = (BLACK, RED, YELLOW, BLUE, GREEN)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            distance = min(x, WIDTH - 1 - x, y, HEIGHT - 1 - y)
            if distance < 20:
                pixels[y * WIDTH + x] = edge_colors[distance // 4]

    corners = (
        (32, 32, RED, 1),
        (400, 32, YELLOW, 2),
        (32, 488, BLUE, 3),
        (400, 488, GREEN, 4),
    )
    for half_base in (0, 512):
        for u0, y0, color, ticks in corners:
            rect(half_base + u0, half_base + u0 + 80, y0, y0 + 80, color)
            for tick in range(ticks):
                rect(half_base + u0 + 8 + 16 * tick,
                     half_base + u0 + 16 + 16 * tick,
                     y0 + 32, y0 + 48, BLACK)

    rect(176, 336, 200, 280, RED)
    rect(248, 264, 216, 264, BLACK)
    rect(512 + 176, 512 + 336, 200, 280, BLUE)
    rect(512 + 224, 512 + 240, 216, 264, WHITE)
    rect(512 + 272, 512 + 288, 216, 264, WHITE)

    for half_base in (0, 512):
        rect(half_base + 156, half_base + 356, 320, 380, RED)
        rect(half_base + 160, half_base + 192, 324, 376, BLACK)
        rect(half_base + 320, half_base + 352, 324, 376, WHITE)
        for y in range(324, 376):
            for u in range(192, 320):
                pixels[y * WIDTH + half_base + u] = WHITE if u & 1 else BLACK

        rect(half_base + 156, half_base + 356, 396, 456, BLUE)
        rect(half_base + 160, half_base + 192, 400, 452, WHITE)
        rect(half_base + 320, half_base + 352, 400, 452, BLACK)
        for y in range(400, 452):
            for u in range(192, 320):
                pixels[y * WIDTH + half_base + u] = BLACK if u & 1 else WHITE

    seam_colors = (BLACK, RED, BLUE, YELLOW, GREEN, WHITE, BLUE, GREEN, RED, YELLOW)
    for index, color in enumerate(seam_colors):
        rect(492 + 4 * index, 496 + 4 * index, 20, 580, color)
    rect(440, 584, 169, 177, BLACK)
    rect(456, 568, 409, 421, RED)

    frame = bytearray(FRAME_BYTES)
    for y in range(HEIGHT):
        for x in range(0, WIDTH, 2):
            frame[(y * WIDTH + x) // 2] = (pixels[y * WIDTH + x] << 4) | pixels[y * WIDTH + x + 1]
    return bytes(frame)


def generate(pattern: str) -> bytes:
    if pattern == "map-orient-v1":
        return generate_map_orient_v1()
    if pattern == "global-v-bars":
        return pack_pixels(lambda x, _y: COLORS[x * 6 // WIDTH])
    if pattern == "global-h-bars":
        return pack_pixels(lambda _x, y: COLORS[y * 6 // HEIGHT])
    raise ValueError(f"unknown pattern: {pattern}")


def split_controllers(frame: bytes) -> tuple[bytes, bytes]:
    first = bytearray()
    second = bytearray()
    for y in range(HEIGHT):
        row = y * ROW_BYTES
        first.extend(frame[row : row + CONTROLLER_ROW_BYTES])
        second.extend(frame[row + CONTROLLER_ROW_BYTES : row + ROW_BYTES])
    return bytes(first), bytes(second)


def controller_stream(frame: bytes, source_half: int, flip_x: bool, flip_y: bool,
                      nibble_swap: bool) -> bytes:
    """Mirror the production driver's byte-level mapping algorithm."""
    output = bytearray()
    for output_y in range(HEIGHT):
        source_y = HEIGHT - 1 - output_y if flip_y else output_y
        row = source_y * ROW_BYTES + source_half * CONTROLLER_ROW_BYTES
        source = frame[row : row + CONTROLLER_ROW_BYTES]
        for output_byte in range(CONTROLLER_ROW_BYTES):
            source_byte = CONTROLLER_ROW_BYTES - 1 - output_byte if flip_x else output_byte
            value = source[source_byte]
            if flip_x != nibble_swap:
                value = ((value << 4) | (value >> 4)) & 0xFF
            output.append(value)
    return bytes(output)


def pixel_at(frame: bytes, x: int, y: int) -> int:
    value = frame[y * ROW_BYTES + x // 2]
    return value & 0xF if x & 1 else value >> 4


def controller_stream_reference(frame: bytes, source_half: int, flip_x: bool,
                                flip_y: bool, nibble_swap: bool) -> bytes:
    """Independent pixel-level reference for all mapping combinations."""
    output = bytearray()
    half_base = source_half * (WIDTH // 2)
    for output_y in range(HEIGHT):
        source_y = HEIGHT - 1 - output_y if flip_y else output_y
        for output_x in range(0, WIDTH // 2, 2):
            source_x0 = WIDTH // 2 - 1 - output_x if flip_x else output_x
            source_x1 = WIDTH // 2 - 1 - (output_x + 1) if flip_x else output_x + 1
            value = (pixel_at(frame, half_base + source_x0, source_y) << 4) | pixel_at(
                frame, half_base + source_x1, source_y
            )
            if nibble_swap:
                value = ((value << 4) | (value >> 4)) & 0xFF
            output.append(value)
    return bytes(output)


def verify_mapping_algorithm(frame: bytes) -> bool:
    for source_half in (0, 1):
        for flip_x in (False, True):
            for flip_y in (False, True):
                for nibble_swap in (False, True):
                    actual = controller_stream(frame, source_half, flip_x, flip_y, nibble_swap)
                    reference = controller_stream_reference(
                        frame, source_half, flip_x, flip_y, nibble_swap
                    )
                    if actual != reference:
                        return False
    return True


def verify(pattern: str, frame: bytes) -> dict[str, int | str | bool]:
    first, second = split_controllers(frame)
    actual = (fnv1a(frame), fnv1a(first), fnv1a(second))
    expected = EXPECTED[pattern]
    result = {
        "pattern": pattern,
        "bytes": len(frame),
        "full_fnv1a": actual[0],
        "cs1_fnv1a": actual[1],
        "cs2_fnv1a": actual[2],
        "expected_full_fnv1a": expected[0],
        "expected_cs1_fnv1a": expected[1],
        "expected_cs2_fnv1a": expected[2],
        "mapping_algorithm_verified": verify_mapping_algorithm(frame),
        "verified": len(frame) == FRAME_BYTES and actual == expected,
    }
    if pattern == "map-orient-v1":
        counts = [0] * 16
        for value in frame:
            counts[value >> 4] += 1
            counts[value & 0xF] += 1
        result["pixel_counts_verified"] = tuple(counts[:7]) == MAP_ORIENT_V1_COUNTS and not any(counts[7:])
        result["verified"] = bool(result["verified"] and result["pixel_counts_verified"])
    result["verified"] = bool(result["verified"] and result["mapping_algorithm_verified"])
    return result


def post_frame(base_url: str, frame: bytes, refresh: bool) -> tuple[int, str]:
    endpoint = "/api/frame" if refresh else "/api/diagnostic/frame-ingress"
    request = urllib.request.Request(
        base_url.rstrip("/") + endpoint,
        data=frame,
        method="POST",
        headers={"Content-Type": "application/octet-stream"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=20) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pattern", choices=sorted(EXPECTED), default="map-orient-v1")
    parser.add_argument("--output", type=Path, help="optionally write the raw 4bpp frame")
    parser.add_argument("--url", help="ESP32 base URL; default endpoint only checks ingress")
    parser.add_argument("--refresh", action="store_true", help="post to /api/frame instead of safe ingress")
    parser.add_argument(
        "--confirm-cold-start",
        action="store_true",
        help="required with --refresh; confirms one test after a >=10 s J2-1 power-off",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.refresh and (not args.url or not args.confirm_cold_start):
        print("ERROR: --refresh requires --url and --confirm-cold-start", file=sys.stderr)
        return 2

    frame = generate(args.pattern)
    report = verify(args.pattern, frame)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["verified"]:
        print("ERROR: deterministic frame self-test failed; refusing output/upload", file=sys.stderr)
        return 1

    if args.output:
        args.output.write_bytes(frame)
        print(f"wrote {len(frame)} bytes to {args.output}")

    if args.url:
        status, body = post_frame(args.url, frame, args.refresh)
        print(f"HTTP {status} {body}")
        if status not in ({202} if args.refresh else {200}):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
