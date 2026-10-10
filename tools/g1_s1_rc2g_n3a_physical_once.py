#!/usr/bin/env python3
"""Describe, execute once, finalize, and replay one physical N3A action.

The selected repeat-2/3/4 plan is re-authorized from its eight physical N2
source result directories on every public path.  Live execution consumes a
workspace-global claim before the only permitted ``POST /api/frame``.  There
is no retry, recovery, reset, firmware upload, serial, or power-control path.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
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
from tools import g1_s1_n3_execution_contract as frozen  # noqa: E402
from tools import g1_s1_n3a_physical_execution as physical  # noqa: E402
from tools import g1_s1_rc2g_n2_physical_analyzer as n2_analyzer  # noqa: E402
from tools import g1_s1_rc2g_n3_once as legacy  # noqa: E402
from tools import g1_s1_rc2g_quality_refresh_once as _quality  # noqa: E402


SCHEMA_VERSION = 1
RUNNER_KIND = "mf1750-g1-s1-rc2g-n3a-physical-fixed-action-runner"
DESCRIPTION_KIND = "mf1750-g1-s1-rc2g-n3a-physical-action-description"
SESSION_KIND = "mf1750-g1-s1-n3a-physical-session-observation"

LOCK_FILENAME = legacy.LOCK_FILENAME
PROFILE_FILENAME = legacy.PROFILE_FILENAME
EVIDENCE_FILENAME = legacy.EVIDENCE_FILENAME
OBSERVATION_FILENAME = legacy.OBSERVATION_FILENAME
FINALIZATION_FILENAME = legacy.FINALIZATION_FILENAME
P0_RESULT_FILENAME = legacy.P0_RESULT_FILENAME
SESSION_OBSERVATION_FILENAME = legacy.SESSION_OBSERVATION_FILENAME
CAMERA_CAPTURE_FILENAME = legacy.CAMERA_CAPTURE_FILENAME

PHYSICAL_PLAN_FILENAME = "N3A-PHYSICAL-PLAN.json"
BINDING_REVIEW_FILENAME = "PHYSICAL-BINDING-REVIEW.bin"
PHYSICAL_CAMPAIGN_FILENAME = "PHYSICAL-CAMPAIGN.json"
FIRMWARE_BINARY_FILENAME = "FIRMWARE.bin"
LIMIT_AUTHORITY_FILENAME = "LIMIT-AUTHORITY.json"
SUPPLIER_LIMITS_FILENAME = LIMIT_AUTHORITY_FILENAME
USAGE_EVIDENCE_FILENAME = "USAGE-EVIDENCE.json"
PROFILE_REVIEW_FILENAME = "PROFILE-REVIEW.json"
PRODUCTION_VALIDATION_FILENAME = "PRODUCTION-PROFILE-VALIDATION.json"

http_request = legacy.http_request


class N3APhysicalActionError(RuntimeError):
    """The action was rejected before its permanent claim existed."""


class N3APhysicalActionUnknown(N3APhysicalActionError):
    """The permanent claim exists; retry and recovery are forbidden."""


@dataclass(frozen=True)
class N3APhysicalPlanFiles:
    plan: Path
    binding_review_artifact: Path
    minimum_interval_seconds: float
    planned_cooldown_seconds: float
    n2_result_directories: Mapping[str, Path]
    n2_reviewer_key: Path


@dataclass(frozen=True)
class N3AProductionFiles:
    profile: Path
    physical_campaign: Path
    firmware_binary: Path
    limit_authority: Path
    usage_evidence: Path
    review_artifact: Path
    reviewer_key: Path

    @property
    def supplier_limits(self) -> Path:
        return self.limit_authority


@dataclass(frozen=True)
class _StoredChain:
    context: physical.N3APhysicalContext
    production: ValidatedProductionProfile
    bundle: Mapping[str, Any]
    validated: Mapping[str, Any]

    @property
    def result(self) -> Mapping[str, Any]:
        return self.bundle["result"]

    @property
    def result_sha256(self) -> str:
        return str(self.validated["result_file_sha256"])

    @property
    def finalization_sha256(self) -> str:
        return str(self.validated["finalization_file_sha256"])

    @property
    def evidence(self) -> Mapping[str, Any]:
        return self.bundle["evidence"]


def _canonical(value: Any) -> bytes:
    try:
        return canonical_json_bytes(value)
    except CampaignContractError as error:
        raise N3APhysicalActionError(str(error)) from error


def _sha256(value: Any) -> str:
    return physical._sha256(value)


def _utc_now() -> str:
    return legacy._utc_now()


def _strict_json(path: Path, *, label: str) -> tuple[Mapping[str, Any], bytes]:
    try:
        return legacy._strict_json_file(path, label=label)
    except legacy.N3FixedActionError as error:
        raise N3APhysicalActionError(str(error)) from error


def _safe_file(path: Path, *, label: str) -> Path:
    try:
        return legacy._safe_regular_file(path, label=label)
    except legacy.N3FixedActionError as error:
        raise N3APhysicalActionError(str(error)) from error


def _atomic(path: Path, payload: bytes, *, unknown: bool) -> None:
    try:
        legacy._atomic_commit(path, payload, unknown_after_commit=unknown)
    except legacy.N3FixedActionUnknown as error:
        raise N3APhysicalActionUnknown(str(error)) from error
    except legacy.N3FixedActionError as error:
        raise N3APhysicalActionError(str(error)) from error


def _write_new(directory: Path, filename: str, value: Mapping[str, Any]) -> str:
    payload = _canonical(value)
    _atomic(directory / filename, payload, unknown=True)
    return _sha256(payload)


def _context(files: N3APhysicalPlanFiles) -> physical.N3APhysicalContext:
    try:
        return physical.load_n3a_physical_execution_context(
            plan_file=files.plan,
            binding_review_artifact_file=files.binding_review_artifact,
            minimum_interval_seconds=files.minimum_interval_seconds,
            planned_cooldown_seconds=files.planned_cooldown_seconds,
            n2_result_directories=files.n2_result_directories,
            n2_reviewer_key_file=files.n2_reviewer_key,
        )
    except physical.N3APhysicalExecutionError as error:
        raise N3APhysicalActionError(str(error)) from error


def _production(
    context: physical.N3APhysicalContext,
    action_key: str,
    files: N3AProductionFiles,
    *,
    evaluated_at: str,
) -> ValidatedProductionProfile:
    try:
        return physical.load_n3a_physical_production_profile(
            context,
            action_key,
            profile_file=files.profile,
            campaign_file=files.physical_campaign,
            firmware_binary_file=files.firmware_binary,
            limit_authority_file=files.limit_authority,
            usage_evidence_file=files.usage_evidence,
            review_artifact_file=files.review_artifact,
            reviewer_key_file=files.reviewer_key,
            evaluated_at=evaluated_at,
        )
    except physical.N3APhysicalExecutionError as error:
        raise N3APhysicalActionError(str(error)) from error


def required_authorization_confirmation(
    context: physical.N3APhysicalContext, action_key: str
) -> str:
    snapshot = physical.load_n3a_physical_action_snapshot(context, action_key)
    return physical.required_authorization_confirmation(context.plan, snapshot)


def required_panel_plan_confirmation(
    context: physical.N3APhysicalContext, action_key: str
) -> str:
    snapshot = physical.load_n3a_physical_action_snapshot(context, action_key)
    return physical.required_panel_plan_confirmation(context, snapshot)


def required_production_profile_confirmation(
    production: ValidatedProductionProfile,
) -> str:
    return physical.required_production_profile_confirmation(production)


def _target_contract(
    context: physical.N3APhysicalContext,
    snapshot: frozen.N3ActionSnapshot,
) -> _quality._RunContract:
    try:
        contract = frozen.build_n3_target_protocol_contract(snapshot)
    except frozen.N3ExecutionContractError as error:
        raise N3APhysicalActionError(str(error)) from error
    return _quality._RunContract(
        **{
            **contract.__dict__,
            "required_authorization_confirmation": (
                physical.required_authorization_confirmation(context.plan, snapshot)
            ),
        }
    )


def _stored_plan_files(
    directory: Path,
    *,
    n2_result_directories: Mapping[str, Path],
    n2_reviewer_key_file: Path,
) -> N3APhysicalPlanFiles:
    plan, _payload = _strict_json(
        directory / PHYSICAL_PLAN_FILENAME, label="stored N3A physical plan"
    )
    schedule = plan.get("process_schedule", {})
    return N3APhysicalPlanFiles(
        plan=directory / PHYSICAL_PLAN_FILENAME,
        binding_review_artifact=directory / BINDING_REVIEW_FILENAME,
        minimum_interval_seconds=schedule.get("minimum_interval_seconds"),
        planned_cooldown_seconds=schedule.get("planned_cooldown_seconds"),
        n2_result_directories=n2_result_directories,
        n2_reviewer_key=n2_reviewer_key_file,
    )


def _stored_production_files(
    directory: Path, profile_reviewer_key_file: Path
) -> N3AProductionFiles:
    return N3AProductionFiles(
        profile=directory / PROFILE_FILENAME,
        physical_campaign=directory / PHYSICAL_CAMPAIGN_FILENAME,
        firmware_binary=directory / FIRMWARE_BINARY_FILENAME,
        limit_authority=directory / LIMIT_AUTHORITY_FILENAME,
        usage_evidence=directory / USAGE_EVIDENCE_FILENAME,
        review_artifact=directory / PROFILE_REVIEW_FILENAME,
        reviewer_key=profile_reviewer_key_file,
    )


def _load_stored_chain(
    result_file: Path,
    *,
    n2_result_directories: Mapping[str, Path],
    n2_reviewer_key_file: Path,
    profile_reviewer_key_file: Path,
    prior_result_file: Optional[Path] = None,
) -> _StoredChain:
    result = _safe_file(result_file, label="physical N3A P0 result")
    if result.name != P0_RESULT_FILENAME:
        raise N3APhysicalActionError(
            f"physical N3A result filename must be {P0_RESULT_FILENAME}"
        )
    directory = result.parent
    context = _context(
        _stored_plan_files(
            directory,
            n2_result_directories=n2_result_directories,
            n2_reviewer_key_file=n2_reviewer_key_file,
        )
    )
    try:
        bundle = legacy._load_bundle_from_result_file(result)
    except legacy.N3FixedActionError as error:
        raise N3APhysicalActionError(str(error)) from error
    action_key = str(bundle["evidence"].get("action_key"))
    evaluated_at = bundle["evidence"].get("profile_evaluated_at")
    if not isinstance(evaluated_at, str) or not evaluated_at:
        raise N3APhysicalActionError("stored profile evaluation time is invalid")
    production = _production(
        context,
        action_key,
        _stored_production_files(directory, profile_reviewer_key_file),
        evaluated_at=evaluated_at,
    )
    report, report_payload = _strict_json(
        directory / PRODUCTION_VALIDATION_FILENAME,
        label="stored N3A production validation",
    )
    if report != production.report or _sha256(report_payload) != _sha256(
        _canonical(production.report)
    ):
        raise N3APhysicalActionError("stored production validation changed")
    snapshot = physical.load_n3a_physical_action_snapshot(context, action_key)
    prior: Optional[_StoredChain] = None
    if snapshot.phase == "target":
        if prior_result_file is None:
            raise N3APhysicalActionError("target replay requires its MAP result")
        prior = _load_stored_chain(
            prior_result_file,
            n2_result_directories=n2_result_directories,
            n2_reviewer_key_file=n2_reviewer_key_file,
            profile_reviewer_key_file=profile_reviewer_key_file,
        )
        if prior.context.plan != context.plan:
            raise N3APhysicalActionError("target and MAP physical plans differ")
    elif prior_result_file is not None:
        raise N3APhysicalActionError("MAP replay must not receive a prior")
    try:
        validated = physical.validate_n3a_physical_finalized_action_bundle(
            context,
            bundle,
            production_profile=production,
            expected_action_key=action_key,
            prior_bundle=prior.bundle if prior else None,
            prior_production_profile=prior.production if prior else None,
        )
    except physical.N3APhysicalExecutionError as error:
        raise N3APhysicalActionError(str(error)) from error
    return _StoredChain(context, production, bundle, validated)


def load_n3a_physical_finalized_action_bundle(
    result_file: Path,
    *,
    n2_result_directories: Mapping[str, Path],
    n2_reviewer_key_file: Path,
    profile_reviewer_key_file: Path,
    primer_result_file: Optional[Path] = None,
) -> dict[str, Any]:
    """Public deep validator; raw N2 replay and profile key are mandatory."""

    return dict(
        _load_stored_chain(
            result_file,
            n2_result_directories=n2_result_directories,
            n2_reviewer_key_file=n2_reviewer_key_file,
            profile_reviewer_key_file=profile_reviewer_key_file,
            prior_result_file=primer_result_file,
        ).validated
    )


def load_n3a_physical_finalized_action_chain(
    result_file: Path,
    *,
    n2_result_directories: Mapping[str, Path],
    n2_reviewer_key_file: Path,
    profile_reviewer_key_file: Path,
    primer_result_file: Optional[Path] = None,
) -> _StoredChain:
    return _load_stored_chain(
        result_file,
        n2_result_directories=n2_result_directories,
        n2_reviewer_key_file=n2_reviewer_key_file,
        profile_reviewer_key_file=profile_reviewer_key_file,
        prior_result_file=primer_result_file,
    )


def _prepare(
    action_key: str,
    *,
    plan_files: N3APhysicalPlanFiles,
    production_files: Optional[N3AProductionFiles],
    evaluated_at: Optional[str],
    primer_result_file: Optional[Path],
) -> tuple[
    dict[str, Any],
    physical.N3APhysicalContext,
    frozen.N3ActionSnapshot,
    Optional[ValidatedProductionProfile],
    Optional[_StoredChain],
]:
    context = _context(plan_files)
    try:
        snapshot = physical.load_n3a_physical_action_snapshot(context, action_key)
    except physical.N3APhysicalExecutionError as error:
        raise N3APhysicalActionError(str(error)) from error
    blockers: list[str] = []
    prior: Optional[_StoredChain] = None
    production: Optional[ValidatedProductionProfile] = None
    description: Optional[Mapping[str, Any]] = None
    if production_files is None:
        blockers.append("deep_production_profile_inputs_missing")
    if evaluated_at is None:
        blockers.append("explicit_evaluated_at_missing")
    if snapshot.phase == "target" and primer_result_file is None:
        blockers.append("same_session_finalized_map_pass_missing")
    if snapshot.phase == "map-primer" and primer_result_file is not None:
        raise N3APhysicalActionError("MAP action must not receive a prior")
    if primer_result_file is not None:
        if production_files is None:
            blockers.append("prior_profile_reviewer_key_missing")
        else:
            prior = _load_stored_chain(
                primer_result_file,
                n2_result_directories=plan_files.n2_result_directories,
                n2_reviewer_key_file=plan_files.n2_reviewer_key,
                profile_reviewer_key_file=production_files.reviewer_key,
            )
            expected = snapshot.action["identity"]["prior"][
                "action_identity_sha256"
            ]
            if (
                prior.context.plan != context.plan
                or prior.validated["action_identity_sha256"] != expected
                or prior.validated["state"] != ResultState.PASS.value
            ):
                raise N3APhysicalActionError(
                    "same-session MAP is cross-plan, cross-repeat, or not PASS"
                )
    if production_files is not None and evaluated_at is not None:
        production = _production(
            context, action_key, production_files, evaluated_at=evaluated_at
        )
        if production.report["production_ready"] is not True:
            blockers.extend(production.report["reasons"])
            blockers.append("deep_production_profile_not_ready")
        try:
            description = describe_action_offline(
                snapshot.campaign,
                action_identity_sha256=snapshot.action["action_identity_sha256"],
                limit_profile=production.profile,
                evaluated_at=evaluated_at,
                prior_result=prior.result if prior else None,
                prior_result_sha256=prior.result_sha256 if prior else None,
            )
        except CampaignContractError as error:
            raise N3APhysicalActionError(str(error)) from error
        blockers.extend(
            item
            for item in description["blockers"]
            if item != "current_runtime_gates_and_exact_authorization_not_evaluated"
        )
        if snapshot.phase == "target" and prior is not None:
            try:
                physical.validate_target_usage_continuity(production, prior.result)
            except physical.N3APhysicalExecutionError as error:
                raise N3APhysicalActionError(str(error)) from error
    blockers = list(dict.fromkeys(blockers))
    plan = physical.validate_n3a_physical_execution_context(context)
    output = {
        "schema_version": SCHEMA_VERSION,
        "kind": DESCRIPTION_KIND,
        "mode": "describe-only",
        "action_key": action_key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "winner_cell_id": plan["selection"]["winner_cell_id"],
        "repeat_count": plan["selection"]["repeat_count"],
        "repeat_ordinal": snapshot.route["repeat_ordinal"],
        "phase": snapshot.phase,
        "plan_canonical_sha256": plan["integrity"]["canonical_sha256"],
        "plan_file_sha256": _sha256(plan),
        "n2_raw_evidence_replayed": True,
        "n2_physical_provenance_canonical_sha256": plan[
            "n2_physical_provenance"
        ]["canonical_sha256"],
        "p0_campaign_canonical_sha256": snapshot.campaign["integrity"][
            "canonical_sha256"
        ],
        "process_schedule": dict(plan["process_schedule"]),
        "reference_preview": dict(snapshot.reference_preview),
        "profile_validation": dict(production.report) if production else None,
        "p0_description": dict(description) if description else None,
        "contract_ready": bool(
            production
            and production.report["production_ready"] is True
            and description
            and description["contract_ready"] is True
            and not blockers
        ),
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "maximum_post_requests": 1,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "required_authorization_confirmation_sha256": _sha256(
            required_authorization_confirmation(context, action_key).encode("ascii")
        ),
        "required_panel_plan_confirmation_sha256": _sha256(
            required_panel_plan_confirmation(context, action_key).encode("utf-8")
        ),
        "required_profile_confirmation_sha256": (
            _sha256(
                required_production_profile_confirmation(production).encode("utf-8")
            )
            if production
            else None
        ),
        "maximum_live_evaluation_age_seconds": (
            physical.MAX_LIVE_EVALUATED_AT_AGE_SECONDS
        ),
        "blockers": blockers,
    }
    return output, context, snapshot, production, prior


def describe_n3a_physical_action(
    action_key: str,
    *,
    plan_files: N3APhysicalPlanFiles,
    production_files: Optional[N3AProductionFiles] = None,
    evaluated_at: Optional[str] = None,
    primer_result_file: Optional[Path] = None,
) -> dict[str, Any]:
    return _prepare(
        action_key,
        plan_files=plan_files,
        production_files=production_files,
        evaluated_at=evaluated_at,
        primer_result_file=primer_result_file,
    )[0]


def _claim_action(
    context: physical.N3APhysicalContext,
    snapshot: frozen.N3ActionSnapshot,
    *,
    attempt_id: str,
    claimed_at: str,
    destination: Path,
    production: ValidatedProductionProfile,
    prior: Optional[_StoredChain],
    start_temperature_c: float,
    confirmations: Mapping[str, bool],
    authorization_confirmation: str,
    controls: Mapping[str, Any],
) -> legacy._Claim:
    declaration = snapshot.action["claim"]
    try:
        registry = legacy._claim_registry()
    except legacy.N3FixedActionError as error:
        raise N3APhysicalActionError(str(error)) from error
    try:
        if destination.resolve(strict=False).is_relative_to(registry):
            raise N3APhysicalActionError(
                "result directory must not overlap claim registry"
            )
    except AttributeError:  # pragma: no cover
        if str(destination.resolve(strict=False)).startswith(str(registry) + os.sep):
            raise N3APhysicalActionError(
                "result directory must not overlap claim registry"
            )
    if declaration["filename"] != f"{snapshot.action['action_identity_sha256']}.json":
        raise N3APhysicalActionError("physical action claim declaration changed")
    plan = physical.validate_n3a_physical_execution_context(context)
    record = {
        "schema_version": SCHEMA_VERSION,
        "kind": frozen.CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "plan_id": plan["plan_id"],
        "plan_canonical_sha256": plan["integrity"]["canonical_sha256"],
        "plan_file_sha256": _sha256(plan),
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "p0_campaign_canonical_sha256": snapshot.campaign["integrity"][
            "canonical_sha256"
        ],
        "attempt_id": attempt_id,
        "claimed_at": claimed_at,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "authorization_consumed_permanently": True,
        "authorization_confirmation_sha256": _sha256(
            authorization_confirmation.encode("ascii")
        ),
        **{key: controls[key] for key in physical._CONTROL_FIELDS},
        "profile_canonical_sha256": production.profile["integrity"][
            "canonical_sha256"
        ],
        "profile_file_sha256": production.profile_file.sha256,
        "prior_result_file_sha256": prior.result_sha256 if prior else None,
        "prior_finalization_file_sha256": (
            prior.finalization_sha256 if prior else None
        ),
        "start_temperature_c": start_temperature_c,
        "confirmations": dict(confirmations),
        "result_directory": str(destination),
        "maximum_post_requests": 1,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
    }
    payload = _canonical(record)
    _atomic(registry / declaration["filename"], payload, unknown=True)
    return legacy._Claim(registry, declaration["filename"], record, _sha256(payload))


def _base_evidence(
    context: physical.N3APhysicalContext,
    snapshot: frozen.N3ActionSnapshot,
    *,
    attempt_id: str,
    claim: legacy._Claim,
    recorded_at: str,
    production: ValidatedProductionProfile,
    evaluated_at: str,
    prior: Optional[_StoredChain],
    start_temperature_c: float,
    controls: Mapping[str, Any],
) -> dict[str, Any]:
    plan = physical.validate_n3a_physical_execution_context(context)
    compat = physical.compatibility_plan(context)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": frozen.EVIDENCE_KIND,
        "runner_kind": frozen.RUNNER_KIND,
        "attempt_id": attempt_id,
        "recorded_at": recorded_at,
        "protocol_completed_at": None,
        "action_key": snapshot.key,
        "cell_id": snapshot.cell_id,
        "candidate_cell_id": snapshot.candidate_cell_id,
        "phase": snapshot.phase,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "plan_id": plan["plan_id"],
        "plan_canonical_sha256": plan["integrity"]["canonical_sha256"],
        "plan_file_sha256": _sha256(plan),
        "execution_manifest_canonical_sha256": compat["execution_manifest"][
            "integrity"
        ]["canonical_sha256"],
        "p0_campaign_canonical_sha256": snapshot.campaign["integrity"][
            "canonical_sha256"
        ],
        "source_manifest_canonical_sha256": compat["source_manifest"][
            "canonical_sha256"
        ],
        "frame_sha256": snapshot.action["identity"]["frame"]["sha256"],
        "reference_preview": dict(snapshot.reference_preview),
        "claim": claim.reference(),
        "profile_canonical_sha256": production.profile["integrity"][
            "canonical_sha256"
        ],
        "profile_file_sha256": production.profile_file.sha256,
        "profile_evaluated_at": evaluated_at,
        "authorization_confirmation_sha256": controls[
            "authorization_confirmation_sha256"
        ],
        **{key: controls[key] for key in physical._CONTROL_FIELDS},
        "prior_result_file_sha256": prior.result_sha256 if prior else None,
        "prior_finalization_file_sha256": (
            prior.finalization_sha256 if prior else None
        ),
        "start_temperature_c": start_temperature_c,
        "maximum_post_requests": 1,
        "automatic_retry_count": 0,
        "retry_allowed": False,
        "recovery_performed": False,
    }


def _copy_inputs(
    destination: Path,
    context: physical.N3APhysicalContext,
    production: ValidatedProductionProfile,
) -> None:
    review = production.review_artifact_file
    if review is None:
        raise N3APhysicalActionError("production profile lost review artifact")
    payloads = {
        PHYSICAL_PLAN_FILENAME: _canonical(context.plan),
        BINDING_REVIEW_FILENAME: context.binding_review_bytes,
        PHYSICAL_CAMPAIGN_FILENAME: _canonical(production.inputs.campaign),
        FIRMWARE_BINARY_FILENAME: production.inputs.firmware_binary.payload,
        LIMIT_AUTHORITY_FILENAME: production.inputs.limit_authority_file.payload,
        USAGE_EVIDENCE_FILENAME: production.inputs.usage_evidence_file.payload,
        PROFILE_REVIEW_FILENAME: review.payload,
        PRODUCTION_VALIDATION_FILENAME: _canonical(production.report),
    }
    for filename, payload in payloads.items():
        _atomic(destination / filename, payload, unknown=False)


def _unknown(
    destination: Optional[Path],
    base: Mapping[str, Any],
    *,
    audit: Optional[Mapping[str, Any]],
    error: BaseException,
) -> None:
    if destination is None or not destination.is_dir():
        return
    post_count = int(audit.get("post_issued_count", 0) if audit else 0)
    request_audit = (
        dict(audit)
        if audit
        and set(audit) == {"post_attempt_count", "post_issued_count", "calls"}
        else {
            "post_attempt_count": 0,
            "post_issued_count": 0,
            "calls": [],
        }
    )
    evidence = {
        **dict(base),
        "outcome": ResultState.UNKNOWN_DO_NOT_RETRY.value,
        "protocol_verified": False,
        "protocol_evidence": None,
        "request_audit": request_audit,
        "error": {"type": type(error).__name__, "message": str(error)},
    }
    evidence_sha = _write_new(destination, EVIDENCE_FILENAME, evidence)
    result = build_result_record(
        action_identity_sha256=str(base["action_identity_sha256"]),
        state=ResultState.UNKNOWN_DO_NOT_RETRY,
        completed_at=_utc_now(),
        evidence_manifest_sha256=evidence_sha,
        post_request_count=post_count,
        details="physical N3A claim consumed; retry/recovery forbidden",
    )
    _write_new(destination, P0_RESULT_FILENAME, result)


def run_n3a_physical_action_once(
    action_key: str,
    result_dir: Path,
    base_url: str,
    *,
    plan_files: N3APhysicalPlanFiles,
    production_files: N3AProductionFiles,
    evaluated_at: str,
    authorization_confirmation: str,
    panel_plan_confirmation: str,
    profile_confirmation: str,
    start_temperature_c: float,
    primer_result_file: Optional[Path] = None,
    confirm_supervised_supply_cv_current_normal: bool = False,
    confirm_physical_cutoff_available: bool = False,
    confirm_single_visible_refresh: bool = False,
    confirm_controller_fresh_boot: bool = False,
    confirm_map_fidelity_from_primer: bool = False,
    confirm_esp32_not_restarted_since_primer: bool = False,
    confirm_no_j2_disconnect_since_primer: bool = False,
    confirm_no_panel_power_cycle_since_primer: bool = False,
    confirm_no_other_visible_refresh_since_primer: bool = False,
    job_timeout_s: float = _quality.DEFAULT_JOB_TIMEOUT_S,
    poll_interval_s: float = _quality.DEFAULT_POLL_INTERVAL_S,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    try:
        destination = legacy._prepare_result_destination(result_dir)
    except legacy.N3FixedActionError as error:
        raise N3APhysicalActionError(str(error)) from error
    if not isinstance(base_url, str) or not base_url.strip():
        raise N3APhysicalActionError("base_url must be a non-empty device URL")
    description, context, snapshot, production, prior = _prepare(
        action_key,
        plan_files=plan_files,
        production_files=production_files,
        evaluated_at=evaluated_at,
        primer_result_file=primer_result_file,
    )
    if not description["contract_ready"] or production is None:
        raise N3APhysicalActionError(
            "physical N3A contract is not ready: "
            + ", ".join(description["blockers"])
        )
    try:
        start_temp = legacy._temperature(
            start_temperature_c, label="start_temperature_c"
        )
    except legacy.N3FixedActionError as error:
        raise N3APhysicalActionError(str(error)) from error
    live_now = _utc_now()
    try:
        controls = physical.control_fields(
            context,
            snapshot,
            production,
            evaluated_at=evaluated_at,
            live_now=live_now,
        )
    except physical.N3APhysicalExecutionError as error:
        raise N3APhysicalActionError(str(error)) from error
    limits = production.profile["limits"]
    if not limits["minimum_start_temperature_c"] <= start_temp <= limits[
        "maximum_start_temperature_c"
    ]:
        raise N3APhysicalActionError("start temperature is outside reviewed limits")
    confirmations = {
        "reviewed_panel_build_and_exact_plan": True,
        "registered_measurement_assets_present": True,
        "supervised_supply_cv_current_normal": (
            confirm_supervised_supply_cv_current_normal
        ),
        "physical_cutoff_available": confirm_physical_cutoff_available,
        "single_visible_refresh": confirm_single_visible_refresh,
        **(
            {"controller_fresh_boot": confirm_controller_fresh_boot}
            if snapshot.phase == "map-primer"
            else {
                "map_fidelity_from_same_session_primer": (
                    confirm_map_fidelity_from_primer
                ),
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
    if any(value is not True for value in confirmations.values()):
        raise N3APhysicalActionError("all physical confirmations must be true")
    if authorization_confirmation != required_authorization_confirmation(
        context, action_key
    ):
        raise N3APhysicalActionError("exact action authorization is required")
    if panel_plan_confirmation != required_panel_plan_confirmation(context, action_key):
        raise N3APhysicalActionError("exact panel/plan confirmation is required")
    if profile_confirmation != required_production_profile_confirmation(production):
        raise N3APhysicalActionError("exact production-profile confirmation is required")
    attempt_id = uuid.uuid4().hex
    claim = _claim_action(
        context,
        snapshot,
        attempt_id=attempt_id,
        claimed_at=live_now,
        destination=destination,
        production=production,
        prior=prior,
        start_temperature_c=start_temp,
        confirmations=confirmations,
        authorization_confirmation=authorization_confirmation,
        controls=controls,
    )
    base = _base_evidence(
        context,
        snapshot,
        attempt_id=attempt_id,
        claim=claim,
        recorded_at=live_now,
        production=production,
        evaluated_at=evaluated_at,
        prior=prior,
        start_temperature_c=start_temp,
        controls=controls,
    )
    created: Optional[Path] = None
    audit_capture: dict[str, Any] = {}
    audit: Optional[Mapping[str, Any]] = audit_capture
    try:
        destination.mkdir()
        created = destination
        _copy_inputs(destination, context, production)
        _write_new(destination, PROFILE_FILENAME, production.profile)
        lock = {
            "schema_version": SCHEMA_VERSION,
            "kind": frozen.LOCK_KIND,
            "plan_id": context.plan["plan_id"],
            "plan_canonical_sha256": context.plan["integrity"][
                "canonical_sha256"
            ],
            "attempt_id": attempt_id,
            "action_key": action_key,
            "action_identity_sha256": snapshot.action["action_identity_sha256"],
            "claim": claim.reference(),
            "confirmations": confirmations,
            "authorization_confirmation_sha256": controls[
                "authorization_confirmation_sha256"
            ],
            **{key: controls[key] for key in physical._CONTROL_FIELDS},
            "state": "authorization_permanently_consumed_do_not_rerun",
            "automatic_retry_authorized": False,
            "automatic_recovery_authorized": False,
        }
        _write_new(destination, LOCK_FILENAME, lock)
        try:
            protocol, audit = legacy._execute_protocol(
                snapshot,
                prior,
                base_url,
                audit_sink=audit_capture,
                job_timeout_s=job_timeout_s,
                poll_interval_s=poll_interval_s,
                sleeper=sleeper,
                clock=clock,
                target_contract_builder=lambda item: _target_contract(context, item),
                request_function=http_request,
            )
        except legacy.N3FixedActionError as error:
            raise N3APhysicalActionError(str(error)) from error
        evidence = {
            **base,
            "protocol_completed_at": _utc_now(),
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
            _unknown(created, base, audit=audit, error=error)
        except BaseException:
            pass
        raise N3APhysicalActionUnknown(
            "physical N3A action is UNKNOWN_DO_NOT_RETRY; claim is permanent"
        ) from error


def _load_pending(
    result_dir: Path,
    *,
    n2_result_directories: Mapping[str, Path],
    n2_reviewer_key_file: Path,
    profile_reviewer_key_file: Path,
    primer_result_file: Optional[Path],
):
    if not isinstance(result_dir, Path) or not result_dir.is_dir():
        raise N3APhysicalActionError("result_dir must be an existing directory")
    try:
        legacy._fixed._reject_reparse_path_chain(
            result_dir, label="physical N3A result directory"
        )
    except (ValueError, RuntimeError, OSError) as error:
        raise N3APhysicalActionError(str(error)) from error
    for name in (
        OBSERVATION_FILENAME,
        FINALIZATION_FILENAME,
        P0_RESULT_FILENAME,
        SESSION_OBSERVATION_FILENAME,
        CAMERA_CAPTURE_FILENAME,
    ):
        if os.path.lexists(result_dir / name):
            raise N3APhysicalActionError("observation was already finalized")
    context = _context(
        _stored_plan_files(
            result_dir,
            n2_result_directories=n2_result_directories,
            n2_reviewer_key_file=n2_reviewer_key_file,
        )
    )
    evidence, evidence_payload = _strict_json(
        result_dir / EVIDENCE_FILENAME, label="N3A protocol evidence"
    )
    profile, profile_payload = _strict_json(
        result_dir / PROFILE_FILENAME, label="N3A copied profile"
    )
    lock, lock_payload = _strict_json(
        result_dir / LOCK_FILENAME, label="N3A action lock"
    )
    action_key = str(evidence.get("action_key"))
    evaluated_at = evidence.get("profile_evaluated_at")
    if not isinstance(evaluated_at, str) or not evaluated_at:
        raise N3APhysicalActionError("pending evaluation time is invalid")
    production = _production(
        context,
        action_key,
        _stored_production_files(result_dir, profile_reviewer_key_file),
        evaluated_at=evaluated_at,
    )
    validation, validation_payload = _strict_json(
        result_dir / PRODUCTION_VALIDATION_FILENAME,
        label="N3A copied production validation",
    )
    if (
        production.report["production_ready"] is not True
        or validation != production.report
        or _sha256(validation_payload) != _sha256(_canonical(production.report))
        or profile != production.profile
        or _sha256(profile_payload) != production.profile_file.sha256
        or evidence.get("outcome") != "protocol_verified_observation_pending"
        or evidence.get("protocol_verified") is not True
        or evidence.get("request_audit", {}).get("post_issued_count") != 1
        or evidence.get("error") is not None
    ):
        raise N3APhysicalActionError("pending N3A evidence is not finalizable")
    snapshot = physical.load_n3a_physical_action_snapshot(context, action_key)
    claim_reference = evidence.get("claim")
    if not isinstance(claim_reference, Mapping):
        raise N3APhysicalActionError("pending claim reference is missing")
    claim, claim_payload = _strict_json(
        legacy._claim_registry() / str(claim_reference.get("filename")),
        label="N3A workspace-global claim",
    )
    claim_sha = _sha256(claim_payload)
    if claim_reference.get("file_sha256") != claim_sha or lock.get(
        "claim"
    ) != claim_reference:
        raise N3APhysicalActionError("claim/lock binding changed")
    try:
        physical.validate_control_records(
            context,
            snapshot,
            production,
            {"claim": claim, "lock": lock, "evidence": evidence},
        )
    except physical.N3APhysicalExecutionError as error:
        raise N3APhysicalActionError(str(error)) from error
    prior: Optional[_StoredChain] = None
    if snapshot.phase == "target":
        if primer_result_file is None:
            raise N3APhysicalActionError("target finalization requires MAP result")
        prior = _load_stored_chain(
            primer_result_file,
            n2_result_directories=n2_result_directories,
            n2_reviewer_key_file=n2_reviewer_key_file,
            profile_reviewer_key_file=profile_reviewer_key_file,
        )
        if (
            prior.context.plan != context.plan
            or evidence.get("prior_result_file_sha256") != prior.result_sha256
            or evidence.get("prior_finalization_file_sha256")
            != prior.finalization_sha256
        ):
            raise N3APhysicalActionError("pending target prior binding changed")
    elif primer_result_file is not None:
        raise N3APhysicalActionError("MAP finalization must not receive a prior")
    try:
        frozen.validate_n3_protocol_evidence(
            evidence,
            snapshot=snapshot,
            prior_bundle=prior.bundle if prior else None,
        )
    except frozen.N3ExecutionContractError as error:
        raise N3APhysicalActionError(str(error)) from error
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


def _session_observation(
    context: physical.N3APhysicalContext,
    snapshot: frozen.N3ActionSnapshot,
    prior: _StoredChain,
    target: Mapping[str, Any],
) -> dict[str, Any]:
    route = snapshot.route
    plan = physical.validate_n3a_physical_execution_context(context)
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": SESSION_KIND,
        "plan_canonical_sha256": plan["integrity"]["canonical_sha256"],
        "winner_cell_id": plan["selection"]["winner_cell_id"],
        "repeat_count": plan["selection"]["repeat_count"],
        "repeat_ordinal": route["repeat_ordinal"],
        "session_id": route["session_id"],
        "map_action_identity_sha256": prior.validated[
            "action_identity_sha256"
        ],
        "map_result_file_sha256": prior.result_sha256,
        "map_finalization_file_sha256": prior.finalization_sha256,
        "target_action_identity_sha256": target["action_identity_sha256"],
        "target_result_file_sha256": target["result_file_sha256"],
        "target_finalization_file_sha256": target["finalization_file_sha256"],
        "target_state": target["state"],
        "map_target_continuity_deep_validated": True,
        "automatic_inference": False,
    }
    return {
        **unsigned,
        "integrity": {
            "canonical_sha256": _sha256(unsigned),
            "canonical_sha256_scope": (
                "entire physical N3A session observation excluding integrity; "
                "canonical JSON"
            ),
        },
    }


def finalize_n3a_physical_observation(
    result_dir: Path,
    observation_file: Path,
    *,
    n2_result_directories: Mapping[str, Path],
    n2_reviewer_key_file: Path,
    profile_reviewer_key_file: Path,
    primer_result_file: Optional[Path] = None,
) -> dict[str, Any]:
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
        n2_result_directories=n2_result_directories,
        n2_reviewer_key_file=n2_reviewer_key_file,
        profile_reviewer_key_file=profile_reviewer_key_file,
        primer_result_file=primer_result_file,
    )
    source, source_payload = _strict_json(
        observation_file, label="operator N3A observation"
    )
    try:
        observation, camera_payload = legacy._build_stored_observation(
            source,
            source_payload,
            snapshot=snapshot,
            evidence=evidence,
            profile=profile,
            observation_file=observation_file,
        )
    except legacy.N3FixedActionError as error:
        raise N3APhysicalActionError(str(error)) from error
    observation_payload = _canonical(observation)
    observation_sha = _sha256(observation_payload)
    evidence_sha = _sha256(evidence_payload)
    profile_sha = _sha256(profile_payload)
    lock_sha = _sha256(lock_payload)
    state = ResultState(observation["overall_state"])
    finalization = {
        "schema_version": SCHEMA_VERSION,
        "kind": frozen.FINALIZATION_KIND,
        "plan_id": context.plan["plan_id"],
        "plan_canonical_sha256": context.plan["integrity"]["canonical_sha256"],
        "attempt_id": evidence["attempt_id"],
        "action_key": snapshot.key,
        "cell_id": snapshot.cell_id,
        "candidate_cell_id": snapshot.candidate_cell_id,
        "phase": snapshot.phase,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "state": state.value,
        "claim_file_sha256": claim_sha,
        "lock_file_sha256": lock_sha,
        "protocol_evidence_file_sha256": evidence_sha,
        "action_observation_file_sha256": observation_sha,
        "profile_file_sha256": profile_sha,
        "authorization_confirmation_sha256": evidence[
            "authorization_confirmation_sha256"
        ],
        **{key: evidence[key] for key in physical._CONTROL_FIELDS},
        "prior_result_file_sha256": prior.result_sha256 if prior else None,
        "prior_finalization_file_sha256": (
            prior.finalization_sha256 if prior else None
        ),
        "visual_pass": observation["visual_pass"],
        "electrical_pass": observation["electrical_pass"],
        "thermal_pass": observation["thermal_pass"],
        "continuity_pass": observation["continuity_pass"],
        "post_refresh_temperature_c": observation["thermal"]["post_action_c"],
        "session_max_temperature_c": observation["thermal"]["session_max_c"],
        "camera_capture_file_sha256": observation["camera"][
            "capture_file_sha256"
        ],
        "visual_electrical_thermal_continuity_assessed_separately": True,
        "automatic_retry_count": 0,
        "retry_allowed": False,
        "recovery_performed": False,
    }
    finalization_payload = _canonical(finalization)
    finalization_sha = _sha256(finalization_payload)
    result = build_result_record(
        action_identity_sha256=snapshot.action["action_identity_sha256"],
        state=state,
        completed_at=str(observation["observed_at"]),
        evidence_manifest_sha256=finalization_sha,
        post_request_count=1,
        details=(
            "physical N3A separated observation PASS"
            if state is ResultState.PASS
            else "one or more physical N3A observation gates failed"
        ),
    )
    result_payload = _canonical(result)
    bundle = legacy._bundle(
        {
            "claim": claim,
            "lock": lock,
            "profile": profile,
            "evidence": evidence,
            "observation": observation,
            "finalization": finalization,
            "result": result,
        }
    )
    try:
        validated = physical.validate_n3a_physical_finalized_action_bundle(
            context,
            bundle,
            production_profile=production,
            expected_action_key=snapshot.key,
            prior_bundle=prior.bundle if prior else None,
            prior_production_profile=prior.production if prior else None,
        )
    except physical.N3APhysicalExecutionError as error:
        raise N3APhysicalActionError(str(error)) from error
    session_payload: Optional[bytes] = None
    session_sha: Optional[str] = None
    if snapshot.phase == "target":
        if prior is None:  # pragma: no cover
            raise N3APhysicalActionError("target lost its MAP chain")
        session = _session_observation(context, snapshot, prior, validated)
        session_payload = _canonical(session)
        session_sha = _sha256(session_payload)
    if camera_payload is not None:
        _atomic(result_dir / CAMERA_CAPTURE_FILENAME, camera_payload, unknown=False)
    for filename, payload in (
        (OBSERVATION_FILENAME, observation_payload),
        (FINALIZATION_FILENAME, finalization_payload),
        (P0_RESULT_FILENAME, result_payload),
    ):
        _atomic(result_dir / filename, payload, unknown=False)
    if session_payload is not None:
        _atomic(
            result_dir / SESSION_OBSERVATION_FILENAME,
            session_payload,
            unknown=False,
        )
    return {
        **validated,
        "camera_capture_present": camera_payload is not None,
        "session_observation_file": (
            SESSION_OBSERVATION_FILENAME if session_payload is not None else None
        ),
        "session_observation_file_sha256": session_sha,
        "session_observation_written": session_payload is not None,
    }


def _positive(value: str) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be numeric") from error
    if not math.isfinite(number) or not number > 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return number


def _nonnegative(value: str) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be numeric") from error
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return number


def _n2_directories(values: Sequence[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        key, separator, path = value.partition("=")
        if not separator or key in result or key not in n2_analyzer.EXPECTED_RESULT_KEYS:
            raise argparse.ArgumentTypeError(
                "--n2-result must be one unique exact ACTION_KEY=PATH"
            )
        result[key] = Path(path)
    if set(result) != set(n2_analyzer.EXPECTED_RESULT_KEYS):
        raise argparse.ArgumentTypeError("exactly eight --n2-result values are required")
    return result


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--action")
    parser.add_argument("--describe-only", action="store_true")
    parser.add_argument("--finalize-observation", action="store_true")
    parser.add_argument("--validate-result", action="store_true")
    parser.add_argument("--physical-plan", type=Path)
    parser.add_argument("--binding-review-artifact", type=Path)
    parser.add_argument("--minimum-interval-seconds", type=_positive)
    parser.add_argument("--planned-cooldown-seconds", type=_nonnegative)
    parser.add_argument("--n2-result", action="append", default=[])
    parser.add_argument("--n2-reviewer-key", type=Path)
    parser.add_argument("--limit-profile", type=Path)
    parser.add_argument("--physical-campaign", type=Path)
    parser.add_argument("--firmware-binary", type=Path)
    parser.add_argument(
        "--limit-authority", "--supplier-limits", dest="limit_authority", type=Path
    )
    parser.add_argument("--usage-evidence", type=Path)
    parser.add_argument("--profile-review-artifact", type=Path)
    parser.add_argument("--profile-reviewer-key", type=Path)
    parser.add_argument("--evaluated-at")
    parser.add_argument("--result-dir", type=Path)
    parser.add_argument("--result-file", type=Path)
    parser.add_argument("--observation-file", type=Path)
    parser.add_argument("--primer-result", type=Path)
    parser.add_argument("--url")
    parser.add_argument("--confirm")
    parser.add_argument("--confirm-panel-plan")
    parser.add_argument("--confirm-profile")
    parser.add_argument("--start-temperature-c", type=float)
    parser.add_argument("--confirm-supervised-supply-cv-current-normal", action="store_true")
    parser.add_argument("--confirm-physical-cutoff-available", action="store_true")
    parser.add_argument("--confirm-single-visible-refresh", action="store_true")
    parser.add_argument("--confirm-controller-fresh-boot", action="store_true")
    parser.add_argument("--confirm-map-fidelity-from-primer", action="store_true")
    parser.add_argument("--confirm-esp32-not-restarted-since-primer", action="store_true")
    parser.add_argument("--confirm-no-j2-disconnect-since-primer", action="store_true")
    parser.add_argument("--confirm-no-panel-power-cycle-since-primer", action="store_true")
    parser.add_argument("--confirm-no-other-visible-refresh-since-primer", action="store_true")
    args = parser.parse_args(argv)
    try:
        args.n2_result_directories = _n2_directories(args.n2_result)
    except argparse.ArgumentTypeError as error:
        parser.error(str(error))
    if not args.n2_reviewer_key:
        parser.error("--n2-reviewer-key is required")
    modes = sum(
        bool(value)
        for value in (args.describe_only, args.finalize_observation, args.validate_result)
    )
    if modes > 1:
        parser.error("describe, finalize, validate modes are mutually exclusive")
    if args.finalize_observation:
        if not all(
            (args.result_dir, args.observation_file, args.profile_reviewer_key)
        ):
            parser.error("finalize requires result-dir, observation, profile reviewer key")
        return args
    if args.validate_result:
        if not all((args.result_file, args.profile_reviewer_key)):
            parser.error("validate requires result-file and profile reviewer key")
        return args
    required_plan = {
        "--action": args.action,
        "--physical-plan": args.physical_plan,
        "--binding-review-artifact": args.binding_review_artifact,
        "--minimum-interval-seconds": args.minimum_interval_seconds,
        "--planned-cooldown-seconds": args.planned_cooldown_seconds,
    }
    missing = [name for name, value in required_plan.items() if value is None]
    if missing:
        parser.error("action mode requires " + ", ".join(missing))
    production_values = {
        "--limit-profile": args.limit_profile,
        "--physical-campaign": args.physical_campaign,
        "--firmware-binary": args.firmware_binary,
        "--limit-authority": args.limit_authority,
        "--usage-evidence": args.usage_evidence,
        "--profile-review-artifact": args.profile_review_artifact,
        "--profile-reviewer-key": args.profile_reviewer_key,
    }
    present = [name for name, value in production_values.items() if value is not None]
    if present and len(present) != len(production_values):
        parser.error("deep production inputs are all-or-none")
    if args.describe_only:
        return args
    missing = [name for name, value in production_values.items() if value is None]
    live = {
        "--evaluated-at": args.evaluated_at,
        "--result-dir": args.result_dir,
        "--url": args.url,
        "--confirm": args.confirm,
        "--confirm-panel-plan": args.confirm_panel_plan,
        "--confirm-profile": args.confirm_profile,
        "--start-temperature-c": args.start_temperature_c,
    }
    missing.extend(name for name, value in live.items() if value is None)
    if missing:
        parser.error("live execution requires " + ", ".join(missing))
    return args


def _plan_files(args: argparse.Namespace) -> N3APhysicalPlanFiles:
    return N3APhysicalPlanFiles(
        plan=args.physical_plan,
        binding_review_artifact=args.binding_review_artifact,
        minimum_interval_seconds=args.minimum_interval_seconds,
        planned_cooldown_seconds=args.planned_cooldown_seconds,
        n2_result_directories=args.n2_result_directories,
        n2_reviewer_key=args.n2_reviewer_key,
    )


def _production_files(args: argparse.Namespace) -> N3AProductionFiles:
    return N3AProductionFiles(
        profile=args.limit_profile,
        physical_campaign=args.physical_campaign,
        firmware_binary=args.firmware_binary,
        limit_authority=args.limit_authority,
        usage_evidence=args.usage_evidence,
        review_artifact=args.profile_review_artifact,
        reviewer_key=args.profile_reviewer_key,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.finalize_observation:
            value = finalize_n3a_physical_observation(
                args.result_dir,
                args.observation_file,
                n2_result_directories=args.n2_result_directories,
                n2_reviewer_key_file=args.n2_reviewer_key,
                profile_reviewer_key_file=args.profile_reviewer_key,
                primer_result_file=args.primer_result,
            )
        elif args.validate_result:
            value = load_n3a_physical_finalized_action_bundle(
                args.result_file,
                n2_result_directories=args.n2_result_directories,
                n2_reviewer_key_file=args.n2_reviewer_key,
                profile_reviewer_key_file=args.profile_reviewer_key,
                primer_result_file=args.primer_result,
            )
        elif args.describe_only:
            value = describe_n3a_physical_action(
                args.action,
                plan_files=_plan_files(args),
                production_files=(
                    _production_files(args) if args.limit_profile else None
                ),
                evaluated_at=args.evaluated_at,
                primer_result_file=args.primer_result,
            )
        else:
            value = run_n3a_physical_action_once(
                args.action,
                args.result_dir,
                args.url,
                plan_files=_plan_files(args),
                production_files=_production_files(args),
                evaluated_at=args.evaluated_at,
                authorization_confirmation=args.confirm,
                panel_plan_confirmation=args.confirm_panel_plan,
                profile_confirmation=args.confirm_profile,
                start_temperature_c=args.start_temperature_c,
                primer_result_file=args.primer_result,
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
            )
    except (N3APhysicalActionError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BINDING_REVIEW_FILENAME",
    "DESCRIPTION_KIND",
    "FIRMWARE_BINARY_FILENAME",
    "LIMIT_AUTHORITY_FILENAME",
    "N3APhysicalActionError",
    "N3APhysicalActionUnknown",
    "N3APhysicalPlanFiles",
    "N3AProductionFiles",
    "PHYSICAL_CAMPAIGN_FILENAME",
    "PHYSICAL_PLAN_FILENAME",
    "PRODUCTION_VALIDATION_FILENAME",
    "PROFILE_REVIEW_FILENAME",
    "SESSION_KIND",
    "SUPPLIER_LIMITS_FILENAME",
    "USAGE_EVIDENCE_FILENAME",
    "describe_n3a_physical_action",
    "finalize_n3a_physical_observation",
    "load_n3a_physical_finalized_action_bundle",
    "load_n3a_physical_finalized_action_chain",
    "main",
    "parse_args",
    "required_authorization_confirmation",
    "required_panel_plan_confirmation",
    "required_production_profile_confirmation",
    "run_n3a_physical_action_once",
]
