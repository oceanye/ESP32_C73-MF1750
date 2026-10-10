from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from tools import mf1750_runtime_lut_partial_hold_repeat_ptlw_v1_once as once
from tools import mf1750_runtime_lut_partial_hold_repeat_ptlw_v1_pack as pack


ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = (
    ROOT
    / ".pio"
    / "build-runtime-lut-partial-hold-repeat-ptlw-v1"
    / "ec5_runtime_lut_partial_hold_repeat_ptlw_v1"
)


def _device_identity(kind: str) -> dict[str, Any]:
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


def _repeat_capabilities() -> dict[str, bool]:
    return {
        "partial_refresh": True,
        "window_refresh": True,
        "command_0x83": True,
        "command_0x86": False,
        "mid_refresh_power_cut": False,
        "spi_frequency_sweep": False,
        "full_screen_global_refresh": False,
        "same_palette_hold_probe": True,
        "cross_palette_hold_probe": False,
    }


def _baseline_contract() -> dict[str, Any]:
    return {
        "ordinal": None,
        "role": "EXTERNAL_FACTORY_OTP_CLEAN_WHITE",
        "external_anchor_required": True,
        "anchor_established_by_firmware": False,
        "one_visible_refresh_required": False,
        "code7_baseline_action_reachable": False,
        "recovery_action_reachable": False,
    }


def _device_version() -> dict[str, Any]:
    runner = once.base.runner
    return {
        **_device_identity("version"),
        "action_count": 3,
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
            "terminal_next_ordinal": 4,
        },
        "baseline_contract": _baseline_contract(),
        **_repeat_capabilities(),
    }


def _device_manifest() -> dict[str, Any]:
    profile = pack.build_report()["contract"]["profile"]
    return {
        **_device_identity("manifest"),
        "actions": list(once.base.runner.ACTIONS),
        "action_count": 3,
        "one_driver_call_per_action": True,
        "factory_otp": False,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "recovery": False,
        "baseline_contract": _baseline_contract(),
        "history_layout": {
            "runtime_lut_profile_id": pack.PROFILE_ID,
            "ptlw_endpoint_contract": "xe=x+w-1;ye=y+h-1",
            "ptlw_mode": 1,
            "windows_disjoint": True,
            "external_factory_white_anchor_required": True,
            "anchor_established_by_firmware": False,
            "runtime_code7_action_reachable": False,
            "full_white_dtm_transport": None,
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
            **profile,
        },
        **_repeat_capabilities(),
    }


class RepeatPreflightFake:
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

    def _status(self) -> dict[str, Any]:
        value = {
            **_device_identity("status"),
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

    def _report(self) -> dict[str, Any]:
        if self.ordinal == 1:
            value = {
                **_device_identity("report"),
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
                **_device_identity("report"),
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
            "version": _device_version(),
            "manifest": _device_manifest(),
            "status": self._status(),
            "report": self._report(),
        }
        return 200, values[name]


def _write_permanent_claim(
    claims: Path, ordinal: int, boot_nonce: str
) -> tuple[Path, dict[str, Any]]:
    action = once.base.runner.ACTIONS[ordinal - 1]
    claim = once.base.runner._seal(  # noqa: SLF001
        {
            "schema_version": 1,
            "kind": (
                f"{once.base.runner.EVIDENCE_KIND_PREFIX}-permanent-claim"
            ),
            "created_at": "2026-08-23T12:34:56.000+08:00",
            "firmware_sha256": once.base.runner.FIRMWARE_SHA256,
            "boot_nonce": boot_nonce,
            "action": dict(action),
            "state": "claimed_before_first_mutation",
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        }
    )
    path = claims / f"{action['action_id']}.json"
    once.base.runner._write_new(path, claim)  # noqa: SLF001
    return path, claim


def _fault_status(
    ordinal: int,
    boot_nonce: str,
    *,
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    action = once.base.runner.ACTIONS[ordinal - 1]
    value = {
        **_device_identity("status"),
        "boot_nonce": boot_nonce,
        "state": "fault_locked",
        "phase": 3,
        "phase_name": "FAULT",
        "cursor_raw": (3 << 8) | ordinal,
        "next_ordinal": ordinal,
        "current_action": dict(action),
        "campaign_complete": False,
        "fixture_self_check_passed": True,
        "cursor_valid": True,
        "persistent_key_present": True,
        "execute_pending": False,
        "gpio_initialized": True,
        "busy": 0,
        "rst": 0,
        "cs": 0,
        "cs2": 0,
        "arm_request_count": ordinal,
        "execute_request_count": ordinal,
        "total_driver_call_count": ordinal,
    }
    value.update(overrides or {})
    return value


def _fault_report(
    ordinal: int,
    boot_nonce: str,
    *,
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    action = once.base.runner.ACTIONS[ordinal - 1]
    value = {
        **_device_identity("report"),
        "boot_nonce": boot_nonce,
        "valid": True,
        "terminal_state": "FAULT",
        "result": False,
        "error": "driver_operation_failed",
        "driver_called": True,
        "ordinal": ordinal,
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "role": action["role"],
        "round": action["round"],
        "branch": action["branch"],
        "job_id": ordinal,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": ordinal,
        "phase": 3,
        "phase_name": "FAULT",
        "next_ordinal": ordinal,
        "no_retry": True,
        "no_recovery": True,
        "driver": {
            "valid": True,
            "running": False,
            "sequence_ok": False,
            "failure_stage": "partial_hold_refresh_sequence",
            "spi_hz": 1_000_000,
            "safe_finish": {
                "busy_before_pins_low": 0,
                "busy_after_pins_low": 0,
                "busy_after_5ms": 0,
                "final_gpio": {
                    "busy": 0,
                    "rst": 0,
                    "cs": 0,
                    "cs2": 0,
                },
            },
        },
    }
    value.update(overrides or {})
    return value


class RepeatFaultReadFake:
    def __init__(
        self,
        ordinal: int,
        *,
        boot_nonce: str = "0123456789abcdef",
        status_overrides: Mapping[str, Any] | None = None,
        report_overrides: Mapping[str, Any] | None = None,
    ) -> None:
        self.ordinal = ordinal
        self.boot_nonce = boot_nonce
        self.status_overrides = dict(status_overrides or {})
        self.report_overrides = dict(report_overrides or {})
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
        assert method == "GET"
        assert headers is None
        assert timeout > 0
        name = path.rsplit("/", 1)[-1]
        self.calls.append((method, name))
        values = {
            "version": _device_version(),
            "manifest": _device_manifest(),
            "status": _fault_status(
                self.ordinal,
                self.boot_nonce,
                overrides=self.status_overrides,
            ),
            "report": _fault_report(
                self.ordinal,
                self.boot_nonce,
                overrides=self.report_overrides,
            ),
        }
        return 200, values[name]


class RepeatMutationFaultFake:
    def __init__(self, *, report_read_error: bool = False) -> None:
        self.boot_nonce = "0123456789abcdef"
        self.report_read_error = report_read_error
        self.execute_seen = False
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
                return 200, _device_version()
            if name == "manifest":
                return 200, _device_manifest()
            if name == "status":
                return 200, RepeatPreflightFake(1, busy=0)._status()
            if not self.execute_seen:
                return 200, RepeatPreflightFake(1, busy=0)._report()
            if self.report_read_error:
                raise OSError("simulated terminal report read failure")
            return 200, _fault_report(1, self.boot_nonce)
        assert method == "POST"
        assert headers is not None
        if name == "arm":
            return 200, {
                "accepted": True,
                "armed": True,
                "action_id": action["action_id"],
                "boot_nonce": self.boot_nonce,
                "arm_nonce": "fedcba9876543210",
            }
        if name == "execute":
            self.execute_seen = True
            return 200, {
                "accepted": True,
                "execute_consumed": True,
                "action_id": action["action_id"],
                "boot_nonce": self.boot_nonce,
            }
        raise AssertionError(name)


def test_pack_has_only_three_cropped_actions_and_external_anchor() -> None:
    report = pack.build_report()
    contract = report["contract"]
    assert [item["role"] for item in report["actions"]] == [
        "PATCH_A",
        "PATCH_B",
        "PATCH_C",
    ]
    assert all(
        item["dtm_transport"] == "UNIFORM_CROPPED_WINDOW"
        for item in report["actions"]
    )
    assert all(item["ptlw_writes_per_controller"] == 2 for item in report["actions"])
    assert contract["external_anchor"] == {
        "required": True,
        "kind": "FACTORY_OTP_CLEAN_WHITE",
        "established_by_firmware": False,
        "model_code_not_transported": 7,
    }
    assert contract["full_screen_refresh_action"] is False
    assert contract["experimental_code7_action"] is False
    assert contract["recovery_action"] is False
    assert "WHITE" not in "|".join(item["role"] for item in report["actions"])
    assert "RECOVERY" not in "|".join(item["branch"] for item in report["actions"])


def test_compiled_identity_matches_pack_and_has_fresh_namespace() -> None:
    text = (
        ROOT / "src" / "ec5_runtime_lut_partial_hold_repeat_ptlw_v1_identity.inc"
    ).read_text(encoding="utf-8")
    report = pack.build_report()
    assert report["contract_id"] in text
    assert pack.NVS_NAMESPACE in text
    assert pack.NVS_NAMESPACE != "rlph_l535a_v4"
    assert "kActionCount = 3" in text
    assert "kRuntimeCode7ActionReachable = false" in text
    for action in report["actions"]:
        assert action["descriptor_id"] in text
        assert action["action_id"] in text
        assert action["frame"]["sha256"] in text
        assert f"0x{action['frame']['fnv1a']:08X}UL" in text


def test_repeat_ptlw_is_after_completed_pon_and_before_drf() -> None:
    driver = (
        ROOT / "src" / "ec5_runtime_lut_partial_hold_repeat_ptlw_v1_driver.inc"
    ).read_text(encoding="utf-8")
    helper_start = driver.index("bool phSecondSettingAndRefreshRepeatPtlw")
    helper_end = driver.index("\n}\n#endif", helper_start)
    helper = driver[helper_start:helper_end]
    pon_wait = helper.index('epdWaitBusyThenIdle("PON")')
    repeat = helper.index("phWritePartialWindow(window);")
    both = helper.index("setActiveControllers(true, true);", repeat)
    cdi = helper.index("epdCommand(CDI);", both)
    btst2 = helper.index("epdCommand(BTST2);", cdi)
    drf = helper.index("epdCommand(DRF);", btst2)
    pof = helper.index("epdCommand(POF);", drf)
    assert pon_wait < repeat < both < cdi < btst2 < drf < pof

    # Every BUSY gate and the same fail-safe/post-display finish remain present.
    for stage in ("PON", "DRF", "POF"):
        assert f'epdRequireIdleBeforeCommand("{stage}")' in helper
        assert f'epdWaitBusyThenIdle("{stage}")' in helper
    assert "epdRequestFailSafePowerOff" in helper
    assert "epdPostDisplayPowerCut()" in helper


def test_initial_ptlw_cropped_dtm_and_pre_pon_cdi_are_preserved() -> None:
    driver = (
        ROOT / "src" / "ec5_runtime_lut_partial_hold_repeat_ptlw_v1_driver.inc"
    ).read_text(encoding="utf-8")
    repeat_path = driver[driver.index("const size_t roleIndex = phRoleIndex(role);") :]
    first_ptlw = repeat_path.index("phWritePartialWindow(*window);")
    cs1_dtm = repeat_path.index("phStreamUniformDtm(false, dtmBytes, cs1Code)")
    cs2_dtm = repeat_path.index("phStreamUniformDtm(true, dtmBytes, cs2Code)")
    pre_pon_cdi = repeat_path.index("epdCommand(CDI);", cs2_dtm)
    helper_call = repeat_path.index("phSecondSettingAndRefreshRepeatPtlw(*window)")
    assert first_ptlw < cs1_dtm < cs2_dtm < pre_pon_cdi < helper_call

    assert "window.x + window.width - 1" in driver
    assert "window.height - (ph::kPtlwYEndOneMore ? 0U : 1U)" in driver
    identity = (
        ROOT / "src" / "ec5_runtime_lut_partial_hold_repeat_ptlw_v1_identity.inc"
    ).read_text(encoding="utf-8")
    assert "kSeparateCsWindowCommands = true" in identity
    assert "kPtlwYEndOneMore = false" in identity
    assert "kPartialWindowMode = 0x01" in identity


def test_main_surface_has_no_white_or_recovery_action() -> None:
    config = (
        ROOT / "src" / "ec5_runtime_lut_partial_hold_repeat_ptlw_v1_main_config.inc"
    ).read_text(encoding="utf-8")
    assert config.count("RLPH_REPEAT_ACTION(") == 4  # macro + three actions
    assert "EpdChromaGridRole::White" not in config
    assert "RUNTIME_LUT_WHITE_BASELINE" not in config
    assert "RUNTIME_LUT_WHITE_RECOVERY" not in config
    shared_main = (
        ROOT / "src" / "ec5_runtime_lut_partial_hold_repeat_ptlw_v1_main.cpp"
    ).read_text(encoding="utf-8")
    assert "recovery_action_reachable\\\":false" in shared_main
    assert "/api/ec5/runtime-lut-repeat-ptlw/execute" in config
    assert "cursor_rptlw_v1" in config


def test_platform_environment_is_isolated() -> None:
    text = (
        ROOT / "platformio.runtime_lut_partial_hold_repeat_ptlw_v1.ini"
    ).read_text(encoding="utf-8")
    assert "build-runtime-lut-partial-hold-repeat-ptlw-v1" in text
    assert "MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V1_BUILD=1" in text
    assert "MF1750_RUNTIME_LUT_PARTIAL_HOLD_V4_BUILD" not in text
    assert "EPD_ENABLE_TEST_PATTERN=0" in text


def test_built_firmware_is_bound_and_excludes_white_action_labels() -> None:
    firmware = BUILD_DIR / "firmware.bin"
    assert firmware.stat().st_size == once.base.runner.FIRMWARE_BYTES == 793312
    assert hashlib.sha256(firmware.read_bytes()).hexdigest() == (
        once.base.runner.FIRMWARE_SHA256
    )
    binary = firmware.read_bytes()
    assert pack.BUILD_TAG.encode("ascii") in binary
    assert b"EXTERNAL_FACTORY_OTP_CLEAN_WHITE" in binary
    assert b"RUNTIME_LUT_WHITE_BASELINE" not in binary
    assert b"RUNTIME_LUT_WHITE_RECOVERY" not in binary


def test_runner_requires_external_anchor_confirmation() -> None:
    with pytest.raises(SystemExit, match="confirm-external-factory-white-anchor"):
        once._require_external_anchor(["run", "--ordinal", "1"])
    assert once._require_external_anchor(
        [
            "run",
            "--ordinal",
            "1",
            "--confirm-external-factory-white-anchor",
        ]
    ) == ["run", "--ordinal", "1"]


def test_runner_manifest_enforces_repeat_ptlw_and_external_anchor() -> None:
    profile = pack.build_report()["contract"]["profile"]
    baseline = {
        "ordinal": None,
        "role": "EXTERNAL_FACTORY_OTP_CLEAN_WHITE",
        "external_anchor_required": True,
        "anchor_established_by_firmware": False,
        "one_visible_refresh_required": False,
        "code7_baseline_action_reachable": False,
        "recovery_action_reachable": False,
    }
    manifest = {
        "kind": "mf1750-ec5-runtime-lut-repeat-ptlw-manifest",
        "build_tag": pack.BUILD_TAG,
        "test_id": pack.TEST_ID,
        "campaign_id": pack.CAMPAIGN_ID,
        "device_api_version": (
            "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_DEVICE_V1"
        ),
        "identity_revision": "runtime-lut-partial-hold-repeat-ptlw-v1",
        "contract_id": pack.build_report()["contract_id"],
        "classification": once.base.runner.CLASSIFICATION,
        "actions": list(once.base.runner.ACTIONS),
        "action_count": 3,
        "one_driver_call_per_action": True,
        "factory_otp": False,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "recovery": False,
        "baseline_contract": baseline,
        "history_layout": {
            "runtime_lut_profile_id": pack.PROFILE_ID,
            "ptlw_endpoint_contract": "xe=x+w-1;ye=y+h-1",
            "ptlw_mode": 1,
            "windows_disjoint": True,
            "external_factory_white_anchor_required": True,
            "anchor_established_by_firmware": False,
            "runtime_code7_action_reachable": False,
            "full_white_dtm_transport": None,
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
            **profile,
        },
        "partial_refresh": True,
        "window_refresh": True,
        "command_0x83": True,
        "command_0x86": False,
        "mid_refresh_power_cut": False,
        "spi_frequency_sweep": False,
        "full_screen_global_refresh": False,
        "same_palette_hold_probe": True,
        "cross_palette_hold_probe": False,
    }
    once._validate_manifest(manifest)
    manifest["history_layout"]["ptlw_writes_per_controller"] = 1
    with pytest.raises(once.base.runner.RecheckError):
        once._validate_manifest(manifest)


def test_describe_exposes_exact_delta_and_forbidden_actions() -> None:
    described = once.describe()
    assert described["visible_actions"] == 3
    assert described["fixed_transport"]["ptlw_writes_per_controller"] == 2
    assert described["required_external_anchor"]["established_by_firmware"] is False
    assert described["required_external_anchor"]["confirmation_semantics"] == (
        "CAMPAIGN_START_LINEAGE_ACKNOWLEDGEMENT_NOT_CURRENT_SCREEN_WHITE"
    )
    assert described["forbidden_operations"]["runtime_code7_baseline"] is True
    assert described["forbidden_operations"]["runtime_code7_recovery"] is True


def test_ordinal1_accepts_busy_low_only_with_strict_fresh_state() -> None:
    fake = RepeatPreflightFake(1, busy=0)
    boot_nonce, transcript, report = once._preflight(
        "http://192.0.2.1",
        1,
        expected_busy=1,
        requester=fake,
    )
    assert boot_nonce == fake.boot_nonce
    assert report["terminal_state"] == "NOT_EXECUTED"
    assert len(transcript) == 4
    assert fake.calls == [
        ("GET", "version"),
        ("GET", "manifest"),
        ("GET", "status"),
        ("GET", "report"),
    ]


def test_busy_low_overrides_are_bound_into_the_base_runner_facade() -> None:
    assert once.base.runner.run_once.__globals__["_preflight"] is once._preflight
    assert once._BASE_PREFLIGHT.__globals__["_validate_ready_status"] is (
        once._validate_ready_status
    )


@pytest.mark.parametrize(
    ("field", "bad"),
    (
        ("arm_request_count", 1),
        ("execute_request_count", 1),
        ("total_driver_call_count", 1),
        ("persistent_key_present", True),
        ("rst", 1),
        ("cs", 1),
        ("cs2", 1),
    ),
)
def test_ordinal1_busy_low_rejects_nonfresh_status(field: str, bad: Any) -> None:
    fake = RepeatPreflightFake(1, busy=0, status_overrides={field: bad})
    with pytest.raises(once.base.runner.RecheckError, match="device ready status"):
        once._preflight(
            "http://192.0.2.1",
            1,
            expected_busy=1,
            requester=fake,
        )
    assert all(method == "GET" for method, _ in fake.calls)


@pytest.mark.parametrize(
    ("field", "bad"),
    (
        ("terminal_state", "COMPLETE"),
        ("total_driver_call_count", 1),
        ("driver_called", True),
        ("next_ordinal", 2),
    ),
)
def test_ordinal1_busy_low_rejects_nonfresh_report(field: str, bad: Any) -> None:
    fake = RepeatPreflightFake(1, busy=0, report_overrides={field: bad})
    with pytest.raises(once.base.runner.RecheckError, match="device fresh report"):
        once._preflight(
            "http://192.0.2.1",
            1,
            expected_busy=1,
            requester=fake,
        )
    assert all(method == "GET" for method, _ in fake.calls)


@pytest.mark.parametrize("ordinal", (2, 3))
def test_later_ordinal_accepts_busy_low_with_same_boot_safe_finish(
    ordinal: int,
) -> None:
    fake = RepeatPreflightFake(ordinal, busy=0)
    boot_nonce, transcript, report = once._preflight(
        "http://192.0.2.1",
        ordinal,
        expected_busy=1,
        requester=fake,
    )
    assert boot_nonce == fake.boot_nonce
    assert report["ordinal"] == ordinal - 1
    assert report["driver"]["safe_finish"]["busy_after_5ms"] == 1
    assert len(transcript) == 4


@pytest.mark.parametrize(
    ("section", "field", "bad", "message"),
    (
        ("safe_finish", "busy_before_pins_low", 0, "safe-finish BUSY"),
        ("safe_finish", "busy_after_pins_low", 0, "safe-finish BUSY"),
        ("safe_finish", "busy_after_5ms", 0, "safe-finish BUSY"),
        ("final_gpio", "busy", 0, "safe-finish GPIO"),
        ("final_gpio", "rst", 1, "safe-finish GPIO"),
        ("driver", "sequence_ok", False, "terminal driver"),
    ),
)
def test_later_busy_low_rejects_incomplete_safe_finish(
    section: str, field: str, bad: Any, message: str
) -> None:
    fake = RepeatPreflightFake(2, busy=0)
    report = fake._report()
    driver = report["driver"]
    if section == "safe_finish":
        driver["safe_finish"][field] = bad
    elif section == "final_gpio":
        driver["safe_finish"]["final_gpio"][field] = bad
    else:
        driver[field] = bad
    fake.report_overrides = {"driver": driver}
    with pytest.raises(once.base.runner.RecheckError, match=message):
        once._preflight(
            "http://192.0.2.1",
            2,
            expected_busy=1,
            requester=fake,
        )
    assert all(method == "GET" for method, _ in fake.calls)


def test_later_busy_low_rejects_report_from_another_boot() -> None:
    fake = RepeatPreflightFake(
        2,
        busy=0,
        report_overrides={"boot_nonce": "fedcba9876543210"},
    )
    with pytest.raises(
        once.base.runner.RecheckError, match="device report boot nonce differs"
    ):
        once._preflight(
            "http://192.0.2.1",
            2,
            expected_busy=1,
            requester=fake,
        )
    assert all(method == "GET" for method, _ in fake.calls)


@pytest.mark.parametrize(
    ("field", "bad"),
    (
        ("action_id", "0" * 64),
        ("ordinal", 0),
        ("total_driver_call_count", 0),
        ("next_ordinal", 3),
    ),
)
def test_later_busy_low_rejects_wrong_prior_report(field: str, bad: Any) -> None:
    fake = RepeatPreflightFake(2, busy=0, report_overrides={field: bad})
    with pytest.raises(once.base.runner.RecheckError, match="device prior report"):
        once._preflight(
            "http://192.0.2.1",
            2,
            expected_busy=1,
            requester=fake,
        )
    assert all(method == "GET" for method, _ in fake.calls)


def test_fault_salvage_is_strictly_get_only_and_seals_existing_claim(
    tmp_path: Path,
) -> None:
    claims = tmp_path / "claims"
    output = tmp_path / "fault-salvage.json"
    boot_nonce = "0123456789abcdef"
    claim_file, _ = _write_permanent_claim(claims, 1, boot_nonce)
    fake = RepeatFaultReadFake(1, boot_nonce=boot_nonce)

    evidence = once.salvage_fault_once(
        "http://192.0.2.1",
        1,
        claims=claims,
        output=output,
        requester=fake,
    )

    assert output.is_file()
    assert evidence["outcome"] == "fault_salvaged_read_only"
    assert evidence["network"] == {"get": 4, "post": 0}
    assert evidence["hardware_mutation_requested"] is False
    assert evidence["action_must_not_be_retried"] is True
    assert evidence["terminal_report"]["terminal_state"] == "FAULT"
    assert evidence["claim_file_sha256"] == hashlib.sha256(
        claim_file.read_bytes()
    ).hexdigest()
    assert fake.calls == [
        ("GET", "version"),
        ("GET", "manifest"),
        ("GET", "status"),
        ("GET", "report"),
    ]


def test_fault_salvage_rejects_tampered_claim_before_any_get(tmp_path: Path) -> None:
    claims = tmp_path / "claims"
    claim_file, _ = _write_permanent_claim(claims, 1, "0123456789abcdef")
    value = json.loads(claim_file.read_text(encoding="utf-8"))
    value["boot_nonce"] = "fedcba9876543210"
    claim_file.write_text(json.dumps(value), encoding="utf-8")
    fake = RepeatFaultReadFake(1)

    with pytest.raises(
        once.base.runner.RecheckError, match="permanent claim integrity differs"
    ):
        once.salvage_fault_once(
            "http://192.0.2.1",
            1,
            claims=claims,
            output=tmp_path / "must-not-exist.json",
            requester=fake,
        )
    assert fake.calls == []


def test_fault_salvage_rejects_different_boot_without_writing(
    tmp_path: Path,
) -> None:
    claims = tmp_path / "claims"
    _write_permanent_claim(claims, 1, "0123456789abcdef")
    fake = RepeatFaultReadFake(1, boot_nonce="fedcba9876543210")
    output = tmp_path / "must-not-exist.json"

    with pytest.raises(
        once.base.runner.RecheckError, match="device fault status boot_nonce differs"
    ):
        once.salvage_fault_once(
            "http://192.0.2.1",
            1,
            claims=claims,
            output=output,
            requester=fake,
        )
    assert not output.exists()
    assert all(method == "GET" for method, _ in fake.calls)


def test_fault_salvage_rejects_unsafe_final_gpio_without_writing(
    tmp_path: Path,
) -> None:
    claims = tmp_path / "claims"
    boot_nonce = "0123456789abcdef"
    _write_permanent_claim(claims, 1, boot_nonce)
    report = _fault_report(1, boot_nonce)
    report["driver"]["safe_finish"]["final_gpio"]["cs2"] = 1
    fake = RepeatFaultReadFake(
        1,
        boot_nonce=boot_nonce,
        report_overrides={"driver": report["driver"]},
    )
    output = tmp_path / "must-not-exist.json"

    with pytest.raises(
        once.base.runner.RecheckError, match="device fault safe-finish GPIO differs"
    ):
        once.salvage_fault_once(
            "http://192.0.2.1",
            1,
            claims=claims,
            output=output,
            requester=fake,
        )
    assert not output.exists()
    assert all(method == "GET" for method, _ in fake.calls)


def test_future_runner_saves_strict_terminal_fault_and_never_retries(
    tmp_path: Path,
) -> None:
    claims = tmp_path / "claims"
    output = tmp_path / "consumed-fault.json"
    fake = RepeatMutationFaultFake()

    with pytest.raises(
        once.base.runner.RecheckError, match="terminal FAULT saved"
    ):
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
    assert evidence["terminal_report"]["terminal_state"] == "FAULT"
    assert evidence["action_must_not_be_retried"] is True
    assert evidence["network"] == {"get": 5, "arm_post": 1, "execute_post": 1}
    before_second_attempt = list(fake.calls)
    with pytest.raises(
        once.base.runner.RecheckError, match="already permanently claimed"
    ):
        once.run_once(
            "http://192.0.2.1",
            1,
            claims=claims,
            output=tmp_path / "second.json",
            requester=fake,
            poll_seconds=0,
            poll_count=1,
        )
    assert fake.calls == before_second_attempt


def test_future_runner_saves_terminal_get_error_as_consumed_without_retry(
    tmp_path: Path,
) -> None:
    claims = tmp_path / "claims"
    output = tmp_path / "consumed-read-error.json"
    fake = RepeatMutationFaultFake(report_read_error=True)

    with pytest.raises(
        once.base.runner.RecheckError, match="use GET-only salvage and never retry"
    ):
        once.base.runner.run_once(
            "http://192.0.2.1",
            1,
            claims=claims,
            output=output,
            requester=fake,
            poll_seconds=0,
            poll_count=1,
        )

    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["outcome"] == "terminal_report_read_error"
    assert evidence["terminal_report"] is None
    assert evidence["action_must_not_be_retried"] is True
    assert evidence["network"] == {"get": 5, "arm_post": 1, "execute_post": 1}
    assert evidence["transcript"][-1]["method"] == "GET"
    assert evidence["transcript"][-1]["endpoint"] == "report"
    assert "simulated terminal report read failure" in (
        evidence["transcript"][-1]["observation_error"]
    )
    assert once.base.runner.run_once is once.run_once


def test_describe_advertises_get_only_fault_salvage() -> None:
    described = once.describe()
    assert described["read_only_fault_salvage"]["network"] == {
        "get": 4,
        "post": 0,
    }
    assert (
        described["read_only_fault_salvage"]["hardware_mutation_requested"]
        is False
    )
    assert described["consumed_failure_persistence"]["terminal_fault"] is True


def test_salvage_cli_dispatches_without_mutation_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, Any] = {}

    def fake_salvage(
        base_url: str,
        ordinal: int,
        *,
        claims: Path,
        output: Path,
    ) -> dict[str, Any]:
        captured.update(
            {
                "base_url": base_url,
                "ordinal": ordinal,
                "claims": claims,
                "output": output,
            }
        )
        return {"outcome": "fault_salvaged_read_only", "post": 0}

    monkeypatch.setattr(once, "salvage_fault_once", fake_salvage)
    claims = tmp_path / "claims"
    output = tmp_path / "salvage.json"
    result = once.main(
        [
            "salvage-fault",
            "--base-url",
            "http://192.0.2.1",
            "--ordinal",
            "1",
            "--claims",
            str(claims),
            "--output",
            str(output),
        ]
    )

    assert result == 0
    assert captured == {
        "base_url": "http://192.0.2.1",
        "ordinal": 1,
        "claims": claims,
        "output": output,
    }
    assert json.loads(capsys.readouterr().out) == {
        "outcome": "fault_salvaged_read_only",
        "post": 0,
    }
