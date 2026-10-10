from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = REPO_ROOT / "tools" / "mf1750_vendor_artifact_hunt.py"
SPEC = importlib.util.spec_from_file_location("mf1750_vendor_artifact_hunt", TOOL_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load vendor artifact hunt")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class Mf1750VendorArtifactHuntTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report()

    def test_two_extracted_trees_are_fully_identity_pinned(self) -> None:
        trees = self.report["trees"]
        self.assertEqual(trees["stm32_vendor"]["files"], 364)
        self.assertEqual(trees["stm32_vendor"]["bytes"], 82_180_051)
        self.assertEqual(
            trees["stm32_vendor"]["manifest_sha256"],
            "5855f19047ab69949eafb14b9a746f2799cd2392a5fd55d5b863d40d687b020d",
        )
        self.assertEqual(trees["iar_vendor"]["files"], 66)
        self.assertEqual(trees["iar_vendor"]["bytes"], 5_631_058)
        self.assertEqual(
            trees["iar_vendor"]["manifest_sha256"],
            "d2d52e3d20e6788eff2c5e16735cb68fdacbc6d05424d5cc980f44282bf0257a",
        )
        self.assertEqual(self.report["scope"]["files"], 430)

    def test_zip_comparison_is_byte_exact_after_gbk_name_canonicalization(
        self,
    ) -> None:
        archive = self.report["archives"]["stm32_zip"]
        self.assertEqual(archive["entries"], 399)
        self.assertEqual(archive["files"], 364)
        self.assertEqual(archive["legacy_gbk_name_normalizations"], 14)
        self.assertEqual(len(archive["normalized_names"]), 14)
        self.assertTrue(archive["all_extracted_file_bytes_match"])
        self.assertEqual(archive["unsafe_paths"], [])
        self.assertEqual(archive["duplicate_canonical_names"], [])
        self.assertEqual(archive["nested_archive_filename_hits"], [])
        self.assertEqual(archive["container_layout"]["trailing_bytes_after_eocd"], 0)

    def test_encrypted_7z_boundary_does_not_overclaim_member_identity(self) -> None:
        archive = self.report["archives"]["iar_7z"]
        self.assertEqual(archive["entries"], 72)
        self.assertEqual(archive["files"], 66)
        self.assertTrue(archive["all_member_names_and_sizes_match_extracted_tree"])
        self.assertTrue(archive["local_reader_reports_encrypted_content"])
        self.assertFalse(archive["member_bytes_compared"])
        self.assertEqual(archive["content_identity_evidence"], "name-and-size-only")
        self.assertIn("do not prove byte identity", archive["evidence_boundary"])

    def test_no_additional_named_mode1_or_800_loader_marker_exists(self) -> None:
        markers = self.report["marker_search"]
        for name in (
            "compile_E5_3Bit_Mode_1",
            "compile_WF_DeCode_SIZE_800",
            "compile_WF_DeCode_SIZE_809",
            "compile_WF_SIZE_799",
        ):
            self.assertEqual(markers[name]["files_with_hits"], 0)
            self.assertEqual(markers[name]["total_occurrences"], 0)

        self.assertEqual(markers["compile_E5_3Bit_Mode_0"]["files_with_hits"], 1)
        self.assertEqual(markers["compile_WF_DeCode_SIZE_544"]["files_with_hits"], 1)
        self.assertEqual(markers["compile_WF_SIZE_535"]["files_with_hits"], 1)
        self.assertFalse(
            self.report["negative_search_boundary"][
                "additional_identity_distinct_named_mode1_or_800_loader_found"
            ]
        )
        self.assertIn(
            "not proof",
            self.report["negative_search_boundary"]["wording"],
        )

    def test_only_loader_library_is_an_unpulled_mode0_member(self) -> None:
        loader = self.report["loader_library"]
        self.assertEqual(
            loader["library"]["sha256"],
            "f6862110533d94b4b0bbc6a864d7b0c936c7402bb83dbd6fc425f0967c8ff06b",
        )
        self.assertEqual(
            loader["member"]["sha256"],
            "92bc03aecc9d19b19ee26c50be5aca94422cc76871dadeab303068ef4da62f1d",
        )
        self.assertEqual(
            loader["compile_macro_values"],
            {"E5_3Bit_Mode": 0, "WF_DeCode_SIZE": 544, "WF_SIZE": 535},
        )
        self.assertEqual(loader["lnp_input_count"], 7)
        self.assertEqual(loader["final_map_axf_loader_marker_hits"], [])
        self.assertEqual(
            loader["classification"], "linker-input-library-member-not-pulled"
        )

    def test_backups_extensionless_file_and_missing_pairings_are_separate(self) -> None:
        provenance = self.report["stm32_artifact_provenance"]
        self.assertEqual(len(provenance["backups"]), 3)
        self.assertTrue(
            all(
                item["classification"] == "backup-editor-only"
                for item in provenance["backups"]
            )
        )
        wf23 = provenance["extensionless_wf23"]
        self.assertEqual(wf23["path"], "Projects/MDK-ARM/12")
        self.assertEqual(wf23["classification"], "editor-only-not-built")
        self.assertFalse(wf23["listed_in_project"])
        self.assertTrue(wf23["editor_state_path_residue_found"])
        for pairing in provenance["missing_profile_pairings"].values():
            self.assertTrue(pairing["referenced"])
            self.assertFalse(pairing["matching_named_file_found"])

    def test_iar_objects_distinguish_output_table_from_direct_xlink_inputs(
        self,
    ) -> None:
        provenance = self.report["iar_object_provenance"]
        self.assertEqual(provenance["all_r43_count"], 29)
        self.assertEqual(len(provenance["project_r43_output_table"]), 9)
        direct = provenance["final_d43_direct_project_r43_inputs"]
        self.assertEqual(
            [Path(item["path"]).name for item in direct],
            ["DELAY.r43", "E6_73.r43", "main.r43"],
        )
        self.assertEqual(len(provenance["delivered_r43_not_direct_inputs"]), 26)
        non_direct_paths = {
            item["path"] for item in provenance["delivered_r43_not_direct_inputs"]
        }
        self.assertIn(
            "E6_73_sample code_V1.2_20250116/Debug/Obj/E2802.r43",
            non_direct_paths,
        )
        semantics = provenance["dependency_semantics"]
        self.assertTrue(
            semantics["output_file_table_is_not_direct_link_input_membership"]
        )
        self.assertEqual(semantics["project_r43_output_table_count"], 9)
        self.assertEqual(semantics["final_d43_direct_project_r43_input_count"], 3)
        self.assertEqual(
            semantics["final_d43_direct_toolkit_r43_inputs"], ["dl430xlsfn.r43"]
        )
        self.assertIn("does not prove", provenance["classification_boundary"])

    def test_legacy_h3_and_final_linkage_keep_cross_version_boundary(self) -> None:
        proofs = self.report["specialized_binary_and_linkage_proofs"]
        h3 = proofs["legacy_h3"]
        self.assertTrue(h3["direct_binary_evidence"])
        self.assertEqual(h3["command_20_count_bytes"], 799)
        self.assertEqual(h3["command_21_value"], "0xFF")
        self.assertEqual(h3["command_21_count_bytes"], 704)
        self.assertFalse(h3["same_version_as_current_stm32_delivery"])
        self.assertFalse(h3["current_project_linkage_proven"])
        self.assertFalse(h3["recovery_closure_proven"])

        final = proofs["delivered_final_images"]
        self.assertEqual(final["axf_map_pairs"], 7)
        self.assertEqual(final["dual_factory_init_image_count"], 5)
        self.assertFalse(final["same_build_800_byte_loader_found"])
        self.assertFalse(final["runtime_lut_upload_in_factory_trace"])

    def test_module_cli_is_metadata_only(self) -> None:
        run = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.mf1750_vendor_artifact_hunt",
                "--compact",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        report = json.loads(run.stdout)
        self.assertEqual(report["kind"], audit.KIND)
        self.assertEqual(report["schema_version"], 2)
        self.assertFalse(report["scope"]["hardware_accessed"])
        self.assertFalse(report["scope"]["serial_or_com_accessed"])
        self.assertFalse(report["scope"]["device_network_accessed"])
        self.assertFalse(report["scope"]["raw_waveform_emitted"])
        self.assertFalse(report["scope"]["key_material_emitted"])
        self.assertNotIn("waveform_bytes", run.stdout)
        self.assertNotIn("decoded_payload", run.stdout)


if __name__ == "__main__":
    unittest.main()
