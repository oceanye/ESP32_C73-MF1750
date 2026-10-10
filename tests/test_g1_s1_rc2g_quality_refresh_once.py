from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from host.epd_frame import controller_stream, fnv1a, generate_fixture
from tests.test_frame_tool import ScriptedRequester, add_valid_busy_trace, version_body
from tools import g1_s1_rc2g_quality_refresh_once as runner


REPO_ROOT = Path(__file__).resolve().parents[1]
QUALITY_BUNDLES = {
    "atkinson": (
        REPO_ROOT
        / ".test-output"
        / "hardware"
        / "G1S1_QUALITY_ATKINSON_OFFLINE_20260806",
        "ae882e6c7cd032a8315e15a1deb2a77abee025711acb55b5ec22b0fe91a4f32b",
    ),
    "area-weighted-blue-noise": (
        REPO_ROOT
        / ".test-output"
        / "hardware"
        / "G1S1_QUALITY_BLUE_NOISE_OFFLINE_20260806",
        "69244cebe2e37c0d26404b85b9d89471cd95d492a9599481e5f34968c3159a48",
    ),
    "multicolor-dbs": (
        REPO_ROOT
        / ".test-output"
        / "hardware"
        / "G1S1_QUALITY_MULTICOLOR_DBS_OFFLINE_20260806",
        "9eb946ddb91093d654071d55f9fa0f3f890497f368c3cbd7222ea19213f1db3e",
    ),
    "overlap-aware-dbs": (
        REPO_ROOT
        / ".test-output"
        / "hardware"
        / "G1S1_QUALITY_OVERLAP_DBS_OFFLINE_20260806",
        "c7fc66c6cb879997c5a5b34d8b8234c2abbca691a80c29f44c7e212548ebd062",
    ),
}
MAP_FRAME = generate_fixture("map-orient-v1")
MAP_FRAME_SHA256 = hashlib.sha256(MAP_FRAME).hexdigest()
MAP_FRAME_FNV1A = fnv1a(MAP_FRAME)
MAP_CS1_DTM_FNV1A = fnv1a(
    controller_stream(MAP_FRAME, runner.FIXED_CONTROLLER_MAPPINGS[0])
)
MAP_CS2_DTM_FNV1A = fnv1a(
    controller_stream(MAP_FRAME, runner.FIXED_CONTROLLER_MAPPINGS[1])
)


class TickClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        self.value += 0.1
        return self.value


def _job(job_id: int, frame_hash: int, base_ms: int) -> dict[str, object]:
    return {
        "job_id": job_id,
        "action": "uploaded_frame",
        "state": "completed",
        "result": True,
        "queued_at_ms": base_ms,
        "started_at_ms": base_ms + 4,
        "finished_at_ms": base_ms + 32_004,
        "frame_fnv1a": frame_hash,
    }


def _diagnostic(
    frame: bytes,
    job: dict[str, object],
    operation_id: int,
    *,
    stage_overrides: dict[str, int] | None = None,
) -> dict[str, object]:
    timings = {
        "total_ms": 32_000,
        "cs1_upload_ms": 2_440,
        "cs2_upload_ms": 2_440,
        "pon_ms": 181,
        "drf_ms": 25_000,
        "pof_ms": 140,
        "post_psr_ms": 5,
    }
    timings.update(stage_overrides or {})
    mappings = runner.FIXED_CONTROLLER_MAPPINGS
    diagnostic: dict[str, object] = {
        "schema_version": 2,
        "firmware_build_tag": runner.EXPECTED_BUILD_TAG,
        "driver_api_version": runner.EXPECTED_DRIVER_API,
        "job_id": job["job_id"],
        "job_action": "uploaded_frame",
        "job_state": "completed",
        "job_result": True,
        "job_operation_id": operation_id,
        "job_queued_at_ms": job["queued_at_ms"],
        "job_started_at_ms": job["started_at_ms"],
        "job_finished_at_ms": job["finished_at_ms"],
        "operation_id": operation_id,
        "valid": True,
        "running": False,
        "sequence_ok": True,
        "wait_timeout": False,
        "busy_assertion_missing": False,
        "busy_assert_grace_ms": 250,
        "mapping_applied": True,
        "pon_busy_seen": True,
        "drf_busy_seen": True,
        "pof_busy_seen": True,
        "post_psr_busy_seen": False,
        "spi_hz": runner.EXPECTED_REFRESH_SPI_HZ,
        "input_fnv1a": fnv1a(frame),
        "cs1_dtm_fnv1a": fnv1a(controller_stream(frame, mappings[0])),
        "cs2_dtm_fnv1a": fnv1a(controller_stream(frame, mappings[1])),
        **timings,
        "last_wait_ms": timings["post_psr_ms"],
        "last_wait_stage": "post-display PSR",
        "timeout_stage": "none",
        "busy_missing_stage": "none",
        "mapping": {
            "cs1_source_half": 0,
            "cs1_flip_x": False,
            "cs1_flip_y": False,
            "cs1_nibble_swap": False,
            "cs2_source_half": 1,
            "cs2_flip_x": False,
            "cs2_flip_y": False,
            "cs2_nibble_swap": False,
        },
    }
    add_valid_busy_trace(diagnostic)
    return diagnostic


def _responses(
    target_frame: bytes,
    contract: runner._RunContract,
    *,
    prior_job_mutation=None,
    prior_diagnostic_mutation=None,
    target_diagnostic_mutation=None,
    post_gpio: dict[str, int] | None = None,
    frame_response: tuple[int, str] | Exception | None = None,
    supplemental: bool = False,
) -> dict[str, list[tuple[int, str] | Exception]]:
    prior_job = _job(
        contract.expected_prior_job_id,
        contract.expected_prior_frame_fnv1a,
        1_000,
    )
    target_job = _job(
        contract.expected_target_job_id,
        contract.snapshot.frame_fnv1a,
        50_000,
    )
    prior_diagnostic = _diagnostic(
        MAP_FRAME,
        prior_job,
        contract.expected_prior_operation_id,
    )
    # A sequential quality prior need not be MAP.  Bind its declared FNV in
    # the raw diagnostic while retaining a structurally valid synthetic trace.
    prior_diagnostic["input_fnv1a"] = contract.expected_prior_frame_fnv1a
    prior_diagnostic["cs1_dtm_fnv1a"] = contract.expected_prior_cs1_dtm_fnv1a
    prior_diagnostic["cs2_dtm_fnv1a"] = contract.expected_prior_cs2_dtm_fnv1a
    if prior_job_mutation is not None:
        prior_job_mutation(prior_job)
    if prior_diagnostic_mutation is not None:
        prior_diagnostic_mutation(prior_diagnostic)
    target_diagnostic = _diagnostic(
        target_frame,
        target_job,
        contract.expected_target_operation_id,
    )
    if target_diagnostic_mutation is not None:
        target_diagnostic_mutation(target_diagnostic)
    enqueue = {
        "ok": True,
        "bytes": len(target_frame),
        "fnv1a": fnv1a(target_frame),
        "free_psram": 7_800_000,
        "job_id": contract.expected_target_job_id,
    }
    if frame_response is None:
        frame_response = (202, json.dumps(enqueue))
    gpio = dict(post_gpio or {"busy": 0, "rst": 0, "cs": 0, "cs2": 0})
    responses: dict[str, list[tuple[int, str] | Exception]] = {
        "/api/version": [
            (200, version_body(build_tag=runner.EXPECTED_BUILD_TAG)),
            (200, version_body(build_tag=runner.EXPECTED_BUILD_TAG)),
        ],
        "/api/job": [
            (200, json.dumps(prior_job)),
            (200, json.dumps(target_job)),
            (200, json.dumps(target_job)),
        ],
        "/api/diagnostic/report": [
            (200, json.dumps(prior_diagnostic)),
            (200, json.dumps(target_diagnostic)),
            (200, json.dumps(target_diagnostic)),
        ],
        "/api/diagnostic/status": [
            (200, json.dumps({"busy": 0, "rst": 0, "cs": 0, "cs2": 0})),
            (200, json.dumps(gpio)),
        ],
        "/api/frame": [frame_response],
    }
    if supplemental:
        responses["/api/job"].append((200, json.dumps(target_job)))
        responses["/api/diagnostic/report"].append(
            (200, json.dumps(target_diagnostic))
        )
        responses["/api/diagnostic/status"].append((200, json.dumps(gpio)))
    return responses


class Rc2gQualityRefreshOnceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle, cls.manifest_sha256 = QUALITY_BUNDLES["atkinson"]
        cls.snapshot = runner._load_candidate_snapshot(
            cls.bundle, cls.manifest_sha256
        )

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.registry = self.root / "registry"
        self.registry.mkdir()
        self.result_dir = self.root / "result"
        self.contract = runner._build_run_contract(
            self.snapshot,
            expected_prior_job_id=1,
            expected_prior_operation_id=1,
            expected_prior_frame_sha256=MAP_FRAME_SHA256,
            expected_prior_frame_fnv1a=MAP_FRAME_FNV1A,
            expected_prior_cs1_dtm_fnv1a=MAP_CS1_DTM_FNV1A,
            expected_prior_cs2_dtm_fnv1a=MAP_CS2_DTM_FNV1A,
            expected_target_job_id=2,
            expected_target_operation_id=2,
        )

    def _run(
        self,
        requester,
        *,
        result_dir: Path | None = None,
        contract: runner._RunContract | None = None,
        patch_snapshot: bool = True,
        **overrides,
    ):
        active = contract or self.contract
        arguments = {
            "expected_manifest_sha256": active.snapshot.manifest_file_sha256,
            "expected_prior_job_id": active.expected_prior_job_id,
            "expected_prior_operation_id": active.expected_prior_operation_id,
            "expected_prior_frame_sha256": active.expected_prior_frame_sha256,
            "expected_prior_frame_fnv1a": active.expected_prior_frame_fnv1a,
            "expected_prior_cs1_dtm_fnv1a": (
                active.expected_prior_cs1_dtm_fnv1a
            ),
            "expected_prior_cs2_dtm_fnv1a": (
                active.expected_prior_cs2_dtm_fnv1a
            ),
            "expected_target_job_id": active.expected_target_job_id,
            "expected_target_operation_id": active.expected_target_operation_id,
            "authorization_confirmation": (
                active.required_authorization_confirmation
            ),
            "confirm_j2_powered_supervised": True,
            "confirm_supply_and_temperature_normal": True,
            "confirm_reviewed_strict_preview": True,
            "sleeper": lambda _seconds: None,
            "clock": TickClock(),
        }
        arguments.update(overrides)
        snapshot_patch = (
            mock.patch.object(
                runner, "_load_candidate_snapshot", return_value=active.snapshot
            )
            if patch_snapshot
            else mock.patch.object(runner, "_load_candidate_snapshot", wraps=runner._load_candidate_snapshot)
        )
        with snapshot_patch, mock.patch.object(
            runner, "_authorization_registry", return_value=self.registry
        ), mock.patch.object(runner, "http_request", side_effect=requester):
            return runner.run_rc2g_quality_refresh_once(
                self.result_dir if result_dir is None else result_dir,
                "http://device",
                active.snapshot.directory,
                **arguments,
            )

    def test_deep_description_is_offline_and_binds_narrow_timing(self) -> None:
        with mock.patch.object(runner, "http_request") as request, mock.patch.object(
            runner, "_authorization_registry"
        ) as registry:
            described = runner.describe_rc2g_quality_action(
                self.bundle,
                expected_manifest_sha256=self.manifest_sha256,
                expected_prior_job_id=1,
                expected_prior_operation_id=1,
                expected_prior_frame_sha256=MAP_FRAME_SHA256,
                expected_prior_frame_fnv1a=MAP_FRAME_FNV1A,
                expected_prior_cs1_dtm_fnv1a=MAP_CS1_DTM_FNV1A,
                expected_prior_cs2_dtm_fnv1a=MAP_CS2_DTM_FNV1A,
                expected_target_job_id=2,
                expected_target_operation_id=2,
            )
        request.assert_not_called()
        registry.assert_not_called()
        self.assertIs(described["device_io_performed"], False)
        self.assertIs(described["claim_created"], False)
        self.assertEqual(
            described["action_identity_sha256"], self.contract.action_identity_sha256
        )
        self.assertEqual(
            described["required_authorization_confirmation"],
            self.contract.required_authorization_confirmation,
        )
        prior_identity = described["action_identity"]["prior"]
        self.assertEqual(prior_identity["frame_sha256"], MAP_FRAME_SHA256)
        self.assertEqual(
            prior_identity["cs1_dtm_fnv1a"], f"0x{MAP_CS1_DTM_FNV1A:08X}"
        )
        self.assertEqual(
            prior_identity["cs2_dtm_fnv1a"], f"0x{MAP_CS2_DTM_FNV1A:08X}"
        )
        self.assertIn("firmware report does not expose SHA-256", prior_identity[
            "frame_sha256_evidence_scope"
        ])
        self.assertEqual(runner.NOMINAL_JOB_DURATION_MS, (28_000, 45_000))
        self.assertEqual(
            runner.NOMINAL_STAGE_TIMING_MS["cs1_upload_ms"], (1_500, 5_000)
        )
        self.assertEqual(runner.NOMINAL_STAGE_TIMING_MS["pon_ms"], (50, 2_000))
        self.assertEqual(runner.NOMINAL_STAGE_TIMING_MS["drf_ms"], (18_000, 26_000))
        self.assertEqual(runner.NOMINAL_STAGE_TIMING_MS["post_psr_ms"], (0, 100))
        self.assertEqual(runner.MAX_QUEUE_DELAY_MS, 5_000)
        self.assertEqual(runner.MAX_JOB_DRIVER_DURATION_DELTA_MS, 2_000)

    def test_four_quality_algorithms_have_unique_per_action_authorizations(self) -> None:
        identities: set[str] = set()
        confirmations: set[str] = set()
        prior_sha256 = MAP_FRAME_SHA256
        prior_fnv = MAP_FRAME_FNV1A
        prior_cs1 = MAP_CS1_DTM_FNV1A
        prior_cs2 = MAP_CS2_DTM_FNV1A
        for index, (algorithm, (directory, manifest_sha256)) in enumerate(
            QUALITY_BUNDLES.items(), start=2
        ):
            snapshot = runner._load_candidate_snapshot(directory, manifest_sha256)
            contract = runner._build_run_contract(
                snapshot,
                expected_prior_job_id=index - 1,
                expected_prior_operation_id=index - 1,
                expected_prior_frame_sha256=prior_sha256,
                expected_prior_frame_fnv1a=prior_fnv,
                expected_prior_cs1_dtm_fnv1a=prior_cs1,
                expected_prior_cs2_dtm_fnv1a=prior_cs2,
                expected_target_job_id=index,
                expected_target_operation_id=index,
            )
            self.assertEqual(snapshot.algorithm, algorithm)
            identities.add(contract.action_identity_sha256)
            confirmations.add(contract.required_authorization_confirmation)
            self.assertEqual(
                contract.action_identity["prior"]["frame_sha256"], prior_sha256
            )
            prior_sha256 = snapshot.frame_sha256
            prior_fnv = snapshot.frame_fnv1a
            prior_cs1 = int(str(snapshot.controllers[0]["dtm_fnv1a"]), 16)
            prior_cs2 = int(str(snapshot.controllers[1]["dtm_fnv1a"]), 16)
        self.assertEqual(len(identities), 4)
        self.assertEqual(len(confirmations), 4)

    def test_success_claims_before_network_posts_once_and_keeps_busy_informational(self) -> None:
        scripted = ScriptedRequester(
            _responses(self.snapshot.frame, self.contract, post_gpio={
                "busy": 1,
                "rst": 0,
                "cs": 0,
                "cs2": 0,
            })
        )

        def checked_requester(*args, **kwargs):
            claim = self.registry / self.contract.action_identity_sha256
            self.assertTrue(claim.is_file())
            self.assertTrue((self.result_dir / runner.LOCK_FILENAME).is_file())
            return scripted(*args, **kwargs)

        result = self._run(checked_requester)
        posts = [call for call in scripted.calls if call[0] == "POST"]
        self.assertEqual(posts, [("POST", "/api/frame")])
        self.assertEqual(result["network_report"]["job_id"], 2)
        self.assertEqual(result["target_job_raw"], result["network_report"]["job"])
        self.assertEqual(result["network_report"]["diagnostic"]["operation_id"], 2)
        self.assertEqual(result["post_refresh_gpio"]["busy_level"], 1)
        self.assertIs(
            result["post_refresh_gpio"]["busy_after_rst_low_is_informational"],
            True,
        )
        self.assertEqual(result["request_audit"]["post_issued_count"], 1)
        self.assertTrue(
            all(
                stage
                in result["network_report"]["diagnostic"]["busy_trace"][
                    "stages"
                ]
                for stage in ("reset", "pon", "drf", "pof", "post_psr")
            )
        )

    def test_wrong_authorization_is_preclaim_zero_network(self) -> None:
        scripted = ScriptedRequester(_responses(self.snapshot.frame, self.contract))
        with mock.patch.object(
            runner, "_authorization_registry"
        ) as registry, mock.patch.object(runner, "http_request") as request, mock.patch.object(
            runner, "_load_candidate_snapshot", return_value=self.snapshot
        ):
            with self.assertRaisesRegex(
                runner.Rc2gQualityRefreshError, "exact per-action"
            ):
                runner.run_rc2g_quality_refresh_once(
                    self.result_dir,
                    "http://device",
                    self.bundle,
                    expected_manifest_sha256=self.manifest_sha256,
                    expected_prior_job_id=1,
                    expected_prior_operation_id=1,
                    expected_prior_frame_sha256=MAP_FRAME_SHA256,
                    expected_prior_frame_fnv1a=MAP_FRAME_FNV1A,
                    expected_prior_cs1_dtm_fnv1a=MAP_CS1_DTM_FNV1A,
                    expected_prior_cs2_dtm_fnv1a=MAP_CS2_DTM_FNV1A,
                    expected_target_job_id=2,
                    expected_target_operation_id=2,
                    authorization_confirmation="yes",
                    confirm_j2_powered_supervised=True,
                    confirm_supply_and_temperature_normal=True,
                    confirm_reviewed_strict_preview=True,
                )
        registry.assert_not_called()
        request.assert_not_called()
        self.assertEqual(scripted.calls, [])
        self.assertFalse(self.result_dir.exists())

    def test_prior_identity_mismatch_is_unknown_zero_post_get_only_capture(self) -> None:
        responses = _responses(
            self.snapshot.frame,
            self.contract,
            prior_job_mutation=lambda job: job.__setitem__("frame_fnv1a", 0),
            supplemental=True,
        )
        scripted = ScriptedRequester(responses)
        with self.assertRaises(runner.Rc2gQualityRefreshUnknown):
            self._run(scripted)
        self.assertEqual([call for call in scripted.calls if call[0] == "POST"], [])
        recorded = json.loads(
            (self.result_dir / runner.RESULT_FILENAME).read_text("utf-8")
        )
        self.assertEqual(recorded["outcome"], "unknown_do_not_retry")
        self.assertIsNone(recorded["network_report"])
        captures = recorded["best_effort_postclaim_evidence"]["captures"]
        self.assertTrue(all(item["method"] == "GET" for item in captures.values()))

    def test_prior_missing_new_drf_edge_is_unknown_before_post(self) -> None:
        def remove_edge(diagnostic):
            diagnostic["busy_trace"]["drf"]["assertion_after_idle"] = False

        scripted = ScriptedRequester(
            _responses(
                self.snapshot.frame,
                self.contract,
                prior_diagnostic_mutation=remove_edge,
                supplemental=True,
            )
        )
        with self.assertRaises(runner.Rc2gQualityRefreshUnknown):
            self._run(scripted)
        self.assertEqual([call for call in scripted.calls if call[0] == "POST"], [])
        recorded = json.loads(
            (self.result_dir / runner.RESULT_FILENAME).read_text("utf-8")
        )
        self.assertIn("BUSY trace", recorded["error"]["message"])

    def test_prior_dtm_mismatch_is_unknown_before_post(self) -> None:
        def mismatch_cs1(diagnostic):
            diagnostic["cs1_dtm_fnv1a"] = (
                MAP_CS1_DTM_FNV1A + 1
            ) & 0xFFFFFFFF

        scripted = ScriptedRequester(
            _responses(
                self.snapshot.frame,
                self.contract,
                prior_diagnostic_mutation=mismatch_cs1,
                supplemental=True,
            )
        )
        with self.assertRaises(runner.Rc2gQualityRefreshUnknown):
            self._run(scripted)
        self.assertEqual([call for call in scripted.calls if call[0] == "POST"], [])
        recorded = json.loads(
            (self.result_dir / runner.RESULT_FILENAME).read_text("utf-8")
        )
        self.assertIn("frozen prior DTM", recorded["error"]["message"])
        self.assertEqual(
            recorded["action_identity"]["prior"]["cs1_dtm_fnv1a"],
            f"0x{MAP_CS1_DTM_FNV1A:08X}",
        )

    def test_target_stage_timing_failure_preserves_report_and_raw_diagnostic(self) -> None:
        def slow_pon(diagnostic):
            diagnostic["pon_ms"] = 2_001
            diagnostic["total_ms"] = 34_000
            diagnostic["busy_trace"]["pon"]["wait_ms"] = 2_001

        scripted = ScriptedRequester(
            _responses(
                self.snapshot.frame,
                self.contract,
                target_diagnostic_mutation=slow_pon,
                supplemental=True,
            )
        )
        with self.assertRaises(runner.Rc2gQualityRefreshUnknown):
            self._run(scripted)
        self.assertEqual(
            [call for call in scripted.calls if call[0] == "POST"],
            [("POST", "/api/frame")],
        )
        recorded = json.loads(
            (self.result_dir / runner.RESULT_FILENAME).read_text("utf-8")
        )
        self.assertIsNotNone(recorded["network_report"])
        self.assertEqual(recorded["target_diagnostic_raw"]["pon_ms"], 2_001)
        self.assertIn("50..2000", recorded["error"]["message"])

    def test_target_missing_new_pof_edge_fails_after_the_only_post(self) -> None:
        def remove_edge(diagnostic):
            diagnostic["busy_trace"]["pof"]["assertion_after_idle"] = False

        scripted = ScriptedRequester(
            _responses(
                self.snapshot.frame,
                self.contract,
                target_diagnostic_mutation=remove_edge,
                supplemental=True,
            )
        )
        with self.assertRaises(runner.Rc2gQualityRefreshUnknown):
            self._run(scripted)
        self.assertEqual(
            [call for call in scripted.calls if call[0] == "POST"],
            [("POST", "/api/frame")],
        )
        recorded = json.loads(
            (self.result_dir / runner.RESULT_FILENAME).read_text("utf-8")
        )
        self.assertIsNone(recorded["network_report"])
        self.assertIn("BUSY", recorded["error"]["message"])

    def test_post_rst_busy_samples_may_differ_and_are_preserved(self) -> None:
        def separate_samples(diagnostic):
            diagnostic["busy_trace"]["safe_finish"]["busy_after_5ms"] = 1
            diagnostic["busy_trace"]["final_gpio"]["busy"] = 0

        scripted = ScriptedRequester(
            _responses(
                self.snapshot.frame,
                self.contract,
                target_diagnostic_mutation=separate_samples,
                post_gpio={"busy": 1, "rst": 0, "cs": 0, "cs2": 0},
            )
        )
        result = self._run(scripted)
        trace = result["network_report"]["diagnostic"]["busy_trace"]
        self.assertEqual(trace["safe_finish"]["busy_after_5ms"], 1)
        self.assertEqual(trace["final_gpio"]["busy"], 0)
        self.assertEqual(result["post_refresh_gpio"]["busy_level"], 1)
        self.assertEqual(
            [call for call in scripted.calls if call[0] == "POST"],
            [("POST", "/api/frame")],
        )

    def test_invalid_post_gpio_preserves_raw_and_never_recovers(self) -> None:
        scripted = ScriptedRequester(
            _responses(
                self.snapshot.frame,
                self.contract,
                post_gpio={"busy": 0, "rst": 1, "cs": 0, "cs2": 0},
            )
        )
        with self.assertRaises(runner.Rc2gQualityRefreshUnknown):
            self._run(scripted)
        self.assertEqual(
            [call for call in scripted.calls if call[0] == "POST"],
            [("POST", "/api/frame")],
        )
        recorded = json.loads(
            (self.result_dir / runner.RESULT_FILENAME).read_text("utf-8")
        )
        self.assertIs(recorded["protocol_verified"], True)
        self.assertEqual(recorded["post_refresh_gpio_status_raw"]["rst"], 1)
        self.assertIsNotNone(recorded["network_report"])
        audit_posts = [
            call
            for call in recorded["request_audit"]["calls"]
            if call["method"] == "POST"
        ]
        self.assertEqual(len(audit_posts), 1)

    def test_transport_loss_consumes_claim_and_second_invocation_is_zero_network(self) -> None:
        scripted = ScriptedRequester(
            _responses(
                self.snapshot.frame,
                self.contract,
                frame_response=OSError("simulated transport loss"),
            )
        )
        with self.assertRaises(runner.Rc2gQualityRefreshUnknown):
            self._run(scripted)
        self.assertEqual(
            [call for call in scripted.calls if call[0] == "POST"],
            [("POST", "/api/frame")],
        )
        calls = list(scripted.calls)
        with self.assertRaisesRegex(
            runner.Rc2gQualityRefreshError, "already permanently consumed"
        ):
            self._run(scripted, result_dir=self.root / "second")
        self.assertEqual(scripted.calls, calls)
        self.assertFalse((self.root / "second").exists())

    def test_existing_result_directory_is_preclaim_zero_network(self) -> None:
        self.result_dir.mkdir()
        scripted = ScriptedRequester(_responses(self.snapshot.frame, self.contract))
        with mock.patch.object(runner, "_authorization_registry") as registry:
            with self.assertRaisesRegex(
                runner.Rc2gQualityRefreshError, "already exists"
            ):
                self._run(scripted)
        registry.assert_not_called()
        self.assertEqual(scripted.calls, [])

    def test_non_next_target_is_rejected_before_claim_or_network(self) -> None:
        with self.assertRaisesRegex(runner.Rc2gQualityRefreshError, "next non-zero"):
            runner._build_run_contract(
                self.snapshot,
                expected_prior_job_id=1,
                expected_prior_operation_id=1,
                expected_prior_frame_sha256=MAP_FRAME_SHA256,
                expected_prior_frame_fnv1a=MAP_FRAME_FNV1A,
                expected_prior_cs1_dtm_fnv1a=MAP_CS1_DTM_FNV1A,
                expected_prior_cs2_dtm_fnv1a=MAP_CS2_DTM_FNV1A,
                expected_target_job_id=3,
                expected_target_operation_id=2,
            )

    def test_cli_supports_offline_authorization_description_without_escape_hatches(self) -> None:
        parsed = runner.parse_args(
            [
                "--candidate-dir",
                str(self.bundle),
                "--manifest-sha256",
                self.manifest_sha256,
                "--expected-prior-job-id",
                "1",
                "--expected-prior-operation-id",
                "1",
                "--expected-prior-frame-sha256",
                MAP_FRAME_SHA256,
                "--expected-prior-frame-fnv1a",
                "0x9D04142D",
                "--expected-prior-cs1-dtm-fnv1a",
                f"0x{MAP_CS1_DTM_FNV1A:08X}",
                "--expected-prior-cs2-dtm-fnv1a",
                f"0x{MAP_CS2_DTM_FNV1A:08X}",
                "--expected-target-job-id",
                "2",
                "--expected-target-operation-id",
                "2",
                "--describe-only",
            ]
        )
        self.assertTrue(parsed.describe_only)
        self.assertEqual(parsed.expected_prior_frame_sha256, MAP_FRAME_SHA256)
        self.assertEqual(parsed.expected_prior_frame_fnv1a, MAP_FRAME_FNV1A)
        self.assertEqual(parsed.expected_prior_cs1_dtm_fnv1a, MAP_CS1_DTM_FNV1A)
        self.assertEqual(parsed.expected_prior_cs2_dtm_fnv1a, MAP_CS2_DTM_FNV1A)
        source = inspect.getsource(runner.parse_args)
        for forbidden in ("--force", "--retry", "--recovery", "--cancel"):
            self.assertNotIn(forbidden, source)
        public = inspect.signature(runner.run_rc2g_quality_refresh_once).parameters
        for forbidden in ("requester", "registry", "force", "retry", "recovery"):
            self.assertNotIn(forbidden, public)


if __name__ == "__main__":
    unittest.main()
