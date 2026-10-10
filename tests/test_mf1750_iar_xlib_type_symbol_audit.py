from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools import mf1750_iar_r43_cross_object_graph as graph
from tools import mf1750_iar_xlib_type_symbol_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]


def _official_xlib() -> Path | None:
    configured = os.environ.get("MF1750_IAR_XLIB_PATH")
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
            / "xlib.exe"
        )
    return next((path for path in candidates if path.is_file()), None)


AVAILABLE_XLIB = _official_xlib()


class Mf1750IarXlibTypeSymbolParserTests(unittest.TestCase):
    def test_source_range_parser_preserves_exact_and_relative_lines(self) -> None:
        absolute = {
            "tag": "t_source_range1",
            "parts": [r"[D:\producer\LUT.h\2:21-25]"],
            "list_line": 10,
        }
        self.assertEqual(
            audit._parse_source_range(absolute),  # noqa: SLF001
            {
                "path": r"D:\producer\LUT.h",
                "start_line": 2,
                "start_column": 21,
                "end_line": 2,
                "end_column": 25,
                "xlib_list_line": 10,
            },
        )
        relative = {
            "tag": "t_source_range1",
            "parts": ["[364:1-442:1]"],
            "list_line": 20,
        }
        self.assertEqual(
            audit._parse_source_range(relative),  # noqa: SLF001
            {
                "path": None,
                "start_line": 364,
                "start_column": 1,
                "end_line": 442,
                "end_column": 1,
                "xlib_list_line": 20,
            },
        )

    def test_identity_pin_fails_closed_before_any_tool_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "E2802.r43"
            path.write_bytes(b"not the object")
            with self.assertRaisesRegex(audit.IarTypeSymbolAuditError, "size mismatch"):
                audit._pin_object(path, audit.OBJECTS["E2802"])  # noqa: SLF001


@unittest.skipUnless(
    AVAILABLE_XLIB is not None,
    "the identity-pinned official XLIB 6.1.3.56 is not available",
)
class Mf1750IarXlibTypeSymbolOfficialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert AVAILABLE_XLIB is not None
        cls.report = audit.build_report(AVAILABLE_XLIB)

    def test_all_array_dimensions_are_direct_and_cross_object_identical(self) -> None:
        expected = [
            ("const unsigned char[1503]", ["DATA0"]),
            ("const unsigned char[704]", ["DATA1"]),
            ("unsigned char[2560]", ["dataBuff"]),
            ("unsigned char[8]", ["dataBuff2"]),
            ("unsigned char[2]", ["BUF"]),
            ("unsigned char[1024]", ["GetTempBuf", "lut_otp"]),
            ("unsigned char[3]", ["chk_code"]),
        ]
        for row in self.report["objects"].values():
            arrays = row["array_dimensions"]
            self.assertEqual(len(arrays), 7)
            self.assertEqual(
                [
                    (
                        item["declaration"],
                        [binding["name"] for binding in item["bindings"]],
                    )
                    for item in arrays
                ],
                expected,
            )
        cross = self.report["cross_object_adjudication"]
        self.assertTrue(cross["selected_normalized_type_projection_identical"])
        self.assertTrue(cross["DATA0_type_is_const_unsigned_char_1503"])
        self.assertTrue(cross["DATA1_type_is_const_unsigned_char_704"])
        self.assertTrue(cross["dataBuff_type_is_unsigned_char_2560"])

    def test_array_source_lines_use_pinned_producer_paths(self) -> None:
        expected = {
            "E2801": {
                "directory": (
                    r"D:\E2801\Firmware_BX\20200527_E2801_BX_V0_0_1 - "
                    r"OTP Test - VDG_HDG - 34pin"
                ),
                "data_buff_line": 126,
            },
            "E2802": {
                "directory": (
                    r"D:\E2802\20200923_3_inch\20200807_E2802_V0_0_4 - "
                    r"for verification"
                ),
                "data_buff_line": 133,
            },
        }
        for object_name, row in self.report["objects"].items():
            by_name = {
                binding["name"]: binding
                for array in row["array_dimensions"]
                for binding in array["bindings"]
            }
            directory = expected[object_name]["directory"]
            self.assertEqual(
                by_name["DATA0"]["source_range"]["path"], directory + r"\LUT.h"
            )
            self.assertEqual(by_name["DATA0"]["source_range"]["start_line"], 2)
            self.assertEqual(by_name["DATA1"]["source_range"]["start_line"], 138)
            self.assertEqual(
                by_name["dataBuff"]["source_range"]["start_line"],
                expected[object_name]["data_buff_line"],
            )
            self.assertEqual(
                by_name["dataBuff"]["source_range"]["path_identity_basis"],
                "pinned embedded producer directory plus XLIB source basename",
            )

    def test_read_and_load_signatures_are_exact(self) -> None:
        expected = {
            "ReadData": ("void", ["uint8_t", "uint16_t", "uint8_t *", "uint16_t"]),
            "EPD_Load_LUT": ("void", ["uint16_t", "uint8_t *", "uint16_t"]),
            "EPD_Load_LUT_const": (
                "void",
                ["uint16_t", "const uint8_t *", "uint16_t"],
            ),
            "Upload_Temperature_LUT": ("uint8_t", []),
        }
        for row in self.report["objects"].values():
            functions = row["selected_function_types"]
            for name, (return_type, parameters) in expected.items():
                signature = functions[name]["signature"]
                self.assertEqual(signature["return"], return_type)
                self.assertEqual(signature["parameters"], parameters)

    def test_upload_locals_and_line_information_are_exact(self) -> None:
        names_and_types = [
            ("a", "int16_t"),
            ("status", "uint8_t"),
            ("TemperatureAddress", "uint32_t"),
            ("i", "uint32_t"),
            ("TemperatureAddress_23_16", "uint8_t"),
            ("TemperatureAddress_15_0", "uint16_t"),
            ("BUF", "uint8_t[2]"),
            ("LUT_idx", "int16_t"),
        ]
        expected_lines = {
            "E2801": [None, 489, 490, 491, 492, 493, 494, 495],
            "E2802": [None, 366, 367, 368, 369, 370, 371, 372],
        }
        for object_name, row in self.report["objects"].items():
            locals_rows = row["upload_temperature_lut_locals"]
            self.assertEqual(
                [(item["name"], item["normalized_type"]) for item in locals_rows],
                names_and_types,
            )
            self.assertEqual(
                [
                    None
                    if item["explicit_source_range"] is None
                    else item["explicit_source_range"]["start_line"]
                    for item in locals_rows
                ],
                expected_lines[object_name],
            )
            self.assertEqual(
                row["selected_function_types"]["Upload_Temperature_LUT"]["body_range"][
                    "start_line"
                ],
                487 if object_name == "E2801" else 364,
            )

    def test_data_arrays_have_zero_section_relocation_references(self) -> None:
        expected_totals = {"E2801": (997, 38), "E2802": (1_058, 37)}
        for object_name, row in self.report["objects"].items():
            relocations = row["array_relocation_references"]
            self.assertEqual(
                (
                    relocations["t_push_rel_records"],
                    relocations["referenced_section_count"],
                ),
                expected_totals[object_name],
            )
            for array_name, section in (("DATA0", "0x0014"), ("DATA1", "0x0015")):
                target = relocations["targets"][array_name]
                self.assertEqual(target["section_id"], section)
                self.assertEqual(target["t_push_rel_reference_operands"], 0)
                self.assertEqual(target["t_org_rel1_definition_origins"], 1)

    def test_report_is_deterministic_metadata_only_and_non_authorizing(self) -> None:
        self.assertEqual(
            self.report["integrity"]["canonical_sha256"],
            "2e777a28642c683c0c131a025525a531f969b86734048b0dd79e435718c7f4b3",
        )
        serialized = json.dumps(self.report, sort_keys=True).lower()
        for forbidden in (
            '"object_bytes"',
            '"lut_bytes"',
            '"waveform_bytes"',
            '"payload_bytes"',
            '"raw_object_code"',
            '"live_payload"',
        ):
            self.assertNotIn(forbidden, serialized)
        scope = self.report["scope"]
        self.assertFalse(scope["hardware_accessed"])
        self.assertFalse(scope["serial_or_COM8_accessed"])
        self.assertFalse(scope["device_network_accessed"])
        self.assertEqual(scope["visible_refreshes"], 0)
        boundaries = self.report["evidence_boundaries"]
        self.assertFalse(
            boundaries["DATA0_internal_799_subobject_or_field_boundary_proven"]
        )
        self.assertFalse(boundaries["current_800_byte_wrapper_ABI_proven"])
        self.assertFalse(boundaries["dual_controller_destination_or_commit_proven"])
        self.assertFalse(boundaries["authorizes_live_hardware_action"])

    def test_one_dimension_mutation_fails_closed(self) -> None:
        assert AVAILABLE_XLIB is not None
        object_path = graph.DEFAULT_IAR_ROOT / graph.OBJECT_DIR_REL / "E2802.r43"
        payload = audit._run_list_object_code(AVAILABLE_XLIB, object_path)  # noqa: SLF001
        old = b"ARRAY1 unsigned char 000005DF 000005DF"
        new = b"ARRAY1 unsigned char 000005DE 000005DE"
        self.assertEqual(payload.count(old), 1)
        mutated = payload.replace(old, new)
        with self.assertRaisesRegex(
            audit.IarTypeSymbolAuditError, "array type 0077 changed"
        ):
            audit._parse_object_listing(  # noqa: SLF001
                "E2802", mutated, audit.OBJECTS["E2802"]
            )

    def test_cli_emits_the_same_report_and_exact_command_contract(self) -> None:
        assert AVAILABLE_XLIB is not None
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.mf1750_iar_xlib_type_symbol_audit",
                "--xlib",
                str(AVAILABLE_XLIB),
                "--compact",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            timeout=60,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8"))
        parsed = json.loads(completed.stdout)
        self.assertEqual(parsed["integrity"], self.report["integrity"])
        contract = parsed["official_tool_contract"]
        self.assertEqual(contract["operation"], "LIST-OBJECT-CODE")
        self.assertEqual(
            contract["stdin_lines_exact_template"],
            [
                "ON-ERROR-EXIT",
                'LIST-OBJECT-CODE "<temporary-copy-of-E2801-or-E2802.r43>" '
                '"<temporary-list-output>"',
                "EXIT",
            ],
        )


if __name__ == "__main__":
    unittest.main()
