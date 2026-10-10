"""Deterministic pre-dither tone and gamut mapping.

The public :func:`map_raster` entry point accepts the existing canonical
``RasterImage``/``Palette`` types and returns another ``RasterImage`` suitable
for C2 quantization.  ``mode=none`` (and its ``legacy`` alias) returns the
original raster bytes and mode exactly.  The mapped path uses a bounded colour
cache and a precomputed 3-D convex-hull representation; it has no device I/O or
third-party dependency.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import itertools
import json
import math
from typing import Any, Mapping, Sequence, Tuple

from host.color_pipeline import Palette, RasterImage, encode_rgb_png
from host.color_pipeline.color import (
    Lab,
    LinearRGB,
    SRGB8_TO_LINEAR,
    lab_to_xyz,
    linear_channel_to_srgb,
    linear_rgb_to_lab,
    xyz_to_lab,
    xyz_to_linear_rgb,
)

from .profile import (
    GAMUT_MAPPER_VERSION,
    GAMUT_PROFILE_CANONICAL_HASH_SCOPE,
    PRESET_ALIASES,
    GamutProfile,
    RenderingPreset,
)


MAPPING_REPORT_SCHEMA_VERSION = 1
MAPPING_REPORT_KIND = "mf1750-gamut-mapping-report"
MAPPED_RASTER_ENCODING = "linear-srgb-u16be-v1"
LEGACY_RASTER_ENCODING = "legacy-decoded-raster-bytes-v1"
MAPPED_RASTER_CANONICAL_HASH_SCOPE = (
    "canonical UTF-8 JSON identity header, one LF byte, then tightly packed "
    "row-major mapped raster bytes in the declared encoding"
)
MAPPING_REPORT_CANONICAL_HASH_SCOPE = (
    "entire mapping report excluding report_integrity; UTF-8 JSON with sorted "
    "keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
SOFT_PROOF_WARNING = (
    "Monitor simulation only; preview RGB cannot reproduce reflective panel colour, "
    "illumination, viewing geometry, texture, ghosting or waveform history."
)


class GamutMappingError(ValueError):
    """Raised when mapping inputs or identities violate the G1 contract."""


class MappingMode(str, Enum):
    NONE = "none"
    GAMUT_MAP = "gamut-map"


class RenderingIntent(str, Enum):
    RELATIVE_COLORIMETRIC = "relative-colorimetric"
    PERCEPTUAL = "perceptual"
    SATURATION = "saturation"


def _finite(value: Any, *, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GamutMappingError(f"{label} must be numeric and not boolean")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise GamutMappingError(f"{label} must be finite and in [{minimum}, {maximum}]")
    return result


def _lab(value: Sequence[float], *, label: str = "Lab") -> Lab:
    try:
        values = tuple(value)
    except TypeError as error:
        raise GamutMappingError(f"{label} must contain exactly three numbers") from error
    if len(values) != 3:
        raise GamutMappingError(f"{label} must contain exactly three numbers")
    result = tuple(
        _finite(component, label=f"{label}[{index}]", minimum=-200.0, maximum=200.0)
        for index, component in enumerate(values)
    )
    # The canonical sRGB->XYZ matrix yields white at L*=100.0000039 because
    # its rounded Y coefficients sum to 1.0000001.  Accept only that tiny
    # conversion tolerance and normalize it before identity/report use.
    if not -1e-5 <= result[0] <= 100.00001:
        raise GamutMappingError(f"{label} lightness must be in [0, 100]")
    return (min(100.0, max(0.0, result[0])), result[1], result[2])


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
        raise GamutMappingError(f"mapping report is not canonical JSON: {error}") from error


def _normalize_mode(value: MappingMode | str) -> MappingMode:
    if value == "legacy":
        return MappingMode.NONE
    try:
        return value if isinstance(value, MappingMode) else MappingMode(value)
    except (TypeError, ValueError) as error:
        raise GamutMappingError("mode must be none/legacy or gamut-map") from error


def _normalize_intent(value: RenderingIntent | str) -> RenderingIntent:
    if isinstance(value, str):
        value = PRESET_ALIASES.get(value, value)
    try:
        return value if isinstance(value, RenderingIntent) else RenderingIntent(value)
    except (TypeError, ValueError) as error:
        raise GamutMappingError(
            "intent must be relative-colorimetric/faithful, perceptual/photographic, "
            "or saturation/vivid"
        ) from error


@dataclass(frozen=True)
class MappingOptions:
    mode: MappingMode | str = MappingMode.GAMUT_MAP
    intent: RenderingIntent | str = RenderingIntent.PERCEPTUAL
    strength: float = 1.0
    cache_entries: int = 65536

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", _normalize_mode(self.mode))
        object.__setattr__(self, "intent", _normalize_intent(self.intent))
        object.__setattr__(
            self,
            "strength",
            _finite(self.strength, label="mapping strength", minimum=0.0, maximum=1.0),
        )
        if (
            type(self.cache_entries) is not int
            or not 0 <= self.cache_entries <= 262144
        ):
            raise GamutMappingError("cache_entries must be an integer in [0, 262144]")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "intent": self.intent.value,
            "strength": self.strength,
            "cache_entries": self.cache_entries,
        }


def map_lightness(
    lightness: float,
    black_lightness: float,
    white_lightness: float,
    *,
    tone_gamma: float,
    strength: float = 1.0,
) -> float:
    """Map source L* monotonically into a profile's black/white range."""

    source = _finite(lightness, label="source lightness", minimum=0.0, maximum=100.0)
    black = _finite(
        black_lightness, label="black lightness", minimum=0.0, maximum=100.0
    )
    white = _finite(
        white_lightness, label="white lightness", minimum=0.0, maximum=100.0
    )
    gamma = _finite(tone_gamma, label="tone gamma", minimum=0.25, maximum=4.0)
    amount = _finite(strength, label="mapping strength", minimum=0.0, maximum=1.0)
    if black >= white:
        raise GamutMappingError("black lightness must be lower than white lightness")
    target = black + (white - black) * ((source / 100.0) ** gamma)
    return source + amount * (target - source)


def _dot(first: Sequence[float], second: Sequence[float]) -> float:
    return first[0] * second[0] + first[1] * second[1] + first[2] * second[2]


def _subtract(first: Sequence[float], second: Sequence[float]) -> Tuple[float, float, float]:
    return (first[0] - second[0], first[1] - second[1], first[2] - second[2])


def _cross(first: Sequence[float], second: Sequence[float]) -> Tuple[float, float, float]:
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


class _ConvexHull:
    """Small deterministic 3-D half-space hull; six primaries are typical."""

    _EPSILON = 1e-11

    def __init__(self, points: Sequence[Sequence[float]]) -> None:
        normalized = tuple(tuple(float(channel) for channel in point) for point in points)
        if len(normalized) < 4 or any(len(point) != 3 for point in normalized):
            raise GamutMappingError("gamut model requires at least four 3-D XYZ points")
        if not all(math.isfinite(value) for point in normalized for value in point):
            raise GamutMappingError("gamut model XYZ points must be finite")
        self.points = normalized
        centroid = tuple(
            sum(point[channel] for point in normalized) / len(normalized)
            for channel in range(3)
        )
        facets: list[tuple[Tuple[float, float, float], float]] = []
        seen: set[tuple[int, int, int, int]] = set()
        for first, second, third in itertools.combinations(normalized, 3):
            normal = _cross(_subtract(second, first), _subtract(third, first))
            length = math.sqrt(_dot(normal, normal))
            if length <= self._EPSILON:
                continue
            unit = tuple(value / length for value in normal)
            offset = _dot(unit, first)
            distances = [_dot(unit, point) - offset for point in normalized]
            if not (
                max(distances) <= self._EPSILON
                or min(distances) >= -self._EPSILON
            ):
                continue
            if _dot(unit, centroid) > offset:
                unit = tuple(-value for value in unit)
                offset = -offset
            key = tuple(int(round(value * 1e10)) for value in (*unit, offset))
            if key not in seen:
                seen.add(key)
                facets.append((unit, offset))
        if len(facets) < 4:
            raise GamutMappingError("gamut model points do not span a bounded 3-D hull")
        self.facets = tuple(sorted(facets, key=lambda item: (*item[0], item[1])))

    def contains(self, xyz: Sequence[float], *, tolerance: float = 1e-9) -> bool:
        return all(_dot(normal, xyz) <= offset + tolerance for normal, offset in self.facets)

    def ray_limit(self, origin: Sequence[float], direction: Sequence[float]) -> float:
        if not self.contains(origin, tolerance=1e-8):
            raise GamutMappingError("internal neutral-axis origin lies outside gamut hull")
        limit = math.inf
        for normal, offset in self.facets:
            speed = _dot(normal, direction)
            if speed > self._EPSILON:
                candidate = (offset - _dot(normal, origin)) / speed
                limit = min(limit, max(0.0, candidate))
        if not math.isfinite(limit):
            raise GamutMappingError("gamut hull ray did not intersect a boundary")
        return limit


@dataclass(frozen=True)
class MappedColor:
    source_lab: Lab
    tone_mapped_lab: Lab
    mapped_lab: Lab
    mapped_xyz: Tuple[float, float, float]
    in_gamut_after_tone: bool
    boundary_scale: float
    applied_scale: float
    tone_delta_l: float
    chroma_compression: float
    display_linear_rgb: LinearRGB
    display_clipped: bool
    numeric_fallback: bool


class GamutMapper:
    """Reusable per-colour mapper with a precomputed target-gamut hull."""

    def __init__(self, palette: Palette, profile: GamutProfile) -> None:
        if not isinstance(palette, Palette):
            raise GamutMappingError("palette must be a host.color_pipeline.Palette")
        if not isinstance(profile, GamutProfile):
            raise GamutMappingError("profile must be a GamutProfile")
        if (
            profile.palette_id != palette.palette_id
            or profile.palette_canonical_sha256 != palette.canonical_sha256
        ):
            raise GamutMappingError("profile does not bind the supplied palette")
        points = [lab_to_xyz(entry.lab) for entry in palette.entries]
        if profile.model_kind == "measured_point_cloud_v1":
            points.extend(sample.xyz for sample in profile.mixture_samples)
        self.palette = palette
        self.profile = profile
        self._hull = _ConvexHull(points)
        self._black_lab = palette.entry(0).lab
        self._white_lab = palette.entry(1).lab
        self._black_xyz = lab_to_xyz(self._black_lab)
        self._white_xyz = lab_to_xyz(self._white_lab)

    def contains_xyz(self, xyz: Sequence[float], *, tolerance: float = 1e-9) -> bool:
        try:
            values = tuple(float(value) for value in xyz)
        except (TypeError, ValueError) as error:
            raise GamutMappingError("XYZ must contain exactly three finite numbers") from error
        if len(values) != 3 or not all(math.isfinite(value) for value in values):
            raise GamutMappingError("XYZ must contain exactly three finite numbers")
        return self._hull.contains(values, tolerance=tolerance)

    def contains_lab(self, lab: Sequence[float], *, tolerance: float = 1e-9) -> bool:
        return self.contains_xyz(lab_to_xyz(_lab(lab)), tolerance=tolerance)

    def _neutral_xyz(self, lightness: float) -> Tuple[float, float, float]:
        # Lab L* depends only on XYZ Y.  Interpolate the measured black/white
        # line by the Y required for this L*, rather than linearly interpolating
        # L* itself (which would introduce a large lightness error).
        target_y = lab_to_xyz((lightness, 0.0, 0.0))[1]
        y_span = self._white_xyz[1] - self._black_xyz[1]
        if y_span <= 0.0:
            raise GamutMappingError("profile black/white XYZ luminance order is invalid")
        position = min(1.0, max(0.0, (target_y - self._black_xyz[1]) / y_span))
        return tuple(
            self._black_xyz[channel]
            + position * (self._white_xyz[channel] - self._black_xyz[channel])
            for channel in range(3)
        )  # type: ignore[return-value]

    @staticmethod
    def _scale_for_intent(
        boundary: float,
        preset: RenderingPreset,
        intent: RenderingIntent,
        strength: float,
    ) -> float:
        boundary = max(0.0, boundary)
        if boundary <= 1e-15:
            return 0.0
        if intent is RenderingIntent.RELATIVE_COLORIMETRIC:
            return min(1.0, boundary)
        if intent is RenderingIntent.SATURATION:
            return min(boundary, 1.0 + preset.saturation_boost * strength)

        # Perceptual soft compression is expressed in normalized radial gamut
        # occupancy.  It is identity below the knee, continuous at the knee,
        # and asymptotically approaches (but never exceeds) the hull boundary.
        occupancy = 1.0 / boundary
        knee = preset.compression_knee
        if occupancy <= knee or knee >= 1.0:
            full_scale = 1.0
        else:
            span = max(1e-12, 1.0 - knee)
            compressed_occupancy = knee + span * (
                1.0 - math.exp(-(occupancy - knee) / span)
            )
            compressed_occupancy = min(1.0, compressed_occupancy)
            full_scale = compressed_occupancy / occupancy
        blended = 1.0 + strength * (full_scale - 1.0)
        # Out-of-gamut colours are always brought inside even at strength=0;
        # strength controls only additional soft compression.
        return min(boundary, blended)

    def map_lab(
        self,
        lab: Sequence[float],
        *,
        intent: RenderingIntent | str = RenderingIntent.PERCEPTUAL,
        strength: float = 1.0,
    ) -> MappedColor:
        source = _lab(lab)
        selected_intent = _normalize_intent(intent)
        amount = _finite(strength, label="mapping strength", minimum=0.0, maximum=1.0)
        preset = self.profile.preset(selected_intent.value)
        mapped_l = map_lightness(
            source[0],
            self._black_lab[0],
            self._white_lab[0],
            tone_gamma=preset.tone_gamma,
            strength=amount,
        )
        toned = (mapped_l, source[1], source[2])
        target_xyz = lab_to_xyz(toned)
        neutral = self._neutral_xyz(mapped_l)
        direction = _subtract(target_xyz, neutral)
        if _dot(direction, direction) <= 1e-24:
            boundary = 1.0
            in_gamut = True
            scale = 1.0
        else:
            boundary = self._hull.ray_limit(neutral, direction)
            in_gamut = boundary >= 1.0 - 1e-10
            scale = self._scale_for_intent(boundary, preset, selected_intent, amount)
        mapped_xyz = tuple(
            neutral[channel] + scale * direction[channel] for channel in range(3)
        )
        numeric_fallback = False
        if not self._hull.contains(mapped_xyz, tolerance=2e-9):
            # Numerical guard: retreat by a tiny deterministic factor.  This is
            # a bounded floating-point fallback, never a palette guess.
            numeric_fallback = True
            scale *= 1.0 - 1e-10
            mapped_xyz = tuple(
                neutral[channel] + scale * direction[channel] for channel in range(3)
            )
            if not self._hull.contains(mapped_xyz, tolerance=2e-9):
                raise GamutMappingError("mapped colour failed the declared hull bound")
        mapped_lab = xyz_to_lab(mapped_xyz)
        raw_display = xyz_to_linear_rgb(mapped_xyz)
        display_clipped = any(value < 0.0 or value > 1.0 for value in raw_display)
        display = tuple(min(1.0, max(0.0, value)) for value in raw_display)
        source_chroma = math.hypot(toned[1], toned[2])
        mapped_chroma = math.hypot(mapped_lab[1], mapped_lab[2])
        return MappedColor(
            source_lab=source,
            tone_mapped_lab=toned,
            mapped_lab=mapped_lab,
            mapped_xyz=mapped_xyz,  # type: ignore[arg-type]
            in_gamut_after_tone=in_gamut,
            boundary_scale=boundary,
            applied_scale=scale,
            tone_delta_l=mapped_l - source[0],
            chroma_compression=max(0.0, source_chroma - mapped_chroma),
            display_linear_rgb=display,  # type: ignore[arg-type]
            display_clipped=display_clipped,
            numeric_fallback=numeric_fallback,
        )


@dataclass(frozen=True, init=False)
class GamutMappingReport:
    _payload_json: bytes = field(repr=False)

    def __init__(self, payload: Mapping[str, Any]) -> None:
        if not isinstance(payload, Mapping):
            raise GamutMappingError("mapping report payload must be an object")
        object.__setattr__(self, "_payload_json", _canonical_json(payload))
        # The helper is defined later in the module but is available whenever
        # public construction occurs after import has completed.
        validate_mapping_report(self.to_dict())

    @property
    def payload(self) -> dict[str, Any]:
        """Return a fresh snapshot; callers cannot mutate stored evidence."""

        return json.loads(self._payload_json.decode("utf-8"))

    def to_dict(self) -> dict[str, Any]:
        snapshot = self.payload
        canonical = self._payload_json
        snapshot["report_integrity"] = {
            "canonical_sha256": hashlib.sha256(canonical).hexdigest(),
            "canonical_sha256_scope": MAPPING_REPORT_CANONICAL_HASH_SCOPE,
            "fingerprint_trust": (
                "audit fingerprint only; not a digital signature or trust-store decision"
            ),
        }
        return snapshot


def _source_preview_rgb(image: RasterImage) -> bytes:
    output = bytearray(image.width * image.height * 3)
    channels = image.channels
    for index in range(image.width * image.height):
        source = index * channels
        target = index * 3
        if channels == 3:
            output[target : target + 3] = image.pixels[source : source + 3]
            continue
        alpha = image.pixels[source + 3] / 255.0
        inverse = 1.0 - alpha
        for channel in range(3):
            linear = SRGB8_TO_LINEAR[image.pixels[source + channel]] * alpha + inverse
            output[target + channel] = min(
                255,
                max(0, int(math.floor(linear_channel_to_srgb(linear) * 255.0 + 0.5))),
            )
    return bytes(output)


@dataclass(frozen=True)
class GamutMappingResult:
    source_image: RasterImage
    mapped_image: RasterImage
    mapped_linear_u16be: bytes
    options: MappingOptions
    profile: GamutProfile | None
    report: GamutMappingReport

    @property
    def mapped_raster_identity(self) -> dict[str, Any]:
        return self.report.to_dict()["mapped_raster"]

    def source_preview_rgb(self) -> bytes:
        return _source_preview_rgb(self.source_image)

    def source_preview_png(self) -> bytes:
        return encode_rgb_png(
            self.source_image.width, self.source_image.height, self.source_preview_rgb()
        )

    def mapped_preview_rgb(self) -> bytes:
        return _source_preview_rgb(self.mapped_image)

    def mapped_preview_png(self) -> bytes:
        return encode_rgb_png(
            self.mapped_image.width, self.mapped_image.height, self.mapped_preview_rgb()
        )

    def validated_snapshot(self) -> "GamutMappingResult":
        """Revalidate byte and report identities before an application consumes them."""

        validate_mapping_result(self)
        return GamutMappingResult(
            source_image=RasterImage(
                self.source_image.width,
                self.source_image.height,
                self.source_image.mode,
                self.source_image.pixels,
            ),
            mapped_image=RasterImage(
                self.mapped_image.width,
                self.mapped_image.height,
                self.mapped_image.mode,
                self.mapped_image.pixels,
            ),
            mapped_linear_u16be=bytes(self.mapped_linear_u16be),
            options=self.options,
            profile=self.profile,
            report=GamutMappingReport(self.report.payload),
        )


def _mapped_identity(
    image: RasterImage,
    encoded: bytes,
    encoding: str,
    *,
    profile: GamutProfile | None,
    options: MappingOptions,
) -> dict[str, Any]:
    header = {
        "width": image.width,
        "height": image.height,
        "mode": image.mode,
        "encoding": encoding,
        "row_order": "top-left row-major tightly packed",
        "profile_canonical_sha256": (
            None if profile is None else profile.canonical_sha256
        ),
        "mapper_version": GAMUT_MAPPER_VERSION,
        "options": {
            "mode": options.mode.value,
            "intent": options.intent.value,
            "strength": options.strength,
        },
    }
    canonical = _canonical_json(header) + b"\n" + encoded
    return {
        **header,
        "encoded_bytes": len(encoded),
        "encoded_sha256": hashlib.sha256(encoded).hexdigest(),
        "canonical_sha256": hashlib.sha256(canonical).hexdigest(),
        "canonical_sha256_scope": MAPPED_RASTER_CANONICAL_HASH_SCOPE,
    }


def map_raster(
    image: RasterImage,
    *,
    palette: Palette | None = None,
    profile: GamutProfile | None = None,
    options: MappingOptions | None = None,
    allow_unqualified_simulation: bool = False,
) -> GamutMappingResult:
    """Map a complete raster before C2 dithering, without any device access.

    The mapped path requires a bound profile.  A reference or otherwise
    unqualified profile requires the explicit simulation opt-in and remains
    ``formal_upload_authorized=false`` in the report.  ``none``/``legacy`` is
    an exact byte-preserving compatibility path and requires no profile.
    """

    if not isinstance(image, RasterImage):
        raise GamutMappingError("image must be a host.color_pipeline.RasterImage")
    selected_options = MappingOptions() if options is None else options
    if not isinstance(selected_options, MappingOptions):
        raise GamutMappingError("options must be MappingOptions or None")
    if type(allow_unqualified_simulation) is not bool:
        raise GamutMappingError("allow_unqualified_simulation must be boolean")

    source_identity = {
        "width": image.width,
        "height": image.height,
        "mode": image.mode,
        "pixel_bytes": len(image.pixels),
        "sha256": hashlib.sha256(image.pixels).hexdigest(),
        "sha256_scope": "decoded tightly-packed source pixel bytes only",
        "transfer_function": "IEC 61966-2-1 sRGB",
        "alpha": (
            "straight; composed onto white in linear light"
            if image.mode == "RGBA"
            else "absent"
        ),
    }

    if selected_options.mode is MappingMode.NONE:
        mapped = RasterImage(image.width, image.height, image.mode, image.pixels)
        identity = _mapped_identity(
            mapped,
            mapped.pixels,
            LEGACY_RASTER_ENCODING,
            profile=None,
            options=selected_options,
        )
        payload = {
            "schema_version": MAPPING_REPORT_SCHEMA_VERSION,
            "kind": MAPPING_REPORT_KIND,
            "mapper": {"version": GAMUT_MAPPER_VERSION, "algorithm": "legacy-pass-through"},
            "source_raster": source_identity,
            "profile": None,
            "options": selected_options.to_mapping(),
            "statistics": {
                "pixels": image.width * image.height,
                "unique_input_colours_evaluated": 0,
                "cache_capacity": selected_options.cache_entries,
                "cache_peak_entries": 0,
                "out_of_gamut_after_tone_pixels": 0,
                "out_of_gamut_after_tone_ratio": 0.0,
                "tone_delta_l_abs_mean": 0.0,
                "tone_delta_l_abs_max": 0.0,
                "chroma_compression_mean": 0.0,
                "chroma_compression_max": 0.0,
                "display_gamut_clipped_pixels": 0,
                "numeric_fallback_pixels": 0,
            },
            "mapped_raster": identity,
            "qualification": {
                "simulation": True,
                "profile_provenance_complete_for_formal_use": False,
                "profile_hardware_formal_qualified": False,
                "artifact_hardware_qualified": False,
                "formal_upload_authorized": False,
                "reason": "legacy mapping bypass; G1 profile not applied",
            },
            "warnings": [SOFT_PROOF_WARNING],
            "hardware_tested": False,
            "device_io_performed": False,
        }
        report = GamutMappingReport(payload)
        validate_mapping_report(report.to_dict())
        result = GamutMappingResult(
            image, mapped, b"", selected_options, None, report
        )
        validate_mapping_result(result)
        return result

    if not isinstance(palette, Palette):
        raise GamutMappingError("gamut-map mode requires an explicit Palette")
    if not isinstance(profile, GamutProfile):
        raise GamutMappingError("gamut-map mode requires an explicit GamutProfile")
    if (
        profile.palette_id != palette.palette_id
        or profile.palette_canonical_sha256 != palette.canonical_sha256
    ):
        raise GamutMappingError("profile palette identity does not match palette")
    if (not palette.calibrated or profile.is_simulation) and not allow_unqualified_simulation:
        raise GamutMappingError(
            "uncalibrated/unqualified mapping requires allow_unqualified_simulation=True"
        )

    mapper = GamutMapper(palette, profile)
    mapped_rgb8 = bytearray(image.width * image.height * 3)
    mapped_u16 = bytearray(image.width * image.height * 6)
    cache: OrderedDict[bytes, tuple[bytes, bytes, MappedColor]] = OrderedDict()
    unique_evaluations = 0
    cache_peak = 0
    out_of_gamut = 0
    tone_sum = 0.0
    tone_max = 0.0
    chroma_sum = 0.0
    chroma_max = 0.0
    display_clipped = 0
    numeric_fallback = 0
    channels = image.channels
    total = image.width * image.height

    for index in range(total):
        source_offset = index * channels
        key = image.pixels[source_offset : source_offset + channels]
        cached = cache.get(key) if selected_options.cache_entries else None
        if cached is not None:
            cache.move_to_end(key)
            rgb_bytes, u16_bytes, colour = cached
        else:
            alpha = 1.0 if channels == 3 else key[3] / 255.0
            inverse = 1.0 - alpha
            linear = tuple(
                SRGB8_TO_LINEAR[key[channel]] * alpha + inverse for channel in range(3)
            )
            source_lab = linear_rgb_to_lab(linear)
            colour = mapper.map_lab(
                source_lab,
                intent=selected_options.intent,
                strength=selected_options.strength,
            )
            quantized = tuple(
                min(65535, max(0, int(math.floor(value * 65535.0 + 0.5))))
                for value in colour.display_linear_rgb
            )
            u16_bytes = b"".join(value.to_bytes(2, "big") for value in quantized)
            rgb_bytes = bytes(
                min(
                    255,
                    max(
                        0,
                        int(
                            math.floor(
                                linear_channel_to_srgb(value / 65535.0) * 255.0 + 0.5
                            )
                        ),
                    ),
                )
                for value in quantized
            )
            unique_evaluations += 1
            if selected_options.cache_entries:
                cache[key] = (rgb_bytes, u16_bytes, colour)
                if len(cache) > selected_options.cache_entries:
                    cache.popitem(last=False)
                cache_peak = max(cache_peak, len(cache))

        target_rgb = index * 3
        target_u16 = index * 6
        mapped_rgb8[target_rgb : target_rgb + 3] = rgb_bytes
        mapped_u16[target_u16 : target_u16 + 6] = u16_bytes
        if not colour.in_gamut_after_tone:
            out_of_gamut += 1
        absolute_tone = abs(colour.tone_delta_l)
        tone_sum += absolute_tone
        tone_max = max(tone_max, absolute_tone)
        chroma_sum += colour.chroma_compression
        chroma_max = max(chroma_max, colour.chroma_compression)
        if colour.display_clipped:
            display_clipped += 1
        if colour.numeric_fallback:
            numeric_fallback += 1

    mapped = RasterImage(image.width, image.height, "RGB", bytes(mapped_rgb8))
    encoded = bytes(mapped_u16)
    identity = _mapped_identity(
        mapped,
        encoded,
        MAPPED_RASTER_ENCODING,
        profile=profile,
        options=selected_options,
    )
    preset = profile.preset(selected_options.intent.value)
    simulation = not palette.calibrated or profile.is_simulation
    reason = (
        "uncalibrated palette and/or characterization profile; monitor simulation only"
        if simulation
        else "software mapper is not a trust-store or hardware authorization boundary"
    )
    warnings = [SOFT_PROOF_WARNING]
    if simulation:
        warnings.insert(
            0,
            "Synthetic/uncalibrated model: not a measured MF-1750 gamut and not hardware qualified.",
        )
    payload = {
        "schema_version": MAPPING_REPORT_SCHEMA_VERSION,
        "kind": MAPPING_REPORT_KIND,
        "mapper": {
            "version": GAMUT_MAPPER_VERSION,
            "algorithm": "tone-plus-3d-xyz-convex-radial-compression-v1",
        },
        "source_raster": source_identity,
        "profile": {
            "id": profile.profile_id,
            "version": profile.profile_version,
            "canonical_sha256": profile.canonical_sha256,
            "canonical_sha256_scope": GAMUT_PROFILE_CANONICAL_HASH_SCOPE,
            "palette_id": profile.palette_id,
            "palette_canonical_sha256": profile.palette_canonical_sha256,
            "model_kind": profile.model_kind,
            "characterization_level": profile.characterization_level,
            "approximation": profile.approximation,
        },
        "options": {
            **selected_options.to_mapping(),
            "preset": preset.to_mapping(),
        },
        "statistics": {
            "pixels": total,
            "unique_input_colours_evaluated": unique_evaluations,
            "cache_capacity": selected_options.cache_entries,
            "cache_peak_entries": cache_peak,
            "out_of_gamut_after_tone_pixels": out_of_gamut,
            "out_of_gamut_after_tone_ratio": out_of_gamut / total,
            "tone_delta_l_abs_mean": tone_sum / total,
            "tone_delta_l_abs_max": tone_max,
            "chroma_compression_mean": chroma_sum / total,
            "chroma_compression_max": chroma_max,
            "display_gamut_clipped_pixels": display_clipped,
            "numeric_fallback_pixels": numeric_fallback,
        },
        "mapped_raster": identity,
        "qualification": {
            "simulation": simulation,
            "profile_provenance_complete_for_formal_use": (
                profile.provenance_complete_for_formal_use
            ),
            "profile_hardware_formal_qualified": profile.hardware_formal_qualified,
            "artifact_hardware_qualified": False,
            "formal_upload_authorized": False,
            "reason": reason,
        },
        "warnings": warnings,
        "hardware_tested": False,
        "device_io_performed": False,
    }
    report = GamutMappingReport(payload)
    validate_mapping_report(report.to_dict())
    result = GamutMappingResult(
        image, mapped, encoded, selected_options, profile, report
    )
    validate_mapping_result(result)
    return result


def validate_mapping_report(report: Mapping[str, Any]) -> None:
    """Validate report structure and its canonical audit identity."""

    if not isinstance(report, Mapping):
        raise GamutMappingError("mapping report must be an object")
    expected = {
        "schema_version",
        "kind",
        "mapper",
        "source_raster",
        "profile",
        "options",
        "statistics",
        "mapped_raster",
        "qualification",
        "warnings",
        "hardware_tested",
        "device_io_performed",
        "report_integrity",
    }
    if set(report) != expected:
        raise GamutMappingError("mapping report has missing or unknown top-level fields")
    if report["schema_version"] != MAPPING_REPORT_SCHEMA_VERSION or type(report["schema_version"]) is not int:
        raise GamutMappingError("mapping report schema_version is invalid")
    if report["kind"] != MAPPING_REPORT_KIND:
        raise GamutMappingError("mapping report kind is invalid")
    if report["hardware_tested"] is not False or report["device_io_performed"] is not False:
        raise GamutMappingError("mapping report must remain software-only")
    mapper = report["mapper"]
    if not isinstance(mapper, Mapping) or set(mapper) != {"version", "algorithm"}:
        raise GamutMappingError("mapping report mapper identity is invalid")
    if mapper.get("version") != GAMUT_MAPPER_VERSION:
        raise GamutMappingError("mapping report mapper version is invalid")
    options = report["options"]
    if not isinstance(options, Mapping):
        raise GamutMappingError("mapping report options must be an object")
    try:
        normalized_options = MappingOptions(
            mode=options.get("mode"),
            intent=options.get("intent"),
            strength=options.get("strength"),
            cache_entries=options.get("cache_entries"),
        )
    except (TypeError, ValueError) as error:
        raise GamutMappingError(f"mapping report options are invalid: {error}") from error
    mode = normalized_options.mode
    expected_option_keys = {"mode", "intent", "strength", "cache_entries"}
    if mode is MappingMode.GAMUT_MAP:
        expected_option_keys.add("preset")
    if set(options) != expected_option_keys:
        raise GamutMappingError("mapping report option fields differ from its mode")
    if {key: options[key] for key in ("mode", "intent", "strength", "cache_entries")} != normalized_options.to_mapping():
        raise GamutMappingError("mapping report options are not canonical")
    mapped = report["mapped_raster"]
    if not isinstance(mapped, Mapping) or set(mapped) != {
        "width",
        "height",
        "mode",
        "encoding",
        "row_order",
        "profile_canonical_sha256",
        "mapper_version",
        "options",
        "encoded_bytes",
        "encoded_sha256",
        "canonical_sha256",
        "canonical_sha256_scope",
    }:
        raise GamutMappingError("mapping report mapped_raster identity is invalid")
    for digest_field in ("encoded_sha256", "canonical_sha256"):
        value = mapped[digest_field]
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise GamutMappingError(f"mapped_raster {digest_field} is invalid")
    if mapped["canonical_sha256_scope"] != MAPPED_RASTER_CANONICAL_HASH_SCOPE:
        raise GamutMappingError("mapped raster canonical hash scope is invalid")
    source = report["source_raster"]
    if not isinstance(source, Mapping) or set(source) != {
        "width",
        "height",
        "mode",
        "pixel_bytes",
        "sha256",
        "sha256_scope",
        "transfer_function",
        "alpha",
    }:
        raise GamutMappingError("mapping report source raster identity is invalid")
    if (
        type(source.get("width")) is not int
        or source["width"] <= 0
        or type(source.get("height")) is not int
        or source["height"] <= 0
        or type(source.get("pixel_bytes")) is not int
        or source["pixel_bytes"] <= 0
        or type(mapped.get("width")) is not int
        or mapped["width"] <= 0
        or type(mapped.get("height")) is not int
        or mapped["height"] <= 0
        or type(mapped.get("encoded_bytes")) is not int
        or mapped["encoded_bytes"] <= 0
    ):
        raise GamutMappingError("mapping raster dimensions/byte counts are invalid")
    if (
        source.get("width") != mapped.get("width")
        or source.get("height") != mapped.get("height")
        or mapped.get("mapper_version") != GAMUT_MAPPER_VERSION
        or mapped.get("options")
        != {key: options[key] for key in ("mode", "intent", "strength")}
    ):
        raise GamutMappingError("mapping source/output/options identities disagree")
    if mode is MappingMode.NONE:
        if (
            mapper.get("algorithm") != "legacy-pass-through"
            or report.get("profile") is not None
            or mapped.get("profile_canonical_sha256") is not None
            or mapped.get("encoding") != LEGACY_RASTER_ENCODING
            or mapped.get("mode") != source.get("mode")
            or mapped.get("encoded_bytes") != source.get("pixel_bytes")
        ):
            raise GamutMappingError("legacy mapping evidence is internally inconsistent")
    else:
        profile = report.get("profile")
        if not isinstance(profile, Mapping) or set(profile) != {
            "id",
            "version",
            "canonical_sha256",
            "canonical_sha256_scope",
            "palette_id",
            "palette_canonical_sha256",
            "model_kind",
            "characterization_level",
            "approximation",
        }:
            raise GamutMappingError("mapped profile summary is invalid")
        if (
            mapper.get("algorithm")
            != "tone-plus-3d-xyz-convex-radial-compression-v1"
            or mapped.get("profile_canonical_sha256")
            != profile.get("canonical_sha256")
            or mapped.get("encoding") != MAPPED_RASTER_ENCODING
            or mapped.get("mode") != "RGB"
            or mapped.get("encoded_bytes") != mapped.get("width") * mapped.get("height") * 6
        ):
            raise GamutMappingError("gamut-mapped evidence is internally inconsistent")
        preset = options.get("preset")
        if not isinstance(preset, Mapping) or preset.get("version") is None:
            raise GamutMappingError("gamut-mapped report lacks a rendering preset")
    qualification = report["qualification"]
    if not isinstance(qualification, Mapping) or qualification.get("artifact_hardware_qualified") is not False or qualification.get("formal_upload_authorized") is not False:
        raise GamutMappingError("mapping report must fail closed for hardware/formal upload")
    warnings = report["warnings"]
    if not isinstance(warnings, list) or SOFT_PROOF_WARNING not in warnings:
        raise GamutMappingError("mapping report must carry the monitor simulation warning")
    integrity = report["report_integrity"]
    if not isinstance(integrity, Mapping) or set(integrity) != {
        "canonical_sha256",
        "canonical_sha256_scope",
        "fingerprint_trust",
    }:
        raise GamutMappingError("mapping report integrity block is invalid")
    unsigned = dict(report)
    del unsigned["report_integrity"]
    expected_hash = hashlib.sha256(_canonical_json(unsigned)).hexdigest()
    if integrity.get("canonical_sha256") != expected_hash:
        raise GamutMappingError("mapping report integrity hash does not match content")
    if integrity.get("canonical_sha256_scope") != MAPPING_REPORT_CANONICAL_HASH_SCOPE:
        raise GamutMappingError("mapping report integrity scope is invalid")


def validate_mapping_result(result: GamutMappingResult) -> None:
    """Bind an in-memory result's bytes back to every reported identity."""

    if not isinstance(result, GamutMappingResult):
        raise GamutMappingError("result must be a GamutMappingResult")
    report = result.report.to_dict()
    validate_mapping_report(report)
    source = report["source_raster"]
    if not isinstance(source, Mapping) or set(source) != {
        "width",
        "height",
        "mode",
        "pixel_bytes",
        "sha256",
        "sha256_scope",
        "transfer_function",
        "alpha",
    }:
        raise GamutMappingError("mapping report source identity is invalid")
    if (
        source["width"] != result.source_image.width
        or source["height"] != result.source_image.height
        or source["mode"] != result.source_image.mode
        or source["pixel_bytes"] != len(result.source_image.pixels)
        or source["sha256"] != hashlib.sha256(result.source_image.pixels).hexdigest()
    ):
        raise GamutMappingError("source raster does not match mapping report")
    if (
        result.mapped_image.width != result.source_image.width
        or result.mapped_image.height != result.source_image.height
    ):
        raise GamutMappingError("mapped raster dimensions differ from source")

    if result.options.mode is MappingMode.NONE:
        if result.profile is not None or result.mapped_linear_u16be != b"":
            raise GamutMappingError("legacy result must not carry profile/Q16 mapped bytes")
        if (
            result.mapped_image.mode != result.source_image.mode
            or result.mapped_image.pixels != result.source_image.pixels
        ):
            raise GamutMappingError("legacy result is not byte-for-byte source compatible")
        encoded = result.mapped_image.pixels
        encoding = LEGACY_RASTER_ENCODING
        expected_options: Mapping[str, Any] = result.options.to_mapping()
    else:
        if not isinstance(result.profile, GamutProfile):
            raise GamutMappingError("mapped result lacks its gamut profile")
        expected_length = result.mapped_image.width * result.mapped_image.height * 6
        if len(result.mapped_linear_u16be) != expected_length:
            raise GamutMappingError("mapped Q16 raster length is invalid")
        if result.mapped_image.mode != "RGB":
            raise GamutMappingError("mapped gamut raster must be RGB")
        expected_rgb = bytearray(result.mapped_image.width * result.mapped_image.height * 3)
        u16_to_srgb8: dict[int, int] = {}
        for index in range(result.mapped_image.width * result.mapped_image.height):
            for channel in range(3):
                offset = index * 6 + channel * 2
                value = (
                    result.mapped_linear_u16be[offset] << 8
                    | result.mapped_linear_u16be[offset + 1]
                )
                converted = u16_to_srgb8.get(value)
                if converted is None:
                    converted = min(
                        255,
                        max(
                            0,
                            int(
                                math.floor(
                                    linear_channel_to_srgb(value / 65535.0) * 255.0
                                    + 0.5
                                )
                            ),
                        ),
                    )
                    u16_to_srgb8[value] = converted
                expected_rgb[index * 3 + channel] = converted
        if bytes(expected_rgb) != result.mapped_image.pixels:
            raise GamutMappingError("mapped RGB bytes do not derive from mapped Q16 identity")
        encoded = result.mapped_linear_u16be
        encoding = MAPPED_RASTER_ENCODING
        expected_options = {
            **result.options.to_mapping(),
            "preset": result.profile.preset(result.options.intent.value).to_mapping(),
        }
        profile_report = report["profile"]
        if (
            not isinstance(profile_report, Mapping)
            or profile_report.get("id") != result.profile.profile_id
            or profile_report.get("canonical_sha256") != result.profile.canonical_sha256
        ):
            raise GamutMappingError("mapped profile identity differs from report")

    expected_identity = _mapped_identity(
        result.mapped_image,
        encoded,
        encoding,
        profile=result.profile,
        options=result.options,
    )
    if report["mapped_raster"] != expected_identity:
        raise GamutMappingError("mapped raster identity does not match result bytes")
    if report["options"] != expected_options:
        raise GamutMappingError("mapping options differ from report")


__all__ = [
    "GAMUT_MAPPER_VERSION",
    "LEGACY_RASTER_ENCODING",
    "MAPPED_RASTER_CANONICAL_HASH_SCOPE",
    "MAPPED_RASTER_ENCODING",
    "MAPPING_REPORT_CANONICAL_HASH_SCOPE",
    "MAPPING_REPORT_KIND",
    "MAPPING_REPORT_SCHEMA_VERSION",
    "SOFT_PROOF_WARNING",
    "GamutMapper",
    "GamutMappingError",
    "GamutMappingReport",
    "GamutMappingResult",
    "MappedColor",
    "MappingMode",
    "MappingOptions",
    "RenderingIntent",
    "map_lightness",
    "map_raster",
    "validate_mapping_result",
    "validate_mapping_report",
]
