#!/usr/bin/env python3
"""Execute and replay one deeply authenticated physical N5 action.

The legacy N5 runner remains useful as a single-POST/outcome-commit/finalizer
engine, but its caller-supplied timestamps and self-sealed profile boundary are
not a production trust boundary.  This module supplies that boundary.  Every
live action replays the authenticated physical plan, loads the real campaign,
firmware, neutral limit-authority, usage, approval, and reviewer-key files,
uses an actual (injectable) wall clock, enforces the stricter of materialized
and authority schedules, and requires exact action/panel-plan/profile tokens
before the permanent claim can exist.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import math
from pathlib import Path
import sys
from typing import Any, Callable, Mapping, Optional, Sequence
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.extended_color import execution  # noqa: E402
from host.extended_color import n5_rc2g_protocol  # noqa: E402
from host.visible_refresh_campaign import (  # noqa: E402
    ProductionProfileError,
    ValidatedProductionProfile,
    canonical_json_bytes,
    load_validated_production_profile,
    read_local_regular_file,
)
from tools import mf1750_n5_fixed_execution as fixed  # noqa: E402
from tools import mf1750_n5_physical_campaign as physical_campaign  # noqa: E402


SCHEMA_VERSION = 1
CONTROL_KIND = "mf1750-n5-production-physical-action-controls"
PHYSICAL_PALETTE_AGGREGATE_KIND = (
    "mf1750-n5-production-physical-palette-aggregate"
)
PHYSICAL_TRANSITION_AGGREGATE_KIND = (
    "mf1750-n5-production-physical-transition-aggregate"
)
MAX_PROFILE_EVALUATION_AGE_SECONDS = 300.0
ACTION_TOKEN_PREFIX = "AUTHORIZE_ONE_VISIBLE_RC2G_N5_PHYSICAL"
PANEL_PLAN_TOKEN_PREFIX = "CONFIRM_N5_PHYSICAL_PANEL_PLAN"
PROFILE_TOKEN_PREFIX = "CONFIRM_N5_APPROVED_PRODUCTION_PROFILE"

PHYSICAL_PLAN_FILE = "N5-PRODUCTION-PHYSICAL-PLAN.json"
COMPILE_PROFILE_FILE = "N5-COMPILE-PROFILE.json"
SOURCE_MANIFEST_FILE = "N5-OFFLINE-SOURCE-MANIFEST.json"
PHYSICAL_ANCHOR_FILE = "N5-PHYSICAL-ANCHOR-CAMPAIGN.json"
PHYSICAL_CAMPAIGN_FILE = "N5-PHYSICAL-CAMPAIGN.json"
FIRMWARE_BINARY_FILE = "N5-RC2G-FIRMWARE.bin"
SCIENCE_REVIEW_EVIDENCE_FILE = "N5-STATIC-SCIENCE-REVIEW.bin"
SCIENCE_REVIEW_APPROVAL_FILE = "N5-STATIC-SCIENCE-APPROVAL.json"
LIMIT_AUTHORITY_FILE = "N5-LIMIT-AUTHORITY.json"
USAGE_EVIDENCE_FILE = "N5-USAGE-EVIDENCE.json"
PROFILE_REVIEW_FILE = "N5-PROFILE-REVIEW.json"
PRODUCTION_VALIDATION_FILE = "N5-PRODUCTION-VALIDATION.json"
PHYSICAL_CONTROLS_FILE = "N5-PHYSICAL-CONTROLS.json"

# A physical plan contains 73 full frames.  Recompiling it for every one of
# several result directories is intentionally exact but needlessly repeats
# the same expensive pure replay.  This small content-addressed cache keeps
# the security property: the key covers both every mapping and every original
# byte string held by the context, so any mutation misses the cache.
_VALIDATED_CONTEXT_CACHE: dict[str, bytes] = {}
_VALIDATED_CONTEXT_CACHE_LIMIT = 8
_VALIDATED_ACTION_RESULT_CACHE: dict[str, bytes] = {}
_VALIDATED_ACTION_RESULT_CACHE_LIMIT = 128


class N5PhysicalExecutionError(ValueError):
    """Physical N5 production evidence failed before claim or during replay."""


@dataclass(frozen=True)
class N5PhysicalContext:
    plan: Mapping[str, Any]
    plan_bytes: bytes
    inputs: physical_campaign.N5PhysicalCampaignInputs
    namespace: str
    minimum_interval_seconds: float
    planned_cooldown_seconds: float


@dataclass(frozen=True)
class N5ProductionFiles:
    profile: Path
    physical_campaign: Path
    firmware_binary: Path
    limit_authority: Path
    usage_evidence: Path
    review_artifact: Path
    reviewer_key: Path


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise N5PhysicalExecutionError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise N5PhysicalExecutionError(
            f"{label} must be an ISO-8601 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise N5PhysicalExecutionError(f"{label} must include a UTC offset")
    return parsed


def _finite(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise N5PhysicalExecutionError(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise N5PhysicalExecutionError(f"{label} must be a finite number")
    return number


def load_n5_physical_context(
    *,
    plan_file: Path,
    compile_profile_file: Path,
    source_manifest_file: Path,
    physical_anchor_campaign_file: Path,
    firmware_binary_file: Path,
    science_review_evidence_file: Path,
    science_review_approval_file: Path,
    science_reviewer_key_file: Path,
    namespace: str,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> N5PhysicalContext:
    inputs = physical_campaign.load_n5_physical_inputs(
        compile_profile_file=compile_profile_file,
        source_manifest_file=source_manifest_file,
        physical_anchor_campaign_file=physical_anchor_campaign_file,
        firmware_binary_file=firmware_binary_file,
        science_review_evidence_file=science_review_evidence_file,
        science_review_approval_file=science_review_approval_file,
        reviewer_key_file=science_reviewer_key_file,
    )
    plan = physical_campaign.load_validated_n5_physical_plan(
        plan_file,
        inputs=inputs,
        namespace=namespace,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )
    try:
        plan_payload = read_local_regular_file(
            plan_file,
            label="N5 production physical plan",
            maximum_bytes=physical_campaign.MAX_JSON_BYTES,
        ).payload
    except ProductionProfileError as error:
        raise N5PhysicalExecutionError(str(error)) from error
    return N5PhysicalContext(
        plan=plan,
        plan_bytes=plan_payload,
        inputs=inputs,
        namespace=namespace,
        minimum_interval_seconds=float(minimum_interval_seconds),
        planned_cooldown_seconds=float(planned_cooldown_seconds),
    )


def _physical_context_cache_key(context: N5PhysicalContext) -> str:
    inputs = context.inputs
    return _sha256(
        {
            "plan": context.plan,
            "plan_bytes_sha256": _sha256(context.plan_bytes),
            "compile_profile": inputs.compile_profile,
            "compile_profile_bytes_sha256": _sha256(
                inputs.compile_profile_bytes
            ),
            "source_manifest": inputs.source_manifest,
            "source_manifest_bytes_sha256": _sha256(
                inputs.source_manifest_bytes
            ),
            "physical_anchor": inputs.physical_anchor,
            "physical_anchor_bytes_sha256": _sha256(
                inputs.physical_anchor_bytes
            ),
            "firmware_binary_sha256": _sha256(inputs.firmware_binary),
            "science_review_evidence_sha256": _sha256(
                inputs.science_review_evidence
            ),
            "science_review_approval": inputs.science_review_approval,
            "science_review_approval_bytes_sha256": _sha256(
                inputs.science_review_approval_bytes
            ),
            "reviewer_key_sha256": _sha256(inputs.reviewer_key),
            "namespace": context.namespace,
            "minimum_interval_seconds": context.minimum_interval_seconds,
            "planned_cooldown_seconds": context.planned_cooldown_seconds,
        }
    )


def validate_n5_physical_context(context: N5PhysicalContext) -> Mapping[str, Any]:
    if not isinstance(context, N5PhysicalContext):
        raise N5PhysicalExecutionError("N5 physical context type changed")
    cache_key = _physical_context_cache_key(context)
    canonical_plan = canonical_json_bytes(context.plan)
    if _VALIDATED_CONTEXT_CACHE.get(cache_key) == canonical_plan:
        if context.plan_bytes != canonical_plan:
            raise N5PhysicalExecutionError("N5 physical plan actual bytes changed")
        return context.plan
    try:
        plan = physical_campaign.validate_n5_physical_plan(
            context.plan,
            context.inputs,
            namespace=context.namespace,
            minimum_interval_seconds=context.minimum_interval_seconds,
            planned_cooldown_seconds=context.planned_cooldown_seconds,
        )
    except physical_campaign.N5PhysicalCampaignError as error:
        raise N5PhysicalExecutionError(str(error)) from error
    if context.plan_bytes != canonical_json_bytes(plan):
        raise N5PhysicalExecutionError("N5 physical plan actual bytes changed")
    if len(_VALIDATED_CONTEXT_CACHE) >= _VALIDATED_CONTEXT_CACHE_LIMIT:
        _VALIDATED_CONTEXT_CACHE.pop(next(iter(_VALIDATED_CONTEXT_CACHE)))
    _VALIDATED_CONTEXT_CACHE[cache_key] = canonical_plan
    return plan


def _physical_result_cache_key(
    context: N5PhysicalContext,
    result_dir: Path,
    profile_reviewer_key_file: Path,
) -> str:
    if result_dir.is_symlink() or not result_dir.is_dir():
        raise N5PhysicalExecutionError("physical N5 result directory is missing")
    files: list[dict[str, Any]] = []
    for path in sorted(result_dir.iterdir(), key=lambda value: value.name):
        if path.is_symlink() or not path.is_file():
            raise N5PhysicalExecutionError(
                "physical N5 result directory contains a non-regular entry"
            )
        try:
            snapshot = read_local_regular_file(
                path,
                label=f"physical N5 cached result {path.name}",
                maximum_bytes=physical_campaign.MAX_JSON_BYTES,
            )
        except ProductionProfileError as error:
            raise N5PhysicalExecutionError(str(error)) from error
        files.append(
            {
                "name": path.name,
                "bytes": len(snapshot.payload),
                "sha256": snapshot.sha256,
            }
        )
    try:
        reviewer_key = read_local_regular_file(
            profile_reviewer_key_file,
            label="physical N5 profile reviewer key",
            maximum_bytes=physical_campaign.MAX_REVIEW_KEY_BYTES,
        )
    except ProductionProfileError as error:
        raise N5PhysicalExecutionError(str(error)) from error
    return _sha256(
        {
            "physical_context_content_key": _physical_context_cache_key(context),
            "result_files": files,
            "profile_reviewer_key_sha256": reviewer_key.sha256,
        }
    )


def _snapshot(context: N5PhysicalContext, action_key: str) -> execution.ActionSnapshot:
    plan = validate_n5_physical_context(context)
    return _snapshot_from_plan(plan, action_key)


def _snapshot_from_plan(
    plan: Mapping[str, Any], action_key: str
) -> execution.ActionSnapshot:
    try:
        return execution.load_action_snapshot(plan["execution_contract"], action_key)
    except execution.N5ExecutionError as error:
        raise N5PhysicalExecutionError(f"physical N5 action is invalid: {error}") from error


def _load_production_for_snapshot(
    context: N5PhysicalContext,
    snapshot: execution.ActionSnapshot,
    files: N5ProductionFiles,
    *,
    evaluated_at: str,
) -> ValidatedProductionProfile:
    try:
        production = load_validated_production_profile(
            profile_file=files.profile,
            campaign_file=files.physical_campaign,
            firmware_binary_file=files.firmware_binary,
            supplier_limits_file=files.limit_authority,
            usage_evidence_file=files.usage_evidence,
            review_artifact_file=files.review_artifact,
            reviewer_key_file=files.reviewer_key,
            evaluated_at=evaluated_at,
        )
    except ProductionProfileError as error:
        raise N5PhysicalExecutionError(
            f"deep N5 production profile failed: {error}"
        ) from error
    campaign = context.plan["runtime_manifest"]["shared_p0"]
    if (
        production.report.get("production_ready") is not True
        or production.report.get("deep_bindings_valid") is not True
        or production.inputs.campaign != campaign
        or production.inputs.campaign
        != context.plan["execution_contract"]["p0_campaign"]
        or production.inputs.firmware_binary.sha256
        != context.plan["source"]["firmware_binary_sha256"]
        or production.report.get("action_allowlist_count") != 73
        or len(production.profile["action_allowlist"]) != 73
    ):
        raise N5PhysicalExecutionError(
            "production profile does not bind the complete physical N5 campaign"
        )
    return production


def load_n5_physical_production_profile(
    context: N5PhysicalContext,
    action_key: str,
    files: N5ProductionFiles,
    *,
    evaluated_at: str,
) -> ValidatedProductionProfile:
    snapshot = _snapshot(context, action_key)
    return _load_production_for_snapshot(
        context, snapshot, files, evaluated_at=evaluated_at
    )


def required_action_token(context: N5PhysicalContext, action_key: str) -> str:
    snapshot = _snapshot(context, action_key)
    return _required_action_token(context, snapshot)


def _required_action_token(
    context: N5PhysicalContext, snapshot: execution.ActionSnapshot
) -> str:
    return (
        f"{ACTION_TOKEN_PREFIX}__PLAN_{context.plan['integrity']['canonical_sha256']}"
        f"__ACTION_{snapshot.action['action_identity_sha256']}"
        "__NO_RETRY_NO_RECOVERY"
    )


def required_panel_plan_token(context: N5PhysicalContext, action_key: str) -> str:
    snapshot = _snapshot(context, action_key)
    return _required_panel_plan_token(context, snapshot)


def _required_panel_plan_token(
    context: N5PhysicalContext, snapshot: execution.ActionSnapshot
) -> str:
    panel_sha = _sha256(context.plan["execution_contract"]["p0_campaign"]["panel"])
    return (
        f"{PANEL_PLAN_TOKEN_PREFIX}__PANEL_{panel_sha}"
        f"__PLAN_{context.plan['integrity']['canonical_sha256']}"
        f"__ACTION_{snapshot.action['action_identity_sha256']}"
    )


def required_profile_token(production: ValidatedProductionProfile) -> str:
    review = production.review_artifact_file
    if review is None or production.reviewer_key_id is None:
        raise N5PhysicalExecutionError(
            "approved production profile lost review/key identity"
        )
    return (
        f"{PROFILE_TOKEN_PREFIX}"
        f"__PROFILE_{production.profile['integrity']['canonical_sha256']}"
        f"__FILE_{production.profile_file.sha256}"
        f"__REVIEW_{review.sha256}"
        f"__KEY_{production.reviewer_key_id}"
    )


def authorization_confirmation_sha256(
    *, action_token: str, panel_plan_token: str, profile_token: str
) -> str:
    return _sha256(
        {
            "action_token_sha256": _sha256(action_token.encode("utf-8")),
            "panel_plan_token_sha256": _sha256(
                panel_plan_token.encode("utf-8")
            ),
            "profile_token_sha256": _sha256(profile_token.encode("utf-8")),
        }
    )


def validate_live_evaluation_age(evaluated_at: str, claimed_at: str) -> float:
    evaluated = _timestamp(evaluated_at, label="profile evaluated_at")
    claimed = _timestamp(claimed_at, label="actual claimed_at")
    age = (claimed - evaluated).total_seconds()
    if age < 0 or age > MAX_PROFILE_EVALUATION_AGE_SECONDS:
        raise N5PhysicalExecutionError(
            "production profile evaluation is not within 300 seconds of claim"
        )
    return age


def _schedule_controls(
    context: N5PhysicalContext,
    snapshot: execution.ActionSnapshot,
    production: ValidatedProductionProfile,
    *,
    evaluated_at: str,
    claimed_at: str,
) -> dict[str, Any]:
    age = validate_live_evaluation_age(evaluated_at, claimed_at)
    limits = production.profile["limits"]
    usage = production.profile["usage"]
    materialized_interval = float(
        context.plan["operator_process_schedule"]["minimum_interval_seconds"]
    )
    authority_interval = float(limits["minimum_interval_seconds"])
    effective_interval = max(materialized_interval, authority_interval)
    materialized_cooldown = float(
        context.plan["operator_process_schedule"]["planned_cooldown_seconds"]
    )
    authority_cooldown = float(limits["minimum_cooldown_seconds"])
    effective_cooldown = max(materialized_cooldown, authority_cooldown)
    last_value = usage["last_visible_refresh_completed_at"]
    last = (
        None
        if last_value is None
        else _timestamp(last_value, label="usage last visible completion")
    )
    claimed = _timestamp(claimed_at, label="actual claimed_at")
    elapsed = None if last is None else (claimed - last).total_seconds()
    if elapsed is not None and elapsed < 0:
        raise N5PhysicalExecutionError("usage evidence completion follows claim time")
    interval_applies = last is not None
    cooldown_applies = (
        last is not None
        and int(usage["cumulative_visible_refresh_count"]) > 0
        and int(usage["session_visible_refresh_count"]) == 0
    )
    if interval_applies and elapsed is not None and elapsed < effective_interval:
        raise N5PhysicalExecutionError(
            "effective physical minimum refresh interval has not elapsed"
        )
    if cooldown_applies and elapsed is not None and elapsed < effective_cooldown:
        raise N5PhysicalExecutionError(
            "effective physical inter-session cooldown has not elapsed"
        )
    identity_interval = float(
        snapshot.action["identity"]["schedule"][
            "minimum_interval_since_prior_seconds"
        ]
    )
    if snapshot.action["identity"]["prior"] is not None and identity_interval != materialized_interval:
        raise N5PhysicalExecutionError(
            "physical action identity lost the materialized interval"
        )
    if float(snapshot.session["planned_cooldown_seconds"]) != materialized_cooldown:
        raise N5PhysicalExecutionError(
            "physical session identity lost the materialized cooldown"
        )
    return {
        "profile_evaluated_at": evaluated_at,
        "claimed_at": claimed_at,
        "live_evaluation_age_seconds": age,
        "maximum_live_evaluation_age_seconds": MAX_PROFILE_EVALUATION_AGE_SECONDS,
        "schedule_reference_completed_at": last_value,
        "materialized_minimum_interval_seconds": materialized_interval,
        "authority_minimum_interval_seconds": authority_interval,
        "effective_minimum_interval_seconds": effective_interval,
        "minimum_interval_gate_applies": interval_applies,
        "minimum_interval_elapsed_seconds": elapsed,
        "materialized_planned_cooldown_seconds": materialized_cooldown,
        "authority_minimum_cooldown_seconds": authority_cooldown,
        "effective_minimum_cooldown_seconds": effective_cooldown,
        "minimum_cooldown_gate_applies": cooldown_applies,
        "minimum_cooldown_elapsed_seconds": elapsed if cooldown_applies else None,
        "schedule_gates_satisfied": True,
    }


def _physical_controls(
    context: N5PhysicalContext,
    snapshot: execution.ActionSnapshot,
    production: ValidatedProductionProfile,
    authorization: Mapping[str, Any],
    *,
    evaluated_at: str,
    claimed_at: str,
) -> dict[str, Any]:
    action_token = _required_action_token(context, snapshot)
    panel_token = _required_panel_plan_token(context, snapshot)
    profile_token = required_profile_token(production)
    schedule = _schedule_controls(
        context,
        snapshot,
        production,
        evaluated_at=evaluated_at,
        claimed_at=claimed_at,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": CONTROL_KIND,
        "plan_id": context.plan["plan_id"],
        "plan_canonical_sha256": context.plan["integrity"]["canonical_sha256"],
        "plan_file_sha256": _sha256(context.plan_bytes),
        "runtime_manifest_canonical_sha256": context.plan["runtime_manifest"][
            "integrity"
        ]["canonical_sha256"],
        "execution_contract_canonical_sha256": context.plan[
            "execution_contract"
        ]["integrity"]["canonical_sha256"],
        "physical_campaign_canonical_sha256": context.plan[
            "execution_contract"
        ]["p0_campaign"]["integrity"]["canonical_sha256"],
        "panel_canonical_sha256": _sha256(
            context.plan["execution_contract"]["p0_campaign"]["panel"]
        ),
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "profile_canonical_sha256": production.profile["integrity"][
            "canonical_sha256"
        ],
        "profile_file_sha256": production.profile_file.sha256,
        "limit_authority_file_sha256": production.inputs.limit_authority_file.sha256,
        "usage_evidence_file_sha256": production.inputs.usage_evidence_file.sha256,
        "profile_review_file_sha256": production.review_artifact_file.sha256,
        "profile_reviewer_key_id": production.reviewer_key_id,
        "authorization_file_sha256": _sha256(authorization),
        "authorization_confirmation_sha256": authorization_confirmation_sha256(
            action_token=action_token,
            panel_plan_token=panel_token,
            profile_token=profile_token,
        ),
        "action_token_sha256": _sha256(action_token.encode("utf-8")),
        "panel_plan_token_sha256": _sha256(panel_token.encode("utf-8")),
        "profile_token_sha256": _sha256(profile_token.encode("utf-8")),
        **schedule,
        "single_post_only": True,
        "automatic_advance": False,
        "automatic_retry": False,
        "automatic_recovery": False,
    }


def _verify_exact_tokens(
    context: N5PhysicalContext,
    snapshot: execution.ActionSnapshot,
    production: ValidatedProductionProfile,
    authorization: Mapping[str, Any],
    *,
    action_token: str,
    panel_plan_token: str,
    profile_token: str,
) -> None:
    expected_action = _required_action_token(context, snapshot)
    expected_panel = _required_panel_plan_token(context, snapshot)
    expected_profile = required_profile_token(production)
    values = (
        (action_token, expected_action, "exact action token"),
        (panel_plan_token, expected_panel, "exact panel/plan token"),
        (profile_token, expected_profile, "exact production-profile token"),
    )
    for supplied, expected, label in values:
        if not isinstance(supplied, str) or not hmac.compare_digest(supplied, expected):
            raise N5PhysicalExecutionError(f"{label} is required")
    expected_confirmation = authorization_confirmation_sha256(
        action_token=expected_action,
        panel_plan_token=expected_panel,
        profile_token=expected_profile,
    )
    observed = authorization.get("confirmation_sha256")
    if not isinstance(observed, str) or not hmac.compare_digest(
        observed, expected_confirmation
    ):
        raise N5PhysicalExecutionError(
            "external authorization does not bind all three exact physical tokens"
        )


def _validate_live_prior(
    context: N5PhysicalContext,
    snapshot: execution.ActionSnapshot,
    production: ValidatedProductionProfile,
    prior_bundle: Optional[Mapping[str, Any]],
    prior_result_dir: Optional[Path],
    *,
    profile_reviewer_key_file: Path,
) -> None:
    declaration = snapshot.action["identity"]["prior"]
    if declaration is None:
        if prior_bundle is not None or prior_result_dir is not None:
            raise N5PhysicalExecutionError(
                "root physical N5 action must not receive prior evidence"
            )
        return
    if prior_bundle is None or prior_result_dir is None:
        raise N5PhysicalExecutionError(
            "dependent physical N5 action requires its prior result directory and item"
        )
    prior_item = _load_committed_action_item(prior_result_dir)
    if prior_bundle != prior_item:
        raise N5PhysicalExecutionError(
            "live prior item differs from its physical result directory"
        )
    validated = validate_n5_physical_action_result(
        context,
        prior_result_dir,
        profile_reviewer_key_file=profile_reviewer_key_file,
    )
    if (
        validated.get("state") != "PASS"
        or prior_item.get("action_identity_sha256")
        != declaration["action_identity_sha256"]
    ):
        raise N5PhysicalExecutionError(
            "live prior is not the exact physical finalized PASS predecessor"
        )
    usage = production.profile["usage"]
    if usage["last_visible_refresh_completed_at"] != prior_item["result"][
        "completed_at"
    ]:
        raise N5PhysicalExecutionError(
            "authenticated usage does not identify the exact immediate predecessor"
        )


def _context_artifacts(context: N5PhysicalContext) -> dict[str, bytes]:
    inputs = context.inputs
    return {
        PHYSICAL_PLAN_FILE: context.plan_bytes,
        COMPILE_PROFILE_FILE: inputs.compile_profile_bytes,
        SOURCE_MANIFEST_FILE: inputs.source_manifest_bytes,
        PHYSICAL_ANCHOR_FILE: inputs.physical_anchor_bytes,
        SCIENCE_REVIEW_EVIDENCE_FILE: inputs.science_review_evidence,
        SCIENCE_REVIEW_APPROVAL_FILE: inputs.science_review_approval_bytes,
    }


def _production_artifacts(
    production: ValidatedProductionProfile,
) -> dict[str, bytes]:
    review = production.review_artifact_file
    if review is None:
        raise N5PhysicalExecutionError("production profile review bytes are missing")
    return {
        PHYSICAL_CAMPAIGN_FILE: production.inputs.campaign_file.payload,
        FIRMWARE_BINARY_FILE: production.inputs.firmware_binary.payload,
        LIMIT_AUTHORITY_FILE: production.inputs.limit_authority_file.payload,
        USAGE_EVIDENCE_FILE: production.inputs.usage_evidence_file.payload,
        PROFILE_REVIEW_FILE: review.payload,
    }


def run_n5_physical_action_once(
    context: N5PhysicalContext,
    action_key: str,
    *,
    production_files: N5ProductionFiles,
    authorization: Mapping[str, Any],
    session_start: Mapping[str, Any],
    prior_bundle: Optional[Mapping[str, Any]],
    prior_result_dir: Optional[Path] = None,
    result_dir: Path,
    claim_root: Path,
    base_url: str,
    action_token: str,
    panel_plan_token: str,
    profile_token: str,
    start_temperature_c: int | float,
    confirm_supply_cv_current_normal: bool,
    confirm_j2_on: bool,
    confirm_physical_cutoff_available: bool,
    wall_clock: Callable[[], str] = _utc_now,
    transport: Optional[Any] = None,
    protocol_driver: Optional[Any] = None,
) -> dict[str, Any]:
    """Validate all physical authority, then consume one permanent claim."""

    plan = validate_n5_physical_context(context)
    contract = plan["execution_contract"]
    snapshot = _snapshot_from_plan(plan, action_key)
    evaluated_at = wall_clock()
    _timestamp(evaluated_at, label="actual profile evaluation time")
    production = _load_production_for_snapshot(
        context,
        snapshot,
        production_files,
        evaluated_at=evaluated_at,
    )
    try:
        execution.validate_session_start(session_start, snapshot=snapshot)
        execution.validate_authorization(
            authorization, contract=contract, snapshot=snapshot
        )
    except execution.N5ExecutionError as error:
        raise N5PhysicalExecutionError(
            f"physical preclaim record is invalid: {error}"
        ) from error
    _validate_live_prior(
        context,
        snapshot,
        production,
        prior_bundle,
        prior_result_dir,
        profile_reviewer_key_file=production_files.reviewer_key,
    )
    _verify_exact_tokens(
        context,
        snapshot,
        production,
        authorization,
        action_token=action_token,
        panel_plan_token=panel_plan_token,
        profile_token=profile_token,
    )
    start = _finite(start_temperature_c, label="start_temperature_c")
    if not all(
        value is True
        for value in (
            confirm_supply_cv_current_normal,
            confirm_j2_on,
            confirm_physical_cutoff_available,
        )
    ):
        raise N5PhysicalExecutionError(
            "all live electrical/J2/cutoff confirmations must be true"
        )
    claimed_at = wall_clock()
    controls = _physical_controls(
        context,
        snapshot,
        production,
        authorization,
        evaluated_at=evaluated_at,
        claimed_at=claimed_at,
    )
    limits = production.profile["limits"]
    if not float(limits["minimum_start_temperature_c"]) <= start <= float(
        limits["maximum_start_temperature_c"]
    ):
        raise N5PhysicalExecutionError(
            "start temperature is outside reviewed production limits"
        )
    runtime_gates = {
        "observed_at": claimed_at,
        "start_temperature_c": start,
        "supply_cv_current_normal": True,
        "j2_on": True,
        "physical_cutoff_available": True,
        "operator_advance_artifact_sha256": authorization[
            "authorization_artifact_sha256"
        ],
        "runtime_evidence_sha256": _sha256(controls),
    }
    artifacts = {
        **_context_artifacts(context),
        **_production_artifacts(production),
    }
    try:
        return fixed._run_fixed_action_core(
            plan["runtime_manifest"],
            contract=contract,
            action_key=action_key,
            limit_profile=production.profile,
            profile_evaluated_at=evaluated_at,
            authorization=authorization,
            session_start=session_start,
            runtime_gates=runtime_gates,
            prior_bundle=prior_bundle,
            attempt_id=uuid.uuid4().hex,
            claimed_at=claimed_at,
            protocol_completed_at=claimed_at,
            claim_root=claim_root,
            result_dir=result_dir,
            base_url=base_url,
            transport=transport,
            protocol_driver=protocol_driver,
            preclaim_records={
                PHYSICAL_CONTROLS_FILE: controls,
                PRODUCTION_VALIDATION_FILE: production.report,
            },
            preclaim_artifacts=artifacts,
        )
    except (fixed.N5FixedExecutionToolError, execution.N5ExecutionError) as error:
        raise N5PhysicalExecutionError(str(error)) from error


def _stored_production_files(
    result_dir: Path, reviewer_key_file: Path
) -> N5ProductionFiles:
    return N5ProductionFiles(
        profile=result_dir / fixed.RESULT_PROFILE_FILE,
        physical_campaign=result_dir / PHYSICAL_CAMPAIGN_FILE,
        firmware_binary=result_dir / FIRMWARE_BINARY_FILE,
        limit_authority=result_dir / LIMIT_AUTHORITY_FILE,
        usage_evidence=result_dir / USAGE_EVIDENCE_FILE,
        review_artifact=result_dir / PROFILE_REVIEW_FILE,
        reviewer_key=reviewer_key_file,
    )


def _strict_result_json(result_dir: Path, filename: str) -> Mapping[str, Any]:
    try:
        return fixed._strict_json_file(result_dir / filename, label=filename)
    except fixed.N5FixedExecutionToolError as error:
        raise N5PhysicalExecutionError(str(error)) from error


def _load_committed_action_item(result_dir: Path) -> Mapping[str, Any]:
    try:
        return fixed._load_finalized_action_item(
            result_dir / fixed.RESULT_ACTION_ITEM_FILE
        )
    except fixed.N5FixedExecutionToolError as error:
        raise N5PhysicalExecutionError(str(error)) from error


def _verify_stored_artifacts(
    context: N5PhysicalContext,
    result_dir: Path,
    production: ValidatedProductionProfile,
) -> None:
    expected = {
        **_context_artifacts(context),
        **_production_artifacts(production),
        PRODUCTION_VALIDATION_FILE: canonical_json_bytes(production.report),
    }
    for filename, payload in expected.items():
        try:
            stored = read_local_regular_file(
                result_dir / filename,
                label=f"stored physical N5 {filename}",
                maximum_bytes=physical_campaign.MAX_JSON_BYTES,
            ).payload
        except ProductionProfileError as error:
            raise N5PhysicalExecutionError(str(error)) from error
        if stored != payload:
            raise N5PhysicalExecutionError(
                f"stored physical N5 {filename} differs from trusted replay"
            )


def validate_n5_physical_action_result(
    context: N5PhysicalContext,
    result_dir: Path,
    *,
    profile_reviewer_key_file: Path,
) -> dict[str, Any]:
    """Deeply replay one finalized action without network or device I/O."""

    if not isinstance(result_dir, Path) or not result_dir.is_dir():
        raise N5PhysicalExecutionError("physical N5 result directory is missing")
    plan = validate_n5_physical_context(context)
    cache_key = _physical_result_cache_key(
        context, result_dir, profile_reviewer_key_file
    )
    cached = _VALIDATED_ACTION_RESULT_CACHE.get(cache_key)
    if cached is not None:
        return json.loads(cached.decode("utf-8"))
    contract = plan["execution_contract"]
    item = _load_committed_action_item(result_dir)
    action_key = str(item.get("action_key"))
    snapshot = _snapshot_from_plan(plan, action_key)
    claim = item.get("claim")
    if not isinstance(claim, Mapping):
        raise N5PhysicalExecutionError("physical N5 finalized claim is missing")
    evaluated_at = claim.get("profile_evaluated_at")
    claimed_at = claim.get("claimed_at")
    if not isinstance(evaluated_at, str) or not isinstance(claimed_at, str):
        raise N5PhysicalExecutionError("physical N5 claim time binding is invalid")
    production = _load_production_for_snapshot(
        context,
        snapshot,
        _stored_production_files(result_dir, profile_reviewer_key_file),
        evaluated_at=evaluated_at,
    )
    _verify_stored_artifacts(context, result_dir, production)
    authorization = item.get("authorization")
    if not isinstance(authorization, Mapping):
        raise N5PhysicalExecutionError("physical N5 authorization is missing")
    controls = _strict_result_json(result_dir, PHYSICAL_CONTROLS_FILE)
    expected_controls = _physical_controls(
        context,
        snapshot,
        production,
        authorization,
        evaluated_at=evaluated_at,
        claimed_at=claimed_at,
    )
    if controls != expected_controls:
        raise N5PhysicalExecutionError(
            "stored physical N5 plan/profile/schedule controls changed"
        )
    if (
        claim.get("runtime_gates", {}).get("runtime_evidence_sha256")
        != _sha256(controls)
        or authorization.get("confirmation_sha256")
        != controls["authorization_confirmation_sha256"]
        or item.get("profile") != production.profile
        or item.get("profile_file_sha256") != production.profile_file.sha256
    ):
        raise N5PhysicalExecutionError(
            "finalized N5 item does not bind deep physical production evidence"
        )
    prior = None
    prior_path = result_dir / fixed.RESULT_PRIOR_FILE
    if prior_path.exists():
        prior_record = _strict_result_json(result_dir, fixed.RESULT_PRIOR_FILE)
        try:
            prior = fixed._prior_action_item(contract, action_key, prior_record)
        except fixed.N5FixedExecutionToolError as error:
            raise N5PhysicalExecutionError(str(error)) from error
    try:
        strict = n5_rc2g_protocol.validate_strict_action_item(
            contract, item, prior_item=prior
        )
    except (
        execution.N5ExecutionError,
        n5_rc2g_protocol.N5Rc2gProtocolError,
    ) as error:
        raise N5PhysicalExecutionError(
            f"strict physical N5 action replay failed: {error}"
        ) from error
    if strict.get("strict_rc2g_verified") is not True:
        raise N5PhysicalExecutionError("physical N5 action is not strict RC2G PASS")
    result = {
        **strict,
        "physical_plan_canonical_sha256": plan["integrity"]["canonical_sha256"],
        "production_profile_file_sha256": production.profile_file.sha256,
        "deep_production_profile_replayed": True,
        "physical_controls_replayed": True,
        "network_io_performed": False,
        "device_io_performed": False,
    }
    if len(_VALIDATED_ACTION_RESULT_CACHE) >= _VALIDATED_ACTION_RESULT_CACHE_LIMIT:
        _VALIDATED_ACTION_RESULT_CACHE.pop(
            next(iter(_VALIDATED_ACTION_RESULT_CACHE))
        )
    _VALIDATED_ACTION_RESULT_CACHE[cache_key] = canonical_json_bytes(result)
    return result


def finalize_n5_physical_action(
    context: N5PhysicalContext,
    result_dir: Path,
    *,
    manual_observation_payload: Mapping[str, Any],
    claim_root: Path,
    profile_reviewer_key_file: Path,
    wall_clock: Callable[[], str] = _utc_now,
) -> dict[str, Any]:
    plan = validate_n5_physical_context(context)
    receipt = _strict_result_json(result_dir, fixed.RESULT_RECEIPT_FILE)
    claim = receipt.get("claim")
    if not isinstance(claim, Mapping):
        raise N5PhysicalExecutionError("pending physical N5 receipt lacks claim")
    action_key = str(claim.get("action_key"))
    evaluated_at = str(claim.get("profile_evaluated_at"))
    snapshot = _snapshot_from_plan(plan, action_key)
    production = _load_production_for_snapshot(
        context,
        snapshot,
        _stored_production_files(result_dir, profile_reviewer_key_file),
        evaluated_at=evaluated_at,
    )
    _verify_stored_artifacts(context, result_dir, production)
    try:
        output = fixed._finalize_fixed_action_core(
            manifest=plan["runtime_manifest"],
            contract=plan["execution_contract"],
            result_dir=result_dir,
            manual_observation_payload=manual_observation_payload,
            completed_at=wall_clock(),
            claim_root=claim_root,
        )
    except (fixed.N5FixedExecutionToolError, execution.N5ExecutionError) as error:
        raise N5PhysicalExecutionError(str(error)) from error
    replay = validate_n5_physical_action_result(
        context,
        result_dir,
        profile_reviewer_key_file=profile_reviewer_key_file,
    )
    return {**output, "physical_replay": replay}


def validate_n5_physical_finalized_bundle(
    context: N5PhysicalContext,
    bundle: Mapping[str, Any],
    *,
    result_dirs: Sequence[Path],
    profile_reviewer_key_file: Path,
) -> dict[str, Any]:
    """Require every bundle action to come from one deep physical result."""

    plan = validate_n5_physical_context(context)
    contract = plan["execution_contract"]
    if len(result_dirs) != len(set(path.resolve() for path in result_dirs)):
        raise N5PhysicalExecutionError("duplicate physical N5 result directory")
    items: dict[str, Mapping[str, Any]] = {}
    deep: dict[str, Mapping[str, Any]] = {}
    for result_dir in result_dirs:
        validated = validate_n5_physical_action_result(
            context,
            result_dir,
            profile_reviewer_key_file=profile_reviewer_key_file,
        )
        item = _load_committed_action_item(result_dir)
        action_sha = str(item["action_identity_sha256"])
        if action_sha in items:
            raise N5PhysicalExecutionError(
                "duplicate physical N5 finalized action identity"
            )
        items[action_sha] = item
        deep[action_sha] = validated
    bundled_items = bundle.get("actions")
    if not isinstance(bundled_items, list):
        raise N5PhysicalExecutionError("physical N5 finalized bundle actions are missing")
    bundle_by_sha = {
        str(item.get("action_identity_sha256")): item
        for item in bundled_items
        if isinstance(item, Mapping)
    }
    if (
        len(bundle_by_sha) != len(bundled_items)
        or set(bundle_by_sha) != set(items)
        or any(bundle_by_sha[sha] != item for sha, item in items.items())
    ):
        raise N5PhysicalExecutionError(
            "physical N5 bundle is cross-plan, duplicated, or differs from result files"
        )
    try:
        strict = n5_rc2g_protocol.validate_strict_finalized_bundle(contract, bundle)
    except (
        execution.N5ExecutionError,
        n5_rc2g_protocol.N5Rc2gProtocolError,
    ) as error:
        raise N5PhysicalExecutionError(
            f"strict physical N5 finalized bundle failed: {error}"
        ) from error
    if (
        strict.get("state") != "normal"
        or strict.get("strict_rc2g_verified") is not True
        or set(strict.get("strict_actions_by_sha", {})) != set(items)
    ):
        raise N5PhysicalExecutionError(
            "physical N5 bundle did not strictly replay every action"
        )
    return {
        **strict,
        "physical_plan_canonical_sha256": plan["integrity"]["canonical_sha256"],
        "deep_actions_by_sha": deep,
        "physical_deep_replay": True,
        "network_io_performed": False,
        "device_io_performed": False,
    }


def build_n5_physical_session_bundle(
    context: N5PhysicalContext,
    *,
    result_dirs: Sequence[Path],
    session_starts: Sequence[Mapping[str, Any]],
    finalized_at: str,
    j2_cut_session_ids: Sequence[str],
    profile_reviewer_key_file: Path,
    output_file: Path,
) -> dict[str, Any]:
    plan = validate_n5_physical_context(context)
    contract = plan["execution_contract"]
    action_items = [
        _load_committed_action_item(path)
        for path in result_dirs
    ]
    try:
        bundle = execution.build_finalized_bundle(
            contract,
            action_items,
            session_starts,
            finalized_at=finalized_at,
            j2_cut_session_ids=j2_cut_session_ids,
        )
    except execution.N5ExecutionError as error:
        raise N5PhysicalExecutionError(str(error)) from error
    summary = validate_n5_physical_finalized_bundle(
        context,
        bundle,
        result_dirs=result_dirs,
        profile_reviewer_key_file=profile_reviewer_key_file,
    )
    try:
        file_sha = fixed._publish_json(output_file, bundle)
    except fixed.N5FixedExecutionToolError as error:
        raise N5PhysicalExecutionError(str(error)) from error
    stored = _strict_result_json(output_file.parent, output_file.name)
    stored_summary = validate_n5_physical_finalized_bundle(
        context,
        stored,
        result_dirs=result_dirs,
        profile_reviewer_key_file=profile_reviewer_key_file,
    )
    if stored_summary != summary:
        raise N5PhysicalExecutionError("stored physical N5 bundle replay changed")
    return {
        "bundle_canonical_sha256": bundle["integrity"]["canonical_sha256"],
        "bundle_file_sha256": file_sha,
        "action_count": len(bundle["actions"]),
        "session_count": len(bundle["sessions"]),
        "physical_deep_replay": True,
        "strict_rc2g_verified": True,
        "output": str(output_file.resolve()),
    }


def _physical_aggregate_envelope(
    context: N5PhysicalContext,
    bundle: Mapping[str, Any],
    deep_summary: Mapping[str, Any],
    aggregate: Mapping[str, Any],
    *,
    kind: str,
) -> dict[str, Any]:
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "physical_plan_canonical_sha256": context.plan["integrity"][
            "canonical_sha256"
        ],
        "execution_contract_canonical_sha256": context.plan[
            "execution_contract"
        ]["integrity"]["canonical_sha256"],
        "finalized_bundle_canonical_sha256": bundle["integrity"][
            "canonical_sha256"
        ],
        "strict_action_count": len(deep_summary["strict_actions_by_sha"]),
        "strict_rc2g_verified": True,
        "every_action_deep_production_profile_replayed": True,
        "aggregate": aggregate,
        "classification": {
            "production_physical": True,
            "offline_structural_only": False,
            "network_io_performed": False,
            "device_io_performed": False,
        },
    }
    return execution._seal(unsigned)


def aggregate_n5_physical_palette(
    context: N5PhysicalContext,
    observations: Sequence[Mapping[str, Any]],
    *,
    standard_table: Mapping[str, Any],
    instrument_qualification: Mapping[str, Any],
    finalized_bundle: Mapping[str, Any],
    result_dirs: Sequence[Path],
    profile_reviewer_key_file: Path,
) -> dict[str, Any]:
    """Production palette aggregation after per-action physical deep replay."""

    from host.extended_color import aggregation

    plan = validate_n5_physical_context(context)
    deep = validate_n5_physical_finalized_bundle(
        context,
        finalized_bundle,
        result_dirs=result_dirs,
        profile_reviewer_key_file=profile_reviewer_key_file,
    )
    aggregate = aggregation.aggregate_production_measured_palette(
        plan["runtime_manifest"]["formal_palette_plan"],
        observations,
        standard_table=standard_table,
        instrument_qualification=instrument_qualification,
        execution_contract=plan["execution_contract"],
        finalized_bundle=finalized_bundle,
    )
    return _physical_aggregate_envelope(
        context,
        finalized_bundle,
        deep,
        aggregate,
        kind=PHYSICAL_PALETTE_AGGREGATE_KIND,
    )


def aggregate_n5_physical_transition(
    context: N5PhysicalContext,
    observations: Sequence[Mapping[str, Any]],
    *,
    standard_table: Mapping[str, Any],
    instrument_qualification: Mapping[str, Any],
    finalized_bundle: Mapping[str, Any],
    result_dirs: Sequence[Path],
    profile_reviewer_key_file: Path,
) -> dict[str, Any]:
    """Production transition aggregation after per-action physical replay."""

    from host.extended_color import aggregation

    plan = validate_n5_physical_context(context)
    deep = validate_n5_physical_finalized_bundle(
        context,
        finalized_bundle,
        result_dirs=result_dirs,
        profile_reviewer_key_file=profile_reviewer_key_file,
    )
    aggregate = aggregation.aggregate_production_transition_profile(
        plan["runtime_manifest"]["formal_transition_plan"],
        observations,
        standard_table=standard_table,
        instrument_qualification=instrument_qualification,
        execution_contract=plan["execution_contract"],
        finalized_bundle=finalized_bundle,
    )
    return _physical_aggregate_envelope(
        context,
        finalized_bundle,
        deep,
        aggregate,
        kind=PHYSICAL_TRANSITION_AGGREGATE_KIND,
    )


def _add_plan_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--physical-plan", type=Path, required=True)
    parser.add_argument("--compile-profile", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--physical-anchor", type=Path, required=True)
    parser.add_argument("--firmware-binary", type=Path, required=True)
    parser.add_argument("--science-review-evidence", type=Path, required=True)
    parser.add_argument("--science-review-approval", type=Path, required=True)
    parser.add_argument("--science-reviewer-key", type=Path, required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--minimum-interval-seconds", type=float, required=True)
    parser.add_argument("--planned-cooldown-seconds", type=float, required=True)


def _add_production_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--physical-campaign", type=Path, required=True)
    parser.add_argument(
        "--limit-authority",
        type=Path,
        required=True,
        help="neutral supplier limits or supervised process-policy authority",
    )
    parser.add_argument("--usage-evidence", type=Path, required=True)
    parser.add_argument("--profile-review", type=Path, required=True)
    parser.add_argument("--profile-reviewer-key", type=Path, required=True)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    describe = subparsers.add_parser(
        "describe", help="deeply validate one action and print its exact tokens"
    )
    _add_plan_arguments(describe)
    _add_production_arguments(describe)
    describe.add_argument("--action", required=True)
    run = subparsers.add_parser("run", help="perform exactly one physical N5 refresh")
    _add_plan_arguments(run)
    _add_production_arguments(run)
    run.add_argument("--action", required=True)
    run.add_argument("--authorization", type=Path, required=True)
    run.add_argument("--session-start", type=Path, required=True)
    run.add_argument("--prior-bundle", type=Path)
    run.add_argument("--prior-result-dir", type=Path)
    run.add_argument("--result-dir", type=Path, required=True)
    run.add_argument("--url", required=True)
    run.add_argument("--action-token", required=True)
    run.add_argument("--panel-plan-token", required=True)
    run.add_argument("--profile-token", required=True)
    run.add_argument("--start-temperature-c", type=float, required=True)
    run.add_argument("--confirm-supply-cv-current-normal", action="store_true")
    run.add_argument("--confirm-j2-on", action="store_true")
    run.add_argument("--confirm-physical-cutoff-available", action="store_true")
    finalize = subparsers.add_parser(
        "finalize", help="finalize and physically replay one pending action"
    )
    _add_plan_arguments(finalize)
    finalize.add_argument("--result-dir", type=Path, required=True)
    finalize.add_argument("--manual-observation", type=Path, required=True)
    finalize.add_argument("--profile-reviewer-key", type=Path, required=True)
    bundle = subparsers.add_parser(
        "build-session-bundle",
        help="build a strict/deep physical session bundle without device I/O",
    )
    _add_plan_arguments(bundle)
    bundle.add_argument("--result-dir", type=Path, action="append", required=True)
    bundle.add_argument("--session-start", type=Path, action="append", required=True)
    bundle.add_argument("--profile-reviewer-key", type=Path, required=True)
    bundle.add_argument("--finalized-at", required=True)
    bundle.add_argument("--j2-cut-session-id", action="append", default=[])
    bundle.add_argument("--output", type=Path, required=True)
    validate = subparsers.add_parser(
        "validate-bundle",
        help="strictly replay every physical bundle action without device I/O",
    )
    _add_plan_arguments(validate)
    validate.add_argument("--bundle", type=Path, required=True)
    validate.add_argument("--result-dir", type=Path, action="append", required=True)
    validate.add_argument("--profile-reviewer-key", type=Path, required=True)
    return parser.parse_args(argv)


def _context_from_args(args: argparse.Namespace) -> N5PhysicalContext:
    return load_n5_physical_context(
        plan_file=args.physical_plan,
        compile_profile_file=args.compile_profile,
        source_manifest_file=args.source_manifest,
        physical_anchor_campaign_file=args.physical_anchor,
        firmware_binary_file=args.firmware_binary,
        science_review_evidence_file=args.science_review_evidence,
        science_review_approval_file=args.science_review_approval,
        science_reviewer_key_file=args.science_reviewer_key,
        namespace=args.namespace,
        minimum_interval_seconds=args.minimum_interval_seconds,
        planned_cooldown_seconds=args.planned_cooldown_seconds,
    )


def _production_from_args(args: argparse.Namespace) -> N5ProductionFiles:
    return N5ProductionFiles(
        profile=args.profile,
        physical_campaign=args.physical_campaign,
        firmware_binary=args.firmware_binary,
        limit_authority=args.limit_authority,
        usage_evidence=args.usage_evidence,
        review_artifact=args.profile_review,
        reviewer_key=args.profile_reviewer_key,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        args = parse_args(argv)
        context = _context_from_args(args)
        if args.command == "describe":
            evaluated_at = _utc_now()
            plan = validate_n5_physical_context(context)
            snapshot = _snapshot_from_plan(plan, args.action)
            production = _load_production_for_snapshot(
                context,
                snapshot,
                _production_from_args(args),
                evaluated_at=evaluated_at,
            )
            output = {
                "mode": "describe-only",
                "action_key": args.action,
                "profile_evaluated_at": evaluated_at,
                "action_token": _required_action_token(context, snapshot),
                "panel_plan_token": _required_panel_plan_token(context, snapshot),
                "profile_token": required_profile_token(production),
                "production_validation": production.report,
                "claim_created": False,
                "network_io_performed": False,
                "device_io_performed": False,
            }
        elif args.command == "run":
            authorization = fixed._strict_json_file(
                args.authorization, label="physical N5 external authorization"
            )
            session_start = fixed._strict_json_file(
                args.session_start, label="physical N5 session start"
            )
            prior = (
                None
                if args.prior_bundle is None
                else fixed._strict_json_file(
                    args.prior_bundle, label="physical N5 immediate prior"
                )
            )
            output = run_n5_physical_action_once(
                context,
                args.action,
                production_files=_production_from_args(args),
                authorization=authorization,
                session_start=session_start,
                prior_bundle=prior,
                prior_result_dir=args.prior_result_dir,
                result_dir=args.result_dir,
                claim_root=fixed.PRODUCTION_CLAIM_ROOT,
                base_url=args.url,
                action_token=args.action_token,
                panel_plan_token=args.panel_plan_token,
                profile_token=args.profile_token,
                start_temperature_c=args.start_temperature_c,
                confirm_supply_cv_current_normal=(
                    args.confirm_supply_cv_current_normal
                ),
                confirm_j2_on=args.confirm_j2_on,
                confirm_physical_cutoff_available=(
                    args.confirm_physical_cutoff_available
                ),
            )
        elif args.command == "finalize":
            manual = fixed._strict_json_file(
                args.manual_observation,
                label="physical N5 manual observation",
            )
            output = finalize_n5_physical_action(
                context,
                args.result_dir,
                manual_observation_payload=manual,
                claim_root=fixed.PRODUCTION_CLAIM_ROOT,
                profile_reviewer_key_file=args.profile_reviewer_key,
            )
        elif args.command == "build-session-bundle":
            starts = [
                fixed._strict_json_file(
                    path, label="physical N5 session-start observation"
                )
                for path in args.session_start
            ]
            output = build_n5_physical_session_bundle(
                context,
                result_dirs=args.result_dir,
                session_starts=starts,
                finalized_at=args.finalized_at,
                j2_cut_session_ids=args.j2_cut_session_id,
                profile_reviewer_key_file=args.profile_reviewer_key,
                output_file=args.output,
            )
        else:
            bundle = fixed._strict_json_file(
                args.bundle, label="physical N5 finalized bundle"
            )
            output = validate_n5_physical_finalized_bundle(
                context,
                bundle,
                result_dirs=args.result_dir,
                profile_reviewer_key_file=args.profile_reviewer_key,
            )
    except (
        N5PhysicalExecutionError,
        physical_campaign.N5PhysicalCampaignError,
        fixed.N5FixedExecutionToolError,
        execution.N5ExecutionError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
    return 0 if output.get("state") != "UNKNOWN_DO_NOT_RETRY" else 3


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ACTION_TOKEN_PREFIX",
    "MAX_PROFILE_EVALUATION_AGE_SECONDS",
    "N5PhysicalContext",
    "N5PhysicalExecutionError",
    "N5ProductionFiles",
    "PANEL_PLAN_TOKEN_PREFIX",
    "PROFILE_TOKEN_PREFIX",
    "authorization_confirmation_sha256",
    "aggregate_n5_physical_palette",
    "aggregate_n5_physical_transition",
    "build_n5_physical_session_bundle",
    "finalize_n5_physical_action",
    "load_n5_physical_context",
    "load_n5_physical_production_profile",
    "required_action_token",
    "required_panel_plan_token",
    "required_profile_token",
    "run_n5_physical_action_once",
    "validate_live_evaluation_age",
    "validate_n5_physical_action_result",
    "validate_n5_physical_context",
    "validate_n5_physical_finalized_bundle",
]
