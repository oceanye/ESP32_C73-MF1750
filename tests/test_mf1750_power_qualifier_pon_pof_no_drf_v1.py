from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from tools import mf1750_power_qualifier_pon_pof_no_drf_v1_once as once
from tools import mf1750_power_qualifier_pon_pof_no_drf_v1_pack as pack


BOOT = "0123456789abcdef"
QUAL = "1111111111111111"
ARM = "2222222222222222"


def _identity(suffix: str) -> dict[str, Any]:
    return {
        "kind": f"mf1750-power-qualifier-pon-pof-no-drf-v1-{suffix}",
        "build_tag": pack.BUILD_TAG,
        "test_id": pack.TEST_ID,
        "campaign_id": pack.CAMPAIGN_ID,
        "contract_id": pack.CONTRACT_ID,
        "descriptor_id": pack.DESCRIPTOR_ID,
        "action_id": pack.ACTION_ID,
    }


def _version() -> dict[str, Any]:
    return {
        **_identity("version"),
        "action_count": 1,
        "startup_refresh": False,
        "visible_refresh_requests": 0,
        "base_route": once.ENDPOINT_BASE,
        "device_api_version": pack.DEVICE_API_VERSION,
        "identity_revision": pack.IDENTITY_REVISION,
        "classification": pack.CLASSIFICATION,
        "automatic_execute": False,
        "automatic_chaining": False,
        "retry": False,
        "recovery": False,
        "raw_frame_ingress": False,
        "runtime_lut_write": False,
        "ptlw_write": False,
        "visible_refresh": False,
        "nvs_contract": {
            "namespace": pack.NVS_NAMESPACE,
            "key": pack.NVS_KEY,
            "terminal_next_ordinal": 2,
        },
    }


def _manifest() -> dict[str, Any]:
    return {
        **_identity("manifest"),
        "actions": [once.ACTION],
        "classification": pack.CLASSIFICATION,
        "nvs": {
            "namespace": pack.NVS_NAMESPACE,
            "key": pack.NVS_KEY,
            "terminal_next_ordinal": 2,
            "missing_key_is_fresh_only": True,
            "nonterminal_phase_on_boot": "FAULT_NO_RESUME_NO_RETRY",
        },
        "qualification": {
            "reset_count": 1, "cs1_revision_reads": 2,
            "cs2_revision_reads": 2, "stable_required": True,
            "nontrivial_required": True, "same_boot_required": True,
            "qualified_busy_level": 1,
            "qualified_gpio": {"rst": 1, "cs1": 1, "cs2": 1, "sck": 0, "dc": 0, "mosi": 0},
        },
        "probe": {
            "spi_hz": pack.PROBE_SPI_HZ,
            "exactly_one_pon": True,
            "exactly_one_pof": True,
            "pon_count": 1, "pof_count": 1, "drf_count": 0,
            "dtm_bytes": 0, "lut_bytes": 0, "ptlw_writes": 0,
            "command_0x86_count": 0, "visible_refresh_requests": 0,
            "failure_cleanup_matrix": pack.FAILURE_CLEANUP_MATRIX,
            "post_pof": ["DELAY_6000MS", "PSR_4F6E", "WAIT_IDLE", "DELAY_1000MS", "PINS_LOW"],
        },
        "allowed_command_payload_sequence": [
            "REV_CS1_X2_70", "REV_CS2_X2_70", "AA_495520080918",
            "PWR_01_3F", "PSR_00_5F69", "BTST1_05_401F1F2C",
            "BTST3_08_6F1F1F22", "BTST2_06_6F1F1717",
            "POFS_03_00540044", "TCON_60_0200", "PLL_30_08",
            "CDI_50_3F", "TRES_61_02000258", "PWS_E3_2F",
            "T_VDCS_84_01", "CCSET_CS1_E0_01", "CCSET_CS2_E0_01",
            "SELECT_DUAL_BEFORE_PON", "PON_04",
            "SELECT_DUAL_BEFORE_POF", "POF_02_00",
            "SELECT_DUAL_BEFORE_POST_PSR", "PSR_00_4F6E",
        ],
        "forbidden_commands": list(pack.FORBIDDEN_COMMANDS),
        "safety": {
            "startup_action": False, "automatic_execute": False,
            "automatic_retry": False, "automatic_recovery": False,
            "automatic_chaining": False,
        },
        "action_count": 1,
        "one_driver_call_per_action": True,
        "probe_sequence": list(pack.PROBE_SEQUENCE),
        "pon_count": 1,
        "pof_count": 1,
        "drf_count": 0,
        "dtm_bytes": 0,
        "lut_bytes": 0,
        "ptlw_writes": 0,
        "visible_refresh_requests": 0,
        "retry": False,
        "recovery": False,
        "autochain": False,
    }


def _status(*, qualified: bool, busy: int) -> dict[str, Any]:
    return {
        **_identity("status"),
        "boot_nonce": BOOT,
        "next_ordinal": 1,
        "campaign_complete": False,
        "state": "qualified" if qualified else "ready_unqualified",
        "phase": 2 if qualified else 0,
        "phase_name": "QUALIFIED" if qualified else "FRESH",
        "same_boot_qualified": qualified,
        "qualified_pin_posture": qualified,
        "qualify_pending": False,
        "probe_pending": False,
        "qualify_request_count": 1 if qualified else 0,
        "qualifier_call_count": 1 if qualified else 0,
        "arm_request_count": 0,
        "execute_request_count": 0,
        "probe_call_count": 0,
        "cursor_raw": 2 if qualified else 0,
        "fixture_self_check_passed": True,
        "cursor_valid": True,
        "gpio_initialized": True,
        "execute_pending": False,
        "persistent_key_present": qualified,
        "qualification_consumed": qualified,
        "qualification_valid": qualified,
        "total_driver_call_count": 0,
        "gpio": {
            "busy": busy, "rst": 1 if qualified else 0,
            "cs1": 1 if qualified else 0, "cs2": 1 if qualified else 0,
            "sck": 0, "dc": 0, "mosi": 0,
        },
        "qualification_nonce": QUAL if qualified else None,
    }


def _report(*, terminal: bool = False) -> dict[str, Any]:
    value: dict[str, Any] = {
        **_identity("report"),
        "boot_nonce": BOOT,
        "terminal_state": "NOT_EXECUTED",
        "result": False,
    }
    if not terminal:
        return value
    probe = {
        "valid": True,
        "running": False,
        "spi_hz": pack.PROBE_SPI_HZ,
        "sequence_ok": True,
        "wait_timeout": False,
        "busy_assertion_missing": False,
        "pre_command_idle_failure": False,
        "failure_stage": "none",
        "timeout_stage": "none",
        "busy_missing_stage": "none",
        "pre_command_busy_stage": "none",
        "post_psr_command_sent": True,
        "post_psr_payload_hex": "4f6e",
        "pon_command_sent": True,
        "pof_command_sent": True,
        "pon_idle_completed": True,
        "pof_idle_completed": True,
        "pon_busy_seen": True,
        "pof_busy_seen": True,
        "pon_gate_entry": 1,
        "pof_gate_entry": 1,
        "command_trace": list(pack.PROBE_COMMAND_TRACE),
        "wire_event_count": pack.PROBE_WIRE_EVENT_COUNT,
        "wire_fnv1a": pack.PROBE_WIRE_FNV1A,
        "command_counts": {
            "pon": 1, "pof": 1, "drf": 0, "dtm": 0,
            "lut": 0, "ptlw": 0, "command_0x86": 0,
            "visible_refresh_requests": 0,
        },
        "forbidden_commands": {
            "drf": False,
            "dtm": False,
            "lut": False,
            "ptlw": False,
            "command_0x86": False,
        },
        "safe_finish": {
            "busy_before_pins_low": 1,
            "final_gpio": {
                "rst": 0,
                "cs1": 0,
                "cs2": 0,
                "sck": 0,
                "dc": 0,
                "mosi": 0,
            },
        },
    }
    value.update(
        {
            "terminal_state": "COMPLETE",
            "result": True,
            "ordinal": 1,
            "role": once.ACTION["role"],
            "branch": once.ACTION["branch"],
            "phase": 5,
            "phase_name": "COMPLETE",
            "action_id": pack.ACTION_ID,
            "descriptor_id": pack.DESCRIPTOR_ID,
            "qualification_nonce": QUAL,
            "qualifier_call_count": 1,
            "probe_call_count": 1,
            "valid": True,
            "driver_called": True,
            "driver_call_count_for_action": 1,
            "total_driver_call_count": 1,
            "next_ordinal": 2,
            "campaign_complete": True,
            "readiness": _readiness(),
            "probe": probe,
            "driver": probe,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        }
    )
    return value


def _readiness() -> dict[str, Any]:
    sample = {"idle": True, "bytes": [1, 2, 3]}
    return {
        "valid": True,
        "qualified": True,
        "entry_busy": 0,
        "final_busy": 1,
        "final_gpio": {"rst": 1, "cs1": 1, "cs2": 1, "sck": 0, "dc": 0, "mosi": 0},
        "final_high_stable_ms": 50,
        "reset_count": 1,
        "revision_read_count": 4,
        "revision_command_trace": [0x70, 0x70, 0x70, 0x70],
        "total_ms": 200,
        "cs1": {"sample1": sample, "sample2": sample, "stable": True, "nontrivial": True},
        "cs2": {"sample1": sample, "sample2": sample, "stable": True, "nontrivial": True},
        "failure_stage": "none",
    }


def _qualified_report() -> dict[str, Any]:
    return {
        **_identity("report"),
        "valid": True,
        "boot_nonce": BOOT,
        "terminal_state": "QUALIFIED",
        "result": True,
        "phase": 2,
        "phase_name": "QUALIFIED",
        "qualification_nonce": QUAL,
        "driver_called": False,
        "readiness": _readiness(),
        "probe": None,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
    }


def _qualification_fault_status() -> dict[str, Any]:
    value = _status(qualified=False, busy=1)
    value.update(
        {
            "state": "fault_locked",
            "phase": 6,
            "phase_name": "FAULT",
            "qualify_request_count": 1,
            "qualifier_call_count": 1,
            "cursor_raw": 6,
            "persistent_key_present": True,
            "qualification_consumed": True,
        }
    )
    return value


def _qualification_fault_report() -> dict[str, Any]:
    cs1_sample = {"idle": True, "bytes": [1, 1, 4]}
    cs2_sample = {"idle": True, "bytes": [0, 0, 0]}
    readiness = {
        "valid": True,
        "qualified": False,
        "entry_busy": 1,
        "final_busy": 1,
        "final_gpio": {
            "rst": 0,
            "cs1": 0,
            "cs2": 0,
            "sck": 0,
            "dc": 0,
            "mosi": 0,
        },
        "final_high_stable_ms": 50,
        "reset_count": 1,
        "revision_read_count": 4,
        "revision_command_trace": [0x70, 0x70, 0x70, 0x70],
        "total_ms": 200,
        "cs1": {
            "sample1": cs1_sample,
            "sample2": cs1_sample,
            "stable": True,
            "nontrivial": True,
        },
        "cs2": {
            "sample1": cs2_sample,
            "sample2": cs2_sample,
            "stable": True,
            "nontrivial": False,
        },
        "failure_stage": "cs2_revision_trivial",
    }
    probe = {
        "valid": False,
        "running": False,
        "sequence_ok": False,
        "operation_id": 0,
        "spi_hz": 0,
        "pon_command_sent": False,
        "pof_command_sent": False,
        "post_psr_command_sent": False,
        "pon_busy_seen": False,
        "pof_busy_seen": False,
        "command_counts": {
            "pon": 0,
            "pof": 0,
            "drf": 0,
            "dtm": 0,
            "lut": 0,
            "ptlw": 0,
            "command_0x86": 0,
            "visible_refresh_requests": 0,
        },
        "forbidden_commands": {
            "drf": False,
            "dtm": False,
            "lut": False,
            "ptlw": False,
            "command_0x86": False,
        },
        "command_trace": [],
        "wire_event_count": 0,
        "wire_fnv1a": 0x811C9DC5,
    }
    return {
        **_identity("report"),
        "valid": True,
        "boot_nonce": BOOT,
        "terminal_state": "FAULT",
        "result": False,
        "error": "readiness_qualification_failed",
        "qualification_nonce": None,
        "phase": 6,
        "phase_name": "FAULT",
        "readiness": readiness,
        "probe": probe,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
    }


class ScriptedRequester:
    def __init__(
        self,
        values: list[tuple[str, str, Mapping[str, Any] | Exception]],
    ) -> None:
        self.values = list(values)
        self.calls: list[tuple[str, str, Mapping[str, str]]] = []

    def __call__(
        self,
        _origin: str,
        path: str,
        *,
        method: str,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        del timeout
        wanted_method, wanted_path, response = self.values.pop(0)
        assert (method, path) == (wanted_method, wanted_path)
        self.calls.append((method, path, dict(headers or {})))
        if isinstance(response, Exception):
            raise response
        return 200, response


def _four(
    status: Mapping[str, Any], report: Mapping[str, Any] | None = None
) -> list[tuple[str, str, Mapping[str, Any]]]:
    return [
        ("GET", once.ENDPOINTS["version"], _version()),
        ("GET", once.ENDPOINTS["manifest"], _manifest()),
        ("GET", once.ENDPOINTS["status"], status),
        ("GET", once.ENDPOINTS["report"], report or _report()),
    ]


@pytest.fixture
def bound_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary = tmp_path / "firmware.bin"
    elf = tmp_path / "firmware.elf"
    binary.write_bytes(b"bin")
    elf.write_bytes(b"elf")
    monkeypatch.setattr(once, "FIRMWARE_BIN", binary)
    monkeypatch.setattr(once, "FIRMWARE_ELF", elf)
    monkeypatch.setattr(once, "FIRMWARE_BIN_BYTES", 3)
    monkeypatch.setattr(once, "FIRMWARE_ELF_BYTES", 3)
    monkeypatch.setattr(once, "FIRMWARE_BIN_SHA256", hashlib.sha256(b"bin").hexdigest())
    monkeypatch.setattr(once, "FIRMWARE_ELF_SHA256", hashlib.sha256(b"elf").hexdigest())


def test_pack_ids_are_derived_and_forbidden_surface_is_exact() -> None:
    report = pack.build_report()
    assert report["descriptor_canonical_sha256"] == pack.DESCRIPTOR_ID
    assert pack._action_id(pack.DESCRIPTOR_ID) == pack.ACTION_ID
    assert report["contract_canonical_sha256"] == pack.CONTRACT_ID
    assert tuple(report["contract"]["forbidden_commands"]) == pack.FORBIDDEN_COMMANDS
    assert "CDI_0X50" not in pack.FORBIDDEN_COMMANDS
    assert "BTST2_0X06" not in pack.FORBIDDEN_COMMANDS
    assert pack.PROBE_COMMAND_TRACE == (
        0xAA, 0x01, 0x00, 0x05, 0x08, 0x06, 0x03, 0x60, 0x30,
        0x50, 0x61, 0xE3, 0x84, 0xE0, 0xE0, 0x04, 0x02, 0x00,
    )
    assert (pack.PROBE_WIRE_EVENT_COUNT, pack.PROBE_WIRE_FNV1A) == (
        58,
        0xC12C52D5,
    )
    assert report["descriptor"]["probe_spi_hz"] == 1_000_000
    assert report["contract"]["probe"]["spi_hz"] == 1_000_000
    assert report["descriptor"]["failure_cleanup_matrix"] == (
        pack.FAILURE_CLEANUP_MATRIX
    )
    assert report["contract"]["nvs"]["missing_key_is_fresh_only"] is True
    assert (
        report["contract"]["nvs"]["nonterminal_phase_on_boot"]
        == "FAULT_NO_RESUME_NO_RETRY"
    )


def test_describe_and_dry_validate_are_offline_with_bound_artifacts(
    bound_artifacts: None,
) -> None:
    assert once.describe()["live_authorized"] is False
    value = once.dry_validate()
    assert value["offline_only"] is True
    assert value["network_accessed"] is False
    assert value["pack_valid"] is True
    assert value["live_entry_enabled"] is True


def test_j2_off_diagnostic_is_exactly_four_gets(
    tmp_path: Path, bound_artifacts: None
) -> None:
    requester = ScriptedRequester(_four(_status(qualified=False, busy=0)))
    value = once.diagnose_j2_off(
        "http://192.168.1.11",
        output=tmp_path / "diag.json",
        confirm_j2_off=True,
        requester=requester,
    )
    assert value["network"] == {"get": 4, "post": 0}
    assert all(call[0] == "GET" for call in requester.calls)


def test_qualification_fault_salvage_is_four_gets_and_no_claim(
    tmp_path: Path, bound_artifacts: None
) -> None:
    claims = tmp_path / "claims"
    output = tmp_path / "result.json"
    attempt_file = claims / f"{pack.ACTION_ID}.qualification-attempt.json"
    reservation_file = Path(str(output) + ".reserve")
    once._write_new(
        attempt_file,
        once._seal(
            {
                "schema_version": 1,
                "kind": "mf1750-power-qualifier-pon-pof-no-drf-v1-qualification-attempt",
                "created_at": "2026-08-25T23:29:01.525+08:00",
                "firmware_sha256": once.FIRMWARE_BIN_SHA256,
                "boot_nonce": BOOT,
                "action": once.ACTION,
                "initial_busy": 1,
                "state": "reserved_before_qualify_post",
                "no_automatic_retry": True,
            }
        ),
    )
    once._write_new(
        reservation_file,
        once._seal(
            {
                "schema_version": 1,
                "kind": "mf1750-power-qualifier-pon-pof-no-drf-v1-output-reservation",
                "created_at": "2026-08-25T23:29:01.526+08:00",
                "boot_nonce": BOOT,
                "final_output": str(output.resolve()),
            }
        ),
    )
    requester = ScriptedRequester(
        _four(_qualification_fault_status(), _qualification_fault_report())
    )
    value = once.salvage_fault(
        "http://192.168.1.11",
        claims=claims,
        output=output,
        confirm_j2_off=True,
        requester=requester,
    )
    assert value["network"] == {"get": 4, "post": 0}
    assert value["probe_command_counts"] == {"pon": 0, "pof": 0, "drf": 0}
    assert value["permanent_claim_present"] is False
    assert value["action_must_not_be_retried"] is True
    assert output.is_file()
    assert not (claims / f"{pack.ACTION_ID}.json").exists()
    assert all(method == "GET" for method, _, _ in requester.calls)


def test_live_flow_qualifies_before_arm_and_never_requests_visible_refresh(
    tmp_path: Path, bound_artifacts: None
) -> None:
    qualify = {
        **_identity("qualification"),
        "accepted": True,
        "qualification_queued": True,
        "boot_nonce": BOOT,
        "action_id": pack.ACTION_ID,
        "descriptor_id": pack.DESCRIPTOR_ID,
        "phase": 1,
        "phase_name": "QUALIFY_CONSUMED",
        "no_retry": True,
        "no_recovery": True,
    }
    arm = {
        **_identity("arm"),
        "accepted": True,
        "armed": True,
        "arm_nonce": ARM,
        "qualification_nonce": QUAL,
        "boot_nonce": BOOT,
        "action_id": pack.ACTION_ID,
        "descriptor_id": pack.DESCRIPTOR_ID,
    }
    execute = {
        **_identity("execute"),
        "accepted": True,
        "execute_consumed": True,
        "qualification_nonce": QUAL,
        "boot_nonce": BOOT,
        "action_id": pack.ACTION_ID,
        "descriptor_id": pack.DESCRIPTOR_ID,
    }
    scripted = (
        _four(_status(qualified=False, busy=0))
        + [("POST", once.ENDPOINTS["qualify"], qualify)]
        + _four(_status(qualified=True, busy=1), _qualified_report())
        + [
            ("POST", once.ENDPOINTS["arm"], arm),
            ("POST", once.ENDPOINTS["execute"], execute),
            ("GET", once.ENDPOINTS["report"], _report(terminal=True)),
        ]
    )
    requester = ScriptedRequester(scripted)
    value = once.run_once(
        "http://192.168.1.11",
        claims=tmp_path / "claims",
        output=tmp_path / "result.json",
        confirm_j2_on=True,
        requester=requester,
        poll_seconds=0,
        poll_count=1,
    )
    endpoints = [Path(call[1]).name for call in requester.calls]
    assert endpoints.index("qualify") < endpoints.index("arm") < endpoints.index("execute")
    assert value["outcome"] == "complete_pass"
    assert value["visible_refresh_requests"] == 0
    assert value["network"] == {
        "get": 9,
        "qualify_post": 1,
        "arm_post": 1,
        "execute_post": 1,
    }


def test_terminal_get_timeouts_do_not_repeat_any_post(
    tmp_path: Path, bound_artifacts: None
) -> None:
    qualify = {
        **_identity("qualification"),
        "accepted": True,
        "qualification_queued": True,
        "boot_nonce": BOOT,
        "action_id": pack.ACTION_ID,
        "descriptor_id": pack.DESCRIPTOR_ID,
        "phase": 1,
        "phase_name": "QUALIFY_CONSUMED",
        "no_retry": True,
        "no_recovery": True,
    }
    arm = {
        **_identity("arm"),
        "accepted": True,
        "armed": True,
        "arm_nonce": ARM,
        "qualification_nonce": QUAL,
        "boot_nonce": BOOT,
        "action_id": pack.ACTION_ID,
        "descriptor_id": pack.DESCRIPTOR_ID,
    }
    execute = {
        **_identity("execute"),
        "accepted": True,
        "execute_consumed": True,
        "qualification_nonce": QUAL,
        "boot_nonce": BOOT,
        "action_id": pack.ACTION_ID,
        "descriptor_id": pack.DESCRIPTOR_ID,
    }
    requester = ScriptedRequester(
        _four(_status(qualified=False, busy=0))
        + [("POST", once.ENDPOINTS["qualify"], qualify)]
        + _four(_status(qualified=True, busy=1), _qualified_report())
        + [
            ("POST", once.ENDPOINTS["arm"], arm),
            ("POST", once.ENDPOINTS["execute"], execute),
            ("GET", once.ENDPOINTS["report"], TimeoutError("listener restarting")),
            ("GET", once.ENDPOINTS["report"], TimeoutError("probe still running")),
            ("GET", once.ENDPOINTS["report"], _report(terminal=True)),
        ]
    )
    value = once.run_once(
        "http://192.168.1.11",
        claims=tmp_path / "claims",
        output=tmp_path / "result.json",
        confirm_j2_on=True,
        requester=requester,
        poll_seconds=0,
        poll_count=3,
    )
    post_endpoints = [
        Path(path).name for method, path, _ in requester.calls if method == "POST"
    ]
    assert post_endpoints == ["qualify", "arm", "execute"]
    assert len(value["terminal_poll_errors"]) == 2
    assert value["outcome"] == "complete_pass"


def test_qualified_raw_busy_zero_fails_before_claim_or_arm(
    tmp_path: Path, bound_artifacts: None
) -> None:
    qualify = {
        **_identity("qualification"),
        "accepted": True,
        "qualification_queued": True,
        "boot_nonce": BOOT,
        "action_id": pack.ACTION_ID,
        "descriptor_id": pack.DESCRIPTOR_ID,
        "phase": 1,
        "phase_name": "QUALIFY_CONSUMED",
        "no_retry": True,
        "no_recovery": True,
    }
    requester = ScriptedRequester(
        _four(_status(qualified=False, busy=0))
        + [("POST", once.ENDPOINTS["qualify"], qualify)]
        + _four(_status(qualified=True, busy=0), _qualified_report())
    )
    with pytest.raises(once.QualifierError, match="BUSY|busy"):
        once.run_once(
            "http://192.168.1.11",
            claims=tmp_path / "claims",
            output=tmp_path / "result.json",
            confirm_j2_on=True,
            requester=requester,
            poll_seconds=0,
        )
    assert all(Path(call[1]).name != "arm" for call in requester.calls)
    assert not (tmp_path / "claims" / f"{pack.ACTION_ID}.json").exists()


def test_existing_output_is_rejected_before_any_request(
    tmp_path: Path, bound_artifacts: None
) -> None:
    output = tmp_path / "result.json"
    output.write_text("occupied", encoding="utf-8")
    requester = ScriptedRequester([])
    with pytest.raises(once.QualifierError, match="overwrite final evidence"):
        once.run_once(
            "http://192.168.1.11",
            claims=tmp_path / "claims",
            output=output,
            confirm_j2_on=True,
            requester=requester,
        )
    assert requester.calls == []


def test_runner_has_no_serial_relay_or_flash_surface() -> None:
    source = Path(once.__file__).read_text(encoding="utf-8")
    for forbidden in ("import serial", "relay_zave", "esptool", "run_upload"):
        assert forbidden not in source
    assert "ProxyHandler({})" in source


def test_written_result_integrity_is_canonical(
    tmp_path: Path, bound_artifacts: None
) -> None:
    # Exercise sealing without duplicating the full live fixture.
    sealed = once._seal({"value": 1})
    body = dict(sealed)
    integrity = body.pop("integrity")
    assert integrity["sha256"] == hashlib.sha256(
        json.dumps(
            body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
