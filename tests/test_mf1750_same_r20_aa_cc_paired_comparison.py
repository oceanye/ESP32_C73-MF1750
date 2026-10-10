from __future__ import annotations

import json
import math
from pathlib import Path
import statistics

import pytest

from tools import mf1750_same_r20_aa_cc_paired_comparison as comparison


def _seal(value: dict) -> dict:
    unsigned = {key: item for key, item in value.items() if key != "integrity"}
    unsigned["integrity"] = {
        "algorithm": comparison.INTEGRITY_ALGORITHM,
        "sha256": comparison._sha256_bytes(comparison._canonical_json(unsigned)),
    }
    return unsigned


def _write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")
    return path


def _base_labs(*, controller_one_lstar_offset: float = 0.0) -> dict:
    labs = {}
    for controller in range(2):
        for code in range(8):
            labs[(controller, code)] = [
                42.0 + code * 2.0 + controller * controller_one_lstar_offset,
                -18.0 + code * 3.0,
                14.0 - code * 2.0,
            ]
    return labs


def _changed_labs(
    source: dict,
    changes: dict[tuple[int, int], list[float]] | None = None,
) -> dict:
    changes = changes or {}
    return {
        key: [
            component + changes.get(key, [0.0, 0.0, 0.0])[index]
            for index, component in enumerate(lab)
        ]
        for key, lab in source.items()
    }


def _analysis(
    *,
    role: str,
    labs: dict,
    noise: float = 1.0,
    reference_sha: str = "1" * 64,
) -> dict:
    source_photo_sha = ("b" if role == "AA" else "d") * 64
    analysis_id = comparison._sha256_bytes(
        comparison._canonical_json(
            {
                "photo_sha256": source_photo_sha,
                "reference_file_sha256": reference_sha,
                "role": role,
                "method": comparison.ANALYSIS_METHOD_ID,
            }
        )
    )
    cells = []
    for controller in range(2):
        for code in range(8):
            row, column = divmod(code, 4)
            cells.append(
                {
                    "cell_id": f"C{controller}-CODE{code}",
                    "controller": controller,
                    "row": row,
                    "column": column,
                    "code": code,
                    "logical_bounds": comparison._logical_bounds(
                        controller, row, column
                    ),
                    "inner_patch_valid_fraction": 1.0,
                    "robust_rgb_median": [100.0, 110.0, 120.0],
                    "robust_rgb_mad": [1.0, 1.0, 1.0],
                    "camera_relative_lab": labs[(controller, code)],
                    "cell_to_top_separator_de76": 10.0,
                }
            )
    pairs = []
    deltas = []
    for code in range(8):
        cs1 = labs[(0, code)]
        cs2 = labs[(1, code)]
        delta = math.dist(cs1, cs2)
        deltas.append(delta)
        pairs.append(
            {
                "code": code,
                "camera_relative_de76": delta,
                "absolute_lstar_difference": abs(cs1[0] - cs2[0]),
                "cs1_lab": cs1,
                "cs2_lab": cs2,
            }
        )
    threshold = max(4.0, 3.0 * noise)
    passed = all(delta <= threshold for delta in deltas)
    return _seal(
        {
            "schema_version": comparison.ANALYSIS_SCHEMA_VERSION,
            "kind": comparison.ANALYSIS_KIND,
            "analysis_id": analysis_id,
            "role": role,
            "layout": {
                "id": comparison.LAYOUT_ID,
                "controller_count": 2,
                "rows": 2,
                "columns_per_controller": 4,
                "code_mapping": "code = row * 4 + column",
                "same_dtm_both_controllers": True,
            },
            "source_photo": {
                "path": f"{role.lower()}.png",
                "bytes": 100,
                "sha256": source_photo_sha,
                "width": 1920,
                "height": 1080,
            },
            "reference_geometry": {
                "path": "geometry.json",
                "bytes": 200,
                "file_sha256": reference_sha,
                "canonical_integrity_sha256": "2" * 64,
                "camera_must_not_have_moved": True,
            },
            "geometry_guard": {
                "minimum_inner_patch_valid_fraction": 1.0,
                "contrasting_cell_count": 16,
                "minimum_required_contrasting_cells": 8,
                "reference_homography_alignment_guard_pass": True,
            },
            "cells": cells,
            "left_right_pairs": pairs,
            "paired_summary": {
                "camera_relative_de76_median": statistics.median(deltas),
                "camera_relative_de76_p95": comparison._percentile(deltas, 0.95),
                "camera_relative_de76_max": max(deltas),
                "repeat_noise_p95_de76": noise,
                "exploratory_threshold_de76": threshold,
                "all_pairs_within_exploratory_threshold": passed,
            },
            "classification": {
                "state": (
                    "CAMERA_RELATIVE_CONTROLLER_MATCH_CANDIDATE"
                    if passed
                    else "CAMERA_RELATIVE_CONTROLLER_MISMATCH_CANDIDATE"
                ),
                "controller_equivalence_proven": False,
                "absolute_colour_proven": False,
                "qualified_new_colour": False,
            },
            "evidence_boundaries": {
                "camera_relative_de76_not_calibrated_de00": True,
                "reference_homography_reuse_requires_fixed_camera": True,
                "compiled_identical_payload_does_not_prove_bus_reception": True,
                "device_io_performed": False,
            },
            "output_write_contract": "O_EXCL",
        }
    )


def _pair(
    tmp_path: Path,
    *,
    aa_labs: dict | None = None,
    cc_labs: dict | None = None,
    aa_noise: float = 1.0,
    cc_noise: float = 1.0,
) -> tuple[Path, Path]:
    aa_labs = aa_labs or _base_labs()
    cc_labs = cc_labs or _changed_labs(aa_labs)
    return (
        _write(
            tmp_path / "aa.json",
            _analysis(role="AA", labs=aa_labs, noise=aa_noise),
        ),
        _write(
            tmp_path / "cc.json",
            _analysis(role="CC", labs=cc_labs, noise=cc_noise),
        ),
    )


def _verify_output_seal(result: dict) -> None:
    unsigned = {key: value for key, value in result.items() if key != "integrity"}
    assert result["integrity"] == {
        "algorithm": comparison.INTEGRITY_ALGORITHM,
        "sha256": comparison._sha256_bytes(comparison._canonical_json(unsigned)),
    }


def test_no_resolved_effect_is_reported_for_all_codes(tmp_path: Path) -> None:
    aa, cc = _pair(tmp_path)
    result = comparison.compare(aa, cc)
    assert result["classification"]["state"] == "NO_RESOLVED_AA_TO_CC_EFFECT"
    assert result["summary"]["classification_counts"] == {
        comparison.R20_LINKED_EXPLORATORY_EFFECT: 0,
        comparison.NO_RESOLVED_EFFECT: 8,
        comparison.CONTROLLER_INCONSISTENT: 0,
    }
    assert len(result["controller_code_deltas"]) == 16
    assert len(result["code_results"]) == 8
    assert result["classification"]["absolute_colour_proven"] is False
    assert result["classification"]["qualified_new_colour"] is False
    assert result["evidence_boundaries"]["device_io_performed"] is False
    _verify_output_seal(result)


def test_bilateral_consistent_over_threshold_change_is_r20_linked_exploratory(
    tmp_path: Path,
) -> None:
    aa_labs = _base_labs()
    cc_labs = _changed_labs(
        aa_labs,
        {(0, 3): [6.0, 0.0, 0.0], (1, 3): [6.5, 0.0, 0.0]},
    )
    aa, cc = _pair(tmp_path, aa_labs=aa_labs, cc_labs=cc_labs)
    result = comparison.compare(aa, cc)
    code = result["code_results"][3]
    assert code["classification"] == comparison.R20_LINKED_EXPLORATORY_EFFECT
    assert code["left_right_change_vector_de76"] == pytest.approx(0.5)
    assert result["classification"]["state"] == (
        "R20_LINKED_EXPLORATORY_EFFECT_CODES_PRESENT"
    )
    assert result["summary"]["classification_code_lists"][
        comparison.R20_LINKED_EXPLORATORY_EFFECT
    ] == [3]


def test_one_controller_only_effect_is_controller_inconsistent(tmp_path: Path) -> None:
    aa_labs = _base_labs(controller_one_lstar_offset=3.9)
    cc_labs = _changed_labs(aa_labs, {(0, 2): [4.1, 0.0, 0.0]})
    aa, cc = _pair(tmp_path, aa_labs=aa_labs, cc_labs=cc_labs)
    result = comparison.compare(aa, cc)
    assert result["code_results"][2]["classification"] == (
        comparison.CONTROLLER_INCONSISTENT
    )
    assert result["classification"]["state"] == (
        "CONTROLLER_INCONSISTENT_CODES_PRESENT"
    )


def test_bilateral_effect_with_divergent_vectors_is_controller_inconsistent(
    tmp_path: Path,
) -> None:
    aa_labs = _base_labs(controller_one_lstar_offset=3.9)
    cc_labs = _changed_labs(
        aa_labs,
        {(0, 5): [10.0, 0.0, 0.0], (1, 5): [5.0, 0.0, 0.0]},
    )
    aa, cc = _pair(tmp_path, aa_labs=aa_labs, cc_labs=cc_labs)
    result = comparison.compare(aa, cc)
    code = result["code_results"][5]
    assert code["cs1_aa_to_cc_camera_relative_de76"] == pytest.approx(10.0)
    assert code["cs2_aa_to_cc_camera_relative_de76"] == pytest.approx(5.0)
    assert code["left_right_change_vector_de76"] == pytest.approx(5.0)
    assert code["classification"] == comparison.CONTROLLER_INCONSISTENT


def test_exact_threshold_is_not_over_threshold(tmp_path: Path) -> None:
    aa_labs = _base_labs()
    cc_labs = _changed_labs(
        aa_labs,
        {(0, 0): [4.0, 0.0, 0.0], (1, 0): [4.0, 0.0, 0.0]},
    )
    aa, cc = _pair(tmp_path, aa_labs=aa_labs, cc_labs=cc_labs)
    result = comparison.compare(aa, cc)
    assert result["code_results"][0]["classification"] == (
        comparison.NO_RESOLVED_EFFECT
    )
    assert all(
        not item["exceeds_exploratory_threshold"]
        for item in result["controller_code_deltas"]
        if item["code"] == 0
    )


def test_tampered_input_seal_is_rejected(tmp_path: Path) -> None:
    aa, cc = _pair(tmp_path)
    value = json.loads(aa.read_text("utf-8"))
    value["cells"][0]["camera_relative_lab"][0] += 1.0
    aa.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(comparison.SameR20AACCComparisonError, match="integrity"):
        comparison.compare(aa, cc)


def test_wrong_role_is_rejected(tmp_path: Path) -> None:
    labs = _base_labs()
    aa = _write(tmp_path / "aa.json", _analysis(role="AA", labs=labs))
    cc = _write(tmp_path / "cc.json", _analysis(role="AA", labs=labs))
    with pytest.raises(comparison.SameR20AACCComparisonError, match="role"):
        comparison.compare(aa, cc)


def test_reference_geometry_mismatch_is_rejected(tmp_path: Path) -> None:
    labs = _base_labs()
    aa = _write(tmp_path / "aa.json", _analysis(role="AA", labs=labs))
    cc = _write(
        tmp_path / "cc.json",
        _analysis(role="CC", labs=labs, reference_sha="3" * 64),
    )
    with pytest.raises(comparison.SameR20AACCComparisonError, match="geometry"):
        comparison.compare(aa, cc)


def test_repeat_noise_baseline_mismatch_is_rejected(tmp_path: Path) -> None:
    aa, cc = _pair(tmp_path, aa_noise=1.0, cc_noise=1.1)
    with pytest.raises(comparison.SameR20AACCComparisonError, match="noise"):
        comparison.compare(aa, cc)


def test_failed_controller_pair_gate_is_rejected(tmp_path: Path) -> None:
    aa_labs = _base_labs()
    cc_labs = _changed_labs(aa_labs, {(1, 4): [5.0, 0.0, 0.0]})
    aa, cc = _pair(tmp_path, aa_labs=aa_labs, cc_labs=cc_labs)
    with pytest.raises(
        comparison.SameR20AACCComparisonError, match="gate did not pass"
    ):
        comparison.compare(aa, cc)


def test_forged_pair_metric_is_rejected_even_with_valid_seal(tmp_path: Path) -> None:
    aa, cc = _pair(tmp_path)
    value = json.loads(cc.read_text("utf-8"))
    value["left_right_pairs"][0]["camera_relative_de76"] += 0.5
    cc.write_text(json.dumps(_seal(value)), encoding="utf-8")
    with pytest.raises(comparison.SameR20AACCComparisonError, match="derived metric"):
        comparison.compare(aa, cc)


def test_duplicate_cell_is_rejected_even_with_valid_seal(tmp_path: Path) -> None:
    aa, cc = _pair(tmp_path)
    value = json.loads(cc.read_text("utf-8"))
    value["cells"][1] = dict(value["cells"][0])
    cc.write_text(json.dumps(_seal(value)), encoding="utf-8")
    with pytest.raises(comparison.SameR20AACCComparisonError, match="duplicate"):
        comparison.compare(aa, cc)


def test_cli_creates_exclusive_sealed_output(
    tmp_path: Path, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    aa, cc = _pair(tmp_path)
    output = tmp_path / "comparison.json"
    assert (
        comparison.main(
            [
                "--aa-analysis",
                str(aa),
                "--cc-analysis",
                str(cc),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    first = output.read_bytes()
    assert capsysbinary.readouterr().out == first
    sealed = json.loads(first)
    _verify_output_seal(sealed)
    assert (
        comparison.main(
            [
                "--aa-analysis",
                str(aa),
                "--cc-analysis",
                str(cc),
                "--output",
                str(output),
            ]
        )
        == 2
    )
    assert output.read_bytes() == first
    assert b"refusing to overwrite" in capsysbinary.readouterr().err


def test_direct_exclusive_writer_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "sealed.json"
    comparison._write_exclusive(output, b"first")
    with pytest.raises(
        comparison.SameR20AACCComparisonError, match="refusing to overwrite"
    ):
        comparison._write_exclusive(output, b"second")
    assert output.read_bytes() == b"first"
