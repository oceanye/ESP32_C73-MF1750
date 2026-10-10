from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

import pytest

from tools import (
    mf1750_runtime_lut_cross_palette_partial_hold_v1_white_containment_once as once,
)
from tools import (
    mf1750_runtime_lut_cross_palette_partial_hold_v1_white_containment_pack as pack,
)


ROOT = Path(__file__).resolve().parents[1]
RUNNING_SHA = "a" * 64


def _identity() -> dict[str, Any]:
    return {
        "build_tag": pack.BUILD_TAG,
        "test_id": pack.TEST_ID,
        "campaign_id": pack.CAMPAIGN_ID,
        "profile_id": pack.PROFILE_ID,
        "environment": pack.ENVIRONMENT,
        "device_api_version": pack.DEVICE_API_VERSION,
        "identity_revision": pack.IDENTITY_REVISION,
        "running_app_elf_sha256": RUNNING_SHA,
        "contract_id": pack.CONTRACT_ID,
        "transaction_descriptor_sha256": pack.DESCRIPTOR_ID,
        "transaction_descriptor_marker": pack.DESCRIPTOR_MARKER,
    }


def _version() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-version",
        **_identity(),
        "classification": pack.CLASSIFICATION,
        "profile": {"profile_id": pack.PROFILE_ID},
        "action_count": 1,
        "startup_refresh": False,
        "raw_ingress": False,
        "retry": False,
        "automatic_chaining": False,
        "profile_switch": False,
        "runtime_payload_present": False,
        "live_authorized": False,
    }


def _manifest() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-manifest",
        **_identity(),
        "classification": pack.CLASSIFICATION,
        "action_count": 1,
        "one_driver_call_per_action": True,
        "startup_refresh": False,
        "raw_frame_ingress": False,
        "raw_lut_ingress": False,
        "electrical_parameter_ingress": False,
        "timing_parameter_ingress": False,
        "runtime_payload_present": False,
        "generated_include": None,
        "runtime_psr_present": False,
        "hidden_lut_command_present": False,
        "r20_present": False,
        "r21_present": False,
        "vcom_write": False,
        "vcom_sweep": False,
        "vcom_write_or_sweep": False,
        "retry": False,
        "automatic_chaining": False,
        "automatic_recovery": False,
        "profile_switch": False,
        "requires_new_exact_authorization": True,
        "j2_state_is_operator_assertion_not_firmware_detection": True,
        "factory_path": {"hard_reset": True},
        "actions": [once.ACTION],
        "unproven_assumptions": [],
        "nvs_contract": {
            "namespace": pack.NVS_NAMESPACE,
            "key": pack.NVS_KEY,
            "encoding": "uint16_high_byte_phase_low_byte_ordinal",
            "initial_cursor": 1,
            "terminal_cursor": 2,
            "clear_route": False,
            "persistent_across_reboot": True,
        },
    }


def _status(*, busy: int = 1, complete: bool = False) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-status",
        **_identity(),
        "boot_nonce": "0123456789abcdef",
        "state": "complete" if complete else "ready",
        "phase": 0,
        "phase_name": "READY",
        "cursor_raw": 2 if complete else 1,
        "next_ordinal": 2 if complete else 1,
        "campaign_complete": complete,
        "cursor_valid": True,
        "persistent_key_present": complete,
        "fixture_self_check_passed": True,
        "execute_pending": False,
        "arm_request_count": 1 if complete else 0,
        "execute_request_count": 1 if complete else 0,
        "total_driver_call_count": 1 if complete else 0,
        "gpio_initialized": True,
        "busy": busy,
        "rst": 0,
        "cs": 0,
        "cs2": 0,
        "sck": 0,
        "dc": 0,
        "mosi": 0,
    }


def _fresh_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-report",
        "valid": False,
        **_identity(),
        "terminal_state": "NOT_EXECUTED",
        "result": False,
        "driver_called": False,
        "driver_call_count_for_action": 0,
        "no_retry": True,
    }


def _complete_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-report",
        "valid": True,
        **_identity(),
        "ordinal": 1,
        "action_id": pack.ACTION_ID,
        "terminal_state": "COMPLETE",
        "result": True,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "next_ordinal": 2,
        "campaign_complete": True,
        "no_retry": True,
        "job_queued_at_ms": 1,
        "job_started_at_ms": 2,
        "job_finished_at_ms": 3,
        "driver": {
            "valid": True,
            "running": False,
            "sequence_ok": True,
            "wait_timeout": False,
            "busy_assertion_missing": False,
            "mapping_applied": True,
            "pon_busy_seen": True,
            "drf_busy_seen": True,
            "pof_busy_seen": True,
            "pre_command_idle_failure": False,
            "input_fnv1a": pack.FRAME_FNV1A,
            "cs1_dtm_fnv1a": pack.DTM_FNV1A,
            "cs2_dtm_fnv1a": pack.DTM_FNV1A,
            "busy_trace": {
                "idle_level": 1,
                "safe_finish": {"busy_after_pins_low": 1, "busy_after_5ms": 1},
                "final_gpio": {
                    "busy": 1,
                    "rst": 0,
                    "cs": 0,
                    "cs2": 0,
                    "sck": 0,
                    "dc": 0,
                    "mosi": 0,
                },
            },
        },
    }


class FakeDevice:
    def __init__(self, *, busy: int = 1, bad_driver: bool = False) -> None:
        self.busy = busy
        self.bad_driver = bad_driver
        self.executed = False
        self.calls: list[tuple[str, str]] = []

    def __call__(
        self,
        _base_url: str,
        path: str,
        *,
        method: str,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        assert timeout > 0
        name = path.rsplit("/", 1)[-1]
        self.calls.append((method, name))
        if method == "GET":
            assert headers is None
            if name == "version":
                return 200, _version()
            if name == "manifest":
                return 200, _manifest()
            if name == "status":
                return 200, _status(busy=self.busy, complete=self.executed)
            if name == "report":
                if not self.executed:
                    return 200, _fresh_report()
                report = _complete_report()
                if self.bad_driver:
                    report["driver"]["drf_busy_seen"] = False
                return 200, report
        assert method == "POST" and headers is not None
        if name == "arm":
            assert headers["X-EC5-Intent"] == pack.ARM_INTENT
            return 201, {
                "accepted": True,
                "armed": True,
                **_identity(),
                "ordinal": 1,
                "action_id": pack.ACTION_ID,
                "boot_nonce": "0123456789abcdef",
                "arm_nonce": "fedcba9876543210",
                "not_hardware_authorization": True,
            }
        if name == "execute":
            assert headers["X-EC5-Intent"] == pack.EXECUTE_INTENT
            self.executed = True
            return 202, {
                "accepted": True,
                "job_id": 1,
                **_identity(),
                "action_id": pack.ACTION_ID,
                "execute_consumed": True,
                "no_retry": True,
            }
        raise AssertionError((method, name))


def test_pack_binds_exact_fresh_artifacts_and_embedded_identity() -> None:
    report = pack.build_report()
    binary = ROOT / pack.FIRMWARE_BIN
    elf = ROOT / pack.FIRMWARE_ELF
    assert binary.stat().st_size == pack.FIRMWARE_BIN_BYTES == 786_528
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == pack.FIRMWARE_BIN_SHA256
    assert elf.stat().st_size == pack.FIRMWARE_ELF_BYTES == 13_214_020
    assert hashlib.sha256(elf.read_bytes()).hexdigest() == pack.FIRMWARE_ELF_SHA256
    for marker in (
        pack.BUILD_TAG,
        pack.CONTRACT_ID,
        pack.NVS_NAMESPACE,
        pack.DESCRIPTOR_MARKER,
    ):
        assert marker.encode("ascii") in elf.read_bytes()
    assert report["contract"]["busy_qualification"]["busy_zero_accepted"] is False


def test_describe_is_offline_nonautomatic_and_single_action() -> None:
    value = once.describe()
    assert value["offline_only"] is True
    assert value["network_requests"] == 0
    assert value["visible_refreshes"] == 0
    assert value["firmware_busy_gates"] == ["ARM", "EXECUTE", "DISPATCH"]
    assert value["host_preflight_busy"] == "RAW_READY_BUSY_1_ONLY"
    assert value["blocking_refresh_first_poll_floor_seconds"] == 65.0
    assert value["automatic_retry"] is False
    assert value["automatic_recovery"] is False
    assert value["automatic_chaining"] is False
    assert value["ordinal_skip"] is False
    assert value["artifact_binding_status"]["firmware_bin"]["verified"] is True
    assert value["artifact_binding_status"]["firmware_elf"]["verified"] is True


def test_direct_script_describe_smoke() -> None:
    script = (
        ROOT
        / "tools"
        / "mf1750_runtime_lut_cross_palette_partial_hold_v1_"
        "white_containment_once.py"
    )
    completed = subprocess.run(
        [sys.executable, str(script), "describe"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["automatic_execution"] is False


def test_exact_one_action_completes_with_two_posts(
    tmp_path: Path,
) -> None:
    fake = FakeDevice()
    output = tmp_path / "result.json"
    result = once.run_once(
        "http://192.0.2.1",
        claims=tmp_path / "claims",
        output=output,
        requester=fake,
        poll_seconds=65,
        poll_count=1,
        sleeper=lambda _seconds: None,
    )
    assert result["outcome"] == "complete_pass"
    assert [call for call in fake.calls if call[0] == "POST"] == [
        ("POST", "arm"),
        ("POST", "execute"),
    ]
    assert result["no_retry"] is True
    assert result["no_recovery"] is True
    assert result["no_autochain"] is True
    assert json.loads(output.read_text(encoding="utf-8"))["outcome"] == "complete_pass"


def test_busy_low_fails_before_any_post_and_consumes_claim(tmp_path: Path) -> None:
    fake = FakeDevice(busy=0)
    claims = tmp_path / "claims"
    with pytest.raises(once.ContainmentConsumedError, match="busy"):
        once.run_once(
            "http://192.0.2.1",
            claims=claims,
            output=tmp_path / "result.json",
            requester=fake,
            poll_seconds=65,
            poll_count=1,
            sleeper=lambda _seconds: None,
        )
    assert not [call for call in fake.calls if call[0] == "POST"]
    assert (claims / f"{pack.ACTION_ID}.json").is_file()


def test_duplicate_claim_refuses_before_network(tmp_path: Path) -> None:
    fake = FakeDevice()
    claims = tmp_path / "claims"
    once._create_claim(claims)  # noqa: SLF001
    with pytest.raises(once.ContainmentConsumedError, match="permanently claimed"):
        once.run_once(
            "http://192.0.2.1",
            claims=claims,
            output=tmp_path / "result.json",
            requester=fake,
        )
    assert fake.calls == []


def test_corrupt_terminal_evidence_is_never_accepted_or_retried(tmp_path: Path) -> None:
    fake = FakeDevice(bad_driver=True)
    with pytest.raises(once.ContainmentConsumedError, match="drf_busy_seen"):
        once.run_once(
            "http://192.0.2.1",
            claims=tmp_path / "claims",
            output=tmp_path / "result.json",
            requester=fake,
            poll_seconds=65,
            poll_count=1,
            sleeper=lambda _seconds: None,
        )
    assert [call for call in fake.calls if call[0] == "POST"] == [
        ("POST", "arm"),
        ("POST", "execute"),
    ]


def test_sub_65_second_first_poll_is_rejected_before_network(tmp_path: Path) -> None:
    fake = FakeDevice()
    with pytest.raises(once.ContainmentError, match="65..300"):
        once.run_once(
            "http://192.0.2.1",
            claims=tmp_path / "claims",
            output=tmp_path / "result.json",
            requester=fake,
            poll_seconds=64.999,
            poll_count=1,
            sleeper=lambda _seconds: None,
        )
    assert fake.calls == []
    assert not (tmp_path / "claims").exists()


def test_missing_clean_tree_artifact_fails_before_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeDevice()
    monkeypatch.setattr(pack, "FIRMWARE_BIN", tmp_path / "missing-firmware.bin")
    with pytest.raises(ValueError, match="BIN binding differs"):
        once.run_once(
            "http://192.0.2.1",
            claims=tmp_path / "claims",
            output=tmp_path / "result.json",
            requester=fake,
        )
    assert fake.calls == []
    assert not (tmp_path / "claims").exists()
