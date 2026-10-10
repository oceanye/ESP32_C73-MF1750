#!/usr/bin/env python3
"""Describe, run, finalize, and replay one physical-bound N8 action.

Every production action authenticates the physical contract, firmware bytes,
limit authority, usage evidence, approval artifact, and trusted reviewer key
before a permanent global claim can be created.  A claimed action permits one
POST only and has no retry, recovery, reset, firmware upload, GPIO control, or
power-control path.  The legacy public N8 live entry remains blocked.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
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

from host.visible_refresh_campaign import (  # noqa: E402
    CLAIM_REGISTRY_ID,
    CampaignContractError,
    ResultState,
    ValidatedProductionProfile,
    build_result_record,
    canonical_json_bytes,
    describe_action_offline,
)
from tools import g1_s1_n8_execution_contract as frozen  # noqa: E402
from tools import g1_s1_n8_physical_execution as physical  # noqa: E402
from tools import g1_s1_rc2g_n8_once as legacy  # noqa: E402


SCHEMA_VERSION = 1
RUNNER_KIND = "mf1750-g1-s1-rc2g-n8-physical-action-runner"
DESCRIPTION_KIND = "mf1750-g1-s1-rc2g-n8-physical-action-description"

LOCK_FILENAME = frozen.LOCK_FILENAME
MANIFEST_FILENAME = frozen.MANIFEST_FILENAME
PROFILE_FILENAME = frozen.PROFILE_FILENAME
EVIDENCE_FILENAME = frozen.EVIDENCE_FILENAME
OBSERVATION_FILENAME = frozen.OBSERVATION_FILENAME
FINALIZATION_FILENAME = frozen.FINALIZATION_FILENAME
P0_RESULT_FILENAME = frozen.P0_RESULT_FILENAME
BUNDLE_FILENAME = frozen.BUNDLE_FILENAME
CAMERA_CAPTURE_FILENAME = frozen.CAMERA_CAPTURE_FILENAME
PRIOR_BUNDLE_FILENAME = legacy.PRIOR_BUNDLE_FILENAME

PHYSICAL_CONTRACT_FILENAME = "N8-PHYSICAL-EXECUTION-CONTRACT.json"
PHYSICAL_CAMPAIGN_FILENAME = "PHYSICAL-CAMPAIGN.json"
BINDING_REVIEW_FILENAME = "PHYSICAL-BINDING-REVIEW.bin"
FIRMWARE_BINARY_FILENAME = "FIRMWARE.bin"
LIMIT_AUTHORITY_FILENAME = "LIMIT-AUTHORITY.json"
USAGE_EVIDENCE_FILENAME = "USAGE-EVIDENCE.json"
PROFILE_REVIEW_FILENAME = "PROFILE-REVIEW.json"
PRODUCTION_VALIDATION_FILENAME = "PRODUCTION-PROFILE-VALIDATION.json"
CLAIM_COMMIT_UNCERTAIN_FILENAME = "CLAIM-COMMIT-UNCERTAIN.json"
CLAIM_COMMIT_UNCERTAIN_KIND = (
    "mf1750-g1-s1-rc2g-n8-physical-claim-commit-uncertain"
)

http_request = legacy.http_request


class N8PhysicalActionError(RuntimeError):
    """A physical N8 action was rejected before its permanent claim."""


class N8PhysicalActionUnknown(N8PhysicalActionError):
    """A physical N8 claim exists; retry and recovery are forbidden."""


@dataclass(frozen=True)
class N8PhysicalPlanFiles:
    contract: Path
    physical_campaign: Path
    binding_review_artifact: Path
    minimum_interval_seconds: float
    planned_cooldown_seconds: float


@dataclass(frozen=True)
class N8ProductionFiles:
    profile: Path
    firmware_binary: Path
    limit_authority: Path
    usage_evidence: Path
    review_artifact: Path
    reviewer_key: Path


@dataclass(frozen=True)
class _Claim:
    record: Mapping[str, Any]
    file_sha256: str

    def reference(self) -> dict[str, Any]:
        return {
            "registry_id": CLAIM_REGISTRY_ID,
            "filename": f"{self.record['action_identity_sha256']}.json",
            "file_sha256": self.file_sha256,
            "attempt_id": self.record["attempt_id"],
            "action_identity_sha256": self.record[
                "action_identity_sha256"
            ],
            "state": self.record["state"],
        }


@dataclass(frozen=True)
class _StoredChain:
    context: physical.N8PhysicalContext
    production_chain: tuple[ValidatedProductionProfile, ...]
    bundle: Mapping[str, Any]
    payload: bytes
    validated: Mapping[str, Any]

    @property
    def production(self) -> ValidatedProductionProfile:
        return self.production_chain[-1]

    @property
    def result(self) -> Mapping[str, Any]:
        return self.bundle["result"]

    @property
    def result_sha256(self) -> str:
        return str(self.validated["result_file_sha256"])

    @property
    def finalization_sha256(self) -> str:
        return str(self.validated["finalization_file_sha256"])


@dataclass(frozen=True)
class _StoredCurrent:
    context: physical.N8PhysicalContext
    production: ValidatedProductionProfile
    bundle: Mapping[str, Any]
    payload: bytes
    snapshot: frozen.N8ActionSnapshot


def _canonical(value: Any) -> bytes:
    try:
        return canonical_json_bytes(value)
    except CampaignContractError as error:
        raise N8PhysicalActionError(f"canonical JSON failed: {error}") from error


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else _canonical(value)
    return frozen._sha256(payload)


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _strict_json_file(
    path: Path, *, label: str
) -> tuple[Mapping[str, Any], bytes]:
    try:
        return legacy._strict_json_file(path, label=label)
    except legacy.N8FixedActionError as error:
        raise N8PhysicalActionError(str(error)) from error


def _safe_regular_file(path: Path, *, label: str) -> Path:
    try:
        return legacy._fixed._safe_regular_file(path, label=label)
    except legacy._fixed.N2PFixedActionError as error:
        raise N8PhysicalActionError(str(error)) from error


def _prepare_destination(path: Path) -> Path:
    try:
        return legacy._prepare_destination(path)
    except legacy.N8FixedActionError as error:
        raise N8PhysicalActionError(str(error)) from error


def _atomic(
    path: Path, payload: bytes, *, unknown_after_commit: bool = False
) -> None:
    try:
        legacy._atomic(path, payload, unknown_after_commit=unknown_after_commit)
    except legacy.N8FixedActionUnknown as error:
        raise N8PhysicalActionUnknown(str(error)) from error
    except legacy.N8FixedActionError as error:
        if unknown_after_commit:
            raise N8PhysicalActionUnknown(str(error)) from error
        raise N8PhysicalActionError(str(error)) from error


def _write_new(directory: Path, filename: str, value: Mapping[str, Any]) -> str:
    payload = _canonical(value)
    _atomic(directory / filename, payload)
    return _sha256(payload)


def _load_context(files: N8PhysicalPlanFiles) -> physical.N8PhysicalContext:
    try:
        return physical.load_n8_physical_execution_context(
            contract_file=files.contract,
            physical_campaign_file=files.physical_campaign,
            binding_review_artifact_file=files.binding_review_artifact,
            minimum_interval_seconds=files.minimum_interval_seconds,
            planned_cooldown_seconds=files.planned_cooldown_seconds,
        )
    except physical.N8PhysicalExecutionError as error:
        raise N8PhysicalActionError(str(error)) from error


def _load_production(
    context: physical.N8PhysicalContext,
    plan: N8PhysicalPlanFiles,
    files: N8ProductionFiles,
    *,
    evaluated_at: str,
) -> ValidatedProductionProfile:
    try:
        return physical.load_n8_physical_production_profile(
            context,
            profile_file=files.profile,
            campaign_file=plan.physical_campaign,
            firmware_binary_file=files.firmware_binary,
            limit_authority_file=files.limit_authority,
            usage_evidence_file=files.usage_evidence,
            review_artifact_file=files.review_artifact,
            reviewer_key_file=files.reviewer_key,
            evaluated_at=evaluated_at,
        )
    except physical.N8PhysicalExecutionError as error:
        raise N8PhysicalActionError(str(error)) from error


def required_authorization_confirmation(
    context: physical.N8PhysicalContext, action_key: str
) -> str:
    snapshot = physical.load_n8_physical_action_snapshot(context, action_key)
    return physical.required_n8_physical_authorization_confirmation(
        context.contract, snapshot
    )


def required_panel_confirmation(context: physical.N8PhysicalContext) -> str:
    return physical.required_n8_physical_panel_confirmation(context)


def required_production_profile_confirmation(
    production: ValidatedProductionProfile,
) -> str:
    return physical.required_n8_physical_production_profile_confirmation(
        production
    )


def authorization_confirmation_sha256(
    context: physical.N8PhysicalContext, action_key: str
) -> str:
    return _sha256(
        required_authorization_confirmation(context, action_key).encode("ascii")
    )


def _stored_plan_files(directory: Path) -> N8PhysicalPlanFiles:
    contract, _payload = _strict_json_file(
        directory / PHYSICAL_CONTRACT_FILENAME,
        label="stored N8 physical execution contract",
    )
    schedule = contract.get("reviewed_schedule", {})
    return N8PhysicalPlanFiles(
        contract=directory / PHYSICAL_CONTRACT_FILENAME,
        physical_campaign=directory / PHYSICAL_CAMPAIGN_FILENAME,
        binding_review_artifact=directory / BINDING_REVIEW_FILENAME,
        minimum_interval_seconds=schedule.get("minimum_interval_seconds"),
        planned_cooldown_seconds=schedule.get("planned_cooldown_seconds"),
    )


def _stored_production_files(
    directory: Path, reviewer_key_file: Path
) -> N8ProductionFiles:
    return N8ProductionFiles(
        profile=directory / PROFILE_FILENAME,
        firmware_binary=directory / FIRMWARE_BINARY_FILENAME,
        limit_authority=directory / LIMIT_AUTHORITY_FILENAME,
        usage_evidence=directory / USAGE_EVIDENCE_FILENAME,
        review_artifact=directory / PROFILE_REVIEW_FILENAME,
        reviewer_key=reviewer_key_file,
    )


def _load_stored_current(
    result_file: Path, *, reviewer_key_file: Path
) -> _StoredCurrent:
    resolved = _safe_regular_file(result_file, label="physical N8 P0 result")
    if resolved.name != P0_RESULT_FILENAME:
        raise N8PhysicalActionError(
            f"physical N8 result filename must be {P0_RESULT_FILENAME}"
        )
    directory = resolved.parent
    context = _load_context(_stored_plan_files(directory))
    bundle, payload = _strict_json_file(
        directory / BUNDLE_FILENAME, label="stored physical N8 finalized bundle"
    )
    result, result_payload = _strict_json_file(
        resolved, label="stored physical N8 P0 result"
    )
    if (
        bundle.get("result") != result
        or bundle.get("result_file_sha256") != _sha256(result_payload)
    ):
        raise N8PhysicalActionError("stored physical N8 result/bundle changed")
    evidence = bundle.get("evidence")
    if not isinstance(evidence, Mapping):
        raise N8PhysicalActionError("stored physical N8 evidence is missing")
    evaluated_at = evidence.get("profile_evaluated_at")
    if not isinstance(evaluated_at, str) or not evaluated_at:
        raise N8PhysicalActionError("stored N8 profile evaluation time is invalid")
    plan = _stored_plan_files(directory)
    production = _load_production(
        context,
        plan,
        _stored_production_files(directory, reviewer_key_file),
        evaluated_at=evaluated_at,
    )
    report, report_payload = _strict_json_file(
        directory / PRODUCTION_VALIDATION_FILENAME,
        label="stored N8 deep production validation",
    )
    if report != production.report or _sha256(report_payload) != _sha256(
        production.report
    ):
        raise N8PhysicalActionError("stored N8 production validation changed")
    snapshot = physical.load_n8_physical_action_snapshot(
        context, str(evidence.get("action_key"))
    )
    if bundle.get("profile") != production.profile:
        raise N8PhysicalActionError("stored N8 bundle/profile changed")
    return _StoredCurrent(context, production, bundle, payload, snapshot)


def _load_stored_chain(
    result_file: Path,
    *,
    reviewer_key_file: Path,
    prior_result_files: Sequence[Path] = (),
) -> _StoredChain:
    current = _load_stored_current(
        result_file, reviewer_key_file=reviewer_key_file
    )
    if len(prior_result_files) != current.snapshot.ordinal - 1:
        raise N8PhysicalActionError(
            "stored N8 replay requires every earlier result in this sequence"
        )
    production_chain: list[ValidatedProductionProfile] = []
    previous_bundle: Optional[Mapping[str, Any]] = None
    previous_bundle_sha: Optional[str] = None
    for ordinal, path in enumerate(prior_result_files, start=1):
        prior = _load_stored_current(path, reviewer_key_file=reviewer_key_file)
        if (
            prior.context.contract != current.context.contract
            or prior.snapshot.sequence_id != current.snapshot.sequence_id
            or prior.snapshot.ordinal != ordinal
        ):
            raise N8PhysicalActionError(
                "stored N8 prior result is cross-contract, cross-sequence, or reordered"
            )
        try:
            validated = physical.validate_n8_physical_finalized_action_bundle(
                current.context,
                prior.bundle,
                production_profile=prior.production,
                prior_production_profiles=tuple(production_chain),
                expected_action_key=prior.snapshot.key,
            )
        except physical.N8PhysicalExecutionError as error:
            raise N8PhysicalActionError(str(error)) from error
        if validated["state"] != ResultState.PASS.value:
            raise N8PhysicalActionError("stored N8 prior action is not PASS")
        if ordinal > 1 and prior.bundle.get(
            "prior_bundle_file_sha256"
        ) != previous_bundle_sha:
            raise N8PhysicalActionError("stored N8 prior bundle chain is broken")
        production_chain.append(prior.production)
        previous_bundle = prior.bundle
        previous_bundle_sha = _sha256(prior.payload)
    if current.snapshot.ordinal == 1:
        if current.bundle.get("prior_bundle") is not None:
            raise N8PhysicalActionError("N8 root unexpectedly embeds a prior")
    elif (
        previous_bundle is None
        or current.bundle.get("prior_bundle") != previous_bundle
        or current.bundle.get("prior_bundle_file_sha256") != previous_bundle_sha
    ):
        raise N8PhysicalActionError("current N8 action embeds another prior chain")
    try:
        validated = physical.validate_n8_physical_finalized_action_bundle(
            current.context,
            current.bundle,
            production_profile=current.production,
            prior_production_profiles=tuple(production_chain),
            expected_action_key=current.snapshot.key,
        )
    except physical.N8PhysicalExecutionError as error:
        raise N8PhysicalActionError(str(error)) from error
    production_chain.append(current.production)
    return _StoredChain(
        current.context,
        tuple(production_chain),
        current.bundle,
        current.payload,
        validated,
    )


def load_n8_physical_finalized_action_chain(
    result_file: Path,
    *,
    reviewer_key_file: Path,
    prior_result_files: Sequence[Path] = (),
) -> _StoredChain:
    """Deeply replay a physical action and all prior production artifacts."""

    return _load_stored_chain(
        result_file,
        reviewer_key_file=reviewer_key_file,
        prior_result_files=prior_result_files,
    )


def load_n8_physical_finalized_action_bundle(
    result_file: Path,
    *,
    reviewer_key_file: Path,
    prior_result_files: Sequence[Path] = (),
) -> dict[str, Any]:
    return dict(
        _load_stored_chain(
            result_file,
            reviewer_key_file=reviewer_key_file,
            prior_result_files=prior_result_files,
        ).validated
    )


def _prepare(
    action_key: str,
    *,
    plan_files: N8PhysicalPlanFiles,
    production_files: Optional[N8ProductionFiles],
    evaluated_at: Optional[str],
    prior_result_files: Sequence[Path],
) -> tuple[
    dict[str, Any],
    physical.N8PhysicalContext,
    frozen.N8ActionSnapshot,
    Optional[ValidatedProductionProfile],
    Optional[_StoredChain],
]:
    context = _load_context(plan_files)
    snapshot = physical.load_n8_physical_action_snapshot(context, action_key)
    blockers: list[str] = []
    production: Optional[ValidatedProductionProfile] = None
    prior: Optional[_StoredChain] = None
    p0_description: Optional[Mapping[str, Any]] = None
    if production_files is None:
        blockers.append("deep_production_profile_inputs_missing")
    if evaluated_at is None:
        blockers.append("explicit_evaluated_at_missing")
    if len(prior_result_files) != snapshot.ordinal - 1:
        blockers.append("all_exact_prior_results_in_sequence_missing")
    if prior_result_files:
        if production_files is None:
            blockers.append("prior_trusted_reviewer_key_missing")
        else:
            prior = _load_stored_chain(
                prior_result_files[-1],
                reviewer_key_file=production_files.reviewer_key,
                prior_result_files=prior_result_files[:-1],
            )
            expected_prior = snapshot.action["identity"]["prior"][
                "action_identity_sha256"
            ]
            if (
                prior.context.contract != context.contract
                or prior.validated["action_identity_sha256"] != expected_prior
                or prior.validated["state"] != ResultState.PASS.value
            ):
                raise N8PhysicalActionError(
                    "physical N8 prior is cross-contract, reordered, or not PASS"
                )
    if production_files is not None and evaluated_at is not None:
        production = _load_production(
            context,
            plan_files,
            production_files,
            evaluated_at=evaluated_at,
        )
        if snapshot.ordinal > 1:
            if prior is None:
                blockers.append("exact_prior_deep_chain_missing")
            else:
                current_usage = production.profile["usage"]
                prior_usage = prior.production.profile["usage"]
                if (
                    current_usage["cumulative_visible_refresh_count"]
                    != prior_usage["cumulative_visible_refresh_count"] + 1
                    or current_usage["session_visible_refresh_count"]
                    != snapshot.ordinal - 1
                    or current_usage["consecutive_visible_refresh_count"]
                    != snapshot.ordinal - 1
                    or current_usage["last_visible_refresh_completed_at"]
                    != prior.result["completed_at"]
                ):
                    raise N8PhysicalActionError(
                        "current usage evidence does not name the exact prior action"
                    )
        try:
            p0_description = describe_action_offline(
                context.physical_campaign,
                action_identity_sha256=snapshot.action[
                    "action_identity_sha256"
                ],
                limit_profile=production.profile,
                evaluated_at=evaluated_at,
                prior_result=prior.result if prior else None,
                prior_result_sha256=prior.result_sha256 if prior else None,
            )
        except CampaignContractError as error:
            raise N8PhysicalActionError(
                f"physical N8 P0 description failed: {error}"
            ) from error
        blockers.extend(
            blocker
            for blocker in p0_description["blockers"]
            if blocker
            != "current_runtime_gates_and_exact_authorization_not_evaluated"
        )
    blockers = list(dict.fromkeys(blockers))
    description = {
        "schema_version": SCHEMA_VERSION,
        "kind": DESCRIPTION_KIND,
        "mode": "describe-only",
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action[
            "action_identity_sha256"
        ],
        "sequence_id": snapshot.sequence_id,
        "ordinal": snapshot.ordinal,
        "role": snapshot.role,
        "frame_source_id": snapshot.frame_source_id,
        "frame": dict(snapshot.action["identity"]["frame"]),
        "reference_preview": dict(snapshot.reference_preview),
        "power_mode": snapshot.power_mode,
        "temperature_bin_id": snapshot.temperature_bin_id,
        "dynamic_first_action_baseline": (
            snapshot.ordinal == 1
            and snapshot.power_mode == "supervised_continuous"
        ),
        "physical_execution_contract_canonical_sha256": context.contract[
            "integrity"
        ]["canonical_sha256"],
        "physical_execution_contract_file_sha256": (
            physical.n8_physical_execution_contract_file_sha256(
                context.contract
            )
        ),
        "physical_campaign_canonical_sha256": context.contract[
            "p0_campaign_canonical_sha256"
        ],
        "profile_validation": (
            None if production is None else dict(production.report)
        ),
        "prior_bundle_file_sha256": _sha256(prior.payload) if prior else None,
        "prior_finalization_file_sha256": (
            prior.finalization_sha256 if prior else None
        ),
        "prior_result_file_sha256": prior.result_sha256 if prior else None,
        "p0_description": dict(p0_description) if p0_description else None,
        "contract_ready": bool(
            p0_description and p0_description["contract_ready"] and not blockers
        ),
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "required_authorization_confirmation": (
            required_authorization_confirmation(context, action_key)
        ),
        "required_panel_confirmation": required_panel_confirmation(context),
        "required_production_profile_confirmation": (
            None
            if production is None
            else required_production_profile_confirmation(production)
        ),
        "claim_created": False,
        "network_io_performed": False,
        "maximum_post_requests": 1,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "qualification_state": "NOT_QUALIFIED",
        "blockers": blockers,
    }
    return description, context, snapshot, production, prior


def describe_n8_physical_action(
    action_key: str,
    *,
    plan_files: N8PhysicalPlanFiles,
    production_files: Optional[N8ProductionFiles] = None,
    evaluated_at: Optional[str] = None,
    prior_result_files: Sequence[Path] = (),
) -> dict[str, Any]:
    description, _context, _snapshot, _production, _prior = _prepare(
        action_key,
        plan_files=plan_files,
        production_files=production_files,
        evaluated_at=evaluated_at,
        prior_result_files=prior_result_files,
    )
    return description


def _claim_action(
    context: physical.N8PhysicalContext,
    snapshot: frozen.N8ActionSnapshot,
    *,
    attempt_id: str,
    claimed_at: str,
    destination: Path,
    runtime_manifest_sha256: str,
    production: ValidatedProductionProfile,
    prior: Optional[_StoredChain],
    start_temperature_c: float,
    confirmations: Mapping[str, bool],
    authorization_confirmation: str,
    control_fields: Mapping[str, Any],
) -> _Claim:
    record = {
        "schema_version": SCHEMA_VERSION,
        "kind": frozen.CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action[
            "action_identity_sha256"
        ],
        "execution_contract_canonical_sha256": context.contract["integrity"][
            "canonical_sha256"
        ],
        "runtime_manifest_file_sha256": runtime_manifest_sha256,
        "attempt_id": attempt_id,
        "claimed_at": claimed_at,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "authorization_consumed_permanently": True,
        "authorization_confirmation_sha256": _sha256(
            authorization_confirmation.encode("ascii")
        ),
        "profile_canonical_sha256": production.profile["integrity"][
            "canonical_sha256"
        ],
        "profile_file_sha256": production.profile_file.sha256,
        "prior_bundle_file_sha256": _sha256(prior.payload) if prior else None,
        "prior_finalization_file_sha256": (
            prior.finalization_sha256 if prior else None
        ),
        "prior_result_file_sha256": prior.result_sha256 if prior else None,
        "start_external_temperature_c": start_temperature_c,
        "confirmations": dict(confirmations),
        "result_directory": str(destination),
        "maximum_post_requests": 1,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        **{key: control_fields[key] for key in physical._CONTROL_FIELDS},
    }
    payload = _canonical(record)
    registry = legacy._claim_registry()
    if legacy._fixed._is_within(destination, registry):
        raise N8PhysicalActionError("result directory overlaps the claim registry")
    _atomic(
        registry / f"{snapshot.action['action_identity_sha256']}.json",
        payload,
        unknown_after_commit=True,
    )
    return _Claim(record, _sha256(payload))


def _base_evidence(
    context: physical.N8PhysicalContext,
    snapshot: frozen.N8ActionSnapshot,
    *,
    attempt_id: str,
    recorded_at: str,
    runtime: Mapping[str, Any],
    runtime_sha256: str,
    production: ValidatedProductionProfile,
    claim: _Claim,
    evaluated_at: str,
    prior: Optional[_StoredChain],
    start_temperature_c: float,
    control_fields: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": frozen.EVIDENCE_KIND,
        "runner_kind": RUNNER_KIND,
        "attempt_id": attempt_id,
        "recorded_at": recorded_at,
        "protocol_completed_at": None,
        "profile_evaluated_at": evaluated_at,
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action[
            "action_identity_sha256"
        ],
        "sequence_id": snapshot.sequence_id,
        "ordinal": snapshot.ordinal,
        "role": snapshot.role,
        "frame_sha256": snapshot.action["identity"]["frame"]["sha256"],
        "reference_preview": dict(snapshot.reference_preview),
        "execution_contract_canonical_sha256": context.contract["integrity"][
            "canonical_sha256"
        ],
        "execution_contract_file_sha256": (
            physical.n8_physical_execution_contract_file_sha256(
                context.contract
            )
        ),
        "runtime_manifest_canonical_sha256": runtime["integrity"][
            "canonical_sha256"
        ],
        "runtime_manifest_file_sha256": runtime_sha256,
        "profile_canonical_sha256": production.profile["integrity"][
            "canonical_sha256"
        ],
        "profile_file_sha256": production.profile_file.sha256,
        "claim": claim.reference(),
        "prior_bundle_file_sha256": _sha256(prior.payload) if prior else None,
        "prior_finalization_file_sha256": (
            prior.finalization_sha256 if prior else None
        ),
        "prior_result_file_sha256": prior.result_sha256 if prior else None,
        "start_external_temperature_c": start_temperature_c,
        "maximum_post_requests": 1,
        "automatic_retry_count": 0,
        "retry_allowed": False,
        "recovery_performed": False,
        "outcome": None,
        "protocol_verified": False,
        "protocol_evidence": None,
        "request_audit": None,
        "error": None,
        "qualification_state": "NOT_QUALIFIED",
        "authorization_confirmation_sha256": control_fields[
            "authorization_confirmation_sha256"
        ],
        **{key: control_fields[key] for key in physical._CONTROL_FIELDS},
    }


def _copy_artifact(path: Path, payload: bytes) -> None:
    _atomic(path, payload)


def _copy_execution_inputs(
    destination: Path,
    context: physical.N8PhysicalContext,
    production: ValidatedProductionProfile,
) -> None:
    review = production.review_artifact_file
    if review is None:
        raise N8PhysicalActionError("production review artifact is missing")
    _copy_artifact(
        destination / PHYSICAL_CONTRACT_FILENAME, _canonical(context.contract)
    )
    _copy_artifact(
        destination / PHYSICAL_CAMPAIGN_FILENAME,
        _canonical(context.physical_campaign),
    )
    _copy_artifact(
        destination / BINDING_REVIEW_FILENAME, context.binding_review_bytes
    )
    _copy_artifact(
        destination / FIRMWARE_BINARY_FILENAME,
        production.inputs.firmware_binary.payload,
    )
    _copy_artifact(
        destination / LIMIT_AUTHORITY_FILENAME,
        production.inputs.limit_authority_file.payload,
    )
    _copy_artifact(
        destination / USAGE_EVIDENCE_FILENAME,
        production.inputs.usage_evidence_file.payload,
    )
    _copy_artifact(destination / PROFILE_REVIEW_FILENAME, review.payload)
    _copy_artifact(
        destination / PRODUCTION_VALIDATION_FILENAME,
        _canonical(production.report),
    )


def _record_unknown(
    destination: Optional[Path],
    base: Mapping[str, Any],
    *,
    requester_audit: Mapping[str, Any],
    error: BaseException,
    wall_clock: Callable[[], str],
) -> None:
    if destination is None:
        return
    evidence = {
        **base,
        "protocol_completed_at": wall_clock(),
        "outcome": ResultState.UNKNOWN_DO_NOT_RETRY.value,
        "protocol_verified": False,
        "protocol_evidence": None,
        "request_audit": dict(requester_audit),
        "error": {"type": type(error).__name__, "message": str(error)},
    }
    if not (destination / EVIDENCE_FILENAME).exists():
        _write_new(destination, EVIDENCE_FILENAME, evidence)
    result = build_result_record(
        action_identity_sha256=str(base["action_identity_sha256"]),
        state=ResultState.UNKNOWN_DO_NOT_RETRY,
        completed_at=wall_clock(),
        evidence_manifest_sha256=_sha256(evidence),
        post_request_count=int(requester_audit.get("post_issued_count", 0)),
        details="physical N8 claim consumed; retry/recovery forbidden",
    )
    if not (destination / P0_RESULT_FILENAME).exists():
        _write_new(destination, P0_RESULT_FILENAME, result)


def _record_claim_commit_uncertain(
    destination: Path,
    *,
    snapshot: frozen.N8ActionSnapshot,
    attempt_id: str,
    recorded_at: str,
    runtime_manifest_sha256: str,
    production: ValidatedProductionProfile,
    error: BaseException,
) -> None:
    marker = {
        "schema_version": SCHEMA_VERSION,
        "kind": CLAIM_COMMIT_UNCERTAIN_KIND,
        "attempt_id": attempt_id,
        "recorded_at": recorded_at,
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action[
            "action_identity_sha256"
        ],
        "runtime_manifest_file_sha256": runtime_manifest_sha256,
        "profile_canonical_sha256": production.profile["integrity"][
            "canonical_sha256"
        ],
        "profile_file_sha256": production.profile_file.sha256,
        "claim_state": "UNCERTAIN_DO_NOT_RETRY",
        "network_io_performed": False,
        "post_request_count": 0,
        "automatic_retry_allowed": False,
        "automatic_recovery_allowed": False,
        "error": {"type": type(error).__name__, "message": str(error)},
        "qualification_state": "NOT_QUALIFIED",
    }
    marker_sha = _write_new(
        destination, CLAIM_COMMIT_UNCERTAIN_FILENAME, marker
    )
    result = build_result_record(
        action_identity_sha256=snapshot.action["action_identity_sha256"],
        state=ResultState.UNKNOWN_DO_NOT_RETRY,
        completed_at=recorded_at,
        evidence_manifest_sha256=marker_sha,
        post_request_count=0,
        details="physical N8 claim commit uncertain; retry/recovery forbidden",
    )
    _write_new(destination, P0_RESULT_FILENAME, result)


def run_n8_physical_action_once(
    action_key: str,
    result_dir: Path,
    base_url: str,
    *,
    plan_files: N8PhysicalPlanFiles,
    production_files: N8ProductionFiles,
    evaluated_at: str,
    authorization_confirmation: str,
    panel_confirmation: str,
    profile_confirmation: str,
    start_external_temperature_c: float,
    prior_result_files: Sequence[Path] = (),
    confirmations: Optional[Mapping[str, bool]] = None,
    job_timeout_s: float = legacy._quality.DEFAULT_JOB_TIMEOUT_S,
    poll_interval_s: float = legacy._quality.DEFAULT_POLL_INTERVAL_S,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    wall_clock: Optional[Callable[[], str]] = None,
) -> dict[str, Any]:
    """Consume one physical claim, then perform exactly one visible POST."""

    destination = _prepare_destination(result_dir)
    if not isinstance(base_url, str) or not base_url.strip():
        raise N8PhysicalActionError("base_url must be a non-empty device root URL")
    description, context, snapshot, production, prior = _prepare(
        action_key,
        plan_files=plan_files,
        production_files=production_files,
        evaluated_at=evaluated_at,
        prior_result_files=prior_result_files,
    )
    if not description["contract_ready"] or production is None:
        raise N8PhysicalActionError(
            "physical N8 contract is not ready: "
            + ", ".join(description["blockers"])
        )
    now = _utc_now if wall_clock is None else wall_clock
    live_now = now()
    try:
        start_temp = legacy._temperature(
            start_external_temperature_c,
            label="start_external_temperature_c",
        )
        control = physical.n8_physical_control_fields(
            context,
            snapshot,
            production,
            evaluated_at=evaluated_at,
            live_now=live_now,
        )
    except (legacy.N8FixedActionError, physical.N8PhysicalExecutionError) as error:
        raise N8PhysicalActionError(str(error)) from error
    limits = production.profile["limits"]
    if not (
        limits["minimum_start_temperature_c"]
        <= start_temp
        <= limits["maximum_start_temperature_c"]
    ):
        raise N8PhysicalActionError(
            "start external temperature is outside reviewed limits"
        )
    expected_fields = legacy._confirmation_fields(snapshot)
    supplied = {} if confirmations is None else dict(confirmations)
    if (
        set(supplied) != expected_fields
        or any(type(value) is not bool or value is not True for value in supplied.values())
    ):
        raise N8PhysicalActionError(
            "all and only physical N8 action confirmations must be true"
        )
    if authorization_confirmation != required_authorization_confirmation(
        context, action_key
    ):
        raise N8PhysicalActionError(
            "exact physical N8 action authorization token is required"
        )
    if panel_confirmation != required_panel_confirmation(context):
        raise N8PhysicalActionError(
            "exact physical N8 panel/build/binding token is required"
        )
    if profile_confirmation != required_production_profile_confirmation(
        production
    ):
        raise N8PhysicalActionError(
            "exact physical N8 approved-profile token is required"
        )
    runtime = physical.compile_n8_physical_runtime_manifest(context, production)
    runtime_payload = _canonical(runtime)
    runtime_sha = _sha256(runtime_payload)
    attempt_id = uuid.uuid4().hex
    try:
        destination.mkdir()
        _copy_execution_inputs(destination, context, production)
        _atomic(destination / MANIFEST_FILENAME, runtime_payload)
        _atomic(destination / PROFILE_FILENAME, production.profile_file.payload)
        if prior is not None:
            _atomic(destination / PRIOR_BUNDLE_FILENAME, prior.payload)
    except BaseException as error:
        raise N8PhysicalActionError(
            "physical N8 pre-claim materialization failed; no action was issued"
        ) from error
    try:
        claim = _claim_action(
            context,
            snapshot,
            attempt_id=attempt_id,
            claimed_at=live_now,
            destination=destination,
            runtime_manifest_sha256=runtime_sha,
            production=production,
            prior=prior,
            start_temperature_c=start_temp,
            confirmations=supplied,
            authorization_confirmation=authorization_confirmation,
            control_fields=control,
        )
    except N8PhysicalActionUnknown as error:
        try:
            _record_claim_commit_uncertain(
                destination,
                snapshot=snapshot,
                attempt_id=attempt_id,
                recorded_at=live_now,
                runtime_manifest_sha256=runtime_sha,
                production=production,
                error=error,
            )
        except BaseException:
            pass
        raise N8PhysicalActionUnknown(
            "physical N8 claim commit is uncertain; durable marker attempted; "
            "do not retry or recover"
        ) from error
    audit_capture: dict[str, Any] = {
        "post_attempt_count": 0,
        "post_issued_count": 0,
        "calls": [],
    }
    base = _base_evidence(
        context,
        snapshot,
        attempt_id=attempt_id,
        recorded_at=live_now,
        runtime=runtime,
        runtime_sha256=runtime_sha,
        production=production,
        claim=claim,
        evaluated_at=evaluated_at,
        prior=prior,
        start_temperature_c=start_temp,
        control_fields=control,
    )
    try:
        lock = {
            "schema_version": SCHEMA_VERSION,
            "kind": frozen.LOCK_KIND,
            "execution_contract_canonical_sha256": context.contract[
                "integrity"
            ]["canonical_sha256"],
            "attempt_id": attempt_id,
            "action_key": action_key,
            "action_identity_sha256": snapshot.action[
                "action_identity_sha256"
            ],
            "claim": claim.reference(),
            "confirmations": supplied,
            "authorization_confirmation_sha256": control[
                "authorization_confirmation_sha256"
            ],
            "state": "authorization_permanently_consumed_do_not_rerun",
            "automatic_retry_authorized": False,
            "automatic_recovery_authorized": False,
            **{key: control[key] for key in physical._CONTROL_FIELDS},
        }
        _write_new(destination, LOCK_FILENAME, lock)
        prior_adapter = (
            None
            if prior is None
            else legacy._Prior(prior.bundle, prior.payload, prior.validated)
        )
        protocol, audit = legacy._execute_protocol(
            snapshot,
            prior_adapter,
            base_url,
            audit_sink=audit_capture,
            job_timeout_s=job_timeout_s,
            poll_interval_s=poll_interval_s,
            sleeper=sleeper,
            clock=clock,
            protocol_contract_builder=frozen.build_n8_protocol_contract,
            request_function=http_request,
        )
        evidence = {
            **base,
            "protocol_completed_at": now(),
            "outcome": "protocol_verified_observation_pending",
            "protocol_verified": True,
            "protocol_evidence": dict(protocol),
            "request_audit": dict(audit),
            "error": None,
        }
        _write_new(destination, EVIDENCE_FILENAME, evidence)
        return evidence
    except BaseException as error:
        try:
            _record_unknown(
                destination,
                base,
                requester_audit=audit_capture,
                error=error,
                wall_clock=now,
            )
        except BaseException:
            pass
        raise N8PhysicalActionUnknown(
            "physical N8 action is UNKNOWN_DO_NOT_RETRY; claim is permanent"
        ) from error


def _claim_from_reference(
    reference: Mapping[str, Any]
) -> tuple[Mapping[str, Any], str]:
    try:
        return legacy._load_claim(reference)
    except legacy.N8FixedActionError as error:
        raise N8PhysicalActionError(str(error)) from error


def _load_pending(
    result_dir: Path,
    *,
    reviewer_key_file: Path,
    prior_result_files: Sequence[Path],
) -> tuple[
    physical.N8PhysicalContext,
    frozen.N8ActionSnapshot,
    ValidatedProductionProfile,
    Mapping[str, Any],
    bytes,
    Mapping[str, Any],
    bytes,
    Mapping[str, Any],
    bytes,
    Mapping[str, Any],
    str,
    Optional[_StoredChain],
]:
    if not isinstance(result_dir, Path):
        raise N8PhysicalActionError("result_dir must be pathlib.Path")
    if not result_dir.is_dir() or result_dir.is_symlink():
        raise N8PhysicalActionError("result_dir must be an existing regular directory")
    for name in (
        OBSERVATION_FILENAME,
        FINALIZATION_FILENAME,
        P0_RESULT_FILENAME,
        BUNDLE_FILENAME,
    ):
        if os.path.lexists(result_dir / name):
            raise N8PhysicalActionError("physical N8 observation was already finalized")
    context = _load_context(_stored_plan_files(result_dir))
    runtime, runtime_payload = _strict_json_file(
        result_dir / MANIFEST_FILENAME,
        label="stored physical N8 runtime manifest",
    )
    profile, profile_payload = _strict_json_file(
        result_dir / PROFILE_FILENAME, label="stored physical N8 profile"
    )
    evidence, evidence_payload = _strict_json_file(
        result_dir / EVIDENCE_FILENAME,
        label="stored physical N8 protocol evidence",
    )
    lock, lock_payload = _strict_json_file(
        result_dir / LOCK_FILENAME, label="stored physical N8 action lock"
    )
    evaluated_at = evidence.get("profile_evaluated_at")
    if not isinstance(evaluated_at, str) or not evaluated_at:
        raise N8PhysicalActionError("pending N8 profile evaluation time is invalid")
    plan = _stored_plan_files(result_dir)
    production = _load_production(
        context,
        plan,
        _stored_production_files(result_dir, reviewer_key_file),
        evaluated_at=evaluated_at,
    )
    physical.validate_n8_physical_runtime_manifest(context, runtime, production)
    if (
        profile != production.profile
        or _sha256(profile_payload) != production.profile_file.sha256
        or evidence.get("runner_kind") != RUNNER_KIND
        or evidence.get("outcome") != "protocol_verified_observation_pending"
        or evidence.get("protocol_verified") is not True
        or evidence.get("request_audit", {}).get("post_issued_count") != 1
        or evidence.get("error") is not None
    ):
        raise N8PhysicalActionError("physical N8 evidence is not finalizable")
    claim, claim_sha = _claim_from_reference(evidence["claim"])
    snapshot = physical.load_n8_physical_action_snapshot(
        context, str(evidence.get("action_key"))
    )
    try:
        physical.validate_n8_physical_control_records(
            context,
            snapshot,
            production,
            {"claim": claim, "lock": lock, "evidence": evidence},
        )
    except physical.N8PhysicalExecutionError as error:
        raise N8PhysicalActionError(str(error)) from error
    if len(prior_result_files) != snapshot.ordinal - 1:
        raise N8PhysicalActionError(
            "finalization requires every prior result in this sequence"
        )
    prior: Optional[_StoredChain] = None
    if prior_result_files:
        prior = _load_stored_chain(
            prior_result_files[-1],
            reviewer_key_file=reviewer_key_file,
            prior_result_files=prior_result_files[:-1],
        )
        prior_bundle, prior_payload = _strict_json_file(
            result_dir / PRIOR_BUNDLE_FILENAME,
            label="copied physical N8 prior bundle",
        )
        if (
            prior.context.contract != context.contract
            or prior_bundle != prior.bundle
            or _sha256(prior_payload) != _sha256(prior.payload)
            or evidence.get("prior_bundle_file_sha256") != _sha256(prior.payload)
            or evidence.get("prior_finalization_file_sha256")
            != prior.finalization_sha256
            or evidence.get("prior_result_file_sha256") != prior.result_sha256
        ):
            raise N8PhysicalActionError("pending N8 prior chain changed")
    try:
        frozen._validate_protocol(
            evidence,
            snapshot,
            prior.bundle if prior else None,
            protocol_contract_builder=frozen.build_n8_protocol_contract,
        )
    except frozen.N8ExecutionContractError as error:
        raise N8PhysicalActionError(str(error)) from error
    return (
        context,
        snapshot,
        production,
        evidence,
        evidence_payload,
        profile,
        profile_payload,
        lock,
        lock_payload,
        claim,
        claim_sha,
        prior,
    )


def finalize_n8_physical_observation(
    result_dir: Path,
    operator_observation_file: Path,
    *,
    reviewer_key_file: Path,
    prior_result_files: Sequence[Path] = (),
) -> dict[str, Any]:
    """Seal one manual/camera observation after replaying all prior profiles."""

    (
        context,
        snapshot,
        production,
        evidence,
        evidence_payload,
        profile,
        profile_payload,
        lock,
        lock_payload,
        claim,
        claim_sha,
        prior,
    ) = _load_pending(
        result_dir,
        reviewer_key_file=reviewer_key_file,
        prior_result_files=prior_result_files,
    )
    source, source_payload = _strict_json_file(
        operator_observation_file,
        label="physical N8 operator observation",
    )
    runtime = evidence
    runtime_manifest, _runtime_payload = _strict_json_file(
        result_dir / MANIFEST_FILENAME,
        label="stored physical N8 runtime manifest",
    )
    try:
        observation, camera_payload = legacy._build_observation(
            source,
            source_payload,
            observation_file=operator_observation_file,
            snapshot=snapshot,
            runtime=runtime_manifest,
            evidence=runtime,
        )
    except legacy.N8FixedActionError as error:
        raise N8PhysicalActionError(str(error)) from error
    observation_payload = _canonical(observation)
    observation_sha = _sha256(observation_payload)
    evidence_sha = _sha256(evidence_payload)
    profile_sha = _sha256(profile_payload)
    lock_sha = _sha256(lock_payload)
    finalization = {
        "schema_version": SCHEMA_VERSION,
        "kind": frozen.FINALIZATION_KIND,
        "attempt_id": evidence["attempt_id"],
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action[
            "action_identity_sha256"
        ],
        "sequence_id": snapshot.sequence_id,
        "ordinal": snapshot.ordinal,
        "state": observation["overall_state"],
        "manifest_file_sha256": evidence["runtime_manifest_file_sha256"],
        "claim_file_sha256": claim_sha,
        "lock_file_sha256": lock_sha,
        "profile_file_sha256": profile_sha,
        "protocol_evidence_file_sha256": evidence_sha,
        "action_observation_file_sha256": observation_sha,
        "prior_bundle_file_sha256": _sha256(prior.payload) if prior else None,
        "prior_finalization_file_sha256": (
            prior.finalization_sha256 if prior else None
        ),
        "prior_result_file_sha256": prior.result_sha256 if prior else None,
        "visual_pass": observation["visual_pass"],
        "electrical_pass": observation["electrical_pass"],
        "thermal_pass": observation["thermal_pass"],
        "temperature_bin_pass": observation["temperature_bin_pass"],
        "continuity_pass": observation["continuity_pass"],
        "camera_capture_file_sha256": observation["camera"][
            "capture_file_sha256"
        ],
        "visual_electrical_thermal_continuity_assessed_separately": True,
        "automatic_retry_count": 0,
        "retry_allowed": False,
        "recovery_performed": False,
        "qualification_state": "NOT_QUALIFIED",
        "authorization_confirmation_sha256": evidence[
            "authorization_confirmation_sha256"
        ],
        **{key: evidence[key] for key in physical._CONTROL_FIELDS},
    }
    finalization_payload = _canonical(finalization)
    finalization_sha = _sha256(finalization_payload)
    result = build_result_record(
        action_identity_sha256=snapshot.action["action_identity_sha256"],
        state=ResultState(observation["overall_state"]),
        completed_at=str(observation["observed_at"]),
        evidence_manifest_sha256=finalization_sha,
        post_request_count=1,
        details="physical N8 observation finalized; remains NOT_QUALIFIED",
    )
    result_payload = _canonical(result)
    result_sha = _sha256(result_payload)
    records = {
        "manifest": (runtime_manifest, evidence["runtime_manifest_file_sha256"]),
        "claim": (claim, claim_sha),
        "lock": (lock, lock_sha),
        "profile": (profile, profile_sha),
        "evidence": (evidence, evidence_sha),
        "observation": (observation, observation_sha),
        "finalization": (finalization, finalization_sha),
        "result": (result, result_sha),
    }
    bundle: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": frozen.BUNDLE_KIND,
    }
    for name, (record, digest) in records.items():
        bundle[name] = record
        bundle[f"{name}_file_sha256"] = digest
    bundle.update(
        {
            "prior_bundle": prior.bundle if prior else None,
            "prior_bundle_file_sha256": _sha256(prior.payload) if prior else None,
            "qualification_state": "NOT_QUALIFIED",
        }
    )
    try:
        validated = physical.validate_n8_physical_finalized_action_bundle(
            context,
            bundle,
            production_profile=production,
            prior_production_profiles=(
                () if prior is None else prior.production_chain
            ),
            expected_action_key=snapshot.key,
        )
    except physical.N8PhysicalExecutionError as error:
        raise N8PhysicalActionError(
            f"refusing invalid physical N8 finalization: {error}"
        ) from error
    _atomic(result_dir / CAMERA_CAPTURE_FILENAME, camera_payload)
    _atomic(result_dir / OBSERVATION_FILENAME, observation_payload)
    _atomic(result_dir / FINALIZATION_FILENAME, finalization_payload)
    _atomic(result_dir / P0_RESULT_FILENAME, result_payload)
    _atomic(result_dir / BUNDLE_FILENAME, _canonical(bundle))
    return {
        **validated,
        "bundle_file_sha256": _sha256(bundle),
        "camera_capture_present": True,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=frozen.FIXED_ACTION_KEYS)
    parser.add_argument("--describe-only", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--validate-result", action="store_true")
    parser.add_argument("--physical-contract", type=Path)
    parser.add_argument("--physical-campaign", type=Path)
    parser.add_argument("--binding-review-artifact", type=Path)
    parser.add_argument("--minimum-interval-seconds", type=float)
    parser.add_argument("--planned-cooldown-seconds", type=float)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--firmware-binary", type=Path)
    parser.add_argument("--limit-authority", type=Path)
    parser.add_argument("--usage-evidence", type=Path)
    parser.add_argument("--profile-review", type=Path)
    parser.add_argument("--reviewer-key", type=Path)
    parser.add_argument("--evaluated-at")
    parser.add_argument("--prior-result", type=Path, action="append", default=[])
    parser.add_argument("--result-dir", type=Path)
    parser.add_argument("--result-file", type=Path)
    parser.add_argument("--base-url")
    parser.add_argument("--authorization-confirmation")
    parser.add_argument("--panel-confirmation")
    parser.add_argument("--profile-confirmation")
    parser.add_argument("--start-external-temperature-c", type=float)
    parser.add_argument("--operator-observation", type=Path)
    for field in (
        "reviewed_panel_and_build",
        "supervised_supply_cv_current_normal",
        "physical_cutoff_available",
        "single_visible_refresh",
        "external_temperature_instrument_verified",
        "fixed_camera_ready",
        "controller_fresh_boot",
        "controller_idle_no_inflight_job",
        "supervised_continuous_session_start",
        "prior_screen_fidelity_pass",
        "esp32_not_restarted_between_actions",
        "no_j2_disconnect_between_actions",
        "no_panel_power_cycle_between_actions",
        "no_other_visible_refresh_between_actions",
    ):
        parser.add_argument(
            "--confirm-" + field.replace("_", "-"),
            dest="confirm_" + field,
            action="store_true",
        )
    args = parser.parse_args(argv)
    modes = sum(
        bool(value)
        for value in (
            args.describe_only,
            args.finalize,
            args.validate_result,
        )
    )
    if modes > 1:
        parser.error("describe, finalize, and validate modes are mutually exclusive")
    if args.finalize:
        if not args.result_dir or not args.operator_observation or not args.reviewer_key:
            parser.error(
                "finalize requires result-dir, operator-observation, reviewer-key"
            )
        return args
    if args.validate_result:
        if not args.result_file or not args.reviewer_key:
            parser.error("validate requires result-file and reviewer-key")
        return args
    plan_values = {
        "--action": args.action,
        "--physical-contract": args.physical_contract,
        "--physical-campaign": args.physical_campaign,
        "--binding-review-artifact": args.binding_review_artifact,
        "--minimum-interval-seconds": args.minimum_interval_seconds,
        "--planned-cooldown-seconds": args.planned_cooldown_seconds,
    }
    missing = [name for name, value in plan_values.items() if value is None]
    if missing:
        parser.error("action mode requires " + ", ".join(missing))
    production_values = {
        "--profile": args.profile,
        "--firmware-binary": args.firmware_binary,
        "--limit-authority": args.limit_authority,
        "--usage-evidence": args.usage_evidence,
        "--profile-review": args.profile_review,
        "--reviewer-key": args.reviewer_key,
    }
    present = [
        name for name, value in production_values.items() if value is not None
    ]
    if present and len(present) != len(production_values):
        parser.error("deep production inputs are all-or-none")
    if args.describe_only:
        if present and args.evaluated_at is None:
            parser.error("deep describe requires --evaluated-at")
        return args
    missing = [name for name, value in production_values.items() if value is None]
    live_values = {
        "--evaluated-at": args.evaluated_at,
        "--result-dir": args.result_dir,
        "--base-url": args.base_url,
        "--authorization-confirmation": args.authorization_confirmation,
        "--panel-confirmation": args.panel_confirmation,
        "--profile-confirmation": args.profile_confirmation,
        "--start-external-temperature-c": args.start_external_temperature_c,
    }
    missing.extend(
        name for name, value in live_values.items() if value is None
    )
    if missing:
        parser.error("live execution requires " + ", ".join(missing))
    return args


def _plan_files(args: argparse.Namespace) -> N8PhysicalPlanFiles:
    return N8PhysicalPlanFiles(
        contract=args.physical_contract,
        physical_campaign=args.physical_campaign,
        binding_review_artifact=args.binding_review_artifact,
        minimum_interval_seconds=args.minimum_interval_seconds,
        planned_cooldown_seconds=args.planned_cooldown_seconds,
    )


def _production_files(args: argparse.Namespace) -> N8ProductionFiles:
    return N8ProductionFiles(
        profile=args.profile,
        firmware_binary=args.firmware_binary,
        limit_authority=args.limit_authority,
        usage_evidence=args.usage_evidence,
        review_artifact=args.profile_review,
        reviewer_key=args.reviewer_key,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.finalize:
            value = finalize_n8_physical_observation(
                args.result_dir,
                args.operator_observation,
                reviewer_key_file=args.reviewer_key,
                prior_result_files=args.prior_result,
            )
        elif args.validate_result:
            value = load_n8_physical_finalized_action_bundle(
                args.result_file,
                reviewer_key_file=args.reviewer_key,
                prior_result_files=args.prior_result,
            )
        elif args.describe_only:
            value = describe_n8_physical_action(
                args.action,
                plan_files=_plan_files(args),
                production_files=(
                    _production_files(args) if args.profile else None
                ),
                evaluated_at=args.evaluated_at,
                prior_result_files=args.prior_result,
            )
        else:
            context = _load_context(_plan_files(args))
            snapshot = physical.load_n8_physical_action_snapshot(
                context, args.action
            )
            confirmations = {
                field: bool(getattr(args, "confirm_" + field))
                for field in legacy._confirmation_fields(snapshot)
            }
            value = run_n8_physical_action_once(
                args.action,
                args.result_dir,
                args.base_url,
                plan_files=_plan_files(args),
                production_files=_production_files(args),
                evaluated_at=args.evaluated_at,
                authorization_confirmation=args.authorization_confirmation,
                panel_confirmation=args.panel_confirmation,
                profile_confirmation=args.profile_confirmation,
                start_external_temperature_c=(
                    args.start_external_temperature_c
                ),
                prior_result_files=args.prior_result,
                confirmations=confirmations,
            )
    except (N8PhysicalActionError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BINDING_REVIEW_FILENAME",
    "CLAIM_COMMIT_UNCERTAIN_FILENAME",
    "FIRMWARE_BINARY_FILENAME",
    "LIMIT_AUTHORITY_FILENAME",
    "N8PhysicalActionError",
    "N8PhysicalActionUnknown",
    "N8PhysicalPlanFiles",
    "N8ProductionFiles",
    "DESCRIPTION_KIND",
    "PHYSICAL_CAMPAIGN_FILENAME",
    "PHYSICAL_CONTRACT_FILENAME",
    "PRODUCTION_VALIDATION_FILENAME",
    "PROFILE_REVIEW_FILENAME",
    "USAGE_EVIDENCE_FILENAME",
    "authorization_confirmation_sha256",
    "describe_n8_physical_action",
    "finalize_n8_physical_observation",
    "load_n8_physical_finalized_action_bundle",
    "load_n8_physical_finalized_action_chain",
    "main",
    "parse_args",
    "required_authorization_confirmation",
    "required_panel_confirmation",
    "required_production_profile_confirmation",
    "run_n8_physical_action_once",
]
