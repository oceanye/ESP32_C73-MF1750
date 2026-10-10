from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools import mf1750_redpink_v2_colour_family_summary as summary


def _seal(value: dict[str, object]) -> dict[str, object]:
    result = dict(value)
    result["integrity"] = {
        "algorithm": summary.INTEGRITY_ALGORITHM,
        "sha256": hashlib.sha256(summary._canonical_json(result)).hexdigest(),
    }
    return result


def _cells(*, structured_rows: bool = True) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for controller in range(2):
        for row in range(8):
            for column in range(8):
                if controller == 0:
                    base_lab = [58.0, -9.0, 32.0]
                    rgb = [150.0, 151.0, 88.0]
                    hsv = [62.0, 42.0, 60.0]
                else:
                    base_lab = [34.0, 31.0, 2.0]
                    rgb = [145.0, 72.0, 94.0]
                    hsv = [344.0, 50.0, 57.0]
                row_effect = 1.8 * row if structured_rows else 0.0
                column_effect = 0.08 * column if structured_rows else 0.0
                lab = [
                    base_lab[0] + row_effect + column_effect,
                    base_lab[1] + 0.08 * column,
                    base_lab[2] - 0.06 * row,
                ]
                result.append(
                    {
                        "cell_id": f"C{controller}-R{row}-K{column}",
                        "controller": controller,
                        "row": row,
                        "column": column,
                        "recipe_id": f"REDPINK-A{column}-B{row}-A0",
                        "robust_rgb_median": rgb,
                        "robust_rgb_mad": [1.0, 1.0, 1.0],
                        "camera_relative_lab": lab,
                        "camera_relative_hsv": {
                            "hue_degrees": hsv[0],
                            "saturation_percent": hsv[1],
                            "value_percent": hsv[2],
                        },
                    }
                )
    return result


def _write_grid(
    path: Path,
    photo: Path,
    *,
    cells: list[dict[str, object]] | None = None,
    reverse_cells: bool = False,
) -> dict[str, object]:
    payload = photo.read_bytes()
    cell_records = list(cells if cells is not None else _cells())
    if reverse_cells:
        cell_records.reverse()
    root = _seal(
        {
            "schema_version": summary.GRID_SCHEMA_VERSION,
            "kind": summary.GRID_KIND,
            "source_photo": {
                "path": str(photo),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "width": 1920,
                "height": 1080,
            },
            "campaign_layout": {
                "id": summary.GRID_LAYOUT_ID,
                "action_ordinal": 4,
                "controllers_are_not_assumed_colour_equivalent": True,
            },
            "grid_judgement": {
                "enough_to_interpret_grid_camera_relatively": True,
            },
            "cells": cell_records,
            "candidate_ranking_metadata": {
                "camera_relative_spatial_assessment": (
                    "NO_OBVIOUS_PAIRED_CELL_OUTLIER_BEYOND_SMOOTH_SPATIAL_TREND"
                ),
                "obvious_spatial_outlier_cell_count": 0,
                "obvious_paired_recipe_count": 0,
                "scope": "camera-relative post-target history candidate ranking",
            },
        }
    )
    path.write_text(json.dumps(root, indent=2), encoding="utf-8")
    return root


def test_family_summary_finds_structured_row_effect_without_qualifying_colour(
    tmp_path: Path,
) -> None:
    photo = tmp_path / "action4.jpg"
    photo.write_bytes(b"bound-photo-bytes")
    grid = tmp_path / "grid.json"
    _write_grid(grid, photo)

    report = summary.summarize(grid, photo)

    assert [
        item["camera_relative_family_label"]
        for item in report["controller_family_envelopes"]
    ] == ["yellow-olive-direction", "red-pink-direction"]
    effects = report["structured_factor_effects"]
    assert effects["structured_effect_state"] == (
        "STRUCTURED_ROW_EFFECT_CANDIDATE_POSITION_CONFOUNDED"
    )
    by_axis = {item["axis"]: item for item in effects["axes"]}
    assert by_axis["row"]["structured_effect_detected"] is True
    assert by_axis["column"]["structured_effect_detected"] is False
    assert by_axis["row"]["cross_controller_lstar_pearson"] == pytest.approx(1.0)
    assert report["evidence_classification"]["qualified_new_colour"] is False
    assert report["evidence_classification"]["qualified_brightness_level"] is False
    assert report["evidence_classification"]["stability_status"] == (
        "UNPROVEN_SINGLE_CAPTURE"
    )
    assert all(
        item["cluster_count_is_not_colour_count"]
        for item in report["controller_relative_lab_clustering"]
    )


def test_clustering_is_deterministic_when_input_cell_order_changes(
    tmp_path: Path,
) -> None:
    photo = tmp_path / "action4.jpg"
    photo.write_bytes(b"same-photo")
    first_grid = tmp_path / "grid-first.json"
    second_grid = tmp_path / "grid-reversed.json"
    _write_grid(first_grid, photo)
    _write_grid(second_grid, photo, reverse_cells=True)

    first = summary.summarize(first_grid, photo)
    second = summary.summarize(second_grid, photo)

    assert first["controller_family_envelopes"] == second["controller_family_envelopes"]
    assert (
        first["controller_relative_lab_clustering"]
        == second["controller_relative_lab_clustering"]
    )
    assert first["structured_factor_effects"] == second["structured_factor_effects"]


def test_minimum_cluster_guard_falls_back_to_one_exploratory_band(
    tmp_path: Path,
) -> None:
    photo = tmp_path / "action4.jpg"
    photo.write_bytes(b"uniform-photo")
    uniform_cells = _cells(structured_rows=False)
    for cell in uniform_cells:
        if cell["controller"] == 0:
            cell["camera_relative_lab"] = [65.0, -9.0, 32.0]
        else:
            cell["camera_relative_lab"] = [45.0, 31.0, 2.0]
    grid = tmp_path / "grid.json"
    _write_grid(grid, photo, cells=uniform_cells)

    report = summary.summarize(grid, photo)

    for clustering in report["controller_relative_lab_clustering"]:
        assert clustering["selected_exploratory_k"] == 1
        assert clustering["selection_reason"] == (
            "no-k-passed-both-silhouette-and-minimum-cluster-size-guards"
        )
        assert len(clustering["relative_appearance_bands"]) == 1


def test_repeat_grid_is_integrity_bound_but_remains_position_confounded(
    tmp_path: Path,
) -> None:
    primary_photo = tmp_path / "primary.jpg"
    repeat_photo = tmp_path / "repeat.jpg"
    primary_photo.write_bytes(b"primary-photo")
    repeat_photo.write_bytes(b"repeat-photo")
    primary_grid = tmp_path / "primary-grid.json"
    repeat_grid = tmp_path / "repeat-grid.json"
    _write_grid(primary_grid, primary_photo)
    repeated_cells = _cells()
    for cell in repeated_cells:
        lab = cell["camera_relative_lab"]
        cell["camera_relative_lab"] = [lab[0] * 1.05 + 0.7, lab[1], lab[2]]
    repeat_root = _write_grid(repeat_grid, repeat_photo, cells=repeated_cells)

    report = summary.summarize(
        primary_grid,
        primary_photo,
        repeat_grid_analysis_path=repeat_grid,
    )

    comparison = report["repeatability_comparison"]
    assert comparison["available"] is True
    assert (
        comparison["source_repeat_grid_analysis"]["canonical_integrity_sha256"]
        == repeat_root["integrity"]["sha256"]
    )
    assert len(comparison["axis_lstar_profile_comparisons"]) == 4
    row_correlations = [
        item["primary_repeat_lstar_pearson"]
        for item in comparison["axis_lstar_profile_comparisons"]
        if item["axis"] == "row"
    ]
    assert row_correlations == pytest.approx([1.0, 1.0])
    assert comparison["position_confounded_in_both_fixed_layout_captures"] is True
    classification = report["evidence_classification"]
    assert classification["capture_count"] == 2
    assert classification["stability_status"] == ("UNPROVEN_REPEAT_POSITION_CONFOUNDED")
    assert classification["qualified_new_colour"] is False
    assert classification["qualified_brightness_level"] is False


def test_tampered_grid_and_photo_hash_mismatch_are_rejected(tmp_path: Path) -> None:
    photo = tmp_path / "action4.jpg"
    photo.write_bytes(b"original-photo")
    grid = tmp_path / "grid.json"
    root = _write_grid(grid, photo)
    root["cells"][0]["camera_relative_lab"][0] += 1.0
    grid.write_text(json.dumps(root), encoding="utf-8")

    with pytest.raises(
        summary.ColourFamilySummaryError, match="integrity SHA-256 differs"
    ):
        summary.summarize(grid, photo)

    _write_grid(grid, photo)
    other_photo = tmp_path / "other.jpg"
    other_photo.write_bytes(b"different-photo")
    with pytest.raises(
        summary.ColourFamilySummaryError, match="source photo bytes or SHA-256 differ"
    ):
        summary.summarize(grid, other_photo)


def test_cli_output_is_o_excl_and_integrity_covers_summary(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    photo = tmp_path / "action4.jpg"
    photo.write_bytes(b"cli-photo")
    grid = tmp_path / "grid.json"
    output = tmp_path / "summary.json"
    _write_grid(grid, photo)

    arguments = [
        "summarize",
        "--grid-analysis",
        str(grid),
        "--photo",
        str(photo),
        "--output",
        str(output),
    ]
    assert summary.main(arguments) == 0
    stdout, stderr = capfd.readouterr()
    assert stderr == ""
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert json.loads(stdout) == persisted
    integrity = persisted.pop("integrity")
    assert (
        integrity["sha256"]
        == hashlib.sha256(summary._canonical_json(persisted)).hexdigest()
    )
    original = output.read_bytes()

    assert summary.main(arguments) == 2
    _, stderr = capfd.readouterr()
    assert "refusing to overwrite" in stderr
    assert output.read_bytes() == original
