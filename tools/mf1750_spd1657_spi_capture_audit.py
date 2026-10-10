#!/usr/bin/env python3
"""Audit a decoded dual-CS SPD1657 runtime-LUT SPI capture offline.

The input is a strict JSON export of decoded SPI byte frames grouped into
adjacent runs with the same CS selection and D/C level.  The tool reconstructs
command transactions, checks the complete successful runtime-atlas sequence,
and classifies the observed R20/R21 pair as H1, H2, or H3 for one explicitly
selected vendor profile.  It emits only lengths and SHA-256 identities, never
captured parameter bytes or recovered vendor key material.

This is a wire-observation adjudicator, not a logic-analyzer decoder.  The CLI
therefore also requires the original raw capture and verifies that its byte
length and SHA-256 match the provenance recorded by the decoded JSON.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Final, Iterable, Mapping

from tools import mf1750_ec5_runtime_lut_contract as runtime_contract
from tools import mf1750_spd1657_vendor_profile_pack as profile_pack


KIND: Final = "mf1750-spd1657-dual-cs-spi-capture-audit"
INPUT_KIND: Final = "mf1750-decoded-dual-cs-spi-byte-runs"
SCHEMA_VERSION: Final = 1
MAX_CAPTURE_JSON_BYTES: Final = 8 * 1024 * 1024
MAX_RUNS: Final = 4096
SHA256_RE: Final = re.compile(r"[0-9a-f]{64}\Z")
HEX_RE: Final = re.compile(r"(?:[0-9a-f]{2})+\Z")

CS1: Final = ("CS1",)
CS2: Final = ("CS2",)
BOTH: Final = ("CS1", "CS2")
VALID_TARGETS: Final = (CS1, CS2, BOTH)
FORBIDDEN_OTP_PROGRAM_OPCODES: Final = frozenset((0x90, 0x91))


class SpiCaptureAuditError(RuntimeError):
    """Raised when a capture is malformed, incomplete, or contract-inexact."""


@dataclass(frozen=True)
class Transaction:
    controllers: tuple[str, ...]
    command: int
    payload: bytes

    @property
    def parameter_bytes(self) -> int:
        return len(self.payload)

    @property
    def parameter_sha256(self) -> str:
        return _sha256(self.payload)


@dataclass(frozen=True)
class ExpectedTransaction:
    controllers: tuple[str, ...]
    command: int
    parameter_bytes: int
    parameter_sha256: str
    label: str


@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str
    r20: bytes
    r21: bytes

    @property
    def signature(self) -> tuple[int, str, int, str]:
        return (len(self.r20), _sha256(self.r20), len(self.r21), _sha256(self.r21))


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SpiCaptureAuditError(message)


def _require_exact_keys(value: Mapping[str, Any], keys: set[str], label: str) -> None:
    observed = set(value)
    if observed != keys:
        missing = ",".join(sorted(keys - observed)) or "none"
        extra = ",".join(sorted(observed - keys)) or "none"
        raise SpiCaptureAuditError(
            f"{label} keys differ (missing={missing}; extra={extra})"
        )


def _require_int(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise SpiCaptureAuditError(f"{label} must be an integer >= {minimum}")
    return value


def _require_text(value: Any, label: str, *, maximum: int = 128) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or any(ord(character) < 0x20 or ord(character) > 0x7E for character in value)
    ):
        raise SpiCaptureAuditError(f"{label} must be printable ASCII")
    return value


def _pairs_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise SpiCaptureAuditError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _read_regular_file(path: Path, label: str, *, maximum: int | None = None) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise SpiCaptureAuditError(
            f"{label} must be a regular non-symlink file: {path}"
        )
    size = path.stat().st_size
    if maximum is not None and size > maximum:
        raise SpiCaptureAuditError(f"{label} exceeds {maximum} bytes")
    return path.read_bytes()


def _hash_regular_file(path: Path, label: str) -> tuple[int, str]:
    """Hash a potentially large raw capture without loading it into memory."""

    if path.is_symlink() or not path.is_file():
        raise SpiCaptureAuditError(
            f"{label} must be a regular non-symlink file: {path}"
        )
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise SpiCaptureAuditError(f"{label} open handle is not a regular file")
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            total += len(chunk)
        after = os.fstat(stream.fileno())
    path_after = path.stat()
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    path_identity_after = (
        path_after.st_dev,
        path_after.st_ino,
        path_after.st_size,
        path_after.st_mtime_ns,
    )
    _require(
        identity_before == identity_after == path_identity_after
        and total == before.st_size,
        f"{label} changed while it was hashed",
    )
    return total, digest.hexdigest()


def _load_json(payload: bytes) -> Mapping[str, Any]:
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SpiCaptureAuditError("capture JSON is not UTF-8") from error
    try:
        value = json.loads(decoded, object_pairs_hook=_pairs_without_duplicates)
    except (json.JSONDecodeError, SpiCaptureAuditError) as error:
        if isinstance(error, SpiCaptureAuditError):
            raise
        raise SpiCaptureAuditError("capture JSON is malformed") from error
    if not isinstance(value, Mapping):
        raise SpiCaptureAuditError("capture JSON root must be an object")
    return value


def _parse_provenance(
    value: Any, *, raw_capture_sha256: str, raw_capture_bytes: int
) -> dict[str, str | int]:
    if not isinstance(value, Mapping):
        raise SpiCaptureAuditError("provenance must be an object")
    _require_exact_keys(
        value,
        {"decoder_name", "decoder_version", "raw_capture_bytes", "raw_capture_sha256"},
        "provenance",
    )
    decoder_name = _require_text(value["decoder_name"], "decoder_name")
    decoder_version = _require_text(value["decoder_version"], "decoder_version")
    declared_bytes = _require_int(value["raw_capture_bytes"], "raw_capture_bytes")
    declared_sha = value["raw_capture_sha256"]
    _require(
        isinstance(declared_sha, str) and SHA256_RE.fullmatch(declared_sha) is not None,
        "raw_capture_sha256 must be lowercase SHA-256",
    )
    _require(declared_bytes == raw_capture_bytes, "raw capture byte length mismatch")
    _require(declared_sha == raw_capture_sha256, "raw capture SHA-256 mismatch")
    return {
        "decoder_name": decoder_name,
        "decoder_version": decoder_version,
        "raw_capture_bytes": declared_bytes,
        "raw_capture_sha256": declared_sha,
    }


def _parse_decoder(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SpiCaptureAuditError("decoder_contract must be an object")
    expected = {
        "protocol": "SPI",
        "clock_mode": 0,
        "bit_order": "MSB_FIRST",
        "word_bits": 8,
        "cs_active_level": 0,
        "dc_command_level": 0,
        "dc_data_level": 1,
    }
    _require_exact_keys(value, set(expected), "decoder_contract")
    for key, wanted in expected.items():
        observed = value[key]
        if isinstance(wanted, int):
            _require_int(observed, f"decoder_contract.{key}")
        _require(observed == wanted, f"decoder_contract.{key} must equal {wanted!r}")
    return dict(expected)


def _parse_controllers(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SpiCaptureAuditError(f"{label} must be a controller array")
    controllers = tuple(value)
    _require(controllers in VALID_TARGETS, f"{label} is not canonical CS1/CS2/BOTH")
    return controllers


def _parse_runs(value: Any) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(value, list) or not value or len(value) > MAX_RUNS:
        raise SpiCaptureAuditError(f"runs must contain 1..{MAX_RUNS} entries")
    parsed: list[dict[str, Any]] = []
    next_frame = 0
    prior_end_ns = -1
    for index, item in enumerate(value):
        label = f"runs[{index}]"
        if not isinstance(item, Mapping):
            raise SpiCaptureAuditError(f"{label} must be an object")
        _require_exact_keys(
            item,
            {
                "controllers",
                "dc_level",
                "end_ns",
                "first_frame",
                "last_frame",
                "mosi_hex",
                "start_ns",
            },
            label,
        )
        controllers = _parse_controllers(item["controllers"], f"{label}.controllers")
        dc_level = _require_int(item["dc_level"], f"{label}.dc_level")
        _require(dc_level in (0, 1), f"{label}.dc_level must be 0 or 1")
        first_frame = _require_int(item["first_frame"], f"{label}.first_frame")
        last_frame = _require_int(item["last_frame"], f"{label}.last_frame")
        start_ns = _require_int(item["start_ns"], f"{label}.start_ns")
        end_ns = _require_int(item["end_ns"], f"{label}.end_ns")
        mosi_hex = item["mosi_hex"]
        _require(
            isinstance(mosi_hex, str) and HEX_RE.fullmatch(mosi_hex) is not None,
            f"{label}.mosi_hex must be nonempty canonical lowercase byte hex",
        )
        payload = bytes.fromhex(mosi_hex)
        _require(first_frame == next_frame, f"{label}.first_frame is not contiguous")
        _require(
            last_frame == first_frame + len(payload) - 1,
            f"{label}.last_frame does not bind every decoded byte",
        )
        _require(start_ns > prior_end_ns, f"{label} timestamp overlaps or is unordered")
        _require(end_ns > start_ns, f"{label}.end_ns must exceed start_ns")
        parsed.append(
            {
                "controllers": controllers,
                "dc_level": dc_level,
                "payload": payload,
                "first_frame": first_frame,
                "last_frame": last_frame,
                "start_ns": start_ns,
                "end_ns": end_ns,
            }
        )
        next_frame = last_frame + 1
        prior_end_ns = end_ns
    return parsed, next_frame


def _reconstruct_transactions(runs: Iterable[Mapping[str, Any]]) -> list[Transaction]:
    transactions: list[Transaction] = []
    pending_controllers: tuple[str, ...] | None = None
    pending_command: int | None = None
    pending_payload = bytearray()

    def finish() -> None:
        nonlocal pending_controllers, pending_command, pending_payload
        if pending_controllers is not None and pending_command is not None:
            transactions.append(
                Transaction(
                    pending_controllers, pending_command, bytes(pending_payload)
                )
            )
        pending_controllers = None
        pending_command = None
        pending_payload = bytearray()

    for index, run in enumerate(runs):
        controllers = run["controllers"]
        payload = run["payload"]
        if run["dc_level"] == 0:
            _require(
                len(payload) == 1,
                f"command run {index} must contain exactly one decoded byte",
            )
            finish()
            pending_controllers = controllers
            pending_command = payload[0]
        else:
            _require(pending_command is not None, f"data run {index} has no command")
            _require(
                controllers == pending_controllers,
                f"data run {index} changes controller selection within a transaction",
            )
            pending_payload.extend(payload)
    finish()
    _require(transactions, "capture contains no reconstructed command transactions")
    return transactions


def _hypotheses(profile_id: str) -> dict[str, Hypothesis]:
    material = profile_pack.load_profile(profile_id)
    plain = material.plaintext
    result = {
        "H1_overlapping_eight_rows": Hypothesis(
            "H1_overlapping_eight_rows", plain[:535], plain[95:799]
        ),
        "H2_extension_slots_5_to_7": Hypothesis(
            "H2_extension_slots_5_to_7", plain[:535], b"\xff" * 440 + plain[535:799]
        ),
        "H3_full_799_r20_ff_r21": Hypothesis(
            "H3_full_799_r20_ff_r21", plain[:799], b"\xff" * 704
        ),
    }
    signatures = [item.signature for item in result.values()]
    _require(
        len(signatures) == len(set(signatures)), "H1/H2/H3 signatures became ambiguous"
    )
    return result


def _classify_waveform(
    transactions: list[Transaction], profile_id: str
) -> tuple[Hypothesis, dict[str, Any]]:
    _require(len(transactions) >= 25, "capture is truncated before both LUT uploads")
    pairs: dict[str, tuple[Transaction, Transaction]] = {
        "CS1": (transactions[20], transactions[21]),
        "CS2": (transactions[23], transactions[24]),
    }
    observed_signatures: dict[str, tuple[int, str, int, str]] = {}
    for controller, (r20, r21) in pairs.items():
        wanted_target = (controller,)
        _require(
            r20.controllers == wanted_target and r20.command == 0x20,
            f"{controller} R20 transaction is missing or out of order",
        )
        _require(
            r21.controllers == wanted_target and r21.command == 0x21,
            f"{controller} R21 transaction is missing or out of order",
        )
        observed_signatures[controller] = (
            r20.parameter_bytes,
            r20.parameter_sha256,
            r21.parameter_bytes,
            r21.parameter_sha256,
        )
    _require(
        observed_signatures["CS1"] == observed_signatures["CS2"],
        "CS1 and CS2 received different LUT identities",
    )
    observed = observed_signatures["CS1"]
    matches = [
        item for item in _hypotheses(profile_id).values() if item.signature == observed
    ]
    _require(len(matches) == 1, "R20/R21 does not uniquely match H1, H2, or H3")
    hypothesis = matches[0]
    controller_report = {
        controller: {
            "r20_bytes": signature[0],
            "r20_sha256": signature[1],
            "r21_bytes": signature[2],
            "r21_sha256": signature[3],
        }
        for controller, signature in observed_signatures.items()
    }
    return hypothesis, controller_report


def _expected(profile_id: str, hypothesis: Hypothesis) -> list[ExpectedTransaction]:
    material = profile_pack.load_profile(profile_id)
    descriptor = runtime_contract.transaction_descriptor(
        profile_id, runtime_contract.ROLE_RUNTIME
    )
    dtm = descriptor["payload_identity"]

    def literal(
        controllers: tuple[str, ...], command: int, payload: bytes, label: str
    ) -> ExpectedTransaction:
        return ExpectedTransaction(
            controllers, command, len(payload), _sha256(payload), label
        )

    expected = [
        literal(BOTH, 0xAA, bytes.fromhex("495520080918"), "factory_init_magic"),
        literal(BOTH, 0x01, b"\x3f", "factory_init_pwr"),
        literal(BOTH, 0x00, bytes.fromhex("5f69"), "factory_init_psr"),
        literal(BOTH, 0x05, bytes.fromhex("401f1f2c"), "factory_init_btst1"),
        literal(BOTH, 0x08, bytes.fromhex("6f1f1f22"), "factory_init_btst3"),
        literal(BOTH, 0x06, bytes.fromhex("6f1f1717"), "factory_init_btst2"),
        literal(BOTH, 0x03, bytes.fromhex("00540044"), "factory_init_pofs"),
        literal(BOTH, 0x60, bytes.fromhex("0200"), "factory_init_tcon"),
        literal(BOTH, 0x30, b"\x08", "factory_init_pll"),
        literal(BOTH, 0x50, b"\x3f", "factory_init_cdi"),
        literal(BOTH, 0x61, bytes.fromhex("02000258"), "factory_init_tres"),
        literal(BOTH, 0xE3, b"\x2f", "factory_init_pws"),
        literal(BOTH, 0x84, b"\x01", "factory_init_t_vdcs"),
        literal(CS1, 0xE0, b"\x01", "cascade_enable_cs1"),
        literal(CS2, 0xE0, b"\x01", "cascade_enable_cs2"),
        literal(BOTH, 0x00, bytes.fromhex("5fe9"), "runtime_psr"),
        literal(BOTH, 0x01, material.power_payload, "runtime_pwr"),
        literal(BOTH, 0x30, material.pll_payload, "runtime_pll"),
        literal(BOTH, 0x61, bytes.fromhex("02000258"), "runtime_tres"),
        literal(CS1, 0xE9, b"\x01", "runtime_enable_cs1"),
        literal(CS1, 0x20, hypothesis.r20, "runtime_r20_cs1"),
        literal(CS1, 0x21, hypothesis.r21, "runtime_r21_cs1"),
        literal(CS2, 0xE9, b"\x01", "runtime_enable_cs2"),
        literal(CS2, 0x20, hypothesis.r20, "runtime_r20_cs2"),
        literal(CS2, 0x21, hypothesis.r21, "runtime_r21_cs2"),
        ExpectedTransaction(
            CS1,
            0x10,
            int(dtm["cs1_dtm_bytes"]),
            str(dtm["cs1_dtm_sha256"]),
            "atlas_dtm_cs1",
        ),
        ExpectedTransaction(
            CS2,
            0x10,
            int(dtm["cs2_dtm_bytes"]),
            str(dtm["cs2_dtm_sha256"]),
            "atlas_dtm_cs2",
        ),
        literal(BOTH, 0x04, b"", "power_on"),
        literal(BOTH, 0x06, bytes.fromhex("6f1f1749"), "refresh_btst2"),
        literal(BOTH, 0x12, b"\x00", "display_refresh"),
        literal(BOTH, 0x02, b"\x00", "power_off"),
        literal(BOTH, 0x00, bytes.fromhex("4f6e"), "post_power_off_psr"),
    ]
    _require(len(expected) == 32, "internal expected transaction count changed")
    return expected


def _audit_exact_sequence(
    transactions: list[Transaction], expected: list[ExpectedTransaction]
) -> list[dict[str, Any]]:
    forbidden = [
        (index, transaction.command)
        for index, transaction in enumerate(transactions)
        if transaction.command in FORBIDDEN_OTP_PROGRAM_OPCODES
    ]
    _require(
        not forbidden, "capture contains forbidden OTP programming opcode 0x90/0x91"
    )
    _require(
        len(transactions) == len(expected),
        f"transaction count differs: expected {len(expected)}, observed {len(transactions)}",
    )
    metadata: list[dict[str, Any]] = []
    for index, (observed, wanted) in enumerate(zip(transactions, expected)):
        _require(
            observed.controllers == wanted.controllers,
            f"transaction {index} ({wanted.label}) controller selection differs",
        )
        _require(
            observed.command == wanted.command,
            f"transaction {index} ({wanted.label}) command differs",
        )
        _require(
            observed.parameter_bytes == wanted.parameter_bytes,
            f"transaction {index} ({wanted.label}) parameter length differs",
        )
        _require(
            observed.parameter_sha256 == wanted.parameter_sha256,
            f"transaction {index} ({wanted.label}) parameter identity differs",
        )
        metadata.append(
            {
                "ordinal": index + 1,
                "label": wanted.label,
                "controllers": list(wanted.controllers),
                "command": f"0x{wanted.command:02X}",
                "parameter_bytes": wanted.parameter_bytes,
                "parameter_sha256": wanted.parameter_sha256,
            }
        )
    return metadata


def audit_capture_document(
    document: Mapping[str, Any],
    *,
    profile_id: str,
    raw_capture_sha256: str,
    raw_capture_bytes: int,
    decoded_capture_sha256: str | None = None,
    decoded_capture_bytes: int | None = None,
) -> dict[str, Any]:
    """Validate one already-parsed strict capture document."""

    _require(profile_id in profile_pack.PROFILES, "profile must be selected explicitly")
    _require_exact_keys(
        document,
        {"decoder_contract", "kind", "provenance", "runs", "schema_version"},
        "capture root",
    )
    _require(document["kind"] == INPUT_KIND, "capture kind differs")
    schema_version = _require_int(document["schema_version"], "capture schema_version")
    _require(schema_version == SCHEMA_VERSION, "capture schema differs")
    provenance = _parse_provenance(
        document["provenance"],
        raw_capture_sha256=raw_capture_sha256,
        raw_capture_bytes=raw_capture_bytes,
    )
    decoder = _parse_decoder(document["decoder_contract"])
    runs, decoded_spi_bytes = _parse_runs(document["runs"])
    transactions = _reconstruct_transactions(runs)
    hypothesis, controllers = _classify_waveform(transactions, profile_id)
    expected = _expected(profile_id, hypothesis)
    transaction_metadata = _audit_exact_sequence(transactions, expected)

    descriptor = runtime_contract.transaction_descriptor(
        profile_id, runtime_contract.ROLE_RUNTIME
    )
    expected_h3 = descriptor["command_contract"]["h3"]
    h3_match = (
        hypothesis.hypothesis_id == "H3_full_799_r20_ff_r21"
        and len(hypothesis.r20) == expected_h3["r20_bytes"]
        and _sha256(hypothesis.r20) == expected_h3["r20_sha256"]
        and len(hypothesis.r21) == expected_h3["r21_bytes"]
        and _sha256(hypothesis.r21) == expected_h3["r21_sha256"]
    )
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "valid": True,
        "profile_id": profile_id,
        "capture_identity": {
            "decoded_capture_bytes": decoded_capture_bytes,
            "decoded_capture_sha256": decoded_capture_sha256,
            **provenance,
        },
        "decoder_contract": decoder,
        "capture_geometry": {
            "run_count": len(runs),
            "decoded_spi_byte_count": decoded_spi_bytes,
            "transaction_count": len(transactions),
            "frame_indices_contiguous": True,
            "timestamps_strictly_ordered": True,
            "dc_boundaries_reconstructed": True,
        },
        "initialization_and_refresh": {
            "exact_full_success_sequence": True,
            "factory_init_to_both": True,
            "cascade_enable_cs1_then_cs2": True,
            "runtime_global_config_to_both": True,
            "runtime_upload_order": ["CS1", "CS2"],
            "atlas_dtm_order": ["CS1", "CS2"],
            "pon_drf_pof_and_post_psr_present": True,
            "forbidden_otp_program_opcodes_present": False,
        },
        "waveform_classification": {
            "hypothesis_id": hypothesis.hypothesis_id,
            "unambiguous_h1_h2_h3_match": True,
            "controllers": controllers,
            "both_controllers_identical": True,
            "matches_frozen_empirical_h3_runtime_contract": h3_match,
            "same_version_mode1_abi_proven": False,
        },
        "transactions": transaction_metadata,
        "evidence_limits": {
            "input_layer": "decoded_spi_byte_runs_bound_to_raw_capture_sha256",
            "raw_logic_edges_redecoded_by_this_tool": False,
            "controller_internal_register_readback_performed": False,
            "controller_acceptance_proven": False,
            "secondary_controller_acceptance_from_single_busy_proven": False,
            "electrical_rails_or_panel_fpl_compatibility_proven": False,
            "wire_sequence_identity_only": True,
        },
        "safety": {
            "offline_read_only": True,
            "hardware_accessed": False,
            "serial_accessed": False,
            "device_network_accessed": False,
            "flash_written": False,
            "display_refreshed": False,
            "raw_parameter_bytes_emitted": False,
            "vendor_key_material_emitted": False,
        },
    }


def audit_capture_files(
    *, capture_path: Path, raw_capture_path: Path, profile_id: str
) -> dict[str, Any]:
    decoded = _read_regular_file(
        capture_path, "decoded capture JSON", maximum=MAX_CAPTURE_JSON_BYTES
    )
    raw_bytes, raw_sha256 = _hash_regular_file(raw_capture_path, "raw logic capture")
    document = _load_json(decoded)
    return audit_capture_document(
        document,
        profile_id=profile_id,
        raw_capture_sha256=raw_sha256,
        raw_capture_bytes=raw_bytes,
        decoded_capture_sha256=_sha256(decoded),
        decoded_capture_bytes=len(decoded),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--raw-capture", required=True, type=Path)
    parser.add_argument(
        "--profile", required=True, choices=sorted(profile_pack.PROFILES)
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = audit_capture_files(
            capture_path=args.capture,
            raw_capture_path=args.raw_capture,
            profile_id=args.profile,
        )
    except (OSError, SpiCaptureAuditError, profile_pack.ProfilePackError) as error:
        json.dump(
            {
                "kind": KIND,
                "schema_version": SCHEMA_VERSION,
                "valid": False,
                "error": str(error),
            },
            sys.stdout,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        sys.stdout.write("\n")
        return 2
    json.dump(report, sys.stdout, ensure_ascii=True, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
