from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools import mf1750_lightness_hold_function_chain_v1_once as once
from tools import mf1750_lightness_hold_function_chain_v1_pack as pack
from tools import mf1750_stable_code0_luma_latin_v3_pack as v3


def test_source_authority_is_exact_and_sealed() -> None:
    result = pack.validate_source_authority(require_sealed=True)
    assert result["sealed"] is True
    assert result["missing"] == []
    expected_canonical = {
        "white_action": "555b94739704096bde278ee3e0c3eb5ac901ccc7d390481f725093467a6c414b",
        "retained_capture": "7e9f7b6b9edb1e246da06316153e24e846761bc1c02fdf3a02fa5d1384ac7362",
        "relay_off": "5ebe1472699eccfd53b4b7013f67de6e818734342d6a4f680b148f7a5ce19400",
        "clean_white_review": "7de626ce68c5dc2952a0c17cdc41cd59ced97191f14344713f71bcb6b4a5ab40",
    }
    assert {
        name: result["verified_existing_files"][name]["canonical_sha256"]
        for name in expected_canonical
    } == expected_canonical


def test_l1_l2_l3_are_exact_v3_packed_frames_and_streams() -> None:
    report = pack.build_report()
    old = v3.build_report()["actions"][:3]
    new = report["actions"][:3]
    assert [item["frame"] for item in new] == [item["frame"] for item in old]
    assert [item["transport"]["cs1_dtm"] for item in new] == [
        item["cs1_dtm"] for item in old
    ]
    assert [item["transport"]["cs2_dtm"] for item in new] == [
        item["cs2_dtm"] for item in old
    ]
    assert [item["global_header"] for item in new] == ["active", "commented", "active"]


def test_hold_probes_are_cumulative_and_do_not_cover_candidate_cells() -> None:
    frames = pack._frames()  # noqa: SLF001
    grid = (pack.GRID_X0, pack.GRID_Y0, pack.GRID_X1_EXCLUSIVE, pack.GRID_Y1_EXCLUSIVE)
    for window in pack.HOLD_WINDOWS:
        assert window.x % 2 == 0 and window.width % 2 == 0
        assert window.x + window.width <= pack.CONTROLLER_WIDTH
        assert window.y + window.height <= pack.HEIGHT
        assert (
            window.x + window.width <= grid[0]
            or grid[2] <= window.x
            or window.y + window.height <= grid[1]
            or grid[3] <= window.y
        )
    assert frames[3] != frames[2]
    assert frames[4] != frames[3]
    top = pack.H1_WINDOW
    row_bytes = pack.WIDTH // 2
    top_slice = slice(
        top.y * row_bytes + top.x // 2,
        top.y * row_bytes + (top.x + top.width) // 2,
    )
    assert frames[3][top_slice] == frames[4][top_slice]


def test_hold_transport_is_the_clean_single_inclusive_ptlw_path() -> None:
    report = pack.build_report()
    hold = report["actions"][3:]
    assert [item["global_header"] for item in hold] == ["active", "commented"]
    assert [item["transport"]["ptlw_payload_hex"] for item in hold] == [
        "004001bf0008001f01",
        "004001bf0238024f01",
    ]
    assert all(item["transport"]["ptlw_writes_per_controller"] == 1 for item in hold)
    assert all(
        item["transport"]["prestage_dtm"]["sha256"] == pack.PRELOAD_DTM_SHA256
        for item in hold
    )
    contract = report["contract"]["clean_ptlw_transport"]
    assert contract["repeat_ptlw_after_pon_busy"] is False
    assert contract["action_stage_cdi"] is False
    assert contract["action_stage_btst2"] is False
    assert contract["command_0x86"] is False


def test_firmware_sources_freeze_h1_h2_semantics_and_exclude_white_successor() -> None:
    driver = pack.driver_path().read_text(encoding="utf-8")
    main = (pack.REPO_ROOT / "src/ec5_lightness_hold_function_chain_v1_main.cpp").read_text(
        encoding="utf-8"
    )
    config = pack.main_config_path().read_text(encoding="utf-8")
    assert "ph::kHoldWindows[holdIndex]" in driver
    assert "phWritePartialWindow(window, holdIndex, false);" in driver
    assert "phWritePartialWindow(window, holdIndex, true);" in driver
    assert "epdCommand(CDI)" not in driver
    assert "epdCommand(0x86)" not in driver
    assert "kActionCount = 5" in main
    assert "EpdChromaGridRole::ReverseSource" in config
    assert "EpdChromaGridRole::ReverseTarget" in config
    assert '\\"factory_otp_white_successor_embedded\\":false' in config
    assert "epdDisplayCompiledFactoryOtpWhiteRecovery" not in config


def test_platformio_environment_is_isolated_and_forbids_factory_white() -> None:
    ini = (pack.REPO_ROOT / "platformio.lightness_hold_function_chain_v1.ini").read_text(
        encoding="utf-8"
    )
    assert "build_dir = .pio/b-lightness-hold-function-chain-v1" in ini
    assert "+<ec5_lightness_hold_function_chain_v1_epd_driver.cpp>" in ini
    assert "+<ec5_lightness_hold_function_chain_v1_main.cpp>" in ini
    assert "MF1750_LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_BUILD=1" in ini
    assert "MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY=0" in ini


def test_old_v3_sources_remain_byte_frozen() -> None:
    result = pack.validate_v3_non_regression()
    assert result["exact_l1_l3"] is True
    for relative, wanted in pack.V3_FROZEN_SOURCE_SHA256.items():
        assert hashlib.sha256((pack.REPO_ROOT / relative).read_bytes()).hexdigest() == wanted


def test_runner_is_five_manual_actions_and_never_claims_gray() -> None:
    result = once.dry_validate(verify_artifacts=True)
    assert result["actions"] == 5
    assert result["qualified_brightness_levels"] == 0
    assert result["local_hold_claimed"] is False
    assert result["independent_white_successor_required"] is True
    assert [item["global_header"] for item in once.base.runner.ACTIONS] == [
        "active",
        "commented",
        "active",
        "active",
        "commented",
    ]


def test_source_failure_precedes_any_diagnostic_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    requested = False

    def requester(*args: object, **kwargs: object) -> object:
        nonlocal requested
        requested = True
        raise AssertionError("request must not run")

    def fail_source(*args: object, **kwargs: object) -> object:
        raise RuntimeError("synthetic source failure")

    monkeypatch.setattr(pack, "validate_source_authority", fail_source)
    with pytest.raises(RuntimeError, match="synthetic source failure"):
        once.diagnose_j2_off(
            "http://192.168.1.7",
            confirm_j2_off=True,
            confirm_source_clean_white_retained=True,
            output=tmp_path / "diagnostic.json",
            requester=requester,
        )
    assert requested is False
