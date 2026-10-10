from __future__ import annotations

from copy import deepcopy
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from host.visible_refresh_campaign import ResultState, canonical_json_bytes
from tests import n8_bundle_fixture as fixture
from tests.test_frame_tool import ScriptedRequester
from tests.test_g1_s1_rc2g_map_baseline_once import TickClock as MapTickClock, _responses as map_responses
from tests.test_g1_s1_rc2g_quality_refresh_once import TickClock as TargetTickClock, _responses as target_responses
from tools import g1_s1_n8_execution_contract as execution
from tools import g1_s1_rc2g_n2_photo_campaign_once as n2_runner
from tools import g1_s1_rc2g_n8_once as runner


class N8FixedExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = execution.compile_n8_execution_contract()
        cls.runtime = fixture.ready_manifest()

    def test_frozen_contract_has_exact_15_actions_10_dependencies_and_hashes(self) -> None:
        self.assertEqual(len(execution.FIXED_ACTION_KEYS), 15)
        self.assertEqual(self.contract["counts"]["visible_actions"], 15)
        self.assertEqual(
            self.contract["counts"]["dependent_finalized_pass_whole_file_bindings"], 10
        )
        self.assertEqual(
            self.contract["integrity"]["canonical_sha256"],
            execution.EXPECTED_CONTRACT_CANONICAL_SHA256,
        )
        self.assertEqual(
            execution.execution_contract_file_sha256(self.contract),
            execution.EXPECTED_CONTRACT_FILE_SHA256,
        )
        self.assertEqual(
            self.contract["source_manifest"]["canonical_sha256"],
            execution.EXPECTED_SOURCE_MANIFEST_CANONICAL_SHA256,
        )

    def test_warm_source_semantics_are_supervised_continuous_dynamic_not_reboot(self) -> None:
        power = self.contract["power_semantics"]
        self.assertEqual(
            power["supervised_continuous_sequences"],
            ["n8-warm-q1-q2-q3-q4"],
        )
        self.assertFalse(power["warm_session_requires_controller_fresh_boot"])
        self.assertTrue(power["warm_root_dynamic_first_action_baseline"])
        self.assertTrue(power["j2_may_remain_on_during_nominal_sequence"])
        source = execution._source_manifest()
        warm = source["sequences"][1]
        self.assertEqual(warm["power_mode"], "supervised_continuous")
        self.assertFalse(warm["requires_controller_fresh_boot"])

    def test_cli_is_closed_action_enum_without_frame_or_job_overrides(self) -> None:
        signature = inspect.signature(
            runner._run_n8_fixed_action_once_legacy_test_only
        ).parameters
        for forbidden in (
            "frame",
            "frame_sha256",
            "expected_prior_job_id",
            "expected_target_job_id",
            "expected_prior_operation_id",
            "expected_target_operation_id",
        ):
            self.assertNotIn(forbidden, signature)
        parser_source = inspect.getsource(runner.parse_args)
        for forbidden in (
            "--frame",
            "--frame-sha256",
            "--expected-prior-job-id",
            "--expected-target-job-id",
        ):
            self.assertNotIn(forbidden, parser_source)
        for key in execution.FIXED_ACTION_KEYS:
            self.assertEqual(
                runner.parse_args(["--action", key, "--describe-only"]).action,
                key,
            )

    def test_public_legacy_live_entry_is_blocked_before_claim_and_network(self) -> None:
        with (
            mock.patch.object(
                runner,
                "_prepare_inputs",
                side_effect=AssertionError("input preparation forbidden"),
            ),
            mock.patch.object(
                runner,
                "_claim_action",
                side_effect=AssertionError("claim forbidden"),
            ),
            mock.patch.object(
                runner,
                "http_request",
                side_effect=AssertionError("network forbidden"),
            ),
        ):
            with self.assertRaisesRegex(
                runner.N8FixedActionError,
                "legacy N8 live execution is disabled",
            ):
                runner.run_n8_fixed_action_once()

    def test_all_snapshots_bind_frozen_frames_and_reference_previews(self) -> None:
        seen = set()
        for key in execution.FIXED_ACTION_KEYS:
            snapshot = execution.load_n8_action_snapshot(key)
            self.assertEqual(
                snapshot.action["action_identity_sha256"],
                execution.FIXED_ACTION_SHA256S[key],
            )
            self.assertEqual(
                execution._sha256(snapshot.frame),
                snapshot.action["identity"]["frame"]["sha256"],
            )
            if snapshot.frame_source_id != "MAP":
                self.assertTrue(snapshot.reference_preview["workspace_relative_file"].endswith("final.png"))
            seen.add(snapshot.action["action_identity_sha256"])
        self.assertEqual(len(seen), 15)

    def test_describe_only_has_zero_claim_and_zero_network(self) -> None:
        with (
            mock.patch.object(runner, "http_request", side_effect=AssertionError("network forbidden")),
            mock.patch.object(n2_runner, "DEFAULT_CLAIM_REGISTRY") as registry,
        ):
            description = runner.describe_n8_fixed_action("n8-warm-q1-q2-q3-q4-map")
        self.assertFalse(description["contract_ready"])
        self.assertFalse(description["claim_created"])
        self.assertFalse(description["network_io_performed"])
        self.assertIn("reviewed_runtime_manifest_missing", description["blockers"])
        registry.assert_not_called()

    def test_all_15_actions_form_five_recursive_deep_verified_chains(self) -> None:
        bundles = fixture.build_all_pass()
        self.assertEqual(len(bundles), 15)
        by_sequence: dict[str, list[dict[str, object]]] = {}
        for bundle in bundles:
            validated = execution.validate_n8_finalized_action_bundle(
                self.contract, bundle
            )
            self.assertTrue(validated["execution_evidence_verified"])
            self.assertEqual(validated["state"], ResultState.PASS.value)
            self.assertEqual(validated["qualification_state"], "NOT_QUALIFIED")
            by_sequence.setdefault(validated["sequence_id"], []).append(validated)
        self.assertEqual(sorted(map(len, by_sequence.values())), [2, 2, 2, 4, 5])
        for sequence in by_sequence.values():
            ordered = sorted(sequence, key=lambda item: int(item["ordinal"]))
            for prior, target in zip(ordered, ordered[1:]):
                self.assertEqual(target["completed_job_id"], prior["completed_job_id"] + 1)
                self.assertEqual(
                    target["completed_operation_id"], prior["completed_operation_id"] + 1
                )
                self.assertEqual(
                    target["prior_result_file_sha256"], prior["result_file_sha256"]
                )
                self.assertEqual(
                    target["prior_finalization_file_sha256"],
                    prior["finalization_file_sha256"],
                )

    def test_warm_dynamic_nonzero_baseline_records_live_ids_without_reboot(self) -> None:
        key = "n8-warm-q1-q2-q3-q4-map"
        snapshot = execution.load_n8_action_snapshot(key)
        run_contract = execution.build_n8_protocol_contract(
            snapshot,
            prior_job_id=7,
            prior_operation_id=19,
        )
        responses = target_responses(snapshot.frame, run_contract)
        requester = ScriptedRequester(responses)
        hardware = runner.REPO_ROOT / ".test-output" / "hardware"
        hardware.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=hardware) as temporary:
            root = Path(temporary)
            registry = root / "claims"
            registry.mkdir()
            manifest_path = root / "runtime.json"
            manifest_path.write_bytes(canonical_json_bytes(self.runtime))
            destination = root / "result"
            with (
                mock.patch.object(n2_runner, "DEFAULT_CLAIM_REGISTRY", registry),
                mock.patch.object(runner, "http_request", requester),
                mock.patch.object(runner, "_utc_now", return_value=fixture.RUNNER_NOW),
            ):
                evidence = runner._run_n8_fixed_action_once_legacy_test_only(
                    key,
                    destination,
                    "http://device",
                    runtime_manifest_file=manifest_path,
                    evaluated_at=fixture.EVALUATED_AT,
                    authorization_confirmation=runner.required_authorization_confirmation(key),
                    start_external_temperature_c=24,
                    confirmations=fixture.confirmations(snapshot),
                    sleeper=lambda _seconds: None,
                    clock=TargetTickClock(),
                )
        protocol = evidence["protocol_evidence"]
        self.assertEqual(protocol["preflight_mode"], "dynamic_first_action_baseline")
        self.assertEqual(protocol["preflight"]["job_raw"]["job_id"], 7)
        self.assertEqual(protocol["completed_action"]["job_id"], 8)
        self.assertEqual(protocol["completed_action"]["operation_id"], 20)
        self.assertEqual(evidence["request_audit"]["post_issued_count"], 1)

    def test_nested_claim_protocol_prior_and_qualification_tamper_fail_closed(self) -> None:
        bundles = fixture.build_all_pass()
        root = deepcopy(bundles[0])
        root["claim"]["confirmations"]["controller_fresh_boot"] = False
        root["claim_file_sha256"] = execution._sha256(root["claim"])
        with self.assertRaises(execution.N8ExecutionContractError):
            execution.validate_n8_finalized_action_bundle(self.contract, root)
        dependent = deepcopy(bundles[1])
        dependent["evidence"]["protocol_evidence"]["completed_action"]["job_id"] += 1
        dependent["evidence_file_sha256"] = execution._sha256(dependent["evidence"])
        with self.assertRaises(execution.N8ExecutionContractError):
            execution.validate_n8_finalized_action_bundle(self.contract, dependent)
        dependent = deepcopy(bundles[1])
        dependent["prior_bundle_file_sha256"] = fixture.fixture_sha256("wrong-prior")
        with self.assertRaises(execution.N8ExecutionContractError):
            execution.validate_n8_finalized_action_bundle(self.contract, dependent)
        root = deepcopy(bundles[0])
        root["qualification_state"] = "QUALIFIED"
        with self.assertRaises(execution.N8ExecutionContractError):
            execution.validate_n8_finalized_action_bundle(self.contract, root)

    def test_continuity_failure_is_finalized_fail_and_stops_chain(self) -> None:
        sequence = fixture.build_sequence(
            "n8-temperature-nominal-q4",
            runtime=self.runtime,
            states={2: ResultState.FAIL},
        )
        validated = execution.validate_n8_finalized_action_bundle(
            self.contract, sequence[-1]
        )
        self.assertEqual(validated["state"], ResultState.FAIL.value)
        self.assertFalse(validated["observation"]["visual_pass"])
        self.assertEqual(validated["qualification_state"], "NOT_QUALIFIED")

    def test_post_claim_failure_is_unknown_and_never_reissued(self) -> None:
        key = "n8-temperature-low-q4-map"
        snapshot = execution.load_n8_action_snapshot(key)
        responses = map_responses()
        responses["/api/job"][1] = RuntimeError("connection lost after POST")
        requester = ScriptedRequester(responses)
        hardware = runner.REPO_ROOT / ".test-output" / "hardware"
        hardware.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=hardware) as temporary:
            root = Path(temporary)
            registry = root / "claims"
            registry.mkdir()
            manifest_path = root / "runtime.json"
            manifest_path.write_bytes(canonical_json_bytes(self.runtime))
            destination = root / "result"
            with (
                mock.patch.object(n2_runner, "DEFAULT_CLAIM_REGISTRY", registry),
                mock.patch.object(runner, "http_request", requester),
                mock.patch.object(runner, "_utc_now", return_value=fixture.RUNNER_NOW),
            ):
                with self.assertRaises(runner.N8FixedActionUnknown):
                    runner._run_n8_fixed_action_once_legacy_test_only(
                        key,
                        destination,
                        "http://device",
                        runtime_manifest_file=manifest_path,
                        evaluated_at=fixture.EVALUATED_AT,
                        authorization_confirmation=runner.required_authorization_confirmation(key),
                        start_external_temperature_c=10,
                        confirmations=fixture.confirmations(snapshot),
                        sleeper=lambda _seconds: None,
                        clock=MapTickClock(),
                    )
                unknown = json.loads((destination / runner.P0_RESULT_FILENAME).read_text("utf-8"))
                self.assertEqual(unknown["state"], ResultState.UNKNOWN_DO_NOT_RETRY.value)
                self.assertEqual(unknown["post_request_count"], 1)
                self.assertEqual(requester.calls.count(("POST", "/api/frame")), 1)
                with self.assertRaises(runner.N8FixedActionUnknown):
                    runner._run_n8_fixed_action_once_legacy_test_only(
                        key,
                        root / "replay",
                        "http://device",
                        runtime_manifest_file=manifest_path,
                        evaluated_at=fixture.EVALUATED_AT,
                        authorization_confirmation=runner.required_authorization_confirmation(key),
                        start_external_temperature_c=10,
                        confirmations=fixture.confirmations(snapshot),
                    )
                self.assertEqual(requester.calls.count(("POST", "/api/frame")), 1)


if __name__ == "__main__":
    unittest.main()
