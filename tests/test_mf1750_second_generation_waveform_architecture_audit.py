from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import pymupdf

from tools import mf1750_second_generation_waveform_architecture_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = (
    REPO_ROOT / "tools" / "mf1750_second_generation_waveform_architecture_audit.py"
)
EXPECTED_CANONICAL_SHA256 = (
    "aaee09b1ecea72e4efec76d6b5a6bddc2509cc3ad13c1ba911c672198742de42"
)


class Mf1750SecondGenerationWaveformArchitectureAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report()

    def test_documents_are_identity_page_and_anchor_pinned(self) -> None:
        documents = self.report["documents"]
        self.assertEqual(
            [document["id"] for document in documents],
            [spec["id"] for spec in audit.PDF_DOCUMENTS],
        )
        self.assertEqual(len(documents), 4)
        for document, spec in zip(documents, audit.PDF_DOCUMENTS, strict=True):
            self.assertEqual(document["bytes"], spec["bytes"])
            self.assertEqual(document["sha256"], spec["sha256"])
            self.assertEqual(document["page_count"], spec["page_count"])
            self.assertFalse(document["raw_pdf_or_full_page_text_emitted"])
            self.assertEqual(
                [page["pdf_page_1_based"] for page in document["pages"]],
                list(spec["pages"]),
            )
            for page in document["pages"]:
                page_spec = spec["pages"][page["pdf_page_1_based"]]
                self.assertEqual(
                    page["normalized_text_utf8_bytes"], page_spec["utf8_bytes"]
                )
                self.assertEqual(page["normalized_text_sha256"], page_spec["sha256"])
                self.assertTrue(page["all_required_anchors_present"])
                self.assertFalse(page["page_text_emitted"])

    def test_first_party_sources_place_t2000_as_external_tcon_layer(self) -> None:
        documents = {document["id"]: document for document in self.report["documents"]}
        t2000 = documents["EINK_HIMAX_T2000_2024"]["facts"]
        self.assertEqual(
            t2000["hardware_type"],
            "standalone color-ePaper timing-controller ASIC (TCON)",
        )
        self.assertEqual(t2000["host_inputs"], ["MIPI-DSI", "USB 3.0", "SPI"])
        self.assertEqual(t2000["panel_side_outputs"], ["mLVDS", "TTL"])
        self.assertTrue(t2000["controls_voltage_timing_and_duration"])
        self.assertTrue(t2000["temperature_compensation"])

        current = documents["MF17506_M009F_T_VENDOR_SPEC"]["facts"]
        self.assertEqual(current["pixel_input_bits"], 3)
        self.assertEqual(current["host_interface"], "SPI")
        self.assertEqual(current["documented_driver_topology"], "SPD1657 x2")
        self.assertEqual(current["reference_circuit_part_name"], "SPD1657B")
        self.assertEqual(current["waveform_storage"], "on-chip OTP")

        finding = self.report["architecture_findings"]
        self.assertTrue(finding["t2000_hardware_asic_confirmed_by_first_party"])
        self.assertTrue(finding["t2000_is_controller_silicon_not_electrophoretic_film"])
        self.assertTrue(
            finding["external_t2000_pcb_implementation_demonstrated_by_supplier"]
        )
        self.assertFalse(
            finding["documented_drop_in_t2000_compatibility_with_current_spi_module"]
        )
        self.assertFalse(finding["complete_public_bare_chip_design_package_proven"])
        self.assertFalse(finding["absolute_as_built_t2000_absence_proven"])

    def test_second_generation_announcement_is_pinned_without_merging_claims(
        self,
    ) -> None:
        announcement = self.report["eink_second_generation_announcement"]
        spec = audit.ANNOUNCEMENT_SPEC
        self.assertEqual(announcement["bytes"], spec["bytes"])
        self.assertEqual(announcement["sha256"], spec["sha256"])
        self.assertEqual(
            announcement["normalized_visible_sha256"],
            spec["normalized_visible_sha256"],
        )
        self.assertTrue(announcement["all_required_anchors_present"])
        self.assertFalse(announcement["raw_html_or_visible_text_emitted"])
        facts = announcement["facts"]
        self.assertTrue(facts["new_waveform_uses_existing_particles_for_color_mixing"])
        self.assertTrue(
            facts[
                "new_waveform_plus_upgraded_three_bit_chipset_claims_eight_primary_colors"
            ]
        )
        self.assertTrue(facts["compatible_chip_ecosystem_names_solomon_systech"])
        self.assertEqual(
            facts["t2000_spectra6_new_colors_named"],
            ["cyan", "light green", "orange"],
        )
        self.assertTrue(
            facts[
                "eight_primary_and_t2000_color_statements_are_not_arithmetically_merged"
            ]
        )

    def test_local_profiles_preserve_geometry_without_semantic_upgrade(self) -> None:
        local = self.report["local_vendor_profiles"]
        geometry = local["shared_geometry"]
        self.assertEqual(geometry["decoded_bytes"], 800)
        self.assertEqual(geometry["arithmetic"], "7 + 9 * 8 * 11 + 1 = 800")
        self.assertEqual(geometry["structural_block_count"], 9)
        self.assertEqual(geometry["records_per_structural_block"], 8)
        self.assertEqual(geometry["structural_record_bytes"], 11)
        self.assertEqual(geometry["candidate_r20_bytes"], 799)
        self.assertEqual(geometry["constructed_r21_bytes"], 704)
        self.assertFalse(geometry["constructed_r21_is_vendor_profile_bytes"])
        self.assertEqual(local["wf20_wf23_positional_byte_differences"], 357)
        self.assertFalse(
            local["block_or_record_color_phase_or_electrical_semantics_assigned"]
        )

        self.assertEqual(set(local["profiles"]), {"WF20_25", "WF23_25"})
        for profile in local["profiles"].values():
            self.assertEqual(profile["decoded_bytes"], 800)
            self.assertEqual(profile["candidate_r20_bytes"], 799)
            self.assertTrue(
                profile["source_declares_e5_two_bit_development_environment"]
            )
            self.assertFalse(
                profile["raw_profile_wrapper_plaintext_or_include_bytes_emitted"]
            )

    def test_archived_library_markers_do_not_become_mode_one_loader_proof(self) -> None:
        legacy = self.report["archived_e2802_library"]
        self.assertEqual(
            legacy["active_marker_projection"],
            {"E5_3Bit_Mode": 0, "WF_DeCode_SIZE": 544, "WF_SIZE": 535},
        )
        self.assertTrue(legacy["ascii_marker_presence"]["E5_3Bit_Mode 0"])
        self.assertFalse(legacy["ascii_marker_presence"]["E5_3Bit_Mode 1"])
        self.assertFalse(legacy["mode_1_or_800_byte_loader_bound_by_these_markers"])
        self.assertFalse(
            legacy["incidental_untyped_decimal_occurrences_interpreted_as_abi"]
        )

    def test_public_architecture_does_not_recover_local_runtime_abi(self) -> None:
        decision = self.report["second_generation_to_local_abi_adjudication"]
        self.assertTrue(
            decision["second_generation_three_bit_color_mixing_architecture_public"]
        )
        self.assertTrue(
            decision["solomon_systech_named_as_compatible_chip_ecosystem_member"]
        )
        for term_map in decision[
            "official_t2000_documents_selected_runtime_abi_term_presence"
        ].values():
            self.assertEqual(set(term_map), set(audit.RUNTIME_ABI_TERMS))
            self.assertFalse(any(term_map.values()))
        for key in (
            "announcement_names_spd1657",
            "announcement_names_e2802",
            "official_t2000_runtime_waveform_write_abi_disclosed_in_pinned_sources",
            "local_module_three_bit_input_proves_second_generation_waveform",
            "local_profile_800_byte_length_proves_second_generation_waveform",
            "nine_local_structural_blocks_map_to_eight_primary_colors",
            "nine_local_structural_blocks_map_to_one_plus_eight_categories",
            "wf20_or_wf23_proven_t2000_profile",
            "wf20_or_wf23_proven_spd1657_second_generation_profile",
            "archived_mode_0_535_marker_closes_mode_1_800_loader",
            "eight_primary_statement_and_t2000_three_named_colors_may_be_added",
            "category_order_recovered",
            "eleven_byte_record_field_layout_recovered",
            "phase_repeat_level_duration_or_voltage_fields_recovered",
            "controller_side_decode_recovered",
            "dual_controller_load_commit_or_rollback_recovered",
            "runtime_to_otp_recovery_contract_recovered",
        ):
            self.assertFalse(decision[key], key)

    def test_pdf_identity_mutation_fails_before_evidence_is_accepted(self) -> None:
        spec = dict(audit.PDF_DOCUMENTS[0])
        original = Path(spec["path"]).read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            tampered = Path(directory) / "T2000.pdf"
            tampered.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
            spec["path"] = tampered
            with self.assertRaisesRegex(
                audit.SecondGenerationArchitectureAuditError,
                "identity changed",
            ):
                audit._pdf_evidence(spec, pymupdf)

    def test_report_is_deterministic_metadata_only_and_cli_is_exclusive(self) -> None:
        self.assertEqual(audit.build_report(), self.report)
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
        self.assertFalse(
            self.report["material_handling"][
                "profile_plaintext_or_waveform_bytes_emitted"
            ]
        )
        self.assertTrue(self.report["safety"]["offline_only"])
        for key, value in self.report["safety"].items():
            if key != "offline_only":
                self.assertFalse(value, key)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "second-generation.json"
            environment = dict(os.environ)
            environment["PYTHONIOENCODING"] = "utf-8"
            command = [
                sys.executable,
                str(TOOL_PATH),
                "--compact",
                "--output",
                str(output),
            ]
            run = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8")), self.report
            )
            duplicate = subprocess.run(
                command,
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
