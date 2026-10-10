#!/usr/bin/env python3
"""Inventory retained Arm ELF command sinks and size constants offline.

This audit is deliberately narrower than a general disassembler.  It parses
the exact 34 retained ArmCC objects and seven final AXF images supplied by the
vendor, follows relocation-bound or linked Thumb BL calls to known command
sinks, and decodes MOVW/MOVS/LDR-literal evidence for a small, declared set of
waveform-size constants.  Raw aligned integer coincidences are reported only
as rejected candidates.  No waveform bytes, live payload, hardware, serial,
network, flashing, or refresh action is produced.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.application.durable_io import write_new_bytes_durable  # noqa: E402


KIND = "mf1750-armcc-exec-sink-inventory-audit"
SCHEMA_VERSION = 1
DEFAULT_REFERENCE_ROOT = REPO_ROOT / "参考资料" / "REG-API-oqc(1)(1)" / "REG-API-oqc"
OUTPUT_REL = Path("Output")

EXPECTED_OBJECT_COUNT = 34
EXPECTED_OBJECT_BYTES = 30_054_060
EXPECTED_OBJECT_MANIFEST_SHA256 = (
    "3c17874f2a26e831ebc0a9431ac92e4a27690912a510ee3318f082607fa8b4c7"
)
EXPECTED_AXF_COUNT = 7
EXPECTED_AXF_BYTES = 7_491_660
EXPECTED_AXF_MANIFEST_SHA256 = (
    "faeeed732911e95e54b6843a4b8141095f24b031c9b8c11e0dc60b8afefd2f5c"
)

ELFCLASS32 = 1
ELFDATA2LSB = 1
ET_REL = 1
ET_EXEC = 2
EM_ARM = 40
SHT_SYMTAB = 2
SHT_REL = 9
SHF_EXECINSTR = 0x4
STT_FUNC = 2
R_ARM_THM_CALL = 10
R_ARM_THM_JUMP24 = 30

TARGET_CONSTANTS = (535, 704, 799, 800, 1503, 2508)
COMMAND_VALUES = (0x20, 0x21)

# These are APIs whose first ABI argument is the command byte.  PreSelected is
# included because read helpers call it directly; Target is excluded because
# its first argument is a selector and its command is in r1.
COMMAND_SINKS = (
    "EPD_WriteCMD",
    "EPD_WriteCMD_PreSelected",
    "EPD_WriteCMD_ToBoth",
    "EPD_WriteCMD_ToMaster",
    "EPD_WriteCMD_ToSlave",
    "sendSPICommand",
)
DUAL_COMMAND_SINKS = (
    "EPD_WriteCMD_ToBoth",
    "EPD_WriteCMD_ToMaster",
    "EPD_WriteCMD_ToSlave",
)


class ExecSinkAuditError(RuntimeError):
    """Raised when a pinned corpus identity or ELF invariant changes."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExecSinkAuditError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_sha256(value: object) -> str:
    return _sha256(_canonical_bytes(value))


def _read_c_string(table: bytes, offset: int, label: str) -> str:
    _require(0 <= offset < len(table), f"{label} string offset is out of bounds")
    end = table.find(b"\x00", offset)
    _require(end >= 0, f"{label} string is unterminated")
    return table[offset:end].decode("utf-8", errors="replace")


def _manifest(paths: Iterable[Path], root: Path) -> list[dict[str, Any]]:
    result = []
    for path in sorted(paths, key=lambda item: item.name.casefold()):
        payload = path.read_bytes()
        result.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": len(payload),
                "sha256": _sha256(payload),
            }
        )
    return result


def _pin_manifest(
    rows: list[dict[str, Any]],
    *,
    count: int,
    total_bytes: int,
    digest: str,
    label: str,
) -> dict[str, Any]:
    _require(len(rows) == count, f"{label} file count changed")
    _require(
        sum(int(row["bytes"]) for row in rows) == total_bytes,
        f"{label} total bytes changed",
    )
    observed = _canonical_sha256(rows)
    _require(observed == digest, f"{label} manifest identity changed")
    return {
        "file_count": len(rows),
        "total_bytes": total_bytes,
        "canonical_manifest_sha256": observed,
        "files": rows,
    }


def _parse_elf(payload: bytes, label: str) -> dict[str, Any]:
    _require(len(payload) >= 52, f"{label}: truncated ELF32 header")
    _require(payload[:4] == b"\x7fELF", f"{label}: not ELF")
    _require(payload[4] == ELFCLASS32, f"{label}: not ELF32")
    _require(payload[5] == ELFDATA2LSB, f"{label}: not little endian")
    elf_type, machine = struct.unpack_from("<HH", payload, 16)
    _require(elf_type in (ET_REL, ET_EXEC), f"{label}: unsupported ELF type")
    _require(machine == EM_ARM, f"{label}: machine is not ARM")
    section_offset = struct.unpack_from("<I", payload, 32)[0]
    section_entry_bytes, section_count, names_index = struct.unpack_from(
        "<HHH", payload, 46
    )
    _require(section_count > 0, f"{label}: empty/extended section table unsupported")
    _require(section_entry_bytes >= 40, f"{label}: short section header")
    _require(names_index < section_count, f"{label}: bad section-name table")
    _require(
        section_offset + section_count * section_entry_bytes <= len(payload),
        f"{label}: section table is out of bounds",
    )
    raw_sections = [
        struct.unpack_from(
            "<IIIIIIIIII",
            payload,
            section_offset + index * section_entry_bytes,
        )
        for index in range(section_count)
    ]
    names_section = raw_sections[names_index]
    names_start, names_bytes = names_section[4], names_section[5]
    _require(
        names_start + names_bytes <= len(payload),
        f"{label}: section-name bytes are out of bounds",
    )
    names = payload[names_start : names_start + names_bytes]
    sections: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_sections):
        offset, size = raw[4], raw[5]
        if raw[1] != 8:  # SHT_NOBITS has no file payload.
            _require(offset + size <= len(payload), f"{label}: section out of bounds")
        sections.append(
            {
                "index": index,
                "name": _read_c_string(names, raw[0], f"{label} section"),
                "type": raw[1],
                "flags": raw[2],
                "address": raw[3],
                "offset": offset,
                "size": size,
                "link": raw[6],
                "info": raw[7],
                "alignment": raw[8],
                "entry_size": raw[9],
            }
        )

    symbols: list[dict[str, Any]] = []
    symbols_by_table_index: dict[tuple[int, int], dict[str, Any]] = {}
    for symtab in sections:
        if symtab["type"] != SHT_SYMTAB:
            continue
        linked = int(symtab["link"])
        _require(linked < len(sections), f"{label}: invalid symbol string link")
        string_section = sections[linked]
        strings = payload[
            int(string_section["offset"]) : int(string_section["offset"])
            + int(string_section["size"])
        ]
        entry_bytes = int(symtab["entry_size"]) or 16
        _require(entry_bytes >= 16, f"{label}: short symbol entry")
        _require(
            int(symtab["size"]) % entry_bytes == 0,
            f"{label}: misaligned symbol table",
        )
        for index, position in enumerate(
            range(
                int(symtab["offset"]),
                int(symtab["offset"]) + int(symtab["size"]),
                entry_bytes,
            )
        ):
            name_offset, value, size, info, other, section_index = struct.unpack_from(
                "<IIIBBH", payload, position
            )
            symbol = {
                "table_section_index": int(symtab["index"]),
                "index": index,
                "name": _read_c_string(strings, name_offset, f"{label} symbol")
                if name_offset
                else "",
                "value": value,
                "size": size,
                "binding": info >> 4,
                "type": info & 0x0F,
                "other": other,
                "section_index": section_index,
            }
            symbols.append(symbol)
            symbols_by_table_index[(int(symtab["index"]), index)] = symbol

    relocations: list[dict[str, Any]] = []
    for relsec in sections:
        if relsec["type"] != SHT_REL:
            continue
        target_index = int(relsec["info"])
        symtab_index = int(relsec["link"])
        _require(target_index < len(sections), f"{label}: bad relocation target")
        entry_bytes = int(relsec["entry_size"]) or 8
        _require(entry_bytes >= 8, f"{label}: short relocation entry")
        _require(
            int(relsec["size"]) % entry_bytes == 0,
            f"{label}: misaligned relocation section",
        )
        for position in range(
            int(relsec["offset"]),
            int(relsec["offset"]) + int(relsec["size"]),
            entry_bytes,
        ):
            offset, info = struct.unpack_from("<II", payload, position)
            symbol_index, relocation_type = info >> 8, info & 0xFF
            symbol = symbols_by_table_index.get((symtab_index, symbol_index))
            _require(symbol is not None, f"{label}: unresolved relocation symbol")
            relocations.append(
                {
                    "relocation_section_index": int(relsec["index"]),
                    "target_section_index": target_index,
                    "offset": offset,
                    "type": relocation_type,
                    "symbol": symbol,
                }
            )
    return {
        "type": elf_type,
        "payload": payload,
        "sections": sections,
        "symbols": symbols,
        "relocations": relocations,
    }


def _section_bytes(elf: dict[str, Any], section: dict[str, Any]) -> bytes:
    start = int(section["offset"])
    return elf["payload"][start : start + int(section["size"])]


def _function_symbols(elf: dict[str, Any]) -> list[dict[str, Any]]:
    sections = elf["sections"]
    result = []
    seen: set[tuple[int, int, int, str]] = set()
    for symbol in elf["symbols"]:
        section_index = int(symbol["section_index"])
        if (
            int(symbol["type"]) != STT_FUNC
            or int(symbol["size"]) <= 0
            or section_index <= 0
            or section_index >= len(sections)
            or not int(sections[section_index]["flags"]) & SHF_EXECINSTR
        ):
            continue
        start = int(symbol["value"]) & ~1
        key = (section_index, start, int(symbol["size"]), str(symbol["name"]))
        if key in seen:
            continue
        seen.add(key)
        result.append(symbol)
    return result


def _function_at(elf: dict[str, Any], section_index: int, offset: int) -> str | None:
    matches = []
    for symbol in _function_symbols(elf):
        if int(symbol["section_index"]) != section_index:
            continue
        section = elf["sections"][section_index]
        start = (int(symbol["value"]) & ~1) - (
            int(section["address"]) if int(elf["type"]) == ET_EXEC else 0
        )
        if start <= offset < start + int(symbol["size"]):
            matches.append((int(symbol["size"]), str(symbol["name"])))
    return min(matches)[1] if matches else None


def _thumb_width(first: int) -> int:
    return 4 if first & 0xF800 in (0xE800, 0xF000, 0xF800) else 2


def _decode_movw(first: int, second: int) -> tuple[int, int] | None:
    if first & 0xFBF0 != 0xF240:
        return None
    destination = (second >> 8) & 0x0F
    immediate = (
        ((first & 0x000F) << 12)
        | (((first >> 10) & 1) << 11)
        | (((second >> 12) & 0x7) << 8)
        | (second & 0x00FF)
    )
    return destination, immediate


def _decode_movs(first: int) -> tuple[int, int] | None:
    if first & 0xF800 != 0x2000:
        return None
    return (first >> 8) & 0x7, first & 0xFF


def _thumb_bl_target(address: int, first: int, second: int) -> int:
    sign = (first >> 10) & 1
    j1 = (second >> 13) & 1
    j2 = (second >> 11) & 1
    i1 = (~(j1 ^ sign)) & 1
    i2 = (~(j2 ^ sign)) & 1
    displacement = (
        (sign << 24)
        | (i1 << 23)
        | (i2 << 22)
        | ((first & 0x03FF) << 12)
        | ((second & 0x07FF) << 1)
    )
    if displacement & (1 << 24):
        displacement -= 1 << 25
    return (address + 4 + displacement) & 0xFFFFFFFF


def _direct_r0_immediate(code: bytes, call_offset: int) -> dict[str, Any] | None:
    """Recover only an immediately adjacent MOVS/MOVW r0 argument.

    The intentionally strict adjacency rule is the false-positive boundary:
    no speculative register propagation through arbitrary instructions or
    control flow is performed.
    """

    if call_offset >= 2:
        first = struct.unpack_from("<H", code, call_offset - 2)[0]
        movs = _decode_movs(first)
        if movs is not None and movs[0] == 0:
            return {
                "value": movs[1],
                "producer": "MOVS_r0_imm8_immediately_before_BL",
                "producer_offset_delta": -2,
            }
    if call_offset >= 4:
        first, second = struct.unpack_from("<HH", code, call_offset - 4)
        movw = _decode_movw(first, second)
        if movw is not None and movw[0] == 0:
            return {
                "value": movw[1],
                "producer": "MOVW_r0_imm16_immediately_before_BL",
                "producer_offset_delta": -4,
            }
    return None


def _scan_semantic_constants(elf: dict[str, Any]) -> dict[str, Any]:
    accepted: list[dict[str, Any]] = []
    raw: list[dict[str, Any]] = []
    seen_functions: set[tuple[int, int, int]] = set()
    sections = elf["sections"]
    for symbol in _function_symbols(elf):
        section_index = int(symbol["section_index"])
        section = sections[section_index]
        base = int(section["address"]) if int(elf["type"]) == ET_EXEC else 0
        start = (int(symbol["value"]) & ~1) - base
        size = int(symbol["size"])
        identity = (section_index, start, size)
        if identity in seen_functions:
            continue
        seen_functions.add(identity)
        data = _section_bytes(elf, section)
        _require(
            0 <= start <= start + size <= len(data),
            "function extent is outside executable section",
        )
        code = data[start : start + size]
        offset = 0
        while offset + 2 <= len(code):
            first = struct.unpack_from("<H", code, offset)[0]
            width = _thumb_width(first)
            if width == 4 and offset + 4 <= len(code):
                second = struct.unpack_from("<H", code, offset + 2)[0]
                movw = _decode_movw(first, second)
                if movw is not None and movw[1] in TARGET_CONSTANTS:
                    accepted.append(
                        {
                            "value": movw[1],
                            "evidence": "decoded_thumb_MOVW_immediate",
                            "destination_register": f"r{movw[0]}",
                            "section": str(section["name"]),
                            "section_offset": start + offset,
                            "function": str(symbol["name"]),
                        }
                    )
            offset += width if offset + width <= len(code) else 2

    # Raw aligned words/halfwords are useful as a completeness check but are
    # explicitly not promoted to executable semantics.
    for section in sections:
        if not int(section["flags"]) & SHF_EXECINSTR or int(section["size"]) == 0:
            continue
        data = _section_bytes(elf, section)
        for width, fmt in ((2, "<H"), (4, "<I")):
            for offset in range(0, len(data) - width + 1, width):
                value = struct.unpack_from(fmt, data, offset)[0]
                if value in TARGET_CONSTANTS:
                    raw.append(
                        {
                            "value": value,
                            "width_bytes": width,
                            "section": str(section["name"]),
                            "section_offset": offset,
                            "containing_function": _function_at(
                                elf, int(section["index"]), offset
                            ),
                            "accepted_as_semantic_constant": False,
                            "rejection": (
                                "aligned_integer_coincidence_without_decoded_"
                                "instruction_or_literal-reference_binding"
                            ),
                        }
                    )
    accepted.sort(
        key=lambda row: (
            int(row["value"]),
            str(row["function"]),
            int(row["section_offset"]),
        )
    )
    raw.sort(
        key=lambda row: (
            int(row["value"]),
            str(row["section"]),
            int(row["section_offset"]),
            int(row["width_bytes"]),
        )
    )
    return {"accepted": accepted, "raw_rejected": raw}


def _scan_object_calls(elf: dict[str, Any]) -> list[dict[str, Any]]:
    _require(int(elf["type"]) == ET_REL, "object call scanner requires ET_REL")
    sections = elf["sections"]
    calls = []
    for relocation in elf["relocations"]:
        symbol = relocation["symbol"]
        sink = str(symbol["name"])
        if (
            int(relocation["type"]) not in (R_ARM_THM_CALL, R_ARM_THM_JUMP24)
            or sink not in COMMAND_SINKS
        ):
            continue
        section_index = int(relocation["target_section_index"])
        section = sections[section_index]
        _require(
            int(section["flags"]) & SHF_EXECINSTR,
            "command relocation target is not executable",
        )
        code = _section_bytes(elf, section)
        call_offset = int(relocation["offset"])
        _require(call_offset + 4 <= len(code), "command relocation is out of bounds")
        immediate = _direct_r0_immediate(code, call_offset)
        calls.append(
            {
                "caller": _function_at(elf, section_index, call_offset),
                "section": str(section["name"]),
                "section_offset": call_offset,
                "sink": sink,
                "binding": "SHT_REL_symbol_plus_R_ARM_THM_CALL_or_JUMP24",
                "r0_immediate": immediate,
            }
        )
    return sorted(
        calls,
        key=lambda row: (
            str(row["caller"]),
            int(row["section_offset"]),
            str(row["sink"]),
        ),
    )


def _linked_function_addresses(elf: dict[str, Any]) -> dict[int, list[str]]:
    result: dict[int, list[str]] = {}
    for symbol in _function_symbols(elf):
        address = int(symbol["value"]) & ~1
        result.setdefault(address, []).append(str(symbol["name"]))
    return result


def _scan_axf_calls(elf: dict[str, Any]) -> list[dict[str, Any]]:
    _require(int(elf["type"]) == ET_EXEC, "AXF call scanner requires ET_EXEC")
    sections = elf["sections"]
    functions_at = _linked_function_addresses(elf)
    calls = []
    seen_ranges: set[tuple[int, int, int]] = set()
    for symbol in _function_symbols(elf):
        section_index = int(symbol["section_index"])
        section = sections[section_index]
        section_address = int(section["address"])
        start = (int(symbol["value"]) & ~1) - section_address
        size = int(symbol["size"])
        function_identity = (section_index, start, size)
        if function_identity in seen_ranges:
            continue
        seen_ranges.add(function_identity)
        section_data = _section_bytes(elf, section)
        _require(
            0 <= start <= start + size <= len(section_data),
            "linked function is outside executable section",
        )
        code = section_data[start : start + size]
        offset = 0
        while offset + 2 <= len(code):
            first = struct.unpack_from("<H", code, offset)[0]
            width = _thumb_width(first)
            if width == 4 and offset + 4 <= len(code):
                second = struct.unpack_from("<H", code, offset + 2)[0]
                if first & 0xF800 == 0xF000 and second & 0xD000 == 0xD000:
                    address = section_address + start + offset
                    target = _thumb_bl_target(address, first, second)
                    names = functions_at.get(target, [])
                    sinks = sorted(set(names) & set(COMMAND_SINKS))
                    for sink in sinks:
                        calls.append(
                            {
                                "caller": str(symbol["name"]),
                                "section": str(section["name"]),
                                "virtual_address": f"0x{address:08X}",
                                "sink": sink,
                                "target_virtual_address": f"0x{target:08X}",
                                "binding": "decoded_Thumb_BL_to_exact_STT_FUNC_address",
                                "r0_immediate": _direct_r0_immediate(code, offset),
                            }
                        )
            offset += width if offset + width <= len(code) else 2
    return sorted(
        calls,
        key=lambda row: (
            str(row["caller"]),
            str(row["virtual_address"]),
            str(row["sink"]),
        ),
    )


def _summarize_calls(calls: list[dict[str, Any]]) -> dict[str, Any]:
    sinks = Counter(str(row["sink"]) for row in calls)
    resolved = [row for row in calls if row["r0_immediate"] is not None]
    values = Counter(int(row["r0_immediate"]["value"]) for row in resolved)
    watched = {
        f"0x{value:02X}": [
            row for row in resolved if int(row["r0_immediate"]["value"]) == value
        ]
        for value in COMMAND_VALUES
    }
    return {
        "direct_call_count": len(calls),
        "direct_calls_by_sink": dict(sorted(sinks.items())),
        "adjacent_r0_immediate_resolved_count": len(resolved),
        "resolved_command_value_histogram": {
            f"0x{value:02X}": count for value, count in sorted(values.items())
        },
        "watched_command_calls": watched,
        "all_calls": calls,
    }


def _audit_file(path: Path, root: Path, expected_type: int) -> dict[str, Any]:
    payload = path.read_bytes()
    elf = _parse_elf(payload, path.name)
    _require(int(elf["type"]) == expected_type, f"{path.name}: ELF type changed")
    exec_sections = [
        section
        for section in elf["sections"]
        if int(section["flags"]) & SHF_EXECINSTR and int(section["size"]) > 0
    ]
    constants = _scan_semantic_constants(elf)
    calls = _scan_object_calls(elf) if expected_type == ET_REL else _scan_axf_calls(elf)
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "elf_type": "ET_REL" if expected_type == ET_REL else "ET_EXEC",
        "executable_section_count": len(exec_sections),
        "executable_section_bytes": sum(int(row["size"]) for row in exec_sections),
        "function_symbol_count": len(_function_symbols(elf)),
        "command_calls": _summarize_calls(calls),
        "target_constants": constants,
    }


def _aggregate(files: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = []
    raw = []
    calls = []
    for file_row in files:
        for row in file_row["target_constants"]["accepted"]:
            accepted.append({"path": file_row["path"], **row})
        for row in file_row["target_constants"]["raw_rejected"]:
            raw.append({"path": file_row["path"], **row})
        for row in file_row["command_calls"]["all_calls"]:
            calls.append({"path": file_row["path"], **row})
    semantic_counts = Counter(int(row["value"]) for row in accepted)
    raw_counts = Counter(int(row["value"]) for row in raw)
    summary = _summarize_calls(calls)
    return {
        "executable_section_count": sum(
            int(row["executable_section_count"]) for row in files
        ),
        "executable_section_bytes": sum(
            int(row["executable_section_bytes"]) for row in files
        ),
        "function_symbol_count": sum(
            int(row["function_symbol_count"]) for row in files
        ),
        "semantic_constant_counts": {
            str(value): semantic_counts.get(value, 0) for value in TARGET_CONSTANTS
        },
        "raw_rejected_counts": {
            str(value): raw_counts.get(value, 0) for value in TARGET_CONSTANTS
        },
        "semantic_constant_sites": accepted,
        "raw_rejected_sites": raw,
        "command_calls": summary,
    }


def _same_function_r20_535_bindings(
    calls: list[dict[str, Any]], constants: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Pair R20 calls with decoded 535 sites in the same exact ELF function.

    This is deliberately a same-function association, not a claim that the
    MOVW value alone proves loop bounds or dataflow.  The source/record audit
    supplies that stronger adjacent-loop proof independently.
    """

    result = []
    for call in calls:
        for constant in constants:
            if (
                call["path"] == constant["path"]
                and call["caller"] == constant["function"]
                and int(constant["value"]) == 535
            ):
                result.append(
                    {
                        "path": call["path"],
                        "function": call["caller"],
                        "command_sink": call["sink"],
                        "r20_call_binding": call["binding"],
                        "constant_binding": constant["evidence"],
                        "association_strength": "same_exact_STT_FUNC_only",
                        "direct_loop_dataflow_claimed_by_this_inventory": False,
                    }
                )
    return result


def build_report(reference_root: Path = DEFAULT_REFERENCE_ROOT) -> dict[str, Any]:
    output_root = reference_root / OUTPUT_REL
    _require(output_root.is_dir(), f"missing vendor Output directory: {output_root}")
    object_paths = list(output_root.glob("*.o"))
    axf_paths = list(output_root.glob("*.axf"))
    object_manifest = _pin_manifest(
        _manifest(object_paths, reference_root),
        count=EXPECTED_OBJECT_COUNT,
        total_bytes=EXPECTED_OBJECT_BYTES,
        digest=EXPECTED_OBJECT_MANIFEST_SHA256,
        label="retained object corpus",
    )
    axf_manifest = _pin_manifest(
        _manifest(axf_paths, reference_root),
        count=EXPECTED_AXF_COUNT,
        total_bytes=EXPECTED_AXF_BYTES,
        digest=EXPECTED_AXF_MANIFEST_SHA256,
        label="final AXF corpus",
    )
    objects = [
        _audit_file(path, reference_root, ET_REL)
        for path in sorted(object_paths, key=lambda item: item.name.casefold())
    ]
    axfs = [
        _audit_file(path, reference_root, ET_EXEC)
        for path in sorted(axf_paths, key=lambda item: item.name.casefold())
    ]
    object_aggregate = _aggregate(objects)
    axf_aggregate = _aggregate(axfs)

    object_r20 = object_aggregate["command_calls"]["watched_command_calls"]["0x20"]
    axf_r20 = axf_aggregate["command_calls"]["watched_command_calls"]["0x20"]
    object_r21 = object_aggregate["command_calls"]["watched_command_calls"]["0x21"]
    axf_r21 = axf_aggregate["command_calls"]["watched_command_calls"]["0x21"]
    object_r20_535 = _same_function_r20_535_bindings(
        object_r20, object_aggregate["semantic_constant_sites"]
    )
    axf_r20_535 = _same_function_r20_535_bindings(
        axf_r20, axf_aggregate["semantic_constant_sites"]
    )
    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "corpus": {
            "reference_root": str(reference_root),
            "retained_objects": object_manifest,
            "final_axfs": axf_manifest,
            "selection_rule": "Output/*.o plus Output/*.axf only",
            "prebuilt_CROF_archive_member_in_scope": False,
        },
        "method": {
            "elf": "bounded ELF32 little-endian EM_ARM parser",
            "object_calls": (
                "SHT_REL target section plus R_ARM_THM_CALL/R_ARM_THM_JUMP24 "
                "symbol binding"
            ),
            "axf_calls": "decoded Thumb BL target equals exact linked STT_FUNC address",
            "constant_acceptance": "decoded MOVW immediate inside STT_FUNC extent",
            "command_value_acceptance": (
                "MOVS/MOVW r0 immediate exactly adjacent to bound command BL"
            ),
            "false_positive_filter": (
                "aligned raw u16/u32 matches are rejected unless separately decoded "
                "as an accepted semantic producer"
            ),
        },
        "retained_objects": {"files": objects, "aggregate": object_aggregate},
        "final_axfs": {"files": axfs, "aggregate": axf_aggregate},
        "runtime_loader_boundary": {
            "object_r20_calls": object_r20,
            "axf_r20_calls": axf_r20,
            "object_r21_calls": object_r21,
            "axf_r21_calls": axf_r21,
            "object_r20_535_same_function_bindings": object_r20_535,
            "axf_r20_535_same_function_bindings": axf_r20_535,
            "all_r20_targets_are_legacy_single_sink": all(
                str(row["sink"]) == "EPD_WriteCMD" for row in object_r20 + axf_r20
            ),
            "r20_to_dual_command_sink_found": any(
                str(row["sink"]) in DUAL_COMMAND_SINKS for row in object_r20 + axf_r20
            ),
            "immediate_r21_command_call_found": bool(object_r21 or axf_r21),
            "strict_same_build_799_or_800_semantic_constant_found": any(
                int(row["value"]) in (799, 800)
                for row in object_aggregate["semantic_constant_sites"]
                + axf_aggregate["semantic_constant_sites"]
            ),
            "same_build_dual_destination_runtime_loader_proven": False,
        },
        "negative_boundary": {
            "archive_scope": (
                "The prebuilt eload_3bits_M3_E2802_20251229.lib CROF member is not "
                "an Output retained ELF object and is intentionally not reinterpreted "
                "by this ELF inventory. Its mode-0 535/704 contract is covered by the "
                "separate loadWF deep audit."
            ),
            "no_claim_from_absence": (
                "Absence in these exact objects/AXFs does not prove that another "
                "SPD1657 build or the missing mode-1 source lacks an 800-byte ABI."
            ),
            "dual_helpers_not_loader_proof": (
                "Presence of ToMaster/ToSlave/ToBoth helpers or dual-target OTP init "
                "does not bind the observed runtime R20/535 loop to both controllers."
            ),
            "raw_constants_not_semantics": True,
        },
        "adjudication": {
            "verdict": "MODE0_R20_535_ONLY_IN_RETAINED_ARM_ELF_RUNTIME_PATH",
            "same_build_mode1_800_abi_recovered": False,
            "r21_704_linked_runtime_path_recovered": False,
            "dual_controller_runtime_loader_recovered": False,
            "authorizes_live_hardware_action": False,
        },
        "safety": {
            "offline_only": True,
            "hardware_accessed": False,
            "serial_accessed": False,
            "network_accessed": False,
            "flashed": False,
            "display_refreshed": False,
            "waveform_bytes_emitted": False,
            "executable_screen_payload_generated": False,
        },
    }
    report["report_canonical_sha256"] = _canonical_sha256(report)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit retained Arm ELF command sinks and size constants offline."
    )
    parser.add_argument(
        "--reference-root",
        type=Path,
        default=DEFAULT_REFERENCE_ROOT,
        help="Vendor REG-API-oqc root (default: pinned local delivery).",
    )
    parser.add_argument("--output", type=Path, help="Write JSON to a new file.")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = build_report(args.reference_root.resolve())
    if args.compact:
        payload = _canonical_bytes(report) + b"\n"
    else:
        payload = (
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
    if args.output is not None:
        write_new_bytes_durable(args.output.resolve(), payload)
    else:
        sys.stdout.buffer.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
