from __future__ import annotations

import pytest

from host.static_photo.common import verify_integrity
from host.static_photo.lightness_screen import (
    LightnessMeasurement,
    LightnessScreenError,
    MeasurementPhase,
    screen_lightness_ladders,
)
from host.static_photo.multi_lut_hold_schedule import Controller


SHA = "a" * 64


def _recipe(
    recipe_id: str,
    lab: tuple[float, float, float],
    *,
    controller: Controller = Controller.CS1,
    profile: str = "known-compatible-r20-a",
    pure: bool = True,
    boundary: bool = True,
    include_repeat: bool = False,
) -> list[LightnessMeasurement]:
    output: list[LightnessMeasurement] = []
    for index, offset in enumerate((-0.3, -0.1, 0.1, 0.3)):
        measured = (lab[0] + offset, lab[1], lab[2])
        output.append(
            LightnessMeasurement(
                controller,
                profile,
                5,
                recipe_id,
                f"r{index}",
                MeasurementPhase.TARGET,
                measured,
                pure,
                boundary,
                SHA,
            )
        )
        if include_repeat:
            output.append(
                LightnessMeasurement(
                    controller,
                    profile,
                    5,
                    recipe_id,
                    f"r{index}",
                    MeasurementPhase.TARGET_REPEAT,
                    (measured[0] + 0.2, measured[1], measured[2]),
                    pure,
                    boundary,
                    SHA,
                )
            )
    return output


def test_same_controller_hue_and_target_produce_lightness_candidate() -> None:
    report = screen_lightness_ladders(
        _recipe("dark", (38.0, 15.0, -32.0), include_repeat=True)
        + _recipe("light", (55.0, 15.5, -31.5), include_repeat=True)
    )
    verify_integrity(report, "lightness report")
    assert report["candidate_pair_count"] == 1
    pair = report["groups"][0]["candidate_pairs"][0]
    assert pair["darker_recipe_id"] == "dark"
    assert pair["lighter_recipe_id"] == "light"
    assert pair["repeat_evidence_complete"] is True
    assert pair["repeat_stability_pass"] is True
    assert report["qualified_lightness_level_count"] == 0


def test_controllers_are_never_pooled() -> None:
    report = screen_lightness_ladders(
        _recipe("dark", (38.0, 15.0, -32.0), controller=Controller.CS1)
        + _recipe("light", (58.0, 15.0, -32.0), controller=Controller.CS2)
    )
    assert len(report["groups"]) == 2
    assert report["candidate_pair_count"] == 0


def test_different_profiles_are_never_pooled() -> None:
    report = screen_lightness_ladders(
        _recipe("dark", (38.0, 15.0, -32.0), profile="r20-a")
        + _recipe("light", (58.0, 15.0, -32.0), profile="r20-b")
    )
    assert len(report["groups"]) == 2
    assert report["candidate_pair_count"] == 0


@pytest.mark.parametrize("pure,boundary", [(False, True), (True, False)])
def test_spatial_impurity_or_bad_boundary_rejects_recipe(
    pure: bool, boundary: bool
) -> None:
    report = screen_lightness_ladders(
        _recipe("dark", (38.0, 15.0, -32.0), pure=pure, boundary=boundary)
        + _recipe("light", (58.0, 15.0, -32.0))
    )
    assert report["candidate_pair_count"] == 0


def test_position_instability_rejects_recipe() -> None:
    unstable = _recipe("dark", (38.0, 15.0, -32.0))
    unstable[-1] = LightnessMeasurement(
        Controller.CS1,
        "known-compatible-r20-a",
        5,
        "dark",
        "r3",
        MeasurementPhase.TARGET,
        (70.0, 15.0, -32.0),
        True,
        True,
        SHA,
    )
    report = screen_lightness_ladders(unstable + _recipe("light", (58.0, 15.0, -32.0)))
    assert report["candidate_pair_count"] == 0


def test_hue_drift_is_not_a_lightness_candidate() -> None:
    report = screen_lightness_ladders(
        _recipe("blue", (38.0, 15.0, -32.0)) + _recipe("red", (58.0, 34.0, 18.0))
    )
    assert report["candidate_pair_count"] == 0


def test_repeat_must_hold_at_each_matching_replica() -> None:
    values = _recipe("dark", (38.0, 15.0, -32.0), include_repeat=True)
    repeat_index = next(
        index
        for index, item in enumerate(values)
        if item.phase is MeasurementPhase.TARGET_REPEAT and item.replica_id == "r3"
    )
    original = values[repeat_index]
    values[repeat_index] = LightnessMeasurement(
        original.controller,
        original.lut_profile_id,
        original.target_code,
        original.recipe_id,
        original.replica_id,
        original.phase,
        (original.measured_lab[0] + 25.0, *original.measured_lab[1:]),
        True,
        True,
        SHA,
    )
    report = screen_lightness_ladders(
        values + _recipe("light", (58.0, 15.0, -32.0), include_repeat=True)
    )
    pair = report["groups"][0]["candidate_pairs"][0]
    assert pair["repeat_evidence_complete"] is True
    assert pair["repeat_stability_pass"] is False


def test_two_neutral_gray_levels_are_candidate_pair() -> None:
    report = screen_lightness_ladders(
        _recipe("gray-dark", (32.0, 2.0, -1.0))
        + _recipe("gray-light", (62.0, -2.0, 1.5))
    )
    assert report["candidate_pair_count"] == 1


def test_duplicate_measurement_identity_fails_closed() -> None:
    values = _recipe("gray", (32.0, 2.0, -1.0))
    with pytest.raises(LightnessScreenError, match="duplicate"):
        screen_lightness_ladders(values + [values[0]])
