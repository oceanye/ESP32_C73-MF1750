"""Deterministic host-side six-colour quantization for MF-1750 frames."""

from .color import (
    ColorValueError,
    Lab,
    LinearRGB,
    delta_e_ciede2000,
    lab_to_linear_rgb,
    lab_to_srgb8,
    linear_rgb_to_lab,
    srgb8_to_lab,
    srgb8_to_linear_rgb,
)
from .palette import (
    Palette,
    PaletteEntry,
    PaletteError,
    load_palette,
    palette_from_mapping,
    reference_palette,
)
from .pipeline import (
    ColorPipelineError,
    DitherMode,
    PipelineOptions,
    QuantizationReport,
    QuantizationResult,
    RasterImage,
    quantize_image,
    quantize_panel_image,
)
from .preview import PreviewError, encode_rgb_png

__all__ = [
    "ColorPipelineError",
    "ColorValueError",
    "DitherMode",
    "Lab",
    "LinearRGB",
    "Palette",
    "PaletteEntry",
    "PaletteError",
    "PipelineOptions",
    "PreviewError",
    "QuantizationReport",
    "QuantizationResult",
    "RasterImage",
    "delta_e_ciede2000",
    "encode_rgb_png",
    "lab_to_linear_rgb",
    "lab_to_srgb8",
    "linear_rgb_to_lab",
    "load_palette",
    "palette_from_mapping",
    "quantize_image",
    "quantize_panel_image",
    "reference_palette",
    "srgb8_to_lab",
    "srgb8_to_linear_rgb",
]
