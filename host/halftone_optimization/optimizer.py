"""Bounded multicolour DBS with overlap-aware, multiscale simulation loss."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import struct
import time
from typing import Any, Callable, Dict, Mapping, Sequence, Tuple

from host.color_pipeline.color import linear_channel_to_srgb
from host.color_pipeline.palette import Palette, reference_palette
from host.color_pipeline.pipeline import RasterImage
from host.color_pipeline.preview import encode_rgb_png
from host.epd_frame import pack_pixels

from .blue_noise import _SplitMix64, raster_linear_rgb
from .model import (
    ALLOWED_CODES,
    UNCONSTRAINED_CODE,
    HalftoneModelError,
    OverlapObservationModel,
    box_blur_rgb,
    box_source_response,
    validate_code_constraints,
    validate_six_codes,
)


DBS_REPORT_SCHEMA_VERSION = 2
DBS_ALGORITHM = "overlap-aware-multicolour-dbs-v1"
DBS_COVERAGE_CONTRACT = "dbs-proposal-coverage-v1"
DBS_PROPOSAL_TRACE_ENCODING = (
    "concatenated big-endian >QBQQ records: one-based proposal ordinal, "
    "operation byte (0=recolour, 1=swap), primary pixel, partner pixel or "
    "uint64-max sentinel"
)
DBS_TILE_GRID_CONTRACT = (
    "row-major proportional grid v1; column=floor(x*columns/width), "
    "row=floor(y*rows/height)"
)
MULTISCALE_SIZES = (3, 7, 15)
MULTISCALE_DEFAULT_WEIGHTS = (0.50, 0.30, 0.20)


class HalftoneOptimizationError(HalftoneModelError):
    """Raised when a DBS option or input violates the offline contract."""


def _number(
    value: object,
    label: str,
    minimum: float,
    maximum: float,
    *,
    minimum_inclusive: bool = True,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HalftoneOptimizationError(f"{label} must be numeric and not boolean")
    converted = float(value)
    lower_ok = converted >= minimum if minimum_inclusive else converted > minimum
    if not math.isfinite(converted) or not lower_ok or converted > maximum:
        relation = "[" if minimum_inclusive else "("
        raise HalftoneOptimizationError(
            f"{label} must be finite and in {relation}{minimum}, {maximum}]"
        )
    return converted


@dataclass(frozen=True)
class DBSOptions:
    """Deterministic search, loss, budget and stop-condition controls."""

    seed: int = 0x53314442
    max_evaluations: int = 2000
    max_accepted_moves: int = 500
    stagnation_evaluations: int = 500
    swap_probability: float = 0.25
    swap_radius: int = 3
    min_improvement: float = 1e-10
    time_limit_seconds: float | None = None
    cancel_check_interval: int = 16
    multiscale_weights: Tuple[float, float, float] = MULTISCALE_DEFAULT_WEIGHTS
    edge_weight: float = 0.10
    direction_weight: float = 0.02
    periodic_weight: float = 0.02
    cluster_weight: float = 0.01

    def __post_init__(self) -> None:
        if type(self.seed) is not int or not 0 <= self.seed <= 0xFFFFFFFFFFFFFFFF:
            raise HalftoneOptimizationError(
                "seed must be an integer in [0, 0xffffffffffffffff]"
            )
        for label in (
            "max_evaluations",
            "max_accepted_moves",
            "stagnation_evaluations",
            "swap_radius",
            "cancel_check_interval",
        ):
            value = getattr(self, label)
            if type(value) is not int or value <= 0:
                raise HalftoneOptimizationError(f"{label} must be a positive integer")
        if self.max_accepted_moves > self.max_evaluations:
            raise HalftoneOptimizationError(
                "max_accepted_moves cannot exceed max_evaluations"
            )
        if self.stagnation_evaluations > self.max_evaluations:
            raise HalftoneOptimizationError(
                "stagnation_evaluations cannot exceed max_evaluations"
            )
        object.__setattr__(
            self,
            "swap_probability",
            _number(self.swap_probability, "swap_probability", 0.0, 1.0),
        )
        object.__setattr__(
            self,
            "min_improvement",
            _number(self.min_improvement, "min_improvement", 0.0, 1e6),
        )
        if self.time_limit_seconds is not None:
            object.__setattr__(
                self,
                "time_limit_seconds",
                _number(
                    self.time_limit_seconds,
                    "time_limit_seconds",
                    0.0,
                    86400.0,
                    minimum_inclusive=False,
                ),
            )
        if not isinstance(self.multiscale_weights, (tuple, list)) or len(
            self.multiscale_weights
        ) != len(MULTISCALE_SIZES):
            raise HalftoneOptimizationError(
                "multiscale_weights must contain weights for 3x3, 7x7 and 15x15"
            )
        scale_weights = tuple(
            _number(value, "multiscale weight", 0.0, 1e6)
            for value in self.multiscale_weights
        )
        if not math.isclose(math.fsum(scale_weights), 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise HalftoneOptimizationError("multiscale_weights must sum to 1")
        object.__setattr__(self, "multiscale_weights", scale_weights)
        for label in (
            "edge_weight",
            "direction_weight",
            "periodic_weight",
            "cluster_weight",
        ):
            object.__setattr__(
                self,
                label,
                _number(getattr(self, label), label, 0.0, 1e6),
            )


@dataclass(frozen=True)
class LossBreakdown:
    total: float
    scale_3x3: float
    scale_7x7: float
    scale_15x15: float
    edge: float
    direction: float
    periodic: float
    cluster: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "total": self.total,
            "multiscale_3x3": self.scale_3x3,
            "multiscale_7x7": self.scale_7x7,
            "multiscale_15x15": self.scale_15x15,
            "edge": self.edge,
            "direction": self.direction,
            "periodic": self.periodic,
            "cluster": self.cluster,
        }


@dataclass(frozen=True)
class HalftoneOptimizationResult:
    width: int
    height: int
    codes: bytes
    palette: Palette
    simulated_preview_rgb: bytes
    report: Dict[str, Any]

    def preview_png(self) -> bytes:
        return encode_rgb_png(self.width, self.height, self.simulated_preview_rgb)

    def discrete_preview_rgb(self) -> bytes:
        colours = {entry.code: entry.preview_rgb for entry in self.palette.entries}
        return b"".join(bytes(colours[code]) for code in self.codes)

    def discrete_preview_png(self) -> bytes:
        return encode_rgb_png(self.width, self.height, self.discrete_preview_rgb())


# Forward, non-wrapping pairs.  The first four are the four principal
# orientations; later offsets measure horizontal/vertical periodicity.
_STRUCTURE_OFFSETS: Tuple[Tuple[str, int, int, int], ...] = (
    ("h", 1, 1, 0),
    ("v", 1, 0, 1),
    ("d45", 1, 1, 1),
    ("d135", 1, 1, -1),
    ("h", 2, 2, 0),
    ("v", 2, 0, 2),
    ("h", 4, 4, 0),
    ("v", 4, 0, 4),
    ("h", 8, 8, 0),
    ("v", 8, 0, 8),
)


@dataclass
class _StructureStats:
    colour_counts: list[int]
    equal_counts: list[int]
    pair_totals: Tuple[int, ...]


def _build_structure_stats(codes: Sequence[int], width: int, height: int) -> _StructureStats:
    code_index = {code: index for index, code in enumerate(ALLOWED_CODES)}
    colour_counts = [0] * len(ALLOWED_CODES)
    for code in codes:
        colour_counts[code_index[code]] += 1
    equal_counts = [0] * len(_STRUCTURE_OFFSETS)
    pair_totals = []
    for offset_index, (_, _, dx, dy) in enumerate(_STRUCTURE_OFFSETS):
        total = 0
        for y_value in range(height):
            other_y = y_value + dy
            if not 0 <= other_y < height:
                continue
            row = y_value * width
            other_row = other_y * width
            for x_value in range(width):
                other_x = x_value + dx
                if not 0 <= other_x < width:
                    continue
                total += 1
                if codes[row + x_value] == codes[other_row + other_x]:
                    equal_counts[offset_index] += 1
        pair_totals.append(total)
    return _StructureStats(colour_counts, equal_counts, tuple(pair_totals))


def _structure_components(stats: _StructureStats, pixel_count: int) -> Tuple[float, float, float]:
    baseline = math.fsum((count / pixel_count) ** 2 for count in stats.colour_counts)
    correlations = [
        (equal / total) if total else None
        for equal, total in zip(stats.equal_counts, stats.pair_totals)
    ]
    directional_values = [value for value in correlations[:4] if value is not None]
    if directional_values:
        mean_direction = math.fsum(directional_values) / len(directional_values)
        direction = math.fsum(
            (value - mean_direction) ** 2 for value in directional_values
        ) / len(directional_values)
        cluster = max(0.0, mean_direction - baseline) ** 2
    else:
        direction = cluster = 0.0
    periodic_values = [value for value in correlations[4:] if value is not None]
    periodic = (
        math.fsum((value - baseline) ** 2 for value in periodic_values)
        / len(periodic_values)
        if periodic_values
        else 0.0
    )
    return direction, periodic, cluster


def evaluate_structure_penalties(
    codes: bytes | bytearray | memoryview, width: int, height: int
) -> Dict[str, float]:
    """Evaluate direction, periodicity and cluster terms for a six-code grid."""

    if type(width) is not int or width <= 0 or type(height) is not int or height <= 0:
        raise HalftoneOptimizationError("structure dimensions must be positive integers")
    raw_codes = validate_six_codes(codes, width * height)
    direction, periodic, cluster = _structure_components(
        _build_structure_stats(raw_codes, width, height), width * height
    )
    return {
        "direction": direction,
        "periodic": periodic,
        "cluster": cluster,
    }


def _structure_after_changes(
    stats: _StructureStats,
    codes: Sequence[int],
    changes: Mapping[int, int],
    width: int,
    height: int,
) -> _StructureStats:
    colour_counts = stats.colour_counts[:]
    code_index = {code: index for index, code in enumerate(ALLOWED_CODES)}
    for pixel, new_code in changes.items():
        old_code = codes[pixel]
        if old_code == new_code:
            continue
        colour_counts[code_index[old_code]] -= 1
        colour_counts[code_index[new_code]] += 1

    affected_pairs: set[Tuple[int, int, int]] = set()
    for pixel in changes:
        y_value, x_value = divmod(pixel, width)
        for offset_index, (_, _, dx, dy) in enumerate(_STRUCTURE_OFFSETS):
            other_x = x_value + dx
            other_y = y_value + dy
            if 0 <= other_x < width and 0 <= other_y < height:
                affected_pairs.add((offset_index, pixel, other_y * width + other_x))
            first_x = x_value - dx
            first_y = y_value - dy
            if 0 <= first_x < width and 0 <= first_y < height:
                affected_pairs.add((offset_index, first_y * width + first_x, pixel))
    equal_counts = stats.equal_counts[:]
    for offset_index, first, second in affected_pairs:
        old_equal = codes[first] == codes[second]
        new_first = changes.get(first, codes[first])
        new_second = changes.get(second, codes[second])
        new_equal = new_first == new_second
        equal_counts[offset_index] += int(new_equal) - int(old_equal)
    return _StructureStats(colour_counts, equal_counts, stats.pair_totals)


def _squared_error_sum(first: Sequence[float], second: Sequence[float]) -> float:
    return math.fsum((float(one) - float(two)) ** 2 for one, two in zip(first, second))


def _edge_error_sum(
    predicted: Sequence[float], target: Sequence[float], width: int, height: int
) -> float:
    total = 0.0
    for y_value in range(height):
        for x_value in range(width):
            first = y_value * width + x_value
            if x_value + 1 < width:
                total += _edge_pair_error(predicted, target, first, first + 1)
            if y_value + 1 < height:
                total += _edge_pair_error(predicted, target, first, first + width)
    return total


def _edge_pair_error(
    predicted: Sequence[float], target: Sequence[float], first: int, second: int
) -> float:
    first_offset = first * 3
    second_offset = second * 3
    return math.fsum(
        (
            (float(predicted[first_offset + channel]) - float(predicted[second_offset + channel]))
            - (float(target[first_offset + channel]) - float(target[second_offset + channel]))
        )
        ** 2
        for channel in range(3)
    )


def _edge_pair_count(width: int, height: int) -> int:
    return max(1, (width - 1) * height + (height - 1) * width)


@dataclass
class _State:
    width: int
    height: int
    codes: bytearray
    palette: Palette
    model: OverlapObservationModel
    target: Sequence[float]
    observed: Sequence[float]
    target_scales: list[Sequence[float]]
    predicted_scales: list[Sequence[float]]
    colour_error_sums: list[float]
    edge_error_sum: float
    structure: _StructureStats

    def loss(self, options: DBSOptions) -> LossBreakdown:
        normalizer = self.width * self.height * 3
        scale_values = [value / normalizer for value in self.colour_error_sums]
        edge = self.edge_error_sum / (_edge_pair_count(self.width, self.height) * 3)
        direction, periodic, cluster = _structure_components(
            self.structure, self.width * self.height
        )
        total = (
            math.fsum(
                weight * value
                for weight, value in zip(options.multiscale_weights, scale_values)
            )
            + options.edge_weight * edge
            + options.direction_weight * direction
            + options.periodic_weight * periodic
            + options.cluster_weight * cluster
        )
        return LossBreakdown(
            total,
            scale_values[0],
            scale_values[1],
            scale_values[2],
            edge,
            direction,
            periodic,
            cluster,
        )


def _prepare_state(
    image: RasterImage,
    codes: bytes,
    palette: Palette,
    model: OverlapObservationModel,
) -> _State:
    target = raster_linear_rgb(image)
    observed = model.render_linear_rgb(codes, image.width, image.height, palette=palette)
    target_scales = [
        box_blur_rgb(target, image.width, image.height, size)
        for size in MULTISCALE_SIZES
    ]
    predicted_scales = [
        box_blur_rgb(observed, image.width, image.height, size)
        for size in MULTISCALE_SIZES
    ]
    colour_error_sums = [
        _squared_error_sum(predicted, expected)
        for predicted, expected in zip(predicted_scales, target_scales)
    ]
    edge_error = _edge_error_sum(
        predicted_scales[0], target_scales[0], image.width, image.height
    )
    structure = _build_structure_stats(codes, image.width, image.height)
    return _State(
        image.width,
        image.height,
        bytearray(codes),
        palette,
        model,
        target,
        observed,
        target_scales,
        predicted_scales,
        colour_error_sums,
        edge_error,
        structure,
    )


@dataclass
class _MoveEvaluation:
    changes: Dict[int, int]
    loss: LossBreakdown
    observation_delta: Dict[int, list[float]]
    scale_deltas: list[Dict[int, list[float]]]
    colour_error_sums: list[float]
    edge_error_sum: float
    structure: _StructureStats


def _add_rgb_delta(
    destination: Dict[int, list[float]], index: int, colour: Sequence[float], weight: float
) -> None:
    current = destination.get(index)
    if current is None:
        destination[index] = [
            float(colour[0]) * weight,
            float(colour[1]) * weight,
            float(colour[2]) * weight,
        ]
    else:
        current[0] += float(colour[0]) * weight
        current[1] += float(colour[1]) * weight
        current[2] += float(colour[2]) * weight


def _observation_delta(state: _State, changes: Mapping[int, int]) -> Dict[int, list[float]]:
    colours = {entry.code: entry.diffusion_rgb for entry in state.palette.entries}
    output: Dict[int, list[float]] = {}
    for pixel, new_code in changes.items():
        old_code = state.codes[pixel]
        if old_code == new_code:
            continue
        y_value, x_value = divmod(pixel, state.width)
        for affected, weight in state.model.source_response(
            old_code, x_value, y_value, state.width, state.height
        ).items():
            _add_rgb_delta(output, affected, colours[old_code], -weight)
        for affected, weight in state.model.source_response(
            new_code, x_value, y_value, state.width, state.height
        ).items():
            _add_rgb_delta(output, affected, colours[new_code], weight)
    return output


def _scale_delta(
    observation_delta: Mapping[int, Sequence[float]],
    width: int,
    height: int,
    size: int,
) -> Dict[int, list[float]]:
    output: Dict[int, list[float]] = {}
    for pixel, delta in observation_delta.items():
        y_value, x_value = divmod(pixel, width)
        for affected, weight in box_source_response(
            x_value, y_value, width, height, size
        ).items():
            _add_rgb_delta(output, affected, delta, weight)
    return output


def _changed_error_sum(
    current_sum: float,
    predicted: Sequence[float],
    target: Sequence[float],
    changes: Mapping[int, Sequence[float]],
) -> float:
    delta_total = 0.0
    for pixel, delta in changes.items():
        offset = pixel * 3
        for channel in range(3):
            old_difference = float(predicted[offset + channel]) - float(target[offset + channel])
            new_difference = old_difference + float(delta[channel])
            delta_total += new_difference * new_difference - old_difference * old_difference
    return current_sum + delta_total


def _edge_after_scale_delta(
    current_sum: float,
    predicted: Sequence[float],
    target: Sequence[float],
    changes: Mapping[int, Sequence[float]],
    width: int,
    height: int,
) -> float:
    pairs: set[Tuple[int, int]] = set()
    for pixel in changes:
        y_value, x_value = divmod(pixel, width)
        if x_value:
            pairs.add((pixel - 1, pixel))
        if x_value + 1 < width:
            pairs.add((pixel, pixel + 1))
        if y_value:
            pairs.add((pixel - width, pixel))
        if y_value + 1 < height:
            pairs.add((pixel, pixel + width))
    delta_total = 0.0
    for first, second in pairs:
        old_error = _edge_pair_error(predicted, target, first, second)
        new_error = 0.0
        first_offset = first * 3
        second_offset = second * 3
        first_delta = changes.get(first, (0.0, 0.0, 0.0))
        second_delta = changes.get(second, (0.0, 0.0, 0.0))
        for channel in range(3):
            predicted_gradient = (
                float(predicted[first_offset + channel])
                + float(first_delta[channel])
                - float(predicted[second_offset + channel])
                - float(second_delta[channel])
            )
            target_gradient = float(target[first_offset + channel]) - float(
                target[second_offset + channel]
            )
            new_error += (predicted_gradient - target_gradient) ** 2
        delta_total += new_error - old_error
    return current_sum + delta_total


def _loss_from_values(
    state: _State,
    options: DBSOptions,
    colour_error_sums: Sequence[float],
    edge_error_sum: float,
    structure: _StructureStats,
) -> LossBreakdown:
    normalizer = state.width * state.height * 3
    scales = [value / normalizer for value in colour_error_sums]
    edge = edge_error_sum / (_edge_pair_count(state.width, state.height) * 3)
    direction, periodic, cluster = _structure_components(
        structure, state.width * state.height
    )
    total = (
        math.fsum(
            weight * value for weight, value in zip(options.multiscale_weights, scales)
        )
        + options.edge_weight * edge
        + options.direction_weight * direction
        + options.periodic_weight * periodic
        + options.cluster_weight * cluster
    )
    return LossBreakdown(
        total,
        scales[0],
        scales[1],
        scales[2],
        edge,
        direction,
        periodic,
        cluster,
    )


def _evaluate_changes(
    state: _State, changes: Mapping[int, int], options: DBSOptions
) -> _MoveEvaluation:
    normalized = {
        pixel: code
        for pixel, code in changes.items()
        if state.codes[pixel] != code
    }
    observation_delta = _observation_delta(state, normalized)
    scale_deltas = [
        _scale_delta(observation_delta, state.width, state.height, size)
        for size in MULTISCALE_SIZES
    ]
    colour_sums = [
        _changed_error_sum(old_sum, predicted, target, delta)
        for old_sum, predicted, target, delta in zip(
            state.colour_error_sums,
            state.predicted_scales,
            state.target_scales,
            scale_deltas,
        )
    ]
    edge_sum = _edge_after_scale_delta(
        state.edge_error_sum,
        state.predicted_scales[0],
        state.target_scales[0],
        scale_deltas[0],
        state.width,
        state.height,
    )
    structure = _structure_after_changes(
        state.structure, state.codes, normalized, state.width, state.height
    )
    loss = _loss_from_values(state, options, colour_sums, edge_sum, structure)
    return _MoveEvaluation(
        dict(normalized),
        loss,
        observation_delta,
        scale_deltas,
        colour_sums,
        edge_sum,
        structure,
    )


def _apply_move(state: _State, move: _MoveEvaluation) -> None:
    for pixel, code in move.changes.items():
        state.codes[pixel] = code
    for pixel, delta in move.observation_delta.items():
        offset = pixel * 3
        for channel in range(3):
            state.observed[offset + channel] += delta[channel]  # type: ignore[index]
    for predicted, deltas in zip(state.predicted_scales, move.scale_deltas):
        for pixel, delta in deltas.items():
            offset = pixel * 3
            for channel in range(3):
                predicted[offset + channel] += delta[channel]  # type: ignore[index]
    state.colour_error_sums = move.colour_error_sums
    state.edge_error_sum = move.edge_error_sum
    state.structure = move.structure


def evaluate_halftone_loss(
    image: RasterImage,
    codes: bytes | bytearray | memoryview,
    *,
    palette: Palette | None = None,
    model: OverlapObservationModel | None = None,
    options: DBSOptions | None = None,
) -> LossBreakdown:
    """Evaluate the same complete objective used by DBS without changing codes."""

    if type(image) is not RasterImage:
        raise HalftoneOptimizationError("image must be a RasterImage instance")
    raw_codes = validate_six_codes(codes, image.width * image.height)
    selected_palette = reference_palette() if palette is None else palette
    if type(selected_palette) is not Palette:
        raise HalftoneOptimizationError("palette must be a Palette instance or None")
    selected_model = (
        OverlapObservationModel.gaussian_simulation() if model is None else model
    )
    if type(selected_model) is not OverlapObservationModel:
        raise HalftoneOptimizationError(
            "model must be an OverlapObservationModel instance or None"
        )
    selected_options = DBSOptions() if options is None else options
    if type(selected_options) is not DBSOptions:
        raise HalftoneOptimizationError("options must be a DBSOptions instance or None")
    return _prepare_state(
        image, raw_codes, selected_palette, selected_model
    ).loss(selected_options)


def _valid_neighbours(pixel: int, width: int, height: int, radius: int) -> list[int]:
    y_value, x_value = divmod(pixel, width)
    neighbours = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx == 0 and dy == 0:
                continue
            other_x = x_value + dx
            other_y = y_value + dy
            if 0 <= other_x < width and 0 <= other_y < height:
                neighbours.append(other_y * width + other_x)
    return neighbours


def _simulation_preview(observed: Sequence[float]) -> bytes:
    output = bytearray(len(observed))
    for index, value in enumerate(observed):
        encoded = linear_channel_to_srgb(min(1.0, max(0.0, float(value))))
        output[index] = min(255, max(0, int(round(encoded * 255.0))))
    return bytes(output)


class _ProposalCoverage:
    """Model-independent evidence for the deterministic proposal schedule."""

    _NO_PARTNER = 0xFFFFFFFFFFFFFFFF

    def __init__(self, width: int, height: int, unlocked_pixels: int) -> None:
        self.width = width
        self.height = height
        self.unlocked_pixels = unlocked_pixels
        self.primary_seen = bytearray(width * height)
        self.touched_seen = bytearray(width * height)
        self.unique_primary_pixels = 0
        self.unique_touched_pixels = 0
        self.left_proposals = 0
        self.right_proposals = 0
        self.tile_columns = min(16, width)
        self.tile_rows = min(10, height)
        self.tile_proposals = [0] * (self.tile_columns * self.tile_rows)
        self.trace = hashlib.sha256()
        self.samples: list[Dict[str, Any]] = []

    def _mark(self, seen: bytearray, pixel: int) -> bool:
        if seen[pixel]:
            return False
        seen[pixel] = 1
        return True

    def record(
        self,
        ordinal: int,
        operation: str,
        primary: int,
        partner: int | None,
    ) -> None:
        if operation not in {"single-recolour", "pair-swap"}:
            raise AssertionError("unknown DBS proposal operation")
        if not 0 <= primary < self.width * self.height:
            raise AssertionError("DBS primary proposal pixel is outside the raster")
        if partner is not None and not 0 <= partner < self.width * self.height:
            raise AssertionError("DBS partner proposal pixel is outside the raster")
        if operation == "pair-swap" and partner is None:
            raise AssertionError("DBS swap proposal has no partner")
        if operation == "single-recolour" and partner is not None:
            raise AssertionError("DBS recolour proposal unexpectedly has a partner")

        if self._mark(self.primary_seen, primary):
            self.unique_primary_pixels += 1
        if self._mark(self.touched_seen, primary):
            self.unique_touched_pixels += 1
        if partner is not None and self._mark(self.touched_seen, partner):
            self.unique_touched_pixels += 1

        _primary_y, primary_x = divmod(primary, self.width)
        if primary_x < self.width // 2:
            self.left_proposals += 1
        else:
            self.right_proposals += 1
        tile_column = primary_x * self.tile_columns // self.width
        tile_row = _primary_y * self.tile_rows // self.height
        self.tile_proposals[tile_row * self.tile_columns + tile_column] += 1

        operation_byte = 1 if operation == "pair-swap" else 0
        encoded_partner = self._NO_PARTNER if partner is None else partner
        self.trace.update(
            struct.pack(">QBQQ", ordinal, operation_byte, primary, encoded_partner)
        )
        if len(self.samples) < 32:
            pixels = [primary] if partner is None else [primary, partner]
            self.samples.append(
                {
                    "proposal": ordinal,
                    "operation": operation,
                    "pixels": pixels,
                }
            )

    def to_mapping(self, proposal_count: int) -> Dict[str, Any]:
        if proposal_count != self.left_proposals + self.right_proposals:
            raise AssertionError("DBS proposal side counts do not cover the trace")
        if proposal_count != sum(self.tile_proposals):
            raise AssertionError("DBS proposal tile counts do not cover the trace")
        nonempty_tiles = sum(value > 0 for value in self.tile_proposals)
        panel_grid = self.width == 1024 and self.height == 600
        return {
            "contract": DBS_COVERAGE_CONTRACT,
            "unlocked_pixels": self.unlocked_pixels,
            "unique_primary_pixels": self.unique_primary_pixels,
            "unique_touched_pixels": self.unique_touched_pixels,
            "primary_coverage_ratio": (
                self.unique_primary_pixels / self.unlocked_pixels
                if self.unlocked_pixels
                else 0.0
            ),
            "proposal_trace_sha256": self.trace.hexdigest(),
            "proposal_trace_encoding": DBS_PROPOSAL_TRACE_ENCODING,
            "proposal_trace_samples": self.samples,
            "horizontal_split": {
                "split_x": self.width // 2,
                "left_proposals": self.left_proposals,
                "right_proposals": self.right_proposals,
            },
            "tile_grid": {
                "contract": DBS_TILE_GRID_CONTRACT,
                "columns": self.tile_columns,
                "rows": self.tile_rows,
                "panel_1024x600_exact_64x60": panel_grid,
                "exact_tile_width": 64 if panel_grid else None,
                "exact_tile_height": 60 if panel_grid else None,
                "proposal_counts": self.tile_proposals,
                "nonempty_tiles": nonempty_tiles,
                "empty_tiles": len(self.tile_proposals) - nonempty_tiles,
                "minimum_proposals": min(self.tile_proposals),
                "maximum_proposals": max(self.tile_proposals),
            },
        }


def optimize_multicolor_dbs(
    image: RasterImage,
    initial_codes: bytes | bytearray | memoryview,
    *,
    palette: Palette | None = None,
    model: OverlapObservationModel | None = None,
    options: DBSOptions | None = None,
    cancel_check: Callable[[], bool] | None = None,
    code_constraints: bytes | bytearray | memoryview | None = None,
) -> HalftoneOptimizationResult:
    """Run deterministic bounded single-recolour and nearby-pair-swap DBS.

    The expensive preprocessing is a fixed number of linear image passes.
    Search work is capped by ``max_evaluations`` and can be stopped by either
    the stagnation/accepted/time budgets or a cooperative ``cancel_check``.
    No device or network API is imported or called.
    """

    if type(image) is not RasterImage:
        raise HalftoneOptimizationError("image must be a RasterImage instance")
    codes = validate_six_codes(initial_codes, image.width * image.height)
    constraints = validate_code_constraints(code_constraints, len(codes))
    for index, fixed_code in enumerate(constraints):
        if fixed_code != UNCONSTRAINED_CODE and codes[index] != fixed_code:
            raise HalftoneOptimizationError(
                f"initial code at protected pixel {index} differs from its constraint"
            )
    selected_palette = reference_palette() if palette is None else palette
    if type(selected_palette) is not Palette:
        raise HalftoneOptimizationError("palette must be a Palette instance or None")
    selected_model = (
        OverlapObservationModel.gaussian_simulation() if model is None else model
    )
    if type(selected_model) is not OverlapObservationModel:
        raise HalftoneOptimizationError(
            "model must be an OverlapObservationModel instance or None"
        )
    selected_options = DBSOptions() if options is None else options
    if type(selected_options) is not DBSOptions:
        raise HalftoneOptimizationError("options must be a DBSOptions instance or None")
    if cancel_check is not None and not callable(cancel_check):
        raise HalftoneOptimizationError("cancel_check must be callable or None")

    state = _prepare_state(image, codes, selected_palette, selected_model)
    initial_loss = state.loss(selected_options)
    current_loss = initial_loss
    rng = _SplitMix64(selected_options.seed)
    evaluation_count = 0
    proposal_count = 0
    accepted_recolours = 0
    accepted_swaps = 0
    rejected_evaluations = 0
    last_improvement_evaluation = 0
    stop_reason = "evaluation_budget"
    accepted_digest = hashlib.sha256()
    move_samples: list[Dict[str, Any]] = []
    start = time.monotonic()
    cancelled = bool(cancel_check is not None and cancel_check())
    unlocked_pixels = tuple(
        index
        for index, value in enumerate(constraints)
        if value == UNCONSTRAINED_CODE
    )
    proposal_coverage = _ProposalCoverage(
        image.width, image.height, len(unlocked_pixels)
    )
    if not unlocked_pixels:
        stop_reason = "all_pixels_protected"

    while not cancelled and unlocked_pixels:
        if evaluation_count >= selected_options.max_evaluations:
            stop_reason = "evaluation_budget"
            break
        if accepted_recolours + accepted_swaps >= selected_options.max_accepted_moves:
            stop_reason = "accepted_move_budget"
            break
        if (
            evaluation_count - last_improvement_evaluation
            >= selected_options.stagnation_evaluations
        ):
            stop_reason = "stagnation"
            break
        if (
            selected_options.time_limit_seconds is not None
            and time.monotonic() - start >= selected_options.time_limit_seconds
        ):
            stop_reason = "time_budget"
            break
        if (
            cancel_check is not None
            and evaluation_count % selected_options.cancel_check_interval == 0
            and cancel_check()
        ):
            stop_reason = "cancelled"
            cancelled = True
            break

        proposal_count += 1
        pixel = unlocked_pixels[rng.below(len(unlocked_pixels))]
        choose_swap = (
            rng.next_u64() / 18446744073709551616.0
            < selected_options.swap_probability
        )
        neighbours = (
            [
                candidate
                for candidate in _valid_neighbours(
                    pixel, image.width, image.height, selected_options.swap_radius
                )
                if constraints[candidate] == UNCONSTRAINED_CODE
            ]
            if choose_swap
            else []
        )
        best_move: _MoveEvaluation | None = None
        operation = "single-recolour"
        move_indices: Tuple[int, ...] = (pixel,)

        if choose_swap and neighbours:
            operation = "pair-swap"
            other = neighbours[rng.below(len(neighbours))]
            move_indices = (pixel, other)
            proposal_coverage.record(proposal_count, operation, pixel, other)
            evaluation_count += 1
            if state.codes[pixel] != state.codes[other]:
                candidate = _evaluate_changes(
                    state,
                    {pixel: state.codes[other], other: state.codes[pixel]},
                    selected_options,
                )
                if candidate.loss.total < current_loss.total - selected_options.min_improvement:
                    best_move = candidate
                else:
                    rejected_evaluations += 1
            else:
                rejected_evaluations += 1
        else:
            proposal_coverage.record(proposal_count, operation, pixel, None)
            old_code = state.codes[pixel]
            for candidate_code in ALLOWED_CODES:
                if candidate_code == old_code:
                    continue
                if evaluation_count >= selected_options.max_evaluations:
                    break
                evaluation_count += 1
                candidate = _evaluate_changes(
                    state, {pixel: candidate_code}, selected_options
                )
                if candidate.loss.total < current_loss.total - selected_options.min_improvement:
                    if best_move is None or candidate.loss.total < best_move.loss.total:
                        best_move = candidate
                else:
                    rejected_evaluations += 1
                if (
                    cancel_check is not None
                    and evaluation_count % selected_options.cancel_check_interval == 0
                    and cancel_check()
                ):
                    stop_reason = "cancelled"
                    cancelled = True
                    best_move = None
                    break

        if cancelled:
            break
        if best_move is None:
            continue
        old_codes = tuple(state.codes[index] for index in move_indices)
        improvement = current_loss.total - best_move.loss.total
        _apply_move(state, best_move)
        current_loss = best_move.loss
        last_improvement_evaluation = evaluation_count
        if operation == "pair-swap":
            accepted_swaps += 1
        else:
            accepted_recolours += 1
        new_codes = tuple(state.codes[index] for index in move_indices)
        trace_line = (
            f"{evaluation_count}:{operation}:{','.join(map(str, move_indices))}:"
            f"{','.join(map(str, old_codes))}->{','.join(map(str, new_codes))}:"
            f"{improvement.hex()}\n"
        ).encode("ascii")
        accepted_digest.update(trace_line)
        if len(move_samples) < 32:
            move_samples.append(
                {
                    "evaluation": evaluation_count,
                    "operation": operation,
                    "pixels": list(move_indices),
                    "old_codes": list(old_codes),
                    "new_codes": list(new_codes),
                    "loss_improvement_hex": improvement.hex(),
                }
            )

    if cancelled and stop_reason != "cancelled":
        stop_reason = "cancelled"
    output_codes = bytes(state.codes)
    if set(output_codes).difference(ALLOWED_CODES):
        raise AssertionError("DBS emitted a non-physical code")
    report: Dict[str, Any] = {
        "schema_version": DBS_REPORT_SCHEMA_VERSION,
        "kind": "mf1750-overlap-aware-halftone-optimization-report",
        "algorithm": DBS_ALGORITHM,
        "dimensions": {"width": image.width, "height": image.height},
        "physical_codes": list(ALLOWED_CODES),
        "input": {
            "raster_sha256": hashlib.sha256(image.pixels).hexdigest(),
            "initial_codes_sha256": hashlib.sha256(codes).hexdigest(),
            "initial_frame_sha256": (
                None
                if image.width % 2
                else hashlib.sha256(
                    pack_pixels(codes, image.width, image.height)
                ).hexdigest()
            ),
        },
        "output": {"codes_sha256": hashlib.sha256(output_codes).hexdigest()},
        "palette": {
            "id": selected_palette.palette_id,
            "calibrated": selected_palette.calibrated,
            "canonical_sha256": selected_palette.canonical_sha256,
        },
        "observation_model": selected_model.metadata(),
        "loss_contract": {
            "scales": list(MULTISCALE_SIZES),
            "multiscale_weights": list(selected_options.multiscale_weights),
            "edge_weight": selected_options.edge_weight,
            "direction_weight": selected_options.direction_weight,
            "periodic_weight": selected_options.periodic_weight,
            "cluster_weight": selected_options.cluster_weight,
            "colour_space": "linear sRGB simulation",
            "colour_metric": "mean squared RGB after overlapping convolution",
            "direction_metric": "variance of same-code correlation over H/V/45/135 degrees",
            "periodic_metric": "same-code correlation deviation from area-ratio baseline at lags 2/4/8",
            "cluster_metric": "positive lag-1 same-code correlation excess over area-ratio baseline",
        },
        "search": {
            "seed": selected_options.seed,
            "operations": ["single-pixel recolour", "nearby two-pixel swap"],
            "swap_probability": selected_options.swap_probability,
            "swap_radius": selected_options.swap_radius,
            "min_improvement": selected_options.min_improvement,
            "evaluations": evaluation_count,
            "proposals": proposal_count,
            "accepted_recolours": accepted_recolours,
            "accepted_swaps": accepted_swaps,
            "rejected_evaluations": rejected_evaluations,
            "accepted_move_trace_sha256": accepted_digest.hexdigest(),
            "accepted_move_samples": move_samples,
            "coverage": proposal_coverage.to_mapping(proposal_count),
            "code_constraints": {
                "provided": code_constraints is not None,
                "locked_pixels": len(codes) - len(unlocked_pixels),
                "mask_sha256": hashlib.sha256(constraints).hexdigest(),
                "unconstrained_sentinel": UNCONSTRAINED_CODE,
            },
        },
        "budget": {
            "max_evaluations": selected_options.max_evaluations,
            "max_accepted_moves": selected_options.max_accepted_moves,
            "stagnation_evaluations": selected_options.stagnation_evaluations,
            "time_limit_seconds": selected_options.time_limit_seconds,
            "cancel_check_interval": selected_options.cancel_check_interval,
            "stop_reason": stop_reason,
        },
        "loss": {
            "initial": initial_loss.to_dict(),
            "final": current_loss.to_dict(),
            "improvement": initial_loss.total - current_loss.total,
        },
        "determinism": {
            "deterministic_if_not_time_limited_or_cancelled": True,
            "time_limit_enabled": selected_options.time_limit_seconds is not None,
            "cancelled": stop_reason == "cancelled",
        },
        "qualification": {
            "simulation_only": True,
            "hardware_tested": False,
            "hardware_qualified": False,
            "device_accessed": False,
            "reason": "observation kernels and preview have not been fitted to MF-1750 measurements",
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
    return HalftoneOptimizationResult(
        image.width,
        image.height,
        output_codes,
        selected_palette,
        _simulation_preview(state.observed),
        report,
    )
