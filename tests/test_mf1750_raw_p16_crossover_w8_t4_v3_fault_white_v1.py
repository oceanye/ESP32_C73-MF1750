from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

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
    mf1750_raw_p16_crossover_w8_t4_v3_fault_white_v1_build as build,
)
from tools import (
    mf1750_raw_p16_crossover_w8_t4_v3_fault_white_v1_once as once,
)
from tools import (
    mf1750_raw_p16_crossover_w8_t4_v3_fault_white_v1_pack as w8,
)


ROOT = Path(__file__).resolve().parents[1]


def test_w8_deep_fault_authority_and_transcript_are_exact() -> None:
    authority = w8.validate_fault_authority()
    assert authority["terminal_state"] == "FAULT"
    assert authority["outcome"] == "fault_salvaged_read_only"
    assert authority["network"] == {"get": 0, "post": 0}
    assert authority["reconciled_historical_network"] == {"get": 4, "post": 0}
    assert authority["historical_transcript"] == __import__("json").loads(
        Path(w8.RAW_SALVAGE_BINDING["path"]).read_bytes()
    )["transcript"]
    assert [
        (item["method"], item["endpoint"], item["status"])
        for item in authority["historical_transcript"]
    ] == [
        ("GET", "version", 200),
        ("GET", "manifest", 200),
        ("GET", "status", 200),
        ("GET", "report", 200),
    ]
    assert authority["driver_called"] is True
    assert authority["driver_call_count_for_action"] == 1
    assert authority["total_driver_call_count"] == 1
    assert authority["terminal_report"]["driver"]["timeout_stage"] == "DRF"
    assert authority["terminal_report"]["driver"]["drf_ms"] == 60_001
    assert authority["partial_visible_panel_mutation_possible"] is True
    assert authority["panel_state_qualified"] is False


def test_w8_fault_contract_wire_action_and_obsolete_rejection() -> None:
    report = w8.build_white_report()
    action = report["action"]
    assert set(action) == {
        "ordinal",
        "role",
        "source_campaign_id",
        "source_contract_id",
        "source_descriptor_id",
        "source_action_id",
        "descriptor_id",
        "action_id",
        "frame_sha256",
        "cs1_dtm_sha256",
        "cs2_dtm_sha256",
    }
    assert action["source_action_id"] == (
        "90d769f4e139829bd5aed23ae03aa831be8b4b67159a3463f8747dbeb2c2baee"
    )
    contract = report["contract"]
    assert contract["source_terminal_state_required"] == "FAULT"
    assert contract["source_driver_call_count_required"] == 1
    assert contract["source_drf_timeout_ms"] == 60_001
    assert contract["source_complete_path_forbidden"] is True
    assert contract["source_action_must_not_be_retried"] is True
    assert contract["fresh_fault_bound_white_containment_required"] is True
    assert contract["panel_state_qualified"] is False
    assert contract["rejected_obsolete_white_action_ids"] == [
        w5.build_white_report()["action"]["action_id"],
        w6.build_white_report()["action"]["action_id"],
        w7.build_white_report()["action"]["action_id"],
    ]


def test_w8_relay_history_and_protective_off_are_exact() -> None:
    assert w8.PROTECTIVE_OFF_BINDING["switched_at"] > w8.LATEST_REPOWER_ON_BINDING["switched_at"]
    assert w8.validate_fault_authority()["terminal_state"] == "FAULT"
    contract = w8.build_white_report()["contract"]
    assert contract["relay_off_query_is_commanded_state_only"] is True
    assert contract["relay_electrical_state_proven"] is False
    assert contract["protective_off_switch_receipt_required_before_live"] is True
    assert contract["protective_off_postdates_latest_repower_on"] is True


def test_w8_cpp_ini_identity_and_sealed_artifacts_match() -> None:
    report = w8.build_white_report()
    identity = (ROOT / "src/ec5_raw_p16_crossover_w8_t4_v3_fault_white_v1_identity.inc").read_text(encoding="utf-8")
    program = (ROOT / "src/ec5_raw_p16_crossover_w2_discovery_successor_white_program.inc").read_text(encoding="utf-8")
    ini = (ROOT / "platformio.raw_p16_crossover_w8_t4_v3_fault_white_v1.ini").read_text(encoding="utf-8")
    for value in (
        report["contract_id"],
        report["action"]["descriptor_id"],
        report["action"]["action_id"],
        report["action"]["source_action_id"],
        w8.CONFIG.campaign_id,
        w8.CONFIG.build_tag,
        w8.marker(),
    ):
        assert value in identity
    selector = "MF1750_RAW_P16_CROSSOVER_W8_T4_V3_FAULT_WHITE_V1_BUILD"
    assert selector in program
    assert f"{selector}=1" in ini
    assert '"/api/ec5/raw-p16-crossover-"' in program
    for endpoint in ("version", "manifest", "status", "report", "arm", "execute"):
        assert f'"w8-after-t4-successor-v3-fault-white-v1/{endpoint}"' in program
    assert "upload_protocol" not in ini
    assert "upload_command" not in ini
    for item in once._artifact_binding().values():  # noqa: SLF001
        payload = Path(item["path"]).read_bytes()
        assert len(payload) == item["bytes"]
        assert hashlib.sha256(payload).hexdigest() == item["sha256"]


def test_w8_runner_and_compile_only_build_preflight_pass() -> None:
    validation = once.dry_validate()
    assert validation["result"] == "PASS"
    assert validation["authority_terminal_state"] == "FAULT"
    assert validation["artifacts_verified"] is True
    assert validation["j2_off_diagnostic_required_before_run"] is True
    assert validation["same_boot_diagnostic_to_execute_required"] is True
    assert build.prebuild_validate()["result"] == "PASS"


def test_w8_run_refuses_missing_diagnostic_before_host_or_device(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    monkeypatch.setattr(once, "_verify_artifacts", lambda: events.append("artifacts"))
    monkeypatch.setattr(once, "_verify_fault_authority_chain", lambda: events.append("authority"))
    monkeypatch.setattr(once, "_diagnostic_path", lambda: tmp_path / "missing.json")
    monkeypatch.setattr(once, "_configure_white", lambda: events.append("host"))
    assert once.main(
        [
            "run-white",
            "--base-url",
            "http://192.0.2.1",
            "--confirm-j2-on",
            "--confirm-gnd-normal",
        ]
    ) == 2
    assert events == ["artifacts", "authority"]


def test_w8_same_boot_wrapper_rejects_changed_status_boot() -> None:
    def fake(_base: str, _path: str, **_kwargs: object) -> tuple[int, dict[str, str]]:
        return 200, {"boot_nonce": "different"}

    checked = once._same_boot_requester(  # noqa: SLF001
        fake, status_path="/status", expected_boot_nonce="expected"
    )
    with pytest.raises(once.W8RunnerError, match="boot changed"):
        checked("http://192.0.2.1", "/status", method="GET", headers=None, timeout=1.0)
