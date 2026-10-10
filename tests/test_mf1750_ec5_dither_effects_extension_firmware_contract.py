from __future__ import annotations

import hashlib
from pathlib import Path
import re

from host import dither_effects_suite as suite
from tools import mf1750_ec5_dither_effects_extension_contract as contract


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src/ec5_dither_effects_extension_main.cpp"
DRIVER = ROOT / "src/ec5_dither_effects_extension_driver.inc"
HEADER = ROOT / "src/epd_driver.h"
DRIVER_CPP = ROOT / "src/epd_driver.cpp"
EXTENSION_HEADER = ROOT / "src/ec5_dither_effects_extension_epd_driver.h"
EXTENSION_DRIVER_CPP = ROOT / "src/ec5_dither_effects_extension_epd_driver.cpp"
PLATFORMIO = ROOT / "platformio.dither_effects_extension.ini"


def _literal(source: str, name: str) -> str:
    match = re.search(
        rf'static constexpr const char \*{re.escape(name)}\s*=\s*"([^"]+)";',
        source,
    )
    assert match is not None, name
    return match.group(1)


def _char_array(source: str, name: str) -> str:
    match = re.search(
        rf'static constexpr char {re.escape(name)}\[\]\s*=\s*"([^"]+)";',
        source,
    )
    assert match is not None, name
    return match.group(1)


def _between(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    return source[begin : source.index(end, begin)]


def _histogram(role: str) -> str:
    values = contract.ROLE_IDENTITIES[role]["histogram_codes_0_to_7"]
    return "{" + ", ".join(str(value) for value in values) + "}"


def test_main_identity_routes_anchor_and_four_actions_match_contract() -> None:
    source = MAIN.read_text(encoding="utf-8")
    manifest = contract.campaign_manifest()
    expected = {
        "kClassification": contract.CLASSIFICATION,
        "kProfileSource": "factory_otp",
        "kIdentityRevision": contract.IDENTITY_REVISION,
        "kDeviceApiVersion": contract.DEVICE_API_VERSION,
        "kLayoutId": contract.LAYOUT_ID,
        "kBuildTag": contract.BUILD_TAG,
        "kTestId": contract.TEST_ID,
        "kCampaignId": contract.CAMPAIGN_ID,
        "kContractId": manifest["contract_id"],
        "kNvsNamespace": contract.NVS_NAMESPACE,
        "kNvsKey": contract.NVS_KEY,
    }
    for name, value in expected.items():
        assert _literal(source, name) == value

    prefix = "/api/ec5/dither-effects-extension"
    for name, suffix in (
        ("kVersionRoute", "version"),
        ("kManifestRoute", "manifest"),
        ("kStatusRoute", "status"),
        ("kReportRoute", "report"),
        ("kArmRoute", "arm"),
        ("kExecuteRoute", "execute"),
    ):
        assert _literal(source, name) == f"{prefix}/{suffix}"

    anchor = _between(source, "String anchorContractJson()", "String identityJson()")
    for token in (
        contract.PREDECESSOR_CAMPAIGN_ID,
        r"\"ordinal\":2",
        contract.PREDECESSOR_ROLE,
        contract.PREDECESSOR_ACTION_ID,
        r"\"evidence_bound_at_release_materialization\":true",
        r"\"required_host_gate_for_ordinal_1\":true",
    ):
        assert token in anchor

    table = _between(
        source,
        "static constexpr ActionDescriptor kActions[] = {",
        "static_assert(sizeof(kActions)",
    )
    assert "kActionCount = 4" in source
    assert "kTerminalOrdinal = kActionCount + 1" in source
    assert r"\"terminal_next_ordinal\":5" in source
    assert table.count("EpdDitherEffectsExtensionRole::") == 4
    for descriptor in contract.DESCRIPTORS:
        role = str(descriptor["role"])
        identity = contract.ROLE_IDENTITIES[role]
        for token in (
            role,
            str(descriptor["branch"]),
            str(descriptor["descriptor_id"]),
            str(descriptor["hardware_action_id"]),
            f"0x{identity['frame']['fnv1a_u32']:08X}UL",
            f"0x{identity['cs1_dtm']['fnv1a_u32']:08X}UL",
            f"0x{identity['cs2_dtm']['fnv1a_u32']:08X}UL",
            _histogram(role),
        ):
            assert token in table
        for token in (
            str(descriptor["frame_sha256"]),
            str(descriptor["cs1_dtm_sha256"]),
            str(descriptor["cs2_dtm_sha256"]),
        ):
            assert token in source


def test_main_is_bodyless_one_shot_and_exposes_no_raw_or_waveform_path() -> None:
    source = MAIN.read_text(encoding="utf-8")
    setup = _between(source, "void setup()", "void loop()")
    assert setup.index(
        "epdValidateCompiledDitherEffectsExtensionFixtures()"
    ) < setup.index("epdBegin()")
    assert "epdDisplayCompiledDitherEffectsExtension" not in setup
    assert "epdClear" not in setup

    routes = _between(source, "void installRoutes()", "void startWiFi()")
    assert routes.count("server.on(") == 6
    assert routes.count("HTTP_GET") == 4
    assert routes.count("server.on(kArmRoute, HTTP_POST") == 1
    assert routes.count("server.on(kExecuteRoute, HTTP_POST") == 1

    worker = _between(source, "void executePendingAction()", "}  // namespace")
    call = "epdDisplayCompiledDitherEffectsExtension(action->driverRole)"
    assert source.count(call) == 1
    assert worker.index("persistentPhase != kPhaseConsumed") < worker.index(call)
    assert worker.index("++driverCallCountForAction") < worker.index(call)
    assert "persistCursor(kPhaseFault, action->ordinal)" in worker
    assert "persistCursor(kPhaseReady, followingOrdinal)" in worker

    for required in (
        r"\"action_count\":4",
        r"\"automatic_chaining\":false",
        r"\"startup_refresh\":false",
        r"\"raw_frame_ingress\":false",
        r"\"runtime_lut_write\":false",
        r"\"electrical_parameter_write\":false",
        r"\"retry\":false",
        r"\"recovery\":false",
        "persistCursor(kPhaseConsumed, action->ordinal)",
        "arm_nonce_forbidden_during_arm",
        "arm_nonce_missing_or_stale",
    ):
        assert required in source
    for forbidden in (
        '"/api/frame"',
        '"/api/ec5/reset"',
        '"/api/ec5/retry"',
        '"/api/ec5/recovery"',
        '"/api/ec5/partial"',
        "server.upload",
        "HTTP_PUT",
        "epdDisplayFrame(",
        "epdDisplayFrameAtFrequency(",
        "epdClearWhite(",
        "epdClearBlack(",
        "cursorStore.clear(",
        "cursorStore.remove(",
        "nvs_flash_erase",
    ):
        assert forbidden not in source


def test_driver_layout_and_all_three_compiled_identities_match_host() -> None:
    driver = DRIVER.read_text(encoding="utf-8")
    scalars = {
        "DEE_GRADIENT_X0_LOCAL": suite.GRADIENT_X0_LOCAL,
        "DEE_GRADIENT_WIDTH": suite.GRADIENT_WIDTH,
        "DEE_GRADIENT_Y0": suite.GRADIENT_Y0,
        "DEE_GRADIENT_ROW_HEIGHT": suite.GRADIENT_ROW_HEIGHT,
        "DEE_GRADIENT_ROW_GAP": suite.GRADIENT_ROW_GAP,
        "DEE_CHART_X0_LOCAL": suite.CHART_X0_LOCAL,
        "DEE_CHART_WIDTH": suite.CHART_WIDTH,
        "DEE_TRIFIELD_HEIGHT": suite.TRIFIELD_HEIGHT,
        "DEE_NEUTRAL_Y0": suite.NEUTRAL_Y0,
        "DEE_BLOCK_Y0": suite.BLOCK_Y0,
        "DEE_DETAIL_Y0": suite.DETAIL_Y0,
    }
    for name, value in scalars.items():
        assert re.search(rf"\b{name}\s*=\s*{value};", driver)

    matrix = "\n".join(
        "    {" + ", ".join(str(value) for value in row) + "},"
        for row in suite.BAYER_8X8
    )
    assert matrix in driver
    pairs = ", ".join(
        f"{{{family.code_a}, {family.code_b}}}" for family in suite.MIX_FAMILIES
    )
    assert pairs in driver

    arrays = {
        suite.ROLE_PAIR_GRADIENTS: (
            "DEE_PAIR_GRADIENTS_FRAME_SHA256",
            "DEE_PAIR_GRADIENTS_CS1_DTM_SHA256",
            "DEE_PAIR_GRADIENTS_CS2_DTM_SHA256",
        ),
        suite.ROLE_EFFECTS_CHART: (
            "DEE_EFFECTS_CHART_FRAME_SHA256",
            "DEE_EFFECTS_CHART_CS1_DTM_SHA256",
            "DEE_EFFECTS_CHART_CS2_DTM_SHA256",
        ),
        suite.ROLE_WHITE: (
            "DEE_WHITE_FRAME_SHA256",
            "DEE_WHITE_DTM_SHA256",
            "DEE_WHITE_DTM_SHA256",
        ),
    }
    for role, names in arrays.items():
        identity = suite.frame_identity(role)
        assert tuple(_char_array(driver, name) for name in names) == (
            identity.frame.sha256,
            identity.cs1_dtm.sha256,
            identity.cs2_dtm.sha256,
        )
        for value in (
            identity.frame.fnv1a_u32,
            identity.cs1_dtm.fnv1a_u32,
            identity.cs2_dtm.fnv1a_u32,
        ):
            assert f"0x{value:08X}UL" in driver
        histogram = "{" + ", ".join(str(value) for value in identity.histogram) + "}"
        assert histogram in driver


def test_display_validates_full_frame_and_both_streams_before_panel_io() -> None:
    driver = DRIVER.read_text(encoding="utf-8")
    validator = _between(driver, "bool deeValidateRole", "}  // namespace")
    for token in (
        "std::memcmp(histogram, wanted.histogram",
        "fnv1a(frame, EPD_FRAME_BYTES)",
        "mbedtls_sha256_ret(frame, EPD_FRAME_BYTES",
        "deeComputeDtmIdentity(frame, false",
        "deeComputeDtmIdentity(frame, true",
        "wanted.frameSha256",
        "wanted.cs1DtmSha256",
        "wanted.cs2DtmSha256",
    ):
        assert token in validator

    display = driver[driver.index("bool epdDisplayCompiledDitherEffectsExtension") :]
    assert display.index("deeValidateRole(role, frame, &validation)") < display.index(
        "epdPrepareCascade(EPD_SPI_DEFAULT_HZ)"
    )
    assert display.count("epdStreamPackedFrameController(frame, false)") == 1
    assert display.count("epdStreamPackedFrameController(frame, true)") == 1
    assert display.count("epdSecondSettingAndRefresh()") == 1
    for forbidden in (
        "epdDisplayFrame(",
        "epdDisplayFrameAtFrequency(",
        "epdSetLut",
        "epdWriteLut",
        "epdSetVoltage",
        "retry",
        "recovery",
    ):
        assert forbidden not in display


def test_fixture_is_isolated_in_header_driver_and_platformio_environment() -> None:
    header = HEADER.read_text(encoding="utf-8")
    driver_cpp = DRIVER_CPP.read_text(encoding="utf-8")
    extension_header = EXTENSION_HEADER.read_text(encoding="utf-8")
    extension_driver_cpp = EXTENSION_DRIVER_CPP.read_text(encoding="utf-8")
    config = PLATFORMIO.read_text(encoding="utf-8")
    for token in (
        "EpdDitherEffectsExtensionRole",
        "epdValidateCompiledDitherEffectsExtensionFixtures",
        "epdDisplayCompiledDitherEffectsExtension",
    ):
        assert token not in header
        assert token not in driver_cpp
        assert token in extension_header
    assert hashlib.sha256(HEADER.read_bytes()).hexdigest() == (
        "3bbddfe8893e3024b0d745b0342dd1be576ebb6be7017ef4704952636ad42343"
    )
    assert hashlib.sha256(DRIVER_CPP.read_bytes()).hexdigest() == (
        "386acdd3e2fef3d22e4b97551330d310b86d1aafc5085df35a676e9b8dad2f6c"
    )
    assert '#include "epd_driver.cpp"' in extension_driver_cpp
    assert '#include "ec5_dither_effects_extension_driver.inc"' in extension_driver_cpp
    assert "dedicated PlatformIO environment" in extension_header
    assert "-<*>" in config
    assert "+<epd_driver.cpp>" not in config
    assert "+<ec5_dither_effects_extension_epd_driver.cpp>" in config
    assert "+<ec5_dither_effects_extension_main.cpp>" in config
    assert "EPD_ENABLE_TEST_PATTERN=0" in config
    assert "MF1750_ENABLE_DITHER_EFFECTS_EXTENSION=1" in config
    for forbidden in ("upload_port", "monitor_port", "targets = upload"):
        assert forbidden not in config
