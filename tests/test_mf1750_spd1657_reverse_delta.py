from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = REPO_ROOT / "tools" / "mf1750_spd1657_reverse_delta.py"
SPEC = importlib.util.spec_from_file_location("spd1657_reverse_delta", TOOL_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load SPD1657 reverse-delta audit")
reverse_delta = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reverse_delta)


class Spd1657ReverseDeltaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = reverse_delta.build_report()

    def test_vendor_archive_freezes_the_extracted_evidence_tree(self) -> None:
        archive = self.report["vendor_archive"]
        self.assertEqual(
            archive["sha256"],
            "c8174a2c9082a826c7e77029da8d6bc54eee498421580badb2753eb911aa9ead",
        )
        self.assertTrue(archive["all_frozen_entries_match_extracted_tree"])
        self.assertEqual(len(archive["entries"]), 8)
        self.assertTrue(
            all(item["matches_extracted_tree"] for item in archive["entries"])
        )

    def test_800_byte_candidate_wrapper_and_plaintext_are_exact(self) -> None:
        candidate = self.report["candidate_800"]
        wrapper = candidate["wrapper"]
        self.assertEqual(wrapper["bytes"], 842)
        self.assertEqual(wrapper["ciphertext_bytes"], 800)
        self.assertEqual(wrapper["key_length_offset"], 800)
        self.assertEqual(wrapper["key_length"], 40)
        self.assertEqual(wrapper["wrapped_key_offset"], 802)
        self.assertTrue(wrapper["recovered_key_matches_supplied_source"])
        self.assertFalse(wrapper["customer_key_material_emitted"])

        mismatch = candidate["supplied_loader_mismatch"]
        self.assertEqual(mismatch["loader_ciphertext_bytes"], 544)
        self.assertEqual(mismatch["observed_key_length_at_544"], 5157)
        self.assertFalse(mismatch["observed_key_field_fits_wrapper"])
        self.assertFalse(mismatch["compatible"])

        plaintext = candidate["plaintext"]
        self.assertEqual(plaintext["bytes"], 800)
        self.assertEqual(plaintext["layout_formula"], "7 + 9 * (8 * 11) + 1")
        self.assertEqual(plaintext["category_count"], 9)
        self.assertTrue(plaintext["sentinel_is_zero"])
        self.assertFalse(plaintext["raw_plaintext_emitted"])

    def test_both_decoded_headers_have_manual_bounded_electrical_metadata(
        self,
    ) -> None:
        wf20 = self.report["candidate_800"]["electrical_request_interpretation"]
        self.assertEqual(
            wf20["requested_gate_rails_v"], {"positive": 20, "negative": -20}
        )
        self.assertEqual(
            wf20["requested_full_source_rails_v"],
            {"positive": 15, "negative": -15},
        )
        self.assertEqual(
            wf20["requested_intermediate_source_levels_v"],
            {"vsh_lv": 6.5, "vsl_lv": -8.2, "vsh_lv2": 8.0, "vsl_lv2": -8.8},
        )
        self.assertTrue(wf20["all_level_codes_in_manual_0x00_to_0x78_range"])
        self.assertTrue(wf20["all_requested_levels_within_vgh_vgl_two_volt_window"])
        self.assertFalse(wf20["decoded_raw_header_emitted"])
        self.assertEqual(wf20["requested_frame_rate_hz"], 43)
        self.assertTrue(wf20["pll_frequency_interpreted"])
        self.assertFalse(wf20["panel_batch_or_fpl_limits_proven"])
        self.assertFalse(wf20["live_approved"])
        self.assertEqual(
            wf20["manual_evidence"]["sha256"],
            "29f9c4e2e9cbd6d1aaa4622df4d2ecac8a51a205701a616a96104d03659b89d0",
        )

        wf23 = self.report["candidate_wf23_25"]["electrical_request_interpretation"]
        self.assertEqual(
            wf23["requested_intermediate_source_levels_v"],
            {"vsh_lv": 7.2, "vsl_lv": -8.4, "vsh_lv2": 8.2, "vsl_lv2": -9.8},
        )
        self.assertEqual(wf23["requested_gate_rails_v"], wf20["requested_gate_rails_v"])
        self.assertEqual(
            wf23["requested_full_source_rails_v"],
            wf20["requested_full_source_rails_v"],
        )
        self.assertEqual(wf23["requested_frame_rate_hz"], 43)
        self.assertFalse(wf23["live_approved"])

    def test_hidden_wf23_25_is_a_second_exact_profile_not_a_live_payload(
        self,
    ) -> None:
        candidate = self.report["candidate_wf23_25"]
        self.assertEqual(candidate["source_path"], "Projects/MDK-ARM/12")
        self.assertEqual(candidate["source_bytes"], 5776)
        self.assertEqual(
            candidate["source_sha256"],
            "c75d23a0f290deb8416619028284c53726bd399921a2dc0ffe043bef7f227c5d",
        )
        self.assertEqual(candidate["declared_filename"], "WF23_25.h")
        self.assertEqual(candidate["vendor_filename_numeric_tokens"], [23, 25])
        self.assertFalse(candidate["temperature_filename_semantics_proven"])
        self.assertFalse(candidate["temperature_compatibility_qualified"])

        wrapper = candidate["wrapper"]
        self.assertEqual(wrapper["bytes"], 876)
        self.assertEqual(wrapper["ciphertext_bytes"], 800)
        self.assertEqual(wrapper["key_length_offset"], 800)
        self.assertEqual(wrapper["key_length"], 74)
        self.assertEqual(wrapper["wrapped_key_offset"], 802)
        self.assertTrue(wrapper["xor_recovered_key_is_printable_ascii"])
        self.assertFalse(wrapper["customer_key_material_emitted"])

        plaintext = candidate["plaintext"]
        self.assertEqual(plaintext["bytes"], 800)
        self.assertEqual(
            plaintext["sha256"],
            "95e5fef3dc2946afdabbb35dceef1f1e48b8917d181946a82d06724c0a1c09d8",
        )
        self.assertEqual(plaintext["layout_formula"], "7 + 9 * (8 * 11) + 1")
        self.assertTrue(plaintext["sentinel_is_zero"])
        self.assertFalse(plaintext["raw_plaintext_emitted"])
        self.assertEqual(
            [item["index"] for item in candidate["categories"] if item["all_ff"]],
            [5, 8],
        )

        comparison = candidate["comparison_to_wf20_25"]
        self.assertEqual(comparison["equal_plaintext_positions"], 443)
        self.assertEqual(comparison["total_plaintext_positions"], 800)
        self.assertEqual(comparison["equal_category_indices"], [5, 8])
        self.assertTrue(comparison["same_pll_request"])
        self.assertFalse(comparison["same_power_request"])

        h3 = candidate["metadata_only_h3"]
        self.assertEqual(h3["construction"], "R20=plain[0:799], R21=FF*704")
        self.assertEqual(
            h3["r20_sha256"],
            "2eeae0e8e6a936cfd55e0a215371c114c037dbb70e701d8b95a2f560387788fb",
        )
        self.assertFalse(h3["same_build_loader_proof"])
        self.assertFalse(h3["live_eligible"])
        self.assertFalse(h3["raw_parameters_emitted"])

        linkage = candidate["build_linkage"]
        self.assertFalse(linkage["listed_in_keil_project"])
        self.assertTrue(linkage["opened_as_editor_document"])
        self.assertFalse(linkage["linked_loader_or_reachable_call_path_found"])
        classification = candidate["classification"]
        self.assertTrue(classification["second_vendor_supplied_decodable_profile"])
        self.assertFalse(classification["current_544_byte_loader_compatible"])
        self.assertFalse(classification["same_build_800_byte_loader_found"])
        self.assertFalse(classification["live_payload_approved"])

    def test_legacy_labels_prevent_an_unsafe_category_to_pixel_promotion(self) -> None:
        candidate = self.report["candidate_800"]
        inference = candidate["category_semantics_evidence"]
        self.assertEqual(
            inference["legacy_535_labels"],
            ["VCOM", "Black", "White", "Yellow", "Red", "Power"],
        )
        self.assertTrue(inference["candidate_first_535_has_same_geometry"])
        self.assertEqual(
            inference["sample_3bit_color_codes"],
            {"black": 0, "white": 1, "red": 2, "yellow": 3, "blue": 5, "green": 6},
        )
        self.assertEqual(inference["unassigned_pixel_codes"], [4, 7])
        self.assertEqual(inference["all_ff_category_indices"], [5, 8])
        self.assertTrue(inference["category_5_legacy_position_is_power"])
        self.assertTrue(
            inference["category_5_cannot_be_uniquely_promoted_to_pixel_code_4"]
        )
        self.assertTrue(inference["tail_categories_6_and_7_are_active"])
        self.assertTrue(inference["tail_category_8_is_all_ff"])
        self.assertFalse(inference["unique_category_to_pixel_code_mapping_proven"])

        categories = candidate["categories"]
        self.assertEqual(len(categories), 9)
        self.assertTrue(categories[5]["all_ff"])
        self.assertTrue(categories[8]["all_ff"])
        self.assertFalse(categories[6]["all_ff"])
        self.assertFalse(categories[7]["all_ff"])
        self.assertEqual(
            candidate["legacy_535_comparison"],
            {
                "path": "User/EDP_init.c",
                "sha256": "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b",
                "equal": False,
                "equal_byte_positions": 223,
                "total_byte_positions": 535,
            },
        )

    def test_800_byte_candidate_has_three_unresolved_mode1_views(self) -> None:
        view = self.report["candidate_800"]["register_view_inference"]
        mode0 = view["current_mode0_r20_geometry"]
        self.assertEqual(mode0["plaintext_slice"], "[0:535]")
        self.assertEqual(mode0["bytes"], 535)
        self.assertEqual(
            mode0["sha256"],
            "54a6fe90594630b58fb50a5f7903f8590eb56a2fc2ec1ccb8f084dd9c30612d1",
        )
        self.assertEqual(
            mode0["legacy_category_labels"],
            ["VCOM", "Black", "White", "Yellow", "Red", "Power"],
        )
        hypotheses = view["mode1_hypotheses"]
        h1 = hypotheses["H1_overlapping_eight_rows"]
        self.assertEqual(h1["construction"], "R20=plain[0:535], R21=plain[95:799]")
        self.assertEqual(h1["slice_offset_formula"], "7 + 88")
        self.assertEqual(h1["r21_bytes"], 704)
        self.assertEqual(
            h1["r21_sha256"],
            "050f12e9e75f1f7fe2eadf8dff9de00a6eef28e7b7e82251e38bb2fb7c8815ac",
        )
        self.assertEqual(
            h1["row_all_ff"], [False, False, False, False, True, False, False, True]
        )
        self.assertTrue(h1["row_hashes_equal_categories_1_through_8"])
        self.assertEqual(h1["overlap_with_r20_bytes"], 440)

        h2 = hypotheses["H2_extension_slots_5_to_7"]
        self.assertEqual(
            h2["construction"], "R20=plain[0:535], R21=FF*440+plain[535:799]"
        )
        self.assertEqual(h2["r21_bytes"], 704)
        self.assertEqual(
            h2["r21_sha256"],
            "27c4b947ce4bb82c7823a2bf1f637722d4b66737d17e57f16f2ed5c2dc681789",
        )
        self.assertEqual(
            h2["row_all_ff"], [True, True, True, True, True, False, False, True]
        )
        self.assertTrue(h2["tail_row_hashes_equal_categories_6_through_8"])

        h3 = hypotheses["H3_full_799_r20_ff_r21"]
        self.assertEqual(h3["construction"], "R20=plain[0:799], R21=FF*704")
        self.assertEqual(h3["r20_bytes"], 799)
        self.assertEqual(
            h3["r20_sha256"],
            "3cab2e2915205400bfdb0c2749a3e1e606cb6f190b8f3638849c532449a0ca26",
        )
        self.assertEqual(h3["r21_bytes"], 704)
        self.assertEqual(
            h3["r21_sha256"],
            "24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f",
        )
        self.assertTrue(h3["decoded_padding_byte_excluded"])
        self.assertFalse(h3["same_generation_mode1_binary_proof"])
        self.assertEqual(view["preferred_hypothesis"], "H3_full_799_r20_ff_r21")
        self.assertFalse(view["ambiguity_resolved"])
        self.assertTrue(view["mode1_source_binary_or_spi_capture_required"])
        self.assertFalse(view["direct_mode1_loader_or_relocation_proof"])
        self.assertFalse(view["live_payload_approved"])

        traces = self.report["candidate_800"]["metadata_only_spi_hypotheses"]
        self.assertEqual(traces["controllers_required"], ["CS1", "CS2"])
        self.assertTrue(traces["identical_profile_hashes_on_both_controllers_required"])
        self.assertFalse(traces["controller_transaction_order_proven"])
        self.assertEqual(
            [
                (item["command"], item["parameter_bytes"], item["parameter_sha256"])
                for item in traces["common_header_transactions"]
            ],
            [
                (
                    "0x01",
                    6,
                    "44a59eb14f6766b6f7de20019ee9739c7ab262c02e6b5e4a48f22e87c289b917",
                ),
                (
                    "0x30",
                    1,
                    "dbc1b4c900ffe48d575b5da5c638040125f65db0fe3e24494b76ea986457d986",
                ),
            ],
        )
        self.assertFalse(traces["H1_overlapping_eight_rows"]["live_eligible"])
        self.assertFalse(traces["H2_extension_slots_5_to_7"]["live_eligible"])
        h3_trace = traces["H3_full_799_r20_ff_r21"]
        self.assertEqual(
            [
                (item["command"], item["parameter_bytes"], item["parameter_sha256"])
                for item in h3_trace["lut_transactions"]
            ],
            [
                (
                    "0x20",
                    799,
                    "3cab2e2915205400bfdb0c2749a3e1e606cb6f190b8f3638849c532449a0ca26",
                ),
                (
                    "0x21",
                    704,
                    "24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f",
                ),
            ],
        )
        self.assertFalse(h3_trace["live_eligible"])
        self.assertFalse(traces["raw_parameters_emitted"])

    def test_legacy_iar_object_adds_h3_side_evidence_without_live_promotion(
        self,
    ) -> None:
        iar = self.report["legacy_iar_e2802"]
        self.assertEqual(iar["bytes"], 328_062)
        self.assertEqual(
            iar["sha256"],
            "19fb74c05444880ea6a403d697307e47a874998b5529ee84dd0592ecae16c9ce",
        )
        self.assertEqual(iar["data0"]["bytes"], 1503)
        self.assertEqual(iar["data0"]["layout_formula"], "7 + 17 * 88")
        self.assertEqual(iar["data0"]["active_88_byte_blocks"], list(range(6)))
        self.assertEqual(iar["data0"]["all_ff_88_byte_blocks"], list(range(6, 17)))
        self.assertEqual(iar["data1"]["bytes"], 704)
        self.assertEqual(iar["data1"]["layout_formula"], "8 * 88")
        self.assertEqual(
            [row["non_ff_bytes"] for row in iar["data1"]["rows"]],
            [53, 59, 66, 52, 54, 0, 0, 0],
        )
        self.assertFalse(iar["data1"]["referenced_by_active_upload_path"])
        sequence = iar["reverse_engineered_runtime_sequence"]
        self.assertEqual(
            [
                (item["command"], item["parameter_bytes"])
                for item in sequence["transactions"]
            ],
            [("0x20", 799), ("0x21", 704)],
        )
        self.assertTrue(sequence["data1_constant_is_not_the_active_r21_source"])
        self.assertTrue(sequence["machine_signature_binding_reproduced_by_this_tool"])
        self.assertEqual(len(sequence["unique_ubrof_machine_signatures"]), 7)
        self.assertEqual(
            sequence["dataBuff_plus_4_source_anchor_file_offset"], "0x17F60"
        )
        self.assertFalse(sequence["can_uniquely_prove_current_mode1_contract"])
        self.assertFalse(
            iar["limits"]["safe_live_artifact_derivable_from_this_object_alone"]
        )

    def test_library_debug_contract_exposes_the_missing_selector_glue(self) -> None:
        library = self.report["library"]
        compile_contract = library["compile_contract"]
        self.assertTrue(compile_contract["wf_decode_size_544"])
        self.assertTrue(compile_contract["wf_size_535"])
        self.assertTrue(compile_contract["e5_3bit_mode_0"])
        self.assertTrue(compile_contract["compiled_header_path_present"])
        self.assertTrue(compile_contract["all_selector_macros_present_in_debug"])
        self.assertTrue(compile_contract["spi_chip_select_symbol_present_in_debug"])
        self.assertEqual(compile_contract["selector_macros"]["MAS_SLA"], "0x10")

        gap = library["delivered_header_version_gap"]
        self.assertFalse(gap["mas_sla_declared"])
        self.assertFalse(gap["spi_chip_select_declared"])
        self.assertTrue(gap["sample_main_assigns_mas_sla"])
        self.assertFalse(gap["compiled_and_delivered_headers_are_contract_compatible"])

        glue = library["delivered_writeepd_glue"]
        self.assertFalse(glue["references_spi_chip_select"])
        self.assertFalse(glue["uses_both_writer"])
        self.assertTrue(glue["uses_legacy_generic_writer"])
        self.assertFalse(glue["honors_sample_main_mas_sla_assignment"])

    def test_unique_704_byte_ff_candidate_is_frozen_without_guessing_semantics(
        self,
    ) -> None:
        lut1 = self.report["library"]["lut1_candidate"]
        self.assertEqual(lut1["member_offset_hex"], "0x1B54")
        self.assertEqual(lut1["archive_offset_hex"], "0x1CF6")
        self.assertEqual(lut1["bytes"], 704)
        self.assertEqual(
            lut1["sha256"],
            "24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f",
        )
        self.assertTrue(lut1["all_ff"])
        self.assertTrue(lut1["only_long_ff_run_in_object"])
        self.assertTrue(lut1["public_lut1_data_symbol_present"])
        self.assertTrue(lut1["formal_relocation_binding_proven_by_this_tool"])
        self.assertFalse(lut1["ff_semantics_known"])

    def test_crof_relocations_and_dwarf_formally_bind_mode0_r21(self) -> None:
        library = self.report["library"]
        formal = library["formal_loader_bindings"]
        header = formal["orc_header"]
        self.assertEqual(header["section_header_offset"], 0xD240)
        self.assertEqual(header["section_header_entry_bytes"], 40)
        self.assertEqual(header["section_count"], 271)

        relocations = formal["relocation_section"]
        self.assertEqual(relocations["name"], ".reli.loadWF")
        self.assertEqual(relocations["data_member_offset"], 0xAB4C)
        self.assertEqual(relocations["bytes"], 0x68)
        self.assertTrue(relocations["unique_signature_match"])
        self.assertEqual(len(relocations["entries"]), 13)
        self.assertEqual(
            [entry["offset"] for entry in relocations["entries"][-7:]],
            [0x88, 0x8C, 0x90, 0x94, 0x98, 0x9C, 0xA0],
        )
        self.assertEqual(relocations["entries"][-1]["symbol_index"], 0xC4)
        self.assertEqual(relocations["entries"][-1]["symbol_name"], "LUT1_DATA")

        arrays = formal["dwarf"]["array_types"]
        self.assertEqual(arrays["in"]["bytes"], 544)
        self.assertEqual(arrays["pwr_d"]["bytes"], 6)
        self.assertEqual(arrays["pll_d"]["bytes"], 1)
        self.assertEqual(arrays["LUT1_DATA"]["type_die_offset"], 0x2A9)
        self.assertEqual(arrays["LUT1_DATA"]["upper_bound"], 703)
        self.assertEqual(arrays["LUT1_DATA"]["bytes"], 704)

        binding = formal["fourth_write_binding"]
        self.assertEqual(binding["command"], "0x21")
        self.assertEqual(binding["parameter_bytes"], 704)
        self.assertEqual(binding["literal_relocation_offset"], 0xA0)
        self.assertEqual(binding["literal_symbol_index"], 0xC4)
        self.assertTrue(binding["formal_binding_proven"])
        self.assertTrue(binding["source_is_independent_symbol_not_in_plus_95"])

        counterevidence = library["current_mode0_counterevidence"]
        self.assertFalse(counterevidence["mode_branch_present"])
        self.assertFalse(counterevidence["r21_source_is_decoded_in_plus_95"])
        self.assertFalse(
            counterevidence["candidate_mode1_register_view_used_by_this_build"]
        )

    def test_cascade_schematic_proves_a_jumperable_not_a_fixed_broadcast(self) -> None:
        schematic = self.report["cascade_schematic"]
        self.assertEqual(schematic["pages"], 1)
        self.assertTrue(schematic["all_topology_tokens_present"])
        topology = schematic["topology_evidence"]
        self.assertTrue(topology["external_8pin_j1_exposes_one_cs"])
        self.assertTrue(topology["controller_symbol_has_csb_and_sl_csb"])
        self.assertTrue(topology["j4_places_cs_and_sl_csb_on_a_two_pin_header"])
        self.assertTrue(topology["j4_is_jumperable_bridge"])
        self.assertFalse(topology["physical_jumper_population_or_state_proven"])

    def test_dormant_nootp_source_is_not_promoted_to_a_live_initialization(
        self,
    ) -> None:
        paths = self.report["initialization_paths"]
        nootp = paths["dormant_nootp_path"]
        self.assertTrue(nootp["definition_is_never_called_in_delivered_user_main"])
        self.assertEqual(nootp["geometry_source_by_gate"], [428, 428])
        self.assertEqual(
            nootp["reads_wrapper_ciphertext_indices_as_register_values"],
            [1, 2, 3, 4, 6],
        )
        self.assertFalse(nootp["uses_decoded_plaintext_header"])
        self.assertTrue(nootp["psr_0x0f_0x89"])
        self.assertTrue(nootp["e9_0x01"])
        self.assertTrue(nootp["uses_generic_writer"])
        self.assertFalse(nootp["uses_both_writer"])
        self.assertFalse(nootp["matches_current_dual_controller_runtime_contract"])

        factory = paths["factory_init_path"]
        self.assertTrue(factory["calls_reset"])
        self.assertTrue(factory["uses_both_writer"])
        self.assertTrue(factory["psr_0x5f_0x69"])
        self.assertTrue(factory["tres_512x600"])
        self.assertFalse(factory["formal_runtime_to_factory_otp_recovery_proven"])

    def test_supplied_otp_blob_is_not_promoted_to_a_runtime_lut_or_read_from_hardware(
        self,
    ) -> None:
        otp = self.report["otp_payload"]
        self.assertEqual(otp["bytes"], 1152)
        self.assertTrue(otp["three_384_byte_program_blocks"])
        self.assertFalse(otp["contains_candidate_800"])
        self.assertFalse(otp["contains_candidate_first_535"])
        self.assertEqual(otp["exact_11_byte_candidate_group_matches"], 0)
        self.assertFalse(otp["hardware_otp_read"])
        self.assertFalse(otp["otp_programming_attempted"])

    def test_cli_emits_metadata_only_and_keeps_runtime_hard_blocked(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(TOOL_PATH)],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["kind"], reverse_delta.KIND)
        self.assertEqual(report["schema_version"], reverse_delta.SCHEMA_VERSION)
        self.assertFalse(report["runtime_profile_ready"])
        self.assertFalse(report["visible_runtime_test_authorized"])
        self.assertEqual(len(report["blockers"]), 8)
        self.assertEqual(
            report["first_live_test_target"][
                "vendor_filename_numeric_tokens_by_profile"
            ],
            {"WF20_25": [20, 25], "WF23_25": [23, 25]},
        )
        self.assertFalse(
            report["first_live_test_target"]["temperature_filename_semantics_proven"]
        )
        self.assertFalse(
            report["first_live_test_target"]["temperature_compatibility_qualified"]
        )
        self.assertEqual(
            report["first_live_test_target"]["experimental_fixed_temperature_guard_c"],
            [25.0, 25.0],
        )
        self.assertFalse(
            report["first_live_test_target"]["vendor_temperature_band_claim"]
        )
        self.assertEqual(
            report["first_live_test_target"]["candidate_profile_ids"],
            ["WF20_25", "WF23_25"],
        )
        self.assertFalse(report["first_live_test_target"]["profile_priority_resolved"])
        self.assertFalse(report["first_live_test_target"]["materialized"])
        self.assertFalse(report["first_live_test_target"]["authorized"])
        self.assertTrue(report["safety"]["offline_read_only"])
        self.assertFalse(report["safety"]["hardware_accessed"])
        self.assertFalse(report["safety"]["serial_accessed"])
        self.assertFalse(report["safety"]["device_network_accessed"])
        self.assertEqual(report["safety"]["vendor_profiles_decrypted_in_memory"], 2)
        self.assertFalse(report["safety"]["live_payload_generated"])
        self.assertNotIn("0f5445f92132b6ef57466f274d3b6b2d47d79356", completed.stdout)
        self.assertNotIn("00 23 34 32 3a 14 02", completed.stdout.lower())


if __name__ == "__main__":
    unittest.main()
