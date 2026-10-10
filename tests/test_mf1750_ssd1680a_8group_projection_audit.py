from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools import mf1750_ssd1680a_8group_projection_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = REPO_ROOT / "tools" / "mf1750_ssd1680a_8group_projection_audit.py"
EXPECTED_CANONICAL_SHA256 = (
    "513b6ddeedcf3933af8577eb79fc28f73253f5cde94a92e1f2abe21fd5a3dcbe"
)


class Mf1750Ssd1680aEightGroupProjectionAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report()

    def test_primary_manual_identity_and_exact_group_layout(self) -> None:
        source = self.report["primary_adjacent_document"]
        self.assertEqual(source["bytes"], 1_257_063)
        self.assertEqual(
            source["sha256"],
            "92ccb43dbcb847707ff907de9989ea18214c968f3584b7493e7460d9268a43bc",
        )
        self.assertEqual(source["page_count"], 47)
        self.assertEqual(source["extractor"]["version"], "1.28.2")
        self.assertEqual(
            [page["pdf_page_1_based"] for page in source["pages"]],
            [14, 15, 25, 29],
        )
        for page in source["pages"]:
            self.assertTrue(page["all_required_anchors_present"])
            self.assertFalse(page["page_text_emitted"])
            self.assertEqual(
                page["normalized_text_sha256"],
                audit.PAGE_TEXT_SHA256[page["pdf_page_1_based"]],
            )

        facts = source["facts"]
        self.assertEqual(
            (facts["lut_count"], facts["groups_per_lut"], facts["group_bytes_per_lut"]),
            (4, 8, 7),
        )
        self.assertEqual(facts["bytes_per_lut"], 56)
        fields = facts["field_layout_zero_based_within_one_lut_group"]
        self.assertEqual(fields["repeat_RP"]["byte_offset"], 0)
        self.assertEqual(fields["phase_A_to_D"]["byte_offsets_inclusive"], [1, 4])
        self.assertEqual(fields["phase_A_to_D"]["VS_bits"], "7:6")
        self.assertEqual(fields["phase_A_to_D"]["TP_bits"], "5:0")
        self.assertEqual(fields["state_repeat_AB"]["byte_offset"], 5)
        self.assertEqual(fields["state_repeat_CD"]["byte_offset"], 6)
        self.assertEqual(facts["register_0x32"]["payload_bytes"], 227)
        self.assertEqual(facts["full_waveform_setting"]["bytes"], 233)

    def test_command_roles_are_incompatible_with_local_r20_r21_payloads(self) -> None:
        boundary = self.report["hybrid_lineage_boundary"]
        self.assertEqual(
            boundary["local_observed_geometry"],
            {
                "groups_per_category": 8,
                "record_bytes": 11,
                "category_bytes": 88,
                "candidate_R20_bytes": 799,
                "candidate_R21_bytes": 704,
            },
        )
        adjacent = boundary["SSD1680A"]
        self.assertTrue(adjacent["matches_local_group_count"])
        self.assertFalse(adjacent["matches_local_record_width"])
        self.assertFalse(adjacent["command_0x20_role_matches_local_payload_sink"])
        self.assertFalse(adjacent["command_0x21_role_matches_local_payload_sink"])
        self.assertEqual(adjacent["waveform_write_command"], "0x32")
        self.assertEqual(adjacent["waveform_write_bytes"], 227)

    def test_every_contiguous_projection_is_valid_and_therefore_nonidentifying(
        self,
    ) -> None:
        active = self.report["local_evidence"]["active_aggregate"]
        self.assertEqual((active["category_count"], active["record_count"]), (41, 328))
        for view_name in ("raw", "bitwise_complement"):
            view = active["views"][view_name]
            self.assertEqual(view["candidate_window_count"], 5)
            self.assertTrue(view["all_windows_accept_every_record_by_bit_domain"])
            self.assertFalse(view["unique_window_identified_by_validity"])
            self.assertEqual(
                [
                    row["candidate_start_offset_in_local_11_byte_record"]
                    for row in view["candidate_windows"]
                ],
                [0, 1, 2, 3, 4],
            )
            for row in view["candidate_windows"]:
                self.assertEqual(
                    row["syntactically_valid_under_adjacent_bit_domains"], 328
                )
                self.assertEqual(
                    row["invalid_record_count_under_adjacent_bit_domains"], 0
                )
                self.assertEqual(row["unexplained_local_bytes_per_record"], 4)
                self.assertFalse(
                    row["field_names_or_zero_semantics_apply_to_local_format_proven"]
                )
                self.assertFalse(row["raw_records_or_field_values_emitted"])

    def test_hybrid_eight_by_eleven_relation_is_not_an_abi(self) -> None:
        boundary = self.report["hybrid_lineage_boundary"]
        self.assertTrue(
            boundary[
                "no_single_adjacent_manual_matches_group_count_record_width_command_role_and_payload_length"
            ]
        )
        self.assertTrue(
            boundary[
                "hybrid_8_groups_times_11_bytes_is_an_arithmetic_recombination_not_an_ABI"
            ]
        )
        self.assertTrue(boundary["SPD1656"]["VCOM_matches_local_record_width"])
        self.assertFalse(boundary["SPD1656"]["VCOM_matches_local_group_count"])
        self.assertEqual(
            (
                boundary["SPD1656"]["VCOM_group_count"],
                boundary["SPD1656"]["VCOM_group_bytes"],
                boundary["SPD1656"]["VCOM_R20_payload_bytes"],
            ),
            (20, 11, 220),
        )
        matrix = boundary["candidate_layout_matrix"]
        self.assertEqual(
            matrix["SSD1680A"]["direct_source_layout"],
            "1 RP + 4 combined VS/TP + 2 SR = 7 bytes",
        )
        self.assertEqual(
            matrix["unpublished_phase_expansion"]["arithmetic_only"],
            "1 RP + 8 combined VS/TP + 2 SR = 11 bytes",
        )
        self.assertFalse(
            matrix["unpublished_phase_expansion"][
                "eight_phase_two_SR_controller_source_found"
            ]
        )
        self.assertEqual(
            matrix["unpublished_phase_expansion"][
                "symmetric_one_SR_per_phase_pair_would_instead_require_bytes"
            ],
            13,
        )
        for item in matrix.values():
            self.assertFalse(item["transfer_allowed"])

    def test_adjudication_preserves_non_portability_and_hardware_boundary(self) -> None:
        decision = self.report["adjudication"]
        self.assertTrue(decision["eight_group_similarity_is_real_but_insufficient"])
        for key in (
            "four_extra_local_bytes_per_record_explained",
            "contiguous_seven_byte_alignment_identified",
            "raw_or_complement_view_identified",
            "local_RP_VS_TP_SR_field_names_proven",
            "local_zero_skip_repeat_or_voltage_semantics_proven",
            "SSD1680A_command_0x20_or_0x21_field_transfer_allowed",
            "SSD1680A_electrical_code_or_timing_transfer_allowed",
            "hardware_experiment_or_payload_generation_authorized",
        ):
            self.assertFalse(decision[key], key)

    def test_report_is_deterministic_metadata_only_and_cli_is_exclusive(self) -> None:
        first = audit.build_report()
        second = audit.build_report()
        self.assertEqual(first, second)
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
            run = subprocess.run(
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
            self.assertEqual(run.returncode, 0, run.stderr)
            emitted = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(emitted, self.report)
            duplicate = subprocess.run(
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
            self.assertEqual(duplicate.returncode, 2)
            self.assertIn("already exists", duplicate.stderr)


if __name__ == "__main__":
    unittest.main()
