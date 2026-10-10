#!/usr/bin/env python3
"""Offline V1C readiness audit for the full-frame/PTLW A/B campaign.

V1B demonstrated a strict counterexample to the proposed reset-only gate:
reset and the pre-PON idle check completed, PON asserted BUSY, and PON then
failed to return idle within 60 seconds.  Consequently raw BUSY, reset-idle,
or stable revision reads cannot qualify PON completion.

This module is deliberately offline-only.  It does not import a device runner,
HTTP client, serial library, relay controller, or flashing tool.  It can audit
sealed local evidence and emits a fail-closed, diagnostic-only V1C decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
PROGRAM = ROOT / "src" / "ec5_runtime_lut_ptlw_fullframe_ab_v1_program.inc"
DRIVER = ROOT / "src" / "ec5_runtime_lut_ptlw_fullframe_ab_v1_driver.inc"
SHARED_DRIVER = ROOT / "src" / "epd_driver.cpp"
WHITE_DRIVER = ROOT / "src" / "ec5_factory_otp_white_recovery_driver.inc"
OFFLINE_MANIFEST = (
    ROOT
    / "docs"
    / "MF1750_RUNTIME_LUT_PTLW_FULLFRAME_AB_V1_OFFLINE_BUILD_2026-08-25.json"
)

SCHEMA_VERSION = 1
KIND = "mf1750-runtime-lut-ptlw-fullframe-ab-v1c-readiness-audit"
MODE = "DIAGNOSTIC_ONLY"
PON_TIMEOUT_MS = 60_000
OFFLINE_MANIFEST_SHA256 = (
    "05d871059ef4bbfac880a00f522e441b1587dcf80b84f79eb924d4c41761ff53"
)

SHARED_ACTION_BINDING = {
    "ordinal": 1,
    "action_id": "bd6b07ebd793837c5cc134531b474d01bc9d8ebb62807ffd5c49ae92d090907c",
    "descriptor_id": "d7821ce9969ba7586e841acdc15d9d5988d642fed1802e0e760350e23021aaf8",
    "role": "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
}
V1_BINDING = {
    "firmware_sha256": "6e42e3b08ec8053a3efea3e4f12d334dc246abb99576454188136391fa1130fb",
    "contract_id": "9e7414f483174cc74fa8adca9c1c2ea4c23c3250f84882969f34e87efb25a8fa",
    "build_tag": "MF1750_EC5_RUNTIME_LUT_PTLW_FULLFRAME_AB_V1_2026-08-25",
    "boot_nonce": "35d91cbde71348d6",
    "test_id": "EC5-RUNTIME-LUT-PTLW-FULLFRAME-AB-V1",
    "campaign_id": "EC5_RUNTIME_LUT_PTLW_FULLFRAME_AB_V1",
}
V1B_BINDING = {
    "firmware_sha256": "48fb0397948385feb2a0b155dca22bbb741e346df1a0edd7871c8765bd7181c3",
    "contract_id": "e6e8802a3fd93f1f867c20f1e2013dc4ade410881b2ade46d1e1fb60d9821cb5",
    "build_tag": "MF1750_EC5_RUNTIME_LUT_PTLW_FULLFRAME_AB_V1B_2026-08-25",
    "boot_nonce": "59f89f6255ec54ae",
    "test_id": "EC5-RUNTIME-LUT-PTLW-FULLFRAME-AB-V1B",
    "campaign_id": "EC5_RUNTIME_LUT_PTLW_FULLFRAME_AB_V1B",
}

EXPECTED_DRIVER_PATH = {
    "input_frame_fnv1a": 322_178_501,
    "cs1_dtm_fnv1a": 3_081_262_533,
    "cs2_dtm_fnv1a": 3_081_262_533,
    "cs1_upload_ms": 2_444,
    "cs2_upload_ms": 2_444,
    "spi_hz": 1_000_000,
}

SOURCE_BINDING_PATHS = (
    "src/ec5_runtime_lut_ptlw_fullframe_ab_v1_driver.inc",
    "src/ec5_factory_otp_white_recovery_driver.inc",
    "src/epd_driver.cpp",
)


class V1CReadinessError(ValueError):
    """Raised when supplied local evidence does not match the V1B fault."""


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    sealed = dict(value)
    sealed["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(_canonical_bytes(value)).hexdigest(),
    }
    return sealed


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise V1CReadinessError(f"cannot read local JSON evidence: {path}") from error
    if not isinstance(value, Mapping):
        raise V1CReadinessError(f"local JSON evidence must be an object: {path}")
    return value


def _verify_embedded_integrity(
    value: Mapping[str, Any], *, label: str
) -> dict[str, Any]:
    integrity = value.get("integrity")
    _require(isinstance(integrity, Mapping), f"{label} integrity is missing")
    _require(
        integrity.get("algorithm")
        == "sha256-canonical-json-without-integrity",
        f"{label} integrity algorithm differs",
    )
    expected = integrity.get("sha256")
    _require(
        isinstance(expected, str) and len(expected) == 64,
        f"{label} integrity SHA-256 is invalid",
    )
    unsigned = dict(value)
    del unsigned["integrity"]
    actual = hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()
    _require(actual == expected, f"{label} canonical integrity mismatch")
    return {
        "algorithm": "sha256-canonical-json-without-integrity",
        "embedded_sha256": expected,
        "recomputed_sha256": actual,
        "valid": True,
    }


def _require(value: bool, message: str) -> None:
    if not value:
        raise V1CReadinessError(message)


def _source_audit() -> dict[str, Any]:
    try:
        program = PROGRAM.read_text(encoding="utf-8")
        driver = DRIVER.read_text(encoding="utf-8")
        shared = SHARED_DRIVER.read_text(encoding="utf-8")
    except OSError as error:
        raise V1CReadinessError("V1B source files are unavailable") from error

    execute_start = program.index("void handleExecute()")
    execute_end = program.index("\nvoid installRoutes()", execute_start)
    execute = program[execute_start:execute_end]
    dispatch_start = program.index("void executePendingAction()")
    dispatch_end = program.index("\n}\n\n}  // namespace", dispatch_start)
    dispatch = program[dispatch_start:dispatch_end]
    init_start = shared.index("static bool epdInitResolutionSelected")
    init_end = shared.index("\nstatic bool epdInitResolution(", init_start)
    init = shared[init_start:init_end]
    refresh_start = driver.index("bool phRefreshTreatmentsIdentically()")
    refresh_end = driver.index("\n}\n\n}  // namespace", refresh_start)
    refresh = driver[refresh_start:refresh_end]

    consumed_before_dispatch = (
        execute.index("persistCursor(kPhaseConsumed")
        < execute.index("executePending = true")
    )
    dispatch_calls_driver = (
        "epdDisplayCompiledFactoryOtpWhiteRecovery()" in dispatch
        and "epdDisplayCompiledChromaGrid(action->driverRole)" in dispatch
    )
    reset_before_idle = init.index("epdReset();") < init.index(
        'epdWaitIdle("reset")'
    )
    pon_after_precommand_idle = refresh.index(
        'epdRequireIdleBeforeCommand("PON")'
    ) < refresh.index("epdCommand(PON)")
    pon_wait_after_command = refresh.index("epdCommand(PON)") < refresh.index(
        'epdWaitBusyThenIdle("PON")'
    )

    _require(consumed_before_dispatch, "V1B no longer consumes before dispatch")
    _require(dispatch_calls_driver, "V1B driver dispatch structure changed")
    _require(reset_before_idle, "V1B reset/idle ordering changed")
    _require(pon_after_precommand_idle, "V1B pre-PON idle ordering changed")
    _require(pon_wait_after_command, "V1B PON wait ordering changed")

    return {
        "durable_action_consumed_before_driver_call": True,
        "driver_reset_precedes_reset_idle_wait": True,
        "precommand_idle_precedes_pon": True,
        "pon_busy_then_idle_wait_follows_pon": True,
        "reset_only_path_contains_pon": False,
        "revision_read_path_contains_pon": False,
        "source_paths": [
            str(PROGRAM.relative_to(ROOT)),
            str(DRIVER.relative_to(ROOT)),
            str(SHARED_DRIVER.relative_to(ROOT)),
        ],
    }


def _original_v1_source_binding() -> dict[str, Any]:
    try:
        raw_manifest = OFFLINE_MANIFEST.read_bytes()
    except OSError as error:
        raise V1CReadinessError("original V1 offline manifest is unavailable") from error
    manifest_file_sha256 = hashlib.sha256(raw_manifest).hexdigest()
    _require(
        manifest_file_sha256 == OFFLINE_MANIFEST_SHA256,
        "original V1 offline manifest file SHA-256 differs",
    )
    manifest = _load_json(OFFLINE_MANIFEST)
    _require(
        manifest.get("schema") == "mf1750-offline-build-record-v1",
        "original V1 offline manifest schema differs",
    )
    _require(
        manifest.get("contract_id") == V1_BINDING["contract_id"],
        "original V1 offline manifest contract differs",
    )
    artifacts = manifest.get("artifacts")
    _require(isinstance(artifacts, Mapping), "offline manifest artifacts missing")
    firmware = artifacts.get("firmware.bin")
    _require(isinstance(firmware, Mapping), "offline manifest firmware.bin missing")
    _require(
        firmware.get("sha256") == V1_BINDING["firmware_sha256"],
        "offline manifest V1 firmware binding differs",
    )
    source_sha256 = manifest.get("source_sha256")
    _require(isinstance(source_sha256, Mapping), "offline manifest source hashes missing")

    sources: dict[str, dict[str, Any]] = {}
    for relative in SOURCE_BINDING_PATHS:
        expected = source_sha256.get(relative)
        _require(
            isinstance(expected, str) and len(expected) == 64,
            f"offline manifest source hash missing: {relative}",
        )
        path = ROOT / relative
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            raise V1CReadinessError(f"bound source is unavailable: {relative}") from error
        _require(actual == expected, f"current source differs from V1 manifest: {relative}")
        sources[relative] = {
            "manifest_sha256": expected,
            "current_sha256": actual,
            "match": True,
        }
    return {
        "manifest_path": str(OFFLINE_MANIFEST.relative_to(ROOT)),
        "manifest_file_sha256": manifest_file_sha256,
        "manifest_contract_id": manifest["contract_id"],
        "manifest_firmware_bin_sha256": firmware["sha256"],
        "sources": sources,
        "all_driver_white_shared_sources_match": True,
        "scope": (
            "runtime treatment driver, factory-white driver, and shared driver; "
            "V1B state-machine/identity files are intentionally outside this parity claim"
        ),
    }


def _validate_record_binding(
    record: Mapping[str, Any],
    terminal: Mapping[str, Any],
    expected: Mapping[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    action = record.get("action")
    _require(isinstance(action, Mapping), f"{label} action binding is missing")
    for key, wanted in SHARED_ACTION_BINDING.items():
        _require(action.get(key) == wanted, f"{label} action {key} differs")
        _require(terminal.get(key) == wanted, f"{label} terminal action {key} differs")
    _require(
        terminal.get("action_id") == action.get("action_id")
        and terminal.get("descriptor_id") == action.get("descriptor_id"),
        f"{label} action/terminal binding differs",
    )
    _require(
        record.get("firmware_sha256") == expected["firmware_sha256"],
        f"{label} firmware SHA-256 differs",
    )
    _require(
        record.get("boot_nonce") == expected["boot_nonce"],
        f"{label} top-level boot nonce differs",
    )
    for key in ("contract_id", "build_tag", "boot_nonce", "test_id", "campaign_id"):
        _require(terminal.get(key) == expected[key], f"{label} terminal {key} differs")
    return {
        "firmware_sha256": expected["firmware_sha256"],
        "contract_id": expected["contract_id"],
        "build_tag": expected["build_tag"],
        "boot_nonce": expected["boot_nonce"],
        "test_id": expected["test_id"],
        "campaign_id": expected["campaign_id"],
        "action": dict(SHARED_ACTION_BINDING),
        "exact": True,
    }


def _driver_path(driver: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    values = {
        "input_frame_fnv1a": driver.get("input_fnv1a"),
        "cs1_dtm_fnv1a": driver.get("cs1_dtm_fnv1a"),
        "cs2_dtm_fnv1a": driver.get("cs2_dtm_fnv1a"),
        "cs1_upload_ms": driver.get("cs1_upload_ms"),
        "cs2_upload_ms": driver.get("cs2_upload_ms"),
        "spi_hz": driver.get("spi_hz"),
    }
    _require(values == EXPECTED_DRIVER_PATH, f"{label} driver payload/timing path differs")
    return values


def assess_no_pon_observables(
    *,
    raw_busy_idle_high: bool,
    reset_idle_completed: bool,
    cs1_revision_stable: bool,
    cs2_revision_stable: bool,
) -> dict[str, Any]:
    """Classify the strongest possible no-PON digital-path observation.

    Even when every observable is positive, none exercises the PON high-voltage
    path.  The result therefore always keeps visible action fail-closed.
    """

    digital_path_observed = all(
        (
            raw_busy_idle_high,
            reset_idle_completed,
            cs1_revision_stable,
            cs2_revision_stable,
        )
    )
    return {
        "raw_busy_idle_high": raw_busy_idle_high,
        "reset_idle_completed": reset_idle_completed,
        "cs1_revision_stable": cs1_revision_stable,
        "cs2_revision_stable": cs2_revision_stable,
        "digital_reset_spi_path_observed": digital_path_observed,
        "pon_command_sent": False,
        "pon_busy_assertion_observed": False,
        "pon_idle_completion_observed": False,
        "pon_completion_qualified": False,
        "visible_action_allowed": False,
        "reason": (
            "no-PON observables do not exercise the controller high-voltage "
            "power-on stage"
        ),
    }


def describe() -> dict[str, Any]:
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "mode": MODE,
            "offline_only": True,
            "hardware_accessed": False,
            "network_accessed": False,
            "serial_or_com_accessed": False,
            "relay_accessed": False,
            "firmware_flashed": False,
            "display_refreshed": False,
            "source_audit": _source_audit(),
            "original_v1_source_binding": _original_v1_source_binding(),
            "proof_boundary": {
                "reliable_no_pon_gate_identified": False,
                "raw_busy_proves_pon_completion": False,
                "reset_idle_proves_pon_completion": False,
                "stable_revision_reads_prove_pon_completion": False,
                "pon_completion_requires_observing_pon_busy_then_idle": True,
                "visible_action_may_be_consumed_after_no_pon_gate": False,
            },
            "v1c_decision": {
                "visible_action_firmware_authorized_by_this_audit": False,
                "visible_action_runner_enabled": False,
                "dry_run_and_local_fault_audit_only": True,
                "do_not_retry_v1b_ordinal_1": True,
                "do_not_relabel_reset_only_as_power_qualification": True,
                "separate_supervised_pon_pof_no_drf_probe_needed_if_pursued": True,
            },
        }
    )


def _extract_v1b_fault(salvage: Mapping[str, Any]) -> dict[str, Any]:
    embedded_integrity = _verify_embedded_integrity(
        salvage, label="V1B salvage"
    )
    _require(
        salvage.get("kind")
        == "mf1750-ec5-runtime-lut-ptlw-fullframe-ab-v1b-read-only-fault-salvage",
        "evidence is not the V1B read-only fault salvage",
    )
    _require(salvage.get("outcome") == "fault_salvaged_read_only", "salvage outcome differs")
    _require(salvage.get("network") == {"get": 4, "post": 0}, "salvage was not GET-only")
    _require(salvage.get("hardware_mutation_requested") is False, "salvage requested mutation")
    _require(salvage.get("action_must_not_be_retried") is True, "no-retry evidence missing")
    _require(salvage.get("no_retry") is True, "no_retry differs")
    _require(salvage.get("no_recovery") is True, "no_recovery differs")
    _require(salvage.get("no_autochain") is True, "no_autochain differs")

    terminal = salvage.get("terminal_report")
    _require(isinstance(terminal, Mapping), "terminal report is missing")
    identity_binding = _validate_record_binding(
        salvage, terminal, V1B_BINDING, label="V1B salvage"
    )
    _require(terminal.get("terminal_state") == "FAULT", "terminal state is not FAULT")
    _require(terminal.get("ordinal") == 1, "fault was not ordinal 1")
    _require(terminal.get("driver_called") is True, "driver call evidence missing")
    _require(terminal.get("total_driver_call_count") == 1, "driver count differs")
    driver = terminal.get("driver")
    _require(isinstance(driver, Mapping), "driver evidence is missing")
    driver_path = _driver_path(driver, label="V1B fault")
    _require(driver.get("valid") is True, "driver evidence is invalid")
    _require(driver.get("failure_stage") == "refresh_sequence", "failure stage differs")
    _require(driver.get("timeout_stage") == "PON", "timeout was not PON")
    _require(driver.get("wait_timeout") is True, "PON timeout flag is missing")
    _require(driver.get("pon_busy_seen") is True, "PON BUSY assertion was not observed")
    _require(driver.get("pon_ms", 0) >= PON_TIMEOUT_MS, "PON wait was shorter than timeout")
    _require(driver.get("pre_command_idle_failure") is False, "pre-PON idle gate failed")
    _require(driver.get("pre_command_busy_stage") == "none", "pre-command BUSY stage differs")
    _require(driver.get("busy_assertion_missing") is False, "PON assertion was missing")
    _require(driver.get("drf_busy_seen") is False and driver.get("drf_ms") == 0, "DRF was reached")

    safe = driver.get("safe_finish")
    _require(isinstance(safe, Mapping), "safe-finish evidence is missing")
    _require(
        safe.get("busy_before_pins_low") == 1
        and safe.get("busy_after_pins_low") == 1
        and safe.get("busy_after_5ms") == 1,
        "safe-finish BUSY samples differ",
    )
    gpio = safe.get("final_gpio")
    _require(isinstance(gpio, Mapping), "safe-finish GPIO evidence is missing")
    _require(
        gpio.get("busy") == 1
        and gpio.get("rst") == 0
        and gpio.get("cs") == 0
        and gpio.get("cs2") == 0,
        "safe-finish GPIO levels differ",
    )

    return {
        "ordinal": 1,
        "driver_calls": 1,
        "reset_and_precommand_idle_completed": True,
        "pon_busy_asserted": True,
        "pon_idle_completed": False,
        "pon_wait_ms": driver["pon_ms"],
        "drf_reached": False,
        "safe_finish_busy_high_and_panel_outputs_low": True,
        "counterexample": (
            "reset/precommand-idle success did not imply PON completion"
        ),
        "embedded_integrity": embedded_integrity,
        "identity_binding": identity_binding,
        "driver_path": driver_path,
    }


def _extract_success_reference(reference: Mapping[str, Any]) -> dict[str, Any]:
    embedded_integrity = _verify_embedded_integrity(
        reference, label="V1 success reference"
    )
    _require(reference.get("outcome") == "complete_pass", "reference was not a complete pass")
    terminal = reference.get("terminal_report")
    _require(isinstance(terminal, Mapping), "reference terminal report is missing")
    identity_binding = _validate_record_binding(
        reference, terminal, V1_BINDING, label="V1 success reference"
    )
    driver = terminal.get("driver")
    _require(isinstance(driver, Mapping), "reference driver evidence is missing")
    driver_path = _driver_path(driver, label="V1 success")
    _require(driver.get("pon_busy_seen") is True, "reference PON assertion missing")
    _require(driver.get("timeout_stage") == "none", "reference contains a timeout")
    _require(driver.get("sequence_ok") is True, "reference sequence did not pass")
    return {
        "build_tag": terminal.get("build_tag"),
        "pon_wait_ms": driver.get("pon_ms"),
        "drf_wait_ms": driver.get("drf_ms"),
        "pof_wait_ms": driver.get("pof_ms"),
        "sequence_ok": True,
        "embedded_integrity": embedded_integrity,
        "identity_binding": identity_binding,
        "driver_path": driver_path,
    }


def audit_fault(
    salvage_file: Path,
    *,
    successful_reference_file: Path,
) -> dict[str, Any]:
    fault = _extract_v1b_fault(_load_json(salvage_file))
    reference = _extract_success_reference(_load_json(successful_reference_file))
    equality = {
        key: reference["driver_path"][key] == fault["driver_path"][key]
        for key in EXPECTED_DRIVER_PATH
    }
    _require(all(equality.values()), "V1/V1B driver path evidence differs")
    driver_path_comparison = {
        "v1_success": reference["driver_path"],
        "v1b_pon_timeout": fault["driver_path"],
        "field_equality": equality,
        "all_payload_fnv_upload_timing_and_spi_equal": True,
        "interpretation": (
            "the uploaded factory-white payload identities, per-controller "
            "upload times, and SPI path are identical; this isolates no source "
            "or payload-path delta, but does not prove transient power/panel state"
        ),
    }
    source_binding = _original_v1_source_binding()
    return _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "mode": MODE,
            "offline_only": True,
            "hardware_accessed": False,
            "network_accessed": False,
            "serial_or_com_accessed": False,
            "relay_accessed": False,
            "firmware_flashed": False,
            "display_refreshed": False,
            "salvage_file": str(salvage_file.resolve()),
            "successful_reference_file": (
                str(successful_reference_file.resolve())
            ),
            "source_audit": _source_audit(),
            "original_v1_source_binding": source_binding,
            "v1b_fault": fault,
            "successful_reference": reference,
            "driver_path_comparison": driver_path_comparison,
            "strongest_no_pon_observation": assess_no_pon_observables(
                raw_busy_idle_high=True,
                reset_idle_completed=True,
                cs1_revision_stable=True,
                cs2_revision_stable=True,
            ),
            "proof_boundary": {
                "reliable_no_pon_gate_identified": False,
                "v1b_is_counterexample_to_reset_only_qualification": True,
                "pon_completion_qualified": False,
                "visible_action_allowed": False,
                "driver_source_and_payload_path_delta_identified": False,
                "transient_or_physical_state_proven": False,
            },
            "v1c_decision": {
                "mode": MODE,
                "visible_action_firmware_authorized_by_this_audit": False,
                "visible_action_runner_enabled": False,
                "do_not_retry_v1b_ordinal_1": True,
                "do_not_consume_new_action_on_reset_only_evidence": True,
                "next_live_probe_is_outside_this_no_pon_contract": (
                    "a separately reviewed supervised PON+POF/no-DRF probe"
                ),
            },
        }
    )


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    audit = sub.add_parser("audit-fault")
    audit.add_argument("--salvage", type=Path, required=True)
    audit.add_argument("--successful-reference", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "describe":
            value = describe()
        else:
            value = audit_fault(
                args.salvage,
                successful_reference_file=args.successful_reference,
            )
            _write_json(args.output, value)
    except V1CReadinessError as error:
        print(f"V1C readiness error: {error}")
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
