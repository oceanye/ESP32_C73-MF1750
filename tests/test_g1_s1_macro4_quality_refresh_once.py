from __future__ import annotations

import copy
import hashlib
import inspect
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from host.epd_frame import FRAME_BYTES
from tests.test_frame_tool import ScriptedRequester, valid_refresh_responses
from tools import g1_s1_macro4_quality_refresh_once as runner


PRODUCTION_BUNDLE = (
    Path(__file__).resolve().parents[1]
    / ".test-output"
    / "hardware"
    / "G1S1_QUALITY_MACRO4_BLUE_NOISE_OFFLINE_20260807"
)


def _target_responses(frame: bytes) -> dict[str, list[tuple[int, str] | Exception]]:
    responses = valid_refresh_responses(frame)
    status, enqueue_body = responses["/api/frame"][0]
    enqueue = json.loads(enqueue_body)
    enqueue["job_id"] = runner.EXPECTED_TARGET_JOB_ID
    responses["/api/frame"] = [(status, json.dumps(enqueue))]

    status, job_body = responses["/api/job"][0]
    job = json.loads(job_body)
    job["job_id"] = runner.EXPECTED_TARGET_JOB_ID
    responses["/api/job"] = [(status, json.dumps(job))]

    status, diagnostic_body = responses["/api/diagnostic/report"][0]
    diagnostic = json.loads(diagnostic_body)
    diagnostic.update(
        {
            "job_id": runner.EXPECTED_TARGET_JOB_ID,
            "job_operation_id": runner.EXPECTED_TARGET_OPERATION_ID,
            "operation_id": runner.EXPECTED_TARGET_OPERATION_ID,
        }
    )
    responses["/api/diagnostic/report"] = [(status, json.dumps(diagnostic))]
    return responses


def _full_responses(frame: bytes) -> dict[str, list[tuple[int, str] | Exception]]:
    target = _target_responses(frame)
    version_response = target["/api/version"][0]
    return {
        "/api/version": [version_response, version_response],
        "/api/job": [
            (200, json.dumps(runner.EXPECTED_PRIOR_JOB)),
            target["/api/job"][0],
        ],
        "/api/diagnostic/report": [
            (200, json.dumps(runner.EXPECTED_PRIOR_DIAGNOSTIC)),
            target["/api/diagnostic/report"][0],
        ],
        "/api/diagnostic/status": [
            (200, json.dumps(runner.EXPECTED_COLD_RECONNECT_GPIO)),
            (200, json.dumps(runner.EXPECTED_WARM_SAFE_FINISH_GPIO)),
        ],
        "/api/frame": target["/api/frame"],
    }


class Macro4QualityRefreshOnceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bundle = self.root / "macro4"
        self.bundle.mkdir()
        for source in PRODUCTION_BUNDLE.iterdir():
            shutil.copyfile(source, self.bundle / source.name)
        self.frame = (self.bundle / "frame.bin").read_bytes()
        self.manifest_bytes = (self.bundle / "manifest.json").read_bytes()
        self.manifest = json.loads(self.manifest_bytes)
        self.manifest_sha256 = hashlib.sha256(self.manifest_bytes).hexdigest()
        self.registry = self.root / "registry"
        self.registry.mkdir()
        self.result_dir = self.root / "result"

    def _run(self, requester, *, result_dir: Path | None = None, **overrides):
        actual_perform_refresh = runner.perform_refresh

        def perform_with_requester(*args, **kwargs):
            kwargs["requester"] = requester
            return actual_perform_refresh(*args, **kwargs)

        arguments = {
            "authorization_confirmation": runner.REQUIRED_AUTHORIZATION_CONFIRMATION,
            "confirm_j2_powered_supervised": True,
            "confirm_j2_reconnected_cold_start": True,
            "confirm_supply_and_temperature_normal": True,
            "sleeper": lambda _seconds: None,
        }
        arguments.update(overrides)
        with mock.patch.object(
            runner, "DEFAULT_CANDIDATE_DIRECTORY", self.bundle
        ), mock.patch.object(
            runner,
            "_deep_validate_candidate_directory",
            return_value=self.manifest,
        ), mock.patch.object(
            runner, "_authorization_registry", return_value=self.registry
        ), mock.patch.object(
            runner, "http_request", side_effect=requester
        ), mock.patch.object(
            runner, "perform_refresh", side_effect=perform_with_requester
        ):
            return runner.run_macro4_quality_refresh_once(
                self.result_dir if result_dir is None else result_dir,
                "http://device",
                **arguments,
            )

    def test_production_bundle_and_all_frozen_identities_match(self) -> None:
        self.assertEqual(
            runner.DEFAULT_CANDIDATE_DIRECTORY,
            PRODUCTION_BUNDLE,
        )
        self.assertEqual(
            runner.EXPECTED_MANIFEST_SHA256,
            "7c6f8569eb8a1cba9de144b7c660e79b932c1abbcbb5d6aa334ac694056420ad",
        )
        self.assertEqual(
            runner.EXPECTED_MANIFEST_CANONICAL_SHA256,
            "85abb1a948079eba89b7ca854c4b6b867e3b5f6716f5819c22765b610c2e900b",
        )
        self.assertEqual(
            (runner.EXPECTED_FRAME_SHA256, runner.EXPECTED_FRAME_FNV1A),
            (
                "1f509baa655d84fe13da65441f22929f32a43a0ac66d45d753f7a3d394a2281d",
                0x092C9775,
            ),
        )
        self.assertEqual(
            (
                runner.EXPECTED_CS1_DTM_SHA256,
                runner.EXPECTED_CS1_DTM_FNV1A,
                runner.EXPECTED_CS2_DTM_SHA256,
                runner.EXPECTED_CS2_DTM_FNV1A,
            ),
            (
                "a36a9288154d882916a6562d44d86c41278ea45ffbfcbc2afe634616d5a52fcc",
                0x3F1601D5,
                "d9bf80b6433bba8356502ce62ce44450da7339902413d9018d4ee6c959fb231d",
                0x52ECC935,
            ),
        )
        self.assertEqual(self.manifest_sha256, runner.EXPECTED_MANIFEST_SHA256)
        self.assertEqual(
            self.manifest["manifest_integrity"]["canonical_sha256"],
            runner.EXPECTED_MANIFEST_CANONICAL_SHA256,
        )
        self.assertEqual(len(self.frame), FRAME_BYTES)
        self.assertEqual(
            runner.EXPECTED_COLD_RECONNECT_GPIO,
            {"busy": 0, "rst": 0, "cs": 0, "cs2": 0},
        )
        self.assertEqual(
            runner.EXPECTED_WARM_SAFE_FINISH_GPIO,
            {"busy": 1, "rst": 0, "cs": 0, "cs2": 0},
        )

    def test_real_deep_validator_and_frozen_snapshot_interoperate(self) -> None:
        snapshot = runner._load_candidate_snapshot(
            PRODUCTION_BUNDLE, runner._frozen_manifest_sha256()
        )
        self.assertEqual(snapshot.manifest, self.manifest)
        self.assertEqual(snapshot.manifest_bytes, self.manifest_bytes)
        self.assertEqual(snapshot.frame, self.frame)

    def test_public_and_cli_interfaces_have_no_override_retry_or_recovery(self) -> None:
        parameters = inspect.signature(runner.run_macro4_quality_refresh_once).parameters
        for forbidden in (
            "candidate_dir",
            "requester",
            "authorization_registry",
            "authorized_manifest_sha256",
            "force",
            "retry",
            "recovery",
        ):
            self.assertNotIn(forbidden, parameters)
        parsed = runner.parse_args(
            [
                "--result-dir",
                str(self.result_dir),
                "--url",
                "http://device",
                "--confirm",
                runner.REQUIRED_AUTHORIZATION_CONFIRMATION,
            ]
        )
        self.assertEqual(parsed.confirm, runner.REQUIRED_AUTHORIZATION_CONFIRMATION)
        parser_source = inspect.getsource(runner.parse_args)
        self.assertNotIn("--force", parser_source)
        self.assertNotIn("--retry", parser_source)
        self.assertNotIn("--recovery", parser_source)
        self.assertIn("validate_candidate_directory", inspect.getsource(runner))
        self.assertIn("g1_s1_macro4_quality_candidate", inspect.getsource(runner))

    def test_wrong_authorization_is_preclaim_zero_validator_claim_result_or_network(self) -> None:
        with mock.patch.object(
            runner, "DEFAULT_CANDIDATE_DIRECTORY", self.bundle
        ), mock.patch.object(
            runner, "_deep_validate_candidate_directory"
        ) as validator, mock.patch.object(
            runner, "_authorization_registry"
        ) as registry, mock.patch.object(
            runner, "http_request"
        ) as request, mock.patch.object(
            runner, "perform_refresh"
        ) as refresh:
            with self.assertRaisesRegex(
                runner.Macro4QualityRefreshError, "exact reviewed-preview"
            ):
                runner.run_macro4_quality_refresh_once(
                    self.result_dir,
                    "http://device",
                    authorization_confirmation="yes",
                    confirm_j2_powered_supervised=True,
                    confirm_j2_reconnected_cold_start=True,
                    confirm_supply_and_temperature_normal=True,
                )
        validator.assert_not_called()
        registry.assert_not_called()
        request.assert_not_called()
        refresh.assert_not_called()
        self.assertFalse(self.result_dir.exists())

    def test_missing_cold_reconnect_confirmation_is_preclaim_zero_network(self) -> None:
        with mock.patch.object(
            runner, "DEFAULT_CANDIDATE_DIRECTORY", self.bundle
        ), mock.patch.object(
            runner, "_deep_validate_candidate_directory"
        ) as validator, mock.patch.object(
            runner, "_authorization_registry"
        ) as registry, mock.patch.object(
            runner, "http_request"
        ) as request, mock.patch.object(
            runner, "perform_refresh"
        ) as refresh:
            with self.assertRaisesRegex(
                runner.Macro4QualityRefreshError, "cold-reconnect"
            ):
                runner.run_macro4_quality_refresh_once(
                    self.result_dir,
                    "http://device",
                    authorization_confirmation=runner.REQUIRED_AUTHORIZATION_CONFIRMATION,
                    confirm_j2_powered_supervised=True,
                    confirm_j2_reconnected_cold_start=False,
                    confirm_supply_and_temperature_normal=True,
                )
        validator.assert_not_called()
        registry.assert_not_called()
        request.assert_not_called()
        refresh.assert_not_called()
        self.assertFalse(self.result_dir.exists())

    def test_deep_validator_rejection_is_preclaim_and_zero_network(self) -> None:
        with mock.patch.object(
            runner, "DEFAULT_CANDIDATE_DIRECTORY", self.bundle
        ), mock.patch.object(
            runner,
            "_deep_validate_candidate_directory",
            side_effect=runner.Macro4QualityRefreshError("deep reject"),
        ), mock.patch.object(
            runner, "_authorization_registry"
        ) as registry, mock.patch.object(
            runner, "http_request"
        ) as request, mock.patch.object(
            runner, "perform_refresh"
        ) as refresh:
            with self.assertRaisesRegex(runner.Macro4QualityRefreshError, "deep reject"):
                runner.run_macro4_quality_refresh_once(
                    self.result_dir,
                    "http://device",
                    authorization_confirmation=runner.REQUIRED_AUTHORIZATION_CONFIRMATION,
                    confirm_j2_powered_supervised=True,
                    confirm_j2_reconnected_cold_start=True,
                    confirm_supply_and_temperature_normal=True,
                )
        registry.assert_not_called()
        request.assert_not_called()
        refresh.assert_not_called()
        self.assertFalse(self.result_dir.exists())

    def test_success_claims_before_result_and_network_and_posts_once(self) -> None:
        scripted = ScriptedRequester(_full_responses(self.frame))
        real_create = runner._create_result_directory

        def checked_create(destination, snapshot, claim):
            self.assertTrue((self.registry / self.manifest_sha256).is_file())
            self.assertFalse(destination.exists())
            return real_create(destination, snapshot, claim)

        def requester(*args, **kwargs):
            self.assertTrue((self.registry / self.manifest_sha256).is_file())
            self.assertTrue((self.result_dir / runner.LOCK_FILENAME).is_file())
            return scripted(*args, **kwargs)

        with mock.patch.object(
            runner, "_create_result_directory", side_effect=checked_create
        ):
            result = self._run(requester)

        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
        self.assertEqual(
            scripted.calls.count(("GET", "/api/diagnostic/status")), 2
        )
        self.assertEqual(
            [call for call in scripted.calls if call[0] == "POST"],
            [("POST", "/api/frame")],
        )
        self.assertEqual(result["network_report"]["job_id"], 5)
        self.assertEqual(result["network_report"]["diagnostic"]["operation_id"], 5)
        self.assertEqual(result["current_prior_preflight"]["job"]["job_id"], 4)
        self.assertEqual(result["current_prior_preflight"]["diagnostic"]["operation_id"], 4)
        self.assertEqual(
            result["current_prior_preflight"]["gpio_status"],
            runner.EXPECTED_COLD_RECONNECT_GPIO,
        )
        self.assertEqual(
            result["post_refresh_gpio_status"],
            runner.EXPECTED_WARM_SAFE_FINISH_GPIO,
        )
        self.assertEqual(result["outcome"], "protocol_verified_manual_observation_required")
        self.assertIs(result["formal"], False)
        self.assertIs(result["hardware_qualified"], False)
        self.assertIs(result["hardware_tested"], False)
        self.assertIs(result["algorithm_qualification"], False)
        self.assertEqual(
            result["manual_observation_required"],
            list(runner.MANUAL_OBSERVATION_REQUIRED),
        )

    def test_current_prior_mismatch_is_unknown_with_zero_frame_posts(self) -> None:
        responses = _full_responses(self.frame)
        wrong = dict(runner.EXPECTED_PRIOR_JOB)
        wrong["job_id"] = 99
        responses["/api/job"][0] = (200, json.dumps(wrong))
        scripted = ScriptedRequester(responses)

        with self.assertRaises(runner.Macro4QualityRefreshUnknown):
            self._run(scripted)

        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 0)
        self.assertTrue((self.registry / self.manifest_sha256).is_file())
        recorded = json.loads((self.result_dir / runner.RESULT_FILENAME).read_text("utf-8"))
        self.assertEqual(recorded["outcome"], "unknown_do_not_retry")

    def test_warm_busy_one_is_rejected_by_this_cold_start_contract_zero_post(self) -> None:
        responses = _full_responses(self.frame)
        responses["/api/diagnostic/status"][0] = (
            200,
            json.dumps(runner.EXPECTED_WARM_SAFE_FINISH_GPIO),
        )
        scripted = ScriptedRequester(responses)

        with self.assertRaises(runner.Macro4QualityRefreshUnknown):
            self._run(scripted)

        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 0)
        self.assertTrue((self.registry / self.manifest_sha256).is_file())
        recorded = json.loads((self.result_dir / runner.RESULT_FILENAME).read_text("utf-8"))
        self.assertEqual(recorded["outcome"], "unknown_do_not_retry")
        self.assertIn("fresh J2-P1 reconnect", recorded["error"]["message"])

    def test_post_refresh_busy_zero_is_unknown_after_exactly_one_post(self) -> None:
        responses = _full_responses(self.frame)
        responses["/api/diagnostic/status"][1] = (
            200,
            json.dumps(runner.EXPECTED_COLD_RECONNECT_GPIO),
        )
        # The refresh consumes the target job/report and the first raw
        # post-refresh status.  Supply a distinct GET-only incident snapshot.
        responses["/api/job"].append(responses["/api/job"][-1])
        responses["/api/diagnostic/report"].append(
            responses["/api/diagnostic/report"][-1]
        )
        responses["/api/diagnostic/status"].append(
            (200, json.dumps(runner.EXPECTED_COLD_RECONNECT_GPIO))
        )
        scripted = ScriptedRequester(responses)

        with self.assertRaises(runner.Macro4QualityRefreshUnknown):
            self._run(scripted)

        self.assertEqual(
            [call for call in scripted.calls if call[0] == "POST"],
            [("POST", "/api/frame")],
        )
        self.assertEqual(
            scripted.calls.count(("GET", "/api/diagnostic/status")), 3
        )
        recorded = json.loads((self.result_dir / runner.RESULT_FILENAME).read_text("utf-8"))
        self.assertEqual(recorded["outcome"], "unknown_do_not_retry")
        self.assertIs(recorded["protocol_verified"], True)
        self.assertEqual(
            recorded["network_report"]["job_id"], runner.EXPECTED_TARGET_JOB_ID
        )
        self.assertEqual(
            recorded["network_report"]["diagnostic"]["operation_id"],
            runner.EXPECTED_TARGET_OPERATION_ID,
        )
        self.assertEqual(
            recorded["post_refresh_gpio_status"],
            runner.EXPECTED_COLD_RECONNECT_GPIO,
        )
        supplemental = recorded["best_effort_postclaim_evidence"]
        self.assertIs(supplemental["attempted"], True)
        self.assertIs(supplemental["requests_are_read_only"], True)
        self.assertIs(supplemental["state_changing_request_performed"], False)
        self.assertEqual(
            supplemental["captures"]["job"]["value"]["job_id"],
            runner.EXPECTED_TARGET_JOB_ID,
        )
        self.assertEqual(
            supplemental["captures"]["diagnostic_report"]["value"]["operation_id"],
            runner.EXPECTED_TARGET_OPERATION_ID,
        )
        self.assertEqual(
            supplemental["captures"]["gpio_status"]["value"],
            runner.EXPECTED_COLD_RECONNECT_GPIO,
        )
        self.assertTrue(
            all(
                capture["method"] == "GET"
                for capture in supplemental["captures"].values()
            )
        )
        self.assertIn("warm safe-finish", recorded["error"]["message"])

    def test_network_exception_is_unknown_one_post_and_global_claim_cannot_reuse(self) -> None:
        responses = _full_responses(self.frame)
        responses["/api/frame"] = [OSError("simulated transport loss")]
        scripted = ScriptedRequester(responses)
        with self.assertRaises(runner.Macro4QualityRefreshUnknown):
            self._run(scripted)
        self.assertEqual(
            [call for call in scripted.calls if call[0] == "POST"],
            [("POST", "/api/frame")],
        )
        recorded = json.loads((self.result_dir / runner.RESULT_FILENAME).read_text("utf-8"))
        supplemental = recorded["best_effort_postclaim_evidence"]
        self.assertEqual(
            supplemental["captures"]["job"]["status"], "captured"
        )
        self.assertEqual(
            supplemental["captures"]["diagnostic_report"]["status"], "captured"
        )
        self.assertEqual(
            supplemental["captures"]["gpio_status"]["status"], "captured"
        )
        self.assertIsNone(recorded["network_report"])
        calls = list(scripted.calls)

        with self.assertRaisesRegex(
            runner.Macro4QualityRefreshError, "already permanently consumed"
        ):
            self._run(scripted, result_dir=self.root / "different-result")
        self.assertEqual(scripted.calls, calls)
        self.assertFalse((self.root / "different-result").exists())

    def test_same_manifest_cannot_succeed_again_via_new_result_directory(self) -> None:
        scripted = ScriptedRequester(_full_responses(self.frame))
        self._run(scripted)
        calls = list(scripted.calls)
        with self.assertRaisesRegex(
            runner.Macro4QualityRefreshError, "already permanently consumed"
        ):
            self._run(scripted, result_dir=self.root / "second")
        self.assertEqual(scripted.calls, calls)
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)

    def test_postclaim_local_failure_is_unknown_and_performs_zero_network(self) -> None:
        scripted = ScriptedRequester(_full_responses(self.frame))
        with mock.patch.object(
            runner, "_create_result_directory", side_effect=OSError("create failed")
        ):
            with self.assertRaises(runner.Macro4QualityRefreshUnknown):
                self._run(scripted)
        self.assertTrue((self.registry / self.manifest_sha256).is_file())
        self.assertEqual(scripted.calls, [])

    def test_failed_read_only_capture_is_recorded_without_retry_or_recovery(self) -> None:
        responses = _full_responses(self.frame)
        responses["/api/diagnostic/status"][1] = (
            200,
            json.dumps(runner.EXPECTED_COLD_RECONNECT_GPIO),
        )
        # No responses remain after the visible attempt.  Each supplemental
        # GET therefore fails independently inside ScriptedRequester.
        scripted = ScriptedRequester(responses)

        with self.assertRaises(runner.Macro4QualityRefreshUnknown):
            self._run(scripted)

        self.assertEqual(
            [call for call in scripted.calls if call[0] == "POST"],
            [("POST", "/api/frame")],
        )
        recorded = json.loads((self.result_dir / runner.RESULT_FILENAME).read_text("utf-8"))
        supplemental = recorded["best_effort_postclaim_evidence"]
        self.assertEqual(
            set(supplemental["captures"]),
            {"job", "diagnostic_report", "gpio_status"},
        )
        self.assertTrue(
            all(
                capture["status"] == "capture_failed"
                and capture["method"] == "GET"
                for capture in supplemental["captures"].values()
            )
        )
        self.assertEqual(
            recorded["post_refresh_gpio_status"],
            runner.EXPECTED_COLD_RECONNECT_GPIO,
        )
        self.assertIsNotNone(recorded["network_report"])

    def test_frozen_canonical_hash_mismatch_is_preclaim(self) -> None:
        with mock.patch.object(
            runner, "DEFAULT_CANDIDATE_DIRECTORY", self.bundle
        ), mock.patch.object(
            runner, "EXPECTED_MANIFEST_CANONICAL_SHA256", "0" * 64
        ), mock.patch.object(
            runner,
            "_deep_validate_candidate_directory",
            return_value=self.manifest,
        ), mock.patch.object(
            runner, "_authorization_registry"
        ) as registry, mock.patch.object(
            runner, "http_request"
        ) as request:
            with self.assertRaisesRegex(
                runner.Macro4QualityRefreshError, "canonical manifest integrity"
            ):
                runner.run_macro4_quality_refresh_once(
                    self.result_dir,
                    "http://device",
                    authorization_confirmation=runner.REQUIRED_AUTHORIZATION_CONFIRMATION,
                    confirm_j2_powered_supervised=True,
                    confirm_j2_reconnected_cold_start=True,
                    confirm_supply_and_temperature_normal=True,
                )
        registry.assert_not_called()
        request.assert_not_called()

    def test_network_report_rechecks_job_operation_hash_timing_and_safe_finish(self) -> None:
        responses = _target_responses(self.frame)
        requester = ScriptedRequester(responses)
        report = runner.perform_refresh(
            "http://device",
            self.frame,
            expected_mappings=runner.FIXED_CONTROLLER_MAPPINGS,
            requester=requester,
            sleeper=lambda _seconds: None,
        )
        mutations = {
            "job": lambda value: value.__setitem__("job_id", 6),
            "result": lambda value: value["job"].__setitem__("result", False),
            "frame": lambda value: value["job"].__setitem__("frame_fnv1a", 0),
            "operation": lambda value: value["diagnostic"].__setitem__("operation_id", 6),
            "dtm": lambda value: value["diagnostic"]["physical_controllers"][0].__setitem__(
                "dtm_fnv1a", 0
            ),
            "timing": lambda value: value["job"].__setitem__(
                "finished_at_ms", value["job"]["started_at_ms"] + 1
            ),
            "safe-finish": lambda value: value["diagnostic"].__setitem__(
                "safe_finish_verified", False
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                changed = copy.deepcopy(report)
                mutate(changed)
                with self.assertRaises(runner.Macro4QualityRefreshError):
                    runner._validate_network_report(changed)


if __name__ == "__main__":
    unittest.main()
