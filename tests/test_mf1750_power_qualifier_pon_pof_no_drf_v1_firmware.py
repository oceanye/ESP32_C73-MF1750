from __future__ import annotations

import re
from pathlib import Path

from tools import mf1750_power_qualifier_pon_pof_no_drf_v1_pack as pack


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "src" / "ec5_power_qualifier_pon_pof_no_drf_v1_driver.cpp"
HEADER = ROOT / "src" / "ec5_power_qualifier_pon_pof_no_drf_v1.h"
MAIN = ROOT / "src" / "ec5_power_qualifier_pon_pof_no_drf_v1_main.cpp"
INI = ROOT / "platformio.power_qualifier_pon_pof_no_drf_v1.ini"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _slice(source: str, start: str, end: str) -> str:
    left = source.index(start)
    right = source.index(end, left)
    return source[left:right]


def test_isolated_build_compiles_only_qualifier_sources() -> None:
    ini = _text(INI)
    assert "default_envs = ec5_power_qualifier_pon_pof_no_drf_v1" in ini
    assert "-<*>" in ini
    assert "+<ec5_power_qualifier_pon_pof_no_drf_v1_driver.cpp>" in ini
    assert "+<ec5_power_qualifier_pon_pof_no_drf_v1_main.cpp>" in ini
    assert "EPD_ENABLE_TEST_PATTERN=0" in ini
    assert "MF1750_POWER_QUALIFIER_PON_POF_NO_DRF_V1_BUILD=1" in ini


def test_firmware_identity_is_derived_pack_identity() -> None:
    main = _text(MAIN)
    for value in (
        pack.BUILD_TAG,
        pack.TEST_ID,
        pack.CAMPAIGN_ID,
        pack.CONTRACT_ID,
        pack.DESCRIPTOR_ID,
        pack.ACTION_ID,
        pack.NVS_NAMESPACE,
        pack.NVS_KEY,
    ):
        assert value in main


def test_readiness_is_one_reset_then_four_revision_reads_without_reset() -> None:
    driver = _text(DRIVER)
    begin = _slice(driver, "bool beginRevisionSession()", "Ec5PowerQualifierRevisionSample")
    read = _slice(driver, "Ec5PowerQualifierRevisionSample readRevisionWithoutReset", "bool equalRevision")
    readiness = _slice(driver, "bool ec5PowerQualifierRunReadinessOnce()", "bool ec5PowerQualifierRunPonPofOnce()")
    assert begin.count("resetControllers();") == 1
    assert "resetControllers" not in read
    assert readiness.count("readRevisionWithoutReset(false)") == 2
    assert readiness.count("readRevisionWithoutReset(true)") == 2
    assert "readinessReport.cs1Nontrivial" in readiness
    assert "readinessReport.cs2Nontrivial" in readiness
    assert "readinessReport.finalRst == 1U" in readiness
    assert "readinessReport.finalCs1 == 1U" in readiness
    assert "readinessReport.finalCs2 == 1U" in readiness
    assert "readinessReport.finalSck == 0U" in readiness
    assert "readinessReport.finalDc == 0U" in readiness
    assert "readinessReport.finalMosi == 0U" in readiness


def test_probe_has_exact_allowlisted_command_trace_and_no_visible_command() -> None:
    driver = _text(DRIVER)
    enum_body = _slice(driver, "enum : uint8_t {", "};")
    forbidden_literals = ("0x10", "0x11", "0x12", "0x13", "0x20", "0x21", "0x83", "0x86")
    for literal in forbidden_literals:
        assert literal not in enum_body
        assert f"command({literal})" not in driver

    expected_constants = (
        "kCmdVendorUnlock", "kCmdPowerSetting", "kCmdPanelSetting",
        "kCmdBoosterSoftStart1", "kCmdBoosterSoftStart3",
        "kCmdBoosterSoftStart2", "kCmdPowerOffSequence", "kCmdTcon",
        "kCmdPll", "kCmdVcomInterval", "kCmdResolution",
        "kCmdPowerSaving", "kCmdTvdcs", "kCmdCascade", "kCmdPowerOn",
        "kCmdPowerOff",
    )
    calls = re.findall(r"command\((kCmd\w+)\)", driver)
    assert set(calls) == set(expected_constants)
    assert "delay(6000);" in driver
    assert "data(0x4F);" in driver and "data(0x6E);" in driver
    assert "delay(1000);" in driver

    main = _text(MAIN)
    trace = ", ".join(f"0x{value:02X}" for value in pack.PROBE_COMMAND_TRACE)
    assert trace.split(", ")[0] in main
    assert "probe.wireEventCount == 58" in main
    assert "probe.wireFnv1a == 0xC12C52D5UL" in main


def test_wire_digest_records_controller_mask_dcx_and_value() -> None:
    driver = _text(DRIVER)
    write = _slice(driver, "void write8(uint8_t dcx", "void command(uint8_t value)")
    order = [
        write.index("probeReport.wireFnv1a ^= controllerMask"),
        write.index("probeReport.wireFnv1a ^= dcx"),
        write.index("probeReport.wireFnv1a ^= value"),
    ]
    assert order == sorted(order)
    assert "++probeReport.wireEventCount" in write
    assert (pack.PROBE_WIRE_EVENT_COUNT, pack.PROBE_WIRE_FNV1A) == (
        58,
        0xC12C52D5,
    )


def test_each_power_stage_explicitly_reselects_both_controllers() -> None:
    driver = _text(DRIVER)
    probe = _slice(
        driver,
        "bool ec5PowerQualifierRunPonPofOnce()",
        "const Ec5PowerQualifierReadinessReport &ec5PowerQualifierReadinessReport()",
    )
    pon = probe.index("command(kCmdPowerOn)")
    pof = probe.index("command(kCmdPowerOff)")
    post_psr = probe.index("command(kCmdPanelSetting)", pof)
    dual_selects = [
        match.start()
        for match in re.finditer(r"selectControllers\(true, true\);", probe)
    ]
    assert any(position < pon for position in dual_selects)
    assert any(pon < position < pof for position in dual_selects)
    assert any(pof < position < post_psr for position in dual_selects)


def test_power_command_busy_gate_rejects_low_entry_before_command() -> None:
    driver = _text(DRIVER)
    gate = _slice(
        driver,
        "bool requireIdleBeforePowerCommand",
        "bool waitBusyThenIdle",
    )
    assert gate.index("if (entry != 1U)") < gate.index("waitIdle(")
    assert "probeReport.preCommandIdleFailure = true;" in gate
    assert "return false;" in gate


def test_main_is_explicit_one_shot_with_nonce_and_no_startup_action() -> None:
    main = _text(MAIN)
    setup = _slice(main, "void setup()", "void loop()")
    assert "ec5PowerQualifierRunReadinessOnce" not in setup
    assert "ec5PowerQualifierRunPonPofOnce" not in setup
    assert "putUChar(kNvsKey, kFresh)" not in setup
    assert "X-EC5-Qualification-Nonce" in main
    assert "exactHeader(kQualificationNonceHeader, qualificationNonce())" in main
    assert main.index("persistPhase(kQualifyConsumed)") < main.index("qualifyPending = true")
    assert main.index("persistPhase(kProbeConsumed)") < main.index("probePending = true")
    assert "automatic_retry\\\":false" in main
    assert "automatic_recovery\\\":false" in main
    assert "automatic_chaining\\\":false" in main
    assert "ec5PowerQualifierForceSafeHold();" in _slice(
        main, "void enterFault", "void rejectMutation"
    )


def test_manifest_exposes_frozen_power_and_nvs_contract() -> None:
    main = _text(MAIN)
    manifest = _slice(main, "String manifestJson()", "String statusJson()")
    for token in (
        r'\"spi_hz\":1000000',
        r'\"exactly_one_pon\":true',
        r'\"exactly_one_pof\":true',
        r'\"missing_key_is_fresh_only\":true',
        r'\"nonterminal_phase_on_boot\"',
        "FAULT_NO_RESUME_NO_RETRY",
        "NO_HIGH_VOLTAGE_PATH_WAS_ENTERED",
        "ONE_FAIL_SAFE_POF_IS_REQUIRED",
        "A_SECOND_POF_IS_FORBIDDEN",
        "SELECT_DUAL_BEFORE_PON",
        "SELECT_DUAL_BEFORE_POF",
        "SELECT_DUAL_BEFORE_POST_PSR",
    ):
        assert token in manifest


def test_success_requires_busy_edges_wire_trace_and_all_low_finish() -> None:
    main = _text(MAIN)
    success = _slice(main, "const bool exactSuccess", "if (!exactSuccess)")
    for token in (
        "probe.ponBusySeen",
        "probe.pofBusySeen",
        "probe.ponIdleCompleted",
        "probe.pofIdleCompleted",
        "probe.ponGateEntry == 1",
        "probe.pofGateEntry == 1",
        "commandTraceExact",
        "probe.spiHz == 1000000UL",
        "probe.wireEventCount == 58",
        "probe.wireFnv1a == 0xC12C52D5UL",
        "probe.safeFinishBusyBeforePinsLow == 1",
        "probe.finalRst == 0",
        "probe.finalCs1 == 0",
        "probe.finalCs2 == 0",
        "probe.finalSck == 0",
        "probe.finalDc == 0",
        "probe.finalMosi == 0",
    ):
        assert token in success
