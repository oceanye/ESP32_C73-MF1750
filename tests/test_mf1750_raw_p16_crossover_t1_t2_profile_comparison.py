from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools import mf1750_raw_p16_crossover_position_balanced_pack as pack
from tools import mf1750_raw_p16_crossover_t1_t2_profile_comparison as comparison


def _seal(value: dict) -> dict:
    unsigned = {key: item for key, item in value.items() if key != "integrity"}
    unsigned["integrity"] = {
        "algorithm": comparison.INTEGRITY_ALGORITHM,
        "sha256": comparison.sha256_bytes(comparison.canonical_json(unsigned)),
    }
    return unsigned


def _write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")
    return path


def _appearance(*, stage: str, controller: int, code: int, model: str) -> list[float]:
    active = [62.0 + code * 0.4, 24.0 - code * 0.2, -22.0 + code * 0.3]
    commented = [40.0 + code * 0.4, -22.0 + code * 0.2, 24.0 - code * 0.3]
    if model == "no-effect":
        return [52.0 + code * 0.4, 0.0, 0.0]
    if model == "profile":
        profile = comparison._expected_profiles(stage)[controller]
        return active if profile == "active" else commented
    if model == "side":
        return active if controller == 0 else commented
    raise AssertionError(model)


def _analysis(
    *,
    stage: str,
    frame_index: int,
    model: str = "profile",
    camera_lock_id: str = "a" * 64,
    position_bad: tuple[int, int] | None = None,
) -> dict:
    expected = comparison._expected_binding(stage)
    frame_shift = (frame_index - 2) * 0.2
    codes = []
    for code in range(8):
        controllers = []
        for controller in range(2):
            base = _appearance(
                stage=stage, controller=controller, code=code, model=model
            )
            positions = []
            offsets = (-0.3, -0.1, 0.1, 0.3)
            for position_index, (row, column) in enumerate(
                comparison._expected_positions(code)
            ):
                extra = (
                    20.0
                    if position_bad == (controller, code) and position_index == 3
                    else 0.0
                )
                positions.append(
                    {
                        "row": row,
                        "column": column,
                        "camera_relative_lab": [
                            base[0] + frame_shift + offsets[position_index] + extra,
                            base[1],
                            base[2],
                        ],
                    }
                )
            center = comparison._median_vector(
                [item["camera_relative_lab"] for item in positions]
            )
            dispersions = [
                comparison._distance(item["camera_relative_lab"], center)
                for item in positions
            ]
            controllers.append(
                {
                    "controller": controller,
                    "profile": comparison._expected_profiles(stage)[controller],
                    "positions": positions,
                    "center_lab": center,
                    "position_dispersion_de76": dispersions,
                    "position_dispersion_p95_de76": comparison._percentile(
                        dispersions, 0.95
                    ),
                }
            )
        codes.append({"code": code, "controllers": controllers})
    camera_lock = {
        "fixture_camera_lock_marker": camera_lock_id,
        "fixed_camera": True,
    }
    canonical_camera_lock_id = comparison.sha256_bytes(
        comparison.canonical_json(camera_lock)
    )
    homography = [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]
    projection_geometry = {
        "valid": True,
        "fixed_camera": True,
        "camera_lock_id": canonical_camera_lock_id,
        "homography_logical_to_photo": homography,
        "sampling_geometry_admitted": True,
        "historical_g1_homography_reused": False,
        "all_projected_cells_inside_photo": True,
        "automatic_cell_lattice_reprojection_proven": False,
        "panel_area_fraction_of_photo": 0.5,
        "minimum_required_panel_area_fraction": 0.08,
        "minimum_projected_cell_side_px": 40.0,
        "minimum_required_projected_cell_side_px": 20.0,
    }
    projection = {
        **expected,
        "layout": {
            "id": pack.layout.VARIANT_KEY,
            "controller_count": 2,
            "rows": pack.GRID_ROWS,
            "columns_per_controller": pack.GRID_COLUMNS,
            "row_codes": [list(row) for row in pack.CODE_ROWS],
            "positions_per_code_per_controller": 4,
            "same_dtm_both_controllers": True,
        },
        "geometry": projection_geometry,
        "codes": codes,
    }
    position_labs = {
        (controller["controller"], position["row"], position["column"]): position[
            "camera_relative_lab"
        ]
        for code in codes
        for controller in code["controllers"]
        for position in controller["positions"]
    }
    cells = []
    for controller in range(2):
        for row in range(pack.GRID_ROWS):
            for column in range(pack.GRID_COLUMNS):
                code = pack.CODE_ROWS[row][column]
                position_index = comparison._expected_positions(code).index(
                    (row, column)
                )
                cells.append(
                    {
                        "cell_id": f"CS{controller + 1}-R{row}-C{column}-CODE{code}",
                        "controller": controller,
                        "row": row,
                        "column": column,
                        "position_index_for_code": position_index,
                        "code": code,
                        "logical_bounds": [float(column), float(row), 1.0, 1.0],
                        "logical_center": [column + 0.5, row + 0.5],
                        "projected_inner_roi_corners": [
                            [float(column), float(row)],
                            [float(column + 1), float(row)],
                            [float(column + 1), float(row + 1)],
                            [float(column), float(row + 1)],
                        ],
                        "inner_fraction": 0.6,
                        "sample_count": 2000,
                        "robust_rgb_median": [100.0, 100.0, 100.0],
                        "robust_rgb_mad": [1.0, 1.0, 1.0],
                        "camera_relative_lab_d65_from_rgb_median": position_labs[
                            (controller, row, column)
                        ],
                    }
                )
    groups = [
        {
            "controller": controller["controller"],
            "code": code["code"],
            "sample_count": 4,
            "cell_ids": [],
            "camera_relative_lab_component_median": controller["center_lab"],
            "delta_e00_to_group_median": [0.0, 0.0, 0.0, 0.0],
            "maximum_delta_e00_to_group_median": 0.0,
            "heuristic_category": "NO_OBVIOUS_POSITION_DIFFERENCE_IN_THIS_CAPTURE",
            "qualification_effect": "NONE",
        }
        for controller_index in range(2)
        for code in codes
        for controller in [code["controllers"][controller_index]]
    ]
    token = f"{stage}-{frame_index}"
    evidence_hash = lambda suffix: hashlib.sha256(  # noqa: E731
        f"{token}-{suffix}".encode()
    ).hexdigest()
    return _seal(
        {
            "schema_version": comparison.INPUT_SCHEMA_VERSION,
            "kind": comparison.INPUT_KIND,
            **expected,
            "source_evidence": {
                "photo": {
                    "path": f"{token}.jpg",
                    "bytes": 1000 + frame_index,
                    "sha256": evidence_hash("photo"),
                    "width": 2000,
                    "height": 1200,
                },
                "capture_sidecar": {
                    "path": f"{token}-capture.json",
                    "bytes": 100 + frame_index,
                    "sha256": evidence_hash("capture"),
                    "canonical_integrity_sha256": evidence_hash("capture-integrity"),
                },
                "action_result": {
                    "path": f"{token}-action.json",
                    "bytes": 100 + frame_index,
                    "sha256": evidence_hash("action"),
                    "canonical_integrity_sha256": evidence_hash("action-integrity"),
                },
            },
            "action_binding": comparison._expected_action_binding(stage),
            "camera_lock": camera_lock,
            "layout": {
                "logical_width": 1024,
                "logical_height": 600,
                "controller_count": 2,
                "controller_width": 512,
                "rows_per_controller": pack.GRID_ROWS,
                "columns_per_controller": pack.GRID_COLUMNS,
                "row_codes": [list(row) for row in pack.CODE_ROWS],
                "samples_per_code_per_controller": 4,
                "same_layout_both_controllers": True,
                "spatial_dither": False,
                "legacy_endpoint_4x2_analyzer_used": False,
            },
            "geometry": {
                "source": "EXPLICIT_CURRENT_PHOTO_PANEL_CORNERS",
                "historical_g1_homography_reused": False,
                "logical_coordinate_convention": "MF1750 full panel 1024x600",
                "homography_logical_to_current_photo": homography,
                "supplied_panel_corners_tl_tr_br_bl": [
                    [0.0, 0.0],
                    [1024.0, 0.0],
                    [1024.0, 600.0],
                    [0.0, 600.0],
                ],
                "panel_area_fraction_of_photo": 0.5,
                "minimum_required_panel_area_fraction": 0.08,
                "minimum_projected_cell_side_px": 40.0,
                "minimum_required_projected_cell_side_px": 20.0,
                "all_projected_cells_inside_photo": True,
                "automatic_cell_lattice_reprojection_proven": False,
                "manual_corner_precision_limitation": "fixture",
                "sampling_geometry_admitted": True,
            },
            "measurement_method": {
                "physical_colour_calibrated": False,
                "absolute_colour_measurement": False,
                "repeatability_measurement": False,
            },
            "cells": cells,
            "position_balanced_summary": {
                "samples_per_code_per_controller": 4,
                "controller_code_groups": groups,
            },
            "comparison_projection": projection,
            "classification": {
                "state": "CAMERA_RELATIVE_CROSSOVER_POSITION_COMPARISON_ONLY",
                "camera_relative_candidates_only": True,
                "absolute_colour_proven": False,
                "stable_colour_proven": False,
                "repeatable_colour_proven": False,
                "qualified_new_colour": False,
                "qualified_colour_count": 0,
                "cross_stage_equivalence_proven": False,
            },
            "hardware_io_performed_by_analyzer": False,
            "camera_access_performed_by_analyzer": False,
            "visible_refresh_authorized": False,
            "output_write_contract": "O_EXCL",
        }
    )


def _sets(
    tmp_path: Path,
    *,
    model: str = "profile",
    position_bad: tuple[int, int] | None = None,
    t2_camera_lock_id: str = "a" * 64,
) -> tuple[list[Path], list[Path]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    t1 = [
        _write(
            tmp_path / f"t1-{index}.json",
            _analysis(
                stage=comparison.T1_STAGE,
                frame_index=index,
                model=model,
                position_bad=position_bad,
            ),
        )
        for index in range(1, 4)
    ]
    t2 = [
        _write(
            tmp_path / f"t2-{index}.json",
            _analysis(
                stage=comparison.T2_STAGE,
                frame_index=index,
                model=model,
                camera_lock_id=t2_camera_lock_id,
            ),
        )
        for index in range(1, 4)
    ]
    return t1, t2


def _verify_seal(value: dict) -> None:
    unsigned = {key: item for key, item in value.items() if key != "integrity"}
    assert value["integrity"] == {
        "algorithm": comparison.INTEGRITY_ALGORITHM,
        "sha256": comparison.sha256_bytes(comparison.canonical_json(unsigned)),
    }


def test_profile_swap_is_profile_following_candidate_for_every_code(
    tmp_path: Path,
) -> None:
    t1, t2 = _sets(tmp_path, model="profile")
    result = comparison.compare(t1, t2)
    assert result["summary"]["state"] == "PROFILE_FOLLOWING_CANDIDATES_PRESENT"
    assert result["summary"]["classification_counts"] == {
        comparison.INCONCLUSIVE: 0,
        comparison.PROFILE_FOLLOWING_CANDIDATE: 8,
        comparison.SIDE_FOLLOWING_CANDIDATE: 0,
    }
    assert all(
        item["classification"] == comparison.PROFILE_FOLLOWING_CANDIDATE
        and item["model_metrics"]["profile_model_pass"] is True
        and item["model_metrics"]["side_model_pass"] is False
        for item in result["code_results"]
    )
    assert result["summary"]["absolute_colour_proven"] is False
    assert result["summary"]["stable_colour_proven"] is False
    assert result["summary"]["qualified_new_colour"] is False
    _verify_seal(result)


def test_fixed_controller_appearance_is_side_following_candidate(
    tmp_path: Path,
) -> None:
    t1, t2 = _sets(tmp_path, model="side")
    result = comparison.compare(t1, t2)
    assert result["summary"]["state"] == "SIDE_FOLLOWING_CANDIDATES_PRESENT"
    assert all(
        item["classification"] == comparison.SIDE_FOLLOWING_CANDIDATE
        and item["model_metrics"]["side_model_pass"] is True
        and item["model_metrics"]["profile_model_pass"] is False
        for item in result["code_results"]
    )


def test_no_resolved_profile_difference_is_strictly_inconclusive(
    tmp_path: Path,
) -> None:
    t1, t2 = _sets(tmp_path, model="no-effect")
    result = comparison.compare(t1, t2)
    assert result["summary"]["state"] == comparison.INCONCLUSIVE
    assert all(
        item["classification"] == comparison.INCONCLUSIVE
        and item["diagnostic_reason"] == "NO_RESOLVED_ACTIVE_COMMENTED_SEPARATION"
        for item in result["code_results"]
    )


def test_one_bad_four_position_group_blocks_only_that_code(tmp_path: Path) -> None:
    t1, t2 = _sets(tmp_path, model="profile", position_bad=(0, 5))
    result = comparison.compare(t1, t2)
    code5 = result["code_results"][5]
    assert code5["classification"] == comparison.INCONCLUSIVE
    assert code5["diagnostic_reason"] == "POSITION_OR_TEMPORAL_INCONSISTENCY"
    assert code5["priority_role"] == "PRIMARY"
    assert result["code_results"][3]["classification"] == (
        comparison.PROFILE_FOLLOWING_CANDIDATE
    )


def test_exact_stage_contract_action_binding_is_required(tmp_path: Path) -> None:
    t1, t2 = _sets(tmp_path)
    value = json.loads(t2[0].read_text("utf-8"))
    value["comparison_projection"]["contract_id"] = "0" * 64
    _write(t2[0], _seal(value))
    with pytest.raises(comparison.CrossoverProfileComparisonError, match="contract_id"):
        comparison.compare(t1, t2)


def test_old_or_wrong_analysis_kind_is_rejected(tmp_path: Path) -> None:
    t1, t2 = _sets(tmp_path)
    value = json.loads(t1[0].read_text("utf-8"))
    value["kind"] = "mf1750-raw-p16-retained-atlas-camera-relative-analysis"
    _write(t1[0], _seal(value))
    with pytest.raises(comparison.CrossoverProfileComparisonError, match="schema"):
        comparison.compare(t1, t2)


def test_tampered_input_integrity_is_rejected(tmp_path: Path) -> None:
    t1, t2 = _sets(tmp_path)
    value = json.loads(t1[0].read_text("utf-8"))
    value["comparison_projection"]["codes"][3]["controllers"][0]["positions"][0][
        "camera_relative_lab"
    ][0] += 1.0
    _write(t1[0], value)
    with pytest.raises(comparison.CrossoverProfileComparisonError, match="integrity"):
        comparison.compare(t1, t2)


def test_forged_derived_position_statistics_are_rejected(tmp_path: Path) -> None:
    t1, t2 = _sets(tmp_path)
    value = json.loads(t1[0].read_text("utf-8"))
    value["comparison_projection"]["codes"][5]["controllers"][0]["center_lab"][0] += 0.5
    _write(t1[0], _seal(value))
    with pytest.raises(comparison.CrossoverProfileComparisonError, match="forged"):
        comparison.compare(t1, t2)


def test_three_distinct_records_and_one_camera_lock_are_required(
    tmp_path: Path,
) -> None:
    t1, t2 = _sets(tmp_path)
    with pytest.raises(comparison.CrossoverProfileComparisonError, match="paths"):
        comparison.compare([t1[0], t1[0], t1[2]], t2)
    t1, t2 = _sets(tmp_path / "second", t2_camera_lock_id="b" * 64)
    with pytest.raises(
        comparison.CrossoverProfileComparisonError, match="camera locks"
    ):
        comparison.compare(t1, t2)


def test_output_binds_raw_input_hashes_and_priority_order(tmp_path: Path) -> None:
    t1, t2 = _sets(tmp_path)
    result = comparison.compare(t1, t2)
    assert result["priority"] == {
        "primary_codes": [3, 5, 6, 7],
        "guard_codes": [4],
        "control_codes": [0, 1, 2],
        "review_order": [3, 5, 6, 7, 4, 0, 1, 2],
    }
    for path, binding in zip(t1, result["input_bindings"]["t1-ac"], strict=True):
        assert binding["file_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert (
            binding["contract_id"]
            == comparison._expected_binding("t1-ac")["contract_id"]
        )


def test_t1_only_preflight_passes_three_consistent_sealed_frames(
    tmp_path: Path,
) -> None:
    t1, _t2 = _sets(tmp_path)
    result = comparison.preflight_t1(t1)
    assert result["kind"] == comparison.PREFLIGHT_KIND
    assert result["schema_version"] == comparison.PREFLIGHT_SCHEMA_VERSION
    assert result["supersedes_source_path"] is None
    assert result["supersedes_file_sha256"] is None
    assert result["summary"]["state"] == "PASS_T1_POSITION_TEMPORAL_PREFLIGHT"
    assert result["summary"]["position_temporal_gate_pass"] is True
    assert result["summary"]["w1_containment_required"] is True
    assert result["summary"]["advance_to_t2_permitted"] is True
    assert result["summary"]["diagnostic_reason"] == (
        "POSITION_TEMPORAL_PREFLIGHT_PASS"
    )
    assert all(item["position_temporal_gate_pass"] for item in result["code_results"])
    assert result["summary"]["profile_or_side_following_classified"] is False
    _verify_seal(result)


def test_t1_only_preflight_blocks_t2_on_position_dispersion(tmp_path: Path) -> None:
    t1, _t2 = _sets(tmp_path, position_bad=(0, 5))
    result = comparison.preflight_t1(t1)
    assert result["summary"]["state"] == "FAIL_T1_POSITION_TEMPORAL_PREFLIGHT"
    assert result["summary"]["position_temporal_gate_pass"] is False
    assert result["summary"]["w1_containment_required"] is True
    assert result["summary"]["advance_to_t2_permitted"] is False
    assert result["summary"]["diagnostic_reason"] == ("POSITION_DEPENDENT_INCONCLUSIVE")
    assert {
        tuple((item["controller"], item["code"]))
        for item in result["summary"]["failed_controller_code_groups"]
    } == {(0, 5)}


def test_t1_only_preflight_cli_writes_o_excl_report(
    tmp_path: Path, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    t1, _t2 = _sets(tmp_path)
    output = tmp_path / "t1-preflight.json"
    argv = [
        "--t1-analysis",
        *(str(path) for path in t1),
        "--t1-only-preflight",
        "--output",
        str(output),
    ]
    assert comparison.main(argv) == 0
    report = json.loads(output.read_text("utf-8"))
    assert report["summary"]["w1_containment_required"] is True
    assert report["summary"]["advance_to_t2_permitted"] is True
    assert comparison.main(argv) == 2
    _verify_seal(report)
    capsysbinary.readouterr()


def test_t1_preflight_v2_binds_exact_superseded_v1_record(tmp_path: Path) -> None:
    t1, _t2 = _sets(tmp_path)
    corrected = comparison.preflight_t1(t1)
    old = dict(corrected)
    old["schema_version"] = 1
    old["kind"] = comparison.PREFLIGHT_V1_KIND
    for field in (
        "supersedes_source_path",
        "supersedes_file_sha256",
        "supersedes_canonical_integrity_sha256",
        "supersession_reason",
    ):
        old.pop(field)
    old_summary = dict(old["summary"])
    old_summary["advance_to_w1_then_t2_permitted"] = old_summary.pop(
        "advance_to_t2_permitted"
    )
    old_summary.pop("w1_containment_required")
    old_summary.pop("diagnostic_reason")
    old["summary"] = old_summary
    old_path = _write(tmp_path / "old-v1-preflight.json", _seal(old))

    report = comparison.preflight_t1(t1, supersedes_preflight=old_path)
    assert report["supersedes_source_path"] == old_path.resolve().as_posix()
    assert (
        report["supersedes_file_sha256"]
        == hashlib.sha256(old_path.read_bytes()).hexdigest()
    )
    assert (
        report["supersedes_canonical_integrity_sha256"]
        == json.loads(old_path.read_text("utf-8"))["integrity"]["sha256"]
    )
    assert report["summary"]["w1_containment_required"] is True
    assert report["summary"]["advance_to_t2_permitted"] is True
    _verify_seal(report)


def test_cli_creates_one_o_excl_sealed_output(
    tmp_path: Path, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    t1, t2 = _sets(tmp_path)
    output = tmp_path / "comparison.json"
    argv = [
        "--t1-analysis",
        *(str(path) for path in t1),
        "--t2-analysis",
        *(str(path) for path in t2),
        "--output",
        str(output),
    ]
    assert comparison.main(argv) == 0
    first = output.read_bytes()
    assert capsysbinary.readouterr().out == first
    value = json.loads(first)
    assert value["output_write_contract"] == "O_EXCL"
    _verify_seal(value)
    assert comparison.main(argv) == 2
    captured = capsysbinary.readouterr()
    assert b"refusing to overwrite" in captured.err
    assert output.read_bytes() == first
