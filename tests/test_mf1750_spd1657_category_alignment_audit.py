from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

from tools import mf1750_spd1657_category_alignment_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]


class Mf1750Spd1657CategoryAlignmentAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report()

    def test_all_five_identity_pinned_datasets_keep_only_direct_labels(self) -> None:
        datasets = self.report["datasets"]
        expected = {
            audit.LEGACY_ID: (6, [], audit.LEGACY_LABELS),
            audit.DATA0_ID: (9, [6, 7, 8], ()),
            audit.DATA1_ID: (8, [5, 6, 7], ()),
            audit.WF20_ID: (9, [5, 8], ()),
            audit.WF23_ID: (9, [5, 8], ()),
        }
        for dataset_id, (row_count, all_ff_rows, labels) in expected.items():
            dataset = datasets[dataset_id]
            geometry = dataset["payload_geometry"]
            self.assertEqual(geometry["row_count"], row_count)
            self.assertEqual(geometry["row_bytes"], 88)
            self.assertEqual(geometry["records_per_row"], 8)
            self.assertEqual(geometry["record_bytes"], 11)
            self.assertEqual(dataset["all_ff_row_indices"], all_ff_rows)
            self.assertEqual(dataset["direct_vendor_labels"], list(labels))
            self.assertFalse(dataset["raw_values_emitted"])

        self.assertEqual(
            datasets[audit.DATA0_ID]["provenance"]["slice_sha256"],
            "9317dfc98fef531e0196b06ba2bce5d6bf9212a135b6fb677678949ac742338e",
        )
        self.assertEqual(
            datasets[audit.DATA1_ID]["provenance"]["array_sha256"],
            "6dbd5a232419da637084683867933a7f60ce06d28a5034136d0f0efae3015e6a",
        )

    def test_no_complete_legacy_labeled_row_matches_any_target(self) -> None:
        alignments = self.report["legacy_label_alignment"]
        for target_id in (audit.DATA0_ID, audit.DATA1_ID, audit.WF20_ID, audit.WF23_ID):
            alignment = alignments[target_id]
            self.assertEqual(alignment["full_labeled_row_exact_match_count"], 0)
            self.assertEqual(alignment["labels_transferred"], [])
            self.assertTrue(
                all(
                    not row["exact_byte_target_indices"]
                    for row in alignment["labeled_rows"]
                )
            )
            self.assertFalse(alignment["position_or_distance_alone_is_label_evidence"])

        data0 = alignments[audit.DATA0_ID]
        self.assertEqual(
            [row["same_ordinal_byte_distance"] for row in data0["labeled_rows"]],
            [31, 60, 55, 51, 63, 52],
        )
        self.assertTrue(
            all(
                not row["same_ordinal_geometry_signature_equal"]
                for row in data0["labeled_rows"]
            )
        )
        assignment = data0["one_to_one_byte_distance_assignment"]
        self.assertEqual(assignment["minimum_total_byte_hamming_distance"], 301)
        self.assertEqual(assignment["optimal_assignment_count"], 30)
        self.assertEqual(assignment["positional_total_byte_hamming_distance"], 312)
        self.assertFalse(assignment["positional_assignment_is_optimal"])
        self.assertFalse(assignment["distance_optimization_proves_semantic_mapping"])

    def test_only_wf_row0_retains_a_non_ff_exact_record_link_to_legacy_vcom(
        self,
    ) -> None:
        comparisons = self.report["exact_11byte_record_comparisons"]
        legacy_data0 = comparisons[f"{audit.LEGACY_ID}__vs__{audit.DATA0_ID}"]
        self.assertEqual(legacy_data0["shared_unique_record_count"], 1)
        self.assertEqual(legacy_data0["shared_unique_non_all_ff_record_count"], 0)

        expected_target_coordinates = {
            audit.WF20_ID: [[0, 3], [0, 4], [0, 5], [0, 6], [0, 7]],
            audit.WF23_ID: [[0, 6], [0, 7]],
        }
        for target_id, target_coordinates in expected_target_coordinates.items():
            comparison = comparisons[f"{audit.LEGACY_ID}__vs__{target_id}"]
            self.assertEqual(comparison["shared_unique_non_all_ff_record_count"], 1)
            cluster = comparison["shared_non_all_ff_record_clusters"][0]
            self.assertEqual(cluster["left_coordinates"], [[0, 5], [0, 6], [0, 7]])
            self.assertEqual(cluster["right_coordinates"], target_coordinates)
            self.assertFalse(cluster["all_ff"])
            self.assertFalse(
                comparison[
                    "exact_subrecord_identity_proves_complete_row_or_category_semantics"
                ]
            )

        adjudication = self.report["adjudication"]
        self.assertFalse(
            adjudication["DATA0_shares_a_non_all_ff_11byte_record_with_legacy"]
        )
        self.assertTrue(
            adjudication[
                "WF20_and_WF23_row0_share_the_only_legacy_non_all_ff_record_cluster"
            ]
        )
        self.assertTrue(
            adjudication["WF20_WF23_row0_is_structurally_consistent_with_legacy_VCOM"]
        )
        self.assertEqual(adjudication["shared_row0_cluster_byte_count"], 11)
        self.assertEqual(adjudication["shared_row0_cluster_ff_byte_count"], 10)
        self.assertEqual(adjudication["shared_row0_cluster_non_ff_byte_count"], 1)
        self.assertEqual(adjudication["shared_row0_cluster_distinct_value_count"], 2)
        self.assertTrue(
            adjudication["shared_row0_cluster_is_low_information_filler_compatible"]
        )
        self.assertFalse(
            adjudication["shared_row0_cluster_supports_a_VCOM_category_candidate"]
        )
        self.assertFalse(adjudication["WF20_WF23_row0_is_therefore_proven_to_be_VCOM"])

    def test_data0_data1_adjacency_and_offsets_do_not_supply_a_mapping(self) -> None:
        same_object = self.report["iar_same_object_structure"]
        self.assertTrue(same_object["arrays_are_byte_identical_across_E2801_and_E2802"])
        self.assertTrue(same_object["DATA0_and_DATA1_are_adjacent_UBROF_sections"])
        self.assertFalse(
            same_object["adjacency_proves_a_logical_pair_or_category_mapping"]
        )

        comparison = self.report["DATA1_against_nine_row_offset_hypotheses"][
            audit.DATA0_ID
        ]
        hypotheses = comparison["hypotheses"]
        self.assertEqual(
            [row["total_byte_hamming_distance"] for row in hypotheses],
            [306, 273],
        )
        self.assertEqual(
            [
                row["non_all_ff_DATA1_rows_total_byte_hamming_distance"]
                for row in hypotheses
            ],
            [272, 273],
        )
        self.assertEqual(comparison["minimum_total_distance_offsets"], [1])
        self.assertEqual(comparison["minimum_non_all_ff_DATA1_distance_offsets"], [0])
        self.assertFalse(comparison["non_all_ff_exact_row_match_exists"])
        self.assertIsNone(comparison["offset_selected_as_semantic_mapping"])

    def test_same_envelope_columns_all_vary_and_apparent_stability_is_ff(self) -> None:
        comparison = self.report["record_byte_column_comparisons"][
            "WF20_25__vs__WF23_25"
        ]
        self.assertEqual(comparison["aligned_record_count"], 72)
        self.assertEqual(comparison["active_record_count"], 50)
        self.assertEqual(comparison["fully_invariant_column_indices"], [])
        self.assertEqual(comparison["active_record_fully_invariant_column_indices"], [])
        self.assertEqual(
            [row["equal_count"] for row in comparison["columns"]],
            [43, 33, 35, 26, 40, 61, 45, 31, 34, 58, 33],
        )
        self.assertEqual(
            [row["active_record_equal_count"] for row in comparison["columns"]],
            [21, 11, 13, 4, 18, 39, 23, 9, 12, 36, 11],
        )
        for column in (5, 9):
            row = comparison["columns"][column]
            self.assertEqual(
                row["active_record_equal_count"], row["active_record_equal_ff_count"]
            )
            self.assertEqual(row["active_record_equal_non_ff_count"], 0)

        data0_column9 = self.report["datasets"][audit.DATA0_ID]["record_byte_columns"][
            9
        ]
        self.assertTrue(data0_column9["constant"])
        self.assertEqual(data0_column9["constant_class"], "all_ff")

    def test_five_way_consensus_has_no_invariant_or_named_column(self) -> None:
        consensus = self.report["five_way_first_48_record_consensus"]
        self.assertEqual(consensus["common_record_count"], 48)
        self.assertEqual(consensus["active_record_count"], 45)
        self.assertEqual(consensus["fully_invariant_column_indices"], [])
        self.assertEqual(consensus["active_record_fully_invariant_column_indices"], [])
        self.assertEqual(
            [row["all_equal_count"] for row in consensus["columns"]],
            [11, 6, 12, 4, 7, 20, 8, 8, 11, 21, 8],
        )
        self.assertEqual(
            [row["active_record_all_equal_count"] for row in consensus["columns"]],
            [8, 3, 9, 1, 4, 17, 5, 5, 8, 18, 5],
        )
        self.assertFalse(consensus["common_ordinal_alignment_is_semantically_proven"])
        adjudication = self.report["adjudication"]
        self.assertFalse(
            adjudication["any_of_11_columns_can_be_named_from_current_evidence"]
        )
        self.assertFalse(adjudication["phase_mapping_proven"])
        self.assertFalse(adjudication["electrical_field_mapping_proven"])

    def test_header_equalities_are_coordinates_not_label_transfer(self) -> None:
        comparisons = self.report["header_coordinate_equality"]
        self.assertEqual(
            comparisons[f"{audit.LEGACY_ID}__vs__{audit.DATA0_ID}"][
                "equal_position_indices"
            ],
            [],
        )
        for target in (audit.WF20_ID, audit.WF23_ID):
            row = comparisons[f"{audit.LEGACY_ID}__vs__{target}"]
            self.assertEqual(row["equal_position_indices"], [0, 5, 6])
            self.assertFalse(row["equal_value_transfers_a_header_field_label"])
        self.assertEqual(
            comparisons[f"{audit.WF20_ID}__vs__{audit.WF23_ID}"][
                "equal_position_indices"
            ],
            [0, 5, 6],
        )

    def test_report_is_deterministic_metadata_only_and_cli_matches(self) -> None:
        self.assertEqual(
            self.report["integrity"]["canonical_sha256"],
            "572a86bcbcdccb9aa17e4114b34cfef7b348f2492ee0154e43085db482780445",
        )
        safety = self.report["safety"]
        self.assertTrue(safety["offline_only"])
        self.assertTrue(
            all(not value for key, value in safety.items() if key != "offline_only")
        )
        serialized = json.dumps(self.report, sort_keys=True).lower()
        for forbidden in (
            "payload_hex",
            "plaintext_hex",
            "waveform_hex",
            "customer_key",
            "recovered_key",
            "authorization_action",
        ):
            self.assertNotIn(forbidden, serialized)

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.mf1750_spd1657_category_alignment_audit",
                "--compact",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8"))
        cli_report = json.loads(completed.stdout)
        self.assertEqual(cli_report["kind"], audit.KIND)
        self.assertEqual(cli_report["integrity"], self.report["integrity"])


if __name__ == "__main__":
    unittest.main()
