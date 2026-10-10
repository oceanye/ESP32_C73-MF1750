#!/usr/bin/env python3
"""Execute or finalize one of eight frozen N4 V3 RC2G actions exactly once.

Only ``--action`` selects identity, and its choices are the four V3 cells'
MAP-primer/target pairs.  Frame bytes, hashes, jobs, sessions, manifest, proof,
and campaign cannot be overridden.  A workspace-global claim is committed
before network I/O; after that point every failure is terminal
``UNKNOWN_DO_NOT_RETRY``.  The runner never controls J2 or any power switch.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable, Mapping, Optional, Sequence
import uuid

from PIL import Image, UnidentifiedImageError


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.visible_refresh_campaign import (  # noqa: E402
    CLAIM_REGISTRY_ID,
    CampaignContractError,
    ResultState,
    build_result_record,
    canonical_json_bytes,
    describe_action_offline,
    validate_limit_profile,
)
from tools import g1_s1_n4_v3_execution_contract as execution  # noqa: E402
from tools import g1_s1_rc2g_map_baseline_once as _map  # noqa: E402
from tools import g1_s1_rc2g_n2_photo_campaign_once as _fixed  # noqa: E402
from tools import g1_s1_rc2g_quality_refresh_once as _quality  # noqa: E402


SCHEMA_VERSION = execution.SCHEMA_VERSION
RUNNER_KIND = execution.RUNNER_KIND
CLAIM_KIND = execution.CLAIM_KIND
LOCK_KIND = execution.LOCK_KIND
EVIDENCE_KIND = execution.EVIDENCE_KIND
OBSERVATION_KIND = execution.OBSERVATION_KIND
FINALIZATION_KIND = execution.FINALIZATION_KIND
BUNDLE_KIND = execution.BUNDLE_KIND

LOCK_FILENAME = execution.LOCK_FILENAME
PROFILE_FILENAME = execution.PROFILE_FILENAME
EVIDENCE_FILENAME = execution.EVIDENCE_FILENAME
OBSERVATION_FILENAME = execution.OBSERVATION_FILENAME
FINALIZATION_FILENAME = execution.FINALIZATION_FILENAME
P0_RESULT_FILENAME = execution.P0_RESULT_FILENAME
CELL_OBSERVATION_FILENAME = execution.CELL_OBSERVATION_FILENAME
CAMERA_CAPTURE_FILENAME = "N4-V3-CAMERA-CAPTURE.bin"
OPERATOR_OBSERVATION_KIND = "mf1750-g1-s1-rc2g-n4-v3-operator-observation-input"

FIXED_ACTION_SHA256S = execution.FIXED_ACTION_SHA256S
FIXED_ACTION_KEYS = execution.FIXED_ACTION_KEYS
AUTHORIZATION_PREFIX = execution.AUTHORIZATION_PREFIX
AUTHORIZATION_SUFFIX = execution.AUTHORIZATION_SUFFIX
http_request = _quality.http_request


class N4V3FixedActionError(RuntimeError):
    """The selected action was rejected before its permanent claim existed."""


class N4V3FixedActionUnknown(N4V3FixedActionError):
    """The action claim exists; retry and recovery are forbidden."""


def _require_deep_production_profile_path() -> None:
    """Disable the legacy shape-only profile path before claim or network I/O."""

    raise N4V3FixedActionError(
        "legacy N4 V3 live execution is disabled: a deep production profile "
        "and physical-bound campaign are required"
    )


@dataclass(frozen=True)
class _Claim:
    registry: Path
    filename: str
    record: Mapping[str, Any]
    file_sha256: str

    def reference(self) -> dict[str, Any]:
        return {
            "registry_id": CLAIM_REGISTRY_ID,
            "filename": self.filename,
            "file_sha256": self.file_sha256,
            "attempt_id": self.record["attempt_id"],
            "action_identity_sha256": self.record["action_identity_sha256"],
            "state": self.record["state"],
        }


@dataclass(frozen=True)
class _PriorBundle:
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


def _canonical_json(value: Any) -> bytes:
    try:
        return canonical_json_bytes(value)
    except CampaignContractError as error:
        raise N4V3FixedActionError(f"canonical JSON encoding failed: {error}") from error


def _sha256(payload: bytes) -> str:
    return execution._sha256(payload)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _translate_fixed_error(error: BaseException) -> N4V3FixedActionError:
    return N4V3FixedActionError(str(error))


def _strict_json_file(
    path: Path, *, label: str, allow_single_trailing_lf: bool = False
) -> tuple[Mapping[str, Any], bytes]:
    try:
        return _fixed._strict_json_file(
            path,
            label=label,
            allow_single_trailing_lf=allow_single_trailing_lf,
        )
    except _fixed.N2PFixedActionError as error:
        raise _translate_fixed_error(error) from error


def _reject_reparse_path_chain(path: Path, *, label: str) -> None:
    try:
        _fixed._reject_reparse_path_chain(path, label=label)
    except _fixed.N2PFixedActionError as error:
        raise _translate_fixed_error(error) from error


def _safe_regular_file(path: Path, *, label: str) -> Path:
    try:
        return _fixed._safe_regular_file(path, label=label)
    except _fixed.N2PFixedActionError as error:
        raise _translate_fixed_error(error) from error


def _prepare_result_destination(path: Path) -> Path:
    try:
        return _fixed._prepare_result_destination(path)
    except _fixed.N2PFixedActionError as error:
        raise _translate_fixed_error(error) from error


def _claim_registry() -> Path:
    try:
        return _fixed._claim_registry()
    except _fixed.N2PFixedActionError as error:
        raise _translate_fixed_error(error) from error


def _atomic_commit(path: Path, payload: bytes, *, unknown_after_commit: bool) -> None:
    try:
        _fixed._atomic_commit(
            path, payload, unknown_after_commit=unknown_after_commit
        )
    except _fixed.N2PFixedActionUnknown as error:
        raise N4V3FixedActionUnknown(str(error)) from error
    except _fixed.N2PFixedActionError as error:
        if unknown_after_commit:
            raise N4V3FixedActionUnknown(str(error)) from error
        raise _translate_fixed_error(error) from error


def _write_new(directory: Path, filename: str, value: Mapping[str, Any]) -> str:
    payload = _canonical_json(value)
    _atomic_commit(directory / filename, payload, unknown_after_commit=False)
    return _sha256(payload)


def _temperature(value: object, *, label: str) -> float:
    try:
        return _fixed._temperature(value, label=label)
    except _fixed.N2PFixedActionError as error:
        raise _translate_fixed_error(error) from error


def _rfc3339(value: object, *, label: str) -> datetime:
    try:
        return _fixed._rfc3339(value, label=label)
    except _fixed.N2PFixedActionError as error:
        raise _translate_fixed_error(error) from error


def _require_keys(value: object, keys: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise N4V3FixedActionError(f"{label} fields differ from the frozen contract")
    return value


def _require_sha256(value: object, *, label: str, nullable: bool = False) -> Optional[str]:
    try:
        return execution._require_sha256(value, label=label, nullable=nullable)
    except execution.N4V3ExecutionContractError as error:
        raise N4V3FixedActionError(str(error)) from error


def required_authorization_confirmation(action_key: str) -> str:
    try:
        action_sha = FIXED_ACTION_SHA256S[action_key]
    except KeyError as error:
        raise N4V3FixedActionError(
            "action_key is not one of the eight frozen N4 V3 actions"
        ) from error
    return f"{AUTHORIZATION_PREFIX}{action_sha.upper()}{AUTHORIZATION_SUFFIX}"


def authorization_confirmation_sha256(action_key: str) -> str:
    return _sha256(required_authorization_confirmation(action_key).encode("ascii"))


def _execution_contract() -> Mapping[str, Any]:
    try:
        return execution.compile_n4_v3_execution_contract()
    except execution.N4V3ExecutionContractError as error:
        raise N4V3FixedActionError(str(error)) from error


def _snapshot(action_key: str) -> execution.N4V3ActionSnapshot:
    try:
        return execution.load_n4_v3_action_snapshot(action_key)
    except execution.N4V3ExecutionContractError as error:
        raise N4V3FixedActionError(str(error)) from error


def _load_profile(path: Path) -> tuple[Mapping[str, Any], str]:
    profile, payload = _strict_json_file(path, label="reviewed N4 V3 limit profile")
    try:
        validate_limit_profile(profile)
    except CampaignContractError as error:
        raise N4V3FixedActionError(f"reviewed limit profile is invalid: {error}") from error
    return profile, _sha256(payload)


def _claim_record_from_reference(reference: object) -> tuple[Mapping[str, Any], str]:
    root = _require_keys(
        reference,
        {
            "registry_id",
            "filename",
            "file_sha256",
            "attempt_id",
            "action_identity_sha256",
            "state",
        },
        label="N4 V3 consumed claim reference",
    )
    action_sha = _require_sha256(
        root["action_identity_sha256"], label="claim action identity"
    )
    expected_filename = f"{action_sha}.json"
    if (
        root["registry_id"] != CLAIM_REGISTRY_ID
        or root["filename"] != expected_filename
        or root["state"] != "authorization_permanently_consumed_do_not_rerun"
    ):
        raise N4V3FixedActionError("N4 V3 consumed claim reference changed")
    declared_sha = _require_sha256(root["file_sha256"], label="claim file")
    claim, payload = _strict_json_file(
        _claim_registry() / expected_filename,
        label="N4 V3 workspace-global consumed claim",
    )
    if _sha256(payload) != declared_sha:
        raise N4V3FixedActionError("N4 V3 consumed claim file SHA changed")
    return claim, declared_sha


def _load_bundle_from_result_file(result_file: Path) -> Mapping[str, Any]:
    directory = result_file.parent
    names = {
        "lock": LOCK_FILENAME,
        "profile": PROFILE_FILENAME,
        "evidence": EVIDENCE_FILENAME,
        "observation": OBSERVATION_FILENAME,
        "finalization": FINALIZATION_FILENAME,
        "result": P0_RESULT_FILENAME,
    }
    records: dict[str, Mapping[str, Any]] = {}
    hashes: dict[str, str] = {}
    resolved_result = _safe_regular_file(result_file, label="same-cell MAP P0 result")
    if resolved_result.name != P0_RESULT_FILENAME:
        raise N4V3FixedActionError(
            f"same-cell MAP result filename must be {P0_RESULT_FILENAME}"
        )
    for key, filename in names.items():
        record, payload = _strict_json_file(
            directory / filename, label=f"same-cell MAP {key}"
        )
        records[key] = record
        hashes[key] = _sha256(payload)
    claim, claim_sha = _claim_record_from_reference(records["evidence"].get("claim"))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": BUNDLE_KIND,
        "claim": claim,
        "claim_file_sha256": claim_sha,
        "lock": records["lock"],
        "lock_file_sha256": hashes["lock"],
        "profile": records["profile"],
        "profile_file_sha256": hashes["profile"],
        "evidence": records["evidence"],
        "evidence_file_sha256": hashes["evidence"],
        "observation": records["observation"],
        "observation_file_sha256": hashes["observation"],
        "finalization": records["finalization"],
        "finalization_file_sha256": hashes["finalization"],
        "result": records["result"],
        "result_file_sha256": hashes["result"],
    }


def _load_prior_bundle(
    result_file: Path, snapshot: execution.N4V3ActionSnapshot
) -> _PriorBundle:
    if snapshot.phase != "target":
        raise N4V3FixedActionError("only a target action may bind a MAP result")
    bundle = _load_bundle_from_result_file(result_file)
    contract = _execution_contract()
    try:
        validated = execution.validate_n4_v3_finalized_action_bundle(
            contract,
            bundle,
            expected_action_key=f"{snapshot.cell_id}-map-primer",
        )
    except execution.N4V3ExecutionContractError as error:
        raise N4V3FixedActionError(f"same-cell MAP bundle is invalid: {error}") from error
    expected_prior = snapshot.action["identity"]["prior"]["action_identity_sha256"]
    if (
        validated["action_identity_sha256"] != expected_prior
        or validated["state"] != ResultState.PASS.value
    ):
        raise N4V3FixedActionError("same-cell MAP bundle is cross-cell or not PASS")
    return _PriorBundle(bundle=bundle, validated=validated)


def _prepare_fixed_inputs(
    snapshot: execution.N4V3ActionSnapshot,
    *,
    limit_profile_file: Optional[Path],
    evaluated_at: Optional[str],
    primer_result_file: Optional[Path],
) -> tuple[dict[str, Any], Optional[Mapping[str, Any]], Optional[str], Optional[_PriorBundle]]:
    contract = _execution_contract()
    blockers: list[str] = []
    profile: Optional[Mapping[str, Any]] = None
    profile_sha: Optional[str] = None
    prior: Optional[_PriorBundle] = None
    p0_description: Optional[Mapping[str, Any]] = None
    if limit_profile_file is None:
        blockers.append("reviewed_limit_profile_missing")
    if evaluated_at is None:
        blockers.append("explicit_evaluated_at_missing")
    if snapshot.phase == "target" and primer_result_file is None:
        blockers.append("same_cell_canonical_pass_map_bundle_missing")
    if snapshot.phase == "map-primer" and primer_result_file is not None:
        raise N4V3FixedActionError("MAP-primer must not receive a prior result")
    if primer_result_file is not None:
        prior = _load_prior_bundle(primer_result_file, snapshot)
    if limit_profile_file is not None and evaluated_at is not None:
        profile, profile_sha = _load_profile(limit_profile_file)
        try:
            p0_description = describe_action_offline(
                snapshot.campaign,
                action_identity_sha256=snapshot.action["action_identity_sha256"],
                limit_profile=profile,
                evaluated_at=evaluated_at,
                prior_result=prior.result if prior else None,
                prior_result_sha256=prior.result_sha256 if prior else None,
            )
        except CampaignContractError as error:
            raise N4V3FixedActionError(f"P0 action description failed: {error}") from error
        blockers.extend(p0_description["blockers"])
    blockers = list(dict.fromkeys(blockers))
    description = {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-g1-s1-rc2g-n4-v3-fixed-action-description",
        "mode": "describe-only",
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "cell_id": snapshot.cell_id,
        "phase": snapshot.phase,
        "execution_contract_canonical_sha256": contract["integrity"][
            "canonical_sha256"
        ],
        "execution_contract_file_sha256": execution.execution_contract_file_sha256(
            contract
        ),
        "source_manifest_canonical_sha256": contract["source_v3"][
            "manifest_canonical_sha256"
        ],
        "source_proof_canonical_sha256": contract["source_v3"][
            "proof_canonical_sha256"
        ],
        "historical_source_p0_campaign_canonical_sha256": contract[
            "source_p0_campaign_canonical_sha256"
        ],
        "p0_campaign_canonical_sha256": contract["p0_campaign_canonical_sha256"],
        "frame": dict(snapshot.action["identity"]["frame"]),
        "reference_preview": dict(snapshot.reference_preview),
        "power_semantics": dict(contract["power_semantics"]),
        "profile_file_sha256": profile_sha,
        "prior_result_file_sha256": prior.result_sha256 if prior else None,
        "prior_finalization_file_sha256": (
            prior.finalization_sha256 if prior else None
        ),
        "p0_description": dict(p0_description) if p0_description else None,
        "contract_ready": bool(p0_description and p0_description["contract_ready"]),
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "authorization_created": False,
        "required_authorization_confirmation_sha256": (
            authorization_confirmation_sha256(snapshot.key)
        ),
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "maximum_post_requests": 1,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "blockers": blockers,
    }
    return description, profile, profile_sha, prior


def describe_n4_v3_fixed_action(
    action_key: str,
    *,
    limit_profile_file: Optional[Path] = None,
    evaluated_at: Optional[str] = None,
    primer_result_file: Optional[Path] = None,
) -> dict[str, Any]:
    snapshot = _snapshot(action_key)
    description, _profile, _profile_sha, _prior = _prepare_fixed_inputs(
        snapshot,
        limit_profile_file=limit_profile_file,
        evaluated_at=evaluated_at,
        primer_result_file=primer_result_file,
    )
    return description


def _claim_action(
    snapshot: execution.N4V3ActionSnapshot,
    *,
    attempt_id: str,
    claimed_at: str,
    destination: Path,
    profile: Mapping[str, Any],
    profile_file_sha256: str,
    prior: Optional[_PriorBundle],
    start_temperature_c: float,
    confirmations: Mapping[str, bool],
    authorization_confirmation: str,
) -> _Claim:
    contract = _execution_contract()
    declaration = snapshot.action["claim"]
    if (
        declaration["registry_id"] != CLAIM_REGISTRY_ID
        or declaration["filename"]
        != f"{snapshot.action['action_identity_sha256']}.json"
        or declaration["create_before_network"] is not True
        or declaration["overridable"] is not False
    ):
        raise N4V3FixedActionError("N4 V3 workspace-global claim declaration changed")
    registry = _claim_registry()
    if _fixed._is_within(destination, registry):
        raise N4V3FixedActionError("result directory must not overlap claim registry")
    record = {
        "schema_version": SCHEMA_VERSION,
        "kind": CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "execution_contract_canonical_sha256": contract["integrity"][
            "canonical_sha256"
        ],
        "p0_campaign_canonical_sha256": contract["p0_campaign_canonical_sha256"],
        "attempt_id": attempt_id,
        "claimed_at": claimed_at,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "authorization_consumed_permanently": True,
        "authorization_confirmation_sha256": _sha256(
            authorization_confirmation.encode("ascii")
        ),
        "profile_canonical_sha256": profile["integrity"]["canonical_sha256"],
        "profile_file_sha256": profile_file_sha256,
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
    payload = _canonical_json(record)
    filename = declaration["filename"]
    _atomic_commit(registry / filename, payload, unknown_after_commit=True)
    return _Claim(registry, filename, record, _sha256(payload))


def _target_contract(
    snapshot: execution.N4V3ActionSnapshot,
) -> _quality._RunContract:
    try:
        contract = execution.build_n4_v3_target_protocol_contract(snapshot)
    except execution.N4V3ExecutionContractError as error:
        raise N4V3FixedActionError(str(error)) from error
    return _quality._RunContract(
        **{
            **contract.__dict__,
            "required_authorization_confirmation": (
                required_authorization_confirmation(snapshot.key)
            ),
        }
    )


def _execute_protocol(
    snapshot: execution.N4V3ActionSnapshot,
    prior: Optional[_PriorBundle],
    base_url: str,
    *,
    audit_sink: dict[str, Any],
    job_timeout_s: float,
    poll_interval_s: float,
    sleeper: Callable[[float], None],
    clock: Callable[[], float],
    target_contract_builder: Optional[
        Callable[[execution.N4V3ActionSnapshot], _quality._RunContract]
    ] = None,
    request_function: Optional[Callable[..., Any]] = None,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    selected_contract_builder = target_contract_builder or _target_contract
    selected_request_function = request_function or http_request
    requester: _map._AuditedRequester | _quality._AuditedRequester
    requester = (
        _map._AuditedRequester(selected_request_function)
        if snapshot.phase == "map-primer"
        else _quality._AuditedRequester(selected_request_function)
    )
    try:
        if snapshot.phase == "map-primer":
            fresh = _map._validate_fresh_boot_state(base_url, requester)
            report = _map._perform_refresh_once(
                base_url,
                snapshot.frame,
                requester,
                job_timeout_s=job_timeout_s,
                poll_interval_s=poll_interval_s,
                sleeper=sleeper,
                clock=clock,
            )
            raw_job = _map._get_json_object(
                base_url,
                "/api/job",
                label="N4 V3 MAP immutable job",
                requester=requester,
            )
            raw_diagnostic = _map._get_json_object(
                base_url,
                "/api/diagnostic/report",
                label="N4 V3 MAP immutable diagnostic",
                requester=requester,
            )
            gpio = _map._get_json_object(
                base_url,
                "/api/diagnostic/status",
                label="N4 V3 MAP post-refresh GPIO",
                requester=requester,
            )
            completed = _map._validate_completed_map_evidence(
                report, raw_job, raw_diagnostic, gpio, snapshot.frame
            )
            protocol = {
                "fresh_boot_preflight": dict(fresh),
                "completed_map_evidence": dict(completed),
            }
        else:
            if prior is None:
                raise N4V3FixedActionError("target protocol requires same-cell MAP")
            run_contract = selected_contract_builder(snapshot)
            prior_completed = prior.evidence.get("protocol_evidence", {}).get(
                "completed_map_evidence"
            )
            if not isinstance(prior_completed, Mapping):
                raise N4V3FixedActionError("stored MAP lacks exact protocol evidence")
            exact_prior = {
                "job_raw": prior_completed.get("job_raw"),
                "diagnostic_raw": prior_completed.get("diagnostic_raw"),
            }
            live_prior = _quality._validate_prior(
                base_url,
                requester,
                run_contract,
                expected_exact_prior_evidence=exact_prior,
            )
            report = _quality._perform_refresh_once(
                base_url,
                snapshot.frame,
                requester,
                job_timeout_s=job_timeout_s,
                poll_interval_s=poll_interval_s,
                sleeper=sleeper,
                clock=clock,
            )
            _quality._validate_network_report(report, run_contract)
            raw_job = _quality._get_json_object(
                base_url,
                "/api/job",
                label="N4 V3 target immutable job reread",
                requester=requester,
            )
            if raw_job != report.get("job"):
                raise N4V3FixedActionError("target immutable job changed between reads")
            raw_diagnostic = _quality._get_json_object(
                base_url,
                "/api/diagnostic/report",
                label="N4 V3 target immutable diagnostic reread",
                requester=requester,
            )
            normalized = _quality._validate_target_raw_diagnostic(
                raw_diagnostic, report, run_contract
            )
            gpio_raw = _quality._get_json_object(
                base_url,
                "/api/diagnostic/status",
                label="N4 V3 target post-refresh GPIO",
                requester=requester,
            )
            gpio = _quality._validate_gpio_snapshot(
                gpio_raw, label="N4 V3 target post-refresh GPIO"
            )
            protocol = {
                "same_cell_primer_live_preflight": dict(live_prior),
                "network_report": dict(report),
                "target_job_raw": dict(raw_job),
                "target_diagnostic_raw": dict(raw_diagnostic),
                "target_diagnostic_validated": dict(normalized),
                "post_refresh_gpio_status_raw": dict(gpio),
            }
        audit = requester.snapshot()
        if audit["post_attempt_count"] != 1 or audit["post_issued_count"] != 1:
            raise N4V3FixedActionError(
                "N4 V3 fixed action did not issue exactly one POST /api/frame"
            )
        return protocol, audit
    finally:
        audit_sink.clear()
        audit_sink.update(requester.snapshot())


def _base_evidence(
    snapshot: execution.N4V3ActionSnapshot,
    *,
    attempt_id: str,
    claim: _Claim,
    recorded_at: str,
    profile: Mapping[str, Any],
    profile_file_sha256: str,
    evaluated_at: str,
    prior: Optional[_PriorBundle],
    start_temperature_c: float,
) -> dict[str, Any]:
    contract = _execution_contract()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EVIDENCE_KIND,
        "runner_kind": RUNNER_KIND,
        "attempt_id": attempt_id,
        "recorded_at": recorded_at,
        "action_key": snapshot.key,
        "cell_id": snapshot.cell_id,
        "phase": snapshot.phase,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "execution_contract_canonical_sha256": contract["integrity"][
            "canonical_sha256"
        ],
        "execution_contract_file_sha256": execution.execution_contract_file_sha256(
            contract
        ),
        "p0_campaign_canonical_sha256": contract["p0_campaign_canonical_sha256"],
        "source_manifest_canonical_sha256": contract["source_v3"][
            "manifest_canonical_sha256"
        ],
        "source_proof_canonical_sha256": contract["source_v3"][
            "proof_canonical_sha256"
        ],
        "frame_sha256": snapshot.action["identity"]["frame"]["sha256"],
        "reference_preview": dict(snapshot.reference_preview),
        "claim": claim.reference(),
        "profile_canonical_sha256": profile["integrity"]["canonical_sha256"],
        "profile_file_sha256": profile_file_sha256,
        "profile_evaluated_at": evaluated_at,
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
        details="claim consumed; no retry or recovery is permitted",
    )
    _write_new(destination, P0_RESULT_FILENAME, result)


def run_n4_v3_fixed_action_once(
    action_key: str,
    result_dir: Path,
    base_url: str,
    *,
    limit_profile_file: Path,
    evaluated_at: str,
    authorization_confirmation: str,
    start_temperature_c: float,
    primer_result_file: Optional[Path] = None,
    confirm_reviewed_panel_and_build: bool = False,
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
    """Consume the global claim and issue exactly one visible-refresh POST."""

    _require_deep_production_profile_path()
    snapshot = _snapshot(action_key)
    destination = _prepare_result_destination(result_dir)
    if not isinstance(base_url, str) or not base_url.strip():
        raise N4V3FixedActionError("base_url must be a non-empty device root URL")
    description, profile, profile_sha, prior = _prepare_fixed_inputs(
        snapshot,
        limit_profile_file=limit_profile_file,
        evaluated_at=evaluated_at,
        primer_result_file=primer_result_file,
    )
    if not description["contract_ready"]:
        raise N4V3FixedActionError(
            "reviewed P0 contract is not ready: "
            + ", ".join(description["blockers"])
        )
    if profile is None or profile_sha is None:
        raise N4V3FixedActionError("reviewed profile did not survive validation")
    start_temp = _temperature(start_temperature_c, label="start_temperature_c")
    limits = profile["limits"]
    if not limits["minimum_start_temperature_c"] <= start_temp <= limits[
        "maximum_start_temperature_c"
    ]:
        raise N4V3FixedActionError("start temperature is outside reviewed limits")
    common_confirmations = {
        "reviewed_panel_and_build": confirm_reviewed_panel_and_build,
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
        raise N4V3FixedActionError(
            "all action-specific physical confirmations must be true"
        )
    expected_confirmation = required_authorization_confirmation(action_key)
    if authorization_confirmation != expected_confirmation:
        raise N4V3FixedActionError(
            "exact frozen N4 V3 action authorization confirmation is required"
        )

    attempt_id = uuid.uuid4().hex
    claimed_at = _utc_now()
    claim = _claim_action(
        snapshot,
        attempt_id=attempt_id,
        claimed_at=claimed_at,
        destination=destination,
        profile=profile,
        profile_file_sha256=profile_sha,
        prior=prior,
        start_temperature_c=start_temp,
        confirmations=confirmations,
        authorization_confirmation=authorization_confirmation,
    )
    created_destination: Optional[Path] = None
    audit_capture: dict[str, Any] = {}
    requester_audit: Optional[Mapping[str, Any]] = audit_capture
    base = _base_evidence(
        snapshot,
        attempt_id=attempt_id,
        claim=claim,
        recorded_at=claimed_at,
        profile=profile,
        profile_file_sha256=profile_sha,
        evaluated_at=evaluated_at,
        prior=prior,
        start_temperature_c=start_temp,
    )
    try:
        destination.mkdir()
        created_destination = destination
        contract = _execution_contract()
        _write_new(
            destination,
            LOCK_FILENAME,
            {
                "schema_version": SCHEMA_VERSION,
                "kind": LOCK_KIND,
                "execution_contract_canonical_sha256": contract["integrity"][
                    "canonical_sha256"
                ],
                "attempt_id": attempt_id,
                "action_key": action_key,
                "action_identity_sha256": snapshot.action[
                    "action_identity_sha256"
                ],
                "claim": claim.reference(),
                "confirmations": confirmations,
                "authorization_confirmation_sha256": (
                    authorization_confirmation_sha256(action_key)
                ),
                "state": "authorization_permanently_consumed_do_not_rerun",
                "automatic_retry_authorized": False,
                "automatic_recovery_authorized": False,
            },
        )
        _write_new(destination, PROFILE_FILENAME, profile)
        protocol, requester_audit = _execute_protocol(
            snapshot,
            prior,
            base_url,
            audit_sink=audit_capture,
            job_timeout_s=job_timeout_s,
            poll_interval_s=poll_interval_s,
            sleeper=sleeper,
            clock=clock,
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
        raise N4V3FixedActionUnknown(
            "N4 V3 action is UNKNOWN_DO_NOT_RETRY; its global claim is permanent"
        ) from error


def _timing_from_protocol(evidence: Mapping[str, Any]) -> dict[str, float]:
    protocol = evidence["protocol_evidence"]
    if evidence["phase"] == "map-primer":
        timing = protocol["completed_map_evidence"]["nominal_timing"]
        return {
            "queue_delay_ms": timing["queue_delay_ms"],
            "job_duration_ms": timing["job_duration_ms"],
            "driver_total_ms": timing["total_ms"],
            "cs1_upload_ms": timing["cs1_upload_ms"],
            "cs2_upload_ms": timing["cs2_upload_ms"],
            "pon_ms": timing["pon_ms"],
            "drf_ms": timing["drf_ms"],
            "pof_ms": timing["pof_ms"],
            "post_psr_ms": timing["post_psr_ms"],
        }
    job = protocol["target_job_raw"]
    diagnostic = protocol["target_diagnostic_raw"]
    return {
        "queue_delay_ms": _quality._u32_duration(
            job["queued_at_ms"], job["started_at_ms"]
        ),
        "job_duration_ms": _quality._u32_duration(
            job["started_at_ms"], job["finished_at_ms"]
        ),
        "driver_total_ms": diagnostic["total_ms"],
        "cs1_upload_ms": diagnostic["cs1_upload_ms"],
        "cs2_upload_ms": diagnostic["cs2_upload_ms"],
        "pon_ms": diagnostic["pon_ms"],
        "drf_ms": diagnostic["drf_ms"],
        "pof_ms": diagnostic["pof_ms"],
        "post_psr_ms": diagnostic["post_psr_ms"],
    }


def _camera_binding(
    camera: Mapping[str, Any], *, base_directory: Path
) -> tuple[Optional[bytes], Mapping[str, Any]]:
    root = _require_keys(
        camera,
        {
            "observation_kind",
            "observer_or_camera_asset_sha256",
            "file",
            "capture_file_sha256",
            "fixed_exposure_profile_sha256",
        },
        label="N4 V3 operator camera input",
    )
    if root["observation_kind"] not in {"standardized-manual", "fixed-camera"}:
        raise N4V3FixedActionError("camera observation_kind is invalid")
    observer_sha = _require_sha256(
        root["observer_or_camera_asset_sha256"], label="observer/camera asset"
    )
    if root["observation_kind"] == "standardized-manual":
        if any(
            root[field] is not None
            for field in (
                "file",
                "capture_file_sha256",
                "fixed_exposure_profile_sha256",
            )
        ):
            raise N4V3FixedActionError(
                "standardized-manual observation must not imply a camera capture"
            )
        return None, {
            "observation_kind": "standardized-manual",
            "observer_or_camera_asset_sha256": observer_sha,
            "capture_file_sha256": None,
            "fixed_exposure_profile_sha256": None,
            "copied_file": None,
            "bytes": None,
            "decoded_format": None,
            "width": None,
            "height": None,
        }
    if not isinstance(root["file"], str) or not root["file"]:
        raise N4V3FixedActionError("fixed-camera observation requires a file")
    capture_sha = _require_sha256(
        root["capture_file_sha256"], label="camera capture file"
    )
    exposure_sha = _require_sha256(
        root["fixed_exposure_profile_sha256"], label="fixed exposure profile"
    )
    declared = Path(root["file"])
    capture_path = declared if declared.is_absolute() else base_directory / declared
    resolved = _safe_regular_file(capture_path, label="N4 V3 camera capture")
    try:
        payload = resolved.read_bytes()
    except OSError as error:
        raise N4V3FixedActionError(f"could not read camera capture: {error}") from error
    if _sha256(payload) != capture_sha:
        raise N4V3FixedActionError("camera bytes do not match declared SHA-256")
    try:
        with Image.open(BytesIO(payload)) as opened:
            decoded_format = opened.format
            width, height = opened.size
            opened.verify()
    except (OSError, UnidentifiedImageError, ValueError) as error:
        raise N4V3FixedActionError(f"camera capture is not a valid image: {error}") from error
    if not decoded_format or width < 1 or height < 1:
        raise N4V3FixedActionError("camera capture metadata is invalid")
    return payload, {
        "observation_kind": "fixed-camera",
        "observer_or_camera_asset_sha256": observer_sha,
        "capture_file_sha256": capture_sha,
        "fixed_exposure_profile_sha256": exposure_sha,
        "copied_file": CAMERA_CAPTURE_FILENAME,
        "bytes": len(payload),
        "decoded_format": decoded_format,
        "width": width,
        "height": height,
    }


def _build_stored_observation(
    source: Mapping[str, Any],
    source_payload: bytes,
    *,
    snapshot: execution.N4V3ActionSnapshot,
    contract: Mapping[str, Any],
    evidence: Mapping[str, Any],
    profile: Mapping[str, Any],
    observation_file: Path,
) -> tuple[Mapping[str, Any], Optional[bytes]]:
    root = _require_keys(
        source,
        {
            "schema_version",
            "kind",
            "action_key",
            "action_identity_sha256",
            "observed_at",
            "reference_preview_sha256",
            "visual",
            "electrical",
            "thermal",
            "continuity",
            "camera",
        },
        label="N4 V3 operator observation",
    )
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != OPERATOR_OBSERVATION_KIND
        or root["action_key"] != snapshot.key
        or root["action_identity_sha256"]
        != snapshot.action["action_identity_sha256"]
        or root["reference_preview_sha256"]
        != snapshot.reference_preview["sha256"]
    ):
        raise N4V3FixedActionError("operator observation action/preview binding changed")
    observed_at = _rfc3339(root["observed_at"], label="observation.observed_at")
    protocol_completed = _rfc3339(
        evidence["protocol_completed_at"], label="protocol_completed_at"
    )
    if observed_at < protocol_completed:
        raise N4V3FixedActionError("observation predates the completed refresh protocol")
    now = _rfc3339(_utc_now(), label="current finalization time")
    if observed_at > now + timedelta(minutes=15):
        raise N4V3FixedActionError("observation is implausibly far in the future")
    if snapshot.phase == "map-primer":
        visual = _require_keys(
            root["visual"],
            {
                "map_fidelity_pass",
                "orientation_pass",
                "seam_assessment_pass",
                "full_panel_inspected",
                "all_six_colors_present",
                "no_retained_old_regions",
            },
            label="N4 V3 MAP visual input",
        )
        if any(type(value) is not bool for value in visual.values()):
            raise N4V3FixedActionError("MAP visual inputs must be boolean")
        stored_visual = dict(visual)
        visual_pass = all(visual.values())
    else:
        visual = _require_keys(
            root["visual"],
            {
                "roi_definition_sha256",
                "target_fidelity_pass",
                "orientation_pass",
                "seam_assessment_pass",
                "full_panel_inspected",
                "no_retained_old_regions",
                "fidelity_score",
                "ghosting_score",
                "artifact_severity_score",
            },
            label="N4 V3 target visual input",
        )
        _require_sha256(visual["roi_definition_sha256"], label="ROI definition")
        for field in (
            "target_fidelity_pass",
            "orientation_pass",
            "seam_assessment_pass",
            "full_panel_inspected",
            "no_retained_old_regions",
        ):
            if type(visual[field]) is not bool:
                raise N4V3FixedActionError(f"target visual {field} must be boolean")
        try:
            execution._number(
                visual["fidelity_score"],
                label="fidelity_score",
                minimum=0,
                maximum=1,
            )
            execution._number(
                visual["ghosting_score"], label="ghosting_score", minimum=0
            )
            execution._number(
                visual["artifact_severity_score"],
                label="artifact_severity_score",
                minimum=0,
            )
        except execution.N4V3ExecutionContractError as error:
            raise N4V3FixedActionError(str(error)) from error
        stored_visual = {
            "protocol_sha256": contract["evidence_contract"][
                "visual_observation_protocol_sha256"
            ],
            "observation_evidence_sha256": _sha256(source_payload),
            **dict(visual),
        }
        visual_pass = all(
            visual[field]
            for field in (
                "target_fidelity_pass",
                "orientation_pass",
                "seam_assessment_pass",
                "full_panel_inspected",
                "no_retained_old_regions",
            )
        )

    electrical = _require_keys(
        root["electrical"],
        {
            "meter_asset_sha256",
            "clock_asset_sha256",
            "pre_voltage_v",
            "pre_idle_current_a",
            "post_voltage_v",
            "post_idle_current_a",
            "peak_current_a",
            "constant_voltage_mode",
            "reviewed_limits_pass",
        },
        label="N4 V3 electrical input",
    )
    _require_sha256(electrical["meter_asset_sha256"], label="meter asset")
    _require_sha256(electrical["clock_asset_sha256"], label="clock asset")
    for field in (
        "pre_voltage_v",
        "pre_idle_current_a",
        "post_voltage_v",
        "post_idle_current_a",
        "peak_current_a",
    ):
        try:
            execution._number(electrical[field], label=f"electrical.{field}", minimum=0)
        except execution.N4V3ExecutionContractError as error:
            raise N4V3FixedActionError(str(error)) from error
    if (
        type(electrical["constant_voltage_mode"]) is not bool
        or type(electrical["reviewed_limits_pass"]) is not bool
    ):
        raise N4V3FixedActionError("electrical pass inputs must be boolean")
    stored_electrical = {
        **dict(electrical),
        "timing_ms": _timing_from_protocol(evidence),
    }
    electrical_pass = bool(
        electrical["constant_voltage_mode"] and electrical["reviewed_limits_pass"]
    )

    thermal = _require_keys(
        root["thermal"],
        {
            "pre_action_c",
            "post_action_c",
            "session_max_c",
            "uncertainty_u95_c",
            "sensor_asset_sha256",
            "calibration_artifact_sha256",
            "measurement_evidence_sha256",
            "uncertainty_evidence_sha256",
        },
        label="N4 V3 thermal input",
    )
    pre_temp = _temperature(thermal["pre_action_c"], label="thermal.pre_action_c")
    post_temp = _temperature(thermal["post_action_c"], label="thermal.post_action_c")
    session_max = _temperature(thermal["session_max_c"], label="thermal.session_max_c")
    if session_max < max(pre_temp, post_temp):
        raise N4V3FixedActionError("session maximum is below a temperature sample")
    try:
        execution._number(
            thermal["uncertainty_u95_c"],
            label="thermal.uncertainty_u95_c",
            minimum=0,
        )
    except execution.N4V3ExecutionContractError as error:
        raise N4V3FixedActionError(str(error)) from error
    for field in (
        "sensor_asset_sha256",
        "calibration_artifact_sha256",
        "measurement_evidence_sha256",
        "uncertainty_evidence_sha256",
    ):
        _require_sha256(thermal[field], label=f"thermal.{field}")
    maximum_temperature = profile["limits"]["maximum_post_refresh_temperature_c"]
    if maximum_temperature is None:
        raise N4V3FixedActionError("reviewed profile lacks maximum temperature")
    thermal_pass = post_temp <= maximum_temperature and session_max <= maximum_temperature

    if snapshot.phase == "map-primer":
        if root["continuity"] is not None:
            raise N4V3FixedActionError("MAP continuity input must be null")
        continuity = None
        continuity_pass = True
    else:
        continuity = _require_keys(
            root["continuity"],
            {
                "controller_reboot_between_actions",
                "panel_power_cycle_between_actions",
                "j2_disconnect_between_actions",
                "other_visible_refresh_between_actions",
            },
            label="N4 V3 MAP-target continuity input",
        )
        if any(type(value) is not bool for value in continuity.values()):
            raise N4V3FixedActionError("continuity inputs must be boolean")
        continuity_pass = not any(continuity.values())
    camera_payload, camera = _camera_binding(
        root["camera"], base_directory=observation_file.parent
    )
    state = (
        ResultState.PASS
        if visual_pass and electrical_pass and thermal_pass and continuity_pass
        else ResultState.FAIL
    )
    stored = {
        "schema_version": SCHEMA_VERSION,
        "kind": OBSERVATION_KIND,
        "execution_contract_canonical_sha256": contract["integrity"][
            "canonical_sha256"
        ],
        "attempt_id": evidence["attempt_id"],
        "action_key": snapshot.key,
        "cell_id": snapshot.cell_id,
        "phase": snapshot.phase,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "observed_at": root["observed_at"],
        "reference_preview_sha256": snapshot.reference_preview["sha256"],
        "visual": stored_visual,
        "electrical": stored_electrical,
        "thermal": dict(thermal),
        "continuity": dict(continuity) if continuity is not None else None,
        "camera": dict(camera),
        "source_observation_file_sha256": _sha256(source_payload),
        "visual_pass": visual_pass,
        "electrical_pass": electrical_pass,
        "thermal_pass": thermal_pass,
        "continuity_pass": continuity_pass,
        "overall_state": state.value,
    }
    return stored, camera_payload


def _bundle(
    *,
    claim: Mapping[str, Any],
    claim_sha: str,
    lock: Mapping[str, Any],
    lock_sha: str,
    profile: Mapping[str, Any],
    profile_sha: str,
    evidence: Mapping[str, Any],
    evidence_sha: str,
    observation: Mapping[str, Any],
    observation_sha: str,
    finalization: Mapping[str, Any],
    finalization_sha: str,
    result: Mapping[str, Any],
    result_sha: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": BUNDLE_KIND,
        "claim": dict(claim),
        "claim_file_sha256": claim_sha,
        "lock": dict(lock),
        "lock_file_sha256": lock_sha,
        "profile": dict(profile),
        "profile_file_sha256": profile_sha,
        "evidence": dict(evidence),
        "evidence_file_sha256": evidence_sha,
        "observation": dict(observation),
        "observation_file_sha256": observation_sha,
        "finalization": dict(finalization),
        "finalization_file_sha256": finalization_sha,
        "result": dict(result),
        "result_file_sha256": result_sha,
    }


def load_n4_v3_finalized_action_bundle(result_file: Path) -> dict[str, Any]:
    """Load and pure-validate a finalized MAP action bundle from canonical files."""

    bundle = _load_bundle_from_result_file(result_file)
    try:
        execution.validate_n4_v3_finalized_action_bundle(
            _execution_contract(), bundle
        )
    except execution.N4V3ExecutionContractError as error:
        raise N4V3FixedActionError(f"finalized N4 V3 bundle is invalid: {error}") from error
    return dict(bundle)


def finalize_n4_v3_observation(
    result_dir: Path,
    observation_file: Path,
    *,
    primer_result_file: Optional[Path] = None,
) -> dict[str, Any]:
    """Seal one action observation and its immutable P0 result with no device I/O."""

    if not isinstance(result_dir, Path):
        raise N4V3FixedActionError("result_dir must be pathlib.Path")
    _reject_reparse_path_chain(result_dir, label="N4 V3 result directory")
    if not result_dir.is_dir() or result_dir.is_symlink():
        raise N4V3FixedActionError("result_dir must be an existing regular directory")
    for name in (
        OBSERVATION_FILENAME,
        FINALIZATION_FILENAME,
        P0_RESULT_FILENAME,
        CELL_OBSERVATION_FILENAME,
    ):
        if os.path.lexists(result_dir / name):
            raise N4V3FixedActionError("observation was already finalized")
    evidence, evidence_payload = _strict_json_file(
        result_dir / EVIDENCE_FILENAME, label="N4 V3 protocol evidence"
    )
    profile, profile_payload = _strict_json_file(
        result_dir / PROFILE_FILENAME, label="N4 V3 copied reviewed profile"
    )
    lock, lock_payload = _strict_json_file(
        result_dir / LOCK_FILENAME, label="N4 V3 action lock"
    )
    try:
        validate_limit_profile(profile)
    except CampaignContractError as error:
        raise N4V3FixedActionError(f"copied reviewed profile is invalid: {error}") from error
    if (
        evidence.get("kind") != EVIDENCE_KIND
        or evidence.get("outcome") != "protocol_verified_observation_pending"
        or evidence.get("protocol_verified") is not True
        or evidence.get("profile_file_sha256") != _sha256(profile_payload)
        or evidence.get("profile_canonical_sha256")
        != profile["integrity"]["canonical_sha256"]
        or evidence.get("request_audit", {}).get("post_issued_count") != 1
        or evidence.get("error") is not None
    ):
        raise N4V3FixedActionError("N4 V3 protocol evidence is not finalizable")
    claim, claim_sha = _claim_record_from_reference(evidence.get("claim"))
    if lock.get("claim") != evidence.get("claim"):
        raise N4V3FixedActionError("N4 V3 action lock/claim binding changed")
    protocol_completed_at = _rfc3339(
        evidence.get("protocol_completed_at"), label="protocol_completed_at"
    )
    claimed_at = _rfc3339(evidence.get("recorded_at"), label="claim recorded_at")
    if protocol_completed_at < claimed_at:
        raise N4V3FixedActionError("protocol completion predates the consumed claim")
    action_key = evidence.get("action_key")
    if action_key not in FIXED_ACTION_SHA256S:
        raise N4V3FixedActionError("protocol evidence action is not frozen")
    snapshot = _snapshot(str(action_key))
    if evidence.get("action_identity_sha256") != snapshot.action[
        "action_identity_sha256"
    ]:
        raise N4V3FixedActionError("protocol evidence action binding changed")
    if snapshot.phase == "target":
        if primer_result_file is None:
            raise N4V3FixedActionError(
                "target finalization requires --primer-result for deep same-cell binding"
            )
        prior = _load_prior_bundle(primer_result_file, snapshot)
        if (
            evidence.get("prior_result_file_sha256") != prior.result_sha256
            or evidence.get("prior_finalization_file_sha256")
            != prior.finalization_sha256
        ):
            raise N4V3FixedActionError("target protocol evidence prior binding changed")
    else:
        if primer_result_file is not None:
            raise N4V3FixedActionError("MAP finalization must not receive a prior result")
        prior = None

    source_observation, source_payload = _strict_json_file(
        observation_file, label="operator N4 V3 observation"
    )
    contract = _execution_contract()
    observation, camera_payload = _build_stored_observation(
        source_observation,
        source_payload,
        snapshot=snapshot,
        contract=contract,
        evidence=evidence,
        profile=profile,
        observation_file=observation_file,
    )
    observation_payload = _canonical_json(observation)
    observation_sha = _sha256(observation_payload)
    evidence_sha = _sha256(evidence_payload)
    profile_sha = _sha256(profile_payload)
    lock_sha = _sha256(lock_payload)
    state = ResultState(observation["overall_state"])
    finalization = {
        "schema_version": SCHEMA_VERSION,
        "kind": FINALIZATION_KIND,
        "execution_contract_canonical_sha256": contract["integrity"][
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
    finalization_payload = _canonical_json(finalization)
    finalization_sha = _sha256(finalization_payload)
    result = build_result_record(
        action_identity_sha256=snapshot.action["action_identity_sha256"],
        state=state,
        completed_at=str(observation["observed_at"]),
        evidence_manifest_sha256=finalization_sha,
        post_request_count=1,
        details=(
            "visual/electrical/thermal/continuity PASS recorded independently"
            if state is ResultState.PASS
            else "one or more separated observation gates failed"
        ),
    )
    result_payload = _canonical_json(result)
    result_sha = _sha256(result_payload)
    bundle = _bundle(
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
        validated = execution.validate_n4_v3_finalized_action_bundle(
            contract,
            bundle,
            expected_action_key=snapshot.key,
            prior_bundle=prior.bundle if prior else None,
        )
    except execution.N4V3ExecutionContractError as error:
        raise N4V3FixedActionError(
            f"refusing to commit an invalid finalized bundle: {error}"
        ) from error
    cell_observation_payload: Optional[bytes] = None
    cell_observation_sha: Optional[str] = None
    if snapshot.phase == "target":
        if prior is None:  # pragma: no cover - guarded above
            raise N4V3FixedActionError("target cell observation lost its MAP bundle")
        # Local import keeps the shared execution contract independent from its
        # downstream analyzer and avoids an import cycle.
        from tools import g1_s1_n4_v3_analyzer as analyzer

        try:
            analysis_contract = analyzer.compile_n4_v3_analysis_contract()
            cell_observation = analyzer.build_n4_v3_cell_observation(
                analysis_contract,
                cell_id=snapshot.cell_id,
                map_bundle=prior.bundle,
                target_bundle=bundle,
            )
            analyzer.validate_n4_v3_cell_observation(
                cell_observation, analysis_contract
            )
        except analyzer.N4V3AnalysisError as error:
            raise N4V3FixedActionError(
                f"refusing to commit an invalid N4 V3 cell observation: {error}"
            ) from error
        cell_observation_payload = _canonical_json(cell_observation)
        cell_observation_sha = _sha256(cell_observation_payload)
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
    if cell_observation_payload is not None:
        _atomic_commit(
            result_dir / CELL_OBSERVATION_FILENAME,
            cell_observation_payload,
            unknown_after_commit=False,
        )
    return {
        **validated,
        "camera_capture_present": camera_payload is not None,
        "cell_observation_file": (
            CELL_OBSERVATION_FILENAME if cell_observation_payload is not None else None
        ),
        "cell_observation_file_sha256": cell_observation_sha,
        "cell_observation_written": cell_observation_payload is not None,
    }


def _float_argument(value: str) -> float:
    try:
        return _temperature(float(value), label="temperature")
    except (ValueError, N4V3FixedActionError) as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--action", choices=FIXED_ACTION_KEYS)
    parser.add_argument("--describe-only", action="store_true")
    parser.add_argument("--finalize-observation", action="store_true")
    parser.add_argument("--limit-profile", type=Path)
    parser.add_argument("--evaluated-at")
    parser.add_argument("--primer-result", type=Path)
    parser.add_argument("--result-dir", type=Path)
    parser.add_argument("--observation-file", type=Path)
    parser.add_argument("--url")
    parser.add_argument("--confirm")
    parser.add_argument("--start-temperature-c", type=_float_argument)
    parser.add_argument("--confirm-reviewed-panel-and-build", action="store_true")
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
    parser.add_argument(
        "--confirm-no-j2-disconnect-since-primer", action="store_true"
    )
    parser.add_argument(
        "--confirm-no-panel-power-cycle-since-primer", action="store_true"
    )
    parser.add_argument(
        "--confirm-no-other-visible-refresh-since-primer", action="store_true"
    )
    args = parser.parse_args(argv)
    if args.finalize_observation:
        if args.result_dir is None or args.observation_file is None:
            parser.error("finalization requires --result-dir and --observation-file")
        if args.action is not None:
            parser.error("finalization derives the action from immutable evidence")
        return args
    if args.action is None:
        parser.error("--action is required")
    if args.describe_only:
        return args
    required = {
        "--limit-profile": args.limit_profile,
        "--evaluated-at": args.evaluated_at,
        "--result-dir": args.result_dir,
        "--url": args.url,
        "--confirm": args.confirm,
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
            result = finalize_n4_v3_observation(
                args.result_dir,
                args.observation_file,
                primer_result_file=args.primer_result,
            )
        elif args.describe_only:
            result = describe_n4_v3_fixed_action(
                args.action,
                limit_profile_file=args.limit_profile,
                evaluated_at=args.evaluated_at,
                primer_result_file=args.primer_result,
            )
        else:
            result = run_n4_v3_fixed_action_once(
                args.action,
                args.result_dir,
                args.url,
                limit_profile_file=args.limit_profile,
                evaluated_at=args.evaluated_at,
                authorization_confirmation=args.confirm,
                start_temperature_c=args.start_temperature_c,
                primer_result_file=args.primer_result,
                confirm_reviewed_panel_and_build=args.confirm_reviewed_panel_and_build,
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
    except N4V3FixedActionUnknown as error:
        print(f"UNKNOWN_DO_NOT_RETRY: {error}", file=sys.stderr)
        return 3
    except N4V3FixedActionError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
