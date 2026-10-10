from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

import pytest

from tools import (
    mf1750_raw_p16_crossover_w8_t4_v3_fault_white_v1_once as w8_once,
)
from tools import (
    mf1750_raw_p16_crossover_w8_t4_v3_fault_white_v1_pack as w8,
)
from tools import (
    mf1750_raw_p16_crossover_w9_w8_arm400_successor_white_v1_once as once,
)
from tools import (
    mf1750_raw_p16_crossover_w9_w8_arm400_successor_white_v1_pack as w9,
)


def _wire_identity(host: Any) -> dict[str, Any]:
    adapter = host.pack
    return {
        "build_tag": adapter.BUILD_TAG,
        "test_id": adapter.TEST_ID,
        "campaign_id": adapter.CAMPAIGN_ID,
        "profile_id": adapter.PROFILE_ID,
        "environment": adapter.ENVIRONMENT,
        "device_api_version": adapter.DEVICE_API_VERSION,
        "identity_revision": adapter.IDENTITY_REVISION,
        "running_app_elf_sha256": adapter.FIRMWARE_ELF_SHA256,
        "contract_id": adapter.CONTRACT_ID,
        "transaction_descriptor_sha256": adapter.DESCRIPTOR_ID,
        "transaction_descriptor_marker": adapter.DESCRIPTOR_MARKER,
    }


def _wire_version(host: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-version",
        **_wire_identity(host),
        "classification": host.pack.CLASSIFICATION,
        "action_count": 1,
        "startup_refresh": False,
        "raw_ingress": False,
        "retry": False,
        "automatic_chaining": False,
        "profile_switch": False,
        "runtime_payload_present": False,
        "live_authorized": False,
    }


def _wire_manifest(host: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-manifest",
        **_wire_identity(host),
        "classification": host.pack.CLASSIFICATION,
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
        "vcom_write_or_sweep": False,
        "retry": False,
        "automatic_chaining": False,
        "automatic_recovery": False,
        "profile_switch": False,
        "requires_new_exact_authorization": True,
        "actions": [host.ACTION],
        "nvs_contract": {
            "namespace": host.pack.NVS_NAMESPACE,
            "key": host.pack.NVS_KEY,
            "initial_cursor": 1,
            "terminal_cursor": 2,
            "clear_route": False,
            "persistent_across_reboot": True,
        },
    }


def _wire_status(host: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-status",
        **_wire_identity(host),
        "boot_nonce": "0123456789abcdef",
        "state": "ready",
        "phase": 0,
        "phase_name": "READY",
        "cursor_raw": 1,
        "next_ordinal": 1,
        "campaign_complete": False,
        "cursor_valid": True,
        "persistent_key_present": False,
        "fixture_self_check_passed": True,
        "execute_pending": False,
        "arm_request_count": 0,
        "execute_request_count": 0,
        "total_driver_call_count": 0,
        "gpio_initialized": True,
        "busy": 1,
        "rst": 0,
        "cs": 0,
        "cs2": 0,
        "sck": 0,
        "dc": 0,
        "mosi": 0,
    }


def _wire_fresh_report(host: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-report",
        **_wire_identity(host),
        "valid": False,
        "terminal_state": "NOT_EXECUTED",
        "result": False,
        "driver_called": False,
        "driver_call_count_for_action": 0,
        "no_retry": True,
    }


def _wire_complete_report(host: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-report",
        **_wire_identity(host),
        "valid": True,
        "ordinal": 1,
        "action_id": host.pack.ACTION_ID,
        "terminal_state": "COMPLETE",
        "result": True,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "next_ordinal": 2,
        "campaign_complete": True,
        "no_retry": True,
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
            "input_fnv1a": host.pack.FRAME_FNV1A,
            "cs1_dtm_fnv1a": host.pack.DTM_FNV1A,
            "cs2_dtm_fnv1a": host.pack.DTM_FNV1A,
            "busy_trace": {
                "idle_level": 1,
                "safe_finish": {
                    "busy_after_pins_low": 1,
                    "busy_after_5ms": 1,
                },
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


class _W9WireDevice:
    def __init__(self, host: Any) -> None:
        self.host = host
        self.executed = False
        self.post_intents: list[tuple[str, str]] = []

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
        assert path.startswith(f"{w9.CONFIG.base_route}/")
        endpoint = path.rsplit("/", 1)[-1]
        if method == "GET":
            if endpoint == "version":
                return 200, _wire_version(self.host)
            if endpoint == "manifest":
                return 200, _wire_manifest(self.host)
            if endpoint == "status":
                return 200, _wire_status(self.host)
            if endpoint == "report":
                report = (
                    _wire_complete_report(self.host)
                    if self.executed
                    else _wire_fresh_report(self.host)
                )
                return 200, report
        assert headers is not None
        intent = headers["X-EC5-Intent"]
        self.post_intents.append((endpoint, intent))
        if endpoint == "arm":
            return 201, {
                "accepted": True,
                "armed": True,
                **_wire_identity(self.host),
                "ordinal": 1,
                "action_id": self.host.pack.ACTION_ID,
                "boot_nonce": "0123456789abcdef",
                "arm_nonce": "fedcba9876543210",
            }
        if endpoint == "execute":
            self.executed = True
            return 202, {
                "accepted": True,
                "job_id": 1,
                **_wire_identity(self.host),
                "action_id": self.host.pack.ACTION_ID,
                "execute_consumed": True,
                "no_retry": True,
            }
        raise AssertionError((method, endpoint))


def test_w9_configured_host_intents_exactly_match_shared_firmware_literals() -> None:
    firmware = w9.shared_firmware_intents()
    assert firmware == {
        "arm": "ARM_ONE_FIXED_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION",
        "execute": "EXECUTE_ONE_FIXED_FACTORY_OTP_WHITE_ONCE",
    }
    assert w9.validate_intent_parity() == firmware

    host = once._configure_white()  # noqa: SLF001
    assert host.pack.ARM_INTENT == w9.WHITE_ARM_INTENT == firmware["arm"]
    assert (
        host.pack.EXECUTE_INTENT
        == w9.WHITE_EXECUTE_INTENT
        == firmware["execute"]
    )


def test_w9_dynamic_wire_path_posts_shared_firmware_intents(tmp_path: Path) -> None:
    host = once._configure_white()  # noqa: SLF001
    device = _W9WireDevice(host)
    result = host.run_once(
        "http://192.0.2.1",
        claims=tmp_path / "claims",
        output=tmp_path / "result.json",
        confirm_j2_on=True,
        requester=device,
        poll_seconds=65.0,
        poll_count=1,
        sleeper=lambda _seconds: None,
    )

    firmware = w9.shared_firmware_intents()
    assert device.post_intents == [
        ("arm", firmware["arm"]),
        ("execute", firmware["execute"]),
    ]
    assert result["network"] == {"get": 5, "post": 2}
    assert result["outcome"] == "complete_pass"


def test_w9_sealed_bin_and_elf_embed_only_the_correct_white_intents() -> None:
    expected = w9.WHITE_ARTIFACTS[w9.STAGE]
    wrong_w8_intents = {
        w8.WHITE_ARM_INTENT,
        w8.WHITE_EXECUTE_INTENT,
    }
    assert wrong_w8_intents == {
        "ARM_ONE_FIXED_FAULT_BOUND_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION",
        "EXECUTE_ONE_FIXED_FAULT_BOUND_FACTORY_OTP_WHITE_ONCE",
    }
    assert wrong_w8_intents.isdisjoint(
        {w9.WHITE_ARM_INTENT, w9.WHITE_EXECUTE_INTENT}
    )

    for label, path, byte_key, sha_key in (
        ("bin", w9.white_artifact_paths()[0], "bin_bytes", "bin_sha256"),
        ("elf", w9.white_artifact_paths()[1], "elf_bytes", "elf_sha256"),
    ):
        payload = path.read_bytes()
        assert len(payload) == expected[byte_key], label
        assert hashlib.sha256(payload).hexdigest() == expected[sha_key], label
        for intent in (w9.WHITE_ARM_INTENT, w9.WHITE_EXECUTE_INTENT):
            assert intent.encode("ascii") in payload, (label, intent)
        for stale_intent in wrong_w8_intents:
            assert stale_intent.encode("ascii") not in payload, (
                label,
                stale_intent,
            )


def test_w9_identity_route_nvs_action_and_outputs_do_not_reuse_w8() -> None:
    fresh = w9.build_white_report()
    stale = w8.build_white_report()
    fresh_contract = fresh["contract"]
    stale_contract = stale["contract"]
    fresh_action = fresh["action"]
    stale_action = stale["action"]

    for fresh_value, stale_value in (
        (fresh["contract_id"], stale["contract_id"]),
        (fresh_action["descriptor_id"], stale_action["descriptor_id"]),
        (fresh_action["action_id"], stale_action["action_id"]),
        (w9.CONFIG.build_tag, w8.CONFIG.build_tag),
        (w9.CONFIG.test_id, w8.CONFIG.test_id),
        (w9.CONFIG.campaign_id, w8.CONFIG.campaign_id),
        (w9.DEVICE_API_VERSION, w8.DEVICE_API_VERSION),
        (w9.IDENTITY_REVISION, w8.IDENTITY_REVISION),
        (fresh_contract["base_route"], stale_contract["base_route"]),
        (fresh_contract["nvs_namespace"], stale_contract["nvs_namespace"]),
        (fresh_contract["nvs_key"], stale_contract["nvs_key"]),
        (once._output_root(), w8_once._output_root()),  # noqa: SLF001
        (once._claim_root(), w8_once._claim_root()),  # noqa: SLF001
    ):
        assert fresh_value != stale_value

    assert fresh_action["source_action_id"] == stale_action["action_id"]
    assert fresh_action["action_id"] not in fresh_contract[
        "rejected_obsolete_white_action_ids"
    ]
    assert stale_action["action_id"] in fresh_contract[
        "rejected_obsolete_white_action_ids"
    ]


def test_w9_authority_is_exactly_w8_four_get_arm400_without_execute_or_driver() -> None:
    authority = w9.validate_predecessor_authority()
    attempt = authority["w8_attempt"]
    transcript = attempt["transcript"]

    assert attempt["network"] == {"get": 4, "post": 1}
    assert [
        (item["method"], item["endpoint"], item["status"])
        for item in transcript
    ] == [
        ("GET", "version", 200),
        ("GET", "manifest", 200),
        ("GET", "status", 200),
        ("GET", "report", 200),
        ("POST", "arm", 400),
    ]
    assert all(item["endpoint"] != "execute" for item in transcript)
    assert transcript[-1]["body"] == {
        "accepted": False,
        "error": "intent_mismatch",
        "fault_locked": True,
        "no_retry": True,
    }
    assert transcript[-1]["headers"]["X-EC5-Intent"] == w8.WHITE_ARM_INTENT

    status = transcript[2]["body"]
    report = transcript[3]["body"]
    assert status["execute_request_count"] == 0
    assert status["total_driver_call_count"] == 0
    assert report["terminal_state"] == "NOT_EXECUTED"
    assert report["driver_called"] is False
    assert report["driver_call_count_for_action"] == 0
    assert attempt["visible_refresh_may_have_occurred"] is False
    assert attempt["visible_refreshes_confirmed"] == 0


def test_w9_run_without_fresh_diagnostic_fails_before_request_or_claim(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events: list[str] = []
    claim_root = tmp_path / "claims-must-not-be-created"

    monkeypatch.setattr(once, "_verify_artifacts", lambda: events.append("artifacts"))
    monkeypatch.setattr(
        once,
        "_verify_predecessor_authority_chain",
        lambda: events.append("authority"),
    )
    monkeypatch.setattr(once, "_diagnostic_path", lambda: tmp_path / "missing.json")
    monkeypatch.setattr(once, "_claim_root", lambda: claim_root)

    def forbid_host_construction() -> None:
        events.append("host")
        raise AssertionError("host construction would permit a request path")

    monkeypatch.setattr(once, "_configure_white", forbid_host_construction)

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
    assert not claim_root.exists()
