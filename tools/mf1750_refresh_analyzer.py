#!/usr/bin/env python3
"""Plan and validate offline MF-1750 SPI refresh sweeps.

This tool never opens a serial port, performs HTTP requests, or refreshes a
panel. It turns separately captured firmware reports and serial logs into a
machine-readable observation, then enforces the staged handoff gates.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


FIXTURE = "map-orient-v1"
EXPECTED_FULL_FNV1A = 0x9D04142D
EXPECTED_CS1_FNV1A = 0xF26832DD
EXPECTED_CS2_FNV1A = 0xFE199FF5
EXPECTED_HASHES = {
    "full_fnv1a": EXPECTED_FULL_FNV1A,
    "cs1_dtm_fnv1a": EXPECTED_CS1_FNV1A,
    "cs2_dtm_fnv1a": EXPECTED_CS2_FNV1A,
}
FRAME_BYTES = 307200
DEFAULT_FREQUENCIES = (1_000_000, 2_000_000, 4_000_000, 8_000_000, 10_000_000)
OPTIONAL_FREQUENCY = 20_000_000
MINIMUM_COLD_POWER_OFF_S = 10.0

_FULL_HASH_RE = re.compile(r"MAP_ORIENT_V1 frame FNV-1a:\s*(\d+)")
_CS1_RE = re.compile(
    r"CS1 upload done after\s+(\d+)\s+ms,\s+DTM FNV-1a=(\d+)", re.IGNORECASE
)
_CS2_RE = re.compile(
    r"CS2 upload done after\s+(\d+)\s+ms,\s+DTM FNV-1a=(\d+)", re.IGNORECASE
)
_DRF_RE = re.compile(r"EPD idle:\s*DRF after\s+(\d+)\s+ms", re.IGNORECASE)
_REFRESH_RE = re.compile(r"EPD full-frame cascade refresh:\s*(PASS|FAILED)", re.IGNORECASE)


class RefreshAnalysisError(ValueError):
    """Raised for malformed input documents or impossible observations."""


def theoretical_wire_time_ms(spi_hz: int, frame_bytes: int = FRAME_BYTES) -> float:
    """Return raw 8-bit transfer time, excluding CS/GPIO/software overhead."""

    if not isinstance(spi_hz, int) or isinstance(spi_hz, bool) or spi_hz <= 0:
        raise RefreshAnalysisError("spi_hz must be a positive integer")
    if not isinstance(frame_bytes, int) or frame_bytes < 0:
        raise RefreshAnalysisError("frame_bytes must be a non-negative integer")
    return frame_bytes * 8 * 1000.0 / spi_hz


def _blank_observation(spi_hz: int) -> Dict[str, Any]:
    return {
        "run_id": f"map-orient-v1-{spi_hz // 1_000_000}mhz",
        "spi_hz": spi_hz,
        "fixture": FIXTURE,
        "cold_start": None,
        "power_off_s": None,
        "full_fnv1a": None,
        "cs1_dtm_fnv1a": None,
        "cs2_dtm_fnv1a": None,
        "cs1_upload_ms": None,
        "cs2_upload_ms": None,
        "drf_ms": None,
        "total_ms": None,
        "sequence_ok": None,
        "wait_timeout": None,
        "visual_pass": None,
        "cv_pass": None,
        "thermal_pass": None,
        "notes": "",
    }


def build_plan(include_20mhz: bool = False) -> Dict[str, Any]:
    """Build a blank, ordered cold-start sweep plan."""

    frequencies = list(DEFAULT_FREQUENCIES)
    if include_20mhz:
        frequencies.append(OPTIONAL_FREQUENCY)
    return {
        "schema_version": 1,
        "kind": "mf1750-spi-refresh-sweep",
        "hardware_tested": False,
        "fixture": FIXTURE,
        "expected_hashes": dict(EXPECTED_HASHES),
        "minimum_cold_power_off_s": MINIMUM_COLD_POWER_OFF_S,
        "frequency_order_hz": frequencies,
        "runs": [_blank_observation(spi_hz) for spi_hz in frequencies],
    }


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise RefreshAnalysisError(f"cannot read {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise RefreshAnalysisError(f"invalid JSON in {path}: {error}") from error


def _write_json(data: Any, output: Optional[Path]) -> None:
    rendered = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if output is None:
        sys.stdout.write(rendered)
    else:
        output.write_text(rendered, encoding="utf-8")


def _last_match(pattern: re.Pattern[str], text: str) -> Optional[re.Match[str]]:
    matches = list(pattern.finditer(text))
    return matches[-1] if matches else None


def extract_observation(
    spi_hz: int,
    serial_log: str,
    diagnostic_report: Mapping[str, Any],
    *,
    cold_start: bool,
    power_off_s: float,
    visual_pass: bool,
    cv_pass: bool,
    thermal_pass: bool,
    notes: str = "",
) -> Dict[str, Any]:
    """Merge one captured serial log and diagnostic report without hardware I/O."""

    observation = _blank_observation(spi_hz)
    observation.update(
        {
            "cold_start": cold_start,
            "power_off_s": power_off_s,
            "visual_pass": visual_pass,
            "cv_pass": cv_pass,
            "thermal_pass": thermal_pass,
            "notes": notes,
        }
    )

    full_match = _last_match(_FULL_HASH_RE, serial_log)
    cs1_match = _last_match(_CS1_RE, serial_log)
    cs2_match = _last_match(_CS2_RE, serial_log)
    drf_match = _last_match(_DRF_RE, serial_log)
    refresh_match = _last_match(_REFRESH_RE, serial_log)

    observation["full_fnv1a"] = (
        int(full_match.group(1)) if full_match else diagnostic_report.get("input_fnv1a")
    )
    if cs1_match:
        observation["cs1_upload_ms"] = int(cs1_match.group(1))
        observation["cs1_dtm_fnv1a"] = int(cs1_match.group(2))
    else:
        observation["cs1_upload_ms"] = diagnostic_report.get("cs1_upload_ms")
        observation["cs1_dtm_fnv1a"] = diagnostic_report.get("cs1_dtm_fnv1a")
    if cs2_match:
        observation["cs2_upload_ms"] = int(cs2_match.group(1))
        observation["cs2_dtm_fnv1a"] = int(cs2_match.group(2))
    else:
        observation["cs2_upload_ms"] = diagnostic_report.get("cs2_upload_ms")
        observation["cs2_dtm_fnv1a"] = diagnostic_report.get("cs2_dtm_fnv1a")
    observation["drf_ms"] = int(drf_match.group(1)) if drf_match else None
    observation["total_ms"] = diagnostic_report.get("total_ms")
    observation["sequence_ok"] = diagnostic_report.get("sequence_ok")
    if observation["sequence_ok"] is None and refresh_match:
        observation["sequence_ok"] = refresh_match.group(1).upper() == "PASS"
    observation["wait_timeout"] = diagnostic_report.get("wait_timeout")
    if observation["wait_timeout"] is None:
        observation["wait_timeout"] = "busy timeout" in serial_log.lower()
    report_spi_hz = diagnostic_report.get("spi_hz")
    if report_spi_hz is not None and report_spi_hz != spi_hz:
        raise RefreshAnalysisError(
            f"diagnostic report spi_hz={report_spi_hz} does not match requested {spi_hz}"
        )
    return observation


_COMPLETION_FIELDS = (
    "cold_start",
    "power_off_s",
    "full_fnv1a",
    "cs1_dtm_fnv1a",
    "cs2_dtm_fnv1a",
    "cs1_upload_ms",
    "cs2_upload_ms",
    "drf_ms",
    "total_ms",
    "sequence_ok",
    "wait_timeout",
    "visual_pass",
    "cv_pass",
    "thermal_pass",
)


def _is_complete(run: Mapping[str, Any]) -> bool:
    return all(run.get(field) is not None for field in _COMPLETION_FIELDS)


def validate_run(run: Mapping[str, Any]) -> Tuple[List[str], List[str]]:
    """Return ``(errors, warnings)`` for one complete observation."""

    errors: List[str] = []
    warnings: List[str] = []
    spi_hz = run.get("spi_hz")
    if spi_hz not in DEFAULT_FREQUENCIES + (OPTIONAL_FREQUENCY,):
        errors.append(f"unsupported staged frequency: {spi_hz!r}")
        return errors, warnings
    if run.get("fixture") != FIXTURE:
        errors.append(f"fixture must be {FIXTURE!r}")
    if run.get("cold_start") is not True:
        errors.append("cold_start must be true")
    power_off_s = run.get("power_off_s")
    if not isinstance(power_off_s, (int, float)) or isinstance(power_off_s, bool):
        errors.append("power_off_s must be numeric")
    elif power_off_s < MINIMUM_COLD_POWER_OFF_S:
        errors.append(f"power_off_s must be at least {MINIMUM_COLD_POWER_OFF_S:g}")

    for field, expected in EXPECTED_HASHES.items():
        if run.get(field) != expected:
            errors.append(f"{field}={run.get(field)!r}; expected {expected}")
    for field in ("cs1_upload_ms", "cs2_upload_ms", "drf_ms", "total_ms"):
        value = run.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            errors.append(f"{field} must be a positive number")
    for field in ("sequence_ok", "visual_pass", "cv_pass", "thermal_pass"):
        if run.get(field) is not True:
            errors.append(f"{field} must be true")
    if run.get("wait_timeout") is not False:
        errors.append("wait_timeout must be false")

    cs1_ms = run.get("cs1_upload_ms")
    cs2_ms = run.get("cs2_upload_ms")
    total_ms = run.get("total_ms")
    if all(isinstance(value, (int, float)) for value in (cs1_ms, cs2_ms, total_ms)):
        if total_ms < cs1_ms + cs2_ms:
            errors.append("total_ms cannot be shorter than the two uploads")
    if isinstance(cs1_ms, (int, float)) and isinstance(cs2_ms, (int, float)):
        imbalance = abs(cs1_ms - cs2_ms) / max(cs1_ms, cs2_ms)
        if imbalance > 0.20:
            warnings.append(f"CS upload imbalance is {imbalance:.1%}; inspect wiring/timing")
        raw_half_ms = theoretical_wire_time_ms(spi_hz, FRAME_BYTES // 2)
        if min(cs1_ms, cs2_ms) + 1 < raw_half_ms:
            warnings.append(
                "reported upload is below raw wire time; verify timer scope and spi_hz"
            )
    return errors, warnings


def analyze_document(document: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate ordered sweep gates and return a machine-readable summary."""

    if document.get("schema_version") != 1 or document.get("kind") != "mf1750-spi-refresh-sweep":
        raise RefreshAnalysisError("not an MF-1750 SPI refresh sweep schema version 1 document")
    runs = document.get("runs")
    if not isinstance(runs, list) or not runs:
        raise RefreshAnalysisError("runs must be a non-empty list")

    frequencies = [run.get("spi_hz") for run in runs if isinstance(run, Mapping)]
    expected_order = list(DEFAULT_FREQUENCIES)
    if OPTIONAL_FREQUENCY in frequencies:
        expected_order.append(OPTIONAL_FREQUENCY)
    if frequencies != expected_order:
        raise RefreshAnalysisError(
            f"frequency order must be {expected_order}; got {frequencies}"
        )

    results: List[Dict[str, Any]] = []
    all_lower_passed = True
    highest_passed_hz: Optional[int] = None
    next_frequency_hz: Optional[int] = None
    for run in runs:
        spi_hz = run["spi_hz"]
        complete = _is_complete(run)
        errors: List[str] = []
        warnings: List[str] = []
        if not complete:
            status = "PENDING"
            if next_frequency_hz is None and all_lower_passed:
                next_frequency_hz = spi_hz
            all_lower_passed = False
        else:
            errors, warnings = validate_run(run)
            if not all_lower_passed:
                errors.insert(0, "a lower-frequency gate has not passed")
            if spi_hz == OPTIONAL_FREQUENCY and highest_passed_hz != DEFAULT_FREQUENCIES[-1]:
                errors.insert(0, "20 MHz is locked until 1/2/4/8/10 MHz all pass")
            status = "PASS" if not errors else "FAIL"
            if status == "PASS":
                highest_passed_hz = spi_hz
            else:
                all_lower_passed = False
        results.append(
            {
                "run_id": run.get("run_id"),
                "spi_hz": spi_hz,
                "status": status,
                "theoretical_wire_ms": round(theoretical_wire_time_ms(spi_hz), 3),
                "measured_upload_ms": (
                    run.get("cs1_upload_ms", 0) + run.get("cs2_upload_ms", 0)
                    if complete
                    else None
                ),
                "drf_ms": run.get("drf_ms") if complete else None,
                "total_ms": run.get("total_ms") if complete else None,
                "errors": errors,
                "warnings": warnings,
            }
        )

    statuses = [result["status"] for result in results]
    if "FAIL" in statuses:
        overall = "FAIL"
    elif "PENDING" in statuses:
        overall = "INCOMPLETE"
    else:
        overall = "PASS"
    return {
        "schema_version": 1,
        "overall": overall,
        "hardware_tested": bool(highest_passed_hz),
        "highest_passed_hz": highest_passed_hz,
        "next_frequency_hz": next_frequency_hz,
        "waveform_fast_refresh_tested": False,
        "results": results,
    }


def _replace_run(document: Mapping[str, Any], observation: Mapping[str, Any]) -> Dict[str, Any]:
    updated = copy.deepcopy(document)
    matches = [run for run in updated.get("runs", []) if run.get("spi_hz") == observation["spi_hz"]]
    if len(matches) != 1:
        raise RefreshAnalysisError(
            f"plan must contain exactly one run for spi_hz={observation['spi_hz']}"
        )
    matches[0].update(observation)
    return updated


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="generate a blank staged sweep plan")
    plan_parser.add_argument("--include-20mhz", action="store_true")
    plan_parser.add_argument("--output", type=Path)

    extract_parser = subparsers.add_parser(
        "extract", help="merge an offline serial log and diagnostic report into a plan"
    )
    extract_parser.add_argument("plan", type=Path)
    extract_parser.add_argument("--serial-log", type=Path, required=True)
    extract_parser.add_argument("--report", type=Path, required=True)
    extract_parser.add_argument("--spi-hz", type=int, required=True)
    extract_parser.add_argument("--cold-start", action="store_true", required=True)
    extract_parser.add_argument("--power-off-s", type=float, required=True)
    extract_parser.add_argument("--visual-pass", action="store_true", required=True)
    extract_parser.add_argument("--cv-pass", action="store_true", required=True)
    extract_parser.add_argument("--thermal-pass", action="store_true", required=True)
    extract_parser.add_argument("--notes", default="")
    extract_parser.add_argument("--output", type=Path)

    analyze_parser = subparsers.add_parser("analyze", help="validate a populated sweep plan")
    analyze_parser.add_argument("input", type=Path)
    analyze_parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "plan":
            _write_json(build_plan(args.include_20mhz), args.output)
            return 0
        if args.command == "extract":
            document = _load_json(args.plan)
            report = _load_json(args.report)
            if not isinstance(report, Mapping):
                raise RefreshAnalysisError("diagnostic report must be a JSON object")
            try:
                serial_log = args.serial_log.read_text(encoding="utf-8", errors="replace")
            except OSError as error:
                raise RefreshAnalysisError(f"cannot read {args.serial_log}: {error}") from error
            observation = extract_observation(
                args.spi_hz,
                serial_log,
                report,
                cold_start=args.cold_start,
                power_off_s=args.power_off_s,
                visual_pass=args.visual_pass,
                cv_pass=args.cv_pass,
                thermal_pass=args.thermal_pass,
                notes=args.notes,
            )
            _write_json(_replace_run(document, observation), args.output)
            return 0
        if args.command == "analyze":
            report = analyze_document(_load_json(args.input))
            _write_json(report, args.output)
            return {"PASS": 0, "INCOMPLETE": 2, "FAIL": 1}[report["overall"]]
    except RefreshAnalysisError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())

