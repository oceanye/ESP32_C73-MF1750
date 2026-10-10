#!/usr/bin/env python3
"""Offline observation template and evaluator for stable-code0 Latin V3.

This tool never opens a camera or a network connection.  It binds manually or
externally sampled CIE Lab values to the immutable 8x8 recipe manifest, decodes
the CS2 180-degree placement, and emits review candidates only.  It cannot
qualify a colour or a production gray/brightness level.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_stable_code0_luma_latin_v3_once as once  # noqa: E402
from tools import mf1750_stable_code0_luma_latin_v3_pack as pack  # noqa: E402


class ObservationError(RuntimeError):
    """Raised when an observation is incomplete, ambiguous, or unbound."""


STAGES = ("L3", "L4")
CONTROLLERS = ("CS1", "CS2")
CAPTURE_STATES = ("PASS", "FAIL", "UNKNOWN")
STRIPE_STATES = ("CLEAR", "PRESENT", "UNCERTAIN")
DEFAULT_THRESHOLDS = {
    "minimum_between_middle_delta_l_star": 4.0,
    "maximum_repeat_l_star_range": 3.0,
    "maximum_same_hue_angle_degrees": 12.0,
    "minimum_chroma_for_hue_gate": 5.0,
    "maximum_l3_l4_cell_delta_l_star": 3.0,
    "maximum_l3_l4_cell_delta_e76": 5.0,
}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _recipe_index() -> dict[tuple[str, int, int], dict[str, Any]]:
    result: dict[tuple[str, int, int], dict[str, Any]] = {}
    for item in pack.recipe_map():
        key = (
            str(item["controller_name"]),
            int(item["physical_row"]),
            int(item["physical_column"]),
        )
        result[key] = deepcopy(item)
    if len(result) != 128:
        raise ObservationError("recipe manifest cardinality differs")
    return result


def observation_template(*, include_l4: bool = True) -> dict[str, Any]:
    """Return a strict fillable template; no image or device is accessed."""

    report = pack.build_report()
    stages = STAGES if include_l4 else ("L3",)
    terminal_paths = {
        "L3": once.ACTION_OUTPUTS[3].relative_to(REPO_ROOT).as_posix(),
        "L4": once.ACTION_OUTPUTS[4].relative_to(REPO_ROOT).as_posix(),
    }
    recipes = _recipe_index()
    measurements: list[dict[str, Any]] = []
    for stage in stages:
        for controller in CONTROLLERS:
            for row in range(8):
                for column in range(8):
                    recipe = recipes[(controller, row, column)]
                    measurements.append(
                        {
                            "stage": stage,
                            "controller": controller,
                            "controller_role": recipe["controller_role"],
                            "physical_row": row,
                            "physical_column": column,
                            "logical_row": recipe["decoder"]["logical_row"],
                            "logical_column": recipe["decoder"]["logical_column"],
                            "decoder_transform": recipe["decoder"]["transform"],
                            "recipe_id": recipe["recipe_id"],
                            "middle_code": recipe["middle"]["code"],
                            "panel_local_roi": deepcopy(recipe["local_roi"]),
                            "lab": {"l_star": None, "a_star": None, "b_star": None},
                            "bottom_edge_stripe": "UNCERTAIN",
                        }
                    )
    body = {
        "schema_version": 1,
        "kind": "mf1750-stable-code0-luma-latin-v3-observation-template",
        "campaign_id": pack.CAMPAIGN_ID,
        "contract_id": report["contract_id"],
        "capture_policy": {
            "camera": "48MP_USB_CAMERA_VID_32E4_PID_4801",
            "automatic_capture_performed_by_this_tool": False,
            "camera_relative_only": True,
            "absolute_colour_claimed": False,
            "controller_colour_equivalence_claimed": False,
        },
        "captures": {
            stage: {
                "terminal_evidence_path": terminal_paths[stage],
                "image_path": None,
                "image_bytes": None,
                "image_sha256": None,
                "quality": {
                    "both_controller_rois_visible": "UNKNOWN",
                    "exposure_usable": "UNKNOWN",
                    "focus_usable": "UNKNOWN",
                    "glare_not_material": "UNKNOWN",
                },
            }
            for stage in stages
        },
        "thresholds": deepcopy(DEFAULT_THRESHOLDS),
        "measurements": measurements,
        "operator_notes": None,
        "qualification_boundary": {
            "review_candidates_only": True,
            "qualified_colour_count": 0,
            "qualified_gray_levels": 0,
        },
    }
    return {**body, "template_sha256": hashlib.sha256(_canonical(body)).hexdigest()}


def _finite_number(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ObservationError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ObservationError(f"{label} must be a finite number")
    return result


def _lab(value: Any, *, label: str) -> tuple[float, float, float]:
    if not isinstance(value, Mapping):
        raise ObservationError(f"{label} Lab object missing")
    l_star = _finite_number(value.get("l_star"), label=f"{label}.l_star")
    a_star = _finite_number(value.get("a_star"), label=f"{label}.a_star")
    b_star = _finite_number(value.get("b_star"), label=f"{label}.b_star")
    if not 0.0 <= l_star <= 100.0:
        raise ObservationError(f"{label}.l_star outside [0,100]")
    return l_star, a_star, b_star


def _hue(a_star: float, b_star: float) -> float:
    return math.degrees(math.atan2(b_star, a_star)) % 360.0


def _angle_delta(left: float, right: float) -> float:
    return abs((left - right + 180.0) % 360.0 - 180.0)


def _median_lab(values: Sequence[tuple[float, float, float]]) -> tuple[float, float, float]:
    return tuple(statistics.median(item[index] for item in values) for index in range(3))  # type: ignore[return-value]


def _validate_capture(stage: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ObservationError(f"capture {stage} missing")
    expected_terminal = once.ACTION_OUTPUTS[3 if stage == "L3" else 4]
    terminal = value.get("terminal_evidence_path")
    if not isinstance(terminal, str):
        raise ObservationError(f"capture {stage} terminal path missing")
    terminal_path = Path(terminal)
    if not terminal_path.is_absolute():
        terminal_path = REPO_ROOT / terminal_path
    if terminal_path.resolve() != expected_terminal.resolve():
        raise ObservationError(f"capture {stage} terminal path differs")
    quality = value.get("quality")
    if not isinstance(quality, Mapping):
        raise ObservationError(f"capture {stage} quality missing")
    expected_quality = {
        "both_controller_rois_visible",
        "exposure_usable",
        "focus_usable",
        "glare_not_material",
    }
    if set(quality) != expected_quality or any(
        quality[key] not in CAPTURE_STATES for key in expected_quality
    ):
        raise ObservationError(f"capture {stage} quality differs")
    image_path = value.get("image_path")
    image_bytes = value.get("image_bytes")
    image_sha256 = value.get("image_sha256")
    if not isinstance(image_path, str) or not image_path:
        raise ObservationError(f"capture {stage} image path missing")
    if not isinstance(image_bytes, int) or isinstance(image_bytes, bool) or image_bytes <= 0:
        raise ObservationError(f"capture {stage} image byte count differs")
    if not isinstance(image_sha256, str) or len(image_sha256) != 64:
        raise ObservationError(f"capture {stage} image SHA-256 differs")
    return {
        "terminal_path": terminal_path,
        "quality_pass": all(quality[key] == "PASS" for key in expected_quality),
        "quality": deepcopy(dict(quality)),
        "image_binding": {
            "path": image_path,
            "bytes": image_bytes,
            "sha256": image_sha256,
        },
    }


def validate_observation_document(
    value: Mapping[str, Any], *, verify_terminal: bool
) -> dict[str, Any]:
    """Validate all 8x8 cells, recipe decoding, capture gates, and source IDs."""

    report = pack.build_report()
    if (
        value.get("schema_version") != 1
        or value.get("kind") != "mf1750-stable-code0-luma-latin-v3-observation-template"
        or value.get("campaign_id") != pack.CAMPAIGN_ID
        or value.get("contract_id") != report["contract_id"]
    ):
        raise ObservationError("observation root identity differs")
    thresholds = value.get("thresholds")
    if not isinstance(thresholds, Mapping) or set(thresholds) != set(DEFAULT_THRESHOLDS):
        raise ObservationError("threshold set differs")
    checked_thresholds = {
        key: _finite_number(thresholds[key], label=f"thresholds.{key}")
        for key in DEFAULT_THRESHOLDS
    }
    captures = value.get("captures")
    if not isinstance(captures, Mapping) or set(captures) not in ({"L3"}, {"L3", "L4"}):
        raise ObservationError("capture stage set differs")
    checked_captures = {
        stage: _validate_capture(stage, captures[stage]) for stage in captures
    }
    if verify_terminal:
        for stage, capture in checked_captures.items():
            terminal = once.validate_terminal_evidence(capture["terminal_path"])
            if terminal["ordinal"] != (3 if stage == "L3" else 4):
                raise ObservationError(f"capture {stage} terminal ordinal differs")
            capture["terminal"] = terminal

    recipes = _recipe_index()
    measurements = value.get("measurements")
    wanted_count = 128 * len(captures)
    if not isinstance(measurements, list) or len(measurements) != wanted_count:
        raise ObservationError("measurement count differs")
    checked: dict[tuple[str, str, int, int], dict[str, Any]] = {}
    for index, item in enumerate(measurements):
        if not isinstance(item, Mapping):
            raise ObservationError(f"measurement {index} root differs")
        stage = item.get("stage")
        controller = item.get("controller")
        row = item.get("physical_row")
        column = item.get("physical_column")
        if (
            stage not in captures
            or controller not in CONTROLLERS
            or not isinstance(row, int)
            or isinstance(row, bool)
            or not isinstance(column, int)
            or isinstance(column, bool)
            or not 0 <= row < 8
            or not 0 <= column < 8
        ):
            raise ObservationError(f"measurement {index} coordinate differs")
        key = (str(stage), str(controller), row, column)
        if key in checked:
            raise ObservationError(f"duplicate measurement {key}")
        recipe = recipes[(str(controller), row, column)]
        exact = {
            "controller_role": recipe["controller_role"],
            "logical_row": recipe["decoder"]["logical_row"],
            "logical_column": recipe["decoder"]["logical_column"],
            "decoder_transform": recipe["decoder"]["transform"],
            "recipe_id": recipe["recipe_id"],
            "middle_code": recipe["middle"]["code"],
            "panel_local_roi": recipe["local_roi"],
        }
        if any(item.get(name) != wanted for name, wanted in exact.items()):
            raise ObservationError(f"measurement {key} recipe binding differs")
        stripe = item.get("bottom_edge_stripe")
        if stripe not in STRIPE_STATES:
            raise ObservationError(f"measurement {key} stripe state differs")
        checked[key] = {
            "lab": _lab(item.get("lab"), label=f"measurement {key}"),
            "middle_code": recipe["middle"]["code"],
            "stripe": stripe,
        }
    expected_keys = {
        (stage, controller, row, column)
        for stage in captures
        for controller in CONTROLLERS
        for row in range(8)
        for column in range(8)
    }
    if set(checked) != expected_keys:
        raise ObservationError("measurement coordinate coverage differs")
    return {
        "thresholds": checked_thresholds,
        "captures": checked_captures,
        "measurements": checked,
    }


def evaluate_observations(
    value: Mapping[str, Any], *, verify_terminal: bool = True
) -> dict[str, Any]:
    """Evaluate luma/repeat/edge gates while keeping qualification at zero."""

    checked = validate_observation_document(value, verify_terminal=verify_terminal)
    thresholds = checked["thresholds"]
    measurements = checked["measurements"]
    per_controller: dict[str, Any] = {}
    any_stripe = False
    any_uncertain_stripe = False
    any_position_effect = False
    candidate_count = 0
    for controller in CONTROLLERS:
        stage_results: dict[str, Any] = {}
        for stage in checked["captures"]:
            groups: dict[int, list[tuple[float, float, float]]] = {
                code: [] for code in range(8)
            }
            stripe_counts = {state: 0 for state in STRIPE_STATES}
            for row in range(8):
                for column in range(8):
                    item = measurements[(stage, controller, row, column)]
                    groups[item["middle_code"]].append(item["lab"])
                    stripe_counts[item["stripe"]] += 1
            medians = {code: _median_lab(samples) for code, samples in groups.items()}
            repeat_ranges = {
                code: max(sample[0] for sample in samples)
                - min(sample[0] for sample in samples)
                for code, samples in groups.items()
            }
            l_values = [medians[code][0] for code in range(8)]
            between_delta_l = max(l_values) - min(l_values)
            chromas = {
                code: math.hypot(medians[code][1], medians[code][2])
                for code in range(8)
            }
            hues = {
                code: _hue(medians[code][1], medians[code][2])
                for code in range(8)
            }
            hue_codes = [
                code
                for code in range(8)
                if chromas[code] >= thresholds["minimum_chroma_for_hue_gate"]
            ]
            hue_span = max(
                (_angle_delta(hues[left], hues[right]) for left in hue_codes for right in hue_codes),
                default=0.0,
            )
            position_effect = any(
                span > thresholds["maximum_repeat_l_star_range"]
                for span in repeat_ranges.values()
            )
            same_hue = hue_span <= thresholds["maximum_same_hue_angle_degrees"]
            luma_candidate = (
                between_delta_l >= thresholds["minimum_between_middle_delta_l_star"]
                and same_hue
                and not position_effect
            )
            candidate_count += int(luma_candidate)
            any_position_effect |= position_effect
            any_stripe |= stripe_counts["PRESENT"] > 0
            any_uncertain_stripe |= stripe_counts["UNCERTAIN"] > 0
            stage_results[stage] = {
                "middle_median_lab": {
                    str(code): {
                        "l_star": medians[code][0],
                        "a_star": medians[code][1],
                        "b_star": medians[code][2],
                    }
                    for code in range(8)
                },
                "repeat_l_star_range": {str(code): repeat_ranges[code] for code in range(8)},
                "between_middle_delta_l_star": between_delta_l,
                "same_hue_angle_span_degrees": hue_span,
                "same_hue_gate_pass": same_hue,
                "position_effect_gate_pass": not position_effect,
                "luma_mechanism_review_candidate": luma_candidate,
                "bottom_edge_stripe_counts": stripe_counts,
            }
        repeat = None
        if "L4" in checked["captures"]:
            deltas_l: list[float] = []
            deltas_e: list[float] = []
            for row in range(8):
                for column in range(8):
                    l3 = measurements[("L3", controller, row, column)]["lab"]
                    l4 = measurements[("L4", controller, row, column)]["lab"]
                    deltas_l.append(abs(l4[0] - l3[0]))
                    deltas_e.append(math.sqrt(sum((l4[i] - l3[i]) ** 2 for i in range(3))))
            repeat = {
                "maximum_cell_delta_l_star": max(deltas_l),
                "maximum_cell_delta_e76": max(deltas_e),
                "gate_pass": (
                    max(deltas_l) <= thresholds["maximum_l3_l4_cell_delta_l_star"]
                    and max(deltas_e) <= thresholds["maximum_l3_l4_cell_delta_e76"]
                ),
            }
        per_controller[controller] = {
            "interpretation": (
                "CS2_RED_FAMILY_PRIMARY" if controller == "CS2" else "CS1_INTERNAL_CONTROL"
            ),
            "stages": stage_results,
            "l3_to_l4_repeat": repeat,
        }

    quality_pass = all(item["quality_pass"] for item in checked["captures"].values())
    repeat_fail = any(
        value["l3_to_l4_repeat"] is not None
        and value["l3_to_l4_repeat"]["gate_pass"] is not True
        for value in per_controller.values()
    )
    if any_stripe:
        decision = "REJECT_BOTTOM_EDGE_STRIPE_PRESENT"
    elif not quality_pass or any_uncertain_stripe:
        decision = "REVIEW_CAPTURE_OR_EDGE_QUALITY"
    elif repeat_fail:
        decision = "REVIEW_L3_L4_REPEAT_INSTABILITY"
    elif any_position_effect:
        decision = "REVIEW_POSITION_EFFECT"
    elif candidate_count:
        decision = "REVIEW_LUMA_MECHANISM_CANDIDATES"
    else:
        decision = "NO_SIGNIFICANT_LUMA_MECHANISM"
    return {
        "schema_version": 1,
        "kind": "mf1750-stable-code0-luma-latin-v3-observation-evaluation",
        "decision": decision,
        "campaign_id": pack.CAMPAIGN_ID,
        "contract_id": pack.build_report()["contract_id"],
        "controller_results": per_controller,
        "capture_quality_gate_pass": quality_pass,
        "qualified_colour_count": 0,
        "qualified_gray_levels": 0,
        "automatic_qualification_forbidden": True,
        "human_review_required_for_any_candidate": True,
        "hardware_accessed": False,
        "camera_accessed": False,
        "network_requests": 0,
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    template = sub.add_parser("template")
    template.add_argument("--l3-only", action="store_true")
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("observation", type=Path)
    evaluate.add_argument("--skip-terminal-validation", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "template":
            value = observation_template(include_l4=not args.l3_only)
        else:
            source = json.loads(args.observation.read_text(encoding="utf-8"))
            if not isinstance(source, Mapping):
                raise ObservationError("observation root is not an object")
            value = evaluate_observations(
                source,
                verify_terminal=not args.skip_terminal_validation,
            )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ObservationError) as error:
        print(f"stable-code0 observation error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
