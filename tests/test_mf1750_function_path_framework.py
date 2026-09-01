import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK = ROOT / "docs" / "MF1750_FUNCTION_PATH_FRAMEWORK_2026-09-01.json"


def _load() -> dict:
    return json.loads(FRAMEWORK.read_text(encoding="utf-8"))


def test_function_path_is_single_pixel_and_controller_specific() -> None:
    payload = _load()
    assert payload["scope"]["pixel_model"] == "single_pixel_transport_code_history"
    assert payload["scope"]["spatial_dithering_allowed_as_colour_evidence"] is False
    assert payload["scope"]["controllers_evaluated_separately"] is True
    assert (
        "independent physical colour systems"
        in payload["coarse_screening_gates"]["controller_rule"]
    )


def test_framework_prioritizes_lightness_before_more_hues_and_reliability() -> None:
    payload = _load()
    order = payload["priority_order"]
    assert order.index("POSITION_BALANCED_GRAY_LIGHTNESS_MECHANISM") < order.index(
        "MORE_HUE_ENUMERATION"
    )
    assert order.index("STABLE_BASE_HUE_LIGHTNESS_LATIN_SCREEN") < order.index(
        "LONG_DURATION_AND_MULTI_RUN_RELIABILITY"
    )
    assert order.index("STABLE_BASE_HUE_LIGHTNESS_LATIN_SCREEN") < order.index(
        "POSITION_BALANCED_GRAY_LIGHTNESS_MECHANISM"
    )
    assert order.index("STABLE_BASE_HUE_LIGHTNESS_FAMILY_GENERALIZATION") < order.index(
        "MORE_HUE_ENUMERATION"
    )
    assert order.index("FIXED_STATIC_PHOTO_EXECUTION_CAMPAIGN") < order.index(
        "MORE_HUE_ENUMERATION"
    )


def test_unearned_colour_and_photo_claims_remain_zero() -> None:
    payload = _load()
    state = payload["current_state"]
    assert state["qualified_new_colours"] == 0
    assert state["qualified_neutral_gray_levels"] == 0
    assert state["qualified_lightness_levels"] == 0
    assert state["qualified_cross_lut_palette_slots"] == 0
    assert state["qualified_photo_palette_slots"] == 0
    assert payload["scope"]["automatic_unique_colour_claims"] is False


def test_live_f2_snapshot_records_l4_collapse_and_white_containment() -> None:
    payload = _load()
    state = payload["current_state"]
    snapshot = payload["live_f2_v3_snapshot"]

    assert state["terminal_live_action"] == "V3_INDEPENDENT_FACTORY_OTP_WHITE_COMPLETE"
    assert state["w11_retained_white_anchor"] == "CONSUMED_BY_V3_L1"
    assert state["v3_optional_l4_repeat"] == "COMPLETE_NEGATIVE_STABILITY_DIAGNOSTIC"
    assert state["v3_factory_otp_white_containment"].startswith("COMPLETE")
    assert snapshot["completed_visible_ordinals"] == [1, 2, 3, 4]
    assert snapshot["optional_l4_repeat_executed"] is True
    assert snapshot["same_exposure_comparison"]["repeat_gate"] == "FAIL_COLLAPSED"
    assert "ZERO_QUALIFIED" in snapshot["qualification_decision"]


def test_only_the_48mp_project_camera_is_admitted() -> None:
    camera = _load()["evidence_camera"]
    assert (camera["vid"], camera["pid"]) == ("32E4", "4801")
    assert camera["allowed_for_this_project"] is True
    assert "1BCF:PID_0B15" in camera["explicitly_excluded_device"]


def test_visible_actions_are_fail_closed_and_not_autochained() -> None:
    payload = _load()
    safety = payload["execution_safety"]
    assert safety["exactly_one_driver_call_per_visible_action"] is True
    assert safety["no_retry"] is True
    assert safety["no_fallback"] is True
    assert safety["no_recovery"] is True
    assert safety["no_autochain"] is True
    assert safety["factory_otp_white_containment_is_independent_successor"] is True
    assert safety["source_gate"].startswith("V3 white successor COMPLETE")
    assert safety["next_live_successor"].startswith(
        "F1 LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3"
    )
    assert "independently bound factory-OTP white" in safety["sequential_test_policy"]


def test_lightness_candidates_require_position_and_fresh_reconstruction_gates() -> None:
    payload = _load()
    gates = payload["coarse_screening_gates"]
    assert gates["position_repeatability"]["required_valid_replicas"] == "all"
    assert gates["chromatic_lightness_candidate"]["absolute_delta_l_star_min"] == 8.0
    assert gates["reproducibility"]["history_recipe_mode"] == (
        "FRESH_WHITE_RECONSTRUCTION"
    )
    assert (
        gates["reproducibility"][
            "in_place_identical_target_repeat_allowed_for_history_recipe"
        ]
        is False
    )
    assert (
        gates["single_pixel_purity"]["spatial_dither_or_interleaved_stripes"]
        == "REJECT"
    )


def test_photo_path_names_the_fail_closed_multi_lut_scheduler() -> None:
    payload = _load()
    photo = next(stage for stage in payload["stages"] if stage["id"] == "F6")
    assert photo["software_component"] == "host.static_photo.multi_lut_hold_schedule"
    assert "NO_HARDWARE_PALETTE_QUALIFIED" in photo["status"]
    assert "Reject candidate recipes" in photo["fail_closed_behavior"]


def test_implemented_software_pipeline_connects_lightness_to_photo_schedule() -> None:
    pipeline = _load()["software_pipeline"]
    assert [item["order"] for item in pipeline] == [
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
    ]
    assert pipeline[0]["component"] == "host.static_photo.lightness_screen"
    assert pipeline[0]["status"] == "IMPLEMENTED_OFFLINE"
    assert "Never pool CS1/CS2" in pipeline[0]["fail_closed"]
    assert "position_balanced_v3_photo_analyzer" in pipeline[1]["component"]
    assert "binocular camera" in pipeline[1]["fail_closed"]
    assert pipeline[2]["component"] == "host.static_photo.controller_palette_inventory"
    assert "fresh-white reconstruction" in pipeline[2]["fail_closed"]
    assert pipeline[3]["component"] == "host.static_photo.v3_lightness_workflow"
    assert (
        pipeline[4]["component"] == "host.static_photo.position_balanced_hold_compare"
    )
    assert "missing probes" in pipeline[4]["fail_closed"]
    assert pipeline[5]["component"] == "host.static_photo.fresh_reconstruction_compare"
    assert "recipes lacking all four visible replicas" in pipeline[5]["fail_closed"]
    assert pipeline[6]["component"] == "host.static_photo.lightness_family_plan"
    assert "unready families are excluded" in pipeline[6]["fail_closed"]
    assert pipeline[7]["component"] == "host.static_photo.multi_lut_hold_schedule"
    assert pipeline[8]["component"] == "static-photo palette and pixel mapping"
    assert pipeline[9]["component"] == "host.static_photo.fixed_photo_execution"
    assert "runtime raw frame" in pipeline[9]["fail_closed"]
    assert pipeline[10]["component"] == "host.static_photo.function_first_orchestrator"
    assert (
        "one ready family unlocks only its limited subset"
        in pipeline[10]["fail_closed"]
    )


def test_lightness_fallbacks_do_not_become_unknown_lut_sweeps() -> None:
    payload = _load()
    mechanisms = {item["id"]: item for item in payload["lightness_mechanism_paths"]}
    assert mechanisms["M1"]["status"] == "ACTIVE_NEXT_IN_F1"
    assert mechanisms["M2"]["status"] == "REQUIRED_AFTER_F1_HIT"
    assert mechanisms["M3"]["mechanism"] == "fresh_white_reconstruction"
    assert mechanisms["M6"]["status"] == "HIGH_RISK_DEFERRED"
    assert payload["deferred_work"]["unknown_register_or_lut_command_sweep"] == (
        "PROHIBITED"
    )


def test_first_mechanism_generalizes_over_stable_hues_before_new_hue_search() -> None:
    payload = _load()
    stage = next(item for item in payload["stages"] if item["id"] == "F4A")
    assert stage["new_hue_enumeration"] is False
    assert stage["status"] == (
        "OFFLINE_FRAMEWORK_IMPLEMENTED_WAITING_FOR_FIRST_MECHANISM_HIT"
    )
    assert stage["software_component"] == "host.static_photo.lightness_family_plan"
    assert stage["partial_palette_subset_allowed"] is True
    assert stage["per_hue_required_gates"] == [
        "controller_local_lightness_screen",
        "local_hold",
        "fresh_white_reconstruction",
        "factory_white_recovery",
    ]


def test_f1_offline_identity_and_recovery_successor_are_frozen() -> None:
    stage = next(item for item in _load()["stages"] if item["id"] == "F1")
    assert "OFFLINE_AUDIT_PASS" in stage["status"]
    assert stage["contract_id"] == (
        "a114a46bec02b5de80c1f63757723e90cf8e101a81429a8f47eabadc471e3b88"
    )
    assert stage["firmware_sha256"] == (
        "f19eca9e771dedb1c62c25ae017e602bf25ef31f0086aeb26f65bd4575353b22"
    )
    assert stage["white_successor_firmware_sha256"] == (
        "3acadd182c2579e0a45015750cdb73ccddea51358a4068a7dfa4fba333125b1a"
    )
    assert stage["offline_sha256_manifest_entries"] == 31


def test_fixed_photo_execution_is_a_separate_fail_closed_stage() -> None:
    stage = next(item for item in _load()["stages"] if item["id"] == "F7")
    assert stage["status"].startswith("OFFLINE_BUNDLE_FRAMEWORK_IMPLEMENTED")
    assert stage["software_component"] == "host.static_photo.fixed_photo_execution"
    assert stage["runtime_raw_frame_ingress"] is False
    assert stage["dynamic_lut_or_payload_ingress"] is False
    assert stage["required_gates"][-1] == "independent_factory_otp_white_successor"


def test_candidate_hold_successor_is_sealed_without_claiming_live_hold() -> None:
    stage = next(item for item in _load()["stages"] if item["id"] == "F4")
    assert "OFFLINE_AUDIT_PASS" in stage["status"]
    assert stage["contract_id"] == (
        "329e0bb6075291cc2bbdc1045a642b055b06fb8d312d2a7761b1332358e04229"
    )
    assert stage["firmware_sha256"] == (
        "5a0d80b7391ae8f171747a1505521ff7193757bef86bf5e34bfb1f5be2d95db8"
    )
    assert stage["candidate_cells_retained"] == 128
    assert stage["probe_windows_outside_candidate_grid"] is True
    assert stage["comparison_component"] == (
        "host.static_photo.position_balanced_hold_compare"
    )
    assert "exact F1 G3 COMPLETE" in stage["remaining_gate"]


def test_fresh_reconstruction_firmware_and_white_successor_are_sealed() -> None:
    stage = next(item for item in _load()["stages"] if item["id"] == "F3")
    assert "RECONSTRUCTION_MAIN_WHITE_SUCCESSOR_SEALED" in stage["status"]
    assert stage["contract_id"] == (
        "5d76fda3bf199d29538ec0c6555db4a294b6b11ffb5805613805b4f759b7d132"
    )
    assert stage["firmware_sha256"] == (
        "9b8493903baa1c656cf387481a52f217293d2f2ccedb09afebd2cdeda400f2a3"
    )
    assert stage["white_successor_firmware_sha256"] == (
        "e78cd7b18d8c020d09f1fc554cd4f0f2063cfcd8c3b590391ed637b0260bba45"
    )
    assert stage["offline_sha256_manifest_entries"] == 24
