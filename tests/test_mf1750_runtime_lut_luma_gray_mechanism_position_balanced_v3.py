from __future__ import annotations

from pathlib import Path

import pytest

from tools import (
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_audit as audit,
)
from tools import (
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_once as runner,
)
from tools import (
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_pack as pack,
)


def test_current_v3_white_source_chain_is_exact_and_camera_relative() -> None:
    source = pack.validate_source_gate()
    assert source["source_tuple"] == {
        "campaign_id": "EC5_STABLE_CODE0_LUMA_LATIN_V3_FACTORY_OTP_WHITE_SUCCESSOR_V1",
        "contract_id": "787c2898a841913ac009e0284a1f3680403cc77a05ec700cb17f1a4a08152377",
        "descriptor_id": "8e74da212546b89bfdeba9e6638b30a8d4aa75114d394387c3d2a3b73f8276e0",
        "action_id": "7d68be7197e6af89e6a7d500010160b6c11343ae5f92d990e1b982275fb5245f",
    }
    assert source["camera_relative_only"] is True
    assert source["absolute_white_or_uniformity_qualified"] is False
    assert source["qualified_level_count"] == 0
    assert source["retained_action_to_capture_continuity_proven"] is False
    assert source["review_id"] == audit.EXPECTED_REVIEW_ID
    assert set(source["bindings"]) == {
        "completed_action",
        "permanent_claim",
        "relay_protective_off",
        "capture_sidecar",
        "capture_jpeg",
        "camera_white_review",
    }


def test_sixteen_recipes_are_position_balanced_without_spatial_dither() -> None:
    report = pack.build_report()
    assert len(report["contract"]["recipes"]) == 16
    assert all(pack.CS1_RECIPE_AT_CELL.count(recipe) == 4 for recipe in range(16))
    assert pack.CS2_RECIPE_AT_CELL == tuple(reversed(pack.CS1_RECIPE_AT_CELL))
    assert report["contract"]["spatial_dither"] is False
    assert report["contract"]["spatial_mixing"] is False
    assert all(
        item["spatial_dither"] is False for item in report["contract"]["recipes"]
    )


def test_g1_g2_g3_and_optional_g4_mechanics_are_frozen() -> None:
    report = pack.build_report()
    actions = report["actions"]
    assert [item["global_header"] for item in actions] == [
        "active",
        "commented",
        "active",
        "active",
    ]
    assert [item["role"] for item in actions] == list(pack.ROLES)
    assert actions[2]["frame"] == actions[3]["frame"]
    assert actions[2]["cs1_dtm"] == actions[3]["cs1_dtm"]
    assert actions[2]["cs2_dtm"] == actions[3]["cs2_dtm"]
    assert actions[2]["action_id"] != actions[3]["action_id"]
    assert report["contract"]["required_core_action_ordinals"] == [1, 2, 3]
    assert report["contract"]["optional_repeat_action_ordinal"] == 4


def test_v3_campaign_build_route_nvs_claims_and_artifacts_are_isolated() -> None:
    result = pack.dry_validate(verify_artifacts=True)
    assert result["result"] == "PASS"
    assert result["compiled_identity_binary"]["counts"] == {"bin": 1, "elf": 1}
    assert pack.CONFIG.environment == "ec5_luma_gray_mpb_v3"
    assert pack.CONFIG.build_root == "b-luma-gray-mpb-v3"
    assert pack.CONFIG.nvs_namespace == "lgmpb_v3"
    assert pack.CONFIG.nvs_key == "cur_lgmpb3"
    assert pack.CONFIG.nvs_boot_key == "boot_lgmpb3"
    assert pack.CONFIG.base_route.endswith("position-balanced-v3")
    assert "position_balanced_v3_claims" in str(runner.base.runner.DEFAULT_CLAIMS)
    assert "20260901_V3" in str(runner.base.runner.DEFAULT_OUTPUT)
    assert result["contract_id"] != audit.OLD_V2_CONTRACT_ID
    assert not set(result["action_ids"]) & audit.OLD_V2_ACTION_IDS


def test_main_actions_have_no_white_action_and_no_embedded_recovery_chain() -> None:
    contract = pack.build_report()["contract"]
    assert all(
        item["driver_role"] != "White" for item in pack.build_report()["actions"]
    )
    assert contract["automatic_recovery"] is False
    assert contract["autochain"] is False
    assert contract["independent_factory_otp_white_successor_required"] is True


def test_run_requires_current_camera_relative_white_confirmation_before_request(
    tmp_path: Path,
) -> None:
    calls = 0

    def requester(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError((args, kwargs))

    with pytest.raises(runner.base.runner.RecheckError, match="camera-relative"):
        runner.run_once(
            "http://192.168.1.7",
            1,
            claims=tmp_path / "claims",
            output=tmp_path / "result.json",
            requester=requester,
            confirm_j2_on=True,
            confirm_gnd_normal=True,
            confirm_current_v3_camera_relative_white=False,
        )
    assert calls == 0


def test_bound_json_rejects_non_exact_allowlist_hash() -> None:
    binding = dict(pack.SOURCE_BINDINGS["camera_white_review"])
    binding["file_sha256"] = "0" * 64
    with pytest.raises(pack.LumaGrayMechanismV3PackError, match="file binding differs"):
        pack._read_bound_json(binding, "tampered review")  # noqa: SLF001


def test_independent_audit_reports_fresh_white_successor_present() -> None:
    result = audit.audit(verify_artifacts=True)
    assert result["result"] == "PASS"
    assert result["main_action_sequence_embeds_white_recovery"] is False
    assert result["independent_white_successor_present"] is True
    assert result["remaining_gate"] is None
