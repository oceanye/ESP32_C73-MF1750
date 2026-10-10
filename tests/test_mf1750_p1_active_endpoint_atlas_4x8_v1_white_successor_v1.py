from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from tools import mf1750_p1_active_endpoint_atlas_4x8_v1_pack as source_pack
from tools import (
    mf1750_p1_active_endpoint_atlas_4x8_v1_white_successor_v1_codegen as codegen,
)
from tools import (
    mf1750_p1_active_endpoint_atlas_4x8_v1_white_successor_v1_pack as pack,
)
from tools import mf1750_p1_active_endpoint_atlas_4x8_v1_once as source_once
from tools import (
    mf1750_p1_active_endpoint_atlas_4x8_v1_white_successor_v1_once as once,
)
from tools import (
    mf1750_p1_active_endpoint_atlas_4x8_v1_white_successor_v1_audit as audit,
)


def test_contract_accepts_only_exact_p1_ordinal1_complete() -> None:
    report = pack.build_report(verify_artifacts=True)
    source = source_pack.build_report()
    contract = report["contract"]
    assert contract["source_main_contract_id"] == pack.SOURCE_MAIN_CONTRACT_ID
    assert contract["source_main_artifacts"] == pack.SOURCE_ARTIFACTS
    assert contract["accepted_source_ordinals"] == [1]
    assert contract["accepted_source_complete_actions"] == [
        {
            "ordinal": 1,
            "descriptor_id": source["actions"][0]["descriptor_id"],
            "action_id": source["actions"][0]["action_id"],
            "role": source_pack.ROLE,
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
    assert contract["startup_refresh"] is False
    assert contract["retry"] is False
    assert contract["fallback"] is False
    assert contract["automatic_recovery"] is False
    assert contract["autochain"] is False
    assert pack.NVS_NAMESPACE != source_pack.NVS_NAMESPACE
    assert pack.BASE_ROUTE != source_pack.BASE_ROUTE
    assert report["contract_id"] != source_pack.build_report()["contract_id"]


def test_source_and_successor_artifacts_are_exactly_sealed() -> None:
    assert pack.source_artifacts_are_sealed() is True
    assert pack.artifacts_are_sealed() is True
    validation = pack.dry_validate(require_sealed=True, verify_artifacts=True)
    assert validation["result"] == "PASS"
    assert validation["accepted_source_ordinals"] == [1]
    assert validation["source_artifacts_sealed"] is True
    assert validation["successor_artifacts_sealed"] is True


def test_generated_identity_and_main_bind_source_hashes() -> None:
    report = pack.build_report(verify_artifacts=True)
    verified = pack.validate_compiled_identity_sources(report)
    assert verified["verified"] is True
    identity = pack.identity_source_path().read_text(encoding="utf-8")
    main = pack.main_source_path().read_text(encoding="utf-8")
    assert pack.SOURCE_MAIN_CONTRACT_ID in identity
    assert pack.SOURCE_ARTIFACTS["bin_sha256"] in identity
    assert pack.SOURCE_ARTIFACTS["elf_sha256"] in identity
    assert '\\"accepted_source_complete_ordinals\\":[1]' in main
    assert '\\"source_main_completed_p1_only\\":true' in main
    assert pack.BASE_ROUTE in main


def test_codegen_is_frozen_to_p1_ordinal1_and_isolated_platformio() -> None:
    report = pack.build_report()
    generated = codegen.render_sources(report)
    main = generated[codegen.MAIN_NAME].decode("utf-8")
    assert codegen.NEW_MACRO in main
    assert codegen.OLD_MACRO not in main
    assert pack.TEST_ID in main
    assert '\\"accepted_source_complete_ordinals\\":[1]' in main
    config = (
        pack.REPO_ROOT
        / "platformio.p1_active_endpoint_atlas_4x8_v1_white_successor_v1.ini"
    ).read_text(encoding="utf-8")
    assert f"default_envs = {pack.ENVIRONMENT}" in config
    assert f"build_dir = .pio/{pack.BUILD_ROOT}" in config
    assert "MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY=1" in config
    assert "MF1750_OTP_WHITE_FOR_PROFILE_WF23_25=1" in config
    assert f"{codegen.NEW_MACRO}=1" in config


def test_pack_rejects_wrong_source_role_or_contract() -> None:
    source = source_pack.build_report()
    wrong_role = deepcopy(source)
    wrong_role["actions"][0]["role"] = "FOREIGN_ROLE"
    with pytest.raises(pack.P1WhiteSuccessorPackError):
        pack._report(wrong_role, pack.SOURCE_ARTIFACTS)  # noqa: SLF001
    wrong_contract = deepcopy(source)
    wrong_contract["contract_id"] = "f" * 64
    with pytest.raises(pack.P1WhiteSuccessorPackError):
        pack._report(wrong_contract, pack.SOURCE_ARTIFACTS)  # noqa: SLF001


def test_artifact_paths_are_inside_isolated_build_root() -> None:
    expected = Path(".pio") / pack.BUILD_ROOT / pack.ENVIRONMENT
    assert pack.FIRMWARE_BIN.relative_to(pack.REPO_ROOT).parent == expected
    assert pack.FIRMWARE_ELF.relative_to(pack.REPO_ROOT).parent == expected


def test_runner_validation_is_offline_and_exact_source_path() -> None:
    value = once.dry_validate()
    assert value["result"] == "PASS"
    assert value["network_requests"] == 0
    assert value["hardware_accessed"] is False
    assert value["accepted_source_ordinals"] == [1]
    assert value["source_terminal_path"] == (
        ".test-output/hardware/MF1750_P1_COMPLETE_ACTIVE_ENDPOINT_20260901_V1/"
        "action-01-active-complete-position-balanced-4x8-endpoint-atlas.json"
    )
    binding = once._source_binding(pack.build_report())  # noqa: SLF001
    assert binding["source_main_completed_p1_only"] is True
    assert binding["source_main_interrupted_or_completed_branch"] is False
    assert binding["source_main_resume_forbidden_after_containment"] is True


def test_runner_deep_gate_accepts_only_fixed_complete_p1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    action = tmp_path / "action-01.json"
    action.write_bytes(b"sealed-p1-placeholder")
    claim = tmp_path / "claims/p1.json"
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
        "role": pack.SOURCE_ROLE,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "visible_refreshes": 1,
        "source_history_actions": 0,
        "middle_history_actions": 0,
        "identical_target_repeat_actions": 0,
        "retry": False,
        "recovery": False,
        "autochain": False,
        "boot_nonce": "0123456789abcdef",
        "claim_path": "claims/p1.json",
        "claim_file_sha256": "1" * 64,
        "claim_canonical_integrity_sha256": "2" * 64,
        "file_sha256": "3" * 64,
        "canonical_integrity_sha256": "4" * 64,
    }
    monkeypatch.setattr(source_once, "validate_terminal_evidence", lambda path: deep)
    result = once._validate_source_terminal(action, pack.build_report())  # noqa: SLF001
    assert result["source_success_claimed"] is True
    assert result["ordinal"] == 1
    assert result["claim"]["bytes"] == len(b"sealed-claim-placeholder")
    with pytest.raises(once.P1WhiteSuccessorRunnerError):
        once._validate_source_terminal(  # noqa: SLF001
            tmp_path / "foreign-action.json", pack.build_report()
        )


def test_runner_cli_has_no_alternate_source_retry_or_recovery() -> None:
    parser_source = (
        pack.REPO_ROOT
        / "tools/mf1750_p1_active_endpoint_atlas_4x8_v1_white_successor_v1_once.py"
    ).read_text(encoding="utf-8")
    assert "--source-terminal-evidence" in parser_source
    assert "--confirm-optional-l4-source" not in parser_source
    assert "--retry" not in parser_source
    assert "--recovery" not in parser_source


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


def test_legacy_delegate_identity_exports_match_compiled_report() -> None:
    report = pack.build_report(verify_artifacts=True)
    assert pack.CONTRACT_ID == report["contract_id"]
    assert pack.DESCRIPTOR_ID == report["descriptor_id"]
    assert pack.ACTION_ID == report["action_id"]
    assert pack.DESCRIPTOR_MARKER == pack.compiled_identity_marker(report)
    assert pack.DESCRIPTOR_MARKER in pack.identity_source_path().read_text(
        encoding="utf-8"
    )


def test_v2_host_paths_preserve_failed_v1_diagnostic() -> None:
    v1 = (
        pack.REPO_ROOT
        / ".test-output/hardware/"
        "MF1750_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_WHITE_20260901_V1/"
        "j2-off-diagnostic.json"
    )
    assert once.DEFAULT_OUTPUT.name.endswith("WHITE_20260901_V2")
    assert once.DIAGNOSTIC_OUTPUT.parent == once.DEFAULT_OUTPUT
    assert once.ACTION_OUTPUT.parent == once.DEFAULT_OUTPUT
    assert "white_successor_v2_claims" in once.DEFAULT_CLAIMS.name
    if v1.is_file():
        value = json.loads(v1.read_text(encoding="utf-8"))
        assert value["outcome"] == "j2_off_diagnostic_failed_no_claim"
        assert value["network"] == {"get": 4, "post": 0}
        assert value["permanent_claims_created"] == 0
        assert v1.parent != once.DEFAULT_OUTPUT


def test_diagnose_and_run_use_same_exact_identity_preflight() -> None:
    v1 = (
        pack.REPO_ROOT
        / ".test-output/hardware/"
        "MF1750_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_WHITE_20260901_V1/"
        "j2-off-diagnostic.json"
    )
    if not v1.is_file():
        pytest.skip("现场 V1 four-GET transcript 不在当前工作树")
    evidence = json.loads(v1.read_text(encoding="utf-8"))
    responses = {
        item["endpoint"]: deepcopy(item["body"]) for item in evidence["transcript"]
    }
    old = once._load_delegate()  # noqa: SLF001
    host = old.host

    def replay(
        _base_url: str,
        path: str,
        *,
        method: str,
        headers: dict[str, str] | None,
        timeout: float,
    ) -> tuple[int, dict[str, object]]:
        assert method == "GET"
        assert headers is None
        assert timeout > 0
        return 200, deepcopy(responses[path.rsplit("/", 1)[-1]])

    for expected_busy in (0, 1):
        responses["status"]["busy"] = expected_busy
        transcript: list[dict[str, object]] = []
        running_sha, boot_nonce, report = host._preflight(  # noqa: SLF001
            replay,
            transcript,
            "http://192.168.1.11",
            expected_busy=expected_busy,
            timeout=1.0,
            progress={},
        )
        assert running_sha == pack.FIRMWARE_ELF_SHA256
        assert boot_nonce == evidence["transcript"][2]["body"]["boot_nonce"]
        assert report["terminal_state"] == "NOT_EXECUTED"
        assert [item["endpoint"] for item in transcript] == [
            "version",
            "manifest",
            "status",
            "report",
        ]
