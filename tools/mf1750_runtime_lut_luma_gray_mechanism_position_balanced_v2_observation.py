#!/usr/bin/env python3
"""Offline 48MP observation manifest/evaluator for position-balanced V2.

This tool never opens a camera or contacts the device.  It binds already
captured files, emits the exact 128 central cell ROIs, and evaluates supplied
Lab/defect observations.  Passing gates creates candidates only; it can never
qualify a colour, neutral, gray level, or brightness level.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v2_once as runner,
)
from tools import (  # noqa: E402
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v2_pack as pack,
)


class ObservationError(RuntimeError):
    """Raised when an offline observation envelope is incomplete or altered."""


KIND = "mf1750-luma-gray-mechanism-position-balanced-v2-camera-observation"
RESULT_KIND = f"{KIND}-evaluation"
MAX_POSITION_DELTA_E76 = 8.0
MAX_REPEAT_DELTA_E76 = 8.0
MAX_NEUTRAL_CHROMA = 10.0
MIN_MECHANISM_DELTA_L = 4.0


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_new(path: Path, value: Mapping[str, Any]) -> None:
    body = deepcopy(dict(value))
    body["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": _sha(_canonical(body)),
    }
    payload = json.dumps(
        body, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, payload)
    finally:
        os.close(descriptor)


def _read_integrity(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ObservationError(f"{label} missing or unsafe")
    try:
        value = json.loads(path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ObservationError(f"{label} is not UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ObservationError(f"{label} root differs")
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    if (
        not isinstance(integrity, Mapping)
        or integrity.get("algorithm") != "sha256-canonical-json-without-integrity"
        or integrity.get("sha256") != _sha(_canonical(body))
    ):
        raise ObservationError(f"{label} integrity differs")
    return value


def roi_manifest() -> dict[str, Any]:
    report = pack.build_report()
    samples: list[dict[str, Any]] = []
    for controller, mapping in (("CS1", pack.CS1_RECIPE_AT_CELL), ("CS2", pack.CS2_RECIPE_AT_CELL)):
        counts = {recipe: 0 for recipe in range(16)}
        for cell, recipe in enumerate(mapping):
            row, column = divmod(cell, 8)
            repeat = counts[recipe]
            counts[recipe] += 1
            x = pack.GRID_X0 + column * (pack.CELL_WIDTH + pack.GAP_X)
            y = pack.GRID_Y0 + row * (pack.CELL_HEIGHT + pack.GAP_Y)
            samples.append(
                {
                    "sample_id": f"{controller}-R{recipe:02d}-P{repeat}",
                    "controller": controller,
                    "recipe": recipe,
                    "repeat_position": repeat,
                    "row": row,
                    "column": column,
                    "local_roi": {"x": x, "y": y, "width": pack.CELL_WIDTH, "height": pack.CELL_HEIGHT},
                    "panel_roi": {
                        "x": x + (0 if controller == "CS1" else 512),
                        "y": y,
                        "width": pack.CELL_WIDTH,
                        "height": pack.CELL_HEIGHT,
                    },
                    "central_inset_fraction": 0.20,
                }
            )
    return {
        "schema_version": 1,
        "kind": f"{KIND}-roi-manifest",
        "offline_only": True,
        "contract_id": report["contract_id"],
        "geometry": deepcopy(report["contract"]["geometry"]),
        "samples": samples,
        "sample_count": len(samples),
        "controller_policy": "CS1_AND_CS2_EVALUATED_SEPARATELY",
        "g3_g4_policy": "PAIR_ONLY_IF_BOTH_INDEPENDENT_ACTION_CAPTURES_EXIST",
        "qualified_colour_count": 0,
    }


def _file_binding(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ObservationError(f"{label} missing or unsafe")
    payload = path.read_bytes()
    return {"path": str(path.resolve()), "bytes": len(payload), "file_sha256": _sha(payload)}


def make_template(
    *, action_evidence: Path, capture: Path, capture_sidecar: Path, output: Path
) -> dict[str, Any]:
    deep = runner.validate_terminal_evidence(action_evidence)
    if deep["ordinal"] not in (3, 4):
        raise ObservationError("camera observation accepts only G3 or G4 COMPLETE")
    sidecar = _read_integrity(capture_sidecar, label="capture sidecar")
    manifest = roi_manifest()
    measurements = []
    for sample in manifest["samples"]:
        measurements.append(
            {
                **sample,
                "lab": None,
                "bottom_edge_clean": None,
                "horizontal_stripe_absent": None,
                "vertical_stripe_absent": None,
                "roi_visible": None,
                "operator_note": None,
            }
        )
    value = {
        "schema_version": 1,
        "kind": KIND,
        "state": "UNOBSERVED_TEMPLATE",
        "offline_only": True,
        "action_evidence": {
            **deep,
            **_file_binding(action_evidence, label="action evidence"),
        },
        "capture": _file_binding(capture, label="capture"),
        "capture_sidecar": {
            **_file_binding(capture_sidecar, label="capture sidecar"),
            "canonical_integrity_sha256": sidecar["integrity"]["sha256"],
        },
        "roi_manifest_sha256": _sha(_canonical(manifest)),
        "measurements": measurements,
        "thresholds": {
            "max_position_delta_e76": MAX_POSITION_DELTA_E76,
            "max_g3_g4_repeat_delta_e76": MAX_REPEAT_DELTA_E76,
            "max_neutral_chroma": MAX_NEUTRAL_CHROMA,
            "min_mechanism_delta_l": MIN_MECHANISM_DELTA_L,
        },
        "required_defect_gates": [
            "bottom_edge_clean",
            "horizontal_stripe_absent",
            "vertical_stripe_absent",
        ],
        "qualified_colour_count": 0,
        "automatic_colour_qualification": False,
    }
    _write_new(output, value)
    return value


def _lab(value: Any) -> tuple[float, float, float] | None:
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value)
        or any(not math.isfinite(float(item)) for item in value)
    ):
        raise ObservationError("Lab value must be null or three finite numbers")
    return tuple(float(item) for item in value)


def _delta_e(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((left - right) ** 2 for left, right in zip(a, b, strict=True)))


def evaluate(input_path: Path, output: Path, *, repeat_input: Path | None = None) -> dict[str, Any]:
    value = _read_integrity(input_path, label="observation")
    manifest = roi_manifest()
    expected = {item["sample_id"]: item for item in manifest["samples"]}
    observed = value.get("measurements")
    if not isinstance(observed, list) or len(observed) != 128:
        raise ObservationError("observation must contain exactly 128 samples")
    indexed = {item.get("sample_id"): item for item in observed if isinstance(item, Mapping)}
    if set(indexed) != set(expected):
        raise ObservationError("observation sample identity set differs")
    recipe_results: list[dict[str, Any]] = []
    missing = 0
    defect_failures = 0
    for controller in ("CS1", "CS2"):
        for recipe in range(16):
            samples = [indexed[f"{controller}-R{recipe:02d}-P{repeat}"] for repeat in range(4)]
            labs = [_lab(item.get("lab")) for item in samples]
            complete = all(lab is not None and item.get("roi_visible") is True for lab, item in zip(labs, samples, strict=True))
            defects_ok = all(
                item.get(key) is True
                for item in samples
                for key in ("bottom_edge_clean", "horizontal_stripe_absent", "vertical_stripe_absent")
            )
            if not complete:
                missing += 1
            if not defects_ok:
                defect_failures += 1
            dispersion = None
            mean_lab = None
            if complete:
                typed = [lab for lab in labs if lab is not None]
                mean_lab = [sum(lab[index] for lab in typed) / 4 for index in range(3)]
                dispersion = max(_delta_e(left, right) for left in typed for right in typed)
            recipe_results.append(
                {
                    "controller": controller,
                    "recipe": recipe,
                    "complete_4_of_4": complete,
                    "defect_gates_pass": defects_ok,
                    "max_position_delta_e76": dispersion,
                    "position_balanced": dispersion is not None and dispersion <= MAX_POSITION_DELTA_E76,
                    "mean_lab": mean_lab,
                    "mean_chroma": None if mean_lab is None else math.hypot(mean_lab[1], mean_lab[2]),
                    "mean_hue_degrees": (
                        None
                        if mean_lab is None
                        else (math.degrees(math.atan2(mean_lab[2], mean_lab[1])) % 360.0)
                    ),
                    "neutral_candidate": mean_lab is not None and math.hypot(mean_lab[1], mean_lab[2]) <= MAX_NEUTRAL_CHROMA,
                }
            )
    mechanism_groups: list[dict[str, Any]] = []
    for controller in ("CS1", "CS2"):
        for target_code, recipes in ((3, range(0, 8)), (7, range(8, 16))):
            rows = [
                item
                for item in recipe_results
                if item["controller"] == controller and item["recipe"] in recipes
            ]
            l_values = [item["mean_lab"][0] for item in rows if item["mean_lab"] is not None]
            delta_l = None if len(l_values) != 8 else max(l_values) - min(l_values)
            mechanism_groups.append(
                {
                    "controller": controller,
                    "target_code": target_code,
                    "complete": len(l_values) == 8,
                    "lstar_span": delta_l,
                    "mechanism_delta_l_candidate": delta_l is not None and delta_l >= MIN_MECHANISM_DELTA_L,
                }
            )
    repeat_binding = None
    repeat_gate = None
    if repeat_input is not None:
        repeat = _read_integrity(repeat_input, label="G4 repeat observation")
        if value.get("action_evidence", {}).get("ordinal") != 3 or repeat.get("action_evidence", {}).get("ordinal") != 4:
            raise ObservationError("repeat comparison requires G3 input and G4 repeat")
        repeat_binding = _file_binding(repeat_input, label="G4 repeat observation")
        repeated = repeat.get("measurements")
        if not isinstance(repeated, list) or len(repeated) != 128:
            raise ObservationError("G4 repeat must contain exactly 128 samples")
        repeated_index = {
            item.get("sample_id"): item for item in repeated if isinstance(item, Mapping)
        }
        if set(repeated_index) != set(expected):
            raise ObservationError("G4 repeat sample identity set differs")
        deltas = []
        for sample_id in sorted(expected):
            left = _lab(indexed[sample_id].get("lab"))
            right = _lab(repeated_index[sample_id].get("lab"))
            if left is None or right is None:
                raise ObservationError("G3/G4 repeat comparison requires all Lab values")
            deltas.append(_delta_e(left, right))
        repeat_gate = {
            "sample_count": len(deltas),
            "max_delta_e76": max(deltas),
            "threshold": MAX_REPEAT_DELTA_E76,
            "passed": max(deltas) <= MAX_REPEAT_DELTA_E76,
        }
    all_complete = missing == 0
    all_defects_clean = defect_failures == 0
    all_position_balanced = all(item["position_balanced"] for item in recipe_results)
    repeat_ok = repeat_gate is None or repeat_gate["passed"]
    mechanism_detected = any(
        item["mechanism_delta_l_candidate"] for item in mechanism_groups
    )
    state = (
        "CANDIDATE_MECHANISM_PASS_REQUIRES_HUMAN_REVIEW"
        if all_complete
        and all_defects_clean
        and all_position_balanced
        and repeat_ok
        and mechanism_detected
        else "REVIEW"
    )
    result = {
        "schema_version": 1,
        "kind": RESULT_KIND,
        "state": state,
        "offline_only": True,
        "source_observation": _file_binding(input_path, label="observation"),
        "repeat_observation": repeat_binding,
        "controller_policy": "CS1_AND_CS2_NOT_MERGED",
        "recipe_results": recipe_results,
        "mechanism_groups": mechanism_groups,
        "g3_g4_repeat_gate": repeat_gate,
        "summary": {
            "incomplete_controller_recipes": missing,
            "controller_recipes_with_edge_or_stripe_failure": defect_failures,
            "all_position_balanced": all_position_balanced,
            "g3_g4_repeat_evaluated": repeat_input is not None,
            "g3_g4_repeat_passed": repeat_gate["passed"] if repeat_gate else None,
            "any_delta_l_mechanism_candidate": mechanism_detected,
        },
        "qualified_colour_count": 0,
        "qualified_gray_levels": 0,
        "qualified_brightness_levels": 0,
        "automatic_colour_qualification": False,
        "human_and_calibrated_followup_required": True,
    }
    _write_new(output, result)
    return result


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("manifest")
    template = sub.add_parser("template", allow_abbrev=False)
    template.add_argument("--action-evidence", type=Path, required=True)
    template.add_argument("--capture", type=Path, required=True)
    template.add_argument("--capture-sidecar", type=Path, required=True)
    template.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("evaluate", allow_abbrev=False)
    check.add_argument("--input", type=Path, required=True)
    check.add_argument("--repeat-input", type=Path)
    check.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "manifest":
            result = roi_manifest()
        elif args.command == "template":
            result = make_template(
                action_evidence=args.action_evidence,
                capture=args.capture,
                capture_sidecar=args.capture_sidecar,
                output=args.output,
            )
        else:
            result = evaluate(args.input, args.output, repeat_input=args.repeat_input)
    except (ObservationError, OSError, RuntimeError) as error:
        print(f"LUMA/GRAY V2 observation error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
