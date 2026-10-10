from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests.test_g1_s1_rc2g_map_baseline_once import (
    ScriptedRequester as PrimerScriptedRequester,
    TickClock as PrimerTickClock,
    _responses as primer_responses,
)
from tests.test_g1_s1_rc2g_quality_refresh_once import (
    QUALITY_BUNDLES,
    ScriptedRequester as QualityScriptedRequester,
    TickClock as QualityTickClock,
    _responses as quality_responses,
)
from tools import g1_s1_rc2g_low_balanced_pilot_once as runner
from tools import g1_s1_rc2g_n1_low_balanced_map_primer_once as primer
from tools import g1_s1_rc2g_quality_refresh_once as quality


class Rc2gLowBalancedPilotOnceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = runner._load_fixed_candidate()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            dir=runner.REPO_ROOT / ".test-output"
        )
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.primer_registry = self.root / "primer-registry"
        self.primer_registry.mkdir()
        self.primer_result_dir = self.root / "primer-result"
        self.target_registry = self.root / "target-registry"
        self.target_registry.mkdir()
        self.target_result_dir = self.root / "target-result"
        scripted = PrimerScriptedRequester(primer_responses())
        with mock.patch.object(
            primer, "_authorization_registry", return_value=self.primer_registry
        ), mock.patch.object(primer, "http_request", side_effect=scripted):
            primer.run_n1_low_balanced_map_primer_once(
                self.primer_result_dir,
                "http://device",
                authorization_confirmation=primer.REQUIRED_AUTHORIZATION_CONFIRMATION,
                confirm_rc2g_flashed_fresh_boot=True,
                confirm_j2_powered_supervised=True,
                confirm_supply_and_temperature_normal=True,
                confirm_single_visible_primer_refresh=True,
                sleeper=lambda _seconds: None,
                clock=PrimerTickClock(),
            )
        self.primer_result = self.primer_result_dir / primer.RESULT_FILENAME
        self.primer_sha = hashlib.sha256(self.primer_result.read_bytes()).hexdigest()

    def _primer_registry_patch(self):
        return mock.patch.object(
            runner.primer,
            "DEFAULT_AUTHORIZATION_REGISTRY",
            self.primer_registry,
        )

    def _build_contract(self):
        with self._primer_registry_patch(), mock.patch.object(
            runner, "_load_fixed_candidate", return_value=self.snapshot
        ):
            return runner._build_contract(self.primer_result, self.primer_sha)

    def _run(self, requester, *, result_dir: Path | None = None, **overrides):
        _snapshot, _evidence, _binding, contract = self._build_contract()
        arguments = {
            "primer_result_sha256": self.primer_sha,
            "authorization_confirmation": contract.required_authorization_confirmation,
            "confirm_j2_powered_supervised": True,
            "confirm_supply_and_temperature_normal": True,
            "confirm_primer_visual_pass": True,
            "confirm_no_esp32_reboot_since_primer": True,
            "confirm_no_j2_disconnect_since_primer": True,
            "confirm_reviewed_low_balanced_strict_preview": True,
            "sleeper": lambda _seconds: None,
            "clock": QualityTickClock(),
        }
        arguments.update(overrides)
        with self._primer_registry_patch(), mock.patch.object(
            runner, "_load_fixed_candidate", return_value=self.snapshot
        ), mock.patch.object(
            quality, "_authorization_registry", return_value=self.target_registry
        ), mock.patch.object(quality, "http_request", side_effect=requester):
            return runner.run_low_balanced_pilot_once(
                self.target_result_dir if result_dir is None else result_dir,
                "http://device",
                self.primer_result,
                **arguments,
            )

    def _target_responses(
        self,
        contract,
        *,
        prior_job_mutation=None,
        prior_diagnostic_mutation=None,
        supplemental: bool = False,
    ):
        responses = quality_responses(
            self.snapshot.frame,
            contract,
            supplemental=supplemental,
        )
        stored = json.loads(self.primer_result.read_text("utf-8"))[
            "completed_map_evidence"
        ]
        prior_job = dict(stored["job_raw"])
        prior_diagnostic = dict(stored["diagnostic_raw"])
        if prior_job_mutation is not None:
            prior_job_mutation(prior_job)
        if prior_diagnostic_mutation is not None:
            prior_diagnostic_mutation(prior_diagnostic)
        responses["/api/job"][0] = (200, json.dumps(prior_job))
        responses["/api/diagnostic/report"][0] = (
            200,
            json.dumps(prior_diagnostic),
        )
        return responses

    def test_fixed_candidate_is_exact_old_successful_low_spatial_raster(self) -> None:
        snapshot = self.snapshot
        self.assertEqual(snapshot.frame_sha256, runner.EXPECTED_FRAME_SHA256)
        self.assertEqual(snapshot.frame_fnv1a, 0xA9641618)
        self.assertEqual(snapshot.controllers[0]["dtm_fnv1a"], "0xCB085C03")
        self.assertEqual(snapshot.controllers[1]["dtm_fnv1a"], "0x9ABD749A")
        old = (runner.OLD_LOW_SPATIAL_DIR / "frame.bin").read_bytes()
        self.assertEqual(snapshot.frame, old)
        self.assertFalse(snapshot.manifest["classification"]["upload_authorized"])
        self.assertEqual(
            snapshot.manifest["variants"]["low-balanced"]["counts"][
                "half_imbalance_l1"
            ],
            4,
        )

    def test_primer_result_and_permanent_claim_are_deep_validated(self) -> None:
        with self._primer_registry_patch():
            evidence = runner._load_primer_evidence(
                self.primer_result, self.primer_sha
            )
        self.assertEqual(evidence.result_sha256, self.primer_sha)
        self.assertEqual(evidence.attempt_id, evidence.claim_attempt_id)
        completed = evidence.result["completed_map_evidence"]
        self.assertEqual(completed["job_raw"]["job_id"], 1)
        self.assertEqual(completed["diagnostic_raw"]["operation_id"], 1)
        self.assertEqual(completed["diagnostic_raw"]["input_fnv1a"], 0x9D04142D)

    def test_tampered_primer_result_is_rejected_even_with_matching_file_sha(self) -> None:
        tampered_dir = self.root / "tampered"
        tampered_dir.mkdir()
        tampered_path = tampered_dir / primer.RESULT_FILENAME
        value = json.loads(self.primer_result.read_text("utf-8"))
        value["protocol_verified"] = False
        payload = runner._canonical_json(value)
        tampered_path.write_bytes(payload)
        with self._primer_registry_patch(), self.assertRaisesRegex(
            runner.LowBalancedPilotError, "protocol_verified"
        ):
            runner._load_primer_evidence(
                tampered_path, hashlib.sha256(payload).hexdigest()
            )

    def test_wrong_primer_sha_is_rejected(self) -> None:
        with self._primer_registry_patch(), self.assertRaisesRegex(
            runner.LowBalancedPilotError, "does not match"
        ):
            runner._load_primer_evidence(self.primer_result, "0" * 64)

    def test_primer_audit_allows_read_only_get_timeout_before_success(self) -> None:
        value = json.loads(self.primer_result.read_text("utf-8"))
        calls = value["request_audit"]["calls"]
        calls.insert(
            6,
            {
                "index": 7,
                "method": "GET",
                "endpoint": "/api/job",
                "timeout_seconds": 20.0,
                "request_bytes": 0,
                "outcome": "exception",
                "error": {
                    "type": "FrameToolNetworkError",
                    "message": "GET /api/job failed: timed out",
                },
            },
        )
        for index, call in enumerate(calls, start=1):
            call["index"] = index
        payload = runner._canonical_json(value)
        self.primer_result.write_bytes(payload)
        with self._primer_registry_patch():
            evidence = runner._load_primer_evidence(
                self.primer_result, hashlib.sha256(payload).hexdigest()
            )
        self.assertEqual(evidence.result["request_audit"]["post_issued_count"], 1)

    def test_primer_audit_rejects_any_extra_or_failed_post(self) -> None:
        value = json.loads(self.primer_result.read_text("utf-8"))
        calls = value["request_audit"]["calls"]
        calls.append(
            {
                "index": len(calls) + 1,
                "method": "POST",
                "endpoint": "/api/frame",
                "timeout_seconds": 20.0,
                "request_bytes": 307200,
                "request_sha256": runner.baseline.EXPECTED_FRAME_SHA256,
                "outcome": "exception",
                "error": {"type": "TimeoutError", "message": "timed out"},
            }
        )
        payload = runner._canonical_json(value)
        self.primer_result.write_bytes(payload)
        with self._primer_registry_patch(), self.assertRaisesRegex(
            runner.LowBalancedPilotError, "sole successful MAP ingress"
        ):
            runner._load_primer_evidence(
                self.primer_result, hashlib.sha256(payload).hexdigest()
            )

    def test_description_is_offline_and_binds_primer_sha_and_fixed_claim(self) -> None:
        with self._primer_registry_patch(), mock.patch.object(
            runner, "_load_fixed_candidate", return_value=self.snapshot
        ), mock.patch.object(quality, "http_request") as request, mock.patch.object(
            quality, "_authorization_registry"
        ) as registry:
            described = runner.describe_low_balanced_pilot(
                self.primer_result, self.primer_sha
            )
        request.assert_not_called()
        registry.assert_not_called()
        self.assertFalse(described["device_io_performed"])
        self.assertFalse(described["claim_created"])
        self.assertEqual(described["primer_result_sha256"], self.primer_sha)
        binding = described["fixed_external_evidence_binding"]
        self.assertEqual(binding["fixed_action_id"], runner.FIXED_ACTION_ID)
        self.assertEqual(binding["primer_result"]["sha256"], self.primer_sha)
        self.assertFalse(
            binding["claim_scope"]["partitioned_by_primer_result_sha256"]
        )
        self.assertEqual(
            described["fixed_claim"]["filename"], runner.FIXED_ACTION_ID
        )
        self.assertIn(
            described["action_identity_sha256"].upper(),
            described["required_authorization_confirmation"],
        )

    def test_public_cli_has_no_candidate_campaign_registry_or_job_override(self) -> None:
        parameters = inspect.signature(runner.run_low_balanced_pilot_once).parameters
        for forbidden in (
            "candidate_dir",
            "manifest_sha256",
            "campaign_id",
            "action_id",
            "registry",
            "expected_prior_job_id",
            "expected_target_job_id",
            "frame",
            "retry",
            "recovery",
            "force",
        ):
            self.assertNotIn(forbidden, parameters)
        source = inspect.getsource(runner.parse_args)
        for option in (
            "--candidate-dir",
            "--manifest-sha256",
            "--campaign-id",
            "--action-id",
            "--registry",
            "--job-id",
            "--retry",
            "--recovery",
            "--force",
        ):
            self.assertNotIn(option, source)

    def test_generic_internal_hook_rejects_arbitrary_snapshot_before_claim(self) -> None:
        bad_snapshot = replace(self.snapshot, algorithm="arbitrary-hidden-frame")
        with mock.patch.object(quality, "_authorization_registry") as registry, \
             mock.patch.object(quality, "http_request") as request, \
             self.assertRaisesRegex(
                 quality.Rc2gQualityRefreshError, "complete fixed N1 scope"
             ):
            quality.run_rc2g_quality_refresh_once(
                self.target_result_dir,
                "http://device",
                runner.FACTORIAL_DIR,
                expected_manifest_sha256=runner.EXPECTED_FACTORIAL_MANIFEST_SHA256,
                expected_prior_job_id=1,
                expected_prior_operation_id=1,
                expected_prior_frame_sha256=runner.baseline.EXPECTED_FRAME_SHA256,
                expected_prior_frame_fnv1a=runner.baseline.EXPECTED_FRAME_FNV1A,
                expected_prior_cs1_dtm_fnv1a=(
                    runner.baseline.EXPECTED_CS1_DTM_FNV1A
                ),
                expected_prior_cs2_dtm_fnv1a=(
                    runner.baseline.EXPECTED_CS2_DTM_FNV1A
                ),
                expected_target_job_id=2,
                expected_target_operation_id=2,
                authorization_confirmation="unused",
                confirm_j2_powered_supervised=True,
                confirm_supply_and_temperature_normal=True,
                confirm_reviewed_strict_preview=True,
                _prevalidated_snapshot=bad_snapshot,
            )
        registry.assert_not_called()
        request.assert_not_called()

    def test_normal_quality_path_rejects_alternate_fixed_claim_partition(self) -> None:
        candidate, manifest_sha = QUALITY_BUNDLES["atkinson"]
        with mock.patch.object(quality, "_authorization_registry") as registry, \
             mock.patch.object(quality, "http_request") as request, \
             mock.patch.object(quality, "_load_candidate_snapshot") as loader, \
             self.assertRaisesRegex(
                 quality.Rc2gQualityRefreshError,
                 "overrides require the sole fixed N1 snapshot",
             ):
            quality.run_rc2g_quality_refresh_once(
                self.target_result_dir,
                "http://device",
                candidate,
                expected_manifest_sha256=manifest_sha,
                expected_prior_job_id=1,
                expected_prior_operation_id=1,
                expected_prior_frame_sha256=runner.baseline.EXPECTED_FRAME_SHA256,
                expected_prior_frame_fnv1a=runner.baseline.EXPECTED_FRAME_FNV1A,
                expected_prior_cs1_dtm_fnv1a=(
                    runner.baseline.EXPECTED_CS1_DTM_FNV1A
                ),
                expected_prior_cs2_dtm_fnv1a=(
                    runner.baseline.EXPECTED_CS2_DTM_FNV1A
                ),
                expected_target_job_id=2,
                expected_target_operation_id=2,
                authorization_confirmation="unused",
                confirm_j2_powered_supervised=True,
                confirm_supply_and_temperature_normal=True,
                confirm_reviewed_strict_preview=True,
                _fixed_claim_filename="alternate",
            )
        loader.assert_not_called()
        registry.assert_not_called()
        request.assert_not_called()

    def test_missing_manual_confirmation_is_preclaim_and_zero_network(self) -> None:
        for name in (
            "confirm_j2_powered_supervised",
            "confirm_supply_and_temperature_normal",
            "confirm_primer_visual_pass",
            "confirm_no_esp32_reboot_since_primer",
            "confirm_no_j2_disconnect_since_primer",
            "confirm_reviewed_low_balanced_strict_preview",
        ):
            with self.subTest(name=name), mock.patch.object(
                quality, "_authorization_registry"
            ) as registry, mock.patch.object(quality, "http_request") as request:
                with self.assertRaisesRegex(runner.LowBalancedPilotError, "all supervised"):
                    runner.run_low_balanced_pilot_once(
                        self.target_result_dir,
                        "http://device",
                        self.primer_result,
                        primer_result_sha256=self.primer_sha,
                        authorization_confirmation="unused",
                        confirm_j2_powered_supervised=name
                        != "confirm_j2_powered_supervised",
                        confirm_supply_and_temperature_normal=name
                        != "confirm_supply_and_temperature_normal",
                        confirm_primer_visual_pass=name
                        != "confirm_primer_visual_pass",
                        confirm_no_esp32_reboot_since_primer=name
                        != "confirm_no_esp32_reboot_since_primer",
                        confirm_no_j2_disconnect_since_primer=name
                        != "confirm_no_j2_disconnect_since_primer",
                        confirm_reviewed_low_balanced_strict_preview=name
                        != "confirm_reviewed_low_balanced_strict_preview",
                    )
            registry.assert_not_called()
            request.assert_not_called()

    def test_wrong_authorization_is_preclaim_and_zero_network(self) -> None:
        with self._primer_registry_patch(), mock.patch.object(
            runner, "_load_fixed_candidate", return_value=self.snapshot
        ), mock.patch.object(quality, "_authorization_registry") as registry, mock.patch.object(
            quality, "http_request"
        ) as request, self.assertRaisesRegex(
            runner.LowBalancedPilotError, "exact low-balanced"
        ):
            runner.run_low_balanced_pilot_once(
                self.target_result_dir,
                "http://device",
                self.primer_result,
                primer_result_sha256=self.primer_sha,
                authorization_confirmation="yes",
                confirm_j2_powered_supervised=True,
                confirm_supply_and_temperature_normal=True,
                confirm_primer_visual_pass=True,
                confirm_no_esp32_reboot_since_primer=True,
                confirm_no_j2_disconnect_since_primer=True,
                confirm_reviewed_low_balanced_strict_preview=True,
            )
        registry.assert_not_called()
        request.assert_not_called()

    def test_success_fixed_claim_exists_before_network_and_posts_once(self) -> None:
        _snapshot, _evidence, _binding, contract = self._build_contract()
        scripted = QualityScriptedRequester(
            self._target_responses(contract)
        )

        def checked_requester(*args, **kwargs):
            self.assertTrue(
                (self.target_registry / runner.FIXED_CLAIM_FILENAME).is_file()
            )
            self.assertTrue(
                (self.target_result_dir / quality.LOCK_FILENAME).is_file()
            )
            return scripted(*args, **kwargs)

        result = self._run(checked_requester)
        self.assertEqual(
            [call for call in scripted.calls if call[0] == "POST"],
            [("POST", "/api/frame")],
        )
        self.assertEqual(result["network_report"]["job_id"], 2)
        self.assertEqual(result["target_diagnostic_raw"]["operation_id"], 2)
        self.assertEqual(result["request_audit"]["post_issued_count"], 1)
        self.assertEqual(result["classification"], runner.CLASSIFICATION)
        self.assertEqual(result["fixed_action_id"], runner.FIXED_ACTION_ID)
        self.assertEqual(
            result["exact_action"]["action_id"], runner.FIXED_ACTION_ID
        )
        self.assertEqual(
            result["action_identity"]["fixed_external_evidence_binding"]
            ["primer_result"]["sha256"],
            self.primer_sha,
        )
        claim = json.loads(
            (self.target_registry / runner.FIXED_CLAIM_FILENAME).read_text("utf-8")
        )
        self.assertEqual(claim["action_identity_sha256"], contract.action_identity_sha256)
        self.assertTrue(claim["confirmations"]["primer_visual_fidelity_pass"])
        self.assertEqual(claim["fixed_action_id"], runner.FIXED_ACTION_ID)

    def test_live_prior_must_equal_stored_primer_evidence_before_post(self) -> None:
        _snapshot, _evidence, _binding, contract = self._build_contract()

        def shift_job(job):
            for key in ("queued_at_ms", "started_at_ms", "finished_at_ms"):
                job[key] += 100

        def shift_diagnostic(diagnostic):
            for key in (
                "job_queued_at_ms",
                "job_started_at_ms",
                "job_finished_at_ms",
            ):
                diagnostic[key] += 100

        scripted = QualityScriptedRequester(
            self._target_responses(
                contract,
                prior_job_mutation=shift_job,
                prior_diagnostic_mutation=shift_diagnostic,
                supplemental=True,
            )
        )
        with self.assertRaises(quality.Rc2gQualityRefreshUnknown):
            self._run(scripted)
        self.assertTrue(
            (self.target_registry / runner.FIXED_CLAIM_FILENAME).is_file()
        )
        self.assertEqual(
            [call for call in scripted.calls if call[0] == "POST"], []
        )
        recorded = json.loads(
            (self.target_result_dir / quality.RESULT_FILENAME).read_text("utf-8")
        )
        self.assertEqual(recorded["outcome"], "unknown_do_not_retry")
        self.assertEqual(recorded["request_audit"]["post_issued_count"], 0)
        self.assertIn("exact stored primer", recorded["error"]["message"])

    def test_fixed_claim_cannot_be_partitioned_by_new_result_directory(self) -> None:
        _snapshot, _evidence, _binding, contract = self._build_contract()
        first = QualityScriptedRequester(
            self._target_responses(contract)
        )
        self._run(first)
        second = QualityScriptedRequester(
            self._target_responses(contract)
        )
        with self.assertRaisesRegex(
            runner.LowBalancedPilotError, "already permanently consumed"
        ):
            self._run(second, result_dir=self.root / "another-result")
        self.assertEqual(second.calls, [])


if __name__ == "__main__":
    unittest.main()
