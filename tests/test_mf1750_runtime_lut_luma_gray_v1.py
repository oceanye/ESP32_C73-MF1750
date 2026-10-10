from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools import mf1750_runtime_lut_luma_gray_v1_once as once
from tools import mf1750_runtime_lut_luma_gray_v1_pack as pack
from tools import (
    mf1750_runtime_lut_luma_gray_v1_white_containment_once as containment_once,
)
from tools import (
    mf1750_runtime_lut_luma_gray_v1_white_containment_pack as containment_pack,
)

ROOT = Path(__file__).resolve().parents[1]


def test_two_pages_have_32_unique_recipes_and_four_positions_each() -> None:
    report = pack.build_report()
    contract = report["contract"]
    assert len(contract["recipes"]) == 32
    assert {item["page"] for item in contract["recipes"]} == {1, 2}
    assert all(len(item["positions"]) == 4 for item in contract["recipes"])
    assert all(pack.RECIPE_AT_CELL.count(recipe) == 4 for recipe in range(16))
    assert contract["pages"] == [
        {
            "page": 1,
            "target": {"global_header": "active", "code": 3},
            "recipe_count": 16,
        },
        {
            "page": 2,
            "target": {"global_header": "active", "code": 7},
            "recipe_count": 16,
        },
    ]


def test_evidence_boundary_and_machine_thresholds_are_explicit() -> None:
    contract = pack.build_report()["contract"]
    assert contract["requested_factory_otp_black_white_per_cell_source"] is False
    assert contract["source_anchor_codes"] == [3, 7]
    assert contract["source_anchor_colour_names_claimed"] is False
    assert contract["true_neutral_gray_claimed"] is False
    assert contract["qualified_gray_levels"] == 0
    gate = contract["position_acceptance"]
    assert gate["required_valid_repeats"] == "4_of_4"
    assert gate["max_within_recipe_position_dispersion_p95_delta_e76"] == 6.6032
    assert gate["gray_candidate_relative_neutral_locus_ab_distance_max"] == 8.0
    assert gate["gray_candidate_min_repeats_passing"] == "3_of_4"
    assert gate["gray_candidate_lstar_range"] == [15.0, 85.0]
    assert gate["minimum_adjacent_candidate_delta_lstar"] == 8.0
    qualification = contract["qualification_stage_not_this_campaign"]
    assert qualification == {
        "relative_neutral_locus_ab_distance_max": 5.0,
        "target_repeat_delta_e76_max": 6.6032,
        "fresh_run_count": 3,
        "observation_times_seconds": [5, 60, 600],
        "qualified_by_this_campaign": False,
    }


def test_action_order_and_profile_sequence_are_frozen() -> None:
    report = pack.build_report()
    assert [item["role"] for item in report["actions"]] == list(pack.ROLES)
    assert pack.GLOBAL_HEADERS == (
        None,
        "active",
        "commented",
        "active",
        None,
        "active",
        "commented",
        "active",
    )
    assert report["contract"]["factory_otp_white_ordinals"] == [1, 5]
    assert report["contract"]["main_campaign_contains_final_recovery"] is False
    assert (
        report["contract"]["independent_fresh_factory_otp_white_containment_required"]
        is True
    )
    assert all("boot_admission" in action for action in once.base.runner.ACTIONS)
    assert [action["global_header"] for action in once.base.runner.ACTIONS] == list(
        pack.GLOBAL_HEADERS
    )
    assert once.base.runner.ACTIONS[7]["driver_entry"] == "epdDisplayCompiledChromaGrid"


def test_runner_accepts_only_the_exact_manifest_thresholds() -> None:
    capabilities = {
        "full_screen_global_refresh": True,
        "history_brightness_screening": True,
        "busy_qualified_arm_execute_dispatch": True,
        "device_enforced_same_boot": True,
        "candidate_only": True,
        "independent_fresh_white_containment_required": True,
        "partial_refresh": False,
        "window_refresh": False,
        "command_0x83": False,
        "command_0x86": False,
        "local_hold_claimed": False,
        "true_neutral_gray_claimed": False,
        "qualified_gray_levels": 0,
        "qualified_brightness_levels": 0,
    }
    manifest = {
        "kind": "mf1750-ec5-luma-gray-v1-manifest",
        "build_tag": pack.BUILD_TAG,
        "test_id": pack.TEST_ID,
        "campaign_id": pack.CAMPAIGN_ID,
        "device_api_version": once.base.runner.DEVICE_API_VERSION,
        "identity_revision": once.base.runner.IDENTITY_REVISION,
        "contract_id": once.REPORT["contract_id"],
        "classification": once.base.runner.CLASSIFICATION,
        "layout_id": pack.VARIANT_KEY,
        "action_count": 8,
        "actions": list(once.base.runner.ACTIONS),
        "history_layout": {
            "pages": 2,
            "recipes_per_page": 16,
            "repeats_per_recipe_per_controller": 4,
            "required_valid_repeats": "4_of_4",
            "source_anchor_codes": [3, 7],
            "factory_otp_per_cell_black_white_source_implemented": False,
            "true_neutral_gray_claimed": False,
            "qualified_gray_levels": 0,
            "position_dispersion_p95_delta_e76_max": 6.6032,
        },
        **capabilities,
    }
    once._validate_manifest(manifest)
    manifest["history_layout"]["position_dispersion_p95_delta_e76_max"] = 6.0
    with pytest.raises(once.base.runner.RecheckError, match="threshold/layout"):
        once._validate_manifest(manifest)


def test_compiled_identity_files_bind_pack_actions_and_contract() -> None:
    report = pack.build_report()
    identity = (ROOT / "src/ec5_runtime_lut_luma_gray_v1_identity.inc").read_text(
        encoding="utf-8"
    )
    config = (ROOT / "src/ec5_runtime_lut_luma_gray_v1_main_config.inc").read_text(
        encoding="utf-8"
    )
    assert report["contract_id"] in identity
    for action in report["actions"]:
        assert action["descriptor_id"] in config
        assert action["action_id"] in config
        assert action["frame"]["sha256"] in config
        assert action["cs1_dtm"]["sha256"] in config


def test_main_and_containment_artifacts_match_frozen_hashes() -> None:
    assert once.dry_validate()["result"] == "PASS"
    assert containment_once.dry_validate()["result"] == "PASS"
    for path, size, digest in (
        (
            once.BUILD_DIR / "firmware.bin",
            once.base.runner.FIRMWARE_BYTES,
            once.base.runner.FIRMWARE_SHA256,
        ),
        (once.BUILD_DIR / "firmware.elf", once.ELF_BYTES, once.ELF_SHA256),
        (
            containment_pack.FIRMWARE_BIN,
            containment_pack.FIRMWARE_BIN_BYTES,
            containment_pack.FIRMWARE_BIN_SHA256,
        ),
        (
            containment_pack.FIRMWARE_ELF,
            containment_pack.FIRMWARE_ELF_BYTES,
            containment_pack.FIRMWARE_ELF_SHA256,
        ),
    ):
        data = Path(path).read_bytes()
        assert len(data) == size
        assert hashlib.sha256(data).hexdigest() == digest


def test_containment_is_fresh_and_cannot_resume_main_campaign() -> None:
    report = containment_pack.build_report()
    assert report["contract_id"] == containment_pack.CONTRACT_ID
    assert report["descriptor_id"] == containment_pack.DESCRIPTOR_ID
    assert report["action_id"] == containment_pack.ACTION_ID
    assert (
        report["contract"]["source_main_contract_id"]
        == pack.build_report()["contract_id"]
    )
    assert report["contract"]["main_campaign_resume_after_containment"] is False
    assert report["contract"]["runtime_lut_write"] is False
