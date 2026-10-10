from __future__ import annotations

import hashlib
from pathlib import Path

from tools import mf1750_runtime_lut_ptlw_fullframe_ab_v1_pack as pack


ROOT = Path(__file__).resolve().parents[1]
IDENTITY = ROOT / "src" / "ec5_runtime_lut_ptlw_fullframe_ab_v1_identity.inc"
MAIN_CONFIG = (
    ROOT / "src" / "ec5_runtime_lut_ptlw_fullframe_ab_v1_main_config.inc"
)


def _fnv1a(data: bytes) -> int:
    value = 0x811C9DC5
    for byte in data:
        value = ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
    return value


def _controller_composite() -> bytes:
    data = bytearray([0x77]) * 153600
    for y in range(240, 360):
        start = y * 256 + 176 // 2
        data[start : start + 80] = bytes([0x55]) * 80
    return bytes(data)


def test_pack_is_offline_and_freezes_white_a_white_b_white() -> None:
    report = pack.build_report()
    assert report["offline_only"] is True
    assert report["hardware_accessed"] is False
    assert report["device_network_accessed"] is False
    assert report["serial_or_com_accessed"] is False
    assert report["firmware_flashed"] is False
    assert report["display_refreshed"] is False
    assert [item["ordinal"] for item in report["actions"]] == [1, 2, 3, 4, 5]
    assert [item["role"] for item in report["actions"]] == [
        "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
        "TREATMENT_A_FULLFRAME_COMPOSITE",
        "FACTORY_OTP_WHITE_CROSSOVER_RESET",
        "TREATMENT_B_INCLUSIVE_PTLW_CROP",
        "FACTORY_OTP_WHITE_RECOVERY",
    ]
    assert len({item["descriptor_id"] for item in report["actions"]}) == 5
    assert len({item["action_id"] for item in report["actions"]}) == 5
    assert report["nvs_namespace"] == "rlpffab_v1b"
    assert report["nvs_key"] == "cursor_ffab1b"
    busy = report["contract"]["busy_qualification"]
    assert busy["ordinal_1_raw_levels_accepted"] == [0, 1]
    assert busy["fresh_low_requires_external_j2_on_confirmation"] is True
    assert busy["fresh_low_requires_zero_driver_count"] is True
    assert busy["later_ordinal_raw_levels_accepted"] == [0, 1]
    assert busy["late_low_is_never_treated_as_idle"] is True
    assert busy["late_low_requires_same_boot_prior_complete"] is True
    assert busy["late_low_requires_prior_safe_finish_high"] is True
    assert busy["late_low_requires_ram_only_firmware_eligibility"] is True
    assert busy["driver_reset_requalifies_idle_before_commands"] is True
    assert busy["unqualified_busy_zero_accepted"] is False


def test_component_and_combined_stream_identities_are_exact() -> None:
    report = pack.build_report()
    a, b = report["actions"][1], report["actions"][3]
    preload = bytes([0x77]) * 153600
    composite = _controller_composite()
    crop = bytes([0x55]) * 9600
    expected = {
        "preload": (preload, "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd", 0x285715C5),
        "composite": (composite, "352e61d15eb963fe2e1b37a07664be885ec6c8a0e1383bb3e96869fe517ca3ed", 0x2FA81DC5),
        "crop": (crop, "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3", 0x77244145),
        "a_combined": (preload + composite, "5f592d3f581cddb9b625a17a1507b7df4a01e16da8e8fefc94783910a33bc190", 0x83E295C5),
        "b_combined": (preload + crop, "a84b59d945284e204a5d1b3d4d7a139a3e429d6cc557ec7645cabfb1cc48146f", 0xD92EB945),
    }
    for payload, sha256, fnv1a in expected.values():
        assert hashlib.sha256(payload).hexdigest() == sha256
        assert _fnv1a(payload) == fnv1a

    assert a["prestage_dtm"]["sha256"] == expected["preload"][1]
    assert b["prestage_dtm"] == a["prestage_dtm"]
    assert a["target_dtm"]["sha256"] == expected["composite"][1]
    assert b["target_dtm"]["sha256"] == expected["crop"][1]
    assert a["cs1_dtm"] == a["cs2_dtm"] == {
        "bytes": 307200,
        "fnv1a": 0x83E295C5,
        "sha256": expected["a_combined"][1],
    }
    assert b["cs1_dtm"] == b["cs2_dtm"] == {
        "bytes": 163200,
        "fnv1a": 0xD92EB945,
        "sha256": expected["b_combined"][1],
    }


def test_a_and_b_have_same_sram_model_and_exact_controlled_delta() -> None:
    report = pack.build_report()
    a, b = report["actions"][1], report["actions"][3]
    assert a["frame"] == b["frame"]
    assert a["frame"] == {
        "bytes": 307200,
        "fnv1a": 0x2E339DC5,
        "sha256": "c0b69123df2d5f80702d75301b453b1c46ff9fa945bea99fdcf75f298c2f9576",
        "histogram": [0, 0, 0, 0, 0, 38400, 0, 576000],
    }
    assert a["target_window"] == b["target_window"] == {
        "x": 176,
        "y": 240,
        "width": 160,
        "height": 120,
        "cs1_code": 5,
        "cs2_code": 5,
    }
    assert a["ptlw_payload_hex"] is None
    assert a["ptlw_writes_per_controller"] == 0
    assert a["dtm_transport"] == "FULL_CONTROLLER_COMPOSITE_NO_PTLW"
    assert b["ptlw_payload_hex"] == "00b0014f00f0016701"
    assert b["ptlw_writes_per_controller"] == 1
    assert b["dtm_transport"] == "INCLUSIVE_PTLW_UNIFORM_CROPPED_WINDOW"
    common = [
        "PON_BUSY_COMPLETE_60S_GATE",
        "DRF_00_BUSY_COMPLETE_60S_GATE",
        "POF_00_BUSY_COMPLETE_60S_GATE",
    ]
    assert a["refresh_sequence"] == b["refresh_sequence"] == common
    for treatment in (a, b):
        assert treatment["forbidden_action_stage_commands"] == [
            "CDI",
            "BTST2",
            "REPEAT_PTLW_AFTER_PON",
            "0x86",
        ]
    for white in report["actions"][::2]:
        assert "BTST2" in white["refresh_sequence"]
        assert "BTST2" not in white["forbidden_action_stage_commands"]


def test_cpp_identity_and_main_config_are_bound_to_pack() -> None:
    report = pack.build_report()
    identity_text = IDENTITY.read_text(encoding="utf-8")
    config_text = MAIN_CONFIG.read_text(encoding="utf-8")
    combined = identity_text + config_text
    assert report["contract_id"] in identity_text
    for item in report["actions"]:
        assert item["descriptor_id"] in combined
        assert item["action_id"] in combined
    for item in (report["actions"][1], report["actions"][3]):
        assert item["frame"]["sha256"] in identity_text
        assert item["cs1_dtm"]["sha256"] in identity_text
        assert f"0x{item['frame']['fnv1a']:08X}UL" in identity_text
        assert f"0x{item['cs1_dtm']['fnv1a']:08X}UL" in identity_text
    for marker in (
        "kFullControllerDtmBytes = 153600",
        "kCroppedDtmBytes = 9600",
        "0x00, 0xB0, 0x01, 0x4F, 0x00, 0xF0, 0x01, 0x67, 0x01",
        "kRepeatPtlwAfterPonBusy = false",
        "kActionStageCdi = false",
        "kActionStageBtst2 = false",
        "kCommand0x86Reachable = false",
    ):
        assert marker in identity_text
    assert "EpdChromaGridRole::Source, 0" in config_text
    assert "EpdChromaGridRole::Mid, 1" in config_text
    assert '\\"factory_otp_white_refresh_uses_shared_btst2\\":true' in config_text
    assert '\\"runtime_treatment_action_stage_btst2\\":false' in config_text
    assert "CDI_FF" not in config_text
    assert "REPEAT_PTLW_AFTER_PON" not in config_text
