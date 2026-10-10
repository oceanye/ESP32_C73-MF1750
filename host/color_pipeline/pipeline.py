"""Deterministic RGB/RGBA to canonical six-colour 4bpp conversion."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from array import array
from typing import Any, Dict, List, Optional, Sequence, Tuple

from host.epd_frame import (
    FRAME_BYTES,
    HEIGHT,
    PHYSICAL_COLOR_CODES,
    WIDTH,
    fnv1a,
    pack_pixels,
    validate_frame,
)

from .color import LinearRGB, SRGB8_TO_LINEAR, delta_e_ciede2000, linear_rgb_to_lab
from .palette import (
    PALETTE_CANONICAL_HASH_SCOPE,
    PALETTE_SCHEMA_VERSION,
    Palette,
    PaletteEntry,
    reference_palette,
)
from .preview import encode_rgb_png


class ColorPipelineError(ValueError):
    """Raised when a raster or pipeline option violates the host contract."""


REPORT_SCHEMA_VERSION = 2
PIPELINE_VERSION = "2.0.0"
PIPELINE_BUILD_ID = "mf1750-color-pipeline-v2-2026-08-04"
INPUT_TRANSFER_FUNCTION = "IEC 61966-2-1 sRGB"
ALPHA_BACKGROUND_SRGB8 = (255, 255, 255)
REPORT_CANONICAL_HASH_SCOPE = (
    "entire report object excluding report_integrity; UTF-8 JSON with sorted "
    "keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
UNCONSTRAINED_PHYSICAL_CODE = 0xFF


class DitherMode(str, Enum):
    NONE = "none"
    FLOYD_STEINBERG = "floyd-steinberg"
    ATKINSON = "atkinson"
    ORDERED_BAYER = "ordered-bayer-8x8"
    HASHED_THRESHOLD = "hashed-threshold"


@dataclass(frozen=True)
class RasterImage:
    """Decoded bytes whose construction declares 8-bit straight-alpha sRGB."""

    width: int
    height: int
    mode: str
    pixels: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.width, int) or isinstance(self.width, bool) or self.width <= 0:
            raise ColorPipelineError("image width must be a positive integer")
        if not isinstance(self.height, int) or isinstance(self.height, bool) or self.height <= 0:
            raise ColorPipelineError("image height must be a positive integer")
        normalized_mode = self.mode.upper() if isinstance(self.mode, str) else ""
        if normalized_mode not in ("RGB", "RGBA"):
            raise ColorPipelineError("image mode must be RGB or RGBA")
        try:
            view = memoryview(self.pixels).cast("B")
        except (TypeError, ValueError) as error:
            raise ColorPipelineError("image pixels must be contiguous bytes") from error
        channels = 3 if normalized_mode == "RGB" else 4
        expected = self.width * self.height * channels
        if len(view) != expected:
            raise ColorPipelineError(f"image has {len(view)} bytes; expected {expected}")
        object.__setattr__(self, "mode", normalized_mode)
        object.__setattr__(self, "pixels", bytes(view))

    @property
    def channels(self) -> int:
        return 3 if self.mode == "RGB" else 4


@dataclass(frozen=True)
class PipelineOptions:
    dither: DitherMode | str = DitherMode.FLOYD_STEINBERG
    seed: int = 0x4D463137
    serpentine: bool = True
    white_protection: bool = True
    white_luminance_threshold: float = 0.95
    white_chroma_threshold: float = 0.025
    preserve_edges: bool = True
    edge_threshold: float = 0.18
    text_mode: bool = False
    text_luminance_threshold: float = 0.5

    def __post_init__(self) -> None:
        try:
            mode = self.dither if isinstance(self.dither, DitherMode) else DitherMode(self.dither)
        except ValueError as error:
            allowed = ", ".join(mode.value for mode in DitherMode)
            raise ColorPipelineError(f"unknown dither mode; expected one of: {allowed}") from error
        object.__setattr__(self, "dither", mode)
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise ColorPipelineError("seed must be an integer")
        if not 0 <= self.seed <= 0xFFFFFFFF:
            raise ColorPipelineError("seed must be in [0, 0xffffffff]")
        for label in ("serpentine", "white_protection", "preserve_edges", "text_mode"):
            if not isinstance(getattr(self, label), bool):
                raise ColorPipelineError(f"{label} must be boolean")
        for label in (
            "white_luminance_threshold",
            "white_chroma_threshold",
            "edge_threshold",
            "text_luminance_threshold",
        ):
            raw_value = getattr(self, label)
            if isinstance(raw_value, bool):
                raise ColorPipelineError(f"{label} must be a number, not boolean")
            value = float(raw_value)
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ColorPipelineError(f"{label} must be finite and in [0, 1]")
            object.__setattr__(self, label, value)


@dataclass(frozen=True)
class QuantizationReport:
    width: int
    height: int
    frame_bytes: int
    frame_sha256: str
    frame_fnv1a: str
    input_mode: str
    input_raster_bytes: int
    input_raster_sha256: str
    canonical_panel_dimensions: bool
    panel_frame_bytes_output: bool
    authorization_reason: str
    allow_uncalibrated_palette: bool
    palette_id: str
    palette_calibrated: bool
    palette_source: str
    palette_illuminant: str
    palette_observer: str
    palette_notes: str
    palette_canonical_sha256: str
    palette_calibration: Optional[Tuple[str, str]]
    palette_entries: Tuple[
        Tuple[int, str, Tuple[float, float, float], Tuple[int, int, int]], ...
    ]
    dither: str
    requested_dither: str
    seed: int
    serpentine: bool
    white_protection: bool
    white_luminance_threshold: float
    white_chroma_threshold: float
    text_mode: bool
    text_luminance_threshold: float
    edge_preservation: bool
    requested_edge_preservation: bool
    edge_threshold: float
    counts: Tuple[Tuple[int, str, int], ...]

    def to_dict(self) -> Dict[str, Any]:
        total = self.width * self.height
        report: Dict[str, Any] = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "kind": "mf1750-color-quantization-report",
            "pipeline": {
                "version": PIPELINE_VERSION,
                "build_id": PIPELINE_BUILD_ID,
            },
            "width": self.width,
            "height": self.height,
            "frame_bytes": self.frame_bytes,
            "frame_sha256": self.frame_sha256,
            "frame_fnv1a": self.frame_fnv1a,
            "input_raster": {
                "width": self.width,
                "height": self.height,
                "mode": self.input_mode,
                "pixel_bytes": self.input_raster_bytes,
                "sha256": self.input_raster_sha256,
                "sha256_scope": "decoded tightly-packed pixel bytes only",
                "row_order": "top-left row-major",
                "transfer_function": INPUT_TRANSFER_FUNCTION,
                "caller_declaration": {
                    "decoded_srgb8": True,
                    "rgba_alpha_is_straight": (
                        True if self.input_mode == "RGBA" else None
                    ),
                    "statement": (
                        "caller declares decoded 8-bit IEC sRGB input and, for "
                        "RGBA, straight (unassociated) alpha"
                    ),
                },
                "alpha": {
                    "representation": (
                        "straight" if self.input_mode == "RGBA" else "absent"
                    ),
                    "background_srgb8": list(ALPHA_BACKGROUND_SRGB8),
                    "compositing_space": "linear-light",
                    "applied": self.input_mode == "RGBA",
                },
            },
            "palette": {
                "schema_version": PALETTE_SCHEMA_VERSION,
                "id": self.palette_id,
                "calibrated": self.palette_calibrated,
                "source": self.palette_source,
                "illuminant": self.palette_illuminant,
                "observer": self.palette_observer,
                "notes": self.palette_notes,
                "calibration": (
                    None
                    if self.palette_calibration is None
                    else {
                        "measurement_id": self.palette_calibration[0],
                        "artifact_sha256": self.palette_calibration[1],
                    }
                ),
                "canonical_sha256": self.palette_canonical_sha256,
                "canonical_sha256_scope": PALETTE_CANONICAL_HASH_SCOPE,
                "fingerprint_trust": (
                    "audit fingerprint only; not a digital signature or "
                    "trust-store decision"
                ),
                "entries": [
                    {
                        "code": code,
                        "name": name,
                        "lab": list(lab),
                        "preview_rgb": list(preview_rgb),
                    }
                    for code, name, lab, preview_rgb in self.palette_entries
                ],
            },
            "options": {
                "dither": self.dither,
                "requested_dither": self.requested_dither,
                "seed": self.seed,
                "serpentine": self.serpentine,
                "white_protection": self.white_protection,
                "white_luminance_threshold": self.white_luminance_threshold,
                "white_chroma_threshold": self.white_chroma_threshold,
                "text_mode": self.text_mode,
                "text_luminance_threshold": self.text_luminance_threshold,
                "edge_preservation": self.edge_preservation,
                "requested_edge_preservation": self.requested_edge_preservation,
                "edge_threshold": self.edge_threshold,
            },
            "safety": {
                "canonical_panel_dimensions": self.canonical_panel_dimensions,
                "panel_frame_bytes_output": self.panel_frame_bytes_output,
                "palette_calibrated": self.palette_calibrated,
                "allow_uncalibrated_palette": self.allow_uncalibrated_palette,
                "authorization_reason": self.authorization_reason,
            },
            "usage": [
                {
                    "code": code,
                    "name": name,
                    "count": count,
                    "ratio": count / total,
                }
                for code, name, count in self.counts
            ],
            "hardware_tested": False,
        }
        canonical_bytes = json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        report["report_integrity"] = {
            "canonical_sha256": hashlib.sha256(canonical_bytes).hexdigest(),
            "canonical_sha256_scope": REPORT_CANONICAL_HASH_SCOPE,
            "fingerprint_trust": (
                "audit fingerprint only; not a digital signature or "
                "trust-store decision"
            ),
        }
        return report


@dataclass(frozen=True)
class QuantizationResult:
    width: int
    height: int
    frame: bytes
    codes: bytes
    palette: Palette
    report: QuantizationReport

    def preview_rgb(self) -> bytes:
        colour_by_code = {entry.code: entry.preview_rgb for entry in self.palette.entries}
        output = bytearray(len(self.codes) * 3)
        for index, code in enumerate(self.codes):
            rgb = colour_by_code[code]
            start = index * 3
            output[start : start + 3] = bytes(rgb)
        return bytes(output)

    def preview_png(self) -> bytes:
        return encode_rgb_png(self.width, self.height, self.preview_rgb())


_BAYER_8X8 = (
    (0, 48, 12, 60, 3, 51, 15, 63),
    (32, 16, 44, 28, 35, 19, 47, 31),
    (8, 56, 4, 52, 11, 59, 7, 55),
    (40, 24, 36, 20, 43, 27, 39, 23),
    (2, 50, 14, 62, 1, 49, 13, 61),
    (34, 18, 46, 30, 33, 17, 45, 29),
    (10, 58, 6, 54, 9, 57, 5, 53),
    (42, 26, 38, 22, 41, 25, 37, 21),
)


def _clamp_rgb(rgb: Sequence[float]) -> LinearRGB:
    return tuple(min(1.0, max(0.0, value)) for value in rgb)  # type: ignore[return-value]


def _pixel_linear(image: RasterImage, pixel_index: int) -> Tuple[LinearRGB, float]:
    offset = pixel_index * image.channels
    data = image.pixels
    red = SRGB8_TO_LINEAR[data[offset]]
    green = SRGB8_TO_LINEAR[data[offset + 1]]
    blue = SRGB8_TO_LINEAR[data[offset + 2]]
    if image.channels == 3:
        return (red, green, blue), 1.0
    alpha = data[offset + 3] / 255.0
    inverse = 1.0 - alpha
    # Alpha is composited over white in linear light, not gamma-encoded sRGB.
    return (
        red * alpha + inverse,
        green * alpha + inverse,
        blue * alpha + inverse,
    ), alpha


def _luminance(rgb: Sequence[float]) -> float:
    return 0.2126729 * rgb[0] + 0.7151522 * rgb[1] + 0.0721750 * rgb[2]


def _edge_mask(image: RasterImage, threshold: float) -> bytearray:
    width = image.width
    height = image.height
    pixel_count = width * height
    values = array("f", [0.0]) * (pixel_count * 3)
    for index in range(pixel_count):
        rgb = _pixel_linear(image, index)[0]
        offset = index * 3
        values[offset] = rgb[0]
        values[offset + 1] = rgb[1]
        values[offset + 2] = rgb[2]
    edges = bytearray(pixel_count)

    def distance(first: int, second: int) -> float:
        first_offset = first * 3
        second_offset = second * 3
        return max(
            abs(values[first_offset] - values[second_offset]),
            abs(values[first_offset + 1] - values[second_offset + 1]),
            abs(values[first_offset + 2] - values[second_offset + 2]),
        )

    for y in range(height):
        row = y * width
        for x in range(width):
            index = row + x
            maximum = 0.0
            if x:
                maximum = max(maximum, distance(index, index - 1))
            if x + 1 < width:
                maximum = max(maximum, distance(index, index + 1))
            if y:
                maximum = max(maximum, distance(index, index - width))
            if y + 1 < height:
                maximum = max(maximum, distance(index, index + width))
            edges[index] = 1 if maximum >= threshold else 0
    return edges


def _nearest_two(rgb: LinearRGB, entries: Sequence[PaletteEntry]) -> Tuple[int, float, int, float]:
    lab = linear_rgb_to_lab(rgb)
    first = (math.inf, math.inf, -1)
    second = (math.inf, math.inf, -1)
    for index, entry in enumerate(entries):
        candidate = (delta_e_ciede2000(lab, entry.lab), entry.code, index)
        if candidate < first:
            second = first
            first = candidate
        elif candidate < second:
            second = candidate
    return first[2], first[0], second[2], second[0]


def _threshold(mode: DitherMode, x: int, y: int, seed: int) -> float:
    if mode == DitherMode.ORDERED_BAYER:
        return (_BAYER_8X8[y & 7][x & 7] + 0.5) / 64.0
    # A stateless integer hash makes seeded stochastic thresholding reproducible
    # across Python versions.  It is deliberately not labelled "blue noise".
    value = (seed & 0xFFFFFFFF) ^ ((x * 0x9E3779B1) & 0xFFFFFFFF)
    value ^= (y * 0x85EBCA77) & 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x7FEB352D) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 0x846CA68B) & 0xFFFFFFFF
    value ^= value >> 16
    return (value + 0.5) / 4294967296.0


def _choose_threshold_candidate(
    rgb: LinearRGB,
    entries: Sequence[PaletteEntry],
    threshold: float,
) -> int:
    first_index, first_distance, second_index, second_distance = _nearest_two(rgb, entries)
    if first_distance == 0.0:
        return first_index
    distance_sum = first_distance + second_distance
    second_probability = 0.5 if distance_sum == 0.0 else first_distance / distance_sum
    return second_index if threshold < second_probability else first_index


def _is_protected_white(rgb: LinearRGB, alpha: float, options: PipelineOptions) -> bool:
    if alpha == 0.0:
        return True
    if not options.white_protection:
        return False
    chroma = max(rgb) - min(rgb)
    return (
        _luminance(rgb) >= options.white_luminance_threshold
        and chroma <= options.white_chroma_threshold
    )


def _quantize_codes(
    image: RasterImage,
    palette: Palette,
    options: PipelineOptions,
) -> bytes:
    width = image.width
    height = image.height
    entries = palette.entries
    diffusion_colours = tuple(entry.diffusion_rgb for entry in entries)
    white_index = next(index for index, entry in enumerate(entries) if entry.code == 1)
    black_index = next(index for index, entry in enumerate(entries) if entry.code == 0)
    edges: Optional[bytearray] = None
    if options.preserve_edges and not options.text_mode:
        edges = _edge_mask(image, options.edge_threshold)
    codes = bytearray(width * height)

    if options.text_mode:
        for index in range(len(codes)):
            rgb, alpha = _pixel_linear(image, index)
            selected = (
                white_index
                if _is_protected_white(rgb, alpha, options)
                or _luminance(rgb) >= options.text_luminance_threshold
                else black_index
            )
            codes[index] = entries[selected].code
        return bytes(codes)

    if options.dither in (DitherMode.NONE, DitherMode.ORDERED_BAYER, DitherMode.HASHED_THRESHOLD):
        for y in range(height):
            for x in range(width):
                index = y * width + x
                rgb, alpha = _pixel_linear(image, index)
                if _is_protected_white(rgb, alpha, options):
                    selected = white_index
                elif edges is not None and edges[index]:
                    selected = _nearest_two(rgb, entries)[0]
                elif options.dither == DitherMode.NONE:
                    selected = _nearest_two(rgb, entries)[0]
                else:
                    selected = _choose_threshold_candidate(
                        rgb, entries, _threshold(options.dither, x, y, options.seed)
                    )
                codes[index] = entries[selected].code
        return bytes(codes)

    slots = width * 3
    error_rows: List[List[float]] = [[0.0] * slots for _ in range(3)]

    def add_error(
        target_x: int,
        target_y: int,
        residual: LinearRGB,
        weight: float,
    ) -> None:
        if not (0 <= target_x < width and 0 <= target_y < height):
            return
        target_index = target_y * width + target_x
        if edges is not None and edges[target_index]:
            return
        row_errors = error_rows[target_y % 3]
        offset = target_x * 3
        row_errors[offset] += residual[0] * weight
        row_errors[offset + 1] += residual[1] * weight
        row_errors[offset + 2] += residual[2] * weight

    for y in range(height):
        direction = -1 if options.serpentine and (y & 1) else 1
        x_values = range(width - 1, -1, -1) if direction < 0 else range(width)
        current_errors = error_rows[y % 3]
        for x in x_values:
            index = y * width + x
            source_rgb, alpha = _pixel_linear(image, index)
            if _is_protected_white(source_rgb, alpha, options):
                selected = white_index
                effective_rgb = source_rgb
                diffuse = False
            else:
                offset = x * 3
                if edges is not None and edges[index]:
                    effective_rgb = source_rgb
                    diffuse = False
                else:
                    effective_rgb = _clamp_rgb(
                        (
                            source_rgb[0] + current_errors[offset],
                            source_rgb[1] + current_errors[offset + 1],
                            source_rgb[2] + current_errors[offset + 2],
                        )
                    )
                    diffuse = True
                selected = _nearest_two(effective_rgb, entries)[0]
            codes[index] = entries[selected].code
            if not diffuse:
                continue
            palette_rgb = diffusion_colours[selected]
            residual = (
                effective_rgb[0] - palette_rgb[0],
                effective_rgb[1] - palette_rgb[1],
                effective_rgb[2] - palette_rgb[2],
            )
            if options.dither == DitherMode.FLOYD_STEINBERG:
                add_error(x + direction, y, residual, 7.0 / 16.0)
                add_error(x - direction, y + 1, residual, 3.0 / 16.0)
                add_error(x, y + 1, residual, 5.0 / 16.0)
                add_error(x + direction, y + 1, residual, 1.0 / 16.0)
            else:  # Atkinson
                for target_x, target_y in (
                    (x + direction, y),
                    (x + 2 * direction, y),
                    (x - direction, y + 1),
                    (x, y + 1),
                    (x + direction, y + 1),
                    (x, y + 2),
                ):
                    add_error(target_x, target_y, residual, 1.0 / 8.0)
        error_rows[y % 3] = [0.0] * slots
    return bytes(codes)


def build_protection_constraints(
    image: RasterImage,
    *,
    palette: Optional[Palette] = None,
    options: Optional[PipelineOptions] = None,
) -> bytes:
    """Return per-pixel fixed colour codes for C2 protection semantics.

    An unconstrained pixel is encoded as ``0xff``.  Protected white pixels,
    edge pixels and every text-mode pixel contain one of the six physical
    codes.  S1 algorithms consume this mask so the existing C2 controls do not
    silently stop working when a different halftoner is selected.
    """

    if type(image) is not RasterImage:
        raise ColorPipelineError("image must be a RasterImage instance")
    selected_palette = reference_palette() if palette is None else palette
    if type(selected_palette) is not Palette:
        raise ColorPipelineError("palette must be a Palette instance or None")
    selected_options = PipelineOptions() if options is None else options
    if type(selected_options) is not PipelineOptions:
        raise ColorPipelineError("options must be a PipelineOptions instance or None")
    entries = selected_palette.entries
    white_code = next(entry.code for entry in entries if entry.code == 1)
    black_code = next(entry.code for entry in entries if entry.code == 0)
    constraints = bytearray(
        (UNCONSTRAINED_PHYSICAL_CODE,) * (image.width * image.height)
    )
    edges = (
        _edge_mask(image, selected_options.edge_threshold)
        if selected_options.preserve_edges and not selected_options.text_mode
        else None
    )
    for index in range(len(constraints)):
        rgb, alpha = _pixel_linear(image, index)
        if selected_options.text_mode:
            constraints[index] = (
                white_code
                if _is_protected_white(rgb, alpha, selected_options)
                or _luminance(rgb) >= selected_options.text_luminance_threshold
                else black_code
            )
        elif _is_protected_white(rgb, alpha, selected_options):
            constraints[index] = white_code
        elif edges is not None and edges[index]:
            constraints[index] = entries[_nearest_two(rgb, entries)[0]].code
    return bytes(constraints)


def quantize_image(
    image: RasterImage,
    *,
    palette: Optional[Palette] = None,
    options: Optional[PipelineOptions] = None,
    allow_uncalibrated_palette: bool = False,
) -> QuantizationResult:
    """Quantize an even-width RGB/RGBA raster to canonical packed 4bpp.

    Small rasters remain an offline/test entry point.  A panel-sized raster is
    a production-capable frame and therefore rejects an uncalibrated palette
    unless the caller records an explicit ``allow_uncalibrated_palette=True``
    opt-in.
    """

    if image.width % 2:
        raise ColorPipelineError("4bpp output requires an even image width")
    if not isinstance(allow_uncalibrated_palette, bool):
        raise ColorPipelineError("allow_uncalibrated_palette must be boolean")
    if palette is None:
        selected_palette = reference_palette()
    elif type(palette) is Palette:
        selected_palette = palette
    else:
        raise ColorPipelineError("palette must be a Palette instance or None")
    if options is None:
        selected_options = PipelineOptions()
    elif type(options) is PipelineOptions:
        selected_options = options
    else:
        raise ColorPipelineError("options must be a PipelineOptions instance or None")
    canonical_panel_dimensions = (image.width, image.height) == (WIDTH, HEIGHT)
    expected_frame_bytes = image.width * image.height // 2
    panel_frame_bytes_output = expected_frame_bytes == FRAME_BYTES
    if panel_frame_bytes_output and not canonical_panel_dimensions:
        raise ColorPipelineError(
            f"{FRAME_BYTES}-byte output is reserved for canonical "
            f"{WIDTH}x{HEIGHT} panel dimensions; got {image.width}x{image.height}"
        )
    if (
        canonical_panel_dimensions
        and not selected_palette.calibrated
        and not allow_uncalibrated_palette
    ):
        raise ColorPipelineError(
            "panel-sized output requires a calibrated palette; pass "
            "allow_uncalibrated_palette=True only for an explicitly authorized "
            "uncalibrated panel experiment"
        )
    if not canonical_panel_dimensions:
        authorization_reason = "offline_non_panel_frame"
    elif selected_palette.calibrated:
        authorization_reason = "calibrated_palette"
    else:
        authorization_reason = "explicit_uncalibrated_palette_opt_in"
    codes = _quantize_codes(image, selected_palette, selected_options)
    # The palette's render_path declares the code semantics: the stock OTP
    # contract ships only the six physical codes, while the measured L535
    # R20 path drives all eight nibbles (white=7).
    pack_allowed = (
        list(range(8))
        if selected_palette.render_path == "l535_r20"
        else PHYSICAL_COLOR_CODES
    )
    frame = pack_pixels(codes, image.width, image.height, allowed_colors=pack_allowed)
    counts_by_code = {entry.code: 0 for entry in selected_palette.entries}
    for code in codes:
        counts_by_code[code] += 1
    counts = tuple(
        (entry.code, entry.name, counts_by_code[entry.code])
        for entry in selected_palette.entries
    )
    report = QuantizationReport(
        width=image.width,
        height=image.height,
        frame_bytes=len(frame),
        frame_sha256=hashlib.sha256(frame).hexdigest(),
        frame_fnv1a=f"0x{fnv1a(frame):08X}",
        input_mode=image.mode,
        input_raster_bytes=len(image.pixels),
        input_raster_sha256=hashlib.sha256(image.pixels).hexdigest(),
        canonical_panel_dimensions=canonical_panel_dimensions,
        panel_frame_bytes_output=panel_frame_bytes_output,
        authorization_reason=authorization_reason,
        allow_uncalibrated_palette=allow_uncalibrated_palette,
        palette_id=selected_palette.palette_id,
        palette_calibrated=selected_palette.calibrated,
        palette_source=selected_palette.source,
        palette_illuminant=selected_palette.illuminant,
        palette_observer=selected_palette.observer,
        palette_notes=selected_palette.notes,
        palette_canonical_sha256=selected_palette.canonical_sha256,
        palette_calibration=(
            None
            if selected_palette.calibration is None
            else (
                selected_palette.calibration.measurement_id,
                selected_palette.calibration.artifact_sha256,
            )
        ),
        palette_entries=tuple(
            (entry.code, entry.name, entry.lab, entry.preview_rgb)
            for entry in selected_palette.entries
        ),
        dither=(
            DitherMode.NONE.value
            if selected_options.text_mode
            else selected_options.dither.value
        ),
        requested_dither=selected_options.dither.value,
        seed=selected_options.seed,
        serpentine=selected_options.serpentine,
        white_protection=selected_options.white_protection,
        white_luminance_threshold=selected_options.white_luminance_threshold,
        white_chroma_threshold=selected_options.white_chroma_threshold,
        text_mode=selected_options.text_mode,
        text_luminance_threshold=selected_options.text_luminance_threshold,
        edge_preservation=(selected_options.preserve_edges and not selected_options.text_mode),
        requested_edge_preservation=selected_options.preserve_edges,
        edge_threshold=selected_options.edge_threshold,
        counts=counts,
    )
    return QuantizationResult(
        image.width,
        image.height,
        frame,
        codes,
        selected_palette,
        report,
    )


def quantize_panel_image(
    image: RasterImage,
    *,
    palette: Optional[Palette] = None,
    options: Optional[PipelineOptions] = None,
    allow_uncalibrated_palette: bool = False,
) -> QuantizationResult:
    """Quantize exactly one MF-1750 1024x600 image to a 307200-byte frame.

    Uncalibrated palettes are rejected by default.  The explicit opt-in is for
    controlled panel experiments and is preserved in report schema v2.
    """

    if (image.width, image.height) != (WIDTH, HEIGHT):
        raise ColorPipelineError(
            f"panel input must be {WIDTH}x{HEIGHT}; got {image.width}x{image.height}"
        )
    result = quantize_image(
        image,
        palette=palette,
        options=options,
        allow_uncalibrated_palette=allow_uncalibrated_palette,
    )
    if len(result.frame) != FRAME_BYTES:
        raise AssertionError("panel frame length invariant failed")
    validate_frame(
        result.frame,
        allowed_colors=(
            list(range(8))
            if result.palette.render_path == "l535_r20"
            else PHYSICAL_COLOR_CODES
        ),
    )
    return result
