from __future__ import annotations

from pathlib import Path

from tools import mf1750_partial_hold_warm_session_v1_pack as pack


ROOT = Path(__file__).resolve().parents[1]


def test_warm_pack_is_five_fixed_same_boot_actions() -> None:
    report = pack.build_report()
    contract = report["contract"]
    assert report["contract_id"] == (
        "a3d1efdf10bff5abaed06b9ddc0b3c7044487a25eca89ceadbb24d2d069fa905"
    )
    assert [item["role"] for item in report["actions"]] == list(pack.ROLES)
    assert [item["session_phase"] for item in report["actions"]] == [
        "OPEN",
        "WARM",
        "WARM",
        "WARM",
        "CLOSE",
    ]
    assert contract["session"] == {
        "prepare_count": 1,
        "hard_reset_count": 1,
        "runtime_lut_upload_count": 1,
        "pon_count": 1,
        "patch_drf_without_pon": 3,
        "final_white_full_window_ptlw": True,
        "pof_count_on_success": 1,
        "physical_power_control": False,
        "same_boot_required": True,
        "boot_resume": False,
        "unexpected_reboot_requires_physical_cut_before_recovery": True,
        "max_warm_gap_ms": 120000,
    }
    assert contract["retry"] is False
    assert contract["autochain"] is False
    assert contract["mid_refresh_power_cut"] is False


def test_compiled_identity_is_bound_to_pack() -> None:
    text = (ROOT / "src" / "ec5_partial_hold_warm_session_v1_identity.inc").read_text()
    report = pack.build_report()
    assert report["contract_id"] in text
    for action in report["actions"]:
        assert action["descriptor_id"] in text
        assert action["action_id"] in text
        assert action["frame"]["sha256"] in text
        assert f"0x{action['frame']['fnv1a']:08X}UL" in text


def test_driver_has_one_prepare_one_pon_and_strict_ptlw() -> None:
    driver = (ROOT / "src" / "ec5_partial_hold_warm_session_v1_driver.inc").read_text()
    assert driver.count("epdPrepareCascade(EPD_SPI_DEFAULT_HZ)") == 1
    assert driver.count("epdCommand(PON);") == 1
    assert "epdReset(" not in driver
    assert "phWritePartialWindow(*window);" in driver
    assert "phWritePartialWindow(fullController);" in driver
    assert "0, 0, EPD_CONTROLLER_WIDTH, EPD_HEIGHT" in driver
    assert "ph::kPartialWindowCommand != 0x83" in driver
    assert "ph::kPartialWindowPayloadBytes != 9" in driver
    assert "ph::kPtlwYEndOneMore" in driver
    assert "!phWindowValid(fullController)" in driver
    assert "phStreamUniformDtm(false, dtmBytes, cs1Code)" in driver
    assert "phStreamUniformDtm(true, dtmBytes, cs2Code)" in driver
    assert "epdCommand(CDI);\n  epdData(0xFF);" in driver
    assert "epdCommand(DRF);" in driver
    assert "epdCommand(POF);" in driver
    assert "setActiveControllers(true, true);\n    epdRequestFailSafePowerOff" in driver
    assert "warmState != EpdPartialHoldWarmState::Closed" in driver
    assert "do not undo that safe state" in driver
    for forbidden in ("0x86", "0x90", "0x91", "0x92"):
        assert f"epdCommand({forbidden})" not in driver


def test_http_model_is_one_shot_and_reboot_fail_closed() -> None:
    main = (ROOT / "src" / "ec5_partial_hold_warm_session_v1_main.cpp").read_text()
    assert "persistCursor(kPhaseArmed, action->ordinal)" in main
    assert "persistCursor(kPhaseConsumed, action->ordinal)" in main
    assert "driverCallCountForAction != 0" in main
    assert "epdDisplayCompiledPartialHoldWarmSession(action->driverRole)" in main
    assert "epdServicePartialHoldWarmSession()" in main
    assert "same_boot_warm_session_evidence_lost" in main
    assert "nextOrdinal == 1" in main
    assert 'replay_allowed\\":false' in main
    assert "retry" in main
    assert "autochain" in main
    assert "relay" not in main.lower()
    assert "COM14" not in main


def test_platform_environment_is_source_isolated() -> None:
    config = (ROOT / "platformio.partial_hold_warm_session_v1.ini").read_text()
    assert "-<*>" in config
    assert "+<ec5_partial_hold_warm_session_v1_epd_driver.cpp>" in config
    assert "+<ec5_partial_hold_warm_session_v1_main.cpp>" in config
    assert "MF1750_PARTIAL_HOLD_WARM_SESSION_V1_BUILD=1" in config
    assert "EPD_ENABLE_TEST_PATTERN=0" in config
