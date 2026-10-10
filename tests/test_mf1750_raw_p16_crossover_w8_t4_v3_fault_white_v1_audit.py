from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v3_pack as t4,
)
from tools import (
    mf1750_raw_p16_crossover_w5_t4_active_header_ca_r20_swap_confirmation_white_v1_pack as w5,
)
from tools import (
    mf1750_raw_p16_crossover_w6_t4_active_header_ca_r20_swap_confirmation_successor_v2_white_v1_pack as w6,
)
from tools import (
    mf1750_raw_p16_crossover_w7_t4_active_header_ca_r20_swap_confirmation_successor_v3_white_v1_pack as w7,
)
from tools import (
    mf1750_raw_p16_crossover_w8_t4_v3_fault_white_v1_once as once,
)
from tools import (
    mf1750_raw_p16_crossover_w8_t4_v3_fault_white_v1_pack as w8,
)


ROOT = Path(__file__).resolve().parents[1]


def _identity(report: dict[str, object]) -> tuple[object, ...]:
    action = report.get("action") or report["actions"][0]  # type: ignore[index]
    contract = report["contract"]  # type: ignore[index]
    return (
        report["contract_id"],
        action["descriptor_id"],  # type: ignore[index]
        action["action_id"],  # type: ignore[index]
        contract["campaign_id"],  # type: ignore[index]
        contract["base_route"],  # type: ignore[index]
        contract["nvs_namespace"],  # type: ignore[index]
    )


def test_w8_fault_authority_and_relay_chronology_are_deep_valid() -> None:
    authority = w8.validate_fault_authority()
    status = authority["status"]
    terminal = authority["terminal_report"]
    driver = terminal["driver"]
    assert authority["terminal_state"] == "FAULT"
    assert authority["partial_visible_panel_mutation_possible"] is True
    assert authority["panel_state_qualified"] is False
    assert authority["matched_swap_complete"] is False
    assert status["arm_request_count"] == 1
    assert status["execute_request_count"] == 1
    assert status["total_driver_call_count"] == 1
    assert terminal["driver_call_count_for_action"] == 1
    assert terminal["total_driver_call_count"] == 1
    assert driver["drf_ms"] == 60_001
    assert driver["wait_timeout"] is True
    assert driver["timeout_stage"] == "DRF"
    assert driver["sequence_ok"] is False
    assert (
        w8.PROTECTIVE_OFF_BINDING["switched_at"]
        > w8.LATEST_REPOWER_ON_BINDING["switched_at"]
    )


def test_w8_identity_is_fresh_and_rejects_complete_path() -> None:
    report = w8.build_white_report()
    contract = report["contract"]
    action = report["action"]
    own = _identity(report)
    for predecessor in (
        w5.build_white_report(),
        w6.build_white_report(),
        w7.build_white_report(),
        t4.build_report(),
    ):
        assert all(left != right for left, right in zip(own, _identity(predecessor)))
    assert action["source_action_id"] == t4.build_report()["actions"][0]["action_id"]
    assert contract["source_terminal_state_required"] == "FAULT"
    assert contract["source_complete_path_forbidden"] is True
    assert contract["source_action_must_not_be_retried"] is True
    assert contract["factory_otp_white_only"] is True
    assert contract["runtime_payload"] is False
    assert contract["startup_refresh"] is False
    assert action["action_id"] not in contract["rejected_obsolete_white_action_ids"]
    assert len(w8.CONFIG.nvs_namespace) <= 15
    assert len(w8.CONFIG.nvs_key) <= 15


def test_w8_sealed_artifacts_embed_exact_identity() -> None:
    report = w8.build_white_report()
    action = report["action"]
    expected = w8.WHITE_ARTIFACTS[w8.STAGE]
    for label, path, byte_key, sha_key in (
        ("bin", w8.white_artifact_paths()[0], "bin_bytes", "bin_sha256"),
        ("elf", w8.white_artifact_paths()[1], "elf_bytes", "elf_sha256"),
    ):
        payload = path.read_bytes()
        assert len(payload) == expected[byte_key], label
        assert hashlib.sha256(payload).hexdigest() == expected[sha_key], label
        for token in (
            w8.CONFIG.campaign_id,
            w8.CONFIG.build_tag,
            report["contract_id"],
            action["descriptor_id"],
            action["action_id"],
            action["source_contract_id"],
            action["source_action_id"],
            w8.marker(),
        ):
            assert token.encode("ascii") in payload, (label, token)


def test_w8_run_rejects_missing_diagnostic_before_host_or_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    monkeypatch.setattr(once, "_verify_artifacts", lambda: events.append("artifacts"))
    monkeypatch.setattr(
        once,
        "_verify_fault_authority_chain",
        lambda: events.append("authority"),
    )
    monkeypatch.setattr(once, "_diagnostic_path", lambda: tmp_path / "missing.json")
    monkeypatch.setattr(once, "_configure_white", lambda: events.append("host"))
    assert (
        once.main(
            [
                "run-white",
                "--base-url",
                "http://must-not-be-used.invalid",
                "--confirm-j2-on",
                "--confirm-gnd-normal",
            ]
        )
        == 2
    )
    assert events == ["artifacts", "authority"]


def test_w8_rejects_predecessor_diagnostic_as_near_miss(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    predecessor = (
        ROOT
        / ".test-output/hardware"
        / (
            "MF1750_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_"
            "SUCCESSOR_V2_WHITE_20260831_V1"
        )
        / "j2-off-diagnostic.json"
    )
    if not predecessor.is_file():
        pytest.skip("fixed predecessor diagnostic is unavailable")
    candidate = tmp_path / "j2-off-diagnostic.json"
    candidate.write_bytes(predecessor.read_bytes())
    monkeypatch.setattr(once, "_diagnostic_path", lambda: candidate)
    with pytest.raises(once.W8RunnerError, match="envelope differs"):
        once._validate_diagnostic_evidence()  # noqa: SLF001


def test_w8_same_boot_requester_rejects_changed_boot() -> None:
    def requester(
        _base_url: str,
        _path: str,
        *,
        method: str,
        headers: dict[str, str] | None,
        timeout: float,
    ) -> tuple[int, dict[str, str]]:
        del method, headers, timeout
        return 200, {"boot_nonce": "changed"}

    checked = once._same_boot_requester(  # noqa: SLF001
        requester,
        status_path="/status",
        expected_boot_nonce="expected",
    )
    with pytest.raises(once.W8RunnerError, match="boot changed"):
        checked(
            "http://not-used.invalid",
            "/status",
            method="GET",
            headers=None,
            timeout=1.0,
        )


def test_w8_compile_config_has_no_upload_path() -> None:
    config = (
        ROOT / "platformio.raw_p16_crossover_w8_t4_v3_fault_white_v1.ini"
    ).read_text(encoding="utf-8")
    assert "build_dir = .pio/b-w8t4f-w1" in config
    assert "default_envs = ec5_p16_w8t4f_w1" in config
    assert "MF1750_RAW_P16_CROSSOVER_W8_T4_V3_FAULT_WHITE_V1_BUILD=1" in config
    assert "MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY=1" in config
    assert "MF1750_PURE_FIELD_WHITE=1" in config
    assert "upload_protocol" not in config
    assert "upload_command" not in config


def test_w8_relay_bindings_keep_electrical_boundary_explicit() -> None:
    report = w8.build_white_report()
    contract = report["contract"]
    assert contract["relay_off_query_is_commanded_state_only"] is True
    assert contract["relay_electrical_state_proven"] is False
    assert contract["fresh_user_physical_gnd_confirmation_required_before_j2_on"] is True
    assert contract["protective_off_switch_receipt_required_before_live"] is True
    for binding in (
        w8.RELAY_OFF_QUERY_BINDING,
        w8.LATEST_REPOWER_ON_BINDING,
        w8.PROTECTIVE_OFF_BINDING,
    ):
        payload = Path(binding["path"]).read_bytes()
        assert len(payload) == binding["bytes"]
        assert hashlib.sha256(payload).hexdigest() == binding["file_sha256"]
        value = json.loads(payload)
        integrity = value.pop("integrity")
        assert (
            hashlib.sha256(w8.canonical_json(value)).hexdigest()
            == integrity["canonical_sha256"]
            == binding["canonical_integrity_sha256"]
        )
