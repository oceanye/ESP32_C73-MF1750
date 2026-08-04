from __future__ import annotations

import hashlib
import json
import unittest

from host.application import (
    AdapterError,
    AdapterNetworkError,
    ApplicationArtifact,
    ApplicationSession,
    HttpDeviceAdapter,
    OfflineAdapter,
    SessionError,
    SessionState,
)
from host.application.device import ARM_CONFIRMATION
from host.application.pipeline import APPLICATION_REPORT_SCHEMA, APPLICATION_REPORT_VERSION
from host.epd_frame import ControllerMapping, FRAME_BYTES, generate_fixture
from tests.test_frame_tool import (
    DEFAULT_MAPPINGS,
    ScriptedRequester,
    valid_refresh_responses,
)
from tools import mf1750_frame_tool as frame_tool


def authorized_artifact() -> ApplicationArtifact:
    frame = generate_fixture("global-h-bars")
    report = {
        "schema": APPLICATION_REPORT_SCHEMA,
        "version": APPLICATION_REPORT_VERSION,
        "palette_provenance": {"calibrated": True, "source": "synthetic test fixture"},
        "output": {
            "width": 1024,
            "height": 600,
            "bytes": FRAME_BYTES,
            "sha256": hashlib.sha256(frame).hexdigest(),
        },
        "formal_upload_authorized": True,
        "authorization_reason": "calibrated_palette",
        "offline_verified": True,
        "protocol_verified": False,
        "hardware_tested": False,
    }
    return ApplicationArtifact(frame, b"", report, True)


def adapter_with_responses(
    responses: dict[str, list[tuple[int, str] | Exception]],
) -> tuple[HttpDeviceAdapter, ScriptedRequester]:
    requester = ScriptedRequester(responses)
    adapter = HttpDeviceAdapter("http://device.invalid", requester=requester)
    adapter.allow_connection(True)
    adapter.arm_refresh(ARM_CONFIRMATION)
    return adapter, requester


class OfflineAdapterTests(unittest.TestCase):
    def test_default_offline_adapter_never_has_a_network_request_path(self) -> None:
        adapter = OfflineAdapter()
        frame = generate_fixture("global-v-bars")
        result = adapter.frame_ingress(frame)
        self.assertTrue(result["offline_verified"])
        self.assertFalse(result["protocol_verified"])
        self.assertIs(result["hardware_tested"], False)
        self.assertEqual(adapter.network_requests, 0)
        with self.assertRaisesRegex(AdapterError, "does not access a device"):
            adapter.refresh_enqueue(authorized_artifact(), DEFAULT_MAPPINGS)

    def test_reference_palette_artifact_cannot_be_forged_into_upload_authorization(self) -> None:
        frame = generate_fixture("global-v-bars")
        report = {
            "schema": APPLICATION_REPORT_SCHEMA,
            "version": APPLICATION_REPORT_VERSION,
            "palette_provenance": {"calibrated": False},
            "output": {
                "width": 1024,
                "height": 600,
                "bytes": FRAME_BYTES,
                "sha256": hashlib.sha256(frame).hexdigest(),
            },
            "formal_upload_authorized": True,
            "authorization_reason": "calibrated_palette",
            "offline_verified": True,
            "hardware_tested": False,
        }
        with self.assertRaisesRegex(ValueError, "calibrated provenance"):
            ApplicationArtifact(frame, b"", report, True)


class HttpAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.artifact = authorized_artifact()

    def test_http_202_is_queued_not_completed_and_duplicate_is_locked(self) -> None:
        responses = valid_refresh_responses(self.artifact.frame)
        adapter, requester = adapter_with_responses(responses)
        queued = adapter.refresh_enqueue(self.artifact, DEFAULT_MAPPINGS)
        self.assertEqual(queued["http_status"], 202)
        self.assertEqual(queued["state"], "queued")
        self.assertFalse(queued["protocol_verified"])
        self.assertTrue(adapter.refresh_in_flight)
        with self.assertRaisesRegex(AdapterError, "duplicate submission"):
            adapter.refresh_enqueue(self.artifact, DEFAULT_MAPPINGS)
        self.assertEqual(requester.calls[:2], [("GET", "/api/version"), ("POST", "/api/frame")])

    def test_completed_job_still_requires_matching_diagnostic_before_success(self) -> None:
        adapter, _ = adapter_with_responses(valid_refresh_responses(self.artifact.frame))
        adapter.refresh_enqueue(self.artifact, DEFAULT_MAPPINGS)
        completed = adapter.poll_job()
        self.assertEqual(completed["state"], "completed_pending_report")
        self.assertFalse(completed["protocol_verified"])
        final = adapter.diagnostic_report()
        self.assertTrue(final["protocol_verified"])
        self.assertIs(final["hardware_tested"], False)
        self.assertEqual(final["diagnostic"]["operation_id"], 23)

    def test_failed_stale_and_mismatched_jobs_cannot_succeed(self) -> None:
        mutations = {
            "failed": {"state": "failed", "result": False},
            "stale": {"job_id": 999},
            "hash": {"frame_fnv1a": 1},
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label):
                responses = valid_refresh_responses(self.artifact.frame)
                job = json.loads(responses["/api/job"][0][1])
                job.update(mutation)
                responses["/api/job"] = [(200, json.dumps(job))]
                adapter, _ = adapter_with_responses(responses)
                adapter.refresh_enqueue(self.artifact, DEFAULT_MAPPINGS)
                with self.assertRaises(AdapterError):
                    adapter.poll_job()
                self.assertFalse(adapter.state.value == "protocol_verified")

    def test_job_without_terminal_result_becomes_stale_and_cannot_succeed(self) -> None:
        responses = valid_refresh_responses(self.artifact.frame)
        clock_value = [100.0]
        requester = ScriptedRequester(responses)
        adapter = HttpDeviceAdapter(
            "http://device.invalid",
            requester=requester,
            job_timeout_s=5.0,
            clock=lambda: clock_value[0],
        )
        adapter.allow_connection(True)
        adapter.arm_refresh(ARM_CONFIRMATION)
        adapter.refresh_enqueue(self.artifact, DEFAULT_MAPPINGS)
        clock_value[0] = 105.0
        with self.assertRaisesRegex(AdapterError, "stale"):
            adapter.poll_job()
        self.assertNotEqual(adapter.state.value, "protocol_verified")

    def test_operation_id_or_report_mismatch_cannot_succeed(self) -> None:
        responses = valid_refresh_responses(self.artifact.frame)
        diagnostic = json.loads(responses["/api/diagnostic/report"][0][1])
        diagnostic["job_operation_id"] = diagnostic["operation_id"] + 1
        responses["/api/diagnostic/report"] = [(200, json.dumps(diagnostic))]
        adapter, _ = adapter_with_responses(responses)
        adapter.refresh_enqueue(self.artifact, DEFAULT_MAPPINGS)
        adapter.poll_job()
        with self.assertRaisesRegex(AdapterError, "operation_id"):
            adapter.diagnostic_report()
        self.assertNotEqual(adapter.state.value, "protocol_verified")

    def test_network_error_can_recover_without_unlocking_duplicate_submission(self) -> None:
        responses = valid_refresh_responses(self.artifact.frame)
        responses["/api/job"].insert(
            0, frame_tool.FrameToolNetworkError("synthetic polling interruption")
        )
        adapter, _ = adapter_with_responses(responses)
        session = ApplicationSession(adapter)
        session.set_artifact(self.artifact)
        # Adapter permission/arm were set by the fixture; session mirrors the
        # user-facing state before enqueue.
        session.state = SessionState.ARMED
        session.enqueue_refresh(DEFAULT_MAPPINGS)
        with self.assertRaises(AdapterNetworkError):
            session.poll_job()
        self.assertTrue(session.refresh_locked)
        self.assertTrue(session.recovery_available)
        with self.assertRaisesRegex(SessionError, "locked"):
            session.enqueue_refresh(DEFAULT_MAPPINGS)
        recovered = session.recover()
        self.assertEqual(recovered["state"], "queued")
        completed = session.poll_job()
        self.assertEqual(completed["state"], "completed_pending_report")
        final = session.retrieve_diagnostic()
        self.assertTrue(final["protocol_verified"])
        self.assertFalse(session.refresh_locked)
        combined_report = session.application_report()
        self.assertTrue(combined_report["protocol_verified"])
        self.assertIs(combined_report["hardware_tested"], False)

    def test_remote_cancel_is_explicitly_unsupported_and_local_abort_is_not_remote(self) -> None:
        adapter, _ = adapter_with_responses(valid_refresh_responses(self.artifact.frame))
        adapter.refresh_enqueue(self.artifact, DEFAULT_MAPPINGS)
        cancel = adapter.cancel()
        self.assertFalse(cancel["supported"])
        self.assertEqual(cancel["status"], "unsupported")
        aborted = adapter.local_abort()
        self.assertFalse(aborted["remote_cancelled"])
        self.assertTrue(aborted["remote_job_may_continue"])

    def test_connection_and_arm_each_require_explicit_user_action(self) -> None:
        requester = ScriptedRequester(valid_refresh_responses(self.artifact.frame))
        adapter = HttpDeviceAdapter("http://device.invalid", requester=requester)
        with self.assertRaisesRegex(AdapterError, "not been explicitly allowed"):
            adapter.version_preflight(DEFAULT_MAPPINGS)
        adapter.allow_connection(True)
        with self.assertRaisesRegex(AdapterError, "one-shot explicit arm"):
            adapter.refresh_enqueue(self.artifact, DEFAULT_MAPPINGS)
        with self.assertRaisesRegex(AdapterError, "exactly equal"):
            adapter.arm_refresh("yes")
        self.assertEqual(requester.calls, [])

    def test_legacy_or_arbitrary_device_routes_are_blocked_before_requester(self) -> None:
        requester = ScriptedRequester({})
        adapter = HttpDeviceAdapter("http://device.invalid", requester=requester)
        for method, route in (("GET", "/api/white"), ("POST", "/api/test"), ("GET", "/x")):
            with self.subTest(method=method, route=route):
                with self.assertRaisesRegex(AdapterError, "safety allowlist"):
                    adapter._request(
                        adapter._base_url, route, method=method, data=None, timeout=1.0
                    )
        self.assertEqual(requester.calls, [])


if __name__ == "__main__":
    unittest.main()
