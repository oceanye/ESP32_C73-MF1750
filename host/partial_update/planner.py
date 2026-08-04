"""Build controller-neutral old-frame/new-frame transition plans.

The output is deliberately not a controller command stream.  It captures the
information a documented partial-update interface would need: changed pixels,
transition counts, protected border pixels, and *logical-half* regions.

Supplying an old-frame file is not proof that those pixels are currently on the
panel.  A transition comparison is therefore enabled only when the caller also
supplies matching, explicitly trusted provenance for the last successful
display operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from host.epd_frame import (
    FRAME_BYTES,
    HEIGHT,
    PHYSICAL_COLOR_CODES,
    WIDTH,
    ControllerMapping,
    FrameContractError,
    fnv1a,
    validate_frame,
)


COLOR_CODES = tuple(sorted(PHYSICAL_COLOR_CODES))
COLOR_NAMES = ("black", "white", "yellow", "red", "blue", "green")
MAX_NEIGHBOR_RADIUS = 32
_COLOR_INDEX = {color: index for index, color in enumerate(COLOR_CODES)}


class PartialUpdateContractError(ValueError):
    """Raised when a frame or planning parameter violates the contract."""


@dataclass(frozen=True)
class LogicalHalfRegion:
    """Half-open canonical rectangle belonging to one logical frame half.

    Physical-controller coordinates are absent unless the caller explicitly
    supplies the frozen pair of :class:`ControllerMapping` objects.  The order
    of that pair identifies physical controllers 1 and 2; it is never inferred
    from left/right position.
    """

    logical_half: int
    global_x0: int
    global_y0: int
    global_x1: int
    global_y1: int
    logical_local_x0: int
    logical_local_x1: int
    physical_controller: Optional[int] = None
    physical_local_x0: Optional[int] = None
    physical_local_y0: Optional[int] = None
    physical_local_x1: Optional[int] = None
    physical_local_y1: Optional[int] = None
    physical_mapping: Optional[ControllerMapping] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "logical_half": self.logical_half,
            "global_x0": self.global_x0,
            "global_y0": self.global_y0,
            "global_x1": self.global_x1,
            "global_y1": self.global_y1,
            "logical_local_x0": self.logical_local_x0,
            "logical_local_x1": self.logical_local_x1,
        }
        if self.physical_controller is not None:
            mapping = self.physical_mapping
            if mapping is None:  # Defensive: invalid objects should never serialize.
                raise PartialUpdateContractError("physical region is missing its mapping")
            result.update(
                {
                    "physical_controller": self.physical_controller,
                    "physical_local_x0": self.physical_local_x0,
                    "physical_local_y0": self.physical_local_y0,
                    "physical_local_x1": self.physical_local_x1,
                    "physical_local_y1": self.physical_local_y1,
                    "physical_mapping": {
                        "source_half": mapping.source_half,
                        "flip_x": mapping.flip_x,
                        "flip_y": mapping.flip_y,
                        "nibble_swap": mapping.nibble_swap,
                    },
                }
            )
        return result


@dataclass(frozen=True)
class TransitionPlan:
    width: int
    height: int
    old_frame_supplied: bool
    supplied_old_frame_fnv1a: Optional[int]
    last_success_operation_id: Optional[str]
    last_success_frame_fnv1a: Optional[int]
    last_success_trusted: bool
    last_success_matches_old_frame: Optional[bool]
    transition_comparison_performed: bool
    new_frame_fnv1a: int
    changed_pixels: Optional[int]
    protected_pixels: int
    unchanged_pixels: Optional[int]
    neighbor_radius: int
    bounding_box: Optional[Tuple[int, int, int, int]]
    logical_half_regions: Tuple[LogicalHalfRegion, ...]
    physical_mapping_supplied: bool
    transition_histogram: Optional[Tuple[Tuple[int, ...], ...]]

    def to_dict(self) -> Dict[str, Any]:
        pixel_total = self.width * self.height
        return {
            "schema_version": 2,
            "kind": "mf1750-partial-update-plan",
            "hardware_tested": False,
            "controller_commands_generated": False,
            "width": self.width,
            "height": self.height,
            "old_frame_supplied": self.old_frame_supplied,
            "supplied_old_frame_fnv1a": self.supplied_old_frame_fnv1a,
            "last_success_provenance": {
                "operation_id": self.last_success_operation_id,
                "frame_fnv1a": self.last_success_frame_fnv1a,
                "trusted": self.last_success_trusted,
                "matches_supplied_old_frame": self.last_success_matches_old_frame,
            },
            "transition_comparison_performed": self.transition_comparison_performed,
            "planning_mode": (
                "trusted_transition"
                if self.transition_comparison_performed
                else "conservative_full_screen"
            ),
            "new_frame_fnv1a": self.new_frame_fnv1a,
            "changed_pixels": self.changed_pixels,
            "protected_pixels": self.protected_pixels,
            "unchanged_pixels": self.unchanged_pixels,
            "changed_pixels_known": self.transition_comparison_performed,
            "changed_fraction": (
                self.changed_pixels / pixel_total
                if self.changed_pixels is not None
                else None
            ),
            "protected_fraction": self.protected_pixels / pixel_total,
            "neighbor_radius": self.neighbor_radius,
            "max_neighbor_radius": MAX_NEIGHBOR_RADIUS,
            "bounding_box": list(self.bounding_box) if self.bounding_box is not None else None,
            "logical_half_regions": [region.to_dict() for region in self.logical_half_regions],
            "physical_mapping_supplied": self.physical_mapping_supplied,
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
        raise PartialUpdateContractError("two packed logical halves require width divisible by 4")


def _validated_frame(
    frame: bytes | bytearray | memoryview, width: int, height: int, label: str
) -> memoryview:
    try:
        return validate_frame(frame, width, height)
    except FrameContractError as error:
        raise PartialUpdateContractError(f"{label}: {error}") from error


def _validate_hash(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 0xFFFFFFFF:
        raise PartialUpdateContractError("last_success_frame_fnv1a must be a 32-bit unsigned integer")
    return value


def _validated_mappings(
    mappings: Optional[Sequence[ControllerMapping]],
) -> Optional[Tuple[ControllerMapping, ControllerMapping]]:
    if mappings is None:
        return None
    try:
        frozen = tuple(mappings)
    except TypeError as error:
        raise PartialUpdateContractError(
            "frozen_controller_mappings must contain two ControllerMapping objects"
        ) from error
    if len(frozen) != 2 or any(not isinstance(mapping, ControllerMapping) for mapping in frozen):
        raise PartialUpdateContractError(
            "frozen_controller_mappings must contain two ControllerMapping objects"
        )
    if {mapping.source_half for mapping in frozen} != {0, 1}:
        raise PartialUpdateContractError(
            "frozen_controller_mappings must route logical halves 0 and 1 exactly once"
        )
    return frozen[0], frozen[1]


def _pixel(view: memoryview, row_bytes: int, x: int, y: int) -> int:
    value = view[y * row_bytes + x // 2]
    return value & 0xF if x & 1 else value >> 4


def _dilate_cardinal(mask: bytearray, width: int, height: int, radius: int) -> bytearray:
    expanded = bytearray(mask)
    if radius == 0 or not expanded:
        return expanded
    # In particular, avoid radius full passes in conservative/full-change mode.
    if expanded.count(1) == width * height:
        return expanded
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
        if expanded.count(1) == width * height:
            break
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


def _physical_coordinates(
    logical_half: int,
    local_x0: int,
    global_y0: int,
    local_x1: int,
    global_y1: int,
    half_width: int,
    height: int,
    mappings: Optional[Tuple[ControllerMapping, ControllerMapping]],
) -> Tuple[
    Optional[int],
    Optional[int],
    Optional[int],
    Optional[int],
    Optional[int],
    Optional[ControllerMapping],
]:
    if mappings is None:
        return None, None, None, None, None, None
    for index, mapping in enumerate(mappings):
        if mapping.source_half != logical_half:
            continue
        physical_x0, physical_x1 = (
            (half_width - local_x1, half_width - local_x0)
            if mapping.flip_x
            else (local_x0, local_x1)
        )
        physical_y0, physical_y1 = (
            (height - global_y1, height - global_y0)
            if mapping.flip_y
            else (global_y0, global_y1)
        )
        return (
            index + 1,
            physical_x0,
            physical_y0,
            physical_x1,
            physical_y1,
            mapping,
        )
    raise PartialUpdateContractError("logical half is absent from frozen controller mappings")


def _make_region(
    logical_half: int,
    global_x0: int,
    global_y0: int,
    global_x1: int,
    global_y1: int,
    width: int,
    height: int,
    mappings: Optional[Tuple[ControllerMapping, ControllerMapping]],
) -> LogicalHalfRegion:
    half_width = width // 2
    local_x0 = global_x0 - logical_half * half_width
    local_x1 = global_x1 - logical_half * half_width
    (
        physical_controller,
        physical_local_x0,
        physical_local_y0,
        physical_local_x1,
        physical_local_y1,
        physical_mapping,
    ) = _physical_coordinates(
        logical_half,
        local_x0,
        global_y0,
        local_x1,
        global_y1,
        half_width,
        height,
        mappings,
    )
    return LogicalHalfRegion(
        logical_half=logical_half,
        global_x0=global_x0,
        global_y0=global_y0,
        global_x1=global_x1,
        global_y1=global_y1,
        logical_local_x0=local_x0,
        logical_local_x1=local_x1,
        physical_controller=physical_controller,
        physical_local_x0=physical_local_x0,
        physical_local_y0=physical_local_y0,
        physical_local_x1=physical_local_x1,
        physical_local_y1=physical_local_y1,
        physical_mapping=physical_mapping,
    )


def _full_screen_regions(
    width: int,
    height: int,
    mappings: Optional[Tuple[ControllerMapping, ControllerMapping]],
) -> Tuple[LogicalHalfRegion, LogicalHalfRegion]:
    half_width = width // 2
    return (
        _make_region(0, 0, 0, half_width, height, width, height, mappings),
        _make_region(1, half_width, 0, width, height, width, height, mappings),
    )


def _logical_half_regions(
    mask: bytearray,
    width: int,
    height: int,
    mappings: Optional[Tuple[ControllerMapping, ControllerMapping]],
) -> Tuple[LogicalHalfRegion, ...]:
    half_width = width // 2
    regions: List[LogicalHalfRegion] = []
    for logical_half in (0, 1):
        half_start = logical_half * half_width
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
            _make_region(
                logical_half,
                min_x,
                min_y,
                max_x_exclusive,
                max_y + 1,
                width,
                height,
                mappings,
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
    last_success_operation_id: Optional[str] = None,
    last_success_frame_fnv1a: Optional[int] = None,
    last_success_trusted: bool = False,
    frozen_controller_mappings: Optional[Sequence[ControllerMapping]] = None,
) -> TransitionPlan:
    """Build a conservative partial-update research plan.

    ``old_frame`` alone only records a candidate previous frame.  Pixel-level
    transitions are calculated only when all three last-success provenance
    fields are supplied, the trust flag is true, and the provenance hash
    matches the supplied old frame.  Otherwise the plan safely covers the
    complete screen and does not invent a transition histogram.

    ``frozen_controller_mappings`` is optional and must contain the mappings
    for physical controllers 1 and 2 in that order.  Without it, regions remain
    purely logical and no physical controller is named.
    """

    _validate_dimensions(width, height)
    if not isinstance(neighbor_radius, int) or isinstance(neighbor_radius, bool):
        raise PartialUpdateContractError("neighbor_radius must be an integer")
    if neighbor_radius < 0:
        raise PartialUpdateContractError("neighbor_radius cannot be negative")
    if neighbor_radius > MAX_NEIGHBOR_RADIUS:
        raise PartialUpdateContractError(
            f"neighbor_radius cannot exceed {MAX_NEIGHBOR_RADIUS} pixels"
        )
    if not isinstance(last_success_trusted, bool):
        raise PartialUpdateContractError("last_success_trusted must be a boolean")
    if last_success_operation_id is not None:
        if not isinstance(last_success_operation_id, str) or not last_success_operation_id.strip():
            raise PartialUpdateContractError(
                "last_success_operation_id must be a non-empty string when supplied"
            )
        last_success_operation_id = last_success_operation_id.strip()
    last_success_frame_fnv1a = _validate_hash(last_success_frame_fnv1a)
    mappings = _validated_mappings(frozen_controller_mappings)

    new_view = _validated_frame(new_frame, width, height, "new_frame")
    old_view = (
        _validated_frame(old_frame, width, height, "old_frame")
        if old_frame is not None
        else None
    )
    old_hash = fnv1a(old_view) if old_view is not None else None
    provenance_matches = (
        old_hash == last_success_frame_fnv1a
        if old_hash is not None and last_success_frame_fnv1a is not None
        else None
    )

    if last_success_trusted:
        if old_view is None:
            raise PartialUpdateContractError(
                "trusted last-success provenance requires old_frame"
            )
        if last_success_operation_id is None:
            raise PartialUpdateContractError(
                "trusted last-success provenance requires last_success_operation_id"
            )
        if last_success_frame_fnv1a is None:
            raise PartialUpdateContractError(
                "trusted last-success provenance requires last_success_frame_fnv1a"
            )
        if not provenance_matches:
            raise PartialUpdateContractError(
                "last_success_frame_fnv1a does not match the supplied old_frame"
            )

    transition_comparison_performed = bool(last_success_trusted and provenance_matches)
    pixel_total = width * height
    new_hash = fnv1a(new_view)

    # Unknown or untrusted panel state: do not spend time constructing/dilating
    # an all-one mask, and do not derive transitions from a merely present file.
    if not transition_comparison_performed:
        return TransitionPlan(
            width=width,
            height=height,
            old_frame_supplied=old_view is not None,
            supplied_old_frame_fnv1a=old_hash,
            last_success_operation_id=last_success_operation_id,
            last_success_frame_fnv1a=last_success_frame_fnv1a,
            last_success_trusted=last_success_trusted,
            last_success_matches_old_frame=provenance_matches,
            transition_comparison_performed=False,
            new_frame_fnv1a=new_hash,
            changed_pixels=None,
            protected_pixels=pixel_total,
            unchanged_pixels=None,
            neighbor_radius=neighbor_radius,
            bounding_box=(0, 0, width, height),
            logical_half_regions=_full_screen_regions(width, height, mappings),
            physical_mapping_supplied=mappings is not None,
            transition_histogram=None,
        )

    # Provenance checks above guarantee old_view is present here.
    assert old_view is not None
    row_bytes = width // 2
    changed_mask = bytearray(pixel_total)
    histogram = [[0 for _ in COLOR_CODES] for _ in COLOR_CODES]
    changed_pixels = 0
    for y in range(height):
        for x in range(width):
            old_color = _pixel(old_view, row_bytes, x, y)
            new_color = _pixel(new_view, row_bytes, x, y)
            histogram[_COLOR_INDEX[old_color]][_COLOR_INDEX[new_color]] += 1
            if old_color != new_color:
                changed_mask[y * width + x] = 1
                changed_pixels += 1

    # A full-change transition is common in diagnostics.  Bypass up to 32
    # redundant dilation and region-scan passes.
    if changed_pixels == pixel_total:
        protected_pixels = pixel_total
        bounding_box: Optional[Tuple[int, int, int, int]] = (0, 0, width, height)
        regions: Tuple[LogicalHalfRegion, ...] = _full_screen_regions(width, height, mappings)
    else:
        protected_mask = _dilate_cardinal(changed_mask, width, height, neighbor_radius)
        protected_pixels = sum(protected_mask)
        bounding_box = _bounding_box(protected_mask, width, height)
        regions = _logical_half_regions(protected_mask, width, height, mappings)

    return TransitionPlan(
        width=width,
        height=height,
        old_frame_supplied=True,
        supplied_old_frame_fnv1a=old_hash,
        last_success_operation_id=last_success_operation_id,
        last_success_frame_fnv1a=last_success_frame_fnv1a,
        last_success_trusted=True,
        last_success_matches_old_frame=True,
        transition_comparison_performed=True,
        new_frame_fnv1a=new_hash,
        changed_pixels=changed_pixels,
        protected_pixels=protected_pixels,
        unchanged_pixels=pixel_total - changed_pixels,
        neighbor_radius=neighbor_radius,
        bounding_box=bounding_box,
        logical_half_regions=regions,
        physical_mapping_supplied=mappings is not None,
        transition_histogram=tuple(tuple(row) for row in histogram),
    )
