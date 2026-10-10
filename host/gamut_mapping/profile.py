"""Strict, versioned gamut-characterization profiles for MF-1750.

The profile is deliberately separate from the six-colour palette.  It binds
to the palette's canonical fingerprint and describes the *model* used for
offline mapping; it never turns a reference palette into a measurement.  A
fingerprint is an audit identity, not a signature or a trust-store decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Tuple

from host.color_pipeline import PIPELINE_VERSION, Palette, reference_palette
from host.epd_frame import PHYSICAL_COLOR_CODES


GAMUT_PROFILE_SCHEMA_VERSION = 1
GAMUT_PROFILE_KIND = "mf1750-gamut-profile"
GAMUT_MAPPER_VERSION = "1.0.0"
GAMUT_PROFILE_CANONICAL_HASH_SCOPE = (
    "entire normalized gamut profile except canonical_sha256; UTF-8 JSON with "
    "sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
GAMUT_PROFILE_FINGERPRINT_TRUST = (
    "audit fingerprint only; not a digital signature or trust-store decision"
)

MODEL_KINDS = frozenset({"linear_xyz_convex_v1", "measured_point_cloud_v1"})
CHARACTERIZATION_LEVELS = frozenset(
    {"reference", "measured_primaries", "measured_mixtures"}
)
# Render-path binding shared with host.color_pipeline.palette: "otp" keeps the
# stock physical frame contract; "l535_r20" binds the measured L535 runtime-LUT
# path whose pure-sample codes are the bound palette's drive nibbles.
RENDER_PATH_OTP = "otp"
RENDER_PATH_L535_R20 = "l535_r20"
RENDER_PATHS = (RENDER_PATH_OTP, RENDER_PATH_L535_R20)
RENDERING_INTENTS = (
    "relative-colorimetric",
    "perceptual",
    "saturation",
)
PRESET_ALIASES = {
    "faithful": "relative-colorimetric",
    "photographic": "perceptual",
    "vivid": "saturation",
}

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_GIT_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
_SEMVER_RE = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\Z")
_PROFILE_ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{2,127}\Z")
_PANEL_MODEL = "MF-17506-M009F-T"
_COLOR_CODES = tuple(sorted(PHYSICAL_COLOR_CODES))
_PROFILE_VALIDATION_TOKEN = object()


class GamutProfileError(ValueError):
    """Raised when a gamut profile is incomplete or internally inconsistent."""


def _mapping(value: Any, *, label: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GamutProfileError(f"{label} must be an object")
    actual = set(value)
    if actual != keys:
        raise GamutProfileError(
            f"{label} keys differ: missing={sorted(keys - actual)}, "
            f"extra={sorted(actual - keys)}"
        )
    return value


def _list(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise GamutProfileError(f"{label} must be a list")
    return value


def _text(value: Any, *, label: str, maximum: int = 4096) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 0x20 for character in value)
    ):
        raise GamutProfileError(f"{label} must be a trimmed non-empty string")
    return value


def _nullable_text(value: Any, *, label: str, maximum: int = 4096) -> str | None:
    if value is None:
        return None
    return _text(value, label=label, maximum=maximum)


def _number(
    value: Any,
    *,
    label: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GamutProfileError(f"{label} must be a JSON number, not boolean")
    result = float(value)
    if not math.isfinite(result):
        raise GamutProfileError(f"{label} must be finite")
    if minimum is not None and result < minimum:
        raise GamutProfileError(f"{label} must be at least {minimum}")
    if maximum is not None and result > maximum:
        raise GamutProfileError(f"{label} must be at most {maximum}")
    return result


def _nullable_number(
    value: Any,
    *,
    label: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    if value is None:
        return None
    return _number(value, label=label, minimum=minimum, maximum=maximum)


def _sha256(value: Any, *, label: str, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise GamutProfileError(f"{label} must be exactly 64 lowercase hex digits")
    return value


def _timestamp(value: Any, *, label: str, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    text = _text(value, label=label, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise GamutProfileError(f"{label} must be an RFC 3339 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GamutProfileError(f"{label} must include a UTC offset")
    return text


def _calendar_date(value: Any, *, label: str, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    text = _text(value, label=label, maximum=10)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as error:
        raise GamutProfileError(f"{label} must be an ISO 8601 calendar date") from error
    if parsed.isoformat() != text:
        raise GamutProfileError(f"{label} must use canonical YYYY-MM-DD form")
    return text


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise GamutProfileError(f"profile is not canonical JSON: {error}") from error


@dataclass(frozen=True)
class RenderingPreset:
    """Versioned tone/chroma trade-offs for one rendering intent."""

    intent: str
    version: str
    tone_gamma: float
    compression_knee: float
    saturation_boost: float
    lightness_weight: float
    chroma_weight: float
    hue_weight: float

    def __post_init__(self) -> None:
        if self.intent not in RENDERING_INTENTS:
            raise GamutProfileError("rendering preset intent is invalid")
        if not isinstance(self.version, str) or _SEMVER_RE.fullmatch(self.version) is None:
            raise GamutProfileError("rendering preset version must be semantic x.y.z")
        values = {
            "tone_gamma": (self.tone_gamma, 0.25, 4.0),
            "compression_knee": (self.compression_knee, 0.0, 1.0),
            "saturation_boost": (self.saturation_boost, 0.0, 1.0),
            "lightness_weight": (self.lightness_weight, 0.0, 10.0),
            "chroma_weight": (self.chroma_weight, 0.0, 10.0),
            "hue_weight": (self.hue_weight, 0.0, 10.0),
        }
        normalized: dict[str, float] = {}
        for label, (value, minimum, maximum) in values.items():
            normalized[label] = _number(
                value, label=f"rendering preset {label}", minimum=minimum, maximum=maximum
            )
        if not any(
            normalized[field] > 0.0
            for field in ("lightness_weight", "chroma_weight", "hue_weight")
        ):
            raise GamutProfileError("rendering preset colour weights cannot all be zero")
        for label, value in normalized.items():
            object.__setattr__(self, label, value)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "tone_gamma": self.tone_gamma,
            "compression_knee": self.compression_knee,
            "saturation_boost": self.saturation_boost,
            "lightness_weight": self.lightness_weight,
            "chroma_weight": self.chroma_weight,
            "hue_weight": self.hue_weight,
        }


@dataclass(frozen=True)
class PureSampleReference:
    code: int
    sample_id: str
    artifact_sha256: str | None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "sample_id": self.sample_id,
            "artifact_sha256": self.artifact_sha256,
        }


@dataclass(frozen=True)
class MixtureSample:
    sample_id: str
    mask_id: str
    area_fractions: Tuple[Tuple[int, float], ...]
    xyz: Tuple[float, float, float]
    artifact_sha256: str

    def to_mapping(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "mask_id": self.mask_id,
            "area_fractions": [
                {"code": code, "fraction": fraction}
                for code, fraction in self.area_fractions
            ],
            "xyz": list(self.xyz),
            "artifact_sha256": self.artifact_sha256,
        }


@dataclass(frozen=True)
class GamutProfile:
    """Validated profile bound to one exact :class:`Palette` fingerprint."""

    profile_id: str
    profile_version: str
    color_pipeline_version: str
    gamut_mapper_version: str
    palette_id: str
    palette_canonical_sha256: str
    model_kind: str
    characterization_level: str
    render_path: str
    approximation: bool
    pure_sample_refs: Tuple[PureSampleReference, ...]
    mixture_samples: Tuple[MixtureSample, ...]
    measurement_id: str | None
    raw_artifact_sha256: str | None
    units: str
    illuminant: str
    observer: str
    geometry: str | None
    backing: str | None
    instrument: str | None
    instrument_calibration_date: str | None
    measured_at: str | None
    panel_model: str
    panel_id: str | None
    panel_batch: str | None
    firmware_commit: str | None
    waveform_version: str | None
    temperature_c: float | None
    temperature_tolerance_c: float | None
    relative_humidity_percent: float | None
    presets: Tuple[RenderingPreset, ...]
    source_statement: str
    signature: str | None
    canonical_sha256: str
    _validation_token: object = field(repr=False, compare=False, default=None)

    def __post_init__(self) -> None:
        if self._validation_token is not _PROFILE_VALIDATION_TOKEN:
            raise GamutProfileError(
                "construct profiles with gamut_profile_from_mapping() or the synthetic builder"
            )
        if hashlib.sha256(self.canonical_bytes()).hexdigest() != self.canonical_sha256:
            raise GamutProfileError(
                "constructed profile canonical_sha256 identity is inconsistent"
            )

    def preset(self, intent: str) -> RenderingPreset:
        normalized = PRESET_ALIASES.get(intent, intent)
        for preset in self.presets:
            if preset.intent == normalized:
                return preset
        raise GamutProfileError(f"profile does not define rendering intent {intent!r}")

    @property
    def provenance_complete_for_formal_use(self) -> bool:
        """Whether required identities are present; this is not trust approval."""

        return (
            self.characterization_level == "measured_mixtures"
            and self.model_kind == "measured_point_cloud_v1"
            and bool(self.mixture_samples)
            and all(item.artifact_sha256 is not None for item in self.pure_sample_refs)
            and all(
                value is not None
                for value in (
                    self.measurement_id,
                    self.raw_artifact_sha256,
                    self.geometry,
                    self.backing,
                    self.instrument,
                    self.instrument_calibration_date,
                    self.measured_at,
                    self.panel_id,
                    self.panel_batch,
                    self.firmware_commit,
                    self.waveform_version,
                    self.temperature_c,
                    self.temperature_tolerance_c,
                    self.relative_humidity_percent,
                )
            )
        )

    @property
    def hardware_formal_qualified(self) -> bool:
        """Always false here: fingerprints are not a measurement trust decision."""

        return False

    @property
    def is_simulation(self) -> bool:
        return self.characterization_level == "reference" or not self.provenance_complete_for_formal_use

    def canonical_payload_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": GAMUT_PROFILE_SCHEMA_VERSION,
            "kind": GAMUT_PROFILE_KIND,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "pipeline_compatibility": {
                "color_pipeline_version": self.color_pipeline_version,
                "gamut_mapper_version": self.gamut_mapper_version,
            },
            "palette": {
                "id": self.palette_id,
                "canonical_sha256": self.palette_canonical_sha256,
            },
            "model": {
                "kind": self.model_kind,
                "characterization_level": self.characterization_level,
                **({"render_path": self.render_path}
                   if self.render_path != RENDER_PATH_OTP else {}),
                "approximation": self.approximation,
                "pure_sample_refs": [item.to_mapping() for item in self.pure_sample_refs],
                "mixture_samples": [item.to_mapping() for item in self.mixture_samples],
            },
            "measurement": {
                "measurement_id": self.measurement_id,
                "raw_artifact_sha256": self.raw_artifact_sha256,
                "units": self.units,
                "illuminant": self.illuminant,
                "observer": self.observer,
                "geometry": self.geometry,
                "backing": self.backing,
                "instrument": self.instrument,
                "instrument_calibration_date": self.instrument_calibration_date,
                "measured_at": self.measured_at,
            },
            "panel": {
                "model": self.panel_model,
                "panel_id": self.panel_id,
                "batch": self.panel_batch,
            },
            "firmware": {
                "commit": self.firmware_commit,
                "waveform_version": self.waveform_version,
            },
            "environment": {
                "temperature_c": self.temperature_c,
                "temperature_tolerance_c": self.temperature_tolerance_c,
                "relative_humidity_percent": self.relative_humidity_percent,
            },
            "rendering_presets": {
                preset.intent: preset.to_mapping() for preset in self.presets
            },
            "trust": {
                "fingerprint_trust": GAMUT_PROFILE_FINGERPRINT_TRUST,
                "source_statement": self.source_statement,
                "signature": self.signature,
            },
        }

    def canonical_mapping(self) -> dict[str, Any]:
        payload = self.canonical_payload_mapping()
        payload["canonical_sha256"] = self.canonical_sha256
        return payload

    def canonical_bytes(self) -> bytes:
        return _canonical_json(self.canonical_payload_mapping())


def seal_profile_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a JSON snapshot with its audit fingerprint attached.

    Sealing is not signing and does not make a profile trusted or calibrated.
    Validation still requires the exact referenced :class:`Palette`.
    """

    if not isinstance(payload, Mapping) or "canonical_sha256" in payload:
        raise GamutProfileError(
            "profile payload must be an object without canonical_sha256"
        )
    try:
        snapshot = json.loads(_canonical_json(payload).decode("utf-8"))
    except json.JSONDecodeError as error:  # pragma: no cover - canonical JSON is valid
        raise GamutProfileError("cannot snapshot profile payload") from error
    snapshot["canonical_sha256"] = hashlib.sha256(_canonical_json(snapshot)).hexdigest()
    return snapshot


def _parse_preset(intent: str, value: Any) -> RenderingPreset:
    preset = _mapping(
        value,
        label=f"rendering_presets.{intent}",
        keys={
            "version",
            "tone_gamma",
            "compression_knee",
            "saturation_boost",
            "lightness_weight",
            "chroma_weight",
            "hue_weight",
        },
    )
    version = _text(preset["version"], label=f"{intent}.version", maximum=32)
    return RenderingPreset(
        intent=intent,
        version=version,
        tone_gamma=_number(preset["tone_gamma"], label=f"{intent}.tone_gamma"),
        compression_knee=_number(
            preset["compression_knee"], label=f"{intent}.compression_knee"
        ),
        saturation_boost=_number(
            preset["saturation_boost"], label=f"{intent}.saturation_boost"
        ),
        lightness_weight=_number(
            preset["lightness_weight"], label=f"{intent}.lightness_weight"
        ),
        chroma_weight=_number(
            preset["chroma_weight"], label=f"{intent}.chroma_weight"
        ),
        hue_weight=_number(preset["hue_weight"], label=f"{intent}.hue_weight"),
    )


def gamut_profile_from_mapping(data: Mapping[str, Any], palette: Palette) -> GamutProfile:
    """Strictly parse and bind one gamut profile to ``palette``."""

    if not isinstance(palette, Palette):
        raise GamutProfileError("palette must be a host.color_pipeline.Palette")
    root = _mapping(
        data,
        label="gamut profile",
        keys={
            "schema_version",
            "kind",
            "profile_id",
            "profile_version",
            "pipeline_compatibility",
            "palette",
            "model",
            "measurement",
            "panel",
            "firmware",
            "environment",
            "rendering_presets",
            "trust",
            "canonical_sha256",
        },
    )
    if type(root["schema_version"]) is not int or root["schema_version"] != GAMUT_PROFILE_SCHEMA_VERSION:
        raise GamutProfileError(
            f"schema_version must be integer {GAMUT_PROFILE_SCHEMA_VERSION}"
        )
    if root["kind"] != GAMUT_PROFILE_KIND:
        raise GamutProfileError("gamut profile kind is invalid")
    profile_id = _text(root["profile_id"], label="profile_id", maximum=128)
    if _PROFILE_ID_RE.fullmatch(profile_id) is None:
        raise GamutProfileError("profile_id contains unsupported characters")
    profile_version = _text(root["profile_version"], label="profile_version", maximum=32)
    if _SEMVER_RE.fullmatch(profile_version) is None:
        raise GamutProfileError("profile_version must be semantic x.y.z")

    compatibility = _mapping(
        root["pipeline_compatibility"],
        label="pipeline_compatibility",
        keys={"color_pipeline_version", "gamut_mapper_version"},
    )
    color_pipeline_version = _text(
        compatibility["color_pipeline_version"], label="color_pipeline_version", maximum=32
    )
    gamut_mapper_version = _text(
        compatibility["gamut_mapper_version"], label="gamut_mapper_version", maximum=32
    )
    if color_pipeline_version != PIPELINE_VERSION:
        raise GamutProfileError(
            f"profile requires color pipeline {color_pipeline_version}; running {PIPELINE_VERSION}"
        )
    if gamut_mapper_version != GAMUT_MAPPER_VERSION:
        raise GamutProfileError(
            f"profile requires gamut mapper {gamut_mapper_version}; running {GAMUT_MAPPER_VERSION}"
        )

    palette_binding = _mapping(
        root["palette"], label="palette binding", keys={"id", "canonical_sha256"}
    )
    palette_id = _text(palette_binding["id"], label="palette.id", maximum=128)
    palette_sha = _sha256(
        palette_binding["canonical_sha256"], label="palette.canonical_sha256"
    )
    if palette_id != palette.palette_id or palette_sha != palette.canonical_sha256:
        raise GamutProfileError("profile palette identity does not match the supplied palette")

    model = _mapping(
        root["model"],
        label="model",
        keys=(
            {
                "kind",
                "characterization_level",
                "approximation",
                "pure_sample_refs",
                "mixture_samples",
            }
            | ({"render_path"}
               if "render_path" in root["model"] else set())
        ),
    )
    render_path = model.get("render_path", RENDER_PATH_OTP)
    if not isinstance(render_path, str) or render_path not in RENDER_PATHS:
        raise GamutProfileError(f"model.render_path must be one of {list(RENDER_PATHS)}")
    palette_render_path = getattr(palette, "render_path", RENDER_PATH_OTP)
    if render_path != palette_render_path:
        raise GamutProfileError("profile render_path does not match the bound palette")
    allowed_codes = (
        tuple(sorted(entry.code for entry in palette.entries))
        if render_path == RENDER_PATH_L535_R20
        else _COLOR_CODES
    )
    model_kind = model["kind"]
    if model_kind not in MODEL_KINDS:
        raise GamutProfileError("model.kind is unsupported")
    characterization = model["characterization_level"]
    if characterization not in CHARACTERIZATION_LEVELS:
        raise GamutProfileError("model.characterization_level is unsupported")
    if type(model["approximation"]) is not bool:
        raise GamutProfileError("model.approximation must be boolean")
    approximation = model["approximation"]
    if model_kind == "linear_xyz_convex_v1" and approximation is not True:
        raise GamutProfileError("linear_xyz_convex_v1 must be marked approximation=true")
    if model_kind == "measured_point_cloud_v1" and characterization != "measured_mixtures":
        raise GamutProfileError("measured_point_cloud_v1 requires measured_mixtures")

    pure_rows = _list(model["pure_sample_refs"], label="model.pure_sample_refs")
    if len(pure_rows) != len(allowed_codes):
        raise GamutProfileError("pure_sample_refs must contain exactly six entries")
    pure_refs: list[PureSampleReference] = []
    seen_sample_ids: set[str] = set()
    for index, raw in enumerate(pure_rows):
        row = _mapping(
            raw,
            label=f"pure_sample_refs[{index}]",
            keys={"code", "sample_id", "artifact_sha256"},
        )
        code = row["code"]
        if type(code) is not int or code not in allowed_codes:
            raise GamutProfileError(f"pure_sample_refs[{index}].code is invalid")
        sample_id = _text(
            row["sample_id"], label=f"pure_sample_refs[{index}].sample_id", maximum=256
        )
        if sample_id in seen_sample_ids:
            raise GamutProfileError("sample IDs must be unique across the profile")
        seen_sample_ids.add(sample_id)
        artifact = _sha256(
            row["artifact_sha256"],
            label=f"pure_sample_refs[{index}].artifact_sha256",
            nullable=True,
        )
        pure_refs.append(PureSampleReference(code, sample_id, artifact))
    pure_refs.sort(key=lambda item: item.code)
    if tuple(item.code for item in pure_refs) != allowed_codes:
        raise GamutProfileError("pure_sample_refs must bind each legal code once")

    mixture_rows = _list(model["mixture_samples"], label="model.mixture_samples")
    mixtures: list[MixtureSample] = []
    seen_mixture_signatures: set[tuple[Any, ...]] = set()
    for index, raw in enumerate(mixture_rows):
        row = _mapping(
            raw,
            label=f"mixture_samples[{index}]",
            keys={"sample_id", "mask_id", "area_fractions", "xyz", "artifact_sha256"},
        )
        sample_id = _text(
            row["sample_id"], label=f"mixture_samples[{index}].sample_id", maximum=256
        )
        if sample_id in seen_sample_ids:
            raise GamutProfileError("sample IDs must be unique across the profile")
        seen_sample_ids.add(sample_id)
        mask_id = _text(
            row["mask_id"], label=f"mixture_samples[{index}].mask_id", maximum=256
        )
        fractions_raw = _list(
            row["area_fractions"], label=f"mixture_samples[{index}].area_fractions"
        )
        if not 2 <= len(fractions_raw) <= len(allowed_codes):
            raise GamutProfileError("mixture area_fractions must use two through six colours")
        fractions: list[tuple[int, float]] = []
        seen_codes: set[int] = set()
        for fraction_index, raw_fraction in enumerate(fractions_raw):
            fraction_row = _mapping(
                raw_fraction,
                label=f"mixture {index} fraction {fraction_index}",
                keys={"code", "fraction"},
            )
            code = fraction_row["code"]
            if type(code) is not int or code not in allowed_codes or code in seen_codes:
                raise GamutProfileError("mixture fraction codes must be unique legal integers")
            seen_codes.add(code)
            fraction = _number(
                fraction_row["fraction"],
                label=f"mixture {index} code {code} fraction",
                minimum=0.0,
                maximum=1.0,
            )
            if fraction == 0.0:
                raise GamutProfileError("mixture fractions must be positive; omit zero entries")
            fractions.append((code, fraction))
        fractions.sort(key=lambda item: item[0])
        if not math.isclose(sum(value for _, value in fractions), 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise GamutProfileError("mixture area fractions must sum to one")

        xyz_raw = row["xyz"]
        if not isinstance(xyz_raw, list) or len(xyz_raw) != 3:
            raise GamutProfileError("mixture xyz must contain exactly three numbers")
        xyz = tuple(
            _number(value, label=f"mixture {index} xyz[{channel}]", minimum=0.0, maximum=2.0)
            for channel, value in enumerate(xyz_raw)
        )
        artifact = _sha256(
            row["artifact_sha256"], label=f"mixture_samples[{index}].artifact_sha256"
        )
        signature = (mask_id, tuple(fractions))
        if signature in seen_mixture_signatures:
            raise GamutProfileError("duplicate mixture mask/area-fraction sample")
        seen_mixture_signatures.add(signature)
        mixtures.append(
            MixtureSample(sample_id, mask_id, tuple(fractions), xyz, artifact)  # type: ignore[arg-type]
        )
    mixtures.sort(key=lambda item: item.sample_id)
    if characterization == "reference" and mixtures:
        raise GamutProfileError("reference profiles cannot contain measured mixture samples")
    if characterization == "measured_mixtures" and not mixtures:
        raise GamutProfileError("measured_mixtures requires at least one mixture sample")

    measurement = _mapping(
        root["measurement"],
        label="measurement",
        keys={
            "measurement_id",
            "raw_artifact_sha256",
            "units",
            "illuminant",
            "observer",
            "geometry",
            "backing",
            "instrument",
            "instrument_calibration_date",
            "measured_at",
        },
    )
    measurement_id = _nullable_text(
        measurement["measurement_id"], label="measurement.measurement_id", maximum=256
    )
    raw_artifact = _sha256(
        measurement["raw_artifact_sha256"],
        label="measurement.raw_artifact_sha256",
        nullable=True,
    )
    if measurement["units"] != "relative_cie_xyz_y1":
        raise GamutProfileError("measurement.units must be relative_cie_xyz_y1")
    if measurement["illuminant"] != "D65" or measurement["observer"] != "2deg":
        raise GamutProfileError("gamut profiles require D65/2deg data")
    geometry = _nullable_text(measurement["geometry"], label="measurement.geometry")
    backing = _nullable_text(measurement["backing"], label="measurement.backing")
    instrument = _nullable_text(measurement["instrument"], label="measurement.instrument")
    calibration_date = _calendar_date(
        measurement["instrument_calibration_date"],
        label="measurement.instrument_calibration_date",
        nullable=True,
    )
    measured_at = _timestamp(
        measurement["measured_at"], label="measurement.measured_at", nullable=True
    )

    panel = _mapping(root["panel"], label="panel", keys={"model", "panel_id", "batch"})
    if panel["model"] != _PANEL_MODEL:
        raise GamutProfileError(f"panel.model must be {_PANEL_MODEL}")
    panel_id = _nullable_text(panel["panel_id"], label="panel.panel_id", maximum=256)
    panel_batch = _nullable_text(panel["batch"], label="panel.batch", maximum=256)

    firmware = _mapping(
        root["firmware"], label="firmware", keys={"commit", "waveform_version"}
    )
    firmware_commit = firmware["commit"]
    if firmware_commit is not None and (
        not isinstance(firmware_commit, str) or _GIT_SHA_RE.fullmatch(firmware_commit) is None
    ):
        raise GamutProfileError("firmware.commit must be null or 40 lowercase hex digits")
    waveform_version = _nullable_text(
        firmware["waveform_version"], label="firmware.waveform_version", maximum=256
    )

    environment = _mapping(
        root["environment"],
        label="environment",
        keys={"temperature_c", "temperature_tolerance_c", "relative_humidity_percent"},
    )
    temperature = _nullable_number(
        environment["temperature_c"], label="environment.temperature_c", minimum=-40, maximum=100
    )
    temperature_tolerance = _nullable_number(
        environment["temperature_tolerance_c"],
        label="environment.temperature_tolerance_c",
        minimum=0,
        maximum=30,
    )
    humidity = _nullable_number(
        environment["relative_humidity_percent"],
        label="environment.relative_humidity_percent",
        minimum=0,
        maximum=100,
    )

    presets_raw = _mapping(
        root["rendering_presets"],
        label="rendering_presets",
        keys=set(RENDERING_INTENTS),
    )
    presets = tuple(_parse_preset(intent, presets_raw[intent]) for intent in RENDERING_INTENTS)

    trust = _mapping(
        root["trust"],
        label="trust",
        keys={"fingerprint_trust", "source_statement", "signature"},
    )
    if trust["fingerprint_trust"] != GAMUT_PROFILE_FINGERPRINT_TRUST:
        raise GamutProfileError("trust.fingerprint_trust statement is invalid")
    source_statement = _text(
        trust["source_statement"], label="trust.source_statement", maximum=4096
    )
    signature = _nullable_text(trust["signature"], label="trust.signature", maximum=4096)

    reference_nulls = (
        measurement_id,
        raw_artifact,
        geometry,
        backing,
        instrument,
        calibration_date,
        measured_at,
        panel_id,
        panel_batch,
        firmware_commit,
        waveform_version,
        temperature,
        temperature_tolerance,
        humidity,
        signature,
    )
    if characterization == "reference":
        if any(value is not None for value in reference_nulls):
            raise GamutProfileError(
                "reference profile must keep measurement/hardware identities explicitly null"
            )
        if any(item.artifact_sha256 is not None for item in pure_refs):
            raise GamutProfileError("reference pure-sample artifact hashes must be null")
    else:
        required_measurement = (
            measurement_id,
            raw_artifact,
            geometry,
            backing,
            instrument,
            calibration_date,
            measured_at,
            panel_id,
            panel_batch,
            firmware_commit,
            waveform_version,
            temperature,
            temperature_tolerance,
            humidity,
        )
        if any(value is None for value in required_measurement):
            raise GamutProfileError(
                "measured characterization requires complete measurement, panel, firmware and environment provenance"
            )
        if any(item.artifact_sha256 is None for item in pure_refs):
            raise GamutProfileError("measured characterization requires every pure-sample artifact hash")

    canonical_sha = _sha256(root["canonical_sha256"], label="canonical_sha256")
    profile = GamutProfile(
        profile_id=profile_id,
        profile_version=profile_version,
        color_pipeline_version=color_pipeline_version,
        gamut_mapper_version=gamut_mapper_version,
        palette_id=palette_id,
        palette_canonical_sha256=palette_sha,  # type: ignore[arg-type]
        model_kind=model_kind,
        characterization_level=characterization,
        render_path=render_path,
        approximation=approximation,
        pure_sample_refs=tuple(pure_refs),
        mixture_samples=tuple(mixtures),
        measurement_id=measurement_id,
        raw_artifact_sha256=raw_artifact,
        units=measurement["units"],
        illuminant=measurement["illuminant"],
        observer=measurement["observer"],
        geometry=geometry,
        backing=backing,
        instrument=instrument,
        instrument_calibration_date=calibration_date,
        measured_at=measured_at,
        panel_model=panel["model"],
        panel_id=panel_id,
        panel_batch=panel_batch,
        firmware_commit=firmware_commit,
        waveform_version=waveform_version,
        temperature_c=temperature,
        temperature_tolerance_c=temperature_tolerance,
        relative_humidity_percent=humidity,
        presets=presets,
        source_statement=source_statement,
        signature=signature,
        canonical_sha256=canonical_sha,  # type: ignore[arg-type]
        _validation_token=_PROFILE_VALIDATION_TOKEN,
    )
    if profile.canonical_payload_mapping() != {key: value for key, value in root.items() if key != "canonical_sha256"}:
        raise GamutProfileError("gamut profile is not in canonical normalized form")
    expected_sha = hashlib.sha256(profile.canonical_bytes()).hexdigest()
    if canonical_sha != expected_sha:
        raise GamutProfileError("gamut profile canonical_sha256 does not match its content")
    return profile


def load_gamut_profile(path: str | Path, palette: Palette) -> GamutProfile:
    profile_path = Path(path)

    def reject_constant(value: str) -> None:
        raise GamutProfileError(f"profile JSON constant {value} is not permitted")

    try:
        data = json.loads(
            profile_path.read_text(encoding="utf-8"), parse_constant=reject_constant
        )
    except GamutProfileError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GamutProfileError(f"cannot load gamut profile {profile_path}: {error}") from error
    return gamut_profile_from_mapping(data, palette)


def build_synthetic_reference_profile(palette: Palette | None = None) -> GamutProfile:
    """Build the explicit uncalibrated convex-hull simulation profile."""

    selected = reference_palette() if palette is None else palette
    if not isinstance(selected, Palette):
        raise GamutProfileError("palette must be a host.color_pipeline.Palette")
    if selected.calibrated:
        raise GamutProfileError(
            "synthetic reference profile cannot be attached to a calibrated palette"
        )
    payload: dict[str, Any] = {
        "schema_version": GAMUT_PROFILE_SCHEMA_VERSION,
        "kind": GAMUT_PROFILE_KIND,
        "profile_id": "synthetic-reference-linear-xyz-v1",
        "profile_version": "1.0.0",
        "pipeline_compatibility": {
            "color_pipeline_version": PIPELINE_VERSION,
            "gamut_mapper_version": GAMUT_MAPPER_VERSION,
        },
        "palette": {
            "id": selected.palette_id,
            "canonical_sha256": selected.canonical_sha256,
        },
        "model": {
            "kind": "linear_xyz_convex_v1",
            "characterization_level": "reference",
            "approximation": True,
            "pure_sample_refs": [
                {
                    "code": code,
                    "sample_id": f"{selected.palette_id}-code-{code}",
                    "artifact_sha256": None,
                }
                for code in _COLOR_CODES
            ],
            "mixture_samples": [],
        },
        "measurement": {
            "measurement_id": None,
            "raw_artifact_sha256": None,
            "units": "relative_cie_xyz_y1",
            "illuminant": "D65",
            "observer": "2deg",
            "geometry": None,
            "backing": None,
            "instrument": None,
            "instrument_calibration_date": None,
            "measured_at": None,
        },
        "panel": {"model": _PANEL_MODEL, "panel_id": None, "batch": None},
        "firmware": {"commit": None, "waveform_version": None},
        "environment": {
            "temperature_c": None,
            "temperature_tolerance_c": None,
            "relative_humidity_percent": None,
        },
        "rendering_presets": {
            "relative-colorimetric": {
                "version": "1.0.0",
                "tone_gamma": 1.0,
                "compression_knee": 1.0,
                "saturation_boost": 0.0,
                "lightness_weight": 1.0,
                "chroma_weight": 1.0,
                "hue_weight": 1.0,
            },
            "perceptual": {
                "version": "1.0.0",
                "tone_gamma": 0.92,
                "compression_knee": 0.72,
                "saturation_boost": 0.0,
                "lightness_weight": 1.25,
                "chroma_weight": 0.85,
                "hue_weight": 1.35,
            },
            "saturation": {
                "version": "1.0.0",
                "tone_gamma": 1.0,
                "compression_knee": 0.88,
                "saturation_boost": 0.18,
                "lightness_weight": 0.8,
                "chroma_weight": 1.5,
                "hue_weight": 0.75,
            },
        },
        "trust": {
            "fingerprint_trust": GAMUT_PROFILE_FINGERPRINT_TRUST,
            "source_statement": (
                "Synthetic uncalibrated D65/2deg model derived only from the bound "
                "palette; offline monitor simulation, not MF-1750 measurement"
            ),
            "signature": None,
        },
    }
    return gamut_profile_from_mapping(seal_profile_mapping(payload), selected)


__all__ = [
    "CHARACTERIZATION_LEVELS",
    "GAMUT_MAPPER_VERSION",
    "GAMUT_PROFILE_CANONICAL_HASH_SCOPE",
    "GAMUT_PROFILE_FINGERPRINT_TRUST",
    "GAMUT_PROFILE_KIND",
    "GAMUT_PROFILE_SCHEMA_VERSION",
    "MODEL_KINDS",
    "PRESET_ALIASES",
    "RENDERING_INTENTS",
    "GamutProfile",
    "GamutProfileError",
    "MixtureSample",
    "PureSampleReference",
    "RenderingPreset",
    "build_synthetic_reference_profile",
    "gamut_profile_from_mapping",
    "load_gamut_profile",
    "seal_profile_mapping",
]
