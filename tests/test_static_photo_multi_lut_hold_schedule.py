from __future__ import annotations

import pytest

from host.epd_frame import unpack_pixels
from host.static_photo.history_palette import QualificationLevel, TRANSPORT_CODES
from host.static_photo.multi_lut_hold_schedule import (
    Controller,
    LutHoldCapability,
    MultiLutRecipe,
    MultiLutScheduleError,
    PassPhase,
    build_multi_lut_hold_schedule,
)


SHA_A = "a" * 64
SHA_B = "b" * 64


def _recipe(
    name: str,
    controller: Controller,
    profile: str,
    *,
    middle: int | None,
    repeats: int = 2,
    qualified: bool = True,
    fresh_reconstruction: bool = False,
) -> MultiLutRecipe:
    return MultiLutRecipe(
        name,
        controller,
        profile,
        7,
        middle,
        0,
        repeats,
        QualificationLevel.QUALIFIED if qualified else QualificationLevel.CANDIDATE,
        not fresh_reconstruction,
        True,
        True,
        SHA_A,
        fresh_white_reconstruction_qualified=fresh_reconstruction,
    )


def _capability(profile: str, *, retains: tuple[str, ...]) -> LutHoldCapability:
    return LutHoldCapability(profile, 7, 6, True, True, retains, SHA_B)


def test_two_lut_schedule_holds_committed_pixels_and_is_explicit() -> None:
    recipes = (
        _recipe("A-CS1", Controller.CS1, "A", middle=2),
        _recipe("B-CS1", Controller.CS1, "B", middle=None, repeats=2),
        _recipe("A-CS2", Controller.CS2, "A", middle=3),
        _recipe("B-CS2", Controller.CS2, "B", middle=None, repeats=2),
    )
    # Width 4: first two columns are CS1, last two columns are CS2.
    indices = bytes((0, 1, 2, 3, 0, 1, 2, 3))
    result = build_multi_lut_hold_schedule(
        recipes,
        indices,
        (_capability("A", retains=()), _capability("B", retains=("A",))),
        profile_order=("A", "B"),
        width=4,
        height=2,
    )
    assert [item.phase for item in result.passes] == [
        PassPhase.SOURCE,
        PassPhase.MIDDLE,
        PassPhase.TARGET,
        PassPhase.TARGET_REPEAT,
        PassPhase.SOURCE,
        PassPhase.TARGET,
        PassPhase.TARGET_REPEAT,
    ]
    second_profile_source = unpack_pixels(
        result.passes[4].packed_frame,
        4,
        2,
        allowed_colors=TRANSPORT_CODES,
    )
    # A pixels use B's controller-specific HOLD codes; B pixels receive source C7.
    assert second_profile_source == bytes((7, 7, 6, 7, 7, 7, 6, 7))
    mapping = result.mapping()
    assert mapping["spatial_dithering"] is False
    assert mapping["live_authorized"] is False
    assert mapping["autochain_allowed"] is False
    assert mapping["independent_factory_otp_white_containment_required"] is True
    assert len(mapping["integrity"]["canonical_sha256"]) == 64
    assert mapping["recipes"][0]["measurement_artifact_sha256"] == SHA_A
    assert mapping["hold_capabilities"][1]["retains_profile_ids"] == ["A"]


def test_candidate_recipe_is_rejected_before_schedule_generation() -> None:
    recipes = (
        _recipe("A-CS1", Controller.CS1, "A", middle=2, qualified=False),
        _recipe("A-CS2", Controller.CS2, "A", middle=2),
    )
    with pytest.raises(MultiLutScheduleError, match="qualified for colour"):
        build_multi_lut_hold_schedule(
            recipes,
            bytes((0, 0, 1, 1)),
            (_capability("A", retains=()),),
            profile_order=("A",),
            width=4,
            height=1,
        )


def test_qualified_recipe_requires_a_reproducibility_and_recovery_gate() -> None:
    with pytest.raises(MultiLutScheduleError, match="requires fresh-white"):
        _recipe("INSUFFICIENT", Controller.CS1, "A", middle=None, repeats=1)


def test_fresh_white_reconstruction_allows_one_target_per_construction() -> None:
    recipe = _recipe(
        "HISTORY",
        Controller.CS1,
        "A",
        middle=3,
        repeats=1,
        fresh_reconstruction=True,
    )
    assert recipe.fresh_white_reconstruction_qualified is True
    assert recipe.target_repeat_count == 1


def test_recipe_rejects_ambiguous_reproducibility_modes() -> None:
    with pytest.raises(MultiLutScheduleError, match="mode is ambiguous"):
        MultiLutRecipe(
            "AMBIGUOUS",
            Controller.CS1,
            "A",
            7,
            3,
            0,
            2,
            QualificationLevel.QUALIFIED,
            True,
            True,
            True,
            SHA_A,
            fresh_white_reconstruction_qualified=True,
        )


def test_fresh_reconstruction_cannot_generate_in_place_target_repeats() -> None:
    with pytest.raises(MultiLutScheduleError, match="one target per construction"):
        _recipe(
            "NO-IN-PLACE-REPEAT",
            Controller.CS1,
            "A",
            middle=3,
            repeats=2,
            fresh_reconstruction=True,
        )


def test_fresh_reconstruction_schedule_has_no_in_place_repeat_pass() -> None:
    recipes = (
        _recipe(
            "FRESH-CS1",
            Controller.CS1,
            "A",
            middle=3,
            repeats=1,
            fresh_reconstruction=True,
        ),
        _recipe(
            "FRESH-CS2",
            Controller.CS2,
            "A",
            middle=3,
            repeats=1,
            fresh_reconstruction=True,
        ),
    )
    result = build_multi_lut_hold_schedule(
        recipes,
        bytes((0, 0, 1, 1)),
        (_capability("A", retains=()),),
        profile_order=("A",),
        width=4,
        height=1,
    )
    assert [item.phase for item in result.passes] == [
        PassPhase.SOURCE,
        PassPhase.MIDDLE,
        PassPhase.TARGET,
    ]
    mapping = result.mapping()
    assert all(
        recipe["fresh_white_reconstruction_qualified"] is True
        for recipe in mapping["recipes"]
    )
    assert all(
        recipe["identical_target_repeat_qualified"] is False
        for recipe in mapping["recipes"]
    )


def test_unused_candidate_does_not_pollute_a_qualified_schedule() -> None:
    recipes = (
        _recipe("A-CS1", Controller.CS1, "A", middle=None),
        _recipe("A-CS2", Controller.CS2, "A", middle=None),
        _recipe("UNUSED", Controller.CS1, "UNUSED", middle=4, qualified=False),
    )
    result = build_multi_lut_hold_schedule(
        recipes,
        bytes((0, 0, 1, 1)),
        (_capability("A", retains=()),),
        profile_order=("A",),
        width=4,
        height=1,
    )
    assert result.profile_order == ("A",)
    assert [item.phase for item in result.passes] == [
        PassPhase.SOURCE,
        PassPhase.TARGET,
        PassPhase.TARGET_REPEAT,
    ]


def test_cross_lut_order_requires_directional_retention_evidence() -> None:
    recipes = (
        _recipe("A-CS1", Controller.CS1, "A", middle=None),
        _recipe("B-CS1", Controller.CS1, "B", middle=None),
        _recipe("A-CS2", Controller.CS2, "A", middle=None),
        _recipe("B-CS2", Controller.CS2, "B", middle=None),
    )
    with pytest.raises(MultiLutScheduleError, match="retain every committed"):
        build_multi_lut_hold_schedule(
            recipes,
            bytes((0, 1, 2, 3)),
            (_capability("A", retains=()), _capability("B", retains=())),
            profile_order=("A", "B"),
            width=4,
            height=1,
        )


def test_controller_specific_recipe_cannot_cross_panel_half() -> None:
    recipes = (
        _recipe("A-CS1", Controller.CS1, "A", middle=None),
        _recipe("A-CS2", Controller.CS2, "A", middle=None),
    )
    with pytest.raises(MultiLutScheduleError, match="controller differs"):
        build_multi_lut_hold_schedule(
            recipes,
            bytes((1, 0, 0, 1)),
            (_capability("A", retains=()),),
            profile_order=("A",),
            width=4,
            height=1,
        )
