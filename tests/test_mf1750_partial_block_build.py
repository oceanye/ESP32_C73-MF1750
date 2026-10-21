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

    def test_v2_layout_swaps_only_the_two_probe_slots(self) -> None:
        regions_v1, bg_v1 = tool.atlas_regions("V1")
        regions_v2, bg_v2 = tool.atlas_regions("V2")
        self.assertIsNotNone(bg_v1)
        self.assertIsNone(bg_v2)
        self.assertEqual(
            [(r["x"], r["y"], r["w"], r["h"]) for r in regions_v2],
            [(r["x"], r["y"], r["w"], r["h"]) for r in regions_v1] + [
                (bg_v1["x"], bg_v1["y"], bg_v1["w"], bg_v1["h"])],
        )
        self.assertEqual([r["code"] for r in regions_v2], [0, 1, 2, 3, 4, 5, 7, 6])
        self.assertEqual(regions_v2[6]["name"], "code7_probe")
        self.assertEqual(regions_v2[6]["x"], 544)
        self.assertEqual(regions_v2[7]["name"], "code6")
        self.assertEqual(regions_v2[7]["x"], 792)
        tool._validate_atlas_layout("V2")
        # V2 frame differs from V1 only in the two swapped slots, both on CS2.
        frame_v1 = tool.build_atlas_frame("V1")
        frame_v2 = tool.build_atlas_frame("V2")
        self.assertEqual(
            tool.controller_stream(frame_v1, False),
            tool.controller_stream(frame_v2, False),
        )
        self.assertNotEqual(
            tool.controller_stream(frame_v1, True),
            tool.controller_stream(frame_v2, True),
        )
        diff = [i for i, pair in enumerate(zip(frame_v1, frame_v2))
                if pair[0] != pair[1]]
        # (544,384): 0x66 -> 0x77; (792,384): 0x77 -> 0x66.
        self.assertEqual(len(diff), 2 * 192 * 160 // 2)
        for index in diff:
            row, byte_in_row = divmod(index, 512)
            self.assertGreaterEqual(row, 384)
            self.assertLess(row, 544)
            self.assertTrue(272 <= byte_in_row < 368 or 396 <= byte_in_row < 492)
            self.assertEqual(
                {frame_v1[index], frame_v2[index]}, {0x66, 0x77}
            )


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
        identities = tool.route_b_identities("V1")
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

    def test_v2_transport_differs_only_in_patch_code(self) -> None:
        v1 = tool.route_b_identities("V1")
        v2 = tool.route_b_identities("V2")
        self.assertEqual(v2["preload_dtm"], v1["preload_dtm"])
        self.assertEqual(v2["ptlw_payloads_hex"], v1["ptlw_payloads_hex"])
        self.assertEqual(v2["crop_dtm"]["code"], 4)
        self.assertEqual(v2["crop_dtm"]["bytes"], 9600)
        self.assertEqual(
            v2["crop_dtm"]["sha256"],
            "bb64c1ea9e2c0ee91322ae077ba61abd99c9265afcb2dd60a6b063077f1968a9",
        )
        self.assertEqual(
            v2["combined_dtm"]["sha256"],
            "b179a9665f2e449780b77d8575dcb244715e97b09053faf8f0fa77e88a692f93",
        )
        self.assertEqual(v2["combined_dtm"]["bytes"], 163200)
        report = tool.build_report("V2")
        self.assertIn("0 -> 4", report["changes_vs_v1"]["route_b_patch_code"])
        self.assertEqual(report["route_b"]["roi_list"]["layout_revision"], "V2")
        self.assertEqual(
            [r["code"] for r in report["route_b"]["roi_list"]["regions"][:6]],
            [4] * 6,
        )

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
        for version in tool.ATLAS_VERSIONS:
            first = tool.render_version(version)
            second = tool.render_version(version)
            self.assertEqual(first, second)
            for relative, content in first.items():
                with self.subTest(version=version, source=relative):
                    path = ROOT / relative
                    self.assertTrue(path.is_file())
                    self.assertEqual(path.read_bytes(), content.encode("utf-8"))

    def test_both_drivers_share_the_byte_identical_r2g_tail(self) -> None:
        tail = tool._r2g_tail()
        for version in tool.ATLAS_VERSIONS:
            names = tool._version_names(version)
            for key in ("atlas_driver", "ptlw_driver"):
                relative = names[key]
                with self.subTest(version=version, driver=relative):
                    text = tool.render_version(version)[relative]
                    self.assertIn(tail, text)
                    self.assertEqual(
                        tool._sha256(tail.encode("utf-8")),
                        tool.build_report(version)["runtime_tail_sha256"],
                    )

    def test_route_b_driver_binds_the_full_frame_profile_objects(self) -> None:
        for version in tool.ATLAS_VERSIONS:
            driver = tool.render_version(version)[
                tool._version_names(version)["ptlw_driver"]]
            with self.subTest(version=version):
                for label in ("1E", "0E", "1C"):
                    self.assertIn(f'#include "generated/spd1657_wf_wmask_{label}.inc"', driver)
                self.assertIn("namespace pb_profile_a = mf1750::runtime_lut::wf_wmask_1E;", driver)
                self.assertIn("namespace pb_profile_b = mf1750::runtime_lut::wf_wmask_0E;", driver)
                self.assertIn("namespace pb_profile_c = mf1750::runtime_lut::wf_wmask_1C;", driver)
                # No new waveform bytes: the only kR20Payload written to the panel are
                # the three sealed profile objects.
                self.assertNotIn("kR20Payload[535] = {", driver)

    def test_v2_ptlw_driver_binds_code4_patch(self) -> None:
        driver = tool.render_version("V2")[
            tool._version_names("V2")["ptlw_driver"]]
        self.assertIn('partial_block_ptlw_v2_contract.inc', driver)
        self.assertIn("namespace pb = mf1750::partial_block::ptlw_v2;", driver)
        contract = tool.render_version("V2")[
            "src/generated/partial_block_ptlw_v2_contract.inc"]
        self.assertIn("kPatchCode = 0x04", contract)
        self.assertIn("kPreloadCode = 0x07", contract)

    def test_mains_register_only_the_intended_actions(self) -> None:
        for version in tool.ATLAS_VERSIONS:
            names = tool._version_names(version)
            rendered = tool.render_version(version)
            atlas_main = rendered[names["atlas_main"]]
            ptlw_main = rendered[names["ptlw_main"]]
            with self.subTest(version=version):
                self.assertIn(names["atlas_tag"], atlas_main)
                self.assertIn(names["ptlw_tag"], ptlw_main)
                self.assertIn('server.on("/api/partial-atlas-1e"', atlas_main)
                self.assertIn('server.on("/api/frame", HTTP_POST', atlas_main)
                for route in ("factory-white", "patch-a-1e", "patch-b-0e",
                              "patch-c-1c", "white-recovery"):
                    self.assertIn(f'server.on("/api/partial-block/{route}"', ptlw_main)
                self.assertNotIn('server.on("/api/frame"', ptlw_main)
                self.assertNotIn("frame-ingress", ptlw_main)

    def test_env_tag_and_doc_registration(self) -> None:
        platformio = (ROOT / "platformio.ini").read_text(encoding="utf-8")
        frame_tool = (ROOT / "tools/mf1750_frame_tool.py").read_text(encoding="utf-8")
        api_doc = (ROOT / "docs/MF1750_DRIVER_API.md").read_text(encoding="utf-8")
        for version in tool.ATLAS_VERSIONS:
            names = tool._version_names(version)
            for env_key, tag_key, main_key in (
                ("atlas_env", "atlas_tag", "atlas_main"),
                ("ptlw_env", "ptlw_tag", "ptlw_main"),
            ):
                env, tag = names[env_key], names[tag_key]
                with self.subTest(version=version, env=env):
                    self.assertIn(f"[env:{env}]", platformio)
                    self.assertIn(tag, frame_tool)
                    self.assertIn(tag, api_doc)
                    self.assertIn(f'FW_BUILD_TAG = "{tag}"',
                                  tool.render_version(version)[names[main_key]])
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

    def test_v2_roi_lists_load_in_multi_roi_lab(self) -> None:
        atlas_regions = self._load(tool.atlas_roi_list_doc("V2"))
        self.assertEqual(
            [(region["name"], region["code"]) for region in atlas_regions],
            [("code0", 0), ("code1", 1), ("code2", 2), ("code3", 3),
             ("code4", 4), ("code5", 5), ("code7_probe", 7), ("code6", 6)],
        )
        ptlw_regions = self._load(tool.ptlw_roi_list_doc("V2"))
        self.assertEqual(
            [region["code"] for region in ptlw_regions[:6]], [4] * 6,
        )


class SpatialDecodeAuditTests(unittest.TestCase):
    """Per-pixel decode cross-check for a spatially-varying frame.

    The L535 full-frame path historically refreshed only uniform frames, where
    a controller-mapping error cannot be seen.  This audit replays the
    driver's exact MAP_ORIENT_V1 cascade mapping (CS1 = left half rows, CS2 =
    right half rows, no flips or nibble swap) over the compiled route A frame
    and verifies every pixel position decodes to the intended code.
    """

    @staticmethod
    def _decode_display(version: str = "V1") -> bytearray:
        frame = tool.build_atlas_frame(version)
        streams = (tool.controller_stream(frame, False),
                   tool.controller_stream(frame, True))
        disp = bytearray(tool.WIDTH * tool.HEIGHT)
        for second, stream in enumerate(streams):
            for y in range(tool.HEIGHT):
                row = stream[y * 256:(y + 1) * 256]
                base = second * tool.CONTROLLER_WIDTH
                for bx in range(256):
                    disp[y * tool.WIDTH + base + bx * 2] = row[bx] >> 4
                    disp[y * tool.WIDTH + base + bx * 2 + 1] = row[bx] & 0x0F
        return disp

    def test_every_region_decodes_to_pure_intended_code(self) -> None:
        for version in tool.ATLAS_VERSIONS:
            disp = self._decode_display(version)
            regions, background_reference = tool.atlas_regions(version)
            for roi in list(regions) + ([background_reference] if background_reference else []):
                with self.subTest(version=version, region=roi["name"]):
                    seen = {
                        disp[y * tool.WIDTH + x]
                        for y in range(roi["y"], roi["y"] + roi["h"])
                        for x in range(roi["x"], roi["x"] + roi["w"])
                    }
                    self.assertEqual(seen, {roi["code"]})

    def test_decoded_background_is_pure_code7(self) -> None:
        for version in tool.ATLAS_VERSIONS:
            disp = self._decode_display(version)
            regions, _background_reference = tool.atlas_regions(version)
            covered = set()
            for roi in regions:
                for y in range(roi["y"], roi["y"] + roi["h"]):
                    for x in range(roi["x"], roi["x"] + roi["w"]):
                        covered.add(y * tool.WIDTH + x)
            background_codes = {
                disp[index] for index in range(len(disp)) if index not in covered
            }
            self.assertEqual(background_codes, {tool.ATLAS_BACKGROUND_CODE})

    def test_transport_fnv1a_identities_are_pinned(self) -> None:
        frame_v1 = tool.build_atlas_frame("V1")
        self.assertEqual(tool._fnv1a(frame_v1), 0x59C5EDC5)
        self.assertEqual(tool._fnv1a(tool.controller_stream(frame_v1, False)), 0x28DCCDC5)
        self.assertEqual(tool._fnv1a(tool.controller_stream(frame_v1, True)), 0xA6ADADC5)
        frame_v2 = tool.build_atlas_frame("V2")
        self.assertEqual(tool._fnv1a(frame_v2), 0x96EDCDC5)
        self.assertEqual(tool._fnv1a(tool.controller_stream(frame_v2, False)), 0x28DCCDC5)
        self.assertEqual(tool._fnv1a(tool.controller_stream(frame_v2, True)), 0xC4138DC5)


class V3SessionTests(unittest.TestCase):
    """Route A V3: normalization + probes + V2 atlas session env."""

    def test_normalize_sequence_is_pinned(self) -> None:
        seq = tool.V3_NORMALIZE_SEQUENCE
        self.assertEqual(len(seq), 8)
        self.assertEqual([s["kind"] for s in seq[:2]], ["factory_otp_white"] * 2)
        self.assertEqual(
            [(s["kind"], s["code"]) for s in seq[2:]],
            [("active_uniform", 0), ("active_uniform", 1)] * 3,
        )
        self.assertEqual(seq[-1]["code"], 1)
        contract = tool.render_v3()["src/generated/partial_atlas_1e_v3_contract.inc"]
        self.assertIn("kNormalizeStepCount = 8", contract)
        self.assertIn("FACTORY_OTP_WHITE", contract)
        self.assertIn("ACTIVE_UNIFORM", contract)

    def test_tuple_binding_byte_identity(self) -> None:
        report = tool.build_v3_report()
        self.assertEqual(report["tuples"]["active"]["r20_sha256"],
                         tool.V3_ACTIVE_R20_SHA256)
        self.assertEqual(report["tuples"]["active"]["pwr_sha256"], wmask.PWR_SHA256)
        self.assertEqual(report["tuples"]["active"]["pll_sha256"], wmask.PLL_SHA256)
        self.assertEqual(report["tuples"]["active"]["r21_sha256"], wmask.R21_SHA256)
        self.assertEqual(report["tuples"]["1E"]["r20_sha256"],
                         wmask.build_offline_variant(0x0E, True)[0]["r20_sha256"])
        self.assertFalse(report["tuples"]["factory_otp"]["runtime_lut_uploaded"])

    def test_frame_and_stream_identities(self) -> None:
        identities = tool.v3_identities()
        frames, streams = identities["frames"], identities["streams"]
        self.assertEqual(frames["black"]["sha256"],
                         "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf")
        self.assertEqual(frames["white"]["sha256"],
                         "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d")
        self.assertEqual(frames["probe7"]["sha256"],
                         "f27255891c2b00350b2f7aca6f0719116c6a29262008b7621ef4b7df66b099f2")
        # The V3 atlas action carries the exact V2 frame.
        self.assertEqual(frames["atlas_v2"]["sha256"],
                         "1bca805d48996052b748fdaaae9ac8579c2d72b241d2ed5a4836f28d181dc22b")
        self.assertEqual(frames["atlas_v2"]["fnv1a"], 0x96EDCDC5)
        self.assertEqual(streams["white"], 0xB7A855C5)
        self.assertEqual(streams["probe7"], 0x285715C5)
        self.assertEqual(streams["black"], 0xC18E7DC5)
        self.assertEqual(streams["atlas_v2_cs1"], 0x28DCCDC5)
        self.assertEqual(streams["atlas_v2_cs2"], 0xC4138DC5)

    def test_v3_driver_structure_and_tail_identity(self) -> None:
        driver = tool.render_v3()["src/partial_atlas_1e_v3_epd_driver.cpp"]
        self.assertIn(tool._r2g_tail(), driver)
        for inc in ("spd1657_legacy_535_reference.inc", "spd1657_wf_wmask_1E.inc",
                    "partial_atlas_1e_v2_layout.inc", "partial_atlas_1e_v3_contract.inc"):
            self.assertIn(f'#include "generated/{inc}"', driver)
        self.assertIn("namespace pb_profile_1e = mf1750::runtime_lut::wf_wmask_1E;", driver)
        self.assertIn("pbv3LoadRuntimeTuple", driver)
        self.assertIn("pbv3::kAtlasV2FrameFnv1a", driver)
        self.assertIn("epdDisplayCompiledFactoryOtpWhiteRecovery", driver)
        self.assertEqual(tool.build_v3_report()["runtime_tail_sha256"],
                         tool.build_report("V1")["runtime_tail_sha256"])

    def test_v3_main_endpoints_and_no_frame_ingress(self) -> None:
        main = tool.render_v3()["src/partial_atlas_1e_v3_main.cpp"]
        self.assertIn('MF1750_PARTIAL_BLOCK_ATLAS_1E_20261020_V3', main)
        for route in ("normalize", "probe-code7", "probe-code1",
                      "atlas-v2", "white-recovery"):
            with self.subTest(route=route):
                self.assertIn(f'server.on("/api/partial-atlas-v3/{route}"', main)
        self.assertIn('server.on("/api/partial-atlas-v3/steps", HTTP_GET', main)
        self.assertIn("epdGetPartialAtlasV3StepReports", main)
        self.assertNotIn('server.on("/api/frame"', main)
        self.assertNotIn("frame-ingress", main)

    def test_v3_render_deterministic_and_matches_disk(self) -> None:
        first, second = tool.render_v3(), tool.render_v3()
        self.assertEqual(first, second)
        for relative, content in first.items():
            with self.subTest(source=relative):
                path = ROOT / relative
                self.assertTrue(path.is_file())
                self.assertEqual(path.read_bytes(), content.encode("utf-8"))

    def test_v3_env_tag_and_doc_registration(self) -> None:
        platformio = (ROOT / "platformio.ini").read_text(encoding="utf-8")
        frame_tool = (ROOT / "tools/mf1750_frame_tool.py").read_text(encoding="utf-8")
        api_doc = (ROOT / "docs/MF1750_DRIVER_API.md").read_text(encoding="utf-8")
        self.assertIn(f"[env:{tool.ATLAS_ENV_V3}]", platformio)
        self.assertIn(tool.ATLAS_TAG_V3, frame_tool)
        self.assertIn(tool.ATLAS_TAG_V3, api_doc)
        self.assertIn(f'FW_BUILD_TAG = "{tool.ATLAS_TAG_V3}"',
                      tool.render_v3()["src/partial_atlas_1e_v3_main.cpp"])

    def test_v3_roi_list_is_the_v2_layout(self) -> None:
        # The V3 atlas action refreshes the V2 frame, so the measurement
        # regions are the V2 layout's regions.
        doc = tool.atlas_roi_list_doc("V2")
        self.assertEqual(
            [region["name"] for region in doc["regions"]],
            ["code0", "code1", "code2", "code3", "code4", "code5",
             "code7_probe", "code6"],
        )


class V4SessionTests(unittest.TestCase):
    """Route A V4: compact atlas in the visible camera window, no probes."""

    def test_compact_layout_matches_frozen_design(self) -> None:
        regions = tool.v4_regions()
        self.assertEqual(
            [(r["x"], r["y"], r["w"], r["h"], r["code"]) for r in regions],
            [(20, 190, 110, 110, 0), (140, 190, 110, 110, 1),
             (260, 190, 110, 110, 2), (380, 190, 110, 110, 3),
             (20, 330, 110, 110, 4), (140, 330, 110, 110, 5),
             (260, 330, 110, 110, 7), (380, 330, 110, 110, 6)],
        )
        tool._validate_v4_layout()  # raises on alignment/seam/safe-rect/overlap drift

    def test_frame_bytes_and_identity(self) -> None:
        frame = tool.build_v4_frame()
        self.assertEqual(len(frame), 307200)
        self.assertEqual(tool._sha256(frame),
                         "ee9920e61be396031f2c51c73b498a5a563e4ccfcc6b666b4b5bed7afda92efb")
        self.assertEqual(tool._fnv1a(frame), 0xA778C6A5)
        self.assertEqual(tool._fnv1a(tool.controller_stream(frame, False)), 0x746E0EA5)
        # Every cell sits on CS1's left half, so CS2's stream is pure code7.
        self.assertEqual(tool._fnv1a(tool.controller_stream(frame, True)), 0x285715C5)
        self.assertEqual(frame[0], 0x77)
        for roi in tool.v4_regions():
            with self.subTest(cell=roi["name"]):
                pair = (roi["code"] << 4) | roi["code"]
                first = roi["y"] * 512 + roi["x"] // 2
                self.assertEqual(frame[first], pair)
                last = (roi["y"] + roi["h"] - 1) * 512 + (roi["x"] + roi["w"]) // 2 - 1
                self.assertEqual(frame[last], pair)

    def test_every_cell_decodes_to_pure_intended_code(self) -> None:
        frame = tool.build_v4_frame()
        cs1 = tool.controller_stream(frame, False)
        for roi in tool.v4_regions():
            with self.subTest(cell=roi["name"]):
                seen = set()
                for y in range(roi["y"], roi["y"] + roi["h"]):
                    row = cs1[y * 256:(y + 1) * 256]
                    for bx in range(roi["x"] // 2, (roi["x"] + roi["w"]) // 2):
                        seen.add(row[bx] >> 4)
                        seen.add(row[bx] & 0x0F)
                self.assertEqual(seen, {roi["code"]})

    def test_normalize_sequence_byte_identical_to_v3(self) -> None:
        contract = tool.render_v4()["src/generated/partial_atlas_1e_v4_contract.inc"]
        v3_contract = (ROOT / "src/generated/partial_atlas_1e_v3_contract.inc").read_text(encoding="utf-8")
        for marker in ("kNormalizeStepCount = 8", "FACTORY_OTP_WHITE", "ACTIVE_UNIFORM"):
            self.assertIn(marker, contract)
        self.assertEqual(
            [(s["kind"], s["code"]) for s in tool.V3_NORMALIZE_SEQUENCE],
            [("factory_otp_white", 1)] * 2 + [("active_uniform", 0), ("active_uniform", 1)] * 3,
        )
        self.assertIn("0xC18E7DC5", contract)  # active code0 stream fnv pin
        self.assertIn("0xB7A855C5", contract)  # OTP/code1 stream fnv pin
        self.assertTrue(tool.build_v4_report()["normalize"]["byte_identical_to_v3"])

    def test_v4_driver_structure_and_tail_identity(self) -> None:
        driver = tool.render_v4()["src/partial_atlas_1e_v4_epd_driver.cpp"]
        self.assertIn(tool._r2g_tail(), driver)
        for inc in ("spd1657_legacy_535_reference.inc", "spd1657_wf_wmask_1E.inc",
                    "partial_atlas_1e_v4_contract.inc"):
            self.assertIn(f'#include "generated/{inc}"', driver)
        self.assertIn("namespace pb_profile_1e = mf1750::runtime_lut::wf_wmask_1E;", driver)
        self.assertIn("pbv4LoadRuntimeTuple", driver)
        self.assertIn("epdDisplayCompiledFactoryOtpWhiteRecovery", driver)
        # The two V3 probe actions are gone.
        self.assertNotIn("ProbeCode7", driver)
        self.assertNotIn("ProbeCode1", driver)
        self.assertEqual(tool.build_v4_report()["runtime_tail_sha256"],
                         tool.build_report("V1")["runtime_tail_sha256"])

    def test_v4_main_endpoints_and_no_probes(self) -> None:
        main = tool.render_v4()["src/partial_atlas_1e_v4_main.cpp"]
        self.assertIn('MF1750_PARTIAL_BLOCK_ATLAS_1E_20261020_V4', main)
        for route in ("normalize", "atlas-v3", "white-recovery"):
            with self.subTest(route=route):
                self.assertIn(f'server.on("/api/partial-atlas-v4/{route}"', main)
        self.assertIn('server.on("/api/partial-atlas-v4/steps", HTTP_GET', main)
        self.assertNotIn("probe-code7", main)
        self.assertNotIn("probe-code1", main)
        self.assertNotIn('server.on("/api/frame"', main)
        self.assertNotIn("frame-ingress", main)

    def test_v4_render_deterministic_and_matches_disk(self) -> None:
        first, second = tool.render_v4(), tool.render_v4()
        self.assertEqual(first, second)
        for relative, content in first.items():
            with self.subTest(source=relative):
                path = ROOT / relative
                self.assertTrue(path.is_file())
                self.assertEqual(path.read_bytes(), content.encode("utf-8"))

    def test_v4_env_tag_and_doc_registration(self) -> None:
        platformio = (ROOT / "platformio.ini").read_text(encoding="utf-8")
        frame_tool = (ROOT / "tools/mf1750_frame_tool.py").read_text(encoding="utf-8")
        api_doc = (ROOT / "docs/MF1750_DRIVER_API.md").read_text(encoding="utf-8")
        self.assertIn(f"[env:{tool.ATLAS_ENV_V4}]", platformio)
        self.assertIn(tool.ATLAS_TAG_V4, frame_tool)
        self.assertIn(tool.ATLAS_TAG_V4, api_doc)
        self.assertIn(f'FW_BUILD_TAG = "{tool.ATLAS_TAG_V4}"',
                      tool.render_v4()["src/partial_atlas_1e_v4_main.cpp"])

    def test_v4_roi_list_loads_in_multi_roi_lab(self) -> None:
        doc = tool.v4_roi_list_doc()
        self.assertEqual(doc["layout_revision"], "V3")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "layout.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            regions, _payload = roi_lab._load_layout(path)
        self.assertEqual(
            [(r["name"], r["code"]) for r in regions],
            [("code0", 0), ("code1", 1), ("code2", 2), ("code3", 3),
             ("code4", 4), ("code5", 5), ("code7", 7), ("code6", 6)],
        )


class Btst2SweepTests(unittest.TestCase):
    """BTST2[3] ladder sweep: V4 frame + parameterized phase-C byte."""

    def test_rung_table_is_pinned(self) -> None:
        self.assertEqual(tool.SWEEP_RUNG_BYTES, (0x17, 0x29, 0x39, 0x49))
        self.assertEqual(tool.SWEEP_RUNG_NAMES, ("s17", "s29", "s39", "s49"))
        self.assertEqual(tool.SWEEP_BTST2_PREFIX, (0x6F, 0x1F, 0x17))
        tool._validate_sweep()
        contract = tool.render_sweep()["src/generated/btst2_sweep_v1_contract.inc"]
        self.assertIn("kRungBytes[kRungCount] = {0x17, 0x29, 0x39, 0x49}", contract)
        self.assertIn("kBtst2Prefix[3] = {\n    0x6F, 0x1F, 0x17}", contract)
        self.assertIn("kRungNames[kRungCount] = {\"s17\", \"s29\", \"s39\", \"s49\"}", contract)

    def test_frame_identity_equals_v4(self) -> None:
        self.assertEqual(tool.build_v4_frame(), tool.build_v4_frame())
        contract = tool.render_sweep()["src/generated/btst2_sweep_v1_contract.inc"]
        identities = tool.v4_identities()
        self.assertIn(f'static constexpr char kAtlasFrameSha256[] = "{identities["frame"]["sha256"]}"', contract)
        self.assertIn(f"kAtlasFrameFnv1a = 0x{identities['frame']['fnv1a']:08X}UL", contract)
        self.assertIn(f"kAtlasCs1StreamFnv1a = 0x{identities['streams']['cs1']:08X}UL", contract)
        self.assertIn(f"kAtlasCs2StreamFnv1a = 0x{identities['streams']['cs2']:08X}UL", contract)
        self.assertEqual(identities["frame"]["sha256"],
                         "ee9920e61be396031f2c51c73b498a5a563e4ccfcc6b666b4b5bed7afda92efb")

    def test_driver_reuses_v4_layout_and_tail(self) -> None:
        driver = tool.render_sweep()["src/btst2_sweep_v1_epd_driver.cpp"]
        self.assertIn(tool._r2g_tail(), driver)
        self.assertIn('#include "generated/partial_atlas_1e_v4_contract.inc"', driver)
        self.assertIn('#include "generated/btst2_sweep_v1_contract.inc"', driver)
        self.assertIn("namespace pbv4 = mf1750::partial_block::atlas_v4;", driver)
        self.assertIn("namespace pbs = mf1750::btst2_sweep::v1;", driver)
        self.assertIn("pbv4::kAtlasFrameFnv1a == pbs::kAtlasFrameFnv1a", driver)
        self.assertNotIn("ProbeCode7", driver)
        self.assertNotIn("RunNormalize", driver)

    def test_validation_helpers_are_byte_identical_to_v4(self) -> None:
        sweep = tool.render_sweep()["src/btst2_sweep_v1_epd_driver.cpp"]
        v4 = (ROOT / "src/partial_atlas_1e_v4_epd_driver.cpp").read_text(encoding="utf-8")
        for fn in ("bool pbv4DigestMatchesHex", "bool pbv4PayloadShaMatches",
                   "bool pbv4ValidateTuples", "bool pbv4LoadRuntimeTuple"):
            with self.subTest(helper=fn):
                start_v4 = v4.index(fn)
                end_v4 = v4.index("\n}\n", start_v4) + 3
                body = v4[start_v4:end_v4]
                self.assertIn(body, sweep)

    def test_refresh_wrapper_matches_sealed_refresh_except_one_byte(self) -> None:
        tail = tool._r2g_tail()
        start = tail.index("bool epdSecondSettingAndRefresh() {")
        end = tail.index("}", tail.index("return epdPostDisplayPowerCut();", start)) + 1
        sealed = tail[start:end]
        normalized = sealed.replace(
            "bool epdSecondSettingAndRefresh() {",
            "bool pbsRefreshWithBtst2(uint8_t btst2Byte3) {",
        ).replace("epdData(0x49);", "epdData(btst2Byte3);")
        # V2 fix: the wrapper must re-select both controllers before PON (the
        # CS2 DTM stream leaves CS2-only selected), matching the sealed V4
        # pbv4RefreshFullFrame wrapper's first statement.
        expected = normalized.replace(
            "bool pbsRefreshWithBtst2(uint8_t btst2Byte3) {\n",
            "bool pbsRefreshWithBtst2(uint8_t btst2Byte3) {\n"
            "  setActiveControllers(true, true);\n",
        )
        driver = tool.render_sweep()["src/btst2_sweep_v1_epd_driver.cpp"]
        start_s = driver.index("bool pbsRefreshWithBtst2(uint8_t btst2Byte3) {")
        end_s = driver.index("}", driver.index("return epdPostDisplayPowerCut();", start_s)) + 1
        wrapper = driver[start_s:end_s]
        # The wrapper adds explanatory comment lines; strip comment lines for the compare.
        body_lines = [line for line in wrapper.splitlines() if not line.strip().startswith("//")]
        self.assertEqual("\n".join(body_lines), expected)

    def test_refresh_reselects_both_controllers_before_pon(self) -> None:
        """Pin the V2 fix: V1 sent PON/BTST2/DRF to CS2 only -> DRF timeout."""

        driver = tool.render_sweep()["src/btst2_sweep_v1_epd_driver.cpp"]
        start = driver.index("bool pbsRefreshWithBtst2(uint8_t btst2Byte3) {")
        end = driver.index("}", driver.index("return epdPostDisplayPowerCut();", start)) + 1
        body = driver[start:end]
        selection = body.index("setActiveControllers(true, true);")
        pon = body.index("epdCommand(PON);")
        self.assertLess(selection, pon)
        self.assertEqual(body.count("epdCommand(PON);"), 1)
        # The only narrowing selections allowed before the refresh are the
        # per-controller DTM streams inside the R2G tail's own helpers; the
        # rung wrapper itself must restore both controllers.
        contract = tool.render_sweep()["src/generated/btst2_sweep_v1_contract.inc"]
        self.assertIn("kFixRevision = 2", contract)

    def test_v4_refresh_wrapper_also_selects_both_controllers(self) -> None:
        v4 = (ROOT / "src/partial_atlas_1e_v4_epd_driver.cpp").read_text(encoding="utf-8")
        start = v4.index("bool pbv4RefreshFullFrame() {")
        end = v4.index("}", start + 200) + 1
        body = v4[start:end]
        self.assertLess(
            body.index("setActiveControllers(true, true);"),
            body.index("epdSecondSettingAndRefresh();"),
        )

    def test_rung_dispatch_and_endpoints(self) -> None:
        driver = tool.render_sweep()["src/btst2_sweep_v1_epd_driver.cpp"]
        main = tool.render_sweep()["src/btst2_sweep_v1_main.cpp"]
        for index, name in enumerate(tool.SWEEP_RUNG_NAMES):
            with self.subTest(rung=name):
                self.assertIn(f'server.on("/api/btst2-sweep/{name}"', main)
                self.assertIn(f"return pbsRunAtlasRung({index});", driver)
        self.assertIn("epdData(btst2Byte3);", driver)
        self.assertIn('server.on("/api/btst2-sweep/white-recovery"', main)
        self.assertIn('server.on("/api/btst2-sweep/steps", HTTP_GET', main)
        self.assertIn("epdDisplayCompiledFactoryOtpWhiteRecovery", driver)
        self.assertNotIn('server.on("/api/frame"', main)
        self.assertNotIn("frame-ingress", main)
        self.assertNotIn("normalize", main.lower().replace("btst2_sweep_white_recovery", ""))

    def test_sweep_render_deterministic_and_matches_disk(self) -> None:
        first, second = tool.render_sweep(), tool.render_sweep()
        self.assertEqual(first, second)
        for relative, content in first.items():
            with self.subTest(source=relative):
                path = ROOT / relative
                self.assertTrue(path.is_file())
                self.assertEqual(path.read_bytes(), content.encode("utf-8"))

    def test_sweep_env_tag_and_doc_registration(self) -> None:
        platformio = (ROOT / "platformio.ini").read_text(encoding="utf-8")
        frame_tool = (ROOT / "tools/mf1750_frame_tool.py").read_text(encoding="utf-8")
        api_doc = (ROOT / "docs/MF1750_DRIVER_API.md").read_text(encoding="utf-8")
        self.assertIn(f"[env:{tool.SWEEP_ENV}]", platformio)
        self.assertIn(tool.SWEEP_TAG, frame_tool)
        self.assertIn(tool.SWEEP_TAG, api_doc)
        self.assertIn(f'FW_BUILD_TAG = "{tool.SWEEP_TAG}"',
                      tool.render_sweep()["src/btst2_sweep_v1_main.cpp"])


if __name__ == "__main__":
    unittest.main()
