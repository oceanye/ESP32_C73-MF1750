from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from tools import mf1750_spd1657_arithmetic_transform_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CANONICAL_SHA256 = (
    "b77e5edbc169257cc56cb3af25085a358b7a43aa433432117cce29ae40a8015c"
)


class Mf1750Spd1657ArithmeticTransformAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report()

    def test_exact_arithmetic_family_is_pinned_without_semantic_promotion(self) -> None:
        family = self.report["arithmetic_family"]
        self.assertEqual(family["legacy_535"]["equation"], "535 = 7 + 6*8*11")
        self.assertEqual(family["profile_first_799"]["equation"], "799 = 7 + 9*8*11")
        self.assertEqual(
            family["profile_decoded_800"]["equation"],
            "800 = 7 + 9*8*11 + 1",
        )
        self.assertEqual(family["secondary_704"]["equation"], "704 = 8*8*11")
        self.assertEqual(
            family["iar_DATA0_1503"]["equations"],
            ["1503 = 799 + 704", "1503 = 7 + 17*8*11"],
        )
        self.assertTrue(
            family["iar_DATA0_1503"]["exactly_first799_concatenated_with_FF704"]
        )
        self.assertFalse(
            family["iar_DATA0_1503"][
                "internal_799_boundary_declared_by_symbol_or_subobject"
            ]
        )
        self.assertFalse(
            family["secondary_704"][
                "segmentation_assigns_LUT_category_or_controller_semantics"
            ]
        )

    def test_all_704_bytes_segment_as_eight_rows_of_eight_records(self) -> None:
        datasets = self.report["datasets"]
        expected_active = {
            "legacy_wf_data_535": 40,
            "iar_DATA0_first799": 28,
            "iar_DATA1_704": 35,
            "WF20_25": 38,
            "WF23_25": 50,
        }
        for dataset_id, active_count in expected_active.items():
            row = datasets[dataset_id]
            self.assertEqual(row["record_bytes"], 11)
            self.assertEqual(row["records_per_row"], 8)
            self.assertEqual(row["non_all_ff_record_count"], active_count)
            self.assertTrue(
                row["all_rows_have_active_prefix_then_optional_all_ff_suffix"]
            )
            self.assertFalse(row["raw_record_or_payload_bytes_emitted"])

        data1 = datasets["iar_DATA1_704"]
        self.assertEqual(data1["bytes"], 704)
        self.assertEqual(data1["row_count"], 8)
        self.assertEqual(data1["record_count"], 64)
        self.assertTrue(all(row["record_count"] == 8 for row in data1["rows"]))

    def test_data0_data1_have_no_active_record_or_mask_reordering_bridge(self) -> None:
        relationship = self.report["DATA0_DATA1_relationship"]
        for row in relationship["R20_like_bodies_vs_DATA1_shared_active_records"]:
            self.assertEqual(row["shared_unique_non_all_ff_record_count"], 0)

        aligned = relationship["aligned_offsets_0_and_1"]
        self.assertFalse(aligned["active_row_record_or_mask_alignment_found"])
        self.assertIsNone(aligned["offset_selected_as_semantic_mapping"])
        for row in aligned["tested_offsets"]:
            self.assertEqual(row["non_all_ff_exact_row_indices"], [])
            self.assertEqual(row["equal_nontrivial_all_ff_mask_row_indices"], [])
            self.assertEqual(row["non_all_ff_exact_record_count"], 0)

        arbitrary = relationship["arbitrary_row_and_record_reordering"]
        self.assertEqual(arbitrary["exact_non_all_ff_row_pairs"], [])
        self.assertEqual(
            arbitrary["record_multiset_equivalent_non_all_ff_row_pairs"], []
        )
        self.assertEqual(arbitrary["equal_nontrivial_all_ff_mask_row_pairs"], [])
        self.assertFalse(relationship["category_or_register_pairing_proven"])

    def test_bounded_simple_transform_family_has_no_exact_mapping(self) -> None:
        screen = self.report["simple_transform_screen"]
        self.assertFalse(screen["exact_transform_found"])
        self.assertFalse(screen["other_transforms_excluded"])
        for row in screen["same_length_first799_pairs"]:
            for key in (
                "exact_identity",
                "whole_payload_bytewise_complement",
                "record_multisets_equal",
                "row_multisets_equal",
                "record_byte_reversal_multiset_equal",
                "single_uniform_xor_delta",
                "single_uniform_additive_mod256_delta",
            ):
                self.assertFalse(row[key])

        shared = screen["WF20_vs_WF23_shared_active_records"]
        self.assertEqual(shared["shared_unique_non_all_ff_record_count"], 1)
        self.assertEqual(
            shared["shared_unique_low_information_filler_compatible_record_count"],
            1,
        )
        self.assertEqual(shared["shared_unique_non_low_information_record_count"], 0)

    def test_checksum_and_terminator_results_stay_bounded_negative(self) -> None:
        checksums = self.report["checksum_hypotheses"]
        for row in checksums["outer_profile_suffix"]["profiles"].values():
            self.assertTrue(row["suffix_is_zero"])
            self.assertEqual(row["matching_candidate_algorithms"], [])
            self.assertFalse(row["simple_checksum_match_exists"])
        self.assertTrue(
            checksums["outer_profile_suffix"][
                "does_not_exclude_crc_mac_or_other_integrity_scheme"
            ]
        )

        per_record = checksums["per_record"]
        self.assertFalse(per_record["universal_simple_checksum_relation_found"])
        self.assertTrue(
            per_record["does_not_test_or_exclude_crc_mac_or_field_encoding"]
        )
        for dataset_rows in per_record["datasets"].values():
            self.assertTrue(
                all(
                    not row["universal_match_at_any_candidate_check_byte"]
                    for row in dataset_rows.values()
                )
            )

        boundary = self.report["terminator_repeat_duration_boundary"]
        self.assertTrue(
            boundary[
                "all_datasets_have_active_prefix_then_optional_all_ff_suffix_per_row"
            ]
        )
        self.assertEqual(
            boundary["non_all_ff_record_starting_ff_ff_count_across_all_datasets"],
            0,
        )
        self.assertEqual(boundary["raw_record_byte0_zero_count_across_all_datasets"], 0)
        self.assertFalse(boundary["trailing_all_ff_is_a_controller_terminator_proven"])
        self.assertFalse(boundary["record_byte0_is_repeat_count_proven"])
        self.assertFalse(boundary["any_record_byte_is_duration_proven"])

    def test_header_delta_preserves_loader_evidence_without_brightness_claim(
        self,
    ) -> None:
        delta = self.report["electrical_header_delta"]
        self.assertEqual(delta["equal_byte_indices"], [0, 5, 6])
        self.assertEqual(delta["different_byte_indices"], [1, 2, 3, 4])
        binding = delta["current_armcc_loader_binding"]
        self.assertFalse(binding["header_byte5_forwarded_to_dedicated_header_command"])
        self.assertTrue(binding["header_byte5_included_in_opaque_R20_payload"])
        self.assertTrue(binding["referenced_from_prior_identity_pinned_audit"])
        self.assertFalse(binding["reproduced_by_this_tool"])
        self.assertTrue(
            binding["this_tool_only_computes_profile_header_coordinate_delta"]
        )
        projection = delta["public_spd1657_manual_projection"]
        self.assertTrue(projection["same_gate_level_selector_position"])
        self.assertTrue(
            projection["all_four_intermediate_source_level_positions_differ"]
        )
        self.assertTrue(projection["same_pll_request_position"])
        self.assertTrue(
            projection["mapping_referenced_from_prior_identity_pinned_audit"]
        )
        self.assertFalse(projection["manual_loaded_or_parsed_by_this_tool"])
        self.assertFalse(projection["reproduced_by_this_tool"])
        self.assertFalse(projection["manual_assigns_brightness_or_contrast_semantics"])
        self.assertFalse(delta["record_body_fields_inferred_from_header_delta"])

        adjudication = self.report["adjudication"]
        self.assertTrue(
            adjudication[
                "electrical_header_loader_binding_referenced_from_prior_identity_pinned_audit"
            ]
        )
        self.assertFalse(
            adjudication["electrical_header_loader_binding_reproduced_by_this_tool"]
        )
        self.assertFalse(adjudication["public_manual_mapping_reproduced_by_this_tool"])

    def test_build_never_enters_profile_pack_render_or_write_paths(self) -> None:
        with (
            mock.patch.object(
                audit.profile_pack,
                "render_include",
                side_effect=AssertionError("render path must remain unreachable"),
            ),
            mock.patch.object(
                audit.profile_pack,
                "write_include",
                side_effect=AssertionError("write path must remain unreachable"),
            ),
        ):
            report = audit.build_report()
        self.assertFalse(
            report["material_handling"]["profile_pack_render_or_write_path_called"]
        )

    def test_report_is_deterministic_metadata_only_and_cli_reproduces_it(self) -> None:
        self.assertEqual(self.report["schema_version"], 2)
        self.assertEqual(
            self.report["scope"],
            "offline_identity_pinned_metadata_output_only",
        )
        handling = self.report["material_handling"]
        self.assertTrue(handling["existing_vendor_wrappers_read"])
        self.assertTrue(
            handling["vendor_key_material_recovered_in_memory_by_load_profile"]
        )
        self.assertTrue(
            handling["existing_plaintext_decrypted_in_memory_by_load_profile"]
        )
        self.assertEqual(handling["decrypted_profile_count"], 2)
        self.assertEqual(handling["plaintext_bytes_per_profile"], 800)
        self.assertFalse(handling["profile_pack_render_or_write_path_called"])
        self.assertFalse(handling["raw_key_plaintext_or_waveform_bytes_emitted"])
        self.assertFalse(handling["raw_key_plaintext_or_waveform_bytes_written"])
        self.assertFalse(handling["include_or_firmware_generated"])
        self.assertFalse(handling["flashable_runtime_payload_generated"])
        self.assertEqual(
            self.report["integrity"]["canonical_sha256"],
            EXPECTED_CANONICAL_SHA256,
        )
        serialized = json.dumps(self.report, sort_keys=True).lower()
        for forbidden in (
            '"waveform_bytes"',
            '"plaintext_bytes"',
            '"key_bytes"',
            '"payload_bytes"',
            '"raw_payload"',
            '"authorization_token"',
        ):
            self.assertNotIn(forbidden, serialized)
        safety = self.report["safety"]
        self.assertTrue(safety["offline_only"])
        self.assertTrue(safety["existing_profile_plaintext_materialized_in_memory"])
        self.assertFalse(safety["hardware_accessed"])
        self.assertFalse(safety["serial_or_COM8_accessed"])
        self.assertFalse(safety["device_network_accessed"])
        self.assertFalse(safety["display_refresh_attempted"])
        self.assertFalse(safety["runtime_payload_generated"])
        self.assertFalse(safety["profile_plaintext_or_key_written_to_disk"])

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.mf1750_spd1657_arithmetic_transform_audit",
                "--compact",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            timeout=120,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8"))
        cli_report = json.loads(completed.stdout)
        self.assertEqual(cli_report["kind"], audit.KIND)
        self.assertEqual(
            cli_report["integrity"]["canonical_sha256"], EXPECTED_CANONICAL_SHA256
        )


if __name__ == "__main__":
    unittest.main()
