from __future__ import annotations

import hashlib
import json

import pytest

from host.static_photo import (
    FamilyGate,
    FamilyGateEvidence,
    GateResult,
    LightnessFamilyPlanError,
    LightnessFamilySeed,
    LightnessMechanism,
    MechanismMaturity,
    StableEndpoint,
    build_lightness_family_plan,
    export_lightness_family_plan,
    verify_lightness_family_plan,
)
from host.static_photo.multi_lut_hold_schedule import Controller


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _seed(
    controller: Controller = Controller.CS1,
    *,
    endpoint_id: str = "stable-blue",
    mechanism_id: str = "history-lightness-v1",
    maturity: MechanismMaturity = MechanismMaturity.CANDIDATE,
    target_code: int = 3,
    target_profile: str = "R20-A",
) -> LightnessFamilySeed:
    endpoint = StableEndpoint(
        endpoint_id=endpoint_id,
        controller=controller,
        code=target_code,
        profile_id=target_profile,
        evidence_sha256=_sha(f"endpoint-{controller.value}-{endpoint_id}"),
    )
    mechanism = LightnessMechanism(
        mechanism_id=mechanism_id,
        controller=controller,
        source_profile_id="R20-SOURCE",
        middle_profile_id="R20-MIDDLE",
        target_profile_id=target_profile,
        source_code=7,
        target_code=target_code,
        maturity=maturity,
        evidence_sha256=_sha(
            f"mechanism-{controller.value}-{endpoint_id}-{mechanism_id}"
        ),
    )
    return LightnessFamilySeed(endpoint, mechanism)


def _gates(
    seed: LightnessFamilySeed,
    *,
    result_by_gate: dict[FamilyGate, GateResult] | None = None,
) -> tuple[FamilyGateEvidence, ...]:
    values = []
    for gate in tuple(FamilyGate)[1:]:
        result = (result_by_gate or {}).get(gate, GateResult.PASS)
        values.append(
            FamilyGateEvidence(
                controller=seed.endpoint.controller,
                endpoint_id=seed.endpoint.endpoint_id,
                mechanism_id=seed.mechanism.mechanism_id,
                gate=gate,
                result=result,
                evidence_sha256=_sha(f"{seed.family_id}-{gate.value}-{result.value}"),
            )
        )
    return tuple(values)


def test_unhit_mechanism_freezes_position_balanced_template_only() -> None:
    seed = _seed(maturity=MechanismMaturity.NO_HIT_YET)
    plan = build_lightness_family_plan((seed,))
    verify_lightness_family_plan(plan)

    assert plan["status"] == "PREPARED_NOT_LIVE_ADMITTED"
    assert plan["photo_schedule_admission"]["admitted"] is False
    assert plan["execution_boundary"]["live_authorization_generated"] is False
    assert plan["execution_boundary"]["executable_hardware_plan_generated"] is False
    assert plan["families"][0]["gates"][0]["status"] == "NO_HIT_YET"
    assert all(gate["status"] == "BLOCKED" for gate in plan["families"][0]["gates"][1:])

    batch = plan["batches"][0]
    assert batch["controller"] == "CS1"
    assert batch["recipe_count"] == 8
    assert batch["replicas_per_recipe"] == 4
    assert len(batch["cells"]) == 32
    assert batch["hardware_action_specification"] is None
    assert batch["hardware_authorization"] is None
    for middle_code in range(8):
        cells = [cell for cell in batch["cells"] if cell["middle_code"] == middle_code]
        assert len(cells) == 4
        assert {cell["row"] for cell in cells} == {0, 1, 2, 3}
        assert {(cell["vertical_half"], cell["horizontal_half"]) for cell in cells} == {
            ("TOP", "LEFT"),
            ("TOP", "RIGHT"),
            ("BOTTOM", "LEFT"),
            ("BOTTOM", "RIGHT"),
        }


def test_candidate_stays_prepared_until_every_gate_and_proof_exist() -> None:
    seed = _seed(maturity=MechanismMaturity.CANDIDATE)
    plan = build_lightness_family_plan((seed,))
    states = plan["families"][0]["gates"]

    assert states[0]["status"] == "PASS"
    assert states[1]["gate"] == "LOCAL_HOLD"
    assert states[1]["status"] == "PENDING"
    assert all(state["status"] == "BLOCKED" for state in states[2:])
    assert plan["status"] == "PREPARED_NOT_LIVE_ADMITTED"
    assert plan["qualification_boundary"]["automatic_new_colour_claim"] is False
    assert plan["qualification_boundary"]["automatic_gray_level_claim"] is False


def test_gate_evidence_cannot_skip_an_earlier_gate() -> None:
    seed = _seed(maturity=MechanismMaturity.CANDIDATE)
    skipped = FamilyGateEvidence(
        controller=Controller.CS1,
        endpoint_id=seed.endpoint.endpoint_id,
        mechanism_id=seed.mechanism.mechanism_id,
        gate=FamilyGate.FRESH_WHITE_RECONSTRUCTION,
        result=GateResult.PASS,
        evidence_sha256=_sha("skipped-fresh-white"),
    )
    with pytest.raises(LightnessFamilyPlanError, match="before LOCAL_HOLD passed"):
        build_lightness_family_plan((seed,), (skipped,))


def test_proven_mechanism_with_all_gates_is_photo_ready_but_not_live_authorized() -> (
    None
):
    seed = _seed(maturity=MechanismMaturity.PROVEN)
    plan = build_lightness_family_plan((seed,), _gates(seed))

    assert plan["status"] == "PALETTE_READY"
    assert plan["families"][0]["status"] == "PALETTE_READY"
    assert [gate["status"] for gate in plan["families"][0]["gates"]] == ["PASS"] * 6
    assert plan["photo_schedule_admission"]["admitted"] is True
    assert (
        plan["photo_schedule_admission"]["requires_separate_hardware_authority"] is True
    )
    assert plan["photo_schedule_admission"]["hardware_action_ids"] == []
    assert plan["execution_boundary"]["live_admitted"] is False
    assert plan["execution_boundary"]["live_authorization_generated"] is False
    assert plan["batches"][0]["photo_schedule_eligible"] is True


def test_one_ready_family_unlocks_only_that_offline_palette_subset() -> None:
    ready = _seed(
        Controller.CS1,
        endpoint_id="ready-blue",
        mechanism_id="ready-mechanism",
        maturity=MechanismMaturity.PROVEN,
    )
    pending = _seed(
        Controller.CS2,
        endpoint_id="pending-green",
        mechanism_id="pending-mechanism",
        maturity=MechanismMaturity.CANDIDATE,
        target_code=4,
    )
    plan = build_lightness_family_plan((pending, ready), _gates(ready))

    assert plan["status"] == "PARTIAL_PALETTE_READY"
    assert plan["photo_schedule_admission"]["admitted"] is True
    assert plan["photo_schedule_admission"]["ready_family_count"] == 1
    assert plan["photo_schedule_admission"]["ready_family_ids"] == [ready.family_id]
    assert plan["photo_schedule_admission"]["unready_families_excluded"] is True
    assert (
        plan["gate_state_machine"]["all_families_must_pass_before_photo_scheduling"]
        is False
    )
    by_family = {item["family_id"]: item for item in plan["families"]}
    assert by_family[ready.family_id]["photo_schedule_admitted"] is True
    assert by_family[pending.family_id]["photo_schedule_admitted"] is False


def test_candidate_cannot_claim_palette_ready() -> None:
    seed = _seed(maturity=MechanismMaturity.CANDIDATE)
    with pytest.raises(LightnessFamilyPlanError, match="unproven mechanism"):
        build_lightness_family_plan((seed,), _gates(seed))


def test_failed_gate_blocks_later_gates_and_photo_schedule() -> None:
    seed = _seed(maturity=MechanismMaturity.PROVEN)
    local_fail = FamilyGateEvidence(
        controller=seed.endpoint.controller,
        endpoint_id=seed.endpoint.endpoint_id,
        mechanism_id=seed.mechanism.mechanism_id,
        gate=FamilyGate.LOCAL_HOLD,
        result=GateResult.FAIL,
        evidence_sha256=_sha("local-hold-fail"),
    )
    plan = build_lightness_family_plan((seed,), (local_fail,))

    gates = plan["families"][0]["gates"]
    assert gates[1]["status"] == "FAIL"
    assert all(item["status"] == "BLOCKED" for item in gates[2:])
    assert plan["photo_schedule_admission"]["admitted"] is False


def test_cs1_and_cs2_are_separate_batches_and_never_pooled() -> None:
    cs1 = _seed(
        Controller.CS1,
        endpoint_id="stable-green",
        mechanism_id="mechanism-cs1",
    )
    cs2 = _seed(
        Controller.CS2,
        endpoint_id="stable-green",
        mechanism_id="mechanism-cs2",
    )
    plan = build_lightness_family_plan((cs2, cs1))

    assert [batch["controller"] for batch in plan["batches"]] == ["CS1", "CS2"]
    assert all(batch["controllers_merged"] is False for batch in plan["batches"])
    assert all(batch["controller_local_only"] is True for batch in plan["batches"])
    assert plan["qualification_boundary"]["controllers_pooled"] is False
    assert plan["qualification_boundary"]["cs1_cs2_batches_merged"] is False


def test_stable_endpoint_must_match_mechanism_controller_profile_and_code() -> None:
    good = _seed()
    wrong_controller = LightnessMechanism(
        mechanism_id="wrong-controller",
        controller=Controller.CS2,
        source_profile_id="S",
        middle_profile_id="M",
        target_profile_id=good.endpoint.profile_id,
        source_code=7,
        target_code=good.endpoint.code,
        maturity=MechanismMaturity.CANDIDATE,
        evidence_sha256=_sha("wrong-controller"),
    )
    with pytest.raises(LightnessFamilyPlanError, match="controllers must match"):
        LightnessFamilySeed(good.endpoint, wrong_controller)

    wrong_target = LightnessMechanism(
        mechanism_id="wrong-target",
        controller=Controller.CS1,
        source_profile_id="S",
        middle_profile_id="M",
        target_profile_id="OTHER",
        source_code=7,
        target_code=4,
        maturity=MechanismMaturity.CANDIDATE,
        evidence_sha256=_sha("wrong-target"),
    )
    with pytest.raises(LightnessFamilyPlanError, match="profile must match"):
        LightnessFamilySeed(good.endpoint, wrong_target)


def test_spatial_dither_and_non_lowercase_hash_are_rejected() -> None:
    with pytest.raises(LightnessFamilyPlanError, match="spatial dithering"):
        StableEndpoint(
            endpoint_id="dithered",
            controller=Controller.CS1,
            code=1,
            profile_id="R20",
            evidence_sha256=_sha("dithered"),
            spatial_dithering_used=True,
        )
    with pytest.raises(LightnessFamilyPlanError, match="lowercase hex"):
        StableEndpoint(
            endpoint_id="uppercase",
            controller=Controller.CS1,
            code=1,
            profile_id="R20",
            evidence_sha256=_sha("uppercase").upper(),
        )


def test_gate_evidence_requires_exact_controller_family_binding() -> None:
    seed = _seed(maturity=MechanismMaturity.PROVEN)
    foreign = FamilyGateEvidence(
        controller=Controller.CS2,
        endpoint_id=seed.endpoint.endpoint_id,
        mechanism_id=seed.mechanism.mechanism_id,
        gate=FamilyGate.LOCAL_HOLD,
        result=GateResult.PASS,
        evidence_sha256=_sha("foreign"),
    )
    with pytest.raises(LightnessFamilyPlanError, match="exact family seed"):
        build_lightness_family_plan((seed,), (foreign,))


def test_plan_is_canonical_and_input_order_independent() -> None:
    cs1 = _seed(Controller.CS1, endpoint_id="blue", mechanism_id="m-blue")
    cs2 = _seed(Controller.CS2, endpoint_id="red", mechanism_id="m-red")
    first = build_lightness_family_plan((cs1, cs2))
    second = build_lightness_family_plan((cs2, cs1))

    assert first == second
    assert (
        first["integrity"]["canonical_sha256"]
        == second["integrity"]["canonical_sha256"]
    )

    tampered = json.loads(json.dumps(first))
    tampered["batches"][0]["recipes"][0]["target"]["code"] = 6
    with pytest.raises(LightnessFamilyPlanError, match="canonical SHA-256 differs"):
        verify_lightness_family_plan(tampered)


def test_export_writes_verified_json_and_refuses_implicit_overwrite(tmp_path) -> None:
    plan = build_lightness_family_plan((_seed(),))
    output = tmp_path / "docs" / "lightness-family-plan.json"

    assert export_lightness_family_plan(plan, output) == output
    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded == plan
    verify_lightness_family_plan(loaded)
    with pytest.raises(LightnessFamilyPlanError, match="already exists"):
        export_lightness_family_plan(plan, output)


def test_screen_cannot_be_rebound_as_post_screen_evidence() -> None:
    seed = _seed()
    with pytest.raises(LightnessFamilyPlanError, match="cannot be supplied again"):
        FamilyGateEvidence(
            controller=seed.endpoint.controller,
            endpoint_id=seed.endpoint.endpoint_id,
            mechanism_id=seed.mechanism.mechanism_id,
            gate=FamilyGate.SCREEN,
            result=GateResult.PASS,
            evidence_sha256=_sha("screen-duplicate"),
        )
