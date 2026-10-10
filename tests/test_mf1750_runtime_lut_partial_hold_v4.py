from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools import mf1750_runtime_lut_partial_hold_v4_once as once
from tools import mf1750_runtime_lut_partial_hold_v4_pack as pack


ROOT = Path(__file__).resolve().parents[1]


def test_v4_is_bound_to_photo_mapped_codes_and_transport() -> None:
    report = pack.build_report()
    roles = report["contract"]["photo_mapped_code_roles"]
    assert roles["shared_white"] == 7
    assert roles["shared_blue"] == 5
    assert roles["shared_green"] == 6
    assert roles["controller_dependent"] == [0, 1, 2, 4]
    assert roles["evidence_photo_sha256"] == (
        "679e47694956c3ead0146b6115ac4e21ffc56d0315172bd508fdf67a94c517c2"
    )
    assert [item["dtm_transport"] for item in report["actions"]] == [
        "PACKED_FRAME_CONTROLLER",
        "UNIFORM_CROPPED_WINDOW",
        "UNIFORM_CROPPED_WINDOW",
        "UNIFORM_CROPPED_WINDOW",
        "PACKED_FRAME_CONTROLLER",
    ]


def test_v4_compiled_identity_matches_pack() -> None:
    text = (ROOT / "src" / "ec5_runtime_lut_partial_hold_v4_identity.inc").read_text()
    report = pack.build_report()
    assert report["contract_id"] in text
    for action in report["actions"]:
        assert action["descriptor_id"] in text
        assert action["action_id"] in text
        assert action["frame"]["sha256"] in text
        assert f"0x{action['frame']['fnv1a']:08X}UL" in text


def test_v4_driver_changes_only_full_white_transport() -> None:
    text = (ROOT / "src" / "ec5_runtime_lut_partial_hold_v4_driver.inc").read_text()
    assert "epdStreamPackedFrameController(frame," in text
    assert "phStreamUniformDtm(false, dtmBytes," in text
    assert "phStreamUniformDtm(true, dtmBytes," in text
    assert "if (!fullWhite) phWritePartialWindow(*window);" in text
    assert "ph::kPartialWindowCommand" in text


def test_v4_partial_refresh_strict_wire_contract() -> None:
    driver = (ROOT / "src" / "ec5_runtime_lut_partial_hold_v4_driver.inc").read_text()
    identity = (
        ROOT / "src" / "ec5_runtime_lut_partial_hold_v4_identity.inc"
    ).read_text()
    shared = (ROOT / "src" / "epd_driver.cpp").read_text()

    # PSR.A[4]=1 selects 3-bit pixels; PSR.B[7]=1 selects the MCU LUT.
    assert "kRuntimePsr[2] = {0x5F, 0xE9}" in driver
    assert "kPartialWindowCommand = 0x83" in identity
    assert "kPartialWindowPayloadBytes = 9" in identity
    assert "kPartialWindowMode = 0x01" in identity
    assert "kPtlwYEndOneMore = false" in identity
    assert "window.x + window.width - 1" in driver
    assert "window.height - (ph::kPtlwYEndOneMore ? 0U : 1U)" in driver

    # Native 3-bit data uses two pixels per byte. There is no synthetic DTM
    # format-prefix byte between command 0x10 and the cropped pixel stream.
    assert "(window.x & 1U) == 0" in driver
    assert "(window.width & 1U) == 0" in driver
    assert (
        "window->width) *\n                                    window->height / 2"
        in driver
    )
    assert "epdCommand(DTM);\n  epdStreamFillBytes(byteCount, pair);" in driver

    # The window refresh follows the independently implemented adjacent-panel
    # convention: floating border, ordinary DRF, and the proven BUSY-gated
    # PON/DRF/POF sequence. It is not a fast-refresh or zero-field proof.
    assert "epdCommand(CDI);\n    epdData(0xFF);" in driver
    for stage in ("PON", "DRF", "POF"):
        assert f'epdRequireIdleBeforeCommand("{stage}")' in shared
        assert f'epdWaitBusyThenIdle("{stage}")' in shared

    # Exact-chip OTP programming/read paths and the unrelated 0x86 candidate
    # remain unreachable from this driver.
    for command in ("0x86", "0x90", "0x91", "0x92"):
        assert f"epdCommand({command})" not in driver
        assert f"phWriteFixedPayload({command}" not in driver


def test_v4_runner_is_exactly_bound() -> None:
    firmware = (
        ROOT
        / ".pio"
        / "build-runtime-lut-partial-hold-v4"
        / "ec5_runtime_lut_partial_hold_l535_active_v4"
        / "firmware.bin"
    )
    assert firmware.stat().st_size == once.base.runner.FIRMWARE_BYTES == 793728
    assert hashlib.sha256(firmware.read_bytes()).hexdigest() == (
        once.base.runner.FIRMWARE_SHA256
    )
    assert once.base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS == 55.0


def test_v4_manifest_requires_packed_white_transport() -> None:
    profile = pack.build_report()["contract"]["profile"]
    manifest = {
        "kind": "mf1750-ec5-runtime-lut-partial-hold-manifest",
        "build_tag": pack.BUILD_TAG,
        "test_id": pack.TEST_ID,
        "campaign_id": pack.CAMPAIGN_ID,
        "device_api_version": "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_DEVICE_V4",
        "identity_revision": "runtime-lut-partial-hold-v4",
        "contract_id": pack.build_report()["contract_id"],
        "classification": (
            "EXPERIMENTAL_SPD1657_L535_RUNTIME_LUT_PTLW_LOCAL_HOLD_CANDIDATE"
        ),
        "actions": list(once.base.runner.ACTIONS),
        "action_count": 5,
        "one_driver_call_per_action": True,
        "factory_otp": False,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "history_layout": {
            "runtime_lut_profile_id": pack.PROFILE_ID,
            "ptlw_endpoint_contract": "xe=x+w-1;ye=y+h-1",
            "windows_disjoint": True,
            "white_transport_code": 7,
            "full_white_dtm_transport": "packed_frame_per_controller",
            **profile,
        },
        "partial_refresh": True,
        "window_refresh": True,
        "command_0x83": True,
        "command_0x86": False,
        "mid_refresh_power_cut": False,
        "spi_frequency_sweep": False,
        "full_screen_global_refresh": True,
        "same_palette_hold_probe": True,
        "cross_palette_hold_probe": False,
    }
    once.base._validate_manifest(manifest)
    manifest["history_layout"]["full_white_dtm_transport"] = "uniform_fill"
    with pytest.raises(once.base.runner.RecheckError):
        once.base._validate_manifest(manifest)
