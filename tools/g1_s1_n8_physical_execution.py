#!/usr/bin/env python3
"""Compile and deeply validate the physical-bound N8 execution contract.

The frozen N8 science remains unchanged, but every one of its fifteen P0
actions, five sessions, priors, and global claim filenames is rebuilt against
one reviewed physical panel/RC2G firmware anchor.  This module performs no
claim, authorization, network, device, reset, firmware, GPIO, or power I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

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
from tools import g1_s1_n8_carryover_campaign as campaign
from tools import g1_s1_n8_execution_contract as frozen


SCHEMA_VERSION = 1
CONTRACT_KIND = "mf1750-g1-s1-n8-physical-execution-contract"
CONTRACT_ID_PREFIX = "g1-s1-n8-physical-"
CONTRACT_HASH_SCOPE = (
    "entire N8 physical execution contract excluding integrity; UTF-8 JSON "
    "with sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
RUNTIME_KIND = "mf1750-g1-s1-n8-physical-runtime-manifest"
RUNTIME_HASH_SCOPE = CONTRACT_HASH_SCOPE.replace(
    "execution contract", "runtime manifest"
)
MAX_REBIND_REVIEW_BYTES = 4 * 1024 * 1024
MAX_LIVE_EVALUATED_AT_AGE_SECONDS = 300

AUTHORIZATION_PREFIX = "AUTHORIZE_ONE_VISIBLE_RC2G_N8_PHYSICAL__ACTION_"
AUTHORIZATION_SUFFIX = "__NO_RETRY_NO_RECOVERY"
PANEL_CONFIRMATION_PREFIX = "CONFIRM_N8_PHYSICAL_PANEL__SERIAL_"
PROFILE_CONFIRMATION_PREFIX = "CONFIRM_N8_APPROVED_PRODUCTION_PROFILE"

_CONTROL_FIELDS = frozenset(
    {
        "panel_confirmation_sha256",
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
        "usage_cumulative_visible_refresh_count",
        "usage_session_visible_refresh_count",
        "usage_consecutive_visible_refresh_count",
        "usage_last_visible_refresh_completed_at",
        "usage_position_matches_action_ordinal",
        "schedule_gates_satisfied",
    }
)
PHYSICAL_RECORD_EXTRA_KEYS = {
    "claim": _CONTROL_FIELDS,
    "lock": _CONTROL_FIELDS,
    "evidence": _CONTROL_FIELDS | {"authorization_confirmation_sha256"},
    "finalization": _CONTROL_FIELDS | {"authorization_confirmation_sha256"},
}


class N8PhysicalExecutionError(ValueError):
    """Physical N8 identity, schedule, or production evidence failed closed."""


@dataclass(frozen=True)
class N8PhysicalContext:
    contract: Mapping[str, Any]
    binding_review_bytes: bytes
    minimum_interval_seconds: float
    planned_cooldown_seconds: float

    @property
    def physical_campaign(self) -> Mapping[str, Any]:
        return self.contract["p0_campaign"]

    @property
    def physical_anchor_campaign(self) -> Mapping[str, Any]:
        return self.contract["physical_anchor_campaign"]

    @property
    def rebind_manifest(self) -> Mapping[str, Any]:
        return self.contract["physical_rebind"]


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _snapshot(value: Any) -> Any:
    try:
        return json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (CampaignContractError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N8PhysicalExecutionError(
            f"value is not canonical JSON data: {error}"
        ) from error


def _integrity(unsigned: Mapping[str, Any], scope: str) -> dict[str, str]:
    return {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": scope,
    }


def _identity_map(rebind: Mapping[str, Any]) -> dict[str, str]:
    result = {
        item["source_action_identity_sha256"]: item[
            "physical_action_identity_sha256"
        ]
        for item in rebind["action_identity_map"]
    }
    if len(result) != 15:
        raise N8PhysicalExecutionError("physical N8 identity map must contain 15 actions")
    return result


def _rebuilt_sequences(
    source_manifest: Mapping[str, Any], rebind: Mapping[str, Any]
) -> list[dict[str, Any]]:
    mapping = _identity_map(rebind)
    physical_campaign = rebind["physical_campaign"]
    actions = {
        action["action_identity_sha256"]: action
        for action in physical_campaign["actions"]
    }
    sessions = {
        session["session_id"]: session
        for session in physical_campaign["sessions"]
    }
    result: list[dict[str, Any]] = []
    for source_sequence in source_manifest["sequences"]:
        sequence = _snapshot(source_sequence)
        physical_session = sessions.get(sequence["sequence_id"])
        if physical_session is None:
            raise N8PhysicalExecutionError("physical N8 sequence session is missing")
        sequence["session_canonical_sha256"] = physical_session["integrity"][
            "canonical_sha256"
        ]
        for record in sequence["actions"]:
            source_sha = record["action_identity_sha256"]
            physical_sha = mapping[source_sha]
            action = actions.get(physical_sha)
            if action is None:
                raise N8PhysicalExecutionError(
                    "physical N8 sequence action is missing"
                )
            record["action_identity_sha256"] = physical_sha
            record["claim_declaration"] = _snapshot(action["claim"])
            requirement = record["prior_result_requirement"]
            source_prior = requirement["prior_action_identity_sha256"]
            if source_prior is not None:
                requirement["prior_action_identity_sha256"] = mapping[source_prior]
        result.append(sequence)
    return result


def _fixed_actions(
    source_manifest: Mapping[str, Any], rebind: Mapping[str, Any]
) -> list[dict[str, Any]]:
    mapping = _identity_map(rebind)
    rows = []
    for source in frozen._action_rows(source_manifest):
        row = _snapshot(source)
        row["action_identity_sha256"] = mapping[
            source["action_identity_sha256"]
        ]
        prior = source["prior_action_identity_sha256"]
        row["prior_action_identity_sha256"] = (
            None if prior is None else mapping[prior]
        )
        rows.append(row)
    if (
        len(rows) != 15
        or tuple(row["action_key"] for row in rows) != frozen.FIXED_ACTION_KEYS
        or len({row["action_identity_sha256"] for row in rows}) != 15
    ):
        raise N8PhysicalExecutionError(
            "physical N8 fixed action order/membership changed"
        )
    return rows


def _source_binding() -> dict[str, Any]:
    contract = frozen.compile_n8_execution_contract()
    source = frozen._source_manifest()
    return {
        "execution_contract_kind": contract["kind"],
        "execution_contract_id": contract["contract_id"],
        "execution_contract_canonical_sha256": contract["integrity"][
            "canonical_sha256"
        ],
        "execution_contract_file_sha256": frozen.execution_contract_file_sha256(
            contract
        ),
        "source_manifest_kind": source["kind"],
        "source_manifest_canonical_sha256": source["integrity"][
            "canonical_sha256"
        ],
        "source_manifest_file_sha256": _sha256(source),
        "legacy_live_entry_remains_blocked": True,
    }


def _classification() -> dict[str, Any]:
    return {
        "offline_compiled": True,
        "physical_panel_instance_bound": True,
        "all_15_action_identities_rebuilt": True,
        "all_5_sessions_rebuilt": True,
        "all_claim_filenames_rebuilt": True,
        "deep_production_profile_evaluated_at_runtime": False,
        "hardware_execution_authorized": False,
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "automatic_execution": False,
        "automatic_retry": False,
        "automatic_recovery": False,
    }


def _compile_contract(
    physical_anchor_campaign: Mapping[str, Any],
    *,
    measurement_registry: Mapping[str, Any],
    temperature_bin_plan: Mapping[str, Any],
    binding_review_bytes: bytes,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
    namespace: str,
) -> dict[str, Any]:
    source_manifest = frozen._source_manifest()
    source_campaign = source_manifest["p0_campaign"]
    try:
        anchor = validate_campaign_contract(physical_anchor_campaign)
        measurements = campaign.validate_measurement_registry(measurement_registry)
        bins = campaign.validate_temperature_bin_plan(temperature_bin_plan)
        rebind = compile_physical_campaign_rebind(
            source_campaign,
            anchor,
            namespace=namespace,
            binding_review_bytes=binding_review_bytes,
            minimum_interval_seconds=minimum_interval_seconds,
            planned_cooldown_seconds=planned_cooldown_seconds,
        )
        validate_physical_campaign_rebind(
            rebind,
            source_campaign=source_campaign,
            physical_anchor_campaign=anchor,
            binding_review_bytes=binding_review_bytes,
            minimum_interval_seconds=minimum_interval_seconds,
            planned_cooldown_seconds=planned_cooldown_seconds,
        )
    except (
        CampaignContractError,
        PhysicalCampaignRebindError,
        campaign.N8CampaignError,
    ) as error:
        raise N8PhysicalExecutionError(str(error)) from error
    if campaign._measurement_blockers(measurements):
        raise N8PhysicalExecutionError(
            "physical N8 measurement registry is incomplete"
        )
    if campaign._temperature_bin_blockers(bins):
        raise N8PhysicalExecutionError(
            "physical N8 temperature-bin plan is incomplete"
        )
    physical_campaign = rebind["physical_campaign"]
    fixed = _fixed_actions(source_manifest, rebind)
    sequences = _rebuilt_sequences(source_manifest, rebind)
    source_claims = {
        action["claim"]["filename"] for action in source_campaign["actions"]
    }
    physical_claims = {
        action["claim"]["filename"] for action in physical_campaign["actions"]
    }
    if len(physical_claims) != 15 or source_claims.intersection(physical_claims):
        raise N8PhysicalExecutionError("physical N8 claim namespace was not rebuilt")
    schedule = _snapshot(rebind["binding"]["reviewed_schedule"])
    source_power = _snapshot(
        frozen.compile_n8_execution_contract()["power_semantics"]
    )
    source_power.update(
        {
            "physical_panel_instance_bound": True,
            "action_identities_changed": True,
            "legacy_action_claims_reusable": False,
        }
    )
    source_evidence = _snapshot(
        frozen.compile_n8_execution_contract()["evidence_contract"]
    )
    source_evidence.update(
        {
            "standalone_physical_campaign_required": True,
            "deep_production_profile_required_before_claim": True,
            "production_profile_full_campaign_allowlist_required": True,
            "real_firmware_authority_usage_review_bytes_revalidated": True,
            "reviewer_key_never_copied_into_result": True,
        }
    )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": CONTRACT_KIND,
        "contract_id": (
            f"{CONTRACT_ID_PREFIX}{rebind['integrity']['canonical_sha256']}"
        ),
        "namespace": namespace,
        "source_binding": _source_binding(),
        "physical_anchor_campaign": _snapshot(anchor),
        "physical_rebind": _snapshot(rebind),
        "p0_campaign": _snapshot(physical_campaign),
        "p0_campaign_canonical_sha256": physical_campaign["integrity"][
            "canonical_sha256"
        ],
        "p0_campaign_file_sha256": _sha256(physical_campaign),
        "fixed_actions": fixed,
        "sequences": sequences,
        "measurement_registry": _snapshot(measurements),
        "temperature_bin_plan": _snapshot(bins),
        "reviewed_schedule": schedule,
        "binding_review_artifact": {
            "bytes": len(binding_review_bytes),
            "sha256": _sha256(binding_review_bytes),
            "actual_bytes_hashed": True,
        },
        "power_semantics": source_power,
        "evidence_contract": source_evidence,
        "analysis_contract": _snapshot(source_manifest["analysis_contract"]),
        "classification": _classification(),
    }
    return {**unsigned, "integrity": _integrity(unsigned, CONTRACT_HASH_SCOPE)}


def compile_n8_physical_execution_context(
    physical_anchor_campaign: Mapping[str, Any],
    *,
    measurement_registry: Mapping[str, Any],
    temperature_bin_plan: Mapping[str, Any],
    binding_review_bytes: bytes,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
    namespace: str = "n8-physical",
) -> N8PhysicalContext:
    contract = _compile_contract(
        physical_anchor_campaign,
        measurement_registry=measurement_registry,
        temperature_bin_plan=temperature_bin_plan,
        binding_review_bytes=binding_review_bytes,
        minimum_interval_seconds=minimum_interval_seconds,
        planned_cooldown_seconds=planned_cooldown_seconds,
        namespace=namespace,
    )
    return N8PhysicalContext(
        contract=contract,
        binding_review_bytes=bytes(binding_review_bytes),
        minimum_interval_seconds=float(minimum_interval_seconds),
        planned_cooldown_seconds=float(planned_cooldown_seconds),
    )


def validate_n8_physical_execution_context(
    context: N8PhysicalContext,
) -> Mapping[str, Any]:
    if not isinstance(context, N8PhysicalContext):
        raise N8PhysicalExecutionError("physical N8 context type is invalid")
    expected = _compile_contract(
        context.contract["physical_anchor_campaign"],
        measurement_registry=context.contract["measurement_registry"],
        temperature_bin_plan=context.contract["temperature_bin_plan"],
        binding_review_bytes=context.binding_review_bytes,
        minimum_interval_seconds=context.minimum_interval_seconds,
        planned_cooldown_seconds=context.planned_cooldown_seconds,
        namespace=context.contract["namespace"],
    )
    if expected != context.contract:
        raise N8PhysicalExecutionError(
            "physical N8 context differs from deterministic reconstruction"
        )
    return context.contract


def validate_n8_physical_execution_contract(
    contract: Mapping[str, Any], *, context: Optional[N8PhysicalContext] = None
) -> Mapping[str, Any]:
    if not isinstance(contract, Mapping) or contract.get("kind") != CONTRACT_KIND:
        raise N8PhysicalExecutionError("physical N8 contract identity is invalid")
    unsigned = dict(contract)
    integrity = unsigned.pop("integrity", None)
    if integrity != _integrity(unsigned, CONTRACT_HASH_SCOPE):
        raise N8PhysicalExecutionError("physical N8 contract integrity is invalid")
    try:
        physical_campaign = validate_campaign_contract(contract["p0_campaign"])
    except CampaignContractError as error:
        raise N8PhysicalExecutionError(str(error)) from error
    if (
        len(contract.get("fixed_actions", ())) != 15
        or len(contract.get("sequences", ())) != 5
        or physical_campaign["integrity"]["canonical_sha256"]
        != contract.get("p0_campaign_canonical_sha256")
        or _sha256(physical_campaign) != contract.get("p0_campaign_file_sha256")
    ):
        raise N8PhysicalExecutionError("physical N8 contract membership changed")
    if context is not None:
        validate_n8_physical_execution_context(context)
        if contract != context.contract:
            raise N8PhysicalExecutionError(
                "physical N8 contract differs from its deep context"
            )
    return contract


def n8_physical_execution_contract_file_sha256(
    contract: Mapping[str, Any]
) -> str:
    return _sha256(validate_n8_physical_execution_contract(contract))


def load_n8_physical_action_snapshot(
    context: N8PhysicalContext, action_key: str
) -> frozen.N8ActionSnapshot:
    contract = validate_n8_physical_execution_contract(
        context.contract, context=context
    )
    rows = [row for row in contract["fixed_actions"] if row["action_key"] == action_key]
    if len(rows) != 1:
        raise N8PhysicalExecutionError(
            "action key is not one of 15 physical N8 actions"
        )
    row = rows[0]
    matches = [
        action
        for action in contract["p0_campaign"]["actions"]
        if action["action_identity_sha256"] == row["action_identity_sha256"]
    ]
    if len(matches) != 1:
        raise N8PhysicalExecutionError("physical N8 action is not unique")
    action = matches[0]
    source = frozen.load_n8_action_snapshot(action_key)
    identity = action["identity"]
    source_identity = source.action["identity"]
    for field in ("session_id", "cell_id", "action_id", "phase", "frame", "request"):
        if identity[field] != source_identity[field]:
            raise N8PhysicalExecutionError(
                f"physical N8 action changed frozen {field} semantics"
            )
    expected_interval = (
        context.minimum_interval_seconds
        if source_identity["prior"] is not None
        else source_identity["schedule"]["minimum_interval_since_prior_seconds"]
    )
    if identity["schedule"] != {
        **source_identity["schedule"],
        "minimum_interval_since_prior_seconds": expected_interval,
    }:
        raise N8PhysicalExecutionError("physical N8 action schedule changed")
    if _sha256(source.frame) != identity["frame"]["sha256"]:
        raise N8PhysicalExecutionError("physical N8 frame bytes changed")
    return frozen.N8ActionSnapshot(
        key=action_key,
        sequence_id=row["sequence_id"],
        ordinal=row["ordinal"],
        role=row["role"],
        frame_source_id=row["frame_source_id"],
        power_mode=row["power_mode"],
        temperature_bin_id=row["temperature_bin_id"],
        campaign=contract["p0_campaign"],
        action=action,
        frame=source.frame,
        reference_preview=source.reference_preview,
    )


def load_n8_physical_execution_context(
    *,
    contract_file: Path,
    physical_campaign_file: Path,
    binding_review_artifact_file: Path,
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
) -> N8PhysicalContext:
    try:
        contract_artifact = read_local_regular_file(
            contract_file,
            label="N8 physical execution contract",
            maximum_bytes=16 * 1024 * 1024,
        )
        contract = json.loads(contract_artifact.payload.decode("utf-8"))
        physical_campaign = read_standalone_physical_campaign(
            physical_campaign_file
        )
        review = read_local_regular_file(
            binding_review_artifact_file,
            label="N8 physical binding review artifact",
            maximum_bytes=MAX_REBIND_REVIEW_BYTES,
        )
    except (
        ProductionProfileError,
        PhysicalCampaignRebindError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise N8PhysicalExecutionError(str(error)) from error
    if (
        not isinstance(contract, Mapping)
        or contract_artifact.payload != canonical_json_bytes(contract)
        or contract.get("p0_campaign") != physical_campaign
    ):
        raise N8PhysicalExecutionError(
            "stored physical N8 contract/campaign bytes changed"
        )
    context = N8PhysicalContext(
        contract=contract,
        binding_review_bytes=review.payload,
        minimum_interval_seconds=float(minimum_interval_seconds),
        planned_cooldown_seconds=float(planned_cooldown_seconds),
    )
    validate_n8_physical_execution_context(context)
    return context


def load_n8_physical_production_profile(
    context: N8PhysicalContext,
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
    validate_n8_physical_execution_context(context)
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
        raise N8PhysicalExecutionError(
            f"deep N8 production profile failed: {error}"
        ) from error
    if (
        validated.report.get("production_ready") is not True
        or validated.inputs.campaign != context.physical_campaign
        or validated.report.get("campaign_canonical_sha256")
        != context.contract["p0_campaign_canonical_sha256"]
        or validated.report.get("action_allowlist_count") != 15
    ):
        raise N8PhysicalExecutionError(
            "deep profile does not allow the complete physical N8 campaign"
        )
    return validated


def required_n8_physical_authorization_confirmation(
    _contract: Mapping[str, Any], snapshot: frozen.N8ActionSnapshot
) -> str:
    return (
        f"{AUTHORIZATION_PREFIX}"
        f"{snapshot.action['action_identity_sha256'].upper()}"
        f"{AUTHORIZATION_SUFFIX}"
    )


def required_n8_physical_panel_confirmation(
    context: N8PhysicalContext,
) -> str:
    panel = context.physical_campaign["panel"]
    firmware = context.physical_campaign["firmware"]
    binding = context.rebind_manifest["binding"]["canonical_sha256"]
    return (
        f"{PANEL_CONFIRMATION_PREFIX}{panel['serial']}"
        f"__BUILD_TAG_{firmware['build_tag']}__BINDING_{binding.upper()}"
    )


def required_n8_physical_production_profile_confirmation(
    production: ValidatedProductionProfile,
) -> str:
    review = production.review_artifact_file
    if review is None or production.reviewer_key_id is None:
        raise N8PhysicalExecutionError("production review trust chain is incomplete")
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
        raise N8PhysicalExecutionError("profile confirmation contains invalid SHA")
    return (
        f"{PROFILE_CONFIRMATION_PREFIX}"
        f"__PROFILE_CANONICAL_{values[0].upper()}"
        f"__PROFILE_FILE_{values[1].upper()}"
        f"__REVIEW_ARTIFACT_FILE_{values[2].upper()}"
        f"__REVIEWER_KEY_ID_{values[3]}"
        f"__USAGE_FILE_{values[4].upper()}"
        f"__LIMIT_AUTHORITY_FILE_{values[5].upper()}"
    )


def validate_n8_physical_live_evaluation_time(
    evaluated_at: str, live_now: str
) -> float:
    try:
        evaluated = frozen._timestamp(evaluated_at, label="profile evaluated_at")
        current = frozen._timestamp(live_now, label="live wall clock")
    except frozen.N8ExecutionContractError as error:
        raise N8PhysicalExecutionError(str(error)) from error
    age = (current - evaluated).total_seconds()
    if age < 0:
        raise N8PhysicalExecutionError("profile evaluated_at must not be future")
    if age > MAX_LIVE_EVALUATED_AT_AGE_SECONDS:
        raise N8PhysicalExecutionError(
            "profile evaluated_at is too old; revalidate immediately"
        )
    return age


def n8_physical_control_fields(
    context: N8PhysicalContext,
    snapshot: frozen.N8ActionSnapshot,
    production: ValidatedProductionProfile,
    *,
    evaluated_at: str,
    live_now: str,
) -> dict[str, Any]:
    age = validate_n8_physical_live_evaluation_time(evaluated_at, live_now)
    try:
        current = frozen._timestamp(live_now, label="live wall clock")
        last_value = production.profile["usage"][
            "last_visible_refresh_completed_at"
        ]
        last = (
            None
            if last_value is None
            else frozen._timestamp(last_value, label="usage latest visible refresh")
        )
    except frozen.N8ExecutionContractError as error:
        raise N8PhysicalExecutionError(str(error)) from error
    sessions = [
        session
        for session in snapshot.campaign["sessions"]
        if session["session_id"] == snapshot.sequence_id
    ]
    if len(sessions) != 1:
        raise N8PhysicalExecutionError("physical N8 action session is not unique")
    usage = production.profile["usage"]
    limits = production.profile["limits"]
    expected_position = snapshot.ordinal - 1
    if (
        usage["session_visible_refresh_count"] != expected_position
        or usage["consecutive_visible_refresh_count"] != expected_position
    ):
        raise N8PhysicalExecutionError(
            "profile usage position differs from the N8 action ordinal"
        )
    materialized_interval = float(
        snapshot.action["identity"]["schedule"][
            "minimum_interval_since_prior_seconds"
        ]
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
        raise N8PhysicalExecutionError(
            "effective physical minimum refresh interval has not elapsed"
        )
    if cooldown_applies and elapsed is not None and elapsed < effective_cooldown:
        raise N8PhysicalExecutionError(
            "effective physical inter-session cooldown has not elapsed"
        )
    action_token = required_n8_physical_authorization_confirmation(
        context.contract, snapshot
    )
    panel_token = required_n8_physical_panel_confirmation(context)
    profile_token = required_n8_physical_production_profile_confirmation(
        production
    )
    return {
        "authorization_confirmation_sha256": _sha256(
            action_token.encode("utf-8")
        ),
        "panel_confirmation_sha256": _sha256(panel_token.encode("utf-8")),
        "profile_confirmation_sha256": _sha256(profile_token.encode("utf-8")),
        "profile_evaluated_at": evaluated_at,
        "live_evaluation_age_seconds": age,
        "maximum_live_evaluation_age_seconds": (
            MAX_LIVE_EVALUATED_AT_AGE_SECONDS
        ),
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
        "usage_cumulative_visible_refresh_count": usage[
            "cumulative_visible_refresh_count"
        ],
        "usage_session_visible_refresh_count": usage[
            "session_visible_refresh_count"
        ],
        "usage_consecutive_visible_refresh_count": usage[
            "consecutive_visible_refresh_count"
        ],
        "usage_last_visible_refresh_completed_at": last_value,
        "usage_position_matches_action_ordinal": True,
        "schedule_gates_satisfied": True,
    }


def _authority_identity(authority: Mapping[str, Any]) -> dict[str, Any]:
    if "policy_id" in authority:
        return {"issuer": authority["issuer"], "authority_id": authority["policy_id"]}
    return {
        "issuer": authority["supplier_id"],
        "authority_id": authority["document_id"],
    }


def _production_static_lineage(
    production: ValidatedProductionProfile,
) -> dict[str, Any]:
    review = production.review_artifact_file
    if review is None:
        raise N8PhysicalExecutionError("production review artifact is missing")
    return {
        "panel": _snapshot(production.profile["panel"]),
        "firmware": _snapshot(production.profile["firmware"]),
        "firmware_binary_sha256": production.inputs.firmware_binary.sha256,
        "limit_authority_kind": production.report["limit_authority_kind"],
        "limit_authority_classification": production.report[
            "limit_authority_classification"
        ],
        "limit_authority_file_sha256": (
            production.inputs.limit_authority_file.sha256
        ),
        "limit_authority_identity": _authority_identity(
            production.inputs.limit_authority
        ),
        "profile_id": production.profile["profile_id"],
        "profile_version": production.profile["profile_version"],
        "reviewer_id": production.profile["review"]["reviewer_id"],
        "reviewer_key_id": production.reviewer_key_id,
    }


def _production_semantic_lineage(
    production: ValidatedProductionProfile,
) -> dict[str, Any]:
    """Stable campaign lineage; per-action authority bytes remain deep-checked.

    A fresh usage snapshot must be reviewed before that profile's valid_from,
    so a supervised campaign legitimately materializes a new authority/review
    artifact for every action.  Their file SHAs are retained in each runtime
    manifest; semantic continuity is the common authority identity, limits,
    panel/build, profile version, and trusted reviewer key.
    """

    result = _production_static_lineage(production)
    result.pop("limit_authority_file_sha256")
    result["limits"] = _snapshot(production.profile["limits"])
    return result


def compile_n8_physical_runtime_manifest(
    context: N8PhysicalContext,
    production: ValidatedProductionProfile,
) -> dict[str, Any]:
    validate_n8_physical_execution_context(context)
    if production.inputs.campaign != context.physical_campaign:
        raise N8PhysicalExecutionError(
            "runtime production profile belongs to another physical campaign"
        )
    review = production.review_artifact_file
    if review is None or production.reviewer_key_id is None:
        raise N8PhysicalExecutionError("runtime production trust chain is incomplete")
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": RUNTIME_KIND,
        "physical_execution_contract_canonical_sha256": context.contract[
            "integrity"
        ]["canonical_sha256"],
        "physical_execution_contract_file_sha256": (
            n8_physical_execution_contract_file_sha256(context.contract)
        ),
        "p0_campaign_canonical_sha256": context.contract[
            "p0_campaign_canonical_sha256"
        ],
        "p0_campaign_file_sha256": context.contract[
            "p0_campaign_file_sha256"
        ],
        "panel": _snapshot(context.physical_campaign["panel"]),
        "firmware": _snapshot(context.physical_campaign["firmware"]),
        "measurement_registry": _snapshot(
            context.contract["measurement_registry"]
        ),
        "temperature_bin_plan": _snapshot(
            context.contract["temperature_bin_plan"]
        ),
        "reviewed_schedule": _snapshot(context.contract["reviewed_schedule"]),
        "limit_profile": _snapshot(production.profile),
        "production_lineage": {
            **_production_static_lineage(production),
            "profile_canonical_sha256": production.profile["integrity"][
                "canonical_sha256"
            ],
            "profile_file_sha256": production.profile_file.sha256,
            "usage_evidence_file_sha256": (
                production.inputs.usage_evidence_file.sha256
            ),
            "review_artifact_file_sha256": review.sha256,
        },
        "classification": {
            "physical_runtime_binding": True,
            "deep_production_profile_validated": True,
            "hardware_execution_authorized": False,
            "claim_created": False,
            "network_io_performed": False,
            "device_io_performed": False,
            "qualification_state": "NOT_QUALIFIED",
        },
    }
    return {**unsigned, "integrity": _integrity(unsigned, RUNTIME_HASH_SCOPE)}


def validate_n8_physical_runtime_manifest(
    context: N8PhysicalContext,
    value: Mapping[str, Any],
    production: ValidatedProductionProfile,
) -> Mapping[str, Any]:
    expected = compile_n8_physical_runtime_manifest(context, production)
    if value != expected:
        raise N8PhysicalExecutionError("physical N8 runtime manifest changed")
    return value


def _production_key(
    production: ValidatedProductionProfile,
) -> tuple[str, str]:
    return (
        str(production.profile["integrity"]["canonical_sha256"]),
        production.profile_file.sha256,
    )


def _bundle_chain(bundle: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    result = []
    current: Optional[Mapping[str, Any]] = bundle
    while current is not None:
        result.append(current)
        prior = current.get("prior_bundle")
        if prior is not None and not isinstance(prior, Mapping):
            raise N8PhysicalExecutionError("physical N8 prior bundle is invalid")
        current = prior
    result.reverse()
    return result


def _validate_usage_chain(
    context: N8PhysicalContext,
    bundle: Mapping[str, Any],
    profiles: Mapping[tuple[str, str], ValidatedProductionProfile],
) -> None:
    chain = _bundle_chain(bundle)
    lineage: Optional[dict[str, Any]] = None
    previous_usage: Optional[Mapping[str, Any]] = None
    previous_result: Optional[Mapping[str, Any]] = None
    for expected_ordinal, item in enumerate(chain, start=1):
        key = (
            str(item["profile"]["integrity"]["canonical_sha256"]),
            str(item["profile_file_sha256"]),
        )
        production = profiles.get(key)
        if production is None:
            raise N8PhysicalExecutionError(
                "physical N8 bundle chain lacks a deep production profile"
            )
        snapshot = load_n8_physical_action_snapshot(
            context, str(item["evidence"]["action_key"])
        )
        usage = production.profile["usage"]
        if (
            snapshot.ordinal != expected_ordinal
            or usage["session_visible_refresh_count"] != expected_ordinal - 1
            or usage["consecutive_visible_refresh_count"] != expected_ordinal - 1
        ):
            raise N8PhysicalExecutionError(
                "physical N8 profile usage/action ordinal chain changed"
            )
        current_lineage = _production_semantic_lineage(production)
        if lineage is None:
            lineage = current_lineage
        elif current_lineage != lineage:
            raise N8PhysicalExecutionError(
                "physical N8 production lineage changed within a sequence"
            )
        if previous_usage is not None and previous_result is not None:
            if (
                usage["cumulative_visible_refresh_count"]
                != previous_usage["cumulative_visible_refresh_count"] + 1
                or usage["last_visible_refresh_completed_at"]
                != previous_result["completed_at"]
            ):
                raise N8PhysicalExecutionError(
                    "physical N8 profile usage does not name the exact prior action"
                )
        previous_usage = usage
        previous_result = item["result"]


def validate_n8_physical_control_records(
    context: N8PhysicalContext,
    snapshot: frozen.N8ActionSnapshot,
    production: ValidatedProductionProfile,
    records: Mapping[str, Mapping[str, Any]],
) -> None:
    claim = records.get("claim")
    lock = records.get("lock")
    evidence = records.get("evidence")
    if not all(isinstance(value, Mapping) for value in (claim, lock, evidence)):
        raise N8PhysicalExecutionError("physical N8 control records are incomplete")
    assert claim is not None and lock is not None and evidence is not None
    expected = n8_physical_control_fields(
        context,
        snapshot,
        production,
        evaluated_at=str(evidence.get("profile_evaluated_at")),
        live_now=str(evidence.get("recorded_at")),
    )
    common = {key: expected[key] for key in _CONTROL_FIELDS}
    for label, record in (("claim", claim), ("lock", lock), ("evidence", evidence)):
        if {key: record.get(key) for key in _CONTROL_FIELDS} != common:
            raise N8PhysicalExecutionError(
                f"physical N8 {label} token/freshness/schedule binding changed"
            )
    for label in ("evidence", "finalization"):
        record = records.get(label)
        if record is not None and record.get(
            "authorization_confirmation_sha256"
        ) != expected["authorization_confirmation_sha256"]:
            raise N8PhysicalExecutionError(
                f"physical N8 {label} action authorization binding changed"
            )
    finalization = records.get("finalization")
    if finalization is not None and {
        key: finalization.get(key) for key in _CONTROL_FIELDS
    } != common:
        raise N8PhysicalExecutionError(
            "physical N8 finalization control binding changed"
        )
    if production.report.get("evaluated_at") != expected["profile_evaluated_at"]:
        raise N8PhysicalExecutionError(
            "deep N8 production evaluation timestamp changed"
        )


def validate_n8_physical_finalized_action_bundle(
    context: N8PhysicalContext,
    bundle: Mapping[str, Any],
    *,
    production_profile: ValidatedProductionProfile,
    prior_production_profiles: Sequence[ValidatedProductionProfile] = (),
    expected_action_key: Optional[str] = None,
) -> dict[str, Any]:
    """Deeply replay one physical N8 bundle and every embedded prior."""

    contract = validate_n8_physical_execution_contract(
        context.contract, context=context
    )
    all_profiles = (*prior_production_profiles, production_profile)
    profiles = {_production_key(item): item for item in all_profiles}
    if len(profiles) != len(all_profiles):
        raise N8PhysicalExecutionError("duplicate deep production profile replay")
    chain = _bundle_chain(bundle)
    if len(chain) != len(all_profiles):
        raise N8PhysicalExecutionError(
            "physical N8 embedded chain/profile count differs"
        )
    for item in all_profiles:
        if (
            item.report.get("production_ready") is not True
            or item.inputs.campaign != context.physical_campaign
        ):
            raise N8PhysicalExecutionError(
                "physical N8 stored profile is not deeply production-ready"
            )
    current_key = (
        str(bundle.get("profile", {}).get("integrity", {}).get("canonical_sha256")),
        str(bundle.get("profile_file_sha256")),
    )
    if current_key != _production_key(production_profile):
        raise N8PhysicalExecutionError(
            "current physical N8 profile differs from deep production inputs"
        )

    def contract_validator(value: Mapping[str, Any]) -> Mapping[str, Any]:
        return validate_n8_physical_execution_contract(value, context=context)

    def snapshot_loader(
        _contract: Mapping[str, Any], action_key: str
    ) -> frozen.N8ActionSnapshot:
        return load_n8_physical_action_snapshot(context, action_key)

    def manifest_validator(
        value: Mapping[str, Any], profile: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        key = (
            str(profile.get("integrity", {}).get("canonical_sha256")),
            _sha256(profile),
        )
        selected = profiles.get(key)
        if selected is None or selected.profile != profile:
            raise N8PhysicalExecutionError(
                "physical runtime uses an unvalidated production profile"
            )
        return validate_n8_physical_runtime_manifest(context, value, selected)

    def prior_key_resolver(
        _contract: Mapping[str, Any], snapshot: frozen.N8ActionSnapshot
    ) -> str:
        prior_sha = snapshot.action["identity"]["prior"][
            "action_identity_sha256"
        ]
        matches = [
            row["action_key"]
            for row in context.contract["fixed_actions"]
            if row["action_identity_sha256"] == prior_sha
        ]
        if len(matches) != 1:
            raise N8PhysicalExecutionError("physical N8 prior key is not unique")
        return str(matches[0])

    def extension_validator(
        _contract: Mapping[str, Any],
        snapshot: frozen.N8ActionSnapshot,
        records: Mapping[str, Mapping[str, Any]],
    ) -> None:
        claim = records["claim"]
        selected = profiles.get(
            (
                str(claim.get("profile_canonical_sha256")),
                str(claim.get("profile_file_sha256")),
            )
        )
        if selected is None:
            raise N8PhysicalExecutionError(
                "physical controls use an unvalidated production profile"
            )
        validate_n8_physical_control_records(
            context, snapshot, selected, records
        )

    try:
        result = frozen.validate_n8_finalized_action_bundle(
            contract,
            bundle,
            expected_action_key=expected_action_key,
            _contract_validator=contract_validator,
            _snapshot_loader=snapshot_loader,
            _contract_file_sha256=n8_physical_execution_contract_file_sha256,
            _authorization_confirmation=(
                required_n8_physical_authorization_confirmation
            ),
            _manifest_validator=manifest_validator,
            _protocol_contract_builder=frozen.build_n8_protocol_contract,
            _prior_action_key_resolver=prior_key_resolver,
            _runner_kind="mf1750-g1-s1-rc2g-n8-physical-action-runner",
            _record_extra_keys=PHYSICAL_RECORD_EXTRA_KEYS,
            _record_extension_validator=extension_validator,
        )
    except (frozen.N8ExecutionContractError, N8PhysicalExecutionError) as error:
        raise N8PhysicalExecutionError(
            f"physical N8 finalized bundle is invalid: {error}"
        ) from error
    _validate_usage_chain(context, bundle, profiles)
    return result


__all__ = [
    "AUTHORIZATION_PREFIX",
    "AUTHORIZATION_SUFFIX",
    "CONTRACT_KIND",
    "MAX_LIVE_EVALUATED_AT_AGE_SECONDS",
    "N8PhysicalContext",
    "N8PhysicalExecutionError",
    "PHYSICAL_RECORD_EXTRA_KEYS",
    "RUNTIME_KIND",
    "compile_n8_physical_execution_context",
    "compile_n8_physical_runtime_manifest",
    "load_n8_physical_action_snapshot",
    "load_n8_physical_execution_context",
    "load_n8_physical_production_profile",
    "n8_physical_control_fields",
    "n8_physical_execution_contract_file_sha256",
    "required_n8_physical_authorization_confirmation",
    "required_n8_physical_panel_confirmation",
    "required_n8_physical_production_profile_confirmation",
    "validate_n8_physical_control_records",
    "validate_n8_physical_execution_context",
    "validate_n8_physical_execution_contract",
    "validate_n8_physical_finalized_action_bundle",
    "validate_n8_physical_live_evaluation_time",
    "validate_n8_physical_runtime_manifest",
]
