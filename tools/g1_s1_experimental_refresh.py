#!/usr/bin/env python3
"""Run one supervised, experimental G1/S1 panel refresh exactly once.

This runner is intentionally separate from the offline candidate generator.  It
requires an already complete candidate bundle, an authorization bound to the
exact ``manifest.json`` file bytes, three explicit physical confirmations, and
a brand-new result directory.  A workspace-global claim permanently consumes
the authorized manifest SHA before any attempt-local write or network action;
neither changing the result directory nor a later local/network failure can
re-arm it.
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

from host.epd_frame import ControllerMapping, fnv1a, validate_frame  # noqa: E402
from tools.g1_s1_panel_candidate import (  # noqa: E402
    CandidateError,
    PHOTO_SOURCE_KIND,
    SOURCE_INPUT_FILENAME,
    validate_candidate_directory,
)
from tools.local_path_safety import (  # noqa: E402
    LocalPathSafetyError,
    require_local_regular_path_syntax,
)
from tools.mf1750_frame_tool import (  # noqa: E402
    DEFAULT_JOB_TIMEOUT_S,
    DEFAULT_POLL_INTERVAL_S,
    perform_refresh,
)


LOCK_FILENAME = "ATTEMPT-LOCK.json"
RESULT_FILENAME = "EXPERIMENT-RESULT.json"
LOCK_KIND = "mf1750-g1-s1-experimental-refresh-attempt-lock"
RESULT_KIND = "mf1750-g1-s1-experimental-refresh-result"
CLAIM_KIND = "mf1750-g1-s1-experimental-refresh-authorization-claim"
CLAIM_REGISTRY_ID = "workspace-g1-s1-authorization-registry-v1"
SCHEMA_VERSION = 1
DEFAULT_AUTHORIZATION_REGISTRY = (
    REPO_ROOT / ".test-output" / "hardware" / ".g1_s1_authorization_registry"
)
BASE_REQUIRED_CANDIDATE_FILES = frozenset(
    {"frame.bin", "manifest.json", "source.png", "mapped.png", "final.png", "model.png"}
)
PHOTO_REQUIRED_CANDIDATE_FILES = frozenset(
    {*BASE_REQUIRED_CANDIDATE_FILES, SOURCE_INPUT_FILENAME}
)
# Retain the old public name for callers that describe the legacy synthetic
# bundle shape.  Runtime selection is exact and source-kind aware below.
REQUIRED_CANDIDATE_FILES = BASE_REQUIRED_CANDIDATE_FILES
PREVIEW_STAGES = ("source", "mapped", "final", "model")
FIXED_CONTROLLER_MAPPINGS = (
    ControllerMapping(0, False, False, False),
    ControllerMapping(1, False, False, False),
)
EXPERIMENTAL_CLASSIFICATION = {
    "experimental": True,
    "uncalibrated": True,
    "formal": False,
    "hardware_qualified": False,
    "hardware_tested": False,
}
MANUAL_OBSERVATION_REQUIRED = (
    "full_panel_visual_result",
    "power_supply_cv_and_current",
    "L1_L2_temperature",
    "busy_timing_and_serial_log",
    "J2_power_cut_and_TP1_discharge",
)
EXACT_ACTION = {
    "method": "POST",
    "endpoint": "/api/frame",
    "maximum_posts": 1,
    "automatic_retry": False,
}


class ExperimentalRefreshError(RuntimeError):
    """Raised before a refresh or when a safe result cannot be recorded."""


class ExperimentalRefreshUnknown(ExperimentalRefreshError):
    """The one allowed network attempt began and must not be retried."""


@dataclass(frozen=True)
class _CandidateSnapshot:
    directory: Path
    manifest: Mapping[str, Any]
    manifest_bytes: bytes
    manifest_file_sha256: str
    frame: bytes


@dataclass(frozen=True)
class _AuthorizationClaim:
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
        raise ExperimentalRefreshError(
            f"value cannot be represented as canonical JSON: {error}"
        ) from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _sha256_argument(value: str) -> str:
    normalized = value.lower() if isinstance(value, str) else ""
    if len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized):
        raise argparse.ArgumentTypeError("expected exactly 64 hexadecimal SHA-256 digits")
    return normalized


def _require_sha256(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise ExperimentalRefreshError(f"{label} must be a SHA-256 string")
    normalized = value.lower()
    if len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized):
        raise ExperimentalRefreshError(f"{label} must be exactly 64 hexadecimal digits")
    return normalized


def _mapping_record(mapping: ControllerMapping) -> dict[str, int | bool]:
    return {
        "source_half": mapping.source_half,
        "flip_x": mapping.flip_x,
        "flip_y": mapping.flip_y,
        "nibble_swap": mapping.nibble_swap,
    }


def _exact_recorded_file(
    directory: Path,
    record: object,
    *,
    required_name: str,
    label: str,
) -> bytes:
    if not isinstance(record, Mapping) or record.get("file") != required_name:
        raise ExperimentalRefreshError(f"{label} file identity is invalid")
    payload = (directory / required_name).read_bytes()
    if record.get("bytes") != len(payload) or record.get("sha256") != _sha256(payload):
        raise ExperimentalRefreshError(f"{label} bytes changed after candidate validation")
    return payload


def _load_candidate_snapshot(
    candidate_dir: Path,
    authorized_manifest_sha256: str,
) -> _CandidateSnapshot:
    """Deep-validate and snapshot every authorized byte before any network call."""

    try:
        manifest = validate_candidate_directory(candidate_dir)
    except (CandidateError, OSError, ValueError) as error:
        raise ExperimentalRefreshError(f"candidate validation failed: {error}") from error
    if not isinstance(manifest, Mapping):
        raise ExperimentalRefreshError("candidate validator did not return a manifest object")
    try:
        directory = candidate_dir.resolve(strict=True)
        entries = tuple(directory.iterdir())
        actual_files = {path.name for path in entries if path.is_file()}
        source_record = manifest.get("source")
        photo_source = (
            isinstance(source_record, Mapping)
            and source_record.get("source_kind") == PHOTO_SOURCE_KIND
        )
        required_files = (
            PHOTO_REQUIRED_CANDIDATE_FILES
            if photo_source
            else BASE_REQUIRED_CANDIDATE_FILES
        )
        if actual_files != required_files or any(path.is_dir() for path in entries):
            raise ExperimentalRefreshError("candidate file set changed after validation")

        manifest_bytes = (directory / "manifest.json").read_bytes()
        if manifest_bytes != _canonical_json(manifest):
            raise ExperimentalRefreshError("manifest bytes changed after candidate validation")
        manifest_file_sha256 = _sha256(manifest_bytes)
        if manifest_file_sha256 != authorized_manifest_sha256:
            raise ExperimentalRefreshError(
                "authorized manifest file SHA-256 does not match manifest.json bytes"
            )
        if photo_source:
            assert isinstance(source_record, Mapping)
            _exact_recorded_file(
                directory,
                source_record.get("input"),
                required_name=SOURCE_INPUT_FILENAME,
                label="candidate frozen photo source input",
            )

        if manifest.get("classification") != {
            "experimental": True,
            "uncalibrated": True,
            "formal": False,
            "hardware_tested": False,
            "upload_authorized": False,
        }:
            raise ExperimentalRefreshError("candidate is not the fail-closed experimental class")
        transport = manifest.get("transport")
        if not isinstance(transport, Mapping) or transport != {
            "mode": "offline",
            "endpoint": None,
            "method": None,
            "device_io_performed": False,
            "hardware_tested": False,
        }:
            raise ExperimentalRefreshError(
                "refresh runner accepts only a completely offline candidate bundle"
            )
        options = manifest.get("options")
        option_value = options.get("value") if isinstance(options, Mapping) else None
        algorithm = option_value.get("algorithm") if isinstance(option_value, Mapping) else None
        if not isinstance(algorithm, str) or not algorithm:
            raise ExperimentalRefreshError("candidate algorithm binding is missing")
        simulation = manifest.get("simulation")
        simulation_report_sha256 = (
            simulation.get("report_canonical_sha256")
            if isinstance(simulation, Mapping)
            else None
        )
        _require_sha256(
            simulation_report_sha256,
            label="candidate simulation report canonical SHA-256",
        )

        frame_record = manifest.get("frame")
        frame = _exact_recorded_file(
            directory, frame_record, required_name="frame.bin", label="candidate frame"
        )
        validate_frame(frame)
        if not isinstance(frame_record, Mapping) or frame_record.get("fnv1a") != f"0x{fnv1a(frame):08X}":
            raise ExperimentalRefreshError("candidate frame FNV-1a identity changed")

        preview_records = manifest.get("previews")
        if not isinstance(preview_records, Mapping) or set(preview_records) != set(PREVIEW_STAGES):
            raise ExperimentalRefreshError("candidate preview records are incomplete")
        for stage in PREVIEW_STAGES:
            _exact_recorded_file(
                directory,
                preview_records[stage],
                required_name=f"{stage}.png",
                label=f"candidate {stage} preview",
            )
    except ExperimentalRefreshError:
        raise
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise ExperimentalRefreshError(
            f"candidate changed while taking the authorized snapshot: {error}"
        ) from error

    return _CandidateSnapshot(
        directory=directory,
        manifest=dict(manifest),
        manifest_bytes=manifest_bytes,
        manifest_file_sha256=manifest_file_sha256,
        frame=frame,
    )


def _prepare_new_result_destination(result_dir: Path) -> Path:
    try:
        require_local_regular_path_syntax(result_dir, label="result directory")
    except LocalPathSafetyError as error:
        raise ExperimentalRefreshError(str(error)) from error
    if os.path.lexists(result_dir):
        raise ExperimentalRefreshError(
            "result directory already exists; this attempt must not be rerun or overwritten"
        )
    try:
        parent = result_dir.parent.resolve(strict=True)
    except OSError as error:
        raise ExperimentalRefreshError(f"result parent does not exist: {error}") from error
    if not parent.is_dir():
        raise ExperimentalRefreshError("result parent must be a directory")
    destination = parent / result_dir.name
    if os.path.lexists(destination):
        raise ExperimentalRefreshError(
            "result directory already exists; this attempt must not be rerun or overwritten"
        )
    return destination


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _create_result_directory(destination: Path, candidate_dir: Path) -> Path:
    if _is_within(destination, candidate_dir):
        raise ExperimentalRefreshError("result directory must not be inside the candidate bundle")
    try:
        destination.mkdir()
    except FileExistsError as error:
        raise ExperimentalRefreshError(
            "result directory appeared; this attempt must not be rerun"
        ) from error
    except OSError as error:
        raise ExperimentalRefreshError(f"could not create result directory: {error}") from error
    return destination


def _authorization_registry() -> Path:
    """Return the single production authorization registry.

    There is deliberately no public/path parameter.  Tests isolate this fixed
    production dependency by monkeypatching this private helper, never by
    widening the production runner API.
    """

    path = DEFAULT_AUTHORIZATION_REGISTRY
    try:
        require_local_regular_path_syntax(path, label="authorization registry")
    except LocalPathSafetyError as error:
        raise ExperimentalRefreshError(str(error)) from error
    if os.path.lexists(path) and path.is_symlink():
        raise ExperimentalRefreshError("authorization registry must not be a symlink")
    try:
        parent = path.parent.resolve(strict=True)
        workspace = REPO_ROOT.resolve(strict=True)
        if not parent.is_dir() or not _is_within(parent, workspace):
            raise ExperimentalRefreshError(
                "authorization registry parent must be a workspace directory"
            )
        path.mkdir(exist_ok=True)
        registry = path.resolve(strict=True)
    except OSError as error:
        raise ExperimentalRefreshError(f"could not create authorization registry: {error}") from error
    if path.is_symlink() or not registry.is_dir():
        raise ExperimentalRefreshError("authorization registry must be a directory")
    if not _is_within(registry, workspace):
        raise ExperimentalRefreshError("default authorization registry escaped the workspace")
    return registry


def _claim_authorization(
    snapshot: _CandidateSnapshot,
    *,
    attempt_id: str,
    claimed_at_utc: str,
    result_destination: Path,
) -> _AuthorizationClaim:
    """Atomically and permanently consume one manifest-file authorization."""

    registry = _authorization_registry()
    # The exact manifest-file SHA is the complete claim filename.  No result
    # directory component is present, so changing result-dir cannot re-arm it.
    filename = snapshot.manifest_file_sha256
    destination = registry / filename
    record = {
        "schema_version": SCHEMA_VERSION,
        "kind": CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "attempt_id": attempt_id,
        "claimed_at_utc": claimed_at_utc,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "authorization_consumed_permanently": True,
        "manifest_file_sha256": snapshot.manifest_file_sha256,
        "frame_sha256": snapshot.manifest["frame"]["sha256"],
        "algorithm": snapshot.manifest["options"]["value"]["algorithm"],
        "simulation_report_canonical_sha256": snapshot.manifest["simulation"][
            "report_canonical_sha256"
        ],
        "result_directory": str(result_destination),
        "exact_action": dict(EXACT_ACTION),
        "automatic_retry_authorized": False,
        "formal": False,
        "hardware_qualified": False,
        "hardware_tested": False,
    }
    payload = _canonical_json(record)
    temporary = registry / f".{filename}.tmp-{uuid.uuid4().hex}"
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        temporary.unlink()
    except FileExistsError as error:
        raise ExperimentalRefreshError(
            "this authorized manifest SHA-256 was already permanently consumed; do not rerun"
        ) from error
    except OSError as error:
        raise ExperimentalRefreshError(
            f"could not atomically claim the manifest authorization: {error}"
        ) from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return _AuthorizationClaim(registry, filename, _sha256(payload), record)


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
        raise ExperimentalRefreshError(f"{name} already exists; refusing overwrite") from error
    except OSError as error:
        raise ExperimentalRefreshError(f"could not atomically write {name}: {error}") from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _write_result(directory: Path, result: Mapping[str, Any]) -> None:
    _atomic_new_file(directory, RESULT_FILENAME, _canonical_json(result))


def _base_result(
    attempt_id: str,
    snapshot: _CandidateSnapshot,
    claim: _AuthorizationClaim,
    *,
    recorded_at_utc: str,
) -> dict[str, Any]:
    frame_record = snapshot.manifest["frame"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": RESULT_KIND,
        "attempt_id": attempt_id,
        "recorded_at_utc": recorded_at_utc,
        "candidate": {
            "manifest_file_sha256": snapshot.manifest_file_sha256,
            "manifest_integrity_sha256": snapshot.manifest["manifest_integrity"][
                "canonical_sha256"
            ],
            "frame_sha256": frame_record["sha256"],
            "frame_fnv1a": frame_record["fnv1a"],
            "algorithm": snapshot.manifest["options"]["value"]["algorithm"],
            "simulation_report_canonical_sha256": snapshot.manifest["simulation"][
                "report_canonical_sha256"
            ],
        },
        "authorization_claim": claim.reference(),
        "exact_action": dict(EXACT_ACTION),
        "authorization_state": "authorization_permanently_consumed_do_not_rerun",
        "authorization_consumed_permanently": True,
        "formal": False,
        "hardware_qualified": False,
        "hardware_tested": False,
        "classification": dict(EXPERIMENTAL_CLASSIFICATION),
        "manual_observation_required": list(MANUAL_OBSERVATION_REQUIRED),
        "manual_observation_completed": False,
        "automatic_retry_authorized": False,
    }


def run_experimental_refresh(
    candidate_dir: Path,
    result_dir: Path,
    base_url: str,
    *,
    authorized_manifest_sha256: str,
    confirm_experimental_uncalibrated: bool = False,
    confirm_j2_powered_supervised: bool = False,
    confirm_cold_start: bool = False,
    job_timeout_s: float = DEFAULT_JOB_TIMEOUT_S,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Perform the one and only network refresh associated with ``result_dir``."""

    if not isinstance(candidate_dir, Path) or not isinstance(result_dir, Path):
        raise ExperimentalRefreshError("candidate_dir and result_dir must be pathlib.Path objects")
    destination = _prepare_new_result_destination(result_dir)
    authorized_hash = _require_sha256(
        authorized_manifest_sha256, label="authorized manifest file SHA-256"
    )
    confirmations = {
        "experimental_uncalibrated": confirm_experimental_uncalibrated,
        "J2_powered_supervised": confirm_j2_powered_supervised,
        "cold_start": confirm_cold_start,
    }
    if any(type(value) is not bool or value is not True for value in confirmations.values()):
        raise ExperimentalRefreshError(
            "all three explicit confirmations are required before an experimental refresh"
        )
    if not isinstance(base_url, str) or not base_url.strip():
        raise ExperimentalRefreshError("base_url must be a non-empty device root URL")

    # This performs the complete deep candidate validation and exact manifest
    # file authorization match before the attempt directory or any network I/O.
    snapshot = _load_candidate_snapshot(candidate_dir, authorized_hash)
    attempt_id = uuid.uuid4().hex
    attempt_created_at_utc = _utc_now()
    claim = _claim_authorization(
        snapshot,
        attempt_id=attempt_id,
        claimed_at_utc=attempt_created_at_utc,
        result_destination=destination,
    )
    directory = _create_result_directory(destination, snapshot.directory)
    lock = {
        "schema_version": SCHEMA_VERSION,
        "kind": LOCK_KIND,
        "attempt_id": attempt_id,
        "created_at_utc": attempt_created_at_utc,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "authorization_consumed_permanently": True,
        "candidate_manifest_file_sha256": snapshot.manifest_file_sha256,
        "candidate_frame_sha256": snapshot.manifest["frame"]["sha256"],
        "algorithm": snapshot.manifest["options"]["value"]["algorithm"],
        "simulation_report_canonical_sha256": snapshot.manifest["simulation"][
            "report_canonical_sha256"
        ],
        "authorization_claim": claim.reference(),
        "exact_action": dict(EXACT_ACTION),
        "confirmations": confirmations,
        "fixed_controller_mappings": [
            _mapping_record(mapping) for mapping in FIXED_CONTROLLER_MAPPINGS
        ],
        "formal": False,
        "hardware_qualified": False,
        "hardware_tested": False,
        "automatic_retry_authorized": False,
    }
    # The immutable no-retry latch exists before perform_refresh can normalize
    # the URL, preflight the device, or POST the frame.
    _atomic_new_file(directory, LOCK_FILENAME, _canonical_json(lock))

    try:
        # Deliberately exactly one invocation. perform_refresh itself performs
        # one /api/frame POST and only read-only polling after that submission.
        network_report = perform_refresh(
            base_url,
            snapshot.frame,
            expected_mappings=FIXED_CONTROLLER_MAPPINGS,
            job_timeout_s=job_timeout_s,
            poll_interval_s=poll_interval_s,
            sleeper=sleeper,
            clock=clock,
        )
        if (
            network_report.get("protocol_verified") is not True
            or network_report.get("hardware_tested") is not False
        ):
            raise ExperimentalRefreshError(
                "refresh protocol report did not retain its fail-closed classification"
            )
        result = {
            **_base_result(
                attempt_id,
                snapshot,
                claim,
                recorded_at_utc=_utc_now(),
            ),
            "outcome": "protocol_verified_manual_observation_required",
            "protocol_verified": True,
            "network_report": network_report,
        }
        _write_result(directory, result)
        return result
    except BaseException as error:
        unknown = {
            **_base_result(
                attempt_id,
                snapshot,
                claim,
                recorded_at_utc=_utc_now(),
            ),
            "outcome": "unknown_do_not_retry",
            "protocol_verified": None,
            "network_report": None,
            "error": {
                "type": type(error).__name__,
                "message": str(error),
            },
        }
        try:
            _write_result(directory, unknown)
        except ExperimentalRefreshError as record_error:
            raise ExperimentalRefreshUnknown(
                "refresh outcome is unknown; ATTEMPT-LOCK remains and RESULT could not be "
                f"recorded ({record_error}); do not retry"
            ) from error
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        raise ExperimentalRefreshUnknown(
            "refresh outcome is unknown_do_not_retry; retain ATTEMPT-LOCK and inspect the device"
        ) from error


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--url", required=True, help="device root URL on the trusted test network")
    parser.add_argument(
        "--authorized-manifest-sha256",
        type=_sha256_argument,
        required=True,
        help="SHA-256 of the exact candidate manifest.json file bytes",
    )
    parser.add_argument("--confirm-experimental-uncalibrated", action="store_true")
    parser.add_argument("--confirm-j2-powered-supervised", action="store_true")
    parser.add_argument("--confirm-cold-start", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        result = run_experimental_refresh(
            args.candidate_dir,
            args.result_dir,
            args.url,
            authorized_manifest_sha256=args.authorized_manifest_sha256,
            confirm_experimental_uncalibrated=args.confirm_experimental_uncalibrated,
            confirm_j2_powered_supervised=args.confirm_j2_powered_supervised,
            confirm_cold_start=args.confirm_cold_start,
        )
    except ExperimentalRefreshUnknown as error:
        print(f"UNKNOWN_DO_NOT_RETRY: {error}", file=sys.stderr)
        return 3
    except ExperimentalRefreshError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(_canonical_json(result).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
