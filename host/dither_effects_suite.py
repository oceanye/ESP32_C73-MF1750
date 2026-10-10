"""Deterministic factory-OTP spatial-dither effect charts for MF1750.

This module is deliberately offline-only.  It creates three canonical
1024x600 packed-4bpp frames:

* ``pair-gradients``: seven native-colour pairs rendered as smooth ordered
  spatial mixtures;
* ``effects-chart``: warm/cool three-colour fields, a neutral ramp, native
  flat blocks, and a small edge/detail strip; and
* ``white``: the independent factory-OTP recovery frame.

Both 512-pixel controller halves contain the same semantic layout and the
same ordered-mask phase.  Appearance names and nominal RGB previews are only
operator aids.  Nothing here changes a waveform, LUT, voltage, timing, or
single-pixel pigment state, and this module has no hardware or network path.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json

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


CLASSIFICATION = "FACTORY_OTP_SPATIAL_DITHER_EFFECTS_EXTENSION_OFFLINE_ONLY"
PROFILE_SOURCE = "factory_otp"
CUSTOM_LUT_OR_WAVEFORM = False
HARDWARE_EXECUTION_AUTHORIZED = False
SPATIAL_MIXING_ONLY = True
SINGLE_PIXEL_MULTI_PIGMENT_CLAIM = False

ROLE_PAIR_GRADIENTS = "pair-gradients"
ROLE_EFFECTS_CHART = "effects-chart"
ROLE_WHITE = "white"
ROLES = (ROLE_PAIR_GRADIENTS, ROLE_EFFECTS_CHART, ROLE_WHITE)

FROZEN_ROLE_SHA256 = {
    ROLE_PAIR_GRADIENTS: (
        "531306ff2f309ce8f85b76c851cbb90512b65f92c608ca5b0ae518920778f122",
        "92ccf83245be714c5a8272882487f4e668edddf4a5cab8191bb5c609e8869404",
        "92ccf83245be714c5a8272882487f4e668edddf4a5cab8191bb5c609e8869404",
    ),
    ROLE_EFFECTS_CHART: (
        "02351166adb9d52e36eaccef0b50360c7c74806608ab404b5a08b648f5dc0865",
        "b2a4159fd17ed409fe441773df0d8f657f503f53693d35a0a2720d6f6ec7f678",
        "b2a4159fd17ed409fe441773df0d8f657f503f53693d35a0a2720d6f6ec7f678",
    ),
    ROLE_WHITE: (
        "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
        "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
        "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
    ),
}

LEGAL_CODES = (0, 1, 2, 3, 5, 6)
COLOR_NAME_BY_CODE = {
    0: "black",
    1: "white",
    2: "yellow",
    3: "red",
    5: "blue",
    6: "green",
}
NOMINAL_RGB_BY_CODE = {
    0: (0, 0, 0),
    1: (255, 255, 255),
    2: (255, 255, 0),
    3: (255, 0, 0),
    5: (0, 0, 255),
    6: (0, 255, 0),
}

# Standard recursive 8x8 Bayer rank matrix.  Each rank 0..63 occurs exactly
# once, so a locally constant mixture is exactly quantized in 1/64 steps.
BAYER_8X8 = (
    (0, 32, 8, 40, 2, 34, 10, 42),
    (48, 16, 56, 24, 50, 18, 58, 26),
    (12, 44, 4, 36, 14, 46, 6, 38),
    (60, 28, 52, 20, 62, 30, 54, 22),
    (3, 35, 11, 43, 1, 33, 9, 41),
    (51, 19, 59, 27, 49, 17, 57, 25),
    (15, 47, 7, 39, 13, 45, 5, 37),
    (63, 31, 55, 23, 61, 29, 53, 21),
)


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
    MixFamily("red-yellow", "orange-family", 3, 2),
    MixFamily("yellow-white", "light-yellow-family", 2, 1),
    MixFamily("green-yellow", "lime-family", 6, 2),
    MixFamily("red-blue", "purple-family", 3, 5),
    MixFamily("red-green", "brown-family", 3, 6),
    MixFamily("green-blue", "cyan-or-sky-family", 6, 5),
    MixFamily("red-white", "pink-family", 3, 1),
)

# Pair-gradient layout, duplicated exactly on each controller half.
GRADIENT_X0_LOCAL = 24
GRADIENT_WIDTH = 464
GRADIENT_Y0 = 14
GRADIENT_ROW_HEIGHT = 72
GRADIENT_ROW_GAP = 10
GRADIENT_Y1 = (
    GRADIENT_Y0
    + len(MIX_FAMILIES) * GRADIENT_ROW_HEIGHT
    + (len(MIX_FAMILIES) - 1) * GRADIENT_ROW_GAP
)

# Composite effects-chart regions, again local to each controller half.
CHART_X0_LOCAL = 24
CHART_WIDTH = 464
TRIFIELD_Y0 = 24
TRIFIELD_HEIGHT = 224
TRIFIELD_WIDTH = 224
TRIFIELD_GAP = 16
NEUTRAL_Y0 = 272
NEUTRAL_HEIGHT = 112
BLOCK_Y0 = 408
BLOCK_HEIGHT = 112
BLOCK_GAP = 4
BLOCK_WIDTH = 74
BLOCK_BORDER = 2
DETAIL_Y0 = 536
DETAIL_HEIGHT = 40


class DitherEffectsSuiteError(ValueError):
    """Raised when the fixed dither-effects contract is violated."""


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
    role: str
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


def _checked_role(value: object) -> str:
    if value not in ROLES:
        raise DitherEffectsSuiteError(f"role must be one of {ROLES!r}")
    return str(value)


def _payload_identity(payload: bytes) -> PayloadIdentity:
    return PayloadIdentity(
        byte_count=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        fnv1a_u32=fnv1a(payload),
    )


def _set_pixel(frame: bytearray, x: int, y: int, code: int) -> None:
    if code not in LEGAL_CODES:
        raise DitherEffectsSuiteError("attempted to place a non-factory code")
    offset = y * ROW_BYTES + x // 2
    if x & 1:
        frame[offset] = (frame[offset] & 0xF0) | code
    else:
        frame[offset] = (frame[offset] & 0x0F) | (code << 4)


def _two_code(code_a: int, code_b: int, a_units: int, x: int, y: int) -> int:
    if not 0 <= a_units <= 64:
        raise DitherEffectsSuiteError("two-colour mixture is outside 0..64")
    if a_units == 64:
        return code_a
    if a_units == 0:
        return code_b
    return code_a if BAYER_8X8[y & 7][x & 7] < a_units else code_b


def _three_code(
    code_a: int,
    code_b: int,
    code_c: int,
    units_a: int,
    units_b: int,
    x: int,
    y: int,
) -> int:
    if units_a < 0 or units_b < 0 or units_a + units_b > 64:
        raise DitherEffectsSuiteError("three-colour mixture is outside 64 units")
    rank = BAYER_8X8[y & 7][x & 7]
    if rank < units_a:
        return code_a
    if rank < units_a + units_b:
        return code_b
    return code_c


def _build_pair_gradients(frame: bytearray) -> None:
    for half in range(2):
        half_x = half * CONTROLLER_WIDTH
        for row, family in enumerate(MIX_FAMILIES):
            y0 = GRADIENT_Y0 + row * (GRADIENT_ROW_HEIGHT + GRADIENT_ROW_GAP)
            for local_y in range(GRADIENT_ROW_HEIGHT):
                y = y0 + local_y
                for local_x in range(GRADIENT_WIDTH):
                    # Exact pure endpoints with 65 ordered mixture levels.
                    a_units = round(
                        (GRADIENT_WIDTH - 1 - local_x) * 64 / (GRADIENT_WIDTH - 1)
                    )
                    code = _two_code(
                        family.code_a,
                        family.code_b,
                        a_units,
                        local_x,
                        local_y,
                    )
                    _set_pixel(frame, half_x + GRADIENT_X0_LOCAL + local_x, y, code)


def _fill_trifield(
    frame: bytearray,
    *,
    half_x: int,
    x0_local: int,
    code_a: int,
    code_b: int,
) -> None:
    for local_y in range(TRIFIELD_HEIGHT):
        nonwhite_units = round(
            (TRIFIELD_HEIGHT - 1 - local_y) * 64 / (TRIFIELD_HEIGHT - 1)
        )
        for local_x in range(TRIFIELD_WIDTH):
            units_a = round(
                nonwhite_units * (TRIFIELD_WIDTH - 1 - local_x) / (TRIFIELD_WIDTH - 1)
            )
            units_b = nonwhite_units - units_a
            code = _three_code(
                code_a,
                code_b,
                1,
                units_a,
                units_b,
                local_x,
                local_y,
            )
            _set_pixel(
                frame,
                half_x + x0_local + local_x,
                TRIFIELD_Y0 + local_y,
                code,
            )


def _build_effects_chart(frame: bytearray) -> None:
    block_codes = LEGAL_CODES
    for half in range(2):
        half_x = half * CONTROLLER_WIDTH
        _fill_trifield(
            frame,
            half_x=half_x,
            x0_local=CHART_X0_LOCAL,
            code_a=3,
            code_b=2,
        )
        _fill_trifield(
            frame,
            half_x=half_x,
            x0_local=CHART_X0_LOCAL + TRIFIELD_WIDTH + TRIFIELD_GAP,
            code_a=5,
            code_b=6,
        )

        for local_y in range(NEUTRAL_HEIGHT):
            for local_x in range(CHART_WIDTH):
                black_units = round(
                    (CHART_WIDTH - 1 - local_x) * 64 / (CHART_WIDTH - 1)
                )
                code = _two_code(0, 1, black_units, local_x, local_y)
                _set_pixel(
                    frame,
                    half_x + CHART_X0_LOCAL + local_x,
                    NEUTRAL_Y0 + local_y,
                    code,
                )

        for index, code in enumerate(block_codes):
            x0 = CHART_X0_LOCAL + index * (BLOCK_WIDTH + BLOCK_GAP)
            for y in range(BLOCK_Y0, BLOCK_Y0 + BLOCK_HEIGHT):
                for x in range(x0, x0 + BLOCK_WIDTH):
                    on_border = (
                        x < x0 + BLOCK_BORDER
                        or x >= x0 + BLOCK_WIDTH - BLOCK_BORDER
                        or y < BLOCK_Y0 + BLOCK_BORDER
                        or y >= BLOCK_Y0 + BLOCK_HEIGHT - BLOCK_BORDER
                    )
                    _set_pixel(frame, half_x + x, y, 0 if on_border else code)

        # A compact, deterministic edge strip.  Four black/white square-wave
        # zones exercise 1, 2, 4, and 8 pixel features without text/fonts.
        zone_width = CHART_WIDTH // 4
        for zone, feature_width in enumerate((1, 2, 4, 8)):
            x0 = CHART_X0_LOCAL + zone * zone_width
            x1 = CHART_X0_LOCAL + CHART_WIDTH if zone == 3 else x0 + zone_width
            for local_y in range(DETAIL_HEIGHT):
                y = DETAIL_Y0 + local_y
                for x in range(x0, x1):
                    local_x = x - x0
                    code = (
                        0
                        if ((local_x // feature_width) + (local_y // feature_width)) & 1
                        else 1
                    )
                    _set_pixel(frame, half_x + x, y, code)


@lru_cache(maxsize=len(ROLES))
def build_frame(role: str) -> bytes:
    """Build one fixed effects-suite frame."""

    checked = _checked_role(role)
    frame = bytearray(b"\x11" * FRAME_BYTES)
    if checked == ROLE_PAIR_GRADIENTS:
        _build_pair_gradients(frame)
    elif checked == ROLE_EFFECTS_CHART:
        _build_effects_chart(frame)
    result = bytes(frame)
    validate_frame(result)
    return result


def controller_stream(frame: bytes, half: int) -> bytes:
    if type(half) is not int or half not in (0, 1):
        raise DitherEffectsSuiteError("controller half must be integer 0 or 1")
    validated = bytes(validate_frame(frame))
    stream = _mapped_controller_stream(
        validated,
        ControllerMapping(source_half=half),
    )
    if len(stream) != CONTROLLER_FRAME_BYTES:
        raise DitherEffectsSuiteError("controller DTM byte count differs")
    return stream


@lru_cache(maxsize=len(ROLES))
def frame_identity(role: str) -> FrameIdentity:
    checked = _checked_role(role)
    frame = build_frame(checked)
    counts = pixel_counts(frame)
    histogram = tuple(counts[code] if code < len(counts) else 0 for code in range(8))
    return FrameIdentity(
        role=checked,
        frame=_payload_identity(frame),
        cs1_dtm=_payload_identity(controller_stream(frame, 0)),
        cs2_dtm=_payload_identity(controller_stream(frame, 1)),
        histogram=histogram,
    )


def pixel_code(frame: bytes, x: int, y: int) -> int:
    if len(frame) != FRAME_BYTES:
        raise DitherEffectsSuiteError("frame byte count differs")
    if (
        type(x) is not int
        or type(y) is not int
        or not (0 <= x < WIDTH and 0 <= y < HEIGHT)
    ):
        raise DitherEffectsSuiteError("pixel coordinate is outside the panel")
    value = frame[y * ROW_BYTES + x // 2]
    return value & 0x0F if x & 1 else value >> 4


def layout_manifest() -> dict[str, object]:
    """Return a deterministic self-describing offline layout manifest."""

    identities = {role: frame_identity(role).to_dict() for role in ROLES}
    unsigned: dict[str, object] = {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-dither-effects-extension-layout",
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
        "ordered_mask": {
            "id": "bayer-8x8-rank-0-to-63",
            "mixture_resolution_units": 64,
            "ranks": [list(row) for row in BAYER_8X8],
        },
        "pair_gradients": {
            "rows": len(MIX_FAMILIES),
            "x0_local": GRADIENT_X0_LOCAL,
            "width": GRADIENT_WIDTH,
            "y0": GRADIENT_Y0,
            "row_height": GRADIENT_ROW_HEIGHT,
            "row_gap": GRADIENT_ROW_GAP,
            "y1_exclusive": GRADIENT_Y1,
            "direction": "pure-a-left-to-pure-b-right",
            "families": [
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
        },
        "effects_chart": {
            "warm_trifield": {
                "codes": [3, 2, 1],
                "names": ["red", "yellow", "white"],
                "rectangle_local": [24, 24, 224, 224],
            },
            "cool_trifield": {
                "codes": [5, 6, 1],
                "names": ["blue", "green", "white"],
                "rectangle_local": [264, 24, 224, 224],
            },
            "neutral_ramp": {
                "codes": [0, 1],
                "names": ["black", "white"],
                "rectangle_local": [24, 272, 464, 112],
            },
            "native_blocks": {
                "codes": list(LEGAL_CODES),
                "rectangle_local": [24, 408, 464, 112],
                "block_width": BLOCK_WIDTH,
                "gap": BLOCK_GAP,
                "border_code": 0,
                "border_width_pixels": BLOCK_BORDER,
            },
            "edge_strip": {
                "codes": [0, 1],
                "feature_widths_pixels": [1, 2, 4, 8],
                "rectangle_local": [24, 536, 464, 40],
            },
        },
        "controller_halves_are_semantically_identical": True,
        "controller_pattern_phase_is_identical": True,
        "identities": identities,
        "interpretation": {
            "nominal_rgb_preview_is_not_colorimetric_prediction": True,
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


def _validate_constants() -> None:
    ranks = [rank for row in BAYER_8X8 for rank in row]
    if sorted(ranks) != list(range(64)):
        raise RuntimeError("8x8 Bayer rank contract differs")
    if GRADIENT_X0_LOCAL + GRADIENT_WIDTH > CONTROLLER_WIDTH:
        raise RuntimeError("gradient layout exceeds a controller half")
    if GRADIENT_Y1 > HEIGHT:
        raise RuntimeError("gradient layout exceeds panel height")
    if CHART_X0_LOCAL + CHART_WIDTH > CONTROLLER_WIDTH:
        raise RuntimeError("effects chart exceeds a controller half")
    if DETAIL_Y0 + DETAIL_HEIGHT > HEIGHT:
        raise RuntimeError("effects chart exceeds panel height")
    if (
        BLOCK_WIDTH * len(LEGAL_CODES) + BLOCK_GAP * (len(LEGAL_CODES) - 1)
        != CHART_WIDTH
    ):
        raise RuntimeError("native block widths do not fill the chart")
    if tuple(COLOR_NAME_BY_CODE) != LEGAL_CODES:
        raise RuntimeError("dither effects legal colour order differs")
    if set(LEGAL_CODES) != set(PHYSICAL_COLOR_CODES):
        raise RuntimeError("dither effects physical colour contract differs")


def validate_frozen_identities() -> None:
    """Fail closed if deterministic frame or controller bytes drift."""

    for role, expected in FROZEN_ROLE_SHA256.items():
        identity = frame_identity(role)
        actual = (
            identity.frame.sha256,
            identity.cs1_dtm.sha256,
            identity.cs2_dtm.sha256,
        )
        if actual != expected:
            raise RuntimeError(f"dither effects role {role} identity drifted")


_validate_constants()
validate_frozen_identities()
