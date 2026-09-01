from __future__ import annotations

import hashlib
import json

import pytest

from host.static_photo.common import attach_integrity
from host.static_photo import (
    CrossControllerOpticalMatchEvidence,
    PaletteTargetCoverageError,
    QualifiedPaletteSlot,
    build_default_256_palette_target,
    build_palette_target_coverage,
    export_palette_target_coverage,
    verify_palette_target,
    verify_palette_target_coverage,
)
from host.static_photo.multi_lut_hold_schedule import Controller


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _slot(
    controller: Controller,
    slot_id: str,
    *,
    recipe_id: str | None = None,
    family_id: str | None = None,
    single_pixel_pure: bool = True,
    spatial_dithering_used: bool = False,
) -> QualifiedPaletteSlot:
    inferred_family = "NEUTRAL" if slot_id.startswith("N-") else slot_id.split("-")[0]
    return QualifiedPaletteSlot(
        controller=controller,
        target_slot_id=slot_id,
        recipe_id=recipe_id or f"recipe-{controller.value}-{slot_id}",
        family_id=family_id or inferred_family,
        lut_profile_id=f"profile-{controller.value}",
        measured_lab=(50.0, 10.0, -5.0),
        qualification_evidence_sha256=_sha(
            f"qualification-{controller.value}-{slot_id}-{recipe_id or 'default'}"
        ),
        single_pixel_pure=single_pixel_pure,
        spatial_dithering_used=spatial_dithering_used,
    )


def _match(
    slot_id: str,
    *,
    cs1_recipe_id: str | None = None,
    cs2_recipe_id: str | None = None,
    delta_e00: float = 1.2,
    threshold: float = 3.0,
    passed: bool = True,
    evidence_sha256: str | None = None,
) -> CrossControllerOpticalMatchEvidence:
    return CrossControllerOpticalMatchEvidence(
        target_slot_id=slot_id,
        cs1_recipe_id=cs1_recipe_id or f"recipe-CS1-{slot_id}",
        cs2_recipe_id=cs2_recipe_id or f"recipe-CS2-{slot_id}",
        delta_e00=delta_e00,
        acceptance_threshold_delta_e00=threshold,
        passed=passed,
        optical_match_evidence_sha256=evidence_sha256
        or _sha(f"optical-match-{slot_id}-{delta_e00}-{threshold}-{passed}"),
    )


def test_target_is_12_named_families_times_2_tracks_times_10_plus_16() -> None:
    target = build_default_256_palette_target()
    verify_palette_target(target)

    allocation = target["allocation"]
    assert allocation["final_palette_slot_count"] == 256
    assert allocation["named_chromatic_hue_family_ids"] == [
        "R",
        "RO",
        "O",
        "Y",
        "YG",
        "G",
        "T",
        "C",
        "B",
        "I",
        "V",
        "M",
    ]
    assert allocation["named_chromatic_hue_family_count"] == 12
    assert allocation["chroma_or_subhue_tracks_per_family"] == 2
    assert allocation["lightness_steps_per_track"] == 10
    assert allocation["chromatic_lightness_series_count"] == 24
    assert allocation["chromatic_slot_count"] == 240
    assert allocation["neutral_slot_count"] == 16
    assert len(target["slots"]) == 256
    assert len({slot["slot_id"] for slot in target["slots"]}) == 256
    assert target["interpretation"]["two_tracks_are_not_independent_pure_hues"]
    assert target["development_milestones"]["chromatic_lightness_step_order"] == [
        3,
        5,
        10,
    ]
    for family_id in allocation["named_chromatic_hue_family_ids"]:
        family = [slot for slot in target["slots"] if slot["family_id"] == family_id]
        assert len(family) == 20
        assert {slot["track_id"] for slot in family} == {"T1", "T2"}
        assert all(
            len([slot for slot in family if slot["track_id"] == track_id]) == 10
            for track_id in ("T1", "T2")
        )


def test_empty_coverage_requests_only_three_step_ladder() -> None:
    coverage = build_palette_target_coverage(build_default_256_palette_target())
    verify_palette_target_coverage(coverage)

    assert coverage["status"] == "NO_QUALIFIED_SLOTS"
    assert {
        item["experiment_kind"]
        for item in coverage["next_priority_function_experiments"]
    } == {"ESTABLISH_FIRST_STABLE_BASE_3_STEP_LIGHTNESS_LADDER"}
    assert all(
        item["target_step_count"] == 3
        for item in coverage["next_priority_function_experiments"]
    )
    assert (
        coverage["policy"]["ten_step_claim_before_three_and_five_step_gates"] is False
    )
    assert coverage["execution_boundary"]["hardware_accessed"] is False


@pytest.mark.parametrize(
    ("ranks", "kind", "target_count", "missing_ranks"),
    [
        ((5,), "COMPLETE_CURRENT_3_STEP_LIGHTNESS_LADDER", 3, (1, 10)),
        ((1, 5, 10), "EXPAND_CURRENT_LIGHTNESS_LADDER_TO_5_STEPS", 5, (3, 8)),
        (
            (1, 3, 5, 8, 10),
            "EXPAND_CURRENT_LIGHTNESS_LADDER_TO_10_STEPS",
            10,
            (2, 4, 6, 7, 9),
        ),
    ],
)
def test_lightness_development_advances_strictly_three_then_five_then_ten(
    ranks: tuple[int, ...],
    kind: str,
    target_count: int,
    missing_ranks: tuple[int, ...],
) -> None:
    assignments = tuple(_slot(Controller.CS1, f"B-T1-L{rank:02d}") for rank in ranks)
    coverage = build_palette_target_coverage(
        build_default_256_palette_target(), assignments
    )
    priority = coverage["next_priority_function_experiments"][0]

    assert priority["experiment_kind"] == kind
    assert priority["family_id"] == "B"
    assert priority["track_id"] == "T1"
    assert priority["target_step_count"] == target_count
    assert priority["target_slot_ids"] == [
        f"B-T1-L{rank:02d}" for rank in missing_ranks
    ]


def test_partial_family_admits_only_exact_controller_local_slots() -> None:
    assignments = tuple(
        _slot(Controller.CS1, f"YG-T2-L{rank:02d}") for rank in (1, 5, 10)
    )
    coverage = build_palette_target_coverage(
        build_default_256_palette_target(), assignments
    )
    cs1, cs2 = coverage["controllers"]
    series = next(
        item
        for item in cs1["chromatic_lightness_series"]
        if item["lightness_series_id"] == "YG-T2"
    )

    assert series["status"] == "PARTIAL_READY"
    assert series["lightness_milestone"]["achieved_step_count"] == 3
    assert series["photo_chain_subset_admitted"] is True
    assert cs1["photo_chain_admission"]["admitted_slot_ids"] == [
        "YG-T2-L01",
        "YG-T2-L05",
        "YG-T2-L10",
    ]
    assert cs2["photo_chain_admission"]["admitted"] is False
    assert coverage["policy"]["controllers_pooled"] is False


def test_complete_chromatic_path_starts_neutral_at_three_steps() -> None:
    assignments = tuple(
        _slot(Controller.CS1, f"G-T1-L{rank:02d}") for rank in range(1, 11)
    )
    coverage = build_palette_target_coverage(
        build_default_256_palette_target(), assignments
    )
    cs1 = coverage["controllers"][0]
    priority = coverage["next_priority_function_experiments"][0]

    assert cs1["complete_ten_step_chromatic_series_ids"] == ["G-T1"]
    assert priority["experiment_kind"] == "ESTABLISH_NEUTRAL_3_STEP_LIGHTNESS_LADDER"
    assert priority["target_step_count"] == 3
    assert priority["target_slot_ids"] == ["N-L01", "N-L08", "N-L16"]


def test_ten_step_neutral_milestone_unlocks_limited_photo_validation() -> None:
    chromatic = [_slot(Controller.CS1, f"R-T1-L{rank:02d}") for rank in range(1, 11)]
    neutral_ranks = (1, 2, 4, 6, 8, 10, 12, 14, 15, 16)
    neutral = [_slot(Controller.CS1, f"N-L{rank:02d}") for rank in neutral_ranks]
    coverage = build_palette_target_coverage(
        build_default_256_palette_target(), tuple(chromatic + neutral)
    )
    priority = coverage["next_priority_function_experiments"][0]

    assert (
        priority["experiment_kind"] == "VALIDATE_LIMITED_PHOTO_CHAIN_WITH_READY_SUBSET"
    )
    assert len(priority["target_slot_ids"]) == 20
    assert coverage["policy"]["broad_hue_enumeration_deferred"] is True


def test_same_slot_on_both_controllers_without_optical_evidence_is_not_panel_ready() -> (
    None
):
    slot_id = "O-T1-L05"
    coverage = build_palette_target_coverage(
        build_default_256_palette_target(),
        (_slot(Controller.CS1, slot_id), _slot(Controller.CS2, slot_id)),
    )
    panel = coverage["panel_wide_intersection"]

    assert panel["same_target_slot_candidate_ids"] == [slot_id]
    assert panel["optically_matched_slot_ids"] == []
    assert panel["slot_ids_without_passing_optical_evidence"] == [slot_id]
    assert panel["full_panel_limited_photo_chain_admitted"] is False
    assert panel["next_gate"]["experiment_kind"] == (
        "COLLECT_CROSS_CONTROLLER_OPTICAL_MATCH_EVIDENCE"
    )
    assert coverage["policy"]["same_slot_intersection_grants_panel_admission"] is False


def test_complete_controller_tables_without_matches_are_not_panel_target_complete() -> (
    None
):
    target = build_default_256_palette_target()
    slot_ids = [slot["slot_id"] for slot in target["slots"]]
    assignments = tuple(
        _slot(controller, slot_id)
        for controller in (Controller.CS1, Controller.CS2)
        for slot_id in slot_ids
    )

    coverage = build_palette_target_coverage(target, assignments)

    assert coverage["status"] == "CONTROLLER_TARGET_COMPLETE_PANEL_MATCH_PENDING"
    assert all(
        item["qualified_slot_count"] == 256 for item in coverage["controllers"]
    )
    assert coverage["panel_wide_intersection"]["optically_matched_slot_count"] == 0
    assert (
        coverage["panel_wide_intersection"][
            "full_panel_limited_photo_chain_admitted"
        ]
        is False
    )


def test_passing_recipe_bound_delta_e_evidence_admits_only_that_panel_slot() -> None:
    slot_id = "M-T2-L08"
    assignments = (_slot(Controller.CS1, slot_id), _slot(Controller.CS2, slot_id))
    coverage = build_palette_target_coverage(
        build_default_256_palette_target(), assignments, (_match(slot_id),)
    )
    panel = coverage["panel_wide_intersection"]

    assert panel["optically_matched_slot_ids"] == [slot_id]
    assert panel["full_panel_limited_photo_chain_admitted"] is True
    assert panel["next_gate"]["experiment_kind"] == "PANEL_WIDE_MATCHED_SUBSET_READY"
    evidence = coverage["cross_controller_optical_matches"][0]
    assert evidence["cs1_recipe_id"] == f"recipe-CS1-{slot_id}"
    assert evidence["cs2_recipe_id"] == f"recipe-CS2-{slot_id}"
    assert evidence["delta_e00"] == 1.2


def test_failed_optical_evidence_remains_fail_closed() -> None:
    slot_id = "I-T1-L03"
    coverage = build_palette_target_coverage(
        build_default_256_palette_target(),
        (_slot(Controller.CS1, slot_id), _slot(Controller.CS2, slot_id)),
        (_match(slot_id, delta_e00=4.0, threshold=3.0, passed=False),),
    )
    panel = coverage["panel_wide_intersection"]

    assert panel["failed_optical_match_slot_ids"] == [slot_id]
    assert panel["optically_matched_slot_ids"] == []
    assert panel["full_panel_limited_photo_chain_admitted"] is False


def test_optical_evidence_must_bind_both_exact_recipes_and_be_independent() -> None:
    slot_id = "C-T2-L07"
    cs1 = _slot(Controller.CS1, slot_id)
    cs2 = _slot(Controller.CS2, slot_id)
    target = build_default_256_palette_target()

    with pytest.raises(PaletteTargetCoverageError, match="recipe binding differs"):
        build_palette_target_coverage(
            target,
            (cs1, cs2),
            (_match(slot_id, cs1_recipe_id="wrong-recipe"),),
        )
    with pytest.raises(PaletteTargetCoverageError, match="independent evidence"):
        build_palette_target_coverage(
            target,
            (cs1, cs2),
            (_match(slot_id, evidence_sha256=cs1.qualification_evidence_sha256),),
        )
    with pytest.raises(
        PaletteTargetCoverageError, match="requires qualified CS1 and CS2"
    ):
        build_palette_target_coverage(target, (cs1,), (_match(slot_id),))


def test_passing_optical_evidence_cannot_exceed_delta_e_threshold() -> None:
    with pytest.raises(PaletteTargetCoverageError, match="exceeds"):
        _match("V-T1-L05", delta_e00=3.01, threshold=3.0, passed=True)


def test_spatial_dither_non_pure_unknown_and_duplicate_assignments_are_rejected() -> (
    None
):
    with pytest.raises(PaletteTargetCoverageError, match="spatial dithering"):
        _slot(Controller.CS1, "R-T1-L01", spatial_dithering_used=True)
    with pytest.raises(PaletteTargetCoverageError, match="single-pixel pure"):
        _slot(Controller.CS1, "R-T1-L01", single_pixel_pure=False)

    target = build_default_256_palette_target()
    with pytest.raises(PaletteTargetCoverageError, match="unknown target slot"):
        build_palette_target_coverage(target, (_slot(Controller.CS1, "Q-T1-L01"),))
    with pytest.raises(PaletteTargetCoverageError, match="family binding differs"):
        build_palette_target_coverage(
            target,
            (_slot(Controller.CS1, "R-T1-L01", family_id="RO"),),
        )
    with pytest.raises(PaletteTargetCoverageError, match="duplicate controller"):
        build_palette_target_coverage(
            target,
            (
                _slot(Controller.CS1, "R-T1-L01", recipe_id="recipe-a"),
                _slot(Controller.CS1, "R-T1-L01", recipe_id="recipe-b"),
            ),
        )
    with pytest.raises(PaletteTargetCoverageError, match="multiple target slots"):
        build_palette_target_coverage(
            target,
            (
                _slot(Controller.CS1, "R-T1-L01", recipe_id="same-recipe"),
                _slot(Controller.CS1, "R-T1-L02", recipe_id="same-recipe"),
            ),
        )


def test_coverage_is_order_independent_and_tamper_detected() -> None:
    target = build_default_256_palette_target()
    slot_id = "RO-T2-L04"
    cs1 = _slot(Controller.CS1, slot_id)
    cs2 = _slot(Controller.CS2, slot_id)
    match = _match(slot_id)
    first = build_palette_target_coverage(target, (cs2, cs1), (match,))
    second = build_palette_target_coverage(target, (cs1, cs2), (match,))

    assert first == second
    tampered = json.loads(json.dumps(first))
    tampered["panel_wide_intersection"]["optically_matched_slot_ids"] = []
    with pytest.raises(PaletteTargetCoverageError, match="canonical SHA-256 differs"):
        verify_palette_target_coverage(tampered)


def test_resealed_same_slot_without_passing_evidence_still_fails_closed() -> None:
    slot_id = "Y-T1-L05"
    coverage = build_palette_target_coverage(
        build_default_256_palette_target(),
        (_slot(Controller.CS1, slot_id), _slot(Controller.CS2, slot_id)),
    )
    unsigned = dict(coverage)
    unsigned.pop("integrity")
    unsigned["panel_wide_intersection"] = {
        **unsigned["panel_wide_intersection"],
        "optically_matched_slot_count": 1,
        "optically_matched_slot_ids": [slot_id],
        "slot_ids_without_passing_optical_evidence": [],
        "full_panel_limited_photo_chain_admitted": True,
    }
    resealed = attach_integrity(unsigned)

    with pytest.raises(PaletteTargetCoverageError, match="optical matches differ"):
        verify_palette_target_coverage(resealed)


def test_target_tamper_bad_hash_and_export_boundary(tmp_path) -> None:
    target = build_default_256_palette_target()
    tampered = json.loads(json.dumps(target))
    tampered["slots"][0]["target_lightness_lstar"] = 6
    with pytest.raises(PaletteTargetCoverageError, match="canonical SHA-256 differs"):
        verify_palette_target(tampered)
    with pytest.raises(PaletteTargetCoverageError, match="lowercase"):
        _match("T-T1-L01", evidence_sha256=_sha("evidence").upper())

    coverage = build_palette_target_coverage(target)
    output = tmp_path / "palette-coverage.json"
    assert export_palette_target_coverage(coverage, output) == output
    verify_palette_target_coverage(json.loads(output.read_text(encoding="utf-8")))
    with pytest.raises(PaletteTargetCoverageError, match="already exists"):
        export_palette_target_coverage(coverage, output)
