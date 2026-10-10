from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools import mf1750_iar_r43_cross_object_graph as graph


REPO_ROOT = Path(__file__).resolve().parents[1]


class Mf1750IarR43CrossObjectGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = graph.build_report()

    def test_all_29_objects_and_both_ubrof_versions_are_identity_pinned(self) -> None:
        self.assertEqual(self.report["schema_version"], 2)
        scope = self.report["scope"]
        self.assertEqual(scope["r43_objects"], 29)
        self.assertEqual(scope["UBROF10_objects"], 26)
        self.assertEqual(scope["UBROF11_objects"], 3)
        self.assertEqual(
            self.report["identity"]["object_manifest_sha256"],
            "08f7b10936d066441c09843ee0345ec3f61ac3735ae521a1d892af100c0ba70d",
        )
        versions = {
            row["name"]: row["ubrof_version_byte"]
            for row in self.report["identity"]["objects"]
        }
        self.assertEqual(
            {name for name, version in versions.items() if version == 11},
            {"DELAY.r43", "E6_73.r43", "main.r43"},
        )

    def test_paired_direct_call_graph_is_not_a_symbol_string_search(self) -> None:
        report = self.report
        self.assertEqual(report["graph"]["direct_call_edges"], 1_786)
        self.assertEqual(len(report["graph"]["target_edges"]), 27)
        self.assertFalse(report["graph"]["all_edges_included"])
        self.assertTrue(
            report["evidence_boundaries"]["symbol_string_is_not_a_call_edge"]
        )
        self.assertFalse(
            report["evidence_boundaries"]["complete_PUBLIC_EXTERN_tables_recovered"]
        )
        e2802 = report["objects"]["E2802.r43"]["observed_records"]
        self.assertEqual(e2802["paired_CALLA_relocations"], 360)
        self.assertEqual(e2802["operator_0x5D_external_index"], 91)
        self.assertEqual(e2802["operator_0x5E_local_section_relative"], 269)

    def test_e2801_and_e2802_init_and_upload_remain_separate(self) -> None:
        legacy = self.report["legacy_E2801_E2802"]
        expected = {
            "E2801.r43": ("0x2E", "0x1E", 66, 4),
            "E2802.r43": ("0x2D", "0x1E", 59, 2),
        }
        caller_names = {
            "EPD_Display_White",
            "EPD_Display_Black",
            "EPD_Display_Yellow",
            "EPD_Display_Red",
            "EPD_Display_line_4bit",
            "EPD_Display_Dot",
            "EPD_Display_Dot_4bit",
        }
        for name, (init, upload, init_refs, upload_refs) in expected.items():
            item = legacy[name]
            self.assertEqual(item["EPD_Init_section"], init)
            self.assertEqual(item["Upload_Temperature_LUT_section"], upload)
            self.assertEqual(item["EPD_Init_dataBuff_source_records"], init_refs)
            self.assertEqual(item["Upload_dataBuff_source_records"], upload_refs)
            self.assertEqual(len(item["direct_upload_callers"]), 7)
            self.assertEqual(
                {
                    caller["caller_symbols"][0]
                    for caller in item["direct_upload_callers"]
                },
                caller_names,
            )
            self.assertFalse(item["EPD_Init_calls_Upload_Temperature_LUT"])
            self.assertFalse(item["common_local_root_reaches_both"])

    def test_dep_output_table_is_distinct_from_direct_xlink_inputs(self) -> None:
        dependency = self.report["dependency_graph"]
        self.assertEqual(dependency["file_version"], 4)
        self.assertEqual(dependency["configuration"], "Debug")
        self.assertEqual(dependency["file_id_base"], 0)
        self.assertEqual(dependency["output_file_table_entry_count"], 60)
        self.assertEqual(
            [
                (row["producer_source"], row["file_id"], row["name"])
                for row in dependency["zero_based_producer_output_checks"]
            ],
            [
                ("$PROJ_DIR$\\E6_73.c", 56, "E6_73.r43"),
                ("$PROJ_DIR$\\DELAY.C", 44, "DELAY.r43"),
                ("$PROJ_DIR$\\main.c", 38, "main.r43"),
            ],
        )
        self.assertEqual(
            [
                (row["file_id"], row["name"])
                for row in dependency["root_xlink_output_rows"]
            ],
            [(51, "C2_Example.d43"), (13, "C2_Example.txt")],
        )
        self.assertEqual(
            [
                (row["file_id"], row["name"])
                for row in dependency["r43_output_table_rows"]
            ],
            [
                (9, "EL073.r43"),
                (11, "HAL_UCS.r43"),
                (23, "HAL_PMM.r43"),
                (32, "dl430xlsfn.r43"),
                (33, "HAL_TLV.r43"),
                (38, "main.r43"),
                (44, "DELAY.r43"),
                (49, "HAL_FLASH.r43"),
                (54, "HAL_PMAP.r43"),
                (56, "E6_73.r43"),
            ],
        )
        self.assertEqual(len(dependency["project_r43_output_table_names"]), 9)
        self.assertEqual(
            [
                (row["file_id"], row["name"], row["classification"])
                for row in dependency["final_d43_direct_xlink_input_rows"]
            ],
            [
                (28, "lnk430f5502.xcl", "toolkit-linker-command-file"),
                (27, "multiplier32.xcl", "toolkit-linker-command-file"),
                (44, "DELAY.r43", "project-r43-object"),
                (56, "E6_73.r43", "project-r43-object"),
                (38, "main.r43", "project-r43-object"),
                (32, "dl430xlsfn.r43", "toolkit-r43-library"),
            ],
        )
        self.assertEqual(
            dependency["final_d43_direct_project_r43_input_names"],
            ["DELAY.r43", "E6_73.r43", "main.r43"],
        )
        self.assertEqual(
            dependency["final_d43_direct_toolkit_r43_input_names"],
            ["dl430xlsfn.r43"],
        )
        self.assertNotIn("E2801.r43", dependency["project_r43_output_table_names"])
        self.assertNotIn("E2802.r43", dependency["project_r43_output_table_names"])

    def test_current_direct_input_root_has_init_but_no_legacy_upload(self) -> None:
        current = self.report["current_delivered_direct_xlink_inputs"]
        self.assertEqual(
            current["project_r43_objects"],
            ["DELAY.r43", "E6_73.r43", "main.r43"],
        )
        self.assertEqual(current["toolkit_r43_objects"], ["dl430xlsfn.r43"])
        self.assertEqual(
            current["root"],
            {"object": "main.r43", "section_id": "0x19", "symbol": "main"},
        )
        edge = current["EPD_Init_edge"]
        self.assertEqual(edge["relocation_file_offset"], "0x5AE4")
        self.assertEqual(edge["relocation_classification"], "external-index")
        self.assertEqual(edge["target_id"], "0x2")
        self.assertEqual(
            current["resolved_EPD_Init_provider"],
            {
                "object": "E6_73.r43",
                "section_id": "0xD",
                "final_d43_symbol_marker_present": True,
            },
        )
        self.assertFalse(
            current["Upload_Temperature_LUT_symbol_name_in_direct_project_r43_inputs"]
        )
        self.assertEqual(current["Upload_Temperature_LUT_direct_call_edges"], [])
        self.assertFalse(current["Upload_Temperature_LUT_marker_in_final_d43"])
        self.assertFalse(current["main_reaches_legacy_runtime_upload"])

    def test_negative_adjudication_is_bounded_and_does_not_merge_orphans(self) -> None:
        adjudication = self.report["adjudication"]
        self.assertEqual(
            adjudication[
                "external_direct_calls_to_Upload_Temperature_LUT_across_all_29"
            ],
            0,
        )
        self.assertTrue(adjudication["legacy_upload_calls_are_local_only"])
        self.assertFalse(
            adjudication[
                "delivered_root_combining_EPD_Init_dataBuff_and_E2801_or_E2802_upload_found"
            ]
        )
        self.assertEqual(
            adjudication["verdict"], "NOT_FOUND_WITHIN_PINNED_DELIVERED_GRAPH"
        )
        boundaries = self.report["evidence_boundaries"]
        self.assertTrue(boundaries["all_29_objects_are_not_one_link_unit"])
        self.assertTrue(boundaries["orphan_objects_have_no_delivered_link_manifest"])
        self.assertTrue(
            boundaries["dependency_output_table_membership_is_not_direct_xlink_input"]
        )
        self.assertTrue(boundaries["toolkit_r43_direct_input_not_parsed"])
        self.assertIn("does not claim", boundaries["why"])

    def test_identity_mismatch_fails_before_offset_interpretation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            copied_root = Path(temp_dir) / "iar"
            shutil.copytree(graph.DEFAULT_IAR_ROOT, copied_root)
            target = copied_root / graph.OBJECT_DIR_REL / "E2802.r43"
            payload = bytearray(target.read_bytes())
            payload[-1] ^= 0x01
            target.write_bytes(payload)
            with self.assertRaisesRegex(graph.GraphError, "E2802.r43 SHA-256 mismatch"):
                graph.build_report(copied_root)

    def test_cli_is_metadata_only_and_can_include_all_edges(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.mf1750_iar_r43_cross_object_graph",
                "--compact",
                "--include-all-edges",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["kind"], graph.KIND)
        self.assertEqual(len(report["graph"]["edges"]), 1_786)
        self.assertTrue(report["graph"]["all_edges_included"])
        self.assertFalse(report["scope"]["hardware_accessed"])
        self.assertFalse(report["scope"]["serial_or_COM_accessed"])
        self.assertFalse(report["scope"]["device_network_accessed"])
        self.assertFalse(report["scope"]["raw_object_bytes_emitted"])
        self.assertNotIn("decoded_payload", completed.stdout)
        self.assertNotIn("waveform_bytes", completed.stdout)


if __name__ == "__main__":
    unittest.main()
