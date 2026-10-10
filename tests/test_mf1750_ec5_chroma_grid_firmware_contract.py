from __future__ import annotations

from pathlib import Path
import re

from tools.mf1750_ec5_chroma_grid import build_manifest


ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "src/ec5_chroma_grid_main.cpp"
DRIVER_PATH = ROOT / "src/ec5_chroma_grid_driver.inc"
HEADER_PATH = ROOT / "src/ec5_chroma_grid_epd_driver.h"
WRAPPER_PATH = ROOT / "src/ec5_chroma_grid_epd_driver.cpp"
PLATFORMIO_PATH = ROOT / "platformio.chroma_grid.ini"
RUNNER_PATH = ROOT / "tools/mf1750_ec5_chroma_grid_once.py"


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


def test_device_and_offline_manifest_have_one_exact_identity_chain() -> None:
    source = MAIN_PATH.read_text("utf-8")
    manifest, _ = build_manifest()
    assert _literal(source, "kClassification") == manifest["classification"]
    assert _literal(source, "kCampaignId") == manifest["campaign_id"]
    assert _literal(source, "kContractId") == manifest["integrity"][
        "canonical_sha256"
    ]
    table = _between(
        source,
        "static constexpr ActionDescriptor kActions[] = {",
        "static_assert(sizeof(kActions)",
    )
    positions: list[int] = []
    role_names = {
        "white": ("CHROMA_WHITE_BASELINE", "CHROMA_WHITE_RECOVERY"),
        "source": ("CHROMA_SOURCE_GRID",),
        "mid": ("CHROMA_MID_GRID",),
        "target": ("CHROMA_TARGET_GRID",),
    }
    for action in manifest["actions"]:
        positions.append(table.index(action["action_id"]))
        assert action["descriptor_id"] in table
        assert action["frame_sha256"] in source
        assert action["cs1_dtm_sha256"] in source
        assert action["cs2_dtm_sha256"] in source
    assert positions == sorted(positions)
    for names in role_names.values():
        for name in names:
            assert name in table
    assert "kActionCount = 5" in source
    assert "must contain exactly five actions" in source
    assert '"action_count\\\":3' not in source
    assert '"terminal_next_ordinal\\\":4' not in source
    assert "String(kActionCount)" in source
    assert "String(kTerminalOrdinal)" in source
    assert "external_clean_white_anchor" not in source
    assert "baselineContractJson" in source
    action_json = _between(source, "String actionJson", "String versionJson")
    assert '\\"transport_code_histogram\\"' in action_json
    assert "histogramJson(action)" in action_json
    for token in (
        "sequences_per_controller\\\":64",
        "roi_count\\\":128",
        "grid_x0_local\\\":34",
        "grid_x1_local_exclusive\\\":478",
        "grid_y0\\\":30",
        "grid_y1_exclusive\\\":570",
        "cell_width\\\":52",
        "gap_x\\\":4",
        "gap_y\\\":4",
    ):
        assert token in source


def test_compiled_builder_is_fixed_full_screen_and_fail_closed() -> None:
    driver = DRIVER_PATH.read_text("utf-8")
    manifest, _ = build_manifest()
    for token in (
        "CG_CELL_WIDTH = 52",
        "CG_CELL_HEIGHT = 64",
        "CG_CELL_GAP_X = 4",
        "CG_CELL_GAP_Y = 4",
        "CG_GRID_X0 = 34",
        "CG_GRID_Y0 = 30",
        "CG_SOURCE_ORDER_CS1",
        "CG_SOURCE_ORDER_CS2",
        "CG_MID_CODES",
        "CG_TARGET_CODES",
        "coverage[sourceOrder[row]][midIndex][targetIndex]",
        "std::memset(frame, 0x11, EPD_FRAME_BYTES)",
    ):
        assert token in driver
    for frame in manifest["frames"].values():
        assert frame["sha256"] in driver
        for controller in frame["controllers"]:
            assert controller["sha256"] in driver
            assert controller["fnv1a"] + "UL" in driver
    display = driver[driver.index("bool epdDisplayCompiledChromaGrid") :]
    assert display.index("cgValidateRole") < display.index("epdPrepareCascade")
    assert display.count("epdSecondSettingAndRefresh()") == 1
    assert "setActiveControllers(true, true)" in display


def test_each_ordinal_is_consumed_before_one_driver_call_and_never_autochains() -> None:
    source = MAIN_PATH.read_text("utf-8")
    worker = _between(source, "void executePendingAction()", "}  // namespace")
    call = "epdDisplayCompiledChromaGrid(action->driverRole)"
    assert source.count(call) == 1
    assert worker.index("persistentPhase != kPhaseConsumed") < worker.index(call)
    assert worker.index("++driverCallCountForAction") < worker.index(call)
    assert "persistCursor(kPhaseReady, followingOrdinal)" in worker
    setup = _between(source, "void setup()", "void loop()")
    assert "epdValidateCompiledChromaGridFixtures()" in setup
    assert "epdDisplayCompiledChromaGrid" not in setup
    assert "epdClear" not in setup
    assert "non_ready_cursor_seen_at_boot" in setup


def test_only_fixed_api_and_isolated_no_upload_build_exist() -> None:
    source = MAIN_PATH.read_text("utf-8")
    routes = _between(source, "void installRoutes()", "void startWiFi()")
    assert routes.count("server.on(") == 6
    for endpoint in ("version", "manifest", "status", "report", "arm", "execute"):
        assert f'/api/ec5/chroma-grid/{endpoint}' in source
    for forbidden in (
        '"/api/frame"',
        '"/api/ec5/reset"',
        '"/api/ec5/retry"',
        '"/api/ec5/recovery"',
        "server.upload",
        "HTTP_PUT",
        "cursorStore.clear(",
        "cursorStore.remove(",
        "nvs_flash_erase",
    ):
        assert forbidden not in source

    config = PLATFORMIO_PATH.read_text("utf-8")
    for token in (
        "[env:esp32-s3-devkitc-1-ec5-chroma-grid]",
        "-<*>",
        "+<ec5_chroma_grid_epd_driver.cpp>",
        "+<ec5_chroma_grid_main.cpp>",
        "EPD_ENABLE_TEST_PATTERN=0",
        "MF1750_ENABLE_CHROMA_GRID=1",
    ):
        assert token in config
    for forbidden in ("upload_port", "monitor_port", "target = upload"):
        assert forbidden not in config

    header = HEADER_PATH.read_text("utf-8")
    wrapper = WRAPPER_PATH.read_text("utf-8")
    assert "enum class EpdChromaGridRole" in header
    assert "epdValidateCompiledChromaGridFixtures" in header
    assert "epdDisplayCompiledChromaGrid" in header
    assert '#include "ec5_chroma_grid_driver.inc"' in wrapper


def test_one_action_runner_matches_firmware_and_never_controls_power() -> None:
    source = RUNNER_PATH.read_text("utf-8")
    main = MAIN_PATH.read_text("utf-8")
    manifest, _ = build_manifest()
    for action in manifest["actions"]:
        assert action["action_id"] in source
        assert action["descriptor_id"] in source
    names = {
        "BUILD_TAG": "kBuildTag",
        "TEST_ID": "kTestId",
        "CAMPAIGN_ID": "kCampaignId",
        "DEVICE_API_VERSION": "kDeviceApiVersion",
        "IDENTITY_REVISION": "kIdentityRevision",
        "CONTRACT_ID": "kContractId",
        "CLASSIFICATION": "kClassification",
        "NVS_NAMESPACE": "kNvsNamespace",
        "ARM_INTENT": "kArmIntent",
        "EXECUTE_INTENT": "kExecuteIntent",
    }
    for name, main_name in names.items():
        match = re.search(rf'runner\.{name}\s*=\s*(?:\(\s*)?"([^"]+)"', source)
        assert match is not None, name
        expected = _literal(main, main_name)
        assert match.group(1) == expected
    for forbidden in ("relay", "COM14", "esptool", "platformio", "flash"):
        assert forbidden not in source.lower().replace("never flashes", "")
