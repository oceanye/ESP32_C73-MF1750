"""Synthetic round-trip tests for the MIDDLE photo analyzer geometry pipeline."""
from __future__ import annotations

import numpy as np

from tools import mf1750_lh1_rebound_v2_middle_photo_analyzer as analyzer


def _synthetic_frame() -> np.ndarray:
    """Two 8x8 coloured grids on a bright background, axis aligned."""
    img = np.full((3000, 4000, 3), (178, 155, 147), np.uint8)
    palette = [
        (76, 51, 113), (122, 106, 138), (99, 79, 128), (89, 38, 35),
        (120, 103, 137), (95, 47, 43), (98, 80, 51), (255, 255, 255),
    ]
    # White cells (code 7) per side, mirroring the real placement pattern.
    white = {(1, 3), (1, 6), (3, 3), (3, 4), (4, 3), (4, 4), (6, 3), (6, 4)}
    for x0, table in ((1700, "CS1"), (2680, "CS2")):
        for r in range(8):
            for c in range(8):
                if (r, c) in white:
                    continue
                code = (r * 8 + c) % 7
                x = x0 + c * 100
                y = 680 + r * 108
                cv2_color = palette[code]
                img[y:y + 82, x:x + 78] = cv2_color
    return img


def test_detect_assign_two_sides():
    import cv2  # noqa: F401 - pipeline dependency
    img = _synthetic_frame()
    centers = analyzer.detect_centers(img)
    comps = analyzer.grid_components(centers)
    assert len(comps) == 2
    for comp in comps:
        assert len(comp) == 56  # 64 cells minus 8 white
        lattice, _theta = analyzer.assign_lattice(comp)
        assert len(lattice) == 56
        rows = {r for r, _ in lattice}
        cols = {c for _, c in lattice}
        assert len(rows) == 8 and len(cols) == 8


def test_lab_batch_matches_host_pipeline():
    rng = np.random.default_rng(7)
    samples = rng.integers(0, 256, size=(64, 3))
    from host.color_pipeline.color import srgb8_to_lab
    mine = analyzer.srgb_to_lab_batch(samples)
    theirs = np.array([srgb8_to_lab(tuple(int(v) for v in px)) for px in samples])
    assert np.max(np.abs(mine - theirs)) < 1e-9


def test_recipe_index_and_placement_crosscheck():
    assert analyzer.recipe_index("LH1-S7-M0-T3") == 0
    assert analyzer.recipe_index("LH1-S7-M7-T3") == 7
    assert analyzer.recipe_index("LH1-S7-M0-T7") == 8
    assert analyzer.recipe_index("LH1-S7-M7-T7") == 15
