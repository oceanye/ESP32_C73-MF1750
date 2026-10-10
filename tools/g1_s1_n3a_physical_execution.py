#!/usr/bin/env python3
"""Deep production adapter for one physical N3A repeatability plan.

Every public context validation replays the eight finalized physical N2
results through :mod:`g1_s1_n3a_physical_plan`; a self-sealed analysis or plan
is never sufficient.  This module only validates files and derives control
records.  It has no claim, HTTP, serial, firmware, reset, or power path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Optional

from host.visible_refresh_campaign import (
    CampaignContractError,
    ProductionProfileError,
    ValidatedProductionProfile,
    canonical_json_bytes,
    load_validated_production_profile,
    read_local_regular_file,
    read_standalone_physical_campaign,
)
from tools import g1_s1_n3_execution_contract as frozen
from tools import g1_s1_n3a_physical_plan as physical_plan


SCHEMA_VERSION = 1
AUTHORIZATION_PREFIX = "AUTHORIZE_ONE_VISIBLE_RC2G_N3A_PHYSICAL__ACTION_"
AUTHORIZATION_SUFFIX = "__NO_RETRY_NO_RECOVERY"
PANEL_PLAN_CONFIRMATION_PREFIX = "CONFIRM_N3A_PHYSICAL_PANEL_PLAN"
PROFILE_CONFIRMATION_PREFIX = "CONFIRM_N3A_APPROVED_PRODUCTION_PROFILE"
MAX_LIVE_EVALUATED_AT_AGE_SECONDS = 300
MAX_PLAN_BYTES = physical_plan.MAX_PLAN_JSON_BYTES
MAX_REVIEW_BYTES = physical_plan.MAX_BINDING_REVIEW_BYTES

_CONTROL_FIELDS = frozenset(
    {
        "panel_plan_confirmation_sha256",
        "profile_confirmation_sha256",
        "profile_evaluated_at",
        "live_evaluation_age_seconds",
        "maximum_live_evaluation_age_seconds",
        "schedule_reference_completed_at",
        "materialized_minimum_interval_seconds",
        "authority_minimum_interval_seconds",
        "effective_minimum_interval_seconds",
        "minimum_interval_gate_applies",
        "minimum_interval_elapsed_seconds",
        "materialized_planned_cooldown_seconds",
        "authority_minimum_cooldown_seconds",
        "effective_minimum_cooldown_seconds",
        "minimum_cooldown_gate_applies",
        "minimum_cooldown_elapsed_seconds",
        "schedule_gates_satisfied",
    }
)
PHYSICAL_RECORD_EXTRA_KEYS = {
    "claim": _CONTROL_FIELDS,
    "lock": _CONTROL_FIELDS,
    "evidence": _CONTROL_FIELDS | {"authorization_confirmation_sha256"},
    "finalization": _CONTROL_FIELDS | {"authorization_confirmation_sha256"},
}


class N3APhysicalExecutionError(ValueError):
    """A physical N3A plan or production evidence failed closed."""


@dataclass(frozen=True)
class N3APhysicalContext:
    plan: Mapping[str, Any]
    binding_review_bytes: bytes
    minimum_interval_seconds: float
    planned_cooldown_seconds: float
    n2_result_directories: Mapping[str, Path]
    n2_reviewer_key_file: Path


def _canonical(value: Any) -> bytes:
    try:
        return canonical_json_bytes(value)
    except CampaignContractError as error:
        raise N3APhysicalExecutionError(str(error)) from error


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else _canonical(value)
    return hashlib.sha256(payload).hexdigest()


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(_canonical(value).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N3APhysicalExecutionError(str(error)) from error


def _source_campaign(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    selected = plan["selected_source"]
    branches = [
        item
        for item in plan["source_n3a_manifest"]["branches"]
        if item["branch_id"] == selected["branch_id"]
    ]
    templates = [
        item
        for branch in branches
        for item in branch["repeat_templates"]
        if item["template_id"] == selected["template_id"]
    ]
    if len(branches) != 1 or len(templates) != 1:
        raise N3APhysicalExecutionError("selected N3A source campaign is not unique")
    return templates[0]["p0_campaign"]


def validate_n3a_physical_execution_context(
    context: N3APhysicalContext,
) -> Mapping[str, Any]:
    if not isinstance(context, N3APhysicalContext):
        raise N3APhysicalExecutionError("context must be N3APhysicalContext")
    try:
        plan = physical_plan.validate_n3a_physical_plan(
            context.plan,
            n2_result_directories=context.n2_result_directories,
            reviewer_key_file=context.n2_reviewer_key_file,
            binding_review_bytes=context.binding_review_bytes,
            minimum_interval_seconds=context.minimum_interval_seconds,
            planned_cooldown_seconds=context.planned_cooldown_seconds,
        )
    except (physical_plan.N3APhysicalPlanError, ValueError, RuntimeError, OSError) as error:
        raise N3APhysicalExecutionError(
            f"physical N3A raw-evidence replay failed: {error}"
        ) from error
    assets = plan["measurement_asset_contract"]
    if (
        assets["all_identities_registered"] is not True
        or assets["blockers"] != []
        or plan["selection"]["authorized_use"] != "N3_branch_selection_only"
        or plan["selection"]["algorithm_qualified"] is not False
        or plan["selection"]["population_inference"] is not False
        or len(plan["selected_routes"]) not in (2, 3, 4)
        or len(plan["fixed_actions"]) != 2 * len(plan["selected_routes"])
    ):
        raise N3APhysicalExecutionError(
            "physical N3A plan is not a complete registered repeat-2/3/4 branch"
        )
    return plan


def n3a_physical_plan_file_sha256(context: N3APhysicalContext) -> str:
    return _sha256(validate_n3a_physical_execution_context(context))


def compatibility_plan(context: N3APhysicalContext) -> Mapping[str, Any]:
    """Expose only the legacy metadata seams needed by the audited validator."""

    plan = validate_n3a_physical_execution_context(context)
    manifest = plan["source_n3a_manifest"]
    return {
        **_snapshot(plan),
        "execution_manifest": _snapshot(manifest),
        "execution_manifest_file_sha256": plan["source_n3a_manifest_file_sha256"],
        "source_manifest": {
            "canonical_sha256": manifest["integrity"]["canonical_sha256"]
        },
    }


def load_n3a_physical_action_snapshot(
    context: N3APhysicalContext, action_key: str
) -> frozen.N3ActionSnapshot:
    plan = validate_n3a_physical_execution_context(context)
    if not isinstance(action_key, str) or action_key not in plan["fixed_actions"]:
        raise N3APhysicalExecutionError("action_key is not in physical N3A plan")
    fixed = plan["fixed_actions"][action_key]
    campaign = plan["physical_rebind"]["physical_campaign"]
    actions = {
        item["action_identity_sha256"]: item for item in campaign["actions"]
    }
    action = actions.get(fixed["action_identity_sha256"])
    routes = [
        item
        for item in plan["selected_routes"]
        if action_key in {item["map_action_key"], item["target_action_key"]}
    ]
    source_actions = {
        item["action_identity_sha256"]: item
        for item in _source_campaign(plan)["actions"]
    }
    source_action = source_actions.get(fixed["source_action_identity_sha256"])
    if action is None or source_action is None or len(routes) != 1:
        raise N3APhysicalExecutionError("physical N3A action lineage is not unique")
    old_identity = source_action["identity"]
    identity = action["identity"]
    for field in (
        "session_id",
        "cell_id",
        "action_id",
        "phase",
        "frame",
        "request",
        "automatic_retry",
        "automatic_recovery",
    ):
        if identity[field] != old_identity[field]:
            raise N3APhysicalExecutionError(
                f"physical N3A action changed frozen {field} semantics"
            )
    source_key = (
        "q1-map-primer"
        if fixed["phase"] == "map-primer"
        else f"{fixed['winner_cell_id'].lower()}-target"
    )
    try:
        source = frozen._source_action_snapshot(source_key)
    except frozen.N3ExecutionContractError as error:
        raise N3APhysicalExecutionError(str(error)) from error
    if _sha256(source.frame) != identity["frame"]["sha256"]:
        raise N3APhysicalExecutionError("physical N3A frame bytes changed")
    return frozen.N3ActionSnapshot(
        plan=compatibility_plan(context),
        key=action_key,
        cell_id=fixed["cell_id"],
        candidate_cell_id=fixed["winner_cell_id"],
        phase=fixed["phase"],
        campaign=campaign,
        action=action,
        route=routes[0],
        frame=source.frame,
        reference_preview=_snapshot(source.reference_preview),
    )


def required_authorization_confirmation(
    _plan: Mapping[str, Any], snapshot: frozen.N3ActionSnapshot
) -> str:
    return (
        f"{AUTHORIZATION_PREFIX}"
        f"{snapshot.action['action_identity_sha256'].upper()}"
        f"{AUTHORIZATION_SUFFIX}"
    )


def required_panel_plan_confirmation(
    context: N3APhysicalContext, snapshot: frozen.N3ActionSnapshot
) -> str:
    plan = validate_n3a_physical_execution_context(context)
    return (
        f"{PANEL_PLAN_CONFIRMATION_PREFIX}"
        f"__SERIAL_{snapshot.campaign['panel']['serial']}"
        f"__BUILD_TAG_{snapshot.campaign['firmware']['build_tag']}"
        f"__PLAN_{plan['integrity']['canonical_sha256'].upper()}"
        f"__REBIND_{plan['physical_rebind']['binding']['canonical_sha256'].upper()}"
        f"__N2_REPLAY_{plan['n2_physical_provenance']['canonical_sha256'].upper()}"
        f"__ASSETS_{plan['measurement_asset_contract']['registry_canonical_sha256'].upper()}"
    )


def required_production_profile_confirmation(
    production: ValidatedProductionProfile,
) -> str:
    review = production.review_artifact_file
    if review is None or production.reviewer_key_id is None:
        raise N3APhysicalExecutionError("approved production review is incomplete")
    values = (
        production.profile["integrity"]["canonical_sha256"],
        production.profile_file.sha256,
        review.sha256,
        production.reviewer_key_id,
        production.inputs.usage_evidence_file.sha256,
        production.inputs.limit_authority_file.sha256,
    )
    if any(
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
        for value in values
    ):
        raise N3APhysicalExecutionError(
            "production profile confirmation contains an invalid SHA-256"
        )
    return (
        f"{PROFILE_CONFIRMATION_PREFIX}"
        f"__PROFILE_CANONICAL_{values[0].upper()}"
        f"__PROFILE_FILE_{values[1].upper()}"
        f"__REVIEW_ARTIFACT_FILE_{values[2].upper()}"
        f"__REVIEWER_KEY_ID_{values[3]}"
        f"__USAGE_FILE_{values[4].upper()}"
        f"__LIMIT_AUTHORITY_FILE_{values[5].upper()}"
    )


def _timestamp(value: Any, *, label: str) -> datetime:
    try:
        return frozen._timestamp(value, label=label)
    except frozen.N3ExecutionContractError as error:
        raise N3APhysicalExecutionError(str(error)) from error


def validate_live_evaluation_time(evaluated_at: str, live_now: str) -> float:
    evaluated = _timestamp(evaluated_at, label="profile evaluated_at")
    current = _timestamp(live_now, label="live execution current time")
    age = (current - evaluated).total_seconds()
    if age < 0:
        raise N3APhysicalExecutionError("profile evaluated_at must not be future")
    if age > MAX_LIVE_EVALUATED_AT_AGE_SECONDS:
        raise N3APhysicalExecutionError(
            "profile evaluated_at is too old; revalidate immediately"
        )
    return age


def control_fields(
    context: N3APhysicalContext,
    snapshot: frozen.N3ActionSnapshot,
    production: ValidatedProductionProfile,
    *,
    evaluated_at: str,
    live_now: str,
) -> dict[str, Any]:
    age = validate_live_evaluation_time(evaluated_at, live_now)
    current = _timestamp(live_now, label="live execution current time")
    last_value = production.profile["usage"]["last_visible_refresh_completed_at"]
    last = (
        None
        if last_value is None
        else _timestamp(last_value, label="usage last_visible_refresh_completed_at")
    )
    identity = snapshot.action["identity"]
    sessions = [
        item
        for item in snapshot.campaign["sessions"]
        if item["session_id"] == identity["session_id"]
    ]
    if len(sessions) != 1:
        raise N3APhysicalExecutionError("physical action session is not unique")
    limits = production.profile["limits"]
    usage = production.profile["usage"]
    materialized_interval = float(
        identity["schedule"]["minimum_interval_since_prior_seconds"]
    )
    authority_interval = float(limits["minimum_interval_seconds"])
    effective_interval = max(materialized_interval, authority_interval)
    materialized_cooldown = float(sessions[0]["planned_cooldown_seconds"])
    authority_cooldown = float(limits["minimum_cooldown_seconds"])
    effective_cooldown = max(materialized_cooldown, authority_cooldown)
    elapsed = None if last is None else (current - last).total_seconds()
    interval_applies = last is not None
    cooldown_applies = (
        last is not None
        and usage["cumulative_visible_refresh_count"] > 0
        and usage["session_visible_refresh_count"] == 0
    )
    if interval_applies and elapsed is not None and elapsed < effective_interval:
        raise N3APhysicalExecutionError(
            "effective physical minimum refresh interval has not elapsed"
        )
    if cooldown_applies and elapsed is not None and elapsed < effective_cooldown:
        raise N3APhysicalExecutionError(
            "effective physical inter-session cooldown has not elapsed"
        )
    return {
        "authorization_confirmation_sha256": _sha256(
            required_authorization_confirmation(context.plan, snapshot).encode("ascii")
        ),
        "panel_plan_confirmation_sha256": _sha256(
            required_panel_plan_confirmation(context, snapshot).encode("utf-8")
        ),
        "profile_confirmation_sha256": _sha256(
            required_production_profile_confirmation(production).encode("utf-8")
        ),
        "profile_evaluated_at": evaluated_at,
        "live_evaluation_age_seconds": age,
        "maximum_live_evaluation_age_seconds": MAX_LIVE_EVALUATED_AT_AGE_SECONDS,
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


def validate_target_usage_continuity(
    production: ValidatedProductionProfile, prior_result: Mapping[str, Any]
) -> None:
    usage = production.profile["usage"]
    if (
        usage["session_visible_refresh_count"] != 1
        or usage["consecutive_visible_refresh_count"] != 1
        or usage["last_visible_refresh_completed_at"]
        != prior_result.get("completed_at")
    ):
        raise N3APhysicalExecutionError(
            "target usage evidence does not prove uninterrupted MAP continuity"
        )


def load_n3a_physical_production_profile(
    context: N3APhysicalContext,
    action_key: str,
    *,
    profile_file: Path,
    campaign_file: Path,
    firmware_binary_file: Path,
    limit_authority_file: Path,
    usage_evidence_file: Path,
    review_artifact_file: Optional[Path],
    reviewer_key_file: Optional[Path],
    evaluated_at: str,
) -> ValidatedProductionProfile:
    snapshot = load_n3a_physical_action_snapshot(context, action_key)
    try:
        standalone = read_standalone_physical_campaign(campaign_file)
        production = load_validated_production_profile(
            profile_file=profile_file,
            campaign_file=campaign_file,
            firmware_binary_file=firmware_binary_file,
            supplier_limits_file=limit_authority_file,
            usage_evidence_file=usage_evidence_file,
            review_artifact_file=review_artifact_file,
            reviewer_key_file=reviewer_key_file,
            evaluated_at=evaluated_at,
        )
    except (ProductionProfileError, ValueError, RuntimeError, OSError) as error:
        raise N3APhysicalExecutionError(
            f"deep N3A production profile failed: {error}"
        ) from error
    if (
        standalone != snapshot.campaign
        or production.inputs.campaign != snapshot.campaign
        or production.report["action_allowlist_count"]
        != len(snapshot.campaign["actions"])
    ):
        raise N3APhysicalExecutionError(
            "production profile does not bind the complete physical N3A campaign"
        )
    return production


def validate_control_records(
    context: N3APhysicalContext,
    snapshot: frozen.N3ActionSnapshot,
    production: ValidatedProductionProfile,
    records: Mapping[str, Mapping[str, Any]],
) -> None:
    evidence = records.get("evidence")
    claim = records.get("claim")
    lock = records.get("lock")
    if not all(isinstance(item, Mapping) for item in (evidence, claim, lock)):
        raise N3APhysicalExecutionError("physical control records are incomplete")
    assert evidence is not None and claim is not None and lock is not None
    expected = control_fields(
        context,
        snapshot,
        production,
        evaluated_at=str(evidence.get("profile_evaluated_at")),
        live_now=str(evidence.get("recorded_at")),
    )
    common = {key: expected[key] for key in _CONTROL_FIELDS}
    for label, record in (("claim", claim), ("lock", lock), ("evidence", evidence)):
        if {key: record.get(key) for key in _CONTROL_FIELDS} != common:
            raise N3APhysicalExecutionError(
                f"physical {label} plan/profile/freshness binding changed"
            )
    finalization = records.get("finalization")
    if finalization is not None and {
        key: finalization.get(key) for key in _CONTROL_FIELDS
    } != common:
        raise N3APhysicalExecutionError(
            "physical finalization plan/profile/freshness binding changed"
        )
    for label, record in (("evidence", evidence), ("finalization", finalization)):
        if record is not None and record.get(
            "authorization_confirmation_sha256"
        ) != expected["authorization_confirmation_sha256"]:
            raise N3APhysicalExecutionError(
                f"physical {label} action authorization binding changed"
            )
    if production.report.get("evaluated_at") != expected["profile_evaluated_at"]:
        raise N3APhysicalExecutionError("deep production evaluation time changed")


def validate_n3a_physical_finalized_action_bundle(
    context: N3APhysicalContext,
    bundle: Mapping[str, Any],
    *,
    production_profile: ValidatedProductionProfile,
    expected_action_key: Optional[str] = None,
    prior_bundle: Optional[Mapping[str, Any]] = None,
    prior_production_profile: Optional[ValidatedProductionProfile] = None,
) -> dict[str, Any]:
    plan = validate_n3a_physical_execution_context(context)
    compat = compatibility_plan(context)
    action_key = expected_action_key or str(bundle.get("evidence", {}).get("action_key"))
    snapshot = load_n3a_physical_action_snapshot(context, action_key)
    if (
        production_profile.report.get("production_ready") is not True
        or production_profile.inputs.campaign != snapshot.campaign
        or bundle.get("profile") != production_profile.profile
        or bundle.get("profile_file_sha256") != production_profile.profile_file.sha256
    ):
        raise N3APhysicalExecutionError(
            "stored N3A profile differs from deep production artifacts"
        )
    if prior_bundle is not None:
        if prior_production_profile is None:
            raise N3APhysicalExecutionError(
                "target prior requires its own deep production profile"
            )
        validate_n3a_physical_finalized_action_bundle(
            context,
            prior_bundle,
            production_profile=prior_production_profile,
        )
        validate_target_usage_continuity(production_profile, prior_bundle["result"])
    candidates = {
        (item.profile["integrity"]["canonical_sha256"], item.profile_file.sha256): item
        for item in (production_profile, prior_production_profile)
        if item is not None
    }

    def extension(
        _plan: Mapping[str, Any],
        item_snapshot: frozen.N3ActionSnapshot,
        records: Mapping[str, Mapping[str, Any]],
    ) -> None:
        claim = records["claim"]
        selected = candidates.get(
            (claim.get("profile_canonical_sha256"), claim.get("profile_file_sha256"))
        )
        if selected is None:
            raise N3APhysicalExecutionError(
                "control chain uses an unvalidated production profile"
            )
        validate_control_records(context, item_snapshot, selected, records)

    try:
        return frozen.validate_n3_finalized_action_bundle(
            compat,
            bundle,
            expected_action_key=expected_action_key,
            prior_bundle=prior_bundle,
            _plan_validator=lambda value: (
                compat
                if value == compat
                else (_ for _ in ()).throw(
                    N3APhysicalExecutionError("physical N3A plan changed")
                )
            ),
            _snapshot_loader=lambda _plan, key: load_n3a_physical_action_snapshot(
                context, key
            ),
            _plan_file_sha256=lambda _plan: _sha256(plan),
            _authorization_confirmation=required_authorization_confirmation,
            _record_extra_keys=PHYSICAL_RECORD_EXTRA_KEYS,
            _record_extension_validator=extension,
        )
    except frozen.N3ExecutionContractError as error:
        raise N3APhysicalExecutionError(
            f"physical N3A stored bundle is invalid: {error}"
        ) from error


def _strict_json(path: Path, *, label: str, maximum_bytes: int) -> Mapping[str, Any]:
    try:
        artifact = read_local_regular_file(path, label=label, maximum_bytes=maximum_bytes)
        value = json.loads(artifact.payload.decode("utf-8"))
    except (ProductionProfileError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N3APhysicalExecutionError(f"{label} is invalid: {error}") from error
    if not isinstance(value, Mapping) or artifact.payload != _canonical(value):
        raise N3APhysicalExecutionError(f"{label} must be canonical JSON")
    return value


def load_n3a_physical_execution_context(
    *,
    plan_file: Path,
    binding_review_artifact_file: Path,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
    n2_result_directories: Mapping[str, Path],
    n2_reviewer_key_file: Path,
) -> N3APhysicalContext:
    plan = _strict_json(plan_file, label="N3A physical plan", maximum_bytes=MAX_PLAN_BYTES)
    try:
        review = read_local_regular_file(
            binding_review_artifact_file,
            label="N3A physical binding review",
            maximum_bytes=MAX_REVIEW_BYTES,
        )
    except ProductionProfileError as error:
        raise N3APhysicalExecutionError(str(error)) from error
    context = N3APhysicalContext(
        plan=plan,
        binding_review_bytes=review.payload,
        minimum_interval_seconds=float(minimum_interval_seconds),
        planned_cooldown_seconds=float(planned_cooldown_seconds),
        n2_result_directories=dict(n2_result_directories),
        n2_reviewer_key_file=n2_reviewer_key_file,
    )
    validate_n3a_physical_execution_context(context)
    return context


__all__ = [
    "AUTHORIZATION_PREFIX",
    "AUTHORIZATION_SUFFIX",
    "MAX_LIVE_EVALUATED_AT_AGE_SECONDS",
    "N3APhysicalContext",
    "N3APhysicalExecutionError",
    "PANEL_PLAN_CONFIRMATION_PREFIX",
    "PHYSICAL_RECORD_EXTRA_KEYS",
    "PROFILE_CONFIRMATION_PREFIX",
    "compatibility_plan",
    "control_fields",
    "load_n3a_physical_action_snapshot",
    "load_n3a_physical_execution_context",
    "load_n3a_physical_production_profile",
    "n3a_physical_plan_file_sha256",
    "required_authorization_confirmation",
    "required_panel_plan_confirmation",
    "required_production_profile_confirmation",
    "validate_control_records",
    "validate_live_evaluation_time",
    "validate_n3a_physical_execution_context",
    "validate_n3a_physical_finalized_action_bundle",
    "validate_target_usage_continuity",
]
