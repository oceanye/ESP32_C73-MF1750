"""Fixed host-only factory-OTP 8x8 old-to-new transition fixtures.

The two packed frames produced here use the panel's existing factory OTP
profile.  ``primer`` places the old transport code on matrix rows and
``target`` places the new transport code on matrix columns.  This module does
not load, select, scale, or otherwise modify a runtime LUT or waveform, and it
contains no device, network, serial, GPIO, or refresh path.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
from typing import Literal

from host.epd_frame import (
    CONTROLLER_FRAME_BYTES,
    FRAME_BYTES,
    HEIGHT,
    ROW_BYTES,
    WIDTH,
    ControllerMapping,
    controller_stream as _mapped_controller_stream,
    fnv1a,
    validate_frame,
)


CLASSIFICATION = "FACTORY_OTP_TRANSPORT_CODE_FIXTURE_OFFLINE_ONLY"
PROFILE_SOURCE = "factory_otp"
CUSTOM_LUT_OR_WAVEFORM = False
HARDWARE_EXECUTION_AUTHORIZED = False

ROLES = ("primer", "target")
TRANSPORT_CODES = tuple(range(8))
BACKGROUND_CODE = 1
CONTROLLER_WIDTH = WIDTH // 2
GRID_X0_LOCAL = 32
GRID_X1_LOCAL = 480
GRID_Y0 = 44
GRID_Y1 = 556
GRID_COLUMNS = 8
GRID_ROWS = 8
CELL_WIDTH = 56
CELL_HEIGHT = 64


class OtpTransitionMatrixError(ValueError):
    """Raised when the fixed offline fixture contract is violated."""


@dataclass(frozen=True)
class TransitionROI:
    """One semantic old/new pair and its fixed full-panel rectangle."""

    roi_id: str
    controller: Literal["CS1", "CS2"]
    source_half: int
    old_code: int
    new_code: int
    display_row: int
    display_column: int
    x: int
    y: int
    width: int = CELL_WIDTH
    height: int = CELL_HEIGHT

    @property
    def x1_exclusive(self) -> int:
        return self.x + self.width

    @property
    def y1_exclusive(self) -> int:
        return self.y + self.height


@dataclass(frozen=True)
class PayloadIdentity:
    """Byte identity for a complete frame or one controller DTM stream."""

    byte_count: int
    sha256: str
    fnv1a_u32: int


@dataclass(frozen=True)
class FrameIdentity:
    """Full-frame identity and ordered CS1/CS2 DTM identities."""

    role: Literal["primer", "target"]
    frame: PayloadIdentity
    cs1_dtm: PayloadIdentity
    cs2_dtm: PayloadIdentity


def _role(value: object) -> Literal["primer", "target"]:
    if value not in ROLES:
        raise OtpTransitionMatrixError("role must be 'primer' or 'target'")
    return value  # type: ignore[return-value]


def _half(value: object) -> int:
    if type(value) is not int or value not in (0, 1):
        raise OtpTransitionMatrixError("controller half must be integer 0 or 1")
    return value


def _payload_identity(payload: bytes) -> PayloadIdentity:
    return PayloadIdentity(
        byte_count=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        fnv1a_u32=fnv1a(payload),
    )


@lru_cache(maxsize=1)
def transition_rois() -> tuple[TransitionROI, ...]:
    """Return all 64 old/new pairs per controller.

    CS1 uses increasing old/new display axes.  CS2 is reversed vertically and
    horizontally, so corresponding semantic pairs occupy counterbalanced
    positions across the controller boundary.
    """

    rois: list[TransitionROI] = []
    for source_half, controller in enumerate(("CS1", "CS2")):
        reverse = controller == "CS2"
        x_offset = source_half * CONTROLLER_WIDTH
        for old_code in TRANSPORT_CODES:
            for new_code in TRANSPORT_CODES:
                display_row = 7 - old_code if reverse else old_code
                display_column = 7 - new_code if reverse else new_code
                rois.append(
                    TransitionROI(
                        roi_id=(
                            f"factory-otp-{controller.lower()}-"
                            f"old{old_code}-new{new_code}"
                        ),
                        controller=controller,
                        source_half=source_half,
                        old_code=old_code,
                        new_code=new_code,
                        display_row=display_row,
                        display_column=display_column,
                        x=x_offset + GRID_X0_LOCAL + display_column * CELL_WIDTH,
                        y=GRID_Y0 + display_row * CELL_HEIGHT,
                    )
                )
    return tuple(rois)


def _fill_rectangle(frame: bytearray, roi: TransitionROI, code: int) -> None:
    if roi.x % 2 or roi.width % 2:
        raise OtpTransitionMatrixError("ROI must remain byte aligned")
    pair = bytes(((code << 4) | code,))
    row_payload = pair * (roi.width // 2)
    for y in range(roi.y, roi.y1_exclusive):
        start = y * ROW_BYTES + roi.x // 2
        frame[start : start + len(row_payload)] = row_payload


@lru_cache(maxsize=len(ROLES))
def build_frame(role: str) -> bytes:
    """Build one complete packed factory-OTP primer or target frame."""

    checked_role = _role(role)
    frame = bytearray(bytes(((BACKGROUND_CODE << 4) | BACKGROUND_CODE,)) * FRAME_BYTES)
    for roi in transition_rois():
        _fill_rectangle(
            frame,
            roi,
            roi.old_code if checked_role == "primer" else roi.new_code,
        )
    result = bytes(frame)
    validate_frame(result, allowed_colors=TRANSPORT_CODES)
    return result


def controller_stream(frame: bytes, half: int) -> bytes:
    """Return one MAP_ORIENT_V1 DTM stream for the fixed eight-code fixture."""

    checked_half = _half(half)
    validated = bytes(validate_frame(frame, allowed_colors=TRANSPORT_CODES))
    stream = _mapped_controller_stream(
        validated,
        ControllerMapping(source_half=checked_half),
        allowed_colors=TRANSPORT_CODES,
    )
    if len(stream) != CONTROLLER_FRAME_BYTES:
        raise OtpTransitionMatrixError("controller DTM byte count differs")
    return stream


@lru_cache(maxsize=len(ROLES))
def frame_identity(role: str) -> FrameIdentity:
    """Return full-frame and CS1/CS2 DTM identities for one fixed role."""

    checked_role = _role(role)
    frame = build_frame(checked_role)
    return FrameIdentity(
        role=checked_role,
        frame=_payload_identity(frame),
        cs1_dtm=_payload_identity(controller_stream(frame, 0)),
        cs2_dtm=_payload_identity(controller_stream(frame, 1)),
    )


def pixel_code(frame: bytes, x: int, y: int) -> int:
    """Read one packed code for deterministic fixture inspection."""

    if len(frame) != FRAME_BYTES:
        raise OtpTransitionMatrixError("frame byte count differs")
    if (
        type(x) is not int
        or type(y) is not int
        or not (0 <= x < WIDTH and 0 <= y < HEIGHT)
    ):
        raise OtpTransitionMatrixError("pixel coordinate is outside the panel")
    value = frame[y * ROW_BYTES + x // 2]
    return value & 0x0F if x & 1 else value >> 4


if GRID_X1_LOCAL - GRID_X0_LOCAL != GRID_COLUMNS * CELL_WIDTH:
    raise RuntimeError("factory-OTP transition grid width contract differs")
if GRID_Y1 - GRID_Y0 != GRID_ROWS * CELL_HEIGHT:
    raise RuntimeError("factory-OTP transition grid height contract differs")

