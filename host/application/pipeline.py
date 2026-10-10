"""Application-level image preparation and auditable report generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Mapping, Optional

from host.color_pipeline import (
    PALETTE_CANONICAL_HASH_SCOPE,
    PALETTE_SCHEMA_VERSION,
    PIPELINE_BUILD_ID,
    PIPELINE_VERSION,
    REPORT_CANONICAL_HASH_SCOPE,
    REPORT_SCHEMA_VERSION,
    Palette,
    PaletteError,
    PipelineOptions,
    RasterImage,
    palette_from_mapping,
    quantize_panel_image,
    reference_palette,
)
from host.epd_frame import (
    FRAME_BYTES,
    HEIGHT,
    PHYSICAL_COLOR_CODES,
    WIDTH,
    fnv1a,
    validate_frame,
)

from .images import FitPolicy, normalize_raster
from .simulation import SimulationResult, validate_simulation_report


APPLICATION_REPORT_SCHEMA = "mf1750-application-report"
APPLICATION_REPORT_VERSION = 1
APPLICATION_SIMULATION_REPORT_VERSION = 2
MANUAL_CONFIRMATIONS = (
    "full_panel_visual_result",
    "power_supply_cv",
    "power_supply_current",
    "L1_L2_temperature",
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_C2_REPORT_KIND = "mf1750-color-quantization-report"
_FINGERPRINT_TRUST = (
    "audit fingerprint only; not a digital signature or trust-store decision"
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


def _json_snapshot(value: Any, label: str) -> Any:
    """Return a JSON-only tree with no aliases to caller-owned containers."""

    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ApplicationError(f"{label} must not contain NaN or infinity")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ApplicationError(f"{label} object keys must be strings")
            result[key] = _json_snapshot(item, label)
        return result
    if isinstance(value, (list, tuple)):
        return [_json_snapshot(item, label) for item in value]
    raise ApplicationError(f"{label} must contain only JSON-compatible values")


def _canonical_json_bytes(value: Any, label: str) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ApplicationError(f"{label} is not canonical JSON: {error}") from error


def _bytes_snapshot(value: Any, label: str) -> bytes:
    try:
        view = memoryview(value)
        if view.ndim != 1 or view.itemsize != 1 or view.format != "B":
            view = view.cast("B")
        return bytes(view)
    except (TypeError, ValueError) as error:
        raise ApplicationError(f"{label} must be a contiguous bytes-like object") from error


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ApplicationError(f"{label} must be exactly 64 lowercase hex digits")
    return value


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ApplicationError(f"{label} must be an object")
    return value


def _validate_c2_report(
    report: Mapping[str, Any], frame: bytes
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Validate the complete C2 schema-v2 evidence embedded by this layer."""

    if (
        type(report.get("schema_version")) is not int
        or report.get("schema_version") != REPORT_SCHEMA_VERSION
    ):
        raise ApplicationError(
            f"quantization report schema_version must be integer {REPORT_SCHEMA_VERSION}"
        )
    if report.get("kind") != _C2_REPORT_KIND:
        raise ApplicationError("quantization report kind is invalid")
    pipeline = _require_mapping(
        report.get("pipeline"), "quantization report pipeline"
    )
    if set(pipeline) != {"version", "build_id"} or pipeline != {
        "version": PIPELINE_VERSION,
        "build_id": PIPELINE_BUILD_ID,
    }:
        raise ApplicationError("quantization report pipeline identity is invalid")
    if report.get("hardware_tested") is not False:
        raise ApplicationError("quantization report must keep hardware_tested=false")

    integrity = _require_mapping(
        report.get("report_integrity"), "quantization report report_integrity"
    )
    if set(integrity) != {
        "canonical_sha256",
        "canonical_sha256_scope",
        "fingerprint_trust",
    }:
        raise ApplicationError("quantization report integrity fields are invalid")
    integrity_hash = _require_sha256(
        integrity.get("canonical_sha256"),
        "quantization report integrity canonical_sha256",
    )
    if integrity.get("canonical_sha256_scope") != REPORT_CANONICAL_HASH_SCOPE:
        raise ApplicationError("quantization report integrity hash scope is invalid")
    if integrity.get("fingerprint_trust") != _FINGERPRINT_TRUST:
        raise ApplicationError("quantization report fingerprint trust statement is invalid")
    unsigned = dict(report)
    del unsigned["report_integrity"]
    expected_integrity_hash = hashlib.sha256(
        _canonical_json_bytes(unsigned, "unsigned quantization report")
    ).hexdigest()
    if integrity_hash != expected_integrity_hash:
        raise ApplicationError("quantization report integrity hash does not match its content")

    expected_sha256 = hashlib.sha256(frame).hexdigest()
    expected_fnv1a = f"0x{fnv1a(frame):08X}"
    if report.get("width") != WIDTH or report.get("height") != HEIGHT:
        raise ApplicationError("quantization report dimensions do not match the panel")
    if (
        type(report.get("frame_bytes")) is not int
        or report.get("frame_bytes") != FRAME_BYTES
    ):
        raise ApplicationError("quantization report frame byte count is invalid")
    if report.get("frame_sha256") != expected_sha256:
        raise ApplicationError("quantization report frame sha256 does not match the frame")
    if report.get("frame_fnv1a") != expected_fnv1a:
        raise ApplicationError("quantization report frame fnv1a does not match the frame")

    palette = _require_mapping(report.get("palette"), "quantization report palette")
    if set(palette) != {
        "schema_version",
        "id",
        "calibrated",
        "source",
        "illuminant",
        "observer",
        "notes",
        "calibration",
        "canonical_sha256",
        "canonical_sha256_scope",
        "fingerprint_trust",
        "entries",
    }:
        raise ApplicationError("quantization palette fields are invalid")
    if (
        type(palette.get("schema_version")) is not int
        or palette.get("schema_version") != PALETTE_SCHEMA_VERSION
    ):
        raise ApplicationError(
            f"quantization palette schema_version must be integer {PALETTE_SCHEMA_VERSION}"
        )
    if palette.get("canonical_sha256_scope") != PALETTE_CANONICAL_HASH_SCOPE:
        raise ApplicationError("quantization palette canonical hash scope is invalid")
    if palette.get("fingerprint_trust") != _FINGERPRINT_TRUST:
        raise ApplicationError("quantization palette fingerprint trust statement is invalid")
    palette_hash = _require_sha256(
        palette.get("canonical_sha256"), "quantization palette canonical_sha256"
    )
    palette_mapping = {
        "schema_version": palette.get("schema_version"),
        "palette_id": palette.get("id"),
        "calibrated": palette.get("calibrated"),
        "source": palette.get("source"),
        "illuminant": palette.get("illuminant"),
        "observer": palette.get("observer"),
        "notes": palette.get("notes"),
        "calibration": palette.get("calibration"),
        "entries": palette.get("entries"),
    }
    try:
        normalized_palette = palette_from_mapping(palette_mapping)
    except PaletteError as error:
        raise ApplicationError(f"quantization palette provenance is invalid: {error}") from error
    if normalized_palette.canonical_mapping() != palette_mapping:
        raise ApplicationError("quantization palette is not in canonical normalized form")
    if normalized_palette.canonical_sha256 != palette_hash:
        raise ApplicationError("quantization palette canonical hash does not match its content")

    safety = _require_mapping(report.get("safety"), "quantization report safety")
    if set(safety) != {
        "canonical_panel_dimensions",
        "panel_frame_bytes_output",
        "palette_calibrated",
        "allow_uncalibrated_palette",
        "authorization_reason",
    }:
        raise ApplicationError("quantization report safety fields are invalid")
    if safety.get("canonical_panel_dimensions") is not True:
        raise ApplicationError("quantization safety requires canonical panel dimensions")
    if safety.get("panel_frame_bytes_output") is not True:
        raise ApplicationError("quantization safety requires canonical panel frame bytes")
    if safety.get("palette_calibrated") is not normalized_palette.calibrated:
        raise ApplicationError("quantization safety palette calibration flag is inconsistent")
    expected_allow_uncalibrated = not normalized_palette.calibrated
    if safety.get("allow_uncalibrated_palette") is not expected_allow_uncalibrated:
        raise ApplicationError("quantization safety uncalibrated-palette flag is inconsistent")
    expected_reason = (
        "calibrated_palette"
        if normalized_palette.calibrated
        else "explicit_uncalibrated_palette_opt_in"
    )
    if safety.get("authorization_reason") != expected_reason:
        raise ApplicationError("quantization safety authorization reason is inconsistent")
    return palette, _require_mapping(report.get("options"), "quantization report options")


@dataclass(frozen=True, init=False, slots=True)
class ApplicationArtifact:
    frame: bytes
    preview_png: bytes
    source_preview_png: bytes
    mapped_preview_png: bytes
    model_preview_png: bytes
    _report_json: bytes = field(repr=False)
    upload_authorized: bool

    def __init__(
        self,
        frame: bytes | bytearray | memoryview,
        preview_png: bytes | bytearray | memoryview,
        report: Mapping[str, Any],
        upload_authorized: bool,
        *,
        source_preview_png: bytes | bytearray | memoryview | None = None,
        mapped_preview_png: bytes | bytearray | memoryview | None = None,
        model_preview_png: bytes | bytearray | memoryview | None = None,
    ) -> None:
        canonical_frame = validate_application_frame(frame)
        canonical_preview = _bytes_snapshot(preview_png, "application preview")
        canonical_source_preview = _bytes_snapshot(
            canonical_preview if source_preview_png is None else source_preview_png,
            "application source preview",
        )
        canonical_mapped_preview = _bytes_snapshot(
            canonical_preview if mapped_preview_png is None else mapped_preview_png,
            "application mapped preview",
        )
        canonical_model_preview = _bytes_snapshot(
            canonical_preview if model_preview_png is None else model_preview_png,
            "application model preview",
        )
        if type(upload_authorized) is not bool:
            raise ApplicationError("upload_authorized must be boolean")
        if not isinstance(report, Mapping):
            raise ApplicationError("application artifact report must be an object")
        report_snapshot = _json_snapshot(report, "application artifact report")
        report_json = _canonical_json_bytes(report_snapshot, "application artifact report")
        self._validate_report(
            report_snapshot,
            canonical_frame,
            upload_authorized,
            {
                "source": canonical_source_preview,
                "mapped": canonical_mapped_preview,
                "final": canonical_preview,
                "model": canonical_model_preview,
            },
        )
        object.__setattr__(self, "frame", canonical_frame)
        object.__setattr__(self, "preview_png", canonical_preview)
        object.__setattr__(self, "source_preview_png", canonical_source_preview)
        object.__setattr__(self, "mapped_preview_png", canonical_mapped_preview)
        object.__setattr__(self, "model_preview_png", canonical_model_preview)
        object.__setattr__(self, "_report_json", report_json)
        object.__setattr__(self, "upload_authorized", upload_authorized)

    @staticmethod
    def _validate_report(
        report: Mapping[str, Any],
        frame: bytes,
        upload_authorized: bool,
        previews: Mapping[str, bytes],
    ) -> None:
        if report.get("schema") != APPLICATION_REPORT_SCHEMA:
            raise ApplicationError("application artifact report schema is invalid")
        version = report.get("version")
        if type(version) is not int or version not in {
            APPLICATION_REPORT_VERSION,
            APPLICATION_SIMULATION_REPORT_VERSION,
        }:
            raise ApplicationError("application artifact report version is invalid")
        if report.get("offline_verified") is not True:
            raise ApplicationError("application artifact must be offline_verified")
        if report.get("hardware_tested") is not False:
            raise ApplicationError("application report must keep hardware_tested=false")
        output = _require_mapping(report.get("output"), "application report output")
        if output.get("width") != WIDTH or output.get("height") != HEIGHT:
            raise ApplicationError("application report output dimensions do not match the panel")
        if type(output.get("bytes")) is not int or output.get("bytes") != FRAME_BYTES:
            raise ApplicationError("application report output byte count is invalid")
        expected_sha256 = hashlib.sha256(frame).hexdigest()
        expected_fnv1a = f"0x{fnv1a(frame):08X}"
        if output.get("sha256") != expected_sha256:
            raise ApplicationError("application report output hash does not match the frame")
        if output.get("fnv1a") != expected_fnv1a:
            raise ApplicationError("application report output fnv1a does not match the frame")
        if report.get("formal_upload_authorized") is not upload_authorized:
            raise ApplicationError("artifact upload authorization differs from its report")
        if version == APPLICATION_SIMULATION_REPORT_VERSION:
            ApplicationArtifact._validate_simulation_application_report(
                report, frame, upload_authorized, previews
            )
            return
        purpose = report.get("purpose")
        if purpose not in {item.value for item in PreparationPurpose}:
            raise ApplicationError("application report purpose is invalid")
        quantization = _require_mapping(
            report.get("quantization_report"), "application quantization_report"
        )
        palette, options = _validate_c2_report(quantization, frame)
        if report.get("palette_provenance") != palette:
            raise ApplicationError("application palette provenance differs from C2 evidence")
        if report.get("quantization_options") != options:
            raise ApplicationError("application quantization options differ from C2 evidence")
        if output.get("usage") != quantization.get("usage"):
            raise ApplicationError("application output usage differs from C2 evidence")
        input_report = _require_mapping(report.get("input"), "application report input")
        quantization_input = _require_mapping(
            quantization.get("input_raster"), "quantization report input_raster"
        )
        if input_report.get("normalized_raster_sha256") != quantization_input.get("sha256"):
            raise ApplicationError("normalized raster hash differs from C2 evidence")

        calibrated = palette.get("calibrated") is True
        expected_authorized = purpose == PreparationPurpose.FORMAL_UPLOAD.value and calibrated
        if upload_authorized is not expected_authorized:
            raise ApplicationError(
                "formal upload requires purpose=formal_upload and calibrated C2 provenance"
            )
        if purpose == PreparationPurpose.FORMAL_UPLOAD.value and not calibrated:
            raise ApplicationError("formal upload authorization requires calibrated provenance")
        expected_reason = (
            "calibrated_palette"
            if expected_authorized
            else (
                "calibrated_palette_offline_preview_only"
                if calibrated
                else "reference_palette_offline_preview_only"
            )
        )
        if report.get("authorization_reason") != expected_reason:
            if expected_authorized:
                raise ApplicationError("formal upload authorization reason is invalid")
            raise ApplicationError("offline preview authorization reason is invalid")

    @staticmethod
    def _validate_simulation_application_report(
        report: Mapping[str, Any],
        frame: bytes,
        upload_authorized: bool,
        previews: Mapping[str, bytes],
    ) -> None:
        if upload_authorized:
            raise ApplicationError("G1/S1 monitor simulation can never authorize upload")
        if report.get("purpose") != PreparationPurpose.OFFLINE_PREVIEW.value:
            raise ApplicationError("G1/S1 simulation must use offline_preview purpose")
        if report.get("authorization_reason") != "g1_s1_simulation_offline_preview_only":
            raise ApplicationError("G1/S1 simulation authorization reason is invalid")
        simulation = _require_mapping(
            report.get("simulation_report"), "application simulation_report"
        )
        try:
            validate_simulation_report(simulation, frame=frame, previews=previews)
        except ValueError as error:
            raise ApplicationError(f"simulation artifact is invalid: {error}") from error
        output = _require_mapping(report.get("output"), "application report output")
        simulation_output = _require_mapping(
            simulation.get("output"), "simulation report output"
        )
        if output.get("sha256") != simulation_output.get("frame_sha256"):
            raise ApplicationError("application output differs from simulation frame")
        if output.get("fnv1a") != simulation_output.get("frame_fnv1a"):
            raise ApplicationError("application output FNV differs from simulation frame")
        if output.get("usage") != simulation_output.get("usage"):
            raise ApplicationError("application usage differs from simulation report")
        palette = _require_mapping(simulation.get("palette"), "simulation palette")
        if report.get("palette_provenance") != {
            **palette,
            "canonical_sha256": simulation.get("palette_canonical_sha256"),
        }:
            raise ApplicationError("application palette differs from simulation provenance")
        preview_metadata = _require_mapping(
            report.get("previews"), "application preview metadata"
        )
        if preview_metadata != simulation.get("previews"):
            raise ApplicationError("application previews differ from simulation evidence")
        input_report = _require_mapping(report.get("input"), "application input")
        if input_report.get("normalized_raster_sha256") != simulation.get(
            "source_raster_sha256"
        ):
            raise ApplicationError("application normalized raster differs from simulation input")
        if report.get("hardware_tested") is not False:
            raise ApplicationError("simulation application report must keep hardware_tested=false")

    @property
    def report(self) -> dict[str, Any]:
        """Return a fresh JSON tree; callers cannot mutate stored evidence."""

        return json.loads(self._report_json.decode("utf-8"))

    @property
    def identity(self) -> dict[str, Any]:
        """Return the stable frame/report identity without exposing aliases."""

        return {
            "frame_sha256": hashlib.sha256(self.frame).hexdigest(),
            "frame_fnv1a": fnv1a(self.frame),
            "frame_bytes": len(self.frame),
            "report_sha256": hashlib.sha256(self._report_json).hexdigest(),
        }

    @property
    def artifact_identity(self) -> dict[str, Any]:
        """Backward-readable alias for callers that use the longer name."""

        return self.identity

    def validated_snapshot(self) -> "ApplicationArtifact":
        """Rebuild and fully validate a fresh snapshot from the current fields.

        ``frozen=True`` protects ordinary callers, but Python code can still use
        low-level attribute operations.  Device boundaries therefore call this
        method again immediately before binding or enqueueing instead of
        trusting that construction-time validation is still current.
        """

        try:
            return ApplicationArtifact(
                self.frame,
                self.preview_png,
                self.report,
                self.upload_authorized,
                source_preview_png=self.source_preview_png,
                mapped_preview_png=self.mapped_preview_png,
                model_preview_png=self.model_preview_png,
            )
        except ApplicationError:
            raise
        except (AttributeError, TypeError, UnicodeError, json.JSONDecodeError) as error:
            raise ApplicationError(
                f"application artifact snapshot is unreadable: {error}"
            ) from error


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


def prepare_simulation_artifact(
    simulation: SimulationResult,
    source: InputSource,
    *,
    decode_provenance: Mapping[str, Any],
) -> ApplicationArtifact:
    """Wrap one G1/S1 monitor simulation in the application evidence contract.

    The resulting artifact is deliberately offline-only.  In particular, this
    helper cannot be used to turn synthetic gamut or optical models into a
    formally upload-authorized frame.
    """

    if type(simulation) is not SimulationResult:
        raise ApplicationError("simulation must be a SimulationResult")
    if type(source) is not InputSource:
        raise ApplicationError("source must be an InputSource")
    if not isinstance(decode_provenance, Mapping):
        raise ApplicationError("decode_provenance must be an object")
    provenance = _json_snapshot(decode_provenance, "decode provenance")
    if provenance.get("hardware_tested") is not False:
        raise ApplicationError("decode provenance must keep hardware_tested=false")
    if provenance.get("formal_colour_eligible") is not False:
        raise ApplicationError("decode provenance must be formally ineligible")
    if provenance.get("declared_media_type") != source.media_type:
        raise ApplicationError("decode provenance media type differs from input source")

    try:
        result = simulation.validated_snapshot()
    except ValueError as error:
        raise ApplicationError(f"simulation result is invalid: {error}") from error
    frame = validate_application_frame(result.frame)
    simulation_report = _json_snapshot(result.report, "simulation report")
    simulation_output = _require_mapping(
        simulation_report.get("output"), "simulation report output"
    )
    palette = _require_mapping(
        simulation_report.get("palette"), "simulation report palette"
    )
    preview_metadata = _require_mapping(
        simulation_report.get("previews"), "simulation report previews"
    )
    report: dict[str, Any] = {
        "schema": APPLICATION_REPORT_SCHEMA,
        "version": APPLICATION_SIMULATION_REPORT_VERSION,
        "input": {
            "source": source.label,
            "media_type": source.media_type,
            "sha256": source.sha256,
            "sha256_scope": source.hash_scope,
            "normalized_mode": "RGB/RGBA8 sRGB",
            "normalized_width": WIDTH,
            "normalized_height": HEIGHT,
            "normalized_raster_sha256": simulation_report[
                "source_raster_sha256"
            ],
        },
        "normalization": provenance,
        "palette_provenance": {
            **palette,
            "canonical_sha256": simulation_report["palette_canonical_sha256"],
        },
        "quantization_options": simulation_report["halftone"],
        "simulation_report": simulation_report,
        "previews": preview_metadata,
        "output": {
            "width": WIDTH,
            "height": HEIGHT,
            "bits_per_pixel": 4,
            "bytes": len(frame),
            "sha256": simulation_output["frame_sha256"],
            "fnv1a": simulation_output["frame_fnv1a"],
            "physical_color_codes": sorted(PHYSICAL_COLOR_CODES),
            "usage": simulation_output["usage"],
        },
        "purpose": PreparationPurpose.OFFLINE_PREVIEW.value,
        "formal_upload_authorized": False,
        "authorization_reason": "g1_s1_simulation_offline_preview_only",
        "offline_verified": True,
        "protocol_verified": False,
        "hardware_tested": False,
        "verified_scope": [
            "server_source_byte_hash_and_decode_provenance",
            "G1_continuous_gamut_mapping_simulation",
            "S1_six_colour_halftone_or_DBS_simulation",
            "canonical_frame_dimensions_length_colors_and_hash",
            "four_monitor_preview_byte_hashes",
        ],
        "manual_confirmation_required": {
            item: False for item in MANUAL_CONFIRMATIONS
        },
    }
    return ApplicationArtifact(
        frame,
        result.final_png,
        report,
        False,
        source_preview_png=result.source_png,
        mapped_preview_png=result.mapped_png,
        model_preview_png=result.model_png,
    )


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
    upload_authorized = (
        selected_purpose is PreparationPurpose.FORMAL_UPLOAD
        and selected_palette.calibrated
    )
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
        "quantization_report": quantization,
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
            "calibrated_palette"
            if upload_authorized
            else (
                "calibrated_palette_offline_preview_only"
                if selected_palette.calibrated
                else "reference_palette_offline_preview_only"
            )
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
