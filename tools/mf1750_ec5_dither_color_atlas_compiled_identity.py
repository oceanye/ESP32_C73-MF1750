#!/usr/bin/env python3
"""Fail-closed offline identity gate for the dither-atlas firmware pair.

The gate resolves the exact linked ``kActions`` and ``DCA_IDENTITIES``
objects, follows their runtime pointers, verifies the sole compiled display
call and boot fixture validator, and binds the selected ESP application BIN
to the selected ELF through the ESP-IDF app descriptor. It never performs
device, serial, network, upload, or visible-refresh I/O.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_compiled_identity as elf_reader  # noqa: E402
from tools import mf1750_ec5_dither_color_atlas_contract as contract  # noqa: E402


MAX_BINARY_BYTES = 4 * 1024 * 1024
MAX_ELF_BYTES = 32 * 1024 * 1024

SHF_ALLOC = 0x2
SHF_EXECINSTR = 0x4
STB_LOCAL = 0
STB_GLOBAL = 1
STT_OBJECT = 1
STT_FUNC = 2
STT_FILE = 4
SHN_ABS = 0xFFF1

APP_DESCRIPTOR_OFFSET = 32
APP_DESCRIPTOR_MAGIC = bytes.fromhex("3254cdab")
EMBEDDED_ELF_SHA256_OFFSET = 176

# ESP32-S3 uses 32-bit pointers. These layouts intentionally include the C++
# ABI padding and therefore bind the exact runtime objects, not source text.
ACTION_RECORD = struct.Struct("<BB2xIB3x" + "I" * 18)
DRIVER_IDENTITY_RECORD = struct.Struct("<" + "I" * 14)


def _local_object_symbol(name: str) -> str:
    return f"_ZN12_GLOBAL__N_1L{len(name)}{name}E"


ACTION_SYMBOL = _local_object_symbol("kActions")
DRIVER_IDENTITIES_SYMBOL = _local_object_symbol("DCA_IDENTITIES")
DISPLAY_SYMBOL = "_Z34epdDisplayCompiledDitherColorAtlas23EpdDitherColorAtlasRole"
FIXTURE_VALIDATOR_SYMBOL = "_Z43epdValidateCompiledDitherColorAtlasFixturesv"
LOOP_SYMBOL = "_Z4loopv"
SETUP_SYMBOL = "_Z5setupv"
EXPECTED_MAIN_FILE = "ec5_dither_color_atlas_main.cpp"

DRIVER_SHA_SYMBOLS = {
    "atlas_frame": _local_object_symbol("DCA_ATLAS_FRAME_SHA256"),
    "atlas_cs1": _local_object_symbol("DCA_ATLAS_CS1_DTM_SHA256"),
    "atlas_cs2": _local_object_symbol("DCA_ATLAS_CS2_DTM_SHA256"),
    "white_frame": _local_object_symbol("DCA_WHITE_FRAME_SHA256"),
    "white_dtm": _local_object_symbol("DCA_WHITE_DTM_SHA256"),
}

ROLE_SHA_KEYS = {
    contract.ROLE_ATLAS: ("atlas_frame", "atlas_cs1", "atlas_cs2"),
    contract.ROLE_WHITE: ("white_frame", "white_dtm", "white_dtm"),
}

DRIVER_ROLE_BY_ROLE = {
    contract.ROLE_ATLAS: 0,
    contract.ROLE_WHITE: 1,
}

EXPECTED_ENDPOINTS = (
    "/api/ec5/dither-color-atlas/version",
    "/api/ec5/dither-color-atlas/manifest",
    "/api/ec5/dither-color-atlas/status",
    "/api/ec5/dither-color-atlas/report",
    "/api/ec5/dither-color-atlas/arm",
    "/api/ec5/dither-color-atlas/execute",
)

# Search both selected artifacts. This also catches linked-but-dead fixture
# code left in debug/string sections, while exact endpoint validation below
# is restricted to allocated runtime sections.
FORBIDDEN_MARKERS = (
    b"MF1750_EC5_OTP_TRANSITION_MATRIX_DEVICE",
    b"EC5_COLOR_LAB_CAMPAIGN",
    b"EC5_COLOR_LAB_RECOVERY_CAMPAIGN",
    b"MF1750_EC5_COLOR_LAB_DEVICE",
    b"MF1750_EC5_COLOR_LAB_RECOVERY_DEVICE",
    b"MF1750_EC5_U07T_DEVICE",
    b"MF1750_EC5_U04_U05_COMPARE_DEVICE",
    b"MF1750_EC5_DEVICE_V3",
    b"ec5_otp_transition_matrix_main.cpp",
    b"ec5_color_lab_main.cpp",
    b"ec5_color_lab_recovery_main.cpp",
    b"ec5_sixstate_main.cpp",
    b"ec5_u04_u05_compare_main.cpp",
    b"ec5_u07t_main.cpp",
    b"ec5_unknown_probe_main.cpp",
    b"/api/ec5/otp-transition-matrix/",
    b"/api/ec5/color-lab/",
    b"/api/ec5/sixstate/",
    b"/api/ec5/version\0",
    b"/api/ec5/manifest\0",
    b"/api/ec5/status\0",
    b"/api/ec5/report\0",
    b"/api/ec5/arm\0",
    b"/api/ec5/execute\0",
    b"/api/frame\0",
    b"/api/diagnostic/frame-ingress\0",
    b"/api/lut",
    b"/api/waveform",
    b"/api/runtime-lut",
    b"/api/runtime-waveform",
    b"/api/ec5/retry",
    b"/api/ec5/recovery",
)


class DitherColorAtlasCompiledIdentityError(ValueError):
    """The selected firmware pair failed the exact compiled identity gate."""


@dataclass(frozen=True)
class LinkedSymbol:
    name: str
    value: int
    size: int
    binding: int
    symbol_type: int
    section: elf_reader.Section | None
    file_offset: int | None
    payload: bytes


def _slice(payload: bytes, offset: int, size: int, *, label: str) -> bytes:
    if offset < 0 or size < 0 or offset > len(payload) or size > len(payload) - offset:
        raise DitherColorAtlasCompiledIdentityError(
            f"{label} exceeds its containing file"
        )
    return payload[offset : offset + size]


def _cstring(payload: bytes, offset: int, *, label: str) -> str:
    if offset < 0 or offset >= len(payload):
        raise DitherColorAtlasCompiledIdentityError(
            f"{label} is outside its string table"
        )
    end = payload.find(b"\0", offset)
    if end < 0:
        raise DitherColorAtlasCompiledIdentityError(f"{label} is not NUL terminated")
    try:
        return payload[offset:end].decode("ascii")
    except UnicodeDecodeError as error:
        raise DitherColorAtlasCompiledIdentityError(f"{label} is not ASCII") from error


def _read_regular(path: Path, *, label: str, maximum: int) -> tuple[Path, bytes]:
    candidate = Path(path)
    try:
        before = candidate.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise DitherColorAtlasCompiledIdentityError(
                f"{label} must be a non-symlink regular file"
            )
        if before.st_size <= 0 or before.st_size > maximum:
            raise DitherColorAtlasCompiledIdentityError(f"{label} has an invalid size")
        payload = candidate.read_bytes()
        after = candidate.lstat()
    except OSError as error:
        raise DitherColorAtlasCompiledIdentityError(
            f"could not read {label}: {error}"
        ) from error
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
        raise DitherColorAtlasCompiledIdentityError(
            f"{label} changed while it was read"
        )
    return candidate.resolve(strict=True), payload


def _symbols(image: elf_reader.Elf32Image) -> tuple[LinkedSymbol, ...]:
    result: list[LinkedSymbol] = []
    for symtab in image.sections:
        if symtab.section_type != elf_reader.SHT_SYMTAB:
            continue
        if (
            symtab.entry_size != elf_reader.SYMBOL_ENTRY.size
            or symtab.size % symtab.entry_size
        ):
            raise DitherColorAtlasCompiledIdentityError(
                f"ELF symbol table {symtab.name} has an invalid entry size"
            )
        if symtab.link <= 0 or symtab.link >= len(image.sections):
            raise DitherColorAtlasCompiledIdentityError(
                f"ELF symbol table {symtab.name} has an invalid string-table link"
            )
        string_section = image.sections[symtab.link]
        if string_section.section_type != elf_reader.SHT_STRTAB:
            raise DitherColorAtlasCompiledIdentityError(
                f"ELF symbol table {symtab.name} does not link to STRTAB"
            )
        strings = _slice(
            image.payload,
            string_section.offset,
            string_section.size,
            label="ELF symbol strings",
        )
        for relative in range(0, symtab.size, symtab.entry_size):
            raw = _slice(
                image.payload,
                symtab.offset + relative,
                elf_reader.SYMBOL_ENTRY.size,
                label="ELF symbol entry",
            )
            name_offset, value, size, info, _other, section_index = (
                elf_reader.SYMBOL_ENTRY.unpack(raw)
            )
            name = _cstring(strings, name_offset, label="ELF symbol name")
            section: elf_reader.Section | None = None
            file_offset: int | None = None
            symbol_payload = b""
            if 0 < section_index < len(image.sections):
                section = image.sections[section_index]
                if section.section_type != elf_reader.SHT_NOBITS:
                    if value < section.address:
                        raise DitherColorAtlasCompiledIdentityError(
                            f"ELF symbol {name!r} starts before section {section.name}"
                        )
                    relative_value = value - section.address
                    if (
                        relative_value > section.size
                        or size > section.size - relative_value
                    ):
                        raise DitherColorAtlasCompiledIdentityError(
                            f"ELF symbol {name!r} exceeds section {section.name}"
                        )
                    file_offset = section.offset + relative_value
                    symbol_payload = _slice(
                        image.payload,
                        file_offset,
                        size,
                        label=f"ELF symbol {name!r}",
                    )
            elif section_index not in (0, SHN_ABS, 0xFFF2):
                raise DitherColorAtlasCompiledIdentityError(
                    f"ELF symbol {name!r} has unsupported section index "
                    f"0x{section_index:04x}"
                )
            result.append(
                LinkedSymbol(
                    name=name,
                    value=value,
                    size=size,
                    binding=info >> 4,
                    symbol_type=info & 0x0F,
                    section=section,
                    file_offset=file_offset,
                    payload=symbol_payload,
                )
            )
    if not result:
        raise DitherColorAtlasCompiledIdentityError(
            "ELF does not contain a static symbol table"
        )
    return tuple(result)


def _exact_symbol(
    symbols: Sequence[LinkedSymbol],
    name: str,
    *,
    label: str,
    binding: int,
    symbol_type: int,
    size: int | None = None,
) -> LinkedSymbol:
    matches = [symbol for symbol in symbols if symbol.name == name]
    if len(matches) != 1:
        raise DitherColorAtlasCompiledIdentityError(
            f"ELF must contain exactly one {label} symbol {name}; found {len(matches)}"
        )
    symbol = matches[0]
    if symbol.binding != binding or symbol.symbol_type != symbol_type:
        raise DitherColorAtlasCompiledIdentityError(
            f"ELF {label} symbol has the wrong binding or type"
        )
    if size is not None and symbol.size != size:
        raise DitherColorAtlasCompiledIdentityError(
            f"ELF {label} symbol size is {symbol.size}, expected {size}"
        )
    if (
        symbol.section is None
        or symbol.file_offset is None
        or not symbol.section.flags & SHF_ALLOC
    ):
        raise DitherColorAtlasCompiledIdentityError(
            f"ELF {label} symbol is not in an allocated file-backed section"
        )
    return symbol


def _runtime_cstring(image: elf_reader.Elf32Image, address: int, *, label: str) -> str:
    matches = [
        section
        for section in image.sections
        if section.flags & SHF_ALLOC
        and section.section_type != elf_reader.SHT_NOBITS
        and section.address <= address < section.address + section.size
    ]
    if len(matches) != 1:
        raise DitherColorAtlasCompiledIdentityError(
            f"{label} pointer 0x{address:08x} is not in exactly one runtime section"
        )
    section = matches[0]
    file_offset = section.offset + address - section.address
    section_end = section.offset + section.size
    end = image.payload.find(b"\0", file_offset, section_end)
    if end < 0:
        raise DitherColorAtlasCompiledIdentityError(
            f"{label} runtime string is not NUL terminated"
        )
    try:
        return image.payload[file_offset:end].decode("ascii")
    except UnicodeDecodeError as error:
        raise DitherColorAtlasCompiledIdentityError(
            f"{label} runtime string is not ASCII"
        ) from error


@lru_cache(maxsize=len(contract.ROLES))
def _histogram(role: str) -> tuple[int, ...]:
    values = [0] * 8
    for byte in contract.role_frame(role):
        high = byte >> 4
        low = byte & 0x0F
        if high >= len(values) or low >= len(values):
            raise DitherColorAtlasCompiledIdentityError(
                f"host role {role} contains a non-transport code"
            )
        values[high] += 1
        values[low] += 1
    return tuple(values)


def required_identity_strings() -> tuple[str, ...]:
    """Return the complete deduplicated runtime/BIN identity string set."""

    values: list[str] = [
        contract.CLASSIFICATION,
        contract.BUILD_TAG,
        contract.TEST_ID,
        contract.CAMPAIGN_ID,
        contract.DEVICE_API_VERSION,
        contract.IDENTITY_REVISION,
        contract.LAYOUT_ID,
        contract.NVS_NAMESPACE,
        contract.NVS_KEY,
        contract.campaign_manifest()["contract_id"],
        *EXPECTED_ENDPOINTS,
    ]
    for descriptor in contract.DESCRIPTORS:
        values.extend(
            (
                str(descriptor["role"]),
                str(descriptor["branch"]),
                str(descriptor["descriptor_id"]),
                str(descriptor["hardware_action_id"]),
                str(descriptor["frame_sha256"]),
                str(descriptor["cs1_dtm_sha256"]),
                str(descriptor["cs2_dtm_sha256"]),
            )
        )
        prior = descriptor["action_identity_preimage"]["prior_static_action_id"]
        if prior is not None:
            values.append(str(prior))
    return tuple(dict.fromkeys(values))


def _validate_required_strings(elf: bytes, binary: bytes) -> None:
    for value in required_identity_strings():
        needle = value.encode("ascii") + b"\0"
        if needle not in elf:
            raise DitherColorAtlasCompiledIdentityError(
                f"ELF lacks frozen runtime identity string {value!r}"
            )
        if needle not in binary:
            raise DitherColorAtlasCompiledIdentityError(
                f"firmware BIN lacks frozen runtime identity string {value!r}"
            )
    for label, payload in (("ELF", elf), ("firmware BIN", binary)):
        for marker in FORBIDDEN_MARKERS:
            if marker in payload:
                display = marker.rstrip(b"\0").decode("ascii", errors="replace")
                raise DitherColorAtlasCompiledIdentityError(
                    f"{label} contains forbidden fixture identity or mutation "
                    f"endpoint {display!r}"
                )


def _validate_main_actions(
    image: elf_reader.Elf32Image, symbols: Sequence[LinkedSymbol]
) -> tuple[list[dict[str, Any]], LinkedSymbol]:
    wanted_size = len(contract.DESCRIPTORS) * ACTION_RECORD.size
    action_symbol = _exact_symbol(
        symbols,
        ACTION_SYMBOL,
        label="main ActionDescriptor array",
        binding=STB_LOCAL,
        symbol_type=STT_OBJECT,
        size=wanted_size,
    )
    compiled: list[dict[str, Any]] = []
    for index, descriptor in enumerate(contract.DESCRIPTORS):
        start = index * ACTION_RECORD.size
        raw = action_symbol.payload[start : start + ACTION_RECORD.size]
        if raw[2:4] != b"\0\0" or raw[9:12] != b"\0\0\0":
            raise DitherColorAtlasCompiledIdentityError(
                f"main ActionDescriptor ordinal {index + 1} padding differs"
            )
        fields = ACTION_RECORD.unpack(raw)
        ordinal, driver_role, role_ptr, round_number = fields[:4]
        (
            branch_ptr,
            descriptor_ptr,
            action_ptr,
            prior_ptr,
            frame_ptr,
            cs1_ptr,
            cs2_ptr,
            frame_fnv,
            cs1_fnv,
            cs2_fnv,
            *histogram,
        ) = fields[4:]
        role = str(descriptor["role"])
        identity = contract.ROLE_IDENTITIES[role]
        expected_prior = descriptor["action_identity_preimage"][
            "prior_static_action_id"
        ]
        expected_scalars = (
            int(descriptor["ordinal"]),
            DRIVER_ROLE_BY_ROLE[role],
            int(descriptor["round"]),
            int(identity["frame"]["fnv1a_u32"]),
            int(identity["cs1_dtm"]["fnv1a_u32"]),
            int(identity["cs2_dtm"]["fnv1a_u32"]),
            _histogram(role),
        )
        actual_scalars = (
            ordinal,
            driver_role,
            round_number,
            frame_fnv,
            cs1_fnv,
            cs2_fnv,
            tuple(histogram),
        )
        if actual_scalars != expected_scalars:
            raise DitherColorAtlasCompiledIdentityError(
                f"main ActionDescriptor ordinal {index + 1} scalar identity differs"
            )
        expected_strings = {
            "role": (role_ptr, role),
            "branch": (branch_ptr, str(descriptor["branch"])),
            "descriptor_id": (descriptor_ptr, str(descriptor["descriptor_id"])),
            "action_id": (action_ptr, str(descriptor["hardware_action_id"])),
            "frame_sha256": (frame_ptr, str(descriptor["frame_sha256"])),
            "cs1_dtm_sha256": (cs1_ptr, str(descriptor["cs1_dtm_sha256"])),
            "cs2_dtm_sha256": (cs2_ptr, str(descriptor["cs2_dtm_sha256"])),
        }
        if expected_prior is None:
            if prior_ptr != 0:
                raise DitherColorAtlasCompiledIdentityError(
                    "main ActionDescriptor ordinal 1 prior action is not null"
                )
        elif _runtime_cstring(
            image, prior_ptr, label=f"action {index + 1} prior_action_id"
        ) != str(expected_prior):
            raise DitherColorAtlasCompiledIdentityError(
                f"main ActionDescriptor ordinal {index + 1} prior action differs"
            )
        resolved_strings: dict[str, str] = {}
        for field, (pointer, expected) in expected_strings.items():
            actual = _runtime_cstring(
                image, pointer, label=f"action {index + 1} {field}"
            )
            if actual != expected:
                raise DitherColorAtlasCompiledIdentityError(
                    f"main ActionDescriptor ordinal {index + 1} {field} differs"
                )
            resolved_strings[field] = actual
        compiled.append(
            {
                "ordinal": ordinal,
                "driver_role": driver_role,
                **resolved_strings,
                "prior_action_id": expected_prior,
                "frame_fnv1a": f"0x{frame_fnv:08x}",
                "cs1_dtm_fnv1a": f"0x{cs1_fnv:08x}",
                "cs2_dtm_fnv1a": f"0x{cs2_fnv:08x}",
                "histogram": list(histogram),
            }
        )
    return compiled, action_symbol


def _validate_driver_identities(
    image: elf_reader.Elf32Image, symbols: Sequence[LinkedSymbol]
) -> tuple[dict[str, Any], LinkedSymbol]:
    sha_symbols = {
        key: _exact_symbol(
            symbols,
            name,
            label=f"driver {key} SHA-256",
            binding=STB_LOCAL,
            symbol_type=STT_OBJECT,
            size=65,
        )
        for key, name in DRIVER_SHA_SYMBOLS.items()
    }
    for role, keys in ROLE_SHA_KEYS.items():
        identity = contract.ROLE_IDENTITIES[role]
        expected = (
            str(identity["frame"]["sha256"]),
            str(identity["cs1_dtm"]["sha256"]),
            str(identity["cs2_dtm"]["sha256"]),
        )
        for key, value in zip(keys, expected, strict=True):
            if sha_symbols[key].payload != value.encode("ascii") + b"\0":
                raise DitherColorAtlasCompiledIdentityError(
                    f"driver {role} {key} exact SHA-256 object differs"
                )

    identities_symbol = _exact_symbol(
        symbols,
        DRIVER_IDENTITIES_SYMBOL,
        label="driver DCA_IDENTITIES array",
        binding=STB_LOCAL,
        symbol_type=STT_OBJECT,
        size=len(contract.ROLES) * DRIVER_IDENTITY_RECORD.size,
    )
    roles: dict[str, Any] = {}
    for index, role in enumerate(contract.ROLES):
        start = index * DRIVER_IDENTITY_RECORD.size
        values = DRIVER_IDENTITY_RECORD.unpack(
            identities_symbol.payload[start : start + DRIVER_IDENTITY_RECORD.size]
        )
        frame_fnv, cs1_fnv, cs2_fnv, frame_ptr, cs1_ptr, cs2_ptr, *histogram = values
        identity = contract.ROLE_IDENTITIES[role]
        keys = ROLE_SHA_KEYS[role]
        expected_values = (
            int(identity["frame"]["fnv1a_u32"]),
            int(identity["cs1_dtm"]["fnv1a_u32"]),
            int(identity["cs2_dtm"]["fnv1a_u32"]),
            sha_symbols[keys[0]].value,
            sha_symbols[keys[1]].value,
            sha_symbols[keys[2]].value,
            _histogram(role),
        )
        actual_values = (
            frame_fnv,
            cs1_fnv,
            cs2_fnv,
            frame_ptr,
            cs1_ptr,
            cs2_ptr,
            tuple(histogram),
        )
        if actual_values != expected_values:
            raise DitherColorAtlasCompiledIdentityError(
                f"driver DCA_IDENTITIES role {role} differs"
            )
        for field, pointer, key in (
            ("frame", frame_ptr, keys[0]),
            ("cs1_dtm", cs1_ptr, keys[1]),
            ("cs2_dtm", cs2_ptr, keys[2]),
        ):
            if _runtime_cstring(
                image, pointer, label=f"driver {role} {field} SHA-256"
            ) != str(identity[field]["sha256"]):
                raise DitherColorAtlasCompiledIdentityError(
                    f"driver {role} {field} SHA-256 pointer differs"
                )
        roles[role] = {
            "index": index,
            "frame_fnv1a": f"0x{frame_fnv:08x}",
            "cs1_dtm_fnv1a": f"0x{cs1_fnv:08x}",
            "cs2_dtm_fnv1a": f"0x{cs2_fnv:08x}",
            "frame_sha256": str(identity["frame"]["sha256"]),
            "cs1_dtm_sha256": str(identity["cs1_dtm"]["sha256"]),
            "cs2_dtm_sha256": str(identity["cs2_dtm"]["sha256"]),
            "histogram": list(histogram),
        }
    return roles, identities_symbol


def _direct_calls_to(
    image: elf_reader.Elf32Image, target: int
) -> tuple[dict[str, Any], ...]:
    calls: list[dict[str, Any]] = []
    for section in image.sections:
        if (
            not section.flags & SHF_EXECINSTR
            or section.section_type == elf_reader.SHT_NOBITS
            or section.size < 3
        ):
            continue
        payload = _slice(
            image.payload,
            section.offset,
            section.size,
            label=f"executable section {section.name}",
        )
        # Xtensa direct CALL0/4/8/12: signed 18-bit word displacement from
        # (PC + 4) rounded down to four-byte alignment. Every byte may be an
        # instruction boundary, so scan all offsets and then bind the caller.
        for offset in range(len(payload) - 2):
            instruction = int.from_bytes(payload[offset : offset + 3], "little")
            if instruction & 0x0F != 0x05:
                continue
            displacement = instruction >> 6
            if displacement & (1 << 17):
                displacement -= 1 << 18
            address = section.address + offset
            destination = (((address + 4) & ~3) + (displacement << 2)) & 0xFFFFFFFF
            if destination == target:
                calls.append(
                    {
                        "section": section.name,
                        "vma": address,
                        "vma_hex": f"0x{address:08x}",
                        "call_window": (instruction >> 4) & 0x03,
                    }
                )
    return tuple(calls)


def _calls_inside(
    calls: Sequence[dict[str, Any]], caller: LinkedSymbol
) -> tuple[dict[str, Any], ...]:
    """Restrict byte-scan candidates to the contractually allowed caller.

    Xtensa instructions are variable length.  The conservative all-offset scan
    above can therefore see a CALL-shaped three-byte window inside an unrelated
    instruction.  Binding the candidate to the exact linked caller function
    removes that false positive while retaining the required call-site proof.
    """

    return tuple(
        call
        for call in calls
        if caller.value <= int(call["vma"]) < caller.value + caller.size
    )


def _runtime_api_endpoints(image: elf_reader.Elf32Image) -> Counter[str]:
    pattern = re.compile(rb"/api/[A-Za-z0-9._/-]+\x00")
    endpoints: Counter[str] = Counter()
    for section in image.sections:
        if (
            not section.flags & SHF_ALLOC
            or section.section_type == elf_reader.SHT_NOBITS
        ):
            continue
        payload = _slice(
            image.payload,
            section.offset,
            section.size,
            label=f"runtime section {section.name}",
        )
        for match in pattern.finditer(payload):
            endpoint = match.group()[:-1].decode("ascii")
            if endpoint.endswith((".c", ".cc", ".cpp", ".h", ".hpp")):
                continue
            endpoints[endpoint] += 1
    return endpoints


def _executable_function(
    symbols: Sequence[LinkedSymbol], name: str, *, label: str
) -> LinkedSymbol:
    symbol = _exact_symbol(
        symbols,
        name,
        label=label,
        binding=STB_GLOBAL,
        symbol_type=STT_FUNC,
    )
    if (
        symbol.size <= 0
        or symbol.section is None
        or not symbol.section.flags & SHF_EXECINSTR
    ):
        raise DitherColorAtlasCompiledIdentityError(
            f"compiled {label} is not a non-empty executable function"
        )
    return symbol


def _validate_executable_identity(
    image: elf_reader.Elf32Image, symbols: Sequence[LinkedSymbol]
) -> dict[str, Any]:
    display = _executable_function(
        symbols,
        DISPLAY_SYMBOL,
        label="epdDisplayCompiledDitherColorAtlas",
    )
    fixture_validator = _executable_function(
        symbols,
        FIXTURE_VALIDATOR_SYMBOL,
        label="dither-atlas fixture validator",
    )
    loop = _executable_function(symbols, LOOP_SYMBOL, label="Arduino loop")
    setup = _executable_function(symbols, SETUP_SYMBOL, label="Arduino setup")

    display_calls = _calls_inside(_direct_calls_to(image, display.value), loop)
    if len(display_calls) != 1:
        raise DitherColorAtlasCompiledIdentityError(
            "ELF must contain exactly one direct call to "
            f"epdDisplayCompiledDitherColorAtlas; found {len(display_calls)}"
        )
    display_call_vma = int(display_calls[0]["vma"])
    if not loop.value <= display_call_vma < loop.value + loop.size:
        raise DitherColorAtlasCompiledIdentityError(
            "the sole compiled dither-atlas display call is not inside loop()"
        )

    validator_calls = _calls_inside(
        _direct_calls_to(image, fixture_validator.value), setup
    )
    if len(validator_calls) != 1:
        raise DitherColorAtlasCompiledIdentityError(
            "ELF must contain exactly one direct call to the dither-atlas "
            f"fixture validator; found {len(validator_calls)}"
        )
    validator_call_vma = int(validator_calls[0]["vma"])
    if not setup.value <= validator_call_vma < setup.value + setup.size:
        raise DitherColorAtlasCompiledIdentityError(
            "the sole compiled dither-atlas fixture-validator call is not "
            "inside setup()"
        )

    compiled_display_symbols = sorted(
        {symbol.name for symbol in symbols if "epdDisplayCompiled" in symbol.name}
    )
    if compiled_display_symbols != [DISPLAY_SYMBOL]:
        raise DitherColorAtlasCompiledIdentityError(
            "ELF contains another compiled fixture display symbol"
        )
    main_files = sorted(
        symbol.name
        for symbol in symbols
        if symbol.symbol_type == STT_FILE and symbol.name.endswith("_main.cpp")
    )
    if main_files != [EXPECTED_MAIN_FILE]:
        raise DitherColorAtlasCompiledIdentityError(
            f"ELF fixture-main source identity differs: {main_files!r}"
        )
    endpoints = _runtime_api_endpoints(image)
    expected_endpoints = Counter({endpoint: 1 for endpoint in EXPECTED_ENDPOINTS})
    if endpoints != expected_endpoints:
        raise DitherColorAtlasCompiledIdentityError(
            f"ELF runtime API endpoint set differs: {dict(endpoints)!r}"
        )
    return {
        "display_symbol": {
            "name": display.name,
            "vma": f"0x{display.value:08x}",
            "size": display.size,
            "section": display.section.name,
        },
        "fixture_validator_symbol": {
            "name": fixture_validator.name,
            "vma": f"0x{fixture_validator.value:08x}",
            "size": fixture_validator.size,
            "section": fixture_validator.section.name,
        },
        "display_direct_call_count": len(display_calls),
        "display_direct_call": dict(display_calls[0]),
        "display_caller": {
            "name": loop.name,
            "vma": f"0x{loop.value:08x}",
            "size": loop.size,
        },
        "fixture_validator_direct_call_count": len(validator_calls),
        "fixture_validator_direct_call": dict(validator_calls[0]),
        "fixture_validator_caller": {
            "name": setup.name,
            "vma": f"0x{setup.value:08x}",
            "size": setup.size,
        },
        "fixture_main_files": main_files,
        "api_endpoints": sorted(endpoints),
        "other_compiled_fixture_display_symbols": [],
    }


def _binary_elf_link(binary: bytes, elf: bytes) -> dict[str, Any]:
    selected = hashlib.sha256(elf).digest()
    if (
        len(binary) < EMBEDDED_ELF_SHA256_OFFSET + len(selected)
        or binary[0] != 0xE9
        or not elf.startswith(elf_reader.ELF_MAGIC)
        or binary[
            APP_DESCRIPTOR_OFFSET : APP_DESCRIPTOR_OFFSET + len(APP_DESCRIPTOR_MAGIC)
        ]
        != APP_DESCRIPTOR_MAGIC
        or binary[
            EMBEDDED_ELF_SHA256_OFFSET : EMBEDDED_ELF_SHA256_OFFSET + len(selected)
        ]
        != selected
    ):
        raise DitherColorAtlasCompiledIdentityError(
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


def validate_artifacts(elf_file: Path, binary_file: Path) -> dict[str, Any]:
    """Validate one exact ELF/BIN pair without consulting hardware."""

    elf_path, elf = _read_regular(
        Path(elf_file), label="dither color-atlas ELF", maximum=MAX_ELF_BYTES
    )
    binary_path, binary = _read_regular(
        Path(binary_file),
        label="dither color-atlas firmware BIN",
        maximum=MAX_BINARY_BYTES,
    )
    try:
        if os.path.samefile(elf_path, binary_path):
            raise DitherColorAtlasCompiledIdentityError(
                "firmware ELF and BIN must be different regular files"
            )
    except OSError as error:
        raise DitherColorAtlasCompiledIdentityError(
            f"could not compare firmware artifact paths: {error}"
        ) from error

    _validate_required_strings(elf, binary)
    binary_elf_link = _binary_elf_link(binary, elf)
    try:
        image = elf_reader.Elf32Image(elf, label=str(elf_path))
    except elf_reader.CompiledIdentityError as error:
        raise DitherColorAtlasCompiledIdentityError(
            f"compiled dither-atlas ELF identity gate failed: {error}"
        ) from error
    symbols = _symbols(image)
    actions, action_symbol = _validate_main_actions(image, symbols)
    roles, identities_symbol = _validate_driver_identities(image, symbols)
    executable = _validate_executable_identity(image, symbols)
    return {
        "schema_version": 1,
        "kind": "mf1750-ec5-dither-color-atlas-compiled-identity-validation",
        "valid": True,
        "offline": True,
        "device_io_performed": False,
        "serial_io_performed": False,
        "network_io_performed": False,
        "upload_performed": False,
        "visible_refreshes": 0,
        "execution_eligible": False,
        "classification": contract.CLASSIFICATION,
        "spatial_mixing_only": True,
        "runtime_lut_or_waveform_changed": False,
        "campaign_id": contract.CAMPAIGN_ID,
        "build_tag": contract.BUILD_TAG,
        "test_id": contract.TEST_ID,
        "contract_id": contract.campaign_manifest()["contract_id"],
        "firmware": {
            "elf": {
                "file": str(elf_path),
                "bytes": len(elf),
                "sha256": hashlib.sha256(elf).hexdigest(),
            },
            "binary": {
                "file": str(binary_path),
                "bytes": len(binary),
                "sha256": hashlib.sha256(binary).hexdigest(),
            },
            "binary_elf_link": binary_elf_link,
        },
        "main": {
            "action_count": len(actions),
            "action_descriptor_symbol": {
                "name": action_symbol.name,
                "size": action_symbol.size,
                "vma": f"0x{action_symbol.value:08x}",
                "section": action_symbol.section.name,
            },
            "actions": actions,
        },
        "driver": {
            "role_count": len(roles),
            "identity_symbol": {
                "name": identities_symbol.name,
                "size": identities_symbol.size,
                "vma": f"0x{identities_symbol.value:08x}",
                "section": identities_symbol.section.name,
            },
            "roles": roles,
        },
        "executable": executable,
        "negative_identity_scan": {
            "forbidden_marker_count": len(FORBIDDEN_MARKERS),
            "other_fixture_main_identity_absent": True,
            "other_compiled_fixture_display_absent": True,
            "raw_frame_endpoint_absent": True,
            "lut_or_waveform_endpoint_absent": True,
            "retry_or_recovery_endpoint_absent": True,
        },
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-artifacts", allow_abbrev=False)
    validate.add_argument("--elf", type=Path, required=True)
    validate.add_argument("--binary", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = validate_artifacts(args.elf, args.binary)
    except DitherColorAtlasCompiledIdentityError as error:
        print(f"EC5 dither-atlas compiled-identity error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
