from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools import mf1750_runtime_lut_cross_palette_ab_v1_once as ab_once
from tools import mf1750_runtime_lut_cross_palette_ba_v1_once as ba_once
from tools import mf1750_runtime_lut_cross_palette_v1_pack as pack


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("direction", ["ab", "ba"])
def test_cross_pack_geometry_and_histograms(direction: pack.Direction) -> None:
    report = pack.build_report(direction)
    contract = report["contract"]
    assert contract["direction"] == direction
    assert contract["partial_refresh"] is False
    assert contract["cross_palette_hold_probe"] is True
    assert contract["target_repeat_stability_probe"] is True
    assert contract["geometry"] == {
        "width": 1024,
        "height": 600,
        "controller_width": 512,
        "source_rows": 8,
        "source_row_height": 75,
        "target_columns_per_controller": 8,
        "target_column_width": 64,
        "history_cells_per_controller": 64,
        "history_cells_total": 128,
        "spatial_dither": False,
    }
    expected = [76800] * 8
    assert report["actions"][1]["frame"]["histogram"] == expected
    assert report["actions"][2]["frame"]["histogram"] == expected
    assert report["actions"][3]["frame"]["histogram"] == expected
    assert report["actions"][0]["frame"]["histogram"] == [0] * 7 + [614400]


def test_cross_direction_profiles_are_inverse() -> None:
    ab = pack.build_report("ab")["actions"]
    ba = pack.build_report("ba")["actions"]
    assert [item["global_header"] for item in ab] == [
        "active",
        "active",
        "commented",
        "commented",
        "active",
    ]
    assert [item["global_header"] for item in ba] == [
        "active",
        "commented",
        "active",
        "active",
        "active",
    ]


def test_cross_compiled_identities_match_pack() -> None:
    text = (ROOT / "src" / "ec5_runtime_lut_cross_palette_v1_identity.inc").read_text()
    for direction in ("ab", "ba"):
        report = pack.build_report(direction)
        assert report["contract_id"] in text
        for action in report["actions"]:
            assert action["descriptor_id"] in text
            assert action["action_id"] in text
            assert action["frame"]["sha256"] in text
            assert action["cs1_dtm"]["sha256"] in text
            assert f"0x{action['frame']['fnv1a']:08X}UL" in text


def test_cross_selected_transport_is_full_frame_without_ptlw() -> None:
    driver = (ROOT / "src" / "ec5_runtime_lut_cross_palette_v1_driver.inc").read_text()
    config = (
        ROOT / "src" / "ec5_runtime_lut_cross_palette_v1_main_config.inc"
    ).read_text()
    assert "static constexpr bool fullFrame = true;" in driver
    assert "if (!fullFrame && !fullWhite) phWritePartialWindow(*window);" in driver
    assert "(fullFrame || fullWhite)" in driver
    assert '"partial_refresh\\":false' in config
    assert '"command_0x83\\":false' in config
    assert '"cross_palette_hold_probe\\":true' in config
    assert '"target_repeat_stability_probe\\":true' in config


def test_cross_fixture_validates_the_packed_controller_dtm() -> None:
    driver = (ROOT / "src" / "ec5_runtime_lut_cross_palette_v1_driver.inc").read_text()
    packed_branch = driver.split("bool phValidateRole", 1)[1].split(
        "void phWritePartialWindowAt", 1
    )[0]
    assert "defined(MF1750_RUNTIME_LUT_CROSS_PALETTE_AB_V1_BUILD)" in packed_branch
    assert "defined(MF1750_RUNTIME_LUT_CROSS_PALETTE_BA_V1_BUILD)" in packed_branch
    assert "phPackedFrameDtmIdentity(frame, false" in packed_branch
    assert "phPackedFrameDtmIdentity(frame, true" in packed_branch


@pytest.mark.parametrize(
    ("once", "environment"),
    [
        (ab_once, "ec5_runtime_lut_cross_palette_ab_v1"),
        (ba_once, "ec5_runtime_lut_cross_palette_ba_v1"),
    ],
)
def test_cross_runner_exact_firmware_binding(once, environment: str) -> None:
    firmware = (
        ROOT
        / ".pio"
        / "build-runtime-lut-cross-palette-v1"
        / environment
        / "firmware.bin"
    )
    assert firmware.stat().st_size == once.base.runner.FIRMWARE_BYTES
    assert hashlib.sha256(firmware.read_bytes()).hexdigest() == (
        once.base.runner.FIRMWARE_SHA256
    )


@pytest.mark.parametrize(("once", "direction"), [(ab_once, "ab"), (ba_once, "ba")])
def test_cross_manifest_validation_and_direction_gate(once, direction: str) -> None:
    report = pack.build_report(direction)
    source_header = "active" if direction == "ab" else "commented"
    target_header = "commented" if direction == "ab" else "active"
    source_profile = pack.profile(source_header)["id"]
    target_profile = pack.profile(target_header)["id"]
    fixed_profile = pack.profile(source_header)
    manifest = {
        "kind": "mf1750-ec5-runtime-lut-partial-hold-manifest",
        "build_tag": pack.constants(direction)["build_tag"],
        "test_id": pack.constants(direction)["test_id"],
        "campaign_id": pack.constants(direction)["campaign_id"],
        "device_api_version": "MF1750_EC5_RUNTIME_LUT_CROSS_PALETTE_DEVICE_V1",
        "identity_revision": "runtime-lut-cross-palette-v1",
        "contract_id": report["contract_id"],
        "classification": (
            "EXPERIMENTAL_L535_BIDIRECTIONAL_8X8_CROSS_PALETTE_HOLD_SEARCH"
        ),
        "actions": list(once.base.runner.ACTIONS),
        "action_count": 5,
        "one_driver_call_per_action": True,
        "factory_otp": False,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "history_layout": {
            "cross_palette_direction": direction,
            "action_global_headers": [
                "active",
                source_header,
                target_header,
                target_header,
                "active",
            ],
            "source_profile_id": source_profile,
            "target_profile_id": target_profile,
            "runtime_lut_profile_id": f"{source_profile}_TO_{target_profile}",
            "ptlw_command_issued": False,
            "cropped_dtm": False,
            "all_action_dtm_transport": "packed_frame_per_controller",
            "source_rows": 8,
            "target_columns_per_controller": 8,
            "history_cells_per_controller": 64,
            "history_cells_total": 128,
            "target_repeat_stability_probe": True,
            "white_transport_code": pack.WHITE_CODE,
            **{
                key: fixed_profile[key]
                for key in (
                    "cs1_r20_prefix_bytes",
                    "cs1_r20_prefix_sha256",
                    "cs2_r20_prefix_bytes",
                    "cs2_r20_prefix_sha256",
                    "r21_bytes",
                    "r21_sha256",
                )
            },
        },
        "partial_refresh": False,
        "window_refresh": False,
        "command_0x83": False,
        "command_0x86": False,
        "mid_refresh_power_cut": False,
        "spi_frequency_sweep": False,
        "full_screen_global_refresh": True,
        "same_palette_hold_probe": False,
        "full_frame_cumulative_redraw": False,
        "cross_palette_hold_probe": True,
        "target_repeat_stability_probe": True,
    }
    once.base._validate_manifest(manifest)
    manifest["history_layout"]["cross_palette_direction"] = (
        "ba" if direction == "ab" else "ab"
    )
    with pytest.raises(once.base.runner.RecheckError):
        once.base._validate_manifest(manifest)
