"""Application-level image preparation and auditable report generation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from typing import Any, Mapping, Optional

from host.color_pipeline import (
    Palette,
    PipelineOptions,
    RasterImage,
    quantize_panel_image,
    reference_palette,
)
from host.epd_frame import FRAME_BYTES, HEIGHT, PHYSICAL_COLOR_CODES, WIDTH, validate_frame

from .images import FitPolicy, normalize_raster


APPLICATION_REPORT_SCHEMA = "mf1750-application-report"
APPLICATION_REPORT_VERSION = 1
MANUAL_CONFIRMATIONS = (
    "full_panel_visual_result",
    "power_supply_cv",
    "power_supply_current",
    "L1_L2_temperature",
)


class ApplicationError(ValueError):
    """Raised when application input or authorization violates the contract."""


class PreparationPurpose(str, Enum):
    OFFLINE_PREVIEW = "offline_preview"
    FORMAL_UPLOAD = "formal_upload"


@dataclass(frozen=True)
class InputSource:
    label: str
    media_type: str
    sha256: str
    hash_scope: str = "original input bytes"

    @classmethod
    def from_bytes(cls, label: str, media_type: str, source: bytes) -> "InputSource":
        return cls(label, media_type, hashlib.sha256(source).hexdigest())

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label.strip():
            raise ApplicationError("input source label must be non-empty")
        if not isinstance(self.media_type, str) or not self.media_type.strip():
            raise ApplicationError("input media type must be non-empty")
        if (
            not isinstance(self.sha256, str)
            or len(self.sha256) != 64
            or any(character not in "0123456789abcdefABCDEF" for character in self.sha256)
        ):
            raise ApplicationError("input source sha256 must be exactly 64 hex digits")
        if not isinstance(self.hash_scope, str) or not self.hash_scope.strip():
            raise ApplicationError("input hash scope must be non-empty")
        object.__setattr__(self, "label", self.label.strip())
        object.__setattr__(self, "media_type", self.media_type.strip())
        object.__setattr__(self, "sha256", self.sha256.lower())
        object.__setattr__(self, "hash_scope", self.hash_scope.strip())


@dataclass(frozen=True)
class ApplicationArtifact:
    frame: bytes
    preview_png: bytes
    report: Mapping[str, Any]
    upload_authorized: bool

    def __post_init__(self) -> None:
        frame = validate_application_frame(self.frame)
        if type(self.upload_authorized) is not bool:
            raise ApplicationError("upload_authorized must be boolean")
        if self.report.get("schema") != APPLICATION_REPORT_SCHEMA:
            raise ApplicationError("application artifact report schema is invalid")
        if self.report.get("version") != APPLICATION_REPORT_VERSION:
            raise ApplicationError("application artifact report version is invalid")
        if self.report.get("offline_verified") is not True:
            raise ApplicationError("application artifact must be offline_verified")
        if self.report.get("hardware_tested") is not False:
            raise ApplicationError("application report must keep hardware_tested=false")
        output = self.report.get("output")
        if not isinstance(output, Mapping):
            raise ApplicationError("application report output must be an object")
        if output.get("width") != WIDTH or output.get("height") != HEIGHT:
            raise ApplicationError("application report output dimensions do not match the panel")
        if output.get("bytes") != FRAME_BYTES:
            raise ApplicationError("application report output byte count is invalid")
        if output.get("sha256") != hashlib.sha256(frame).hexdigest():
            raise ApplicationError("application report output hash does not match the frame")
        if self.report.get("formal_upload_authorized") is not self.upload_authorized:
            raise ApplicationError("artifact upload authorization differs from its report")
        palette = self.report.get("palette_provenance")
        if not isinstance(palette, Mapping):
            raise ApplicationError("application report palette provenance must be an object")
        if self.upload_authorized:
            if palette.get("calibrated") is not True:
                raise ApplicationError("formal upload authorization requires calibrated provenance")
            if self.report.get("authorization_reason") != "calibrated_palette":
                raise ApplicationError("formal upload authorization reason is invalid")


def validate_application_frame(frame: bytes | bytearray | memoryview) -> bytes:
    """Re-run the one canonical frame validator immediately before output."""

    try:
        validated = bytes(validate_frame(frame, WIDTH, HEIGHT))
    except ValueError as error:
        raise ApplicationError(f"invalid canonical application frame: {error}") from error
    if len(validated) != FRAME_BYTES:
        raise ApplicationError(f"application frame must contain exactly {FRAME_BYTES} bytes")
    return validated


def _purpose(value: PreparationPurpose | str) -> PreparationPurpose:
    try:
        return value if isinstance(value, PreparationPurpose) else PreparationPurpose(value)
    except ValueError as error:
        raise ApplicationError("purpose must be offline_preview or formal_upload") from error


def prepare_image(
    image: RasterImage,
    source: InputSource,
    *,
    fit: FitPolicy | str = FitPolicy.CONTAIN,
    palette: Optional[Palette] = None,
    options: Optional[PipelineOptions] = None,
    purpose: PreparationPurpose | str = PreparationPurpose.OFFLINE_PREVIEW,
) -> ApplicationArtifact:
    """Normalize and quantize one image without performing device I/O."""

    selected_purpose = _purpose(purpose)
    selected_palette = reference_palette() if palette is None else palette
    if not isinstance(selected_palette, Palette):
        raise ApplicationError("palette must be a Palette instance")
    if selected_purpose is PreparationPurpose.FORMAL_UPLOAD and not selected_palette.calibrated:
        raise ApplicationError(
            "formal full-frame output requires a calibrated palette; the reference palette "
            "is allowed only for explicitly labelled offline preview"
        )
    normalized = normalize_raster(image, fit)
    result = quantize_panel_image(
        normalized,
        palette=selected_palette,
        options=options,
        allow_uncalibrated_palette=(
            selected_purpose is PreparationPurpose.OFFLINE_PREVIEW
            and not selected_palette.calibrated
        ),
    )
    frame = validate_application_frame(result.frame)
    quantization = result.report.to_dict()
    upload_authorized = bool(selected_palette.calibrated)
    report: dict[str, Any] = {
        "schema": APPLICATION_REPORT_SCHEMA,
        "version": APPLICATION_REPORT_VERSION,
        "input": {
            "source": source.label,
            "media_type": source.media_type,
            "sha256": source.sha256,
            "sha256_scope": source.hash_scope,
            "decoded_mode": image.mode,
            "decoded_width": image.width,
            "decoded_height": image.height,
            "decoded_raster_sha256": hashlib.sha256(image.pixels).hexdigest(),
            "normalized_raster_sha256": hashlib.sha256(normalized.pixels).hexdigest(),
        },
        "normalization": {
            "fit": FitPolicy(fit).value,
            "resampler": "deterministic_nearest_neighbour",
            "target_width": WIDTH,
            "target_height": HEIGHT,
            "rgba_alpha_composition": "C2 linear-light composition onto white",
        },
        "palette_provenance": quantization["palette"],
        "quantization_options": quantization["options"],
        "output": {
            "width": WIDTH,
            "height": HEIGHT,
            "bits_per_pixel": 4,
            "bytes": len(frame),
            "sha256": hashlib.sha256(frame).hexdigest(),
            "fnv1a": quantization["frame_fnv1a"],
            "physical_color_codes": sorted(PHYSICAL_COLOR_CODES),
            "usage": quantization["usage"],
        },
        "purpose": selected_purpose.value,
        "formal_upload_authorized": upload_authorized,
        "authorization_reason": (
            "calibrated_palette" if upload_authorized else "reference_palette_offline_preview_only"
        ),
        "offline_verified": True,
        "protocol_verified": False,
        "hardware_tested": False,
        "verified_scope": [
            "decoded_raster_normalization",
            "existing_C2_six_color_quantization",
            "canonical_frame_dimensions_length_colors_and_hash",
        ],
        "manual_confirmation_required": {item: False for item in MANUAL_CONFIRMATIONS},
    }
    return ApplicationArtifact(frame, result.preview_png(), report, upload_authorized)
