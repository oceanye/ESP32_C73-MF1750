"""Decoded raster adapters and deterministic panel normalization.

The core accepts already-decoded RGB/RGBA bytes and has no third-party
dependency.  Pillow is an optional decoder only; importing this module does not
import or require Pillow.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import io
from pathlib import Path
from typing import Any, Dict, Protocol

from host.color_pipeline import RasterImage
from host.epd_frame import HEIGHT, WIDTH


class ImageDecodeError(ValueError):
    """Raised when an optional decoder cannot produce a supported raster."""


class FitPolicy(str, Enum):
    CONTAIN = "contain"
    COVER = "cover"
    STRETCH = "stretch"


@dataclass(frozen=True)
class DecodedRaster:
    """One server-decoded, normalized raster plus explicit colour provenance.

    This is the versioned G1/S1 preview path.  It intentionally remains
    separate from :class:`PillowImageDecoder` and :func:`normalize_raster` so
    the existing C2 legacy path keeps its byte-for-byte behaviour.
    """

    raster: RasterImage
    source_sha256: str
    provenance: Dict[str, Any]

    def __post_init__(self) -> None:
        if type(self.raster) is not RasterImage:
            raise ImageDecodeError("decoded raster must contain a RasterImage")
        if (
            not isinstance(self.source_sha256, str)
            or len(self.source_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.source_sha256)
        ):
            raise ImageDecodeError("decoded source_sha256 must be 64 lowercase hex digits")
        if not isinstance(self.provenance, dict):
            raise ImageDecodeError("decoded provenance must be a dictionary")


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


_SOURCE_FORMAT_BY_MEDIA_TYPE = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
_EXIF_ORIENTATION_TAG = 274
_ROTATION_DEGREES = (0, 90, 180, 270)
MAX_DECODED_SOURCE_PIXELS = 100_000_000


def decode_normalized_source(
    source: bytes | bytearray | memoryview,
    media_type: str,
    fit: FitPolicy | str = FitPolicy.CONTAIN,
    *,
    rotation_degrees: int = 0,
    target_width: int = WIDTH,
    target_height: int = HEIGHT,
) -> DecodedRaster:
    """Decode original image bytes and produce the G1/S1 working raster.

    Embedded ICC profiles are converted to IEC sRGB with Pillow/LittleCMS.
    Untagged sources use an explicit sRGB assumption that is recorded as
    offline-only evidence.  EXIF orientation is applied before the explicit
    rotation and deterministic geometry step.  This function never accesses a
    device or grants hardware authorization.
    """

    try:
        raw = bytes(memoryview(source).cast("B"))
    except (TypeError, ValueError) as error:
        raise ImageDecodeError("source image must be contiguous bytes") from error
    if not raw:
        raise ImageDecodeError("source image must not be empty")
    if media_type not in _SOURCE_FORMAT_BY_MEDIA_TYPE:
        raise ImageDecodeError("media type must be image/png, image/jpeg, or image/webp")
    selected_fit = _coerce_policy(fit)
    if type(rotation_degrees) is not int or rotation_degrees not in _ROTATION_DEGREES:
        raise ImageDecodeError("rotation_degrees must be one of 0, 90, 180, or 270")
    if type(target_width) is not int or type(target_height) is not int:
        raise ImageDecodeError("target dimensions must be integers")
    if target_width <= 0 or target_height <= 0:
        raise ImageDecodeError("target dimensions must be positive")

    try:
        import PIL  # type: ignore[import-not-found]
        from PIL import Image, ImageCms, ImageOps  # type: ignore[import-not-found]
    except ImportError as error:
        raise ImageDecodeError(
            "Pillow with ImageCms support is required for the G1/S1 source-byte path"
        ) from error

    try:
        with Image.open(io.BytesIO(raw)) as opened:
            actual_format = str(opened.format or "").upper()
            if actual_format != _SOURCE_FORMAT_BY_MEDIA_TYPE[media_type]:
                raise ImageDecodeError(
                    f"declared {media_type} does not match decoded {actual_format or 'unknown'}"
                )
            if getattr(opened, "n_frames", 1) != 1:
                raise ImageDecodeError("animated or multi-frame source images are not accepted")
            if opened.width * opened.height > MAX_DECODED_SOURCE_PIXELS:
                raise ImageDecodeError(
                    f"decoded image exceeds {MAX_DECODED_SOURCE_PIXELS} pixels"
                )
            source_width = opened.width
            source_height = opened.height
            try:
                orientation = int(opened.getexif().get(_EXIF_ORIENTATION_TAG, 1))
            except (AttributeError, TypeError, ValueError):
                orientation = 1
            oriented = ImageOps.exif_transpose(opened)
            has_alpha = "A" in oriented.getbands() or "transparency" in opened.info
            alpha = oriented.convert("RGBA").getchannel("A") if has_alpha else None
            embedded_icc = opened.info.get("icc_profile")
            if embedded_icc is not None and not isinstance(embedded_icc, bytes):
                raise ImageDecodeError("embedded ICC profile must be byte data")
            if embedded_icc:
                try:
                    source_profile = ImageCms.ImageCmsProfile(io.BytesIO(embedded_icc))
                    destination_profile = ImageCms.createProfile("sRGB")
                    converted_rgb = ImageCms.profileToProfile(
                        oriented,
                        source_profile,
                        destination_profile,
                        outputMode="RGB",
                        renderingIntent=0,
                    )
                    profile_description = str(
                        ImageCms.getProfileDescription(source_profile)
                    ).strip()
                except Exception as error:
                    raise ImageDecodeError(
                        f"embedded ICC conversion to sRGB failed: {error}"
                    ) from error
                icc_handling = "embedded_icc_to_srgb_relative_colorimetric"
                icc_sha256 = hashlib.sha256(embedded_icc).hexdigest()
                source_profile_label = profile_description or "embedded-icc"
                srgb_assumption = False
            else:
                converted_rgb = oriented.convert("RGB")
                icc_handling = "untagged_explicit_srgb_assumption"
                icc_sha256 = None
                source_profile_label = "assumed-iec-srgb"
                srgb_assumption = True
            if alpha is not None:
                working = converted_rgb.convert("RGBA")
                working.putalpha(alpha)
            else:
                working = converted_rgb

            if rotation_degrees:
                transpose = {
                    90: Image.Transpose.ROTATE_90,
                    180: Image.Transpose.ROTATE_180,
                    270: Image.Transpose.ROTATE_270,
                }[rotation_degrees]
                working = working.transpose(transpose)

            resample = Image.Resampling.LANCZOS
            target_size = (target_width, target_height)
            if selected_fit is FitPolicy.STRETCH:
                normalized = working.resize(target_size, resample=resample)
            elif selected_fit is FitPolicy.COVER:
                normalized = ImageOps.fit(
                    working,
                    target_size,
                    method=resample,
                    centering=(0.5, 0.5),
                )
            else:
                contained = ImageOps.contain(working, target_size, method=resample)
                fill = (255, 255, 255, 0) if working.mode == "RGBA" else (255, 255, 255)
                normalized = Image.new(working.mode, target_size, fill)
                offset = (
                    (target_width - contained.width) // 2,
                    (target_height - contained.height) // 2,
                )
                normalized.paste(contained, offset)
            mode = "RGBA" if normalized.mode == "RGBA" else "RGB"
            if normalized.mode != mode:
                normalized = normalized.convert(mode)
            raster = RasterImage(target_width, target_height, mode, normalized.tobytes())
    except ImageDecodeError:
        raise
    except Exception as error:
        raise ImageDecodeError(f"image decode/normalization failed: {error}") from error

    littlecms_version = str(
        getattr(getattr(ImageCms, "core", object()), "littlecms_version", "unknown")
    )
    provenance: Dict[str, Any] = {
        "path_version": 2,
        "decoder": "Pillow",
        "decoder_version": str(getattr(PIL, "__version__", "unknown")),
        "littlecms_version": littlecms_version,
        "decoded_format": actual_format,
        "declared_media_type": media_type,
        "source_width": source_width,
        "source_height": source_height,
        "exif_orientation": orientation,
        "exif_transposed": orientation != 1,
        "explicit_rotation_degrees": rotation_degrees,
        "embedded_icc_sha256": icc_sha256,
        "source_profile": source_profile_label,
        "icc_handling": icc_handling,
        "srgb_assumption": srgb_assumption,
        "working_space": "IEC 61966-2-1 sRGB RGB8/RGBA8",
        "fit": selected_fit.value,
        "resampler": "Pillow-LANCZOS",
        "target_width": target_width,
        "target_height": target_height,
        "formal_colour_eligible": False,
        "formal_ineligibility_reason": (
            "source decode provenance alone cannot qualify an unmeasured panel gamut"
        ),
        "hardware_tested": False,
    }
    return DecodedRaster(raster, hashlib.sha256(raw).hexdigest(), provenance)


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
