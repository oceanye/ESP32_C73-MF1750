#!/usr/bin/env python3
"""Read-only terminal reconciliation for the already-consumed T4 V3 action.

This is deliberately not another action runner.  It first validates the fixed
O_EXCL consumed-failure record and its permanent claim, then reserves one fixed
O_EXCL output and performs exactly four GETs (version, manifest, status,
report).  It has no POST, retry, recovery, relay, serial, flash, reset, or
refresh path.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
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
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v3_once as once,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v3_pack as pack,
)


class T4V3TerminalSalvageError(RuntimeError):
    """Raised when reconciliation must stop closed."""


SOURCE_FAILURE = (
    once._output_root() / "action-01-position-balanced-atlas.json"  # noqa: SLF001
).resolve()
CLAIM_FILE = (
    once._claim_root()  # noqa: SLF001
    / f"{pack.build_report()['actions'][0]['action_id']}.json"
).resolve()
SALVAGE_OUTPUT = (
    once._output_root() / "action-01-terminal-read-only-salvage.json"  # noqa: SLF001
).resolve()
RECONCILED_OUTPUT = (
    once._output_root()
    / "action-01-terminal-read-only-salvage-reconciled.json"  # noqa: SLF001
).resolve()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise T4V3TerminalSalvageError(message)


def _load_json(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    _require(path.is_file() and not path.is_symlink(), f"{label} missing or unsafe")
    payload = path.read_bytes()
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise T4V3TerminalSalvageError(f"{label} is not JSON") from error
    _require(isinstance(value, dict), f"{label} root differs")
    return payload, value


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _verify_integrity(value: Mapping[str, Any], *, label: str) -> str:
    body = deepcopy(dict(value))
    integrity = body.pop("integrity", None)
    _require(
        isinstance(integrity, Mapping)
        and integrity.get("algorithm") == "sha256-canonical-json-without-integrity",
        f"{label} integrity envelope differs",
    )
    observed = hashlib.sha256(_canonical(body)).hexdigest()
    _require(integrity.get("sha256") == observed, f"{label} integrity differs")
    return observed


def _validate_source_and_claim(host: Any) -> dict[str, Any]:
    """Validate every local authority before an output is reserved or a GET occurs."""

    once.dry_validate()
    expected_action = deepcopy(host.base.runner.ACTIONS[0])
    expected_firmware = pack.ARTIFACTS[pack.STAGE]["bin_sha256"]

    source_payload, source = _load_json(SOURCE_FAILURE, label="T4 V3 consumed failure")
    source_integrity = _verify_integrity(source, label="T4 V3 consumed failure")
    _require(
        source.get("kind")
        == (
            "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v3-consumed-failure"
        )
        and source.get("outcome") == "terminal_report_read_error"
        and source.get("terminal_report") is None
        and source.get("terminal_report_strictly_validated") is False,
        "source is not the fixed terminal-report read failure",
    )
    _require(source.get("action") == expected_action, "source action differs")
    _require(source.get("firmware_sha256") == expected_firmware, "source firmware differs")
    _require(
        source.get("network") == {"get": 5, "arm_post": 1, "execute_post": 1},
        "source request counts differ",
    )
    _require(
        source.get("claim_state") == "permanently_consumed"
        and source.get("action_must_not_be_retried") is True
        and source.get("no_retry") is True
        and source.get("no_recovery") is True
        and source.get("no_autochain") is True,
        "source no-retry envelope differs",
    )

    transcript = source.get("transcript")
    _require(isinstance(transcript, list) and len(transcript) == 7, "source transcript differs")
    expected_wire = [
        ("GET", "version"),
        ("GET", "manifest"),
        ("GET", "status"),
        ("GET", "report"),
        ("POST", "arm"),
        ("POST", "execute"),
        ("GET", "report"),
    ]
    _require(
        [(item.get("method"), item.get("endpoint")) for item in transcript]
        == expected_wire,
        "source transcript order differs",
    )
    for index, wanted_status in enumerate((200, 200, 200, 200, 201, 202)):
        _require(transcript[index].get("status") == wanted_status, "source HTTP status differs")
    _require(
        transcript[-1].get("status") is None
        and transcript[-1].get("response") is None
        and "timed out" in str(transcript[-1].get("observation_error", "")),
        "source terminal read error differs",
    )

    version, manifest, initial_status, initial_report = (
        transcript[index]["response"] for index in range(4)
    )
    host._validate_version(version)  # noqa: SLF001
    host._validate_manifest(manifest)  # noqa: SLF001
    boot_nonce = host._validate_ready_status(  # noqa: SLF001
        initial_status, 1, expected_busy=1
    )
    host.v3.v1._validate_fresh_no_execute_report(  # noqa: SLF001
        initial_report, boot_nonce
    )
    _require(source.get("boot_nonce") == boot_nonce, "source boot nonce differs")

    arm = transcript[4]["response"]
    execute = transcript[5]["response"]
    for label, value in (("ARM", arm), ("EXECUTE", execute)):
        _require(
            isinstance(value, Mapping)
            and value.get("accepted") is True
            and value.get("boot_nonce") == boot_nonce
            and value.get("action_id") == expected_action["action_id"]
            and value.get("descriptor_id") == expected_action["descriptor_id"]
            and value.get("ordinal") == 1,
            f"source {label} response differs",
        )
    _require(
        arm.get("armed") is True
        and isinstance(arm.get("arm_nonce"), str)
        and execute.get("execute_consumed") is True
        and execute.get("job_id") == 1,
        "source consumed mutation proof differs",
    )

    claim_payload, claim = _load_json(CLAIM_FILE, label="T4 V3 permanent claim")
    claim_integrity = _verify_integrity(claim, label="T4 V3 permanent claim")
    claim_sha256 = hashlib.sha256(claim_payload).hexdigest()
    _require(
        claim.get("kind")
        == (
            "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v3-permanent-claim"
        )
        and claim.get("state") == "claimed_before_first_mutation"
        and claim.get("action") == expected_action
        and claim.get("boot_nonce") == boot_nonce
        and claim.get("firmware_sha256") == expected_firmware
        and claim.get("no_retry") is True
        and claim.get("no_recovery") is True
        and claim.get("no_autochain") is True,
        "permanent claim semantics differ",
    )
    _require(Path(source.get("claim_file", "")).resolve() == CLAIM_FILE, "source claim path differs")
    _require(source.get("claim_file_sha256") == claim_sha256, "source claim SHA differs")
    _require(source.get("claim_integrity") == claim["integrity"], "source claim integrity differs")
    return {
        "boot_nonce": boot_nonce,
        "action": expected_action,
        "firmware_sha256": expected_firmware,
        "source": source,
        "source_binding": {
            "path": str(SOURCE_FAILURE),
            "bytes": len(source_payload),
            "file_sha256": hashlib.sha256(source_payload).hexdigest(),
            "canonical_integrity_sha256": source_integrity,
            "outcome": source["outcome"],
        },
        "claim": claim,
        "claim_binding": {
            "path": str(CLAIM_FILE),
            "bytes": len(claim_payload),
            "file_sha256": claim_sha256,
            "canonical_integrity_sha256": claim_integrity,
        },
    }


def _validate_terminal_status(
    host: Any,
    status: Mapping[str, Any],
    report: Mapping[str, Any],
    *,
    boot_nonce: str,
) -> str:
    host.base.runner._identity(status, kind_suffix="status")  # noqa: SLF001
    common = {
        "boot_nonce": boot_nonce,
        "cursor_valid": True,
        "campaign_boot_key_present": True,
        "campaign_boot_matches_current": True,
        "arm_request_count": 1,
        "execute_request_count": 1,
        "execute_pending": False,
        "rst": 0,
        "cs": 0,
        "cs2": 0,
    }
    for key, wanted in common.items():
        _require(status.get(key) == wanted, f"terminal status {key} differs")
    _require(status.get("busy") in (0, 1), "terminal status BUSY differs")

    terminal_state = report.get("terminal_state")
    if terminal_state == "COMPLETE":
        host.v3._validate_complete_report(report, 1, boot_nonce)  # noqa: SLF001
        exact = {
            "state": "complete",
            "phase": 0,
            "phase_name": "READY",
            "next_ordinal": 2,
            "campaign_complete": True,
            "total_driver_call_count": 1,
            "current_action": None,
            "cursor_raw": 2,
            "persistent_key_present": True,
        }
        for key, wanted in exact.items():
            _require(status.get(key) == wanted, f"COMPLETE status {key} differs")
        return "complete_salvaged_read_only"

    _require(terminal_state == "FAULT", "terminal state is neither COMPLETE nor FAULT")
    action = host.base.runner.ACTIONS[0]
    host.base.runner._identity(report, kind_suffix="report")  # noqa: SLF001
    driver_called = report.get("driver_called")
    _require(driver_called in (False, True), "FAULT driver_called differs")
    expected_count = 1 if driver_called else 0
    report_exact = {
        "boot_nonce": boot_nonce,
        "valid": bool(driver_called),
        "result": False,
        "ordinal": 1,
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "role": action["role"],
        "round": action["round"],
        "branch": action["branch"],
        "driver_call_count_for_action": expected_count,
        "total_driver_call_count": expected_count,
        "phase": 3,
        "phase_name": "FAULT",
        "next_ordinal": 1,
        "no_retry": True,
        "no_recovery": True,
    }
    for key, wanted in report_exact.items():
        _require(report.get(key) == wanted, f"FAULT report {key} differs")
    _require(isinstance(report.get("error"), str) and bool(report["error"]), "FAULT error differs")
    status_exact = {
        "state": "fault_locked",
        "phase": 3,
        "phase_name": "FAULT",
        "next_ordinal": 1,
        "campaign_complete": False,
        "total_driver_call_count": expected_count,
        "current_action": action,
        "cursor_raw": 769,
        "persistent_key_present": True,
    }
    for key, wanted in status_exact.items():
        _require(status.get(key) == wanted, f"FAULT status {key} differs")
    if driver_called:
        driver = report.get("driver")
        source = pack.build_report()["actions"][0]
        _require(
            isinstance(driver, Mapping)
            and driver.get("valid") is True
            and driver.get("running") is False,
            "FAULT driver evidence differs",
        )
        driver_exact = {
            "operation_id": 1,
            "spi_hz": 1_000_000,
            "input_fnv1a": source["frame"]["fnv1a"],
            "cs1_dtm_fnv1a": source["cs1_dtm"]["fnv1a"],
            "cs2_dtm_fnv1a": source["cs2_dtm"]["fnv1a"],
        }
        for key, wanted in driver_exact.items():
            _require(driver.get(key) == wanted, f"FAULT driver {key} differs")
        _require(
            driver.get("sequence_ok") is False
            and isinstance(driver.get("failure_stage"), str)
            and driver.get("failure_stage") != "none",
            "FAULT driver failure semantics differ",
        )
        safe_finish = driver.get("safe_finish")
        final_gpio = (
            safe_finish.get("final_gpio")
            if isinstance(safe_finish, Mapping)
            else None
        )
        _require(
            isinstance(safe_finish, Mapping)
            and all(
                safe_finish.get(key) in (0, 1)
                for key in (
                    "busy_before_pins_low",
                    "busy_after_pins_low",
                    "busy_after_5ms",
                )
            )
            and isinstance(final_gpio, Mapping)
            and final_gpio.get("rst") == 0
            and final_gpio.get("cs") == 0
            and final_gpio.get("cs2") == 0
            and final_gpio.get("busy") in (0, 1),
            "FAULT safe-finish evidence differs",
        )
    else:
        _require(report.get("driver") is None, "FAULT no-driver evidence differs")
    return "fault_salvaged_read_only"


def _reserve(path: Path) -> int:
    _require(path.resolve() == SALVAGE_OUTPUT, "salvage output path differs")
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        return os.open(path, flags, 0o600)
    except FileExistsError as error:
        raise T4V3TerminalSalvageError(
            "terminal salvage output already exists; no retry is permitted"
        ) from error


def _reserve_reconciled(path: Path) -> int:
    _require(path.resolve() == RECONCILED_OUTPUT, "reconciled output path differs")
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        return os.open(path, flags, 0o600)
    except FileExistsError as error:
        raise T4V3TerminalSalvageError(
            "reconciled terminal output already exists; no replay is permitted"
        ) from error


def _seal(host: Any, value: Mapping[str, Any]) -> dict[str, Any]:
    return host.base.runner._seal(value)  # noqa: SLF001


def _commit(descriptor: int, value: Mapping[str, Any]) -> None:
    payload = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    os.write(descriptor, payload)
    os.fsync(descriptor)


def salvage_terminal_once(
    base_url: str,
    *,
    confirm_j2_off: bool,
    output: Path = SALVAGE_OUTPUT,
    requester: Any = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Perform the one frozen four-GET reconciliation and seal its outcome."""

    _require(confirm_j2_off is True, "terminal salvage requires explicit J2-OFF")
    _require(timeout > 0, "timeout must be positive")
    host = once.configure()
    context = _validate_source_and_claim(host)
    descriptor = _reserve(Path(output))
    transcript: list[dict[str, Any]] = []
    terminal: Mapping[str, Any] | None = None
    try:
        selected_requester = requester or host._diagnostic_http_request  # noqa: SLF001
        origin = host._diagnostic_origin(base_url)  # noqa: SLF001
        try:
            version = host.base.runner._request(  # noqa: SLF001
                selected_requester, transcript, origin, "version", timeout=timeout
            )
            manifest = host.base.runner._request(  # noqa: SLF001
                selected_requester, transcript, origin, "manifest", timeout=timeout
            )
            status = host.base.runner._request(  # noqa: SLF001
                selected_requester, transcript, origin, "status", timeout=timeout
            )
            terminal = host.base.runner._request(  # noqa: SLF001
                selected_requester, transcript, origin, "report", timeout=timeout
            )
            host._validate_version(version)  # noqa: SLF001
            host._validate_manifest(manifest)  # noqa: SLF001
            _require(
                version.get("build_tag") == pack.CONFIG.build_tag
                and manifest.get("build_tag") == pack.CONFIG.build_tag,
                "live V3 build identity differs",
            )
            outcome = _validate_terminal_status(
                host,
                status,
                terminal,
                boot_nonce=context["boot_nonce"],
            )
            evidence = _seal(
                host,
                {
                    "schema_version": 1,
                    "kind": (
                        "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-"
                        "swap-confirmation-successor-v3-terminal-read-only-salvage"
                    ),
                    "created_at": host.base.runner._now(),  # noqa: SLF001
                    "firmware_sha256": context["firmware_sha256"],
                    "boot_nonce": context["boot_nonce"],
                    "action": deepcopy(context["action"]),
                    "source_consumed_failure_binding": context["source_binding"],
                    "claim_binding": context["claim_binding"],
                    "claim_integrity": deepcopy(context["claim"]["integrity"]),
                    "claim_state": "permanently_consumed",
                    "status": deepcopy(dict(status)),
                    "terminal_report": deepcopy(dict(terminal)),
                    "transcript": transcript,
                    "network": {"get": 4, "post": 0},
                    "outcome": outcome,
                    "terminal_state": terminal["terminal_state"],
                    "visible_refreshes": (
                        1 if terminal["terminal_state"] == "COMPLETE" else 0
                    ),
                    "terminal_report_strictly_validated": True,
                    "output_write_contract": "O_EXCL_RESERVED_BEFORE_FIRST_GET",
                    "claim_state_reconciled_without_mutation": True,
                    "action_must_not_be_retried": True,
                    "no_retry": True,
                    "no_recovery": True,
                    "no_autochain": True,
                    "hardware_mutation_requested": False,
                    "relay_accessed": False,
                    "serial_or_com_accessed": False,
                    "firmware_flashed": False,
                    "display_refresh_requested": False,
                },
            )
        except Exception as error:
            failure = _seal(
                host,
                {
                    "schema_version": 1,
                    "kind": (
                        "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-"
                        "swap-confirmation-successor-v3-terminal-read-only-salvage-failure"
                    ),
                    "created_at": host.base.runner._now(),  # noqa: SLF001
                    "firmware_sha256": context["firmware_sha256"],
                    "boot_nonce": context["boot_nonce"],
                    "action": deepcopy(context["action"]),
                    "source_consumed_failure_binding": context["source_binding"],
                    "claim_binding": context["claim_binding"],
                    "terminal_report": (
                        deepcopy(dict(terminal))
                        if isinstance(terminal, Mapping)
                        else None
                    ),
                    "transcript": transcript,
                    "network": {
                        "get": sum(item.get("method") == "GET" for item in transcript),
                        "post": 0,
                    },
                    "outcome": "terminal_salvage_failed_read_only",
                    "error": str(error),
                    "terminal_report_strictly_validated": False,
                    "output_write_contract": "O_EXCL_RESERVED_BEFORE_FIRST_GET",
                    "action_must_not_be_retried": True,
                    "no_retry": True,
                    "no_recovery": True,
                    "no_autochain": True,
                    "hardware_mutation_requested": False,
                    "relay_accessed": False,
                    "serial_or_com_accessed": False,
                    "firmware_flashed": False,
                    "display_refresh_requested": False,
                },
            )
            _commit(descriptor, failure)
            raise T4V3TerminalSalvageError(
                "terminal salvage failed and was sealed; no retry is permitted"
            ) from error
        _commit(descriptor, evidence)
        return evidence
    finally:
        os.close(descriptor)


def validate_complete_salvage(path: Path = SALVAGE_OUTPUT) -> tuple[dict[str, Any], bytes]:
    """Deep-validate a COMPLETE salvage for W7 and human composite binding."""

    resolved = Path(path).resolve()
    _require(resolved == SALVAGE_OUTPUT, "complete salvage path differs")
    payload, value = _load_json(resolved, label="T4 V3 terminal salvage")
    canonical_sha = _verify_integrity(value, label="T4 V3 terminal salvage")
    host = once.configure()
    context = _validate_source_and_claim(host)
    _require(
        value.get("kind")
        == (
            "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v3-terminal-read-only-salvage"
        )
        and value.get("outcome") == "complete_salvaged_read_only"
        and value.get("network") == {"get": 4, "post": 0}
        and value.get("visible_refreshes") == 1
        and value.get("action") == context["action"]
        and value.get("boot_nonce") == context["boot_nonce"]
        and value.get("source_consumed_failure_binding") == context["source_binding"]
        and value.get("claim_binding") == context["claim_binding"]
        and value.get("terminal_report_strictly_validated") is True
        and value.get("hardware_mutation_requested") is False
        and value.get("no_retry") is True
        and value.get("no_recovery") is True
        and value.get("no_autochain") is True,
        "complete salvage envelope differs",
    )
    terminal = value.get("terminal_report")
    status = value.get("status")
    _require(isinstance(terminal, Mapping) and isinstance(status, Mapping), "salvage terminal payload differs")
    _require(
        _validate_terminal_status(
            host, status, terminal, boot_nonce=context["boot_nonce"]
        )
        == "complete_salvaged_read_only",
        "salvage is not COMPLETE",
    )
    value["_validated_file_binding"] = {
        "path": str(resolved),
        "bytes": len(payload),
        "file_sha256": hashlib.sha256(payload).hexdigest(),
        "canonical_integrity_sha256": canonical_sha,
    }
    return value, payload


def reconcile_sealed_salvage_failure(
    *,
    source: Path = SALVAGE_OUTPUT,
    output: Path = RECONCILED_OUTPUT,
) -> dict[str, Any]:
    """Strictly reconcile the already-sealed four-GET transcript offline.

    This function has no base URL or requester and therefore cannot perform a
    device request.  It exists because the first terminal-neutral reader
    preserved a valid FAULT transcript but its host-side status validator
    rejected the firmware's intentional FAULT ``current_action`` field.
    """

    source_path = Path(source).resolve()
    _require(source_path == SALVAGE_OUTPUT, "raw salvage source path differs")
    source_payload, raw = _load_json(source_path, label="raw terminal salvage")
    raw_integrity = _verify_integrity(raw, label="raw terminal salvage")
    host = once.configure()
    context = _validate_source_and_claim(host)
    _require(
        raw.get("kind")
        == (
            "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v3-terminal-read-only-salvage-failure"
        )
        and raw.get("outcome") == "terminal_salvage_failed_read_only"
        and raw.get("network") == {"get": 4, "post": 0}
        and raw.get("action") == context["action"]
        and raw.get("boot_nonce") == context["boot_nonce"]
        and raw.get("source_consumed_failure_binding") == context["source_binding"]
        and raw.get("claim_binding") == context["claim_binding"]
        and raw.get("no_retry") is True
        and raw.get("no_recovery") is True
        and raw.get("no_autochain") is True
        and raw.get("hardware_mutation_requested") is False,
        "raw salvage envelope differs",
    )
    transcript = raw.get("transcript")
    _require(isinstance(transcript, list) and len(transcript) == 4, "raw salvage transcript differs")
    _require(
        [(item.get("method"), item.get("endpoint"), item.get("status")) for item in transcript]
        == [
            ("GET", "version", 200),
            ("GET", "manifest", 200),
            ("GET", "status", 200),
            ("GET", "report", 200),
        ],
        "raw salvage was not the exact successful four-GET sequence",
    )
    version, manifest, status, terminal = (
        item.get("response") for item in transcript
    )
    _require(
        all(isinstance(item, Mapping) for item in (version, manifest, status, terminal)),
        "raw salvage response root differs",
    )
    host._validate_version(version)  # noqa: SLF001
    host._validate_manifest(manifest)  # noqa: SLF001
    outcome = _validate_terminal_status(
        host, status, terminal, boot_nonce=context["boot_nonce"]
    )
    _require(outcome == "fault_salvaged_read_only", "raw salvage is not strict FAULT")

    descriptor = _reserve_reconciled(Path(output))
    evidence = _seal(
        host,
        {
            "schema_version": 1,
            "kind": (
                "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-"
                "swap-confirmation-successor-v3-terminal-fault-reconciliation"
            ),
            "created_at": host.base.runner._now(),  # noqa: SLF001
            "offline_only": True,
            "device_requests_made": 0,
            "network": {"get": 0, "post": 0},
            "reconciled_historical_network": {"get": 4, "post": 0},
            "firmware_sha256": context["firmware_sha256"],
            "boot_nonce": context["boot_nonce"],
            "action": deepcopy(context["action"]),
            "source_consumed_failure_binding": context["source_binding"],
            "claim_binding": context["claim_binding"],
            "raw_salvage_binding": {
                "path": str(source_path),
                "bytes": len(source_payload),
                "file_sha256": hashlib.sha256(source_payload).hexdigest(),
                "canonical_integrity_sha256": raw_integrity,
                "outcome": raw["outcome"],
            },
            "status": deepcopy(dict(status)),
            "terminal_report": deepcopy(dict(terminal)),
            "historical_transcript": deepcopy(transcript),
            "outcome": outcome,
            "terminal_state": "FAULT",
            "terminal_report_strictly_validated": True,
            "driver_called": terminal["driver_called"],
            "driver_call_count_for_action": terminal[
                "driver_call_count_for_action"
            ],
            "total_driver_call_count": terminal["total_driver_call_count"],
            "completed_visible_refreshes": 0,
            "partial_visible_panel_mutation_possible": True,
            "panel_state_qualified": False,
            "matched_swap_complete": False,
            "human_profile_following_decision_allowed": False,
            "fresh_fault_bound_white_containment_required": True,
            "output_write_contract": "O_EXCL_OFFLINE_DERIVATION",
            "claim_state": "permanently_consumed",
            "action_must_not_be_retried": True,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
            "hardware_mutation_requested": False,
            "relay_accessed": False,
            "serial_or_com_accessed": False,
            "firmware_flashed": False,
            "display_refresh_requested": False,
        },
    )
    try:
        _commit(descriptor, evidence)
    finally:
        os.close(descriptor)
    return evidence


def validate_fault_reconciliation(
    path: Path = RECONCILED_OUTPUT,
) -> tuple[dict[str, Any], bytes]:
    """Deep-validate the offline FAULT authority for a fresh containment."""

    resolved = Path(path).resolve()
    _require(resolved == RECONCILED_OUTPUT, "FAULT reconciliation path differs")
    payload, value = _load_json(resolved, label="T4 V3 FAULT reconciliation")
    canonical_sha = _verify_integrity(value, label="T4 V3 FAULT reconciliation")
    host = once.configure()
    context = _validate_source_and_claim(host)
    _require(
        value.get("kind")
        == (
            "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v3-terminal-fault-reconciliation"
        )
        and value.get("outcome") == "fault_salvaged_read_only"
        and value.get("offline_only") is True
        and value.get("device_requests_made") == 0
        and value.get("network") == {"get": 0, "post": 0}
        and value.get("reconciled_historical_network") == {"get": 4, "post": 0}
        and value.get("action") == context["action"]
        and value.get("boot_nonce") == context["boot_nonce"]
        and value.get("source_consumed_failure_binding") == context["source_binding"]
        and value.get("claim_binding") == context["claim_binding"]
        and value.get("terminal_state") == "FAULT"
        and value.get("terminal_report_strictly_validated") is True
        and value.get("partial_visible_panel_mutation_possible") is True
        and value.get("panel_state_qualified") is False
        and value.get("matched_swap_complete") is False
        and value.get("human_profile_following_decision_allowed") is False
        and value.get("fresh_fault_bound_white_containment_required") is True
        and value.get("action_must_not_be_retried") is True,
        "FAULT reconciliation envelope differs",
    )
    status = value.get("status")
    terminal = value.get("terminal_report")
    _require(isinstance(status, Mapping) and isinstance(terminal, Mapping), "FAULT reconciliation payload differs")
    _require(
        _validate_terminal_status(
            host, status, terminal, boot_nonce=context["boot_nonce"]
        )
        == "fault_salvaged_read_only",
        "FAULT reconciliation terminal differs",
    )
    value["_validated_file_binding"] = {
        "path": str(resolved),
        "bytes": len(payload),
        "file_sha256": hashlib.sha256(payload).hexdigest(),
        "canonical_integrity_sha256": canonical_sha,
    }
    return value, payload


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate-local")
    live = sub.add_parser("salvage-terminal", allow_abbrev=False)
    live.add_argument("--base-url", required=True)
    live.add_argument("--confirm-j2-off", action="store_true", required=True)
    live.add_argument("--timeout", type=float, default=15.0)
    sub.add_parser("validate-complete")
    sub.add_parser("reconcile-sealed")
    sub.add_parser("validate-fault")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "validate-local":
            host = once.configure()
            context = _validate_source_and_claim(host)
            result = {
                "result": "PASS",
                "offline_only": True,
                "device_requests": 0,
                "source_consumed_failure_binding": context["source_binding"],
                "claim_binding": context["claim_binding"],
                "salvage_output": str(SALVAGE_OUTPUT),
                "network_if_run": {"get": 4, "post": 0},
            }
        elif args.command == "validate-complete":
            value, _payload = validate_complete_salvage()
            result = {
                "result": "PASS",
                "outcome": value["outcome"],
                "terminal_state": value["terminal_state"],
                "network": value["network"],
                "file_binding": value["_validated_file_binding"],
            }
        elif args.command == "reconcile-sealed":
            result = reconcile_sealed_salvage_failure()
        elif args.command == "validate-fault":
            value, _payload = validate_fault_reconciliation()
            result = {
                "result": "PASS",
                "outcome": value["outcome"],
                "terminal_state": value["terminal_state"],
                "network": value["network"],
                "reconciled_historical_network": value[
                    "reconciled_historical_network"
                ],
                "file_binding": value["_validated_file_binding"],
            }
        else:
            result = salvage_terminal_once(
                args.base_url,
                confirm_j2_off=args.confirm_j2_off,
                timeout=args.timeout,
            )
    except (T4V3TerminalSalvageError, ValueError, RuntimeError) as error:
        print(f"T4 V3 terminal salvage error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
