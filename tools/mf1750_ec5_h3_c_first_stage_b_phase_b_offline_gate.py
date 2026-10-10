#!/usr/bin/env python3
"""Offline Phase-B gate contract bound to one committed Phase-A success.

This module has no live execution subcommand and contains no HTTP, serial,
subprocess, COM, GPIO, or hardware client.  It validates and losslessly replays
the already committed Phase-A ``/version`` entity, freezes the remaining
``manifest -> status -> report`` bodyless-GET state machine, and exercises only
an exact in-memory scripted fake.  It does not create a fresh onsite gate,
production authority, authorization phrase, attempt registry, terminal receipt,
claim, or visible-action permission.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from copy import deepcopy
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
from typing import Any, BinaryIO, Final, Mapping, Sequence

from tools import mf1750_ec5_h3_c_first_stage_b_phase_a_authority_contract as phase_a
from tools import mf1750_ec5_h3_c_first_stage_b_read_only_facade_contract as facade
from tools import mf1750_ec5_h3_matched_control_contract as contract
from tools import mf1750_ec5_h3_matched_control_physical_once as physical
from tools.mf1750_ec5_h3_c_first_stage_b_phase_a_live_once import (
    PhaseALiveError,
    require_live_phase_a_success_for_future_phase_b,
)


SCHEMA_VERSION: Final = 1
KIND: Final = "mf1750-ec5-h3-c-first-stage-b-phase-b-offline-gate-v1"
CLASSIFICATION: Final = (
    "OFFLINE_PHASE_B_PREDECESSOR_AND_STATE_MACHINE_CONTRACT_NOT_LIVE_AUTHORITY"
)
FAKE_RESULT_KIND: Final = (
    "mf1750-ec5-h3-c-first-stage-b-phase-b-scripted-fake-result-v1"
)
FAKE_RESULT_CLASSIFICATION: Final = (
    "SYNTHETIC_PHASE_B_FAKE_ONLY_NOT_DEVICE_OR_LIVE_EVIDENCE"
)
PHASE_B_ENDPOINT_NAMES: Final = tuple(phase_a.PHASE_B_ENDPOINTS)
EXPECTED_BASE_URL: Final = phase_a.EXPECTED_CANDIDATE_BASE_URL
EXPECTED_IPV4: Final = phase_a.EXPECTED_CANDIDATE_IPV4
EXPECTED_PORT: Final = 80
SUCCESS_CLASSIFICATION: Final = (
    "V10_MANIFEST_STATUS_REPORT_PROTOCOL_RESPONSE_CONFORMANCE"
)
MAX_RESPONSE_ENTITY_BYTES: Final = facade.MAX_JSON_BYTES


class PhaseBOfflineGateError(ValueError):
    """A predecessor, binding, state-machine, or fake-only invariant differs."""


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    root = deepcopy(dict(unsigned))
    root["integrity"] = {
        "algorithm": "sha256",
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
        "canonical_sha256": contract.sha256(root),
    }
    return root


def _validate_seal(root: Mapping[str, Any], *, label: str) -> str:
    unsigned = {key: value for key, value in root.items() if key != "integrity"}
    expected = _seal(unsigned)["integrity"]
    if root.get("integrity") != expected:
        raise PhaseBOfflineGateError(f"{label} canonical integrity differs")
    return str(expected["canonical_sha256"])


def _absolute(path: Path, *, label: str) -> Path:
    try:
        return phase_a._safe_absolute(path, label=label)  # noqa: SLF001
    except phase_a.PhaseAAuthorityError as error:
        raise PhaseBOfflineGateError(str(error)) from error


def _read_json(path: Path, *, label: str) -> tuple[Path, bytes, Mapping[str, Any]]:
    try:
        resolved, payload, root = facade._read_json(path, label=label)  # noqa: SLF001
    except facade.StageBFacadeContractError as error:
        raise PhaseBOfflineGateError(str(error)) from error
    if payload != contract.canonical_json_bytes(root) + b"\n":
        raise PhaseBOfflineGateError(f"{label} is not exact canonical JSON plus one LF")
    return resolved, payload, root


def _source_binding(path: Path, *, label: str) -> dict[str, Any]:
    try:
        return facade._file_binding(path, label=label)  # noqa: SLF001
    except facade.StageBFacadeContractError as error:
        raise PhaseBOfflineGateError(str(error)) from error


def _decode_bound_base64(*, value: Any, length: Any, sha256: Any, label: str) -> bytes:
    if type(value) is not str or type(length) is not int or type(sha256) is not str:
        raise PhaseBOfflineGateError(f"{label} evidence type differs")
    if length <= 0 or length > MAX_RESPONSE_ENTITY_BYTES:
        raise PhaseBOfflineGateError(f"{label} evidence length differs")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise PhaseBOfflineGateError(f"{label} evidence base64 differs") from error
    if len(decoded) != length or contract.sha256(decoded) != sha256:
        raise PhaseBOfflineGateError(f"{label} evidence hash differs")
    return decoded


def _request_wire(path: str) -> bytes:
    if not path.startswith("/api/ec5/h3-matched-control-v2/"):
        raise PhaseBOfflineGateError("Phase-B request path differs")
    return (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {EXPECTED_IPV4}\r\n"
        "Accept: application/json\r\n"
        "Accept-Encoding: identity\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii")


@dataclass(frozen=True)
class _PhaseAPredecessor:
    envelope_path: Path
    envelope_payload: bytes
    envelope: Mapping[str, Any]
    authority_path: Path
    authority_payload: bytes
    authority: Mapping[str, Any]
    registry_path: Path
    registry_payload: bytes
    registry: Mapping[str, Any]
    receipt_path: Path
    receipt_payload: bytes
    receipt: Mapping[str, Any]
    validation_summary: Mapping[str, Any]


def _load_phase_a_predecessor(
    *, live_envelope_file: Path, terminal_receipt_file: Path
) -> _PhaseAPredecessor:
    try:
        summary = require_live_phase_a_success_for_future_phase_b(
            terminal_receipt_file,
            live_envelope_file=live_envelope_file,
        )
    except PhaseALiveError as error:
        raise PhaseBOfflineGateError(
            f"Phase-A predecessor is not committed success: {error}"
        ) from error
    if (
        summary.get("valid") is not True
        or summary.get("terminal_success") is not True
        or summary.get("terminal_outcome_committed") is not True
        or summary.get("version_protocol_response_conformance") is not True
        or summary.get("may_only_request_separate_phase_b_authority") is not True
        or summary.get("phase_b_authority_generated") is not False
        or summary.get("phase_b_authorization_generated") is not False
        or summary.get("phase_b_executed") is not False
    ):
        raise PhaseBOfflineGateError("Phase-A predecessor summary boundary differs")

    envelope_path, envelope_payload, envelope = _read_json(
        live_envelope_file, label="Phase-A live envelope"
    )
    receipt_path, receipt_payload, receipt = _read_json(
        terminal_receipt_file, label="Phase-A committed terminal receipt"
    )
    attempt = envelope.get("attempt")
    authority_binding = envelope.get("offline_phase_a_authority_binding")
    if not isinstance(attempt, Mapping) or not isinstance(authority_binding, Mapping):
        raise PhaseBOfflineGateError("Phase-A envelope bindings are absent")
    expected_receipt = _absolute(
        Path(str(attempt.get("terminal_receipt_file"))),
        label="Phase-A terminal receipt",
    )
    if receipt_path != expected_receipt:
        raise PhaseBOfflineGateError("Phase-A terminal receipt path differs")

    authority_path, authority_payload, authority = _read_json(
        Path(str(authority_binding.get("path"))),
        label="Phase-A offline authority",
    )
    try:
        authority_summary = phase_a.validate_phase_a_authority(
            authority, require_attempt_paths_absent=False
        )
    except phase_a.PhaseAAuthorityError as error:
        raise PhaseBOfflineGateError(
            f"Phase-A offline authority differs: {error}"
        ) from error
    if (
        authority_binding.get("bytes") != len(authority_payload)
        or authority_binding.get("sha256") != contract.sha256(authority_payload)
        or authority_binding.get("authority_id") != authority_summary["authority_id"]
        or authority_binding.get("canonical_sha256")
        != authority_summary["canonical_sha256"]
    ):
        raise PhaseBOfflineGateError("Phase-A envelope authority binding differs")

    registry_path, registry_payload, registry = _read_json(
        Path(str(attempt.get("registry_file"))),
        label="Phase-A immutable attempt registry",
    )
    if receipt.get("registry_whole_file_sha256") != contract.sha256(
        registry_payload
    ) or receipt.get("attempt_registry_file") != str(registry_path):
        raise PhaseBOfflineGateError("Phase-A receipt registry binding differs")
    return _PhaseAPredecessor(
        envelope_path=envelope_path,
        envelope_payload=envelope_payload,
        envelope=envelope,
        authority_path=authority_path,
        authority_payload=authority_payload,
        authority=authority,
        registry_path=registry_path,
        registry_payload=registry_payload,
        registry=registry,
        receipt_path=receipt_path,
        receipt_payload=receipt_payload,
        receipt=receipt,
        validation_summary=summary,
    )


def _replay_phase_a_version(
    predecessor: _PhaseAPredecessor,
    *,
    facade_blueprint: Mapping[str, Any],
) -> dict[str, Any]:
    endpoints = predecessor.receipt.get("endpoint_outcomes")
    if not isinstance(endpoints, list) or len(endpoints) != 1:
        raise PhaseBOfflineGateError("Phase-A endpoint evidence count differs")
    endpoint = endpoints[0]
    if not isinstance(endpoint, Mapping):
        raise PhaseBOfflineGateError("Phase-A endpoint evidence type differs")
    ordered = facade_blueprint["read_only_state_machine"]["ordered_requests"]
    if not isinstance(ordered, list) or len(ordered) != 4:
        raise PhaseBOfflineGateError("facade diagnostic request count differs")
    version_request = ordered[0]
    if (
        version_request.get("path") != "/api/ec5/h3-matched-control-v2/version"
        or endpoint.get("absolute_url") != version_request.get("absolute_url")
        or endpoint.get("method") != "GET"
        or endpoint.get("validation_outcome") != "PASS"
        or endpoint.get("last_completed_gate") != "EXACT_V10_VALIDATED"
        or endpoint.get("http_status") != 200
    ):
        raise PhaseBOfflineGateError("Phase-A version success evidence differs")
    body = _decode_bound_base64(
        value=endpoint.get("response_entity_body_base64"),
        length=endpoint.get("response_entity_body_bytes"),
        sha256=endpoint.get("response_entity_body_sha256"),
        label="Phase-A version response entity",
    )
    release_file = Path(
        str(facade_blueprint["frozen_v10_validator_binding"]["release_file"])
    )
    try:
        context = physical.load_release(release_file)
        parsed, boot_nonce = facade.decode_and_validate_v10_response_bytes(
            "version", body, context
        )
    except Exception as error:
        raise PhaseBOfflineGateError(
            f"Phase-A version raw replay failed: {error}"
        ) from error
    parsed_sha256 = contract.sha256(parsed)
    if (
        boot_nonce is not None
        or endpoint.get("strict_parsed_canonical_sha256") != parsed_sha256
    ):
        raise PhaseBOfflineGateError("Phase-A version replay outcome differs")
    return {
        "endpoint_name": "version",
        "method": "GET",
        "absolute_url": endpoint["absolute_url"],
        "response_entity_body_bytes": len(body),
        "response_entity_body_sha256": contract.sha256(body),
        "lossless_response_entity_base64_stored_in_predecessor_receipt": True,
        "strict_parsed_canonical_sha256": parsed_sha256,
        "raw_body_replayed_through_exact_v10_decoder_now": True,
        "replay_outcome": "PASS_V10_PROTOCOL_RESPONSE_CONFORMANCE",
        "responder_or_device_identity_proven": False,
        "trusted_ip_binding_proven": False,
        "fresh_boot_or_active_application_proven": False,
    }


def _phase_b_requests(facade_blueprint: Mapping[str, Any]) -> list[dict[str, Any]]:
    ordered = facade_blueprint["read_only_state_machine"]["ordered_requests"]
    if not isinstance(ordered, list) or len(ordered) != 4:
        raise PhaseBOfflineGateError("facade diagnostic request count differs")
    names = [str(item.get("path", "")).rsplit("/", 1)[-1] for item in ordered]
    if names != ["version", *PHASE_B_ENDPOINT_NAMES]:
        raise PhaseBOfflineGateError("facade diagnostic endpoint order differs")
    requests: list[dict[str, Any]] = []
    for phase_b_ordinal, (name, source) in enumerate(
        zip(PHASE_B_ENDPOINT_NAMES, ordered[1:], strict=True), start=1
    ):
        path = str(source["path"])
        absolute_url = str(source["absolute_url"])
        if (
            source.get("method") != "GET"
            or absolute_url != f"{EXPECTED_BASE_URL}{path}"
            or int(source["ordinal"]) != phase_b_ordinal + 1
        ):
            raise PhaseBOfflineGateError(f"Phase-B {name} request differs")
        wire = _request_wire(path)
        requests.append(
            {
                "phase_b_ordinal": phase_b_ordinal,
                "full_diagnostic_ordinal": phase_b_ordinal + 1,
                "name": name,
                "method": "GET",
                "path": path,
                "absolute_url": absolute_url,
                "request_headers": {
                    "Host": EXPECTED_IPV4,
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                },
                "request_body": None,
                "request_wire_bytes": len(wire),
                "request_wire_sha256": contract.sha256(wire),
                "request_wire_ascii": wire.decode("ascii"),
            }
        )
    return requests


def materialize_phase_b_offline_gate(
    *,
    phase_a_live_envelope_file: Path,
    phase_a_terminal_receipt_file: Path,
    facade_blueprint_file: Path,
    gate_blueprint_file: Path,
    planned_phase_b_registry_file: Path,
    planned_phase_b_terminal_receipt_file: Path,
    _require_planned_paths_absent: bool = True,
) -> dict[str, Any]:
    """Build a deterministic offline gate; never create live artifacts."""

    output_path = _absolute(gate_blueprint_file, label="Phase-B gate blueprint")
    registry_path = _absolute(
        planned_phase_b_registry_file, label="planned Phase-B registry"
    )
    terminal_path = _absolute(
        planned_phase_b_terminal_receipt_file,
        label="planned Phase-B terminal receipt",
    )
    finalization_temp = _absolute(
        terminal_path.with_name(terminal_path.name + ".phase-b-finalize-o-excl.tmp"),
        label="planned Phase-B finalization temp",
    )
    distinct_paths = {output_path, registry_path, terminal_path, finalization_temp}
    if len(distinct_paths) != 4:
        raise PhaseBOfflineGateError("Phase-B blueprint/planned paths must be distinct")
    if _require_planned_paths_absent:
        for label, path in (
            ("planned Phase-B registry", registry_path),
            ("planned Phase-B terminal receipt", terminal_path),
            ("planned Phase-B finalization temp", finalization_temp),
        ):
            if path.exists():
                raise PhaseBOfflineGateError(f"{label} already exists")

    facade_path, facade_payload, facade_root = _read_json(
        facade_blueprint_file, label="Stage-B exact-surface facade blueprint"
    )
    try:
        facade_summary = facade.validate_blueprint(
            facade_root, require_live_output_absent=True
        )
    except facade.StageBFacadeContractError as error:
        raise PhaseBOfflineGateError(
            f"Stage-B facade blueprint differs: {error}"
        ) from error
    if (
        facade_summary.get("valid") is not True
        or facade_summary.get("execution_ready") is not False
        or facade_summary.get("live_authorized") is not False
    ):
        raise PhaseBOfflineGateError("Stage-B facade authority boundary differs")

    predecessor = _load_phase_a_predecessor(
        live_envelope_file=phase_a_live_envelope_file,
        terminal_receipt_file=phase_a_terminal_receipt_file,
    )
    occupied = {
        predecessor.envelope_path,
        predecessor.authority_path,
        predecessor.registry_path,
        predecessor.receipt_path,
        facade_path,
    }
    if distinct_paths & occupied:
        raise PhaseBOfflineGateError(
            "Phase-B blueprint/planned paths collide with predecessor evidence"
        )

    authority = predecessor.authority
    future_gate = authority.get("future_phase_b_gate")
    if not isinstance(future_gate, Mapping):
        raise PhaseBOfflineGateError("Phase-A future Phase-B gate is absent")
    if (
        future_gate.get("phase_b_endpoints_exactly") != list(PHASE_B_ENDPOINT_NAMES)
        or future_gate.get("phase_b_repeats_version") is not False
        or future_gate.get("requires_new_fresh_onsite_gate_after_phase_a") is not True
        or future_gate.get("requires_new_distinct_phase_b_user_authorization")
        is not True
        or future_gate.get("phase_b_registry_must_be_distinct") is not True
    ):
        raise PhaseBOfflineGateError("Phase-A future Phase-B policy differs")
    original_final = _absolute(
        Path(str(authority["attempt"]["original_plan_final_output"])),
        label="original plan final output",
    )
    if terminal_path != original_final:
        raise PhaseBOfflineGateError(
            "planned Phase-B terminal receipt must use original plan final output"
        )
    if facade_root["one_shot_output_contract"]["planned_live_output"] != str(
        terminal_path
    ):
        raise PhaseBOfflineGateError("facade and Phase-B terminal paths differ")

    base_url = str(facade_root["read_only_state_machine"]["selected_base_url"])
    if (
        base_url != EXPECTED_BASE_URL
        or authority["candidate_origin"]["base_url"] != base_url
        or predecessor.receipt.get("offline_authority_binding", {}).get("authority_id")
        != authority["authority_id"]
    ):
        raise PhaseBOfflineGateError("Phase-A/Phase-B candidate binding differs")

    version_replay = _replay_phase_a_version(predecessor, facade_blueprint=facade_root)
    requests = _phase_b_requests(facade_root)
    source_bindings = {
        "phase_b_offline_gate_module": _source_binding(
            Path(__file__), label="Phase-B offline gate module"
        ),
        "phase_a_live_validator_module": _source_binding(
            Path(require_live_phase_a_success_for_future_phase_b.__code__.co_filename),
            label="Phase-A live validator module",
        ),
        "exact_surface_facade_module": _source_binding(
            Path(facade.__file__), label="exact-surface facade module"
        ),
    }

    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "classification": CLASSIFICATION,
        "gate_blueprint_file": str(output_path),
        "phase": "B_REMAINING_READ_ONLY_DIAGNOSTIC_OFFLINE_GATE",
        "phase_a_predecessor": {
            "live_envelope": {
                "path": str(predecessor.envelope_path),
                "bytes": len(predecessor.envelope_payload),
                "sha256": contract.sha256(predecessor.envelope_payload),
                "canonical_sha256": predecessor.envelope["integrity"][
                    "canonical_sha256"
                ],
                "live_envelope_id": predecessor.envelope["live_envelope_id"],
            },
            "offline_authority": {
                "path": str(predecessor.authority_path),
                "bytes": len(predecessor.authority_payload),
                "sha256": contract.sha256(predecessor.authority_payload),
                "canonical_sha256": predecessor.authority["integrity"][
                    "canonical_sha256"
                ],
                "authority_id": predecessor.authority["authority_id"],
            },
            "immutable_registry": {
                "path": str(predecessor.registry_path),
                "bytes": len(predecessor.registry_payload),
                "sha256": contract.sha256(predecessor.registry_payload),
                "canonical_sha256": predecessor.registry["integrity"][
                    "canonical_sha256"
                ],
            },
            "committed_terminal_receipt": {
                "path": str(predecessor.receipt_path),
                "bytes": len(predecessor.receipt_payload),
                "sha256": contract.sha256(predecessor.receipt_payload),
                "canonical_sha256": predecessor.receipt["integrity"][
                    "canonical_sha256"
                ],
                "state": predecessor.receipt["state"],
                "terminal_outcome_committed": True,
                "synthetic_test_only": False,
            },
            "phase_a_authorization_phrase_sha256": predecessor.receipt[
                "authorization_phrase_sha256"
            ],
            "phase_a_authorization_is_consumed_and_not_reusable": True,
            "phase_a_attempt_is_permanently_consumed": True,
            "phase_a_retry_allowed": False,
            "phase_b_generated_or_executed_by_predecessor": False,
            "may_only_request_separate_phase_b_authority": True,
        },
        "phase_a_version_raw_replay": version_replay,
        "exact_surface_facade_binding": {
            "path": str(facade_path),
            "bytes": len(facade_payload),
            "sha256": contract.sha256(facade_payload),
            "blueprint_id": facade_root["blueprint_id"],
            "canonical_sha256": facade_root["integrity"]["canonical_sha256"],
            "classification": facade_root["classification"],
        },
        "candidate_origin": {
            "base_url": base_url,
            "literal_ipv4": EXPECTED_IPV4,
            "port": EXPECTED_PORT,
            "same_literal_origin_as_phase_a": True,
            "trusted": False,
            "responder_or_device_identity_proven": False,
            "trusted_ip_binding_proven": False,
            "fresh_boot_or_active_application_proven": False,
            "network_scan_allowed": False,
            "fallback_allowed": False,
            "redirect_allowed": False,
            "dns_allowed": False,
        },
        "phase_b_state_machine": {
            "version_repeated": False,
            "version_predecessor_must_be_replayed_before_any_phase_b_request": True,
            "ordered_requests": requests,
            "endpoint_set_sha256": contract.sha256(requests),
            "successful_exact_get_count": 3,
            "maximum_get_count": 3,
            "maximum_transport_attempts": 3,
            "maximum_post_count": 0,
            "request_body_count": 0,
            "claim_count": 0,
            "client_mutation_requests": 0,
            "client_visible_refresh_requests": 0,
            "validate_each_response_before_next_request": True,
            "stop_on_first_transport_http_decode_or_validation_error": True,
            "each_endpoint_uses_new_connection_with_connection_close": True,
            "retry": False,
            "fallback": False,
            "automatic_recovery": False,
            "automatic_chaining": False,
        },
        "response_validation_contract": {
            "manifest_status_report_strategy": (
                "frozen_subset_validator_plus_source_pinned_exact_surface_validator"
            ),
            "raw_response_entity_bytes_required": True,
            "strict_utf8_json_required": True,
            "duplicate_keys_nan_infinity_trailing_json_rejected": True,
            "exact_recursive_key_type_and_value_surface_required": True,
            "maximum_response_entity_bytes": MAX_RESPONSE_ENTITY_BYTES,
            "http_status_200_required": True,
            "raw_status_headers_and_entity_evidence_required": True,
            "response_entity_lossless_base64_required": True,
            "response_entity_length_and_sha256_required": True,
            "strict_parsed_canonical_sha256_required": True,
            "validation_stack_and_outcome_required": True,
            "status_boot_nonce_recorded_but_not_phase_a_correlated": True,
            "phase_a_version_contains_no_boot_nonce": True,
            "success_classification": SUCCESS_CLASSIFICATION,
            "success_is_device_identity_proof": False,
            "success_is_trusted_ip_proof": False,
            "success_is_fresh_boot_or_active_slot_proof": False,
            "success_directly_authorizes_visible_action": False,
        },
        "planned_production_artifacts": {
            "phase_b_live_authority": {
                "required": True,
                "present": False,
                "copyable_authorization_phrase_present": False,
                "challenge_present": False,
            },
            "fresh_onsite_gate_after_phase_a": {
                "required": True,
                "present": False,
                "prior_phase_a_onsite_gate_reusable": False,
                "must_freshly_confirm_j2_off_usb_white_3v3_25c_1a_current_monitoring_cutoff_no_changes": True,
            },
            "separate_phase_b_user_authorization": {
                "required": True,
                "present": False,
                "phase_a_authorization_reusable": False,
                "must_bind_future_authority_file_hash_id_attempt_challenge_endpoint_set_and_limits": True,
            },
            "phase_b_attempt_registry": {
                "path": str(registry_path),
                "present": registry_path.exists(),
                "must_be_o_excl_created_and_fsynced_before_socket": True,
                "creation_permanently_consumes_future_authorization": True,
                "distinct_from_phase_a_registry": True,
                "never_deleted_or_retried": True,
            },
            "phase_b_terminal_receipt": {
                "path": str(terminal_path),
                "present": terminal_path.exists(),
                "uses_original_plan_final_output": True,
                "o_excl_checkpoint_before_socket_required": True,
                "terminalization_via_bound_temp_then_atomic_replace_required": True,
                "finalization_temp_file": str(finalization_temp),
                "finalization_temp_present": finalization_temp.exists(),
                "retry_allowed": False,
            },
        },
        "future_terminal_receipt_contract": {
            "one_ordered_outcome_per_attempted_endpoint_required": True,
            "per_endpoint_required_fields": [
                "phase_b_ordinal",
                "full_diagnostic_ordinal",
                "method",
                "path",
                "absolute_url",
                "application_transport_attempts",
                "request_wire_sha256",
                "request_bytes_handed_to_socket_api",
                "http_status",
                "raw_status_and_header_base64",
                "response_entity_body_base64",
                "response_entity_body_bytes",
                "response_entity_body_sha256",
                "strict_parsed_canonical_sha256",
                "validation_stack",
                "validation_outcome",
                "last_completed_gate",
            ],
            "transport_exception_request_wire_emitted": "UNKNOWN",
            "transport_exception_peer_received_request": "UNKNOWN",
            "kernel_tcp_retransmission_possible_and_not_application_retry": True,
            "client_get_requests_maximum": 3,
            "client_post_body_claim_mutation_visible_refresh_requests": 0,
            "actual_device_or_background_side_effects": (
                "UNKNOWN_NOT_OBSERVED_BY_READ_ONLY_CLIENT"
            ),
            "terminal_failure_never_unlocks_next_endpoint": True,
            "terminal_success_never_generates_visible_authority": True,
        },
        "implementation_surface": {
            "offline_build_validate_only_cli": True,
            "exact_type_scripted_fake_api_present": True,
            "fake_api_network_requests": 0,
            "fake_api_cannot_write_planned_production_paths": True,
            "live_http_transport_implemented": False,
            "live_execute_subcommand_present": False,
            "production_authority_materialized": False,
            "production_authorization_phrase_materialized": False,
            "production_registry_materialized": False,
            "production_terminal_receipt_materialized": False,
            "device_io_performed": False,
            "execution_ready": False,
            "live_authorized": False,
        },
        "source_bindings": source_bindings,
        "unsatisfied_live_gates": [
            "reviewed_hash_frozen_phase_b_live_runner_and_envelope",
            "new_fresh_onsite_gate_after_phase_a",
            "new_distinct_byte_exact_phase_b_user_authorization",
            "phase_b_registry_first_o_excl_terminalization_implementation",
            "explicit_post_diagnostic_identity_limitation_disposition_before_visible_action",
        ],
    }
    unsigned["offline_gate_id"] = contract.sha256(unsigned)
    return _seal(unsigned)


def validate_phase_b_offline_gate(
    root: Mapping[str, Any], *, require_planned_paths_absent: bool = True
) -> dict[str, Any]:
    """Deep-rebuild the gate and replay its Phase-A predecessor offline."""

    canonical = _validate_seal(root, label="Phase-B offline gate")
    if (
        root.get("schema_version") != SCHEMA_VERSION
        or root.get("kind") != KIND
        or root.get("classification") != CLASSIFICATION
    ):
        raise PhaseBOfflineGateError("Phase-B offline gate schema/kind differs")
    predecessor = root.get("phase_a_predecessor")
    facade_binding = root.get("exact_surface_facade_binding")
    planned = root.get("planned_production_artifacts")
    if not all(
        isinstance(value, Mapping) for value in (predecessor, facade_binding, planned)
    ):
        raise PhaseBOfflineGateError("Phase-B gate reconstruction bindings are absent")
    rebuilt = materialize_phase_b_offline_gate(
        phase_a_live_envelope_file=Path(str(predecessor["live_envelope"]["path"])),
        phase_a_terminal_receipt_file=Path(
            str(predecessor["committed_terminal_receipt"]["path"])
        ),
        facade_blueprint_file=Path(str(facade_binding["path"])),
        gate_blueprint_file=Path(str(root["gate_blueprint_file"])),
        planned_phase_b_registry_file=Path(
            str(planned["phase_b_attempt_registry"]["path"])
        ),
        planned_phase_b_terminal_receipt_file=Path(
            str(planned["phase_b_terminal_receipt"]["path"])
        ),
        _require_planned_paths_absent=require_planned_paths_absent,
    )
    if contract.canonical_json_bytes(root) != contract.canonical_json_bytes(rebuilt):
        raise PhaseBOfflineGateError(
            "Phase-B offline gate differs from deterministic reconstruction"
        )
    expected_id = contract.sha256(
        {
            key: value
            for key, value in root.items()
            if key not in {"offline_gate_id", "integrity"}
        }
    )
    if root.get("offline_gate_id") != expected_id:
        raise PhaseBOfflineGateError("Phase-B offline gate ID differs")
    return {
        "valid": True,
        "offline_gate_id": root["offline_gate_id"],
        "canonical_sha256": canonical,
        "classification": CLASSIFICATION,
        "phase_a_predecessor_committed_success": True,
        "phase_a_raw_version_replayed": True,
        "phase_b_endpoints": list(PHASE_B_ENDPOINT_NAMES),
        "phase_b_repeats_version": False,
        "maximum_get_count": 3,
        "maximum_post_body_claim_mutation_visible_refresh_count": 0,
        "production_authority_or_authorization_generated": False,
        "planned_registry_or_receipt_created": False,
        "execution_ready": False,
        "live_authorized": False,
        "device_io_performed": False,
        "unsatisfied_live_gates": list(root["unsatisfied_live_gates"]),
    }


def load_phase_b_offline_gate(path: Path) -> Mapping[str, Any]:
    _, _, root = _read_json(path, label="Phase-B offline gate")
    return root


def write_new_phase_b_offline_gate(path: Path, root: Mapping[str, Any]) -> None:
    validate_phase_b_offline_gate(root, require_planned_paths_absent=True)
    target = _absolute(path, label="Phase-B offline gate output")
    if target != Path(str(root["gate_blueprint_file"])):
        raise PhaseBOfflineGateError("Phase-B offline gate self-path differs")
    try:
        parent = facade._assert_directory_chain(  # noqa: SLF001
            target.parent, create=True, label="Phase-B offline gate output"
        )
    except facade.StageBFacadeContractError as error:
        raise PhaseBOfflineGateError(str(error)) from error
    target = parent / target.name
    try:
        with target.open("xb") as handle:
            handle.write(contract.canonical_json_bytes(root) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise PhaseBOfflineGateError(
            "Phase-B offline gate output already exists"
        ) from error
    except OSError as error:
        raise PhaseBOfflineGateError(
            f"could not write Phase-B offline gate: {error}"
        ) from error


@dataclass(frozen=True)
class ScriptedPhaseBFakeResponse:
    """One in-memory response; it has no URL-opening capability."""

    status: int
    body: bytes


class ScriptedPhaseBFakeRequester:
    """Exact three-step fake that blocks fetch-before-validation ordering."""

    def __init__(
        self, script: Sequence[tuple[str, ScriptedPhaseBFakeResponse]]
    ) -> None:
        self._script: list[tuple[str, ScriptedPhaseBFakeResponse]] = []
        for absolute_url, response in script:
            if (
                type(absolute_url) is not str
                or type(response) is not ScriptedPhaseBFakeResponse
            ):
                raise PhaseBOfflineGateError("Phase-B fake script item type differs")
            if type(response.status) is not int or type(response.body) is not bytes:
                raise PhaseBOfflineGateError("Phase-B fake response type differs")
            self._script.append(
                (
                    absolute_url,
                    ScriptedPhaseBFakeResponse(response.status, response.body),
                )
            )
        self._cursor = 0
        self._unvalidated_url: str | None = None
        self.calls: list[dict[str, Any]] = []
        self.validation_acknowledgements: list[str] = []

    def fetch(
        self,
        *,
        method: str,
        absolute_url: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> ScriptedPhaseBFakeResponse:
        if self._unvalidated_url is not None:
            raise PhaseBOfflineGateError(
                "Phase-B fake attempted next request before prior validation"
            )
        expected_headers = {
            "Host": EXPECTED_IPV4,
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Connection": "close",
        }
        if method != "GET" or body is not None or dict(headers) != expected_headers:
            raise PhaseBOfflineGateError("Phase-B fake permits exact bodyless GET only")
        if self._cursor >= len(self._script):
            raise PhaseBOfflineGateError("Phase-B fake exceeded scripted budget")
        expected_url, response = self._script[self._cursor]
        if absolute_url != expected_url:
            raise PhaseBOfflineGateError("Phase-B fake origin/order differs")
        self._cursor += 1
        self._unvalidated_url = absolute_url
        self.calls.append(
            {
                "phase_b_ordinal": self._cursor,
                "method": method,
                "absolute_url": absolute_url,
                "headers": dict(headers),
                "body": None,
            }
        )
        return response

    def acknowledge_validation(self, absolute_url: str) -> None:
        if self._unvalidated_url != absolute_url:
            raise PhaseBOfflineGateError(
                "Phase-B fake validation acknowledgement differs"
            )
        self.validation_acknowledgements.append(absolute_url)
        self._unvalidated_url = None


@dataclass
class _FakeReservation:
    path: Path
    handle: BinaryIO

    def finalize(self, root: Mapping[str, Any]) -> None:
        payload = contract.canonical_json_bytes(root) + b"\n"
        try:
            self.handle.seek(0)
            self.handle.truncate(0)
            self.handle.write(payload)
            self.handle.flush()
            os.fsync(self.handle.fileno())
        except OSError as error:
            raise PhaseBOfflineGateError(
                f"could not finalize Phase-B fake result: {error}"
            ) from error


def _reserve_fake_output(path: Path, *, gate: Mapping[str, Any]) -> _FakeReservation:
    target = _absolute(path, label="Phase-B fake output")
    planned = gate["planned_production_artifacts"]
    forbidden = {
        Path(str(planned["phase_b_attempt_registry"]["path"])),
        Path(str(planned["phase_b_terminal_receipt"]["path"])),
        Path(str(planned["phase_b_terminal_receipt"]["finalization_temp_file"])),
        Path(str(gate["gate_blueprint_file"])),
    }
    if target in forbidden:
        raise PhaseBOfflineGateError(
            "Phase-B fake cannot write a planned production or gate path"
        )
    if not target.name.endswith(".phase-b-fake-only.json"):
        raise PhaseBOfflineGateError(
            "Phase-B fake output must end with '.phase-b-fake-only.json'"
        )
    try:
        parent = facade._assert_directory_chain(  # noqa: SLF001
            target.parent, create=True, label="Phase-B fake output"
        )
    except facade.StageBFacadeContractError as error:
        raise PhaseBOfflineGateError(str(error)) from error
    target = parent / target.name
    try:
        handle = target.open("xb+", buffering=0)
    except FileExistsError as error:
        raise PhaseBOfflineGateError(
            "Phase-B fake output already exists; no retry is allowed"
        ) from error
    except OSError as error:
        raise PhaseBOfflineGateError(
            f"could not reserve Phase-B fake output: {error}"
        ) from error
    reservation = _FakeReservation(target, handle)
    try:
        reservation.finalize(
            _seal(
                {
                    "schema_version": SCHEMA_VERSION,
                    "kind": FAKE_RESULT_KIND,
                    "classification": FAKE_RESULT_CLASSIFICATION,
                    "state": "RESERVED_FAKE_ONLY_ATTEMPT_CONSUMED",
                    "output_file": str(target),
                    "offline_gate_id": gate["offline_gate_id"],
                    "reserved_before_scripted_fake_requests": True,
                    "retry_allowed": False,
                    "network_requests": 0,
                    "device_io_performed": False,
                }
            )
        )
    except Exception:
        handle.close()
        raise
    return reservation


def _fake_result(
    *,
    gate: Mapping[str, Any],
    reservation: _FakeReservation,
    requester: ScriptedPhaseBFakeRequester,
    endpoint_outcomes: Sequence[Mapping[str, Any]],
    validated_names: Sequence[str],
    status_boot_nonce: str | None,
    error: Exception | None,
) -> dict[str, Any]:
    success = error is None
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": FAKE_RESULT_KIND,
        "classification": FAKE_RESULT_CLASSIFICATION,
        "state": (
            "COMPLETE_PHASE_B_FAKE_ONLY_VALIDATION"
            if success
            else "TERMINAL_PHASE_B_FAKE_ONLY_FAILURE"
        ),
        "outcome": (
            "FAKE_ONLY_MANIFEST_STATUS_REPORT_CONFORMANCE"
            if success
            else "TERMINAL_FAKE_ONLY_FAILURE_NO_RETRY"
        ),
        "output_file": str(reservation.path),
        "offline_gate_id": gate["offline_gate_id"],
        "offline_gate_canonical_sha256": gate["integrity"]["canonical_sha256"],
        "phase_a_version_raw_replay_performed_before_fake_requests": True,
        "phase_a_version_was_not_requested_again": True,
        "phase_a_predecessor_receipt_sha256": gate["phase_a_predecessor"][
            "committed_terminal_receipt"
        ]["sha256"],
        "requests_attempted": len(requester.calls),
        "request_log": deepcopy(requester.calls),
        "endpoint_outcomes": deepcopy(list(endpoint_outcomes)),
        "validated_response_names": list(validated_names),
        "validation_acknowledgements": list(requester.validation_acknowledgements),
        "status_boot_nonce": status_boot_nonce,
        "success_classification": SUCCESS_CLASSIFICATION if success else None,
        "success_is_responder_or_device_identity_proof": False,
        "success_is_trusted_ip_proof": False,
        "success_is_fresh_boot_or_active_slot_proof": False,
        "success_authorizes_visible_action": False,
        "get_requests_simulated": len(requester.calls),
        "post_requests": 0,
        "request_bodies": 0,
        "claims": 0,
        "client_mutation_requests": 0,
        "client_visible_refresh_requests": 0,
        "fallbacks": 0,
        "retries": 0,
        "automatic_recoveries": 0,
        "automatic_chains": 0,
        "network_requests": 0,
        "serial_or_com_accesses": 0,
        "subprocesses": 0,
        "hardware_accessed": False,
        "device_io_performed": False,
        "production_authority_or_authorization_generated": False,
        "planned_production_paths_touched": False,
        "retry_allowed": False,
        "error_type": None if success else type(error).__name__,
        "error": None if success else str(error),
    }
    return _seal(unsigned)


def run_phase_b_scripted_fake_only(
    gate: Mapping[str, Any],
    *,
    requester: ScriptedPhaseBFakeRequester,
    fake_output: Path,
) -> dict[str, Any]:
    """Exercise the three remaining endpoints through an exact fake only."""

    if type(requester) is not ScriptedPhaseBFakeRequester:
        raise PhaseBOfflineGateError(
            "Phase-B fake runner accepts exact ScriptedPhaseBFakeRequester type only"
        )
    validate_phase_b_offline_gate(gate, require_planned_paths_absent=True)
    reservation = _reserve_fake_output(fake_output, gate=gate)
    outcomes: list[dict[str, Any]] = []
    validated: list[str] = []
    status_boot_nonce: str | None = None
    error: Exception | None = None
    try:
        facade_root = facade.load_blueprint(
            Path(str(gate["exact_surface_facade_binding"]["path"]))
        )
        context = physical.load_release(
            Path(str(facade_root["frozen_v10_validator_binding"]["release_file"]))
        )
        try:
            for request in gate["phase_b_state_machine"]["ordered_requests"]:
                name = str(request["name"])
                response = requester.fetch(
                    method="GET",
                    absolute_url=str(request["absolute_url"]),
                    headers=request["request_headers"],
                    body=None,
                )
                outcome: dict[str, Any] = {
                    "phase_b_ordinal": request["phase_b_ordinal"],
                    "full_diagnostic_ordinal": request["full_diagnostic_ordinal"],
                    "name": name,
                    "path": request["path"],
                    "absolute_url": request["absolute_url"],
                    "http_status": response.status,
                    "response_entity_body_bytes": len(response.body),
                    "response_entity_body_sha256": contract.sha256(response.body),
                    "response_entity_body_base64": base64.b64encode(
                        response.body
                    ).decode("ascii"),
                    "strict_parsed_canonical_sha256": None,
                    "validation_outcome": "STARTED",
                }
                outcomes.append(outcome)
                if response.status != 200:
                    raise PhaseBOfflineGateError(
                        f"GET {request['path']} returned HTTP {response.status}"
                    )
                try:
                    parsed, observed_nonce = (
                        facade.decode_and_validate_v10_response_bytes(
                            name, response.body, context
                        )
                    )
                except Exception:
                    outcome["validation_outcome"] = "FAILED_TERMINAL"
                    raise
                outcome["strict_parsed_canonical_sha256"] = contract.sha256(parsed)
                outcome["validation_outcome"] = "PASS"
                if name == "status":
                    status_boot_nonce = observed_nonce
                requester.acknowledge_validation(str(request["absolute_url"]))
                validated.append(name)
        except Exception as caught:
            error = caught
        result = _fake_result(
            gate=gate,
            reservation=reservation,
            requester=requester,
            endpoint_outcomes=outcomes,
            validated_names=validated,
            status_boot_nonce=status_boot_nonce,
            error=error,
        )
        reservation.finalize(result)
        return result
    finally:
        reservation.handle.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", allow_abbrev=False)
    build.add_argument("--phase-a-live-envelope", type=Path, required=True)
    build.add_argument("--phase-a-terminal-receipt", type=Path, required=True)
    build.add_argument("--facade-blueprint", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--planned-phase-b-registry", type=Path, required=True)
    build.add_argument("--planned-phase-b-terminal-receipt", type=Path, required=True)
    validate = commands.add_parser("validate", allow_abbrev=False)
    validate.add_argument("--gate", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Build or validate offline evidence; never expose fake/live execution."""

    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            root = materialize_phase_b_offline_gate(
                phase_a_live_envelope_file=args.phase_a_live_envelope,
                phase_a_terminal_receipt_file=args.phase_a_terminal_receipt,
                facade_blueprint_file=args.facade_blueprint,
                gate_blueprint_file=args.output,
                planned_phase_b_registry_file=args.planned_phase_b_registry,
                planned_phase_b_terminal_receipt_file=(
                    args.planned_phase_b_terminal_receipt
                ),
            )
            write_new_phase_b_offline_gate(args.output, root)
            artifact = args.output
        else:
            root = load_phase_b_offline_gate(args.gate)
            artifact = args.gate
        summary = validate_phase_b_offline_gate(root, require_planned_paths_absent=True)
        summary["gate_blueprint_file"] = str(
            _absolute(artifact, label="Phase-B offline gate")
        )
    except (PhaseBOfflineGateError, KeyError, TypeError, ValueError) as error:
        print(f"Phase-B offline gate error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
