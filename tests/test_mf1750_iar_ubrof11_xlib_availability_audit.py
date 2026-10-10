from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from tools import mf1750_iar_ubrof11_xlib_availability_audit as audit


def _available_legacy_xlib() -> Path | None:
    configured = os.environ.get("MF1750_IAR_XLIB_PATH")
    candidates = []
    if configured:
        candidates.append(Path(configured))
    candidates.append(
        Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        / "Temp/iar_ew430_6201_xlink_only/component_430_xlink_common/430/bin/xlib.exe"
    )
    for candidate in candidates:
        if not candidate.is_file():
            continue
        payload = candidate.read_bytes()
        if (
            len(payload) == audit.KNOWN_LEGACY_XLIB["size_bytes"]
            and audit._sha256(payload) == audit.KNOWN_LEGACY_XLIB["sha256"]
        ):
            return candidate.resolve()
    return None


class Mf1750IarUbrof11XlibAvailabilityUnitTests(unittest.TestCase):
    def test_version_floor_comparison_is_numeric(self) -> None:
        self.assertTrue(audit._version_at_least("6.3.4.78", "6.3.4.78"))
        self.assertTrue(audit._version_at_least("6.6.2.104", "6.3.4.78"))
        self.assertTrue(audit._version_at_least("10.0.0.1", "6.3.4.78"))
        self.assertFalse(audit._version_at_least("6.1.3.56", "6.3.4.78"))

    def test_explicit_search_root_parser_rejects_ambiguous_input(self) -> None:
        with self.assertRaisesRegex(audit.XlibAvailabilityError, "LABEL=PATH"):
            audit.parse_search_root("missing-separator")
        parsed = audit.parse_search_root("cache=.")
        self.assertEqual(parsed.label, "cache")
        self.assertTrue(parsed.path.is_absolute())

    def test_unknown_local_candidate_is_hashed_but_never_executed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            candidate = root / "nested" / "XLIB.EXE"
            candidate.parent.mkdir()
            candidate.write_bytes(b"unattested fixture")
            report = audit.scan_local_candidates([audit.SearchRoot("fixture", root)])

        self.assertEqual(report["candidate_count"], 1)
        row = report["candidates"][0]
        self.assertEqual(row["relative_path"], "nested/XLIB.EXE")
        self.assertEqual(row["attestation"], "UNATTESTED_IDENTITY_NOT_EXECUTED")
        self.assertFalse(row["execution_permitted_by_this_audit"])
        self.assertFalse(report["unknown_candidates_were_executed"])
        self.assertTrue(report["all_search_roots_fully_readable"])

    def test_official_release_note_parser_pins_exact_fix_semantics(self) -> None:
        payload = b"""
        <h4>XLINK 6.3.4.78 - 2015-Sep-22</h4>
        <p>EW25659 XLIB does not correctly handle UBROF-files that contain
        stack usage information and terminates with an \"Unknown tag: E2\"
        error message.</p>
        <p>XLIB supports UBROF 11 starting with version 6.0.0.46.</p>
        """
        row = audit.parse_xlink_release_notes(payload)
        self.assertEqual(row["EW25659_fixed_in"], "6.3.4.78")
        self.assertTrue(row["fix_heading_present"])
        self.assertTrue(row["unknown_E2_present"])

    def test_update_page_parser_proves_anonymous_href_absence(self) -> None:
        index = (
            b'<a href="?key=0123456789abcdef0123456789abcdef&amp;version=6.40">6.40</a>'
        )
        version_url = audit.parse_update_index_for_640(
            "https://updates.iar.com/?product=EW430", index
        )
        self.assertIn("version=6.40", version_url)
        page = b"""
        <p class="title">Install EW430 6.40</p>
        <p>IAR Embedded Workbench for Texas Instruments MSP430 version 6.40.1</p>
        <a id="download" class="aspNetDisabled">Download installer for Windows</a>
        <p>A valid Support and Update Agreement is required for this download.</p>
        """
        row = audit.parse_ew430_640_update_page(page)
        self.assertFalse(row["anonymous_download_href_present"])
        self.assertTrue(row["download_anchor_server_disabled"])
        self.assertTrue(row["valid_SUA_explicitly_required"])

    def test_trial_and_registration_parsers_require_user_registration(self) -> None:
        trial = b"""
        <p>Evaluation versions are available for 14 days.</p>
        <h3>IAR Embedded Workbench for MSP430</h3>
        <a href="https://register.iar.com/eval?source=iar.com&amp;lms_name=LMS2&amp;features=430.EW.LINKER%2C1.13&amp;lang=en">Download now</a>
        <h3>IAR Embedded Workbench for AVR</h3>
        """
        trial_row = audit.parse_trial_page(trial)
        self.assertTrue(trial_row["registration_required"])
        self.assertTrue(trial_row["msp430_linker_feature_present"])
        registration = b"""
        Register for Evaluation
        IAR Embedded Workbench for MSP430, v. 8.10, Evaluation version
        First name Last name Email Phone Company Country Industry
        Please describe your project Software Licence Agreement
        """
        registration_row = audit.parse_registration_page(registration)
        self.assertTrue(registration_row["required_identity_or_project_fields_present"])
        self.assertFalse(registration_row["form_submission_performed"])

    def test_ti_public_route_stops_at_iar_6201(self) -> None:
        payload = (
            "IAR Embedded Workbench KickStart (IAR 6.20.1 / WIN) "
            "01.00.0B.0A "
            f'<a href="{audit.EXPECTED_TI_ARCHIVE_URL}">download</a>'
        ).encode()
        row = audit.parse_ti_slac050_page(payload)
        self.assertEqual(row["latest_listed_IAR_product_version"], "6.20.1")
        self.assertFalse(row["contains_fixed_or_newer_XLIB"])
        self.assertFalse(row["archive_downloaded_by_this_audit"])


@unittest.skipUnless(
    _available_legacy_xlib() is not None,
    "identity-pinned official XLIB 6.1.3.56 is not locally available",
)
class Mf1750IarUbrof11XlibAvailabilityIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.xlib = _available_legacy_xlib()
        assert cls.xlib is not None
        cls.report = audit.build_report(
            search_roots=[audit.SearchRoot("legacy_bin", cls.xlib.parent)],
            legacy_xlib=cls.xlib,
            network_evidence={
                "network_accessed": False,
                "semantic_validation_performed": False,
            },
        )

    def test_original_three_objects_remain_native_E2_boundary(self) -> None:
        boundary = self.report["known_legacy_XLIB_boundary"]
        self.assertTrue(boundary["performed"])
        self.assertEqual(
            sum(
                row["paired_external_index_call_sites"]
                for row in boundary["objects"].values()
            ),
            52,
        )
        for row in boundary["objects"].values():
            self.assertEqual(
                row["LIST_EXTERNALS_status"], "UNSUPPORTED_STACK_USAGE_TAG_E2"
            )
            self.assertEqual(
                row["LIST_ENTRIES_status"], "UNSUPPORTED_STACK_USAGE_TAG_E2"
            )
            self.assertFalse(row["empty_symbol_table_inferred"])

    def test_report_closes_search_scope_but_not_UBROF11_tables(self) -> None:
        adjudication = self.report["adjudication"]
        self.assertEqual(
            adjudication["verdict"],
            "NO_UPDATED_OFFICIAL_XLIB_IN_READABLE_LOCAL_OR_ANONYMOUS_PUBLIC_SCOPE",
        )
        self.assertFalse(
            adjudication["official_fixed_or_newer_XLIB_found_and_identity_pinned"]
        )
        self.assertFalse(adjudication["three_original_UBROF11_objects_natively_parsed"])
        gap = adjudication["minimum_missing_artifact"]
        self.assertEqual(gap["version_floor"], "6.3.4.78")
        self.assertFalse(gap["installation_required_for_validation"])
        self.assertTrue(gap["user_registration_or_valid_SUA_currently_required"])

    def test_safety_scope_is_zero_hardware_and_zero_unknown_execution(self) -> None:
        scope = self.report["scope"]
        for key in (
            "hardware_accessed",
            "serial_or_COM_accessed",
            "device_network_accessed",
            "firmware_written_or_flashed",
            "visible_refresh_requested",
            "software_installed",
            "unknown_binary_executed",
            "credentials_or_personal_data_submitted",
        ):
            self.assertFalse(scope[key])
        self.assertEqual(
            self.report["local_search"]["attested_fixed_or_newer_candidate_count"], 0
        )


if __name__ == "__main__":
    unittest.main()
