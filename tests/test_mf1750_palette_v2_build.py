"""Tests for the palette v2 builder's fail-closed behavior on collapsed data."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from host.color_pipeline.palette import PaletteError  # noqa: E402
from tools import mf1750_palette_v2_build as v2  # noqa: E402

BLOCKED_REPORT = ROOT / ".test-output/offline/PALETTE_V2_BLOCKED_20261011_V1/v2-blocked-report.json"


class PaletteV2BuildTests(unittest.TestCase):
    def test_v2_build_fails_closed_on_collapsed_gamut(self) -> None:
        # the daylight measurement violates two l535_r20 invariants:
        # black is not the darkest entry and yellow has no chroma
        with self.assertRaises(PaletteError):
            v2.main()
        # and it must refuse before writing any artifact
        self.assertFalse(v2.V2_PALETTE.exists())
        self.assertFalse(v2.V2_PROFILE.exists())

    def test_blocked_report_records_both_violations(self) -> None:
        report = json.loads(BLOCKED_REPORT.read_text(encoding="utf-8"))
        self.assertTrue(report["blocked"])
        rules = {v["rule"] for v in report["violations"]}
        self.assertEqual(len(rules), 2)
        self.assertTrue(any("darkest" in rule for rule in rules))
        self.assertTrue(any("chromatic" in rule for rule in rules))

    def test_drift_table_covers_all_six_codes(self) -> None:
        report = json.loads(BLOCKED_REPORT.read_text(encoding="utf-8"))
        self.assertEqual(len(report["drift_table"]), 6)
        for row in report["drift_table"]:
            self.assertIn("delta_e00", row)
            self.assertGreater(row["delta_e00"], 0)

    def test_v1_palette_untouched(self) -> None:
        from host.color_pipeline.palette import load_palette

        v1 = load_palette(ROOT / "host/color_pipeline/palettes/mf1750_l535_measured_v1.json")
        self.assertEqual(
            v1.canonical_sha256,
            "50bd8193b722224dc9560537c8d33269797575c566a5931fc87cff71ce1b5055",
        )


if __name__ == "__main__":
    unittest.main()
