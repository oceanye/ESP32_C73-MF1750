from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools import mf1750_armcc_mode1_residual_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class ArmccMode1ResidualAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report()

    def test_config_and_dependency_snapshot_have_no_mode1_selector(self) -> None:
        project = self.report["project_and_options"]
        self.assertEqual(len(project["uvprojx_targets"]), 1)
        target = project["uvprojx_targets"][0]
        self.assertEqual(target["name"], "USART")
        self.assertEqual(target["output_name"], "jiaxian-M009F-T_OQC_YX")
        self.assertEqual(target["defines"], ["STM32F103xE", "USE_HAL_DRIVER"])
        self.assertEqual(target["file_records"], 36)
        self.assertEqual(
            target["library_references"],
            ["../../lib/eload_3bits_M3_E2802_20251229.lib"],
        )
        self.assertEqual(target["nonempty_scatter_file_overrides"], [])

        options = project["uvoptx_targets"]
        self.assertEqual(len(options), 1)
        self.assertTrue(options[0]["is_current_target"])
        self.assertEqual(options[0]["library_references"], target["library_references"])

        dependency = self.report["keil_dependency_snapshot"]
        self.assertEqual(dependency["project"], "atk_f103")
        self.assertEqual(dependency["target"], "USART")
        self.assertEqual(dependency["file_records"], 36)
        self.assertEqual(dependency["include_records"], 2001)
        self.assertEqual(
            dependency["compile_defines"],
            [
                "STM32F103xE",
                "STM32F10X_HD",
                "USE_HAL_DRIVER",
                '__UVISION_VERSION="533"',
            ],
        )
        self.assertEqual(len(dependency["library_records"]), 1)
        self.assertEqual(dependency["library_records"][0]["compiler_flags"], "")
        self.assertFalse(dependency["loader_source_record_present"])
        self.assertTrue(dependency["wf20_include_record_present"])
        self.assertFalse(dependency["wf23_include_record_present"])

    def test_single_prebuilt_library_has_one_mode0_object_and_no_source(self) -> None:
        library = self.report["arm_archive"]
        self.assertEqual(library["ar_records"], 3)
        self.assertEqual(len(library["object_members"]), 1)
        self.assertEqual(library["object_members"][0]["name"], "eload_20250305b1.o")
        self.assertEqual(
            library["object_members"][0]["sha256"],
            "92bc03aecc9d19b19ee26c50be5aca94422cc76871dadeab303068ef4da62f1d",
        )
        self.assertEqual(library["loadwf_named_public_symbols"], ["loadWF"])
        self.assertEqual(library["retained_source_macros"]["E5_3Bit_Mode"], "0")
        self.assertEqual(library["retained_source_macros"]["WF_DeCode_SIZE"], "544")
        self.assertEqual(library["retained_source_macros"]["WF_SIZE"], "535")
        self.assertEqual(library["compiler"], "ARM Compiler 5.06 update 3 (build 300)")
        self.assertTrue(library["compile_cpu_cortex_m3_marker_present"])
        self.assertTrue(library["compile_cpu_lpc54606_define_present"])
        self.assertFalse(library["source_delivered"])
        self.assertTrue(library["prebuilt_object_not_recompiled_by_stm32_project"])

    def test_multiencoding_scan_finds_only_three_mode0_bindings(self) -> None:
        scan = self.report["multiencoding_mode_value_scan"]
        self.assertEqual(scan["files_checked"], 430)
        self.assertFalse(scan["mode1_or_800_or_799_value_binding_found"])
        expected = {
            "E5_3Bit_Mode": "0",
            "WF_DeCode_SIZE": "544",
            "WF_SIZE": "535",
        }
        for name, expected_value in expected.items():
            values = scan["bindings"][name]["values"]
            self.assertEqual(set(values), {expected_value})
            row = values[expected_value]
            self.assertEqual(row["occurrences"], 1)
            self.assertEqual(len(row["hits"]), 1)
            self.assertEqual(
                row["hits"][0]["path"],
                "lib/eload_3bits_M3_E2802_20251229.lib",
            )
            self.assertEqual(row["hits"][0]["encoding"], "ascii")

    def test_all_lnp_files_name_same_library_but_no_final_pulls_it(self) -> None:
        chain = self.report["output_link_chain"]
        self.assertEqual(chain["lnp_count"], 7)
        self.assertTrue(chain["all_lnp_input_lists_identical"])
        self.assertEqual(
            chain["normalized_input_list_sha256"],
            "a69d3bb82981cf53126de21188bbe97c557d254a5051b19ce9c0324722c0c2aa",
        )
        for row in chain["lnp_files"]:
            self.assertEqual(row["link_inputs"], 35)
            self.assertEqual(row["object_inputs"], 34)
            self.assertEqual(
                row["library_inputs"],
                ["../../lib/eload_3bits_m3_e2802_20251229.lib"],
            )
        self.assertEqual(chain["scatter_count"], 7)
        self.assertEqual(
            chain["unique_scatter_sha256"],
            ["aa8b6238aa88b9a119d016d39016752f428eed61068b18af3148795b842c6e9c"],
        )
        self.assertEqual(chain["map_files"], 7)
        self.assertEqual(chain["axf_files"], 7)
        self.assertEqual(chain["map_axf_loader_or_mode_marker_hits"], [])
        self.assertTrue(chain["current_output_pair_present"])
        self.assertEqual(
            len(chain["output_basenames_not_declared_by_current_project_snapshot"]),
            6,
        )
        self.assertFalse(chain["older_output_name_is_alternate_target_or_mode_proven"])

    def test_cleanup_editor_and_capture_residue_stay_bounded(self) -> None:
        cleanup = self.report["cleanup_and_temp_residue"]
        counts = cleanup["cleanup_target_suffix_counts"]
        self.assertEqual(counts[".bak"], 3)
        self.assertEqual(counts[".tmp"], 0)
        self.assertEqual(counts[".lnp"], 7)
        self.assertEqual(counts[".axf"], 7)
        self.assertEqual(counts[".map"], 7)
        self.assertEqual(counts[".administrator"], 1)
        self.assertEqual(cleanup["generic_temp_or_old_filename_hits"], [])
        self.assertTrue(cleanup["residues_are_present_in_original_zip"])

        editor = self.report["editor_residue"]
        markers = {
            row["project_tail"]: row
            for row in editor["external_or_older_project_path_markers"]
        }
        self.assertEqual(markers["REG-API-FOG"]["path_records"], 2)
        self.assertEqual(markers["WF-JD79661-128X296"]["path_records"], 5)
        self.assertFalse(
            markers["REG-API-FOG"]["matching_delivered_project_tree_found"]
        )
        self.assertFalse(
            markers["WF-JD79661-128X296"]["matching_delivered_project_tree_found"]
        )
        self.assertEqual(
            editor["extensionless_editor_artifact"]["classification"],
            "EDITOR_ONLY_NOT_BUILT",
        )

        capture = self.report["spi_analyzer_export"]
        self.assertEqual(capture["rows"], 12_722)
        self.assertTrue(capture["packet_ids_are_contiguous_zero_based"])
        self.assertEqual(capture["miso_unique_values"], [0])
        self.assertTrue(all(capture["packet_id_rows_named_like_lut_sizes"].values()))
        self.assertTrue(
            capture["those_decimal_values_are_packet_indices_not_declared_lengths"]
        )
        self.assertFalse(capture["chip_select_column_present"])
        self.assertFalse(capture["data_command_column_present"])
        self.assertFalse(capture["transaction_boundaries_proven"])
        self.assertFalse(capture["filename_to_editor_project_provenance_binding"])
        self.assertFalse(capture["proves_799_or_1503_plus_704_loader_contract"])

    def test_legacy_iar_constants_are_not_promoted_to_current_armcc(self) -> None:
        legacy = self.report["legacy_iar_1503_704_boundary"]
        self.assertEqual(legacy["resident_constants"]["DATA0_bytes"], 1503)
        self.assertEqual(legacy["resident_constants"]["DATA1_bytes"], 704)
        self.assertFalse(
            legacy["resident_constants"]["DATA1_referenced_by_active_upload_path"]
        )
        self.assertEqual(
            legacy["active_legacy_upload_transactions"],
            [
                {"command": "0x20", "parameter_bytes": 799},
                {"command": "0x21", "parameter_bytes": 704},
            ],
        )
        self.assertFalse(legacy["direct_final_d43_input"])
        self.assertFalse(legacy["same_generation_as_current_armcc_loader"])
        self.assertFalse(legacy["can_uniquely_prove_current_mode1_contract"])
        self.assertFalse(legacy["1503_and_704_are_armcc_mode1_macro_values"])

    def test_integrity_cli_and_safety_are_metadata_only(self) -> None:
        report = dict(self.report)
        canonical = report.pop("report_canonical_sha256")
        self.assertEqual(
            canonical, hashlib.sha256(_canonical_bytes(report)).hexdigest()
        )
        self.assertEqual(
            self.report["adjudication"]["verdict"],
            "NO_ADDITIONAL_MODE1_ARMCC_ARTIFACT_IN_PINNED_DELIVERY",
        )
        self.assertFalse(self.report["adjudication"]["authorizes_live_hardware_action"])

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "audit.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/mf1750_armcc_mode1_residual_audit.py",
                    "--output",
                    str(output),
                    "--compact",
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr.decode())
            self.assertEqual(completed.stdout, b"")
            payload = output.read_text(encoding="utf-8")
            cli_report = json.loads(payload)
            self.assertEqual(cli_report["report_canonical_sha256"], canonical)
            self.assertNotIn("waveform_bytes", payload)
            self.assertNotIn("decoded_payload", payload)
            self.assertNotIn("MOSI_bytes", payload)

        safety = self.report["safety"]
        self.assertTrue(safety["offline_only"])
        for key, value in safety.items():
            if key != "offline_only":
                self.assertFalse(value, key)


if __name__ == "__main__":
    unittest.main()
