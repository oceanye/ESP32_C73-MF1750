from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
TOOL_PATH = TOOLS_DIR / "mf1750_spd1657_patent_11byte_audit.py"
sys.path.insert(0, str(TOOLS_DIR))
SPEC = importlib.util.spec_from_file_location("spd1657_patent_11byte_audit", TOOL_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load SPD1657 patent 11-byte audit")
audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


class Spd1657Patent11ByteAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report()

    def test_primary_patent_contract_is_exact_and_offline(self) -> None:
        patent = self.report["primary_patent"]
        self.assertEqual(patent["publication"], "US20070085819A1")
        self.assertEqual(patent["family_publication"], "WO2005038765A1")
        self.assertEqual(patent["controller_example"], "Philips Apollo ASIC")
        self.assertEqual(
            patent["relevant_description_paragraphs"], [37, 38, 48, 49, 50, 51]
        )
        self.assertEqual(patent["pdf_bytes_observed_2026_08_11"], 1_095_324)
        self.assertEqual(
            patent["pdf_sha256_observed_2026_08_11"],
            "7596c486fccf3e58ab84a6241993272feee8e06b91ab4f49eaba404713f46cbe",
        )
        self.assertEqual(
            patent["facts_canonical_sha256"],
            "db4b4a7f717a9a3323e974827f5af1b59878e7027ab0118b38b879cebc5504b6",
        )
        design = patent["particular_design"]
        self.assertEqual(design["record_bytes"], 11)
        self.assertEqual(design["sequence_end_may_be_indicated_by"], "FF FF")
        self.assertEqual(
            design["three_level_example_codes"]["3"],
            "not assigned by the example",
        )
        self.assertFalse(
            patent["pdf_downloaded_or_network_accessed_by_this_offline_tool"]
        )

    def test_primary_patent_fact_tampering_fails_closed(self) -> None:
        with patch.dict(
            audit.PRIMARY_PATENT_FACTS,
            {"publication": "tampered-publication"},
        ):
            with self.assertRaisesRegex(
                audit.Patent11ByteAuditError,
                "primary patent fact contract changed",
            ):
                audit.build_report()

    def test_local_inputs_are_identity_pinned_and_have_exact_geometry(self) -> None:
        expected = {
            "WF20_25": (
                800,
                "1591338095e153bd0c7381b096e0b2e73d35131a700aab7c6cfde6c4756a7a8f",
                "b483da853ecafafecd94f9e34427dd4ebf8a29685ffbf2de7d6f309ad16340c4",
                72,
                38,
                34,
            ),
            "WF23_25": (
                800,
                "95e5fef3dc2946afdabbb35dceef1f1e48b8917d181946a82d06724c0a1c09d8",
                "8dfa3ba7a6e5c378b5ca544d8f1f7982c2dfb79736663ed2afacaa0f168284cb",
                72,
                50,
                22,
            ),
            "legacy535": (
                535,
                "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b",
                "81cd54a403557f181004ea4ae0aac456374d09c6126e31cb59b1e2ba017f194f",
                48,
                40,
                8,
            ),
        }
        for profile_id, headline in expected.items():
            profile = self.report["profiles"][profile_id]
            identity = profile["identity"]
            geometry = profile["local_geometry"]
            self.assertEqual(
                (
                    identity["bytes"],
                    identity["sha256"],
                    identity["body_sha256"],
                    geometry["record_count"],
                    geometry["non_all_ff_record_count"],
                    geometry["all_ff_record_count"],
                ),
                headline,
            )
            self.assertEqual(geometry["bytes_per_record"], 11)
            self.assertEqual(geometry["records_per_category"], 8)
            self.assertFalse(profile["raw_header_body_record_key_or_plaintext_emitted"])

        for profile_id in ("WF20_25", "WF23_25"):
            source = self.report["profiles"][profile_id]["identity"]["source"]
            sentinel = self.report["profiles"][profile_id]["local_geometry"][
                "outer_sentinel"
            ]
            self.assertTrue(source["identity_checked_by_vendor_profile_pack"])
            self.assertTrue(sentinel["is_zero"])
            self.assertFalse(sentinel["is_patent_ff_ff_sequence_terminator"])

    def test_two_bit_selector_projection_is_exact_but_literal_mapping_is_incomplete(
        self,
    ) -> None:
        expected = {
            "WF20_25": (
                {"0": 38, "1": 96, "2": 195, "3": 1975},
                {"0": 38, "1": 96, "2": 195, "3": 887},
            ),
            "WF23_25": (
                {"0": 27, "1": 198, "2": 199, "3": 1880},
                {"0": 27, "1": 198, "2": 199, "3": 1176},
            ),
            "legacy535": (
                {"0": 41, "1": 138, "2": 209, "3": 1148},
                {"0": 41, "1": 138, "2": 209, "3": 892},
            ),
        }
        for profile_id, (all_counts, active_counts) in expected.items():
            projection = self.report["profiles"][profile_id][
                "patent_selector_projection"
            ]
            self.assertEqual(projection["all_records_code_counts"], all_counts)
            self.assertEqual(
                projection["non_all_ff_records_code_counts"], active_counts
            )
            self.assertEqual(
                projection["unassigned_code_3_count_in_non_all_ff_records"],
                active_counts["3"],
            )
            self.assertTrue(
                projection["unassigned_code_3_present_in_non_all_ff_records"]
            )
            self.assertFalse(
                projection[
                    "literal_three_level_example_completely_decodes_local_selectors"
                ]
            )
            self.assertFalse(projection["drive_state_mapping_proven_for_spd1657"])

    def test_projected_timing_positions_are_metadata_only_and_exact(self) -> None:
        expected = {
            "WF20_25": {
                "byte_8": (
                    12,
                    0,
                    13,
                    "9c9a2ce6cff4de4d335b7b4876348b4386ce6c603ce2e2f100a1658f18ead40d",
                ),
                "byte_9": (
                    6,
                    0,
                    32,
                    "f16979a902b88751391879462ad2fd841642a327382244d5e6446c3464737181",
                ),
                "byte_10": (
                    10,
                    0,
                    7,
                    "84df6d2a9e562062f28e341f6d64c674b9d3de8e883a096ead49841b683a59c2",
                ),
            },
            "WF23_25": {
                "byte_8": (
                    12,
                    0,
                    21,
                    "825763941a11bfcb78c89e3a5d158330a018b34a3dea949bf31c1732293daac8",
                ),
                "byte_9": (
                    8,
                    0,
                    42,
                    "9d04d400f5be3017f72736ed830d799f401dea4be3a7f6a87c124f06866b7dd0",
                ),
                "byte_10": (
                    11,
                    0,
                    7,
                    "09b7f5cdb479fc1639487bf420bf92cc1d364ffb778a4a5cf438d4924c7cc79a",
                ),
            },
            "legacy535": {
                "byte_8": (
                    16,
                    2,
                    12,
                    "4bf317f540b80f7fab31fffe524a55cb9c5c12556f2b70b616635daba9248072",
                ),
                "byte_9": (
                    13,
                    0,
                    19,
                    "a3ded624551329fa068c447d0305066b586fe5f67435c54f138db8f7c2638a29",
                ),
                "byte_10": (
                    8,
                    0,
                    5,
                    "c15a54ff15135b8ca4c2915488f75399d23bac4cd9acaea48ded75b5778f881f",
                ),
            },
        }
        for profile_id, positions in expected.items():
            projected = self.report["profiles"][profile_id][
                "patent_timing_position_projection"
            ]
            active = projected["non_all_ff_records"]
            for position, exact in positions.items():
                summary = active[position]
                self.assertEqual(
                    (
                        summary["unique_value_count"],
                        summary["zero_count"],
                        summary["ff_count"],
                        summary["sha256_of_ordered_values"],
                    ),
                    exact,
                )
                self.assertFalse(summary["field_semantics_or_units_proven_for_spd1657"])
            self.assertEqual(
                projected[
                    "non_all_ff_records_with_all_three_projected_timing_bytes_ff"
                ],
                7 if profile_id != "legacy535" else 5,
            )
            self.assertFalse(
                projected["timing_units_or_valid_ranges_stated_for_spd1657"]
            )

    def test_ff_terminator_alignment_is_a_clue_not_a_semantic_transfer(self) -> None:
        expected = {
            "WF20_25": ([0], 5, [0, 3, 3, 4, 3, 8, 3, 2, 8]),
            "WF23_25": ([0, 4, 7], 2, [0, 2, 2, 1, 0, 8, 1, 0, 8]),
            "legacy535": ([0], 3, [0, 1, 2, 2, 1, 2]),
        }
        for profile_id, (no_terminator, single_ff, trailing_counts) in expected.items():
            projection = self.report["profiles"][profile_id][
                "patent_escape_and_terminator_projection"
            ]
            self.assertEqual(projection["non_all_ff_records_starting_ff_ff"], 0)
            self.assertEqual(
                projection["non_all_ff_records_starting_single_ff_then_non_ff"],
                single_ff,
            )
            self.assertEqual(
                projection["category_indices_without_record_boundary_ff_ff"],
                no_terminator,
            )
            self.assertEqual(
                projection[
                    "category_indices_with_non_all_ff_after_first_boundary_ff_ff"
                ],
                [],
            )
            self.assertEqual(
                [
                    item["trailing_all_ff_record_count"]
                    for item in projection["category_summaries"]
                ],
                trailing_counts,
            )
            self.assertTrue(
                projection[
                    "all_observed_all_ff_records_are_trailing_within_each_category"
                ]
            )
            self.assertTrue(
                projection[
                    "observed_boundary_ff_ff_never_precedes_a_later_non_all_ff_record"
                ]
            )
            self.assertTrue(projection["body_ends_with_ff_ff"])
            self.assertFalse(projection["literal_patent_parser_applicability_proven"])
            self.assertFalse(
                projection["category_is_one_independent_patent_sequence_proven"]
            )

    def test_adjudication_keeps_the_hard_semantic_boundary(self) -> None:
        decision = self.report["adjudication"]
        self.assertTrue(decision["exact_record_width_match"])
        self.assertTrue(
            decision[
                "observed_all_ff_padding_is_positionally_compatible_with_an_optional_trailing_terminator"
            ]
        )
        self.assertFalse(
            decision[
                "fixed_eight_record_category_structure_decisively_contradicts_optional_ff_ff_terminator"
            ]
        )
        self.assertFalse(
            decision[
                "fixed_eight_record_category_structure_proves_optional_ff_ff_terminator"
            ]
        )
        self.assertFalse(
            decision["literal_three_level_example_decodes_every_local_selector"]
        )
        for field in (
            "local_candidates_are_same_philips_apollo_format_proven",
            "local_candidates_are_spd1657_field_abi_proven",
            "ff_ff_has_same_terminator_meaning_locally_proven",
            "single_ff_has_same_hardware_shaking_meaning_locally_proven",
            "bytes_8_9_10_have_patent_timing_semantics_locally_proven",
            "category_or_group_is_a_patent_sequence_or_frame_proven",
        ):
            self.assertFalse(decision[field])
        self.assertIn("not_spd1657_abi_proof", decision["compatibility_class"])
        self.assertIn("authorizing a visible refresh", decision["must_not_use_for"])

    def test_cli_is_metadata_only_and_has_no_hardware_path(self) -> None:
        safety = self.report["safety"]
        self.assertTrue(all(not value for value in safety.values()))
        rendered = json.dumps(self.report, sort_keys=True)
        for forbidden in (
            "customer_key",
            "payload_hex",
            "plaintext_hex",
            "record_hex",
            "COM8",
        ):
            self.assertNotIn(forbidden, rendered)

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.mf1750_spd1657_patent_11byte_audit",
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
        self.assertEqual(
            cli_report["profiles"]["WF23_25"]["local_geometry"]["record_count"],
            72,
        )


if __name__ == "__main__":
    unittest.main()
