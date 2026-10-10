#!/usr/bin/env python3
"""Offline compiled-symbol identity gate for the EC5 COLOR_LAB recovery ELF.

The gate resolves the exact local objects linked by the atlas and COLOR_LAB
drivers. Matching digest bytes elsewhere in the ELF are deliberately ignored.
It performs no device, serial, network, upload, or hardware action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_color_lab_recovery_contract as contract  # noqa: E402
from tools import mf1750_ec5_compiled_identity as elf_reader  # noqa: E402


def _local_object_symbol(name: str) -> str:
    return f"_ZN12_GLOBAL__N_1L{len(name)}{name}E"


SYMBOL_NAMES: Mapping[str, str] = {
    "atlas_frame": _local_object_symbol("EC8_ATLAS_FRAME_SHA256"),
    "atlas_cs1_dtm": _local_object_symbol("EC8_ATLAS_CS1_DTM_SHA256"),
    "atlas_cs2_dtm": _local_object_symbol("EC8_ATLAS_CS2_DTM_SHA256"),
    "white_frame": _local_object_symbol("EC8_WHITE_FRAME_SHA256"),
    "white_dtm": _local_object_symbol("EC8_WHITE_DTM_SHA256"),
    "u07_isolated_frame": _local_object_symbol(
        "CL_U07_ISOLATED_FRAME_SHA256"
    ),
    "u07_isolated_dtm": _local_object_symbol("CL_U07_ISOLATED_DTM_SHA256"),
    "sixstate_primer_frame": _local_object_symbol(
        "CL_SIXSTATE_PRIMER_FRAME_SHA256"
    ),
    "sixstate_primer_dtm": _local_object_symbol(
        "CL_SIXSTATE_PRIMER_DTM_SHA256"
    ),
    "u04_target_frame": _local_object_symbol("CL_U04_TARGET_FRAME_SHA256"),
    "u04_target_dtm": _local_object_symbol("CL_U04_TARGET_DTM_SHA256"),
    "u07_target_frame": _local_object_symbol("CL_U07_TARGET_FRAME_SHA256"),
    "u07_target_dtm": _local_object_symbol("CL_U07_TARGET_DTM_SHA256"),
}

ROLE_SYMBOL_KEYS: Mapping[str, Mapping[str, str]] = {
    contract.ROLE_WHITE: {
        "frame": "white_frame",
        "cs1_dtm": "white_dtm",
        "cs2_dtm": "white_dtm",
    },
    contract.ROLE_U07_ISOLATED: {
        "frame": "u07_isolated_frame",
        "cs1_dtm": "u07_isolated_dtm",
        "cs2_dtm": "u07_isolated_dtm",
    },
    contract.ROLE_ATLAS: {
        "frame": "atlas_frame",
        "cs1_dtm": "atlas_cs1_dtm",
        "cs2_dtm": "atlas_cs2_dtm",
    },
    contract.ROLE_U04_PRIMER: {
        "frame": "sixstate_primer_frame",
        "cs1_dtm": "sixstate_primer_dtm",
        "cs2_dtm": "sixstate_primer_dtm",
    },
    contract.ROLE_U04_TARGET: {
        "frame": "u04_target_frame",
        "cs1_dtm": "u04_target_dtm",
        "cs2_dtm": "u04_target_dtm",
    },
    contract.ROLE_U07_PRIMER: {
        "frame": "sixstate_primer_frame",
        "cs1_dtm": "sixstate_primer_dtm",
        "cs2_dtm": "sixstate_primer_dtm",
    },
    contract.ROLE_U07_TARGET: {
        "frame": "u07_target_frame",
        "cs1_dtm": "u07_target_dtm",
        "cs2_dtm": "u07_target_dtm",
    },
}


class ColorLabCompiledIdentityError(ValueError):
    """The COLOR_LAB ELF or its linked role identity failed closed."""


def _expected_symbol_payloads() -> dict[str, bytes]:
    expected: dict[str, bytes] = {}
    for role, fields in ROLE_SYMBOL_KEYS.items():
        identity = contract.ROLE_IDENTITIES[role]
        for field, key in fields.items():
            payload = bytes.fromhex(str(identity[field]["sha256"]))
            existing = expected.setdefault(key, payload)
            if existing != payload:
                raise ColorLabCompiledIdentityError(
                    f"contract assigns incompatible payloads to shared symbol {key}"
                )
    if set(expected) != set(SYMBOL_NAMES):
        raise ColorLabCompiledIdentityError(
            "compiled identity symbol map does not cover the complete role contract"
        )
    return expected


def validate(elf_file: Path) -> dict[str, Any]:
    try:
        resolved, payload = elf_reader._read_regular(  # noqa: SLF001
            Path(elf_file), label="COLOR_LAB ELF"
        )
        image = elf_reader.Elf32Image(payload, label=str(resolved))
        symbols = {
            key: image.runtime_symbol(symbol_name)
            for key, symbol_name in SYMBOL_NAMES.items()
        }
    except elf_reader.CompiledIdentityError as error:
        raise ColorLabCompiledIdentityError(
            f"compiled COLOR_LAB ELF identity gate failed: {error}"
        ) from error

    expected = _expected_symbol_payloads()
    for key, symbol in symbols.items():
        if symbol.payload != expected[key]:
            raise ColorLabCompiledIdentityError(
                f"compiled COLOR_LAB symbol {key} differs from the frozen role fixture: "
                f"expected {expected[key].hex()}, got {symbol.payload.hex()}"
            )

    roles: dict[str, Any] = {}
    for role, fields in ROLE_SYMBOL_KEYS.items():
        roles[role] = {
            field: {
                "symbol_key": key,
                "name": symbols[key].name,
                "sha256_bytes": symbols[key].payload.hex(),
            }
            for field, key in fields.items()
        }

    manifest = contract.campaign_manifest()
    return {
        "schema_version": 1,
        "kind": "mf1750-ec5-color-lab-recovery-compiled-identity-validation",
        "valid": True,
        "offline": True,
        "device_io_performed": False,
        "execution_eligible": False,
        "campaign_id": contract.CAMPAIGN_ID,
        "build_tag": contract.BUILD_TAG,
        "test_id": contract.TEST_ID,
        "contract_id": manifest["contract_id"],
        "action_count": len(contract.DESCRIPTORS),
        "elf_bytes": len(payload),
        "elf_sha256": hashlib.sha256(payload).hexdigest(),
        "symbols": {
            key: {
                "name": symbol.name,
                "size": symbol.size,
                "vma": f"0x{symbol.value:08X}",
                "section": symbol.section.name,
                "file_offset": symbol.file_offset,
                "sha256_bytes": symbol.payload.hex(),
            }
            for key, symbol in symbols.items()
        },
        "roles": roles,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--elf", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = validate(args.elf)
    except ColorLabCompiledIdentityError as error:
        print(f"COLOR_LAB compiled-identity error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
