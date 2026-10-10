from __future__ import annotations

from pathlib import Path
import re

from tools import mf1750_ec5_color_lab_contract as contract


ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "src/ec5_color_lab_main.cpp"
DRIVER_PATH = ROOT / "src/ec5_color_lab_driver.inc"
ATLAS_DRIVER_PATH = ROOT / "src/ec5_eightcode_atlas_driver.inc"
HEADER_PATH = ROOT / "src/epd_driver.h"
DRIVER_CPP_PATH = ROOT / "src/epd_driver.cpp"
PLATFORMIO_PATH = ROOT / "platformio.color_lab.ini"


def _literal(source: str, name: str) -> str:
    match = re.search(
        rf'static constexpr const char \*{re.escape(name)}\s*=\s*"([^"]+)";',
        source,
    )
    assert match is not None, name
    return match.group(1)


def _between(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    finish = source.index(end, begin)
    return source[begin:finish]


def _byte_array(source: str, name: str) -> bytes:
    match = re.search(
        rf"static const uint8_t {re.escape(name)}\[32\]\s*=\s*\{{(.*?)\}};",
        source,
        flags=re.DOTALL,
    )
    assert match is not None, name
    payload = bytes(
        int(value, 16) for value in re.findall(r"0x([0-9A-Fa-f]{2})", match.group(1))
    )
    assert len(payload) == 32
    return payload


def test_main_identity_literals_match_the_frozen_offline_contract() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    manifest = contract.campaign_manifest()
    expected = {
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
        "TECHNICAL_EXPERIMENT_NO_PHYSICAL_COLOUR_CLAIM"
    )


def test_all_frozen_descriptors_and_static_action_ids_are_compiled_in_order() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    table = _between(
        source,
        "static constexpr ActionDescriptor kActions[] = {",
        "#undef PRIMER_ACTION",
    )
    descriptor_positions = []
    action_positions = []
    for descriptor in contract.DESCRIPTORS:
        descriptor_id = descriptor["descriptor_id"]
        action_id = descriptor["hardware_action_id"]
        assert descriptor_id in table
        assert action_id in table
        descriptor_positions.append(table.index(descriptor_id))
        action_positions.append(table.index(action_id))
        assert descriptor["frame_sha256"] in source
        assert descriptor["cs1_dtm_sha256"] in source
        assert descriptor["cs2_dtm_sha256"] in source
    assert descriptor_positions == sorted(descriptor_positions)
    assert action_positions == sorted(action_positions)
    assert "kActionCount = 23" in source
    assert "kTerminalOrdinal = kActionCount + 1" in source
    assert "action table must contain exactly 23 actions" in source
    assert "303bb39e" not in source


def test_cursor_is_one_uint16_key_with_ready_armed_consumed_fault_encoding() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    assert 'kNvsNamespace = "mf1750_ec5cl"' in source
    assert 'kNvsKey = "cursor"' in source
    assert "kPhaseReady = 0" in source
    assert "kPhaseArmed = 1" in source
    assert "kPhaseConsumed = 2" in source
    assert "kPhaseFault = 3" in source
    encode = _between(source, "uint16_t encodeCursor", "bool cursorFieldsValid")
    assert "static_cast<uint16_t>(phase) << 8" in encode
    assert "| ordinal" in encode
    refresh = _between(source, "bool refreshCursorEvidence", "bool persistCursor")
    assert "cursorStore.isKey(kNvsKey)" in refresh
    assert "cursorStore.getUShort(kNvsKey, 0)" in refresh
    assert "encodeCursor(0, 1)" in refresh
    assert "cursorRaw >> 8" in refresh
    assert "cursorRaw & 0xFFU" in refresh
    writes = re.findall(r"cursorStore\.(put[A-Za-z0-9_]*)\(", source)
    assert writes == ["putUShort"]
    for forbidden in (
        "cursorStore.clear(",
        "cursorStore.remove(",
        "nvs_flash_erase",
        "putUChar(",
    ):
        assert forbidden not in source


def test_arm_and_execute_persist_before_state_transition_and_queue() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    arm = _between(source, "void handleArm()", "void handleExecute()")
    assert arm.index("persistCursor(kPhaseArmed, action->ordinal)") < arm.index(
        "state = RuntimeState::Armed"
    )
    execute = _between(source, "void handleExecute()", "void installRoutes()")
    consumed = execute.index("persistCursor(kPhaseConsumed, action->ordinal)")
    assert consumed < execute.index("state = RuntimeState::Queued")
    assert consumed < execute.index("executePending = true")
    assert "driverCallCountForAction != 0" in execute
    assert "execute_duplicate_stale_or_not_armed" in execute


def test_one_explicit_action_makes_exactly_one_driver_call_and_advances_ready() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    worker = _between(source, "void executePendingAction()", "}  // namespace")
    assert worker.count("epdDisplayCompiledColorLab(action->driverRole)") == 1
    assert worker.index("persistentPhase != kPhaseConsumed") < worker.index(
        "epdDisplayCompiledColorLab(action->driverRole)"
    )
    assert worker.index("++driverCallCountForAction") < worker.index(
        "epdDisplayCompiledColorLab(action->driverRole)"
    )
    assert "persistCursor(kPhaseFault, action->ordinal)" in worker
    assert "persistCursor(kPhaseReady, followingOrdinal)" in worker
    assert "followingOrdinal == kTerminalOrdinal" in worker
    assert r'"driver_call_count_for_action\":1' in worker
    assert source.count("epdDisplayCompiledColorLab(") == 1


def test_boot_deep_validates_without_refresh_and_interrupted_phases_fault_lock() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    setup = _between(source, "void setup()", "void loop()")
    assert setup.index("epdValidateCompiledColorLabFixtures()") < setup.index(
        "epdBegin()"
    )
    assert "epdDisplayCompiledColorLab" not in setup
    assert "epdClear" not in setup
    assert "cursorStore.begin(kNvsNamespace, false /* readOnly */)" in setup
    assert "persistentPhase != kPhaseReady" in setup
    assert "non_ready_cursor_seen_at_boot" in setup
    assert "RuntimeState::FaultLocked" in setup
    assert "automatic chaining" in source.lower()
    assert "No startup refresh/raw ingress/dither/auto-chain/retry/recovery" in source


def test_every_mutation_binds_exact_headers_and_any_rejection_fault_locks() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    for header in (
        "X-EC5-Build-Tag",
        "X-EC5-Test-Id",
        "X-EC5-Campaign-Id",
        "X-EC5-Action-Id",
        "X-EC5-Ordinal",
        "X-EC5-Descriptor-Id",
        "X-EC5-Boot-Nonce",
        "X-EC5-Arm-Nonce",
        "X-EC5-Intent",
    ):
        assert header in source
    validation = _between(
        source, "const char *validateMutationContract", "String nvsContractJson"
    )
    for token in (
        "kBuildHeader",
        "kTestHeader",
        "kCampaignHeader",
        "kActionHeader",
        "kOrdinalHeader",
        "kDescriptorHeader",
        "kBootNonceHeader",
        "kArmNonceHeader",
        "kIntentHeader",
    ):
        assert token in validation
    rejection = _between(source, "void rejectMutation", "void handleArm()")
    assert "enterFault(error, action)" in rejection
    routes = _between(source, "void installRoutes()", "void startWiFi()")
    assert 'rejectMutation(404, "unknown_mutation_route"' in routes


def test_device_payloads_match_runner_active_action_schema() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    status = _between(source, "String statusJson()", "String driverEvidenceJson")
    assert "action && persistentPhase != kPhaseReady" in status
    assert '? actionJson(*action)' in status
    assert ': String("null")' in status

    arm = _between(source, "void handleArm()", "void handleExecute()")
    execute = _between(source, "void handleExecute()", "void installRoutes()")
    for payload in (arm, execute):
        assert r'\",\"role\":\"" + action->role' in payload
        assert r'\",\"round\":" + String(action->round)' in payload
        assert r'",\"branch\":\"" + action->branch' in payload


def test_only_fixed_color_lab_routes_exist_with_no_ingress_retry_or_recovery() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")
    for route in (
        "/api/ec5/color-lab/version",
        "/api/ec5/color-lab/manifest",
        "/api/ec5/color-lab/status",
        "/api/ec5/color-lab/report",
        "/api/ec5/color-lab/arm",
        "/api/ec5/color-lab/execute",
    ):
        assert route in source
    for forbidden in (
        '"/api/frame"',
        '"/api/ec5/reset"',
        '"/api/ec5/retry"',
        '"/api/ec5/recovery"',
        "server.upload",
        "HTTP_PUT",
    ):
        assert forbidden not in source
    for token in (
        r'"automatic_chaining\":false',
        r'"startup_refresh\":false',
        r'"raw_frame_ingress\":false',
        r'"dither\":false',
        r'"retry\":false',
        r'"recovery\":false',
    ):
        assert token in source


def test_driver_runtime_sha_arrays_match_every_composed_role() -> None:
    owned = DRIVER_PATH.read_text(encoding="utf-8")
    atlas = ATLAS_DRIVER_PATH.read_text(encoding="utf-8")
    expected = contract.ROLE_IDENTITIES
    arrays = {
        (contract.ROLE_ATLAS, "frame"): (atlas, "EC8_ATLAS_FRAME_SHA256"),
        (contract.ROLE_ATLAS, "cs1_dtm"): (
            atlas,
            "EC8_ATLAS_CS1_DTM_SHA256",
        ),
        (contract.ROLE_ATLAS, "cs2_dtm"): (
            atlas,
            "EC8_ATLAS_CS2_DTM_SHA256",
        ),
        (contract.ROLE_WHITE, "frame"): (atlas, "EC8_WHITE_FRAME_SHA256"),
        (contract.ROLE_WHITE, "cs1_dtm"): (atlas, "EC8_WHITE_DTM_SHA256"),
        (contract.ROLE_U07_ISOLATED, "frame"): (
            owned,
            "CL_U07_ISOLATED_FRAME_SHA256",
        ),
        (contract.ROLE_U07_ISOLATED, "cs1_dtm"): (
            owned,
            "CL_U07_ISOLATED_DTM_SHA256",
        ),
        (contract.ROLE_U04_PRIMER, "frame"): (
            owned,
            "CL_SIXSTATE_PRIMER_FRAME_SHA256",
        ),
        (contract.ROLE_U04_PRIMER, "cs1_dtm"): (
            owned,
            "CL_SIXSTATE_PRIMER_DTM_SHA256",
        ),
        (contract.ROLE_U04_TARGET, "frame"): (
            owned,
            "CL_U04_TARGET_FRAME_SHA256",
        ),
        (contract.ROLE_U04_TARGET, "cs1_dtm"): (
            owned,
            "CL_U04_TARGET_DTM_SHA256",
        ),
        (contract.ROLE_U07_TARGET, "frame"): (
            owned,
            "CL_U07_TARGET_FRAME_SHA256",
        ),
        (contract.ROLE_U07_TARGET, "cs1_dtm"): (
            owned,
            "CL_U07_TARGET_DTM_SHA256",
        ),
    }
    for (role, field), (source, name) in arrays.items():
        assert _byte_array(source, name).hex() == expected[role][field]["sha256"]


def test_driver_deep_validates_all_roles_before_any_panel_io() -> None:
    owned = DRIVER_PATH.read_text(encoding="utf-8")
    validator = _between(owned, "bool clValidateOwnedRole", "bool clMapPublicRole")
    for token in (
        "fnv1a(frame, EPD_FRAME_BYTES)",
        "mbedtls_sha256_ret(frame, EPD_FRAME_BYTES",
        "ec8ComputeDtmIdentity(frame, false",
        "ec8ComputeDtmIdentity(frame, true",
        "wanted.frameSha256",
        "wanted.dtmSha256",
    ):
        assert token in validator
    public_guard = _between(
        owned,
        "bool epdValidateCompiledColorLabFixtures()",
        "bool epdDisplayCompiledColorLab",
    )
    assert "epdValidateCompiledEightCodeAtlasFixtures()" in public_guard
    assert "index < 4" in public_guard
    for forbidden in (
        "epdPrepareCascade",
        "epdSecondSettingAndRefresh",
        "digitalWrite",
    ):
        assert forbidden not in public_guard
    display = owned[owned.index("bool epdDisplayCompiledColorLab") :]
    assert display.index("clValidateOwnedRole") < display.index("epdPrepareCascade")
    assert "EpdColorLabRole::White" in display
    assert "EpdColorLabRole::Atlas" in display


def test_dedicated_platformio_environment_has_no_port_or_upload_target() -> None:
    source = PLATFORMIO_PATH.read_text(encoding="utf-8")
    assert "[env:esp32-s3-devkitc-1-ec5-color-lab]" in source
    for token in (
        "+<epd_driver.cpp>",
        "+<ec5_color_lab_main.cpp>",
        "-<main.cpp>",
        "-<n7_main.cpp>",
        "-<ec5_unknown_probe_main.cpp>",
        "-<ec5_sixstate_main.cpp>",
        "-<ec5_u04_u05_compare_main.cpp>",
        "-<ec5_u07t_main.cpp>",
        "EPD_ENABLE_TEST_PATTERN=0",
        "MF1750_ENABLE_EIGHTCODE_ATLAS=1",
        "MF1750_ENABLE_COLOR_LAB=1",
    ):
        assert token in source
    assert "upload_port" not in source
    assert "monitor_port" not in source
    assert "target = upload" not in source


def test_shared_driver_guards_keep_color_lab_isolated() -> None:
    header = HEADER_PATH.read_text(encoding="utf-8")
    driver = DRIVER_CPP_PATH.read_text(encoding="utf-8")
    assert "MF1750_ENABLE_COLOR_LAB && !MF1750_ENABLE_EIGHTCODE_ATLAS" in header
    assert "enum class EpdColorLabRole" in header
    assert "bool epdValidateCompiledColorLabFixtures();" in header
    assert "bool epdDisplayCompiledColorLab(EpdColorLabRole role);" in header
    assert '#include "ec5_eightcode_atlas_driver.inc"' in driver
    assert '#include "ec5_color_lab_driver.inc"' in driver
