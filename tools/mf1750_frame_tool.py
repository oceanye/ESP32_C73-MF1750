#!/usr/bin/env python3
"""Generate, verify, and safely transfer canonical MF-1750 test frames.

Without ``--url`` this tool is strictly offline.  With ``--url`` it defaults
to the non-refreshing ingress check.  A refresh additionally requires an
explicit cold-start confirmation plus two ordered expected controller
mappings, and is successful only after the matching job and diagnostic report
have both been verified.
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable, Mapping, Optional, Sequence, Tuple
import urllib.error
import urllib.parse
import urllib.request


# ``python tools/mf1750_frame_tool.py`` puts tools/, not the repository root,
# on sys.path.  Bootstrap only the local source tree before importing the one
# canonical frame implementation.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.epd_frame import (  # noqa: E402
    CONTROLLER_FRAME_BYTES,
    EXPECTED_FIXTURE_HASHES,
    FIXTURE_NAMES,
    FRAME_BYTES,
    HEIGHT,
    MAP_ORIENT_V1_PIXEL_COUNTS,
    PHYSICAL_COLOR_CODES,
    WIDTH,
    ControllerMapping,
    FrameContractError,
    controller_stream,
    controller_stream_reference,
    fnv1a,
    generate_fixture,
    pixel_counts,
    split_controllers,
    validate_frame,
    verify_fixture,
)


ALLOWED_BUILD_TAGS = frozenset(
    {
        "MF1750_DRIVER_RC2F_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_PSRFIX_WEBPHOTO_PHYSICAL_2026-08-05",
        "MF1750_DRIVER_RC2G_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_PSRFIX_WEBPHOTO_PHYSICAL_BUSYEDGE_2026-08-07",
        "MF1750_L535_FRAME_V1_20260926",
        "MF1750_L535_FRAME_V2_20261006",
    }
)
BUSY_TRACE_BUILD_TAGS = frozenset(
    {
        "MF1750_DRIVER_RC2G_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_PSRFIX_WEBPHOTO_PHYSICAL_BUSYEDGE_2026-08-07"
    }
)
REQUIRED_DRIVER_API = "MF1750_R16_CASCADE_V3"
NOMINAL_PSRAM_BYTES = 8 * 1024 * 1024
# Arduino's ESP.getPsramSize() reports the managed SPIRAM heap
# (free + allocated), not the physical package capacity. Heap metadata makes
# a real 8 MiB N8R8 module report slightly below nominal. Keep a bounded
# allowance that remains far above a 4 MiB part; the separate free-space gate
# still requires room for the complete canonical frame.
MAX_PSRAM_HEAP_OVERHEAD_BYTES = 64 * 1024
MIN_REPORTED_PSRAM_BYTES = NOMINAL_PSRAM_BYTES - MAX_PSRAM_HEAP_OVERHEAD_BYTES
REQUIRED_REFRESH_SPI_HZ = 1_000_000
UINT32_MAX = 0xFFFFFFFF
UINT32_FORWARD_LIMIT = 0x7FFFFFFF
DEFAULT_JOB_TIMEOUT_S = 180.0
DEFAULT_POLL_INTERVAL_S = 1.0
FROZEN_PRODUCTION_DIR = REPO_ROOT / "hardware" / "mf1750_production_v1" / "production"

HttpRequester = Callable[..., Tuple[int, str]]


class FrameToolError(RuntimeError):
    """Raised when a local or remote safety contract is not satisfied."""


class FrameToolNetworkError(FrameToolError):
    """Raised for a transient transport-level failure."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _mapping_dict(mapping: ControllerMapping) -> dict[str, int | bool]:
    return {
        "source_half": mapping.source_half,
        "flip_x": mapping.flip_x,
        "flip_y": mapping.flip_y,
        "nibble_swap": mapping.nibble_swap,
    }


def _validate_mapping_pair(
    mappings: Optional[Sequence[ControllerMapping]],
) -> Optional[tuple[ControllerMapping, ControllerMapping]]:
    if mappings is None:
        return None
    if len(mappings) != 2:
        raise FrameToolError("exactly two controller mappings are required, ordered CS1 then CS2")
    first, second = mappings
    if not isinstance(first, ControllerMapping) or not isinstance(second, ControllerMapping):
        raise FrameToolError("controller mappings must be ControllerMapping instances")
    if first.source_half == second.source_half:
        raise FrameToolError("CS1 and CS2 mappings must consume different logical halves")
    return first, second


def _require_refresh_mapping_pair(
    mappings: Optional[Sequence[ControllerMapping]],
) -> tuple[ControllerMapping, ControllerMapping]:
    if mappings is None or len(mappings) != 2:
        raise FrameToolError(
            "refresh requires exactly two explicit controller mappings, ordered CS1 then CS2"
        )
    mapping_pair = _validate_mapping_pair(mappings)
    assert mapping_pair is not None
    return mapping_pair


def _validated_frame_bytes(
    frame: bytes | bytearray | memoryview,
    allowed_colors: Optional[Sequence[int]] = None,
) -> bytes:
    """Apply the canonical frame contract and translate it to this tool's error type.

    ``allowed_colors=None`` keeps the stock physical-code set; callers on the
    L535 frame path (build tag MF1750_L535_FRAME_V1_20260926) pass the full
    0..7 nibble set explicitly.
    """

    try:
        if allowed_colors is None:
            return bytes(validate_frame(frame))
        return bytes(validate_frame(frame, allowed_colors=allowed_colors))
    except FrameContractError as error:
        raise FrameToolError(f"invalid canonical frame: {error}") from error


def _mapping_algorithm_verified(frame: bytes) -> bool:
    for source_half, flip_x, flip_y, nibble_swap in itertools.product(
        (0, 1), (False, True), (False, True), (False, True)
    ):
        mapping = ControllerMapping(source_half, flip_x, flip_y, nibble_swap)
        if controller_stream(frame, mapping) != controller_stream_reference(frame, mapping):
            return False
    return True


def build_offline_report(
    pattern: str,
    frame: bytes,
    mappings: Optional[Sequence[ControllerMapping]] = None,
) -> dict[str, Any]:
    """Build a controller-neutral report, adding physical hashes only explicitly."""

    mapping_pair = _validate_mapping_pair(mappings)
    fixture = verify_fixture(pattern, frame)
    logical_left, logical_right = split_controllers(frame)
    expected_full, expected_left, expected_right = EXPECTED_FIXTURE_HASHES[pattern]
    mapping_verified = _mapping_algorithm_verified(frame)
    report: dict[str, Any] = {
        "schema_version": 2,
        "kind": "mf1750-frame-report",
        "pattern": pattern,
        "width": WIDTH,
        "height": HEIGHT,
        "bytes": len(frame),
        "physical_color_codes": sorted(PHYSICAL_COLOR_CODES),
        "full_fnv1a": fnv1a(frame),
        "logical_left_fnv1a": fnv1a(logical_left),
        "logical_right_fnv1a": fnv1a(logical_right),
        "expected_full_fnv1a": expected_full,
        "expected_logical_left_fnv1a": expected_left,
        "expected_logical_right_fnv1a": expected_right,
        "mapping_algorithm_verified": mapping_verified,
        "offline_verified": fixture.verified and mapping_verified,
        "hardware_tested": False,
        "verified_scope": [
            "canonical_fixture_dimensions_colors_and_hashes",
            "host_controller_mapping_algorithm",
        ],
    }
    if pattern == "map-orient-v1":
        report["pixel_counts"] = list(pixel_counts(frame))
        report["pixel_counts_verified"] = pixel_counts(frame) == MAP_ORIENT_V1_PIXEL_COUNTS
        report["offline_verified"] = bool(
            report["offline_verified"] and report["pixel_counts_verified"]
        )
    if mapping_pair is not None:
        report["physical_controllers"] = [
            {
                "controller": f"CS{index}",
                "mapping": _mapping_dict(mapping),
                "dtm_bytes": CONTROLLER_FRAME_BYTES,
                "dtm_fnv1a": fnv1a(controller_stream(frame, mapping)),
            }
            for index, mapping in enumerate(mapping_pair, start=1)
        ]
    return report


def _normalize_base_url(base_url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(base_url)
        # Accessing port performs validation that urlsplit intentionally
        # defers (for example, malformed or out-of-range ports).
        _ = parsed.port
    except ValueError as error:
        raise FrameToolError(f"--url is malformed: {error}") from error
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise FrameToolError("--url must be an absolute http(s) base URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise FrameToolError("--url must not contain credentials, a query, or a fragment")
    if parsed.path not in ("", "/"):
        raise FrameToolError("--url must identify the device root without an extra path")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def http_request(
    base_url: str,
    endpoint: str,
    *,
    method: str = "GET",
    data: Optional[bytes] = None,
    timeout: float = 20.0,
) -> tuple[int, str]:
    request = urllib.request.Request(
        _normalize_base_url(base_url) + endpoint,
        data=data,
        method=method,
        headers={"Content-Type": "application/octet-stream"} if data is not None else {},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise FrameToolNetworkError(f"{method} {endpoint} failed: {error}") from error


def _json_object(body: str, label: str) -> dict[str, Any]:
    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            body,
            object_pairs_hook=reject_duplicate,
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise FrameToolError(f"{label} did not return strict JSON: {error}") from error
    if not isinstance(value, dict):
        raise FrameToolError(f"{label} JSON must be an object")
    return value


def _require_bool(value: Mapping[str, Any], key: str, label: str) -> bool:
    result = value.get(key)
    if type(result) is not bool:
        raise FrameToolError(f"{label}.{key} must be a boolean")
    return result


def _require_int(
    value: Mapping[str, Any], key: str, label: str, *, minimum: int = 0
) -> int:
    result = value.get(key)
    if type(result) is not int or result < minimum:
        raise FrameToolError(f"{label}.{key} must be an integer >= {minimum}")
    return result


def _require_u32(value: Mapping[str, Any], key: str, label: str) -> int:
    result = value.get(key)
    if type(result) is not int or not 0 <= result <= UINT32_MAX:
        raise FrameToolError(f"{label}.{key} must be an unsigned 32-bit integer")
    return result


def _require_nonzero_u32(value: Mapping[str, Any], key: str, label: str) -> int:
    result = _require_u32(value, key, label)
    if result == 0:
        raise FrameToolError(
            f"{label}.{key} must be a non-zero unsigned 32-bit integer"
        )
    return result


def _u32_is_forward_or_equal(earlier: int, later: int) -> bool:
    return ((later - earlier) & UINT32_MAX) <= UINT32_FORWARD_LIMIT


def _require_string(value: Mapping[str, Any], key: str, label: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise FrameToolError(f"{label}.{key} must be a non-empty string")
    return result


def _expect_status(status: int, expected: int, body: str, label: str) -> None:
    if status != expected:
        excerpt = body.replace("\r", " ").replace("\n", " ")[:160]
        raise FrameToolError(f"{label} returned HTTP {status}, expected {expected}: {excerpt}")


def _validate_transfer_response(
    data: Mapping[str, Any], expected_hash: int, label: str
) -> None:
    if _require_bool(data, "ok", label) is not True:
        raise FrameToolError(f"{label}.ok is false")
    if _require_int(data, "bytes", label) != FRAME_BYTES:
        raise FrameToolError(f"{label}.bytes does not match {FRAME_BYTES}")
    if _require_int(data, "fnv1a", label) != expected_hash:
        raise FrameToolError(f"{label}.fnv1a does not match the transmitted frame")
    _require_int(data, "free_psram", label)


def perform_ingress(
    base_url: str,
    frame: bytes | bytearray | memoryview,
    *,
    requester: Optional[HttpRequester] = None,
) -> dict[str, Any]:
    # This must remain the first operation: malformed frames must never cause
    # URL handling or any device request.
    frame_bytes = _validated_frame_bytes(frame)
    request = requester or http_request
    base_url = _normalize_base_url(base_url)
    status, body = request(
        base_url,
        "/api/diagnostic/frame-ingress",
        method="POST",
        data=frame_bytes,
        timeout=20.0,
    )
    _expect_status(status, 200, body, "frame ingress")
    response = _json_object(body, "frame ingress")
    expected_hash = fnv1a(frame_bytes)
    _validate_transfer_response(response, expected_hash, "frame ingress")
    if _require_string(response, "epd_action", "frame ingress") != "none":
        raise FrameToolError("frame ingress.epd_action must be none")
    return {
        "mode": "ingress-only",
        "epd_action": "none",
        "bytes": FRAME_BYTES,
        "fnv1a": expected_hash,
        "protocol_verified": True,
        "hardware_tested": False,
        "verified_scope": [
            "canonical_frame_dimensions_and_physical_color_codes",
            "ingress_bytes_and_fnv1a",
            "explicit_no_epd_action",
        ],
    }


def _parse_version_mapping(value: str, label: str) -> ControllerMapping:
    fields = [field.strip() for field in value.split(",")]
    if len(fields) != 4 or any(field not in ("0", "1") for field in fields):
        raise FrameToolError(f"{label} must contain four comma-separated 0/1 fields")
    numbers = [int(field) for field in fields]
    return ControllerMapping(numbers[0], *(bool(number) for number in numbers[1:]))


def _parse_version(
    body: str,
    expected_mappings: tuple[ControllerMapping, ControllerMapping],
) -> dict[str, Any]:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines or lines[0] not in ALLOWED_BUILD_TAGS:
        raise FrameToolError("firmware build tag is not in the exact safety allowlist")
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            raise FrameToolError(f"malformed /api/version line: {line!r}")
        key, value = (part.strip() for part in line.split(":", 1))
        if key in fields:
            raise FrameToolError(f"duplicate /api/version field: {key}")
        fields[key] = value
    if fields.get("Panel") != f"{WIDTH}x{HEIGHT}":
        raise FrameToolError("firmware panel dimensions do not match the canonical frame")
    if fields.get("Driver API") != REQUIRED_DRIVER_API:
        raise FrameToolError(f"firmware Driver API must be {REQUIRED_DRIVER_API}")
    try:
        frame_bytes = int(fields["Frame bytes"])
        psram_bytes = int(fields["PSRAM bytes"])
        free_psram = int(fields["Free PSRAM"])
        refresh_spi_hz = int(fields["Refresh SPI Hz"])
    except (KeyError, ValueError) as error:
        raise FrameToolError("firmware version has invalid frame/PSRAM/SPI fields") from error
    if frame_bytes != FRAME_BYTES:
        raise FrameToolError(f"firmware frame size must be {FRAME_BYTES}")
    if psram_bytes < MIN_REPORTED_PSRAM_BYTES:
        raise FrameToolError(
            "firmware reports less than the minimum managed PSRAM heap for "
            f"an 8 MiB module ({MIN_REPORTED_PSRAM_BYTES} bytes)"
        )
    if free_psram < FRAME_BYTES:
        raise FrameToolError("firmware does not report enough free PSRAM for one frame")
    if refresh_spi_hz != REQUIRED_REFRESH_SPI_HZ:
        raise FrameToolError(
            f"firmware Refresh SPI Hz must be {REQUIRED_REFRESH_SPI_HZ}"
        )
    try:
        device_mappings = (
            _parse_version_mapping(fields["CS1 Mapping"], "firmware CS1 Mapping"),
            _parse_version_mapping(fields["CS2 Mapping"], "firmware CS2 Mapping"),
        )
    except KeyError as error:
        raise FrameToolError("firmware version is missing CS1/CS2 Mapping") from error
    if device_mappings != expected_mappings:
        raise FrameToolError(
            "firmware CS1/CS2 Mapping differs from the explicit expected mappings"
        )
    return {
        "build_tag": lines[0],
        "driver_api": fields["Driver API"],
        "panel": fields["Panel"],
        "frame_bytes": frame_bytes,
        "psram_bytes": psram_bytes,
        "free_psram": free_psram,
        "refresh_spi_hz": refresh_spi_hz,
        "controller_mappings": [
            {
                "controller": f"CS{controller}",
                "mapping": _mapping_dict(mapping),
            }
            for controller, mapping in enumerate(device_mappings, start=1)
        ],
    }


def _preflight_version(
    base_url: str,
    requester: HttpRequester,
    expected_mappings: tuple[ControllerMapping, ControllerMapping],
) -> dict[str, Any]:
    status, body = requester(base_url, "/api/version", method="GET", data=None, timeout=20.0)
    _expect_status(status, 200, body, "firmware preflight")
    return _parse_version(body, expected_mappings)


def _validate_job(data: Mapping[str, Any], job_id: int, frame_hash: int) -> str:
    label = "job"
    if _require_int(data, "job_id", label, minimum=1) != job_id:
        raise FrameToolError("job id changed while waiting for refresh")
    if _require_string(data, "action", label) != "uploaded_frame":
        raise FrameToolError("job action is not uploaded_frame")
    if _require_int(data, "frame_fnv1a", label) != frame_hash:
        raise FrameToolError("job frame hash does not match the transmitted frame")
    queued_at_ms = _require_u32(data, "queued_at_ms", label)
    started_at_ms = _require_u32(data, "started_at_ms", label)
    finished_at_ms = _require_u32(data, "finished_at_ms", label)
    state = _require_string(data, "state", label)
    result = data.get("result")
    if state in ("queued", "running"):
        if result is not None:
            raise FrameToolError(f"{state} job must have result=null")
        return state
    if state == "completed":
        if result is not True:
            raise FrameToolError("completed job did not report result=true")
        if not _u32_is_forward_or_equal(queued_at_ms, started_at_ms):
            raise FrameToolError("completed job timestamps are not ordered queued -> started")
        if not _u32_is_forward_or_equal(started_at_ms, finished_at_ms):
            raise FrameToolError("completed job timestamps are not ordered started -> finished")
        return state
    if state == "failed":
        raise FrameToolError("refresh job reported failed")
    raise FrameToolError(f"unexpected job state {state!r}")


def _wait_for_job(
    base_url: str,
    job_id: int,
    frame_hash: int,
    requester: HttpRequester,
    *,
    timeout_s: float,
    poll_interval_s: float,
    sleeper: Callable[[float], None],
    clock: Callable[[], float],
) -> dict[str, Any]:
    deadline = clock() + timeout_s
    last_network_error: Optional[Exception] = None
    while clock() < deadline:
        remaining = deadline - clock()
        try:
            status, body = requester(
                base_url,
                "/api/job",
                method="GET",
                data=None,
                timeout=min(20.0, max(1.0, remaining)),
            )
            _expect_status(status, 200, body, "job poll")
            job = _json_object(body, "job poll")
            state = _validate_job(job, job_id, frame_hash)
            if state == "completed":
                return job
            last_network_error = None
        except FrameToolNetworkError as error:
            # The synchronous ESP32 WebServer cannot answer while the display
            # routine is running.  A poll timeout is therefore retryable until
            # the overall job deadline, but malformed responses are not.
            last_network_error = error
        remaining = deadline - clock()
        if remaining > 0:
            sleeper(min(poll_interval_s, remaining))
    suffix = f"; last network error: {last_network_error}" if last_network_error else ""
    raise FrameToolError(f"refresh job did not complete within {timeout_s:g} seconds{suffix}")


def _mapping_from_diagnostic(mapping: Mapping[str, Any], controller: int) -> ControllerMapping:
    label = f"diagnostic.mapping.cs{controller}"
    prefix = f"cs{controller}_"
    source_half = _require_int(mapping, prefix + "source_half", label)
    flip_x = _require_bool(mapping, prefix + "flip_x", label)
    flip_y = _require_bool(mapping, prefix + "flip_y", label)
    nibble_swap = _require_bool(mapping, prefix + "nibble_swap", label)
    try:
        return ControllerMapping(source_half, flip_x, flip_y, nibble_swap)
    except ValueError as error:
        raise FrameToolError(f"{label} is invalid: {error}") from error


def _require_object(
    value: Mapping[str, Any], key: str, label: str
) -> Mapping[str, Any]:
    result = value.get(key)
    if not isinstance(result, dict):
        raise FrameToolError(f"{label}.{key} must be an object")
    return result


def _busy_level(
    value: Mapping[str, Any], key: str, label: str, *, allow_unsampled: bool = False
) -> int:
    level = _require_int(value, key, label)
    allowed = {0, 1, 255} if allow_unsampled else {0, 1}
    if level not in allowed:
        suffix = "0, 1, or 255" if allow_unsampled else "0 or 1"
        raise FrameToolError(f"{label}.{key} must be {suffix}")
    return level


def _validate_busy_trace(
    data: Mapping[str, Any], wait_ms: Mapping[str, int]
) -> dict[str, Any]:
    label = "diagnostic.busy_trace"
    if _require_int(data, "busy_trace_schema_version", "diagnostic") != 1:
        raise FrameToolError("diagnostic.busy_trace_schema_version must be 1")
    if _require_bool(data, "pre_command_idle_failure", "diagnostic") is not False:
        raise FrameToolError("diagnostic reports a pre-command BUSY-idle failure")
    if _require_string(data, "pre_command_busy_stage", "diagnostic") != "none":
        raise FrameToolError("diagnostic.pre_command_busy_stage must be none")
    trace = _require_object(data, "busy_trace", "diagnostic")
    idle_level = _busy_level(trace, "idle_level", label)
    if idle_level != 1:
        raise FrameToolError("diagnostic.busy_trace.idle_level must be 1")
    pre_idle_timeout = _require_int(
        trace, "pre_command_idle_timeout_ms", label, minimum=1
    )
    assert_grace = _require_int(trace, "assert_grace_ms", label, minimum=1)
    if assert_grace != _require_int(data, "busy_assert_grace_ms", "diagnostic"):
        raise FrameToolError(
            "diagnostic busy-trace assertion grace differs from the top-level report"
        )

    stages: dict[str, dict[str, Any]] = {}
    for stage in ("reset", "pon", "drf", "pof", "post_psr"):
        stage_label = f"{label}.{stage}"
        raw = _require_object(trace, stage, label)
        record = {
            "gate_entry_level": _busy_level(
                raw, "gate_entry_level", stage_label, allow_unsampled=stage == "reset"
            ),
            "pre_command_level": _busy_level(
                raw, "pre_command_level", stage_label, allow_unsampled=stage == "reset"
            ),
            "wait_entry_level": _busy_level(raw, "wait_entry_level", stage_label),
            "wait_exit_level": _busy_level(raw, "wait_exit_level", stage_label),
            "pre_command_idle_ok": _require_bool(
                raw, "pre_command_idle_ok", stage_label
            ),
            "assertion_after_idle": _require_bool(
                raw, "assertion_after_idle", stage_label
            ),
            "pre_command_wait_ms": _require_int(
                raw, "pre_command_wait_ms", stage_label
            ),
            "wait_ms": _require_int(raw, "wait_ms", stage_label),
            "assertion_latency_ms": _require_int(
                raw, "assertion_latency_ms", stage_label
            ),
        }
        if record["wait_exit_level"] != idle_level:
            raise FrameToolError(f"{stage_label} did not exit at the idle level")
        if stage == "reset":
            if (
                record["gate_entry_level"] != 255
                or record["pre_command_level"] != 255
                or record["pre_command_idle_ok"] is not False
                or record["assertion_after_idle"] is not False
            ):
                raise FrameToolError(
                    "diagnostic reset BUSY trace contains command-only evidence"
                )
        elif stage in ("pon", "drf", "pof"):
            if (
                record["pre_command_level"] != idle_level
                or record["pre_command_idle_ok"] is not True
                or record["assertion_after_idle"] is not True
                or record["pre_command_wait_ms"] > pre_idle_timeout + 1
                or record["assertion_latency_ms"] > assert_grace
                or record["wait_ms"] != wait_ms[stage]
            ):
                raise FrameToolError(
                    f"{stage_label} does not prove idle-before-command and a new BUSY assertion"
                )
        else:
            if (
                record["pre_command_wait_ms"] != 0
                or record["assertion_after_idle"] is not False
                or record["assertion_latency_ms"] != 0
                or record["wait_ms"] != wait_ms[stage]
            ):
                raise FrameToolError(
                    "diagnostic post-PSR BUSY trace has invalid informational evidence"
                )
        stages[stage] = record

    safe_finish = _require_object(trace, "safe_finish", label)
    safe_before = _busy_level(
        safe_finish, "busy_before_pins_low", f"{label}.safe_finish"
    )
    safe_after = _busy_level(
        safe_finish, "busy_after_pins_low", f"{label}.safe_finish"
    )
    safe_after_5ms = _busy_level(
        safe_finish, "busy_after_5ms", f"{label}.safe_finish"
    )
    if safe_before != idle_level:
        raise FrameToolError(
            "diagnostic safe finish did not begin with BUSY at the idle level"
        )
    final_gpio = _require_object(trace, "final_gpio", label)
    final = {
        "busy": _busy_level(final_gpio, "busy", f"{label}.final_gpio"),
        "rst": _busy_level(final_gpio, "rst", f"{label}.final_gpio"),
        "cs": _busy_level(final_gpio, "cs", f"{label}.final_gpio"),
        "cs2": _busy_level(final_gpio, "cs2", f"{label}.final_gpio"),
    }
    if any(final[key] != 0 for key in ("rst", "cs", "cs2")):
        raise FrameToolError("diagnostic final panel-facing select/reset pins are not low")
    return {
        "schema_version": 1,
        "idle_level": idle_level,
        "pre_command_idle_timeout_ms": pre_idle_timeout,
        "assert_grace_ms": assert_grace,
        "stages": stages,
        "safe_finish": {
            "busy_before_pins_low": safe_before,
            "busy_after_pins_low": safe_after,
            "busy_after_5ms": safe_after_5ms,
        },
        "final_gpio": final,
        "command_edge_contract_verified": True,
        "safe_finish_pin_levels_verified": True,
        "busy_after_rst_low_is_informational": True,
        "post_rst_busy_samples_not_compared": True,
    }


def _validate_diagnostic(
    data: Mapping[str, Any],
    frame: bytes,
    expected_mappings: tuple[ControllerMapping, ControllerMapping],
    version: Mapping[str, Any],
    job: Mapping[str, Any],
    allowed_colors: Optional[Sequence[int]] = None,
) -> dict[str, Any]:
    label = "diagnostic"
    if _require_int(data, "schema_version", label, minimum=1) != 2:
        raise FrameToolError("diagnostic.schema_version must be 2")
    operation_id = _require_nonzero_u32(data, "operation_id", label)
    job_operation_id = _require_nonzero_u32(data, "job_operation_id", label)
    if job_operation_id != operation_id:
        raise FrameToolError(
            "diagnostic job_operation_id does not match driver operation_id"
        )
    required_true = ("valid", "sequence_ok", "mapping_applied")
    for key in required_true:
        if _require_bool(data, key, label) is not True:
            raise FrameToolError(f"diagnostic.{key} is false")
    if _require_bool(data, "running", label) is not False:
        raise FrameToolError("diagnostic report is still running")
    if _require_bool(data, "wait_timeout", label) is not False:
        raise FrameToolError("diagnostic report contains a BUSY timeout")
    if _require_bool(data, "busy_assertion_missing", label) is not False:
        raise FrameToolError("diagnostic reports a missing BUSY assertion")
    if _require_string(data, "busy_missing_stage", label) != "none":
        raise FrameToolError("diagnostic.busy_missing_stage must be none")
    if _require_int(data, "spi_hz", label) != REQUIRED_REFRESH_SPI_HZ:
        raise FrameToolError(f"diagnostic SPI frequency is not {REQUIRED_REFRESH_SPI_HZ}")
    frame_hash = fnv1a(frame)
    if _require_int(data, "input_fnv1a", label) != frame_hash:
        raise FrameToolError("diagnostic input frame hash mismatch")
    if _require_string(data, "firmware_build_tag", label) != version["build_tag"]:
        raise FrameToolError("diagnostic firmware build does not match preflight")
    if _require_string(data, "driver_api_version", label) != version["driver_api"]:
        raise FrameToolError("diagnostic driver API does not match preflight")
    if _require_int(data, "job_id", label, minimum=1) != job["job_id"]:
        raise FrameToolError("diagnostic job id does not match the completed job")
    if _require_string(data, "job_action", label) != job["action"]:
        raise FrameToolError("diagnostic job action does not match the completed job")
    if _require_string(data, "job_state", label) != "completed":
        raise FrameToolError("diagnostic job state is not completed")
    if _require_bool(data, "job_result", label) is not True:
        raise FrameToolError("diagnostic job result is not true")
    for report_key, job_key in (
        ("job_queued_at_ms", "queued_at_ms"),
        ("job_started_at_ms", "started_at_ms"),
        ("job_finished_at_ms", "finished_at_ms"),
    ):
        if _require_u32(data, report_key, label) != job[job_key]:
            raise FrameToolError(
                f"diagnostic {report_key} does not match the completed job"
            )
    if _require_string(data, "timeout_stage", label) != "none":
        raise FrameToolError("diagnostic timeout_stage is not none")
    if _require_string(data, "last_wait_stage", label) != "post-display PSR":
        raise FrameToolError("diagnostic did not reach the safe post-display PSR finish")
    total_ms = _require_int(data, "total_ms", label, minimum=1)
    cs1_upload_ms = _require_int(data, "cs1_upload_ms", label, minimum=1)
    cs2_upload_ms = _require_int(data, "cs2_upload_ms", label, minimum=1)
    wait_ms: dict[str, int] = {}
    for stage in ("pon", "drf", "pof", "post_psr"):
        wait_ms[stage] = _require_int(data, f"{stage}_ms", label)
    for stage in ("pon", "drf", "pof"):
        if _require_bool(data, f"{stage}_busy_seen", label) is not True:
            raise FrameToolError(f"diagnostic.{stage}_busy_seen is false")
    # PON/DRF/POF are controller operations that must assert BUSY.  The
    # post-display PSR write happens after POF in the vendor power-cut
    # sequence; Rev A1 does not assert BUSY for it.  Preserve the sampled flag
    # as evidence, but do not turn the expected false value into a failure.
    post_psr_busy_seen = _require_bool(data, "post_psr_busy_seen", label)
    if not 10_000 <= wait_ms["drf"] <= 60_000:
        raise FrameToolError("diagnostic.drf_ms must be within 10000..60000")
    last_wait_ms = _require_int(data, "last_wait_ms", label)
    if last_wait_ms != wait_ms["post_psr"]:
        raise FrameToolError("diagnostic last_wait_ms does not match post_psr_ms")
    minimum_total_ms = (
        cs1_upload_ms + cs2_upload_ms + sum(wait_ms.values())
    )
    if total_ms < minimum_total_ms:
        raise FrameToolError(
            "diagnostic total_ms is shorter than uploads plus recorded wait stages"
        )
    busy_trace = (
        _validate_busy_trace(data, wait_ms)
        if version["build_tag"] in BUSY_TRACE_BUILD_TAGS
        else None
    )

    raw_mapping = data.get("mapping")
    if not isinstance(raw_mapping, dict):
        raise FrameToolError("diagnostic.mapping must be an object")
    mappings = (
        _mapping_from_diagnostic(raw_mapping, 1),
        _mapping_from_diagnostic(raw_mapping, 2),
    )
    mappings = _validate_mapping_pair(mappings)
    assert mappings is not None
    if mappings != expected_mappings:
        raise FrameToolError("diagnostic mapping differs from the explicit CLI mapping")

    physical: list[dict[str, Any]] = []
    for controller, mapping in enumerate(mappings, start=1):
        if allowed_colors is None:
            stream = controller_stream(frame, mapping)
        else:
            stream = controller_stream(frame, mapping, allowed_colors=allowed_colors)
        expected_hash = fnv1a(stream)
        reported_hash = _require_int(data, f"cs{controller}_dtm_fnv1a", label)
        if reported_hash != expected_hash:
            raise FrameToolError(f"diagnostic CS{controller} DTM hash mismatch")
        physical.append(
            {
                "controller": f"CS{controller}",
                "mapping": _mapping_dict(mapping),
                "dtm_bytes": CONTROLLER_FRAME_BYTES,
                "dtm_fnv1a": expected_hash,
            }
        )
    return {
        "operation_id": operation_id,
        "job_operation_id": job_operation_id,
        "job_driver_operation_identity_matched": True,
        "sequence_verified": True,
        "required_busy_stages_verified": True,
        "post_psr_busy_seen": post_psr_busy_seen,
        "busy_timeout": False,
        "safe_finish_verified": True,
        "busy_trace": busy_trace,
        "physical_controllers": physical,
    }


def perform_refresh(
    base_url: str,
    frame: bytes | bytearray | memoryview,
    *,
    expected_mappings: Optional[Sequence[ControllerMapping]] = None,
    allowed_colors: Optional[Sequence[int]] = None,
    job_timeout_s: float = DEFAULT_JOB_TIMEOUT_S,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    requester: Optional[HttpRequester] = None,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    # This must remain the first operation: malformed frames must never cause
    # mapping/URL handling or any device request.
    frame_bytes = _validated_frame_bytes(frame, allowed_colors)
    mapping_pair = _require_refresh_mapping_pair(expected_mappings)
    request = requester or http_request
    base_url = _normalize_base_url(base_url)
    version = _preflight_version(base_url, request, mapping_pair)
    frame_hash = fnv1a(frame_bytes)
    status, body = request(
        base_url, "/api/frame", method="POST", data=frame_bytes, timeout=20.0
    )
    _expect_status(status, 202, body, "frame refresh enqueue")
    queued = _json_object(body, "frame refresh enqueue")
    _validate_transfer_response(queued, frame_hash, "frame refresh enqueue")
    job_id = _require_int(queued, "job_id", "frame refresh enqueue", minimum=1)
    job = _wait_for_job(
        base_url,
        job_id,
        frame_hash,
        request,
        timeout_s=job_timeout_s,
        poll_interval_s=poll_interval_s,
        sleeper=sleeper,
        clock=clock,
    )
    status, body = request(
        base_url, "/api/diagnostic/report", method="GET", data=None, timeout=20.0
    )
    _expect_status(status, 200, body, "diagnostic report")
    diagnostic = _validate_diagnostic(
        _json_object(body, "diagnostic report"), frame_bytes, mapping_pair, version, job,
        allowed_colors=allowed_colors,
    )
    verified_scope = [
        "canonical_frame_dimensions_and_physical_color_codes",
        "firmware_build_api_spi_psram_and_mapping_preflight",
        "frame_upload_bytes_and_fnv1a",
        "job_identity_state_result_and_frame_hash",
        "diagnostic_immutable_driver_operation_identity",
        "diagnostic_build_api_job_mapping_and_dtm_hashes",
        "diagnostic_sequence_busy_timing_and_safe_finish_evidence",
    ]
    if diagnostic["busy_trace"] is not None:
        verified_scope.append(
            "diagnostic_idle_before_command_busy_edges_and_safe_finish_pin_snapshot"
        )
    return {
        "mode": "refresh",
        "protocol_verified": True,
        "hardware_tested": False,
        "verified_scope": verified_scope,
        "manual_observation_required": [
            "full_panel_visual_result",
            "power_supply_cv_and_current",
            "L1_L2_temperature",
        ],
        "preflight": version,
        "job_id": job_id,
        "job": job,
        "diagnostic": diagnostic,
    }


def _parse_mapping(value: str) -> ControllerMapping:
    fields = [field.strip() for field in value.split(",")]
    if len(fields) != 4 or any(field not in ("0", "1") for field in fields):
        raise argparse.ArgumentTypeError(
            "mapping must be SOURCE_HALF,FLIP_X,FLIP_Y,NIBBLE_SWAP using 0 or 1"
        )
    numbers = [int(field) for field in fields]
    return ControllerMapping(numbers[0], *(bool(number) for number in numbers[1:]))


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected a positive number") from error
    if not 0 < parsed < float("inf"):
        raise argparse.ArgumentTypeError("expected a positive finite number")
    return parsed


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _is_hard_link_to_frozen_file(path: Path, frozen_directory: Path) -> bool:
    """Return true if an existing path aliases any frozen production file."""

    if not path.exists():
        return False
    try:
        for candidate in frozen_directory.rglob("*"):
            if candidate.is_file() and path.samefile(candidate):
                return True
    except OSError as error:
        raise FrameToolError(
            f"could not verify output against frozen production files: {error}"
        ) from error
    return False


def write_frame(path: Path, frame: bytes, *, force: bool = False) -> Path:
    resolved = path.resolve(strict=False)
    frozen = FROZEN_PRODUCTION_DIR.resolve(strict=False)
    if _is_within(resolved, frozen):
        raise FrameToolError("refusing to write inside the frozen production directory")
    if force and _is_hard_link_to_frozen_file(resolved, frozen):
        raise FrameToolError(
            "refusing to replace a hard-link alias of a frozen production file"
        )
    try:
        with resolved.open("wb" if force else "xb") as destination:
            destination.write(frame)
    except FileExistsError as error:
        raise FrameToolError("output already exists; pass --force to replace it") from error
    except OSError as error:
        raise FrameToolError(f"could not write output: {error}") from error
    return resolved


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--pattern", choices=sorted(FIXTURE_NAMES), default="map-orient-v1")
    parser.add_argument("--output", type=Path, help="optionally write the canonical raw frame")
    parser.add_argument("--force", action="store_true", help="allow replacing an existing output")
    parser.add_argument("--url", help="ESP32 root URL; default mode is non-refreshing ingress")
    parser.add_argument(
        "--refresh", action="store_true", help="queue one protocol-verified /api/frame refresh"
    )
    parser.add_argument(
        "--confirm-cold-start",
        action="store_true",
        help="required with --refresh after a >=10 s J2-1 power-off",
    )
    parser.add_argument(
        "--controller-mapping",
        action="append",
        type=_parse_mapping,
        metavar="HALF,FLIP_X,FLIP_Y,NIBBLE_SWAP",
        help="explicit mapping; provide exactly twice in CS1, CS2 order",
    )
    parser.add_argument("--job-timeout", type=_positive_float, default=DEFAULT_JOB_TIMEOUT_S)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.refresh and (not args.url or not args.confirm_cold_start):
        print("ERROR: --refresh requires --url and --confirm-cold-start", file=sys.stderr)
        return 2
    if args.refresh and (
        args.controller_mapping is None or len(args.controller_mapping) != 2
    ):
        print(
            "ERROR: --refresh requires exactly two --controller-mapping values "
            "ordered CS1 then CS2",
            file=sys.stderr,
        )
        return 2
    if args.force and not args.output:
        print("ERROR: --force requires --output", file=sys.stderr)
        return 2
    if args.confirm_cold_start and not args.refresh:
        print("ERROR: --confirm-cold-start is only valid with --refresh", file=sys.stderr)
        return 2
    try:
        mappings = _validate_mapping_pair(args.controller_mapping)
        frame = _validated_frame_bytes(generate_fixture(args.pattern))
        report = build_offline_report(args.pattern, frame, mappings)
        if not report["offline_verified"]:
            raise FrameToolError("deterministic frame self-test failed; refusing output/upload")
        if args.output:
            report["output"] = str(write_frame(args.output, frame, force=args.force))
        if args.url:
            if args.refresh:
                report["network"] = perform_refresh(
                    args.url,
                    frame,
                    expected_mappings=mappings,
                    job_timeout_s=args.job_timeout,
                )
            else:
                report["network"] = perform_ingress(args.url, frame)
    except FrameToolError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
