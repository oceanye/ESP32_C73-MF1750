from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

from tools import mf1750_armcc_loadwf_deep_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]


class ArmccLoadwfDeepAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report()

    def test_archive_and_complete_function_inventory_are_identity_pinned(self) -> None:
        archive = self.report["archive"]
        self.assertEqual(archive["sha256"], audit.EXPECTED_LIBRARY_SHA256)
        self.assertEqual(archive["object_member_count"], 1)
        self.assertEqual(archive["object"]["name"], "eload_20250305b1.o")
        self.assertEqual(archive["object"]["magic_hex"], "f74f524301010100")

        inventory = self.report["function_inventory"]
        functions = inventory["functions"]
        self.assertEqual(inventory["dwarf_subprograms"], 23)
        self.assertEqual(
            [
                (item["name"], item["code_stream_start"], item["bytes"])
                for item in functions
            ],
            list(audit.FUNCTION_LAYOUT),
        )
        self.assertEqual(inventory["executable_bytes"], 0x1408)
        self.assertEqual(inventory["alignment_before_comment_bytes"], 4)

    def test_loadwf_cfg_and_all_four_write_bindings_are_exact(self) -> None:
        loadwf = self.report["loadwf"]
        cfg = loadwf["cfg"]
        self.assertEqual(cfg["node_count"], 6)
        self.assertEqual(cfg["edge_count"], 7)
        self.assertEqual(cfg["cyclomatic_complexity"], 3)
        self.assertEqual(cfg["loops"], 0)
        self.assertEqual(
            [call["callee"] for call in loadwf["call_sites"]],
            [
                "strlen",
                "test_decrypt_cbc_check_key",
                "writeEPD",
                "writeEPD",
                "writeEPD",
                "writeEPD",
            ],
        )
        self.assertEqual(
            [
                (item["command"], item["parameter_bytes"], item["pointer"])
                for item in loadwf["success_transactions"]
            ],
            [
                ("0x01", 6, "pwr_d"),
                ("0x30", 1, "pll_d"),
                ("0x20", 535, "in"),
                ("0x21", 704, "LUT1_DATA"),
            ],
        )
        self.assertFalse(loadwf["writer_result_checked"])
        self.assertFalse(loadwf["controller_or_chip_select_argument_present"])

    def test_decrypt_gate_proves_bounds_bug_and_e2_normal_unreachability(self) -> None:
        gate = self.report["decrypt_gate"]
        wrapper = gate["wrapper_contract"]
        self.assertEqual(wrapper["fixed_ciphertext_copy_bytes"], 544)
        self.assertEqual(wrapper["wrapped_length_offsets"], [544, 545])
        self.assertEqual(wrapper["iniKey_capacity_bytes_from_dwarf"], 75)
        self.assertFalse(wrapper["length_bound_checked_before_iniKey_copy"])
        self.assertFalse(wrapper["length_bound_checked_before_iniKey_xor"])
        self.assertFalse(wrapper["length_bound_checked_before_iniKey_terminator"])
        self.assertTrue(wrapper["length_equality_check_occurs_after_unsafe_operations"])

        self.assertEqual(gate["normal_single_thread_return_pairs"], [[0, 0], [1, 1]])
        self.assertEqual(gate["loadwf_e2_pair"], [1, 0])
        self.assertTrue(gate["e2_branch_exists_in_loadwf_machine_code"])
        self.assertFalse(
            gate["loadwf_e2_reachable_from_normal_single_thread_helper_return"]
        )
        self.assertFalse(gate["plaintext_magic_checked"])
        self.assertFalse(gate["plaintext_format_checked"])
        self.assertFalse(gate["padding_checked"])
        self.assertFalse(gate["integrity_or_authentication_checked"])
        self.assertFalse(gate["aes_callee_error_status_checked"])

        calls = {
            entry["offset"]: entry["symbol_name"]
            for entry in gate["relocation_section"]["entries"]
            if entry["relocation_type"] == "ARM_THM_CALL"
        }
        self.assertEqual(calls[0x9C], "mysha256")
        self.assertEqual(calls[0xA6], "tiny_md5")
        self.assertEqual(calls[0xB0], "AES_init_ctx_iv")
        self.assertEqual(calls[0xBC], "AES_CBC_decrypt_buffer")

    def test_macros_constants_and_mode1_negative_findings_are_bounded(self) -> None:
        macros = {
            item["name"]: item["value"]
            for item in self.report["compiler_and_macros"]["source_macro_records"]
        }
        self.assertEqual(macros["E5_3Bit_Mode"], "0")
        self.assertEqual(macros["Show_Debug_LOG"], "0")
        self.assertEqual(macros["WF_DeCode_SIZE"], "544")
        self.assertEqual(macros["WF_SIZE"], "535")
        self.assertTrue(
            all(
                value == 0
                for value in self.report["compiler_and_macros"][
                    "forbidden_retained_token_counts"
                ].values()
            )
        )

        lut1 = next(
            item for item in self.report["constdata"] if item["name"] == "LUT1_DATA"
        )
        self.assertEqual(lut1["bytes"], 704)
        self.assertTrue(lut1["all_ff"])
        self.assertFalse(lut1["raw_bytes_emitted"])

        negatives = self.report["strict_negative_findings"]
        self.assertFalse(negatives["second_archive_object_member_present"])
        self.assertFalse(negatives["second_loadwf_dwarf_subprogram_present"])
        self.assertFalse(negatives["same_object_799_byte_write_present"])
        self.assertFalse(
            negatives["source_level_inactive_mode1_branch_recoverable_from_object"]
        )
        self.assertFalse(negatives["never_existed_in_original_source_proven"])

    def test_cli_is_metadata_only(self) -> None:
        completed = subprocess.run(
            [sys.executable, "tools/mf1750_armcc_loadwf_deep_audit.py"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["kind"], audit.KIND)
        self.assertFalse(report["safety"]["customer_key_material_emitted"])
        self.assertFalse(report["safety"]["raw_plaintext_emitted"])
        self.assertFalse(report["safety"]["runtime_payload_generated"])
        self.assertFalse(report["safety"]["hardware_accessed"])
        self.assertFalse(report["safety"]["serial_or_com_accessed"])
        self.assertFalse(report["safety"]["device_network_accessed"])


if __name__ == "__main__":
    unittest.main()
