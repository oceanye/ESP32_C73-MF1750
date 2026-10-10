from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools import mf1750_spd1656_lutc_projection_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = REPO_ROOT / "tools" / "mf1750_spd1656_lutc_projection_audit.py"
EXPECTED_CANONICAL_SHA256 = (
    "8434152a38e713c76292854998fe3c5cc038a5922528803b9dba69f387c6d94f"
)


class Mf1750Spd1656LutcProjectionAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report()

    def test_primary_manual_identity_pages_and_exact_lutc_layout(self) -> None:
        source = self.report["primary_adjacent_document"]
        self.assertEqual(source["bytes"], 2_339_387)
        self.assertEqual(
            source["sha256"],
            "1f3f5db0600ee6e8133a4c31f9a3f59c1b5bfcc1a916be98ae848ec64581de07",
        )
        self.assertEqual(source["page_count"], 44)
        self.assertEqual(source["extractor"]["version"], "1.28.2")
        self.assertEqual(
            [page["pdf_page_1_based"] for page in source["pages"]],
            [13, 15, 17, 27, 28, 29],
        )
        for page in source["pages"]:
            self.assertTrue(page["all_required_anchors_present"])
            self.assertFalse(page["page_text_emitted"])
            self.assertEqual(
                page["normalized_text_sha256"],
                audit.PAGE_TEXT_SHA256[page["pdf_page_1_based"]],
            )

        facts = source["facts"]
        self.assertEqual(facts["command"], "R20/LUTC")
        self.assertEqual(facts["role"], "VCOM look-up table")
        self.assertEqual(
            (facts["group_count"], facts["group_bytes"], facts["payload_bytes"]),
            (20, 11, 220),
        )
        fields = facts["field_layout_zero_based"]
        self.assertEqual(fields["repeat_RP"]["byte_offset"], 0)
        self.assertEqual(fields["levels_LVL1_to_LVL4"]["byte_offset"], 1)
        self.assertEqual(fields["levels_LVL5_to_LVL8"]["byte_offset"], 2)
        self.assertEqual(
            fields["phase_frame_counts_TP1_to_TP8"]["byte_offsets_inclusive"],
            [3, 10],
        )
        self.assertEqual(
            facts["adjacent_same_controller_geometries"]["R21_to_R28_color"],
            {
                "group_count": 20,
                "group_bytes": 13,
                "payload_bytes": 260,
                "level_bits": 3,
            },
        )

    def test_every_local_dataset_is_projected_without_emitting_records(self) -> None:
        expected = {
            "legacy_commented_535": {
                "geometry": (6, 48),
                "raw": (0, (18, 36, 36, 294), 0),
                "complement": (0, (294, 36, 36, 18), 91),
                "termination": (6, 0, 0, 0, 0),
            },
            "legacy_active_535": {
                "geometry": (6, 48),
                "raw": (0, (4, 48, 38, 294), 4),
                "complement": (11, (294, 38, 48, 4), 143),
                "termination": (0, 6, 0, 5, 1),
            },
            "iar_DATA0_first799": {
                "geometry": (9, 72),
                "raw": (0, (0, 38, 29, 509), 0),
                "complement": (44, (509, 29, 38, 0), 437),
                "termination": (0, 9, 0, 9, 0),
            },
            "iar_DATA1_704": {
                "geometry": (8, 64),
                "raw": (0, (7, 37, 51, 417), 0),
                "complement": (29, (417, 51, 37, 7), 325),
                "termination": (2, 6, 0, 6, 0),
            },
            "WF20_25": {
                "geometry": (9, 72),
                "raw": (0, (3, 28, 59, 486), 1),
                "complement": (39, (486, 59, 28, 3), 393),
                "termination": (0, 9, 0, 8, 1),
            },
            "WF23_25": {
                "geometry": (9, 72),
                "raw": (0, (0, 76, 33, 467), 0),
                "complement": (24, (467, 33, 76, 0), 332),
                "termination": (2, 7, 0, 6, 1),
            },
        }
        self.assertEqual(set(self.report["local_datasets"]), set(expected))
        for dataset_id, exact in expected.items():
            dataset = self.report["local_datasets"][dataset_id]
            self.assertEqual(
                (dataset["category_count"], dataset["record_count"]),
                exact["geometry"],
            )
            for view_name, expected_key in (
                ("raw", "raw"),
                ("bitwise_complement", "complement"),
            ):
                projection = dataset["views"][view_name][
                    "documented_spd1656_projection"
                ]
                observed = (
                    projection["RP"]["zero_count"],
                    tuple(
                        projection["LVL"]["two_bit_code_counts"][str(code)]
                        for code in range(4)
                    ),
                    projection["TP"]["zero_count"],
                )
                self.assertEqual(observed, exact[expected_key])
                self.assertFalse(projection["raw_records_or_field_values_emitted"])
                self.assertFalse(
                    projection["LVL"][
                        "electrical_level_mapping_proven_for_local_format"
                    ]
                )
                self.assertFalse(
                    projection["TP"]["frame_count_semantics_proven_for_local_format"]
                )

            termination = dataset["views"]["bitwise_complement"][
                "documented_spd1656_projection"
            ]["RP"]["termination_shape"]
            self.assertEqual(
                (
                    termination["categories_with_no_zero_candidate"],
                    termination["categories_with_candidate_zero_suffix"],
                    termination["categories_with_later_nonzero_candidate"],
                    termination["categories_with_whole_zero_record_suffix"],
                    termination[
                        "categories_with_nonzero_record_after_first_zero_candidate"
                    ],
                ),
                exact["termination"],
            )
            self.assertFalse(dataset["raw_records_or_payload_bytes_emitted"])

    def test_active_aggregate_raw_and_complement_results_are_exact(self) -> None:
        aggregate = self.report["active_dataset_aggregate"]
        self.assertEqual(aggregate["category_count"], 41)
        self.assertEqual(aggregate["record_count"], 328)
        self.assertTrue(aggregate["inactive_commented_table_excluded"])

        raw = aggregate["raw"]["documented_spd1656_projection"]
        self.assertEqual(
            (raw["RP"]["zero_count"], raw["RP"]["nonzero_count"]), (0, 328)
        )
        self.assertEqual(
            raw["LVL"]["two_bit_code_counts"],
            {"0": 14, "1": 227, "2": 210, "3": 2173},
        )
        self.assertEqual(
            (raw["TP"]["zero_count"], raw["TP"]["nonzero_count"]), (5, 2619)
        )
        self.assertEqual(
            raw["RP"]["termination_shape"]["categories_with_no_zero_candidate"],
            41,
        )

        complement = aggregate["bitwise_complement"]["documented_spd1656_projection"]
        self.assertEqual(
            (complement["RP"]["zero_count"], complement["RP"]["nonzero_count"]),
            (147, 181),
        )
        self.assertEqual(
            complement["LVL"]["two_bit_code_counts"],
            {"0": 2173, "1": 210, "2": 227, "3": 14},
        )
        self.assertEqual(
            (complement["TP"]["zero_count"], complement["TP"]["nonzero_count"]),
            (1630, 994),
        )
        termination = complement["RP"]["termination_shape"]
        self.assertEqual(
            (
                termination["categories_with_no_zero_candidate"],
                termination["categories_with_candidate_zero_suffix"],
                termination["categories_with_later_nonzero_candidate"],
                termination["categories_with_whole_zero_record_suffix"],
                termination[
                    "categories_with_nonzero_record_after_first_zero_candidate"
                ],
                termination["zero_candidate_but_nonzero_record_count"],
            ),
            (4, 37, 0, 34, 3, 10),
        )

    def test_all_offset_sweep_refutes_unique_RP_identification(self) -> None:
        aggregate = self.report["active_dataset_aggregate"]
        raw = aggregate["raw"]["all_candidate_byte_offsets"]
        self.assertEqual(
            [row["categories_with_no_zero_candidate"] for row in raw],
            [41, 41, 41, 40, 40, 41, 40, 41, 39, 41, 41],
        )
        complement = aggregate["bitwise_complement"]
        sweep = complement["all_candidate_byte_offsets"]
        self.assertEqual(
            [row["categories_with_whole_zero_record_suffix"] for row in sweep],
            [34, 20, 17, 30, 13, 10, 34, 23, 13, 10, 26],
        )
        self.assertEqual(
            [row["categories_with_later_nonzero_candidate"] for row in sweep],
            [0, 15, 13, 8, 23, 16, 0, 8, 16, 15, 3],
        )
        self.assertEqual(complement["byte_offsets_at_that_maximum"], [0, 6])
        self.assertEqual(complement["maximum_whole_zero_suffix_category_count"], 34)
        self.assertFalse(complement["documented_RP_offset_is_unique_maximum"])

    def test_profile_delta_is_partitioned_without_promoting_field_names(self) -> None:
        comparison = self.report["paired_profile_field_region_difference"]
        self.assertEqual(comparison["compared_record_count"], 72)
        self.assertEqual(
            comparison["different_byte_positions_under_adjacent_layout"],
            {
                "RP_byte_0": 29,
                "packed_LVL_bytes_1_2": 76,
                "TP_bytes_3_10": 248,
                "total": 353,
            },
        )
        self.assertFalse(comparison["field_names_apply_to_local_format_proven"])

    def test_adjudication_preserves_strict_non_portability_boundary(self) -> None:
        decision = self.report["adjudication"]
        self.assertTrue(
            decision["same_eleven_byte_width_is_structural_similarity_only"]
        )
        self.assertEqual(
            decision["active_raw_projection"],
            {
                "RP_zero_record_count": 0,
                "category_count_without_RP_zero": 41,
                "literal_SPD1656_zero_termination_shape_observed": False,
            },
        )
        self.assertTrue(
            decision["active_complement_projection"][
                "supports_active_low_or_complemented_structure_as_a_hypothesis"
            ]
        )
        self.assertFalse(
            decision["active_complement_projection"][
                "proves_controller_side_complement"
            ]
        )
        for key in (
            "documented_RP_byte_offset_uniquely_identified_by_zero_suffix",
            "local_GROUP_record_is_one_SPD1656_phase_proven",
            "local_group_contains_eight_phases_proven",
            "local_RP_LVL_TP_field_names_proven",
            "local_FF_is_terminator_skip_or_noop_proven",
            "local_voltage_polarity_duration_or_repeat_semantics_proven",
            "direct_SPD1656_parser_or_voltage_code_transfer_allowed",
            "hardware_experiment_or_payload_generation_authorized",
        ):
            self.assertFalse(decision[key], key)

    def test_report_is_deterministic_metadata_only_and_cli_is_exclusive(self) -> None:
        self.assertEqual(self.report["kind"], audit.KIND)
        self.assertEqual(self.report["schema_version"], 1)
        self.assertEqual(
            self.report["integrity"]["canonical_sha256"],
            EXPECTED_CANONICAL_SHA256,
        )

        def assert_no_binary(value: object) -> None:
            self.assertNotIsInstance(value, (bytes, bytearray))
            if isinstance(value, dict):
                for child in value.values():
                    assert_no_binary(child)
            elif isinstance(value, list):
                for child in value:
                    assert_no_binary(child)

        assert_no_binary(self.report)
        handling = self.report["material_handling"]
        self.assertFalse(handling["raw_key_plaintext_record_or_waveform_bytes_emitted"])
        self.assertFalse(handling["raw_key_plaintext_record_or_waveform_bytes_written"])
        self.assertFalse(handling["runtime_payload_include_or_firmware_generated"])
        safety = self.report["safety"]
        self.assertTrue(safety["offline_only"])
        for key, value in safety.items():
            if key != "offline_only":
                self.assertFalse(value, key)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "projection.json"
            environment = dict(os.environ)
            environment["PYTHONIOENCODING"] = "utf-8"
            first = subprocess.run(
                [
                    sys.executable,
                    str(TOOL_PATH),
                    "--compact",
                    "--output",
                    str(output),
                ],
                cwd=REPO_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            emitted = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                emitted["integrity"]["canonical_sha256"],
                EXPECTED_CANONICAL_SHA256,
            )
            second = subprocess.run(
                [
                    sys.executable,
                    str(TOOL_PATH),
                    "--compact",
                    "--output",
                    str(output),
                ],
                cwd=REPO_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(second.returncode, 2)
            self.assertIn("already exists", second.stderr)


if __name__ == "__main__":
    unittest.main()
