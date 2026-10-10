from __future__ import annotations

from pathlib import Path
import re

from tools import mf1750_ec5_h3_matched_control_contract as matched_contract


ROOT = Path(__file__).resolve().parents[1]
CONTROL_HEADER = ROOT / "src/ec5_h3_matched_control_driver.h"
CONTROL_WRAPPER = ROOT / "src/ec5_h3_matched_control_driver.cpp"
CONTROL_DRIVER = ROOT / "src/ec5_h3_matched_control_driver.inc"
CONTROL_MAIN = ROOT / "src/ec5_h3_matched_control_main.cpp"
RECOVERY_MAIN = ROOT / "src/ec5_h3_matched_control_otp_white_main.cpp"
ONCE_ENVELOPE = ROOT / "src/ec5_h3_matched_control_once_main.inc"
H3_DRIVER = ROOT / "src/ec5_runtime_lut_empirical_h3_driver.inc"
GENERATED_WF20 = ROOT / "src/generated/spd1657_wf20_25_empirical_h3.inc"
CONTROL_CONFIG = ROOT / "platformio.h3_matched_control_wf20_25.ini"
RECOVERY_CONFIG = ROOT / "platformio.h3_matched_control_otp_white_wf20_25.ini"


def _between(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    finish = source.index(end, begin)
    return source[begin:finish]


def _literal(source: str, name: str) -> str:
    match = re.search(
        rf"static constexpr char {re.escape(name)}\[\]\s*=\s*"
        r'"([^"]+)";',
        source,
    )
    assert match is not None, name
    return match.group(1)


def _byte_array(source: str, name: str) -> tuple[int, ...]:
    match = re.search(
        rf"(?:static constexpr (?:std::)?uint8_t {re.escape(name)})"
        r"(?:\[\d+\])?\s*=\s*\{([^}}]+)\};",
        source,
    )
    assert match is not None, name
    return tuple(
        int(value, 16) for value in re.findall(r"0x([0-9A-Fa-f]+)", match.group(1))
    )


def test_control_has_a_closed_command_allowlist_without_r20_or_r21() -> None:
    source = CONTROL_DRIVER.read_text(encoding="utf-8")
    enum_block = _between(
        source, "enum class H3MatchedFixedCommand", "static constexpr uint8_t"
    )
    commands = {
        name: int(value, 16)
        for name, value in re.findall(r"(\w+)\s*=\s*0x([0-9A-Fa-f]{2})", enum_block)
    }
    assert commands == {
        "PanelSetting": 0x00,
        "PowerSetting": 0x01,
        "Pll": 0x30,
        "Resolution": 0x61,
        "HiddenLutEnable": 0xE9,
    }
    assert 0x20 not in commands.values()
    assert 0x21 not in commands.values()
    for forbidden in (
        "LutR20",
        "LutR21",
        "kR20Payload",
        "kR21Payload",
        "generated/spd1657",
        "h3UploadFixedWaveformToController",
    ):
        assert forbidden not in source + CONTROL_WRAPPER.read_text(encoding="utf-8")
    emitter = _between(
        source, "void h3mcEmitFixedCommand", "void h3mcWriteFixedPayload"
    )
    assert source.count("epdCommand(") == 1
    assert "epdCommand(static_cast<uint8_t>(command))" in emitter


def test_control_freezes_the_same_wf20_power_pll_psr_tres_and_e9() -> None:
    control = CONTROL_DRIVER.read_text(encoding="utf-8")
    generated = GENERATED_WF20.read_text(encoding="utf-8")
    assert _byte_array(control, "H3MC_POWER_PAYLOAD") == _byte_array(
        generated, "kPowerPayload"
    )
    assert _byte_array(control, "H3MC_PLL_PAYLOAD") == _byte_array(
        generated, "kPllPayload"
    )
    assert _byte_array(control, "H3MC_RUNTIME_PSR") == (0x5F, 0xE9)
    assert _byte_array(control, "H3MC_CONTROLLER_TRES") == (0x02, 0x00, 0x02, 0x58)
    assert _byte_array(control, "H3MC_HIDDEN_ENABLE") == (0x01,)
    for hash_name in (
        "kSourceArtifactSha256",
        "kDecodedHeaderSha256",
        "kPowerPayloadSha256",
        "kPllPayloadSha256",
    ):
        expected = re.search(
            rf"static constexpr char {hash_name}\[\]\s*=\s*\"([0-9a-f]{{64}})\";",
            generated,
        )
        assert expected is not None
        assert expected.group(1) in control


def test_delete_only_trace_preserves_order_and_records_removed_upload_duration() -> (
    None
):
    control = CONTROL_DRIVER.read_text(encoding="utf-8")
    display = control[control.index("bool epdDisplayCompiledH3MatchedControl") :]
    expected_control = (
        "epdPrepareCascade(EPD_SPI_DEFAULT_HZ)",
        "h3mcApplyMatchedGlobalConfig()",
        "h3mcApplyHiddenEnableToController(false)",
        "h3mcApplyHiddenEnableToController(true)",
        "epdStreamPackedFrameController(frame, false)",
        "epdStreamPackedFrameController(frame, true)",
        "epdSecondSettingAndRefresh()",
    )
    positions = [display.index(token) for token in expected_control]
    assert positions == sorted(positions)

    h3 = H3_DRIVER.read_text(encoding="utf-8")
    h3_display = h3[h3.index("bool epdDisplayCompiledEmpiricalH3") :]
    expected_h3 = (
        "epdPrepareCascade(EPD_SPI_DEFAULT_HZ)",
        "h3ApplyFixedGlobalRuntimeConfigToBothControllers()",
        "h3UploadFixedWaveformToController(false)",
        "h3UploadFixedWaveformToController(true)",
        "epdStreamPackedFrameController(frame, false)",
        "epdStreamPackedFrameController(frame, true)",
        "epdSecondSettingAndRefresh()",
    )
    h3_positions = [h3_display.index(token) for token in expected_h3]
    assert h3_positions == sorted(h3_positions)

    global_config = _between(
        control,
        "bool h3mcApplyMatchedGlobalConfig()",
        "bool h3mcApplyHiddenEnableToController",
    )
    for token in (
        "setActiveControllers(true, true)",
        "PanelSetting",
        "PowerSetting",
        'epdWaitIdle("matched control PWR")',
        "H3MatchedFixedCommand::Pll",
        "H3MatchedFixedCommand::Resolution",
    ):
        assert token in global_config
    e9 = _between(
        control,
        "bool h3mcApplyHiddenEnableToController",
        "}  // namespace",
    )
    assert "setActiveControllers(!secondController, secondController)" in e9
    assert "H3MatchedFixedCommand::HiddenLutEnable" in e9
    assert "matched control CS1 E9" in e9
    assert "matched control CS2 E9" in e9

    main = CONTROL_MAIN.read_text(encoding="utf-8")
    assert "E9_ONLY_NO_R20_R21_COMMAND_STREAM_AND_DURATION_CONTROL" in main
    assert '"control_design\\":' in main
    assert '"strict_payload_only_control\\":false' in main
    assert '"time_matched_control\\":false' in main
    assert '"dummy_clocks_inserted\\":false' in main
    assert '"empty_r20_or_r21_commands_inserted\\":false' in main
    assert '"per_controller_removed_spi_bytes_and_edges\\":1505' in main
    assert '"per_controller_removed_cooperative_yields\\":5' in main
    assert "NO_DETECTABLE_INCREMENTAL_EFFECT" in main
    assert "dummy" not in control.lower()
    generated = GENERATED_WF20.read_text(encoding="utf-8")
    r20_bytes = int(
        re.search(r"kR20PayloadBytes\s*=\s*(\d+)", generated).group(1)  # type: ignore[union-attr]
    )
    r21_bytes = int(
        re.search(r"kR21PayloadBytes\s*=\s*(\d+)", generated).group(1)  # type: ignore[union-attr]
    )
    assert 1 + r20_bytes + 1 + r21_bytes == 1505
    assert r20_bytes // 256 + r21_bytes // 256 == 5
    assert "if ((index & 0xFFU) == 0xFFU) yield();" in h3


def test_control_atlas_identity_is_byte_for_byte_the_h3_identity() -> None:
    control = CONTROL_DRIVER.read_text(encoding="utf-8")
    h3 = H3_DRIVER.read_text(encoding="utf-8")
    for digest in (
        "77454fe933f79b301ecb55b2a065276e0f4fe122bf8416746f71f9b92e90637b",
        "85cd5683ae2d9c5bf9e97bea539a905cdf244983befaeba7e5321aa73ed774f7",
        "cfb5bba82a9421e4c3a13ed10731105d78852a05238ca52ddf3bd9cdd099b943",
    ):
        assert digest in control
        assert digest in h3
    for identity in ("0xCE553145UL", "0x639C1785UL", "0x1BADB785UL"):
        assert identity in control
        assert identity in h3
    histogram = "{16640, 548608, 8192, 8192, 8192, 8192, 8192, 8192}"
    assert histogram in control
    assert histogram in h3
    for geometry in (
        "H3MC_PATCH_SIDE = 64",
        "H3MC_BORDER = 2",
        "H3MC_LOCAL_X[4] = {48, 160, 272, 384}",
        "H3MC_Y0[2] = {190, 346}",
        "H3MC_CS1_ORDER[8] = {0, 1, 2, 3, 4, 5, 6, 7}",
        "H3MC_CS2_ORDER[8] = {7, 6, 5, 4, 3, 2, 1, 0}",
    ):
        assert geometry in control


def test_control_wrapper_reuses_common_private_path_without_linking_h3() -> None:
    header = CONTROL_HEADER.read_text(encoding="utf-8")
    wrapper = CONTROL_WRAPPER.read_text(encoding="utf-8")
    assert wrapper.count('#include "epd_driver.cpp"') == 1
    assert wrapper.count('#include "ec5_h3_matched_control_driver.inc"') == 1
    assert "ec5_runtime_lut_empirical_h3_driver.inc" not in wrapper
    assert "MF1750_ENABLE_H3_MATCHED_NO_R20_R21 != 1" in header
    assert "must be isolated from every existing fixture" in header
    assert "MF1750_ENABLE_RUNTIME_LUT_EMPIRICAL_H3" in header
    assert "MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY" in header


def test_both_builds_have_unique_source_sets_and_no_upload_directives() -> None:
    control = CONTROL_CONFIG.read_text(encoding="utf-8")
    recovery = RECOVERY_CONFIG.read_text(encoding="utf-8")
    assert "default_envs = ec5_h3_matched_no_r20_r21_wf20_25" in control
    assert "default_envs = ec5_h3_matched_control_otp_white_wf20_25" in recovery
    assert "+<ec5_h3_matched_control_driver.cpp>" in control
    assert "+<ec5_h3_matched_control_main.cpp>" in control
    assert "+<epd_driver.cpp>" not in control
    assert "+<epd_driver.cpp>" in recovery
    assert "+<ec5_h3_matched_control_otp_white_main.cpp>" in recovery
    assert "ec5_runtime_lut_empirical_h3_main.cpp" not in control + recovery
    assert "ec5_factory_otp_white_recovery_main.cpp" not in control + recovery
    assert "MF1750_ENABLE_RUNTIME_LUT_EMPIRICAL_H3=1" not in control + recovery
    assert "MF1750_ENABLE_H3_MATCHED_NO_R20_R21=1" in control
    assert "MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY=1" in recovery
    for source in (control, recovery):
        assert "-<*>" in source
        assert "EPD_ENABLE_TEST_PATTERN=0" in source
        assert "upload_port" not in source
        assert "upload_flags" not in source
        assert "extra_scripts" not in source


def test_frozen_identity_namespace_routes_actions_and_markers_are_disjoint() -> None:
    control = CONTROL_MAIN.read_text(encoding="utf-8")
    recovery = RECOVERY_MAIN.read_text(encoding="utf-8")
    root_contract = matched_contract.profile_contract()
    action_by_role = {action["role"]: action for action in root_contract["actions"]}
    control_binding = matched_contract.device_binding(
        "WF20_25", matched_contract.ROLE_CONTROL
    )
    recovery_binding = matched_contract.device_binding(
        "WF20_25", matched_contract.ROLE_WHITE
    )
    expected = {
        "contract": root_contract["contract_id"],
        "control_descriptor": action_by_role[matched_contract.ROLE_CONTROL][
            "transaction_descriptor_sha256"
        ],
        "control_action": action_by_role[matched_contract.ROLE_CONTROL][
            "hardware_action_id"
        ],
        "recovery_descriptor": action_by_role[matched_contract.ROLE_WHITE][
            "transaction_descriptor_sha256"
        ],
        "recovery_action": action_by_role[matched_contract.ROLE_WHITE][
            "hardware_action_id"
        ],
    }
    assert expected["contract"] in control and expected["contract"] in recovery
    assert expected["control_descriptor"] in control
    assert expected["control_action"] in control
    assert expected["recovery_descriptor"] in recovery
    assert expected["recovery_action"] in recovery
    assert _literal(control, "kH3mcCampaignId") == matched_contract.CAMPAIGN_ID
    assert _literal(recovery, "kH3mcCampaignId") == matched_contract.CAMPAIGN_ID
    assert (
        _literal(control, "kH3mcDeviceApiVersion")
        == matched_contract.DEVICE_API_VERSION
    )
    assert (
        _literal(recovery, "kH3mcDeviceApiVersion")
        == matched_contract.DEVICE_API_VERSION
    )
    assert _literal(control, "kH3mcNvsNamespace") == "h3ctl_w20_v2"
    assert _literal(recovery, "kH3mcNvsNamespace") == "h3crw20_v2"
    assert 'kH3mcNvsKey[] = "used_v2"' in ONCE_ENVELOPE.read_text(encoding="utf-8")
    for superseded in (*matched_contract.SUPERSEDED_V1_NVS_NAMESPACES, "used_v1"):
        assert superseded not in control + recovery + ONCE_ENVELOPE.read_text(
            encoding="utf-8"
        )
    assert _literal(control, "kH3mcBaseRoute") == control_binding["base_route"]
    assert _literal(recovery, "kH3mcBaseRoute") == recovery_binding["base_route"]
    assert _literal(control, "kH3mcBuildTag") == control_binding["build_tag"]
    assert _literal(recovery, "kH3mcBuildTag") == recovery_binding["build_tag"]
    assert _literal(control, "kH3mcTestId") == control_binding["test_id"]
    assert _literal(recovery, "kH3mcTestId") == recovery_binding["test_id"]
    assert _literal(control, "kH3mcRole") == matched_contract.ROLE_CONTROL
    assert _literal(recovery, "kH3mcRole") == matched_contract.ROLE_WHITE
    control_audit = matched_contract.command_audit_marker(
        "WF20_25", matched_contract.ROLE_CONTROL
    )
    recovery_audit = matched_contract.command_audit_marker(
        "WF20_25", matched_contract.ROLE_WHITE
    )
    assert control.count(control_audit) == 1
    assert recovery.count(recovery_audit) == 1
    assert control_audit not in recovery
    assert recovery_audit not in control


def test_common_envelope_is_bodyless_once_only_and_never_autochains() -> None:
    common = ONCE_ENVELOPE.read_text(encoding="utf-8")
    assert "EPD_ENABLE_TEST_PATTERN != 0" in common
    version = _between(common, "String h3mcVersionJson()", "String h3mcManifestJson()")
    assert (
        '"\\",\\"profile\\":" + h3mcOnceProfileJson() +\n'
        '         ",\\"action_count\\":1,\\"startup_refresh\\":false,"' in version
    )
    assert 'h3mcOnceProfileJson() +\n         "\\",\\"action_count\\":1' not in version
    assert version.count("h3mcOnceProfileJson()") == 1
    setup = _between(common, "void setup()", "void loop()")
    assert setup.index("h3mcLoadRunningAppElfSha256()") < setup.index(
        "h3mcOnceValidateFixture()"
    )
    assert setup.index("h3mcOnceValidateFixture()") < setup.index("epdBegin()")
    assert "h3mcOnceExecuteFixture" not in setup
    execute = _between(common, "void h3mcHandleExecute()", "void h3mcInstallRoutes()")
    assert execute.index(
        "h3mcPersistCursor(kH3mcPhaseConsumed, kH3mcActionOrdinal)"
    ) < execute.index("h3mcExecutePending = true")
    runner = _between(common, "void h3mcExecutePendingAction()", "}  // namespace")
    assert runner.count("h3mcOnceExecuteFixture()") == 1
    assert "h3mcDriverCallCountForAction != 0" in runner
    for token in (
        '"startup_refresh\\":false',
        '"raw_frame_ingress\\":false',
        '"raw_lut_ingress\\":false',
        '"retry\\":false',
        '"automatic_chaining\\":false',
        '"automatic_recovery\\":false',
        '"profile_switch\\":false',
        '"clear_route\\":false',
    ):
        assert token in common
    for forbidden in (
        '"/api/frame"',
        "server.upload",
        "HTTP_PUT",
        "cursorStore.clear(",
        "cursorStore.remove(",
    ):
        assert forbidden not in common


def test_control_and_recovery_call_only_their_one_compiled_action() -> None:
    control = CONTROL_MAIN.read_text(encoding="utf-8")
    recovery = RECOVERY_MAIN.read_text(encoding="utf-8")
    assert control.count("epdDisplayCompiledH3MatchedControl(") == 1
    assert "epdDisplayCompiledFactoryOtpWhiteRecovery(" not in control
    assert "epdDisplayCompiledEmpiricalH3(" not in control
    assert recovery.count("epdDisplayCompiledFactoryOtpWhiteRecovery()") == 1
    assert "epdDisplayCompiledH3MatchedControl(" not in recovery
    assert "epdDisplayCompiledEmpiricalH3(" not in recovery
    assert "generated/spd1657" not in recovery
    assert "kR20Payload" not in recovery
    assert "kR21Payload" not in recovery
    assert 'runtime_payload_present\\":false' in recovery
