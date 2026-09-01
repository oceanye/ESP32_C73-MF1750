from __future__ import annotations

from copy import deepcopy

import pytest

from host.static_photo.common import canonical_sha256, verify_integrity
from host.static_photo.v3_lightness_workflow import (
    V3LightnessWorkflowError,
    build_v3_lightness_hold_repeat_white_workflow,
)


ANALYSIS_FILE_SHA = "a" * 64
REPEAT_FILE_SHA = "b" * 64


def _seal_external(value: dict) -> dict:
    result = deepcopy(value)
    result["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": canonical_sha256(result),
    }
    return result


def _analysis(
    cs1_l: tuple[float, ...],
    cs2_l: tuple[float, ...],
    *,
    decision: str = "REVIEW_CONTROLLER_LOCAL_LIGHTNESS_SIGNAL_REPEAT_NEEDED",
    exposure: float = -6.0,
) -> dict:
    assert len(cs1_l) == len(cs2_l) == 8
    cells = []
    for controller, levels in (("CS1", cs1_l), ("CS2", cs2_l)):
        for row in range(8):
            for column in range(8):
                code = (row + column) % 8
                cells.append(
                    {
                        "controller": controller,
                        "controller_role": "TEST_CONTROLLER_LOCAL",
                        "physical_row": row,
                        "physical_column": column,
                        "logical_row": row,
                        "logical_column": column,
                        "decoder_transform": "identity",
                        "recipe_id": f"cell-{controller}-{row}-{column}",
                        "middle_code": code,
                        "illumination_normalized_camera_relative_lab": [
                            levels[code],
                            12.0,
                            -28.0,
                        ],
                        "center_rgb_mad": [1.0, 1.0, 1.0],
                        "center_all_channels_low_clip_fraction": 0.0,
                        "center_any_channel_high_clip_fraction": 0.0,
                        "bottom_edge_stripe": "CLEAR",
                    }
                )
    return _seal_external(
        {
            "schema_version": 1,
            "kind": (
                "mf1750-stable-code0-luma-latin-v3-camera-relative-photo-analysis"
            ),
            "campaign_id": "EC5_STABLE_CODE0_LUMA_LATIN_V3",
            "test_id": "EC5-STABLE-CODE0-LUMA-LATIN-V3",
            "contract_id": (
                "472cb28efa39538963cc94da3d8442f2a0e35603fdd41f38eb973bcb600f8302"
            ),
            "stage": "L3",
            "decision": decision,
            "source_capture_sidecar": {
                "camera_usb_identity": "VID_32E4:PID_4801",
                "capture_binding": "live_synchronized",
                "requested_settings": {"exposure": exposure},
                "effective_settings_before_frame": {"exposure": exposure},
                "effective_settings_after_frame": {"exposure": exposure},
            },
            "method": {
                "controllers_pooled": False,
                "cs1_cs2_colour_equivalence_claimed": False,
                "absolute_colour_claimed": False,
            },
            "quality_thresholds": {
                "maximum_all_channels_low_clip_fraction": 0.02,
                "maximum_any_channel_high_clip_fraction": 0.005,
                "maximum_center_rgb_mad": 6.0,
            },
            "capture_quality": {
                "both_controller_rois_visible": "PASS",
                "exposure_usable": "PASS",
                "focus_usable": "PASS",
                "glare_not_material": "PASS",
                "single_pixel_fill_coarse_uniformity_pass": True,
            },
            "controller_results": {
                controller: {
                    "controller": controller,
                    "controller_local_only": True,
                }
                for controller in ("CS1", "CS2")
            },
            "cells": cells,
            "qualification_boundary": {
                "review_candidates_only": True,
                "qualified_colour_count": 0,
                "qualified_gray_levels": 0,
                "persistence_proven": False,
                "cross_controller_equivalence_proven": False,
                "camera_relative_only": True,
            },
            "hardware_accessed": False,
            "camera_accessed": False,
            "network_requests": 0,
        }
    )


def _repeat(analysis: dict, *, cs1_pass: bool, cs2_pass: bool) -> dict:
    return _seal_external(
        {
            "schema_version": 1,
            "kind": (
                "mf1750-stable-code0-luma-latin-v3-l3-l4-"
                "camera-relative-repeat-comparison"
            ),
            "campaign_id": "EC5_STABLE_CODE0_LUMA_LATIN_V3",
            "test_id": "EC5-STABLE-CODE0-LUMA-LATIN-V3",
            "contract_id": (
                "472cb28efa39538963cc94da3d8442f2a0e35603fdd41f38eb973bcb600f8302"
            ),
            "decision": "REVIEW_REPEAT_SCREEN",
            "source_reports": {
                "L3": {
                    "path": "synthetic-l3-analysis.json",
                    "bytes": 1000,
                    "sha256": ANALYSIS_FILE_SHA,
                    "canonical_integrity_sha256": analysis["integrity"]["sha256"],
                },
                "L4": {
                    "path": "synthetic-l4-analysis.json",
                    "bytes": 1000,
                    "sha256": "d" * 64,
                    "canonical_integrity_sha256": "e" * 64,
                },
            },
            "comparability": {
                "analysis_method_equal": True,
                "analysis_thresholds_equal": True,
                "camera_settings_except_exposure_equal": True,
                "camera_exposure_equal": False,
                "l3_requested_exposure": -6.0,
                "l4_requested_exposure": -4.0,
                "controller_local_centered_lightness_comparison_used": True,
                "cross_controller_comparison_used": False,
                "raw_absolute_lab_repeat_comparable": False,
            },
            "controller_results": {
                "CS1": {
                    "controller": "CS1",
                    "controller_local_only": True,
                    "centered_lightness_repeat_gate_pass": cs1_pass,
                    "raw_absolute_lab_repeat_claimed": False,
                },
                "CS2": {
                    "controller": "CS2",
                    "controller_local_only": True,
                    "centered_lightness_repeat_gate_pass": cs2_pass,
                    "raw_absolute_lab_repeat_claimed": False,
                },
            },
            "quality_gate_pass": True,
            "bottom_edge_clear_in_both_captures": True,
            "qualification_boundary": {
                "repeatable_signal_is_not_a_qualified_gray_level": True,
                "qualified_colour_count": 0,
                "qualified_gray_levels": 0,
                "absolute_colour_claimed": False,
                "cross_controller_equivalence_claimed": False,
                "same_exposure_repeat_proven": False,
                "persistence_proven": False,
            },
            "hardware_accessed": False,
            "camera_accessed": False,
            "network_requests": 0,
        }
    )


def _same_exposure_repeat(
    analysis: dict,
    *,
    cs1_pass: bool,
    cs2_pass: bool,
    bottom_edge_clear: bool,
) -> dict:
    result = _repeat(analysis, cs1_pass=cs1_pass, cs2_pass=cs2_pass)
    result = deepcopy(result)
    result.pop("integrity")
    result["decision"] = (
        "REVIEW_CS2_LIGHTNESS_SIGNAL_NOT_REPEATABLE_OR_NOT_PRESENT_"
        "WITH_EDGE_UNCERTAINTY"
    )
    result["comparability"] = {
        "analysis_method_equal": True,
        "analysis_thresholds_equal": True,
        "exact_by_field": {
            "requested_settings": True,
            "effective_settings_before_frame": True,
            "effective_settings_after_frame": True,
        },
        "except_exposure_equal_by_field": {
            "requested_settings": True,
            "effective_settings_before_frame": True,
            "effective_settings_after_frame": True,
        },
        "exposure_equal_by_field": {
            "requested_settings": True,
            "effective_settings_before_frame": True,
            "effective_settings_after_frame": True,
        },
        "camera_settings_exactly_equal": True,
        "camera_settings_except_exposure_equal": True,
        "camera_exposure_equal": True,
        "l3_requested_exposure": -4.0,
        "l4_requested_exposure": -4.0,
        "raw_absolute_lab_repeat_comparable": True,
        "controller_local_centered_lightness_comparison_used": True,
        "cross_controller_comparison_used": False,
    }
    result["bottom_edge_clear_in_both_captures"] = bottom_edge_clear
    result["qualification_boundary"]["same_exposure_repeat_proven"] = True
    return _seal_external(result)


def _build(analysis: dict, repeat: dict | None = None) -> dict:
    return build_v3_lightness_hold_repeat_white_workflow(
        analysis,
        analysis_file_sha256=ANALYSIS_FILE_SHA,
        repeat_comparison=repeat,
        repeat_comparison_file_sha256=(REPEAT_FILE_SHA if repeat else None),
    )


def test_review_with_zero_qualification_stays_empty_and_white_only() -> None:
    report = _build(_analysis((40.0,) * 8, (52.0,) * 8))
    verify_integrity(report, "V3 workflow")
    assert report["shortlist"]["candidate_count"] == 0
    assert report["shortlist"]["qualified_colour_count"] == 0
    assert report["shortlist"]["qualified_gray_level_count"] == 0
    assert report["shortlist"]["qualified_lightness_level_count"] == 0
    assert report["evidence_plan"]["status"] == "NO_SHORTLIST_WHITE_CONTAINMENT_ONLY"
    assert [item["status"] for item in report["evidence_plan"]["steps"]] == [
        "SKIPPED_EMPTY_SHORTLIST",
        "SKIPPED_EMPTY_SHORTLIST",
        "SKIPPED_EMPTY_SHORTLIST",
        "REQUIRED_CAMPAIGN_CONTAINMENT",
    ]
    assert report["feature_priority"]["hue_enumeration"] == "DEFERRED"


def test_cross_controller_difference_is_never_a_lightness_candidate() -> None:
    report = _build(_analysis((25.0,) * 8, (75.0,) * 8))
    assert report["shortlist"]["candidate_count"] == 0
    assert len(report["controller_local_lightness_screen"]["groups"]) == 2
    assert (
        report["evidence_boundaries"]["cross_controller_difference_counts_as_lightness"]
        is False
    )


def test_coarse_candidate_plans_fresh_white_reconstruction_chain() -> None:
    report = _build(
        _analysis(
            (35.0, 55.0, 35.0, 35.0, 35.0, 35.0, 35.0, 35.0),
            (45.0,) * 8,
        )
    )
    assert report["shortlist"]["candidate_count"] == 8
    assert report["shortlist"]["by_controller"]["CS2"] == []
    records = report["shortlist"]["by_controller"]["CS1"]
    assert all(
        item["qualification_state"] == "COARSE_CANDIDATE_ONLY" for item in records
    )
    assert all(
        "pending:controller-local-hold" in item["blocking_reasons"] for item in records
    )
    assert all(item["candidate"]["target_repeat_count"] == 1 for item in records)
    assert (
        report["candidate_inventory_preview"]["controller_local_qualified_recipe_count"]
        == 0
    )
    assert report["evidence_plan"]["ordered_roles"] == [
        "CONTROLLER_LOCAL_HOLD_VALIDATION",
        "INDEPENDENT_FACTORY_OTP_WHITE_BASELINE",
        "FRESH_WHITE_RECONSTRUCTION_REPEAT",
        "FINAL_FACTORY_OTP_WHITE_CONTAINMENT",
    ]
    assert [item["status"] for item in report["evidence_plan"]["steps"]] == [
        "REQUIRED",
        "BLOCKED_UNTIL_HOLD_PASS",
        "BLOCKED_UNTIL_INDEPENDENT_WHITE_BASELINE_PASS",
        "REQUIRED_CAMPAIGN_CONTAINMENT",
    ]
    reconstruction = report["evidence_plan"]["steps"][2]
    assert reconstruction["must_start_from_independent_factory_otp_white_baseline"]
    assert reconstruction["reexecute_full_colour_construction_chain"]
    assert reconstruction["in_place_identical_target_repeat_allowed"] is False
    assert reconstruction["original_candidate_overwrite_allowed"] is False
    assert (
        report["evidence_boundaries"]["identical_target_repeat_after_hold_planned"]
        is False
    )
    assert report["evidence_plan"]["live_authorized"] is False


def test_failed_controller_local_repeat_screen_empties_that_shortlist() -> None:
    analysis = _analysis(
        (35.0, 55.0, 35.0, 35.0, 35.0, 35.0, 35.0, 35.0),
        (45.0,) * 8,
    )
    report = _build(analysis, _repeat(analysis, cs1_pass=False, cs2_pass=True))
    assert report["shortlist"]["candidate_count"] == 0
    assert report["shortlist"]["excluded_after_repeat_screen_by_controller"]["CS1"]
    assert (
        report["evidence_boundaries"][
            "repeat_comparison_auto_creates_qualification_evidence"
        ]
        is False
    )


def test_passing_repeat_screen_still_requires_fresh_reconstruction_chain() -> None:
    analysis = _analysis(
        (35.0, 55.0, 35.0, 35.0, 35.0, 35.0, 35.0, 35.0),
        (45.0,) * 8,
    )
    report = _build(analysis, _repeat(analysis, cs1_pass=True, cs2_pass=True))
    assert report["shortlist"]["candidate_count"] == 8
    assert report["shortlist"]["qualified_lightness_level_count"] == 0
    assert report["evidence_plan"]["steps"][0]["status"] == "REQUIRED"
    assert report["evidence_plan"]["steps"][1]["prior_hold_pass_required"] is True
    assert report["evidence_plan"]["steps"][2]["status"] == (
        "BLOCKED_UNTIL_INDEPENDENT_WHITE_BASELINE_PASS"
    )


def test_same_exposure_schema_with_edge_uncertainty_stays_empty() -> None:
    analysis = _analysis(
        (35.0, 55.0, 35.0, 35.0, 35.0, 35.0, 35.0, 35.0),
        (45.0,) * 8,
        exposure=-4.0,
    )
    repeat = _same_exposure_repeat(
        analysis,
        cs1_pass=True,
        cs2_pass=False,
        bottom_edge_clear=False,
    )
    report = _build(analysis, repeat)
    assert report["repeat_comparison"]["comparison_mode"] == (
        "SAME_EXPOSURE_RAW_AND_CONTROLLER_CENTERED"
    )
    assert report["repeat_comparison"]["l3_requested_exposure"] == -4.0
    assert report["repeat_comparison"]["l4_requested_exposure"] == -4.0
    assert report["shortlist"]["candidate_count"] == 0
    assert report["shortlist"]["qualified_colour_count"] == 0
    assert report["shortlist"]["qualified_gray_level_count"] == 0
    assert report["evidence_plan"]["status"] == ("NO_SHORTLIST_WHITE_CONTAINMENT_ONLY")


def test_same_exposure_schema_rejects_l3_exposure_mismatch() -> None:
    analysis = _analysis(
        (35.0, 55.0, 35.0, 35.0, 35.0, 35.0, 35.0, 35.0),
        (45.0,) * 8,
        exposure=-6.0,
    )
    repeat = _same_exposure_repeat(
        analysis,
        cs1_pass=True,
        cs2_pass=False,
        bottom_edge_clear=False,
    )
    with pytest.raises(V3LightnessWorkflowError, match="L3 requested exposure"):
        _build(analysis, repeat)


def test_same_exposure_schema_rejects_inexact_camera_settings() -> None:
    analysis = _analysis(
        (35.0, 55.0, 35.0, 35.0, 35.0, 35.0, 35.0, 35.0),
        (45.0,) * 8,
        exposure=-4.0,
    )
    repeat = _same_exposure_repeat(
        analysis,
        cs1_pass=True,
        cs2_pass=False,
        bottom_edge_clear=False,
    )
    repeat = deepcopy(repeat)
    repeat.pop("integrity")
    repeat["comparability"]["camera_settings_exactly_equal"] = False
    repeat = _seal_external(repeat)
    with pytest.raises(
        V3LightnessWorkflowError,
        match="same-exposure repeat comparison boundary",
    ):
        _build(analysis, repeat)


def test_spatial_dithering_is_rejected() -> None:
    analysis = _analysis((40.0,) * 8, (40.0,) * 8)
    analysis = deepcopy(analysis)
    analysis.pop("integrity")
    analysis["cells"][0]["spatial_dithering_used"] = True
    analysis = _seal_external(analysis)
    with pytest.raises(V3LightnessWorkflowError, match="spatial dithering"):
        _build(analysis)


def test_wrong_camera_identity_is_rejected() -> None:
    analysis = _analysis((40.0,) * 8, (40.0,) * 8)
    analysis = deepcopy(analysis)
    analysis.pop("integrity")
    analysis["source_capture_sidecar"]["camera_usb_identity"] = "VID_1BCF:PID_0B15"
    analysis = _seal_external(analysis)
    with pytest.raises(V3LightnessWorkflowError, match="camera USB identity"):
        _build(analysis)


def test_unearned_input_qualification_claim_is_rejected() -> None:
    analysis = _analysis((40.0,) * 8, (40.0,) * 8)
    analysis = deepcopy(analysis)
    analysis.pop("integrity")
    analysis["qualification_boundary"]["qualified_gray_levels"] = 1
    analysis = _seal_external(analysis)
    with pytest.raises(V3LightnessWorkflowError, match="qualification claim"):
        _build(analysis)


def test_tampered_analysis_integrity_is_rejected() -> None:
    analysis = _analysis((40.0,) * 8, (40.0,) * 8)
    analysis["decision"] = "TAMPERED"
    with pytest.raises(V3LightnessWorkflowError, match="canonical SHA-256"):
        _build(analysis)


def test_repeat_source_binding_is_exact() -> None:
    analysis = _analysis(
        (35.0, 55.0, 35.0, 35.0, 35.0, 35.0, 35.0, 35.0),
        (45.0,) * 8,
    )
    repeat = _repeat(analysis, cs1_pass=True, cs2_pass=True)
    repeat = deepcopy(repeat)
    repeat.pop("integrity")
    repeat["source_reports"]["L3"]["sha256"] = "c" * 64
    repeat = _seal_external(repeat)
    with pytest.raises(V3LightnessWorkflowError, match="L3 source binding"):
        _build(analysis, repeat)
