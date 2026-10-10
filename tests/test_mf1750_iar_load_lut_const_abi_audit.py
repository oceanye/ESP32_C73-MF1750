from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools import mf1750_iar_load_lut_const_abi_audit as audit
from tools import mf1750_iar_r43_cross_object_graph as graph


REPO_ROOT = Path(__file__).resolve().parents[1]


def _iar_tool(filename: str, environment_name: str) -> Path | None:
    configured = os.environ.get(environment_name)
    candidates = [] if configured is None else [Path(configured)]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(
            Path(local_app_data)
            / "Temp"
            / "iar_ew430_6201_xlink_only"
            / "component_430_xlink_common"
            / "430"
            / "bin"
            / filename
        )
    return next((path for path in candidates if path.is_file()), None)


def _objdump() -> Path | None:
    configured = os.environ.get("MF1750_MSP430_OBJDUMP_PATH")
    candidates = [] if configured is None else [Path(configured)]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(
            Path(local_app_data)
            / "Temp"
            / "msp430-gcc-7.3.2.154-win64-extracted"
            / "msp430-gcc-7.3.2.154_win64"
            / "bin"
            / "msp430-elf-objdump.exe"
        )
    return next((path for path in candidates if path.is_file()), None)


AVAILABLE_XLINK = _iar_tool("xlink.exe", "MF1750_IAR_XLINK_PATH")
AVAILABLE_XLIB = _iar_tool("xlib.exe", "MF1750_IAR_XLIB_PATH")
AVAILABLE_OBJDUMP = _objdump()


class Mf1750IarLoadLutConstParserTests(unittest.TestCase):
    def test_cross_reference_accepts_code_data_and_not_needed_rows(self) -> None:
        text = """
        DATA0                    0C5D
        EPD_Load_LUT_const       NOT NEEDED
        SPI_COMMAND              00010020
MODULE MAP
"""
        self.assertEqual(audit._cross_reference_status(text, "DATA0"), "0C5D")
        self.assertEqual(
            audit._cross_reference_status(text, "EPD_Load_LUT_const"),
            "NOT NEEDED",
        )
        self.assertEqual(
            audit._cross_reference_status(text, "SPI_COMMAND"),
            "00010020",
        )

    def test_module_entry_distinguishes_included_and_not_needed_parts(self) -> None:
        text = """
MODULE MAP
CODE
  Segment part 44. NOT NEEDED.
           ENTRY                   ADDRESS         REF BY
           =====                   =======         ======
           EPD_Load_LUT_const
               calls direct
CODE
  Relative segment, address: 000104D8 - 000104F7 (0x20 bytes), align: 1
  Segment part 29.            Intra module refs:   Upload_Temperature_LUT
           ENTRY                   ADDRESS         REF BY
           =====                   =======         ======
           EPD_Load_LUT            000104D8
               calls direct
"""
        const = audit._module_entry(text, "EPD_Load_LUT_const")
        self.assertEqual(const["segment_part"], 44)
        self.assertFalse(const["needed"])
        self.assertIsNone(const["address"])
        self.assertIsNone(const["span"])
        self.assertEqual(const["incoming_intra_module_refs"], [])

        mutable = audit._module_entry(text, "EPD_Load_LUT")
        self.assertEqual(mutable["segment_part"], 29)
        self.assertTrue(mutable["needed"])
        self.assertEqual(mutable["address"], "0x104D8")
        self.assertEqual(mutable["span"]["bytes"], 32)
        self.assertEqual(
            mutable["incoming_intra_module_refs"],
            ["Upload_Temperature_LUT"],
        )

    def test_complete_instruction_contract_encodes_pretested_unsigned_loop(
        self,
    ) -> None:
        self.assertEqual(len(audit.EXPECTED_INSTRUCTIONS), 14)
        self.assertEqual(audit.EXPECTED_INSTRUCTIONS[0x10002], "mov r13, r10")
        self.assertEqual(audit.EXPECTED_INSTRUCTIONS[0x10004], "mov r14, r11")
        self.assertEqual(audit.EXPECTED_INSTRUCTIONS[0x1000A], "clr r8")
        self.assertEqual(audit.EXPECTED_INSTRUCTIONS[0x1000C], "jmp $+12")
        self.assertEqual(audit.EXPECTED_INSTRUCTIONS[0x1000E], "mov.b @r10, r12")
        self.assertEqual(audit.EXPECTED_INSTRUCTIONS[0x10018], "cmp r11, r8")
        self.assertEqual(audit.EXPECTED_INSTRUCTIONS[0x1001A], "jnc $-12")
        self.assertEqual(
            audit.SPI_DATA_SERIALIZATION_INSTRUCTIONS[0x1009E],
            "mov.b r12, r10",
        )
        self.assertEqual(
            audit.SPI_DATA_SERIALIZATION_INSTRUCTIONS[0x100F2],
            "cmp.b #0, r10",
        )
        self.assertEqual(
            audit.SPI_DATA_SERIALIZATION_INSTRUCTIONS[0x100EA],
            "rla.b r10",
        )

    def test_object_pin_rejects_mutation_before_any_link(self) -> None:
        name = "E2802.r43"
        source = graph.DEFAULT_IAR_ROOT / graph.OBJECT_DIR_REL / name
        payload = bytearray(source.read_bytes())
        payload[-1] ^= 1
        with tempfile.TemporaryDirectory() as temp_name:
            copied = Path(temp_name) / name
            copied.write_bytes(payload)
            with self.assertRaisesRegex(
                audit.LoadLutConstAbiAuditError,
                "SHA-256 changed",
            ):
                audit._pin_object(copied, audit.OBJECTS[name])


@unittest.skipUnless(
    AVAILABLE_XLINK is not None
    and AVAILABLE_XLIB is not None
    and AVAILABLE_OBJDUMP is not None,
    "the identity-pinned XLINK/XLIB/objdump toolchain is not available",
)
class Mf1750IarLoadLutConstOfficialToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert AVAILABLE_XLINK is not None
        assert AVAILABLE_XLIB is not None
        assert AVAILABLE_OBJDUMP is not None
        cls.report = audit.build_report(
            AVAILABLE_XLINK,
            AVAILABLE_XLIB,
            AVAILABLE_OBJDUMP,
        )

    def test_four_helpers_have_one_complete_identical_machine_body(self) -> None:
        equivalence = self.report["cross_object_and_function_equivalence"]
        self.assertEqual(equivalence["root_only_links_compared"], 4)
        self.assertEqual(
            equivalence["unique_function_body_sha256"],
            [audit.COMMON_LINK["function_sha256"]],
        )
        self.assertEqual(
            equivalence["unique_root_only_image_sha256"],
            [audit.COMMON_LINK["intel_hex_sha256"]],
        )
        self.assertTrue(
            equivalence["EPD_Load_LUT_const_equals_EPD_Load_LUT_machine_body"]
        )
        self.assertTrue(equivalence["E2801_equals_E2802_machine_body"])

        for obj in self.report["objects"].values():
            for function in audit.FUNCTIONS:
                linked = obj["functions"][function]["root_only_synthetic_link"]
                self.assertEqual(linked["function"]["byte_count"], 32)
                self.assertEqual(linked["function"]["instruction_line_count"], 14)
                self.assertEqual(
                    linked["function"]["sha256"],
                    audit.COMMON_LINK["function_sha256"],
                )
                self.assertEqual(linked["DATA0_cross_reference"], "NOT NEEDED")
                self.assertEqual(linked["DATA1_cross_reference"], "NOT NEEDED")
                for helper in audit.HELPERS:
                    self.assertTrue(
                        linked["helpers"][helper]["entry_consumes_R12_low_byte"]
                    )

    def test_register_abi_is_command_pointer_count_with_zero_count_pretest(
        self,
    ) -> None:
        abi = self.report["register_abi"]
        self.assertIn("command byte", abi["R12_on_entry"])
        self.assertIn("source byte pointer", abi["R13_on_entry"])
        self.assertIn("unsigned byte count", abi["R14_on_entry"])
        self.assertIn("zero count sends no data bytes", abi["loop_pretest"])
        self.assertEqual(abi["command_helper_calls_per_invocation"], 1)
        self.assertFalse(abi["C_prototype_recovered_exactly"])

    def test_sender_is_fixed_length_original_order_without_record_parser(self) -> None:
        dataflow = self.report["sender_dataflow_adjudication"]
        self.assertTrue(dataflow["complete_generic_sender_instruction_contract_pinned"])
        self.assertTrue(dataflow["complete_SPI_DATA_machine_body_hash_pinned"])
        self.assertTrue(dataflow["source_byte_loaded_once_per_counted_iteration"])
        self.assertEqual(dataflow["source_pointer_increment_bytes"], 1)
        self.assertEqual(dataflow["loop_counter_increment_per_byte"], 1)
        self.assertFalse(
            dataflow["data_value_controls_generic_sender_loop_or_termination"]
        )
        self.assertFalse(dataflow["eleven_or_eighty_eight_byte_record_stride_present"])
        self.assertFalse(
            dataflow["NOT_XOR_RBIT_REV_or_byte_complement_in_generic_sender_present"]
        )
        self.assertEqual(dataflow["SPI_DATA_serialized_bit_count"], 8)
        self.assertEqual(dataflow["SPI_DATA_wire_bit_order"], "D7_to_D0")
        self.assertFalse(dataflow["SPI_DATA_bitwise_complement_before_wire_present"])
        self.assertTrue(
            dataflow["MCU_sender_side_fixed_length_original_byte_order_proven"]
        )
        self.assertFalse(dataflow["controller_internal_decode_or_complement_proven"])
        self.assertFalse(dataflow["FF_or_zero_terminator_semantics_proven"])

    def test_const_has_no_natural_consumer_while_mutable_has_upload_consumer(
        self,
    ) -> None:
        for name, obj in self.report["objects"].items():
            const = obj["functions"]["EPD_Load_LUT_const"]
            mutable = obj["functions"]["EPD_Load_LUT"]
            self.assertEqual(const["incoming_direct_calls"], [])
            self.assertEqual(
                const["all_other_PUBLIC_roots_natural_reference_test"][
                    "target_cross_reference_status"
                ],
                "NOT NEEDED",
            )
            self.assertFalse(
                const["all_other_PUBLIC_roots_natural_reference_test"]["target_needed"]
            )
            self.assertEqual(len(mutable["incoming_direct_calls"]), 1, name)
            self.assertEqual(
                mutable["incoming_direct_calls"][0]["caller_symbols"],
                ["Upload_Temperature_LUT"],
            )
            self.assertTrue(
                mutable["all_other_PUBLIC_roots_natural_reference_test"][
                    "target_needed"
                ]
            )
            self.assertEqual(
                mutable["all_other_PUBLIC_roots_natural_reference_test"][
                    "incoming_intra_module_refs"
                ],
                ["Upload_Temperature_LUT"],
            )

    def test_complete_project_scan_separates_same_spelling_from_external_consumer(
        self,
    ) -> None:
        consumer = self.report["consumer_adjudication"]
        self.assertEqual(consumer["objects_scanned"], 29)
        self.assertEqual(consumer["paired_direct_call_edges_scanned"], 1_786)
        self.assertEqual(consumer["EPD_Load_LUT_const_direct_consumer_edges"], [])
        self.assertEqual(
            consumer["EPD_Load_LUT_const_observed_external_direct_consumer_count"],
            0,
        )
        self.assertEqual(
            consumer["EPD_Load_LUT_observed_external_direct_consumer_count"],
            0,
        )
        self.assertEqual(
            consumer["EPD_Load_LUT_same_spelling_local_edge_counts_by_object"],
            {
                "E2801.r43": 1,
                "E2802.r43": 1,
                "ED020OC2.r43": 27,
                "ED020OC4.r43": 14,
            },
        )
        self.assertFalse(
            consumer["same_spelling_local_symbols_are_cross_object_consumers"]
        )
        self.assertFalse(consumer["E2801_or_E2802_is_current_final_d43_direct_input"])
        external = consumer["official_external_table_scan"]
        self.assertEqual(external["official_XLIB_parseable_external_tables"], 26)
        self.assertEqual(
            external["official_XLIB_version_bounded_external_tables"],
            ["DELAY.r43", "E6_73.r43", "main.r43"],
        )
        self.assertEqual(
            external["EPD_Load_LUT_const_external_declaration_objects"],
            [],
        )
        self.assertEqual(external["EPD_Load_LUT_external_declaration_objects"], [])

    def test_report_is_metadata_only_and_integrity_sealed(self) -> None:
        scope = self.report["scope"]
        self.assertFalse(scope["hardware_accessed"])
        self.assertFalse(scope["serial_or_com_accessed"])
        self.assertFalse(scope["device_network_accessed"])
        self.assertFalse(scope["raw_object_code_emitted"])
        self.assertFalse(scope["raw_disassembly_emitted"])
        self.assertFalse(scope["raw_waveform_or_payload_emitted"])
        self.assertEqual(scope["visible_refreshes"], 0)

        without_integrity = {
            key: value for key, value in self.report.items() if key != "integrity"
        }
        self.assertEqual(
            audit._sha256(audit._canonical_bytes(without_integrity)),
            self.report["integrity"]["canonical_sha256"],
        )
        serialized = json.dumps(self.report, sort_keys=True)
        self.assertNotIn('"raw_bytes"', serialized)
        self.assertNotIn('"disassembly"', serialized)

    def test_cli_emits_same_sealed_report(self) -> None:
        assert AVAILABLE_XLINK is not None
        assert AVAILABLE_XLIB is not None
        assert AVAILABLE_OBJDUMP is not None
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.mf1750_iar_load_lut_const_abi_audit",
                "--xlink",
                str(AVAILABLE_XLINK),
                "--xlib",
                str(AVAILABLE_XLIB),
                "--objdump",
                str(AVAILABLE_OBJDUMP),
                "--compact",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            timeout=60,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8"))
        self.assertFalse(completed.stderr)
        cli_report = json.loads(completed.stdout.decode("utf-8"))
        self.assertEqual(
            cli_report["integrity"]["canonical_sha256"],
            self.report["integrity"]["canonical_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
