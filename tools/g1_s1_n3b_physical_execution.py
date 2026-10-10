#!/usr/bin/env python3
"""Compile and deeply validate the physical-bound N3B execution plan.

The four frozen Williams blocks remain the frame/order source.  Every block is
independently rebound to one physical N2 panel/firmware anchor, with an
operator-selected experimental interval/cooldown embedded in the binding hash.
This module performs no claim, network, device, firmware, or power I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Optional

from host.visible_refresh_campaign import (
    CampaignContractError,
    PhysicalCampaignRebindError,
    ProductionProfileError,
    ValidatedProductionProfile,
    canonical_json_bytes,
    compile_physical_campaign_rebind,
    load_validated_production_profile,
    read_local_regular_file,
    read_standalone_physical_campaign,
    validate_campaign_contract,
    validate_physical_campaign_rebind,
)
from tools import g1_s1_n3_execution_contract as frozen


SCHEMA_VERSION = 1
PLAN_KIND = "mf1750-g1-s1-n3b-physical-execution-plan"
PLAN_HASH_SCOPE = (
    "entire N3B physical execution plan excluding integrity; UTF-8 JSON with "
    "sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
PLAN_ID_PREFIX = "g1-s1-n3b-physical-"
AUTHORIZATION_PREFIX = "AUTHORIZE_ONE_VISIBLE_RC2G_N3B_PHYSICAL__ACTION_"
AUTHORIZATION_SUFFIX = "__NO_RETRY_NO_RECOVERY"
PANEL_PLAN_CONFIRMATION_PREFIX = "CONFIRM_N3B_PHYSICAL_PANEL_PLAN"
PROFILE_CONFIRMATION_PREFIX = "CONFIRM_N3B_APPROVED_PRODUCTION_PROFILE"
MAX_LIVE_EVALUATED_AT_AGE_SECONDS = 300
MAX_PLAN_BYTES = 64 * 1024 * 1024
MAX_REVIEW_BYTES = 4 * 1024 * 1024

_NAMESPACE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}\Z")
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


class N3BPhysicalExecutionError(ValueError):
    """A physical N3B plan or its deep evidence failed closed."""


@dataclass(frozen=True)
class N3BPhysicalContext:
    plan: Mapping[str, Any]
    binding_review_bytes: bytes
    minimum_interval_seconds: float
    planned_cooldown_seconds: float


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (CampaignContractError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N3BPhysicalExecutionError(
            f"value is not canonical JSON data: {error}"
        ) from error


def _integrity(unsigned: Mapping[str, Any]) -> dict[str, str]:
    return {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": PLAN_HASH_SCOPE,
    }


def _seal_embedded_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    unsigned = _snapshot(manifest)
    integrity = unsigned.pop("integrity")
    scope = integrity["canonical_sha256_scope"]
    return {
        **unsigned,
        "integrity": {
            "canonical_sha256": _sha256(unsigned),
            "canonical_sha256_scope": scope,
        },
    }


def _source_plan(measurement_assets: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        plan = frozen.compile_n3b_exact_plan(measurement_assets=measurement_assets)
        root = frozen.validate_n3_exact_plan(plan)
    except frozen.N3ExecutionContractError as error:
        raise N3BPhysicalExecutionError(
            f"source N3B exact plan is invalid: {error}"
        ) from error
    if (
        root["study"] != "N3B"
        or root["readiness"]["measurement_assets_ready"] is not True
        or root["readiness"]["measurement_asset_blockers"]
    ):
        raise N3BPhysicalExecutionError(
            "physical N3B requires all ten measurement asset identities"
        )
    return root


def _rebuild_branch(
    source_branch: Mapping[str, Any], rebind_manifest: Mapping[str, Any]
) -> dict[str, Any]:
    campaign = rebind_manifest["physical_campaign"]
    identity_map = {
        item["source_action_identity_sha256"]: item[
            "physical_action_identity_sha256"
        ]
        for item in rebind_manifest["action_identity_map"]
    }
    routes = []
    for route in source_branch["routes"]:
        rebuilt = _snapshot(route)
        rebuilt["map_action_identity_sha256"] = identity_map[
            route["map_action_identity_sha256"]
        ]
        rebuilt["target_action_identity_sha256"] = identity_map[
            route["target_action_identity_sha256"]
        ]
        routes.append(rebuilt)
    return {
        **{
            key: _snapshot(value)
            for key, value in source_branch.items()
            if key not in {"p0_campaign", "routes"}
        },
        "p0_campaign": _snapshot(campaign),
        "routes": routes,
    }


def _physical_manifest(
    source_plan: Mapping[str, Any], rebinds: list[Mapping[str, Any]]
) -> dict[str, Any]:
    source = source_plan["execution_manifest"]
    branches = source["branches"]
    physical_branches = [
        _rebuild_branch(branch, manifest)
        for branch, manifest in zip(branches, rebinds)
    ]
    unsigned = {
        **{
            key: _snapshot(value)
            for key, value in source.items()
            if key not in {"integrity", "branches", "panel", "firmware"}
        },
        "panel": _snapshot(rebinds[0]["physical_campaign"]["panel"]),
        "firmware": _snapshot(rebinds[0]["physical_campaign"]["firmware"]),
        "branches": physical_branches,
    }
    return _seal_embedded_manifest(
        {**unsigned, "integrity": source["integrity"]}
    )


def _physical_routes(
    source_plan: Mapping[str, Any], rebinds: list[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    rebind_by_branch = {
        f"n3b-balanced-block-{index}": manifest
        for index, manifest in enumerate(rebinds, start=1)
    }
    routes: list[dict[str, Any]] = []
    for source in source_plan["selected_routes"]:
        manifest = rebind_by_branch[source["branch_id"]]
        campaign = manifest["physical_campaign"]
        identity_map = {
            item["source_action_identity_sha256"]: item[
                "physical_action_identity_sha256"
            ]
            for item in manifest["action_identity_map"]
        }
        route = _snapshot(source)
        route.update(
            {
                "campaign_id": campaign["campaign_id"],
                "p0_campaign_canonical_sha256": campaign["integrity"][
                    "canonical_sha256"
                ],
                "map_action_identity_sha256": identity_map[
                    source["map_action_identity_sha256"]
                ],
                "target_action_identity_sha256": identity_map[
                    source["target_action_identity_sha256"]
                ],
            }
        )
        routes.append(route)
    return routes


def _fixed_actions(routes: list[Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for route in routes:
        for label, phase in (("map", "map-primer"), ("target", "target")):
            key = route[f"{label}_action_key"]
            result[key] = {
                "action_identity_sha256": route[
                    f"{label}_action_identity_sha256"
                ],
                "phase": phase,
                "cell_id": route["cell_id"],
                "candidate_cell_id": route["candidate_cell_id"],
                "campaign_id": route["campaign_id"],
                "p0_campaign_canonical_sha256": route[
                    "p0_campaign_canonical_sha256"
                ],
                "prior_action_key": (
                    route["map_action_key"] if label == "target" else None
                ),
            }
    if len(result) != 32:
        raise N3BPhysicalExecutionError(
            "physical N3B plan must contain exactly 32 unique actions"
        )
    return result


def _compile_from_source(
    source_plan: Mapping[str, Any],
    physical_anchor_campaign: Mapping[str, Any],
    *,
    binding_review_bytes: bytes,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
    namespace_prefix: str,
) -> dict[str, Any]:
    try:
        source = frozen.validate_n3_exact_plan(source_plan)
        anchor = validate_campaign_contract(physical_anchor_campaign)
    except (frozen.N3ExecutionContractError, CampaignContractError) as error:
        raise N3BPhysicalExecutionError(str(error)) from error
    if (
        source["study"] != "N3B"
        or source["readiness"]["measurement_assets_ready"] is not True
    ):
        raise N3BPhysicalExecutionError(
            "source must be the complete measurement-ready N3B exact plan"
        )
    if (
        not isinstance(namespace_prefix, str)
        or _NAMESPACE_RE.fullmatch(namespace_prefix) is None
    ):
        raise N3BPhysicalExecutionError("N3B namespace prefix is invalid")
    branches = source["execution_manifest"]["branches"]
    if len(branches) != 4:
        raise N3BPhysicalExecutionError("source N3B plan lost one of four blocks")
    rebinds: list[Mapping[str, Any]] = []
    try:
        for index, branch in enumerate(branches, start=1):
            manifest = compile_physical_campaign_rebind(
                branch["p0_campaign"],
                anchor,
                namespace=f"{namespace_prefix}-block-{index}",
                binding_review_bytes=binding_review_bytes,
                minimum_interval_seconds=minimum_interval_seconds,
                planned_cooldown_seconds=planned_cooldown_seconds,
            )
            validate_physical_campaign_rebind(
                manifest,
                source_campaign=branch["p0_campaign"],
                physical_anchor_campaign=anchor,
                binding_review_bytes=binding_review_bytes,
                minimum_interval_seconds=minimum_interval_seconds,
                planned_cooldown_seconds=planned_cooldown_seconds,
            )
            rebinds.append(manifest)
    except PhysicalCampaignRebindError as error:
        raise N3BPhysicalExecutionError(
            f"N3B physical block rebind failed: {error}"
        ) from error
    manifest = _physical_manifest(source, rebinds)
    routes = _physical_routes(source, rebinds)
    actions = _fixed_actions(routes)
    binding_hashes = [item["binding"]["canonical_sha256"] for item in rebinds]
    aggregate = _sha256(binding_hashes)
    schedule = _snapshot(rebinds[0]["binding"]["reviewed_schedule"])
    if any(item["binding"]["reviewed_schedule"] != schedule for item in rebinds):
        raise N3BPhysicalExecutionError("N3B blocks use different reviewed schedules")
    source_power = _snapshot(source["power_semantics"])
    source_power.update(
        {
            "physical_panel_instance_bound": True,
            "action_identities_changed": True,
            "legacy_action_claims_reusable": False,
        }
    )
    evidence_contract = _snapshot(source["evidence_contract"])
    evidence_contract.update(
        {
            "standalone_physical_campaign_required": True,
            "deep_production_profile_required_before_claim": True,
            "full_block_campaign_allowlist_required": True,
            "real_limit_authority_usage_review_firmware_bytes_revalidated": True,
            "reviewer_key_never_copied_into_result": True,
        }
    )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": PLAN_KIND,
        "plan_id": f"{PLAN_ID_PREFIX}{aggregate}",
        "study": "N3B",
        "namespace_prefix": namespace_prefix,
        "source_exact_plan": _snapshot(source),
        "source_manifest": _snapshot(source["source_manifest"]),
        "physical_anchor_campaign": _snapshot(anchor),
        "binding_review_artifact": {
            "bytes": len(binding_review_bytes),
            "sha256": _sha256(binding_review_bytes),
            "actual_bytes_hashed": True,
        },
        "process_schedule": schedule,
        "physical_rebinds": [
            {
                "block_index": index,
                "branch_id": f"n3b-balanced-block-{index}",
                "manifest": _snapshot(item),
            }
            for index, item in enumerate(rebinds, start=1)
        ],
        "execution_manifest": manifest,
        "execution_manifest_file_sha256": _sha256(manifest),
        "selection": _snapshot(source["selection"]),
        "selected_routes": routes,
        "fixed_actions": actions,
        "power_semantics": source_power,
        "evidence_contract": evidence_contract,
        "readiness": {
            "physical_plan_compiled": True,
            "measurement_assets_ready": True,
            "physical_panel_bound": True,
            "reviewed_schedule_bound": True,
            "deep_production_profile_evaluated_at_runtime": False,
            "hardware_ready": False,
        },
        "classification": {
            "offline_compiled": True,
            "software_ready": True,
            "hardware_ready": False,
            "hardware_execution_authorized": False,
            "claim_created": False,
            "network_io_performed": False,
            "device_io_performed": False,
            "automatic_execution": False,
            "automatic_retry": False,
            "automatic_recovery": False,
        },
    }
    return {**unsigned, "integrity": _integrity(unsigned)}


def compile_n3b_physical_execution_context(
    physical_anchor_campaign: Mapping[str, Any],
    *,
    measurement_assets: Mapping[str, Any],
    binding_review_bytes: bytes,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
    namespace_prefix: str = "n3b-physical",
) -> N3BPhysicalContext:
    """Build all four physical blocks from one reviewed process schedule."""

    source = _source_plan(measurement_assets)
    plan = _compile_from_source(
        source,
        physical_anchor_campaign,
        binding_review_bytes=binding_review_bytes,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
        namespace_prefix=namespace_prefix,
    )
    return N3BPhysicalContext(
        plan=plan,
        binding_review_bytes=bytes(binding_review_bytes),
        minimum_interval_seconds=float(minimum_interval_seconds),
        planned_cooldown_seconds=float(planned_cooldown_seconds),
    )


def validate_n3b_physical_execution_context(
    context: N3BPhysicalContext,
) -> Mapping[str, Any]:
    if not isinstance(context, N3BPhysicalContext):
        raise N3BPhysicalExecutionError("physical N3B context type is invalid")
    expected = _compile_from_source(
        context.plan["source_exact_plan"],
        context.plan["physical_anchor_campaign"],
        binding_review_bytes=context.binding_review_bytes,
        minimum_interval_seconds=context.minimum_interval_seconds,
        planned_cooldown_seconds=context.planned_cooldown_seconds,
        namespace_prefix=context.plan["namespace_prefix"],
    )
    if expected != context.plan:
        raise N3BPhysicalExecutionError(
            "physical N3B context differs from deterministic reconstruction"
        )
    return context.plan


def n3b_physical_plan_file_sha256(plan: Mapping[str, Any]) -> str:
    if not isinstance(plan, Mapping) or plan.get("kind") != PLAN_KIND:
        raise N3BPhysicalExecutionError("physical N3B plan identity is invalid")
    unsigned = dict(plan)
    integrity = unsigned.pop("integrity", None)
    if integrity != _integrity(unsigned):
        raise N3BPhysicalExecutionError("physical N3B plan integrity is invalid")
    return _sha256(plan)


def _campaign_for_fixed_action(
    plan: Mapping[str, Any], fixed: Mapping[str, Any]
) -> Mapping[str, Any]:
    matches = [
        item["manifest"]["physical_campaign"]
        for item in plan["physical_rebinds"]
        if item["manifest"]["physical_campaign"]["campaign_id"]
        == fixed["campaign_id"]
    ]
    if len(matches) != 1:
        raise N3BPhysicalExecutionError("physical N3B action campaign is not unique")
    return validate_campaign_contract(matches[0])


def load_n3b_physical_action_snapshot(
    context: N3BPhysicalContext, action_key: str
) -> frozen.N3ActionSnapshot:
    plan = validate_n3b_physical_execution_context(context)
    if not isinstance(action_key, str) or action_key not in plan["fixed_actions"]:
        raise N3BPhysicalExecutionError("action_key is not in physical N3B plan")
    fixed = plan["fixed_actions"][action_key]
    campaign = _campaign_for_fixed_action(plan, fixed)
    actions = {
        action["action_identity_sha256"]: action for action in campaign["actions"]
    }
    action = actions.get(fixed["action_identity_sha256"])
    if action is None:
        raise N3BPhysicalExecutionError("physical N3B action is missing")
    routes = [
        route
        for route in plan["selected_routes"]
        if action_key in {route["map_action_key"], route["target_action_key"]}
    ]
    if len(routes) != 1:
        raise N3BPhysicalExecutionError("physical N3B route is not unique")
    try:
        source = frozen.load_n3_action_snapshot(
            plan["source_exact_plan"], action_key
        )
    except frozen.N3ExecutionContractError as error:
        raise N3BPhysicalExecutionError(str(error)) from error
    old_identity = source.action["identity"]
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
            raise N3BPhysicalExecutionError(
                f"physical N3B action changed frozen {field} semantics"
            )
    expected_interval = (
        context.minimum_interval_seconds
        if old_identity["prior"] is not None
        else old_identity["schedule"]["minimum_interval_since_prior_seconds"]
    )
    if identity["schedule"] != {
        **old_identity["schedule"],
        "minimum_interval_since_prior_seconds": expected_interval,
    }:
        raise N3BPhysicalExecutionError("physical N3B action schedule changed")
    if _sha256(source.frame) != identity["frame"]["sha256"]:
        raise N3BPhysicalExecutionError("physical N3B frame bytes changed")
    return frozen.N3ActionSnapshot(
        plan=plan,
        key=action_key,
        cell_id=fixed["cell_id"],
        candidate_cell_id=fixed["candidate_cell_id"],
        phase=fixed["phase"],
        campaign=campaign,
        action=action,
        route=routes[0],
        frame=source.frame,
        reference_preview=source.reference_preview,
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
    context: N3BPhysicalContext, snapshot: frozen.N3ActionSnapshot
) -> str:
    plan = validate_n3b_physical_execution_context(context)
    rebinds = [
        item["manifest"]
        for item in plan["physical_rebinds"]
        if item["manifest"]["physical_campaign"]["campaign_id"]
        == snapshot.campaign["campaign_id"]
    ]
    if len(rebinds) != 1:
        raise N3BPhysicalExecutionError("action rebind binding is not unique")
    return (
        f"{PANEL_PLAN_CONFIRMATION_PREFIX}"
        f"__SERIAL_{snapshot.campaign['panel']['serial']}"
        f"__BUILD_TAG_{snapshot.campaign['firmware']['build_tag']}"
        f"__PLAN_{plan['integrity']['canonical_sha256'].upper()}"
        f"__REBIND_{rebinds[0]['binding']['canonical_sha256'].upper()}"
        f"__ASSETS_{plan['execution_manifest']['measurement_asset_registry_sha256'].upper()}"
    )


def required_production_profile_confirmation(
    production: ValidatedProductionProfile,
) -> str:
    review = production.review_artifact_file
    if review is None or production.reviewer_key_id is None:
        raise N3BPhysicalExecutionError("approved production review is incomplete")
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
        raise N3BPhysicalExecutionError(
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


def validate_live_evaluation_time(evaluated_at: str, live_now: str) -> float:
    try:
        evaluated = frozen._timestamp(evaluated_at, label="profile evaluated_at")
        current = frozen._timestamp(live_now, label="live execution current time")
    except frozen.N3ExecutionContractError as error:
        raise N3BPhysicalExecutionError(str(error)) from error
    age = (current - evaluated).total_seconds()
    if age < 0:
        raise N3BPhysicalExecutionError("profile evaluated_at must not be future")
    if age > MAX_LIVE_EVALUATED_AT_AGE_SECONDS:
        raise N3BPhysicalExecutionError(
            "profile evaluated_at is too old; revalidate immediately"
        )
    return age


def control_fields(
    context: N3BPhysicalContext,
    snapshot: frozen.N3ActionSnapshot,
    production: ValidatedProductionProfile,
    *,
    evaluated_at: str,
    live_now: str,
) -> dict[str, Any]:
    age = validate_live_evaluation_time(evaluated_at, live_now)
    try:
        current = frozen._timestamp(live_now, label="live execution current time")
        last_visible_value = production.profile["usage"][
            "last_visible_refresh_completed_at"
        ]
        last_visible = (
            None
            if last_visible_value is None
            else frozen._timestamp(
                last_visible_value,
                label="usage last_visible_refresh_completed_at",
            )
        )
    except frozen.N3ExecutionContractError as error:
        raise N3BPhysicalExecutionError(str(error)) from error
    identity = snapshot.action["identity"]
    sessions = [
        session
        for session in snapshot.campaign["sessions"]
        if session["session_id"] == identity["session_id"]
    ]
    if len(sessions) != 1:  # pragma: no cover - campaign validation is stricter
        raise N3BPhysicalExecutionError("physical action session is not unique")
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
    elapsed = (
        None if last_visible is None else (current - last_visible).total_seconds()
    )
    interval_applies = last_visible is not None
    cooldown_applies = (
        last_visible is not None
        and usage["cumulative_visible_refresh_count"] > 0
        and usage["session_visible_refresh_count"] == 0
    )
    if interval_applies and elapsed is not None and elapsed < effective_interval:
        raise N3BPhysicalExecutionError(
            "effective physical minimum refresh interval has not elapsed"
        )
    if cooldown_applies and elapsed is not None and elapsed < effective_cooldown:
        raise N3BPhysicalExecutionError(
            "effective physical inter-session cooldown has not elapsed"
        )
    return {
        "authorization_confirmation_sha256": _sha256(
            required_authorization_confirmation(context.plan, snapshot).encode(
                "ascii"
            )
        ),
        "panel_plan_confirmation_sha256": _sha256(
            required_panel_plan_confirmation(context, snapshot).encode("utf-8")
        ),
        "profile_confirmation_sha256": _sha256(
            required_production_profile_confirmation(production).encode("utf-8")
        ),
        "profile_evaluated_at": evaluated_at,
        "live_evaluation_age_seconds": age,
        "maximum_live_evaluation_age_seconds": (
            MAX_LIVE_EVALUATED_AT_AGE_SECONDS
        ),
        "schedule_reference_completed_at": (
            None
            if last_visible is None
            else last_visible_value
        ),
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
    production: ValidatedProductionProfile,
    prior_result: Mapping[str, Any],
) -> None:
    """Require authenticated usage to identify MAP as the latest refresh."""

    usage = production.profile["usage"]
    if (
        usage["session_visible_refresh_count"] != 1
        or usage["consecutive_visible_refresh_count"] != 1
        or usage["last_visible_refresh_completed_at"]
        != prior_result.get("completed_at")
    ):
        raise N3BPhysicalExecutionError(
            "target usage evidence does not prove uninterrupted MAP continuity"
        )


def validate_control_records(
    context: N3BPhysicalContext,
    snapshot: frozen.N3ActionSnapshot,
    production: ValidatedProductionProfile,
    records: Mapping[str, Mapping[str, Any]],
) -> None:
    evidence = records.get("evidence")
    claim = records.get("claim")
    lock = records.get("lock")
    if not all(isinstance(item, Mapping) for item in (evidence, claim, lock)):
        raise N3BPhysicalExecutionError("physical control records are incomplete")
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
            raise N3BPhysicalExecutionError(
                f"physical {label} plan/profile/freshness binding changed"
            )
    for label in ("evidence", "finalization"):
        record = records.get(label)
        if record is not None and record.get(
            "authorization_confirmation_sha256"
        ) != expected["authorization_confirmation_sha256"]:
            raise N3BPhysicalExecutionError(
                f"physical {label} action authorization binding changed"
            )
    finalization = records.get("finalization")
    if finalization is not None and {
        key: finalization.get(key) for key in _CONTROL_FIELDS
    } != common:
        raise N3BPhysicalExecutionError(
            "physical finalization plan/profile/freshness binding changed"
        )
    if production.report.get("evaluated_at") != expected["profile_evaluated_at"]:
        raise N3BPhysicalExecutionError("deep production evaluation time changed")


def load_n3b_physical_production_profile(
    context: N3BPhysicalContext,
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
    snapshot = load_n3b_physical_action_snapshot(context, action_key)
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
    except (PhysicalCampaignRebindError, ProductionProfileError) as error:
        raise N3BPhysicalExecutionError(
            f"deep N3B production profile failed: {error}"
        ) from error
    if (
        standalone != snapshot.campaign
        or production.inputs.campaign != snapshot.campaign
        or production.report["action_allowlist_count"]
        != len(snapshot.campaign["actions"])
    ):
        raise N3BPhysicalExecutionError(
            "production profile does not bind the complete physical N3B block"
        )
    return production


def validate_n3b_physical_finalized_action_bundle(
    context: N3BPhysicalContext,
    bundle: Mapping[str, Any],
    *,
    production_profile: ValidatedProductionProfile,
    expected_action_key: Optional[str] = None,
    prior_bundle: Optional[Mapping[str, Any]] = None,
    prior_production_profile: Optional[ValidatedProductionProfile] = None,
) -> dict[str, Any]:
    plan = validate_n3b_physical_execution_context(context)
    action_key = expected_action_key or str(bundle.get("evidence", {}).get("action_key"))
    snapshot = load_n3b_physical_action_snapshot(context, action_key)
    if (
        production_profile.report.get("production_ready") is not True
        or production_profile.inputs.campaign != snapshot.campaign
        or bundle.get("profile") != production_profile.profile
        or bundle.get("profile_file_sha256")
        != production_profile.profile_file.sha256
    ):
        raise N3BPhysicalExecutionError(
            "stored N3B profile differs from deep production artifacts"
        )
    if prior_bundle is not None:
        if prior_production_profile is None:
            raise N3BPhysicalExecutionError(
                "target prior requires its own deep production profile"
            )
        validate_n3b_physical_finalized_action_bundle(
            context,
            prior_bundle,
            production_profile=prior_production_profile,
        )
        validate_target_usage_continuity(
            production_profile, prior_bundle["result"]
        )
    candidates = {
        (
            item.profile["integrity"]["canonical_sha256"],
            item.profile_file.sha256,
        ): item
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
            (
                claim.get("profile_canonical_sha256"),
                claim.get("profile_file_sha256"),
            )
        )
        if selected is None:
            raise N3BPhysicalExecutionError(
                "control chain uses an unvalidated production profile"
            )
        validate_control_records(context, item_snapshot, selected, records)

    try:
        result = frozen.validate_n3_finalized_action_bundle(
            plan,
            bundle,
            expected_action_key=expected_action_key,
            prior_bundle=prior_bundle,
            _plan_validator=lambda value: (
                plan
                if value == plan
                else (_ for _ in ()).throw(
                    N3BPhysicalExecutionError("physical N3B plan changed")
                )
            ),
            _snapshot_loader=lambda _plan, key: load_n3b_physical_action_snapshot(
                context, key
            ),
            _plan_file_sha256=n3b_physical_plan_file_sha256,
            _authorization_confirmation=required_authorization_confirmation,
            _record_extra_keys=PHYSICAL_RECORD_EXTRA_KEYS,
            _record_extension_validator=extension,
        )
    except frozen.N3ExecutionContractError as error:
        raise N3BPhysicalExecutionError(
            f"physical N3B stored bundle is invalid: {error}"
        ) from error
    if bundle["evidence"]["profile_evaluated_at"] != production_profile.report[
        "evaluated_at"
    ]:
        raise N3BPhysicalExecutionError(
            "stored N3B evidence changed production evaluation context"
        )
    return result


def _strict_json(path: Path, *, label: str, maximum_bytes: int) -> Mapping[str, Any]:
    try:
        artifact = read_local_regular_file(
            path, label=label, maximum_bytes=maximum_bytes
        )
        value = json.loads(artifact.payload.decode("utf-8"))
    except (ProductionProfileError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N3BPhysicalExecutionError(f"{label} is invalid: {error}") from error
    if not isinstance(value, Mapping) or artifact.payload != canonical_json_bytes(value):
        raise N3BPhysicalExecutionError(f"{label} must be canonical JSON")
    return value


def load_n3b_physical_execution_context(
    *,
    plan_file: Path,
    binding_review_artifact_file: Path,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> N3BPhysicalContext:
    plan = _strict_json(plan_file, label="N3B physical plan", maximum_bytes=MAX_PLAN_BYTES)
    try:
        review = read_local_regular_file(
            binding_review_artifact_file,
            label="N3B physical binding review",
            maximum_bytes=MAX_REVIEW_BYTES,
        )
    except ProductionProfileError as error:
        raise N3BPhysicalExecutionError(str(error)) from error
    context = N3BPhysicalContext(
        plan=plan,
        binding_review_bytes=review.payload,
        minimum_interval_seconds=float(minimum_interval_seconds),
        planned_cooldown_seconds=float(planned_cooldown_seconds),
    )
    validate_n3b_physical_execution_context(context)
    return context


__all__ = [
    "AUTHORIZATION_PREFIX",
    "AUTHORIZATION_SUFFIX",
    "MAX_LIVE_EVALUATED_AT_AGE_SECONDS",
    "N3BPhysicalContext",
    "N3BPhysicalExecutionError",
    "PANEL_PLAN_CONFIRMATION_PREFIX",
    "PHYSICAL_RECORD_EXTRA_KEYS",
    "PLAN_HASH_SCOPE",
    "PLAN_ID_PREFIX",
    "PLAN_KIND",
    "PROFILE_CONFIRMATION_PREFIX",
    "compile_n3b_physical_execution_context",
    "control_fields",
    "validate_target_usage_continuity",
    "load_n3b_physical_action_snapshot",
    "load_n3b_physical_execution_context",
    "load_n3b_physical_production_profile",
    "n3b_physical_plan_file_sha256",
    "required_authorization_confirmation",
    "required_panel_plan_confirmation",
    "required_production_profile_confirmation",
    "validate_control_records",
    "validate_live_evaluation_time",
    "validate_n3b_physical_execution_context",
    "validate_n3b_physical_finalized_action_bundle",
]
