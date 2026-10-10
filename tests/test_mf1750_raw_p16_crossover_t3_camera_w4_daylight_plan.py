from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools import (
    mf1750_raw_p16_crossover_t3_camera_w4_daylight_plan as plan,
)


@pytest.fixture(scope="module")
def frozen_plan() -> dict:
    # Authority and artifact verification is intentionally expensive.  One
    # module-scoped deep build is enough for all structural assertions below.
    return plan.build_plan()


def test_plan_binds_frozen_t3_w4_and_exact_48mp_profile(
    frozen_plan: dict,
) -> None:
    value = frozen_plan

    assert value["offline_only"] is True
    assert value["hardware_accessed"] is False
    assert value["camera_accessed"] is False
    assert value["device_network_accessed"] is False
    assert value["serial_or_com_accessed"] is False
    assert value["relay_accessed"] is False
    assert value["firmware_flashed"] is False
    assert value["display_refreshed"] is False

    t3 = value["firmware"]["t3"]
    w4 = value["firmware"]["w4"]
    assert (
        t3["contract_id"]
        == "714ddf2e44725361e9b404ce512d9c9a96a96d7b31cce8bfbd4555d0883e9e19"
    )
    assert (
        t3["action_id"]
        == "db009936f341cd612be9aa47d08a0a316ec2c581c3c88d35d089ce3fa5857104"
    )
    assert (
        t3["descriptor_id"]
        == "52de5c169b19bf7db2788f73e2c450971bb6adffb7c305cb0dd8d7873b9b3af9"
    )
    assert (
        w4["contract_id"]
        == "7edf2e1916d536aa8b7d6d77be19899aab4fc6816e8c48de1e1b621bff0b7d52"
    )
    assert (
        w4["action_id"]
        == "e621ea9a05da45da4a120c2b68fbdefcad5f4a48274a5ac5290f5fcc25d7c55b"
    )
    assert (
        w4["descriptor_id"]
        == "398b8a86224185b6c6ca7b2d49bc83861f64f2a8c69afa03fbb430b9077c1f45"
    )
    assert value["firmware"]["w4_exact_t3_source_quartet"] == {
        "campaign_id": t3["campaign_id"],
        "contract_id": t3["contract_id"],
        "descriptor_id": t3["descriptor_id"],
        "action_id": t3["action_id"],
    }
    assert t3["bin"] == {
        "path": t3["bin"]["path"],
        "bytes": 805_232,
        "sha256": "05c00d71a163ecfc22d0d333404ac8967eaa06b929003ce0c28dda7499615760",
        "verified_from_disk": True,
    }
    assert t3["elf"] == {
        "path": t3["elf"]["path"],
        "bytes": 13_299_376,
        "sha256": "89d20faec2d5bde42915a5fe30515c917f722ca06777b016a75c38020e83a56e",
        "verified_from_disk": True,
    }
    assert w4["bin"] == {
        "path": w4["bin"]["path"],
        "bytes": 787_248,
        "sha256": "9f3ab672c214cdf128a01a51b2803d5a586f72fab1cad065373eead30ee63bf7",
        "verified_from_disk": True,
    }
    assert w4["elf"] == {
        "path": w4["elf"]["path"],
        "bytes": 13_214_976,
        "sha256": "16b37334ef8142ad33a8856dcf2850f751a8cf80489152766b8dc0602e278118",
        "verified_from_disk": True,
    }

    camera = value["camera_contract"]
    assert camera["target"]["usb_vid"] == "32E4"
    assert camera["target"]["usb_pid"] == "4801"
    assert camera["target"]["excluded_camera"] == {
        "friendly_name": "dual-lens USB Camera",
        "usb_vid": "1BCF",
        "usb_pid": "0B15",
    }
    assert camera["profile"]["frame_width"] == 4000
    assert camera["profile"]["frame_height"] == 3000
    assert camera["profile"]["fourcc"] == "MJPG"
    assert camera["profile"]["exposure"] == -6.0
    assert camera["profile"]["fresh_v2_exposure_minus_3_profile_permitted"] is False
    assert camera["total_required_frames"] == 5
    assert camera["output_root"] == (
        ".test-output/hardware/"
        "MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_"
        "CAMERA_DAYLIGHT_V1"
    )
    assert camera["post_white_output_root"] == (
        ".test-output/hardware/"
        "MF1750_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_"
        "WHITE_CAMERA_DAYLIGHT_V1"
    )
    assert camera["formal_attempt_claimed_before_camera_open"] is True
    assert camera["panel_corners_bound_after_acquisition_to_same_photo"] is True
    assert camera["setup_only_view_gate"] == {
        "required_before_formal_w3": True,
        "formal_evidence": False,
        "may_supply_formal_corners": False,
        "maximum_attempts": 2,
    }
    sources = camera["implementation_sources"]
    assert set(sources) == {
        "t3_capture_pack",
        "w4_post_white_capture",
        "camera_evidence",
        "camera_observation",
        "human_observation_and_comparison",
    }
    assert all(binding["verified_from_disk"] is True for binding in sources.values())
    assert all(binding["bytes"] > 0 for binding in sources.values())
    assert all(len(binding["sha256"]) == 64 for binding in sources.values())
    assert sources["t3_capture_pack"]["path"] == plan.T3_CAPTURE_TOOL
    assert sources["w4_post_white_capture"]["path"] == (plan.W4_POST_WHITE_CAPTURE_TOOL)
    ca_reference = value["source_authorities"]["t2_ca_human_screen_reference"]
    assert ca_reference["path"] == plan.CA_HUMAN_REFERENCE
    assert ca_reference["reported_ca_baseline_match"] is True
    assert ca_reference["four_replicates_consistent_and_stable"] is True
    assert ca_reference["controls_pass"] is True
    assert ca_reference["human_screen_reference_ready"] is True
    assert ca_reference["verified_from_disk"] is True


def test_order_keeps_atlas_off_and_sealed_before_w4(frozen_plan: dict) -> None:
    value = frozen_plan
    machine = value["state_machine"]
    steps = machine["steps"]
    assert [step["ordinal"] for step in steps] == list(range(1, 15))
    assert [step["id"] for step in steps] == [
        "SETUP_ONLY_CAMERA_VIEW_GATE",
        "ACQUIRE_W3_PRE_WHITE",
        "ADMIT_W3_PRE_WHITE_FROM_SAME_JPEG",
        "INSTALL_AND_DIAGNOSE_T3",
        "EXECUTE_T3_ONCE",
        "POWER_OFF_AND_ENTER_T3_CAPTURE_HOLD",
        "ACQUIRE_ADMIT_T3_SEQUENTIALLY",
        "SEAL_T3_CAPTURE_SET",
        "SCREEN_T3_AND_BIND_HUMAN_DECISION_INPUT",
        "INSTALL_AND_DIAGNOSE_W4",
        "EXECUTE_W4_WHITE_ONCE",
        "POWER_OFF_AND_ACQUIRE_W4_WHITE",
        "ADMIT_AND_SEAL_W4_WHITE_FROM_SAME_JPEG",
        "ANALYZE_AND_REPORT_OFFLINE",
    ]
    assert machine["total_visible_refresh_budget"] == 2
    assert machine["explicit_resume_required_before_each_visible_action"] is True
    assert machine["visible_action_retry_budget"] == 0
    assert machine["visible_action_recovery_budget"] == 0
    assert machine["visible_action_autochain_budget"] == 0
    assert machine["bounded_camera_attempts_are_read_only_not_action_retries"] is True
    assert machine["capture_bytes_seal_required_before_w4"] is True
    assert machine["camera_classification_required_before_w4"] is False
    assert machine["human_profile_decision_required_before_w4"] is False
    assert steps[0]["formal_evidence"] is False
    assert steps[0]["consumes_formal_capture_attempt"] is False
    assert steps[1]["attempt_claim_timing"] == "BEFORE_CAMERA_OPEN"
    assert steps[1]["panel_corners_required_at_acquire"] is False
    assert steps[2]["same_jpeg_corner_binding_required"] is True
    assert steps[5]["camera_access"] == 0
    assert steps[5]["success"] == "T3_ATLAS_RETAINED_WITH_RELAY_COMMANDED_OFF"
    assert steps[6]["maximum_capture_attempts"] == 5
    assert steps[6]["failure"].startswith("KEEP_RELAY_OFF_RETAIN_ATLAS")
    assert steps[6]["same_jpeg_corner_binding_required"] is True
    assert steps[6]["sequence_rule"].startswith("EACH_ACQUIRE_MUST_REACH")
    assert steps[8]["camera_only_may_decide_profile_vs_physical_side"] is False
    assert steps[8]["w4_safety_containment_blocked_by_missing_human_seed"] is False
    assert "T3_CAPTURE_SET_SEALED" in steps[9]["requires"]
    assert steps[10]["mutation_budget"] == {
        "arm": 1,
        "execute": 1,
        "driver": 1,
        "visible_refresh": 1,
        "retry": 0,
        "recovery": 0,
        "autochain": 0,
    }
    assert steps[4]["mutation_budget"]["retry"] == 0
    assert steps[4]["mutation_budget"]["recovery"] == 0
    assert steps[4]["mutation_budget"]["autochain"] == 0
    assert steps[3]["mutation_budget"]["write_before"] == "default_reset"
    assert steps[3]["mutation_budget"]["verify_after"] == "hard_reset"
    assert steps[3]["mutation_budget"]["extra_or_manual_reset"] == 0
    assert steps[9]["mutation_budget"]["write_before"] == "default_reset"
    assert steps[9]["mutation_budget"]["verify_after"] == "hard_reset"
    assert steps[9]["mutation_budget"]["extra_or_manual_reset"] == 0
    assert steps[11]["maximum_attempts"] == 2
    assert steps[11]["attempt_claim_timing"] == "BEFORE_CAMERA_OPEN"
    assert steps[12]["same_jpeg_corner_binding_required"] is True
    assert steps[12]["pass_only_admission_and_seal"] is True
    assert steps[12]["review_or_fail_terminal_state"] == "REJECTED"
    assert machine["runner_busy_gate"] == {
        "placement": (
            "INSIDE_FROZEN_RUNNER_AFTER_EXACT_4_GET_AND_BEFORE_CLAIM_ARM_POST"
        ),
        "raw_busy_required": 1,
        "busy_zero_fails_before_claim_or_post": True,
        "independent_pause_subcommand_available": False,
    }


def test_camera_result_stays_coarse_and_low_confidence_is_review(
    frozen_plan: dict,
) -> None:
    value = frozen_plan["camera_screening"]
    assert value["classification_vocabulary"] == [
        "HUMAN_CAMERA_SCREEN_PASS",
        "HUMAN_CAMERA_SCREEN_REVIEW",
        "HUMAN_CAMERA_SCREEN_FAIL",
    ]
    assert value["low_confidence_result"] == "HUMAN_CAMERA_SCREEN_REVIEW"
    assert (
        value["camera_only_ceiling_without_truthful_t3_human_seed"]
        == "HUMAN_CAMERA_SCREEN_REVIEW"
    )
    assert value["camera_only_may_answer_profile_vs_physical_side"] is False
    assert value["absolute_colour_claimed"] is False
    assert value["formal_colour_gate_evaluated"] is False
    assert value["qualified_colour_count"] == 0
    assert value["profile_following_proven"] is False
    assert value["required_checks"]["panel_geometry"] == "64_CELLS_AND_TWO_4X8_HALVES"
    assert value["required_checks"]["replicates"] == "FOUR_PER_CONTROLLER_CODE"
    assert value["human_escalation"]["required_for_review"] is True
    assert (
        value["human_escalation"]["required_for_primary_profile_vs_side_decision"]
        is True
    )

    decision = frozen_plan["decision_objectives"]
    assert decision["reference_t2_profile_assignment"] == "CS1_C__CS2_A"
    assert decision["candidate_t3_profile_assignment"] == "CS1_A__CS2_C"
    assert decision["camera_only_primary_decision"] == "NOT_EARNED"
    assert "REQUIRES_CURRENT_T3_HUMAN" in decision["earning_rule"]
    assert set(decision["decision_branches"]) == {
        "PROFILE_FOLLOWING_CANDIDATE",
        "PHYSICAL_SIDE_FOLLOWING",
        "UNSTABLE_OR_CONFOUNDED",
    }
    assert decision["absolute_colour_or_palette_qualification_claimed"] is False
    assert decision["qualified_colour_count"] == 0


def test_independent_partial_plan_uses_fixed_dual_3x8_and_earns_no_seals(
    frozen_plan: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Reuse the already deep-validated legacy plan so this structural test does
    # not rehash the large firmware artifacts a second time.
    monkeypatch.setattr(plan, "build_plan", lambda: copy.deepcopy(frozen_plan))
    value = plan.build_partial_plan()

    assert value["kind"] == plan.PARTIAL_KIND
    assert value["mode"] == plan.PARTIAL_MODE
    camera = value["camera_contract"]
    assert camera["coverage_scope"] == "partial_panel"
    assert camera["full_panel_visible"] is False
    assert camera["full_panel_uncropped"] is False
    assert camera["fixed_camera_position_must_not_move"] is True
    assert camera["selected_rows"] == [0, 1, 2]
    assert camera["selected_columns"] == list(range(8))
    assert camera["selected_cells_per_frame"] == 48
    assert camera["replicates_per_code_per_controller_per_frame"] == 3
    assert camera["total_required_frames"] == 4
    assert camera["post_white_required_frames"] == 0
    assert camera["setup_only_view_gate"]["full_screen_test_required"] is False
    assert camera["w4_post_white_camera_seal_authorized"] is False

    screen = value["camera_screening"]
    assert screen["required_checks"]["profile_code_pairs"] == list(range(8))
    assert screen["required_checks"]["normalization"] == (
        "SAME_SIDE_SAME_CELL_W3_WHITE"
    )
    assert screen["required_checks"]["row_3"] == (
        "NOT_EVALUATED_OUTSIDE_SELECTED_ROI"
    )
    assert screen["required_checks"]["bottom_edge"] == (
        "NOT_EVALUATED_OUTSIDE_SELECTED_ROI"
    )
    assert screen["formal_full_panel_evidence"] is False
    assert screen["profile_following_decision_earned"] is False
    assert screen["w4_post_white_full_screen_seal_earned"] is False
    assert screen["evidence_boundary"][
        "partial_pass_may_not_be_promoted_to_formal_full_panel"
    ] is True

    steps = {item["id"]: item for item in value["state_machine"]["steps"]}
    assert steps["POWER_OFF_AND_ACQUIRE_W4_WHITE"]["authorized"] is False
    assert steps["ADMIT_AND_SEAL_W4_WHITE_FROM_SAME_JPEG"]["authorized"] is False
    assert value["tomorrow_terminal_conditions"]["formal_full_panel_evidence"] == (
        "NOT_EARNED"
    )
    assert value["tomorrow_terminal_conditions"]["profile_following_decision"] == (
        "NOT_EARNED"
    )
    assert value["tomorrow_terminal_conditions"]["w4_post_white_camera_seal"] == (
        "NOT_EARNED"
    )

    legacy = frozen_plan
    assert legacy["camera_contract"]["full_panel_visible"] is True
    assert legacy["camera_contract"]["total_required_frames"] == 5
    assert legacy["camera_screening"]["required_checks"]["panel_geometry"] == (
        "64_CELLS_AND_TWO_4X8_HALVES"
    )


def test_integrity_and_deterministic_rebuild_detect_mutation(
    frozen_plan: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = frozen_plan
    assert value["integrity"] == {
        "algorithm": plan.INTEGRITY_ALGORITHM,
        "sha256": value["integrity"]["sha256"],
    }
    unsealed = copy.deepcopy(value)
    expected_digest = unsealed["integrity"]["sha256"]
    unsealed["integrity"] = None
    assert plan.sha256_bytes(plan.canonical_json(unsealed)) == expected_digest

    changed = copy.deepcopy(value)
    changed["camera_contract"]["profile"]["exposure"] = -3.0
    monkeypatch.setattr(plan, "build_plan", lambda: copy.deepcopy(value))
    with pytest.raises(plan.DaylightPlanError, match="deterministic rebuild"):
        plan.validate_plan(changed)


def test_built_plan_does_not_alias_mutable_camera_declarations() -> None:
    first = plan.build_plan()
    first["camera_contract"]["profile"]["exposure"] = -3.0
    first["camera_contract"]["target"]["usb_vid"] = "1BCF"

    rebuilt = plan.build_plan()
    assert rebuilt["camera_contract"]["profile"]["exposure"] == -6.0
    assert rebuilt["camera_contract"]["target"]["usb_vid"] == "32E4"


def test_write_is_o_excl_and_strict_loader_rejects_duplicate_keys(
    tmp_path: Path, frozen_plan: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(plan, "build_plan", lambda: copy.deepcopy(frozen_plan))
    output = tmp_path / "plan.json"
    written = plan.write_plan(output)
    assert plan.load_and_validate(output) == written
    with pytest.raises(plan.DaylightPlanError, match="refusing to overwrite"):
        plan.write_plan(output)

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    with pytest.raises(plan.DaylightPlanError, match="strict UTF-8 JSON"):
        plan.load_and_validate(duplicate)


def test_artifact_byte_change_fails_closed_before_plan_creation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bad_bin = tmp_path / "firmware.bin"
    bad_elf = tmp_path / "firmware.elf"
    bad_bin.write_bytes(b"not-the-frozen-bin")
    bad_elf.write_bytes(b"not-the-frozen-elf")
    monkeypatch.setattr(plan.t3, "artifact_paths", lambda: (bad_bin, bad_elf))
    with pytest.raises(plan.DaylightPlanError, match="bin artifact differs"):
        plan.build_plan()


def test_module_exposes_no_live_operation_surface() -> None:
    forbidden = {
        "capture",
        "flash",
        "reset",
        "command_relay_on",
        "command_relay_off",
        "run_t3",
        "run_w4",
    }
    assert forbidden.isdisjoint(vars(plan))
    source = Path(plan.__file__).read_text(encoding="utf-8")
    assert "import requests" not in source
    assert "import serial" not in source
    assert "import cv2" not in source


def test_serialized_plan_has_no_nan(frozen_plan: dict) -> None:
    payload = json.dumps(frozen_plan, allow_nan=False)
    assert "NaN" not in payload
