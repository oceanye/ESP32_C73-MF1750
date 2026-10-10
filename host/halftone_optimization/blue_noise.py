"""Deterministic void-and-cluster blue-noise threshold generation.

Unlike the C2 hashed-threshold baseline, this module constructs a ranked
threshold tile from spatial density.  It relaxes a seeded binary pattern by
moving tight clusters into large voids, then assigns the complete threshold
ordering by cluster removal and void insertion.
"""

from __future__ import annotations

from array import array
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
import struct
from typing import Any, Dict, Sequence, Tuple

from host.color_pipeline.color import (
    SRGB8_TO_LINEAR,
    delta_e_ciede2000,
    linear_rgb_to_lab,
)
from host.color_pipeline.palette import Palette, reference_palette
from host.color_pipeline.pipeline import RasterImage
from host.color_pipeline.preview import encode_rgb_png
from host.epd_frame import PHYSICAL_COLOR_CODES

from .model import (
    ALLOWED_CODES,
    UNCONSTRAINED_CODE,
    HalftoneModelError,
    validate_code_constraints,
)


BLUE_NOISE_SCHEMA_VERSION = 1
BLUE_NOISE_ALGORITHM = "deterministic-void-and-cluster-ranked-threshold-v1"
AREA_WEIGHTED_BLUE_NOISE_ALGORITHM = (
    "six-channel-decorrelated-void-and-cluster-gumbel-max-v1"
)
AREA_WEIGHTED_ORDERED_ALGORITHM = (
    "six-colour-area-weighted-bayer-8x8-inverse-cdf-v1"
)
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


class BlueNoiseError(HalftoneModelError):
    """Raised when blue-noise generation or quantization input is invalid."""


class _SplitMix64:
    """Small specified PRNG whose stream is independent of Python versions."""

    __slots__ = ("state",)

    def __init__(self, seed: int) -> None:
        self.state = seed & 0xFFFFFFFFFFFFFFFF

    def next_u64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        value = self.state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return value ^ (value >> 31)

    def below(self, limit: int) -> int:
        if limit <= 0:
            raise ValueError("limit must be positive")
        # Rejection removes modulo bias and preserves a fully specified stream.
        threshold = ((1 << 64) - limit) % limit
        while True:
            value = self.next_u64()
            if value >= threshold:
                return value % limit


def _finite_float(value: object, label: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BlueNoiseError(f"{label} must be numeric and not boolean")
    converted = float(value)
    if not math.isfinite(converted) or not minimum <= converted <= maximum:
        raise BlueNoiseError(f"{label} must be finite and in [{minimum}, {maximum}]")
    return converted


@dataclass(frozen=True)
class BlueNoiseOptions:
    """Bounded parameters for a reusable blue-noise threshold tile."""

    tile_width: int = 32
    tile_height: int = 32
    seed: int = 0x5331424E
    sigma: float = 1.5
    initial_density: float = 0.1
    max_relaxation_moves: int = 4096

    def __post_init__(self) -> None:
        for label in ("tile_width", "tile_height", "max_relaxation_moves"):
            value = getattr(self, label)
            if type(value) is not int or value <= 0:
                raise BlueNoiseError(f"{label} must be a positive integer")
        if self.tile_width * self.tile_height < 16:
            raise BlueNoiseError("blue-noise tile must contain at least 16 samples")
        if self.tile_width * self.tile_height > 16384:
            raise BlueNoiseError("blue-noise tile is limited to 16384 samples")
        if type(self.seed) is not int or not 0 <= self.seed <= 0xFFFFFFFFFFFFFFFF:
            raise BlueNoiseError("seed must be an integer in [0, 0xffffffffffffffff]")
        object.__setattr__(self, "sigma", _finite_float(self.sigma, "sigma", 0.25, 32.0))
        density = _finite_float(self.initial_density, "initial_density", 0.01, 0.49)
        object.__setattr__(self, "initial_density", density)


@dataclass(frozen=True)
class BlueNoiseThresholdMap:
    width: int
    height: int
    ranks: Tuple[int, ...]
    seed: int
    sigma: float
    initial_density: float
    relaxation_moves: int
    relaxation_stop_reason: str
    low_frequency_energy: float
    mean_nearest_distance: float

    def __post_init__(self) -> None:
        sample_count = self.width * self.height
        if len(self.ranks) != sample_count or set(self.ranks) != set(range(sample_count)):
            raise BlueNoiseError("rank map must be a complete threshold permutation")

    @property
    def thresholds(self) -> Tuple[float, ...]:
        inverse = 1.0 / (self.width * self.height)
        return tuple((rank + 0.5) * inverse for rank in self.ranks)

    def threshold_at(self, x_value: int, y_value: int) -> float:
        if type(x_value) is not int or type(y_value) is not int:
            raise BlueNoiseError("threshold coordinates must be integers")
        index = (y_value % self.height) * self.width + (x_value % self.width)
        return (self.ranks[index] + 0.5) / (self.width * self.height)

    def to_report(self) -> Dict[str, Any]:
        rank_bytes = b"".join(struct.pack(">I", rank) for rank in self.ranks)
        report: Dict[str, Any] = {
            "schema_version": BLUE_NOISE_SCHEMA_VERSION,
            "kind": "mf1750-blue-noise-threshold-report",
            "algorithm": BLUE_NOISE_ALGORITHM,
            "width": self.width,
            "height": self.height,
            "seed": self.seed,
            "sigma": self.sigma,
            "initial_density": self.initial_density,
            "relaxation": {
                "moves": self.relaxation_moves,
                "stop_reason": self.relaxation_stop_reason,
            },
            "diagnostics": {
                "low_frequency_energy": self.low_frequency_energy,
                "mean_nearest_toroidal_distance": self.mean_nearest_distance,
            },
            "rank_sha256": hashlib.sha256(rank_bytes).hexdigest(),
            "threshold_contract": "complete rank permutation; threshold=(rank+0.5)/N",
            "tiling_warning": (
                "threshold_at repeats this finite blue-noise tile; use a sufficiently "
                "large tile and the DBS periodic penalty for final simulation"
            ),
            "qualification": {
                "simulation_only": True,
                "hardware_tested": False,
                "hardware_qualified": False,
            },
        }
        canonical = json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        report["report_integrity"] = {
            "canonical_sha256": hashlib.sha256(canonical).hexdigest(),
            "scope": "entire report excluding report_integrity; canonical JSON",
        }
        return report


def _gaussian_torus_offsets(
    width: int, height: int, sigma: float
) -> Tuple[Tuple[int, int, float], ...]:
    radius = max(1, int(math.ceil(3.0 * sigma)))
    aggregated: Dict[Tuple[int, int], float] = {}
    for y_value in range(-radius, radius + 1):
        for x_value in range(-radius, radius + 1):
            wrapped = (x_value % width, y_value % height)
            weight = math.exp(-0.5 * (x_value * x_value + y_value * y_value) / (sigma * sigma))
            aggregated[wrapped] = aggregated.get(wrapped, 0.0) + weight
    return tuple(
        (x_value, y_value, weight)
        for (x_value, y_value), weight in sorted(aggregated.items())
    )


def _update_energy(
    energy: list[float],
    point: int,
    multiplier: float,
    width: int,
    height: int,
    offsets: Sequence[Tuple[int, int, float]],
) -> None:
    point_y, point_x = divmod(point, width)
    for offset_x, offset_y, weight in offsets:
        target_x = (point_x + offset_x) % width
        target_y = (point_y + offset_y) % height
        energy[target_y * width + target_x] += multiplier * weight


def _select_extreme(
    occupancy: Sequence[bool], energy: Sequence[float], occupied: bool, maximum: bool
) -> int:
    selected = -1
    selected_energy = -math.inf if maximum else math.inf
    for index, is_occupied in enumerate(occupancy):
        if is_occupied is not occupied:
            continue
        candidate = energy[index]
        if (
            (maximum and candidate > selected_energy)
            or (not maximum and candidate < selected_energy)
            or (candidate == selected_energy and (selected < 0 or index < selected))
        ):
            selected = index
            selected_energy = candidate
    if selected < 0:
        raise AssertionError("void-and-cluster selection set is empty")
    return selected


def _diagnostics(
    ranks: Sequence[int], width: int, height: int, density: float
) -> Tuple[float, float]:
    count = max(1, min(len(ranks) - 1, int(round(len(ranks) * density))))
    points = [index for index, rank in enumerate(ranks) if rank < count]
    nearest = []
    for point in points:
        y_one, x_one = divmod(point, width)
        best = math.inf
        for other in points:
            if other == point:
                continue
            y_two, x_two = divmod(other, width)
            dx = min(abs(x_one - x_two), width - abs(x_one - x_two))
            dy = min(abs(y_one - y_two), height - abs(y_one - y_two))
            best = min(best, math.hypot(dx, dy))
        if math.isfinite(best):
            nearest.append(best)
    mean_nearest = math.fsum(nearest) / len(nearest) if nearest else 0.0

    selected = set(points)
    low_energy = 0.0
    frequency_count = 0
    mean = len(points) / len(ranks)
    for ky in range(-2, 3):
        for kx in range(-2, 3):
            if kx == 0 and ky == 0:
                continue
            real = imaginary = 0.0
            for index in range(len(ranks)):
                y_value, x_value = divmod(index, width)
                signal = (1.0 if index in selected else 0.0) - mean
                angle = -2.0 * math.pi * (
                    kx * x_value / width + ky * y_value / height
                )
                real += signal * math.cos(angle)
                imaginary += signal * math.sin(angle)
            low_energy += (real * real + imaginary * imaginary) / (len(ranks) ** 2)
            frequency_count += 1
    return low_energy / max(1, frequency_count), mean_nearest


@lru_cache(maxsize=64)
def generate_blue_noise_thresholds(
    options: BlueNoiseOptions | None = None,
) -> BlueNoiseThresholdMap:
    """Generate one bounded deterministic void-and-cluster rank map."""

    selected = BlueNoiseOptions() if options is None else options
    if type(selected) is not BlueNoiseOptions:
        raise BlueNoiseError("options must be a BlueNoiseOptions instance or None")
    width = selected.tile_width
    height = selected.tile_height
    sample_count = width * height
    initial_count = max(1, min(sample_count - 1, int(round(sample_count * selected.initial_density))))
    rng = _SplitMix64(selected.seed)
    shuffled = list(range(sample_count))
    for index in range(sample_count - 1, 0, -1):
        other = rng.below(index + 1)
        shuffled[index], shuffled[other] = shuffled[other], shuffled[index]
    occupancy = [False] * sample_count
    for index in shuffled[:initial_count]:
        occupancy[index] = True
    offsets = _gaussian_torus_offsets(width, height, selected.sigma)
    energy = [0.0] * sample_count
    for index, occupied in enumerate(occupancy):
        if occupied:
            _update_energy(energy, index, 1.0, width, height, offsets)

    moves = 0
    stop_reason = "relaxation_budget"
    for _ in range(selected.max_relaxation_moves):
        cluster = _select_extreme(occupancy, energy, True, True)
        occupancy[cluster] = False
        _update_energy(energy, cluster, -1.0, width, height, offsets)
        void = _select_extreme(occupancy, energy, False, False)
        occupancy[void] = True
        _update_energy(energy, void, 1.0, width, height, offsets)
        if void == cluster:
            stop_reason = "stable_void_cluster"
            break
        moves += 1

    stable_occupancy = occupancy[:]
    stable_energy = energy[:]
    ranks = [-1] * sample_count

    lower_occupancy = stable_occupancy[:]
    lower_energy = stable_energy[:]
    for rank in range(initial_count - 1, -1, -1):
        cluster = _select_extreme(lower_occupancy, lower_energy, True, True)
        ranks[cluster] = rank
        lower_occupancy[cluster] = False
        _update_energy(lower_energy, cluster, -1.0, width, height, offsets)

    upper_occupancy = stable_occupancy[:]
    upper_energy = stable_energy[:]
    for rank in range(initial_count, sample_count):
        void = _select_extreme(upper_occupancy, upper_energy, False, False)
        ranks[void] = rank
        upper_occupancy[void] = True
        _update_energy(upper_energy, void, 1.0, width, height, offsets)

    low_frequency, mean_nearest = _diagnostics(
        ranks, width, height, selected.initial_density
    )
    return BlueNoiseThresholdMap(
        width,
        height,
        tuple(ranks),
        selected.seed,
        selected.sigma,
        selected.initial_density,
        moves,
        stop_reason,
        low_frequency,
        mean_nearest,
    )


def _pixel_linear(image: RasterImage, index: int) -> Tuple[float, float, float]:
    offset = index * image.channels
    red = SRGB8_TO_LINEAR[image.pixels[offset]]
    green = SRGB8_TO_LINEAR[image.pixels[offset + 1]]
    blue = SRGB8_TO_LINEAR[image.pixels[offset + 2]]
    if image.channels == 3:
        return red, green, blue
    alpha = image.pixels[offset + 3] / 255.0
    inverse = 1.0 - alpha
    return red * alpha + inverse, green * alpha + inverse, blue * alpha + inverse


def raster_linear_rgb(image: RasterImage) -> array:
    if type(image) is not RasterImage:
        raise BlueNoiseError("image must be a RasterImage instance")
    output = array("f", [0.0]) * (image.width * image.height * 3)
    for index in range(image.width * image.height):
        colour = _pixel_linear(image, index)
        offset = index * 3
        output[offset] = colour[0]
        output[offset + 1] = colour[1]
        output[offset + 2] = colour[2]
    return output


@dataclass(frozen=True)
class BlueNoiseQuantizationResult:
    width: int
    height: int
    codes: bytes
    palette: Palette
    threshold_maps: Tuple[BlueNoiseThresholdMap, ...]
    report: Dict[str, Any]

    @property
    def threshold_map(self) -> BlueNoiseThresholdMap:
        """Compatibility view for the legacy one-channel baseline."""

        return self.threshold_maps[0]

    def preview_rgb(self) -> bytes:
        colours = {entry.code: entry.preview_rgb for entry in self.palette.entries}
        return b"".join(bytes(colours[code]) for code in self.codes)

    def preview_png(self) -> bytes:
        return encode_rgb_png(self.width, self.height, self.preview_rgb())


@dataclass(frozen=True)
class AreaWeightedOrderedResult:
    width: int
    height: int
    codes: bytes
    palette: Palette
    report: Dict[str, Any]

    def preview_rgb(self) -> bytes:
        colours = {entry.code: entry.preview_rgb for entry in self.palette.entries}
        return b"".join(bytes(colours[code]) for code in self.codes)

    def preview_png(self) -> bytes:
        return encode_rgb_png(self.width, self.height, self.preview_rgb())


def quantize_blue_noise(
    image: RasterImage,
    *,
    palette: Palette | None = None,
    options: BlueNoiseOptions | None = None,
    code_constraints: bytes | bytearray | memoryview | None = None,
) -> BlueNoiseQuantizationResult:
    """Quantize to the nearest two physical colours using a blue-noise rank tile."""

    if type(image) is not RasterImage:
        raise BlueNoiseError("image must be a RasterImage instance")
    selected_palette = reference_palette() if palette is None else palette
    if type(selected_palette) is not Palette:
        raise BlueNoiseError("palette must be a Palette instance or None")
    threshold_map = generate_blue_noise_thresholds(options)
    entries = selected_palette.entries
    codes = bytearray(image.width * image.height)
    constraints = validate_code_constraints(code_constraints, len(codes))
    for y_value in range(image.height):
        for x_value in range(image.width):
            index = y_value * image.width + x_value
            if constraints[index] != UNCONSTRAINED_CODE:
                selected_code = constraints[index]
            else:
                target_lab = linear_rgb_to_lab(_pixel_linear(image, index))
                distances = sorted(
                    (delta_e_ciede2000(target_lab, entry.lab), entry.code)
                    for entry in entries
                )
                first_distance, first_code = distances[0]
                second_distance, second_code = distances[1]
                if first_distance == 0.0:
                    selected_code = first_code
                else:
                    distance_sum = first_distance + second_distance
                    probability_second = (
                        0.5 if distance_sum == 0.0 else first_distance / distance_sum
                    )
                    selected_code = (
                        second_code
                        if threshold_map.threshold_at(x_value, y_value)
                        < probability_second
                        else first_code
                    )
            codes[index] = selected_code
    if set(codes).difference(PHYSICAL_COLOR_CODES):
        raise AssertionError("blue-noise quantizer emitted a non-physical code")
    report: Dict[str, Any] = {
        "schema_version": BLUE_NOISE_SCHEMA_VERSION,
        "kind": "mf1750-blue-noise-quantization-report",
        "algorithm": "legacy-nearest-two-ciede2000-with-void-and-cluster-v1",
        "width": image.width,
        "height": image.height,
        "seed": threshold_map.seed,
        "input_raster_sha256": hashlib.sha256(image.pixels).hexdigest(),
        "codes_sha256": hashlib.sha256(codes).hexdigest(),
        "physical_codes": list(ALLOWED_CODES),
        "mixing_weights": {
            "source": "legacy nearest-two CIEDE2000 distance ratio",
            "nearest_two_delta_e_ratio_used": True,
            "g1_six_colour_area_weight_contract": False,
            "recommended_for_new_area_weighted_pipeline": False,
        },
        "palette": {
            "id": selected_palette.palette_id,
            "calibrated": selected_palette.calibrated,
            "canonical_sha256": selected_palette.canonical_sha256,
        },
        "threshold_map": threshold_map.to_report(),
        "code_constraints": {
            "provided": code_constraints is not None,
            "locked_pixels": sum(
                value != UNCONSTRAINED_CODE for value in constraints
            ),
            "mask_sha256": hashlib.sha256(constraints).hexdigest(),
            "unconstrained_sentinel": UNCONSTRAINED_CODE,
        },
        "qualification": {
            "simulation_only": True,
            "hardware_tested": False,
            "hardware_qualified": False,
            "reason": "blue-noise threshold and preview have not been fitted to a panel",
        },
    }
    canonical = json.dumps(
        report,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    report["report_integrity"] = {
        "canonical_sha256": hashlib.sha256(canonical).hexdigest(),
        "scope": "entire report excluding report_integrity; canonical JSON",
    }
    return BlueNoiseQuantizationResult(
        image.width,
        image.height,
        bytes(codes),
        selected_palette,
        (threshold_map,),
        report,
    )


def _channel_options(options: BlueNoiseOptions, channel_index: int) -> BlueNoiseOptions:
    # Derive independent, specified SplitMix64 streams rather than coordinate
    # hashes or phase shifts of one common mask.
    rng = _SplitMix64(options.seed ^ (0xD1B54A32D192ED03 * (channel_index + 1)))
    return BlueNoiseOptions(
        tile_width=options.tile_width,
        tile_height=options.tile_height,
        seed=rng.next_u64(),
        sigma=options.sigma,
        initial_density=options.initial_density,
        max_relaxation_moves=options.max_relaxation_moves,
    )


def quantize_area_weighted_blue_noise(
    width: int,
    height: int,
    area_weights: Sequence[float],
    *,
    palette: Palette | None = None,
    options: BlueNoiseOptions | None = None,
    solver_id: str = "external-six-colour-area-weight-solver",
    code_constraints: bytes | bytearray | memoryview | None = None,
) -> BlueNoiseQuantizationResult:
    """Assign six physical colours from per-pixel non-negative area weights.

    ``area_weights`` is flat top-left row-major data in physical-code order
    ``(0, 1, 2, 3, 5, 6)``.  Every six-value vector must sum to one.  Six
    independently generated void-and-cluster rank maps feed deterministic
    Gumbel-max categorical assignment; this avoids treating nearest-two Delta E
    ratios as physical mixing weights.
    """

    if type(width) is not int or width <= 0 or type(height) is not int or height <= 0:
        raise BlueNoiseError("area-weight dimensions must be positive integers")
    if not isinstance(solver_id, str) or not solver_id.strip():
        raise BlueNoiseError("solver_id must be a non-empty string")
    expected = width * height * len(ALLOWED_CODES)
    try:
        actual = len(area_weights)
    except TypeError as error:
        raise BlueNoiseError("area_weights must be a sized sequence") from error
    if actual != expected:
        raise BlueNoiseError(f"area_weights has {actual} values; expected {expected}")
    weight_hash = hashlib.sha256()
    # Binary64 storage keeps the validated canonical values without the large
    # per-object overhead of millions of Python floats at panel resolution.
    normalized_weights = array("d", [0.0]) * expected
    for pixel in range(width * height):
        start = pixel * len(ALLOWED_CODES)
        total = 0.0
        for channel in range(len(ALLOWED_CODES)):
            raw = area_weights[start + channel]
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise BlueNoiseError("area weights must be numeric and not boolean")
            value = float(raw)
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise BlueNoiseError("area weights must be finite and in [0, 1]")
            normalized_weights[start + channel] = value
            total += value
            weight_hash.update(struct.pack(">d", value))
        if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise BlueNoiseError(
                f"area weights for pixel {pixel} sum to {total!r}; expected 1"
            )
    selected_palette = reference_palette() if palette is None else palette
    if type(selected_palette) is not Palette:
        raise BlueNoiseError("palette must be a Palette instance or None")
    selected_options = BlueNoiseOptions() if options is None else options
    if type(selected_options) is not BlueNoiseOptions:
        raise BlueNoiseError("options must be a BlueNoiseOptions instance or None")
    threshold_maps = tuple(
        generate_blue_noise_thresholds(_channel_options(selected_options, channel))
        for channel in range(len(ALLOWED_CODES))
    )
    codes = bytearray(width * height)
    constraints = validate_code_constraints(code_constraints, len(codes))
    for y_value in range(height):
        for x_value in range(width):
            pixel = y_value * width + x_value
            if constraints[pixel] != UNCONSTRAINED_CODE:
                codes[pixel] = constraints[pixel]
                continue
            start = pixel * len(ALLOWED_CODES)
            best_score = -math.inf
            best_code = ALLOWED_CODES[0]
            for channel, code in enumerate(ALLOWED_CODES):
                weight = normalized_weights[start + channel]
                if weight == 0.0:
                    continue
                uniform = threshold_maps[channel].threshold_at(x_value, y_value)
                gumbel = -math.log(-math.log(uniform))
                score = math.log(weight) + gumbel
                if score > best_score or (score == best_score and code < best_code):
                    best_score = score
                    best_code = code
            codes[pixel] = best_code
    if set(codes).difference(PHYSICAL_COLOR_CODES):
        raise AssertionError("area-weighted blue-noise quantizer emitted an invalid code")
    report: Dict[str, Any] = {
        "schema_version": BLUE_NOISE_SCHEMA_VERSION,
        "kind": "mf1750-area-weighted-blue-noise-quantization-report",
        "algorithm": AREA_WEIGHTED_BLUE_NOISE_ALGORITHM,
        "width": width,
        "height": height,
        "seed": selected_options.seed,
        "codes_sha256": hashlib.sha256(codes).hexdigest(),
        "physical_code_order": list(ALLOWED_CODES),
        "area_weights": {
            "solver_id": solver_id.strip(),
            "contract": "six finite non-negative weights per pixel; sum=1",
            "canonical_binary64_sha256": weight_hash.hexdigest(),
            "canonical_binary64_scope": (
                "top-left row-major, physical code order, IEEE-754 binary64 big-endian"
            ),
            "nearest_two_delta_e_ratio_used": False,
        },
        "assignment": {
            "method": "categorical Gumbel-max",
            "decorrelated_channels": True,
            "channel_seeds": [threshold.seed for threshold in threshold_maps],
            "threshold_algorithm": BLUE_NOISE_ALGORITHM,
        },
        "code_constraints": {
            "provided": code_constraints is not None,
            "locked_pixels": sum(
                value != UNCONSTRAINED_CODE for value in constraints
            ),
            "mask_sha256": hashlib.sha256(constraints).hexdigest(),
            "unconstrained_sentinel": UNCONSTRAINED_CODE,
        },
        "palette": {
            "id": selected_palette.palette_id,
            "calibrated": selected_palette.calibrated,
            "canonical_sha256": selected_palette.canonical_sha256,
        },
        "threshold_maps": [threshold.to_report() for threshold in threshold_maps],
        "qualification": {
            "simulation_only": True,
            "hardware_tested": False,
            "hardware_qualified": False,
            "reason": "area weights and six blue-noise channels have not been fitted to a panel",
        },
    }
    canonical = json.dumps(
        report,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    report["report_integrity"] = {
        "canonical_sha256": hashlib.sha256(canonical).hexdigest(),
        "scope": "entire report excluding report_integrity; canonical JSON",
    }
    return BlueNoiseQuantizationResult(
        width,
        height,
        bytes(codes),
        selected_palette,
        threshold_maps,
        report,
    )


def quantize_area_weighted_ordered(
    width: int,
    height: int,
    area_weights: Sequence[float],
    *,
    palette: Palette | None = None,
    seed: int = 0x4D463137,
    solver_id: str = "external-six-colour-area-weight-solver",
    code_constraints: bytes | bytearray | memoryview | None = None,
) -> AreaWeightedOrderedResult:
    """Assign six area weights with a phase-seeded Bayer 8x8 inverse CDF.

    This is the ordered counterpart to the preferred six-channel blue-noise
    assignment.  It consumes all six G1 weights and never derives a mixture
    from nearest-two Delta E ratios.
    """

    if type(width) is not int or width <= 0 or type(height) is not int or height <= 0:
        raise BlueNoiseError("area-weight dimensions must be positive integers")
    if type(seed) is not int or not 0 <= seed <= 0xFFFFFFFF:
        raise BlueNoiseError("ordered area-weight seed must be a uint32 integer")
    if not isinstance(solver_id, str) or not solver_id.strip():
        raise BlueNoiseError("solver_id must be a non-empty string")
    expected = width * height * len(ALLOWED_CODES)
    try:
        actual = len(area_weights)
    except TypeError as error:
        raise BlueNoiseError("area_weights must be a sized sequence") from error
    if actual != expected:
        raise BlueNoiseError(f"area_weights has {actual} values; expected {expected}")
    normalized_weights = array("d", [0.0]) * expected
    weight_hash = hashlib.sha256()
    for pixel in range(width * height):
        start = pixel * len(ALLOWED_CODES)
        total = 0.0
        for channel in range(len(ALLOWED_CODES)):
            raw = area_weights[start + channel]
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise BlueNoiseError("area weights must be numeric and not boolean")
            value = float(raw)
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise BlueNoiseError("area weights must be finite and in [0, 1]")
            normalized_weights[start + channel] = value
            weight_hash.update(struct.pack(">d", value))
            total += value
        if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise BlueNoiseError(
                f"area weights for pixel {pixel} sum to {total!r}; expected 1"
            )
    selected_palette = reference_palette() if palette is None else palette
    if type(selected_palette) is not Palette:
        raise BlueNoiseError("palette must be a Palette instance or None")
    constraints = validate_code_constraints(code_constraints, width * height)
    codes = bytearray(width * height)
    phase = seed & 63
    for y_value in range(height):
        for x_value in range(width):
            pixel = y_value * width + x_value
            if constraints[pixel] != UNCONSTRAINED_CODE:
                codes[pixel] = constraints[pixel]
                continue
            threshold = (((_BAYER_8X8[y_value & 7][x_value & 7] + phase) & 63) + 0.5) / 64.0
            cumulative = 0.0
            selected_code = ALLOWED_CODES[-1]
            start = pixel * len(ALLOWED_CODES)
            for channel, code in enumerate(ALLOWED_CODES):
                cumulative += normalized_weights[start + channel]
                if threshold < cumulative:
                    selected_code = code
                    break
            codes[pixel] = selected_code
    report: Dict[str, Any] = {
        "schema_version": BLUE_NOISE_SCHEMA_VERSION,
        "kind": "mf1750-area-weighted-ordered-quantization-report",
        "algorithm": AREA_WEIGHTED_ORDERED_ALGORITHM,
        "width": width,
        "height": height,
        "seed": seed,
        "codes_sha256": hashlib.sha256(codes).hexdigest(),
        "physical_code_order": list(ALLOWED_CODES),
        "area_weights": {
            "solver_id": solver_id.strip(),
            "contract": "six finite non-negative weights per pixel; sum=1",
            "canonical_binary64_sha256": weight_hash.hexdigest(),
            "canonical_binary64_scope": (
                "top-left row-major, physical code order, IEEE-754 binary64 big-endian"
            ),
            "nearest_two_delta_e_ratio_used": False,
        },
        "assignment": {
            "method": "categorical inverse CDF",
            "threshold_algorithm": "phase-seeded-bayer-8x8-rank-map-v1",
            "period_width": 8,
            "period_height": 8,
            "rank_phase": phase,
        },
        "code_constraints": {
            "provided": code_constraints is not None,
            "locked_pixels": sum(
                value != UNCONSTRAINED_CODE for value in constraints
            ),
            "mask_sha256": hashlib.sha256(constraints).hexdigest(),
            "unconstrained_sentinel": UNCONSTRAINED_CODE,
        },
        "palette": {
            "id": selected_palette.palette_id,
            "calibrated": selected_palette.calibrated,
            "canonical_sha256": selected_palette.canonical_sha256,
        },
        "qualification": {
            "simulation_only": True,
            "hardware_tested": False,
            "hardware_qualified": False,
            "reason": "area weights and ordered assignment have not been fitted to a panel",
        },
    }
    canonical = json.dumps(
        report,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    report["report_integrity"] = {
        "canonical_sha256": hashlib.sha256(canonical).hexdigest(),
        "scope": "entire report excluding report_integrity; canonical JSON",
    }
    return AreaWeightedOrderedResult(
        width, height, bytes(codes), selected_palette, report
    )
