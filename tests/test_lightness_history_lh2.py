"""LH2 drive-map algorithm: frame/recipe invariants, no device involved."""
from __future__ import annotations

from host.static_photo import lightness_history_lh2 as lh2


def test_map_code_quadrants_cover_each_half():
    for recipe in range(16):
        m, h = lh2.recipe_parts(recipe)
        codes = {lh2.map_code(recipe, r, c)
                 for r in (1, 5) for c in (1, 5)
                 if lh2.recipe_parts(recipe) == (m, h)}
        assert len(codes) == 4
        assert codes == set(range(4 * h, 4 * h + 4))


def test_map_frame_pairs_unique_per_side():
    # Every (history, code) pair appears exactly once per side in the MAP frame.
    cells_by_side = lh2.placement()
    for cells in cells_by_side:
        pairs = set()
        for index, recipe in enumerate(cells):
            r, c = divmod(index, 8)
            pair = (recipe % 8, lh2.map_code(recipe, r, c))
            assert pair not in pairs
            pairs.add(pair)
        assert len(pairs) == 64


def test_frame_histograms():
    source = lh2.payload_identity(lh2.frame("SOURCE"), True)["histogram"]
    assert source == [0, 0, 0, 0, 0, 0, 0, 614400]
    middle = lh2.payload_identity(lh2.frame("MIDDLE"), True)["histogram"]
    assert middle == [33280] * 7 + [381440]
    map_hist = lh2.payload_identity(lh2.frame("MAP"), True)["histogram"]
    # Each of the 8 codes covers 8 cells per side; code 7 also owns the background.
    assert map_hist == [33280] * 7 + [381440]
    assert lh2.frame("MAP") != lh2.frame("MIDDLE")


def test_recipes_and_positions():
    recipes = lh2.recipes()
    assert len(recipes) == 16
    assert recipes[0]["recipe_id"] == "LH2-S7-M0-H0"
    assert recipes[15]["recipe_id"] == "LH2-S7-M7-H1"
    for recipe in recipes:
        for ctrl in ("cs1", "cs2"):
            assert len(recipe["positions"][ctrl]) == 4
        m = int(recipe["recipe_id"].split("-")[2][1])
        h = int(recipe["recipe_id"].split("-")[3][1])
        assert recipe["map"]["codes_by_quadrant"] == (
            {"TL": 0, "TR": 1, "BL": 2, "BR": 3} if h == 0 else
            {"TL": 4, "TR": 5, "BL": 6, "BR": 7})
        assert recipe["middle"]["code"] == m


def test_map_codes_match_positions():
    # The recipe metadata codes_by_quadrant must equal the frame rule applied at
    # the recipe's actual quadrant positions.
    for recipe_index, recipe in enumerate(lh2.recipes()):
        for ctrl in ("cs1", "cs2"):
            for pos in recipe["positions"][ctrl]:
                q = ("T" if pos["row"] < 4 else "B") + ("L" if pos["column"] < 4 else "R")
                assert lh2.map_code(recipe_index, pos["row"], pos["column"]) == \
                    recipe["map"]["codes_by_quadrant"][q]


def test_frames_are_deterministic_and_sized():
    for stage in lh2.STAGES:
        assert len(lh2.frame(stage)) == 307200
    assert lh2.frame("MAP") == lh2.frame("MAP")
