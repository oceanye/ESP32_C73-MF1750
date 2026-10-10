"""Compile deterministic, zero-I/O runtime-waveform command plans.

The compiler accepts only canonical manifest bytes, immutable controller
payload bytes, a byte-backed P0 evidence bundle, and a caller-supplied trusted
format registry.  The production registry is empty, so current candidates
return ``BLOCKED_FORMAT_NOT_REGISTERED`` and no command plan.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from . import contracts, evidence, format_registry


EXECUTION_PLAN_SCHEMA_VERSION = 1
EXECUTION_PLAN_KIND = "mf1750-runtime-waveform-zero-io-execution-plan"
BLOCKED_PLAN_KIND = "mf1750-runtime-waveform-blocked-execution-plan"
ZERO_IO_CLASSIFICATION = "ZERO_IO_PLAN_COMPILED_HARDWARE_EXECUTION_DISABLED"

_PLAN_KEYS = {
    "schema_version",
    "kind",
    "classification",
    "candidate_manifest_sha256",
    "evidence_bundle_sha256",
    "format_registration_sha256",
    "compiled",
    "steps",
    "integrity",
    "payload_bytes_embedded",
    "callbacks_present",
    "authorization_token_issued",
    "hardware_execution_eligible",
    "execution_ready",
    "visible_refresh_authorized",
    "hardware_io_performed",
    "network_io_performed",
}
_STEP_KEYS = {
    "index",
    "predecessor_identity_sha256",
    "controller_target",
    "opcode",
    "parameter_source",
    "parameter_length",
    "parameter_sha256",
    "step_identity_sha256",
}
_INTEGRITY_KEYS = {"canonical_sha256", "scope"}


class ExecutionPlanError(ValueError):
    """Raised when zero-I/O plan inputs are noncanonical, stale, or unsafe."""


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExecutionPlanError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ExecutionPlanError(f"non-finite JSON constant {value!r} is forbidden")


def load_canonical_manifest_bytes(payload: bytes) -> dict[str, Any]:
    """Decode exact canonical JSON bytes with duplicate-key rejection."""

    if not isinstance(payload, bytes) or not payload:
        raise ExecutionPlanError("candidate manifest must be non-empty immutable bytes")
    try:
        decoded = payload.decode("utf-8")
        candidate = json.loads(
            decoded,
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExecutionPlanError("candidate manifest bytes are invalid UTF-8 JSON") from error
    if not isinstance(candidate, dict):
        raise ExecutionPlanError("candidate manifest top level must be an object")
    try:
        canonical = contracts.canonical_json_bytes(candidate)
        contracts.validate_candidate(candidate)
    except contracts.RuntimeWaveformContractError as error:
        raise ExecutionPlanError(str(error)) from error
    if payload != canonical:
        raise ExecutionPlanError("candidate manifest bytes are not exact canonical JSON")
    return candidate


def _blocked_plan(candidate_manifest_sha256: str, *, blocker_code: str) -> dict[str, Any]:
    return {
        "schema_version": EXECUTION_PLAN_SCHEMA_VERSION,
        "kind": BLOCKED_PLAN_KIND,
        "classification": blocker_code,
        "candidate_manifest_sha256": candidate_manifest_sha256,
        "compiled": False,
        "steps": [],
        "blocker_codes": [blocker_code],
        "payload_bytes_embedded": False,
        "callbacks_present": False,
        "authorization_token_issued": False,
        "hardware_execution_eligible": False,
        "execution_ready": False,
        "visible_refresh_authorized": False,
        "hardware_io_performed": False,
        "network_io_performed": False,
    }


def _step_identity(step_without_identity: Mapping[str, Any]) -> str:
    return contracts.sha256_hex(contracts.canonical_json_bytes(step_without_identity))


def _plan_integrity(plan_without_integrity: Mapping[str, Any]) -> str:
    return contracts.sha256_hex(contracts.canonical_json_bytes(plan_without_integrity))


def compile_execution_plan(
    candidate_manifest_bytes: bytes,
    controller_payload_bytes: Mapping[str, bytes],
    *,
    evidence_bundle: Mapping[str, Any] | None = None,
    evidence_artifact_bytes: Mapping[str, bytes] | None = None,
    trusted_format_registrations: Mapping[str, Mapping[str, Any]] = (
        format_registry.REGISTERED_FORMATS
    ),
) -> dict[str, Any]:
    """Compile a byte-free plan, or return the stable unregistered-format block."""

    candidate = load_canonical_manifest_bytes(candidate_manifest_bytes)
    candidate_sha = contracts.sha256_hex(candidate_manifest_bytes)
    format_id = candidate["payload"]["format_id"]
    try:
        registration = (
            None
            if format_id is None
            else format_registry.trusted_registration_for(
                format_id, registry=trusted_format_registrations
            )
        )
    except format_registry.FormatRegistrationError as error:
        raise ExecutionPlanError(str(error)) from error
    if registration is None:
        return _blocked_plan(
            candidate_sha,
            blocker_code=format_registry.BLOCKED_FORMAT_NOT_REGISTERED,
        )
    if evidence_bundle is None or evidence_artifact_bytes is None:
        raise ExecutionPlanError(
            "registered format compilation requires the complete P0 evidence bundle"
        )
    try:
        evidence_report = evidence.validate_evidence_bundle(
            candidate,
            evidence_bundle,
            controller_payload_bytes=controller_payload_bytes,
            artifact_bytes=evidence_artifact_bytes,
            trusted_format_registrations=trusted_format_registrations,
        )
        registration_view = format_registry.validate_format_registration(
            registration,
            expected_format_id=format_id,
            expected_format_document_sha256=candidate["payload"][
                "format_document_sha256"
            ],
            expected_loader_source_sha256=candidate["provenance"][
                "loader_source_sha256"
            ],
            expected_reviewer_id=candidate["provenance"][
                "vendor_or_panel_owner_review_id"
            ],
            controller_payload_lengths={
                item["controller"]: item["bytes"]
                for item in candidate["payload"]["controller_payloads"]
            },
        )
    except (evidence.EvidenceBundleError, format_registry.FormatRegistrationError) as error:
        raise ExecutionPlanError(str(error)) from error
    if not evidence_report["offline_evidence_complete"]:
        raise ExecutionPlanError("P0 evidence bundle is not offline-complete")

    predecessor = candidate_sha
    steps: list[dict[str, Any]] = []
    for registered_step in registration_view["steps"]:
        if registered_step["parameter_source"] == "controller_payload":
            parameter = controller_payload_bytes[
                registered_step["controller_target"]
            ]
        else:
            parameter = evidence_artifact_bytes[
                f"command_parameter_{registered_step['index']}"
            ]
        step_without_identity = {
            "index": registered_step["index"],
            "predecessor_identity_sha256": predecessor,
            "controller_target": registered_step["controller_target"],
            "opcode": registered_step["opcode"],
            "parameter_source": registered_step["parameter_source"],
            "parameter_length": len(parameter),
            "parameter_sha256": contracts.sha256_hex(parameter),
        }
        identity = _step_identity(step_without_identity)
        step = {**step_without_identity, "step_identity_sha256": identity}
        steps.append(step)
        predecessor = identity

    plan_without_integrity = {
        "schema_version": EXECUTION_PLAN_SCHEMA_VERSION,
        "kind": EXECUTION_PLAN_KIND,
        "classification": ZERO_IO_CLASSIFICATION,
        "candidate_manifest_sha256": candidate_sha,
        "evidence_bundle_sha256": evidence_report["evidence_bundle_sha256"],
        "format_registration_sha256": registration_view["canonical_sha256"],
        "compiled": True,
        "steps": steps,
        "payload_bytes_embedded": False,
        "callbacks_present": False,
        "authorization_token_issued": False,
        "hardware_execution_eligible": False,
        "execution_ready": False,
        "visible_refresh_authorized": False,
        "hardware_io_performed": False,
        "network_io_performed": False,
    }
    return {
        **plan_without_integrity,
        "integrity": {
            "canonical_sha256": _plan_integrity(plan_without_integrity),
            "scope": "all_top_level_fields_except_integrity",
        },
    }


def validate_execution_plan(
    plan: Mapping[str, Any],
    *,
    trusted_format_registration: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Deep-validate a compiled plan without accepting payload bytes or callbacks."""

    if not isinstance(plan, Mapping) or set(plan) != _PLAN_KEYS:
        raise ExecutionPlanError("compiled execution plan keys differ")
    if (
        plan["schema_version"] != EXECUTION_PLAN_SCHEMA_VERSION
        or plan["kind"] != EXECUTION_PLAN_KIND
        or plan["classification"] != ZERO_IO_CLASSIFICATION
        or plan["compiled"] is not True
    ):
        raise ExecutionPlanError("compiled execution plan identity differs")
    for field in (
        "payload_bytes_embedded",
        "callbacks_present",
        "authorization_token_issued",
        "hardware_execution_eligible",
        "execution_ready",
        "visible_refresh_authorized",
        "hardware_io_performed",
        "network_io_performed",
    ):
        if plan[field] is not False:
            raise ExecutionPlanError(f"compiled execution plan {field} must be false")
    for field in (
        "candidate_manifest_sha256",
        "evidence_bundle_sha256",
        "format_registration_sha256",
    ):
        try:
            contracts._hash(plan[field], label=field)  # noqa: SLF001
        except contracts.RuntimeWaveformContractError as error:
            raise ExecutionPlanError(str(error)) from error

    steps = plan["steps"]
    if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes)):
        raise ExecutionPlanError("compiled execution plan steps must be an array")
    if trusted_format_registration is not None:
        try:
            registration_view = format_registry.validate_format_registration(
                trusted_format_registration
            )
        except format_registry.FormatRegistrationError as error:
            raise ExecutionPlanError(str(error)) from error
        if plan["format_registration_sha256"] != registration_view["canonical_sha256"]:
            raise ExecutionPlanError("plan trusted format registration identity differs")
        if len(steps) != len(registration_view["steps"]):
            raise ExecutionPlanError("plan step count differs from trusted registration")
    else:
        registration_view = None

    predecessor = plan["candidate_manifest_sha256"]
    for position, raw in enumerate(steps):
        if not isinstance(raw, Mapping) or set(raw) != _STEP_KEYS:
            raise ExecutionPlanError(f"compiled step {position} keys differ")
        if raw["index"] != position or raw["predecessor_identity_sha256"] != predecessor:
            raise ExecutionPlanError("compiled plan predecessor chain differs")
        if raw["controller_target"] not in {"CS1", "CS2"}:
            raise ExecutionPlanError("compiled plan controller target differs")
        if raw["opcode"] not in contracts.ALLOWED_RUNTIME_COMMANDS:
            raise ExecutionPlanError("compiled plan contains a non-allowlisted opcode")
        if (
            type(raw["parameter_length"]) is not int
            or raw["parameter_length"] < 1
            or raw["parameter_length"] > 1_048_576
        ):
            raise ExecutionPlanError("compiled plan parameter length differs")
        for field in ("parameter_sha256", "step_identity_sha256"):
            try:
                contracts._hash(raw[field], label=f"step {position} {field}")  # noqa: SLF001
            except contracts.RuntimeWaveformContractError as error:
                raise ExecutionPlanError(str(error)) from error
        unsigned = {key: raw[key] for key in _STEP_KEYS - {"step_identity_sha256"}}
        if raw["step_identity_sha256"] != _step_identity(unsigned):
            raise ExecutionPlanError(f"compiled step {position} identity differs")
        if registration_view is not None:
            registered = registration_view["steps"][position]
            exact_fields = (
                "index",
                "controller_target",
                "opcode",
                "parameter_source",
                "parameter_length",
            )
            if any(raw[field] != registered[field] for field in exact_fields):
                raise ExecutionPlanError(
                    f"compiled step {position} differs from trusted registration"
                )
            if (
                registered["literal_parameter_sha256"] is not None
                and raw["parameter_sha256"]
                != registered["literal_parameter_sha256"]
            ):
                raise ExecutionPlanError(
                    f"compiled step {position} literal parameter identity differs"
                )
        predecessor = raw["step_identity_sha256"]

    integrity = plan["integrity"]
    if not isinstance(integrity, Mapping) or set(integrity) != _INTEGRITY_KEYS:
        raise ExecutionPlanError("compiled execution plan integrity keys differ")
    if integrity["scope"] != "all_top_level_fields_except_integrity":
        raise ExecutionPlanError("compiled execution plan integrity scope differs")
    unsigned_plan = {key: plan[key] for key in _PLAN_KEYS - {"integrity"}}
    if integrity["canonical_sha256"] != _plan_integrity(unsigned_plan):
        raise ExecutionPlanError("compiled execution plan canonical hash differs")
    return {
        "valid": True,
        "canonical_sha256": integrity["canonical_sha256"],
        "step_count": len(steps),
        "hardware_execution_eligible": False,
        "execution_ready": False,
        "visible_refresh_authorized": False,
    }
