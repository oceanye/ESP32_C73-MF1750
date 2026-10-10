from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = REPO_ROOT / "tools" / "good_display_esp32e6_firmware_audit.py"
SPEC = importlib.util.spec_from_file_location("good_display_firmware_audit", TOOL_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load Good Display firmware audit")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class GoodDisplayEsp32E6FirmwareAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report()

    def test_official_zip_and_three_flash_images_are_identity_pinned(self) -> None:
        bundle = self.report["vendor_zip"]
        self.assertEqual(bundle["bytes"], 1_156_950)
        self.assertEqual(
            bundle["sha256"],
            "8eaff3e3a68da354c6ad1fc62a1d6b6ee2144df64198ab35a544e5a96f868a96",
        )
        self.assertTrue(bundle["identity_match"])
        self.assertTrue(bundle["crc_all_entries_valid"])
        self.assertEqual(
            {item["basename"] for item in bundle["entries"]},
            {"GDEP073E01wifi.bin", "SD.bin", "usb.bin"},
        )
        self.assertEqual(
            self.report["images"]["GDEP073E01wifi.bin"]["sha256"],
            "df8959b99304d3b6d0b7e560cc4db03a5edb9ffe28640f7428d662285b548508",
        )
        self.assertEqual(
            self.report["images"]["SD.bin"]["sha256"],
            "86d9da5e0200ccbf0a5ef7a90a1b89bc06b554d591a3a24cdb99d2648672dcf5",
        )
        self.assertEqual(
            self.report["images"]["usb.bin"]["sha256"],
            "f21bd62bd2171e4fa30c527847b60313dba746cc16eb44a3ecba9e178551cdad",
        )

    def test_partition_and_esp_application_containers_validate(self) -> None:
        expected = {
            "GDEP073E01wifi.bin": ("0x40379d54", "16MB", 6, "Mar 31 2026"),
            "SD.bin": ("0x40375d78", "4MB", 6, "Jul 22 2025"),
            "usb.bin": ("0x403766d8", "4MB", 5, "Jan  6 2025"),
        }
        for name, (entry, flash_size, segments, compile_date) in expected.items():
            image = self.report["images"][name]
            self.assertEqual(
                image["partition_table"]["md5"], audit.EXPECTED_PARTITION_MD5
            )
            self.assertTrue(image["partition_table"]["md5_valid"])
            self.assertTrue(image["partition_table"]["identical_expected_layout"])
            app = image["app"]
            self.assertEqual(app["chip"], "ESP32-S3")
            self.assertEqual(app["entry_address"], entry)
            self.assertEqual(app["flash_size"], flash_size)
            self.assertEqual(app["segment_count"], segments)
            self.assertTrue(app["checksum_valid"])
            self.assertTrue(app["validation_sha256_valid"])
            self.assertEqual(
                app["application_description"]["compile_date"], compile_date
            )

    def test_raw_hits_are_not_promoted_to_runtime_lut_evidence(self) -> None:
        for image in self.report["images"].values():
            literals = image["business_literals"]
            self.assertTrue(literals["all_controller_runtime_profile_terms_absent"])
            for term in (
                "SPD1657",
                "SPD1656",
                "ED2208",
                "WF20_25",
                "WF23_25",
                "waveform",
                "LUT_token",
                "0x20",
                "0x21",
            ):
                self.assertEqual(literals["occurrences"][term], [])
            patterns = image["raw_patterns"]
            self.assertEqual(patterns["known_local_e6_init_prefix"]["count"], 0)
            self.assertGreater(patterns["adjacent_0x20_0x21"]["count"], 0)
            self.assertEqual(
                patterns["adjacent_0x20_0x21"]["classification"],
                "raw_untyped_byte_pattern_only",
            )
            self.assertFalse(
                patterns["adjacent_0x20_0x21"]["instruction_or_panel_semantics_proven"]
            )
            self.assertEqual(patterns["799_le32"]["count"], 0)

    def test_wifi_contrast_is_browser_code_and_dithering_is_direct_evidence(
        self,
    ) -> None:
        host = self.report["images"]["GDEP073E01wifi.bin"]["embedded_host_ui"]
        self.assertTrue(host["title_present"])
        self.assertTrue(host["real_palette_literal"])
        self.assertTrue(host["driver_palette_literal"])
        self.assertTrue(all(host["dither_algorithms"].values()))
        self.assertEqual(host["adjust_contrast_occurrence_count"], 1)
        self.assertTrue(host["adjust_contrast_definition_only"])
        self.assertFalse(host["brightness_literal_present"])
        self.assertEqual(
            host["classification"], "embedded_browser_image_preprocessing_javascript"
        )
        self.assertFalse(host["panel_brightness_or_contrast_register_proven"])

    def test_sd_pixel_codes_and_sd_card_spi_path_are_bounded(self) -> None:
        sd = self.report["images"]["SD.bin"]
        colors = sd["sd_pixel_codes"]
        self.assertTrue(colors["all_six_driver_codes_present"])
        self.assertEqual(
            colors["driver_color_codes"],
            {"black": 0, "white": 1, "yellow": 2, "red": 3, "blue": 5, "green": 6},
        )
        instruction = sd["instruction_level"]
        spi_refs = instruction["custom_string_paths"]["spi_initialization"][
            "l32r_candidates"
        ]
        self.assertIn("0x420024e2", {item["virtual_address"] for item in spi_refs})
        scan_refs = instruction["custom_string_paths"]["scan_images"]["l32r_candidates"]
        self.assertIn("0x4200235e", {item["virtual_address"] for item in scan_refs})
        anchors = instruction["verified_raw_instruction_anchors"]
        self.assertTrue(all(item["identity_match"] for item in anchors.values()))
        bounded = instruction["bounded_interpretation"]
        self.assertTrue(bounded["custom_sd_spi_setup_path_supported"])
        self.assertTrue(bounded["this_is_sd_card_spi_not_panel_lut_transport"])
        self.assertFalse(bounded["panel_spi_call_graph_recovered"])
        self.assertFalse(bounded["controller_command_0x20_or_0x21_proven"])

    def test_conclusion_is_negative_for_live_runtime_lut_and_hardware(self) -> None:
        finding = self.report["cross_image_findings"]
        self.assertTrue(finding["controller_runtime_profile_literals_absent"])
        self.assertTrue(finding["host_dither_pipeline_recovered"])
        self.assertTrue(finding["sd_six_color_pixel_code_mapping_recovered"])
        self.assertFalse(finding["spd1657_or_ed2208_abi_recovered"])
        self.assertFalse(finding["runtime_lut_payload_recovered"])
        self.assertFalse(finding["dual_panel_controller_delivery_recovered"])
        self.assertFalse(self.report["live_payload_generated"])
        self.assertFalse(self.report["live_test_authorized"])
        safety = self.report["safety"]
        self.assertTrue(safety["offline_static_analysis_only"])
        self.assertFalse(safety["hardware_accessed"])
        self.assertFalse(safety["serial_or_com_accessed"])
        self.assertFalse(safety["device_network_accessed"])

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
