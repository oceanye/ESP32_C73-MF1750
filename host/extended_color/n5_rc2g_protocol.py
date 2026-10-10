"""Strict RC2G protocol adapter for one already-claimed N5 action.

The N5 execution core owns authorization, the workspace-global claim, and
the outer request audit.  This module only supplies the post-claim RC2G
protocol driver.  Every device request is bridged through that outer audited
transport and is then checked again by the proven N2/N4 RC2G validators.

No function in this module retries, recovers, advances to another action, or
controls panel power.  The replay validators are pure and perform no I/O.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
import hashlib
import json
import math
import time
from typing import Any, Optional

from host.extended_color import execution
from host.visible_refresh_campaign import ResultState, canonical_json_bytes
from tools import g1_s1_rc2g_map_baseline_once as _map
from tools import g1_s1_rc2g_quality_refresh_once as _quality
from tools import mf1750_frame_tool as _frame_tool


SCHEMA_VERSION = 1
DEVICE_EVIDENCE_KIND = "mf1750-n5-strict-rc2g-device-evidence"

PREFLIGHT_PANEL_COLD = "panel-cold-fresh-job0"
PREFLIGHT_SUPERVISED_FRESH = "supervised-live-fresh-job0"
PREFLIGHT_SUPERVISED_COMPLETED = "supervised-live-completed"
PREFLIGHT_EXACT_PREDECESSOR = "same-session-exact-predecessor"

_FRESH_JOB = {
    "job_id": 0,
    "action": "none",
    "state": "idle",
    "result": None,
    "queued_at_ms": 0,
    "started_at_ms": 0,
    "finished_at_ms": 0,
    "frame_fnv1a": 0,
}
_FRESH_DIAGNOSTIC = {
    "schema_version": 2,
    "valid": False,
    "error": "no_completed_job_report",
}
_JOB_KEYS = {
    "job_id",
    "action",
    "state",
    "result",
    "queued_at_ms",
    "started_at_ms",
    "finished_at_ms",
    "frame_fnv1a",
}
_PREFLIGHT_KEYS = {
    "version",
    "job_raw",
    "diagnostic_raw",
    "normalized_busy_trace",
    "gpio_status_raw",
    "gpio",
}
_EVIDENCE_KEYS = {
    "schema_version",
    "kind",
    "action_key",
    "action_identity_sha256",
    "execution_contract_canonical_sha256",
    "session_id",
    "preflight_mode",
    "preflight",
    "network_report",
    "target_job_raw",
    "target_diagnostic_raw",
    "target_diagnostic_validated",
    "post_refresh_gpio_status_raw",
    "post_refresh_gpio",
    "strict_request_audit",
    "wire_responses",
    "completed_action",
    "maximum_post_requests",
    "automatic_advance",
    "automatic_retry",
    "automatic_recovery",
}
_COMPLETED_KEYS = {
    "job_id",
    "operation_id",
    "frame_sha256",
    "frame_fnv1a",
    "cs1_dtm_fnv1a",
    "cs2_dtm_fnv1a",
    "job_raw_sha256",
    "diagnostic_raw_sha256",
}
_ALLOWED_ROUTES = {
    ("GET", "/api/version"),
    ("GET", "/api/job"),
    ("GET", "/api/diagnostic/report"),
    ("GET", "/api/diagnostic/status"),
    ("POST", "/api/frame"),
}


class N5Rc2gProtocolError(execution.N5ExecutionError):
    """Strict N5 RC2G evidence or configuration is invalid."""


def _exact(value: object, *, label: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        actual = set(value) if isinstance(value, Mapping) else set()
        raise N5Rc2gProtocolError(
            f"{label} fields changed; missing={sorted(keys - actual)}, "
            f"extra={sorted(actual - keys)}"
        )
    return value


def _sha256(value: object) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _u32(value: object, *, label: str, nonzero: bool = False) -> int:
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
        raise N5Rc2gProtocolError(f"{label} must be an unsigned 32-bit integer")
    if nonzero and value == 0:
        raise N5Rc2gProtocolError(f"{label} must be non-zero")
    return value


def _hex_u32(value: object, *, label: str) -> int:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise N5Rc2gProtocolError(f"{label} must be a 0x-prefixed uint32")
    try:
        parsed = int(value, 16)
    except ValueError as error:
        raise N5Rc2gProtocolError(f"{label} is not hexadecimal") from error
    return _u32(parsed, label=label)


def _next_nonzero_u32(value: int) -> int:
    result = (value + 1) & 0xFFFFFFFF
    return 1 if result == 0 else result


def _session_position(
    snapshot: execution.ActionSnapshot,
) -> tuple[bool, Optional[str]]:
    identities = snapshot.session.get("action_identity_sha256s")
    if not isinstance(identities, list) or not identities:
        raise N5Rc2gProtocolError("N5 session action sequence is absent")
    action_sha = snapshot.action["action_identity_sha256"]
    try:
        index = identities.index(action_sha)
    except ValueError as error:
        raise N5Rc2gProtocolError("N5 action is absent from its session") from error
    if identities.count(action_sha) != 1:
        raise N5Rc2gProtocolError("N5 session duplicates the selected action")
    return index == 0, None if index == 0 else str(identities[index - 1])


def _candidate_snapshot(
    snapshot: execution.ActionSnapshot, frame: bytes
) -> _quality._CandidateSnapshot:
    frame_record = snapshot.action["identity"]["frame"]
    controllers = frame_record.get("controllers")
    if not isinstance(controllers, list) or len(controllers) != 2:
        raise N5Rc2gProtocolError("N5 frame lacks two physical controller records")
    if _sha256(frame) != frame_record.get("sha256"):
        raise N5Rc2gProtocolError("N5 frame bytes differ from the frozen action")
    frame_fnv1a = _hex_u32(frame_record.get("fnv1a"), label="N5 frame FNV-1a")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-n5-strict-rc2g-candidate-binding",
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "frame": frame_record,
    }
    manifest_bytes = canonical_json_bytes(manifest)
    return _quality._CandidateSnapshot(
        directory=Path("."),
        manifest=manifest,
        manifest_bytes=manifest_bytes,
        manifest_file_sha256=_sha256(manifest_bytes),
        manifest_canonical_sha256=_sha256(manifest),
        algorithm=f"n5:{snapshot.key}",
        frame=frame,
        frame_sha256=str(frame_record["sha256"]),
        frame_fnv1a=frame_fnv1a,
        controllers=(dict(controllers[0]), dict(controllers[1])),
    )


def _run_contract(
    candidate: _quality._CandidateSnapshot,
    *,
    prior_job_id: int,
    prior_operation_id: int,
    prior_frame_sha256: Optional[str],
    prior_frame_fnv1a: int,
    prior_cs1_dtm_fnv1a: int,
    prior_cs2_dtm_fnv1a: int,
    target_job_id: int,
    target_operation_id: int,
    prior_scope: str,
) -> _quality._RunContract:
    prior_identity = {
        "job_id": prior_job_id,
        "operation_id": prior_operation_id,
        "frame_sha256": prior_frame_sha256,
        "frame_sha256_evidence_scope": prior_scope,
        "frame_fnv1a": prior_frame_fnv1a,
        "cs1_dtm_fnv1a": prior_cs1_dtm_fnv1a,
        "cs2_dtm_fnv1a": prior_cs2_dtm_fnv1a,
    }
    action_identity = {
        "schema_version": SCHEMA_VERSION,
        "kind": "mf1750-n5-strict-rc2g-action-binding",
        "n5_action_identity_sha256": candidate.manifest[
            "action_identity_sha256"
        ],
        "prior": prior_identity,
        "target": {
            "job_id": target_job_id,
            "operation_id": target_operation_id,
            "frame_sha256": candidate.frame_sha256,
            "frame_fnv1a": candidate.frame_fnv1a,
        },
    }
    return _quality._RunContract(
        snapshot=candidate,
        expected_prior_job_id=prior_job_id,
        expected_prior_operation_id=prior_operation_id,
        expected_prior_frame_sha256=prior_frame_sha256 or "0" * 64,
        expected_prior_frame_fnv1a=prior_frame_fnv1a,
        expected_prior_cs1_dtm_fnv1a=prior_cs1_dtm_fnv1a,
        expected_prior_cs2_dtm_fnv1a=prior_cs2_dtm_fnv1a,
        expected_target_job_id=target_job_id,
        expected_target_operation_id=target_operation_id,
        action_identity=action_identity,
        action_identity_sha256=_sha256(action_identity),
        required_authorization_confirmation="external-N5-authorization-only",
    )


def _fresh_run_contract(
    candidate: _quality._CandidateSnapshot,
) -> _quality._RunContract:
    return _run_contract(
        candidate,
        prior_job_id=0,
        prior_operation_id=0,
        prior_frame_sha256=None,
        prior_frame_fnv1a=0,
        prior_cs1_dtm_fnv1a=0,
        prior_cs2_dtm_fnv1a=0,
        target_job_id=1,
        target_operation_id=1,
        prior_scope="strict fresh job0/no completed diagnostic",
    )


def _completed_run_contract(
    candidate: _quality._CandidateSnapshot,
    job: Mapping[str, Any],
    diagnostic: Mapping[str, Any],
    *,
    prior_frame_sha256: Optional[str],
    prior_scope: str,
) -> _quality._RunContract:
    prior_job_id = _u32(job.get("job_id"), label="prior job id", nonzero=True)
    prior_operation_id = _u32(
        diagnostic.get("operation_id"),
        label="prior operation id",
        nonzero=True,
    )
    if diagnostic.get("job_operation_id") != prior_operation_id:
        raise N5Rc2gProtocolError("prior job/driver operation identity differs")
    return _run_contract(
        candidate,
        prior_job_id=prior_job_id,
        prior_operation_id=prior_operation_id,
        prior_frame_sha256=prior_frame_sha256,
        prior_frame_fnv1a=_u32(job.get("frame_fnv1a"), label="prior frame FNV-1a"),
        prior_cs1_dtm_fnv1a=_u32(
            diagnostic.get("cs1_dtm_fnv1a"), label="prior CS1 DTM FNV-1a"
        ),
        prior_cs2_dtm_fnv1a=_u32(
            diagnostic.get("cs2_dtm_fnv1a"), label="prior CS2 DTM FNV-1a"
        ),
        target_job_id=_next_nonzero_u32(prior_job_id),
        target_operation_id=_next_nonzero_u32(prior_operation_id),
        prior_scope=prior_scope,
    )


def _validate_version(version: Mapping[str, Any]) -> None:
    try:
        _quality._validate_version(version, label="N5 strict RC2G preflight")
    except (_quality.Rc2gQualityRefreshError, _frame_tool.FrameToolError) as error:
        raise N5Rc2gProtocolError(str(error)) from error


def _validate_fresh_records(
    version: Mapping[str, Any],
    job: Mapping[str, Any],
    diagnostic: Mapping[str, Any],
    gpio_raw: Mapping[str, Any],
) -> dict[str, Any]:
    _validate_version(version)
    if dict(job) != _FRESH_JOB or dict(diagnostic) != _FRESH_DIAGNOSTIC:
        raise N5Rc2gProtocolError(
            "RC2G preflight is not exact fresh job0/no-completed-report state"
        )
    try:
        gpio = _quality._validate_gpio_snapshot(
            gpio_raw, label="N5 strict fresh GPIO"
        )
    except _quality.Rc2gQualityRefreshError as error:
        raise N5Rc2gProtocolError(str(error)) from error
    return {
        "version": dict(version),
        "job_raw": dict(job),
        "diagnostic_raw": dict(diagnostic),
        "normalized_busy_trace": None,
        "gpio_status_raw": dict(gpio_raw),
        "gpio": _quality._gpio_evidence(gpio),
    }


def _validate_completed_records(
    run: _quality._RunContract,
    version: Mapping[str, Any],
    job: Mapping[str, Any],
    diagnostic: Mapping[str, Any],
    gpio_raw: Mapping[str, Any],
) -> dict[str, Any]:
    _validate_version(version)
    if set(job) != _JOB_KEYS:
        raise N5Rc2gProtocolError("prior job fields are not the strict contract")
    try:
        state = _quality._validate_job(
            job, run.expected_prior_job_id, run.expected_prior_frame_fnv1a
        )
        if state != "completed":
            raise N5Rc2gProtocolError("prior RC2G job is not completed")
        trace = _quality._validate_prior_raw_diagnostic(diagnostic, job, run)
        gpio = _quality._validate_gpio_snapshot(
            gpio_raw, label="N5 strict prior GPIO"
        )
    except (_quality.Rc2gQualityRefreshError, _frame_tool.FrameToolError) as error:
        raise N5Rc2gProtocolError(str(error)) from error
    return {
        "version": dict(version),
        "job_raw": dict(job),
        "diagnostic_raw": dict(diagnostic),
        "normalized_busy_trace": dict(trace),
        "gpio_status_raw": dict(gpio_raw),
        "gpio": _quality._gpio_evidence(gpio),
    }


def _read_version(
    base_url: str, requester: _quality._AuditedRequester
) -> Mapping[str, Any]:
    try:
        version = _quality._preflight_version(
            base_url, requester, _quality.FIXED_CONTROLLER_MAPPINGS
        )
    except _frame_tool.FrameToolError as error:
        raise N5Rc2gProtocolError(
            f"N5 strict RC2G firmware preflight failed: {error}"
        ) from error
    _validate_version(version)
    return version


def _read_json(
    base_url: str,
    endpoint: str,
    *,
    label: str,
    requester: _quality._AuditedRequester,
) -> Mapping[str, Any]:
    try:
        return _map._get_json_object(
            base_url, endpoint, label=label, requester=requester
        )
    except _map.Rc2gMapBaselineError as error:
        raise N5Rc2gProtocolError(str(error)) from error


def _read_preflight(
    base_url: str,
    requester: _quality._AuditedRequester,
    candidate: _quality._CandidateSnapshot,
    *,
    mode: str,
    expected_prior: Optional[Mapping[str, Any]],
) -> tuple[dict[str, Any], _quality._RunContract]:
    version = _read_version(base_url, requester)
    job = _read_json(
        base_url, "/api/job", label="N5 strict prior job", requester=requester
    )
    diagnostic = _read_json(
        base_url,
        "/api/diagnostic/report",
        label="N5 strict prior diagnostic",
        requester=requester,
    )
    gpio_raw = _read_json(
        base_url,
        "/api/diagnostic/status",
        label="N5 strict prior GPIO",
        requester=requester,
    )
    if mode in {PREFLIGHT_PANEL_COLD, PREFLIGHT_SUPERVISED_FRESH}:
        if expected_prior is not None:
            raise N5Rc2gProtocolError("fresh preflight cannot bind completed evidence")
        return _validate_fresh_records(version, job, diagnostic, gpio_raw), (
            _fresh_run_contract(candidate)
        )
    if mode == PREFLIGHT_SUPERVISED_COMPLETED:
        if expected_prior is not None:
            raise N5Rc2gProtocolError(
                "dynamic supervised preflight cannot bind a stored predecessor"
            )
        run = _completed_run_contract(
            candidate,
            job,
            diagnostic,
            prior_frame_sha256=None,
            prior_scope="live strict RC2G report; firmware does not expose SHA-256",
        )
    elif mode == PREFLIGHT_EXACT_PREDECESSOR:
        if expected_prior is None:
            raise N5Rc2gProtocolError(
                "same-session action lacks exact predecessor RC2G evidence"
            )
        expected_job = expected_prior.get("target_job_raw")
        expected_diagnostic = expected_prior.get("target_diagnostic_raw")
        expected_completed = expected_prior.get("completed_action")
        if (
            not isinstance(expected_job, Mapping)
            or not isinstance(expected_diagnostic, Mapping)
            or not isinstance(expected_completed, Mapping)
            or dict(job) != dict(expected_job)
            or dict(diagnostic) != dict(expected_diagnostic)
        ):
            raise N5Rc2gProtocolError(
                "live prior is not the exact stored preceding job/operation evidence"
            )
        run = _completed_run_contract(
            candidate,
            job,
            diagnostic,
            prior_frame_sha256=str(expected_completed.get("frame_sha256")),
            prior_scope="exact preceding finalized N5 strict device evidence",
        )
    else:
        raise N5Rc2gProtocolError("unknown N5 RC2G preflight mode")
    return _validate_completed_records(
        run, version, job, diagnostic, gpio_raw
    ), run


def _bridge_requester(
    audited: execution.AuditedTransport, *, base_url: str
) -> tuple[_quality._AuditedRequester, list[dict[str, Any]]]:
    wire_responses: list[dict[str, Any]] = []

    def bridge(
        requested_base_url: str,
        endpoint: str,
        *,
        method: str,
        data: Optional[bytes],
        timeout: float,
    ) -> tuple[int, str]:
        del timeout
        if requested_base_url != base_url:
            raise N5Rc2gProtocolError("RC2G helper changed the frozen device URL")
        response = audited.request(method, endpoint, data)
        if (
            not isinstance(response, tuple)
            or len(response) != 2
            or type(response[0]) is not int
            or not isinstance(response[1], str)
        ):
            raise N5Rc2gProtocolError(
                "RC2G transport must return an integer status and text body"
            )
        wire_responses.append(
            {
                "index": len(wire_responses) + 1,
                "method": method.upper(),
                "endpoint": endpoint,
                "status": response[0],
                "response_body": response[1],
            }
        )
        return response

    return _quality._AuditedRequester(bridge), wire_responses


def _extract_item(
    contract: Mapping[str, Any],
    prior_bundle: Optional[Mapping[str, Any]],
    expected_sha256: Optional[str],
) -> Optional[Mapping[str, Any]]:
    if expected_sha256 is None:
        return None
    if prior_bundle is None:
        raise N5Rc2gProtocolError("dependent N5 action lacks a prior action item")
    if prior_bundle.get("kind") == execution.BUNDLE_KIND:
        execution.validate_finalized_bundle(contract, prior_bundle)
        matches = [
            item
            for item in prior_bundle["actions"]
            if item.get("action_identity_sha256") == expected_sha256
        ]
        if len(matches) != 1:
            raise N5Rc2gProtocolError(
                "prior finalized bundle lacks the exact predecessor item"
            )
        item = matches[0]
    else:
        item = prior_bundle
    summary = execution._validate_action_item(contract, item)
    if (
        summary["action_identity_sha256"] != expected_sha256
        or summary["state"] != ResultState.PASS.value
    ):
        raise N5Rc2gProtocolError(
            "strict RC2G predecessor is not the exact finalized PASS action"
        )
    return item


def _intrinsic_device_evidence(
    contract: Mapping[str, Any], item: Mapping[str, Any]
) -> Mapping[str, Any]:
    summary = execution._validate_action_item(contract, item)
    protocol = item["protocol_evidence"]
    if protocol["outcome"] != ResultState.PASS.value:
        raise N5Rc2gProtocolError("strict RC2G predecessor protocol is not PASS")
    evidence = protocol["device_evidence"]
    if not isinstance(evidence, Mapping):
        raise N5Rc2gProtocolError("strict RC2G predecessor evidence is absent")
    _replay_device_evidence(
        contract,
        summary["action_key"],
        evidence,
        protocol_audit=protocol["request_audit"],
        prior_item=None,
        permit_unbound_same_session=True,
    )
    return evidence


def _preflight_mode(
    snapshot: execution.ActionSnapshot,
    *,
    dynamic_job: Optional[Mapping[str, Any]] = None,
) -> tuple[str, Optional[str]]:
    is_root, previous_session_sha = _session_position(snapshot)
    if not is_root:
        return PREFLIGHT_EXACT_PREDECESSOR, previous_session_sha
    power_mode = snapshot.session.get("power_mode")
    if power_mode == "panel_cold_cycle":
        return PREFLIGHT_PANEL_COLD, None
    if power_mode != "supervised_continuous":
        raise N5Rc2gProtocolError("unsupported N5 session power mode")
    if dynamic_job is None:
        return "supervised-live-dynamic", None
    if dict(dynamic_job) == _FRESH_JOB:
        return PREFLIGHT_SUPERVISED_FRESH, None
    return PREFLIGHT_SUPERVISED_COMPLETED, None


def make_http_transport(
    base_url: str,
    timeout_seconds: float = 20.0,
    *,
    requester: Optional[Callable[..., tuple[int, str]]] = None,
) -> Callable[[str, str, Optional[bytes]], tuple[int, str]]:
    """Return the only real-I/O transport accepted by the N5 execution core.

    ``requester`` is an injection seam for scripted tests.  Production callers
    omit it and receive the no-proxy RC2G HTTP requester.
    """

    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(float(timeout_seconds))
        or float(timeout_seconds) <= 0
    ):
        raise N5Rc2gProtocolError("RC2G HTTP timeout must be finite and positive")
    try:
        normalized = _frame_tool._normalize_base_url(base_url)
    except _frame_tool.FrameToolError as error:
        raise N5Rc2gProtocolError(str(error)) from error
    raw_requester = requester or _quality.http_request

    def transport(
        method: str, endpoint: str, data: Optional[bytes]
    ) -> tuple[int, str]:
        return raw_requester(
            normalized,
            endpoint,
            method=method,
            data=data,
            timeout=float(timeout_seconds),
        )

    return transport


def make_protocol_driver(
    contract: Mapping[str, Any],
    action_key: str,
    prior_bundle: Optional[Mapping[str, Any]] = None,
    *,
    base_url: str,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    job_timeout_seconds: float = _quality.DEFAULT_JOB_TIMEOUT_S,
    poll_interval_seconds: float = _quality.DEFAULT_POLL_INTERVAL_S,
) -> Callable[[execution.AuditedTransport, bytes], Mapping[str, Any]]:
    """Build a post-claim, exactly-one-POST driver for one frozen N5 action."""

    root = execution.validate_execution_contract(contract)
    snapshot = execution.load_action_snapshot(root, action_key)
    try:
        normalized_url = _frame_tool._normalize_base_url(base_url)
    except _frame_tool.FrameToolError as error:
        raise N5Rc2gProtocolError(str(error)) from error
    mode, previous_session_sha = _preflight_mode(snapshot)
    predecessor = _extract_item(root, prior_bundle, previous_session_sha)
    expected_prior = (
        None if predecessor is None else _intrinsic_device_evidence(root, predecessor)
    )

    def driver(
        audited: execution.AuditedTransport, frame: bytes
    ) -> Mapping[str, Any]:
        candidate = _candidate_snapshot(snapshot, frame)
        requester, wire_responses = _bridge_requester(
            audited, base_url=normalized_url
        )
        active_mode = mode
        if mode == "supervised-live-dynamic":
            # Read the full strict preflight once, then classify the already
            # captured immutable job.  No probe is retried or discarded.
            version = _read_version(normalized_url, requester)
            job = _read_json(
                normalized_url,
                "/api/job",
                label="N5 strict live job",
                requester=requester,
            )
            diagnostic = _read_json(
                normalized_url,
                "/api/diagnostic/report",
                label="N5 strict live diagnostic",
                requester=requester,
            )
            gpio_raw = _read_json(
                normalized_url,
                "/api/diagnostic/status",
                label="N5 strict live GPIO",
                requester=requester,
            )
            active_mode, _unused = _preflight_mode(
                snapshot, dynamic_job=job
            )
            if active_mode == PREFLIGHT_SUPERVISED_FRESH:
                preflight = _validate_fresh_records(
                    version, job, diagnostic, gpio_raw
                )
                run = _fresh_run_contract(candidate)
            else:
                run = _completed_run_contract(
                    candidate,
                    job,
                    diagnostic,
                    prior_frame_sha256=None,
                    prior_scope=(
                        "live strict RC2G report; firmware does not expose SHA-256"
                    ),
                )
                preflight = _validate_completed_records(
                    run, version, job, diagnostic, gpio_raw
                )
        else:
            preflight, run = _read_preflight(
                normalized_url,
                requester,
                candidate,
                mode=active_mode,
                expected_prior=expected_prior,
            )
        try:
            network_report = _quality._perform_refresh_once(
                normalized_url,
                frame,
                requester,
                job_timeout_s=job_timeout_seconds,
                poll_interval_s=poll_interval_seconds,
                sleeper=sleeper,
                clock=clock,
            )
            _quality._validate_network_report(network_report, run)
        except (_quality.Rc2gQualityRefreshError, _frame_tool.FrameToolError) as error:
            raise N5Rc2gProtocolError(str(error)) from error
        target_job_raw = _read_json(
            normalized_url,
            "/api/job",
            label="N5 strict target immutable job reread",
            requester=requester,
        )
        if dict(target_job_raw) != dict(network_report.get("job", {})):
            raise N5Rc2gProtocolError(
                "target immutable job changed between strict reads"
            )
        target_diagnostic_raw = _read_json(
            normalized_url,
            "/api/diagnostic/report",
            label="N5 strict target immutable diagnostic reread",
            requester=requester,
        )
        try:
            target_validated = _quality._validate_target_raw_diagnostic(
                target_diagnostic_raw, network_report, run
            )
        except _quality.Rc2gQualityRefreshError as error:
            raise N5Rc2gProtocolError(str(error)) from error
        post_gpio_raw = _read_json(
            normalized_url,
            "/api/diagnostic/status",
            label="N5 strict post-refresh GPIO",
            requester=requester,
        )
        try:
            post_gpio = _quality._validate_gpio_snapshot(
                post_gpio_raw, label="N5 strict post-refresh GPIO"
            )
        except _quality.Rc2gQualityRefreshError as error:
            raise N5Rc2gProtocolError(str(error)) from error
        strict_audit = requester.snapshot()
        if (
            strict_audit["post_attempt_count"] != 1
            or strict_audit["post_issued_count"] != 1
        ):
            raise N5Rc2gProtocolError(
                "strict RC2G driver did not issue exactly one POST /api/frame"
            )
        controller_records = snapshot.action["identity"]["frame"]["controllers"]
        completed = {
            "job_id": run.expected_target_job_id,
            "operation_id": run.expected_target_operation_id,
            "frame_sha256": candidate.frame_sha256,
            "frame_fnv1a": candidate.frame_fnv1a,
            "cs1_dtm_fnv1a": _hex_u32(
                controller_records[0]["dtm_fnv1a"], label="target CS1 DTM FNV-1a"
            ),
            "cs2_dtm_fnv1a": _hex_u32(
                controller_records[1]["dtm_fnv1a"], label="target CS2 DTM FNV-1a"
            ),
            "job_raw_sha256": _sha256(target_job_raw),
            "diagnostic_raw_sha256": _sha256(target_diagnostic_raw),
        }
        evidence = {
            "schema_version": SCHEMA_VERSION,
            "kind": DEVICE_EVIDENCE_KIND,
            "action_key": snapshot.key,
            "action_identity_sha256": snapshot.action["action_identity_sha256"],
            "execution_contract_canonical_sha256": root["integrity"][
                "canonical_sha256"
            ],
            "session_id": snapshot.session["session_id"],
            "preflight_mode": active_mode,
            "preflight": preflight,
            "network_report": dict(network_report),
            "target_job_raw": dict(target_job_raw),
            "target_diagnostic_raw": dict(target_diagnostic_raw),
            "target_diagnostic_validated": dict(target_validated),
            "post_refresh_gpio_status_raw": dict(post_gpio_raw),
            "post_refresh_gpio": _quality._gpio_evidence(post_gpio),
            "strict_request_audit": strict_audit,
            "wire_responses": wire_responses,
            "completed_action": completed,
            "maximum_post_requests": 1,
            "automatic_advance": False,
            "automatic_retry": False,
            "automatic_recovery": False,
        }
        # A protocol PASS must already be finalizable.  Replay the complete
        # raw transcript and semantic evidence before returning to the core;
        # this is pure and performs no additional device request.
        _replay_device_evidence(
            root,
            snapshot.key,
            evidence,
            protocol_audit=audited.snapshot(),
            prior_item=predecessor,
        )
        return evidence

    return driver


def _validate_request_audits(
    strict: object,
    outer: object,
    wire_responses: object,
    *,
    frame_sha256: str,
) -> list[Mapping[str, Any]]:
    strict_root = _exact(
        strict,
        label="strict RC2G request audit",
        keys={"post_attempt_count", "post_issued_count", "calls"},
    )
    outer_root = _exact(
        outer,
        label="outer N5 request audit",
        keys={"post_attempt_count", "post_issued_count", "calls"},
    )
    if (
        strict_root["post_attempt_count"] != 1
        or strict_root["post_issued_count"] != 1
        or outer_root["post_attempt_count"] != 1
        or outer_root["post_issued_count"] != 1
        or not isinstance(strict_root["calls"], list)
        or not isinstance(outer_root["calls"], list)
        or len(strict_root["calls"]) != len(outer_root["calls"])
    ):
        raise N5Rc2gProtocolError("RC2G request audits do not prove one exact POST")
    if not isinstance(wire_responses, list) or len(wire_responses) != len(
        strict_root["calls"]
    ):
        raise N5Rc2gProtocolError(
            "RC2G raw response transcript does not cover every request"
        )
    posts = 0
    validated_wire: list[Mapping[str, Any]] = []
    for index, (strict_call, outer_call, wire_call) in enumerate(
        zip(
            strict_root["calls"],
            outer_root["calls"],
            wire_responses,
        ),
        start=1,
    ):
        if (
            not isinstance(strict_call, Mapping)
            or not isinstance(outer_call, Mapping)
        ):
            raise N5Rc2gProtocolError("RC2G request audit call is not an object")
        wire = _exact(
            wire_call,
            label="RC2G raw response transcript call",
            keys={"index", "method", "endpoint", "status", "response_body"},
        )
        method = strict_call.get("method")
        endpoint = strict_call.get("endpoint")
        strict_keys = {
            "index",
            "method",
            "endpoint",
            "timeout_seconds",
            "request_bytes",
            "outcome",
            "status",
            "response_bytes",
            "response_sha256",
        }
        if method == "POST":
            strict_keys.add("request_sha256")
        if set(strict_call) != strict_keys:
            raise N5Rc2gProtocolError(
                "strict RC2G request call fields changed; "
                f"missing={sorted(strict_keys - set(strict_call))}, "
                f"extra={sorted(set(strict_call) - strict_keys)}"
            )
        response_body = wire["response_body"]
        if not isinstance(response_body, str):
            raise N5Rc2gProtocolError("RC2G raw response body must be text")
        response_bytes = response_body.encode("utf-8")
        timeout = strict_call.get("timeout_seconds")
        expected_status = 202 if method == "POST" else 200
        if (
            strict_call.get("index") != index
            or outer_call.get("sequence") != index
            or wire["index"] != index
            or (method, endpoint) not in _ALLOWED_ROUTES
            or outer_call.get("method") != method
            or outer_call.get("endpoint") != endpoint
            or wire["method"] != method
            or wire["endpoint"] != endpoint
            or strict_call.get("outcome") != "response"
            or type(strict_call.get("status")) is not int
            or strict_call.get("status") != expected_status
            or wire["status"] != expected_status
            or isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(float(timeout))
            or float(timeout) <= 0
            or strict_call.get("response_bytes") != len(response_bytes)
            or strict_call.get("response_sha256") != _sha256(response_bytes)
        ):
            raise N5Rc2gProtocolError("RC2G inner/outer request audits diverge")
        if method == "POST":
            posts += 1
            if (
                strict_call.get("request_sha256") != frame_sha256
                or outer_call.get("request_body_sha256") != frame_sha256
                or strict_call.get("request_bytes") != _frame_tool.FRAME_BYTES
            ):
                raise N5Rc2gProtocolError("RC2G POST frame identity changed")
        elif (
            outer_call.get("request_body_sha256") is not None
            or strict_call.get("request_bytes") != 0
        ):
            raise N5Rc2gProtocolError("RC2G GET unexpectedly carried a body")
        validated_wire.append(wire)
    if posts != 1:
        raise N5Rc2gProtocolError("RC2G audit lacks exactly one POST")
    routes = [(call["method"], call["endpoint"]) for call in validated_wire]
    fixed_prefix = [
        ("GET", "/api/version"),
        ("GET", "/api/job"),
        ("GET", "/api/diagnostic/report"),
        ("GET", "/api/diagnostic/status"),
        ("GET", "/api/version"),
        ("POST", "/api/frame"),
    ]
    fixed_suffix = [
        ("GET", "/api/diagnostic/report"),
        ("GET", "/api/job"),
        ("GET", "/api/diagnostic/report"),
        ("GET", "/api/diagnostic/status"),
    ]
    polling_routes = routes[len(fixed_prefix) : -len(fixed_suffix)]
    if (
        routes[: len(fixed_prefix)] != fixed_prefix
        or routes[-len(fixed_suffix) :] != fixed_suffix
        or not polling_routes
        or any(route != ("GET", "/api/job") for route in polling_routes)
    ):
        raise N5Rc2gProtocolError("RC2G request sequence is not the fixed protocol")
    return validated_wire


def _strict_json_body(body: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(body, str):
        raise N5Rc2gProtocolError(f"{label} raw body must be text")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            body,
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise N5Rc2gProtocolError(f"{label} is not strict JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise N5Rc2gProtocolError(f"{label} must be a JSON object")
    return value


def _validate_wire_bindings(
    wire: list[Mapping[str, Any]],
    *,
    preflight: Mapping[str, Any],
    report: Mapping[str, Any],
    target_job: Mapping[str, Any],
    target_diagnostic: Mapping[str, Any],
    post_gpio_raw: Mapping[str, Any],
    run: _quality._RunContract,
) -> None:
    version_calls = [call for call in wire if call["endpoint"] == "/api/version"]
    if len(version_calls) != 2:
        raise N5Rc2gProtocolError("RC2G transcript must contain two version reads")
    parsed_versions = []
    for call in version_calls:
        try:
            parsed = _frame_tool._parse_version(
                call["response_body"], _quality.FIXED_CONTROLLER_MAPPINGS
            )
        except _frame_tool.FrameToolError as error:
            raise N5Rc2gProtocolError(
                f"raw RC2G version response is invalid: {error}"
            ) from error
        _validate_version(parsed)
        parsed_versions.append(parsed)
    if (
        dict(parsed_versions[0]) != dict(preflight["version"])
        or dict(parsed_versions[1]) != dict(report.get("preflight", {}))
    ):
        raise N5Rc2gProtocolError(
            "raw RC2G version responses do not bind stored preflight identities"
        )

    job_calls = [call for call in wire if call["endpoint"] == "/api/job"]
    jobs = [
        _strict_json_body(call["response_body"], label="raw RC2G job response")
        for call in job_calls
    ]
    if (
        len(jobs) < 3
        or dict(jobs[0]) != dict(preflight["job_raw"])
        or dict(jobs[-2]) != dict(report.get("job", {}))
        or dict(jobs[-1]) != dict(target_job)
    ):
        raise N5Rc2gProtocolError("raw RC2G jobs do not bind stored job evidence")
    for job in jobs[1:-1]:
        if set(job) != _JOB_KEYS:
            raise N5Rc2gProtocolError("raw target job fields changed")
        try:
            _quality._validate_job(
                job, run.expected_target_job_id, run.snapshot.frame_fnv1a
            )
        except _frame_tool.FrameToolError as error:
            raise N5Rc2gProtocolError(
                f"raw target job response is invalid: {error}"
            ) from error

    diagnostic_calls = [
        call for call in wire if call["endpoint"] == "/api/diagnostic/report"
    ]
    diagnostics = [
        _strict_json_body(
            call["response_body"], label="raw RC2G diagnostic response"
        )
        for call in diagnostic_calls
    ]
    if (
        len(diagnostics) != 3
        or dict(diagnostics[0]) != dict(preflight["diagnostic_raw"])
        or dict(diagnostics[1]) != dict(target_diagnostic)
        or dict(diagnostics[2]) != dict(target_diagnostic)
    ):
        raise N5Rc2gProtocolError(
            "raw RC2G diagnostics do not bind stored immutable reports"
        )

    gpio_calls = [
        call for call in wire if call["endpoint"] == "/api/diagnostic/status"
    ]
    gpios = [
        _strict_json_body(call["response_body"], label="raw RC2G GPIO response")
        for call in gpio_calls
    ]
    if (
        len(gpios) != 2
        or dict(gpios[0]) != dict(preflight["gpio_status_raw"])
        or dict(gpios[1]) != dict(post_gpio_raw)
    ):
        raise N5Rc2gProtocolError("raw RC2G GPIO responses do not bind stored GPIO")

    frame_calls = [call for call in wire if call["endpoint"] == "/api/frame"]
    if len(frame_calls) != 1:
        raise N5Rc2gProtocolError("RC2G transcript lacks the sole frame enqueue")
    enqueue = _strict_json_body(
        frame_calls[0]["response_body"], label="raw RC2G frame enqueue"
    )
    if set(enqueue) != {"ok", "bytes", "fnv1a", "free_psram", "job_id"}:
        raise N5Rc2gProtocolError("raw RC2G frame enqueue fields changed")
    try:
        _frame_tool._validate_transfer_response(
            enqueue, run.snapshot.frame_fnv1a, "raw RC2G frame enqueue"
        )
    except _frame_tool.FrameToolError as error:
        raise N5Rc2gProtocolError(str(error)) from error
    if enqueue["job_id"] != run.expected_target_job_id:
        raise N5Rc2gProtocolError("raw RC2G enqueue job id changed")


def _replay_device_evidence(
    contract: Mapping[str, Any],
    action_key: str,
    device_evidence: Mapping[str, Any],
    *,
    protocol_audit: Mapping[str, Any],
    prior_item: Optional[Mapping[str, Any]],
    permit_unbound_same_session: bool = False,
) -> dict[str, Any]:
    root = execution.validate_execution_contract(contract)
    snapshot = execution.load_action_snapshot(root, action_key)
    evidence = _exact(
        device_evidence,
        label="N5 strict RC2G device evidence",
        keys=_EVIDENCE_KEYS,
    )
    if (
        evidence["schema_version"] != SCHEMA_VERSION
        or evidence["kind"] != DEVICE_EVIDENCE_KIND
        or evidence["action_key"] != snapshot.key
        or evidence["action_identity_sha256"]
        != snapshot.action["action_identity_sha256"]
        or evidence["execution_contract_canonical_sha256"]
        != root["integrity"]["canonical_sha256"]
        or evidence["session_id"] != snapshot.session["session_id"]
        or evidence["maximum_post_requests"] != 1
        or evidence["automatic_advance"] is not False
        or evidence["automatic_retry"] is not False
        or evidence["automatic_recovery"] is not False
    ):
        raise N5Rc2gProtocolError("N5 strict RC2G evidence binding changed")
    preflight = _exact(
        evidence["preflight"], label="N5 strict RC2G preflight", keys=_PREFLIGHT_KEYS
    )
    first, previous_session_sha = _session_position(snapshot)
    mode = evidence["preflight_mode"]
    expected_prior: Optional[Mapping[str, Any]] = None
    if not first:
        if mode != PREFLIGHT_EXACT_PREDECESSOR:
            raise N5Rc2gProtocolError(
                "same-session action did not use exact predecessor preflight"
            )
        if prior_item is None:
            if not permit_unbound_same_session:
                raise N5Rc2gProtocolError(
                    "same-session strict replay requires its preceding action item"
                )
        else:
            expected_prior = _intrinsic_device_evidence(root, prior_item)
            if prior_item.get("action_identity_sha256") != previous_session_sha:
                raise N5Rc2gProtocolError(
                    "strict replay received the wrong preceding action item"
                )
    elif snapshot.session["power_mode"] == "panel_cold_cycle":
        if mode != PREFLIGHT_PANEL_COLD:
            raise N5Rc2gProtocolError("panel-cold session did not prove fresh job0")
    elif mode not in {
        PREFLIGHT_SUPERVISED_FRESH,
        PREFLIGHT_SUPERVISED_COMPLETED,
    }:
        raise N5Rc2gProtocolError("supervised root has an invalid preflight mode")

    candidate = _candidate_snapshot(
        snapshot,
        # Replay needs only immutable frame identities.  The quality target
        # validators consume the frame bytes, so regenerate the exact frame
        # through the deterministic production catalog lazily here.
        _load_frame_for_replay(root, action_key),
    )
    version = preflight["version"]
    job = preflight["job_raw"]
    diagnostic = preflight["diagnostic_raw"]
    gpio_raw = preflight["gpio_status_raw"]
    if not all(
        isinstance(value, Mapping)
        for value in (version, job, diagnostic, gpio_raw)
    ):
        raise N5Rc2gProtocolError("strict preflight records must be objects")
    if mode in {PREFLIGHT_PANEL_COLD, PREFLIGHT_SUPERVISED_FRESH}:
        validated_preflight = _validate_fresh_records(
            version, job, diagnostic, gpio_raw
        )
        run = _fresh_run_contract(candidate)
    else:
        if expected_prior is not None:
            if (
                dict(job) != dict(expected_prior["target_job_raw"])
                or dict(diagnostic)
                != dict(expected_prior["target_diagnostic_raw"])
            ):
                raise N5Rc2gProtocolError(
                    "stored preflight is not the exact preceding target evidence"
                )
            prior_frame_sha = str(
                expected_prior["completed_action"]["frame_sha256"]
            )
            prior_scope = "exact preceding finalized N5 strict device evidence"
        else:
            prior_frame_sha = None
            prior_scope = (
                "live strict RC2G report; firmware does not expose SHA-256"
            )
        run = _completed_run_contract(
            candidate,
            job,
            diagnostic,
            prior_frame_sha256=prior_frame_sha,
            prior_scope=prior_scope,
        )
        validated_preflight = _validate_completed_records(
            run, version, job, diagnostic, gpio_raw
        )
    if dict(preflight) != validated_preflight:
        raise N5Rc2gProtocolError("stored strict RC2G preflight normalization changed")

    report = evidence["network_report"]
    target_job = evidence["target_job_raw"]
    target_diagnostic = evidence["target_diagnostic_raw"]
    post_gpio_raw = evidence["post_refresh_gpio_status_raw"]
    if not all(
        isinstance(value, Mapping)
        for value in (report, target_job, target_diagnostic, post_gpio_raw)
    ):
        raise N5Rc2gProtocolError("strict target evidence records must be objects")
    try:
        _quality._validate_network_report(report, run)
        if dict(target_job) != dict(report.get("job", {})):
            raise N5Rc2gProtocolError("strict target job reread changed")
        normalized = _quality._validate_target_raw_diagnostic(
            target_diagnostic, report, run
        )
        post_gpio = _quality._validate_gpio_snapshot(
            post_gpio_raw, label="replayed N5 post-refresh GPIO"
        )
    except (_quality.Rc2gQualityRefreshError, _frame_tool.FrameToolError) as error:
        raise N5Rc2gProtocolError(str(error)) from error
    if (
        dict(evidence["target_diagnostic_validated"]) != dict(normalized)
        or dict(evidence["post_refresh_gpio"])
        != _quality._gpio_evidence(post_gpio)
    ):
        raise N5Rc2gProtocolError("strict target normalized evidence changed")
    controllers = snapshot.action["identity"]["frame"]["controllers"]
    expected_completed = {
        "job_id": run.expected_target_job_id,
        "operation_id": run.expected_target_operation_id,
        "frame_sha256": candidate.frame_sha256,
        "frame_fnv1a": candidate.frame_fnv1a,
        "cs1_dtm_fnv1a": _hex_u32(
            controllers[0]["dtm_fnv1a"], label="replayed target CS1 DTM FNV-1a"
        ),
        "cs2_dtm_fnv1a": _hex_u32(
            controllers[1]["dtm_fnv1a"], label="replayed target CS2 DTM FNV-1a"
        ),
        "job_raw_sha256": _sha256(target_job),
        "diagnostic_raw_sha256": _sha256(target_diagnostic),
    }
    completed = _exact(
        evidence["completed_action"],
        label="N5 strict completed action",
        keys=_COMPLETED_KEYS,
    )
    if dict(completed) != expected_completed:
        raise N5Rc2gProtocolError("strict completed job/action identity changed")
    wire = _validate_request_audits(
        evidence["strict_request_audit"],
        protocol_audit,
        evidence["wire_responses"],
        frame_sha256=candidate.frame_sha256,
    )
    _validate_wire_bindings(
        wire,
        preflight=preflight,
        report=report,
        target_job=target_job,
        target_diagnostic=target_diagnostic,
        post_gpio_raw=post_gpio_raw,
        run=run,
    )
    return {
        "action_key": snapshot.key,
        "action_identity_sha256": snapshot.action["action_identity_sha256"],
        "session_id": snapshot.session["session_id"],
        "preflight_mode": mode,
        "completed_action": dict(completed),
        "strict_rc2g_verified": True,
    }


def _load_frame_for_replay(
    contract: Mapping[str, Any], action_key: str
) -> bytes:
    # Local import avoids a module cycle: the fixed CLI imports this adapter
    # lazily for run/validate, while its deterministic frame catalog is the
    # canonical source for N5 bytes.
    from tools.mf1750_n5_fixed_execution import load_action_frame

    return load_action_frame(contract, action_key)


def validate_strict_action_item(
    contract: Mapping[str, Any],
    item: Mapping[str, Any],
    prior_item: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Deep-validate one finalized item and replay its strict RC2G evidence."""

    root = execution.validate_execution_contract(contract)
    summary = execution._validate_action_item(root, item)
    protocol = item["protocol_evidence"]
    if protocol["outcome"] == ResultState.UNKNOWN_DO_NOT_RETRY.value:
        if protocol["device_evidence"] is not None:
            raise N5Rc2gProtocolError(
                "UNKNOWN strict RC2G action unexpectedly contains success evidence"
            )
        return {**summary, "strict_rc2g_verified": False, "terminal_unknown": True}
    strict = _replay_device_evidence(
        root,
        summary["action_key"],
        protocol["device_evidence"],
        protocol_audit=protocol["request_audit"],
        prior_item=prior_item,
    )
    return {**summary, "strict_rc2g": strict, "strict_rc2g_verified": True}


def validate_strict_finalized_bundle(
    contract: Mapping[str, Any], bundle: Mapping[str, Any]
) -> dict[str, Any]:
    """Replay all strict RC2G records after the core finalized-bundle gate."""

    root = execution.validate_execution_contract(contract)
    core = execution.validate_finalized_bundle(root, bundle)
    items_by_sha = {
        str(item["action_identity_sha256"]): item for item in bundle["actions"]
    }
    strict_actions: dict[str, Mapping[str, Any]] = {}
    for entry in sorted(root["actions"], key=lambda value: value["order"]):
        action_sha = str(entry["action_identity_sha256"])
        item = items_by_sha.get(action_sha)
        if item is None:
            continue
        snapshot = execution.load_action_snapshot(root, str(entry["action_key"]))
        _first, previous_session_sha = _session_position(snapshot)
        prior_item = (
            None
            if previous_session_sha is None
            else items_by_sha.get(previous_session_sha)
        )
        validated = validate_strict_action_item(root, item, prior_item)
        strict_actions[action_sha] = {
            "action_key": validated["action_key"],
            "state": validated["state"],
            "strict_rc2g_verified": validated["strict_rc2g_verified"],
            "terminal_unknown": validated.get("terminal_unknown", False),
        }
    if len(strict_actions) != len(bundle["actions"]):
        raise N5Rc2gProtocolError("not every finalized action was strictly replayed")
    return {
        **core,
        "strict_rc2g_verified": all(
            action["strict_rc2g_verified"] for action in strict_actions.values()
        ),
        "strict_actions_by_sha": strict_actions,
        "network_io_performed": False,
        "device_io_performed": False,
    }


__all__ = [
    "DEVICE_EVIDENCE_KIND",
    "N5Rc2gProtocolError",
    "PREFLIGHT_EXACT_PREDECESSOR",
    "PREFLIGHT_PANEL_COLD",
    "PREFLIGHT_SUPERVISED_COMPLETED",
    "PREFLIGHT_SUPERVISED_FRESH",
    "make_http_transport",
    "make_protocol_driver",
    "validate_strict_action_item",
    "validate_strict_finalized_bundle",
]
