from __future__ import annotations

import hashlib
from pathlib import Path

from tools import mf1750_runtime_lut_partial_hold_repeat_ptlw_v3_pack as pack


ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = (
    ROOT
    / ".pio"
    / "build-runtime-lut-partial-hold-repeat-ptlw-v3"
    / "ec5_runtime_lut_partial_hold_repeat_ptlw_v3"
)
BIN_SHA256 = "81a0e6ac8a106a10338cf7045b185b17d11fa913ce0949893ff6de31cea57da4"
ELF_SHA256 = "e93a57248db0220a528015f78b18a2e5c273866a3e33725649e8d983cd6256a8"


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_final_v3_build_is_exact_and_contains_every_new_identity() -> None:
    firmware = BUILD_DIR / "firmware.bin"
    elf = BUILD_DIR / "firmware.elf"
    assert firmware.stat().st_size == 796_496
    assert _sha256(firmware) == BIN_SHA256
    assert elf.stat().st_size == 13_285_792
    assert _sha256(elf) == ELF_SHA256
    binary = firmware.read_bytes()
    report = pack.build_report()
    assert report["contract_id"] == (
        "4c5f008e1ef770d9ea1523f41cee7b9d06b4cb9f8bf05d6bfd2f65f9a3aff7a0"
    )
    assert [item["ordinal"] for item in report["actions"]] == [1, 2, 3, 4, 5]
    for item in report["actions"]:
        assert item["descriptor_id"].encode("ascii") in binary
        assert item["action_id"].encode("ascii") in binary
    for value in (
        pack.BUILD_TAG,
        pack.TEST_ID,
        pack.CAMPAIGN_ID,
        pack.NVS_NAMESPACE,
        pack.NVS_KEY,
        report["contract_id"],
    ):
        assert value.encode("ascii") in binary


def test_v3_pack_is_new_busy_qualified_five_action_contract() -> None:
    report = pack.build_report()
    contract = report["contract"]
    assert report["offline_only"] is True
    assert report["hardware_accessed"] is False
    assert report["firmware_flashed"] is False
    assert report["display_refreshed"] is False
    assert contract["busy_qualification"] == {
        "raw_idle_level": 1,
        "host_preflight_required_for_every_ordinal": True,
        "firmware_arm_required": True,
        "firmware_execute_required": True,
        "firmware_dispatch_required": True,
        "busy_zero_accepted": False,
    }
    assert contract["factory_otp_white"]["ordinals"] == [1, 5]
    assert contract["runtime_transport_codes"] == [3, 5, 6]
    assert contract["experimental_code7_action"] is False
    assert contract["retry"] is False
    assert contract["automatic_recovery"] is False
    assert contract["autochain"] is False


def test_v3_firmware_has_three_non_bypassable_busy_high_gates() -> None:
    source = _text("src/ec5_runtime_lut_partial_hold_repeat_ptlw_v1_main.cpp")
    v3_guard = "MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD"
    for error in (
        "arm_busy_not_idle_high",
        "execute_busy_not_idle_high",
        "dispatch_busy_not_idle_high",
    ):
        location = source.index(f'"{error}"')
        prefix = source[max(0, location - 220) : location]
        assert v3_guard in prefix
        assert "epdReadBusy() != 1" in prefix
    dispatch = source[source.index("void executePendingAction()") :]
    assert dispatch.index("dispatch_busy_not_idle_high") < dispatch.index(
        "++driverCallCountForAction"
    )
    assert dispatch.index("dispatch_busy_not_idle_high") < dispatch.index(
        "epdDisplayCompiledFactoryOtpWhiteRecovery()"
    )


def test_v3_routes_nvs_and_payloads_are_frozen() -> None:
    config = _text(
        "src/ec5_runtime_lut_partial_hold_repeat_ptlw_v3_main_config.inc"
    )
    for route in ("version", "manifest", "status", "report", "arm", "execute"):
        assert f'/api/ec5/runtime-lut-repeat-ptlw-v3/{route}' in config
    assert '"cursor_rptv3"' in config
    assert "busy_qualified_arm_execute_dispatch" in config
    report = pack.build_report()
    partial = report["actions"][1:4]
    assert [item["window"]["cs1_code"] for item in partial] == [3, 5, 6]
    assert all(item["ptlw_writes_per_controller"] == 2 for item in partial)
    assert all(item["window"] is None for item in (report["actions"][0], report["actions"][4]))


def test_v3_platformio_isolated_and_no_startup_refresh() -> None:
    platformio = _text("platformio.runtime_lut_partial_hold_repeat_ptlw_v3.ini")
    assert "build-runtime-lut-partial-hold-repeat-ptlw-v3" in platformio
    assert "MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD=1" in platformio
    assert "EPD_ENABLE_TEST_PATTERN=0" in platformio
    source = _text("src/ec5_runtime_lut_partial_hold_repeat_ptlw_v1_main.cpp")
    setup = source[source.index("void setup()") : source.index("void loop()")]
    assert "epdDisplayCompiled" not in setup
    assert setup.count("epdBegin();") == 1
