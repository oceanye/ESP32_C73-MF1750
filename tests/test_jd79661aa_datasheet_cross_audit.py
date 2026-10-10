from __future__ import annotations

import hashlib
import json
import unittest
from urllib.request import Request

from tools import jd79661aa_datasheet_cross_audit as audit


def _source_fixture() -> tuple[str, str]:
    lines = ["void X::_InitDisplay()", "{"]
    for command, data in audit.EXPECTED_INIT_TRACE[:-1]:
        lines.append(f"  _writeCommand(0x{command:02X});")
        if command == 0x61:
            expressions = (
                "WIDTH / 256",
                "WIDTH % 256",
                "HEIGHT / 256",
                "HEIGHT % 256",
            )
            for expression in expressions:
                lines.append(f"  _writeData({expression});")
        else:
            for value in data:
                lines.append(f"  _writeData(0x{value:02X});")
    lines.extend(
        [
            "  _PowerOn();",
            "}",
            "void X::_PowerOn()",
            "{",
            "  _writeCommand(0x04);",
            "}",
        ]
    )
    header = "static const uint16_t WIDTH = 128;\nstatic const uint16_t HEIGHT = 250;\n"
    return "\n".join(lines), header


class DatasheetCrossAuditTests(unittest.TestCase):
    def test_network_inputs_are_exact_https_urls_and_redirects_fail_closed(
        self,
    ) -> None:
        self.assertEqual(audit.SCHEMA_VERSION, 2)
        self.assertEqual(set(audit.URLS), set(audit.EXPECTED_IDENTITIES))
        for url in audit.URLS.values():
            self.assertTrue(url.startswith("https://"))

        handler = audit._RejectRedirects()
        with self.assertRaisesRegex(
            audit.DatasheetAuditError, "network redirect refused"
        ):
            handler.redirect_request(
                Request(audit.PDF_URL),
                None,
                302,
                "Found",
                {},
                "http://127.0.0.1/device",
            )

    def test_public_identities_are_fully_pinned(self) -> None:
        self.assertEqual(
            audit.EXPECTED_IDENTITIES["datasheet_pdf"],
            (
                3_386_370,
                "fc18052e01fe9d0aba00e15c9c87919659b44d0d2132f8d538bc2045bac67625",
            ),
        )
        self.assertEqual(audit.EXPECTED_PDF_PAGES, 78)
        self.assertEqual(len(audit.EXPECTED_CRITICAL_PAGE_TEXT), 12)
        self.assertEqual(
            audit.GXEPD2_COMMIT, "de82887e77a78528ea386e68bba2cb0291d2c319"
        )

    def test_pdf_semantics_keep_command_claims_bounded(self) -> None:
        pages = [""] * 64
        commands = " ".join(
            f"R{command:02X}H" for command in sorted(audit.EXPECTED_REGISTER_COMMANDS)
        )
        pages[17] = commands
        pages[18] = ""
        pages[20] = "LUT selection setting 1 : Using LUT from register"
        pages[62] = "R60H S2G[5:0] G2S[5:0]"
        pages[63] = "Tsen LUT0 R10h Data stop (20h) (11h)"

        result = audit._pdf_semantics(
            pages,
            {},
            extractor_version="synthetic-test",
            enforce_pins=False,
        )

        table = result["register_table"]
        self.assertEqual(table["command_count"], 30)
        self.assertFalse(table["command_0x20_present"])
        self.assertFalse(table["command_0x21_present"])
        self.assertFalse(table["command_0xe9_present"])
        opcode = result["opcode_adjudication"]
        self.assertEqual(opcode["0x20"]["page_64_waveform_diagram_label"], "LUT0 (20h)")
        self.assertFalse(opcode["0x20"]["parameter_count_or_payload_format_disclosed"])
        self.assertEqual(opcode["0xe9"]["case_insensitive_token_occurrences"], 0)

    def test_pinned_init_parses_to_15_groups_and_43_bytes(self) -> None:
        source, header = _source_fixture()

        trace = audit._source_init_trace(source, header)
        flattened = audit._flatten_trace(trace)

        self.assertEqual(trace, audit.EXPECTED_INIT_TRACE)
        self.assertEqual(len(trace), 15)
        self.assertEqual(len(flattened), 43)
        self.assertEqual(
            hashlib.sha256(flattened).hexdigest(),
            audit.capture_audit.GXEPD2_INIT_FLAT_SHA256,
        )

    def test_manual_covers_only_eight_init_opcodes(self) -> None:
        result = audit._init_documentation_cross(
            audit.EXPECTED_INIT_TRACE,
            set(audit.EXPECTED_REGISTER_COMMANDS),
        )

        self.assertEqual(result["formal_register_table_command_groups"], 8)
        self.assertEqual(result["absent_from_formal_register_table_groups"], 7)
        self.assertEqual(result["formal_groups_with_exact_parameter_count"], 7)
        self.assertEqual(result["pwr_source_parameter_count"], 2)
        self.assertEqual(result["pwr_datasheet_parameter_rows"], 6)
        self.assertFalse(result["datasheet_fully_supports_43_byte_init"])
        by_command = {row["command"]: row for row in result["groups"]}
        self.assertEqual(by_command["0x60"]["datasheet_status"], "mtp_default_map_only")
        self.assertEqual(
            by_command["0xe9"]["datasheet_status"],
            "absent_from_public_pdf_register_table",
        )

    def test_fragment_localizes_to_complete_03_and_06_groups(self) -> None:
        public_cross = {
            "flattened_init_cross_check": {
                "maximal_fragment_source_offset": 8,
                "maximal_fragment_capture_offset": 14,
                "longest_common_contiguous_fragment_bytes": 12,
            }
        }

        result = audit._fragment_localization(
            audit.EXPECTED_INIT_TRACE,
            public_cross,
        )

        self.assertEqual(result["fully_covered_source_group_count"], 2)
        self.assertEqual(
            [row["command"] for row in result["overlapped_source_groups"]],
            ["0x03", "0x06"],
        )
        self.assertEqual(result["documented_complete_group_bytes"], 8)
        self.assertEqual(result["undocumented_complete_group_bytes"], 4)
        self.assertFalse(result["capture_dc_or_command_boundaries_recovered"])
        self.assertFalse(result["exact_generator_or_panel_proven"])

    def test_json_canonicalization_is_stable(self) -> None:
        value = {"z": False, "a": ["JD79661AA", 0x20]}
        first = audit._sha256(audit._canonical_bytes(value))
        second = audit._sha256(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
