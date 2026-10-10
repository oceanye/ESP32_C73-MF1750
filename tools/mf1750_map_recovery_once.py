#!/usr/bin/env python3
"""Run the single authorized MAP_ORIENT_V1 recovery after the G1/S1 incident.

This entry point has no frame, pattern, requester, or registry injection.  It
generates the canonical MAP fixture internally, validates every frozen
identity, permanently claims the recovery before creating an attempt directory
or touching the network, and never retries an uncertain attempt.
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
from typing import Any, Mapping, Optional, Sequence
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.epd_frame import (  # noqa: E402
    EXPECTED_FIXTURE_HASHES,
    FRAME_BYTES,
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
from tools.mf1750_frame_tool import perform_refresh  # noqa: E402


SCHEMA_VERSION = 1
MAP_FIXTURE_NAME = "map-orient-v1"
MAP_FRAME_SHA256 = "1deedf924e40c676c2080fec08dfe5da10a8c1bb53b699ec4a85b0b6101b5c36"
MAP_EXPECTED_FNV1A = (0x9D04142D, 0xF26832DD, 0xFE199FF5)
INCIDENT_ATTEMPT_ID = "6d5731dbd7bf46d5a4bd11e8737df744"
INCIDENT_FRAME_FNV1A = "0x657DB1B5"
INCIDENT_RESULT_KIND = "mf1750-g1-s1-experimental-refresh-result"
RECOVERY_ACTION_ID = "map-orient-v1-recovery-after-g1-s1-incident"

_FIXED_INCIDENT_DIRECTORY = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "G1S1_AWORDERED_RUN1_20260806_212715"
)
_INCIDENT_RESULT_FILENAME = "EXPERIMENT-RESULT.json"
_DEVICE_JOB_FILENAME = "DEVICE-JOB-AFTER-FAILURE.json"
_DEVICE_DIAGNOSTIC_FILENAME = "DEVICE-DIAGNOSTIC-REPORT-AFTER-FAILURE.json"
_DEVICE_STATUS_FILENAME = "DEVICE-STATUS-AFTER-POWER-CUT.json"
_FIXED_INCIDENT_RESULT_SHA256 = (
    "5c46ef9d075b20d2613d8330d8c0aa366af66bb474d4cabbddb8e0c6a49496c4"
)
_FIXED_DEVICE_JOB_SHA256 = (
    "3749d6f0524efa42145686b0a66e01d8e2b96a9ae5419f4756f9de4c361cd38b"
)
_FIXED_DEVICE_DIAGNOSTIC_SHA256 = (
    "5d14f45ab0c3676318bd4ae022a71c457108e89e73640ac851d886b7a0acb335"
)
_FIXED_DEVICE_STATUS_SHA256 = (
    "11a4f1dabaf4a1e819ef35dee51e56332f78b4afbd97494124cf8fcac9153185"
)

LOCK_FILENAME = "ATTEMPT-LOCK.json"
RESULT_FILENAME = "RECOVERY-RESULT.json"
LOCK_KIND = "mf1750-map-recovery-attempt-lock"
RESULT_KIND = "mf1750-map-recovery-result"
CLAIM_KIND = "mf1750-map-recovery-claim"
CLAIM_REGISTRY_ID = "workspace-mf1750-map-recovery-registry-v1"
DEFAULT_AUTHORIZATION_REGISTRY = (
    REPO_ROOT / ".test-output" / "hardware" / ".mf1750_map_recovery_registry"
)

FIXED_CONTROLLER_MAPPINGS = (
    ControllerMapping(0, False, False, False),
    ControllerMapping(1, False, False, False),
)
EXACT_ACTION = {
    "action_id": RECOVERY_ACTION_ID,
    "method": "POST",
    "endpoint": "/api/frame",
    "fixture": MAP_FIXTURE_NAME,
    "maximum_posts": 1,
    "automatic_retry": False,
}
CLASSIFICATION = {
    "recovery": True,
    "formal": False,
    "hardware_qualified": False,
    "hardware_tested": False,
}
MANUAL_OBSERVATION_REQUIRED = (
    "map_orientation_seam_and_nibble_probes",
    "power_supply_cv_and_current",
    "L1_L2_temperature",
    "busy_timing_and_serial_log",
    "J2_power_cut_and_TP1_discharge",
)


class MapRecoveryError(RuntimeError):
    """The recovery was rejected before its one-shot claim was consumed."""


class MapRecoveryUnknown(MapRecoveryError):
    """The claim was consumed; the recovery must never be attempted again."""


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
        raise MapRecoveryError(f"canonical JSON encoding failed: {error}") from error


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


RECOVERY_IDENTITY = {
    "schema_version": SCHEMA_VERSION,
    "kind": "mf1750-map-recovery-identity",
    "incident_attempt_id": INCIDENT_ATTEMPT_ID,
    "frame": {
        "fixture": MAP_FIXTURE_NAME,
        "bytes": FRAME_BYTES,
        "sha256": MAP_FRAME_SHA256,
        "full_fnv1a": f"0x{MAP_EXPECTED_FNV1A[0]:08X}",
        "cs1_dtm_fnv1a": f"0x{MAP_EXPECTED_FNV1A[1]:08X}",
        "cs2_dtm_fnv1a": f"0x{MAP_EXPECTED_FNV1A[2]:08X}",
    },
    "fixed_controller_mappings": [
        _mapping_record(mapping) for mapping in FIXED_CONTROLLER_MAPPINGS
    ],
    "exact_action": dict(EXACT_ACTION),
}
RECOVERY_IDENTITY_SHA256 = _sha256(_canonical_json(RECOVERY_IDENTITY))
CLAIM_FILENAME = RECOVERY_IDENTITY_SHA256


@dataclass(frozen=True)
class _RecoveryClaim:
    filename: str
    payload_sha256: str
    record: Mapping[str, Any]

    def reference(self) -> dict[str, Any]:
        return {
            "registry_id": CLAIM_REGISTRY_ID,
            "file": self.filename,
            "sha256": self.payload_sha256,
            "recovery_identity_sha256": RECOVERY_IDENTITY_SHA256,
            "attempt_id": self.record["attempt_id"],
            "state": self.record["state"],
        }


def _require_sha256(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise MapRecoveryError(f"{label} must be a SHA-256 string")
    normalized = value.lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise MapRecoveryError(f"{label} must be exactly 64 hexadecimal digits")
    return normalized


def _sha256_argument(value: str) -> str:
    try:
        return _require_sha256(value, label="incident result SHA-256")
    except MapRecoveryError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _attempt_id_argument(value: str) -> str:
    normalized = value.lower() if isinstance(value, str) else ""
    if len(normalized) != 32 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise argparse.ArgumentTypeError("attempt id must be exactly 32 hexadecimal digits")
    return normalized


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _authorization_registry() -> Path:
    """Create and return only the fixed, non-symlinked workspace registry."""

    path = DEFAULT_AUTHORIZATION_REGISTRY
    try:
        require_local_regular_path_syntax(path, label="authorization registry")
        workspace = REPO_ROOT.resolve(strict=True)
        relative = path.relative_to(REPO_ROOT)
    except (LocalPathSafetyError, OSError, ValueError) as error:
        raise MapRecoveryError(
            f"fixed authorization registry is outside the workspace: {error}"
        ) from error
    if not relative.parts or any(part in ("", ".", "..") for part in relative.parts):
        raise MapRecoveryError("fixed authorization registry path is invalid")

    current = REPO_ROOT
    for part in relative.parts:
        current = current / part
        try:
            current.mkdir()
        except FileExistsError:
            pass
        except OSError as error:
            raise MapRecoveryError(
                f"could not create fixed authorization registry: {error}"
            ) from error
        try:
            if current.is_symlink():
                raise MapRecoveryError(
                    "fixed authorization registry must not traverse a symlink"
                )
            resolved = current.resolve(strict=True)
        except OSError as error:
            raise MapRecoveryError(
                f"could not resolve fixed authorization registry: {error}"
            ) from error
        if not current.is_dir():
            raise MapRecoveryError("fixed authorization registry component is not a directory")
        if resolved != current or not _is_within(resolved, workspace):
            raise MapRecoveryError(
                "fixed authorization registry resolved through a link or escaped the workspace"
            )
    return current


def _load_fixed_map_frame() -> bytes:
    if EXPECTED_FIXTURE_HASHES.get(MAP_FIXTURE_NAME) != MAP_EXPECTED_FNV1A:
        raise MapRecoveryError("repository MAP fixture hash contract changed")
    try:
        frame = bytes(generate_fixture(MAP_FIXTURE_NAME))
        validate_frame(frame)
        fixture_report = verify_fixture(MAP_FIXTURE_NAME, frame)
    except (KeyError, TypeError, ValueError) as error:
        raise MapRecoveryError(f"could not generate canonical MAP fixture: {error}") from error
    if len(frame) != FRAME_BYTES or _sha256(frame) != MAP_FRAME_SHA256:
        raise MapRecoveryError("canonical MAP fixture full byte identity changed")
    actual = (
        fnv1a(frame),
        fnv1a(controller_stream(frame, FIXED_CONTROLLER_MAPPINGS[0])),
        fnv1a(controller_stream(frame, FIXED_CONTROLLER_MAPPINGS[1])),
    )
    if actual != MAP_EXPECTED_FNV1A or fixture_report.verified is not True:
        raise MapRecoveryError("canonical MAP fixture FNV or fixture verification failed")
    return frame


def _fixed_incident_directory_path() -> Path:
    """Resolve the frozen incident directory without following workspace links."""

    path = _FIXED_INCIDENT_DIRECTORY
    try:
        require_local_regular_path_syntax(path, label="fixed incident directory")
        workspace = REPO_ROOT.resolve(strict=True)
        relative = path.relative_to(REPO_ROOT)
        current = REPO_ROOT
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise MapRecoveryError(
                    "fixed incident directory must not traverse a symlink"
                )
        resolved = path.resolve(strict=True)
    except (LocalPathSafetyError, OSError, ValueError) as error:
        raise MapRecoveryError(f"fixed incident directory is unavailable: {error}") from error
    if resolved != path or not _is_within(resolved, workspace) or not resolved.is_dir():
        raise MapRecoveryError(
            "fixed incident directory resolved through a link or escaped the workspace"
        )
    return resolved


def _read_frozen_json(
    path: Path,
    expected_sha256: str,
    *,
    label: str,
    require_canonical: bool = False,
) -> tuple[Mapping[str, Any], str]:
    try:
        if path.is_symlink():
            raise MapRecoveryError(f"{label} must not be a symlink")
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise MapRecoveryError(f"{label} must be a regular file")
        payload = resolved.read_bytes()
    except OSError as error:
        raise MapRecoveryError(f"could not read {label}: {error}") from error
    actual_sha256 = _sha256(payload)
    if actual_sha256 != expected_sha256:
        raise MapRecoveryError(f"{label} does not match its frozen SHA-256")
    try:
        record = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MapRecoveryError(f"{label} is not valid UTF-8 JSON: {error}") from error
    if not isinstance(record, Mapping):
        raise MapRecoveryError(f"{label} must contain a JSON object")
    if require_canonical and _canonical_json(record) != payload:
        raise MapRecoveryError(f"{label} must be canonical JSON")
    return record, actual_sha256


def _validate_frozen_incident_semantics(
    result: Mapping[str, Any],
    job: Mapping[str, Any],
    diagnostic: Mapping[str, Any],
    status: Mapping[str, Any],
) -> None:
    candidate = result.get("candidate")
    if (
        result.get("kind") != INCIDENT_RESULT_KIND
        or result.get("attempt_id") != INCIDENT_ATTEMPT_ID
        or result.get("outcome") != "unknown_do_not_retry"
        or result.get("authorization_consumed_permanently") is not True
        or not isinstance(candidate, Mapping)
        or candidate.get("frame_fnv1a") != INCIDENT_FRAME_FNV1A
    ):
        raise MapRecoveryError("incident result does not identify the fixed failed attempt")

    expected_input_fnv1a = int(INCIDENT_FRAME_FNV1A, 16)
    job_expected = {
        "job_id": 2,
        "action": "uploaded_frame",
        "state": "failed",
        "result": False,
        "frame_fnv1a": expected_input_fnv1a,
    }
    if any(job.get(key) != value for key, value in job_expected.items()):
        raise MapRecoveryError("frozen device job is not failed job 2 for the incident frame")
    if type(job.get("job_id")) is not int or type(job.get("frame_fnv1a")) is not int:
        raise MapRecoveryError("frozen device job integer identities are invalid")
    if type(job.get("result")) is not bool:
        raise MapRecoveryError("frozen device job result must be boolean")

    diagnostic_expected = {
        "job_id": 2,
        "job_action": "uploaded_frame",
        "job_state": "failed",
        "job_result": False,
        "job_operation_id": 2,
        "operation_id": 2,
        "valid": True,
        "running": False,
        "sequence_ok": False,
        "wait_timeout": True,
        "busy_assertion_missing": False,
        "mapping_applied": True,
        "pon_busy_seen": True,
        "drf_busy_seen": True,
        "pof_busy_seen": False,
        "post_psr_busy_seen": False,
        "spi_hz": 1_000_000,
        "input_fnv1a": expected_input_fnv1a,
        "cs1_dtm_fnv1a": 0x43E97823,
        "cs2_dtm_fnv1a": 0xE8FA6243,
        "pon_ms": 180,
        "drf_ms": 60010,
        "pof_ms": 0,
        "post_psr_ms": 0,
        "last_wait_ms": 30005,
        "last_wait_stage": "POF cleanup after DRF failure",
        "timeout_stage": "DRF",
        "busy_missing_stage": "none",
    }
    if any(diagnostic.get(key) != value for key, value in diagnostic_expected.items()):
        raise MapRecoveryError("frozen diagnostic does not prove the DRF and cleanup timeouts")
    for key in (
        "job_id",
        "job_operation_id",
        "operation_id",
        "spi_hz",
        "input_fnv1a",
        "cs1_dtm_fnv1a",
        "cs2_dtm_fnv1a",
        "pon_ms",
        "drf_ms",
        "pof_ms",
        "post_psr_ms",
        "last_wait_ms",
    ):
        if type(diagnostic.get(key)) is not int:
            raise MapRecoveryError(f"frozen diagnostic {key} must be an integer")
    for key in (
        "job_result",
        "valid",
        "running",
        "sequence_ok",
        "wait_timeout",
        "busy_assertion_missing",
        "mapping_applied",
        "pon_busy_seen",
        "drf_busy_seen",
        "pof_busy_seen",
        "post_psr_busy_seen",
    ):
        if type(diagnostic.get(key)) is not bool:
            raise MapRecoveryError(f"frozen diagnostic {key} must be boolean")
    for job_key, diagnostic_key in (
        ("queued_at_ms", "job_queued_at_ms"),
        ("started_at_ms", "job_started_at_ms"),
        ("finished_at_ms", "job_finished_at_ms"),
    ):
        if (
            type(job.get(job_key)) is not int
            or diagnostic.get(diagnostic_key) != job.get(job_key)
        ):
            raise MapRecoveryError("frozen job and diagnostic timestamps are not bound")
    mapping = diagnostic.get("mapping")
    expected_mapping = {
        "cs1_source_half": 0,
        "cs1_flip_x": False,
        "cs1_flip_y": False,
        "cs1_nibble_swap": False,
        "cs2_source_half": 1,
        "cs2_flip_x": False,
        "cs2_flip_y": False,
        "cs2_nibble_swap": False,
    }
    if mapping != expected_mapping:
        raise MapRecoveryError("frozen diagnostic mapping is not the fixed panel mapping")
    if not isinstance(mapping, Mapping) or any(
        type(mapping.get(key)) is not bool
        for key in (
            "cs1_flip_x",
            "cs1_flip_y",
            "cs1_nibble_swap",
            "cs2_flip_x",
            "cs2_flip_y",
            "cs2_nibble_swap",
        )
    ):
        raise MapRecoveryError("frozen diagnostic mapping field types are invalid")
    if any(
        type(mapping.get(key)) is not int
        for key in ("cs1_source_half", "cs2_source_half")
    ):
        raise MapRecoveryError("frozen diagnostic mapping source halves must be integers")
    expected_status = {"busy": 0, "rst": 0, "cs": 0, "cs2": 0}
    if status != expected_status or any(type(value) is not int for value in status.values()):
        raise MapRecoveryError("frozen post-power-cut status does not hold all panel pins low")


def _load_fixed_incident_bundle() -> dict[str, Any]:
    directory = _fixed_incident_directory_path()
    result, result_sha256 = _read_frozen_json(
        directory / _INCIDENT_RESULT_FILENAME,
        _FIXED_INCIDENT_RESULT_SHA256,
        label="fixed incident result",
        require_canonical=True,
    )
    job, job_sha256 = _read_frozen_json(
        directory / _DEVICE_JOB_FILENAME,
        _FIXED_DEVICE_JOB_SHA256,
        label="frozen device job",
    )
    diagnostic, diagnostic_sha256 = _read_frozen_json(
        directory / _DEVICE_DIAGNOSTIC_FILENAME,
        _FIXED_DEVICE_DIAGNOSTIC_SHA256,
        label="frozen device diagnostic",
    )
    status, status_sha256 = _read_frozen_json(
        directory / _DEVICE_STATUS_FILENAME,
        _FIXED_DEVICE_STATUS_SHA256,
        label="frozen post-power-cut status",
    )
    _validate_frozen_incident_semantics(result, job, diagnostic, status)
    return {
        "incident_attempt_id": INCIDENT_ATTEMPT_ID,
        "incident_directory": str(directory),
        "files": {
            "incident_result": {
                "file": _INCIDENT_RESULT_FILENAME,
                "sha256": result_sha256,
            },
            "device_job_after_failure": {
                "file": _DEVICE_JOB_FILENAME,
                "sha256": job_sha256,
            },
            "device_diagnostic_after_failure": {
                "file": _DEVICE_DIAGNOSTIC_FILENAME,
                "sha256": diagnostic_sha256,
            },
            "device_status_after_power_cut": {
                "file": _DEVICE_STATUS_FILENAME,
                "sha256": status_sha256,
            },
        },
        "semantics_verified": {
            "failed_job_2_and_frame_identity": True,
            "driver_operation_2_drf_and_cleanup_timeout": True,
            "post_power_cut_panel_pins_low": True,
        },
    }


def _incident_result_file_evidence(path: Path, authorized_sha256: str) -> dict[str, Any]:
    if authorized_sha256 != _FIXED_INCIDENT_RESULT_SHA256:
        raise MapRecoveryError("incident result authorization is not the frozen SHA-256")
    try:
        require_local_regular_path_syntax(path, label="incident result")
        if path.is_symlink():
            raise MapRecoveryError("incident result must not be a symlink")
        requested = path.resolve(strict=True)
    except LocalPathSafetyError as error:
        raise MapRecoveryError(str(error)) from error
    except OSError as error:
        raise MapRecoveryError(f"could not resolve incident result: {error}") from error
    bundle = _load_fixed_incident_bundle()
    fixed_result = Path(bundle["incident_directory"]) / _INCIDENT_RESULT_FILENAME
    if requested != fixed_result:
        raise MapRecoveryError("incident result path is not the fixed workspace evidence")
    return {"mode": "incident_result_file", **bundle}


def _incident_evidence(
    *,
    incident_result_path: Optional[Path],
    incident_result_sha256: Optional[str],
    incident_attempt_id: Optional[str],
) -> dict[str, Any]:
    file_mode = incident_result_path is not None or incident_result_sha256 is not None
    id_mode = incident_attempt_id is not None
    if file_mode == id_mode:
        raise MapRecoveryError(
            "provide either incident result path+SHA-256 or the explicit incident attempt id"
        )
    if file_mode:
        if not isinstance(incident_result_path, Path) or incident_result_sha256 is None:
            raise MapRecoveryError("incident result path and SHA-256 must be provided together")
        return _incident_result_file_evidence(
            incident_result_path,
            _require_sha256(incident_result_sha256, label="incident result SHA-256"),
        )
    if incident_attempt_id != INCIDENT_ATTEMPT_ID:
        raise MapRecoveryError("incident attempt id does not match the fixed recovery incident")
    return {"mode": "explicit_incident_attempt_id_with_frozen_evidence", **_load_fixed_incident_bundle()}


def _prepare_new_result_destination(result_dir: Path) -> Path:
    try:
        require_local_regular_path_syntax(result_dir, label="result directory")
    except LocalPathSafetyError as error:
        raise MapRecoveryError(str(error)) from error
    if os.path.lexists(result_dir):
        raise MapRecoveryError("result directory already exists; refusing overwrite or rerun")
    try:
        parent = result_dir.parent.resolve(strict=True)
    except OSError as error:
        raise MapRecoveryError(f"result parent does not exist: {error}") from error
    if not parent.is_dir():
        raise MapRecoveryError("result parent must be a directory")
    destination = parent / result_dir.name
    if os.path.lexists(destination):
        raise MapRecoveryError("result directory already exists; refusing overwrite or rerun")
    return destination


def _create_result_directory(destination: Path, registry: Path) -> Path:
    if _is_within(destination, registry):
        raise MapRecoveryError("result directory must not be inside the claim registry")
    try:
        destination.mkdir()
    except FileExistsError as error:
        raise MapRecoveryError("result directory appeared; refusing overwrite") from error
    except OSError as error:
        raise MapRecoveryError(f"could not create result directory: {error}") from error
    return destination


def _atomic_new_file(directory: Path, name: str, payload: bytes) -> None:
    temporary = directory / f".{name}.tmp-{uuid.uuid4().hex}"
    destination = directory / name
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        temporary.unlink()
    except FileExistsError as error:
        raise MapRecoveryError(f"{name} already exists; refusing overwrite") from error
    except OSError as error:
        raise MapRecoveryError(f"could not atomically write {name}: {error}") from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _claim_recovery(
    registry: Path,
    *,
    attempt_id: str,
    claimed_at_utc: str,
    result_destination: Path,
    incident_evidence: Mapping[str, Any],
) -> _RecoveryClaim:
    record = {
        "schema_version": SCHEMA_VERSION,
        "kind": CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "attempt_id": attempt_id,
        "claimed_at_utc": claimed_at_utc,
        "state": "recovery_identity_permanently_consumed_do_not_rerun",
        "recovery_identity_sha256": RECOVERY_IDENTITY_SHA256,
        "recovery_identity": RECOVERY_IDENTITY,
        "incident_evidence": dict(incident_evidence),
        "result_directory": str(result_destination),
        "authorization_consumed_permanently": True,
        "automatic_retry_authorized": False,
        "formal": False,
        "hardware_qualified": False,
        "hardware_tested": False,
    }
    payload = _canonical_json(record)
    payload_sha256 = _sha256(payload)
    claim = _RecoveryClaim(CLAIM_FILENAME, payload_sha256, record)
    temporary = registry / f".{CLAIM_FILENAME}.tmp-{uuid.uuid4().hex}"
    destination = registry / CLAIM_FILENAME
    claim_linked = False
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        claim_linked = True
        # The destination is the permanent claim. Failure to remove its
        # already-linked staging name is harmless and must never make this
        # consumed authorization look retryable.
        try:
            temporary.unlink()
        except OSError:
            pass
    except FileExistsError as error:
        if claim_linked:
            raise MapRecoveryUnknown(
                "MAP recovery claim exists; post-claim cleanup failed; do not retry"
            ) from error
        raise MapRecoveryError(
            "this fixed MAP recovery identity was already permanently consumed; do not rerun"
        ) from error
    except BaseException as error:
        if claim_linked:
            raise MapRecoveryUnknown(
                "MAP recovery claim exists; post-claim processing failed; do not retry"
            ) from error
        if not isinstance(error, OSError):
            raise
        raise MapRecoveryError(f"could not atomically claim MAP recovery: {error}") from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except BaseException:
            # This is only removal of a staging hard-link name. Once the
            # destination exists, no cleanup signal may re-arm the recovery.
            pass
    return claim


def _fixture_record() -> dict[str, Any]:
    return dict(RECOVERY_IDENTITY["frame"])


def _base_record(
    *,
    attempt_id: str,
    recorded_at_utc: str,
    claim: _RecoveryClaim,
    incident_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": RESULT_KIND,
        "attempt_id": attempt_id,
        "recorded_at_utc": recorded_at_utc,
        "state": "recovery_identity_permanently_consumed_do_not_rerun",
        "recovery_identity_sha256": RECOVERY_IDENTITY_SHA256,
        "incident_evidence": dict(incident_evidence),
        "fixture": _fixture_record(),
        "authorization_claim": claim.reference(),
        "exact_action": dict(EXACT_ACTION),
        "authorization_consumed_permanently": True,
        "automatic_retry_authorized": False,
        "classification": dict(CLASSIFICATION),
        "formal": False,
        "hardware_qualified": False,
        "hardware_tested": False,
        "manual_observation_required": list(MANUAL_OBSERVATION_REQUIRED),
        "manual_observation_completed": False,
    }


def _perform_fixed_refresh(base_url: str, frame: bytes) -> dict[str, Any]:
    """Production network seam: exact current preflight and the fixed mappings."""

    return perform_refresh(
        base_url,
        frame,
        expected_mappings=FIXED_CONTROLLER_MAPPINGS,
    )


def run_map_recovery_once(
    result_dir: Path,
    base_url: str,
    *,
    incident_result_path: Optional[Path] = None,
    incident_result_sha256: Optional[str] = None,
    incident_attempt_id: Optional[str] = None,
    confirm_recovery_after_incident: bool = False,
    confirm_j2_powered_supervised: bool = False,
    confirm_cold_start: bool = False,
) -> dict[str, Any]:
    """Consume and run the sole fixed MAP recovery authorization."""

    if not isinstance(result_dir, Path):
        raise MapRecoveryError("result_dir must be a pathlib.Path")
    destination = _prepare_new_result_destination(result_dir)
    confirmations = {
        "recovery_after_incident": confirm_recovery_after_incident,
        "J2_powered_supervised": confirm_j2_powered_supervised,
        "cold_start": confirm_cold_start,
    }
    if any(type(value) is not bool or value is not True for value in confirmations.values()):
        raise MapRecoveryError("all three explicit recovery confirmations are required")
    if not isinstance(base_url, str) or not base_url.strip():
        raise MapRecoveryError("base_url must be a non-empty device root URL")
    evidence = _incident_evidence(
        incident_result_path=incident_result_path,
        incident_result_sha256=incident_result_sha256,
        incident_attempt_id=incident_attempt_id,
    )
    frame = _load_fixed_map_frame()
    registry = _authorization_registry()
    attempt_id = uuid.uuid4().hex
    created_at_utc = _utc_now()
    claim = _claim_recovery(
        registry,
        attempt_id=attempt_id,
        claimed_at_utc=created_at_utc,
        result_destination=destination,
        incident_evidence=evidence,
    )

    directory: Optional[Path] = None
    try:
        directory = _create_result_directory(destination, registry)
        lock = {
            "schema_version": SCHEMA_VERSION,
            "kind": LOCK_KIND,
            "attempt_id": attempt_id,
            "created_at_utc": created_at_utc,
            "state": "recovery_identity_permanently_consumed_do_not_rerun",
            "recovery_identity_sha256": RECOVERY_IDENTITY_SHA256,
            "incident_evidence": dict(evidence),
            "fixture": _fixture_record(),
            "authorization_claim": claim.reference(),
            "exact_action": dict(EXACT_ACTION),
            "confirmations": confirmations,
            "fixed_controller_mappings": [
                _mapping_record(mapping) for mapping in FIXED_CONTROLLER_MAPPINGS
            ],
            "authorization_consumed_permanently": True,
            "automatic_retry_authorized": False,
            "formal": False,
            "hardware_qualified": False,
            "hardware_tested": False,
        }
        _atomic_new_file(directory, LOCK_FILENAME, _canonical_json(lock))

        network_report = _perform_fixed_refresh(base_url, frame)
        if (
            network_report.get("protocol_verified") is not True
            or network_report.get("hardware_tested") is not False
        ):
            raise MapRecoveryError("refresh report lost its fail-closed classification")
        result = {
            **_base_record(
                attempt_id=attempt_id,
                recorded_at_utc=_utc_now(),
                claim=claim,
                incident_evidence=evidence,
            ),
            "outcome": "protocol_verified_manual_observation_required",
            "protocol_verified": True,
            "network_report": network_report,
        }
        _atomic_new_file(directory, RESULT_FILENAME, _canonical_json(result))
        return result
    except BaseException as error:
        record_error: Optional[BaseException] = None
        if directory is not None:
            unknown = {
                **_base_record(
                    attempt_id=attempt_id,
                    recorded_at_utc=_utc_now(),
                    claim=claim,
                    incident_evidence=evidence,
                ),
                "outcome": "unknown_do_not_retry",
                "protocol_verified": None,
                "network_report": None,
                "error": {"type": type(error).__name__, "message": str(error)},
            }
            try:
                _atomic_new_file(directory, RESULT_FILENAME, _canonical_json(unknown))
            except BaseException as result_error:
                record_error = result_error
        detail = (
            f"; recovery result could not be recorded ({record_error})"
            if record_error is not None
            else ""
        )
        raise MapRecoveryUnknown(
            "MAP recovery outcome is unknown_do_not_retry; the global claim is permanent"
            f"{detail}"
        ) from error


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--url", required=True, help="device root URL on the trusted test network")
    parser.add_argument("--incident-result-path", type=Path)
    parser.add_argument("--incident-result-sha256", type=_sha256_argument)
    parser.add_argument("--incident-attempt-id", type=_attempt_id_argument)
    parser.add_argument("--confirm-recovery-after-incident", action="store_true")
    parser.add_argument("--confirm-j2-powered-supervised", action="store_true")
    parser.add_argument("--confirm-cold-start", action="store_true")
    args = parser.parse_args(argv)
    file_mode = args.incident_result_path is not None or args.incident_result_sha256 is not None
    id_mode = args.incident_attempt_id is not None
    if file_mode == id_mode:
        parser.error(
            "provide either --incident-result-path with --incident-result-sha256, "
            "or --incident-attempt-id"
        )
    if file_mode and (
        args.incident_result_path is None or args.incident_result_sha256 is None
    ):
        parser.error("--incident-result-path and --incident-result-sha256 are required together")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        result = run_map_recovery_once(
            args.result_dir,
            args.url,
            incident_result_path=args.incident_result_path,
            incident_result_sha256=args.incident_result_sha256,
            incident_attempt_id=args.incident_attempt_id,
            confirm_recovery_after_incident=args.confirm_recovery_after_incident,
            confirm_j2_powered_supervised=args.confirm_j2_powered_supervised,
            confirm_cold_start=args.confirm_cold_start,
        )
    except MapRecoveryUnknown as error:
        print(f"UNKNOWN_DO_NOT_RETRY: {error}", file=sys.stderr)
        return 3
    except MapRecoveryError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(_canonical_json(result).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
