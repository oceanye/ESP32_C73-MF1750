from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from tools import mf1750_runtime_lut_partial_hold_repeat_ptlw_v2_once as once
from tools import mf1750_runtime_lut_partial_hold_repeat_ptlw_v2_pack as pack


ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = (
    ROOT
    / ".pio"
    / "build-runtime-lut-partial-hold-repeat-ptlw-v2"
    / "ec5_runtime_lut_partial_hold_repeat_ptlw_v2"
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
    profile = pack.build_report()["contract"]["profile"]
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
            **profile,
        },
        **_capabilities(),
    }


class V2PreflightFake:
    def __init__(
        self,
        ordinal: int,
        *,
        busy: int,
        status_overrides: Mapping[str, Any] | None = None,
        report_overrides: Mapping[str, Any] | None = None,
    ) -> None:
        self.ordinal = ordinal
        self.busy = busy
        self.status_overrides = dict(status_overrides or {})
        self.report_overrides = dict(report_overrides or {})
        self.boot_nonce = "0123456789abcdef"
        self.calls: list[tuple[str, str]] = []

    def status(self) -> dict[str, Any]:
        value = {
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
        value.update(self.status_overrides)
        return value

    def report(self) -> dict[str, Any]:
        if self.ordinal == 1:
            value = {
                **_identity("report"),
                "boot_nonce": self.boot_nonce,
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
        else:
            prior = once.base.runner.ACTIONS[self.ordinal - 2]
            value = {
                **_identity("report"),
                "boot_nonce": self.boot_nonce,
                "valid": True,
                "terminal_state": "COMPLETE",
                "result": True,
                "driver_called": True,
                "driver_call_count_for_action": 1,
                "total_driver_call_count": self.ordinal - 1,
                "ordinal": self.ordinal - 1,
                "descriptor_id": prior["descriptor_id"],
                "action_id": prior["action_id"],
                "role": prior["role"],
                "branch": prior["branch"],
                "phase": 0,
                "phase_name": "READY",
                "next_ordinal": self.ordinal,
                "campaign_complete": False,
                "no_retry": True,
                "no_recovery": True,
                "driver": {
                    "valid": True,
                    "running": False,
                    "sequence_ok": True,
                    "wait_timeout": False,
                    "busy_assertion_missing": False,
                    "pre_command_idle_failure": False,
                    "failure_stage": "none",
                    "spi_hz": 1_000_000,
                    "safe_finish": {
                        "busy_before_pins_low": 1,
                        "busy_after_pins_low": 1,
                        "busy_after_5ms": 1,
                        "final_gpio": {
                            "busy": 1,
                            "rst": 0,
                            "cs": 0,
                            "cs2": 0,
                        },
                    },
                },
            }
        value.update(self.report_overrides)
        return value

    def __call__(
        self,
        _base_url: str,
        path: str,
        *,
        method: str,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        assert method == "GET"
        assert headers is None
        assert timeout > 0
        name = path.rsplit("/", 1)[-1]
        self.calls.append((method, name))
        values = {
            "version": _version(),
            "manifest": _manifest(),
            "status": self.status(),
            "report": self.report(),
        }
        return 200, values[name]


def _fault_report() -> dict[str, Any]:
    action = once.base.runner.ACTIONS[0]
    return {
        **_identity("report"),
        "boot_nonce": "0123456789abcdef",
        "valid": True,
        "terminal_state": "FAULT",
        "result": False,
        "error": "driver_operation_failed",
        "driver_called": True,
        "ordinal": 1,
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "role": action["role"],
        "round": action["round"],
        "branch": action["branch"],
        "job_id": 1,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "phase": 3,
        "phase_name": "FAULT",
        "next_ordinal": 1,
        "no_retry": True,
        "no_recovery": True,
        "driver": {
            "valid": True,
            "running": False,
            "sequence_ok": False,
            "spi_hz": 1_000_000,
            "safe_finish": {
                "busy_before_pins_low": 0,
                "busy_after_pins_low": 0,
                "busy_after_5ms": 0,
                "final_gpio": {"busy": 0, "rst": 0, "cs": 0, "cs2": 0},
            },
        },
    }


class V2MutationFaultFake:
    def __init__(self, *, read_error: bool = False) -> None:
        self.read_error = read_error
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
        action = once.base.runner.ACTIONS[0]
        if method == "GET":
            assert headers is None
            if name == "version":
                return 200, _version()
            if name == "manifest":
                return 200, _manifest()
            if name == "status":
                return 200, V2PreflightFake(1, busy=0).status()
            if not self.executed:
                return 200, V2PreflightFake(1, busy=0).report()
            if self.read_error:
                raise OSError("simulated V2 report read error")
            return 200, _fault_report()
        assert method == "POST"
        assert headers is not None
        if name == "arm":
            return 200, {
                "accepted": True,
                "armed": True,
                "action_id": action["action_id"],
                "boot_nonce": "0123456789abcdef",
                "arm_nonce": "fedcba9876543210",
            }
        if name == "execute":
            self.executed = True
            return 200, {
                "accepted": True,
                "execute_consumed": True,
                "action_id": action["action_id"],
                "boot_nonce": "0123456789abcdef",
            }
        raise AssertionError(name)


def test_v2_runner_is_bound_to_final_firmware_and_five_actions() -> None:
    firmware = BUILD_DIR / "firmware.bin"
    assert firmware.stat().st_size == once.base.runner.FIRMWARE_BYTES == 796_160
    assert hashlib.sha256(firmware.read_bytes()).hexdigest() == (
        once.base.runner.FIRMWARE_SHA256
    )
    assert once.base.runner.FIRMWARE_SHA256 == (
        "c1e6851f42156ec0f34b98036ae8b89e29ebf5176dac0f8d930605178391cdef"
    )
    assert [action["role"] for action in once.base.runner.ACTIONS] == [
        "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
        "PATCH_A",
        "PATCH_B",
        "PATCH_C",
        "FACTORY_OTP_WHITE_RECOVERY",
    ]


def test_describe_exposes_bound_identity_and_strict_busy_contract() -> None:
    value = once.describe()
    assert value["firmware_binding"]["bound"] is True
    assert value["visible_actions"] == 5
    assert value["preflight_busy_contract"] == {
        "ordinal_1": "BUSY_0_OR_1_STRICT_FRESH_FACTORY_WHITE_HEALTH_ONLY",
        "ordinals_2_to_5": (
            "BUSY_1_AND_SAME_BOOT_PRIOR_COMPLETE_SAFE_FINISH_1_1_1"
        ),
    }
    assert value["automatic_retry"] is False
    assert value["automatic_chaining"] is False


def test_unbound_runner_fails_before_any_device_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = V2MutationFaultFake()
    monkeypatch.setattr(once.base.runner, "FIRMWARE_SHA256", None)
    monkeypatch.setattr(once.base.runner, "FIRMWARE_BYTES", None)
    with pytest.raises(once.base.runner.RecheckError, match="not bound"):
        once.run_once(
            "http://192.0.2.1",
            1,
            claims=tmp_path / "claims",
            output=tmp_path / "result.json",
            requester=fake,
        )
    assert fake.calls == []


def test_ordinal1_accepts_busy_low_only_with_strict_fresh_health() -> None:
    fake = V2PreflightFake(1, busy=0)
    boot, transcript, report = once._preflight(
        "http://192.0.2.1", 1, expected_busy=1, requester=fake
    )
    assert boot == fake.boot_nonce
    assert report["terminal_state"] == "NOT_EXECUTED"
    assert len(transcript) == 4


@pytest.mark.parametrize(
    ("field", "bad"),
    (
        ("arm_request_count", 1),
        ("execute_request_count", 1),
        ("total_driver_call_count", 1),
        ("persistent_key_present", True),
    ),
)
def test_ordinal1_rejects_nonfresh_status(field: str, bad: Any) -> None:
    fake = V2PreflightFake(1, busy=0, status_overrides={field: bad})
    with pytest.raises(once.base.runner.RecheckError):
        once._preflight(
            "http://192.0.2.1", 1, expected_busy=1, requester=fake
        )
    assert all(method == "GET" for method, _ in fake.calls)


def test_ordinal1_rejects_non_factory_health_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actions = [dict(action) for action in once.base.runner.ACTIONS]
    actions[0]["role"] = "PATCH_A"
    monkeypatch.setattr(once.base.runner, "ACTIONS", tuple(actions))
    fake = V2PreflightFake(1, busy=0)
    with pytest.raises(
        once.base.runner.RecheckError, match="not the factory-white health"
    ):
        once._preflight(
            "http://192.0.2.1", 1, expected_busy=1, requester=fake
        )


@pytest.mark.parametrize("ordinal", (2, 3, 4, 5))
def test_later_ordinals_require_busy_high_and_same_boot_prior_complete(
    ordinal: int,
) -> None:
    fake = V2PreflightFake(ordinal, busy=1)
    boot, transcript, report = once._preflight(
        "http://192.0.2.1", ordinal, expected_busy=1, requester=fake
    )
    assert boot == fake.boot_nonce
    assert report["ordinal"] == ordinal - 1
    assert report["driver"]["safe_finish"]["busy_after_5ms"] == 1
    assert len(transcript) == 4


@pytest.mark.parametrize("ordinal", (2, 3, 4, 5))
def test_later_ordinals_reject_busy_low(ordinal: int) -> None:
    fake = V2PreflightFake(ordinal, busy=0)
    with pytest.raises(
        once.base.runner.RecheckError, match="requires ready BUSY=1"
    ):
        once._preflight(
            "http://192.0.2.1", ordinal, expected_busy=1, requester=fake
        )


@pytest.mark.parametrize(
    ("section", "field", "bad"),
    (
        ("safe_finish", "busy_before_pins_low", 0),
        ("safe_finish", "busy_after_pins_low", 0),
        ("safe_finish", "busy_after_5ms", 0),
        ("final_gpio", "busy", 0),
    ),
)
def test_later_ordinals_reject_incomplete_safe_finish(
    section: str, field: str, bad: Any
) -> None:
    fake = V2PreflightFake(3, busy=1)
    report = fake.report()
    if section == "safe_finish":
        report["driver"]["safe_finish"][field] = bad
    else:
        report["driver"]["safe_finish"]["final_gpio"][field] = bad
    fake.report_overrides = {"driver": report["driver"]}
    with pytest.raises(once.base.runner.RecheckError, match="safe-finish"):
        once._preflight(
            "http://192.0.2.1", 3, expected_busy=1, requester=fake
        )


def test_ordinal2_explicitly_requires_factory_health_prior() -> None:
    fake = V2PreflightFake(
        2, busy=1, report_overrides={"role": "FACTORY_OTP_WHITE_RECOVERY"}
    )
    with pytest.raises(once.base.runner.RecheckError, match="prior report role"):
        once._preflight(
            "http://192.0.2.1", 2, expected_busy=1, requester=fake
        )


def test_later_ordinal_rejects_prior_report_from_another_boot() -> None:
    fake = V2PreflightFake(
        4, busy=1, report_overrides={"boot_nonce": "fedcba9876543210"}
    )
    with pytest.raises(once.base.runner.RecheckError, match="boot nonce differs"):
        once._preflight(
            "http://192.0.2.1", 4, expected_busy=1, requester=fake
        )


def test_terminal_fault_is_persisted_and_claim_prevents_retry(tmp_path: Path) -> None:
    fake = V2MutationFaultFake()
    claims = tmp_path / "claims"
    output = tmp_path / "fault.json"
    with pytest.raises(once.base.runner.RecheckError, match="terminal FAULT saved"):
        once.run_once(
            "http://192.0.2.1",
            1,
            claims=claims,
            output=output,
            requester=fake,
            poll_seconds=0,
            poll_count=1,
        )
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["outcome"] == "terminal_fault"
    assert evidence["terminal_report_strictly_validated"] is True
    assert evidence["action_must_not_be_retried"] is True
    calls = list(fake.calls)
    with pytest.raises(once.base.runner.RecheckError, match="already permanently claimed"):
        once.run_once(
            "http://192.0.2.1",
            1,
            claims=claims,
            output=tmp_path / "second.json",
            requester=fake,
            poll_seconds=0,
            poll_count=1,
        )
    assert fake.calls == calls


def test_terminal_get_error_is_persisted_without_retry(tmp_path: Path) -> None:
    fake = V2MutationFaultFake(read_error=True)
    output = tmp_path / "read-error.json"
    with pytest.raises(once.base.runner.RecheckError, match="GET-only salvage"):
        once.run_once(
            "http://192.0.2.1",
            1,
            claims=tmp_path / "claims",
            output=output,
            requester=fake,
            poll_seconds=0,
            poll_count=1,
        )
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["outcome"] == "terminal_report_read_error"
    assert evidence["terminal_report"] is None
    assert evidence["transcript"][-1]["endpoint"] == "report"
    assert "simulated V2 report read error" in (
        evidence["transcript"][-1]["observation_error"]
    )


def test_private_v1_facade_is_bound_to_v2_validators_and_runner() -> None:
    assert once.base.runner.run_once is once.run_once
    assert once.v1.run_once.__globals__["_preflight"] is once._preflight
    assert once.v1._BASE_PREFLIGHT.__globals__["_validate_ready_status"] is (
        once._validate_ready_status
    )
