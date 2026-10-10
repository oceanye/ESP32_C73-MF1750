from __future__ import annotations

from copy import deepcopy
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from host.visible_refresh_campaign import ResultState, canonical_json_bytes
from tests import n4_v3_bundle_fixture as fixture
from tests.test_frame_tool import ScriptedRequester
from tests.test_g1_s1_rc2g_map_baseline_once import (
    TickClock as MapTickClock,
    _responses as map_responses,
)
from tools import g1_s1_n4_v3_execution_contract as execution
from tools import g1_s1_rc2g_n2_photo_campaign_once as n2_runner
from tools import g1_s1_rc2g_n4_v3_once as runner


class N4V3FixedActionRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = execution.compile_n4_v3_execution_contract()

    def test_frozen_execution_contract_only_supersedes_session_power_off(self) -> None:
        contract = self.contract
        self.assertEqual(
            contract["integrity"]["canonical_sha256"],
            execution.EXPECTED_CONTRACT_CANONICAL_SHA256,
        )
        self.assertEqual(
            execution.execution_contract_file_sha256(contract),
            execution.EXPECTED_CONTRACT_FILE_SHA256,
        )
        self.assertEqual(
            contract["source_p0_campaign_canonical_sha256"],
            execution.EXPECTED_SOURCE_P0_CAMPAIGN_CANONICAL_SHA256,
        )
        self.assertEqual(
            contract["p0_campaign_canonical_sha256"],
            execution.EXPECTED_P0_CAMPAIGN_CANONICAL_SHA256,
        )
        source = contract["source_p0_campaign"]
        runtime = contract["p0_campaign"]
        self.assertEqual(source["actions"], runtime["actions"])
        for historical, selected in zip(source["sessions"], runtime["sessions"]):
            changed = {key for key in historical if historical[key] != selected[key]}
            self.assertEqual(changed, {"final_power_off_required", "integrity"})
            self.assertTrue(historical["final_power_off_required"])
            self.assertFalse(selected["final_power_off_required"])
            self.assertTrue(selected["j2_may_remain_on_before_session"])
        power = contract["power_semantics"]
        self.assertTrue(power["same_cell_j2_disconnect_forbidden"])
        self.assertTrue(power["j2_may_remain_on_between_cells"])
        self.assertTrue(
            power["power_off_required_before_firmware_or_configuration_change"]
        )

    def test_cli_enumerates_only_eight_actions_and_has_no_identity_overrides(self) -> None:
        self.assertEqual(len(runner.FIXED_ACTION_KEYS), 8)
        self.assertEqual(set(runner.FIXED_ACTION_KEYS), set(runner.FIXED_ACTION_SHA256S))
        signature = inspect.signature(runner.run_n4_v3_fixed_action_once).parameters
        for forbidden in (
            "frame",
            "frame_sha256",
            "manifest",
            "manifest_sha256",
            "proof_sha256",
            "expected_target_job_id",
            "expected_prior_job_id",
        ):
            self.assertNotIn(forbidden, signature)
        parser_source = inspect.getsource(runner.parse_args)
        for forbidden_flag in (
            "--frame",
            "--frame-sha256",
            "--manifest",
            "--manifest-sha256",
            "--proof-sha256",
            "--expected-target-job-id",
            "--expected-prior-job-id",
        ):
            self.assertNotIn(forbidden_flag, parser_source)
        for key in runner.FIXED_ACTION_KEYS:
            parsed = runner.parse_args(["--action", key, "--describe-only"])
            self.assertEqual(parsed.action, key)
        with self.assertRaises(SystemExit):
            runner.parse_args(["--action", "custom-target", "--describe-only"])

    def test_all_action_snapshots_bind_exact_v3_frames_and_previews(self) -> None:
        seen = set()
        for key in runner.FIXED_ACTION_KEYS:
            with self.subTest(action=key):
                snapshot = execution.load_n4_v3_action_snapshot(key)
                self.assertEqual(
                    snapshot.action["action_identity_sha256"],
                    runner.FIXED_ACTION_SHA256S[key],
                )
                self.assertEqual(
                    execution._sha256(snapshot.frame),
                    snapshot.action["identity"]["frame"]["sha256"],
                )
                seen.add(snapshot.action["action_identity_sha256"])
                if snapshot.phase == "target":
                    self.assertEqual(
                        snapshot.reference_preview["bundle_filename"],
                        f"{snapshot.cell_id}.strict-final.png",
                    )
        self.assertEqual(len(seen), 8)

    def test_describe_only_is_zero_claim_and_zero_network(self) -> None:
        with mock.patch.object(
            runner, "http_request", side_effect=AssertionError("network forbidden")
        ):
            description = runner.describe_n4_v3_fixed_action(
                "low-balanced-map-primer"
            )
        self.assertFalse(description["contract_ready"])
        self.assertFalse(description["hardware_ready"])
        self.assertFalse(description["claim_created"])
        self.assertIn("reviewed_limit_profile_missing", description["blockers"])

    def test_all_eight_actions_form_four_deep_verified_map_target_chains(self) -> None:
        for cell in execution.v3.CAMPAIGN_CELL_ORDER:
            with self.subTest(cell=cell, phase="map-primer"):
                map_bundle = fixture.build_finalized_bundle(
                    f"{cell}-map-primer", contract=self.contract
                )
                map_validated = execution.validate_n4_v3_finalized_action_bundle(
                    self.contract,
                    map_bundle,
                    expected_action_key=f"{cell}-map-primer",
                )
                self.assertTrue(map_validated["execution_evidence_verified"])
            with self.subTest(cell=cell, phase="target"):
                target_bundle = fixture.build_finalized_bundle(
                    f"{cell}-target",
                    contract=self.contract,
                    prior_bundle=map_bundle,
                )
                target_validated = execution.validate_n4_v3_finalized_action_bundle(
                    self.contract,
                    target_bundle,
                    expected_action_key=f"{cell}-target",
                    prior_bundle=map_bundle,
                )
                self.assertEqual(target_validated["state"], ResultState.PASS.value)
                self.assertTrue(target_validated["execution_evidence_verified"])
                self.assertEqual(
                    target_validated["prior_result_file_sha256"],
                    map_validated["result_file_sha256"],
                )
                self.assertEqual(
                    target_validated["prior_finalization_file_sha256"],
                    map_validated["finalization_file_sha256"],
                )

    def test_target_rejects_cross_cell_map_bundle(self) -> None:
        map_bundle = fixture.build_finalized_bundle(
            "low-balanced-map-primer", contract=self.contract
        )
        with self.assertRaises(runner.N4V3FixedActionError):
            fixture.build_finalized_bundle(
                "high-balanced-target",
                contract=self.contract,
                prior_bundle=map_bundle,
            )

    def test_target_finalizer_persists_and_validates_cell_observation(self) -> None:
        cell = fixture.build_finalized_cell(
            "high-balanced", contract=self.contract
        )
        observation = cell["cell_observation"]
        self.assertEqual(
            observation["kind"], "mf1750-g1-s1-n4-v3-cell-observation"
        )
        self.assertTrue(observation["execution_evidence_verified"])
        self.assertEqual(
            execution._sha256(observation),
            cell["cell_observation_file_sha256"],
        )

    def test_target_continuity_failure_is_terminal_fail_not_visual_pass(self) -> None:
        map_bundle = fixture.build_finalized_bundle(
            "low-unbalanced-map-primer", contract=self.contract
        )
        target_bundle = fixture.build_finalized_bundle(
            "low-unbalanced-target",
            contract=self.contract,
            prior_bundle=map_bundle,
            overrides={
                "continuity": {"j2_disconnect_between_actions": True},
            },
        )
        validated = execution.validate_n4_v3_finalized_action_bundle(
            self.contract,
            target_bundle,
            prior_bundle=map_bundle,
        )
        self.assertEqual(validated["state"], ResultState.FAIL.value)
        self.assertTrue(validated["observation"]["visual_pass"])
        self.assertFalse(validated["observation"]["continuity_pass"])

    def test_fixed_camera_capture_hashes_are_unique_per_action(self) -> None:
        first = fixture.build_finalized_bundle(
            "high-balanced-map-primer",
            contract=self.contract,
            overrides={"camera": {"observation_kind": "fixed-camera"}},
        )
        second = fixture.build_finalized_bundle(
            "high-unbalanced-map-primer",
            contract=self.contract,
            overrides={"camera": {"observation_kind": "fixed-camera"}},
        )
        self.assertNotEqual(
            first["observation"]["camera"]["capture_file_sha256"],
            second["observation"]["camera"]["capture_file_sha256"],
        )

    def test_legacy_live_profile_path_is_disabled_before_claim_and_network(self) -> None:
        with (
            mock.patch.object(runner, "_claim_action", side_effect=AssertionError("claim")),
            mock.patch.object(runner, "http_request", side_effect=AssertionError("network")),
            self.assertRaisesRegex(
                runner.N4V3FixedActionError, "legacy N4 V3 live execution"
            ),
        ):
            runner.run_n4_v3_fixed_action_once(
                "low-balanced-map-primer",
                Path("must-not-be-created"),
                "http://device",
                limit_profile_file=Path("must-not-be-read.json"),
                evaluated_at=fixture.EVALUATED_AT,
                authorization_confirmation="must-not-be-read",
                start_temperature_c=25,
            )

    def test_nested_protocol_or_claim_tamper_fails_closed(self) -> None:
        bundle = fixture.build_finalized_bundle(
            "high-unbalanced-map-primer", contract=self.contract
        )
        tampered = deepcopy(bundle)
        tampered["evidence"]["protocol_evidence"]["fresh_boot_preflight"][
            "job_raw"
        ]["job_id"] = 1
        tampered["evidence_file_sha256"] = execution._sha256(tampered["evidence"])
        with self.assertRaises(execution.N4V3ExecutionContractError):
            execution.validate_n4_v3_finalized_action_bundle(self.contract, tampered)
        tampered = deepcopy(bundle)
        tampered["claim"]["confirmations"]["controller_fresh_boot"] = False
        tampered["claim_file_sha256"] = execution._sha256(tampered["claim"])
        with self.assertRaises(execution.N4V3ExecutionContractError):
            execution.validate_n4_v3_finalized_action_bundle(self.contract, tampered)

    def test_post_failure_records_unknown_with_one_post_and_replay_has_zero_io(self) -> None:
        hardware = runner.REPO_ROOT / ".test-output" / "hardware"
        hardware.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=hardware) as temporary:
            root = Path(temporary)
            registry = root / "claims"
            profile = fixture._profile(
                self.contract["p0_campaign"], prior_completed=False
            )
            profile_path = root / "profile.json"
            profile_path.write_bytes(canonical_json_bytes(profile))
            responses = map_responses()
            responses["/api/job"][1] = RuntimeError("lost after POST")
            scripted = ScriptedRequester(responses)
            destination = root / "unknown"
            action_key = "low-balanced-map-primer"
            with (
                mock.patch.object(runner, "_require_deep_production_profile_path"),
                mock.patch.object(n2_runner, "DEFAULT_CLAIM_REGISTRY", registry),
                mock.patch.object(runner, "http_request", scripted),
                mock.patch.object(
                    runner, "_utc_now", return_value="2026-08-08T00:00:30Z"
                ),
            ):
                with self.assertRaises(runner.N4V3FixedActionUnknown):
                    runner.run_n4_v3_fixed_action_once(
                        action_key,
                        destination,
                        "http://device",
                        limit_profile_file=profile_path,
                        evaluated_at=fixture.EVALUATED_AT,
                        authorization_confirmation=(
                            runner.required_authorization_confirmation(action_key)
                        ),
                        start_temperature_c=25,
                        confirm_reviewed_panel_and_build=True,
                        confirm_supervised_supply_cv_current_normal=True,
                        confirm_physical_cutoff_available=True,
                        confirm_single_visible_refresh=True,
                        confirm_controller_fresh_boot=True,
                        sleeper=lambda _seconds: None,
                        clock=MapTickClock(),
                    )
                evidence = json.loads(
                    (destination / runner.EVIDENCE_FILENAME).read_text(encoding="utf-8")
                )
                result = json.loads(
                    (destination / runner.P0_RESULT_FILENAME).read_text(encoding="utf-8")
                )
                self.assertEqual(
                    evidence["outcome"], ResultState.UNKNOWN_DO_NOT_RETRY.value
                )
                self.assertEqual(result["post_request_count"], 1)
                self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
                with mock.patch.object(
                    runner, "http_request", side_effect=AssertionError("replay network")
                ):
                    with self.assertRaises(runner.N4V3FixedActionUnknown):
                        runner.run_n4_v3_fixed_action_once(
                            action_key,
                            root / "replay",
                            "http://device",
                            limit_profile_file=profile_path,
                            evaluated_at=fixture.EVALUATED_AT,
                            authorization_confirmation=(
                                runner.required_authorization_confirmation(action_key)
                            ),
                            start_temperature_c=25,
                            confirm_reviewed_panel_and_build=True,
                            confirm_supervised_supply_cv_current_normal=True,
                            confirm_physical_cutoff_available=True,
                            confirm_single_visible_refresh=True,
                            confirm_controller_fresh_boot=True,
                        )


if __name__ == "__main__":
    unittest.main()
