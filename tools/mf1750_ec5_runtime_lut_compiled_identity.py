#!/usr/bin/env python3
"""Validate exact BIN/ELF identities for one empirical-H3 campaign image.

This is an offline gate.  It validates a dedicated transaction descriptor
compiled into the selected ELF and the ESP32 app-descriptor binding from BIN
to ELF.  It intentionally does *not* infer command safety from arbitrary byte
absence in the firmware binary: waveform data may naturally contain any byte,
including values that are also controller opcodes.
"""

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

from tools import mf1750_ec5_runtime_lut_contract as contract


SCHEMA_VERSION: Final = 1
KIND: Final = "mf1750-ec5-empirical-h3-compiled-identity"
MAX_BINARY_BYTES: Final = 4_000_000
MAX_ELF_BYTES: Final = 32_000_000
MAX_SOURCE_BYTES: Final = 2_000_000
MAX_INCLUDE_BYTES: Final = 2_000_000
APP_DESCRIPTOR_OFFSET: Final = 32
APP_DESCRIPTOR_MAGIC: Final = bytes.fromhex("3254cdab")
EMBEDDED_ELF_SHA256_OFFSET: Final = 176


class RuntimeLutCompiledIdentityError(ValueError):
    """The selected build artifacts do not satisfy the exact offline gate."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_regular(path: Path, *, label: str, maximum: int) -> tuple[Path, bytes]:
    candidate = Path(path)
    try:
        before = candidate.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise RuntimeLutCompiledIdentityError(
                f"{label} must be a non-symlink regular file"
            )
        if before.st_size <= 0 or before.st_size > maximum:
            raise RuntimeLutCompiledIdentityError(f"{label} size is invalid")
        payload = candidate.read_bytes()
        after = candidate.lstat()
    except OSError as error:
        raise RuntimeLutCompiledIdentityError(
            f"could not read {label}: {error}"
        ) from error
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
    if identity_before != identity_after or len(payload) != after.st_size:
        raise RuntimeLutCompiledIdentityError(f"{label} changed while being read")
    return candidate.resolve(strict=True), payload


def _different_files(left: Path, right: Path, *, label: str) -> None:
    try:
        if os.path.samefile(left, right):
            raise RuntimeLutCompiledIdentityError(f"{label} must be different files")
    except OSError as error:
        raise RuntimeLutCompiledIdentityError(
            f"could not compare {label}: {error}"
        ) from error


def _require_count(payload: bytes, marker: bytes, count: int, *, label: str) -> None:
    observed = payload.count(marker)
    if observed != count:
        raise RuntimeLutCompiledIdentityError(
            f"{label} occurrence count is {observed}, expected {count}"
        )


def _require_present(payload: bytes, marker: bytes, *, label: str) -> None:
    if marker not in payload:
        raise RuntimeLutCompiledIdentityError(f"{label} is absent")


def _require_unique_source_marker(source: bytes, marker: bytes, *, label: str) -> None:
    # C/C++ commonly splits a long literal into adjacent quoted fragments.
    # Removing only quote/whitespace/quote boundaries reproduces that exact
    # language concatenation without making ordinary identity strings unique.
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
        raise RuntimeLutCompiledIdentityError(
            "firmware BIN app descriptor does not bind the selected exact ELF"
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


def _runtime_required_ascii(profile_id: str) -> tuple[str, ...]:
    row = contract.profile_row(profile_id)
    frozen = contract.validate_contract(profile_id)
    actions = {item["role"]: item for item in frozen["actions"]}
    device = contract.device_binding(profile_id, contract.ROLE_RUNTIME)
    descriptor = contract.transaction_descriptor(profile_id, contract.ROLE_RUNTIME)
    identity = descriptor["payload_identity"]
    return (
        contract.compiled_descriptor_marker(profile_id, contract.ROLE_RUNTIME),
        frozen["contract_id"],
        actions[contract.ROLE_RUNTIME]["hardware_action_id"],
        actions[contract.ROLE_WHITE]["hardware_action_id"],
        profile_id,
        row["runtime_environment"],
        row["runtime_nvs_namespace"],
        device["build_tag"],
        device["test_id"],
        device["campaign_id"],
        device["base_route"],
        device["arm_intent"],
        device["execute_intent"],
        row["generated_include_sha256"],
        row["r20_sha256"],
        row["r21_sha256"],
        identity["frame_sha256"],
        identity["cs1_dtm_sha256"],
        identity["cs2_dtm_sha256"],
    )


def _recovery_required_ascii(profile_id: str) -> tuple[str, ...]:
    row = contract.profile_row(profile_id)
    frozen = contract.validate_contract(profile_id)
    recovery_action = next(
        item for item in frozen["actions"] if item["role"] == contract.ROLE_WHITE
    )
    device = contract.device_binding(profile_id, contract.ROLE_WHITE)
    descriptor = contract.transaction_descriptor(profile_id, contract.ROLE_WHITE)
    identity = descriptor["payload_identity"]
    return (
        contract.compiled_descriptor_marker(profile_id, contract.ROLE_WHITE),
        frozen["contract_id"],
        recovery_action["hardware_action_id"],
        profile_id,
        row["recovery_environment"],
        row["recovery_nvs_namespace"],
        device["build_tag"],
        device["test_id"],
        device["campaign_id"],
        device["base_route"],
        device["arm_intent"],
        device["execute_intent"],
        identity["frame_sha256"],
        identity["cs1_dtm_sha256"],
        identity["cs2_dtm_sha256"],
    )


def _recovery_forbidden_ascii() -> tuple[str, ...]:
    result = [
        "kR20Payload",
        "kR21Payload",
        contract.ROLE_RUNTIME,
    ]
    for profile_id in contract.PROFILES:
        row = contract.profile_row(profile_id)
        result.extend(
            (
                Path(row["generated_include"]).name,
                row["generated_include_sha256"],
                row["r20_sha256"],
            )
        )
    return tuple(result)


def validate_image(
    profile_id: str,
    role: str,
    *,
    elf_file: Path,
    binary_file: Path,
    transaction_source_file: Path,
    generated_include_file: Path | None = None,
) -> dict[str, Any]:
    """Validate one one-action image and return exact immutable identities."""

    contract.validate_contract(profile_id)
    if role not in contract.ROLES:
        raise RuntimeLutCompiledIdentityError(f"unsupported image role {role!r}")
    row = contract.profile_row(profile_id)
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
        raise RuntimeLutCompiledIdentityError(
            f"{role} transaction source must be UTF-8"
        ) from error

    binary_elf_link = _binary_elf_link(binary, elf)
    descriptor = contract.transaction_descriptor(profile_id, role)
    marker = contract.compiled_descriptor_marker(profile_id, role).encode("ascii")
    _require_unique_source_marker(
        source, marker, label=f"{role} source descriptor marker"
    )
    _require_count(elf, marker, 1, label=f"{role} ELF descriptor marker")

    include_record: dict[str, Any] | None = None
    if role == contract.ROLE_RUNTIME:
        if generated_include_file is None:
            raise RuntimeLutCompiledIdentityError(
                "runtime image requires the exact generated profile include"
            )
        include_path, include = _read_regular(
            generated_include_file,
            label="generated H3 include",
            maximum=MAX_INCLUDE_BYTES,
        )
        expected_include = (contract.REPO_ROOT / row["generated_include"]).resolve()
        if include_path != expected_include:
            raise RuntimeLutCompiledIdentityError(
                "runtime generated include path is not the selected frozen profile"
            )
        if _sha256(include) != row["generated_include_sha256"]:
            raise RuntimeLutCompiledIdentityError(
                "runtime generated include hash differs"
            )
        for text in _runtime_required_ascii(profile_id):
            _require_present(
                elf,
                text.encode("ascii"),
                label=f"runtime ELF dedicated identity {text}",
            )
        include_record = _record(include_path, include)
    else:
        if generated_include_file is not None:
            raise RuntimeLutCompiledIdentityError(
                "factory-OTP recovery must not accept a runtime generated include"
            )
        for text in _recovery_required_ascii(profile_id):
            _require_present(
                elf,
                text.encode("ascii"),
                label=f"recovery ELF dedicated identity {text}",
            )
        for text in _recovery_forbidden_ascii():
            marker_bytes = text.encode("ascii")
            if marker_bytes in source or marker_bytes in elf:
                raise RuntimeLutCompiledIdentityError(
                    f"recovery image contains forbidden runtime marker {text}"
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
        "one_compiled_visible_action": True,
        "transaction_descriptor": descriptor,
        "transaction_descriptor_sha256": contract.sha256(descriptor),
        "compiled_descriptor_marker": marker.decode("ascii"),
        "firmware": {
            "elf": _record(elf_path, elf),
            "binary": _record(binary_path, binary),
            "binary_elf_link": binary_elf_link,
            "transaction_source": _record(source_path, source),
            "generated_include": include_record,
        },
        "opcode_verification_scope": {
            "method": "dedicated_source_and_compiled_ELF_transaction_descriptor",
            "whole_binary_opcode_absence_scan_performed": False,
            "reason": "runtime LUT payload bytes may naturally equal opcode values",
            "arbitrary_payload_byte_values_allowed": True,
        },
        "device_io_performed": False,
        "serial_io_performed": False,
        "network_io_performed": False,
        "upload_performed": False,
        "visible_refreshes": 0,
        "live_authorized": False,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--profile", choices=contract.PROFILES, required=True)
    parser.add_argument("--role", choices=contract.ROLES, required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--transaction-source", type=Path, required=True)
    parser.add_argument("--generated-include", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = validate_image(
            args.profile,
            args.role,
            elf_file=args.elf,
            binary_file=args.binary,
            transaction_source_file=args.transaction_source,
            generated_include_file=args.generated_include,
        )
    except RuntimeLutCompiledIdentityError as error:
        print(f"runtime-LUT compiled-identity error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
