from __future__ import annotations

from pathlib import Path
import re

from tools import mf1750_ec5_otp_transition_matrix_contract as contract


ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "src/ec5_otp_transition_matrix_main.cpp"
DRIVER_PATH = ROOT / "src/ec5_otp_transition_matrix_driver.inc"
HEADER_PATH = ROOT / "src/epd_driver.h"
DRIVER_CPP_PATH = ROOT / "src/epd_driver.cpp"
PLATFORMIO_PATH = ROOT / "platformio.otp_transition_matrix.ini"


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


def test_main_identity_literals_match_the_frozen_host_contract() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    manifest = contract.campaign_manifest()
    expected = {
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
    assert _literal(source, "kClassification") == (
        "FACTORY_OTP_8X8_TRANSITION_EXPERIMENT_NO_RUNTIME_LUT"
    )


def test_three_actions_match_frozen_descriptors_in_exact_order() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    table = _between(
        source,
        "static constexpr ActionDescriptor kActions[] = {",
        "static_assert(sizeof(kActions)",
    )
    descriptor_positions: list[int] = []
    action_positions: list[int] = []
    for descriptor in contract.DESCRIPTORS:
        descriptor_id = descriptor["descriptor_id"]
        action_id = descriptor["hardware_action_id"]
        descriptor_positions.append(table.index(descriptor_id))
        action_positions.append(table.index(action_id))
        assert descriptor["role"] in table
        assert descriptor["branch"] in table
        assert descriptor["frame_sha256"] in source
        assert descriptor["cs1_dtm_sha256"] in source
        assert descriptor["cs2_dtm_sha256"] in source
        prior = descriptor["action_identity_preimage"]["prior_static_action_id"]
        if prior is None:
            assert "nullptr" in table[: table.index(action_id) + len(action_id) + 20]
        else:
            assert prior in table
    assert descriptor_positions == sorted(descriptor_positions)
    assert action_positions == sorted(action_positions)
    assert "kActionCount = 3" in source
    assert "kTerminalOrdinal = kActionCount + 1" in source
    assert "must contain exactly three actions" in source


def test_device_action_json_is_the_exact_mature_runner_shape() -> None:
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
        assert rf'\"{key}\"' in action_json
    for forbidden in (
        "hardware_action_id",
        "frame_fnv1a_hex",
        "pixel_histogram_0_to_7",
        "maximum_arm_posts",
        "automatic_chaining",
    ):
        assert forbidden not in action_json


def test_cursor_is_one_uint16_key_with_four_fail_closed_phases() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    assert 'kNvsNamespace = "mf1750_otpm8"' in source
    assert 'kNvsKey = "cursor_v1"' in source
    for token in (
        "kPhaseReady = 0",
        "kPhaseArmed = 1",
        "kPhaseConsumed = 2",
        "kPhaseFault = 3",
    ):
        assert token in source
    encode = _between(source, "uint16_t encodeCursor", "bool cursorFieldsValid")
    assert "static_cast<uint16_t>(phase) << 8" in encode
    assert "| ordinal" in encode
    refresh = _between(source, "bool refreshCursorEvidence", "bool persistCursor")
    assert "cursorStore.isKey(kNvsKey)" in refresh
    assert "cursorStore.getUShort(kNvsKey, 0)" in refresh
    assert "encodeCursor(0, 1)" in refresh
    assert "cursorRaw >> 8" in refresh
    assert "cursorRaw & 0xFFU" in refresh
    assert re.findall(r"cursorStore\.(put[A-Za-z0-9_]*)\(", source) == ["putUShort"]
    for forbidden in (
        "cursorStore.clear(",
        "cursorStore.remove(",
        "nvs_flash_erase",
        "putUChar(",
        "putBytes(",
    ):
        assert forbidden not in source


def test_arm_and_execute_are_bodyless_nonce_bound_and_consumed_first() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    assert _literal(source, "kArmIntent") == (
        "ARM_ONE_FIXED_FACTORY_OTP_TRANSITION_MATRIX_ACTION"
    )
    assert _literal(source, "kExecuteIntent") == (
        "EXECUTE_ARMED_FACTORY_OTP_TRANSITION_MATRIX_ACTION_ONCE"
    )
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
    arm = _between(source, "void handleArm()", "void handleExecute()")
    assert arm.index("persistCursor(kPhaseArmed, action->ordinal)") < arm.index(
        "state = RuntimeState::Armed"
    )
    execute = _between(source, "void handleExecute()", "void installRoutes()")
    consumed = execute.index("persistCursor(kPhaseConsumed, action->ordinal)")
    assert consumed < execute.index("state = RuntimeState::Queued")
    assert consumed < execute.index("executePending = true")
    assert "driverCallCountForAction != 0" in execute


def test_each_action_has_one_and_only_one_compiled_driver_call() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    worker = _between(source, "void executePendingAction()", "}  // namespace")
    call = "epdDisplayCompiledOtpTransitionMatrix(action->driverRole)"
    assert worker.count(call) == 1
    assert worker.index("persistentPhase != kPhaseConsumed") < worker.index(call)
    assert worker.index("++driverCallCountForAction") < worker.index(call)
    assert "persistCursor(kPhaseFault, action->ordinal)" in worker
    assert "persistCursor(kPhaseReady, followingOrdinal)" in worker
    assert "followingOrdinal == kTerminalOrdinal" in worker
    assert source.count("epdDisplayCompiledOtpTransitionMatrix(") == 1
    for forbidden in (
        "epdDisplayFrame(",
        "epdDisplayFrameAtFrequency(",
        "epdClearWhite(",
        "epdClearBlack(",
    ):
        assert forbidden not in source


def test_boot_deep_validates_but_never_refreshes_or_resumes() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    setup = _between(source, "void setup()", "void loop()")
    assert setup.index(
        "epdValidateCompiledOtpTransitionMatrixFixtures()"
    ) < setup.index("epdBegin()")
    assert "epdDisplayCompiledOtpTransitionMatrix" not in setup
    assert "epdClear" not in setup
    assert "cursorStore.begin(kNvsNamespace, false /* readOnly */)" in setup
    assert "persistentPhase != kPhaseReady" in setup
    assert "non_ready_cursor_seen_at_boot" in setup
    assert "enterFault(" in setup


def test_only_six_fixed_routes_exist_and_rejections_fault_lock() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    for endpoint in (
        "version",
        "manifest",
        "status",
        "report",
        "arm",
        "execute",
    ):
        assert f'/api/ec5/otp-transition-matrix/{endpoint}' in source
    routes = _between(source, "void installRoutes()", "void startWiFi()")
    assert routes.count("server.on(") == 6
    assert 'rejectMutation(404, "unknown_mutation_route"' in routes
    rejection = _between(source, "void rejectMutation", "void handleArm()")
    assert "enterFault(error, action)" in rejection
    for forbidden in (
        '"/api/frame"',
        '"/api/ec5/reset"',
        '"/api/ec5/retry"',
        '"/api/ec5/recovery"',
        "server.upload",
        "HTTP_PUT",
    ):
        assert forbidden not in source


def test_driver_layout_and_deep_identities_match_the_host_fixture() -> None:
    driver = DRIVER_PATH.read_text(encoding="utf-8")
    assert "OTM_CELL_WIDTH = 56" in driver
    assert "OTM_CELL_HEIGHT = 64" in driver
    assert "OTM_GRID_X0 = 32" in driver
    assert "OTM_GRID_Y0 = 44" in driver
    arrays = {
        contract.ROLE_PRIMER: (
            "OTM_PRIMER_FRAME_SHA256",
            "OTM_PRIMER_CS1_DTM_SHA256",
            "OTM_PRIMER_CS2_DTM_SHA256",
        ),
        contract.ROLE_TARGET: (
            "OTM_TARGET_FRAME_SHA256",
            "OTM_TARGET_CS1_DTM_SHA256",
            "OTM_TARGET_CS2_DTM_SHA256",
        ),
        contract.ROLE_WHITE: (
            "OTM_WHITE_FRAME_SHA256",
            "OTM_WHITE_DTM_SHA256",
            "OTM_WHITE_DTM_SHA256",
        ),
    }
    for role, names in arrays.items():
        actual = tuple(_char_array_literal(driver, name) for name in names)
        expected = (
            contract.ROLE_IDENTITIES[role]["frame"]["sha256"],
            contract.ROLE_IDENTITIES[role]["cs1_dtm"]["sha256"],
            contract.ROLE_IDENTITIES[role]["cs2_dtm"]["sha256"],
        )
        assert actual == expected
        for field in ("frame", "cs1_dtm", "cs2_dtm"):
            fnv = contract.ROLE_IDENTITIES[role][field]["fnv1a_u32"]
            assert f"0x{fnv:08X}UL" in driver
    validator = _between(driver, "bool otmValidateRole", "}  // namespace")
    for token in (
        "fnv1a(frame, EPD_FRAME_BYTES)",
        "mbedtls_sha256_ret(frame, EPD_FRAME_BYTES",
        "otmComputeDtmIdentity(frame, false",
        "otmComputeDtmIdentity(frame, true",
        "wanted.frameSha256",
        "wanted.cs1DtmSha256",
        "wanted.cs2DtmSha256",
    ):
        assert token in validator
    display = driver[driver.index("bool epdDisplayCompiledOtpTransitionMatrix") :]
    assert display.index("otmValidateRole") < display.index("epdPrepareCascade")
    assert "setActiveControllers(true, true)" in display
    assert display.count("epdSecondSettingAndRefresh()") == 1


def test_platformio_build_is_exactly_isolated_and_has_no_upload_binding() -> None:
    config = PLATFORMIO_PATH.read_text(encoding="utf-8")
    for token in (
        "[env:esp32-s3-devkitc-1-ec5-otp-transition-matrix]",
        "-<*>",
        "+<epd_driver.cpp>",
        "+<ec5_otp_transition_matrix_main.cpp>",
        "EPD_ENABLE_TEST_PATTERN=0",
        "MF1750_ENABLE_OTP_TRANSITION_MATRIX=1",
    ):
        assert token in config
    for forbidden in (
        "upload_port",
        "monitor_port",
        "upload_flags",
        "extra_scripts",
        "target = upload",
    ):
        assert forbidden not in config

    header = HEADER_PATH.read_text(encoding="utf-8")
    driver_cpp = DRIVER_CPP_PATH.read_text(encoding="utf-8")
    assert "enum class EpdOtpTransitionMatrixRole" in header
    assert "bool epdValidateCompiledOtpTransitionMatrixFixtures();" in header
    assert "epdDisplayCompiledOtpTransitionMatrix(" in header
    assert '#include "ec5_otp_transition_matrix_driver.inc"' in driver_cpp

