#!/usr/bin/env python3
"""GET-only reconciliation of the rejected, never-executed T4 V4 host run.

This is not an action runner.  It binds the fixed V4 flash, IPv4/MAC,
J2-OFF diagnostic, relay-ON, and final protective relay-OFF receipts before it
opens a socket.  With J2 explicitly confirmed OFF, it reserves one immutable
O_EXCL evidence path and issues exactly two requests: GET status, then GET
report.  It has no POST, relay, serial, flash, reset, recovery, retry, or
display-refresh path.

The success result proves only that the V4 action remained NOT_EXECUTED on the
same ESP32 boot, with zero ARM/EXECUTE requests and zero driver calls.  It
therefore permits a *fresh-identity* successor while permanently tombstoning
the unused V4 action identity; it never authorizes reuse of the V4 action.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v4_once as once,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v4_pack as pack,
)


class T4V4HostRejectionReconciliationError(RuntimeError):
    """Raised when the read-only NOT_EXECUTED reconciliation must stop."""


OUTPUT_ROOT = once._output_root().resolve()  # noqa: SLF001
RECONCILIATION_OUTPUT = (
    OUTPUT_ROOT / "action-01-host-runner-rejection-reconciled.json"
).resolve()
ACTION_OUTPUT = (
    OUTPUT_ROOT / "action-01-position-balanced-atlas.json"
).resolve()
EXPECTED_ACTION = pack.build_report()["actions"][0]
CLAIM_FILE = (
    once._claim_root() / f"{EXPECTED_ACTION['action_id']}.json"  # noqa: SLF001
).resolve()
FIXED_IPV4 = "192.168.1.11"
FIXED_BASE_URL = f"http://{FIXED_IPV4}"
EXPECTED_MAC = "A4-CB-8F-D9-FC-D4"


def _evidence_path(name: str) -> str:
    return str(
        Path(
            ".test-output/hardware/"
            "MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_"
            "SWAP_CONFIRMATION_SUCCESSOR_20260901_V4"
        )
        / name
    ).replace("\\", "/")


FIXED_BINDINGS: dict[str, dict[str, Any]] = {
    "pre_flash_protective_off": {
        "path": _evidence_path("relay-pre-flash-protective-off.json"),
        "bytes": 1_807,
        "file_sha256": (
            "ee57db9c7c2457749312a883702352759ba1ddfa07b2c4104d2d4426ad5a6897"
        ),
        "canonical_integrity_sha256": (
            "2c2f1a4aec9b7d352422600d6ec84bb1bcf07ad80ede4bfe72683c4491775d5b"
        ),
        "integrity_algorithm": "sha256",
    },
    "app_only_single_boot_flash": {
        "path": _evidence_path("app-only-single-boot-flash.json"),
        "bytes": 6_695,
        "file_sha256": (
            "785191a5355372d9c1ae65e40755b0cf412369e24ccfbc61bbee18153bb2c65f"
        ),
        "canonical_integrity_sha256": (
            "8430ce4b911f724d1e5d44c8c5be568e6938977b7ff8ab08a32f58be5623b191"
        ),
        "integrity_algorithm": "sha256-canonical-json-without-integrity",
    },
    "exact_ipv4_mac_binding": {
        "path": _evidence_path("exact-ipv4-mac-binding.json"),
        "bytes": 3_437,
        "file_sha256": (
            "9d3f36c69340d68a873f7832d1add314dad4cbca60033eaed1ba5bbecae2b473"
        ),
        "canonical_integrity_sha256": (
            "5ebcc7a02639cef8b8a64c09f94d1a88260c6c783ba387bfe88aeb8eab50c0f6"
        ),
        "integrity_algorithm": "sha256-canonical-json-without-integrity",
    },
    "j2_off_diagnostic": {
        "path": _evidence_path("j2-off-diagnostic.json"),
        "bytes": 38_945,
        "file_sha256": (
            "c6d694d6ddce8ce62c0ac16a190adf2c63add55b09be1f4a455a1ecc4201a5af"
        ),
        "canonical_integrity_sha256": (
            "23a5f7e87fe78097c94d6508f11038825bb92d7c88b5296df840eeacd7c9434a"
        ),
        "integrity_algorithm": "sha256-canonical-json-without-integrity",
    },
    "pre_action_on": {
        "path": _evidence_path("relay-pre-action-on.json"),
        "bytes": 1_886,
        "file_sha256": (
            "edbdf83bb2672efa59f9f563d4d3c8732b9d126565362b499e71bfe72d7d0460"
        ),
        "canonical_integrity_sha256": (
            "328be356cc6cf8065e85e3339e296a26232a7caee239f6f1a6b01a5723c38a35"
        ),
        "integrity_algorithm": "sha256",
    },
    "post_rejection_protective_off": {
        "path": _evidence_path(
            "relay-post-runner-rejection-protective-off.json"
        ),
        "bytes": 1_807,
        "file_sha256": (
            "4d5eb9b217e56a06a07d99e335df3b36be9d63669e7cae49e20a14b114e2d54b"
        ),
        "canonical_integrity_sha256": (
            "c6f423282e12a47873ad61d4cff8362000836cfe5da6a87d017615e3dcf78565"
        ),
        "integrity_algorithm": "sha256",
    },
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise T4V4HostRejectionReconciliationError(message)


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _parse_time(value: Any, *, label: str) -> datetime:
    _require(isinstance(value, str), f"{label} timestamp differs")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise T4V4HostRejectionReconciliationError(
            f"{label} timestamp differs"
        ) from error
    _require(parsed.tzinfo is not None, f"{label} timestamp is naive")
    return parsed


def _load_bound(label: str) -> tuple[bytes, dict[str, Any]]:
    binding = FIXED_BINDINGS[label]
    path = (REPO_ROOT / binding["path"]).resolve()
    _require(path.is_file() and not path.is_symlink(), f"{label} missing or unsafe")
    payload = path.read_bytes()
    _require(len(payload) == binding["bytes"], f"{label} byte count differs")
    _require(_sha256(payload) == binding["file_sha256"], f"{label} file SHA differs")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise T4V4HostRejectionReconciliationError(
            f"{label} is not UTF-8 JSON"
        ) from error
    _require(isinstance(value, dict), f"{label} JSON root differs")
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    algorithm = binding["integrity_algorithm"]
    key = "canonical_sha256" if algorithm == "sha256" else "sha256"
    _require(
        isinstance(integrity, Mapping)
        and integrity.get("algorithm") == algorithm
        and integrity.get(key) == binding["canonical_integrity_sha256"]
        and _sha256(_canonical(body)) == binding["canonical_integrity_sha256"],
        f"{label} canonical integrity differs",
    )
    return payload, value


def _binding_reference(label: str) -> dict[str, Any]:
    binding = FIXED_BINDINGS[label]
    return {
        "path": binding["path"],
        "bytes": binding["bytes"],
        "file_sha256": binding["file_sha256"],
        "canonical_integrity_sha256": binding["canonical_integrity_sha256"],
    }


def _validate_relay(value: Mapping[str, Any], *, state: str, label: str) -> None:
    authority = value.get("authority")
    _require(
        value.get("kind") == "mf17506-zave-relay-exact-bound-switch-receipt"
        and value.get("channel") == 1
        and value.get("contact_path") == "COM1-NO1"
        and value.get("commanded_state") == state
        and value.get("target_state") == state
        and value.get("target_gate_passed") is True
        and value.get("contact_switch_performed") is True
        and value.get("electrical_state_proven") is False
        and value.get("automatic_retry_performed") is False
        and value.get("automatic_recovery_performed") is False
        and value.get("feedback_command_count") == 1
        and value.get("independent_query_count") == 1
        and value.get("output_write_contract")
        == "O_EXCL_PRE_RESERVED_BEFORE_DEVICE_IO"
        and isinstance(authority, Mapping),
        f"{label} relay semantics differ",
    )
    if state == "OFF":
        _require(
            value.get("off_gate_passed") is True
            and authority.get("basis") == "PROTECTIVE_OFF"
            and authority.get("on_authorized") is False,
            f"{label} protective OFF semantics differ",
        )
    else:
        _require(
            value.get("off_gate_passed") is False
            and authority.get("on_authorized") is True
            and authority.get("authorization_id")
            == "USER_CONTINUE_NEXT_REAL_SCREEN_T4_V4_20260901",
            f"{label} ON authority differs",
        )


def _validate_flash(value: Mapping[str, Any]) -> None:
    binary = value.get("binary")
    constraints = value.get("constraints")
    steps = value.get("steps")
    artifact_bin, _artifact_elf = pack.artifact_paths()
    sealed = pack.ARTIFACTS[pack.STAGE]
    _require(
        value.get("kind") == "mf1750-app-only-single-boot-flash-result"
        and value.get("outcome") == "app_only_write_verify_single_boot_pass"
        and value.get("success") is True
        and value.get("j2_confirmed_off") is True
        and value.get("output_write_contract") == "O_EXCL"
        and isinstance(binary, Mapping)
        and binary.get("bytes") == sealed["bin_bytes"]
        and binary.get("expected_sha256") == sealed["bin_sha256"]
        and binary.get("observed_sha256") == sealed["bin_sha256"]
        and Path(str(binary.get("path"))).resolve() == artifact_bin.resolve()
        and binary.get("preflight_verified") is True
        and isinstance(constraints, Mapping)
        and constraints.get("application_only") is True
        and constraints.get("application_start_count_after_write") == 1
        and constraints.get("bootloader_write") is False
        and constraints.get("partition_table_write") is False
        and constraints.get("nvs_write_or_erase") is False
        and constraints.get("erase_command") is False
        and constraints.get("retry") is False
        and constraints.get("recovery") is False
        and constraints.get("fallback") is False
        and isinstance(steps, list)
        and len(steps) == 2
        and [item.get("name") for item in steps]
        == [
            "write_flash_stay_in_bootloader",
            "verify_flash_then_single_hard_reset",
        ]
        and all(item.get("returncode") == 0 for item in steps),
        "fixed app-only single-boot flash semantics differ",
    )
    flash_text = str(steps[0].get("stdout", {}).get("tail_utf8", ""))
    _require(
        "MAC: a4:cb:8f:d9:fc:d4" in flash_text,
        "flash evidence does not bind expected ESP32 MAC",
    )


def _validate_ip(value: Mapping[str, Any]) -> None:
    _require(
        value.get("kind") == "mf1750-exact-ipv4-mac-binding-attempt-v1"
        and value.get("outcome") == "active_exact_mac_binding_pass"
        and value.get("candidate_ipv4") == FIXED_IPV4
        and value.get("expected_mac") == EXPECTED_MAC
        and value.get("candidate_count") == 1
        and value.get("single_candidate_confirmed") is True
        and value.get("binding_passed") is True
        and value.get("fresh_binding_passed") is True
        and value.get("network_layer_mac_binding_observed") is True
        and value.get("device_application_identity_proven") is False
        and value.get("device_api_requests") == 0
        and value.get("http_requests") == 0
        and value.get("mutation_requests") == 0
        and value.get("visible_refresh_requests") == 0
        and value.get("retry") is False
        and value.get("fallback") is False
        and value.get("scan") is False
        and value.get("output_contract") == "O_EXCL_TERMINAL",
        "fixed IPv4/MAC evidence semantics differ",
    )


def _validate_diagnostic(
    host: Any, value: Mapping[str, Any]
) -> tuple[str, Mapping[str, Any], Mapping[str, Any]]:
    report = pack.build_report()
    artifact = pack.ARTIFACTS[pack.STAGE]
    transcript = value.get("transcript")
    _require(
        value.get("kind")
        == (
            "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-"
            "swap-confirmation-successor-v4-j2-off-diagnostic"
        )
        and value.get("outcome") == "j2_off_diagnostic_pass"
        and value.get("j2_confirmed_off") is True
        and value.get("base_url") == FIXED_BASE_URL
        and value.get("campaign_id") == pack.CONFIG.campaign_id
        and value.get("test_id") == pack.CONFIG.test_id
        and value.get("contract_id") == report["contract_id"]
        and value.get("build_tag") == pack.CONFIG.build_tag
        and value.get("local_artifact_binding")
        == {
            "bound": True,
            "bin": {
                "bytes": artifact["bin_bytes"],
                "sha256": artifact["bin_sha256"],
            },
            "elf": {
                "bytes": artifact["elf_bytes"],
                "sha256": artifact["elf_sha256"],
            },
        }
        and value.get("fresh_cursor_key_absent") is True
        and value.get("campaign_boot_key_present_and_current") is True
        and value.get("next_ordinal") == 1
        and value.get("network") == {"get": 4, "post": 0}
        and value.get("permanent_claims_created") == 0
        and value.get("visible_refreshes") == 0
        and value.get("output_write_contract") == "O_EXCL"
        and value.get("no_retry") is True
        and value.get("no_recovery") is True
        and value.get("no_autochain") is True
        and isinstance(transcript, list)
        and [
            (item.get("method"), item.get("endpoint"), item.get("status"))
            for item in transcript
        ]
        == [
            ("GET", "version", 200),
            ("GET", "manifest", 200),
            ("GET", "status", 200),
            ("GET", "report", 200),
        ],
        "fixed J2-OFF diagnostic semantics differ",
    )
    version, manifest, status, no_execute = (
        item.get("response") for item in transcript
    )
    _require(
        all(
            isinstance(item, Mapping)
            for item in (version, manifest, status, no_execute)
        ),
        "fixed J2-OFF diagnostic response root differs",
    )
    host._validate_version(version)  # noqa: SLF001
    host._validate_manifest(manifest)  # noqa: SLF001
    boot_nonce = host._validate_ready_status(  # noqa: SLF001
        status, 1, expected_busy=0
    )
    # Ordinal 1 has no predecessor.  The shared prior-terminal validator is
    # intentionally inapplicable here; this is the established fresh report
    # validator used by the other one-action campaigns.
    host.v3.v1._validate_fresh_no_execute_report(  # noqa: SLF001
        no_execute, boot_nonce
    )
    _require(
        value.get("boot_nonce") == boot_nonce
        and value.get("status") == status
        and value.get("report") == no_execute,
        "fixed J2-OFF diagnostic boot/report binding differs",
    )
    return boot_nonce, status, no_execute


def _validate_local_authorities() -> dict[str, Any]:
    """Validate all immutable inputs before O_EXCL or network access."""

    once.dry_validate()
    values: dict[str, dict[str, Any]] = {}
    for label in FIXED_BINDINGS:
        _payload, values[label] = _load_bound(label)
    _validate_relay(
        values["pre_flash_protective_off"],
        state="OFF",
        label="pre-flash protective OFF",
    )
    _validate_flash(values["app_only_single_boot_flash"])
    _validate_ip(values["exact_ipv4_mac_binding"])
    _validate_relay(values["pre_action_on"], state="ON", label="pre-action ON")
    _validate_relay(
        values["post_rejection_protective_off"],
        state="OFF",
        label="post-rejection protective OFF",
    )
    host = once.configure()
    boot_nonce, initial_status, initial_report = _validate_diagnostic(
        host, values["j2_off_diagnostic"]
    )

    pre_flash_off_at = _parse_time(
        values["pre_flash_protective_off"].get("switched_at"),
        label="pre-flash OFF",
    )
    flash_started_at = _parse_time(
        values["app_only_single_boot_flash"].get("started_at"),
        label="flash start",
    )
    flash_finished_at = _parse_time(
        values["app_only_single_boot_flash"].get("finished_at"),
        label="flash finish",
    )
    ip_finished_at = _parse_time(
        values["exact_ipv4_mac_binding"].get("finished_at"),
        label="IPv4/MAC finish",
    )
    diagnostic_at = _parse_time(
        values["j2_off_diagnostic"].get("created_at"),
        label="J2-OFF diagnostic",
    )
    on_at = _parse_time(values["pre_action_on"].get("switched_at"), label="ON")
    final_off_at = _parse_time(
        values["post_rejection_protective_off"].get("switched_at"),
        label="post-rejection OFF",
    )
    # The fixed receipt is named ``relay-pre-flash-protective-off`` but its
    # sealed timestamp is after the application-only flash.  Do not turn that
    # filename into an unearned temporal claim: the flash result itself is the
    # authority that J2 was confirmed OFF for flashing.  The relay receipt is
    # instead used exactly where its timestamp places it, before the J2-OFF
    # diagnostic and before the later ON/OFF pair.
    _require(
        flash_started_at
        < flash_finished_at
        < ip_finished_at
        < pre_flash_off_at
        < diagnostic_at
        < on_at
        < final_off_at,
        "fixed flash/IP/diagnostic/ON/OFF chronology differs",
    )
    _require(
        not CLAIM_FILE.exists()
        and not CLAIM_FILE.is_symlink()
        and not ACTION_OUTPUT.exists()
        and not ACTION_OUTPUT.is_symlink(),
        "V4 claim or action result exists; host-rejection reconciliation is invalid",
    )
    return {
        "host": host,
        "boot_nonce": boot_nonce,
        "initial_status": deepcopy(dict(initial_status)),
        "initial_report": deepcopy(dict(initial_report)),
        "bindings": {
            label: _binding_reference(label) for label in FIXED_BINDINGS
        },
        "action": deepcopy(EXPECTED_ACTION),
        "firmware_sha256": pack.ARTIFACTS[pack.STAGE]["bin_sha256"],
        "claim_path": str(CLAIM_FILE),
        "action_output_path": str(ACTION_OUTPUT),
    }


def _reserve(path: Path) -> int:
    resolved = Path(path).resolve()
    _require(
        resolved == RECONCILIATION_OUTPUT,
        "reconciliation output path is not the fixed O_EXCL path",
    )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        return os.open(resolved, flags, 0o444)
    except FileExistsError as error:
        raise T4V4HostRejectionReconciliationError(
            "reconciliation output already exists; no retry is permitted"
        ) from error


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    body = deepcopy(dict(value))
    _require("integrity" not in body, "integrity is reserved")
    return {
        **body,
        "integrity": {
            "algorithm": "sha256-canonical-json-without-integrity",
            "sha256": _sha256(_canonical(body)),
        },
    }


def _commit(descriptor: int, value: Mapping[str, Any]) -> None:
    payload = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    offset = 0
    while offset < len(payload):
        offset += os.write(descriptor, payload[offset:])
    os.fsync(descriptor)


def _request_get(
    requester: Any,
    transcript: list[dict[str, Any]],
    endpoint: str,
    *,
    timeout: float,
) -> Mapping[str, Any]:
    _require(endpoint in {"status", "report"}, "non-read-only endpoint rejected")
    path = f"{pack.CONFIG.base_route}/{endpoint}"
    status_code, response = requester(
        FIXED_BASE_URL,
        path,
        method="GET",
        headers=None,
        timeout=timeout,
    )
    transcript.append(
        {
            "method": "GET",
            "endpoint": endpoint,
            "path": path,
            "headers": {},
            "status": status_code,
            "response": deepcopy(dict(response))
            if isinstance(response, Mapping)
            else None,
        }
    )
    _require(status_code == 200, f"GET {endpoint} HTTP status differs")
    _require(isinstance(response, Mapping), f"GET {endpoint} response differs")
    return response


def reconcile_host_rejection_once(
    *,
    confirm_j2_off: bool,
    output: Path = RECONCILIATION_OUTPUT,
    requester: Any = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Seal one two-GET proof that V4 never reached device mutation."""

    _require(confirm_j2_off is True, "reconciliation requires explicit J2-OFF")
    _require(timeout > 0, "timeout must be positive")
    context = _validate_local_authorities()
    descriptor = _reserve(Path(output))
    transcript: list[dict[str, Any]] = []
    try:
        try:
            selected_requester = requester or context["host"]._diagnostic_http_request  # noqa: SLF001
            status = _request_get(
                selected_requester, transcript, "status", timeout=timeout
            )
            no_execute = _request_get(
                selected_requester, transcript, "report", timeout=timeout
            )
            host = context["host"]
            boot_nonce = host._validate_ready_status(  # noqa: SLF001
                status, 1, expected_busy=0
            )
            host.v3.v1._validate_fresh_no_execute_report(  # noqa: SLF001
                no_execute, boot_nonce
            )
            _require(
                boot_nonce == context["boot_nonce"]
                and status == context["initial_status"]
                and no_execute == context["initial_report"],
                "live NOT_EXECUTED state differs from fixed same-boot diagnostic",
            )
            _require(
                status.get("arm_request_count") == 0
                and status.get("execute_request_count") == 0
                and status.get("total_driver_call_count") == 0
                and status.get("current_action") is None
                and status.get("phase_name") == "READY"
                and no_execute.get("terminal_state") == "NOT_EXECUTED"
                and no_execute.get("driver_called") is False
                and no_execute.get("driver_call_count_for_action") == 0
                and no_execute.get("total_driver_call_count") == 0
                and no_execute.get("action_id") is None
                and no_execute.get("descriptor_id") is None,
                "live device counters do not prove NOT_EXECUTED",
            )
            _require(
                not CLAIM_FILE.exists()
                and not CLAIM_FILE.is_symlink()
                and not ACTION_OUTPUT.exists()
                and not ACTION_OUTPUT.is_symlink(),
                "V4 claim or action result appeared during reconciliation",
            )
            evidence = _seal(
                {
                    "schema_version": 1,
                    "kind": (
                        "mf1750-raw-p16-crossover-t4-active-header-ca-r20-"
                        "swap-confirmation-successor-v4-host-runner-rejection-"
                        "not-executed-reconciliation"
                    ),
                    "created_at": _now(),
                    "outcome": "not_executed_reconciled_read_only",
                    "terminal_state": "NOT_EXECUTED",
                    "campaign_id": pack.CONFIG.campaign_id,
                    "contract_id": pack.build_report()["contract_id"],
                    "descriptor_id": context["action"]["descriptor_id"],
                    "action_id": context["action"]["action_id"],
                    "firmware_sha256": context["firmware_sha256"],
                    "boot_nonce": boot_nonce,
                    "action": context["action"],
                    "fixed_predecessor_bindings": context["bindings"],
                    "status": deepcopy(dict(status)),
                    "terminal_report": deepcopy(dict(no_execute)),
                    "transcript": transcript,
                    "network": {"get": 2, "post": 0},
                    "rejected_host_run_network": {"get": 0, "post": 0},
                    "host_rejected_before_any_network_request": True,
                    "network_requests": 0,
                    "permanent_claims_created": 0,
                    "arm_requests": 0,
                    "execute_requests": 0,
                    "same_boot_as_j2_off_diagnostic": True,
                    "same_boot": True,
                    "w9_clean_white_remains_valid": True,
                    "v4_action_must_not_be_retried": True,
                    "j2_confirmed_off_for_reconciliation": True,
                    "relay_state_source": "fixed_post_rejection_protective_off_receipt",
                    "relay_accessed_by_reconciliation": False,
                    "serial_or_com_accessed": False,
                    "firmware_flashed": False,
                    "reset_requested": False,
                    "display_refresh_requested": False,
                    "mutation_requests_sent": 0,
                    "arm_request_count": 0,
                    "execute_request_count": 0,
                    "driver_called": False,
                    "driver_call_count_for_action": 0,
                    "total_driver_call_count": 0,
                    "visible_refreshes": 0,
                    "permanent_claim_path": context["claim_path"],
                    "permanent_claim_absent_before_and_after": True,
                    "action_result_path": context["action_output_path"],
                    "action_result_absent_before_and_after": True,
                    "host_rejection_reason_cryptographically_claimed": False,
                    "host_rejection_classification_basis": (
                        "fixed receipt filename plus absent claim/result and live zero "
                        "device mutation counters"
                    ),
                    "safe_supersession": {
                        "admissible": True,
                        "fresh_identity_required": True,
                        "v4_action_id_must_be_tombstoned": True,
                        "v4_action_must_not_be_retried": True,
                        "v4_action_must_not_be_reused": True,
                        "white_recovery_required_for_v4_mutation": False,
                        "basis": (
                            "same-boot READY/NOT_EXECUTED with zero ARM, EXECUTE, "
                            "driver, POST, and visible-refresh counts"
                        ),
                    },
                    "output_write_contract": "O_EXCL_RESERVED_BEFORE_FIRST_GET",
                    "no_retry": True,
                    "no_recovery": True,
                    "no_autochain": True,
                }
            )
        except Exception as error:
            failure = _seal(
                {
                    "schema_version": 1,
                    "kind": (
                        "mf1750-raw-p16-crossover-t4-active-header-ca-r20-"
                        "swap-confirmation-successor-v4-host-runner-rejection-"
                        "reconciliation-failure"
                    ),
                    "created_at": _now(),
                    "outcome": "reconciliation_failed_closed_read_only",
                    "error": str(error),
                    "firmware_sha256": context["firmware_sha256"],
                    "boot_nonce": context["boot_nonce"],
                    "action": context["action"],
                    "fixed_predecessor_bindings": context["bindings"],
                    "transcript": transcript,
                    "network": {
                        "get": sum(
                            item.get("method") == "GET" for item in transcript
                        ),
                        "post": 0,
                    },
                    "j2_confirmed_off_for_reconciliation": True,
                    "relay_accessed_by_reconciliation": False,
                    "serial_or_com_accessed": False,
                    "firmware_flashed": False,
                    "reset_requested": False,
                    "display_refresh_requested": False,
                    "mutation_requests_sent": 0,
                    "safe_supersession": {"admissible": False},
                    "output_write_contract": "O_EXCL_RESERVED_BEFORE_FIRST_GET",
                    "no_retry": True,
                    "no_recovery": True,
                    "no_autochain": True,
                }
            )
            _commit(descriptor, failure)
            raise T4V4HostRejectionReconciliationError(
                "reconciliation failed and was sealed; no retry is permitted"
            ) from error
        _commit(descriptor, evidence)
        return evidence
    finally:
        os.close(descriptor)


def validate_reconciliation(
    path: Path = RECONCILIATION_OUTPUT,
) -> tuple[dict[str, Any], bytes]:
    """Deep-validate the fixed success evidence for a fresh successor."""

    resolved = Path(path).resolve()
    _require(resolved == RECONCILIATION_OUTPUT, "reconciliation path differs")
    _require(resolved.is_file() and not resolved.is_symlink(), "reconciliation missing")
    payload = resolved.read_bytes()
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise T4V4HostRejectionReconciliationError(
            "reconciliation is not UTF-8 JSON"
        ) from error
    _require(isinstance(value, dict), "reconciliation root differs")
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    canonical_sha = _sha256(_canonical(body))
    _require(
        isinstance(integrity, Mapping)
        and integrity.get("algorithm")
        == "sha256-canonical-json-without-integrity"
        and integrity.get("sha256") == canonical_sha,
        "reconciliation canonical integrity differs",
    )
    context = _validate_local_authorities()
    transcript = value.get("transcript")
    status = value.get("status")
    no_execute = value.get("terminal_report")
    _require(
        value.get("kind")
        == (
            "mf1750-raw-p16-crossover-t4-active-header-ca-r20-"
            "swap-confirmation-successor-v4-host-runner-rejection-"
            "not-executed-reconciliation"
        )
        and value.get("outcome") == "not_executed_reconciled_read_only"
        and value.get("terminal_state") == "NOT_EXECUTED"
        and value.get("campaign_id") == pack.CONFIG.campaign_id
        and value.get("contract_id") == pack.build_report()["contract_id"]
        and value.get("descriptor_id") == context["action"]["descriptor_id"]
        and value.get("action_id") == context["action"]["action_id"]
        and value.get("firmware_sha256") == context["firmware_sha256"]
        and value.get("boot_nonce") == context["boot_nonce"]
        and value.get("action") == context["action"]
        and value.get("fixed_predecessor_bindings") == context["bindings"]
        and value.get("network") == {"get": 2, "post": 0}
        and value.get("rejected_host_run_network") == {"get": 0, "post": 0}
        and value.get("host_rejected_before_any_network_request") is True
        and value.get("network_requests") == 0
        and value.get("permanent_claims_created") == 0
        and value.get("arm_requests") == 0
        and value.get("execute_requests") == 0
        and value.get("mutation_requests_sent") == 0
        and value.get("arm_request_count") == 0
        and value.get("execute_request_count") == 0
        and value.get("driver_called") is False
        and value.get("driver_call_count_for_action") == 0
        and value.get("total_driver_call_count") == 0
        and value.get("visible_refreshes") == 0
        and value.get("same_boot_as_j2_off_diagnostic") is True
        and value.get("same_boot") is True
        and value.get("w9_clean_white_remains_valid") is True
        and value.get("v4_action_must_not_be_retried") is True
        and value.get("permanent_claim_absent_before_and_after") is True
        and value.get("action_result_absent_before_and_after") is True
        and value.get("relay_accessed_by_reconciliation") is False
        and value.get("serial_or_com_accessed") is False
        and value.get("firmware_flashed") is False
        and value.get("reset_requested") is False
        and value.get("display_refresh_requested") is False
        and value.get("output_write_contract")
        == "O_EXCL_RESERVED_BEFORE_FIRST_GET"
        and value.get("no_retry") is True
        and value.get("no_recovery") is True
        and value.get("no_autochain") is True
        and value.get("safe_supersession")
        == {
            "admissible": True,
            "fresh_identity_required": True,
            "v4_action_id_must_be_tombstoned": True,
            "v4_action_must_not_be_retried": True,
            "v4_action_must_not_be_reused": True,
            "white_recovery_required_for_v4_mutation": False,
            "basis": (
                "same-boot READY/NOT_EXECUTED with zero ARM, EXECUTE, "
                "driver, POST, and visible-refresh counts"
            ),
        }
        and isinstance(transcript, list)
        and [
            (item.get("method"), item.get("endpoint"), item.get("status"))
            for item in transcript
        ]
        == [("GET", "status", 200), ("GET", "report", 200)]
        and isinstance(status, Mapping)
        and isinstance(no_execute, Mapping)
        and status == context["initial_status"]
        and no_execute == context["initial_report"],
        "reconciliation success envelope differs",
    )
    boot_nonce = context["host"]._validate_ready_status(  # noqa: SLF001
        status, 1, expected_busy=0
    )
    context["host"].v3.v1._validate_fresh_no_execute_report(  # noqa: SLF001
        no_execute, boot_nonce
    )
    _require(boot_nonce == context["boot_nonce"], "reconciliation boot differs")
    value["_validated_file_binding"] = {
        "path": str(resolved),
        "bytes": len(payload),
        "file_sha256": _sha256(payload),
        "canonical_integrity_sha256": canonical_sha,
    }
    return value, payload


def dry_validate() -> dict[str, Any]:
    context = _validate_local_authorities()
    return {
        "result": "PASS",
        "offline_only": True,
        "hardware_accessed": False,
        "network_requests": 0,
        "relay_accessed": False,
        "serial_or_com_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "fixed_base_url": FIXED_BASE_URL,
        "boot_nonce": context["boot_nonce"],
        "action_id": context["action"]["action_id"],
        "fixed_predecessor_bindings": context["bindings"],
        "reconciliation_output": str(RECONCILIATION_OUTPUT),
        "network_if_run": {"get": 2, "post": 0},
        "terminal_state_required": "NOT_EXECUTED",
        "fresh_successor_identity_required": True,
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("dry-validate")
    live = sub.add_parser("reconcile", allow_abbrev=False)
    live.add_argument("--confirm-j2-off", action="store_true", required=True)
    live.add_argument("--timeout", type=float, default=15.0)
    sub.add_parser("validate-evidence")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "dry-validate":
            result = dry_validate()
        elif args.command == "reconcile":
            result = reconcile_host_rejection_once(
                confirm_j2_off=args.confirm_j2_off,
                timeout=args.timeout,
            )
        else:
            value, _payload = validate_reconciliation()
            result = {
                "result": "PASS",
                "outcome": value["outcome"],
                "terminal_state": value["terminal_state"],
                "network": value["network"],
                "safe_supersession": value["safe_supersession"],
                "file_binding": value["_validated_file_binding"],
            }
    except (ValueError, RuntimeError) as error:
        print(f"T4 V4 host-rejection reconciliation error: {error}")
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
