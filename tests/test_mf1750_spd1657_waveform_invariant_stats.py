from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from tools import mf1750_spd1657_vendor_profile_pack as profile_pack
from tools import mf1750_spd1657_waveform_invariant_stats as audit


REPO_ROOT = Path(__file__).resolve().parents[1]


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class Spd1657WaveformInvariantStatsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report()

    def test_all_five_datasets_are_identity_pinned_and_record_aligned(self) -> None:
        expected = {
            "WF20_25": (
                800,
                "1591338095e153bd0c7381b096e0b2e73d35131a700aab7c6cfde6c4756a7a8f",
                7,
                792,
                72,
            ),
            "WF23_25": (
                800,
                "95e5fef3dc2946afdabbb35dceef1f1e48b8917d181946a82d06724c0a1c09d8",
                7,
                792,
                72,
            ),
            "legacy_wf_data_535": (
                535,
                "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b",
                7,
                528,
                48,
            ),
            "legacy_iar_data1_704": (
                704,
                "6dbd5a232419da637084683867933a7f60ce06d28a5034136d0f0efae3015e6a",
                0,
                704,
                64,
            ),
            "armcc_lut1_704": (
                704,
                "24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f",
                0,
                704,
                64,
            ),
        }
        self.assertEqual(set(self.report["datasets"]), set(expected))
        for name, headline in expected.items():
            dataset = self.report["datasets"][name]
            region = dataset["record_region"]
            self.assertEqual(
                (
                    dataset["bytes"],
                    dataset["sha256"],
                    region["offset"],
                    region["bytes"],
                    region["record_count"],
                ),
                headline,
            )
            self.assertEqual(region["record_bytes"], 11)
            self.assertEqual(region["records_per_structural_block"], 8)
            self.assertFalse(dataset["raw_waveform_bytes_emitted"])

    def test_entropy_and_repeat_patterns_are_exact_and_value_free(self) -> None:
        expected = {
            "WF20_25": (2.350985802121, 29, 4, 47, 125, 6),
            "WF23_25": (2.844513643342, 46, 6, 32, 92, 6),
            "legacy_wf_data_535": (3.515305970343, 36, 3, 15, 22, 5),
            "legacy_iar_data1_704": (2.561151696953, 27, 5, 42, 286, 3),
            "armcc_lut1_704": (0.0, 1, 1, 64, 704, 1),
        }
        for name, headline in expected.items():
            dataset = self.report["datasets"][name]
            entropy = dataset["entropy_and_concentration"]
            repeats = dataset["exact_record_repetition"]
            runs = dataset["same_byte_runs"]
            self.assertEqual(
                (
                    entropy["shannon_entropy_bits_per_byte"],
                    repeats["unique_record_count"],
                    repeats["duplicate_cluster_count"],
                    repeats["records_participating_in_duplicate_clusters"],
                    runs["longest_run_bytes"],
                    len(runs["runs_at_least_one_record"]),
                ),
                headline,
            )
            self.assertEqual(len(entropy["record_byte_index_entropy_bits"]), 11)
            self.assertEqual(len(entropy["record_byte_index_unique_value_counts"]), 11)
            self.assertFalse(entropy["raw_symbol_values_emitted"])
            self.assertFalse(runs["byte_values_emitted"])

        armcc = self.report["datasets"]["armcc_lut1_704"]
        self.assertTrue(
            armcc["exact_record_repetition"]["whole_sequence_is_single_record_repeat"]
        )
        self.assertEqual(
            armcc["exact_record_repetition"]["minimal_exact_record_period"], 1
        )

    def test_two_vendor_profiles_have_exact_invariant_and_varying_coordinates(
        self,
    ) -> None:
        comparison = self.report["comparisons"]["same_envelope_profiles"]
        full = comparison["full_800"]
        self.assertEqual(full["equal_byte_positions"], 443)
        self.assertEqual(full["different_byte_positions"], 357)
        self.assertEqual(comparison["opaque_prefix_7"]["equal_byte_positions"], 3)
        self.assertEqual(comparison["opaque_prefix_7"]["different_byte_positions"], 4)
        self.assertEqual(comparison["opaque_suffix_1"]["equal_byte_positions"], 1)

        body = comparison["record_body_792"]
        self.assertEqual(body["equal_byte_positions"], 439)
        self.assertEqual(body["different_byte_positions"], 353)
        records = body["record_comparison"]
        self.assertEqual(records["exact_equal_record_count"], 24)
        self.assertEqual(
            records["exact_equal_record_indices"],
            [
                6,
                7,
                14,
                15,
                22,
                23,
                31,
                40,
                41,
                42,
                43,
                44,
                45,
                46,
                47,
                55,
                64,
                65,
                66,
                67,
                68,
                69,
                70,
                71,
            ],
        )
        self.assertEqual(records["equal_positions_inside_nonidentical_records"], 175)
        self.assertEqual(
            records["different_counts_by_record_byte_index"],
            [29, 39, 37, 46, 32, 11, 27, 41, 38, 14, 39],
        )
        self.assertTrue(
            self.report["bounded_findings"]["same_envelope_profile_pair"][
                "every_record_byte_index_varies_somewhere"
            ]
        )

    def test_cross_generation_alignments_are_counted_but_not_semantically_joined(
        self,
    ) -> None:
        comparisons = self.report["comparisons"]
        legacy535 = comparisons["legacy_535_index_alignment_only"]
        self.assertEqual(
            legacy535["WF20_25_vs_legacy_wf_data_535"]["equal_byte_positions"],
            220,
        )
        self.assertEqual(
            legacy535["WF23_25_vs_legacy_wf_data_535"]["equal_byte_positions"],
            208,
        )

        legacy704 = comparisons["legacy_704_pair"]
        self.assertEqual(legacy704["equal_byte_positions"], 420)
        self.assertEqual(legacy704["different_byte_positions"], 284)
        self.assertEqual(legacy704["record_comparison"]["exact_equal_record_count"], 29)

        profile_iar = comparisons[
            "profile_first_64_vs_legacy_iar_704_index_alignment_only"
        ]
        self.assertEqual(
            (
                profile_iar["WF20_25"]["equal_byte_positions"],
                profile_iar["WF23_25"]["equal_byte_positions"],
            ),
            (351, 328),
        )
        self.assertFalse(
            self.report["bounded_findings"][
                "cross_generation_alignment_establishes_field_semantics"
            ]
        )

    def test_common_first_48_record_classes_are_exact(self) -> None:
        common = self.report["comparisons"]["common_first_48_records"]
        three = common["three_way_profiles_and_legacy_535"]
        self.assertEqual(
            {name: row["byte_positions"] for name, row in three["classes"].items()},
            {
                "all_equal": 174,
                "WF20_25_equals_WF23_25_only": 113,
                "WF20_25_equals_legacy_wf_data_535_only": 46,
                "WF23_25_equals_legacy_wf_data_535_only": 34,
                "all_distinct": 161,
            },
        )
        self.assertEqual(three["exact_equal_record_count"], 8)

        four = common["four_way_including_legacy_iar_704"]
        self.assertEqual(four["all_equal_byte_positions"], 129)
        self.assertEqual(four["exact_equal_record_indices"], [31, 46, 47])
        self.assertIn("structural coincidence only", four["interpretation"])

    def test_integrity_cli_and_semantic_boundary_are_metadata_only(self) -> None:
        without_integrity = dict(self.report)
        integrity = without_integrity.pop("integrity")
        self.assertEqual(
            integrity["canonical_sha256"],
            hashlib.sha256(_canonical_bytes(without_integrity)).hexdigest(),
        )

        rendered = json.dumps(self.report, ensure_ascii=False, sort_keys=True)
        for profile_id in ("WF20_25", "WF23_25"):
            self.assertNotIn(
                profile_pack.load_profile(profile_id).plaintext.hex(), rendered
            )
        self.assertEqual(re.findall(r"[0-9A-Fa-f]{65,}", rendered), [])

        semantic = self.report["semantic_boundary"]
        self.assertTrue(semantic["eleven_bytes_are_treated_as_structural_records_only"])
        for key, value in semantic.items():
            if key != "eleven_bytes_are_treated_as_structural_records_only":
                self.assertFalse(value, key)

        safety = self.report["safety"]
        self.assertTrue(safety["offline_only"])
        for key, value in safety.items():
            if key != "offline_only":
                self.assertFalse(value, key)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "audit.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tools.mf1750_spd1657_waveform_invariant_stats",
                    "--output",
                    str(output),
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr.decode())
            self.assertEqual(completed.stdout, b"")
            cli_report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(cli_report["integrity"], integrity)


if __name__ == "__main__":
    unittest.main()
