from __future__ import annotations

import json
from pathlib import Path
import unittest

from tools import mf1750_lut_attrib_diff as tool
from tools import mf1750_partial_block_build as build
from tools import mf1750_wf_wmask_build as wmask


class LutIdentityTests(unittest.TestCase):
    def test_1e_r20_identical_across_paths_and_module(self) -> None:
        evidence = tool.build_evidence()
        self.assertTrue(evidence["lut_identity"]["identical"])
        expected = wmask.build_offline_variant(0x0E, True)[0]["r20_sha256"]
        self.assertEqual(evidence["lut_identity"]["atlas_1e_r20_sha256"], expected)
        self.assertEqual(evidence["lut_identity"]["ptlw_1e_r20_sha256"], expected)
        self.assertEqual(evidence["lut_identity"]["module_1e_r20_sha256"], expected)

    def test_all_three_ptlw_profiles_match_module(self) -> None:
        evidence = tool.build_evidence()
        for label, (mask, group) in {"1E": (0x0E, True), "0E": (0x0E, False), "1C": (0x0C, True)}.items():
            with self.subTest(profile=label):
                expected = wmask.build_offline_variant(mask, group)[0]["r20_sha256"]
                self.assertEqual(
                    evidence["lut_identity"]["profiles"][label]["ptlw_r20_sha256"],
                    expected,
                )
                self.assertEqual(
                    evidence["lut_identity"]["profiles"][label]["module_r20_sha256"],
                    expected,
                )

    def test_shared_active_payload_pins(self) -> None:
        evidence = tool.build_evidence()
        self.assertEqual(evidence["lut_identity"]["pwr_sha256"], wmask.PWR_SHA256)
        self.assertEqual(evidence["lut_identity"]["pll_sha256"], wmask.PLL_SHA256)
        self.assertEqual(evidence["lut_identity"]["r21_sha256"], wmask.R21_SHA256)


class RefreshSequenceDiffTests(unittest.TestCase):
    def test_btst2_byte_pins_match_driver_source(self) -> None:
        r2g = (Path(__file__).resolve().parents[1] /
               "src/wf_bisect_r2g_epd_driver.cpp").read_text(encoding="utf-8")
        self.assertIn("epdCommand(BTST2);\n  epdData(0x6F);\n  epdData(0x1F);\n"
                      "  epdData(0x17);\n  epdData(0x49);", r2g)
        self.assertIn("epdCommand(BTST2);\n  epdData(0x6F);\n  epdData(0x1F);\n"
                      "  epdData(0x17);\n  epdData(0x17);", r2g)

    def test_ptlw_clean_refresh_has_no_btst2(self) -> None:
        text = (Path(__file__).resolve().parents[1] /
                "src/partial_block_ptlw_v2_epd_driver.cpp").read_text(encoding="utf-8")
        start = text.index("bool pbRefreshCleanPtlw()")
        end = text.index("}", text.index("return epdPostDisplayPowerCut();", start))
        body = text[start:end]
        self.assertNotIn("epdCommand(BTST2)", body)
        self.assertNotIn("epdData(0x49)", body)
        for stage in ("epdCommand(PON)", "epdCommand(DRF)", "epdCommand(POF)"):
            self.assertIn(stage, body)

    def test_only_driven_byte_difference_recorded(self) -> None:
        diff = tool.build_evidence()["refresh_sequence_diff"]["only_driven_byte_difference"]
        self.assertEqual(diff["atlas_value"], "0x49")
        self.assertIn("0x17", diff["ptlw_value"])
        self.assertEqual(diff["semantics"]["0x49"]["vphssc_drv"], 2)
        self.assertEqual(diff["semantics"]["0x17"]["vphssc_drv"], 1)

    def test_drf_bins_are_the_same_family(self) -> None:
        evidence = tool.build_evidence()
        self.assertTrue(evidence["drf_bins"]["same_slow_bin"])
        for value in evidence["drf_bins"]["atlas_full_frame_ms"] + \
                evidence["drf_bins"]["ptlw_partial_ms"]:
            self.assertTrue(31037 <= value <= 34305)


class PtlwWindowDirectionTests(unittest.TestCase):
    def test_window_180_mapping(self) -> None:
        self.assertEqual(tool.window_180({"x": 48, "y": 64, "w": 160, "h": 120}),
                         {"x": 304, "y": 416, "w": 160, "h": 120})
        self.assertEqual(tool.window_180({"x": 304, "y": 240, "w": 160, "h": 120}),
                         {"x": 48, "y": 240, "w": 160, "h": 120})
        self.assertEqual(tool.window_180({"x": 48, "y": 416, "w": 160, "h": 120}),
                         {"x": 304, "y": 64, "w": 160, "h": 120})

    def test_measured_spans_match_180_not_y_only(self) -> None:
        evidence = tool.build_evidence()["ptlw_window_direction"]
        measured = evidence["measurements"][0]
        flipped = tool.window_180(measured["window"])
        cs1 = measured["observed_spans_cs1"]
        cs2 = measured["observed_spans_cs2"]
        # Within-controller 180 prediction: CS1 x in [304,464], CS2 x in [816,976].
        self.assertGreaterEqual(cs1["x"][0], 250)
        self.assertLessEqual(cs1["x"][1], 500)
        self.assertGreaterEqual(cs2["x"][0], 740)
        self.assertLessEqual(cs2["x"][1], 1000)
        # Y-only flip prediction would put CS1 x in [48,208]; clearly violated.
        self.assertGreater(cs1["x"][0], 208)
        self.assertGreater(cs2["x"][0], 720)
        self.assertGreaterEqual(cs1["y"][0], 400)
        self.assertEqual(flipped["x"], 304)
        self.assertEqual(flipped["y"], 416)


if __name__ == "__main__":
    unittest.main()
