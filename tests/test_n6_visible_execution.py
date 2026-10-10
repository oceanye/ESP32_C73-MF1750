from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from host.application.n6_browser_campaign import DEFAULT_MAPPINGS
from host.application.n6_visible_execution import (
    MANUAL_OBSERVATION_KIND,
    N6_ARM_CONFIRMATION,
    AtomicN6ClaimStore,
    N6BrowserExecutionController,
    N6ClaimConsumed,
    N6HttpRefreshDriver,
    N6PostClaimUnknown,
    N6TransportOutcomeUnknown,
    N6VisibleExecutionError,
    describe_n6_formal_materialization,
    execute_n6_formal_once,
    finalize_n6_manual_observation,
    finalize_n6_unknown_receipt,
    seal_n6_manual_observation,
    validate_n6_finalized_bundle,
    validate_n6_formal_manifest,
    validate_n6_protocol_receipt,
)
from tests.n6_formal_fixture import (
    CLAIMED_AT,
    COMPLETED_AT,
    artifact_and_config,
    authorization,
    browser_observation,
    formal_manifest,
    offline_manifest,
    runtime_observation,
    success_protocol_result,
)
from tests.application_browser_harness import LoopbackFakeDeviceServer


class RecordingDriver:
    def __init__(self, workspace: Path, result=None, error=None) -> None:
        self.workspace = workspace
        self.result = result
        self.error = error
        self.calls = 0
        self.claim_seen_before_call = False

    def __call__(self, frame: bytes, mappings):
        del frame
        self.calls += 1
        manifest = formal_manifest()
        declaration = manifest["action"]["claim"]
        path = (
            self.workspace
            / declaration["workspace_relative_registry"]
            / declaration["filename"]
        )
        self.claim_seen_before_call = path.is_file()
        self.assert_mappings = tuple(mappings)
        if self.error is not None:
            raise self.error
        return deepcopy(self.result)


def _execute(workspace: Path, driver: RecordingDriver):
    artifact, _ = artifact_and_config()
    return execute_n6_formal_once(
        formal_manifest(),
        artifact,
        authorization=authorization(),
        runtime_observation=runtime_observation(),
        browser_observation=browser_observation(),
        arm_confirmation=N6_ARM_CONFIRMATION,
        attempt_id="n6-test-attempt-1",
        claimed_at=CLAIMED_AT,
        completed_at=COMPLETED_AT,
        claim_store=AtomicN6ClaimStore(workspace),
        protocol_driver=driver,
    )


def _manual(receipt, *, visible=True):
    manifest = formal_manifest()
    return seal_n6_manual_observation(
        {
            "schema_version": 1,
            "kind": MANUAL_OBSERVATION_KIND,
            "formal_manifest_canonical_sha256": manifest["integrity"][
                "canonical_sha256"
            ],
            "protocol_receipt_canonical_sha256": receipt["integrity"][
                "canonical_sha256"
            ],
            "action_identity_sha256": manifest["action"]["action_identity_sha256"],
            "attempt_id": receipt["attempt_id"],
            "observed_at": "2026-08-08T12:42:00+08:00",
            "observer_id": "n6-test-observer",
            "full_panel_visual_matches_preview": visible,
            "map_fidelity_pass": visible,
            "orientation_seam_and_ghosting_normal": visible,
            "supply_cv_current_normal": True,
            "post_refresh_current_normal": True,
            "temperature_normal": True,
            "esp32_unexpected_restart": False,
            "j2_state_after_observation": "on",
            "manual_evidence_sha256": "2" * 64,
            "notes": "test-only observation",
        },
        manifest=manifest,
        protocol_receipt=receipt,
    )


class N6FormalMaterializationTests(unittest.TestCase):
    def test_default_describe_is_blocked_without_placeholder_hashes_or_side_effects(self) -> None:
        description = describe_n6_formal_materialization(
            offline_manifest(), evaluated_at="2026-08-08T12:30:00+08:00"
        )
        self.assertFalse(description["materialization_ready"])
        self.assertFalse(description["claim_created"])
        self.assertFalse(description["network_io_performed"])
        self.assertIn(
            "complete_measured_palette_aggregate_missing", description["blockers"]
        )
        self.assertTrue(
            all(value is None for value in description["evidence_identities"].values())
        )

    def test_complete_evidence_materializes_and_deep_tamper_fails(self) -> None:
        manifest = formal_manifest()
        validate_n6_formal_manifest(manifest)
        self.assertFalse(manifest["classification"]["hardware_execution_authorized"])
        self.assertFalse(manifest["classification"]["claim_created"])
        tampered = deepcopy(manifest)
        tampered["runtime_review"]["device_contract"]["maximum_frame_posts"] = 2
        with self.assertRaises(N6VisibleExecutionError):
            validate_n6_formal_manifest(tampered)


class N6FixedExecutionTests(unittest.TestCase):
    def test_real_loopback_http_driver_performs_one_frame_post_and_deep_closure(self) -> None:
        fake = LoopbackFakeDeviceServer().start()
        fake.mode = "success"
        try:
            with tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory)
                receipt = _execute(
                    workspace,
                    N6HttpRefreshDriver(
                        fake.origin,
                        poll_interval_s=0.001,
                        sleeper=lambda _seconds: None,
                    ),
                )
                validate_n6_protocol_receipt(receipt, manifest=formal_manifest())
                self.assertEqual(fake.ledger.count("GET", "/api/version"), 1)
                self.assertEqual(fake.ledger.count("POST", "/api/frame"), 1)
                self.assertEqual(fake.ledger.count("GET", "/api/job"), 1)
                self.assertEqual(
                    fake.ledger.count("GET", "/api/diagnostic/report"), 1
                )
        finally:
            fake.close()

    def test_success_claims_before_driver_and_second_run_is_permanently_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            first = RecordingDriver(workspace, result=success_protocol_result())
            receipt = _execute(workspace, first)
            validate_n6_protocol_receipt(receipt, manifest=formal_manifest())
            self.assertTrue(first.claim_seen_before_call)
            self.assertEqual(first.calls, 1)
            self.assertEqual(first.assert_mappings, DEFAULT_MAPPINGS)
            self.assertEqual(receipt["frame_post_request_count"], 1)
            self.assertEqual(receipt["state"], "PROTOCOL_VERIFIED_PENDING_MANUAL")

            second = RecordingDriver(workspace, result=success_protocol_result())
            with self.assertRaises(N6ClaimConsumed):
                _execute(workspace, second)
            self.assertEqual(second.calls, 0)

    def test_wrong_terminal_job_is_unknown_and_claim_stays_consumed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            wrong = success_protocol_result()
            wrong["job"]["job_id"] = 999
            driver = RecordingDriver(workspace, result=wrong)
            with self.assertRaises(N6PostClaimUnknown) as raised:
                _execute(workspace, driver)
            receipt = raised.exception.receipt
            self.assertTrue(driver.claim_seen_before_call)
            self.assertEqual(receipt["state"], "UNKNOWN_DO_NOT_RETRY")
            self.assertEqual(receipt["frame_post_request_count"], 1)
            bundle = finalize_n6_unknown_receipt(
                formal_manifest(),
                receipt,
                finalized_at="2026-08-08T12:43:00+08:00",
            )
            self.assertEqual(bundle["result"]["state"], "UNKNOWN_DO_NOT_RETRY")
            self.assertFalse(bundle["result"]["retry_allowed"])

    def test_network_unknown_after_frame_post_is_terminal_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            driver = RecordingDriver(
                workspace,
                error=N6TransportOutcomeUnknown(
                    "loopback connection closed after body", frame_post_request_count=1
                ),
            )
            with self.assertRaises(N6PostClaimUnknown) as raised:
                _execute(workspace, driver)
            self.assertEqual(
                raised.exception.receipt["protocol_evidence"]["outcome"],
                "UNKNOWN_DO_NOT_RETRY",
            )
            self.assertEqual(driver.calls, 1)

    def test_claim_fsync_unknown_emits_valid_zero_post_terminal_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            driver = RecordingDriver(workspace, result=success_protocol_result())
            with patch(
                "host.application.n6_visible_execution.os.fsync",
                side_effect=OSError("fault-injected fsync failure"),
            ), self.assertRaises(N6PostClaimUnknown) as raised:
                _execute(workspace, driver)
            receipt = raised.exception.receipt
            validate_n6_protocol_receipt(receipt, manifest=formal_manifest())
            self.assertEqual(receipt["state"], "UNKNOWN_DO_NOT_RETRY")
            self.assertEqual(receipt["frame_post_request_count"], 0)
            self.assertEqual(driver.calls, 0)
            declaration = formal_manifest()["action"]["claim"]
            self.assertTrue(
                (
                    workspace
                    / declaration["workspace_relative_registry"]
                    / declaration["filename"]
                ).exists()
            )

    def test_manual_finalizer_emits_pass_or_terminal_fail_and_rejects_tamper(self) -> None:
        for visible, expected in ((True, "PASS"), (False, "FAIL")):
            with self.subTest(visible=visible), tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory)
                receipt = _execute(
                    workspace,
                    RecordingDriver(workspace, result=success_protocol_result()),
                )
                bundle = finalize_n6_manual_observation(
                    formal_manifest(),
                    receipt,
                    _manual(receipt, visible=visible),
                    finalized_at="2026-08-08T12:43:00+08:00",
                )
                validate_n6_finalized_bundle(bundle, manifest=formal_manifest())
                self.assertEqual(bundle["result"]["state"], expected)
                tampered = deepcopy(bundle)
                tampered["result"]["retry_allowed"] = True
                with self.assertRaises(N6VisibleExecutionError):
                    validate_n6_finalized_bundle(tampered, manifest=formal_manifest())


class N6BrowserControllerTests(unittest.TestCase):
    def test_local_browser_chain_has_zero_device_io_until_claimed_enqueue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            driver = RecordingDriver(workspace, result=success_protocol_result())
            controller = N6BrowserExecutionController(
                formal_manifest(),
                authorization=authorization(),
                claim_store=AtomicN6ClaimStore(workspace),
                protocol_driver=driver,
                attempt_id="n6-controller-attempt-1",
                utc_now=iter((CLAIMED_AT, COMPLETED_AT)).__next__,
            )
            controller.bind_server_origin("http://127.0.0.1:8765")
            controller.set_runtime_observation(runtime_observation())
            controller.record_page_load()
            controller.record_page_load()
            controller.record_authenticated_read()
            artifact, _ = artifact_and_config()
            self.assertTrue(controller.observe_artifact(artifact))
            for stage in ("source", "mapped", "final", "model"):
                controller.record_preview_fetch(artifact.identity["report_sha256"], stage)
            controller.allow_connection(
                token_validated=True, same_origin_validated=True
            )
            controller.local_preflight(
                DEFAULT_MAPPINGS,
                token_validated=True,
                same_origin_validated=True,
            )
            controller.arm(
                N6_ARM_CONFIRMATION,
                token_validated=True,
                same_origin_validated=True,
            )
            self.assertEqual(driver.calls, 0)
            controller._enqueue_legacy_test_only(
                DEFAULT_MAPPINGS,
                token_validated=True,
                same_origin_validated=True,
            )
            self.assertEqual(driver.calls, 1)
            polled = controller.poll_job(
                token_validated=True, same_origin_validated=True
            )
            self.assertEqual(polled["state"], "completed_pending_report")
            report = controller.diagnostic_report(
                token_validated=True, same_origin_validated=True
            )
            self.assertTrue(report["protocol_verified"])
            receipt = controller.receipt
            assert receipt is not None
            self.assertEqual(receipt["browser_observation"]["reload_count"], 1)
            self.assertFalse(controller.status_overlay({})["refresh_locked"])
            with self.assertRaises(N6VisibleExecutionError):
                controller._enqueue_legacy_test_only(
                    DEFAULT_MAPPINGS,
                    token_validated=True,
                    same_origin_validated=True,
                )


if __name__ == "__main__":
    unittest.main()
