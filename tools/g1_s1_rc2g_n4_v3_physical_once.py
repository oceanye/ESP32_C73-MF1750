#!/usr/bin/env python3
"""Describe, execute, finalize, and replay one physical-bound N4 V3 action.

Every live invocation replays the physical campaign lineage and authenticates
the exact campaign, firmware binary, truthful limit authority, usage snapshot,
review artifact, and trusted reviewer key before it can create a global claim.  The
claim is permanent and precedes all network I/O.  Exactly one POST is allowed;
there is no retry, recovery, firmware upload, or power-control path.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
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
from tools import g1_s1_n4_v3_execution_contract as frozen  # noqa: E402
from tools import g1_s1_n4_v3_physical_execution as physical  # noqa: E402
from tools import g1_s1_rc2g_n4_v3_once as legacy  # noqa: E402
from tools import g1_s1_rc2g_quality_refresh_once as _quality  # noqa: E402


SCHEMA_VERSION = 1
RUNNER_KIND = "mf1750-g1-s1-rc2g-n4-v3-physical-fixed-action-runner"
DESCRIPTION_KIND = "mf1750-g1-s1-rc2g-n4-v3-physical-action-description"
CELL_OBSERVATION_KIND = "mf1750-g1-s1-n4-v3-physical-cell-observation"
AUTHORIZATION_PREFIX = physical.AUTHORIZATION_PREFIX
AUTHORIZATION_SUFFIX = physical.AUTHORIZATION_SUFFIX

LOCK_FILENAME = legacy.LOCK_FILENAME
PROFILE_FILENAME = legacy.PROFILE_FILENAME
EVIDENCE_FILENAME = legacy.EVIDENCE_FILENAME
OBSERVATION_FILENAME = legacy.OBSERVATION_FILENAME
FINALIZATION_FILENAME = legacy.FINALIZATION_FILENAME
P0_RESULT_FILENAME = legacy.P0_RESULT_FILENAME
CELL_OBSERVATION_FILENAME = legacy.CELL_OBSERVATION_FILENAME
CAMERA_CAPTURE_FILENAME = legacy.CAMERA_CAPTURE_FILENAME

PHYSICAL_CONTRACT_FILENAME = "N4-V3-PHYSICAL-EXECUTION-CONTRACT.json"
PHYSICAL_REBIND_FILENAME = "N4-V3-PHYSICAL-REBIND.json"
PHYSICAL_CAMPAIGN_FILENAME = "PHYSICAL-CAMPAIGN.json"
PHYSICAL_ANCHOR_FILENAME = "N2-PHYSICAL-ANCHOR-CAMPAIGN.json"
BINDING_REVIEW_FILENAME = "PHYSICAL-BINDING-REVIEW.bin"
FIRMWARE_BINARY_FILENAME = "FIRMWARE.bin"
LIMIT_AUTHORITY_FILENAME = "LIMIT-AUTHORITY.json"
# Compatibility name for callers importing the old constant.  New bundles
# always persist the neutral LIMIT-AUTHORITY.json filename.
SUPPLIER_LIMITS_FILENAME = LIMIT_AUTHORITY_FILENAME
USAGE_EVIDENCE_FILENAME = "USAGE-EVIDENCE.json"
PROFILE_REVIEW_FILENAME = "PROFILE-REVIEW.json"
PRODUCTION_VALIDATION_FILENAME = "PRODUCTION-PROFILE-VALIDATION.json"

http_request = legacy.http_request


class N4PhysicalActionError(RuntimeError):
    """The physical action was rejected before its permanent claim existed."""


class N4PhysicalActionUnknown(N4PhysicalActionError):
    """The physical action claim exists; retry and recovery are forbidden."""


@dataclass(frozen=True)
class N4PhysicalBindingFiles:
    rebind_manifest: Path
    physical_campaign: Path
    physical_anchor_campaign: Path
    binding_review_artifact: Path
    minimum_interval_seconds: float
    planned_cooldown_seconds: float


@dataclass(frozen=True)
class N4ProductionFiles:
    profile: Path
    firmware_binary: Path
    limit_authority: Path
    usage_evidence: Path
    review_artifact: Path
    reviewer_key: Path

    @property
    def supplier_limits(self) -> Path:
        """Compatibility alias for the neutral limit-authority input."""

        return self.limit_authority


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
            "action_identity_sha256": self.record["action_identity_sha256"],
            "state": self.record["state"],
        }


@dataclass(frozen=True)
class _StoredChain:
    context: physical.N4PhysicalContext
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


def _sha256(payload: bytes) -> str:
    return frozen._sha256(payload)


def _canonical(value: Any) -> bytes:
    try:
        return canonical_json_bytes(value)
    except CampaignContractError as error:
        raise N4PhysicalActionError(f"canonical JSON failed: {error}") from error


def _utc_now() -> str:
    return legacy._utc_now()


def _translate(error: BaseException) -> N4PhysicalActionError:
    return N4PhysicalActionError(str(error))


def _atomic_commit(path: Path, payload: bytes, *, unknown_after_commit: bool) -> None:
    try:
        legacy._atomic_commit(
            path, payload, unknown_after_commit=unknown_after_commit
        )
    except legacy.N4V3FixedActionUnknown as error:
        raise N4PhysicalActionUnknown(str(error)) from error
    except legacy.N4V3FixedActionError as error:
        if unknown_after_commit:
            raise N4PhysicalActionUnknown(str(error)) from error
        raise _translate(error) from error


def _write_new(directory: Path, filename: str, value: Mapping[str, Any]) -> str:
    payload = _canonical(value)
    _atomic_commit(directory / filename, payload, unknown_after_commit=False)
    return _sha256(payload)


def _strict_json_file(path: Path, *, label: str) -> tuple[Mapping[str, Any], bytes]:
    try:
        return legacy._strict_json_file(path, label=label)
    except legacy.N4V3FixedActionError as error:
        raise _translate(error) from error


def _safe_regular_file(path: Path, *, label: str) -> Path:
    try:
        return legacy._safe_regular_file(path, label=label)
    except legacy.N4V3FixedActionError as error:
        raise _translate(error) from error


def _prepare_result_destination(path: Path) -> Path:
    try:
        return legacy._prepare_result_destination(path)
    except legacy.N4V3FixedActionError as error:
        raise _translate(error) from error


def _temperature(value: object, *, label: str) -> float:
    try:
        return legacy._temperature(value, label=label)
    except legacy.N4V3FixedActionError as error:
        raise _translate(error) from error


def _rfc3339(value: object, *, label: str):
    try:
        return legacy._rfc3339(value, label=label)
    except legacy.N4V3FixedActionError as error:
        raise _translate(error) from error


def _load_context(files: N4PhysicalBindingFiles) -> physical.N4PhysicalContext:
    try:
        return physical.load_n4_physical_execution_context(
            rebind_manifest_file=files.rebind_manifest,
            physical_campaign_file=files.physical_campaign,
            physical_anchor_campaign_file=files.physical_anchor_campaign,
            binding_review_artifact_file=files.binding_review_artifact,
            minimum_interval_seconds=files.minimum_interval_seconds,
            planned_cooldown_seconds=files.planned_cooldown_seconds,
        )
    except physical.N4PhysicalExecutionError as error:
        raise N4PhysicalActionError(str(error)) from error


def _load_production(
    context: physical.N4PhysicalContext,
    binding: N4PhysicalBindingFiles,
    production: N4ProductionFiles,
    *,
    evaluated_at: str,
) -> ValidatedProductionProfile:
    try:
        return physical.load_n4_physical_production_profile(
            context,
            profile_file=production.profile,
            campaign_file=binding.physical_campaign,
            firmware_binary_file=production.firmware_binary,
            limit_authority_file=production.limit_authority,
            usage_evidence_file=production.usage_evidence,
            review_artifact_file=production.review_artifact,
            reviewer_key_file=production.reviewer_key,
            evaluated_at=evaluated_at,
        )
    except physical.N4PhysicalExecutionError as error:
        raise N4PhysicalActionError(str(error)) from error


def required_authorization_confirmation(
    context: physical.N4PhysicalContext, action_key: str
) -> str:
    try:
        snapshot = physical.load_n4_physical_action_snapshot(context, action_key)
    except physical.N4PhysicalExecutionError as error:
        raise N4PhysicalActionError(str(error)) from error
    return (
        f"{AUTHORIZATION_PREFIX}"
        f"{snapshot.action['action_identity_sha256'].upper()}"
        f"{AUTHORIZATION_SUFFIX}"
    )


def authorization_confirmation_sha256(
    context: physical.N4PhysicalContext, action_key: str
) -> str:
    return _sha256(required_authorization_confirmation(context, action_key).encode("ascii"))


def required_panel_build_confirmation(
    context: physical.N4PhysicalContext,
) -> str:
    try:
        return physical.required_n4_physical_panel_build_confirmation(
            str(context.physical_campaign["panel"]["serial"]),
            str(context.physical_campaign["firmware"]["build_tag"]),
            str(context.rebind_manifest["binding"]["canonical_sha256"]),
        )
    except physical.N4PhysicalExecutionError as error:
        raise N4PhysicalActionError(str(error)) from error


def required_production_profile_confirmation(
    production: ValidatedProductionProfile,
) -> str:
    try:
        return physical.required_n4_physical_production_profile_confirmation(
            production
        )
    except physical.N4PhysicalExecutionError as error:
        raise N4PhysicalActionError(str(error)) from error


def _target_contract(
    context: physical.N4PhysicalContext,
    snapshot: frozen.N4V3ActionSnapshot,
) -> _quality._RunContract:
    try:
        contract = frozen.build_n4_v3_target_protocol_contract(snapshot)
    except frozen.N4V3ExecutionContractError as error:
        raise N4PhysicalActionError(str(error)) from error
    return _quality._RunContract(
        **{
            **contract.__dict__,
            "required_authorization_confirmation": (
                required_authorization_confirmation(context, snapshot.key)
            ),
        }
    )


def _stored_binding_files(directory: Path) -> N4PhysicalBindingFiles:
    manifest, _payload = _strict_json_file(
        directory / PHYSICAL_REBIND_FILENAME,
        label="stored N4 physical rebind manifest",
    )
    schedule = manifest.get("binding", {}).get("reviewed_schedule", {})
    return N4PhysicalBindingFiles(
        rebind_manifest=directory / PHYSICAL_REBIND_FILENAME,
        physical_campaign=directory / PHYSICAL_CAMPAIGN_FILENAME,
        physical_anchor_campaign=directory / PHYSICAL_ANCHOR_FILENAME,
        binding_review_artifact=directory / BINDING_REVIEW_FILENAME,
        minimum_interval_seconds=schedule.get("minimum_interval_seconds"),
        planned_cooldown_seconds=schedule.get("planned_cooldown_seconds"),
    )


def _stored_production_files(directory: Path, reviewer_key: Path) -> N4ProductionFiles:
    return N4ProductionFiles(
        profile=directory / PROFILE_FILENAME,
        firmware_binary=directory / FIRMWARE_BINARY_FILENAME,
        limit_authority=directory / LIMIT_AUTHORITY_FILENAME,
        usage_evidence=directory / USAGE_EVIDENCE_FILENAME,
        review_artifact=directory / PROFILE_REVIEW_FILENAME,
        reviewer_key=reviewer_key,
    )


def _load_stored_chain(
    result_file: Path,
    *,
    reviewer_key_file: Path,
    prior_result_file: Optional[Path] = None,
) -> _StoredChain:
    resolved = _safe_regular_file(result_file, label="physical N4 P0 result")
    if resolved.name != P0_RESULT_FILENAME:
        raise N4PhysicalActionError(
            f"physical N4 result filename must be {P0_RESULT_FILENAME}"
        )
    directory = resolved.parent
    context = _load_context(_stored_binding_files(directory))
    stored_contract, contract_payload = _strict_json_file(
        directory / PHYSICAL_CONTRACT_FILENAME,
        label="stored N4 physical execution contract",
    )
    if (
        stored_contract != context.contract
        or _sha256(contract_payload)
        != physical.n4_physical_execution_contract_file_sha256(context.contract)
    ):
        raise N4PhysicalActionError("stored physical execution contract changed")
    try:
        bundle = legacy._load_bundle_from_result_file(resolved)
    except legacy.N4V3FixedActionError as error:
        raise N4PhysicalActionError(str(error)) from error
    evidence = bundle["evidence"]
    evaluated_at = evidence.get("profile_evaluated_at")
    if not isinstance(evaluated_at, str) or not evaluated_at:
        raise N4PhysicalActionError("stored profile evaluation time is invalid")
    production = _load_production(
        context,
        _stored_binding_files(directory),
        _stored_production_files(directory, reviewer_key_file),
        evaluated_at=evaluated_at,
    )
    validation_record, validation_payload = _strict_json_file(
        directory / PRODUCTION_VALIDATION_FILENAME,
        label="stored deep production validation",
    )
    if (
        validation_record != production.report
        or _sha256(validation_payload) != _sha256(_canonical(production.report))
    ):
        raise N4PhysicalActionError("stored deep production validation changed")
    snapshot = physical.load_n4_physical_action_snapshot(
        context, str(evidence.get("action_key"))
    )
    prior: Optional[_StoredChain] = None
    if snapshot.phase == "target":
        if prior_result_file is None:
            raise N4PhysicalActionError(
                "physical N4 target validation requires its MAP result"
            )
        prior = _load_stored_chain(
            prior_result_file, reviewer_key_file=reviewer_key_file
        )
        if prior.context.contract != context.contract:
            raise N4PhysicalActionError("target and MAP physical contexts differ")
    elif prior_result_file is not None:
        raise N4PhysicalActionError("MAP validation must not receive a prior result")
    try:
        validated = physical.validate_n4_physical_finalized_action_bundle(
            context,
            bundle,
            production_profile=production,
            expected_action_key=snapshot.key,
            prior_bundle=prior.bundle if prior else None,
            prior_production_profile=prior.production if prior else None,
        )
    except physical.N4PhysicalExecutionError as error:
        raise N4PhysicalActionError(str(error)) from error
    return _StoredChain(context, production, bundle, validated)


def load_n4_v3_physical_finalized_action_bundle(
    result_file: Path,
    *,
    reviewer_key_file: Path,
    primer_result_file: Optional[Path] = None,
) -> dict[str, Any]:
    """Replay stored bytes and authenticated inputs without network/device I/O."""

    chain = _load_stored_chain(
        result_file,
        reviewer_key_file=reviewer_key_file,
        prior_result_file=primer_result_file,
    )
    return dict(chain.validated)


def load_n4_v3_physical_finalized_action_chain(
    result_file: Path,
    *,
    reviewer_key_file: Path,
    primer_result_file: Optional[Path] = None,
) -> _StoredChain:
    """Return the deeply replayed bundle/profile/context for offline analyzers."""

    return _load_stored_chain(
        result_file,
        reviewer_key_file=reviewer_key_file,
        prior_result_file=primer_result_file,
    )


def _prepare(
    action_key: str,
    *,
    binding_files: N4PhysicalBindingFiles,
    production_files: Optional[N4ProductionFiles],
    evaluated_at: Optional[str],
    primer_result_file: Optional[Path],
) -> tuple[
    dict[str, Any],
    physical.N4PhysicalContext,
    frozen.N4V3ActionSnapshot,
    Optional[ValidatedProductionProfile],
    Optional[_StoredChain],
]:
    context = _load_context(binding_files)
    try:
        snapshot = physical.load_n4_physical_action_snapshot(context, action_key)
    except physical.N4PhysicalExecutionError as error:
        raise N4PhysicalActionError(str(error)) from error
    blockers: list[str] = []
    production: Optional[ValidatedProductionProfile] = None
    prior: Optional[_StoredChain] = None
    p0_description: Optional[Mapping[str, Any]] = None
    if production_files is None:
        blockers.append("deep_production_profile_inputs_missing")
    if evaluated_at is None:
        blockers.append("explicit_evaluated_at_missing")
    if snapshot.phase == "target" and primer_result_file is None:
        blockers.append("same_cell_canonical_pass_map_bundle_missing")
    if snapshot.phase == "map-primer" and primer_result_file is not None:
        raise N4PhysicalActionError("MAP-primer must not receive a prior result")
    if primer_result_file is not None:
        reviewer_key = (
            production_files.reviewer_key if production_files is not None else None
        )
        if reviewer_key is None:
            blockers.append("prior_deep_reviewer_key_missing")
        else:
            prior = _load_stored_chain(
                primer_result_file, reviewer_key_file=reviewer_key
            )
            expected_prior = snapshot.action["identity"]["prior"][
                "action_identity_sha256"
            ]
            if (
                prior.context.contract != context.contract
                or prior.validated["action_identity_sha256"] != expected_prior
                or prior.validated["state"] != ResultState.PASS.value
            ):
                raise N4PhysicalActionError(
                    "same-cell MAP bundle is cross-context, cross-cell, or not PASS"
                )
    if production_files is not None and evaluated_at is not None:
        production = _load_production(
            context,
            binding_files,
            production_files,
            evaluated_at=evaluated_at,
        )
        if production.report["production_ready"] is not True:
            blockers.extend(production.report["reasons"])
            blockers.append("deep_production_profile_not_ready")
        try:
            p0_description = describe_action_offline(
                context.physical_campaign,
                action_identity_sha256=snapshot.action["action_identity_sha256"],
                limit_profile=production.profile,
                evaluated_at=evaluated_at,
                prior_result=prior.result if prior else None,
                prior_result_sha256=prior.result_sha256 if prior else None,
            )
        except CampaignContractError as error:
            raise N4PhysicalActionError(
                f"physical P0 description failed: {error}"
            ) from error
        blockers.extend(
            blocker
            for blocker in p0_description["blockers"]
            if blocker
            != "current_runtime_gates_and_exact_authorization_not_evaluated"
        )
        if snapshot.phase == "target" and prior is not None:
            try:
                physical.validate_n4_physical_target_usage_continuity(
                    production, prior.result
                )
            except physical.N4PhysicalExecutionError as error:
                raise N4PhysicalActionError(str(error)) from error
    blockers = list(dict.fromkeys(blockers))
    description = {
        "schema_version": SCHEMA_VERSION,
        "kind": DESCRIPTION_KIND,
        "mode": "describe-only",
        "action_key": action_key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "cell_id": snapshot.cell_id,
        "phase": snapshot.phase,
        "physical_execution_contract_canonical_sha256": context.contract[
            "integrity"
        ]["canonical_sha256"],
        "physical_execution_contract_file_sha256": (
            physical.n4_physical_execution_contract_file_sha256(context.contract)
        ),
        "physical_rebind_canonical_sha256": context.rebind_manifest["integrity"][
            "canonical_sha256"
        ],
        "p0_campaign_canonical_sha256": context.physical_campaign["integrity"][
            "canonical_sha256"
        ],
        "frame": dict(snapshot.action["identity"]["frame"]),
        "reference_preview": dict(snapshot.reference_preview),
        "profile_validation": dict(production.report) if production else None,
        "prior_result_file_sha256": prior.result_sha256 if prior else None,
        "prior_finalization_file_sha256": (
            prior.finalization_sha256 if prior else None
        ),
        "p0_description": dict(p0_description) if p0_description else None,
        "contract_ready": bool(
            production
            and production.report["production_ready"] is True
            and p0_description
            and p0_description["contract_ready"]
            and not blockers
        ),
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "required_authorization_confirmation_sha256": (
            authorization_confirmation_sha256(context, action_key)
        ),
        "required_panel_build_confirmation_sha256": _sha256(
            required_panel_build_confirmation(context).encode("utf-8")
        ),
        "required_profile_confirmation_sha256": (
            _sha256(
                required_production_profile_confirmation(production).encode("utf-8")
            )
            if production is not None
            else None
        ),
        "maximum_live_evaluation_age_seconds": (
            physical.MAX_LIVE_EVALUATED_AT_AGE_SECONDS
        ),
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "maximum_post_requests": 1,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "blockers": blockers,
    }
    return description, context, snapshot, production, prior


def describe_n4_v3_physical_action(
    action_key: str,
    *,
    binding_files: N4PhysicalBindingFiles,
    production_files: Optional[N4ProductionFiles] = None,
    evaluated_at: Optional[str] = None,
    primer_result_file: Optional[Path] = None,
) -> dict[str, Any]:
    description, _context, _snapshot, _production, _prior = _prepare(
        action_key,
        binding_files=binding_files,
        production_files=production_files,
        evaluated_at=evaluated_at,
        primer_result_file=primer_result_file,
    )
    return description


def _claim_action(
    context: physical.N4PhysicalContext,
    snapshot: frozen.N4V3ActionSnapshot,
    *,
    attempt_id: str,
    claimed_at: str,
    destination: Path,
    production: ValidatedProductionProfile,
    prior: Optional[_StoredChain],
    start_temperature_c: float,
    confirmations: Mapping[str, bool],
    authorization_confirmation: str,
    control_fields: Mapping[str, Any],
) -> _Claim:
    declaration = snapshot.action["claim"]
    if (
        declaration["registry_id"] != CLAIM_REGISTRY_ID
        or declaration["filename"]
        != f"{snapshot.action['action_identity_sha256']}.json"
        or declaration["create_before_network"] is not True
        or declaration["overridable"] is not False
        or declaration["partitioned_by_campaign_id"] is not False
    ):
        raise N4PhysicalActionError("physical workspace-global claim changed")
    try:
        registry = legacy._claim_registry()
    except legacy.N4V3FixedActionError as error:
        raise N4PhysicalActionError(str(error)) from error
    if legacy._fixed._is_within(destination, registry):
        raise N4PhysicalActionError("result directory must not overlap claim registry")
    record = {
        "schema_version": SCHEMA_VERSION,
        "kind": frozen.CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "execution_contract_canonical_sha256": context.contract["integrity"][
            "canonical_sha256"
        ],
        "p0_campaign_canonical_sha256": context.contract[
            "p0_campaign_canonical_sha256"
        ],
        "attempt_id": attempt_id,
        "claimed_at": claimed_at,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "authorization_consumed_permanently": True,
        "authorization_confirmation_sha256": _sha256(
            authorization_confirmation.encode("ascii")
        ),
        **{key: control_fields[key] for key in physical._CONTROL_FIELDS},
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
    _atomic_commit(
        registry / declaration["filename"], payload, unknown_after_commit=True
    )
    return _Claim(record, _sha256(payload))


def _base_evidence(
    context: physical.N4PhysicalContext,
    snapshot: frozen.N4V3ActionSnapshot,
    *,
    attempt_id: str,
    claim: _Claim,
    recorded_at: str,
    production: ValidatedProductionProfile,
    evaluated_at: str,
    prior: Optional[_StoredChain],
    start_temperature_c: float,
    control_fields: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": frozen.EVIDENCE_KIND,
        # The shared deep stored validator currently fixes this generic N4
        # record kind.  Physical identity is the execution-contract SHA below.
        "runner_kind": frozen.RUNNER_KIND,
        "attempt_id": attempt_id,
        "recorded_at": recorded_at,
        "action_key": snapshot.key,
        "cell_id": snapshot.cell_id,
        "phase": snapshot.phase,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "execution_contract_canonical_sha256": context.contract["integrity"][
            "canonical_sha256"
        ],
        "execution_contract_file_sha256": (
            physical.n4_physical_execution_contract_file_sha256(context.contract)
        ),
        "p0_campaign_canonical_sha256": context.contract[
            "p0_campaign_canonical_sha256"
        ],
        "source_manifest_canonical_sha256": context.contract["source_v3"][
            "manifest_canonical_sha256"
        ],
        "source_proof_canonical_sha256": context.contract["source_v3"][
            "proof_canonical_sha256"
        ],
        "frame_sha256": snapshot.action["identity"]["frame"]["sha256"],
        "reference_preview": dict(snapshot.reference_preview),
        "claim": claim.reference(),
        "profile_canonical_sha256": production.profile["integrity"][
            "canonical_sha256"
        ],
        "profile_file_sha256": production.profile_file.sha256,
        "profile_evaluated_at": evaluated_at,
        "authorization_confirmation_sha256": control_fields[
            "authorization_confirmation_sha256"
        ],
        **{key: control_fields[key] for key in physical._CONTROL_FIELDS},
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


def _copy_execution_inputs(
    destination: Path,
    context: physical.N4PhysicalContext,
    production: ValidatedProductionProfile,
) -> None:
    review = production.review_artifact_file
    if review is None:
        raise N4PhysicalActionError("production-ready profile lost its review artifact")
    payloads = {
        PHYSICAL_CONTRACT_FILENAME: _canonical(context.contract),
        PHYSICAL_REBIND_FILENAME: _canonical(context.rebind_manifest),
        PHYSICAL_CAMPAIGN_FILENAME: _canonical(context.physical_campaign),
        PHYSICAL_ANCHOR_FILENAME: _canonical(context.physical_anchor_campaign),
        BINDING_REVIEW_FILENAME: context.binding_review_bytes,
        FIRMWARE_BINARY_FILENAME: production.inputs.firmware_binary.payload,
        LIMIT_AUTHORITY_FILENAME: production.inputs.limit_authority_file.payload,
        USAGE_EVIDENCE_FILENAME: production.inputs.usage_evidence_file.payload,
        PROFILE_REVIEW_FILENAME: review.payload,
        PRODUCTION_VALIDATION_FILENAME: _canonical(production.report),
    }
    for filename, payload in payloads.items():
        _atomic_commit(
            destination / filename, payload, unknown_after_commit=False
        )


def _record_unknown(
    destination: Optional[Path],
    base: Mapping[str, Any],
    *,
    requester_audit: Optional[Mapping[str, Any]],
    error: BaseException,
) -> None:
    if destination is None or not destination.is_dir():
        return
    post_count = int(
        requester_audit.get("post_issued_count", 0) if requester_audit else 0
    )
    evidence = {
        **dict(base),
        "outcome": ResultState.UNKNOWN_DO_NOT_RETRY.value,
        "protocol_verified": False,
        "protocol_completed_at": None,
        "protocol_evidence": None,
        "request_audit": dict(requester_audit) if requester_audit else None,
        "error": {"type": type(error).__name__, "message": str(error)},
    }
    evidence_sha = _write_new(destination, EVIDENCE_FILENAME, evidence)
    result = build_result_record(
        action_identity_sha256=str(base["action_identity_sha256"]),
        state=ResultState.UNKNOWN_DO_NOT_RETRY,
        completed_at=_utc_now(),
        evidence_manifest_sha256=evidence_sha,
        post_request_count=post_count,
        details="physical claim consumed; no retry or recovery is permitted",
    )
    _write_new(destination, P0_RESULT_FILENAME, result)


def run_n4_v3_physical_action_once(
    action_key: str,
    result_dir: Path,
    base_url: str,
    *,
    binding_files: N4PhysicalBindingFiles,
    production_files: N4ProductionFiles,
    evaluated_at: str,
    authorization_confirmation: str,
    panel_build_confirmation: str,
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
    """Consume one new physical claim and issue exactly one visible POST."""

    destination = _prepare_result_destination(result_dir)
    if not isinstance(base_url, str) or not base_url.strip():
        raise N4PhysicalActionError("base_url must be a non-empty device root URL")
    description, context, snapshot, production, prior = _prepare(
        action_key,
        binding_files=binding_files,
        production_files=production_files,
        evaluated_at=evaluated_at,
        primer_result_file=primer_result_file,
    )
    if not description["contract_ready"] or production is None:
        raise N4PhysicalActionError(
            "physical N4 contract is not ready: "
            + ", ".join(description["blockers"])
        )
    start_temp = _temperature(start_temperature_c, label="start_temperature_c")
    live_now = _utc_now()
    try:
        control_fields = physical.n4_physical_control_fields(
            context,
            snapshot,
            production,
            evaluated_at=evaluated_at,
            live_now=live_now,
        )
    except physical.N4PhysicalExecutionError as error:
        raise N4PhysicalActionError(str(error)) from error
    limits = production.profile["limits"]
    if not limits["minimum_start_temperature_c"] <= start_temp <= limits[
        "maximum_start_temperature_c"
    ]:
        raise N4PhysicalActionError("start temperature is outside reviewed limits")
    common_confirmations = {
        # Derived from authenticated artifact validation; no caller boolean can
        # substitute for this gate.
        "reviewed_panel_and_build": production.report["production_ready"] is True,
        "supervised_supply_cv_current_normal": (
            confirm_supervised_supply_cv_current_normal
        ),
        "physical_cutoff_available": confirm_physical_cutoff_available,
        "single_visible_refresh": confirm_single_visible_refresh,
    }
    phase_confirmations = (
        {"controller_fresh_boot": confirm_controller_fresh_boot}
        if snapshot.phase == "map-primer"
        else {
            "map_fidelity_from_same_cell_primer": confirm_map_fidelity_from_primer,
            "esp32_not_restarted_since_primer": (
                confirm_esp32_not_restarted_since_primer
            ),
            "no_j2_disconnect_since_primer": confirm_no_j2_disconnect_since_primer,
            "no_panel_power_cycle_since_primer": (
                confirm_no_panel_power_cycle_since_primer
            ),
            "no_other_visible_refresh_since_primer": (
                confirm_no_other_visible_refresh_since_primer
            ),
        }
    )
    confirmations = {**common_confirmations, **phase_confirmations}
    if any(type(value) is not bool or value is not True for value in confirmations.values()):
        raise N4PhysicalActionError(
            "all physical action confirmations must be true"
        )
    expected_confirmation = required_authorization_confirmation(context, action_key)
    if authorization_confirmation != expected_confirmation:
        raise N4PhysicalActionError(
            "exact physical N4 action authorization confirmation is required"
        )
    if panel_build_confirmation != required_panel_build_confirmation(context):
        raise N4PhysicalActionError(
            "exact physical panel/build/binding confirmation is required"
        )
    if profile_confirmation != required_production_profile_confirmation(production):
        raise N4PhysicalActionError(
            "exact approved production-profile confirmation is required"
        )

    attempt_id = uuid.uuid4().hex
    claimed_at = live_now
    claim = _claim_action(
        context,
        snapshot,
        attempt_id=attempt_id,
        claimed_at=claimed_at,
        destination=destination,
        production=production,
        prior=prior,
        start_temperature_c=start_temp,
        confirmations=confirmations,
        authorization_confirmation=authorization_confirmation,
        control_fields=control_fields,
    )
    created_destination: Optional[Path] = None
    audit_capture: dict[str, Any] = {}
    requester_audit: Optional[Mapping[str, Any]] = audit_capture
    base = _base_evidence(
        context,
        snapshot,
        attempt_id=attempt_id,
        claim=claim,
        recorded_at=claimed_at,
        production=production,
        evaluated_at=evaluated_at,
        prior=prior,
        start_temperature_c=start_temp,
        control_fields=control_fields,
    )
    try:
        destination.mkdir()
        created_destination = destination
        _copy_execution_inputs(destination, context, production)
        _write_new(destination, PROFILE_FILENAME, production.profile)
        _write_new(
            destination,
            LOCK_FILENAME,
            {
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
                "confirmations": confirmations,
                "authorization_confirmation_sha256": (
                    authorization_confirmation_sha256(context, action_key)
                ),
                **{key: control_fields[key] for key in physical._CONTROL_FIELDS},
                "state": "authorization_permanently_consumed_do_not_rerun",
                "automatic_retry_authorized": False,
                "automatic_recovery_authorized": False,
            },
        )
        protocol, requester_audit = legacy._execute_protocol(
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
        evidence = {
            **base,
            "outcome": "protocol_verified_observation_pending",
            "protocol_verified": True,
            "protocol_completed_at": _utc_now(),
            "protocol_evidence": dict(protocol),
            "request_audit": dict(requester_audit),
            "error": None,
        }
        _write_new(destination, EVIDENCE_FILENAME, evidence)
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
        raise N4PhysicalActionUnknown(
            "physical N4 action is UNKNOWN_DO_NOT_RETRY; claim is permanent"
        ) from error


def _load_pending(
    result_dir: Path,
    *,
    reviewer_key_file: Path,
    primer_result_file: Optional[Path],
) -> tuple[
    physical.N4PhysicalContext,
    frozen.N4V3ActionSnapshot,
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
        raise N4PhysicalActionError("result_dir must be pathlib.Path")
    try:
        legacy._reject_reparse_path_chain(
            result_dir, label="physical N4 result directory"
        )
    except legacy.N4V3FixedActionError as error:
        raise N4PhysicalActionError(str(error)) from error
    if not result_dir.is_dir() or result_dir.is_symlink():
        raise N4PhysicalActionError("result_dir must be an existing regular directory")
    for name in (
        OBSERVATION_FILENAME,
        FINALIZATION_FILENAME,
        P0_RESULT_FILENAME,
        CELL_OBSERVATION_FILENAME,
    ):
        if os.path.lexists(result_dir / name):
            raise N4PhysicalActionError("physical observation was already finalized")
    context = _load_context(_stored_binding_files(result_dir))
    contract, contract_payload = _strict_json_file(
        result_dir / PHYSICAL_CONTRACT_FILENAME,
        label="stored physical execution contract",
    )
    if contract != context.contract:
        raise N4PhysicalActionError("stored physical execution contract changed")
    evidence, evidence_payload = _strict_json_file(
        result_dir / EVIDENCE_FILENAME, label="physical N4 protocol evidence"
    )
    profile, profile_payload = _strict_json_file(
        result_dir / PROFILE_FILENAME, label="copied reviewed profile"
    )
    lock, lock_payload = _strict_json_file(
        result_dir / LOCK_FILENAME, label="physical N4 action lock"
    )
    evaluated_at = evidence.get("profile_evaluated_at")
    if not isinstance(evaluated_at, str) or not evaluated_at:
        raise N4PhysicalActionError("pending profile evaluation time is invalid")
    production = _load_production(
        context,
        _stored_binding_files(result_dir),
        _stored_production_files(result_dir, reviewer_key_file),
        evaluated_at=evaluated_at,
    )
    if (
        production.report["production_ready"] is not True
        or profile != production.profile
        or _sha256(profile_payload) != production.profile_file.sha256
        or evidence.get("kind") != frozen.EVIDENCE_KIND
        or evidence.get("outcome") != "protocol_verified_observation_pending"
        or evidence.get("protocol_verified") is not True
        or evidence.get("profile_file_sha256") != production.profile_file.sha256
        or evidence.get("profile_canonical_sha256")
        != production.profile["integrity"]["canonical_sha256"]
        or evidence.get("request_audit", {}).get("post_issued_count") != 1
        or evidence.get("error") is not None
    ):
        raise N4PhysicalActionError("physical N4 evidence is not finalizable")
    try:
        claim, claim_sha = legacy._claim_record_from_reference(evidence.get("claim"))
    except legacy.N4V3FixedActionError as error:
        raise N4PhysicalActionError(str(error)) from error
    if lock.get("claim") != evidence.get("claim"):
        raise N4PhysicalActionError("physical lock/claim binding changed")
    action_key = evidence.get("action_key")
    try:
        snapshot = physical.load_n4_physical_action_snapshot(context, str(action_key))
    except physical.N4PhysicalExecutionError as error:
        raise N4PhysicalActionError(str(error)) from error
    if evidence.get("action_identity_sha256") != snapshot.action[
        "action_identity_sha256"
    ]:
        raise N4PhysicalActionError("pending physical action binding changed")
    try:
        physical.validate_n4_physical_control_records(
            context,
            snapshot,
            production,
            {"claim": claim, "lock": lock, "evidence": evidence},
        )
    except physical.N4PhysicalExecutionError as error:
        raise N4PhysicalActionError(str(error)) from error
    prior: Optional[_StoredChain] = None
    if snapshot.phase == "target":
        if primer_result_file is None:
            raise N4PhysicalActionError(
                "target finalization requires its physical MAP result"
            )
        prior = _load_stored_chain(
            primer_result_file, reviewer_key_file=reviewer_key_file
        )
        if (
            prior.context.contract != context.contract
            or evidence.get("prior_result_file_sha256") != prior.result_sha256
            or evidence.get("prior_finalization_file_sha256")
            != prior.finalization_sha256
        ):
            raise N4PhysicalActionError("target pending prior binding changed")
    elif primer_result_file is not None:
        raise N4PhysicalActionError("MAP finalization must not receive a prior")
    try:
        frozen.validate_n4_v3_protocol_evidence(
            evidence,
            snapshot=snapshot,
            prior_bundle=prior.bundle if prior else None,
        )
    except frozen.N4V3ExecutionContractError as error:
        raise N4PhysicalActionError(
            f"stored physical protocol replay failed: {error}"
        ) from error
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


def _physical_cell_observation(
    context: physical.N4PhysicalContext,
    snapshot: frozen.N4V3ActionSnapshot,
    prior: _StoredChain,
    target_validated: Mapping[str, Any],
) -> dict[str, Any]:
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": CELL_OBSERVATION_KIND,
        "physical_execution_contract_canonical_sha256": context.contract[
            "integrity"
        ]["canonical_sha256"],
        "cell_id": snapshot.cell_id,
        "map_action_identity_sha256": prior.validated[
            "action_identity_sha256"
        ],
        "map_result_file_sha256": prior.result_sha256,
        "map_finalization_file_sha256": prior.finalization_sha256,
        "target_action_identity_sha256": target_validated[
            "action_identity_sha256"
        ],
        "target_result_file_sha256": target_validated["result_file_sha256"],
        "target_finalization_file_sha256": target_validated[
            "finalization_file_sha256"
        ],
        "target_state": target_validated["state"],
        "map_and_target_deep_validated": True,
        "automatic_inference": False,
    }
    return {
        **unsigned,
        "integrity": {
            "canonical_sha256": _sha256(_canonical(unsigned)),
            "canonical_sha256_scope": (
                "entire physical N4 cell observation excluding integrity; "
                "canonical JSON"
            ),
        },
    }


def finalize_n4_v3_physical_observation(
    result_dir: Path,
    observation_file: Path,
    *,
    reviewer_key_file: Path,
    primer_result_file: Optional[Path] = None,
) -> dict[str, Any]:
    """Seal one manual observation after replaying all stored evidence bytes."""

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
        primer_result_file=primer_result_file,
    )
    source_observation, source_payload = _strict_json_file(
        observation_file, label="operator physical N4 observation"
    )
    try:
        observation, camera_payload = legacy._build_stored_observation(
            source_observation,
            source_payload,
            snapshot=snapshot,
            contract=context.contract,
            evidence=evidence,
            profile=profile,
            observation_file=observation_file,
        )
    except legacy.N4V3FixedActionError as error:
        raise N4PhysicalActionError(str(error)) from error
    observation_payload = _canonical(observation)
    observation_sha = _sha256(observation_payload)
    evidence_sha = _sha256(evidence_payload)
    profile_sha = _sha256(profile_payload)
    lock_sha = _sha256(lock_payload)
    state = ResultState(observation["overall_state"])
    finalization = {
        "schema_version": SCHEMA_VERSION,
        "kind": frozen.FINALIZATION_KIND,
        "execution_contract_canonical_sha256": context.contract["integrity"][
            "canonical_sha256"
        ],
        "attempt_id": evidence["attempt_id"],
        "action_key": snapshot.key,
        "cell_id": snapshot.cell_id,
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
        "visual_electrical_thermal_assessed_separately": True,
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
            "physical visual/electrical/thermal/continuity PASS recorded"
            if state is ResultState.PASS
            else "one or more separated physical observation gates failed"
        ),
    )
    result_payload = _canonical(result)
    result_sha = _sha256(result_payload)
    bundle = legacy._bundle(
        claim=claim,
        claim_sha=claim_sha,
        lock=lock,
        lock_sha=lock_sha,
        profile=profile,
        profile_sha=profile_sha,
        evidence=evidence,
        evidence_sha=evidence_sha,
        observation=observation,
        observation_sha=observation_sha,
        finalization=finalization,
        finalization_sha=finalization_sha,
        result=result,
        result_sha=result_sha,
    )
    try:
        validated = physical.validate_n4_physical_finalized_action_bundle(
            context,
            bundle,
            production_profile=production,
            expected_action_key=snapshot.key,
            prior_bundle=prior.bundle if prior else None,
            prior_production_profile=prior.production if prior else None,
        )
    except physical.N4PhysicalExecutionError as error:
        raise N4PhysicalActionError(
            f"refusing invalid physical finalized bundle: {error}"
        ) from error
    cell_payload: Optional[bytes] = None
    cell_sha: Optional[str] = None
    if snapshot.phase == "target":
        if prior is None:  # pragma: no cover - guarded above
            raise N4PhysicalActionError("target lost its MAP chain")
        cell = _physical_cell_observation(context, snapshot, prior, validated)
        cell_payload = _canonical(cell)
        cell_sha = _sha256(cell_payload)
    if camera_payload is not None:
        _atomic_commit(
            result_dir / CAMERA_CAPTURE_FILENAME,
            camera_payload,
            unknown_after_commit=False,
        )
    _atomic_commit(
        result_dir / OBSERVATION_FILENAME,
        observation_payload,
        unknown_after_commit=False,
    )
    _atomic_commit(
        result_dir / FINALIZATION_FILENAME,
        finalization_payload,
        unknown_after_commit=False,
    )
    _atomic_commit(
        result_dir / P0_RESULT_FILENAME,
        result_payload,
        unknown_after_commit=False,
    )
    if cell_payload is not None:
        _atomic_commit(
            result_dir / CELL_OBSERVATION_FILENAME,
            cell_payload,
            unknown_after_commit=False,
        )
    return {
        **validated,
        "camera_capture_present": camera_payload is not None,
        "cell_observation_file": (
            CELL_OBSERVATION_FILENAME if cell_payload is not None else None
        ),
        "cell_observation_file_sha256": cell_sha,
        "cell_observation_written": cell_payload is not None,
    }


def _binding_from_args(args: argparse.Namespace) -> N4PhysicalBindingFiles:
    return N4PhysicalBindingFiles(
        rebind_manifest=args.rebind_manifest,
        physical_campaign=args.physical_campaign,
        physical_anchor_campaign=args.physical_anchor_campaign,
        binding_review_artifact=args.binding_review_artifact,
        minimum_interval_seconds=args.minimum_interval_seconds,
        planned_cooldown_seconds=args.planned_cooldown_seconds,
    )


def _production_from_args(args: argparse.Namespace) -> N4ProductionFiles:
    return N4ProductionFiles(
        profile=args.limit_profile,
        firmware_binary=args.firmware_binary,
        limit_authority=args.limit_authority,
        usage_evidence=args.usage_evidence,
        review_artifact=args.profile_review_artifact,
        reviewer_key=args.reviewer_key,
    )


def _add_binding_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--rebind-manifest", type=Path)
    parser.add_argument("--physical-campaign", type=Path)
    parser.add_argument("--physical-anchor-campaign", type=Path)
    parser.add_argument("--binding-review-artifact", type=Path)
    parser.add_argument("--minimum-interval-seconds", type=_positive_interval_argument)
    parser.add_argument("--planned-cooldown-seconds", type=_cooldown_argument)


def _add_production_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--limit-profile", type=Path)
    parser.add_argument("--firmware-binary", type=Path)
    parser.add_argument(
        "--limit-authority",
        "--supplier-limits",
        dest="limit_authority",
        type=Path,
    )
    parser.add_argument("--usage-evidence", type=Path)
    parser.add_argument("--profile-review-artifact", type=Path)
    parser.add_argument("--reviewer-key", type=Path)


def _float_argument(value: str) -> float:
    try:
        return _temperature(float(value), label="temperature")
    except (ValueError, N4PhysicalActionError) as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _positive_interval_argument(value: str) -> float:
    result = _float_argument(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("minimum interval must be positive")
    return result


def _cooldown_argument(value: str) -> float:
    result = _float_argument(value)
    if result < 0:
        raise argparse.ArgumentTypeError("planned cooldown must be non-negative")
    return result


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--action", choices=frozen.FIXED_ACTION_KEYS)
    parser.add_argument("--describe-only", action="store_true")
    parser.add_argument("--finalize-observation", action="store_true")
    parser.add_argument("--validate-result", action="store_true")
    parser.add_argument("--result-dir", type=Path)
    parser.add_argument("--result-file", type=Path)
    parser.add_argument("--observation-file", type=Path)
    parser.add_argument("--primer-result", type=Path)
    parser.add_argument("--evaluated-at")
    parser.add_argument("--url")
    parser.add_argument("--confirm")
    parser.add_argument("--confirm-panel-build")
    parser.add_argument("--confirm-profile")
    parser.add_argument("--start-temperature-c", type=_float_argument)
    parser.add_argument(
        "--confirm-supervised-supply-cv-current-normal", action="store_true"
    )
    parser.add_argument("--confirm-physical-cutoff-available", action="store_true")
    parser.add_argument("--confirm-single-visible-refresh", action="store_true")
    parser.add_argument("--confirm-controller-fresh-boot", action="store_true")
    parser.add_argument("--confirm-map-fidelity-from-primer", action="store_true")
    parser.add_argument(
        "--confirm-esp32-not-restarted-since-primer", action="store_true"
    )
    parser.add_argument("--confirm-no-j2-disconnect-since-primer", action="store_true")
    parser.add_argument(
        "--confirm-no-panel-power-cycle-since-primer", action="store_true"
    )
    parser.add_argument(
        "--confirm-no-other-visible-refresh-since-primer", action="store_true"
    )
    _add_binding_args(parser)
    # Validation/finalization load production copies from the result directory.
    _add_production_args(parser)
    args = parser.parse_args(argv)
    modes = sum(
        bool(value)
        for value in (
            args.describe_only,
            args.finalize_observation,
            args.validate_result,
        )
    )
    if modes > 1:
        parser.error("describe, finalize, and validate modes are mutually exclusive")
    if args.finalize_observation:
        if args.result_dir is None or args.observation_file is None or args.reviewer_key is None:
            parser.error(
                "finalization requires --result-dir, --observation-file, and --reviewer-key"
            )
        return args
    if args.validate_result:
        if args.result_file is None or args.reviewer_key is None:
            parser.error("validation requires --result-file and --reviewer-key")
        return args
    if args.action is None:
        parser.error("--action is required")
    binding_required = {
        "--rebind-manifest": args.rebind_manifest,
        "--physical-campaign": args.physical_campaign,
        "--physical-anchor-campaign": args.physical_anchor_campaign,
        "--binding-review-artifact": args.binding_review_artifact,
        "--minimum-interval-seconds": args.minimum_interval_seconds,
        "--planned-cooldown-seconds": args.planned_cooldown_seconds,
    }
    missing_binding = [
        name for name, value in binding_required.items() if value is None
    ]
    if missing_binding:
        parser.error("action description/execution requires " + ", ".join(missing_binding))
    production_values = {
        "--limit-profile": args.limit_profile,
        "--firmware-binary": args.firmware_binary,
        "--limit-authority": args.limit_authority,
        "--usage-evidence": args.usage_evidence,
        "--profile-review-artifact": args.profile_review_artifact,
        "--reviewer-key": args.reviewer_key,
    }
    present_production = [
        name for name, value in production_values.items() if value is not None
    ]
    if present_production and len(present_production) != len(production_values):
        parser.error("deep production inputs are all-or-none")
    if args.describe_only:
        return args
    missing_production = [
        name for name, value in production_values.items() if value is None
    ]
    if missing_production:
        parser.error("live execution requires " + ", ".join(missing_production))
    required = {
        "--evaluated-at": args.evaluated_at,
        "--result-dir": args.result_dir,
        "--url": args.url,
        "--confirm": args.confirm,
        "--confirm-panel-build": args.confirm_panel_build,
        "--confirm-profile": args.confirm_profile,
        "--start-temperature-c": args.start_temperature_c,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        parser.error("live execution requires " + ", ".join(missing))
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.finalize_observation:
            result = finalize_n4_v3_physical_observation(
                args.result_dir,
                args.observation_file,
                reviewer_key_file=args.reviewer_key,
                primer_result_file=args.primer_result,
            )
        elif args.validate_result:
            result = load_n4_v3_physical_finalized_action_bundle(
                args.result_file,
                reviewer_key_file=args.reviewer_key,
                primer_result_file=args.primer_result,
            )
        else:
            binding = _binding_from_args(args)
            production = (
                _production_from_args(args) if args.limit_profile is not None else None
            )
            if args.describe_only:
                result = describe_n4_v3_physical_action(
                    args.action,
                    binding_files=binding,
                    production_files=production,
                    evaluated_at=args.evaluated_at,
                    primer_result_file=args.primer_result,
                )
            else:
                result = run_n4_v3_physical_action_once(
                    args.action,
                    args.result_dir,
                    args.url,
                    binding_files=binding,
                    production_files=production,
                    evaluated_at=args.evaluated_at,
                    authorization_confirmation=args.confirm,
                    panel_build_confirmation=args.confirm_panel_build,
                    profile_confirmation=args.confirm_profile,
                    start_temperature_c=args.start_temperature_c,
                    primer_result_file=args.primer_result,
                    confirm_supervised_supply_cv_current_normal=(
                        args.confirm_supervised_supply_cv_current_normal
                    ),
                    confirm_physical_cutoff_available=(
                        args.confirm_physical_cutoff_available
                    ),
                    confirm_single_visible_refresh=(
                        args.confirm_single_visible_refresh
                    ),
                    confirm_controller_fresh_boot=args.confirm_controller_fresh_boot,
                    confirm_map_fidelity_from_primer=(
                        args.confirm_map_fidelity_from_primer
                    ),
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
    except N4PhysicalActionUnknown as error:
        print(f"UNKNOWN_DO_NOT_RETRY: {error}", file=sys.stderr)
        return 3
    except N4PhysicalActionError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "N4PhysicalActionError",
    "N4PhysicalActionUnknown",
    "N4PhysicalBindingFiles",
    "N4ProductionFiles",
    "authorization_confirmation_sha256",
    "describe_n4_v3_physical_action",
    "finalize_n4_v3_physical_observation",
    "load_n4_v3_physical_finalized_action_bundle",
    "load_n4_v3_physical_finalized_action_chain",
    "main",
    "parse_args",
    "required_authorization_confirmation",
    "run_n4_v3_physical_action_once",
]
