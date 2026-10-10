"""Offline-only contracts for a future dual-controller 3-bit waveform loader.

This module deliberately contains no hardware transport.  It validates exact
panel, payload, electrical, recovery, and review identities and reports why a
candidate is blocked.  The current STM32/OQC reference proves that a runtime
LUT mechanism exists, but it does not satisfy this contract.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
import re
from typing import Any, Mapping


SCHEMA_VERSION = 1
CANDIDATE_KIND = "mf1750-spd1657-runtime-waveform-candidate"
EVALUATION_KIND = "mf1750-spd1657-runtime-waveform-evaluation"
BLOCKED_CLASSIFICATION = "OFFLINE_ONLY_NOT_EXECUTABLE"
OFFLINE_COMPLETE_CLASSIFICATION = (
    "OFFLINE_CONTRACT_COMPLETE_HARDWARE_EXECUTION_DISABLED"
)
# Compatibility alias for callers that used the V1 name.  "READY" means only
# that the offline document is complete; it never means hardware execution is
# enabled.
READY_CLASSIFICATION = OFFLINE_COMPLETE_CLASSIFICATION
HARDWARE_EXECUTION_BLOCKER = "hardware_execution_disabled_current_phase"

PANEL_MODEL = "MF-17506-M009F-T"
CONTROLLER_MODEL = "SPD1657B/E2802"
PANEL_WIDTH = 1024
PANEL_HEIGHT = 600
CONTROLLER_WIDTH = 512
CONTROLLER_HEIGHT = 600
FORMAL_CODES = (0, 1, 2, 3, 5, 6)
EXPERIMENTAL_CODES = (4, 7)
TRANSPORT_CODES = tuple(range(8))
MIN_CONTROLLER_PAYLOAD_BYTES = 512

# The current offline contract recognizes exactly the two RAM-LUT operations
# evidenced by the reviewed reference path.  Names and purposes are also
# frozen so an allowed opcode cannot be disguised or reinterpreted.
ALLOWED_RUNTIME_COMMANDS = {
    0x20: ("lut_ram_write", "runtime_lut_data"),
    0xE9: ("mcu_lut_mode_select", "ram_lut_mode"),
}

GATE_NAMES = (
    "panel_and_batch_exact",
    "controller_revision_exact",
    "dual_controller_3bit_format_documented",
    "plaintext_decoded_payload_available",
    "portable_loader_source_reviewed",
    "register_sequence_reviewed",
    "code_semantics_reviewed",
    "electrical_parameters_approved",
    "temperature_bin_approved",
    "known_good_otp_equivalence_passed",
    "independent_recovery_validated",
    "sacrificial_panel_authorized",
    "power_telemetry_and_hard_cutoff_ready",
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
_REPRESENTATIONS = {
    "identity_only_missing_decoded_payload",
    "plaintext_decoded_3bit_lut",
}
_TOP_KEYS = {
    "schema_version",
    "kind",
    "profile_id",
    "created_at",
    "hardware_tested",
    "panel",
    "encoding",
    "payload",
    "electrical",
    "operation_contract",
    "provenance",
    "recovery",
    "qualification_gates",
}
_PANEL_KEYS = {
    "model",
    "serial",
    "batch_id",
    "controller_model",
    "controller_revision",
    "controller_count",
    "cascade",
    "panel_width",
    "panel_height",
    "controller_width",
    "controller_height",
}
_ENCODING_KEYS = {
    "bits_per_pixel",
    "transport_codes",
    "formal_codes",
    "experimental_codes",
    "channel_model",
}
_PAYLOAD_KEYS = {
    "representation",
    "format_id",
    "format_document_sha256",
    "controller_payloads",
}
_CONTROLLER_PAYLOAD_KEYS = {"controller", "bytes", "sha256"}
_ELECTRICAL_KEYS = {
    "temperature_min_c",
    "temperature_max_c",
    "vcom_mv",
    "vgh_mv",
    "vgl_mv",
    "vsh_mv",
    "vsl_mv",
    "frame_rate_hz",
    "phase_timing_documented",
}
_OPERATION_KEYS = {
    "mode",
    "commands",
    "otp_programming_allowed",
    "otp_erase_allowed",
    "startup_auto_apply",
    "network_raw_upload_allowed",
}
_COMMAND_KEYS = {"name", "opcode", "purpose"}
_PROVENANCE_KEYS = {
    "reference_artifact_sha256",
    "source_payload_sha256",
    "loader_source_sha256",
    "vendor_or_panel_owner_review_id",
    "source_is_current_panel_3bit",
}
_RECOVERY_KEYS = {
    "known_good_profile_sha256",
    "white_recovery_contract_sha256",
    "restore_otp_mode_without_programming",
    "validated_on_sacrificial_panel",
}


class RuntimeWaveformContractError(ValueError):
    """Raised when a waveform candidate is malformed or unsafe to classify."""


def canonical_json_bytes(value: Any) -> bytes:
    """Encode one value deterministically and reject NaN/Infinity."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise RuntimeWaveformContractError(
            "waveform candidate is not canonical-JSON encodable"
        ) from error


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _mapping(value: Any, *, label: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise RuntimeWaveformContractError(f"{label} keys differ")
    return value


def _text(
    value: Any,
    *,
    label: str,
    nullable: bool = False,
    maximum: int = 4096,
) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise RuntimeWaveformContractError(f"{label} must be non-empty text")
    return value


def _identifier(value: Any, *, label: str, nullable: bool = False) -> str | None:
    text = _text(value, label=label, nullable=nullable, maximum=128)
    if text is None:
        return None
    if _IDENTIFIER.fullmatch(text) is None:
        raise RuntimeWaveformContractError(f"{label} is not a safe identifier")
    return text


def _hash(value: Any, *, label: str, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RuntimeWaveformContractError(f"{label} must be a lowercase SHA-256")
    return value


def _boolean(value: Any, *, label: str) -> bool:
    if type(value) is not bool:
        raise RuntimeWaveformContractError(f"{label} must be boolean")
    return value


def _integer(
    value: Any,
    *,
    label: str,
    minimum: int | None = None,
    maximum: int | None = None,
    nullable: bool = False,
) -> int | None:
    if value is None and nullable:
        return None
    if type(value) is not int:
        raise RuntimeWaveformContractError(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        raise RuntimeWaveformContractError(f"{label} is below its minimum")
    if maximum is not None and value > maximum:
        raise RuntimeWaveformContractError(f"{label} is above its maximum")
    return value


def _number(
    value: Any,
    *,
    label: str,
    minimum: float | None = None,
    maximum: float | None = None,
    nullable: bool = False,
) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeWaveformContractError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise RuntimeWaveformContractError(f"{label} must be finite")
    if minimum is not None and result < minimum:
        raise RuntimeWaveformContractError(f"{label} is below its minimum")
    if maximum is not None and result > maximum:
        raise RuntimeWaveformContractError(f"{label} is above its maximum")
    return result


def _timestamp(value: Any, *, label: str) -> str:
    text = _text(value, label=label, maximum=64)
    assert text is not None
    if _RFC3339.fullmatch(text) is None:
        raise RuntimeWaveformContractError(f"{label} must be RFC 3339")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise RuntimeWaveformContractError(f"{label} is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeWaveformContractError(f"{label} lacks a UTC offset")
    return text


def _list_of_exact_ints(value: Any, expected: tuple[int, ...], *, label: str) -> None:
    if not isinstance(value, list) or value != list(expected):
        raise RuntimeWaveformContractError(f"{label} differs")


def _validate_panel(value: Any) -> Mapping[str, Any]:
    panel = _mapping(value, label="panel", keys=_PANEL_KEYS)
    if panel["model"] != PANEL_MODEL or panel["controller_model"] != CONTROLLER_MODEL:
        raise RuntimeWaveformContractError("panel/controller model differs")
    _text(panel["serial"], label="panel.serial")
    _text(panel["batch_id"], label="panel.batch_id", nullable=True)
    _text(panel["controller_revision"], label="panel.controller_revision", nullable=True)
    expected = {
        "controller_count": 2,
        "cascade": True,
        "panel_width": PANEL_WIDTH,
        "panel_height": PANEL_HEIGHT,
        "controller_width": CONTROLLER_WIDTH,
        "controller_height": CONTROLLER_HEIGHT,
    }
    for key, wanted in expected.items():
        if panel[key] != wanted:
            raise RuntimeWaveformContractError(f"panel.{key} differs")
    return panel


def _validate_encoding(value: Any) -> Mapping[str, Any]:
    encoding = _mapping(value, label="encoding", keys=_ENCODING_KEYS)
    if encoding["bits_per_pixel"] != 3:
        raise RuntimeWaveformContractError("only the exact 3-bit transport is accepted")
    _list_of_exact_ints(encoding["transport_codes"], TRANSPORT_CODES, label="transport codes")
    _list_of_exact_ints(encoding["formal_codes"], FORMAL_CODES, label="formal codes")
    _list_of_exact_ints(
        encoding["experimental_codes"], EXPERIMENTAL_CODES, label="experimental codes"
    )
    if (
        encoding["channel_model"]
        != "indexed_particle_target_states_not_independent_rgb_channels"
    ):
        raise RuntimeWaveformContractError("waveform channel model differs")
    return encoding


def _validate_payload(value: Any) -> tuple[Mapping[str, Any], dict[str, Mapping[str, Any]]]:
    payload = _mapping(value, label="payload", keys=_PAYLOAD_KEYS)
    if payload["representation"] not in _REPRESENTATIONS:
        raise RuntimeWaveformContractError("payload representation is invalid")
    _identifier(payload["format_id"], label="payload.format_id", nullable=True)
    _hash(
        payload["format_document_sha256"],
        label="payload.format_document_sha256",
        nullable=True,
    )
    items = payload["controller_payloads"]
    if not isinstance(items, list) or len(items) != 2:
        raise RuntimeWaveformContractError("exactly two controller payload identities are required")
    indexed: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(items):
        item = _mapping(
            raw,
            label=f"controller payload {index}",
            keys=_CONTROLLER_PAYLOAD_KEYS,
        )
        controller = item["controller"]
        if controller not in {"CS1", "CS2"} or controller in indexed:
            raise RuntimeWaveformContractError("controller payload identities differ")
        length = _integer(
            item["bytes"],
            label=f"{controller} payload bytes",
            minimum=1,
            maximum=1_048_576,
            nullable=True,
        )
        digest = _hash(
            item["sha256"], label=f"{controller} payload SHA-256", nullable=True
        )
        if (length is None) != (digest is None):
            raise RuntimeWaveformContractError(
                f"{controller} payload bytes and SHA must both be null or both present"
            )
        indexed[controller] = item
    if set(indexed) != {"CS1", "CS2"}:
        raise RuntimeWaveformContractError("CS1 and CS2 payload identities are required")
    if payload["representation"] == "plaintext_decoded_3bit_lut":
        if payload["format_id"] is None or payload["format_document_sha256"] is None:
            raise RuntimeWaveformContractError(
                "decoded 3-bit payload requires a frozen format and document identity"
            )
        if any(item["bytes"] is None for item in indexed.values()):
            raise RuntimeWaveformContractError(
                "decoded 3-bit payload requires both controller payload identities"
            )
    return payload, indexed


def _validate_electrical(value: Any) -> Mapping[str, Any]:
    electrical = _mapping(value, label="electrical", keys=_ELECTRICAL_KEYS)
    minimum = _number(
        electrical["temperature_min_c"],
        label="electrical.temperature_min_c",
        minimum=-40.0,
        maximum=100.0,
        nullable=True,
    )
    maximum = _number(
        electrical["temperature_max_c"],
        label="electrical.temperature_max_c",
        minimum=-40.0,
        maximum=100.0,
        nullable=True,
    )
    if minimum is not None and maximum is not None and minimum > maximum:
        raise RuntimeWaveformContractError("electrical temperature interval is inverted")
    for key in ("vcom_mv", "vgh_mv", "vgl_mv", "vsh_mv", "vsl_mv"):
        _number(
            electrical[key],
            label=f"electrical.{key}",
            minimum=-100_000.0,
            maximum=100_000.0,
            nullable=True,
        )
    _number(
        electrical["frame_rate_hz"],
        label="electrical.frame_rate_hz",
        minimum=0.01,
        maximum=10_000.0,
        nullable=True,
    )
    _boolean(
        electrical["phase_timing_documented"],
        label="electrical.phase_timing_documented",
    )
    return electrical


def _validate_operations(value: Any) -> Mapping[str, Any]:
    contract = _mapping(value, label="operation contract", keys=_OPERATION_KEYS)
    if contract["mode"] != "runtime_lut_ram_only":
        raise RuntimeWaveformContractError("only runtime RAM LUT mode is permitted")
    for key in (
        "otp_programming_allowed",
        "otp_erase_allowed",
        "startup_auto_apply",
        "network_raw_upload_allowed",
    ):
        if _boolean(contract[key], label=f"operation_contract.{key}") is not False:
            raise RuntimeWaveformContractError(f"operation_contract.{key} must be false")
    commands = contract["commands"]
    if not isinstance(commands, list):
        raise RuntimeWaveformContractError("operation commands must be an array")
    seen: set[int] = set()
    for index, raw in enumerate(commands):
        command = _mapping(raw, label=f"command {index}", keys=_COMMAND_KEYS)
        name = _identifier(command["name"], label=f"command {index} name")
        purpose = _identifier(command["purpose"], label=f"command {index} purpose")
        opcode = _integer(
            command["opcode"], label=f"command {index} opcode", minimum=0, maximum=255
        )
        assert name is not None and purpose is not None and opcode is not None
        allowed_identity = ALLOWED_RUNTIME_COMMANDS.get(opcode)
        if allowed_identity is None:
            raise RuntimeWaveformContractError(
                f"forbidden opcode 0x{opcode:02x} is not in the exact runtime allowlist"
            )
        if (name, purpose) != allowed_identity:
            raise RuntimeWaveformContractError(
                f"command identity for opcode 0x{opcode:02x} differs from the allowlist"
            )
        if opcode in seen:
            raise RuntimeWaveformContractError("operation command opcode is duplicated")
        seen.add(opcode)
    return contract


def _validate_provenance(value: Any) -> Mapping[str, Any]:
    provenance = _mapping(value, label="provenance", keys=_PROVENANCE_KEYS)
    _hash(
        provenance["reference_artifact_sha256"],
        label="provenance.reference_artifact_sha256",
    )
    _hash(
        provenance["source_payload_sha256"],
        label="provenance.source_payload_sha256",
        nullable=True,
    )
    _hash(
        provenance["loader_source_sha256"],
        label="provenance.loader_source_sha256",
        nullable=True,
    )
    _identifier(
        provenance["vendor_or_panel_owner_review_id"],
        label="provenance.vendor_or_panel_owner_review_id",
        nullable=True,
    )
    _boolean(
        provenance["source_is_current_panel_3bit"],
        label="provenance.source_is_current_panel_3bit",
    )
    return provenance


def _validate_recovery(value: Any) -> Mapping[str, Any]:
    recovery = _mapping(value, label="recovery", keys=_RECOVERY_KEYS)
    _hash(
        recovery["known_good_profile_sha256"],
        label="recovery.known_good_profile_sha256",
        nullable=True,
    )
    _hash(
        recovery["white_recovery_contract_sha256"],
        label="recovery.white_recovery_contract_sha256",
        nullable=True,
    )
    _boolean(
        recovery["restore_otp_mode_without_programming"],
        label="recovery.restore_otp_mode_without_programming",
    )
    _boolean(
        recovery["validated_on_sacrificial_panel"],
        label="recovery.validated_on_sacrificial_panel",
    )
    return recovery


def _validate_gates(value: Any) -> Mapping[str, bool]:
    gates = _mapping(value, label="qualification gates", keys=set(GATE_NAMES))
    for name in GATE_NAMES:
        _boolean(gates[name], label=f"qualification_gates.{name}")
    return gates  # type: ignore[return-value]


def validate_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Strictly validate one offline candidate without deciding hardware action."""

    root = _mapping(candidate, label="waveform candidate", keys=_TOP_KEYS)
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != CANDIDATE_KIND:
        raise RuntimeWaveformContractError("waveform candidate identity differs")
    _identifier(root["profile_id"], label="profile_id")
    _timestamp(root["created_at"], label="created_at")
    if _boolean(root["hardware_tested"], label="hardware_tested") is not False:
        raise RuntimeWaveformContractError(
            "candidate contracts are pre-hardware artifacts; hardware_tested must be false"
        )
    panel = _validate_panel(root["panel"])
    encoding = _validate_encoding(root["encoding"])
    payload, controller_payloads = _validate_payload(root["payload"])
    electrical = _validate_electrical(root["electrical"])
    operations = _validate_operations(root["operation_contract"])
    provenance = _validate_provenance(root["provenance"])
    recovery = _validate_recovery(root["recovery"])
    gates = _validate_gates(root["qualification_gates"])
    return {
        "root": root,
        "panel": panel,
        "encoding": encoding,
        "payload": payload,
        "controller_payloads": controller_payloads,
        "electrical": electrical,
        "operations": operations,
        "provenance": provenance,
        "recovery": recovery,
        "gates": gates,
    }


def _identity_blockers(validated: Mapping[str, Any]) -> list[str]:
    panel = validated["panel"]
    payload = validated["payload"]
    controller_payloads = validated["controller_payloads"]
    electrical = validated["electrical"]
    operations = validated["operations"]
    provenance = validated["provenance"]
    recovery = validated["recovery"]
    blockers: list[str] = []
    if panel["batch_id"] is None:
        blockers.append("panel_batch_identity_missing")
    if panel["controller_revision"] is None:
        blockers.append("controller_revision_identity_missing")
    if payload["representation"] != "plaintext_decoded_3bit_lut":
        blockers.append("decoded_3bit_payload_missing")
    if payload["format_id"] is None or payload["format_document_sha256"] is None:
        blockers.append("decoded_layout_identity_missing")
    for controller in ("CS1", "CS2"):
        length = controller_payloads[controller]["bytes"]
        if length is not None and length < MIN_CONTROLLER_PAYLOAD_BYTES:
            blockers.append(f"{controller.lower()}_payload_too_short")
    supplied_opcodes = {command["opcode"] for command in operations["commands"]}
    for opcode in sorted(ALLOWED_RUNTIME_COMMANDS):
        if opcode not in supplied_opcodes:
            blockers.append(f"required_runtime_opcode_missing:0x{opcode:02x}")
    if not provenance["source_is_current_panel_3bit"]:
        blockers.append("source_not_proven_for_current_panel_3bit")
    if provenance["source_payload_sha256"] is None:
        blockers.append("source_payload_identity_missing")
    if provenance["loader_source_sha256"] is None:
        blockers.append("portable_loader_source_missing")
    if provenance["vendor_or_panel_owner_review_id"] is None:
        blockers.append("vendor_or_panel_owner_review_missing")
    required_electrical = (
        "temperature_min_c",
        "temperature_max_c",
        "vcom_mv",
        "vgh_mv",
        "vgl_mv",
        "vsh_mv",
        "vsl_mv",
        "frame_rate_hz",
    )
    if any(electrical[key] is None for key in required_electrical):
        blockers.append("electrical_profile_incomplete")
    expected_polarities = {
        "vcom_mv": -1,
        "vgh_mv": 1,
        "vgl_mv": -1,
        "vsh_mv": 1,
        "vsl_mv": -1,
    }
    for key, polarity in expected_polarities.items():
        value = electrical[key]
        if value is not None and (value == 0 or (value > 0) != (polarity > 0)):
            blockers.append(f"electrical_polarity_invalid:{key}")
    if not electrical["phase_timing_documented"]:
        blockers.append("phase_timing_undocumented")
    if recovery["known_good_profile_sha256"] is None:
        blockers.append("known_good_profile_missing")
    if recovery["white_recovery_contract_sha256"] is None:
        blockers.append("recovery_contract_missing")
    if not recovery["restore_otp_mode_without_programming"]:
        blockers.append("otp_mode_restore_not_proven")
    if not recovery["validated_on_sacrificial_panel"]:
        blockers.append("sacrificial_panel_recovery_not_validated")
    return blockers


def evaluate_candidate(
    candidate: Mapping[str, Any],
    *,
    controller_payload_bytes: Mapping[str, bytes] | None = None,
    evidence_bundle: Mapping[str, Any] | None = None,
    evidence_artifact_bytes: Mapping[str, bytes] | None = None,
    trusted_format_registrations: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a deterministic, offline-only completeness report.

    This module has no hardware execution path.  A structurally complete
    report therefore remains explicitly non-executable; candidate-supplied
    qualification gates are attestations, not physical authorization.
    """

    validated = validate_candidate(candidate)
    manifest_blockers = _identity_blockers(validated)
    payload_checks: dict[str, dict[str, Any]] = {}
    expected_payloads = validated["controller_payloads"]
    if validated["payload"]["representation"] == "plaintext_decoded_3bit_lut":
        if controller_payload_bytes is None or set(controller_payload_bytes) != {
            "CS1",
            "CS2",
        }:
            manifest_blockers.append("both_controller_payload_bytes_not_supplied")
        else:
            for controller in ("CS1", "CS2"):
                raw = controller_payload_bytes[controller]
                if not isinstance(raw, bytes):
                    raise RuntimeWaveformContractError(
                        f"{controller} supplied payload must be immutable bytes"
                    )
                expected = expected_payloads[controller]
                actual = {"bytes": len(raw), "sha256": sha256_hex(raw)}
                passed = (
                    actual["bytes"] == expected["bytes"]
                    and actual["sha256"] == expected["sha256"]
                )
                payload_checks[controller] = {**actual, "identity_passed": passed}
                if not passed:
                    manifest_blockers.append(
                        f"{controller.lower()}_payload_identity_mismatch"
                    )
    else:
        payload_checks = {
            "CS1": {"identity_passed": False, "reason": "decoded payload absent"},
            "CS2": {"identity_passed": False, "reason": "decoded payload absent"},
        }
    for name in GATE_NAMES:
        if not validated["gates"][name]:
            manifest_blockers.append(f"gate_false:{name}")
    manifest_blockers = sorted(set(manifest_blockers))
    manifest_complete = not manifest_blockers

    evidence_report: dict[str, Any] | None = None
    evidence_blockers: list[str] = []
    if evidence_bundle is None and evidence_artifact_bytes is None:
        evidence_blockers.append("deep_evidence_bundle_not_supplied")
    elif evidence_bundle is None or evidence_artifact_bytes is None:
        raise RuntimeWaveformContractError(
            "evidence bundle and evidence artifact bytes must be supplied together"
        )
    elif controller_payload_bytes is None:
        evidence_blockers.append("deep_evidence_requires_both_controller_payloads")
    else:
        from . import evidence as evidence_contract  # local import avoids a cycle

        try:
            kwargs: dict[str, Any] = {}
            if trusted_format_registrations is not None:
                kwargs["trusted_format_registrations"] = trusted_format_registrations
            evidence_report = evidence_contract.validate_evidence_bundle(
                candidate,
                evidence_bundle,
                controller_payload_bytes=controller_payload_bytes,
                artifact_bytes=evidence_artifact_bytes,
                **kwargs,
            )
        except evidence_contract.EvidenceBundleError as error:
            raise RuntimeWaveformContractError(str(error)) from error
        evidence_blockers.extend(evidence_report["blocker_codes"])
        if not evidence_report["offline_evidence_complete"]:
            evidence_blockers.append("deep_evidence_incomplete")
    evidence_blockers = sorted(set(evidence_blockers))
    offline_blockers = sorted(set(manifest_blockers + evidence_blockers))
    offline_complete = manifest_complete and not evidence_blockers
    hardware_blockers = [HARDWARE_EXECUTION_BLOCKER]
    blockers = sorted(set(offline_blockers + hardware_blockers))
    manifest_sha = sha256_hex(canonical_json_bytes(candidate))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EVALUATION_KIND,
        "profile_id": candidate["profile_id"],
        "candidate_manifest_sha256": manifest_sha,
        "valid": True,
        "manifest_contract_complete": manifest_complete,
        "manifest_blocker_codes": manifest_blockers,
        "offline_contract_complete": offline_complete,
        "offline_blocker_codes": offline_blockers,
        "deep_evidence_validated": bool(
            evidence_report is not None
            and evidence_report["offline_evidence_complete"]
        ),
        "evidence_evaluation": evidence_report,
        "hardware_execution_eligible": False,
        "execution_ready": False,
        "classification": (
            OFFLINE_COMPLETE_CLASSIFICATION
            if offline_complete
            else BLOCKED_CLASSIFICATION
        ),
        "blocker_codes": blockers,
        "hardware_execution_blocker_codes": hardware_blockers,
        "qualification_gates_are_candidate_attestations": True,
        "controller_payload_checks": payload_checks,
        "hardware_io_performed": False,
        "network_io_performed": False,
        "visible_refresh_authorized": False,
    }


def build_reference_blocked_candidate(*, created_at: str) -> dict[str, Any]:
    """Describe current STM32/OQC evidence without embedding or approving its LUT."""

    _timestamp(created_at, label="created_at")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": CANDIDATE_KIND,
        "profile_id": "stm32-oqc-reference-evidence-v1",
        "created_at": created_at,
        "hardware_tested": False,
        "panel": {
            "model": PANEL_MODEL,
            "serial": "MF750M009T6420/1582643AGY44",
            "batch_id": None,
            "controller_model": CONTROLLER_MODEL,
            "controller_revision": None,
            "controller_count": 2,
            "cascade": True,
            "panel_width": PANEL_WIDTH,
            "panel_height": PANEL_HEIGHT,
            "controller_width": CONTROLLER_WIDTH,
            "controller_height": CONTROLLER_HEIGHT,
        },
        "encoding": {
            "bits_per_pixel": 3,
            "transport_codes": list(TRANSPORT_CODES),
            "formal_codes": list(FORMAL_CODES),
            "experimental_codes": list(EXPERIMENTAL_CODES),
            "channel_model": "indexed_particle_target_states_not_independent_rgb_channels",
        },
        "payload": {
            "representation": "identity_only_missing_decoded_payload",
            "format_id": None,
            "format_document_sha256": None,
            "controller_payloads": [
                {"controller": "CS1", "bytes": None, "sha256": None},
                {"controller": "CS2", "bytes": None, "sha256": None},
            ],
        },
        "electrical": {
            "temperature_min_c": None,
            "temperature_max_c": None,
            "vcom_mv": None,
            "vgh_mv": None,
            "vgl_mv": None,
            "vsh_mv": None,
            "vsl_mv": None,
            "frame_rate_hz": None,
            "phase_timing_documented": False,
        },
        "operation_contract": {
            "mode": "runtime_lut_ram_only",
            "commands": [
                {"name": "mcu_lut_mode_select", "opcode": 233, "purpose": "ram_lut_mode"},
                {"name": "lut_ram_write", "opcode": 32, "purpose": "runtime_lut_data"},
            ],
            "otp_programming_allowed": False,
            "otp_erase_allowed": False,
            "startup_auto_apply": False,
            "network_raw_upload_allowed": False,
        },
        "provenance": {
            "reference_artifact_sha256": "c8174a2c9082a826c7e77029da8d6bc54eee498421580badb2753eb911aa9ead",
            "source_payload_sha256": "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b",
            "loader_source_sha256": None,
            "vendor_or_panel_owner_review_id": None,
            "source_is_current_panel_3bit": False,
        },
        "recovery": {
            "known_good_profile_sha256": None,
            "white_recovery_contract_sha256": None,
            "restore_otp_mode_without_programming": False,
            "validated_on_sacrificial_panel": False,
        },
        "qualification_gates": {name: False for name in GATE_NAMES},
    }
