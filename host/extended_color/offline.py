"""Deterministic, offline-only fixtures for MF-1750 colour research.

This module deliberately has no device, HTTP, serial, GPIO, or firmware
dependencies.  Known-colour frames continue through the public six-colour
``host.epd_frame`` contract.  The two unknown-code fixtures are constructed
and verified only by the fixed-layout functions in this module; they are not
accepted by the public frame contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence, Tuple, Union

from host.epd_frame import (
    FRAME_BYTES,
    HEIGHT,
    PHYSICAL_COLOR_CODES,
    ROW_BYTES,
    WIDTH,
    ControllerMapping,
    FrameContractError,
    controller_stream,
    fnv1a,
    pixel_counts,
    validate_frame,
)
from host.epd_frame.core import BLACK, BLUE, GREEN, RED, WHITE, YELLOW


COLOR_ORDER = (BLACK, WHITE, YELLOW, RED, BLUE, GREEN)
COLOR_NAMES = ("black", "white", "yellow", "red", "blue", "green")
COLOR_NAME_BY_CODE = MappingProxyType(dict(zip(COLOR_ORDER, COLOR_NAMES)))
COLOR_CODE_BY_NAME = MappingProxyType(dict(zip(COLOR_NAMES, COLOR_ORDER)))

CONTROLLER_WIDTH = WIDTH // 2
PANEL_PIXELS = WIDTH * HEIGHT
DEFAULT_CONTROLLER_MAPPINGS = (ControllerMapping(0), ControllerMapping(1))

TRANSITION_BANDS = len(COLOR_ORDER)
TRANSITION_MEASUREMENT_SIZE = 64

UNKNOWN_CODES = (0x4, 0x7)
UNKNOWN_ROI_SIZE = 64
UNKNOWN_GUARD_BAND = 32
UNKNOWN_TOTAL_PIXELS = 2 * UNKNOWN_ROI_SIZE * UNKNOWN_ROI_SIZE
UNKNOWN_AREA_FRACTION = UNKNOWN_TOTAL_PIXELS / PANEL_PIXELS

PATTERN_NAMES = (
    "solid-black",
    "solid-white",
    "solid-yellow",
    "solid-red",
    "solid-blue",
    "solid-green",
    "blocks-horizontal",
    "blocks-vertical-mirrored",
    "transition-initial",
    "transition-target",
    "unknown-0x4",
    "unknown-0x7",
)

_TOKEN_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,47})\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class ExtendedColorContractError(ValueError):
    """Raised when an offline research artifact violates its frozen contract."""


@dataclass(frozen=True)
class Rectangle:
    """Half-open pixel rectangle in canonical full-frame coordinates."""

    x0: int
    y0: int
    x1: int
    y1: int

    def __post_init__(self) -> None:
        for name in ("x0", "y0", "x1", "y1"):
            if type(getattr(self, name)) is not int:
                raise ExtendedColorContractError(f"rectangle {name} must be an integer")
        if not (0 <= self.x0 < self.x1 <= WIDTH):
            raise ExtendedColorContractError("rectangle x coordinates are outside the panel")
        if not (0 <= self.y0 < self.y1 <= HEIGHT):
            raise ExtendedColorContractError("rectangle y coordinates are outside the panel")

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    @property
    def pixels(self) -> int:
        return self.width * self.height

    def translated(self, dx: int, dy: int = 0) -> "Rectangle":
        if type(dx) is not int or type(dy) is not int:
            raise ExtendedColorContractError("rectangle translation must use integers")
        return Rectangle(self.x0 + dx, self.y0 + dy, self.x1 + dx, self.y1 + dy)

    def to_dict(self) -> dict[str, int]:
        return {
            "x0": self.x0,
            "y0": self.y0,
            "x1": self.x1,
            "y1": self.y1,
            "width": self.width,
            "height": self.height,
            "pixels": self.pixels,
        }


@dataclass(frozen=True)
class TransitionROI:
    """One measurement ROI for an old-colour to new-colour transition."""

    roi_id: str
    controller: str
    logical_half: int
    old_code: int
    target_code: int
    cell: Rectangle
    measurement: Rectangle

    def to_dict(self) -> dict[str, Any]:
        return {
            "roi_id": self.roi_id,
            "controller": self.controller,
            "logical_half": self.logical_half,
            "old_code": self.old_code,
            "old_color": COLOR_NAME_BY_CODE[self.old_code],
            "target_code": self.target_code,
            "target_color": COLOR_NAME_BY_CODE[self.target_code],
            "cell": self.cell.to_dict(),
            "measurement": self.measurement.to_dict(),
        }


@dataclass(frozen=True)
class UnknownProbeROI:
    """One fixed unknown-code ROI and its known-white guard band."""

    roi_id: str
    controller: str
    logical_half: int
    unknown_code: int
    measurement: Rectangle
    guard_outer: Rectangle

    def to_dict(self) -> dict[str, Any]:
        return {
            "roi_id": self.roi_id,
            "controller": self.controller,
            "logical_half": self.logical_half,
            "unknown_code": self.unknown_code,
            "measurement": self.measurement.to_dict(),
            "guard_band_pixels": UNKNOWN_GUARD_BAND,
            "guard_outer": self.guard_outer.to_dict(),
            "guard_fill_code": WHITE,
            "guard_fill_color": COLOR_NAME_BY_CODE[WHITE],
        }


@dataclass(frozen=True)
class ControllerIdentity:
    controller: str
    mapping: ControllerMapping
    dtm_bytes: int
    dtm_sha256: str
    dtm_fnv1a: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "controller": self.controller,
            "mapping": _mapping_dict(self.mapping),
            "dtm_bytes": self.dtm_bytes,
            "dtm_sha256": self.dtm_sha256,
            "dtm_fnv1a": self.dtm_fnv1a,
            "dtm_fnv1a_hex": f"0x{self.dtm_fnv1a:08X}",
        }


@dataclass(frozen=True)
class FrameIdentity:
    frame_bytes: int
    frame_sha256: str
    frame_fnv1a: int
    controllers: Tuple[ControllerIdentity, ControllerIdentity]
    canonical_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": WIDTH,
            "height": HEIGHT,
            "bits_per_pixel": 4,
            "frame_bytes": self.frame_bytes,
            "frame_sha256": self.frame_sha256,
            "frame_fnv1a": self.frame_fnv1a,
            "frame_fnv1a_hex": f"0x{self.frame_fnv1a:08X}",
            "controllers": [controller.to_dict() for controller in self.controllers],
            "canonical_sha256": self.canonical_sha256,
            "canonical_sha256_scope": (
                "canonical JSON of frame byte/hash fields and ordered CS1/CS2 DTM identities"
            ),
        }


ROI = Union[TransitionROI, UnknownProbeROI]


@dataclass(frozen=True)
class OfflineFrameArtifact:
    """Immutable generated frame plus a reproducible machine report."""

    pattern: str
    stage: str
    case: str
    repetition: int
    frame: bytes
    identity: FrameIdentity
    formal_api_compatible: bool
    rois: Tuple[ROI, ...] = ()
    matrix_role: Optional[str] = None
    matrix_old_order: Optional[Tuple[int, ...]] = None
    matrix_target_order: Optional[Tuple[int, ...]] = None
    unknown_code: Optional[int] = None

    @property
    def test_id(self) -> str:
        return deterministic_test_id(
            self.stage,
            self.case,
            self.repetition,
            self.identity.canonical_sha256,
        )

    def report(self) -> dict[str, Any]:
        report: dict[str, Any] = {
            "schema_version": 1,
            "kind": "mf1750-extended-color-offline-frame",
            "pattern": self.pattern,
            "test_id": self.test_id,
            "stage": self.stage,
            "case": self.case,
            "repetition": self.repetition,
            "hardware_tested": False,
            "offline_only": True,
            "device_io_performed": False,
            "network_io_performed": False,
            "dimensions": {
                "width": WIDTH,
                "height": HEIGHT,
                "bits_per_pixel": 4,
                "packed_bytes": FRAME_BYTES,
            },
            "physical_color_codes": list(COLOR_ORDER),
            "identity": self.identity.to_dict(),
            "safety": {
                "formal_api_compatible": self.formal_api_compatible,
                "production_color_guard_changed": False,
                "device_refresh_capability": False,
                "automatic_retry_capability": False,
            },
            "rois": [roi.to_dict() for roi in self.rois],
        }
        if self.matrix_role is not None:
            if self.matrix_old_order is None or self.matrix_target_order is None:
                raise ExtendedColorContractError("matrix artifact is missing its color orders")
            report["transition_matrix"] = {
                "role": self.matrix_role,
                "sequence": ["transition-initial", "transition-target"],
                "color_codes": list(COLOR_ORDER),
                "color_names": list(COLOR_NAMES),
                "old_axis": "horizontal",
                "target_axis": "vertical-mirrored-about-panel-centerline",
                "mirrored_controller_halves": True,
                "transition_rois_per_controller": TRANSITION_BANDS**2,
                "old_order_top_to_bottom": list(self.matrix_old_order),
                "old_order_names_top_to_bottom": [
                    COLOR_NAME_BY_CODE[code] for code in self.matrix_old_order
                ],
                "target_order_cs1_left_to_right": list(self.matrix_target_order),
                "target_order_names_cs1_left_to_right": [
                    COLOR_NAME_BY_CODE[code] for code in self.matrix_target_order
                ],
                "target_order_cs2_left_to_right": list(reversed(self.matrix_target_order)),
                "target_order_names_cs2_left_to_right": [
                    COLOR_NAME_BY_CODE[code] for code in reversed(self.matrix_target_order)
                ],
            }
        if self.unknown_code is not None:
            report["unknown_probe"] = {
                "code": self.unknown_code,
                "allowed_experimental_codes": list(UNKNOWN_CODES),
                "background_code": WHITE,
                "background_color": COLOR_NAME_BY_CODE[WHITE],
                "unknown_pixels": UNKNOWN_TOTAL_PIXELS,
                "unknown_area_fraction": UNKNOWN_AREA_FRACTION,
                "unknown_area_percent": UNKNOWN_AREA_FRACTION * 100.0,
                "fixed_layout_verified": True,
                "release_build_enabled": False,
                "arbitrary_raw_unknown_frame_accepted": False,
            }
        return report


@dataclass(frozen=True)
class TransitionMatrixFrames:
    repetition: int
    old_order: Tuple[int, ...]
    target_order: Tuple[int, ...]
    initial: bytes
    target: bytes
    rois: Tuple[TransitionROI, ...]


def _mapping_dict(mapping: ControllerMapping) -> dict[str, Union[int, bool]]:
    return {
        "source_half": mapping.source_half,
        "flip_x": mapping.flip_x,
        "flip_y": mapping.flip_y,
        "nibble_swap": mapping.nibble_swap,
    }


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_known_color(color: object) -> int:
    if type(color) is not int or color not in PHYSICAL_COLOR_CODES:
        raise ExtendedColorContractError(
            "color must be one of the formal physical codes 0, 1, 2, 3, 5, or 6"
        )
    return color


def _require_unknown_code(code: object) -> int:
    if type(code) is not int or code not in UNKNOWN_CODES:
        raise ExtendedColorContractError("unknown probe code must be exactly 0x4 or 0x7")
    return code


def _require_repetition(repetition: object) -> int:
    if type(repetition) is not int or not 1 <= repetition <= 999:
        raise ExtendedColorContractError("repetition must be an integer from 1 through 999")
    return repetition


def _band_index(position: int, extent: int) -> int:
    return min(TRANSITION_BANDS - 1, position * TRANSITION_BANDS // extent)


def _band_bounds(index: int, extent: int) -> tuple[int, int]:
    if type(index) is not int or not 0 <= index < TRANSITION_BANDS:
        raise ExtendedColorContractError("band index is outside the six-colour matrix")
    # These ceil-divided boundaries exactly match floor(position * 6 / extent).
    start = (index * extent + TRANSITION_BANDS - 1) // TRANSITION_BANDS
    end = ((index + 1) * extent + TRANSITION_BANDS - 1) // TRANSITION_BANDS
    return start, end


def transition_color_orders(repetition: int = 1) -> Tuple[Tuple[int, ...], Tuple[int, ...]]:
    """Return the old and target band orders for one deterministic matrix round."""

    repeat = _require_repetition(repetition)
    offset = (repeat - 1) % TRANSITION_BANDS
    old_order = tuple(
        COLOR_ORDER[(position + offset) % TRANSITION_BANDS]
        for position in range(TRANSITION_BANDS)
    )
    target_order = tuple(
        COLOR_ORDER[(position - offset) % TRANSITION_BANDS]
        for position in range(TRANSITION_BANDS)
    )
    return old_order, target_order


@lru_cache(maxsize=None)
def generate_solid_frame(color: int) -> bytes:
    """Return one canonical full-screen frame containing a formal colour."""

    code = _require_known_color(color)
    frame = bytes(((code << 4) | code,)) * FRAME_BYTES
    validate_frame(frame)
    return frame


@lru_cache(maxsize=None)
def _generate_banded_frame(orientation: str, order: Tuple[int, ...]) -> bytes:
    if orientation not in ("horizontal", "vertical-mirrored"):
        raise ExtendedColorContractError(
            "block orientation must be 'horizontal' or 'vertical-mirrored'"
        )
    if len(order) != TRANSITION_BANDS or set(order) != set(COLOR_ORDER):
        raise ExtendedColorContractError("band order must be a permutation of six colors")
    output = bytearray(FRAME_BYTES)
    if orientation == "horizontal":
        for y in range(HEIGHT):
            code = order[_band_index(y, HEIGHT)]
            value = (code << 4) | code
            row_start = y * ROW_BYTES
            output[row_start : row_start + ROW_BYTES] = bytes((value,)) * ROW_BYTES
    else:
        row = bytearray(ROW_BYTES)
        for byte_x in range(ROW_BYTES):
            x = byte_x * 2
            high_local_x = x if x < CONTROLLER_WIDTH else WIDTH - 1 - x
            low_x = x + 1
            low_local_x = low_x if low_x < CONTROLLER_WIDTH else WIDTH - 1 - low_x
            high = order[_band_index(high_local_x, CONTROLLER_WIDTH)]
            low = order[_band_index(low_local_x, CONTROLLER_WIDTH)]
            row[byte_x] = (high << 4) | low
        for y in range(HEIGHT):
            row_start = y * ROW_BYTES
            output[row_start : row_start + ROW_BYTES] = row
    frame = bytes(output)
    validate_frame(frame)
    return frame


def generate_large_blocks_frame(orientation: str) -> bytes:
    """Return six large bands; vertical bands are true centerline mirrors."""

    return _generate_banded_frame(orientation, COLOR_ORDER)


@lru_cache(maxsize=None)
def transition_rois(repetition: int = 1) -> Tuple[TransitionROI, ...]:
    """Return the frozen 72-entry machine-readable matrix ROI list."""

    old_order, target_order = transition_color_orders(repetition)
    result = []
    for logical_half, controller in enumerate(("CS1", "CS2")):
        for old_index, old_code in enumerate(old_order):
            y0, y1 = _band_bounds(old_index, HEIGHT)
            for target_index, target_code in enumerate(target_order):
                local_x0, local_x1 = _band_bounds(target_index, CONTROLLER_WIDTH)
                left_cell = Rectangle(local_x0, y0, local_x1, y1)
                left_measurement_x0 = (
                    left_cell.x0 + (left_cell.width - TRANSITION_MEASUREMENT_SIZE) // 2
                )
                measurement_y0 = (
                    left_cell.y0 + (left_cell.height - TRANSITION_MEASUREMENT_SIZE) // 2
                )
                left_measurement = Rectangle(
                    left_measurement_x0,
                    measurement_y0,
                    left_measurement_x0 + TRANSITION_MEASUREMENT_SIZE,
                    measurement_y0 + TRANSITION_MEASUREMENT_SIZE,
                )
                if logical_half == 0:
                    cell = left_cell
                    measurement = left_measurement
                else:
                    cell = Rectangle(WIDTH - left_cell.x1, y0, WIDTH - left_cell.x0, y1)
                    measurement = Rectangle(
                        WIDTH - left_measurement.x1,
                        left_measurement.y0,
                        WIDTH - left_measurement.x0,
                        left_measurement.y1,
                    )
                result.append(
                    TransitionROI(
                        roi_id=(
                            f"ec4-{controller.lower()}-"
                            f"{COLOR_NAME_BY_CODE[old_code]}-to-"
                            f"{COLOR_NAME_BY_CODE[target_code]}"
                        ),
                        controller=controller,
                        logical_half=logical_half,
                        old_code=old_code,
                        target_code=target_code,
                        cell=cell,
                        measurement=measurement,
                    )
                )
    return tuple(result)


@lru_cache(maxsize=None)
def generate_transition_matrix_frames(repetition: int = 1) -> TransitionMatrixFrames:
    """Return old-horizontal and new-vertical frames covering all 36 transitions."""

    repeat = _require_repetition(repetition)
    old_order, target_order = transition_color_orders(repeat)
    return TransitionMatrixFrames(
        repetition=repeat,
        old_order=old_order,
        target_order=target_order,
        initial=_generate_banded_frame("horizontal", old_order),
        target=_generate_banded_frame("vertical-mirrored", target_order),
        rois=transition_rois(repeat),
    )


@lru_cache(maxsize=None)
def unknown_probe_rois(code: int) -> Tuple[UnknownProbeROI, UnknownProbeROI]:
    """Return the two fixed, corresponding 64x64 unknown-code ROIs."""

    unknown = _require_unknown_code(code)
    left_measurement = Rectangle(224, 268, 288, 332)
    left_guard = Rectangle(
        left_measurement.x0 - UNKNOWN_GUARD_BAND,
        left_measurement.y0 - UNKNOWN_GUARD_BAND,
        left_measurement.x1 + UNKNOWN_GUARD_BAND,
        left_measurement.y1 + UNKNOWN_GUARD_BAND,
    )
    right_measurement = left_measurement.translated(CONTROLLER_WIDTH)
    right_guard = left_guard.translated(CONTROLLER_WIDTH)
    return (
        UnknownProbeROI("ec5-cs1-unknown", "CS1", 0, unknown, left_measurement, left_guard),
        UnknownProbeROI("ec5-cs2-unknown", "CS2", 1, unknown, right_measurement, right_guard),
    )


@lru_cache(maxsize=None)
def generate_unknown_probe_frame(code: int) -> bytes:
    """Generate only the fixed white-background 0x4 or 0x7 design fixture."""

    unknown = _require_unknown_code(code)
    frame = bytearray(bytes((0x11,)) * FRAME_BYTES)
    unknown_byte = bytes((((unknown << 4) | unknown),))
    for roi in unknown_probe_rois(unknown):
        rectangle = roi.measurement
        if rectangle.x0 % 2 or rectangle.x1 % 2:
            raise ExtendedColorContractError("unknown ROI must remain byte aligned")
        for y in range(rectangle.y0, rectangle.y1):
            start = y * ROW_BYTES + rectangle.x0 // 2
            end = y * ROW_BYTES + rectangle.x1 // 2
            frame[start:end] = unknown_byte * (end - start)
    result = bytes(frame)
    validate_frame(result, allowed_colors=(*COLOR_ORDER, unknown))
    return result


def validate_unknown_probe_frame(frame: bytes, code: int) -> memoryview:
    """Accept an unknown-code frame only when it exactly matches the fixed fixture."""

    unknown = _require_unknown_code(code)
    try:
        view = validate_frame(frame, allowed_colors=(*COLOR_ORDER, unknown))
    except FrameContractError as error:
        raise ExtendedColorContractError(f"unknown probe frame is invalid: {error}") from error
    if bytes(view) != generate_unknown_probe_frame(unknown):
        raise ExtendedColorContractError("unknown probe frame does not match the fixed layout")
    return view


def _build_frame_identity(frame: bytes, allowed_codes: Sequence[int]) -> FrameIdentity:
    try:
        view = validate_frame(frame, allowed_colors=allowed_codes)
    except FrameContractError as error:
        raise ExtendedColorContractError(f"frame identity input is invalid: {error}") from error
    canonical_frame = bytes(view)
    frame_document: dict[str, Any] = {
        "frame_bytes": len(canonical_frame),
        "frame_sha256": _sha256(canonical_frame),
        "frame_fnv1a": fnv1a(canonical_frame),
        "controllers": [],
    }
    controller_identities = []
    for index, mapping in enumerate(DEFAULT_CONTROLLER_MAPPINGS, start=1):
        stream = controller_stream(
            canonical_frame,
            mapping,
            allowed_colors=allowed_codes,
        )
        identity = ControllerIdentity(
            controller=f"CS{index}",
            mapping=mapping,
            dtm_bytes=len(stream),
            dtm_sha256=_sha256(stream),
            dtm_fnv1a=fnv1a(stream),
        )
        controller_identities.append(identity)
        frame_document["controllers"].append(identity.to_dict())
    canonical_sha256 = _sha256(_canonical_json(frame_document))
    return FrameIdentity(
        frame_bytes=len(canonical_frame),
        frame_sha256=frame_document["frame_sha256"],
        frame_fnv1a=frame_document["frame_fnv1a"],
        controllers=(controller_identities[0], controller_identities[1]),
        canonical_sha256=canonical_sha256,
    )


def frame_identity(frame: bytes) -> FrameIdentity:
    """Build an identity only for a frame accepted by the formal six-colour guard."""

    return _build_frame_identity(frame, COLOR_ORDER)


def deterministic_test_id(
    stage: str,
    case: str,
    repetition: int,
    identity_sha256: str,
) -> str:
    """Return a stable experiment ID derived solely from explicit inputs."""

    if not isinstance(stage, str) or _TOKEN_RE.fullmatch(stage) is None:
        raise ExtendedColorContractError("stage must be a 1..48 character ASCII token")
    if not isinstance(case, str) or _TOKEN_RE.fullmatch(case) is None:
        raise ExtendedColorContractError("case must be a 1..48 character ASCII token")
    repeat = _require_repetition(repetition)
    if not isinstance(identity_sha256, str) or _SHA256_RE.fullmatch(identity_sha256) is None:
        raise ExtendedColorContractError("identity_sha256 must be 64 lowercase hex digits")
    seed = {
        "schema": "mf1750-deterministic-test-id-v1",
        "stage": stage.upper(),
        "case": case.upper(),
        "repetition": repeat,
        "identity_sha256": identity_sha256,
    }
    suffix = _sha256(_canonical_json(seed))[:12].upper()
    return f"MF1750-{stage.upper()}-{case.upper()}-R{repeat:03d}-{suffix}"


@lru_cache(maxsize=None)
def build_artifact(pattern: str, repetition: int = 1) -> OfflineFrameArtifact:
    """Generate one named offline artifact without filesystem or device I/O."""

    repeat = _require_repetition(repetition)
    if not isinstance(pattern, str) or pattern not in PATTERN_NAMES:
        raise ExtendedColorContractError(
            f"unknown pattern {pattern!r}; choose one of {PATTERN_NAMES}"
        )

    if pattern.startswith("solid-"):
        name = pattern.removeprefix("solid-")
        frame = generate_solid_frame(COLOR_CODE_BY_NAME[name])
        return OfflineFrameArtifact(
            pattern,
            "EC2",
            pattern,
            repeat,
            frame,
            frame_identity(frame),
            True,
        )

    if pattern == "blocks-horizontal":
        frame = generate_large_blocks_frame("horizontal")
        return OfflineFrameArtifact(
            pattern,
            "EC2",
            pattern,
            repeat,
            frame,
            frame_identity(frame),
            True,
        )

    if pattern == "blocks-vertical-mirrored":
        frame = generate_large_blocks_frame("vertical-mirrored")
        return OfflineFrameArtifact(
            pattern,
            "EC2",
            pattern,
            repeat,
            frame,
            frame_identity(frame),
            True,
        )

    if pattern in ("transition-initial", "transition-target"):
        matrix = generate_transition_matrix_frames(repeat)
        role = "initial-old-horizontal" if pattern == "transition-initial" else "target-new-vertical"
        frame = matrix.initial if pattern == "transition-initial" else matrix.target
        return OfflineFrameArtifact(
            pattern,
            "EC4",
            pattern,
            repeat,
            frame,
            frame_identity(frame),
            True,
            rois=matrix.rois,
            matrix_role=role,
            matrix_old_order=matrix.old_order,
            matrix_target_order=matrix.target_order,
        )

    unknown = 0x4 if pattern == "unknown-0x4" else 0x7
    frame = generate_unknown_probe_frame(unknown)
    validate_unknown_probe_frame(frame, unknown)
    identity = _build_frame_identity(frame, (*COLOR_ORDER, unknown))
    return OfflineFrameArtifact(
        pattern,
        "EC5-DESIGN",
        pattern,
        repeat,
        frame,
        identity,
        False,
        rois=unknown_probe_rois(unknown),
        unknown_code=unknown,
    )


def known_pixel_counts(frame: bytes) -> Tuple[int, ...]:
    """Expose strict six-colour counts without weakening the shared core guard."""

    try:
        return pixel_counts(frame)
    except FrameContractError as error:
        raise ExtendedColorContractError(f"known-colour frame is invalid: {error}") from error
