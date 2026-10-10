#!/usr/bin/env python3
"""Offline analyzer for one physical-bound N2P four-cell campaign.

The analyzer accepts exactly the eight finalized physical result directories
from four disjoint MAP->target sessions.  Every directory is first passed to
the production physical-once validator with ``require_finalized=True``.  This
module then performs the campaign-level checks that no single-action validator
can perform: common operator/campaign/profile safety lineage, unique claims
and attempts, exact same-cell priors, disjoint sessions, fixed panel/build
bindings, per-action profile freshness, camera comparability, and tie-safe
six-dimension ranking.

Analysis is read-only.  It performs no device or network I/O and creates no
claim or authorization.  The optional writer only publishes the canonical
analysis JSON to a caller-selected new file.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.visible_refresh_campaign import (  # noqa: E402
    ResultState,
    canonical_json_bytes,
    result_file_sha256,
)
from tools import g1_s1_rc2g_n2_physical_once as fixed  # noqa: E402
from tools.local_path_safety import (  # noqa: E402
    LocalPathSafetyError,
    require_local_regular_path_syntax,
)


SCHEMA_VERSION = 1
ANALYSIS_KIND = "mf1750-g1-s1-rc2g-n2p-physical-four-cell-analysis"
ANALYSIS_HASH_SCOPE = (
    "entire physical analysis excluding integrity; UTF-8 JSON with sorted "
    "keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
EXPECTED_RESULT_KEYS = tuple(fixed.FIXED_ACTION_KEYS)
SCORE_DIMENSIONS = (
    "detail",
    "tone",
    "gradients",
    "texture",
    "artifacts",
    "source_fidelity",
)
SOURCE_SNAPSHOT_FILENAMES = (
    fixed.COPIED_OPERATOR_FILENAME,
    fixed.COPIED_CAMPAIGN_FILENAME,
    fixed.COPIED_SOURCE_MANIFEST_FILENAME,
    fixed.COPIED_PANEL_FILENAME,
    fixed.COPIED_BINDING_REVIEW_FILENAME,
    fixed.COPIED_PROFILE_FILENAME,
    fixed.COPIED_FIRMWARE_FILENAME,
    fixed.COPIED_SUPPLIER_FILENAME,
    fixed.COPIED_USAGE_FILENAME,
    fixed.COPIED_PROFILE_REVIEW_FILENAME,
)
ROTATING_PROFILE_SNAPSHOT_FILENAMES = frozenset(
    {
        fixed.COPIED_PROFILE_FILENAME,
        fixed.COPIED_SUPPLIER_FILENAME,
        fixed.COPIED_USAGE_FILENAME,
        fixed.COPIED_PROFILE_REVIEW_FILENAME,
    }
)
STABLE_SOURCE_SNAPSHOT_FILENAMES = tuple(
    filename
    for filename in SOURCE_SNAPSHOT_FILENAMES
    if filename not in ROTATING_PROFILE_SNAPSHOT_FILENAMES
)

ANALYZER_CONTRACT = {
    "schema_version": 1,
    "contract_id": "n2p-physical-four-cell-offline-ranking-v2",
    "required_result_keys": list(EXPECTED_RESULT_KEYS),
    "required_terminal_chains": 8,
    "required_disjoint_map_target_sessions": 4,
    "deep_single_action_validator": (
        "tools.g1_s1_rc2g_n2_physical_once.validate_physical_result"
    ),
    "single_action_validator_require_finalized": True,
    "common_source_bindings": [
        "physical_operator_manifest",
        "physical_campaign",
        "production_profile_lineage",
        "panel",
        "firmware_build",
        "limit_authority_safety_contract",
        "common_limits_envelope",
        "per_action_profile_identity_and_validity",
        "reviewer_key_id",
        "all_nonrotating_copied_source_snapshot_bytes",
    ],
    "per_action_profile_policy": (
        "approved usage-bound profile rotates monotonically before every action"
    ),
    "score_dimensions_in_frozen_order": list(SCORE_DIMENSIONS),
    "score_source": "finalized_manual_target_observation",
    "primary_sort": "six_dimension_integer_total_descending",
    "reported_secondary_statistic": "arithmetic_mean",
    "tie_policy": "equal_top_total_is_explicit_tie_no_selected_winner",
    "camera_policy": {
        "not_required_for_manual_score_winner": True,
        "comparable_only_if_all_four_targets_have_verified_captures": True,
        "same_camera_and_fixed_settings_required": True,
        "missing_or_mismatched_capture_is_reported_not_hidden": True,
    },
    "winner_use": "N3_branch_selection_only",
    "algorithm_qualified": False,
    "population_inference": False,
    "network_io": False,
    "device_io": False,
    "claim_creation": False,
    "authorization_creation": False,
}


class N2PhysicalAnalysisError(RuntimeError):
    """A physical N2P chain or cross-campaign binding is invalid."""


@dataclass(frozen=True)
class _JsonSnapshot:
    value: Mapping[str, Any]
    payload: bytes
    sha256: str


@dataclass(frozen=True)
class _PhysicalResult:
    key: str
    directory: Path
    validation: Mapping[str, Any]
    operator: Mapping[str, Any]
    campaign: Mapping[str, Any]
    profile: Mapping[str, Any]
    action: Mapping[str, Any]
    evidence: Mapping[str, Any]
    observation: Mapping[str, Any]
    finalization: Mapping[str, Any]
    result: Mapping[str, Any]
    lock: Mapping[str, Any]
    snapshot_files: Mapping[str, Any]
    operator_file_sha256: str
    campaign_file_sha256: str
    profile_file_sha256: str
    result_file_sha256: str
    score_total: Optional[int]
    score_mean: Optional[float]
    camera_signature_sha256: Optional[str]


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise N2PhysicalAnalysisError(
            f"canonical JSON encoding failed: {error}"
        ) from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


ANALYZER_CONTRACT_SHA256 = (
    "f1fc03cf382f042d88351844cb431ebd1a7ab0e6af9e60e96edcbb06879e8b63"
)
if _sha256(_canonical(ANALYZER_CONTRACT)) != ANALYZER_CONTRACT_SHA256:
    raise RuntimeError("frozen physical N2P analyzer/ranking contract changed")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _hash(value: object, *, label: str) -> str:
    if not _is_sha256(value):
        raise N2PhysicalAnalysisError(f"{label} must be lowercase SHA-256")
    return str(value)


def _text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise N2PhysicalAnalysisError(f"{label} must be non-empty normalized text")
    return value


def _rfc3339(value: object, *, label: str) -> Any:
    try:
        return fixed._rfc3339(value, label=label)
    except fixed.N2PhysicalOnceError as error:
        raise N2PhysicalAnalysisError(f"{label} is invalid: {error}") from error


def _exact(value: object, *, label: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise N2PhysicalAnalysisError(f"{label} fields changed")
    return value


def _read_json(directory: Path, filename: str, *, label: str) -> _JsonSnapshot:
    try:
        snapshot = fixed._read_snapshot(
            directory / filename,
            label=label,
            maximum_bytes=16 * 1024 * 1024,
        )
        value = fixed._parse_json_snapshot(snapshot, label=label)
    except fixed.N2PhysicalOnceError as error:
        raise N2PhysicalAnalysisError(f"{label} is invalid: {error}") from error
    return _JsonSnapshot(value=value, payload=snapshot.payload, sha256=snapshot.sha256)


def _safe_directory(path: Path, *, label: str) -> Path:
    if not isinstance(path, Path):
        raise N2PhysicalAnalysisError(f"{label} must be pathlib.Path")
    try:
        require_local_regular_path_syntax(path, label=label)
        return fixed._safe_result_directory(path, must_exist=True)
    except (LocalPathSafetyError, fixed.N2PhysicalOnceError) as error:
        raise N2PhysicalAnalysisError(f"{label} is unsafe or unavailable: {error}") from error


def _expected_key_parts(key: str) -> tuple[str, str]:
    if key not in EXPECTED_RESULT_KEYS:
        raise N2PhysicalAnalysisError(f"unknown physical result key {key!r}")
    cell, phase = key.split("-", 1)
    return cell.upper(), phase


def _action_for_key(
    operator: Mapping[str, Any], campaign: Mapping[str, Any], key: str
) -> Mapping[str, Any]:
    fixed_actions = operator.get("fixed_actions")
    if not isinstance(fixed_actions, Mapping) or tuple(fixed_actions) != EXPECTED_RESULT_KEYS:
        raise N2PhysicalAnalysisError("physical operator fixed action enum changed")
    action_sha = fixed_actions.get(key)
    matches = [
        action
        for action in campaign.get("actions", [])
        if isinstance(action, Mapping)
        and action.get("action_identity_sha256") == action_sha
    ]
    if len(matches) != 1:
        raise N2PhysicalAnalysisError(f"{key} physical action is absent or duplicated")
    action = matches[0]
    identity = action.get("identity")
    cell_id, phase = _expected_key_parts(key)
    if (
        not isinstance(identity, Mapping)
        or identity.get("cell_id") != cell_id
        or identity.get("phase") != phase
        or not _is_sha256(action_sha)
    ):
        raise N2PhysicalAnalysisError(f"{key} dynamic physical identity changed")
    return action


def _validate_snapshot_files(
    value: object,
    *,
    key: str,
    filenames: Sequence[str] = SOURCE_SNAPSHOT_FILENAMES,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(filenames):
        raise N2PhysicalAnalysisError(f"{key} copied production snapshot set changed")
    for filename in filenames:
        item = _exact(
            value[filename],
            label=f"{key} snapshot {filename}",
            keys={"bytes", "sha256"},
        )
        if type(item["bytes"]) is not int or item["bytes"] < 1:
            raise N2PhysicalAnalysisError(f"{key} snapshot {filename} byte count is invalid")
        _hash(item["sha256"], label=f"{key} snapshot {filename}")
    return value


def _camera_signature(
    key: str,
    observation: Mapping[str, Any],
    finalization: Mapping[str, Any],
) -> Optional[str]:
    camera = observation.get("camera")
    if not isinstance(camera, Mapping):
        raise N2PhysicalAnalysisError(f"{key} stored camera observation is missing")
    binding = observation.get("verified_camera_evidence")
    captured = camera.get("capture_performed")
    if captured is False:
        if (
            binding is not None
            or finalization.get("camera_capture_present_for_this_action") is not False
            or finalization.get("camera_capture_file_sha256") is not None
        ):
            raise N2PhysicalAnalysisError(f"{key} uncaptured observation gained camera evidence")
        return None
    if captured is not True or not isinstance(binding, Mapping):
        raise N2PhysicalAnalysisError(f"{key} captured target lacks verified camera evidence")
    capture_sha = _hash(binding.get("sha256"), label=f"{key} camera capture")
    if (
        finalization.get("camera_capture_present_for_this_action") is not True
        or finalization.get("camera_capture_file_sha256") != capture_sha
    ):
        raise N2PhysicalAnalysisError(f"{key} camera finalization binding changed")
    signature = [
        camera.get("camera_id"),
        camera.get("tripod_position_id"),
        camera.get("lighting_setup_id"),
        camera.get("exposure_mode"),
        camera.get("white_balance_mode"),
        camera.get("focus_mode"),
        camera.get("image_processing"),
        binding.get("decoded_format"),
        binding.get("width"),
        binding.get("height"),
    ]
    if any(value is None for value in signature):
        raise N2PhysicalAnalysisError(f"{key} camera comparability signature is incomplete")
    return _sha256(_canonical(signature))


def _load_physical_result(
    key: str,
    directory: Path,
    *,
    reviewer_key_file: Path,
) -> _PhysicalResult:
    try:
        validation = fixed.validate_physical_result(
            directory,
            reviewer_key_file=reviewer_key_file,
            require_finalized=True,
        )
    except fixed.N2PhysicalOnceError as error:
        raise N2PhysicalAnalysisError(
            f"{key} failed deep physical-result validation: {error}"
        ) from error
    if (
        not isinstance(validation, Mapping)
        or validation.get("kind") != fixed.VALIDATION_KIND
        or validation.get("valid") is not True
        or validation.get("action_key") != key
        or validation.get("outcome") != "protocol_verified_observation_pending"
        or validation.get("finalized") is not True
        or validation.get("state") not in {ResultState.PASS.value, ResultState.FAIL.value}
        or validation.get("automatic_retry_authorized") is not False
        or validation.get("automatic_recovery_authorized") is not False
    ):
        raise N2PhysicalAnalysisError(f"{key} public physical validation summary changed")

    operator_snapshot = _read_json(
        directory, fixed.COPIED_OPERATOR_FILENAME, label=f"{key} physical operator"
    )
    campaign_snapshot = _read_json(
        directory, fixed.COPIED_CAMPAIGN_FILENAME, label=f"{key} physical campaign"
    )
    profile_snapshot = _read_json(
        directory, fixed.COPIED_PROFILE_FILENAME, label=f"{key} production profile"
    )
    evidence_snapshot = _read_json(
        directory, fixed.EVIDENCE_FILENAME, label=f"{key} physical evidence"
    )
    observation_snapshot = _read_json(
        directory, fixed.OBSERVATION_FILENAME, label=f"{key} physical observation"
    )
    finalization_snapshot = _read_json(
        directory, fixed.FINALIZATION_FILENAME, label=f"{key} physical finalization"
    )
    result_snapshot = _read_json(
        directory, fixed.P0_RESULT_FILENAME, label=f"{key} P0 result"
    )
    lock_snapshot = _read_json(
        directory, fixed.LOCK_FILENAME, label=f"{key} physical attempt lock"
    )

    operator = operator_snapshot.value
    campaign = campaign_snapshot.value
    profile = profile_snapshot.value
    evidence = evidence_snapshot.value
    observation = observation_snapshot.value
    finalization = finalization_snapshot.value
    result = result_snapshot.value
    lock = lock_snapshot.value
    if operator.get("physical_campaign_contract") != campaign:
        raise N2PhysicalAnalysisError(f"{key} operator/campaign copy binding changed")
    action = _action_for_key(operator, campaign, key)
    action_sha = action["action_identity_sha256"]
    snapshots = _validate_snapshot_files(evidence.get("snapshot_files"), key=key)
    if (
        snapshots[fixed.COPIED_OPERATOR_FILENAME]["sha256"]
        != operator_snapshot.sha256
        or snapshots[fixed.COPIED_CAMPAIGN_FILENAME]["sha256"]
        != campaign_snapshot.sha256
        or snapshots[fixed.COPIED_PROFILE_FILENAME]["sha256"]
        != profile_snapshot.sha256
    ):
        raise N2PhysicalAnalysisError(f"{key} copied source file SHA binding changed")
    if (
        validation.get("action_identity_sha256") != action_sha
        or validation.get("operator_manifest_canonical_sha256")
        != operator.get("integrity", {}).get("canonical_sha256")
        or validation.get("campaign_canonical_sha256")
        != campaign.get("integrity", {}).get("canonical_sha256")
        or validation.get("profile_canonical_sha256")
        != profile.get("integrity", {}).get("canonical_sha256")
        or validation.get("reviewer_key_id") != evidence.get("reviewer_key_id")
        or evidence.get("action_key") != key
        or evidence.get("action_identity_sha256") != action_sha
        or evidence.get("operator_manifest_canonical_sha256")
        != validation.get("operator_manifest_canonical_sha256")
        or evidence.get("campaign_canonical_sha256")
        != validation.get("campaign_canonical_sha256")
        or evidence.get("profile_canonical_sha256")
        != validation.get("profile_canonical_sha256")
        or evidence.get("profile_file_sha256") != profile_snapshot.sha256
        or finalization.get("action_key") != key
        or finalization.get("action_identity_sha256") != action_sha
        or finalization.get("state") != validation.get("state")
        or result.get("action_identity_sha256") != action_sha
        or result.get("state") != validation.get("state")
        or lock.get("action_key") != key
        or lock.get("action_identity_sha256") != action_sha
        or lock.get("attempt_id") != evidence.get("attempt_id")
        or lock.get("claim") != evidence.get("claim")
    ):
        raise N2PhysicalAnalysisError(f"{key} physical result cross-binding changed")
    try:
        actual_result_sha = result_file_sha256(result)
    except Exception as error:
        raise N2PhysicalAnalysisError(f"{key} result identity is invalid: {error}") from error
    if actual_result_sha != result_snapshot.sha256:
        raise N2PhysicalAnalysisError(f"{key} result whole-file SHA changed")
    if (
        profile.get("panel") != campaign.get("panel")
        or profile.get("firmware") != campaign.get("firmware")
        or profile.get("review", {}).get("approved") is not True
    ):
        raise N2PhysicalAnalysisError(f"{key} panel/build/profile binding changed")

    identity = action["identity"]
    score_total: Optional[int] = None
    score_mean: Optional[float] = None
    if identity["phase"] == "target":
        visual = observation.get("visual")
        if not isinstance(visual, Mapping):
            raise N2PhysicalAnalysisError(f"{key} target visual score record is missing")
        scores = [visual.get(dimension) for dimension in SCORE_DIMENSIONS]
        if any(type(score) is not int or not 1 <= score <= 5 for score in scores):
            raise N2PhysicalAnalysisError(f"{key} target scores must be integer 1..5")
        score_total = sum(scores)
        score_mean = score_total / len(scores)
    camera_signature = _camera_signature(key, observation, finalization)
    return _PhysicalResult(
        key=key,
        directory=directory,
        validation=validation,
        operator=operator,
        campaign=campaign,
        profile=profile,
        action=action,
        evidence=evidence,
        observation=observation,
        finalization=finalization,
        result=result,
        lock=lock,
        snapshot_files=snapshots,
        operator_file_sha256=operator_snapshot.sha256,
        campaign_file_sha256=campaign_snapshot.sha256,
        profile_file_sha256=profile_snapshot.sha256,
        result_file_sha256=actual_result_sha,
        score_total=score_total,
        score_mean=score_mean,
        camera_signature_sha256=camera_signature,
    )


def _candidate_for_cell(operator: Mapping[str, Any], cell_id: str) -> Mapping[str, Any]:
    source = operator.get("source")
    candidates = source.get("candidate_bindings") if isinstance(source, Mapping) else None
    if not isinstance(candidates, list):
        raise N2PhysicalAnalysisError("operator source candidate bindings are missing")
    matches = [
        candidate
        for candidate in candidates
        if isinstance(candidate, Mapping) and candidate.get("cell_id") == cell_id
    ]
    if len(matches) != 1:
        raise N2PhysicalAnalysisError(f"{cell_id} source candidate binding is not unique")
    candidate = matches[0]
    _text(candidate.get("algorithm"), label=f"{cell_id} algorithm")
    _hash(candidate.get("frame_sha256"), label=f"{cell_id} candidate frame")
    return candidate


def _validate_common_source(bundles: Mapping[str, _PhysicalResult]) -> dict[str, Any]:
    first = bundles[EXPECTED_RESULT_KEYS[0]]
    first_authority_contract = _limit_authority_safety_contract(first)
    stable_snapshots = {
        filename: dict(first.snapshot_files[filename])
        for filename in STABLE_SOURCE_SNAPSHOT_FILENAMES
    }
    common = {
        "operator_manifest_id": first.operator.get("operator_manifest_id"),
        "operator_manifest_canonical_sha256": first.operator.get("integrity", {}).get(
            "canonical_sha256"
        ),
        "operator_manifest_file_sha256": first.operator_file_sha256,
        "physical_binding_canonical_sha256": first.operator.get("physical_binding", {})
        .get("integrity", {})
        .get("canonical_sha256"),
        "campaign_id": first.campaign.get("campaign_id"),
        "campaign_canonical_sha256": first.campaign.get("integrity", {}).get(
            "canonical_sha256"
        ),
        "campaign_file_sha256": first.campaign_file_sha256,
        "panel": first.campaign.get("panel"),
        "firmware": first.campaign.get("firmware"),
        "profile_lineage": {
            "profile_identity_policy": "unique-approved-profile-per-action",
            "profile_validity_policy": "independently-deep-validated-per-action",
            "limit_authority_identity_policy": "unique-reviewed-authority-per-action",
            "limit_authority_safety_contract_sha256": _sha256(
                _canonical(first_authority_contract)
            ),
            "reviewer_id": first.profile.get("review", {}).get("reviewer_id"),
            "reviewer_key_id": first.validation.get("reviewer_key_id"),
            "panel": first.profile.get("panel"),
            "firmware": first.profile.get("firmware"),
            "action_allowlist": first.profile.get("action_allowlist"),
            "limits": first.profile.get("limits"),
        },
        "stable_source_snapshot_files": stable_snapshots,
        "scoring_contract_sha256": first.evidence.get("scoring_contract_sha256"),
        "camera_observation_contract_sha256": first.evidence.get(
            "camera_observation_contract_sha256"
        ),
    }
    _validate_source_binding(common)
    for key in EXPECTED_RESULT_KEYS[1:]:
        item = bundles[key]
        item_stable_snapshots = {
            filename: dict(item.snapshot_files[filename])
            for filename in STABLE_SOURCE_SNAPSHOT_FILENAMES
        }
        comparison = {
            "operator_manifest_id": item.operator.get("operator_manifest_id"),
            "operator_manifest_canonical_sha256": item.operator.get("integrity", {}).get(
                "canonical_sha256"
            ),
            "operator_manifest_file_sha256": item.operator_file_sha256,
            "physical_binding_canonical_sha256": item.operator.get(
                "physical_binding", {}
            )
            .get("integrity", {})
            .get("canonical_sha256"),
            "campaign_id": item.campaign.get("campaign_id"),
            "campaign_canonical_sha256": item.campaign.get("integrity", {}).get(
                "canonical_sha256"
            ),
            "campaign_file_sha256": item.campaign_file_sha256,
            "panel": item.campaign.get("panel"),
            "firmware": item.campaign.get("firmware"),
            "profile_lineage": {
                "profile_identity_policy": "unique-approved-profile-per-action",
                "profile_validity_policy": "independently-deep-validated-per-action",
                "limit_authority_identity_policy": "unique-reviewed-authority-per-action",
                "limit_authority_safety_contract_sha256": _sha256(
                    _canonical(_limit_authority_safety_contract(item))
                ),
                "reviewer_id": item.profile.get("review", {}).get("reviewer_id"),
                "reviewer_key_id": item.validation.get("reviewer_key_id"),
                "panel": item.profile.get("panel"),
                "firmware": item.profile.get("firmware"),
                "action_allowlist": item.profile.get("action_allowlist"),
                "limits": item.profile.get("limits"),
            },
            "stable_source_snapshot_files": item_stable_snapshots,
            "scoring_contract_sha256": item.evidence.get("scoring_contract_sha256"),
            "camera_observation_contract_sha256": item.evidence.get(
                "camera_observation_contract_sha256"
            ),
        }
        if comparison != common:
            raise N2PhysicalAnalysisError(
                f"{key} is not from the same operator/campaign/profile safety lineage"
            )
    return common


def _limit_authority_safety_contract(
    bundle: _PhysicalResult,
) -> Mapping[str, Any]:
    snapshot = _read_json(
        bundle.directory,
        fixed.COPIED_SUPPLIER_FILENAME,
        label=f"{bundle.key} limit authority",
    )
    expected_sha = bundle.snapshot_files[fixed.COPIED_SUPPLIER_FILENAME]["sha256"]
    if snapshot.sha256 != expected_sha:
        raise N2PhysicalAnalysisError(
            f"{bundle.key} limit authority file SHA binding changed"
        )
    authority = dict(snapshot.value)
    rotating_fields = {"policy_id", "issued_at", "validity"}
    if not rotating_fields.issubset(authority):
        raise N2PhysicalAnalysisError(
            f"{bundle.key} rotating limit authority identity fields are missing"
        )
    for field in rotating_fields:
        authority.pop(field)
    return authority


def _profile_usage_state(bundle: _PhysicalResult) -> dict[str, Any]:
    usage = bundle.profile.get("usage")
    if not isinstance(usage, Mapping):
        raise N2PhysicalAnalysisError(f"{bundle.key} production usage state is missing")
    required = {
        "cumulative_visible_refresh_count",
        "session_visible_refresh_count",
        "consecutive_visible_refresh_count",
        "last_visible_refresh_completed_at",
        "snapshot_at",
        "evidence_sha256",
    }
    if set(usage) != required:
        raise N2PhysicalAnalysisError(f"{bundle.key} production usage fields changed")
    for field in (
        "cumulative_visible_refresh_count",
        "session_visible_refresh_count",
        "consecutive_visible_refresh_count",
    ):
        if type(usage[field]) is not int or usage[field] < 0:
            raise N2PhysicalAnalysisError(f"{bundle.key} {field} is invalid")
    _hash(usage["evidence_sha256"], label=f"{bundle.key} usage evidence")
    snapshot = _rfc3339(
        usage["snapshot_at"], label=f"{bundle.key} usage snapshot_at"
    )
    last_value = usage["last_visible_refresh_completed_at"]
    last = (
        None
        if last_value is None
        else _rfc3339(
            last_value, label=f"{bundle.key} usage last visible refresh"
        )
    )
    if last is not None and last > snapshot:
        raise N2PhysicalAnalysisError(
            f"{bundle.key} usage last refresh follows its snapshot"
        )
    review = bundle.profile.get("review")
    if not isinstance(review, Mapping) or review.get("approved") is not True:
        raise N2PhysicalAnalysisError(f"{bundle.key} profile is not approved")
    profile_canonical = _hash(
        bundle.profile.get("integrity", {}).get("canonical_sha256"),
        label=f"{bundle.key} profile canonical identity",
    )
    review_artifact_sha = _hash(
        bundle.snapshot_files[fixed.COPIED_PROFILE_REVIEW_FILENAME]["sha256"],
        label=f"{bundle.key} profile review artifact",
    )
    usage_file_sha = _hash(
        bundle.snapshot_files[fixed.COPIED_USAGE_FILENAME]["sha256"],
        label=f"{bundle.key} usage evidence file",
    )
    if (
        usage_file_sha != usage["evidence_sha256"]
        or review.get("review_artifact_sha256") != review_artifact_sha
    ):
        raise N2PhysicalAnalysisError(
            f"{bundle.key} rotating profile evidence binding changed"
        )
    profile_id = _text(
        bundle.profile.get("profile_id"), label=f"{bundle.key} profile id"
    )
    profile_version = _text(
        bundle.profile.get("profile_version"), label=f"{bundle.key} profile version"
    )
    validity = _exact(
        bundle.profile.get("validity"),
        label=f"{bundle.key} profile validity",
        keys={"valid_from", "expires_at"},
    )
    valid_from = _rfc3339(
        validity["valid_from"], label=f"{bundle.key} profile valid_from"
    )
    expires_at = _rfc3339(
        validity["expires_at"], label=f"{bundle.key} profile expires_at"
    )
    if valid_from >= expires_at:
        raise N2PhysicalAnalysisError(
            f"{bundle.key} profile validity interval is empty or reversed"
        )
    return {
        "profile_id": profile_id,
        "profile_version": profile_version,
        "valid_from": validity["valid_from"],
        "expires_at": validity["expires_at"],
        "profile_canonical_sha256": profile_canonical,
        "profile_file_sha256": bundle.profile_file_sha256,
        "profile_review_artifact_file_sha256": review_artifact_sha,
        "limit_authority_file_sha256": bundle.snapshot_files[
            fixed.COPIED_SUPPLIER_FILENAME
        ]["sha256"],
        "usage_evidence_file_sha256": usage_file_sha,
        "cumulative_visible_refresh_count": usage[
            "cumulative_visible_refresh_count"
        ],
        "session_visible_refresh_count": usage["session_visible_refresh_count"],
        "consecutive_visible_refresh_count": usage[
            "consecutive_visible_refresh_count"
        ],
        "last_visible_refresh_completed_at": last_value,
        "snapshot_at": usage["snapshot_at"],
    }


def _validate_usage_progression(
    bundles: Mapping[str, _PhysicalResult],
) -> dict[str, Mapping[str, Any]]:
    states = {key: _profile_usage_state(bundles[key]) for key in EXPECTED_RESULT_KEYS}
    first_count = states[EXPECTED_RESULT_KEYS[0]]["cumulative_visible_refresh_count"]
    prior_completed = None
    profile_shas: set[str] = set()
    profile_ids: set[str] = set()
    profile_files: set[str] = set()
    review_files: set[str] = set()
    authority_files: set[str] = set()
    usage_files: set[str] = set()
    for index, key in enumerate(EXPECTED_RESULT_KEYS):
        state = states[key]
        phase = _expected_key_parts(key)[1]
        expected_session_count = 0 if phase == "map-primer" else 1
        if (
            state["cumulative_visible_refresh_count"] != first_count + index
            or state["session_visible_refresh_count"] != expected_session_count
            or state["consecutive_visible_refresh_count"] != expected_session_count
        ):
            raise N2PhysicalAnalysisError(
                f"{key} pre-action usage does not follow the frozen campaign order"
            )
        snapshot = _rfc3339(
            state["snapshot_at"], label=f"{key} usage snapshot_at"
        )
        last_value = state["last_visible_refresh_completed_at"]
        last = (
            None
            if last_value is None
            else _rfc3339(last_value, label=f"{key} usage last refresh")
        )
        if prior_completed is not None and (
            last is None or last < prior_completed or snapshot < prior_completed
        ):
            raise N2PhysicalAnalysisError(
                f"{key} reused a usage snapshot older than the preceding finalized action"
            )
        prior_completed = _rfc3339(
            bundles[key].result.get("completed_at"),
            label=f"{key} finalized completed_at",
        )
        profile_shas.add(str(state["profile_canonical_sha256"]))
        profile_ids.add(str(state["profile_id"]))
        profile_files.add(str(state["profile_file_sha256"]))
        review_files.add(str(state["profile_review_artifact_file_sha256"]))
        authority_files.add(str(state["limit_authority_file_sha256"]))
        usage_files.add(str(state["usage_evidence_file_sha256"]))
    if not all(
        len(values) == 8
        for values in (
            profile_ids,
            profile_shas,
            profile_files,
            review_files,
            authority_files,
            usage_files,
        )
    ):
        raise N2PhysicalAnalysisError(
            "per-action approved profile/usage snapshot was replayed"
        )
    return states


def _validate_sessions(bundles: Mapping[str, _PhysicalResult]) -> list[dict[str, Any]]:
    campaign = bundles[EXPECTED_RESULT_KEYS[0]].campaign
    declared_sessions = campaign.get("sessions")
    if not isinstance(declared_sessions, list) or len(declared_sessions) != 4:
        raise N2PhysicalAnalysisError("physical campaign must declare four sessions")
    sessions_by_id = {
        session.get("session_id"): session
        for session in declared_sessions
        if isinstance(session, Mapping)
    }
    if len(sessions_by_id) != 4 or None in sessions_by_id:
        raise N2PhysicalAnalysisError("physical session identities are not disjoint")
    records: list[dict[str, Any]] = []
    covered: set[str] = set()
    for cell in range(1, 5):
        cell_id = f"Q{cell}"
        primer = bundles[f"q{cell}-map-primer"]
        target = bundles[f"q{cell}-target"]
        primer_identity = primer.action.get("identity", {})
        target_identity = target.action.get("identity", {})
        session_id = primer_identity.get("session_id")
        prior = target_identity.get("prior")
        session = sessions_by_id.get(session_id)
        expected_ids = [
            primer.action["action_identity_sha256"],
            target.action["action_identity_sha256"],
        ]
        if (
            target_identity.get("session_id") != session_id
            or session_id in covered
            or not isinstance(session, Mapping)
            or session.get("cell_id") != cell_id
            or session.get("action_identity_sha256s") != expected_ids
            or primer_identity.get("prior") is not None
            or not isinstance(prior, Mapping)
            or prior.get("action_identity_sha256") != expected_ids[0]
            or primer.evidence.get("prior_result_file_sha256") is not None
            or target.evidence.get("prior_result_file_sha256")
            != primer.result_file_sha256
        ):
            raise N2PhysicalAnalysisError(
                f"{cell_id} is not one exact disjoint MAP-to-target session"
            )
        confirmations = target.evidence.get("confirmations")
        continuity_names = (
            "map_fidelity_from_same_cell_primer",
            "esp32_not_restarted_since_primer",
            "no_j2_disconnect_since_primer",
            "no_panel_power_cycle_since_primer",
            "no_other_visible_refresh_since_primer",
        )
        if not isinstance(confirmations, Mapping) or any(
            confirmations.get(name) is not True for name in continuity_names
        ):
            raise N2PhysicalAnalysisError(f"{cell_id} MAP-to-target continuity changed")
        covered.add(str(session_id))
        records.append(
            {
                "cell_id": cell_id,
                "session_id": session_id,
                "primer_action_key": primer.key,
                "primer_action_identity_sha256": expected_ids[0],
                "primer_result_file_sha256": primer.result_file_sha256,
                "target_action_key": target.key,
                "target_action_identity_sha256": expected_ids[1],
                "target_result_file_sha256": target.result_file_sha256,
                "target_prior_result_file_sha256": target.evidence[
                    "prior_result_file_sha256"
                ],
                "same_cell_prior_verified": True,
                "continuity_confirmed": True,
            }
        )
    if covered != set(sessions_by_id):
        raise N2PhysicalAnalysisError("physical sessions contain uncovered or reused actions")
    return records


def _claim_fields(bundle: _PhysicalResult) -> tuple[str, str, str]:
    claim = bundle.evidence.get("claim")
    if not isinstance(claim, Mapping):
        raise N2PhysicalAnalysisError(f"{bundle.key} consumed claim reference is missing")
    filename = _text(claim.get("filename"), label=f"{bundle.key} claim filename")
    file_sha = _hash(claim.get("file_sha256"), label=f"{bundle.key} claim file")
    attempt = _text(bundle.evidence.get("attempt_id"), label=f"{bundle.key} attempt id")
    if (
        claim.get("action_identity_sha256")
        != bundle.action["action_identity_sha256"]
        or claim.get("attempt_id") != attempt
        or claim.get("state")
        != "authorization_permanently_consumed_do_not_rerun"
    ):
        raise N2PhysicalAnalysisError(f"{bundle.key} consumed claim binding changed")
    return filename, file_sha, attempt


def analyze_n2p_physical_campaign(
    result_directories: Mapping[str, Path],
    *,
    reviewer_key_file: Path,
) -> dict[str, Any]:
    """Deep-validate eight physical chains and return canonical sealed analysis."""

    if not isinstance(result_directories, Mapping) or set(result_directories) != set(
        EXPECTED_RESULT_KEYS
    ):
        raise N2PhysicalAnalysisError(
            "result_directories must contain exactly the eight physical action keys"
        )
    if not isinstance(reviewer_key_file, Path):
        raise N2PhysicalAnalysisError("reviewer_key_file must be pathlib.Path")
    resolved = {
        key: _safe_directory(result_directories[key], label=f"{key} result directory")
        for key in EXPECTED_RESULT_KEYS
    }
    if len(set(resolved.values())) != 8:
        raise N2PhysicalAnalysisError("physical result directory replay/duplication detected")
    bundles = {
        key: _load_physical_result(
            key,
            resolved[key],
            reviewer_key_file=reviewer_key_file,
        )
        for key in EXPECTED_RESULT_KEYS
    }
    source_binding = _validate_common_source(bundles)
    profile_states = _validate_usage_progression(bundles)
    sessions = _validate_sessions(bundles)

    claim_tuples = [_claim_fields(bundles[key]) for key in EXPECTED_RESULT_KEYS]
    result_shas = [bundles[key].result_file_sha256 for key in EXPECTED_RESULT_KEYS]
    if (
        len({item[0] for item in claim_tuples}) != 8
        or len({item[1] for item in claim_tuples}) != 8
        or len({item[2] for item in claim_tuples}) != 8
        or len(set(result_shas)) != 8
    ):
        raise N2PhysicalAnalysisError(
            "claim/result/attempt replay detected across physical actions"
        )

    chains = []
    for key, claim_tuple in zip(EXPECTED_RESULT_KEYS, claim_tuples):
        bundle = bundles[key]
        identity = bundle.action["identity"]
        chains.append(
            {
                "action_key": key,
                "cell_id": identity["cell_id"],
                "phase": identity["phase"],
                "session_id": identity["session_id"],
                "action_identity_sha256": bundle.action["action_identity_sha256"],
                "result_file_sha256": bundle.result_file_sha256,
                "state": bundle.result["state"],
                "completed_at": bundle.result["completed_at"],
                "attempt_id": claim_tuple[2],
                "claim_filename": claim_tuple[0],
                "claim_file_sha256": claim_tuple[1],
                "prior_result_file_sha256": bundle.evidence.get(
                    "prior_result_file_sha256"
                ),
                "profile_state": dict(profile_states[key]),
                "visual_pass": bundle.observation.get("visual_pass"),
                "electrical_pass": bundle.observation.get("electrical_pass"),
                "post_refresh_temperature_pass": bundle.observation.get(
                    "post_refresh_temperature_pass"
                ),
                "camera_capture_verified": (
                    bundle.camera_signature_sha256 is not None
                ),
                "camera_capture_file_sha256": bundle.finalization.get(
                    "camera_capture_file_sha256"
                ),
            }
        )

    targets = [bundles[f"q{cell}-target"] for cell in range(1, 5)]
    scorecard = []
    for target in targets:
        cell_id = target.action["identity"]["cell_id"]
        candidate = _candidate_for_cell(target.operator, cell_id)
        target_frame = target.action["identity"]["frame"]["sha256"]
        if candidate["frame_sha256"] != target_frame:
            raise N2PhysicalAnalysisError(f"{cell_id} target/candidate frame binding changed")
        assert target.score_total is not None and target.score_mean is not None
        visual = target.observation["visual"]
        scorecard.append(
            {
                "cell_id": cell_id,
                "action_key": target.key,
                "action_identity_sha256": target.action["action_identity_sha256"],
                "algorithm": candidate["algorithm"],
                "frame_sha256": target_frame,
                "target_result_file_sha256": target.result_file_sha256,
                "scores": {
                    dimension: visual[dimension] for dimension in SCORE_DIMENSIONS
                },
                "score_total": target.score_total,
                "score_mean": target.score_mean,
                "visual_pass": target.observation["visual_pass"],
                "electrical_pass": target.observation["electrical_pass"],
                "post_refresh_temperature_pass": target.observation[
                    "post_refresh_temperature_pass"
                ],
                "camera_capture_verified": target.camera_signature_sha256 is not None,
            }
        )

    totals = sorted({int(row["score_total"]) for row in scorecard}, reverse=True)
    rank_by_total = {total: index + 1 for index, total in enumerate(totals)}
    ranking = sorted(
        (
            {"rank": rank_by_total[int(row["score_total"])], **row}
            for row in scorecard
        ),
        key=lambda row: (row["rank"], row["cell_id"]),
    )
    highest = totals[0]
    top = [row for row in ranking if row["score_total"] == highest]
    top_tie = len(top) != 1

    primer_pass = all(
        bundles[f"q{cell}-map-primer"].result["state"] == ResultState.PASS.value
        and bundles[f"q{cell}-map-primer"].observation["visual_pass"] is True
        for cell in range(1, 5)
    )
    targets_pass = all(
        target.result["state"] == ResultState.PASS.value for target in targets
    )
    separated_gates_pass = all(
        target.observation["visual_pass"] is True
        and target.observation["electrical_pass"] is True
        and target.observation["post_refresh_temperature_pass"] is True
        for target in targets
    )
    session_gates_pass = len(sessions) == 4 and all(
        session["same_cell_prior_verified"] is True
        and session["continuity_confirmed"] is True
        for session in sessions
    )
    winner_gates_pass = (
        primer_pass
        and targets_pass
        and separated_gates_pass
        and session_gates_pass
        and not top_tie
    )

    signature_rows = [
        {
            "cell_id": target.action["identity"]["cell_id"],
            "capture_verified": target.camera_signature_sha256 is not None,
            "signature_sha256": target.camera_signature_sha256,
        }
        for target in targets
    ]
    signatures = [row["signature_sha256"] for row in signature_rows]
    all_captured = all(signature is not None for signature in signatures)
    same_signature = all_captured and len(set(signatures)) == 1
    camera_reasons = []
    if not all_captured:
        camera_reasons.append("verified_target_capture_missing")
    elif not same_signature:
        camera_reasons.append("camera_or_fixed_settings_differ_across_targets")

    selected_winner: Optional[dict[str, Any]] = None
    if winner_gates_pass:
        winner = top[0]
        selected_winner = {
            "cell_id": winner["cell_id"],
            "algorithm": winner["algorithm"],
            "action_key": winner["action_key"],
            "action_identity_sha256": winner["action_identity_sha256"],
            "frame_sha256": winner["frame_sha256"],
            "target_result_file_sha256": winner["target_result_file_sha256"],
            "score_total": winner["score_total"],
            "score_mean": winner["score_mean"],
            "selection_basis": "unique_highest_preregistered_six_dimension_total",
            "authorized_use": "N3_branch_selection_only",
            "algorithm_qualified": False,
            "population_inference": False,
        }
        selected_winner["winner_identity_sha256"] = _sha256(
            _canonical(selected_winner)
        )

    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": ANALYSIS_KIND,
        "mode": "offline-read-only-physical-analysis",
        "analyzer_contract_sha256": ANALYZER_CONTRACT_SHA256,
        "selection_interpretation": {
            "selection_scope": "one_exact_physical_bound_N2P_campaign_only",
            "target_candidate_count": 4,
            "observations_per_target_candidate": 1,
            "score_type": "single_supervised_manual_observation",
            "selected_winner_use": "N3_branch_selection_only",
            "algorithm_qualified": False,
            "population_inference": False,
            "general_algorithm_superiority_claim": False,
        },
        "source_binding": source_binding,
        "validated_chains": chains,
        "validated_sessions": sessions,
        "scorecard": scorecard,
        "ranking": ranking,
        "tie_state": {
            "top_score_total": highest,
            "top_tie": top_tie,
            "top_tied_cell_ids": [row["cell_id"] for row in top],
            "arbitrary_tie_break_performed": False,
        },
        "camera_comparability": {
            "comparable": bool(all_captured and same_signature),
            "verified_target_capture_count": sum(
                signature is not None for signature in signatures
            ),
            "same_camera_and_fixed_settings": bool(same_signature),
            "target_signatures": signature_rows,
            "reasons": camera_reasons,
            "affects_manual_score_winner": False,
        },
        "winner_gates": {
            "all_primer_map_pass": primer_pass,
            "all_target_results_pass": targets_pass,
            "visual_electrical_temperature_gates_pass": separated_gates_pass,
            "four_disjoint_same_cell_sessions_pass": session_gates_pass,
            "unique_top_total": not top_tie,
            "all_pass": winner_gates_pass,
        },
        "selected_winner": selected_winner,
        "hardware_io_performed": False,
        "network_io_performed": False,
        "claim_created": False,
        "authorization_created": False,
    }
    analysis = {
        **unsigned,
        "integrity": {
            "canonical_sha256": _sha256(_canonical(unsigned)),
            "canonical_sha256_scope": ANALYSIS_HASH_SCOPE,
        },
    }
    validate_n2p_physical_analysis(analysis)
    return analysis


def _validate_source_binding(value: object) -> Mapping[str, Any]:
    source = _exact(
        value,
        label="physical analysis source binding",
        keys={
            "operator_manifest_id",
            "operator_manifest_canonical_sha256",
            "operator_manifest_file_sha256",
            "physical_binding_canonical_sha256",
            "campaign_id",
            "campaign_canonical_sha256",
            "campaign_file_sha256",
            "panel",
            "firmware",
            "profile_lineage",
            "stable_source_snapshot_files",
            "scoring_contract_sha256",
            "camera_observation_contract_sha256",
        },
    )
    _text(source["operator_manifest_id"], label="operator manifest id")
    _text(source["campaign_id"], label="physical campaign id")
    for field in (
        "operator_manifest_canonical_sha256",
        "operator_manifest_file_sha256",
        "physical_binding_canonical_sha256",
        "campaign_canonical_sha256",
        "campaign_file_sha256",
        "scoring_contract_sha256",
        "camera_observation_contract_sha256",
    ):
        _hash(source[field], label=field)
    panel = _exact(
        source["panel"],
        label="physical analysis panel",
        keys={"model", "serial", "board_id", "pcb_revision"},
    )
    for field, item in panel.items():
        _text(item, label=f"panel {field}")
    if "UNBOUND" in panel["serial"].upper():
        raise N2PhysicalAnalysisError("physical analysis retained an unbound panel")
    firmware = source["firmware"]
    if not isinstance(firmware, Mapping):
        raise N2PhysicalAnalysisError("physical analysis firmware binding is missing")
    _text(firmware.get("build_tag"), label="firmware build tag")
    _hash(firmware.get("binary_sha256"), label="firmware binary")
    lineage = _exact(
        source["profile_lineage"],
        label="physical analysis production profile lineage",
        keys={
            "profile_identity_policy",
            "profile_validity_policy",
            "limit_authority_identity_policy",
            "limit_authority_safety_contract_sha256",
            "reviewer_id",
            "reviewer_key_id",
            "panel",
            "firmware",
            "action_allowlist",
            "limits",
        },
    )
    if lineage["profile_identity_policy"] != "unique-approved-profile-per-action":
        raise N2PhysicalAnalysisError("profile identity policy changed")
    if (
        lineage["profile_validity_policy"]
        != "independently-deep-validated-per-action"
    ):
        raise N2PhysicalAnalysisError("profile validity policy changed")
    if (
        lineage["limit_authority_identity_policy"]
        != "unique-reviewed-authority-per-action"
    ):
        raise N2PhysicalAnalysisError("limit authority identity policy changed")
    _text(lineage["reviewer_id"], label="profile reviewer id")
    _hash(lineage["reviewer_key_id"], label="reviewer key id")
    _hash(
        lineage["limit_authority_safety_contract_sha256"],
        label="limit authority safety contract",
    )
    if lineage["panel"] != panel or lineage["firmware"] != firmware:
        raise N2PhysicalAnalysisError("analysis profile-lineage panel/build binding changed")
    allowlist = lineage["action_allowlist"]
    if not isinstance(allowlist, list) or len(allowlist) != 8:
        raise N2PhysicalAnalysisError("profile lineage lacks the complete eight-action allowlist")
    allowlist_shas: set[str] = set()
    for item in allowlist:
        if not isinstance(item, Mapping):
            raise N2PhysicalAnalysisError("profile action allowlist item is invalid")
        allowlist_shas.add(
            _hash(item.get("action_identity_sha256"), label="allowed action identity")
        )
        if item.get("maximum_uses") != 1:
            raise N2PhysicalAnalysisError("profile action allowlist maximum use changed")
    if len(allowlist_shas) != 8:
        raise N2PhysicalAnalysisError("profile action allowlist identity is duplicated")
    if not isinstance(lineage["limits"], Mapping) or not lineage["limits"]:
        raise N2PhysicalAnalysisError("profile limit envelope is missing")
    snapshots = _validate_snapshot_files(
        source["stable_source_snapshot_files"],
        key="analysis stable",
        filenames=STABLE_SOURCE_SNAPSHOT_FILENAMES,
    )
    if (
        snapshots[fixed.COPIED_OPERATOR_FILENAME]["sha256"]
        != source["operator_manifest_file_sha256"]
        or snapshots[fixed.COPIED_CAMPAIGN_FILENAME]["sha256"]
        != source["campaign_file_sha256"]
        or snapshots[fixed.COPIED_FIRMWARE_FILENAME]["sha256"]
        != firmware["binary_sha256"]
    ):
        raise N2PhysicalAnalysisError("analysis source snapshot/file binding changed")
    return source


def validate_n2p_physical_analysis(
    analysis: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Validate a sealed physical analysis without reopening result directories."""

    root = _exact(
        analysis,
        label="physical N2P analysis",
        keys={
            "schema_version",
            "kind",
            "mode",
            "analyzer_contract_sha256",
            "selection_interpretation",
            "source_binding",
            "validated_chains",
            "validated_sessions",
            "scorecard",
            "ranking",
            "tie_state",
            "camera_comparability",
            "winner_gates",
            "selected_winner",
            "hardware_io_performed",
            "network_io_performed",
            "claim_created",
            "authorization_created",
            "integrity",
        },
    )
    unsigned = dict(root)
    integrity = unsigned.pop("integrity")
    if (
        not isinstance(integrity, Mapping)
        or set(integrity) != {"canonical_sha256", "canonical_sha256_scope"}
        or integrity.get("canonical_sha256") != _sha256(_canonical(unsigned))
        or integrity.get("canonical_sha256_scope") != ANALYSIS_HASH_SCOPE
    ):
        raise N2PhysicalAnalysisError("physical analysis canonical integrity is invalid")
    expected_interpretation = {
        "selection_scope": "one_exact_physical_bound_N2P_campaign_only",
        "target_candidate_count": 4,
        "observations_per_target_candidate": 1,
        "score_type": "single_supervised_manual_observation",
        "selected_winner_use": "N3_branch_selection_only",
        "algorithm_qualified": False,
        "population_inference": False,
        "general_algorithm_superiority_claim": False,
    }
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != ANALYSIS_KIND
        or root["mode"] != "offline-read-only-physical-analysis"
        or root["analyzer_contract_sha256"] != ANALYZER_CONTRACT_SHA256
        or root["selection_interpretation"] != expected_interpretation
        or any(
            root[field] is not False
            for field in (
                "hardware_io_performed",
                "network_io_performed",
                "claim_created",
                "authorization_created",
            )
        )
    ):
        raise N2PhysicalAnalysisError("physical analysis identity/scope changed")
    _validate_source_binding(root["source_binding"])

    chains = root["validated_chains"]
    if not isinstance(chains, list) or len(chains) != 8:
        raise N2PhysicalAnalysisError("physical analysis requires eight validated chains")
    chain_by_key: dict[str, Mapping[str, Any]] = {}
    attempts: set[str] = set()
    claim_names: set[str] = set()
    claim_shas: set[str] = set()
    result_shas: set[str] = set()
    profile_states: dict[str, Mapping[str, Any]] = {}
    profile_ids: set[str] = set()
    profile_canonical_shas: set[str] = set()
    profile_file_shas: set[str] = set()
    profile_review_shas: set[str] = set()
    authority_file_shas: set[str] = set()
    usage_file_shas: set[str] = set()
    lineage = root["source_binding"]["profile_lineage"]
    for expected_key, chain in zip(EXPECTED_RESULT_KEYS, chains):
        item = _exact(
            chain,
            label=f"{expected_key} validated chain",
            keys={
                "action_key",
                "cell_id",
                "phase",
                "session_id",
                "action_identity_sha256",
                "result_file_sha256",
                "state",
                "completed_at",
                "attempt_id",
                "claim_filename",
                "claim_file_sha256",
                "prior_result_file_sha256",
                "profile_state",
                "visual_pass",
                "electrical_pass",
                "post_refresh_temperature_pass",
                "camera_capture_verified",
                "camera_capture_file_sha256",
            },
        )
        cell_id, phase = _expected_key_parts(expected_key)
        if (
            item["action_key"] != expected_key
            or item["cell_id"] != cell_id
            or item["phase"] != phase
            or item["state"] not in {ResultState.PASS.value, ResultState.FAIL.value}
            or any(
                type(item[field]) is not bool
                for field in (
                    "visual_pass",
                    "electrical_pass",
                    "post_refresh_temperature_pass",
                    "camera_capture_verified",
                )
            )
        ):
            raise N2PhysicalAnalysisError("validated physical chain identity changed")
        _text(item["session_id"], label=f"{expected_key} session id")
        _hash(item["action_identity_sha256"], label=f"{expected_key} action identity")
        result_sha = _hash(item["result_file_sha256"], label=f"{expected_key} result")
        _rfc3339(item["completed_at"], label=f"{expected_key} completed_at")
        attempt = _text(item["attempt_id"], label=f"{expected_key} attempt id")
        claim_name = _text(item["claim_filename"], label=f"{expected_key} claim filename")
        claim_sha = _hash(item["claim_file_sha256"], label=f"{expected_key} claim file")
        prior = item["prior_result_file_sha256"]
        if phase == "map-primer":
            if prior is not None:
                raise N2PhysicalAnalysisError("MAP chain gained prior result")
        else:
            _hash(prior, label=f"{expected_key} prior result")
        capture_sha = item["camera_capture_file_sha256"]
        if item["camera_capture_verified"]:
            _hash(capture_sha, label=f"{expected_key} camera capture")
        elif capture_sha is not None:
            raise N2PhysicalAnalysisError("uncaptured chain gained camera SHA")
        profile_state = _exact(
            item["profile_state"],
            label=f"{expected_key} profile state",
            keys={
                "profile_id",
                "profile_version",
                "valid_from",
                "expires_at",
                "profile_canonical_sha256",
                "profile_file_sha256",
                "profile_review_artifact_file_sha256",
                "limit_authority_file_sha256",
                "usage_evidence_file_sha256",
                "cumulative_visible_refresh_count",
                "session_visible_refresh_count",
                "consecutive_visible_refresh_count",
                "last_visible_refresh_completed_at",
                "snapshot_at",
            },
        )
        profile_ids.add(
            _text(profile_state["profile_id"], label=f"{expected_key} profile id")
        )
        _text(profile_state["profile_version"], label=f"{expected_key} profile version")
        valid_from = _rfc3339(
            profile_state["valid_from"], label=f"{expected_key} profile valid_from"
        )
        expires_at = _rfc3339(
            profile_state["expires_at"], label=f"{expected_key} profile expires_at"
        )
        if valid_from >= expires_at:
            raise N2PhysicalAnalysisError(
                f"{expected_key} profile validity interval is empty or reversed"
            )
        profile_canonical_shas.add(
            _hash(
                profile_state["profile_canonical_sha256"],
                label=f"{expected_key} profile canonical identity",
            )
        )
        profile_file_shas.add(
            _hash(
                profile_state["profile_file_sha256"],
                label=f"{expected_key} profile file",
            )
        )
        profile_review_shas.add(
            _hash(
                profile_state["profile_review_artifact_file_sha256"],
                label=f"{expected_key} profile review artifact",
            )
        )
        authority_file_shas.add(
            _hash(
                profile_state["limit_authority_file_sha256"],
                label=f"{expected_key} limit authority file",
            )
        )
        usage_file_shas.add(
            _hash(
                profile_state["usage_evidence_file_sha256"],
                label=f"{expected_key} usage evidence file",
            )
        )
        for field in (
            "cumulative_visible_refresh_count",
            "session_visible_refresh_count",
            "consecutive_visible_refresh_count",
        ):
            if type(profile_state[field]) is not int or profile_state[field] < 0:
                raise N2PhysicalAnalysisError(
                    f"{expected_key} profile usage counter is invalid"
                )
        _rfc3339(
            profile_state["snapshot_at"], label=f"{expected_key} usage snapshot_at"
        )
        if profile_state["last_visible_refresh_completed_at"] is not None:
            _rfc3339(
                profile_state["last_visible_refresh_completed_at"],
                label=f"{expected_key} usage last refresh",
            )
        profile_states[expected_key] = profile_state
        attempts.add(attempt)
        claim_names.add(claim_name)
        claim_shas.add(claim_sha)
        result_shas.add(result_sha)
        chain_by_key[expected_key] = item
    if not all(len(values) == 8 for values in (attempts, claim_names, claim_shas, result_shas)):
        raise N2PhysicalAnalysisError("physical analysis contains replayed chain identity")
    allowed_action_shas = {
        item["action_identity_sha256"]
        for item in lineage["action_allowlist"]
        if isinstance(item, Mapping)
    }
    if allowed_action_shas != {
        chain["action_identity_sha256"] for chain in chain_by_key.values()
    }:
        raise N2PhysicalAnalysisError(
            "physical analysis chains differ from the complete profile allowlist"
        )
    if not all(
        len(values) == 8
        for values in (
            profile_ids,
            profile_canonical_shas,
            profile_file_shas,
            profile_review_shas,
            authority_file_shas,
            usage_file_shas,
        )
    ):
        raise N2PhysicalAnalysisError("physical analysis reused a per-action profile snapshot")
    base_count = profile_states[EXPECTED_RESULT_KEYS[0]][
        "cumulative_visible_refresh_count"
    ]
    prior_completed = None
    for index, key in enumerate(EXPECTED_RESULT_KEYS):
        state = profile_states[key]
        phase = _expected_key_parts(key)[1]
        expected_session_count = 0 if phase == "map-primer" else 1
        snapshot_at = _rfc3339(
            state["snapshot_at"], label=f"{key} usage snapshot_at"
        )
        last_value = state["last_visible_refresh_completed_at"]
        last = (
            None
            if last_value is None
            else _rfc3339(last_value, label=f"{key} usage last refresh")
        )
        if (
            state["cumulative_visible_refresh_count"] != base_count + index
            or state["session_visible_refresh_count"] != expected_session_count
            or state["consecutive_visible_refresh_count"] != expected_session_count
            or (
                prior_completed is not None
                and (
                    last is None
                    or last < prior_completed
                    or snapshot_at < prior_completed
                )
            )
        ):
            raise N2PhysicalAnalysisError("physical analysis usage progression changed")
        prior_completed = _rfc3339(
            chain_by_key[key]["completed_at"], label=f"{key} completed_at"
        )

    sessions = root["validated_sessions"]
    if not isinstance(sessions, list) or len(sessions) != 4:
        raise N2PhysicalAnalysisError("physical analysis requires four validated sessions")
    seen_session_ids: set[str] = set()
    for cell, session in enumerate(sessions, start=1):
        item = _exact(
            session,
            label=f"Q{cell} validated session",
            keys={
                "cell_id",
                "session_id",
                "primer_action_key",
                "primer_action_identity_sha256",
                "primer_result_file_sha256",
                "target_action_key",
                "target_action_identity_sha256",
                "target_result_file_sha256",
                "target_prior_result_file_sha256",
                "same_cell_prior_verified",
                "continuity_confirmed",
            },
        )
        primer_key = f"q{cell}-map-primer"
        target_key = f"q{cell}-target"
        primer = chain_by_key[primer_key]
        target = chain_by_key[target_key]
        if (
            item["cell_id"] != f"Q{cell}"
            or item["session_id"] in seen_session_ids
            or item["session_id"] != primer["session_id"]
            or item["session_id"] != target["session_id"]
            or item["primer_action_key"] != primer_key
            or item["target_action_key"] != target_key
            or item["primer_action_identity_sha256"]
            != primer["action_identity_sha256"]
            or item["target_action_identity_sha256"]
            != target["action_identity_sha256"]
            or item["primer_result_file_sha256"] != primer["result_file_sha256"]
            or item["target_result_file_sha256"] != target["result_file_sha256"]
            or item["target_prior_result_file_sha256"]
            != primer["result_file_sha256"]
            or target["prior_result_file_sha256"] != primer["result_file_sha256"]
            or item["same_cell_prior_verified"] is not True
            or item["continuity_confirmed"] is not True
        ):
            raise N2PhysicalAnalysisError("validated MAP-to-target session changed")
        seen_session_ids.add(str(item["session_id"]))

    scorecard = root["scorecard"]
    if not isinstance(scorecard, list) or len(scorecard) != 4:
        raise N2PhysicalAnalysisError("physical analysis scorecard requires four targets")
    normalized_rows: list[dict[str, Any]] = []
    for cell, row in enumerate(scorecard, start=1):
        item = _exact(
            row,
            label=f"Q{cell} scorecard row",
            keys={
                "cell_id",
                "action_key",
                "action_identity_sha256",
                "algorithm",
                "frame_sha256",
                "target_result_file_sha256",
                "scores",
                "score_total",
                "score_mean",
                "visual_pass",
                "electrical_pass",
                "post_refresh_temperature_pass",
                "camera_capture_verified",
            },
        )
        key = f"q{cell}-target"
        chain = chain_by_key[key]
        scores = item["scores"]
        if (
            item["cell_id"] != f"Q{cell}"
            or item["action_key"] != key
            or item["action_identity_sha256"] != chain["action_identity_sha256"]
            or item["target_result_file_sha256"] != chain["result_file_sha256"]
            or not isinstance(scores, Mapping)
            or set(scores) != set(SCORE_DIMENSIONS)
            or any(
                item[field] is not chain[field]
                for field in (
                    "visual_pass",
                    "electrical_pass",
                    "post_refresh_temperature_pass",
                    "camera_capture_verified",
                )
            )
        ):
            raise N2PhysicalAnalysisError("physical scorecard target binding changed")
        _text(item["algorithm"], label=f"Q{cell} algorithm")
        _hash(item["frame_sha256"], label=f"Q{cell} target frame")
        values = [scores[dimension] for dimension in SCORE_DIMENSIONS]
        if any(type(score) is not int or not 1 <= score <= 5 for score in values):
            raise N2PhysicalAnalysisError("physical score values must be integer 1..5")
        total = sum(values)
        if item["score_total"] != total or item["score_mean"] != total / 6:
            raise N2PhysicalAnalysisError("physical score total/mean changed")
        normalized_rows.append(dict(item))

    totals = sorted({int(row["score_total"]) for row in normalized_rows}, reverse=True)
    rank_by_total = {total: index + 1 for index, total in enumerate(totals)}
    expected_ranking = sorted(
        (
            {"rank": rank_by_total[int(row["score_total"])], **row}
            for row in normalized_rows
        ),
        key=lambda row: (row["rank"], row["cell_id"]),
    )
    if root["ranking"] != expected_ranking:
        raise N2PhysicalAnalysisError("physical ranking is not the frozen total rule")
    highest = totals[0]
    top = [row for row in expected_ranking if row["score_total"] == highest]
    top_tie = len(top) != 1
    expected_tie = {
        "top_score_total": highest,
        "top_tie": top_tie,
        "top_tied_cell_ids": [row["cell_id"] for row in top],
        "arbitrary_tie_break_performed": False,
    }
    if root["tie_state"] != expected_tie:
        raise N2PhysicalAnalysisError("physical analysis tie state changed")

    camera = _exact(
        root["camera_comparability"],
        label="physical camera comparability",
        keys={
            "comparable",
            "verified_target_capture_count",
            "same_camera_and_fixed_settings",
            "target_signatures",
            "reasons",
            "affects_manual_score_winner",
        },
    )
    signature_rows = camera["target_signatures"]
    if not isinstance(signature_rows, list) or len(signature_rows) != 4:
        raise N2PhysicalAnalysisError("physical camera signatures require four targets")
    signatures: list[Optional[str]] = []
    for cell, signature_row in enumerate(signature_rows, start=1):
        signature = _exact(
            signature_row,
            label=f"Q{cell} camera signature",
            keys={"cell_id", "capture_verified", "signature_sha256"},
        )
        row = normalized_rows[cell - 1]
        if (
            signature["cell_id"] != f"Q{cell}"
            or type(signature["capture_verified"]) is not bool
            or signature["capture_verified"] is not row["camera_capture_verified"]
        ):
            raise N2PhysicalAnalysisError("camera signature/scorecard binding changed")
        value = signature["signature_sha256"]
        if signature["capture_verified"]:
            signatures.append(_hash(value, label=f"Q{cell} camera signature"))
        elif value is not None:
            raise N2PhysicalAnalysisError("uncaptured target gained camera signature")
        else:
            signatures.append(None)
    all_captured = all(signature is not None for signature in signatures)
    same_signature = all_captured and len(set(signatures)) == 1
    reasons = (
        []
        if all_captured and same_signature
        else [
            (
                "camera_or_fixed_settings_differ_across_targets"
                if all_captured
                else "verified_target_capture_missing"
            )
        ]
    )
    expected_camera = {
        "comparable": bool(all_captured and same_signature),
        "verified_target_capture_count": sum(
            signature is not None for signature in signatures
        ),
        "same_camera_and_fixed_settings": bool(same_signature),
        "target_signatures": signature_rows,
        "reasons": reasons,
        "affects_manual_score_winner": False,
    }
    if camera != expected_camera:
        raise N2PhysicalAnalysisError("physical camera-comparability result changed")

    primer_pass = all(
        chain_by_key[f"q{cell}-map-primer"]["state"] == ResultState.PASS.value
        and chain_by_key[f"q{cell}-map-primer"]["visual_pass"] is True
        for cell in range(1, 5)
    )
    target_pass = all(
        chain_by_key[f"q{cell}-target"]["state"] == ResultState.PASS.value
        for cell in range(1, 5)
    )
    separated = all(
        row["visual_pass"] is True
        and row["electrical_pass"] is True
        and row["post_refresh_temperature_pass"] is True
        for row in normalized_rows
    )
    expected_gates = {
        "all_primer_map_pass": primer_pass,
        "all_target_results_pass": target_pass,
        "visual_electrical_temperature_gates_pass": separated,
        "four_disjoint_same_cell_sessions_pass": True,
        "unique_top_total": not top_tie,
        "all_pass": primer_pass and target_pass and separated and not top_tie,
    }
    if root["winner_gates"] != expected_gates:
        raise N2PhysicalAnalysisError("physical winner gates changed")
    winner = root["selected_winner"]
    if not expected_gates["all_pass"]:
        if winner is not None:
            raise N2PhysicalAnalysisError("physical analysis selected winner with failed gates")
    else:
        row = top[0]
        expected_winner = {
            "cell_id": row["cell_id"],
            "algorithm": row["algorithm"],
            "action_key": row["action_key"],
            "action_identity_sha256": row["action_identity_sha256"],
            "frame_sha256": row["frame_sha256"],
            "target_result_file_sha256": row["target_result_file_sha256"],
            "score_total": row["score_total"],
            "score_mean": row["score_mean"],
            "selection_basis": "unique_highest_preregistered_six_dimension_total",
            "authorized_use": "N3_branch_selection_only",
            "algorithm_qualified": False,
            "population_inference": False,
        }
        expected_winner["winner_identity_sha256"] = _sha256(
            _canonical(expected_winner)
        )
        if winner != expected_winner:
            raise N2PhysicalAnalysisError("physical selected N3 branch identity changed")
    return analysis


def write_n2p_physical_analysis(
    result_directories: Mapping[str, Path],
    output_file: Path,
    *,
    reviewer_key_file: Path,
) -> Mapping[str, Any]:
    """Analyze and exclusively publish one canonical analysis JSON file."""

    analysis = analyze_n2p_physical_campaign(
        result_directories, reviewer_key_file=reviewer_key_file
    )
    if not isinstance(output_file, Path):
        raise N2PhysicalAnalysisError("output_file must be pathlib.Path")
    try:
        require_local_regular_path_syntax(output_file, label="physical N2P analysis output")
        if os.path.lexists(output_file):
            raise N2PhysicalAnalysisError("physical analysis output already exists")
        fixed._reject_reparse_path_chain(
            output_file.parent, label="physical N2P analysis output parent"
        )
        parent = output_file.parent.resolve(strict=True)
    except N2PhysicalAnalysisError:
        raise
    except (LocalPathSafetyError, fixed.N2PhysicalOnceError, OSError) as error:
        raise N2PhysicalAnalysisError(f"analysis output path is unsafe: {error}") from error
    try:
        fixed._atomic_commit(
            parent / output_file.name,
            canonical_json_bytes(analysis),
            unknown_after_commit=False,
        )
    except fixed.N2PhysicalOnceError as error:
        raise N2PhysicalAnalysisError(str(error)) from error
    return analysis


# Compatibility-shaped aliases make migration from the legacy analyzer explicit
# without weakening the physical reviewer-key requirement.
analyze_n2p_campaign = analyze_n2p_physical_campaign
validate_n2p_analysis = validate_n2p_physical_analysis
write_n2p_analysis = write_n2p_physical_analysis


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for key in EXPECTED_RESULT_KEYS:
        parser.add_argument(f"--{key}-dir", type=Path, required=True)
    parser.add_argument("--reviewer-key", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    directories = {
        key: getattr(args, key.replace("-", "_") + "_dir")
        for key in EXPECTED_RESULT_KEYS
    }
    try:
        analysis = (
            write_n2p_physical_analysis(
                directories,
                args.output,
                reviewer_key_file=args.reviewer_key,
            )
            if args.output is not None
            else analyze_n2p_physical_campaign(
                directories, reviewer_key_file=args.reviewer_key
            )
        )
    except N2PhysicalAnalysisError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(analysis, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ANALYSIS_KIND",
    "ANALYZER_CONTRACT",
    "ANALYZER_CONTRACT_SHA256",
    "EXPECTED_RESULT_KEYS",
    "N2PhysicalAnalysisError",
    "SCORE_DIMENSIONS",
    "analyze_n2p_campaign",
    "analyze_n2p_physical_campaign",
    "main",
    "parse_args",
    "validate_n2p_analysis",
    "validate_n2p_physical_analysis",
    "write_n2p_analysis",
    "write_n2p_physical_analysis",
]
