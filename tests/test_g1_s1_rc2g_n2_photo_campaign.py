from __future__ import annotations

from copy import deepcopy
import hashlib
import inspect
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from host.visible_refresh_campaign import (
    CampaignContractError,
    build_fixed_action_declaration,
    build_session_contract,
    seal_campaign_contract,
    validate_campaign_contract,
)
from tools import g1_s1_rc2g_n2_photo_campaign as campaign


def _registry_snapshot() -> object:
    root = campaign.HARDWARE_DIR / ".visible_refresh_fixed_action_claims_v1"
    if not root.exists():
        return None
    if not root.is_dir():
        return ("not-directory",)
    return tuple(
        (path.relative_to(root).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def _reseal_outer(value: dict[str, object]) -> dict[str, object]:
    unsigned = deepcopy(value)
    unsigned.pop("manifest_integrity")
    return {
        **unsigned,
        "manifest_integrity": {
            "canonical_sha256": campaign._sha256(campaign._canonical_json(unsigned)),
            "canonical_sha256_scope": campaign.MANIFEST_HASH_SCOPE,
        },
    }


class N2PhotoCampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry_before = _registry_snapshot()
        cls.manifest = campaign.compile_campaign_manifest()
        cls.registry_after_compile = _registry_snapshot()
        cls.payload = campaign._canonical_json(cls.manifest)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_frozen_outer_manifest_hashes_and_membership(self) -> None:
        self.assertIsNotNone(campaign.EXPECTED_MANIFEST_CANONICAL_SHA256)
        self.assertIsNotNone(campaign.EXPECTED_MANIFEST_FILE_SHA256)
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

    def test_every_candidate_layer_is_frozen(self) -> None:
        for spec, cell in zip(campaign.CELL_SPECS, self.manifest["cells"]):
            with self.subTest(cell=spec.cell_id):
                candidate = cell["candidate"]
                self.assertEqual(candidate["source"], campaign.SHARED_SOURCE)
                self.assertEqual(candidate["mapped"]["rgb8_sha256"], campaign.SHARED_MAPPED["rgb8_sha256"])
                self.assertEqual(candidate["profile"], campaign.SHARED_PROFILE)
                self.assertEqual(candidate["protection"], campaign.SHARED_PROTECTION)
                self.assertEqual(candidate["options"]["value"], campaign._expected_options(spec))
                self.assertEqual(candidate["options"]["canonical_sha256"], spec.options_canonical_sha256)
                self.assertEqual(candidate["artifact"]["manifest_file_sha256"], spec.manifest_file_sha256)
                self.assertEqual(candidate["artifact"]["manifest_canonical_sha256"], spec.manifest_canonical_sha256)
                self.assertEqual(candidate["frame"]["sha256"], spec.frame_sha256)
                self.assertEqual(candidate["frame"]["fnv1a"], f"0x{spec.frame_fnv1a:08X}")
                self.assertEqual(candidate["frame"]["codes_sha256"], spec.codes_sha256)
                self.assertEqual(candidate["previews"]["source"], campaign.SHARED_PREVIEWS["source"])
                self.assertEqual(candidate["previews"]["mapped"], campaign.SHARED_PREVIEWS["mapped"])
                self.assertEqual(candidate["previews"]["final"]["sha256"], spec.final_preview_sha256)
                self.assertEqual(candidate["previews"]["model"]["sha256"], spec.model_preview_sha256)
                self.assertEqual(candidate["simulation_report_canonical_sha256"], spec.simulation_report_sha256)
                controllers = candidate["frame"]["controllers"]
                self.assertEqual(
                    [item["dtm_sha256"] for item in controllers],
                    [spec.cs1_dtm_sha256, spec.cs2_dtm_sha256],
                )
                self.assertEqual(
                    [item["dtm_fnv1a"] for item in controllers],
                    [f"0x{spec.cs1_dtm_fnv1a:08X}", f"0x{spec.cs2_dtm_fnv1a:08X}"],
                )
        self.assertEqual(self.manifest["cells"][0]["candidate"]["initializer"], {"present": False})
        self.assertEqual(self.manifest["cells"][1]["candidate"]["initializer"], {"present": False})
        self.assertEqual(self.manifest["cells"][2]["candidate"]["initializer"], campaign.SHARED_INITIALIZER)
        self.assertEqual(self.manifest["cells"][3]["candidate"]["initializer"], campaign.SHARED_INITIALIZER)

    def test_q3_q4_common_schedule_coverage_and_scientific_gate(self) -> None:
        gate = self.manifest["scientific_gate"]
        self.assertTrue(gate["scientific_gate_pass"])
        shared = gate["shared_schedule"]
        self.assertEqual(shared["seed"], campaign.SHARED_SEED)
        self.assertEqual(shared["budget"], campaign.SHARED_DBS_BUDGET)
        self.assertEqual(shared["constraint_mask_sha256"], campaign.SHARED_PROTECTION["constraint_mask_sha256"])
        self.assertEqual(shared["initializer"], campaign.SHARED_INITIALIZER)
        self.assertEqual(shared["proposal_trace_sha256"], campaign.PROPOSAL_TRACE_SHA256)
        coverage = gate["coverage"]
        self.assertGreaterEqual(coverage["observed_primary_ratio"], 0.10)
        self.assertEqual(coverage["tile_count"], 160)
        self.assertEqual(coverage["nonempty_tiles"], 160)
        self.assertGreaterEqual(coverage["left_ratio"], 0.45)
        self.assertLessEqual(coverage["left_ratio"], 0.55)
        self.assertGreaterEqual(coverage["right_ratio"], 0.45)
        self.assertLessEqual(coverage["right_ratio"], 0.55)
        self.assertTrue(coverage["pass"])

        matrix = gate["loss_matrix"]
        self.assertLess(
            matrix["identity_model"]["Q3_multicolor_dbs"],
            matrix["identity_model"]["Q4_overlap_dbs"],
        )
        self.assertLess(
            matrix["overlap_model"]["Q4_overlap_dbs"],
            matrix["overlap_model"]["Q3_multicolor_dbs"],
        )
        self.assertTrue(matrix["diagonal_dominance_pass"])
        for cell_id in ("Q3", "Q4"):
            improvement = gate["initializer_improvement"][cell_id]
            self.assertLess(improvement["final_total"], improvement["initializer_total"])
            self.assertTrue(improvement["pass"])

    def test_q3_q4_pixel_difference_is_recorded_but_not_the_scientific_gate(self) -> None:
        difference = self.manifest["scientific_gate"]["pixel_difference"]
        self.assertEqual(difference["differing_pixels"], 6_530)
        self.assertEqual(difference["total_pixels"], 614_400)
        self.assertAlmostEqual(difference["ratio"], 6_530 / 614_400)
        self.assertFalse(difference["required_as_sole_scientific_gate"])
        basis = self.manifest["scientific_gate"]["acceptance_basis"]
        self.assertTrue(any("diagonally dominant" in item for item in basis))
        self.assertFalse(any("pixel difference" in item for item in basis))

    def test_p0_has_four_disconnected_fresh_boot_map_target_sessions(self) -> None:
        p0 = self.manifest["p0_campaign_contract"]
        validate_campaign_contract(p0)
        self.assertEqual(len(p0["sessions"]), 4)
        self.assertEqual(len(p0["actions"]), 8)
        self.assertEqual(self.manifest["execution_graph"]["disconnected_component_count"], 4)
        self.assertEqual(self.manifest["execution_graph"]["inter_cell_edges"], [])
        by_hash = {action["action_identity_sha256"]: action for action in p0["actions"]}
        for session in p0["sessions"]:
            self.assertEqual(session["power_mode"], "controller_fresh_boot")
            self.assertTrue(session["requires_controller_fresh_boot"])
            self.assertFalse(session["requires_panel_power_cycle"])
            self.assertTrue(session["j2_may_remain_on_before_session"])
            self.assertFalse(session["automatic_advance"])
            primer_sha, target_sha = session["action_identity_sha256s"]
            primer = by_hash[primer_sha]["identity"]
            target = by_hash[target_sha]["identity"]
            self.assertEqual(primer["phase"], "map-primer")
            self.assertIsNone(primer["prior"])
            self.assertEqual(target["phase"], "target")
            self.assertEqual(target["prior"]["scope"], "same_cell")
            self.assertEqual(target["prior"]["action_identity_sha256"], primer_sha)
            self.assertEqual(primer["cell_id"], target["cell_id"])

    def test_all_eight_actions_and_claim_declarations_are_unique(self) -> None:
        actions = self.manifest["p0_campaign_contract"]["actions"]
        ids = [action["identity"]["action_id"] for action in actions]
        hashes = [action["action_identity_sha256"] for action in actions]
        claims = [action["claim"]["filename"] for action in actions]
        self.assertEqual(len(set(ids)), 8)
        self.assertEqual(len(set(hashes)), 8)
        self.assertEqual(len(set(claims)), 8)
        for action in actions:
            self.assertEqual(action["identity"]["request"]["maximum_post_requests"], 1)
            self.assertFalse(action["identity"]["automatic_retry"])
            self.assertFalse(action["identity"]["automatic_recovery"])
            self.assertFalse(action["claim"]["partitioned_by_campaign_id"])
            self.assertTrue(action["claim"]["create_before_network"])

    def test_candidate_ready_but_hardware_execution_and_upload_blocked(self) -> None:
        classification = self.manifest["classification"]
        readiness = self.manifest["readiness"]
        self.assertTrue(classification["candidate_set_ready"])
        self.assertTrue(readiness["candidate_set_ready"])
        for key in (
            "hardware_ready",
            "execution_runner_present",
            "reviewed_limit_profile_present",
            "scoring_contract_present",
            "hardware_execution_authorized",
            "upload_authorized",
        ):
            self.assertFalse(readiness[key])
        self.assertGreaterEqual(len(readiness["blockers"]), 3)

    def test_compile_and_describe_create_no_claim_or_device_side_effect(self) -> None:
        self.assertEqual(self.registry_before, self.registry_after_compile)
        description = campaign.describe_campaign_offline(self.manifest)
        self.assertEqual(_registry_snapshot(), self.registry_after_compile)
        self.assertFalse(description["claim_created"])
        self.assertFalse(description["authorization_created"])
        self.assertFalse(description["network_io_performed"])
        self.assertFalse(description["device_io_performed"])
        self.assertFalse(description["hardware_ready"])
        self.assertEqual(len(description["actions"]), 8)
        self.assertTrue(all(not item["claim_created"] for item in description["actions"]))

    def test_candidate_drift_is_rejected(self) -> None:
        spec = campaign.CELL_SPECS[0]
        original = campaign.validate_candidate_directory(spec.directory)
        drifted = deepcopy(original)
        drifted["frame"]["sha256"] = "0" * 64
        with mock.patch.object(campaign, "validate_candidate_directory", return_value=drifted):
            with self.assertRaises(campaign.N2PhotoCampaignError):
                campaign._load_fixed_cell(spec)

    def test_outer_tamper_is_rejected_even_when_resealed(self) -> None:
        tampered = deepcopy(self.manifest)
        tampered["readiness"]["hardware_ready"] = True
        tampered = _reseal_outer(tampered)
        with self.assertRaisesRegex(campaign.N2PhotoCampaignError, "hardware-blocked"):
            campaign.validate_compiled_manifest(tampered)

        tampered = deepcopy(self.manifest)
        tampered["scientific_gate"]["pixel_difference"]["required_as_sole_scientific_gate"] = True
        tampered = _reseal_outer(tampered)
        with self.assertRaisesRegex(campaign.N2PhotoCampaignError, "scientific gate"):
            campaign.validate_compiled_manifest(tampered)

    def test_p0_replay_and_cross_cell_prior_are_rejected(self) -> None:
        p0 = self.manifest["p0_campaign_contract"]
        replay = deepcopy(p0)
        replay.pop("integrity")
        replay["actions"].append(deepcopy(replay["actions"][0]))
        with self.assertRaisesRegex(CampaignContractError, "duplicated"):
            seal_campaign_contract(replay)

        cross = deepcopy(p0)
        cross.pop("integrity")
        q3_primer = next(
            action
            for action in cross["actions"]
            if action["identity"]["cell_id"] == "Q3" and action["identity"]["phase"] == "map-primer"
        )
        q4_target_index = next(
            index
            for index, action in enumerate(cross["actions"])
            if action["identity"]["cell_id"] == "Q4" and action["identity"]["phase"] == "target"
        )
        old_target = cross["actions"][q4_target_index]
        identity = old_target["identity"]
        replacement = build_fixed_action_declaration(
            campaign_id=identity["campaign_id"],
            session_id=identity["session_id"],
            cell_id=identity["cell_id"],
            action_id=identity["action_id"],
            phase=identity["phase"],
            frame=identity["frame"],
            endpoint=identity["request"]["endpoint"],
            prior_action_identity_sha256=q3_primer["action_identity_sha256"],
            prior_scope="same_cell",
            minimum_interval_since_prior_seconds=identity["schedule"][
                "minimum_interval_since_prior_seconds"
            ],
        )
        cross["actions"][q4_target_index] = replacement
        q4_session_index = next(
            index for index, session in enumerate(cross["sessions"]) if session["cell_id"] == "Q4"
        )
        old_session = cross["sessions"][q4_session_index]
        cross["sessions"][q4_session_index] = build_session_contract(
            session_id=old_session["session_id"],
            cell_id=old_session["cell_id"],
            power_mode=old_session["power_mode"],
            planned_cooldown_seconds=old_session["planned_cooldown_seconds"],
            final_power_off_required=old_session["final_power_off_required"],
            action_identity_sha256s=(
                old_session["action_identity_sha256s"][0],
                replacement["action_identity_sha256"],
            ),
        )
        with self.assertRaisesRegex(CampaignContractError, "same_cell prior crosses"):
            seal_campaign_contract(cross)

    def test_clean_ci_may_lack_pio_but_present_binary_must_match(self) -> None:
        missing = self.root / "missing" / "firmware.bin"
        with mock.patch.object(campaign, "FIRMWARE_BINARY", missing):
            evidence = campaign._validate_firmware_binary()
        self.assertFalse(evidence["local_build_artifact_required_for_offline_compile"])
        self.assertTrue(evidence["if_present_must_match_frozen_identity"])
        wrong = self.root / "firmware.bin"
        wrong.write_bytes(b"wrong")
        with mock.patch.object(campaign, "FIRMWARE_BINARY", wrong):
            with self.assertRaisesRegex(campaign.N2PhotoCampaignError, "identity changed"):
                campaign._validate_firmware_binary()

    def test_write_validate_noncanonical_duplicate_and_overwrite_guards(self) -> None:
        destination = self.root / "n2p.json"
        with mock.patch.object(campaign, "compile_campaign_manifest", return_value=self.manifest):
            written = campaign.write_campaign_manifest(destination)
            validated = campaign.validate_campaign_manifest(destination)
            with self.assertRaisesRegex(campaign.N2PhotoCampaignError, "already exists"):
                campaign.write_campaign_manifest(destination)
        self.assertEqual(written, self.manifest)
        self.assertEqual(validated, self.manifest)
        self.assertEqual(destination.read_bytes(), self.payload)

        noncanonical = self.root / "pretty.json"
        noncanonical.write_text(json.dumps(self.manifest, indent=2), encoding="utf-8")
        with self.assertRaisesRegex(campaign.N2PhotoCampaignError, "not canonical"):
            campaign.validate_campaign_manifest(noncanonical)
        duplicate = self.root / "duplicate.json"
        duplicate.write_bytes(b'{"kind":"one","kind":"two"}')
        with self.assertRaisesRegex(campaign.N2PhotoCampaignError, "duplicate key"):
            campaign.validate_campaign_manifest(duplicate)

    def test_public_api_and_cli_expose_no_execution_or_override_surface(self) -> None:
        for name in ("http_request", "perform_refresh", "requester", "create_claim"):
            self.assertFalse(hasattr(campaign, name))
        for function in (
            campaign.compile_campaign_manifest,
            campaign.campaign_manifest_bytes,
            campaign.describe_campaign_offline,
            campaign.write_campaign_manifest,
            campaign.validate_campaign_manifest,
        ):
            for forbidden in (
                "url",
                "base_url",
                "candidate_dir",
                "cell_id",
                "algorithm",
                "authorization",
                "requester",
                "registry",
                "execute",
            ):
                self.assertNotIn(forbidden, inspect.signature(function).parameters)
        source = inspect.getsource(campaign.parse_args)
        for forbidden_option in (
            "--url",
            "--candidate-dir",
            "--cell",
            "--algorithm",
            "--authorization",
            "--execute",
            "--upload",
        ):
            self.assertNotIn(forbidden_option, source)
        self.assertTrue(campaign.parse_args(["--describe"]).describe)

    def test_cli_describe_summary_remains_offline_and_claim_free(self) -> None:
        output = io.StringIO()
        with mock.patch.object(campaign, "compile_campaign_manifest", return_value=self.manifest), mock.patch(
            "sys.stdout", output
        ):
            exit_code = campaign.main(["--describe"])
        self.assertEqual(exit_code, 0)
        description = json.loads(output.getvalue())
        self.assertEqual(description["mode"], "describe-only")
        self.assertFalse(description["claim_created"])
        self.assertFalse(description["authorization_created"])
        self.assertFalse(description["network_io_performed"])
        self.assertFalse(description["device_io_performed"])
        self.assertFalse(description["hardware_ready"])


if __name__ == "__main__":
    unittest.main()
