from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from tools import mf1750_spd1657_profile_color_delta as audit
from tools import mf1750_spd1657_vendor_profile_pack as profile_pack


REPO_ROOT = Path(__file__).resolve().parents[1]


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class Spd1657ProfileColorDeltaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report()

    def test_profiles_and_envelope_are_exactly_identity_pinned(self) -> None:
        expected = {
            "WF20_25": (
                "1591338095e153bd0c7381b096e0b2e73d35131a700aab7c6cfde6c4756a7a8f",
                "2fc6ab4de405835d9a5ff93a19adb03e277d0dece9df87a88c467a07bcb801af",
                "3cab2e2915205400bfdb0c2749a3e1e606cb6f190b8f3638849c532449a0ca26",
            ),
            "WF23_25": (
                "95e5fef3dc2946afdabbb35dceef1f1e48b8917d181946a82d06724c0a1c09d8",
                "082e520524ebe6c5667d778a1c51407a37d459cc34f8db76b54ba26e93732185",
                "2eeae0e8e6a936cfd55e0a215371c114c037dbb70e701d8b95a2f560387788fb",
            ),
        }
        self.assertEqual(set(self.report["profiles"]), set(expected))
        for profile_id, hashes in expected.items():
            profile = self.report["profiles"][profile_id]
            self.assertEqual(profile["decoded_bytes"], 800)
            self.assertEqual(
                (
                    profile["decoded_sha256"],
                    profile["prefix_sha256"],
                    profile["r20_candidate_sha256"],
                ),
                hashes,
            )
            self.assertTrue(profile["identity_pinned_by_vendor_profile_loader"])
            self.assertTrue(
                profile["filename_numeric_tokens_have_no_proven_temperature_semantics"]
            )
            self.assertFalse(profile["raw_plaintext_or_waveform_bytes_emitted"])

    def test_full_prefix_body_suffix_deltas_are_exact(self) -> None:
        comparison = self.report["same_envelope_comparison"]
        self.assertEqual(
            (
                comparison["full_800"]["equal_byte_positions"],
                comparison["full_800"]["different_byte_positions"],
            ),
            (443, 357),
        )
        self.assertEqual(
            (
                comparison["opaque_prefix_7"]["equal_byte_positions"],
                comparison["opaque_prefix_7"]["different_byte_positions"],
            ),
            (3, 4),
        )
        self.assertEqual(
            (
                comparison["structural_body_9x8x11"]["equal_byte_positions"],
                comparison["structural_body_9x8x11"]["different_byte_positions"],
            ),
            (439, 353),
        )
        self.assertEqual(comparison["opaque_suffix_1"]["different_byte_positions"], 0)

    def test_block_and_record_localization_is_exact(self) -> None:
        body = self.report["same_envelope_comparison"]["structural_body_9x8x11"]
        records = body["record_comparison"]
        self.assertEqual(records["exact_equal_record_count"], 24)
        self.assertEqual(records["records_with_any_difference"], 48)
        self.assertEqual(
            records["different_counts_by_record_byte_index"],
            [29, 39, 37, 46, 32, 11, 27, 41, 38, 14, 39],
        )
        self.assertEqual(
            [row["different_byte_positions"] for row in body["structural_blocks"]],
            [36, 43, 48, 59, 55, 0, 52, 60, 0],
        )
        self.assertEqual(
            [row["records_with_any_difference"] for row in body["structural_blocks"]],
            [6, 6, 6, 7, 8, 0, 7, 8, 0],
        )
        self.assertEqual(body["whole_block_exact_equal_indices"], [5, 8])
        self.assertEqual(
            body["blocks_ranked_by_descending_positional_byte_mismatch"],
            [
                {"block_index": 7, "different_byte_positions": 60},
                {"block_index": 3, "different_byte_positions": 59},
                {"block_index": 4, "different_byte_positions": 55},
                {"block_index": 6, "different_byte_positions": 52},
                {"block_index": 2, "different_byte_positions": 48},
                {"block_index": 1, "different_byte_positions": 43},
                {"block_index": 0, "different_byte_positions": 36},
                {"block_index": 5, "different_byte_positions": 0},
                {"block_index": 8, "different_byte_positions": 0},
            ],
        )
        self.assertEqual(
            self.report["bounded_findings"][
                "unique_maximum_by_positional_byte_mismatch"
            ],
            {"block_index": 7, "different_byte_positions": 60},
        )
        bit_ranked = body["blocks_ranked_by_descending_bit_hamming_distance"]
        self.assertEqual(bit_ranked[0], {"block_index": 3, "bit_hamming_distance": 124})
        self.assertEqual(
            next(row for row in bit_ranked if row["block_index"] == 7),
            {"block_index": 7, "bit_hamming_distance": 108},
        )
        self.assertEqual(
            body["blocks_ranked_by_descending_unsigned_byte_l1_distance"][:2],
            [
                {"block_index": 3, "unsigned_byte_l1_distance": 4941},
                {"block_index": 7, "unsigned_byte_l1_distance": 4496},
            ],
        )
        self.assertEqual(
            body["blocks_ranked_by_descending_changed_record_count"][:2],
            [
                {"block_index": 4, "records_with_any_difference": 8},
                {"block_index": 7, "records_with_any_difference": 8},
            ],
        )
        shared = self.report["bounded_findings"][
            "zero_based_block_5_and_8_four_way_identity"
        ]
        self.assertTrue(shared["all_equal"])
        self.assertEqual(shared["bytes_each"], 88)
        self.assertEqual(
            shared["sha256"],
            "fc351643198ac4ec4e78649c99ad06b4cd45b554005990cdc70e520b49dd9bf0",
        )
        self.assertTrue(shared["each_block_is_uniform"])
        self.assertFalse(shared["uniform_byte_value_emitted"])
        self.assertFalse(shared["controller_meaning_assigned"])

    def test_transport_context_requires_two_profile_matched_pairs(self) -> None:
        transport = self.report["empirical_h3_transport_context"]
        self.assertEqual(
            transport["candidate_r20_first_799"]["different_byte_positions"], 357
        )
        self.assertEqual(
            transport["derived_power_payload"]["different_byte_positions"], 4
        )
        self.assertEqual(
            transport["derived_power_payload"]["different_decoded_prefix_offsets"],
            [1, 2, 3, 4],
        )
        self.assertEqual(
            transport["derived_pll_payload"]["different_byte_positions"], 0
        )
        self.assertFalse(transport["direct_WF20_T_vs_WF23_T_is_body_only_comparison"])

        design = self.report["color_experiment_design"]
        self.assertEqual(len(design["required_matched_pairs"]), 2)
        self.assertTrue(
            design["compare_within_each_profile_before_cross_profile_effect_comparison"]
        )
        self.assertTrue(design["same_DTM_atlas_and_controller_order_required"])
        self.assertFalse(design["brightness_only_change_counts_as_new_color"])
        self.assertFalse(design["header_body_block_or_record_splicing_allowed"])
        self.assertFalse(
            design["single_block_or_single_record_live_mutation_authorized"]
        )

    def test_integrity_cli_safety_and_no_raw_waveform_are_exact(self) -> None:
        without_integrity = dict(self.report)
        integrity = without_integrity.pop("integrity")
        self.assertEqual(
            integrity["canonical_sha256"],
            hashlib.sha256(_canonical_bytes(without_integrity)).hexdigest(),
        )

        rendered = json.dumps(self.report, ensure_ascii=False, sort_keys=True)
        for profile_id in audit.PROFILE_IDS:
            self.assertNotIn(
                profile_pack.load_profile(profile_id).plaintext.hex(), rendered
            )
        self.assertEqual(re.findall(r"[0-9A-Fa-f]{65,}", rendered), [])

        semantic = self.report["semantic_boundary"]
        self.assertTrue(semantic["block_is_structural_not_named_color_category"])
        self.assertTrue(semantic["record_is_structural_not_named_phase_group"])
        for key, value in semantic.items():
            if key not in {
                "block_is_structural_not_named_color_category",
                "record_is_structural_not_named_phase_group",
            }:
                self.assertFalse(value, key)

        safety = self.report["safety"]
        self.assertTrue(safety["offline_only"])
        for key, value in safety.items():
            if key != "offline_only":
                self.assertFalse(value, key)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "profile-color-delta.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tools.mf1750_spd1657_profile_color_delta",
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
