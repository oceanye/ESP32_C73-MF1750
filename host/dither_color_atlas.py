"""Fixed, offline-only rectangular dither colour atlas for the EC5 panel.

The atlas reproduces the simple spatial-mixing experiment described by
MyEmbeddedStuff for Spectra 6 displays.  Each row is one pair of already
verified native factory-OTP colours.  Its five columns are pure A, 75/25,
50/50, 25/75, and pure B.  The 50/50 patch is the exact one-pixel A/B
checkerboard from the article; the quarter steps use the same deterministic
2x2 Bayer threshold tile.

Both 512-pixel controller halves contain the same semantic layout, pattern
phase, and pixel recipes.  The module contains no device, network, serial,
GPIO, refresh, LUT, waveform, voltage, or timing path.  Candidate names such
as ``purple`` are hypotheses for operator comparison, not measured colours.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from typing import Literal

from host.epd_frame import (
    CONTROLLER_FRAME_BYTES,
    CONTROLLER_WIDTH,
    FRAME_BYTES,
    HEIGHT,
    PHYSICAL_COLOR_CODES,
    ROW_BYTES,
    WIDTH,
    ControllerMapping,
    controller_stream as _mapped_controller_stream,
    fnv1a,
    pixel_counts,
    validate_frame,
)


CLASSIFICATION = "FACTORY_OTP_SPATIAL_DITHER_ATLAS_OFFLINE_ONLY"
PROFILE_SOURCE = "factory_otp"
CUSTOM_LUT_OR_WAVEFORM = False
HARDWARE_EXECUTION_AUTHORIZED = False
SPATIAL_MIXING_ONLY = True
SINGLE_PIXEL_MULTI_PIGMENT_CLAIM = False

ROLES = ("atlas", "white")
LEGAL_CODES = (0, 1, 2, 3, 5, 6)
COLOR_NAME_BY_CODE = {
    0: "black",
    1: "white",
    2: "yellow",
    3: "red",
    5: "blue",
    6: "green",
}

GRID_X0_LOCAL = 26
GRID_Y0 = 34
GRID_COLUMNS = 5
GRID_ROWS = 7
CELL_WIDTH = 84
CELL_HEIGHT = 68
COLUMN_GAP = 10
ROW_GAP = 10
GRID_X1_LOCAL = (
    GRID_X0_LOCAL + GRID_COLUMNS * CELL_WIDTH + (GRID_COLUMNS - 1) * COLUMN_GAP
)
GRID_Y1 = GRID_Y0 + GRID_ROWS * CELL_HEIGHT + (GRID_ROWS - 1) * ROW_GAP

# Threshold ranks for a deterministic 2x2 ordered mask.  With two A pixels,
# this is exactly the one-pixel checkerboard A/B; one and three A pixels are
# the corresponding quarter-area steps.
BAYER_2X2 = ((0, 2), (3, 1))


class DitherColorAtlasError(ValueError):
    """Raised when the fixed dither-atlas contract is violated."""


@dataclass(frozen=True)
class MixFamily:
    row_id: str
    appearance_hypothesis: str
    code_a: int
    code_b: int

    @property
    def color_a(self) -> str:
        return COLOR_NAME_BY_CODE[self.code_a]

    @property
    def color_b(self) -> str:
        return COLOR_NAME_BY_CODE[self.code_b]


MIX_FAMILIES = (
    MixFamily("red-yellow", "orange", 3, 2),
    MixFamily("yellow-white", "light-yellow", 2, 1),
    MixFamily("green-yellow", "lime", 6, 2),
    MixFamily("red-blue", "purple", 3, 5),
    MixFamily("red-green", "brown", 3, 6),
    MixFamily("green-blue", "cyan-or-sky-blue", 6, 5),
    MixFamily("red-white", "light-pink", 3, 1),
)


@dataclass(frozen=True)
class MixColumn:
    column_id: str
    a_quarters: int

    @property
    def b_quarters(self) -> int:
        return 4 - self.a_quarters


MIX_COLUMNS = (
    MixColumn("pure-a", 4),
    MixColumn("a75-b25", 3),
    MixColumn("a50-b50-checkerboard", 2),
    MixColumn("a25-b75", 1),
    MixColumn("pure-b", 0),
)


@dataclass(frozen=True)
class AtlasROI:
    roi_id: str
    controller: Literal["CS1", "CS2"]
    source_half: int
    display_row: int
    display_column: int
    row_id: str
    appearance_hypothesis: str
    code_a: int
    code_b: int
    a_quarters: int
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

    @property
    def b_quarters(self) -> int:
        return 4 - self.a_quarters

    @property
    def color_a(self) -> str:
        return COLOR_NAME_BY_CODE[self.code_a]

    @property
    def color_b(self) -> str:
        return COLOR_NAME_BY_CODE[self.code_b]

    @property
    def pattern(self) -> str:
        if self.a_quarters in (0, 4):
            return "solid"
        if self.a_quarters == 2:
            return "checkerboard-1px-50-50"
        return "bayer-2x2-quarter-area"

    def to_dict(self) -> dict[str, object]:
        return {
            "roi_id": self.roi_id,
            "controller": self.controller,
            "source_half": self.source_half,
            "display_row": self.display_row,
            "display_column": self.display_column,
            "row_id": self.row_id,
            "appearance_hypothesis": self.appearance_hypothesis,
            "pair": {
                "code_a": self.code_a,
                "color_a": self.color_a,
                "code_b": self.code_b,
                "color_b": self.color_b,
            },
            "recipe": {
                "a_quarters": self.a_quarters,
                "b_quarters": self.b_quarters,
                "a_fraction": self.a_quarters / 4,
                "b_fraction": self.b_quarters / 4,
                "pattern": self.pattern,
                "tile_side_pixels": 2,
                "tile_origin": "roi-top-left",
            },
            "rectangle": {
                "x": self.x,
                "y": self.y,
                "width": self.width,
                "height": self.height,
                "x1_exclusive": self.x1_exclusive,
                "y1_exclusive": self.y1_exclusive,
            },
        }


@dataclass(frozen=True)
class PayloadIdentity:
    byte_count: int
    sha256: str
    fnv1a_u32: int

    def to_dict(self) -> dict[str, object]:
        return {
            "bytes": self.byte_count,
            "sha256": self.sha256,
            "fnv1a_u32": self.fnv1a_u32,
            "fnv1a_hex": f"0x{self.fnv1a_u32:08X}",
        }


@dataclass(frozen=True)
class FrameIdentity:
    role: Literal["atlas", "white"]
    frame: PayloadIdentity
    cs1_dtm: PayloadIdentity
    cs2_dtm: PayloadIdentity
    histogram: tuple[int, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "frame": self.frame.to_dict(),
            "cs1_dtm": self.cs1_dtm.to_dict(),
            "cs2_dtm": self.cs2_dtm.to_dict(),
            "histogram_codes_0_to_7": list(self.histogram),
        }


def _role(value: object) -> Literal["atlas", "white"]:
    if value not in ROLES:
        raise DitherColorAtlasError("role must be 'atlas' or 'white'")
    return value  # type: ignore[return-value]


def _payload_identity(payload: bytes) -> PayloadIdentity:
    return PayloadIdentity(
        byte_count=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        fnv1a_u32=fnv1a(payload),
    )


@lru_cache(maxsize=1)
def atlas_rois() -> tuple[AtlasROI, ...]:
    """Return the 35 semantic patches on each identical controller half."""

    rois: list[AtlasROI] = []
    for source_half, controller in enumerate(("CS1", "CS2")):
        half_offset = source_half * CONTROLLER_WIDTH
        for row, family in enumerate(MIX_FAMILIES):
            for column, mix_column in enumerate(MIX_COLUMNS):
                rois.append(
                    AtlasROI(
                        roi_id=(
                            f"dither-{controller.lower()}-{family.row_id}-"
                            f"{mix_column.column_id}"
                        ),
                        controller=controller,  # type: ignore[arg-type]
                        source_half=source_half,
                        display_row=row,
                        display_column=column,
                        row_id=family.row_id,
                        appearance_hypothesis=family.appearance_hypothesis,
                        code_a=family.code_a,
                        code_b=family.code_b,
                        a_quarters=mix_column.a_quarters,
                        x=(
                            half_offset
                            + GRID_X0_LOCAL
                            + column * (CELL_WIDTH + COLUMN_GAP)
                        ),
                        y=GRID_Y0 + row * (CELL_HEIGHT + ROW_GAP),
                    )
                )
    return tuple(rois)


def _code_at_local(roi: AtlasROI, local_x: int, local_y: int) -> int:
    if roi.a_quarters == 4:
        return roi.code_a
    if roi.a_quarters == 0:
        return roi.code_b
    threshold = BAYER_2X2[local_y & 1][local_x & 1]
    return roi.code_a if threshold < roi.a_quarters else roi.code_b


def _fill_rectangle(frame: bytearray, roi: AtlasROI) -> None:
    if roi.x % 2 or roi.y % 2 or roi.width % 4 or roi.height % 4:
        raise DitherColorAtlasError(
            "ROI must use an even local phase and contain whole 2x2 tiles"
        )
    for local_y in range(roi.height):
        row_start = (roi.y + local_y) * ROW_BYTES + roi.x // 2
        row = bytearray(roi.width // 2)
        for byte_index in range(len(row)):
            local_x = byte_index * 2
            high = _code_at_local(roi, local_x, local_y)
            low = _code_at_local(roi, local_x + 1, local_y)
            row[byte_index] = (high << 4) | low
        frame[row_start : row_start + len(row)] = row


@lru_cache(maxsize=len(ROLES))
def build_frame(role: str) -> bytes:
    """Build one fixed atlas or all-white canonical frame."""

    checked_role = _role(role)
    frame = bytearray(b"\x11" * FRAME_BYTES)
    if checked_role == "atlas":
        for roi in atlas_rois():
            _fill_rectangle(frame, roi)
    result = bytes(frame)
    validate_frame(result)
    return result


def controller_stream(frame: bytes, half: int) -> bytes:
    if type(half) is not int or half not in (0, 1):
        raise DitherColorAtlasError("controller half must be integer 0 or 1")
    validated = bytes(validate_frame(frame))
    stream = _mapped_controller_stream(
        validated,
        ControllerMapping(source_half=half),
    )
    if len(stream) != CONTROLLER_FRAME_BYTES:
        raise DitherColorAtlasError("controller DTM byte count differs")
    return stream


@lru_cache(maxsize=len(ROLES))
def frame_identity(role: str) -> FrameIdentity:
    checked_role = _role(role)
    frame = build_frame(checked_role)
    counts = pixel_counts(frame)
    histogram = tuple(counts[code] if code < len(counts) else 0 for code in range(8))
    return FrameIdentity(
        role=checked_role,
        frame=_payload_identity(frame),
        cs1_dtm=_payload_identity(controller_stream(frame, 0)),
        cs2_dtm=_payload_identity(controller_stream(frame, 1)),
        histogram=histogram,
    )


def pixel_code(frame: bytes, x: int, y: int) -> int:
    if len(frame) != FRAME_BYTES:
        raise DitherColorAtlasError("frame byte count differs")
    if (
        type(x) is not int
        or type(y) is not int
        or not (0 <= x < WIDTH and 0 <= y < HEIGHT)
    ):
        raise DitherColorAtlasError("pixel coordinate is outside the panel")
    value = frame[y * ROW_BYTES + x // 2]
    return value & 0x0F if x & 1 else value >> 4


def layout_manifest() -> dict[str, object]:
    """Return a deterministic, self-describing offline atlas manifest."""

    identities = {role: frame_identity(role).to_dict() for role in ROLES}
    unsigned: dict[str, object] = {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-dither-color-atlas-layout",
        "classification": CLASSIFICATION,
        "dimensions": {
            "width": WIDTH,
            "height": HEIGHT,
            "bits_per_pixel": 4,
            "frame_bytes": FRAME_BYTES,
            "controller_width": CONTROLLER_WIDTH,
        },
        "profile_source": PROFILE_SOURCE,
        "runtime_lut_or_waveform_changed": CUSTOM_LUT_OR_WAVEFORM,
        "spatial_mixing_only": SPATIAL_MIXING_ONLY,
        "single_pixel_multi_pigment_claim": SINGLE_PIXEL_MULTI_PIGMENT_CLAIM,
        "hardware_tested": False,
        "hardware_execution_authorized": HARDWARE_EXECUTION_AUTHORIZED,
        "legal_codes": list(LEGAL_CODES),
        "color_names_by_code": {
            str(code): COLOR_NAME_BY_CODE[code] for code in LEGAL_CODES
        },
        "grid": {
            "rows": GRID_ROWS,
            "columns": GRID_COLUMNS,
            "cell_width": CELL_WIDTH,
            "cell_height": CELL_HEIGHT,
            "column_gap": COLUMN_GAP,
            "row_gap": ROW_GAP,
            "x0_local": GRID_X0_LOCAL,
            "x1_local_exclusive": GRID_X1_LOCAL,
            "y0": GRID_Y0,
            "y1_exclusive": GRID_Y1,
            "controller_halves_are_semantically_identical": True,
            "controller_pattern_phase_is_identical": True,
        },
        "columns": [
            {
                "display_column": index,
                "column_id": column.column_id,
                "a_quarters": column.a_quarters,
                "b_quarters": column.b_quarters,
            }
            for index, column in enumerate(MIX_COLUMNS)
        ],
        "rows": [
            {
                "display_row": index,
                "row_id": family.row_id,
                "appearance_hypothesis": family.appearance_hypothesis,
                "code_a": family.code_a,
                "color_a": family.color_a,
                "code_b": family.code_b,
                "color_b": family.color_b,
            }
            for index, family in enumerate(MIX_FAMILIES)
        ],
        "rois": [roi.to_dict() for roi in atlas_rois()],
        "identities": identities,
        "interpretation": {
            "appearance_names_are_hypotheses": True,
            "new_physical_pixel_state_claimed": False,
            "new_waveform_or_lut_state_claimed": False,
            "measured_colour_claimed": False,
            "operator_should_record_near_and_mid_distance": True,
        },
    }
    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    unsigned["integrity"] = {
        "canonical_sha256": hashlib.sha256(canonical).hexdigest(),
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }
    return unsigned


if GRID_X1_LOCAL != 486 or GRID_X1_LOCAL > CONTROLLER_WIDTH:
    raise RuntimeError("dither atlas grid width contract differs")
if GRID_Y1 != 570 or GRID_Y1 > HEIGHT:
    raise RuntimeError("dither atlas grid height contract differs")
if tuple(COLOR_NAME_BY_CODE) != LEGAL_CODES:
    raise RuntimeError("dither atlas legal colour order differs")
if set(LEGAL_CODES) != set(PHYSICAL_COLOR_CODES):
    raise RuntimeError("dither atlas physical colour contract differs")
