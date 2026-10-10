from __future__ import annotations

import hashlib
from pathlib import Path

from tools import mf1750_runtime_lut_partial_hold_repeat_ptlw_v2_pack as pack


ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = (
    ROOT
    / ".pio"
    / "build-runtime-lut-partial-hold-repeat-ptlw-v2"
    / "ec5_runtime_lut_partial_hold_repeat_ptlw_v2"
)
BIN_SHA256 = "c1e6851f42156ec0f34b98036ae8b89e29ebf5176dac0f8d930605178391cdef"
ELF_SHA256 = "870b869d8c5d770310f0fe3ff1c6a0acca0b2e4b5caccd2466ecf30b7ad40889"


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_final_isolated_bin_and_elf_are_exact() -> None:
    firmware = BUILD_DIR / "firmware.bin"
    elf = BUILD_DIR / "firmware.elf"
    assert firmware.stat().st_size == 796_160
    assert _sha256(firmware) == BIN_SHA256
    assert elf.stat().st_size == 13_285_540
    assert _sha256(elf) == ELF_SHA256


def test_pack_identity_and_all_five_actions_are_compiled() -> None:
    report = pack.build_report()
    assert report["offline_only"] is True
    assert report["hardware_accessed"] is False
    assert report["firmware_flashed"] is False
    assert report["display_refreshed"] is False
    assert report["contract_id"] == (
        "688624257e3e9928d93d9693f09931a5803baefa03592715dea6d15150887ed3"
    )
    assert [action["ordinal"] for action in report["actions"]] == [1, 2, 3, 4, 5]

    identity = _text(
        "src/ec5_runtime_lut_partial_hold_repeat_ptlw_v2_identity.inc"
    )
    config = _text(
        "src/ec5_runtime_lut_partial_hold_repeat_ptlw_v2_main_config.inc"
    )
    binary = (BUILD_DIR / "firmware.bin").read_bytes()
    bound_source = identity + config
    for action in report["actions"]:
        assert action["descriptor_id"] in bound_source
        assert action["action_id"] in bound_source
        assert action["action_id"].encode("ascii") in binary

    for value in (
        pack.BUILD_TAG,
        pack.TEST_ID,
        pack.CAMPAIGN_ID,
        pack.NVS_NAMESPACE,
        pack.NVS_KEY,
        report["contract_id"],
    ):
        assert value.encode("ascii") in binary


def test_white_ordinals_use_only_validated_factory_0x11_entry() -> None:
    report = pack.build_report()
    actions = report["actions"]
    white_actions = [actions[0], actions[4]]
    assert [action["ordinal"] for action in white_actions] == [1, 5]
    for action in white_actions:
        assert action["palette_source"] == "FACTORY_OTP"
        assert action["dtm_transport"] == "FACTORY_OTP_PACKED_FULL_FRAME_0X11"
        assert action["ptlw_writes_per_controller"] == 0
        assert action["window"] is None
        assert "FULL_FRAME_0X11_DTM_CS1" in action["refresh_sequence"]
        assert "FULL_FRAME_0X11_DTM_CS2" in action["refresh_sequence"]
        assert not any("PTLW" in step for step in action["refresh_sequence"])

    factory_contract = report["contract"]["factory_otp_white"]
    assert factory_contract["ordinals"] == [1, 5]
    assert factory_contract["frame_fill_byte"] == "0x11"
    assert factory_contract["driver_entry"] == (
        "epdDisplayCompiledFactoryOtpWhiteRecovery"
    )

    factory_driver = _text("src/ec5_factory_otp_white_recovery_driver.inc")
    assert "std::memset(frame, 0x11, EPD_FRAME_BYTES);" in factory_driver
    assert "epdStreamPackedFrameController(frame, false)" in factory_driver
    assert "epdStreamPackedFrameController(frame, true)" in factory_driver
    assert "phUploadRuntimeLut" not in factory_driver
    assert "spd1657_legacy_535_reference.inc" not in factory_driver

    config = _text(
        "src/ec5_runtime_lut_partial_hold_repeat_ptlw_v2_main_config.inc"
    )
    assert config.count("EpdChromaGridRole::White") == 2
    shared_main = _text(
        "src/ec5_runtime_lut_partial_hold_repeat_ptlw_v1_main.cpp"
    )
    dispatcher = shared_main[shared_main.index("void executePendingAction()") :]
    assert "action->driverRole == EpdChromaGridRole::White" in dispatcher
    assert "epdDisplayCompiledFactoryOtpWhiteRecovery()" in dispatcher
    assert ": epdDisplayCompiledChromaGrid(action->driverRole)" in dispatcher


def test_partial_actions_are_codes_3_5_6_and_repeat_ptlw_without_code7() -> None:
    report = pack.build_report()
    partial = report["actions"][1:4]
    assert [action["role"] for action in partial] == [
        "PATCH_A",
        "PATCH_B",
        "PATCH_C",
    ]
    assert [action["window"]["cs1_code"] for action in partial] == [3, 5, 6]
    assert [action["window"]["cs2_code"] for action in partial] == [3, 5, 6]
    for action in partial:
        assert action["palette_source"] == "L535_RUNTIME"
        assert action["dtm_transport"] == "UNIFORM_CROPPED_WINDOW"
        assert action["ptlw_writes_per_controller"] == 2
        assert action["refresh_sequence"].count(
            "PTLW_CS1_REPEAT_POST_PON"
        ) == 1
        assert action["refresh_sequence"].count(
            "PTLW_CS2_REPEAT_POST_PON"
        ) == 1

    assert report["contract"]["runtime_transport_codes"] == [3, 5, 6]
    assert report["contract"]["experimental_code7_action"] is False
    identity = _text(
        "src/ec5_runtime_lut_partial_hold_repeat_ptlw_v2_identity.inc"
    )
    assert "kRuntimeCode7ActionReachable = false" in identity
    assert "{48, 64, 160, 120, 7, 7}" not in identity
    assert "{304, 240, 160, 120, 7, 7}" not in identity
    assert "{48, 416, 160, 120, 7, 7}" not in identity


def test_repeat_ptlw_occurs_after_pon_and_before_drf() -> None:
    driver = _text(
        "src/ec5_runtime_lut_partial_hold_repeat_ptlw_v1_driver.inc"
    )
    start = driver.index("bool phSecondSettingAndRefreshRepeatPtlw")
    end = driver.index("\n}\n#endif", start)
    helper = driver[start:end]
    pon_wait = helper.index('epdWaitBusyThenIdle("PON")')
    repeat = helper.index("phWritePartialWindow(window);")
    cdi = helper.index("epdCommand(CDI);", repeat)
    btst2 = helper.index("epdCommand(BTST2);", cdi)
    drf = helper.index("epdCommand(DRF);", btst2)
    assert pon_wait < repeat < cdi < btst2 < drf

    operation = driver[driver.index("bool epdDisplayCompiledChromaGrid") :]
    initial_ptlw = operation.index("phWritePartialWindow(*window);")
    cs1_dtm = operation.index("phStreamUniformDtm(false, dtmBytes, cs1Code)")
    cs2_dtm = operation.index("phStreamUniformDtm(true, dtmBytes, cs2Code)")
    repeat_call = operation.index("phSecondSettingAndRefreshRepeatPtlw(*window)")
    assert initial_ptlw < cs1_dtm < cs2_dtm < repeat_call


def test_version_and_manifest_expose_the_mixed_factory_runtime_contract() -> None:
    shared_main = _text(
        "src/ec5_runtime_lut_partial_hold_repeat_ptlw_v1_main.cpp"
    )
    version_start = shared_main.index("String versionJson()")
    manifest_start = shared_main.index("String manifestJson()", version_start)
    end = shared_main.index("String gpioJson()", manifest_start)
    version_source = shared_main[version_start:manifest_start]
    manifest_source = shared_main[manifest_start:end]
    v2_wire = (
        "#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD)\n"
        '                  "\\"factory_otp\\":true,'
        '\\"custom_lut_or_waveform\\":true,"\n'
        '                  "\\"raw_frame_ingress\\":false,'
        '\\"runtime_lut_write\\":true,"'
    )
    assert version_source.count(v2_wire) == 1
    v2_factory = (
        "#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD)\n"
        '                  "\\"factory_otp\\":true,'
        '\\"custom_lut_or_waveform\\":true,"'
    )
    v2_runtime = (
        "#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD)\n"
        '                  "\\"raw_frame_ingress\\":false,'
        '\\"runtime_lut_write\\":true,"'
    )
    assert manifest_source.count(v2_factory) == 1
    assert manifest_source.count(v2_runtime) == 1
    assert (version_source + manifest_source).count(
        "MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD"
    ) == 3

    binary = (BUILD_DIR / "firmware.bin").read_bytes()
    assert b'"factory_otp":true,"custom_lut_or_waveform":true,' in binary
    assert b'"raw_frame_ingress":false,"runtime_lut_write":true,' in binary


def test_startup_is_zero_refresh_and_campaign_never_autochains() -> None:
    platformio = _text("platformio.runtime_lut_partial_hold_repeat_ptlw_v2.ini")
    assert "build-runtime-lut-partial-hold-repeat-ptlw-v2" in platformio
    assert "EPD_ENABLE_TEST_PATTERN=0" in platformio
    assert "MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD=1" in platformio

    shared_main = _text(
        "src/ec5_runtime_lut_partial_hold_repeat_ptlw_v1_main.cpp"
    )
    setup = shared_main[
        shared_main.index("void setup()") : shared_main.index("void loop()")
    ]
    assert "epdDisplayCompiled" not in setup
    assert "executePendingAction" not in setup
    # epdBegin only initializes pins/SPI state; the build flag prevents its
    # optional test pattern and no visible-action entry is called by setup.
    assert setup.count("epdBegin();") == 1
    assert '\\"automatic_execute\\":false' in shared_main
    assert '\\"automatic_chaining\\":false' in shared_main
    assert '\\"startup_refresh\\":false' in shared_main
    assert '\\"retry\\":false' in shared_main
    assert '\\"recovery\\":false' in shared_main


def test_all_pon_busy_gates_remain_at_60_seconds() -> None:
    core = _text("src/epd_driver.cpp")
    assert (
        'bool epdWaitBusyThenIdle(const char *stage, uint32_t timeoutMs = 60000)'
        in core
    )
    config = _text(
        "src/ec5_runtime_lut_partial_hold_repeat_ptlw_v2_main_config.inc"
    )
    assert '"\\"pon_timeout_ms\\":60000' in config
    report = pack.build_report()
    assert report["contract"]["controlled_repeat_delta"]["pon_timeout_ms"] == 60_000
    for action in report["actions"]:
        assert "PON_BUSY_COMPLETE_60S_GATE" in action["refresh_sequence"]
