"""PAL1 palette build tests; fully offline, synthetic extraction documents."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools import mf1750_pal1_palette_build as pb

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / ".test-output/offline/PAL1_CAL_20260925_R2"

LABS = {
    0: (5.0, -2.0, -9.0), 1: (66.0, 1.0, -12.0), 2: (55.0, 10.0, 60.0),
    3: (30.0, 34.0, -2.0), 4: (35.0, 5.0, 5.0), 5: (30.0, 20.0, -52.0),
    6: (33.0, -8.0, -13.0), 7: (65.0, 1.5, -13.0),
}
PROVENANCE = {"panel_id": "PANEL-001", "panel_batch": "BATCH-A",
              "instrument_calibration_date": "2026-09-20",
              "measured_at": "2026-09-24T10:00:00Z",
              "temperature_c": 23.0, "temperature_tolerance_c": 2.0,
              "relative_humidity_percent": 45.0,
              "firmware_commit": "a" * 40, "waveform_version": "L535_ACTIVE"}


def build_extraction(lab_fn=LABS, *, recipe="PAL1-C", comparison="PAL1_C",
                     jitter_cs2=0.2, quality=True):
    rows = []
    for controller in ("CS1", "CS2"):
        for code in range(8):
            L, a, b_ = lab_fn[code]
            jitter = jitter_cs2 if controller == "CS2" else 0.0
            for row in range(8):
                lab = [L + jitter, a + jitter * 0.3, b_ - jitter * 0.2]
                rows.append({
                    "controller": controller,
                    "recipe_id": f"{recipe}{code}-R{row}",
                    "comparison_id": f"{comparison}{code}",
                    "grid_row": row, "grid_col": code,
                    "position": ("T" if row < 4 else "B") + ("L" if code < 4 else "R"),
                    "lab_median": lab,
                    "lab_samples": [list(lab)] * 10,
                    "quality_pass": quality,
                    "single_pixel_uniform": True,
                })
    return {"identity": {"stage": "PAL1"}, "rows": rows}


@pytest.fixture(scope="module")
def contract():
    return json.loads((PACKAGE / "contract.json").read_text(encoding="utf-8"))


def test_schema_physical_gate_fail_closed():
    # The active-path measurement that violates the schema's physical naming
    # (black L* above white L*) must fail before any write.
    from host.color_pipeline.palette import PaletteError
    bad = {**LABS, 0: (70.0, -2.0, -9.0)}  # "black" lighter than "white"
    endpoints = pb.column_endpoints(build_extraction(lab_fn=bad))
    deltas = pb.cross_side_check(endpoints)
    palette = pb.build_palette(endpoints, deltas, "T", "a" * 64,
                               {"contract_id": "c" * 64, "campaign_id": "x",
                                "actions": [{"action_id": "a" * 64,
                                             "frame": {"sha256": "f" * 64}}]})
    with pytest.raises(PaletteError, match="black"):
        pb.palette_from_mapping({k: v for k, v in palette.items() if k != "extras"})


def test_uniformity_column_rule_tolerates_documented_failures():
    # One uniformity-failed cell whose Lab sits on the column median: tolerated
    # and recorded. Three failures, or an outlier Lab, fail closed.
    base = build_extraction()
    for row in base["rows"]:
        if row["controller"] == "CS1" and row["grid_col"] == 0 and row["grid_row"] == 1:
            row["single_pixel_uniform"] = False
    endpoints = pb.column_endpoints(base)
    tolerated = endpoints["uniformity_tolerated_cells"]
    assert list(tolerated["columns"]) == ["CS1/C0"]
    assert tolerated["columns"]["CS1/C0"][0]["row"] == 1
    assert tolerated["rule"]["max_failed_cells_per_column"] == 2

    three = build_extraction()
    for row in three["rows"]:
        if row["controller"] == "CS1" and row["grid_col"] == 0 and row["grid_row"] in (1, 2, 3):
            row["single_pixel_uniform"] = False
    with pytest.raises(pb.PaletteBuildError, match="exceed the"):
        pb.column_endpoints(three)

    outlier = build_extraction()
    for row in outlier["rows"]:
        if row["controller"] == "CS1" and row["grid_col"] == 0 and row["grid_row"] == 1:
            row["single_pixel_uniform"] = False
            row["lab_median"] = [v + 6.0 for v in row["lab_median"]]
    with pytest.raises(pb.PaletteBuildError, match="column outlier"):
        pb.column_endpoints(outlier)

    hard = build_extraction()
    hard["rows"][0]["quality_pass"] = False  # clip/scatter stays hard-fail
    with pytest.raises(pb.PaletteBuildError, match="fail-closed"):
        pb.column_endpoints(hard)


def test_column_endpoints_and_noise():
    endpoints = pb.column_endpoints(build_extraction())
    assert len(endpoints) == 16
    assert endpoints["CS1", 0]["lab_median"] == pytest.approx(LABS[0])
    assert endpoints["CS2", 1]["lab_median"][0] == pytest.approx(LABS[1][0] + 0.2)
    assert endpoints["CS1", 5]["noise_lstar"] == pytest.approx(0.0)
    # The dose-format recipe/comparison prefix is accepted too.
    dose_format = build_extraction(recipe="LH3D-S7-D", comparison="DOSE_C")
    assert pb.column_endpoints(dose_format)["CS1", 2]["lab_median"] == pytest.approx(LABS[2])


def test_column_endpoints_validation():
    bad = build_extraction()
    bad["rows"][0]["quality_pass"] = False
    with pytest.raises(pb.PaletteBuildError, match="fail-closed"):
        pb.column_endpoints(bad)
    bad = build_extraction()
    bad["rows"][0]["grid_col"] = 7
    with pytest.raises(pb.PaletteBuildError, match="grid position"):
        pb.column_endpoints(bad)
    bad = build_extraction()
    bad["rows"][0]["lab_samples"] = bad["rows"][0]["lab_samples"][:9]
    with pytest.raises(pb.PaletteBuildError, match="10"):
        pb.column_endpoints(bad)
    bad = build_extraction()["rows"][:-1]
    with pytest.raises(pb.PaletteBuildError, match="row cells"):
        pb.column_endpoints({"rows": bad})


def test_cross_side_check_fail_closed():
    endpoints = pb.column_endpoints(build_extraction())
    deltas = pb.cross_side_check(endpoints)
    assert deltas[3]["delta_lstar"] == pytest.approx(0.2)
    # CS2 red 6 L* lighter than CS1: beyond the cross-controller limit.
    bad = build_extraction()
    for row in bad["rows"]:
        if row["controller"] == "CS2" and row["grid_col"] == 3:
            row["lab_median"] = [36.0, 34.0, -2.0]
    endpoints = pb.column_endpoints(bad)
    with pytest.raises(pb.PaletteBuildError, match="disagreement"):
        pb.cross_side_check(endpoints)


def test_palette_schema_roundtrip_and_white_calibration(contract):
    endpoints = pb.column_endpoints(build_extraction())
    deltas = pb.cross_side_check(endpoints)
    palette = pb.build_palette(endpoints, deltas, "PAL1-CAL-TEST", "a" * 64, contract)
    obj = pb.palette_from_mapping({k: v for k, v in palette.items() if k != "extras"})
    assert obj.calibrated is True
    assert obj.calibration.measurement_id == "PAL1-CAL-TEST"
    assert obj.calibration.artifact_sha256 == "a" * 64
    assert len(obj.entries) == 6
    assert obj.entry(0).name == "black" and obj.entry(1).name == "white"
    assert obj.entry(1).lab[0] == pytest.approx(66.1, abs=0.01)
    assert obj.entry(0).lab[0] < obj.entry(1).lab[0]
    extras = palette["extras"]
    assert extras["outside_schema_retention"] is True
    assert set(extras["record_only_endpoints"]) == {"4", "7"}
    coefficient = extras["measurement"]["white_calibration_coefficient"]
    assert coefficient["bright_reference_lstar"] == 65.8
    assert coefficient["measured_white_lstar_mean"] == pytest.approx(65.1)
    assert coefficient["ratio_bright_over_measured"] == pytest.approx(65.8 / 65.1, rel=1e-3)
    assert extras["measurement"]["contract_sha256"] == contract["contract_id"]
    # The canonical hash never covers the extras block.
    assert "extras" not in obj.canonical_mapping()


def test_gamut_profile_roundtrip(contract):
    endpoints = pb.column_endpoints(build_extraction())
    deltas = pb.cross_side_check(endpoints)
    palette = pb.build_palette(endpoints, deltas, "PAL1-CAL-TEST", "a" * 64, contract)
    obj = pb.palette_from_mapping({k: v for k, v in palette.items() if k != "extras"})
    profile = pb.build_gamut_profile(palette, obj, "a" * 64, PROVENANCE, "PAL1-CAL-TEST")
    loaded = pb.gamut_profile_from_mapping(profile, obj)
    assert loaded.characterization_level == "measured_primaries"
    assert loaded.measurement_id == "PAL1-CAL-TEST"
    assert all(item.artifact_sha256 == "a" * 64 for item in loaded.pure_sample_refs)
    assert loaded.palette_canonical_sha256 == obj.canonical_sha256
    with pytest.raises(pb.PaletteBuildError, match="provenance"):
        pb.validate_provenance({k: v for k, v in PROVENANCE.items() if k != "panel_id"})


def test_cli_writes_palette_and_profile(tmp_path, contract):
    from host.static_photo.common import attach_integrity
    extraction_path = tmp_path / "extraction.json"
    extraction_path.write_text(
        json.dumps(attach_integrity(build_extraction())), encoding="utf-8")
    provenance_path = tmp_path / "provenance.json"
    provenance_path.write_text(json.dumps(PROVENANCE), encoding="utf-8")
    palette_out = tmp_path / "palette.json"
    profile_out = tmp_path / "profile.json"
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/mf1750_pal1_palette_build.py"),
         "--extraction", str(extraction_path), "--package", str(PACKAGE),
         "--provenance", str(provenance_path), "--measurement-id", "PAL1-CAL-TEST",
         "--palette-out", str(palette_out), "--profile-out", str(profile_out)],
        cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["result"] == "PASS" and summary["hardware_accessed"] is False
    from host.color_pipeline.palette import load_palette
    from host.gamut_mapping.profile import load_gamut_profile
    palette = load_palette(palette_out)
    assert palette.calibrated is True
    profile = load_gamut_profile(profile_out, palette)
    assert profile.characterization_level == "measured_primaries"
    again = subprocess.run(
        [sys.executable, str(ROOT / "tools/mf1750_pal1_palette_build.py"),
         "--extraction", str(extraction_path), "--package", str(PACKAGE),
         "--provenance", str(provenance_path),
         "--palette-out", str(palette_out), "--profile-out", str(profile_out)],
        cwd=ROOT, capture_output=True, text=True)
    assert again.returncode != 0  # O_EXCL refuses existing outputs


def test_pal2_extraction_compat_and_white_code(contract):
    # PAL2 production-path extraction: PAL2-C recipe ids, white reference is
    # code 1 (columns 4/7 are white-filled).
    pal2 = build_extraction(recipe="PAL2-C", comparison="PAL2_C")
    endpoints = pb.column_endpoints(pal2)
    deltas = pb.cross_side_check(endpoints)
    palette = pb.build_palette(endpoints, deltas, "PAL2-TEST", "b" * 64,
                               contract, white_code=1)
    coefficient = palette["extras"]["measurement"]["white_calibration_coefficient"]
    assert coefficient["white_code"] == 1
    assert coefficient["measured_white_lstar_mean"] == pytest.approx(66.1)
    # Out-of-range white code fails instead of silently reading another column.
    with pytest.raises(KeyError):
        pb.build_palette(endpoints, deltas, "T", "b" * 64, contract, white_code=9)
    # The PAL1 default (white column 7) is unchanged.
    palette7 = pb.build_palette(endpoints, deltas, "T", "b" * 64, contract)
    assert palette7["extras"]["measurement"]["white_calibration_coefficient"]["white_code"] == 7
