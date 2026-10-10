#!/usr/bin/env python3
"""Run the frozen RC2G cold-boot MAP baseline exactly once.

This runner is a separate, fail-closed authorization path for the first
visible refresh after flashing and rebooting the BUSY-edge instrumented RC2G
firmware.  Before any device request it validates the canonical
``map-orient-v1`` bytes and atomically consumes one workspace-global claim.
It then proves the device is at the exact fresh-boot state (job 0/idle and no
completed diagnostic), permits at most one ``POST /api/frame``, and requires
the resulting MAP job 1/operation 1 to have the frozen controller DTM hashes,
the RC2G BUSY-edge trace, nominal timing, and low panel-facing output pins.

There is no retry or recovery path.  After the claim exists, every failure is
``unknown_do_not_retry``.  Completed reports, raw GPIO snapshots, and
best-effort read-only evidence are retained whenever they can be obtained.
BUSY sampled after RST is driven low is evidence only; RST/CS1/CS2 must be low.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable, Mapping, Optional, Sequence
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.epd_frame import (  # noqa: E402
    CONTROLLER_FRAME_BYTES,
    FRAME_BYTES,
    HEIGHT,
    WIDTH,
    ControllerMapping,
    controller_stream,
    fnv1a,
    generate_fixture,
    validate_frame,
    verify_fixture,
)
from tools.local_path_safety import (  # noqa: E402
    LocalPathSafetyError,
    require_local_regular_path_syntax,
)
from tools.mf1750_frame_tool import (  # noqa: E402
    BUSY_TRACE_BUILD_TAGS,
    DEFAULT_JOB_TIMEOUT_S,
    DEFAULT_POLL_INTERVAL_S,
    FrameToolError,
    _preflight_version,
    _validate_diagnostic,
    _validate_job,
    http_request,
    perform_refresh,
)


SCHEMA_VERSION = 1
LOCK_FILENAME = "ATTEMPT-LOCK.json"
RESULT_FILENAME = "RC2G-MAP-BASELINE-RESULT.json"
LOCK_KIND = "mf1750-g1-s1-rc2g-map-baseline-attempt-lock"
RESULT_KIND = "mf1750-g1-s1-rc2g-map-baseline-result"
CLAIM_KIND = "mf1750-g1-s1-rc2g-map-baseline-claim"
CLAIM_REGISTRY_ID = "workspace-g1-s1-rc2g-map-baseline-registry-v1"
FIXED_ACTION_ID = "rc2g-cold-boot-map-orient-v1-job1-op1-once-v1"
DEFAULT_AUTHORIZATION_REGISTRY = (
    REPO_ROOT / ".test-output" / "hardware" / ".g1_s1_rc2g_map_baseline_registry"
)

EXPECTED_BUILD_TAG = (
    "MF1750_DRIVER_RC2G_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_"
    "PSRFIX_WEBPHOTO_PHYSICAL_BUSYEDGE_2026-08-07"
)
EXPECTED_DRIVER_API = "MF1750_R16_CASCADE_V3"
EXPECTED_REFRESH_SPI_HZ = 1_000_000
FIXED_CONTROLLER_MAPPINGS = (
    ControllerMapping(0, False, False, False),
    ControllerMapping(1, False, False, False),
)

FIXTURE_NAME = "map-orient-v1"
EXPECTED_FRAME_SHA256 = "1deedf924e40c676c2080fec08dfe5da10a8c1bb53b699ec4a85b0b6101b5c36"
EXPECTED_FRAME_FNV1A = 0x9D04142D
EXPECTED_CS1_DTM_SHA256 = "d1ce843dca5ec7a615329f6a118dc9bd03498f686f1b5bfe55d51a97556eccaa"
EXPECTED_CS1_DTM_FNV1A = 0xF26832DD
EXPECTED_CS2_DTM_SHA256 = "ae0bc93cc2cf736fc2f9c209865c93443e90271b992647a8d8c7a5761e08c791"
EXPECTED_CS2_DTM_FNV1A = 0xFE199FF5
EXPECTED_TARGET_JOB_ID = 1
EXPECTED_TARGET_OPERATION_ID = 1
EXPECTED_PANEL_OUTPUTS_LOW = {"rst": 0, "cs": 0, "cs2": 0}

# These gates are deliberately much narrower than the generic frame tool's
# validity envelope.  They contain both known nominal MAP runs (~34.17 s,
# PON ~181 ms, DRF ~21.7 s, POF ~140 ms) while rejecting the prior tens-of-
# seconds PON anomaly as a nominal RC2G baseline.
NOMINAL_TIMING_RANGES_MS = {
    "total_ms": (28_000, 45_000),
    "cs1_upload_ms": (1_500, 5_000),
    "cs2_upload_ms": (1_500, 5_000),
    "pon_ms": (50, 2_000),
    "drf_ms": (18_000, 26_000),
    "pof_ms": (50, 1_000),
    "post_psr_ms": (0, 100),
}
MAX_QUEUE_DELAY_MS = 5_000
MAX_JOB_DRIVER_DURATION_DELTA_MS = 2_000

REQUIRED_AUTHORIZATION_CONFIRMATION = (
    "AUTHORIZE_ONE_VISIBLE_RC2G_COLD_BOOT_MAP_ORIENT_V1_BASELINE_JOB1_OP1__"
    "NO_RETRY_NO_RECOVERY"
)


class Rc2gMapBaselineError(RuntimeError):
    """The baseline was rejected before its permanent claim existed."""


class Rc2gMapBaselineUnknown(Rc2gMapBaselineError):
    """The claim exists, so the exact baseline must never be attempted again."""


@dataclass(frozen=True)
class _FixtureSnapshot:
    frame: bytes
    frame_sha256: str
    controllers: tuple[Mapping[str, Any], Mapping[str, Any]]


@dataclass(frozen=True)
class _Claim:
    registry: Path
    filename: str
    payload_sha256: str
    record: Mapping[str, Any]

    def reference(self) -> dict[str, Any]:
        return {
            "registry_id": CLAIM_REGISTRY_ID,
            "file": self.filename,
            "sha256": self.payload_sha256,
            "attempt_id": self.record["attempt_id"],
            "state": self.record["state"],
        }


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise Rc2gMapBaselineError(
            f"canonical JSON encoding failed: {error}"
        ) from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _mapping_record(mapping: ControllerMapping) -> dict[str, int | bool]:
    return {
        "source_half": mapping.source_half,
        "flip_x": mapping.flip_x,
        "flip_y": mapping.flip_y,
        "nibble_swap": mapping.nibble_swap,
    }


def _controller_records() -> list[dict[str, Any]]:
    sha256s = (EXPECTED_CS1_DTM_SHA256, EXPECTED_CS2_DTM_SHA256)
    fnv1as = (EXPECTED_CS1_DTM_FNV1A, EXPECTED_CS2_DTM_FNV1A)
    return [
        {
            "controller": f"CS{index}",
            "mapping": _mapping_record(mapping),
            "dtm_bytes": CONTROLLER_FRAME_BYTES,
            "dtm_sha256": sha256,
            "dtm_fnv1a": f"0x{hash_value:08X}",
        }
        for index, (mapping, sha256, hash_value) in enumerate(
            zip(FIXED_CONTROLLER_MAPPINGS, sha256s, fnv1as), start=1
        )
    ]


EXACT_ACTION = {
    "action_id": FIXED_ACTION_ID,
    "method": "POST",
    "endpoint": "/api/frame",
    "maximum_posts": 1,
    "automatic_retry": False,
    "automatic_recovery": False,
    "required_initial_job_id": 0,
    "required_initial_job_state": "idle",
    "required_initial_diagnostic": "no_completed_job_report",
    "target_job_id": EXPECTED_TARGET_JOB_ID,
    "target_operation_id": EXPECTED_TARGET_OPERATION_ID,
}
ACTION_IDENTITY = {
    "schema_version": SCHEMA_VERSION,
    "kind": "mf1750-g1-s1-rc2g-map-baseline-action-identity",
    "action_id": FIXED_ACTION_ID,
    "firmware": {
        "build_tag": EXPECTED_BUILD_TAG,
        "driver_api": EXPECTED_DRIVER_API,
        "refresh_spi_hz": EXPECTED_REFRESH_SPI_HZ,
        "busy_trace_required": True,
        "busy_trace_schema_version": 1,
    },
    "frame": {
        "fixture": FIXTURE_NAME,
        "bytes": FRAME_BYTES,
        "sha256": EXPECTED_FRAME_SHA256,
        "fnv1a": f"0x{EXPECTED_FRAME_FNV1A:08X}",
        "controllers": _controller_records(),
    },
    "timing_ranges_ms": {
        key: {"minimum": limits[0], "maximum": limits[1]}
        for key, limits in NOMINAL_TIMING_RANGES_MS.items()
    },
    "gpio_contract": {
        "required_low_outputs": dict(EXPECTED_PANEL_OUTPUTS_LOW),
        "busy_after_rst_low": "informational_0_or_1",
    },
    "exact_action": dict(EXACT_ACTION),
}
ACTION_IDENTITY_SHA256 = "8f83d951986f403a5e531558c1a663deae99988915c7bd4e367b00bf59e8489d"
AUTHORIZATION_CONFIRMATION_SHA256 = (
    "3b05288f37768eb8dda4dc9fb119d13451b9e10c6ee737fef0e544fa670ae535"
)
if _sha256(_canonical_json(ACTION_IDENTITY)) != ACTION_IDENTITY_SHA256:
    raise RuntimeError("frozen RC2G MAP baseline action identity changed")
if (
    _sha256(REQUIRED_AUTHORIZATION_CONFIRMATION.encode("ascii"))
    != AUTHORIZATION_CONFIRMATION_SHA256
):
    raise RuntimeError("frozen RC2G MAP baseline authorization string changed")

CLASSIFICATION = {
    "experimental": True,
    "rc2g_instrumentation_baseline": True,
    "known_map_visual_baseline": True,
    "formal": False,
    "hardware_qualified": False,
    "hardware_tested": False,
    "algorithm_qualification": False,
}
REQUIRED_VERIFIED_SCOPE = frozenset(
    {
        "canonical_frame_dimensions_and_physical_color_codes",
        "firmware_build_api_spi_psram_and_mapping_preflight",
        "frame_upload_bytes_and_fnv1a",
        "job_identity_state_result_and_frame_hash",
        "diagnostic_immutable_driver_operation_identity",
        "diagnostic_build_api_job_mapping_and_dtm_hashes",
        "diagnostic_sequence_busy_timing_and_safe_finish_evidence",
        "diagnostic_idle_before_command_busy_edges_and_safe_finish_pin_snapshot",
    }
)


def _validate_fixture_snapshot() -> _FixtureSnapshot:
    try:
        frame = generate_fixture(FIXTURE_NAME)
        verify_fixture(FIXTURE_NAME, frame)
        validate_frame(frame)
    except (KeyError, ValueError) as error:
        raise Rc2gMapBaselineError(f"MAP fixture validation failed: {error}") from error
    frame_sha256 = _sha256(frame)
    if frame_sha256 != EXPECTED_FRAME_SHA256 or fnv1a(frame) != EXPECTED_FRAME_FNV1A:
        raise Rc2gMapBaselineError("MAP frame identity changed")
    streams = tuple(
        controller_stream(frame, mapping) for mapping in FIXED_CONTROLLER_MAPPINGS
    )
    if tuple(_sha256(stream) for stream in streams) != (
        EXPECTED_CS1_DTM_SHA256,
        EXPECTED_CS2_DTM_SHA256,
    ) or tuple(fnv1a(stream) for stream in streams) != (
        EXPECTED_CS1_DTM_FNV1A,
        EXPECTED_CS2_DTM_FNV1A,
    ):
        raise Rc2gMapBaselineError("MAP controller DTM identities changed")
    return _FixtureSnapshot(frame, frame_sha256, tuple(_controller_records()))


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _prepare_result_destination(result_dir: Path) -> Path:
    try:
        require_local_regular_path_syntax(result_dir, label="MAP baseline result directory")
    except LocalPathSafetyError as error:
        raise Rc2gMapBaselineError(str(error)) from error
    if os.path.lexists(result_dir):
        raise Rc2gMapBaselineError(
            "result directory already exists; refusing overwrite or rerun"
        )
    try:
        parent = result_dir.parent.resolve(strict=True)
    except OSError as error:
        raise Rc2gMapBaselineError(f"result parent does not exist: {error}") from error
    if not parent.is_dir():
        raise Rc2gMapBaselineError("result parent must be a directory")
    destination = parent / result_dir.name
    if os.path.lexists(destination):
        raise Rc2gMapBaselineError(
            "result directory already exists; refusing overwrite or rerun"
        )
    return destination


def _authorization_registry() -> Path:
    path = DEFAULT_AUTHORIZATION_REGISTRY
    try:
        require_local_regular_path_syntax(path, label="MAP baseline authorization registry")
        if os.path.lexists(path) and path.is_symlink():
            raise Rc2gMapBaselineError("MAP baseline registry must not be a symlink")
        parent = path.parent.resolve(strict=True)
        workspace = REPO_ROOT.resolve(strict=True)
        if not parent.is_dir() or not _is_within(parent, workspace):
            raise Rc2gMapBaselineError(
                "MAP baseline registry parent must be in the workspace"
            )
        path.mkdir(exist_ok=True)
        registry = path.resolve(strict=True)
    except Rc2gMapBaselineError:
        raise
    except (LocalPathSafetyError, OSError) as error:
        raise Rc2gMapBaselineError(
            f"could not create MAP baseline registry: {error}"
        ) from error
    if path.is_symlink() or not registry.is_dir() or not _is_within(registry, workspace):
        raise Rc2gMapBaselineError("MAP baseline registry escaped the workspace")
    return registry


def _claim_action(
    snapshot: _FixtureSnapshot,
    *,
    attempt_id: str,
    claimed_at_utc: str,
    result_destination: Path,
    confirmations: Mapping[str, Any],
) -> _Claim:
    registry = _authorization_registry()
    if _is_within(result_destination, registry):
        raise Rc2gMapBaselineError(
            "result directory must not be inside the MAP baseline registry"
        )
    record = {
        "schema_version": SCHEMA_VERSION,
        "kind": CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "action_id": FIXED_ACTION_ID,
        "action_identity": dict(ACTION_IDENTITY),
        "action_identity_sha256": ACTION_IDENTITY_SHA256,
        "authorization_confirmation_sha256": AUTHORIZATION_CONFIRMATION_SHA256,
        "attempt_id": attempt_id,
        "claimed_at_utc": claimed_at_utc,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "authorization_consumed_permanently": True,
        "frame_sha256": snapshot.frame_sha256,
        "result_directory": str(result_destination),
        "confirmations": dict(confirmations),
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "formal": False,
        "hardware_qualified": False,
        "hardware_tested": False,
    }
    payload = _canonical_json(record)
    claim = _Claim(registry, FIXED_ACTION_ID, _sha256(payload), record)
    destination = registry / FIXED_ACTION_ID
    temporary = registry / f".{FIXED_ACTION_ID}.tmp-{uuid.uuid4().hex}"
    linked = False
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        linked = True
        try:
            temporary.unlink()
        except OSError:
            pass
    except FileExistsError as error:
        if linked:
            raise Rc2gMapBaselineUnknown(
                "MAP baseline claim exists after cleanup failure; do not retry"
            ) from error
        raise Rc2gMapBaselineError(
            "this RC2G MAP baseline action was already permanently consumed; do not retry"
        ) from error
    except BaseException as error:
        if linked:
            raise Rc2gMapBaselineUnknown(
                "MAP baseline claim exists after claim processing failure; do not retry"
            ) from error
        if not isinstance(error, OSError):
            raise
        raise Rc2gMapBaselineError(
            f"could not atomically claim RC2G MAP baseline: {error}"
        ) from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except BaseException:
            pass
    return claim


def _create_result_directory(destination: Path, claim: _Claim) -> Path:
    if _is_within(destination, claim.registry):
        raise Rc2gMapBaselineError("result directory overlaps the claim registry")
    try:
        destination.mkdir()
    except FileExistsError as error:
        raise Rc2gMapBaselineError("result directory appeared; refusing overwrite") from error
    except OSError as error:
        raise Rc2gMapBaselineError(f"could not create result directory: {error}") from error
    return destination


def _atomic_new_file(directory: Path, name: str, payload: bytes) -> None:
    destination = directory / name
    temporary = directory / f".{name}.tmp-{uuid.uuid4().hex}"
    linked = False
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        linked = True
        try:
            temporary.unlink()
        except OSError:
            pass
    except FileExistsError as error:
        raise Rc2gMapBaselineError(f"{name} already exists; refusing overwrite") from error
    except OSError as error:
        if linked:
            raise Rc2gMapBaselineError(
                f"{name} committed but staging cleanup failed"
            ) from error
        raise Rc2gMapBaselineError(f"could not atomically write {name}: {error}") from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except BaseException:
            pass


class _AuditedRequester:
    """Allow only evidence GETs and one issued POST /api/frame."""

    _ALLOWED = {
        ("GET", "/api/version"),
        ("GET", "/api/job"),
        ("GET", "/api/diagnostic/report"),
        ("GET", "/api/diagnostic/status"),
        ("POST", "/api/frame"),
    }

    def __init__(self, requester: Callable[..., tuple[int, str]]) -> None:
        self._requester = requester
        self.calls: list[dict[str, Any]] = []
        self.post_attempt_count = 0
        self.post_issued_count = 0

    def __call__(
        self,
        base_url: str,
        endpoint: str,
        *,
        method: str,
        data: bytes | None,
        timeout: float,
    ) -> tuple[int, str]:
        normalized_method = method.upper()
        entry: dict[str, Any] = {
            "index": len(self.calls) + 1,
            "method": normalized_method,
            "endpoint": endpoint,
            "timeout_seconds": timeout,
            "request_bytes": len(data) if data is not None else 0,
        }
        if data is not None:
            entry["request_sha256"] = _sha256(bytes(data))
        self.calls.append(entry)
        if (normalized_method, endpoint) not in self._ALLOWED:
            entry["outcome"] = "blocked_route"
            raise Rc2gMapBaselineError(
                f"request route is not allowlisted: {normalized_method} {endpoint}"
            )
        if normalized_method == "POST":
            self.post_attempt_count += 1
            if endpoint != "/api/frame" or self.post_issued_count >= 1:
                entry["outcome"] = "blocked_additional_post"
                raise Rc2gMapBaselineError(
                    "RC2G MAP baseline permits at most one issued POST /api/frame"
                )
            self.post_issued_count += 1
        try:
            status, body = self._requester(
                base_url,
                endpoint,
                method=normalized_method,
                data=data,
                timeout=timeout,
            )
        except BaseException as error:
            entry["outcome"] = "exception"
            entry["error"] = {"type": type(error).__name__, "message": str(error)}
            raise
        entry["outcome"] = "response"
        entry["status"] = status
        if isinstance(body, str):
            encoded = body.encode("utf-8")
            entry["response_bytes"] = len(encoded)
            entry["response_sha256"] = _sha256(encoded)
        else:
            entry["response_bytes"] = None
            entry["response_sha256"] = None
        return status, body

    def snapshot(self) -> dict[str, Any]:
        return {
            "post_attempt_count": self.post_attempt_count,
            "post_issued_count": self.post_issued_count,
            "calls": [dict(call) for call in self.calls],
        }


def _strict_json_object(body: str, *, label: str) -> Mapping[str, Any]:
    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate key {key!r}")
            value[key] = item
        return value

    try:
        value = json.loads(
            body,
            object_pairs_hook=reject_duplicate,
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise Rc2gMapBaselineError(f"{label} is not strict JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise Rc2gMapBaselineError(f"{label} must be a JSON object")
    return value


def _get_json_object(
    base_url: str,
    endpoint: str,
    *,
    label: str,
    requester: _AuditedRequester,
) -> Mapping[str, Any]:
    status, body = requester(
        base_url, endpoint, method="GET", data=None, timeout=20.0
    )
    if status != 200:
        excerpt = body[:200] if isinstance(body, str) else repr(body)[:200]
        raise Rc2gMapBaselineError(f"{label} returned HTTP {status}: {excerpt}")
    return _strict_json_object(body, label=label)


def _expected_version_static() -> dict[str, Any]:
    return {
        "build_tag": EXPECTED_BUILD_TAG,
        "driver_api": EXPECTED_DRIVER_API,
        "panel": f"{WIDTH}x{HEIGHT}",
        "frame_bytes": FRAME_BYTES,
        "refresh_spi_hz": EXPECTED_REFRESH_SPI_HZ,
        "controller_mappings": [
            {"controller": f"CS{index}", "mapping": _mapping_record(mapping)}
            for index, mapping in enumerate(FIXED_CONTROLLER_MAPPINGS, start=1)
        ],
    }


def _validate_version(version: Mapping[str, Any], *, label: str) -> None:
    if EXPECTED_BUILD_TAG not in BUSY_TRACE_BUILD_TAGS:
        raise Rc2gMapBaselineError(
            "EXPECTED_BUILD_TAG must remain an allowlisted BUSY-trace build"
        )
    if any(version.get(key) != value for key, value in _expected_version_static().items()):
        raise Rc2gMapBaselineError(
            f"{label} build/API/panel/SPI/mappings are not the frozen RC2G identity"
        )


def _validate_gpio_snapshot(value: Mapping[str, Any], *, label: str) -> dict[str, int]:
    if set(value) != {"busy", "rst", "cs", "cs2"}:
        raise Rc2gMapBaselineError(f"{label} fields are not the strict GPIO contract")
    snapshot: dict[str, int] = {}
    for key in ("busy", "rst", "cs", "cs2"):
        level = value.get(key)
        if type(level) is not int or level not in (0, 1):
            raise Rc2gMapBaselineError(f"{label}.{key} must be integer level 0 or 1")
        snapshot[key] = level
    if any(snapshot[key] != expected for key, expected in EXPECTED_PANEL_OUTPUTS_LOW.items()):
        raise Rc2gMapBaselineError(f"{label} RST/CS1/CS2 outputs are not all low")
    return snapshot


def _validate_fresh_boot_state(
    base_url: str, requester: _AuditedRequester
) -> Mapping[str, Any]:
    try:
        version = _preflight_version(base_url, requester, FIXED_CONTROLLER_MAPPINGS)
    except FrameToolError as error:
        raise Rc2gMapBaselineError(f"fresh-boot firmware preflight failed: {error}") from error
    _validate_version(version, label="fresh-boot firmware")
    job = _get_json_object(
        base_url, "/api/job", label="fresh-boot job", requester=requester
    )
    expected_job = {
        "job_id": 0,
        "action": "none",
        "state": "idle",
        "result": None,
        "queued_at_ms": 0,
        "started_at_ms": 0,
        "finished_at_ms": 0,
        "frame_fnv1a": 0,
    }
    if job != expected_job:
        raise Rc2gMapBaselineError(
            "device is not the exact fresh boot job0/idle state"
        )
    diagnostic = _get_json_object(
        base_url,
        "/api/diagnostic/report",
        label="fresh-boot diagnostic",
        requester=requester,
    )
    expected_diagnostic = {
        "schema_version": 2,
        "valid": False,
        "error": "no_completed_job_report",
    }
    if diagnostic != expected_diagnostic:
        raise Rc2gMapBaselineError(
            "fresh boot already has a completed or unexpected diagnostic report"
        )
    gpio_raw = _get_json_object(
        base_url,
        "/api/diagnostic/status",
        label="fresh-boot GPIO",
        requester=requester,
    )
    gpio = _validate_gpio_snapshot(gpio_raw, label="fresh-boot GPIO")
    return {
        "version": dict(version),
        "job_raw": dict(job),
        "diagnostic_raw": dict(diagnostic),
        "gpio_status_raw": dict(gpio),
        "busy_after_rst_low_is_informational": True,
    }


def _validate_required_busy_trace(
    diagnostic: Mapping[str, Any], *, label: str
) -> Mapping[str, Any]:
    trace = diagnostic.get("busy_trace")
    if not isinstance(trace, Mapping):
        raise Rc2gMapBaselineError(f"{label} nested BUSY trace is required")
    if (
        trace.get("schema_version") != 1
        or trace.get("idle_level") != 1
        or trace.get("command_edge_contract_verified") is not True
        or trace.get("safe_finish_pin_levels_verified") is not True
        or trace.get("busy_after_rst_low_is_informational") is not True
    ):
        raise Rc2gMapBaselineError(f"{label} BUSY trace contract is not verified")
    stages = trace.get("stages")
    if not isinstance(stages, Mapping) or set(stages) != {
        "reset",
        "pon",
        "drf",
        "pof",
        "post_psr",
    }:
        raise Rc2gMapBaselineError(f"{label} BUSY trace stages are incomplete")
    for stage_name in ("pon", "drf", "pof"):
        stage = stages.get(stage_name)
        if (
            not isinstance(stage, Mapping)
            or stage.get("pre_command_level") != 1
            or stage.get("pre_command_idle_ok") is not True
            or stage.get("assertion_after_idle") is not True
            or stage.get("wait_exit_level") != 1
        ):
            raise Rc2gMapBaselineError(
                f"{label} {stage_name.upper()} lacks idle-before-command/new-BUSY-edge proof"
            )
    safe_finish = trace.get("safe_finish")
    final_gpio = trace.get("final_gpio")
    if not isinstance(safe_finish, Mapping) or safe_finish.get("busy_before_pins_low") != 1:
        raise Rc2gMapBaselineError(
            f"{label} did not begin safe finish with BUSY at the idle level"
        )
    if not isinstance(final_gpio, Mapping):
        raise Rc2gMapBaselineError(f"{label} final GPIO trace is missing")
    _validate_gpio_snapshot(final_gpio, label=f"{label} final GPIO trace")
    return trace


def _u32_duration(start: int, finish: int) -> int:
    return (finish - start) & 0xFFFFFFFF


def _validate_nominal_timing(
    job: Mapping[str, Any], raw_diagnostic: Mapping[str, Any]
) -> dict[str, int]:
    timestamps = tuple(
        job.get(key) for key in ("queued_at_ms", "started_at_ms", "finished_at_ms")
    )
    if any(type(value) is not int or not 0 <= value <= 0xFFFFFFFF for value in timestamps):
        raise Rc2gMapBaselineError("MAP job timing fields are not uint32")
    queued, started, finished = timestamps
    queue_delay = _u32_duration(queued, started)
    job_duration = _u32_duration(started, finished)
    if queue_delay > MAX_QUEUE_DELAY_MS:
        raise Rc2gMapBaselineError("MAP job queue delay is outside the nominal gate")
    total_minimum, total_maximum = NOMINAL_TIMING_RANGES_MS["total_ms"]
    if not total_minimum <= job_duration <= total_maximum:
        raise Rc2gMapBaselineError("MAP job duration is outside the nominal gate")
    values: dict[str, int] = {}
    for field, (minimum, maximum) in NOMINAL_TIMING_RANGES_MS.items():
        value = raw_diagnostic.get(field)
        if type(value) is not int or not minimum <= value <= maximum:
            raise Rc2gMapBaselineError(
                f"MAP diagnostic {field} is outside nominal {minimum}..{maximum} ms"
            )
        values[field] = value
    if abs(job_duration - values["total_ms"]) > MAX_JOB_DRIVER_DURATION_DELTA_MS:
        raise Rc2gMapBaselineError(
            "MAP job duration and driver total differ beyond the nominal gate"
        )
    return {
        **values,
        "queue_delay_ms": queue_delay,
        "job_duration_ms": job_duration,
    }


def _expected_physical_records() -> list[dict[str, Any]]:
    return [
        {
            "controller": record["controller"],
            "mapping": record["mapping"],
            "dtm_bytes": record["dtm_bytes"],
            "dtm_fnv1a": int(record["dtm_fnv1a"], 16),
        }
        for record in _controller_records()
    ]


def _validate_completed_map_evidence(
    report: object,
    raw_job: Mapping[str, Any],
    raw_diagnostic: Mapping[str, Any],
    post_gpio_raw: Mapping[str, Any],
    frame: bytes,
) -> Mapping[str, Any]:
    if not isinstance(report, Mapping):
        raise Rc2gMapBaselineError("MAP network report must be an object")
    if report.get("protocol_verified") is not True or report.get("hardware_tested") is not False:
        raise Rc2gMapBaselineError("MAP report lost its fail-closed classification")
    scope = report.get("verified_scope")
    if not isinstance(scope, list) or not REQUIRED_VERIFIED_SCOPE.issubset(scope):
        raise Rc2gMapBaselineError("MAP report lacks the RC2G BUSY-trace verified scope")
    version = report.get("preflight")
    if not isinstance(version, Mapping):
        raise Rc2gMapBaselineError("MAP report preflight is missing")
    _validate_version(version, label="MAP refresh firmware")
    try:
        state = _validate_job(raw_job, EXPECTED_TARGET_JOB_ID, EXPECTED_FRAME_FNV1A)
    except FrameToolError as error:
        raise Rc2gMapBaselineError(f"MAP job1 validation failed: {error}") from error
    if state != "completed":
        raise Rc2gMapBaselineError("MAP job1 is not completed")
    report_job = report.get("job")
    if (
        report.get("job_id") != EXPECTED_TARGET_JOB_ID
        or not isinstance(report_job, Mapping)
        or dict(report_job) != dict(raw_job)
    ):
        raise Rc2gMapBaselineError("MAP report and raw job1 evidence differ")
    try:
        normalized = _validate_diagnostic(
            raw_diagnostic,
            frame,
            FIXED_CONTROLLER_MAPPINGS,
            version,
            raw_job,
        )
    except FrameToolError as error:
        raise Rc2gMapBaselineError(
            f"MAP raw diagnostic validation failed: {error}"
        ) from error
    report_diagnostic = report.get("diagnostic")
    if not isinstance(report_diagnostic, Mapping) or dict(report_diagnostic) != normalized:
        raise Rc2gMapBaselineError(
            "MAP normalized and independently read diagnostic evidence differ"
        )
    if (
        normalized.get("operation_id") != EXPECTED_TARGET_OPERATION_ID
        or normalized.get("job_operation_id") != EXPECTED_TARGET_OPERATION_ID
        or normalized.get("job_driver_operation_identity_matched") is not True
        or normalized.get("sequence_verified") is not True
        or normalized.get("required_busy_stages_verified") is not True
        or normalized.get("busy_timeout") is not False
        or normalized.get("safe_finish_verified") is not True
        or normalized.get("physical_controllers") != _expected_physical_records()
    ):
        raise Rc2gMapBaselineError(
            "MAP result is not the exact nominal job1/operation1/DTM identity"
        )
    trace = _validate_required_busy_trace(normalized, label="MAP job1 diagnostic")
    timing = _validate_nominal_timing(raw_job, raw_diagnostic)
    post_gpio = _validate_gpio_snapshot(post_gpio_raw, label="post-MAP GPIO")
    return {
        "network_report": dict(report),
        "job_raw": dict(raw_job),
        "diagnostic_raw": dict(raw_diagnostic),
        "diagnostic_validated": dict(normalized),
        "busy_trace": dict(trace),
        "nominal_timing": timing,
        "gpio_status_raw": dict(post_gpio),
        "busy_after_rst_low_is_informational": True,
    }


def _perform_refresh_once(
    base_url: str,
    frame: bytes,
    requester: _AuditedRequester,
    *,
    job_timeout_s: float,
    poll_interval_s: float,
    sleeper: Callable[[float], None],
    clock: Callable[[], float],
) -> Mapping[str, Any]:
    return perform_refresh(
        base_url,
        frame,
        expected_mappings=FIXED_CONTROLLER_MAPPINGS,
        job_timeout_s=job_timeout_s,
        poll_interval_s=poll_interval_s,
        requester=requester,
        sleeper=sleeper,
        clock=clock,
    )


def _collect_best_effort_evidence(
    base_url: str, requester: _AuditedRequester
) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for name, endpoint in (
        ("job_raw", "/api/job"),
        ("diagnostic_raw", "/api/diagnostic/report"),
        ("gpio_status_raw", "/api/diagnostic/status"),
    ):
        try:
            evidence[name] = dict(
                _get_json_object(
                    base_url,
                    endpoint,
                    label=f"best-effort {name}",
                    requester=requester,
                )
            )
        except BaseException as error:
            evidence[name] = {
                "unavailable": True,
                "error": {"type": type(error).__name__, "message": str(error)},
            }
    return evidence


def _base_result(
    *,
    attempt_id: str,
    claim: _Claim,
    recorded_at_utc: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": RESULT_KIND,
        "attempt_id": attempt_id,
        "recorded_at_utc": recorded_at_utc,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "action_id": FIXED_ACTION_ID,
        "action_identity_sha256": ACTION_IDENTITY_SHA256,
        "authorization_confirmation_sha256": AUTHORIZATION_CONFIRMATION_SHA256,
        "authorization_claim": claim.reference(),
        "frame": dict(ACTION_IDENTITY["frame"]),
        "exact_action": dict(EXACT_ACTION),
        "authorization_consumed_permanently": True,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "classification": dict(CLASSIFICATION),
        "formal": False,
        "hardware_qualified": False,
        "hardware_tested": False,
        "algorithm_qualification": False,
        "manual_observation_required": [
            "screen_matches_frozen_map_orient_v1_preview",
            "left_right_orientation_labels_and_center_seam",
            "all_six_physical_colors_and_no_retained_old_regions",
            "power_supply_3_3v_cv_current_and_temperature",
            "fixed_camera_photo_if_any_visual_difference_is_seen",
            "post_run_power_state",
        ],
        "manual_observation_completed": False,
    }


def run_rc2g_map_baseline_once(
    result_dir: Path,
    base_url: str,
    *,
    authorization_confirmation: str,
    confirm_rc2g_flashed_fresh_boot: bool = False,
    confirm_j2_powered_supervised: bool = False,
    confirm_supply_and_temperature_normal: bool = False,
    confirm_single_visible_refresh: bool = False,
    job_timeout_s: float = DEFAULT_JOB_TIMEOUT_S,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Consume and execute the sole RC2G cold-boot MAP baseline action."""

    if not isinstance(result_dir, Path):
        raise Rc2gMapBaselineError("result_dir must be pathlib.Path")
    destination = _prepare_result_destination(result_dir)
    if authorization_confirmation != REQUIRED_AUTHORIZATION_CONFIRMATION:
        raise Rc2gMapBaselineError(
            "exact RC2G cold-boot MAP baseline authorization string is required"
        )
    boolean_confirmations = {
        "rc2g_flashed_fresh_boot": confirm_rc2g_flashed_fresh_boot,
        "J2_powered_supervised": confirm_j2_powered_supervised,
        "supply_and_temperature_normal": confirm_supply_and_temperature_normal,
        "single_visible_refresh": confirm_single_visible_refresh,
    }
    if any(type(value) is not bool or value is not True for value in boolean_confirmations.values()):
        raise Rc2gMapBaselineError(
            "all four explicit flash/boot, supervised-power, normal-supply, and single-refresh confirmations are required"
        )
    if not isinstance(base_url, str) or not base_url.strip():
        raise Rc2gMapBaselineError("base_url must be a non-empty device root URL")

    snapshot = _validate_fixture_snapshot()
    attempt_id = uuid.uuid4().hex
    created_at_utc = _utc_now()
    confirmations = {
        "authorization_confirmation": authorization_confirmation,
        **boolean_confirmations,
    }
    # The global claim is intentionally committed before the first network
    # request.  Even a fresh-boot preflight failure consumes this action.
    claim = _claim_action(
        snapshot,
        attempt_id=attempt_id,
        claimed_at_utc=created_at_utc,
        result_destination=destination,
        confirmations=confirmations,
    )

    directory: Optional[Path] = None
    requester = _AuditedRequester(http_request)
    fresh_boot: Optional[Mapping[str, Any]] = None
    network_report: Optional[Mapping[str, Any]] = None
    raw_job: Optional[Mapping[str, Any]] = None
    raw_diagnostic: Optional[Mapping[str, Any]] = None
    post_gpio_raw: Optional[Mapping[str, Any]] = None
    completed_evidence: Optional[Mapping[str, Any]] = None
    try:
        directory = _create_result_directory(destination, claim)
        lock = {
            "schema_version": SCHEMA_VERSION,
            "kind": LOCK_KIND,
            "attempt_id": attempt_id,
            "created_at_utc": created_at_utc,
            "state": "authorization_permanently_consumed_do_not_rerun",
            "action_identity": dict(ACTION_IDENTITY),
            "action_identity_sha256": ACTION_IDENTITY_SHA256,
            "authorization_confirmation_sha256": AUTHORIZATION_CONFIRMATION_SHA256,
            "authorization_claim": claim.reference(),
            "confirmations": confirmations,
            "authorization_consumed_permanently": True,
            "automatic_retry_authorized": False,
            "automatic_recovery_authorized": False,
            "formal": False,
            "hardware_qualified": False,
            "hardware_tested": False,
        }
        _atomic_new_file(directory, LOCK_FILENAME, _canonical_json(lock))

        fresh_boot = _validate_fresh_boot_state(base_url, requester)
        network_report = _perform_refresh_once(
            base_url,
            snapshot.frame,
            requester,
            job_timeout_s=job_timeout_s,
            poll_interval_s=poll_interval_s,
            sleeper=sleeper,
            clock=clock,
        )
        if requester.post_issued_count != 1:
            raise Rc2gMapBaselineError(
                "RC2G MAP baseline did not issue exactly one POST /api/frame"
            )
        raw_job = _get_json_object(
            base_url, "/api/job", label="post-MAP job", requester=requester
        )
        raw_diagnostic = _get_json_object(
            base_url,
            "/api/diagnostic/report",
            label="post-MAP diagnostic",
            requester=requester,
        )
        post_gpio_raw = _get_json_object(
            base_url,
            "/api/diagnostic/status",
            label="post-MAP GPIO",
            requester=requester,
        )
        completed_evidence = _validate_completed_map_evidence(
            network_report,
            raw_job,
            raw_diagnostic,
            post_gpio_raw,
            snapshot.frame,
        )
        result = {
            **_base_result(
                attempt_id=attempt_id,
                claim=claim,
                recorded_at_utc=_utc_now(),
            ),
            "outcome": "protocol_verified_manual_observation_required",
            "protocol_verified": True,
            "fresh_boot_preflight": dict(fresh_boot),
            "completed_map_evidence": dict(completed_evidence),
            "request_audit": requester.snapshot(),
            "best_effort_postclaim_evidence": None,
        }
        _atomic_new_file(directory, RESULT_FILENAME, _canonical_json(result))
        return result
    except BaseException as error:
        best_effort: Optional[Mapping[str, Any]] = None
        if requester.calls:
            best_effort = _collect_best_effort_evidence(base_url, requester)
        record_error: Optional[BaseException] = None
        try:
            if directory is not None:
                unknown = {
                    **_base_result(
                        attempt_id=attempt_id,
                        claim=claim,
                        recorded_at_utc=_utc_now(),
                    ),
                    "outcome": "unknown_do_not_retry",
                    "protocol_verified": None,
                    "fresh_boot_preflight": (
                        dict(fresh_boot) if fresh_boot is not None else None
                    ),
                    "network_report": (
                        dict(network_report) if network_report is not None else None
                    ),
                    "post_refresh_job_raw": (
                        dict(raw_job) if raw_job is not None else None
                    ),
                    "post_refresh_diagnostic_raw": (
                        dict(raw_diagnostic) if raw_diagnostic is not None else None
                    ),
                    "post_refresh_gpio_status_raw": (
                        dict(post_gpio_raw) if post_gpio_raw is not None else None
                    ),
                    "completed_map_evidence": (
                        dict(completed_evidence)
                        if completed_evidence is not None
                        else None
                    ),
                    "request_audit": requester.snapshot(),
                    "best_effort_postclaim_evidence": (
                        dict(best_effort) if best_effort is not None else None
                    ),
                    "error": {"type": type(error).__name__, "message": str(error)},
                }
                _atomic_new_file(directory, RESULT_FILENAME, _canonical_json(unknown))
        except BaseException as result_error:
            record_error = result_error
        detail = f"; result recording also failed ({record_error})" if record_error else ""
        raise Rc2gMapBaselineUnknown(
            "RC2G MAP baseline outcome is unknown_do_not_retry; the global claim is permanent"
            + detail
        ) from error


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument(
        "--url", required=True, help="device root URL on the trusted test network"
    )
    parser.add_argument(
        "--confirm", required=True, help="exact one-refresh authorization string"
    )
    parser.add_argument("--confirm-rc2g-flashed-fresh-boot", action="store_true")
    parser.add_argument("--confirm-j2-powered-supervised", action="store_true")
    parser.add_argument("--confirm-supply-and-temperature-normal", action="store_true")
    parser.add_argument("--confirm-single-visible-refresh", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        result = run_rc2g_map_baseline_once(
            args.result_dir,
            args.url,
            authorization_confirmation=args.confirm,
            confirm_rc2g_flashed_fresh_boot=args.confirm_rc2g_flashed_fresh_boot,
            confirm_j2_powered_supervised=args.confirm_j2_powered_supervised,
            confirm_supply_and_temperature_normal=args.confirm_supply_and_temperature_normal,
            confirm_single_visible_refresh=args.confirm_single_visible_refresh,
        )
    except Rc2gMapBaselineUnknown as error:
        print(f"UNKNOWN_DO_NOT_RETRY: {error}", file=sys.stderr)
        return 3
    except Rc2gMapBaselineError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(_canonical_json(result).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
