"""Deterministic frame fixtures shared by host tests and future tooling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Tuple

from .core import (
    BLACK,
    BLUE,
    FRAME_BYTES,
    GREEN,
    HEIGHT,
    RED,
    WHITE,
    WIDTH,
    YELLOW,
    ControllerMapping,
    controller_stream,
    fnv1a,
    pack_pixels,
    pixel_counts,
)


FIXTURE_NAMES = ("global-v-bars", "global-h-bars", "map-orient-v1")
BAR_COLORS = (WHITE, BLACK, RED, YELLOW, BLUE, GREEN)
EXPECTED_FIXTURE_HASHES: Dict[str, Tuple[int, int, int]] = {
    "global-v-bars": (0x908478A5, 0x61BCF1C5, 0xA3446735),
    "global-h-bars": (0x7DD055C5, 0x855679C5, 0x855679C5),
    "map-orient-v1": (0x9D04142D, 0xF26832DD, 0xFE199FF5),
}
MAP_ORIENT_V1_PIXEL_COUNTS = (
    39536,
    425808,
    29280,
    47072,
    0,
    44192,
    28512,
) + (0,) * 9


@dataclass(frozen=True)
class FixtureReport:
    name: str
    byte_count: int
    full_fnv1a: int
    cs1_fnv1a: int
    cs2_fnv1a: int
    pixel_counts: Tuple[int, ...]
    verified: bool


def _pack_function(pixel_at: Callable[[int, int], int]) -> bytes:
    return pack_pixels(
        pixel_at(x, y)
        for y in range(HEIGHT)
        for x in range(WIDTH)
    )


def _generate_global_v_bars() -> bytes:
    return _pack_function(lambda x, _y: BAR_COLORS[x * len(BAR_COLORS) // WIDTH])


def _generate_global_h_bars() -> bytes:
    return _pack_function(lambda _x, y: BAR_COLORS[y * len(BAR_COLORS) // HEIGHT])


def _generate_map_orient_v1() -> bytes:
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
    for half_base in (0, WIDTH // 2):
        for local_x, y0, color, ticks in corners:
            rect(half_base + local_x, half_base + local_x + 80, y0, y0 + 80, color)
            for tick in range(ticks):
                rect(
                    half_base + local_x + 8 + 16 * tick,
                    half_base + local_x + 16 + 16 * tick,
                    y0 + 32,
                    y0 + 48,
                    BLACK,
                )

    rect(176, 336, 200, 280, RED)
    rect(248, 264, 216, 264, BLACK)
    rect(512 + 176, 512 + 336, 200, 280, BLUE)
    rect(512 + 224, 512 + 240, 216, 264, WHITE)
    rect(512 + 272, 512 + 288, 216, 264, WHITE)

    for half_base in (0, WIDTH // 2):
        rect(half_base + 156, half_base + 356, 320, 380, RED)
        rect(half_base + 160, half_base + 192, 324, 376, BLACK)
        rect(half_base + 320, half_base + 352, 324, 376, WHITE)
        for y in range(324, 376):
            for local_x in range(192, 320):
                pixels[y * WIDTH + half_base + local_x] = WHITE if local_x & 1 else BLACK

        rect(half_base + 156, half_base + 356, 396, 456, BLUE)
        rect(half_base + 160, half_base + 192, 400, 452, WHITE)
        rect(half_base + 320, half_base + 352, 400, 452, BLACK)
        for y in range(400, 452):
            for local_x in range(192, 320):
                pixels[y * WIDTH + half_base + local_x] = BLACK if local_x & 1 else WHITE

    seam_colors = (BLACK, RED, BLUE, YELLOW, GREEN, WHITE, BLUE, GREEN, RED, YELLOW)
    for index, color in enumerate(seam_colors):
        rect(492 + 4 * index, 496 + 4 * index, 20, 580, color)
    rect(440, 584, 169, 177, BLACK)
    rect(456, 568, 409, 421, RED)
    return pack_pixels(pixels)


def generate_fixture(name: str) -> bytes:
    """Generate one named fixture without file or hardware I/O."""

    generators = {
        "global-v-bars": _generate_global_v_bars,
        "global-h-bars": _generate_global_h_bars,
        "map-orient-v1": _generate_map_orient_v1,
    }
    try:
        generator = generators[name]
    except KeyError as error:
        raise ValueError(f"unknown fixture {name!r}; choose one of {FIXTURE_NAMES}") from error
    return generator()


def verify_fixture(name: str, frame: bytes | None = None) -> FixtureReport:
    """Verify byte length, hashes, and the MAP_ORIENT_V1 color counts."""

    if frame is None:
        frame = generate_fixture(name)
    if name not in EXPECTED_FIXTURE_HASHES:
        raise ValueError(f"unknown fixture {name!r}; choose one of {FIXTURE_NAMES}")
    cs1 = controller_stream(frame, ControllerMapping(0))
    cs2 = controller_stream(frame, ControllerMapping(1))
    actual_hashes = (fnv1a(frame), fnv1a(cs1), fnv1a(cs2))
    counts = pixel_counts(frame)
    counts_ok = name != "map-orient-v1" or counts == MAP_ORIENT_V1_PIXEL_COUNTS
    return FixtureReport(
        name=name,
        byte_count=len(frame),
        full_fnv1a=actual_hashes[0],
        cs1_fnv1a=actual_hashes[1],
        cs2_fnv1a=actual_hashes[2],
        pixel_counts=counts,
        verified=len(frame) == FRAME_BYTES
        and actual_hashes == EXPECTED_FIXTURE_HASHES[name]
        and counts_ok,
    )

