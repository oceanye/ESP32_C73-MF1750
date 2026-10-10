"""Deterministic six-primary area-weight solver for mapped target colours.

This is a reusable per-colour interface for later S1 halftoners.  It returns
non-negative weights that sum to one and an exact 2x2 or 4x4 integer recipe.
The solver precomputes the finite recipe space once and keeps a bounded exact
target cache; no stochastic state or device path is involved.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
from typing import Any, Iterator, Sequence, Tuple

from host.color_pipeline import Palette, delta_e_ciede2000
from host.color_pipeline.color import Lab, lab_to_xyz, xyz_to_lab
from host.extended_color import COLOR_NAME_BY_CODE, COLOR_ORDER, render_area_mix_tile

from .mapper import RenderingIntent
from .profile import PRESET_ALIASES, GamutProfile


AREA_WEIGHT_SOLVER_VERSION = "1.0.0"
AREA_WEIGHT_REPORT_SCHEMA_VERSION = 1
AREA_WEIGHT_REPORT_KIND = "mf1750-six-primary-area-weight-solution"
AREA_WEIGHT_ID_SCOPE = (
    "canonical UTF-8 JSON binding solver version, palette/profile identities, "
    "target Lab, objective, exact integer counts and physical colour order"
)


class AreaWeightError(ValueError):
    """Raised when a six-primary area-weight request violates its contract."""


def _finite(
    value: Any, *, label: str, minimum: float = 0.0, maximum: float = math.inf
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AreaWeightError(f"{label} must be numeric and not boolean")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise AreaWeightError(f"{label} is outside its finite range")
    return result


def _target_lab(value: Sequence[float]) -> Lab:
    try:
        items = tuple(value)
    except TypeError as error:
        raise AreaWeightError("target Lab must contain exactly three numbers") from error
    if len(items) != 3:
        raise AreaWeightError("target Lab must contain exactly three numbers")
    lightness = _finite(
        items[0], label="target L*", minimum=-1e-5, maximum=100.00001
    )
    lightness = min(100.0, max(0.0, lightness))
    a_value = _finite(items[1], label="target a*", minimum=-200.0, maximum=200.0)
    b_value = _finite(items[2], label="target b*", minimum=-200.0, maximum=200.0)
    return (lightness, a_value, b_value)


def _intent(value: RenderingIntent | str) -> RenderingIntent:
    if isinstance(value, str):
        value = PRESET_ALIASES.get(value, value)
    try:
        return value if isinstance(value, RenderingIntent) else RenderingIntent(value)
    except (TypeError, ValueError) as error:
        raise AreaWeightError("area-weight intent is invalid") from error


@dataclass(frozen=True)
class AreaWeightOptions:
    tile_side: int = 2
    intent: RenderingIntent | str = RenderingIntent.PERCEPTUAL
    delta_e_weight: float = 1.0
    grain_weight: float = 0.025
    color_count_weight: float = 0.01
    max_colors: int = 6
    cache_entries: int = 4096

    def __post_init__(self) -> None:
        if type(self.tile_side) is not int or self.tile_side not in (2, 4):
            raise AreaWeightError("tile_side must be integer 2 or 4")
        object.__setattr__(self, "intent", _intent(self.intent))
        for label in ("delta_e_weight", "grain_weight", "color_count_weight"):
            object.__setattr__(
                self,
                label,
                _finite(getattr(self, label), label=label, minimum=0.0, maximum=100.0),
            )
        if not any(
            getattr(self, label) > 0.0
            for label in ("delta_e_weight", "grain_weight", "color_count_weight")
        ):
            raise AreaWeightError("area-weight objective cannot have all-zero weights")
        if type(self.max_colors) is not int or not 1 <= self.max_colors <= 6:
            raise AreaWeightError("max_colors must be an integer in [1, 6]")
        if type(self.cache_entries) is not int or not 0 <= self.cache_entries <= 65536:
            raise AreaWeightError("cache_entries must be an integer in [0, 65536]")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "tile_side": self.tile_side,
            "intent": self.intent.value,
            "delta_e_weight": self.delta_e_weight,
            "grain_weight": self.grain_weight,
            "color_count_weight": self.color_count_weight,
            "max_colors": self.max_colors,
            "cache_entries": self.cache_entries,
        }


@lru_cache(maxsize=2)
def _compositions(total: int) -> Tuple[Tuple[int, ...], ...]:
    def generate(remaining: int, parts: int, prefix: Tuple[int, ...]) -> Iterator[Tuple[int, ...]]:
        if parts == 1:
            yield prefix + (remaining,)
            return
        for value in range(remaining + 1):
            yield from generate(remaining - value, parts - 1, prefix + (value,))

    return tuple(generate(total, len(COLOR_ORDER), ()))


def _hue_difference(first: Lab, second: Lab) -> float:
    first_chroma = math.hypot(first[1], first[2])
    second_chroma = math.hypot(second[1], second[2])
    if first_chroma <= 1e-12 or second_chroma <= 1e-12:
        return 0.0
    first_hue = math.degrees(math.atan2(first[2], first[1])) % 360.0
    second_hue = math.degrees(math.atan2(second[2], second[1])) % 360.0
    difference = abs(first_hue - second_hue)
    return min(difference, 360.0 - difference)


@dataclass(frozen=True)
class _Candidate:
    counts: Tuple[int, ...]
    weights: Tuple[float, ...]
    predicted_lab: Lab
    active_colors: int
    grain_penalty: float


@dataclass(frozen=True)
class AreaWeightSolution:
    target_lab: Lab
    predicted_lab: Lab
    counts: Tuple[int, ...]
    weights: Tuple[float, ...]
    tile_side: int
    intent: RenderingIntent
    objective_score: float
    delta_e00: float
    lightness_error: float
    chroma_error: float
    hue_error_degrees: float
    grain_penalty: float
    color_count_penalty: float
    palette: Palette
    profile: GamutProfile
    options: AreaWeightOptions

    @property
    def tile(self) -> Tuple[int, ...]:
        return render_area_mix_tile(self.tile_side, self.counts)

    @property
    def weights_by_code(self) -> Tuple[Tuple[int, float], ...]:
        return tuple(zip(COLOR_ORDER, self.weights))

    @property
    def solution_id(self) -> str:
        payload = self._identity_payload()
        digest = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        return f"MF1750-G1-MIX-{digest[:16].upper()}"

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "solver_version": AREA_WEIGHT_SOLVER_VERSION,
            "palette_canonical_sha256": self.palette.canonical_sha256,
            "profile_canonical_sha256": self.profile.canonical_sha256,
            "target_lab": list(self.target_lab),
            "options": self.options.to_mapping(),
            "color_order": list(COLOR_ORDER),
            "counts": list(self.counts),
        }

    def to_report(self) -> dict[str, Any]:
        pixels = self.tile_side * self.tile_side
        report = {
            "schema_version": AREA_WEIGHT_REPORT_SCHEMA_VERSION,
            "kind": AREA_WEIGHT_REPORT_KIND,
            "solution_id": self.solution_id,
            "solution_id_scope": AREA_WEIGHT_ID_SCOPE,
            "solver_version": AREA_WEIGHT_SOLVER_VERSION,
            "target_lab": list(self.target_lab),
            "predicted_lab": list(self.predicted_lab),
            "palette": {
                "id": self.palette.palette_id,
                "canonical_sha256": self.palette.canonical_sha256,
                "calibrated": self.palette.calibrated,
            },
            "profile": {
                "id": self.profile.profile_id,
                "canonical_sha256": self.profile.canonical_sha256,
                "characterization_level": self.profile.characterization_level,
            },
            "objective": {
                "intent": self.intent.value,
                "total_score": self.objective_score,
                "delta_e00": self.delta_e00,
                "lightness_error": self.lightness_error,
                "chroma_error": self.chroma_error,
                "hue_error_degrees": self.hue_error_degrees,
                "grain_penalty": self.grain_penalty,
                "color_count_penalty": self.color_count_penalty,
                "effective_weights": {
                    "delta_e": self.options.delta_e_weight,
                    "lightness": self.profile.preset(self.intent.value).lightness_weight,
                    "chroma": self.profile.preset(self.intent.value).chroma_weight,
                    "hue": self.profile.preset(self.intent.value).hue_weight,
                    "grain": self.options.grain_weight,
                    "color_count": self.options.color_count_weight,
                },
            },
            "recipe": {
                "tile_side": self.tile_side,
                "tile_pixels": pixels,
                "counts": [
                    {
                        "code": code,
                        "name": COLOR_NAME_BY_CODE[code],
                        "pixels": count,
                        "weight": weight,
                    }
                    for code, count, weight in zip(COLOR_ORDER, self.counts, self.weights)
                ],
                "tile_codes": [
                    list(self.tile[row * self.tile_side : (row + 1) * self.tile_side])
                    for row in range(self.tile_side)
                ],
                "tile_sha256": hashlib.sha256(bytes(self.tile)).hexdigest(),
            },
            "qualification": {
                "simulation": (not self.palette.calibrated or self.profile.is_simulation),
                "hardware_formal_qualified": False,
                "formal_upload_authorized": False,
                "prediction_is_measurement": False,
            },
            "hardware_tested": False,
            "device_io_performed": False,
        }
        return report


class AreaWeightSolver:
    """Precomputed recipe solver suitable for repeated S1 pixel/cache calls."""

    def __init__(
        self,
        palette: Palette,
        profile: GamutProfile,
        *,
        options: AreaWeightOptions | None = None,
        allow_unqualified_simulation: bool = False,
    ) -> None:
        if not isinstance(palette, Palette):
            raise AreaWeightError("palette must be a host.color_pipeline.Palette")
        if not isinstance(profile, GamutProfile):
            raise AreaWeightError("profile must be a GamutProfile")
        if (
            profile.palette_id != palette.palette_id
            or profile.palette_canonical_sha256 != palette.canonical_sha256
        ):
            raise AreaWeightError("profile does not bind the supplied palette")
        if type(allow_unqualified_simulation) is not bool:
            raise AreaWeightError("allow_unqualified_simulation must be boolean")
        if (not palette.calibrated or profile.is_simulation) and not allow_unqualified_simulation:
            raise AreaWeightError(
                "uncalibrated/unqualified area mixing requires explicit simulation opt-in"
            )
        selected = AreaWeightOptions() if options is None else options
        if not isinstance(selected, AreaWeightOptions):
            raise AreaWeightError("options must be AreaWeightOptions or None")
        self.palette = palette
        self.profile = profile
        self.options = selected
        self._cache: OrderedDict[Lab, AreaWeightSolution] = OrderedDict()
        xyz_values = tuple(lab_to_xyz(palette.entry(code).lab) for code in COLOR_ORDER)
        pixels = selected.tile_side * selected.tile_side
        candidates: list[_Candidate] = []
        for counts in _compositions(pixels):
            active = sum(count > 0 for count in counts)
            if active > selected.max_colors:
                continue
            weights = tuple(count / pixels for count in counts)
            xyz = tuple(
                sum(weight * primary[channel] for weight, primary in zip(weights, xyz_values))
                for channel in range(3)
            )
            predicted = xyz_to_lab(xyz)
            grain = 1.0 - sum(weight * weight for weight in weights)
            candidates.append(_Candidate(counts, weights, predicted, active, grain))
        if not candidates:
            raise AreaWeightError("area-weight objective has no legal candidate recipes")
        self._candidates = tuple(candidates)

    @property
    def recipe_space_size(self) -> int:
        return len(self._candidates)

    def solve(self, target_lab: Sequence[float]) -> AreaWeightSolution:
        target = _target_lab(target_lab)
        cached = self._cache.get(target) if self.options.cache_entries else None
        if cached is not None:
            self._cache.move_to_end(target)
            return cached
        preset = self.profile.preset(self.options.intent.value)
        target_chroma = math.hypot(target[1], target[2])
        ranked = []
        for candidate in self._candidates:
            predicted = candidate.predicted_lab
            delta_e = delta_e_ciede2000(target, predicted)
            lightness = abs(target[0] - predicted[0])
            chroma = abs(target_chroma - math.hypot(predicted[1], predicted[2]))
            hue = _hue_difference(target, predicted)
            color_count_penalty = max(0, candidate.active_colors - 1) / 5.0
            score = (
                self.options.delta_e_weight * delta_e
                + preset.lightness_weight * lightness
                + preset.chroma_weight * chroma
                + preset.hue_weight * (hue / 180.0) * 10.0
                + self.options.grain_weight * candidate.grain_penalty
                + self.options.color_count_weight * color_count_penalty
            )
            ranked.append(
                (
                    score,
                    delta_e,
                    lightness,
                    chroma,
                    hue,
                    candidate.counts,
                    candidate,
                    color_count_penalty,
                )
            )
        best = min(ranked, key=lambda item: item[:6])
        candidate = best[6]
        solution = AreaWeightSolution(
            target_lab=target,
            predicted_lab=candidate.predicted_lab,
            counts=candidate.counts,
            weights=candidate.weights,
            tile_side=self.options.tile_side,
            intent=self.options.intent,
            objective_score=best[0],
            delta_e00=best[1],
            lightness_error=best[2],
            chroma_error=best[3],
            hue_error_degrees=best[4],
            grain_penalty=candidate.grain_penalty,
            color_count_penalty=best[7],
            palette=self.palette,
            profile=self.profile,
            options=self.options,
        )
        if self.options.cache_entries:
            self._cache[target] = solution
            if len(self._cache) > self.options.cache_entries:
                self._cache.popitem(last=False)
        return solution


def solve_area_weights(
    target_lab: Sequence[float],
    *,
    palette: Palette,
    profile: GamutProfile,
    options: AreaWeightOptions | None = None,
    allow_unqualified_simulation: bool = False,
) -> AreaWeightSolution:
    """Convenience one-shot wrapper; reuse ``AreaWeightSolver`` for many pixels."""

    return AreaWeightSolver(
        palette,
        profile,
        options=options,
        allow_unqualified_simulation=allow_unqualified_simulation,
    ).solve(target_lab)


__all__ = [
    "AREA_WEIGHT_ID_SCOPE",
    "AREA_WEIGHT_REPORT_KIND",
    "AREA_WEIGHT_REPORT_SCHEMA_VERSION",
    "AREA_WEIGHT_SOLVER_VERSION",
    "AreaWeightError",
    "AreaWeightOptions",
    "AreaWeightSolution",
    "AreaWeightSolver",
    "solve_area_weights",
]
