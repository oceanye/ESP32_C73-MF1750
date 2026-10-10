#!/usr/bin/env python3
"""Offline LH3 dose-axis comparison: DOSE2 minus DOSE1 per (side, code column).

No device, network, relay or camera access. Inputs are the two extraction
documents produced by the LH2-style 10-frame 128-ROI photo pipeline (same
grid; column c carries code c) — one captured after DOSE1, one after DOSE2 —
plus the LH3 dose package contract. Because DOSE2's frame is byte-identical to
DOSE1's, the only independent variable between the two extractions is one
extra same-code application.

Per (controller, code): the 8 row cells give a median Lab endpoint per stage;
the paired per-frame deltas give a noise band max(5*MAD, CI95) for both
delta-L* and delta-E00 (CIEDE2000). Each column is judged by the frozen gate
MF1750_LIGHTNESS_TEST_V1_20260911 (|dL*|>=2, dE00>=3, |dh|<=5 deg):

  A  SATURATED    both deltas fall inside their noise bands (dose2 == dose1)
  B  DEEPENED     darker by the frozen gate, both deltas beat their noise
                  bands, hue stays within 5 degrees (dose = lightness knob)
  C  HUE_DRIFT    real colour change with hue difference over 5 degrees
                  (code-axis drift dominates; dose axis not directly usable)
  INCONCLUSIVE    anything else (below gate, lightening, failed quality)

Also emits the dose1 absolute endpoint table with reserved fields for the
later comparison against the bright-session LH2 MIDDLE endpoints.

Output: self-sealed (canonical SHA-256 integrity) dose-analysis.json plus a
short dose-report.md in the caller's --output-dir. The comparison core is a
pure function; only main() touches the filesystem.
"""
from __future__ import annotations

import argparse
import hashlib
from itertools import permutations
import json
import math
from pathlib import Path
import re
from statistics import median
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.color_pipeline.color import delta_e_ciede2000  # noqa: E402
from host.static_photo import lightness_history_lh3_dose as lh3dose  # noqa: E402
from host.static_photo.common import StaticPhotoContractError, attach_integrity, verify_integrity  # noqa: E402
from host.static_photo.lightness_test import THRESHOLDS  # noqa: E402

KIND = "mf1750-lh3-dose-analysis-v1"
RECIPE = re.compile(r"LH3D-S7-D([0-7])-R([0-7])")
MIDDLE_RECIPE = re.compile(r"LH1-S7-M([0-7])-T[37]")
CONTROLLERS = ("CS1", "CS2")
NOISE_SAMPLE_COUNT = THRESHOLDS["noise_sample_count_minimum"]  # 10 frames
# Student-t half-width factor for N=10 (df=9), same as the extraction pipeline.
CI95_T = 2.262
# Cross-session endpoint screening tolerance for the bright-MIDDLE comparison.
# NOT the frozen gate: the white-ratio calibration removes the session gain
# but not the camera's tone compression, and the dim session's chroma noise is
# larger; 5 L* / 10 degrees is a declared screening tolerance, recorded in
# the report.
MIDDLE_TOLERANCE = {"delta_lstar_max": 5.0, "hue_difference_max_degrees": 10.0}
GATE = {
    "gate_id": THRESHOLDS["version"],
    "minimum_delta_lstar": THRESHOLDS["minimum_delta_lstar"],
    "minimum_delta_e00": THRESHOLDS["minimum_delta_e00"],
    "maximum_hue_difference_degrees": THRESHOLDS["maximum_hue_difference_degrees"],
    "neutral_chroma_exclusive": THRESHOLDS["minimum_chroma_exclusive"],
    "noise_formula": "max(5*MAD, ci95_half_width) on paired per-frame deltas; "
                     "column band = max over the column's 8 cells",
}


class DoseAnalysisError(ValueError):
    """Malformed evidence, identity mismatch, or non-bindable contract."""


def _bind(path: Path) -> dict:
    data = Path(path).read_bytes()
    return {"path": str(Path(path).resolve()), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def _noise_band(deltas: list[float]) -> float:
    if len(deltas) < NOISE_SAMPLE_COUNT:
        raise DoseAnalysisError(
            f"noise requires at least {NOISE_SAMPLE_COUNT} paired frames")
    med = median(deltas)
    mad = median(abs(d - med) for d in deltas)
    mean = sum(deltas) / len(deltas)
    var = sum((d - mean) ** 2 for d in deltas) / (len(deltas) - 1)
    ci95 = CI95_T * math.sqrt(var) / math.sqrt(len(deltas))
    return max(5 * mad, ci95)


def _hue_delta(a: tuple[float, float, float], b: tuple[float, float, float]):
    # Same neutral-axis rule as the frozen lightness test: hue is undefined
    # when both endpoints sit inside the neutral chroma cylinder.
    if math.hypot(a[1], a[2]) <= GATE["neutral_chroma_exclusive"] and \
            math.hypot(b[1], b[2]) <= GATE["neutral_chroma_exclusive"]:
        return None
    difference = abs(math.degrees(math.atan2(a[2], a[1]) - math.atan2(b[2], b[1]))) % 360
    return min(difference, 360 - difference)


def judge_column(delta_lstar, delta_e00, hue_deg, noise_l, noise_e,
                 quality_pass=True):
    """Pure per-column verdict under the frozen gate; no I/O."""
    for name, value in (("delta_lstar", delta_lstar), ("delta_e00", delta_e00),
                        ("noise_l", noise_l), ("noise_e", noise_e)):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise DoseAnalysisError(f"{name} must be finite")
    if noise_l < 0 or noise_e < 0:
        raise DoseAnalysisError("noise bands must be >= 0")
    if hue_deg is not None and not 0 <= hue_deg <= 180:
        raise DoseAnalysisError("hue difference must be in 0..180 degrees or None")
    if quality_pass is not True:
        return {"verdict": "INCONCLUSIVE", "result_class": None,
                "reasons": ["QUALITY_OR_UNIFORMITY_FAILED"]}
    within_noise = abs(delta_lstar) <= noise_l and delta_e00 <= noise_e
    if within_noise:
        return {"verdict": "SATURATED", "result_class": "A",
                "reasons": ["DELTAS_WITHIN_NOISE_BAND"]}
    if hue_deg is not None and \
            hue_deg > GATE["maximum_hue_difference_degrees"] and \
            delta_e00 > noise_e:
        return {"verdict": "HUE_DRIFT", "result_class": "C",
                "reasons": ["HUE_DIFFERENCE_EXCEEDS_5_DEGREES_WITH_REAL_COLOR_CHANGE"]}
    reasons = []
    if delta_lstar > -GATE["minimum_delta_lstar"]:
        reasons.append("NOT_DARKER_BY_FROZEN_GATE")
    if abs(delta_lstar) <= noise_l:
        reasons.append("DELTA_L_WITHIN_NOISE")
    if delta_e00 < GATE["minimum_delta_e00"]:
        reasons.append("DELTA_E00_BELOW_FROZEN_GATE")
    if delta_e00 <= noise_e:
        reasons.append("DELTA_E00_WITHIN_NOISE")
    if hue_deg is not None and hue_deg > GATE["maximum_hue_difference_degrees"]:
        reasons.append("HUE_DIFFERENCE_EXCEEDS_5_DEGREES")
    if not reasons:
        return {"verdict": "DEEPENED", "result_class": "B",
                "reasons": ["DOSE2_DARKER_SAME_HUE_BEYOND_NOISE"],
                "hue_gate": "not_applicable_neutral" if hue_deg is None else "pass"}
    return {"verdict": "INCONCLUSIVE", "result_class": None, "reasons": reasons}


def _lab_triple(value, label):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise DoseAnalysisError(f"{label} must be a 3-component Lab triple")
    result = []
    for component in value:
        if isinstance(component, bool) or not isinstance(component, (int, float)) \
                or not math.isfinite(component):
            raise DoseAnalysisError(f"{label} components must be finite numbers")
        result.append(float(component))
    return tuple(result)


def _validate_extraction(value, action, contract_id, label):
    if not isinstance(value, dict) or not isinstance(value.get("rows"), list):
        raise DoseAnalysisError(f"{label}: extraction must be an object with rows")
    identity = value.get("identity")
    if not isinstance(identity, dict):
        raise DoseAnalysisError(f"{label}: identity must be an object")
    if identity.get("action_sha256") != action["action_id"]:
        raise DoseAnalysisError(f"{label}: identity action_sha256 does not bind "
                                f"the contract {action['stage']} action")
    if identity.get("frame_sha256") != action["frame"]["sha256"]:
        raise DoseAnalysisError(f"{label}: identity frame_sha256 does not bind "
                                f"the contract {action['stage']} frame")
    if "contract_id" in identity and identity["contract_id"] != contract_id:
        raise DoseAnalysisError(f"{label}: identity contract_id differs")
    rows = {}
    for index, row in enumerate(value["rows"]):
        if not isinstance(row, dict):
            raise DoseAnalysisError(f"{label}: row {index} must be an object")
        match = RECIPE.fullmatch(str(row.get("recipe_id")))
        controller = row.get("controller")
        if controller not in CONTROLLERS or match is None:
            raise DoseAnalysisError(f"{label}: row {index} controller/recipe malformed")
        code, grid_row = int(match.group(1)), int(match.group(2))
        if row.get("grid_col") != code or row.get("grid_row") != grid_row:
            raise DoseAnalysisError(f"{label}: row {index} grid position disagrees "
                                    "with recipe id")
        if row.get("comparison_id") != f"DOSE_C{code}":
            raise DoseAnalysisError(f"{label}: row {index} comparison_id differs")
        key = (controller, code, grid_row)
        if key in rows:
            raise DoseAnalysisError(f"{label}: duplicate cell {key}")
        lab_median = _lab_triple(row.get("lab_median"), f"{label} row {index} lab_median")
        samples = row.get("lab_samples")
        if not isinstance(samples, list) or len(samples) != NOISE_SAMPLE_COUNT:
            raise DoseAnalysisError(
                f"{label}: row {index} needs exactly {NOISE_SAMPLE_COUNT} Lab samples")
        samples = [_lab_triple(s, f"{label} row {index} sample") for s in samples]
        for flag in ("quality_pass", "single_pixel_uniform"):
            if row.get(flag) is not None and type(row[flag]) is not bool:
                raise DoseAnalysisError(f"{label}: row {index} {flag} must be bool or null")
        rows[key] = {"lab_median": lab_median, "lab_samples": samples,
                     "quality_pass": row.get("quality_pass") is True,
                     "single_pixel_uniform": row.get("single_pixel_uniform") is True}
    expected = {(c, code, r) for c in CONTROLLERS for code in range(8) for r in range(8)}
    if set(rows) != expected:
        raise DoseAnalysisError(f"{label}: extraction must cover exactly the 128 "
                                "(side, code, row) dose cells")
    return rows


def validate_contract(contract):
    if not isinstance(contract, dict) or \
            contract.get("kind") != "mf1750-lightness-history-firmware-contract-v1" or \
            contract.get("algorithm_id") != lh3dose.TEST_ID:
        raise DoseAnalysisError("not an LH3 dose firmware contract")
    body = {k: v for k, v in contract.items() if k != "contract_id"}
    stated = contract.get("contract_id")
    if not isinstance(stated, str) or lh3dose.digest(lh3dose.canonical(body)) != stated:
        raise DoseAnalysisError("contract identity digest mismatch")
    actions = contract.get("actions")
    if not isinstance(actions, list) or len(actions) != 3 or \
            [a.get("stage") for a in actions] != ["SOURCE", "DOSE1", "DOSE2"]:
        raise DoseAnalysisError("contract action chain differs")
    if actions[1]["frame"]["sha256"] != actions[2]["frame"]["sha256"]:
        raise DoseAnalysisError("contract DOSE2 frame is not byte-identical to DOSE1")
    return actions


def middle_endpoints(value):
    """Per (side, code) median Lab from the bright-session MIDDLE extraction."""
    rows = value.get("rows") if isinstance(value, dict) else None
    if not isinstance(rows, list):
        raise DoseAnalysisError("MIDDLE extraction must be an object with rows")
    groups: dict[tuple[str, int], list[tuple[float, float, float]]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise DoseAnalysisError(f"MIDDLE row {index} must be an object")
        match = MIDDLE_RECIPE.fullmatch(str(row.get("recipe_id")))
        controller = row.get("controller")
        if controller not in CONTROLLERS or match is None:
            raise DoseAnalysisError(f"MIDDLE row {index} controller/recipe malformed")
        key = (controller, int(match.group(1)))
        lab = _lab_triple(row.get("lab_median"), f"MIDDLE row {index} lab_median")
        groups.setdefault(key, []).append(lab)
    expected = {(c, code) for c in CONTROLLERS for code in range(8)}
    if set(groups) != expected or any(len(v) != 8 for v in groups.values()):
        raise DoseAnalysisError("MIDDLE extraction must cover 8 cells per (side, code)")
    return {key: tuple(median(lab[ch] for lab in labs) for ch in range(3))
            for key, labs in groups.items()}


def _hue_of(lab):
    return round(math.degrees(math.atan2(lab[2], lab[1])) % 360, 2)


def compare_middle_endpoints(dose1_centers, middle_centers):
    """Cross-session reproduction check against the bright MIDDLE endpoints.

    DOSE1's drive posture is identical to MIDDLE's (commented global header,
    active-white history, chain depth 2, codes 0..7), so same code should
    reproduce. The sessions differ in illumination, so each side is
    normalized by its own code-7 white column: a multiplicative gain
    (L7_middle / L7_dose1) maps the dim session's white onto the bright
    session's white. A ratio is used rather than a subtractive offset because
    the camera-relative pipeline scales the whole L* axis with exposure —
    the white point moves 65.8 -> 40 between sessions while dark codes move
    proportionally, not by a constant offset.

    Also runs the XOR-3 permutation warning: if the dose firmware's code axis
    drifted (c -> c^3), the xor3-remapped comparison would fit better than the
    identity one; a full 8! best-permutation diagnostic is included so any
    other systematic swap surfaces too.
    """
    per_code = []
    for controller in CONTROLLERS:
        white_dose = dose1_centers[(controller, 7)][0]
        white_middle = middle_centers[(controller, 7)][0]
        if white_dose <= 0 or white_middle <= 0:
            raise DoseAnalysisError("white reference L* must be positive")
        gain = white_middle / white_dose
        for code in range(8):
            lab_d = dose1_centers[(controller, code)]
            lab_m = middle_centers[(controller, code)]
            norm_l = lab_d[0] * gain
            delta_l = norm_l - lab_m[0]
            delta_h = _hue_delta(lab_d, lab_m)
            consistent = abs(delta_l) <= MIDDLE_TOLERANCE["delta_lstar_max"] and (
                delta_h is None
                or delta_h <= MIDDLE_TOLERANCE["hue_difference_max_degrees"])
            per_code.append({
                "controller": controller, "code": code,
                "white_gain_middle_over_dose1": round(gain, 5),
                "dose1_lab_median": [round(v, 4) for v in lab_d],
                "middle_lab_median": [round(v, 4) for v in lab_m],
                "dose1_lstar_normalized": round(norm_l, 4),
                "middle_lstar": round(lab_m[0], 4),
                "delta_lstar_normalized": round(delta_l, 4),
                "hue_dose1_degrees": _hue_of(lab_d),
                "hue_middle_degrees": _hue_of(lab_m),
                "delta_hue_degrees": None if delta_h is None else round(delta_h, 4),
                "consistent": consistent,
            })

    def cost(controller, perm):
        gain = (middle_centers[(controller, 7)][0]
                / dose1_centers[(controller, 7)][0])
        total = 0.0
        for code in range(8):
            total += abs(dose1_centers[(controller, code)][0] * gain
                         - middle_centers[(controller, perm[code])][0])
        return total

    diagnostics = {}
    for controller in CONTROLLERS:
        identity = tuple(range(8))
        xor3 = tuple(c ^ 3 for c in range(8))
        best = min(permutations(range(8)), key=lambda p: cost(controller, p))
        diagnostics[controller] = {
            "identity_cost_sum_abs_delta_lstar": round(cost(controller, identity), 3),
            "xor3_cost_sum_abs_delta_lstar": round(cost(controller, xor3), 3),
            "best_permutation": list(best),
            "best_permutation_cost": round(cost(controller, best), 3),
            "best_permutation_is_xor3": list(best) == list(xor3),
        }
    consistent_codes = sorted({c["code"] for c in per_code if c["consistent"]})
    per_side_consistent = {
        ctrl: sum(1 for c in per_code
                  if c["controller"] == ctrl and c["consistent"])
        for ctrl in CONTROLLERS
    }
    if all(n >= 7 for n in per_side_consistent.values()) and all(
            diagnostics[ctrl]["identity_cost_sum_abs_delta_lstar"]
            <= diagnostics[ctrl]["xor3_cost_sum_abs_delta_lstar"]
            for ctrl in CONTROLLERS):
        session_verdict = "REPRODUCED"
    elif any(diagnostics[ctrl]["best_permutation_is_xor3"] or
             diagnostics[ctrl]["xor3_cost_sum_abs_delta_lstar"]
             < diagnostics[ctrl]["identity_cost_sum_abs_delta_lstar"] - 8
             for ctrl in CONTROLLERS):
        session_verdict = "SUSPECTED_XOR3_PERMUTATION"
    else:
        session_verdict = "INCOMPARABLE"
    return {
        "status": "EVALUATED",
        "reference": "LH1 rebound bright-session MIDDLE endpoints "
                     "(commented header, active-white history, chain depth 2 — "
                     "identical drive posture to DOSE1)",
        "normalization": "per-side white-ratio gain L7_middle/L7_dose1; "
                         "multiplicative because camera-relative L* scales "
                         "with exposure rather than shifting by a constant",
        "screening_tolerance": {**MIDDLE_TOLERANCE,
                                "note": "declared cross-session screening "
                                        "tolerance, not the frozen optical gate"},
        "tolerance_is_not_frozen_gate": True,
        "per_code": per_code,
        "consistent_codes": consistent_codes,
        "per_side_consistent_count": per_side_consistent,
        "xor3_permutation_diagnostic": diagnostics,
        "session_verdict": session_verdict,
    }


def _extraction_context(value, rows, label):
    """Summarize detection/quality/session facts from one extraction document.

    Defensive: unit-test extractions carry only identity+rows, so every field
    degrades to None instead of failing the comparison.
    """
    frames = value.get("frames") if isinstance(value.get("frames"), list) else []
    per_ctrl = {}
    for ctrl in CONTROLLERS:
        detected, rmse, drift, ambiguous = [], [], [], 0
        for frame in frames:
            rep = frame.get(ctrl) if isinstance(frame, dict) else None
            if not isinstance(rep, dict):
                continue
            detected.append(rep.get("detected_cells"))
            if type(rep.get("reprojection_rmse_px")) in (int, float):
                rmse.append(rep["reprojection_rmse_px"])
            if type(rep.get("median_assignment_drift_px")) in (int, float):
                drift.append(rep["median_assignment_drift_px"])
            ambiguous += len(rep.get("ambiguous_assignment_cells_excluded") or [])
        per_ctrl[ctrl] = {
            "detected_cells_min": min(detected) if detected else None,
            "detected_cells_max": max(detected) if detected else None,
            "reprojection_rmse_px_median": median(rmse) if rmse else None,
            "median_assignment_drift_px_max": max(drift) if drift else None,
            "ambiguous_assignment_cells_excluded_total": ambiguous,
        }
    anchor = value.get("anchor_frame")
    quality_fail = [r for key, r in rows.items()
                    if not r["quality_pass"] or not r["single_pixel_uniform"]]
    return {
        "stage": value.get("dose_stage_contract", {}).get("stage")
        if isinstance(value.get("dose_stage_contract"), dict) else None,
        "analyzer_version": value.get("analyzer_version"),
        "live_result": value.get("live_result"),
        "mapping_inherited_from_sealed_middle_extraction":
            bool(value.get("mapping_source", {}).get(
                "inherited_from_sealed_middle_extraction"))
            if isinstance(value.get("mapping_source"), dict) else None,
        "cell_detection": value.get("cell_detection"),
        "frame_count": len(frames) if frames else None,
        "per_controller": per_ctrl,
        "anchor_frame_present": anchor is not None,
        "quality_or_uniformity_failed_cells": len(quality_fail),
        "quality_failed_cells_by_column": sorted(
            {f"{ctrl}/C{code}" for ctrl, code, _row in
             (k for k, r in rows.items()
              if not r["quality_pass"] or not r["single_pixel_uniform"])}),
    }


def compare(contract, dose1, dose2, middle=None):
    """Pure comparison core: two validated extractions -> unsigned report.

    When `middle` (the bright-session MIDDLE extraction document) is given,
    the dose1 absolute endpoints are additionally compared against the MIDDLE
    endpoints under per-side white-ratio normalization (XOR-3 check included).
    """
    actions = validate_contract(contract)
    rows1 = _validate_extraction(dose1, actions[1], contract["contract_id"], "dose1")
    rows2 = _validate_extraction(dose2, actions[2], contract["contract_id"], "dose2")
    middle_centers = middle_endpoints(middle) if middle is not None else None
    columns = []
    endpoints = []
    dose1_centers = {}
    for controller in CONTROLLERS:
        for code in range(8):
            cells1 = [rows1[(controller, code, r)] for r in range(8)]
            cells2 = [rows2[(controller, code, r)] for r in range(8)]
            center1 = tuple(median(c["lab_median"][ch] for c in cells1) for ch in range(3))
            center2 = tuple(median(c["lab_median"][ch] for c in cells2) for ch in range(3))
            dose1_centers[(controller, code)] = center1
            noise_l_cells, noise_e_cells = [], []
            for c1, c2 in zip(cells1, cells2, strict=True):
                deltas_l, deltas_e = [], []
                for s1, s2 in zip(c1["lab_samples"], c2["lab_samples"], strict=True):
                    deltas_l.append(s2[0] - s1[0])
                    deltas_e.append(delta_e_ciede2000(s1, s2))
                noise_l_cells.append(_noise_band(deltas_l))
                noise_e_cells.append(_noise_band(deltas_e))
            noise_l = max(noise_l_cells)
            noise_e = max(noise_e_cells)
            delta_lstar = center2[0] - center1[0]
            delta_e00 = delta_e_ciede2000(center1, center2)
            hue = _hue_delta(center1, center2)
            quality = all(c["quality_pass"] and c["single_pixel_uniform"]
                          for c in cells1 + cells2)
            verdict = judge_column(delta_lstar, delta_e00, hue, noise_l, noise_e,
                                   quality)
            columns.append({
                "controller": controller, "code": code, "cell_count": 8,
                "dose1_lab_median": [round(v, 4) for v in center1],
                "dose2_lab_median": [round(v, 4) for v in center2],
                "delta_lstar": round(delta_lstar, 4),
                "delta_e00": round(delta_e00, 4),
                "hue_difference_degrees": None if hue is None else round(hue, 4),
                "noise_delta_lstar": round(noise_l, 4),
                "noise_delta_e00": round(noise_e, 4),
                "quality_pass": quality,
                **verdict,
            })
            endpoints.append({
                "controller": controller, "code": code,
                "dose1_lab_median": [round(v, 4) for v in center1],
                "dose1_cell_lab_medians": [[round(v, 4) for v in c["lab_median"]]
                                           for c in cells1],
                "bright_middle_endpoint_comparison": {
                    "status": "NOT_EVALUATED",
                    "reference": "LH2 bright-session MIDDLE endpoints",
                    "reason": "fields reserved; requires the sealed bright MIDDLE "
                              "extraction, which is a separate batch",
                },
            })
    counts = {}
    for column in columns:
        counts[column["verdict"]] = counts.get(column["verdict"], 0) + 1
    middle_comparison = None
    if middle_centers is not None:
        middle_comparison = compare_middle_endpoints(dose1_centers, middle_centers)
        per_endpoint = {(c["controller"], c["code"]): c
                        for c in middle_comparison["per_code"]}
        for endpoint in endpoints:
            key = (endpoint["controller"], endpoint["code"])
            endpoint["bright_middle_endpoint_comparison"] = {
                "status": "EVALUATED",
                **{k: v for k, v in per_endpoint[key].items()
                   if k not in ("controller", "code")},
                "screening_tolerance": middle_comparison["screening_tolerance"],
            }
    # The code-7 commented white reference column doubles as the inter-batch
    # illumination/drift control: dose2's frame is identical, so any shift in
    # that column is session drift, not dose. A sub-gate systematic shift
    # there confounds small darkening readings on every other column.
    reference_shift = {
        c["controller"]: {"delta_lstar": c["delta_lstar"],
                          "delta_e00": c["delta_e00"],
                          "hue_difference_degrees": c["hue_difference_degrees"]}
        for c in columns if c["code"] == 7
    }
    max_ref_e00 = max(v["delta_e00"] for v in reference_shift.values())
    caveat = (
        "code-7 white reference column shows an inter-batch systematic shift "
        "below the frozen gate (max dE00 %.2f); per-frame paired noise does "
        "not include inter-batch drift, so small sub-gate darkening readings "
        "on other columns are confounded by it. Only effects clearly above "
        "both the noise band and this reference shift are dose evidence."
        % max_ref_e00)
    return {
        "kind": KIND,
        "test_id": lh3dose.TEST_ID,
        "contract_id": contract["contract_id"],
        "dose1_action_id": actions[1]["action_id"],
        "dose2_action_id": actions[2]["action_id"],
        "frame_sha256": actions[1]["frame"]["sha256"],
        "dose2_frame_byte_identical_to_dose1": True,
        "frozen_gate": GATE,
        "columns": columns,
        "dose1_absolute_endpoints": endpoints,
        "extraction_context": {
            "dose1": _extraction_context(dose1, rows1, "dose1"),
            "dose2": _extraction_context(dose2, rows2, "dose2"),
        },
        "middle_endpoint_comparison": middle_comparison,
        "summary": {"columns_total": 16,
                    "verdict_counts": counts,
                    "saturated_codes": sorted({c["code"] for c in columns
                                               if c["verdict"] == "SATURATED"}),
                    "deepened_codes": sorted({c["code"] for c in columns
                                              if c["verdict"] == "DEEPENED"}),
                    "hue_drift_codes": sorted({c["code"] for c in columns
                                               if c["verdict"] == "HUE_DRIFT"}),
                    "reference_column_shift": reference_shift,
                    "interpretation_caveat": caveat},
        "screen_only": True,
        "qualified_count": 0,
        "optical_verdict": "HOLD_FOR_REVIEW",
        "note": "Per-column dose judgement only; not a qualification or a "
                "live admission gate. Verdicts per side must agree before a "
                "code-level claim is made.",
    }


def render_markdown(report):
    lines = [
        "# LH3 剂量轴对比报告（DOSE2 − DOSE1）",
        "",
        f"- contract: `{report['contract_id']}`",
        f"- 冻结门: `{report['frozen_gate']['gate_id']}` "
        f"(|ΔL*|≥{report['frozen_gate']['minimum_delta_lstar']}, "
        f"ΔE00≥{report['frozen_gate']['minimum_delta_e00']}, "
        f"Δh≤{report['frozen_gate']['maximum_hue_difference_degrees']}°)",
        f"- 噪声带: {report['frozen_gate']['noise_formula']}",
        f"- 判决汇总: "
        + ", ".join(f"{k}={v}" for k, v in sorted(report["summary"]["verdict_counts"].items())),
        "",
        "| 侧 | 码 | ΔL* | ΔE00 | Δh(°) | 噪声ΔL* | 噪声ΔE00 | 判决 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in report["columns"]:
        hue = "n/a(neutral)" if c["hue_difference_degrees"] is None \
            else f"{c['hue_difference_degrees']:.2f}"
        lines.append(
            f"| {c['controller']} | C{c['code']} | {c['delta_lstar']:+.2f} "
            f"| {c['delta_e00']:.2f} | {hue} | {c['noise_delta_lstar']:.2f} "
            f"| {c['noise_delta_e00']:.2f} | {c['verdict']} |")
    ref = report["summary"]["reference_column_shift"]
    lines += [
        "",
        "## 采集上下文与质量门",
        "",
        f"- 判读警示: {report['summary']['interpretation_caveat']}",
        f"- 白参照列（码7）系统性偏移: "
        + ", ".join(f"{k}: ΔL*={v['delta_lstar']:+.2f}, ΔE00={v['delta_e00']:.2f}"
                    for k, v in sorted(ref.items())),
    ]
    for stage, ctx in sorted(report.get("extraction_context", {}).items()):
        if not ctx or ctx.get("frame_count") is None:
            continue
        det = ctx["per_controller"]
        bullet = (
            f"- {stage}: {ctx['frame_count']} 帧 + 锚帧"
            f"{'有' if ctx['anchor_frame_present'] else '无'}；检测格数 "
            + " / ".join(f"{ctrl} {v['detected_cells_min']}..{v['detected_cells_max']}/64"
                         f"(RMSE≤{v['reprojection_rmse_px_median']:.2f}px)"
                         for ctrl, v in sorted(det.items()))
            + f"；质量/均匀性失败格 {ctx['quality_or_uniformity_failed_cells']}"
            + (f"（{', '.join(ctx['quality_failed_cells_by_column'])}）"
               if ctx["quality_failed_cells_by_column"] else ""))
        if ctx.get("cell_detection") and ctx["cell_detection"].get("method"):
            bullet += f"；检测: {ctx['cell_detection']['method']}"
        lines.append(bullet)
        if ctx.get("cell_detection") and ctx["cell_detection"].get("reason"):
            lines.append(f"  - 会话注记: {ctx['cell_detection']['reason']}")
    lines += [
        "",
        "## DOSE1 绝对端点（亮光 MIDDLE 对照）",
        "",
    ]
    middle = report.get("middle_endpoint_comparison")
    if middle:
        lines += [
            f"- 会话判决: **{middle['session_verdict']}**；归一化: {middle['normalization']}",
            f"- 筛查容差（非冻结门）: |ΔL*|≤{middle['screening_tolerance']['delta_lstar_max']}"
            f"、Δh≤{middle['screening_tolerance']['hue_difference_max_degrees']}°",
            "",
            "| 侧 | 码 | dose1 L* | 归一化L* | MIDDLE L* | ΔL*归一 | dose1色相° | MIDDLE色相° | Δh° | 一致 |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for c in middle["per_code"]:
            dh = "n/a" if c["delta_hue_degrees"] is None else f"{c['delta_hue_degrees']:.2f}"
            lines.append(
                f"| {c['controller']} | C{c['code']} | {c['dose1_lab_median'][0]:.2f} "
                f"| {c['dose1_lstar_normalized']:.2f} | {c['middle_lstar']:.2f} "
                f"| {c['delta_lstar_normalized']:+.2f} | {c['hue_dose1_degrees']:.0f} "
                f"| {c['hue_middle_degrees']:.0f} | {dh} "
                f"| {'✓' if c['consistent'] else '✗'} |")
        lines.append("")
        for ctrl, diag in sorted(middle["xor3_permutation_diagnostic"].items()):
            lines.append(
                f"- {ctrl} 置换诊断: identity cost {diag['identity_cost_sum_abs_delta_lstar']:.2f}"
                f" vs xor3 cost {diag['xor3_cost_sum_abs_delta_lstar']:.2f}"
                f"；最优置换 {diag['best_permutation']}（cost {diag['best_permutation_cost']:.2f}）"
                + ("——**最优置换正是 c→c^3！**" if diag["best_permutation_is_xor3"] else ""))
    else:
        lines.append("- MIDDLE 对照: NOT_EVALUATED（字段预留，未提供 --middle-extraction）")
    lines += [
        "",
        "| 侧 | 码 | dose1 L* | dose1 a* | dose1 b* |",
        "|---|---|---|---|---|",
    ]
    for e in report["dose1_absolute_endpoints"]:
        lab = e["dose1_lab_median"]
        lines.append(f"| {e['controller']} | C{e['code']} "
                     f"| {lab[0]:.2f} | {lab[1]:.2f} | {lab[2]:.2f} |")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True,
                        help="LH3 dose package directory (contract.json inside)")
    parser.add_argument("--dose1-extraction", type=Path, required=True,
                        help="extraction.json from the post-DOSE1 10-frame batch")
    parser.add_argument("--dose2-extraction", type=Path, required=True,
                        help="extraction.json from the post-DOSE2 10-frame batch")
    parser.add_argument("--middle-extraction", type=Path, default=None,
                        help="optional bright-session MIDDLE extraction.json for "
                             "the dose1 absolute-endpoint cross-session comparison")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise SystemExit("output dir must not exist (O_EXCL batch)")
    contract_path = args.package / "contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    dose1 = json.loads(args.dose1_extraction.read_text(encoding="utf-8"))
    dose2 = json.loads(args.dose2_extraction.read_text(encoding="utf-8"))
    middle = None
    if args.middle_extraction is not None:
        middle = json.loads(args.middle_extraction.read_text(encoding="utf-8"))
    try:
        verify_integrity(dose1, "dose1 extraction")
        verify_integrity(dose2, "dose2 extraction")
        if middle is not None and "integrity" in middle:
            verify_integrity(middle, "middle extraction")
        report = compare(contract, dose1, dose2, middle=middle)
    except (DoseAnalysisError, StaticPhotoContractError) as error:
        raise SystemExit(f"FAIL_STOP: {error}")
    report["inputs"] = {"contract": _bind(contract_path),
                        "dose1_extraction": _bind(args.dose1_extraction),
                        "dose2_extraction": _bind(args.dose2_extraction)}
    if args.middle_extraction is not None:
        report["inputs"]["middle_extraction"] = _bind(args.middle_extraction)
    report["hardware_accessed"] = False
    report["network_accessed"] = False
    sealed = attach_integrity(report)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    analysis = args.output_dir / "dose-analysis.json"
    analysis.write_text(json.dumps(sealed, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    (args.output_dir / "dose-report.md").write_text(
        render_markdown(sealed), encoding="utf-8")
    print(json.dumps({"result": "PASS", "output": str(analysis),
                      "verdict_counts": sealed["summary"]["verdict_counts"],
                      "hardware_accessed": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
