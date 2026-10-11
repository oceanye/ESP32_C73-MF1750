"""Tests for the DITHER_ATLAS frame kit."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from host import epd_frame  # noqa: E402
from host.static_photo import lightness_history as base  # noqa: E402
from tools import mf1750_dither_atlas_frame_build as kit  # noqa: E402

OUT_DIR = ROOT / ".test-output/offline/DITHER_ATLAS_20261010_R1"
FRAME_SHA = "ded7b327e8af79777b14f9588de94dc9c4f53411e245cd6c9809b98276e8b355"


def _codes() -> np.ndarray:
    frame = (OUT_DIR / "atlas.frame4bpp").read_bytes()
    return np.array(list(epd_frame.unpack_pixels(frame, allowed_colors=list(range(8)))),
                    dtype=np.uint8).reshape(base.HEIGHT, base.WIDTH)


class AtlasKitTests(unittest.TestCase):
    def test_package_files_and_pin(self) -> None:
        frame = (OUT_DIR / "atlas.frame4bpp").read_bytes()
        self.assertEqual(kit._sha(frame), FRAME_SHA)
        manifest = json.loads((OUT_DIR / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["frame"]["sha256"], FRAME_SHA)

    def test_regeneration_byte_identical(self) -> None:
        rebuilt = epd_frame.pack_pixels(
            kit.build_frame().reshape(-1).tolist(), allowed_colors=list(range(8)))
        self.assertEqual(rebuilt, (OUT_DIR / "atlas.frame4bpp").read_bytes())

    def test_frame_validates_full_nibble_set(self) -> None:
        epd_frame.validate_frame((OUT_DIR / "atlas.frame4bpp").read_bytes(),
                                 allowed_colors=list(range(8)))

    def test_ladder_levels_are_monotone_in_coverage(self) -> None:
        codes = _codes()
        row_code = kit.CODES[0]
        counts = []
        for col in range(kit.COLS):
            x = kit.GRID_X0 + col * (kit.CELL_W + kit.GAP)
            y = kit.GRID_Y0
            region = codes[y:y + kit.CELL_H, x:x + kit.CELL_W]
            counts.append(int((region == row_code).sum()))
        self.assertEqual(counts, sorted(counts))
        self.assertEqual(counts[0], 0)
        self.assertEqual(counts[-1], kit.CELL_W * kit.CELL_H)

    def test_ladder_rows_use_their_codes(self) -> None:
        codes = _codes()
        for row in range(6):
            x = kit.GRID_X0 + 10 * (kit.CELL_W + kit.GAP)  # level 100%
            y = kit.GRID_Y0 + row * (kit.CELL_H + kit.GAP)
            region = codes[y:y + kit.CELL_H, x:x + kit.CELL_W]
            self.assertTrue((region == kit.CODES[row]).all(), row)

    def test_bridge_row_is_50_50(self) -> None:
        codes = _codes()
        for col, pair in enumerate(kit.BRIDGES):
            x = kit.GRID_X0 + col * (kit.CELL_W + kit.GAP)
            y = kit.GRID_Y0 + 6 * (kit.CELL_H + kit.GAP)
            region = codes[y:y + kit.CELL_H, x:x + kit.CELL_W]
            frac = float((region == pair[0]).mean())
            self.assertAlmostEqual(frac, 0.5, delta=0.02)
            self.assertTrue(set(np.unique(region)) <= set(pair), col)

    def test_anchor_row_sequence(self) -> None:
        codes = _codes()
        for col, code in enumerate(kit.ANCHOR_SEQ):
            x = kit.GRID_X0 + col * (kit.CELL_W + kit.GAP) + kit.CELL_W // 2
            y = kit.GRID_Y0 + 7 * (kit.CELL_H + kit.GAP) + kit.CELL_H // 2
            self.assertEqual(int(codes[y, x]), code, col)
        self.assertNotEqual(kit.ANCHOR_SEQ, kit.ANCHOR_SEQ[::-1])  # non-palindromic

    def test_orientation_bands(self) -> None:
        codes = _codes()
        # cells are painted over the bands inside the grid; the bands stay
        # intact in the x-margins that no cell covers
        self.assertTrue((codes[0:18, 0:20] == 3).all())
        self.assertTrue((codes[0:18, 1004:] == 3).all())
        self.assertTrue((codes[base.HEIGHT - 18:, 0:20] == 6).all())
        self.assertTrue((codes[base.HEIGHT - 18:, 1004:] == 6).all())

    def test_cell_map_coverage(self) -> None:
        cells = json.loads((OUT_DIR / "cell-map.json").read_text(encoding="utf-8"))
        self.assertEqual(len(cells), 6 * 11 + 11 + 11)
        ladder = [c for c in cells if c["kind"] == "ladder"]
        self.assertEqual(
            {(c["row"], c["column"]) for c in ladder},
            {(r, c) for r in range(6) for c in range(11)},
        )


if __name__ == "__main__":
    unittest.main()
