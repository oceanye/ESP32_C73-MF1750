from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools import mf1750_iar_temperature_selector_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]


def _available_xlink() -> Path | None:
    configured = os.environ.get("MF1750_IAR_XLINK_PATH")
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
            / "xlink.exe"
        )
    return next((path for path in candidates if path.is_file()), None)


def _available_objdump() -> Path | None:
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


AVAILABLE_XLINK = _available_xlink()
AVAILABLE_OBJDUMP = _available_objdump()


def _hex_record(address: int, record_type: int, data: bytes = b"") -> bytes:
    body = bytes((len(data), (address >> 8) & 0xFF, address & 0xFF, record_type)) + data
    checksum = (-sum(body)) & 0xFF
    return b":" + (body + bytes((checksum,))).hex().upper().encode("ascii") + b"\n"


class Mf1750IarTemperatureSelectorParserTests(unittest.TestCase):
    def test_intel_hex_segment_and_linear_addresses_are_validated(self) -> None:
        payload = b"".join(
            (
                _hex_record(0, 0x02, b"\x10\x00"),
                _hex_record(0x0010, 0x00, b"\xaa\xbb"),
                _hex_record(0, 0x04, b"\x00\x02"),
                _hex_record(0x0020, 0x00, b"\xcc"),
                _hex_record(0, 0x01),
            )
        )
        image = audit.parse_intel_hex(payload)
        self.assertEqual(
            image.memory,
            {0x10010: 0xAA, 0x10011: 0xBB, 0x20020: 0xCC},
        )
        self.assertEqual(image.record_count, 5)
        self.assertEqual(image.data_record_count, 2)
        self.assertEqual(image.extended_segment_records, 1)
        self.assertEqual(image.extended_linear_records, 1)

    def test_intel_hex_checksum_overlap_eof_and_type_fail_closed(self) -> None:
        valid = _hex_record(0, 0x00, b"\x01") + _hex_record(0, 0x01)
        corrupted = bytearray(valid)
        corrupted[9] = ord("0") if corrupted[9] != ord("0") else ord("1")
        with self.assertRaisesRegex(audit.TemperatureSelectorAuditError, "checksum"):
            audit.parse_intel_hex(bytes(corrupted))

        overlap = (
            _hex_record(0, 0x00, b"\x01")
            + _hex_record(0, 0x00, b"\x02")
            + _hex_record(0, 0x01)
        )
        with self.assertRaisesRegex(audit.TemperatureSelectorAuditError, "overlap"):
            audit.parse_intel_hex(overlap)
        with self.assertRaisesRegex(audit.TemperatureSelectorAuditError, "EOF"):
            audit.parse_intel_hex(_hex_record(0, 0x00, b"\x01"))
        with self.assertRaisesRegex(audit.TemperatureSelectorAuditError, "type 0x03"):
            audit.parse_intel_hex(_hex_record(0, 0x03, b"\x00\x00\x00\x00"))

    def test_objdump_tab_parser_excludes_comment_from_semantic_instruction(
        self,
    ) -> None:
        payload = b"""
Disassembly of section .sec1:
   10044:\t39 40 19 00 \tmov\t#25,\tr9\t;#0x0019
   10048:\tb1 13 22 02 \tcalla\t#66082\t\t;0x10222
   1004c:\t23 02 
"""
        rows = audit.parse_objdump_instructions(payload)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].address, 0x10044)
        self.assertEqual(rows[0].encoded_bytes, bytes.fromhex("39 40 19 00"))
        self.assertEqual(rows[0].normalized_instruction, "mov #25, r9")
        self.assertEqual(rows[1].normalized_instruction, "calla #66082")
        self.assertTrue(rows[0].stripped_line.startswith("10044:"))

    def test_address_byte_manifest_includes_each_little_endian_address(self) -> None:
        self.assertEqual(
            audit._address_byte_manifest_sha256(
                {0x10000: 0x3B, 0x10001: 0x15, 0x20000: 0xAA}
            ),
            "3b10856507ed08e8a1d3365c322359785616cccd214811ecae234c7b5e6315ce",
        )

    def test_link_contract_is_exact_and_uses_synthetic_externals(self) -> None:
        arguments = audit._link_arguments(Path("out.hex"), Path("E2802.r43"))
        self.assertEqual(
            arguments[:6],
            [
                "-Fintel-extended",
                "-o",
                "out.hex",
                "-cmsp430",
                audit.CODE_PLACEMENT,
                audit.DATA_PLACEMENT,
            ],
        )
        self.assertEqual(arguments[-2:], ["-gUpload_Temperature_LUT", "E2802.r43"])
        definitions = [argument for argument in arguments if argument.startswith("-D")]
        self.assertEqual(len(definitions), 11)
        self.assertIn("-D?Mul32=0xF0020", definitions)
        self.assertIn("-DReadData=0xF0030", definitions)

    @unittest.skipUnless(
        AVAILABLE_XLINK is not None,
        "the identity-pinned official XLINK is not available",
    )
    def test_xlink_identity_mismatch_fails_before_version_invocation(self) -> None:
        assert AVAILABLE_XLINK is not None
        with tempfile.TemporaryDirectory() as temp_dir:
            copied = Path(temp_dir) / "xlink.exe"
            shutil.copyfile(AVAILABLE_XLINK, copied)
            payload = bytearray(copied.read_bytes())
            payload[-1] ^= 1
            copied.write_bytes(payload)
            with self.assertRaisesRegex(
                audit.TemperatureSelectorAuditError, "SHA-256 mismatch"
            ):
                audit._pin_tool(
                    copied,
                    audit.EXPECTED_XLINK,
                    label="XLINK",
                    version_args=[],
                    version_banner=audit.XLINK_VERSION_BANNER,
                    encoding="cp1252",
                )


@unittest.skipUnless(
    AVAILABLE_XLINK is not None and AVAILABLE_OBJDUMP is not None,
    "the identity-pinned XLINK and MSP430 objdump are not both available",
)
class Mf1750IarTemperatureSelectorIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert AVAILABLE_XLINK is not None
        assert AVAILABLE_OBJDUMP is not None
        cls.report = audit.build_report(AVAILABLE_XLINK, AVAILABLE_OBJDUMP)

    def test_tools_sources_and_synthetic_outputs_are_identity_pinned(self) -> None:
        identity = self.report["identity"]
        self.assertEqual(identity["xlink"]["version"], "6.1.3.56")
        self.assertEqual(identity["xlink"]["sha256"], audit.EXPECTED_XLINK["sha256"])
        self.assertEqual(identity["objdump"]["version"], "2.26.20160125")
        self.assertEqual(
            identity["objdump"]["sha256"], audit.EXPECTED_OBJDUMP["sha256"]
        )
        for object_name in ("E2801", "E2802"):
            expected = audit.EXPECTED_LINKS[f"{object_name}.r43"]
            row = self.report["objects"][object_name]
            self.assertEqual(row["source_object"]["sha256"], expected["source_sha256"])
            linked = row["synthetic_linked_image"]
            self.assertEqual(linked["intel_hex_sha256"], expected["intel_hex_sha256"])
            self.assertEqual(
                linked["address_byte_manifest_sha256"],
                expected["address_byte_manifest_sha256"],
            )
            self.assertEqual(linked["function"]["sha256"], expected["function_sha256"])
            self.assertEqual(
                linked["function"]["normalized_disassembly_sha256"],
                expected["normalized_disassembly_sha256"],
            )

    def test_exact_function_ranges_counts_and_hashes_are_reproduced(self) -> None:
        e2801 = self.report["objects"]["E2801"]["synthetic_linked_image"]
        self.assertEqual(e2801["emitted_memory_bytes"], 684)
        self.assertEqual(e2801["emitted_address_start"], "0x10000")
        self.assertEqual(e2801["emitted_address_end_inclusive"], "0x102AB")
        self.assertEqual(e2801["function"]["synthetic_start"], "0x1002E")
        self.assertEqual(e2801["function"]["synthetic_end_inclusive"], "0x10129")
        self.assertEqual(e2801["function"]["instruction_line_count"], 94)
        self.assertEqual(e2801["function"]["normalized_disassembly_bytes"], 3813)

        e2802 = self.report["objects"]["E2802"]["synthetic_linked_image"]
        self.assertEqual(e2802["emitted_memory_bytes"], 472)
        self.assertEqual(e2802["emitted_address_end_inclusive"], "0x101D7")
        self.assertEqual(e2802["function"]["synthetic_start"], "0x10020")
        self.assertEqual(e2802["function"]["synthetic_end_inclusive"], "0x100DF")
        self.assertEqual(e2802["function"]["instruction_line_count"], 77)
        self.assertEqual(e2802["function"]["normalized_disassembly_bytes"], 3078)

    def test_fixed_temperature_selector_and_upload_semantics_are_machine_readable(
        self,
    ) -> None:
        e2801 = self.report["objects"]["E2801"]["semantic_facts"]
        e2802 = self.report["objects"]["E2802"]["semantic_facts"]
        for facts in (e2801, e2802):
            self.assertEqual(facts["selector_temperature_celsius"], 25)
            self.assertEqual(facts["temperature_slot_count"], 30)
            self.assertEqual(facts["match_predicate"], "header[1] <= 25 < header[0]")
            self.assertEqual(facts["matched_slot_bulk_read_bytes"], 2508)
            self.assertEqual(facts["lut0_byte_count"], 799)
            self.assertEqual(facts["lut1_byte_count"], 704)
            self.assertTrue(facts["lut1_is_generated_loop_not_dataBuff"])
            self.assertFalse(facts["current_800_byte_runtime_wrapper_abi_proven"])
        self.assertTrue(e2801["tsc_command_0x40_before_selection"])
        self.assertTrue(e2801["spi_get_data_called"])
        self.assertFalse(e2801["spi_get_data_result_copied_to_selector_register"])
        self.assertFalse(e2802["tsc_command_0x40_before_selection"])
        self.assertFalse(e2802["spi_get_data_called"])
        self.assertTrue(e2801["psr_write_inside_upload"])
        self.assertFalse(e2802["psr_write_inside_upload"])

    def test_report_is_deterministic_metadata_only_and_non_authorizing(self) -> None:
        self.assertEqual(
            self.report["integrity"]["canonical_sha256"],
            "b1a30b5699a1b60231593b9c25547076f5d96c32db7f163fb25b7e10b4f1aed7",
        )
        scope = self.report["scope"]
        for key in (
            "hardware_accessed",
            "serial_or_com_accessed",
            "device_network_accessed",
            "flashed",
            "live_token_or_claim_generated",
            "raw_object_code_emitted",
            "raw_disassembly_emitted",
            "raw_waveform_or_payload_emitted",
        ):
            self.assertFalse(scope[key])
        self.assertEqual(scope["visible_refreshes"], 0)
        boundaries = self.report["evidence_boundaries"]
        self.assertFalse(boundaries["authorizes_live_hardware_action"])
        self.assertFalse(boundaries["current_spd1657_800_byte_abi_proven"])
        self.assertFalse(boundaries["current_dual_controller_loading_contract_proven"])

    def test_cli_emits_no_raw_code_or_disassembly(self) -> None:
        assert AVAILABLE_XLINK is not None
        assert AVAILABLE_OBJDUMP is not None
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.mf1750_iar_temperature_selector_audit",
                "--xlink",
                str(AVAILABLE_XLINK),
                "--objdump",
                str(AVAILABLE_OBJDUMP),
                "--compact",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            timeout=120,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8"))
        stdout = completed.stdout.decode("utf-8")
        self.assertIn(audit.KIND, stdout)
        for forbidden in (
            '"encoded_bytes"',
            '"stripped_line"',
            '"normalized_instruction"',
            '"object_bytes"',
            '"waveform_bytes"',
            '"decoded_payload"',
        ):
            self.assertNotIn(forbidden, stdout)


if __name__ == "__main__":
    unittest.main()
