#!/usr/bin/env python3
"""Compile and validate the physical-bound N4 V3 execution context.

This module joins three independently audited boundaries without performing
device I/O:

* the frozen N4 V3 frame/protocol source;
* one fully rebuilt physical campaign rebind rooted in the N2 panel/firmware
  anchor; and
* the deep production-profile verifier over real local artifact bytes.

The legacy N4 runner remains disabled.  Live execution is implemented only by
the separate physical runner, which consumes :class:`N4PhysicalContext`.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Optional

from host.visible_refresh_campaign import (
    CampaignContractError,
    PhysicalCampaignRebindError,
    ProductionProfileError,
    ValidatedProductionProfile,
    canonical_json_bytes,
    load_validated_production_profile,
    read_local_regular_file,
    read_physical_campaign_rebind_manifest,
    read_standalone_physical_campaign,
    validate_campaign_contract,
    validate_physical_campaign_rebind,
)
from tools import g1_s1_n4_v3_execution_contract as frozen


SCHEMA_VERSION = 1
CONTRACT_KIND = "mf1750-g1-s1-n4-v3-physical-execution-contract"
CONTRACT_ID_PREFIX = "g1-s1-n4-v3-physical-"
CONTRACT_HASH_SCOPE = (
    "entire N4 V3 physical execution contract excluding integrity; UTF-8 JSON "
    "with sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
MAX_REBIND_REVIEW_BYTES = 4 * 1024 * 1024
AUTHORIZATION_PREFIX = "AUTHORIZE_ONE_VISIBLE_RC2G_N4_V3_PHYSICAL__ACTION_"
AUTHORIZATION_SUFFIX = "__NO_RETRY_NO_RECOVERY"
PANEL_BUILD_CONFIRMATION_PREFIX = "CONFIRM_N4_V3_PHYSICAL_PANEL__SERIAL_"
PROFILE_CONFIRMATION_PREFIX = "CONFIRM_N4_V3_APPROVED_PRODUCTION_PROFILE"
MAX_LIVE_EVALUATED_AT_AGE_SECONDS = 300

_CONTROL_FIELDS = frozenset(
    {
        "panel_build_confirmation_sha256",
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


class N4PhysicalExecutionError(ValueError):
    """Raised when physical N4 identity or production evidence fails closed."""


@dataclass(frozen=True)
class N4PhysicalContext:
    """One deeply validated, immutable N4 physical execution context."""

    contract: Mapping[str, Any]
    rebind_manifest: Mapping[str, Any]
    physical_campaign: Mapping[str, Any]
    physical_anchor_campaign: Mapping[str, Any]
    binding_review_bytes: bytes
    minimum_interval_seconds: float
    planned_cooldown_seconds: float

    @property
    def binding_review_sha256(self) -> str:
        return hashlib.sha256(self.binding_review_bytes).hexdigest()


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (CampaignContractError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N4PhysicalExecutionError(
            f"value is not canonical JSON data: {error}"
        ) from error


def _integrity(unsigned: Mapping[str, Any]) -> dict[str, str]:
    return {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": CONTRACT_HASH_SCOPE,
    }


def _fixed_actions(campaign: Mapping[str, Any]) -> dict[str, str]:
    actions: dict[str, str] = {}
    for action in campaign["actions"]:
        identity = action["identity"]
        key = f"{identity['cell_id']}-{identity['phase']}"
        if key in actions:
            raise N4PhysicalExecutionError("physical N4 action key is duplicated")
        actions[key] = action["action_identity_sha256"]
    if tuple(actions) != frozen.FIXED_ACTION_KEYS:
        raise N4PhysicalExecutionError(
            "physical campaign is not the exact ordered eight-action N4 V3 set"
        )
    return actions


def _source_binding(contract: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": contract["kind"],
        "contract_id": contract["contract_id"],
        "canonical_sha256": contract["integrity"]["canonical_sha256"],
        "file_sha256": frozen.execution_contract_file_sha256(contract),
        "p0_campaign_canonical_sha256": contract[
            "p0_campaign_canonical_sha256"
        ],
        "p0_campaign_file_sha256": contract["p0_campaign_file_sha256"],
        "executable_after_physical_rebind": False,
    }


def _rebind_binding(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": manifest["kind"],
        "namespace": manifest["namespace"],
        "canonical_sha256": manifest["integrity"]["canonical_sha256"],
        "file_sha256": _sha256(manifest),
        "binding_canonical_sha256": manifest["binding"]["canonical_sha256"],
        "binding_review_artifact_sha256": manifest["binding"][
            "binding_review_artifact"
        ]["sha256"],
        "reviewed_schedule": _snapshot(manifest["binding"]["reviewed_schedule"]),
        "source_campaign_canonical_sha256": manifest["source"][
            "campaign_canonical_sha256"
        ],
        "physical_anchor_campaign_canonical_sha256": manifest["physical_anchor"][
            "campaign_canonical_sha256"
        ],
        "all_action_identities_rebuilt": True,
        "legacy_claims_reusable": False,
    }


def _power_semantics(source: Mapping[str, Any]) -> dict[str, Any]:
    result = _snapshot(source["power_semantics"])
    result["action_identities_changed"] = True
    result["physical_panel_instance_bound"] = True
    result["legacy_action_claims_reusable"] = False
    return result


def _evidence_contract(source: Mapping[str, Any]) -> dict[str, Any]:
    result = _snapshot(source["evidence_contract"])
    result.update(
        {
            "standalone_physical_campaign_required": True,
            "deep_production_profile_required_before_claim": True,
            "production_profile_full_campaign_allowlist_required": True,
            "real_firmware_limit_authority_usage_review_bytes_revalidated": True,
            "reviewer_key_never_copied_into_result": True,
        }
    )
    return result


def _classification() -> dict[str, Any]:
    return {
        "offline_compiled": True,
        "physical_panel_instance_bound": True,
        "deep_production_profile_evaluated_at_runtime": False,
        "hardware_execution_authorized": False,
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "automatic_execution": False,
        "automatic_retry": False,
        "automatic_recovery": False,
    }


def compile_n4_physical_execution_context(
    rebind_manifest: Mapping[str, Any],
    physical_campaign: Mapping[str, Any],
    physical_anchor_campaign: Mapping[str, Any],
    *,
    binding_review_bytes: bytes,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> N4PhysicalContext:
    """Compile a physical contract after replaying the complete rebind lineage."""

    source = frozen.compile_n4_v3_execution_contract()
    try:
        validated_rebind = validate_physical_campaign_rebind(
            rebind_manifest,
            source_campaign=source["p0_campaign"],
            physical_anchor_campaign=physical_anchor_campaign,
            binding_review_bytes=binding_review_bytes,
            minimum_interval_seconds=minimum_interval_seconds,
            planned_cooldown_seconds=planned_cooldown_seconds,
        )
        campaign = validate_campaign_contract(physical_campaign)
        anchor = validate_campaign_contract(physical_anchor_campaign)
    except (CampaignContractError, PhysicalCampaignRebindError) as error:
        raise N4PhysicalExecutionError(
            f"physical N4 rebind validation failed: {error}"
        ) from error
    if campaign != validated_rebind["physical_campaign"]:
        raise N4PhysicalExecutionError(
            "standalone physical campaign differs from the rebind manifest"
        )
    fixed_actions = _fixed_actions(campaign)
    source_by_action_id = {
        action["identity"]["action_id"]: action
        for action in source["p0_campaign"]["actions"]
    }
    physical_by_action_id = {
        action["identity"]["action_id"]: action for action in campaign["actions"]
    }
    if set(source_by_action_id) != set(physical_by_action_id):
        raise N4PhysicalExecutionError("physical N4 action membership changed")
    for key, old_sha in frozen.FIXED_ACTION_SHA256S.items():
        action_id = source_by_action_id[
            next(
                action_id
                for action_id, action in source_by_action_id.items()
                if action["action_identity_sha256"] == old_sha
            )
        ]["identity"]["action_id"]
        if physical_by_action_id[action_id]["action_identity_sha256"] != fixed_actions[key]:
            raise N4PhysicalExecutionError(
                f"physical N4 action mapping changed for {key}"
            )
    rebind_record = _rebind_binding(validated_rebind)
    contract_id = f"{CONTRACT_ID_PREFIX}{rebind_record['canonical_sha256']}"
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": CONTRACT_KIND,
        "contract_id": contract_id,
        "source_v3": _snapshot(source["source_v3"]),
        "source_execution_contract": _source_binding(source),
        "physical_rebind": rebind_record,
        "source_p0_campaign": _snapshot(source["p0_campaign"]),
        "source_p0_campaign_canonical_sha256": source[
            "p0_campaign_canonical_sha256"
        ],
        "source_p0_campaign_file_sha256": source["p0_campaign_file_sha256"],
        "p0_campaign": _snapshot(campaign),
        "p0_campaign_canonical_sha256": campaign["integrity"]["canonical_sha256"],
        "p0_campaign_file_sha256": _sha256(campaign),
        "fixed_actions": fixed_actions,
        "reviewed_schedule": _snapshot(
            validated_rebind["binding"]["reviewed_schedule"]
        ),
        "power_semantics": _power_semantics(source),
        "evidence_contract": _evidence_contract(source),
        "classification": _classification(),
    }
    contract = {**unsigned, "integrity": _integrity(unsigned)}
    context = N4PhysicalContext(
        contract=contract,
        rebind_manifest=_snapshot(validated_rebind),
        physical_campaign=_snapshot(campaign),
        physical_anchor_campaign=_snapshot(anchor),
        binding_review_bytes=bytes(binding_review_bytes),
        minimum_interval_seconds=float(minimum_interval_seconds),
        planned_cooldown_seconds=float(planned_cooldown_seconds),
    )
    return context


def validate_n4_physical_execution_context(
    context: N4PhysicalContext,
) -> Mapping[str, Any]:
    """Reconstruct a context from its retained immutable input snapshots."""

    if not isinstance(context, N4PhysicalContext):
        raise N4PhysicalExecutionError("physical N4 context type is invalid")
    expected = compile_n4_physical_execution_context(
        context.rebind_manifest,
        context.physical_campaign,
        context.physical_anchor_campaign,
        binding_review_bytes=context.binding_review_bytes,
        minimum_interval_seconds=context.minimum_interval_seconds,
        planned_cooldown_seconds=context.planned_cooldown_seconds,
    )
    if expected.contract != context.contract:
        raise N4PhysicalExecutionError(
            "physical N4 context differs from deterministic reconstruction"
        )
    return context.contract


def _validate_contract_shape(contract: Mapping[str, Any]) -> Mapping[str, Any]:
    keys = {
        "schema_version",
        "kind",
        "contract_id",
        "source_v3",
        "source_execution_contract",
        "physical_rebind",
        "source_p0_campaign",
        "source_p0_campaign_canonical_sha256",
        "source_p0_campaign_file_sha256",
        "p0_campaign",
        "p0_campaign_canonical_sha256",
        "p0_campaign_file_sha256",
        "fixed_actions",
        "reviewed_schedule",
        "power_semantics",
        "evidence_contract",
        "classification",
        "integrity",
    }
    if not isinstance(contract, Mapping) or set(contract) != keys:
        raise N4PhysicalExecutionError("physical N4 contract fields changed")
    if contract["schema_version"] != SCHEMA_VERSION or contract["kind"] != CONTRACT_KIND:
        raise N4PhysicalExecutionError("physical N4 contract identity changed")
    unsigned = dict(contract)
    integrity = unsigned.pop("integrity")
    if integrity != _integrity(unsigned):
        raise N4PhysicalExecutionError("physical N4 contract integrity is invalid")
    try:
        campaign = validate_campaign_contract(contract["p0_campaign"])
    except CampaignContractError as error:
        raise N4PhysicalExecutionError(f"physical N4 campaign is invalid: {error}") from error
    if (
        contract["p0_campaign_canonical_sha256"]
        != campaign["integrity"]["canonical_sha256"]
        or contract["p0_campaign_file_sha256"] != _sha256(campaign)
        or contract["fixed_actions"] != _fixed_actions(campaign)
        or contract["reviewed_schedule"]
        != contract["physical_rebind"].get("reviewed_schedule")
    ):
        raise N4PhysicalExecutionError("physical N4 campaign binding changed")
    return contract


def validate_n4_physical_execution_contract(
    contract: Mapping[str, Any], *, context: Optional[N4PhysicalContext] = None
) -> Mapping[str, Any]:
    """Validate self-integrity and optionally exact deep context equality."""

    root = _validate_contract_shape(contract)
    if context is not None:
        validate_n4_physical_execution_context(context)
        if root != context.contract:
            raise N4PhysicalExecutionError(
                "physical N4 contract differs from deep context"
            )
    return root


def n4_physical_execution_contract_file_sha256(contract: Mapping[str, Any]) -> str:
    return _sha256(validate_n4_physical_execution_contract(contract))


def required_n4_physical_authorization_confirmation(
    _contract: Mapping[str, Any], snapshot: frozen.N4V3ActionSnapshot
) -> str:
    return (
        f"{AUTHORIZATION_PREFIX}"
        f"{snapshot.action['action_identity_sha256'].upper()}"
        f"{AUTHORIZATION_SUFFIX}"
    )


def required_n4_physical_panel_build_confirmation(
    panel_serial: str, build_tag: str, binding_sha256: str
) -> str:
    for value, label in (
        (panel_serial, "panel serial"),
        (build_tag, "build tag"),
        (binding_sha256, "binding SHA-256"),
    ):
        if not isinstance(value, str) or not value or value != value.strip():
            raise N4PhysicalExecutionError(f"{label} is invalid")
    if (
        len(binding_sha256) != 64
        or any(character not in "0123456789abcdef" for character in binding_sha256)
    ):
        raise N4PhysicalExecutionError("binding SHA-256 is invalid")
    return (
        f"{PANEL_BUILD_CONFIRMATION_PREFIX}{panel_serial}"
        f"__BUILD_TAG_{build_tag}__BINDING_{binding_sha256.upper()}"
    )


def required_n4_physical_production_profile_confirmation(
    production: ValidatedProductionProfile,
) -> str:
    review = production.review_artifact_file
    reviewer_key_id = production.reviewer_key_id
    if review is None or reviewer_key_id is None:
        raise N4PhysicalExecutionError(
            "approved production review snapshots are incomplete"
        )
    values = (
        production.profile["integrity"]["canonical_sha256"],
        production.profile_file.sha256,
        review.sha256,
        reviewer_key_id,
        production.inputs.usage_evidence_file.sha256,
        production.inputs.limit_authority_file.sha256,
    )
    if any(
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
        for value in values
    ):
        raise N4PhysicalExecutionError(
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


def validate_n4_physical_live_evaluation_time(
    evaluated_at: str, live_now: str
) -> float:
    try:
        evaluated = frozen._timestamp(evaluated_at, label="live profile evaluated_at")
        current = frozen._timestamp(live_now, label="live execution current time")
    except frozen.N4V3ExecutionContractError as error:
        raise N4PhysicalExecutionError(str(error)) from error
    age_seconds = (current - evaluated).total_seconds()
    if age_seconds < 0:
        raise N4PhysicalExecutionError(
            "live profile evaluated_at must not be in the future"
        )
    if age_seconds > MAX_LIVE_EVALUATED_AT_AGE_SECONDS:
        raise N4PhysicalExecutionError(
            "live profile evaluated_at is too old; revalidate immediately"
        )
    return age_seconds


def n4_physical_control_fields(
    context: N4PhysicalContext,
    snapshot: frozen.N4V3ActionSnapshot,
    production: ValidatedProductionProfile,
    *,
    evaluated_at: str,
    live_now: str,
) -> dict[str, Any]:
    age = validate_n4_physical_live_evaluation_time(evaluated_at, live_now)
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
    except frozen.N4V3ExecutionContractError as error:
        raise N4PhysicalExecutionError(str(error)) from error
    identity = snapshot.action["identity"]
    sessions = [
        session
        for session in snapshot.campaign["sessions"]
        if session["session_id"] == identity["session_id"]
    ]
    if len(sessions) != 1:  # pragma: no cover - campaign validation is stricter
        raise N4PhysicalExecutionError("physical action session is not unique")
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
        raise N4PhysicalExecutionError(
            "effective physical minimum refresh interval has not elapsed"
        )
    if cooldown_applies and elapsed is not None and elapsed < effective_cooldown:
        raise N4PhysicalExecutionError(
            "effective physical inter-session cooldown has not elapsed"
        )
    binding_sha = context.rebind_manifest["binding"]["canonical_sha256"]
    panel_token = required_n4_physical_panel_build_confirmation(
        str(context.physical_campaign["panel"]["serial"]),
        str(context.physical_campaign["firmware"]["build_tag"]),
        str(binding_sha),
    )
    profile_token = required_n4_physical_production_profile_confirmation(production)
    action_token = required_n4_physical_authorization_confirmation(
        context.contract, snapshot
    )
    return {
        "authorization_confirmation_sha256": _sha256(action_token.encode("utf-8")),
        "panel_build_confirmation_sha256": _sha256(panel_token.encode("utf-8")),
        "profile_confirmation_sha256": _sha256(profile_token.encode("utf-8")),
        "profile_evaluated_at": evaluated_at,
        "live_evaluation_age_seconds": age,
        "maximum_live_evaluation_age_seconds": MAX_LIVE_EVALUATED_AT_AGE_SECONDS,
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


def validate_n4_physical_target_usage_continuity(
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
        raise N4PhysicalExecutionError(
            "target usage evidence does not prove uninterrupted MAP continuity"
        )


def validate_n4_physical_control_records(
    context: N4PhysicalContext,
    snapshot: frozen.N4V3ActionSnapshot,
    production: ValidatedProductionProfile,
    records: Mapping[str, Mapping[str, Any]],
) -> None:
    evidence = records.get("evidence")
    claim = records.get("claim")
    lock = records.get("lock")
    if not all(isinstance(value, Mapping) for value in (evidence, claim, lock)):
        raise N4PhysicalExecutionError("physical control records are incomplete")
    assert evidence is not None and claim is not None and lock is not None
    expected = n4_physical_control_fields(
        context,
        snapshot,
        production,
        evaluated_at=str(evidence.get("profile_evaluated_at")),
        live_now=str(evidence.get("recorded_at")),
    )
    common = {key: expected[key] for key in _CONTROL_FIELDS}
    for label, record in (("claim", claim), ("lock", lock), ("evidence", evidence)):
        actual = {key: record.get(key) for key in _CONTROL_FIELDS}
        if actual != common:
            raise N4PhysicalExecutionError(
                f"physical {label} panel/profile/freshness binding changed"
            )
    for label in ("evidence", "finalization"):
        record = records.get(label)
        if record is not None and record.get(
            "authorization_confirmation_sha256"
        ) != expected["authorization_confirmation_sha256"]:
            raise N4PhysicalExecutionError(
                f"physical {label} action authorization binding changed"
            )
    finalization = records.get("finalization")
    if finalization is not None:
        actual = {key: finalization.get(key) for key in _CONTROL_FIELDS}
        if actual != common:
            raise N4PhysicalExecutionError(
                "physical finalization panel/profile/freshness binding changed"
            )
    if production.report.get("evaluated_at") != expected["profile_evaluated_at"]:
        raise N4PhysicalExecutionError(
            "deep production report evaluation time changed"
        )


def load_n4_physical_execution_context(
    *,
    rebind_manifest_file: Path,
    physical_campaign_file: Path,
    physical_anchor_campaign_file: Path,
    binding_review_artifact_file: Path,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> N4PhysicalContext:
    """Safely load all physical binding artifacts and compile the context."""

    try:
        manifest = read_physical_campaign_rebind_manifest(rebind_manifest_file)
        campaign = read_standalone_physical_campaign(physical_campaign_file)
        anchor = read_standalone_physical_campaign(physical_anchor_campaign_file)
        review = read_local_regular_file(
            binding_review_artifact_file,
            label="N4 physical binding review artifact",
            maximum_bytes=MAX_REBIND_REVIEW_BYTES,
        )
    except (PhysicalCampaignRebindError, ProductionProfileError) as error:
        raise N4PhysicalExecutionError(str(error)) from error
    return compile_n4_physical_execution_context(
        manifest,
        campaign,
        anchor,
        binding_review_bytes=review.payload,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
    )


def load_n4_physical_action_snapshot(
    context: N4PhysicalContext, action_key: str
) -> frozen.N4V3ActionSnapshot:
    """Load one physical action while retaining the frozen frame bytes."""

    contract = validate_n4_physical_execution_contract(
        context.contract, context=context
    )
    fixed_actions = contract["fixed_actions"]
    if not isinstance(action_key, str) or action_key not in fixed_actions:
        raise N4PhysicalExecutionError(
            "action_key is not one of the eight physical N4 actions"
        )
    action_sha = fixed_actions[action_key]
    matches = [
        action
        for action in contract["p0_campaign"]["actions"]
        if action["action_identity_sha256"] == action_sha
    ]
    if len(matches) != 1:
        raise N4PhysicalExecutionError("physical N4 action is not unique")
    action = matches[0]
    source = frozen.load_n4_v3_action_snapshot(action_key)
    identity = action["identity"]
    source_identity = source.action["identity"]
    if any(
        identity[field] != source_identity[field]
        for field in ("session_id", "cell_id", "action_id", "phase", "frame", "request")
    ):
        raise N4PhysicalExecutionError("physical N4 action changed frozen semantics")
    expected_schedule = {
        **source_identity["schedule"],
        "minimum_interval_since_prior_seconds": (
            context.minimum_interval_seconds
            if source_identity["prior"] is not None
            else source_identity["schedule"][
                "minimum_interval_since_prior_seconds"
            ]
        ),
    }
    if identity["schedule"] != expected_schedule:
        raise N4PhysicalExecutionError("physical N4 reviewed action schedule changed")
    if _sha256(source.frame) != identity["frame"]["sha256"]:
        raise N4PhysicalExecutionError("physical N4 frame bytes changed")
    return frozen.N4V3ActionSnapshot(
        key=action_key,
        cell_id=identity["cell_id"],
        phase=identity["phase"],
        campaign=contract["p0_campaign"],
        action=action,
        frame=source.frame,
        reference_preview=source.reference_preview,
    )


def load_n4_physical_production_profile(
    context: N4PhysicalContext,
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
    """Deeply validate the real profile bytes against this physical context."""

    validate_n4_physical_execution_contract(context.contract, context=context)
    try:
        validated = load_validated_production_profile(
            profile_file=profile_file,
            campaign_file=campaign_file,
            firmware_binary_file=firmware_binary_file,
            supplier_limits_file=limit_authority_file,
            usage_evidence_file=usage_evidence_file,
            review_artifact_file=review_artifact_file,
            reviewer_key_file=reviewer_key_file,
            evaluated_at=evaluated_at,
        )
    except ProductionProfileError as error:
        raise N4PhysicalExecutionError(f"deep production profile failed: {error}") from error
    report = validated.report
    if (
        validated.inputs.campaign != context.physical_campaign
        or report["campaign_canonical_sha256"]
        != context.contract["p0_campaign_canonical_sha256"]
        or report["action_allowlist_count"] != len(context.physical_campaign["actions"])
    ):
        raise N4PhysicalExecutionError(
            "deep production profile does not bind the complete physical N4 campaign"
        )
    return validated


def _context_contract_validator(context: N4PhysicalContext):
    def validate(value: Mapping[str, Any]) -> Mapping[str, Any]:
        return validate_n4_physical_execution_contract(value, context=context)

    return validate


def _context_snapshot_loader(context: N4PhysicalContext):
    def load(_contract: Mapping[str, Any], action_key: str):
        return load_n4_physical_action_snapshot(context, action_key)

    return load


def validate_n4_physical_finalized_action_bundle(
    context: N4PhysicalContext,
    bundle: Mapping[str, Any],
    *,
    production_profile: ValidatedProductionProfile,
    expected_action_key: Optional[str] = None,
    prior_bundle: Optional[Mapping[str, Any]] = None,
    prior_production_profile: Optional[ValidatedProductionProfile] = None,
) -> dict[str, Any]:
    """Deep-validate stored N4 evidence plus authenticated production inputs."""

    contract = validate_n4_physical_execution_contract(
        context.contract, context=context
    )
    if production_profile.report.get("production_ready") is not True:
        raise N4PhysicalExecutionError(
            "stored N4 bundle profile was not deeply production-ready"
        )
    if (
        production_profile.inputs.campaign != context.physical_campaign
        or bundle.get("profile") != production_profile.profile
        or bundle.get("profile_file_sha256")
        != production_profile.profile_file.sha256
    ):
        raise N4PhysicalExecutionError(
            "stored N4 profile differs from deep production artifacts"
        )
    if prior_bundle is not None:
        if prior_production_profile is None:
            raise N4PhysicalExecutionError(
                "target prior requires its own deep production profile validation"
            )
        validate_n4_physical_finalized_action_bundle(
            context,
            prior_bundle,
            production_profile=prior_production_profile,
        )
        validate_n4_physical_target_usage_continuity(
            production_profile, prior_bundle["result"]
        )
    profile_candidates = {
        (
            item.profile["integrity"]["canonical_sha256"],
            item.profile_file.sha256,
        ): item
        for item in (production_profile, prior_production_profile)
        if item is not None
    }

    def validate_control_extension(
        _contract: Mapping[str, Any],
        snapshot: frozen.N4V3ActionSnapshot,
        records: Mapping[str, Mapping[str, Any]],
    ) -> None:
        claim = records["claim"]
        key = (
            claim.get("profile_canonical_sha256"),
            claim.get("profile_file_sha256"),
        )
        selected = profile_candidates.get(key)
        if selected is None:
            raise N4PhysicalExecutionError(
                "stored control chain uses an unvalidated production profile"
            )
        validate_n4_physical_control_records(
            context,
            snapshot,
            selected,
            records,
        )
    try:
        result = frozen.validate_n4_v3_finalized_action_bundle(
            contract,
            bundle,
            expected_action_key=expected_action_key,
            prior_bundle=prior_bundle,
            _contract_validator=_context_contract_validator(context),
            _snapshot_loader=_context_snapshot_loader(context),
            _contract_file_sha256=n4_physical_execution_contract_file_sha256,
            _authorization_confirmation=(
                required_n4_physical_authorization_confirmation
            ),
            _record_extra_keys=PHYSICAL_RECORD_EXTRA_KEYS,
            _record_extension_validator=validate_control_extension,
        )
    except frozen.N4V3ExecutionContractError as error:
        raise N4PhysicalExecutionError(
            f"physical N4 stored bundle is invalid: {error}"
        ) from error
    evidence = bundle["evidence"]
    if (
        evidence["profile_evaluated_at"] != production_profile.report["evaluated_at"]
        or evidence["p0_campaign_canonical_sha256"]
        != context.contract["p0_campaign_canonical_sha256"]
    ):
        raise N4PhysicalExecutionError(
            "stored N4 evidence differs from deep profile evaluation context"
        )
    return result


__all__ = [
    "CONTRACT_HASH_SCOPE",
    "CONTRACT_ID_PREFIX",
    "CONTRACT_KIND",
    "AUTHORIZATION_PREFIX",
    "AUTHORIZATION_SUFFIX",
    "MAX_REBIND_REVIEW_BYTES",
    "MAX_LIVE_EVALUATED_AT_AGE_SECONDS",
    "N4PhysicalContext",
    "N4PhysicalExecutionError",
    "PANEL_BUILD_CONFIRMATION_PREFIX",
    "PHYSICAL_RECORD_EXTRA_KEYS",
    "PROFILE_CONFIRMATION_PREFIX",
    "compile_n4_physical_execution_context",
    "load_n4_physical_action_snapshot",
    "load_n4_physical_execution_context",
    "load_n4_physical_production_profile",
    "n4_physical_execution_contract_file_sha256",
    "required_n4_physical_authorization_confirmation",
    "required_n4_physical_panel_build_confirmation",
    "required_n4_physical_production_profile_confirmation",
    "n4_physical_control_fields",
    "validate_n4_physical_target_usage_continuity",
    "validate_n4_physical_control_records",
    "validate_n4_physical_live_evaluation_time",
    "validate_n4_physical_execution_context",
    "validate_n4_physical_execution_contract",
    "validate_n4_physical_finalized_action_bundle",
]
