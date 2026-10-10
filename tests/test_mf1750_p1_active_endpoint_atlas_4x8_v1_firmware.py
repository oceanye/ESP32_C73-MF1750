from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools import mf1750_p1_active_endpoint_atlas_4x8_v1_pack as pack


ROOT = Path(__file__).resolve().parents[1]


def test_p1_is_one_fresh_endpoint_action_without_history_or_repeat() -> None:
    report = pack.build_report()
    contract = report["contract"]
    assert report["contract_id"] == (
        "d36450e7cf69ad2e5e612f9df5b5abe0d33a036f9c3198a79a9e0e97a89a59f2"
    )
    assert len(report["actions"]) == 1
    assert contract["fresh_one_shot"] is True
    assert contract["source_history_actions"] == 0
    assert contract["middle_history_actions"] == 0
    assert contract["identical_target_repeat_actions"] == 0
    assert contract["runtime_lut_ordinals"] == [1]
    assert contract["factory_otp_white_ordinals"] == []
    assert contract["automatic_chaining"] is False
    assert contract["retry"] is False
    assert contract["recovery"] is False


def test_required_position_balanced_rows_and_controller_streams() -> None:
    assert pack.CODE_ROWS == (
        (0, 1, 2, 3, 4, 5, 6, 7),
        (4, 5, 6, 7, 0, 1, 2, 3),
        (1, 2, 3, 4, 5, 6, 7, 0),
        (5, 6, 7, 0, 1, 2, 3, 4),
    )
    assert Counter(code for row in pack.CODE_ROWS for code in row) == Counter(
        {code: 4 for code in range(8)}
    )
    frame = pack.atlas_frame()
    assert len(frame) == 307_200
    assert pack.controller_stream(frame, 0) == pack.controller_stream(frame, 1)
    assert pack.build_report()["actions"][0]["frame"]["histogram"] == [
        41_600,
        41_600,
        41_600,
        41_600,
        41_600,
        41_600,
        41_600,
        323_200,
    ]


def test_complete_active_profile_is_byte_identical_on_both_controllers() -> None:
    profile = pack.active_profile()
    action = pack.build_report()["actions"][0]
    assert profile["id"] == "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_ACTIVE535"
    assert profile["complete_profile_tuple"] is True
    assert profile["controller_payloads_byte_identical"] is True
    assert profile["cs1"] == profile["cs2"]
    assert profile["global_tuple_id"] == (
        "4ba82591a96bc789f1ec2ea17ab81d4ae7e8986386cad8264a8dac48f021e820"
    )
    assert action["cs1_dtm"] == action["cs2_dtm"]
    assert action["waveform_binding"] == profile


def test_cpp_contract_binds_pack_and_private_source_only() -> None:
    report = pack.build_report()
    action = report["actions"][0]
    identity = (ROOT / "src/ec5_p1_active_endpoint_atlas_4x8_v1_identity.inc").read_text(
        encoding="utf-8"
    )
    config = (ROOT / "src/ec5_p1_active_endpoint_atlas_4x8_v1_main_config.inc").read_text(
        encoding="utf-8"
    )
    program = (ROOT / "src/ec5_p1_active_endpoint_atlas_4x8_v1_program.inc").read_text(
        encoding="utf-8"
    )
    driver = (ROOT / "src/ec5_p1_active_endpoint_atlas_4x8_v1_driver.inc").read_text(
        encoding="utf-8"
    )
    assert report["contract_id"] in identity
    assert action["descriptor_id"] in identity and action["descriptor_id"] in config
    assert action["action_id"] in identity and action["action_id"] in config
    assert '"complete_profile_tuple\\\":true"' in program
    assert "ph::kCodeRows[row][column]" in driver
    assert "ph::kGridYByRow[row]" in driver
    for shared in (
        "src/ec5_runtime_lut_same_r20_parity_4x8_v2_main.cpp",
        "src/ec5_runtime_lut_same_r20_parity_4x8_v2_driver.inc",
    ):
        assert "P1_ACTIVE_ENDPOINT" not in (ROOT / shared).read_text(encoding="utf-8")


def test_final_artifacts_are_exact_and_offline_contract_claims_zero_io() -> None:
    verified = pack.validate_artifacts()
    assert pack.artifacts_are_sealed() is True
    assert verified == {
        "firmware.bin": {
            "path": (
                ".pio/build-p1-active-endpoint-atlas-4x8-v1/"
                "ec5_p1_active_endpoint_atlas_4x8_v1/firmware.bin"
            ),
            "bytes": 799_024,
            "sha256": (
                "f5c83b357c1db3dd065669e36d0ac9a09edfe47c720fadecad98c196a81652ed"
            ),
        },
        "firmware.elf": {
            "path": (
                ".pio/build-p1-active-endpoint-atlas-4x8-v1/"
                "ec5_p1_active_endpoint_atlas_4x8_v1/firmware.elf"
            ),
            "bytes": 13_286_576,
            "sha256": (
                "c6eb0203cd7b5cd2373199ead8857cb793e495a459bced12aa3fd5160e5b7a7c"
            ),
        },
    }
    report = pack.build_report()
    assert report["offline_only"] is True
    assert report["hardware_accessed"] is False
    assert report["device_network_accessed"] is False
    assert report["serial_or_com_accessed"] is False
    assert report["relay_accessed"] is False
    assert report["firmware_flashed"] is False
    assert report["display_refreshed"] is False
