from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tools import mf1750_spd1657_record_semantics_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CANONICAL_SHA256 = (
    "12954f599d9c76a8c0d87dbe3270e1b39e206aceb64dce740333fb3647350316"
)


class Mf1750Spd1657RecordSemanticsAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report()

    def test_two_complete_source_tables_have_direct_group_labels(self) -> None:
        source = self.report["source_label_contract"]
        self.assertEqual(source["source"]["source_bytes"], 32_220)
        self.assertEqual(
            source["source"]["source_sha256"],
            "1b6bbcf35cefc338f7ab9b76c04c869f9a82e800c4ccaa52d204d9fd6e53b7a5",
        )
        expected = {
            "commented": {
                "table_sha256": "2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26",
                "source_region": (
                    13,
                    61,
                    49,
                    3_572,
                    "52e61dd31132de3537223945ca44469e8846a56f02406fbcff2be311b80e378f",
                ),
                "record_lines": (14, 61),
                "source_form": "commented_out_complete_table_byte_lines",
            },
            "active": {
                "table_sha256": "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b",
                "source_region": (
                    63,
                    111,
                    49,
                    3_470,
                    "8ae0bd939759cd243b90587efd40a7486382774e8c0f4c7242d6ebf4281530b8",
                ),
                "record_lines": (64, 111),
                "source_form": "active_initializer_byte_lines",
            },
        }
        for table_id, exact in expected.items():
            table = source["tables"][table_id]
            reconstructed = table["reconstructed_table"]
            region = table["source_region"]
            self.assertEqual(reconstructed["bytes"], 535)
            self.assertEqual(reconstructed["sha256"], exact["table_sha256"])
            self.assertFalse(reconstructed["raw_bytes_emitted"])
            self.assertEqual(
                (
                    region["start_line_number"],
                    region["end_line_number"],
                    region["line_count"],
                    region["bytes"],
                    region["sha256"],
                ),
                exact["source_region"],
            )
            self.assertFalse(region["raw_source_text_emitted"])
            self.assertEqual(table["header_line_number"], region["start_line_number"])
            self.assertEqual(
                (
                    table["first_labeled_line_number"],
                    table["last_labeled_line_number"],
                ),
                exact["record_lines"],
            )
            self.assertEqual(table["source_form"], exact["source_form"])
            self.assertEqual(table["header_bytes"], 7)
            self.assertEqual(table["record_bytes"], 11)
            self.assertEqual(table["record_count"], 48)
            self.assertEqual(table["category_count"], 6)
            self.assertEqual(table["records_per_category"], 8)
            self.assertEqual(
                table["category_labels"],
                ["VCOM", "Black", "White", "Yellow", "Red", "Power"],
            )
            self.assertTrue(table["all_48_record_boundaries_directly_labeled_inline"])
            self.assertFalse(table["raw_header_record_or_payload_bytes_emitted"])

        gain = source["direct_semantic_gain"]
        self.assertFalse(gain["eleven_byte_boundaries_are_only_arithmetic"])
        self.assertTrue(gain["every_legacy_record_is_directly_named_as_a_GROUP_slot"])
        self.assertFalse(
            gain["group_slot_is_a_chronological_phase_proven_by_local_source"]
        )
        self.assertFalse(gain["any_of_the_eleven_bytes_is_named_by_local_source"])

    def test_only_active_table_is_compiled_and_linked(self) -> None:
        status = self.report["compiled_and_linked_status"]
        self.assertEqual(status["object"]["bytes"], 1_283_980)
        self.assertEqual(
            status["object"]["sha256"],
            "6854348d4b2dd797974d5d0c00fe806cf519a9a12271f54a9e4e81be864dac76",
        )
        self.assertEqual(status["object"]["active_full_table_occurrence_count"], 1)
        self.assertEqual(status["object"]["commented_full_table_occurrence_count"], 0)
        binding = status["object"]["wf_data_elf32_symbol_binding"]
        self.assertEqual(
            binding,
            {
                "symbol_table_section_index": 665,
                "symbol_table_section_name": ".symtab",
                "symbol_index": 562,
                "binding": 1,
                "type": 1,
                "other": 2,
                "section_index": 67,
                "section_name": ".data",
                "section_relative_value": 7,
                "symbol_bytes": 535,
                "symbol_file_offset": 311_021,
                "symbol_payload_sha256": (
                    "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b"
                ),
                "raw_symbol_payload_emitted": False,
            },
        )
        self.assertEqual(status["link_map"]["bytes"], 257_903)
        self.assertEqual(
            status["link_map"]["wf_data_535_edp_init_data_symbol_row_count"], 1
        )
        self.assertTrue(
            status["active_table_bound_to_wf_data_symbol_in_edp_init_object"]
        )
        self.assertFalse(
            status["commented_exact_full_table_present_in_edp_init_object"]
        )
        self.assertTrue(status["active_wf_data_535_linked_by_delivered_map"])
        self.assertTrue(
            status["active_wf_data_symbol_content_compiled_and_linked_by_delivered_map"]
        )
        self.assertFalse(
            status["commented_source_lines_active_in_this_translation_unit"]
        )
        self.assertFalse(status["commented_table_role_proven"])
        self.assertFalse(status["commented_table_runtime_authorized"])
        self.assertEqual(
            status["commented_table_safe_operational_status"],
            "inactive_source_bytes_role_unknown_unvalidated_comparison_only",
        )

    def test_elf_symbol_binding_rejects_symbol_drift_despite_raw_occurrence(
        self,
    ) -> None:
        source = audit._parse_source_tables()
        active = source["payloads"]["active"]
        object_payload = audit.LEGACY_OBJECT.read_bytes()
        file_offset = self.report["compiled_and_linked_status"]["object"][
            "wf_data_elf32_symbol_binding"
        ]["symbol_file_offset"]
        mutated = bytearray(object_payload)
        mutated[file_offset] ^= 0x01
        mutated.extend(active)
        self.assertEqual(bytes(mutated).count(active), 1)
        with self.assertRaisesRegex(
            audit.RecordSemanticsAuditError,
            "wf_data bytes differ",
        ):
            audit._bind_elf32_symbol(
                bytes(mutated),
                symbol_name="wf_data",
                expected_section=".data",
                expected_size=535,
                expected_payload=active,
            )

    def test_commented_and_active_tables_share_labels_not_record_contents(self) -> None:
        comparison = self.report["commented_vs_active_same_source_comparison"]
        self.assertTrue(comparison["same_source_same_direct_label_geometry"])
        self.assertEqual(comparison["equal_byte_positions"], 146)
        self.assertEqual(comparison["different_byte_positions"], 389)
        self.assertEqual(comparison["equal_header_position_indices"], [0, 2, 5])
        self.assertEqual(comparison["different_header_position_indices"], [1, 3, 4, 6])
        self.assertEqual(comparison["same_coordinate_exact_record_count"], 0)
        self.assertEqual(comparison["shared_unique_non_all_ff_record_count"], 0)
        self.assertEqual(
            comparison["content_relation_class"],
            "same_direct_labels_but_distinct_contents_no_shared_active_record",
        )
        self.assertFalse(comparison["one_is_a_simple_duplicate_of_the_other"])
        self.assertFalse(
            comparison["difference_assigns_duration_voltage_or_phase_fields"]
        )
        self.assertFalse(comparison["commented_table_role_proven"])
        self.assertFalse(
            comparison["commented_table_is_an_authorized_runtime_candidate"]
        )
        provenance = self.report["datasets"]["legacy_commented_535"]["provenance"]
        self.assertFalse(provenance["source_lines_active_in_this_translation_unit"])
        self.assertFalse(
            provenance["exact_full_table_present_in_current_edp_init_object"]
        )
        self.assertEqual(provenance["role"], "unknown")
        self.assertFalse(provenance["runtime_authorized"])
        adjudication = self.report["adjudication"]
        self.assertTrue(adjudication["commented_legacy_source_lines_are_inactive"])
        self.assertFalse(adjudication["commented_legacy_table_role_proven"])
        self.assertFalse(
            adjudication["commented_legacy_table_is_an_authorized_runtime_candidate"]
        )
        for category in comparison["categories"]:
            self.assertEqual(
                category["equal_byte_positions"] + category["different_byte_positions"],
                88,
            )
            self.assertEqual(category["same_coordinate_exact_record_indices"], [])

        for row in self.report["commented_table_cross_dataset_exact_record_screen"]:
            self.assertEqual(row["shared_unique_non_all_ff_record_count"], 0)
            self.assertFalse(row["raw_records_emitted"])
            self.assertFalse(row["exact_match_would_assign_semantics"])

    def test_comment_link_and_static_consumption_evidence_are_separate(self) -> None:
        ladder = self.report["legacy_evidence_ladder"]
        self.assertIn(
            "source author naming", ladder["level_1_comment_labels"]["establishes"]
        )
        linked = ladder["level_2_compiled_and_linked_active_bytes"]
        self.assertTrue(linked["active_bytes_bound_to_wf_data_elf_symbol"])
        self.assertTrue(
            linked["commented_exact_full_table_absent_from_edp_init_object"]
        )
        self.assertTrue(linked["wf_data_535_symbol_present_in_link_map"])
        execution = ladder["level_3_delivered_c_consumption"]
        self.assertTrue(execution["all_535_bytes_forwarded_in_order_to_command_0x20"])
        self.assertTrue(execution["header_bytes_1_through_4_also_bind_to_PWR_0x01"])
        self.assertTrue(execution["header_byte_0_has_only_opaque_0x20_forwarding"])
        self.assertTrue(
            execution[
                "header_byte_5_has_only_opaque_0x20_forwarding_after_no_named_field_use"
            ]
        )
        self.assertTrue(
            execution[
                "header_byte_6_has_only_opaque_0x20_forwarding_after_no_named_field_use"
            ]
        )
        self.assertFalse(execution["hardware_runtime_observed"])

    def test_header_dataflow_does_not_promote_comment_names(self) -> None:
        binding = self.report["legacy_header_execution_binding"]
        self.assertEqual(binding["source_corpus"]["file_count"], 21)
        self.assertEqual(binding["source_corpus"]["bytes"], 1_965_112)
        self.assertEqual(
            binding["source_corpus"]["canonical_manifest_sha256"],
            "c0df8659bc16bf37f3ef0739131a2791efd2c149f1c2a2a0eb91074c321df2ed",
        )
        coordinates = binding["header_coordinates"]
        self.assertEqual([row["index"] for row in coordinates], list(range(7)))
        self.assertEqual(
            [row["direct_scalar_read_in_delivered_c_sources"] for row in coordinates],
            [False, True, True, True, True, True, True],
        )
        self.assertEqual(
            [row["dedicated_command_binding"] for row in coordinates],
            ["none_proven"]
            + ["PWR_0x01_via_EPD_setting_V1_to_V4"] * 4
            + ["none_proven", "none_proven"],
        )
        self.assertTrue(
            all(
                row["forwarded_opaquely_as_member_of_command_0x20_payload"]
                for row in coordinates
            )
        )
        self.assertTrue(binding["bytes_1_through_4_have_direct_PWR_execution_binding"])
        self.assertFalse(binding["byte_0_VGHL_has_direct_scalar_execution_binding"])
        self.assertEqual(binding["byte_5_assignment_count_in_source_corpus"], 2)
        self.assertFalse(
            binding["byte_5_struct_field_has_named_non_assignment_use_in_source_corpus"]
        )
        self.assertTrue(
            binding["dedicated_VCOM_command_0x82_uses_separate_global_vcom"]
        )
        self.assertFalse(binding["byte_5_has_dedicated_VCOM_execution_binding"])
        self.assertEqual(binding["byte_6_assignment_count_in_source_corpus"], 2)
        self.assertEqual(
            binding["byte_6_assigned_to_struct_field"], "EPD_setting.Frame"
        )
        self.assertFalse(binding["byte_6_comment_and_struct_field_names_agree"])
        self.assertFalse(
            binding["byte_6_struct_field_has_named_non_assignment_use_in_source_corpus"]
        )
        self.assertTrue(binding["dedicated_PLL_command_0x30_uses_literal_not_byte_6"])
        self.assertFalse(binding["byte_6_has_dedicated_PLL_execution_binding"])
        self.assertTrue(
            binding[
                "command_0x20_immediately_followed_by_exact_i0_to_i534_wf_data_loop"
            ]
        )
        loop_comment = binding["upload_loop_source_comment"]
        self.assertEqual(loop_comment["line_number"], 1228)
        self.assertEqual(
            loop_comment["normalized_comment"],
            "循环次数根据不同的芯片规格有所不同",
        )
        self.assertEqual(
            loop_comment["normalized_comment_utf8_sha256"],
            audit.LEGACY_UPLOAD_LOOP_COMMENT_UTF8_SHA256,
        )
        self.assertEqual(loop_comment["attached_loop_iteration_count"], 535)
        self.assertTrue(
            loop_comment[
                "establishes_535_is_not_asserted_as_universal_across_all_chips"
            ]
        )
        self.assertFalse(loop_comment["establishes_mode1_uses_799_or_800_bytes"])
        self.assertFalse(loop_comment["establishes_dual_controller_destination"])

    def test_linked_uart_path_blocks_runtime_initializer_promotion(self) -> None:
        binding = self.report["legacy_header_execution_binding"]
        mutation = binding["mutable_wf_data_runtime_replacement"]
        self.assertEqual(
            mutation["UartDataDeal_source"],
            {
                "path": ("参考资料/REG-API-oqc(1)(1)/REG-API-oqc/User/UartDataDeal.c"),
                "bytes": 5_047,
                "sha256": (
                    "da853aa6f02c2ec3da271d3bc6dc23c50467b3b6af4e5d8b113dc18304e5d897"
                ),
            },
        )
        self.assertEqual(
            mutation["usart_source"],
            {
                "path": (
                    "参考资料/REG-API-oqc(1)(1)/REG-API-oqc/Drivers/SYSTEM/usart/usart.c"
                ),
                "bytes": 6_008,
                "sha256": (
                    "dd3fcf761175113a73740d4b30de40e7c87dfe4500ef0f4c297cb47fda5be460"
                ),
            },
        )
        self.assertTrue(
            mutation["case_5_calls_Uart_save_wf_data_from_USART1_RData_plus_6"]
        )
        self.assertTrue(
            mutation["Uart_save_wf_data_clears_whole_global_then_copies_WF_DATA_LENGTH"]
        )
        self.assertEqual(mutation["WF_DATA_LENGTH"], 535)
        self.assertFalse(
            mutation["declared_buff_len_parameter_consumed_in_function_body"]
        )
        self.assertEqual(
            mutation["link_map_reference_chain_counts"],
            {
                "startup_vector_to_USART1_IRQHandler": 1,
                "USART1_IRQHandler_to_receive_analyse": 1,
                "receive_analyse_to_Uart_save_wf_data": 1,
                "Uart_save_wf_data_to_wf_data": 1,
            },
        )
        self.assertTrue(mutation["linked_interrupt_to_mutable_wf_data_path_exists"])
        self.assertTrue(
            mutation["path_requires_a_matching_runtime_UART_case_5_request"]
        )
        self.assertFalse(mutation["path_itself_calls_EPD_initial_or_command_0x20"])
        self.assertFalse(
            mutation[
                "compiled_initializer_contents_remain_unmodified_at_each_0x20_upload_proven"
            ]
        )
        self.assertFalse(
            mutation["runtime_bytes_at_each_upload_are_the_compiled_initializer_proven"]
        )
        self.assertFalse(binding["all_pre_call_mutations_of_wf_data_excluded"])
        active = self.report["datasets"]["legacy_active_535"]["provenance"]
        self.assertTrue(active["mutable_global_with_linked_UART_replacement_path"])
        self.assertFalse(
            active["initializer_contents_are_runtime_upload_bytes_at_every_call_proven"]
        )
        ladder = self.report["legacy_evidence_ladder"]
        self.assertFalse(
            ladder["level_3_delivered_c_consumption"][
                "compiled_initializer_is_the_runtime_upload_content_proven"
            ]
        )

    def test_upload_loop_comment_rejects_detached_or_changed_source(self) -> None:
        source = audit.LEGACY_SOURCE.read_bytes()
        text = source.decode("gb18030")
        self.assertEqual(
            audit._source_upload_loop_comment(source)["line_number"],
            audit.LEGACY_UPLOAD_LOOP_COMMENT_LINE,
        )
        detached = text.replace(
            "for(i=0;i<535;i++)                               //循环次数",
            "for(i=0;i<534;i++)                               //循环次数",
            1,
        ).encode("gb18030")
        with self.assertRaisesRegex(
            audit.RecordSemanticsAuditError,
            "exact 535-byte loop header",
        ):
            audit._source_upload_loop_comment(detached)

        def replace_line(lines: list[str], line_number: int, content: str) -> None:
            original = lines[line_number - 1]
            ending = (
                "\r\n"
                if original.endswith("\r\n")
                else "\n"
                if original.endswith("\n")
                else ""
            )
            lines[line_number - 1] = content + ending

        decoy_lines = text.splitlines(keepends=True)
        replace_line(decoy_lines, 1208, "\tEPD_WriteCMD(0x20);")
        replace_line(decoy_lines, 1209, "\tfor(i=0;i<535;i++)")
        replace_line(decoy_lines, 1210, "\tEPD_WriteDATA(wf_data[i]);")
        replace_line(
            decoy_lines, audit.LEGACY_UPLOAD_COMMAND_LINE, "\tEPD_WriteCMD(0x21);"
        )
        decoy_text = "".join(decoy_lines)
        decoy_epd_initial = audit.geometry.reverse_delta._extract_function(
            audit._strip_comments(decoy_text), "EPD_initial"
        )
        self.assertIsNotNone(
            audit.LEGACY_SEQUENTIAL_UPLOAD_PATTERN.search(decoy_epd_initial),
            "the decoy must exercise a detached positive sequence in EPD_initial",
        )
        with self.assertRaisesRegex(
            audit.RecordSemanticsAuditError,
            "not immediately preceded by command 0x20",
        ):
            audit._source_upload_loop_comment(decoy_text.encode("gb18030"))

        wrong_function_lines = text.splitlines(keepends=True)
        replace_line(
            wrong_function_lines,
            audit.LEGACY_EPD_INITIAL_DEFINITION_LINE,
            "void Not_EPD_initial(void)",
        )
        with self.assertRaisesRegex(
            audit.RecordSemanticsAuditError,
            "EPD_initial definition line changed",
        ):
            audit._source_upload_loop_comment(
                "".join(wrong_function_lines).encode("gb18030")
            )

        truncated = "".join(text.splitlines(keepends=True)[:1228]).encode("gb18030")
        with self.assertRaisesRegex(
            audit.RecordSemanticsAuditError,
            "truncated before EPD_initial closes",
        ):
            audit._source_upload_loop_comment(truncated)

    def test_dataset_geometry_sparsity_and_literal_projection_are_exact(self) -> None:
        expected = {
            "legacy_commented_535": (48, 48, 0, 7, 22),
            "legacy_active_535": (48, 40, 8, 1, 24),
            "iar_DATA0_first799": (72, 28, 44, 5, 19),
            "iar_DATA1_704": (64, 35, 29, 5, 23),
            "WF20_25": (72, 38, 34, 1, 22),
            "WF23_25": (72, 50, 22, 1, 20),
        }
        for dataset_id, exact in expected.items():
            dataset = self.report["datasets"][dataset_id]
            geometry = dataset["geometry"]
            complement = dataset["active_low_sparsity_screen"][
                "bitwise_complement_one_bit_weight"
            ]
            self.assertEqual(
                (
                    geometry["record_count"],
                    geometry["non_all_ff_record_count"],
                    geometry["all_ff_record_count"],
                    complement["minimum"],
                    complement["maximum"],
                ),
                exact,
            )
            screen = dataset["active_low_sparsity_screen"]
            self.assertTrue(
                screen["all_active_records_have_at_most_24_set_bits_after_complement"]
            )
            self.assertFalse(
                screen["controller_internal_complement_or_active_low_encoding_proven"]
            )
            projection = dataset["philips_11byte_projection"]
            self.assertGreater(
                projection["raw_first_eight_bytes_two_bit_code_counts"]["3"],
                0,
            )
            self.assertGreater(
                projection["complemented_first_eight_bytes_two_bit_code_counts"]["3"],
                0,
            )
            self.assertFalse(
                projection[
                    "one_transform_satisfies_literal_three_level_example_and_FF_FF_boundary"
                ]
            )
            self.assertFalse(
                projection["bytes_0_through_7_are_voltage_selectors_proven"]
            )
            self.assertFalse(projection["bytes_8_through_10_are_timing_fields_proven"])

    def test_data0_data1_and_public_analogies_remain_bounded(self) -> None:
        provenance = self.report["iar_provenance"]
        self.assertTrue(provenance["arrays_are_byte_identical_across_E2801_and_E2802"])
        self.assertTrue(provenance["DATA0_and_DATA1_are_adjacent_UBROF_sections"])
        self.assertFalse(
            provenance["adjacency_proves_a_logical_pair_or_category_mapping"]
        )

        public = self.report["public_format_hypotheses"]
        philips = public["philips_apollo_11byte"]
        self.assertTrue(philips["exact_width_match"])
        self.assertFalse(philips["local_format_or_controller_identity_match_proven"])
        self.assertFalse(
            philips["literal_raw_or_complement_projection_decodes_all_local_records"]
        )
        eink = public["eink_compact_segment_example"]
        self.assertEqual(
            eink["source"]["facts_canonical_sha256"],
            audit.EINK_COMPACT_PATENT_FACTS_SHA256,
        )
        self.assertFalse(eink["patent_defines_an_11byte_group_record"])
        self.assertFalse(
            eink["local_two_bit_voltage_or_four_bit_duration_field_assigned"]
        )
        adjacent = public["good_display_adjacent_eight_group_contract"]
        self.assertTrue(adjacent["same_eight_group_count_as_local_legacy_labels"])
        self.assertFalse(
            adjacent["therefore_local_11byte_record_contains_no_timing_field"]
        )
        manual = public["spd1656_manual"]
        self.assertEqual(manual["bytes"], 2_339_387)
        self.assertTrue(manual["strict_geometry_conflict_for_color_parser"])
        self.assertFalse(manual["direct_vcom_record_parser_transfer_proven"])
        self.assertFalse(manual["direct_color_record_parser_transfer_proven"])
        self.assertFalse(public["network_accessed_by_this_offline_tool"])

    def test_build_never_enters_profile_render_or_write_paths(self) -> None:
        with (
            mock.patch.object(
                audit.profile_pack,
                "render_include",
                side_effect=AssertionError("render path must remain unreachable"),
            ),
            mock.patch.object(
                audit.profile_pack,
                "write_include",
                side_effect=AssertionError("write path must remain unreachable"),
            ),
        ):
            report = audit.build_report()
        self.assertFalse(
            report["material_handling"]["profile_pack_render_or_write_path_called"]
        )

    def test_report_is_deterministic_metadata_only_and_cli_is_exclusive(self) -> None:
        self.assertEqual(self.report["kind"], audit.KIND)
        self.assertEqual(self.report["schema_version"], 3)
        self.assertEqual(
            self.report["integrity"]["canonical_sha256"],
            EXPECTED_CANONICAL_SHA256,
        )

        def assert_no_binary(value: object) -> None:
            self.assertNotIsInstance(value, (bytes, bytearray))
            if isinstance(value, dict):
                for child in value.values():
                    assert_no_binary(child)
            elif isinstance(value, list):
                for child in value:
                    assert_no_binary(child)

        assert_no_binary(self.report)
        handling = self.report["material_handling"]
        self.assertFalse(handling["raw_key_plaintext_waveform_or_record_bytes_emitted"])
        self.assertFalse(handling["raw_key_plaintext_waveform_or_record_bytes_written"])
        self.assertFalse(handling["runtime_payload_include_or_firmware_generated"])
        safety = self.report["safety"]
        self.assertTrue(safety["offline_only"])
        for key, value in safety.items():
            if key != "offline_only":
                self.assertFalse(value, key)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "record-semantics.json"
            command = [
                sys.executable,
                "-m",
                "tools.mf1750_spd1657_record_semantics_audit",
                "--output",
                str(output),
                "--compact",
            ]
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                timeout=120,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr.decode())
            self.assertEqual(completed.stdout, b"")
            parsed = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                parsed["integrity"]["canonical_sha256"],
                EXPECTED_CANONICAL_SHA256,
            )
            repeated = subprocess.run(
                command,
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                timeout=120,
            )
            self.assertEqual(repeated.returncode, 2)
            self.assertIn(b"refusing overwrite", repeated.stderr)


if __name__ == "__main__":
    unittest.main()
