"""Offline, controller-local lightness tests; never grants hardware or slot admission.

Uniform patches measure a single-pixel recipe, not spatially mixed colours.
This module consumes derived measurements; it does not capture or drive a panel.
"""

from __future__ import annotations

from copy import deepcopy
from itertools import combinations
import math
from statistics import median
from typing import Any, Mapping, Sequence

from host.color_pipeline.color import delta_e_ciede2000
from .common import attach_integrity, finite_triple, require_sha256, require_text


VERSION = "MF1750_LIGHTNESS_TEST_V1_20260911"
DATA_KIND = "mf1750-lightness-test-observations-v1"
POSITIONS = ("TL", "TR", "BL", "BR")
CONTROLLERS = ("CS1", "CS2")
LEVEL_COUNTS = (3, 5, 10)
# Experimental screening criteria, NOT manufacturer specifications. Reuse P2's
# 2 L*/3 DE00/5 degree and 3 L*/5 DE76 position bounds; add all-quadrant checks.
THRESHOLDS = {
    "version": VERSION,
    "scope": "offline optical screening only; not a live admission gate",
    "manufacturer_specification": False,
    "minimum_delta_lstar": 2.0,
    "minimum_delta_e00": 3.0,
    "maximum_hue_difference_degrees": 5.0,
    "minimum_chroma_exclusive": 8.0,
    "position_p95_absolute_delta_lstar_maximum": 3.0,
    "position_p95_delta_e76_maximum": 5.0,
    "noise_sample_count_minimum": 10,
    "noise_formula": "max(5*MAD, ci95_half_width) for each ROI; pair uses max of both ROIs",
    "pair_rule": "median AND each matching quadrant; all pairs in ladder share hue",
    "pair_noise_rule": "both delta_L and delta_E00 must exceed their own noise bound",
    "cross_controller_delta_lstar_maximum": 3.0,
    "cross_controller_delta_e76_maximum": 5.0,
    "cross_controller_hue_difference_maximum": 5.0,
    "thresholds_lowered_for_5_or_10_levels": False,
}


class LightnessTestError(ValueError):
    """Malformed evidence, incompatible identities, or duplicate observations."""


def _number(value: object, label: str, *, minimum: float = 0.0) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum:
        raise LightnessTestError(f"{label} must be finite and >= {minimum}")
    return float(value)


def _p95(values: Sequence[float]) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * 0.95
    low = int(index)
    return ordered[low] + (ordered[math.ceil(index)] - ordered[low]) * (index - low)


def _center(labs: Sequence[Sequence[float]]) -> list[float]:
    return [median(lab[i] for lab in labs) for i in range(3)]


def _hue_delta(a: Sequence[float], b: Sequence[float]) -> float | None:
    if (
        min(math.hypot(*a[1:]), math.hypot(*b[1:]))
        <= THRESHOLDS["minimum_chroma_exclusive"]
    ):
        return None  # Neutral-axis tests are a separate family, never coloured ranks.
    difference = (
        abs(math.degrees(math.atan2(a[2], a[1]) - math.atan2(b[2], b[1]))) % 360
    )
    return min(difference, 360 - difference)


def _differences(a: Sequence[float], b: Sequence[float]) -> dict[str, Any]:
    return {
        "delta_lstar": b[0] - a[0],
        "delta_e76": math.dist(a, b),
        "delta_e00": delta_e_ciede2000(a, b),
        "hue_difference_degrees": _hue_delta(a, b),
    }


def _noise(value: Mapping[str, Any]) -> tuple[float, float]:
    n = value.get("sample_count")
    if type(n) is not int or n < THRESHOLDS["noise_sample_count_minimum"]:
        raise LightnessTestError(
            "noise requires at least 10 retained captures, not refreshes"
        )
    return tuple(
        max(
            5 * _number(value.get(f"{metric}_mad"), "MAD"),
            _number(value.get(f"{metric}_ci95_half_width"), "CI"),
        )
        for metric in ("lstar", "delta_e00")
    )


def _pair_pass(difference: Mapping[str, Any], noise_l: float, noise_e: float) -> bool:
    hue = difference["hue_difference_degrees"]
    return (
        hue is not None
        and hue <= THRESHOLDS["maximum_hue_difference_degrees"]
        and difference["delta_lstar"] >= THRESHOLDS["minimum_delta_lstar"]
        and difference["delta_lstar"] > noise_l
        and difference["delta_e00"] >= THRESHOLDS["minimum_delta_e00"]
        and difference["delta_e00"] > noise_e
    )


def build_plan(recipes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Describe existing V3 recipe geometry without generating display payloads."""
    if len(recipes) != 16:
        raise LightnessTestError("history screen requires the existing 16 recipes")
    return attach_integrity(
        {
            "schema_version": 1,
            "kind": "mf1750-lightness-test-plan-v1",
            "test_id": VERSION,
            "goal": {
                "total_slots": 256,
                "neutral_slots": 16,
                "hue_families": 12,
                "tracks_per_family": 2,
                "lightness_ranks_per_track": 10,
                "priority": "coloured same-hue lightness",
                "qualified_slots": 0,
            },
            "level_counts": list(LEVEL_COUNTS),
            "level_counts_are_refresh_repetitions": False,
            "thresholds": deepcopy(THRESHOLDS),
            "history_screen": {
                "recipe_count_per_controller": 16,
                "recipes_per_target_comparison_group": 8,
                "ten_level_screen_requires_additional_distinct_recipes": True,
                "positions_per_recipe": 4,
                "cells_per_controller": 64,
                "total_cells": 128,
                "source": "active C7",
                "middle": "commented C0..C7",
                "target": "active C3 or C7",
                "comparison_groups": ["TARGET_C3", "TARGET_C7"],
                "target_groups_pooled": False,
                "same_hue_not_assumed_from_target_code": True,
                "recipes": deepcopy(list(recipes)),
                "existing_firmware_reference_only": "EC5_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3",
                "fresh_source_rebinding_required": True,
                "old_white_anchor_reusable": False,
                "required_separate_visible_actions_per_construction": 3,
                "actions": ["SOURCE", "MIDDLE", "TARGET"],
                "stop_and_review_after_each_action": True,
                "identical_target_G4_repeat_included": False,
            },
            "frame_rate_branch": {
                "status": "HOLD_FOR_EVIDENCE",
                "selected_test_values": None,
                "existing_complete_tuple_nominal_hz": {"active": 43, "commented": 50},
                "existing_tuples_are_single_variable_comparison": False,
                "prerequisites": [
                    "PWR 0F fixed-bit discrepancy",
                    "base PLL 08 meaning",
                    "OTP single-parameter PWR mode",
                    "effective clock and cascade scope",
                    "panel-specific safe fixed-LUT combination",
                ],
                "live_payloads_generated": False,
            },
            "evaluation_order": [
                "IDENTITY_PROTOCOL",
                "IMAGE_OPTICAL",
                "FOUR_POSITION_ENDPOINTS",
                "SAME_HUE_LADDER",
                "LOCAL_HOLD",
                "FRESH_WHITE_RECONSTRUCTION",
                "RETENTION",
                "CROSS_CONTROLLER",
                "HUMAN_QUALIFICATION_REVIEW",
            ],
            "later_stage_requirements": {
                "LOCAL_HOLD": "separately sealed action; compare protected ROI before/after neighbour refresh",
                "FRESH_WHITE_RECONSTRUCTION": "3 independent fresh-white chains, same recipe and rank direction",
                "RETENTION": "no refresh at 5/60/600 s; same camera/illumination; report raw and derived data",
                "CROSS_CONTROLLER": "both controllers separately pass; optical rank matching; never sum counts",
                "5_AND_10": "require prior 3/5 acceptance evidence; no automatic promotion from a screen",
                "white_recovery_erases_candidate": "normal recovery, not transient evidence",
                "transient_evidence": [
                    "static drift",
                    "neighbour-refresh disturbance",
                    "fresh reconstruction failure",
                ],
                "stage_analyzers_implemented_here": [
                    "four-position screening",
                    "same-hue ladder search",
                ],
                "qualification_reviewer_implemented_here": False,
            },
            "capture": {
                "usb_id": "VID_32E4:PID_4801",
                "baseline_captures": 10,
                "post_target_captures": 10,
                "captures_are_display_refreshes": False,
                "roi": "central 60% of each uniform recipe patch",
                "raw_iso_hardware_trigger": "unknown until capability evidence; retain unsupported as false/null",
                "lab_space": "camera-relative unless independently calibrated",
                "requested_and_effective_settings_kept_separately": True,
            },
            "live_entry": {
                "authorized": False,
                "runner_generated": False,
                "screen_last_observation": "2x4x8 coloured atlas; not a fresh-white anchor",
                "relay_last_record": "OFF",
                "electrical_state_proven": False,
                "post_flash_same_boot_j2_off_diagnostic_required": True,
                "fresh_com_ip_mac_boot_required": True,
                "maximum_next_action": {
                    "arm": 1,
                    "execute": 1,
                    "driver": 1,
                    "visible_refresh": 1,
                },
                "retry": 0,
                "automatic_white_recovery": 0,
                "autochain": 0,
            },
            "stop_conditions": [
                "identity/protocol mismatch",
                "unexpected BUSY or timeout",
                "unknown electrical state",
                "new fixed lines or damage",
                "invalid camera or clipped/blurred ROI",
                "unsealed source/firmware/action",
            ],
            "hardware_accessed": False,
        }
    )


def blank_observations(recipes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = []
    for recipe in recipes:
        for controller in CONTROLLERS:
            for position in recipe["positions"][controller.lower()]:
                quadrant = ("T" if position["row"] < 4 else "B") + (
                    "L" if position["column"] < 4 else "R"
                )
                rows.append(
                    {
                        "controller": controller,
                        "comparison_id": f"TARGET_C{recipe['target']['code']}",
                        "recipe_id": recipe["recipe_id"],
                        "position": quadrant,
                        "roi": position["local_roi"],
                        "lab": None,
                        "noise": None,
                        "quality_pass": None,
                        "single_pixel_uniform": None,
                        "measurement_evidence_sha256": None,
                    }
                )
    return {
        "schema_version": 1,
        "kind": DATA_KIND,
        "test_id": VERSION,
        "threshold_version": VERSION,
        "requested_levels": 3,
        "data_origin": "UNFILLED",
        "lab_space": "camera-relative",
        "protocol_result": "UNKNOWN",
        "image_result": "UNKNOWN",
        "identity": {
            key: None
            for key in (
                "panel_id",
                "run_id",
                "controller_revision",
                "boot",
                "profile_id",
                "test_phase",
                "firmware_sha256",
                "action_sha256",
                "frame_sha256",
                "source_state",
                "target_state",
                "camera_setup_id",
                "illumination_id",
                "temperature_c",
                "roi_definition_id",
            )
        },
        "camera": {
            "usb_id": "VID_32E4:PID_4801",
            "requested_settings": None,
            "effective_settings": None,
            "raw_supported": None,
            "iso_supported": None,
            "hardware_trigger_supported": None,
        },
        "waveform_internal_phase": "OPAQUE",
        "hue_family": None,
        "track": None,
        "evidence_files": [],
        "observations": rows,
    }


def analyze_observations(data: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate one comparable capture set, always leaving qualification at zero.

    File authenticity is the CLI's separate responsibility. Structural validity
    or user-declared PASS is never treated as physical/protocol qualification.
    """
    if (
        data.get("kind") != DATA_KIND
        or data.get("schema_version") != 1
        or data.get("test_id") != VERSION
        or data.get("threshold_version") != VERSION
    ):
        raise LightnessTestError("dataset identity or threshold version differs")
    levels = data.get("requested_levels")
    if type(levels) is not int or levels not in LEVEL_COUNTS:
        raise LightnessTestError("requested_levels must be 3, 5 or 10, not repetitions")
    if data.get("data_origin") not in ("UNFILLED", "FIELD_DERIVED", "TEST_FIXTURE"):
        raise LightnessTestError("data origin must be explicit")
    if data.get("lab_space") not in ("camera-relative", "calibrated"):
        raise LightnessTestError("Lab space must be explicit; spaces cannot be pooled")
    if data.get("waveform_internal_phase") != "OPAQUE":
        raise LightnessTestError("this test does not decode waveform phases")
    if data.get("camera", {}).get("usb_id") != "VID_32E4:PID_4801":
        raise LightnessTestError("only VID_32E4:PID_4801 evidence is supported")
    for field in ("protocol_result", "image_result"):
        if data.get(field) not in ("PASS", "FAIL", "UNKNOWN"):
            raise LightnessTestError(f"{field} must be PASS/FAIL/UNKNOWN")
    identity = data.get("identity")
    if not isinstance(identity, Mapping):
        raise LightnessTestError("identity must be an object")
    required = (
        "panel_id",
        "run_id",
        "controller_revision",
        "boot",
        "profile_id",
        "test_phase",
        "firmware_sha256",
        "action_sha256",
        "frame_sha256",
        "source_state",
        "target_state",
        "camera_setup_id",
        "illumination_id",
        "temperature_c",
        "roi_definition_id",
    )
    missing_identity = [key for key in required if identity.get(key) is None]
    for key in required:
        value = identity.get(key)
        if value is not None:
            if key.endswith("sha256"):
                require_sha256(value, key)
            elif key == "temperature_c":
                _number(value, key, minimum=-100)
            else:
                require_text(value, key)
    if data["lab_space"] == "calibrated":
        require_sha256(data.get("calibration_evidence_sha256"), "calibration evidence")
    rows = data.get("observations")
    if not isinstance(rows, list) or len(rows) > 128:
        raise LightnessTestError("observations must be an array of at most 128 cells")
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise LightnessTestError("observation must be an object")
        if set(row) != {
            "controller",
            "comparison_id",
            "recipe_id",
            "position",
            "roi",
            "lab",
            "noise",
            "quality_pass",
            "single_pixel_uniform",
            "measurement_evidence_sha256",
        }:
            raise LightnessTestError(
                "observation keys differ; per-cell identity overrides are forbidden"
            )
        controller, position = row.get("controller"), row.get("position")
        if controller not in CONTROLLERS or position not in POSITIONS:
            raise LightnessTestError(
                "controller/position must be CS1/CS2 and TL/TR/BL/BR"
            )
        key = (
            controller,
            require_text(row.get("comparison_id"), "comparison_id"),
            require_text(row.get("recipe_id"), "recipe_id"),
        )
        if position in grouped.setdefault(key, {}):
            raise LightnessTestError(
                "duplicate recipe/position; photos are not spatial replicas"
            )
        for flag in ("quality_pass", "single_pixel_uniform"):
            if row.get(flag) is not None and type(row[flag]) is not bool:
                raise LightnessTestError(f"{flag} must be bool or null")
        grouped[key][position] = row

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    used_rois: set[tuple[Any, ...]] = set()
    for (controller, comparison_id, recipe_id), positions in sorted(grouped.items()):
        reasons, labs, noise = [], {}, {}
        if set(positions) != set(POSITIONS):
            reasons.append("MISSING_FOUR_QUADRANTS")
        for position, row in positions.items():
            if (
                row.get("lab") is None
                or row.get("noise") is None
                or row.get("measurement_evidence_sha256") is None
            ):
                reasons.append("MISSING_OPTICAL_EVIDENCE")
                continue
            lab = finite_triple(row["lab"], "lab")
            if not 0 <= lab[0] <= 100:
                raise LightnessTestError("L* must be in 0..100")
            require_sha256(row["measurement_evidence_sha256"], "measurement evidence")
            roi = row.get("roi")
            if not isinstance(roi, Mapping) or any(
                type(roi.get(k)) is not int for k in ("x", "y", "width", "height")
            ):
                raise LightnessTestError("ROI must have integer x/y/width/height")
            if (
                min(roi["x"], roi["y"]) < 0
                or min(roi["width"], roi["height"]) <= 0
                or roi["x"] + roi["width"] > 512
                or roi["y"] + roi["height"] > 600
            ):
                raise LightnessTestError("ROI is outside the controller")
            physical_quadrant = ("T" if roi["y"] + roi["height"] / 2 < 300 else "B") + (
                "L" if roi["x"] + roi["width"] / 2 < 256 else "R"
            )
            if position != physical_quadrant:
                raise LightnessTestError(
                    "position label disagrees with physical ROI quadrant"
                )
            roi_key = (controller, roi["x"], roi["y"], roi["width"], roi["height"])
            if roi_key in used_rois:
                raise LightnessTestError(
                    "one physical ROI cannot count as two recipe/position cells"
                )
            used_rois.add(roi_key)
            if not isinstance(row["noise"], Mapping):
                raise LightnessTestError("noise must be an object")
            try:
                noise[position] = _noise(row["noise"])
            except LightnessTestError as error:
                if (
                    type(row["noise"].get("sample_count")) is int
                    and 0 <= row["noise"]["sample_count"] < 10
                ):
                    reasons.append("MISSING_NOISE_CAPTURES")
                else:
                    raise error
            labs[position] = lab
            if (
                row.get("quality_pass") is not True
                or row.get("single_pixel_uniform") is not True
            ):
                reasons.append("QUALITY_OR_SINGLE_PIXEL_UNPROVEN")
        center = _center(list(labs.values())) if labs else None
        dl = _p95([abs(lab[0] - center[0]) for lab in labs.values()]) if labs else None
        de = _p95([math.dist(lab, center) for lab in labs.values()]) if labs else None
        if center is not None and (
            dl > THRESHOLDS["position_p95_absolute_delta_lstar_maximum"]
            or de > THRESHOLDS["position_p95_delta_e76_maximum"]
        ):
            reasons.append("POSITION_DEPENDENT")
        if (
            center is not None
            and math.hypot(*center[1:]) <= THRESHOLDS["minimum_chroma_exclusive"]
        ):
            reasons.append("NEUTRAL_AXIS_NOT_COLOURED_FAMILY")
        item = {
            "recipe_id": recipe_id,
            "center_lab": center,
            "position_p95_delta_lstar": dl,
            "position_p95_delta_e76": de,
            "screen_eligible": not reasons,
            "reasons": sorted(set(reasons)),
            "positions": positions,
            "labs": labs,
            "noise": noise,
        }
        groups.setdefault((controller, comparison_id), []).append(item)

    reports = []
    for (controller, comparison_id), recipes in sorted(groups.items()):
        if len(recipes) > 16:
            raise LightnessTestError("at most 16 recipes per comparison group")
        valid = sorted(
            (r for r in recipes if r["screen_eligible"]),
            key=lambda r: (r["center_lab"][0], r["recipe_id"]),
        )
        pairs, edges = [], set()
        for a, b in combinations(valid, 2):
            differences = _differences(a["center_lab"], b["center_lab"])
            paired = []
            for position in POSITIONS:
                nl = max(a["noise"][position][0], b["noise"][position][0])
                ne = max(a["noise"][position][1], b["noise"][position][1])
                diff = _differences(a["labs"][position], b["labs"][position])
                paired.append(
                    {
                        "position": position,
                        **diff,
                        "noise_delta_lstar": nl,
                        "noise_delta_e00": ne,
                        "pass": _pair_pass(diff, nl, ne),
                    }
                )
            passed = _pair_pass(
                differences,
                max(p["noise_delta_lstar"] for p in paired),
                max(p["noise_delta_e00"] for p in paired),
            ) and all(p["pass"] for p in paired)
            pair = {
                "darker": a["recipe_id"],
                "lighter": b["recipe_id"],
                **differences,
                "quadrants": paired,
                "candidate_pair_pass": passed,
            }
            pairs.append(pair)
            if passed:
                edges.add((a["recipe_id"], b["recipe_id"]))
        ids = [r["recipe_id"] for r in valid]
        longest: tuple[str, ...] = ()
        for count in range(len(ids), 1, -1):
            longest = next(
                (
                    chain
                    for chain in combinations(ids, count)
                    if all(pair in edges for pair in combinations(chain, 2))
                ),
                (),
            )
            if longest:
                break
        if not longest and ids:
            longest = (ids[0],)
        for item in recipes:
            for key in ("labs", "noise"):
                item.pop(key)
        input_gate = (
            data["protocol_result"] == "PASS"
            and data["image_result"] == "PASS"
            and not missing_identity
            and data["data_origin"] != "UNFILLED"
        )
        reports.append(
            {
                "controller": controller,
                "comparison_id": comparison_id,
                "recipes": recipes,
                "pairs": pairs,
                "largest_same_hue_candidate_chain": list(longest),
                "candidate_level_count": len(longest),
                "input_review_complete": input_gate,
                "optical_level_count_pass": len(longest) >= levels,
                "requested_level_screen_pass": input_gate and len(longest) >= levels,
                "qualification_count": 0,
            }
        )
    protocol_failed = data["protocol_result"] == "FAIL"
    missing = missing_identity + (
        ["protocol review"] if data["protocol_result"] == "UNKNOWN" else []
    )
    missing += ["image review"] if data["image_result"] != "PASS" else []
    return attach_integrity(
        {
            "schema_version": 1,
            "kind": "mf1750-lightness-test-screen-report-v1",
            "test_id": VERSION,
            "input_data_origin": data["data_origin"],
            "lab_space": data["lab_space"],
            "requested_levels": levels,
            "thresholds": deepcopy(THRESHOLDS),
            "identity_and_protocol": {
                "declared_result": data["protocol_result"],
                "missing_bindings": missing,
                "raw_protocol_verification_performed_by_this_function": False,
            },
            "groups": reports,
            "required_controllers": list(CONTROLLERS),
            "missing_controllers": [
                c for c in CONTROLLERS if not any(r["controller"] == c for r in reports)
            ],
            "verdict": "FAIL_STOP" if protocol_failed else "HOLD_FOR_EVIDENCE",
            "screen_only": True,
            "qualified_count": 0,
            "later_gates": {
                stage: "NOT_EVALUATED"
                for stage in (
                    "LOCAL_HOLD",
                    "FRESH_WHITE_RECONSTRUCTION",
                    "RETENTION",
                    "CROSS_CONTROLLER",
                )
            },
            "next_action": "stop on protocol failure"
            if protocol_failed
            else "review controller-local screen; collect missing evidence; no automatic next action",
            "hardware_accessed": False,
            "live_authorization": False,
            "actual_counts": {
                "arm": 0,
                "execute": 0,
                "driver": 0,
                "visible_refresh": 0,
            },
        }
    )
