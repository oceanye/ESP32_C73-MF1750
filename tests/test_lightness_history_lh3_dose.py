"""LH3 dose-axis algorithm: frame/column invariants, no device involved."""
from __future__ import annotations

import pytest

from host.static_photo import lightness_history_lh3_dose as lh3


def test_dose_code_is_column_index():
    for row in range(8):
        for column in range(8):
            assert lh3.dose_code(row, column) == column
    with pytest.raises(ValueError):
        lh3.dose_code(8, 0)
    with pytest.raises(ValueError):
        lh3.dose_code(0, 8)


def test_dose_frames_column_pure():
    # Column c of each side carries code c in all 8 rows: probe every cell's
    # first pixel byte in the packed 4bpp frame.
    frame = lh3.frame("DOSE1")
    base = lh3.base
    for side in range(2):
        for row in range(8):
            for column in range(8):
                x = side * base.HALF + base.X0 + column * (base.CELL_W + base.GAP)
                y = base.Y0 + row * (base.CELL_H + base.GAP)
                byte = frame[y * (base.WIDTH // 2) + x // 2]
                assert byte == column * 17


def test_dose2_frame_byte_identical_to_dose1():
    assert lh3.frame("DOSE2") == lh3.frame("DOSE1")


def test_source_frame_all_white():
    assert set(lh3.frame("SOURCE")) == {0x77}
    assert lh3.frame("SOURCE") != lh3.frame("DOSE1")


def test_frame_histograms():
    source = lh3.payload_identity(lh3.frame("SOURCE"), True)["histogram"]
    assert source == [0, 0, 0, 0, 0, 0, 0, 614400]
    dose = lh3.payload_identity(lh3.frame("DOSE1"), True)["histogram"]
    # Each code owns one 8-cell column per side; code 7 also owns the background.
    assert dose == [33280] * 7 + [381440]
    assert lh3.payload_identity(lh3.frame("DOSE2"), True)["histogram"] == dose


def test_recipes_and_positions():
    recipes = lh3.recipes()
    assert len(recipes) == 8
    assert recipes[0]["recipe_id"] == "LH3D-S7-D0"
    assert recipes[7]["recipe_id"] == "LH3D-S7-D7"
    for code, recipe in enumerate(recipes):
        assert recipe["source"] == {"global_header": "active", "code": 7}
        assert recipe["dose1"] == {"global_header": "commented", "code": code}
        assert recipe["dose2"] == {"global_header": "commented", "code": code}
        assert recipe["repeats_per_controller"] == 8
        for ctrl in ("cs1", "cs2"):
            positions = recipe["positions"][ctrl]
            assert len(positions) == 8
            for row, position in enumerate(positions):
                assert position["row"] == row and position["column"] == code
                roi = position["local_roi"]
                assert roi["x"] == lh3.base.X0 + code * (lh3.base.CELL_W + lh3.base.GAP)
                assert roi["y"] == lh3.base.Y0 + row * (lh3.base.CELL_H + lh3.base.GAP)


def test_frames_are_deterministic_and_sized():
    for stage in lh3.STAGES:
        assert len(lh3.frame(stage)) == 307200
        assert lh3.frame(stage) == lh3.frame(stage)
    with pytest.raises(ValueError):
        lh3.frame("WHITE")
