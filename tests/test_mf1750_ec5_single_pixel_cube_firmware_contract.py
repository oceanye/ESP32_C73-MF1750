from __future__ import annotations

from pathlib import Path
import re

from tools.mf1750_ec5_single_pixel_cube import build_manifest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src/ec5_chroma_grid_main.cpp"
CONFIG = ROOT / "src/ec5_single_pixel_cube_main_config.inc"
DRIVER = ROOT / "src/ec5_single_pixel_cube_driver.inc"
WRAPPER = ROOT / "src/ec5_single_pixel_cube_epd_driver.cpp"
ENTRY = ROOT / "src/ec5_single_pixel_cube_main.cpp"
PLATFORMIO = ROOT / "platformio.single_pixel_cube.ini"


def _literal(source: str, name: str) -> str:
    match = re.search(
        rf'static constexpr const char \*{re.escape(name)}\s*=\s*"([^"]+)";',
        source,
    )
    assert match is not None, name
    return match.group(1)


def test_compiled_contract_matches_all_offline_frame_identities() -> None:
    manifest, _ = build_manifest()
    config = CONFIG.read_text("utf-8")
    driver = DRIVER.read_text("utf-8")

    assert _literal(config, "kClassification") == manifest["classification"]
    assert _literal(config, "kCampaignId") == manifest["campaign_id"]
    assert _literal(config, "kContractId") == manifest["integrity"][
        "canonical_sha256"
    ]
    positions: list[int] = []
    for action in manifest["actions"]:
        positions.append(config.index(action["action_id"]))
        assert action["descriptor_id"] in config
        assert action["frame_sha256"] in config
        assert action["cs1_dtm_sha256"] in config
        assert action["cs2_dtm_sha256"] in config
    assert positions == sorted(positions)

    for identity in manifest["frames"].values():
        assert identity["sha256"] in driver
        assert identity["fnv1a"] + "UL" in driver
        for controller in identity["controllers"]:
            assert controller["sha256"] in driver
            assert controller["fnv1a"] + "UL" in driver


def test_dense_layout_is_uniform_per_roi_and_covers_the_full_cube() -> None:
    driver = DRIVER.read_text("utf-8")
    for token in (
        "SPC_COLUMNS = 11",
        "SPC_ROWS = 24",
        "SPC_SLOTS_PER_CONTROLLER == 264",
        "SPC_CELL_WIDTH = 40",
        "SPC_CELL_HEIGHT = 22",
        "SPC_GAP_X = 4",
        "SPC_GAP_Y = 2",
        "SPC_X0 = 16",
        "SPC_Y0 = 13",
        "source + mid + target",
        "std::memset(frame, 0x11, EPD_FRAME_BYTES)",
        "std::memset",
    ):
        assert token in driver
    assert "coverage" in driver
    assert "256" in driver
    assert "32" in driver
    executable = "\n".join(line.split("//", 1)[0] for line in driver.splitlines())
    assert "0x86" not in executable
    for forbidden in (
        "partial",
        "window",
        "powerCut",
        "power_cut",
        "runtimeLut",
        "runtime_lut",
        "spiSweep",
        "spi_sweep",
    ):
        assert forbidden not in executable


def test_isolated_entry_keeps_one_full_screen_refresh_per_action() -> None:
    main = MAIN.read_text("utf-8")
    config = CONFIG.read_text("utf-8")
    driver = DRIVER.read_text("utf-8")
    wrapper = WRAPPER.read_text("utf-8")
    entry = ENTRY.read_text("utf-8")
    platformio = PLATFORMIO.read_text("utf-8")

    assert '#include "ec5_single_pixel_cube_main_config.inc"' in main
    assert "MF1750_SINGLE_PIXEL_CUBE_BUILD" in main
    assert "kCampaignCapabilitiesJson" in main
    for token in (
        '\\"partial_refresh\\":false',
        '\\"window_refresh\\":false',
        '\\"command_0x86\\":false',
        '\\"mid_refresh_power_cut\\":false',
        '\\"spi_frequency_sweep\\":false',
        '\\"full_screen_global_refresh\\":true',
        '\\"grid_x1_local_exclusive\\":496',
    ):
        assert token in config

    display = driver[driver.index("bool epdDisplayCompiledChromaGrid") :]
    assert display.index("spcValidateRole") < display.index("epdPrepareCascade")
    assert display.count("epdSecondSettingAndRefresh()") == 1
    assert "setActiveControllers(true, true)" in display
    assert '#include "epd_driver.cpp"' in wrapper
    assert '#include "ec5_single_pixel_cube_driver.inc"' in wrapper
    assert '#include "ec5_chroma_grid_main.cpp"' in entry
    for token in (
        "-<*>",
        "+<ec5_single_pixel_cube_epd_driver.cpp>",
        "+<ec5_single_pixel_cube_main.cpp>",
        "EPD_ENABLE_TEST_PATTERN=0",
        "MF1750_ENABLE_CHROMA_GRID=1",
        "MF1750_SINGLE_PIXEL_CUBE_BUILD=1",
    ):
        assert token in platformio
    for forbidden in ("upload_port", "monitor_port", "target = upload"):
        assert forbidden not in platformio
