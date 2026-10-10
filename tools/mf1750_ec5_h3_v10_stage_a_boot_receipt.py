#!/usr/bin/env python3
"""Build and validate the sealed, partial V10 Stage-A boot-control receipt.

This is an offline evidence tool.  It has no serial, subprocess, network, or
hardware execution entry point.  The receipt proves one observed ``chip_id``
process result and its identity output.  It deliberately does *not* treat the
pre-connect bootloader reset plus final hard-reset request as "exactly one
reset", and it does not prove that an application booted after that request.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Final, Mapping, Sequence

from tools import mf1750_ec5_h3_c_first_diagnostic_recovery_contract as recovery
from tools import mf1750_ec5_h3_matched_control_contract as contract


SCHEMA_VERSION: Final = 1
KIND: Final = "mf1750-ec5-h3-v10-stage-a-partial-boot-control-receipt-v1"
CLASSIFICATION: Final = "PARTIAL_BOOT_CONTROL_RECEIPT_NOT_STAGE_A_COMPLETE"
MAX_BYTES: Final = 4_000_000

EXPECTED_PLAN_ID: Final = (
    "6690b02cfd4334a0a9e6179daad4ce5f3efddc601470e4e8515745418300379d"
)
EXPECTED_PLAN_FILE_SHA256: Final = (
    "587590234464d3d3630cc9629ae8738e7697c55731f3203d0c35553770d3fbeb"
)
EXPECTED_PLAN_CANONICAL_SHA256: Final = (
    "75504e526433b55a259b9c7f56cd39334593e4751043c1ec7df8b9309a2801a1"
)
EXPECTED_STAGE_A_INTENT_SHA256: Final = (
    "4361cbd400fde18f356e5e6de9e66aecd6cf6f87c0fe1de4ac101a286b6feba7"
)
EXPECTED_RELEASE_ID: Final = recovery.EXPECTED_RELEASE_ID
EXPECTED_FIRMWARE_SHA256: Final = recovery.EXPECTED_CONTROL_BINARY_SHA256
EXPECTED_MAC: Final = recovery.EXPECTED_DEVICE_MAC

EXPECTED_TRANSCRIPT_SHA256: Final = (
    "d4eefeb970d27fa7e76fc102e80719b48511b509378553be1c5e7f06953d044b"
)
EXPECTED_TRANSCRIPT_BYTES: Final = 339
EXPECTED_TRANSCRIPT: Final = (
    "esptool.py v4.11.0\n"
    "Serial port COM8\n"
    "Connecting....\n"
    "Chip is ESP32-S3 (QFN56) (revision v0.2)\n"
    "Features: WiFi, BLE, Embedded PSRAM 8MB (AP_3v3)\n"
    "Crystal is 40MHz\n"
    "MAC: a4:cb:8f:d9:fc:d4\n"
    "Uploading stub...\n"
    "Running stub...\n"
    "Stub running...\n"
    "Warning: ESP32-S3 has no Chip ID. Reading MAC instead.\n"
    "MAC: a4:cb:8f:d9:fc:d4\n"
    "Hard resetting via RTS pin...\n"
).encode()

PYTHON_PATH: Final = Path(r"C:\Users\Ye\.platformio\penv\Scripts\python.exe")
ESPTOOL_PATH: Final = Path(
    r"C:\Users\Ye\.platformio\packages\tool-esptoolpy\esptool.py"
)
EXPECTED_PYTHON_SHA256: Final = (
    "e4c6ffe75947e5fcaf5b6a604776a19882e19b4315f2ac58ad460dcef2e5609a"
)
EXPECTED_ESPTOOL_SHA256: Final = (
    "7e6833367b891629474c7717eb1689178377c1b13be286016ef72ee2c4e269a9"
)
EXACT_ARGV: Final = (
    str(PYTHON_PATH),
    str(ESPTOOL_PATH),
    "--chip",
    "esp32s3",
    "--port",
    "COM8",
    "--baud",
    "115200",
    "--before",
    "default_reset",
    "--after",
    "hard_reset",
    "chip_id",
)


class StageABootReceiptError(ValueError):
    """The evidence, receipt, or an exact binding differs."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_regular(path: Path, *, label: str) -> tuple[Path, bytes]:
    target = Path(os.path.abspath(os.fspath(path)))
    try:
        before = target.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise StageABootReceiptError(f"{label} must be a non-symlink regular file")
        if before.st_size <= 0 or before.st_size > MAX_BYTES:
            raise StageABootReceiptError(f"{label} size is invalid")
        payload = target.read_bytes()
        after = target.lstat()
    except OSError as error:
        raise StageABootReceiptError(f"could not read {label}: {error}") from error
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise StageABootReceiptError(f"{label} changed while being read")
    return target, payload


def _decode_json(payload: bytes, *, label: str) -> Mapping[str, Any]:
    try:
        root = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise StageABootReceiptError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(root, Mapping):
        raise StageABootReceiptError(f"{label} root is not an object")
    return root


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    root = deepcopy(dict(unsigned))
    root["integrity"] = {
        "algorithm": "sha256",
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
        "canonical_sha256": contract.sha256(root),
    }
    return root


def _validate_seal(root: Mapping[str, Any]) -> str:
    unsigned = {key: value for key, value in root.items() if key != "integrity"}
    if root.get("integrity") != _seal(unsigned)["integrity"]:
        raise StageABootReceiptError("receipt canonical integrity differs")
    return str(root["integrity"]["canonical_sha256"])


def _exact_file_binding(
    path: Path, expected_sha256: str, *, label: str
) -> dict[str, Any]:
    resolved, payload = _read_regular(path, label=label)
    digest = contract.sha256(payload)
    if digest != expected_sha256:
        raise StageABootReceiptError(f"{label} SHA-256 differs")
    return {"path": str(resolved), "bytes": len(payload), "sha256": digest}


def materialize_receipt(
    *, plan_file: Path, transcript_file: Path, receipt_file: Path
) -> dict[str, Any]:
    """Deep-bind the supplied offline evidence into a deterministic receipt."""

    plan_path, plan_payload = _read_regular(plan_file, label="recovery plan")
    if contract.sha256(plan_payload) != EXPECTED_PLAN_FILE_SHA256:
        raise StageABootReceiptError("recovery plan whole-file SHA-256 differs")
    plan = _decode_json(plan_payload, label="recovery plan")
    try:
        plan_summary = recovery.validate_plan(plan)
    except recovery.DiagnosticRecoveryContractError as error:
        raise StageABootReceiptError(
            f"recovery plan validation failed: {error}"
        ) from error
    expected_plan = {
        "plan_id": EXPECTED_PLAN_ID,
        "canonical_sha256": EXPECTED_PLAN_CANONICAL_SHA256,
        "stage_a_new_boot_intent_sha256": EXPECTED_STAGE_A_INTENT_SHA256,
        "release_id": EXPECTED_RELEASE_ID,
        "firmware_binary_sha256": EXPECTED_FIRMWARE_SHA256,
    }
    for key, expected in expected_plan.items():
        if plan_summary.get(key) != expected:
            raise StageABootReceiptError(f"recovery plan {key} differs")

    transcript_path, transcript = _read_regular(transcript_file, label="transcript")
    if (
        transcript != EXPECTED_TRANSCRIPT
        or len(transcript) != EXPECTED_TRANSCRIPT_BYTES
        or contract.sha256(transcript) != EXPECTED_TRANSCRIPT_SHA256
    ):
        raise StageABootReceiptError("transcript exact bytes differ")
    if transcript.count(f"MAC: {EXPECTED_MAC}".encode()) != 2:
        raise StageABootReceiptError("transcript exact-MAC occurrence count differs")

    output_path = Path(os.path.abspath(os.fspath(receipt_file)))
    stage_a = plan["two_stage_future_authority"]["new_boot_stage"]
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "classification": CLASSIFICATION,
        "receipt_file": str(output_path),
        "plan_binding": {
            "path": str(plan_path),
            "bytes": len(plan_payload),
            "sha256": contract.sha256(plan_payload),
            "plan_id": plan_summary["plan_id"],
            "canonical_sha256": plan_summary["canonical_sha256"],
            "release_id": plan_summary["release_id"],
            "firmware_binary_sha256": plan_summary["firmware_binary_sha256"],
            "stage_a_intent": stage_a["intent"],
            "stage_a_intent_canonical_sha256": stage_a["intent_canonical_sha256"],
        },
        "serial_port_identity_observation": {
            "source": "SEPARATE_PRECOMMAND_READ_ONLY_HOST_PORT_ENUMERATION",
            "counts_as_chip_id_invocation": False,
            "port": "COM8",
            "description": "CH343",
            "vid_hex": "1A86",
            "pid_hex": "55D3",
            "usb_serial_number": "5C4C165475",
            "cryptographic_device_identity_proof": False,
        },
        "command_observation": {
            "exact_argv": list(EXACT_ARGV),
            "exact_argv_canonical_sha256": contract.sha256(list(EXACT_ARGV)),
            "chip_id_process_invocations": 1,
            "shell_exit_code": 0,
            "shell_exit_code_provenance": (
                "OBSERVED_IN_CODEX_SHELL_TOOL_RESULT_NOT_EMBEDDED_IN_TRANSCRIPT"
            ),
            "raw_stdout_stderr_capture_independently_sealed": False,
            "python_executable": _exact_file_binding(
                PYTHON_PATH, EXPECTED_PYTHON_SHA256, label="Python executable"
            ),
            "esptool_script": _exact_file_binding(
                ESPTOOL_PATH, EXPECTED_ESPTOOL_SHA256, label="esptool script"
            ),
            "semantic": {
                "tool": "esptool.py v4.11.0",
                "chip_argument": "esp32s3",
                "port_argument": "COM8",
                "baud_argument": 115200,
                "before_argument": "default_reset",
                "after_argument": "hard_reset",
                "operation": "chip_id",
                "flash_write_requested": False,
                "network_requested": False,
            },
        },
        "transcript_binding": {
            "path": str(transcript_path),
            "bytes": len(transcript),
            "sha256": contract.sha256(transcript),
            "provenance": "EXACT_TOOL_OUTPUT_TRANSCRIBED_TO_FILE_AFTER_COMMAND_NOT_DIRECT_TEE",
            "file_mtime_is_acquisition_time_proof": False,
            "hash_claim_scope": "exact bytes of the post-command tool-output transcription",
            "mac_exact_occurrences_in_one_invocation": 2,
        },
        "identity_observation": {
            "esptool_version": "4.11.0",
            "chip": "ESP32-S3",
            "package": "QFN56",
            "revision": "v0.2",
            "features": ["WiFi", "BLE", "Embedded PSRAM 8MB (AP_3v3)"],
            "crystal_mhz": 40,
            "mac": EXPECTED_MAC,
            "stub_reported_running": True,
            "same_mac_printed_twice_within_single_invocation": True,
        },
        "boot_control_accounting": {
            "authorized_stage_a_command_invocations": 1,
            "bootloader_entry_reset_control_sequence_requested": 1,
            "bootloader_entry_single_electrical_reset_proven": False,
            "connecting_dot_count": 4,
            "connecting_dots_are_sync_attempts_not_reset_count": True,
            "final_application_hard_reset_message_count": 1,
            "final_application_hard_reset_requested": True,
            "final_hard_reset_routine_returned_without_process_visible_error": True,
            "post_reset_application_handshake_observed": False,
            "post_reset_application_boot_proven": False,
            "total_low_level_reset_control_transitions": "UNKNOWN",
            "total_reset_or_boot_count_claimed_exactly_one": False,
            "plan_exactly_one_scope_is_ambiguous_against_observed_command_semantics": True,
            "plan_new_boot_operations_exactly_one_satisfied": False,
            "persistent_flash_or_nvs_mutations_requested_by_command": 0,
            "post_reset_application_persistent_mutations": "UNKNOWN",
            "http_get_requests": 0,
            "http_post_requests": 0,
            "claims": 0,
            "diagnostic_api_mutations": 0,
            "visible_refreshes": 0,
        },
        "proof_boundary": {
            "proves_one_chip_id_process_exit_zero": True,
            "proves_reported_chip_and_mac_identity": True,
            "proves_final_hard_reset_was_requested": True,
            "proves_active_application_boot": False,
            "proves_active_ota_slot": False,
            "proves_active_v10_binary": False,
            "proves_firmware_at_0x10000_is_running": False,
            "proves_wifi_sta_connected": False,
            "proves_ip_192_168_1_7": False,
            "proves_ip_192_168_1_14": False,
            "proves_http_server_or_api_routes_ready": False,
            "proves_boot_nonce": False,
            "proves_device_profile_manifest_status_or_report": False,
            "proves_firmware_detected_j2_state": False,
            "proves_no_post_reset_application_nvs_or_otadata_mutation": False,
        },
        "gate_outcome": {
            "partial_identity_and_boot_control_receipt_valid": True,
            "stage_a_intent_satisfied": False,
            "sealed_new_boot_completion_receipt_gate_satisfied": False,
            "trusted_single_ip_binding_satisfied": False,
            "fresh_onsite_gate_satisfied": False,
            "stage_b_diagnostic_authorization_derivable": False,
            "copyable_authorization_token_emitted": False,
            "reason": "no post-reset application handshake; exact-one boot/reset scope is not proven",
        },
        "offline_materialization": {
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "device_network_accessed": False,
            "subprocess_executed": False,
            "device_mutations": 0,
        },
    }
    unsigned["receipt_id"] = contract.sha256(unsigned)
    return _seal(unsigned)


def validate_receipt(root: Mapping[str, Any]) -> dict[str, Any]:
    """Validate seal and exact deterministic reconstruction."""

    canonical = _validate_seal(root)
    if (
        root.get("schema_version") != SCHEMA_VERSION
        or root.get("kind") != KIND
        or root.get("classification") != CLASSIFICATION
    ):
        raise StageABootReceiptError("receipt schema/kind/classification differs")
    rebuilt = materialize_receipt(
        plan_file=Path(str(root["plan_binding"]["path"])),
        transcript_file=Path(str(root["transcript_binding"]["path"])),
        receipt_file=Path(str(root["receipt_file"])),
    )
    if contract.canonical_json_bytes(root) != contract.canonical_json_bytes(rebuilt):
        raise StageABootReceiptError(
            "receipt differs from deterministic reconstruction"
        )
    expected_id = contract.sha256(
        {
            key: value
            for key, value in root.items()
            if key not in {"receipt_id", "integrity"}
        }
    )
    if root.get("receipt_id") != expected_id:
        raise StageABootReceiptError("receipt ID differs")
    return {
        "valid": True,
        "receipt_id": root["receipt_id"],
        "canonical_sha256": canonical,
        "classification": CLASSIFICATION,
        "stage_a_intent_satisfied": False,
        "active_v10_proven": False,
        "ip_proven": False,
        "stage_b_authorization_derivable": False,
        "device_io_performed_by_validator": False,
    }


def load_receipt(path: Path) -> Mapping[str, Any]:
    _, payload = _read_regular(path, label="receipt")
    return _decode_json(payload, label="receipt")


def write_new_receipt(path: Path, root: Mapping[str, Any]) -> None:
    validate_receipt(root)
    target = Path(os.path.abspath(os.fspath(path)))
    if target != Path(str(root["receipt_file"])):
        raise StageABootReceiptError("receipt output self-path differs")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = contract.canonical_json_bytes(root) + b"\n"
    try:
        with target.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise StageABootReceiptError("receipt output already exists") from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", allow_abbrev=False)
    build.add_argument("--plan", type=Path, required=True)
    build.add_argument("--transcript", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate", allow_abbrev=False)
    validate.add_argument("--receipt", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            root = materialize_receipt(
                plan_file=args.plan,
                transcript_file=args.transcript,
                receipt_file=args.output,
            )
            write_new_receipt(args.output, root)
        else:
            root = load_receipt(args.receipt)
        summary = validate_receipt(root)
    except (StageABootReceiptError, KeyError, TypeError) as error:
        print(f"Stage-A receipt error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
