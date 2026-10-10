#!/usr/bin/env python3
"""Offline BIN/ELF/source identity gate for the WF23 C23 images."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Final, Sequence


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_h3_c23_matched_control_contract as contract  # noqa: E402


SCHEMA_VERSION: Final = 1
KIND: Final = "mf1750-ec5-h3-c23-matched-control-compiled-identity"
MAX_BINARY_BYTES: Final = 4_000_000
MAX_ELF_BYTES: Final = 32_000_000
MAX_SOURCE_BYTES: Final = 2_000_000
APP_DESCRIPTOR_OFFSET: Final = 32
APP_DESCRIPTOR_MAGIC: Final = bytes.fromhex("3254cdab")
EMBEDDED_ELF_SHA256_OFFSET: Final = 176

# Only the dedicated transaction source is checked for semantic tokens.
# Arbitrary ELF/BIN byte values 0x20 and 0x21 are not meaningful opcodes.
CONTROL_SOURCE_FORBIDDEN: Final = re.compile(
    rb"(?i)(?:\b0x0*20\b|\b0x0*21\b|\bkR20\w*|\bkR21\w*|"
    rb"\bR20_PAYLOAD\b|\bR21_PAYLOAD\b)"
)


class C23CompiledIdentityError(ValueError):
    """A C23 firmware artifact failed closed."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_regular(path: Path, *, label: str, maximum: int) -> tuple[Path, bytes]:
    candidate = Path(path)
    try:
        before = candidate.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise C23CompiledIdentityError(
                f"{label} must be a non-symlink regular file"
            )
        if before.st_size <= 0 or before.st_size > maximum:
            raise C23CompiledIdentityError(f"{label} size is invalid")
        payload = candidate.read_bytes()
        after = candidate.lstat()
    except OSError as error:
        raise C23CompiledIdentityError(f"could not read {label}: {error}") from error
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
        raise C23CompiledIdentityError(f"{label} changed while being read")
    return candidate.resolve(strict=True), payload


def _different_files(left: Path, right: Path, *, label: str) -> None:
    try:
        if os.path.samefile(left, right):
            raise C23CompiledIdentityError(f"{label} must be different files")
    except OSError as error:
        raise C23CompiledIdentityError(f"could not compare {label}: {error}") from error


def _require_count(payload: bytes, marker: bytes, count: int, *, label: str) -> None:
    observed = payload.count(marker)
    if observed != count:
        raise C23CompiledIdentityError(
            f"{label} occurrence count is {observed}, expected {count}"
        )


def _require_present(payload: bytes, text: str, *, label: str) -> None:
    if text.encode("ascii") not in payload:
        raise C23CompiledIdentityError(f"{label} {text!r} is absent")


def _require_unique_source_marker(source: bytes, marker: bytes, *, label: str) -> None:
    normalized = re.sub(rb'"\s*"', b"", source)
    _require_count(normalized, marker, 1, label=label)


def _binary_elf_link(binary: bytes, elf: bytes) -> dict[str, Any]:
    selected = hashlib.sha256(elf).digest()
    end = EMBEDDED_ELF_SHA256_OFFSET + len(selected)
    if (
        len(binary) < end
        or binary[0] != 0xE9
        or not elf.startswith(b"\x7fELF")
        or binary[
            APP_DESCRIPTOR_OFFSET : APP_DESCRIPTOR_OFFSET + len(APP_DESCRIPTOR_MAGIC)
        ]
        != APP_DESCRIPTOR_MAGIC
        or binary[EMBEDDED_ELF_SHA256_OFFSET:end] != selected
    ):
        raise C23CompiledIdentityError(
            "C23 firmware BIN app descriptor does not bind the selected exact ELF"
        )
    return {
        "app_descriptor_offset": APP_DESCRIPTOR_OFFSET,
        "app_descriptor_magic_hex": APP_DESCRIPTOR_MAGIC.hex(),
        "embedded_elf_sha256_offset": EMBEDDED_ELF_SHA256_OFFSET,
        "embedded_elf_sha256": selected.hex(),
        "selected_elf_sha256": selected.hex(),
        "exact_match": True,
    }


def _record(path: Path, payload: bytes) -> dict[str, Any]:
    return {"path": str(path), "bytes": len(payload), "sha256": _sha256(payload)}


def _required_ascii(profile_id: str, role: str) -> tuple[str, ...]:
    frozen = contract.validate_contract(profile_id)
    action = next(item for item in frozen["actions"] if item["role"] == role)
    descriptor = contract.transaction_descriptor(profile_id, role)
    device = contract.device_binding(profile_id, role)
    identity = descriptor["payload_identity"]
    common = (
        contract.compiled_descriptor_marker(profile_id, role),
        contract.command_audit_marker(profile_id, role),
        profile_id,
        contract.CAMPAIGN_ID,
        contract.DEVICE_API_VERSION,
        frozen["contract_id"],
        descriptor["environment"],
        descriptor["nvs_namespace"],
        device["build_tag"],
        device["test_id"],
        device["base_route"],
        device["arm_intent"],
        device["execute_intent"],
        action["hardware_action_id"],
        action["transaction_descriptor_sha256"],
        identity["frame_sha256"],
        identity["cs1_dtm_sha256"],
        identity["cs2_dtm_sha256"],
    )
    if role == contract.ROLE_CONTROL:
        return (*common, contract.CONTROL_DESIGN, "NO_DETECTABLE_INCREMENTAL_EFFECT")
    return common


def _forbidden_runtime_payload_ascii() -> tuple[str, ...]:
    row = contract.profile_row()
    return (
        Path(row["reference_generated_include"]).name,
        row["reference_generated_include_sha256"],
        row["reference_r20_sha256"],
        row["reference_r21_sha256"],
        "kR20Payload",
        "kR21Payload",
    )


def validate_image(
    profile_id: str,
    role: str,
    *,
    elf_file: Path,
    binary_file: Path,
    transaction_source_file: Path,
) -> dict[str, Any]:
    """Deep-validate one exact, one-action C23 image offline."""

    contract.validate_contract(profile_id)
    if role not in contract.ROLES:
        raise C23CompiledIdentityError(f"unsupported C23 image role {role!r}")
    elf_path, elf = _read_regular(elf_file, label=f"{role} ELF", maximum=MAX_ELF_BYTES)
    binary_path, binary = _read_regular(
        binary_file, label=f"{role} BIN", maximum=MAX_BINARY_BYTES
    )
    source_path, source = _read_regular(
        transaction_source_file,
        label=f"{role} transaction source",
        maximum=MAX_SOURCE_BYTES,
    )
    _different_files(elf_path, binary_path, label=f"{role} ELF and BIN")
    try:
        source.decode("utf-8")
    except UnicodeDecodeError as error:
        raise C23CompiledIdentityError(
            f"{role} transaction source must be UTF-8"
        ) from error

    binary_elf_link = _binary_elf_link(binary, elf)
    descriptor = contract.transaction_descriptor(profile_id, role)
    descriptor_marker = contract.compiled_descriptor_marker(profile_id, role).encode(
        "ascii"
    )
    audit_marker = contract.command_audit_marker(profile_id, role).encode("ascii")
    _require_unique_source_marker(
        source, descriptor_marker, label=f"{role} source descriptor marker"
    )
    _require_unique_source_marker(
        source, audit_marker, label=f"{role} source command-audit marker"
    )
    _require_count(elf, descriptor_marker, 1, label=f"{role} ELF descriptor marker")
    _require_count(elf, audit_marker, 1, label=f"{role} ELF command-audit marker")
    for text in _required_ascii(profile_id, role):
        _require_present(elf, text, label=f"{role} ELF dedicated identity")

    for text in _forbidden_runtime_payload_ascii():
        encoded = text.encode("ascii")
        if encoded in source or encoded in elf:
            raise C23CompiledIdentityError(
                f"{role} image contains forbidden T23 payload marker {text!r}"
            )
    if role == contract.ROLE_CONTROL:
        match = CONTROL_SOURCE_FORBIDDEN.search(source)
        if match is not None:
            raise C23CompiledIdentityError(
                "C23 transaction source contains a forbidden R20/R21 token"
            )
    else:
        control_descriptor = contract.compiled_descriptor_marker(
            profile_id, contract.ROLE_CONTROL
        ).encode("ascii")
        if control_descriptor in source or control_descriptor in elf:
            raise C23CompiledIdentityError(
                "C23 recovery image contains the control descriptor"
            )

    action = next(
        item
        for item in contract.validate_contract(profile_id)["actions"]
        if item["role"] == role
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "valid": True,
        "offline": True,
        "profile_id": profile_id,
        "role": role,
        "environment": descriptor["environment"],
        "nvs_namespace": descriptor["nvs_namespace"],
        "hardware_action_id": action["hardware_action_id"],
        "one_compiled_visible_action": True,
        "transaction_descriptor": descriptor,
        "transaction_descriptor_sha256": contract.sha256(descriptor),
        "compiled_descriptor_marker": descriptor_marker.decode("ascii"),
        "compiled_command_audit_marker": audit_marker.decode("ascii"),
        "firmware": {
            "elf": _record(elf_path, elf),
            "binary": _record(binary_path, binary),
            "binary_elf_link": binary_elf_link,
            "transaction_source": _record(source_path, source),
            "generated_include": None,
        },
        "command_surface_verification": {
            "method": (
                "dedicated_source_and_ELF_descriptor_plus_control_source_token_gate"
            ),
            "transaction_source_r20_r21_tokens_absent": role == contract.ROLE_CONTROL,
            "t23_generated_payload_markers_absent_from_source_and_elf": True,
            "whole_binary_opcode_absence_scan_performed": False,
            "whole_binary_opcode_absence_is_meaningful": False,
        },
        "device_io_performed": False,
        "serial_io_performed": False,
        "network_io_performed": False,
        "upload_performed": False,
        "visible_refreshes": 0,
        "live_authorized": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--profile", choices=contract.PROFILES, required=True)
    parser.add_argument("--role", choices=contract.ROLES, required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--transaction-source", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = validate_image(
            args.profile,
            args.role,
            elf_file=args.elf,
            binary_file=args.binary,
            transaction_source_file=args.transaction_source,
        )
    except C23CompiledIdentityError as error:
        print(f"C23 compiled-identity error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
