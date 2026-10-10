"""Deep, byte-backed evidence validation for runtime-waveform candidates."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from . import contracts
from . import format_registry


EVIDENCE_SCHEMA_VERSION = 1
EVIDENCE_BUNDLE_KIND = "mf1750-runtime-waveform-evidence-bundle"
EVIDENCE_EVALUATION_KIND = "mf1750-runtime-waveform-evidence-evaluation"

_BUNDLE_KEYS = {
    "schema_version",
    "kind",
    "candidate_manifest_sha256",
    "reviewer_id",
    "panel_binding",
    "electrical_binding",
    "recovery_binding",
    "artifact_records",
    "format_registration_sha256",
    "hardware_execution_eligible",
    "visible_refresh_authorized",
}
_PANEL_BINDING_KEYS = {
    "model",
    "serial",
    "batch_id",
    "controller_model",
    "controller_revision",
    "controller_count",
}
_RECOVERY_BINDING_KEYS = {
    "known_good_profile_sha256",
    "white_recovery_contract_sha256",
    "restore_otp_mode_without_programming",
    "validated_on_sacrificial_panel",
}
_ARTIFACT_RECORD_KEYS = {"role", "bytes", "sha256"}
_FIXED_ARTIFACT_ROLES = {
    "reference_artifact",
    "panel_identity_document",
    "controller_revision_document",
    "format_document",
    "loader_source",
    "electrical_approval",
    "known_good_profile",
    "white_recovery_contract",
    "vendor_review",
    "format_registration",
}


class EvidenceBundleError(ValueError):
    """Raised when an evidence bundle is malformed, stale, or byte-incomplete."""


def _mapping(value: Any, *, label: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise EvidenceBundleError(f"{label} keys differ")
    return value


def _hash(value: Any, *, label: str, nullable: bool = False) -> str | None:
    try:
        return contracts._hash(value, label=label, nullable=nullable)  # noqa: SLF001
    except contracts.RuntimeWaveformContractError as error:
        raise EvidenceBundleError(str(error)) from error


def _identifier(value: Any, *, label: str) -> str:
    try:
        result = contracts._identifier(value, label=label)  # noqa: SLF001
    except contracts.RuntimeWaveformContractError as error:
        raise EvidenceBundleError(str(error)) from error
    assert result is not None
    return result


def _integer(value: Any, *, label: str) -> int:
    try:
        result = contracts._integer(  # noqa: SLF001
            value, label=label, minimum=1, maximum=16 * 1024 * 1024
        )
    except contracts.RuntimeWaveformContractError as error:
        raise EvidenceBundleError(str(error)) from error
    assert result is not None
    return result


def _boolean(value: Any, *, label: str) -> bool:
    try:
        return contracts._boolean(value, label=label)  # noqa: SLF001
    except contracts.RuntimeWaveformContractError as error:
        raise EvidenceBundleError(str(error)) from error


def _expected_panel_binding(candidate: Mapping[str, Any]) -> dict[str, Any]:
    panel = candidate["panel"]
    return {key: panel[key] for key in _PANEL_BINDING_KEYS}


def _expected_recovery_binding(candidate: Mapping[str, Any]) -> dict[str, Any]:
    recovery = candidate["recovery"]
    return {key: recovery[key] for key in _RECOVERY_BINDING_KEYS}


def _record_index(value: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise EvidenceBundleError("artifact_records must be an array")
    records: dict[str, Mapping[str, Any]] = {}
    for position, raw in enumerate(value):
        record = _mapping(
            raw, label=f"artifact record {position}", keys=_ARTIFACT_RECORD_KEYS
        )
        role = _identifier(record["role"], label=f"artifact record {position} role")
        if role in records:
            raise EvidenceBundleError(f"artifact role {role!r} is duplicated")
        _integer(record["bytes"], label=f"artifact {role} bytes")
        _hash(record["sha256"], label=f"artifact {role} sha256")
        records[role] = record
    return records


def _validate_artifact_bytes(
    records: Mapping[str, Mapping[str, Any]],
    artifact_bytes: Mapping[str, bytes],
    *,
    expected_roles: set[str],
) -> dict[str, dict[str, Any]]:
    if set(records) != expected_roles:
        missing = sorted(expected_roles - set(records))
        extra = sorted(set(records) - expected_roles)
        raise EvidenceBundleError(
            f"artifact record roles differ; missing={missing!r}, extra={extra!r}"
        )
    if set(artifact_bytes) != expected_roles:
        missing = sorted(expected_roles - set(artifact_bytes))
        extra = sorted(set(artifact_bytes) - expected_roles)
        raise EvidenceBundleError(
            f"artifact byte roles differ; missing={missing!r}, extra={extra!r}"
        )
    checks: dict[str, dict[str, Any]] = {}
    for role in sorted(expected_roles):
        raw = artifact_bytes[role]
        if not isinstance(raw, bytes):
            raise EvidenceBundleError(f"artifact {role} must be immutable bytes")
        actual = {"bytes": len(raw), "sha256": contracts.sha256_hex(raw)}
        expected = records[role]
        passed = actual["bytes"] == expected["bytes"] and actual["sha256"] == expected["sha256"]
        checks[role] = {**actual, "identity_passed": passed}
        if not passed:
            raise EvidenceBundleError(f"artifact {role} byte identity differs")
    return checks


def validate_evidence_bundle(
    candidate: Mapping[str, Any],
    bundle: Mapping[str, Any],
    *,
    controller_payload_bytes: Mapping[str, bytes],
    artifact_bytes: Mapping[str, bytes],
    trusted_format_registrations: Mapping[str, Mapping[str, Any]] = (
        format_registry.REGISTERED_FORMATS
    ),
) -> dict[str, Any]:
    """Validate actual bytes and a trusted exact-sequence registration.

    Successful validation means only that the offline evidence envelope is
    internally complete.  It never enables hardware I/O or visible refresh.
    """

    validated = contracts.validate_candidate(candidate)
    root = _mapping(bundle, label="evidence bundle", keys=_BUNDLE_KEYS)
    if (
        root["schema_version"] != EVIDENCE_SCHEMA_VERSION
        or root["kind"] != EVIDENCE_BUNDLE_KIND
    ):
        raise EvidenceBundleError("evidence bundle identity differs")
    candidate_sha = contracts.sha256_hex(contracts.canonical_json_bytes(candidate))
    if _hash(
        root["candidate_manifest_sha256"], label="candidate_manifest_sha256"
    ) != candidate_sha:
        raise EvidenceBundleError("evidence bundle candidate identity differs")
    reviewer_id = _identifier(root["reviewer_id"], label="reviewer_id")
    if reviewer_id != validated["provenance"]["vendor_or_panel_owner_review_id"]:
        raise EvidenceBundleError("evidence reviewer differs from candidate")
    if _boolean(
        root["hardware_execution_eligible"], label="hardware_execution_eligible"
    ):
        raise EvidenceBundleError("evidence bundle cannot authorize hardware execution")
    if _boolean(
        root["visible_refresh_authorized"], label="visible_refresh_authorized"
    ):
        raise EvidenceBundleError("evidence bundle cannot authorize visible refresh")

    panel_binding = _mapping(
        root["panel_binding"], label="panel binding", keys=_PANEL_BINDING_KEYS
    )
    if panel_binding != _expected_panel_binding(candidate):
        raise EvidenceBundleError("panel/batch/controller binding differs")
    electrical_binding = _mapping(
        root["electrical_binding"],
        label="electrical binding",
        keys=set(contracts._ELECTRICAL_KEYS),  # noqa: SLF001
    )
    if electrical_binding != candidate["electrical"]:
        raise EvidenceBundleError("approved electrical binding differs")
    recovery_binding = _mapping(
        root["recovery_binding"],
        label="recovery binding",
        keys=_RECOVERY_BINDING_KEYS,
    )
    if recovery_binding != _expected_recovery_binding(candidate):
        raise EvidenceBundleError("OTP equivalence/recovery binding differs")

    format_id = validated["payload"]["format_id"]
    registration = (
        None
        if format_id is None
        else format_registry.trusted_registration_for(
            format_id, registry=trusted_format_registrations
        )
    )
    blockers: list[str] = []
    registration_view: dict[str, Any] | None = None
    if registration is None:
        blockers.append(format_registry.BLOCKED_FORMAT_NOT_REGISTERED)
        expected_roles = set(_FIXED_ARTIFACT_ROLES)
    else:
        try:
            registration_view = format_registry.validate_format_registration(
                registration,
                expected_format_id=format_id,
                expected_format_document_sha256=validated["payload"][
                    "format_document_sha256"
                ],
                expected_loader_source_sha256=validated["provenance"][
                    "loader_source_sha256"
                ],
                expected_reviewer_id=reviewer_id,
                controller_payload_lengths={
                    controller: validated["controller_payloads"][controller]["bytes"]
                    for controller in ("CS1", "CS2")
                },
            )
        except format_registry.FormatRegistrationError as error:
            raise EvidenceBundleError(str(error)) from error
        dynamic_roles = {
            f"command_parameter_{step['index']}"
            for step in registration_view["steps"]
            if step["parameter_source"] == "literal_parameter"
        }
        expected_roles = set(_FIXED_ARTIFACT_ROLES) | dynamic_roles

    records = _record_index(root["artifact_records"])
    checks = _validate_artifact_bytes(
        records, artifact_bytes, expected_roles=expected_roles
    )
    expected_candidate_artifacts = {
        "reference_artifact": validated["provenance"]["reference_artifact_sha256"],
        "format_document": validated["payload"]["format_document_sha256"],
        "loader_source": validated["provenance"]["loader_source_sha256"],
        "known_good_profile": validated["recovery"]["known_good_profile_sha256"],
        "white_recovery_contract": validated["recovery"][
            "white_recovery_contract_sha256"
        ],
    }
    for role, expected_sha in expected_candidate_artifacts.items():
        if expected_sha is None or checks[role]["sha256"] != expected_sha:
            raise EvidenceBundleError(f"artifact {role} is not bound by the candidate")

    registration_sha = _hash(
        root["format_registration_sha256"],
        label="format_registration_sha256",
        nullable=True,
    )
    if registration is None:
        if registration_sha is not None:
            raise EvidenceBundleError(
                "unregistered format cannot claim a registration identity"
            )
    else:
        assert registration_view is not None
        expected_registration_sha = registration_view["canonical_sha256"]
        if registration_sha != expected_registration_sha:
            raise EvidenceBundleError("format registration identity differs")
        canonical_registration = contracts.canonical_json_bytes(registration)
        if artifact_bytes["format_registration"] != canonical_registration:
            raise EvidenceBundleError(
                "format registration artifact must be exact canonical JSON"
            )
        for step in registration_view["steps"]:
            if step["parameter_source"] != "literal_parameter":
                continue
            role = f"command_parameter_{step['index']}"
            check = checks[role]
            if (
                check["bytes"] != step["parameter_length"]
                or check["sha256"] != step["literal_parameter_sha256"]
            ):
                raise EvidenceBundleError(
                    f"literal command parameter for step {step['index']} differs"
                )

    if set(controller_payload_bytes) != {"CS1", "CS2"}:
        raise EvidenceBundleError("controller payload bytes require exact CS1/CS2 keys")
    payload_checks: dict[str, dict[str, Any]] = {}
    for controller in ("CS1", "CS2"):
        raw = controller_payload_bytes[controller]
        if not isinstance(raw, bytes):
            raise EvidenceBundleError(f"{controller} payload must be immutable bytes")
        expected = validated["controller_payloads"][controller]
        actual = {"bytes": len(raw), "sha256": contracts.sha256_hex(raw)}
        passed = actual["bytes"] == expected["bytes"] and actual["sha256"] == expected["sha256"]
        payload_checks[controller] = {**actual, "identity_passed": passed}
        if not passed:
            raise EvidenceBundleError(f"{controller} payload identity differs")

    blockers = sorted(set(blockers))
    bundle_sha = contracts.sha256_hex(contracts.canonical_json_bytes(bundle))
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "kind": EVIDENCE_EVALUATION_KIND,
        "candidate_manifest_sha256": candidate_sha,
        "evidence_bundle_sha256": bundle_sha,
        "format_registration_sha256": registration_sha,
        "offline_evidence_complete": not blockers,
        "blocker_codes": blockers,
        "artifact_checks": checks,
        "controller_payload_checks": payload_checks,
        "hardware_execution_eligible": False,
        "execution_ready": False,
        "visible_refresh_authorized": False,
        "hardware_io_performed": False,
        "network_io_performed": False,
    }
