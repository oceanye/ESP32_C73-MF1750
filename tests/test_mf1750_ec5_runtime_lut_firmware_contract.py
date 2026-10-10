from __future__ import annotations

from pathlib import Path
import re

from tools import mf1750_ec5_runtime_lut_contract as contract


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_MAIN = ROOT / "src/ec5_runtime_lut_empirical_h3_main.cpp"
RUNTIME_DRIVER = ROOT / "src/ec5_runtime_lut_empirical_h3_driver.inc"
RECOVERY_MAIN = ROOT / "src/ec5_factory_otp_white_recovery_main.cpp"
RECOVERY_DRIVER = ROOT / "src/ec5_factory_otp_white_recovery_driver.inc"
DRIVER_HEADER = ROOT / "src/epd_driver.h"
DRIVER_CPP = ROOT / "src/epd_driver.cpp"
OLD_COMBINED_CONFIG = ROOT / "platformio.runtime_lut_empirical_h3.ini"

CONFIGS = {
    "WF20_25": {
        contract.ROLE_RUNTIME: ROOT / "platformio.runtime_lut_wf20_25.ini",
        contract.ROLE_WHITE: ROOT / "platformio.otp_white_wf20_25.ini",
    },
    "WF23_25": {
        contract.ROLE_RUNTIME: ROOT / "platformio.runtime_lut_wf23_25.ini",
        contract.ROLE_WHITE: ROOT / "platformio.otp_white_wf23_25.ini",
    },
}


def _between(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    finish = source.index(end, begin)
    return source[begin:finish]


def _conditional_block(source: str, profile_id: str) -> str:
    if profile_id == "WF20_25":
        return _between(
            source,
            "#if MF1750_"
            + (
                "RUNTIME_LUT_PROFILE_WF20_25"
                if source == RUNTIME_MAIN.read_text(encoding="utf-8")
                else "OTP_WHITE_FOR_PROFILE_WF20_25"
            ),
            "#elif",
        )
    marker = (
        "#elif MF1750_RUNTIME_LUT_PROFILE_WF23_25"
        if "RUNTIME_LUT_PROFILE_WF23_25" in source
        else "#elif MF1750_OTP_WHITE_FOR_PROFILE_WF23_25"
    )
    return _between(source, marker, "#endif")


def _literal(block: str, name: str) -> str:
    match = re.search(
        rf'static constexpr const char \*{re.escape(name)}\s*=\s*"([^"]+)";',
        block,
    )
    assert match is not None, name
    return match.group(1)


def _marker(block: str) -> str:
    match = re.search(
        r"(MF1750_EC5_TX_DESCRIPTOR_V1\|PROFILE=[^|]+\|ROLE=[^|]+\|"
        r"SHA256=[0-9a-f]{64})",
        block,
    )
    assert match is not None
    return match.group(1)


def test_four_profile_specific_configs_fail_closed_against_profile_switch() -> None:
    assert not OLD_COMBINED_CONFIG.exists()
    assert set(ROOT.glob("platformio.runtime_lut*.ini")) == {
        CONFIGS["WF20_25"][contract.ROLE_RUNTIME],
        CONFIGS["WF23_25"][contract.ROLE_RUNTIME],
    }
    observed_build_dirs: set[str] = set()
    for profile_id, roles in CONFIGS.items():
        row = contract.profile_row(profile_id)
        for role, path in roles.items():
            source = path.read_text(encoding="utf-8")
            environment = (
                row["runtime_environment"]
                if role == contract.ROLE_RUNTIME
                else row["recovery_environment"]
            )
            assert f"default_envs = {environment}" in source
            build_dir = re.search(r"^build_dir = (.+)$", source, re.MULTILINE)
            assert build_dir is not None
            observed_build_dirs.add(build_dir.group(1))
            assert source.count("[env:") == 1
            assert f"[env:{environment}]" in source
            assert "-<*>" in source
            assert "EPD_ENABLE_TEST_PATTERN=0" in source
            assert "upload_port" not in source
            assert "upload_flags" not in source
            assert "extra_scripts" not in source
            if role == contract.ROLE_RUNTIME:
                assert "+<ec5_runtime_lut_empirical_h3_main.cpp>" in source
                assert "MF1750_ENABLE_RUNTIME_LUT_EMPIRICAL_H3=1" in source
                selected = "WF20_25" if profile_id == "WF20_25" else "WF23_25"
                other = "WF23_25" if selected == "WF20_25" else "WF20_25"
                assert f"MF1750_RUNTIME_LUT_PROFILE_{selected}=1" in source
                assert f"MF1750_RUNTIME_LUT_PROFILE_{other}=0" in source
                assert "FACTORY_OTP_WHITE_RECOVERY=1" not in source
            else:
                assert "+<ec5_factory_otp_white_recovery_main.cpp>" in source
                assert "MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY=1" in source
                selected = "WF20_25" if profile_id == "WF20_25" else "WF23_25"
                other = "WF23_25" if selected == "WF20_25" else "WF20_25"
                assert f"MF1750_OTP_WHITE_FOR_PROFILE_{selected}=1" in source
                assert f"MF1750_OTP_WHITE_FOR_PROFILE_{other}=0" in source
                assert "RUNTIME_LUT_EMPIRICAL_H3=1" not in source
    assert len(observed_build_dirs) == 4


def test_runtime_main_exact_identities_match_frozen_host_contract() -> None:
    source = RUNTIME_MAIN.read_text(encoding="utf-8")
    assert _literal(source, "kDeviceApiVersion") == contract.DEVICE_API_VERSION
    assert (
        _literal(source, "kTestId")
        == contract.device_binding("WF20_25", contract.ROLE_RUNTIME)["test_id"]
    )
    for profile_id in contract.PROFILES:
        block = _conditional_block(source, profile_id)
        root = contract.profile_contract(profile_id)
        row = contract.profile_row(profile_id)
        descriptor = contract.transaction_descriptor(profile_id, contract.ROLE_RUNTIME)
        action = root["actions"][0]
        binding = contract.device_binding(profile_id, contract.ROLE_RUNTIME)
        assert _literal(block, "kExpectedProfileId") == profile_id
        assert _literal(block, "kEnvironmentId") == row["runtime_environment"]
        assert _literal(block, "kCampaignId") == root["campaign_id"]
        assert _literal(block, "kBuildTag") == binding["build_tag"]
        assert _literal(block, "kContractId") == root["contract_id"]
        assert _literal(block, "kNvsNamespace") == row["runtime_nvs_namespace"]
        assert _literal(block, "kDescriptorId") == contract.sha256(descriptor)
        assert _literal(block, "kActionId") == action["hardware_action_id"]
        assert (
            _literal(block, "kGeneratedIncludeSha256")
            == row["generated_include_sha256"]
        )
        assert _marker(block) == contract.compiled_descriptor_marker(
            profile_id, contract.ROLE_RUNTIME
        )
        assert (
            source.count(
                contract.compiled_descriptor_marker(profile_id, contract.ROLE_RUNTIME)
            )
            == 1
        )
    assert _literal(source, "kNvsKey") == "used_v1"


def test_recovery_main_exact_identities_match_frozen_host_contract() -> None:
    source = RECOVERY_MAIN.read_text(encoding="utf-8")
    assert _literal(source, "kDeviceApiVersion") == contract.DEVICE_API_VERSION
    for profile_id in contract.PROFILES:
        block = _conditional_block(source, profile_id)
        root = contract.profile_contract(profile_id)
        row = contract.profile_row(profile_id)
        descriptor = contract.transaction_descriptor(profile_id, contract.ROLE_WHITE)
        action = root["actions"][1]
        binding = contract.device_binding(profile_id, contract.ROLE_WHITE)
        assert _literal(block, "kProfileId") == profile_id
        assert _literal(block, "kEnvironmentId") == row["recovery_environment"]
        assert _literal(block, "kCampaignId") == root["campaign_id"]
        assert _literal(block, "kBuildTag") == binding["build_tag"]
        assert _literal(block, "kContractId") == root["contract_id"]
        assert _literal(block, "kNvsNamespace") == row["recovery_nvs_namespace"]
        assert _literal(block, "kDescriptorId") == contract.sha256(descriptor)
        assert _literal(block, "kActionId") == action["hardware_action_id"]
        assert _marker(block) == contract.compiled_descriptor_marker(
            profile_id, contract.ROLE_WHITE
        )
        assert (
            source.count(
                contract.compiled_descriptor_marker(profile_id, contract.ROLE_WHITE)
            )
            == 1
        )
    binding = contract.device_binding("WF20_25", contract.ROLE_WHITE)
    assert _literal(source, "kTestId") == binding["test_id"]
    assert _literal(source, "kArmIntent") == binding["arm_intent"]
    assert _literal(source, "kExecuteIntent") == binding["execute_intent"]
    assert _literal(source, "kNvsKey") == "used_v1"
    for suffix in ("version", "manifest", "status", "report", "arm", "execute"):
        assert f"{binding['base_route']}/{suffix}" in source


def test_runtime_driver_deep_validation_precedes_every_panel_io() -> None:
    driver = RUNTIME_DRIVER.read_text(encoding="utf-8")
    display = driver[driver.index("bool epdDisplayCompiledEmpiricalH3") :]
    prepare = display.index("epdPrepareCascade(EPD_SPI_DEFAULT_HZ)")
    for token in (
        "h3ValidateProfileContract(&profileError)",
        "h3ValidateProfileHashes(&profileError)",
        "h3ValidateRole(role, frame, &validation)",
    ):
        assert display.index(token) < prepare
    validate_role = _between(
        source=driver, start="bool h3ValidateRole", end="void h3EmitFixedCommand"
    )
    assert "h3ComputeDtmIdentity(frame, false" in validate_role
    assert "h3ComputeDtmIdentity(frame, true" in validate_role
    for token in (
        "kDecodedHeaderSha256",
        "kPowerPayloadSha256",
        "kPllPayloadSha256",
        "kR20PayloadSha256",
        "kR21PayloadSha256",
        "kDecodedPlaintextSha256",
    ):
        assert token in driver


def test_runtime_exact_global_and_per_controller_trace_is_fail_closed() -> None:
    source = RUNTIME_DRIVER.read_text(encoding="utf-8")
    global_block = _between(
        source,
        "bool h3ApplyFixedGlobalRuntimeConfigToBothControllers()",
        "bool h3UploadFixedWaveformToController",
    )
    expected = (
        "setActiveControllers(true, true)",
        "H3FixedCommand::PanelSetting",
        "H3FixedCommand::PowerSetting",
        'epdWaitIdle("runtime H3 PWR")',
        "H3FixedCommand::Pll",
        "H3FixedCommand::Resolution",
    )
    positions = [global_block.index(token) for token in expected]
    assert positions == sorted(positions)
    assert "if (!epdWaitIdle" in global_block
    assert re.search(
        r'if \(!epdWaitIdle\("runtime H3 PWR"\)\) return false;', global_block
    )
    assert "return false" in global_block

    per_controller = _between(
        source,
        "bool h3UploadFixedWaveformToController",
        "}  // namespace",
    )
    expected = (
        "setActiveControllers(!secondController, secondController)",
        "H3FixedCommand::HiddenLutEnable",
        "epdWaitIdle(secondController",
        "H3FixedCommand::LutR20",
        "H3FixedCommand::LutR21",
    )
    positions = [per_controller.index(token) for token in expected]
    assert positions == sorted(positions)
    assert re.search(
        r"if \(!epdWaitIdle\(secondController \? \"runtime H3 CS2 E9\"\s*"
        r": \"runtime H3 CS1 E9\"\)\) \{\s*return false;\s*\}",
        per_controller,
    )
    assert "return false" in per_controller

    display = source[source.index("bool epdDisplayCompiledEmpiricalH3") :]
    expected = (
        "epdPrepareCascade(EPD_SPI_DEFAULT_HZ)",
        "h3ApplyFixedGlobalRuntimeConfigToBothControllers()",
        "h3UploadFixedWaveformToController(false)",
        "h3UploadFixedWaveformToController(true)",
        "epdStreamPackedFrameController(frame, false)",
        "epdStreamPackedFrameController(frame, true)",
        "epdSecondSettingAndRefresh()",
    )
    positions = [display.index(token) for token in expected]
    assert positions == sorted(positions)
    assert "H3_FAILURE_GLOBAL_CONFIG" in display
    assert "H3_FAILURE_CS1_WAVEFORM" in display
    assert "H3_FAILURE_CS2_WAVEFORM" in display


def test_runtime_command_emission_is_a_closed_enum_not_arbitrary_u8() -> None:
    source = RUNTIME_DRIVER.read_text(encoding="utf-8")
    enum_block = _between(source, "enum class H3FixedCommand", "static_assert(")
    commands = {
        name: int(value, 16)
        for name, value in re.findall(r"(\w+)\s*=\s*0x([0-9A-Fa-f]{2})", enum_block)
    }
    assert commands == {
        "PanelSetting": 0x00,
        "PowerSetting": 0x01,
        "DataEntry": 0x10,
        "LutR20": 0x20,
        "LutR21": 0x21,
        "Pll": 0x30,
        "Resolution": 0x61,
        "HiddenLutEnable": 0xE9,
    }
    assert 0x90 not in commands.values()
    assert 0x91 not in commands.values()
    assert source.count("epdCommand(") == 1
    emitter = _between(source, "void h3EmitFixedCommand", "void h3WriteFixedPayload")
    assert "epdCommand(static_cast<uint8_t>(command))" in emitter


def test_runtime_main_is_one_shot_bodyless_and_contains_no_recovery_call() -> None:
    source = RUNTIME_MAIN.read_text(encoding="utf-8")
    assert "kActionCount = 1" in source
    assert "kTerminalOrdinal = 2" in source
    assert source.count("epdDisplayCompiledEmpiricalH3(") == 1
    assert "epdDisplayCompiledFactoryOtpWhiteRecovery(" not in source
    setup = _between(source, "void setup()", "void loop()")
    assert setup.index("epdValidateCompiledEmpiricalH3Fixtures()") < setup.index(
        "epdBegin()"
    )
    assert "epdDisplayCompiledEmpiricalH3" not in setup
    execute = _between(source, "void handleExecute()", "void installRoutes()")
    assert execute.index("persistCursor(kPhaseConsumed, 1)") < execute.index(
        "executePending = true"
    )
    for token in (
        '"startup_refresh":false',
        '"raw_frame_ingress":false',
        '"raw_lut_ingress":false',
        '"retry":false',
        '"automatic_chaining":false',
        '"profile_switch":false',
        '"vendor_proven":false',
        '"live_authorized_until_exact_token":false',
        '"single_busy_observes_master_only":true',
        '"slave_profile_acceptance_proven":false',
    ):
        assert token.replace('"', '\\"') in source
    assert [f"U{index}" for index in range(1, 8)] == re.findall(
        r'\\"id\\":\\"(U\d)\\"', source
    )
    for forbidden in (
        '"/api/frame"',
        "server.upload",
        "HTTP_PUT",
        "epdDisplayFrame(",
        "epdClearWhite(",
        "cursorStore.clear(",
        "cursorStore.remove(",
    ):
        assert forbidden not in source


def test_recovery_is_one_action_factory_only_and_hard_resets_before_white() -> None:
    main = RECOVERY_MAIN.read_text(encoding="utf-8")
    driver = RECOVERY_DRIVER.read_text(encoding="utf-8")
    assert main.count("epdDisplayCompiledFactoryOtpWhiteRecovery()") == 1
    assert "epdDisplayCompiledEmpiricalH3" not in main
    assert "generated/spd1657" not in main
    assert "kR20Payload" not in main + driver
    assert "kR21Payload" not in main + driver
    assert "HiddenLutEnable" not in main + driver
    assert "epdCommand(" not in driver
    setup = _between(main, "void setup()", "void loop()")
    assert setup.index(
        "epdValidateCompiledFactoryOtpWhiteRecoveryFixture()"
    ) < setup.index("epdBegin()")
    assert "epdDisplayCompiledFactoryOtpWhiteRecovery" not in setup
    display = driver[driver.index("bool epdDisplayCompiledFactoryOtpWhiteRecovery") :]
    assert display.index("fowrValidateFrame(frame, &validation)") < display.index(
        "epdPrepareCascade(EPD_SPI_DEFAULT_HZ)"
    )
    assert display.index("epdPrepareCascade(EPD_SPI_DEFAULT_HZ)") < display.index(
        "epdStreamPackedFrameController(frame, false)"
    )
    assert display.index(
        "epdStreamPackedFrameController(frame, false)"
    ) < display.index("epdStreamPackedFrameController(frame, true)")
    assert display.index("epdStreamPackedFrameController(frame, true)") < display.index(
        "epdSecondSettingAndRefresh()"
    )

    common = DRIVER_CPP.read_text(encoding="utf-8")
    init = _between(
        common,
        "static bool epdInitResolutionSelected",
        "static bool epdInitResolution(",
    )
    assert init.index("epdReset()") < init.index("epdCommand(PSR)")
    assert re.search(r"epdCommand\(PSR\);\s*epdData\(0x5F\);\s*epdData\(0x69\);", init)
    prepare = _between(
        common,
        "static bool epdPrepareCascade",
        "static bool epdDiagnosticDualSolidImpl",
    )
    assert "epdInitResolutionSelected" in prepare
    assert "epdEnableCascadeOnBothControllers" in prepare


def test_device_reports_preserve_full_busy_and_final_gpio_evidence() -> None:
    runtime = RUNTIME_MAIN.read_text(encoding="utf-8")
    recovery = RECOVERY_MAIN.read_text(encoding="utf-8")
    common = DRIVER_CPP.read_text(encoding="utf-8")
    assert '#include "epd_diagnostics.h"' in runtime
    assert '#include "epd_diagnostics.h"' in recovery
    assert runtime.count("epdDiagnosticReportJson()") == 2
    assert recovery.count("epdDiagnosticReportJson()") == 2
    report = _between(
        common,
        "String epdDiagnosticReportJson()",
        "const EpdOperationReport &epdGetLastOperationReport()",
    )
    for token in (
        '"pon_busy_seen"',
        '"drf_busy_seen"',
        '"pof_busy_seen"',
        '"failure_stage"',
        '"failure_code"',
        '"busy_trace"',
        '"reset"',
        '"pon"',
        '"drf"',
        '"pof"',
        '"post_psr"',
        '"safe_finish"',
        '"busy_before_pins_low"',
        '"busy_after_pins_low"',
        '"busy_after_5ms"',
        '"final_gpio"',
        '"rst"',
        '"cs"',
        '"cs2"',
        '"sck"',
        '"dc"',
        '"mosi"',
    ):
        assert token.replace('"', '\\"') in report


def test_recovery_mirrors_once_envelope_without_claiming_temperature_safety() -> None:
    source = RECOVERY_MAIN.read_text(encoding="utf-8")
    for token in (
        '"profile":',
        '"compiled_profile_count":1',
        '"auto_selected":false',
        '"apparent_temperature_min_c":0',
        '"apparent_temperature_max_c":37',
        '"temperature_policy":',
        '"temperature_limit_is_safety_qualification":false',
        '"actions":[',
        '"raw_lut_ingress":false',
        '"electrical_parameter_ingress":false',
        '"timing_parameter_ingress":false',
        '"profile_switch":false',
        '"phase":',
        '"phase_name":',
        '"next_ordinal":',
        '"total_driver_call_count":',
        '"driver_call_count_for_action":0',
        '"driver_call_count_for_action":1',
        '"job_id":2',
    ):
        assert token.replace('"', '\\"') in source
    assert [f"U{index}" for index in range(1, 8)] == re.findall(
        r'\\"id\\":\\"(U\d)\\"', source
    )


def test_runtime_profile_echoes_frozen_requested_electrical_metadata() -> None:
    source = RUNTIME_MAIN.read_text(encoding="utf-8")
    header = DRIVER_HEADER.read_text(encoding="utf-8")
    driver = RUNTIME_DRIVER.read_text(encoding="utf-8")
    for field in (
        "requestedGatePositiveMv",
        "requestedGateNegativeMv",
        "requestedFullSourcePositiveMv",
        "requestedFullSourceNegativeMv",
        "requestedVshLvMv",
        "requestedVslLvMv",
        "requestedVshLv2Mv",
        "requestedVslLv2Mv",
        "requestedFrameRateHz",
    ):
        assert field in header
        assert f"profile.{field}" in source
    for field in (
        "kRequestedGatePositiveMv",
        "kRequestedGateNegativeMv",
        "kRequestedFullSourcePositiveMv",
        "kRequestedFullSourceNegativeMv",
        "kRequestedVshLvMv",
        "kRequestedVslLvMv",
        "kRequestedVshLv2Mv",
        "kRequestedVslLv2Mv",
        "kRequestedFrameRateHz",
    ):
        assert field in driver
    assert '"panel_or_fpl_limits_proven"'.replace('"', '\\"') in source
    assert '"h3_header_binding_proven"'.replace('"', '\\"') in source


def test_running_elf_identity_is_checked_before_gpio_initialization() -> None:
    for path, fixture_check in (
        (RUNTIME_MAIN, "epdValidateCompiledEmpiricalH3Fixtures()"),
        (RECOVERY_MAIN, "epdValidateCompiledFactoryOtpWhiteRecoveryFixture()"),
    ):
        source = path.read_text(encoding="utf-8")
        assert "#include <esp_ota_ops.h>" in source
        loader = _between(
            source, "bool loadRunningAppElfSha256()", "uint16_t encodeCursor"
        )
        assert "esp_ota_get_app_description()" in loader
        assert "sizeof(description->app_elf_sha256)" in loader
        assert "runningAppElfSha256[index * 2]" in loader
        assert "runningAppElfSha256[index * 2 + 1]" in loader
        assert "runningAppElfSha256[64] = '\\0'" in loader
        assert "esp_ota_get_app_elf_sha256" not in loader
        assert '"running_app_elf_sha256"'.replace('"', '\\"') in source
        setup = _between(source, "void setup()", "void loop()")
        assert setup.index("loadRunningAppElfSha256()") < setup.index(fixture_check)
        assert setup.index("loadRunningAppElfSha256()") < setup.index("epdBegin()")
        assert "running_app_elf_sha256_self_check_failed" in setup


def test_status_and_terminal_report_cover_all_panel_facing_low_gpio() -> None:
    header = DRIVER_HEADER.read_text(encoding="utf-8")
    common = DRIVER_CPP.read_text(encoding="utf-8")
    for field in ("finalSckLevel", "finalDcLevel", "finalMosiLevel"):
        assert field in header
        assert field in common
    for path in (RUNTIME_MAIN, RECOVERY_MAIN):
        source = path.read_text(encoding="utf-8")
        gpio = _between(source, "String gpioJson()", "String statusJson()")
        for pin in (
            "EPD_PIN_RST",
            "EPD_PIN_CS",
            "EPD_PIN_CS2",
            "EPD_PIN_SCK",
            "EPD_PIN_DC",
            "EPD_PIN_MOSI",
        ):
            assert f"digitalRead({pin})" in gpio


def test_driver_header_and_cpp_keep_both_new_fixtures_mutually_isolated() -> None:
    header = DRIVER_HEADER.read_text(encoding="utf-8")
    cpp = DRIVER_CPP.read_text(encoding="utf-8")
    for macro in (
        "MF1750_ENABLE_RUNTIME_LUT_EMPIRICAL_H3",
        "MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY",
    ):
        assert f"#define {macro} 0" in header
    assert '#include "ec5_runtime_lut_empirical_h3_driver.inc"' in cpp
    assert '#include "ec5_factory_otp_white_recovery_driver.inc"' in cpp
    assert "must select exactly one explicit vendor profile" in header
    assert "must bind exactly one campaign profile" in header
    assert "isolated from every other fixture" in header
