from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = REPO_ROOT / "tools" / "e2802_r43_lut_proof.py"
SPEC = importlib.util.spec_from_file_location("e2802_r43_lut_proof", TOOL_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load E2802.r43 LUT proof")
proof = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(proof)


class E2802R43LutProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = proof.prove_object()

    def test_object_and_bulk_read_are_identity_pinned(self) -> None:
        report = self.report
        self.assertEqual(report["schema_version"], 3)
        self.assertEqual(report["object"]["size_bytes"], 328_062)
        self.assertEqual(
            report["object"]["sha256"],
            "19fb74c05444880ea6a403d697307e47a874998b5529ee84dd0592ecae16c9ce",
        )

        read = report["upload_temperature_lut"]["bulk_read"]
        self.assertEqual(
            read["operation"], "ReadData(selected_address, dataBuff, 2508)"
        )
        self.assertEqual(read["count_bytes"], 2_508)
        self.assertEqual(read["destination"]["section_id"], "0x0E")
        self.assertEqual(read["destination"]["section_offset"], 0)
        self.assertEqual(read["destination"]["backing_section_extent_bytes"], 2_560)
        self.assertFalse(read["destination"]["dataBuff_symbol_size_proven"])
        self.assertNotIn("capacity_bytes", read["destination"])

        reader = read["reader"]
        self.assertEqual(reader["name_from_source_record"], "ReadData")
        self.assertEqual(reader["relocation_operator"], "0x5D")
        self.assertEqual(reader["relocation_classification"], "external-index")
        self.assertEqual(reader["external_symbol_index"], "0x03")
        self.assertEqual(reader["relocation_addend"], 0)
        self.assertFalse(reader["external_index_is_target_section_id"])
        self.assertNotIn("target_section_id", reader)
        self.assertFalse(reader["index_to_symbol_binding_independently_parsed"])
        self.assertFalse(reader["implementation_location_proven"])
        self.assertFalse(reader["provider_object_proven"])
        self.assertFalse(reader["physical_transport_proven"])
        self.assertEqual(read["evidence"]["reader_relocation_file_offset"], "0x17CCF")
        self.assertIn(
            "the provider or transport implementation behind external symbol index 0x03",
            report["not_proven"],
        )
        self.assertIn(
            "dataBuff symbol size beyond its section-relative destination and backing-section extent",
            report["not_proven"],
        )

    def test_init_and_upload_are_separate_without_a_proven_root_order(self) -> None:
        sections = self.report["function_sections"]
        self.assertEqual(sections["EPD_Init"]["section_id"], "0x2D")
        self.assertEqual(sections["Upload_Temperature_LUT"]["section_id"], "0x1E")

        graph = self.report["direct_call_graph"]
        self.assertFalse(graph["EPD_Init_calls_Upload_Temperature_LUT"])
        self.assertFalse(graph["Upload_Temperature_LUT_calls_EPD_Init"])
        self.assertEqual(graph["direct_EPD_Init_callers_inside_this_object"], 0)
        self.assertEqual(graph["Upload_direct_SPI_COMMANDs"], ["0x21"])
        self.assertTrue(graph["Upload_0x20_is_delegated_to_EPD_Load_LUT"])
        self.assertEqual(graph["Upload_busy_wait_calls"], 0)
        self.assertFalse(graph["Upload_contains_PSR_PWR_PLL_E9_PON_DRF_POF"])
        self.assertFalse(graph["init_before_upload_order_proven"])
        self.assertTrue(graph["indirect_or_cross_object_calls_excluded"])

    def test_init_command_table_and_mode_branches_are_explicit(self) -> None:
        init = self.report["EPD_Init"]
        commands = {
            item["name"]: (item["command"], item["parameters"])
            for item in init["ordered_command_table"]
        }
        self.assertEqual(commands["PWR"], ("0x01", "dataBuff[18:24]"))
        self.assertEqual(
            commands["PSR"],
            (
                "0x00",
                "V_mode branch over dataBuff[16], then dataBuff[17]",
            ),
        )
        self.assertEqual(commands["PLL"], ("0x30", "Dyna_PLL branch over dataBuff[42]"))
        self.assertEqual(commands["TRES"], ("0x61", "dataBuff[47:51]"))
        self.assertEqual(commands["TSSET"], ("0xE6", "dataBuff[58]"))

        psr = init["PSR_V_mode_branch"]
        self.assertEqual(
            psr["if_V_mode_equals_1"],
            ["dataBuff[16] | 0x20", "dataBuff[17]"],
        )
        self.assertEqual(
            psr["otherwise"],
            ["dataBuff[16] & 0xDF", "dataBuff[17]"],
        )
        self.assertFalse(psr["legacy_bit_0x20_is_SPD1657_3bit_proof"])

        pll = init["PLL_Dyna_PLL_branch"]
        self.assertEqual(pll["if_Dyna_PLL_equals_1"], "dataBuff[42] | 0x08")
        self.assertEqual(pll["otherwise"], "dataBuff[42] & 0xF7")
        self.assertFalse(init["conditional_calibration"]["visible_refresh"])
        self.assertTrue(init["requires_prepopulated_dataBuff"])

    def test_seven_callers_have_refresh_power_but_not_recovery_closure(self) -> None:
        display = self.report["display_refresh_callers"]
        self.assertEqual(display["logical_callers"], 7)
        self.assertEqual(display["UBROF_source_relocation_records"], 14)
        self.assertEqual(display["records_per_logical_CALLA"], 2)
        self.assertFalse(display["named_blue_or_green_caller_present"])
        self.assertEqual(
            [item["function"] for item in display["callers"]],
            [
                "EPD_Display_White",
                "EPD_Display_Black",
                "EPD_Display_Yellow",
                "EPD_Display_Red",
                "EPD_Display_line_4bit",
                "EPD_Display_Dot",
                "EPD_Display_Dot_4bit",
            ],
        )
        self.assertEqual(
            {item["function"]: item["upload_position"] for item in display["callers"]},
            {
                "EPD_Display_White": "before_DTM",
                "EPD_Display_Black": "before_DTM",
                "EPD_Display_Yellow": "after_PON_before_DRF",
                "EPD_Display_Red": "after_PON_before_DRF",
                "EPD_Display_line_4bit": "before_DTM",
                "EPD_Display_Dot": "before_DTM",
                "EPD_Display_Dot_4bit": "before_DTM",
            },
        )
        self.assertTrue(display["invariants"]["Upload_before_DRF_in_all_callers"])
        self.assertTrue(
            display["invariants"]["PON_before_DRF_before_POF_in_all_callers"]
        )
        self.assertTrue(display["invariants"]["POF_0_then_busy_closure_in_all_callers"])
        self.assertFalse(display["invariants"]["Upload_position_is_uniform"])

        classification = self.report["power_and_recovery_classification"]
        self.assertTrue(classification["closure_proven_for_all_seven_display_callers"])
        self.assertFalse(classification["factory_or_OTP_recovery_closure"])
        self.assertFalse(
            classification["safe_live_panel_sequence_derivable_from_object_alone"]
        )

    def test_cli_is_metadata_only_and_keeps_live_use_blocked(self) -> None:
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
        self.assertFalse(report["safety"]["raw_waveform_emitted"])
        self.assertFalse(report["safety"]["live_approved"])
        self.assertFalse(report["safety"]["hardware_accessed"])
        self.assertFalse(report["safety"]["serial_accessed"])
        self.assertFalse(report["safety"]["device_network_accessed"])
        self.assertNotIn("decoded_payload", completed.stdout)
        self.assertNotIn("waveform_bytes", completed.stdout)

    def test_identity_mismatch_is_rejected_before_offset_evidence(self) -> None:
        payload = bytearray(proof.DEFAULT_OBJECT_PATH.read_bytes())
        payload[-1] ^= 0x01
        with tempfile.TemporaryDirectory() as temp_dir:
            mutated = Path(temp_dir) / "E2802-mutated.r43"
            mutated.write_bytes(payload)
            with self.assertRaisesRegex(proof.ProofError, "SHA-256 mismatch"):
                proof.prove_object(mutated)


if __name__ == "__main__":
    unittest.main()
