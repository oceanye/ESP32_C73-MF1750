from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools import mf1750_solomon_adjacent_family_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = REPO_ROOT / "tools" / "mf1750_solomon_adjacent_family_audit.py"
EXPECTED_CANONICAL_SHA256 = (
    "c090d25412b609524495217e41a7ffaf7e911314b932486bce40cb614e8da8f2"
)


class Mf1750SolomonAdjacentFamilyAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report()

    def test_four_primary_documents_are_identity_and_page_text_pinned(self) -> None:
        documents = self.report["documents"]
        self.assertEqual(
            [item["id"] for item in documents],
            [item["id"] for item in audit.DOCUMENTS],
        )
        self.assertEqual(len(documents), 4)
        for document, spec in zip(documents, audit.DOCUMENTS, strict=True):
            self.assertEqual(document["bytes"], spec["bytes"])
            self.assertEqual(document["sha256"], spec["sha256"])
            self.assertEqual(document["page_count"], spec["page_count"])
            self.assertFalse(document["raw_pdf_or_full_page_text_emitted"])
            self.assertEqual(
                [page["pdf_page_1_based"] for page in document["pages"]],
                list(spec["pages"]),
            )
            for page in document["pages"]:
                self.assertTrue(page["all_required_anchors_present"])
                self.assertFalse(page["page_text_emitted"])
                self.assertEqual(
                    page["normalized_text_sha256"],
                    spec["pages"][page["pdf_page_1_based"]]["sha256"],
                )

    def test_eight_group_lineage_still_uses_seven_byte_groups(self) -> None:
        finding = self.report["cross_document_findings"]
        self.assertTrue(
            finding["ssd1683_and_ssd1683a_selected_waveform_geometry_equal"]
        )
        self.assertTrue(finding["eight_group_public_lineage_reaches_2023"])
        self.assertTrue(
            finding["eight_group_public_lineage_uses_seven_not_eleven_bytes_per_group"]
        )
        documents = {item["id"]: item for item in self.report["documents"]}
        for identity in ("SSD1683_REV1_0_JAN2021", "SSD1683A_REV1_1_MAR2023"):
            facts = documents[identity]["facts"]
            self.assertEqual(
                (
                    facts["groups_per_lut"],
                    facts["phases_per_group"],
                    facts["bytes_per_group_per_lut"],
                    facts["register_0x32_payload_bytes"],
                ),
                (8, 4, 7, 227),
            )
            self.assertEqual(facts["register_0x20_role"], "Master Activation")
            self.assertEqual(facts["register_0x21_role"], "Display Update Control 1")

    def test_same_named_zero_semantics_conflict_is_directly_preserved(self) -> None:
        conflict = self.report["cross_document_findings"][
            "same_named_zero_semantics_conflict"
        ]
        self.assertEqual(conflict["fields"], ["RP", "SR"])
        self.assertEqual(conflict["SSD1681"]["RP_zero"], "repeat times = 1")
        self.assertEqual(conflict["SSD1681"]["SR_zero"], "repeat times = 1")
        self.assertEqual(conflict["SSD1683"]["RP_zero"], "group skipped")
        self.assertEqual(conflict["SSD1683"]["SR_zero"], "sub-group skipped")
        self.assertFalse(conflict["semantics_equal"])

    def test_ssd2677_exposes_architecture_but_not_runtime_abi(self) -> None:
        documents = {item["id"]: item for item in self.report["documents"]}
        facts = documents["SSD2677_REV1_0_MAR2024"]["facts"]
        self.assertEqual(facts["resolution"], {"source": 960, "gate": 680})
        self.assertTrue(facts["programmable_waveform_advertised"])
        self.assertEqual(facts["waveform_otp_bytes"], 6144)
        self.assertTrue(facts["two_chip_cascade_documented"])
        self.assertEqual(facts["cascade_max_resolution"], {"source": 1920, "gate": 680})
        self.assertFalse(facts["public_runtime_waveform_write_command_found"])
        self.assertTrue(facts["unshown_commands_declared_reserved"])
        finding = self.report["cross_document_findings"]
        self.assertTrue(finding["ssd2677_programmable_waveform_and_cascade_public"])
        self.assertFalse(finding["ssd2677_runtime_waveform_write_ABI_public"])

    def test_adjudication_refuses_field_command_and_electrical_transfer(self) -> None:
        decision = self.report["adjudication"]
        for key in (
            "SPD1657_or_E2802_runtime_ABI_recovered",
            "local_11_byte_field_layout_recovered",
            "local_phase_count_recovered",
            "local_zero_or_FF_semantics_recovered",
            "controller_side_complement_decode_recovered",
            "dual_controller_load_commit_or_rollback_contract_recovered",
            "adjacent_command_field_or_electrical_transfer_allowed",
            "ssd2677_cascade_wiring_is_SPD1657_as_built_proof",
            "hardware_experiment_or_payload_generation_authorized",
        ):
            self.assertFalse(decision[key], key)
        targets = self.report["cross_document_findings"][
            "target_numbers_found_in_selected_manual_text"
        ]
        self.assertEqual(set(targets), {"799", "704", "1503", "2508", "535"})
        self.assertFalse(any(targets.values()))

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
                "raw_key_plaintext_record_or_waveform_bytes_emitted"
            ]
        )
        self.assertTrue(self.report["safety"]["offline_only"])
        for key, value in self.report["safety"].items():
            if key != "offline_only":
                self.assertFalse(value, key)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "adjacent-family.json"
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
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8")), self.report
            )
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
