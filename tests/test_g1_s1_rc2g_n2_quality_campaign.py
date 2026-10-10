from __future__ import annotations

from dataclasses import replace
import hashlib
import inspect
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import g1_s1_rc2g_n2_quality_campaign as campaign


class N2QualityCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = campaign.compile_campaign_manifest()
        cls.payload = campaign._canonical_json(cls.manifest)
        cls.q1_snapshot, _record = campaign._load_fixed_cell(
            campaign.CELL_SPECS[0]
        )

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_frozen_manifest_identity_and_four_cells(self) -> None:
        self.assertEqual(
            self.manifest["manifest_integrity"]["canonical_sha256"],
            campaign.EXPECTED_MANIFEST_CANONICAL_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(self.payload).hexdigest(),
            campaign.EXPECTED_MANIFEST_FILE_SHA256,
        )
        self.assertEqual(
            [cell["cell_id"] for cell in self.manifest["cells"]],
            ["Q1", "Q2", "Q3", "Q4"],
        )
        self.assertEqual(
            [cell["algorithm"] for cell in self.manifest["cells"]],
            [
                "atkinson",
                "area-weighted-blue-noise",
                "multicolor-dbs",
                "overlap-aware-dbs",
            ],
        )

    def test_candidate_records_match_every_frozen_spec(self) -> None:
        for spec, cell in zip(campaign.CELL_SPECS, self.manifest["cells"]):
            with self.subTest(cell=spec.cell_id):
                candidate = cell["candidate"]
                self.assertEqual(
                    candidate["manifest_file_sha256"], spec.manifest_file_sha256
                )
                self.assertEqual(
                    candidate["manifest_canonical_sha256"],
                    spec.manifest_canonical_sha256,
                )
                self.assertEqual(candidate["frame_sha256"], spec.frame_sha256)
                self.assertEqual(
                    candidate["frame_fnv1a"], f"0x{spec.frame_fnv1a:08X}"
                )
                self.assertEqual(
                    candidate["strict_final_preview"]["sha256"],
                    spec.final_preview_sha256,
                )
                self.assertFalse(candidate["source_bundle_upload_authorized"])
                self.assertEqual(candidate["input_kind"], "synthetic_test_card")
                self.assertFalse(candidate["natural_photo_input"])
                self.assertFalse(candidate["hardware_ready"])
                self.assertEqual(
                    [record["dtm_sha256"] for record in candidate["controllers"]],
                    [spec.cs1_dtm_sha256, spec.cs2_dtm_sha256],
                )

    def test_all_eight_action_identities_and_claims_are_distinct(self) -> None:
        action_ids = []
        action_hashes = []
        registry_ids = []
        registry_paths = []
        claim_filenames = []
        for cell in self.manifest["cells"]:
            for phase in ("map_primer", "target"):
                envelope = cell[phase]
                identity = envelope["action_identity"]
                claim = identity["claim"]
                action_ids.append(identity["action_id"])
                action_hashes.append(envelope["action_identity_sha256"])
                registry_ids.append(claim["registry_id"])
                registry_paths.append(claim["workspace_relative_registry"])
                claim_filenames.append(claim["fixed_filename"])
                self.assertEqual(claim["fixed_filename"], identity["action_id"])
                self.assertTrue(claim["workspace_global_fixed_action"])
                self.assertFalse(claim["partitioned_by_result_directory"])
                self.assertFalse(claim["partitioned_by_campaign_id"])
                self.assertFalse(claim["partitioned_by_primer_result_sha256"])
                self.assertFalse(claim["claim_created_by_compiler"])
                self.assertEqual(
                    envelope["action_identity_sha256"],
                    hashlib.sha256(campaign._canonical_json(identity)).hexdigest(),
                )
        for values in (
            action_ids,
            action_hashes,
            registry_ids,
            registry_paths,
            claim_filenames,
        ):
            self.assertEqual(len(values), 8)
            self.assertEqual(len(set(values)), 8)

    def test_each_cell_is_fresh_map_then_one_target_not_serial_playback(self) -> None:
        policy = self.manifest["campaign_policy"]
        self.assertTrue(policy["sessions_are_independent"])
        self.assertTrue(policy["fresh_map_primer_per_cell_required"])
        self.assertTrue(policy["exactly_one_target_after_each_own_primer"])
        self.assertFalse(policy["serial_playback_authorized"])
        self.assertFalse(policy["cross_cell_prior_reuse_authorized"])
        graph = self.manifest["execution_graph"]
        self.assertEqual(graph["disconnected_component_count"], 4)
        self.assertEqual(graph["inter_cell_edges"], [])
        for cell in self.manifest["cells"]:
            isolation = cell["session_isolation"]
            self.assertEqual(isolation["maximum_visible_refreshes"], 2)
            self.assertEqual(
                isolation["sequence"],
                [
                    "fresh_job0",
                    "own_map_primer_job1_op1",
                    "own_target_job2_op2",
                ],
            )
            self.assertFalse(isolation["previous_cell_as_prior_authorized"])
            self.assertFalse(
                isolation["next_cell_without_new_fresh_boot_authorized"]
            )
            primer = cell["map_primer"]["action_identity"]
            self.assertTrue(primer["required_initial_state"]["fresh_boot_required"])
            self.assertEqual(primer["required_initial_state"]["job_id"], 0)
            self.assertEqual(primer["target"]["job_id"], 1)
            self.assertEqual(primer["target"]["operation_id"], 1)
            target = cell["target"]["action_identity"]
            self.assertTrue(target["required_prior"]["same_cell_only"])
            self.assertEqual(target["required_prior"]["job_id"], 1)
            self.assertEqual(target["required_prior"]["operation_id"], 1)
            self.assertEqual(target["target"]["job_id"], 2)
            self.assertEqual(target["target"]["operation_id"], 2)
            self.assertEqual(
                target["required_prior"]["primer_action_identity_sha256"],
                cell["map_primer"]["action_identity_sha256"],
            )

    def test_every_layer_is_fail_closed_and_issues_no_authorization(self) -> None:
        self.assertEqual(
            self.manifest["classification"],
            {
                "experimental": True,
                "formal": False,
                "hardware_qualified": False,
                "hardware_tested": False,
                "algorithm_qualification": False,
                "causal_attribution_authorized": False,
                "natural_image_quality_evaluation": False,
                "synthetic_test_card_comparison_only": True,
                "hardware_ready": False,
                "upload_authorized": False,
                "offline_compiler_only": True,
            },
        )
        transport = self.manifest["transport"]
        self.assertEqual(transport["mode"], "offline")
        self.assertTrue(
            all(
                transport[key] is False
                for key in (
                    "network_io_performed",
                    "device_io_performed",
                    "serial_io_performed",
                    "gpio_io_performed",
                    "upload_performed",
                    "upload_authorized",
                )
            )
        )
        integration = self.manifest["integration_required_before_hardware"]
        self.assertFalse(integration["generic_runner_direct_use_authorized"])
        self.assertFalse(integration["compiler_contains_execution_path"])
        self.assertFalse(integration["authorization_strings_issued"])
        self.assertFalse(integration["hardware_execution_authorized"])
        self.assertFalse(integration["upload_authorized"])
        for cell in self.manifest["cells"]:
            self.assertFalse(cell["execution_runner_present"])
            self.assertFalse(cell["authorization_string_issued"])
            self.assertFalse(cell["natural_photo_input"])
            self.assertFalse(cell["hardware_ready"])
            self.assertFalse(cell["upload_authorized"])
            for phase in ("map_primer", "target"):
                action = cell[phase]["action_identity"]
                self.assertFalse(action["authorization_issued"])
                self.assertFalse(action["hardware_execution_authorized"])
                self.assertTrue(action["blocked_by_campaign_gap_audit"])
                self.assertFalse(action["upload_authorized"])
                self.assertEqual(action["exact_action"]["maximum_posts"], 1)
                self.assertFalse(action["exact_action"]["automatic_retry"])
                self.assertFalse(action["exact_action"]["automatic_recovery"])

    def test_gap_audit_blocks_hardware_and_freezes_q3_q4_near_identity(self) -> None:
        gap = self.manifest["campaign_gap_audit"]
        self.assertFalse(gap["hardware_ready"])
        self.assertFalse(gap["hardware_execution_authorized"])
        self.assertFalse(gap["natural_photo_input_present"])
        self.assertEqual(gap["source_input_kind"], "synthetic_test_card")
        self.assertEqual(gap["q3_q4_differing_pixels"], 50)
        self.assertEqual(gap["q3_q4_total_pixels"], 614_400)
        self.assertAlmostEqual(gap["q3_q4_difference_ratio"], 50 / 614_400)
        self.assertFalse(gap["q3_q4_separation_adequate_for_n2"])
        self.assertTrue(
            any("not a frozen natural photo" in item for item in gap["blockers"])
        )
        self.assertTrue(any("only 50" in item for item in gap["blockers"]))
        integration = self.manifest["integration_required_before_hardware"]
        self.assertFalse(integration["current_candidate_set_hardware_ready"])
        self.assertTrue(integration["natural_photo_candidate_rebuild_required"])
        self.assertTrue(integration["q3_q4_separation_review_required"])

    def test_compilation_creates_no_claim_registry_or_artifact(self) -> None:
        before = sorted(campaign.HARDWARE_DIR.glob(".g1_s1_rc2g_n2_*"))
        compiled = campaign.compile_campaign_manifest()
        after = sorted(campaign.HARDWARE_DIR.glob(".g1_s1_rc2g_n2_*"))
        self.assertEqual(before, after)
        self.assertFalse(compiled["transport"]["device_io_performed"])

    def test_candidate_drift_fails_before_manifest_compilation(self) -> None:
        drifted = replace(
            self.q1_snapshot,
            frame_sha256="0" * 64,
        )
        with mock.patch.object(
            campaign, "_load_quality_candidate_snapshot", return_value=drifted
        ):
            with self.assertRaisesRegex(campaign.N2CampaignError, "identity changed"):
                campaign._load_fixed_cell(campaign.CELL_SPECS[0])

    def test_write_validate_and_refuse_overwrite(self) -> None:
        destination = self.root / "n2-manifest.json"
        with mock.patch.object(
            campaign, "compile_campaign_manifest", return_value=self.manifest
        ):
            written = campaign.write_campaign_manifest(destination)
            validated = campaign.validate_campaign_manifest(destination)
            with self.assertRaisesRegex(campaign.N2CampaignError, "already exists"):
                campaign.write_campaign_manifest(destination)
        self.assertEqual(written, self.manifest)
        self.assertEqual(validated, self.manifest)
        self.assertEqual(destination.read_bytes(), self.payload)

    def test_noncanonical_tamper_and_duplicate_key_are_rejected(self) -> None:
        noncanonical = self.root / "noncanonical.json"
        noncanonical.write_text(json.dumps(self.manifest, indent=2), "utf-8")
        with self.assertRaisesRegex(campaign.N2CampaignError, "not canonical"):
            campaign.validate_campaign_manifest(noncanonical)

        duplicate = self.root / "duplicate.json"
        duplicate.write_bytes(b'{"kind":"one","kind":"two"}')
        with self.assertRaisesRegex(campaign.N2CampaignError, "duplicate key"):
            campaign.validate_campaign_manifest(duplicate)

        tampered = self.root / "tampered.json"
        value = json.loads(self.payload)
        value["campaign_policy"]["serial_playback_authorized"] = True
        tampered.write_bytes(campaign._canonical_json(value))
        with mock.patch.object(
            campaign, "compile_campaign_manifest", return_value=self.manifest
        ):
            with self.assertRaisesRegex(campaign.N2CampaignError, "differs"):
                campaign.validate_campaign_manifest(tampered)

    def test_public_api_and_cli_have_no_execution_or_cell_override_surface(self) -> None:
        for name in (
            "http_request",
            "perform_refresh",
            "run_rc2g_quality_refresh_once",
            "requester",
        ):
            self.assertFalse(hasattr(campaign, name))
        for function in (
            campaign.compile_campaign_manifest,
            campaign.campaign_manifest_bytes,
            campaign.write_campaign_manifest,
            campaign.validate_campaign_manifest,
        ):
            parameters = inspect.signature(function).parameters
            for forbidden in (
                "url",
                "base_url",
                "candidate_dir",
                "cell_id",
                "algorithm",
                "authorization",
                "requester",
                "registry",
            ):
                self.assertNotIn(forbidden, parameters)
        parsed = campaign.parse_args(["--print"])
        self.assertTrue(parsed.print_manifest)
        source = inspect.getsource(campaign.parse_args)
        for forbidden_option in (
            "--url",
            "--candidate-dir",
            "--cell",
            "--algorithm",
            "--confirm",
            "--registry",
            "--execute",
            "--upload",
        ):
            self.assertNotIn(forbidden_option, source)

    def test_cli_summary_remains_offline_only(self) -> None:
        output = io.StringIO()
        with mock.patch.object(
            campaign, "compile_campaign_manifest", return_value=self.manifest
        ), mock.patch("sys.stdout", output):
            exit_code = campaign.main(["--print"])
        self.assertEqual(exit_code, 0)
        summary = json.loads(output.getvalue())
        self.assertEqual(summary["cell_ids"], ["Q1", "Q2", "Q3", "Q4"])
        self.assertFalse(summary["network_io_performed"])
        self.assertFalse(summary["device_io_performed"])
        self.assertFalse(summary["claim_created"])
        self.assertFalse(summary["authorization_strings_issued"])
        self.assertFalse(summary["upload_authorized"])


if __name__ == "__main__":
    unittest.main()
