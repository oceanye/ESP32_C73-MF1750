from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tools import mf1750_runtime_lut_ptlw_fullframe_ab_v1_once as once
from tools import mf1750_runtime_lut_ptlw_fullframe_ab_v1_pack as pack


ROOT = Path(__file__).resolve().parents[1]


def test_controlled_delta_is_addressing_transport_only() -> None:
    report = pack.build_report()
    actions = report["actions"]
    assert [item["ordinal"] for item in actions] == [1, 2, 3, 4, 5]
    assert [item["role"] for item in actions] == [
        "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
        "TREATMENT_A_FULLFRAME_COMPOSITE",
        "FACTORY_OTP_WHITE_CROSSOVER_RESET",
        "TREATMENT_B_INCLUSIVE_PTLW_CROP",
        "FACTORY_OTP_WHITE_RECOVERY",
    ]

    a, b = actions[1], actions[3]
    assert a["frame"] == b["frame"]
    assert a["target_window"] == b["target_window"] == {
        "x": 176,
        "y": 240,
        "width": 160,
        "height": 120,
        "cs1_code": 5,
        "cs2_code": 5,
    }
    assert a["prestage_dtm"] == b["prestage_dtm"]
    assert a["ptlw_writes_per_controller"] == 0
    assert b["ptlw_writes_per_controller"] == 1
    assert a["target_dtm"]["bytes"] == 153_600
    assert b["target_dtm"]["bytes"] == 9_600
    assert a["refresh_sequence"] == b["refresh_sequence"] == [
        "PON_BUSY_COMPLETE_60S_GATE",
        "DRF_00_BUSY_COMPLETE_60S_GATE",
        "POF_00_BUSY_COMPLETE_60S_GATE",
    ]

    delta = report["contract"]["controlled_delta"]
    assert delta["independent_variable"] == "SRAM_ADDRESSING_TRANSPORT"
    assert delta["same_final_controller_sram"] is True
    assert delta["same_logical_frame"] is True
    assert delta["same_runtime_lut_profile"] is True
    assert delta["runtime_treatment_action_stage_cdi"] is False
    assert delta["runtime_treatment_action_stage_btst2"] is False
    assert delta["runtime_treatment_repeat_ptlw_after_pon"] is False
    assert delta["command_0x86"] is False


def test_evidence_boundary_keeps_calibration_gate_fail_closed() -> None:
    boundary = once.describe()["evidence_boundary"]
    assert boundary["offline_build_proves_panel_result"] is False
    assert boundary["live_ab_required"] is True
    assert boundary["formal_8x2_calibration_requires_three_clean_b_cycles"] is True
    assert boundary["nominal_slots_after_gate"] == 16
    assert boundary["nominal_slots_are_distinct_colors_without_measurement"] is False
    assert boundary["deduplicate_by_measured_color"] is True
    assert boundary["do_not_claim_arbitrary_lut_or_256_color_support"] is True


def test_compiled_identity_binds_component_and_combined_payloads() -> None:
    report = pack.build_report()
    identity = (
        ROOT / "src/ec5_runtime_lut_ptlw_fullframe_ab_v1_identity.inc"
    ).read_text(encoding="utf-8")
    driver = (
        ROOT / "src/ec5_runtime_lut_ptlw_fullframe_ab_v1_driver.inc"
    ).read_text(encoding="utf-8")

    assert report["contract_id"] in identity
    payloads = report["contract"]["payload_identities"]
    for item in payloads.values():
        assert item["sha256"] in identity
        assert f"0x{item['fnv1a']:08X}UL" in identity

    assert "phValidatePreloadIdentity" in driver
    assert "phTargetDtmIdentity" in driver
    assert "phCombinedDtmIdentity" in driver
    assert "PH_FAILURE_TARGET_IDENTITY" in driver
    assert "PH_FAILURE_DTM_IDENTITY" in driver
    assert "PH_FAILURE_PRELOAD_STREAM_IDENTITY" in driver
    assert "PH_FAILURE_STREAM_IDENTITY" in driver


def test_runtime_actions_share_minimal_refresh_and_b_writes_ptlw_once() -> None:
    driver = (
        ROOT / "src/ec5_runtime_lut_ptlw_fullframe_ab_v1_driver.inc"
    ).read_text(encoding="utf-8")
    start = driver.index("bool phRefreshTreatmentsIdentically()")
    end = driver.index("\n}\n\n}  // namespace", start) + 2
    refresh = driver[start:end]

    assert refresh.count("epdCommand(PON)") == 1
    assert refresh.count("epdCommand(DRF)") == 1
    assert refresh.count("epdCommand(POF)") == 1
    assert refresh.index("epdCommand(PON)") < refresh.index("epdCommand(DRF)")
    assert refresh.index("epdCommand(DRF)") < refresh.index("epdCommand(POF)")
    assert refresh.count("epdData(0x00)") == 2
    for forbidden in ("CDI", "BTST2", "0x86", "phWriteBPartialWindow"):
        assert forbidden not in refresh

    action_body = driver[driver.index("bool epdDisplayCompiledChromaGrid") :]
    assert action_body.count("phWriteBPartialWindow(false)") == 1
    assert action_body.count("phWriteBPartialWindow(true)") == 1
    assert action_body.count("phRefreshTreatmentsIdentically()") == 1
    assert "phStreamPackedControllerDtm(frame, false, cs1PreloadFnv)" in action_body
    assert "phStreamPackedControllerDtm(frame, true, cs2PreloadFnv)" in action_body
    assert "ph::kCroppedDtmBytes, ph::kBlueCode" in action_body


def test_program_keeps_factory_white_and_busy_gates() -> None:
    program = (
        ROOT / "src/ec5_runtime_lut_ptlw_fullframe_ab_v1_program.inc"
    ).read_text(encoding="utf-8")
    config = (
        ROOT / "src/ec5_runtime_lut_ptlw_fullframe_ab_v1_main_config.inc"
    ).read_text(encoding="utf-8")
    assert 'rejectMutation(503, "arm_busy_not_idle_high"' in program
    assert 'rejectMutation(503, "execute_busy_not_idle_high"' in program
    assert 'enterFault("dispatch_busy_not_idle_high"' in program
    assert "latePofSleepLowEligible" in program
    assert "fullframeDriverEstablishesLatePofSleepLow" in program
    assert "fullframeBusyAdmissionAllowed" in program
    assert "action.ordinal == 1 && totalDriverCallCount == 0U" in program
    assert "latePofSleepLowEligible = false;" in program
    assert "driver.safeFinishBusyBeforePinsLow == 1" in program
    assert "driver.safeFinishBusyAfterPinsLow == 1" in program
    assert "driver.safeFinishBusyAfter5Ms == 1" in program
    assert "driver.finalBusyLevel == 1" in program
    driver = (ROOT / "src/epd_driver.cpp").read_text(encoding="utf-8")
    prepare = driver[driver.index("static bool epdInitResolutionSelected") :]
    assert prepare.index("epdReset();") < prepare.index('epdWaitIdle("reset")')
    assert "epdDisplayCompiledFactoryOtpWhiteRecovery()" in program
    assert "epdDisplayCompiledChromaGrid(action->driverRole)" in program
    assert r'\"factory_otp_white_refresh_uses_shared_btst2\":true' in config
    assert r'\"runtime_treatment_action_stage_btst2\":false' in config
    assert r'\"late_low_requires_ram_only_firmware_eligibility\":true' in config
    assert r'\"driver_reset_requalifies_idle_before_commands\":true' in config


def test_isolated_build_has_no_upload_target() -> None:
    ini = (ROOT / "platformio.runtime_lut_ptlw_fullframe_ab_v1.ini").read_text(
        encoding="utf-8"
    )
    assert "build-runtime-lut-ptlw-fullframe-ab-v1" in ini
    assert "+<ec5_runtime_lut_ptlw_fullframe_ab_v1_epd_driver.cpp>" in ini
    assert "+<ec5_runtime_lut_ptlw_fullframe_ab_v1_main.cpp>" in ini
    assert "upload_port" not in ini
    assert "upload_protocol" not in ini


def test_runner_artifacts_are_exactly_bound_and_describe_is_portable(
    tmp_path: Path,
) -> None:
    status = once.artifact_binding_status()
    assert status["firmware_bin"]["verified"] is True
    assert status["firmware_elf"]["verified"] is True
    assert once.FIRMWARE_BIN.stat().st_size == once.FIRMWARE_BIN_BYTES
    assert hashlib.sha256(once.FIRMWARE_BIN.read_bytes()).hexdigest() == (
        once.FIRMWARE_BIN_SHA256
    )
    assert once.FIRMWARE_ELF.stat().st_size == once.FIRMWARE_ELF_BYTES
    assert hashlib.sha256(once.FIRMWARE_ELF.read_bytes()).hexdigest() == (
        once.FIRMWARE_ELF_SHA256
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.mf1750_runtime_lut_ptlw_fullframe_ab_v1_once",
            "describe",
        ],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        check=True,
        capture_output=True,
        text=True,
    )
    description = json.loads(completed.stdout)
    assert description["artifact_binding_status"]["firmware_bin"]["verified"]
    assert description["artifact_binding_status"]["firmware_elf"]["verified"]
    assert description["fixed_transport"]["factory_otp_white_ordinals"] == [1, 3, 5]
    assert description["fixed_transport"]["runtime_lut_partial_ordinals"] == [2, 4]
    assert description["evidence_boundary"]["live_ab_required"] is True
    assert description["automatic_retry"] is False
    assert description["automatic_recovery"] is False
    assert description["automatic_chaining"] is False


def test_runner_rejects_diagnose_without_explicit_j2_off() -> None:
    with pytest.raises(once.base.runner.RecheckError, match="J2-OFF confirmation"):
        once.diagnose_j2_off(
            "http://127.0.0.1",
            output=ROOT / ".test-output" / "should-not-exist",
            confirm_j2_off=False,
            requester=lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("network must not be called")
            ),
        )


def _ready_status(*, busy: int, ordinal: int = 1) -> dict[str, object]:
    runner = once.base.runner
    return {
        "kind": f"{runner.DEVICE_KIND_PREFIX}-status",
        "build_tag": runner.BUILD_TAG,
        "test_id": runner.TEST_ID,
        "campaign_id": runner.CAMPAIGN_ID,
        "device_api_version": runner.DEVICE_API_VERSION,
        "identity_revision": runner.IDENTITY_REVISION,
        "contract_id": runner.CONTRACT_ID,
        "classification": runner.CLASSIFICATION,
        "boot_nonce": "0123456789abcdef",
        "state": "ready",
        "phase": 0,
        "phase_name": "READY",
        "cursor_raw": ordinal,
        "next_ordinal": ordinal,
        "current_action": None,
        "campaign_complete": False,
        "fixture_self_check_passed": True,
        "cursor_valid": True,
        "gpio_initialized": True,
        "busy": busy,
        "rst": 0,
        "cs": 0,
        "cs2": 0,
        "execute_pending": False,
        "persistent_key_present": ordinal != 1,
        "arm_request_count": ordinal - 1,
        "execute_request_count": ordinal - 1,
        "total_driver_call_count": ordinal - 1,
    }


def test_ready_status_separates_j2_off_from_live_busy_gate() -> None:
    assert (
        once._validate_ready_status(_ready_status(busy=0), 1, expected_busy=0)
        == "0123456789abcdef"
    )
    assert (
        once._validate_ready_status(_ready_status(busy=1), 1, expected_busy=1)
        == "0123456789abcdef"
    )
    assert (
        once._validate_ready_status(_ready_status(busy=0), 1, expected_busy=1)
        == "0123456789abcdef"
    )

    assert (
        once._validate_ready_status(
            _ready_status(busy=0, ordinal=2), 2, expected_busy=1
        )
        == "0123456789abcdef"
    )


def test_j2_off_ready_status_rejects_nonfresh_request_counters() -> None:
    status = _ready_status(busy=0)
    status["arm_request_count"] = 1
    with pytest.raises(
        once.base.runner.RecheckError,
        match="J2-OFF diagnostic status arm_request_count differs",
    ):
        once._validate_ready_status(status, 1, expected_busy=0)


def test_fresh_live_busy_low_rejects_nonzero_driver_count() -> None:
    status = _ready_status(busy=0)
    status["total_driver_call_count"] = 1
    with pytest.raises(
        once.base.runner.RecheckError,
        match="fresh externally powered reset-low status total_driver_call_count differs",
    ):
        once._validate_ready_status(status, 1, expected_busy=1)


def test_post_action_busy_low_keeps_same_boot_counters_strict() -> None:
    status = _ready_status(busy=0, ordinal=2)
    status["execute_request_count"] = 0
    with pytest.raises(
        once.base.runner.RecheckError,
        match="post-action safe-hold status execute_request_count differs",
    ):
        once._validate_ready_status(status, 2, expected_busy=1)


def test_post_action_busy_low_still_requires_v3_prior_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status = _ready_status(busy=0, ordinal=2)

    def fake_base_preflight(
        _base_url: str,
        ordinal: int,
        *,
        expected_busy: int,
        requester: object,
    ) -> tuple[str, list[dict[str, object]], dict[str, object]]:
        del requester
        nonce = once._validate_ready_status(
            status, ordinal, expected_busy=expected_busy
        )
        return nonce, [], {"boot_nonce": nonce}

    def reject_prior_report(
        _value: object, _ordinal: int, _boot_nonce: str
    ) -> None:
        raise once.base.runner.RecheckError("strict-prior-sentinel")

    monkeypatch.setattr(once.v1, "_BASE_PREFLIGHT", fake_base_preflight)
    monkeypatch.setattr(
        once.v3, "_validate_prior_terminal_report", reject_prior_report
    )
    with pytest.raises(
        once.base.runner.RecheckError, match="strict-prior-sentinel"
    ):
        once.v3._preflight(  # noqa: SLF001
            "http://127.0.0.1",
            2,
            expected_busy=1,
            requester=object(),
        )
