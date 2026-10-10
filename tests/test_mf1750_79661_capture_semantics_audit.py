from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools import mf1750_79661_capture_semantics_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class Capture79661SemanticsAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report()

    def test_capture_schema_time_and_byte_sequence_are_identity_pinned(self) -> None:
        identity = self.report["capture_identity"]
        self.assertEqual(identity["bytes"], 370_580)
        self.assertEqual(identity["sha256"], audit.CAPTURE_SHA256)
        self.assertEqual(identity["data_rows"], 12_722)
        self.assertEqual(
            identity["header_columns"], ["Time [s]", "Packet ID", "MOSI", "MISO"]
        )
        self.assertEqual(identity["line_ending"], "CRLF")

        decoded = self.report["decoded_sequences"]
        self.assertEqual(
            decoded["column_text_sha256"], audit.EXPECTED_COLUMN_TEXT_SHA256
        )
        self.assertEqual(decoded["packet_ids"]["first"], 0)
        self.assertEqual(decoded["packet_ids"]["last"], 12_721)
        self.assertTrue(decoded["packet_ids"]["contiguous_zero_based"])
        self.assertEqual(decoded["mosi"]["sha256"], audit.EXPECTED_MOSI_SHA256)
        self.assertEqual(decoded["mosi"]["unique_byte_value_count"], 72)
        self.assertFalse(decoded["mosi"]["raw_sequence_emitted"])
        self.assertEqual(decoded["miso"]["sha256"], audit.EXPECTED_MISO_SHA256)
        self.assertTrue(decoded["miso"]["all_decoded_values_zero"])
        self.assertFalse(decoded["miso"]["controller_readback_proven"])

    def test_timing_bursts_are_exact_but_not_promoted_to_transactions(self) -> None:
        timing = self.report["timing_only_segmentation"]
        self.assertEqual(timing["first_timestamp"], "2.4706995000")
        self.assertEqual(timing["last_timestamp"], "8.6219261000")
        self.assertEqual(timing["duration_ticks"], 61_512_266_000)
        self.assertEqual(
            timing["delta_big_endian_u64_sha256"],
            "30efc29d7f01f64db2cc52d6f3e57d13e2446365d5f05078e93f402a96fda601",
        )
        self.assertEqual(timing["largest_intra_run_delta_ticks"], 845_000)
        self.assertEqual(timing["smallest_inter_run_delta_ticks"], 9_790_000)
        self.assertEqual(timing["large_gap_count"], 15)
        self.assertEqual(
            timing["timing_run_lengths"],
            [57, 7, 2, 2, 6321, 4, 2, 543, 3, 1024, 1024, 1024, 1024, 1024, 657, 4],
        )
        self.assertTrue(
            all(
                count == 0
                for count in timing[
                    "timing_run_lengths_matching_declared_payload_sizes"
                ].values()
            )
        )
        self.assertTrue(
            all(
                count == 0
                for count in timing[
                    "timing_run_lengths_matching_command_plus_payload_sizes"
                ].values()
            )
        )
        self.assertFalse(timing["timing_gaps_are_transaction_boundaries_proven"])
        self.assertFalse(timing["timing_runs_are_spi_transactions_proven"])

    def test_every_known_payload_and_every_possible_window_are_checked(self) -> None:
        search = self.report["known_payload_search"]
        references = {row["name"]: row for row in search["references"]}
        self.assertEqual(len(references), 15)
        expected = {
            "legacy_wf_data_535": (
                535,
                "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b",
            ),
            "legacy_iar_data1_704": (
                704,
                "6dbd5a232419da637084683867933a7f60ce06d28a5034136d0f0efae3015e6a",
            ),
            "ff_704": (
                704,
                "24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f",
            ),
            "WF20_25_plain_800": (
                800,
                "1591338095e153bd0c7381b096e0b2e73d35131a700aab7c6cfde6c4756a7a8f",
            ),
            "WF20_25_first_799": (
                799,
                "3cab2e2915205400bfdb0c2749a3e1e606cb6f190b8f3638849c532449a0ca26",
            ),
            "WF23_25_plain_800": (
                800,
                "95e5fef3dc2946afdabbb35dceef1f1e48b8917d181946a82d06724c0a1c09d8",
            ),
            "WF23_25_first_799": (
                799,
                "2eeae0e8e6a936cfd55e0a215371c114c037dbb70e701d8b95a2f560387788fb",
            ),
            "legacy_iar_data0_1503": (
                1503,
                "eafe51e741f2e0922a2404abcc016473a203e9824bf91fd550f74ee6e05b8bc5",
            ),
            "legacy_iar_data0_first_799": (
                799,
                "9317dfc98fef531e0196b06ba2bce5d6bf9212a135b6fb677678949ac742338e",
            ),
        }
        for name, (length, digest) in expected.items():
            with self.subTest(name=name):
                self.assertEqual(references[name]["bytes"], length)
                self.assertEqual(references[name]["sha256"], digest)
        for row in references.values():
            self.assertEqual(row["exact_contiguous_match_count"], 0)
            self.assertLessEqual(row["longest_common_contiguous_fragment_bytes"], 15)
            self.assertLessEqual(row["maximal_fragment_unique_byte_count_max"], 3)
            self.assertFalse(row["raw_fragment_bytes_emitted"])

        families = {
            row["window_bytes"]: row for row in search["capture_window_families"]
        }
        self.assertEqual(set(families), {535, 704, 799, 800, 1503})
        for length, row in families.items():
            with self.subTest(length=length):
                self.assertEqual(row["ordered_window_count"], 12_722 - length + 1)
                self.assertEqual(row["known_reference_identity_match_count"], 0)
                self.assertTrue(row["every_possible_contiguous_window_scanned"])
                self.assertFalse(row["raw_window_bytes_emitted"])
        self.assertFalse(search["any_complete_known_payload_identity_present"])
        self.assertFalse(
            search["short_low_diversity_fragment_matches_are_payload_identity"]
        )

    def test_e6_and_adjacent_jd_source_matches_remain_bounded(self) -> None:
        cross = self.report["source_and_project_cross_check"]
        e6 = cross["known_e6_init"]
        self.assertEqual(e6["flattened_command_plus_parameter_bytes"], 48)
        self.assertEqual(e6["flattened_sha256"], audit.E6_INIT_FLAT_SHA256)
        self.assertEqual(e6["exact_contiguous_match_count"], 0)
        self.assertEqual(e6["longest_common_contiguous_fragment_bytes"], 3)
        self.assertTrue(e6["flattening_discards_dc_but_still_does_not_match"])
        self.assertTrue(e6["capture_may_begin_after_an_unobserved_init"])

        editor = cross["editor_residue"]
        self.assertEqual(editor["matching_path_records"], 5)
        self.assertEqual(
            editor["matching_path_basenames"],
            ["EPD_DATA.h", "EPD_init.h", "UartDataDeal.h", "pattern.h", "usart.h"],
        )
        self.assertEqual(editor["matching_delivered_project_directories"], [])
        self.assertTrue(editor["capture_filename_numeric_tail_matches_project_tail"])
        self.assertFalse(editor["filename_to_project_provenance_binding_proven"])
        self.assertFalse(editor["external_implementation_source_delivered"])

        adjacent = cross["nearest_adjacent_source"]
        self.assertEqual(adjacent["function"], "IC_JD79667_initialCode")
        self.assertEqual(adjacent["write_call_count"], 55)
        self.assertEqual(adjacent["literal_byte_call_count"], 51)
        self.assertEqual(adjacent["capture_start_aligned_literal_matches"], 15)
        self.assertEqual(adjacent["capture_start_aligned_literal_mismatches"], 36)
        self.assertFalse(adjacent["exact_function_byte_pattern_compatible"])
        self.assertFalse(adjacent["listed_in_current_uvprojx"])
        self.assertFalse(adjacent["matching_output_object_present"])

        observability = cross["command_data_observability"]
        self.assertTrue(
            observability[
                "adjacent_command_and_data_calls_use_same_mosi_transmit_primitive"
            ]
        )
        self.assertTrue(
            observability["adjacent_command_data_role_is_selected_by_dc_level"]
        )
        self.assertFalse(observability["capture_has_dc_column"])
        self.assertFalse(
            observability["adjacent_source_can_restore_roles_without_exact_provenance"]
        )

    def test_pinned_public_jd79661_source_is_positive_but_partial_evidence(
        self,
    ) -> None:
        public = self.report["pinned_public_jd79661_cross_check"]
        provenance = public["provenance"]
        self.assertEqual(provenance["commit"], audit.GXEPD2_COMMIT)
        self.assertTrue(provenance["immutable_commit_pinned"])
        self.assertTrue(
            provenance["identity_observed_in_explicitly_authorized_public_read"]
        )
        self.assertFalse(provenance["report_generation_performs_network_io"])
        self.assertEqual(
            provenance["file_identities"]["GxEPD2_213c_GDEY0213F51.cpp"],
            {
                "bytes": 31_749,
                "sha256": "a1ed92b7c8a33da2f2b9ae74c75d0f904275e78cd8304676aed8942dc5cd00b3",
            },
        )
        self.assertEqual(
            provenance["file_identities"]["GxEPD2_213c_GDEY0213F51.h"],
            {
                "bytes": 5_551,
                "sha256": "e92dbb60af5a8766da4497150bef0e0b9f7ec2d44d935b1c7b93546f2d1d2ccf",
            },
        )

        target = public["declared_target"]
        self.assertEqual(target["controller"], "JD79661")
        self.assertEqual(target["panel"], "GDEY0213F51")
        self.assertEqual((target["width"], target["height"]), (128, 250))
        self.assertEqual(target["two_bits_per_pixel_full_buffer_bytes"], 8_000)
        self.assertFalse(target["same_dimensions_as_external_editor_residue"])

        init = public["flattened_init_cross_check"]
        self.assertEqual(init["source_command_groups"], 15)
        self.assertEqual(init["flattened_command_plus_parameter_bytes"], 43)
        self.assertEqual(init["flattened_sha256"], audit.GXEPD2_INIT_FLAT_SHA256)
        self.assertEqual(init["exact_contiguous_match_count"], 0)
        self.assertEqual(init["first_timing_run_bytes"], 57)
        self.assertEqual(init["exact_source_groups_present_in_first_timing_run"], 10)
        self.assertEqual(
            init["longest_common_subsequence_bytes_in_first_timing_run"], 33
        )
        self.assertFalse(init["all_matched_source_groups_retain_source_order"])
        self.assertEqual(init["longest_common_contiguous_fragment_bytes"], 12)
        self.assertEqual(init["maximal_fragment_unique_byte_count_min"], 12)
        self.assertEqual(init["maximal_fragment_capture_offset"], 14)
        self.assertEqual(init["maximal_fragment_source_offset"], 8)
        self.assertTrue(init["fragment_is_positive_controller_family_compatibility"])
        self.assertFalse(init["fragment_proves_exact_generator_or_panel"])
        self.assertFalse(init["fragment_proves_command_data_roles_in_capture"])

        screen = public["default_screen_buffer_cross_check"]
        self.assertEqual(screen["source_full_buffer_transfer_bytes"], 8_000)
        self.assertEqual(screen["exact_default_white_transfer_match_count"], 0)
        self.assertEqual(
            screen["capture_longest_contiguous_default_white_value_run"], 5_776
        )
        self.assertEqual(
            screen["capture_total_default_white_encoded_value_count"], 11_552
        )
        self.assertFalse(screen["exact_source_default_screen_write_present"])
        self.assertFalse(screen["capture_completeness_proven"])

        adjudication = public["adjudication"]
        self.assertTrue(adjudication["jd79661_init_fragment_compatibility_present"])
        self.assertFalse(adjudication["exact_flattened_public_init_present"])
        self.assertFalse(adjudication["public_source_binds_capture_to_exact_panel"])
        self.assertFalse(adjudication["public_source_restores_full_transactions"])

    def test_ambiguity_verdict_integrity_and_safety_are_fail_closed(self) -> None:
        ambiguity = self.report["ambiguity_quantification"]
        self.assertEqual(ambiguity["adjacent_cut_positions"], 12_721)
        self.assertEqual(ambiguity["remaining_unobserved_cut_decisions"], 12_706)
        self.assertEqual(
            ambiguity["syntax_agnostic_segmentations_preserving_all_large_gap_cuts"],
            "2^12706",
        )
        self.assertEqual(ambiguity["unobserved_per_byte_dc_labelings"], "2^12722")
        self.assertFalse(ambiguity["command_data_boundaries_proven"])
        self.assertFalse(ambiguity["transaction_sequence_recovered"])

        verdict = self.report["adjudication"]
        self.assertEqual(
            verdict["verdict"],
            "JD79661_PUBLIC_INIT_FRAGMENT_COMPATIBILITY_ONLY__NO_EXACT_CONTIGUOUS_KNOWN_PAYLOAD_IDENTITY_OR_TRANSACTION_RECOVERY",
        )
        self.assertTrue(
            verdict["capture_has_public_jd79661_init_fragment_compatibility"]
        )
        self.assertFalse(
            verdict[
                "capture_contains_exact_contiguous_known_535_704_799_800_or_1503_payload_identity"
            ]
        )
        self.assertFalse(verdict["capture_is_spd1657_runtime_lut_upload_proven"])
        self.assertFalse(verdict["authorizes_live_hardware_action"])

        report = dict(self.report)
        canonical = report.pop("report_canonical_sha256")
        self.assertEqual(
            canonical, hashlib.sha256(_canonical_bytes(report)).hexdigest()
        )
        safety = self.report["safety"]
        self.assertTrue(safety["offline_read_only"])
        for key, value in safety.items():
            if key != "offline_read_only":
                self.assertFalse(value, key)

    def test_mutated_capture_is_rejected_before_semantic_analysis(self) -> None:
        original = audit.DEFAULT_CAPTURE.read_bytes()
        mutation = bytearray(original)
        mutation[-4] = ord("1") if mutation[-4] != ord("1") else ord("2")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "79661.csv"
            path.write_bytes(mutation)
            with self.assertRaisesRegex(
                audit.CaptureSemanticsAuditError, "SHA-256 changed"
            ):
                audit.load_capture(path)

    def test_cli_is_exclusive_and_emits_metadata_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "audit.json"
            command = [
                sys.executable,
                "-m",
                "tools.mf1750_79661_capture_semantics_audit",
                "--output",
                str(output),
                "--compact",
            ]
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr.decode())
            self.assertEqual(completed.stdout, b"")
            payload = output.read_text(encoding="utf-8")
            parsed = json.loads(payload)
            self.assertEqual(
                parsed["report_canonical_sha256"],
                self.report["report_canonical_sha256"],
            )
            self.assertNotIn("mosi_hex", payload.lower())
            self.assertNotIn("miso_hex", payload.lower())
            self.assertNotIn(audit.E6_INIT_FLAT.hex(), payload.lower())
            self.assertNotIn(audit.GXEPD2_INIT_FLAT.hex().lower(), payload.lower())
            capture = audit.load_capture()
            self.assertNotIn(capture.mosi[:32].hex(), payload.lower())

            repeated = subprocess.run(
                command,
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
            )
            self.assertEqual(repeated.returncode, 2)
            self.assertIn(b"refusing overwrite", repeated.stderr)


if __name__ == "__main__":
    unittest.main()
