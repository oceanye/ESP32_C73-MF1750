"""Tests for the LH2 drive-map MAP photo analyzer: recipe parsing, mapping
inheritance, frame-rule consistency with the host module, and a synthetic-frame
regression of the dark-session blackhat detector feeding the base pipeline."""
from __future__ import annotations

import json

import numpy as np
import pytest

from host.static_photo import lightness_history_lh2 as lh2
from tools import mf1750_lh2_drive_map_photo_analyzer as analyzer


def test_recipe_codes_and_index():
    assert analyzer.recipe_codes("LH2-S7-M0-H0") == (0, 0)
    assert analyzer.recipe_codes("LH2-S7-M7-H1") == (7, 1)
    assert analyzer.recipe_index("LH2-S7-M0-H0") == 0
    assert analyzer.recipe_index("LH2-S7-M7-H0") == 7
    assert analyzer.recipe_index("LH2-S7-M0-H1") == 8
    assert analyzer.recipe_index("LH2-S7-M7-H1") == 15
    with pytest.raises(SystemExit):
        analyzer.recipe_codes("LH2-S7-M8-H0")
    with pytest.raises(SystemExit):
        analyzer.recipe_codes("LH1-S7-M0-T3")


def test_map_code_matches_host_module():
    for recipe in range(16):
        m, h = lh2.recipe_parts(recipe)
        for row in range(8):
            for col in range(8):
                assert analyzer.map_code(h, row, col) == lh2.map_code(recipe, row, col)
    # every (history, code) pair appears exactly once per side
    for cells in lh2.placement():
        seen = set()
        for index, recipe in enumerate(cells):
            r, c = divmod(index, 8)
            seen.add((recipe % 8, lh2.map_code(recipe, r, c)))
        assert len(seen) == 64


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


def _synthetic_frame() -> np.ndarray:
    """Two 8x8 coloured grids on a bright background, axis aligned (same shape
    as the MIDDLE analyzer regression; dark enough cells for the blackhat)."""
    img = np.full((3000, 4000, 3), (178, 155, 147), np.uint8)
    palette = [
        (76, 51, 113), (122, 106, 138), (99, 79, 128), (89, 38, 35),
        (120, 103, 137), (95, 47, 43), (98, 80, 51), (255, 255, 255),
    ]
    white = {(1, 3), (1, 6), (3, 3), (3, 4), (4, 3), (4, 4), (6, 3), (6, 4)}
    for x0 in (1700, 2680):
        for r in range(8):
            for c in range(8):
                if (r, c) in white:
                    continue
                code = (r * 8 + c) % 7
                x = x0 + c * 100
                y = 680 + r * 108
                img[y:y + 82, x:x + 78] = palette[code]
    return img


def test_dark_session_detector_feeds_base_pipeline():
    from tools import mf1750_lh1_rebound_v2_middle_photo_analyzer as base
    img = _synthetic_frame()
    centers = analyzer.detect_centers(img)
    comps = base.grid_components(centers)
    assert len(comps) == 2
    for comp in comps:
        assert len(comp) == 56  # 64 cells minus 8 white
        lattice, _theta = base.assign_lattice(comp)
        assert len(lattice) == 56
        rows = {r for r, _ in lattice}
        cols = {c for _, c in lattice}
        assert len(rows) == 8 and len(cols) == 8


def test_dark_session_detector_on_dark_scene():
    """The fixed-threshold base detector fails on the 2026-09-18 evening
    illumination; the blackhat variant must still find the cells."""
    from tools import mf1750_lh1_rebound_v2_middle_photo_analyzer as base
    img = (_synthetic_frame().astype(np.float32) * 0.55).clip(0, 255).astype(np.uint8)
    # base detector sees the whole scene as "dark" and collapses (empty center
    # set; IndexError inside grid_components on this scene)
    with pytest.raises((SystemExit, IndexError)):
        base.grid_components(base.detect_centers(img))
    centers = analyzer.detect_centers(img)
    comps = base.grid_components(centers)
    assert len(comps) == 2
    assert all(len(c) == 56 for c in comps)
