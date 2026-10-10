from __future__ import annotations

from host.extended_color.mf1750_target_hues import (
    ADAPTIVE_RESERVE_SLOTS,
    TARGET_HUES,
    build_catalog,
    validate_catalog,
)
from tools.mf1750_target_hue_catalog import describe


def test_target_hue_catalog_is_a_complete_256_slot_plan() -> None:
    validate_catalog()
    assert (
        sum(item.palette_slots_256 for item in TARGET_HUES) + ADAPTIVE_RESERVE_SLOTS
        == 256
    )
    assert len(TARGET_HUES) == 13


def test_target_hue_catalog_keeps_candidates_unqualified() -> None:
    report = build_catalog()
    boundary = report["evidence_boundary"]
    assert boundary["direct_transport_slots_per_controller_profile"] == 8
    assert len(boundary["confirmed_visual_base_groups"]) == 7
    assert boundary["qualified_unique_colours_now"] is None
    assert boundary["history_recipes_are_not_unique_colours"] is True
    assert report["spatial_dithering"] is False
    assert report["initial_target_levels"] == 84
    assert "not that many lightness levels" in report["palette_slot_semantics"]


def test_target_hue_catalog_prioritises_photo_critical_families() -> None:
    priority_zero = {item.hue_id for item in TARGET_HUES if item.priority == 0}
    assert priority_zero == {"N", "R", "RO", "O", "Y", "G", "B"}
    skin = next(item for item in TARGET_HUES if item.hue_id == "O")
    assert skin.initial_lightness_steps == 8
    assert skin.palette_slots_256 == 32


def test_cli_description_has_stable_identity_and_no_live_claim() -> None:
    first = describe()
    second = describe()
    assert first == second
    assert len(first["catalog_id"]) == 64
    assert first["offline_only"] is True
    assert first["hardware_accessed"] is False


def test_blue_screening_batch_binds_reviewed_firmware_and_fresh_containment() -> None:
    batch = build_catalog()["offline_screening_batches"][0]
    assert batch["batch_id"] == "BLUE-BRIGHTNESS-64-V1"
    assert batch["hue_id"] == "B"
    assert batch["unique_history_recipes"] == 64
    assert batch["physical_controller_observations"] == 128
    assert batch["qualified_brightness_levels"] == 0
    assert batch["spatial_dithering"] is False
    assert batch["status"] == "live-screened-zero-visible-brightness-candidates"
    assert batch["live_screening"]["protocol_actions_complete"] == 6
    assert batch["live_screening"]["first_target_visible_brightness_candidates"] == 0
    assert (
        batch["live_screening"]["identical_target_repeat_visible_brightness_candidates"]
        == 0
    )
    assert batch["live_screening"]["runtime_code7_white_recovery"] == (
        "protocol-pass-visual-fail"
    )
    assert batch["contract_id"] == (
        "3d5dee5165a86ec470205bcd970c4d76fceb68599d4a54cc1aea882dae2bfee7"
    )
    containment = batch["failure_containment"]
    assert containment["fresh_identity"] is True
    assert containment["campaign_nvs_dependency"] is False
    assert containment["nvs_namespace"] == "rlhbcw_v1"
    assert containment["nvs_key"] == "used_hbcw1"
