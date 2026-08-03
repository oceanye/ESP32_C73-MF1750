from __future__ import annotations

import copy
import unittest

from tools.mf1750_refresh_analyzer import (
    DEFAULT_FREQUENCIES,
    EXPECTED_CS1_FNV1A,
    EXPECTED_CS2_FNV1A,
    EXPECTED_FULL_FNV1A,
    OPTIONAL_FREQUENCY,
    RefreshAnalysisError,
    analyze_document,
    build_plan,
    extract_observation,
    theoretical_wire_time_ms,
    validate_run,
)


def completed_run(spi_hz: int) -> dict:
    return {
        "run_id": f"run-{spi_hz}",
        "spi_hz": spi_hz,
        "fixture": "map-orient-v1",
        "cold_start": True,
        "power_off_s": 10.0,
        "full_fnv1a": EXPECTED_FULL_FNV1A,
        "cs1_dtm_fnv1a": EXPECTED_CS1_FNV1A,
        "cs2_dtm_fnv1a": EXPECTED_CS2_FNV1A,
        "cs1_upload_ms": max(20, round(theoretical_wire_time_ms(spi_hz) / 2 + 10)),
        "cs2_upload_ms": max(20, round(theoretical_wire_time_ms(spi_hz) / 2 + 10)),
        "drf_ms": 21700,
        "total_ms": 31000,
        "sequence_ok": True,
        "wait_timeout": False,
        "visual_pass": True,
        "cv_pass": True,
        "thermal_pass": True,
        "notes": "test fixture",
    }


class PlanTests(unittest.TestCase):
    def test_default_plan_stops_at_10mhz(self) -> None:
        plan = build_plan()
        self.assertEqual(plan["frequency_order_hz"], list(DEFAULT_FREQUENCIES))
        self.assertNotIn(OPTIONAL_FREQUENCY, plan["frequency_order_hz"])
        self.assertTrue(all(run["cold_start"] is None for run in plan["runs"]))

    def test_optional_plan_places_20mhz_last(self) -> None:
        plan = build_plan(include_20mhz=True)
        self.assertEqual(plan["frequency_order_hz"][-1], OPTIONAL_FREQUENCY)

    def test_wire_time_budget(self) -> None:
        self.assertAlmostEqual(theoretical_wire_time_ms(1_000_000), 2457.6)
        self.assertAlmostEqual(theoretical_wire_time_ms(10_000_000), 245.76)
        self.assertAlmostEqual(theoretical_wire_time_ms(20_000_000), 122.88)
        with self.assertRaises(RefreshAnalysisError):
            theoretical_wire_time_ms(0)


class ExtractionTests(unittest.TestCase):
    def test_extracts_hashes_and_stage_timings(self) -> None:
        log = """
MAP_ORIENT_V1 frame FNV-1a: 2634290221 (expected 2634290221), counts=PASS
EPD full frame CS1 upload done after 1500 ms, DTM FNV-1a=4066915037
EPD full frame CS2 upload done after 1490 ms, DTM FNV-1a=4263092213
EPD idle: DRF after 21701 ms, busy_seen=1
EPD full-frame cascade refresh: PASS
"""
        diagnostic = {
            "spi_hz": 1_000_000,
            "sequence_ok": True,
            "wait_timeout": False,
            "total_ms": 31500,
        }
        observation = extract_observation(
            1_000_000,
            log,
            diagnostic,
            cold_start=True,
            power_off_s=12,
            visual_pass=True,
            cv_pass=True,
            thermal_pass=True,
        )
        self.assertEqual(observation["full_fnv1a"], EXPECTED_FULL_FNV1A)
        self.assertEqual(observation["cs1_dtm_fnv1a"], EXPECTED_CS1_FNV1A)
        self.assertEqual(observation["cs2_dtm_fnv1a"], EXPECTED_CS2_FNV1A)
        self.assertEqual(observation["drf_ms"], 21701)
        self.assertEqual(observation["cs1_upload_ms"], 1500)

    def test_rejects_report_frequency_mismatch(self) -> None:
        with self.assertRaisesRegex(RefreshAnalysisError, "does not match"):
            extract_observation(
                1_000_000,
                "",
                {"spi_hz": 2_000_000},
                cold_start=True,
                power_off_s=10,
                visual_pass=True,
                cv_pass=True,
                thermal_pass=True,
            )


class GateTests(unittest.TestCase):
    def test_one_valid_run_has_no_errors(self) -> None:
        errors, warnings = validate_run(completed_run(1_000_000))
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_hash_visual_and_cold_start_failures_are_blocking(self) -> None:
        run = completed_run(1_000_000)
        run["cs2_dtm_fnv1a"] ^= 1
        run["visual_pass"] = False
        run["cold_start"] = False
        errors, _ = validate_run(run)
        self.assertTrue(any("cs2_dtm_fnv1a" in error for error in errors))
        self.assertIn("visual_pass must be true", errors)
        self.assertIn("cold_start must be true", errors)

    def test_complete_default_sweep_passes(self) -> None:
        document = build_plan()
        document["runs"] = [completed_run(spi_hz) for spi_hz in DEFAULT_FREQUENCIES]
        report = analyze_document(document)
        self.assertEqual(report["overall"], "PASS")
        self.assertEqual(report["highest_passed_hz"], 10_000_000)
        self.assertFalse(report["waveform_fast_refresh_tested"])

    def test_pending_lower_frequency_blocks_later_completed_run(self) -> None:
        document = build_plan()
        document["runs"][1] = completed_run(2_000_000)
        report = analyze_document(document)
        self.assertEqual(report["overall"], "FAIL")
        self.assertIn("a lower-frequency gate has not passed", report["results"][1]["errors"])

    def test_20mhz_is_locked_until_lower_sweep_passes(self) -> None:
        document = build_plan(include_20mhz=True)
        document["runs"][-1] = completed_run(OPTIONAL_FREQUENCY)
        report = analyze_document(document)
        self.assertEqual(report["results"][-1]["status"], "FAIL")
        self.assertTrue(any("20 MHz is locked" in error for error in report["results"][-1]["errors"]))

    def test_frequency_reordering_is_rejected(self) -> None:
        document = build_plan()
        document["runs"][0], document["runs"][1] = document["runs"][1], document["runs"][0]
        with self.assertRaisesRegex(RefreshAnalysisError, "frequency order"):
            analyze_document(document)


if __name__ == "__main__":
    unittest.main()

