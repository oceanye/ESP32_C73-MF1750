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

from host.epd_frame import controller_stream, fnv1a, generate_fixture
from tests.test_frame_tool import ScriptedRequester, add_valid_busy_trace, version_body
from tools import g1_s1_macro4_redisplay_once as runner


REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_BUNDLE = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "G1S1_QUALITY_MACRO4_BLUE_NOISE_OFFLINE_20260807"
)
PRODUCTION_OLD_CLAIM = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".g1_s1_macro4_quality_registry"
    / runner.EXPECTED_MANIFEST_SHA256
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
) -> dict[str, object]:
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
        "total_ms": 32_000,
        "cs1_upload_ms": 1_500,
        "cs2_upload_ms": 1_500,
        "pon_ms": 100,
        "drf_ms": 25_000,
        "pof_ms": 100,
        "post_psr_ms": 20,
        "last_wait_ms": 20,
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
    # Keep the redisplay tests ready for the reviewed instrumented build: the
    # runner has one centralized build constant, and changing it should not
    # require hand-editing every synthetic device response.
    if "BUSYEDGE" in runner.EXPECTED_BUILD_TAG:
        add_valid_busy_trace(diagnostic)
    return diagnostic


def _responses(
    macro_frame: bytes,
    *,
    post_gpio: dict[str, int] | None = None,
) -> dict[str, list[tuple[int, str] | Exception]]:
    map_frame = generate_fixture(runner.MAP_FIXTURE_NAME)
    prior_job = _job(runner.EXPECTED_PRIOR_JOB_ID, runner.MAP_FRAME_FNV1A, 1_000)
    target_job = _job(runner.EXPECTED_TARGET_JOB_ID, runner.EXPECTED_FRAME_FNV1A, 50_000)
    prior_diagnostic = _diagnostic(map_frame, prior_job, runner.EXPECTED_PRIOR_OPERATION_ID)
    target_diagnostic = _diagnostic(
        macro_frame, target_job, runner.EXPECTED_TARGET_OPERATION_ID
    )
    enqueue = {
        "ok": True,
        "bytes": len(macro_frame),
        "fnv1a": fnv1a(macro_frame),
        "free_psram": 7_800_000,
        "job_id": runner.EXPECTED_TARGET_JOB_ID,
    }
    idle = {"busy": 0, **runner.EXPECTED_PANEL_OUTPUTS_LOW}
    final_gpio = dict(post_gpio if post_gpio is not None else idle)
    return {
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
            (200, json.dumps(target_diagnostic)),
        ],
        "/api/diagnostic/status": [
            (200, json.dumps(idle)),
            (200, json.dumps(final_gpio)),
            (200, json.dumps(final_gpio)),
        ],
        "/api/frame": [(202, json.dumps(enqueue))],
    }


class Macro4RedisplayOnceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bundle = self.root / "candidate"
        self.bundle.mkdir()
        for source in PRODUCTION_BUNDLE.iterdir():
            shutil.copyfile(source, self.bundle / source.name)
        self.frame = (self.bundle / "frame.bin").read_bytes()
        self.manifest = json.loads((self.bundle / "manifest.json").read_bytes())
        self.old_claim = self.root / "old-quality-claim"
        shutil.copyfile(PRODUCTION_OLD_CLAIM, self.old_claim)
        self.old_claim_bytes = self.old_claim.read_bytes()
        self.registry = self.root / "redisplay-registry"
        self.registry.mkdir()
        self.result_dir = self.root / "result"

    def _run(
        self,
        requester: ScriptedRequester,
        *,
        result_dir: Path | None = None,
        registry: Path | None = None,
        patch_refresh=None,
        **overrides,
    ):
        active_registry = self.registry if registry is None else registry
        active_registry.mkdir(exist_ok=True)
        arguments = {
            "authorization_confirmation": runner.REQUIRED_AUTHORIZATION_CONFIRMATION,
            "confirm_j2_powered_supervised": True,
            "confirm_supply_and_temperature_normal": True,
            "confirm_visual_quality_concern_redisplay": True,
            "sleeper": lambda _seconds: None,
            "clock": TickClock(),
        }
        arguments.update(overrides)
        patches = [
            mock.patch.object(runner, "DEFAULT_CANDIDATE_DIRECTORY", self.bundle),
            mock.patch.object(runner, "ORIGINAL_QUALITY_CLAIM_PATH", self.old_claim),
            mock.patch.object(
                runner, "_deep_validate_candidate_directory", return_value=self.manifest
            ),
            mock.patch.object(runner, "_authorization_registry", return_value=active_registry),
            mock.patch.object(runner, "http_request", side_effect=requester),
        ]
        if patch_refresh is not None:
            patches.append(mock.patch.object(runner, "perform_refresh", side_effect=patch_refresh))
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            if patch_refresh is None:
                return runner.run_macro4_redisplay_once(
                    self.result_dir if result_dir is None else result_dir,
                    "http://device",
                    **arguments,
                )
            with patches[5]:
                return runner.run_macro4_redisplay_once(
                    self.result_dir if result_dir is None else result_dir,
                    "http://device",
                    **arguments,
                )

    def test_frozen_production_identities_and_independent_registry(self) -> None:
        self.assertEqual(runner.DEFAULT_CANDIDATE_DIRECTORY, PRODUCTION_BUNDLE)
        self.assertEqual(runner.EXPECTED_FRAME_FNV1A, 0x092C9775)
        self.assertEqual(
            (runner.EXPECTED_CS1_DTM_FNV1A, runner.EXPECTED_CS2_DTM_FNV1A),
            (0x3F1601D5, 0x52ECC935),
        )
        self.assertEqual(
            (
                runner.MAP_FRAME_FNV1A,
                runner.MAP_CS1_DTM_FNV1A,
                runner.MAP_CS2_DTM_FNV1A,
            ),
            (0x9D04142D, 0xF26832DD, 0xFE199FF5),
        )
        self.assertEqual(runner.EXPECTED_PRIOR_JOB_ID, 1)
        self.assertEqual(runner.EXPECTED_PRIOR_OPERATION_ID, 1)
        self.assertEqual(runner.EXPECTED_TARGET_JOB_ID, 2)
        self.assertEqual(runner.EXPECTED_TARGET_OPERATION_ID, 2)
        self.assertEqual(
            runner._sha256(runner._canonical_json(runner.ACTION_IDENTITY)),
            runner.ACTION_IDENTITY_SHA256,
        )
        self.assertEqual(
            runner._sha256(runner.REQUIRED_AUTHORIZATION_CONFIRMATION.encode("ascii")),
            runner.AUTHORIZATION_CONFIRMATION_SHA256,
        )
        self.assertNotEqual(
            runner.DEFAULT_AUTHORIZATION_REGISTRY.parent / runner.FIXED_ACTION_ID,
            runner.ORIGINAL_QUALITY_CLAIM_PATH,
        )
        self.assertEqual(
            hashlib.sha256(PRODUCTION_OLD_CLAIM.read_bytes()).hexdigest(),
            runner.ORIGINAL_QUALITY_CLAIM_SHA256,
        )

    def test_real_candidate_deep_validation_and_original_claim_interoperate(self) -> None:
        snapshot = runner._load_candidate_snapshot()
        claim = runner._load_original_quality_claim()
        self.assertEqual(snapshot.frame, self.frame)
        self.assertEqual(snapshot.manifest, self.manifest)
        self.assertEqual(claim["attempt_id"], runner.ORIGINAL_QUALITY_ATTEMPT_ID)

    def test_cli_has_required_confirmations_and_no_retry_or_override_surface(self) -> None:
        parsed = runner.parse_args(
            [
                "--result-dir", str(self.result_dir),
                "--url", "http://device",
                "--confirm", runner.REQUIRED_AUTHORIZATION_CONFIRMATION,
                "--confirm-j2-powered-supervised",
                "--confirm-supply-and-temperature-normal",
                "--confirm-visual-quality-concern-redisplay",
            ]
        )
        self.assertTrue(parsed.confirm_j2_powered_supervised)
        self.assertTrue(parsed.confirm_supply_and_temperature_normal)
        self.assertTrue(parsed.confirm_visual_quality_concern_redisplay)
        parameters = inspect.signature(runner.run_macro4_redisplay_once).parameters
        for forbidden in ("candidate_dir", "requester", "registry", "retry", "recovery", "force"):
            self.assertNotIn(forbidden, parameters)
        source = inspect.getsource(runner.parse_args)
        self.assertNotIn("--retry", source)
        self.assertNotIn("--recovery", source)
        self.assertNotIn("--force", source)

    def test_wrong_confirmation_is_preclaim_and_zero_network(self) -> None:
        with mock.patch.object(runner, "_deep_validate_candidate_directory") as validator, \
             mock.patch.object(runner, "_authorization_registry") as registry, \
             mock.patch.object(runner, "http_request") as request:
            with self.assertRaisesRegex(runner.Macro4RedisplayError, "exact frozen-frame"):
                runner.run_macro4_redisplay_once(
                    self.result_dir,
                    "http://device",
                    authorization_confirmation="yes",
                    confirm_j2_powered_supervised=True,
                    confirm_supply_and_temperature_normal=True,
                    confirm_visual_quality_concern_redisplay=True,
                )
        validator.assert_not_called()
        registry.assert_not_called()
        request.assert_not_called()
        self.assertFalse(self.result_dir.exists())

    def test_each_confirmation_is_required_before_claim_or_network(self) -> None:
        flags = (
            "confirm_j2_powered_supervised",
            "confirm_supply_and_temperature_normal",
            "confirm_visual_quality_concern_redisplay",
        )
        for flag in flags:
            with self.subTest(flag=flag), mock.patch.object(
                runner, "_deep_validate_candidate_directory"
            ) as validator, mock.patch.object(runner, "http_request") as request:
                arguments = {name: True for name in flags}
                arguments[flag] = False
                with self.assertRaisesRegex(runner.Macro4RedisplayError, "confirmations"):
                    runner.run_macro4_redisplay_once(
                        self.result_dir,
                        "http://device",
                        authorization_confirmation=runner.REQUIRED_AUTHORIZATION_CONFIRMATION,
                        **arguments,
                    )
            validator.assert_not_called()
            request.assert_not_called()

    def test_success_proves_map_job1_then_one_macro4_job2_post(self) -> None:
        scripted = ScriptedRequester(_responses(self.frame))
        result = self._run(scripted)
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
        self.assertEqual([call for call in scripted.calls if call[0] == "POST"], [
            ("POST", "/api/frame")
        ])
        self.assertEqual(result["prior_map_job1_preflight"]["job"]["job_id"], 1)
        self.assertEqual(
            result["prior_map_job1_preflight"]["diagnostic_validated"]["operation_id"], 1
        )
        self.assertEqual(result["network_report"]["job_id"], 2)
        self.assertEqual(result["network_report"]["diagnostic"]["operation_id"], 2)
        self.assertEqual(result["post_refresh_diagnostic_raw"]["operation_id"], 2)
        self.assertEqual(result["nominal_timing"]["pon_ms"], 100)
        self.assertEqual(
            result["post_refresh_gpio_status_raw"],
            {"busy": 0, **runner.EXPECTED_PANEL_OUTPUTS_LOW},
        )
        self.assertTrue(
            result["network_report"]["diagnostic"]["busy_trace"][
                "command_edge_contract_verified"
            ]
        )
        self.assertEqual(result["request_audit"]["post_attempt_count"], 1)
        self.assertEqual(result["request_audit"]["post_issued_count"], 1)
        self.assertEqual(result["outcome"], "protocol_verified_manual_observation_required")
        self.assertTrue((self.registry / runner.FIXED_ACTION_ID).is_file())
        self.assertTrue((self.result_dir / runner.LOCK_FILENAME).is_file())
        self.assertTrue((self.result_dir / runner.RESULT_FILENAME).is_file())
        self.assertEqual(self.old_claim.read_bytes(), self.old_claim_bytes)

    def test_map_prior_hash_mismatch_is_unknown_with_zero_posts(self) -> None:
        responses = _responses(self.frame)
        prior = json.loads(responses["/api/job"][0][1])
        prior["frame_fnv1a"] = 0
        responses["/api/job"][0] = (200, json.dumps(prior))
        scripted = ScriptedRequester(responses)
        with self.assertRaises(runner.Macro4RedisplayUnknown):
            self._run(scripted)
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 0)
        recorded = json.loads((self.result_dir / runner.RESULT_FILENAME).read_text("utf-8"))
        self.assertEqual(recorded["outcome"], "unknown_do_not_retry")
        self.assertEqual(recorded["request_audit"]["post_issued_count"], 0)

    def test_map_prior_operation_sequence_and_timing_are_strict(self) -> None:
        mutations = {
            "operation": lambda value: value.__setitem__("operation_id", 9),
            "sequence": lambda value: value.__setitem__("sequence_ok", False),
            "timing": lambda value: value.__setitem__("drf_ms", 35_001),
            "job5-like-PON": lambda value: value.__setitem__("pon_ms", 37_110),
            "dtm": lambda value: value.__setitem__("cs1_dtm_fnv1a", 0),
            "busy-edge": lambda value: value["busy_trace"]["pon"].__setitem__(
                "assertion_after_idle", False
            ),
            "unsafe-pin": lambda value: value["busy_trace"]["final_gpio"].__setitem__(
                "rst", 1
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                responses = _responses(self.frame)
                diagnostic = json.loads(responses["/api/diagnostic/report"][0][1])
                mutate(diagnostic)
                responses["/api/diagnostic/report"][0] = (200, json.dumps(diagnostic))
                scripted = ScriptedRequester(responses)
                sub_registry = self.root / f"registry-{label}"
                with self.assertRaises(runner.Macro4RedisplayUnknown):
                    self._run(
                        scripted,
                        result_dir=self.root / f"result-{label}",
                        registry=sub_registry,
                    )
                self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 0)

    def test_map_prior_gpio_requires_low_outputs_but_busy_is_informational(self) -> None:
        for busy in (0, 1):
            self.assertEqual(
                runner._validate_gpio_snapshot(
                    {"busy": busy, "rst": 0, "cs": 0, "cs2": 0},
                    label="test GPIO",
                )["busy"],
                busy,
            )
        responses = _responses(self.frame)
        responses["/api/diagnostic/status"][0] = (
            200, json.dumps({"busy": 1, "rst": 1, "cs": 0, "cs2": 0})
        )
        scripted = ScriptedRequester(responses)
        with self.assertRaises(runner.Macro4RedisplayUnknown):
            self._run(scripted)
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 0)

    def test_post_gpio_mismatch_preserves_network_report_and_raw_gpio(self) -> None:
        raw = {"busy": 0, "rst": 0, "cs": 1, "cs2": 0}
        scripted = ScriptedRequester(_responses(self.frame, post_gpio=raw))
        with self.assertRaises(runner.Macro4RedisplayUnknown):
            self._run(scripted)
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
        recorded = json.loads((self.result_dir / runner.RESULT_FILENAME).read_text("utf-8"))
        self.assertEqual(recorded["network_report"]["job_id"], 2)
        self.assertEqual(recorded["post_refresh_gpio_status_raw"], raw)
        self.assertEqual(recorded["outcome"], "unknown_do_not_retry")

    def test_target_raw_timing_anomaly_is_unknown_after_the_only_post(self) -> None:
        responses = _responses(self.frame)
        for index in (1, 2):
            raw = json.loads(responses["/api/diagnostic/report"][index][1])
            raw["cs1_upload_ms"] = 6_000
            raw["total_ms"] = 37_000
            responses["/api/diagnostic/report"][index] = (200, json.dumps(raw))
        scripted = ScriptedRequester(responses)
        with self.assertRaises(runner.Macro4RedisplayUnknown):
            self._run(scripted)
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
        recorded = json.loads((self.result_dir / runner.RESULT_FILENAME).read_text("utf-8"))
        self.assertEqual(recorded["post_refresh_diagnostic_raw"]["cs1_upload_ms"], 6_000)
        self.assertEqual(recorded["outcome"], "unknown_do_not_retry")

    def test_post_transport_exception_is_unknown_and_claim_cannot_be_reused(self) -> None:
        responses = _responses(self.frame)
        responses["/api/frame"] = [OSError("simulated transport loss")]
        scripted = ScriptedRequester(responses)
        with self.assertRaises(runner.Macro4RedisplayUnknown):
            self._run(scripted)
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
        recorded = json.loads((self.result_dir / runner.RESULT_FILENAME).read_text("utf-8"))
        self.assertEqual(recorded["request_audit"]["post_issued_count"], 1)
        self.assertIsNotNone(recorded["best_effort_postclaim_evidence"])
        calls = list(scripted.calls)
        with self.assertRaisesRegex(runner.Macro4RedisplayError, "already permanently consumed"):
            self._run(scripted, result_dir=self.root / "second")
        self.assertEqual(scripted.calls, calls)
        self.assertFalse((self.root / "second").exists())

    def test_audited_requester_blocks_a_second_post_before_issuing_it(self) -> None:
        scripted = ScriptedRequester(_responses(self.frame))

        def malicious_refresh(base_url, frame, *, requester, **_kwargs):
            requester(base_url, "/api/frame", method="POST", data=frame, timeout=20.0)
            requester(base_url, "/api/frame", method="POST", data=frame, timeout=20.0)
            raise AssertionError("unreachable")

        with self.assertRaises(runner.Macro4RedisplayUnknown):
            self._run(scripted, patch_refresh=malicious_refresh)
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
        recorded = json.loads((self.result_dir / runner.RESULT_FILENAME).read_text("utf-8"))
        self.assertEqual(recorded["request_audit"]["post_attempt_count"], 2)
        self.assertEqual(recorded["request_audit"]["post_issued_count"], 1)

    def test_target_report_rechecks_job_operation_hash_dtm_and_sequence(self) -> None:
        scripted = ScriptedRequester(_responses(self.frame))
        result = self._run(scripted)
        mutations = {
            "job": lambda value: value["job"].__setitem__("job_id", 3),
            "hash": lambda value: value["job"].__setitem__("frame_fnv1a", 0),
            "operation": lambda value: value["diagnostic"].__setitem__("operation_id", 3),
            "dtm": lambda value: value["diagnostic"]["physical_controllers"][0].__setitem__(
                "dtm_fnv1a", 0
            ),
            "sequence": lambda value: value["diagnostic"].__setitem__(
                "sequence_verified", False
            ),
            "busy-trace": lambda value: value["diagnostic"]["busy_trace"].__setitem__(
                "command_edge_contract_verified", False
            ),
            "target-PON-only-abnormal": lambda value: value["diagnostic"][
                "busy_trace"
            ]["stages"]["pon"].__setitem__("wait_ms", 10_000),
            "job5-like-duration": lambda value: value["job"].__setitem__(
                "finished_at_ms", value["job"]["started_at_ms"] + 89_049
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                changed = copy.deepcopy(result["network_report"])
                mutate(changed)
                with self.assertRaises(runner.Macro4RedisplayError):
                    runner._validate_network_report(changed)

    def test_original_claim_corruption_is_preclaim_and_zero_network(self) -> None:
        self.old_claim.write_bytes(self.old_claim_bytes + b"\n")
        scripted = ScriptedRequester(_responses(self.frame))
        with self.assertRaisesRegex(runner.Macro4RedisplayError, "claim SHA-256 changed"):
            self._run(scripted)
        self.assertEqual(scripted.calls, [])
        self.assertFalse((self.registry / runner.FIXED_ACTION_ID).exists())
        self.assertFalse(self.result_dir.exists())

    def test_existing_result_directory_rejected_before_validation_claim_or_network(self) -> None:
        self.result_dir.mkdir()
        with mock.patch.object(runner, "_deep_validate_candidate_directory") as validator, \
             mock.patch.object(runner, "_authorization_registry") as registry, \
             mock.patch.object(runner, "http_request") as request:
            with self.assertRaisesRegex(runner.Macro4RedisplayError, "already exists"):
                runner.run_macro4_redisplay_once(
                    self.result_dir,
                    "http://device",
                    authorization_confirmation=runner.REQUIRED_AUTHORIZATION_CONFIRMATION,
                    confirm_j2_powered_supervised=True,
                    confirm_supply_and_temperature_normal=True,
                    confirm_visual_quality_concern_redisplay=True,
                )
        validator.assert_not_called()
        registry.assert_not_called()
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
