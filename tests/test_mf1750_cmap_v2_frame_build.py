"""Tests for the MAP-v2 color-intermediate frame kit."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from host import epd_frame  # noqa: E402
from host.static_photo import lightness_history as base  # noqa: E402
from tools import mf1750_cmap_v2_frame_build as kit  # noqa: E402

OUT_DIR = ROOT / ".test-output/offline/CMAP_V2_20261009_R1"
HISTORY_SHA = "9136ec686620da2c2ef3ac718406e77065e27adee28df6a47cb2b1b629212208"
PROBE_SHA = "7a2fb6fdba5bd9db6129486c4a44cb5d403f8e1a62391b9af8fe61819b77942e"


def _codes(frame_bytes: bytes) -> list[int]:
    return list(epd_frame.unpack_pixels(frame_bytes, allowed_colors=list(range(8))))


def _cell_code(codes: list[int], x: int, y: int) -> int:
    return codes[y * base.WIDTH + x]


class FrameKitTests(unittest.TestCase):
    def test_package_files_exist_and_match_pins(self) -> None:
        self.assertEqual(
            epd_frame and Path(OUT_DIR / "history.frame4bpp").read_bytes()
            and kit._sha((OUT_DIR / "history.frame4bpp").read_bytes()),
            HISTORY_SHA,
        )
        self.assertEqual(kit._sha((OUT_DIR / "probe.frame4bpp").read_bytes()), PROBE_SHA)
        manifest = json.loads((OUT_DIR / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["audit"], {"passed": True, "errors": []})

    def test_regeneration_is_byte_identical(self) -> None:
        self.assertEqual(kit._frame("history"), (OUT_DIR / "history.frame4bpp").read_bytes())
        self.assertEqual(kit._frame("probe"), (OUT_DIR / "probe.frame4bpp").read_bytes())

    def test_frames_validate_full_nibble_set(self) -> None:
        for name in ("history", "probe"):
            frame = (OUT_DIR / f"{name}.frame4bpp").read_bytes()
            epd_frame.validate_frame(frame, allowed_colors=list(range(8)))

    def test_history_frame_rows_are_uniform_history_codes(self) -> None:
        codes = _codes((OUT_DIR / "history.frame4bpp").read_bytes())
        for row in range(8):
            for column in range(8):
                x = base.X0 + column * (base.CELL_W + base.GAP) + base.CELL_W // 2
                y = base.Y0 + row * (base.CELL_H + base.GAP) + base.CELL_H // 2
                self.assertEqual(_cell_code(codes, x, y), row, (row, column))
                self.assertEqual(
                    _cell_code(codes, base.HALF + x, y), row, ("cs2", row, column)
                )

    def test_probe_frame_columns_are_target_codes(self) -> None:
        codes = _codes((OUT_DIR / "probe.frame4bpp").read_bytes())
        for row in range(8):
            for column in range(8):
                x = base.X0 + column * (base.CELL_W + base.GAP) + base.CELL_W // 2
                y = base.Y0 + row * (base.CELL_H + base.GAP) + base.CELL_H // 2
                self.assertEqual(_cell_code(codes, x, y), column, (row, column))
                self.assertEqual(
                    _cell_code(codes, base.HALF + x, y), column, ("cs2", row, column)
                )

    def test_calibration_strip_codes(self) -> None:
        history = _codes((OUT_DIR / "history.frame4bpp").read_bytes())
        probe = _codes((OUT_DIR / "probe.frame4bpp").read_bytes())
        for row in range(8):
            x = kit.CAL_X + base.CELL_W // 2
            y = base.Y0 + row * (base.CELL_H + base.GAP) + base.CELL_H // 2
            self.assertEqual(_cell_code(history, x, y), 7, ("history", row))
            self.assertEqual(_cell_code(probe, x, y), row, ("probe", row))
            self.assertEqual(_cell_code(probe, base.HALF + x, y), row, ("probe cs2", row))

    def test_reference_strip_blocks(self) -> None:
        probe = _codes((OUT_DIR / "probe.frame4bpp").read_bytes())
        block_w = base.HALF // kit.REF_BLOCKS
        for block in range(kit.REF_BLOCKS):
            x = block * block_w + block_w // 2
            y = kit.REF_Y + kit.REF_H // 2
            expected = 3 if block % 2 else 7
            self.assertEqual(_cell_code(probe, x, y), expected, ("probe", block))

    def test_cell_map_coverage(self) -> None:
        cells = json.loads((OUT_DIR / "cell-map.json").read_text(encoding="utf-8"))
        matrix = [c for c in cells if c["kind"] == "matrix"]
        pairs = {(c["side"], c["history_code"], c["target_code"]) for c in matrix}
        self.assertEqual(
            pairs,
            {(side, h, t) for side in ("CS1", "CS2") for h in range(8) for t in range(8)},
        )
        calibration = [c for c in cells if c["kind"] == "calibration_code_axis"]
        self.assertEqual(len(calibration), 16)
        for c in calibration:
            self.assertEqual(c["history_code"], 7)
            self.assertEqual(c["target_code"], c["row"])

    def test_background_is_white_code(self) -> None:
        for name in ("history", "probe"):
            codes = _codes((OUT_DIR / f"{name}.frame4bpp").read_bytes())
            self.assertEqual(_cell_code(codes, 8, 8), 7, name)
            self.assertEqual(_cell_code(codes, 600, 8), 7, name)


if __name__ == "__main__":
    unittest.main()
