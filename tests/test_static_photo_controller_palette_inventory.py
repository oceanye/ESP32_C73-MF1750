from __future__ import annotations

import hashlib

import pytest

from host.static_photo.common import verify_integrity
from host.static_photo.controller_palette_inventory import (
    CandidateKind,
    ControllerPaletteCandidate,
    ControllerPaletteEvidence,
    ControllerPaletteInventory,
    ControllerPaletteInventoryError,
    CrossProfileRetentionEvidence,
    QualificationEvidenceRole,
    ReproducibilityMode,
    candidate_from_lightness_screen,
)
from host.static_photo.lightness_screen import (
    LightnessMeasurement,
    MeasurementPhase,
    screen_lightness_ladders,
)
from host.static_photo.multi_lut_hold_schedule import (
    Controller,
    build_multi_lut_hold_schedule,
)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _candidate(
    candidate_id: str,
    controller: Controller,
    profile: str,
    *,
    dither: bool = False,
    reproducibility_mode: ReproducibilityMode = (
        ReproducibilityMode.IDENTICAL_TARGET_REPEAT
    ),
    target_repeat_count: int = 2,
) -> ControllerPaletteCandidate:
    return ControllerPaletteCandidate(
        candidate_id=candidate_id,
        controller=controller,
        lut_profile_id=profile,
        kind=CandidateKind.COARSE_LIGHTNESS,
        source_code=7,
        middle_code=3,
        target_code=0,
        target_repeat_count=target_repeat_count,
        measured_lab=(42.0, 12.0, -28.0),
        preview_rgb=None,
        single_pixel_pure=True,
        spatial_dithering_used=dither,
        coarse_screen_artifact_sha256=_sha(f"coarse-file-{controller}-{candidate_id}"),
        coarse_screen_canonical_sha256=_sha(
            f"coarse-canonical-{controller}-{candidate_id}"
        ),
        reproducibility_mode=reproducibility_mode,
    )


def _evidence(
    candidate: ControllerPaletteCandidate,
    role: QualificationEvidenceRole,
    *,
    artifact_label: str | None = None,
    passed: bool = True,
) -> ControllerPaletteEvidence:
    return ControllerPaletteEvidence(
        role=role,
        controller=candidate.controller,
        candidate_id=candidate.candidate_id,
        lut_profile_id=candidate.lut_profile_id,
        candidate_fingerprint_sha256=candidate.fingerprint_sha256,
        artifact_sha256=_sha(
            artifact_label
            or f"{candidate.controller}-{candidate.candidate_id}-{role.value}"
        ),
        passed=passed,
        single_pixel_pure=True,
        spatial_dithering_used=False,
        observed_target_repeat_count=(
            2 if role is QualificationEvidenceRole.IDENTICAL_TARGET_REPEAT else None
        ),
        fresh_white_reconstruction_count=(
            2 if role is QualificationEvidenceRole.FRESH_WHITE_RECONSTRUCTION else None
        ),
        hold_code=(
            (7 if candidate.controller is Controller.CS1 else 6)
            if role is QualificationEvidenceRole.LOCAL_HOLD
            else None
        ),
        baseline_hold_passed=(
            True if role is QualificationEvidenceRole.LOCAL_HOLD else None
        ),
    )


def _complete_evidence(
    candidate: ControllerPaletteCandidate,
) -> tuple[ControllerPaletteEvidence, ...]:
    reproducibility_role = (
        QualificationEvidenceRole.IDENTICAL_TARGET_REPEAT
        if candidate.reproducibility_mode is ReproducibilityMode.IDENTICAL_TARGET_REPEAT
        else QualificationEvidenceRole.FRESH_WHITE_RECONSTRUCTION
    )
    roles = (
        reproducibility_role,
        QualificationEvidenceRole.LOCAL_HOLD,
        QualificationEvidenceRole.FACTORY_WHITE_RECOVERY,
    )
    return tuple(_evidence(candidate, role) for role in roles)


def _cross(
    controller: Controller,
    active: str,
    retained: str,
    *,
    artifact_label: str | None = None,
) -> CrossProfileRetentionEvidence:
    return CrossProfileRetentionEvidence(
        controller=controller,
        active_lut_profile_id=active,
        retained_lut_profile_id=retained,
        hold_code=7 if controller is Controller.CS1 else 6,
        artifact_sha256=_sha(
            artifact_label or f"cross-{controller}-{active}-retains-{retained}"
        ),
        passed=True,
        retained_pixels_unchanged=True,
        single_pixel_pure=True,
        spatial_dithering_used=False,
    )


def test_coarse_candidate_is_never_automatically_promoted() -> None:
    candidate = _candidate("gray-1", Controller.CS1, "R20-A")
    inventory = ControllerPaletteInventory("inventory", (candidate,), ())
    mapping = inventory.mapping()
    verify_integrity(mapping, "controller palette inventory")
    assert mapping["controller_local_qualified_recipe_count"] == 0
    assert mapping["candidates"][0]["qualification_state"] == "COARSE_CANDIDATE_ONLY"
    assert inventory.qualified_entries(Controller.CS1) == ()
    assert (
        mapping["evidence_boundaries"]["coarse_candidate_automatically_promoted"]
        is False
    )


def test_verified_lightness_pair_still_enters_as_candidate_only() -> None:
    measurements = []
    for recipe_id, base_l in (("dark", 35.0), ("light", 55.0)):
        for replica in range(4):
            for phase, offset in (
                (MeasurementPhase.TARGET, 0.0),
                (MeasurementPhase.TARGET_REPEAT, 0.2),
            ):
                measurements.append(
                    LightnessMeasurement(
                        Controller.CS1,
                        "A",
                        0,
                        recipe_id,
                        f"r{replica}",
                        phase,
                        (base_l + offset, 12.0, -28.0),
                        True,
                        True,
                        _sha(f"measurement-{recipe_id}-{replica}-{phase.value}"),
                    )
                )
    report = screen_lightness_ladders(measurements)
    candidate = candidate_from_lightness_screen(
        report,
        controller=Controller.CS1,
        lut_profile_id="A",
        target_code=0,
        recipe_id="dark",
        source_code=7,
        middle_code=3,
        target_repeat_count=1,
        report_file_sha256=_sha("screen-report-file"),
    )
    inventory = ControllerPaletteInventory("inventory", (candidate,), ())
    assert report["groups"][0]["candidate_pairs"][0]["repeat_stability_pass"] is True
    assert (
        candidate.reproducibility_mode is ReproducibilityMode.FRESH_WHITE_RECONSTRUCTION
    )
    assert inventory.qualified_entries(Controller.CS1) == ()


def test_lightness_recipe_outside_a_candidate_pair_is_rejected() -> None:
    measurements = [
        LightnessMeasurement(
            Controller.CS1,
            "A",
            0,
            "only",
            f"r{replica}",
            MeasurementPhase.TARGET,
            (35.0, 12.0, -28.0),
            True,
            True,
            _sha(f"measurement-only-{replica}"),
        )
        for replica in range(4)
    ]
    report = screen_lightness_ladders(measurements)
    with pytest.raises(ControllerPaletteInventoryError, match="not a coarse"):
        candidate_from_lightness_screen(
            report,
            controller=Controller.CS1,
            lut_profile_id="A",
            target_code=0,
            recipe_id="only",
            source_code=7,
            middle_code=3,
            target_repeat_count=1,
            report_file_sha256=_sha("screen-report-file"),
        )


def test_repeat_hold_and_white_proofs_must_be_independent() -> None:
    candidate = _candidate("gray-1", Controller.CS1, "R20-A")
    evidence = tuple(
        _evidence(candidate, role, artifact_label="shared-proof")
        for role in (
            QualificationEvidenceRole.IDENTICAL_TARGET_REPEAT,
            QualificationEvidenceRole.LOCAL_HOLD,
            QualificationEvidenceRole.FACTORY_WHITE_RECOVERY,
        )
    )
    inventory = ControllerPaletteInventory("inventory", (candidate,), evidence)
    record = inventory.mapping()["candidates"][0]
    assert record["qualification_state"] == "COARSE_CANDIDATE_ONLY"
    assert "evidence:not-independent" in record["blocking_reasons"]


def test_local_hold_proof_must_explicitly_pass_baseline_hold() -> None:
    candidate = _candidate("gray-1", Controller.CS1, "R20-A")
    proof = list(_complete_evidence(candidate))
    local_index = next(
        index
        for index, item in enumerate(proof)
        if item.role is QualificationEvidenceRole.LOCAL_HOLD
    )
    local = proof[local_index]
    proof[local_index] = ControllerPaletteEvidence(
        role=local.role,
        controller=local.controller,
        candidate_id=local.candidate_id,
        lut_profile_id=local.lut_profile_id,
        candidate_fingerprint_sha256=local.candidate_fingerprint_sha256,
        artifact_sha256=local.artifact_sha256,
        passed=True,
        single_pixel_pure=True,
        spatial_dithering_used=False,
        hold_code=local.hold_code,
        baseline_hold_passed=False,
    )
    inventory = ControllerPaletteInventory("inventory", (candidate,), tuple(proof))
    assert inventory.qualified_entries(Controller.CS1) == ()
    assert (
        "failed:baseline-hold"
        in inventory.mapping()["candidates"][0]["blocking_reasons"]
    )


def test_complete_proofs_create_only_controller_local_recipe() -> None:
    left = _candidate("same-id", Controller.CS1, "R20-A")
    right = _candidate("same-id", Controller.CS2, "R20-A")
    inventory = ControllerPaletteInventory(
        "inventory",
        (left, right),
        _complete_evidence(left) + _complete_evidence(right),
    )
    left_entries = inventory.quantization_entries(Controller.CS1)
    right_entries = inventory.quantization_entries(Controller.CS2)
    assert len(left_entries) == len(right_entries) == 1
    assert left_entries[0].candidate.controller is Controller.CS1
    assert right_entries[0].candidate.controller is Controller.CS2
    assert (
        left_entries[0].qualification_manifest_sha256
        != right_entries[0].qualification_manifest_sha256
    )
    assert inventory.mapping()["evidence_boundaries"]["controllers_pooled"] is False
    assert (
        inventory.mapping()["evidence_boundaries"][
            "legacy_history_palette_export_allowed"
        ]
        is False
    )


def test_history_lightness_recipe_uses_fresh_white_reconstruction() -> None:
    candidate = _candidate(
        "gray-from-history",
        Controller.CS1,
        "R20-A",
        reproducibility_mode=ReproducibilityMode.FRESH_WHITE_RECONSTRUCTION,
        target_repeat_count=1,
    )
    inventory = ControllerPaletteInventory(
        "inventory", (candidate,), _complete_evidence(candidate)
    )
    entries = inventory.qualified_entries(Controller.CS1)
    assert len(entries) == 1
    recipe = entries[0].to_multi_lut_recipe()
    assert recipe.identical_target_repeat_qualified is False
    assert recipe.fresh_white_reconstruction_qualified is True
    assert recipe.target_repeat_count == 1


def test_wrong_reproducibility_proof_cannot_qualify_history_recipe() -> None:
    candidate = _candidate(
        "gray-from-history",
        Controller.CS1,
        "R20-A",
        reproducibility_mode=ReproducibilityMode.FRESH_WHITE_RECONSTRUCTION,
        target_repeat_count=1,
    )
    evidence = (
        _evidence(candidate, QualificationEvidenceRole.IDENTICAL_TARGET_REPEAT),
        _evidence(candidate, QualificationEvidenceRole.LOCAL_HOLD),
        _evidence(candidate, QualificationEvidenceRole.FACTORY_WHITE_RECOVERY),
    )
    inventory = ControllerPaletteInventory("inventory", (candidate,), evidence)
    record = inventory.mapping()["candidates"][0]
    assert record["qualification_state"] == "COARSE_CANDIDATE_ONLY"
    assert "missing:fresh-white-reconstruction" in record["blocking_reasons"]
    assert "unexpected:identical-target-repeat" in record["blocking_reasons"]


def test_spatial_dither_cannot_become_a_qualified_colour() -> None:
    candidate = _candidate("dithered", Controller.CS1, "R20-A", dither=True)
    inventory = ControllerPaletteInventory(
        "inventory", (candidate,), _complete_evidence(candidate)
    )
    assert inventory.qualified_entries(Controller.CS1) == ()
    assert (
        "candidate:spatial-dithering-used"
        in inventory.mapping()["candidates"][0]["blocking_reasons"]
    )


def test_evidence_cannot_be_rebound_to_other_controller() -> None:
    candidate = _candidate("gray-1", Controller.CS1, "R20-A")
    proof = _evidence(candidate, QualificationEvidenceRole.LOCAL_HOLD)
    wrong_controller = ControllerPaletteEvidence(
        role=proof.role,
        controller=Controller.CS2,
        candidate_id=proof.candidate_id,
        lut_profile_id=proof.lut_profile_id,
        candidate_fingerprint_sha256=proof.candidate_fingerprint_sha256,
        artifact_sha256=proof.artifact_sha256,
        passed=proof.passed,
        single_pixel_pure=proof.single_pixel_pure,
        spatial_dithering_used=proof.spatial_dithering_used,
        observed_target_repeat_count=proof.observed_target_repeat_count,
        hold_code=6,
        baseline_hold_passed=True,
    )
    with pytest.raises(ControllerPaletteInventoryError, match="unknown candidate"):
        ControllerPaletteInventory("inventory", (candidate,), (wrong_controller,))


def _two_profile_inventory(
    *,
    include_cs2_cross: bool = True,
    cross_reuses_recipe_artifact: bool = False,
) -> ControllerPaletteInventory:
    candidates = tuple(
        _candidate(f"{profile}-swatch", controller, profile)
        for profile in ("A", "B")
        for controller in Controller
    )
    evidence = tuple(
        proof for candidate in candidates for proof in _complete_evidence(candidate)
    )
    cross = [_cross(Controller.CS1, "B", "A")]
    if include_cs2_cross:
        cross_label = None
        if cross_reuses_recipe_artifact:
            target = next(
                candidate
                for candidate in candidates
                if candidate.controller is Controller.CS2
                and candidate.lut_profile_id == "B"
            )
            cross_label = f"{target.controller}-{target.candidate_id}-local-hold"
        cross.append(_cross(Controller.CS2, "B", "A", artifact_label=cross_label))
    return ControllerPaletteInventory("inventory", candidates, evidence, tuple(cross))


def test_cross_lut_export_requires_each_controller_retention_proof() -> None:
    inventory = _two_profile_inventory(include_cs2_cross=False)
    with pytest.raises(
        ControllerPaletteInventoryError,
        match="missing controller-specific cross-profile",
    ):
        inventory.multi_lut_schedule_inputs(profile_order=("A", "B"))


def test_cross_profile_proof_must_be_independent_of_recipe_proofs() -> None:
    inventory = _two_profile_inventory(cross_reuses_recipe_artifact=True)
    with pytest.raises(ControllerPaletteInventoryError, match="not independent"):
        inventory.multi_lut_schedule_inputs(profile_order=("A", "B"))


def test_complete_inventory_bridges_to_existing_multi_lut_scheduler() -> None:
    inventory = _two_profile_inventory()
    bridge = inventory.multi_lut_schedule_inputs(profile_order=("A", "B"))
    assert bridge.profile_order == ("A", "B")
    assert len(bridge.recipes) == 4
    assert bridge.capabilities[1].retains_profile_ids == ("A",)
    indices = bytes(
        (
            bridge.recipe_index_by_controller_candidate[(Controller.CS1, "A-swatch")],
            bridge.recipe_index_by_controller_candidate[(Controller.CS1, "B-swatch")],
            bridge.recipe_index_by_controller_candidate[(Controller.CS2, "A-swatch")],
            bridge.recipe_index_by_controller_candidate[(Controller.CS2, "B-swatch")],
        )
    )
    schedule = build_multi_lut_hold_schedule(
        bridge.recipes,
        indices,
        bridge.capabilities,
        profile_order=bridge.profile_order,
        width=4,
        height=1,
    )
    assert schedule.profile_order == ("A", "B")
    assert len(bridge.qualification_manifest_sha256) == 64
