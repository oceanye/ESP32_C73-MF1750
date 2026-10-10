from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import mf1750_redpink_permuted_grid_photo_analyzer as adapter
from tools import mf1750_redpink_recipe_permutation_comparison as comparison


def _signed(value: dict) -> dict:
    value = dict(value)
    value["integrity"] = {
        "algorithm": comparison.INTEGRITY_ALGORITHM,
        "sha256": comparison._sha256_bytes(comparison._canonical_json(value)),
    }
    return value


def _recipe_value(source: int, middle: int, component: int) -> float:
    return float(
        ((source * 37 + middle * 19 + source * middle * 11 + component * 7) % 83) + 8
    )


def _report(*, permuted: bool, follows_recipe: bool = True) -> dict:
    cells = []
    for controller in range(2):
        for row in range(8):
            for column in range(8):
                source = (column + 3) % 8 if permuted else column
                middle = 7 - row if permuted else row
                value_source = source if follows_recipe or not permuted else column
                value_middle = middle if follows_recipe or not permuted else row
                cells.append(
                    {
                        "cell_id": f"C{controller}-R{row}-K{column}",
                        "controller": controller,
                        "row": row,
                        "column": column,
                        "recipe_id": f"REDPINK-A{source}-B{middle}-A0",
                        "camera_relative_lab": [
                            _recipe_value(value_source, value_middle, component)
                            + controller
                            for component in range(3)
                        ],
                    }
                )
    return _signed(
        {
            "schema_version": 1,
            "kind": comparison.PERMUTED_KIND if permuted else comparison.BASE_KIND,
            "source_photo": {
                "path": "p1.jpg" if permuted else "p0.jpg",
                "bytes": 1,
                "sha256": "1" * 64 if permuted else "0" * 64,
                "width": 1920,
                "height": 1080,
            },
            "campaign_layout": {
                "id": comparison.PERMUTED_LAYOUT_ID
                if permuted
                else comparison.BASE_LAYOUT_ID,
                "action_ordinal": 3 if permuted else 4,
                "controllers_are_not_assumed_colour_equivalent": True,
            },
            "grid_judgement": {"enough_to_interpret_grid_camera_relatively": True},
            "cells": cells,
        }
    )


def _write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_recipe_following_structure_passes_candidate_gate(tmp_path: Path) -> None:
    baseline = _write(tmp_path / "p0.json", _report(permuted=False))
    permuted = _write(tmp_path / "p1.json", _report(permuted=True))
    result = comparison.compare(baseline, permuted)
    assert (
        result["classification"]["state"] == "BOTH_CONTROLLERS_RECIPE_LINKED_CANDIDATE"
    )
    assert result["classification"]["qualified_new_colour"] is False
    assert all(item["recipe_linked_candidate"] for item in result["controllers"])
    assert all(
        item["lab_equal_component_pearson"]["recipe_aligned"] == pytest.approx(1.0)
        for item in result["controllers"]
    )
    assert all(
        set(item["recipe_aligned_delta_plane_by_p1_position"])
        == {"lstar", "astar", "bstar"}
        for item in result["controllers"]
    )


def test_physical_position_following_structure_fails_gate(tmp_path: Path) -> None:
    baseline = _write(tmp_path / "p0.json", _report(permuted=False))
    permuted = _write(
        tmp_path / "p1.json", _report(permuted=True, follows_recipe=False)
    )
    result = comparison.compare(baseline, permuted)
    assert result["classification"]["state"] == "NO_RECIPE_LINKED_CANDIDATE"
    assert all(not item["recipe_linked_candidate"] for item in result["controllers"])
    assert all(
        item["physical_coordinate_pearson"]["lstar"] == pytest.approx(1.0)
        for item in result["controllers"]
    )


def test_lstar_only_match_does_not_override_chroma_mismatch(tmp_path: Path) -> None:
    baseline_value = _report(permuted=False)
    permuted_value = _report(permuted=True)
    for cell in permuted_value["cells"]:
        cell["camera_relative_lab"][1] *= -1
        cell["camera_relative_lab"][2] *= -1
    permuted_value = _signed(
        {k: v for k, v in permuted_value.items() if k != "integrity"}
    )
    baseline = _write(tmp_path / "p0.json", baseline_value)
    permuted = _write(tmp_path / "p1.json", permuted_value)
    result = comparison.compare(baseline, permuted)
    assert result["classification"]["state"] == "NO_RECIPE_LINKED_CANDIDATE"
    assert all(
        item["recipe_coordinate_pearson"]["lstar"] == pytest.approx(1.0)
        for item in result["controllers"]
    )


def test_tampered_integrity_is_rejected(tmp_path: Path) -> None:
    baseline_value = _report(permuted=False)
    baseline_value["cells"][0]["camera_relative_lab"][0] += 1
    baseline = _write(tmp_path / "p0.json", baseline_value)
    permuted = _write(tmp_path / "p1.json", _report(permuted=True))
    with pytest.raises(comparison.RecipePermutationComparisonError, match="integrity"):
        comparison.compare(baseline, permuted)


def test_adapter_mapping_is_bijective_and_semantically_correct() -> None:
    base_cells = []
    for controller in range(2):
        for row in range(8):
            for column in range(8):
                base_cells.append(
                    {
                        "controller": controller,
                        "row": row,
                        "column": column,
                        "camera_relative_lab": [50.0, 0.0, 0.0],
                    }
                )
    result = adapter.adapt_base_report(
        {
            "schema_version": 1,
            "kind": comparison.BASE_KIND,
            "source_photo": {"path": "x.jpg"},
            "geometry_quality": {},
            "grid_judgement": {"enough_to_interpret_grid_camera_relatively": True},
            "cells": base_cells,
            "row_column_differences": {},
        }
    )
    assert result["campaign_layout"]["id"] == comparison.PERMUTED_LAYOUT_ID
    assert result["cells"][0]["recipe_id"] == "REDPINK-A3-B7-A0"
    assert result["cells"][-1]["recipe_id"] == "REDPINK-A2-B0-A0"
    assert len({item["recipe_id"] for item in result["cells"][:64]}) == 64


def test_exclusive_output_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "result.json"
    comparison._write_exclusive(output, b"first")
    with pytest.raises(
        comparison.RecipePermutationComparisonError, match="refusing to overwrite"
    ):
        comparison._write_exclusive(output, b"second")
    assert output.read_bytes() == b"first"
