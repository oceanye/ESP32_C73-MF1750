from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools import e2801_r43_lut_proof as e2801
from tools import e2802_r43_lut_proof as e2802


REPO_ROOT = Path(__file__).resolve().parents[1]


class E2801R43LutProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = e2801.prove_object()

    def test_identity_and_scope_are_pinned_and_offline(self) -> None:
        report = self.report
        self.assertEqual(report["kind"], e2801.KIND)
        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["object"]["size_bytes"], 315_632)
        self.assertEqual(
            report["object"]["sha256"],
            "404b950ea65b754a335b90be24683281ebee9dab52e362fd6d49170b4b8a38a3",
        )
        self.assertEqual(report["object"]["UBROF_version_byte"], 10)
        safety = report["safety"]
        self.assertTrue(safety["offline_read_only"])
        self.assertFalse(safety["hardware_accessed"])
        self.assertFalse(safety["serial_or_COM_accessed"])
        self.assertFalse(safety["device_network_accessed"])
        self.assertFalse(safety["firmware_written_or_flashed"])
        self.assertFalse(safety["visible_refresh_requested"])
        self.assertFalse(safety["raw_LUT_or_waveform_emitted"])

    def test_function_sections_and_2508_byte_read_are_exact(self) -> None:
        sections = self.report["function_sections"]
        self.assertEqual(sections["EPD_Init"]["section_id"], "0x2E")
        self.assertEqual(sections["EPD_Load_LUT"]["section_id"], "0x1D")
        self.assertEqual(sections["Upload_Temperature_LUT"]["section_id"], "0x1E")
        bulk = self.report["upload_temperature_lut"]["preload"]["bulk_read"]
        preload = self.report["upload_temperature_lut"]["preload"]
        self.assertEqual(
            preload["ReadData_ABI"]["argument_order"],
            ["address", "destination", "count"],
        )
        self.assertEqual(
            preload["ReadData_ABI"]["register_assignment"],
            {
                "address": "R12:R13 (copied from R7:R6)",
                "destination": "R14",
                "count": "R15",
            },
        )
        self.assertEqual(
            [
                (
                    call["source_line"],
                    call["operation"],
                    call["count"],
                    call["paired_CALLA_record_file_offset"],
                )
                for call in preload["observed_ReadData_calls"]
            ],
            [
                (509, "ReadData(address, stack_destination, 2)", 2, "0x1C9E0"),
                (
                    518,
                    "ReadData(selected_address, dataBuff, 2508)",
                    2_508,
                    "0x1D378",
                ),
            ],
        )
        self.assertEqual(
            bulk["operation"], "ReadData(selected_address, dataBuff, 2508)"
        )
        self.assertEqual(bulk["count_hex"], "0x09CC")
        self.assertEqual(bulk["count_bytes"], 2_508)
        self.assertEqual(bulk["destination"]["backing_section_extent_bytes"], 2_560)
        self.assertFalse(bulk["destination"]["symbol_capacity_bytes_proven"])
        self.assertNotIn("capacity_bytes", bulk["destination"])
        self.assertEqual(bulk["reader_relocation_classification"], "external-index")
        self.assertEqual(bulk["reader_external_symbol_index"], "0x03")
        self.assertEqual(
            bulk["reader_name_evidence"],
            {
                "paired_debug_source_symbol": "ReadData",
                "namespace_1_name_index": 3,
                "namespace_1_name_record_file_offset": "0x2483",
            },
        )
        self.assertFalse(bulk["reader_external_index_is_local_section_id"])
        self.assertFalse(bulk["reader_definition_present_in_this_object"])
        self.assertNotIn("reader_target_section_id", bulk)
        self.assertFalse(bulk["physical_transport_proven"])
        read_data_edges = [
            row
            for row in self.report["upload_temperature_lut"][
                "source_annotated_named_direct_CALLA_inventory"
            ]
            if row["symbol"] == "ReadData"
        ]
        self.assertEqual(
            [
                (
                    row["record_file_offset"],
                    row["source_line"],
                    row["relocation_operator"],
                    row["target_id"],
                    row["relocation_classification"],
                )
                for row in read_data_edges
            ],
            [
                ("0x1C9E0", 509, "0x5D", "0x03", "external-index"),
                ("0x1D378", 518, "0x5D", "0x03", "external-index"),
            ],
        )

    def test_upload_geometry_and_psr_placement_are_exact(self) -> None:
        upload = self.report["upload_temperature_lut"]
        self.assertEqual(
            upload["preload"]["temperature_sequence"],
            ["SPI_COMMAND(0x40)", "check_busy_high", "SPI_GET_DATA"],
        )
        self.assertEqual(
            upload["command_enum_anchors"],
            {
                "PSR": {
                    "value": "0x00",
                    "file_offset": "0x2113",
                    "evidence": "identity-pinned embedded enum record",
                },
                "LUT0": {
                    "value": "0x20",
                    "file_offset": "0x2194",
                    "evidence": "identity-pinned embedded enum record",
                },
                "LUT1": {
                    "value": "0x21",
                    "file_offset": "0x21A0",
                    "evidence": "identity-pinned embedded enum record",
                },
                "TSC": {
                    "value": "0x40",
                    "file_offset": "0x21B7",
                    "evidence": "identity-pinned embedded enum record",
                },
            },
        )
        self.assertEqual(
            upload["preload"]["temperature_command_name_from_embedded_enum"],
            "TSC",
        )
        psr = upload["preload"]["PSR_V_mode_branch"]
        self.assertEqual(psr["command"], "0x00")
        self.assertEqual(psr["if_V_mode_equals_1"], "dataBuff[2] | 0x20")
        self.assertEqual(psr["otherwise"], "dataBuff[2] & 0xDF")
        self.assertTrue(psr["PSR_is_inside_Upload_Temperature_LUT"])
        self.assertEqual(
            psr["control_flow"],
            {
                "compare_source_record_file_offset": "0x1D52E",
                "not_equal_branch_source_record_file_offset": "0x1D5E3",
                "mode_1_join_jump_source_record_file_offset": "0x1DB82",
                "mutually_exclusive_paths_and_join_proven": True,
            },
        )
        self.assertFalse(psr["legacy_bit_0x20_is_SPD1657_3bit_proof"])
        self.assertEqual(upload["lut0"]["command"], "0x20")
        self.assertEqual(upload["lut0"]["source"], "dataBuff + 4")
        self.assertEqual(upload["lut0"]["count_hex"], "0x031F")
        self.assertEqual(upload["lut0"]["count_bytes"], 799)
        self.assertEqual(upload["lut0"]["callee_section_id"], "0x1D")
        self.assertEqual(
            upload["lut0"]["callee_argument_registers"],
            {
                "command": "R12=0x20",
                "source": "R13=dataBuff+4 -> R10",
                "count": "R14=0x031F -> R11",
                "loop_counter": "R8 starts at 0",
            },
        )
        self.assertTrue(upload["lut0"]["callee_loop_proven"])
        self.assertEqual(
            upload["EPD_Load_LUT_pinned_loop_signatures"],
            {
                "caller_source_and_count_register_copy": {
                    "file_offset": "0x1B3B5",
                    "occurrences_in_EPD_Load_LUT": 1,
                },
                "counter_clear_and_jump_to_compare": {
                    "file_offset": "0x1B66A",
                    "occurrences_in_EPD_Load_LUT": 1,
                },
                "dereference_and_SPI_DATA_call": {
                    "file_offset": "0x1B742",
                    "occurrences_in_EPD_Load_LUT": 1,
                },
                "increment_pointer_counter_compare_and_unsigned_loop": {
                    "file_offset": "0x1B92F",
                    "occurrences_in_EPD_Load_LUT": 1,
                },
            },
        )
        self.assertEqual(upload["lut1"]["command"], "0x21")
        self.assertEqual(upload["lut1"]["value"], "0xFF")
        self.assertEqual(upload["lut1"]["count_bytes"], 704)
        self.assertEqual(
            upload["lut1"]["loop_control_flow"],
            {
                "pretest_jump_source_record_file_offset": "0x1E604",
                "less_than_backedge_source_record_file_offset": "0x1E8DB",
                "counter_clear_and_pretest_jump_proven": True,
                "increment_compare_0x02C0_and_backedge_proven": True,
                "exact_iteration_count_proven": True,
            },
        )
        self.assertTrue(upload["source_annotated_named_direct_PSR_observed"])
        self.assertEqual(
            upload["source_annotated_named_direct_SPI_COMMAND_values"],
            ["0x40", "0x00", "0x00", "0x21"],
        )
        self.assertEqual(
            upload["effective_command_order"],
            [
                {"command": "0x40", "dispatch": "direct SPI_COMMAND"},
                {
                    "command": "0x00",
                    "dispatch": "direct SPI_COMMAND",
                    "source_paths": 2,
                    "executions_per_invocation": 1,
                },
                {"command": "0x20", "dispatch": "EPD_Load_LUT helper"},
                {"command": "0x21", "dispatch": "direct SPI_COMMAND"},
            ],
        )
        negative = upload["negative_direct_command_observation"]
        self.assertEqual(
            negative["checked_command_values"],
            {
                "PWR": "0x01",
                "PLL": "0x30",
                "E9": "0xE9",
                "PON": "0x04",
                "DRF": "0x12",
                "POF": "0x02",
            },
        )
        self.assertEqual(negative["observed_checked_values"], [])
        self.assertFalse(
            negative["indirect_unannotated_or_cross_object_paths_ruled_out"]
        )
        self.assertNotIn("contains_direct_PWR_PLL_E9_PON_DRF_POF", upload)
        self.assertNotIn("logical_direct_SPI_COMMAND_sequence", upload)
        self.assertEqual(len(upload["pinned_ubrof_signatures"]), 11)

    def test_separate_e2801_e2802_comparison_matches_content_and_geometry(
        self,
    ) -> None:
        other = e2802.prove_object()
        self.assertEqual(
            other["object"]["sha256"],
            "19fb74c05444880ea6a403d697307e47a874998b5529ee84dd0592ecae16c9ce",
        )
        for name in ("DATA0", "DATA1"):
            ours = self.report["tagged_arrays"][name]
            theirs = other["tagged_arrays"][name]
            self.assertEqual(ours["decoded_bytes"], theirs["decoded_bytes"])
            self.assertEqual(ours["decoded_sha256"], theirs["decoded_sha256"])
            self.assertTrue(ours["report_key_is_candidate_symbol_label"])
            self.assertFalse(ours["symbol_name_to_section_binding_proven"])
            self.assertFalse(ours["link_to_runtime_dataBuff_upload_proven"])
            self.assertFalse(ours["standalone_E2802_content_comparison_performed"])

        self.assertEqual(
            self.report["tagged_arrays"]["DATA0"]["namespace_1_name_record"],
            {"index": 17, "file_offset": "0x25E3"},
        )
        self.assertEqual(
            self.report["tagged_arrays"]["DATA1"]["namespace_1_name_record"],
            {"index": 18, "file_offset": "0x25F6"},
        )

        ours_upload = self.report["upload_temperature_lut"]
        their_upload = other["upload_temperature_lut"]
        self.assertEqual(ours_upload["lut0"]["count_bytes"], 799)
        self.assertEqual(their_upload["lut0"]["count_bytes"], 799)
        self.assertEqual(ours_upload["lut1"]["count_bytes"], 704)
        self.assertEqual(their_upload["lut1"]["count_bytes"], 704)
        self.assertTrue(ours_upload["source_annotated_named_direct_PSR_observed"])
        self.assertFalse(their_upload["contains_PSR_PWR_PLL_E9_refresh_or_recovery"])
        self.assertEqual(other["EPD_Init"]["PSR_V_mode_branch"]["command"], "0x00")
        adjudication = self.report["adjudication"]
        self.assertFalse(adjudication["standalone_E2802_comparison_performed"])
        self.assertFalse(
            adjudication["cross_object_or_cross_version_corroboration_claimed"]
        )
        self.assertNotIn("cross_version_corroboration", adjudication)

    def test_exactly_seven_local_display_callers_and_no_init_edge(self) -> None:
        graph = self.report["direct_call_graph"]
        self.assertEqual(graph["direct_display_caller_count"], 7)
        self.assertEqual(graph["paired_CALLA_record_count"], 7)
        self.assertEqual(graph["source_relocation_record_count"], 14)
        self.assertEqual(graph["source_relocation_records_per_logical_CALLA"], 2)
        self.assertEqual(
            [
                (
                    row["function"],
                    row["caller_section_id"],
                    row["section_marker_file_offset"],
                    row["section_end_file_offset"],
                    row["source_line"],
                    row["source_relocation_record_file_offsets"],
                )
                for row in graph["direct_display_callers"]
            ],
            [
                (
                    "EPD_Display_White",
                    "0x26",
                    "0x3883C",
                    "0x3AA2F",
                    1420,
                    ["0x38B82", "0x38C74"],
                ),
                (
                    "EPD_Display_Black",
                    "0x25",
                    "0x3AA2F",
                    "0x3CE38",
                    1492,
                    ["0x3AD99", "0x3AE8B"],
                ),
                (
                    "EPD_Display_Yellow",
                    "0x24",
                    "0x3CE38",
                    "0x3F250",
                    1555,
                    ["0x3D1A2", "0x3D294"],
                ),
                (
                    "EPD_Display_Red",
                    "0x23",
                    "0x3F250",
                    "0x4164A",
                    1619,
                    ["0x3F5BA", "0x3F6AC"],
                ),
                (
                    "EPD_Display_line_4bit",
                    "0x22",
                    "0x4164A",
                    "0x4319D",
                    1677,
                    ["0x41915", "0x41A07"],
                ),
                (
                    "EPD_Display_Dot",
                    "0x20",
                    "0x43612",
                    "0x45C8E",
                    1738,
                    ["0x439CB", "0x43ABD"],
                ),
                (
                    "EPD_Display_Dot_4bit",
                    "0x1F",
                    "0x45C8E",
                    "0x4834B",
                    1794,
                    ["0x46045", "0x46137"],
                ),
            ],
        )
        self.assertTrue(
            all(
                row["relocation_classification"] == "local-section-relative"
                for row in graph["direct_display_callers"]
            )
        )
        self.assertTrue(
            all(
                row["all_call_records_within_caller_section"]
                for row in graph["direct_display_callers"]
            )
        )
        self.assertEqual(
            [
                row["function_name_branch_label_anchor_count"]
                for row in graph["direct_display_callers"]
            ],
            [9, 9, 9, 9, 4, 14, 14],
        )
        negative = graph["negative_edge_observation"]
        self.assertFalse(
            negative["EPD_Init_to_Upload"][
                "source_annotated_named_direct_CALLA_observed"
            ]
        )
        self.assertFalse(
            negative["EPD_Init_to_Upload"]["local_section_relocation_observed"]
        )
        self.assertFalse(
            negative["Upload_to_EPD_Init"][
                "source_annotated_named_direct_CALLA_observed"
            ]
        )
        self.assertFalse(
            negative["Upload_to_EPD_Init"]["local_section_relocation_observed"]
        )
        self.assertFalse(negative["indirect_or_cross_object_paths_ruled_out"])
        self.assertFalse(graph["init_before_upload_order_proven"])
        self.assertFalse(graph["PUBLIC_or_EXTERN_table_resolved"])

    def test_identity_mismatch_fails_before_offset_interpretation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            copied = Path(temp_dir) / "E2801.r43"
            shutil.copyfile(e2801.DEFAULT_OBJECT_PATH, copied)
            payload = bytearray(copied.read_bytes())
            payload[-1] ^= 0x01
            copied.write_bytes(payload)
            with self.assertRaisesRegex(e2801.ProofError, "SHA-256 mismatch"):
                e2801.prove_object(copied)

    def test_cli_is_metadata_only(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "tools.e2801_r43_lut_proof", "--compact"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["kind"], e2801.KIND)
        self.assertFalse(report["safety"]["hardware_accessed"])
        self.assertFalse(report["safety"]["raw_LUT_or_waveform_emitted"])
        self.assertNotIn("decoded_payload", completed.stdout)
        self.assertNotIn("waveform_bytes", completed.stdout)


if __name__ == "__main__":
    unittest.main()
