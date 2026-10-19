from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tools import mf1750_multi_roi_lab as roi_lab
from tools import mf1750_partial_block_build as tool
from tools import mf1750_wf_wmask_build as wmask

ROOT = Path(__file__).resolve().parents[1]

# Sealed 2026-08 clean-PTLW transport pins (tools/mf1750_runtime_lut_true_r20_partial_hold_v1_identity.inc).
SEALED_PTLW_PAYLOADS = (
    "003000cf004000b701",
    "013001cf00f0016701",
    "003000cf01a0021701",
)
SEALED_PRELOAD_SHA256 = "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd"
SEALED_CROP_SHA256 = "e9a15a094703faaea3fdf53af7e04da21717008ab4bb228799712b2fced03c65"
SEALED_COMBINED_SHA256 = "73871e076e8a8b3af18e19616312a9d502e66330dfbdd506b700b5cf882d6825"
SEALED_PRELOAD_FNV1A = 0x285715C5
SEALED_CROP_FNV1A = 0x0E5DBBC5
SEALED_COMBINED_FNV1A = 0x706833C5


class RouteALayoutTests(unittest.TestCase):
    def test_roi_layout_matches_frozen_design(self) -> None:
        self.assertEqual(len(tool.ATLAS_ROIS), 7)
        self.assertEqual([roi["code"] for roi in tool.ATLAS_ROIS], [0, 1, 2, 3, 4, 5, 6])
        self.assertEqual(
            [(roi["x"], roi["y"], roi["w"], roi["h"]) for roi in tool.ATLAS_ROIS],
            [(48, 64, 192, 160), (288, 64, 192, 160), (544, 64, 192, 160),
             (792, 64, 192, 160), (48, 384, 192, 160), (288, 384, 192, 160),
             (544, 384, 192, 160)],
        )
        tool._validate_atlas_layout()  # raises on alignment/seam/bounds/overlap drift

    def test_frame_bytes_and_identity(self) -> None:
        frame = tool.build_atlas_frame()
        self.assertEqual(len(frame), 307200)
        # White background is code 7 pairs; every untouched pixel stays 0x77.
        self.assertEqual(frame[0], 0x77)
        self.assertEqual(frame[-1], 0x77)
        for roi in tool.ATLAS_ROIS:
            with self.subTest(roi=roi["name"]):
                pair = (roi["code"] << 4) | roi["code"]
                first = roi["y"] * 512 + roi["x"] // 2
                last = (roi["y"] + roi["h"] - 1) * 512 + (roi["x"] + roi["w"]) // 2 - 1
                self.assertEqual(frame[first], pair)
                self.assertEqual(frame[last], pair)
                self.assertEqual(frame[first - 1], 0x77)
        report = tool.build_report()
        self.assertEqual(report["route_a"]["frame"]["sha256"], tool._sha256(frame))
        self.assertEqual(report["route_a"]["frame"]["fnv1a"], tool._fnv1a(frame))
        self.assertEqual(report["route_a"]["frame"]["background_code"], 7)

    def test_controller_streams_follow_identity_mapping(self) -> None:
        frame = tool.build_atlas_frame()
        cs1 = tool.controller_stream(frame, False)
        cs2 = tool.controller_stream(frame, True)
        self.assertEqual(len(cs1), 153600)
        self.assertEqual(len(cs2), 153600)
        self.assertEqual(cs1[:256], frame[:256])
        self.assertEqual(cs2[:256], frame[256:512])
        report = tool.build_report()["route_a"]["controller_streams"]
        self.assertEqual(report["cs1"]["sha256"], tool._sha256(cs1))
        self.assertEqual(report["cs2"]["sha256"], tool._sha256(cs2))
        self.assertNotEqual(report["cs1"]["sha256"], report["cs2"]["sha256"])

    def test_layout_hash_is_canonical_and_stable(self) -> None:
        doc = tool.atlas_layout_doc()
        sha = tool._sha256(tool._canonical(doc))
        self.assertEqual(sha, tool._sha256(tool._canonical(tool.atlas_layout_doc())))
        self.assertEqual(tool.build_report()["route_a"]["layout"]["sha256"], sha)
        self.assertEqual(doc["background_code"], 7)
        self.assertTrue(doc["seam_avoidance_x512"])


class RouteBContractTests(unittest.TestCase):
    def test_windows_match_handoff_geometry(self) -> None:
        self.assertEqual(
            [(w["x"], w["y"], w["w"], w["h"]) for w in tool.PTLW_WINDOWS],
            [(48, 64, 160, 120), (304, 240, 160, 120), (48, 416, 160, 120)],
        )
        tool._validate_ptlw_windows()

    def test_ptlw_payloads_match_sealed_clean_recipe(self) -> None:
        payloads = [tool.ptlw_payload(window).hex() for window in tool.PTLW_WINDOWS]
        self.assertEqual(payloads, list(SEALED_PTLW_PAYLOADS))
        for window in tool.PTLW_WINDOWS:
            raw = tool.ptlw_payload(window)
            self.assertEqual(len(raw), 9)
            self.assertEqual(raw[-1], 0x01)
            x_end = (raw[2] << 8) | raw[3]
            y_end = (raw[6] << 8) | raw[7]
            self.assertEqual(x_end, window["x"] + window["w"] - 1)
            self.assertEqual(y_end, window["y"] + window["h"] - 1)

    def test_transport_identities_match_sealed_august_pins(self) -> None:
        identities = tool.route_b_identities()
        self.assertEqual(identities["preload_dtm"]["sha256"], SEALED_PRELOAD_SHA256)
        self.assertEqual(identities["preload_dtm"]["fnv1a"], SEALED_PRELOAD_FNV1A)
        self.assertEqual(identities["preload_dtm"]["bytes"], 153600)
        self.assertEqual(identities["preload_dtm"]["code"], 7)
        self.assertEqual(identities["crop_dtm"]["sha256"], SEALED_CROP_SHA256)
        self.assertEqual(identities["crop_dtm"]["fnv1a"], SEALED_CROP_FNV1A)
        self.assertEqual(identities["crop_dtm"]["bytes"], 9600)
        self.assertEqual(identities["crop_dtm"]["code"], 0)
        self.assertEqual(identities["combined_dtm"]["sha256"], SEALED_COMBINED_SHA256)
        self.assertEqual(identities["combined_dtm"]["fnv1a"], SEALED_COMBINED_FNV1A)

    def test_action_profile_binding_matches_full_frame_profiles(self) -> None:
        self.assertEqual(tool.PTLW_PROFILE_LABELS, ("1E", "0E", "1C"))
        profiles = tool._profile_reports()
        expected = {
            "1E": wmask.build_offline_variant(0x0E, True)[0],
            "0E": wmask.build_offline_variant(0x0E)[0],
            "1C": wmask.build_offline_variant(0x0C, True)[0],
        }
        for label in ("1E", "0E", "1C"):
            with self.subTest(profile=label):
                self.assertEqual(profiles[label]["r20_sha256"],
                                 expected[label]["r20_sha256"])
                self.assertEqual(profiles[label]["pwr_sha256"], wmask.PWR_SHA256)
                self.assertEqual(profiles[label]["pll_sha256"], wmask.PLL_SHA256)
                self.assertEqual(profiles[label]["r21_sha256"], wmask.R21_SHA256)
        report = tool.build_report()["route_b"]
        self.assertEqual(
            [action["profile"] for action in report["actions"]],
            [None, "1E", "0E", "1C", None],
        )
        for action in report["actions"]:
            if action["profile"] is None:
                continue
            with self.subTest(action=action["ordinal"]):
                self.assertTrue(
                    report["profiles"][action["profile"]]["family_label_is_not_bitmask"]
                )

    def test_refresh_sequence_is_the_clean_ptlw_recipe(self) -> None:
        transport = tool.build_report()["route_b"]["transport"]
        order = transport["order"]
        self.assertEqual(
            order,
            [
                "LOAD_SELECTED_PWR_PLL_PSR_TRES_BROADCAST",
                "LOAD_SELECTED_R20_R21_CS1",
                "LOAD_SAME_SELECTED_R20_R21_CS2",
                "FULL_CODE7_DTM_PRESTAGE_CS1_NO_REFRESH",
                "FULL_CODE7_DTM_PRESTAGE_CS2_NO_REFRESH",
                "PTLW_CS1_INCLUSIVE_ONCE",
                "CROPPED_TARGET_DTM_CS1",
                "PTLW_CS2_INCLUSIVE_ONCE",
                "CROPPED_TARGET_DTM_CS2",
                "PON_BUSY_COMPLETE",
                "DRF_00_BUSY_COMPLETE",
                "POF_00_BUSY_COMPLETE",
            ],
        )
        ptlw_index = max(i for i, step in enumerate(order) if step.startswith("PTLW"))
        pon_index = order.index("PON_BUSY_COMPLETE")
        self.assertLess(ptlw_index, pon_index)
        self.assertFalse(transport["action_stage_btst2"])
        self.assertFalse(transport["action_stage_cdi"])
        self.assertFalse(transport["command_0x86"])
        report = tool.build_report()["route_b"]
        self.assertEqual(report["ptlw"]["writes_per_controller_per_action"], 1)
        self.assertFalse(report["ptlw"]["repeat_after_pon"])
        self.assertEqual(tool.build_report()["spi_hz"], 1_000_000)


class GeneratedSourcesTests(unittest.TestCase):
    def test_render_is_deterministic_and_matches_disk(self) -> None:
        first = tool.render_all()
        second = tool.render_all()
        self.assertEqual(first, second)
        for relative, content in first.items():
            with self.subTest(source=relative):
                path = ROOT / relative
                self.assertTrue(path.is_file())
                self.assertEqual(path.read_bytes(), content.encode("utf-8"))

    def test_both_drivers_share_the_byte_identical_r2g_tail(self) -> None:
        tail = tool._r2g_tail()
        for relative in (
            "src/partial_atlas_1e_epd_driver.cpp",
            "src/partial_block_ptlw_epd_driver.cpp",
        ):
            with self.subTest(driver=relative):
                text = tool.render_all()[relative]
                self.assertIn(tail, text)
                self.assertEqual(
                    tool._sha256(tail.encode("utf-8")),
                    tool.build_report()["runtime_tail_sha256"],
                )

    def test_route_b_driver_binds_the_full_frame_profile_objects(self) -> None:
        driver = tool.render_all()["src/partial_block_ptlw_epd_driver.cpp"]
        for label in ("1E", "0E", "1C"):
            with self.subTest(profile=label):
                self.assertIn(f'#include "generated/spd1657_wf_wmask_{label}.inc"', driver)
        self.assertIn("namespace pb_profile_a = mf1750::runtime_lut::wf_wmask_1E;", driver)
        self.assertIn("namespace pb_profile_b = mf1750::runtime_lut::wf_wmask_0E;", driver)
        self.assertIn("namespace pb_profile_c = mf1750::runtime_lut::wf_wmask_1C;", driver)
        # No new waveform bytes: the only kR20Payload written to the panel are
        # the three sealed profile objects.
        self.assertNotIn("kR20Payload[535] = {", driver)

    def test_mains_register_only_the_intended_actions(self) -> None:
        rendered = tool.render_all()
        atlas_main = rendered["src/partial_atlas_1e_main.cpp"]
        ptlw_main = rendered["src/partial_block_ptlw_main.cpp"]
        self.assertIn('MF1750_PARTIAL_BLOCK_ATLAS_1E_20261020', atlas_main)
        self.assertIn('MF1750_PARTIAL_BLOCK_PTLW_20261020', ptlw_main)
        self.assertIn('server.on("/api/partial-atlas-1e"', atlas_main)
        self.assertIn('server.on("/api/frame", HTTP_POST', atlas_main)
        for route in ("factory-white", "patch-a-1e", "patch-b-0e",
                      "patch-c-1c", "white-recovery"):
            with self.subTest(route=route):
                self.assertIn(f'server.on("/api/partial-block/{route}"', ptlw_main)
        self.assertNotIn('server.on("/api/frame"', ptlw_main)
        self.assertNotIn("frame-ingress", ptlw_main)

    def test_env_tag_and_doc_registration(self) -> None:
        platformio = (ROOT / "platformio.ini").read_text(encoding="utf-8")
        frame_tool = (ROOT / "tools/mf1750_frame_tool.py").read_text(encoding="utf-8")
        api_doc = (ROOT / "docs/MF1750_DRIVER_API.md").read_text(encoding="utf-8")
        for env, tag in (
            (tool.ATLAS_ENV, tool.ATLAS_TAG),
            (tool.PTLW_ENV, tool.PTLW_TAG),
        ):
            with self.subTest(env=env):
                self.assertIn(f"[env:{env}]", platformio)
                self.assertIn(tag, frame_tool)
                self.assertIn(tag, api_doc)
                self.assertIn(f'FW_BUILD_TAG = "{tag}"',
                              tool.render_all()[
                                  "src/partial_atlas_1e_main.cpp"
                                  if env == tool.ATLAS_ENV
                                  else "src/partial_block_ptlw_main.cpp"
                              ])
        ptlw_section = platformio.split(f"[env:{tool.PTLW_ENV}]")[1]
        self.assertIn("MF1750_PARTIAL_BLOCK_PTLW_BUILD=1", ptlw_section)
        self.assertIn("MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY=1", ptlw_section)
        self.assertNotIn("upload_speed", ptlw_section.split("[env:")[1]
                         if ptlw_section.count("[env:") > 1 else "")


class MeasurementToolCompatibilityTests(unittest.TestCase):
    def _load(self, doc: dict) -> list[dict]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "layout.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            regions, _payload = roi_lab._load_layout(path)
        return regions

    def test_route_a_roi_list_loads_in_multi_roi_lab(self) -> None:
        regions = self._load(tool.atlas_roi_list_doc())
        self.assertEqual(len(regions), 8)
        self.assertEqual(
            [(region["name"], region["code"]) for region in regions],
            [("code0", 0), ("code1", 1), ("code2", 2), ("code3", 3),
             ("code4", 4), ("code5", 5), ("code6", 6), ("bg_ref", 7)],
        )
        for region in regions:
            self.assertEqual((region["w"], region["h"]), (192.0, 160.0))

    def test_route_b_roi_list_loads_in_multi_roi_lab(self) -> None:
        regions = self._load(tool.ptlw_roi_list_doc())
        self.assertEqual(
            [region["name"] for region in regions],
            ["a_cs1", "a_cs2", "b_cs1", "b_cs2", "c_cs1", "c_cs2",
             "bg_north", "bg_south"],
        )
        by_name = {region["name"]: region for region in regions}
        self.assertEqual((by_name["a_cs1"]["x"], by_name["a_cs1"]["y"]), (48.0, 64.0))
        self.assertEqual((by_name["a_cs2"]["x"], by_name["a_cs2"]["y"]), (560.0, 64.0))
        self.assertEqual((by_name["b_cs2"]["x"], by_name["b_cs2"]["y"]), (816.0, 240.0))
        self.assertEqual((by_name["c_cs2"]["x"], by_name["c_cs2"]["y"]), (560.0, 416.0))


if __name__ == "__main__":
    unittest.main()
