from __future__ import annotations

from collections import Counter

from tools import mf1750_p2_commented_endpoint_atlas_4x8_v1_codegen as codegen
from tools import mf1750_p2_commented_endpoint_atlas_4x8_v1_pack as pack


def test_fresh_one_shot_comment_profile_and_position_balance() -> None:
    report = pack.build_report()
    contract = report["contract"]
    action = report["actions"][0]
    profile = pack.commented_profile()
    assert contract["action_count"] == 1
    assert contract["one_driver_call_per_action"] is True
    assert contract["one_visible_refresh_per_action"] is True
    assert contract["complete_busy_required"] is True
    assert contract["fresh_one_shot"] is True
    assert contract["source_history_actions"] == 0
    assert contract["middle_history_actions"] == 0
    assert contract["identical_target_repeat_actions"] == 0
    assert contract["retry"] is False
    assert contract["recovery"] is False
    assert contract["automatic_chaining"] is False
    assert profile["name"] == "commented"
    assert profile["complete_profile_tuple"] is True
    assert profile["cs1"] == profile["cs2"]
    assert action["waveform_binding"] == profile
    assert action["cs1_dtm"] == action["cs2_dtm"]
    assert Counter(code for row in pack.CODE_ROWS for code in row) == Counter(
        {code: 4 for code in range(8)}
    )


def test_sealed_frame_dtm_and_artifacts() -> None:
    action = pack.build_report()["actions"][0]
    assert action["frame"]["sha256"] == "d8ee6b0889c8c2e92e3d0d34410f93d90f924816c59987de496ef0ca27ac1768"
    assert action["cs1_dtm"]["sha256"] == "b64c835514b4b6110002c1c2cb366a93bf804f5953229107fa52b27de83dfe0f"
    assert action["global_tuple_id"] == "1d4efb64203093929779a31321695100a6c778367157d633a2dcccabdbdc4038"
    assert pack.validate_artifacts() == {
        "firmware.bin": {
            "path": ".pio/build-p2-commented-endpoint-atlas-4x8-v1/ec5_p2_commented_endpoint_atlas_4x8_v1/firmware.bin",
            "bytes": 798_496,
            "sha256": "61d7704f4dfbcfd3b2ec21aa1eb571b400bf5ee391ababe6e4da1dc54010935d",
        },
        "firmware.elf": {
            "path": ".pio/build-p2-commented-endpoint-atlas-4x8-v1/ec5_p2_commented_endpoint_atlas_4x8_v1/firmware.elf",
            "bytes": 13_286_496,
            "sha256": "451b7663aabd40a0771161c334c41f1f9be39ff0d47b2b7a7342b4edda9f7ac1",
        },
    }


def test_codegen_forces_commented_tuple_without_mutating_p1() -> None:
    generated = codegen.render_sources(pack.build_report())
    driver = generated[f"{codegen.PREFIX}_driver.inc"].decode()
    program = generated[f"{codegen.PREFIX}_program.inc"].decode()
    config = generated[f"{codegen.PREFIX}_main_config.inc"].decode()
    assert "useCommentedGlobal = true;" in driver
    assert "const bool active = false;" in program
    assert pack.commented_profile()["global_tuple_id"] in config
    assert "MF1750_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_BUILD" not in driver
    assert "MF1750_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_BUILD" not in program
