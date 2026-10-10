from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools import mf1750_iar_project_config_chain_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]


class Mf1750IarProjectConfigChainAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report()

    def test_scope_and_complete_tree_identity_are_pinned(self) -> None:
        report = self.report
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["identity"]["file_count"], 66)
        self.assertEqual(report["identity"]["size_bytes"], 5_631_058)
        self.assertEqual(
            report["identity"]["manifest_sha256"],
            "b1763fff073ec820cef28fd34ff5d6f26e3cd3b09100188df40b930e2c5d60b0",
        )
        scope = report["scope"]
        self.assertTrue(scope["offline_read_only"])
        self.assertFalse(scope["hardware_accessed"])
        self.assertFalse(scope["serial_or_COM_accessed"])
        self.assertFalse(scope["device_network_accessed"])
        self.assertFalse(scope["firmware_written_or_flashed"])
        self.assertFalse(scope["reset_or_refresh_requested"])
        self.assertFalse(scope["physical_action_token_or_claim_created"])

    def test_workspace_and_both_project_configurations_are_separated(self) -> None:
        report = self.report
        self.assertEqual(report["workspace"]["projects"], ["$WS_DIR$\\C2_Example.ewp"])
        project = report["project"]
        self.assertEqual(
            project["project_level_sources"],
            [
                "$PROJ_DIR$\\DELAY.C",
                "$PROJ_DIR$\\E6_73.c",
                "$PROJ_DIR$\\main.c",
            ],
        )
        self.assertEqual(project["exclusion_count"], 0)
        debug = project["configurations"]["Debug"]
        release = project["configurations"]["Release"]
        self.assertEqual(debug["target"], "MSP430F5502\tMSP430F5502")
        self.assertEqual(release["target"], "MSP430F5529\tMSP430F5529")
        self.assertEqual(debug["link"]["primary_output"], "C2_Example.d43")
        self.assertTrue(debug["link"]["generate_extra_output"])
        self.assertEqual(debug["link"]["extra_output"], "C2_Example.txt")
        self.assertEqual(release["link"]["primary_output"], "C2_Example.txt")
        self.assertFalse(release["link"]["generate_extra_output"])
        self.assertEqual(
            report["dependency_and_link_chain"]["Release"]["output_table_entries"],
            0,
        )
        self.assertFalse(report["artifact_inventory"]["Release_directory_present"])

    def test_declared_inventory_and_direct_input_levels_do_not_collapse(self) -> None:
        chain = self.report["configuration_snapshot_vs_generated_Debug_chain"]
        self.assertEqual(chain["project_declared_source_count"], 3)
        self.assertEqual(chain["DEP_project_object_inventory_count"], 9)
        self.assertEqual(chain["DEP_direct_project_object_count"], 3)
        self.assertEqual(
            chain["DEP_inventory_only_not_direct_input"],
            [
                "EL073.r43",
                "HAL_FLASH.r43",
                "HAL_PMAP.r43",
                "HAL_PMM.r43",
                "HAL_TLV.r43",
                "HAL_UCS.r43",
            ],
        )
        debug_chain = self.report["dependency_and_link_chain"]["Debug"]
        self.assertEqual(
            [row["name"] for row in debug_chain["direct_XLINK_inputs"]],
            [
                "lnk430f5502.xcl",
                "multiplier32.xcl",
                "DELAY.r43",
                "E6_73.r43",
                "main.r43",
                "dl430xlsfn.r43",
            ],
        )
        self.assertTrue(
            chain["EWP_Debug_runtime_library_option"].endswith("dl430xsfn.r43")
        )
        self.assertEqual(chain["DEP_direct_runtime_library"], "dl430xlsfn.r43")
        self.assertEqual(
            chain["final_d43_runtime_library_marker_counts"],
            {"dl430xlsfn": 12, "dl430xsfn": 0},
        )

    def test_e6_is_current_init_input_but_runtime_objects_are_orphans(self) -> None:
        rows = self.report["producer_and_provider_ownership"]
        e6 = rows["E6_73.r43"]
        self.assertTrue(e6["project_declared_source_family"])
        self.assertTrue(e6["dependency_output_inventory_member"])
        self.assertTrue(e6["final_d43_direct_project_input"])
        self.assertEqual(e6["object_entry_candidates"]["EPD_Init"], ["0xD"])
        self.assertEqual(e6["object_entry_candidates"]["Upload_Temperature_LUT"], [])
        self.assertEqual(
            e6["provider_status"], "BOUNDED_CURRENT_DEBUG_EPD_INIT_ATTRIBUTION"
        )

        for name in ("E2801.r43", "E2802.r43", "ED020OC4.r43"):
            row = rows[name]
            self.assertFalse(row["project_declared_source_family"])
            self.assertFalse(row["dependency_output_inventory_member"])
            self.assertFalse(row["final_d43_direct_project_input"])
            self.assertTrue(row["object_entry_candidates"]["Upload_Temperature_LUT"])
            self.assertFalse(row["provider_object_proven_for_current_final_upload"])
            self.assertEqual(
                row["provider_status"],
                "ORPHAN_OBJECT_PROVIDER_CANDIDATE_NOT_LINKED",
            )

    def test_debug_ti_txt_is_same_link_extra_output_not_alternate_provider(
        self,
    ) -> None:
        outputs = self.report["final_outputs"]
        self.assertEqual(
            outputs["Debug_d43"]["target_marker_counts"],
            {
                "EPD_Init": 1,
                "Upload_Temperature_LUT": 0,
                "E2801": 0,
                "E2802": 0,
                "E6_73": 10,
            },
        )
        ti_txt = outputs["Debug_extra_TI_TXT"]
        self.assertEqual(ti_txt["format"], "TI-TXT")
        self.assertEqual(ti_txt["total_data_bytes"], 2_002)
        self.assertEqual(ti_txt["reset_vector"], "0xA000")
        self.assertEqual(
            [(row["start_address"], row["size_bytes"]) for row in ti_txt["segments"]],
            [("0xA000", 2_000), ("0xFFFE", 2)],
        )
        self.assertEqual(
            ti_txt["relation"], "EXTRA_OUTPUT_OF_THE_SAME_DEBUG_XLINK_ROOT"
        )
        self.assertFalse(ti_txt["independent_provider_or_link_manifest"])

    def test_ready_made_final_has_v1_1_not_v1_2_object_lineage(self) -> None:
        boundary = self.report["source_revision_boundary"]
        self.assertEqual(
            boundary["final_output_revision_provenance"],
            "V1.1_OBJECT_LINEAGE_NOT_V1.2_REBUILD",
        )
        self.assertEqual(
            boundary["delivered_E6_73_c"]["VDD_cut_debug_statement_occurrences"],
            6,
        )
        linked = boundary["delivered_direct_input_E6_73_r43"]
        self.assertIn("V1.1_20231030", linked["embedded_producer_source"])
        self.assertEqual(linked["VDD_cut_debug_statement_occurrences"], 0)

    def test_source_browser_and_local_xcl_are_not_hidden_link_manifests(self) -> None:
        source_browser = self.report["source_browser_chain"]
        self.assertEqual(
            source_browser["ninja"]["classification"],
            "SOURCE_BROWSER_GRAPH_NOT_FIRMWARE_LINK_GRAPH",
        )
        self.assertEqual(source_browser["pbw"]["record_count"], 3_187)
        self.assertEqual(source_browser["pbw"]["Upload_Temperature_LUT_name_rows"], 0)
        self.assertFalse(source_browser["pbw"]["E2801_or_E2802_marker_present"])
        linf = source_browser["auxiliary"]["pbd_linf"]
        self.assertEqual(
            linf["aggregated_names"],
            ["C2_Example.pbd", "DELAY.pbi", "E6_73.pbi", "main.pbi"],
        )
        self.assertFalse(linf["E2801_or_E2802_aggregated"])
        inventory = self.report["artifact_inventory"]
        self.assertEqual(len(inventory["local_xcl_files"]), 7)
        self.assertEqual(inventory["local_linker_response_xcl"], [])
        self.assertEqual(inventory["map_or_listing_files"], [])
        self.assertTrue(inventory["Debug_List_directory_empty"])

    def test_negative_adjudication_remains_bounded(self) -> None:
        adjudication = self.report["adjudication"]
        self.assertTrue(adjudication["current_Debug_main_root_present"])
        self.assertTrue(
            adjudication["current_Debug_E6_73_EPD_Init_attribution_supported"]
        )
        self.assertFalse(adjudication["current_Debug_Upload_Temperature_LUT_present"])
        self.assertFalse(adjudication["E2801_or_E2802_directly_linked"])
        self.assertFalse(
            adjudication[
                "final_linked_root_combining_main_or_EPD_Init_with_Upload_Temperature_LUT_found"
            ]
        )
        self.assertEqual(
            adjudication["verdict"],
            "NO_FINAL_LINKED_ROOT_TO_RUNTIME_UPLOAD_IN_DELIVERED_CONFIGURATIONS",
        )
        boundaries = self.report["evidence_boundaries"]
        self.assertFalse(boundaries["project_declaration_is_link_proof"])
        self.assertFalse(
            boundaries["dependency_output_inventory_is_direct_input_proof"]
        )
        self.assertFalse(boundaries["provider_candidate_name_join_is_final_link_proof"])

    def test_tree_identity_change_fails_before_configuration_interpretation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            copied_root = Path(temp_dir) / "iar"
            shutil.copytree(audit.DEFAULT_IAR_ROOT, copied_root)
            project = copied_root / "C2_Example.ewp"
            project.write_bytes(project.read_bytes() + b"\n")
            with self.assertRaisesRegex(
                audit.ProjectChainError,
                "IAR project (byte count|tree manifest) changed",
            ):
                audit.build_report(copied_root)

    def test_cli_emits_metadata_only_json(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.mf1750_iar_project_config_chain_audit",
                "--compact",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["kind"], audit.KIND)
        self.assertFalse(report["scope"]["raw_object_or_firmware_bytes_emitted"])
        self.assertNotIn("waveform_bytes", completed.stdout)
        self.assertNotIn("decoded_payload", completed.stdout)


if __name__ == "__main__":
    unittest.main()
