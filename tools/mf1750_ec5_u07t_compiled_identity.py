#!/usr/bin/env python3
"""Offline compiled-symbol identity gate for the independent U07T ELF."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_compiled_identity as elf_reader  # noqa: E402
from tools import mf1750_ec5_u07t_identity as identity  # noqa: E402


FRAME_SYMBOL = "_ZN12_GLOBAL__N_1L16EC5_FRAME_SHA256E"
DTM_SYMBOL = "_ZN12_GLOBAL__N_1L14EC5_DTM_SHA256E"


class U07TCompiledIdentityError(ValueError):
    """The U07T ELF or linked runtime identity failed closed."""


def validate(elf_file: Path) -> dict[str, Any]:
    try:
        resolved, payload = elf_reader._read_regular(  # noqa: SLF001
            Path(elf_file), label="U07T ELF"
        )
        image = elf_reader.Elf32Image(payload, label=str(resolved))
        symbols = {
            "frame_sha256": image.runtime_symbol(FRAME_SYMBOL),
            "dtm_sha256": image.runtime_symbol(DTM_SYMBOL),
        }
    except elf_reader.CompiledIdentityError as error:
        raise U07TCompiledIdentityError(
            f"compiled U07T ELF identity gate failed: {error}"
        ) from error
    wanted = {
        "frame_sha256": bytes.fromhex(identity.FRAME_SHA256),
        "dtm_sha256": bytes.fromhex(identity.DTM_SHA256),
    }
    for key, symbol in symbols.items():
        if symbol.payload != wanted[key]:
            raise U07TCompiledIdentityError(
                f"compiled U07T {key} differs from frozen fixture"
            )
    return {
        "schema_version": 1,
        "kind": "mf1750-ec5-u07t-compiled-identity-validation",
        "valid": True,
        "offline": True,
        "device_io_performed": False,
        "classification": "TECHNICAL_DESCRIPTIVE_NOT_QUALIFIED",
        "action_id": identity.FROZEN_ACTION_ID,
        "elf_bytes": len(payload),
        "elf_sha256": hashlib.sha256(payload).hexdigest(),
        "symbols": {
            key: {
                "name": symbol.name,
                "size": symbol.size,
                "section": symbol.section.name,
                "file_offset": symbol.file_offset,
                "sha256_bytes": symbol.payload.hex(),
            }
            for key, symbol in symbols.items()
        },
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--elf", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = validate(args.elf)
    except U07TCompiledIdentityError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
