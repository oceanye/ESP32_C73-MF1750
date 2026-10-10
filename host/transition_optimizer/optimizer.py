"""Deterministic transition-aware error diffusion for the MF-1750.

The present panel uses one fixed global waveform.  Consequently this module
optimizes a measured *proxy* for optical/electrical burden; it does not claim
to shorten BUSY time.  Every transition-dependent score comes from a complete
measured 6x6 profile.  Missing measurements either fail closed (the default)
or produce an explicitly unqualified perceptual-only fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Mapping, Optional, Sequence

from host.color_pipeline import (
    DitherMode,
    Palette,
    PipelineOptions,
    QuantizationResult,
    RasterImage,
    UNCONSTRAINED_PHYSICAL_CODE,
    build_protection_constraints,
    delta_e_ciede2000,
    encode_rgb_png,
    linear_rgb_to_lab,
    quantize_image,
)
from host.color_pipeline.color import SRGB8_TO_LINEAR
from host.epd_frame import (
    FRAME_BYTES,
    HEIGHT,
    PHYSICAL_COLOR_CODES,
    WIDTH,
    fnv1a,
    pack_pixels,
)
from host.extended_color import COLOR_ORDER, validate_transition_profile


SCHEMA_VERSION = 1
RESULT_KIND = "mf1750-transition-aware-optimization-result"
PARETO_KIND = "mf1750-transition-aware-pareto-report"
ALGORITHM_ID = "measured-transition-aware-error-diffusion-v1"
RESULT_HASH_SCOPE = (
    "entire transition-aware report excluding integrity; UTF-8 JSON with "
    "sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
PARETO_HASH_SCOPE = RESULT_HASH_SCOPE.replace(
    "transition-aware report", "transition-aware Pareto report"
)

_COMPONENT_FIELDS = {
    "optical": "delta_e00_mean",
    "peak_current": "peak_current_a_mean",
    "energy": "energy_j_mean",
    "settling": "busy_ms_mean",
    "ghosting": "ghosting_metric_mean",
    "temperature": "temperature_rise_c_mean",
    "recovery_failure": "recovery_pass_rate",
}


class TransitionOptimizationError(ValueError):
    """An input, measured profile, or report failed closed."""


class MissingProfileMode(str, Enum):
    REJECT = "reject"
    PERCEPTUAL_ONLY = "perceptual-only-unqualified"


class UnknownCurrentMode(str, Enum):
    REJECT = "reject"
    CONSERVATIVE_WORST_CASE = "conservative-worst-case"
    PERCEPTUAL_ONLY = "perceptual-only-unqualified"


_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


def _sha_field(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise TransitionOptimizationError(
            f"{label} must be 64 lowercase hexadecimal digits"
        )
    return value


@dataclass(frozen=True)
class TransitionInputBinding:
    """Reviewed cross-asset binding for a palette and transition profile.

    A calibrated palette does not itself contain a panel serial.  This record
    therefore prevents silently pairing a palette from one measurement
    campaign with a transition matrix from another panel/build/waveform.
    """

    binding_id: str
    palette_canonical_sha256: str
    palette_calibration_artifact_sha256: str
    transition_profile_canonical_sha256: str
    panel_serial: str
    firmware_binary_sha256: str
    waveform_sha256: str
    review_artifact_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.binding_id, str)
            or not self.binding_id.strip()
            or any(ord(character) < 0x20 for character in self.binding_id)
        ):
            raise TransitionOptimizationError("binding_id must be non-empty text")
        if (
            not isinstance(self.panel_serial, str)
            or not self.panel_serial.strip()
            or any(ord(character) < 0x20 for character in self.panel_serial)
        ):
            raise TransitionOptimizationError("binding panel_serial must be non-empty text")
        object.__setattr__(self, "binding_id", self.binding_id.strip())
        object.__setattr__(self, "panel_serial", self.panel_serial.strip())
        for name in (
            "palette_canonical_sha256",
            "palette_calibration_artifact_sha256",
            "transition_profile_canonical_sha256",
            "firmware_binary_sha256",
            "waveform_sha256",
            "review_artifact_sha256",
        ):
            object.__setattr__(
                self, name, _sha_field(getattr(self, name), label=f"binding.{name}")
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "binding_id": self.binding_id,
            "palette_canonical_sha256": self.palette_canonical_sha256,
            "palette_calibration_artifact_sha256": (
                self.palette_calibration_artifact_sha256
            ),
            "transition_profile_canonical_sha256": (
                self.transition_profile_canonical_sha256
            ),
            "panel_serial": self.panel_serial,
            "firmware_binary_sha256": self.firmware_binary_sha256,
            "waveform_sha256": self.waveform_sha256,
            "review_artifact_sha256": self.review_artifact_sha256,
        }


def _finite_nonnegative(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TransitionOptimizationError(f"{label} must be a finite non-negative number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise TransitionOptimizationError(f"{label} must be a finite non-negative number")
    return result


@dataclass(frozen=True)
class TransitionMetricWeights:
    """Weights inside the normalized measured transition-cost term."""

    optical: float = 1.0
    peak_current: float = 1.0
    energy: float = 1.0
    settling: float = 1.0
    ghosting: float = 1.0
    temperature: float = 1.0
    recovery_failure: float = 1.0

    def __post_init__(self) -> None:
        for name in _COMPONENT_FIELDS:
            object.__setattr__(
                self,
                name,
                _finite_nonnegative(getattr(self, name), label=f"metric_weights.{name}"),
            )

    def to_dict(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in _COMPONENT_FIELDS}

    @property
    def total(self) -> float:
        return sum(self.to_dict().values())


@dataclass(frozen=True)
class TransitionOptimizationOptions:
    """Weights for ``J = alpha*DE00 + beta*T + gamma*changed + delta*spatial``."""

    alpha: float = 1.0
    beta: float = 0.0
    gamma: float = 0.0
    delta: float = 0.0
    metric_weights: TransitionMetricWeights = field(
        default_factory=TransitionMetricWeights
    )
    pipeline_options: PipelineOptions = field(
        default_factory=lambda: PipelineOptions(
            dither=DitherMode.FLOYD_STEINBERG,
            preserve_edges=False,
        )
    )
    missing_profile_mode: MissingProfileMode | str = MissingProfileMode.REJECT
    unknown_current_mode: UnknownCurrentMode | str = UnknownCurrentMode.REJECT

    def __post_init__(self) -> None:
        for name in ("alpha", "beta", "gamma", "delta"):
            object.__setattr__(
                self,
                name,
                _finite_nonnegative(getattr(self, name), label=name),
            )
        if self.alpha + self.beta + self.gamma + self.delta <= 0:
            raise TransitionOptimizationError("at least one objective weight must be positive")
        if type(self.metric_weights) is not TransitionMetricWeights:
            raise TransitionOptimizationError(
                "metric_weights must be TransitionMetricWeights"
            )
        if type(self.pipeline_options) is not PipelineOptions:
            raise TransitionOptimizationError("pipeline_options must be PipelineOptions")
        try:
            missing = (
                self.missing_profile_mode
                if isinstance(self.missing_profile_mode, MissingProfileMode)
                else MissingProfileMode(self.missing_profile_mode)
            )
            unknown = (
                self.unknown_current_mode
                if isinstance(self.unknown_current_mode, UnknownCurrentMode)
                else UnknownCurrentMode(self.unknown_current_mode)
            )
        except ValueError as error:
            raise TransitionOptimizationError("unknown profile/current-state mode") from error
        object.__setattr__(self, "missing_profile_mode", missing)
        object.__setattr__(self, "unknown_current_mode", unknown)
        if self.beta > 0 and self.metric_weights.total <= 0:
            raise TransitionOptimizationError(
                "beta > 0 requires at least one measured transition metric weight"
            )
        if (
            self.beta + self.gamma + self.delta > 0
            and self.pipeline_options.dither
            not in (DitherMode.FLOYD_STEINBERG, DitherMode.ATKINSON)
        ):
            raise TransitionOptimizationError(
                "state-aware optimization requires Floyd-Steinberg or Atkinson diffusion"
            )

    def to_dict(self) -> dict[str, Any]:
        pipeline = self.pipeline_options
        return {
            "alpha": self.alpha,
            "beta": self.beta,
            "gamma": self.gamma,
            "delta": self.delta,
            "metric_weights": self.metric_weights.to_dict(),
            "pipeline": {
                "dither": pipeline.dither.value,
                "seed": pipeline.seed,
                "serpentine": pipeline.serpentine,
                "white_protection": pipeline.white_protection,
                "white_luminance_threshold": pipeline.white_luminance_threshold,
                "white_chroma_threshold": pipeline.white_chroma_threshold,
                "preserve_edges": pipeline.preserve_edges,
                "edge_threshold": pipeline.edge_threshold,
                "text_mode": pipeline.text_mode,
                "text_luminance_threshold": pipeline.text_luminance_threshold,
            },
            "missing_profile_mode": self.missing_profile_mode.value,
            "unknown_current_mode": self.unknown_current_mode.value,
        }


@dataclass(frozen=True)
class TransitionOptimizationResult:
    width: int
    height: int
    frame: bytes
    codes: bytes
    palette: Palette
    report: Mapping[str, Any]

    def preview_rgb(self) -> bytes:
        by_code = {entry.code: entry.preview_rgb for entry in self.palette.entries}
        output = bytearray(len(self.codes) * 3)
        for index, code in enumerate(self.codes):
            output[index * 3 : index * 3 + 3] = bytes(by_code[code])
        return bytes(output)

    def preview_png(self) -> bytes:
        return encode_rgb_png(self.width, self.height, self.preview_rgb())


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise TransitionOptimizationError(f"canonical JSON encoding failed: {error}") from error


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else _canonical_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _seal(unsigned: Mapping[str, Any], scope: str) -> dict[str, Any]:
    return {
        **dict(unsigned),
        "integrity": {
            "canonical_sha256": _sha256(unsigned),
            "canonical_sha256_scope": scope,
        },
    }


def _pixel_linear(image: RasterImage, index: int) -> tuple[tuple[float, float, float], float]:
    offset = index * image.channels
    red = SRGB8_TO_LINEAR[image.pixels[offset]]
    green = SRGB8_TO_LINEAR[image.pixels[offset + 1]]
    blue = SRGB8_TO_LINEAR[image.pixels[offset + 2]]
    if image.channels == 3:
        return (red, green, blue), 1.0
    alpha = image.pixels[offset + 3] / 255.0
    inverse = 1.0 - alpha
    return (
        red * alpha + inverse,
        green * alpha + inverse,
        blue * alpha + inverse,
    ), alpha


def _clamp(rgb: Sequence[float]) -> tuple[float, float, float]:
    return tuple(min(1.0, max(0.0, float(value))) for value in rgb)  # type: ignore[return-value]


def _validate_current_codes(
    current_codes: Optional[bytes], *, pixel_count: int
) -> Optional[bytes]:
    if current_codes is None:
        return None
    try:
        payload = bytes(memoryview(current_codes).cast("B"))
    except (TypeError, ValueError) as error:
        raise TransitionOptimizationError("current_codes must be contiguous bytes") from error
    if len(payload) != pixel_count:
        raise TransitionOptimizationError(
            f"current_codes has {len(payload)} pixels; expected {pixel_count}"
        )
    invalid = sorted(set(payload) - set(PHYSICAL_COLOR_CODES))
    if invalid:
        raise TransitionOptimizationError(
            "current_codes contains non-physical codes: "
            + ", ".join(f"0x{value:X}" for value in invalid)
        )
    return payload


def _profile_cost_table(
    profile: Optional[Mapping[str, Any]],
    options: TransitionOptimizationOptions,
) -> tuple[
    Optional[dict[tuple[int, int], float]],
    dict[str, Any],
    bool,
]:
    """Return normalized costs, provenance report and formal input readiness."""

    if profile is None:
        if options.missing_profile_mode is MissingProfileMode.REJECT:
            raise TransitionOptimizationError("a transition profile is required")
        return None, {
            "present": False,
            "canonical_sha256": None,
            "hardware_tested": False,
            "complete_6x6": False,
            "panel_serial": None,
            "firmware_binary_sha256": None,
            "waveform_id": None,
            "waveform_sha256": None,
            "environment": None,
            "component_ranges": None,
            "fixed_global_busy_range_ms": None,
        }, False
    if not isinstance(profile, Mapping):
        raise TransitionOptimizationError("transition_profile must be an object or None")
    try:
        validate_transition_profile(profile)
    except ValueError as error:
        raise TransitionOptimizationError(f"transition profile is invalid: {error}") from error
    cells = list(profile["cells"])
    measured = all(cell["sample_count"] > 0 for cell in cells)
    if not measured:
        if options.missing_profile_mode is MissingProfileMode.REJECT:
            raise TransitionOptimizationError(
                "the transition profile is incomplete and fallback was not selected"
            )
        return None, {
            "present": True,
            "canonical_sha256": _sha256(profile),
            "hardware_tested": bool(profile["hardware_tested"]),
            "complete_6x6": False,
            "panel_serial": profile["panel_serial"],
            "firmware_binary_sha256": profile["firmware_binary_sha256"],
            "waveform_id": profile["waveform_id"],
            "waveform_sha256": profile["waveform_sha256"],
            "environment": dict(profile["environment"]),
            "component_ranges": None,
            "fixed_global_busy_range_ms": None,
        }, False

    component_values: dict[str, list[float]] = {name: [] for name in _COMPONENT_FIELDS}
    raw_by_pair: dict[tuple[int, int], dict[str, float]] = {}
    for cell in cells:
        pair = (cell["old_code"], cell["new_code"])
        values: dict[str, float] = {}
        for name, field_name in _COMPONENT_FIELDS.items():
            value = float(cell[field_name])
            if name == "temperature":
                value = max(0.0, value)
            elif name == "recovery_failure":
                value = 1.0 - value
            values[name] = value
            component_values[name].append(value)
        raw_by_pair[pair] = values

    ranges: dict[str, dict[str, Any]] = {}
    normalized: dict[str, dict[tuple[int, int], float]] = {}
    for name, values in component_values.items():
        minimum = min(values)
        maximum = max(values)
        span = maximum - minimum
        ranges[name] = {
            "minimum": minimum,
            "maximum": maximum,
            "constant_across_profile": span == 0.0,
        }
        normalized[name] = {
            pair: (0.0 if span == 0.0 else (components[name] - minimum) / span)
            for pair, components in raw_by_pair.items()
        }

    weights = options.metric_weights.to_dict()
    denominator = options.metric_weights.total
    costs = {
        pair: (
            0.0
            if denominator == 0.0
            else sum(weights[name] * normalized[name][pair] for name in weights)
            / denominator
        )
        for pair in raw_by_pair
    }
    busy_values = component_values["settling"]
    record = {
        "present": True,
        "canonical_sha256": _sha256(profile),
        "hardware_tested": bool(profile["hardware_tested"]),
        "complete_6x6": True,
        "panel_serial": profile["panel_serial"],
        "firmware_binary_sha256": profile["firmware_binary_sha256"],
        "waveform_id": profile["waveform_id"],
        "waveform_sha256": profile["waveform_sha256"],
        "environment": dict(profile["environment"]),
        "component_ranges": ranges,
        "fixed_global_busy_range_ms": max(busy_values) - min(busy_values),
    }
    return costs, record, True


def _measurement_binding_record(
    binding: Optional[TransitionInputBinding],
    *,
    palette: Palette,
    profile: Optional[Mapping[str, Any]],
    profile_record: Mapping[str, Any],
) -> dict[str, Any]:
    if binding is None:
        return {
            "present": False,
            "verified": False,
            "binding": None,
            "blockers": ["reviewed_palette_transition_cross_asset_binding_missing"],
        }
    if type(binding) is not TransitionInputBinding:
        raise TransitionOptimizationError(
            "measurement_binding must be TransitionInputBinding or None"
        )
    if profile is None or profile_record["complete_6x6"] is not True:
        raise TransitionOptimizationError(
            "measurement binding requires a complete measured transition profile"
        )
    if not palette.calibrated or palette.calibration is None:
        raise TransitionOptimizationError(
            "measurement binding requires a calibrated palette"
        )
    expected = {
        "palette_canonical_sha256": palette.canonical_sha256,
        "palette_calibration_artifact_sha256": (
            palette.calibration.artifact_sha256
        ),
        "transition_profile_canonical_sha256": _sha256(profile),
        "panel_serial": profile["panel_serial"],
        "firmware_binary_sha256": profile["firmware_binary_sha256"],
        "waveform_sha256": profile["waveform_sha256"],
    }
    supplied = binding.to_dict()
    mismatches = [field for field, value in expected.items() if supplied[field] != value]
    if mismatches:
        raise TransitionOptimizationError(
            "measurement binding does not match palette/profile: "
            + ", ".join(mismatches)
        )
    return {
        "present": True,
        "verified": True,
        "binding": supplied,
        "blockers": [],
    }


def _transition_histogram(
    current: Optional[bytes], final: bytes
) -> Optional[list[list[int]]]:
    if current is None:
        return None
    indices = {code: index for index, code in enumerate(COLOR_ORDER)}
    matrix = [[0 for _ in COLOR_ORDER] for _ in COLOR_ORDER]
    for old, new in zip(current, final):
        matrix[indices[old]][indices[new]] += 1
    return matrix


def _objective_metrics(
    image: RasterImage,
    codes: bytes,
    palette: Palette,
    current: Optional[bytes],
    costs: Optional[Mapping[tuple[int, int], float]],
) -> dict[str, Any]:
    entries = palette.by_code
    perceptual: list[float] = []
    transition_sum: Optional[float] = 0.0 if current is not None and costs is not None else None
    changed: Optional[int] = 0 if current is not None else None
    spatial_sum = 0.0
    width = image.width
    for index, code in enumerate(codes):
        source_lab = linear_rgb_to_lab(_pixel_linear(image, index)[0])
        perceptual.append(delta_e_ciede2000(source_lab, entries[code].lab))
        if current is not None:
            if code != current[index]:
                assert changed is not None
                changed += 1
            if costs is not None:
                assert transition_sum is not None
                transition_sum += costs[(current[index], code)]
        neighbours: list[int] = []
        x = index % width
        y = index // width
        if x:
            neighbours.append(codes[index - 1])
        if y:
            neighbours.append(codes[index - width])
        if neighbours:
            spatial_sum += sum(value == code for value in neighbours) / len(neighbours)
    count = len(codes)
    return {
        "perceptual_error_de00_sum": sum(perceptual),
        "perceptual_error_de00_mean": sum(perceptual) / count,
        "perceptual_error_de00_maximum": max(perceptual),
        "normalized_transition_cost_sum": transition_sum,
        "normalized_transition_cost_mean": (
            transition_sum / count if transition_sum is not None else None
        ),
        "changed_pixels": changed,
        "changed_ratio": changed / count if changed is not None else None,
        "spatial_same_selected_neighbour_penalty_sum": spatial_sum,
        "spatial_same_selected_neighbour_penalty_mean": spatial_sum / count,
    }


def _ordinary_result(
    image: RasterImage,
    palette: Palette,
    options: TransitionOptimizationOptions,
    *,
    allow_uncalibrated_palette: bool,
) -> QuantizationResult:
    return quantize_image(
        image,
        palette=palette,
        options=options.pipeline_options,
        allow_uncalibrated_palette=allow_uncalibrated_palette,
    )


def optimize_transition_aware(
    image: RasterImage,
    *,
    palette: Palette,
    transition_profile: Optional[Mapping[str, Any]],
    current_codes: Optional[bytes],
    measurement_binding: Optional[TransitionInputBinding] = None,
    options: Optional[TransitionOptimizationOptions] = None,
    allow_uncalibrated_palette: bool = False,
) -> TransitionOptimizationResult:
    """Optimize one raster without performing any device or network I/O."""

    if type(image) is not RasterImage:
        raise TransitionOptimizationError("image must be RasterImage")
    if type(palette) is not Palette:
        raise TransitionOptimizationError("palette must be Palette")
    if image.width % 2:
        raise TransitionOptimizationError("4bpp output requires an even image width")
    output_bytes = image.width * image.height // 2
    if output_bytes == FRAME_BYTES and (image.width, image.height) != (WIDTH, HEIGHT):
        raise TransitionOptimizationError(
            f"{FRAME_BYTES}-byte output is reserved for {WIDTH}x{HEIGHT}"
        )
    if type(allow_uncalibrated_palette) is not bool:
        raise TransitionOptimizationError("allow_uncalibrated_palette must be boolean")
    selected = TransitionOptimizationOptions() if options is None else options
    if type(selected) is not TransitionOptimizationOptions:
        raise TransitionOptimizationError("options must be TransitionOptimizationOptions")
    current = _validate_current_codes(
        current_codes, pixel_count=image.width * image.height
    )
    costs, profile_record, complete_profile = _profile_cost_table(
        transition_profile, selected
    )
    binding_record = _measurement_binding_record(
        measurement_binding,
        palette=palette,
        profile=transition_profile,
        profile_record=profile_record,
    )

    transition_terms_requested = selected.beta > 0 or selected.gamma > 0
    if current is None and transition_terms_requested:
        if selected.unknown_current_mode is UnknownCurrentMode.REJECT:
            raise TransitionOptimizationError(
                "transition/change objectives require current_codes or an explicit fallback"
            )
        if selected.unknown_current_mode is UnknownCurrentMode.PERCEPTUAL_ONLY:
            costs = None
        elif selected.beta > 0 and costs is None:
            raise TransitionOptimizationError(
                "conservative unknown-current mode requires a complete measured profile"
            )

    ordinary_degenerate = selected.beta == selected.gamma == selected.delta == 0.0
    perceptual_fallback = (
        not ordinary_degenerate
        and (
            (not complete_profile and selected.beta > 0)
            or (
                current is None
                and transition_terms_requested
                and selected.unknown_current_mode is UnknownCurrentMode.PERCEPTUAL_ONLY
            )
        )
    )

    if ordinary_degenerate or perceptual_fallback:
        ordinary = _ordinary_result(
            image,
            palette,
            selected,
            allow_uncalibrated_palette=allow_uncalibrated_palette,
        )
        codes = ordinary.codes
        frame = ordinary.frame
        execution_path = (
            "exact-ordinary-quantizer-degeneration"
            if ordinary_degenerate
            else "explicit-unqualified-perceptual-only-fallback"
        )
    else:
        if (
            (image.width, image.height) == (WIDTH, HEIGHT)
            and not palette.calibrated
            and not allow_uncalibrated_palette
        ):
            raise TransitionOptimizationError(
                "panel-sized optimization requires a calibrated palette"
            )
        constraints = build_protection_constraints(
            image,
            palette=palette,
            options=selected.pipeline_options,
        )
        entries = tuple(palette.entries)
        diffusion = {entry.code: entry.diffusion_rgb for entry in entries}
        codes_buffer = bytearray(image.width * image.height)
        slots = image.width * 3
        errors = [[0.0] * slots for _ in range(3)]

        worst_cost = (
            {
                new: max(costs[(old, new)] for old in COLOR_ORDER)
                for new in COLOR_ORDER
            }
            if current is None and costs is not None
            else None
        )

        def add_error(
            target_x: int,
            target_y: int,
            residual: tuple[float, float, float],
            weight: float,
        ) -> None:
            if not (0 <= target_x < image.width and 0 <= target_y < image.height):
                return
            target = target_y * image.width + target_x
            if constraints[target] != UNCONSTRAINED_PHYSICAL_CODE:
                return
            row = errors[target_y % 3]
            offset = target_x * 3
            for channel in range(3):
                row[offset + channel] += residual[channel] * weight

        for y in range(image.height):
            direction = -1 if selected.pipeline_options.serpentine and y & 1 else 1
            xs = (
                range(image.width - 1, -1, -1)
                if direction < 0
                else range(image.width)
            )
            row_errors = errors[y % 3]
            for x in xs:
                index = y * image.width + x
                source = _pixel_linear(image, index)[0]
                fixed_code = constraints[index]
                if fixed_code != UNCONSTRAINED_PHYSICAL_CODE:
                    selected_code = fixed_code
                    effective = source
                    diffuse = False
                else:
                    offset = x * 3
                    effective = _clamp(
                        (
                            source[0] + row_errors[offset],
                            source[1] + row_errors[offset + 1],
                            source[2] + row_errors[offset + 2],
                        )
                    )
                    lab = linear_rgb_to_lab(effective)
                    best: Optional[tuple[float, int]] = None
                    for entry in entries:
                        transition_cost = 0.0
                        changed_penalty = 0.0
                        if current is not None:
                            old_code = current[index]
                            if costs is not None:
                                transition_cost = costs[(old_code, entry.code)]
                            changed_penalty = float(old_code != entry.code)
                        elif worst_cost is not None:
                            transition_cost = worst_cost[entry.code]
                            changed_penalty = 1.0
                        neighbours: list[int] = []
                        if x and direction > 0:
                            neighbours.append(codes_buffer[index - 1])
                        if x + 1 < image.width and direction < 0:
                            neighbours.append(codes_buffer[index + 1])
                        if y:
                            neighbours.append(codes_buffer[index - image.width])
                        spatial = (
                            sum(value == entry.code for value in neighbours)
                            / len(neighbours)
                            if neighbours
                            else 0.0
                        )
                        score = (
                            selected.alpha * delta_e_ciede2000(lab, entry.lab)
                            + selected.beta * transition_cost
                            + selected.gamma * changed_penalty
                            + selected.delta * spatial
                        )
                        candidate = (score, entry.code)
                        if best is None or candidate < best:
                            best = candidate
                    assert best is not None
                    selected_code = best[1]
                    diffuse = True
                codes_buffer[index] = selected_code
                if not diffuse:
                    continue
                colour = diffusion[selected_code]
                residual = (
                    effective[0] - colour[0],
                    effective[1] - colour[1],
                    effective[2] - colour[2],
                )
                if selected.pipeline_options.dither is DitherMode.FLOYD_STEINBERG:
                    add_error(x + direction, y, residual, 7.0 / 16.0)
                    add_error(x - direction, y + 1, residual, 3.0 / 16.0)
                    add_error(x, y + 1, residual, 5.0 / 16.0)
                    add_error(x + direction, y + 1, residual, 1.0 / 16.0)
                else:
                    for target_x, target_y in (
                        (x + direction, y),
                        (x + 2 * direction, y),
                        (x - direction, y + 1),
                        (x, y + 1),
                        (x + direction, y + 1),
                        (x, y + 2),
                    ):
                        add_error(target_x, target_y, residual, 1.0 / 8.0)
            errors[y % 3] = [0.0] * slots
        codes = bytes(codes_buffer)
        frame = pack_pixels(codes, image.width, image.height)
        execution_path = "measured-transition-aware-error-diffusion"

    histogram = _transition_histogram(current, codes)
    objectives = _objective_metrics(image, codes, palette, current, costs)
    counts = {str(code): codes.count(code) for code in COLOR_ORDER}
    formal_input_eligible = bool(
        complete_profile
        and palette.calibrated
        and current is not None
        and binding_record["verified"] is True
    )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": RESULT_KIND,
        "algorithm_id": ALGORITHM_ID,
        "execution_path": execution_path,
        "input": {
            "width": image.width,
            "height": image.height,
            "mode": image.mode,
            "raster_sha256": _sha256(image.pixels),
        },
        "palette": {
            "palette_id": palette.palette_id,
            "canonical_sha256": palette.canonical_sha256,
            "calibrated": palette.calibrated,
            "calibration_artifact_sha256": (
                palette.calibration.artifact_sha256
                if palette.calibration is not None
                else None
            ),
        },
        "transition_profile": profile_record,
        "measurement_binding": binding_record,
        "options": selected.to_dict(),
        "current_state": {
            "known": current is not None,
            "codes_sha256": _sha256(current) if current is not None else None,
            "mode": (
                "exact-known-frame"
                if current is not None
                else selected.unknown_current_mode.value
            ),
        },
        "output": {
            "frame_bytes": len(frame),
            "frame_sha256": _sha256(frame),
            "frame_fnv1a": f"0x{fnv1a(frame):08X}",
            "codes_sha256": _sha256(codes),
            "counts": counts,
            "transition_histogram_code_order": list(COLOR_ORDER),
            "transition_histogram": histogram,
            "transition_histogram_sum": (
                sum(sum(row) for row in histogram) if histogram is not None else None
            ),
        },
        "objectives": objectives,
        "classification": {
            "offline_only": True,
            "device_io_performed": False,
            "network_io_performed": False,
            "visible_refresh_authorized": False,
            "formal_input_eligible": formal_input_eligible,
            "optimizer_output_hardware_qualified": False,
            "perceptual_only_fallback": perceptual_fallback,
            "ordinary_quantizer_exact_degeneration": ordinary_degenerate,
            "fixed_global_waveform": True,
            "busy_time_reduction_claim_allowed": False,
            "transition_specific_or_partial_waveform_present": False,
            "pareto_selection_required": True,
        },
    }
    report = _seal(unsigned, RESULT_HASH_SCOPE)
    validate_transition_optimization_report(report)
    return TransitionOptimizationResult(
        image.width, image.height, frame, codes, palette, report
    )


def validate_transition_optimization_report(
    report: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Validate report integrity and the safety/identity invariants."""

    if not isinstance(report, Mapping):
        raise TransitionOptimizationError("optimization report must be an object")
    expected = {
        "schema_version",
        "kind",
        "algorithm_id",
        "execution_path",
        "input",
        "palette",
        "transition_profile",
        "measurement_binding",
        "options",
        "current_state",
        "output",
        "objectives",
        "classification",
        "integrity",
    }
    if set(report) != expected:
        raise TransitionOptimizationError("optimization report fields changed")
    if (
        report["schema_version"] != SCHEMA_VERSION
        or report["kind"] != RESULT_KIND
        or report["algorithm_id"] != ALGORITHM_ID
    ):
        raise TransitionOptimizationError("optimization report schema changed")
    unsigned = dict(report)
    integrity = unsigned.pop("integrity")
    if integrity != {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": RESULT_HASH_SCOPE,
    }:
        raise TransitionOptimizationError("optimization report integrity is invalid")
    classification = report["classification"]
    if not isinstance(classification, Mapping) or any(
        classification.get(field) is not expected_value
        for field, expected_value in {
            "offline_only": True,
            "device_io_performed": False,
            "network_io_performed": False,
            "visible_refresh_authorized": False,
            "optimizer_output_hardware_qualified": False,
            "fixed_global_waveform": True,
            "busy_time_reduction_claim_allowed": False,
            "transition_specific_or_partial_waveform_present": False,
            "pareto_selection_required": True,
        }.items()
    ):
        raise TransitionOptimizationError("optimization safety classification changed")
    palette_record = report["palette"]
    profile_record = report["transition_profile"]
    current_record = report["current_state"]
    binding_record = report["measurement_binding"]
    if not all(
        isinstance(value, Mapping)
        for value in (
            palette_record,
            profile_record,
            current_record,
            binding_record,
        )
    ):
        raise TransitionOptimizationError("optimization evidence records are invalid")
    if set(profile_record) != {
        "present",
        "canonical_sha256",
        "hardware_tested",
        "complete_6x6",
        "panel_serial",
        "firmware_binary_sha256",
        "waveform_id",
        "waveform_sha256",
        "environment",
        "component_ranges",
        "fixed_global_busy_range_ms",
    }:
        raise TransitionOptimizationError("transition profile evidence fields changed")
    if set(binding_record) != {"present", "verified", "binding", "blockers"}:
        raise TransitionOptimizationError("measurement binding evidence fields changed")
    if binding_record["verified"] is True:
        binding = binding_record["binding"]
        if (
            binding_record["present"] is not True
            or binding_record["blockers"] != []
            or not isinstance(binding, Mapping)
            or set(binding)
            != {
                "binding_id",
                "palette_canonical_sha256",
                "palette_calibration_artifact_sha256",
                "transition_profile_canonical_sha256",
                "panel_serial",
                "firmware_binary_sha256",
                "waveform_sha256",
                "review_artifact_sha256",
            }
            or binding["palette_canonical_sha256"]
            != palette_record.get("canonical_sha256")
            or binding["palette_calibration_artifact_sha256"]
            != palette_record.get("calibration_artifact_sha256")
            or binding["transition_profile_canonical_sha256"]
            != profile_record["canonical_sha256"]
            or binding["panel_serial"] != profile_record["panel_serial"]
            or binding["firmware_binary_sha256"]
            != profile_record["firmware_binary_sha256"]
            or binding["waveform_sha256"] != profile_record["waveform_sha256"]
        ):
            raise TransitionOptimizationError("measurement binding evidence is invalid")
        for field in (
            "palette_canonical_sha256",
            "palette_calibration_artifact_sha256",
            "transition_profile_canonical_sha256",
            "firmware_binary_sha256",
            "waveform_sha256",
            "review_artifact_sha256",
        ):
            _sha_field(binding[field], label=f"report binding.{field}")
    elif (
        binding_record["present"] is not False
        or binding_record["binding"] is not None
        or binding_record["blockers"]
        != ["reviewed_palette_transition_cross_asset_binding_missing"]
    ):
        raise TransitionOptimizationError("missing measurement binding semantics changed")
    expected_formal = bool(
        palette_record.get("calibrated") is True
        and profile_record["hardware_tested"] is True
        and profile_record["complete_6x6"] is True
        and current_record.get("known") is True
        and binding_record["verified"] is True
    )
    if classification.get("formal_input_eligible") is not expected_formal:
        raise TransitionOptimizationError("formal input eligibility was not derived")
    if expected_formal and classification.get("perceptual_only_fallback") is not False:
        raise TransitionOptimizationError("formal input cannot use a fallback")
    output = report["output"]
    if not isinstance(output, Mapping):
        raise TransitionOptimizationError("optimization output record is invalid")
    width = report["input"].get("width") if isinstance(report["input"], Mapping) else None
    height = report["input"].get("height") if isinstance(report["input"], Mapping) else None
    if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
        raise TransitionOptimizationError("optimization input dimensions are invalid")
    counts = output.get("counts")
    if (
        not isinstance(counts, Mapping)
        or set(counts) != {str(code) for code in COLOR_ORDER}
        or any(type(value) is not int or value < 0 for value in counts.values())
        or sum(counts.values()) != width * height
    ):
        raise TransitionOptimizationError("optimization colour counts are invalid")
    histogram = output.get("transition_histogram")
    if histogram is None:
        if output.get("transition_histogram_sum") is not None:
            raise TransitionOptimizationError("unknown-state histogram sum must be null")
    else:
        if (
            not isinstance(histogram, list)
            or len(histogram) != 6
            or any(
                not isinstance(row, list)
                or len(row) != 6
                or any(type(value) is not int or value < 0 for value in row)
                for row in histogram
            )
            or sum(sum(row) for row in histogram) != width * height
            or output.get("transition_histogram_sum") != width * height
        ):
            raise TransitionOptimizationError("transition histogram is invalid")
    return report


def _dominates(first: Mapping[str, float], second: Mapping[str, float]) -> bool:
    fields = (
        "perceptual_error_de00_mean",
        "normalized_transition_cost_mean",
        "changed_ratio",
        "spatial_same_selected_neighbour_penalty_mean",
    )
    return all(first[field] <= second[field] for field in fields) and any(
        first[field] < second[field] for field in fields
    )


def build_pareto_report(
    image: RasterImage,
    *,
    palette: Palette,
    transition_profile: Mapping[str, Any],
    current_codes: bytes,
    measurement_binding: Optional[TransitionInputBinding] = None,
    option_grid: Sequence[TransitionOptimizationOptions],
    allow_uncalibrated_palette: bool = False,
) -> dict[str, Any]:
    """Evaluate an explicit weight grid and return every non-dominated point."""

    if not isinstance(option_grid, Sequence) or isinstance(option_grid, (str, bytes)):
        raise TransitionOptimizationError("option_grid must be a non-empty sequence")
    if not option_grid:
        raise TransitionOptimizationError("option_grid must not be empty")
    fingerprints: set[str] = set()
    points: list[dict[str, Any]] = []
    for index, options in enumerate(option_grid):
        if type(options) is not TransitionOptimizationOptions:
            raise TransitionOptimizationError("option_grid contains an invalid option")
        fingerprint = _sha256(options.to_dict())
        if fingerprint in fingerprints:
            raise TransitionOptimizationError("option_grid contains a duplicate weight point")
        fingerprints.add(fingerprint)
        result = optimize_transition_aware(
            image,
            palette=palette,
            transition_profile=transition_profile,
            current_codes=current_codes,
            measurement_binding=measurement_binding,
            options=options,
            allow_uncalibrated_palette=allow_uncalibrated_palette,
        )
        metrics = dict(result.report["objectives"])
        if any(
            metrics[field] is None
            for field in (
                "normalized_transition_cost_mean",
                "changed_ratio",
            )
        ):
            raise TransitionOptimizationError(
                "Pareto comparison requires known current state and measured costs"
            )
        points.append(
            {
                "index": index,
                "options_sha256": fingerprint,
                "options": options.to_dict(),
                "frame_sha256": result.report["output"]["frame_sha256"],
                "report_canonical_sha256": result.report["integrity"][
                    "canonical_sha256"
                ],
                "objectives": metrics,
                "dominated": False,
                "dominated_by_indices": [],
            }
        )
    for point in points:
        dominators = [
            other["index"]
            for other in points
            if other is not point
            and _dominates(other["objectives"], point["objectives"])
        ]
        point["dominated_by_indices"] = dominators
        point["dominated"] = bool(dominators)
    nondominated = [point["index"] for point in points if not point["dominated"]]
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": PARETO_KIND,
        "algorithm_id": ALGORITHM_ID,
        "input_raster_sha256": _sha256(image.pixels),
        "palette_canonical_sha256": palette.canonical_sha256,
        "transition_profile_canonical_sha256": _sha256(transition_profile),
        "current_codes_sha256": _sha256(bytes(current_codes)),
        "measurement_binding_sha256": (
            _sha256(measurement_binding.to_dict())
            if measurement_binding is not None
            else None
        ),
        "points": points,
        "nondominated_indices": nondominated,
        "selection": None,
        "classification": {
            "offline_only": True,
            "single_best_claimed": False,
            "operator_or_preregistered_rule_must_select": True,
            "hardware_qualified": False,
            "visible_refresh_authorized": False,
            "busy_time_reduction_claim_allowed": False,
        },
    }
    report = _seal(unsigned, PARETO_HASH_SCOPE)
    validate_pareto_report(report)
    return report


def validate_pareto_report(report: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(report, Mapping):
        raise TransitionOptimizationError("Pareto report must be an object")
    expected = {
        "schema_version",
        "kind",
        "algorithm_id",
        "input_raster_sha256",
        "palette_canonical_sha256",
        "transition_profile_canonical_sha256",
        "current_codes_sha256",
        "measurement_binding_sha256",
        "points",
        "nondominated_indices",
        "selection",
        "classification",
        "integrity",
    }
    if set(report) != expected:
        raise TransitionOptimizationError("Pareto report fields changed")
    if (
        report["schema_version"] != SCHEMA_VERSION
        or report["kind"] != PARETO_KIND
        or report["algorithm_id"] != ALGORITHM_ID
        or report["selection"] is not None
    ):
        raise TransitionOptimizationError("Pareto report schema/selection changed")
    unsigned = dict(report)
    integrity = unsigned.pop("integrity")
    if integrity != {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": PARETO_HASH_SCOPE,
    }:
        raise TransitionOptimizationError("Pareto report integrity is invalid")
    points = report["points"]
    if not isinstance(points, list) or not points:
        raise TransitionOptimizationError("Pareto report points are invalid")
    indices = list(range(len(points)))
    if [point.get("index") for point in points if isinstance(point, Mapping)] != indices:
        raise TransitionOptimizationError("Pareto point indices are invalid")
    for point in points:
        if not isinstance(point, Mapping):
            raise TransitionOptimizationError("Pareto point is invalid")
        expected_dominators = [
            other["index"]
            for other in points
            if other is not point
            and _dominates(other["objectives"], point["objectives"])
        ]
        if (
            point.get("dominated_by_indices") != expected_dominators
            or point.get("dominated") is not bool(expected_dominators)
        ):
            raise TransitionOptimizationError("Pareto dominance evidence changed")
    expected_front = [point["index"] for point in points if not point["dominated"]]
    if report["nondominated_indices"] != expected_front:
        raise TransitionOptimizationError("Pareto frontier changed")
    classification = report["classification"]
    if not isinstance(classification, Mapping) or classification != {
        "offline_only": True,
        "single_best_claimed": False,
        "operator_or_preregistered_rule_must_select": True,
        "hardware_qualified": False,
        "visible_refresh_authorized": False,
        "busy_time_reduction_claim_allowed": False,
    }:
        raise TransitionOptimizationError("Pareto safety classification changed")
    return report
