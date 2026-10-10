from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from tools import mf1750_iar_xlib_provider_graph as provider_graph


REPO_ROOT = Path(__file__).resolve().parents[1]
STORED_REPORT = (
    REPO_ROOT
    / ".test-output"
    / "offline"
    / "mf1750_iar_xlib_provider_graph_20260812.json"
)


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


class Mf1750IarXlibProviderGraphUnitTests(unittest.TestCase):
    def test_candidate_classification_never_says_resolved(self) -> None:
        self.assertEqual(
            provider_graph._candidate_classification(0),
            "NONE_IN_26_XLIB_PARSEABLE_OBJECTS",
        )
        self.assertEqual(
            provider_graph._candidate_classification(1),
            "UNIQUE_WITHIN_26_XLIB_PARSEABLE_OBJECTS",
        )
        self.assertEqual(
            provider_graph._candidate_classification(2),
            "AMBIGUOUS_WITHIN_26_XLIB_PARSEABLE_OBJECTS",
        )
        with self.assertRaisesRegex(
            provider_graph.ProviderGraphError, "cannot be negative"
        ):
            provider_graph._candidate_classification(-1)

    def test_entry_index_preserves_all_exact_name_candidates(self) -> None:
        index = provider_graph._entry_table_index(
            {
                "z.r43": ["EPD_Init", "only_z"],
                "A.r43": ["EPD_Init", "only_a"],
            }
        )
        self.assertEqual(index["EPD_Init"], ["A.r43", "z.r43"])
        self.assertEqual(index["only_a"], ["A.r43"])
        self.assertNotIn("provider", index)


@unittest.skipUnless(
    _available_xlib() is not None,
    "the identity-pinned official XLIB is not available",
)
class Mf1750IarXlibProviderGraphIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.xlib = _available_xlib()
        assert cls.xlib is not None
        cls.report = provider_graph.build_report(cls.xlib)

    def test_all_external_sites_are_grouped_without_erasing_e2_boundary(
        self,
    ) -> None:
        report = self.report
        self.assertEqual(report["schema_version"], 1)
        graph = report["external_provider_candidate_graph"]
        self.assertEqual(graph["external_call_groups"], 68)
        self.assertEqual(graph["external_call_sites"], 401)
        self.assertEqual(graph["official_xlib_verified_groups"], 58)
        self.assertEqual(graph["official_xlib_verified_call_sites"], 349)
        self.assertEqual(graph["version_boundary_groups"], 10)
        self.assertEqual(graph["version_boundary_call_sites"], 52)
        self.assertEqual(
            graph["groups_with_version_boundary_observed_definition_candidates"], 16
        )
        self.assertEqual(
            graph["call_sites_with_version_boundary_observed_definition_candidates"],
            235,
        )
        self.assertEqual(graph["external_provider_object_edges_proven"], 0)
        self.assertEqual(
            report["official_tool_boundary"]["unsupported_objects"],
            ["DELAY.r43", "E6_73.r43", "main.r43"],
        )
        self.assertFalse(
            report["official_tool_boundary"]["unsupported_tables_treated_as_empty"]
        )
        self.assertFalse(report["official_tool_boundary"]["transformed_copies_used"])

    def test_provider_candidate_counts_are_exact_but_not_link_resolution(
        self,
    ) -> None:
        graph = self.report["external_provider_candidate_graph"]
        self.assertEqual(
            graph["candidate_classification_counts"],
            {
                "NONE_IN_26_XLIB_PARSEABLE_OBJECTS": {
                    "groups": 24,
                    "call_sites": 351,
                },
                "UNIQUE_WITHIN_26_XLIB_PARSEABLE_OBJECTS": {
                    "groups": 38,
                    "call_sites": 43,
                },
                "AMBIGUOUS_WITHIN_26_XLIB_PARSEABLE_OBJECTS": {
                    "groups": 6,
                    "call_sites": 7,
                },
            },
        )
        self.assertTrue(
            all(not row["provider_object_proven"] for row in graph["candidate_rows"])
        )
        usb_init = next(
            row
            for row in graph["candidate_rows"]
            if row["caller_object"] == "usb.r43"
            and row["observed_debug_symbol"] == "USB_initMemcpy"
        )
        self.assertEqual(
            usb_init["official_xlib_entry_provider_candidates"], ["dma.r43"]
        )
        self.assertEqual(
            usb_init["official_candidate_classification"],
            "UNIQUE_WITHIN_26_XLIB_PARSEABLE_OBJECTS",
        )
        self.assertFalse(usb_init["provider_object_proven"])

    def test_legacy_init_and_upload_entries_still_have_separate_local_roots(
        self,
    ) -> None:
        target = self.report["target_chain_adjudication"]
        self.assertEqual(
            [
                row["object"]
                for row in target[
                    "objects_with_official_entries_for_both_EPD_Init_and_upload"
                ]
            ],
            ["E2801.r43", "E2802.r43", "ED020OC4.r43"],
        )
        self.assertTrue(
            all(
                not row["EPD_Init_reaches_Upload_Temperature_LUT_locally"]
                for row in target[
                    "objects_with_official_entries_for_both_EPD_Init_and_upload"
                ]
            )
        )
        for object_name, init_section in (
            ("E2801.r43", "0x2E"),
            ("E2802.r43", "0x2D"),
        ):
            row = target["legacy_objects"][object_name]
            self.assertTrue(row["official_xlib_entries_confirm_both_targets"])
            self.assertEqual(row["EPD_Init_section"], init_section)
            self.assertEqual(row["Upload_Temperature_LUT_section"], "0x1E")
            self.assertFalse(row["EPD_Init_reaches_Upload_Temperature_LUT_locally"])
            self.assertEqual(row["local_root_display_to_upload_edge_count"], 7)

    def test_main_name_matched_legacy_paths_are_candidates_not_root_proof(
        self,
    ) -> None:
        target = self.report["target_chain_adjudication"]
        self.assertEqual(target["main_to_legacy_upload_candidate_path_count"], 8)
        self.assertEqual(target["main_to_legacy_upload_candidate_call_site_weight"], 10)
        self.assertTrue(
            all(
                row["main_symbol_evidence"]
                == "PAIRED_DEBUG_SOURCE_ONLY_XLIB_E2_VERSION_BOUNDARY"
                and row["provider_selection_proven"] is False
                and row["compatible_with_current_final_d43_direct_inputs"] is False
                for row in target["main_to_legacy_upload_name_matched_candidate_paths"]
            )
        )
        self.assertFalse(target["candidate_paths_are_proven_linked_paths"])
        self.assertFalse(target["main_to_EPD_Init_to_upload_candidate_path_found"])
        current = target["current_final_d43"]
        self.assertEqual(
            current["direct_project_r43_inputs"],
            ["DELAY.r43", "E6_73.r43", "main.r43"],
        )
        self.assertEqual(
            current["E6_73_EPD_Init_observed_definition_candidate"],
            {"object": "E6_73.r43", "section_id": "0xD"},
        )
        self.assertFalse(current["E6_73_provider_is_officially_resolved_by_this_xlib"])
        self.assertEqual(current["main_to_E6_73_candidate_edge_groups"], 7)
        self.assertEqual(current["main_to_E6_73_candidate_call_sites"], 8)
        self.assertEqual(
            {
                row["observed_debug_symbol"]
                for row in current["main_to_E6_73_observed_definition_candidate_edges"]
            },
            {"EPD_Init", *provider_graph.MAIN_DISPLAY_SYMBOLS},
        )
        self.assertIsNone(current["E6_73_observed_Upload_Temperature_LUT_section"])
        self.assertFalse(current["E2801_or_E2802_is_a_direct_input"])
        self.assertFalse(current["Upload_Temperature_LUT_marker_present"])

    def test_negative_root_verdict_is_explicitly_bounded(self) -> None:
        target = self.report["target_chain_adjudication"]
        self.assertEqual(target["external_calls_to_exact_Upload_Temperature_LUT"], 0)
        self.assertFalse(
            target["proven_main_or_EPD_Init_root_to_E2801_or_E2802_upload"]
        )
        self.assertEqual(
            target["verdict"],
            "NOT_FOUND_WITHIN_OFFICIAL_XLIB_TABLES_AND_PINNED_LINK_MEMBERSHIP",
        )
        read_data = target["legacy_ReadData_external_dependencies"]
        self.assertEqual(read_data["E2801.r43"]["call_site_count"], 26)
        self.assertEqual(read_data["E2802.r43"]["call_site_count"], 36)
        self.assertTrue(
            all(
                not row["provider_candidates_in_29_delivered_object_evidence"]
                and not row["provider_object_or_transport_proven"]
                for row in read_data.values()
            )
        )
        boundaries = self.report["evidence_boundaries"]
        self.assertFalse(
            boundaries["matching_EXTERNAL_and_ENTRY_names_prove_link_selection"]
        )
        self.assertFalse(
            boundaries["unique_candidate_within_26_parseable_objects_proves_provider"]
        )
        self.assertFalse(boundaries["all_29_objects_are_one_link_unit"])
        self.assertFalse(boundaries["toolkit_library_symbols_parsed"])
        self.assertFalse(boundaries["authorizes_hardware_or_visible_refresh"])

    def test_report_identity_and_zero_io_contract_are_machine_readable(self) -> None:
        identity = self.report["identity"]
        self.assertEqual(
            identity["xlib"]["sha256"],
            "ea11101e1365065c5899dc1db644eb8d6f0ff769abc477119770355d98804284",
        )
        self.assertEqual(
            identity["parsed_external_and_entry_table_manifest_sha256"],
            "40973a7a6b63f11b1b2cbc94e935021da2eb55a427bb1f7e9fc43627d4091413",
        )
        scope = self.report["scope"]
        for key in (
            "hardware_accessed",
            "serial_or_com_accessed",
            "device_network_accessed",
            "firmware_written_or_flashed",
            "live_token_or_claim_generated",
            "raw_object_code_emitted",
            "raw_disassembly_emitted",
            "raw_lut_waveform_key_or_plaintext_emitted",
        ):
            self.assertFalse(scope[key])
        self.assertEqual(scope["visible_refreshes"], 0)
        self.assertEqual(
            self.report["integrity"]["canonical_sha256"],
            "de40c90bedf91c0b518923e3e0718e46e28f444b473397db6cb7f7aca43bfa66",
        )

    def test_stored_metadata_report_is_exactly_reproducible(self) -> None:
        payload = STORED_REPORT.read_bytes()
        self.assertEqual(len(payload), 180_610)
        self.assertEqual(
            hashlib.sha256(payload).hexdigest(),
            "9f4ab28cc4abb96fcd55b7f3e287014a64eb2d30089cd433fee0046ab0e23221",
        )
        self.assertEqual(json.loads(payload.decode("utf-8")), self.report)

    def test_cli_emits_metadata_only_json(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.mf1750_iar_xlib_provider_graph",
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
        report = json.loads(stdout)
        self.assertEqual(report["kind"], provider_graph.KIND)
        self.assertNotIn('"object_bytes"', stdout)
        self.assertNotIn('"object_code_bytes"', stdout)
        self.assertNotIn('"raw_waveform"', stdout)
        self.assertNotIn('"plaintext_bytes"', stdout)
        self.assertFalse(
            report["evidence_boundaries"]["authorizes_hardware_or_visible_refresh"]
        )


if __name__ == "__main__":
    unittest.main()
