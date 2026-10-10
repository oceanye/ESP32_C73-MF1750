from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from tools import mf1750_runtime_lut_partial_hold_repeat_ptlw_v3_once as once
from tools import mf1750_runtime_lut_partial_hold_repeat_ptlw_v3_pack as pack


ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = (
    ROOT
    / ".pio"
    / "build-runtime-lut-partial-hold-repeat-ptlw-v3"
    / "ec5_runtime_lut_partial_hold_repeat_ptlw_v3"
)


def _identity(kind: str) -> dict[str, Any]:
    runner = once.base.runner
    return {
        "kind": f"{runner.DEVICE_KIND_PREFIX}-{kind}",
        "build_tag": runner.BUILD_TAG,
        "test_id": runner.TEST_ID,
        "campaign_id": runner.CAMPAIGN_ID,
        "device_api_version": runner.DEVICE_API_VERSION,
        "identity_revision": runner.IDENTITY_REVISION,
        "contract_id": runner.CONTRACT_ID,
        "classification": runner.CLASSIFICATION,
    }


def _capabilities() -> dict[str, bool]:
    return {
        "partial_refresh": True,
        "window_refresh": True,
        "command_0x83": True,
        "command_0x86": False,
        "mid_refresh_power_cut": False,
        "spi_frequency_sweep": False,
        "full_screen_global_refresh": True,
        "factory_otp_white_actions": True,
        "same_palette_hold_probe": True,
        "cross_palette_hold_probe": False,
        "busy_qualified_arm_execute_dispatch": True,
    }


def _baseline() -> dict[str, Any]:
    return {
        "ordinal": 1,
        "role": "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
        "external_anchor_required": False,
        "anchor_established_by_firmware": True,
        "one_visible_refresh_required": True,
        "runtime_code7_action_reachable": False,
        "factory_otp_recovery_ordinal": 5,
    }


def _version() -> dict[str, Any]:
    runner = once.base.runner
    return {
        **_identity("version"),
        "layout_id": pack.VARIANT_KEY,
        "profile_source": once._PROFILE_SOURCE,  # noqa: SLF001
        "action_count": 5,
        "factory_otp": True,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        **{
            key: False
            for key in (
                "automatic_execute",
                "automatic_chaining",
                "startup_refresh",
                "raw_frame_ingress",
                "electrical_parameter_write",
                "dither",
                "spatial_mixing",
                "retry",
                "recovery",
            )
        },
        "nvs_contract": {
            "namespace": runner.NVS_NAMESPACE,
            "key": runner.NVS_KEY,
            "terminal_next_ordinal": 6,
        },
        "baseline_contract": _baseline(),
        **_capabilities(),
    }


def _manifest() -> dict[str, Any]:
    profile = once.REPORT["contract"]["profile"]
    return {
        **_identity("manifest"),
        "layout_id": pack.VARIANT_KEY,
        "profile_source": once._PROFILE_SOURCE,  # noqa: SLF001
        "actions": list(once.base.runner.ACTIONS),
        "action_count": 5,
        "one_driver_call_per_action": True,
        "factory_otp": True,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "recovery": False,
        "baseline_contract": _baseline(),
        "history_layout": {
            "factory_otp_anchor_ordinal": 1,
            "factory_otp_recovery_ordinal": 5,
            "factory_otp_white_frame_fill_byte": 0x11,
            "factory_otp_white_frame_bytes": 307_200,
            "anchor_established_by_firmware": True,
            "external_factory_white_anchor_required": False,
            "runtime_code7_action_reachable": False,
            "runtime_transport_codes": [3, 5, 6],
            "ptlw_command": 0x83,
            "ptlw_payload_bytes": 9,
            "ptlw_endpoint_contract": "xe=x+w-1;ye=y+h-1",
            "ptlw_mode": 1,
            "ptlw_writes_per_controller": 2,
            "initial_ptlw_before_cropped_dtm": True,
            "repeat_ptlw_after_pon_busy": True,
            "pre_pon_cdi_ff_preserved": True,
            "post_pon_sequence": [
                "PTLW_CS1",
                "PTLW_CS2",
                "CDI_FF_BOTH",
                "BTST2",
                "DRF",
            ],
            "pon_timeout_ms": 60_000,
            "cropped_dtm": True,
            "packed_bpp": 4,
            "windows_disjoint": True,
            "cs2_position_mirrored": False,
            "runtime_lut_profile_id": pack.PROFILE_ID,
            "global_header_profile": "legacy_active",
            "sequential_hold_observation_required": True,
            "camera_required": False,
            "busy_idle_level_required": 1,
            "busy_zero_accepted": False,
            **profile,
        },
        **_capabilities(),
    }


def _fresh_report(boot_nonce: str) -> dict[str, Any]:
    return {
        **_identity("report"),
        "boot_nonce": boot_nonce,
        "valid": False,
        "ordinal": None,
        "descriptor_id": None,
        "action_id": None,
        "terminal_state": "NOT_EXECUTED",
        "result": False,
        "error": "no_execute_report",
        "driver_called": False,
        "driver_call_count_for_action": 0,
        "total_driver_call_count": 0,
        "phase": 0,
        "next_ordinal": 1,
        "no_retry": True,
        "no_recovery": True,
    }


def _complete_report(ordinal: int, boot_nonce: str) -> dict[str, Any]:
    action = once.base.runner.ACTIONS[ordinal - 1]
    source = once.REPORT["actions"][ordinal - 1]
    return {
        **_identity("report"),
        "boot_nonce": boot_nonce,
        "valid": True,
        "terminal_state": "COMPLETE",
        "result": True,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": ordinal,
        "ordinal": ordinal,
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "role": action["role"],
        "branch": action["branch"],
        "phase": 0,
        "phase_name": "READY",
        "next_ordinal": ordinal + 1,
        "campaign_complete": ordinal == 5,
        "no_retry": True,
        "no_recovery": True,
        "driver": {
            "operation_id": ordinal,
            "valid": True,
            "running": False,
            "sequence_ok": True,
            "wait_timeout": False,
            "busy_assertion_missing": False,
            "pre_command_idle_failure": False,
            "failure_stage": "none",
            "timeout_stage": "none",
            "busy_missing_stage": "none",
            "pre_command_busy_stage": "none",
            "spi_hz": 1_000_000,
            "pon_busy_seen": True,
            "drf_busy_seen": True,
            "pof_busy_seen": True,
            "pon_ms": 260,
            "drf_ms": 33_930,
            "pof_ms": 20,
            "input_fnv1a": source["frame"]["fnv1a"],
            "cs1_dtm_fnv1a": source["cs1_dtm"]["fnv1a"],
            "cs2_dtm_fnv1a": source["cs2_dtm"]["fnv1a"],
            "safe_finish": {
                "busy_before_pins_low": 1,
                "busy_after_pins_low": 1,
                "busy_after_5ms": 1,
                "final_gpio": {"busy": 1, "rst": 0, "cs": 0, "cs2": 0},
            },
        },
    }


class V3Fake:
    def __init__(
        self,
        ordinal: int,
        *,
        busy: int = 1,
        prior_boot_nonce: str | None = None,
        complete_driver_overrides: Mapping[str, Any] | None = None,
    ) -> None:
        self.ordinal = ordinal
        self.busy = busy
        self.boot_nonce = "0123456789abcdef"
        self.prior_boot_nonce = prior_boot_nonce
        self.complete_driver_overrides = dict(complete_driver_overrides or {})
        self.executed = False
        self.calls: list[tuple[str, str]] = []

    def status(self) -> dict[str, Any]:
        return {
            **_identity("status"),
            "boot_nonce": self.boot_nonce,
            "state": "ready",
            "phase": 0,
            "phase_name": "READY",
            "cursor_raw": self.ordinal,
            "next_ordinal": self.ordinal,
            "current_action": None,
            "campaign_complete": False,
            "fixture_self_check_passed": True,
            "cursor_valid": True,
            "gpio_initialized": True,
            "busy": self.busy,
            "rst": 0,
            "cs": 0,
            "cs2": 0,
            "execute_pending": False,
            "persistent_key_present": self.ordinal != 1,
            "arm_request_count": self.ordinal - 1,
            "execute_request_count": self.ordinal - 1,
            "total_driver_call_count": self.ordinal - 1,
        }

    def report(self) -> dict[str, Any]:
        if self.executed:
            value = _complete_report(self.ordinal, self.boot_nonce)
            value["driver"].update(self.complete_driver_overrides)
            return value
        if self.ordinal == 1:
            return _fresh_report(self.boot_nonce)
        return _complete_report(
            self.ordinal - 1, self.prior_boot_nonce or self.boot_nonce
        )

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
            values = {
                "version": _version(),
                "manifest": _manifest(),
                "status": self.status(),
                "report": self.report(),
            }
            return 200, values[name]
        assert method == "POST"
        assert headers is not None
        action = once.base.runner.ACTIONS[self.ordinal - 1]
        if name == "arm":
            return 200, {
                "accepted": True,
                "armed": True,
                "action_id": action["action_id"],
                "boot_nonce": self.boot_nonce,
                "arm_nonce": "fedcba9876543210",
            }
        if name == "execute":
            self.executed = True
            return 200, {
                "accepted": True,
                "execute_consumed": True,
                "action_id": action["action_id"],
                "boot_nonce": self.boot_nonce,
            }
        raise AssertionError(name)


def _set_path(value: dict[str, Any], path: str, bad: Any) -> None:
    target: dict[str, Any] = value
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = bad


def test_v3_runner_binds_final_binary_routes_identity_and_nvs() -> None:
    firmware = BUILD_DIR / "firmware.bin"
    assert firmware.stat().st_size == once.base.runner.FIRMWARE_BYTES == 796_496
    assert hashlib.sha256(firmware.read_bytes()).hexdigest() == (
        once.base.runner.FIRMWARE_SHA256
    )
    assert once.base.runner.CONTRACT_ID == (
        "4c5f008e1ef770d9ea1523f41cee7b9d06b4cb9f8bf05d6bfd2f65f9a3aff7a0"
    )
    assert once.base.runner.NVS_NAMESPACE == "rlph_rptlw_v3"
    assert once.base.runner.NVS_KEY == "cursor_rptv3"
    assert all("repeat-ptlw-v3" in path for path in once.base.runner.ENDPOINTS.values())


def test_describe_exposes_strict_v3_gates() -> None:
    value = once.describe()
    assert value["firmware_binding"]["bound"] is True
    assert value["preflight_busy_contract"] == {
        "ordinals_1_to_5": "RAW_READY_BUSY_1_ONLY",
        "busy_zero_accepted": False,
        "firmware_gates": ["ARM", "EXECUTE", "DISPATCH"],
    }
    assert value["fixed_transport"][
        "blocking_refresh_first_poll_floor_seconds"
    ] == 65.0
    assert value["automatic_retry"] is False
    assert value["automatic_chaining"] is False


@pytest.mark.parametrize("ordinal", (1, 2, 3, 4, 5))
def test_every_ordinal_requires_ready_busy_high(ordinal: int) -> None:
    fake = V3Fake(ordinal, busy=1)
    boot_nonce, transcript, _ = once._preflight(  # noqa: SLF001
        "http://192.0.2.1", ordinal, expected_busy=1, requester=fake
    )
    assert boot_nonce == fake.boot_nonce
    assert len(transcript) == 4
    low = V3Fake(ordinal, busy=0)
    with pytest.raises(once.base.runner.RecheckError, match="BUSY=1"):
        once._preflight(  # noqa: SLF001
            "http://192.0.2.1", ordinal, expected_busy=1, requester=low
        )


def test_ordinal1_requires_fresh_report_and_later_requires_same_boot() -> None:
    fresh = V3Fake(1)
    fresh.executed = True
    with pytest.raises(once.base.runner.RecheckError):
        once._preflight(  # noqa: SLF001
            "http://192.0.2.1", 1, expected_busy=1, requester=fresh
        )
    wrong_boot = V3Fake(3, prior_boot_nonce="fedcba9876543210")
    with pytest.raises(once.base.runner.RecheckError, match="boot nonce"):
        once._preflight(  # noqa: SLF001
            "http://192.0.2.1", 3, expected_busy=1, requester=wrong_boot
        )


@pytest.mark.parametrize("ordinal", (1, 2, 3, 4, 5))
def test_strict_complete_accepts_exact_evidence(ordinal: int) -> None:
    once._validate_complete_report(  # noqa: SLF001
        _complete_report(ordinal, "0123456789abcdef"),
        ordinal,
        "0123456789abcdef",
    )


@pytest.mark.parametrize(
    ("path", "bad"),
    (
        ("total_driver_call_count", 0),
        ("driver.operation_id", 0),
        ("driver.sequence_ok", False),
        ("driver.wait_timeout", True),
        ("driver.pon_busy_seen", False),
        ("driver.drf_busy_seen", False),
        ("driver.pof_busy_seen", False),
        ("driver.pon_ms", 0),
        ("driver.drf_ms", 0),
        ("driver.pof_ms", 0),
        ("driver.timeout_stage", "PON"),
        ("driver.busy_missing_stage", "DRF"),
        ("driver.pre_command_busy_stage", "POF"),
        ("driver.input_fnv1a", 0),
        ("driver.cs1_dtm_fnv1a", 0),
        ("driver.cs2_dtm_fnv1a", 0),
        ("driver.safe_finish.busy_before_pins_low", 0),
        ("driver.safe_finish.busy_after_pins_low", 0),
        ("driver.safe_finish.busy_after_5ms", 0),
        ("driver.safe_finish.final_gpio.busy", 0),
        ("driver.safe_finish.final_gpio.rst", 1),
        ("driver.safe_finish.final_gpio.cs", 1),
        ("driver.safe_finish.final_gpio.cs2", 1),
    ),
)
def test_strict_complete_rejects_each_critical_field(path: str, bad: Any) -> None:
    report = _complete_report(2, "0123456789abcdef")
    _set_path(report, path, bad)
    with pytest.raises(once.base.runner.RecheckError):
        once._validate_complete_report(  # noqa: SLF001
            report, 2, "0123456789abcdef"
        )


def test_run_rejects_sub_65s_poll_floor_before_network(tmp_path: Path) -> None:
    fake = V3Fake(1)
    with pytest.raises(once.base.runner.RecheckError, match=">= 65"):
        once.run_once(
            "http://192.0.2.1",
            1,
            claims=tmp_path / "claims",
            output=tmp_path / "result.json",
            requester=fake,
            poll_seconds=64.999,
        )
    assert fake.calls == []


def test_strict_complete_rejection_is_consumed_and_never_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(once.v1.time, "sleep", lambda _seconds: None)
    fake = V3Fake(1, complete_driver_overrides={"input_fnv1a": 0})
    claims = tmp_path / "claims"
    output = tmp_path / "rejected.json"
    with pytest.raises(
        once.base.runner.RecheckError, match="strict V3 validation"
    ):
        once.run_once(
            "http://192.0.2.1",
            1,
            claims=claims,
            output=output,
            requester=fake,
            poll_seconds=65,
            poll_count=1,
        )
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["outcome"] == "terminal_complete_rejected"
    assert evidence["action_must_not_be_retried"] is True
    assert evidence["terminal_report"]["driver"]["input_fnv1a"] == 0
    assert not (tmp_path / ".rejected.json.v3-terminal-staging").exists()
    calls = list(fake.calls)
    with pytest.raises(once.base.runner.RecheckError, match="permanently claimed"):
        once.run_once(
            "http://192.0.2.1",
            1,
            claims=claims,
            output=tmp_path / "second.json",
            requester=fake,
            poll_seconds=65,
            poll_count=1,
        )
    assert fake.calls == calls


def test_exact_complete_is_promoted_from_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(once.v1.time, "sleep", lambda _seconds: None)
    fake = V3Fake(1)
    output = tmp_path / "pass.json"
    result = once.run_once(
        "http://192.0.2.1",
        1,
        claims=tmp_path / "claims",
        output=output,
        requester=fake,
        poll_seconds=65,
        poll_count=1,
    )
    assert result["outcome"] == "complete_pass"
    assert json.loads(output.read_text(encoding="utf-8"))["outcome"] == (
        "complete_pass"
    )
    assert not (tmp_path / ".pass.json.v3-terminal-staging").exists()
