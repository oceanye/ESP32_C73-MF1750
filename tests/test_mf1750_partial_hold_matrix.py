from __future__ import annotations

from pathlib import Path

from tools import mf1750_partial_hold_matrix as hold


ROOT = Path(__file__).resolve().parents[1]
IDENTITY = ROOT / "src" / "ec5_partial_hold_identity.inc"
DRIVER = ROOT / "src" / "ec5_partial_hold_driver.inc"
MAIN = ROOT / "src" / "ec5_chroma_grid_main.cpp"
CONFIG = ROOT / "src" / "ec5_partial_hold_main_config.inc"
PLATFORMIO = ROOT / "platformio.partial_hold_matrix.ini"


def test_eight_fixed_variants_and_five_actions_each() -> None:
    report = hold.build_report()
    assert report["offline_only"] is True
    assert report["hardware_accessed"] is False
    assert report["device_network_accessed"] is False
    assert report["serial_or_com_accessed"] is False
    assert report["firmware_flushed"] is False
    assert report["display_refreshed"] is False
    assert [item["variant"]["key"] for item in report["variants"]] == [
        "ACCUMULATE_OVERWRITE",
        "EDGE_GEOMETRY",
        "DUAL_CS_SPLIT",
        "ACCUMULATE_VMIRROR",
        "ACCUMULATE_SYMMETRIC_V2",
        "ACCUMULATE_SYMMETRIC_Y_INCLUSIVE",
        "ACCUMULATE_SYMMETRIC_BLUE1",
        "ACCUMULATE_SYMMETRIC_Y_INCLUSIVE_BLUE1",
    ]
    assert all(len(item["actions"]) == 5 for item in report["variants"])


def test_cpp_identity_is_exactly_bound_to_generator() -> None:
    source = IDENTITY.read_text("utf-8")
    for variant in hold.build_report()["variants"]:
        assert variant["contract_id"] in source
        for action in variant["actions"]:
            assert action["descriptor_id"] in source
            assert action["action_id"] in source
            assert action["frame"]["sha256"] in source
            assert action["cs1_dtm"]["sha256"] in source
            assert action["cs2_dtm"]["sha256"] in source
            assert f"0x{action['frame']['fnv1a']:08X}UL" in source
            assert f"0x{action['cs1_dtm']['fnv1a']:08X}UL" in source
            assert f"0x{action['cs2_dtm']['fnv1a']:08X}UL" in source
            histogram = ", ".join(str(value) for value in action["frame"]["histogram"])
            assert "{" + histogram + "}" in source


def test_windows_are_packed_safe_and_one_more_y_endpoint_is_bounded() -> None:
    for variant in hold.VARIANTS:
        for window in variant.windows:
            hold.validate_window(window)
            assert window.x % 2 == 0
            assert window.width % 2 == 0
            assert window.x + window.width <= hold.CONTROLLER_WIDTH
            assert window.y + window.height < hold.HEIGHT


def test_vmirror_places_cs2_window_at_the_vertical_mirror_coordinate() -> None:
    variant = hold.build_report()["variants"][3]
    action = variant["actions"][1]
    assert action["window"]["y"] == 96
    assert action["window"]["cs2_y"] == 360
    assert action["window"]["cs2_vertical_mirror"] is True
    frame = bytearray([0x11]) * (hold.WIDTH * hold.HEIGHT // 2)
    hold.set_rect(
        frame,
        hold.VARIANTS[3].windows[0],
        cs2_vertical_mirror=True,
    )
    row_bytes = hold.WIDTH // 2
    assert frame[96 * row_bytes + 48 // 2] == 0x33
    assert frame[360 * row_bytes + (512 + 48) // 2] == 0x33
    assert frame[96 * row_bytes + (512 + 48) // 2] == 0x11


def test_symmetric_v2_matches_original_geometry_with_separate_cs_commands() -> None:
    report = hold.build_report()
    original = report["variants"][0]
    symmetric = report["variants"][4]
    assert symmetric["variant"]["windows"] == original["variant"]["windows"]
    assert symmetric["variant"]["separate_cs_window_commands"] is True
    assert "cs2_vertical_mirror" not in symmetric["variant"]
    for original_action, symmetric_action in zip(
        original["actions"], symmetric["actions"], strict=True
    ):
        assert symmetric_action["frame"] == original_action["frame"]
        assert symmetric_action["cs1_dtm"] == original_action["cs1_dtm"]
        assert symmetric_action["cs2_dtm"] == original_action["cs2_dtm"]
        assert symmetric_action["action_id"] != original_action["action_id"]


def test_y_endpoint_variant_changes_only_ptlw_endpoint_contract() -> None:
    report = hold.build_report()
    control = report["variants"][4]
    inclusive = report["variants"][5]
    assert inclusive["variant"]["windows"] == control["variant"]["windows"]
    assert inclusive["variant"]["ptlw_y_end_one_more"] is False
    for control_action, inclusive_action in zip(
        control["actions"], inclusive["actions"], strict=True
    ):
        assert inclusive_action["frame"] == control_action["frame"]
        assert inclusive_action["cs1_dtm"] == control_action["cs1_dtm"]
        assert inclusive_action["cs2_dtm"] == control_action["cs2_dtm"]


def test_blue1_variant_changes_only_patch_b_code_and_accumulated_frame() -> None:
    report = hold.build_report()
    blue2 = report["variants"][4]
    blue1 = report["variants"][6]
    assert blue1["variant"]["windows"][0] == blue2["variant"]["windows"][0]
    assert blue1["variant"]["windows"][2] == blue2["variant"]["windows"][2]
    assert blue2["variant"]["windows"][1]["cs1_code"] == 5
    assert blue1["variant"]["windows"][1]["cs1_code"] == 4
    assert blue1["actions"][0]["frame"] == blue2["actions"][0]["frame"]
    assert blue1["actions"][1]["frame"] == blue2["actions"][1]["frame"]
    assert blue1["actions"][2]["cs1_dtm"]["bytes"] == 11520
    assert blue1["actions"][2]["cs1_dtm"]["sha256"] != blue2["actions"][2][
        "cs1_dtm"
    ]["sha256"]


def test_y_inclusive_blue1_combines_only_the_two_qualified_variables() -> None:
    report = hold.build_report()
    blue2 = report["variants"][5]
    legacy_blue1 = report["variants"][6]
    qualified = report["variants"][7]
    assert qualified["variant"]["ptlw_y_end_one_more"] is False
    assert qualified["variant"]["windows"] == legacy_blue1["variant"]["windows"]
    assert qualified["variant"]["windows"][0] == blue2["variant"]["windows"][0]
    assert qualified["variant"]["windows"][2] == blue2["variant"]["windows"][2]
    assert qualified["variant"]["windows"][1]["cs1_code"] == 4
    for qualified_action, legacy_action in zip(
        qualified["actions"], legacy_blue1["actions"], strict=True
    ):
        assert qualified_action["frame"] == legacy_action["frame"]
        assert qualified_action["cs1_dtm"] == legacy_action["cs1_dtm"]
        assert qualified_action["cs2_dtm"] == legacy_action["cs2_dtm"]
    identity = IDENTITY.read_text("utf-8")
    config = CONFIG.read_text("utf-8")
    assert "kVariant != 5 && kVariant != 7" in identity
    assert "MF1750_PARTIAL_HOLD_VARIANT == 5 ||" in config
    assert '"\\\"ptlw_endpoint_contract\\\":\\\"xe=x+w-1;ye=y+h-1\\\","' in config


def test_driver_has_only_fixed_ptlw_factory_otp_path() -> None:
    source = DRIVER.read_text("utf-8")
    config = CONFIG.read_text("utf-8")
    assert "kPartialWindowCommand = 0x83" in IDENTITY.read_text("utf-8")
    assert "epdCommand(ph::kPartialWindowCommand)" in source
    assert "ph::kPtlwYEndOneMore" in source
    assert "epdCommand(DTM)" in source
    assert "epdSecondSettingAndRefresh()" in source
    assert "epdPrepareCascade(EPD_SPI_DEFAULT_HZ)" in source
    assert "epdCommand(0x86)" not in source
    assert "epdCommand(0x90)" not in source
    assert "epdCommand(0x91)" not in source
    assert '"runtime_lut_write":false' not in config  # emitted by shared shell
    assert "command_0x83" in config
    assert "mid_refresh_power_cut" in config
    assert "camera_required" in config


def test_partial_hold_restarts_http_listener_after_blocking_panel_io() -> None:
    source = MAIN.read_text("utf-8")
    assert "void restartHttpListenerAfterBlockingPanelIo()" in source
    assert "#ifdef MF1750_PARTIAL_HOLD_BUILD" in source
    assert "server.stop();" in source
    assert "server.begin();" in source
    assert source.count("restartHttpListenerAfterBlockingPanelIo();") == 3


def test_platformio_has_eight_isolated_builds_and_no_upload_target() -> None:
    source = PLATFORMIO.read_text("utf-8")
    for name, index in (
        ("ec5_partial_hold_accumulate", 0),
        ("ec5_partial_hold_edges", 1),
        ("ec5_partial_hold_cs_split", 2),
        ("ec5_partial_hold_acc_vmirror", 3),
        ("ec5_partial_hold_acc_symmetric_v2", 4),
        ("ec5_partial_hold_acc_symmetric_y_inclusive", 5),
        ("ec5_partial_hold_acc_symmetric_blue1", 6),
        ("ec5_partial_hold_acc_symmetric_y_inclusive_blue1", 7),
    ):
        assert f"[env:{name}]" in source
        assert f"-D MF1750_PARTIAL_HOLD_VARIANT={index}" in source
    assert "upload_port" not in source
    assert "upload_protocol" not in source
