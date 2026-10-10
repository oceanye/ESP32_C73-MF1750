#!/usr/bin/env python3
"""Execute and adjudicate one production-bound N7 SPI sweep action.

Only the physical campaign produced by :mod:`mf1750_n7_physical_campaign`
is accepted.  Every run replays the physical materialization and the complete
authenticated production profile from actual local bytes before it can create
the workspace-global claim or make a device request.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable, Mapping, Optional, Sequence
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.visible_refresh_campaign import (  # noqa: E402
    CLAIM_REGISTRY_ID,
    CLAIM_REGISTRY_RELATIVE_PATH,
    CampaignContractError,
    ResultState,
    build_result_record,
    canonical_json_bytes,
    result_file_sha256,
    validate_result_record,
)
from host.visible_refresh_campaign.production_profile import (  # noqa: E402
    ArtifactSnapshot,
    ProductionProfileError,
    ValidatedProductionProfile,
    load_validated_production_profile,
    read_local_regular_file,
)
from tools import mf1750_frame_tool as frame_tool  # noqa: E402
from tools import mf1750_n7_physical_campaign as physical  # noqa: E402
from tools import mf1750_n7_spi_sweep_campaign as frozen  # noqa: E402
from tools import mf1750_n7_spi_sweep_once as legacy  # noqa: E402
from tools import mf1750_refresh_analyzer as analyzer  # noqa: E402


SCHEMA_VERSION = 1
RUNNER_KIND = "mf1750-n7-physical-production-once"
CLAIM_KIND = "mf1750-n7-physical-consumed-claim"
LOCK_KIND = "mf1750-n7-physical-attempt-lock"
LIVE_KIND = "mf1750-n7-physical-live-evidence"
FINAL_KIND = "mf1750-n7-physical-finalized-evidence"
MAX_LIVE_EVALUATION_AGE_SECONDS = 300.0
MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_EVIDENCE_BYTES = 64 * 1024 * 1024
DEFAULT_CLAIM_REGISTRY = REPO_ROOT / Path(CLAIM_REGISTRY_RELATIVE_PATH)

LOCK_FILENAME = "ATTEMPT-LOCK.json"
LIVE_FILENAME = "N7-PHYSICAL-LIVE.json"
FINAL_FILENAME = "N7-PHYSICAL-FINAL.json"
P0_RESULT_FILENAME = "P0-ACTION-RESULT.json"
SERIAL_FILENAME = "N7-SERIAL-CAPTURE.log"
SCOPE_FILENAME = "N7-SCOPE-CAPTURE.bin"
TIMING_FILENAME = "N7-TIMING-CAPTURE.bin"
SOURCE_DIRECTORY = "N7-SOURCE"
PHYSICAL_DIRECTORY = "N7-PHYSICAL"
PANEL_FILENAME = "PHYSICAL-PANEL.json"
BINDING_REVIEW_FILENAME = "PANEL-BINDING-REVIEW.bin"
PROFILE_FILENAME = "PRODUCTION-PROFILE.json"
AUTHORITY_FILENAME = "LIMIT-AUTHORITY.json"
USAGE_FILENAME = "USAGE-EVIDENCE.json"
PROFILE_REVIEW_FILENAME = "PROFILE-REVIEW.json"
PRIOR_LIVE_FILENAME = "PRIOR-N7-PHYSICAL-LIVE.json"
PRIOR_FINAL_FILENAME = "PRIOR-N7-PHYSICAL-FINAL.json"
PRIOR_RESULT_FILENAME = "PRIOR-P0-ACTION-RESULT.json"

ACTION_AUTHORIZATION_PREFIX = "AUTHORIZE_ONE_VISIBLE_N7_PHYSICAL"
PANEL_CONFIRMATION_PREFIX = "CONFIRM_N7_PHYSICAL_PANEL"
PROFILE_CONFIRMATION_PREFIX = "CONFIRM_N7_APPROVED_PRODUCTION_PROFILE"
ACTION_AUTHORIZATION_SUFFIX = "__NO_RETRY_NO_RECOVERY"

_RFC3339_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z"
)


class N7PhysicalOnceError(RuntimeError):
    """Rejected before claim, or invalid stored physical evidence."""


class N7PhysicalOnceUnknown(N7PhysicalOnceError):
    """The physical action claim exists and retry is permanently forbidden."""


@dataclass(frozen=True)
class _Context:
    manifest: Mapping[str, Any]
    campaign: Mapping[str, Any]
    action: Mapping[str, Any]
    session: Mapping[str, Any]
    frequency_hz: int
    action_key: str
    production: ValidatedProductionProfile
    snapshots: Mapping[str, ArtifactSnapshot]


@dataclass(frozen=True)
class _Prior:
    directory: Path
    live: Mapping[str, Any]
    final: Mapping[str, Any]
    result: Mapping[str, Any]
    final_file_sha256: str
    result_file_sha256: str


@dataclass(frozen=True)
class _Claim:
    path: Path
    record: Mapping[str, Any]
    payload: bytes

    def reference(self) -> dict[str, Any]:
        return {
            "registry_id": CLAIM_REGISTRY_ID,
            "filename": self.path.name,
            "file_sha256": _sha256(self.payload),
            "attempt_id": self.record["attempt_id"],
            "action_identity_sha256": self.record["action_identity_sha256"],
            "state": self.record["state"],
        }


def _sha256(value: bytes | Mapping[str, Any]) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise N7PhysicalOnceError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _parse_timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or _RFC3339_RE.fullmatch(value) is None:
        raise N7PhysicalOnceError(f"{label} must be timezone-aware RFC3339")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise N7PhysicalOnceError(f"{label} is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise N7PhysicalOnceError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _number(value: Any, *, label: str, minimum: float = 0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise N7PhysicalOnceError(f"{label} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < minimum:
        raise N7PhysicalOnceError(f"{label} must be finite and at least {minimum}")
    return normalized


def _read(path: Path, *, label: str, maximum: int = MAX_EVIDENCE_BYTES) -> ArtifactSnapshot:
    try:
        return read_local_regular_file(path, label=label, maximum_bytes=maximum)
    except ProductionProfileError as error:
        raise N7PhysicalOnceError(str(error)) from error


def _json(snapshot: ArtifactSnapshot, *, label: str) -> Mapping[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise N7PhysicalOnceError(f"{label} contains duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            snapshot.payload.decode("utf-8"),
            object_pairs_hook=unique,
            parse_constant=lambda token: (_ for _ in ()).throw(
                N7PhysicalOnceError(f"{label} contains forbidden number {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N7PhysicalOnceError(f"{label} is invalid UTF-8 JSON: {error}") from error
    if not isinstance(value, Mapping) or snapshot.payload != canonical_json_bytes(value):
        raise N7PhysicalOnceError(f"{label} must be a canonical JSON object")
    return value


def _action_allowlist(campaign: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "action_id": action["identity"]["action_id"],
            "action_identity_sha256": action["action_identity_sha256"],
            "method": action["identity"]["request"]["method"],
            "endpoint": action["identity"]["request"]["endpoint"],
            "frame_sha256": action["identity"]["frame"]["sha256"],
            "maximum_uses": 1,
        }
        for action in campaign["actions"]
    ]


def _input_snapshots(
    *,
    physical_bundle_dir: Path,
    source_campaign_directory: Path,
    panel_file: Path,
    panel_binding_review_file: Path,
) -> dict[str, ArtifactSnapshot]:
    return {
        f"{SOURCE_DIRECTORY}/campaign.json": _read(
            source_campaign_directory / "campaign.json", label="N7 source campaign"
        ),
        f"{SOURCE_DIRECTORY}/firmware.bin": _read(
            source_campaign_directory / "firmware.bin", label="N7 firmware binary"
        ),
        f"{SOURCE_DIRECTORY}/SHA256SUMS.txt": _read(
            source_campaign_directory / "SHA256SUMS.txt", label="N7 source checksums"
        ),
        f"{PHYSICAL_DIRECTORY}/{physical.PHYSICAL_CAMPAIGN_FILENAME}": _read(
            physical_bundle_dir / physical.PHYSICAL_CAMPAIGN_FILENAME,
            label="N7 physical campaign",
        ),
        f"{PHYSICAL_DIRECTORY}/{physical.MANIFEST_FILENAME}": _read(
            physical_bundle_dir / physical.MANIFEST_FILENAME,
            label="N7 physical manifest",
        ),
        PANEL_FILENAME: _read(panel_file, label="physical panel identity"),
        BINDING_REVIEW_FILENAME: _read(
            panel_binding_review_file, label="N7 panel binding review"
        ),
    }


def _load_context(
    frequency_hz: int,
    *,
    physical_bundle_dir: Path,
    source_campaign_directory: Path,
    panel_file: Path,
    panel_binding_review_file: Path,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
    profile_file: Path,
    limit_authority_file: Path,
    usage_evidence_file: Path,
    profile_review_artifact_file: Path,
    reviewer_key_file: Path,
    evaluated_at: str,
) -> _Context:
    if type(frequency_hz) is not int or frequency_hz not in frozen.FREQUENCIES:
        raise N7PhysicalOnceError("frequency must be one of 1/2/4/8/10 MHz")
    try:
        manifest = physical.read_physical_bundle(
            physical_bundle_dir,
            source_campaign_directory,
            panel_file,
            panel_binding_review_file,
            minimum_interval_seconds=minimum_interval_seconds,
            planned_cooldown_seconds=planned_cooldown_seconds,
        )
    except physical.N7PhysicalCampaignError as error:
        raise N7PhysicalOnceError(f"N7 physical materialization failed: {error}") from error
    campaign = manifest["physical_campaign"]
    campaign_file = physical_bundle_dir / physical.PHYSICAL_CAMPAIGN_FILENAME
    firmware_file = source_campaign_directory / "firmware.bin"
    try:
        production = load_validated_production_profile(
            profile_file=profile_file,
            campaign_file=campaign_file,
            firmware_binary_file=firmware_file,
            supplier_limits_file=limit_authority_file,
            usage_evidence_file=usage_evidence_file,
            review_artifact_file=profile_review_artifact_file,
            reviewer_key_file=reviewer_key_file,
            evaluated_at=evaluated_at,
        )
    except ProductionProfileError as error:
        raise N7PhysicalOnceError(f"N7 production profile failed: {error}") from error
    if (
        production.report["approved"] is not True
        or production.report["production_ready"] is not True
        or production.inputs.campaign != campaign
        or production.profile["action_allowlist"] != _action_allowlist(campaign)
        or production.review_artifact_file is None
        or production.reviewer_key_id is None
    ):
        raise N7PhysicalOnceError("N7 production profile is not ready and exact")
    action_key = f"{frequency_hz // 1_000_000}mhz"
    action_sha = manifest["fixed_actions"].get(action_key)
    actions = [
        item for item in campaign["actions"] if item["action_identity_sha256"] == action_sha
    ]
    if len(actions) != 1:
        raise N7PhysicalOnceError("selected N7 physical action is not unique")
    action = actions[0]
    sessions = [
        item
        for item in campaign["sessions"]
        if action_sha in item["action_identity_sha256s"]
    ]
    if len(sessions) != 1 or sessions[0]["power_mode"] != "panel_cold_driver_only":
        raise N7PhysicalOnceError("selected N7 action lost driver-only cold semantics")
    snapshots = _input_snapshots(
        physical_bundle_dir=physical_bundle_dir,
        source_campaign_directory=source_campaign_directory,
        panel_file=panel_file,
        panel_binding_review_file=panel_binding_review_file,
    )
    snapshots.update(
        {
            PROFILE_FILENAME: production.profile_file,
            AUTHORITY_FILENAME: production.inputs.limit_authority_file,
            USAGE_FILENAME: production.inputs.usage_evidence_file,
            PROFILE_REVIEW_FILENAME: production.review_artifact_file,
        }
    )
    return _Context(
        manifest=manifest,
        campaign=campaign,
        action=action,
        session=sessions[0],
        frequency_hz=frequency_hz,
        action_key=action_key,
        production=production,
        snapshots=snapshots,
    )


def required_action_authorization(frequency_hz: int, action_sha256: str) -> str:
    if type(frequency_hz) is not int or frequency_hz not in frozen.FREQUENCIES:
        raise N7PhysicalOnceError("authorization frequency is invalid")
    if not isinstance(action_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", action_sha256) is None:
        raise N7PhysicalOnceError("authorization action identity is invalid")
    return (
        f"{ACTION_AUTHORIZATION_PREFIX}_{frequency_hz // 1_000_000}MHZ"
        f"__ACTION_{action_sha256.upper()}{ACTION_AUTHORIZATION_SUFFIX}"
    )


def required_panel_confirmation(context: _Context) -> str:
    return (
        f"{PANEL_CONFIRMATION_PREFIX}__SERIAL_{context.campaign['panel']['serial']}"
        f"__BUILD_TAG_{context.campaign['firmware']['build_tag']}"
        f"__MATERIALIZATION_{context.manifest['integrity']['canonical_sha256'].upper()}"
    )


def required_profile_confirmation(context: _Context) -> str:
    review = context.production.review_artifact_file
    key_id = context.production.reviewer_key_id
    if review is None or key_id is None:
        raise N7PhysicalOnceError("N7 production review snapshots are incomplete")
    return (
        f"{PROFILE_CONFIRMATION_PREFIX}"
        f"__PROFILE_{context.production.profile_file.sha256.upper()}"
        f"__REVIEW_{review.sha256.upper()}"
        f"__KEY_{key_id.upper()}"
        f"__USAGE_{context.production.inputs.usage_evidence_file.sha256.upper()}"
        f"__AUTHORITY_{context.production.inputs.limit_authority_file.sha256.upper()}"
    )


def _schedule_decision(
    context: _Context,
    *,
    evaluated_at: str,
    panel_power_off_seconds: Optional[float],
) -> dict[str, Any]:
    now = _parse_timestamp(evaluated_at, label="schedule evaluated_at")
    identity = context.action["identity"]
    profile = context.production.profile
    materialized_interval = float(
        identity["schedule"]["minimum_interval_since_prior_seconds"]
    )
    authority_interval = float(profile["limits"]["minimum_interval_seconds"])
    materialized_cooldown = float(context.session["planned_cooldown_seconds"])
    authority_cooldown = float(profile["limits"]["minimum_cooldown_seconds"])
    minimum_driver_off = float(context.session["minimum_panel_power_off_seconds"])
    effective_interval = max(materialized_interval, authority_interval)
    effective_cooldown = max(
        materialized_cooldown, authority_cooldown, minimum_driver_off
    )
    last_value = profile["usage"]["last_visible_refresh_completed_at"]
    last = (
        None
        if last_value is None
        else _parse_timestamp(last_value, label="usage last visible refresh")
    )
    elapsed = None if last is None else (now - last).total_seconds()
    dependent = identity["prior"] is not None
    blockers: list[str] = []
    if last is not None and elapsed is not None:
        if dependent and elapsed < effective_interval:
            blockers.append("effective_action_interval_not_elapsed")
        if elapsed < effective_cooldown:
            blockers.append("effective_session_cooldown_not_elapsed")
    if dependent and last is None:
        blockers.append("dependent_action_usage_has_no_last_visible_refresh")
    if panel_power_off_seconds is not None:
        observed_off = _number(
            panel_power_off_seconds, label="panel_power_off_seconds"
        )
        if observed_off < effective_cooldown:
            blockers.append("measured_driver_off_interval_too_short")
    else:
        observed_off = None
    return {
        "evaluated_at": evaluated_at,
        "last_visible_refresh_completed_at": last_value,
        "elapsed_since_last_visible_refresh_seconds": elapsed,
        "dependent_action": dependent,
        "materialized_minimum_interval_seconds": materialized_interval,
        "authority_minimum_interval_seconds": authority_interval,
        "effective_minimum_interval_seconds": effective_interval,
        "materialized_planned_cooldown_seconds": materialized_cooldown,
        "authority_minimum_cooldown_seconds": authority_cooldown,
        "minimum_driver_off_seconds": minimum_driver_off,
        "effective_minimum_cooldown_seconds": effective_cooldown,
        "measured_panel_power_off_seconds": observed_off,
        "ready": not blockers and observed_off is not None,
        "blockers": blockers + (
            ["measured_driver_off_interval_required"] if observed_off is None else []
        ),
    }


def describe_physical_action(
    frequency_hz: int,
    *,
    physical_bundle_dir: Path,
    source_campaign_directory: Path,
    panel_file: Path,
    panel_binding_review_file: Path,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
    profile_file: Path,
    limit_authority_file: Path,
    usage_evidence_file: Path,
    profile_review_artifact_file: Path,
    reviewer_key_file: Path,
    predecessor_result_dir: Optional[Path] = None,
    now: Callable[[], datetime] = _now_utc,
) -> dict[str, Any]:
    evaluated_at = _timestamp(now())
    context = _load_context(
        frequency_hz,
        physical_bundle_dir=physical_bundle_dir,
        source_campaign_directory=source_campaign_directory,
        panel_file=panel_file,
        panel_binding_review_file=panel_binding_review_file,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
        profile_file=profile_file,
        limit_authority_file=limit_authority_file,
        usage_evidence_file=usage_evidence_file,
        profile_review_artifact_file=profile_review_artifact_file,
        reviewer_key_file=reviewer_key_file,
        evaluated_at=evaluated_at,
    )
    prior = _load_prior(
        predecessor_result_dir, context, reviewer_key_file=reviewer_key_file
    )
    authorization = required_action_authorization(
        frequency_hz, str(context.action["action_identity_sha256"])
    )
    panel_confirmation = required_panel_confirmation(context)
    profile_confirmation = required_profile_confirmation(context)
    schedule = _schedule_decision(
        context, evaluated_at=evaluated_at, panel_power_off_seconds=None
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-n7-physical-action-description",
        "frequency_hz": frequency_hz,
        "endpoint": context.action["identity"]["request"]["endpoint"],
        "action_identity_sha256": context.action["action_identity_sha256"],
        "panel": dict(context.campaign["panel"]),
        "firmware": dict(context.campaign["firmware"]),
        "materialization_canonical_sha256": context.manifest["integrity"][
            "canonical_sha256"
        ],
        "profile_validation": dict(context.production.report),
        "runtime_schedule_without_measured_off_interval": schedule,
        "predecessor_validated": (
            prior is not None or frequency_hz == frozen.FREQUENCIES[0]
        ),
        "required_action_authorization": authorization,
        "required_panel_confirmation": panel_confirmation,
        "required_profile_confirmation": profile_confirmation,
        "maximum_live_evaluation_age_seconds": MAX_LIVE_EVALUATION_AGE_SECONDS,
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "hardware_execution_authorized": False,
        "qualification_state": "NOT_QUALIFIED",
    }


def _safe_result_directory(path: Path, *, must_exist: bool) -> Path:
    if not isinstance(path, Path) or path.name in {"", ".", ".."}:
        raise N7PhysicalOnceError("result directory must be a concrete pathlib.Path")
    if must_exist:
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise N7PhysicalOnceError(f"result directory is unavailable: {error}") from error
        if path.is_symlink() or not resolved.is_dir():
            raise N7PhysicalOnceError("result directory must be a real directory")
        return resolved
    if os.path.lexists(path):
        raise N7PhysicalOnceError("result directory already exists; refusing replay")
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as error:
        raise N7PhysicalOnceError(f"result parent is unavailable: {error}") from error
    if not parent.is_dir() or path.parent.is_symlink():
        raise N7PhysicalOnceError("result parent must be a real directory")
    return parent / path.name


def _write_new(path: Path, payload: bytes, *, label: str) -> str:
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise N7PhysicalOnceError(f"{label} already exists; refusing overwrite") from error
    except OSError as error:
        raise N7PhysicalOnceError(f"could not write {label}: {error}") from error
    return _sha256(payload)


def _write_json(path: Path, value: Mapping[str, Any], *, label: str) -> str:
    return _write_new(path, canonical_json_bytes(value), label=label)


def _copy_snapshots(directory: Path, context: _Context) -> None:
    (directory / SOURCE_DIRECTORY).mkdir()
    (directory / PHYSICAL_DIRECTORY).mkdir()
    for relative, snapshot in context.snapshots.items():
        path = directory / Path(relative)
        if path.parent not in {
            directory,
            directory / SOURCE_DIRECTORY,
            directory / PHYSICAL_DIRECTORY,
        }:
            raise N7PhysicalOnceError("snapshot destination escaped fixed result layout")
        _write_new(path, snapshot.payload, label=f"snapshot {relative}")


def _snapshot_records(context: _Context) -> dict[str, dict[str, Any]]:
    return {
        name: {
            "bytes": len(snapshot.payload),
            "sha256": snapshot.sha256,
        }
        for name, snapshot in sorted(context.snapshots.items())
    }


def _claim_registry() -> Path:
    registry = DEFAULT_CLAIM_REGISTRY
    if registry.is_symlink():
        raise N7PhysicalOnceError("N7 physical claim registry must not be a symlink")
    try:
        registry.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise N7PhysicalOnceError(f"cannot create N7 physical claim registry: {error}") from error
    if not registry.is_dir():
        raise N7PhysicalOnceError("N7 physical claim registry is not a directory")
    return registry


def _claim_action(
    context: _Context,
    *,
    attempt_id: str,
    claimed_at: str,
    schedule: Mapping[str, Any],
    start_temperature_c: float,
    confirmations: Mapping[str, bool],
    authorization_confirmation: str,
    panel_confirmation: str,
    profile_confirmation: str,
    prior: Optional[_Prior],
) -> _Claim:
    action_sha = str(context.action["action_identity_sha256"])
    record = {
        "schema_version": SCHEMA_VERSION,
        "kind": CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "attempt_id": attempt_id,
        "claimed_at": claimed_at,
        "action_identity_sha256": action_sha,
        "frequency_hz": context.frequency_hz,
        "endpoint": context.action["identity"]["request"]["endpoint"],
        "materialization_canonical_sha256": context.manifest["integrity"][
            "canonical_sha256"
        ],
        "campaign_canonical_sha256": context.campaign["integrity"][
            "canonical_sha256"
        ],
        "profile_canonical_sha256": context.production.profile["integrity"][
            "canonical_sha256"
        ],
        "profile_file_sha256": context.production.profile_file.sha256,
        "reviewer_key_id": context.production.reviewer_key_id,
        "authorization_confirmation_sha256": _sha256(
            authorization_confirmation.encode("utf-8")
        ),
        "panel_confirmation_sha256": _sha256(panel_confirmation.encode("utf-8")),
        "profile_confirmation_sha256": _sha256(
            profile_confirmation.encode("utf-8")
        ),
        "runtime_schedule_decision": deepcopy(schedule),
        "predecessor_final_file_sha256": (
            prior.final_file_sha256 if prior is not None else None
        ),
        "predecessor_result_file_sha256": (
            prior.result_file_sha256 if prior is not None else None
        ),
        "start_temperature_c": start_temperature_c,
        "confirmations": dict(confirmations),
        "state": "authorization_permanently_consumed_do_not_rerun",
        "maximum_visible_posts": 1,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "qualification_state": "NOT_QUALIFIED",
    }
    payload = canonical_json_bytes(record)
    path = _claim_registry() / f"{action_sha}.json"
    try:
        _write_new(path, payload, label="N7 physical action claim")
    except N7PhysicalOnceError as error:
        if path.exists():
            raise N7PhysicalOnceUnknown(
                "this exact N7 physical action claim is already permanently consumed"
            ) from error
        raise
    return _Claim(path=path, record=record, payload=payload)


def _validate_claim_reference(
    reference: Any, context: _Context, *, expected_record: Optional[Mapping[str, Any]] = None
) -> Mapping[str, Any]:
    if not isinstance(reference, Mapping):
        raise N7PhysicalOnceError("N7 physical claim reference is missing")
    action_sha = str(context.action["action_identity_sha256"])
    expected_path = DEFAULT_CLAIM_REGISTRY / f"{action_sha}.json"
    snapshot = _read(expected_path, label="workspace-global N7 physical claim")
    claim = _json(snapshot, label="workspace-global N7 physical claim")
    if (
        reference
        != {
            "registry_id": CLAIM_REGISTRY_ID,
            "filename": expected_path.name,
            "file_sha256": snapshot.sha256,
            "attempt_id": claim.get("attempt_id"),
            "action_identity_sha256": action_sha,
            "state": "authorization_permanently_consumed_do_not_rerun",
        }
        or claim.get("kind") != CLAIM_KIND
        or claim.get("action_identity_sha256") != action_sha
        or claim.get("maximum_visible_posts") != 1
        or claim.get("automatic_retry_authorized") is not False
        or claim.get("automatic_recovery_authorized") is not False
    ):
        raise N7PhysicalOnceError("N7 physical claim reference/record changed")
    if expected_record is not None and claim != expected_record:
        raise N7PhysicalOnceError("stored N7 physical claim differs from expected control record")
    return claim


def _expected_confirmation_keys(frequency_hz: int) -> frozenset[str]:
    common = {
        "physical_panel_identity_verified",
        "j2_driver_power_off_for_measured_interval",
        "supply_cv_current_temperature_normal",
        "physical_cutoff_available",
        "scope_capture_armed",
        "single_visible_action",
    }
    if frequency_hz == frozen.FREQUENCIES[0]:
        common.add("n7_firmware_flashed_with_j2_off_and_fresh_boot")
    else:
        common.update(
            {
                "esp32_not_restarted_since_previous_frequency",
                "previous_screen_fidelity_pass",
                "no_other_visible_refresh_since_previous_frequency",
            }
        )
    return frozenset(common)


def _validate_confirmations(
    frequency_hz: int, confirmations: Mapping[str, bool]
) -> dict[str, bool]:
    expected = _expected_confirmation_keys(frequency_hz)
    if (
        not isinstance(confirmations, Mapping)
        or set(confirmations) != expected
        or any(type(value) is not bool or value is not True for value in confirmations.values())
    ):
        raise N7PhysicalOnceError(
            "all and only action-specific N7 physical confirmations must be true"
        )
    return dict(confirmations)


def _load_prior(
    predecessor_result_dir: Optional[Path],
    context: _Context,
    *,
    reviewer_key_file: Path,
) -> Optional[_Prior]:
    index = frozen.FREQUENCIES.index(context.frequency_hz)
    if index == 0:
        if predecessor_result_dir is not None:
            raise N7PhysicalOnceError("1 MHz physical action must not provide a predecessor")
        return None
    if predecessor_result_dir is None:
        raise N7PhysicalOnceError("higher N7 frequencies require the previous finalized PASS")
    stored = _validate_result_directory(
        predecessor_result_dir,
        reviewer_key_file=reviewer_key_file,
        require_finalized=True,
    )
    expected_frequency = frozen.FREQUENCIES[index - 1]
    expected_prior_sha = context.action["identity"]["prior"][
        "action_identity_sha256"
    ]
    if (
        stored["frequency_hz"] != expected_frequency
        or stored["context"].manifest != context.manifest
        or stored["context"].action["action_identity_sha256"] != expected_prior_sha
        or stored["result"]["state"] != ResultState.PASS.value
        or stored["final"]["outcome"] != "PASS"
    ):
        raise N7PhysicalOnceError("predecessor is not the exact previous-frequency PASS")
    prior_usage = stored["context"].production.profile["usage"]
    current_usage = context.production.profile["usage"]
    if (
        current_usage["cumulative_visible_refresh_count"]
        != prior_usage["cumulative_visible_refresh_count"] + 1
        or current_usage["session_visible_refresh_count"] != 0
        or current_usage["consecutive_visible_refresh_count"] != 0
        or current_usage["last_visible_refresh_completed_at"]
        != stored["live"]["protocol_completed_at"]
    ):
        raise N7PhysicalOnceError("current profile usage does not continue predecessor exactly")
    return _Prior(
        directory=stored["directory"],
        live=stored["live"],
        final=stored["final"],
        result=stored["result"],
        final_file_sha256=stored["final_snapshot"].sha256,
        result_file_sha256=stored["result_snapshot"].sha256,
    )


def _protocol(
    context: _Context,
    prior: Optional[_Prior],
    base_url: str,
    *,
    requester: Optional[Callable[..., tuple[int, str]]],
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
    job_timeout_s: float,
) -> tuple[dict[str, Any], legacy._AuditedRequester]:
    audited = legacy._AuditedRequester(
        requester or frame_tool.http_request,
        str(context.action["identity"]["request"]["endpoint"]),
    )
    version_raw, version_fields = legacy._version(audited, base_url)
    prior_job = legacy._request_json(audited, base_url, "/api/job")
    prior_report = legacy._request_json(audited, base_url, "/api/diagnostic/report")
    prior_gpio = legacy._request_json(audited, base_url, "/api/diagnostic/status")
    legacy._validate_gpio(prior_gpio, "pre-action")
    if prior is None:
        legacy._validate_job(prior_job, expected_id=0, state="idle", result=None)
        if prior_report != {
            "schema_version": 2,
            "valid": False,
            "error": "no_completed_job_report",
        }:
            raise N7PhysicalOnceError("first N7 physical action did not begin at job0/op0")
        prior_operation_id = 0
        plan_before = analyzer.build_plan(False)
    else:
        if (
            prior_job != prior.live["protocol"]["target_job"]
            or prior_report != prior.live["protocol"]["target_diagnostic"]
        ):
            raise N7PhysicalOnceError("device continuity differs from predecessor PASS")
        prior_operation_id = int(prior_report["operation_id"])
        plan_before = deepcopy(prior.final["sweep_plan"])
    try:
        plan_analysis = analyzer.analyze_document(plan_before)
    except analyzer.RefreshAnalysisError as error:
        raise N7PhysicalOnceError(f"N7 sweep plan before action is invalid: {error}") from error
    if plan_analysis.get("next_frequency_hz") != context.frequency_hz:
        raise N7PhysicalOnceError("frequency is not the next analyzer-approved action")
    queued_response = legacy._request_json(
        audited,
        base_url,
        str(context.action["identity"]["request"]["endpoint"]),
        method="POST",
        expected_status=202,
    )
    if set(queued_response) != {"ok", "job"} or queued_response.get("ok") is not True:
        raise N7PhysicalOnceError("N7 enqueue response fields differ")
    queued_job = queued_response.get("job")
    if not isinstance(queued_job, Mapping):
        raise N7PhysicalOnceError("N7 enqueue response lacks job object")
    expected_job_id = (int(prior_job["job_id"]) + 1) & 0xFFFFFFFF or 1
    legacy._validate_job(
        queued_job, expected_id=expected_job_id, state="queued", result=None
    )
    deadline = clock() + job_timeout_s
    completed: Optional[Mapping[str, Any]] = None
    while clock() < deadline:
        observed = legacy._request_json(audited, base_url, "/api/job")
        if observed.get("state") == "completed":
            legacy._validate_job(
                observed, expected_id=expected_job_id, state="completed", result=True
            )
            completed = observed
            break
        if observed.get("state") not in {"queued", "running"}:
            raise N7PhysicalOnceError("N7 job reached a non-success terminal state")
        sleeper(0.25)
    if completed is None:
        raise N7PhysicalOnceError("N7 job did not complete before the fixed deadline")
    diagnostic = legacy._request_json(audited, base_url, "/api/diagnostic/report")
    expected_operation_id = (prior_operation_id + 1) & 0xFFFFFFFF or 1
    legacy._validate_diagnostic(
        diagnostic,
        frequency_hz=context.frequency_hz,
        job=completed,
        operation_id=expected_operation_id,
    )
    post_gpio = legacy._request_json(audited, base_url, "/api/diagnostic/status")
    legacy._validate_gpio(post_gpio, "post-action")
    if audited.visible_posts != 1:
        raise N7PhysicalOnceError("N7 audit did not observe exactly one visible POST")
    return (
        {
            "version_raw": version_raw,
            "version_fields": dict(version_fields),
            "prior_job": deepcopy(prior_job),
            "prior_diagnostic": deepcopy(prior_report),
            "prior_gpio": deepcopy(prior_gpio),
            "queued_response": deepcopy(queued_response),
            "target_job": deepcopy(completed),
            "target_diagnostic": deepcopy(diagnostic),
            "post_gpio": deepcopy(post_gpio),
            "sweep_plan_before_action": plan_before,
        },
        audited,
    )


def _request_audit(audited: legacy._AuditedRequester) -> dict[str, Any]:
    return {
        "calls": deepcopy(audited.calls),
        "visible_post_count": audited.visible_posts,
        "visible_endpoint": audited.action_endpoint,
        "retry_count": 0,
        "recovery_count": 0,
    }


def _record_unknown(
    directory: Optional[Path],
    base: Mapping[str, Any],
    *,
    audited: Optional[legacy._AuditedRequester],
    error: BaseException,
    completed_at: str,
) -> None:
    if directory is None or not directory.is_dir():
        return
    audit = _request_audit(audited) if audited is not None else None
    live = {
        **dict(base),
        "protocol_completed_at": None,
        "outcome": "UNKNOWN_DO_NOT_RETRY",
        "protocol_verified": False,
        "protocol": None,
        "request_audit": audit,
        "error": {"type": type(error).__name__, "message": str(error)},
    }
    live_sha = _write_json(
        directory / LIVE_FILENAME, live, label="N7 physical UNKNOWN evidence"
    )
    post_count = audited.visible_posts if audited is not None else 0
    result = build_result_record(
        action_identity_sha256=str(base["action_identity_sha256"]),
        state=ResultState.UNKNOWN_DO_NOT_RETRY,
        completed_at=completed_at,
        evidence_manifest_sha256=live_sha,
        post_request_count=post_count,
        details="N7 physical claim consumed; retry and recovery are forbidden",
    )
    _write_json(directory / P0_RESULT_FILENAME, result, label="N7 UNKNOWN P0 result")


def run_physical_action_once(
    frequency_hz: int,
    result_dir: Path,
    base_url: str,
    *,
    physical_bundle_dir: Path,
    source_campaign_directory: Path,
    panel_file: Path,
    panel_binding_review_file: Path,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
    profile_file: Path,
    limit_authority_file: Path,
    usage_evidence_file: Path,
    profile_review_artifact_file: Path,
    reviewer_key_file: Path,
    authorization_confirmation: str,
    panel_confirmation: str,
    profile_confirmation: str,
    panel_power_off_seconds: float,
    start_temperature_c: float,
    confirmations: Mapping[str, bool],
    predecessor_result_dir: Optional[Path] = None,
    requester: Optional[Callable[..., tuple[int, str]]] = None,
    now: Callable[[], datetime] = _now_utc,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    job_timeout_s: float = legacy.DEFAULT_JOB_TIMEOUT_S,
) -> Mapping[str, Any]:
    """Claim and execute exactly one deeply reviewed physical N7 action."""

    evaluated_at = _timestamp(now())
    context = _load_context(
        frequency_hz,
        physical_bundle_dir=physical_bundle_dir,
        source_campaign_directory=source_campaign_directory,
        panel_file=panel_file,
        panel_binding_review_file=panel_binding_review_file,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
        profile_file=profile_file,
        limit_authority_file=limit_authority_file,
        usage_evidence_file=usage_evidence_file,
        profile_review_artifact_file=profile_review_artifact_file,
        reviewer_key_file=reviewer_key_file,
        evaluated_at=evaluated_at,
    )
    prior = _load_prior(
        predecessor_result_dir, context, reviewer_key_file=reviewer_key_file
    )
    expected_authorization = required_action_authorization(
        frequency_hz, str(context.action["action_identity_sha256"])
    )
    if authorization_confirmation != expected_authorization:
        raise N7PhysicalOnceError("exact N7 physical action authorization is required")
    if panel_confirmation != required_panel_confirmation(context):
        raise N7PhysicalOnceError("exact N7 physical panel confirmation is required")
    if profile_confirmation != required_profile_confirmation(context):
        raise N7PhysicalOnceError("exact N7 production profile confirmation is required")
    confirmed = _validate_confirmations(frequency_hz, confirmations)
    start_temperature = _number(
        start_temperature_c, label="start_temperature_c", minimum=-50
    )
    limits = context.production.profile["limits"]
    if not (
        float(limits["minimum_start_temperature_c"])
        <= start_temperature
        <= float(limits["maximum_start_temperature_c"])
    ):
        raise N7PhysicalOnceError("start temperature is outside reviewed limits")
    schedule = _schedule_decision(
        context,
        evaluated_at=evaluated_at,
        panel_power_off_seconds=panel_power_off_seconds,
    )
    if schedule["ready"] is not True:
        raise N7PhysicalOnceError(
            "N7 physical runtime schedule is not ready: "
            + ", ".join(schedule["blockers"])
        )
    timeout = _number(job_timeout_s, label="job_timeout_s", minimum=0.000_001)
    try:
        normalized_url = frame_tool._normalize_base_url(base_url)
    except frame_tool.FrameToolError as error:
        raise N7PhysicalOnceError(str(error)) from error
    destination = _safe_result_directory(result_dir, must_exist=False)
    claim_time = _timestamp(now())
    age = (
        _parse_timestamp(claim_time, label="claim time")
        - _parse_timestamp(evaluated_at, label="profile evaluation time")
    ).total_seconds()
    if age < 0 or age > MAX_LIVE_EVALUATION_AGE_SECONDS:
        raise N7PhysicalOnceError(
            "production profile evaluation is stale before claim; describe/run again"
        )
    attempt_id = uuid.uuid4().hex
    claim = _claim_action(
        context,
        attempt_id=attempt_id,
        claimed_at=claim_time,
        schedule=schedule,
        start_temperature_c=start_temperature,
        confirmations=confirmed,
        authorization_confirmation=authorization_confirmation,
        panel_confirmation=panel_confirmation,
        profile_confirmation=profile_confirmation,
        prior=prior,
    )
    created: Optional[Path] = None
    audited: Optional[legacy._AuditedRequester] = None
    base = {
        "schema_version": SCHEMA_VERSION,
        "kind": LIVE_KIND,
        "runner_kind": RUNNER_KIND,
        "attempt_id": attempt_id,
        "recorded_at": claim_time,
        "profile_evaluated_at": evaluated_at,
        "live_evaluation_age_seconds": age,
        "maximum_live_evaluation_age_seconds": MAX_LIVE_EVALUATION_AGE_SECONDS,
        "frequency_hz": frequency_hz,
        "action_key": context.action_key,
        "action_identity_sha256": context.action["action_identity_sha256"],
        "endpoint": context.action["identity"]["request"]["endpoint"],
        "materialization_canonical_sha256": context.manifest["integrity"][
            "canonical_sha256"
        ],
        "campaign_canonical_sha256": context.campaign["integrity"][
            "canonical_sha256"
        ],
        "profile_canonical_sha256": context.production.profile["integrity"][
            "canonical_sha256"
        ],
        "reviewer_key_id": context.production.reviewer_key_id,
        "snapshots": _snapshot_records(context),
        "claim": claim.reference(),
        "runtime_schedule_decision": schedule,
        "start_temperature_c": start_temperature,
        "confirmations": confirmed,
        "authorization_confirmation_sha256": _sha256(
            authorization_confirmation.encode("utf-8")
        ),
        "panel_confirmation_sha256": _sha256(panel_confirmation.encode("utf-8")),
        "profile_confirmation_sha256": _sha256(
            profile_confirmation.encode("utf-8")
        ),
        "predecessor_final_file_sha256": (
            prior.final_file_sha256 if prior is not None else None
        ),
        "predecessor_result_file_sha256": (
            prior.result_file_sha256 if prior is not None else None
        ),
        "maximum_visible_posts": 1,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "qualification_state": "NOT_QUALIFIED",
    }
    try:
        destination.mkdir()
        created = destination
        _copy_snapshots(destination, context)
        if prior is not None:
            _write_json(
                destination / PRIOR_LIVE_FILENAME,
                prior.live,
                label="copied prior N7 live evidence",
            )
            _write_json(
                destination / PRIOR_FINAL_FILENAME,
                prior.final,
                label="copied prior N7 final evidence",
            )
            _write_json(
                destination / PRIOR_RESULT_FILENAME,
                prior.result,
                label="copied prior N7 P0 result",
            )
        lock = {
            "schema_version": SCHEMA_VERSION,
            "kind": LOCK_KIND,
            "attempt_id": attempt_id,
            "action_identity_sha256": context.action["action_identity_sha256"],
            "claim": claim.reference(),
            "authorization_confirmation_sha256": base[
                "authorization_confirmation_sha256"
            ],
            "panel_confirmation_sha256": base["panel_confirmation_sha256"],
            "profile_confirmation_sha256": base["profile_confirmation_sha256"],
            "runtime_schedule_decision": schedule,
            "state": "visible_action_may_have_been_attempted_do_not_rerun",
            "maximum_visible_posts": 1,
            "automatic_retry": False,
            "automatic_recovery": False,
        }
        _write_json(destination / LOCK_FILENAME, lock, label="N7 physical attempt lock")
        protocol, audited = _protocol(
            context,
            prior,
            normalized_url,
            requester=requester,
            clock=clock,
            sleeper=sleeper,
            job_timeout_s=timeout,
        )
        completed_at = _timestamp(now())
        live = {
            **base,
            "protocol_completed_at": completed_at,
            "outcome": "PROTOCOL_PASS_PENDING_FINALIZATION",
            "protocol_verified": True,
            "protocol": protocol,
            "request_audit": _request_audit(audited),
            "error": None,
        }
        _write_json(destination / LIVE_FILENAME, live, label="N7 physical live evidence")
        return live
    except BaseException as error:
        try:
            _record_unknown(
                created,
                base,
                audited=audited,
                error=error,
                completed_at=_timestamp(now()),
            )
        except BaseException:
            pass
        raise N7PhysicalOnceUnknown(
            "N7 physical action is UNKNOWN_DO_NOT_RETRY; its claim is permanent"
        ) from error


def _sealed_record(payload: Mapping[str, Any], *, scope: str) -> dict[str, Any]:
    unsigned = deepcopy(dict(payload))
    if "integrity" in unsigned:
        raise N7PhysicalOnceError("record payload unexpectedly contains integrity")
    return {
        **unsigned,
        "integrity": {
            "canonical_sha256": _sha256(unsigned),
            "canonical_sha256_scope": scope,
        },
    }


def _validate_sealed_record(value: Mapping[str, Any], *, scope: str, label: str) -> None:
    if not isinstance(value, Mapping) or "integrity" not in value:
        raise N7PhysicalOnceError(f"{label} lacks integrity")
    unsigned = dict(value)
    integrity = unsigned.pop("integrity")
    if integrity != {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": scope,
    }:
        raise N7PhysicalOnceError(f"{label} integrity changed")


def _load_stored_context(
    directory: Path,
    live: Mapping[str, Any],
    *,
    reviewer_key_file: Path,
) -> _Context:
    manifest_snapshot = _read(
        directory / PHYSICAL_DIRECTORY / physical.MANIFEST_FILENAME,
        label="stored N7 physical manifest",
    )
    manifest = _json(manifest_snapshot, label="stored N7 physical manifest")
    schedule = manifest.get("operator_process_schedule")
    if not isinstance(schedule, Mapping):
        raise N7PhysicalOnceError("stored N7 materialization lacks process schedule")
    frequency = live.get("frequency_hz")
    if type(frequency) is not int:
        raise N7PhysicalOnceError("stored N7 live frequency is invalid")
    return _load_context(
        frequency,
        physical_bundle_dir=directory / PHYSICAL_DIRECTORY,
        source_campaign_directory=directory / SOURCE_DIRECTORY,
        panel_file=directory / PANEL_FILENAME,
        panel_binding_review_file=directory / BINDING_REVIEW_FILENAME,
        minimum_interval_seconds=schedule["minimum_interval_seconds"],
        planned_cooldown_seconds=schedule["planned_cooldown_seconds"],
        profile_file=directory / PROFILE_FILENAME,
        limit_authority_file=directory / AUTHORITY_FILENAME,
        usage_evidence_file=directory / USAGE_FILENAME,
        profile_review_artifact_file=directory / PROFILE_REVIEW_FILENAME,
        reviewer_key_file=reviewer_key_file,
        evaluated_at=str(live.get("profile_evaluated_at")),
    )


def _validate_prior_copies(
    directory: Path,
    context: _Context,
    live: Mapping[str, Any],
) -> tuple[Optional[Mapping[str, Any]], Optional[Mapping[str, Any]]]:
    dependent = context.action["identity"]["prior"] is not None
    paths = (
        directory / PRIOR_LIVE_FILENAME,
        directory / PRIOR_FINAL_FILENAME,
        directory / PRIOR_RESULT_FILENAME,
    )
    present = [os.path.lexists(path) for path in paths]
    if not dependent:
        if any(present):
            raise N7PhysicalOnceError("root N7 action unexpectedly has prior copies")
        if (
            live.get("predecessor_final_file_sha256") is not None
            or live.get("predecessor_result_file_sha256") is not None
        ):
            raise N7PhysicalOnceError("root N7 action gained predecessor hashes")
        return None, None
    if not all(present):
        raise N7PhysicalOnceError("dependent N7 action has incomplete prior copies")
    prior_live_snapshot = _read(paths[0], label="copied prior N7 live")
    prior_final_snapshot = _read(paths[1], label="copied prior N7 final")
    prior_result_snapshot = _read(paths[2], label="copied prior N7 P0 result")
    prior_live = _json(prior_live_snapshot, label="copied prior N7 live")
    prior_final = _json(prior_final_snapshot, label="copied prior N7 final")
    prior_result = _json(prior_result_snapshot, label="copied prior N7 P0 result")
    _validate_sealed_record(
        prior_final, scope="N7 physical final evidence excluding integrity", label="prior final"
    )
    try:
        validate_result_record(prior_result)
    except CampaignContractError as error:
        raise N7PhysicalOnceError(f"copied prior P0 result is invalid: {error}") from error
    expected_prior_sha = context.action["identity"]["prior"][
        "action_identity_sha256"
    ]
    expected_frequency = frozen.FREQUENCIES[
        frozen.FREQUENCIES.index(context.frequency_hz) - 1
    ]
    if (
        prior_live.get("action_identity_sha256") != expected_prior_sha
        or prior_live.get("frequency_hz") != expected_frequency
        or prior_live.get("outcome") != "PROTOCOL_PASS_PENDING_FINALIZATION"
        or prior_final.get("action_identity_sha256") != expected_prior_sha
        or prior_final.get("frequency_hz") != expected_frequency
        or prior_final.get("outcome") != "PASS"
        or prior_result.get("action_identity_sha256") != expected_prior_sha
        or prior_result.get("state") != ResultState.PASS.value
        or prior_final_snapshot.sha256
        != live.get("predecessor_final_file_sha256")
        or prior_result_snapshot.sha256
        != live.get("predecessor_result_file_sha256")
    ):
        raise N7PhysicalOnceError("copied predecessor binding changed")
    return prior_live, prior_final


def _validate_request_audit(context: _Context, audit: Any) -> None:
    endpoint = context.action["identity"]["request"]["endpoint"]
    if (
        not isinstance(audit, Mapping)
        or audit.get("visible_post_count") != 1
        or audit.get("visible_endpoint") != endpoint
        or audit.get("retry_count") != 0
        or audit.get("recovery_count") != 0
    ):
        raise N7PhysicalOnceError("N7 physical request audit safety fields changed")
    calls = audit.get("calls")
    if not isinstance(calls, list) or len(calls) < 8:
        raise N7PhysicalOnceError("N7 physical request audit is incomplete")
    observed = []
    for index, call in enumerate(calls):
        if not isinstance(call, Mapping) or call.get("sequence") != index:
            raise N7PhysicalOnceError("N7 request audit sequence changed")
        observed.append((call.get("method"), call.get("endpoint")))
    if observed[:5] != [
        ("GET", "/api/version"),
        ("GET", "/api/job"),
        ("GET", "/api/diagnostic/report"),
        ("GET", "/api/diagnostic/status"),
        ("POST", endpoint),
    ]:
        raise N7PhysicalOnceError("N7 preflight/POST audit order changed")
    if observed[-2:] != [
        ("GET", "/api/diagnostic/report"),
        ("GET", "/api/diagnostic/status"),
    ] or any(call != ("GET", "/api/job") for call in observed[5:-2]):
        raise N7PhysicalOnceError("N7 post/terminal audit order changed")


def _validate_protocol(
    directory: Path,
    context: _Context,
    live: Mapping[str, Any],
) -> None:
    protocol = live.get("protocol")
    if not isinstance(protocol, Mapping):
        raise N7PhysicalOnceError("N7 physical protocol evidence is missing")
    version_fields = legacy._parse_version_body(protocol.get("version_raw"))
    if protocol.get("version_fields") != version_fields:
        raise N7PhysicalOnceError("N7 version parse changed")
    prior_live, prior_final = _validate_prior_copies(directory, context, live)
    prior_job = protocol.get("prior_job")
    prior_report = protocol.get("prior_diagnostic")
    prior_gpio = protocol.get("prior_gpio")
    if not all(isinstance(value, Mapping) for value in (prior_job, prior_report, prior_gpio)):
        raise N7PhysicalOnceError("N7 prior device evidence is incomplete")
    legacy._validate_gpio(prior_gpio, "stored pre-action")
    if prior_live is None:
        legacy._validate_job(prior_job, expected_id=0, state="idle", result=None)
        if prior_report != {
            "schema_version": 2,
            "valid": False,
            "error": "no_completed_job_report",
        }:
            raise N7PhysicalOnceError("stored root N7 action did not start at job0/op0")
        prior_operation_id = 0
    else:
        assert prior_final is not None
        if (
            prior_job != prior_live["protocol"]["target_job"]
            or prior_report != prior_live["protocol"]["target_diagnostic"]
        ):
            raise N7PhysicalOnceError("stored N7 predecessor continuity changed")
        prior_operation_id = int(prior_report["operation_id"])
        if protocol.get("sweep_plan_before_action") != prior_final.get("sweep_plan"):
            raise N7PhysicalOnceError("stored N7 predecessor sweep plan changed")
    plan = protocol.get("sweep_plan_before_action")
    try:
        plan_analysis = analyzer.analyze_document(plan)
    except analyzer.RefreshAnalysisError as error:
        raise N7PhysicalOnceError(f"stored N7 sweep plan is invalid: {error}") from error
    if plan_analysis.get("next_frequency_hz") != context.frequency_hz:
        raise N7PhysicalOnceError("stored N7 action was not the next approved frequency")
    queued = protocol.get("queued_response")
    target_job = protocol.get("target_job")
    diagnostic = protocol.get("target_diagnostic")
    post_gpio = protocol.get("post_gpio")
    if not all(isinstance(value, Mapping) for value in (queued, target_job, diagnostic, post_gpio)):
        raise N7PhysicalOnceError("N7 target protocol evidence is incomplete")
    expected_job_id = (int(prior_job["job_id"]) + 1) & 0xFFFFFFFF or 1
    if set(queued) != {"ok", "job"} or queued.get("ok") is not True:
        raise N7PhysicalOnceError("stored N7 queued response changed")
    legacy._validate_job(
        queued["job"], expected_id=expected_job_id, state="queued", result=None
    )
    legacy._validate_job(
        target_job, expected_id=expected_job_id, state="completed", result=True
    )
    expected_operation_id = (prior_operation_id + 1) & 0xFFFFFFFF or 1
    legacy._validate_diagnostic(
        diagnostic,
        frequency_hz=context.frequency_hz,
        job=target_job,
        operation_id=expected_operation_id,
    )
    legacy._validate_gpio(post_gpio, "stored post-action")
    _validate_request_audit(context, live.get("request_audit"))


def _expected_claim_record(
    context: _Context,
    live: Mapping[str, Any],
) -> Mapping[str, Any]:
    claim = _validate_claim_reference(live.get("claim"), context)
    expected_tokens = {
        "authorization_confirmation_sha256": _sha256(
            required_action_authorization(
                context.frequency_hz, str(context.action["action_identity_sha256"])
            ).encode("utf-8")
        ),
        "panel_confirmation_sha256": _sha256(
            required_panel_confirmation(context).encode("utf-8")
        ),
        "profile_confirmation_sha256": _sha256(
            required_profile_confirmation(context).encode("utf-8")
        ),
    }
    for field, expected in expected_tokens.items():
        if live.get(field) != expected or claim.get(field) != expected:
            raise N7PhysicalOnceError(f"stored N7 {field} binding changed")
    expected_pairs = {
        "attempt_id": live.get("attempt_id"),
        "claimed_at": live.get("recorded_at"),
        "action_identity_sha256": context.action["action_identity_sha256"],
        "frequency_hz": context.frequency_hz,
        "endpoint": context.action["identity"]["request"]["endpoint"],
        "materialization_canonical_sha256": context.manifest["integrity"][
            "canonical_sha256"
        ],
        "campaign_canonical_sha256": context.campaign["integrity"][
            "canonical_sha256"
        ],
        "profile_canonical_sha256": context.production.profile["integrity"][
            "canonical_sha256"
        ],
        "profile_file_sha256": context.production.profile_file.sha256,
        "reviewer_key_id": context.production.reviewer_key_id,
        "runtime_schedule_decision": live.get("runtime_schedule_decision"),
        "start_temperature_c": live.get("start_temperature_c"),
        "confirmations": live.get("confirmations"),
        "predecessor_final_file_sha256": live.get("predecessor_final_file_sha256"),
        "predecessor_result_file_sha256": live.get("predecessor_result_file_sha256"),
    }
    for field, expected in expected_pairs.items():
        if claim.get(field) != expected:
            raise N7PhysicalOnceError(f"stored N7 claim {field} changed")
    return claim


def _validate_control(
    directory: Path,
    context: _Context,
    live: Mapping[str, Any],
) -> None:
    if live.get("snapshots") != _snapshot_records(context):
        raise N7PhysicalOnceError("stored N7 source/profile snapshots changed")
    if (
        live.get("runner_kind") != RUNNER_KIND
        or live.get("action_identity_sha256")
        != context.action["action_identity_sha256"]
        or live.get("materialization_canonical_sha256")
        != context.manifest["integrity"]["canonical_sha256"]
        or live.get("campaign_canonical_sha256")
        != context.campaign["integrity"]["canonical_sha256"]
        or live.get("profile_canonical_sha256")
        != context.production.profile["integrity"]["canonical_sha256"]
        or live.get("reviewer_key_id") != context.production.reviewer_key_id
        or live.get("maximum_live_evaluation_age_seconds")
        != MAX_LIVE_EVALUATION_AGE_SECONDS
        or live.get("maximum_visible_posts") != 1
        or live.get("automatic_retry_authorized") is not False
        or live.get("automatic_recovery_authorized") is not False
        or live.get("qualification_state") != "NOT_QUALIFIED"
    ):
        raise N7PhysicalOnceError("stored N7 physical control binding changed")
    evaluated = _parse_timestamp(
        live.get("profile_evaluated_at"), label="stored profile evaluated_at"
    )
    recorded = _parse_timestamp(live.get("recorded_at"), label="stored claim time")
    age = (recorded - evaluated).total_seconds()
    if (
        age < 0
        or age > MAX_LIVE_EVALUATION_AGE_SECONDS
        or live.get("live_evaluation_age_seconds") != age
    ):
        raise N7PhysicalOnceError("stored N7 profile freshness binding changed")
    confirmations = _validate_confirmations(
        context.frequency_hz, live.get("confirmations")
    )
    del confirmations
    measured_off = live.get("runtime_schedule_decision", {}).get(
        "measured_panel_power_off_seconds"
    )
    expected_schedule = _schedule_decision(
        context,
        evaluated_at=str(live.get("profile_evaluated_at")),
        panel_power_off_seconds=measured_off,
    )
    if (
        expected_schedule != live.get("runtime_schedule_decision")
        or expected_schedule["ready"] is not True
    ):
        raise N7PhysicalOnceError("stored N7 runtime schedule decision changed")
    claim = _expected_claim_record(context, live)
    lock_snapshot = _read(directory / LOCK_FILENAME, label="N7 physical attempt lock")
    lock = _json(lock_snapshot, label="N7 physical attempt lock")
    if lock != {
        "schema_version": SCHEMA_VERSION,
        "kind": LOCK_KIND,
        "attempt_id": live["attempt_id"],
        "action_identity_sha256": context.action["action_identity_sha256"],
        "claim": live["claim"],
        "authorization_confirmation_sha256": live[
            "authorization_confirmation_sha256"
        ],
        "panel_confirmation_sha256": live["panel_confirmation_sha256"],
        "profile_confirmation_sha256": live["profile_confirmation_sha256"],
        "runtime_schedule_decision": live["runtime_schedule_decision"],
        "state": "visible_action_may_have_been_attempted_do_not_rerun",
        "maximum_visible_posts": 1,
        "automatic_retry": False,
        "automatic_recovery": False,
    }:
        raise N7PhysicalOnceError("N7 physical attempt lock changed")
    _validate_claim_reference(live["claim"], context, expected_record=claim)


def _read_optional_timing(directory: Path, final: Mapping[str, Any]) -> Optional[bytes]:
    reference = final["raw_evidence"]["timing"]
    path = directory / TIMING_FILENAME
    if reference is None:
        if os.path.lexists(path):
            raise N7PhysicalOnceError("unreferenced N7 timing capture exists")
        return None
    snapshot = _read(path, label="stored N7 timing capture")
    if reference != {"filename": TIMING_FILENAME, "bytes": len(snapshot.payload), "sha256": snapshot.sha256}:
        raise N7PhysicalOnceError("stored N7 timing capture reference changed")
    return snapshot.payload


def _recompute_final_analysis(
    directory: Path,
    live: Mapping[str, Any],
    final: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    serial = _read(directory / SERIAL_FILENAME, label="stored N7 serial capture")
    scope = _read(directory / SCOPE_FILENAME, label="stored N7 scope capture")
    timing = _read_optional_timing(directory, final)
    raw = final.get("raw_evidence")
    if not isinstance(raw, Mapping):
        raise N7PhysicalOnceError("N7 final raw evidence references are missing")
    if raw.get("serial") != {
        "filename": SERIAL_FILENAME,
        "bytes": len(serial.payload),
        "sha256": serial.sha256,
    } or raw.get("scope") != {
        "filename": SCOPE_FILENAME,
        "bytes": len(scope.payload),
        "sha256": scope.sha256,
    }:
        raise N7PhysicalOnceError("N7 serial/scope evidence reference changed")
    observation = final.get("observation")
    if not isinstance(observation, Mapping):
        raise N7PhysicalOnceError("N7 final observation is missing")
    protocol = live["protocol"]
    try:
        extracted = analyzer.extract_observation(
            int(live["frequency_hz"]),
            serial.payload,
            protocol["target_diagnostic"],
            protocol["target_job"],
            protocol["version_raw"].encode("utf-8"),
            scope.payload,
            cold_start=True,
            power_off_s=float(
                live["runtime_schedule_decision"]["measured_panel_power_off_seconds"]
            ),
            supply_voltage_v=observation["supply_voltage_v"],
            current_limit_a=observation["current_limit_a"],
            peak_current_a=observation["peak_current_a"],
            max_temperature_c=observation["max_temperature_c"],
            measured_sclk_hz=observation["measured_sclk_hz"],
            sclk_pass=observation["sclk_pass"],
            visual_pass=observation["visual_pass"],
            cv_pass=observation["cv_pass"],
            thermal_pass=observation["thermal_pass"],
            acoustic_pass=observation["acoustic_pass"],
            timing_evidence=timing,
            timing_pass=observation["timing_pass"],
            notes=observation["notes"],
        )
        populated = analyzer._replace_run(
            protocol["sweep_plan_before_action"], extracted
        )
        analysis = analyzer.analyze_document(populated)
    except (KeyError, TypeError, ValueError, analyzer.RefreshAnalysisError) as error:
        raise N7PhysicalOnceError(f"N7 final evidence replay failed: {error}") from error
    return populated, analysis


def _validate_result_directory(
    result_dir: Path,
    *,
    reviewer_key_file: Path,
    require_finalized: bool,
) -> dict[str, Any]:
    directory = _safe_result_directory(result_dir, must_exist=True)
    live_snapshot = _read(directory / LIVE_FILENAME, label="N7 physical live evidence")
    live = _json(live_snapshot, label="N7 physical live evidence")
    if live.get("schema_version") != SCHEMA_VERSION or live.get("kind") != LIVE_KIND:
        raise N7PhysicalOnceError("N7 physical live kind/schema changed")
    context = _load_stored_context(directory, live, reviewer_key_file=reviewer_key_file)
    _validate_control(directory, context, live)
    outcome = live.get("outcome")
    final_path = directory / FINAL_FILENAME
    result_path = directory / P0_RESULT_FILENAME
    if outcome == "UNKNOWN_DO_NOT_RETRY":
        if live.get("protocol_verified") is not False or live.get("protocol") is not None:
            raise N7PhysicalOnceError("N7 UNKNOWN evidence gained verified protocol")
        result_snapshot = _read(result_path, label="N7 UNKNOWN P0 result")
        result = _json(result_snapshot, label="N7 UNKNOWN P0 result")
        try:
            validate_result_record(result)
        except CampaignContractError as error:
            raise N7PhysicalOnceError(f"N7 UNKNOWN result is invalid: {error}") from error
        if (
            result["state"] != ResultState.UNKNOWN_DO_NOT_RETRY.value
            or result["evidence_manifest_sha256"] != live_snapshot.sha256
            or os.path.lexists(final_path)
        ):
            raise N7PhysicalOnceError("N7 UNKNOWN terminal binding changed")
        if require_finalized:
            raise N7PhysicalOnceError("N7 action is UNKNOWN and cannot be finalized")
        return {
            "directory": directory,
            "context": context,
            "frequency_hz": context.frequency_hz,
            "live": live,
            "live_snapshot": live_snapshot,
            "final": None,
            "final_snapshot": None,
            "result": result,
            "result_snapshot": result_snapshot,
        }
    if (
        outcome != "PROTOCOL_PASS_PENDING_FINALIZATION"
        or live.get("protocol_verified") is not True
        or live.get("error") is not None
    ):
        raise N7PhysicalOnceError("N7 physical live outcome is invalid")
    completed = _parse_timestamp(
        live.get("protocol_completed_at"), label="N7 protocol_completed_at"
    )
    if completed < _parse_timestamp(live.get("recorded_at"), label="N7 claim time"):
        raise N7PhysicalOnceError("N7 protocol completed before claim")
    _validate_protocol(directory, context, live)
    final_exists = os.path.lexists(final_path)
    result_exists = os.path.lexists(result_path)
    if final_exists != result_exists:
        raise N7PhysicalOnceError("N7 finalization/result is partial")
    if not final_exists:
        if require_finalized:
            raise N7PhysicalOnceError("N7 physical action is not finalized")
        return {
            "directory": directory,
            "context": context,
            "frequency_hz": context.frequency_hz,
            "live": live,
            "live_snapshot": live_snapshot,
            "final": None,
            "final_snapshot": None,
            "result": None,
            "result_snapshot": None,
        }
    final_snapshot = _read(final_path, label="N7 physical final evidence")
    final = _json(final_snapshot, label="N7 physical final evidence")
    _validate_sealed_record(
        final, scope="N7 physical final evidence excluding integrity", label="N7 final"
    )
    if (
        final.get("kind") != FINAL_KIND
        or final.get("frequency_hz") != context.frequency_hz
        or final.get("action_identity_sha256")
        != context.action["action_identity_sha256"]
        or final.get("live_file_sha256") != live_snapshot.sha256
        or final.get("claim") != live.get("claim")
        or final.get("qualification_state") != "NOT_QUALIFIED"
        or final.get("automatic_retry_authorized") is not False
        or final.get("automatic_recovery_authorized") is not False
    ):
        raise N7PhysicalOnceError("N7 final control binding changed")
    populated, analysis = _recompute_final_analysis(directory, live, final)
    if final.get("sweep_plan") != populated or final.get("analysis") != analysis:
        raise N7PhysicalOnceError("N7 final analyzer replay changed")
    rows = [
        row for row in analysis["results"] if row["spi_hz"] == context.frequency_hz
    ]
    passed = (
        len(rows) == 1
        and rows[0]["status"] == "PASS"
        and analysis.get("highest_passed_hz") == context.frequency_hz
    )
    expected_outcome = "PASS" if passed else "FAIL"
    if final.get("outcome") != expected_outcome:
        raise N7PhysicalOnceError("N7 final outcome differs from analyzer")
    result_snapshot = _read(result_path, label="N7 physical P0 result")
    result = _json(result_snapshot, label="N7 physical P0 result")
    try:
        validate_result_record(result)
    except CampaignContractError as error:
        raise N7PhysicalOnceError(f"N7 physical P0 result is invalid: {error}") from error
    if (
        result_file_sha256(result) != result_snapshot.sha256
        or result["action_identity_sha256"]
        != context.action["action_identity_sha256"]
        or result["state"]
        != (ResultState.PASS.value if passed else ResultState.FAIL.value)
        or result["evidence_manifest_sha256"] != final_snapshot.sha256
        or result["post_request_count"] != 1
    ):
        raise N7PhysicalOnceError("N7 physical P0 result binding changed")
    return {
        "directory": directory,
        "context": context,
        "frequency_hz": context.frequency_hz,
        "live": live,
        "live_snapshot": live_snapshot,
        "final": final,
        "final_snapshot": final_snapshot,
        "result": result,
        "result_snapshot": result_snapshot,
    }


def validate_physical_result(
    result_dir: Path,
    *,
    reviewer_key_file: Path,
    require_finalized: bool = True,
) -> dict[str, Any]:
    """Public deep validator for one self-contained physical N7 result."""

    stored = _validate_result_directory(
        result_dir,
        reviewer_key_file=reviewer_key_file,
        require_finalized=require_finalized,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-n7-physical-result-validation",
        "frequency_hz": stored["frequency_hz"],
        "action_identity_sha256": stored["context"].action[
            "action_identity_sha256"
        ],
        "state": (
            stored["result"]["state"] if stored["result"] is not None else "PENDING"
        ),
        "outcome": stored["live"]["outcome"],
        "finalized": stored["final"] is not None,
        "materialization_canonical_sha256": stored["context"].manifest[
            "integrity"
        ]["canonical_sha256"],
        "campaign_canonical_sha256": stored["context"].campaign["integrity"][
            "canonical_sha256"
        ],
        "profile_canonical_sha256": stored["context"].production.profile[
            "integrity"
        ]["canonical_sha256"],
        "reviewer_key_id": stored["context"].production.reviewer_key_id,
        "qualification_state": "NOT_QUALIFIED",
        "deep_validation_pass": True,
    }


def _write_or_match(path: Path, payload: bytes, *, label: str) -> None:
    if os.path.lexists(path):
        snapshot = _read(path, label=label)
        if snapshot.payload != payload:
            raise N7PhysicalOnceError(f"existing {label} bytes differ")
        return
    _write_new(path, payload, label=label)


def finalize_physical_result(
    result_dir: Path,
    serial_log_path: Path,
    scope_evidence_path: Path,
    *,
    reviewer_key_file: Path,
    measured_sclk_hz: float,
    supply_voltage_v: float,
    current_limit_a: float,
    peak_current_a: float,
    max_temperature_c: float,
    visual_pass: bool,
    cv_pass: bool,
    thermal_pass: bool,
    acoustic_pass: bool,
    sclk_pass: bool,
    timing_evidence_path: Optional[Path] = None,
    timing_pass: Optional[bool] = None,
    notes: str = "",
    now: Callable[[], datetime] = _now_utc,
) -> Mapping[str, Any]:
    """Attach real manual/scope evidence and commit one terminal PASS/FAIL."""

    stored = _validate_result_directory(
        result_dir,
        reviewer_key_file=reviewer_key_file,
        require_finalized=False,
    )
    if stored["final"] is not None or stored["result"] is not None:
        raise N7PhysicalOnceError("N7 physical result is already terminal")
    live = stored["live"]
    if live["outcome"] != "PROTOCOL_PASS_PENDING_FINALIZATION":
        raise N7PhysicalOnceError("only protocol-PASS evidence can be finalized")
    booleans = {
        "visual_pass": visual_pass,
        "cv_pass": cv_pass,
        "thermal_pass": thermal_pass,
        "acoustic_pass": acoustic_pass,
        "sclk_pass": sclk_pass,
    }
    if any(type(value) is not bool for value in booleans.values()):
        raise N7PhysicalOnceError("N7 final verdict fields must be boolean")
    if timing_pass is not None and type(timing_pass) is not bool:
        raise N7PhysicalOnceError("timing_pass must be boolean or null")
    if not isinstance(notes, str) or len(notes) > 4096:
        raise N7PhysicalOnceError("N7 final notes must be at most 4096 characters")
    observation = {
        "measured_sclk_hz": _number(
            measured_sclk_hz, label="measured_sclk_hz", minimum=0.000_001
        ),
        "supply_voltage_v": _number(
            supply_voltage_v, label="supply_voltage_v", minimum=0
        ),
        "current_limit_a": _number(
            current_limit_a, label="current_limit_a", minimum=0
        ),
        "peak_current_a": _number(peak_current_a, label="peak_current_a", minimum=0),
        "max_temperature_c": _number(
            max_temperature_c, label="max_temperature_c", minimum=-50
        ),
        **booleans,
        "timing_pass": timing_pass,
        "notes": notes,
    }
    maximum_post_temperature = float(
        stored["context"].production.profile["limits"][
            "maximum_post_refresh_temperature_c"
        ]
    )
    if observation["max_temperature_c"] > maximum_post_temperature:
        raise N7PhysicalOnceError("observed temperature exceeds reviewed post-refresh limit")
    serial = _read(serial_log_path, label="N7 serial capture")
    scope = _read(scope_evidence_path, label="N7 scope capture")
    timing = (
        _read(timing_evidence_path, label="N7 timing capture")
        if timing_evidence_path is not None
        else None
    )
    directory = stored["directory"]
    _write_or_match(directory / SERIAL_FILENAME, serial.payload, label="N7 serial capture")
    _write_or_match(directory / SCOPE_FILENAME, scope.payload, label="N7 scope capture")
    if timing is not None:
        _write_or_match(
            directory / TIMING_FILENAME, timing.payload, label="N7 timing capture"
        )
    raw = {
        "serial": {
            "filename": SERIAL_FILENAME,
            "bytes": len(serial.payload),
            "sha256": serial.sha256,
        },
        "scope": {
            "filename": SCOPE_FILENAME,
            "bytes": len(scope.payload),
            "sha256": scope.sha256,
        },
        "timing": (
            {
                "filename": TIMING_FILENAME,
                "bytes": len(timing.payload),
                "sha256": timing.sha256,
            }
            if timing is not None
            else None
        ),
    }
    # Reuse the frozen analyzer before publishing either terminal file.
    protocol = live["protocol"]
    try:
        extracted = analyzer.extract_observation(
            int(live["frequency_hz"]),
            serial.payload,
            protocol["target_diagnostic"],
            protocol["target_job"],
            protocol["version_raw"].encode("utf-8"),
            scope.payload,
            cold_start=True,
            power_off_s=float(
                live["runtime_schedule_decision"]["measured_panel_power_off_seconds"]
            ),
            supply_voltage_v=observation["supply_voltage_v"],
            current_limit_a=observation["current_limit_a"],
            peak_current_a=observation["peak_current_a"],
            max_temperature_c=observation["max_temperature_c"],
            measured_sclk_hz=observation["measured_sclk_hz"],
            sclk_pass=observation["sclk_pass"],
            visual_pass=observation["visual_pass"],
            cv_pass=observation["cv_pass"],
            thermal_pass=observation["thermal_pass"],
            acoustic_pass=observation["acoustic_pass"],
            timing_evidence=timing.payload if timing is not None else None,
            timing_pass=observation["timing_pass"],
            notes=observation["notes"],
        )
        populated = analyzer._replace_run(
            protocol["sweep_plan_before_action"], extracted
        )
        analysis = analyzer.analyze_document(populated)
    except analyzer.RefreshAnalysisError as error:
        raise N7PhysicalOnceError(f"N7 analyzer rejected final evidence: {error}") from error
    rows = [
        row for row in analysis["results"] if row["spi_hz"] == live["frequency_hz"]
    ]
    passed = (
        len(rows) == 1
        and rows[0]["status"] == "PASS"
        and analysis.get("highest_passed_hz") == live["frequency_hz"]
    )
    final = _sealed_record(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": FINAL_KIND,
            "finalized_at": _timestamp(now()),
            "outcome": "PASS" if passed else "FAIL",
            "frequency_hz": live["frequency_hz"],
            "action_identity_sha256": live["action_identity_sha256"],
            "live_file_sha256": stored["live_snapshot"].sha256,
            "claim": deepcopy(live["claim"]),
            "materialization_canonical_sha256": live[
                "materialization_canonical_sha256"
            ],
            "profile_canonical_sha256": live["profile_canonical_sha256"],
            "raw_evidence": raw,
            "observation": observation,
            "sweep_plan": populated,
            "analysis": analysis,
            "next_frequency_may_be_described_after_new_usage_review": passed,
            "automatic_next_frequency_authorized": False,
            "automatic_retry_authorized": False,
            "automatic_recovery_authorized": False,
            "qualification_state": "NOT_QUALIFIED",
        },
        scope="N7 physical final evidence excluding integrity",
    )
    final_sha = _write_json(
        directory / FINAL_FILENAME, final, label="N7 physical final evidence"
    )
    result = build_result_record(
        action_identity_sha256=str(live["action_identity_sha256"]),
        state=ResultState.PASS if passed else ResultState.FAIL,
        completed_at=str(live["protocol_completed_at"]),
        evidence_manifest_sha256=final_sha,
        post_request_count=1,
        details=(
            "N7 physical protocol and manual/scope evidence passed"
            if passed
            else "N7 physical evidence failed; stop the sweep"
        ),
    )
    _write_json(directory / P0_RESULT_FILENAME, result, label="N7 physical P0 result")
    validate_physical_result(
        directory, reviewer_key_file=reviewer_key_file, require_finalized=True
    )
    return final


def _add_production_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--physical-bundle", type=Path, required=True)
    parser.add_argument("--source-campaign-dir", type=Path, required=True)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--binding-review", type=Path, required=True)
    parser.add_argument("--minimum-interval-seconds", type=float, required=True)
    parser.add_argument("--planned-cooldown-seconds", type=float, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--limit-authority", type=Path, required=True)
    parser.add_argument("--usage-evidence", type=Path, required=True)
    parser.add_argument("--profile-review", type=Path, required=True)
    parser.add_argument("--reviewer-key", type=Path, required=True)


def _cli_production_inputs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "physical_bundle_dir": args.physical_bundle,
        "source_campaign_directory": args.source_campaign_dir,
        "panel_file": args.panel,
        "panel_binding_review_file": args.binding_review,
        "minimum_interval_seconds": args.minimum_interval_seconds,
        "planned_cooldown_seconds": args.planned_cooldown_seconds,
        "profile_file": args.profile,
        "limit_authority_file": args.limit_authority,
        "usage_evidence_file": args.usage_evidence,
        "profile_review_artifact_file": args.profile_review,
        "reviewer_key_file": args.reviewer_key,
    }


def _frequency(value: str) -> int:
    try:
        result = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("frequency must be an integer Hz") from error
    if result not in frozen.FREQUENCIES:
        raise argparse.ArgumentTypeError("frequency must be 1/2/4/8/10 MHz")
    return result


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    describe = commands.add_parser("describe")
    _add_production_inputs(describe)
    describe.add_argument("--frequency-hz", type=_frequency, required=True)
    describe.add_argument("--predecessor-result-dir", type=Path)

    run = commands.add_parser("run")
    _add_production_inputs(run)
    run.add_argument("result_dir", type=Path)
    run.add_argument("--frequency-hz", type=_frequency, required=True)
    run.add_argument("--predecessor-result-dir", type=Path)
    run.add_argument("--url", required=True)
    run.add_argument("--authorization-confirmation", required=True)
    run.add_argument("--panel-confirmation", required=True)
    run.add_argument("--profile-confirmation", required=True)
    run.add_argument("--panel-power-off-seconds", type=float, required=True)
    run.add_argument("--start-temperature-c", type=float, required=True)
    for flag in sorted(
        set().union(*(_expected_confirmation_keys(value) for value in frozen.FREQUENCIES))
    ):
        run.add_argument(f"--confirm-{flag.replace('_', '-')}", action="store_true")

    finalize = commands.add_parser("finalize")
    finalize.add_argument("result_dir", type=Path)
    finalize.add_argument("--reviewer-key", type=Path, required=True)
    finalize.add_argument("--serial-log", type=Path, required=True)
    finalize.add_argument("--scope-evidence", type=Path, required=True)
    finalize.add_argument("--timing-evidence", type=Path)
    finalize.add_argument("--measured-sclk-hz", type=float, required=True)
    finalize.add_argument("--supply-voltage-v", type=float, required=True)
    finalize.add_argument("--current-limit-a", type=float, required=True)
    finalize.add_argument("--peak-current-a", type=float, required=True)
    finalize.add_argument("--max-temperature-c", type=float, required=True)
    for verdict in (
        "visual-pass",
        "cv-pass",
        "thermal-pass",
        "acoustic-pass",
        "sclk-pass",
    ):
        finalize.add_argument(
            f"--{verdict}", action=argparse.BooleanOptionalAction, required=True
        )
    finalize.add_argument(
        "--timing-pass", action=argparse.BooleanOptionalAction
    )
    finalize.add_argument("--notes", default="")

    validate = commands.add_parser("validate")
    validate.add_argument("result_dir", type=Path)
    validate.add_argument("--reviewer-key", type=Path, required=True)
    validate.add_argument("--allow-pending", action="store_true")
    return parser.parse_args(argv)


def _cli_confirmations(args: argparse.Namespace) -> dict[str, bool]:
    return {
        key: bool(getattr(args, f"confirm_{key}"))
        for key in _expected_confirmation_keys(args.frequency_hz)
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.command == "describe":
        value = describe_physical_action(
            args.frequency_hz,
            **_cli_production_inputs(args),
            predecessor_result_dir=args.predecessor_result_dir,
        )
    elif args.command == "run":
        value = run_physical_action_once(
            args.frequency_hz,
            args.result_dir,
            args.url,
            **_cli_production_inputs(args),
            authorization_confirmation=args.authorization_confirmation,
            panel_confirmation=args.panel_confirmation,
            profile_confirmation=args.profile_confirmation,
            panel_power_off_seconds=args.panel_power_off_seconds,
            start_temperature_c=args.start_temperature_c,
            confirmations=_cli_confirmations(args),
            predecessor_result_dir=args.predecessor_result_dir,
        )
    elif args.command == "finalize":
        value = finalize_physical_result(
            args.result_dir,
            args.serial_log,
            args.scope_evidence,
            reviewer_key_file=args.reviewer_key,
            timing_evidence_path=args.timing_evidence,
            measured_sclk_hz=args.measured_sclk_hz,
            supply_voltage_v=args.supply_voltage_v,
            current_limit_a=args.current_limit_a,
            peak_current_a=args.peak_current_a,
            max_temperature_c=args.max_temperature_c,
            visual_pass=args.visual_pass,
            cv_pass=args.cv_pass,
            thermal_pass=args.thermal_pass,
            acoustic_pass=args.acoustic_pass,
            sclk_pass=args.sclk_pass,
            timing_pass=args.timing_pass,
            notes=args.notes,
        )
    else:
        value = validate_physical_result(
            args.result_dir,
            reviewer_key_file=args.reviewer_key,
            require_finalized=not args.allow_pending,
        )
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "N7PhysicalOnceError",
    "N7PhysicalOnceUnknown",
    "describe_physical_action",
    "finalize_physical_result",
    "required_action_authorization",
    "required_panel_confirmation",
    "required_profile_confirmation",
    "run_physical_action_once",
    "validate_physical_result",
]
