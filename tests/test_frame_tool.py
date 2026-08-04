from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from host.epd_frame import (
    EXPECTED_FIXTURE_HASHES,
    FRAME_BYTES,
    ControllerMapping,
    controller_stream,
    fnv1a,
    generate_fixture,
)
from tools import mf1750_frame_tool as tool


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "MF1750_DRIVER_RC2F_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_PSRFIX_WEBPHOTO_PHYSICAL_2026-08-05"
DEFAULT_MAPPINGS = (ControllerMapping(0), ControllerMapping(1))


def mapping_text(mapping: ControllerMapping) -> str:
    return ",".join(
        str(int(value))
        for value in (
            mapping.source_half,
            mapping.flip_x,
            mapping.flip_y,
            mapping.nibble_swap,
        )
    )


def version_body(
    *,
    mappings: tuple[ControllerMapping, ControllerMapping] = DEFAULT_MAPPINGS,
    refresh_spi_hz: int = 1_000_000,
    psram_bytes: int = tool.NOMINAL_PSRAM_BYTES,
) -> str:
    return "\n".join(
        (
            BUILD_TAG,
            "Panel: 1024x600",
            "Driver API: MF1750_R16_CASCADE_V3",
            "Frame bytes: 307200",
            f"PSRAM bytes: {psram_bytes}",
            "Free PSRAM: 7900000",
            f"Refresh SPI Hz: {refresh_spi_hz}",
            f"CS1 Mapping: {mapping_text(mappings[0])}",
            f"CS2 Mapping: {mapping_text(mappings[1])}",
        )
    )


class ScriptedRequester:
    def __init__(self, responses: dict[str, list[tuple[int, str] | Exception]]) -> None:
        self.responses = {key: list(values) for key, values in responses.items()}
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
        del data, timeout
        self.calls.append((method, endpoint))
        if endpoint not in self.responses or not self.responses[endpoint]:
            raise AssertionError(f"unexpected request: {method} {endpoint}")
        response = self.responses[endpoint].pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def valid_refresh_responses(frame: bytes) -> dict[str, list[tuple[int, str] | Exception]]:
    frame_hash = fnv1a(frame)
    mappings = DEFAULT_MAPPINGS
    job = {
        "job_id": 7,
        "action": "uploaded_frame",
        "state": "completed",
        "result": True,
        "queued_at_ms": 1000,
        "started_at_ms": 1010,
        "finished_at_ms": 33060,
        "frame_fnv1a": frame_hash,
    }
    diagnostic = {
        "schema_version": 2,
        "operation_id": 23,
        "job_operation_id": 23,
        "valid": True,
        "running": False,
        "sequence_ok": True,
        "wait_timeout": False,
        "busy_assertion_missing": False,
        "busy_missing_stage": "none",
        "mapping_applied": True,
        "spi_hz": 1_000_000,
        "input_fnv1a": frame_hash,
        "cs1_dtm_fnv1a": fnv1a(controller_stream(frame, mappings[0])),
        "cs2_dtm_fnv1a": fnv1a(controller_stream(frame, mappings[1])),
        "total_ms": 32000,
        "cs1_upload_ms": 1500,
        "cs2_upload_ms": 1500,
        "pon_ms": 10,
        "pon_busy_seen": True,
        "drf_ms": 25000,
        "drf_busy_seen": True,
        "pof_ms": 20,
        "pof_busy_seen": True,
        "post_psr_ms": 20,
        "post_psr_busy_seen": False,
        "last_wait_ms": 20,
        "last_wait_stage": "post-display PSR",
        "timeout_stage": "none",
        "firmware_build_tag": BUILD_TAG,
        "driver_api_version": "MF1750_R16_CASCADE_V3",
        "job_id": 7,
        "job_action": "uploaded_frame",
        "job_state": "completed",
        "job_result": True,
        "job_queued_at_ms": 1000,
        "job_started_at_ms": 1010,
        "job_finished_at_ms": 33060,
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
    enqueue = {
        "ok": True,
        "bytes": FRAME_BYTES,
        "fnv1a": frame_hash,
        "free_psram": 7800000,
        "job_id": 7,
    }
    return {
        "/api/version": [(200, version_body())],
        "/api/frame": [(202, json.dumps(enqueue))],
        "/api/job": [(200, json.dumps(job))],
        "/api/diagnostic/report": [(200, json.dumps(diagnostic))],
    }


class OfflineReportTests(unittest.TestCase):
    def test_report_uses_logical_hash_names_without_implied_physical_mapping(self) -> None:
        frame = generate_fixture("map-orient-v1")
        report = tool.build_offline_report("map-orient-v1", frame)
        expected = EXPECTED_FIXTURE_HASHES["map-orient-v1"]
        self.assertTrue(report["offline_verified"])
        self.assertIs(report["hardware_tested"], False)
        self.assertNotIn("verified", report)
        self.assertEqual(
            (
                report["full_fnv1a"],
                report["logical_left_fnv1a"],
                report["logical_right_fnv1a"],
            ),
            expected,
        )
        self.assertNotIn("cs1_fnv1a", report)
        self.assertNotIn("physical_controllers", report)

    def test_physical_hashes_require_explicit_ordered_mapping(self) -> None:
        frame = generate_fixture("global-h-bars")
        mappings = (ControllerMapping(1, flip_y=True), ControllerMapping(0))
        report = tool.build_offline_report("global-h-bars", frame, mappings)
        physical = report["physical_controllers"]
        self.assertEqual(physical[0]["controller"], "CS1")
        self.assertEqual(
            physical[0]["dtm_fnv1a"], fnv1a(controller_stream(frame, mappings[0]))
        )

    def test_direct_script_bootstraps_repo_from_another_working_directory(self) -> None:
        script = REPO_ROOT / "tools" / "mf1750_frame_tool.py"
        with tempfile.TemporaryDirectory() as temporary:
            completed = subprocess.run(
                [sys.executable, str(script), "--pattern", "global-h-bars"],
                cwd=temporary,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertTrue(report["offline_verified"])
        self.assertIs(report["hardware_tested"], False)
        self.assertNotIn("verified", report)
        self.assertNotIn("physical_controllers", report)


class OutputSafetyTests(unittest.TestCase):
    def test_existing_output_requires_force(self) -> None:
        frame = b"safe"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "frame.bin"
            output.write_bytes(b"old")
            with self.assertRaisesRegex(tool.FrameToolError, "--force"):
                tool.write_frame(output, frame)
            tool.write_frame(output, frame, force=True)
            self.assertEqual(output.read_bytes(), frame)

    def test_frozen_production_path_is_always_rejected(self) -> None:
        output = tool.FROZEN_PRODUCTION_DIR / "never-create-frame-test.bin"
        self.assertFalse(output.exists())
        with self.assertRaisesRegex(tool.FrameToolError, "frozen production"):
            tool.write_frame(output, b"do not write", force=True)
        self.assertFalse(output.exists())

    def test_force_rejects_hard_link_alias_of_frozen_file(self) -> None:
        frozen_file = next(
            path for path in tool.FROZEN_PRODUCTION_DIR.rglob("*") if path.is_file()
        )
        original = frozen_file.read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            alias = Path(temporary) / "frozen-hard-link-alias.bin"
            os.link(frozen_file, alias)
            self.assertTrue(alias.samefile(frozen_file))
            with self.assertRaisesRegex(tool.FrameToolError, "hard-link alias"):
                tool.write_frame(alias, b"must not replace", force=True)
            self.assertEqual(frozen_file.read_bytes(), original)


class NetworkContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = generate_fixture("global-h-bars")
        self.frame_hash = fnv1a(self.frame)

    def test_nonrefreshing_ingress_checks_json_bytes_and_hash(self) -> None:
        response = {
            "ok": True,
            "bytes": FRAME_BYTES,
            "fnv1a": self.frame_hash,
            "free_psram": 7800000,
            "epd_action": "none",
        }
        requester = ScriptedRequester(
            {"/api/diagnostic/frame-ingress": [(200, json.dumps(response))]}
        )
        report = tool.perform_ingress("http://device", self.frame, requester=requester)
        self.assertTrue(report["protocol_verified"])
        self.assertIs(report["hardware_tested"], False)
        self.assertNotIn("verified", report)
        self.assertIn("explicit_no_epd_action", report["verified_scope"])
        self.assertEqual(requester.calls, [("POST", "/api/diagnostic/frame-ingress")])

        response["fnv1a"] ^= 1
        requester = ScriptedRequester(
            {"/api/diagnostic/frame-ingress": [(200, json.dumps(response))]}
        )
        with self.assertRaisesRegex(tool.FrameToolError, "fnv1a"):
            tool.perform_ingress("http://device", self.frame, requester=requester)

    def test_ingress_requires_explicit_no_epd_action(self) -> None:
        base_response = {
            "ok": True,
            "bytes": FRAME_BYTES,
            "fnv1a": self.frame_hash,
            "free_psram": 7800000,
        }
        for action in (None, "refresh"):
            with self.subTest(action=action):
                response = dict(base_response)
                if action is not None:
                    response["epd_action"] = action
                requester = ScriptedRequester(
                    {"/api/diagnostic/frame-ingress": [(200, json.dumps(response))]}
                )
                with self.assertRaisesRegex(tool.FrameToolError, "epd_action"):
                    tool.perform_ingress("http://device", self.frame, requester=requester)

    def test_invalid_frames_fail_before_url_handling_or_any_network(self) -> None:
        invalid_frames = {
            "short": self.frame[:-1],
            "long": self.frame + b"\x00",
            "unsupported-color": b"\x44" + self.frame[1:],
        }
        for label, invalid_frame in invalid_frames.items():
            for operation in ("ingress", "refresh"):
                with self.subTest(frame=label, operation=operation):
                    requester = ScriptedRequester({})
                    with self.assertRaisesRegex(
                        tool.FrameToolError, "invalid canonical frame"
                    ):
                        if operation == "ingress":
                            tool.perform_ingress(
                                "not even a URL", invalid_frame, requester=requester
                            )
                        else:
                            tool.perform_refresh(
                                "not even a URL",
                                invalid_frame,
                                expected_mappings=DEFAULT_MAPPINGS,
                                requester=requester,
                            )
                    self.assertEqual(requester.calls, [])

    def test_malformed_ipv6_url_is_wrapped_and_never_reaches_requester(self) -> None:
        for operation in ("ingress", "refresh"):
            with self.subTest(operation=operation):
                requester = ScriptedRequester({})
                with self.assertRaisesRegex(tool.FrameToolError, "--url is malformed"):
                    if operation == "ingress":
                        tool.perform_ingress(
                            "http://[::1", self.frame, requester=requester
                        )
                    else:
                        tool.perform_refresh(
                            "http://[::1",
                            self.frame,
                            expected_mappings=DEFAULT_MAPPINGS,
                            requester=requester,
                        )
                self.assertEqual(requester.calls, [])

    def test_refresh_requires_two_explicit_ordered_mappings_before_network(self) -> None:
        for mappings in (None, (DEFAULT_MAPPINGS[0],)):
            with self.subTest(mappings=mappings):
                requester = ScriptedRequester({})
                with self.assertRaisesRegex(tool.FrameToolError, "exactly two explicit"):
                    tool.perform_refresh(
                        "not even a URL",
                        self.frame,
                        expected_mappings=mappings,
                        requester=requester,
                    )
                self.assertEqual(requester.calls, [])

    def test_refresh_verifies_preflight_job_diagnostic_and_mapping_hashes(self) -> None:
        requester = ScriptedRequester(valid_refresh_responses(self.frame))
        report = tool.perform_refresh(
            "http://device",
            self.frame,
            expected_mappings=DEFAULT_MAPPINGS,
            requester=requester,
            sleeper=lambda _seconds: None,
        )
        self.assertTrue(report["protocol_verified"])
        self.assertIs(report["hardware_tested"], False)
        self.assertNotIn("verified", report)
        self.assertIn(
            "diagnostic_sequence_busy_timing_and_safe_finish_evidence",
            report["verified_scope"],
        )
        self.assertEqual(
            report["manual_observation_required"],
            [
                "full_panel_visual_result",
                "power_supply_cv_and_current",
                "L1_L2_temperature",
            ],
        )
        self.assertTrue(report["diagnostic"]["safe_finish_verified"])
        self.assertTrue(report["diagnostic"]["required_busy_stages_verified"])
        self.assertFalse(report["diagnostic"]["post_psr_busy_seen"])
        self.assertEqual(report["diagnostic"]["operation_id"], 23)
        self.assertEqual(report["diagnostic"]["job_operation_id"], 23)
        self.assertTrue(
            report["diagnostic"]["job_driver_operation_identity_matched"]
        )
        self.assertIn(
            "diagnostic_immutable_driver_operation_identity",
            report["verified_scope"],
        )
        self.assertEqual(
            requester.calls,
            [
                ("GET", "/api/version"),
                ("POST", "/api/frame"),
                ("GET", "/api/job"),
                ("GET", "/api/diagnostic/report"),
            ],
        )

    def test_failed_looking_202_is_never_success(self) -> None:
        responses = valid_refresh_responses(self.frame)
        responses["/api/frame"] = [(202, json.dumps({"ok": False, "job_id": 7}))]
        requester = ScriptedRequester(responses)
        with self.assertRaises(tool.FrameToolError):
            tool.perform_refresh(
                "http://device",
                self.frame,
                expected_mappings=DEFAULT_MAPPINGS,
                requester=requester,
            )
        self.assertNotIn(("GET", "/api/job"), requester.calls)

    def test_failed_or_mismatched_job_is_never_success(self) -> None:
        for mutation, message in (
            ({"state": "failed", "result": False}, "failed"),
            ({"frame_fnv1a": self.frame_hash ^ 1}, "hash"),
            ({"job_id": 8}, "id changed"),
        ):
            with self.subTest(mutation=mutation):
                responses = valid_refresh_responses(self.frame)
                job = json.loads(responses["/api/job"][0][1])
                job.update(mutation)
                responses["/api/job"] = [(200, json.dumps(job))]
                requester = ScriptedRequester(responses)
                with self.assertRaisesRegex(tool.FrameToolError, message):
                    tool.perform_refresh(
                        "http://device",
                        self.frame,
                        expected_mappings=DEFAULT_MAPPINGS,
                        requester=requester,
                    )

    def test_completed_job_timestamps_must_be_u32_and_ordered(self) -> None:
        mutations = (
            ({"queued_at_ms": True}, "unsigned 32-bit"),
            ({"started_at_ms": 999}, "queued -> started"),
            ({"finished_at_ms": 1009}, "started -> finished"),
        )
        for mutation, message in mutations:
            with self.subTest(mutation=mutation):
                responses = valid_refresh_responses(self.frame)
                job = json.loads(responses["/api/job"][0][1])
                job.update(mutation)
                responses["/api/job"] = [(200, json.dumps(job))]
                with self.assertRaisesRegex(tool.FrameToolError, message):
                    tool.perform_refresh(
                        "http://device",
                        self.frame,
                        expected_mappings=DEFAULT_MAPPINGS,
                        requester=ScriptedRequester(responses),
                    )

    def test_diagnostic_job_timestamps_must_match_completed_job(self) -> None:
        responses = valid_refresh_responses(self.frame)
        diagnostic = json.loads(responses["/api/diagnostic/report"][0][1])
        diagnostic["job_started_at_ms"] += 1
        responses["/api/diagnostic/report"] = [(200, json.dumps(diagnostic))]
        with self.assertRaisesRegex(tool.FrameToolError, "job_started_at_ms"):
            tool.perform_refresh(
                "http://device",
                self.frame,
                expected_mappings=DEFAULT_MAPPINGS,
                requester=ScriptedRequester(responses),
            )

    def test_diagnostic_operation_id_must_be_nonzero_u32(self) -> None:
        invalid_values = (
            ("missing", None),
            ("bool", True),
            ("zero", 0),
            ("negative", -1),
            ("above-u32", tool.UINT32_MAX + 1),
        )
        for label, value in invalid_values:
            with self.subTest(case=label):
                responses = valid_refresh_responses(self.frame)
                diagnostic = json.loads(responses["/api/diagnostic/report"][0][1])
                if label == "missing":
                    diagnostic.pop("operation_id")
                else:
                    diagnostic["operation_id"] = value
                responses["/api/diagnostic/report"] = [
                    (200, json.dumps(diagnostic))
                ]
                with self.assertRaisesRegex(
                    tool.FrameToolError, r"diagnostic\.operation_id"
                ):
                    tool.perform_refresh(
                        "http://device",
                        self.frame,
                        expected_mappings=DEFAULT_MAPPINGS,
                        requester=ScriptedRequester(responses),
                    )

    def test_diagnostic_job_operation_id_must_be_matching_nonzero_u32(self) -> None:
        invalid_values = (
            ("missing", None),
            ("bool", True),
            ("zero", 0),
            ("negative", -1),
            ("above-u32", tool.UINT32_MAX + 1),
            ("mismatch", 24),
        )
        for label, value in invalid_values:
            with self.subTest(case=label):
                responses = valid_refresh_responses(self.frame)
                diagnostic = json.loads(responses["/api/diagnostic/report"][0][1])
                if label == "missing":
                    diagnostic.pop("job_operation_id")
                else:
                    diagnostic["job_operation_id"] = value
                responses["/api/diagnostic/report"] = [
                    (200, json.dumps(diagnostic))
                ]
                with self.assertRaisesRegex(
                    tool.FrameToolError, r"job_operation_id"
                ):
                    tool.perform_refresh(
                        "http://device",
                        self.frame,
                        expected_mappings=DEFAULT_MAPPINGS,
                        requester=ScriptedRequester(responses),
                    )

    def test_diagnostic_busy_missing_summary_is_blocking(self) -> None:
        cases = (
            ("missing-flag", "busy_assertion_missing", None, True, "busy_assertion_missing"),
            ("assertion-missing", "busy_assertion_missing", True, False, "missing BUSY"),
            ("missing-stage", "busy_missing_stage", None, True, "busy_missing_stage"),
            ("named-stage", "busy_missing_stage", "DRF", False, "busy_missing_stage"),
        )
        for label, key, value, remove, message in cases:
            with self.subTest(case=label):
                responses = valid_refresh_responses(self.frame)
                diagnostic = json.loads(responses["/api/diagnostic/report"][0][1])
                if remove:
                    diagnostic.pop(key)
                else:
                    diagnostic[key] = value
                responses["/api/diagnostic/report"] = [
                    (200, json.dumps(diagnostic))
                ]
                with self.assertRaisesRegex(tool.FrameToolError, message):
                    tool.perform_refresh(
                        "http://device",
                        self.frame,
                        expected_mappings=DEFAULT_MAPPINGS,
                        requester=ScriptedRequester(responses),
                    )

    def test_bad_report_or_stale_build_is_never_success(self) -> None:
        responses = valid_refresh_responses(self.frame)
        diagnostic = json.loads(responses["/api/diagnostic/report"][0][1])
        diagnostic["last_wait_stage"] = "POF"
        responses["/api/diagnostic/report"] = [(200, json.dumps(diagnostic))]
        with self.assertRaisesRegex(tool.FrameToolError, "safe post-display"):
            tool.perform_refresh(
                "http://device",
                self.frame,
                expected_mappings=DEFAULT_MAPPINGS,
                requester=ScriptedRequester(responses),
            )

        for bad_tag in (
            BUILD_TAG.replace("RC2F", "RC2E"),
            BUILD_TAG.replace("RC2F", "RC20"),
            BUILD_TAG.replace("COLORGUARD", "NOCOLORGUARD"),
        ):
            with self.subTest(bad_tag=bad_tag):
                responses = valid_refresh_responses(self.frame)
                responses["/api/version"] = [
                    (200, version_body().replace(BUILD_TAG, bad_tag))
                ]
                requester = ScriptedRequester(responses)
                with self.assertRaisesRegex(tool.FrameToolError, "exact safety allowlist"):
                    tool.perform_refresh(
                        "http://device",
                        self.frame,
                        expected_mappings=DEFAULT_MAPPINGS,
                        requester=requester,
                    )
                self.assertEqual(requester.calls, [("GET", "/api/version")])

    def test_cli_wraps_malformed_ipv6_without_network(self) -> None:
        with mock.patch.object(tool, "http_request") as request:
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                result = tool.main(["--url", "http://[::1"])
            self.assertEqual(result, 1)
            self.assertIn("--url is malformed", error.getvalue())
            request.assert_not_called()

    def test_preflight_spi_or_mapping_mismatch_blocks_before_frame_post(self) -> None:
        mismatch_versions = {
            "spi": version_body(refresh_spi_hz=2_000_000),
            "mapping": version_body(
                mappings=(ControllerMapping(1), ControllerMapping(0))
            ),
        }
        for label, body in mismatch_versions.items():
            with self.subTest(label=label):
                responses = valid_refresh_responses(self.frame)
                responses["/api/version"] = [(200, body)]
                requester = ScriptedRequester(responses)
                with self.assertRaises(tool.FrameToolError):
                    tool.perform_refresh(
                        "http://device",
                        self.frame,
                        expected_mappings=DEFAULT_MAPPINGS,
                        requester=requester,
                    )
                self.assertEqual(requester.calls, [("GET", "/api/version")])

    def test_preflight_allows_bounded_8_mib_heap_metadata_overhead(self) -> None:
        observed_hardware_bytes = tool.NOMINAL_PSRAM_BYTES - 2_761
        responses = valid_refresh_responses(self.frame)
        responses["/api/version"] = [
            (200, version_body(psram_bytes=observed_hardware_bytes))
        ]
        requester = ScriptedRequester(responses)

        result = tool.perform_refresh(
            "http://device",
            self.frame,
            expected_mappings=DEFAULT_MAPPINGS,
            requester=requester,
        )

        self.assertEqual(result["preflight"]["psram_bytes"], observed_hardware_bytes)
        self.assertIn(("POST", "/api/frame"), requester.calls)

    def test_preflight_rejects_psram_below_bounded_8_mib_heap_floor(self) -> None:
        responses = valid_refresh_responses(self.frame)
        responses["/api/version"] = [
            (200, version_body(psram_bytes=tool.MIN_REPORTED_PSRAM_BYTES - 1))
        ]
        requester = ScriptedRequester(responses)

        with self.assertRaisesRegex(tool.FrameToolError, "minimum managed PSRAM heap"):
            tool.perform_refresh(
                "http://device",
                self.frame,
                expected_mappings=DEFAULT_MAPPINGS,
                requester=requester,
            )

        self.assertEqual(requester.calls, [("GET", "/api/version")])

    def test_refresh_requires_complete_busy_timing_evidence(self) -> None:
        mutations = (
            ({"pon_busy_seen": False}, "pon_busy_seen"),
            ({"drf_ms": 9_999}, "drf_ms"),
            ({"drf_ms": 60_001}, "drf_ms"),
            ({"post_psr_busy_seen": "false"}, "post_psr_busy_seen"),
            ({"post_psr_ms": 21}, "last_wait_ms"),
            ({"total_ms": 1}, "total_ms"),
        )
        for mutation, message in mutations:
            with self.subTest(mutation=mutation):
                responses = valid_refresh_responses(self.frame)
                diagnostic = json.loads(responses["/api/diagnostic/report"][0][1])
                diagnostic.update(mutation)
                responses["/api/diagnostic/report"] = [(200, json.dumps(diagnostic))]
                with self.assertRaisesRegex(tool.FrameToolError, message):
                    tool.perform_refresh(
                        "http://device",
                        self.frame,
                        expected_mappings=DEFAULT_MAPPINGS,
                        requester=ScriptedRequester(responses),
                    )

    def test_refresh_flag_requires_confirmation_before_any_network(self) -> None:
        with mock.patch.object(tool, "http_request") as request:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(
                    tool.main(
                        [
                            "--url",
                            "http://device",
                            "--refresh",
                            "--controller-mapping",
                            "0,0,0,0",
                            "--controller-mapping",
                            "1,0,0,0",
                        ]
                    ),
                    2,
                )
            request.assert_not_called()

    def test_refresh_cli_requires_explicit_mapping_before_any_network(self) -> None:
        for mapping_args in ((), ("--controller-mapping", "0,0,0,0")):
            with self.subTest(mapping_args=mapping_args):
                with mock.patch.object(tool, "http_request") as request:
                    error = io.StringIO()
                    with contextlib.redirect_stderr(error):
                        result = tool.main(
                            [
                                "--url",
                                "http://device",
                                "--refresh",
                                "--confirm-cold-start",
                                *mapping_args,
                            ]
                        )
                    self.assertEqual(result, 2)
                    self.assertIn("exactly two --controller-mapping", error.getvalue())
                    request.assert_not_called()

    def test_cli_invalid_frame_fails_cleanly_before_any_network(self) -> None:
        invalid_frame = self.frame[:-1]
        commands = (
            ["--url", "not a URL"],
            [
                "--url",
                "not a URL",
                "--refresh",
                "--confirm-cold-start",
                "--controller-mapping",
                "0,0,0,0",
                "--controller-mapping",
                "1,0,0,0",
            ],
        )
        for command in commands:
            with self.subTest(command=command):
                with mock.patch.object(tool, "generate_fixture", return_value=invalid_frame):
                    with mock.patch.object(tool, "http_request") as request:
                        error = io.StringIO()
                        with contextlib.redirect_stderr(error):
                            result = tool.main(command)
                        self.assertEqual(result, 1)
                        self.assertIn("invalid canonical frame", error.getvalue())
                        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
