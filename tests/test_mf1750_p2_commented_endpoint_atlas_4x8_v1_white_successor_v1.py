from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from tools import mf1750_p2_commented_endpoint_atlas_4x8_v1_once as source_once
from tools import mf1750_p2_commented_endpoint_atlas_4x8_v1_pack as source_pack
from tools import (
    mf1750_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_audit as audit,
)
from tools import (
    mf1750_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_codegen as codegen,
)
from tools import (
    mf1750_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_once as once,
)
from tools import (
    mf1750_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_pack as pack,
)


def test_contract_accepts_only_exact_p2_c_ordinal1_complete() -> None:
    report = pack.build_report(verify_artifacts=True)
    source = source_pack.build_report()
    contract = report["contract"]
    assert contract["source_main_contract_id"] == pack.SOURCE_MAIN_CONTRACT_ID
    assert (
        contract["source_main_offline_build_file_sha256"]
        == pack.SOURCE_BUILD_REPORT_FILE_SHA256
    )
    assert contract["source_main_artifacts"] == pack.SOURCE_ARTIFACTS
    assert contract["accepted_source_ordinals"] == [1]
    assert contract["accepted_source_complete_actions"] == [
        {
            "ordinal": 1,
            "descriptor_id": source["actions"][0]["descriptor_id"],
            "action_id": source["actions"][0]["action_id"],
            "role": pack.SOURCE_MAIN_ROLE,
        }
    ]
    assert contract["source_fault_not_accepted"] is True
    assert contract["source_early_stop_not_accepted"] is True
    assert contract["main_campaign_resume_after_containment"] is False


def test_successor_is_fresh_one_action_factory_white_only() -> None:
    report = pack.build_report(verify_artifacts=True)
    contract = report["contract"]
    assert report["action"]["role"] == "FACTORY_OTP_WHITE_RECOVERY"
    assert contract["factory_otp"] is True
    assert contract["runtime_lut_write"] is False
    assert contract["custom_waveform_write"] is False
    assert contract["one_visible_refresh"] is True
    assert contract["full_busy_required"] is True
    assert contract["startup_refresh"] is False
    assert contract["retry"] is False
    assert contract["fallback"] is False
    assert contract["automatic_recovery"] is False
    assert contract["autochain"] is False
    assert pack.NVS_NAMESPACE != source_pack.NVS_NAMESPACE
    assert pack.BASE_ROUTE != source_pack.BASE_ROUTE
    assert report["contract_id"] != source_pack.build_report()["contract_id"]


def test_source_successor_and_compiled_identity_are_sealed() -> None:
    assert pack.source_artifacts_are_sealed() is True
    assert pack.artifacts_are_sealed() is True
    value = pack.dry_validate(require_sealed=True, verify_artifacts=True)
    assert value["result"] == "PASS"
    report = pack.build_report(verify_artifacts=True)
    assert pack.validate_compiled_identity_sources(report)["verified"] is True
    assert pack.validate_compiled_identity_binary(report)["counts"] == {
        "bin": 1,
        "elf": 1,
    }


def test_codegen_and_platformio_are_isolated_and_exact() -> None:
    report = pack.build_report()
    generated = codegen.render_sources(report)
    main = generated[codegen.MAIN_NAME].decode("utf-8")
    identity = generated[codegen.IDENTITY_NAME].decode("utf-8")
    assert codegen.NEW_MACRO in main
    assert codegen.OLD_MACRO not in main
    assert pack.TEST_ID in main
    assert '\\"accepted_source_complete_ordinals\\":[1]' in main
    assert '\\"source_main_completed_p2_commented_only\\":true' in main
    assert identity.count(pack.compiled_identity_marker(report)) == 1
    config = (
        pack.REPO_ROOT
        / "platformio.p2_commented_endpoint_atlas_4x8_v1_white_successor_v1.ini"
    ).read_text(encoding="utf-8")
    assert f"default_envs = {pack.ENVIRONMENT}" in config
    assert f"build_dir = .pio/{pack.BUILD_ROOT}" in config
    assert "MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY=1" in config
    assert "MF1750_OTP_WHITE_FOR_PROFILE_WF23_25=1" in config
    assert f"{codegen.NEW_MACRO}=1" in config


def test_runner_validation_is_offline_and_fixed_to_p2_c_output() -> None:
    value = once.dry_validate()
    assert value["result"] == "PASS"
    assert value["network_requests"] == 0
    assert value["hardware_accessed"] is False
    assert value["accepted_source_ordinals"] == [1]
    assert value["source_terminal_path"] == (
        ".test-output/hardware/MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1/"
        "action-01-commented-complete-position-balanced-4x8-endpoint-atlas.json"
    )
    binding = once._source_binding(pack.build_report())  # noqa: SLF001
    assert binding["source_main_completed_p2_commented_only"] is True
    assert binding["source_main_interrupted_or_completed_branch"] is False
    assert binding["source_main_resume_forbidden_after_containment"] is True


def test_runner_deep_gate_rejects_foreign_source_and_accepts_exact_shape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    action = tmp_path / "action-01.json"
    action.write_bytes(b"sealed-p2-c-placeholder")
    claim = tmp_path / "claims/p2-c.json"
    claim.parent.mkdir()
    claim.write_bytes(b"sealed-claim-placeholder")
    monkeypatch.setattr(once, "REPO_ROOT", tmp_path)
    monkeypatch.setitem(source_once.ACTION_OUTPUTS, 1, action)
    accepted = pack.build_report()["contract"]["accepted_source_complete_actions"][0]
    deep = {
        "terminal_state": "COMPLETE",
        "campaign_id": pack.SOURCE_CAMPAIGN_ID,
        "contract_id": pack.SOURCE_MAIN_CONTRACT_ID,
        "ordinal": 1,
        "descriptor_id": accepted["descriptor_id"],
        "action_id": accepted["action_id"],
        "role": pack.SOURCE_MAIN_ROLE,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "visible_refreshes": 1,
        "retry": False,
        "recovery": False,
        "autochain": False,
        "boot_nonce": "0123456789abcdef",
        "claim_path": "claims/p2-c.json",
        "claim_file_sha256": None,
        "claim_canonical_integrity_sha256": "2" * 64,
        "canonical_integrity_sha256": "4" * 64,
    }
    monkeypatch.setattr(source_once, "validate_terminal_evidence", lambda path: deep)
    result = once._validate_source_terminal(action, pack.build_report())  # noqa: SLF001
    assert result["source_success_claimed"] is True
    assert result["ordinal"] == 1
    assert result["claim"]["bytes"] == len(b"sealed-claim-placeholder")
    with pytest.raises(once.P2CommentedWhiteSuccessorRunnerError):
        once._validate_source_terminal(  # noqa: SLF001
            tmp_path / "foreign-action.json", pack.build_report()
        )


def test_cli_has_no_alternate_source_retry_recovery_or_autochain() -> None:
    source = (
        pack.REPO_ROOT
        / "tools/mf1750_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_once.py"
    ).read_text(encoding="utf-8")
    assert "--source-terminal-evidence" in source
    assert "--confirm-optional" not in source
    assert "--retry" not in source
    assert "--recovery" not in source
    assert "--autochain" not in source


def test_independent_audit_passes_without_claiming_live_execution() -> None:
    value = audit.audit()
    assert value["result"] == "PASS"
    assert value["offline_only"] is True
    assert value["hardware_accessed"] is False
    assert value["accepted_source_ordinals"] == [1]
    assert value["automatic_execution"] is False
    assert value["automatic_retry"] is False
    assert value["automatic_recovery"] is False
    assert value["automatic_chaining"] is False


def test_compatibility_identity_exports_match_compiled_report() -> None:
    report = pack.build_report(verify_artifacts=True)
    assert pack.CONTRACT_ID == report["contract_id"]
    assert pack.DESCRIPTOR_ID == report["descriptor_id"]
    assert pack.ACTION_ID == report["action_id"]
    assert pack.DESCRIPTOR_MARKER == pack.compiled_identity_marker(report)
    assert pack.DESCRIPTOR_MARKER in pack.identity_source_path().read_text(
        encoding="utf-8"
    )


def test_offline_build_seal_matches_exact_successor_and_source() -> None:
    path = (
        pack.REPO_ROOT
        / "docs/MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_"
        "WHITE_SUCCESSOR_V1_OFFLINE_BUILD_2026-09-03.json"
    )
    value = json.loads(path.read_text(encoding="utf-8"))
    report = pack.build_report(verify_artifacts=True)
    assert value["result"] == "PASS"
    assert value["offline_only"] is True
    assert value["contract_id"] == report["contract_id"]
    assert value["descriptor_id"] == report["descriptor_id"]
    assert value["action_id"] == report["action_id"]
    assert value["source_gate"]["source_main_offline_build_file_sha256"] == (
        pack.SOURCE_BUILD_REPORT_FILE_SHA256
    )
    assert value["successor_artifacts"]["firmware_bin"] == {
        "bytes": pack.FIRMWARE_BIN_BYTES,
        "sha256": pack.FIRMWARE_BIN_SHA256,
    }
    assert value["successor_artifacts"]["firmware_elf"] == {
        "bytes": pack.FIRMWARE_ELF_BYTES,
        "sha256": pack.FIRMWARE_ELF_SHA256,
    }


def test_wrong_source_action_is_not_silently_accepted() -> None:
    source = deepcopy(source_pack.build_report())
    source["actions"][0]["action_id"] = "f" * 64
    with pytest.raises(pack.P2CommentedWhiteSuccessorPackError):
        pack._source_action({"actions": []})  # noqa: SLF001
    assert source["actions"][0]["action_id"] != pack.SOURCE_MAIN_ACTION_ID
