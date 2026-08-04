#!/usr/bin/env python3
"""Plan and validate offline MF-1750 SPI refresh sweeps.

This tool never opens a serial port, performs HTTP requests, or refreshes a
panel.  Schema v2 deliberately describes a *future* evidence-capable firmware
contract.  The current ``map_orient_v1_slow`` (100 kHz) action is not accepted
as evidence for the 1/2/4/8/10 MHz sweep.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


FIXTURE = "map-orient-v1"
SWEEP_ACTION = "map_orient_v1_sweep"
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
MAXIMUM_RECORDED_POWER_OFF_S = 604_800.0
SCLK_RELATIVE_TOLERANCE = 0.05
MIN_UPLOAD_IMPROVEMENT_FRACTION = 0.02
MIN_UPLOAD_IMPROVEMENT_MS = 5.0
DRF_MIN_MS = 10_000.0
DRF_MAX_MS = 60_000.0
DRF_BASELINE_RELATIVE_TOLERANCE = 0.20
DRF_BASELINE_ABSOLUTE_TOLERANCE_MS = 2_000.0
MAX_QUEUE_TO_START_MS = 10_000
MAX_JOB_DURATION_MS = 120_000
MAX_JOB_OVERHEAD_MS = 5_000
MAX_SAFE_TEMPERATURE_C = 60.0
UINT32_MASK = 0xFFFFFFFF

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_MAP_RE = re.compile(
    r"MAP_ORIENT_V1 frame FNV-1a:\s*(\d+)\s*"
    r"\(expected\s+(\d+)\),\s*counts=(PASS|FAILED)",
    re.IGNORECASE,
)
_CS1_RE = re.compile(
    r"CS1 upload done after\s+(\d+)\s+ms,\s+DTM FNV-1a=(\d+)", re.IGNORECASE
)
_CS2_RE = re.compile(
    r"CS2 upload done after\s+(\d+)\s+ms,\s+DTM FNV-1a=(\d+)", re.IGNORECASE
)


def _stage_re(stage: str) -> re.Pattern[str]:
    return re.compile(
        rf"EPD idle:\s*{re.escape(stage)} after\s+(\d+)\s+ms,\s*busy_seen=([01])",
        re.IGNORECASE,
    )


_PON_RE = _stage_re("PON")
_DRF_RE = _stage_re("DRF")
_POF_RE = _stage_re("POF")
_POST_PSR_RE = _stage_re("post-display PSR")
_REFRESH_RE = re.compile(
    r"EPD full-frame cascade refresh:\s*(PASS|FAILED)", re.IGNORECASE
)
_JOB_START_RE = re.compile(
    r"Running EPD job\s+(\d+)\s+action\s+(\d+)\s+\(([^)]+)\)",
    re.IGNORECASE,
)
_JOB_FINISH_RE = re.compile(
    r"EPD job\s+(\d+)\s+finished:\s*state=([a-z_]+)\s+"
    r"result_known=([01])\s+result=([01])",
    re.IGNORECASE,
)

_MAPPING_KEYS = (
    "cs1_source_half",
    "cs1_flip_x",
    "cs1_flip_y",
    "cs1_nibble_swap",
    "cs2_source_half",
    "cs2_flip_x",
    "cs2_flip_y",
    "cs2_nibble_swap",
)


class RefreshAnalysisError(ValueError):
    """Raised for malformed capture files or an ambiguous observation."""


def theoretical_wire_time_ms(spi_hz: int, frame_bytes: int = FRAME_BYTES) -> float:
    """Return raw 8-bit transfer time, excluding CS/GPIO/software overhead."""

    if not isinstance(spi_hz, int) or isinstance(spi_hz, bool) or spi_hz <= 0:
        raise RefreshAnalysisError("spi_hz must be a positive integer")
    if not isinstance(frame_bytes, int) or isinstance(frame_bytes, bool) or frame_bytes < 0:
        raise RefreshAnalysisError("frame_bytes must be a non-negative integer")
    try:
        return frame_bytes * 8 * 1000.0 / spi_hz
    except OverflowError as error:
        raise RefreshAnalysisError("wire-time inputs are outside the supported range") from error


def _blank_observation(spi_hz: int) -> Dict[str, Any]:
    return {
        "observation_recorded": False,
        "run_id": f"map-orient-v1-{spi_hz // 1_000_000}mhz",
        "spi_hz": spi_hz,
        "fixture": FIXTURE,
        "firmware_build_tag": None,
        "driver_api_version": None,
        "report_schema_version": None,
        "report_operation_id": None,
        "report_job_operation_id": None,
        "report_busy_assertion_missing": None,
        "report_busy_missing_stage": None,
        "report_firmware_build_tag": None,
        "report_driver_api_version": None,
        "version_report_raw_sha256": None,
        "serial_log_raw_sha256": None,
        "diagnostic_report_canonical_sha256": None,
        "job_report_canonical_sha256": None,
        "mapping_canonical_sha256": None,
        "observation_canonical_sha256": None,
        "scope_evidence_sha256": None,
        "scope_evidence_bytes": None,
        "timing_evidence_sha256": None,
        "timing_evidence_bytes": None,
        "job_id": None,
        "job_action": None,
        "job_state": None,
        "job_result": None,
        "job_frame_fnv1a": None,
        "job_queued_at_ms": None,
        "job_started_at_ms": None,
        "job_finished_at_ms": None,
        "serial_job_start_id": None,
        "serial_job_action_code": None,
        "serial_job_action": None,
        "serial_job_finish_id": None,
        "serial_job_finish_state": None,
        "serial_job_result_known": None,
        "serial_job_result": None,
        "report_job_id": None,
        "report_job_action": None,
        "report_job_state": None,
        "report_job_result": None,
        "report_job_queued_at_ms": None,
        "report_job_started_at_ms": None,
        "report_job_finished_at_ms": None,
        "report_spi_hz": None,
        "cold_start": None,
        "power_off_s": None,
        "supply_voltage_v": None,
        "current_limit_a": None,
        "peak_current_a": None,
        "max_temperature_c": None,
        "measured_sclk_hz": None,
        "sclk_pass": None,
        "timing_pass": None,
        "full_fnv1a": None,
        "serial_expected_fnv1a": None,
        "map_counts_pass": None,
        "cs1_dtm_fnv1a": None,
        "cs2_dtm_fnv1a": None,
        "cs1_upload_ms": None,
        "cs2_upload_ms": None,
        "report_input_fnv1a": None,
        "report_cs1_dtm_fnv1a": None,
        "report_cs2_dtm_fnv1a": None,
        "report_cs1_upload_ms": None,
        "report_cs2_upload_ms": None,
        "pon_ms": None,
        "pon_busy_seen": None,
        "drf_ms": None,
        "drf_busy_seen": None,
        "pof_ms": None,
        "pof_busy_seen": None,
        "post_psr_ms": None,
        "post_psr_busy_seen": None,
        "report_pon_ms": None,
        "report_pon_busy_seen": None,
        "report_drf_ms": None,
        "report_drf_busy_seen": None,
        "report_pof_ms": None,
        "report_pof_busy_seen": None,
        "report_post_psr_ms": None,
        "report_post_psr_busy_seen": None,
        "total_ms": None,
        "report_last_wait_ms": None,
        "report_valid": None,
        "report_running": None,
        "mapping_applied": None,
        "mapping": None,
        "sequence_ok": None,
        "wait_timeout": None,
        "last_wait_stage": None,
        "timeout_stage": None,
        "serial_refresh_pass": None,
        "visual_pass": None,
        "cv_pass": None,
        "thermal_pass": None,
        "acoustic_pass": None,
        "notes": "",
    }


def build_plan(include_20mhz: bool = False) -> Dict[str, Any]:
    """Build a blank, ordered sweep plan; blank rows are the only PENDING rows."""

    frequencies = list(DEFAULT_FREQUENCIES)
    if include_20mhz:
        frequencies.append(OPTIONAL_FREQUENCY)
    return {
        "schema_version": 2,
        "kind": "mf1750-spi-refresh-sweep",
        "hardware_tested": False,
        "fixture": FIXTURE,
        "required_action": SWEEP_ACTION,
        "expected_hashes": dict(EXPECTED_HASHES),
        "minimum_cold_power_off_s": MINIMUM_COLD_POWER_OFF_S,
        "frequency_order_hz": frequencies,
        "runs": [_blank_observation(spi_hz) for spi_hz in frequencies],
    }


def _load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError) as error:
        raise RefreshAnalysisError(f"cannot read {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise RefreshAnalysisError(f"invalid JSON in {path}: {error}") from error
    except ValueError as error:
        raise RefreshAnalysisError(f"unsupported JSON value in {path}: {error}") from error


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise RefreshAnalysisError(f"cannot read {label} {path}: {error}") from error


def _write_json(data: Any, output: Optional[Path]) -> None:
    try:
        rendered = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if output is None:
            sys.stdout.write(rendered)
        else:
            output.write_text(rendered, encoding="utf-8")
    except (OSError, TypeError, ValueError) as error:
        raise RefreshAnalysisError(f"cannot serialize/write {output}: {error}") from error


def _normalized_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_sha256(document: Any, label: str) -> str:
    try:
        encoded = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise RefreshAnalysisError(f"{label} is not canonical JSON: {error}") from error
    return hashlib.sha256(encoded).hexdigest()


def _observation_sha256(observation: Mapping[str, Any]) -> str:
    payload = dict(observation)
    payload.pop("observation_canonical_sha256", None)
    return _canonical_json_sha256(payload, "observation")


def _reject_duplicate_keys(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    document: Dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise RefreshAnalysisError(f"duplicate JSON key: {key!r}")
        document[key] = value
    return document


def _reject_json_constant(value: str) -> Any:
    raise RefreshAnalysisError(f"non-finite JSON number is not allowed: {value}")


def _decode_text_capture(value: Any, label: str) -> Tuple[str, bytes]:
    if isinstance(value, str):
        try:
            raw = value.encode("utf-8")
        except UnicodeError as error:
            raise RefreshAnalysisError(f"{label} is not valid Unicode: {error}") from error
        text = value
    elif isinstance(value, bytes):
        raw = value
        try:
            text = value.decode("utf-8-sig")
        except UnicodeError as error:
            raise RefreshAnalysisError(f"{label} is not valid UTF-8: {error}") from error
    else:
        raise RefreshAnalysisError(f"{label} must be text or raw bytes")
    return text, raw


def _parse_version_report(text: str) -> Tuple[str, str]:
    normalized = _normalized_text(text).strip()
    if not normalized:
        raise RefreshAnalysisError("version report is empty")
    try:
        document = json.loads(
            normalized,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError:
        document = None
    except ValueError as error:
        raise RefreshAnalysisError(f"version report contains an unsupported value: {error}") from error
    if isinstance(document, Mapping):
        build_tag = document.get("firmware_build_tag")
        api_version = document.get("driver_api_version")
    else:
        lines = [line.strip() for line in normalized.splitlines() if line.strip()]
        build_tag = lines[0] if lines else None
        api_version = None
        for line in lines[1:]:
            if line.lower().startswith("driver api:"):
                api_version = line.split(":", 1)[1].strip()
                break
    if not isinstance(build_tag, str) or not build_tag.strip():
        raise RefreshAnalysisError("version report lacks firmware_build_tag")
    if not isinstance(api_version, str) or not api_version.strip():
        raise RefreshAnalysisError("version report lacks driver_api_version")
    return build_tag.strip(), api_version.strip()


def _single_match(
    pattern: re.Pattern[str], text: str, label: str
) -> Optional[re.Match[str]]:
    matches = list(pattern.finditer(text))
    if len(matches) > 1:
        raise RefreshAnalysisError(
            f"serial log contains {len(matches)} {label} records; capture exactly one run"
        )
    return matches[0] if matches else None


def _crosscheck(label: str, left: Any, right: Any) -> None:
    if left is not None and right is not None and left != right:
        raise RefreshAnalysisError(
            f"evidence mismatch for {label}: {left!r} != {right!r}"
        )


def _match_int(match: Optional[re.Match[str]], group: int) -> Optional[int]:
    return int(match.group(group)) if match is not None else None


def _match_bool(match: Optional[re.Match[str]], group: int) -> Optional[bool]:
    return bool(int(match.group(group))) if match is not None else None


def extract_observation(
    spi_hz: int,
    serial_log: str | bytes,
    diagnostic_report: Mapping[str, Any],
    job_report: Mapping[str, Any],
    version_report: str | bytes,
    scope_evidence: bytes,
    *,
    cold_start: bool,
    power_off_s: float,
    supply_voltage_v: float,
    current_limit_a: float,
    peak_current_a: float,
    max_temperature_c: float,
    measured_sclk_hz: float,
    sclk_pass: bool,
    visual_pass: bool,
    cv_pass: bool,
    thermal_pass: bool,
    acoustic_pass: bool,
    timing_evidence: Optional[bytes] = None,
    timing_pass: Optional[bool] = None,
    notes: str = "",
) -> Dict[str, Any]:
    """Merge one run's captures without silently filling missing serial evidence.

    Missing markers remain ``None`` so that a recorded, truncated run becomes
    ``FAIL`` during analysis.  Duplicate markers or contradictory captures are
    rejected as ambiguous input.
    """

    if not isinstance(diagnostic_report, Mapping):
        raise RefreshAnalysisError("diagnostic report must be a JSON object")
    if not isinstance(job_report, Mapping):
        raise RefreshAnalysisError("job report must be a JSON object")
    if not isinstance(scope_evidence, bytes):
        raise RefreshAnalysisError("scope evidence must be bytes")
    if timing_evidence is not None and not isinstance(timing_evidence, bytes):
        raise RefreshAnalysisError("timing evidence must be bytes")

    serial_text, serial_raw = _decode_text_capture(serial_log, "serial capture")
    version_text, version_raw = _decode_text_capture(version_report, "version capture")
    firmware_build_tag, driver_api_version = _parse_version_report(version_text)
    report_operation_id = diagnostic_report.get("operation_id")
    if not _is_u32(report_operation_id) or report_operation_id == 0:
        raise RefreshAnalysisError(
            "diagnostic report operation_id must be a positive unsigned 32-bit integer"
        )
    report_job_operation_id = diagnostic_report.get("job_operation_id")
    if not _is_u32(report_job_operation_id) or report_job_operation_id == 0:
        raise RefreshAnalysisError(
            "diagnostic report job_operation_id must be a positive unsigned 32-bit integer"
        )
    if report_job_operation_id != report_operation_id:
        raise RefreshAnalysisError(
            "diagnostic report job_operation_id/operation_id mismatch"
        )
    report_busy_assertion_missing = diagnostic_report.get("busy_assertion_missing")
    if report_busy_assertion_missing is not False:
        raise RefreshAnalysisError(
            "diagnostic report busy_assertion_missing must be false"
        )
    report_busy_missing_stage = diagnostic_report.get("busy_missing_stage")
    if report_busy_missing_stage != "none":
        raise RefreshAnalysisError(
            "diagnostic report busy_missing_stage must be 'none'"
        )
    observation = _blank_observation(spi_hz)
    observation.update(
        {
            "observation_recorded": True,
            "firmware_build_tag": firmware_build_tag,
            "driver_api_version": driver_api_version,
            "report_schema_version": diagnostic_report.get("schema_version"),
            "report_operation_id": report_operation_id,
            "report_job_operation_id": report_job_operation_id,
            "report_busy_assertion_missing": report_busy_assertion_missing,
            "report_busy_missing_stage": report_busy_missing_stage,
            "report_firmware_build_tag": diagnostic_report.get("firmware_build_tag"),
            "report_driver_api_version": diagnostic_report.get("driver_api_version"),
            "version_report_raw_sha256": _bytes_sha256(version_raw),
            "serial_log_raw_sha256": _bytes_sha256(serial_raw),
            "diagnostic_report_canonical_sha256": _canonical_json_sha256(
                diagnostic_report, "diagnostic report"
            ),
            "job_report_canonical_sha256": _canonical_json_sha256(
                job_report, "job report"
            ),
            "mapping_canonical_sha256": _canonical_json_sha256(
                diagnostic_report.get("mapping"), "diagnostic mapping"
            ),
            "scope_evidence_sha256": _bytes_sha256(scope_evidence),
            "scope_evidence_bytes": len(scope_evidence),
            "timing_evidence_sha256": (
                _bytes_sha256(timing_evidence) if timing_evidence is not None else None
            ),
            "timing_evidence_bytes": (
                len(timing_evidence) if timing_evidence is not None else None
            ),
            "job_id": job_report.get("job_id"),
            "job_action": job_report.get("action"),
            "job_state": job_report.get("state"),
            "job_result": job_report.get("result"),
            "job_frame_fnv1a": job_report.get("frame_fnv1a"),
            "job_queued_at_ms": job_report.get("queued_at_ms"),
            "job_started_at_ms": job_report.get("started_at_ms"),
            "job_finished_at_ms": job_report.get("finished_at_ms"),
            "report_job_id": diagnostic_report.get("job_id"),
            "report_job_action": diagnostic_report.get("job_action"),
            "report_job_state": diagnostic_report.get("job_state"),
            "report_job_result": diagnostic_report.get("job_result"),
            "report_job_queued_at_ms": diagnostic_report.get("job_queued_at_ms"),
            "report_job_started_at_ms": diagnostic_report.get("job_started_at_ms"),
            "report_job_finished_at_ms": diagnostic_report.get("job_finished_at_ms"),
            "report_spi_hz": diagnostic_report.get("spi_hz"),
            "cold_start": cold_start,
            "power_off_s": power_off_s,
            "supply_voltage_v": supply_voltage_v,
            "current_limit_a": current_limit_a,
            "peak_current_a": peak_current_a,
            "max_temperature_c": max_temperature_c,
            "measured_sclk_hz": measured_sclk_hz,
            "sclk_pass": sclk_pass,
            "timing_pass": timing_pass,
            "report_input_fnv1a": diagnostic_report.get("input_fnv1a"),
            "report_cs1_dtm_fnv1a": diagnostic_report.get("cs1_dtm_fnv1a"),
            "report_cs2_dtm_fnv1a": diagnostic_report.get("cs2_dtm_fnv1a"),
            "report_cs1_upload_ms": diagnostic_report.get("cs1_upload_ms"),
            "report_cs2_upload_ms": diagnostic_report.get("cs2_upload_ms"),
            "report_pon_ms": diagnostic_report.get("pon_ms"),
            "report_pon_busy_seen": diagnostic_report.get("pon_busy_seen"),
            "report_drf_ms": diagnostic_report.get("drf_ms"),
            "report_drf_busy_seen": diagnostic_report.get("drf_busy_seen"),
            "report_pof_ms": diagnostic_report.get("pof_ms"),
            "report_pof_busy_seen": diagnostic_report.get("pof_busy_seen"),
            "report_post_psr_ms": diagnostic_report.get("post_psr_ms"),
            "report_post_psr_busy_seen": diagnostic_report.get("post_psr_busy_seen"),
            "total_ms": diagnostic_report.get("total_ms"),
            "report_last_wait_ms": diagnostic_report.get("last_wait_ms"),
            "report_valid": diagnostic_report.get("valid"),
            "report_running": diagnostic_report.get("running"),
            "mapping_applied": diagnostic_report.get("mapping_applied"),
            "mapping": copy.deepcopy(diagnostic_report.get("mapping")),
            "sequence_ok": diagnostic_report.get("sequence_ok"),
            "wait_timeout": diagnostic_report.get("wait_timeout"),
            "last_wait_stage": diagnostic_report.get("last_wait_stage"),
            "timeout_stage": diagnostic_report.get("timeout_stage"),
            "visual_pass": visual_pass,
            "cv_pass": cv_pass,
            "thermal_pass": thermal_pass,
            "acoustic_pass": acoustic_pass,
            "notes": notes,
        }
    )

    normalized_log = _normalized_text(serial_text)
    map_match = _single_match(_MAP_RE, normalized_log, "MAP/count")
    cs1_match = _single_match(_CS1_RE, normalized_log, "CS1 upload")
    cs2_match = _single_match(_CS2_RE, normalized_log, "CS2 upload")
    pon_match = _single_match(_PON_RE, normalized_log, "PON timing")
    drf_match = _single_match(_DRF_RE, normalized_log, "DRF timing")
    pof_match = _single_match(_POF_RE, normalized_log, "POF timing")
    post_psr_match = _single_match(
        _POST_PSR_RE, normalized_log, "post-display PSR timing"
    )
    refresh_match = _single_match(_REFRESH_RE, normalized_log, "refresh result")
    job_start_match = _single_match(_JOB_START_RE, normalized_log, "job start")
    job_finish_match = _single_match(_JOB_FINISH_RE, normalized_log, "job finish")

    ordered_markers = (
        ("job start", job_start_match),
        ("MAP/count", map_match),
        ("CS1 upload", cs1_match),
        ("CS2 upload", cs2_match),
        ("PON timing", pon_match),
        ("DRF timing", drf_match),
        ("POF timing", pof_match),
        ("post-display PSR timing", post_psr_match),
        ("refresh result", refresh_match),
        ("job finish", job_finish_match),
    )
    present_markers = [
        (label, match.start())
        for label, match in ordered_markers
        if match is not None
    ]
    for (left_label, left_position), (right_label, right_position) in zip(
        present_markers, present_markers[1:]
    ):
        if left_position >= right_position:
            raise RefreshAnalysisError(
                "serial markers are outside one ordered job boundary: "
                f"{left_label} must precede {right_label}"
            )

    observation.update(
        {
            "full_fnv1a": _match_int(map_match, 1),
            "serial_expected_fnv1a": _match_int(map_match, 2),
            "map_counts_pass": (
                map_match.group(3).upper() == "PASS" if map_match else None
            ),
            "cs1_upload_ms": _match_int(cs1_match, 1),
            "cs1_dtm_fnv1a": _match_int(cs1_match, 2),
            "cs2_upload_ms": _match_int(cs2_match, 1),
            "cs2_dtm_fnv1a": _match_int(cs2_match, 2),
            "pon_ms": _match_int(pon_match, 1),
            "pon_busy_seen": _match_bool(pon_match, 2),
            "drf_ms": _match_int(drf_match, 1),
            "drf_busy_seen": _match_bool(drf_match, 2),
            "pof_ms": _match_int(pof_match, 1),
            "pof_busy_seen": _match_bool(pof_match, 2),
            "post_psr_ms": _match_int(post_psr_match, 1),
            "post_psr_busy_seen": _match_bool(post_psr_match, 2),
            "serial_refresh_pass": (
                refresh_match.group(1).upper() == "PASS" if refresh_match else None
            ),
            "serial_job_start_id": _match_int(job_start_match, 1),
            "serial_job_action_code": _match_int(job_start_match, 2),
            "serial_job_action": (
                job_start_match.group(3) if job_start_match else None
            ),
            "serial_job_finish_id": _match_int(job_finish_match, 1),
            "serial_job_finish_state": (
                job_finish_match.group(2).lower() if job_finish_match else None
            ),
            "serial_job_result_known": _match_bool(job_finish_match, 3),
            "serial_job_result": _match_bool(job_finish_match, 4),
        }
    )

    # Contradictory complete fields mean that the capture set is ambiguous and
    # must not be written. Missing fields are retained and later become FAIL.
    for label, left, right in (
        ("version/report build tag", firmware_build_tag, observation["report_firmware_build_tag"]),
        ("version/report driver API", driver_api_version, observation["report_driver_api_version"]),
        ("job/report job_id", observation["job_id"], observation["report_job_id"]),
        ("job/report action", observation["job_action"], observation["report_job_action"]),
        ("job/report state", observation["job_state"], observation["report_job_state"]),
        ("job/report result", observation["job_result"], observation["report_job_result"]),
        ("job/report queued timestamp", observation["job_queued_at_ms"], observation["report_job_queued_at_ms"]),
        ("job/report started timestamp", observation["job_started_at_ms"], observation["report_job_started_at_ms"]),
        ("job/report finished timestamp", observation["job_finished_at_ms"], observation["report_job_finished_at_ms"]),
        ("serial/job start id", observation["serial_job_start_id"], observation["job_id"]),
        ("serial/job finish id", observation["serial_job_finish_id"], observation["job_id"]),
        ("serial/job action", observation["serial_job_action"], observation["job_action"]),
        ("serial/job finish state", observation["serial_job_finish_state"], observation["job_state"]),
        ("serial/job finish result", observation["serial_job_result"], observation["job_result"]),
        ("serial refresh/job result", observation["serial_refresh_pass"], observation["job_result"]),
        ("requested/report spi_hz", spi_hz, observation["report_spi_hz"]),
        ("serial/report input hash", observation["full_fnv1a"], observation["report_input_fnv1a"]),
        ("serial/job frame hash", observation["full_fnv1a"], observation["job_frame_fnv1a"]),
        ("serial/report CS1 hash", observation["cs1_dtm_fnv1a"], observation["report_cs1_dtm_fnv1a"]),
        ("serial/report CS2 hash", observation["cs2_dtm_fnv1a"], observation["report_cs2_dtm_fnv1a"]),
        ("serial/report CS1 upload", observation["cs1_upload_ms"], observation["report_cs1_upload_ms"]),
        ("serial/report CS2 upload", observation["cs2_upload_ms"], observation["report_cs2_upload_ms"]),
        ("serial/report PON wait", observation["pon_ms"], observation["report_pon_ms"]),
        ("serial/report PON busy", observation["pon_busy_seen"], observation["report_pon_busy_seen"]),
        ("serial/report DRF wait", observation["drf_ms"], observation["report_drf_ms"]),
        ("serial/report DRF busy", observation["drf_busy_seen"], observation["report_drf_busy_seen"]),
        ("serial/report POF wait", observation["pof_ms"], observation["report_pof_ms"]),
        ("serial/report POF busy", observation["pof_busy_seen"], observation["report_pof_busy_seen"]),
        ("serial/report post-PSR wait", observation["post_psr_ms"], observation["report_post_psr_ms"]),
        ("serial/report post-PSR busy", observation["post_psr_busy_seen"], observation["report_post_psr_busy_seen"]),
        ("serial/report sequence result", observation["serial_refresh_pass"], observation["sequence_ok"]),
        ("post-PSR/report last wait", observation["post_psr_ms"], observation["report_last_wait_ms"]),
    ):
        _crosscheck(label, left, right)
    observation["observation_canonical_sha256"] = _observation_sha256(observation)
    return observation


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value)


def _is_u32(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= UINT32_MASK


def _u32_elapsed(start: int, end: int) -> int:
    return (end - start) & UINT32_MASK


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _validate_mapping(mapping: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(mapping, Mapping):
        return ["mapping must be a JSON object"]
    missing = [key for key in _MAPPING_KEYS if key not in mapping]
    if missing:
        errors.append(f"mapping missing keys: {missing}")
        return errors
    for key in ("cs1_source_half", "cs2_source_half"):
        value = mapping.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value not in (0, 1):
            errors.append(f"mapping.{key} must be 0 or 1")
    if mapping.get("cs1_source_half") == mapping.get("cs2_source_half"):
        errors.append("mapping source halves must form a bijection")
    for key in _MAPPING_KEYS:
        if key.endswith(("flip_x", "flip_y", "nibble_swap")) and not isinstance(
            mapping.get(key), bool
        ):
            errors.append(f"mapping.{key} must be boolean")
    return errors


def _required_value(run: Mapping[str, Any], field: str, errors: List[str]) -> Any:
    value = run.get(field)
    if value is None:
        errors.append(f"{field} is required for a recorded observation")
    return value


def validate_run(run: Mapping[str, Any]) -> Tuple[List[str], List[str]]:
    """Return ``(errors, warnings)`` for one recorded observation."""

    errors: List[str] = []
    warnings: List[str] = []
    if not isinstance(run, Mapping):
        return ["run must be a JSON object"], warnings
    if run.get("observation_recorded") is not True:
        errors.append("observation_recorded must be true")

    spi_hz = run.get("spi_hz")
    if (
        not isinstance(spi_hz, int)
        or isinstance(spi_hz, bool)
        or spi_hz not in DEFAULT_FREQUENCIES + (OPTIONAL_FREQUENCY,)
    ):
        errors.append(f"unsupported staged frequency: {spi_hz!r}")
    if run.get("fixture") != FIXTURE:
        errors.append(f"fixture must be {FIXTURE!r}")

    report_schema_version = _required_value(run, "report_schema_version", errors)
    if (
        not isinstance(report_schema_version, int)
        or isinstance(report_schema_version, bool)
        or report_schema_version != 2
    ):
        errors.append("report_schema_version must be integer 2")
    report_operation_id = _required_value(run, "report_operation_id", errors)
    if report_operation_id is not None and (
        not _is_u32(report_operation_id) or report_operation_id == 0
    ):
        errors.append(
            "report_operation_id must be a positive unsigned 32-bit integer"
        )
    report_job_operation_id = _required_value(
        run, "report_job_operation_id", errors
    )
    if report_job_operation_id is not None and (
        not _is_u32(report_job_operation_id) or report_job_operation_id == 0
    ):
        errors.append(
            "report_job_operation_id must be a positive unsigned 32-bit integer"
        )
    if (
        report_operation_id is not None
        and report_job_operation_id is not None
        and report_operation_id != report_job_operation_id
    ):
        errors.append("report job_operation_id/operation_id mismatch")
    report_busy_assertion_missing = _required_value(
        run, "report_busy_assertion_missing", errors
    )
    if report_busy_assertion_missing is not False:
        errors.append("report_busy_assertion_missing must be false")
    report_busy_missing_stage = _required_value(
        run, "report_busy_missing_stage", errors
    )
    if report_busy_missing_stage != "none":
        errors.append("report_busy_missing_stage must be 'none'")
    for field in (
        "firmware_build_tag",
        "driver_api_version",
        "report_firmware_build_tag",
        "report_driver_api_version",
    ):
        value = _required_value(run, field, errors)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            errors.append(f"{field} must be a non-empty string")
    if (
        run.get("firmware_build_tag") is not None
        and run.get("report_firmware_build_tag") is not None
        and run.get("firmware_build_tag") != run.get("report_firmware_build_tag")
    ):
        errors.append("version/report firmware_build_tag mismatch")
    if (
        run.get("driver_api_version") is not None
        and run.get("report_driver_api_version") is not None
        and run.get("driver_api_version") != run.get("report_driver_api_version")
    ):
        errors.append("version/report driver_api_version mismatch")

    for field in (
        "version_report_raw_sha256",
        "serial_log_raw_sha256",
        "diagnostic_report_canonical_sha256",
        "job_report_canonical_sha256",
        "mapping_canonical_sha256",
        "observation_canonical_sha256",
        "scope_evidence_sha256",
    ):
        value = _required_value(run, field, errors)
        if value is not None and not _valid_sha256(value):
            errors.append(f"{field} must be a lowercase SHA-256 string")
    scope_bytes = _required_value(run, "scope_evidence_bytes", errors)
    if scope_bytes is not None and (
        not isinstance(scope_bytes, int) or isinstance(scope_bytes, bool) or scope_bytes <= 0
    ):
        errors.append("scope_evidence_bytes must be a positive integer")

    job_id = _required_value(run, "job_id", errors)
    if job_id is not None and (not _is_u32(job_id) or job_id == 0):
        errors.append("job_id must be a positive unsigned 32-bit integer")
    if run.get("job_action") != SWEEP_ACTION:
        errors.append(f"job_action must be {SWEEP_ACTION!r}")
    if run.get("job_state") != "completed":
        errors.append("job_state must be 'completed'")
    if run.get("job_result") is not True:
        errors.append("job_result must be true")
    for field in ("job_frame_fnv1a", "job_queued_at_ms", "job_started_at_ms", "job_finished_at_ms"):
        _required_value(run, field, errors)
    queued = run.get("job_queued_at_ms")
    started = run.get("job_started_at_ms")
    finished = run.get("job_finished_at_ms")
    if not all(_is_u32(value) for value in (queued, started, finished)):
        errors.append("job timestamps must be unsigned 32-bit integers")
        job_duration = None
    else:
        queue_delay = _u32_elapsed(queued, started)
        job_duration = _u32_elapsed(started, finished)
        if queue_delay > MAX_QUEUE_TO_START_MS:
            errors.append("job start is too far from queue time")
        if job_duration <= 0 or job_duration > MAX_JOB_DURATION_MS:
            errors.append("job duration is outside the accepted range")

    # The serial job boundary is mandatory and must agree with both JSON reports.
    for field in (
        "serial_job_start_id",
        "serial_job_action_code",
        "serial_job_action",
        "serial_job_finish_id",
        "serial_job_finish_state",
        "serial_job_result_known",
        "serial_job_result",
        "report_job_id",
        "report_job_action",
        "report_job_state",
        "report_job_result",
        "report_job_queued_at_ms",
        "report_job_started_at_ms",
        "report_job_finished_at_ms",
        "report_spi_hz",
    ):
        _required_value(run, field, errors)
    for field in ("serial_job_start_id", "serial_job_finish_id", "report_job_id"):
        value = run.get(field)
        if value is not None and (not _is_u32(value) or value == 0):
            errors.append(f"{field} must be a positive unsigned 32-bit integer")
    action_code = run.get("serial_job_action_code")
    if action_code is not None and not _is_u32(action_code):
        errors.append("serial_job_action_code must be an unsigned 32-bit integer")
    if run.get("report_job_result") is not True:
        errors.append("report_job_result must be true")
    if run.get("report_spi_hz") is not None and (
        not isinstance(run.get("report_spi_hz"), int)
        or isinstance(run.get("report_spi_hz"), bool)
    ):
        errors.append("report_spi_hz must be an integer")
    for field in (
        "report_job_queued_at_ms",
        "report_job_started_at_ms",
        "report_job_finished_at_ms",
    ):
        if run.get(field) is not None and not _is_u32(run.get(field)):
            errors.append(f"{field} must be an unsigned 32-bit integer")
    identity_pairs = (
        ("serial start job_id", run.get("serial_job_start_id"), job_id),
        ("serial finish job_id", run.get("serial_job_finish_id"), job_id),
        ("diagnostic job_id", run.get("report_job_id"), job_id),
        ("serial action", run.get("serial_job_action"), run.get("job_action")),
        ("diagnostic action", run.get("report_job_action"), run.get("job_action")),
        ("serial finish state", run.get("serial_job_finish_state"), run.get("job_state")),
        ("diagnostic state", run.get("report_job_state"), run.get("job_state")),
        ("serial result", run.get("serial_job_result"), run.get("job_result")),
        ("diagnostic result", run.get("report_job_result"), run.get("job_result")),
        (
            "diagnostic queued timestamp",
            run.get("report_job_queued_at_ms"),
            run.get("job_queued_at_ms"),
        ),
        (
            "diagnostic started timestamp",
            run.get("report_job_started_at_ms"),
            run.get("job_started_at_ms"),
        ),
        (
            "diagnostic finished timestamp",
            run.get("report_job_finished_at_ms"),
            run.get("job_finished_at_ms"),
        ),
        ("diagnostic spi_hz", run.get("report_spi_hz"), spi_hz),
    )
    for label, left, right in identity_pairs:
        if left is not None and right is not None and left != right:
            errors.append(f"{label} mismatch")
    if run.get("serial_job_result_known") is not True:
        errors.append("serial_job_result_known must be true")

    if run.get("cold_start") is not True:
        errors.append("cold_start must be true")
    power_off_s = _required_value(run, "power_off_s", errors)
    if power_off_s is not None:
        if not _is_finite_number(power_off_s):
            errors.append("power_off_s must be finite and numeric")
        elif power_off_s < MINIMUM_COLD_POWER_OFF_S:
            errors.append(f"power_off_s must be at least {MINIMUM_COLD_POWER_OFF_S:g}")
        elif power_off_s > MAXIMUM_RECORDED_POWER_OFF_S:
            errors.append(
                f"power_off_s must not exceed {MAXIMUM_RECORDED_POWER_OFF_S:g}"
            )

    supply_voltage_v = _required_value(run, "supply_voltage_v", errors)
    current_limit_a = _required_value(run, "current_limit_a", errors)
    peak_current_a = _required_value(run, "peak_current_a", errors)
    max_temperature_c = _required_value(run, "max_temperature_c", errors)
    if supply_voltage_v is not None:
        if not _is_finite_number(supply_voltage_v):
            errors.append("supply_voltage_v must be finite and numeric")
        elif not 3.20 <= supply_voltage_v <= 3.40:
            errors.append("supply_voltage_v must remain within 3.20..3.40 V")
    if current_limit_a is not None:
        if not _is_finite_number(current_limit_a):
            errors.append("current_limit_a must be finite and numeric")
        elif not 0 < current_limit_a <= 1.0:
            errors.append("current_limit_a must be within (0, 1.0] A")
    if peak_current_a is not None:
        if not _is_finite_number(peak_current_a):
            errors.append("peak_current_a must be finite and numeric")
        elif peak_current_a < 0:
            errors.append("peak_current_a cannot be negative")
        elif _is_finite_number(current_limit_a) and peak_current_a > current_limit_a * 1.05:
            errors.append("peak_current_a exceeds the current limit by more than 5%")
    if max_temperature_c is not None:
        if not _is_finite_number(max_temperature_c):
            errors.append("max_temperature_c must be finite and numeric")
        elif max_temperature_c > MAX_SAFE_TEMPERATURE_C:
            errors.append(
                f"max_temperature_c must not exceed {MAX_SAFE_TEMPERATURE_C:g} C"
            )

    measured_sclk_hz = _required_value(run, "measured_sclk_hz", errors)
    if measured_sclk_hz is not None:
        if not _is_finite_number(measured_sclk_hz) or measured_sclk_hz <= 0:
            errors.append("measured_sclk_hz must be a positive finite number")
        elif isinstance(spi_hz, int) and spi_hz > 0:
            frequency_error = abs(measured_sclk_hz - spi_hz)
            if frequency_error > spi_hz * SCLK_RELATIVE_TOLERANCE:
                errors.append("measured_sclk_hz differs from requested frequency by more than 5%")
    if run.get("sclk_pass") is not True:
        errors.append("sclk_pass must be true")

    # Serial evidence is authoritative; report copies are retained for a second
    # validation pass so hand-edited plans cannot silently break the agreement.
    for field in (
        "full_fnv1a",
        "serial_expected_fnv1a",
        "map_counts_pass",
        "cs1_dtm_fnv1a",
        "cs2_dtm_fnv1a",
        "cs1_upload_ms",
        "cs2_upload_ms",
        "report_input_fnv1a",
        "report_cs1_dtm_fnv1a",
        "report_cs2_dtm_fnv1a",
        "report_cs1_upload_ms",
        "report_cs2_upload_ms",
    ):
        _required_value(run, field, errors)
    for field in (
        "full_fnv1a",
        "serial_expected_fnv1a",
        "job_frame_fnv1a",
        "report_input_fnv1a",
        "cs1_dtm_fnv1a",
        "report_cs1_dtm_fnv1a",
        "cs2_dtm_fnv1a",
        "report_cs2_dtm_fnv1a",
    ):
        value = run.get(field)
        if value is not None and not _is_u32(value):
            errors.append(f"{field} must be an unsigned 32-bit integer")
    for field, expected in (
        ("full_fnv1a", EXPECTED_FULL_FNV1A),
        ("serial_expected_fnv1a", EXPECTED_FULL_FNV1A),
        ("job_frame_fnv1a", EXPECTED_FULL_FNV1A),
        ("report_input_fnv1a", EXPECTED_FULL_FNV1A),
        ("cs1_dtm_fnv1a", EXPECTED_CS1_FNV1A),
        ("report_cs1_dtm_fnv1a", EXPECTED_CS1_FNV1A),
        ("cs2_dtm_fnv1a", EXPECTED_CS2_FNV1A),
        ("report_cs2_dtm_fnv1a", EXPECTED_CS2_FNV1A),
    ):
        if run.get(field) != expected:
            errors.append(f"{field}={run.get(field)!r}; expected {expected}")
    if run.get("map_counts_pass") is not True:
        errors.append("map_counts_pass must be true")
    for label, left, right in (
        ("CS1 upload", run.get("cs1_upload_ms"), run.get("report_cs1_upload_ms")),
        ("CS2 upload", run.get("cs2_upload_ms"), run.get("report_cs2_upload_ms")),
    ):
        if left is not None and right is not None and left != right:
            errors.append(f"serial/report {label} mismatch")

    for field in ("cs1_upload_ms", "cs2_upload_ms", "total_ms"):
        value = _required_value(run, field, errors)
        if value is not None and (not _is_finite_number(value) or value <= 0):
            errors.append(f"{field} must be a positive finite number")
    for field in (
        "cs1_upload_ms",
        "cs2_upload_ms",
        "report_cs1_upload_ms",
        "report_cs2_upload_ms",
        "pon_ms",
        "drf_ms",
        "pof_ms",
        "post_psr_ms",
        "report_pon_ms",
        "report_drf_ms",
        "report_pof_ms",
        "report_post_psr_ms",
        "total_ms",
        "report_last_wait_ms",
    ):
        value = run.get(field)
        if value is not None and not _is_u32(value):
            errors.append(f"{field} must be an unsigned 32-bit integer")
    for field in (
        "pon_ms",
        "pof_ms",
        "post_psr_ms",
        "report_pon_ms",
        "report_pof_ms",
        "report_post_psr_ms",
    ):
        value = _required_value(run, field, errors)
        if value is not None and (not _is_finite_number(value) or value < 0):
            errors.append(f"{field} must be a non-negative finite number")
    for field in ("drf_ms", "report_drf_ms"):
        drf_ms = _required_value(run, field, errors)
        if drf_ms is not None:
            if not _is_finite_number(drf_ms):
                errors.append(f"{field} must be finite and numeric")
            elif not DRF_MIN_MS <= drf_ms <= DRF_MAX_MS:
                errors.append(
                    f"{field} must remain within {DRF_MIN_MS:g}..{DRF_MAX_MS:g} ms"
                )
    for field in (
        "pon_busy_seen",
        "drf_busy_seen",
        "pof_busy_seen",
        "post_psr_busy_seen",
        "report_pon_busy_seen",
        "report_drf_busy_seen",
        "report_pof_busy_seen",
        "report_post_psr_busy_seen",
    ):
        _required_value(run, field, errors)
        if run.get(field) is not True:
            errors.append(f"{field} must be true")

    for label, serial_field, report_field in (
        ("PON wait", "pon_ms", "report_pon_ms"),
        ("DRF wait", "drf_ms", "report_drf_ms"),
        ("POF wait", "pof_ms", "report_pof_ms"),
        ("post-PSR wait", "post_psr_ms", "report_post_psr_ms"),
        ("PON busy", "pon_busy_seen", "report_pon_busy_seen"),
        ("DRF busy", "drf_busy_seen", "report_drf_busy_seen"),
        ("POF busy", "pof_busy_seen", "report_pof_busy_seen"),
        ("post-PSR busy", "post_psr_busy_seen", "report_post_psr_busy_seen"),
    ):
        left = run.get(serial_field)
        right = run.get(report_field)
        if left is not None and right is not None and left != right:
            errors.append(f"serial/report {label} mismatch")

    total_ms = run.get("total_ms")
    report_last_wait_ms = _required_value(run, "report_last_wait_ms", errors)
    if (
        report_last_wait_ms is not None
        and run.get("post_psr_ms") is not None
        and report_last_wait_ms != run.get("post_psr_ms")
    ):
        errors.append("post-PSR/report last wait mismatch")
    stage_values = [run.get(field) for field in ("pon_ms", "drf_ms", "pof_ms", "post_psr_ms")]
    upload_values = [run.get("cs1_upload_ms"), run.get("cs2_upload_ms")]
    if all(_is_finite_number(value) for value in (*upload_values, *stage_values, total_ms)):
        if total_ms < sum(upload_values) + sum(stage_values):
            errors.append("total_ms cannot be shorter than uploads plus BUSY stages")
    if job_duration is not None and _is_finite_number(total_ms):
        if job_duration < total_ms:
            errors.append("job duration cannot be shorter than diagnostic total_ms")
        elif job_duration - total_ms > MAX_JOB_OVERHEAD_MS:
            errors.append("job duration exceeds diagnostic total_ms by too much")

    for field in (
        "report_valid",
        "mapping_applied",
        "sequence_ok",
        "serial_refresh_pass",
        "visual_pass",
        "cv_pass",
        "thermal_pass",
        "acoustic_pass",
    ):
        _required_value(run, field, errors)
        if run.get(field) is not True:
            errors.append(f"{field} must be true")
    if run.get("report_running") is not False:
        errors.append("report_running must be false")
    if run.get("wait_timeout") is not False:
        errors.append("wait_timeout must be false")
    if run.get("timeout_stage") != "none":
        errors.append("timeout_stage must be 'none'")
    if run.get("last_wait_stage") != "post-display PSR":
        errors.append("last_wait_stage must be 'post-display PSR'")
    errors.extend(_validate_mapping(run.get("mapping")))
    try:
        mapping_hash = _canonical_json_sha256(run.get("mapping"), "recorded mapping")
    except RefreshAnalysisError as error:
        errors.append(str(error))
    else:
        if mapping_hash != run.get("mapping_canonical_sha256"):
            errors.append("mapping does not match mapping_canonical_sha256")
    try:
        observation_hash = _observation_sha256(run)
    except RefreshAnalysisError as error:
        errors.append(str(error))
    else:
        if observation_hash != run.get("observation_canonical_sha256"):
            errors.append("observation does not match observation_canonical_sha256")

    cs1_ms = run.get("cs1_upload_ms")
    cs2_ms = run.get("cs2_upload_ms")
    if _is_u32(cs1_ms) and _is_u32(cs2_ms) and max(cs1_ms, cs2_ms) > 0:
        imbalance = abs(cs1_ms - cs2_ms) / max(cs1_ms, cs2_ms)
        if imbalance > 0.20:
            warnings.append(f"CS upload imbalance is {imbalance:.1%}; inspect wiring/timing")
        if isinstance(spi_hz, int) and spi_hz > 0:
            raw_half_ms = theoretical_wire_time_ms(spi_hz, FRAME_BYTES // 2)
            if min(cs1_ms, cs2_ms) + 1 < raw_half_ms:
                errors.append("reported upload is below raw wire time")

    if spi_hz == OPTIONAL_FREQUENCY:
        if run.get("timing_pass") is not True:
            errors.append("20 MHz requires timing_pass=true")
        if not _valid_sha256(run.get("timing_evidence_sha256")):
            errors.append("20 MHz requires a timing evidence SHA-256")
        timing_bytes = run.get("timing_evidence_bytes")
        if not isinstance(timing_bytes, int) or isinstance(timing_bytes, bool) or timing_bytes <= 0:
            errors.append("20 MHz requires non-empty timing evidence")
    elif run.get("timing_pass") is False:
        errors.append("timing_pass=false is a recorded failure")
    return errors, warnings


def _blank_row_is_pristine(run: Mapping[str, Any]) -> bool:
    if run.get("observation_recorded") is not False:
        return False
    template = _blank_observation(run.get("spi_hz"))
    return set(run) == set(template) and all(
        run.get(key) == value for key, value in template.items()
    )


def _canonical_mapping(mapping: Any) -> str:
    try:
        return json.dumps(mapping, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        return "<invalid>"


def _report_number(value: Any) -> Optional[float]:
    return value if _is_finite_number(value) else None


def analyze_document(document: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate ordered individual and cross-frequency sweep gates."""

    if not isinstance(document, Mapping):
        raise RefreshAnalysisError("sweep document must be a JSON object")
    if document.get("schema_version") != 2 or document.get("kind") != "mf1750-spi-refresh-sweep":
        raise RefreshAnalysisError("not an MF-1750 SPI refresh sweep schema version 2 document")
    if document.get("required_action") != SWEEP_ACTION:
        raise RefreshAnalysisError(f"required_action must be {SWEEP_ACTION!r}")
    if document.get("fixture") != FIXTURE:
        raise RefreshAnalysisError(f"fixture must be {FIXTURE!r}")
    if document.get("expected_hashes") != EXPECTED_HASHES:
        raise RefreshAnalysisError("expected_hashes do not match the frozen fixture")
    if document.get("minimum_cold_power_off_s") != MINIMUM_COLD_POWER_OFF_S:
        raise RefreshAnalysisError(
            f"minimum_cold_power_off_s must be {MINIMUM_COLD_POWER_OFF_S:g}"
        )
    runs = document.get("runs")
    if not isinstance(runs, list) or not runs:
        raise RefreshAnalysisError("runs must be a non-empty list")
    if not all(isinstance(run, Mapping) for run in runs):
        raise RefreshAnalysisError("every run must be a JSON object")

    frequencies = [run.get("spi_hz") for run in runs]
    expected_order = list(DEFAULT_FREQUENCIES)
    if OPTIONAL_FREQUENCY in frequencies:
        expected_order.append(OPTIONAL_FREQUENCY)
    if frequencies != expected_order:
        raise RefreshAnalysisError(f"frequency order must be {expected_order}; got {frequencies}")
    if document.get("frequency_order_hz") != frequencies:
        raise RefreshAnalysisError("frequency_order_hz must exactly match the run order")

    results: List[Dict[str, Any]] = []
    all_lower_passed = True
    highest_passed_hz: Optional[int] = None
    next_frequency_hz: Optional[int] = None
    baseline_build: Optional[str] = None
    baseline_api: Optional[str] = None
    baseline_mapping: Optional[str] = None
    baseline_drf_ms: Optional[float] = None
    previous_upload_ms: Optional[Tuple[float, float]] = None
    unique_evidence_fields = (
        ("job_id", "job_id"),
        ("serial_log_raw_sha256", "serial-log capture"),
        ("diagnostic_report_canonical_sha256", "diagnostic capture"),
        ("job_report_canonical_sha256", "job capture"),
        ("scope_evidence_sha256", "scope capture"),
    )
    seen_evidence = {field: set() for field, _ in unique_evidence_fields}

    for run in runs:
        spi_hz = run["spi_hz"]
        errors: List[str] = []
        warnings: List[str] = []
        if _blank_row_is_pristine(run):
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

            if not errors:
                for field, label in unique_evidence_fields:
                    if run.get(field) in seen_evidence[field]:
                        errors.append(f"{label} was reused from a lower-frequency run")

            if not errors:
                mapping_key = _canonical_mapping(run.get("mapping"))
                if baseline_build is None:
                    baseline_build = run.get("firmware_build_tag")
                    baseline_api = run.get("driver_api_version")
                    baseline_mapping = mapping_key
                    baseline_drf_ms = float(run["drf_ms"])
                else:
                    if run.get("firmware_build_tag") != baseline_build:
                        errors.append("firmware_build_tag changed within the sweep")
                    if run.get("driver_api_version") != baseline_api:
                        errors.append("driver_api_version changed within the sweep")
                    if mapping_key != baseline_mapping:
                        errors.append("controller mapping changed within the sweep")
                    drf_tolerance = max(
                        DRF_BASELINE_ABSOLUTE_TOLERANCE_MS,
                        baseline_drf_ms * DRF_BASELINE_RELATIVE_TOLERANCE,
                    )
                    if abs(float(run["drf_ms"]) - baseline_drf_ms) > drf_tolerance:
                        errors.append("DRF time departed from the SPI-only baseline")

                upload_ms = (
                    float(run["cs1_upload_ms"]),
                    float(run["cs2_upload_ms"]),
                )
                if previous_upload_ms is not None:
                    for controller, previous_ms, current_ms in zip(
                        ("CS1", "CS2"), previous_upload_ms, upload_ms
                    ):
                        required_improvement = max(
                            MIN_UPLOAD_IMPROVEMENT_MS,
                            previous_ms * MIN_UPLOAD_IMPROVEMENT_FRACTION,
                        )
                        if previous_ms - current_ms < required_improvement:
                            errors.append(
                                f"{controller} upload time did not show a distinguishable "
                                "improvement over the lower frequency"
                            )
                if not errors:
                    previous_upload_ms = upload_ms
                    for field, _ in unique_evidence_fields:
                        seen_evidence[field].add(run.get(field))

            status = "PASS" if not errors else "FAIL"
            if status == "PASS":
                highest_passed_hz = spi_hz
            else:
                all_lower_passed = False

        measured_upload_ms = None
        if _is_finite_number(run.get("cs1_upload_ms")) and _is_finite_number(
            run.get("cs2_upload_ms")
        ):
            measured_upload_ms = run["cs1_upload_ms"] + run["cs2_upload_ms"]
        results.append(
            {
                "run_id": run.get("run_id"),
                "spi_hz": spi_hz,
                "measured_sclk_hz": _report_number(run.get("measured_sclk_hz")),
                "status": status,
                "theoretical_wire_ms": round(theoretical_wire_time_ms(spi_hz), 3),
                "measured_upload_ms": measured_upload_ms,
                "pon_ms": _report_number(run.get("pon_ms")),
                "drf_ms": _report_number(run.get("drf_ms")),
                "pof_ms": _report_number(run.get("pof_ms")),
                "post_psr_ms": _report_number(run.get("post_psr_ms")),
                "total_ms": _report_number(run.get("total_ms")),
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
        "schema_version": 2,
        "overall": overall,
        "hardware_tested": bool(highest_passed_hz),
        "highest_passed_hz": highest_passed_hz,
        "next_frequency_hz": next_frequency_hz,
        "waveform_fast_refresh_tested": False,
        "results": results,
    }


def _replace_run(document: Mapping[str, Any], observation: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(document, Mapping):
        raise RefreshAnalysisError("plan must be a JSON object")
    if document.get("schema_version") != 2 or document.get("kind") != "mf1750-spi-refresh-sweep":
        raise RefreshAnalysisError("plan must use MF-1750 sweep schema version 2")
    runs = document.get("runs")
    if not isinstance(runs, list) or not all(isinstance(run, Mapping) for run in runs):
        raise RefreshAnalysisError("plan runs must be JSON objects")
    updated = copy.deepcopy(document)
    matches = [run for run in updated["runs"] if run.get("spi_hz") == observation.get("spi_hz")]
    if len(matches) != 1:
        raise RefreshAnalysisError(
            f"plan must contain exactly one run for spi_hz={observation.get('spi_hz')}"
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
        "extract", help="merge one offline sweep capture set into a plan"
    )
    extract_parser.add_argument("plan", type=Path)
    extract_parser.add_argument("--serial-log", type=Path, required=True)
    extract_parser.add_argument("--report", type=Path, required=True)
    extract_parser.add_argument("--job-report", type=Path, required=True)
    extract_parser.add_argument("--version-report", type=Path, required=True)
    extract_parser.add_argument("--scope-evidence", type=Path, required=True)
    extract_parser.add_argument("--timing-evidence", type=Path)
    extract_parser.add_argument("--spi-hz", type=int, required=True)
    extract_parser.add_argument("--measured-sclk-hz", type=float, required=True)
    extract_parser.add_argument(
        "--sclk-pass", action=argparse.BooleanOptionalAction, required=True
    )
    extract_parser.add_argument(
        "--timing-pass", action=argparse.BooleanOptionalAction
    )
    extract_parser.add_argument(
        "--cold-start", action=argparse.BooleanOptionalAction, required=True
    )
    extract_parser.add_argument("--power-off-s", type=float, required=True)
    extract_parser.add_argument("--supply-voltage-v", type=float, required=True)
    extract_parser.add_argument("--current-limit-a", type=float, required=True)
    extract_parser.add_argument("--peak-current-a", type=float, required=True)
    extract_parser.add_argument("--max-temperature-c", type=float, required=True)
    extract_parser.add_argument(
        "--visual-pass", action=argparse.BooleanOptionalAction, required=True
    )
    extract_parser.add_argument(
        "--cv-pass", action=argparse.BooleanOptionalAction, required=True
    )
    extract_parser.add_argument(
        "--thermal-pass", action=argparse.BooleanOptionalAction, required=True
    )
    extract_parser.add_argument(
        "--acoustic-pass", action=argparse.BooleanOptionalAction, required=True
    )
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
            diagnostic_report = _load_json(args.report)
            job_report = _load_json(args.job_report)
            if not isinstance(diagnostic_report, Mapping):
                raise RefreshAnalysisError("diagnostic report must be a JSON object")
            if not isinstance(job_report, Mapping):
                raise RefreshAnalysisError("job report must be a JSON object")
            observation = extract_observation(
                args.spi_hz,
                _read_bytes(args.serial_log, "serial log"),
                diagnostic_report,
                job_report,
                _read_bytes(args.version_report, "version report"),
                _read_bytes(args.scope_evidence, "scope evidence"),
                cold_start=args.cold_start,
                power_off_s=args.power_off_s,
                supply_voltage_v=args.supply_voltage_v,
                current_limit_a=args.current_limit_a,
                peak_current_a=args.peak_current_a,
                max_temperature_c=args.max_temperature_c,
                measured_sclk_hz=args.measured_sclk_hz,
                sclk_pass=args.sclk_pass,
                visual_pass=args.visual_pass,
                cv_pass=args.cv_pass,
                thermal_pass=args.thermal_pass,
                acoustic_pass=args.acoustic_pass,
                timing_evidence=(
                    _read_bytes(args.timing_evidence, "timing evidence")
                    if args.timing_evidence is not None
                    else None
                ),
                timing_pass=args.timing_pass,
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
