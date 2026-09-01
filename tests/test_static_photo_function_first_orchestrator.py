from __future__ import annotations

import hashlib

import pytest

from host.static_photo.function_first_orchestrator import (
    FunctionFirstChainError,
    PhotoChainArtifacts,
    build_function_first_chain,
    export_function_first_chain,
    verify_function_first_chain,
)
from host.static_photo.lightness_family_plan import (
    FamilyGate,
    FamilyGateEvidence,
    GateResult,
    LightnessFamilySeed,
    LightnessMechanism,
    MechanismMaturity,
    StableEndpoint,
    build_lightness_family_plan,
)
from host.static_photo.multi_lut_hold_schedule import Controller


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _family_plan(*, ready: bool) -> dict:
    seed = LightnessFamilySeed(
        StableEndpoint("stable-blue", Controller.CS1, 3, "R20-A", _sha("endpoint")),
        LightnessMechanism(
            "lightness-v1",
            Controller.CS1,
            "R20-S",
            "R20-M",
            "R20-A",
            7,
            3,
            MechanismMaturity.PROVEN if ready else MechanismMaturity.CANDIDATE,
            _sha("mechanism"),
        ),
    )
    evidence = ()
    if ready:
        evidence = tuple(
            FamilyGateEvidence(
                Controller.CS1,
                seed.endpoint.endpoint_id,
                seed.mechanism.mechanism_id,
                gate,
                GateResult.PASS,
                _sha(gate.value),
            )
            for gate in tuple(FamilyGate)[1:]
        )
    return build_lightness_family_plan((seed,), evidence)


def test_pending_family_keeps_hue_search_deferred_and_requests_hold() -> None:
    chain = build_function_first_chain(_family_plan(ready=False))
    verify_function_first_chain(chain)

    assert chain["status"] == "OFFLINE_FUNCTION_PATH_IN_PROGRESS"
    assert chain["next_gate"]["capability"] == "STABLE_BASE_LIGHTNESS_FAMILY"
    assert chain["next_gate"]["family_gate"]["gate"] == "LOCAL_HOLD"
    assert chain["policy"]["broader_hue_enumeration"] == "DEFERRED"
    assert chain["execution_boundary"]["hardware_accessed"] is False


def test_one_ready_family_unlocks_palette_subset_not_more_hues() -> None:
    chain = build_function_first_chain(_family_plan(ready=True))

    assert chain["next_gate"] == {
        "capability": "USABLE_CONTROLLER_PALETTE",
        "operation": "BUILD_QUALIFIED_PALETTE_INVENTORY",
    }
    assert chain["stages"][0]["ready_family_count"] == 1
    assert chain["stages"][0]["unready_families_excluded"] is True
    assert chain["policy"]["all_families_required_before_photo_mapping"] is False
    assert chain["policy"]["broader_hue_enumeration"] == "DEFERRED"


def test_downstream_artifacts_advance_in_function_order() -> None:
    ready = _family_plan(ready=True)
    palette = PhotoChainArtifacts(qualified_palette_inventory_sha256=_sha("palette"))
    mapped = PhotoChainArtifacts(
        qualified_palette_inventory_sha256=_sha("palette"),
        photo_pixel_mapping_sha256=_sha("mapping"),
    )
    scheduled = PhotoChainArtifacts(
        qualified_palette_inventory_sha256=_sha("palette"),
        photo_pixel_mapping_sha256=_sha("mapping"),
        multi_lut_hold_schedule_sha256=_sha("schedule"),
    )

    assert build_function_first_chain(ready, palette)["next_gate"]["capability"] == (
        "PHOTO_PIXEL_MAPPING"
    )
    assert build_function_first_chain(ready, mapped)["next_gate"]["capability"] == (
        "MULTI_LUT_LOCAL_HOLD_SCHEDULE"
    )
    assert build_function_first_chain(ready, scheduled)["next_gate"]["capability"] == (
        "SOURCE_WHITE_AUTHORITY"
    )


def test_fixed_bundle_completes_framework_but_does_not_authorize_live() -> None:
    artifacts = PhotoChainArtifacts(
        qualified_palette_inventory_sha256=_sha("palette"),
        photo_pixel_mapping_sha256=_sha("mapping"),
        multi_lut_hold_schedule_sha256=_sha("schedule"),
        source_white_authority_sha256=_sha("source-white"),
        fixed_photo_execution_bundle_sha256=_sha("fixed-bundle"),
    )
    chain = build_function_first_chain(_family_plan(ready=True), artifacts)

    assert chain["status"] == "OFFLINE_FUNCTION_PATH_COMPLETE"
    assert chain["next_gate"]["capability"] == "FUNCTION_PATH_COMPLETE"
    assert chain["policy"]["broader_hue_enumeration"] == (
        "ELIGIBLE_FOR_SEPARATE_PLANNING"
    )
    assert chain["execution_boundary"]["live_authorization_generated"] is False
    assert chain["execution_boundary"]["hardware_action_ids"] == []


def test_dependency_skips_and_hash_reuse_fail_closed() -> None:
    ready = _family_plan(ready=True)
    with pytest.raises(FunctionFirstChainError, match="cannot precede"):
        build_function_first_chain(
            ready,
            PhotoChainArtifacts(photo_pixel_mapping_sha256=_sha("mapping")),
        )
    with pytest.raises(FunctionFirstChainError, match="source-white authority"):
        build_function_first_chain(
            ready,
            PhotoChainArtifacts(source_white_authority_sha256=_sha("white")),
        )
    with pytest.raises(FunctionFirstChainError, match="distinct SHA-256"):
        PhotoChainArtifacts(
            qualified_palette_inventory_sha256=_sha("same"),
            photo_pixel_mapping_sha256=_sha("same"),
        )


def test_no_ready_family_rejects_downstream_claims() -> None:
    with pytest.raises(FunctionFirstChainError, match="at least one PALETTE_READY"):
        build_function_first_chain(
            _family_plan(ready=False),
            PhotoChainArtifacts(qualified_palette_inventory_sha256=_sha("palette")),
        )


def test_integrity_tamper_and_non_lowercase_hash_are_rejected() -> None:
    chain = build_function_first_chain(_family_plan(ready=True))
    tampered = dict(chain)
    tampered["status"] = "OFFLINE_FUNCTION_PATH_COMPLETE"
    with pytest.raises(FunctionFirstChainError, match="canonical SHA-256 differs"):
        verify_function_first_chain(tampered)
    with pytest.raises(FunctionFirstChainError, match="64 lowercase hex"):
        PhotoChainArtifacts(qualified_palette_inventory_sha256=_sha("palette").upper())


def test_export_is_verified_and_non_overwriting(tmp_path) -> None:
    chain = build_function_first_chain(_family_plan(ready=True))
    output = export_function_first_chain(chain, tmp_path / "chain.json")
    assert output.is_file()
    with pytest.raises(FunctionFirstChainError, match="already exists"):
        export_function_first_chain(chain, output)
