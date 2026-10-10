from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = REPO_ROOT / "tools" / "good_display_esp32e6_cross_image_panel_audit.py"
SPEC = importlib.util.spec_from_file_location("good_display_cross_image", TOOL_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load cross-image audit")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class GoodDisplayCrossImagePanelAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report()

    def test_all_disassembly_views_match_the_pinned_app_segments(self) -> None:
        self.assertEqual(set(self.report["images"]), set(audit.IMAGE_SPECS))
        for image in self.report["images"].values():
            view = image["synthetic_disassembly_view"]
            self.assertTrue(view["derived_view_matches_pinned_app_segments"])
            self.assertGreaterEqual(len(view["segments"]), 5)

    def test_init_and_command_data_helpers_are_common_across_three_apps(self) -> None:
        finding = self.report["cross_image_findings"]
        self.assertTrue(finding["common_init_present_in_all_three_apps"])
        self.assertEqual(
            finding["common_init_normalized_sha256"],
            audit.EXPECTED_INIT_NORMALIZED_SHA256,
        )
        traces = []
        for image in self.report["images"].values():
            traces.append(image["typed_init_trace"])
            helpers = image["normalized_common_code"]["command_data_helpers"]
            self.assertEqual(
                helpers["command"]["normalized_disassembly_sha256"],
                audit.EXPECTED_COMMAND_NORMALIZED_SHA256,
            )
            self.assertEqual(
                helpers["data"]["normalized_disassembly_sha256"],
                audit.EXPECTED_DATA_NORMALIZED_SHA256,
            )
            self.assertEqual(helpers["command"]["trace"][1], "dc_low:gpio3")
            self.assertEqual(helpers["data"]["trace"][1], "dc_high:gpio3")
        self.assertEqual(traces[0], traces[1])
        self.assertEqual(traces[1], traces[2])
        self.assertIn({"command": "0x61", "data_hex": "032001e0"}, traces[0])

    def test_packing_and_six_tag_mapping_are_recovered(self) -> None:
        finding = self.report["cross_image_findings"]
        self.assertTrue(finding["panel_image_packing_recovered"])
        self.assertEqual(finding["packed_frame_bytes"], 192_000)
        self.assertEqual(finding["unpacked_tag_frame_bytes"], 384_000)
        self.assertEqual(
            finding["unpacked_tag_to_panel_code"],
            {"0": 0, "29": 5, "76": 3, "150": 6, "226": 2, "255": 1},
        )
        for name in ("GDEP073E01wifi.bin", "usb.bin"):
            packer = self.report["images"][name]["unpacked_pixel_packer"]
            self.assertEqual(packer["first_pixel_position"], "high_nibble")
            self.assertEqual(packer["second_pixel_position"], "low_nibble")
        for name in ("GDEP073E01wifi.bin", "SD.bin"):
            packed = self.report["images"][name]["packed_display"]
            self.assertEqual(
                packed["normalized_disassembly_sha256"],
                audit.EXPECTED_PACKED_DISPLAY_NORMALIZED_SHA256,
            )

    def test_sd_card_spi_is_not_the_sd_panel_transport(self) -> None:
        finding = self.report["cross_image_findings"]
        self.assertTrue(finding["sd_card_spi_and_panel_transport_are_distinct"])
        self.assertEqual(
            finding["sd_card_spi"]["pins"],
            {"sck": 21, "miso": 13, "mosi": 47, "ss": 48},
        )
        self.assertEqual(
            finding["sd_panel_transport"],
            {"backend": "gpio_bitbang_msb_first", "clock_gpio": 12, "data_gpio": 11},
        )
        caller = self.report["images"]["SD.bin"]["caller_chain"]
        self.assertEqual(caller["bmp_success_string_xref"], "0x42002b3d")
        self.assertEqual(caller["init_call"], "0x42002caf")
        self.assertEqual(caller["packed_display_call"], "0x42002cb7")

    def test_runtime_waveform_conclusion_remains_bounded_negative(self) -> None:
        boundary = self.report["runtime_waveform_boundary"]
        self.assertFalse(boundary["typed_command_0x20_recovered"])
        self.assertFalse(boundary["typed_command_0x21_recovered"])
        self.assertFalse(boundary["runtime_lut_length_704_recovered"])
        self.assertFalse(boundary["runtime_lut_length_2508_recovered"])
        self.assertFalse(boundary["runtime_waveform_abi_recovered"])
        self.assertIn("recovered typed", boundary["bounded_scope"])
        self.assertFalse(self.report["live_payload_generated"])
        self.assertFalse(self.report["live_test_authorized"])
        self.assertTrue(self.report["safety"]["offline_static_analysis_only"])

    def test_cli_help_is_ascii_safe(self) -> None:
        result = subprocess.run(
            [sys.executable, str(TOOL_PATH), "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="ascii",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("offline", result.stdout)


if __name__ == "__main__":
    unittest.main()
