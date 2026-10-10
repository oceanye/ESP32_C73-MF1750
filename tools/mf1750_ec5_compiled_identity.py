#!/usr/bin/env python3
"""Validate Stage-A EC5 identities from the symbols in compiled Xtensa ELFs.

This gate is deliberately offline.  It reads the ELF symbol table and extracts
the bytes owned by the runtime ``EC5_FRAME_SHA256`` and ``EC5_DTM_SHA256``
objects.  A matching byte sequence elsewhere in the file is irrelevant.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Mapping, Sequence


ELF_HEADER = struct.Struct("<16sHHIIIIIHHHHHH")
SECTION_HEADER = struct.Struct("<IIIIIIIIII")
SYMBOL_ENTRY = struct.Struct("<IIIBBH")

ELF_MAGIC = b"\x7fELF"
ELFCLASS32 = 1
ELFDATA2LSB = 1
EM_XTENSA = 94
SHT_SYMTAB = 2
SHT_STRTAB = 3
SHT_NOBITS = 8
STB_LOCAL = 0
STT_OBJECT = 1
MAX_ELF_BYTES = 64 * 1024 * 1024

WIDTH = 1024
HEIGHT = 600
ROW_BYTES = WIDTH // 2
FRAME_BYTES = ROW_BYTES * HEIGHT
CONTROLLER_ROW_BYTES = (WIDTH // 2) // 2
ROI_Y0 = 268
ROI_Y1 = 332
ROI_X_RANGES = ((224, 288), (736, 800))

FRAME_SYMBOL = "_ZN12_GLOBAL__N_1L16EC5_FRAME_SHA256E"
DTM_SYMBOL = "_ZN12_GLOBAL__N_1L14EC5_DTM_SHA256E"
RUNTIME_SYMBOLS: Mapping[str, str] = {
    "frame_sha256": FRAME_SYMBOL,
    "dtm_sha256": DTM_SYMBOL,
}


class CompiledIdentityError(ValueError):
    """The ELF or its compiled EC5 identity failed closed."""


@dataclass(frozen=True)
class Section:
    index: int
    name: str
    section_type: int
    flags: int
    address: int
    offset: int
    size: int
    link: int
    info: int
    alignment: int
    entry_size: int


@dataclass(frozen=True)
class RuntimeSymbol:
    name: str
    value: int
    size: int
    binding: int
    symbol_type: int
    section: Section
    file_offset: int
    payload: bytes


def _slice(payload: bytes, offset: int, size: int, *, label: str) -> bytes:
    if offset < 0 or size < 0 or offset > len(payload) or size > len(payload) - offset:
        raise CompiledIdentityError(f"{label} exceeds the ELF file")
    return payload[offset : offset + size]


def _cstring(payload: bytes, offset: int, *, label: str) -> str:
    if offset < 0 or offset >= len(payload):
        raise CompiledIdentityError(f"{label} offset is outside its string table")
    end = payload.find(b"\0", offset)
    if end < 0:
        raise CompiledIdentityError(f"{label} is not NUL terminated")
    try:
        return payload[offset:end].decode("ascii")
    except UnicodeDecodeError as error:
        raise CompiledIdentityError(f"{label} is not ASCII") from error


def _read_regular(path: Path, *, label: str) -> tuple[Path, bytes]:
    path = Path(path)
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise CompiledIdentityError(f"{label} must be a non-symlink regular file")
        if before.st_size <= 0 or before.st_size > MAX_ELF_BYTES:
            raise CompiledIdentityError(f"{label} has an invalid size")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise CompiledIdentityError(f"could not read {label}: {error}") from error
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_identity != after_identity or len(payload) != after.st_size:
        raise CompiledIdentityError(f"{label} changed while it was read")
    return path.resolve(strict=True), payload


class Elf32Image:
    """Small fail-closed reader for the linked ESP32-S3 ELF format."""

    def __init__(self, payload: bytes, *, label: str) -> None:
        self.payload = payload
        self.label = label
        self.sections = self._parse_sections()

    def _parse_sections(self) -> tuple[Section, ...]:
        if len(self.payload) < ELF_HEADER.size:
            raise CompiledIdentityError(f"{self.label} is shorter than an ELF header")
        (
            ident,
            _elf_type,
            machine,
            version,
            _entry,
            _program_offset,
            section_offset,
            _flags,
            header_size,
            _program_entry_size,
            _program_count,
            section_entry_size,
            section_count,
            section_name_index,
        ) = ELF_HEADER.unpack_from(self.payload)
        if ident[:4] != ELF_MAGIC:
            raise CompiledIdentityError(f"{self.label} is not an ELF file")
        if ident[4] != ELFCLASS32 or ident[5] != ELFDATA2LSB or ident[6] != 1:
            raise CompiledIdentityError(
                f"{self.label} must be a 32-bit little-endian ELF v1 image"
            )
        if machine != EM_XTENSA or version != 1:
            raise CompiledIdentityError(f"{self.label} is not an Xtensa ELF v1 image")
        if header_size != ELF_HEADER.size or section_entry_size != SECTION_HEADER.size:
            raise CompiledIdentityError(f"{self.label} uses an unsupported ELF header size")
        if section_count <= 0 or section_name_index <= 0 or section_name_index >= section_count:
            raise CompiledIdentityError(f"{self.label} has invalid section metadata")
        raw_headers = []
        for index in range(section_count):
            offset = section_offset + index * section_entry_size
            raw = _slice(
                self.payload,
                offset,
                SECTION_HEADER.size,
                label=f"{self.label} section header {index}",
            )
            raw_headers.append(SECTION_HEADER.unpack(raw))
        name_header = raw_headers[section_name_index]
        if name_header[1] != SHT_STRTAB:
            raise CompiledIdentityError(f"{self.label} section-name table is not STRTAB")
        names = _slice(
            self.payload,
            name_header[4],
            name_header[5],
            label=f"{self.label} section-name table",
        )
        sections = []
        for index, raw in enumerate(raw_headers):
            (
                name_offset,
                section_type,
                flags,
                address,
                offset,
                size,
                link,
                info,
                alignment,
                entry_size,
            ) = raw
            name = _cstring(names, name_offset, label=f"{self.label} section {index} name")
            if section_type != SHT_NOBITS:
                _slice(
                    self.payload,
                    offset,
                    size,
                    label=f"{self.label} section {name or index}",
                )
            sections.append(
                Section(
                    index,
                    name,
                    section_type,
                    flags,
                    address,
                    offset,
                    size,
                    link,
                    info,
                    alignment,
                    entry_size,
                )
            )
        return tuple(sections)

    def runtime_symbol(self, exact_name: str) -> RuntimeSymbol:
        matches: list[RuntimeSymbol] = []
        for symtab in self.sections:
            if symtab.section_type != SHT_SYMTAB:
                continue
            if symtab.entry_size != SYMBOL_ENTRY.size or symtab.size % symtab.entry_size:
                raise CompiledIdentityError(
                    f"{self.label} symbol table {symtab.name} has an invalid entry size"
                )
            if symtab.link <= 0 or symtab.link >= len(self.sections):
                raise CompiledIdentityError(
                    f"{self.label} symbol table {symtab.name} has an invalid string-table link"
                )
            strings_section = self.sections[symtab.link]
            if strings_section.section_type != SHT_STRTAB:
                raise CompiledIdentityError(
                    f"{self.label} symbol table {symtab.name} does not link to STRTAB"
                )
            strings = _slice(
                self.payload,
                strings_section.offset,
                strings_section.size,
                label=f"{self.label} symbol strings",
            )
            for offset in range(0, symtab.size, symtab.entry_size):
                entry_offset = symtab.offset + offset
                entry = _slice(
                    self.payload,
                    entry_offset,
                    SYMBOL_ENTRY.size,
                    label=f"{self.label} symbol entry",
                )
                name_offset, value, size, info, _other, section_index = SYMBOL_ENTRY.unpack(
                    entry
                )
                name = _cstring(strings, name_offset, label=f"{self.label} symbol name")
                if name != exact_name:
                    continue
                if section_index <= 0 or section_index >= len(self.sections):
                    raise CompiledIdentityError(
                        f"{self.label} runtime symbol {exact_name} has no file-backed section"
                    )
                section = self.sections[section_index]
                if section.section_type == SHT_NOBITS:
                    raise CompiledIdentityError(
                        f"{self.label} runtime symbol {exact_name} is in NOBITS"
                    )
                if value < section.address or size > section.size - (value - section.address):
                    raise CompiledIdentityError(
                        f"{self.label} runtime symbol {exact_name} exceeds section {section.name}"
                    )
                file_offset = section.offset + value - section.address
                symbol_payload = _slice(
                    self.payload,
                    file_offset,
                    size,
                    label=f"{self.label} runtime symbol {exact_name}",
                )
                matches.append(
                    RuntimeSymbol(
                        name,
                        value,
                        size,
                        info >> 4,
                        info & 0x0F,
                        section,
                        file_offset,
                        symbol_payload,
                    )
                )
        if len(matches) != 1:
            raise CompiledIdentityError(
                f"{self.label} must contain exactly one runtime symbol {exact_name}; "
                f"found {len(matches)}"
            )
        symbol = matches[0]
        if symbol.binding != STB_LOCAL or symbol.symbol_type != STT_OBJECT:
            raise CompiledIdentityError(
                f"{self.label} runtime symbol {exact_name} is not a local object"
            )
        if symbol.size != 32:
            raise CompiledIdentityError(
                f"{self.label} runtime symbol {exact_name} size is {symbol.size}, expected 32"
            )
        return symbol


def _fnv1a(payload: bytes) -> int:
    value = 0x811C9DC5
    for item in payload:
        value ^= item
        value = (value * 0x01000193) & 0xFFFFFFFF
    return value


def generated_identity(candidate: int) -> dict[str, object]:
    """Independently generate the fixed Stage-A frame and both DTM streams."""

    if candidate not in (4, 7):
        raise CompiledIdentityError("candidate must be exactly 4 or 7")
    frame = bytearray(b"\x11" * FRAME_BYTES)
    pair = bytes((((candidate << 4) | candidate),))
    for y in range(ROI_Y0, ROI_Y1):
        for x0, x1 in ROI_X_RANGES:
            start = y * ROW_BYTES + x0 // 2
            end = y * ROW_BYTES + x1 // 2
            frame[start:end] = pair * (end - start)
    frame_bytes = bytes(frame)
    cs1 = b"".join(
        frame_bytes[y * ROW_BYTES : y * ROW_BYTES + CONTROLLER_ROW_BYTES]
        for y in range(HEIGHT)
    )
    cs2 = b"".join(
        frame_bytes[
            y * ROW_BYTES + CONTROLLER_ROW_BYTES : (y + 1) * ROW_BYTES
        ]
        for y in range(HEIGHT)
    )
    if len(frame_bytes) != FRAME_BYTES or len(cs1) != 153_600 or cs1 != cs2:
        raise CompiledIdentityError("independent Stage-A generator invariant failed")
    return {
        "candidate": candidate,
        "frame_sha256": hashlib.sha256(frame_bytes).digest(),
        "dtm_sha256": hashlib.sha256(cs1).digest(),
        "frame_fnv1a": _fnv1a(frame_bytes),
        "dtm_fnv1a": _fnv1a(cs1),
        "frame_bytes": len(frame_bytes),
        "dtm_bytes": len(cs1),
    }


def _validate_payload(payload: bytes, *, label: str, candidate: int) -> dict[str, object]:
    image = Elf32Image(payload, label=label)
    expected = generated_identity(candidate)
    other = generated_identity(7 if candidate == 4 else 4)
    compiled: dict[str, RuntimeSymbol] = {
        key: image.runtime_symbol(symbol_name)
        for key, symbol_name in RUNTIME_SYMBOLS.items()
    }
    for key, symbol in compiled.items():
        wanted = expected[key]
        assert isinstance(wanted, bytes)
        if symbol.payload != wanted:
            raise CompiledIdentityError(
                f"{label} U{candidate:02d} {key} compiled bytes mismatch: "
                f"expected {wanted.hex()}, got {symbol.payload.hex()}"
            )
        other_value = other[key]
        assert isinstance(other_value, bytes)
        if symbol.payload == other_value:
            raise CompiledIdentityError(
                f"{label} U{candidate:02d} {key} is not candidate-isolated"
            )
    return {
        "candidate_id": f"U{candidate:02d}",
        "candidate_code": candidate,
        "elf_bytes": len(payload),
        "elf_sha256": hashlib.sha256(payload).hexdigest(),
        "frame_bytes": expected["frame_bytes"],
        "dtm_bytes": expected["dtm_bytes"],
        "frame_fnv1a": f"0x{expected['frame_fnv1a']:08X}",
        "dtm_fnv1a": f"0x{expected['dtm_fnv1a']:08X}",
        "symbols": {
            key: {
                "name": symbol.name,
                "size": symbol.size,
                "vma": f"0x{symbol.value:08X}",
                "section": symbol.section.name,
                "file_offset": symbol.file_offset,
                "sha256_bytes": symbol.payload.hex(),
            }
            for key, symbol in compiled.items()
        },
    }


def validate_pair(u04_elf: Path, u07_elf: Path) -> dict[str, object]:
    u04_path, u04_payload = _read_regular(Path(u04_elf), label="U04 ELF")
    u07_path, u07_payload = _read_regular(Path(u07_elf), label="U07 ELF")
    try:
        same_file = os.path.samefile(u04_path, u07_path)
    except OSError as error:
        raise CompiledIdentityError(f"could not compare ELF paths: {error}") from error
    if same_file:
        raise CompiledIdentityError("U04 and U07 must be different ELF files")
    variants = {
        "U04": _validate_payload(u04_payload, label=str(u04_path), candidate=4),
        "U07": _validate_payload(u07_payload, label=str(u07_path), candidate=7),
    }
    if (
        variants["U04"]["symbols"]["frame_sha256"]["sha256_bytes"]
        == variants["U07"]["symbols"]["frame_sha256"]["sha256_bytes"]
        or variants["U04"]["symbols"]["dtm_sha256"]["sha256_bytes"]
        == variants["U07"]["symbols"]["dtm_sha256"]["sha256_bytes"]
    ):
        raise CompiledIdentityError("U04 and U07 compiled identities are not isolated")
    return {
        "schema_version": 1,
        "kind": "mf1750-ec5-stage-a-compiled-identity-validation",
        "valid": True,
        "offline": True,
        "device_io_performed": False,
        "variants": variants,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser(
        "validate", help="validate U04/U07 compiled runtime identity symbols"
    )
    validate.add_argument("--u04-elf", type=Path, required=True)
    validate.add_argument("--u07-elf", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = validate_pair(args.u04_elf, args.u07_elf)
    except CompiledIdentityError as error:
        print(f"EC5 compiled-identity error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

