#!/usr/bin/env python3
"""Build and validate the offline V10 C-first diagnostic-recovery plan.

This module has no live execution command.  It binds the exact terminal V10
diagnostic failure, the deeply validated V10 release and control binary, one
candidate private IPv4 locator, and one new output path into a sealed plan.
The locator came from an ARP-cache observation, which is explicitly not device
identity, reachability, or authorization evidence.

The planned operation is a separate attempt with exactly one required volatile
new-boot operation: at most four ordered, read-only GETs and zero POSTs, claims,
persistent flash/NVS mutations, diagnostic-API mutations, serial operations,
or visible refreshes.  A fresh, plan-bound user authorization and all live
hardware assertions remain unsatisfied after materialization.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Final, Mapping, Sequence
from urllib import parse as urlparse

from tools import mf1750_ec5_h3_matched_control_contract as contract
from tools import mf1750_ec5_h3_matched_control_physical_once as physical
from tools import mf1750_ec5_h3_matched_control_release as release


SCHEMA_VERSION: Final = 1
KIND: Final = "mf1750-ec5-h3-c-first-v10-diagnostic-recovery-plan-v1"
CLASSIFICATION: Final = "OFFLINE_PLAN_NOT_LIVE_AUTHORIZATION"
PLAN_VERSION: Final = "V10_DIAGNOSTIC_RECOVERY_V1"
MAX_JSON_BYTES: Final = 4_000_000
MAX_FIRMWARE_BYTES: Final = 4_000_000

EXPECTED_PROFILE_ID: Final = "WF20_25"
EXPECTED_ORDINAL: Final = 1
EXPECTED_RELEASE_ID: Final = (
    "1cf8307c8906fa3057509c7a4a15bd79156751aa6b27c3f158435fbaa1049e36"
)
EXPECTED_RELEASE_FILE_SHA256: Final = (
    "a716dac890b3e272144365f51ae1167f6306d4830d841b11d00610ebb2b0698b"
)
EXPECTED_RELEASE_CANONICAL_SHA256: Final = (
    "5616bd495c9faf0983c3d361d5d3bea57837c5f5d8a498805cca940ca595b00e"
)
EXPECTED_CONTROL_BINARY_SHA256: Final = (
    "f0ce5e7a823a8ff3015292393a8a6f17c60522cf85e67b8705ba13b41d11218e"
)
EXPECTED_CONTROL_ELF_SHA256: Final = (
    "27d23a21fc6a297933415f59891a5181452a3c089842cde29b3dfff5dbd34d41"
)
EXPECTED_HARDWARE_ACTION_ID: Final = (
    "a83e82c70a7fc74865b578e73c59f2f7c2b13743fa1b33a12455ac61d1f4b854"
)
EXPECTED_PRIOR_FAILURE_FILE_SHA256: Final = (
    "fe9882799f10112adad7b2492dc3cf874afbf2486a7554cdc747b56468c9b95e"
)
EXPECTED_PRIOR_FAILURE_CANONICAL_SHA256: Final = (
    "92dfa7882d590489f8ae86d6e574d193b2a66192f4b76d3bb91b8ec050ebab61"
)
EXPECTED_DEVICE_MAC: Final = "a4:cb:8f:d9:fc:d4"
ARP_SOURCE: Final = "unverified_operator_input"
MONITORING_CONFIRMATION: Final = contract.OPERATOR_MONITORING_CONFIRMATION
SCREEN_STATE: Final = physical.SCREEN_INITIAL

ENDPOINT_NAMES: Final = ("version", "manifest", "status", "report")
MAC_PATTERN: Final = re.compile(r"^[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}$")
RFC1918_NETWORKS: Final = tuple(
    ipaddress.ip_network(value)
    for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


class DiagnosticRecoveryContractError(ValueError):
    """The offline recovery plan or one of its exact bindings differs."""


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    root = deepcopy(dict(unsigned))
    root["integrity"] = {
        "algorithm": "sha256",
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
        "canonical_sha256": contract.sha256(root),
    }
    return root


def _validate_seal(value: Mapping[str, Any], *, label: str) -> str:
    integrity = value.get("integrity")
    if not isinstance(integrity, Mapping) or set(integrity) != {
        "algorithm",
        "scope",
        "canonical_sha256",
    }:
        raise DiagnosticRecoveryContractError(f"{label} integrity object differs")
    expected = _seal({key: item for key, item in value.items() if key != "integrity"})[
        "integrity"
    ]
    if dict(integrity) != expected:
        raise DiagnosticRecoveryContractError(f"{label} canonical integrity differs")
    return str(integrity["canonical_sha256"])


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_regular_bytes(path: Path, *, label: str, maximum: int) -> tuple[Path, bytes]:
    candidate = Path(os.path.abspath(os.fspath(path)))
    try:
        before = candidate.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise DiagnosticRecoveryContractError(
                f"{label} must be a non-symlink regular file"
            )
        if before.st_size <= 0 or before.st_size > maximum:
            raise DiagnosticRecoveryContractError(f"{label} size is invalid")
        payload = candidate.read_bytes()
        after = candidate.lstat()
    except OSError as error:
        raise DiagnosticRecoveryContractError(
            f"could not read {label}: {error}"
        ) from error
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or len(payload) != after.st_size:
        raise DiagnosticRecoveryContractError(f"{label} changed while being read")
    return candidate, payload


def _decode_json(payload: bytes, *, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {item}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise DiagnosticRecoveryContractError(
            f"{label} is not strict UTF-8 JSON"
        ) from error
    if not isinstance(value, Mapping):
        raise DiagnosticRecoveryContractError(f"{label} root is not an object")
    return value


def _read_json(path: Path, *, label: str) -> tuple[Path, bytes, Mapping[str, Any]]:
    resolved, payload = _read_regular_bytes(path, label=label, maximum=MAX_JSON_BYTES)
    return resolved, payload, _decode_json(payload, label=label)


def _normalize_candidate_base_url(value: str) -> tuple[str, str]:
    try:
        parsed = urlparse.urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise DiagnosticRecoveryContractError(
            "candidate base URL is malformed"
        ) from error
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise DiagnosticRecoveryContractError(
            "candidate base URL must be bare http://RFC1918-IPv4 with no port/path"
        )
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError as error:
        raise DiagnosticRecoveryContractError(
            "candidate base URL host must be an IPv4 literal"
        ) from error
    if not isinstance(address, ipaddress.IPv4Address) or not any(
        address in network for network in RFC1918_NETWORKS
    ):
        raise DiagnosticRecoveryContractError(
            "candidate base URL must use an RFC1918 IPv4 address"
        )
    if (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or int(str(address).split(".")[-1]) in (0, 255)
    ):
        raise DiagnosticRecoveryContractError(
            "candidate base URL IPv4 address is not a usable host locator"
        )
    return f"http://{address}", str(address)


def _normalize_mac(value: str) -> str:
    candidate = value.strip()
    if MAC_PATTERN.fullmatch(candidate) is None:
        raise DiagnosticRecoveryContractError(
            "ARP-observed MAC must use six colon-separated octets"
        )
    normalized = candidate.lower()
    if normalized != EXPECTED_DEVICE_MAC:
        raise DiagnosticRecoveryContractError(
            "ARP-observed MAC is not the pinned ESP32"
        )
    return normalized


def _assert_non_symlink_parent_chain(path: Path, *, label: str) -> None:
    for parent in reversed((path.parent, *path.parent.parents)):
        try:
            info = parent.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise DiagnosticRecoveryContractError(
                f"could not inspect {label} parent: {error}"
            ) from error
        if stat.S_ISLNK(info.st_mode):
            raise DiagnosticRecoveryContractError(
                f"{label} parent chain contains a symlink"
            )
        if not stat.S_ISDIR(info.st_mode):
            raise DiagnosticRecoveryContractError(
                f"{label} parent chain is not a directory"
            )


def _assert_new_output(
    path: Path,
    *,
    prior_path: Path,
    release_path: Path,
    require_absent: bool,
) -> Path:
    candidate = Path(os.path.abspath(os.fspath(path)))
    if candidate in (prior_path, release_path):
        raise DiagnosticRecoveryContractError(
            "new diagnostic output must differ from all bound input files"
        )
    try:
        candidate.lstat()
    except FileNotFoundError:
        pass
    except OSError as error:
        raise DiagnosticRecoveryContractError(
            f"could not inspect new diagnostic output: {error}"
        ) from error
    else:
        if stat.S_ISLNK(candidate.lstat().st_mode):
            raise DiagnosticRecoveryContractError(
                "new diagnostic output must not be a symlink"
            )
        if not stat.S_ISREG(candidate.lstat().st_mode):
            raise DiagnosticRecoveryContractError(
                "new diagnostic output must be a regular file when present"
            )
    if require_absent and candidate.exists():
        raise DiagnosticRecoveryContractError(
            "new diagnostic output already exists; this plan is one-shot"
        )
    _assert_non_symlink_parent_chain(candidate, label="new diagnostic output")
    return candidate


def _prior_failure_binding(path: Path) -> tuple[Path, dict[str, Any]]:
    resolved, payload, root = _read_json(path, label="prior terminal diagnostic")
    canonical = _validate_seal(root, label="prior terminal diagnostic")
    if contract.sha256(payload) != EXPECTED_PRIOR_FAILURE_FILE_SHA256:
        raise DiagnosticRecoveryContractError(
            "prior terminal diagnostic whole-file SHA differs"
        )
    if canonical != EXPECTED_PRIOR_FAILURE_CANONICAL_SHA256:
        raise DiagnosticRecoveryContractError(
            "prior terminal diagnostic canonical SHA differs"
        )
    expected = {
        "schema_version": physical.SCHEMA_VERSION,
        "kind": physical.OUTPUT_ATTEMPT_KIND,
        "state": "TERMINAL_PRECLAIM_FAILURE",
        "retry_allowed": False,
        "release_id": EXPECTED_RELEASE_ID,
        "profile_id": EXPECTED_PROFILE_ID,
        "ordinal": EXPECTED_ORDINAL,
        "hardware_action_id": EXPECTED_HARDWARE_ACTION_ID,
        "operator_temperature_c": "25.0",
        "operator_j2_assertion": "OFF",
        "operator_screen_state": SCREEN_STATE,
        "operator_monitoring_state": MONITORING_CONFIRMATION,
        "created_before_claim": True,
        "created_before_network": True,
        "network_requests_before_reservation": 0,
        "post_requests_before_reservation": 0,
        "network_requests_after_reservation": "unknown_or_not_applicable",
        "error_type": "MatchedControlPhysicalError",
    }
    for key, wanted in expected.items():
        if root.get(key) != wanted:
            raise DiagnosticRecoveryContractError(
                f"prior terminal diagnostic {key} differs"
            )
    if root.get("output_file") != str(resolved):
        raise DiagnosticRecoveryContractError(
            "prior terminal diagnostic self-path differs"
        )
    error_text = root.get("error")
    if not isinstance(error_text, str) or not error_text.startswith(
        "HTTP GET /api/ec5/h3-matched-control-v2/version failed:"
    ):
        raise DiagnosticRecoveryContractError(
            "prior terminal diagnostic failure endpoint differs"
        )
    return resolved, {
        "path": str(resolved),
        "bytes": len(payload),
        "sha256": contract.sha256(payload),
        "canonical_sha256": canonical,
        "schema_version": root["schema_version"],
        "kind": root["kind"],
        "state": root["state"],
        "retry_allowed": root["retry_allowed"],
        "release_id": root["release_id"],
        "profile_id": root["profile_id"],
        "ordinal": root["ordinal"],
        "hardware_action_id": root["hardware_action_id"],
        "failed_endpoint": "/api/ec5/h3-matched-control-v2/version",
        "error_type": root["error_type"],
        "error_sha256": contract.sha256(error_text.encode("utf-8")),
        "network_requests_after_reservation": root[
            "network_requests_after_reservation"
        ],
        "prior_attempt_is_permanently_terminal": True,
        "prior_attempt_must_not_be_retried": True,
    }


def _release_binding(path: Path) -> tuple[Path, dict[str, Any]]:
    resolved, payload, root = _read_json(path, label="V10 release")
    try:
        summary = release.validate_release(root)
    except release.MatchedControlReleaseError as error:
        raise DiagnosticRecoveryContractError(
            f"V10 release failed deep validation: {error}"
        ) from error
    exact = {
        "release_id": EXPECTED_RELEASE_ID,
        "profile_id": EXPECTED_PROFILE_ID,
        "canonical_sha256": EXPECTED_RELEASE_CANONICAL_SHA256,
        "control_binary_sha256": EXPECTED_CONTROL_BINARY_SHA256,
        "control_elf_sha256": EXPECTED_CONTROL_ELF_SHA256,
    }
    for key, wanted in exact.items():
        if summary.get(key) != wanted:
            raise DiagnosticRecoveryContractError(f"V10 release {key} differs")
    file_sha = contract.sha256(payload)
    if file_sha != EXPECTED_RELEASE_FILE_SHA256:
        raise DiagnosticRecoveryContractError("V10 release whole-file SHA differs")

    bindings = root.get("action_artifact_bindings")
    if not isinstance(bindings, list):
        raise DiagnosticRecoveryContractError("V10 release action bindings are absent")
    matches = [item for item in bindings if item.get("ordinal") == EXPECTED_ORDINAL]
    if len(matches) != 1:
        raise DiagnosticRecoveryContractError(
            "V10 release control binding is not unique"
        )
    action = matches[0]
    if (
        action.get("hardware_action_id") != EXPECTED_HARDWARE_ACTION_ID
        or action.get("firmware_binary_sha256") != EXPECTED_CONTROL_BINARY_SHA256
        or action.get("firmware_elf_sha256") != EXPECTED_CONTROL_ELF_SHA256
    ):
        raise DiagnosticRecoveryContractError("V10 release control identity differs")

    images = root.get("compiled_images")
    if not isinstance(images, Mapping):
        raise DiagnosticRecoveryContractError("V10 release compiled images are absent")
    control_image = images.get("matched_no_r20_r21_control")
    if not isinstance(control_image, Mapping):
        raise DiagnosticRecoveryContractError("V10 release control image is absent")
    firmware = control_image.get("firmware")
    if not isinstance(firmware, Mapping):
        raise DiagnosticRecoveryContractError("V10 control firmware is absent")
    binary = firmware.get("binary")
    elf = firmware.get("elf")
    if not isinstance(binary, Mapping) or not isinstance(elf, Mapping):
        raise DiagnosticRecoveryContractError("V10 control binary/ELF is absent")
    binary_path, binary_payload = _read_regular_bytes(
        Path(str(binary.get("path"))),
        label="V10 control binary",
        maximum=MAX_FIRMWARE_BYTES,
    )
    if (
        len(binary_payload) != binary.get("bytes")
        or contract.sha256(binary_payload) != EXPECTED_CONTROL_BINARY_SHA256
        or binary.get("sha256") != EXPECTED_CONTROL_BINARY_SHA256
        or elf.get("sha256") != EXPECTED_CONTROL_ELF_SHA256
    ):
        raise DiagnosticRecoveryContractError("V10 control binary identity differs")
    host_bundle = root.get("host_execution_bundle")
    if not isinstance(host_bundle, Mapping):
        raise DiagnosticRecoveryContractError("V10 host execution bundle is absent")
    return resolved, {
        "path": str(resolved),
        "bytes": len(payload),
        "sha256": file_sha,
        "canonical_sha256": summary["canonical_sha256"],
        "release_id": summary["release_id"],
        "profile_id": summary["profile_id"],
        "contract_id": root["contract_id"],
        "host_execution_bundle_sha256": host_bundle["canonical_sha256"],
        "control_artifact": {
            "ordinal": EXPECTED_ORDINAL,
            "role": action["role"],
            "hardware_action_id": action["hardware_action_id"],
            "transaction_descriptor_sha256": action["transaction_descriptor_sha256"],
            "base_route": action["base_route"],
            "binary": {
                "path": str(binary_path),
                "bytes": len(binary_payload),
                "sha256": contract.sha256(binary_payload),
            },
            "elf_sha256": elf["sha256"],
        },
        "deep_validated": True,
    }


def materialize_plan(
    *,
    prior_failure_file: Path,
    release_file: Path,
    candidate_base_url: str,
    operator_reported_arp_mac: str,
    new_diagnostic_output: Path,
    _require_new_output_absent: bool = True,
) -> dict[str, Any]:
    """Return a sealed, deterministic, non-authorizing recovery plan."""

    prior_path, prior = _prior_failure_binding(prior_failure_file)
    release_path, release_record = _release_binding(release_file)
    if prior["release_id"] != release_record["release_id"]:
        raise DiagnosticRecoveryContractError(
            "prior failure and V10 release identities differ"
        )
    base_url, candidate_ipv4 = _normalize_candidate_base_url(candidate_base_url)
    mac = _normalize_mac(operator_reported_arp_mac)
    new_output = _assert_new_output(
        new_diagnostic_output,
        prior_path=prior_path,
        release_path=release_path,
        require_absent=_require_new_output_absent,
    )
    endpoints = [
        {
            "ordinal": index,
            "method": "GET",
            "path": f"{release_record['control_artifact']['base_route']}/{name}",
        }
        for index, name in enumerate(ENDPOINT_NAMES, start=1)
    ]
    plan_intent = {
        "plan_version": PLAN_VERSION,
        "prior_failure_sha256": prior["sha256"],
        "prior_failure_canonical_sha256": prior["canonical_sha256"],
        "release_id": release_record["release_id"],
        "release_sha256": release_record["sha256"],
        "release_canonical_sha256": release_record["canonical_sha256"],
        "firmware_binary_sha256": release_record["control_artifact"]["binary"][
            "sha256"
        ],
        "hardware_action_id": release_record["control_artifact"]["hardware_action_id"],
        "candidate_base_url": base_url,
        "operator_reported_candidate_mac": mac,
        "new_diagnostic_output": str(new_output),
        "new_boot_required": True,
        "ordered_requests": endpoints,
        "new_boot_operations_exactly": 1,
        "new_boot_is_volatile_state_change": True,
        "maximum_get_requests": 4,
        "maximum_post_requests": 0,
        "maximum_claims": 0,
        "persistent_flash_or_nvs_mutations": 0,
        "diagnostic_api_mutations": 0,
        "maximum_visible_refreshes": 0,
        "retry": False,
        "automatic_chaining": False,
    }
    plan_intent_sha = contract.sha256(plan_intent)
    new_boot_intent = {
        "plan_version": PLAN_VERSION,
        "prior_failure_sha256": prior["sha256"],
        "release_id": release_record["release_id"],
        "firmware_binary_sha256": release_record["control_artifact"]["binary"][
            "sha256"
        ],
        "new_boot_operations_exactly": 1,
        "new_boot_is_volatile_state_change": True,
        "j2_required": "OFF",
        "visible_refreshes": 0,
        "persistent_flash_or_nvs_mutations": 0,
        "sealed_boot_receipt_required": True,
        "separate_user_authorization_required": True,
    }
    new_boot_intent_sha = contract.sha256(new_boot_intent)
    diagnostic_intent_template = {
        "plan_version": PLAN_VERSION,
        "plan_intent_canonical_sha256": plan_intent_sha,
        "sealed_new_boot_receipt_canonical_sha256": (
            "REQUIRED_FUTURE_VALUE_NOT_PRESENT_IN_OFFLINE_PLAN"
        ),
        "fresh_onsite_gate_receipt_canonical_sha256": (
            "REQUIRED_FUTURE_VALUE_NOT_PRESENT_IN_OFFLINE_PLAN"
        ),
        "trusted_single_ip_binding_receipt_canonical_sha256": (
            "REQUIRED_FUTURE_VALUE_NOT_PRESENT_IN_OFFLINE_PLAN"
        ),
        "unique_attempt_reservation_canonical_sha256": (
            "REQUIRED_FUTURE_VALUE_NOT_PRESENT_IN_OFFLINE_PLAN"
        ),
        "ordered_requests": endpoints,
        "maximum_get_requests": 4,
        "maximum_post_requests": 0,
        "maximum_claims": 0,
        "persistent_flash_or_nvs_mutations": 0,
        "diagnostic_api_mutations": 0,
        "maximum_visible_refreshes": 0,
        "separate_user_authorization_required": True,
        "retry": False,
        "automatic_chaining": False,
    }
    diagnostic_intent_template_sha = contract.sha256(diagnostic_intent_template)
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "plan_version": PLAN_VERSION,
        "classification": CLASSIFICATION,
        "purpose": "separate_new_boot_v10_c_first_j2_off_diagnostic_attempt",
        "prior_terminal_attempt": prior,
        "v10_release": release_record,
        "network_locator": {
            "candidate_base_url": base_url,
            "candidate_ipv4": candidate_ipv4,
            "expected_device_mac": EXPECTED_DEVICE_MAC,
            "operator_reported_arp_mac": mac,
            "observation_source": ARP_SOURCE,
            "arp_observation_captured_by_this_tool": False,
            "arp_cache_is_device_identity_proof": False,
            "arp_cache_is_reachability_proof": False,
            "arp_cache_is_fresh_boot_binding_proof": False,
            "arp_cache_is_authorization": False,
            "candidate_locator_status": "UNPROVEN_REQUIRES_FRESH_CONFIRMATION",
            "fresh_post_boot_ip_to_exact_mac_confirmation_required": True,
            "do_not_contact_candidate_during_plan_materialization": True,
        },
        "new_attempt": {
            "relationship_to_prior_attempt": "SEPARATE_NEW_ATTEMPT_NOT_RETRY",
            "new_boot_required": True,
            "new_boot_satisfied_by_plan": False,
            "new_boot_must_occur_after_prior_terminal_failure": True,
            "prior_boot_nonce_available": False,
            "same_verified_v10_binary_required": True,
            "reflash_required": False,
            "reflash_authorized": False,
            "serial_or_com_access_authorized": False,
            "reset_or_usb_action_performed_by_plan": False,
            "new_diagnostic_output": str(new_output),
            "new_diagnostic_output_absent_at_materialization": True,
            "new_diagnostic_output_reserved_by_plan": False,
            "prior_output_must_never_be_reused": True,
            "stop_on_first_request_or_validation_error": True,
            "retry_allowed": False,
            "automatic_recovery": False,
            "automatic_chaining": False,
            "profile_switch": False,
            "one_shot_enforced_by_plan": False,
        },
        "live_preconditions": {
            "all_satisfied_by_plan": False,
            "fresh_user_assertions_required": True,
            "operator_temperature_c_required": "25.0",
            "operator_j2_assertion_required": "OFF",
            "operator_screen_state_required": SCREEN_STATE,
            "operator_monitoring_state_required": MONITORING_CONFIRMATION,
            "new_boot_confirmation_required": True,
            "same_v10_binary_confirmation_required": True,
            "candidate_ip_binding_confirmation_required": True,
            "initial_clean_white_is_treatment_finalized_evidence": False,
        },
        "boot_and_mutation_accounting": {
            "new_boot_operations_exactly": 1,
            "new_boot_is_volatile_state_change": True,
            "new_boot_performed_by_plan_materialization": False,
            "persistent_flash_or_nvs_mutations": 0,
            "diagnostic_api_mutations": 0,
            "visible_refreshes": 0,
        },
        "read_only_diagnostic_budget": {
            "ordered_requests": endpoints,
            "successful_diagnostic_exact_get_requests": 4,
            "maximum_get_requests": 4,
            "maximum_post_requests": 0,
            "maximum_claims": 0,
            "maximum_persistent_flash_or_nvs_mutations": 0,
            "maximum_diagnostic_api_mutations": 0,
            "maximum_visible_refreshes": 0,
            "request_bodies": 0,
            "stop_on_first_error": True,
            "no_retry": True,
            "no_automatic_recovery": True,
            "no_automatic_chaining": True,
        },
        "two_stage_future_authority": {
            "required": True,
            "satisfied_by_plan": False,
            "stage_order": ["NEW_BOOT", "READ_ONLY_DIAGNOSTIC"],
            "prior_authorization_reusable": False,
            "copyable_authorization_token_emitted": False,
            "new_boot_stage": {
                "separate_user_authorization_required": True,
                "authorized_by_plan": False,
                "intent": new_boot_intent,
                "intent_canonical_sha256": new_boot_intent_sha,
                "sealed_new_boot_receipt_required": True,
            },
            "diagnostic_stage": {
                "separate_user_authorization_required": True,
                "authorized_by_plan": False,
                "must_follow_validated_new_boot_receipt": True,
                "intent_template": diagnostic_intent_template,
                "intent_template_canonical_sha256": diagnostic_intent_template_sha,
            },
            "combined_non_authorizing_plan_intent": plan_intent,
            "combined_non_authorizing_plan_intent_canonical_sha256": (plan_intent_sha),
            "stage_a_new_boot_intent_sha256": new_boot_intent_sha,
            "stage_b_diagnostic_intent_template_sha256": (
                diagnostic_intent_template_sha
            ),
        },
        "execution_enforcement": {
            "execution_ready": False,
            "plan_registry_status": "NOT_IMPLEMENTED_BY_THIS_CONTRACT_MODULE",
            "execution_facade_status": "NOT_IMPLEMENTED_BY_THIS_CONTRACT_MODULE",
            "unique_attempt_reservation_status": (
                "NOT_IMPLEMENTED_BY_THIS_CONTRACT_MODULE"
            ),
            "one_shot_enforced_by_this_contract_module": False,
            "network_execution_entry_point_present": False,
        },
        "unsatisfied_gates": [
            {
                "id": "sealed_new_boot_receipt",
                "satisfied": False,
                "required_before": "trusted_single_ip_binding",
            },
            {
                "id": "fresh_onsite_gate",
                "satisfied": False,
                "required_before": "read_only_diagnostic_authorization",
            },
            {
                "id": "trusted_single_ip_binding",
                "satisfied": False,
                "unverified_arp_input_is_sufficient": False,
            },
            {
                "id": "unique_execution_facade_and_attempt_reservation",
                "satisfied": False,
                "required_before": "read_only_diagnostic_authorization",
            },
            {
                "id": "new_boot_user_authorization",
                "satisfied": False,
                "separate_from_diagnostic_authorization": True,
            },
            {
                "id": "read_only_diagnostic_user_authorization",
                "satisfied": False,
                "requires_all_prior_gates": True,
            },
        ],
        "offline_materialization": {
            "offline_only": True,
            "live_authorized": False,
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "device_network_accessed": False,
            "network_requests": 0,
            "firmware_written_or_flashed": False,
            "reset_or_usb_action_performed": False,
            "j2_changed": False,
            "device_mutations": 0,
            "claims_created": 0,
            "visible_refreshes": 0,
        },
    }
    unsigned["plan_id"] = contract.sha256(unsigned)
    return _seal(unsigned)


def validate_plan(
    root: Mapping[str, Any], *, require_new_output_absent: bool = False
) -> dict[str, Any]:
    """Deep-rebuild a plan and return its exact non-authorizing identity.

    Structural validation is intentionally usable after the planned diagnostic
    has occupied its one-shot output path.  Callers preparing execution must
    opt into ``require_new_output_absent=True`` for the pre-execution gate.
    """

    canonical = _validate_seal(root, label="diagnostic recovery plan")
    if (
        root.get("schema_version") != SCHEMA_VERSION
        or root.get("kind") != KIND
        or root.get("plan_version") != PLAN_VERSION
        or root.get("classification") != CLASSIFICATION
    ):
        raise DiagnosticRecoveryContractError("recovery plan schema/kind differs")
    prior = root.get("prior_terminal_attempt")
    release_record = root.get("v10_release")
    locator = root.get("network_locator")
    attempt = root.get("new_attempt")
    if not all(
        isinstance(value, Mapping)
        for value in (prior, release_record, locator, attempt)
    ):
        raise DiagnosticRecoveryContractError("recovery plan bindings are absent")
    rebuilt = materialize_plan(
        prior_failure_file=Path(str(prior["path"])),
        release_file=Path(str(release_record["path"])),
        candidate_base_url=str(locator["candidate_base_url"]),
        operator_reported_arp_mac=str(locator["operator_reported_arp_mac"]),
        new_diagnostic_output=Path(str(attempt["new_diagnostic_output"])),
        _require_new_output_absent=require_new_output_absent,
    )
    if contract.canonical_json_bytes(rebuilt) != contract.canonical_json_bytes(root):
        raise DiagnosticRecoveryContractError(
            "recovery plan differs from deterministic deep reconstruction"
        )
    expected_plan_id = contract.sha256(
        {
            key: value
            for key, value in root.items()
            if key not in {"plan_id", "integrity"}
        }
    )
    if root.get("plan_id") != expected_plan_id:
        raise DiagnosticRecoveryContractError("recovery plan ID differs")
    authority = root["two_stage_future_authority"]
    unsatisfied = root.get("unsatisfied_gates")
    if not isinstance(unsatisfied, list) or any(
        not isinstance(item, Mapping) or item.get("satisfied") is not False
        for item in unsatisfied
    ):
        raise DiagnosticRecoveryContractError("unsatisfied execution gates differ")
    return {
        "valid": True,
        "offline_plan_valid": True,
        "execution_ready": False,
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "plan_id": root["plan_id"],
        "canonical_sha256": canonical,
        "prior_failure_sha256": prior["sha256"],
        "prior_failure_canonical_sha256": prior["canonical_sha256"],
        "release_id": release_record["release_id"],
        "release_sha256": release_record["sha256"],
        "release_canonical_sha256": release_record["canonical_sha256"],
        "firmware_binary_sha256": release_record["control_artifact"]["binary"][
            "sha256"
        ],
        "candidate_base_url": locator["candidate_base_url"],
        "arp_is_proof": False,
        "new_boot_required": True,
        "new_diagnostic_output": attempt["new_diagnostic_output"],
        "stage_a_new_boot_intent_sha256": authority["stage_a_new_boot_intent_sha256"],
        "stage_b_diagnostic_intent_template_sha256": authority[
            "stage_b_diagnostic_intent_template_sha256"
        ],
        "copyable_authorization_token_emitted": False,
        "unsatisfied_gates": [str(item["id"]) for item in unsatisfied],
        "get_budget": 4,
        "post_budget": 0,
        "claim_budget": 0,
        "new_boot_operations_exactly": 1,
        "persistent_flash_or_nvs_mutation_budget": 0,
        "diagnostic_api_mutation_budget": 0,
        "retry_allowed": False,
        "live_authorized": False,
        "device_io_performed": False,
        "validation_mode": (
            "PRE_EXECUTION_OUTPUT_ABSENT"
            if require_new_output_absent
            else "STRUCTURAL_POST_EXECUTION_COMPATIBLE"
        ),
        "new_output_absence_gate_required": require_new_output_absent,
    }


def load_plan(path: Path) -> Mapping[str, Any]:
    _, _, root = _read_json(path, label="diagnostic recovery plan")
    return root


def write_new_plan(path: Path, root: Mapping[str, Any]) -> None:
    validate_plan(root, require_new_output_absent=True)
    payload = contract.canonical_json_bytes(root) + b"\n"
    target = Path(os.path.abspath(os.fspath(path)))
    attempt = root.get("new_attempt")
    if not isinstance(attempt, Mapping):
        raise DiagnosticRecoveryContractError("new-attempt binding is absent")
    if target == Path(str(attempt.get("new_diagnostic_output"))):
        raise DiagnosticRecoveryContractError(
            "plan output must differ from the reserved diagnostic output"
        )
    _assert_non_symlink_parent_chain(target, label="plan output")
    target.parent.mkdir(parents=True, exist_ok=True)
    _assert_non_symlink_parent_chain(target, label="plan output")
    try:
        with target.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise DiagnosticRecoveryContractError("plan output already exists") from error
    except OSError as error:
        raise DiagnosticRecoveryContractError(
            f"could not write plan output: {error}"
        ) from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", allow_abbrev=False)
    build.add_argument("--prior-failure", type=Path, required=True)
    build.add_argument("--release", type=Path, required=True)
    build.add_argument("--candidate-base-url", required=True)
    build.add_argument("--operator-reported-arp-mac", required=True)
    build.add_argument("--new-diagnostic-output", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)

    validate = commands.add_parser("validate", allow_abbrev=False)
    validate.add_argument("--plan", type=Path, required=True)
    validate.add_argument(
        "--preflight-output-absent",
        action="store_true",
        help="also require that the one-shot diagnostic output is still absent",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            plan = materialize_plan(
                prior_failure_file=args.prior_failure,
                release_file=args.release,
                candidate_base_url=args.candidate_base_url,
                operator_reported_arp_mac=args.operator_reported_arp_mac,
                new_diagnostic_output=args.new_diagnostic_output,
            )
            write_new_plan(args.output, plan)
            summary = validate_plan(plan, require_new_output_absent=True)
            summary["plan_file"] = str(Path(os.path.abspath(os.fspath(args.output))))
        else:
            summary = validate_plan(
                load_plan(args.plan),
                require_new_output_absent=args.preflight_output_absent,
            )
            summary["plan_file"] = str(Path(os.path.abspath(os.fspath(args.plan))))
    except (
        DiagnosticRecoveryContractError,
        KeyError,
        TypeError,
    ) as error:
        print(f"diagnostic recovery contract error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
