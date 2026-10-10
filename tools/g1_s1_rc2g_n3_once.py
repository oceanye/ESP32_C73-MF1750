#!/usr/bin/env python3
"""Describe, execute once, or finalize one action from an exact N3 plan.

The exact plan is canonical and compiler-validated.  It is the only source of
action, frame, session, prior, job, and claim identities.  The runner commits a
workspace-global claim before its first network request, permits one POST to
``/api/frame``, and has no retry, recovery, power-control, reset, or firmware
path.  A claimed failure is terminal ``UNKNOWN_DO_NOT_RETRY``.
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
from tools import g1_s1_n3_execution_contract as execution  # noqa: E402
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
SESSION_OBSERVATION_FILENAME = execution.SESSION_OBSERVATION_FILENAME
CAMERA_CAPTURE_FILENAME = execution.CAMERA_CAPTURE_FILENAME
OPERATOR_OBSERVATION_KIND = "mf1750-g1-s1-rc2g-n3-operator-observation-input"
DESCRIPTION_KIND = "mf1750-g1-s1-rc2g-n3-fixed-action-description"

AUTHORIZATION_PREFIX = execution.AUTHORIZATION_PREFIX
AUTHORIZATION_SUFFIX = execution.AUTHORIZATION_SUFFIX
DEFAULT_CLAIM_REGISTRY = _fixed.DEFAULT_CLAIM_REGISTRY
http_request = _quality.http_request


class N3FixedActionError(RuntimeError):
    """The N3 action was rejected before its permanent claim existed."""


class N3FixedActionUnknown(N3FixedActionError):
    """The N3 claim exists; retry and recovery are forbidden."""


def _require_deep_production_profile_path() -> None:
    """Disable the legacy shape-only profile path before claim or network I/O."""

    raise N3FixedActionError(
        "legacy N3 live execution is disabled: a deep production profile must "
        "bind the complete campaign allowlist and real usage/review/firmware bytes"
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


def _canonical(value: Any) -> bytes:
    try:
        return canonical_json_bytes(value)
    except CampaignContractError as error:
        raise N3FixedActionError(f"canonical JSON encoding failed: {error}") from error


def _sha256(payload: bytes) -> str:
    return execution._sha256(payload)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _translate(error: BaseException) -> N3FixedActionError:
    return N3FixedActionError(str(error))


def _strict_json_file(path: Path, *, label: str) -> tuple[Mapping[str, Any], bytes]:
    try:
        return _fixed._strict_json_file(path, label=label)
    except (ValueError, RuntimeError, OSError) as error:
        raise _translate(error) from error


def _safe_regular_file(path: Path, *, label: str) -> Path:
    try:
        return _fixed._safe_regular_file(path, label=label)
    except (ValueError, RuntimeError, OSError) as error:
        raise _translate(error) from error


def _prepare_result_destination(path: Path) -> Path:
    if not isinstance(path, Path):
        raise N3FixedActionError("result directory must be pathlib.Path")
    try:
        _fixed.require_local_regular_path_syntax(path, label="N3 result directory")
        _fixed._reject_reparse_path_chain(path, label="N3 result directory")
        resolved_parent = path.parent.resolve(strict=True)
        destination = resolved_parent / path.name
    except (ValueError, RuntimeError, OSError) as error:
        raise N3FixedActionError(f"unsafe N3 result directory: {error}") from error
    if destination.exists():
        raise N3FixedActionError("N3 result directory already exists")
    return destination


def _atomic_commit(path: Path, payload: bytes, *, unknown_after_commit: bool) -> None:
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        message = f"exclusive evidence path already exists: {path.name}"
        if unknown_after_commit:
            raise N3FixedActionUnknown(message) from error
        raise N3FixedActionError(message) from error
    except OSError as error:
        message = f"could not atomically write {path.name}: {error}"
        if unknown_after_commit:
            raise N3FixedActionUnknown(message) from error
        raise N3FixedActionError(message) from error


def _write_new(directory: Path, filename: str, value: Mapping[str, Any]) -> str:
    payload = _canonical(value)
    _atomic_commit(directory / filename, payload, unknown_after_commit=True)
    return _sha256(payload)


def _rfc3339(value: object, *, label: str) -> datetime:
    try:
        return execution._timestamp(value, label=label)
    except execution.N3ExecutionContractError as error:
        raise N3FixedActionError(str(error)) from error


def _temperature(value: object, *, label: str) -> float:
    try:
        result = execution._number(value, label=label)
    except execution.N3ExecutionContractError as error:
        raise N3FixedActionError(str(error)) from error
    assert result is not None
    return result


def _require_keys(value: object, keys: set[str], *, label: str) -> Mapping[str, Any]:
    try:
        return execution._exact(value, label=label, keys=keys)
    except execution.N3ExecutionContractError as error:
        raise N3FixedActionError(str(error)) from error


def required_authorization_confirmation(
    plan: Mapping[str, Any], action_key: str
) -> str:
    snapshot = execution.load_n3_action_snapshot(plan, action_key)
    return (
        f"{AUTHORIZATION_PREFIX}"
        f"{snapshot.action['action_identity_sha256'].upper()}"
        f"{AUTHORIZATION_SUFFIX}"
    )


def authorization_confirmation_sha256(
    plan: Mapping[str, Any], action_key: str
) -> str:
    return _sha256(required_authorization_confirmation(plan, action_key).encode("ascii"))


def load_n3_exact_plan_file(path: Path) -> tuple[Mapping[str, Any], str]:
    plan, payload = _strict_json_file(path, label="N3 exact execution plan")
    try:
        root = execution.validate_n3_exact_plan(plan)
    except execution.N3ExecutionContractError as error:
        raise N3FixedActionError(f"N3 exact plan is invalid: {error}") from error
    if _sha256(payload) != execution.exact_plan_file_sha256(root):
        raise N3FixedActionError("N3 exact plan whole-file identity changed")
    return root, _sha256(payload)


def _load_profile(path: Path) -> tuple[Mapping[str, Any], str]:
    profile, payload = _strict_json_file(path, label="reviewed N3 limit profile")
    try:
        return validate_limit_profile(profile), _sha256(payload)
    except CampaignContractError as error:
        raise N3FixedActionError(f"reviewed N3 profile is invalid: {error}") from error


def _claim_registry() -> Path:
    path = DEFAULT_CLAIM_REGISTRY
    try:
        _fixed.require_local_regular_path_syntax(path, label="N3 P0 claim registry")
        _fixed._reject_reparse_path_chain(path, label="N3 P0 claim registry")
        path.mkdir(parents=True, exist_ok=True)
        resolved = path.resolve(strict=True)
    except (ValueError, RuntimeError, OSError) as error:
        raise N3FixedActionError(f"could not prepare N3 claim registry: {error}") from error
    return resolved


def _read_bundle_record(directory: Path, filename: str, *, label: str) -> Mapping[str, Any]:
    record, _payload = _strict_json_file(directory / filename, label=label)
    return record


def _load_bundle_from_result_file(result_file: Path) -> dict[str, Any]:
    resolved = _safe_regular_file(result_file, label="N3 P0 result")
    if resolved.name != P0_RESULT_FILENAME:
        raise N3FixedActionError(f"N3 result filename must be {P0_RESULT_FILENAME}")
    directory = resolved.parent
    records = {
        "lock": _read_bundle_record(directory, LOCK_FILENAME, label="N3 action lock"),
        "profile": _read_bundle_record(
            directory, PROFILE_FILENAME, label="N3 reviewed profile"
        ),
        "evidence": _read_bundle_record(
            directory, EVIDENCE_FILENAME, label="N3 protocol evidence"
        ),
        "observation": _read_bundle_record(
            directory, OBSERVATION_FILENAME, label="N3 action observation"
        ),
        "finalization": _read_bundle_record(
            directory, FINALIZATION_FILENAME, label="N3 action finalization"
        ),
        "result": _read_bundle_record(directory, P0_RESULT_FILENAME, label="N3 P0 result"),
    }
    claim_reference = records["evidence"].get("claim")
    if not isinstance(claim_reference, Mapping):
        raise N3FixedActionError("N3 evidence claim reference is missing")
    filename = claim_reference.get("filename")
    if not isinstance(filename, str) or not filename:
        raise N3FixedActionError("N3 evidence claim filename is invalid")
    claim = _read_bundle_record(
        _claim_registry(), filename, label="N3 workspace-global claim"
    )
    bundle: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": BUNDLE_KIND,
        "claim": claim,
    }
    for name, record in {"claim": claim, **records}.items():
        bundle[name] = record
        bundle[f"{name}_file_sha256"] = execution._sha256(record)
    return bundle


def _load_prior_bundle(
    plan: Mapping[str, Any], result_file: Path, snapshot: execution.N3ActionSnapshot
) -> _PriorBundle:
    bundle = _load_bundle_from_result_file(result_file)
    try:
        validated = execution.validate_n3_finalized_action_bundle(
            plan,
            bundle,
            expected_action_key=snapshot.route["map_action_key"],
        )
    except execution.N3ExecutionContractError as error:
        raise N3FixedActionError(f"same-session MAP bundle is invalid: {error}") from error
    if validated["state"] != ResultState.PASS.value:
        raise N3FixedActionError("same-session MAP bundle is not finalized PASS")
    return _PriorBundle(bundle=bundle, validated=validated)


def _prepare_fixed_inputs(
    plan: Mapping[str, Any],
    action_key: str,
    *,
    limit_profile_file: Optional[Path],
    evaluated_at: str,
    primer_result_file: Optional[Path],
) -> tuple[
    execution.N3ActionSnapshot,
    dict[str, Any],
    Optional[Mapping[str, Any]],
    Optional[str],
    Optional[_PriorBundle],
]:
    try:
        snapshot = execution.load_n3_action_snapshot(plan, action_key)
    except execution.N3ExecutionContractError as error:
        raise N3FixedActionError(str(error)) from error
    profile: Optional[Mapping[str, Any]] = None
    profile_sha: Optional[str] = None
    profile_error: Optional[str] = None
    if limit_profile_file is not None:
        try:
            profile, profile_sha = _load_profile(limit_profile_file)
        except N3FixedActionError as error:
            profile_error = str(error)
    prior: Optional[_PriorBundle] = None
    prior_error: Optional[str] = None
    if snapshot.phase == "target":
        if primer_result_file is None:
            prior_error = "missing_same_session_finalized_map_pass_bundle"
        else:
            try:
                prior = _load_prior_bundle(plan, primer_result_file, snapshot)
            except N3FixedActionError as error:
                prior_error = str(error)
    elif primer_result_file is not None:
        raise N3FixedActionError("N3 MAP action must not receive a primer result")
    p0_description: Optional[Mapping[str, Any]] = None
    p0_error: Optional[str] = None
    if profile is not None and prior_error is None:
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
            p0_error = str(error)
    asset_blockers = list(plan["readiness"]["measurement_asset_blockers"])
    preclaim_blockers = [
        *asset_blockers,
        *([f"invalid_limit_profile:{profile_error}"] if profile_error else []),
        *(["missing_reviewed_limit_profile"] if limit_profile_file is None else []),
        *([f"invalid_or_missing_prior:{prior_error}"] if prior_error else []),
        *([f"p0_description_rejected:{p0_error}"] if p0_error else []),
    ]
    blockers = [
        *preclaim_blockers,
        *(list(p0_description["blockers"]) if p0_description else []),
    ]
    blockers = list(dict.fromkeys(blockers))
    description = {
        "schema_version": SCHEMA_VERSION,
        "kind": DESCRIPTION_KIND,
        "mode": "describe-only",
        "plan_id": plan["plan_id"],
        "plan_canonical_sha256": plan["integrity"]["canonical_sha256"],
        "action_key": action_key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "cell_id": snapshot.cell_id,
        "candidate_cell_id": snapshot.candidate_cell_id,
        "phase": snapshot.phase,
        "frame_sha256": snapshot.action["identity"]["frame"]["sha256"],
        "reference_preview": dict(snapshot.reference_preview),
        "route": dict(snapshot.route),
        "contract_ready": not preclaim_blockers
        and p0_description is not None
        and p0_description["contract_ready"] is True,
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "authorization_created": False,
        "required_authorization_confirmation_sha256": (
            authorization_confirmation_sha256(plan, action_key)
        ),
        "claim_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "blockers": blockers,
        "p0_description": dict(p0_description) if p0_description else None,
    }
    return snapshot, description, profile, profile_sha, prior


def describe_n3_fixed_action(
    plan: Mapping[str, Any],
    action_key: str,
    *,
    limit_profile_file: Optional[Path] = None,
    evaluated_at: str,
    primer_result_file: Optional[Path] = None,
) -> dict[str, Any]:
    """Deep-describe one plan action with zero claim, authorization, or network."""

    _snapshot, description, _profile, _profile_sha, _prior = _prepare_fixed_inputs(
        plan,
        action_key,
        limit_profile_file=limit_profile_file,
        evaluated_at=evaluated_at,
        primer_result_file=primer_result_file,
    )
    return description


def _claim_action(
    snapshot: execution.N3ActionSnapshot,
    *,
    plan_file_sha256: str,
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
    registry = _claim_registry()
    try:
        if destination.resolve(strict=False).is_relative_to(registry):
            raise N3FixedActionError("result directory must not overlap claim registry")
    except AttributeError:  # pragma: no cover - Python 3.8 compatibility
        if str(destination.resolve(strict=False)).startswith(str(registry) + os.sep):
            raise N3FixedActionError("result directory must not overlap claim registry")
    plan = snapshot.plan
    record = {
        "schema_version": SCHEMA_VERSION,
        "kind": CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "plan_id": plan["plan_id"],
        "plan_canonical_sha256": plan["integrity"]["canonical_sha256"],
        "plan_file_sha256": plan_file_sha256,
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
        "profile_canonical_sha256": profile["integrity"]["canonical_sha256"],
        "profile_file_sha256": profile_file_sha256,
        "prior_result_file_sha256": prior.result_sha256 if prior else None,
        "prior_finalization_file_sha256": prior.finalization_sha256 if prior else None,
        "start_temperature_c": start_temperature_c,
        "confirmations": dict(confirmations),
        "result_directory": str(destination),
        "maximum_post_requests": 1,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
    }
    payload = _canonical(record)
    filename = snapshot.action["claim"]["filename"]
    _atomic_commit(registry / filename, payload, unknown_after_commit=True)
    return _Claim(registry, filename, record, _sha256(payload))


def _target_contract(snapshot: execution.N3ActionSnapshot) -> _quality._RunContract:
    contract = execution.build_n3_target_protocol_contract(snapshot)
    return _quality._RunContract(
        **{
            **contract.__dict__,
            "required_authorization_confirmation": required_authorization_confirmation(
                snapshot.plan, snapshot.key
            ),
        }
    )


def _execute_protocol(
    snapshot: execution.N3ActionSnapshot,
    prior: Optional[_PriorBundle],
    base_url: str,
    *,
    audit_sink: dict[str, Any],
    job_timeout_s: float,
    poll_interval_s: float,
    sleeper: Callable[[float], None],
    clock: Callable[[], float],
    target_contract_builder: Optional[
        Callable[[execution.N3ActionSnapshot], _quality._RunContract]
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
                base_url, "/api/job", label="N3 MAP immutable job", requester=requester
            )
            raw_diagnostic = _map._get_json_object(
                base_url,
                "/api/diagnostic/report",
                label="N3 MAP immutable diagnostic",
                requester=requester,
            )
            gpio = _map._get_json_object(
                base_url,
                "/api/diagnostic/status",
                label="N3 MAP post-refresh GPIO",
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
                raise N3FixedActionError("N3 target protocol requires same-session MAP")
            run_contract = selected_contract_builder(snapshot)
            completed = prior.evidence.get("protocol_evidence", {}).get(
                "completed_map_evidence"
            )
            if not isinstance(completed, Mapping):
                raise N3FixedActionError("stored N3 MAP lacks exact protocol evidence")
            live_prior = _quality._validate_prior(
                base_url,
                requester,
                run_contract,
                expected_exact_prior_evidence={
                    "job_raw": completed.get("job_raw"),
                    "diagnostic_raw": completed.get("diagnostic_raw"),
                },
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
                label="N3 target immutable job reread",
                requester=requester,
            )
            if raw_job != report.get("job"):
                raise N3FixedActionError("N3 target immutable job changed between reads")
            raw_diagnostic = _quality._get_json_object(
                base_url,
                "/api/diagnostic/report",
                label="N3 target immutable diagnostic reread",
                requester=requester,
            )
            normalized = _quality._validate_target_raw_diagnostic(
                raw_diagnostic, report, run_contract
            )
            gpio_raw = _quality._get_json_object(
                base_url,
                "/api/diagnostic/status",
                label="N3 target post-refresh GPIO",
                requester=requester,
            )
            gpio = _quality._validate_gpio_snapshot(
                gpio_raw, label="N3 target post-refresh GPIO"
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
            raise N3FixedActionError("N3 action did not issue exactly one POST /api/frame")
        return protocol, audit
    finally:
        audit_sink.clear()
        audit_sink.update(requester.snapshot())


def _base_evidence(
    snapshot: execution.N3ActionSnapshot,
    *,
    plan_file_sha256: str,
    attempt_id: str,
    claim: _Claim,
    recorded_at: str,
    profile: Mapping[str, Any],
    profile_file_sha256: str,
    evaluated_at: str,
    prior: Optional[_PriorBundle],
    start_temperature_c: float,
) -> dict[str, Any]:
    plan = snapshot.plan
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EVIDENCE_KIND,
        "runner_kind": RUNNER_KIND,
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
        "plan_file_sha256": plan_file_sha256,
        "execution_manifest_canonical_sha256": plan["execution_manifest"][
            "integrity"
        ]["canonical_sha256"],
        "p0_campaign_canonical_sha256": snapshot.campaign["integrity"][
            "canonical_sha256"
        ],
        "source_manifest_canonical_sha256": plan["source_manifest"][
            "canonical_sha256"
        ],
        "frame_sha256": snapshot.action["identity"]["frame"]["sha256"],
        "reference_preview": dict(snapshot.reference_preview),
        "claim": claim.reference(),
        "profile_canonical_sha256": profile["integrity"]["canonical_sha256"],
        "profile_file_sha256": profile_file_sha256,
        "profile_evaluated_at": evaluated_at,
        "prior_result_file_sha256": prior.result_sha256 if prior else None,
        "prior_finalization_file_sha256": prior.finalization_sha256 if prior else None,
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


def run_n3_fixed_action_once(
    plan: Mapping[str, Any],
    plan_file_sha256: str,
    action_key: str,
    result_dir: Path,
    base_url: str,
    *,
    limit_profile_file: Path,
    evaluated_at: str,
    authorization_confirmation: str,
    start_temperature_c: float,
    primer_result_file: Optional[Path] = None,
    confirm_reviewed_panel_build_and_exact_plan: bool = False,
    confirm_registered_measurement_assets_present: bool = False,
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
    """Consume the global claim, then issue exactly one visible-refresh POST."""

    _require_deep_production_profile_path()
    try:
        root_plan = execution.validate_n3_exact_plan(plan)
    except execution.N3ExecutionContractError as error:
        raise N3FixedActionError(str(error)) from error
    if plan_file_sha256 != execution.exact_plan_file_sha256(root_plan):
        raise N3FixedActionError("N3 exact plan whole-file SHA-256 is invalid")
    destination = _prepare_result_destination(result_dir)
    if not isinstance(base_url, str) or not base_url.strip():
        raise N3FixedActionError("base_url must be a non-empty device root URL")
    snapshot, description, profile, profile_sha, prior = _prepare_fixed_inputs(
        root_plan,
        action_key,
        limit_profile_file=limit_profile_file,
        evaluated_at=evaluated_at,
        primer_result_file=primer_result_file,
    )
    if not description["contract_ready"]:
        raise N3FixedActionError(
            "reviewed N3 contract is not ready: " + ", ".join(description["blockers"])
        )
    if profile is None or profile_sha is None:
        raise N3FixedActionError("reviewed N3 profile did not survive validation")
    start_temp = _temperature(start_temperature_c, label="start_temperature_c")
    limits = profile["limits"]
    if not limits["minimum_start_temperature_c"] <= start_temp <= limits[
        "maximum_start_temperature_c"
    ]:
        raise N3FixedActionError("start temperature is outside reviewed limits")
    common = {
        "reviewed_panel_build_and_exact_plan": (
            confirm_reviewed_panel_build_and_exact_plan
        ),
        "registered_measurement_assets_present": (
            confirm_registered_measurement_assets_present
        ),
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
            "map_fidelity_from_same_session_primer": confirm_map_fidelity_from_primer,
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
    confirmations = {**common, **phase_confirmations}
    if any(type(value) is not bool or value is not True for value in confirmations.values()):
        raise N3FixedActionError("all N3 action-specific confirmations must be true")
    expected_confirmation = required_authorization_confirmation(root_plan, action_key)
    if authorization_confirmation != expected_confirmation:
        raise N3FixedActionError("exact N3 action authorization confirmation is required")

    attempt_id = uuid.uuid4().hex
    claimed_at = _utc_now()
    claim = _claim_action(
        snapshot,
        plan_file_sha256=plan_file_sha256,
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
        plan_file_sha256=plan_file_sha256,
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
        _write_new(
            destination,
            LOCK_FILENAME,
            {
                "schema_version": SCHEMA_VERSION,
                "kind": LOCK_KIND,
                "plan_id": root_plan["plan_id"],
                "plan_canonical_sha256": root_plan["integrity"]["canonical_sha256"],
                "attempt_id": attempt_id,
                "action_key": action_key,
                "action_identity_sha256": snapshot.action[
                    "action_identity_sha256"
                ],
                "claim": claim.reference(),
                "confirmations": confirmations,
                "authorization_confirmation_sha256": (
                    authorization_confirmation_sha256(root_plan, action_key)
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
            "protocol_completed_at": _utc_now(),
            "outcome": "protocol_verified_observation_pending",
            "protocol_verified": True,
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
        raise N3FixedActionUnknown(
            "N3 action is UNKNOWN_DO_NOT_RETRY; its global claim is permanent"
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
    camera: Mapping[str, Any],
    *,
    target: bool,
    base_directory: Path,
) -> tuple[Optional[bytes], Mapping[str, Any]]:
    root = _require_keys(
        camera,
        {"capture_performed", "file", "capture_file_sha256"},
        label="N3 operator camera input",
    )
    if target:
        if root["capture_performed"] is not True:
            raise N3FixedActionError("N3 target requires one fixed-camera capture")
        if not isinstance(root["file"], str) or not root["file"]:
            raise N3FixedActionError("N3 target camera capture requires a file")
        try:
            capture_sha = execution._require_sha256(
                root["capture_file_sha256"], label="N3 camera capture file"
            )
        except execution.N3ExecutionContractError as error:
            raise N3FixedActionError(str(error)) from error
        declared = Path(root["file"])
        capture_path = declared if declared.is_absolute() else base_directory / declared
        resolved = _safe_regular_file(capture_path, label="N3 target camera capture")
        try:
            payload = resolved.read_bytes()
        except OSError as error:
            raise N3FixedActionError(f"could not read N3 camera capture: {error}") from error
        if _sha256(payload) != capture_sha:
            raise N3FixedActionError("N3 camera bytes do not match declared SHA-256")
        try:
            with Image.open(BytesIO(payload)) as opened:
                decoded_format = opened.format
                width, height = opened.size
                opened.verify()
        except (OSError, UnidentifiedImageError, ValueError) as error:
            raise N3FixedActionError(f"N3 camera capture is not a valid image: {error}") from error
        if not decoded_format or width < 1 or height < 1:
            raise N3FixedActionError("N3 camera capture metadata is invalid")
        return payload, {
            "capture_performed": True,
            "capture_file_sha256": capture_sha,
            "copied_file": CAMERA_CAPTURE_FILENAME,
            "bytes": len(payload),
            "decoded_format": decoded_format,
            "width": width,
            "height": height,
        }
    if root != {
        "capture_performed": False,
        "file": None,
        "capture_file_sha256": None,
    }:
        raise N3FixedActionError("N3 MAP camera input must explicitly record no capture")
    return None, {
        "capture_performed": False,
        "capture_file_sha256": None,
        "copied_file": None,
        "bytes": None,
        "decoded_format": None,
        "width": None,
        "height": None,
    }


def _build_stored_observation(
    source: Mapping[str, Any],
    source_payload: bytes,
    *,
    snapshot: execution.N3ActionSnapshot,
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
        label="N3 operator observation",
    )
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["kind"] != OPERATOR_OBSERVATION_KIND
        or root["action_key"] != snapshot.key
        or root["action_identity_sha256"]
        != snapshot.action["action_identity_sha256"]
        or root["reference_preview_sha256"] != snapshot.reference_preview["sha256"]
    ):
        raise N3FixedActionError("N3 operator observation action/preview binding changed")
    observed_at = _rfc3339(root["observed_at"], label="observation.observed_at")
    protocol_completed = _rfc3339(
        evidence["protocol_completed_at"], label="protocol_completed_at"
    )
    if observed_at < protocol_completed:
        raise N3FixedActionError("N3 observation predates the completed protocol")
    now = _rfc3339(_utc_now(), label="current finalization time")
    if observed_at > now + timedelta(minutes=15):
        raise N3FixedActionError("N3 observation is implausibly far in the future")

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
            label="N3 MAP visual input",
        )
        if any(type(value) is not bool for value in visual.values()):
            raise N3FixedActionError("N3 MAP visual inputs must be boolean")
        visual_pass = all(visual.values())
    else:
        visual = _require_keys(
            root["visual"],
            {
                "target_fidelity_pass",
                "orientation_pass",
                "seam_assessment_pass",
                "full_panel_inspected",
                "no_retained_old_regions",
                "photo_difference_score",
                "photo_luminance_mean",
                "photo_luminance_standard_deviation",
            },
            label="N3 target visual input",
        )
        for field in (
            "target_fidelity_pass",
            "orientation_pass",
            "seam_assessment_pass",
            "full_panel_inspected",
            "no_retained_old_regions",
        ):
            if type(visual[field]) is not bool:
                raise N3FixedActionError(f"N3 target visual {field} must be boolean")
        try:
            execution._number(
                visual["photo_difference_score"],
                label="visual.photo_difference_score",
                minimum=0,
                nullable=True,
            )
            for field in (
                "photo_luminance_mean",
                "photo_luminance_standard_deviation",
            ):
                execution._number(
                    visual[field],
                    label=f"visual.{field}",
                    minimum=0,
                    maximum=255,
                    nullable=True,
                )
        except execution.N3ExecutionContractError as error:
            raise N3FixedActionError(str(error)) from error
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
        label="N3 electrical input",
    )
    assets = execution._registered_asset_identity(snapshot.plan)
    try:
        execution._require_sha256(
            electrical["meter_asset_sha256"], label="N3 meter asset"
        )
    except execution.N3ExecutionContractError as error:
        raise N3FixedActionError(str(error)) from error
    if electrical["clock_asset_sha256"] != assets["timing_clock_asset_sha256"]:
        raise N3FixedActionError("N3 observation clock is not the registered asset")
    for field in (
        "pre_voltage_v",
        "pre_idle_current_a",
        "post_voltage_v",
        "post_idle_current_a",
        "peak_current_a",
    ):
        try:
            execution._number(electrical[field], label=f"electrical.{field}", minimum=0)
        except execution.N3ExecutionContractError as error:
            raise N3FixedActionError(str(error)) from error
    if any(
        type(electrical[field]) is not bool
        for field in ("constant_voltage_mode", "reviewed_limits_pass")
    ):
        raise N3FixedActionError("N3 electrical pass inputs must be boolean")
    stored_electrical = {**dict(electrical), "timing_ms": _timing_from_protocol(evidence)}
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
            "measurement_location_asset_sha256",
            "measurement_evidence_sha256",
            "uncertainty_evidence_sha256",
        },
        label="N3 thermal input",
    )
    pre_temp = _temperature(thermal["pre_action_c"], label="thermal.pre_action_c")
    post_temp = _temperature(thermal["post_action_c"], label="thermal.post_action_c")
    session_max = _temperature(thermal["session_max_c"], label="thermal.session_max_c")
    if session_max < max(pre_temp, post_temp):
        raise N3FixedActionError("N3 session maximum is below a temperature sample")
    try:
        execution._number(
            thermal["uncertainty_u95_c"],
            label="thermal.uncertainty_u95_c",
            minimum=0,
        )
    except execution.N3ExecutionContractError as error:
        raise N3FixedActionError(str(error)) from error
    expected_thermal = {
        "sensor_asset_sha256": assets["temperature_sensor_asset_sha256"],
        "calibration_artifact_sha256": assets[
            "temperature_calibration_asset_sha256"
        ],
        "measurement_location_asset_sha256": assets[
            "temperature_location_asset_sha256"
        ],
    }
    if any(thermal[field] != value for field, value in expected_thermal.items()):
        raise N3FixedActionError("N3 thermal assets differ from the exact plan registry")
    for field in ("measurement_evidence_sha256", "uncertainty_evidence_sha256"):
        try:
            execution._require_sha256(thermal[field], label=f"thermal.{field}")
        except execution.N3ExecutionContractError as error:
            raise N3FixedActionError(str(error)) from error
    maximum_temperature = profile["limits"]["maximum_post_refresh_temperature_c"]
    if maximum_temperature is None:
        raise N3FixedActionError("reviewed N3 profile lacks maximum temperature")
    thermal_pass = post_temp <= maximum_temperature and session_max <= maximum_temperature

    if snapshot.phase == "map-primer":
        if root["continuity"] is not None:
            raise N3FixedActionError("N3 MAP continuity input must be null")
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
            label="N3 MAP-target continuity input",
        )
        if any(type(value) is not bool for value in continuity.values()):
            raise N3FixedActionError("N3 continuity inputs must be boolean")
        continuity_pass = not any(continuity.values())
    camera_payload, camera = _camera_binding(
        root["camera"],
        target=snapshot.phase == "target",
        base_directory=observation_file.parent,
    )
    state = (
        ResultState.PASS
        if visual_pass and electrical_pass and thermal_pass and continuity_pass
        else ResultState.FAIL
    )
    stored = {
        "schema_version": SCHEMA_VERSION,
        "kind": OBSERVATION_KIND,
        "plan_canonical_sha256": snapshot.plan["integrity"]["canonical_sha256"],
        "attempt_id": evidence["attempt_id"],
        "action_key": snapshot.key,
        "cell_id": snapshot.cell_id,
        "candidate_cell_id": snapshot.candidate_cell_id,
        "phase": snapshot.phase,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "observed_at": root["observed_at"],
        "reference_preview_sha256": snapshot.reference_preview["sha256"],
        "measurement_assets": assets,
        "visual": dict(visual),
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
    records: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": BUNDLE_KIND,
    }
    for name in (
        "claim",
        "lock",
        "profile",
        "evidence",
        "observation",
        "finalization",
        "result",
    ):
        record = records[name]
        result[name] = dict(record)
        result[f"{name}_file_sha256"] = execution._sha256(record)
    return result


def finalize_n3_observation(
    plan: Mapping[str, Any],
    plan_file_sha256: str,
    result_dir: Path,
    observation_file: Path,
    *,
    primer_result_file: Optional[Path] = None,
) -> dict[str, Any]:
    """Seal one manual observation and immutable P0 result with no device I/O."""

    try:
        root_plan = execution.validate_n3_exact_plan(plan)
    except execution.N3ExecutionContractError as error:
        raise N3FixedActionError(str(error)) from error
    if plan_file_sha256 != execution.exact_plan_file_sha256(root_plan):
        raise N3FixedActionError("N3 exact plan whole-file SHA-256 is invalid")
    if not isinstance(result_dir, Path):
        raise N3FixedActionError("result_dir must be pathlib.Path")
    try:
        _fixed._reject_reparse_path_chain(result_dir, label="N3 result directory")
    except (ValueError, RuntimeError, OSError) as error:
        raise N3FixedActionError(str(error)) from error
    if not result_dir.is_dir() or result_dir.is_symlink():
        raise N3FixedActionError("result_dir must be an existing regular directory")
    for name in (
        OBSERVATION_FILENAME,
        FINALIZATION_FILENAME,
        P0_RESULT_FILENAME,
        SESSION_OBSERVATION_FILENAME,
        CAMERA_CAPTURE_FILENAME,
    ):
        if os.path.lexists(result_dir / name):
            raise N3FixedActionError("N3 observation was already finalized")
    evidence, evidence_payload = _strict_json_file(
        result_dir / EVIDENCE_FILENAME, label="N3 protocol evidence"
    )
    profile, profile_payload = _strict_json_file(
        result_dir / PROFILE_FILENAME, label="N3 copied reviewed profile"
    )
    lock, lock_payload = _strict_json_file(
        result_dir / LOCK_FILENAME, label="N3 action lock"
    )
    try:
        validate_limit_profile(profile)
    except CampaignContractError as error:
        raise N3FixedActionError(f"copied N3 profile is invalid: {error}") from error
    if (
        evidence.get("kind") != EVIDENCE_KIND
        or evidence.get("outcome") != "protocol_verified_observation_pending"
        or evidence.get("protocol_verified") is not True
        or evidence.get("plan_id") != root_plan["plan_id"]
        or evidence.get("plan_canonical_sha256")
        != root_plan["integrity"]["canonical_sha256"]
        or evidence.get("plan_file_sha256") != plan_file_sha256
        or evidence.get("profile_file_sha256") != _sha256(profile_payload)
        or evidence.get("profile_canonical_sha256")
        != profile["integrity"]["canonical_sha256"]
        or evidence.get("request_audit", {}).get("post_issued_count") != 1
        or evidence.get("error") is not None
    ):
        raise N3FixedActionError("N3 protocol evidence is not finalizable")
    action_key = evidence.get("action_key")
    try:
        snapshot = execution.load_n3_action_snapshot(root_plan, str(action_key))
    except execution.N3ExecutionContractError as error:
        raise N3FixedActionError(str(error)) from error
    if evidence.get("action_identity_sha256") != snapshot.action[
        "action_identity_sha256"
    ]:
        raise N3FixedActionError("N3 protocol evidence action binding changed")
    claim_reference = evidence.get("claim")
    if not isinstance(claim_reference, Mapping):
        raise N3FixedActionError("N3 protocol evidence claim is missing")
    claim_filename = claim_reference.get("filename")
    if claim_filename != snapshot.action["claim"]["filename"]:
        raise N3FixedActionError("N3 protocol claim filename changed")
    claim, claim_payload = _strict_json_file(
        _claim_registry() / str(claim_filename), label="N3 workspace-global claim"
    )
    claim_sha = _sha256(claim_payload)
    if (
        claim_reference.get("file_sha256") != claim_sha
        or lock.get("claim") != claim_reference
    ):
        raise N3FixedActionError("N3 action claim/lock binding changed")
    protocol_completed_at = _rfc3339(
        evidence.get("protocol_completed_at"), label="protocol_completed_at"
    )
    claimed_at = _rfc3339(evidence.get("recorded_at"), label="claim recorded_at")
    if protocol_completed_at < claimed_at:
        raise N3FixedActionError("N3 protocol completion predates the consumed claim")
    if snapshot.phase == "target":
        if primer_result_file is None:
            raise N3FixedActionError(
                "N3 target finalization requires its exact MAP --primer-result"
            )
        prior = _load_prior_bundle(root_plan, primer_result_file, snapshot)
        if (
            evidence.get("prior_result_file_sha256") != prior.result_sha256
            or evidence.get("prior_finalization_file_sha256")
            != prior.finalization_sha256
        ):
            raise N3FixedActionError("N3 target protocol prior binding changed")
    else:
        if primer_result_file is not None:
            raise N3FixedActionError("N3 MAP finalization must not receive a prior")
        prior = None
    try:
        execution.validate_n3_protocol_evidence(
            evidence,
            snapshot=snapshot,
            prior_bundle=prior.bundle if prior else None,
        )
    except execution.N3ExecutionContractError as error:
        raise N3FixedActionError(f"stored N3 protocol evidence is invalid: {error}") from error

    source, source_payload = _strict_json_file(
        observation_file, label="operator N3 observation"
    )
    observation, camera_payload = _build_stored_observation(
        source,
        source_payload,
        snapshot=snapshot,
        evidence=evidence,
        profile=profile,
        observation_file=observation_file,
    )
    observation_payload = _canonical(observation)
    observation_sha = _sha256(observation_payload)
    evidence_sha = _sha256(evidence_payload)
    profile_sha = _sha256(profile_payload)
    lock_sha = _sha256(lock_payload)
    state = ResultState(observation["overall_state"])
    finalization = {
        "schema_version": SCHEMA_VERSION,
        "kind": FINALIZATION_KIND,
        "plan_id": root_plan["plan_id"],
        "plan_canonical_sha256": root_plan["integrity"]["canonical_sha256"],
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
            "visual/electrical/thermal/continuity PASS recorded independently"
            if state is ResultState.PASS
            else "one or more separated N3 observation gates failed"
        ),
    )
    result_payload = _canonical(result)
    records = {
        "claim": claim,
        "lock": lock,
        "profile": profile,
        "evidence": evidence,
        "observation": observation,
        "finalization": finalization,
        "result": result,
    }
    bundle = _bundle(records)
    try:
        validated = execution.validate_n3_finalized_action_bundle(
            root_plan,
            bundle,
            expected_action_key=snapshot.key,
            prior_bundle=prior.bundle if prior else None,
        )
    except execution.N3ExecutionContractError as error:
        raise N3FixedActionError(
            f"refusing to commit an invalid N3 finalized bundle: {error}"
        ) from error

    session_payload: Optional[bytes] = None
    session_sha: Optional[str] = None
    if snapshot.phase == "target":
        if prior is None:  # pragma: no cover - guarded above
            raise N3FixedActionError("N3 target lost its MAP bundle")
        from tools import g1_s1_n3_analyzer as analyzer

        try:
            session = analyzer.build_n3_session_observation(
                root_plan, map_bundle=prior.bundle, target_bundle=bundle
            )
            analyzer.validate_n3_observation(
                root_plan["execution_manifest"], session
            )
        except analyzer.N3AnalysisError as error:
            raise N3FixedActionError(
                f"refusing to commit an invalid N3 session observation: {error}"
            ) from error
        session_payload = _canonical(session)
        session_sha = _sha256(session_payload)
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
    if session_payload is not None:
        _atomic_commit(
            result_dir / SESSION_OBSERVATION_FILENAME,
            session_payload,
            unknown_after_commit=False,
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


def _float_argument(value: str) -> float:
    try:
        return _temperature(float(value), label="temperature")
    except (ValueError, N3FixedActionError) as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--plan-file", type=Path, required=True)
    parser.add_argument("--action")
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
    parser.add_argument(
        "--confirm-reviewed-panel-build-and-exact-plan", action="store_true"
    )
    parser.add_argument(
        "--confirm-registered-measurement-assets-present", action="store_true"
    )
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
    if args.finalize_observation:
        if args.result_dir is None or args.observation_file is None:
            parser.error("finalization requires --result-dir and --observation-file")
        if args.action is not None:
            parser.error("finalization derives action identity from stored evidence")
        return args
    if args.action is None or args.evaluated_at is None:
        parser.error("describe/run requires --action and --evaluated-at")
    if args.describe_only:
        return args
    required = {
        "limit_profile": args.limit_profile,
        "result_dir": args.result_dir,
        "url": args.url,
        "confirm": args.confirm,
        "start_temperature_c": args.start_temperature_c,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        parser.error("live run missing: " + ", ".join(missing))
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        plan, plan_sha = load_n3_exact_plan_file(args.plan_file)
        if args.finalize_observation:
            output = finalize_n3_observation(
                plan,
                plan_sha,
                args.result_dir,
                args.observation_file,
                primer_result_file=args.primer_result,
            )
        elif args.describe_only:
            output = describe_n3_fixed_action(
                plan,
                args.action,
                limit_profile_file=args.limit_profile,
                evaluated_at=args.evaluated_at,
                primer_result_file=args.primer_result,
            )
        else:
            output = run_n3_fixed_action_once(
                plan,
                plan_sha,
                args.action,
                args.result_dir,
                args.url,
                limit_profile_file=args.limit_profile,
                evaluated_at=args.evaluated_at,
                authorization_confirmation=args.confirm,
                start_temperature_c=args.start_temperature_c,
                primer_result_file=args.primer_result,
                confirm_reviewed_panel_build_and_exact_plan=(
                    args.confirm_reviewed_panel_build_and_exact_plan
                ),
                confirm_registered_measurement_assets_present=(
                    args.confirm_registered_measurement_assets_present
                ),
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
    except (N3FixedActionError, execution.N3ExecutionContractError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CAMERA_CAPTURE_FILENAME",
    "DESCRIPTION_KIND",
    "N3FixedActionError",
    "N3FixedActionUnknown",
    "OPERATOR_OBSERVATION_KIND",
    "authorization_confirmation_sha256",
    "describe_n3_fixed_action",
    "finalize_n3_observation",
    "load_n3_exact_plan_file",
    "main",
    "parse_args",
    "required_authorization_confirmation",
    "run_n3_fixed_action_once",
]
