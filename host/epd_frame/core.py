"""Canonical MF-1750 4bpp frame packing and controller mapping.

Application frames are row-major with logical origin at the top left. Even x
pixels occupy the high nibble and odd x pixels occupy the low nibble. Physical
controller routing and orientation are represented by :class:`ControllerMapping`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, Optional, Sequence, Tuple


WIDTH = 1024
HEIGHT = 600
ROW_BYTES = WIDTH // 2
FRAME_BYTES = ROW_BYTES * HEIGHT
CONTROLLER_WIDTH = WIDTH // 2
CONTROLLER_HEIGHT = HEIGHT
CONTROLLER_ROW_BYTES = CONTROLLER_WIDTH // 2
CONTROLLER_FRAME_BYTES = CONTROLLER_ROW_BYTES * CONTROLLER_HEIGHT

BLACK = 0x0
WHITE = 0x1
YELLOW = 0x2
RED = 0x3
BLUE = 0x5
GREEN = 0x6
PHYSICAL_COLOR_CODES = frozenset((BLACK, WHITE, YELLOW, RED, BLUE, GREEN))

FNV1A_OFFSET_BASIS = 0x811C9DC5
FNV1A_PRIME = 0x01000193


class FrameContractError(ValueError):
    """Raised when pixels, dimensions, or packed data violate the contract."""


@dataclass(frozen=True)
class ControllerMapping:
    """Route and orient one logical half for one physical controller."""

    source_half: int
    flip_x: bool = False
    flip_y: bool = False
    nibble_swap: bool = False

    def __post_init__(self) -> None:
        if type(self.source_half) is not int or self.source_half not in (0, 1):
            raise FrameContractError("source_half must be integer 0 (left) or 1 (right)")
        for name in ("flip_x", "flip_y", "nibble_swap"):
            if type(getattr(self, name)) is not bool:
                raise FrameContractError(f"{name} must be a boolean")


def _validate_dimensions(width: int, height: int, *, controller_layout: bool) -> None:
    if not isinstance(width, int) or not isinstance(height, int):
        raise FrameContractError("width and height must be integers")
    if width <= 0 or height <= 0:
        raise FrameContractError("width and height must be positive")
    if width % 2:
        raise FrameContractError("4bpp packing requires an even width")
    if controller_layout and width % 4:
        raise FrameContractError("two equal controller halves require width divisible by 4")


def _byte_view(data: bytes | bytearray | memoryview) -> memoryview:
    try:
        view = memoryview(data)
        if view.ndim != 1 or view.itemsize != 1 or view.format != "B":
            view = view.cast("B")
        return view
    except (TypeError, ValueError) as error:
        raise FrameContractError("frame must be a contiguous bytes-like object") from error


def _validate_color(color: object, pixel_index: int, allowed_colors: Optional[Sequence[int]]) -> int:
    if not isinstance(color, int) or isinstance(color, bool):
        raise FrameContractError(f"pixel {pixel_index} is not an integer color code")
    if not 0 <= color <= 0xF:
        raise FrameContractError(f"pixel {pixel_index} color code {color!r} does not fit in 4 bits")
    if allowed_colors is not None and color not in allowed_colors:
        raise FrameContractError(f"pixel {pixel_index} uses unsupported physical color code 0x{color:X}")
    return color


def validate_frame(
    frame: bytes | bytearray | memoryview,
    width: int = WIDTH,
    height: int = HEIGHT,
    *,
    allowed_colors: Optional[Sequence[int]] = PHYSICAL_COLOR_CODES,
) -> memoryview:
    """Validate a packed frame and return a zero-copy byte view."""

    _validate_dimensions(width, height, controller_layout=False)
    view = _byte_view(frame)
    expected = width * height // 2
    if len(view) != expected:
        raise FrameContractError(f"packed frame has {len(view)} bytes; expected {expected}")
    if allowed_colors is not None:
        for byte_index, value in enumerate(view):
            high = value >> 4
            low = value & 0xF
            if high not in allowed_colors:
                raise FrameContractError(
                    f"pixel {byte_index * 2} uses unsupported physical color code 0x{high:X}"
                )
            if low not in allowed_colors:
                raise FrameContractError(
                    f"pixel {byte_index * 2 + 1} uses unsupported physical color code 0x{low:X}"
                )
    return view


def pack_pixels(
    pixels: Iterable[int],
    width: int = WIDTH,
    height: int = HEIGHT,
    *,
    allowed_colors: Optional[Sequence[int]] = PHYSICAL_COLOR_CODES,
) -> bytes:
    """Pack one color code per pixel into canonical high/low-nibble order."""

    _validate_dimensions(width, height, controller_layout=False)
    expected_pixels = width * height
    iterator = iter(pixels)
    packed = bytearray(expected_pixels // 2)
    for byte_index in range(len(packed)):
        even_index = byte_index * 2
        try:
            high_value = next(iterator)
            low_value = next(iterator)
        except StopIteration as error:
            raise FrameContractError(f"pixel input ended before {expected_pixels} pixels") from error
        high = _validate_color(high_value, even_index, allowed_colors)
        low = _validate_color(low_value, even_index + 1, allowed_colors)
        packed[byte_index] = (high << 4) | low
    try:
        next(iterator)
    except StopIteration:
        return bytes(packed)
    raise FrameContractError(f"pixel input contains more than {expected_pixels} pixels")


def unpack_pixels(
    frame: bytes | bytearray | memoryview,
    width: int = WIDTH,
    height: int = HEIGHT,
    *,
    allowed_colors: Optional[Sequence[int]] = PHYSICAL_COLOR_CODES,
) -> bytes:
    """Expand a packed frame to one byte per pixel in row-major order."""

    view = validate_frame(frame, width, height, allowed_colors=allowed_colors)
    pixels = bytearray(width * height)
    for byte_index, value in enumerate(view):
        pixels[byte_index * 2] = value >> 4
        pixels[byte_index * 2 + 1] = value & 0xF
    return bytes(pixels)


def fnv1a(data: bytes | bytearray | memoryview) -> int:
    """Return the unsigned 32-bit FNV-1a hash used by the firmware."""

    value = FNV1A_OFFSET_BASIS
    for byte in _byte_view(data):
        value ^= byte
        value = (value * FNV1A_PRIME) & 0xFFFFFFFF
    return value


def pixel_counts(
    frame: bytes | bytearray | memoryview,
    width: int = WIDTH,
    height: int = HEIGHT,
    *,
    allowed_colors: Optional[Sequence[int]] = PHYSICAL_COLOR_CODES,
) -> Tuple[int, ...]:
    """Count all 16 possible 4-bit codes after validating the frame."""

    view = validate_frame(frame, width, height, allowed_colors=allowed_colors)
    counts = [0] * 16
    for value in view:
        counts[value >> 4] += 1
        counts[value & 0xF] += 1
    return tuple(counts)


def split_controller_rows(
    frame: bytes | bytearray | memoryview,
    width: int = WIDTH,
    height: int = HEIGHT,
    *,
    allowed_colors: Optional[Sequence[int]] = PHYSICAL_COLOR_CODES,
) -> Iterator[Tuple[bytes, bytes]]:
    """Yield ``(left_row, right_row)`` packed halves for each logical row."""

    _validate_dimensions(width, height, controller_layout=True)
    view = validate_frame(frame, width, height, allowed_colors=allowed_colors)
    full_row_bytes = width // 2
    half_row_bytes = width // 4
    for y in range(height):
        row_start = y * full_row_bytes
        middle = row_start + half_row_bytes
        yield bytes(view[row_start:middle]), bytes(view[middle : row_start + full_row_bytes])


def split_controllers(
    frame: bytes | bytearray | memoryview,
    width: int = WIDTH,
    height: int = HEIGHT,
    *,
    allowed_colors: Optional[Sequence[int]] = PHYSICAL_COLOR_CODES,
) -> Tuple[bytes, bytes]:
    """Return packed logical-left and logical-right streams, each row-major."""

    left = bytearray()
    right = bytearray()
    for left_row, right_row in split_controller_rows(
        frame, width, height, allowed_colors=allowed_colors
    ):
        left.extend(left_row)
        right.extend(right_row)
    return bytes(left), bytes(right)


def iter_controller_rows(
    frame: bytes | bytearray | memoryview,
    mapping: ControllerMapping,
    width: int = WIDTH,
    height: int = HEIGHT,
    *,
    allowed_colors: Optional[Sequence[int]] = PHYSICAL_COLOR_CODES,
) -> Iterator[bytes]:
    """Yield mapped DTM rows using the same byte algorithm as the driver."""

    _validate_dimensions(width, height, controller_layout=True)
    view = validate_frame(frame, width, height, allowed_colors=allowed_colors)
    full_row_bytes = width // 2
    controller_row_bytes = width // 4
    for output_y in range(height):
        source_y = height - 1 - output_y if mapping.flip_y else output_y
        row_start = source_y * full_row_bytes + mapping.source_half * controller_row_bytes
        row = bytearray(controller_row_bytes)
        for output_byte in range(controller_row_bytes):
            source_byte = controller_row_bytes - 1 - output_byte if mapping.flip_x else output_byte
            value = view[row_start + source_byte]
            if mapping.flip_x != mapping.nibble_swap:
                value = ((value << 4) | (value >> 4)) & 0xFF
            row[output_byte] = value
        yield bytes(row)


def controller_stream(
    frame: bytes | bytearray | memoryview,
    mapping: ControllerMapping,
    width: int = WIDTH,
    height: int = HEIGHT,
    *,
    allowed_colors: Optional[Sequence[int]] = PHYSICAL_COLOR_CODES,
) -> bytes:
    """Return the complete mapped DTM stream for one controller."""

    return b"".join(
        iter_controller_rows(frame, mapping, width, height, allowed_colors=allowed_colors)
    )


def controller_stream_reference(
    frame: bytes | bytearray | memoryview,
    mapping: ControllerMapping,
    width: int = WIDTH,
    height: int = HEIGHT,
    *,
    allowed_colors: Optional[Sequence[int]] = PHYSICAL_COLOR_CODES,
) -> bytes:
    """Independent pixel-level mapping reference for regression tests."""

    _validate_dimensions(width, height, controller_layout=True)
    view = validate_frame(frame, width, height, allowed_colors=allowed_colors)
    full_row_bytes = width // 2
    half_width = width // 2
    half_base = mapping.source_half * half_width
    output = bytearray(width * height // 4)

    def raw_pixel(x: int, y: int) -> int:
        value = view[y * full_row_bytes + x // 2]
        return value & 0xF if x & 1 else value >> 4

    output_index = 0
    for output_y in range(height):
        source_y = height - 1 - output_y if mapping.flip_y else output_y
        for output_x in range(0, half_width, 2):
            if mapping.flip_x:
                source_x0 = half_width - 1 - output_x
                source_x1 = half_width - 1 - (output_x + 1)
            else:
                source_x0 = output_x
                source_x1 = output_x + 1
            value = (
                raw_pixel(half_base + source_x0, source_y) << 4
                | raw_pixel(half_base + source_x1, source_y)
            )
            if mapping.nibble_swap:
                value = ((value << 4) | (value >> 4)) & 0xFF
            output[output_index] = value
            output_index += 1
    return bytes(output)

