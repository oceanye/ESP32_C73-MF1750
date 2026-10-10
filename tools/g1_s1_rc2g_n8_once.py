#!/usr/bin/env python3
"""Describe, execute once, and manually finalize one exact N8 action.

The action selector is a closed enumeration of the fifteen frozen N8 actions.
Every run permanently consumes the workspace-global action claim before the
first network request, permits at most one ``POST /api/frame``, and contains no
retry, recovery, reset, serial, flashing, GPIO-control, or power-control path.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
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
)
from tools import g1_s1_n8_execution_contract as execution  # noqa: E402
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
MANIFEST_FILENAME = execution.MANIFEST_FILENAME
PROFILE_FILENAME = execution.PROFILE_FILENAME
EVIDENCE_FILENAME = execution.EVIDENCE_FILENAME
OBSERVATION_FILENAME = execution.OBSERVATION_FILENAME
FINALIZATION_FILENAME = execution.FINALIZATION_FILENAME
P0_RESULT_FILENAME = execution.P0_RESULT_FILENAME
BUNDLE_FILENAME = execution.BUNDLE_FILENAME
CAMERA_CAPTURE_FILENAME = execution.CAMERA_CAPTURE_FILENAME
PRIOR_BUNDLE_FILENAME = "N8-PRIOR-FINALIZED-ACTION-BUNDLE.json"
OPERATOR_OBSERVATION_KIND = "mf1750-g1-s1-rc2g-n8-operator-observation-input"

FIXED_ACTION_SHA256S = execution.FIXED_ACTION_SHA256S
FIXED_ACTION_KEYS = execution.FIXED_ACTION_KEYS
http_request = _quality.http_request

LEGACY_LIVE_BLOCK_MESSAGE = (
    "legacy N8 live execution is disabled: use the reviewed physical N8 "
    "campaign/runtime adapter after production approval"
)


class N8FixedActionError(RuntimeError):
    """An N8 action was rejected before its permanent claim existed."""


class N8FixedActionUnknown(N8FixedActionError):
    """The action claim exists; retry and recovery are forbidden."""


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
class _Prior:
    bundle: Mapping[str, Any]
    payload: bytes
    validated: Mapping[str, Any]


def _canonical(value: Any) -> bytes:
    try:
        return canonical_json_bytes(value)
    except CampaignContractError as error:
        raise N8FixedActionError(f"canonical JSON failed: {error}") from error


def _sha256(value: bytes | Mapping[str, Any]) -> str:
    return execution._sha256(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _strict_json_file(path: Path, *, label: str) -> tuple[Mapping[str, Any], bytes]:
    try:
        return _fixed._strict_json_file(path, label=label)
    except _fixed.N2PFixedActionError as error:
        raise N8FixedActionError(str(error)) from error


def _prepare_destination(path: Path) -> Path:
    try:
        return _fixed._prepare_result_destination(path)
    except _fixed.N2PFixedActionError as error:
        raise N8FixedActionError(str(error)) from error


def _claim_registry() -> Path:
    try:
        return _fixed._claim_registry()
    except _fixed.N2PFixedActionError as error:
        raise N8FixedActionError(str(error)) from error


def _atomic(path: Path, payload: bytes, *, unknown_after_commit: bool = False) -> None:
    try:
        _fixed._atomic_commit(path, payload, unknown_after_commit=unknown_after_commit)
    except _fixed.N2PFixedActionUnknown as error:
        raise N8FixedActionUnknown(str(error)) from error
    except _fixed.N2PFixedActionError as error:
        if unknown_after_commit:
            raise N8FixedActionUnknown(str(error)) from error
        raise N8FixedActionError(str(error)) from error


def _write_new(directory: Path, filename: str, value: Mapping[str, Any]) -> str:
    payload = _canonical(value)
    _atomic(directory / filename, payload)
    return _sha256(payload)


def _temperature(value: object, *, label: str) -> float:
    try:
        return _fixed._temperature(value, label=label)
    except _fixed.N2PFixedActionError as error:
        raise N8FixedActionError(str(error)) from error


def _rfc3339(value: object, *, label: str) -> datetime:
    try:
        return _fixed._rfc3339(value, label=label)
    except _fixed.N2PFixedActionError as error:
        raise N8FixedActionError(str(error)) from error


def _require_keys(value: object, keys: set[str], *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise N8FixedActionError(f"{label} fields differ from the fixed contract")
    return value


def required_authorization_confirmation(action_key: str) -> str:
    try:
        action_sha = FIXED_ACTION_SHA256S[action_key]
    except KeyError as error:
        raise N8FixedActionError("action is not one of 15 frozen N8 actions") from error
    return f"{execution.AUTHORIZATION_PREFIX}{action_sha.upper()}{execution.AUTHORIZATION_SUFFIX}"


def authorization_confirmation_sha256(action_key: str) -> str:
    return _sha256(required_authorization_confirmation(action_key).encode("ascii"))


def _load_runtime_manifest(path: Path) -> tuple[Mapping[str, Any], bytes, str]:
    root, payload = _strict_json_file(path, label="reviewed N8 runtime manifest")
    try:
        validated = execution.validate_n8_runtime_manifest(root)
    except execution.N8ExecutionContractError as error:
        raise N8FixedActionError(str(error)) from error
    if payload != _canonical(validated):
        raise N8FixedActionError("runtime manifest file is not canonical JSON bytes")
    return validated, payload, _sha256(payload)


def _load_prior(path: Path, snapshot: execution.N8ActionSnapshot) -> _Prior:
    bundle, payload = _strict_json_file(path, label="N8 exact prior finalized bundle")
    expected_sha = snapshot.action["identity"]["prior"]["action_identity_sha256"]
    expected_key = next(key for key, sha in FIXED_ACTION_SHA256S.items() if sha == expected_sha)
    try:
        validated = execution.validate_n8_finalized_action_bundle(
            execution.compile_n8_execution_contract(), bundle,
            expected_action_key=expected_key,
        )
    except execution.N8ExecutionContractError as error:
        raise N8FixedActionError(f"prior bundle failed deep validation: {error}") from error
    if validated["state"] != ResultState.PASS.value:
        raise N8FixedActionError("prior finalized bundle is not PASS")
    if payload != _canonical(bundle):
        raise N8FixedActionError("prior bundle file is not canonical JSON bytes")
    return _Prior(bundle=bundle, payload=payload, validated=validated)


def _prepare_inputs(
    snapshot: execution.N8ActionSnapshot,
    *,
    runtime_manifest_file: Optional[Path],
    evaluated_at: Optional[str],
    prior_bundle_file: Optional[Path],
) -> tuple[dict[str, Any], Optional[Mapping[str, Any]], Optional[bytes], Optional[str], Optional[_Prior]]:
    blockers: list[str] = []
    runtime: Optional[Mapping[str, Any]] = None
    manifest_payload: Optional[bytes] = None
    manifest_sha: Optional[str] = None
    prior: Optional[_Prior] = None
    p0_description: Optional[Mapping[str, Any]] = None
    if runtime_manifest_file is None:
        blockers.append("reviewed_runtime_manifest_missing")
    else:
        try:
            runtime, manifest_payload, manifest_sha = _load_runtime_manifest(runtime_manifest_file)
        except N8FixedActionError as error:
            blockers.append(f"runtime_manifest_not_ready:{error}")
    if evaluated_at is None:
        blockers.append("explicit_evaluated_at_missing")
    if snapshot.ordinal > 1 and prior_bundle_file is None:
        blockers.append("exact_prior_finalized_pass_bundle_missing")
    if snapshot.ordinal == 1 and prior_bundle_file is not None:
        raise N8FixedActionError("sequence root must not receive a prior bundle")
    if prior_bundle_file is not None:
        prior = _load_prior(prior_bundle_file, snapshot)
    if runtime is not None and evaluated_at is not None:
        try:
            p0_description = describe_action_offline(
                runtime["p0_campaign"],
                action_identity_sha256=snapshot.action["action_identity_sha256"],
                limit_profile=runtime["limit_profile"],
                evaluated_at=evaluated_at,
                prior_result=prior.bundle["result"] if prior else None,
                prior_result_sha256=prior.validated["result_file_sha256"] if prior else None,
            )
        except CampaignContractError as error:
            blockers.append(f"p0_description_failed:{error}")
        else:
            blockers.extend(
                blocker
                for blocker in p0_description["blockers"]
                if blocker
                != "current_runtime_gates_and_exact_authorization_not_evaluated"
            )
    blockers = list(dict.fromkeys(blockers))
    contract = execution.compile_n8_execution_contract()
    description = {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-g1-s1-rc2g-n8-fixed-action-description",
        "mode": "describe-only",
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "sequence_id": snapshot.sequence_id,
        "ordinal": snapshot.ordinal,
        "role": snapshot.role,
        "frame_source_id": snapshot.frame_source_id,
        "frame": dict(snapshot.action["identity"]["frame"]),
        "reference_preview": dict(snapshot.reference_preview),
        "power_mode": snapshot.power_mode,
        "temperature_bin_id": snapshot.temperature_bin_id,
        "dynamic_first_action_baseline": snapshot.ordinal == 1 and snapshot.power_mode == "supervised_continuous",
        "execution_contract_canonical_sha256": contract["integrity"]["canonical_sha256"],
        "execution_contract_file_sha256": execution.execution_contract_file_sha256(contract),
        "runtime_manifest_file_sha256": manifest_sha,
        "prior_bundle_file_sha256": _sha256(prior.payload) if prior else None,
        "prior_finalization_file_sha256": prior.validated["finalization_file_sha256"] if prior else None,
        "prior_result_file_sha256": prior.validated["result_file_sha256"] if prior else None,
        "p0_description": dict(p0_description) if p0_description else None,
        "contract_ready": bool(p0_description and p0_description["contract_ready"] and not blockers),
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "required_authorization_confirmation": required_authorization_confirmation(snapshot.key),
        "claim_created": False,
        "network_io_performed": False,
        "maximum_post_requests": 1,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
        "qualification_state": "NOT_QUALIFIED",
        "blockers": blockers,
    }
    return description, runtime, manifest_payload, manifest_sha, prior


def describe_n8_fixed_action(
    action_key: str,
    *,
    runtime_manifest_file: Optional[Path] = None,
    evaluated_at: Optional[str] = None,
    prior_bundle_file: Optional[Path] = None,
) -> dict[str, Any]:
    snapshot = execution.load_n8_action_snapshot(action_key)
    description, _runtime, _payload, _sha, _prior = _prepare_inputs(
        snapshot, runtime_manifest_file=runtime_manifest_file,
        evaluated_at=evaluated_at, prior_bundle_file=prior_bundle_file,
    )
    return description


def _confirmation_fields(snapshot: execution.N8ActionSnapshot) -> set[str]:
    common = {
        "reviewed_panel_and_build",
        "supervised_supply_cv_current_normal",
        "physical_cutoff_available",
        "single_visible_refresh",
        "external_temperature_instrument_verified",
        "fixed_camera_ready",
    }
    if snapshot.ordinal == 1 and snapshot.power_mode == "controller_fresh_boot":
        return {*common, "controller_fresh_boot"}
    if snapshot.ordinal == 1:
        return {*common, "controller_idle_no_inflight_job", "supervised_continuous_session_start"}
    return {
        *common,
        "prior_screen_fidelity_pass",
        "esp32_not_restarted_between_actions",
        "no_j2_disconnect_between_actions",
        "no_panel_power_cycle_between_actions",
        "no_other_visible_refresh_between_actions",
    }


def _claim_action(
    snapshot: execution.N8ActionSnapshot,
    *,
    attempt_id: str,
    claimed_at: str,
    destination: Path,
    runtime: Mapping[str, Any],
    manifest_sha: str,
    prior: Optional[_Prior],
    start_temperature_c: float,
    confirmations: Mapping[str, bool],
    authorization_confirmation: str,
) -> _Claim:
    contract = execution.compile_n8_execution_contract()
    profile = runtime["limit_profile"]
    profile_sha = _sha256(profile)
    record = {
        "schema_version": SCHEMA_VERSION,
        "kind": CLAIM_KIND,
        "registry_id": CLAIM_REGISTRY_ID,
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "execution_contract_canonical_sha256": contract["integrity"]["canonical_sha256"],
        "runtime_manifest_file_sha256": manifest_sha,
        "attempt_id": attempt_id,
        "claimed_at": claimed_at,
        "state": "authorization_permanently_consumed_do_not_rerun",
        "authorization_consumed_permanently": True,
        "authorization_confirmation_sha256": _sha256(authorization_confirmation.encode("ascii")),
        "profile_canonical_sha256": profile["integrity"]["canonical_sha256"],
        "profile_file_sha256": profile_sha,
        "prior_bundle_file_sha256": _sha256(prior.payload) if prior else None,
        "prior_finalization_file_sha256": prior.validated["finalization_file_sha256"] if prior else None,
        "prior_result_file_sha256": prior.validated["result_file_sha256"] if prior else None,
        "start_external_temperature_c": start_temperature_c,
        "confirmations": dict(confirmations),
        "result_directory": str(destination),
        "maximum_post_requests": 1,
        "automatic_retry_authorized": False,
        "automatic_recovery_authorized": False,
    }
    payload = _canonical(record)
    registry = _claim_registry()
    if _fixed._is_within(destination, registry):
        raise N8FixedActionError("result directory must not overlap claim registry")
    _atomic(registry / f"{snapshot.action['action_identity_sha256']}.json", payload, unknown_after_commit=True)
    return _Claim(record=record, file_sha256=_sha256(payload))


def _get_json(base_url: str, endpoint: str, *, label: str, requester: _quality._AuditedRequester) -> Mapping[str, Any]:
    return _quality._get_json_object(base_url, endpoint, label=label, requester=requester)


def _execute_protocol(
    snapshot: execution.N8ActionSnapshot,
    prior: Optional[_Prior],
    base_url: str,
    *,
    audit_sink: dict[str, Any],
    job_timeout_s: float,
    poll_interval_s: float,
    sleeper: Callable[[float], None],
    clock: Callable[[], float],
    protocol_contract_builder: Optional[Callable[..., Any]] = None,
    request_function: Optional[Callable[..., Any]] = None,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    build_protocol_contract = (
        execution.build_n8_protocol_contract
        if protocol_contract_builder is None
        else protocol_contract_builder
    )
    requester = _quality._AuditedRequester(
        http_request if request_function is None else request_function
    )
    try:
        if snapshot.ordinal == 1 and snapshot.power_mode == "controller_fresh_boot":
            preflight_mode = "controller_fresh_boot"
            preflight = _map._validate_fresh_boot_state(base_url, requester)
            prior_job, prior_operation = 0, 0
        elif snapshot.ordinal == 1:
            preflight_mode = "dynamic_first_action_baseline"
            try:
                version = _quality._preflight_version(
                    base_url, requester, _quality.FIXED_CONTROLLER_MAPPINGS
                )
            except _quality.FrameToolError as error:
                raise N8FixedActionError(f"warm baseline firmware preflight failed: {error}") from error
            _quality._validate_version(version, label="N8 warm baseline")
            preflight = {
                "version": dict(version),
                "job_raw": dict(_get_json(base_url, "/api/job", label="N8 warm baseline job", requester=requester)),
                "diagnostic_raw": dict(_get_json(base_url, "/api/diagnostic/report", label="N8 warm baseline diagnostic", requester=requester)),
                "gpio_status_raw": dict(_get_json(base_url, "/api/diagnostic/status", label="N8 warm baseline GPIO", requester=requester)),
                "controller_idle_no_inflight_confirmed": True,
            }
            prior_job, prior_operation = execution._validate_dynamic_preflight(preflight)
        else:
            if prior is None:
                raise N8FixedActionError("dependent action requires exact prior bundle")
            preflight_mode = "exact_finalized_prior"
            completed = prior.bundle["evidence"]["protocol_evidence"]["completed_action"]
            prior_job, prior_operation = completed["job_id"], completed["operation_id"]
            run_contract = build_protocol_contract(
                snapshot, prior_job_id=prior_job, prior_operation_id=prior_operation
            )
            preflight = _quality._validate_prior(
                base_url, requester, run_contract,
                expected_exact_prior_evidence={
                    "job_raw": completed["job_raw"],
                    "diagnostic_raw": completed["diagnostic_raw"],
                },
            )
        run_contract = build_protocol_contract(
            snapshot, prior_job_id=prior_job, prior_operation_id=prior_operation
        )
        report = _quality._perform_refresh_once(
            base_url, snapshot.frame, requester,
            job_timeout_s=job_timeout_s, poll_interval_s=poll_interval_s,
            sleeper=sleeper, clock=clock,
        )
        _quality._validate_network_report(report, run_contract)
        raw_job = _get_json(base_url, "/api/job", label="N8 immutable target job", requester=requester)
        if raw_job != report.get("job"):
            raise N8FixedActionError("target immutable job changed between reads")
        raw_diagnostic = _get_json(base_url, "/api/diagnostic/report", label="N8 immutable target diagnostic", requester=requester)
        normalized = _quality._validate_target_raw_diagnostic(raw_diagnostic, report, run_contract)
        gpio = _quality._validate_gpio_snapshot(
            _get_json(base_url, "/api/diagnostic/status", label="N8 post-refresh GPIO", requester=requester),
            label="N8 post-refresh GPIO",
        )
        protocol = {
            "preflight_mode": preflight_mode,
            "preflight": dict(preflight),
            "network_report": dict(report),
            "target_job_raw": dict(raw_job),
            "target_diagnostic_raw": dict(raw_diagnostic),
            "target_diagnostic_validated": dict(normalized),
            "post_refresh_gpio_status_raw": dict(gpio),
            "completed_action": {
                "job_id": run_contract.expected_target_job_id,
                "operation_id": run_contract.expected_target_operation_id,
                "frame_sha256": snapshot.action["identity"]["frame"]["sha256"],
                "frame_fnv1a": snapshot.action["identity"]["frame"]["fnv1a"],
                "job_raw": dict(raw_job),
                "diagnostic_raw": dict(raw_diagnostic),
            },
        }
        audit = requester.snapshot()
        if audit["post_attempt_count"] != 1 or audit["post_issued_count"] != 1:
            raise N8FixedActionError("N8 action did not issue exactly one POST /api/frame")
        return protocol, audit
    finally:
        audit_sink.clear()
        audit_sink.update(requester.snapshot())


def _base_evidence(
    snapshot: execution.N8ActionSnapshot,
    *,
    attempt_id: str,
    claimed_at: str,
    runtime: Mapping[str, Any],
    manifest_sha: str,
    claim: _Claim,
    evaluated_at: str,
    prior: Optional[_Prior],
    start_temperature_c: float,
) -> dict[str, Any]:
    contract = execution.compile_n8_execution_contract()
    profile = runtime["limit_profile"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EVIDENCE_KIND,
        "runner_kind": RUNNER_KIND,
        "attempt_id": attempt_id,
        "recorded_at": claimed_at,
        "protocol_completed_at": None,
        "profile_evaluated_at": evaluated_at,
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "sequence_id": snapshot.sequence_id,
        "ordinal": snapshot.ordinal,
        "role": snapshot.role,
        "frame_sha256": snapshot.action["identity"]["frame"]["sha256"],
        "reference_preview": dict(snapshot.reference_preview),
        "execution_contract_canonical_sha256": contract["integrity"]["canonical_sha256"],
        "execution_contract_file_sha256": execution.execution_contract_file_sha256(contract),
        "runtime_manifest_canonical_sha256": runtime["integrity"]["canonical_sha256"],
        "runtime_manifest_file_sha256": manifest_sha,
        "profile_canonical_sha256": profile["integrity"]["canonical_sha256"],
        "profile_file_sha256": _sha256(profile),
        "claim": claim.reference(),
        "prior_bundle_file_sha256": _sha256(prior.payload) if prior else None,
        "prior_finalization_file_sha256": prior.validated["finalization_file_sha256"] if prior else None,
        "prior_result_file_sha256": prior.validated["result_file_sha256"] if prior else None,
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
    }


def _record_unknown(
    destination: Optional[Path], base: Mapping[str, Any], *, requester_audit: Mapping[str, Any], error: BaseException
) -> None:
    if destination is None:
        return
    evidence = {
        **base,
        "protocol_completed_at": _utc_now(),
        "outcome": ResultState.UNKNOWN_DO_NOT_RETRY.value,
        "protocol_verified": False,
        "protocol_evidence": None,
        "request_audit": dict(requester_audit),
        "error": {"type": type(error).__name__, "message": str(error)},
    }
    if not (destination / EVIDENCE_FILENAME).exists():
        _write_new(destination, EVIDENCE_FILENAME, evidence)
    post_count = requester_audit.get("post_issued_count", 0)
    result = build_result_record(
        action_identity_sha256=base["action_identity_sha256"],
        state=ResultState.UNKNOWN_DO_NOT_RETRY,
        completed_at=_utc_now(),
        evidence_manifest_sha256=_sha256(evidence),
        post_request_count=post_count,
        details="claim consumed; no retry or recovery is permitted",
    )
    if not (destination / P0_RESULT_FILENAME).exists():
        _write_new(destination, P0_RESULT_FILENAME, result)


def _run_n8_fixed_action_once_legacy_test_only(
    action_key: str,
    result_dir: Path,
    base_url: str,
    *,
    runtime_manifest_file: Path,
    evaluated_at: str,
    authorization_confirmation: str,
    start_external_temperature_c: float,
    prior_bundle_file: Optional[Path] = None,
    confirmations: Optional[Mapping[str, bool]] = None,
    job_timeout_s: float = _quality.DEFAULT_JOB_TIMEOUT_S,
    poll_interval_s: float = _quality.DEFAULT_POLL_INTERVAL_S,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Exercise the frozen legacy protocol for offline regression fixtures only."""

    snapshot = execution.load_n8_action_snapshot(action_key)
    destination = _prepare_destination(result_dir)
    if not isinstance(base_url, str) or not base_url.strip():
        raise N8FixedActionError("base_url must be a non-empty device root URL")
    description, runtime, manifest_payload, manifest_sha, prior = _prepare_inputs(
        snapshot, runtime_manifest_file=runtime_manifest_file,
        evaluated_at=evaluated_at, prior_bundle_file=prior_bundle_file,
    )
    if not description["contract_ready"]:
        raise N8FixedActionError("reviewed N8 contract is not ready: " + ", ".join(description["blockers"]))
    assert runtime is not None and manifest_payload is not None and manifest_sha is not None
    start_temp = _temperature(start_external_temperature_c, label="start_external_temperature_c")
    limits = runtime["limit_profile"]["limits"]
    if not limits["minimum_start_temperature_c"] <= start_temp <= limits["maximum_start_temperature_c"]:
        raise N8FixedActionError("start external temperature is outside reviewed limits")
    supplied_confirmations = {} if confirmations is None else dict(confirmations)
    expected_fields = _confirmation_fields(snapshot)
    if set(supplied_confirmations) != expected_fields or any(type(item) is not bool or item is not True for item in supplied_confirmations.values()):
        raise N8FixedActionError("all and only action-specific N8 confirmations must be true")
    if authorization_confirmation != required_authorization_confirmation(action_key):
        raise N8FixedActionError("exact frozen N8 action authorization confirmation is required")

    attempt_id = uuid.uuid4().hex
    claimed_at = _utc_now()
    claim = _claim_action(
        snapshot, attempt_id=attempt_id, claimed_at=claimed_at,
        destination=destination, runtime=runtime, manifest_sha=manifest_sha,
        prior=prior, start_temperature_c=start_temp,
        confirmations=supplied_confirmations,
        authorization_confirmation=authorization_confirmation,
    )
    created: Optional[Path] = None
    audit_capture: dict[str, Any] = {"post_attempt_count": 0, "post_issued_count": 0, "calls": []}
    base = _base_evidence(
        snapshot, attempt_id=attempt_id, claimed_at=claimed_at,
        runtime=runtime, manifest_sha=manifest_sha, claim=claim,
        evaluated_at=evaluated_at, prior=prior, start_temperature_c=start_temp,
    )
    try:
        destination.mkdir()
        created = destination
        contract = execution.compile_n8_execution_contract()
        _write_new(destination, MANIFEST_FILENAME, runtime)
        _write_new(destination, PROFILE_FILENAME, runtime["limit_profile"])
        if prior is not None:
            _atomic(destination / PRIOR_BUNDLE_FILENAME, prior.payload)
        _write_new(
            destination, LOCK_FILENAME,
            {
                "schema_version": SCHEMA_VERSION,
                "kind": LOCK_KIND,
                "execution_contract_canonical_sha256": contract["integrity"]["canonical_sha256"],
                "attempt_id": attempt_id,
                "action_key": action_key,
                "action_identity_sha256": snapshot.action["action_identity_sha256"],
                "claim": claim.reference(),
                "confirmations": supplied_confirmations,
                "authorization_confirmation_sha256": authorization_confirmation_sha256(action_key),
                "state": "authorization_permanently_consumed_do_not_rerun",
                "automatic_retry_authorized": False,
                "automatic_recovery_authorized": False,
            },
        )
        protocol, audit = _execute_protocol(
            snapshot, prior, base_url, audit_sink=audit_capture,
            job_timeout_s=job_timeout_s, poll_interval_s=poll_interval_s,
            sleeper=sleeper, clock=clock,
        )
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
            _record_unknown(created, base, requester_audit=audit_capture, error=error)
        except BaseException:
            pass
        raise N8FixedActionUnknown(
            "N8 action is UNKNOWN_DO_NOT_RETRY; its workspace-global claim is permanent"
        ) from error


def run_n8_fixed_action_once(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """Reject the legacy live entry point before any claim or device I/O."""

    raise N8FixedActionError(LEGACY_LIVE_BLOCK_MESSAGE)


def _timing(protocol: Mapping[str, Any]) -> dict[str, float]:
    job = protocol["target_job_raw"]
    diagnostic = protocol["target_diagnostic_raw"]
    return {
        "queue_delay_ms": _quality._u32_duration(job["queued_at_ms"], job["started_at_ms"]),
        "job_duration_ms": _quality._u32_duration(job["started_at_ms"], job["finished_at_ms"]),
        "driver_total_ms": diagnostic["total_ms"],
        "cs1_upload_ms": diagnostic["cs1_upload_ms"],
        "cs2_upload_ms": diagnostic["cs2_upload_ms"],
        "pon_ms": diagnostic["pon_ms"],
        "drf_ms": diagnostic["drf_ms"],
        "pof_ms": diagnostic["pof_ms"],
        "post_psr_ms": diagnostic["post_psr_ms"],
    }


def _camera_input(
    value: Any, *, observation_file: Path, runtime: Mapping[str, Any]
) -> tuple[bytes, dict[str, Any]]:
    root = _require_keys(
        value,
        {"file", "capture_file_sha256", "capture_evidence_sha256"},
        label="N8 raw fixed-camera input",
    )
    if not isinstance(root["file"], str) or not root["file"]:
        raise N8FixedActionError("N8 raw fixed-camera file is required")
    capture = Path(root["file"])
    if not capture.is_absolute():
        capture = observation_file.parent / capture
    try:
        safe = _fixed._safe_regular_file(capture, label="N8 raw camera capture")
        payload = safe.read_bytes()
    except (_fixed.N2PFixedActionError, OSError) as error:
        raise N8FixedActionError(f"could not read N8 camera capture: {error}") from error
    declared = execution._require_sha256(root["capture_file_sha256"], label="camera capture")
    evidence_sha = execution._require_sha256(root["capture_evidence_sha256"], label="camera capture evidence")
    if _sha256(payload) != declared:
        raise N8FixedActionError("camera capture bytes do not match declared SHA")
    try:
        with Image.open(BytesIO(payload)) as opened:
            decoded_format = opened.format
            width, height = opened.size
            opened.verify()
    except (OSError, UnidentifiedImageError, ValueError) as error:
        raise N8FixedActionError(f"camera capture is not a valid image: {error}") from error
    registry = runtime["measurement_registry"]["camera"]
    return payload, {
        "capture_file_sha256": declared,
        "capture_evidence_sha256": evidence_sha,
        "body_asset_sha256": registry["body_asset_sha256"],
        "lens_asset_sha256": registry["lens_asset_sha256"],
        "mount_asset_sha256": registry["mount_asset_sha256"],
        "fixed_exposure_profile_sha256": registry["fixed_exposure_profile_sha256"],
        "crop_asset_sha256": registry["crop_asset_sha256"],
        "illumination_asset_sha256": registry["illumination_asset_sha256"],
        "copied_file": CAMERA_CAPTURE_FILENAME,
        "bytes": len(payload),
        "decoded_format": decoded_format,
        "width": width,
        "height": height,
    }


def _build_observation(
    source: Mapping[str, Any], source_payload: bytes, *,
    observation_file: Path, snapshot: execution.N8ActionSnapshot,
    runtime: Mapping[str, Any], evidence: Mapping[str, Any],
) -> tuple[dict[str, Any], bytes]:
    root = _require_keys(
        source,
        {"schema_version", "kind", "action_key", "action_identity_sha256", "observed_at", "reference_preview_sha256", "visual", "electrical", "external_temperature", "continuity", "camera"},
        label="N8 operator observation",
    )
    if (
        root["schema_version"] != SCHEMA_VERSION or root["kind"] != OPERATOR_OBSERVATION_KIND
        or root["action_key"] != snapshot.key or root["action_identity_sha256"] != snapshot.action["action_identity_sha256"]
        or root["reference_preview_sha256"] != snapshot.reference_preview["sha256"]
    ):
        raise N8FixedActionError("operator observation action/preview binding changed")
    observed = _rfc3339(root["observed_at"], label="observation.observed_at")
    protocol_completed = _rfc3339(evidence["protocol_completed_at"], label="protocol_completed_at")
    if observed < protocol_completed:
        raise N8FixedActionError("observation predates protocol completion")
    if observed > _rfc3339(_utc_now(), label="current time") + timedelta(minutes=15):
        raise N8FixedActionError("observation is implausibly far in the future")
    visual = _require_keys(
        root["visual"],
        {"fidelity_pass", "orientation_pass", "seam_assessment_pass", "full_panel_inspected", "all_six_colors_present", "no_retained_old_regions", "ghosting_score", "artifact_severity_score"},
        label="N8 visual input",
    )
    if any(type(visual[field]) is not bool for field in ("fidelity_pass", "orientation_pass", "seam_assessment_pass", "full_panel_inspected", "all_six_colors_present", "no_retained_old_regions")):
        raise N8FixedActionError("N8 visual flags must be boolean")
    execution._number(visual["ghosting_score"], label="ghosting score", minimum=0)
    execution._number(visual["artifact_severity_score"], label="artifact severity", minimum=0)
    visual_pass = all(visual[field] for field in ("fidelity_pass", "orientation_pass", "seam_assessment_pass", "full_panel_inspected", "all_six_colors_present", "no_retained_old_regions"))
    electrical = _require_keys(
        root["electrical"],
        {"meter_asset_sha256", "clock_asset_sha256", "pre_voltage_v", "pre_idle_current_a", "post_voltage_v", "post_idle_current_a", "peak_current_a", "constant_voltage_mode", "reviewed_limits_pass"},
        label="N8 electrical input",
    )
    registry = runtime["measurement_registry"]
    if electrical["meter_asset_sha256"] != registry["electrical"]["meter_asset_sha256"] or electrical["clock_asset_sha256"] != registry["timing"]["clock_asset_sha256"]:
        raise N8FixedActionError("N8 electrical/timing assets differ from runtime manifest")
    for field in ("pre_voltage_v", "pre_idle_current_a", "post_voltage_v", "post_idle_current_a", "peak_current_a"):
        execution._number(electrical[field], label=f"electrical.{field}", minimum=0)
    if type(electrical["constant_voltage_mode"]) is not bool or type(electrical["reviewed_limits_pass"]) is not bool:
        raise N8FixedActionError("electrical verdicts must be boolean")
    electrical_pass = electrical["constant_voltage_mode"] and electrical["reviewed_limits_pass"]
    stored_electrical = {**dict(electrical), "timing_ms": _timing(evidence["protocol_evidence"])}
    thermal = _require_keys(
        root["external_temperature"],
        {"pre_action_c", "post_action_c", "session_max_c", "uncertainty_u95_c", "sensor_asset_sha256", "calibration_artifact_sha256", "measurement_location_sha256", "measurement_evidence_sha256", "uncertainty_evidence_sha256"},
        label="N8 external temperature input",
    )
    pre = _temperature(thermal["pre_action_c"], label="external_temperature.pre_action_c")
    post = _temperature(thermal["post_action_c"], label="external_temperature.post_action_c")
    maximum = _temperature(thermal["session_max_c"], label="external_temperature.session_max_c")
    if maximum < max(pre, post):
        raise N8FixedActionError("session max temperature is below a sample")
    external = registry["external_temperature"]
    if any(thermal[field] != external[field] for field in ("sensor_asset_sha256", "calibration_artifact_sha256", "measurement_location_sha256", "uncertainty_u95_c")):
        raise N8FixedActionError("external temperature instrument evidence differs from runtime manifest")
    for field in ("measurement_evidence_sha256", "uncertainty_evidence_sha256"):
        execution._require_sha256(thermal[field], label=f"temperature.{field}")
    limits = runtime["limit_profile"]["limits"]
    thermal_pass = limits["minimum_start_temperature_c"] <= pre <= limits["maximum_start_temperature_c"] and post <= limits["maximum_post_refresh_temperature_c"] and maximum <= limits["maximum_post_refresh_temperature_c"]
    bin_pass = True
    if snapshot.temperature_bin_id is not None:
        bin_record = next(item for item in runtime["temperature_bin_plan"]["bins"] if item["bin_id"] == snapshot.temperature_bin_id)
        bin_pass = bin_record["minimum_c"] <= pre <= bin_record["maximum_c"]
    if snapshot.ordinal == 1:
        if root["continuity"] is not None:
            raise N8FixedActionError("sequence root continuity input must be null")
        continuity = None
        continuity_pass = True
    else:
        continuity = _require_keys(
            root["continuity"],
            {"controller_reboot_between_actions", "panel_power_cycle_between_actions", "j2_disconnect_between_actions", "other_visible_refresh_between_actions"},
            label="N8 continuity input",
        )
        if any(type(item) is not bool for item in continuity.values()):
            raise N8FixedActionError("continuity flags must be boolean")
        continuity_pass = not any(continuity.values())
    camera_payload, camera = _camera_input(root["camera"], observation_file=observation_file, runtime=runtime)
    state = ResultState.PASS.value if visual_pass and electrical_pass and thermal_pass and bin_pass and continuity_pass else ResultState.FAIL.value
    stored = {
        "schema_version": SCHEMA_VERSION,
        "kind": OBSERVATION_KIND,
        "attempt_id": evidence["attempt_id"],
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "sequence_id": snapshot.sequence_id,
        "ordinal": snapshot.ordinal,
        "role": snapshot.role,
        "observed_at": root["observed_at"],
        "reference_preview_sha256": snapshot.reference_preview["sha256"],
        "visual": dict(visual),
        "electrical": stored_electrical,
        "external_temperature": dict(thermal),
        "continuity": dict(continuity) if continuity is not None else None,
        "camera": camera,
        "source_observation_file_sha256": _sha256(source_payload),
        "visual_pass": visual_pass,
        "electrical_pass": electrical_pass,
        "thermal_pass": thermal_pass,
        "temperature_bin_pass": bin_pass,
        "continuity_pass": continuity_pass,
        "overall_state": state,
        "qualification_state": "NOT_QUALIFIED",
    }
    return stored, camera_payload


def _load_claim(reference: Mapping[str, Any]) -> tuple[Mapping[str, Any], str]:
    filename = reference.get("filename")
    if not isinstance(filename, str) or filename != f"{reference.get('action_identity_sha256')}.json":
        raise N8FixedActionError("claim reference filename changed")
    claim, payload = _strict_json_file(_claim_registry() / filename, label="N8 workspace-global claim")
    if _sha256(payload) != reference.get("file_sha256"):
        raise N8FixedActionError("workspace-global claim whole-file SHA changed")
    return claim, _sha256(payload)


def finalize_n8_observation(
    result_dir: Path,
    operator_observation_file: Path,
    *,
    expected_action_key: Optional[str] = None,
) -> dict[str, Any]:
    """Finalize protocol evidence with a separate human/camera observation."""

    destination = result_dir.resolve()
    manifest, manifest_payload = _strict_json_file(destination / MANIFEST_FILENAME, label="stored N8 runtime manifest")
    runtime = execution.validate_n8_runtime_manifest(manifest)
    profile, profile_payload = _strict_json_file(destination / PROFILE_FILENAME, label="stored N8 profile")
    if profile != runtime["limit_profile"]:
        raise N8FixedActionError("stored profile differs from stored runtime manifest")
    lock, lock_payload = _strict_json_file(destination / LOCK_FILENAME, label="stored N8 lock")
    evidence, evidence_payload = _strict_json_file(destination / EVIDENCE_FILENAME, label="stored N8 protocol evidence")
    if evidence.get("outcome") != "protocol_verified_observation_pending" or evidence.get("protocol_verified") is not True:
        raise N8FixedActionError("N8 protocol evidence is not ready for manual finalization")
    snapshot = execution.load_n8_action_snapshot(evidence["action_key"])
    if expected_action_key is not None and snapshot.key != expected_action_key:
        raise N8FixedActionError("finalize action selector differs from stored evidence")
    claim, claim_sha = _load_claim(evidence["claim"])
    prior_bundle: Optional[Mapping[str, Any]] = None
    prior_sha: Optional[str] = None
    if snapshot.ordinal > 1:
        prior_bundle, prior_payload = _strict_json_file(destination / PRIOR_BUNDLE_FILENAME, label="stored N8 prior bundle")
        prior_sha = _sha256(prior_payload)
        if prior_sha != evidence["prior_bundle_file_sha256"]:
            raise N8FixedActionError("stored prior bundle whole-file SHA changed")
    source, source_payload = _strict_json_file(operator_observation_file, label="N8 operator observation input")
    observation, camera_payload = _build_observation(
        source, source_payload, observation_file=operator_observation_file,
        snapshot=snapshot, runtime=runtime, evidence=evidence,
    )
    _atomic(destination / CAMERA_CAPTURE_FILENAME, camera_payload)
    observation_sha = _write_new(destination, OBSERVATION_FILENAME, observation)
    finalization = {
        "schema_version": SCHEMA_VERSION,
        "kind": FINALIZATION_KIND,
        "attempt_id": evidence["attempt_id"],
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "sequence_id": snapshot.sequence_id,
        "ordinal": snapshot.ordinal,
        "state": observation["overall_state"],
        "manifest_file_sha256": _sha256(manifest_payload),
        "claim_file_sha256": claim_sha,
        "lock_file_sha256": _sha256(lock_payload),
        "profile_file_sha256": _sha256(profile_payload),
        "protocol_evidence_file_sha256": _sha256(evidence_payload),
        "action_observation_file_sha256": observation_sha,
        "prior_bundle_file_sha256": prior_sha,
        "prior_finalization_file_sha256": evidence["prior_finalization_file_sha256"],
        "prior_result_file_sha256": evidence["prior_result_file_sha256"],
        "visual_pass": observation["visual_pass"],
        "electrical_pass": observation["electrical_pass"],
        "thermal_pass": observation["thermal_pass"],
        "temperature_bin_pass": observation["temperature_bin_pass"],
        "continuity_pass": observation["continuity_pass"],
        "camera_capture_file_sha256": observation["camera"]["capture_file_sha256"],
        "visual_electrical_thermal_continuity_assessed_separately": True,
        "automatic_retry_count": 0,
        "retry_allowed": False,
        "recovery_performed": False,
        "qualification_state": "NOT_QUALIFIED",
    }
    finalization_sha = _write_new(destination, FINALIZATION_FILENAME, finalization)
    result = build_result_record(
        action_identity_sha256=snapshot.action["action_identity_sha256"],
        state=ResultState(observation["overall_state"]),
        completed_at=observation["observed_at"],
        evidence_manifest_sha256=finalization_sha,
        post_request_count=1,
        details="N8 manual observation finalized; campaign remains NOT_QUALIFIED",
    )
    result_sha = _write_new(destination, P0_RESULT_FILENAME, result)
    records = {
        "manifest": (manifest, _sha256(manifest_payload)),
        "claim": (claim, claim_sha),
        "lock": (lock, _sha256(lock_payload)),
        "profile": (profile, _sha256(profile_payload)),
        "evidence": (evidence, _sha256(evidence_payload)),
        "observation": (observation, observation_sha),
        "finalization": (finalization, finalization_sha),
        "result": (result, result_sha),
    }
    bundle: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "kind": BUNDLE_KIND}
    for name, (record, digest) in records.items():
        bundle[name] = record
        bundle[f"{name}_file_sha256"] = digest
    bundle.update(
        {
            "prior_bundle": prior_bundle,
            "prior_bundle_file_sha256": prior_sha,
            "qualification_state": "NOT_QUALIFIED",
        }
    )
    validated = execution.validate_n8_finalized_action_bundle(
        execution.compile_n8_execution_contract(), bundle,
        expected_action_key=snapshot.key,
    )
    _write_new(destination, BUNDLE_FILENAME, bundle)
    return {"bundle": bundle, "bundle_file_sha256": _sha256(bundle), "validated": validated}


def load_n8_finalized_action_bundle(path: Path) -> dict[str, Any]:
    bundle, payload = _strict_json_file(path, label="N8 finalized action bundle")
    execution.validate_n8_finalized_action_bundle(execution.compile_n8_execution_contract(), bundle)
    if payload != _canonical(bundle):
        raise N8FixedActionError("N8 bundle is not canonical JSON bytes")
    return dict(bundle)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=FIXED_ACTION_KEYS, required=True)
    parser.add_argument("--describe-only", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--runtime-manifest", type=Path)
    parser.add_argument("--evaluated-at")
    parser.add_argument("--prior-bundle", type=Path)
    parser.add_argument("--result-dir", type=Path)
    parser.add_argument("--base-url")
    parser.add_argument("--authorization-confirmation")
    parser.add_argument("--start-external-temperature-c", type=float)
    parser.add_argument("--operator-observation", type=Path)
    parser.add_argument("--confirm-reviewed-panel-and-build", action="store_true")
    parser.add_argument("--confirm-supervised-supply-cv-current-normal", action="store_true")
    parser.add_argument("--confirm-physical-cutoff-available", action="store_true")
    parser.add_argument("--confirm-single-visible-refresh", action="store_true")
    parser.add_argument("--confirm-external-temperature-instrument-verified", action="store_true")
    parser.add_argument("--confirm-fixed-camera-ready", action="store_true")
    parser.add_argument("--confirm-controller-fresh-boot", action="store_true")
    parser.add_argument("--confirm-controller-idle-no-inflight-job", action="store_true")
    parser.add_argument("--confirm-supervised-continuous-session-start", action="store_true")
    parser.add_argument("--confirm-prior-screen-fidelity-pass", action="store_true")
    parser.add_argument("--confirm-esp32-not-restarted-between-actions", action="store_true")
    parser.add_argument("--confirm-no-j2-disconnect-between-actions", action="store_true")
    parser.add_argument("--confirm-no-panel-power-cycle-between-actions", action="store_true")
    parser.add_argument("--confirm-no-other-visible-refresh-between-actions", action="store_true")
    return parser.parse_args(argv)


def _cli_confirmations(args: argparse.Namespace, snapshot: execution.N8ActionSnapshot) -> dict[str, bool]:
    values = {
        "reviewed_panel_and_build": args.confirm_reviewed_panel_and_build,
        "supervised_supply_cv_current_normal": args.confirm_supervised_supply_cv_current_normal,
        "physical_cutoff_available": args.confirm_physical_cutoff_available,
        "single_visible_refresh": args.confirm_single_visible_refresh,
        "external_temperature_instrument_verified": args.confirm_external_temperature_instrument_verified,
        "fixed_camera_ready": args.confirm_fixed_camera_ready,
        "controller_fresh_boot": args.confirm_controller_fresh_boot,
        "controller_idle_no_inflight_job": args.confirm_controller_idle_no_inflight_job,
        "supervised_continuous_session_start": args.confirm_supervised_continuous_session_start,
        "prior_screen_fidelity_pass": args.confirm_prior_screen_fidelity_pass,
        "esp32_not_restarted_between_actions": args.confirm_esp32_not_restarted_between_actions,
        "no_j2_disconnect_between_actions": args.confirm_no_j2_disconnect_between_actions,
        "no_panel_power_cycle_between_actions": args.confirm_no_panel_power_cycle_between_actions,
        "no_other_visible_refresh_between_actions": args.confirm_no_other_visible_refresh_between_actions,
    }
    return {key: values[key] for key in _confirmation_fields(snapshot)}


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    snapshot = execution.load_n8_action_snapshot(args.action)
    if args.describe_only:
        value = describe_n8_fixed_action(
            args.action, runtime_manifest_file=args.runtime_manifest,
            evaluated_at=args.evaluated_at, prior_bundle_file=args.prior_bundle,
        )
    elif args.finalize:
        if args.result_dir is None or args.operator_observation is None:
            raise N8FixedActionError("--finalize requires --result-dir and --operator-observation")
        value = finalize_n8_observation(
            args.result_dir,
            args.operator_observation,
            expected_action_key=args.action,
        )
    else:
        required = {
            "--runtime-manifest": args.runtime_manifest,
            "--evaluated-at": args.evaluated_at,
            "--result-dir": args.result_dir,
            "--base-url": args.base_url,
            "--authorization-confirmation": args.authorization_confirmation,
            "--start-external-temperature-c": args.start_external_temperature_c,
        }
        missing = [key for key, value in required.items() if value is None]
        if missing:
            raise N8FixedActionError("run mode is missing: " + ", ".join(missing))
        value = run_n8_fixed_action_once(
            args.action, args.result_dir, args.base_url,
            runtime_manifest_file=args.runtime_manifest,
            evaluated_at=args.evaluated_at,
            authorization_confirmation=args.authorization_confirmation,
            start_external_temperature_c=args.start_external_temperature_c,
            prior_bundle_file=args.prior_bundle,
            confirmations=_cli_confirmations(args, snapshot),
        )
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
