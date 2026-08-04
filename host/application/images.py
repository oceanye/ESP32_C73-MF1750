"""Decoded raster adapters and deterministic panel normalization.

The core accepts already-decoded RGB/RGBA bytes and has no third-party
dependency.  Pillow is an optional decoder only; importing this module does not
import or require Pillow.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Protocol

from host.color_pipeline import RasterImage
from host.epd_frame import HEIGHT, WIDTH


class ImageDecodeError(ValueError):
    """Raised when an optional decoder cannot produce a supported raster."""


class FitPolicy(str, Enum):
    CONTAIN = "contain"
    COVER = "cover"
    STRETCH = "stretch"


class ImageDecoder(Protocol):
    def decode(self, source: bytes) -> RasterImage:
        """Decode bytes to a top-left, tightly packed RGB/RGBA raster."""


class PillowImageDecoder:
    """Optional Pillow adapter; Pillow is deliberately not a core dependency."""

    def decode(self, source: bytes) -> RasterImage:
        try:
            from PIL import Image, ImageOps  # type: ignore[import-not-found]
        except ImportError as error:
            raise ImageDecodeError(
                "Pillow is not installed; pass a decoded RasterImage or use the browser UI"
            ) from error
        try:
            import io

            with Image.open(io.BytesIO(source)) as opened:
                oriented = ImageOps.exif_transpose(opened)
                mode = "RGBA" if "A" in oriented.getbands() else "RGB"
                converted = oriented.convert(mode)
                return RasterImage(converted.width, converted.height, mode, converted.tobytes())
        except Exception as error:
            raise ImageDecodeError(f"image decode failed: {error}") from error

    def decode_file(self, path: str | Path) -> RasterImage:
        return self.decode(Path(path).read_bytes())


def _coerce_policy(policy: FitPolicy | str) -> FitPolicy:
    try:
        return policy if isinstance(policy, FitPolicy) else FitPolicy(policy)
    except ValueError as error:
        allowed = ", ".join(item.value for item in FitPolicy)
        raise ImageDecodeError(f"unknown fit policy; expected one of: {allowed}") from error


def normalize_raster(
    image: RasterImage,
    policy: FitPolicy | str = FitPolicy.CONTAIN,
    *,
    target_width: int = WIDTH,
    target_height: int = HEIGHT,
) -> RasterImage:
    """Normalize with deterministic nearest-neighbour scaling and centred fit.

    ``contain`` pads with opaque white, ``cover`` centre-crops after scaling,
    and ``stretch`` changes aspect ratio.  RGBA pixels remain straight-alpha;
    C2 performs the canonical linear-light composition onto white.
    """

    selected = _coerce_policy(policy)
    if type(target_width) is not int or type(target_height) is not int:
        raise ImageDecodeError("target dimensions must be integers")
    if target_width <= 0 or target_height <= 0:
        raise ImageDecodeError("target dimensions must be positive")

    source_width = image.width
    source_height = image.height
    channels = image.channels
    if selected is FitPolicy.STRETCH:
        scaled_width, scaled_height = target_width, target_height
    else:
        width_ratio = target_width / source_width
        height_ratio = target_height / source_height
        scale = min(width_ratio, height_ratio) if selected is FitPolicy.CONTAIN else max(
            width_ratio, height_ratio
        )
        scaled_width = max(1, round(source_width * scale))
        scaled_height = max(1, round(source_height * scale))

    fill = bytes((255, 255, 255, 255) if channels == 4 else (255, 255, 255))
    output = bytearray(fill * (target_width * target_height))
    offset_x = (target_width - scaled_width) // 2
    offset_y = (target_height - scaled_height) // 2
    source = image.pixels

    for target_y in range(target_height):
        scaled_y = target_y - offset_y
        if not 0 <= scaled_y < scaled_height:
            continue
        source_y = min(source_height - 1, (scaled_y * source_height) // scaled_height)
        for target_x in range(target_width):
            scaled_x = target_x - offset_x
            if not 0 <= scaled_x < scaled_width:
                continue
            source_x = min(source_width - 1, (scaled_x * source_width) // scaled_width)
            source_start = (source_y * source_width + source_x) * channels
            target_start = (target_y * target_width + target_x) * channels
            output[target_start : target_start + channels] = source[
                source_start : source_start + channels
            ]
    return RasterImage(target_width, target_height, image.mode, bytes(output))
