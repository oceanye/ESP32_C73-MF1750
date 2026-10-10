from __future__ import annotations

from pathlib import Path

import pytest

from tools import mf1750_lightness_hold_function_chain_v1_once as source_once
from tools import mf1750_lightness_hold_function_chain_v1_pack as source_pack
from tools import mf1750_lightness_hold_function_chain_v1_white_successor_v1_once as once
from tools import mf1750_lightness_hold_function_chain_v1_white_successor_v1_pack as pack


def test_contract_is_independent_post_h2_factory_white() -> None:
    report = pack.build_report(verify_artifacts=True)
    contract = report["contract"]
    source = source_pack.build_report()
    assert contract["accepted_source_ordinals"] == [5]
    assert contract["accepted_source_complete_actions"] == [
        {
            "ordinal": 5,
            "descriptor_id": source["actions"][4]["descriptor_id"],
            "action_id": source["actions"][4]["action_id"],
            "role": "H2_COMMENTED_CODE6_BOTTOM_PROBE_HOLD_GRID_AND_H1",
        }
    ]
    assert contract["source_fault_not_accepted"] is True
    assert contract["source_early_stop_not_accepted"] is True
    assert contract["factory_otp"] is True
    assert contract["runtime_lut_write"] is False
    assert contract["one_visible_refresh"] is True
    assert contract["autochain"] is False
    assert contract["nvs_namespace"] != source_pack.NVS_NAMESPACE
    assert contract["base_route"] != source_pack.BASE_ROUTE
    assert report["contract_id"] != source["contract_id"]


def test_compiled_identity_and_artifact_marker_are_sealed() -> None:
    validation = pack.dry_validate(verify_artifacts=True)
    assert validation["result"] == "PASS"
    assert validation["accepted_source_ordinals"] == [5]
    assert validation["compiled_identity_binary"]["counts"] == {"bin": 1, "elf": 1}
    assert pack.FIRMWARE_BIN.stat().st_size == pack.FIRMWARE_BIN_BYTES
    assert pack.FIRMWARE_ELF.stat().st_size == pack.FIRMWARE_ELF_BYTES


def test_platformio_environment_is_isolated_and_factory_otp_only() -> None:
    path = pack.REPO_ROOT / "platformio.lightness_hold_function_chain_v1_white_successor_v1.ini"
    text = path.read_text(encoding="utf-8")
    assert f"default_envs = {pack.ENVIRONMENT}" in text
    assert f"build_dir = .pio/{pack.BUILD_ROOT}" in text
    assert "+<ec5_lightness_hold_function_chain_v1_white_successor_v1_main.cpp>" in text
    assert "MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY=1" in text
    assert "MF1750_OTP_WHITE_FOR_PROFILE_WF23_25=1" in text
    assert "MF1750_LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_WHITE_SUCCESSOR_V1_BUILD=1" in text


def test_device_source_binding_is_exact_h2_complete_only() -> None:
    assert once.DEVICE_SOURCE_BINDING == {
        "source_campaign_id": pack.SOURCE_CAMPAIGN_ID,
        "source_main_contract_id": pack.SOURCE_MAIN_CONTRACT_ID,
        "source_main_contract_exact_binding": True,
        "source_main_device_enforced_same_boot": True,
        "source_main_direct_exact_post_resume_after_reboot": False,
        "source_main_nvs_boot_key": source_pack.NVS_BOOT_KEY,
        "accepted_source_complete_ordinals": [5],
        "source_terminal_evidence_required_before_any_live_request": True,
        "main_campaign_resume_after_containment": False,
        "containment_terminal_for_source_campaign": True,
        "source_main_interrupted_or_completed_branch": False,
        "source_main_completed_h2_only": True,
        "source_main_resume_forbidden_after_containment": True,
        "relay_off_required_before_containment": True,
    }
    source = (
        pack.REPO_ROOT
        / "src/ec5_lightness_hold_function_chain_v1_white_successor_v1_main.cpp"
    ).read_text(encoding="utf-8")
    assert '\\"accepted_source_complete_ordinals\\":[5]' in source
    assert '\\"source_main_interrupted_or_completed_branch\\":false' in source
    assert '\\"source_main_completed_h2_only\\":true' in source


def test_successor_source_gate_accepts_only_fixed_h2_complete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixed = tmp_path / "action-05.json"
    fixed.write_bytes(b"sealed-h2-placeholder")
    monkeypatch.setitem(source_once.ACTION_OUTPUTS, 5, fixed)
    monkeypatch.setattr(once, "_repo_relative", lambda path: Path(path).name)
    accepted = pack.build_report()["contract"]["accepted_source_complete_actions"][0]
    deep = {
        "terminal_state": "COMPLETE",
        "campaign_id": pack.SOURCE_CAMPAIGN_ID,
        "contract_id": pack.SOURCE_MAIN_CONTRACT_ID,
        "ordinal": 5,
        "descriptor_id": accepted["descriptor_id"],
        "action_id": accepted["action_id"],
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 5,
        "visible_refreshes": 1,
        "source_success_claimed": True,
        "boot_nonce": "0123456789abcdef",
        "claim_path": ".test-output/fixed-claim.json",
        "claim_bytes": 123,
        "claim_file_sha256": "1" * 64,
        "claim_canonical_integrity_sha256": "2" * 64,
        "canonical_integrity_sha256": "3" * 64,
    }
    monkeypatch.setattr(source_once, "validate_terminal_evidence", lambda path: deep)
    result = once._validate_source_terminal(fixed)  # noqa: SLF001
    assert result["ordinal"] == 5
    assert result["terminal_state"] == "COMPLETE"
    with pytest.raises(once.WhiteSuccessorV1Error):
        once._validate_source_terminal(tmp_path / "action-04.json")  # noqa: SLF001
    with pytest.raises(once.WhiteSuccessorV1Error):
        once._validate_source_terminal(  # noqa: SLF001
            fixed, confirm_optional_l4_source=True
        )


def test_main_terminal_validator_rejects_any_nonfixed_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(source_once.pack, "validate_source_authority", lambda **kwargs: {})
    monkeypatch.setattr(source_once, "_verify_local_artifacts", lambda: {})
    with pytest.raises(source_once.base.runner.RecheckError):
        source_once.validate_terminal_evidence(tmp_path / "not-action-05.json")


def test_cli_has_no_early_stop_or_alternate_source_selector() -> None:
    parser_source = (
        pack.REPO_ROOT
        / "tools/mf1750_lightness_hold_function_chain_v1_white_successor_v1_once.py"
    ).read_text(encoding="utf-8")
    assert "--confirm-optional-l4-source" not in parser_source
    assert "--source-terminal-evidence" in parser_source
    assert once._source_terminal_paths() == {5: source_once.ACTION_OUTPUTS[5].resolve()}  # noqa: SLF001
