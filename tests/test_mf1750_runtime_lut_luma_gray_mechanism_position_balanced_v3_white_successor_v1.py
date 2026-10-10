from __future__ import annotations

from pathlib import Path

import pytest

from tools import (
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_white_successor_v1_audit as audit,
)
from tools import (
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_white_successor_v1_once as runner,
)
from tools import (
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_white_successor_v1_pack as pack,
)


def _deep_source(ordinal: int) -> dict[str, object]:
    item = pack.source_pack.build_report()["actions"][ordinal - 1]
    return {
        "terminal_state": "COMPLETE",
        "campaign_id": pack.SOURCE_CAMPAIGN_ID,
        "contract_id": pack.SOURCE_MAIN_CONTRACT_ID,
        "ordinal": ordinal,
        "descriptor_id": item["descriptor_id"],
        "action_id": item["action_id"],
        "driver_call_count_for_action": 1,
        "total_driver_call_count": ordinal,
        "visible_refreshes": 1,
        "source_success_claimed": True,
        "canonical_integrity_sha256": "1" * 64,
        "boot_nonce": "0123456789abcdef",
        "claim_file_sha256": "2" * 64,
    }


def test_contract_accepts_g3_by_default_and_g4_only_explicitly() -> None:
    contract = pack.build_report()["contract"]
    assert contract["accepted_source_ordinals"] == [3, 4]
    assert contract["default_source_complete_ordinal"] == 3
    assert contract["optional_g4_source_requires_explicit_human_confirmation"] is True
    assert contract["current_function_plan_executes_g4"] is False
    assert contract["automatic_source_selection"] is False
    assert contract["automatic_execution"] is False
    assert contract["automatic_recovery"] is False
    assert contract["autochain"] is False


def test_source_actions_are_exact_fresh_v3_g3_and_g4() -> None:
    source_actions = pack.source_pack.build_report()["actions"]
    accepted = pack.build_report()["contract"]["accepted_source_complete_actions"]
    assert accepted == [
        {
            "ordinal": item["ordinal"],
            "descriptor_id": item["descriptor_id"],
            "action_id": item["action_id"],
            "role": item["role"],
        }
        for item in source_actions[2:4]
    ]
    assert accepted[0]["action_id"] == (
        "f6c6bb92ae708ac325c4bca53ed12d82f19f41fa84adb1ddd8c68e35c40b86ee"
    )
    assert accepted[1]["action_id"] == (
        "a7d2d3390c6c0803eb5f4098592022c344f49c06141ca798f97fcb40ef1c3947"
    )


def test_g3_and_explicit_g4_terminal_gate_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    g3 = tmp_path / "g3.json"
    g4 = tmp_path / "g4.json"
    g3.write_bytes(b"g3")
    paths = {3: g3.resolve(), 4: g4.resolve()}
    monkeypatch.setattr(runner, "_source_terminal_paths", lambda: paths)
    monkeypatch.setattr(runner, "_repo_relative", lambda path: Path(path).name)
    monkeypatch.setattr(
        runner.source_once,
        "validate_terminal_evidence",
        lambda path: _deep_source(3 if Path(path).resolve() == g3.resolve() else 4),
    )
    assert runner._validate_source_terminal_evidence(g3)["ordinal"] == 3  # noqa: SLF001
    g4.write_bytes(b"g4")
    with pytest.raises(runner.WhiteSuccessorV1Error, match="stale G3"):
        runner._validate_source_terminal_evidence(g3)  # noqa: SLF001
    with pytest.raises(runner.WhiteSuccessorV1Error, match="explicit"):
        runner._validate_source_terminal_evidence(g4)  # noqa: SLF001
    accepted = runner._validate_source_terminal_evidence(  # noqa: SLF001
        g4, confirm_optional_g4_source=True
    )
    assert accepted["ordinal"] == 4
    assert accepted["optional_g4_explicitly_confirmed"] is True


def test_wrong_source_path_fails_before_deep_validation(tmp_path: Path) -> None:
    wrong = tmp_path / "wrong.json"
    wrong.write_text("{}", encoding="utf-8")
    with pytest.raises(runner.WhiteSuccessorV1Error, match="fixed V3 G3"):
        runner._validate_source_terminal_evidence(wrong)  # noqa: SLF001


def test_run_requires_manual_j2_and_gnd_before_any_request(tmp_path: Path) -> None:
    calls = 0

    def requester(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError((args, kwargs))

    with pytest.raises(runner.WhiteSuccessorV1Error, match="J2-ON"):
        runner.run_once(
            "http://192.168.1.7",
            source_terminal_evidence=tmp_path / "absent.json",
            confirm_j2_on=False,
            confirm_gnd_normal=True,
            requester=requester,
        )
    assert calls == 0


def test_artifacts_compiled_identity_and_isolation_are_sealed() -> None:
    value = pack.dry_validate(verify_artifacts=True)
    assert value["result"] == "PASS"
    assert value["compiled_identity_binary"]["counts"] == {"bin": 1, "elf": 1}
    assert pack.NVS_NAMESPACE == "lgmpb3w_v1"
    assert pack.NVS_KEY == "used_lgmpb3w1"
    assert pack.ENVIRONMENT == "ec5_luma_gray_mpb_v3_white_v1"
    assert pack.BUILD_ROOT == "b-luma-gray-mpb-v3-white-v1"
    assert pack.BASE_ROUTE.endswith("position-balanced-v3/white-successor-v1")
    assert "position_balanced_v3_white_successor_v1_claims" in str(
        runner.host.DEFAULT_CLAIMS
    )


def test_independent_audit_passes_without_claiming_future_terminal_exists() -> None:
    result = audit.audit()
    assert result["result"] == "PASS"
    assert result["source_main_identity_and_artifacts_deeply_verified"] is True
    assert result["default_source_complete_ordinal"] == 3
    assert result["optional_g4_source_requires_explicit_human_confirmation"] is True
    assert result["automatic_execution"] is False
    assert result["automatic_recovery"] is False
    assert result["automatic_chaining"] is False
    assert result["source_terminal_evidence_deep_validation"].startswith("DEFERRED")
