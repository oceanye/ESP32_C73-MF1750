"""Build controller-neutral old-frame/new-frame transition plans.

The output is deliberately not a controller command stream. It captures the
information a documented partial-update interface would need: changed pixels,
transition counts, protected border pixels, and controller-local regions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple


WIDTH = 1024
HEIGHT = 600
ROW_BYTES = WIDTH // 2
FRAME_BYTES = ROW_BYTES * HEIGHT
COLOR_CODES = (0x0, 0x1, 0x2, 0x3, 0x5, 0x6)
COLOR_NAMES = ("black", "white", "yellow", "red", "blue", "green")
_COLOR_INDEX = {color: index for index, color in enumerate(COLOR_CODES)}
_FNV1A_OFFSET = 0x811C9DC5
_FNV1A_PRIME = 0x01000193


class PartialUpdateContractError(ValueError):
    """Raised when a frame or planning parameter violates the contract."""


@dataclass(frozen=True)
class ControllerRegion:
    """Half-open global and controller-local rectangle for one controller."""

    controller: int
    global_x0: int
    global_y0: int
    global_x1: int
    global_y1: int
    local_x0: int
    local_x1: int

    def to_dict(self) -> Dict[str, int]:
        return {
            "controller": self.controller,
            "global_x0": self.global_x0,
            "global_y0": self.global_y0,
            "global_x1": self.global_x1,
            "global_y1": self.global_y1,
            "local_x0": self.local_x0,
            "local_x1": self.local_x1,
        }


@dataclass(frozen=True)
class TransitionPlan:
    width: int
    height: int
    old_state_known: bool
    old_frame_fnv1a: Optional[int]
    new_frame_fnv1a: int
    changed_pixels: int
    protected_pixels: int
    unchanged_pixels: int
    neighbor_radius: int
    bounding_box: Optional[Tuple[int, int, int, int]]
    controller_regions: Tuple[ControllerRegion, ...]
    transition_histogram: Optional[Tuple[Tuple[int, ...], ...]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": 1,
            "kind": "mf1750-partial-update-plan",
            "hardware_tested": False,
            "controller_commands_generated": False,
            "width": self.width,
            "height": self.height,
            "old_state_known": self.old_state_known,
            "old_frame_fnv1a": self.old_frame_fnv1a,
            "new_frame_fnv1a": self.new_frame_fnv1a,
            "changed_pixels": self.changed_pixels,
            "protected_pixels": self.protected_pixels,
            "unchanged_pixels": self.unchanged_pixels,
            "changed_fraction": self.changed_pixels / (self.width * self.height),
            "protected_fraction": self.protected_pixels / (self.width * self.height),
            "neighbor_radius": self.neighbor_radius,
            "bounding_box": list(self.bounding_box) if self.bounding_box is not None else None,
            "controller_regions": [region.to_dict() for region in self.controller_regions],
            "color_order": list(COLOR_NAMES),
            "color_codes": list(COLOR_CODES),
            "transition_histogram": (
                [list(row) for row in self.transition_histogram]
                if self.transition_histogram is not None
                else None
            ),
            "requires_vendor_partial_update_definition": True,
        }


def _validate_dimensions(width: int, height: int) -> None:
    if not isinstance(width, int) or isinstance(width, bool):
        raise PartialUpdateContractError("width must be an integer")
    if not isinstance(height, int) or isinstance(height, bool):
        raise PartialUpdateContractError("height must be an integer")
    if width <= 0 or height <= 0:
        raise PartialUpdateContractError("width and height must be positive")
    if width % 4:
        raise PartialUpdateContractError("two packed controller halves require width divisible by 4")


def _validated_frame(
    frame: bytes | bytearray | memoryview, width: int, height: int, label: str
) -> memoryview:
    try:
        view = memoryview(frame)
        if view.ndim != 1 or view.itemsize != 1:
            view = view.cast("B")
    except (TypeError, ValueError) as error:
        raise PartialUpdateContractError(f"{label} must be contiguous bytes-like data") from error
    expected = width * height // 2
    if len(view) != expected:
        raise PartialUpdateContractError(f"{label} has {len(view)} bytes; expected {expected}")
    for byte_index, value in enumerate(view):
        high = value >> 4
        low = value & 0xF
        if high not in _COLOR_INDEX:
            raise PartialUpdateContractError(
                f"{label} pixel {byte_index * 2} has unsupported color 0x{high:X}"
            )
        if low not in _COLOR_INDEX:
            raise PartialUpdateContractError(
                f"{label} pixel {byte_index * 2 + 1} has unsupported color 0x{low:X}"
            )
    return view


def fnv1a(frame: bytes | bytearray | memoryview) -> int:
    value = _FNV1A_OFFSET
    try:
        view = memoryview(frame).cast("B")
    except (TypeError, ValueError) as error:
        raise PartialUpdateContractError("frame must be contiguous bytes-like data") from error
    for byte in view:
        value ^= byte
        value = (value * _FNV1A_PRIME) & 0xFFFFFFFF
    return value


def _pixel(view: memoryview, row_bytes: int, x: int, y: int) -> int:
    value = view[y * row_bytes + x // 2]
    return value & 0xF if x & 1 else value >> 4


def _dilate_cardinal(mask: bytearray, width: int, height: int, radius: int) -> bytearray:
    expanded = bytearray(mask)
    for _ in range(radius):
        source = expanded
        target = bytearray(source)
        for y in range(height):
            row = y * width
            for x in range(width):
                index = row + x
                if not source[index]:
                    continue
                if x:
                    target[index - 1] = 1
                if x + 1 < width:
                    target[index + 1] = 1
                if y:
                    target[index - width] = 1
                if y + 1 < height:
                    target[index + width] = 1
        expanded = target
    return expanded


def _bounding_box(mask: bytearray, width: int, height: int) -> Optional[Tuple[int, int, int, int]]:
    min_x = width
    min_y = height
    max_x = -1
    max_y = -1
    for y in range(height):
        row = y * width
        for x in range(width):
            if not mask[row + x]:
                continue
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    if max_x < 0:
        return None
    # Packed 4bpp commands will require complete bytes. Keep x half-open and
    # align outward to pairs without assuming a controller window register.
    min_x &= ~1
    max_x_exclusive = min(width, (max_x + 2) & ~1)
    return min_x, min_y, max_x_exclusive, max_y + 1


def _controller_regions(
    mask: bytearray, width: int, height: int
) -> Tuple[ControllerRegion, ...]:
    half_width = width // 2
    regions: List[ControllerRegion] = []
    for controller in (1, 2):
        half_start = (controller - 1) * half_width
        half_end = half_start + half_width
        min_x = half_end
        min_y = height
        max_x = -1
        max_y = -1
        for y in range(height):
            row = y * width
            for x in range(half_start, half_end):
                if not mask[row + x]:
                    continue
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
        if max_x < 0:
            continue
        min_x &= ~1
        max_x_exclusive = min(half_end, (max_x + 2) & ~1)
        regions.append(
            ControllerRegion(
                controller=controller,
                global_x0=min_x,
                global_y0=min_y,
                global_x1=max_x_exclusive,
                global_y1=max_y + 1,
                local_x0=min_x - half_start,
                local_x1=max_x_exclusive - half_start,
            )
        )
    return tuple(regions)


def build_transition_plan(
    old_frame: Optional[bytes | bytearray | memoryview],
    new_frame: bytes | bytearray | memoryview,
    *,
    width: int = WIDTH,
    height: int = HEIGHT,
    neighbor_radius: int = 1,
) -> TransitionPlan:
    """Compare frames and build a conservative controller-neutral plan.

    ``old_frame=None`` selects conservative unknown-state mode: every pixel is
    marked changed and no transition histogram is invented.
    """

    _validate_dimensions(width, height)
    if not isinstance(neighbor_radius, int) or isinstance(neighbor_radius, bool):
        raise PartialUpdateContractError("neighbor_radius must be an integer")
    if neighbor_radius < 0:
        raise PartialUpdateContractError("neighbor_radius cannot be negative")
    new_view = _validated_frame(new_frame, width, height, "new_frame")
    old_view = (
        _validated_frame(old_frame, width, height, "old_frame")
        if old_frame is not None
        else None
    )
    pixel_total = width * height
    row_bytes = width // 2
    changed_mask = bytearray(pixel_total)
    histogram: Optional[List[List[int]]] = (
        [[0 for _ in COLOR_CODES] for _ in COLOR_CODES] if old_view is not None else None
    )
    changed_pixels = 0

    if old_view is None:
        changed_mask[:] = b"\x01" * pixel_total
        changed_pixels = pixel_total
    else:
        for y in range(height):
            for x in range(width):
                old_color = _pixel(old_view, row_bytes, x, y)
                new_color = _pixel(new_view, row_bytes, x, y)
                histogram[_COLOR_INDEX[old_color]][_COLOR_INDEX[new_color]] += 1
                if old_color != new_color:
                    changed_mask[y * width + x] = 1
                    changed_pixels += 1

    protected_mask = _dilate_cardinal(changed_mask, width, height, neighbor_radius)
    protected_pixels = sum(protected_mask)
    return TransitionPlan(
        width=width,
        height=height,
        old_state_known=old_view is not None,
        old_frame_fnv1a=fnv1a(old_view) if old_view is not None else None,
        new_frame_fnv1a=fnv1a(new_view),
        changed_pixels=changed_pixels,
        protected_pixels=protected_pixels,
        unchanged_pixels=pixel_total - changed_pixels,
        neighbor_radius=neighbor_radius,
        bounding_box=_bounding_box(protected_mask, width, height),
        controller_regions=_controller_regions(protected_mask, width, height),
        transition_histogram=(
            tuple(tuple(row) for row in histogram) if histogram is not None else None
        ),
    )

