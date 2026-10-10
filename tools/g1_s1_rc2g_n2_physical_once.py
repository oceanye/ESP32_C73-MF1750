#!/usr/bin/env python3
"""Execute one action from an exact physical-bound N2P operator bundle.

This runner never accepts the legacy ``UNBOUND-N2P-OFFLINE`` identities.  It
loads the dynamically materialized eight-action campaign, authenticates a
production-reviewed limit profile and all of its source files, consumes the
new workspace-global action claim before network I/O, and delegates only the
already-audited RC2G wire protocol to the legacy implementation.

There is no frame/hash/job override, retry, recovery, or second POST path.
Every non-secret input snapshot used for execution is copied into the result;
the trusted reviewer key is used for validation but is never retained.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
import time
from typing import Any, Callable, Mapping, Optional, Sequence
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.epd_frame import (  # noqa: E402
    FRAME_BYTES,
    controller_stream,
    fnv1a,
    generate_fixture,
    validate_frame,
)
from host.visible_refresh_campaign import (  # noqa: E402
    CLAIM_REGISTRY_ID,
    CLAIM_REGISTRY_RELATIVE_PATH,
    CampaignContractError,
    ResultState,
    build_result_record,
    canonical_json_bytes,
    describe_action_offline,
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
from tools import g1_s1_n2_physical_campaign as physical  # noqa: E402
from tools import g1_s1_rc2g_n2_photo_campaign as frozen  # noqa: E402
from tools import g1_s1_rc2g_n2_photo_campaign_once as legacy  # noqa: E402
from tools.local_path_safety import (  # noqa: E402
    LocalPathSafetyError,
    require_local_regular_path_syntax,
)


SCHEMA_VERSION = 1
RUNNER_KIND = "mf1750-g1-s1-rc2g-n2p-physical-fixed-action-runner"
CLAIM_KIND = "mf1750-g1-s1-rc2g-n2p-physical-action-consumed-claim"
LOCK_KIND = "mf1750-g1-s1-rc2g-n2p-physical-action-lock"
EVIDENCE_KIND = "mf1750-g1-s1-rc2g-n2p-physical-action-evidence"
FINALIZATION_KIND = "mf1750-g1-s1-rc2g-n2p-physical-action-finalization"
DESCRIPTION_KIND = "mf1750-g1-s1-rc2g-n2p-physical-action-description"
VALIDATION_KIND = "mf1750-g1-s1-rc2g-n2p-physical-result-validation"
OBSERVATION_KIND = legacy.OBSERVATION_KIND

LOCK_FILENAME = "ATTEMPT-LOCK.json"
EVIDENCE_FILENAME = "N2P-ACTION-EVIDENCE.json"
OBSERVATION_FILENAME = "N2P-OBSERVATION.json"
FINALIZATION_FILENAME = "N2P-FINALIZATION.json"
P0_RESULT_FILENAME = "P0-ACTION-RESULT.json"
CAMERA_CAPTURE_FILENAME = legacy.CAMERA_CAPTURE_FILENAME

COPIED_OPERATOR_FILENAME = physical.OPERATOR_MANIFEST_FILENAME
COPIED_CAMPAIGN_FILENAME = physical.PHYSICAL_CAMPAIGN_FILENAME
COPIED_SOURCE_MANIFEST_FILENAME = "FROZEN-SOURCE-MANIFEST.json"
COPIED_PANEL_FILENAME = "PHYSICAL-PANEL.json"
COPIED_BINDING_REVIEW_FILENAME = "PANEL-BINDING-REVIEW.bin"
COPIED_PROFILE_FILENAME = "PRODUCTION-LIMIT-PROFILE.json"
COPIED_FIRMWARE_FILENAME = "FIRMWARE.bin"
COPIED_LIMIT_AUTHORITY_FILENAME = "LIMIT-AUTHORITY.json"
# Compatibility alias for callers that imported the pre-policy symbol.  The
# on-disk/result vocabulary is neutral because this file may be an explicitly
# non-supplier supervised experimental process policy.
COPIED_SUPPLIER_FILENAME = COPIED_LIMIT_AUTHORITY_FILENAME
COPIED_USAGE_FILENAME = "USAGE-EVIDENCE.json"
COPIED_PROFILE_REVIEW_FILENAME = "PROFILE-REVIEW-ARTIFACT.json"

ACTION_AUTHORIZATION_PREFIX = (
    "AUTHORIZE_ONE_VISIBLE_RC2G_N2P_PHYSICAL_ACTION__ACTION_"
)
ACTION_AUTHORIZATION_SUFFIX = "__NO_RETRY_NO_RECOVERY"
PANEL_BUILD_CONFIRMATION_PREFIX = "CONFIRM_N2P_PHYSICAL_PANEL__SERIAL_"
PROFILE_CONFIRMATION_PREFIX = "CONFIRM_N2P_APPROVED_PRODUCTION_PROFILE"

MAX_LIVE_EVALUATED_AT_AGE_SECONDS = 300

DEFAULT_CLAIM_REGISTRY = REPO_ROOT / Path(CLAIM_REGISTRY_RELATIVE_PATH)
FIXED_ACTION_KEYS = physical.FIXED_ACTION_KEYS

_MAX_JSON_BYTES = 16 * 1024 * 1024
_MAX_BINDING_REVIEW_BYTES = 64 * 1024 * 1024
_MAX_FIRMWARE_BYTES = 32 * 1024 * 1024
_RFC3339_RE = legacy._RFC3339_RE


class N2PhysicalOnceError(RuntimeError):
    """Raised before the physical action claim is consumed."""


class N2PhysicalOnceUnknown(N2PhysicalOnceError):
    """The new physical action claim exists and the action must not be retried."""


@dataclass(frozen=True)
class _Context:
    action_key: str
    operator: Mapping[str, Any]
    campaign: Mapping[str, Any]
    legacy_snapshot: legacy._ActionSnapshot
    production: ValidatedProductionProfile
    snapshots: Mapping[str, ArtifactSnapshot]

    @property
    def action(self) -> Mapping[str, Any]:
        return self.legacy_snapshot.action


@dataclass(frozen=True)
class _Prior:
    directory: Path
    result: Mapping[str, Any]
    result_sha256: str
    evidence: Mapping[str, Any]
    observation: Mapping[str, Any]
    finalization: Mapping[str, Any]
    context: _Context

    def legacy_bundle(self) -> legacy._PriorBundle:
        return legacy._PriorBundle(
            self.result,
            self.result_sha256,
            self.evidence,
            self.observation,
            self.finalization,
        )


@dataclass(frozen=True)
class _Claim:
    filename: str
    record: Mapping[str, Any]
    payload: bytes

    def reference(self) -> dict[str, Any]:
        return {
            "registry_id": CLAIM_REGISTRY_ID,
            "filename": self.filename,
            "file_sha256": _sha256(self.payload),
            "attempt_id": self.record["attempt_id"],
            "action_identity_sha256": self.record["action_identity_sha256"],
            "state": self.record["state"],
        }


@dataclass(frozen=True)
class _StoredValidation:
    directory: Path
    context: _Context
    evidence: Mapping[str, Any]
    evidence_payload: bytes
    result: Optional[Mapping[str, Any]]
    result_payload: Optional[bytes]
    observation: Optional[Mapping[str, Any]]
    observation_payload: Optional[bytes]
    finalization: Optional[Mapping[str, Any]]
    finalization_payload: Optional[bytes]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _temperature(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise N2PhysicalOnceError(f"{label} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized) or not -50 <= normalized <= 100:
        raise N2PhysicalOnceError(f"{label} is outside the valid measurement range")
    return normalized


def _rfc3339(value: object, *, label: str) -> datetime:
    if not isinstance(value, str) or _RFC3339_RE.fullmatch(value) is None:
        raise N2PhysicalOnceError(f"{label} must be timezone-aware RFC3339")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise N2PhysicalOnceError(f"{label} is not valid RFC3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise N2PhysicalOnceError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _reject_reparse_path_chain(path: Path, *, label: str) -> None:
    try:
        lexical = path.absolute()
    except OSError as error:
        raise N2PhysicalOnceError(f"{label} cannot be made absolute: {error}") from error
    for component in [*reversed(lexical.parents), lexical]:
        try:
            status = os.lstat(component)
        except FileNotFoundError:
            continue
        except OSError as error:
            raise N2PhysicalOnceError(
                f"{label} path component cannot be inspected: {error}"
            ) from error
        attributes = getattr(status, "st_file_attributes", 0)
        reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
        if stat.S_ISLNK(status.st_mode) or attributes & reparse_point:
            raise N2PhysicalOnceError(
                f"{label} leaf and ancestors must not be a symlink or reparse point"
            )


def _safe_result_directory(path: Path, *, must_exist: bool) -> Path:
    label = "physical N2P result directory"
    try:
        require_local_regular_path_syntax(path, label=label)
    except LocalPathSafetyError as error:
        raise N2PhysicalOnceError(str(error)) from error
    _reject_reparse_path_chain(path if must_exist else path.parent, label=label)
    if must_exist:
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise N2PhysicalOnceError(f"{label} does not exist: {error}") from error
        if path.is_symlink() or not resolved.is_dir():
            raise N2PhysicalOnceError(f"{label} must be a real local directory")
        return resolved
    if os.path.lexists(path):
        raise N2PhysicalOnceError("result directory already exists; refusing replay")
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as error:
        raise N2PhysicalOnceError(f"invalid result directory parent: {error}") from error
    if not parent.is_dir():
        raise N2PhysicalOnceError("result parent must be a real directory")
    return parent / path.name


def _parse_json_snapshot(snapshot: ArtifactSnapshot, *, label: str) -> Mapping[str, Any]:
    def reject_constant(token: str) -> None:
        raise ValueError(f"forbidden JSON constant {token}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate key {key!r}")
            value[key] = item
        return value

    try:
        value = json.loads(
            snapshot.payload.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise N2PhysicalOnceError(f"{label} is not strict UTF-8 JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise N2PhysicalOnceError(f"{label} root must be an object")
    if snapshot.payload != canonical_json_bytes(value):
        raise N2PhysicalOnceError(f"{label} must use canonical JSON bytes")
    return value


def _read_snapshot(path: Path, *, label: str, maximum_bytes: int) -> ArtifactSnapshot:
    try:
        return read_local_regular_file(path, label=label, maximum_bytes=maximum_bytes)
    except ProductionProfileError as error:
        raise N2PhysicalOnceError(str(error)) from error


def required_action_authorization(action_identity_sha256: str) -> str:
    if (
        not isinstance(action_identity_sha256, str)
        or len(action_identity_sha256) != 64
        or any(character not in "0123456789abcdef" for character in action_identity_sha256)
    ):
        raise N2PhysicalOnceError("physical action identity SHA-256 is invalid")
    if action_identity_sha256 in legacy.FIXED_ACTION_SHA256S.values():
        raise N2PhysicalOnceError("legacy UNBOUND action identity is forbidden")
    return (
        f"{ACTION_AUTHORIZATION_PREFIX}{action_identity_sha256.upper()}"
        f"{ACTION_AUTHORIZATION_SUFFIX}"
    )


def required_panel_build_confirmation(
    panel_serial: str, build_tag: str, binding_sha256: str
) -> str:
    for value, label in (
        (panel_serial, "panel serial"),
        (build_tag, "build tag"),
        (binding_sha256, "binding SHA-256"),
    ):
        if not isinstance(value, str) or not value or value != value.strip():
            raise N2PhysicalOnceError(f"{label} is invalid")
    return (
        f"{PANEL_BUILD_CONFIRMATION_PREFIX}{panel_serial}"
        f"__BUILD_TAG_{build_tag}__BINDING_{binding_sha256.upper()}"
    )


def required_production_profile_confirmation(
    profile_canonical_sha256: str,
    profile_file_sha256: str,
    review_artifact_file_sha256: str,
    reviewer_key_id: str,
    usage_evidence_file_sha256: str,
    limit_authority_file_sha256: str,
) -> str:
    hashes = (
        (profile_canonical_sha256, "profile canonical SHA-256"),
        (profile_file_sha256, "profile file SHA-256"),
        (review_artifact_file_sha256, "review artifact SHA-256"),
        (usage_evidence_file_sha256, "usage evidence SHA-256"),
        (limit_authority_file_sha256, "limit authority SHA-256"),
    )
    for value, label in hashes:
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise N2PhysicalOnceError(f"{label} is invalid")
    if (
        not isinstance(reviewer_key_id, str)
        or not reviewer_key_id
        or reviewer_key_id != reviewer_key_id.strip()
    ):
        raise N2PhysicalOnceError("reviewer key id is invalid")
    return (
        f"{PROFILE_CONFIRMATION_PREFIX}"
        f"__PROFILE_CANONICAL_{profile_canonical_sha256.upper()}"
        f"__PROFILE_FILE_{profile_file_sha256.upper()}"
        f"__REVIEW_ARTIFACT_FILE_{review_artifact_file_sha256.upper()}"
        f"__REVIEWER_KEY_ID_{reviewer_key_id}"
        f"__USAGE_FILE_{usage_evidence_file_sha256.upper()}"
        f"__LIMIT_AUTHORITY_FILE_{limit_authority_file_sha256.upper()}"
    )


def _profile_confirmation(context: _Context) -> str:
    review = context.production.review_artifact_file
    reviewer_key_id = context.production.reviewer_key_id
    if review is None or reviewer_key_id is None:
        raise N2PhysicalOnceError("approved production review snapshots are incomplete")
    return required_production_profile_confirmation(
        str(context.production.profile["integrity"]["canonical_sha256"]),
        context.production.profile_file.sha256,
        review.sha256,
        reviewer_key_id,
        context.production.inputs.usage_evidence_file.sha256,
        context.production.inputs.limit_authority_file.sha256,
    )


def _validate_live_evaluation_time(evaluated_at: str, live_now: str) -> float:
    evaluated = _rfc3339(evaluated_at, label="live profile evaluated_at")
    current = _rfc3339(live_now, label="live execution current time")
    age_seconds = (current - evaluated).total_seconds()
    if age_seconds < 0:
        raise N2PhysicalOnceError("live profile evaluated_at must not be in the future")
    if age_seconds > MAX_LIVE_EVALUATED_AT_AGE_SECONDS:
        raise N2PhysicalOnceError(
            "live profile evaluated_at is too old; revalidate immediately before execution"
        )
    return age_seconds


def _runtime_schedule_decision(
    context: _Context, *, evaluated_at: str
) -> dict[str, Any]:
    """Evaluate materialized action/session timing against the latest usage state."""

    now = _rfc3339(evaluated_at, label="runtime schedule evaluated_at")
    action = context.action
    identity = action["identity"]
    profile = context.production.profile
    usage = profile["usage"]
    limits = profile["limits"]
    sessions = [
        session
        for session in context.campaign["sessions"]
        if action["action_identity_sha256"] in session["action_identity_sha256s"]
    ]
    if len(sessions) != 1:
        raise N2PhysicalOnceError("physical action is not in exactly one session")
    session = sessions[0]
    action_minimum = identity["schedule"][
        "minimum_interval_since_prior_seconds"
    ]
    authority_minimum = limits["minimum_interval_seconds"]
    planned_cooldown = session["planned_cooldown_seconds"]
    authority_cooldown = limits["minimum_cooldown_seconds"]
    effective_interval = max(action_minimum, authority_minimum)
    effective_cooldown = max(planned_cooldown, authority_cooldown)
    cumulative_count = usage["cumulative_visible_refresh_count"]
    session_count = usage["session_visible_refresh_count"]
    interval_required = identity["prior"] is not None
    cooldown_required = (
        identity["prior"] is None
        and cumulative_count > 0
        and session_count == 0
    )
    last_visible_value = usage["last_visible_refresh_completed_at"]
    last_visible = (
        None
        if last_visible_value is None
        else _rfc3339(
            last_visible_value,
            label="runtime schedule last_visible_refresh_completed_at",
        )
    )
    elapsed_seconds = (
        None if last_visible is None else (now - last_visible).total_seconds()
    )
    blockers: list[str] = []
    if interval_required:
        if elapsed_seconds is None or elapsed_seconds < effective_interval:
            blockers.append("materialized_action_interval_not_elapsed")
    if cooldown_required:
        if elapsed_seconds is None or elapsed_seconds < effective_cooldown:
            blockers.append("materialized_session_cooldown_not_elapsed")
    return {
        "evaluated_at": evaluated_at,
        "last_visible_refresh_completed_at": last_visible_value,
        "elapsed_since_last_visible_refresh_seconds": elapsed_seconds,
        "action_interval_required": interval_required,
        "action_identity_minimum_interval_seconds": action_minimum,
        "limit_authority_minimum_interval_seconds": authority_minimum,
        "effective_minimum_interval_seconds": effective_interval,
        "session_cooldown_required": cooldown_required,
        "operator_planned_cooldown_seconds": planned_cooldown,
        "limit_authority_minimum_cooldown_seconds": authority_cooldown,
        "effective_minimum_cooldown_seconds": effective_cooldown,
        "ready": not blockers,
        "blockers": blockers,
    }


def _action_allowlist(campaign: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = []
    for action in campaign["actions"]:
        identity = action["identity"]
        result.append(
            {
                "action_id": identity["action_id"],
                "action_identity_sha256": action["action_identity_sha256"],
                "method": identity["request"]["method"],
                "endpoint": identity["request"]["endpoint"],
                "frame_sha256": identity["frame"]["sha256"],
                "maximum_uses": 1,
            }
        )
    return result


def _frame_snapshot(
    operator: Mapping[str, Any],
    source: Mapping[str, Any],
    action_key: str,
) -> legacy._ActionSnapshot:
    campaign = operator["physical_campaign_contract"]
    if action_key not in operator["fixed_actions"] or action_key not in FIXED_ACTION_KEYS:
        raise N2PhysicalOnceError("action_key is not one of the materialized eight actions")
    action_sha = operator["fixed_actions"][action_key]
    matches = [
        action
        for action in campaign["actions"]
        if action["action_identity_sha256"] == action_sha
    ]
    if len(matches) != 1:
        raise N2PhysicalOnceError("selected physical action is not unique")
    action = matches[0]
    if action_sha in legacy.FIXED_ACTION_SHA256S.values():
        raise N2PhysicalOnceError("physical action reused a legacy UNBOUND identity")
    cell_id = action["identity"]["cell_id"]
    cells = [cell for cell in source["cells"] if cell["cell_id"] == cell_id]
    if len(cells) != 1:
        raise N2PhysicalOnceError("selected source candidate cell is not unique")
    cell = cells[0]
    phase = action["identity"]["phase"]
    if phase == "map-primer":
        frame = generate_fixture(frozen.MAP_FIXTURE)
        reference_preview = {
            "kind": "map_fixture_frame",
            "workspace_relative_path": None,
            "sha256": frozen.MAP_FRAME_SHA256,
        }
    elif phase == "target":
        relative = cell["candidate"]["artifact"]["workspace_relative_directory"]
        frame_path = REPO_ROOT / Path(relative) / "frame.bin"
        frame_file = _read_snapshot(
            frame_path, label="frozen physical target frame", maximum_bytes=FRAME_BYTES
        )
        frame = frame_file.payload
        reference_preview = {
            "kind": "strict_final_png",
            "workspace_relative_path": f"{relative}/final.png",
            "sha256": cell["candidate"]["previews"]["final"]["sha256"],
        }
    else:
        raise N2PhysicalOnceError("physical action phase is invalid")
    try:
        validate_frame(frame)
    except ValueError as error:
        raise N2PhysicalOnceError(f"physical action frame is invalid: {error}") from error
    frame_record = action["identity"]["frame"]
    controllers = []
    for mapping in legacy._quality.FIXED_CONTROLLER_MAPPINGS:
        stream = controller_stream(frame, mapping)
        controllers.append((_sha256(stream), f"0x{fnv1a(stream):08X}"))
    if (
        _sha256(frame) != frame_record["sha256"]
        or f"0x{fnv1a(frame):08X}" != frame_record["fnv1a"]
        or controllers
        != [
            (controller["dtm_sha256"], controller["dtm_fnv1a"])
            for controller in frame_record["controllers"]
        ]
    ):
        raise N2PhysicalOnceError("physical action frame/DTM identity changed")
    snapshot = legacy._ActionSnapshot(
        key=action_key,
        cell_id=cell_id,
        phase=phase,
        action=action,
        campaign=campaign,
        outer_manifest=operator,
        cell=cell,
        frame=frame,
        reference_preview=reference_preview,
    )
    try:
        legacy._fixed_execution_spec(snapshot)
    except (CampaignContractError, legacy.N2PFixedActionError) as error:
        raise N2PhysicalOnceError(f"physical execution spec is invalid: {error}") from error
    return snapshot


def _validate_source_snapshot(snapshot: ArtifactSnapshot) -> Mapping[str, Any]:
    source = _parse_json_snapshot(snapshot, label="frozen source manifest snapshot")
    try:
        frozen.validate_compiled_manifest(source)
    except frozen.N2PhotoCampaignError as error:
        raise N2PhysicalOnceError(f"frozen source snapshot is invalid: {error}") from error
    if (
        snapshot.sha256 != physical.SOURCE_OUTER_FILE_SHA256
        or source["manifest_integrity"]["canonical_sha256"]
        != physical.SOURCE_OUTER_CANONICAL_SHA256
    ):
        raise N2PhysicalOnceError("frozen source snapshot identity changed")
    return source


def _load_live_context(
    action_key: str,
    *,
    bundle_dir: Path,
    source_manifest_file: Path,
    panel_file: Path,
    binding_review_artifact_file: Path,
    profile_file: Path,
    firmware_binary_file: Path,
    supplier_limits_file: Path,
    usage_evidence_file: Path,
    profile_review_artifact_file: Path,
    reviewer_key_file: Path,
    evaluated_at: str,
) -> _Context:
    source_snapshot = _read_snapshot(
        source_manifest_file,
        label="frozen source manifest input",
        maximum_bytes=_MAX_JSON_BYTES,
    )
    panel_snapshot = _read_snapshot(
        panel_file, label="physical panel input", maximum_bytes=_MAX_JSON_BYTES
    )
    binding_snapshot = _read_snapshot(
        binding_review_artifact_file,
        label="panel binding review input",
        maximum_bytes=_MAX_BINDING_REVIEW_BYTES,
    )
    try:
        operator = physical.validate_physical_bundle(
            bundle_dir,
            source_manifest_file,
            panel_file,
            binding_review_artifact_file,
        )
    except physical.N2PhysicalCampaignError as error:
        raise N2PhysicalOnceError(f"physical bundle validation failed: {error}") from error
    campaign_path, operator_path = physical._bundle_paths(bundle_dir)
    operator_snapshot = _read_snapshot(
        operator_path, label="physical operator manifest", maximum_bytes=_MAX_JSON_BYTES
    )
    operator_value = _parse_json_snapshot(
        operator_snapshot, label="physical operator manifest"
    )
    if operator_value != operator:
        raise N2PhysicalOnceError("physical operator changed after bundle validation")
    if operator["physical_binding"]["binding_review_artifact"] != physical._review_artifact_record(
        binding_snapshot.payload
    ):
        raise N2PhysicalOnceError("binding review snapshot differs from operator binding")
    source = _validate_source_snapshot(source_snapshot)
    panel = _parse_json_snapshot(panel_snapshot, label="physical panel snapshot")
    if panel != operator["physical_binding"]["panel"]:
        raise N2PhysicalOnceError("physical panel snapshot differs from operator binding")
    try:
        production = load_validated_production_profile(
            profile_file=profile_file,
            campaign_file=campaign_path,
            firmware_binary_file=firmware_binary_file,
            supplier_limits_file=supplier_limits_file,
            usage_evidence_file=usage_evidence_file,
            review_artifact_file=profile_review_artifact_file,
            reviewer_key_file=reviewer_key_file,
            evaluated_at=evaluated_at,
        )
    except ProductionProfileError as error:
        raise N2PhysicalOnceError(f"production profile validation failed: {error}") from error
    if (
        production.report["approved"] is not True
        or production.report["production_ready"] is not True
        or production.profile["review"]["approved"] is not True
        or production.inputs.campaign != operator["physical_campaign_contract"]
        or production.inputs.campaign_file.payload
        != canonical_json_bytes(operator["physical_campaign_contract"])
        or operator["physical_campaign_file"]
        != physical._physical_campaign_file_record(production.inputs.campaign)
        or production.profile["panel"] != production.inputs.campaign["panel"]
        or production.profile["firmware"] != production.inputs.campaign["firmware"]
        or production.profile["action_allowlist"]
        != _action_allowlist(production.inputs.campaign)
        or production.report["action_allowlist_count"] != 8
    ):
        raise N2PhysicalOnceError(
            "approved production profile is not ready for the exact physical campaign"
        )
    if production.review_artifact_file is None or production.reviewer_key_id is None:
        raise N2PhysicalOnceError("approved production review snapshots are incomplete")
    snapshots = {
        COPIED_OPERATOR_FILENAME: operator_snapshot,
        COPIED_CAMPAIGN_FILENAME: production.inputs.campaign_file,
        COPIED_SOURCE_MANIFEST_FILENAME: source_snapshot,
        COPIED_PANEL_FILENAME: panel_snapshot,
        COPIED_BINDING_REVIEW_FILENAME: binding_snapshot,
        COPIED_PROFILE_FILENAME: production.profile_file,
        COPIED_FIRMWARE_FILENAME: production.inputs.firmware_binary,
        COPIED_SUPPLIER_FILENAME: production.inputs.limit_authority_file,
        COPIED_USAGE_FILENAME: production.inputs.usage_evidence_file,
        COPIED_PROFILE_REVIEW_FILENAME: production.review_artifact_file,
    }
    return _Context(
        action_key=action_key,
        operator=operator,
        campaign=production.inputs.campaign,
        legacy_snapshot=_frame_snapshot(operator, source, action_key),
        production=production,
        snapshots=snapshots,
    )


def _snapshot_records(snapshots: Mapping[str, ArtifactSnapshot]) -> dict[str, Any]:
    return {
        filename: {
            "bytes": len(snapshot.payload),
            "sha256": snapshot.sha256,
        }
        for filename, snapshot in snapshots.items()
    }


def _prepare_result_destination(path: Path) -> Path:
    destination = _safe_result_directory(path, must_exist=False)
    try:
        workspace = REPO_ROOT.resolve(strict=True)
        registry_parent = DEFAULT_CLAIM_REGISTRY.parent.resolve(strict=True)
    except OSError as error:
        raise N2PhysicalOnceError(f"workspace path validation failed: {error}") from error
    if not _is_within(registry_parent, workspace):
        raise N2PhysicalOnceError("claim registry parent escaped the workspace")
    return destination


def _claim_registry() -> Path:
    path = DEFAULT_CLAIM_REGISTRY
    try:
        require_local_regular_path_syntax(path, label="physical action claim registry")
    except LocalPathSafetyError as error:
        raise N2PhysicalOnceError(str(error)) from error
    _reject_reparse_path_chain(path, label="physical action claim registry")
    try:
        parent = path.parent.resolve(strict=True)
        workspace = REPO_ROOT.resolve(strict=True)
        if not parent.is_dir() or not _is_within(parent, workspace):
            raise N2PhysicalOnceError("physical claim registry parent escaped workspace")
        path.mkdir(exist_ok=True)
        _reject_reparse_path_chain(path, label="physical action claim registry")
        registry = path.resolve(strict=True)
    except N2PhysicalOnceError:
        raise
    except OSError as error:
        raise N2PhysicalOnceError(f"could not prepare physical claim registry: {error}") from error
    if path.is_symlink() or not registry.is_dir() or not _is_within(registry, workspace):
        raise N2PhysicalOnceError("physical claim registry escaped workspace")
    return registry


def _atomic_commit(path: Path, payload: bytes, *, unknown_after_commit: bool) -> None:
    temporary = path.parent / f".{path.name}.tmp-{uuid.uuid4().hex}"
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        temporary.unlink(missing_ok=True)
    except FileExistsError as error:
        if unknown_after_commit:
            raise N2PhysicalOnceUnknown(
                f"{path.name} already exists; physical action is permanently consumed"
            ) from error
        raise N2PhysicalOnceError(f"{path.name} already exists; refusing overwrite") from error
    except OSError as error:
        if unknown_after_commit:
            raise N2PhysicalOnceUnknown(
                f"atomic state of {path.name} is uncertain; do not retry"
            ) from error
        raise N2PhysicalOnceError(f"could not atomically commit {path.name}: {error}") from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _write_json(directory: Path, filename: str, value: Mapping[str, Any]) -> str:
    payload = canonical_json_bytes(value)
    _atomic_commit(directory / filename, payload, unknown_after_commit=False)
    return _sha256(payload)


def _claim_action(
    context: _Context,
    *,
    attempt_id: str,
    claimed_at: str,
    destination: Path,
    prior: Optional[_Prior],
    start_temperature_c: float,
    confirmations: Mapping[str, bool],
    authorization_confirmation: str,
    panel_build_confirmation: str,
    profile_confirmation: str,
    profile_evaluated_at: str,
    live_evaluation_age_seconds: float,
    runtime_schedule_decision: Mapping[str, Any],
) -> _Claim:
    action = context.action
    declaration = action["claim"]
    action_sha = action["action_identity_sha256"]
    if (
        action_sha in legacy.FIXED_ACTION_SHA256S.values()
        or declaration["registry_id"] != CLAIM_REGISTRY_ID
        or declaration["workspace_relative_registry"]
        != CLAIM_REGISTRY_RELATIVE_PATH
        or declaration["filename"] != f"{action_sha}.json"
        or declaration["create_before_network"] is not True
        or declaration["overridable"] is not False
    ):
        raise N2PhysicalOnceError("physical workspace-global claim declaration changed")
    registry = _claim_registry()
    if _is_within(destination, registry):
        raise N2PhysicalOnceError("result directory must not overlap the claim registry")
    record = {
        "schema_version": SCHEMA_VERSION,
        "kind": CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "action_key": context.action_key,
        "action_identity_sha256": action_sha,
        "operator_manifest_canonical_sha256": context.operator["integrity"][
            "canonical_sha256"
        ],
        "operator_manifest_file_sha256": context.snapshots[
            COPIED_OPERATOR_FILENAME
        ].sha256,
        "physical_binding_canonical_sha256": context.operator["physical_binding"][
            "integrity"
        ]["canonical_sha256"],
        "campaign_canonical_sha256": context.campaign["integrity"][
            "canonical_sha256"
        ],
        "campaign_file_sha256": context.production.inputs.campaign_file.sha256,
        "profile_canonical_sha256": context.production.profile["integrity"][
            "canonical_sha256"
        ],
        "profile_file_sha256": context.production.profile_file.sha256,
        "firmware_binary_sha256": context.production.inputs.firmware_binary.sha256,
        "limit_authority_file_sha256": context.production.inputs.limit_authority_file.sha256,
        "usage_evidence_file_sha256": context.production.inputs.usage_evidence_file.sha256,
        "profile_review_artifact_file_sha256": context.production.review_artifact_file.sha256,
        "reviewer_key_id": context.production.reviewer_key_id,
        "attempt_id": attempt_id,
        "claimed_at": claimed_at,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "authorization_consumed_permanently": True,
        "authorization_confirmation_sha256": _sha256(
            authorization_confirmation.encode("utf-8")
        ),
        "panel_build_confirmation_sha256": _sha256(
            panel_build_confirmation.encode("utf-8")
        ),
        "profile_confirmation_sha256": _sha256(
            profile_confirmation.encode("utf-8")
        ),
        "profile_evaluated_at": profile_evaluated_at,
        "live_evaluation_age_seconds": live_evaluation_age_seconds,
        "maximum_live_evaluation_age_seconds": (
            MAX_LIVE_EVALUATED_AT_AGE_SECONDS
        ),
        "runtime_schedule_decision": dict(runtime_schedule_decision),
        "prior_result_file_sha256": prior.result_sha256 if prior else None,
        "start_temperature_c": start_temperature_c,
        "confirmations": dict(confirmations),
        "result_directory": str(destination),
        "maximum_post_requests": 1,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
    }
    payload = canonical_json_bytes(record)
    filename = declaration["filename"]
    _atomic_commit(registry / filename, payload, unknown_after_commit=True)
    return _Claim(filename, record, payload)


def _copy_snapshots(context: _Context, destination: Path) -> None:
    for filename, snapshot in context.snapshots.items():
        _atomic_commit(
            destination / filename, snapshot.payload, unknown_after_commit=False
        )


def _validate_claim_reference(
    action_identity_sha256: str, reference: object
) -> Mapping[str, Any]:
    expected_filename = f"{action_identity_sha256}.json"
    if (
        not isinstance(reference, Mapping)
        or reference.get("registry_id") != CLAIM_REGISTRY_ID
        or reference.get("filename") != expected_filename
        or reference.get("action_identity_sha256") != action_identity_sha256
        or reference.get("state")
        != "authorization_permanently_consumed_do_not_rerun"
    ):
        raise N2PhysicalOnceError("stored physical claim reference is invalid")
    registry = _claim_registry()
    claim_snapshot = _read_snapshot(
        registry / expected_filename,
        label="consumed physical workspace-global claim",
        maximum_bytes=_MAX_JSON_BYTES,
    )
    record = _parse_json_snapshot(
        claim_snapshot, label="consumed physical workspace-global claim"
    )
    if (
        claim_snapshot.sha256 != reference.get("file_sha256")
        or record.get("kind") != CLAIM_KIND
        or record.get("action_identity_sha256") != action_identity_sha256
        or record.get("attempt_id") != reference.get("attempt_id")
        or record.get("state") != reference.get("state")
    ):
        raise N2PhysicalOnceError("consumed physical claim bytes changed")
    return record


def _expected_confirmation_keys(phase: str) -> set[str]:
    common = {
        "supervised_supply_cv_current_normal",
        "physical_cutoff_available",
        "single_visible_refresh",
    }
    if phase == "map-primer":
        return common | {"controller_fresh_boot"}
    if phase == "target":
        return common | {
            "map_fidelity_from_same_cell_primer",
            "esp32_not_restarted_since_primer",
            "no_j2_disconnect_since_primer",
            "no_panel_power_cycle_since_primer",
            "no_other_visible_refresh_since_primer",
        }
    raise N2PhysicalOnceError("physical action phase is invalid")


def _validate_request_audit(value: object, *, frame_sha256: str) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "post_attempt_count",
        "post_issued_count",
        "calls",
    }:
        raise N2PhysicalOnceError("stored request audit fields changed")
    calls = value["calls"]
    if (
        value["post_attempt_count"] != 1
        or value["post_issued_count"] != 1
        or not isinstance(calls, list)
        or not calls
    ):
        raise N2PhysicalOnceError("stored request audit is not exactly one POST")
    allowed = {
        ("GET", "/api/version"),
        ("GET", "/api/job"),
        ("GET", "/api/diagnostic/report"),
        ("GET", "/api/diagnostic/status"),
        ("POST", "/api/frame"),
    }
    post_calls = 0
    for index, call in enumerate(calls, start=1):
        if not isinstance(call, Mapping):
            raise N2PhysicalOnceError("stored request audit call is not an object")
        method = call.get("method")
        endpoint = call.get("endpoint")
        if call.get("outcome") == "exception":
            error = call.get("error")
            exception_keys = {
                "index",
                "method",
                "endpoint",
                "timeout_seconds",
                "request_bytes",
                "outcome",
                "error",
            }
            if (
                set(call) != exception_keys
                or call.get("index") != index
                or (method, endpoint) != ("GET", "/api/job")
                or call.get("request_bytes") != 0
                or isinstance(call.get("timeout_seconds"), bool)
                or not isinstance(call.get("timeout_seconds"), (int, float))
                or not math.isfinite(float(call["timeout_seconds"]))
                or call["timeout_seconds"] <= 0
                or not isinstance(error, Mapping)
                or set(error) != {"type", "message"}
                or error.get("type") != "FrameToolNetworkError"
                or not isinstance(error.get("message"), str)
                or not error["message"].startswith("GET /api/job failed: ")
                or len(error["message"]) > 4096
            ):
                raise N2PhysicalOnceError("stored request audit exception changed")
            continue
        expected_keys = {
            "index",
            "method",
            "endpoint",
            "timeout_seconds",
            "request_bytes",
            "outcome",
            "status",
            "response_bytes",
            "response_sha256",
        }
        if method == "POST":
            expected_keys.add("request_sha256")
        if (
            set(call) != expected_keys
            or call.get("index") != index
            or (method, endpoint) not in allowed
            or call.get("outcome") != "response"
            or type(call.get("status")) is not int
            or not 100 <= call["status"] <= 599
            or type(call.get("response_bytes")) is not int
            or call["response_bytes"] < 0
            or not _is_sha256(call.get("response_sha256"))
            or isinstance(call.get("timeout_seconds"), bool)
            or not isinstance(call.get("timeout_seconds"), (int, float))
            or not math.isfinite(float(call["timeout_seconds"]))
            or call["timeout_seconds"] <= 0
        ):
            raise N2PhysicalOnceError("stored request audit call changed")
        if method == "POST":
            post_calls += 1
            if (
                call.get("request_bytes") != FRAME_BYTES
                or call.get("request_sha256") != frame_sha256
            ):
                raise N2PhysicalOnceError("stored POST does not bind the frozen frame")
        elif call.get("request_bytes") != 0:
            raise N2PhysicalOnceError("stored GET unexpectedly carried request bytes")
    if post_calls != 1:
        raise N2PhysicalOnceError("stored request audit contains an extra/missing POST")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_map_protocol(
    snapshot: legacy._ActionSnapshot, protocol: object
) -> None:
    if not isinstance(protocol, Mapping) or set(protocol) != {
        "fresh_boot_preflight",
        "completed_map_evidence",
    }:
        raise N2PhysicalOnceError("stored MAP protocol fields changed")
    fresh = protocol["fresh_boot_preflight"]
    if not isinstance(fresh, Mapping) or set(fresh) != {
        "version",
        "job_raw",
        "diagnostic_raw",
        "gpio_status_raw",
        "busy_after_rst_low_is_informational",
    }:
        raise N2PhysicalOnceError("stored MAP fresh-boot proof fields changed")
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
    expected_diagnostic = {
        "schema_version": 2,
        "valid": False,
        "error": "no_completed_job_report",
    }
    try:
        legacy._map._validate_version(fresh["version"], label="stored MAP fresh boot")
        gpio = legacy._map._validate_gpio_snapshot(
            fresh["gpio_status_raw"], label="stored MAP fresh-boot GPIO"
        )
        completed = protocol["completed_map_evidence"]
        if not isinstance(completed, Mapping):
            raise N2PhysicalOnceError("stored completed MAP proof is missing")
        rebuilt = legacy._map._validate_completed_map_evidence(
            completed.get("network_report"),
            completed.get("job_raw"),
            completed.get("diagnostic_raw"),
            completed.get("gpio_status_raw"),
            snapshot.frame,
        )
    except N2PhysicalOnceError:
        raise
    except Exception as error:
        raise N2PhysicalOnceError(f"stored MAP protocol is invalid: {error}") from error
    if (
        fresh["job_raw"] != expected_job
        or fresh["diagnostic_raw"] != expected_diagnostic
        or fresh["gpio_status_raw"] != gpio
        or fresh["busy_after_rst_low_is_informational"] is not True
        or rebuilt != completed
    ):
        raise N2PhysicalOnceError("stored MAP protocol does not recompute exactly")


def _validate_target_protocol(
    context: _Context, protocol: object
) -> None:
    required = {
        "same_cell_primer_live_preflight",
        "network_report",
        "target_job_raw",
        "target_diagnostic_raw",
        "target_diagnostic_validated",
        "post_refresh_gpio_status_raw",
    }
    if not isinstance(protocol, Mapping) or set(protocol) != required:
        raise N2PhysicalOnceError("stored target protocol fields changed")
    authorization = required_action_authorization(
        context.action["action_identity_sha256"]
    )
    contract = legacy._target_contract(
        context.legacy_snapshot,
        required_authorization_confirmation_override=authorization,
    )
    prior = protocol["same_cell_primer_live_preflight"]
    if not isinstance(prior, Mapping) or set(prior) != {
        "version",
        "job",
        "diagnostic_raw",
        "nested_busy_trace",
        "gpio",
        "expected_identity",
    }:
        raise N2PhysicalOnceError("stored target prior proof fields changed")
    try:
        legacy._quality._validate_version(prior["version"], label="stored target prior")
        job = prior["job"]
        if not isinstance(job, Mapping) or set(job) != {
            "job_id",
            "action",
            "state",
            "result",
            "queued_at_ms",
            "started_at_ms",
            "finished_at_ms",
            "frame_fnv1a",
        }:
            raise N2PhysicalOnceError("stored target prior job fields changed")
        state = legacy._quality._validate_job(
            job,
            contract.expected_prior_job_id,
            contract.expected_prior_frame_fnv1a,
        )
        trace = legacy._quality._validate_prior_raw_diagnostic(
            prior["diagnostic_raw"], job, contract
        )
        gpio_evidence = prior["gpio"]
        if not isinstance(gpio_evidence, Mapping):
            raise N2PhysicalOnceError("stored target prior GPIO proof is missing")
        gpio = legacy._quality._validate_gpio_snapshot(
            gpio_evidence.get("raw"), label="stored target prior GPIO"
        )
        expected_gpio = legacy._quality._gpio_evidence(gpio)
        report = protocol["network_report"]
        legacy._quality._validate_network_report(report, contract)
        raw_job = protocol["target_job_raw"]
        if not isinstance(report, Mapping) or raw_job != report.get("job"):
            raise N2PhysicalOnceError("stored target immutable job changed")
        normalized = legacy._quality._validate_target_raw_diagnostic(
            protocol["target_diagnostic_raw"], report, contract
        )
        post_gpio = legacy._quality._validate_gpio_snapshot(
            protocol["post_refresh_gpio_status_raw"],
            label="stored target post-refresh GPIO",
        )
    except N2PhysicalOnceError:
        raise
    except Exception as error:
        raise N2PhysicalOnceError(f"stored target protocol is invalid: {error}") from error
    if (
        state != "completed"
        or trace != prior["nested_busy_trace"]
        or expected_gpio != gpio_evidence
        or prior["expected_identity"] != context.action["identity"]["prior"]
        or normalized != protocol["target_diagnostic_validated"]
        or post_gpio != protocol["post_refresh_gpio_status_raw"]
    ):
        raise N2PhysicalOnceError("stored target protocol does not recompute exactly")


def _validate_protocol(context: _Context, protocol: object) -> None:
    if context.legacy_snapshot.phase == "map-primer":
        _validate_map_protocol(context.legacy_snapshot, protocol)
    else:
        _validate_target_protocol(context, protocol)


def _load_copied_context(
    directory: Path,
    *,
    action_key: str,
    evaluated_at: str,
    reviewer_key_file: Path,
) -> _Context:
    snapshots = {
        COPIED_OPERATOR_FILENAME: _read_snapshot(
            directory / COPIED_OPERATOR_FILENAME,
            label="copied physical operator",
            maximum_bytes=_MAX_JSON_BYTES,
        ),
        COPIED_CAMPAIGN_FILENAME: _read_snapshot(
            directory / COPIED_CAMPAIGN_FILENAME,
            label="copied physical campaign",
            maximum_bytes=_MAX_JSON_BYTES,
        ),
        COPIED_SOURCE_MANIFEST_FILENAME: _read_snapshot(
            directory / COPIED_SOURCE_MANIFEST_FILENAME,
            label="copied frozen source manifest",
            maximum_bytes=_MAX_JSON_BYTES,
        ),
        COPIED_PANEL_FILENAME: _read_snapshot(
            directory / COPIED_PANEL_FILENAME,
            label="copied physical panel",
            maximum_bytes=_MAX_JSON_BYTES,
        ),
        COPIED_BINDING_REVIEW_FILENAME: _read_snapshot(
            directory / COPIED_BINDING_REVIEW_FILENAME,
            label="copied panel binding review",
            maximum_bytes=_MAX_BINDING_REVIEW_BYTES,
        ),
    }
    operator = _parse_json_snapshot(
        snapshots[COPIED_OPERATOR_FILENAME], label="copied physical operator"
    )
    try:
        physical.validate_physical_manifest(
            operator,
            binding_review_artifact_payload=snapshots[
                COPIED_BINDING_REVIEW_FILENAME
            ].payload,
        )
    except physical.N2PhysicalCampaignError as error:
        raise N2PhysicalOnceError(f"copied physical operator is invalid: {error}") from error
    campaign = _parse_json_snapshot(
        snapshots[COPIED_CAMPAIGN_FILENAME], label="copied physical campaign"
    )
    if (
        campaign != operator["physical_campaign_contract"]
        or operator["physical_campaign_file"]
        != physical._physical_campaign_file_record(campaign)
    ):
        raise N2PhysicalOnceError("copied campaign/operator binding changed")
    source = _validate_source_snapshot(snapshots[COPIED_SOURCE_MANIFEST_FILENAME])
    panel = _parse_json_snapshot(
        snapshots[COPIED_PANEL_FILENAME], label="copied physical panel"
    )
    if panel != campaign["panel"]:
        raise N2PhysicalOnceError("copied physical panel differs from campaign")
    try:
        production = load_validated_production_profile(
            profile_file=directory / COPIED_PROFILE_FILENAME,
            campaign_file=directory / COPIED_CAMPAIGN_FILENAME,
            firmware_binary_file=directory / COPIED_FIRMWARE_FILENAME,
            supplier_limits_file=directory / COPIED_SUPPLIER_FILENAME,
            usage_evidence_file=directory / COPIED_USAGE_FILENAME,
            review_artifact_file=directory / COPIED_PROFILE_REVIEW_FILENAME,
            reviewer_key_file=reviewer_key_file,
            evaluated_at=evaluated_at,
        )
    except ProductionProfileError as error:
        raise N2PhysicalOnceError(f"copied production profile is invalid: {error}") from error
    if (
        production.report["approved"] is not True
        or production.report["production_ready"] is not True
        or production.inputs.campaign != campaign
        or production.profile["action_allowlist"] != _action_allowlist(campaign)
        or production.review_artifact_file is None
        or production.reviewer_key_id is None
    ):
        raise N2PhysicalOnceError("copied production profile is not ready/exact")
    snapshots = {
        **snapshots,
        COPIED_PROFILE_FILENAME: production.profile_file,
        COPIED_FIRMWARE_FILENAME: production.inputs.firmware_binary,
        COPIED_SUPPLIER_FILENAME: production.inputs.limit_authority_file,
        COPIED_USAGE_FILENAME: production.inputs.usage_evidence_file,
        COPIED_PROFILE_REVIEW_FILENAME: production.review_artifact_file,
    }
    return _Context(
        action_key=action_key,
        operator=operator,
        campaign=campaign,
        legacy_snapshot=_frame_snapshot(operator, source, action_key),
        production=production,
        snapshots=snapshots,
    )


def _validate_control_chain(
    directory: Path,
    context: _Context,
    evidence: Mapping[str, Any],
) -> Mapping[str, Any]:
    lock_snapshot = _read_snapshot(
        directory / LOCK_FILENAME,
        label="physical action attempt lock",
        maximum_bytes=_MAX_JSON_BYTES,
    )
    lock = _parse_json_snapshot(lock_snapshot, label="physical action attempt lock")
    action_sha = context.action["action_identity_sha256"]
    authorization_sha = _sha256(
        required_action_authorization(action_sha).encode("utf-8")
    )
    binding_sha = context.operator["physical_binding"]["integrity"][
        "canonical_sha256"
    ]
    panel_sha = _sha256(
        required_panel_build_confirmation(
            str(context.campaign["panel"]["serial"]),
            str(context.campaign["firmware"]["build_tag"]),
            str(binding_sha),
        ).encode("utf-8")
    )
    profile_sha = _sha256(_profile_confirmation(context).encode("utf-8"))
    confirmations = evidence.get("confirmations")
    expected_confirmation_keys = _expected_confirmation_keys(
        context.legacy_snapshot.phase
    )
    if (
        not isinstance(confirmations, Mapping)
        or set(confirmations) != expected_confirmation_keys
        or any(value is not True for value in confirmations.values())
    ):
        raise N2PhysicalOnceError("stored physical confirmations changed")
    expected_lock = {
        "schema_version": SCHEMA_VERSION,
        "kind": LOCK_KIND,
        "attempt_id": evidence.get("attempt_id"),
        "action_key": context.action_key,
        "action_identity_sha256": action_sha,
        "claim": evidence.get("claim"),
        "confirmations": dict(confirmations),
        "authorization_confirmation_sha256": authorization_sha,
        "panel_build_confirmation_sha256": panel_sha,
        "profile_confirmation_sha256": profile_sha,
        "profile_evaluated_at": evidence.get("profile_evaluated_at"),
        "live_evaluation_age_seconds": evidence.get(
            "live_evaluation_age_seconds"
        ),
        "maximum_live_evaluation_age_seconds": (
            MAX_LIVE_EVALUATED_AT_AGE_SECONDS
        ),
        "runtime_schedule_decision": evidence.get(
            "runtime_schedule_decision"
        ),
        "state": "authorization_permanently_consumed_do_not_rerun",
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
    }
    if lock != expected_lock:
        raise N2PhysicalOnceError("physical action attempt lock binding changed")
    claim = _validate_claim_reference(action_sha, evidence.get("claim"))
    review = context.production.review_artifact_file
    if review is None:
        raise N2PhysicalOnceError("copied production review artifact is missing")
    expected_claim = {
        "schema_version": SCHEMA_VERSION,
        "kind": CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "action_key": context.action_key,
        "action_identity_sha256": action_sha,
        "operator_manifest_canonical_sha256": context.operator["integrity"][
            "canonical_sha256"
        ],
        "operator_manifest_file_sha256": context.snapshots[
            COPIED_OPERATOR_FILENAME
        ].sha256,
        "physical_binding_canonical_sha256": binding_sha,
        "campaign_canonical_sha256": context.campaign["integrity"][
            "canonical_sha256"
        ],
        "campaign_file_sha256": context.production.inputs.campaign_file.sha256,
        "profile_canonical_sha256": context.production.profile["integrity"][
            "canonical_sha256"
        ],
        "profile_file_sha256": context.production.profile_file.sha256,
        "firmware_binary_sha256": context.production.inputs.firmware_binary.sha256,
        "limit_authority_file_sha256": (
            context.production.inputs.limit_authority_file.sha256
        ),
        "usage_evidence_file_sha256": (
            context.production.inputs.usage_evidence_file.sha256
        ),
        "profile_review_artifact_file_sha256": review.sha256,
        "reviewer_key_id": context.production.reviewer_key_id,
        "attempt_id": evidence.get("attempt_id"),
        "claimed_at": evidence.get("recorded_at"),
        "state": "authorization_permanently_consumed_do_not_rerun",
        "authorization_consumed_permanently": True,
        "authorization_confirmation_sha256": authorization_sha,
        "panel_build_confirmation_sha256": panel_sha,
        "profile_confirmation_sha256": profile_sha,
        "profile_evaluated_at": evidence.get("profile_evaluated_at"),
        "live_evaluation_age_seconds": evidence.get(
            "live_evaluation_age_seconds"
        ),
        "maximum_live_evaluation_age_seconds": (
            MAX_LIVE_EVALUATED_AT_AGE_SECONDS
        ),
        "runtime_schedule_decision": evidence.get(
            "runtime_schedule_decision"
        ),
        "prior_result_file_sha256": evidence.get("prior_result_file_sha256"),
        "start_temperature_c": evidence.get("start_temperature_c"),
        "confirmations": dict(confirmations),
        "result_directory": str(directory),
        "maximum_post_requests": 1,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
    }
    if claim != expected_claim:
        raise N2PhysicalOnceError("consumed physical claim payload binding changed")
    if (
        evidence.get("authorization_confirmation_sha256") != authorization_sha
        or evidence.get("panel_build_confirmation_sha256") != panel_sha
        or evidence.get("profile_confirmation_sha256") != profile_sha
    ):
        raise N2PhysicalOnceError("stored exact confirmation binding changed")
    return claim


_OBSERVATION_FINALIZER_FIELDS = {
    "visual_pass",
    "electrical_pass",
    "post_refresh_temperature_pass",
    "overall_state",
    "scoring_contract_sha256",
    "camera_observation_contract_sha256",
    "source_observation_file_sha256",
    "verified_camera_evidence",
}


def _raw_stored_observation(observation: Mapping[str, Any]) -> dict[str, Any]:
    if not _OBSERVATION_FINALIZER_FIELDS.issubset(observation):
        raise N2PhysicalOnceError("stored observation finalizer fields are incomplete")
    return {
        key: value
        for key, value in observation.items()
        if key not in _OBSERVATION_FINALIZER_FIELDS
    }


def _validate_finalized_observation(
    directory: Path,
    context: _Context,
    evidence: Mapping[str, Any],
    evidence_sha256: str,
    observation: Mapping[str, Any],
    observation_sha256: str,
    finalization: Mapping[str, Any],
    result: Mapping[str, Any],
) -> None:
    raw = _raw_stored_observation(observation)
    if observation.get("source_observation_file_sha256") != _sha256(
        canonical_json_bytes(raw)
    ):
        raise N2PhysicalOnceError("stored source observation hash changed")
    raw_for_validation = dict(raw)
    raw_camera = raw.get("camera")
    if not isinstance(raw_camera, Mapping):
        raise N2PhysicalOnceError("stored camera observation is missing")
    raw_for_validation["camera"] = dict(raw_camera)
    if raw_for_validation["camera"].get("capture_performed") is True:
        raw_for_validation["camera"]["file"] = CAMERA_CAPTURE_FILENAME
    completed_at = _rfc3339(
        evidence.get("protocol_completed_at"), label="stored protocol_completed_at"
    )
    try:
        (
            visual_pass,
            electrical_pass,
            thermal_pass,
            post_temp,
            camera_payload,
            camera_binding,
        ) = legacy._validate_observation(
            raw_for_validation,
            context.legacy_snapshot,
            context.production.profile,
            camera_base_directory=directory,
            minimum_observed_at=completed_at,
        )
    except legacy.N2PFixedActionError as error:
        raise N2PhysicalOnceError(f"stored physical observation is invalid: {error}") from error
    state = (
        ResultState.PASS.value
        if visual_pass and electrical_pass and thermal_pass
        else ResultState.FAIL.value
    )
    expected_camera_binding: Optional[dict[str, Any]]
    if camera_binding is None:
        expected_camera_binding = None
        if os.path.lexists(directory / CAMERA_CAPTURE_FILENAME):
            raise N2PhysicalOnceError("uncaptured observation gained camera bytes")
    else:
        expected_camera_binding = dict(camera_binding)
        expected_camera_binding[
            "source_path_recorded_but_not_trusted_after_copy"
        ] = raw_camera["file"]
        if camera_payload is None:
            raise N2PhysicalOnceError("captured observation lacks camera bytes")
    expected_observation = {
        **raw,
        "visual_pass": visual_pass,
        "electrical_pass": electrical_pass,
        "post_refresh_temperature_pass": thermal_pass,
        "overall_state": state,
        "scoring_contract_sha256": legacy.SCORING_CONTRACT_SHA256,
        "camera_observation_contract_sha256": (
            legacy.CAMERA_OBSERVATION_CONTRACT_SHA256
        ),
        "source_observation_file_sha256": _sha256(canonical_json_bytes(raw)),
        "verified_camera_evidence": expected_camera_binding,
    }
    if observation != expected_observation:
        raise N2PhysicalOnceError("stored observation verdict does not recompute exactly")
    expected_finalization = {
        "schema_version": SCHEMA_VERSION,
        "kind": FINALIZATION_KIND,
        "action_key": context.action_key,
        "action_identity_sha256": context.action["action_identity_sha256"],
        "state": state,
        "protocol_evidence_file_sha256": evidence_sha256,
        "observation_file_sha256": observation_sha256,
        "profile_file_sha256": context.production.profile_file.sha256,
        "reviewer_key_id": context.production.reviewer_key_id,
        "post_refresh_temperature_c": post_temp,
        "visual_pass": visual_pass,
        "electrical_pass": electrical_pass,
        "post_refresh_temperature_pass": thermal_pass,
        "visual_and_electrical_assessed_separately": True,
        "scoring_contract_sha256": legacy.SCORING_CONTRACT_SHA256,
        "camera_observation_contract_sha256": (
            legacy.CAMERA_OBSERVATION_CONTRACT_SHA256
        ),
        "camera_capture_file_sha256": (
            expected_camera_binding["sha256"]
            if expected_camera_binding is not None
            else None
        ),
        "camera_capture_present_for_this_action": (
            expected_camera_binding is not None
        ),
    }
    if finalization != expected_finalization:
        raise N2PhysicalOnceError("physical finalization does not recompute exactly")
    expected_result = build_result_record(
        action_identity_sha256=context.action["action_identity_sha256"],
        state=ResultState(state),
        completed_at=str(raw["observed_at"]),
        evidence_manifest_sha256=_sha256(canonical_json_bytes(finalization)),
        post_request_count=1,
        details=(
            "physical visual/electrical/thermal PASS recorded independently"
            if state == ResultState.PASS.value
            else "one or more physical visual/electrical/thermal gates failed"
        ),
    )
    if result != expected_result:
        raise N2PhysicalOnceError("terminal physical result does not recompute exactly")


def _validate_stored_result(
    result_dir: Path,
    *,
    reviewer_key_file: Path,
    require_finalized: bool,
) -> _StoredValidation:
    directory = _safe_result_directory(result_dir, must_exist=True)
    evidence_snapshot = _read_snapshot(
        directory / EVIDENCE_FILENAME,
        label="physical action evidence",
        maximum_bytes=_MAX_JSON_BYTES,
    )
    evidence = _parse_json_snapshot(evidence_snapshot, label="physical action evidence")
    if (
        evidence.get("schema_version") != SCHEMA_VERSION
        or evidence.get("kind") != EVIDENCE_KIND
        or evidence.get("action_key") not in FIXED_ACTION_KEYS
        or evidence.get("maximum_post_requests") != 1
        or evidence.get("automatic_retry_count") != 0
        or evidence.get("retry_allowed") is not False
        or evidence.get("recovery_performed") is not False
    ):
        raise N2PhysicalOnceError("physical action evidence identity changed")
    context = _load_copied_context(
        directory,
        action_key=str(evidence["action_key"]),
        evaluated_at=str(evidence["profile_evaluated_at"]),
        reviewer_key_file=reviewer_key_file,
    )
    if (
        evidence.get("action_identity_sha256")
        != context.action["action_identity_sha256"]
        or evidence.get("snapshot_files") != _snapshot_records(context.snapshots)
        or evidence.get("reviewer_key_id") != context.production.reviewer_key_id
        or evidence.get("operator_manifest_canonical_sha256")
        != context.operator["integrity"]["canonical_sha256"]
        or evidence.get("campaign_canonical_sha256")
        != context.campaign["integrity"]["canonical_sha256"]
        or evidence.get("profile_canonical_sha256")
        != context.production.profile["integrity"]["canonical_sha256"]
        or evidence.get("cell_id") != context.legacy_snapshot.cell_id
        or evidence.get("phase") != context.legacy_snapshot.phase
        or evidence.get("frame_sha256")
        != context.action["identity"]["frame"]["sha256"]
        or evidence.get("reference_preview")
        != context.legacy_snapshot.reference_preview
        or evidence.get("profile_file_sha256")
        != context.production.profile_file.sha256
        or evidence.get("campaign_file_sha256")
        != context.production.inputs.campaign_file.sha256
        or evidence.get("scoring_contract_sha256")
        != legacy.SCORING_CONTRACT_SHA256
        or evidence.get("camera_observation_contract_sha256")
        != legacy.CAMERA_OBSERVATION_CONTRACT_SHA256
        or evidence.get("maximum_live_evaluation_age_seconds")
        != MAX_LIVE_EVALUATED_AT_AGE_SECONDS
    ):
        raise N2PhysicalOnceError("physical action evidence snapshot binding changed")
    recorded_at = _rfc3339(evidence.get("recorded_at"), label="claim recorded_at")
    profile_evaluated_at = _rfc3339(
        evidence.get("profile_evaluated_at"), label="profile_evaluated_at"
    )
    live_age = (recorded_at - profile_evaluated_at).total_seconds()
    if (
        live_age < 0
        or live_age > MAX_LIVE_EVALUATED_AT_AGE_SECONDS
        or evidence.get("live_evaluation_age_seconds") != live_age
    ):
        raise N2PhysicalOnceError("stored live profile evaluation time binding changed")
    expected_runtime_schedule = _runtime_schedule_decision(
        context, evaluated_at=str(evidence.get("recorded_at"))
    )
    if (
        evidence.get("runtime_schedule_decision") != expected_runtime_schedule
        or expected_runtime_schedule["ready"] is not True
    ):
        raise N2PhysicalOnceError("stored runtime schedule decision changed")
    if context.legacy_snapshot.phase == "map-primer":
        if evidence.get("prior_result_file_sha256") is not None:
            raise N2PhysicalOnceError("MAP action unexpectedly gained prior evidence")
    elif not _is_sha256(evidence.get("prior_result_file_sha256")):
        raise N2PhysicalOnceError("target action lacks exact primer result identity")
    _validate_control_chain(directory, context, evidence)
    outcome = evidence.get("outcome")
    if outcome not in {"protocol_verified_observation_pending", "UNKNOWN_DO_NOT_RETRY"}:
        raise N2PhysicalOnceError("physical action evidence outcome is invalid")
    if outcome == "protocol_verified_observation_pending":
        completed_at = _rfc3339(
            evidence.get("protocol_completed_at"), label="protocol_completed_at"
        )
        if (
            evidence.get("protocol_verified") is not True
            or completed_at < recorded_at
            or evidence.get("error") is not None
        ):
            raise N2PhysicalOnceError("verified protocol evidence timing/state changed")
        _validate_request_audit(
            evidence.get("request_audit"),
            frame_sha256=context.action["identity"]["frame"]["sha256"],
        )
        _validate_protocol(context, evidence.get("protocol_evidence"))
    elif (
        evidence.get("protocol_verified") is not False
        or evidence.get("protocol_completed_at") is not None
        or evidence.get("protocol_evidence") is not None
    ):
        raise N2PhysicalOnceError("UNKNOWN evidence gained verified protocol state")
    result: Optional[Mapping[str, Any]] = None
    result_payload: Optional[bytes] = None
    observation: Optional[Mapping[str, Any]] = None
    observation_payload: Optional[bytes] = None
    finalization: Optional[Mapping[str, Any]] = None
    finalization_payload: Optional[bytes] = None
    result_path = directory / P0_RESULT_FILENAME
    finalization_path = directory / FINALIZATION_FILENAME
    observation_path = directory / OBSERVATION_FILENAME
    if os.path.lexists(result_path):
        result_snapshot = _read_snapshot(
            result_path, label="physical P0 result", maximum_bytes=_MAX_JSON_BYTES
        )
        result = _parse_json_snapshot(result_snapshot, label="physical P0 result")
        result_payload = result_snapshot.payload
        try:
            validate_result_record(result)
        except CampaignContractError as error:
            raise N2PhysicalOnceError(f"physical P0 result is invalid: {error}") from error
        if (
            result_file_sha256(result) != result_snapshot.sha256
            or result["action_identity_sha256"]
            != context.action["action_identity_sha256"]
        ):
            raise N2PhysicalOnceError("physical P0 result action/file binding changed")
    finalized_present = os.path.lexists(finalization_path) or os.path.lexists(observation_path)
    if finalized_present:
        if not (os.path.lexists(finalization_path) and os.path.lexists(observation_path)):
            raise N2PhysicalOnceError("physical finalization bundle is partial")
        observation_snapshot = _read_snapshot(
            observation_path,
            label="stored physical observation",
            maximum_bytes=_MAX_JSON_BYTES,
        )
        finalization_snapshot = _read_snapshot(
            finalization_path,
            label="physical finalization",
            maximum_bytes=_MAX_JSON_BYTES,
        )
        observation = _parse_json_snapshot(
            observation_snapshot, label="stored physical observation"
        )
        finalization = _parse_json_snapshot(
            finalization_snapshot, label="physical finalization"
        )
        observation_payload = observation_snapshot.payload
        finalization_payload = finalization_snapshot.payload
        if (
            outcome != "protocol_verified_observation_pending"
            or result is None
        ):
            raise N2PhysicalOnceError("physical finalization/result binding changed")
        _validate_finalized_observation(
            directory,
            context,
            evidence,
            evidence_snapshot.sha256,
            observation,
            observation_snapshot.sha256,
            finalization,
            result,
        )
    elif outcome == "UNKNOWN_DO_NOT_RETRY":
        if result is None or result["state"] != ResultState.UNKNOWN_DO_NOT_RETRY.value:
            raise N2PhysicalOnceError("UNKNOWN evidence lacks its terminal P0 result")
        if result["evidence_manifest_sha256"] != evidence_snapshot.sha256:
            raise N2PhysicalOnceError("UNKNOWN result does not bind its evidence file")
        request_audit = evidence.get("request_audit")
        if request_audit is not None:
            if (
                not isinstance(request_audit, Mapping)
                or type(request_audit.get("post_attempt_count")) is not int
                or type(request_audit.get("post_issued_count")) is not int
                or not 0 <= request_audit["post_attempt_count"] <= 1
                or not 0 <= request_audit["post_issued_count"] <= 1
                or request_audit["post_issued_count"]
                > request_audit["post_attempt_count"]
            ):
                raise N2PhysicalOnceError("UNKNOWN request audit permits a retry")
        if os.path.lexists(directory / CAMERA_CAPTURE_FILENAME):
            raise N2PhysicalOnceError("UNKNOWN action unexpectedly gained camera evidence")
    elif result is not None:
        raise N2PhysicalOnceError("pending physical action unexpectedly has a P0 result")
    elif require_finalized:
        raise N2PhysicalOnceError("physical action observation is not finalized")
    return _StoredValidation(
        directory=directory,
        context=context,
        evidence=evidence,
        evidence_payload=evidence_snapshot.payload,
        result=result,
        result_payload=result_payload,
        observation=observation,
        observation_payload=observation_payload,
        finalization=finalization,
        finalization_payload=finalization_payload,
    )


def _load_prior(
    result_dir: Path,
    target_context: _Context,
    *,
    reviewer_key_file: Path,
) -> _Prior:
    if target_context.legacy_snapshot.phase != "target":
        raise N2PhysicalOnceError("only target actions may bind a primer result")
    stored = _validate_stored_result(
        result_dir, reviewer_key_file=reviewer_key_file, require_finalized=True
    )
    expected = target_context.action["identity"]["prior"]["action_identity_sha256"]
    if (
        stored.result is None
        or stored.observation is None
        or stored.finalization is None
        or stored.context.operator != target_context.operator
        or stored.context.action["action_identity_sha256"] != expected
        or stored.context.legacy_snapshot.phase != "map-primer"
        or stored.context.legacy_snapshot.cell_id
        != target_context.legacy_snapshot.cell_id
        or stored.result["state"] != ResultState.PASS.value
        or stored.observation.get("visual_pass") is not True
    ):
        raise N2PhysicalOnceError("primer result is not the exact same-cell finalized PASS")
    assert stored.result_payload is not None
    return _Prior(
        directory=stored.directory,
        result=stored.result,
        result_sha256=_sha256(stored.result_payload),
        evidence=stored.evidence,
        observation=stored.observation,
        finalization=stored.finalization,
        context=stored.context,
    )


def _prepare_description(
    context: _Context,
    *,
    evaluated_at: str,
    prior: Optional[_Prior],
) -> Mapping[str, Any]:
    try:
        p0 = describe_action_offline(
            context.campaign,
            action_identity_sha256=context.action["action_identity_sha256"],
            limit_profile=context.production.profile,
            evaluated_at=evaluated_at,
            prior_result=prior.result if prior else None,
            prior_result_sha256=prior.result_sha256 if prior else None,
        )
    except CampaignContractError as error:
        raise N2PhysicalOnceError(f"physical P0 description failed: {error}") from error
    return p0


def describe_physical_action(
    action_key: str,
    *,
    bundle_dir: Path,
    source_manifest_file: Path,
    panel_file: Path,
    binding_review_artifact_file: Path,
    profile_file: Path,
    firmware_binary_file: Path,
    supplier_limits_file: Path,
    usage_evidence_file: Path,
    profile_review_artifact_file: Path,
    reviewer_key_file: Path,
    evaluated_at: str,
    primer_result_dir: Optional[Path] = None,
) -> dict[str, Any]:
    context = _load_live_context(
        action_key,
        bundle_dir=bundle_dir,
        source_manifest_file=source_manifest_file,
        panel_file=panel_file,
        binding_review_artifact_file=binding_review_artifact_file,
        profile_file=profile_file,
        firmware_binary_file=firmware_binary_file,
        supplier_limits_file=supplier_limits_file,
        usage_evidence_file=usage_evidence_file,
        profile_review_artifact_file=profile_review_artifact_file,
        reviewer_key_file=reviewer_key_file,
        evaluated_at=evaluated_at,
    )
    if context.legacy_snapshot.phase == "target" and primer_result_dir is None:
        raise N2PhysicalOnceError("target describe requires same-cell primer result directory")
    if context.legacy_snapshot.phase == "map-primer" and primer_result_dir is not None:
        raise N2PhysicalOnceError("map-primer describe must not receive a prior result")
    prior = (
        _load_prior(primer_result_dir, context, reviewer_key_file=reviewer_key_file)
        if primer_result_dir is not None
        else None
    )
    p0 = _prepare_description(context, evaluated_at=evaluated_at, prior=prior)
    schedule_decision = _runtime_schedule_decision(
        context, evaluated_at=evaluated_at
    )
    panel = context.campaign["panel"]
    firmware = context.campaign["firmware"]
    binding_sha = context.operator["physical_binding"]["integrity"]["canonical_sha256"]
    action_authorization = required_action_authorization(
        context.action["action_identity_sha256"]
    )
    panel_confirmation = required_panel_build_confirmation(
        str(panel["serial"]), str(firmware["build_tag"]), str(binding_sha)
    )
    profile_confirmation = _profile_confirmation(context)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": DESCRIPTION_KIND,
        "mode": "describe-only",
        "action_key": action_key,
        "action_identity_sha256": context.action["action_identity_sha256"],
        "phase": context.legacy_snapshot.phase,
        "cell_id": context.legacy_snapshot.cell_id,
        "panel": dict(panel),
        "firmware": dict(firmware),
        "operator_manifest_canonical_sha256": context.operator["integrity"][
            "canonical_sha256"
        ],
        "physical_binding_canonical_sha256": binding_sha,
        "campaign_canonical_sha256": context.campaign["integrity"][
            "canonical_sha256"
        ],
        "profile_canonical_sha256": context.production.profile["integrity"][
            "canonical_sha256"
        ],
        "reviewer_key_id": context.production.reviewer_key_id,
        "production_ready": True,
        "p0_contract_ready": (
            p0["contract_ready"] and schedule_decision["ready"]
        ),
        "p0_description": dict(p0),
        "runtime_schedule_decision": schedule_decision,
        "required_action_authorization_sha256": _sha256(
            action_authorization.encode("utf-8")
        ),
        "required_panel_build_confirmation_sha256": _sha256(
            panel_confirmation.encode("utf-8")
        ),
        "required_profile_confirmation_sha256": _sha256(
            profile_confirmation.encode("utf-8")
        ),
        "maximum_live_evaluation_age_seconds": (
            MAX_LIVE_EVALUATED_AT_AGE_SECONDS
        ),
        "required_target_continuity_confirmations": (
            [
                "map_fidelity_from_same_cell_primer",
                "esp32_not_restarted_since_primer",
                "no_j2_disconnect_since_primer",
                "no_panel_power_cycle_since_primer",
                "no_other_visible_refresh_since_primer",
            ]
            if context.legacy_snapshot.phase == "target"
            else []
        ),
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "maximum_post_requests": 1,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
    }


def _base_evidence(
    context: _Context,
    *,
    attempt_id: str,
    claim: _Claim,
    recorded_at: str,
    evaluated_at: str,
    prior: Optional[_Prior],
    start_temperature_c: float,
    confirmations: Mapping[str, bool],
    authorization_confirmation: str,
    panel_build_confirmation: str,
    profile_confirmation: str,
    live_evaluation_age_seconds: float,
    runtime_schedule_decision: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EVIDENCE_KIND,
        "runner_kind": RUNNER_KIND,
        "attempt_id": attempt_id,
        "recorded_at": recorded_at,
        "action_key": context.action_key,
        "cell_id": context.legacy_snapshot.cell_id,
        "phase": context.legacy_snapshot.phase,
        "action_identity_sha256": context.action["action_identity_sha256"],
        "operator_manifest_canonical_sha256": context.operator["integrity"][
            "canonical_sha256"
        ],
        "operator_manifest_file_sha256": context.snapshots[
            COPIED_OPERATOR_FILENAME
        ].sha256,
        "physical_binding_canonical_sha256": context.operator["physical_binding"][
            "integrity"
        ]["canonical_sha256"],
        "campaign_canonical_sha256": context.campaign["integrity"][
            "canonical_sha256"
        ],
        "campaign_file_sha256": context.production.inputs.campaign_file.sha256,
        "frame_sha256": context.action["identity"]["frame"]["sha256"],
        "reference_preview": dict(context.legacy_snapshot.reference_preview),
        "claim": claim.reference(),
        "profile_canonical_sha256": context.production.profile["integrity"][
            "canonical_sha256"
        ],
        "profile_file_sha256": context.production.profile_file.sha256,
        "profile_evaluated_at": evaluated_at,
        "live_evaluation_age_seconds": live_evaluation_age_seconds,
        "maximum_live_evaluation_age_seconds": (
            MAX_LIVE_EVALUATED_AT_AGE_SECONDS
        ),
        "runtime_schedule_decision": dict(runtime_schedule_decision),
        "reviewer_key_id": context.production.reviewer_key_id,
        "snapshot_files": _snapshot_records(context.snapshots),
        "prior_result_file_sha256": prior.result_sha256 if prior else None,
        "start_temperature_c": start_temperature_c,
        "confirmations": dict(confirmations),
        "authorization_confirmation_sha256": _sha256(
            authorization_confirmation.encode("utf-8")
        ),
        "panel_build_confirmation_sha256": _sha256(
            panel_build_confirmation.encode("utf-8")
        ),
        "profile_confirmation_sha256": _sha256(
            profile_confirmation.encode("utf-8")
        ),
        "scoring_contract_sha256": legacy.SCORING_CONTRACT_SHA256,
        "camera_observation_contract_sha256": (
            legacy.CAMERA_OBSERVATION_CONTRACT_SHA256
        ),
        "maximum_post_requests": 1,
        "automatic_retry_count": 0,
        "retry_allowed": False,
        "recovery_performed": False,
    }


def _record_unknown(
    destination: Optional[Path],
    base: Mapping[str, Any],
    *,
    requester_audit: Optional[Mapping[str, Any]],
    error: BaseException,
) -> None:
    if destination is None or not destination.is_dir():
        return
    post_count = int(requester_audit.get("post_issued_count", 0)) if requester_audit else 0
    evidence = {
        **dict(base),
        "outcome": "UNKNOWN_DO_NOT_RETRY",
        "protocol_verified": False,
        "protocol_completed_at": None,
        "protocol_evidence": None,
        "request_audit": dict(requester_audit) if requester_audit else None,
        "error": {"type": type(error).__name__, "message": str(error)},
    }
    evidence_sha = _write_json(destination, EVIDENCE_FILENAME, evidence)
    result = build_result_record(
        action_identity_sha256=str(base["action_identity_sha256"]),
        state=ResultState.UNKNOWN_DO_NOT_RETRY,
        completed_at=_utc_now(),
        evidence_manifest_sha256=evidence_sha,
        post_request_count=post_count,
        details="physical action claim consumed; retry and recovery are forbidden",
    )
    _write_json(destination, P0_RESULT_FILENAME, result)


def run_physical_action_once(
    action_key: str,
    result_dir: Path,
    base_url: str,
    *,
    bundle_dir: Path,
    source_manifest_file: Path,
    panel_file: Path,
    binding_review_artifact_file: Path,
    profile_file: Path,
    firmware_binary_file: Path,
    supplier_limits_file: Path,
    usage_evidence_file: Path,
    profile_review_artifact_file: Path,
    reviewer_key_file: Path,
    evaluated_at: str,
    authorization_confirmation: str,
    panel_build_confirmation: str,
    profile_confirmation: str,
    start_temperature_c: float,
    primer_result_dir: Optional[Path] = None,
    confirm_supervised_supply_cv_current_normal: bool = False,
    confirm_physical_cutoff_available: bool = False,
    confirm_single_visible_refresh: bool = False,
    confirm_controller_fresh_boot: bool = False,
    confirm_map_fidelity_from_primer: bool = False,
    confirm_esp32_not_restarted_since_primer: bool = False,
    confirm_no_j2_disconnect_since_primer: bool = False,
    confirm_no_panel_power_cycle_since_primer: bool = False,
    confirm_no_other_visible_refresh_since_primer: bool = False,
    job_timeout_s: float = legacy._quality.DEFAULT_JOB_TIMEOUT_S,
    poll_interval_s: float = legacy._quality.DEFAULT_POLL_INTERVAL_S,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    destination = _prepare_result_destination(result_dir)
    if not isinstance(base_url, str) or not base_url.strip():
        raise N2PhysicalOnceError("base_url must be a non-empty device root URL")
    context = _load_live_context(
        action_key,
        bundle_dir=bundle_dir,
        source_manifest_file=source_manifest_file,
        panel_file=panel_file,
        binding_review_artifact_file=binding_review_artifact_file,
        profile_file=profile_file,
        firmware_binary_file=firmware_binary_file,
        supplier_limits_file=supplier_limits_file,
        usage_evidence_file=usage_evidence_file,
        profile_review_artifact_file=profile_review_artifact_file,
        reviewer_key_file=reviewer_key_file,
        evaluated_at=evaluated_at,
    )
    live_now = _utc_now()
    live_evaluation_age_seconds = _validate_live_evaluation_time(
        evaluated_at, live_now
    )
    if context.legacy_snapshot.phase == "target" and primer_result_dir is None:
        raise N2PhysicalOnceError("target live execution requires primer result directory")
    if context.legacy_snapshot.phase == "map-primer" and primer_result_dir is not None:
        raise N2PhysicalOnceError("map-primer must not receive a prior result")
    prior = (
        _load_prior(primer_result_dir, context, reviewer_key_file=reviewer_key_file)
        if primer_result_dir is not None
        else None
    )
    p0 = _prepare_description(context, evaluated_at=evaluated_at, prior=prior)
    if p0["contract_ready"] is not True:
        raise N2PhysicalOnceError(
            "physical P0 contract is not ready: " + ", ".join(p0["blockers"])
        )
    runtime_schedule = _runtime_schedule_decision(
        context, evaluated_at=live_now
    )
    if runtime_schedule["ready"] is not True:
        raise N2PhysicalOnceError(
            "physical runtime schedule is not ready: "
            + ", ".join(runtime_schedule["blockers"])
        )
    start_temp = _temperature(start_temperature_c, label="start_temperature_c")
    limits = context.production.profile["limits"]
    if not limits["minimum_start_temperature_c"] <= start_temp <= limits[
        "maximum_start_temperature_c"
    ]:
        raise N2PhysicalOnceError("start temperature is outside the reviewed profile")
    confirmations = {
        "supervised_supply_cv_current_normal": confirm_supervised_supply_cv_current_normal,
        "physical_cutoff_available": confirm_physical_cutoff_available,
        "single_visible_refresh": confirm_single_visible_refresh,
        **(
            {"controller_fresh_boot": confirm_controller_fresh_boot}
            if context.legacy_snapshot.phase == "map-primer"
            else {
                "map_fidelity_from_same_cell_primer": confirm_map_fidelity_from_primer,
                "esp32_not_restarted_since_primer": (
                    confirm_esp32_not_restarted_since_primer
                ),
                "no_j2_disconnect_since_primer": (
                    confirm_no_j2_disconnect_since_primer
                ),
                "no_panel_power_cycle_since_primer": (
                    confirm_no_panel_power_cycle_since_primer
                ),
                "no_other_visible_refresh_since_primer": (
                    confirm_no_other_visible_refresh_since_primer
                ),
            }
        ),
    }
    if any(type(value) is not bool or value is not True for value in confirmations.values()):
        raise N2PhysicalOnceError("all physical action confirmations must be true")
    expected_authorization = required_action_authorization(
        context.action["action_identity_sha256"]
    )
    binding_sha = context.operator["physical_binding"]["integrity"]["canonical_sha256"]
    expected_panel = required_panel_build_confirmation(
        str(context.campaign["panel"]["serial"]),
        str(context.campaign["firmware"]["build_tag"]),
        str(binding_sha),
    )
    if authorization_confirmation != expected_authorization:
        raise N2PhysicalOnceError("exact dynamic physical-action authorization is required")
    if panel_build_confirmation != expected_panel:
        raise N2PhysicalOnceError("exact physical panel serial/build confirmation is required")
    expected_profile = _profile_confirmation(context)
    if profile_confirmation != expected_profile:
        raise N2PhysicalOnceError("exact approved production-profile confirmation is required")

    attempt_id = uuid.uuid4().hex
    claimed_at = live_now
    claim = _claim_action(
        context,
        attempt_id=attempt_id,
        claimed_at=claimed_at,
        destination=destination,
        prior=prior,
        start_temperature_c=start_temp,
        confirmations=confirmations,
        authorization_confirmation=authorization_confirmation,
        panel_build_confirmation=panel_build_confirmation,
        profile_confirmation=profile_confirmation,
        profile_evaluated_at=evaluated_at,
        live_evaluation_age_seconds=live_evaluation_age_seconds,
        runtime_schedule_decision=runtime_schedule,
    )
    created_destination: Optional[Path] = None
    audit_capture: dict[str, Any] = {}
    requester_audit: Optional[Mapping[str, Any]] = audit_capture
    base = _base_evidence(
        context,
        attempt_id=attempt_id,
        claim=claim,
        recorded_at=claimed_at,
        evaluated_at=evaluated_at,
        prior=prior,
        start_temperature_c=start_temp,
        confirmations=confirmations,
        authorization_confirmation=authorization_confirmation,
        panel_build_confirmation=panel_build_confirmation,
        profile_confirmation=profile_confirmation,
        live_evaluation_age_seconds=live_evaluation_age_seconds,
        runtime_schedule_decision=runtime_schedule,
    )
    try:
        destination.mkdir()
        created_destination = destination
        _copy_snapshots(context, destination)
        _write_json(
            destination,
            LOCK_FILENAME,
            {
                "schema_version": SCHEMA_VERSION,
                "kind": LOCK_KIND,
                "attempt_id": attempt_id,
                "action_key": action_key,
                "action_identity_sha256": context.action["action_identity_sha256"],
                "claim": claim.reference(),
                "confirmations": confirmations,
                "authorization_confirmation_sha256": _sha256(
                    authorization_confirmation.encode("utf-8")
                ),
                "panel_build_confirmation_sha256": _sha256(
                    panel_build_confirmation.encode("utf-8")
                ),
                "profile_confirmation_sha256": _sha256(
                    profile_confirmation.encode("utf-8")
                ),
                "profile_evaluated_at": evaluated_at,
                "live_evaluation_age_seconds": live_evaluation_age_seconds,
                "maximum_live_evaluation_age_seconds": (
                    MAX_LIVE_EVALUATED_AT_AGE_SECONDS
                ),
                "runtime_schedule_decision": runtime_schedule,
                "state": "authorization_permanently_consumed_do_not_rerun",
                "automatic_retry_authorized": False,
                "automatic_recovery_authorized": False,
            },
        )
        try:
            protocol, requester_audit = legacy._execute_protocol(
                context.legacy_snapshot,
                prior.legacy_bundle() if prior else None,
                base_url,
                audit_sink=audit_capture,
                job_timeout_s=job_timeout_s,
                poll_interval_s=poll_interval_s,
                sleeper=sleeper,
                clock=clock,
                required_authorization_confirmation_override=expected_authorization,
            )
        except legacy.N2PFixedActionError as error:
            raise N2PhysicalOnceError(str(error)) from error
        evidence = {
            **base,
            "outcome": "protocol_verified_observation_pending",
            "protocol_verified": True,
            "protocol_completed_at": _utc_now(),
            "protocol_evidence": dict(protocol),
            "request_audit": dict(requester_audit),
            "error": None,
        }
        _write_json(destination, EVIDENCE_FILENAME, evidence)
        return evidence
    except BaseException as error:
        try:
            _record_unknown(
                created_destination,
                base,
                requester_audit=requester_audit,
                error=error,
            )
        except BaseException:
            pass
        raise N2PhysicalOnceUnknown(
            "physical action is UNKNOWN_DO_NOT_RETRY; its global claim is permanent"
        ) from error


def finalize_physical_observation(
    result_dir: Path,
    observation_file: Path,
    *,
    reviewer_key_file: Path,
) -> dict[str, Any]:
    stored = _validate_stored_result(
        result_dir, reviewer_key_file=reviewer_key_file, require_finalized=False
    )
    directory = stored.directory
    if stored.evidence["outcome"] != "protocol_verified_observation_pending":
        raise N2PhysicalOnceError("only verified pending protocol evidence is finalizable")
    if stored.result is not None or stored.finalization is not None or stored.observation is not None:
        raise N2PhysicalOnceError("physical observation was already finalized")
    observation_snapshot = _read_snapshot(
        observation_file, label="operator physical observation", maximum_bytes=_MAX_JSON_BYTES
    )
    observation = _parse_json_snapshot(
        observation_snapshot, label="operator physical observation"
    )
    completed_at = _rfc3339(
        stored.evidence["protocol_completed_at"], label="protocol_completed_at"
    )
    try:
        (
            visual_pass,
            electrical_pass,
            thermal_pass,
            post_temp,
            camera_payload,
            camera_binding,
        ) = legacy._validate_observation(
            observation,
            stored.context.legacy_snapshot,
            stored.context.production.profile,
            camera_base_directory=observation_file.parent,
            minimum_observed_at=completed_at,
        )
    except legacy.N2PFixedActionError as error:
        raise N2PhysicalOnceError(f"physical observation is invalid: {error}") from error
    state = (
        ResultState.PASS
        if visual_pass and electrical_pass and thermal_pass
        else ResultState.FAIL
    )
    stored_observation = {
        **dict(observation),
        "visual_pass": visual_pass,
        "electrical_pass": electrical_pass,
        "post_refresh_temperature_pass": thermal_pass,
        "overall_state": state.value,
        "scoring_contract_sha256": legacy.SCORING_CONTRACT_SHA256,
        "camera_observation_contract_sha256": (
            legacy.CAMERA_OBSERVATION_CONTRACT_SHA256
        ),
        "source_observation_file_sha256": observation_snapshot.sha256,
        "verified_camera_evidence": dict(camera_binding) if camera_binding else None,
    }
    stored_observation_payload = canonical_json_bytes(stored_observation)
    finalization = {
        "schema_version": SCHEMA_VERSION,
        "kind": FINALIZATION_KIND,
        "action_key": stored.context.action_key,
        "action_identity_sha256": stored.context.action["action_identity_sha256"],
        "state": state.value,
        "protocol_evidence_file_sha256": _sha256(stored.evidence_payload),
        "observation_file_sha256": _sha256(stored_observation_payload),
        "profile_file_sha256": stored.context.production.profile_file.sha256,
        "reviewer_key_id": stored.context.production.reviewer_key_id,
        "post_refresh_temperature_c": post_temp,
        "visual_pass": visual_pass,
        "electrical_pass": electrical_pass,
        "post_refresh_temperature_pass": thermal_pass,
        "visual_and_electrical_assessed_separately": True,
        "scoring_contract_sha256": legacy.SCORING_CONTRACT_SHA256,
        "camera_observation_contract_sha256": (
            legacy.CAMERA_OBSERVATION_CONTRACT_SHA256
        ),
        "camera_capture_file_sha256": (
            camera_binding["sha256"] if camera_binding else None
        ),
        "camera_capture_present_for_this_action": camera_binding is not None,
    }
    finalization_payload = canonical_json_bytes(finalization)
    result = build_result_record(
        action_identity_sha256=stored.context.action["action_identity_sha256"],
        state=state,
        completed_at=str(observation["observed_at"]),
        evidence_manifest_sha256=_sha256(finalization_payload),
        post_request_count=1,
        details=(
            "physical visual/electrical/thermal PASS recorded independently"
            if state is ResultState.PASS
            else "one or more physical visual/electrical/thermal gates failed"
        ),
    )
    if camera_payload is not None:
        _atomic_commit(
            directory / CAMERA_CAPTURE_FILENAME,
            camera_payload,
            unknown_after_commit=False,
        )
    _atomic_commit(
        directory / OBSERVATION_FILENAME,
        stored_observation_payload,
        unknown_after_commit=False,
    )
    _atomic_commit(
        directory / FINALIZATION_FILENAME,
        finalization_payload,
        unknown_after_commit=False,
    )
    _write_json(directory, P0_RESULT_FILENAME, result)
    validated = _validate_stored_result(
        directory, reviewer_key_file=reviewer_key_file, require_finalized=True
    )
    assert validated.result is not None
    return {
        "state": state.value,
        "action_key": stored.context.action_key,
        "action_identity_sha256": stored.context.action["action_identity_sha256"],
        "result_file_sha256": result_file_sha256(validated.result),
        "visual_pass": visual_pass,
        "electrical_pass": electrical_pass,
        "post_refresh_temperature_pass": thermal_pass,
    }


def validate_physical_result(
    result_dir: Path,
    *,
    reviewer_key_file: Path,
    require_finalized: bool = False,
) -> dict[str, Any]:
    stored = _validate_stored_result(
        result_dir,
        reviewer_key_file=reviewer_key_file,
        require_finalized=require_finalized,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": VALIDATION_KIND,
        "valid": True,
        "action_key": stored.context.action_key,
        "action_identity_sha256": stored.context.action["action_identity_sha256"],
        "outcome": stored.evidence["outcome"],
        "finalized": stored.finalization is not None,
        "state": stored.result["state"] if stored.result is not None else None,
        "operator_manifest_canonical_sha256": stored.context.operator["integrity"][
            "canonical_sha256"
        ],
        "campaign_canonical_sha256": stored.context.campaign["integrity"][
            "canonical_sha256"
        ],
        "profile_canonical_sha256": stored.context.production.profile["integrity"][
            "canonical_sha256"
        ],
        "reviewer_key_id": stored.context.production.reviewer_key_id,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
    }


def _add_production_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--panel-file", type=Path, required=True)
    parser.add_argument("--binding-review-artifact", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--firmware-binary", type=Path, required=True)
    parser.add_argument(
        "--limit-authority",
        "--supplier-limits",
        dest="limit_authority",
        type=Path,
        required=True,
        help=(
            "supplier limits or an explicitly non-supplier supervised "
            "experimental process policy"
        ),
    )
    parser.add_argument("--usage-evidence", type=Path, required=True)
    parser.add_argument("--profile-review-artifact", type=Path, required=True)
    parser.add_argument("--reviewer-key", type=Path, required=True)
    parser.add_argument("--evaluated-at", required=True)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    describe = subparsers.add_parser("describe", allow_abbrev=False)
    describe.add_argument("--action", choices=FIXED_ACTION_KEYS, required=True)
    describe.add_argument("--primer-result-dir", type=Path)
    _add_production_inputs(describe)

    run = subparsers.add_parser("run", allow_abbrev=False)
    run.add_argument("--action", choices=FIXED_ACTION_KEYS, required=True)
    run.add_argument("--primer-result-dir", type=Path)
    _add_production_inputs(run)
    run.add_argument("--result-dir", type=Path, required=True)
    run.add_argument("--url", required=True)
    run.add_argument("--confirm-action", required=True)
    run.add_argument("--confirm-panel-build", required=True)
    run.add_argument("--confirm-profile", required=True)
    run.add_argument("--start-temperature-c", type=float, required=True)
    run.add_argument("--confirm-supervised-supply-cv-current-normal", action="store_true")
    run.add_argument("--confirm-physical-cutoff-available", action="store_true")
    run.add_argument("--confirm-single-visible-refresh", action="store_true")
    run.add_argument("--confirm-controller-fresh-boot", action="store_true")
    run.add_argument("--confirm-map-fidelity-from-primer", action="store_true")
    run.add_argument("--confirm-esp32-not-restarted-since-primer", action="store_true")
    run.add_argument("--confirm-no-j2-disconnect-since-primer", action="store_true")
    run.add_argument("--confirm-no-panel-power-cycle-since-primer", action="store_true")
    run.add_argument("--confirm-no-other-visible-refresh-since-primer", action="store_true")

    finalize = subparsers.add_parser("finalize", allow_abbrev=False)
    finalize.add_argument("--result-dir", type=Path, required=True)
    finalize.add_argument("--observation-file", type=Path, required=True)
    finalize.add_argument("--reviewer-key", type=Path, required=True)

    validate = subparsers.add_parser("validate", allow_abbrev=False)
    validate.add_argument("--result-dir", type=Path, required=True)
    validate.add_argument("--reviewer-key", type=Path, required=True)
    validate.add_argument("--require-finalized", action="store_true")
    return parser.parse_args(argv)


def _production_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "bundle_dir": args.bundle_dir,
        "source_manifest_file": args.source_manifest,
        "panel_file": args.panel_file,
        "binding_review_artifact_file": args.binding_review_artifact,
        "profile_file": args.profile,
        "firmware_binary_file": args.firmware_binary,
        "supplier_limits_file": args.limit_authority,
        "usage_evidence_file": args.usage_evidence,
        "profile_review_artifact_file": args.profile_review_artifact,
        "reviewer_key_file": args.reviewer_key,
        "evaluated_at": args.evaluated_at,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "describe":
            result = describe_physical_action(
                args.action,
                primer_result_dir=args.primer_result_dir,
                **_production_kwargs(args),
            )
        elif args.command == "run":
            result = run_physical_action_once(
                args.action,
                args.result_dir,
                args.url,
                primer_result_dir=args.primer_result_dir,
                authorization_confirmation=args.confirm_action,
                panel_build_confirmation=args.confirm_panel_build,
                profile_confirmation=args.confirm_profile,
                start_temperature_c=args.start_temperature_c,
                confirm_supervised_supply_cv_current_normal=(
                    args.confirm_supervised_supply_cv_current_normal
                ),
                confirm_physical_cutoff_available=args.confirm_physical_cutoff_available,
                confirm_single_visible_refresh=args.confirm_single_visible_refresh,
                confirm_controller_fresh_boot=args.confirm_controller_fresh_boot,
                confirm_map_fidelity_from_primer=args.confirm_map_fidelity_from_primer,
                confirm_esp32_not_restarted_since_primer=(
                    args.confirm_esp32_not_restarted_since_primer
                ),
                confirm_no_j2_disconnect_since_primer=(
                    args.confirm_no_j2_disconnect_since_primer
                ),
                confirm_no_panel_power_cycle_since_primer=(
                    args.confirm_no_panel_power_cycle_since_primer
                ),
                confirm_no_other_visible_refresh_since_primer=(
                    args.confirm_no_other_visible_refresh_since_primer
                ),
                **_production_kwargs(args),
            )
        elif args.command == "finalize":
            result = finalize_physical_observation(
                args.result_dir,
                args.observation_file,
                reviewer_key_file=args.reviewer_key,
            )
        else:
            result = validate_physical_result(
                args.result_dir,
                reviewer_key_file=args.reviewer_key,
                require_finalized=args.require_finalized,
            )
    except N2PhysicalOnceUnknown as error:
        print(f"UNKNOWN_DO_NOT_RETRY: {error}", file=sys.stderr)
        return 3
    except N2PhysicalOnceError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
