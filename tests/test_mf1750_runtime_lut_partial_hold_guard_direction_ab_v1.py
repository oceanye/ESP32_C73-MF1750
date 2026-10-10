from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

import pytest

from tools import mf1750_runtime_lut_partial_hold_guard_direction_ab_v1_once as once
from tools import mf1750_runtime_lut_partial_hold_guard_direction_ab_v1_pack as pack
from tools import (
    mf1750_runtime_lut_partial_hold_guard_direction_ab_v1_white_containment_once as white_once,
)
from tools import (
    mf1750_runtime_lut_partial_hold_guard_direction_ab_v1_white_containment_pack as white,
)


ROOT = Path(__file__).resolve().parents[1]


def _white_identity() -> dict[str, Any]:
    return {
        "build_tag": white.BUILD_TAG,
        "test_id": white.TEST_ID,
        "campaign_id": white.CAMPAIGN_ID,
        "profile_id": white.PROFILE_ID,
        "environment": white.ENVIRONMENT,
        "device_api_version": white.DEVICE_API_VERSION,
        "identity_revision": white.IDENTITY_REVISION,
        "running_app_elf_sha256": white.FIRMWARE_ELF_SHA256,
        "contract_id": white.CONTRACT_ID,
        "transaction_descriptor_sha256": white.DESCRIPTOR_ID,
        "transaction_descriptor_marker": white.DESCRIPTOR_MARKER,
    }


class _WhiteDiagnosticDevice:
    def __init__(self) -> None:
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
        assert timeout > 0 and headers is None and method == "GET"
        name = path.rsplit("/", 1)[-1]
        self.calls.append((method, name))
        identity = _white_identity()
        if name == "version":
            return 200, {
                "schema_version": 1,
                "kind": "mf1750-ec5-factory-otp-white-recovery-version",
                **identity,
                "classification": white.CLASSIFICATION,
                "action_count": 1,
                "startup_refresh": False,
                "raw_ingress": False,
                "retry": False,
                "automatic_chaining": False,
                "profile_switch": False,
                "runtime_payload_present": False,
                "live_authorized": False,
            }
        if name == "manifest":
            return 200, {
                "schema_version": 1,
                "kind": "mf1750-ec5-factory-otp-white-recovery-manifest",
                **identity,
                "classification": white.CLASSIFICATION,
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
                "actions": [white_once.ACTION],
                "nvs_contract": {
                    "namespace": white.NVS_NAMESPACE,
                    "key": white.NVS_KEY,
                    "initial_cursor": 1,
                    "terminal_cursor": 2,
                    "clear_route": False,
                    "persistent_across_reboot": True,
                },
            }
        if name == "status":
            return 200, {
                "schema_version": 1,
                "kind": "mf1750-ec5-factory-otp-white-recovery-status",
                **identity,
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
                "busy": 0,
                "rst": 0,
                "cs": 0,
                "cs2": 0,
                "sck": 0,
                "dc": 0,
                "mosi": 0,
            }
        if name == "report":
            return 200, {
                "schema_version": 1,
                "kind": "mf1750-ec5-factory-otp-white-recovery-report",
                "valid": False,
                **identity,
                "terminal_state": "NOT_EXECUTED",
                "result": False,
                "driver_called": False,
                "driver_call_count_for_action": 0,
                "no_retry": True,
            }
        raise AssertionError(name)


def test_five_actions_are_fresh_white_guard_direction_crossover() -> None:
    report = pack.build_report()
    actions = report["actions"]
    assert [item["ordinal"] for item in actions] == [1, 2, 3, 4, 5]
    assert [item["palette_source"] for item in actions] == [
        "FACTORY_OTP",
        "L535_RUNTIME",
        "FACTORY_OTP",
        "L535_RUNTIME",
        "FACTORY_OTP",
    ]
    assert [item["role"] for item in actions] == [
        "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
        "PATCH_A",
        "FACTORY_OTP_WHITE_CROSSOVER_RESET",
        "PATCH_B",
        "FACTORY_OTP_WHITE_RECOVERY",
    ]
    assert report["contract"]["controlled_delta"] == {
        "independent_variable": "WHITE_GUARD_DIRECTION_ONLY",
        "a": {"ordinal": 2, "cs1": "BOTTOM_8", "cs2": "TOP_8"},
        "b": {"ordinal": 4, "cs1": "TOP_8", "cs2": "BOTTOM_8"},
        "fresh_white_before_each_treatment": True,
        "crossover_reset_ordinal": 3,
        "code_both_controllers": 5,
        "white_guard_code": 7,
        "same_target_roi": True,
        "same_dtm_rows_and_bytes": True,
        "repeat_identical_ptlw_after_pon_busy": True,
        "pre_pon_cdi_ff_preserved": True,
    }


def test_guard_streams_exactly_match_declared_ptlw_windows() -> None:
    a, b = pack.build_report()["actions"][1::2]
    assert a["window"] == {
        "x": 176,
        "target_y": 240,
        "width": 160,
        "target_height": 120,
        "cs1_code": 5,
        "cs2_code": 5,
        "cs1_guard": "BOTTOM_8",
        "cs2_guard": "TOP_8",
    }
    assert b["window"] == {**a["window"], "cs1_guard": "TOP_8", "cs2_guard": "BOTTOM_8"}

    bottom = pack._guard_bytes(5, "BOTTOM_8")  # noqa: SLF001
    top = pack._guard_bytes(5, "TOP_8")  # noqa: SLF001
    assert len(bottom) == len(top) == 10_240
    assert bottom == bytes([0x55]) * 9_600 + bytes([0x77]) * 640
    assert top == bytes([0x77]) * 640 + bytes([0x55]) * 9_600
    assert hashlib.sha256(bottom).hexdigest() == (
        "aef979e3d8e8ffd5418a4ed3d5cf53a717fed933f4bd9887c9883fc2a6068caa"
    )
    assert hashlib.sha256(top).hexdigest() == (
        "c65c24867a086f0baf581081092bba1d7c52c408cf5aee2241139033aa370cb7"
    )
    assert pack.identity.fnv1a(bottom) == 0xB58021C5
    assert pack.identity.fnv1a(top) == 0xCAE821C5

    for action in (a, b):
        assert action["dtm_rows_per_controller"] == 128
        assert action["dtm_bytes_per_controller"] == 10_240
        assert action["cs1_dtm"]["bytes"] == 10_240
        assert action["cs2_dtm"]["bytes"] == 10_240
        assert action["ptlw_writes_per_controller"] == 2
        assert action["ptlw"]["cs1"]["declared_rows"] == 128
        assert action["ptlw"]["cs2"]["declared_rows"] == 128
    assert a["ptlw"]["cs1"]["payload_hex"] == "00b0014f00f0016f01"
    assert a["ptlw"]["cs2"]["payload_hex"] == "00b0014f00e8016701"
    assert b["ptlw"]["cs1"] == a["ptlw"]["cs2"]
    assert b["ptlw"]["cs2"] == a["ptlw"]["cs1"]


def test_guard_is_diagnostic_not_recovery_or_fix_claim() -> None:
    boundary = pack.build_report()["contract"]["evidence_boundary"]
    assert boundary["explicit_declared_rows_equal_streamed_rows"] is True
    assert (
        boundary["runtime_code7_is_guard_of_factory_white_not_white_recovery"] is True
    )
    assert boundary["guard_width_pixels"] == 8
    assert boundary["guard_refinement_only_after_hit"] == [4, 2, 1]
    assert boundary["physical_bottom_equals_logical_y_end_proven"] is False
    assert boundary["predicted_fix"] is False
    assert "FPC_DIRECTION" in boundary["observation_must_record"]


def test_compiled_identity_and_all_guard_driver_branches_are_explicit() -> None:
    report = pack.build_report()
    identity = (
        ROOT / "src/ec5_runtime_lut_partial_hold_guard_direction_ab_v1_identity.inc"
    ).read_text(encoding="utf-8")
    driver = (
        ROOT / "src/ec5_runtime_lut_partial_hold_guard_direction_ab_v1_driver.inc"
    ).read_text(encoding="utf-8")
    main = (
        ROOT / "src/ec5_runtime_lut_partial_hold_guard_direction_ab_v1_program.inc"
    ).read_text(encoding="utf-8")
    endpoint_driver = (
        ROOT / "src/ec5_runtime_lut_partial_hold_repeat_ptlw_v1_driver.inc"
    ).read_text(encoding="utf-8")
    endpoint_main = (
        ROOT / "src/ec5_runtime_lut_partial_hold_repeat_ptlw_v1_main.cpp"
    ).read_text(encoding="utf-8")
    config = (
        ROOT / "src/ec5_runtime_lut_partial_hold_guard_direction_ab_v1_main_config.inc"
    ).read_text(encoding="utf-8")

    assert report["contract_id"] in identity
    assert "kGuardRows = 8" in identity
    assert "kStreamRows = 128" in identity
    assert "kStreamBytes = 10240" in identity
    for action in (report["actions"][1], report["actions"][3]):
        for key in ("descriptor_id", "action_id"):
            assert action[key] in identity
        assert action["cs1_dtm"]["sha256"] in identity
        assert action["cs2_dtm"]["sha256"] in identity

    macro = "MF1750_RUNTIME_LUT_PARTIAL_HOLD_GUARD_DIRECTION_AB_V1_BUILD"
    assert driver.count(macro) >= 15
    assert "role == EpdChromaGridRole::Source" in driver
    assert "role == EpdChromaGridRole::Mid" in driver
    assert "const size_t dtmBytes = ph::kStreamBytes;" in driver
    assert "phStreamGuardedDtm(false, cs1Code, window->cs1Guard)" in driver
    assert "phStreamGuardedDtm(true, cs2Code, window->cs2Guard)" in driver
    assert "const uint16_t ys =" in driver
    assert "guard == ph::GuardDirection::Top8" in driver
    assert "window.y - ph::kGuardRows" in driver
    assert "window.y + window.height + ph::kGuardRows - 1" in driver
    assert "ph::kStreamRows" in driver
    assert "ph::kStreamBytes" in driver
    assert (
        "!defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_GUARD_DIRECTION_AB_V1_BUILD)"
        in driver
    )
    assert "phSecondSettingAndRefreshRepeatPtlw(*window)" in driver
    assert main.count(macro) >= 10
    assert 'rejectMutation(503, "arm_busy_not_idle_high"' in main
    assert 'rejectMutation(503, "execute_busy_not_idle_high"' in main
    assert 'enterFault("dispatch_busy_not_idle_high"' in main
    assert "epdDisplayCompiledFactoryOtpWhiteRecovery()" in main
    assert macro not in endpoint_driver
    assert macro not in endpoint_main
    assert '\\"guard_rows\\":8' in config
    assert '\\"dtm_rows_per_controller\\":128' in config
    assert '\\"dtm_bytes_per_controller\\":10240' in config


def test_main_artifacts_are_exactly_bound_and_fail_closed() -> None:
    status = once.artifact_binding_status()
    assert status["firmware_bin"]["verified"] is True
    assert status["firmware_elf"]["verified"] is True
    assert once.FIRMWARE_BIN.stat().st_size == once.FIRMWARE_BIN_BYTES
    assert (
        hashlib.sha256(once.FIRMWARE_BIN.read_bytes()).hexdigest()
        == once.FIRMWARE_BIN_SHA256
    )
    assert once.FIRMWARE_ELF.stat().st_size == once.FIRMWARE_ELF_BYTES
    assert (
        hashlib.sha256(once.FIRMWARE_ELF.read_bytes()).hexdigest()
        == once.FIRMWARE_ELF_SHA256
    )
    description = once.describe()
    assert description["fixed_transport"]["factory_otp_white_ordinals"] == [1, 3, 5]
    assert description["fixed_transport"]["runtime_lut_partial_ordinals"] == [2, 4]
    assert description["fixed_transport"]["guard_rows"] == 8
    assert description["fixed_transport"]["stream_rows_per_controller"] == 128
    assert description["fixed_transport"]["stream_bytes_per_controller"] == 10_240
    assert description["automatic_retry"] is False
    assert description["automatic_recovery"] is False
    assert description["automatic_chaining"] is False
    assert description["containment_required_after_abnormal_partial_action"] is True


def test_repo_anchored_describe_from_foreign_cwd(tmp_path: Path) -> None:
    assert once.FIRMWARE_BIN.is_absolute()
    assert once.FIRMWARE_ELF.is_absolute()
    assert "build-runtime-lut-partial-hold-guard-direction-ab-v1" in str(
        once.FIRMWARE_BIN
    )
    assert once.base.runner.DEFAULT_CLAIMS == (
        ROOT
        / ".test-output"
        / "hardware"
        / ".mf1750_runtime_lut_ptlw_guard_direction_ab_v1_claims"
    )
    script = (
        ROOT / "tools/mf1750_runtime_lut_partial_hold_guard_direction_ab_v1_once.py"
    )
    completed = subprocess.run(
        [sys.executable, str(script), "describe"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert all(
        item["verified"] is True for item in payload["artifact_binding_status"].values()
    )
    assert payload["live_authorized"] is False


def test_main_diagnose_j2_off_wrapper_is_bound_and_zero_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, Path]] = []

    def fake(base_url: str, *, output: Path, requester: Any) -> dict[str, Any]:
        assert base_url == "http://192.168.1.7"
        assert requester is once.base.runner._http_request  # noqa: SLF001
        calls.append((base_url, output))
        return {"network": {"get": 4, "post": 0}, "visible_refreshes": 0}

    monkeypatch.setattr(once, "_BASE_DIAGNOSE_J2_OFF", fake)
    output = tmp_path / "main-diagnostic.json"
    value = once.diagnose_j2_off(
        "http://192.168.1.7", output=output, confirm_j2_off=True
    )
    assert value == {"network": {"get": 4, "post": 0}, "visible_refreshes": 0}
    assert calls == [("http://192.168.1.7", output)]
    assert not once.base.runner.DEFAULT_CLAIMS.exists()
    source = (
        ROOT / "tools/mf1750_ec5_otp_transition_matrix_recheck_once.py"
    ).read_text(encoding="utf-8")
    assert "urllib.request.ProxyHandler({})" in source
    with pytest.raises(once.base.runner.RecheckError, match="J2-OFF"):
        once.diagnose_j2_off("http://192.168.1.7", output=output)


def test_independent_white_containment_is_fresh_bound_and_four_get(
    tmp_path: Path,
) -> None:
    report = white.build_report()
    contract = report["contract"]
    assert contract["fresh_identity"] is True
    assert contract["factory_otp_white_only"] is True
    assert contract["runtime_payload"] is False
    assert contract["use_after_guard_action_2_or_4_abnormal"] is True
    assert contract["nvs_namespace"] != pack.NVS_NAMESPACE
    assert contract["nvs_key"] != pack.NVS_KEY
    assert white_once.DEFAULT_CLAIMS != once.base.runner.DEFAULT_CLAIMS
    assert all(
        item["verified"] is True for item in report["artifact_binding_status"].values()
    )

    output = tmp_path / "containment-diagnostic.json"
    fake = _WhiteDiagnosticDevice()
    value = white_once.diagnose_j2_off(
        "http://192.168.1.7",
        output=output,
        confirm_j2_off=True,
        requester=fake,
    )
    assert fake.calls == [
        ("GET", "version"),
        ("GET", "manifest"),
        ("GET", "status"),
        ("GET", "report"),
    ]
    assert value["network"] == {"get": 4, "post": 0}
    assert value["permanent_claims_created"] == 0
    assert value["visible_refreshes"] == 0
    assert output.is_file()


def test_both_cli_parsers_expose_diagnose_from_foreign_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    main_args = once._parse_args(  # noqa: SLF001
        [
            "diagnose-j2-off",
            "--base-url",
            "http://192.168.1.7",
            "--confirm-j2-off",
            "--output",
            str(tmp_path / "main.json"),
        ]
    )
    assert main_args.command == "diagnose-j2-off" and main_args.confirm_j2_off
    white_args = white_once._parser().parse_args(  # noqa: SLF001
        [
            "diagnose-j2-off",
            "--base-url",
            "http://192.168.1.7",
            "--confirm-j2-off",
            "--output",
            str(tmp_path / "white.json"),
        ]
    )
    assert white_args.command == "diagnose-j2-off" and white_args.confirm_j2_off

    for script in (
        ROOT / "tools/mf1750_runtime_lut_partial_hold_guard_direction_ab_v1_once.py",
        ROOT
        / "tools/mf1750_runtime_lut_partial_hold_guard_direction_ab_v1_white_containment_once.py",
    ):
        completed = subprocess.run(
            [sys.executable, str(script), "describe"],
            cwd=tmp_path,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert completed.returncode == 0, completed.stderr
        payload = json.loads(completed.stdout)
        assert all(
            item["verified"] is True
            for item in payload["artifact_binding_status"].values()
        )
