from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools import mf1750_iar_xlib_external_index_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]


def _available_xlib() -> Path | None:
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
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


class Mf1750IarXlibParserTests(unittest.TestCase):
    def test_ordered_external_table_is_parsed_without_timestamp(self) -> None:
        payload = b"""\
##############################################################################
#     IAR Universal Librarian V6.1.3.56              12/Aug/2026  00:19:31   #
##############################################################################

       1.  Pgm  E2802
             Ext   delay
             Ext   ?Mul32
             Ext   ReadData
"""
        parsed = audit.parse_xlib_symbol_list(payload, expected_kind="Ext")
        self.assertEqual(parsed["module"], "E2802")
        self.assertEqual(parsed["symbols"], ["delay", "?Mul32", "ReadData"])
        self.assertEqual(len(parsed["table_sha256"]), 64)

    def test_entry_and_external_rows_cannot_be_silently_mixed(self) -> None:
        payload = b"""\
IAR Universal Librarian V6.1.3.56
       1.  Pgm  E2802
             Ent   EPD_Init
             Ext   ReadData
"""
        with self.assertRaisesRegex(audit.XlibAuditError, "mixed"):
            audit.parse_xlib_symbol_list(payload, expected_kind="Ent")

    def test_observed_indices_preserve_ambiguity_and_call_count(self) -> None:
        rows = audit._observed_index_rows(
            [
                {"target_id": "0x3", "callee_symbol": "ReadData"},
                {"target_id": "0x3", "callee_symbol": "ReadData"},
                {"target_id": "0x1", "callee_symbol": "delay"},
            ]
        )
        self.assertEqual(
            rows,
            [
                {
                    "external_index": 1,
                    "observed_debug_symbols": ["delay"],
                    "call_count": 1,
                },
                {
                    "external_index": 3,
                    "observed_debug_symbols": ["ReadData"],
                    "call_count": 2,
                },
            ],
        )

    def test_xlib_identity_mismatch_fails_before_invocation(self) -> None:
        xlib = _available_xlib()
        if xlib is None:
            self.skipTest("the identity-pinned official XLIB is not available")
        with tempfile.TemporaryDirectory() as temp_dir:
            copied = Path(temp_dir) / "xlib.exe"
            shutil.copyfile(xlib, copied)
            payload = bytearray(copied.read_bytes())
            payload[-1] ^= 1
            copied.write_bytes(payload)
            with self.assertRaisesRegex(audit.XlibAuditError, "SHA-256 mismatch"):
                audit._pin_xlib(copied)


@unittest.skipUnless(
    _available_xlib() is not None,
    "the identity-pinned official XLIB is not available",
)
class Mf1750IarXlibIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.xlib = _available_xlib()
        assert cls.xlib is not None
        cls.report = audit.build_report(cls.xlib)

    def test_all_29_objects_have_explicit_parse_or_version_boundary(self) -> None:
        self.assertEqual(self.report["schema_version"], 1)
        self.assertEqual(len(self.report["objects"]), 29)
        statuses = {
            name: row["xlib_status"] for name, row in self.report["objects"].items()
        }
        self.assertEqual(
            {
                name
                for name, status in statuses.items()
                if status == "UNSUPPORTED_STACK_USAGE_TAG_E2"
            },
            {"DELAY.r43", "E6_73.r43", "main.r43"},
        )
        self.assertEqual(
            sum(status == "PARSED" for status in statuses.values()),
            26,
        )
        for name in ("DELAY.r43", "E6_73.r43", "main.r43"):
            self.assertFalse(
                self.report["objects"][name]["empty_symbol_table_inferred"]
            )

    def test_349_external_calls_match_and_52_are_not_overclaimed(self) -> None:
        cross_check = self.report["external_index_cross_check"]
        self.assertEqual(cross_check["total_paired_external_index_calls"], 401)
        self.assertEqual(cross_check["official_xlib_verified_calls"], 349)
        self.assertEqual(cross_check["version_boundary_calls"], 52)
        self.assertEqual(cross_check["verified_mismatches"], [])
        self.assertTrue(cross_check["parseable_objects_zero_mismatch"])

    def test_tool_table_manifest_and_report_are_deterministically_pinned(self) -> None:
        identity = self.report["identity"]
        self.assertEqual(
            identity["xlib"]["sha256"],
            "ea11101e1365065c5899dc1db644eb8d6f0ff769abc477119770355d98804284",
        )
        self.assertEqual(
            identity["parsed_external_and_entry_table_manifest_sha256"],
            "40973a7a6b63f11b1b2cbc94e935021da2eb55a427bb1f7e9fc43627d4091413",
        )
        self.assertEqual(
            self.report["integrity"]["canonical_sha256"],
            "6d17001cb79a9c09e367704f2f3945c120ef81d6e358b5ad4af5a4519d579e31",
        )

    def test_read_data_index_is_independently_confirmed_but_provider_is_not(
        self,
    ) -> None:
        targeted = self.report["targeted_adjudication"]
        self.assertEqual(targeted["E2801"]["entry_count"], 50)
        self.assertEqual(targeted["E2802"]["entry_count"], 49)
        self.assertEqual(targeted["E2801"]["external_index_3"], "ReadData")
        self.assertEqual(targeted["E2802"]["external_index_3"], "ReadData")
        self.assertEqual(targeted["E2801"]["ReadData_call_count"], 26)
        self.assertEqual(targeted["E2802"]["ReadData_call_count"], 36)
        self.assertTrue(
            targeted["external_index_3_is_ReadData_independently_confirmed"]
        )
        self.assertFalse(
            targeted["ReadData_provider_or_implementation_location_proven"]
        )
        self.assertFalse(targeted["main_index_2_independently_parsed_by_this_xlib"])
        self.assertFalse(targeted["E6_73_is_provider_proven_by_this_xlib"])

    def test_official_e2_boundary_and_zero_io_are_machine_readable(self) -> None:
        boundary = self.report["official_tool_version_boundary"]
        self.assertEqual(boundary["official_issue"], "EW25659")
        self.assertEqual(boundary["official_fix_version"], "6.3.4.78")
        self.assertFalse(boundary["failure_means_empty_external_or_entry_table"])
        scope = self.report["scope"]
        for key in (
            "hardware_accessed",
            "serial_or_com_accessed",
            "device_network_accessed",
            "flashed",
            "raw_object_code_emitted",
            "raw_waveform_or_payload_emitted",
        ):
            self.assertFalse(scope[key])
        self.assertEqual(scope["visible_refreshes"], 0)

    def test_cli_emits_metadata_only_json(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.mf1750_iar_xlib_external_index_audit",
                "--xlib",
                str(self.xlib),
                "--compact",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8"))
        stdout = completed.stdout.decode("utf-8")
        self.assertIn(audit.KIND, stdout)
        self.assertNotIn('"object_bytes"', stdout)
        self.assertNotIn('"object_code_bytes"', stdout)
        self.assertNotIn("waveform_bytes", stdout)
        self.assertNotIn("decoded_payload", stdout)


if __name__ == "__main__":
    unittest.main()
