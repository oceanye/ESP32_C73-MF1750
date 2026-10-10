#!/usr/bin/env python3
"""Offline-only Phase-A authority contract for one V10 ``/version`` GET.

This module implements no HTTP, socket, serial, subprocess, or live execution
surface.  It prepares and validates a non-authorizing challenge artifact for a
narrow superseding exception: the partial Stage-A receipt remains incomplete,
while one separately authorized request to the single operator-selected
literal IPv4 candidate may test only source-pinned V10 protocol-response
conformance.  Success may permit a later *request* for independent Phase-B
authority; it never proves device/IP identity, fresh boot, the active app, or
automatically issues or executes Phase B.
"""

from __future__ import annotations

import argparse
import base64
import binascii
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, BinaryIO, Final, Mapping, Sequence

from tools import mf1750_ec5_h3_c_first_stage_b_read_only_facade_contract as facade
from tools import mf1750_ec5_h3_matched_control_contract as contract


SCHEMA_VERSION: Final = 1
KIND: Final = "mf1750-ec5-h3-c-first-stage-b-phase-a-authority-v1"
CLASSIFICATION: Final = "OFFLINE_NON_AUTHORIZING_PHASE_A_CHALLENGE_NOT_LIVE_EXECUTION"
EXPECTED_BLUEPRINT_FILE_SHA256: Final = (
    "af8150cf3477515b9bd177abd5e9b6d6808e5358f79767f36d14621f6aec51ea"
)
EXPECTED_BLUEPRINT_ID: Final = (
    "eeb88d9b2b75347e40907c6b339f75bfb23c9d96fecda633f376ebc592fe63a4"
)
EXPECTED_BLUEPRINT_CANONICAL_SHA256: Final = (
    "93e11e945511ef72e460dfcf970191a1e06dc58f8c6e6a02ee0199be12701fba"
)
EXPECTED_CANDIDATE_BASE_URL: Final = "http://192.168.1.7"
EXPECTED_CANDIDATE_IPV4: Final = "192.168.1.7"
SUPERSEDED_PRIOR_OPERATOR_URL: Final = "http://192.168.1.14"
LOCATOR_SELECTION_PHRASE: Final = (
    "SELECT_UNVERIFIED_CANDIDATE_HTTP_192_168_1_7_PORT_80__"
    "SUPERSEDE_PRIOR_HTTP_192_168_1_14__NOT_IDENTITY_TRUST_OR_BOOT_PROOF"
)
PHASE_A_AUTHORIZATION_PREFIX: Final = "AUTHORIZE_STAGE_B_PHASE_A_ONE_VERSION_GET"
PHASE_A_ENDPOINTS: Final = ("version",)
PHASE_B_ENDPOINTS: Final = ("manifest", "status", "report")
PHASE_A_REGISTRY_KIND: Final = (
    "mf1750-ec5-h3-c-first-stage-b-phase-a-attempt-registry-v1"
)
PHASE_A_FAKE_RECEIPT_KIND: Final = (
    "mf1750-ec5-h3-c-first-stage-b-phase-a-fake-terminal-receipt-v1"
)
PHASE_A_FAKE_CLASSIFICATION: Final = (
    "SYNTHETIC_PHASE_A_FAKE_ONLY_NOT_LIVE_OR_DEVICE_EVIDENCE"
)
FRESH_GATE_TTL_SECONDS: Final = 600
MAX_OBSERVATION_TO_PREPARE_SECONDS: Final = 120
HEX64: Final = re.compile(r"^[0-9a-f]{64}$")


class PhaseAAuthorityError(ValueError):
    """A source binding, onsite gate, path, or authority seal differs."""


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
        raise PhaseAAuthorityError(f"{label} canonical integrity differs")
    return str(expected["canonical_sha256"])


def _is_reparse(info: os.stat_result) -> bool:
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(info, "st_file_attributes", 0) & marker)


def _safe_absolute(path: Path, *, label: str) -> Path:
    target = Path(os.path.abspath(os.fspath(path)))
    for candidate in reversed((target.parent, *target.parent.parents)):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise PhaseAAuthorityError(f"could not inspect {label}: {error}") from error
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise PhaseAAuthorityError(f"{label} parent chain contains a link/reparse")
        if not stat.S_ISDIR(info.st_mode):
            raise PhaseAAuthorityError(f"{label} parent chain is not a directory")
    if target.exists():
        try:
            info = target.lstat()
        except OSError as error:
            raise PhaseAAuthorityError(f"could not inspect {label}: {error}") from error
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise PhaseAAuthorityError(f"{label} is a link/reparse")
    return target


def _file_binding(
    path: Path, *, label: str
) -> tuple[Mapping[str, Any], bytes, dict[str, Any]]:
    try:
        resolved, payload, root = facade._read_json(path, label=label)  # noqa: SLF001
    except facade.StageBFacadeContractError as error:
        raise PhaseAAuthorityError(str(error)) from error
    return (
        root,
        payload,
        {
            "path": str(resolved),
            "bytes": len(payload),
            "sha256": contract.sha256(payload),
            "canonical_sha256": _validate_seal(root, label=label),
        },
    )


def _source_binding(path: Path, *, label: str) -> dict[str, Any]:
    try:
        return facade._file_binding(path, label=label)  # noqa: SLF001
    except facade.StageBFacadeContractError as error:
        raise PhaseAAuthorityError(str(error)) from error


def _normalize_current(value: str) -> str:
    try:
        current = Decimal(value)
    except InvalidOperation as error:
        raise PhaseAAuthorityError("current reading is not numeric") from error
    if (
        not current.is_finite()
        or current < Decimal("0")
        or current > Decimal("1.0")
        or current != current.quantize(Decimal("0.001"))
    ):
        raise PhaseAAuthorityError(
            "current reading must be finite 0.001 A precision within 0..1.000 A"
        )
    return f"{current:.3f}"


def _zoned_datetime(value: str, *, label: str) -> datetime:
    try:
        normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
        observed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise PhaseAAuthorityError(f"{label} is not ISO-8601") from error
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise PhaseAAuthorityError(f"{label} must include a UTC offset")
    return observed


def _onsite_gate(
    *,
    observed_at: str,
    prepared_at: str,
    current_reading_a: str,
    locator_selection_phrase: str,
    j2_off: bool,
    screen_clean_white: bool,
    esp32_usb_connected: bool,
    supply_3v3_cv_normal: bool,
    temperature_exact_25c: bool,
    current_limit_exact_1a: bool,
    current_and_temperature_monitors_ready: bool,
    physical_cutoff_ready: bool,
    no_reset_since_stage_a: bool,
    no_flash_since_stage_a: bool,
    no_refresh_since_stage_a: bool,
    no_rewire_since_stage_a: bool,
) -> dict[str, Any]:
    exact_bools = {
        "j2_off": j2_off,
        "screen_clean_white": screen_clean_white,
        "esp32_usb_connected": esp32_usb_connected,
        "supply_3v3_cv_normal": supply_3v3_cv_normal,
        "temperature_exact_25c": temperature_exact_25c,
        "current_limit_exact_1a": current_limit_exact_1a,
        "current_and_temperature_monitors_ready": (
            current_and_temperature_monitors_ready
        ),
        "physical_cutoff_ready": physical_cutoff_ready,
        "no_reset_since_stage_a": no_reset_since_stage_a,
        "no_flash_since_stage_a": no_flash_since_stage_a,
        "no_refresh_since_stage_a": no_refresh_since_stage_a,
        "no_rewire_since_stage_a": no_rewire_since_stage_a,
    }
    if any(
        type(value) is not bool or value is not True for value in exact_bools.values()
    ):
        raise PhaseAAuthorityError("every fresh onsite Phase-A assertion must be true")
    if locator_selection_phrase != LOCATOR_SELECTION_PHRASE:
        raise PhaseAAuthorityError(
            "fresh explicit .7 selection and .14 supersession phrase differs"
        )
    observed = _zoned_datetime(observed_at, label="onsite observed-at")
    prepared = _zoned_datetime(prepared_at, label="authority prepared-at")
    observed_utc = observed.astimezone(timezone.utc)
    prepared_utc = prepared.astimezone(timezone.utc)
    if prepared_utc < observed_utc:
        raise PhaseAAuthorityError("onsite observed-at is in the future")
    if (
        prepared_utc - observed_utc
    ).total_seconds() > MAX_OBSERVATION_TO_PREPARE_SECONDS:
        raise PhaseAAuthorityError("onsite observation is stale before preparation")
    not_after = observed_utc + timedelta(seconds=FRESH_GATE_TTL_SECONDS)
    gate = {
        "observed_at": observed_at,
        "prepared_at": prepared_at,
        "not_before_utc": prepared_utc.isoformat().replace("+00:00", "Z"),
        "not_after_utc": not_after.isoformat().replace("+00:00", "Z"),
        "fresh_ttl_seconds": FRESH_GATE_TTL_SECONDS,
        "maximum_observation_to_prepare_seconds": (MAX_OBSERVATION_TO_PREPARE_SECONDS),
        "live_consumer_must_reject_when_now_greater_than_or_equal_to_not_after": True,
        "live_consumer_must_reject_when_now_less_than_not_before": True,
        "live_consumer_time_window_rule": "not_before_utc <= now_utc < not_after_utc",
        "user_authorization_must_be_received_at_or_after_not_before": True,
        "user_authorization_must_be_received_before_not_after": True,
        "host_clock_is_staleness_guard_not_onsite_state_proof": True,
        "any_onsite_condition_change_invalidates_gate": True,
        "candidate_selection_phrase": locator_selection_phrase,
        "candidate_base_url": EXPECTED_CANDIDATE_BASE_URL,
        "superseded_prior_operator_url": SUPERSEDED_PRIOR_OPERATOR_URL,
        **exact_bools,
        "screen_state": "clean_white_initial_pair_not_treatment_finalized",
        "supply_state": "3.3V_CV_NORMAL",
        "temperature_c": "25.0",
        "current_limit_a": "1.0",
        "current_reading_a": _normalize_current(current_reading_a),
        "monitoring_state": (
            "CURRENT_LIMIT_CURRENT_MONITOR_TEMPERATURE_MONITOR_PHYSICAL_CUTOFF_READY"
        ),
        "assertions_are_operator_observations_not_firmware_proof": True,
    }
    gate["gate_canonical_sha256"] = contract.sha256(gate)
    return gate


def materialize_phase_a_authority(
    *,
    blueprint_file: Path,
    stage_a_receipt_file: Path,
    authority_file: Path,
    attempt_registry_file: Path,
    terminal_receipt_file: Path,
    observed_at: str,
    prepared_at: str,
    current_reading_a: str,
    locator_selection_phrase: str,
    j2_off: bool,
    screen_clean_white: bool,
    esp32_usb_connected: bool,
    supply_3v3_cv_normal: bool,
    temperature_exact_25c: bool,
    current_limit_exact_1a: bool,
    current_and_temperature_monitors_ready: bool,
    physical_cutoff_ready: bool,
    no_reset_since_stage_a: bool,
    no_flash_since_stage_a: bool,
    no_refresh_since_stage_a: bool,
    no_rewire_since_stage_a: bool,
    _require_attempt_paths_absent: bool = True,
) -> dict[str, Any]:
    """Build a deterministic non-authorizing Phase-A challenge offline."""

    blueprint, blueprint_payload, blueprint_binding = _file_binding(
        blueprint_file, label="Stage-B V2 blueprint"
    )
    try:
        blueprint_summary = facade.validate_blueprint(
            blueprint, require_live_output_absent=True
        )
    except facade.StageBFacadeContractError as error:
        raise PhaseAAuthorityError(
            f"V2 blueprint validation failed: {error}"
        ) from error
    if (
        blueprint_binding["sha256"] != EXPECTED_BLUEPRINT_FILE_SHA256
        or blueprint_summary["blueprint_id"] != EXPECTED_BLUEPRINT_ID
        or blueprint_summary["canonical_sha256"] != EXPECTED_BLUEPRINT_CANONICAL_SHA256
    ):
        raise PhaseAAuthorityError("frozen Stage-B V2 blueprint identity differs")

    receipt, receipt_payload, receipt_binding = _file_binding(
        stage_a_receipt_file, label="partial Stage-A receipt"
    )
    expected_partial = blueprint["stage_a_partial_receipt_binding"]
    if (
        receipt_binding["path"] != expected_partial["path"]
        or receipt_binding["bytes"] != expected_partial["bytes"]
        or receipt_binding["sha256"] != expected_partial["sha256"]
        or receipt_binding["canonical_sha256"] != expected_partial["canonical_sha256"]
        or receipt.get("classification")
        != "PARTIAL_BOOT_CONTROL_RECEIPT_NOT_STAGE_A_COMPLETE"
        or receipt["gate_outcome"]["stage_a_intent_satisfied"] is not False
    ):
        raise PhaseAAuthorityError("partial Stage-A receipt binding differs")

    authority_path = _safe_absolute(authority_file, label="Phase-A authority output")
    registry_path = _safe_absolute(
        attempt_registry_file, label="Phase-A attempt registry"
    )
    receipt_path = _safe_absolute(
        terminal_receipt_file, label="Phase-A terminal receipt"
    )
    original_final = _safe_absolute(
        Path(str(blueprint["one_shot_output_contract"]["planned_live_output"])),
        label="original plan final diagnostic output",
    )
    if len({authority_path, registry_path, receipt_path}) != 3:
        raise PhaseAAuthorityError(
            "Phase-A authority/registry/receipt paths must differ"
        )
    if original_final in {authority_path, registry_path, receipt_path}:
        raise PhaseAAuthorityError(
            "no Phase-A artifact may occupy the original plan final diagnostic output"
        )
    if _require_attempt_paths_absent:
        for label, path in (
            ("Phase-A attempt registry", registry_path),
            ("Phase-A terminal receipt", receipt_path),
        ):
            if path.exists():
                raise PhaseAAuthorityError(f"{label} already exists; attempt consumed")

    onsite = _onsite_gate(
        observed_at=observed_at,
        prepared_at=prepared_at,
        current_reading_a=current_reading_a,
        locator_selection_phrase=locator_selection_phrase,
        j2_off=j2_off,
        screen_clean_white=screen_clean_white,
        esp32_usb_connected=esp32_usb_connected,
        supply_3v3_cv_normal=supply_3v3_cv_normal,
        temperature_exact_25c=temperature_exact_25c,
        current_limit_exact_1a=current_limit_exact_1a,
        current_and_temperature_monitors_ready=current_and_temperature_monitors_ready,
        physical_cutoff_ready=physical_cutoff_ready,
        no_reset_since_stage_a=no_reset_since_stage_a,
        no_flash_since_stage_a=no_flash_since_stage_a,
        no_refresh_since_stage_a=no_refresh_since_stage_a,
        no_rewire_since_stage_a=no_rewire_since_stage_a,
    )
    version_request = deepcopy(
        blueprint["read_only_state_machine"]["ordered_requests"][0]
    )
    if (
        version_request["method"] != "GET"
        or not version_request["path"].endswith("/version")
        or version_request["absolute_url"]
        != f"{EXPECTED_CANDIDATE_BASE_URL}{version_request['path']}"
    ):
        raise PhaseAAuthorityError("Phase-A exact /version request differs")

    source_bindings = {
        "phase_a_authority_module": _source_binding(
            Path(__file__), label="Phase-A authority module"
        ),
        "v2_exact_surface_facade_module": _source_binding(
            Path(facade.__file__), label="V2 exact surface facade module"
        ),
    }
    if (
        source_bindings["v2_exact_surface_facade_module"]
        != blueprint["exact_response_surface_validation"]["source_bindings"][
            "exact_surface_validator_module"
        ]
    ):
        raise PhaseAAuthorityError("V2 exact-surface source binding differs")

    attempt_preimage = {
        "domain": "MF1750_STAGE_B_PHASE_A_VERSION_BOOTSTRAP_ATTEMPT_V1",
        "blueprint_file_sha256": contract.sha256(blueprint_payload),
        "stage_a_receipt_file_sha256": contract.sha256(receipt_payload),
        "onsite_gate_canonical_sha256": onsite["gate_canonical_sha256"],
        "candidate_base_url": EXPECTED_CANDIDATE_BASE_URL,
        "request": version_request,
        "registry": str(registry_path),
        "receipt": str(receipt_path),
        "source_sha256": source_bindings["phase_a_authority_module"]["sha256"],
    }
    attempt_id = contract.sha256(attempt_preimage)
    challenge = contract.sha256(
        {
            "domain": "MF1750_STAGE_B_PHASE_A_USER_CHALLENGE_V1",
            "attempt_id": attempt_id,
            "onsite_gate_canonical_sha256": onsite["gate_canonical_sha256"],
            "blueprint_id": blueprint["blueprint_id"],
            "stage_a_receipt_canonical_sha256": receipt_binding["canonical_sha256"],
        }
    )
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "classification": CLASSIFICATION,
        "phase": "A_VERSION_PROTOCOL_CONFORMANCE_BOOTSTRAP",
        "authority_file": str(authority_path),
        "authority_scope": {
            "stage_a_remains_incomplete": True,
            "partial_stage_a_intent_satisfied": False,
            "narrow_exception_only": True,
            "maximum_get_requests": 1,
            "maximum_post_requests": 0,
            "request_bodies": 0,
            "claims_or_mutation_requests": 0,
            "visible_refresh_requests": 0,
            "retry": False,
            "fallback": False,
            "automatic_recovery": False,
            "automatic_chaining": False,
        },
        "blueprint_binding": {
            **blueprint_binding,
            "blueprint_id": blueprint["blueprint_id"],
        },
        "partial_stage_a_receipt_binding": {
            **receipt_binding,
            "classification": receipt["classification"],
            "stage_a_intent_satisfied": False,
            "active_application_boot_proven": False,
            "stage_b_authorization_derivable_from_receipt_alone": False,
        },
        "source_bindings": source_bindings,
        "fresh_phase_a_onsite_gate": onsite,
        "candidate_origin": {
            "base_url": EXPECTED_CANDIDATE_BASE_URL,
            "literal_ipv4": EXPECTED_CANDIDATE_IPV4,
            "port": 80,
            "socket_family_required_for_future_live_runner": "AF_INET",
            "prior_operator_url_superseded_for_this_attempt": (
                SUPERSEDED_PRIOR_OPERATOR_URL
            ),
            "fresh_exact_selection_phrase": LOCATOR_SELECTION_PHRASE,
            "trusted": False,
            "identity_proven": False,
            "arp_is_identity_or_reachability_proof": False,
            "dns_allowed": False,
            "scan_allowed": False,
            "fallback_allowed": False,
            "redirect_allowed": False,
            "proxy_or_environment_routing_allowed": False,
        },
        "ordered_requests": [version_request],
        "raw_response_contract": {
            "status_must_equal": 200,
            "maximum_body_bytes": facade.MAX_JSON_BYTES,
            "maximum_status_and_header_bytes": 16_384,
            "content_encoding_allowed": False,
            "transfer_encoding_allowed": False,
            "single_content_length_required": True,
            "transfer_encoding_and_content_length_conflict_rejected": True,
            "body_bytes_meaning": (
                "HTTP_RESPONSE_ENTITY_BYTES_AFTER_HTTP_FRAMING_NOT_RAW_WIRE_BYTES"
            ),
            "strict_utf8_duplicate_nan_trailing_root_gate": True,
            "decoder_and_validator_api": "decode_and_validate_v10_response_bytes",
            "validator_stack": [
                "raw_size_and_strict_json_decoder",
                "source_pinned_exact_surface_validator",
            ],
            "validate_before_any_later_phase": True,
        },
        "future_live_transport_policy": {
            "implemented_by_this_offline_contract": False,
            "application_transport_attempts_maximum": 1,
            "connect_timeout_ms": 3_000,
            "read_timeout_ms": 5_000,
            "total_timeout_ms": 8_000,
            "literal_af_inet_ipv4_only": True,
            "dns_or_getaddrinfo_allowed": False,
            "proxy_or_environment_routing_allowed": False,
            "redirect_allowed": False,
            "network_scan_ping_or_fallback_allowed": False,
            "connection_reuse_or_keepalive_allowed": False,
            "application_retry_allowed": False,
            "exact_request_method": "GET",
            "exact_body_bytes": 0,
            "exact_headers": {
                "Host": EXPECTED_CANDIDATE_IPV4,
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Connection": "close",
            },
            "cookie_header_or_cookie_jar_allowed": False,
            "authorization_header_allowed": False,
            "request_wire_emitted_on_transport_error": "UNKNOWN",
            "peer_received_request_on_transport_error": "UNKNOWN",
            "tcp_kernel_retransmission_is_not_application_retry": True,
        },
        "attempt": {
            "attempt_id": attempt_id,
            "registry_file": str(registry_path),
            "terminal_receipt_file": str(receipt_path),
            "original_plan_final_output": str(original_final),
            "phase_a_must_not_occupy_original_plan_final_output": True,
            "future_live_reservation_order_required": [
                "O_EXCL_REGISTRY_FSYNC",
                "O_EXCL_OUTPUT_FSYNC",
            ],
            "reservation_implemented_by_this_offline_contract": False,
            "registry_creation_is_permanent_attempt_consumption": True,
            "registry_or_output_never_deleted_after_reservation": True,
            "crash_or_second_reservation_failure_is_terminal_indeterminate": True,
            "retry_allowed": False,
        },
        "authorization_challenge": {
            "phase_domain": "PHASE_A_VERSION_ONLY",
            "challenge": challenge,
            "authorization_prefix": PHASE_A_AUTHORIZATION_PREFIX,
            "authority_whole_file_sha256_must_be_bound": True,
            "authority_id_must_be_bound": True,
            "attempt_id_must_be_bound": True,
            "endpoint_set_hash": contract.sha256([version_request]),
            "copyable_authorization_token_present": False,
            "exact_authorization_grammar_not_a_token": (
                "AUTHORIZE_STAGE_B_PHASE_A_ONE_VERSION_GET"
                "__AUTHORITY_FILE_SHA256_{64_HEX_UPPER}"
                "__AUTHORITY_ID_{64_HEX_UPPER}"
                "__ATTEMPT_ID_{64_HEX_UPPER}"
                "__CHALLENGE_{64_HEX_UPPER}"
                "__ENDPOINT_SET_{64_HEX_UPPER}"
                "__UNVERIFIED_HTTP_192_168_1_7_PORT_80"
                "__NOT_DEVICE_IDENTITY_TRUST_OR_BOOT_PROOF"
                "__GET_1_POST_0_BODY_0"
                "__CLAIM_0_MUTATION_REQUEST_0_VISIBLE_REFRESH_REQUEST_0"
                "__NO_RETRY_NO_FALLBACK_NO_RECOVERY_NO_AUTOCHAIN"
            ),
            "placeholder_grammar_is_not_copyable_user_authorization": True,
            "future_runner_must_require_byte_exact_case_exact_complete_phrase": True,
            "separate_exact_user_authorization_required": True,
            "phase_b_token_issued": False,
            "phase_a_and_phase_b_tokens_interchangeable": False,
        },
        "phase_a_success_boundary": {
            "success_classification": "V10_PROTOCOL_RESPONSE_CONFORMANCE",
            "responder_or_device_identity_proven": False,
            "trusted_ip_binding_proven": False,
            "fresh_post_reset_application_boot_proven": False,
            "active_application_or_ota_slot_proven": False,
            "may_only_unlock_request_for_phase_b_authority": True,
            "phase_b_authority_automatically_generated": False,
            "phase_b_automatically_executed": False,
        },
        "future_terminal_receipt_evidence": {
            "attempt_checkpoint_before_connect_required": True,
            "http_status_required_if_response_received": True,
            "response_entity_body_length_and_sha256_required": True,
            "lossless_base64_response_entity_body_required": True,
            "strict_parsed_canonical_sha256_required": True,
            "validator_stack_and_outcome_required": True,
            "request_wire_emitted_may_be_unknown": True,
            "peer_received_request_must_remain_unknown": True,
            "must_not_describe_response_entity_bytes_as_raw_wire_bytes": True,
            "device_api_claim_requests": 0,
            "client_mutation_or_refresh_requests": 0,
            "actual_device_or_background_side_effects": (
                "UNKNOWN_NOT_OBSERVED_BY_READ_ONLY_CLIENT"
            ),
        },
        "future_phase_b_gate": {
            "implemented_by_this_phase_a_contract": False,
            "requires_sealed_phase_a_terminal_success_receipt": True,
            "requires_phase_a_receipt_whole_file_and_canonical_sha256": True,
            "requires_phase_a_version_raw_body_sha256": True,
            "requires_lossless_base64_phase_a_version_raw_body": True,
            "phase_b_loader_must_replay_phase_a_raw_body_through_exact_decoder": True,
            "phase_b_must_not_trust_phase_a_state_or_seal_without_raw_replay": True,
            "requires_phase_a_registry_whole_file_sha256": True,
            "requires_same_literal_candidate_origin": EXPECTED_CANDIDATE_BASE_URL,
            "requires_new_fresh_onsite_gate_after_phase_a": True,
            "requires_new_distinct_phase_b_user_authorization": True,
            "phase_b_endpoints_exactly": list(PHASE_B_ENDPOINTS),
            "phase_b_repeats_version": False,
            "phase_b_registry_must_be_distinct": True,
            "phase_b_may_occupy_original_plan_final_output_only_after_authorization": True,
            "phase_a_registry_alone_is_not_phase_a_success": True,
            "synthetic_fake_phase_a_receipt_is_never_phase_b_eligible": True,
            "required_live_phase_a_receipt_kind_is_not_implemented_yet": True,
        },
        "implementation_surface": {
            "offline_build_validate_only": True,
            "injected_exact_type_raw_fake_facade_present": True,
            "fake_facade_is_not_a_live_transport": True,
            "live_http_transport_implemented": False,
            "live_execute_cli_present": False,
            "hardware_com_or_device_network_accessed": False,
            "execution_ready": False,
            "live_authorized": False,
        },
        "unsatisfied_live_gates": [
            "reviewed_hash_frozen_live_phase_a_runner",
            "separate_exact_phase_a_user_authorization_after_challenge_review",
            "unexpired_fresh_onsite_gate_at_live_consumption",
            "o_excl_registry_then_output_reservation",
            "one_raw_version_get_terminal_receipt",
        ],
    }
    unsigned["authority_id"] = contract.sha256(unsigned)
    return _seal(unsigned)


def validate_phase_a_authority(
    root: Mapping[str, Any], *, require_attempt_paths_absent: bool = True
) -> dict[str, Any]:
    canonical = _validate_seal(root, label="Phase-A authority")
    if (
        root.get("schema_version") != SCHEMA_VERSION
        or root.get("kind") != KIND
        or root.get("classification") != CLASSIFICATION
    ):
        raise PhaseAAuthorityError("Phase-A authority schema/kind differs")
    blueprint = root["blueprint_binding"]
    receipt = root["partial_stage_a_receipt_binding"]
    gate = root["fresh_phase_a_onsite_gate"]
    attempt = root["attempt"]
    rebuilt = materialize_phase_a_authority(
        blueprint_file=Path(str(blueprint["path"])),
        stage_a_receipt_file=Path(str(receipt["path"])),
        authority_file=Path(str(root["authority_file"])),
        attempt_registry_file=Path(str(attempt["registry_file"])),
        terminal_receipt_file=Path(str(attempt["terminal_receipt_file"])),
        observed_at=str(gate["observed_at"]),
        prepared_at=str(gate["prepared_at"]),
        current_reading_a=str(gate["current_reading_a"]),
        locator_selection_phrase=str(gate["candidate_selection_phrase"]),
        j2_off=gate["j2_off"],
        screen_clean_white=gate["screen_clean_white"],
        esp32_usb_connected=gate["esp32_usb_connected"],
        supply_3v3_cv_normal=gate["supply_3v3_cv_normal"],
        temperature_exact_25c=gate["temperature_exact_25c"],
        current_limit_exact_1a=gate["current_limit_exact_1a"],
        current_and_temperature_monitors_ready=gate[
            "current_and_temperature_monitors_ready"
        ],
        physical_cutoff_ready=gate["physical_cutoff_ready"],
        no_reset_since_stage_a=gate["no_reset_since_stage_a"],
        no_flash_since_stage_a=gate["no_flash_since_stage_a"],
        no_refresh_since_stage_a=gate["no_refresh_since_stage_a"],
        no_rewire_since_stage_a=gate["no_rewire_since_stage_a"],
        _require_attempt_paths_absent=require_attempt_paths_absent,
    )
    if contract.canonical_json_bytes(root) != contract.canonical_json_bytes(rebuilt):
        raise PhaseAAuthorityError(
            "Phase-A authority differs from deterministic reconstruction"
        )
    expected_id = contract.sha256(
        {
            key: value
            for key, value in root.items()
            if key not in {"authority_id", "integrity"}
        }
    )
    if root.get("authority_id") != expected_id:
        raise PhaseAAuthorityError("Phase-A authority ID differs")
    return {
        "valid": True,
        "authority_id": root["authority_id"],
        "canonical_sha256": canonical,
        "classification": CLASSIFICATION,
        "phase": root["phase"],
        "candidate_base_url": EXPECTED_CANDIDATE_BASE_URL,
        "stage_a_intent_satisfied": False,
        "copyable_authorization_token_present": False,
        "phase_b_token_issued": False,
        "execution_ready": False,
        "live_authorized": False,
        "device_io_performed": False,
    }


def write_new_phase_a_authority(path: Path, root: Mapping[str, Any]) -> None:
    validate_phase_a_authority(root, require_attempt_paths_absent=True)
    target = _safe_absolute(path, label="Phase-A authority output")
    if target != Path(str(root["authority_file"])):
        raise PhaseAAuthorityError("Phase-A authority self-path differs")
    target.parent.mkdir(parents=True, exist_ok=True)
    target = _safe_absolute(target, label="Phase-A authority output")
    try:
        with target.open("xb") as handle:
            handle.write(contract.canonical_json_bytes(root) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise PhaseAAuthorityError("Phase-A authority output already exists") from error
    except OSError as error:
        raise PhaseAAuthorityError(
            f"could not write Phase-A authority output: {error}"
        ) from error


def load_phase_a_authority(path: Path) -> Mapping[str, Any]:
    try:
        _, _, root = facade._read_json(path, label="Phase-A authority")  # noqa: SLF001
    except facade.StageBFacadeContractError as error:
        raise PhaseAAuthorityError(str(error)) from error
    return root


def _authorization_phrase(
    authority: Mapping[str, Any], *, authority_file_sha256: str
) -> str:
    if HEX64.fullmatch(authority_file_sha256) is None:
        raise PhaseAAuthorityError("Phase-A authority whole-file SHA-256 is invalid")
    challenge = authority["authorization_challenge"]
    return (
        f"{PHASE_A_AUTHORIZATION_PREFIX}"
        f"__AUTHORITY_FILE_SHA256_{authority_file_sha256.upper()}"
        f"__AUTHORITY_ID_{str(authority['authority_id']).upper()}"
        f"__ATTEMPT_ID_{str(authority['attempt']['attempt_id']).upper()}"
        f"__CHALLENGE_{str(challenge['challenge']).upper()}"
        f"__ENDPOINT_SET_{str(challenge['endpoint_set_hash']).upper()}"
        "__UNVERIFIED_HTTP_192_168_1_7_PORT_80"
        "__NOT_DEVICE_IDENTITY_TRUST_OR_BOOT_PROOF"
        "__GET_1_POST_0_BODY_0"
        "__CLAIM_0_MUTATION_REQUEST_0_VISIBLE_REFRESH_REQUEST_0"
        "__NO_RETRY_NO_FALLBACK_NO_RECOVERY_NO_AUTOCHAIN"
    )


def required_phase_a_authorization(authority_file: Path) -> str:
    """Derive the exact phrase only after a complete authority file exists.

    This offline API does not authorize or execute anything and is deliberately
    absent from the CLI.  The returned phrase still requires a later, separate,
    byte-exact user response while the onsite gate remains unexpired.
    """

    try:
        _, payload, root = facade._read_json(  # noqa: SLF001
            authority_file, label="Phase-A authority"
        )
    except facade.StageBFacadeContractError as error:
        raise PhaseAAuthorityError(str(error)) from error
    validate_phase_a_authority(root, require_attempt_paths_absent=True)
    return _authorization_phrase(root, authority_file_sha256=contract.sha256(payload))


@dataclass(frozen=True)
class ScriptedPhaseAFakeResponse:
    """A raw entity response for the exact injected fake requester only."""

    status: int
    headers: tuple[tuple[str, str], ...]
    entity_body: bytes


class ScriptedPhaseAFakeRequester:
    """One-call raw fake with no socket, URL opener, or live capability."""

    def __init__(
        self,
        *,
        expected_absolute_url: str,
        response: ScriptedPhaseAFakeResponse | None = None,
        transport_error: str | None = None,
    ) -> None:
        if type(expected_absolute_url) is not str:
            raise PhaseAAuthorityError("fake expected URL type differs")
        if (response is None) == (transport_error is None):
            raise PhaseAAuthorityError(
                "fake requires exactly one response or transport error"
            )
        if response is not None:
            if (
                type(response) is not ScriptedPhaseAFakeResponse
                or type(response.status) is not int
                or type(response.headers) is not tuple
                or type(response.entity_body) is not bytes
                or any(
                    type(item) is not tuple
                    or len(item) != 2
                    or type(item[0]) is not str
                    or type(item[1]) is not str
                    for item in response.headers
                )
            ):
                raise PhaseAAuthorityError("fake response type differs")
        if transport_error is not None and type(transport_error) is not str:
            raise PhaseAAuthorityError("fake transport error type differs")
        self.expected_absolute_url = expected_absolute_url
        self.response = response
        self.transport_error = transport_error
        self.calls: list[dict[str, Any]] = []
        self.validation_acknowledged = False

    def fetch(
        self,
        *,
        method: str,
        absolute_url: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> ScriptedPhaseAFakeResponse:
        if self.calls:
            raise PhaseAAuthorityError("Phase-A fake exceeded its one-call budget")
        if (
            method != "GET"
            or absolute_url != self.expected_absolute_url
            or dict(headers)
            != {
                "Host": EXPECTED_CANDIDATE_IPV4,
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Connection": "close",
            }
            or body is not None
        ):
            raise PhaseAAuthorityError("Phase-A fake request surface differs")
        self.calls.append(
            {
                "ordinal": 1,
                "method": method,
                "absolute_url": absolute_url,
                "headers": dict(headers),
                "body": None,
                "attempt_recorded_before_fetch": True,
            }
        )
        if self.transport_error is not None:
            raise PhaseAAuthorityError(
                f"scripted fake transport error: {self.transport_error}"
            )
        if self.response is None:  # constructor makes this unreachable
            raise PhaseAAuthorityError("fake response is absent")
        return self.response

    def acknowledge_validation(self) -> None:
        if len(self.calls) != 1 or self.validation_acknowledged:
            raise PhaseAAuthorityError("fake validation acknowledgement differs")
        self.validation_acknowledged = True


class _EvidenceSink:
    def __init__(
        self,
        *,
        path: Path,
        handle: BinaryIO,
        identity: tuple[int, int],
        label: str,
    ) -> None:
        self.path = path
        self.handle = handle
        self.identity = identity
        self.label = label
        self.parent_directory_fsync_status = "NOT_ATTEMPTED"

    def assert_identity(self) -> None:
        _safe_absolute(self.path, label=self.label)
        try:
            path_info = self.path.lstat()
            held_info = os.fstat(self.handle.fileno())
        except OSError as error:
            raise PhaseAAuthorityError(
                f"{self.label} identity could not be verified: {error}"
            ) from error
        if (
            stat.S_ISLNK(path_info.st_mode)
            or _is_reparse(path_info)
            or not stat.S_ISREG(path_info.st_mode)
            or not stat.S_ISREG(held_info.st_mode)
            or path_info.st_nlink != 1
            or held_info.st_nlink != 1
            or (path_info.st_dev, path_info.st_ino) != self.identity
            or (held_info.st_dev, held_info.st_ino) != self.identity
        ):
            raise PhaseAAuthorityError(f"{self.label} identity changed")

    def replace(self, value: Mapping[str, Any]) -> str:
        payload = contract.canonical_json_bytes(value) + b"\n"
        self.assert_identity()
        try:
            self.handle.seek(0)
            self.handle.truncate(0)
            self.handle.write(payload)
            self.handle.flush()
            os.fsync(self.handle.fileno())
        except OSError as error:
            raise PhaseAAuthorityError(
                f"could not persist {self.label}: {error}"
            ) from error
        self.assert_identity()
        if os.fstat(self.handle.fileno()).st_size != len(payload):
            raise PhaseAAuthorityError(f"{self.label} durable length differs")
        return contract.sha256(payload)

    def whole_file_sha256(self) -> str:
        self.assert_identity()
        try:
            self.handle.seek(0)
            payload = self.handle.read()
        except OSError as error:
            raise PhaseAAuthorityError(
                f"could not read held {self.label}: {error}"
            ) from error
        return contract.sha256(payload)

    def close(self) -> None:
        self.handle.close()


def _fsync_parent_directory(path: Path) -> str:
    """Attempt a directory fsync without claiming power-loss durability."""

    try:
        descriptor = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return "UNAVAILABLE_ON_THIS_PLATFORM_NOT_POWER_LOSS_DURABILITY_PROOF"
    try:
        os.fsync(descriptor)
    except OSError:
        return "ATTEMPTED_FAILED_NOT_POWER_LOSS_DURABILITY_PROOF"
    finally:
        os.close(descriptor)
    return "ATTEMPTED_SUCCESS_NOT_POWER_LOSS_DURABILITY_PROOF"


def _reserve_sink(
    path: Path, *, label: str, initial: Mapping[str, Any]
) -> _EvidenceSink:
    target = _safe_absolute(path, label=label)
    target.parent.mkdir(parents=True, exist_ok=True)
    target = _safe_absolute(target, label=label)
    try:
        handle = target.open("xb+", buffering=0)
        created = os.fstat(handle.fileno())
    except FileExistsError as error:
        raise PhaseAAuthorityError(f"{label} already exists; no retry") from error
    except OSError as error:
        raise PhaseAAuthorityError(f"could not reserve {label}: {error}") from error
    sink = _EvidenceSink(
        path=target,
        handle=handle,
        identity=(created.st_dev, created.st_ino),
        label=label,
    )
    try:
        sink.replace(initial)
        sink.parent_directory_fsync_status = _fsync_parent_directory(target)
    except BaseException:
        sink.close()
        raise
    return sink


def _bounded_fake_header_evidence(
    response: ScriptedPhaseAFakeResponse,
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    try:
        status_line = f"HTTP/1.1 {response.status}\r\n".encode("ascii")
    except UnicodeEncodeError as error:  # status is exact int, defensive only
        raise PhaseAAuthorityError("fake HTTP status line is not ASCII") from error
    encoded_parts = [status_line]
    lowered: dict[str, list[str]] = {}
    normalized: list[list[str]] = []
    for name, value in response.headers:
        if not name or "\r" in name or "\n" in name or "\r" in value or "\n" in value:
            raise PhaseAAuthorityError("fake response header syntax differs")
        try:
            encoded = f"{name}: {value}\r\n".encode("ascii")
        except UnicodeEncodeError as error:
            raise PhaseAAuthorityError("fake response headers are not ASCII") from error
        encoded_parts.append(encoded)
        lowered.setdefault(name.lower(), []).append(value)
        normalized.append([name, value])
    encoded_parts.append(b"\r\n")
    status_and_headers = b"".join(encoded_parts)
    if len(status_and_headers) > 16_384:
        raise PhaseAAuthorityError(
            "fake response status and headers exceed the exact ASCII byte budget"
        )
    return lowered, {
        "response_header_count": len(response.headers),
        "synthetic_canonical_status_and_header_ascii_bytes": len(status_and_headers),
        "synthetic_canonical_status_and_header_sha256": contract.sha256(
            status_and_headers
        ),
        "synthetic_header_representation_is_not_observed_raw_wire_bytes": True,
        "response_headers_bounded": normalized,
    }


def _validate_fake_http_envelope(
    response: ScriptedPhaseAFakeResponse, lowered: Mapping[str, list[str]]
) -> None:
    if response.status != 200:
        raise PhaseAAuthorityError(f"Phase-A GET returned HTTP {response.status}")
    if "content-encoding" in lowered:
        raise PhaseAAuthorityError("content encoding is forbidden")
    if "transfer-encoding" in lowered:
        raise PhaseAAuthorityError("transfer encoding is forbidden")
    lengths = lowered.get("content-length", [])
    if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
        raise PhaseAAuthorityError("one exact Content-Length is required")
    if int(lengths[0]) != len(response.entity_body):
        raise PhaseAAuthorityError("Content-Length differs from entity body length")
    content_types = lowered.get("content-type", [])
    if len(content_types) != 1 or content_types[0].split(";", 1)[0].strip().lower() != (
        "application/json"
    ):
        raise PhaseAAuthorityError("one application/json Content-Type is required")


def _time_gate(authority: Mapping[str, Any], *, now: str) -> str:
    gate = authority["fresh_phase_a_onsite_gate"]
    observed_now = _zoned_datetime(now, label="Phase-A fake now").astimezone(
        timezone.utc
    )
    not_before = _zoned_datetime(
        str(gate["not_before_utc"]), label="Phase-A not-before"
    ).astimezone(timezone.utc)
    not_after = _zoned_datetime(
        str(gate["not_after_utc"]), label="Phase-A not-after"
    ).astimezone(timezone.utc)
    if observed_now < not_before or observed_now >= not_after:
        raise PhaseAAuthorityError("Phase-A fresh onsite gate is not currently valid")
    return observed_now.isoformat().replace("+00:00", "Z")


def _phase_a_fake_receipt(
    *,
    authority: Mapping[str, Any],
    authority_file_binding: Mapping[str, Any],
    registry_path: Path,
    registry_initial_canonical: str,
    registry_whole_file_sha256: str,
    registry_parent_directory_fsync_status: str,
    output_parent_directory_fsync_status: str,
    authorization_sha256: str,
    now_utc: str,
    requester: ScriptedPhaseAFakeRequester,
    endpoint_outcome: Mapping[str, Any],
    success: bool,
    error: BaseException | None,
) -> dict[str, Any]:
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": PHASE_A_FAKE_RECEIPT_KIND,
        "classification": PHASE_A_FAKE_CLASSIFICATION,
        "state": (
            "TERMINAL_SUCCESS_FAKE_ONLY"
            if success
            else "TERMINAL_FAILURE_FAKE_ONLY_NO_RETRY"
        ),
        "authority_binding": dict(authority_file_binding),
        "authority_id": authority["authority_id"],
        "attempt_id": authority["attempt"]["attempt_id"],
        "authorization_phrase_sha256": authorization_sha256,
        "authorization_phrase_stored": False,
        "onsite_gate_canonical_sha256": authority["fresh_phase_a_onsite_gate"][
            "gate_canonical_sha256"
        ],
        "fake_evaluation_now_utc": now_utc,
        "attempt_registry_file": str(registry_path),
        "registry_initial_canonical_sha256": registry_initial_canonical,
        "registry_whole_file_sha256": registry_whole_file_sha256,
        "registry_is_immutable_o_excl_marker": True,
        "registry_parent_directory_fsync_status": (
            registry_parent_directory_fsync_status
        ),
        "output_parent_directory_fsync_status": output_parent_directory_fsync_status,
        "file_and_directory_fsync_are_not_power_loss_durability_proof": True,
        "endpoint_outcomes": [deepcopy(dict(endpoint_outcome))],
        "fake_fetch_calls": len(requester.calls),
        "fake_validation_acknowledged": requester.validation_acknowledged,
        "maximum_get_requests": 1,
        "post_requests": 0,
        "request_bodies": 0,
        "device_api_claim_requests": 0,
        "client_mutation_requests": 0,
        "client_visible_refresh_requests": 0,
        "network_requests": 0,
        "serial_or_com_accesses": 0,
        "hardware_accessed": False,
        "device_io_performed": False,
        "retry_allowed": False,
        "automatic_recovery": False,
        "automatic_chaining": False,
        "phase_b_authority_generated": False,
        "phase_b_authorization_generated": False,
        "phase_b_requests": 0,
        "eligible_for_live_phase_b_authority": False,
        "phase_b_ineligibility_reason": (
            "SYNTHETIC_FAKE_RECEIPT_NEVER_ELIGIBLE_FOR_LIVE_PHASE_B"
        ),
        "original_plan_final_output_touched": False,
        "version_protocol_response_conformance": success,
        "responder_or_device_identity_proven": False,
        "trusted_ip_binding_proven": False,
        "fresh_post_reset_application_boot_proven": False,
        "active_application_or_ota_slot_proven": False,
        "actual_device_or_background_side_effects": (
            "NOT_APPLICABLE_SCRIPTED_FAKE_ONLY"
        ),
    }
    if error is None:
        unsigned.update({"error_type": None, "error": None})
    else:
        unsigned.update({"error_type": type(error).__name__, "error": str(error)})
    return _seal(unsigned)


def _registry_initial_record(
    *,
    authority: Mapping[str, Any],
    authority_file_binding: Mapping[str, Any],
    authorization_sha256: str,
    output_path: Path,
) -> dict[str, Any]:
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": PHASE_A_REGISTRY_KIND,
            "classification": PHASE_A_FAKE_CLASSIFICATION,
            "state": "PERMANENTLY_CONSUMED_BEFORE_OUTPUT_OR_FAKE_FETCH",
            "authority_binding": dict(authority_file_binding),
            "authority_id": authority["authority_id"],
            "attempt_id": authority["attempt"]["attempt_id"],
            "authorization_phrase_sha256": authorization_sha256,
            "terminal_receipt_file": str(output_path),
            "registry_created_before_output": True,
            "registry_created_before_fake_fetch": True,
            "immutable_after_initial_o_excl_write": True,
            "outcome_is_recorded_only_in_terminal_receipt": True,
            "parent_directory_fsync_attempt_required_after_create": True,
            "file_and_directory_fsync_are_not_power_loss_durability_proof": True,
            "registry_or_output_never_deleted": True,
            "retry_allowed": False,
            "network_requests": 0,
            "device_io_performed": False,
        }
    )


def run_phase_a_scripted_fake_only(
    authority_file: Path,
    *,
    authorization: str,
    now: str,
    requester: ScriptedPhaseAFakeRequester,
) -> dict[str, Any]:
    """Exercise Phase-A reservation and raw validation through an exact fake."""

    if type(requester) is not ScriptedPhaseAFakeRequester:
        raise PhaseAAuthorityError(
            "Phase-A fake runner accepts the exact scripted fake type only"
        )
    try:
        authority_path, authority_payload, authority = facade._read_json(  # noqa: SLF001
            authority_file, label="Phase-A authority"
        )
    except facade.StageBFacadeContractError as error:
        raise PhaseAAuthorityError(str(error)) from error
    validate_phase_a_authority(authority, require_attempt_paths_absent=False)
    authority_file_sha256 = contract.sha256(authority_payload)
    required = _authorization_phrase(
        authority, authority_file_sha256=authority_file_sha256
    )
    if type(authorization) is not str or authorization != required:
        raise PhaseAAuthorityError("exact Phase-A user authorization differs")
    now_utc = _time_gate(authority, now=now)
    attempt = authority["attempt"]
    registry_path = _safe_absolute(
        Path(str(attempt["registry_file"])), label="Phase-A attempt registry"
    )
    output_path = _safe_absolute(
        Path(str(attempt["terminal_receipt_file"])),
        label="Phase-A terminal receipt",
    )
    if not registry_path.name.endswith(
        ".fake-only.json"
    ) or not output_path.name.endswith(".fake-only.json"):
        raise PhaseAAuthorityError(
            "scripted fake registry and receipt must end with '.fake-only.json'"
        )
    if registry_path.exists():
        raise PhaseAAuthorityError("Phase-A registry exists; no retry")
    if output_path.exists():
        raise PhaseAAuthorityError(
            "Phase-A output exists before registry; attempt must not start"
        )

    # All source/release reconstruction (which may invoke local binary-audit
    # tooling inside the frozen release loader) is completed before O_EXCL and
    # before the fake fetch.  After reservation, validation is pure in-memory.
    blueprint = facade.load_blueprint(Path(str(authority["blueprint_binding"]["path"])))
    v10_context = facade._load_frozen_v10_release(  # noqa: SLF001
        Path(str(blueprint["frozen_v10_validator_binding"]["release_file"]))
    )

    authority_file_binding = {
        "path": str(authority_path),
        "bytes": len(authority_payload),
        "sha256": authority_file_sha256,
        "canonical_sha256": authority["integrity"]["canonical_sha256"],
    }
    authorization_sha256 = contract.sha256(authorization.encode("ascii"))
    registry_initial = _registry_initial_record(
        authority=authority,
        authority_file_binding=authority_file_binding,
        authorization_sha256=authorization_sha256,
        output_path=output_path,
    )
    registry = _reserve_sink(
        registry_path,
        label="Phase-A attempt registry",
        initial=registry_initial,
    )
    output: _EvidenceSink | None = None
    try:
        output_initial = _seal(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": PHASE_A_FAKE_RECEIPT_KIND,
                "classification": PHASE_A_FAKE_CLASSIFICATION,
                "state": "TERMINAL_INDETERMINATE_RESERVED_NO_RETRY",
                "authority_binding": authority_file_binding,
                "authority_id": authority["authority_id"],
                "attempt_id": attempt["attempt_id"],
                "registry_file": str(registry_path),
                "output_reserved_before_fake_fetch": True,
                "retry_allowed": False,
                "network_requests": 0,
                "device_io_performed": False,
            }
        )
        try:
            output = _reserve_sink(
                output_path,
                label="Phase-A terminal receipt",
                initial=output_initial,
            )
        except BaseException:
            # The immutable registry is itself the permanent consumption
            # marker.  Never truncate/rewrite/delete it, including when the
            # second O_EXCL reservation fails or the process is interrupted.
            raise

        registry.assert_identity()
        output.assert_identity()
        now_utc = _time_gate(authority, now=now)
        request = authority["ordered_requests"][0]
        endpoint: dict[str, Any] = {
            "ordinal": 1,
            "name": "version",
            "method": "GET",
            "path": request["path"],
            "absolute_url": request["absolute_url"],
            "attempt_checkpoint_before_fake_fetch": True,
            "last_completed_gate": "ATTEMPT_RECORDED",
            "failure_stage": None,
            "response_received": False,
            "http_status": None,
            "response_header_count": None,
            "synthetic_canonical_status_and_header_ascii_bytes": None,
            "synthetic_canonical_status_and_header_sha256": None,
            "synthetic_header_representation_is_not_observed_raw_wire_bytes": True,
            "response_headers_bounded": None,
            "response_entity_body_bytes": None,
            "response_entity_body_sha256": None,
            "response_entity_body_base64": None,
            "strict_parsed_canonical_sha256": None,
            "validation_stack": [
                "raw_size_and_strict_json_decoder",
                "source_pinned_exact_surface_validator",
            ],
            "validation_outcome": "STARTED",
            "request_wire_emitted": "NOT_APPLICABLE_SCRIPTED_FAKE_ONLY",
            "peer_received_request": "NOT_APPLICABLE_SCRIPTED_FAKE_ONLY",
        }
        error: BaseException | None = None
        success = False
        try:
            response = requester.fetch(
                method="GET",
                absolute_url=str(request["absolute_url"]),
                headers=authority["future_live_transport_policy"]["exact_headers"],
                body=None,
            )
            endpoint["response_received"] = True
            endpoint["http_status"] = response.status
            endpoint["response_entity_body_bytes"] = len(response.entity_body)
            endpoint["last_completed_gate"] = "RESPONSE_RECEIVED"
            if (
                len(response.entity_body) <= 0
                or len(response.entity_body) > facade.MAX_JSON_BYTES
            ):
                raise PhaseAAuthorityError("response entity body size is invalid")
            endpoint["last_completed_gate"] = "BODY_SIZE_OK"
            lowered, header_evidence = _bounded_fake_header_evidence(response)
            endpoint.update(header_evidence)
            endpoint["last_completed_gate"] = "SYNTHETIC_HEADERS_BOUNDED"
            endpoint["response_entity_body_sha256"] = contract.sha256(
                response.entity_body
            )
            endpoint["response_entity_body_base64"] = base64.b64encode(
                response.entity_body
            ).decode("ascii")
            _validate_fake_http_envelope(response, lowered)
            endpoint["last_completed_gate"] = "HTTP_ENVELOPE_OK"
            parsed, _ = facade.decode_and_validate_v10_response_bytes(
                "version", response.entity_body, v10_context
            )
            endpoint["strict_parsed_canonical_sha256"] = contract.sha256(parsed)
            endpoint["validation_outcome"] = "PASS"
            endpoint["last_completed_gate"] = "EXACT_V10_VALIDATED"
            requester.acknowledge_validation()
            success = True
        except BaseException as caught:
            endpoint["validation_outcome"] = "FAILED_TERMINAL_NO_RETRY"
            endpoint["failure_stage"] = {
                "ATTEMPT_RECORDED": "TRANSPORT_FETCH",
                "RESPONSE_RECEIVED": "BODY_SIZE_GATE",
                "BODY_SIZE_OK": "SYNTHETIC_HEADER_GATE",
                "SYNTHETIC_HEADERS_BOUNDED": "HTTP_ENVELOPE_GATE",
                "HTTP_ENVELOPE_OK": "STRICT_JSON_OR_EXACT_V10_GATE",
            }[endpoint["last_completed_gate"]]
            error = caught
        receipt = _phase_a_fake_receipt(
            authority=authority,
            authority_file_binding=authority_file_binding,
            registry_path=registry_path,
            registry_initial_canonical=registry_initial["integrity"][
                "canonical_sha256"
            ],
            registry_whole_file_sha256=registry.whole_file_sha256(),
            registry_parent_directory_fsync_status=(
                registry.parent_directory_fsync_status
            ),
            output_parent_directory_fsync_status=output.parent_directory_fsync_status,
            authorization_sha256=authorization_sha256,
            now_utc=now_utc,
            requester=requester,
            endpoint_outcome=endpoint,
            success=success,
            error=error,
        )
        output.replace(receipt)
        validation_summary = validate_phase_a_fake_terminal_receipt(
            output_path,
            authority_file=authority_path,
            require_success=success,
            _authority_bundle=(
                authority,
                authority_payload,
                authority_file_binding,
            ),
            _v10_context=v10_context,
        )
        if validation_summary["terminal_success"] is not success:
            raise PhaseAAuthorityError(
                "persisted Phase-A fake receipt terminal state differs"
            )
        if error is not None and not isinstance(error, Exception):
            raise error
        return receipt
    finally:
        if output is not None:
            output.close()
        registry.close()


def _load_authority_file(
    authority_file: Path,
) -> tuple[Mapping[str, Any], bytes, dict[str, Any]]:
    try:
        resolved, payload, authority = facade._read_json(  # noqa: SLF001
            authority_file, label="Phase-A authority"
        )
    except facade.StageBFacadeContractError as error:
        raise PhaseAAuthorityError(str(error)) from error
    validate_phase_a_authority(authority, require_attempt_paths_absent=False)
    return (
        authority,
        payload,
        {
            "path": str(resolved),
            "bytes": len(payload),
            "sha256": contract.sha256(payload),
            "canonical_sha256": authority["integrity"]["canonical_sha256"],
        },
    )


def validate_phase_a_attempt_registry(
    registry_file: Path,
    *,
    authority_file: Path,
    _authority_bundle: tuple[Mapping[str, Any], bytes, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Strictly validate the immutable O_EXCL fake attempt marker."""

    authority, authority_payload, authority_binding = (
        _load_authority_file(authority_file)
        if _authority_bundle is None
        else _authority_bundle
    )
    expected_registry = Path(str(authority["attempt"]["registry_file"]))
    target = _safe_absolute(registry_file, label="Phase-A attempt registry")
    if target != expected_registry:
        raise PhaseAAuthorityError("Phase-A registry path differs from authority")
    try:
        resolved, payload, root = facade._read_json(  # noqa: SLF001
            target, label="Phase-A attempt registry"
        )
    except facade.StageBFacadeContractError as error:
        raise PhaseAAuthorityError(str(error)) from error
    authorization = _authorization_phrase(
        authority, authority_file_sha256=contract.sha256(authority_payload)
    )
    expected = _registry_initial_record(
        authority=authority,
        authority_file_binding=authority_binding,
        authorization_sha256=contract.sha256(authorization.encode("ascii")),
        output_path=Path(str(authority["attempt"]["terminal_receipt_file"])),
    )
    try:
        facade._require_exact_value(  # noqa: SLF001
            root, expected, label="Phase-A immutable registry"
        )
    except facade.StageBFacadeContractError as error:
        raise PhaseAAuthorityError(str(error)) from error
    info = resolved.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or _is_reparse(info):
        raise PhaseAAuthorityError("Phase-A registry is not a unique regular file")
    return {
        "valid": True,
        "kind": PHASE_A_REGISTRY_KIND,
        "state": root["state"],
        "attempt_id": root["attempt_id"],
        "path": str(resolved),
        "bytes": len(payload),
        "sha256": contract.sha256(payload),
        "canonical_sha256": root["integrity"]["canonical_sha256"],
        "immutable_permanent_consumption_marker": True,
        "retry_allowed": False,
    }


def validate_phase_a_fake_terminal_receipt(
    receipt_file: Path,
    *,
    authority_file: Path,
    require_success: bool = False,
    _authority_bundle: tuple[Mapping[str, Any], bytes, dict[str, Any]] | None = None,
    _v10_context: Any | None = None,
) -> dict[str, Any]:
    """Strictly load, bind, and replay a synthetic Phase-A receipt."""

    authority, authority_payload, authority_binding = (
        _load_authority_file(authority_file)
        if _authority_bundle is None
        else _authority_bundle
    )
    expected_receipt = Path(str(authority["attempt"]["terminal_receipt_file"]))
    target = _safe_absolute(receipt_file, label="Phase-A fake terminal receipt")
    if target != expected_receipt:
        raise PhaseAAuthorityError("Phase-A receipt path differs from authority")
    registry_summary = validate_phase_a_attempt_registry(
        Path(str(authority["attempt"]["registry_file"])),
        authority_file=authority_file,
        _authority_bundle=(authority, authority_payload, authority_binding),
    )
    try:
        resolved, payload, root = facade._read_json(  # noqa: SLF001
            target, label="Phase-A fake terminal receipt"
        )
    except facade.StageBFacadeContractError as error:
        raise PhaseAAuthorityError(str(error)) from error
    _validate_seal(root, label="Phase-A fake terminal receipt")
    root_keys = {
        "schema_version",
        "kind",
        "classification",
        "state",
        "authority_binding",
        "authority_id",
        "attempt_id",
        "authorization_phrase_sha256",
        "authorization_phrase_stored",
        "onsite_gate_canonical_sha256",
        "fake_evaluation_now_utc",
        "attempt_registry_file",
        "registry_initial_canonical_sha256",
        "registry_whole_file_sha256",
        "registry_is_immutable_o_excl_marker",
        "registry_parent_directory_fsync_status",
        "output_parent_directory_fsync_status",
        "file_and_directory_fsync_are_not_power_loss_durability_proof",
        "endpoint_outcomes",
        "fake_fetch_calls",
        "fake_validation_acknowledged",
        "maximum_get_requests",
        "post_requests",
        "request_bodies",
        "device_api_claim_requests",
        "client_mutation_requests",
        "client_visible_refresh_requests",
        "network_requests",
        "serial_or_com_accesses",
        "hardware_accessed",
        "device_io_performed",
        "retry_allowed",
        "automatic_recovery",
        "automatic_chaining",
        "phase_b_authority_generated",
        "phase_b_authorization_generated",
        "phase_b_requests",
        "eligible_for_live_phase_b_authority",
        "phase_b_ineligibility_reason",
        "original_plan_final_output_touched",
        "version_protocol_response_conformance",
        "responder_or_device_identity_proven",
        "trusted_ip_binding_proven",
        "fresh_post_reset_application_boot_proven",
        "active_application_or_ota_slot_proven",
        "actual_device_or_background_side_effects",
        "error_type",
        "error",
        "integrity",
    }
    if type(root) is not dict or set(root) != root_keys:
        raise PhaseAAuthorityError("Phase-A fake receipt exact root key set differs")
    static_expected = {
        "schema_version": SCHEMA_VERSION,
        "kind": PHASE_A_FAKE_RECEIPT_KIND,
        "classification": PHASE_A_FAKE_CLASSIFICATION,
        "authority_binding": authority_binding,
        "authority_id": authority["authority_id"],
        "attempt_id": authority["attempt"]["attempt_id"],
        "authorization_phrase_sha256": contract.sha256(
            _authorization_phrase(
                authority, authority_file_sha256=contract.sha256(authority_payload)
            ).encode("ascii")
        ),
        "authorization_phrase_stored": False,
        "onsite_gate_canonical_sha256": authority["fresh_phase_a_onsite_gate"][
            "gate_canonical_sha256"
        ],
        "attempt_registry_file": registry_summary["path"],
        "registry_initial_canonical_sha256": registry_summary["canonical_sha256"],
        "registry_whole_file_sha256": registry_summary["sha256"],
        "registry_is_immutable_o_excl_marker": True,
        "file_and_directory_fsync_are_not_power_loss_durability_proof": True,
        "maximum_get_requests": 1,
        "post_requests": 0,
        "request_bodies": 0,
        "device_api_claim_requests": 0,
        "client_mutation_requests": 0,
        "client_visible_refresh_requests": 0,
        "network_requests": 0,
        "serial_or_com_accesses": 0,
        "hardware_accessed": False,
        "device_io_performed": False,
        "retry_allowed": False,
        "automatic_recovery": False,
        "automatic_chaining": False,
        "phase_b_authority_generated": False,
        "phase_b_authorization_generated": False,
        "phase_b_requests": 0,
        "eligible_for_live_phase_b_authority": False,
        "phase_b_ineligibility_reason": (
            "SYNTHETIC_FAKE_RECEIPT_NEVER_ELIGIBLE_FOR_LIVE_PHASE_B"
        ),
        "original_plan_final_output_touched": False,
        "responder_or_device_identity_proven": False,
        "trusted_ip_binding_proven": False,
        "fresh_post_reset_application_boot_proven": False,
        "active_application_or_ota_slot_proven": False,
        "actual_device_or_background_side_effects": (
            "NOT_APPLICABLE_SCRIPTED_FAKE_ONLY"
        ),
    }
    for key, expected in static_expected.items():
        try:
            facade._require_exact_value(  # noqa: SLF001
                root[key], expected, label=f"Phase-A receipt.{key}"
            )
        except facade.StageBFacadeContractError as error:
            raise PhaseAAuthorityError(str(error)) from error
    for status_key in (
        "registry_parent_directory_fsync_status",
        "output_parent_directory_fsync_status",
    ):
        if type(root[status_key]) is not str or not root[status_key].endswith(
            "NOT_POWER_LOSS_DURABILITY_PROOF"
        ):
            raise PhaseAAuthorityError(f"Phase-A receipt {status_key} differs")
    _time_gate(authority, now=str(root["fake_evaluation_now_utc"]))
    if (
        type(root["endpoint_outcomes"]) is not list
        or len(root["endpoint_outcomes"]) != 1
    ):
        raise PhaseAAuthorityError("Phase-A receipt endpoint outcome count differs")
    endpoint = root["endpoint_outcomes"][0]
    endpoint_keys = {
        "ordinal",
        "name",
        "method",
        "path",
        "absolute_url",
        "attempt_checkpoint_before_fake_fetch",
        "last_completed_gate",
        "failure_stage",
        "response_received",
        "http_status",
        "response_header_count",
        "synthetic_canonical_status_and_header_ascii_bytes",
        "synthetic_canonical_status_and_header_sha256",
        "synthetic_header_representation_is_not_observed_raw_wire_bytes",
        "response_headers_bounded",
        "response_entity_body_bytes",
        "response_entity_body_sha256",
        "response_entity_body_base64",
        "strict_parsed_canonical_sha256",
        "validation_stack",
        "validation_outcome",
        "request_wire_emitted",
        "peer_received_request",
    }
    if type(endpoint) is not dict or set(endpoint) != endpoint_keys:
        raise PhaseAAuthorityError("Phase-A receipt endpoint exact key set differs")
    request = authority["ordered_requests"][0]
    endpoint_static = {
        "ordinal": 1,
        "name": "version",
        "method": "GET",
        "path": request["path"],
        "absolute_url": request["absolute_url"],
        "attempt_checkpoint_before_fake_fetch": True,
        "validation_stack": [
            "raw_size_and_strict_json_decoder",
            "source_pinned_exact_surface_validator",
        ],
        "request_wire_emitted": "NOT_APPLICABLE_SCRIPTED_FAKE_ONLY",
        "peer_received_request": "NOT_APPLICABLE_SCRIPTED_FAKE_ONLY",
        "synthetic_header_representation_is_not_observed_raw_wire_bytes": True,
    }
    for key, expected in endpoint_static.items():
        try:
            facade._require_exact_value(  # noqa: SLF001
                endpoint[key], expected, label=f"Phase-A endpoint.{key}"
            )
        except facade.StageBFacadeContractError as error:
            raise PhaseAAuthorityError(str(error)) from error

    success = root["state"] == "TERMINAL_SUCCESS_FAKE_ONLY"
    if root["state"] not in {
        "TERMINAL_SUCCESS_FAKE_ONLY",
        "TERMINAL_FAILURE_FAKE_ONLY_NO_RETRY",
    }:
        raise PhaseAAuthorityError("Phase-A fake receipt terminal state differs")
    if type(root["fake_fetch_calls"]) is not int or root["fake_fetch_calls"] not in (
        0,
        1,
    ):
        raise PhaseAAuthorityError("Phase-A fake fetch count differs")
    if type(root["fake_validation_acknowledged"]) is not bool:
        raise PhaseAAuthorityError("Phase-A validation acknowledgement type differs")
    if root["version_protocol_response_conformance"] is not success:
        raise PhaseAAuthorityError("Phase-A conformance/state consistency differs")
    if success:
        if (
            root["error_type"] is not None
            or root["error"] is not None
            or root["fake_fetch_calls"] != 1
            or root["fake_validation_acknowledged"] is not True
            or endpoint["response_received"] is not True
            or endpoint["http_status"] != 200
            or endpoint["validation_outcome"] != "PASS"
            or endpoint["last_completed_gate"] != "EXACT_V10_VALIDATED"
            or endpoint["failure_stage"] is not None
        ):
            raise PhaseAAuthorityError("Phase-A success receipt consistency differs")
    else:
        if (
            type(root["error_type"]) is not str
            or type(root["error"]) is not str
            or root["fake_fetch_calls"] != 1
            or endpoint["validation_outcome"] != "FAILED_TERMINAL_NO_RETRY"
            or root["fake_validation_acknowledged"] is not False
            or endpoint["last_completed_gate"]
            not in {
                "ATTEMPT_RECORDED",
                "RESPONSE_RECEIVED",
                "BODY_SIZE_OK",
                "SYNTHETIC_HEADERS_BOUNDED",
                "HTTP_ENVELOPE_OK",
            }
            or endpoint["failure_stage"]
            != {
                "ATTEMPT_RECORDED": "TRANSPORT_FETCH",
                "RESPONSE_RECEIVED": "BODY_SIZE_GATE",
                "BODY_SIZE_OK": "SYNTHETIC_HEADER_GATE",
                "SYNTHETIC_HEADERS_BOUNDED": "HTTP_ENVELOPE_GATE",
                "HTTP_ENVELOPE_OK": "STRICT_JSON_OR_EXACT_V10_GATE",
            }[endpoint["last_completed_gate"]]
        ):
            raise PhaseAAuthorityError("Phase-A failure receipt consistency differs")
        if require_success:
            raise PhaseAAuthorityError("Phase-A receipt is not terminal success")

    if type(endpoint["response_received"]) is not bool:
        raise PhaseAAuthorityError("Phase-A response_received type differs")
    if endpoint["response_received"] is False:
        for field in (
            "http_status",
            "response_header_count",
            "synthetic_canonical_status_and_header_ascii_bytes",
            "synthetic_canonical_status_and_header_sha256",
            "response_headers_bounded",
            "response_entity_body_bytes",
            "response_entity_body_sha256",
            "response_entity_body_base64",
            "strict_parsed_canonical_sha256",
        ):
            if endpoint[field] is not None:
                raise PhaseAAuthorityError(
                    f"Phase-A no-response receipt unexpectedly contains {field}"
                )
    else:
        if (
            type(endpoint["http_status"]) is not int
            or type(endpoint["response_entity_body_bytes"]) is not int
        ):
            raise PhaseAAuthorityError(
                "Phase-A received-response primitive evidence types differ"
            )

    body_bundle = (
        endpoint["response_entity_body_sha256"],
        endpoint["response_entity_body_base64"],
    )
    if any(item is None for item in body_bundle) and not all(
        item is None for item in body_bundle
    ):
        raise PhaseAAuthorityError("Phase-A response body evidence is orphaned")
    header_bundle = (
        endpoint["synthetic_canonical_status_and_header_ascii_bytes"],
        endpoint["synthetic_canonical_status_and_header_sha256"],
        endpoint["response_headers_bounded"],
    )
    if any(item is None for item in header_bundle) and not all(
        item is None for item in header_bundle
    ):
        raise PhaseAAuthorityError("Phase-A synthetic header evidence is orphaned")
    gate = endpoint["last_completed_gate"]
    if gate == "ATTEMPT_RECORDED" and endpoint["response_received"] is not False:
        raise PhaseAAuthorityError("Phase-A transport-failure evidence differs")
    if gate == "RESPONSE_RECEIVED" and (
        endpoint["response_received"] is not True
        or 0 < endpoint["response_entity_body_bytes"] <= facade.MAX_JSON_BYTES
        or endpoint["response_header_count"] is not None
        or not all(item is None for item in body_bundle + header_bundle)
    ):
        raise PhaseAAuthorityError("Phase-A body-size failure evidence differs")
    if gate == "BODY_SIZE_OK" and (
        not 0 < endpoint["response_entity_body_bytes"] <= facade.MAX_JSON_BYTES
        or endpoint["response_header_count"] is not None
        or not all(item is None for item in body_bundle + header_bundle)
    ):
        raise PhaseAAuthorityError("Phase-A header-gate failure evidence differs")
    if gate in {
        "SYNTHETIC_HEADERS_BOUNDED",
        "HTTP_ENVELOPE_OK",
        "EXACT_V10_VALIDATED",
    } and (
        not all(item is not None for item in body_bundle + header_bundle)
        or endpoint["response_received"] is not True
        or type(endpoint["response_header_count"]) is not int
    ):
        raise PhaseAAuthorityError("Phase-A bounded response evidence differs")
    if success is not (gate == "EXACT_V10_VALIDATED"):
        raise PhaseAAuthorityError("Phase-A gate/success classification differs")
    if (endpoint["strict_parsed_canonical_sha256"] is None) is not (not success):
        raise PhaseAAuthorityError("Phase-A parsed evidence/state differs")

    encoded = endpoint["response_entity_body_base64"]
    if encoded is not None:
        if type(encoded) is not str:
            raise PhaseAAuthorityError("Phase-A response base64 type differs")
        try:
            entity = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError, TypeError) as error:
            raise PhaseAAuthorityError("Phase-A response base64 is invalid") from error
        if (
            type(endpoint["response_entity_body_bytes"]) is not int
            or endpoint["response_entity_body_bytes"] != len(entity)
            or endpoint["response_entity_body_sha256"] != contract.sha256(entity)
        ):
            raise PhaseAAuthorityError("Phase-A response entity binding differs")
        bounded_headers = endpoint["response_headers_bounded"]
        if bounded_headers is not None:
            if type(bounded_headers) is not list or any(
                type(item) is not list
                or len(item) != 2
                or type(item[0]) is not str
                or type(item[1]) is not str
                for item in bounded_headers
            ):
                raise PhaseAAuthorityError(
                    "Phase-A bounded response headers type differs"
                )
            replay_response = ScriptedPhaseAFakeResponse(
                status=endpoint["http_status"],
                headers=tuple((item[0], item[1]) for item in bounded_headers),
                entity_body=entity,
            )
            lowered, evidence = _bounded_fake_header_evidence(replay_response)
            for evidence_key, evidence_value in evidence.items():
                try:
                    facade._require_exact_value(  # noqa: SLF001
                        endpoint[evidence_key],
                        evidence_value,
                        label=f"Phase-A endpoint.{evidence_key}",
                    )
                except facade.StageBFacadeContractError as error:
                    raise PhaseAAuthorityError(str(error)) from error
            envelope_passed = False
            try:
                _validate_fake_http_envelope(replay_response, lowered)
                envelope_passed = True
            except PhaseAAuthorityError:
                if gate != "SYNTHETIC_HEADERS_BOUNDED":
                    raise PhaseAAuthorityError(
                        "Phase-A envelope replay/gate classification differs"
                    )
            if envelope_passed:
                context = _v10_context
                if context is None:
                    blueprint = facade.load_blueprint(
                        Path(str(authority["blueprint_binding"]["path"]))
                    )
                    context = facade._load_frozen_v10_release(  # noqa: SLF001
                        Path(
                            str(
                                blueprint["frozen_v10_validator_binding"][
                                    "release_file"
                                ]
                            )
                        )
                    )
                try:
                    parsed, _ = facade.decode_and_validate_v10_response_bytes(
                        "version", entity, context
                    )
                except facade.StageBFacadeContractError:
                    if gate != "HTTP_ENVELOPE_OK":
                        raise PhaseAAuthorityError(
                            "Phase-A exact-validator replay/gate classification differs"
                        )
                else:
                    if not success:
                        raise PhaseAAuthorityError(
                            "valid V10 response is falsely classified as failure"
                        )
                    if endpoint["strict_parsed_canonical_sha256"] != contract.sha256(
                        parsed
                    ):
                        raise PhaseAAuthorityError(
                            "Phase-A strict parsed canonical SHA-256 differs"
                        )
        elif gate in {
            "SYNTHETIC_HEADERS_BOUNDED",
            "HTTP_ENVELOPE_OK",
            "EXACT_V10_VALIDATED",
        }:
            raise PhaseAAuthorityError(
                "Phase-A bounded response lacks lossless entity bytes"
            )
    elif success:
        raise PhaseAAuthorityError("Phase-A success receipt lacks raw entity bytes")
    info = resolved.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or _is_reparse(info):
        raise PhaseAAuthorityError("Phase-A receipt is not a unique regular file")
    return {
        "valid": True,
        "terminal_success": success,
        "kind": PHASE_A_FAKE_RECEIPT_KIND,
        "classification": PHASE_A_FAKE_CLASSIFICATION,
        "path": str(resolved),
        "bytes": len(payload),
        "sha256": contract.sha256(payload),
        "canonical_sha256": root["integrity"]["canonical_sha256"],
        "registry_whole_file_sha256": registry_summary["sha256"],
        "raw_version_replayed": success,
        "eligible_for_live_phase_b_authority": False,
        "retry_allowed": False,
    }


def require_live_phase_b_eligible_phase_a_receipt(
    receipt_file: Path,
    *,
    authority_file: Path,
    _v10_context: Any | None = None,
) -> None:
    """Reject synthetic evidence at the future live Phase-B boundary."""

    summary = validate_phase_a_fake_terminal_receipt(
        receipt_file,
        authority_file=authority_file,
        require_success=True,
        _v10_context=_v10_context,
    )
    if summary["classification"] == PHASE_A_FAKE_CLASSIFICATION:
        raise PhaseAAuthorityError(
            "synthetic fake Phase-A receipt is never eligible for live Phase-B"
        )
    raise PhaseAAuthorityError(
        "no reviewed live Phase-A receipt kind is implemented by this contract"
    )


def _add_fresh_gate_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--prepared-at", required=True)
    parser.add_argument("--current-reading-a", required=True)
    parser.add_argument("--locator-selection-phrase", required=True)
    for flag in (
        "j2-off",
        "screen-clean-white",
        "esp32-usb-connected",
        "supply-3v3-cv-normal",
        "temperature-exact-25c",
        "current-limit-exact-1a",
        "current-and-temperature-monitors-ready",
        "physical-cutoff-ready",
        "no-reset-since-stage-a",
        "no-flash-since-stage-a",
        "no-refresh-since-stage-a",
        "no-rewire-since-stage-a",
    ):
        parser.add_argument(f"--{flag}", action="store_true")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build-phase-a", allow_abbrev=False)
    build.add_argument("--blueprint", type=Path, required=True)
    build.add_argument("--stage-a-receipt", type=Path, required=True)
    build.add_argument("--authority-output", type=Path, required=True)
    build.add_argument("--attempt-registry", type=Path, required=True)
    build.add_argument("--terminal-receipt", type=Path, required=True)
    _add_fresh_gate_arguments(build)
    validate = commands.add_parser("validate-phase-a", allow_abbrev=False)
    validate.add_argument("--authority", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Build/validate the offline challenge; never execute a request."""

    args = _parser().parse_args(argv)
    try:
        if args.command == "build-phase-a":
            root = materialize_phase_a_authority(
                blueprint_file=args.blueprint,
                stage_a_receipt_file=args.stage_a_receipt,
                authority_file=args.authority_output,
                attempt_registry_file=args.attempt_registry,
                terminal_receipt_file=args.terminal_receipt,
                observed_at=args.observed_at,
                prepared_at=args.prepared_at,
                current_reading_a=args.current_reading_a,
                locator_selection_phrase=args.locator_selection_phrase,
                j2_off=args.j2_off,
                screen_clean_white=args.screen_clean_white,
                esp32_usb_connected=args.esp32_usb_connected,
                supply_3v3_cv_normal=args.supply_3v3_cv_normal,
                temperature_exact_25c=args.temperature_exact_25c,
                current_limit_exact_1a=args.current_limit_exact_1a,
                current_and_temperature_monitors_ready=(
                    args.current_and_temperature_monitors_ready
                ),
                physical_cutoff_ready=args.physical_cutoff_ready,
                no_reset_since_stage_a=args.no_reset_since_stage_a,
                no_flash_since_stage_a=args.no_flash_since_stage_a,
                no_refresh_since_stage_a=args.no_refresh_since_stage_a,
                no_rewire_since_stage_a=args.no_rewire_since_stage_a,
            )
            write_new_phase_a_authority(args.authority_output, root)
        else:
            root = load_phase_a_authority(args.authority)
        summary = validate_phase_a_authority(root, require_attempt_paths_absent=True)
    except (PhaseAAuthorityError, KeyError, TypeError) as error:
        print(f"Phase-A authority error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
