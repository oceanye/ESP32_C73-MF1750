#!/usr/bin/env python3
"""Seal an offline human A/B judgement for the T3-A to fresh T4-V3-B swap.

The tool never opens a camera, device, relay, serial port, or network
connection.  It binds the already-sealed T3 partial camera report, one exact
completed T4 action result, and 24 human judgements (three visible spatial
replicates for each code).  The judgement asks whether each T4 side resembles
the T3 physical side or the T3 profile-matched opposite side.

This is a profile-versus-physical-side screening tool.  It does not calibrate
absolute colour, qualify a colour, or authorize another display action.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
import importlib
import json
import os
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_profile_following_human_observation as human,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t1_t2_profile_comparison as strict,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t3_profile_following_camera_observation as t3_camera,
)


SCHEMA_VERSION = 3
INPUT_KIND = "mf1750-raw-p16-crossover-t4-successor-v3-matched-swap-human-input-v3"
REPORT_KIND = "mf1750-raw-p16-crossover-t4-successor-v3-matched-swap-human-report-v3"
METHOD_ID = (
    "t3-a-active-header-ac-to-t4-successor-v3-b-active-header-ca-"
    "human-partial-3x8-v3"
)
INTEGRITY_ALGORITHM = strict.INTEGRITY_ALGORITHM

T3_STAGE = human.AC_V2_STAGE
T4_STAGE = "t4-active-header-ca-r20-swap-confirmation-successor-v3"
T4_PACK_MODULE = (
    "tools.mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_"
    "successor_v3_pack"
)
FAILED_T4_V1_ACTION_ID = (
    "c9a88f5b4cae0589279d3d874f81492c17d6ba4afc2f5da256fec56bec9b36a1"
)
FAILED_T4_V2_ACTION_ID = (
    "399a0ec181ece961b25b3de630ae1c313e2855d65d1036459f22aec16bf174b5"
)
REJECTED_ACTION_IDS = (FAILED_T4_V1_ACTION_ID, FAILED_T4_V2_ACTION_ID)

SELECTED_ROWS = (0, 1, 2)
CONTROLLERS = human.CONTROLLERS
CANDIDATE_CODES = human.CANDIDATE_CODES
PRIMARY_CANDIDATE_CODES = (0, 1, 4, 6)
SECONDARY_CANDIDATE_CODES = (7,)
CONTROL_CODES = human.CONTROL_CODES

MATCH_VALUES = (
    "A_CS1",
    "A_CS2",
    "BOTH_A_SIDES_SAME",
    "NEITHER",
    "UNCLEAR",
)
REPLICATE_CLASSIFICATIONS = (
    "PROFILE_FOLLOWING",
    "PHYSICAL_SIDE_FOLLOWING",
    "NON_DISCRIMINATING",
    "MIXED_OR_UNMATCHED",
    "UNCLEAR",
    "UNSTABLE",
)
ARTIFACT_FIELDS = (
    "edge_anomaly",
    "horizontal_stripe",
    "vertical_stripe",
    "residual_or_ghosting",
    "flicker_or_instability",
)

INPUT_KEYS = {
    "schema_version",
    "kind",
    "stage",
    "observed_at",
    "operator",
    "supervision",
    "artifacts",
    "replicates",
}
OPERATOR_KEYS = {"operator_id", "operator_verbatim"}
SUPERVISION_KEYS = {
    "t3_reference_available_during_observation",
    "t4_refresh_complete_reviewed",
    "no_intervening_visible_refresh",
    "ambient_light_stable",
    "viewing_angle_stable",
    "display_stable_through_observation",
    "three_replicates_checked",
    "supervision_verbatim",
}
ARTIFACT_KEYS = {"observed", "operator_verbatim"}
REPLICATE_KEYS = {
    "code",
    "row",
    "column",
    "t4_cs1_matches_t3_a",
    "t4_cs2_matches_t3_a",
    "t4_sides_equal",
    "stable",
    "operator_verbatim",
}


class T4MatchedSwapHumanObservationError(RuntimeError):
    """Raised when a matched-swap input or evidence binding differs."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise T4MatchedSwapHumanObservationError(message)


def _read_json(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        return strict._load_json(Path(path), label=label)  # noqa: SLF001
    except strict.CrossoverProfileComparisonError as error:
        raise T4MatchedSwapHumanObservationError(str(error)) from error


def _verify_integrity(root: Mapping[str, Any], *, label: str) -> str:
    try:
        return strict._verify_integrity(root, label=label)  # noqa: SLF001
    except strict.CrossoverProfileComparisonError as error:
        raise T4MatchedSwapHumanObservationError(str(error)) from error


def _file_binding(path: Path, payload: bytes) -> dict[str, Any]:
    return {
        "path": Path(path).resolve().as_posix(),
        "bytes": len(payload),
        "file_sha256": strict.sha256_bytes(payload),
    }


def _text(value: Any, *, label: str, maximum: int = 4096) -> str:
    _require(isinstance(value, str), f"{label} must be text")
    _require(bool(value.strip()), f"{label} must not be blank")
    _require(len(value) <= maximum, f"{label} is too long")
    return value


def _parse_time(value: Any, *, label: str) -> str:
    text = _text(value, label=label, maximum=64)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise T4MatchedSwapHumanObservationError(f"{label} is not RFC3339") from error
    _require(parsed.tzinfo is not None, f"{label} has no timezone")
    return text


def _expected_positions() -> list[tuple[int, int, int]]:
    return [
        (code, row, human.CODE_ROWS[row].index(code))
        for code in range(8)
        for row in SELECTED_ROWS
    ]


def _t3_reference(path: Path) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    try:
        root, payload = t3_camera.validate_partial_report(Path(path))
    except t3_camera.T3CameraObservationError as error:
        raise T4MatchedSwapHumanObservationError(
            f"T3 A partial report rejected: {error}"
        ) from error
    _require(root.get("stage") == T3_STAGE, "T3 A partial report stage differs")
    _require(
        root.get("mode") == t3_camera.PARTIAL_MODE
        and root.get("layout", {}).get("selected_rows") == list(SELECTED_ROWS),
        "T3 A partial report is not the frozen dual 3x8 layout",
    )
    comparisons = root.get("profile_code_comparison")
    _require(
        isinstance(comparisons, list) and len(comparisons) == 8,
        "T3 A profile comparison differs",
    )
    for code, item in enumerate(comparisons):
        _require(
            item.get("code") == code
            and item.get("cs1_profile_alias") == "A"
            and item.get("cs1_profile") == "active"
            and item.get("cs2_profile_alias") == "C"
            and item.get("cs2_profile") == "commented"
            and item.get("samples_per_profile") == 9,
            f"T3 A code {code} profile binding differs",
        )
    action = root["action_result_bindings"]["t3_ac_profile_following_atlas"]
    return root, payload, action


def _t4_contract() -> dict[str, Any]:
    try:
        pack = importlib.import_module(T4_PACK_MODULE)
        report = pack.build_report()
        action = report["actions"][0]
        config = pack.CONFIG
        artifacts = pack.ARTIFACTS[pack.STAGE]
    except (ImportError, AttributeError, KeyError, IndexError, TypeError) as error:
        raise T4MatchedSwapHumanObservationError(
            "frozen T4 pack is unavailable or has a different interface"
        ) from error
    _require(pack.STAGE == T4_STAGE, "T4 pack stage differs")
    _require(
        action.get("action_id") not in REJECTED_ACTION_IDS,
        "failed T4 V1/V2 action is not reusable as the fresh V3 observation source",
    )
    _require(
        all(
            action_id in tuple(pack.non_reusable_action_ids())
            for action_id in REJECTED_ACTION_IDS
        ),
        "fresh T4 V3 pack does not tombstone both failed V1/V2 actions",
    )
    waveform = action.get("waveform_binding", {})
    _require(
        action.get("global_header") == "active"
        and waveform.get("cs1", {}).get("name") == "commented"
        and waveform.get("cs2", {}).get("name") == "active",
        "T4 is not the active-header CA matched swap",
    )
    _require(
        tuple(tuple(row) for row in pack.CODE_ROWS) == human.CODE_ROWS,
        "T4 code layout differs from T3 A",
    )
    firmware_sha256 = artifacts.get("bin_sha256")
    _require(
        isinstance(firmware_sha256, str)
        and len(firmware_sha256) == 64
        and set(firmware_sha256) <= set("0123456789abcdef")
        and firmware_sha256 != "0" * 64,
        "T4 firmware identity is not sealed",
    )
    return {
        "pack": pack,
        "report": report,
        "action": action,
        "config": config,
        "firmware_sha256": firmware_sha256,
        "profile_map": {
            "global_header": "active",
            "CS1": "commented",
            "CS2": "active",
        },
    }


def _validate_t4_action_result(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved = Path(path).resolve()
    payload, root = _read_json(resolved, label="T4 B action result")
    canonical_sha256 = _verify_integrity(root, label="T4 B action result")
    contract = _t4_contract()
    expected = contract["action"]
    config = contract["config"]
    action = root.get("action")
    terminal = root.get("terminal_report")
    _require(isinstance(action, Mapping), "T4 result.action is missing")
    _require(isinstance(terminal, Mapping), "T4 terminal report is missing")
    observed_action_ids = {
        value
        for value in (action.get("action_id"), terminal.get("action_id"))
        if isinstance(value, str)
    }
    _require(
        not observed_action_ids.intersection(REJECTED_ACTION_IDS),
        "failed T4 V1/V2 action result is permanently rejected",
    )
    try:
        expected_runtime = human._expected_runtime_action(expected)  # noqa: SLF001
    except (KeyError, TypeError) as error:
        raise T4MatchedSwapHumanObservationError(
            "T4 expected runtime action cannot be derived"
        ) from error
    for field, value in expected_runtime.items():
        _require(action.get(field) == value, f"T4 action {field} differs")
    if "prior_static_action_id" in expected:
        _require(
            action.get("prior_static_action_id") == expected["prior_static_action_id"],
            "T4 prior_static_action_id differs",
        )
    _require(
        root.get("schema_version") == 1
        and root.get("kind") == f"mf1750-ec5-{config.route_slug}-result"
        and root.get("outcome") == "complete_pass"
        and root.get("visible_refreshes") == 1
        and root.get("firmware_sha256") == contract["firmware_sha256"]
        and root.get("no_autochain") is True
        and root.get("no_retry") is True
        and root.get("no_recovery") is True,
        "T4 action-result envelope differs",
    )
    terminal_expected = {
        "terminal_state": "COMPLETE",
        "result": True,
        "valid": True,
        "campaign_id": config.campaign_id,
        "test_id": config.test_id,
        "contract_id": contract["report"]["contract_id"],
        "build_tag": config.build_tag,
        "action_id": expected["action_id"],
        "descriptor_id": expected["descriptor_id"],
        "ordinal": 1,
        "role": expected["role"],
        "round": expected["round"],
        "profile_id": expected["profile_id"],
        "global_header": expected["global_header"],
        "global_tuple_id": expected["global_tuple_id"],
        "driver_called": True,
        "driver_call_count_for_action": 1,
    }
    for field, value in terminal_expected.items():
        _require(terminal.get(field) == value, f"T4 terminal {field} differs")
    driver = terminal.get("driver")
    _require(
        isinstance(driver, Mapping)
        and driver.get("valid") is True
        and driver.get("sequence_ok") is True
        and driver.get("wait_timeout") is False
        and driver.get("failure_stage") == "none",
        "T4 terminal driver evidence differs",
    )
    binding = _file_binding(resolved, payload)
    binding.update(
        {
            "canonical_integrity_sha256": canonical_sha256,
            "stage": T4_STAGE,
            "campaign_id": config.campaign_id,
            "test_id": config.test_id,
            "contract_id": contract["report"]["contract_id"],
            "descriptor_id": expected["descriptor_id"],
            "action_id": expected["action_id"],
            "role": expected["role"],
            "round": expected["round"],
            "firmware_sha256": contract["firmware_sha256"],
            "frame_sha256": expected["frame"]["sha256"],
            "cs1_dtm_sha256": expected["cs1_dtm"]["sha256"],
            "cs2_dtm_sha256": expected["cs2_dtm"]["sha256"],
            "profile_id": expected["profile_id"],
            "global_tuple_id": expected["global_tuple_id"],
            "profile_map": contract["profile_map"],
        }
    )
    return binding, root


def _validate_input(root: Mapping[str, Any]) -> dict[str, Any]:
    _require(set(root) == INPUT_KEYS, "operator input keys differ")
    _require(root.get("schema_version") == SCHEMA_VERSION, "input schema differs")
    _require(root.get("kind") == INPUT_KIND, "input kind differs")
    _require(root.get("stage") == T4_STAGE, "input stage differs")
    _parse_time(root.get("observed_at"), label="observed_at")

    operator = root.get("operator")
    _require(isinstance(operator, Mapping), "operator must be an object")
    _require(set(operator) == OPERATOR_KEYS, "operator keys differ")
    _text(operator.get("operator_id"), label="operator_id", maximum=128)
    _text(operator.get("operator_verbatim"), label="operator_verbatim")

    supervision = root.get("supervision")
    _require(isinstance(supervision, Mapping), "supervision must be an object")
    _require(set(supervision) == SUPERVISION_KEYS, "supervision keys differ")
    for field in SUPERVISION_KEYS - {"supervision_verbatim"}:
        _require(type(supervision.get(field)) is bool, f"supervision.{field} differs")
    _text(supervision.get("supervision_verbatim"), label="supervision_verbatim")

    artifacts = root.get("artifacts")
    _require(isinstance(artifacts, Mapping), "artifacts must be an object")
    _require(set(artifacts) == set(ARTIFACT_FIELDS), "artifact fields differ")
    for field in ARTIFACT_FIELDS:
        item = artifacts[field]
        _require(isinstance(item, Mapping), f"artifacts.{field} must be an object")
        _require(set(item) == ARTIFACT_KEYS, f"artifacts.{field} keys differ")
        _require(type(item.get("observed")) is bool, f"artifacts.{field} differs")
        _text(item.get("operator_verbatim"), label=f"artifacts.{field}.verbatim")

    replicates = root.get("replicates")
    _require(isinstance(replicates, list), "replicates must be a list")
    _require(len(replicates) == 24, "exactly 24 partial replicates are required")
    actual_positions = []
    for index, item in enumerate(replicates):
        _require(isinstance(item, Mapping), f"replicate[{index}] must be an object")
        _require(set(item) == REPLICATE_KEYS, f"replicate[{index}] keys differ")
        code = item.get("code")
        row = item.get("row")
        column = item.get("column")
        _require(
            type(code) is int and 0 <= code <= 7, f"replicate[{index}].code differs"
        )
        _require(row in SELECTED_ROWS, f"replicate[{index}].row differs")
        _require(
            type(column) is int and 0 <= column <= 7,
            f"replicate[{index}].column differs",
        )
        _require(
            human.CODE_ROWS[row][column] == code,
            f"replicate[{index}] code/position differs from frozen layout",
        )
        actual_positions.append((code, row, column))
        for field in ("t4_cs1_matches_t3_a", "t4_cs2_matches_t3_a"):
            _require(
                item.get(field) in MATCH_VALUES, f"replicate[{index}].{field} differs"
            )
        _require(
            item.get("t4_sides_equal") is None
            or type(item.get("t4_sides_equal")) is bool,
            f"replicate[{index}].t4_sides_equal differs",
        )
        _require(type(item.get("stable")) is bool, f"replicate[{index}].stable differs")
        _text(item.get("operator_verbatim"), label=f"replicate[{index}].verbatim")
    _require(
        sorted(actual_positions) == sorted(_expected_positions())
        and len(set(actual_positions)) == 24,
        "replicate position set differs from the top 3x8 layout",
    )
    return dict(root)


def _replicate_classification(item: Mapping[str, Any]) -> str:
    if item["stable"] is not True:
        return "UNSTABLE"
    left = item["t4_cs1_matches_t3_a"]
    right = item["t4_cs2_matches_t3_a"]
    if left == "A_CS2" and right == "A_CS1":
        return "PROFILE_FOLLOWING"
    if left == "A_CS1" and right == "A_CS2":
        return "PHYSICAL_SIDE_FOLLOWING"
    if (
        left == "BOTH_A_SIDES_SAME"
        and right == "BOTH_A_SIDES_SAME"
        and item["t4_sides_equal"] is True
    ):
        return "NON_DISCRIMINATING"
    if left == "UNCLEAR" or right == "UNCLEAR":
        return "UNCLEAR"
    return "MIXED_OR_UNMATCHED"


def _code_classification(counts: Counter[str]) -> str:
    if counts["PROFILE_FOLLOWING"] == 3:
        return "PROFILE_FOLLOWING"
    if counts["PHYSICAL_SIDE_FOLLOWING"] == 3:
        return "PHYSICAL_SIDE_FOLLOWING"
    if counts["NON_DISCRIMINATING"] == 3:
        return "NON_DISCRIMINATING_CONTROL"
    if counts["PROFILE_FOLLOWING"] >= 2 and counts["PHYSICAL_SIDE_FOLLOWING"] == 0:
        return "REVIEW_PROFILE_TREND"
    if counts["PHYSICAL_SIDE_FOLLOWING"] >= 2 and counts["PROFILE_FOLLOWING"] == 0:
        return "REVIEW_PHYSICAL_TREND"
    return "INCONCLUSIVE_MIXED"


def _derive(source: Mapping[str, Any]) -> dict[str, Any]:
    by_code: dict[int, list[Mapping[str, Any]]] = {code: [] for code in range(8)}
    for item in source["replicates"]:
        by_code[item["code"]].append(item)
    code_results = []
    for code in range(8):
        results = []
        for item in sorted(by_code[code], key=lambda value: value["row"]):
            classification = _replicate_classification(item)
            _require(
                classification in REPLICATE_CLASSIFICATIONS,
                "internal replicate classification differs",
            )
            results.append({**dict(item), "classification": classification})
        counts = Counter(item["classification"] for item in results)
        code_results.append(
            {
                "code": code,
                "role": "CONTROL" if code in CONTROL_CODES else "CANDIDATE",
                "priority": (
                    "PRIMARY"
                    if code in PRIMARY_CANDIDATE_CODES
                    else "SECONDARY"
                    if code in SECONDARY_CANDIDATE_CODES
                    else "CONTROL"
                ),
                "replicates": results,
                "classification_counts": {
                    name: counts[name] for name in REPLICATE_CLASSIFICATIONS
                },
                "classification": _code_classification(counts),
            }
        )

    candidates = [item for item in code_results if item["code"] in CANDIDATE_CODES]
    controls = [item for item in code_results if item["code"] in CONTROL_CODES]
    candidate_counts = Counter(item["classification"] for item in candidates)
    primary_profile_count = sum(
        item["classification"] == "PROFILE_FOLLOWING"
        for item in candidates
        if item["code"] in PRIMARY_CANDIDATE_CODES
    )
    primary_physical_count = sum(
        item["classification"] == "PHYSICAL_SIDE_FOLLOWING"
        for item in candidates
        if item["code"] in PRIMARY_CANDIDATE_CODES
    )
    controls_pass = all(
        item["classification"] == "NON_DISCRIMINATING_CONTROL" for item in controls
    )
    supervision_pass = all(
        source["supervision"][field] is True
        for field in SUPERVISION_KEYS - {"supervision_verbatim"}
    )
    artifacts_pass = not any(
        source["artifacts"][field]["observed"] for field in ARTIFACT_FIELDS
    )
    all_stable = all(item["stable"] for item in source["replicates"])
    quality_pass = controls_pass and supervision_pass and artifacts_pass and all_stable

    if not quality_pass:
        conclusion = "INCONCLUSIVE_INPUT_OR_CONTROL_GATE"
        screening_state = "FAIL_DATA_QUALITY"
        profile_hypothesis = "NOT_EVALUATED"
    elif candidate_counts["PROFILE_FOLLOWING"] == 5:
        conclusion = "PROFILE_FOLLOWING_STRONG"
        screening_state = "PASS"
        profile_hypothesis = "SUPPORTED"
    elif (
        candidate_counts["PROFILE_FOLLOWING"] >= 4
        and candidate_counts["PHYSICAL_SIDE_FOLLOWING"] == 0
        and primary_profile_count >= 3
    ):
        conclusion = "PROFILE_FOLLOWING_SUPPORTED"
        screening_state = "PASS"
        profile_hypothesis = "SUPPORTED"
    elif candidate_counts["PHYSICAL_SIDE_FOLLOWING"] == 5:
        conclusion = "PHYSICAL_SIDE_FOLLOWING_STRONG"
        screening_state = "PASS"
        profile_hypothesis = "REFUTED_BY_PHYSICAL_SIDE_FOLLOWING"
    elif (
        candidate_counts["PHYSICAL_SIDE_FOLLOWING"] >= 4
        and candidate_counts["PROFILE_FOLLOWING"] == 0
        and primary_physical_count >= 3
    ):
        conclusion = "PHYSICAL_SIDE_FOLLOWING_SUPPORTED"
        screening_state = "PASS"
        profile_hypothesis = "REFUTED_BY_PHYSICAL_SIDE_FOLLOWING"
    else:
        conclusion = "INCONCLUSIVE_MIXED"
        screening_state = "REVIEW"
        profile_hypothesis = "INCONCLUSIVE"

    return {
        "code_results": code_results,
        "candidate_summary": {
            "codes": list(CANDIDATE_CODES),
            "primary_codes": list(PRIMARY_CANDIDATE_CODES),
            "secondary_codes": list(SECONDARY_CANDIDATE_CODES),
            "classification_counts": dict(sorted(candidate_counts.items())),
            "primary_profile_following_count": primary_profile_count,
            "primary_physical_side_following_count": primary_physical_count,
        },
        "control_summary": {
            "codes": list(CONTROL_CODES),
            "all_non_discriminating": controls_pass,
        },
        "quality_gates": {
            "supervision_pass": supervision_pass,
            "artifacts_absent": artifacts_pass,
            "all_24_replicates_stable": all_stable,
            "controls_pass": controls_pass,
            "overall": "PASS" if quality_pass else "FAIL",
        },
        "screening_state": screening_state,
        "matched_swap_conclusion": conclusion,
        "profile_hypothesis": profile_hypothesis,
    }


def build_report(
    *,
    t3_partial_report_path: Path,
    t4_action_result_path: Path,
    operator_input_path: Path,
) -> dict[str, Any]:
    """Build one fail-closed matched-swap report entirely offline."""

    t3_root, t3_payload, t3_action = _t3_reference(t3_partial_report_path)
    t4_binding, _t4_root = _validate_t4_action_result(t4_action_result_path)
    input_payload, input_root = _read_json(operator_input_path, label="operator input")
    source = _validate_input(input_root)

    _require(
        t3_action["frame_sha256"] == t4_binding["frame_sha256"]
        and t3_action["cs1_dtm_sha256"] == t4_binding["cs1_dtm_sha256"]
        and t3_action["cs2_dtm_sha256"] == t4_binding["cs2_dtm_sha256"],
        "T3 A and T4 B frame/DTM differ",
    )
    _require(
        t3_action["profile_map"]
        == {"global_header": "active", "CS1": "active", "CS2": "commented"},
        "T3 A is not active-header AC",
    )
    _require(
        t4_binding["profile_map"]
        == {"global_header": "active", "CS1": "commented", "CS2": "active"},
        "T4 B is not active-header CA",
    )
    t3_ids = {
        t3_action[field]
        for field in ("campaign_id", "contract_id", "descriptor_id", "action_id")
    }
    t4_ids = {
        t4_binding[field]
        for field in ("campaign_id", "contract_id", "descriptor_id", "action_id")
    }
    _require(not t3_ids & t4_ids, "T4 B identity overlaps consumed T3 A")

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "method_id": METHOD_ID,
        "stage": T4_STAGE,
        "matched_swap": {
            "controlled_global_header": "active",
            "t3_a_profile_map": t3_action["profile_map"],
            "t4_b_profile_map": t4_binding["profile_map"],
            "frame_sha256": t4_binding["frame_sha256"],
            "cs1_dtm_sha256": t4_binding["cs1_dtm_sha256"],
            "cs2_dtm_sha256": t4_binding["cs2_dtm_sha256"],
            "only_profile_assignment_swapped": True,
        },
        "t3_a_partial_report_binding": {
            **_file_binding(Path(t3_partial_report_path), t3_payload),
            "canonical_integrity_sha256": t3_root["integrity"]["sha256"],
            "automatic_conclusion": t3_root["automatic_conclusion"],
        },
        "t4_b_action_result_binding": t4_binding,
        "operator_input_binding": _file_binding(operator_input_path, input_payload),
        "raw_operator_input": source,
        "derived": _derive(source),
        "classification_boundary": {
            "human_relative_profile_vs_physical_screen_only": True,
            "camera_evidence_in_this_report": False,
            "absolute_colour_calibrated": False,
            "qualified_colour_count": 0,
            "formal_colour_gate_evaluated": False,
            "automatic_next_action_authorized": False,
        },
        "offline_execution": {
            "hardware_accessed": False,
            "camera_accessed": False,
            "network_accessed": False,
            "serial_or_com_accessed": False,
            "relay_accessed": False,
            "firmware_flashed": False,
            "display_refreshed": False,
        },
        "output_write_contract": "O_EXCL",
    }
    report["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": strict.sha256_bytes(strict.canonical_json(report)),
    }
    return report


def validate_report(path: Path) -> tuple[dict[str, Any], bytes]:
    payload, root = _read_json(path, label="T4 matched-swap report")
    _verify_integrity(root, label="T4 matched-swap report")
    _require(
        root.get("schema_version") == SCHEMA_VERSION
        and root.get("kind") == REPORT_KIND
        and root.get("method_id") == METHOD_ID
        and root.get("stage") == T4_STAGE,
        "T4 matched-swap report identity differs",
    )
    recomputed = build_report(
        t3_partial_report_path=Path(root["t3_a_partial_report_binding"]["path"]),
        t4_action_result_path=Path(root["t4_b_action_result_binding"]["path"]),
        operator_input_path=Path(root["operator_input_binding"]["path"]),
    )
    _require(
        recomputed == root, "T4 matched-swap report differs from deep recomputation"
    )
    return root, payload


def input_template() -> dict[str, Any]:
    replicates = []
    for code, row, column in _expected_positions():
        replicates.append(
            {
                "code": code,
                "row": row,
                "column": column,
                "t4_cs1_matches_t3_a": "UNCLEAR",
                "t4_cs2_matches_t3_a": "UNCLEAR",
                "t4_sides_equal": None,
                "stable": False,
                "operator_verbatim": "FILL_OBSERVATION",
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": INPUT_KIND,
        "stage": T4_STAGE,
        "observed_at": "FILL_RFC3339_WITH_TIMEZONE",
        "operator": {
            "operator_id": "FILL_OPERATOR_ID",
            "operator_verbatim": "FILL_OVERALL_OBSERVATION",
        },
        "supervision": {
            field: False for field in SUPERVISION_KEYS - {"supervision_verbatim"}
        }
        | {"supervision_verbatim": "FILL_SUPERVISION"},
        "artifacts": {
            field: {"observed": False, "operator_verbatim": "FILL_ARTIFACT_CHECK"}
            for field in ARTIFACT_FIELDS
        },
        "replicates": replicates,
    }


def describe_contract() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": (
            "mf1750-raw-p16-crossover-t4-successor-v3-matched-swap-"
            "human-contract-v3"
        ),
        "stage": T4_STAGE,
        "comparison": {
            "A": "T3 active-header CS1=A(active), CS2=C(commented)",
            "B": "T4 active-header CS1=C(commented), CS2=A(active)",
            "profile_following": "B-CS1 resembles A-CS2 AND B-CS2 resembles A-CS1",
            "physical_side_following": "B-CS1 resembles A-CS1 AND B-CS2 resembles A-CS2",
            "control_non_discriminating": (
                "both B sides equal and both match the indistinguishable A sides"
            ),
        },
        "candidate_codes": list(CANDIDATE_CODES),
        "primary_candidate_codes": list(PRIMARY_CANDIDATE_CODES),
        "secondary_candidate_codes": list(SECONDARY_CANDIDATE_CODES),
        "control_codes": list(CONTROL_CODES),
        "selected_rows": list(SELECTED_ROWS),
        "replicates_per_code": 3,
        "rejected_action_ids": list(REJECTED_ACTION_IDS),
        "pass_rule": (
            "5/5 candidate codes, or >=4/5 with zero opposite and >=3/4 primary; "
            "all controls non-discriminating and all quality gates pass"
        ),
        "review_rule": "mixed result or only a two-of-three per-code trend",
        "fail_data_quality_rule": (
            "control mismatch, unstable replicate, artifact, or supervision failure"
        ),
        "no_hardware_or_camera_io": True,
    }


def _serialize(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _write_exclusive(path: Path, payload: bytes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(target, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            target.unlink()
        except OSError:
            pass
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("describe", allow_abbrev=False)
    template = commands.add_parser("template", allow_abbrev=False)
    template.add_argument("--output", type=Path)
    generate = commands.add_parser("generate", allow_abbrev=False)
    generate.add_argument("--t3-partial-report", type=Path, required=True)
    generate.add_argument("--t4-action-result", type=Path, required=True)
    generate.add_argument("--operator-input", type=Path, required=True)
    generate.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate", allow_abbrev=False)
    validate.add_argument("--report", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "describe":
            print(json.dumps(describe_contract(), ensure_ascii=False, indent=2))
            return 0
        if args.command == "template":
            payload = _serialize(input_template())
            if args.output is None:
                sys.stdout.buffer.write(payload)
            else:
                _write_exclusive(args.output, payload)
            return 0
        if args.command == "generate":
            report = build_report(
                t3_partial_report_path=args.t3_partial_report,
                t4_action_result_path=args.t4_action_result,
                operator_input_path=args.operator_input,
            )
            _write_exclusive(args.output, _serialize(report))
            return 0
        if args.command == "validate":
            report, _payload = validate_report(args.report)
            print(json.dumps(report["derived"], ensure_ascii=False, indent=2))
            return 0
    except T4MatchedSwapHumanObservationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
