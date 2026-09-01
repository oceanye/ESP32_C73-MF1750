"""Fail-closed coarse screening for single-pixel lightness ladders.

This module performs no camera capture and no hardware I/O.  It consumes
already-derived Lab measurements and asks a deliberately narrow question:
does one controller, one LUT profile, and one final transport code contain
position-repeatable recipes that preserve hue while separating L*?

The result is screening evidence only.  It never qualifies a physical colour
or authorizes a refresh, and measurements from CS1 and CS2 are never pooled.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from statistics import median
from typing import Any, Sequence

from .common import attach_integrity, finite_triple, require_sha256, require_text
from .multi_lut_hold_schedule import Controller


class LightnessScreenError(ValueError):
    """Raised when a lightness screening input is incomplete or ambiguous."""


class MeasurementPhase(str, Enum):
    TARGET = "target"
    TARGET_REPEAT = "target-repeat"


@dataclass(frozen=True)
class LightnessMeasurement:
    """One inset patch measurement from a single controller and recipe cell."""

    controller: Controller
    lut_profile_id: str
    target_code: int
    recipe_id: str
    replica_id: str
    phase: MeasurementPhase
    measured_lab: tuple[float, float, float]
    single_pixel_pure: bool
    boundary_clean: bool
    measurement_artifact_sha256: str

    def __post_init__(self) -> None:
        try:
            controller = (
                self.controller
                if isinstance(self.controller, Controller)
                else Controller(self.controller)
            )
            phase = (
                self.phase
                if isinstance(self.phase, MeasurementPhase)
                else MeasurementPhase(self.phase)
            )
        except ValueError as error:
            raise LightnessScreenError(
                "controller or measurement phase differs"
            ) from error
        object.__setattr__(self, "controller", controller)
        object.__setattr__(self, "phase", phase)
        object.__setattr__(
            self, "lut_profile_id", require_text(self.lut_profile_id, "lut_profile_id")
        )
        object.__setattr__(self, "recipe_id", require_text(self.recipe_id, "recipe_id"))
        object.__setattr__(
            self, "replica_id", require_text(self.replica_id, "replica_id")
        )
        if type(self.target_code) is not int or not 0 <= self.target_code <= 7:
            raise LightnessScreenError("target_code must be an integer in 0..7")
        object.__setattr__(
            self, "measured_lab", finite_triple(self.measured_lab, "measured_lab")
        )
        if not 0.0 <= self.measured_lab[0] <= 100.0:
            raise LightnessScreenError("measured L* must be in 0..100")
        if (
            type(self.single_pixel_pure) is not bool
            or type(self.boundary_clean) is not bool
        ):
            raise LightnessScreenError("purity and boundary flags must be boolean")
        object.__setattr__(
            self,
            "measurement_artifact_sha256",
            require_sha256(
                self.measurement_artifact_sha256, "measurement_artifact_sha256"
            ),
        )


def _delta_e76(left: Sequence[float], right: Sequence[float]) -> float:
    return math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(left, right)))


def _median_lab(values: Sequence[Sequence[float]]) -> tuple[float, float, float]:
    return tuple(median(float(value[index]) for value in values) for index in range(3))  # type: ignore[return-value]


def _p95(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]


def _hue_angle(lab: Sequence[float]) -> float | None:
    a_star, b_star = float(lab[1]), float(lab[2])
    if math.hypot(a_star, b_star) <= 8.0:
        return None
    return math.degrees(math.atan2(b_star, a_star)) % 360.0


def _hue_distance(left: Sequence[float], right: Sequence[float]) -> float | None:
    left_hue = _hue_angle(left)
    right_hue = _hue_angle(right)
    if left_hue is None and right_hue is None:
        return 0.0
    if left_hue is None or right_hue is None:
        return None
    absolute = abs(left_hue - right_hue)
    return min(absolute, 360.0 - absolute)


def _group_key(measurement: LightnessMeasurement) -> tuple[str, str, int]:
    return (
        measurement.controller.value,
        measurement.lut_profile_id,
        measurement.target_code,
    )


def screen_lightness_ladders(
    measurements: Sequence[LightnessMeasurement],
    *,
    minimum_replicas: int = 4,
    position_p95_delta_e76_max: float = 6.6032,
    lightness_delta_l_star_min: float = 8.0,
    hue_angle_difference_degrees_max: float = 10.0,
    identical_target_repeat_delta_e76_max: float = 6.6032,
) -> dict[str, Any]:
    """Return controller-local coarse lightness candidates with signed evidence.

    A recipe is position-stable only when every required target replica is
    present, visually pure, boundary-clean, and within the configured p95
    radius.  Repeat evidence is assessed separately and never fabricated when
    the optional target-repeat action was not run.
    """

    if not isinstance(measurements, (tuple, list)) or not measurements:
        raise LightnessScreenError("measurements must be a non-empty sequence")
    if not all(isinstance(item, LightnessMeasurement) for item in measurements):
        raise LightnessScreenError(
            "measurements must contain LightnessMeasurement values"
        )
    if type(minimum_replicas) is not int or minimum_replicas < 2:
        raise LightnessScreenError("minimum_replicas must be an integer >= 2")
    thresholds = (
        position_p95_delta_e76_max,
        lightness_delta_l_star_min,
        hue_angle_difference_degrees_max,
        identical_target_repeat_delta_e76_max,
    )
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0.0
        for value in thresholds
    ):
        raise LightnessScreenError("screening thresholds must be finite and positive")

    identities = [
        (
            item.controller.value,
            item.lut_profile_id,
            item.target_code,
            item.recipe_id,
            item.replica_id,
            item.phase.value,
        )
        for item in measurements
    ]
    if len(identities) != len(set(identities)):
        raise LightnessScreenError(
            "duplicate controller/profile/recipe/replica/phase measurement"
        )

    grouped: dict[tuple[str, str, int], list[LightnessMeasurement]] = {}
    for measurement in measurements:
        grouped.setdefault(_group_key(measurement), []).append(measurement)

    group_reports: list[dict[str, Any]] = []
    candidate_pair_count = 0
    for (controller, profile_id, target_code), group in sorted(grouped.items()):
        recipe_ids = sorted({item.recipe_id for item in group})
        recipe_reports: list[dict[str, Any]] = []
        stable_recipes: list[dict[str, Any]] = []
        for recipe_id in recipe_ids:
            recipe_values = [item for item in group if item.recipe_id == recipe_id]
            targets = [
                item for item in recipe_values if item.phase is MeasurementPhase.TARGET
            ]
            repeats = [
                item
                for item in recipe_values
                if item.phase is MeasurementPhase.TARGET_REPEAT
            ]
            target_lab = (
                _median_lab([item.measured_lab for item in targets])
                if targets
                else None
            )
            target_distances = (
                [_delta_e76(item.measured_lab, target_lab) for item in targets]
                if target_lab is not None
                else []
            )
            purity_pass = bool(targets) and all(
                item.single_pixel_pure and item.boundary_clean for item in targets
            )
            replica_pass = len(targets) >= minimum_replicas
            position_p95 = _p95(target_distances)
            position_pass = replica_pass and position_p95 <= position_p95_delta_e76_max

            repeat_complete = bool(repeats) and {
                item.replica_id for item in repeats
            } == {item.replica_id for item in targets}
            repeat_purity_pass = repeat_complete and all(
                item.single_pixel_pure and item.boundary_clean for item in repeats
            )
            repeat_delta = None
            repeat_pass = False
            if repeat_complete and target_lab is not None:
                repeat_by_replica = {item.replica_id: item for item in repeats}
                repeat_delta = _p95(
                    [
                        _delta_e76(
                            item.measured_lab,
                            repeat_by_replica[item.replica_id].measured_lab,
                        )
                        for item in targets
                    ]
                )
                repeat_pass = (
                    repeat_purity_pass
                    and repeat_delta <= identical_target_repeat_delta_e76_max
                )

            position_stable = purity_pass and position_pass
            recipe_report = {
                "recipe_id": recipe_id,
                "target_replica_count": len(targets),
                "repeat_replica_count": len(repeats),
                "median_target_lab": (
                    [round(value, 6) for value in target_lab]
                    if target_lab is not None
                    else None
                ),
                "position_p95_delta_e76": round(position_p95, 6),
                "single_pixel_purity_and_boundary_pass": purity_pass,
                "position_repeatability_pass": position_pass,
                "position_stable": position_stable,
                "identical_target_repeat_complete": repeat_complete,
                "identical_target_repeat_p95_delta_e76": (
                    round(repeat_delta, 6) if repeat_delta is not None else None
                ),
                "identical_target_repeat_pass": repeat_pass,
                "artifact_sha256s": sorted(
                    {item.measurement_artifact_sha256 for item in recipe_values}
                ),
            }
            recipe_reports.append(recipe_report)
            if position_stable and target_lab is not None:
                stable_recipes.append(recipe_report)

        candidate_pairs: list[dict[str, Any]] = []
        for left_index, left in enumerate(stable_recipes):
            for right in stable_recipes[left_index + 1 :]:
                left_lab = left["median_target_lab"]
                right_lab = right["median_target_lab"]
                delta_l = abs(float(left_lab[0]) - float(right_lab[0]))
                hue_delta = _hue_distance(left_lab, right_lab)
                same_hue = (
                    hue_delta is not None
                    and hue_delta <= hue_angle_difference_degrees_max
                )
                if delta_l < lightness_delta_l_star_min or not same_hue:
                    continue
                pair = {
                    "darker_recipe_id": (
                        left["recipe_id"]
                        if float(left_lab[0]) < float(right_lab[0])
                        else right["recipe_id"]
                    ),
                    "lighter_recipe_id": (
                        right["recipe_id"]
                        if float(left_lab[0]) < float(right_lab[0])
                        else left["recipe_id"]
                    ),
                    "absolute_delta_l_star": round(delta_l, 6),
                    "hue_angle_difference_degrees": round(float(hue_delta), 6),
                    "repeat_evidence_complete": bool(
                        left["identical_target_repeat_complete"]
                        and right["identical_target_repeat_complete"]
                    ),
                    "repeat_stability_pass": bool(
                        left["identical_target_repeat_pass"]
                        and right["identical_target_repeat_pass"]
                    ),
                    "classification": "COARSE_LIGHTNESS_CANDIDATE",
                }
                candidate_pairs.append(pair)
        candidate_pair_count += len(candidate_pairs)
        group_reports.append(
            {
                "controller": controller,
                "lut_profile_id": profile_id,
                "target_code": target_code,
                "recipes": recipe_reports,
                "candidate_pairs": candidate_pairs,
                "ordered_position_stable_recipes_dark_to_light": [
                    item["recipe_id"]
                    for item in sorted(
                        stable_recipes,
                        key=lambda item: float(item["median_target_lab"][0]),
                    )
                ],
            }
        )

    unsigned = {
        "schema_version": 1,
        "kind": "MF1750_SINGLE_PIXEL_LIGHTNESS_COARSE_SCREEN",
        "measurement_count": len(measurements),
        "groups": group_reports,
        "candidate_pair_count": candidate_pair_count,
        "qualified_lightness_level_count": 0,
        "thresholds": {
            "minimum_replicas": minimum_replicas,
            "position_p95_delta_e76_max": position_p95_delta_e76_max,
            "lightness_delta_l_star_min": lightness_delta_l_star_min,
            "hue_angle_difference_degrees_max": hue_angle_difference_degrees_max,
            "identical_target_repeat_delta_e76_max": (
                identical_target_repeat_delta_e76_max
            ),
        },
        "evidence_boundaries": {
            "controllers_pooled": False,
            "spatial_dither_counts_as_colour": False,
            "camera_is_colorimeter": False,
            "automatic_colour_qualification": False,
            "automatic_refresh_authorization": False,
            "device_io_performed": False,
        },
    }
    return attach_integrity(unsigned)
