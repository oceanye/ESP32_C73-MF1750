from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any, Mapping

import pytest

from tools import mf1750_power_qualifier_pon_pof_no_drf_v1_once as v1_once
from tools import mf1750_power_qualifier_pon_pof_no_drf_v1_pack as v1_pack
from tools import mf1750_power_qualifier_pon_pof_no_drf_v2_once as once
from tools import mf1750_power_qualifier_pon_pof_no_drf_v2_pack as pack


BOOT = "0123456789abcdef"
QUAL = "1111111111111111"
ARM = "2222222222222222"


def _identity(suffix: str) -> dict[str, Any]:
    return {
        "kind": f"{once.KIND_PREFIX}-{suffix}",
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
            "v1_namespace_and_key_must_not_be_erased": True,
        },
        "qualification": {
            "reset_count": 5,
            "reset_before_each_revision_sample": True,
            "final_posture_reset": True,
            "single_variable_change": "PER_SAMPLE_RESET_ONLY",
            "exact_historical_transaction_reproduction": False,
            "legacy_mosi_high_before_reset_restored": False,
            "legacy_post_reset_tail_2us_restored": False,
            "segmented_cs_framing_changed": False,
            "cs1_revision_reads": 2,
            "cs2_revision_reads": 2,
            "expected_revision_bytes": [1, 1, 4],
            "all_four_samples_exact_required": True,
            "same_boot_required": True,
            "qualified_busy_level": 1,
            "qualified_busy_stable_ms": 50,
            "zero_revision_result": (
                "STOP_BEFORE_PON_AND_DEFER_LEGACY_TRANSACTION_TO_V3"
            ),
            "qualified_gpio": {
                "rst": 1,
                "cs1": 1,
                "cs2": 1,
                "sck": 0,
                "dc": 0,
                "mosi": 0,
            },
        },
        "probe": {
            "spi_hz": pack.PROBE_SPI_HZ,
            "exactly_one_pon": True,
            "exactly_one_pof": True,
            "pon_count": 1,
            "pof_count": 1,
            "drf_count": 0,
            "dtm_bytes": 0,
            "lut_bytes": 0,
            "ptlw_writes": 0,
            "command_0x86_count": 0,
            "visible_refresh_requests": 0,
            "failure_cleanup_matrix": pack.FAILURE_CLEANUP_MATRIX,
            "post_pof": [
                "DELAY_6000MS",
                "PSR_4F6E",
                "WAIT_IDLE",
                "DELAY_1000MS",
                "PINS_LOW",
            ],
        },
        "allowed_command_payload_sequence": once.ALLOWED_COMMAND_PAYLOAD_SEQUENCE,
        "forbidden_commands": list(pack.FORBIDDEN_COMMANDS),
        "safety": {
            "startup_action": False,
            "automatic_execute": False,
            "automatic_retry": False,
            "automatic_recovery": False,
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


def _ready_status() -> dict[str, Any]:
    return {
        **_identity("status"),
        "boot_nonce": BOOT,
        "next_ordinal": 1,
        "campaign_complete": False,
        "state": "ready_unqualified",
        "phase": 0,
        "phase_name": "FRESH",
        "same_boot_qualified": False,
        "qualified_pin_posture": False,
        "qualify_pending": False,
        "probe_pending": False,
        "qualify_request_count": 0,
        "qualifier_call_count": 0,
        "arm_request_count": 0,
        "execute_request_count": 0,
        "probe_call_count": 0,
        "cursor_raw": 0,
        "fixture_self_check_passed": True,
        "cursor_valid": True,
        "gpio_initialized": True,
        "execute_pending": False,
        "persistent_key_present": False,
        "qualification_consumed": False,
        "qualification_valid": False,
        "total_driver_call_count": 0,
        "gpio": {
            "busy": 0,
            "rst": 0,
            "cs1": 0,
            "cs2": 0,
            "sck": 0,
            "dc": 0,
            "mosi": 0,
        },
        "qualification_nonce": None,
    }


def _not_executed_report() -> dict[str, Any]:
    return {
        **_identity("report"),
        "boot_nonce": BOOT,
        "terminal_state": "NOT_EXECUTED",
        "result": False,
    }


def _readiness() -> dict[str, Any]:
    sample = {"idle": True, "bytes": [1, 1, 4]}
    return {
        "valid": True,
        "qualified": True,
        "entry_busy": 1,
        "final_busy": 1,
        "final_gpio": {
            "rst": 1,
            "cs1": 1,
            "cs2": 1,
            "sck": 0,
            "dc": 0,
            "mosi": 0,
        },
        "final_high_stable_ms": 50,
        "reset_count": 5,
        "revision_read_count": 4,
        "revision_command_trace": [0x70, 0x70, 0x70, 0x70],
        "total_ms": 500,
        "cs1": {
            "sample1": sample,
            "sample2": sample,
            "stable": True,
            "nontrivial": True,
        },
        "cs2": {
            "sample1": sample,
            "sample2": sample,
            "stable": True,
            "nontrivial": True,
        },
        "failure_stage": "none",
    }


def _qualified_status() -> dict[str, Any]:
    value = _ready_status()
    value.update(
        {
            "state": "qualified",
            "phase": 2,
            "phase_name": "QUALIFIED",
            "same_boot_qualified": True,
            "qualification_nonce": QUAL,
            "qualified_pin_posture": True,
            "qualify_request_count": 1,
            "qualifier_call_count": 1,
            "cursor_raw": 2,
            "persistent_key_present": True,
            "qualification_consumed": True,
            "qualification_valid": True,
            "gpio": {
                "busy": 1,
                "rst": 1,
                "cs1": 1,
                "cs2": 1,
                "sck": 0,
                "dc": 0,
                "mosi": 0,
            },
        }
    )
    return value


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


def _terminal_report() -> dict[str, Any]:
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
            "pon": 1,
            "pof": 1,
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

    return {
        **_identity("report"),
        "valid": True,
        "boot_nonce": BOOT,
        "terminal_state": "COMPLETE",
        "result": True,
        "ordinal": 1,
        "role": once.ACTION["role"],
        "branch": once.ACTION["branch"],
        "phase": 5,
        "phase_name": "COMPLETE",
        "qualification_nonce": QUAL,
        "qualifier_call_count": 1,
        "probe_call_count": 1,
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


def _qualification_fault_status() -> dict[str, Any]:
    value = _ready_status()
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
            "gpio": {
                "busy": 0,
                "rst": 0,
                "cs1": 0,
                "cs2": 0,
                "sck": 0,
                "dc": 0,
                "mosi": 0,
            },
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
        "final_busy": 0,
        "final_gpio": {
            "rst": 0,
            "cs1": 0,
            "cs2": 0,
            "sck": 0,
            "dc": 0,
            "mosi": 0,
        },
        "final_high_stable_ms": 50,
        "reset_count": 5,
        "revision_read_count": 4,
        "revision_command_trace": [0x70, 0x70, 0x70, 0x70],
        "total_ms": 500,
        "cs1": {
            "sample1": cs1_sample,
            "sample2": cs1_sample,
            "stable": True,
            "nontrivial": True,
            "exact_010104": True,
        },
        "cs2": {
            "sample1": cs2_sample,
            "sample2": cs2_sample,
            "stable": True,
            "nontrivial": False,
            "exact_010104": False,
        },
        "all_revision_samples_exact_010104": False,
        "failure_stage": "cs2_revision_trivial",
    }
    probe = {
        "valid": False,
        "running": False,
        "sequence_ok": False,
        "operation_id": 0,
        "spi_hz": 0,
        "total_ms": 0,
        "wait_timeout": False,
        "busy_assertion_missing": False,
        "pre_command_idle_failure": False,
        "pon_busy_seen": False,
        "pof_busy_seen": False,
        "pon_command_sent": False,
        "pof_command_sent": False,
        "post_psr_command_sent": False,
        "pon_idle_completed": False,
        "pof_idle_completed": False,
        "post_psr_payload_hex": "4f6e",
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
        "pon_ms": 0,
        "pof_ms": 0,
        "post_psr_ms": 0,
        "pon_assertion_latency_ms": 0,
        "pof_assertion_latency_ms": 0,
        "pon_gate_entry": 0xFF,
        "pof_gate_entry": 0xFF,
        "timeout_stage": "none",
        "busy_missing_stage": "none",
        "pre_command_busy_stage": "none",
        "failure_stage": "none",
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
        "safe_finish": {
            "busy_before_pins_low": 0xFF,
            "busy_after_pins_low": 0xFF,
            "busy_after_5ms": 0xFF,
            "final_gpio": {
                "busy": 0xFF,
                "rst": 0xFF,
                "cs1": 0xFF,
                "cs2": 0xFF,
                "sck": 0xFF,
                "dc": 0xFF,
                "mosi": 0xFF,
            },
        },
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
    def __init__(self, values: list[tuple[str, str, Mapping[str, Any]]]) -> None:
        self.values = list(values)
        self.calls: list[tuple[str, str]] = []

    def __call__(
        self,
        _origin: str,
        path: str,
        *,
        method: str,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        del headers, timeout
        wanted_method, wanted_path, response = self.values.pop(0)
        assert (method, path) == (wanted_method, wanted_path)
        self.calls.append((method, path))
        return 200, response


@pytest.fixture
def bound_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary = tmp_path / "firmware.bin"
    elf = tmp_path / "firmware.elf"
    binary.write_bytes(b"bin")
    elf.write_bytes(b"elf")
    monkeypatch.setattr(once.base, "FIRMWARE_BIN", binary)
    monkeypatch.setattr(once.base, "FIRMWARE_ELF", elf)
    monkeypatch.setattr(once.base, "FIRMWARE_BIN_BYTES", 3)
    monkeypatch.setattr(once.base, "FIRMWARE_ELF_BYTES", 3)
    monkeypatch.setattr(
        once.base, "FIRMWARE_BIN_SHA256", hashlib.sha256(b"bin").hexdigest()
    )
    monkeypatch.setattr(
        once.base, "FIRMWARE_ELF_SHA256", hashlib.sha256(b"elf").hexdigest()
    )


def _write_fault_salvage_markers(tmp_path: Path) -> tuple[Path, Path]:
    claims = tmp_path / "claims"
    output = tmp_path / "result.json"
    once.base._write_new(  # noqa: SLF001
        claims / f"{pack.ACTION_ID}.qualification-attempt.json",
        once.base._seal(  # noqa: SLF001
            {
                "schema_version": 1,
                "kind": f"{once.KIND_PREFIX}-qualification-attempt",
                "created_at": "2026-08-26T08:00:00.000+08:00",
                "firmware_sha256": once.base.FIRMWARE_BIN_SHA256,
                "boot_nonce": BOOT,
                "action": once.ACTION,
                "initial_busy": 1,
                "state": "reserved_before_qualify_post",
                "no_automatic_retry": True,
            }
        ),
    )
    once.base._write_new(  # noqa: SLF001
        Path(str(output) + ".reserve"),
        once.base._seal(  # noqa: SLF001
            {
                "schema_version": 1,
                "kind": f"{once.KIND_PREFIX}-output-reservation",
                "created_at": "2026-08-26T08:00:00.001+08:00",
                "boot_nonce": BOOT,
                "final_output": str(output.resolve()),
            }
        ),
    )
    return claims, output


def test_v2_identity_is_fresh_and_canonical() -> None:
    report = pack.build_report()
    assert report["descriptor_canonical_sha256"] == pack.DESCRIPTOR_ID
    assert pack._action_id(pack.DESCRIPTOR_ID) == pack.ACTION_ID
    assert report["contract_canonical_sha256"] == pack.CONTRACT_ID
    assert pack.ACTION_ID != v1_pack.ACTION_ID
    assert pack.NVS_NAMESPACE != v1_pack.NVS_NAMESPACE
    assert pack.NVS_KEY != v1_pack.NVS_KEY
    assert report["actions"][0]["prior_static_action_id"] == v1_pack.ACTION_ID
    prerequisite = report["descriptor"]["prerequisite"]
    assert prerequisite["reset_count"] == 5
    assert prerequisite["expected_revision_bytes"] == [1, 1, 4]
    assert prerequisite["single_variable_change"] == "PER_SAMPLE_RESET_ONLY"
    assert prerequisite["exact_historical_transaction_reproduction"] is False
    assert prerequisite["legacy_mosi_high_before_reset_restored"] is False
    assert prerequisite["legacy_post_reset_tail_2us_restored"] is False


def test_v2_runner_is_isolated_from_v1() -> None:
    assert once.KIND_PREFIX.endswith("-v2")
    assert once.ENDPOINT_BASE.endswith("-v2")
    assert once.ACTION["action_id"] == pack.ACTION_ID
    assert v1_once.ACTION["action_id"] == v1_pack.ACTION_ID
    assert v1_once.ENDPOINT_BASE.endswith("-v1")


def test_v2_readiness_requires_every_sample_exact_010104() -> None:
    once._validate_readiness(_readiness())
    tampered = deepcopy(_readiness())
    tampered["cs2"]["sample2"] = {"idle": True, "bytes": [1, 1, 3]}
    with pytest.raises(once.QualifierError, match="not 010104"):
        once._validate_readiness(tampered)


def test_v2_manifest_freezes_residual_differences() -> None:
    once._validate_manifest(_manifest())
    tampered = deepcopy(_manifest())
    tampered["qualification"]["exact_historical_transaction_reproduction"] = True
    with pytest.raises(once.QualifierError, match="manifest qualification differs"):
        once._validate_manifest(tampered)


def test_v2_j2_off_diagnostic_is_exactly_four_gets(
    tmp_path: Path, bound_artifacts: None
) -> None:
    requester = ScriptedRequester(
        [
            ("GET", once.ENDPOINTS["version"], _version()),
            ("GET", once.ENDPOINTS["manifest"], _manifest()),
            ("GET", once.ENDPOINTS["status"], _ready_status()),
            ("GET", once.ENDPOINTS["report"], _not_executed_report()),
        ]
    )
    value = once.diagnose_j2_off(
        "http://192.168.1.11",
        output=tmp_path / "diagnostic.json",
        confirm_j2_off=True,
        requester=requester,
    )
    assert value["network"] == {"get": 4, "post": 0}
    assert requester.calls == [
        ("GET", once.ENDPOINTS[name])
        for name in ("version", "manifest", "status", "report")
    ]


def test_v2_cs2_zero_fault_salvage_is_four_gets_and_zero_mutation(
    tmp_path: Path, bound_artifacts: None
) -> None:
    claims, output = _write_fault_salvage_markers(tmp_path)
    requester = ScriptedRequester(
        [
            ("GET", once.ENDPOINTS["version"], _version()),
            ("GET", once.ENDPOINTS["manifest"], _manifest()),
            ("GET", once.ENDPOINTS["status"], _qualification_fault_status()),
            ("GET", once.ENDPOINTS["report"], _qualification_fault_report()),
        ]
    )
    value = once.salvage_fault(
        "http://192.168.1.11",
        claims=claims,
        output=output,
        confirm_j2_off=True,
        requester=requester,
    )
    assert requester.calls == [
        ("GET", once.ENDPOINTS[name])
        for name in ("version", "manifest", "status", "report")
    ]
    assert value["network"] == {"get": 4, "post": 0}
    assert value["permanent_claim_present"] is False
    assert value["attempt_state"] == "PERMANENTLY_CONSUMED_DO_NOT_RETRY_V2"
    assert value["raw_readiness_failure"]["failure_stage"] == (
        "cs2_revision_trivial"
    )
    assert value["raw_readiness_failure"]["cs2"]["sample1"]["bytes"] == [0, 0, 0]
    assert value["probe_command_counts"] == {
        "pon": 0,
        "pof": 0,
        "drf": 0,
        "dtm": 0,
        "lut": 0,
        "ptlw": 0,
        "command_0x86": 0,
        "visible_refresh_requests": 0,
    }
    assert output.is_file()
    assert not (claims / f"{pack.ACTION_ID}.json").exists()
    assert len(value["transcript"]) == 4


def test_v2_fault_salvage_rejects_tampered_nonzero_probe_surface(
    tmp_path: Path, bound_artifacts: None
) -> None:
    claims, output = _write_fault_salvage_markers(tmp_path)
    tampered = deepcopy(_qualification_fault_report())
    tampered["probe"]["pon_command_sent"] = True
    tampered["probe"]["command_counts"]["pon"] = 1
    requester = ScriptedRequester(
        [
            ("GET", once.ENDPOINTS["version"], _version()),
            ("GET", once.ENDPOINTS["manifest"], _manifest()),
            ("GET", once.ENDPOINTS["status"], _qualification_fault_status()),
            ("GET", once.ENDPOINTS["report"], tampered),
        ]
    )
    with pytest.raises(once.QualifierError, match="unexpectedly entered"):
        once.salvage_fault(
            "http://192.168.1.11",
            claims=claims,
            output=output,
            confirm_j2_off=True,
            requester=requester,
        )
    assert not output.exists()
    assert all(method == "GET" for method, _ in requester.calls)


def test_v2_fault_validator_accepts_early_busy_and_final_posture_failures() -> None:
    early = deepcopy(_qualification_fault_report())
    readiness = early["readiness"]
    unread = {"idle": False, "bytes": [0, 0, 0]}
    readiness.update(
        {
            "final_high_stable_ms": 0,
            "reset_count": 1,
            "revision_read_count": 0,
            "revision_command_trace": [0, 0, 0, 0],
            "failure_stage": "cs1_sample1_reset_busy",
            "all_revision_samples_exact_010104": False,
        }
    )
    for controller in ("cs1", "cs2"):
        readiness[controller] = {
            "sample1": deepcopy(unread),
            "sample2": deepcopy(unread),
            "stable": False,
            "nontrivial": False,
            "exact_010104": False,
        }
    once._validate_qualification_fault_report(early, boot_nonce=BOOT)

    final_posture = deepcopy(_qualification_fault_report())
    readiness = final_posture["readiness"]
    exact = {"idle": True, "bytes": [1, 1, 4]}
    for controller in ("cs1", "cs2"):
        readiness[controller] = {
            "sample1": deepcopy(exact),
            "sample2": deepcopy(exact),
            "stable": True,
            "nontrivial": True,
            "exact_010104": True,
        }
    readiness["all_revision_samples_exact_010104"] = True
    readiness["failure_stage"] = "final_reset_busy_not_idle_high"
    once._validate_qualification_fault_report(final_posture, boot_nonce=BOOT)


def test_v2_live_fake_requires_exact_readiness_before_single_arm_execute(
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
    first_four = [
        ("GET", once.ENDPOINTS["version"], _version()),
        ("GET", once.ENDPOINTS["manifest"], _manifest()),
        ("GET", once.ENDPOINTS["status"], _ready_status()),
        ("GET", once.ENDPOINTS["report"], _not_executed_report()),
    ]
    qualified_four = [
        ("GET", once.ENDPOINTS["version"], _version()),
        ("GET", once.ENDPOINTS["manifest"], _manifest()),
        ("GET", once.ENDPOINTS["status"], _qualified_status()),
        ("GET", once.ENDPOINTS["report"], _qualified_report()),
    ]
    requester = ScriptedRequester(
        first_four
        + [("POST", once.ENDPOINTS["qualify"], qualify)]
        + qualified_four
        + [
            ("POST", once.ENDPOINTS["arm"], arm),
            ("POST", once.ENDPOINTS["execute"], execute),
            ("GET", once.ENDPOINTS["report"], _terminal_report()),
        ]
    )
    value = once.run_once(
        "http://192.168.1.11",
        claims=tmp_path / "claims",
        output=tmp_path / "result.json",
        confirm_j2_on=True,
        requester=requester,
        poll_seconds=0,
        poll_count=1,
    )
    posts = [Path(path).name for method, path in requester.calls if method == "POST"]
    assert posts == ["qualify", "arm", "execute"]
    assert value["outcome"] == "complete_pass"
    assert value["visible_refresh_requests"] == 0


def test_v2_describe_and_dry_validate_are_offline() -> None:
    described = once.describe()
    validated = once.dry_validate()
    assert described["contract_id"] == pack.CONTRACT_ID
    assert described["action"] == once.ACTION
    assert described["read_only_fault_salvage"]["network"] == {"get": 4, "post": 0}
    assert validated["offline_only"] is True
    assert validated["network_accessed"] is False
    assert validated["pack_valid"] is True
    assert validated["live_entry_enabled"] is True
    assert all(
        item["verified"] is True
        for item in validated["artifact_binding"].values()
    )
