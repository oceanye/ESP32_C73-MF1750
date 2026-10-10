"""LH3 dose analysis tests; fully offline, synthetic extraction documents."""
from __future__ import annotations

import json
from pathlib import Path
from statistics import median
import subprocess
import sys

import pytest

from host.static_photo.common import verify_integrity
from tools import mf1750_lh3_dose_analysis as da

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / ".test-output/offline/LH3_DOSE_20260924_R2"


@pytest.fixture(scope="module")
def contract():
    return json.loads((PACKAGE / "contract.json").read_text(encoding="utf-8"))


def build_extraction(contract, action_index, lab_fn, quality=True):
    """lab_fn(controller, code, row, frame_index) -> (L, a, b) per-frame sample."""
    action = contract["actions"][action_index]
    rows = []
    for controller in ("CS1", "CS2"):
        for code in range(8):
            for row in range(8):
                samples = [lab_fn(controller, code, row, j)
                           for j in range(da.NOISE_SAMPLE_COUNT)]
                med = [median(s[ch] for s in samples) for ch in range(3)]
                rows.append({
                    "controller": controller, "recipe_id": f"LH3D-S7-D{code}-R{row}",
                    "comparison_id": f"DOSE_C{code}", "grid_row": row, "grid_col": code,
                    "position": ("T" if row < 4 else "B") + ("L" if code < 4 else "R"),
                    "lab_median": med,
                    "lab_samples": [list(s) for s in samples],
                    "quality_pass": quality and code != 4,
                    "single_pixel_uniform": True,
                })
    return {"identity": {"action_sha256": action["action_id"],
                         "frame_sha256": action["frame"]["sha256"],
                         "contract_id": contract["contract_id"]},
            "rows": rows}


def const_lab(lab):
    return lambda controller, code, row, j: lab


# Mixed screen: A=code0/7 (identical), B=code1 (same-hue darkening) and code6
# (neutral darkening, hue n/a), C=code2 (45-degree hue turn), code3 lightening,
# code4 quality failure, code5 below the frozen gate -> all INCONCLUSIVE.
DOSE1_LAB = const_lab((50.0, 30.0, 0.0))
DOSE2_LAB_BY_CODE = {
    0: (50.0, 30.0, 0.0),
    1: (46.0, 31.0, 0.0),
    2: (50.0, 21.213, 21.213),
    3: (54.0, 31.0, 0.0),
    4: (46.0, 31.0, 0.0),
    5: (48.7, 30.0, 0.0),
    6: (45.0, 30.5, 0.0),
    7: (50.0, 30.0, 0.0),
}
# code 6 must stay neutral on both stages for the hue-undefined path.
DOSE1_LAB_NEUTRAL6 = lambda controller, code, row, j: \
    (60.0, 0.0, 0.0) if code == 6 else (50.0, 30.0, 0.0)
DOSE2_LAB_MIXED = lambda controller, code, row, j: \
    (55.0, 0.5, 0.0) if code == 6 else DOSE2_LAB_BY_CODE[code]


@pytest.fixture(scope="module")
def report(contract):
    dose1 = build_extraction(contract, 1, DOSE1_LAB_NEUTRAL6)
    dose2 = build_extraction(contract, 2, DOSE2_LAB_MIXED)
    return da.compare(contract, dose1, dose2)


def test_judge_column_boundaries():
    # Frozen gate is inclusive: |dL*|=2, dE00=3, dh=5 exactly -> DEEPENED.
    assert da.judge_column(-2.0, 3.0, 0.0, 0.5, 0.5)["verdict"] == "DEEPENED"
    assert da.judge_column(-2.0, 3.0, 5.0, 0.5, 0.5)["verdict"] == "DEEPENED"
    # Hue one tick over 5 degrees with a real colour change -> HUE_DRIFT.
    assert da.judge_column(-2.0, 3.0, 5.0001, 0.5, 0.5)["verdict"] == "HUE_DRIFT"
    # Noise band is inclusive: both deltas exactly at the band -> SATURATED.
    assert da.judge_column(-1.0, 1.0, None, 1.0, 1.5)["verdict"] == "SATURATED"
    # One delta one tick outside its band and below the frozen gate -> INCONCLUSIVE.
    result = da.judge_column(-1.0, 1.0, None, 0.999, 1.5)
    assert result["verdict"] == "INCONCLUSIVE"
    assert "DELTA_L_WITHIN_NOISE" not in result["reasons"]
    # Large shift swallowed by a larger noise band -> SATURATED (A).
    assert da.judge_column(-4.0, 6.0, 0.0, 4.0, 6.5)["verdict"] == "SATURATED"
    # ...but if only the L* band is exceeded while dE00 stays in noise: INCONCLUSIVE.
    result = da.judge_column(-4.0, 6.0, 0.0, 3.999, 7.0)
    assert result["verdict"] == "INCONCLUSIVE"
    assert "DELTA_E00_WITHIN_NOISE" in result["reasons"]
    # Lightening is never DEEPENED.
    result = da.judge_column(4.0, 6.0, 0.0, 0.5, 0.5)
    assert result["verdict"] == "INCONCLUSIVE"
    assert "NOT_DARKER_BY_FROZEN_GATE" in result["reasons"]
    # Neutral endpoints: hue not applicable, darkening still判 B.
    result = da.judge_column(-4.0, 6.0, None, 0.5, 0.5)
    assert result["verdict"] == "DEEPENED"
    assert result["hue_gate"] == "not_applicable_neutral"
    # Quality failure short-circuits to INCONCLUSIVE.
    assert da.judge_column(-4.0, 6.0, 0.0, 0.5, 0.5, quality_pass=False)["verdict"] == "INCONCLUSIVE"
    with pytest.raises(da.DoseAnalysisError):
        da.judge_column(-2.0, 3.0, 0.0, -0.1, 0.5)
    with pytest.raises(da.DoseAnalysisError):
        da.judge_column(-2.0, 3.0, 181.0, 0.5, 0.5)


def test_compare_mixed_screen_verdicts(report):
    assert report["kind"] == da.KIND
    assert report["dose2_frame_byte_identical_to_dose1"] is True
    by = {(c["controller"], c["code"]): c for c in report["columns"]}
    assert len(by) == 16
    for controller in ("CS1", "CS2"):
        assert by[controller, 0]["verdict"] == "SATURATED"
        assert by[controller, 0]["result_class"] == "A"
        b = by[controller, 1]
        assert b["verdict"] == "DEEPENED" and b["result_class"] == "B"
        assert b["delta_lstar"] == pytest.approx(-4.0)
        assert b["delta_e00"] >= 3.0
        assert b["hue_difference_degrees"] == pytest.approx(0.0, abs=0.01)
        c = by[controller, 2]
        assert c["verdict"] == "HUE_DRIFT" and c["result_class"] == "C"
        assert c["hue_difference_degrees"] == pytest.approx(45.0, abs=0.1)
        assert by[controller, 3]["verdict"] == "INCONCLUSIVE"  # lightening
        q = by[controller, 4]
        assert q["verdict"] == "INCONCLUSIVE" and q["quality_pass"] is False
        assert q["reasons"] == ["QUALITY_OR_UNIFORMITY_FAILED"]
        below = by[controller, 5]
        assert below["verdict"] == "INCONCLUSIVE"
        assert "DELTA_E00_BELOW_FROZEN_GATE" in below["reasons"]
        neutral = by[controller, 6]
        assert neutral["verdict"] == "DEEPENED"
        assert neutral["hue_difference_degrees"] is None
        assert by[controller, 7]["verdict"] == "SATURATED"
    counts = report["summary"]["verdict_counts"]
    assert counts == {"SATURATED": 4, "DEEPENED": 4, "HUE_DRIFT": 2,
                      "INCONCLUSIVE": 6}
    assert report["summary"]["deepened_codes"] == [1, 6]
    assert report["summary"]["hue_drift_codes"] == [2]
    assert report["summary"]["saturated_codes"] == [0, 7]


def test_noise_band_from_paired_frame_deltas(contract):
    # Same -4 L* shift but alternating per frame (-10/+2): the shift is real
    # yet unstable, so the noise band swallows it -> SATURATED.
    shifts = [-10.0, 2.0]
    dose1 = build_extraction(contract, 1, DOSE1_LAB)
    dose2 = build_extraction(
        contract, 2,
        lambda controller, code, row, j: (50.0 + shifts[j % 2], 30.0, 0.0))
    report = da.compare(contract, dose1, dose2)
    column = next(c for c in report["columns"]
                  if c["controller"] == "CS1" and c["code"] == 0)
    assert column["delta_lstar"] == pytest.approx(-4.0)
    assert column["noise_delta_lstar"] >= 30.0  # 5 * MAD of the alternating deltas
    assert column["verdict"] == "SATURATED"
    # A steady -4 shift has a near-zero band and clears the gate.
    dose2_steady = build_extraction(contract, 2, const_lab((46.0, 30.0, 0.0)))
    steady = da.compare(contract, dose1, dose2_steady)
    column = next(c for c in steady["columns"]
                  if c["controller"] == "CS1" and c["code"] == 0)
    assert column["noise_delta_lstar"] == pytest.approx(0.0)
    assert column["verdict"] == "DEEPENED"
    assert column["hue_difference_degrees"] == pytest.approx(0.0, abs=0.01)


def test_dose1_absolute_endpoint_table(report):
    endpoints = {(e["controller"], e["code"]): e
                 for e in report["dose1_absolute_endpoints"]}
    assert len(endpoints) == 16
    cell = endpoints["CS1", 1]
    assert cell["dose1_lab_median"] == pytest.approx([50.0, 30.0, 0.0])
    assert len(cell["dose1_cell_lab_medians"]) == 8
    assert cell["bright_middle_endpoint_comparison"]["status"] == "NOT_EVALUATED"
    neutral = endpoints["CS2", 6]
    assert neutral["dose1_lab_median"] == pytest.approx([60.0, 0.0, 0.0])


def build_middle(lab_fn):
    """lab_fn(controller, code) -> Lab triple for the bright MIDDLE session."""
    rows = []
    for controller in ("CS1", "CS2"):
        for code in range(8):
            for target in (3, 7):
                for position in ("TL", "TR", "BL", "BR"):
                    rows.append({"recipe_id": f"LH1-S7-M{code}-T{target}",
                                 "controller": controller, "position": position,
                                 "lab_median": list(lab_fn(controller, code))})
    return {"rows": rows}


DOSE1_CENTERS = {(ctrl, code): ((60.0, 0.0, 0.0) if code == 6 else
                                (40.0, 30.0, 0.0) if code == 7 else
                                (50.0 - code, 25.0, 5.0 * code))
                 for ctrl in ("CS1", "CS2") for code in range(8)}
GAIN = 65.8 / 40.0


def test_middle_endpoints_parsing_and_validation():
    middle = build_middle(lambda ctrl, code: (30.0 + code, 10.0, -5.0))
    centers = da.middle_endpoints(middle)
    assert len(centers) == 16
    assert centers["CS1", 3] == pytest.approx((33.0, 10.0, -5.0))
    bad = build_middle(lambda ctrl, code: (30.0, 10.0, -5.0))
    bad["rows"][0]["recipe_id"] = "LH2-S7-M0-H0"
    with pytest.raises(da.DoseAnalysisError, match="malformed|cover"):
        da.middle_endpoints(bad)
    bad = build_middle(lambda ctrl, code: (30.0, 10.0, -5.0))["rows"][:-8]
    with pytest.raises(da.DoseAnalysisError, match="cover"):
        da.middle_endpoints({"rows": bad})


def test_middle_comparison_reproduced_identity():
    # Bright session reproduces the same codes scaled by the white gain.
    middle = build_middle(
        lambda ctrl, code: tuple(v * GAIN if i == 0 else v
                                 for i, v in enumerate(DOSE1_CENTERS[ctrl, code])))
    result = da.compare_middle_endpoints(dict(DOSE1_CENTERS),
                                         da.middle_endpoints(middle))
    assert result["status"] == "EVALUATED"
    assert result["session_verdict"] == "REPRODUCED"
    assert result["consistent_codes"] == list(range(8))
    c5 = next(c for c in result["per_code"]
              if c["controller"] == "CS1" and c["code"] == 5)
    assert c5["white_gain_middle_over_dose1"] == pytest.approx(GAIN, rel=1e-3)
    assert c5["dose1_lstar_normalized"] == pytest.approx(c5["middle_lstar"])
    assert c5["delta_lstar_normalized"] == pytest.approx(0.0, abs=0.01)
    assert c5["delta_hue_degrees"] == pytest.approx(0.0, abs=0.01)
    diag = result["xor3_permutation_diagnostic"]["CS1"]
    assert diag["identity_cost_sum_abs_delta_lstar"] < \
        diag["xor3_cost_sum_abs_delta_lstar"]
    assert diag["best_permutation"] == list(range(8))


def test_middle_comparison_detects_xor3_permutation():
    # The bright session's code c shows what the dim session shows at c^3:
    # a systematic c -> c^3 code-axis swap. Code 7 stays white in both (the
    # real-world anchor), the chromatic codes 0..6 are permuted.
    def middle_lab(ctrl, code):
        if code == 7:
            return tuple(v * GAIN if i == 0 else v
                         for i, v in enumerate(DOSE1_CENTERS[ctrl, 7]))
        swapped = DOSE1_CENTERS[ctrl, code ^ 3]
        return (swapped[0] * GAIN, swapped[1], swapped[2])

    middle = build_middle(middle_lab)
    result = da.compare_middle_endpoints(dict(DOSE1_CENTERS),
                                         da.middle_endpoints(middle))
    assert result["session_verdict"] == "SUSPECTED_XOR3_PERMUTATION"
    diag = result["xor3_permutation_diagnostic"]["CS1"]
    assert diag["xor3_cost_sum_abs_delta_lstar"] < \
        diag["identity_cost_sum_abs_delta_lstar"]
    identity_consistent = [c["code"] for c in result["per_code"]
                           if c["controller"] == "CS1" and c["consistent"]]
    assert set(identity_consistent) == {7}  # only the white column matches directly


def test_extraction_identity_binding(contract):
    dose1 = build_extraction(contract, 1, DOSE1_LAB)
    dose2 = build_extraction(contract, 2, DOSE1_LAB)
    # Swapped stages: the dose1 document does not bind the DOSE1 action.
    with pytest.raises(da.DoseAnalysisError, match="dose1"):
        da.compare(contract, dose2, dose1)
    # Tampered action binding.
    bad = build_extraction(contract, 1, DOSE1_LAB)
    bad["identity"]["action_sha256"] = "0" * 64
    with pytest.raises(da.DoseAnalysisError, match="action_sha256"):
        da.compare(contract, bad, dose2)
    bad = build_extraction(contract, 1, DOSE1_LAB)
    bad["identity"]["contract_id"] = "0" * 64
    with pytest.raises(da.DoseAnalysisError, match="contract_id"):
        da.compare(contract, bad, dose2)


def test_extraction_grid_validation(contract):
    dose2 = build_extraction(contract, 2, DOSE1_LAB)
    bad = build_extraction(contract, 1, DOSE1_LAB)
    bad["rows"][0]["grid_col"] = 7
    with pytest.raises(da.DoseAnalysisError, match="grid position"):
        da.compare(contract, bad, dose2)
    bad = build_extraction(contract, 1, DOSE1_LAB)
    bad["rows"][0]["comparison_id"] = "DOSE_C7"
    with pytest.raises(da.DoseAnalysisError, match="comparison_id"):
        da.compare(contract, bad, dose2)
    bad = build_extraction(contract, 1, DOSE1_LAB)
    bad["rows"][1]["recipe_id"] = bad["rows"][0]["recipe_id"]
    bad["rows"][1]["grid_row"] = bad["rows"][0]["grid_row"]
    bad["rows"][1]["comparison_id"] = bad["rows"][0]["comparison_id"]
    with pytest.raises(da.DoseAnalysisError, match="duplicate"):
        da.compare(contract, bad, dose2)
    bad = build_extraction(contract, 1, DOSE1_LAB)
    bad["rows"][0]["lab_samples"] = bad["rows"][0]["lab_samples"][:9]
    with pytest.raises(da.DoseAnalysisError, match="samples"):
        da.compare(contract, bad, dose2)
    bad = build_extraction(contract, 1, DOSE1_LAB)
    del bad["rows"][0]
    with pytest.raises(da.DoseAnalysisError, match="128"):
        da.compare(contract, bad, dose2)


def test_contract_validation(contract):
    dose1 = build_extraction(contract, 1, DOSE1_LAB)
    dose2 = build_extraction(contract, 2, DOSE1_LAB)
    tampered = json.loads(json.dumps(contract))
    tampered["actions"][2]["frame"]["sha256"] = "f" * 64
    body = {k: v for k, v in tampered.items() if k != "contract_id"}
    tampered["contract_id"] = da.lh3dose.digest(da.lh3dose.canonical(body))
    # Identity digest is consistent, but DOSE2 no longer equals DOSE1.
    with pytest.raises(da.DoseAnalysisError, match="byte-identical"):
        da.compare(tampered, dose1, dose2)
    tampered = json.loads(json.dumps(contract))
    tampered["actions"][0]["stage"] = "WHITE"
    with pytest.raises(da.DoseAnalysisError, match="identity digest"):
        da.compare(tampered, dose1, dose2)


def test_cli_with_middle_extraction_fills_endpoint_comparison(tmp_path, contract):
    dose1_path = tmp_path / "dose1.json"
    dose2_path = tmp_path / "dose2.json"
    dose1_path.write_text(json.dumps(
        da.attach_integrity(build_extraction(contract, 1, DOSE1_LAB_NEUTRAL6))),
        encoding="utf-8")
    dose2_path.write_text(json.dumps(
        da.attach_integrity(build_extraction(contract, 2, DOSE2_LAB_MIXED))),
        encoding="utf-8")
    # Bright session reproducing the mixed dose1 screen under the white gain:
    # code 7 white 50 -> 65.8 style gain, other codes scaled on L* only.
    def middle_lab(ctrl, code):
        lab = ((60.0, 0.0, 0.0) if code == 6 else
               (50.0, 30.0, 0.0) if code == 7 else DOSE2_LAB_BY_CODE[code])
        return (lab[0] * 65.8 / 50.0, lab[1], lab[2])

    middle_path = tmp_path / "middle.json"
    middle_path.write_text(json.dumps(build_middle(middle_lab)), encoding="utf-8")
    out = tmp_path / "analysis-middle"
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/mf1750_lh3_dose_analysis.py"),
         "--package", str(PACKAGE), "--dose1-extraction", str(dose1_path),
         "--dose2-extraction", str(dose2_path),
         "--middle-extraction", str(middle_path),
         "--output-dir", str(out)],
        cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    sealed = json.loads((out / "dose-analysis.json").read_text(encoding="utf-8"))
    verify_integrity(sealed, "dose analysis")
    comparison = sealed["middle_endpoint_comparison"]
    assert comparison["status"] == "EVALUATED"
    assert comparison["tolerance_is_not_frozen_gate"] is True
    endpoint = next(e for e in sealed["dose1_absolute_endpoints"]
                    if e["controller"] == "CS1" and e["code"] == 7)
    assert endpoint["bright_middle_endpoint_comparison"]["status"] == "EVALUATED"
    assert sealed["inputs"]["middle_extraction"]["sha256"]
    markdown = (out / "dose-report.md").read_text(encoding="utf-8")
    assert "会话判决" in markdown and "置换诊断" in markdown


def test_cli_outputs_sealed_analysis_and_markdown(tmp_path, contract):
    dose1_path = tmp_path / "dose1.json"
    dose2_path = tmp_path / "dose2.json"
    dose1_path.write_text(json.dumps(
        da.attach_integrity(build_extraction(contract, 1, DOSE1_LAB_NEUTRAL6))),
        encoding="utf-8")
    dose2_path.write_text(json.dumps(
        da.attach_integrity(build_extraction(contract, 2, DOSE2_LAB_MIXED))),
        encoding="utf-8")
    out = tmp_path / "analysis"
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/mf1750_lh3_dose_analysis.py"),
         "--package", str(PACKAGE), "--dose1-extraction", str(dose1_path),
         "--dose2-extraction", str(dose2_path), "--output-dir", str(out)],
        cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["result"] == "PASS"
    assert summary["hardware_accessed"] is False
    sealed = json.loads((out / "dose-analysis.json").read_text(encoding="utf-8"))
    verify_integrity(sealed, "dose analysis")
    assert sealed["summary"]["verdict_counts"] == {
        "SATURATED": 4, "DEEPENED": 4, "HUE_DRIFT": 2, "INCONCLUSIVE": 6}
    assert sealed["inputs"]["dose1_extraction"]["sha256"]
    markdown = (out / "dose-report.md").read_text(encoding="utf-8")
    assert "DOSE2 − DOSE1" in markdown
    assert "| CS1 | C2 |" in markdown and "HUE_DRIFT" in markdown
    assert "n/a(neutral)" in markdown  # code 6 neutral column
    # Output dir is O_EXCL: a second run must refuse.
    again = subprocess.run(
        [sys.executable, str(ROOT / "tools/mf1750_lh3_dose_analysis.py"),
         "--package", str(PACKAGE), "--dose1-extraction", str(dose1_path),
         "--dose2-extraction", str(dose2_path), "--output-dir", str(out)],
        cwd=ROOT, capture_output=True, text=True)
    assert again.returncode != 0
