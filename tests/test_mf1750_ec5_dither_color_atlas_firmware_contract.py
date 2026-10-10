from __future__ import annotations

from pathlib import Path
import re

from host import dither_color_atlas as atlas
from tools import mf1750_ec5_dither_color_atlas_contract as contract


ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "src/ec5_dither_color_atlas_main.cpp"
DRIVER_PATH = ROOT / "src/ec5_dither_color_atlas_driver.inc"
HEADER_PATH = ROOT / "src/epd_driver.h"
DRIVER_CPP_PATH = ROOT / "src/epd_driver.cpp"
PLATFORMIO_PATH = ROOT / "platformio.dither_color_atlas.ini"

ANCHOR_CAMPAIGN_ID = "EC5_OTP_TRANSITION_MATRIX_CAMPAIGN_V1"
ANCHOR_ACTION_ID = "54190f82f4797d1e0d46b2e002f6cbad006bdcdd7eb73b6ae5c0325acbfcae77"
ANCHOR_RESULT_FILE_SHA256 = (
    "d525173ed358246b6890fcf871a5c3268675f4b9b922d66fdb6911725ecb635c"
)
ANCHOR_OBSERVATION_FILE_SHA256 = (
    "5d5bf4414ac8d150e73bde393f438f069ba511f719808723156cf2ba66b68e41"
)
ANCHOR_CLAIM_SHA256 = "78cbd7d30d0b82476bd227a82fa879cfc1bc749c584a6f5c18500679f1e52e20"


def _literal(source: str, name: str) -> str:
    match = re.search(
        rf'static constexpr const char \*{re.escape(name)}\s*=\s*"([^"]+)";',
        source,
    )
    assert match is not None, name
    return match.group(1)


def _char_array_literal(source: str, name: str) -> str:
    match = re.search(
        rf'static constexpr char {re.escape(name)}\[\]\s*=\s*"([^"]+)";',
        source,
    )
    assert match is not None, name
    return match.group(1)


def _between(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    finish = source.index(end, begin)
    return source[begin:finish]


def _identity(role: str) -> dict[str, object]:
    return dict(contract.ROLE_IDENTITIES[role])


def _histogram_literal(role: str) -> str:
    frame = contract.role_frame(role)
    counts = [0] * 8
    for packed in frame:
        counts[packed >> 4] += 1
        counts[packed & 0x0F] += 1
    return "{" + ", ".join(str(value) for value in counts) + "}"


def test_main_identity_routes_and_execution_classification_match_contract() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
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

    prefix = "/api/ec5/dither-color-atlas"
    expected_routes = {
        "kVersionRoute": f"{prefix}/version",
        "kManifestRoute": f"{prefix}/manifest",
        "kStatusRoute": f"{prefix}/status",
        "kReportRoute": f"{prefix}/report",
        "kArmRoute": f"{prefix}/arm",
        "kExecuteRoute": f"{prefix}/execute",
    }
    for name, route in expected_routes.items():
        assert _literal(source, name) == route


def test_exact_two_actions_bind_ids_hashes_fnvs_histograms_and_prior() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    table = _between(
        source,
        "static constexpr ActionDescriptor kActions[] = {",
        "static_assert(sizeof(kActions)",
    )
    assert len(contract.DESCRIPTORS) == 2
    assert "kActionCount = 2" in source
    assert "kTerminalOrdinal = kActionCount + 1" in source
    assert "must contain exactly two actions" in source
    assert table.count("EpdDitherColorAtlasRole::") == 2
    assert "EpdDitherColorAtlasRole::Atlas" in table
    assert "EpdDitherColorAtlasRole::White" in table

    descriptor_positions: list[int] = []
    action_positions: list[int] = []
    for index, descriptor in enumerate(contract.DESCRIPTORS):
        descriptor_id = descriptor["descriptor_id"]
        action_id = descriptor["hardware_action_id"]
        descriptor_positions.append(table.index(descriptor_id))
        action_positions.append(table.index(action_id))
        assert descriptor["role"] in table
        assert descriptor["branch"] in table

        next_descriptor = (
            contract.DESCRIPTORS[index + 1]["descriptor_id"]
            if index + 1 < len(contract.DESCRIPTORS)
            else None
        )
        start = table.index(descriptor_id)
        end = table.index(next_descriptor, start) if next_descriptor else len(table)
        block = table[start:end]
        identity = _identity(descriptor["role"])
        for field in ("frame", "cs1_dtm", "cs2_dtm"):
            payload = identity[field]
            assert isinstance(payload, dict)
            assert payload["sha256"] in source
            assert f"0x{payload['fnv1a_u32']:08X}UL" in block
        assert _histogram_literal(descriptor["role"]) in block

        prior = descriptor["action_identity_preimage"]["prior_static_action_id"]
        if prior is None:
            assert "nullptr" in block
        else:
            assert prior in block

    assert descriptor_positions == sorted(descriptor_positions)
    assert action_positions == sorted(action_positions)


def test_action_json_and_campaign_flags_keep_the_mature_fail_closed_shape() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    action_json = _between(source, "String actionJson", "String versionJson")
    for key in (
        "ordinal",
        "descriptor_id",
        "action_id",
        "prior_static_action_id",
        "role",
        "round",
        "branch",
        "frame_sha256",
        "cs1_dtm_sha256",
        "cs2_dtm_sha256",
    ):
        assert rf"\"{key}\"" in action_json
    for forbidden in (
        "hardware_action_id",
        "frame_fnv1a_hex",
        "pixel_histogram_0_to_7",
        "maximum_arm_posts",
        "automatic_chaining",
    ):
        assert forbidden not in action_json

    for required in (
        r"\"action_count\":2",
        r"\"startup_refresh\":false",
        r"\"raw_frame_ingress\":false",
        r"\"runtime_lut_write\":false",
        r"\"electrical_parameter_write\":false",
        r"\"automatic_chaining\":false",
        r"\"dither\":true",
        r"\"spatial_mixing\":true",
        r"\"single_pixel_multi_pigment_claim\":false",
        r"\"physical_colour_claim\":false",
        r"\"retry\":false",
        r"\"recovery\":false",
    ):
        assert required in source
    for forbidden in (
        r"\"startup_refresh\":true",
        r"\"raw_frame_ingress\":true",
        r"\"runtime_lut_write\":true",
        r"\"electrical_parameter_write\":true",
        r"\"automatic_chaining\":true",
        r"\"retry\":true",
        r"\"recovery\":true",
    ):
        assert forbidden not in source


def test_external_anchor_is_the_completed_matrix_ordinal_three_white() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    anchor = _between(source, "String anchorContractJson()", "String identityJson()")
    for token in (
        ANCHOR_CAMPAIGN_ID,
        r"\"ordinal\":3",
        r"\"role\":\"OTP_WHITE_RECOVERY\"",
        ANCHOR_ACTION_ID,
        ANCHOR_RESULT_FILE_SHA256,
        ANCHOR_OBSERVATION_FILE_SHA256,
        ANCHOR_CLAIM_SHA256,
        r"\"validated_by_device\":false",
        r"\"required_host_gate_for_ordinal_1\":true",
    ):
        assert token in anchor
    for stale in (
        "MF1750_EC5_COLOR_LAB_LIVE_20260810_V1",
        "98881513368c332d",
        r"\"ordinal\":11",
    ):
        assert stale not in anchor


def test_cursor_and_bodyless_mutations_are_nonce_bound_and_consumed_first() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    assert _literal(source, "kArmIntent") == (
        "ARM_ONE_FIXED_FACTORY_OTP_DITHER_COLOR_ATLAS_ACTION"
    )
    assert _literal(source, "kExecuteIntent") == (
        "EXECUTE_ARMED_FACTORY_OTP_DITHER_COLOR_ATLAS_ACTION_ONCE"
    )
    for token in (
        "kPhaseReady = 0",
        "kPhaseArmed = 1",
        "kPhaseConsumed = 2",
        "kPhaseFault = 3",
        r"\"terminal_next_ordinal\":3",
    ):
        assert token in source

    refresh = _between(source, "bool refreshCursorEvidence", "bool persistCursor")
    for token in (
        "cursorStore.isKey(kNvsKey)",
        "cursorStore.getUShort(kNvsKey, 0)",
        "encodeCursor(0, 1)",
        "cursorRaw >> 8",
        "cursorRaw & 0xFFU",
    ):
        assert token in refresh
    assert re.findall(r"cursorStore\.(put[A-Za-z0-9_]*)\(", source) == ["putUShort"]
    for forbidden in (
        "cursorStore.clear(",
        "cursorStore.remove(",
        "nvs_flash_erase",
        "putUChar(",
        "putBytes(",
    ):
        assert forbidden not in source

    validation = _between(
        source, "const char *validateMutationContract", "String nvsContractJson"
    )
    for token in (
        "requestHasBodyOrArguments()",
        "kBuildHeader",
        "kTestHeader",
        "kCampaignHeader",
        "kActionHeader",
        "kOrdinalHeader",
        "kDescriptorHeader",
        "kBootNonceHeader",
        "kArmNonceHeader",
        "kIntentHeader",
        "arm_nonce_forbidden_during_arm",
        "arm_nonce_missing_or_stale",
    ):
        assert token in validation

    execute = _between(source, "void handleExecute()", "void installRoutes()")
    consumed = execute.index("persistCursor(kPhaseConsumed, action->ordinal)")
    assert consumed < execute.index("state = RuntimeState::Queued")
    assert consumed < execute.index("executePending = true")
    assert "driverCallCountForAction != 0" in execute


def test_boot_routes_and_worker_expose_no_automatic_or_raw_path() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    setup = _between(source, "void setup()", "void loop()")
    assert setup.index("epdValidateCompiledDitherColorAtlasFixtures()") < setup.index(
        "epdBegin()"
    )
    assert "epdDisplayCompiledDitherColorAtlas" not in setup
    assert "epdClear" not in setup
    assert "persistentPhase != kPhaseReady" in setup
    assert "non_ready_cursor_seen_at_boot" in setup

    routes = _between(source, "void installRoutes()", "void startWiFi()")
    assert routes.count("server.on(") == 6
    assert routes.count("HTTP_GET") == 4
    assert routes.count("server.on(kArmRoute, HTTP_POST") == 1
    assert routes.count("server.on(kExecuteRoute, HTTP_POST") == 1
    assert 'rejectMutation(404, "unknown_mutation_route"' in routes

    worker = _between(source, "void executePendingAction()", "}  // namespace")
    call = "epdDisplayCompiledDitherColorAtlas(action->driverRole)"
    assert worker.count(call) == 1
    assert source.count("epdDisplayCompiledDitherColorAtlas(") == 1
    assert worker.index("persistentPhase != kPhaseConsumed") < worker.index(call)
    assert worker.index("++driverCallCountForAction") < worker.index(call)
    assert "persistCursor(kPhaseFault, action->ordinal)" in worker
    assert "persistCursor(kPhaseReady, followingOrdinal)" in worker
    assert "followingOrdinal == kTerminalOrdinal" in worker

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
    ):
        assert forbidden not in source


def test_driver_layout_pairs_mask_phase_and_legal_codes_match_host() -> None:
    driver = DRIVER_PATH.read_text(encoding="utf-8")
    expected_scalars = {
        "DCA_GRID_ROWS": atlas.GRID_ROWS,
        "DCA_GRID_COLUMNS": atlas.GRID_COLUMNS,
        "DCA_GRID_X0_LOCAL": atlas.GRID_X0_LOCAL,
        "DCA_GRID_Y0": atlas.GRID_Y0,
        "DCA_CELL_WIDTH": atlas.CELL_WIDTH,
        "DCA_CELL_HEIGHT": atlas.CELL_HEIGHT,
        "DCA_COLUMN_GAP": atlas.COLUMN_GAP,
        "DCA_ROW_GAP": atlas.ROW_GAP,
    }
    for name, value in expected_scalars.items():
        assert re.search(rf"\b{name}\s*=\s*{value};", driver)

    pairs = ", ".join(
        f"{{{family.code_a}, {family.code_b}}}" for family in atlas.MIX_FAMILIES
    )
    assert pairs in driver
    quarters = ", ".join(str(column.a_quarters) for column in atlas.MIX_COLUMNS)
    assert f"DCA_A_QUARTERS[DCA_GRID_COLUMNS] = {{{quarters}}}" in driver
    assert "DCA_BAYER_2X2[2][2] = {{0, 2}, {3, 1}}" in driver

    legal = _between(driver, "bool dcaCodeLegal", "bool dcaValidateLayoutDesign")
    assert tuple(int(value) for value in re.findall(r"code == (\d+)", legal)) == (
        atlas.LEGAL_CODES
    )
    patch = _between(driver, "uint8_t dcaPatchCode", "void dcaFillPatch")
    assert "DCA_BAYER_2X2[localY & 1U][localX & 1U]" in patch
    fill = _between(driver, "void dcaFillPatch", "bool dcaBuildFrame")
    assert "dcaPatchCode(row, column, localX, localY)" in fill
    assert "dcaPatchCode(row, column, localX + 1, localY)" in fill
    assert "x0 / 2" in fill

    builder = _between(driver, "bool dcaBuildFrame", "bool dcaDigestMatchesHex")
    assert "controller < DCA_CONTROLLER_COUNT" in builder
    assert "controller == 0 ? 0 : EPD_CONTROLLER_WIDTH" in builder
    assert "dcaFillPatch(frame, x0, y0, row, column)" in builder
    assert "dcaCodeLegal(high)" in builder
    assert "dcaCodeLegal(low)" in builder


def test_driver_role_identities_fnvs_histograms_and_dual_dtm_are_exact() -> None:
    driver = DRIVER_PATH.read_text(encoding="utf-8")
    arrays = {
        contract.ROLE_ATLAS: (
            "DCA_ATLAS_FRAME_SHA256",
            "DCA_ATLAS_CS1_DTM_SHA256",
            "DCA_ATLAS_CS2_DTM_SHA256",
        ),
        contract.ROLE_WHITE: (
            "DCA_WHITE_FRAME_SHA256",
            "DCA_WHITE_DTM_SHA256",
            "DCA_WHITE_DTM_SHA256",
        ),
    }
    for role, names in arrays.items():
        actual = tuple(_char_array_literal(driver, name) for name in names)
        identity = _identity(role)
        expected = tuple(
            identity[field]["sha256"] for field in ("frame", "cs1_dtm", "cs2_dtm")
        )
        assert actual == expected
        for field in ("frame", "cs1_dtm", "cs2_dtm"):
            assert f"0x{identity[field]['fnv1a_u32']:08X}UL" in driver
        assert _histogram_literal(role) in driver

    atlas_identity = _identity(contract.ROLE_ATLAS)
    assert atlas_identity["cs1_dtm"] == atlas_identity["cs2_dtm"]
    validator = _between(driver, "bool dcaValidateRole", "}  // namespace")
    for token in (
        "std::memcmp(histogram, wanted.histogram",
        "fnv1a(frame, EPD_FRAME_BYTES)",
        "mbedtls_sha256_ret(frame, EPD_FRAME_BYTES",
        "dcaComputeDtmIdentity(frame, false",
        "dcaComputeDtmIdentity(frame, true",
        "wanted.frameSha256",
        "wanted.cs1DtmSha256",
        "wanted.cs2DtmSha256",
    ):
        assert token in validator


def test_display_deep_validates_before_panel_io_and_refreshes_both_once() -> None:
    driver = DRIVER_PATH.read_text(encoding="utf-8")
    display = driver[driver.index("bool epdDisplayCompiledDitherColorAtlas") :]
    assert display.index("dcaValidateRole(role, frame, &validation)") < display.index(
        "epdPrepareCascade(EPD_SPI_DEFAULT_HZ)"
    )
    assert display.index("epdPrepareCascade(EPD_SPI_DEFAULT_HZ)") < display.index(
        "epdStreamPackedFrameController(frame, false)"
    )
    assert display.count("epdStreamPackedFrameController(frame, false)") == 1
    assert display.count("epdStreamPackedFrameController(frame, true)") == 1
    assert "diagnosticReport.cs1DtmFnv1a != wanted.cs1DtmFnv1a" in display
    assert "diagnosticReport.cs2DtmFnv1a != wanted.cs2DtmFnv1a" in display
    assert "setActiveControllers(true, true)" in display
    assert display.count("epdSecondSettingAndRefresh()") == 1

    header = HEADER_PATH.read_text(encoding="utf-8")
    api = _between(
        header,
        "#if MF1750_ENABLE_DITHER_COLOR_ATLAS\n"
        "// Factory-OTP-only spatial dither fixture.",
        "#endif",
    )
    assert "enum class EpdDitherColorAtlasRole" in api
    assert "Atlas = 0" in api
    assert "White = 1" in api
    assert "bool epdValidateCompiledDitherColorAtlasFixtures();" in api
    signature = re.search(r"bool epdDisplayCompiledDitherColorAtlas\(([^)]*)\);", api)
    assert signature is not None
    assert signature.group(1) == "EpdDitherColorAtlasRole role"


def test_fixture_contains_no_raw_lut_vcom_electrical_partial_or_retry_api() -> None:
    driver = DRIVER_PATH.read_text(encoding="utf-8")
    main = MAIN_PATH.read_text(encoding="utf-8")
    code = driver + "\n" + main
    forbidden_calls_or_routes = (
        r"\bepdDisplayFrame\s*\(",
        r"\bepdDisplayFrameAtFrequency\s*\(",
        r"\bepdClear(?:White|Black)\s*\(",
        r"\bepdInitResolution\s*\(",
        r"\bepdWrite(?:Command|Data)\s*\(",
        r"\bloadWF\s*\(",
        r"\bsetVcom\s*\(",
        r"\bsetVoltage\s*\(",
        r"\bpartial(?:Update|Window)\s*\(",
        r"\bserver\.upload\b",
    )
    for pattern in forbidden_calls_or_routes:
        assert re.search(pattern, code, flags=re.IGNORECASE) is None, pattern

    for forbidden_literal in (
        "VCOM",
        "LUT1_DATA",
        "runtime_waveform",
        "partial_window",
        "automaticRetry",
        "automaticRecovery",
        "autoChain",
    ):
        assert forbidden_literal not in code


def test_platformio_source_filter_macro_isolation_and_no_upload_binding() -> None:
    config = PLATFORMIO_PATH.read_text(encoding="utf-8")
    assert "[env:esp32-s3-devkitc-1-ec5-dither-color-atlas]" in config
    source_filter = _between(config, "build_src_filter =", "board_build.filesystem")
    assert "-<*>" in source_filter
    assert re.findall(r"^\s+\+<([^>]+)>", source_filter, flags=re.MULTILINE) == [
        "epd_driver.cpp",
        "ec5_dither_color_atlas_main.cpp",
    ]
    enabled_fixtures = re.findall(r"-D\s+(MF1750_ENABLE_[A-Z0-9_]+)=1", config)
    assert enabled_fixtures == ["MF1750_ENABLE_DITHER_COLOR_ATLAS"]
    assert "EPD_ENABLE_TEST_PATTERN=0" in config
    for forbidden in (
        "upload_port",
        "monitor_port",
        "upload_flags",
        "extra_scripts",
        "target = upload",
    ):
        assert forbidden not in config

    header = HEADER_PATH.read_text(encoding="utf-8")
    assert "#define MF1750_ENABLE_DITHER_COLOR_ATLAS 0" in header
    exclusion = _between(
        header,
        "#if MF1750_ENABLE_DITHER_COLOR_ATLAS &&",
        '#error "Factory-OTP dither color atlas is isolated from other fixtures"',
    )
    for other in (
        "MF1750_ENABLE_UNKNOWN_PROBE",
        "MF1750_ENABLE_SIXSTATE_PROBE",
        "MF1750_ENABLE_U04_U05_COMPARE",
        "MF1750_ENABLE_EIGHTCODE_ATLAS",
        "MF1750_ENABLE_COLOR_LAB",
        "MF1750_ENABLE_OTP_TRANSITION_MATRIX",
    ):
        assert other in exclusion

    driver_cpp = DRIVER_CPP_PATH.read_text(encoding="utf-8")
    assert (
        "#if MF1750_ENABLE_DITHER_COLOR_ATLAS\n"
        '#include "ec5_dither_color_atlas_driver.inc"\n'
        "#endif"
    ) in driver_cpp
    main = MAIN_PATH.read_text(encoding="utf-8")
    assert "#if MF1750_ENABLE_DITHER_COLOR_ATLAS != 1" in main
    assert "#if EPD_ENABLE_TEST_PATTERN != 0" in main
