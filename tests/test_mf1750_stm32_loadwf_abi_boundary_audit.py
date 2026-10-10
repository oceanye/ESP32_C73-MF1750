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
from tools import mf1750_stm32_loadwf_abi_boundary_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class Stm32LoadwfAbiBoundaryAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report()

    def test_sample_ingress_checks_counter_bytes_then_discards_length(self) -> None:
        sample = self.report["source_ingress"]["sample_reg_tool_template"]
        self.assertEqual(sample["command"], "0x20")
        self.assertEqual(sample["counter_field_offsets"], [4, 5])
        self.assertEqual(sample["counter_byte_order"], "big-endian")
        self.assertEqual(sample["checksum_covered_range"], "dataBuff[6 : 6 + COUNTER]")
        self.assertEqual(sample["checksum_field_offset"], "6 + COUNTER")
        self.assertFalse(sample["command_header_covered_by_checksum"])
        self.assertFalse(sample["counter_field_covered_by_checksum"])
        self.assertEqual(sample["loadwf_argument"], "&dataBuff[6]")
        self.assertFalse(sample["counter_passed_to_loadwf"])
        self.assertEqual(sample["exact_length_comparison_count_in_loadwf_case"], 0)
        self.assertFalse(sample["known_size_gate_present"])

        self.assertTrue(sample["receive_function_is_unimplemented_stub"])
        self.assertFalse(sample["usbcdc_header_present_in_supplied_tree"])
        self.assertFalse(sample["sample_main_is_keil_project_entry"])
        self.assertTrue(sample["user_main_is_keil_project_entry"])

    def test_both_supplied_ingress_designs_fail_to_enforce_consumer_length(
        self,
    ) -> None:
        legacy = self.report["source_ingress"]["legacy_uart_ingress"]
        self.assertEqual(legacy["supplied_length_parameter"], "buff_len")
        self.assertEqual(legacy["fixed_copy_bytes"], 535)
        self.assertTrue(legacy["fixed_copy_uses_wf_data_length"])
        self.assertFalse(legacy["function_body_uses_supplied_length"])

        boundary = self.report["cross_layer_length_boundary"]
        self.assertTrue(boundary["producer_checksum_covers_exactly_counter_bytes"])
        self.assertFalse(boundary["producer_passes_length_to_consumer"])
        self.assertFalse(boundary["consumer_abi_has_total_length_argument"])
        self.assertEqual(boundary["consumer_unconditionally_copies_bytes"], 544)
        self.assertEqual(boundary["consumer_reads_length_field_offsets"], [544, 545])
        self.assertFalse(boundary["consumer_checks_caller_bound_before_fixed_copy"])
        self.assertFalse(boundary["counter_at_least_546_gate_present"])
        self.assertFalse(boundary["exact_535_544_546_799_800_842_or_876_gate_present"])
        self.assertFalse(boundary["bytes_read_beyond_counter_are_checksum_covered"])
        self.assertTrue(boundary["contract_gap_proven"])
        self.assertFalse(boundary["actual_storage_out_of_bounds_proven"])
        self.assertFalse(boundary["exploitable_path_proven"])

    def test_exact_544_byte_partition_corrects_byte_five_wording(self) -> None:
        exact = self.report["exact_armcc_decoded_byte_use"]
        self.assertEqual(exact["evidence_grade"], "A")
        self.assertEqual(exact["decoded_working_buffer_bytes"], 544)
        self.assertEqual(
            [(row["decoded_range"], row["bytes"]) for row in exact["ranges"]],
            [
                ("[0,5)", 5),
                ("[5,6)", 1),
                ("[6,7)", 1),
                ("[7,535)", 528),
                ("[535,544)", 9),
            ],
        )
        self.assertEqual(exact["r20"]["bytes"], 535)
        self.assertEqual(exact["r20"]["source_range"], "decoded[0:535]")
        self.assertEqual(exact["r21"]["bytes"], 704)
        self.assertFalse(exact["r21"]["caller_wrapper_source"])
        self.assertFalse(exact["decoded_byte_5_not_written_anywhere"])
        self.assertIn("still forwarded", exact["decoded_byte_5_verdict"])
        self.assertFalse(exact["decoded_bytes_535_through_543_emitted"])

    def test_candidate_geometry_is_not_promoted_to_the_mode0_object(self) -> None:
        candidates = self.report["candidate_800_records"]
        self.assertEqual(candidates["artifact_geometry_evidence_grade"], "A")
        self.assertEqual(
            candidates["promotion_to_current_armcc_abi_evidence_grade"], "U"
        )
        for profile_id, wrapper_bytes in (("WF20_25", 842), ("WF23_25", 876)):
            row = candidates["profiles"][profile_id]
            self.assertEqual(row["wrapper_bytes"], wrapper_bytes)
            self.assertEqual(row["decoded_bytes"], 800)
            self.assertEqual(row["layout_formula"], "7 + 9 * (8 * 11) + 1")
            self.assertEqual(row["sentinel_offset"], 799)
            self.assertTrue(row["sentinel_is_zero"])
        self.assertFalse(candidates["current_armcc_loader_compatible"])
        self.assertFalse(candidates["same_object_799_byte_write_present"])
        self.assertTrue(candidates["first_799_r20_is_cross_generation_hypothesis"])
        self.assertFalse(candidates["first_799_r20_live_eligible"])

    def test_category_phase_and_electrical_provenance_stays_bounded(self) -> None:
        semantics = self.report["semantic_provenance"]
        category = semantics["category"]
        self.assertEqual(
            category["legacy_535_labels"],
            ["VCOM", "Black", "White", "Yellow", "Red", "Power"],
        )
        self.assertFalse(category["current_armcc_parser_present"])
        self.assertFalse(category["unique_category_to_pixel_code_mapping_proven"])
        self.assertEqual(category["semantic_evidence_grade"], "U")

        phase = semantics["phase"]
        self.assertTrue(phase["eleven_byte_group_geometry_observed"])
        self.assertFalse(phase["current_armcc_eleven_byte_parser_present"])
        self.assertFalse(phase["eleven_bytes_are_phase_durations_proven"])
        self.assertFalse(phase["phase_order_or_polarity_proven"])

        electrical = semantics["electrical"]
        self.assertTrue(electrical["decoded_0_to_4_dedicated_pwr_binding"])
        self.assertTrue(electrical["decoded_6_dedicated_pll_binding"])
        self.assertFalse(
            electrical["decoded_5_dedicated_vcom_binding_in_current_loadwf"]
        )
        self.assertTrue(electrical["decoded_5_forwarded_inside_r20"])
        self.assertFalse(electrical["panel_or_fpl_limits_proven"])

    def test_temperature_ranges_are_explicitly_filename_only_inference(self) -> None:
        temperature = self.report["temperature_name_semantics"]
        identifiers = {
            row["identifier"]: row
            for row in temperature["observed_waveform_identifiers"]
        }
        self.assertEqual(
            set(identifiers),
            {"WF00_05", "WF20_25", "WF23_25", "WF24_24", "WF25_25"},
        )
        self.assertEqual(identifiers["WF20_25"]["numeric_pair"], [20, 25])
        self.assertEqual(identifiers["WF23_25"]["numeric_pair"], [23, 25])
        self.assertFalse(
            temperature["wf20_header_preamble_has_explicit_temperature_statement"]
        )
        self.assertFalse(
            temperature["wf23_header_preamble_has_explicit_temperature_statement"]
        )
        self.assertFalse(temperature["explicit_celsius_unit_statement_found"])
        self.assertFalse(
            temperature["filename_numeric_components_parsed_by_supplied_loader"]
        )
        self.assertFalse(
            temperature["filename_numeric_components_used_by_supplied_project_selector"]
        )
        self.assertFalse(temperature["wf23_listed_in_keil_project"])

        local = temperature["local_profile_pack"]
        self.assertTrue(local["uses_apparent_temperature_constant_names"])
        for profile_id in ("WF20_25", "WF23_25"):
            self.assertTrue(
                local["profiles"][profile_id]["values_equal_filename_digits"]
            )
            self.assertFalse(
                local["profiles"][profile_id]["supplier_qualified_by_this_mapping"]
            )

        classification = temperature["classification"]
        self.assertEqual(
            classification["name_to_band_mapping"], "filename-only inference"
        )
        self.assertEqual(classification["inference_evidence_grade"], "C")
        self.assertEqual(classification["temperature_semantics_evidence_grade"], "U")
        self.assertFalse(classification["safe_use_band_authority"])

    def test_integrity_cli_and_report_are_metadata_only(self) -> None:
        without_integrity = dict(self.report)
        integrity = without_integrity.pop("integrity")
        self.assertEqual(
            integrity["canonical_sha256"],
            hashlib.sha256(_canonical_bytes(without_integrity)).hexdigest(),
        )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "audit.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/mf1750_stm32_loadwf_abi_boundary_audit.py",
                    "--output",
                    str(output),
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr.decode())
            self.assertEqual(completed.stdout, b"")
            payload = output.read_text(encoding="utf-8")
            cli_report = json.loads(payload)
            self.assertEqual(cli_report["integrity"], integrity)

            for profile_id in ("WF20_25", "WF23_25"):
                raw_plaintext = profile_pack.load_profile(profile_id).plaintext.hex()
                self.assertNotIn(raw_plaintext, payload)
            self.assertEqual(re.findall(r"[0-9A-Fa-f]{65,}", payload), [])

        safety = self.report["safety"]
        self.assertTrue(safety["offline_only"])
        for key, value in safety.items():
            if key != "offline_only":
                self.assertFalse(value, key)
        self.assertFalse(self.report["adjudication"]["authorizes_live_hardware_action"])


if __name__ == "__main__":
    unittest.main()
