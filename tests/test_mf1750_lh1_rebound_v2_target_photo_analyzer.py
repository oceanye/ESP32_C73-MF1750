"""Tests for the TARGET photo analyzer: mapping inheritance and recipe parsing."""
from __future__ import annotations

import json

import pytest

from tools import mf1750_lh1_rebound_v2_target_photo_analyzer as analyzer


def test_recipe_codes():
    assert analyzer.recipe_codes("LH1-S7-M0-T3") == (0, 3)
    assert analyzer.recipe_codes("LH1-S7-M7-T7") == (7, 7)
    with pytest.raises(SystemExit):
        analyzer.recipe_codes("LH1-S7-M8-T3")


def test_middle_mapping_inheritance(tmp_path):
    good = {"mapping_evidence": {"mapping": {
        "side_to_ctrl": {"CS1": "left", "CS2": "right"},
        "transform_per_side": {"left": "identity", "right": "identity"}}}}
    path = tmp_path / "middle.json"
    path.write_text(json.dumps(good), encoding="utf-8")
    assert analyzer.load_middle_mapping(path) == good["mapping_evidence"]["mapping"]
    bad = {"mapping_evidence": {"mapping": {
        "side_to_ctrl": {"CS1": "right", "CS2": "left"},
        "transform_per_side": {"left": "identity", "right": "identity"}}}}
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(SystemExit):
        analyzer.load_middle_mapping(path)
    path.write_text(json.dumps({"mapping_evidence": {}}), encoding="utf-8")
    with pytest.raises(SystemExit):
        analyzer.load_middle_mapping(path)


def test_scatter_limit_inherited_from_middle_v2():
    from tools import mf1750_lh1_rebound_v2_middle_photo_analyzer as middle
    assert analyzer.ASSIGNMENT_SCATTER_LIMIT_PX == middle.ASSIGNMENT_SCATTER_LIMIT_PX == 15.0
