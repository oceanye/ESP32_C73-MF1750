from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from host.epd_frame import FRAME_BYTES, controller_stream, fnv1a, generate_fixture
from tools import g1_s1_rc2g_map_baseline_once as runner


def _mapping_text(mapping) -> str:
    return ",".join(
        str(int(value))
        for value in (
            mapping.source_half,
            mapping.flip_x,
            mapping.flip_y,
            mapping.nibble_swap,
        )
    )


def _version_body(*, build_tag: str = runner.EXPECTED_BUILD_TAG) -> str:
    return "\n".join(
        (
            build_tag,
            "Panel: 1024x600",
            f"Driver API: {runner.EXPECTED_DRIVER_API}",
            f"Frame bytes: {FRAME_BYTES}",
            "PSRAM bytes: 8388608",
            "Free PSRAM: 7900000",
            f"Refresh SPI Hz: {runner.EXPECTED_REFRESH_SPI_HZ}",
            f"CS1 Mapping: {_mapping_text(runner.FIXED_CONTROLLER_MAPPINGS[0])}",
            f"CS2 Mapping: {_mapping_text(runner.FIXED_CONTROLLER_MAPPINGS[1])}",
        )
    )


def _job(*, total_ms: int = 34_169) -> dict[str, object]:
    started = 1_005
    return {
        "job_id": runner.EXPECTED_TARGET_JOB_ID,
        "action": "uploaded_frame",
        "state": "completed",
        "result": True,
        "queued_at_ms": 1_000,
        "started_at_ms": started,
        "finished_at_ms": started + total_ms,
        "frame_fnv1a": runner.EXPECTED_FRAME_FNV1A,
    }


def _add_busy_trace(diagnostic: dict[str, object], *, final_busy: int = 0) -> None:
    def stage(
        wait_ms: int,
        *,
        gate: int = 1,
        before: int = 1,
        entry: int = 0,
        pre_idle: bool = True,
        assertion: bool = True,
    ) -> dict[str, object]:
        return {
            "gate_entry_level": gate,
            "pre_command_level": before,
            "wait_entry_level": entry,
            "wait_exit_level": 1,
            "pre_command_idle_ok": pre_idle,
            "assertion_after_idle": assertion,
            "pre_command_wait_ms": 0,
            "wait_ms": wait_ms,
            "assertion_latency_ms": 0,
        }

    diagnostic.update(
        {
            "pre_command_idle_failure": False,
            "pre_command_busy_stage": "none",
            "busy_trace_schema_version": 1,
            "busy_trace": {
                "idle_level": 1,
                "pre_command_idle_timeout_ms": 3_000,
                "assert_grace_ms": 250,
                "reset": stage(
                    5,
                    gate=255,
                    before=255,
                    entry=0,
                    pre_idle=False,
                    assertion=False,
                ),
                "pon": stage(int(diagnostic["pon_ms"])),
                "drf": stage(int(diagnostic["drf_ms"])),
                "pof": stage(int(diagnostic["pof_ms"])),
                "post_psr": stage(
                    int(diagnostic["post_psr_ms"]),
                    entry=1,
                    assertion=False,
                ),
                "safe_finish": {
                    "busy_before_pins_low": 1,
                    "busy_after_pins_low": final_busy,
                    "busy_after_5ms": final_busy,
                },
                "final_gpio": {
                    "busy": final_busy,
                    "rst": 0,
                    "cs": 0,
                    "cs2": 0,
                },
            },
        }
    )


def _diagnostic(
    frame: bytes,
    job: dict[str, object],
    *,
    final_busy: int = 0,
    timing: dict[str, int] | None = None,
) -> dict[str, object]:
    values = {
        "total_ms": 34_169,
        "cs1_upload_ms": 2_440,
        "cs2_upload_ms": 2_440,
        "pon_ms": 181,
        "drf_ms": 21_690,
        "pof_ms": 140,
        "post_psr_ms": 5,
    }
    if timing is not None:
        values.update(timing)
    diagnostic: dict[str, object] = {
        "schema_version": 2,
        "firmware_build_tag": runner.EXPECTED_BUILD_TAG,
        "driver_api_version": runner.EXPECTED_DRIVER_API,
        "job_id": runner.EXPECTED_TARGET_JOB_ID,
        "job_action": "uploaded_frame",
        "job_state": "completed",
        "job_result": True,
        "job_operation_id": runner.EXPECTED_TARGET_OPERATION_ID,
        "job_queued_at_ms": job["queued_at_ms"],
        "job_started_at_ms": job["started_at_ms"],
        "job_finished_at_ms": job["finished_at_ms"],
        "operation_id": runner.EXPECTED_TARGET_OPERATION_ID,
        "valid": True,
        "running": False,
        "sequence_ok": True,
        "wait_timeout": False,
        "busy_assertion_missing": False,
        "busy_assert_grace_ms": 250,
        "busy_missing_stage": "none",
        "mapping_applied": True,
        "pon_busy_seen": True,
        "drf_busy_seen": True,
        "pof_busy_seen": True,
        "post_psr_busy_seen": False,
        "spi_hz": runner.EXPECTED_REFRESH_SPI_HZ,
        "input_fnv1a": fnv1a(frame),
        "cs1_dtm_fnv1a": fnv1a(
            controller_stream(frame, runner.FIXED_CONTROLLER_MAPPINGS[0])
        ),
        "cs2_dtm_fnv1a": fnv1a(
            controller_stream(frame, runner.FIXED_CONTROLLER_MAPPINGS[1])
        ),
        **values,
        "last_wait_ms": values["post_psr_ms"],
        "last_wait_stage": "post-display PSR",
        "timeout_stage": "none",
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
    _add_busy_trace(diagnostic, final_busy=final_busy)
    return diagnostic


def _fresh_job() -> dict[str, object]:
    return {
        "job_id": 0,
        "action": "none",
        "state": "idle",
        "result": None,
        "queued_at_ms": 0,
        "started_at_ms": 0,
        "finished_at_ms": 0,
        "frame_fnv1a": 0,
    }


def _responses(
    *,
    final_busy: int = 0,
    timing: dict[str, int] | None = None,
) -> dict[str, list[tuple[int, str] | Exception]]:
    frame = generate_fixture(runner.FIXTURE_NAME)
    total_ms = 34_169 if timing is None else timing.get("total_ms", 34_169)
    target_job = _job(total_ms=total_ms)
    target_diagnostic = _diagnostic(
        frame, target_job, final_busy=final_busy, timing=timing
    )
    enqueue = {
        "ok": True,
        "bytes": len(frame),
        "fnv1a": fnv1a(frame),
        "free_psram": 7_800_000,
        "job_id": runner.EXPECTED_TARGET_JOB_ID,
    }
    fresh_gpio = {"busy": 0, "rst": 0, "cs": 0, "cs2": 0}
    final_gpio = {"busy": final_busy, "rst": 0, "cs": 0, "cs2": 0}
    no_report = {
        "schema_version": 2,
        "valid": False,
        "error": "no_completed_job_report",
    }
    return {
        "/api/version": [
            (200, _version_body()),
            (200, _version_body()),
        ],
        "/api/job": [
            (200, json.dumps(_fresh_job())),
            (200, json.dumps(target_job)),
            (200, json.dumps(target_job)),
            (200, json.dumps(target_job)),
        ],
        "/api/diagnostic/report": [
            (200, json.dumps(no_report)),
            (200, json.dumps(target_diagnostic)),
            (200, json.dumps(target_diagnostic)),
            (200, json.dumps(target_diagnostic)),
        ],
        "/api/diagnostic/status": [
            (200, json.dumps(fresh_gpio)),
            (200, json.dumps(final_gpio)),
            (200, json.dumps(final_gpio)),
        ],
        "/api/frame": [(202, json.dumps(enqueue))],
    }


class ScriptedRequester:
    def __init__(
        self,
        responses: dict[str, list[tuple[int, str] | Exception]],
        *,
        before_first_call=None,
    ) -> None:
        self.responses = {key: list(values) for key, values in responses.items()}
        self.calls: list[tuple[str, str]] = []
        self.before_first_call = before_first_call

    def __call__(
        self,
        _base_url: str,
        endpoint: str,
        *,
        method: str,
        data: bytes | None,
        timeout: float,
    ) -> tuple[int, str]:
        del data, timeout
        if not self.calls and self.before_first_call is not None:
            self.before_first_call()
        self.calls.append((method, endpoint))
        if endpoint not in self.responses or not self.responses[endpoint]:
            raise AssertionError(f"unexpected request: {method} {endpoint}")
        response = self.responses[endpoint].pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class TickClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        self.value += 0.01
        return self.value


class Rc2gMapBaselineOnceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.registry = self.root / "registry"
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
            "confirm_rc2g_flashed_fresh_boot": True,
            "confirm_j2_powered_supervised": True,
            "confirm_supply_and_temperature_normal": True,
            "confirm_single_visible_refresh": True,
            "sleeper": lambda _seconds: None,
            "clock": TickClock(),
        }
        arguments.update(overrides)
        patches = [
            mock.patch.object(runner, "_authorization_registry", return_value=active_registry),
            mock.patch.object(runner, "http_request", side_effect=requester),
        ]
        with patches[0], patches[1]:
            if patch_refresh is None:
                return runner.run_rc2g_map_baseline_once(
                    self.result_dir if result_dir is None else result_dir,
                    "http://device",
                    **arguments,
                )
            with mock.patch.object(
                runner, "perform_refresh", side_effect=patch_refresh
            ):
                return runner.run_rc2g_map_baseline_once(
                    self.result_dir if result_dir is None else result_dir,
                    "http://device",
                    **arguments,
                )

    def test_frozen_map_dtm_build_and_authorization_identities(self) -> None:
        snapshot = runner._validate_fixture_snapshot()
        self.assertEqual(snapshot.frame_sha256, runner.EXPECTED_FRAME_SHA256)
        self.assertEqual(fnv1a(snapshot.frame), 0x9D04142D)
        self.assertEqual(
            (runner.EXPECTED_CS1_DTM_FNV1A, runner.EXPECTED_CS2_DTM_FNV1A),
            (0xF26832DD, 0xFE199FF5),
        )
        self.assertIn("BUSYEDGE", runner.EXPECTED_BUILD_TAG)
        self.assertEqual(
            runner.AUTHORIZATION_CONFIRMATION_SHA256,
            "3b05288f37768eb8dda4dc9fb119d13451b9e10c6ee737fef0e544fa670ae535",
        )
        self.assertEqual(
            runner.ACTION_IDENTITY_SHA256,
            "8f83d951986f403a5e531558c1a663deae99988915c7bd4e367b00bf59e8489d",
        )
        self.assertEqual(
            runner.AUTHORIZATION_CONFIRMATION_SHA256,
            hashlib.sha256(
                runner.REQUIRED_AUTHORIZATION_CONFIRMATION.encode("ascii")
            ).hexdigest(),
        )
        self.assertEqual(
            runner.ACTION_IDENTITY_SHA256,
            hashlib.sha256(runner._canonical_json(runner.ACTION_IDENTITY)).hexdigest(),
        )

    def test_cli_requires_all_confirmations_and_exposes_no_retry_or_override(self) -> None:
        parsed = runner.parse_args(
            [
                "--result-dir",
                str(self.result_dir),
                "--url",
                "http://device",
                "--confirm",
                runner.REQUIRED_AUTHORIZATION_CONFIRMATION,
                "--confirm-rc2g-flashed-fresh-boot",
                "--confirm-j2-powered-supervised",
                "--confirm-supply-and-temperature-normal",
                "--confirm-single-visible-refresh",
            ]
        )
        self.assertTrue(parsed.confirm_rc2g_flashed_fresh_boot)
        self.assertTrue(parsed.confirm_single_visible_refresh)
        parameters = inspect.signature(runner.run_rc2g_map_baseline_once).parameters
        for forbidden in ("requester", "registry", "frame", "retry", "recovery", "force"):
            self.assertNotIn(forbidden, parameters)
        source = inspect.getsource(runner.parse_args)
        self.assertNotIn("--retry", source)
        self.assertNotIn("--recovery", source)
        self.assertNotIn("--force", source)

    def test_wrong_or_missing_confirmation_is_preclaim_and_zero_network(self) -> None:
        for field in (
            "confirm_rc2g_flashed_fresh_boot",
            "confirm_j2_powered_supervised",
            "confirm_supply_and_temperature_normal",
            "confirm_single_visible_refresh",
        ):
            with self.subTest(field=field), mock.patch.object(
                runner, "_authorization_registry"
            ) as registry, mock.patch.object(runner, "http_request") as request:
                arguments = {
                    "authorization_confirmation": runner.REQUIRED_AUTHORIZATION_CONFIRMATION,
                    "confirm_rc2g_flashed_fresh_boot": True,
                    "confirm_j2_powered_supervised": True,
                    "confirm_supply_and_temperature_normal": True,
                    "confirm_single_visible_refresh": True,
                }
                arguments[field] = False
                with self.assertRaisesRegex(runner.Rc2gMapBaselineError, "all four"):
                    runner.run_rc2g_map_baseline_once(
                        self.result_dir, "http://device", **arguments
                    )
            registry.assert_not_called()
            request.assert_not_called()
        with mock.patch.object(runner, "_authorization_registry") as registry, \
             mock.patch.object(runner, "http_request") as request:
            with self.assertRaisesRegex(runner.Rc2gMapBaselineError, "exact RC2G"):
                runner.run_rc2g_map_baseline_once(
                    self.result_dir,
                    "http://device",
                    authorization_confirmation="yes",
                    confirm_rc2g_flashed_fresh_boot=True,
                    confirm_j2_powered_supervised=True,
                    confirm_supply_and_temperature_normal=True,
                    confirm_single_visible_refresh=True,
                )
        registry.assert_not_called()
        request.assert_not_called()

    def test_claim_is_permanent_before_first_network_request(self) -> None:
        def assert_claim_exists() -> None:
            self.assertTrue((self.registry / runner.FIXED_ACTION_ID).is_file())

        scripted = ScriptedRequester(
            _responses(), before_first_call=assert_claim_exists
        )
        result = self._run(scripted)
        self.assertTrue(result["authorization_consumed_permanently"])

    def test_success_proves_fresh_boot_then_one_nominal_map_job1_operation1(self) -> None:
        scripted = ScriptedRequester(_responses())
        result = self._run(scripted)
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
        self.assertEqual(
            [call for call in scripted.calls if call[0] == "POST"],
            [("POST", "/api/frame")],
        )
        self.assertEqual(result["fresh_boot_preflight"]["job_raw"]["job_id"], 0)
        completed = result["completed_map_evidence"]
        self.assertEqual(completed["job_raw"]["job_id"], 1)
        self.assertEqual(completed["diagnostic_raw"]["operation_id"], 1)
        self.assertEqual(completed["nominal_timing"]["pon_ms"], 181)
        self.assertEqual(completed["nominal_timing"]["drf_ms"], 21_690)
        self.assertTrue(completed["busy_trace"]["command_edge_contract_verified"])
        self.assertEqual(result["request_audit"]["post_issued_count"], 1)
        self.assertEqual(
            result["outcome"], "protocol_verified_manual_observation_required"
        )
        recorded = json.loads(
            (self.result_dir / runner.RESULT_FILENAME).read_text("utf-8")
        )
        self.assertEqual(recorded, result)

    def test_busy_after_rst_low_is_informational_for_both_levels(self) -> None:
        for busy in (0, 1):
            with self.subTest(busy=busy):
                registry = self.root / f"registry-busy-{busy}"
                result_dir = self.root / f"result-busy-{busy}"
                result = self._run(
                    ScriptedRequester(_responses(final_busy=busy)),
                    result_dir=result_dir,
                    registry=registry,
                )
                evidence = result["completed_map_evidence"]
                self.assertEqual(evidence["gpio_status_raw"]["busy"], busy)
                self.assertTrue(evidence["busy_after_rst_low_is_informational"])
                self.assertEqual(
                    {key: evidence["gpio_status_raw"][key] for key in ("rst", "cs", "cs2")},
                    runner.EXPECTED_PANEL_OUTPUTS_LOW,
                )

    def test_nonfresh_job_or_completed_diagnostic_is_unknown_with_zero_posts(self) -> None:
        for label in ("job", "diagnostic"):
            with self.subTest(label=label):
                responses = _responses()
                if label == "job":
                    stale = _fresh_job()
                    stale["job_id"] = 9
                    responses["/api/job"][0] = (200, json.dumps(stale))
                else:
                    responses["/api/diagnostic/report"][0] = responses[
                        "/api/diagnostic/report"
                    ][1]
                scripted = ScriptedRequester(responses)
                registry = self.root / f"registry-stale-{label}"
                result_dir = self.root / f"result-stale-{label}"
                with self.assertRaises(runner.Rc2gMapBaselineUnknown):
                    self._run(scripted, result_dir=result_dir, registry=registry)
                self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 0)
                recorded = json.loads(
                    (result_dir / runner.RESULT_FILENAME).read_text("utf-8")
                )
                self.assertEqual(recorded["outcome"], "unknown_do_not_retry")
                self.assertEqual(recorded["request_audit"]["post_issued_count"], 0)
                self.assertIsNotNone(recorded["best_effort_postclaim_evidence"])

    def test_wrong_rc2g_build_is_unknown_before_post(self) -> None:
        responses = _responses()
        responses["/api/version"][0] = (200, _version_body(build_tag="WRONG"))
        scripted = ScriptedRequester(responses)
        with self.assertRaises(runner.Rc2gMapBaselineUnknown):
            self._run(scripted)
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 0)

    def test_tens_of_seconds_pon_and_other_nonnominal_timings_fail_closed(self) -> None:
        cases = {
            "pon": {
                "total_ms": 70_000,
                "pon_ms": 37_110,
                "drf_ms": 21_690,
            },
            "drf": {"total_ms": 52_000, "drf_ms": 39_621},
            "pof": {"total_ms": 45_000, "pof_ms": 10_000},
        }
        for label, timing in cases.items():
            with self.subTest(label=label):
                scripted = ScriptedRequester(_responses(timing=timing))
                registry = self.root / f"registry-timing-{label}"
                result_dir = self.root / f"result-timing-{label}"
                with self.assertRaises(runner.Rc2gMapBaselineUnknown):
                    self._run(scripted, result_dir=result_dir, registry=registry)
                self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
                recorded = json.loads(
                    (result_dir / runner.RESULT_FILENAME).read_text("utf-8")
                )
                self.assertIsNotNone(recorded["network_report"])
                self.assertIsNotNone(recorded["post_refresh_diagnostic_raw"])
                self.assertIsNotNone(recorded["post_refresh_gpio_status_raw"])

    def test_missing_busy_edge_is_unknown_after_the_single_post(self) -> None:
        responses = _responses()
        diagnostic = json.loads(responses["/api/diagnostic/report"][1][1])
        diagnostic["busy_trace"]["pon"]["assertion_after_idle"] = False
        responses["/api/diagnostic/report"][1] = (200, json.dumps(diagnostic))
        responses["/api/diagnostic/report"][2] = (200, json.dumps(diagnostic))
        scripted = ScriptedRequester(responses)
        with self.assertRaises(runner.Rc2gMapBaselineUnknown):
            self._run(scripted)
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
        recorded = json.loads(
            (self.result_dir / runner.RESULT_FILENAME).read_text("utf-8")
        )
        self.assertIsNotNone(recorded["best_effort_postclaim_evidence"])

    def test_post_gpio_output_failure_preserves_report_and_raw_gpio(self) -> None:
        responses = _responses()
        raw = {"busy": 0, "rst": 0, "cs": 1, "cs2": 0}
        responses["/api/diagnostic/status"][1] = (200, json.dumps(raw))
        scripted = ScriptedRequester(responses)
        with self.assertRaises(runner.Rc2gMapBaselineUnknown):
            self._run(scripted)
        recorded = json.loads(
            (self.result_dir / runner.RESULT_FILENAME).read_text("utf-8")
        )
        self.assertEqual(recorded["post_refresh_gpio_status_raw"], raw)
        self.assertIsNotNone(recorded["network_report"])
        self.assertIsNotNone(recorded["post_refresh_diagnostic_raw"])
        self.assertEqual(recorded["request_audit"]["post_issued_count"], 1)

    def test_post_transport_exception_is_unknown_and_claim_cannot_be_reused(self) -> None:
        responses = _responses()
        responses["/api/frame"] = [OSError("simulated transport loss")]
        scripted = ScriptedRequester(responses)
        with self.assertRaises(runner.Rc2gMapBaselineUnknown):
            self._run(scripted)
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
        recorded = json.loads(
            (self.result_dir / runner.RESULT_FILENAME).read_text("utf-8")
        )
        self.assertEqual(recorded["request_audit"]["post_issued_count"], 1)
        self.assertIsNotNone(recorded["best_effort_postclaim_evidence"])
        calls = list(scripted.calls)
        with self.assertRaisesRegex(runner.Rc2gMapBaselineError, "already permanently"):
            self._run(scripted, result_dir=self.root / "second")
        self.assertEqual(scripted.calls, calls)

    def test_audited_requester_blocks_second_post_before_issuing_it(self) -> None:
        scripted = ScriptedRequester(_responses())

        def malicious_refresh(base_url, frame, *, requester, **_kwargs):
            requester(
                base_url, "/api/frame", method="POST", data=frame, timeout=20.0
            )
            requester(
                base_url, "/api/frame", method="POST", data=frame, timeout=20.0
            )
            raise AssertionError("unreachable")

        with self.assertRaises(runner.Rc2gMapBaselineUnknown):
            self._run(scripted, patch_refresh=malicious_refresh)
        self.assertEqual(scripted.calls.count(("POST", "/api/frame")), 1)
        recorded = json.loads(
            (self.result_dir / runner.RESULT_FILENAME).read_text("utf-8")
        )
        self.assertEqual(recorded["request_audit"]["post_attempt_count"], 2)
        self.assertEqual(recorded["request_audit"]["post_issued_count"], 1)

    def test_existing_result_directory_is_preclaim_and_zero_network(self) -> None:
        self.result_dir.mkdir()
        with mock.patch.object(runner, "_authorization_registry") as registry, \
             mock.patch.object(runner, "http_request") as request:
            with self.assertRaisesRegex(runner.Rc2gMapBaselineError, "already exists"):
                runner.run_rc2g_map_baseline_once(
                    self.result_dir,
                    "http://device",
                    authorization_confirmation=runner.REQUIRED_AUTHORIZATION_CONFIRMATION,
                    confirm_rc2g_flashed_fresh_boot=True,
                    confirm_j2_powered_supervised=True,
                    confirm_supply_and_temperature_normal=True,
                    confirm_single_visible_refresh=True,
                )
        registry.assert_not_called()
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
