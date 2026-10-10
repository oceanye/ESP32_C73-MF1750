from __future__ import annotations

from tools import mf1750_ec5_u07t_identity as identity


def test_frozen_action_is_complete_canonical_preimage_hash() -> None:
    assert identity.action_id() == identity.FROZEN_ACTION_ID
    assert identity.FROZEN_ACTION_ID == (
        "303bb39e496f39caef782aadacb0d63e6d4f9b42df550d4c799a4248a8041310"
    )
    assert identity.derive_action_id(identity.action_identity_preimage()) == (
        identity.FROZEN_ACTION_ID
    )


def test_u07t_is_explicitly_technical_and_not_formal_u07() -> None:
    preimage = identity.action_identity_preimage()
    assert preimage["classification"] == "TECHNICAL_DESCRIPTIVE_NOT_QUALIFIED"
    assert preimage["formal_u07_action_id"] == (
        "8f427d1262afb4d4d430033451cf7afc6f319b172c836fcdf1e16a02a13746ae"
    )
    assert identity.FROZEN_ACTION_ID != identity.FORMAL_U07_ACTION_ID
    assert preimage["formal_u07_action_must_remain_unclaimed"] is True
    assert (
        preimage["formal_u07_claim_absence_checked_before_and_after_action"]
        is True
    )
    assert identity.EXECUTION_ELIGIBLE is False
    assert "intervening_u04_u05_compare" in identity.INVALIDATION_REASON


def test_nvs_contract_isolated_from_formal_u07() -> None:
    contract = identity.nvs_contract()
    assert contract == {
        "formal_u04": {
            "namespace": "mf1750_ec5v2",
            "key": "u04v2_phase",
            "expected_present": True,
            "expected_phase": 2,
            "read_only": True,
        },
        "formal_u07": {
            "namespace": "mf1750_ec5v2",
            "key": "u07v2_phase",
            "expected_present": False,
            "expected_phase": 0,
            "read_only": True,
        },
        "active": {
            "namespace": "mf1750_ec5t",
            "key": "u07t_phase",
            "expected_present": False,
            "expected_phase": 0,
            "read_only": False,
        },
    }


def test_preimage_binds_exact_short_hold_skip_and_white_evidence() -> None:
    preimage = identity.action_identity_preimage()
    assert preimage["u04_five_minute_observation_required"] is True
    assert preimage["u04_thirty_minute_observation_expected_status"] == (
        "SKIPPED_BY_OPERATOR"
    )
    assert preimage["formal_u07_review_gate_expected_satisfied"] is False
    assert preimage["after_u04_white_expected_outcome"] == "complete_pass"
    assert preimage["after_u04_white_expected_decision"] == (
        "VISUAL_AND_ELECTRICAL_PASS"
    )
    for key in (
        "corrected_u04_result_file_sha256",
        "corrected_u04_claim_file_sha256",
        "u04_short_hold_file_sha256",
        "after_u04_white_result_file_sha256",
        "after_u04_white_claim_file_sha256",
        "after_u04_white_observation_file_sha256",
    ):
        assert len(preimage[key]) == 64


def test_variant_carries_no_formal_qualification_claim() -> None:
    variant = identity.variant()
    assert variant["candidate_id"] == "U07T"
    assert variant["candidate_code"] == 7
    assert variant["classification"] == "TECHNICAL_DESCRIPTIVE_NOT_QUALIFIED"
    assert variant["action_id"] == identity.FROZEN_ACTION_ID
    assert variant["frame_sha256"] == identity.FRAME_SHA256
    assert variant["dtm_sha256"] == identity.DTM_SHA256
