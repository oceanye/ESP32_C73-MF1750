#!/usr/bin/env python3
"""Redisplay the frozen G1/S1 macro4 frame once after a fresh MAP job1.

This is a separate, fail-closed authorization path.  It never mutates or
reuses the original macro4 quality claim.  The exact redisplay action is
claimed in its own workspace registry before any network request, then the
device must prove a nominal MAP_ORIENT_V1 job1/operation1 prior before the
runner permits one and only one ``POST /api/frame`` for macro4 job2/op2.

There is no retry or recovery path.  Once the claim exists, every exception is
``unknown_do_not_retry``.  The runner preserves any completed network report,
the raw post-refresh GPIO sample, and best-effort read-only device evidence.
It does not confer formal or hardware qualification on the algorithm.
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
RESULT_FILENAME = "MACRO4-REDISPLAY-RESULT.json"
LOCK_KIND = "mf1750-g1-s1-macro4-redisplay-attempt-lock"
RESULT_KIND = "mf1750-g1-s1-macro4-redisplay-result"
CLAIM_KIND = "mf1750-g1-s1-macro4-redisplay-claim"
CLAIM_REGISTRY_ID = "workspace-g1-s1-macro4-redisplay-registry-v1"
FIXED_ACTION_ID = "redisplay-frozen-g1-s1-macro4-after-reboot-map-job1-v1"

DEFAULT_AUTHORIZATION_REGISTRY = (
    REPO_ROOT / ".test-output" / "hardware" / ".g1_s1_macro4_redisplay_registry"
)
DEFAULT_CANDIDATE_DIRECTORY = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "G1S1_QUALITY_MACRO4_BLUE_NOISE_OFFLINE_20260807"
)

# Keep this build identity centralized.  The supervised instrumented firmware
# review must update this single frozen value before any production attempt.
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

EXPECTED_MANIFEST_SHA256 = "7c6f8569eb8a1cba9de144b7c660e79b932c1abbcbb5d6aa334ac694056420ad"
EXPECTED_MANIFEST_CANONICAL_SHA256 = "85abb1a948079eba89b7ca854c4b6b867e3b5f6716f5819c22765b610c2e900b"
EXPECTED_MANIFEST_KIND = "mf1750-g1-s1-macro4-quality-candidate"
EXPECTED_ALGORITHM_ID = "low-resolution-area-weighted-blue-noise-nearest-macro-v1"
EXPECTED_FRAME_SHA256 = "1f509baa655d84fe13da65441f22929f32a43a0ac66d45d753f7a3d394a2281d"
EXPECTED_FRAME_FNV1A = 0x092C9775
EXPECTED_CS1_DTM_SHA256 = "a36a9288154d882916a6562d44d86c41278ea45ffbfcbc2afe634616d5a52fcc"
EXPECTED_CS1_DTM_FNV1A = 0x3F1601D5
EXPECTED_CS2_DTM_SHA256 = "d9bf80b6433bba8356502ce62ce44450da7339902413d9018d4ee6c959fb231d"
EXPECTED_CS2_DTM_FNV1A = 0x52ECC935
REQUIRED_CANDIDATE_FILES = frozenset(
    {"manifest.json", "frame.bin", "source.png", "mapped.png", "strict-final.png", "model.png"}
)

MAP_FIXTURE_NAME = "map-orient-v1"
MAP_FRAME_SHA256 = "1deedf924e40c676c2080fec08dfe5da10a8c1bb53b699ec4a85b0b6101b5c36"
MAP_FRAME_FNV1A = 0x9D04142D
MAP_CS1_DTM_FNV1A = 0xF26832DD
MAP_CS2_DTM_FNV1A = 0xFE199FF5
EXPECTED_PRIOR_JOB_ID = 1
EXPECTED_PRIOR_OPERATION_ID = 1
EXPECTED_TARGET_JOB_ID = 2
EXPECTED_TARGET_OPERATION_ID = 2
EXPECTED_PANEL_OUTPUTS_LOW = {"rst": 0, "cs": 0, "cs2": 0}
NOMINAL_JOB_DURATION_MS = (28_000, 45_000)
NOMINAL_STAGE_TIMING_MS = {
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

ORIGINAL_QUALITY_ATTEMPT_ID = "15b2d7a27cc84726ae512731372f3aad"
ORIGINAL_QUALITY_CLAIM_SHA256 = "527461bbdbd19ff4a58febf6245fb13dcf0514361f9f319e49605452f9415854"
ORIGINAL_QUALITY_CLAIM_PATH = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".g1_s1_macro4_quality_registry"
    / EXPECTED_MANIFEST_SHA256
)

REQUIRED_AUTHORIZATION_CONFIRMATION = (
    "AUTHORIZE_ONE_VISIBLE_REDISPLAY_OF_FROZEN_G1S1_MACRO4_FRAME_AFTER_"
    "NOMINAL_REBOOT_MAP_JOB1__NO_RETRY_NO_RECOVERY"
)
EXACT_ACTION = {
    "action_id": FIXED_ACTION_ID,
    "method": "POST",
    "endpoint": "/api/frame",
    "maximum_posts": 1,
    "automatic_retry": False,
    "automatic_recovery": False,
    "prior_job_id": EXPECTED_PRIOR_JOB_ID,
    "prior_operation_id": EXPECTED_PRIOR_OPERATION_ID,
    "target_job_id": EXPECTED_TARGET_JOB_ID,
    "target_operation_id": EXPECTED_TARGET_OPERATION_ID,
}
CLASSIFICATION = {
    "experimental": True,
    "redisplay_of_frozen_frame": True,
    "subjective_quality_concern_follow_up": True,
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


class Macro4RedisplayError(RuntimeError):
    """The redisplay was rejected before its permanent claim existed."""


class Macro4RedisplayUnknown(Macro4RedisplayError):
    """The claim exists, so the exact redisplay must never be attempted again."""


@dataclass(frozen=True)
class _CandidateSnapshot:
    directory: Path
    manifest: Mapping[str, Any]
    manifest_bytes: bytes
    frame: bytes


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
        raise Macro4RedisplayError(f"canonical JSON encoding failed: {error}") from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _mapping_record(mapping: ControllerMapping) -> dict[str, int | bool]:
    return {
        "source_half": mapping.source_half,
        "flip_x": mapping.flip_x,
        "flip_y": mapping.flip_y,
        "nibble_swap": mapping.nibble_swap,
    }


def _controller_records() -> list[dict[str, Any]]:
    hashes = (EXPECTED_CS1_DTM_FNV1A, EXPECTED_CS2_DTM_FNV1A)
    sha256s = (EXPECTED_CS1_DTM_SHA256, EXPECTED_CS2_DTM_SHA256)
    return [
        {
            "controller": f"CS{index}",
            "mapping": _mapping_record(mapping),
            "dtm_bytes": CONTROLLER_FRAME_BYTES,
            "dtm_sha256": sha256,
            "dtm_fnv1a": f"0x{hash_value:08X}",
        }
        for index, (mapping, sha256, hash_value) in enumerate(
            zip(FIXED_CONTROLLER_MAPPINGS, sha256s, hashes), start=1
        )
    ]


ACTION_IDENTITY = {
    "schema_version": SCHEMA_VERSION,
    "kind": "mf1750-g1-s1-macro4-redisplay-action-identity",
    "action_id": FIXED_ACTION_ID,
    "original_quality_claim": {
        "attempt_id": ORIGINAL_QUALITY_ATTEMPT_ID,
        "manifest_file_sha256": EXPECTED_MANIFEST_SHA256,
        "claim_sha256": ORIGINAL_QUALITY_CLAIM_SHA256,
    },
    "firmware": {
        "build_tag": EXPECTED_BUILD_TAG,
        "driver_api": EXPECTED_DRIVER_API,
        "refresh_spi_hz": EXPECTED_REFRESH_SPI_HZ,
        "busy_trace_required": True,
        "busy_trace_schema_version": 1,
    },
    "prior": {
        "fixture": MAP_FIXTURE_NAME,
        "frame_sha256": MAP_FRAME_SHA256,
        "frame_fnv1a": f"0x{MAP_FRAME_FNV1A:08X}",
        "cs1_dtm_fnv1a": f"0x{MAP_CS1_DTM_FNV1A:08X}",
        "cs2_dtm_fnv1a": f"0x{MAP_CS2_DTM_FNV1A:08X}",
        "job_id": EXPECTED_PRIOR_JOB_ID,
        "operation_id": EXPECTED_PRIOR_OPERATION_ID,
        "gpio_contract": {
            "required_low_outputs": dict(EXPECTED_PANEL_OUTPUTS_LOW),
            "busy_after_rst_low": "informational_0_or_1",
        },
    },
    "redisplay": {
        "manifest_file_sha256": EXPECTED_MANIFEST_SHA256,
        "frame_sha256": EXPECTED_FRAME_SHA256,
        "frame_fnv1a": f"0x{EXPECTED_FRAME_FNV1A:08X}",
        "controllers": _controller_records(),
        "job_id": EXPECTED_TARGET_JOB_ID,
        "operation_id": EXPECTED_TARGET_OPERATION_ID,
    },
    "nominal_timing_ms": {
        "job_duration": list(NOMINAL_JOB_DURATION_MS),
        "stages": {
            key: list(value) for key, value in NOMINAL_STAGE_TIMING_MS.items()
        },
        "job5_like_89049ms_outcome": "unknown_do_not_retry",
    },
    "exact_action": dict(EXACT_ACTION),
}
ACTION_IDENTITY_SHA256 = "f48164a7d93de2072ee78aed0525bd6537b4ac59dad7117e1f5fc99e1395b076"
AUTHORIZATION_CONFIRMATION_SHA256 = (
    "f1b8f3516558511ed61cd65203e318f9b587a6ea32d1577fd3e7fad09896a5a4"
)
if _sha256(_canonical_json(ACTION_IDENTITY)) != ACTION_IDENTITY_SHA256:
    raise RuntimeError("frozen macro4 redisplay action identity changed")
if (
    _sha256(REQUIRED_AUTHORIZATION_CONFIRMATION.encode("ascii"))
    != AUTHORIZATION_CONFIRMATION_SHA256
):
    raise RuntimeError("frozen macro4 redisplay authorization string changed")


def _deep_validate_candidate_directory(directory: Path) -> Mapping[str, Any]:
    try:
        from tools.g1_s1_macro4_quality_candidate import (
            Macro4CandidateError,
            validate_candidate_directory,
        )
    except (ImportError, AttributeError) as error:
        raise Macro4RedisplayError("macro4 deep validator is unavailable") from error
    try:
        manifest = validate_candidate_directory(directory)
    except (Macro4CandidateError, OSError, TypeError, ValueError) as error:
        raise Macro4RedisplayError(f"macro4 deep validation failed: {error}") from error
    if not isinstance(manifest, Mapping):
        raise Macro4RedisplayError("macro4 deep validator did not return an object")
    return manifest


def _load_candidate_snapshot() -> _CandidateSnapshot:
    candidate = DEFAULT_CANDIDATE_DIRECTORY
    try:
        require_local_regular_path_syntax(candidate, label="macro4 candidate directory")
    except LocalPathSafetyError as error:
        raise Macro4RedisplayError(str(error)) from error
    if candidate.is_symlink():
        raise Macro4RedisplayError("macro4 candidate directory must not be a symlink")
    manifest = _deep_validate_candidate_directory(candidate)
    try:
        directory = candidate.resolve(strict=True)
        entries = tuple(directory.iterdir())
        if not directory.is_dir() or any(path.is_dir() for path in entries):
            raise Macro4RedisplayError("macro4 candidate must be a flat directory")
        if {path.name for path in entries if path.is_file()} != REQUIRED_CANDIDATE_FILES:
            raise Macro4RedisplayError("macro4 candidate file set is not frozen")
        if any(path.is_symlink() for path in entries):
            raise Macro4RedisplayError("macro4 candidate files must not be symlinks")
        manifest_bytes = (directory / "manifest.json").read_bytes()
        if manifest_bytes != _canonical_json(manifest):
            raise Macro4RedisplayError("macro4 manifest bytes are not canonical")
        if _sha256(manifest_bytes) != EXPECTED_MANIFEST_SHA256:
            raise Macro4RedisplayError("macro4 manifest file SHA-256 is not frozen")
        unsigned = dict(manifest)
        integrity = unsigned.pop("manifest_integrity", None)
        canonical_sha256 = _sha256(_canonical_json(unsigned))
        if (
            not isinstance(integrity, Mapping)
            or integrity.get("canonical_sha256") != canonical_sha256
            or canonical_sha256 != EXPECTED_MANIFEST_CANONICAL_SHA256
        ):
            raise Macro4RedisplayError("macro4 canonical manifest identity is not frozen")
        algorithm = manifest.get("algorithm")
        if (
            manifest.get("kind") != EXPECTED_MANIFEST_KIND
            or not isinstance(algorithm, Mapping)
            or algorithm.get("id") != EXPECTED_ALGORITHM_ID
        ):
            raise Macro4RedisplayError("macro4 kind/algorithm identity is not frozen")
        classification = manifest.get("classification")
        transport = manifest.get("transport")
        if (
            not isinstance(classification, Mapping)
            or classification.get("formal") is not False
            or classification.get("hardware_qualified") is not False
            or classification.get("upload_authorized") is not False
            or not isinstance(transport, Mapping)
            or transport.get("mode") != "offline"
            or transport.get("device_io_performed") is not False
            or transport.get("network_io_performed") is not False
        ):
            raise Macro4RedisplayError("macro4 bundle lost its offline unqualified class")
        frame = (directory / "frame.bin").read_bytes()
        validate_frame(frame)
        if _sha256(frame) != EXPECTED_FRAME_SHA256 or fnv1a(frame) != EXPECTED_FRAME_FNV1A:
            raise Macro4RedisplayError("macro4 frame identity is not frozen")
        streams = tuple(controller_stream(frame, mapping) for mapping in FIXED_CONTROLLER_MAPPINGS)
        if tuple(fnv1a(stream) for stream in streams) != (
            EXPECTED_CS1_DTM_FNV1A,
            EXPECTED_CS2_DTM_FNV1A,
        ) or tuple(_sha256(stream) for stream in streams) != (
            EXPECTED_CS1_DTM_SHA256,
            EXPECTED_CS2_DTM_SHA256,
        ):
            raise Macro4RedisplayError("macro4 controller DTM identities are not frozen")
        output = manifest.get("output")
        if not isinstance(output, Mapping) or output.get("controllers") != _controller_records():
            raise Macro4RedisplayError("macro4 manifest controller records are not frozen")
        frame_record = output.get("frame")
        if (
            not isinstance(frame_record, Mapping)
            or frame_record.get("file") != "frame.bin"
            or frame_record.get("bytes") != FRAME_BYTES
            or frame_record.get("sha256") != EXPECTED_FRAME_SHA256
            or frame_record.get("fnv1a") != f"0x{EXPECTED_FRAME_FNV1A:08X}"
        ):
            raise Macro4RedisplayError("macro4 manifest frame record is not frozen")
    except Macro4RedisplayError:
        raise
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise Macro4RedisplayError(f"macro4 candidate changed while snapshotting: {error}") from error
    return _CandidateSnapshot(directory, dict(manifest), manifest_bytes, frame)


def _load_original_quality_claim() -> Mapping[str, Any]:
    path = ORIGINAL_QUALITY_CLAIM_PATH
    try:
        require_local_regular_path_syntax(path, label="original macro4 quality claim")
        if path.is_symlink() or not path.resolve(strict=True).is_file():
            raise Macro4RedisplayError("original macro4 quality claim must be a regular file")
        payload = path.read_bytes()
        if _sha256(payload) != ORIGINAL_QUALITY_CLAIM_SHA256:
            raise Macro4RedisplayError("original macro4 quality claim SHA-256 changed")
        value = json.loads(payload)
    except Macro4RedisplayError:
        raise
    except (LocalPathSafetyError, OSError, json.JSONDecodeError) as error:
        raise Macro4RedisplayError(f"could not validate original quality claim: {error}") from error
    if (
        not isinstance(value, Mapping)
        or value.get("attempt_id") != ORIGINAL_QUALITY_ATTEMPT_ID
        or value.get("manifest_file_sha256") != EXPECTED_MANIFEST_SHA256
        or value.get("authorization_consumed_permanently") is not True
        or value.get("state") != "authorization_permanently_consumed_do_not_rerun"
    ):
        raise Macro4RedisplayError("original macro4 quality claim semantics changed")
    return {
        "path": str(path.resolve(strict=True)),
        "sha256": ORIGINAL_QUALITY_CLAIM_SHA256,
        "attempt_id": ORIGINAL_QUALITY_ATTEMPT_ID,
        "state": value["state"],
    }


def _validate_fixed_map_fixture() -> None:
    try:
        frame = generate_fixture(MAP_FIXTURE_NAME)
        verify_fixture(MAP_FIXTURE_NAME, frame)
        validate_frame(frame)
    except (KeyError, ValueError) as error:
        raise Macro4RedisplayError(f"fixed MAP fixture validation failed: {error}") from error
    streams = tuple(controller_stream(frame, mapping) for mapping in FIXED_CONTROLLER_MAPPINGS)
    if (
        _sha256(frame) != MAP_FRAME_SHA256
        or fnv1a(frame) != MAP_FRAME_FNV1A
        or tuple(fnv1a(stream) for stream in streams)
        != (MAP_CS1_DTM_FNV1A, MAP_CS2_DTM_FNV1A)
    ):
        raise Macro4RedisplayError("fixed MAP prior identities changed")


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _prepare_result_destination(result_dir: Path) -> Path:
    try:
        require_local_regular_path_syntax(result_dir, label="redisplay result directory")
    except LocalPathSafetyError as error:
        raise Macro4RedisplayError(str(error)) from error
    if os.path.lexists(result_dir):
        raise Macro4RedisplayError("result directory already exists; refusing overwrite or rerun")
    try:
        parent = result_dir.parent.resolve(strict=True)
    except OSError as error:
        raise Macro4RedisplayError(f"result parent does not exist: {error}") from error
    if not parent.is_dir():
        raise Macro4RedisplayError("result parent must be a directory")
    destination = parent / result_dir.name
    if os.path.lexists(destination):
        raise Macro4RedisplayError("result directory already exists; refusing overwrite or rerun")
    return destination


def _authorization_registry() -> Path:
    path = DEFAULT_AUTHORIZATION_REGISTRY
    try:
        require_local_regular_path_syntax(path, label="redisplay authorization registry")
        if os.path.lexists(path) and path.is_symlink():
            raise Macro4RedisplayError("redisplay registry must not be a symlink")
        parent = path.parent.resolve(strict=True)
        workspace = REPO_ROOT.resolve(strict=True)
        if not parent.is_dir() or not _is_within(parent, workspace):
            raise Macro4RedisplayError("redisplay registry parent must be in the workspace")
        path.mkdir(exist_ok=True)
        registry = path.resolve(strict=True)
    except Macro4RedisplayError:
        raise
    except (LocalPathSafetyError, OSError) as error:
        raise Macro4RedisplayError(f"could not create redisplay registry: {error}") from error
    if path.is_symlink() or not registry.is_dir() or not _is_within(registry, workspace):
        raise Macro4RedisplayError("redisplay registry escaped the workspace")
    return registry


def _claim_action(
    snapshot: _CandidateSnapshot,
    original_claim: Mapping[str, Any],
    *,
    attempt_id: str,
    claimed_at_utc: str,
    result_destination: Path,
    confirmations: Mapping[str, Any],
) -> _Claim:
    registry = _authorization_registry()
    if _is_within(result_destination, registry):
        raise Macro4RedisplayError("result directory must not be inside redisplay registry")
    record = {
        "schema_version": SCHEMA_VERSION,
        "kind": CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "action_id": FIXED_ACTION_ID,
        "action_identity_sha256": ACTION_IDENTITY_SHA256,
        "authorization_confirmation_sha256": AUTHORIZATION_CONFIRMATION_SHA256,
        "attempt_id": attempt_id,
        "claimed_at_utc": claimed_at_utc,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "authorization_consumed_permanently": True,
        "original_quality_claim": dict(original_claim),
        "candidate_manifest_file_sha256": EXPECTED_MANIFEST_SHA256,
        "candidate_frame_sha256": EXPECTED_FRAME_SHA256,
        "candidate_frame_fnv1a": f"0x{EXPECTED_FRAME_FNV1A:08X}",
        "result_directory": str(result_destination),
        "action_identity": dict(ACTION_IDENTITY),
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
            raise Macro4RedisplayUnknown("redisplay claim exists after cleanup failure; do not retry") from error
        raise Macro4RedisplayError("this redisplay action was already permanently consumed; do not retry") from error
    except BaseException as error:
        if linked:
            raise Macro4RedisplayUnknown("redisplay claim exists after claim processing failure; do not retry") from error
        if not isinstance(error, OSError):
            raise
        raise Macro4RedisplayError(f"could not atomically claim redisplay action: {error}") from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except BaseException:
            pass
    return claim


def _create_result_directory(destination: Path, snapshot: _CandidateSnapshot, claim: _Claim) -> Path:
    if _is_within(destination, snapshot.directory) or _is_within(destination, claim.registry):
        raise Macro4RedisplayError("result directory overlaps a frozen input or claim registry")
    try:
        destination.mkdir()
    except FileExistsError as error:
        raise Macro4RedisplayError("result directory appeared; refusing overwrite") from error
    except OSError as error:
        raise Macro4RedisplayError(f"could not create result directory: {error}") from error
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
        raise Macro4RedisplayError(f"{name} already exists; refusing overwrite") from error
    except OSError as error:
        if linked:
            raise Macro4RedisplayError(f"{name} committed but staging cleanup failed") from error
        raise Macro4RedisplayError(f"could not atomically write {name}: {error}") from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except BaseException:
            pass


class _AuditedRequester:
    """Allowlisted requester that records and hard-limits the sole POST."""

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
            raise Macro4RedisplayError(f"request route is not allowlisted: {normalized_method} {endpoint}")
        if normalized_method == "POST":
            self.post_attempt_count += 1
            if endpoint != "/api/frame" or self.post_issued_count >= 1:
                entry["outcome"] = "blocked_additional_post"
                raise Macro4RedisplayError("redisplay permits exactly one issued POST /api/frame")
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
        entry["response_bytes"] = len(body.encode("utf-8")) if isinstance(body, str) else None
        entry["response_sha256"] = _sha256(body.encode("utf-8")) if isinstance(body, str) else None
        return status, body

    def snapshot(self) -> dict[str, Any]:
        return {
            "post_attempt_count": self.post_attempt_count,
            "post_issued_count": self.post_issued_count,
            "calls": [dict(call) for call in self.calls],
        }


def _get_json_object(
    base_url: str,
    endpoint: str,
    *,
    label: str,
    requester: _AuditedRequester,
) -> Mapping[str, Any]:
    status, body = requester(base_url, endpoint, method="GET", data=None, timeout=20.0)
    if status != 200:
        raise Macro4RedisplayError(f"{label} returned HTTP {status}: {body[:200]}")
    try:
        value = json.loads(body)
    except (TypeError, json.JSONDecodeError) as error:
        raise Macro4RedisplayError(f"{label} is not valid JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise Macro4RedisplayError(f"{label} must be a JSON object")
    return value


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
        raise Macro4RedisplayError(
            "redisplay EXPECTED_BUILD_TAG must be an allowlisted BUSY-trace build"
        )
    if any(version.get(key) != value for key, value in _expected_version_static().items()):
        raise Macro4RedisplayError(f"{label} build/API/panel/SPI/mappings are not frozen")


def _validate_gpio_snapshot(value: Mapping[str, Any], *, label: str) -> dict[str, int]:
    if set(value) != {"busy", "rst", "cs", "cs2"}:
        raise Macro4RedisplayError(f"{label} fields are not the strict GPIO contract")
    snapshot: dict[str, int] = {}
    for key in ("busy", "rst", "cs", "cs2"):
        level = value.get(key)
        if type(level) is not int or level not in (0, 1):
            raise Macro4RedisplayError(f"{label}.{key} must be integer level 0 or 1")
        snapshot[key] = level
    if any(snapshot[key] != expected for key, expected in EXPECTED_PANEL_OUTPUTS_LOW.items()):
        raise Macro4RedisplayError(f"{label} RST/CS1/CS2 outputs are not all low")
    # BUSY is an input.  Once RST is held low, either sampled level is retained
    # as evidence and must agree with the nested driver trace, but is not by
    # itself a safe-finish pass/fail condition.
    return snapshot


def _validate_required_busy_trace(
    diagnostic: Mapping[str, Any], *, label: str
) -> Mapping[str, Any]:
    trace = diagnostic.get("busy_trace")
    if not isinstance(trace, Mapping):
        raise Macro4RedisplayError(f"{label} nested BUSY trace is required")
    if (
        trace.get("schema_version") != 1
        or trace.get("idle_level") != 1
        or trace.get("command_edge_contract_verified") is not True
        or trace.get("safe_finish_pin_levels_verified") is not True
        or trace.get("busy_after_rst_low_is_informational") is not True
    ):
        raise Macro4RedisplayError(f"{label} BUSY trace contract is not verified")
    stages = trace.get("stages")
    if not isinstance(stages, Mapping) or set(stages) != {
        "reset", "pon", "drf", "pof", "post_psr"
    }:
        raise Macro4RedisplayError(f"{label} BUSY trace stages are incomplete")
    for stage_name in ("pon", "drf", "pof"):
        stage = stages.get(stage_name)
        if (
            not isinstance(stage, Mapping)
            or stage.get("pre_command_level") != 1
            or stage.get("pre_command_idle_ok") is not True
            or stage.get("assertion_after_idle") is not True
            or stage.get("wait_exit_level") != 1
        ):
            raise Macro4RedisplayError(
                f"{label} {stage_name.upper()} lacks idle-before-command/new-BUSY-edge proof"
            )
        minimum, maximum = NOMINAL_STAGE_TIMING_MS[f"{stage_name}_ms"]
        wait_ms = stage.get("wait_ms")
        if type(wait_ms) is not int or not minimum <= wait_ms <= maximum:
            raise Macro4RedisplayError(
                f"{label} {stage_name.upper()} wait is outside the nominal "
                f"{minimum}..{maximum} ms envelope"
            )
    post_psr = stages.get("post_psr")
    if (
        not isinstance(post_psr, Mapping)
        or post_psr.get("assertion_after_idle") is not False
        or post_psr.get("wait_exit_level") != 1
    ):
        raise Macro4RedisplayError(f"{label} post-PSR informational trace is invalid")
    post_minimum, post_maximum = NOMINAL_STAGE_TIMING_MS["post_psr_ms"]
    post_wait_ms = post_psr.get("wait_ms")
    if type(post_wait_ms) is not int or not post_minimum <= post_wait_ms <= post_maximum:
        raise Macro4RedisplayError(
            f"{label} post-PSR wait is outside the nominal "
            f"{post_minimum}..{post_maximum} ms envelope"
        )
    safe_finish = trace.get("safe_finish")
    final_gpio = trace.get("final_gpio")
    if not isinstance(safe_finish, Mapping) or safe_finish.get("busy_before_pins_low") != 1:
        raise Macro4RedisplayError(f"{label} did not enter safe finish with BUSY idle")
    if not isinstance(final_gpio, Mapping):
        raise Macro4RedisplayError(f"{label} final GPIO trace is missing")
    _validate_gpio_snapshot(final_gpio, label=f"{label} final GPIO trace")
    return trace


def _u32_duration(start: int, finish: int) -> int:
    return (finish - start) & 0xFFFFFFFF


def _validate_timing(
    job: Mapping[str, Any], raw_diagnostic: Mapping[str, Any], *, label: str
) -> dict[str, int]:
    timestamps = tuple(job.get(key) for key in ("queued_at_ms", "started_at_ms", "finished_at_ms"))
    if any(type(value) is not int or not 0 <= value <= 0xFFFFFFFF for value in timestamps):
        raise Macro4RedisplayError(f"{label} job timestamps are not uint32")
    queued, started, finished = timestamps
    queue_delay = _u32_duration(queued, started)
    job_duration = _u32_duration(started, finished)
    if queue_delay > MAX_QUEUE_DELAY_MS or not (
        NOMINAL_JOB_DURATION_MS[0]
        <= job_duration
        <= NOMINAL_JOB_DURATION_MS[1]
    ):
        raise Macro4RedisplayError(f"{label} job timing is outside the visible-refresh envelope")
    values: dict[str, int] = {}
    for field, (minimum, maximum) in NOMINAL_STAGE_TIMING_MS.items():
        value = raw_diagnostic.get(field)
        if type(value) is not int or not minimum <= value <= maximum:
            raise Macro4RedisplayError(f"{label} {field} is outside {minimum}..{maximum} ms")
        values[field] = value
    if abs(job_duration - values["total_ms"]) > MAX_JOB_DRIVER_DURATION_DELTA_MS:
        raise Macro4RedisplayError(
            f"{label} job duration and driver total differ beyond the nominal gate"
        )
    return {
        **values,
        "queue_delay_ms": queue_delay,
        "job_duration_ms": job_duration,
    }


def _validate_map_job1_prior(base_url: str, requester: _AuditedRequester) -> Mapping[str, Any]:
    try:
        version = _preflight_version(base_url, requester, FIXED_CONTROLLER_MAPPINGS)
    except FrameToolError as error:
        raise Macro4RedisplayError(f"MAP prior firmware preflight failed: {error}") from error
    _validate_version(version, label="MAP prior firmware")
    job = _get_json_object(base_url, "/api/job", label="MAP prior job", requester=requester)
    required_job_keys = {
        "job_id", "action", "state", "result", "queued_at_ms", "started_at_ms",
        "finished_at_ms", "frame_fnv1a",
    }
    if set(job) != required_job_keys:
        raise Macro4RedisplayError("MAP prior job fields are not the strict job contract")
    try:
        state = _validate_job(job, EXPECTED_PRIOR_JOB_ID, MAP_FRAME_FNV1A)
    except FrameToolError as error:
        raise Macro4RedisplayError(f"MAP prior job validation failed: {error}") from error
    if state != "completed":
        raise Macro4RedisplayError("MAP prior job1 is not completed")
    raw_diagnostic = _get_json_object(
        base_url, "/api/diagnostic/report", label="MAP prior diagnostic", requester=requester
    )
    map_frame = generate_fixture(MAP_FIXTURE_NAME)
    try:
        normalized = _validate_diagnostic(
            raw_diagnostic,
            map_frame,
            FIXED_CONTROLLER_MAPPINGS,
            version,
            job,
        )
    except FrameToolError as error:
        raise Macro4RedisplayError(f"MAP prior diagnostic validation failed: {error}") from error
    if (
        normalized.get("operation_id") != EXPECTED_PRIOR_OPERATION_ID
        or normalized.get("job_operation_id") != EXPECTED_PRIOR_OPERATION_ID
        or normalized.get("sequence_verified") is not True
        or normalized.get("required_busy_stages_verified") is not True
        or normalized.get("busy_timeout") is not False
        or normalized.get("safe_finish_verified") is not True
    ):
        raise Macro4RedisplayError("MAP prior is not nominal job1/operation1 safe-finish")
    prior_busy_trace = _validate_required_busy_trace(
        normalized, label="MAP prior diagnostic"
    )
    expected_physical = [
        {
            "controller": "CS1",
            "mapping": _mapping_record(FIXED_CONTROLLER_MAPPINGS[0]),
            "dtm_bytes": CONTROLLER_FRAME_BYTES,
            "dtm_fnv1a": MAP_CS1_DTM_FNV1A,
        },
        {
            "controller": "CS2",
            "mapping": _mapping_record(FIXED_CONTROLLER_MAPPINGS[1]),
            "dtm_bytes": CONTROLLER_FRAME_BYTES,
            "dtm_fnv1a": MAP_CS2_DTM_FNV1A,
        },
    ]
    if normalized.get("physical_controllers") != expected_physical:
        raise Macro4RedisplayError("MAP prior controller DTM identities are not frozen")
    _validate_timing(job, raw_diagnostic, label="MAP prior")
    gpio = _get_json_object(
        base_url, "/api/diagnostic/status", label="MAP prior GPIO", requester=requester
    )
    gpio_snapshot = _validate_gpio_snapshot(gpio, label="MAP prior GPIO")
    return {
        "version": dict(version),
        "job": dict(job),
        "diagnostic_raw": dict(raw_diagnostic),
        "diagnostic_validated": dict(normalized),
        "gpio_status_raw": dict(gpio_snapshot),
        "busy_after_rst_low_is_informational": True,
        "nested_busy_trace": dict(prior_busy_trace),
        "map_identity": dict(ACTION_IDENTITY["prior"]),
    }


def _validate_network_report(report: object) -> Mapping[str, Any]:
    if not isinstance(report, Mapping):
        raise Macro4RedisplayError("redisplay network report must be an object")
    if report.get("protocol_verified") is not True or report.get("hardware_tested") is not False:
        raise Macro4RedisplayError("redisplay report lost its fail-closed classification")
    scope = report.get("verified_scope")
    if not isinstance(scope, list) or not REQUIRED_VERIFIED_SCOPE.issubset(scope):
        raise Macro4RedisplayError("redisplay report lacks required verified scope")
    preflight = report.get("preflight")
    if not isinstance(preflight, Mapping):
        raise Macro4RedisplayError("redisplay preflight record is missing")
    _validate_version(preflight, label="redisplay firmware")
    job = report.get("job")
    if (
        not isinstance(job, Mapping)
        or report.get("job_id") != EXPECTED_TARGET_JOB_ID
        or job.get("job_id") != EXPECTED_TARGET_JOB_ID
        or job.get("action") != "uploaded_frame"
        or job.get("state") != "completed"
        or job.get("result") is not True
        or job.get("frame_fnv1a") != EXPECTED_FRAME_FNV1A
    ):
        raise Macro4RedisplayError("redisplay result is not exact completed macro4 job2")
    diagnostic = report.get("diagnostic")
    if (
        not isinstance(diagnostic, Mapping)
        or diagnostic.get("operation_id") != EXPECTED_TARGET_OPERATION_ID
        or diagnostic.get("job_operation_id") != EXPECTED_TARGET_OPERATION_ID
        or diagnostic.get("job_driver_operation_identity_matched") is not True
        or diagnostic.get("sequence_verified") is not True
        or diagnostic.get("required_busy_stages_verified") is not True
        or diagnostic.get("busy_timeout") is not False
        or diagnostic.get("safe_finish_verified") is not True
    ):
        raise Macro4RedisplayError("redisplay job2/operation2 sequence binding is incomplete")
    _validate_required_busy_trace(diagnostic, label="redisplay diagnostic")
    expected_physical = [
        {
            "controller": record["controller"],
            "mapping": record["mapping"],
            "dtm_bytes": record["dtm_bytes"],
            "dtm_fnv1a": int(record["dtm_fnv1a"], 16),
        }
        for record in _controller_records()
    ]
    if diagnostic.get("physical_controllers") != expected_physical:
        raise Macro4RedisplayError("redisplay DTM identities are not the frozen macro4 streams")
    # perform_refresh already validates the raw driver timing; retain an
    # independent job-duration envelope in the one-shot runner.
    timestamps = tuple(job.get(key) for key in ("queued_at_ms", "started_at_ms", "finished_at_ms"))
    if any(type(value) is not int or not 0 <= value <= 0xFFFFFFFF for value in timestamps):
        raise Macro4RedisplayError("redisplay job timing fields are not uint32")
    queued, started, finished = timestamps
    if _u32_duration(queued, started) > MAX_QUEUE_DELAY_MS or not (
        NOMINAL_JOB_DURATION_MS[0]
        <= _u32_duration(started, finished)
        <= NOMINAL_JOB_DURATION_MS[1]
    ):
        raise Macro4RedisplayError("redisplay job timing is outside the visible-refresh envelope")
    return report


def _perform_redisplay_once(
    base_url: str,
    frame: bytes,
    requester: _AuditedRequester,
    *,
    job_timeout_s: float,
    poll_interval_s: float,
    sleeper: Callable[[float], None],
    clock: Callable[[], float],
) -> Mapping[str, Any]:
    report = perform_refresh(
        base_url,
        frame,
        expected_mappings=FIXED_CONTROLLER_MAPPINGS,
        job_timeout_s=job_timeout_s,
        poll_interval_s=poll_interval_s,
        requester=requester,
        sleeper=sleeper,
        clock=clock,
    )
    return report


def _collect_best_effort_evidence(base_url: str, requester: _AuditedRequester) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for name, endpoint in (
        ("job", "/api/job"),
        ("diagnostic", "/api/diagnostic/report"),
        ("gpio_status_raw", "/api/diagnostic/status"),
    ):
        try:
            evidence[name] = dict(
                _get_json_object(base_url, endpoint, label=f"best-effort {name}", requester=requester)
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
    original_claim: Mapping[str, Any],
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
        "original_quality_claim_preserved": dict(original_claim),
        "candidate": {
            "manifest_file_sha256": EXPECTED_MANIFEST_SHA256,
            "manifest_canonical_sha256": EXPECTED_MANIFEST_CANONICAL_SHA256,
            "algorithm_id": EXPECTED_ALGORITHM_ID,
            "frame_sha256": EXPECTED_FRAME_SHA256,
            "frame_fnv1a": f"0x{EXPECTED_FRAME_FNV1A:08X}",
            "controllers": _controller_records(),
        },
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
            "screen_matches_frozen_strict_preview",
            "power_supply_3_3v_and_cv",
            "current_and_temperature",
            "post_run_gpio_and_power_state",
        ],
        "manual_observation_completed": False,
    }


def run_macro4_redisplay_once(
    result_dir: Path,
    base_url: str,
    *,
    authorization_confirmation: str,
    confirm_j2_powered_supervised: bool = False,
    confirm_supply_and_temperature_normal: bool = False,
    confirm_visual_quality_concern_redisplay: bool = False,
    job_timeout_s: float = DEFAULT_JOB_TIMEOUT_S,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Consume and execute the sole MAP-job1-gated macro4 redisplay action."""

    if not isinstance(result_dir, Path):
        raise Macro4RedisplayError("result_dir must be pathlib.Path")
    destination = _prepare_result_destination(result_dir)
    confirmations = {
        "authorization_confirmation": authorization_confirmation,
        "J2_powered_supervised": confirm_j2_powered_supervised,
        "supply_and_temperature_normal": confirm_supply_and_temperature_normal,
        "visual_quality_concern_redisplay_requested": confirm_visual_quality_concern_redisplay,
    }
    if authorization_confirmation != REQUIRED_AUTHORIZATION_CONFIRMATION:
        raise Macro4RedisplayError("exact frozen-frame redisplay authorization string is required")
    if any(type(value) is not bool or value is not True for value in (
        confirm_j2_powered_supervised,
        confirm_supply_and_temperature_normal,
        confirm_visual_quality_concern_redisplay,
    )):
        raise Macro4RedisplayError(
            "explicit supervised-power, normal-supply/temperature, and visual-quality-concern redisplay confirmations are required"
        )
    if not isinstance(base_url, str) or not base_url.strip():
        raise Macro4RedisplayError("base_url must be a non-empty device root URL")

    _validate_fixed_map_fixture()
    snapshot = _load_candidate_snapshot()
    original_claim = _load_original_quality_claim()
    attempt_id = uuid.uuid4().hex
    created_at_utc = _utc_now()
    claim = _claim_action(
        snapshot,
        original_claim,
        attempt_id=attempt_id,
        claimed_at_utc=created_at_utc,
        result_destination=destination,
        confirmations=confirmations,
    )

    directory: Optional[Path] = None
    requester = _AuditedRequester(http_request)
    prior: Optional[Mapping[str, Any]] = None
    network_report: Optional[Mapping[str, Any]] = None
    target_diagnostic_raw: Optional[Mapping[str, Any]] = None
    post_gpio_raw: Optional[Mapping[str, Any]] = None
    try:
        directory = _create_result_directory(destination, snapshot, claim)
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
            "original_quality_claim_preserved": dict(original_claim),
            "confirmations": confirmations,
            "automatic_retry_authorized": False,
            "automatic_recovery_authorized": False,
            "formal": False,
            "hardware_qualified": False,
            "hardware_tested": False,
        }
        _atomic_new_file(directory, LOCK_FILENAME, _canonical_json(lock))

        prior = _validate_map_job1_prior(base_url, requester)
        network_report = _perform_redisplay_once(
            base_url,
            snapshot.frame,
            requester,
            job_timeout_s=job_timeout_s,
            poll_interval_s=poll_interval_s,
            sleeper=sleeper,
            clock=clock,
        )
        _validate_network_report(network_report)
        if requester.post_issued_count != 1:
            raise Macro4RedisplayError("redisplay did not issue exactly one POST /api/frame")
        target_diagnostic_raw = _get_json_object(
            base_url,
            "/api/diagnostic/report",
            label="post-redisplay raw diagnostic",
            requester=requester,
        )
        try:
            repeated_diagnostic = _validate_diagnostic(
                target_diagnostic_raw,
                snapshot.frame,
                FIXED_CONTROLLER_MAPPINGS,
                network_report["preflight"],
                network_report["job"],
            )
        except (FrameToolError, KeyError, TypeError) as error:
            raise Macro4RedisplayError(
                f"post-redisplay raw diagnostic validation failed: {error}"
            ) from error
        if repeated_diagnostic != network_report["diagnostic"]:
            raise Macro4RedisplayError(
                "post-redisplay raw diagnostic changed after the completed network report"
            )
        target_timing = _validate_timing(
            network_report["job"],
            target_diagnostic_raw,
            label="redisplay",
        )
        post_gpio_raw = _get_json_object(
            base_url,
            "/api/diagnostic/status",
            label="post-redisplay GPIO",
            requester=requester,
        )
        post_gpio_snapshot = _validate_gpio_snapshot(
            post_gpio_raw, label="post-redisplay GPIO"
        )
        result = {
            **_base_result(
                attempt_id=attempt_id,
                claim=claim,
                original_claim=original_claim,
                recorded_at_utc=_utc_now(),
            ),
            "outcome": "protocol_verified_manual_observation_required",
            "protocol_verified": True,
            "prior_map_job1_preflight": dict(prior),
            "network_report": dict(network_report),
            "post_refresh_diagnostic_raw": dict(target_diagnostic_raw),
            "nominal_timing": target_timing,
            "post_refresh_gpio_status_raw": dict(post_gpio_snapshot),
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
                        original_claim=original_claim,
                        recorded_at_utc=_utc_now(),
                    ),
                    "outcome": "unknown_do_not_retry",
                    "protocol_verified": None,
                    "prior_map_job1_preflight": dict(prior) if prior is not None else None,
                    "network_report": dict(network_report) if network_report is not None else None,
                    "post_refresh_diagnostic_raw": (
                        dict(target_diagnostic_raw)
                        if target_diagnostic_raw is not None
                        else None
                    ),
                    "post_refresh_gpio_status_raw": (
                        dict(post_gpio_raw) if post_gpio_raw is not None else None
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
        raise Macro4RedisplayUnknown(
            "macro4 redisplay outcome is unknown_do_not_retry; the independent claim is permanent"
            + detail
        ) from error


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--url", required=True, help="device root URL on the trusted test network")
    parser.add_argument("--confirm", required=True, help="exact one-redisplay authorization string")
    parser.add_argument("--confirm-j2-powered-supervised", action="store_true")
    parser.add_argument("--confirm-supply-and-temperature-normal", action="store_true")
    parser.add_argument("--confirm-visual-quality-concern-redisplay", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        result = run_macro4_redisplay_once(
            args.result_dir,
            args.url,
            authorization_confirmation=args.confirm,
            confirm_j2_powered_supervised=args.confirm_j2_powered_supervised,
            confirm_supply_and_temperature_normal=args.confirm_supply_and_temperature_normal,
            confirm_visual_quality_concern_redisplay=(
                args.confirm_visual_quality_concern_redisplay
            ),
        )
    except Macro4RedisplayError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
