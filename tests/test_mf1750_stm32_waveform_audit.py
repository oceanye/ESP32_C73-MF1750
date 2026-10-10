from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

from tools import mf1750_stm32_waveform_audit as waveform_audit


REPO_ROOT = Path(__file__).resolve().parents[1]


class STM32WaveformReferenceAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not waveform_audit.DEFAULT_REFERENCE_ROOT.is_dir():
            raise unittest.SkipTest("STM32 REG-API-oqc reference tree is not present")
        cls.report = waveform_audit.audit()

    def test_active_wf_data_has_exact_535_value_six_category_layout(self) -> None:
        wf_data = self.report["wf_data"]
        self.assertEqual(wf_data["declared_size"], 535)
        self.assertEqual(wf_data["actual_value_count"], 535)
        self.assertEqual(
            wf_data["initializer_sha256"],
            "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b",
        )
        self.assertEqual(wf_data["layout"]["expected_total"], 7 + 6 * 8 * 11)
        self.assertEqual(
            wf_data["categories"],
            ["VCOM", "Black", "White", "Yellow", "Red", "Power"],
        )
        self.assertTrue(wf_data["only_expected_categories"])
        self.assertTrue(wf_data["layout_valid"])
        self.assertEqual(
            wf_data["write_path"],
            {
                "master_cs_symbol": "E_Paper_CS",
                "slave_cs_symbol_present": False,
                "master_only": True,
            },
        )
        application = wf_data["application_contract"]
        self.assertTrue(all(application["header_fields_loaded"].values()))
        self.assertTrue(application["power_fields_v1_to_v4_applied"])
        self.assertFalse(application["header_vcom_applied"])
        self.assertFalse(application["header_frame_applied"])
        self.assertTrue(application["vcom_uses_separate_global"])
        self.assertTrue(application["pll_frame_is_hard_coded"])
        self.assertTrue(application["header_runtime_mismatch"])
        self.assertTrue(application["tres_uses_full_1024x600_macros"])
        self.assertFalse(application["cascade_config_present"])
        self.assertTrue(application["master_only_full_panel_geometry_mismatch"])
        self.assertFalse(application["busy_wait_timeout_present"])
        self.assertTrue(application["unbounded_busy_wait"])
        self.assertEqual(
            wf_data["uart_update_contract"],
            {
                "path": "User/UartDataDeal.c",
                "fixed_535_copy": True,
                "provided_length_checked": False,
                "unsafe_length_contract": True,
            },
        )
        for category in wf_data["categories"]:
            self.assertEqual(wf_data["group_numbers"][category], list(range(1, 9)))

    def test_packaged_waveform_is_842_byte_e5_2bit_input(self) -> None:
        packaged = self.report["packaged_waveform"]
        self.assertEqual(packaged["declared_size"], 842)
        self.assertEqual(packaged["actual_value_count"], 842)
        self.assertEqual(packaged["banner"], "E5 2-bit Development Environment")
        self.assertTrue(packaged["is_e5_2bit"])
        self.assertTrue(packaged["size_valid"])
        self.assertEqual(
            packaged["initializer_sha256"],
            "97efcac1cbc6604a52b942a00b13df349530e152fd28063ed9eda94a36e2dcc5",
        )
        loader = packaged["loader_abi"]
        self.assertEqual(loader["fixed_ciphertext_bytes"], 544)
        self.assertEqual(loader["key_length_offset"], 544)
        self.assertEqual(loader["observed_key_length"], 5157)
        self.assertFalse(loader["key_field_fits_wrapper"])
        self.assertFalse(loader["compatible_with_supplied_loader"])
        candidate = packaged["different_candidate_layout"]
        self.assertEqual(candidate["ciphertext_bytes"], 800)
        self.assertEqual(candidate["key_length"], 40)
        self.assertTrue(candidate["recovered_key_matches_source"])
        self.assertEqual(
            candidate["classification"],
            (
                "self-consistent 800+2+40 candidate layout incompatible with "
                "supplied 544-byte loader"
            ),
        )
        self.assertFalse(candidate["matching_loader_supplied"])
        self.assertFalse(candidate["authoritative_abi_proven"])
        self.assertFalse(candidate["valid_waveform_proven"])
        self.assertFalse(candidate["relative_age_inferred"])
        self.assertEqual(
            packaged["sample_main_required_waveform"],
            {"include": "WF00_05.h", "present": False},
        )
        self.assertFalse(packaged["customer_key_metadata"]["raw_value_emitted"])
        self.assertFalse(packaged["raw_values_emitted"])

    def test_library_is_ar_with_expected_member_and_contract_markers(self) -> None:
        library = self.report["library"]
        self.assertTrue(library["is_ar_archive"])
        self.assertEqual(library["format"], "unix-ar")
        self.assertEqual(
            [(member["name"], member["kind"]) for member in library["members"]],
            [
                ("/", "symbol_table"),
                ("//", "string_table"),
                ("eload_20250305b1.o", "object"),
            ],
        )
        self.assertTrue(library["all_required_markers_present"])
        self.assertTrue(all(library["markers"].values()))
        self.assertEqual(library["decoded_waveform_size"], 544)
        self.assertEqual(library["lut_waveform_size"], 535)
        self.assertEqual(library["e5_3bit_mode_macro_value"], 0)
        self.assertFalse(library["e5_3bit_mode_zero_semantics_known"])
        reverse = library["reverse_contract"]
        self.assertTrue(reverse["exact_binary_identity"])
        self.assertEqual(reverse["object"]["magic_hex"], "f74f5243")
        self.assertEqual(reverse["object"]["archive_data_offset_hex"], "0x1A2")
        self.assertEqual(reverse["code_stream"]["archive_offset_hex"], "0x1DE")
        self.assertEqual(reverse["loadwf"]["actual_return_type"], "uint8_t")
        self.assertEqual(reverse["loadwf"]["archive_offset_hex"], "0x692")
        self.assertEqual(reverse["loadwf"]["bytes"], 0x88)
        self.assertEqual(
            [(item["command"], item["bytes"]) for item in reverse["loadwf"]["success_writes"]],
            [("0x01", 6), ("0x30", 1), ("0x20", 535), ("0x21", 704)],
        )
        self.assertFalse(reverse["loadwf"]["controller_or_cs_argument"])
        self.assertFalse(reverse["loadwf"]["refresh_sequence_present"])
        self.assertEqual(reverse["decrypt_check"]["archive_offset_hex"], "0x134A")
        self.assertEqual(reverse["decrypt_check"]["bytes"], 0xCC)
        self.assertEqual(reverse["decrypt_check"]["fixed_ciphertext_bytes"], 544)
        self.assertFalse(reverse["decrypt_check"]["wrapped_key_bounds_check_present"])
        self.assertEqual(reverse["lut1_data"]["write_bytes"], 704)
        self.assertFalse(reverse["lut1_data"]["phase_or_color_semantics_proven"])
        self.assertFalse(library["waveform_decrypted"])
        self.assertFalse(library["customer_key_material_emitted"])

    def test_lcd_project_and_link_map_evidence_is_reported(self) -> None:
        self.assertEqual((self.report["lcd"]["width"], self.report["lcd"]["height"]), (1024, 600))
        self.assertTrue(self.report["lcd"]["is_1024x600"])
        self.assertTrue(self.report["project"]["all_required_inputs_listed"])
        self.assertEqual(
            self.report["project"]["includes"],
            {"e28xx_source": True, "edp_init_source": True, "waveform_library": True},
        )

        link_map = self.report["link_map"]
        self.assertTrue(link_map["epd_initial_nootp_removed"])
        self.assertTrue(link_map["main_constdata_842_removed"])
        self.assertEqual(link_map["epd_initial_provider"], "e28xx.o")
        self.assertTrue(link_map["epd_initial_from_e28xx"])
        self.assertFalse(link_map["encrypted_loadwf_linked"])
        self.assertTrue(link_map["plain_2bit_runtime_lut_linked"])
        self.assertTrue(link_map["proves_encrypted_loadwf_path_absent"])

    def test_uart_control_plane_does_not_prove_ble_brightness_or_contrast(self) -> None:
        control = self.report["uart_control_plane"]
        transport = control["supplied_transport_evidence"]
        self.assertTrue(transport["uart1_protocol_present"])
        self.assertFalse(transport["bluetooth_or_ble_stack_present"])
        self.assertFalse(transport["gatt_contract_present"])
        self.assertFalse(transport["wireless_app_artifact_present"])
        self.assertFalse(transport["bluetooth_to_uart_bridge_proven"])
        self.assertTrue(transport["only_uart_side_of_possible_bridge_is_supplied"])

        uart = control["physical_uart"]
        self.assertEqual(uart["instance"], "USART1")
        self.assertEqual(uart["tx_pin"], "PA9")
        self.assertEqual(uart["rx_pin"], "PA10")
        self.assertEqual(uart["baud"], 115200)
        self.assertEqual(uart["data_bits"], 8)
        self.assertEqual(uart["stop_bits"], 1)
        self.assertEqual(uart["parity"], "none")
        self.assertEqual(uart["hardware_flow_control"], "none")
        self.assertTrue(uart["rx_dma_and_idle_irq"])

        frame = control["frame"]
        self.assertEqual(frame["header_hex"], "41 41")
        self.assertEqual(frame["command_type_offset"], 4)
        self.assertEqual(frame["payload_offset"], 6)
        self.assertEqual(frame["terminator_hex"], "0D")
        self.assertTrue(frame["validated_by_source"])

        commands = control["commands"]
        self.assertTrue(commands["5"]["calls_uart_save_wf_data"])
        self.assertEqual(commands["5"]["downstream_fixed_copy_bytes"], 535)
        self.assertTrue(commands["5"]["downstream_fixed_copy_present"])
        self.assertFalse(commands["5"]["downstream_checks_supplied_length"])
        self.assertTrue(commands["7"]["sets_get_vcom_dispatch"])
        self.assertTrue(commands["7"]["later_calls_get_vcom"])
        self.assertEqual(commands["7"]["controller_read_register"], "0x81")
        self.assertTrue(commands["8"]["updates_global_vcom"])
        self.assertFalse(commands["8"]["range_or_unit_validation_present"])
        self.assertTrue(commands["8"]["main_branch_ack_only"])
        self.assertFalse(commands["8"]["direct_controller_write_in_set_branch"])
        self.assertTrue(commands["8"]["commented_epd_setting_assignment_present"])

        semantics = control["application_semantics"]
        self.assertTrue(semantics["legacy_initial_later_writes_vcom_or_0x80"])
        self.assertTrue(semantics["legacy_initial_is_master_only"])
        self.assertFalse(semantics["all_display_paths_reinitialize_legacy_path"])
        self.assertFalse(semantics["direct_brightness_command_present"])
        self.assertFalse(semantics["direct_contrast_command_present"])
        self.assertFalse(semantics["waveform_upload_brightness_or_contrast_semantics_proven"])
        self.assertFalse(semantics["raw_vcom_is_approved_brightness_control"])
        self.assertFalse(semantics["contrast_mapping_proven"])

    def test_source_contract_and_color_mapping_conflicts_block_compatibility(self) -> None:
        loadwf = self.report["loadwf_contract"]
        self.assertEqual(loadwf["header_return_type"], "void")
        self.assertEqual(loadwf["caller_result_type"], "unsigned char")
        self.assertEqual(loadwf["assigned_call_count"], 2)
        self.assertTrue(loadwf["return_type_conflict"])
        self.assertEqual(loadwf["binary_actual_return_type"], "uint8_t")
        self.assertTrue(loadwf["binary_proves_header_wrong"])
        self.assertFalse(loadwf["sample_main_is_project_entry"])
        self.assertTrue(loadwf["user_main_is_project_entry"])
        self.assertTrue(loadwf["sample_main_selector_symbols_missing"])
        dual = loadwf["dual_controller"]
        self.assertFalse(dual["handled_inside_loadwf"])
        self.assertTrue(dual["writeepd_uses_generic_path"])
        self.assertTrue(dual["legacy_path_master_only"])
        self.assertTrue(dual["separate_dual_target_apis_exist"])
        self.assertFalse(dual["selector_assignment_proves_broadcast"])
        self.assertFalse(dual["verified_dual_controller_load"])

        colors = self.report["color_codes"]
        self.assertEqual(
            colors["user_2bit"],
            {"black": 0, "white": 1, "yellow": 2, "red": 3},
        )
        self.assertEqual(
            colors["user_2bit_packed_bytes"],
            {"black": "0x00", "white": "0x55", "red": "0xFF", "yellow": "0xAA"},
        )
        self.assertEqual(
            colors["user_single_color_function_bytes"],
            {"black": "0x00", "white": "0x11", "yellow": "0xAA", "red": "0xFF"},
        )
        self.assertTrue(colors["user_single_color_fill_conflict"])
        self.assertEqual(
            colors["sample_3bit"],
            {"black": 0, "white": 1, "red": 2, "yellow": 3, "blue": 5, "green": 6},
        )
        self.assertEqual(colors["esp32"]["yellow"], 2)
        self.assertEqual(colors["esp32"]["red"], 3)
        self.assertTrue(colors["internal_conflict"])
        self.assertTrue(colors["esp32_matches_user_2bit"])
        self.assertFalse(colors["esp32_matches_sample_3bit"])

        self.assertTrue(self.report["artifact_age"]["source_is_newer"])
        self.assertFalse(self.report["compatibility_ready"])
        blocker_codes = {item["code"] for item in self.report["compatibility_blockers"]}
        self.assertEqual(
            blocker_codes,
            {
                "bit_depth_contract_mismatch",
                "active_lut_has_no_blue_or_green_category",
                "encrypted_3bit_loadwf_not_linked",
                "linked_plain_2bit_path_is_master_only",
                "plaintext_lut_header_fields_not_applied",
                "plaintext_lut_full_panel_master_geometry_mismatch",
                "uart_lut_copy_ignores_length",
                "bluetooth_brightness_contrast_mapping_unproven",
                "plaintext_lut_busy_wait_has_no_timeout",
                "loadwf_return_contract_conflict",
                "packaged_waveform_loader_abi_mismatch",
                "sample_main_required_waveform_missing",
                "runtime_loadwf_master_only_glue",
                "reference_internal_color_code_conflict",
                "reference_2bit_fill_literal_conflict",
                "link_artifact_older_than_source",
                "panel_waveform_compatibility_unproven",
                "e6_reference_not_target_and_sequence_inconsistent",
            },
        )

    def test_e6_sample_is_scoped_and_its_v1_2_demo_inconsistency_is_explicit(self) -> None:
        e6 = self.report["e6_sample"]
        self.assertTrue(e6["present"])
        self.assertEqual(e6["file_count"], 66)
        self.assertEqual((e6["geometry"]["width"], e6["geometry"]["height"]), (800, 480))
        self.assertTrue(e6["geometry"]["is_800x480"])
        self.assertEqual(e6["pixel_format"]["bits_per_pixel"], 4)
        self.assertTrue(e6["pixel_format"]["all_six_payloads_consistent"])
        self.assertEqual(e6["colors"]["red"]["packed_byte"], "0x33")
        self.assertEqual(e6["colors"]["yellow"]["packed_byte"], "0x22")
        self.assertTrue(e6["single_display_tail"]["all_six_functions_cut_vdd"])
        self.assertEqual(e6["main_sequence"]["initialization_calls"], 1)
        self.assertEqual(e6["main_sequence"]["display_calls"], 7)
        self.assertFalse(e6["main_sequence"]["repower_after_first_display"])
        self.assertFalse(e6["main_sequence"]["reinitialize_after_first_display"])
        self.assertTrue(e6["main_sequence"]["v1_2_sequential_demo_internally_inconsistent"])
        self.assertTrue(e6["dual_reset_comment_means_two_reset_pulses"])
        self.assertTrue(e6["single_cs_only"])
        self.assertFalse(e6["source_level_runtime_lut_api_found"])
        self.assertFalse(e6["source_level_brightness_api_found"])
        self.assertFalse(e6["usable_as_target_lut_or_electrical_authority"])

        crosscheck = self.report["vendor_sample_crosscheck"]
        self.assertTrue(crosscheck["red_yellow_codes_conflict_across_samples"])
        self.assertFalse(crosscheck["cross_sample_register_or_color_transplant_allowed"])

    def test_cli_emits_json_metadata_only_and_performs_no_io_side_effects(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools/mf1750_stm32_waveform_audit.py")],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["kind"], waveform_audit.KIND)
        self.assertEqual(report["schema_version"], waveform_audit.SCHEMA_VERSION)
        self.assertFalse(report["compatibility_ready"])
        self.assertEqual(
            report["safety"],
            {
                "scope": "this formal audit invocation only",
                "offline_read_only": True,
                "hardware_accessed": False,
                "serial_accessed": False,
                "network_accessed": False,
                "waveform_decrypted": False,
                "accepted_loader_plaintext_decrypted": False,
                "separate_reverse_evidence_candidate_decrypt_in_memory": True,
                "customer_key_material_emitted": False,
                "otp_payload_read": False,
                "raw_waveform_values_emitted": False,
                "live_payload_generated": False,
            },
        )
        self.assertNotIn("iniKey", completed.stdout)
        self.assertNotIn("OTP_DATA", completed.stdout)


if __name__ == "__main__":
    unittest.main()
