from __future__ import annotations

import copy
import hashlib
import json
import math
import unittest

from tools.mf1750_refresh_analyzer import (
    DEFAULT_FREQUENCIES,
    EXPECTED_CS1_FNV1A,
    EXPECTED_CS2_FNV1A,
    EXPECTED_FULL_FNV1A,
    FRAME_BYTES,
    OPTIONAL_FREQUENCY,
    SWEEP_ACTION,
    RefreshAnalysisError,
    analyze_document,
    build_plan,
    extract_observation,
    parse_args,
    theoretical_wire_time_ms,
    validate_run,
)


BUILD_TAG = "test-build"
DRIVER_API = "MF1750_R16_CASCADE_V2"
VERSION_REPORT = (
    f"{BUILD_TAG}\n"
    "Panel: 1024x600 Spectra 6\n"
    f"Driver API: {DRIVER_API}\n"
    "Hardware: R16 cascade\n"
)
MAPPING = {
    "cs1_source_half": 0,
    "cs1_flip_x": False,
    "cs1_flip_y": False,
    "cs1_nibble_swap": False,
    "cs2_source_half": 1,
    "cs2_flip_x": False,
    "cs2_flip_y": False,
    "cs2_nibble_swap": False,
}
PON_MS = 100
DRF_MS = 21_700
POF_MS = 100
POST_PSR_MS = 100


def upload_times(spi_hz: int) -> tuple[int, int]:
    raw_half_ms = theoretical_wire_time_ms(spi_hz, FRAME_BYTES // 2)
    cs1_ms = math.ceil(raw_half_ms + 25)
    return cs1_ms, cs1_ms + 2


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def rebind_observation(run: dict) -> None:
    payload = dict(run)
    payload.pop("observation_canonical_sha256", None)
    run["observation_canonical_sha256"] = canonical_sha256(payload)


def valid_log(
    spi_hz: int,
    *,
    job_id: int | None = None,
    action: str = SWEEP_ACTION,
    counts: str = "PASS",
    busy_seen: int = 1,
    cs1_upload_ms: int | None = None,
    cs2_upload_ms: int | None = None,
    drf_ms: int = DRF_MS,
) -> str:
    if job_id is None:
        job_id = spi_hz // 1_000_000 + 10
    default_cs1_ms, default_cs2_ms = upload_times(spi_hz)
    cs1_ms = default_cs1_ms if cs1_upload_ms is None else cs1_upload_ms
    cs2_ms = default_cs2_ms if cs2_upload_ms is None else cs2_upload_ms
    return (
        f"Running EPD job {job_id} action 27 ({action})\n"
        f"MAP_ORIENT_V1 frame FNV-1a: {EXPECTED_FULL_FNV1A} "
        f"(expected {EXPECTED_FULL_FNV1A}), counts={counts}\n"
        f"EPD full frame CS1 upload done after {cs1_ms} ms, "
        f"DTM FNV-1a={EXPECTED_CS1_FNV1A}\n"
        f"EPD full frame CS2 upload done after {cs2_ms} ms, "
        f"DTM FNV-1a={EXPECTED_CS2_FNV1A}\n"
        f"EPD idle: PON after {PON_MS} ms, busy_seen={busy_seen}\n"
        f"EPD idle: DRF after {drf_ms} ms, busy_seen={busy_seen}\n"
        f"EPD idle: POF after {POF_MS} ms, busy_seen={busy_seen}\n"
        f"EPD idle: post-display PSR after {POST_PSR_MS} ms, "
        f"busy_seen={busy_seen}\n"
        "EPD full-frame cascade refresh: PASS\n"
        f"EPD job {job_id} finished: state=completed result_known=1 result=1\n"
    )


def valid_diagnostic(
    spi_hz: int,
    *,
    job_id: int | None = None,
    action: str = SWEEP_ACTION,
    firmware_build_tag: str = BUILD_TAG,
    cs1_upload_ms: int | None = None,
    cs2_upload_ms: int | None = None,
    drf_ms: int = DRF_MS,
) -> dict:
    if job_id is None:
        job_id = spi_hz // 1_000_000 + 10
    default_cs1_ms, default_cs2_ms = upload_times(spi_hz)
    cs1_ms = default_cs1_ms if cs1_upload_ms is None else cs1_upload_ms
    cs2_ms = default_cs2_ms if cs2_upload_ms is None else cs2_upload_ms
    total_ms = cs1_ms + cs2_ms + PON_MS + drf_ms + POF_MS + POST_PSR_MS + 7_000
    return {
        "schema_version": 2,
        "operation_id": job_id + 100,
        "job_operation_id": job_id + 100,
        "valid": True,
        "running": False,
        "sequence_ok": True,
        "wait_timeout": False,
        "busy_assertion_missing": False,
        "busy_missing_stage": "none",
        "mapping_applied": True,
        "firmware_build_tag": firmware_build_tag,
        "driver_api_version": DRIVER_API,
        "job_id": job_id,
        "job_action": action,
        "job_state": "completed",
        "job_result": True,
        "job_queued_at_ms": 1_000,
        "job_started_at_ms": 1_010,
        "job_finished_at_ms": 1_010 + total_ms + 50,
        "spi_hz": spi_hz,
        "input_fnv1a": EXPECTED_FULL_FNV1A,
        "cs1_dtm_fnv1a": EXPECTED_CS1_FNV1A,
        "cs2_dtm_fnv1a": EXPECTED_CS2_FNV1A,
        "cs1_upload_ms": cs1_ms,
        "cs2_upload_ms": cs2_ms,
        "pon_ms": PON_MS,
        "pon_busy_seen": True,
        "drf_ms": drf_ms,
        "drf_busy_seen": True,
        "pof_ms": POF_MS,
        "pof_busy_seen": True,
        "post_psr_ms": POST_PSR_MS,
        "post_psr_busy_seen": True,
        "total_ms": total_ms,
        "last_wait_ms": POST_PSR_MS,
        "last_wait_stage": "post-display PSR",
        "timeout_stage": "none",
        "mapping": copy.deepcopy(MAPPING),
    }


def valid_job(
    spi_hz: int,
    *,
    job_id: int | None = None,
    action: str = SWEEP_ACTION,
    cs1_upload_ms: int | None = None,
    cs2_upload_ms: int | None = None,
    drf_ms: int = DRF_MS,
) -> dict:
    if job_id is None:
        job_id = spi_hz // 1_000_000 + 10
    diagnostic = valid_diagnostic(
        spi_hz,
        job_id=job_id,
        action=action,
        cs1_upload_ms=cs1_upload_ms,
        cs2_upload_ms=cs2_upload_ms,
        drf_ms=drf_ms,
    )
    queued_at_ms = 1_000
    started_at_ms = 1_010
    finished_at_ms = started_at_ms + diagnostic["total_ms"] + 50
    return {
        "job_id": job_id,
        "action": action,
        "state": "completed",
        "result": True,
        "queued_at_ms": queued_at_ms,
        "started_at_ms": started_at_ms,
        "finished_at_ms": finished_at_ms,
        "frame_fnv1a": EXPECTED_FULL_FNV1A,
    }


def manual_observations(spi_hz: int) -> dict:
    return {
        "cold_start": True,
        "power_off_s": 12.0,
        "supply_voltage_v": 3.3,
        "current_limit_a": 1.0,
        "peak_current_a": 0.2,
        "max_temperature_c": 30.0,
        "measured_sclk_hz": float(spi_hz),
        "sclk_pass": True,
        "visual_pass": True,
        "cv_pass": True,
        "thermal_pass": True,
        "acoustic_pass": True,
    }


def extracted_run(
    spi_hz: int,
    *,
    log: str | None = None,
    diagnostic: dict | None = None,
    job: dict | None = None,
    version_report: str = VERSION_REPORT,
    timing: bool | None = None,
) -> dict:
    if timing is None:
        timing = spi_hz == OPTIONAL_FREQUENCY
    return extract_observation(
        spi_hz,
        valid_log(spi_hz) if log is None else log,
        valid_diagnostic(spi_hz) if diagnostic is None else diagnostic,
        valid_job(spi_hz) if job is None else job,
        version_report,
        f"scope-capture-{spi_hz}".encode(),
        **manual_observations(spi_hz),
        timing_evidence=(b"timing-capture-20mhz" if timing else None),
        timing_pass=(True if timing else None),
        notes="synthetic evidence fixture",
    )


def replace_timing(run: dict, *, cs1_ms: int, cs2_ms: int, drf_ms: int = DRF_MS) -> None:
    run["cs1_upload_ms"] = cs1_ms
    run["report_cs1_upload_ms"] = cs1_ms
    run["cs2_upload_ms"] = cs2_ms
    run["report_cs2_upload_ms"] = cs2_ms
    run["drf_ms"] = drf_ms
    run["report_drf_ms"] = drf_ms
    total_ms = cs1_ms + cs2_ms + PON_MS + drf_ms + POF_MS + POST_PSR_MS + 7_000
    run["total_ms"] = total_ms
    run["job_finished_at_ms"] = run["job_started_at_ms"] + total_ms + 50
    run["report_job_finished_at_ms"] = run["job_finished_at_ms"]
    rebind_observation(run)


class PlanTests(unittest.TestCase):
    def test_default_plan_is_schema_v2_sweep_contract(self) -> None:
        plan = build_plan()
        self.assertEqual(plan["schema_version"], 2)
        self.assertEqual(plan["required_action"], SWEEP_ACTION)
        self.assertEqual(plan["frequency_order_hz"], list(DEFAULT_FREQUENCIES))
        self.assertTrue(all(run["observation_recorded"] is False for run in plan["runs"]))
        self.assertEqual(analyze_document(plan)["overall"], "INCOMPLETE")

    def test_optional_plan_places_20mhz_last(self) -> None:
        plan = build_plan(include_20mhz=True)
        self.assertEqual(plan["frequency_order_hz"][-1], OPTIONAL_FREQUENCY)

    def test_wire_time_budget_and_bad_inputs(self) -> None:
        self.assertAlmostEqual(theoretical_wire_time_ms(1_000_000), 2457.6)
        self.assertAlmostEqual(theoretical_wire_time_ms(10_000_000), 245.76)
        self.assertAlmostEqual(theoretical_wire_time_ms(20_000_000), 122.88)
        with self.assertRaises(RefreshAnalysisError):
            theoretical_wire_time_ms(0)
        with self.assertRaises(RefreshAnalysisError):
            theoretical_wire_time_ms(True)


class ExtractionTests(unittest.TestCase):
    def test_extracts_linked_identity_hashes_mapping_and_timings(self) -> None:
        observation = extracted_run(1_000_000)
        self.assertTrue(observation["observation_recorded"])
        self.assertEqual(observation["firmware_build_tag"], BUILD_TAG)
        self.assertEqual(observation["driver_api_version"], DRIVER_API)
        self.assertEqual(observation["report_schema_version"], 2)
        self.assertEqual(observation["report_operation_id"], 111)
        self.assertEqual(observation["report_driver_api_version"], DRIVER_API)
        self.assertEqual(observation["job_id"], 11)
        self.assertEqual(observation["serial_job_start_id"], 11)
        self.assertEqual(observation["report_job_id"], 11)
        self.assertEqual(observation["report_job_started_at_ms"], 1_010)
        self.assertEqual(observation["full_fnv1a"], EXPECTED_FULL_FNV1A)
        self.assertEqual(observation["cs1_dtm_fnv1a"], EXPECTED_CS1_FNV1A)
        self.assertEqual(observation["cs2_dtm_fnv1a"], EXPECTED_CS2_FNV1A)
        self.assertEqual(observation["drf_ms"], DRF_MS)
        self.assertEqual(observation["report_drf_ms"], DRF_MS)
        self.assertTrue(observation["report_drf_busy_seen"])
        self.assertEqual(observation["mapping"], MAPPING)
        for field in (
            "version_report_raw_sha256",
            "serial_log_raw_sha256",
            "diagnostic_report_canonical_sha256",
            "job_report_canonical_sha256",
            "mapping_canonical_sha256",
            "scope_evidence_sha256",
        ):
            self.assertRegex(observation[field], r"^[0-9a-f]{64}$")

    def test_duplicate_and_cross_capture_mismatches_are_rejected(self) -> None:
        with self.assertRaisesRegex(RefreshAnalysisError, "capture exactly one run"):
            extracted_run(1_000_000, log=valid_log(1_000_000) * 2)

        start_line = valid_log(1_000_000).splitlines()[0]
        with self.assertRaisesRegex(RefreshAnalysisError, "job start"):
            extracted_run(1_000_000, log=valid_log(1_000_000) + start_line)

        diagnostic = valid_diagnostic(1_000_000)
        diagnostic["job_id"] += 1
        with self.assertRaisesRegex(RefreshAnalysisError, "job/report job_id"):
            extracted_run(1_000_000, diagnostic=diagnostic)

        diagnostic = valid_diagnostic(1_000_000)
        diagnostic["cs1_upload_ms"] += 1
        with self.assertRaisesRegex(RefreshAnalysisError, "serial/report CS1 upload"):
            extracted_run(1_000_000, diagnostic=diagnostic)

        diagnostic = valid_diagnostic(1_000_000)
        diagnostic["firmware_build_tag"] = "stale-build"
        with self.assertRaisesRegex(RefreshAnalysisError, "version/report build tag"):
            extracted_run(1_000_000, diagnostic=diagnostic)

        diagnostic = valid_diagnostic(1_000_000)
        diagnostic["driver_api_version"] = "STALE_API"
        with self.assertRaisesRegex(RefreshAnalysisError, "version/report driver API"):
            extracted_run(1_000_000, diagnostic=diagnostic)

        diagnostic = valid_diagnostic(1_000_000)
        diagnostic["job_started_at_ms"] += 1
        with self.assertRaisesRegex(RefreshAnalysisError, "started timestamp"):
            extracted_run(1_000_000, diagnostic=diagnostic)

        diagnostic = valid_diagnostic(1_000_000)
        diagnostic["drf_busy_seen"] = False
        with self.assertRaisesRegex(RefreshAnalysisError, "DRF busy"):
            extracted_run(1_000_000, diagnostic=diagnostic)

        diagnostic = valid_diagnostic(1_000_000)
        diagnostic["drf_ms"] = 1
        with self.assertRaisesRegex(RefreshAnalysisError, "DRF wait"):
            extracted_run(1_000_000, diagnostic=diagnostic)

    def test_serial_markers_must_be_inside_one_ordered_job_boundary(self) -> None:
        lines = valid_log(1_000_000).splitlines()
        reordered = "\n".join([lines[-1], *lines[1:-1], lines[0]])
        with self.assertRaisesRegex(RefreshAnalysisError, "ordered job boundary"):
            extracted_run(1_000_000, log=reordered)

    def test_extract_rejects_invalid_diagnostic_operation_id(self) -> None:
        invalid_values = (None, 0, True, 0x1_0000_0000)
        for value in invalid_values:
            with self.subTest(value=value):
                diagnostic = valid_diagnostic(1_000_000)
                if value is None:
                    diagnostic.pop("operation_id")
                else:
                    diagnostic["operation_id"] = value
                with self.assertRaisesRegex(
                    RefreshAnalysisError,
                    "operation_id must be a positive unsigned 32-bit integer",
                ):
                    extracted_run(1_000_000, diagnostic=diagnostic)

    def test_extract_rejects_unbound_operation_or_missing_busy_assertion(self) -> None:
        for value in (None, 0, True, 0x1_0000_0000):
            with self.subTest(job_operation_id=value):
                diagnostic = valid_diagnostic(1_000_000)
                if value is None:
                    diagnostic.pop("job_operation_id")
                else:
                    diagnostic["job_operation_id"] = value
                with self.assertRaisesRegex(
                    RefreshAnalysisError,
                    "job_operation_id must be a positive unsigned 32-bit integer",
                ):
                    extracted_run(1_000_000, diagnostic=diagnostic)

        diagnostic = valid_diagnostic(1_000_000)
        diagnostic["job_operation_id"] += 1
        with self.assertRaisesRegex(RefreshAnalysisError, "operation_id mismatch"):
            extracted_run(1_000_000, diagnostic=diagnostic)

        for field, value, expected in (
            ("busy_assertion_missing", True, "must be false"),
            ("busy_assertion_missing", None, "must be false"),
            ("busy_missing_stage", "DRF", "must be 'none'"),
            ("busy_missing_stage", None, "must be 'none'"),
        ):
            with self.subTest(field=field, value=value):
                diagnostic = valid_diagnostic(1_000_000)
                if value is None:
                    diagnostic.pop(field)
                else:
                    diagnostic[field] = value
                with self.assertRaisesRegex(RefreshAnalysisError, expected):
                    extracted_run(1_000_000, diagnostic=diagnostic)

    def test_truncated_log_is_recorded_and_fails_instead_of_using_report_fallback(self) -> None:
        log = valid_log(1_000_000)
        log = "\n".join(line for line in log.splitlines() if "MAP_ORIENT_V1" not in line)
        observation = extracted_run(1_000_000, log=log)
        self.assertIsNone(observation["full_fnv1a"])
        document = build_plan()
        document["runs"][0] = observation
        result = analyze_document(document)["results"][0]
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("full_fnv1a is required" in error for error in result["errors"]))

    def test_raw_text_hash_changes_but_canonical_json_hash_ignores_key_order(self) -> None:
        spi_hz = 1_000_000
        lf_run = extracted_run(spi_hz)
        diagnostic = valid_diagnostic(spi_hz)
        job = valid_job(spi_hz)
        crlf_run = extract_observation(
            spi_hz,
            valid_log(spi_hz).replace("\n", "\r\n").encode(),
            dict(reversed(list(diagnostic.items()))),
            dict(reversed(list(job.items()))),
            VERSION_REPORT.encode(),
            f"scope-capture-{spi_hz}".encode(),
            **manual_observations(spi_hz),
        )
        self.assertNotEqual(
            lf_run["serial_log_raw_sha256"], crlf_run["serial_log_raw_sha256"]
        )
        self.assertEqual(
            lf_run["diagnostic_report_canonical_sha256"],
            crlf_run["diagnostic_report_canonical_sha256"],
        )
        self.assertEqual(
            lf_run["job_report_canonical_sha256"],
            crlf_run["job_report_canonical_sha256"],
        )

    def test_cli_requires_external_version_and_scope_evidence_and_records_false(self) -> None:
        args = parse_args(
            [
                "extract",
                "plan.json",
                "--serial-log",
                "serial.log",
                "--report",
                "report.json",
                "--job-report",
                "job.json",
                "--version-report",
                "version.txt",
                "--scope-evidence",
                "scope.csv",
                "--spi-hz",
                "1000000",
                "--measured-sclk-hz",
                "1001000",
                "--no-sclk-pass",
                "--cold-start",
                "--power-off-s",
                "10",
                "--supply-voltage-v",
                "3.3",
                "--current-limit-a",
                "1.0",
                "--peak-current-a",
                "0.2",
                "--max-temperature-c",
                "30",
                "--no-visual-pass",
                "--cv-pass",
                "--thermal-pass",
                "--no-acoustic-pass",
            ]
        )
        self.assertFalse(args.sclk_pass)
        self.assertFalse(args.visual_pass)
        self.assertFalse(args.acoustic_pass)
        self.assertEqual(args.version_report.name, "version.txt")
        self.assertEqual(args.scope_evidence.name, "scope.csv")


class RunGateTests(unittest.TestCase):
    def test_complete_future_contract_run_passes(self) -> None:
        errors, warnings = validate_run(extracted_run(1_000_000))
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_diagnostic_schema_api_job_and_busy_evidence_are_blocking(self) -> None:
        mutations = (
            ("report_schema_version", 1, "report_schema_version must be integer 2"),
            (
                "report_driver_api_version",
                "STALE_API",
                "version/report driver_api_version mismatch",
            ),
            (
                "report_job_started_at_ms",
                1_011,
                "diagnostic started timestamp mismatch",
            ),
            ("report_drf_busy_seen", False, "report_drf_busy_seen must be true"),
            (
                "report_drf_ms",
                1,
                "report_drf_ms must remain within 10000..60000 ms",
            ),
        )
        for field, value, expected_error in mutations:
            with self.subTest(field=field):
                run = extracted_run(1_000_000)
                run[field] = value
                rebind_observation(run)
                document = build_plan()
                document["runs"][0] = run
                report = analyze_document(document)
                self.assertEqual(report["results"][0]["status"], "FAIL")
                self.assertEqual(report["overall"], "FAIL")
                self.assertIn(expected_error, report["results"][0]["errors"])

    def test_recorded_operation_id_must_be_nonzero_u32(self) -> None:
        invalid_values = (None, 0, True, 0x1_0000_0000)
        for value in invalid_values:
            with self.subTest(value=value):
                run = extracted_run(1_000_000)
                run["report_operation_id"] = value
                rebind_observation(run)
                document = build_plan()
                document["runs"][0] = run
                report = analyze_document(document)
                self.assertEqual(report["results"][0]["status"], "FAIL")
                self.assertEqual(report["overall"], "FAIL")
                self.assertTrue(
                    any("report_operation_id" in error for error in report["results"][0]["errors"])
                )

    def test_recorded_operation_binding_and_busy_assertion_are_blocking(self) -> None:
        mutations = (
            ("report_job_operation_id", 0, "report_job_operation_id"),
            ("report_job_operation_id", True, "report_job_operation_id"),
            ("report_job_operation_id", 0x1_0000_0000, "report_job_operation_id"),
            ("report_job_operation_id", 112, "job_operation_id/operation_id mismatch"),
            ("report_busy_assertion_missing", True, "must be false"),
            ("report_busy_missing_stage", "DRF", "must be 'none'"),
        )
        for field, value, expected_error in mutations:
            with self.subTest(field=field, value=value):
                run = extracted_run(1_000_000)
                run[field] = value
                rebind_observation(run)
                document = build_plan()
                document["runs"][0] = run
                result = analyze_document(document)
                self.assertEqual(result["results"][0]["status"], "FAIL")
                self.assertEqual(result["overall"], "FAIL")
                self.assertTrue(
                    any(expected_error in error for error in result["results"][0]["errors"])
                )

    def test_current_100khz_slow_action_cannot_pass_future_sweep_gate(self) -> None:
        spi_hz = 100_000
        action = "map_orient_v1_slow"
        diagnostic = valid_diagnostic(spi_hz, action=action)
        for field in (
            "firmware_build_tag",
            "job_id",
            "job_action",
            "job_state",
            "job_result",
        ):
            diagnostic.pop(field)
        observation = extract_observation(
            spi_hz,
            valid_log(spi_hz, action=action),
            diagnostic,
            valid_job(spi_hz, action=action),
            VERSION_REPORT,
            b"scope-current-api",
            **manual_observations(spi_hz),
        )
        errors, _ = validate_run(observation)
        self.assertTrue(any("unsupported staged frequency" in error for error in errors))
        self.assertTrue(any("job_action must be" in error for error in errors))
        self.assertTrue(any("report_job_id is required" in error for error in errors))

    def test_counts_busy_and_scope_failures_are_blocking(self) -> None:
        counts_run = extracted_run(
            1_000_000, log=valid_log(1_000_000, counts="FAILED")
        )
        errors, _ = validate_run(counts_run)
        self.assertIn("map_counts_pass must be true", errors)

        busy_diagnostic = valid_diagnostic(1_000_000)
        for field in (
            "pon_busy_seen",
            "drf_busy_seen",
            "pof_busy_seen",
            "post_psr_busy_seen",
        ):
            busy_diagnostic[field] = False
        busy_run = extracted_run(
            1_000_000,
            log=valid_log(1_000_000, busy_seen=0),
            diagnostic=busy_diagnostic,
        )
        errors, _ = validate_run(busy_run)
        self.assertIn("drf_busy_seen must be true", errors)

        scope_run = extracted_run(1_000_000)
        scope_run["scope_evidence_bytes"] = 0
        errors, _ = validate_run(scope_run)
        self.assertIn("scope_evidence_bytes must be a positive integer", errors)

        hot_run = extracted_run(1_000_000)
        hot_run["max_temperature_c"] = 61.0
        errors, _ = validate_run(hot_run)
        self.assertTrue(any("must not exceed 60 C" in error for error in errors))

    def test_bad_job_timestamps_and_identity_are_blocking(self) -> None:
        run = extracted_run(1_000_000)
        run["job_finished_at_ms"] = run["job_started_at_ms"]
        errors, _ = validate_run(run)
        self.assertTrue(any("job duration" in error for error in errors))

        run = extracted_run(1_000_000)
        run["serial_job_finish_id"] += 1
        errors, _ = validate_run(run)
        self.assertIn("serial finish job_id mismatch", errors)

        run = extracted_run(1_000_000)
        run["job_finished_at_ms"] += 1
        errors, _ = validate_run(run)
        self.assertIn("observation does not match observation_canonical_sha256", errors)

    def test_u32_timestamp_wrap_is_supported(self) -> None:
        run = extracted_run(1_000_000)
        total_ms = run["total_ms"]
        run["job_queued_at_ms"] = 0xFFFFFF00
        run["job_started_at_ms"] = 0xFFFFFF10
        run["job_finished_at_ms"] = (run["job_started_at_ms"] + total_ms + 50) & 0xFFFFFFFF
        run["report_job_queued_at_ms"] = run["job_queued_at_ms"]
        run["report_job_started_at_ms"] = run["job_started_at_ms"]
        run["report_job_finished_at_ms"] = run["job_finished_at_ms"]
        rebind_observation(run)
        errors, _ = validate_run(run)
        self.assertEqual(errors, [])

    def test_nonfinite_or_incomplete_recorded_attempt_is_fail_not_pending(self) -> None:
        document = build_plan()
        document["runs"][0]["observation_recorded"] = True
        document["runs"][0]["supply_voltage_v"] = float("nan")
        report = analyze_document(document)
        self.assertEqual(report["results"][0]["status"], "FAIL")
        self.assertEqual(report["overall"], "FAIL")
        self.assertTrue(
            any("supply_voltage_v must be finite" in error for error in report["results"][0]["errors"])
        )

        document = build_plan()
        document["runs"][0]["unexpected_evidence"] = "not blank"
        report = analyze_document(document)
        self.assertEqual(report["results"][0]["status"], "FAIL")

    def test_huge_integers_fail_without_overflowing_validation(self) -> None:
        huge = 10**1_000
        for field in ("power_off_s", "measured_sclk_hz", "cs1_upload_ms"):
            with self.subTest(field=field):
                run = extracted_run(1_000_000)
                run[field] = huge
                if field == "cs1_upload_ms":
                    run["report_cs1_upload_ms"] = huge
                errors, _ = validate_run(run)
                self.assertTrue(errors)

        with self.assertRaisesRegex(RefreshAnalysisError, "outside the supported range"):
            theoretical_wire_time_ms(1, 10**1_000)

    def test_sclk_measurement_and_explicit_manual_failures_are_blocking(self) -> None:
        run = extracted_run(1_000_000)
        run["measured_sclk_hz"] = 1_100_000
        run["sclk_pass"] = False
        run["visual_pass"] = False
        errors, _ = validate_run(run)
        self.assertTrue(any("differs from requested" in error for error in errors))
        self.assertIn("sclk_pass must be true", errors)
        self.assertIn("visual_pass must be true", errors)


class SweepGateTests(unittest.TestCase):
    def test_complete_default_sweep_passes_with_distinguishable_uploads(self) -> None:
        document = build_plan()
        document["runs"] = [extracted_run(spi_hz) for spi_hz in DEFAULT_FREQUENCIES]
        report = analyze_document(document)
        self.assertEqual(report["overall"], "PASS")
        self.assertEqual(report["highest_passed_hz"], 10_000_000)
        self.assertFalse(report["waveform_fast_refresh_tested"])

    def test_fixed_1500ms_uploads_across_all_bands_cannot_pass(self) -> None:
        document = build_plan()
        document["runs"] = [extracted_run(spi_hz) for spi_hz in DEFAULT_FREQUENCIES]
        for run in document["runs"]:
            replace_timing(run, cs1_ms=1_500, cs2_ms=1_500)
        report = analyze_document(document)
        self.assertEqual(report["overall"], "FAIL")
        self.assertTrue(
            any("distinguishable improvement" in error for error in report["results"][1]["errors"])
        )

    def test_job_and_scope_captures_cannot_be_replayed_across_bands(self) -> None:
        document = build_plan()
        document["runs"] = [extracted_run(spi_hz) for spi_hz in DEFAULT_FREQUENCIES]
        reused_job_id = document["runs"][0]["job_id"]
        for field in (
            "job_id",
            "serial_job_start_id",
            "serial_job_finish_id",
            "report_job_id",
        ):
            document["runs"][1][field] = reused_job_id
        rebind_observation(document["runs"][1])
        result = analyze_document(document)["results"][1]
        self.assertIn("job_id was reused from a lower-frequency run", result["errors"])

        document = build_plan()
        document["runs"] = [extracted_run(spi_hz) for spi_hz in DEFAULT_FREQUENCIES]
        document["runs"][1]["scope_evidence_sha256"] = document["runs"][0][
            "scope_evidence_sha256"
        ]
        rebind_observation(document["runs"][1])
        result = analyze_document(document)["results"][1]
        self.assertIn("scope capture was reused from a lower-frequency run", result["errors"])

    def test_build_api_mapping_and_drf_must_remain_comparable(self) -> None:
        base = build_plan()
        base["runs"] = [extracted_run(spi_hz) for spi_hz in DEFAULT_FREQUENCIES]

        build_changed = copy.deepcopy(base)
        build_changed["runs"][1]["firmware_build_tag"] = "other-build"
        build_changed["runs"][1]["report_firmware_build_tag"] = "other-build"
        rebind_observation(build_changed["runs"][1])
        result = analyze_document(build_changed)["results"][1]
        self.assertIn("firmware_build_tag changed within the sweep", result["errors"])

        api_changed = copy.deepcopy(base)
        api_changed["runs"][1]["driver_api_version"] = "OTHER_API"
        api_changed["runs"][1]["report_driver_api_version"] = "OTHER_API"
        rebind_observation(api_changed["runs"][1])
        result = analyze_document(api_changed)["results"][1]
        self.assertIn("driver_api_version changed within the sweep", result["errors"])

        mapping_changed = copy.deepcopy(base)
        mapping_changed["runs"][1]["mapping"]["cs1_flip_x"] = True
        mapping_changed["runs"][1]["mapping_canonical_sha256"] = canonical_sha256(
            mapping_changed["runs"][1]["mapping"]
        )
        rebind_observation(mapping_changed["runs"][1])
        result = analyze_document(mapping_changed)["results"][1]
        self.assertIn("controller mapping changed within the sweep", result["errors"])

        drf_changed = copy.deepcopy(base)
        replace_timing(
            drf_changed["runs"][1],
            cs1_ms=drf_changed["runs"][1]["cs1_upload_ms"],
            cs2_ms=drf_changed["runs"][1]["cs2_upload_ms"],
            drf_ms=30_000,
        )
        result = analyze_document(drf_changed)["results"][1]
        self.assertIn("DRF time departed from the SPI-only baseline", result["errors"])

    def test_20mhz_requires_timing_evidence_after_lower_gates(self) -> None:
        document = build_plan(include_20mhz=True)
        document["runs"] = [extracted_run(spi_hz) for spi_hz in DEFAULT_FREQUENCIES]
        run_20mhz = extracted_run(OPTIONAL_FREQUENCY)
        run_20mhz["timing_pass"] = None
        run_20mhz["timing_evidence_sha256"] = None
        run_20mhz["timing_evidence_bytes"] = None
        document["runs"].append(run_20mhz)
        result = analyze_document(document)
        self.assertEqual(result["results"][-1]["status"], "FAIL")
        self.assertTrue(any("20 MHz requires" in error for error in result["results"][-1]["errors"]))

        document["runs"][-1] = extracted_run(OPTIONAL_FREQUENCY)
        self.assertEqual(analyze_document(document)["overall"], "PASS")

    def test_pending_lower_gate_blocks_later_recorded_run(self) -> None:
        document = build_plan()
        document["runs"][1] = extracted_run(2_000_000)
        report = analyze_document(document)
        self.assertEqual(report["overall"], "FAIL")
        self.assertIn("a lower-frequency gate has not passed", report["results"][1]["errors"])

    def test_document_shape_and_order_are_strict(self) -> None:
        document = build_plan()
        document["runs"][0], document["runs"][1] = document["runs"][1], document["runs"][0]
        with self.assertRaisesRegex(RefreshAnalysisError, "frequency order"):
            analyze_document(document)

        document = build_plan()
        document["runs"][0] = 123
        with self.assertRaisesRegex(RefreshAnalysisError, "every run"):
            analyze_document(document)

        document = build_plan()
        document["required_action"] = "map_orient_v1_slow"
        with self.assertRaisesRegex(RefreshAnalysisError, "required_action"):
            analyze_document(document)


if __name__ == "__main__":
    unittest.main()
