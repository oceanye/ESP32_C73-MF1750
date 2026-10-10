from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import mf1750_n7_spi_sweep_campaign as campaign
from tools import mf1750_n7_spi_sweep_once as runner


def fake_firmware() -> bytes:
    return b"synthetic-n7\0" + campaign.FIRMWARE_BUILD_TAG.encode("ascii") + b"\0firmware"


def version_body() -> str:
    return "\n".join(
        (
            campaign.FIRMWARE_BUILD_TAG,
            "Panel: 1024x600",
            f"Driver API: {campaign.DRIVER_API_VERSION}",
            f"Frame bytes: {campaign.FRAME_BYTES}",
            "Refresh SPI Hz: 1000000",
            "N7 Sweep SPI Hz: 1000000,2000000,4000000,8000000,10000000",
            "CS1 Mapping: 0,0,0,0",
            "CS2 Mapping: 1,0,0,0",
            "PSRAM bytes: 8388608",
            "Free PSRAM: 7900000",
        )
    )


def upload_times(spi_hz: int) -> tuple[int, int]:
    raw_half_ms = campaign.FRAME_BYTES // 2 * 8_000 / spi_hz
    first = math.ceil(raw_half_ms + 25)
    return first, first + 2


def job(job_id: int, state: str, *, spi_hz: int, result: bool | None) -> dict[str, object]:
    cs1_ms, cs2_ms = upload_times(spi_hz)
    total_ms = cs1_ms + cs2_ms + 100 + 21_700 + 100 + 100 + 7_000
    started = 1_010 + (job_id - 1) * 40_000
    queued = started - 10
    finished = started + total_ms + 50 if state == "completed" else 0
    return {
        "job_id": job_id,
        "action": campaign.JOB_ACTION,
        "state": state,
        "result": result,
        "queued_at_ms": queued,
        "started_at_ms": started if state != "queued" else 0,
        "finished_at_ms": finished,
        "frame_fnv1a": campaign.EXPECTED_FULL_FNV1A,
    }


def fresh_job() -> dict[str, object]:
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


def busy_stage(
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


def diagnostic(spi_hz: int, target_job: dict[str, object], operation_id: int) -> dict[str, object]:
    cs1_ms, cs2_ms = upload_times(spi_hz)
    total_ms = cs1_ms + cs2_ms + 100 + 21_700 + 100 + 100 + 7_000
    value: dict[str, object] = {
        "schema_version": 2,
        "firmware_build_tag": campaign.FIRMWARE_BUILD_TAG,
        "driver_api_version": campaign.DRIVER_API_VERSION,
        "job_id": target_job["job_id"],
        "job_action": campaign.JOB_ACTION,
        "job_state": "completed",
        "job_result": True,
        "job_operation_id": operation_id,
        "job_queued_at_ms": target_job["queued_at_ms"],
        "job_started_at_ms": target_job["started_at_ms"],
        "job_finished_at_ms": target_job["finished_at_ms"],
        "operation_id": operation_id,
        "valid": True,
        "running": False,
        "sequence_ok": True,
        "wait_timeout": False,
        "busy_assertion_missing": False,
        "busy_assert_grace_ms": 250,
        "busy_missing_stage": "none",
        "pre_command_idle_failure": False,
        "pre_command_busy_stage": "none",
        "mapping_applied": True,
        "pon_busy_seen": True,
        "drf_busy_seen": True,
        "pof_busy_seen": True,
        "post_psr_busy_seen": False,
        "spi_hz": spi_hz,
        "input_fnv1a": campaign.EXPECTED_FULL_FNV1A,
        "cs1_dtm_fnv1a": campaign.EXPECTED_CS1_FNV1A,
        "cs2_dtm_fnv1a": campaign.EXPECTED_CS2_FNV1A,
        "total_ms": total_ms,
        "cs1_upload_ms": cs1_ms,
        "cs2_upload_ms": cs2_ms,
        "pon_ms": 100,
        "drf_ms": 21_700,
        "pof_ms": 100,
        "post_psr_ms": 100,
        "last_wait_ms": 100,
        "last_wait_stage": "post-display PSR",
        "timeout_stage": "none",
        "busy_trace_schema_version": 1,
        "busy_trace": {
            "idle_level": 1,
            "pre_command_idle_timeout_ms": 3_000,
            "assert_grace_ms": 250,
            "reset": busy_stage(
                5, gate=255, before=255, pre_idle=False, assertion=False
            ),
            "pon": busy_stage(100),
            "drf": busy_stage(21_700),
            "pof": busy_stage(100),
            "post_psr": busy_stage(100, entry=1, assertion=False),
            "safe_finish": {
                "busy_before_pins_low": 1,
                "busy_after_pins_low": 0,
                "busy_after_5ms": 0,
            },
            "final_gpio": {"busy": 0, "rst": 0, "cs": 0, "cs2": 0},
        },
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
    return value


def serial_log(spi_hz: int, job_id: int) -> bytes:
    cs1_ms, cs2_ms = upload_times(spi_hz)
    return (
        f"Running EPD job {job_id} action 1 ({campaign.JOB_ACTION})\n"
        f"MAP_ORIENT_V1 frame FNV-1a: {campaign.EXPECTED_FULL_FNV1A} "
        f"(expected {campaign.EXPECTED_FULL_FNV1A}), counts=PASS\n"
        f"EPD full frame CS1 upload done after {cs1_ms} ms, "
        f"DTM FNV-1a={campaign.EXPECTED_CS1_FNV1A}\n"
        f"EPD full frame CS2 upload done after {cs2_ms} ms, "
        f"DTM FNV-1a={campaign.EXPECTED_CS2_FNV1A}\n"
        "EPD idle: PON after 100 ms, busy_seen=1\n"
        "EPD idle: DRF after 21700 ms, busy_seen=1\n"
        "EPD idle: POF after 100 ms, busy_seen=1\n"
        "EPD idle: post-display PSR after 100 ms, busy_seen=0\n"
        "EPD full-frame cascade refresh: PASS\n"
        f"EPD job {job_id} finished: state=completed result_known=1 result=1\n"
    ).encode("utf-8")


class ScriptedRequester:
    def __init__(self, responses: list[tuple[str, str, tuple[int, str] | Exception]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def __call__(
        self,
        _base_url: str,
        endpoint: str,
        *,
        method: str,
        data: bytes | None,
        timeout: float,
    ) -> tuple[int, str]:
        del timeout
        self.calls.append((method, endpoint))
        if not self.responses:
            raise AssertionError(f"unexpected request {method} {endpoint}")
        expected_method, expected_endpoint, response = self.responses.pop(0)
        if (method, endpoint) != (expected_method, expected_endpoint):
            raise AssertionError(
                f"expected {expected_method} {expected_endpoint}; got {method} {endpoint}"
            )
        if method == "POST" and data not in (None, b""):
            raise AssertionError("fixed N7 POST must have no body")
        if isinstance(response, Exception):
            raise response
        return response


def responses_for_first(spi_hz: int = 1_000_000) -> list[tuple[str, str, tuple[int, str] | Exception]]:
    endpoint = campaign.ROUTES[spi_hz]
    queued = job(1, "queued", spi_hz=spi_hz, result=None)
    completed = job(1, "completed", spi_hz=spi_hz, result=True)
    report = diagnostic(spi_hz, completed, 1)
    gpio = {"busy": 0, "rst": 0, "cs": 0, "cs2": 0}
    no_report = {"schema_version": 2, "valid": False, "error": "no_completed_job_report"}
    return [
        ("GET", "/api/version", (200, version_body())),
        ("GET", "/api/job", (200, json.dumps(fresh_job()))),
        ("GET", "/api/diagnostic/report", (200, json.dumps(no_report))),
        ("GET", "/api/diagnostic/status", (200, json.dumps(gpio))),
        ("POST", endpoint, (202, json.dumps({"ok": True, "job": queued}))),
        ("GET", "/api/job", (200, json.dumps(completed))),
        ("GET", "/api/diagnostic/report", (200, json.dumps(report))),
        ("GET", "/api/diagnostic/status", (200, json.dumps(gpio))),
    ]


def responses_for_next(
    spi_hz: int, previous_live: dict[str, object]
) -> list[tuple[str, str, tuple[int, str] | Exception]]:
    previous_job = copy.deepcopy(previous_live["target_job"])
    previous_diagnostic = copy.deepcopy(previous_live["target_diagnostic"])
    next_job_id = int(previous_job["job_id"]) + 1
    next_operation_id = int(previous_diagnostic["operation_id"]) + 1
    queued = job(next_job_id, "queued", spi_hz=spi_hz, result=None)
    completed = job(next_job_id, "completed", spi_hz=spi_hz, result=True)
    report = diagnostic(spi_hz, completed, next_operation_id)
    gpio = {"busy": 1, "rst": 0, "cs": 0, "cs2": 0}
    return [
        ("GET", "/api/version", (200, version_body())),
        ("GET", "/api/job", (200, json.dumps(previous_job))),
        ("GET", "/api/diagnostic/report", (200, json.dumps(previous_diagnostic))),
        ("GET", "/api/diagnostic/status", (200, json.dumps(gpio))),
        (
            "POST",
            campaign.ROUTES[spi_hz],
            (202, json.dumps({"ok": True, "job": queued})),
        ),
        ("GET", "/api/job", (200, json.dumps(completed))),
        ("GET", "/api/diagnostic/report", (200, json.dumps(report))),
        ("GET", "/api/diagnostic/status", (200, json.dumps(gpio))),
    ]


class N7SweepOnceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        firmware = fake_firmware()
        self.bytes_patch = mock.patch.object(
            campaign, "FIRMWARE_EXPECTED_BYTES", len(firmware)
        )
        self.sha_patch = mock.patch.object(
            campaign, "FIRMWARE_EXPECTED_SHA256", campaign.sha256(firmware)
        )
        self.bytes_patch.start()
        self.sha_patch.start()
        self.campaign_dir = self.root / "campaign"
        campaign.write_campaign_directory(
            self.campaign_dir,
            firmware,
            created_at_utc="2026-08-07T12:00:00Z",
        )
        self.claims = self.root / "claims"
        self.registry_patch = mock.patch.object(
            runner, "DEFAULT_AUTHORIZATION_REGISTRY", self.claims
        )
        self.registry_patch.start()

    def tearDown(self) -> None:
        self.registry_patch.stop()
        self.sha_patch.stop()
        self.bytes_patch.stop()
        self.temporary.cleanup()

    def test_public_legacy_live_api_is_hard_blocked_before_claim_or_network(self) -> None:
        with mock.patch.object(
            runner,
            "build_action_contract",
            side_effect=AssertionError("campaign processing is forbidden"),
        ), mock.patch.object(
            runner,
            "_claim_action",
            side_effect=AssertionError("claim creation is forbidden"),
        ), mock.patch.object(
            runner.frame_tool,
            "http_request",
            side_effect=AssertionError("network is forbidden"),
        ):
            with self.assertRaisesRegex(
                runner.N7SweepError, "legacy N7 live execution is disabled"
            ):
                runner.run_n7_sweep_once()
        self.assertFalse(self.claims.exists())

    def run_first(
        self,
        result_name: str = "run-1mhz",
        *,
        scripted: ScriptedRequester | None = None,
    ) -> tuple[dict, ScriptedRequester, Path]:
        contract = runner.build_action_contract(self.campaign_dir, 1_000_000)
        requester = scripted or ScriptedRequester(responses_for_first())
        result_dir = self.root / result_name
        result = runner._run_n7_sweep_once_legacy_test_only(
            self.campaign_dir,
            1_000_000,
            result_dir,
            base_url="http://synthetic-device",
            authorized_campaign_sha256=contract.snapshot.campaign_file_sha256,
            confirmation=contract.authorization_confirmation,
            confirm_n7_firmware_flashed=True,
            confirm_panel_power_off_at_least_10s=True,
            confirm_supply_and_temperature_normal=True,
            confirm_scope_capture_armed=True,
            confirm_single_visible_action=True,
            requester=requester,
            sleeper=lambda _seconds: None,
        )
        return dict(result), requester, result_dir

    def finalize_first(self, result_dir: Path, *, visual_pass: bool = True) -> dict:
        serial_path = self.root / f"serial-{result_dir.name}.log"
        scope_path = self.root / f"scope-{result_dir.name}.csv"
        serial_path.write_bytes(serial_log(1_000_000, 1))
        scope_path.write_bytes(b"synthetic,scope,1mhz\n")
        result = runner.finalize_n7_sweep_result(
            self.campaign_dir,
            result_dir / runner.LIVE_RESULT_FILENAME,
            serial_path,
            scope_path,
            measured_sclk_hz=1_000_000.0,
            power_off_s=12.0,
            supply_voltage_v=3.3,
            current_limit_a=1.0,
            peak_current_a=0.2,
            max_temperature_c=30.0,
            visual_pass=visual_pass,
            cv_pass=True,
            thermal_pass=True,
            acoustic_pass=True,
            notes="synthetic evidence",
        )
        return dict(result)

    def test_success_claims_once_posts_once_and_remains_pending(self) -> None:
        result, requester, result_dir = self.run_first()

        self.assertEqual(result["outcome"], "protocol_pass_pending_adjudication")
        self.assertFalse(result["hardware_tested"])
        self.assertEqual(
            requester.calls.count(("POST", campaign.ROUTES[1_000_000])), 1
        )
        self.assertEqual(len(list(self.claims.iterdir())), 1)
        self.assertTrue((result_dir / runner.ATTEMPT_LOCK_FILENAME).is_file())
        self.assertTrue((result_dir / runner.LIVE_RESULT_FILENAME).is_file())
        self.assertFalse((result_dir / runner.FINAL_RESULT_FILENAME).exists())

    def test_same_action_replay_is_rejected_before_network(self) -> None:
        self.run_first()
        contract = runner.build_action_contract(self.campaign_dir, 1_000_000)
        replay = ScriptedRequester(responses_for_first())

        with self.assertRaisesRegex(runner.N7SweepUnknown, "already permanently consumed"):
            runner._run_n7_sweep_once_legacy_test_only(
                self.campaign_dir,
                1_000_000,
                self.root / "replay",
                base_url="http://synthetic-device",
                authorized_campaign_sha256=contract.snapshot.campaign_file_sha256,
                confirmation=contract.authorization_confirmation,
                confirm_n7_firmware_flashed=True,
                confirm_panel_power_off_at_least_10s=True,
                confirm_supply_and_temperature_normal=True,
                confirm_scope_capture_armed=True,
                confirm_single_visible_action=True,
                requester=replay,
            )
        self.assertEqual(replay.calls, [])

    def test_postclaim_failure_is_unknown_and_never_retried(self) -> None:
        scripted_responses = responses_for_first()
        scripted_responses[5] = (
            "GET",
            "/api/job",
            OSError("synthetic link loss after POST"),
        )
        scripted = ScriptedRequester(scripted_responses)

        with self.assertRaisesRegex(runner.N7SweepUnknown, "link loss"):
            self.run_first("unknown", scripted=scripted)

        self.assertEqual(
            scripted.calls.count(("POST", campaign.ROUTES[1_000_000])), 1
        )
        result = json.loads(
            (self.root / "unknown" / runner.LIVE_RESULT_FILENAME).read_text(encoding="utf-8")
        )
        self.assertEqual(result["outcome"], "unknown_do_not_retry")
        self.assertFalse(result["automatic_retry_authorized"])
        self.assertFalse(result["automatic_recovery_authorized"])

    def test_bad_confirmation_and_arbitrary_frequency_fail_before_claim(self) -> None:
        contract = runner.build_action_contract(self.campaign_dir, 1_000_000)
        with self.assertRaisesRegex(runner.N7SweepError, "confirmation differs"):
            runner._run_n7_sweep_once_legacy_test_only(
                self.campaign_dir,
                1_000_000,
                self.root / "not-claimed",
                base_url="http://synthetic-device",
                authorized_campaign_sha256=contract.snapshot.campaign_file_sha256,
                confirmation="not-the-exact-confirmation",
            )
        with self.assertRaisesRegex(runner.N7SweepError, "1/2/4/8/10"):
            runner.build_action_contract(self.campaign_dir, 3_000_000)
        self.assertFalse(self.claims.exists())

    def test_higher_frequency_requires_previous_final_pass(self) -> None:
        with self.assertRaisesRegex(runner.N7SweepError, "previous PASS"):
            runner.build_action_contract(self.campaign_dir, 2_000_000)
        self.assertFalse(self.claims.exists())

    def test_offline_adjudication_pass_enables_sha_bound_next_action(self) -> None:
        _, _, result_dir = self.run_first()
        final = self.finalize_first(result_dir)
        final_path = result_dir / runner.FINAL_RESULT_FILENAME
        next_contract = runner.build_action_contract(
            self.campaign_dir,
            2_000_000,
            predecessor_result=final_path,
        )

        self.assertEqual(final["outcome"], "pass")
        self.assertTrue(final["next_frequency_authorized"])
        self.assertEqual(final["analysis"]["highest_passed_hz"], 1_000_000)
        predecessor = next_contract.identity["predecessor"]
        self.assertEqual(
            predecessor["final_result_file_sha256"],
            runner._sha256(final_path.read_bytes()),
        )
        self.assertEqual(predecessor["final_result_plan_sha256"], final["plan_sha256"])
        self.assertEqual(predecessor["previous_job_id"], 1)
        self.assertEqual(predecessor["previous_operation_id"], 1)

    def test_second_frequency_runs_only_on_same_boot_pass_chain(self) -> None:
        first_live, _, first_dir = self.run_first()
        self.finalize_first(first_dir)
        final_path = first_dir / runner.FINAL_RESULT_FILENAME
        contract = runner.build_action_contract(
            self.campaign_dir, 2_000_000, predecessor_result=final_path
        )
        scripted = ScriptedRequester(responses_for_next(2_000_000, first_live))
        second_dir = self.root / "run-2mhz"

        second = runner._run_n7_sweep_once_legacy_test_only(
            self.campaign_dir,
            2_000_000,
            second_dir,
            base_url="http://synthetic-device",
            authorized_campaign_sha256=contract.snapshot.campaign_file_sha256,
            confirmation=contract.authorization_confirmation,
            predecessor_result=final_path,
            confirm_n7_firmware_flashed=True,
            confirm_panel_power_off_at_least_10s=True,
            confirm_supply_and_temperature_normal=True,
            confirm_scope_capture_armed=True,
            confirm_single_visible_action=True,
            confirm_esp32_not_rebooted=True,
            requester=scripted,
            sleeper=lambda _seconds: None,
        )

        self.assertEqual(second["outcome"], "protocol_pass_pending_adjudication")
        self.assertEqual(second["prior_job"], first_live["target_job"])
        self.assertEqual(second["prior_diagnostic"], first_live["target_diagnostic"])
        self.assertEqual(second["target_job"]["job_id"], 2)
        self.assertEqual(second["target_diagnostic"]["operation_id"], 2)
        self.assertEqual(
            scripted.calls.count(("POST", campaign.ROUTES[2_000_000])), 1
        )

    def test_failed_visual_adjudication_stops_next_frequency(self) -> None:
        _, _, result_dir = self.run_first()
        final = self.finalize_first(result_dir, visual_pass=False)

        self.assertEqual(final["outcome"], "fail_do_not_continue")
        self.assertFalse(final["next_frequency_authorized"])
        with self.assertRaisesRegex(runner.N7SweepError, "not PASS"):
            runner.build_action_contract(
                self.campaign_dir,
                2_000_000,
                predecessor_result=result_dir / runner.FINAL_RESULT_FILENAME,
            )

    def test_tampered_pass_evidence_is_rejected_from_sha_chain(self) -> None:
        _, _, result_dir = self.run_first()
        self.finalize_first(result_dir)
        final_path = result_dir / runner.FINAL_RESULT_FILENAME
        final = json.loads(final_path.read_text(encoding="utf-8"))
        changed = copy.deepcopy(final)
        changed["manual_and_scope_evidence"]["max_temperature_c"] = 31.0
        final_path.write_bytes(runner._canonical(changed) + b"\n")

        with self.assertRaisesRegex(runner.N7SweepError, "evidence summary differs"):
            runner.build_action_contract(
                self.campaign_dir,
                2_000_000,
                predecessor_result=final_path,
            )

    def test_tampered_live_request_audit_blocks_finalization(self) -> None:
        _, _, result_dir = self.run_first()
        live_path = result_dir / runner.LIVE_RESULT_FILENAME
        live = json.loads(live_path.read_text(encoding="utf-8"))
        live["request_audit"]["visible_post_count"] = 0
        live_path.write_bytes(runner._canonical(live) + b"\n")
        serial_path = self.root / "serial-tampered.log"
        scope_path = self.root / "scope-tampered.csv"
        serial_path.write_bytes(serial_log(1_000_000, 1))
        scope_path.write_bytes(b"scope")

        with self.assertRaisesRegex(runner.N7SweepError, "request audit safety"):
            runner.finalize_n7_sweep_result(
                self.campaign_dir,
                live_path,
                serial_path,
                scope_path,
                measured_sclk_hz=1_000_000.0,
                power_off_s=12.0,
                supply_voltage_v=3.3,
                current_limit_a=1.0,
                peak_current_a=0.2,
                max_temperature_c=30.0,
                visual_pass=True,
                cv_pass=True,
                thermal_pass=True,
                acoustic_pass=True,
            )


if __name__ == "__main__":
    unittest.main()
