from __future__ import annotations

import json
from functools import lru_cache
import unittest

from host.application import (
    AdapterError,
    AdapterNetworkError,
    ApplicationArtifact,
    ApplicationSession,
    HttpDeviceAdapter,
    InputSource,
    OfflineAdapter,
    PreparationPurpose,
    SessionError,
    SessionState,
    prepare_image,
)
from host.application.device import ARM_CONFIRMATION, ARM_TTL_S
from host.color_pipeline import (
    CalibrationProvenance,
    Palette,
    PipelineOptions,
    RasterImage,
    reference_palette,
)
from host.epd_frame import ControllerMapping, FRAME_BYTES, generate_fixture
from tests.test_frame_tool import (
    DEFAULT_MAPPINGS,
    ScriptedRequester,
    valid_refresh_responses,
    version_body,
)
from tools import mf1750_frame_tool as frame_tool


@lru_cache(maxsize=4)
def authorized_artifact(rgb: tuple[int, int, int] = (255, 255, 255)) -> ApplicationArtifact:
    reference = reference_palette()
    palette = Palette(
        "controlled-application-device-test",
        reference.entries,
        True,
        "controlled test measurement",
        calibration=CalibrationProvenance("application-device-test", "d" * 64),
    )
    pixels = bytes(rgb)
    raster = RasterImage(1, 1, "RGB", pixels)
    source = InputSource.from_bytes(
        f"controlled-{rgb[0]}-{rgb[1]}-{rgb[2]}",
        "application/x-controlled-test-rgb",
        pixels,
    )
    return prepare_image(
        raster,
        source,
        palette=palette,
        options=PipelineOptions(text_mode=True),
        purpose=PreparationPurpose.FORMAL_UPLOAD,
    )


@lru_cache(maxsize=1)
def offline_artifact() -> ApplicationArtifact:
    raster = RasterImage(1, 1, "RGB", bytes((255, 255, 255)))
    return prepare_image(
        raster,
        InputSource.from_bytes("reference", "application/x-test", raster.pixels),
        options=PipelineOptions(text_mode=True),
        purpose=PreparationPurpose.OFFLINE_PREVIEW,
    )


def adapter_with_responses(
    responses: dict[str, list[tuple[int, str] | Exception]],
    artifact: ApplicationArtifact | None = None,
) -> tuple[HttpDeviceAdapter, ScriptedRequester]:
    requester = ScriptedRequester(responses)
    if len(requester.responses.get("/api/version", [])) == 1:
        requester.responses["/api/version"] *= 2
    adapter = HttpDeviceAdapter("http://device.invalid", requester=requester)
    adapter.bind_artifact(artifact or authorized_artifact())
    adapter.allow_connection(True)
    adapter.version_preflight(DEFAULT_MAPPINGS)
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
        preview = offline_artifact()
        report = preview.report
        report["formal_upload_authorized"] = True
        report["authorization_reason"] = "calibrated_palette"
        report["purpose"] = PreparationPurpose.FORMAL_UPLOAD.value
        report["palette_provenance"]["calibrated"] = True
        with self.assertRaisesRegex(ValueError, "C2 evidence|calibrated provenance"):
            ApplicationArtifact(preview.frame, preview.preview_png, report, True)


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
        self.assertEqual(
            requester.calls[:3],
            [
                ("GET", "/api/version"),
                ("GET", "/api/version"),
                ("POST", "/api/frame"),
            ],
        )

    def test_low_level_authorization_mutation_is_revalidated_before_enqueue(self) -> None:
        preview = offline_artifact()
        tampered = ApplicationArtifact(
            preview.frame, preview.preview_png, preview.report, preview.upload_authorized
        )
        self.assertFalse(hasattr(tampered, "__dict__"))
        responses = valid_refresh_responses(tampered.frame)
        requester = ScriptedRequester(responses)
        adapter = HttpDeviceAdapter("http://device.invalid", requester=requester)
        adapter.bind_artifact(tampered)
        adapter.allow_connection(True)
        adapter.version_preflight(DEFAULT_MAPPINGS)
        adapter.arm_refresh(ARM_CONFIRMATION)

        # frozen dataclasses are not an authorization boundary: deliberately
        # exercise Python's lowest-level mutation escape hatch.
        object.__setattr__(tampered, "upload_authorized", True)
        with self.assertRaisesRegex(AdapterError, "complete revalidation"):
            adapter.refresh_enqueue(tampered, DEFAULT_MAPPINGS)
        self.assertEqual(requester.calls, [("GET", "/api/version")])
        with self.assertRaisesRegex(AdapterError, "one-shot"):
            adapter.refresh_enqueue(preview, DEFAULT_MAPPINGS)

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
        responses["/api/version"] *= 2
        clock_value = [100.0]
        requester = ScriptedRequester(responses)
        adapter = HttpDeviceAdapter(
            "http://device.invalid",
            requester=requester,
            job_timeout_s=5.0,
            clock=lambda: clock_value[0],
        )
        adapter.bind_artifact(self.artifact)
        adapter.allow_connection(True)
        adapter.version_preflight(DEFAULT_MAPPINGS)
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
        requester = ScriptedRequester(responses)
        requester.responses["/api/version"] *= 2
        adapter = HttpDeviceAdapter("http://device.invalid", requester=requester)
        session = ApplicationSession(adapter)
        session.set_artifact(self.artifact)
        session.allow_device_connection()
        session.version_preflight(DEFAULT_MAPPINGS)
        session.arm_refresh(ARM_CONFIRMATION)
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
        with self.assertRaisesRegex(AdapterError, "bound application artifact"):
            adapter.version_preflight(DEFAULT_MAPPINGS)
        adapter.bind_artifact(self.artifact)
        adapter.version_preflight(DEFAULT_MAPPINGS)
        with self.assertRaisesRegex(AdapterError, "one-shot explicit arm"):
            adapter.refresh_enqueue(self.artifact, DEFAULT_MAPPINGS)
        with self.assertRaisesRegex(AdapterError, "exactly equal"):
            adapter.arm_refresh("yes")
        self.assertEqual(requester.calls, [("GET", "/api/version")])

    def test_session_artifact_replacement_clears_old_protocol_evidence(self) -> None:
        replacement = authorized_artifact((0, 0, 0))
        responses = valid_refresh_responses(self.artifact.frame)
        requester = ScriptedRequester(responses)
        requester.responses["/api/version"] *= 2
        session = ApplicationSession(
            HttpDeviceAdapter("http://device.invalid", requester=requester)
        )
        session.set_artifact(self.artifact)
        session.allow_device_connection()
        session.version_preflight(DEFAULT_MAPPINGS)
        session.arm_refresh(ARM_CONFIRMATION)
        session.enqueue_refresh(DEFAULT_MAPPINGS)
        session.poll_job()
        session.retrieve_diagnostic()
        self.assertTrue(session.application_report()["protocol_verified"])
        status = session.set_artifact(replacement)
        self.assertTrue(status["connection_allowed"])
        self.assertFalse(status["preflight_verified"])
        self.assertFalse(status["armed"])
        self.assertFalse(status["protocol_verified"])
        report = session.application_report()
        self.assertFalse(report["protocol_verified"])
        self.assertNotIn("device_protocol", report)

    def test_session_rejects_verified_result_for_another_artifact(self) -> None:
        replacement = authorized_artifact((0, 0, 0))
        responses = valid_refresh_responses(self.artifact.frame)
        requester = ScriptedRequester(responses)
        requester.responses["/api/version"] *= 2
        adapter = HttpDeviceAdapter("http://device.invalid", requester=requester)
        session = ApplicationSession(adapter)
        session.set_artifact(self.artifact)
        session.allow_device_connection()
        session.version_preflight(DEFAULT_MAPPINGS)
        session.arm_refresh(ARM_CONFIRMATION)
        session.enqueue_refresh(DEFAULT_MAPPINGS)
        session.poll_job()
        adapter.diagnostic_report = lambda: {  # type: ignore[method-assign]
            "state": "protocol_verified",
            "protocol_verified": True,
            "hardware_tested": False,
            "artifact_identity": replacement.identity,
        }
        with self.assertRaisesRegex(SessionError, "not bound"):
            session.retrieve_diagnostic()
        self.assertFalse(session.status()["protocol_verified"])

    def test_bytearray_input_is_copied_before_it_can_change_identity(self) -> None:
        mutable = bytearray(self.artifact.frame)
        copied = ApplicationArtifact(
            mutable,
            self.artifact.preview_png,
            self.artifact.report,
            self.artifact.upload_authorized,
        )
        original_identity = copied.identity
        mutable[0] = 0x00
        self.assertIsInstance(copied.frame, bytes)
        self.assertEqual(copied.identity, original_identity)
        self.assertNotEqual(copied.frame[0], mutable[0])

    def test_replacing_bound_artifact_revokes_old_preflight_and_arm(self) -> None:
        replacement = authorized_artifact((0, 0, 0))
        adapter, requester = adapter_with_responses(
            valid_refresh_responses(self.artifact.frame), self.artifact
        )
        rebound = adapter.bind_artifact(replacement)
        self.assertEqual(rebound["artifact_identity"], replacement.identity)
        self.assertTrue(rebound["connection_allowed"])
        with self.assertRaisesRegex(AdapterError, "one-shot explicit arm"):
            adapter.refresh_enqueue(replacement, DEFAULT_MAPPINGS)
        self.assertEqual(requester.calls, [("GET", "/api/version")])

    def test_arm_expires_and_is_consumed_without_network_submission(self) -> None:
        clock_value = [100.0]
        responses = valid_refresh_responses(self.artifact.frame)
        requester = ScriptedRequester(responses)
        requester.responses["/api/version"] *= 2
        adapter = HttpDeviceAdapter(
            "http://device.invalid", requester=requester, clock=lambda: clock_value[0]
        )
        adapter.bind_artifact(self.artifact)
        adapter.allow_connection(True)
        adapter.version_preflight(DEFAULT_MAPPINGS)
        armed = adapter.arm_refresh(ARM_CONFIRMATION)
        self.assertEqual(armed["ttl_s"], ARM_TTL_S)
        clock_value[0] += ARM_TTL_S
        with self.assertRaisesRegex(AdapterError, "expired"):
            adapter.refresh_enqueue(self.artifact, DEFAULT_MAPPINGS)
        with self.assertRaisesRegex(AdapterError, "one-shot explicit arm"):
            adapter.refresh_enqueue(self.artifact, DEFAULT_MAPPINGS)
        with self.assertRaisesRegex(AdapterError, "requires a preflight"):
            adapter.arm_refresh(ARM_CONFIRMATION)
        self.assertEqual(requester.calls, [("GET", "/api/version")])

    def test_mapping_mismatch_consumes_arm_before_any_refresh_request(self) -> None:
        adapter, requester = adapter_with_responses(
            valid_refresh_responses(self.artifact.frame), self.artifact
        )
        swapped = (ControllerMapping(1), ControllerMapping(0))
        with self.assertRaisesRegex(AdapterError, "mappings differ"):
            adapter.refresh_enqueue(self.artifact, swapped)
        with self.assertRaisesRegex(AdapterError, "one-shot explicit arm"):
            adapter.refresh_enqueue(self.artifact, DEFAULT_MAPPINGS)
        self.assertEqual(requester.calls, [("GET", "/api/version")])

    def test_enqueue_rechecks_current_frame_hashes_and_bound_identity(self) -> None:
        stale = ApplicationArtifact(
            self.artifact.frame,
            self.artifact.preview_png,
            self.artifact.report,
            self.artifact.upload_authorized,
        )
        object.__setattr__(stale, "frame", bytes((0x00,)) * FRAME_BYTES)
        adapter, requester = adapter_with_responses(
            valid_refresh_responses(self.artifact.frame), self.artifact
        )
        with self.assertRaisesRegex(AdapterError, "SHA256|identity"):
            adapter.refresh_enqueue(stale, DEFAULT_MAPPINGS)
        self.assertEqual(requester.calls, [("GET", "/api/version")])

    def test_second_preflight_must_exactly_match_the_armed_version(self) -> None:
        responses = valid_refresh_responses(self.artifact.frame)
        responses["/api/version"] = [
            (200, version_body()),
            (200, version_body().replace("Free PSRAM: 7900000", "Free PSRAM: 7800001")),
        ]
        adapter, requester = adapter_with_responses(responses, self.artifact)
        with self.assertRaisesRegex(AdapterError, "changed after arm"):
            adapter.refresh_enqueue(self.artifact, DEFAULT_MAPPINGS)
        self.assertEqual(
            requester.calls,
            [("GET", "/api/version"), ("GET", "/api/version")],
        )

    def test_returned_job_is_not_an_alias_for_private_job_evidence(self) -> None:
        responses = valid_refresh_responses(self.artifact.frame)
        diagnostic = json.loads(responses["/api/diagnostic/report"][0][1])
        diagnostic["job_id"] = 999
        responses["/api/diagnostic/report"] = [(200, json.dumps(diagnostic))]
        adapter, _ = adapter_with_responses(responses, self.artifact)
        adapter.refresh_enqueue(self.artifact, DEFAULT_MAPPINGS)
        returned = adapter.poll_job()
        returned["job"]["job_id"] = 999
        returned["artifact_identity"]["frame_fnv1a"] = 1
        with self.assertRaisesRegex(AdapterError, "job id"):
            adapter.diagnostic_report()

    def test_final_result_preserves_full_preflight_raw_timing_and_validation(self) -> None:
        adapter, _ = adapter_with_responses(
            valid_refresh_responses(self.artifact.frame), self.artifact
        )
        queued = adapter.refresh_enqueue(self.artifact, DEFAULT_MAPPINGS)
        polled = adapter.poll_job()
        final = adapter.diagnostic_report()
        self.assertEqual(queued["artifact_identity"], self.artifact.identity)
        self.assertEqual(polled["artifact_identity"], self.artifact.identity)
        self.assertEqual(final["artifact_identity"], self.artifact.identity)
        self.assertEqual(final["preflight"]["build_tag"], version_body().splitlines()[0])
        for key in (
            "total_ms",
            "cs1_upload_ms",
            "cs2_upload_ms",
            "pon_ms",
            "drf_ms",
            "pof_ms",
            "post_psr_ms",
            "timeout_stage",
            "last_wait_stage",
        ):
            self.assertIn(key, final["diagnostic"])
        self.assertTrue(final["diagnostic_validation"]["safe_finish_verified"])
        self.assertEqual(
            final["verified_scope"],
            [
                "canonical_frame_dimensions_and_physical_color_codes",
                "firmware_build_api_spi_psram_and_mapping_preflight",
                "frame_upload_bytes_and_fnv1a",
                "job_identity_state_result_and_frame_hash",
                "diagnostic_immutable_driver_operation_identity",
                "diagnostic_build_api_job_mapping_and_dtm_hashes",
                "diagnostic_sequence_busy_timing_and_safe_finish_evidence",
            ],
        )

    def test_legacy_or_arbitrary_device_routes_are_blocked_before_requester(self) -> None:
        requester = ScriptedRequester({})
        adapter = HttpDeviceAdapter("http://device.invalid", requester=requester)
        for method, route in (("GET", "/api/white"), ("POST", "/api/test"), ("GET", "/x")):
            with self.subTest(method=method, route=route):
                with self.assertRaisesRegex(AdapterError, "safety allowlist"):
                    adapter._request(
                        adapter._base_url, route, method=method, data=None, timeout=1.0
                    )
        with self.assertRaisesRegex(AdapterError, "state transition"):
            adapter._request(
                adapter._base_url,
                "/api/version",
                method="GET",
                data=None,
                timeout=1.0,
            )
        self.assertEqual(requester.calls, [])


if __name__ == "__main__":
    unittest.main()
