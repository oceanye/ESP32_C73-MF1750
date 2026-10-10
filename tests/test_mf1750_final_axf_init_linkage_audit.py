from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = REPO_ROOT / "tools" / "mf1750_final_axf_init_linkage_audit.py"
SPEC = importlib.util.spec_from_file_location("final_axf_init_linkage", TOOL_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load final AXF init/linkage audit")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class FinalAxfInitLinkageAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit.build_report()

    def test_all_seven_final_axf_map_pairs_are_identity_pinned(self) -> None:
        images = self.report["images"]
        self.assertEqual(len(images), 7)
        self.assertEqual(
            {image["name"] for image in images},
            {item["name"] for item in audit.EXPECTED_IMAGES},
        )
        self.assertTrue(all(image["map"]["dormant_nootp_removed"] for image in images))
        self.assertTrue(all(image["axf"]["epd_initial_bytes"] > 0 for image in images))

    def test_five_images_share_the_exact_dual_cs_factory_init(self) -> None:
        shared = self.report["shared_dual_factory_init"]
        self.assertEqual(shared["image_count"], 5)
        self.assertEqual(shared["images"], list(audit.EXPECTED_DUAL_SET))
        self.assertEqual(
            shared["normalized_trace_sha256"],
            "9eb1db5d22278d66a5483c38833b20f7ef0cffa3065b16c01d31841346b7fd31",
        )
        self.assertEqual(shared["transaction_count"], 22)
        self.assertTrue(shared["all_writes_use_both_chip_selects"])
        self.assertEqual(shared["psr_bytes"], [0x5F, 0x69])
        self.assertFalse(shared["psr_lut_en"])
        self.assertEqual(shared["cascade_e0_value"], 0x01)
        self.assertEqual(shared["tres_per_controller"], [512, 600])
        self.assertFalse(shared["runtime_lut_upload_in_trace"])

    def test_no_final_image_contains_the_named_or_fingerprinted_800_loader(
        self,
    ) -> None:
        search = self.report["same_build_loader_search"]
        self.assertEqual(search["axf_count"], 7)
        self.assertEqual(search["map_count"], 7)
        self.assertTrue(search["all_markers_and_symbols_absent"])
        self.assertFalse(search["same_build_800_byte_loader_found"])
        for image in self.report["images"]:
            self.assertEqual(image["loader_search"]["forbidden_symbol_hits"], [])
            self.assertEqual(image["loader_search"]["forbidden_marker_hits"], [])
            self.assertFalse(
                image["loader_search"]["named_or_fingerprinted_800_loader_found"]
            )

    def test_wf23_is_vendor_supplied_but_editor_only(self) -> None:
        linkage = self.report["wf23_linkage"]
        self.assertEqual(linkage["path"], "Projects/MDK-ARM/12")
        self.assertEqual(linkage["initializer_bytes"], 876)
        self.assertEqual(
            linkage["initializer_sha256"],
            "d01caa5581b69ab82d7bb34175d21220e4c08582eb55ce5f9f6391700cd6ebb4",
        )
        self.assertTrue(linkage["archive_entry_matches_extracted_file"])
        self.assertFalse(linkage["listed_in_keil_project"])
        self.assertTrue(linkage["opened_as_editor_document"])
        self.assertEqual(linkage["editor_document_match_count"], 1)
        self.assertFalse(linkage["linked_final_image_reference_found"])
        self.assertEqual(
            linkage["classification"], "vendor-supplied-editor-only-not-built"
        )
        self.assertFalse(linkage["waveform_plaintext_or_key_emitted"])

    def test_verdict_preserves_the_runtime_evidence_boundary(self) -> None:
        verdict = self.report["verdict"]
        self.assertTrue(verdict["same_panel_factory_dual_init_proven"])
        self.assertTrue(verdict["wf23_vendor_identity_proven"])
        self.assertFalse(verdict["wf23_linked_or_reachable_in_final_images"])
        self.assertFalse(verdict["same_build_800_byte_loader_proven"])
        self.assertFalse(verdict["dual_runtime_mode1_contract_proven"])
        self.assertFalse(verdict["h3_live_execution_unlocked_by_this_audit"])

    def test_cli_emits_the_same_compact_offline_report(self) -> None:
        run = subprocess.run(
            [sys.executable, str(TOOL_PATH), "--compact"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        report = json.loads(run.stdout)
        self.assertEqual(report["kind"], audit.KIND)
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["scope"]["identity_pinned_final_axf_map_pairs"], 7)
        self.assertFalse(report["scope"]["hardware_accessed"])
        self.assertFalse(report["scope"]["serial_or_com_accessed"])
        self.assertFalse(report["scope"]["device_network_accessed"])
        self.assertFalse(report["scope"]["waveform_plaintext_or_key_emitted"])


if __name__ == "__main__":
    unittest.main()
