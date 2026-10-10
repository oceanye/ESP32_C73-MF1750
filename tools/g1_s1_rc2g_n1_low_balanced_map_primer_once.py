#!/usr/bin/env python3
"""Run the one RC2G MAP primer for the fixed N1 low-balanced pilot.

This is not a parameterized campaign runner.  Its action name, pilot purpose,
MAP bytes, target job/operation, and workspace-global claim are fixed in code.
No campaign ID, output directory, or caller-selected label can create another
authorization partition.  The claim is atomically and permanently consumed
before any network request.

After claiming, the runner proves an exact RC2G fresh boot (job 0/idle and no
completed report), permits at most one ``POST /api/frame``, and accepts only a
nominal ``map-orient-v1`` job 1/operation 1 with the BUSY-edge trace and low
RST/CS1/CS2 outputs.  BUSY after RST is low remains informational.  This MAP
primer does not itself authorize the later low-balanced pilot refresh.

There is no retry or recovery path.  Every post-claim failure is
``unknown_do_not_retry`` and triggers only best-effort read-only evidence
capture.
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

from tools import g1_s1_rc2g_map_baseline_once as baseline  # noqa: E402
from tools.local_path_safety import (  # noqa: E402
    LocalPathSafetyError,
    require_local_regular_path_syntax,
)
from tools.mf1750_frame_tool import (  # noqa: E402
    DEFAULT_JOB_TIMEOUT_S,
    DEFAULT_POLL_INTERVAL_S,
    http_request,
)


SCHEMA_VERSION = 1
LOCK_FILENAME = "ATTEMPT-LOCK.json"
RESULT_FILENAME = "N1-LOW-BALANCED-MAP-PRIMER-RESULT.json"
LOCK_KIND = "mf1750-g1-s1-rc2g-n1-low-balanced-map-primer-attempt-lock"
RESULT_KIND = "mf1750-g1-s1-rc2g-n1-low-balanced-map-primer-result"
CLAIM_KIND = "mf1750-g1-s1-rc2g-n1-low-balanced-map-primer-claim"
CLAIM_REGISTRY_ID = (
    "workspace-g1-s1-rc2g-n1-low-balanced-map-primer-registry-v1"
)
PILOT_ID = "n1-low-balanced-pilot-v1"
FIXED_ACTION_ID = (
    "rc2g-n1-low-balanced-pilot-cold-boot-map-primer-job1-op1-once-v1"
)
DEFAULT_AUTHORIZATION_REGISTRY = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".g1_s1_rc2g_n1_low_balanced_map_primer_registry"
)

# Re-export the exact protocol constants used by this hard-coded action.  The
# action identity below binds their values, so drift in the shared validator
# changes the frozen identity and fails at import time after the hash is set.
EXPECTED_BUILD_TAG = baseline.EXPECTED_BUILD_TAG
EXPECTED_DRIVER_API = baseline.EXPECTED_DRIVER_API
EXPECTED_REFRESH_SPI_HZ = baseline.EXPECTED_REFRESH_SPI_HZ
FIXED_CONTROLLER_MAPPINGS = baseline.FIXED_CONTROLLER_MAPPINGS
FIXTURE_NAME = baseline.FIXTURE_NAME
EXPECTED_FRAME_SHA256 = baseline.EXPECTED_FRAME_SHA256
EXPECTED_FRAME_FNV1A = baseline.EXPECTED_FRAME_FNV1A
EXPECTED_CS1_DTM_SHA256 = baseline.EXPECTED_CS1_DTM_SHA256
EXPECTED_CS1_DTM_FNV1A = baseline.EXPECTED_CS1_DTM_FNV1A
EXPECTED_CS2_DTM_SHA256 = baseline.EXPECTED_CS2_DTM_SHA256
EXPECTED_CS2_DTM_FNV1A = baseline.EXPECTED_CS2_DTM_FNV1A
EXPECTED_TARGET_JOB_ID = baseline.EXPECTED_TARGET_JOB_ID
EXPECTED_TARGET_OPERATION_ID = baseline.EXPECTED_TARGET_OPERATION_ID
EXPECTED_PANEL_OUTPUTS_LOW = dict(baseline.EXPECTED_PANEL_OUTPUTS_LOW)
NOMINAL_TIMING_RANGES_MS = dict(baseline.NOMINAL_TIMING_RANGES_MS)

REQUIRED_AUTHORIZATION_CONFIRMATION = (
    "AUTHORIZE_ONE_VISIBLE_RC2G_N1_LOW_BALANCED_PILOT_COLD_BOOT_MAP_PRIMER_"
    "JOB1_OP1__NO_RETRY_NO_RECOVERY"
)


class N1LowBalancedMapPrimerError(RuntimeError):
    """The fixed primer was rejected before its permanent claim existed."""


class N1LowBalancedMapPrimerUnknown(N1LowBalancedMapPrimerError):
    """The primer claim exists, so this fixed action must not be attempted again."""


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
        raise N1LowBalancedMapPrimerError(
            f"canonical JSON encoding failed: {error}"
        ) from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


EXACT_ACTION = {
    "action_id": FIXED_ACTION_ID,
    "pilot_id": PILOT_ID,
    "purpose": "cold_boot_map_primer_only",
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
    "follow_up_low_balanced_refresh_authorized": False,
}
ACTION_IDENTITY = {
    "schema_version": SCHEMA_VERSION,
    "kind": "mf1750-g1-s1-rc2g-n1-low-balanced-map-primer-action-identity",
    "action_id": FIXED_ACTION_ID,
    "pilot_binding": {
        "pilot_id": PILOT_ID,
        "phase": "N1",
        "fixed_cell": "low-balanced",
        "primer_only": True,
        "next_expected_prior": {
            "fixture": FIXTURE_NAME,
            "job_id": EXPECTED_TARGET_JOB_ID,
            "operation_id": EXPECTED_TARGET_OPERATION_ID,
            "frame_sha256": EXPECTED_FRAME_SHA256,
            "frame_fnv1a": f"0x{EXPECTED_FRAME_FNV1A:08X}",
            "cs1_dtm_fnv1a": f"0x{EXPECTED_CS1_DTM_FNV1A:08X}",
            "cs2_dtm_fnv1a": f"0x{EXPECTED_CS2_DTM_FNV1A:08X}",
        },
        "follow_up_visible_refresh_authorized": False,
    },
    "claim_scope": {
        "workspace_global_fixed_action": True,
        "partitioned_by_campaign_id": False,
        "partitioned_by_result_directory": False,
        "campaign_id_override_supported": False,
    },
    "firmware": dict(baseline.ACTION_IDENTITY["firmware"]),
    "frame": dict(baseline.ACTION_IDENTITY["frame"]),
    "timing_ranges_ms": dict(baseline.ACTION_IDENTITY["timing_ranges_ms"]),
    "gpio_contract": dict(baseline.ACTION_IDENTITY["gpio_contract"]),
    "exact_action": dict(EXACT_ACTION),
}

ACTION_IDENTITY_SHA256 = "6354b456bc71033fa4ef96ebc8ff972e8d1e45f0f27403977c99bdee4cc20660"
AUTHORIZATION_CONFIRMATION_SHA256 = (
    "403d0c52a6c34ce8dee1226bd5422f8c5df586ea6dc2c09a0b812d14746aeb7d"
)
if _sha256(_canonical_json(ACTION_IDENTITY)) != ACTION_IDENTITY_SHA256:
    raise RuntimeError("frozen N1 low-balanced MAP primer action identity changed")
if (
    _sha256(REQUIRED_AUTHORIZATION_CONFIRMATION.encode("ascii"))
    != AUTHORIZATION_CONFIRMATION_SHA256
):
    raise RuntimeError("frozen N1 low-balanced MAP primer authorization changed")

CLASSIFICATION = {
    "experimental": True,
    "rc2g_instrumentation_baseline": True,
    "n1_low_balanced_pilot_primer": True,
    "primer_only": True,
    "formal": False,
    "hardware_qualified": False,
    "hardware_tested": False,
    "algorithm_qualification": False,
}


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _prepare_result_destination(result_dir: Path) -> Path:
    try:
        require_local_regular_path_syntax(
            result_dir, label="N1 low-balanced MAP primer result directory"
        )
    except LocalPathSafetyError as error:
        raise N1LowBalancedMapPrimerError(str(error)) from error
    if os.path.lexists(result_dir):
        raise N1LowBalancedMapPrimerError(
            "result directory already exists; refusing overwrite or rerun"
        )
    try:
        parent = result_dir.parent.resolve(strict=True)
    except OSError as error:
        raise N1LowBalancedMapPrimerError(
            f"result parent does not exist: {error}"
        ) from error
    if not parent.is_dir():
        raise N1LowBalancedMapPrimerError("result parent must be a directory")
    destination = parent / result_dir.name
    if os.path.lexists(destination):
        raise N1LowBalancedMapPrimerError(
            "result directory already exists; refusing overwrite or rerun"
        )
    return destination


def _authorization_registry() -> Path:
    path = DEFAULT_AUTHORIZATION_REGISTRY
    try:
        require_local_regular_path_syntax(
            path, label="N1 low-balanced MAP primer authorization registry"
        )
        if os.path.lexists(path) and path.is_symlink():
            raise N1LowBalancedMapPrimerError("primer registry must not be a symlink")
        parent = path.parent.resolve(strict=True)
        workspace = REPO_ROOT.resolve(strict=True)
        if not parent.is_dir() or not _is_within(parent, workspace):
            raise N1LowBalancedMapPrimerError(
                "primer registry parent must be in the workspace"
            )
        path.mkdir(exist_ok=True)
        registry = path.resolve(strict=True)
    except N1LowBalancedMapPrimerError:
        raise
    except (LocalPathSafetyError, OSError) as error:
        raise N1LowBalancedMapPrimerError(
            f"could not create N1 low-balanced primer registry: {error}"
        ) from error
    if path.is_symlink() or not registry.is_dir() or not _is_within(registry, workspace):
        raise N1LowBalancedMapPrimerError("primer registry escaped the workspace")
    return registry


def _claim_action(
    snapshot: baseline._FixtureSnapshot,
    *,
    attempt_id: str,
    claimed_at_utc: str,
    result_destination: Path,
    confirmations: Mapping[str, Any],
) -> _Claim:
    registry = _authorization_registry()
    if _is_within(result_destination, registry):
        raise N1LowBalancedMapPrimerError(
            "result directory must not be inside the primer registry"
        )
    record = {
        "schema_version": SCHEMA_VERSION,
        "kind": CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "action_id": FIXED_ACTION_ID,
        "pilot_id": PILOT_ID,
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
        "campaign_id_override_supported": False,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "follow_up_low_balanced_refresh_authorized": False,
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
            raise N1LowBalancedMapPrimerUnknown(
                "primer claim exists after cleanup failure; do not retry"
            ) from error
        raise N1LowBalancedMapPrimerError(
            "this fixed N1 low-balanced MAP primer was already permanently consumed; do not retry"
        ) from error
    except BaseException as error:
        if linked:
            raise N1LowBalancedMapPrimerUnknown(
                "primer claim exists after claim processing failure; do not retry"
            ) from error
        if not isinstance(error, OSError):
            raise
        raise N1LowBalancedMapPrimerError(
            f"could not atomically claim N1 low-balanced MAP primer: {error}"
        ) from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except BaseException:
            pass
    return claim


def _create_result_directory(destination: Path, claim: _Claim) -> Path:
    if _is_within(destination, claim.registry):
        raise N1LowBalancedMapPrimerError("result directory overlaps the claim registry")
    try:
        destination.mkdir()
    except FileExistsError as error:
        raise N1LowBalancedMapPrimerError(
            "result directory appeared; refusing overwrite"
        ) from error
    except OSError as error:
        raise N1LowBalancedMapPrimerError(
            f"could not create result directory: {error}"
        ) from error
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
        raise N1LowBalancedMapPrimerError(
            f"{name} already exists; refusing overwrite"
        ) from error
    except OSError as error:
        if linked:
            raise N1LowBalancedMapPrimerError(
                f"{name} committed but staging cleanup failed"
            ) from error
        raise N1LowBalancedMapPrimerError(
            f"could not atomically write {name}: {error}"
        ) from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except BaseException:
            pass


def _base_result(
    *, attempt_id: str, claim: _Claim, recorded_at_utc: str
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": RESULT_KIND,
        "attempt_id": attempt_id,
        "recorded_at_utc": recorded_at_utc,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "action_id": FIXED_ACTION_ID,
        "pilot_id": PILOT_ID,
        "action_identity_sha256": ACTION_IDENTITY_SHA256,
        "authorization_confirmation_sha256": AUTHORIZATION_CONFIRMATION_SHA256,
        "authorization_claim": claim.reference(),
        "frame": dict(ACTION_IDENTITY["frame"]),
        "exact_action": dict(EXACT_ACTION),
        "authorization_consumed_permanently": True,
        "campaign_id_override_supported": False,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "follow_up_low_balanced_refresh_authorized": False,
        "classification": dict(CLASSIFICATION),
        "formal": False,
        "hardware_qualified": False,
        "hardware_tested": False,
        "algorithm_qualification": False,
        "manual_observation_required": [
            "screen_matches_frozen_map_orient_v1_preview",
            "left_right_orientation_labels_center_seam_and_all_six_codes",
            "no_retained_old_regions",
            "power_supply_3_3v_cv_current_and_temperature",
            "post_run_power_state",
        ],
        "manual_observation_completed": False,
    }


def run_n1_low_balanced_map_primer_once(
    result_dir: Path,
    base_url: str,
    *,
    authorization_confirmation: str,
    confirm_rc2g_flashed_fresh_boot: bool = False,
    confirm_j2_powered_supervised: bool = False,
    confirm_supply_and_temperature_normal: bool = False,
    confirm_single_visible_primer_refresh: bool = False,
    job_timeout_s: float = DEFAULT_JOB_TIMEOUT_S,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Consume and execute the fixed N1 low-balanced pilot MAP primer."""

    if not isinstance(result_dir, Path):
        raise N1LowBalancedMapPrimerError("result_dir must be pathlib.Path")
    destination = _prepare_result_destination(result_dir)
    if authorization_confirmation != REQUIRED_AUTHORIZATION_CONFIRMATION:
        raise N1LowBalancedMapPrimerError(
            "exact N1 low-balanced MAP primer authorization string is required"
        )
    boolean_confirmations = {
        "rc2g_flashed_fresh_boot": confirm_rc2g_flashed_fresh_boot,
        "J2_powered_supervised": confirm_j2_powered_supervised,
        "supply_and_temperature_normal": confirm_supply_and_temperature_normal,
        "single_visible_primer_refresh": confirm_single_visible_primer_refresh,
    }
    if any(
        type(value) is not bool or value is not True
        for value in boolean_confirmations.values()
    ):
        raise N1LowBalancedMapPrimerError(
            "all four explicit flash/boot, supervised-power, normal-supply, and single-primer confirmations are required"
        )
    if not isinstance(base_url, str) or not base_url.strip():
        raise N1LowBalancedMapPrimerError(
            "base_url must be a non-empty device root URL"
        )

    try:
        snapshot = baseline._validate_fixture_snapshot()
    except baseline.Rc2gMapBaselineError as error:
        raise N1LowBalancedMapPrimerError(
            f"shared frozen MAP validation failed: {error}"
        ) from error
    attempt_id = uuid.uuid4().hex
    created_at_utc = _utc_now()
    confirmations = {
        "authorization_confirmation": authorization_confirmation,
        **boolean_confirmations,
    }
    claim = _claim_action(
        snapshot,
        attempt_id=attempt_id,
        claimed_at_utc=created_at_utc,
        result_destination=destination,
        confirmations=confirmations,
    )

    directory: Optional[Path] = None
    requester = baseline._AuditedRequester(http_request)
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
            "campaign_id_override_supported": False,
            "authorization_consumed_permanently": True,
            "automatic_retry_authorized": False,
            "automatic_recovery_authorized": False,
            "follow_up_low_balanced_refresh_authorized": False,
            "formal": False,
            "hardware_qualified": False,
            "hardware_tested": False,
        }
        _atomic_new_file(directory, LOCK_FILENAME, _canonical_json(lock))

        fresh_boot = baseline._validate_fresh_boot_state(base_url, requester)
        network_report = baseline._perform_refresh_once(
            base_url,
            snapshot.frame,
            requester,
            job_timeout_s=job_timeout_s,
            poll_interval_s=poll_interval_s,
            sleeper=sleeper,
            clock=clock,
        )
        if requester.post_issued_count != 1:
            raise N1LowBalancedMapPrimerError(
                "N1 low-balanced primer did not issue exactly one POST /api/frame"
            )
        raw_job = baseline._get_json_object(
            base_url, "/api/job", label="post-primer MAP job", requester=requester
        )
        raw_diagnostic = baseline._get_json_object(
            base_url,
            "/api/diagnostic/report",
            label="post-primer MAP diagnostic",
            requester=requester,
        )
        post_gpio_raw = baseline._get_json_object(
            base_url,
            "/api/diagnostic/status",
            label="post-primer MAP GPIO",
            requester=requester,
        )
        completed_evidence = baseline._validate_completed_map_evidence(
            network_report,
            raw_job,
            raw_diagnostic,
            post_gpio_raw,
            snapshot.frame,
        )
        result = {
            **_base_result(
                attempt_id=attempt_id, claim=claim, recorded_at_utc=_utc_now()
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
            best_effort = baseline._collect_best_effort_evidence(base_url, requester)
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
        raise N1LowBalancedMapPrimerUnknown(
            "N1 low-balanced MAP primer outcome is unknown_do_not_retry; the fixed global claim is permanent"
            + detail
        ) from error


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument(
        "--url", required=True, help="device root URL on the trusted test network"
    )
    parser.add_argument(
        "--confirm", required=True, help="exact fixed-primer authorization string"
    )
    parser.add_argument("--confirm-rc2g-flashed-fresh-boot", action="store_true")
    parser.add_argument("--confirm-j2-powered-supervised", action="store_true")
    parser.add_argument("--confirm-supply-and-temperature-normal", action="store_true")
    parser.add_argument("--confirm-single-visible-primer-refresh", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        result = run_n1_low_balanced_map_primer_once(
            args.result_dir,
            args.url,
            authorization_confirmation=args.confirm,
            confirm_rc2g_flashed_fresh_boot=args.confirm_rc2g_flashed_fresh_boot,
            confirm_j2_powered_supervised=args.confirm_j2_powered_supervised,
            confirm_supply_and_temperature_normal=args.confirm_supply_and_temperature_normal,
            confirm_single_visible_primer_refresh=(
                args.confirm_single_visible_primer_refresh
            ),
        )
    except N1LowBalancedMapPrimerUnknown as error:
        print(f"UNKNOWN_DO_NOT_RETRY: {error}", file=sys.stderr)
        return 3
    except N1LowBalancedMapPrimerError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(_canonical_json(result).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
