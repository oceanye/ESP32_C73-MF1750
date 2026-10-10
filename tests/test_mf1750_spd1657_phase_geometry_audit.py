from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
TOOL_PATH = TOOLS_DIR / "mf1750_spd1657_phase_geometry_audit.py"
sys.path.insert(0, str(TOOLS_DIR))
SPEC = importlib.util.spec_from_file_location("spd1657_phase_geometry_audit", TOOL_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load SPD1657 phase-geometry audit")
audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


class Spd1657PhaseGeometryAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report()

    def test_frozen_profiles_have_exact_geometry_and_sentinel_boundary(self) -> None:
        expected = {
            "WF20_25": (800, 792, 518, 1, 34),
            "WF23_25": (800, 792, 425, 0, 22),
            "legacy535": (535, 528, 198, 4, 8),
        }
        for profile_id, headline in expected.items():
            profile = self.report["profiles"][profile_id]
            self.assertEqual(
                (
                    profile["bytes"],
                    profile["body"]["bytes"],
                    profile["body"]["ff_count"],
                    profile["body"]["zero_count"],
                    profile["body"]["all_ff_group_count"],
                ),
                headline,
            )
            self.assertEqual(profile["body"]["bytes_per_group"], 11)
            self.assertEqual(profile["body"]["groups_per_category"], 8)
            self.assertEqual(profile["body"]["first_byte_zero_count"], 0)
            self.assertFalse(profile["raw_header_or_body_bytes_emitted"])

        for profile_id in ("WF20_25", "WF23_25"):
            sentinel = self.report["profiles"][profile_id]["sentinel"]
            self.assertEqual(sentinel["offset"], 799)
            self.assertTrue(sentinel["is_zero"])
            self.assertTrue(sentinel["outside_group_body"])
            self.assertFalse(sentinel["included_in_any_11_byte_group"])
        self.assertFalse(self.report["profiles"]["legacy535"]["sentinel"]["present"])

    def test_global_nibble_and_two_bit_projections_are_exact_but_uninterpreted(
        self,
    ) -> None:
        expected_nibbles = {
            "WF20_25": {
                "0": 3,
                "1": 2,
                "2": 25,
                "3": 11,
                "4": 1,
                "5": 1,
                "6": 12,
                "7": 49,
                "8": 1,
                "9": 6,
                "A": 18,
                "B": 71,
                "C": 3,
                "D": 65,
                "E": 106,
                "F": 1210,
            },
            "WF23_25": {
                "0": 0,
                "1": 1,
                "2": 14,
                "3": 9,
                "4": 2,
                "5": 22,
                "6": 27,
                "7": 108,
                "8": 0,
                "9": 3,
                "A": 9,
                "B": 56,
                "C": 10,
                "D": 61,
                "E": 144,
                "F": 1118,
            },
            "legacy535": {
                "0": 10,
                "1": 0,
                "2": 10,
                "3": 24,
                "4": 5,
                "5": 4,
                "6": 25,
                "7": 75,
                "8": 1,
                "9": 5,
                "A": 26,
                "B": 35,
                "C": 8,
                "D": 58,
                "E": 148,
                "F": 622,
            },
        }
        expected_quads = {
            "WF20_25": {"0": 49, "1": 137, "2": 257, "3": 2725},
            "WF23_25": {"0": 36, "1": 246, "2": 262, "3": 2624},
            "legacy535": {"0": 68, "1": 176, "2": 276, "3": 1592},
        }
        for profile_id in expected_nibbles:
            body = self.report["profiles"][profile_id]["body"]
            self.assertEqual(
                body["nibble_histogram"]["combined"], expected_nibbles[profile_id]
            )
            projection = body["two_bit_projection"]
            self.assertEqual(projection["counts"], expected_quads[profile_id])
            self.assertEqual(projection["classification"], "structural_projection_only")
            self.assertFalse(projection["drive_state_mapping_proven"])

    def test_categories_and_groups_preserve_exact_ff_and_duplicate_structure(
        self,
    ) -> None:
        expected_non_ff_counts = {
            "WF20_25": [
                [7, 8, 7, 1, 1, 1, 1, 1],
                [9, 9, 9, 7, 9, 0, 0, 0],
                [9, 9, 7, 8, 8, 0, 0, 0],
                [9, 9, 10, 8, 0, 0, 0, 0],
                [8, 9, 8, 8, 4, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0, 0],
                [8, 9, 9, 8, 10, 0, 0, 0],
                [9, 9, 10, 8, 6, 4, 0, 0],
                [0, 0, 0, 0, 0, 0, 0, 0],
            ],
            "WF23_25": [
                [7, 7, 7, 8, 8, 7, 1, 1],
                [8, 8, 8, 8, 7, 8, 0, 0],
                [6, 8, 8, 8, 11, 9, 0, 0],
                [6, 8, 8, 9, 10, 9, 5, 0],
                [8, 8, 9, 9, 5, 8, 8, 5],
                [0, 0, 0, 0, 0, 0, 0, 0],
                [8, 8, 8, 9, 4, 8, 5, 0],
                [7, 8, 8, 8, 6, 8, 9, 5],
                [0, 0, 0, 0, 0, 0, 0, 0],
            ],
        }
        for profile_id, expected in expected_non_ff_counts.items():
            categories = self.report["profiles"][profile_id]["categories"]
            observed = [
                [group["non_ff_count"] for group in category["groups"]]
                for category in categories
            ]
            self.assertEqual(observed, expected)
            self.assertEqual(
                [category["index"] for category in categories if category["all_ff"]],
                [5, 8],
            )

        legacy = self.report["profiles"]["legacy535"]
        self.assertEqual(
            [category["label"] for category in legacy["categories"]],
            ["VCOM", "Black", "White", "Yellow", "Red", "Power"],
        )
        self.assertTrue(legacy["source"]["labels_are_vendor_comments"])

    def test_cross_profile_deltas_are_exact(self) -> None:
        comparisons = self.report["comparisons"]
        wf = comparisons["WF20_25_vs_WF23_25"]
        self.assertEqual(wf["equal_header_positions"], 3)
        self.assertEqual(wf["equal_body_positions"], 439)
        self.assertTrue(wf["trailing_sentinel_equal"])
        self.assertEqual(
            wf["category_different_byte_counts"], [36, 43, 48, 59, 55, 0, 52, 60, 0]
        )
        self.assertEqual(
            wf["different_byte_counts_by_group_byte_index"],
            [29, 39, 37, 46, 32, 11, 27, 41, 38, 14, 39],
        )
        self.assertEqual(
            wf["equal_positions_in_compared_header_body_and_optional_sentinel"], 443
        )

        wf20_legacy = comparisons["WF20_25_vs_legacy535_first_six_categories"]
        self.assertEqual(wf20_legacy["equal_body_positions"], 220)
        self.assertEqual(
            wf20_legacy["category_different_byte_counts"], [31, 64, 53, 55, 60, 45]
        )
        wf23_legacy = comparisons["WF23_25_vs_legacy535_first_six_categories"]
        self.assertEqual(wf23_legacy["equal_body_positions"], 208)
        self.assertEqual(
            wf23_legacy["category_different_byte_counts"], [39, 63, 53, 57, 63, 45]
        )

    def test_loader_evidence_is_forwarding_only_and_does_not_assign_fields(
        self,
    ) -> None:
        loader = self.report["loader_forwarding_evidence"]
        current = loader["current_armcc"]
        self.assertEqual(current["writeepd_call_count"], 4)
        self.assertTrue(current["writeepd_forwards_original_pointer_and_length"])
        self.assertTrue(current["bulk_writer_reads_one_byte_then_increments_pointer"])
        self.assertFalse(current["record_reordering_in_delivered_adapter_observed"])

        legacy = loader["legacy_iar_e2802"]
        self.assertEqual(legacy["upload_lut0"]["count_bytes"], 799)
        self.assertEqual(legacy["upload_lut0"]["source"], "dataBuff + 4")
        self.assertTrue(legacy["loop_and_single_byte_spi_forwarding_supported"])
        self.assertFalse(
            legacy["inline_byte_identity_and_pointer_increment_fully_disassembled"]
        )
        self.assertFalse(legacy["record_reordering_observed"])

    def test_spd1656_relation_is_explicit_negative_evidence(self) -> None:
        relation = self.report["spd1656_relation"]
        geometry = relation["published_spd1656_geometry"]
        self.assertEqual(geometry["vcom_formula"], "20 groups * 11 bytes")
        self.assertEqual(geometry["color_formula"], "20 groups * 13 bytes")
        source = relation["third_party_reverse_engineering_source_code"]
        self.assertTrue(source["read_flash_passes_raw_slices_without_complement"])
        self.assertFalse(source["network_fetched_or_executed_by_this_offline_tool"])
        conclusion = relation["compatibility_conclusion"]
        self.assertTrue(
            conclusion["same_11_byte_width_as_spd1656_vcom_is_geometry_only"]
        )
        self.assertFalse(conclusion["direct_spd1656_vcom_parser_transfer_proven"])
        self.assertFalse(conclusion["direct_spd1656_color_parser_transfer_proven"])
        self.assertFalse(
            conclusion["bitwise_complement_is_valid_spd1657_decoder_proven"]
        )
        self.assertFalse(
            conclusion["repeat_level_or_frame_count_semantics_transfer_proven"]
        )

    def test_mode1_interpretation_is_bounded_cross_consistency_not_mapping(
        self,
    ) -> None:
        interpretation = self.report["bounded_mode1_interpretation"]
        self.assertEqual(
            interpretation["evidence_class"],
            "B_structural_geometry_plus_C_semantic_cross_consistency",
        )
        geometry = interpretation["direct_geometry"]
        self.assertTrue(geometry["supports_vcom_plus_eight_target_categories_model"])
        self.assertEqual(
            geometry["all_ff_category_indices_in_both_vendor_profiles"], [5, 8]
        )
        conditional = interpretation["conditional_mapping_only"]
        self.assertEqual(conditional["then_all_ff_target_codes"], [4, 7])
        self.assertFalse(conditional["direct_abi_or_loader_proof"])
        counterweight = interpretation["counterweight"]
        self.assertEqual(counterweight["legacy_mode0_category_5_vendor_label"], "Power")
        self.assertFalse(counterweight["same_generation_mode1_loader_present"])
        self.assertFalse(
            counterweight["therefore_unique_category_to_pixel_code_mapping_proven"]
        )

    def test_report_draws_a_hard_semantic_boundary_and_cli_is_metadata_only(
        self,
    ) -> None:
        semantic = self.report["semantic_boundary"]
        self.assertIn("groups/records, not phases", semantic["wording_rule"])
        self.assertTrue(semantic["not_proven"]["group_is_a_chronological_phase_record"])
        self.assertTrue(semantic["not_proven"]["any_byte_is_repeat_or_duration"])
        self.assertTrue(
            semantic["not_proven"]["any_nibble_or_two_bit_projection_is_a_drive_level"]
        )
        self.assertTrue(
            semantic["not_proven"]["bitwise_complement_is_the_controller_decoder"]
        )

        safety = self.report["safety"]
        self.assertTrue(all(not value for value in safety.values()))
        rendered = json.dumps(self.report, sort_keys=True)
        self.assertNotIn("customer_key", rendered)
        self.assertNotIn("payload_hex", rendered)
        self.assertNotIn("plaintext_hex", rendered)

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.mf1750_spd1657_phase_geometry_audit",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        cli_report = json.loads(completed.stdout)
        self.assertEqual(cli_report["kind"], audit.KIND)
        self.assertEqual(cli_report["schema_version"], 1)
        self.assertEqual(cli_report["profiles"]["WF20_25"]["body"]["ff_count"], 518)


if __name__ == "__main__":
    unittest.main()
