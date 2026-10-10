#!/usr/bin/env python3
"""Recover source-line coverage from the pinned ArmCC loadWF object.

The retained ArmCC object contains DWARF-v3 ``.debug_line`` contributions even
though the original ``eload_20250305b1.c`` source is absent.  This offline tool
parses every structurally valid line program, binds the 23 non-empty main-source
programs to the already identity-pinned function inventory, and maps the six
``loadWF`` call instructions to source-line intervals.

It recovers line coordinates, not source text, preprocessor-inactive branches,
or a mode-1 implementation.  It emits no key, plaintext, waveform, payload, or
authorization material and performs no hardware, serial, network, or firmware
operation.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any, Final

from host.application.durable_io import DurableWriteError, write_new_bytes_durable
from tools import mf1750_armcc_loadwf_deep_audit as deep


KIND: Final = "mf1750-armcc-dwarf-line-audit"
SCHEMA_VERSION: Final = 1
MAIN_SOURCE: Final = r"..\EPD\eload_20250305b1.c"
EXPECTED_LINE_UNIT_COUNT: Final = 31
EXPECTED_MAIN_SOURCE_LINE_UNIT_COUNT: Final = 24
EXPECTED_FUNCTION_COUNT: Final = 23
LOADWF_UNIT_OFFSET: Final = 0x5C58


class DwarfLineAuditError(RuntimeError):
    """Raised when a pinned line-program invariant changes."""


@dataclass(frozen=True)
class LineRow:
    address: int
    line: int
    file_index: int
    end_sequence: bool


@dataclass(frozen=True)
class LineUnit:
    member_offset: int
    payload: bytes
    version: int
    header_bytes: int
    minimum_instruction_bytes: int
    default_is_stmt: bool
    line_base: int
    line_range: int
    opcode_base: int
    files: tuple[str, ...]
    rows: tuple[LineRow, ...]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DwarfLineAuditError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(report: dict[str, Any]) -> bytes:
    return json.dumps(
        report,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _read_uleb128(payload: bytes, offset: int, end: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < end and shift < 64:
        byte = payload[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
    raise DwarfLineAuditError("invalid ULEB128 in line program")


def _read_sleb128(payload: bytes, offset: int, end: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < end and shift < 64:
        byte = payload[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            if byte & 0x40:
                value |= -(1 << shift)
            return value, offset
    raise DwarfLineAuditError("invalid SLEB128 in line program")


def _read_c_string(payload: bytes, offset: int, end: int) -> tuple[str, int]:
    terminator = payload.find(b"\x00", offset, end)
    if terminator < 0:
        raise DwarfLineAuditError("unterminated string in line-program header")
    return payload[offset:terminator].decode("latin-1"), terminator + 1


def _candidate_geometry(payload: bytes, offset: int) -> tuple[int, int] | None:
    if offset + 15 > len(payload):
        return None
    unit_length = struct.unpack_from("<I", payload, offset)[0]
    end = offset + 4 + unit_length
    if unit_length < 20 or unit_length > 20_000 or end > len(payload):
        return None
    version = struct.unpack_from("<H", payload, offset + 4)[0]
    if version != 3:
        return None
    header_length = struct.unpack_from("<I", payload, offset + 6)[0]
    if header_length < 10 or 10 + header_length > unit_length:
        return None
    minimum_instruction = payload[offset + 10]
    default_is_stmt = payload[offset + 11]
    line_base = int.from_bytes(
        payload[offset + 12 : offset + 13], "little", signed=True
    )
    line_range = payload[offset + 13]
    opcode_base = payload[offset + 14]
    if (
        minimum_instruction not in (1, 2, 4)
        or default_is_stmt not in (0, 1)
        or not -20 <= line_base <= 0
        or not 1 <= line_range <= 50
        or not 1 <= opcode_base <= 30
    ):
        return None
    return end, header_length


def _parse_line_unit(payload: bytes, offset: int) -> LineUnit:
    geometry = _candidate_geometry(payload, offset)
    _require(geometry is not None, "invalid line-unit geometry")
    end, header_length = geometry
    version = struct.unpack_from("<H", payload, offset + 4)[0]
    minimum_instruction = payload[offset + 10]
    default_is_stmt = bool(payload[offset + 11])
    line_base = int.from_bytes(
        payload[offset + 12 : offset + 13], "little", signed=True
    )
    line_range = payload[offset + 13]
    opcode_base = payload[offset + 14]
    standard_lengths = tuple(payload[offset + 15 : offset + 14 + opcode_base])
    header_end = offset + 10 + header_length
    cursor = offset + 14 + opcode_base

    while cursor < header_end and payload[cursor] != 0:
        _, cursor = _read_c_string(payload, cursor, header_end)
    _require(cursor < header_end, "directory table has no terminator")
    cursor += 1

    files: list[str] = []
    while cursor < header_end and payload[cursor] != 0:
        name, cursor = _read_c_string(payload, cursor, header_end)
        _, cursor = _read_uleb128(payload, cursor, header_end)
        _, cursor = _read_uleb128(payload, cursor, header_end)
        _, cursor = _read_uleb128(payload, cursor, header_end)
        files.append(name)
    _require(cursor < header_end, "file table has no terminator")
    cursor += 1
    _require(cursor == header_end, "line-program header extent changed")

    address = 0
    file_index = 1
    line = 1
    rows: list[LineRow] = []
    while cursor < end:
        opcode = payload[cursor]
        cursor += 1
        if opcode == 0:
            extended_bytes, cursor = _read_uleb128(payload, cursor, end)
            extended_end = cursor + extended_bytes
            _require(
                extended_bytes > 0 and extended_end <= end,
                "invalid extended line opcode",
            )
            subopcode = payload[cursor]
            cursor += 1
            if subopcode == 1:  # DW_LNE_end_sequence
                rows.append(LineRow(address, line, file_index, True))
                address, file_index, line = 0, 1, 1
            elif subopcode == 2:  # DW_LNE_set_address
                address = int.from_bytes(payload[cursor:extended_end], "little")
            else:
                _require(subopcode == 3, "unsupported extended line opcode")
            cursor = extended_end
            continue

        if opcode < opcode_base:
            if opcode == 1:  # DW_LNS_copy
                rows.append(LineRow(address, line, file_index, False))
            elif opcode == 2:  # DW_LNS_advance_pc
                operand, cursor = _read_uleb128(payload, cursor, end)
                address += operand * minimum_instruction
            elif opcode == 3:  # DW_LNS_advance_line
                operand, cursor = _read_sleb128(payload, cursor, end)
                line += operand
            elif opcode == 4:  # DW_LNS_set_file
                file_index, cursor = _read_uleb128(payload, cursor, end)
            elif opcode == 5:  # DW_LNS_set_column
                _, cursor = _read_uleb128(payload, cursor, end)
            elif opcode in (6, 7, 10, 11):
                pass
            elif opcode == 8:  # DW_LNS_const_add_pc
                address += ((255 - opcode_base) // line_range) * minimum_instruction
            elif opcode == 9:  # DW_LNS_fixed_advance_pc
                _require(cursor + 2 <= end, "truncated fixed PC advance")
                address += int.from_bytes(payload[cursor : cursor + 2], "little")
                cursor += 2
            elif opcode == 12:  # DW_LNS_set_isa
                _, cursor = _read_uleb128(payload, cursor, end)
            else:
                operand_count = standard_lengths[opcode - 1]
                for _ in range(operand_count):
                    _, cursor = _read_uleb128(payload, cursor, end)
            continue

        adjusted = opcode - opcode_base
        address += (adjusted // line_range) * minimum_instruction
        line += line_base + adjusted % line_range
        rows.append(LineRow(address, line, file_index, False))

    _require(cursor == end, "line-program parser crossed unit boundary")
    return LineUnit(
        member_offset=offset,
        payload=payload[offset:end],
        version=version,
        header_bytes=header_length,
        minimum_instruction_bytes=minimum_instruction,
        default_is_stmt=default_is_stmt,
        line_base=line_base,
        line_range=line_range,
        opcode_base=opcode_base,
        files=tuple(files),
        rows=tuple(rows),
    )


def _find_line_units(payload: bytes) -> list[LineUnit]:
    units: list[LineUnit] = []
    offset = 0
    while offset < len(payload):
        geometry = _candidate_geometry(payload, offset)
        if geometry is None:
            offset += 1
            continue
        try:
            unit = _parse_line_unit(payload, offset)
        except DwarfLineAuditError:
            offset += 1
            continue
        units.append(unit)
        offset += len(unit.payload)
    return units


def _line_for_instruction(unit: LineUnit, instruction_offset: int) -> int:
    candidates = [
        row
        for row in unit.rows
        if not row.end_sequence and row.address <= instruction_offset
    ]
    _require(candidates, "call precedes first line row")
    return max(candidates, key=lambda row: row.address).line


def _unit_summary(unit: LineUnit) -> dict[str, Any]:
    non_end = [row for row in unit.rows if not row.end_sequence]
    end_rows = [row for row in unit.rows if row.end_sequence]
    return {
        "member_offset": unit.member_offset,
        "bytes": len(unit.payload),
        "sha256": _sha256(unit.payload),
        "version": unit.version,
        "header_bytes": unit.header_bytes,
        "minimum_instruction_bytes": unit.minimum_instruction_bytes,
        "default_is_stmt": unit.default_is_stmt,
        "line_base": unit.line_base,
        "line_range": unit.line_range,
        "opcode_base": unit.opcode_base,
        "files": list(unit.files),
        "row_count_including_end_sequence": len(unit.rows),
        "end_sequence_count": len(end_rows),
        "address_end": end_rows[-1].address if end_rows else None,
        "first_row_source_line": non_end[0].line if non_end else None,
        "final_row_source_line": non_end[-1].line if non_end else None,
        "minimum_source_line": min((row.line for row in non_end), default=None),
        "maximum_source_line": max((row.line for row in non_end), default=None),
        "raw_line_program_or_source_text_emitted": False,
    }


def build_report() -> dict[str, Any]:
    object_body, archive = deep._read_object(deep.DEFAULT_LIBRARY)  # noqa: SLF001
    deep_report = deep.build_report()
    units = _find_line_units(object_body)
    _require(len(units) == EXPECTED_LINE_UNIT_COUNT, "line-unit count changed")
    main_units = [unit for unit in units if unit.files == (MAIN_SOURCE,)]
    _require(
        len(main_units) == EXPECTED_MAIN_SOURCE_LINE_UNIT_COUNT,
        "main-source line-unit count changed",
    )
    empty = [
        unit for unit in main_units if len(unit.rows) == 1 and unit.rows[0].end_sequence
    ]
    _require(len(empty) == 1, "expected one empty main-source line unit")
    function_units = [unit for unit in main_units if unit not in empty]
    _require(
        len(function_units) == EXPECTED_FUNCTION_COUNT,
        "function line-unit count changed",
    )

    functions = deep_report["function_inventory"]["functions"]
    _require(len(functions) == EXPECTED_FUNCTION_COUNT, "function inventory changed")
    bindings: list[dict[str, Any]] = []
    for unit in function_units:
        summary = _unit_summary(unit)
        candidates = [
            function
            for function in functions
            if function["bytes"] == summary["address_end"]
            and 0 <= summary["first_row_source_line"] - function["dwarf_decl_line"] <= 5
        ]
        _require(len(candidates) == 1, "line unit does not uniquely bind to a function")
        function = candidates[0]
        bindings.append(
            {
                "function": function["name"],
                "function_bytes": function["bytes"],
                "function_sha256": function["sha256"],
                "dwarf_decl_line": function["dwarf_decl_line"],
                "declaration_to_first_mapped_line_delta": (
                    summary["first_row_source_line"] - function["dwarf_decl_line"]
                ),
                "line_unit": summary,
                "binding_key": (
                    "exact function bytes/address_end plus unique first mapped line "
                    "within 0..5 lines after the DWARF declaration"
                ),
            }
        )
    _require(
        {row["function"] for row in bindings} == {row["name"] for row in functions},
        "not every function was bound exactly once",
    )

    loadwf_units = [
        unit for unit in function_units if unit.member_offset == LOADWF_UNIT_OFFSET
    ]
    _require(len(loadwf_units) == 1, "loadWF line unit is not unique")
    loadwf_unit = loadwf_units[0]
    loadwf_binding = next(row for row in bindings if row["function"] == "loadWF")
    _require(
        loadwf_binding["line_unit"]["address_end"] == 136, "loadWF line extent changed"
    )
    call_lines = []
    for call in deep_report["loadwf"]["call_sites"]:
        call_lines.append(
            {
                "instruction_offset": call["offset"],
                "callee": call["callee"],
                "source_line_interval_assignment": _line_for_instruction(
                    loadwf_unit, call["offset"]
                ),
            }
        )
    _require(
        [row["source_line_interval_assignment"] for row in call_lines]
        == [990, 990, 1001, 1002, 1003, 1004],
        "loadWF call-line mapping changed",
    )

    previous = next(
        row for row in bindings if row["function"] == "test_decrypt_cbc_check_key"
    )
    source_gap_start = int(previous["line_unit"]["maximum_source_line"]) + 1
    source_gap_end = int(loadwf_binding["line_unit"]["minimum_source_line"]) - 1
    _require(
        (source_gap_start, source_gap_end) == (935, 986), "source-line gap changed"
    )

    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": "offline_identity_pinned_DWARF_v3_line_metadata_only",
        "input": {
            "library_sha256": archive["sha256"],
            "object_sha256": archive["object"]["sha256"],
            "object_bytes": archive["object"]["bytes"],
            "compiler": "ARM Compiler 5.06 update 3 build 300",
            "source_name": MAIN_SOURCE,
            "source_text_present": False,
        },
        "line_program_inventory": {
            "all_structurally_valid_units": len(units),
            "main_source_units": len(main_units),
            "main_source_empty_units": len(empty),
            "main_source_function_units": len(function_units),
            "all_function_units_uniquely_bound": True,
            "function_bindings": sorted(
                bindings, key=lambda row: row["dwarf_decl_line"]
            ),
            "other_header_source_units": [
                _unit_summary(unit) for unit in units if unit not in main_units
            ],
        },
        "loadWF_source_coordinate_recovery": {
            "line_unit_member_offset": loadwf_unit.member_offset,
            "line_unit_bytes": len(loadwf_unit.payload),
            "line_unit_sha256": _sha256(loadwf_unit.payload),
            "function_bytes": loadwf_binding["function_bytes"],
            "declaration_line": loadwf_binding["dwarf_decl_line"],
            "first_row_mapped_line": loadwf_binding["line_unit"][
                "first_row_source_line"
            ],
            "final_row_mapped_line": loadwf_binding["line_unit"][
                "final_row_source_line"
            ],
            "minimum_mapped_line": loadwf_binding["line_unit"]["minimum_source_line"],
            "maximum_mapped_line": loadwf_binding["line_unit"]["maximum_source_line"],
            "end_sequence_address": loadwf_binding["line_unit"]["address_end"],
            "call_instruction_source_lines": call_lines,
            "four_writeEPD_calls_are_on_consecutive_source_lines_1001_to_1004": True,
            "source_line_gap_immediately_before_loadWF": [
                source_gap_start,
                source_gap_end,
            ],
            "gap_line_count": source_gap_end - source_gap_start + 1,
            "gap_contents_recovered": False,
        },
        "adjudication": {
            "new_direct_fact": (
                "all 23 active functions have exact DWARF line-program bindings; "
                "loadWF maps within source lines 987..1023 (its final row returns to "
                "line 1020), and its four writer calls map to consecutive source-line "
                "intervals 1001..1004"
            ),
            "active_mode0_source_coordinates_recovered": True,
            "original_source_text_recovered": False,
            "preprocessor_inactive_source_recovered": False,
            "source_gap_proves_mode1_branch": False,
            "same_build_mode1_loader_recovered": False,
            "H3_evidence_grade_changed": False,
            "bounded_interpretation": (
                "the line table independently covers the complete active 136-byte mode-0 "
                "loadWF machine function; it cannot reveal comments, blank lines, or "
                "preprocessor-elided code in source lines 935..986 or elsewhere"
            ),
        },
        "material_handling": {
            "raw_line_program_bytes_emitted": False,
            "source_text_emitted": False,
            "key_plaintext_waveform_or_payload_emitted": False,
            "firmware_include_or_release_generated": False,
        },
        "safety": {
            "offline_only": True,
            "hardware_accessed": False,
            "serial_or_COM8_accessed": False,
            "device_network_accessed": False,
            "firmware_or_flash_written": False,
            "display_refresh_attempted": False,
            "authorization_token_generated_or_claimed": False,
            "vendor_evidence_modified": False,
        },
    }
    report["integrity"] = {
        "canonical_encoding": "UTF-8 sorted-key compact JSON excluding integrity",
        "canonical_sha256": _sha256(_canonical_bytes(report)),
    }
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = build_report()
        payload = (
            json.dumps(
                report,
                ensure_ascii=False,
                indent=None if args.compact else 2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        if args.output is None:
            sys.stdout.buffer.write(payload)
        else:
            write_new_bytes_durable(args.output, payload)
    except (
        DwarfLineAuditError,
        deep.DeepAuditError,
        DurableWriteError,
        OSError,
        UnicodeError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
