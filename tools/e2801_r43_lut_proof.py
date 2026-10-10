#!/usr/bin/env python3
"""Prove the legacy E2801.r43 runtime-LUT path without touching hardware.

The IAR object is relocatable UBROF10, not a flat executable.  Every offset
and instruction-record interpretation below is therefore accepted only after
the complete object size and SHA-256 match.  The report deliberately emits
metadata and hashes, never the decoded LUT bytes.

This is evidence from one legacy E2801 object.  Cross-object comparison must
be performed separately; this module does not establish an SPD1657 ABI, a
dual-controller transaction, or a safe live-panel sequence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OBJECT_RELATIVE_PATH = Path(
    "参考资料/E6_73_sample code_V1.2_20250116/"
    "E6_73_sample code_V1.2_20250116/Debug/Obj/E2801.r43"
)
DEFAULT_OBJECT_PATH = REPO_ROOT / OBJECT_RELATIVE_PATH

EXPECTED_OBJECT_SIZE = 315_632
EXPECTED_OBJECT_SHA256 = (
    "404b950ea65b754a335b90be24683281ebee9dab52e362fd6d49170b4b8a38a3"
)

KIND = "legacy-e2801-r43-lut-proof"
SCHEMA_VERSION = 2

# These are identity-pinned UBROF file-record ranges, not linked addresses.
FUNCTION_SECTIONS = {
    "EPD_Init": {
        "section_id": 0x2E,
        "marker_offset": 0x749A,
        "encoded_end_offset": 0x1775A,
        "next_section_id": 0x2D,
    },
    "EPD_Load_LUT": {
        "section_id": 0x1D,
        "marker_offset": 0x1B31A,
        "encoded_end_offset": 0x1BA42,
        "next_section_id": 0x1E,
    },
    "Upload_Temperature_LUT": {
        "section_id": 0x1E,
        "marker_offset": 0x1BA42,
        "encoded_end_offset": 0x1EA64,
        "next_section_id": 0x2A,
    },
}

DATABUFF_STORAGE = {
    "section_id": 0x0E,
    "start_marker_offset": 0x512C,
    "end_marker_offset": 0x5139,
    # The second C7 record establishes the section-relative extent.  This
    # proof does not decode a data-symbol definition that assigns all of that
    # extent to dataBuff, so it must not be reported as symbol capacity.
    "section_extent_bytes": 0x0A00,
}

# These labels are convenient candidates because namespace-1 name records for
# DATA0 and DATA1 exist in the object.  The proof does not decode a definition
# record binding either name to section 0x14/0x15, and it does not read E2802.
TAGGED_ARRAYS = {
    "DATA0": {
        "section_id": 0x14,
        "marker_offset": 0x519E,
        "decoded_length": 1_503,
        "decoded_sha256": (
            "eafe51e741f2e0922a2404abcc016473a203e9824bf91fd550f74ee6e05b8bc5"
        ),
        "encoded_end_offset": 0x5D62,
        "next_section_id": 0x15,
    },
    "DATA1": {
        "section_id": 0x15,
        "marker_offset": 0x5D62,
        "decoded_length": 704,
        "decoded_sha256": (
            "6dbd5a232419da637084683867933a7f60ce06d28a5034136d0f0efae3015e6a"
        ),
        "encoded_end_offset": 0x62E8,
        "next_section_id": 0x18,
    },
}

NAMESPACE_1_SYMBOL_EVIDENCE = {
    "ReadData": {"index": 3, "record_offset": 0x2483},
    "DATA0": {"index": 17, "record_offset": 0x25E3},
    "DATA1": {"index": 18, "record_offset": 0x25F6},
}

COMMAND_ENUM_ANCHORS = {
    "PSR": {"value": 0x00, "offset": 0x2113},
    "LUT0": {"value": 0x20, "offset": 0x2194},
    "LUT1": {"value": 0x21, "offset": 0x21A0},
    "TSC": {"value": 0x40, "offset": 0x21B7},
}

READ_DATA_TWO_BYTE = {
    "argument_setup_and_call_offset": 0x1C959,
    "argument_setup_and_call_bytes": ("372f43370e41370d46374c475d0300000000"),
    "source_record": {
        "line": 509,
        "source": "CALLA   #ReadDatas",
        "offsets": [0x1C9E0, 0x1CAC3],
    },
}

READ_DATA_2508 = {
    "argument_setup_offset": 0x1D20B,
    "argument_setup_bytes": "373f4037cc09373e405e0e00000000",
    "address_and_call_offset": 0x1D2F7,
    "address_and_call_bytes": "370d46374c475d0300000000",
    "source_records": {
        "destination_dataBuff": {
            "line": 518,
            "source": "MOV.W   #dataBuff, R14s",
            "offsets": [0x1D266],
        },
        "ReadData_call": {
            "line": 518,
            "source": "CALLA   #ReadDatas",
            "offsets": [0x1D378, 0x1D45B],
        },
    },
}

EPD_LOAD_LUT_SIGNATURES = {
    "caller_source_and_count_register_copy": {
        "offset": 0x1B3B5,
        "bytes": "370a4d370b4e",
    },
    "counter_clear_and_jump_to_compare": {
        "offset": 0x1B66A,
        "bytes": "3708435e1d00000018",
    },
    "dereference_and_SPI_DATA_call": {
        "offset": 0x1B742,
        "bytes": "376c4a5e1600000000",
    },
    "increment_pointer_counter_compare_and_unsigned_loop": {
        "offset": 0x1B92F,
        "bytes": "371a534937185337089b5e1d0000000e",
    },
}

EPD_LOAD_LUT_SOURCE_RECORDS = {
    "command_call": {
        "line": 465,
        "source": "CALLA   #SPI_COMMANDs",
        "offsets": [0x1B4F5, 0x1B5DB],
    },
    "loop_entry": {
        "line": 466,
        "source": "JMP     ??EPD_Load_LUT_1pa",
        "offsets": [0x1B692],
    },
    "data_call": {
        "line": 468,
        "source": "CALLA   #SPI_DATAs",
        "offsets": [0x1B7C0, 0x1B8A3],
    },
    "unsigned_loop": {
        "line": 466,
        "source": "JNC     ??EPD_Load_LUT_0pa",
        "offsets": [0x1B95E],
    },
}

DISPLAY_SECTIONS = {
    "EPD_Display_White": (0x26, 0x3883C, 0x3AA2F, 0x25, 9),
    "EPD_Display_Black": (0x25, 0x3AA2F, 0x3CE38, 0x24, 9),
    "EPD_Display_Yellow": (0x24, 0x3CE38, 0x3F250, 0x23, 9),
    "EPD_Display_Red": (0x23, 0x3F250, 0x4164A, 0x22, 9),
    "EPD_Display_line_4bit": (0x22, 0x4164A, 0x4319D, 0x21, 4),
    "EPD_Display_Dot": (0x20, 0x43612, 0x45C8E, 0x1F, 14),
    "EPD_Display_Dot_4bit": (0x1F, 0x45C8E, 0x4834B, 0x19, 14),
}

# Exact record signatures in Upload_Temperature_LUT.  They encode the small
# instruction/relocation fragments used for the semantic claims in the report.
UPLOAD_SIGNATURES = {
    "temperature_command_40": {
        "offset": 0x1BED1,
        "bytes": "377c403740005e1900000000",
    },
    "PSR_mode_1_command_00": {
        "offset": 0x1D69E,
        "bytes": "374c435e1900000000",
        "expected_occurrences": [0x1D69E, 0x1DC3E],
    },
    "PSR_mode_1_dataBuff_2_or_20": {
        "offset": 0x1D96D,
        "bytes": "377cd03720005e1600000000",
    },
    "PSR_other_command_00": {
        "offset": 0x1DC3E,
        "bytes": "374c435e1900000000",
        "expected_occurrences": [0x1D69E, 0x1DC3E],
    },
    "PSR_other_dataBuff_2_and_df": {
        "offset": 0x1DF0D,
        "bytes": "377cf037df005e1600000000",
    },
    "lut0_count_031f_and_dataBuff_plus_4": {
        "offset": 0x1E0FE,
        "bytes": "373e40371f03373d405e0e00000004",
    },
    "lut0_command_20_and_call_section_1d": {
        "offset": 0x1E1EE,
        "bytes": "373c403720005e1d00000000",
    },
    "lut1_command_21_and_call_section_19": {
        "offset": 0x1E3E6,
        "bytes": "377c403721005e1900000000",
    },
    "lut1_loop_counter_clear_and_jump_to_compare": {
        "offset": 0x1E5DC,
        "bytes": "370b435e1e000000ea",
    },
    "lut1_ff_and_call_section_16": {
        "offset": 0x1E6BF,
        "bytes": "377c435e1600000000",
    },
    "lut1_increment_compare_02c0_and_loop_branch": {
        "offset": 0x1E8AD,
        "bytes": "371b53373b9037c0025e1e000000e2",
    },
}

UPLOAD_SOURCE_RECORDS = {
    "temperature_command": {
        "line": 498,
        "source": "CALLA   #SPI_COMMANDs",
        "offsets": [0x1BF52, 0x1C038],
    },
    "temperature_busy": {
        "line": 499,
        "source": "CALLA   #check_busy_highs",
        "offsets": [0x1C142, 0x1C22C],
    },
    "temperature_read": {
        "line": 501,
        "source": "CALLA   #SPI_GET_DATAs",
        "offsets": [0x1C340, 0x1C427],
    },
    "mode_compare": {
        "line": 520,
        "source": "CMP.B   #0x1, &V_modes",
        "offsets": [0x1D52E],
    },
    "mode_not_equal_branch": {
        "line": 520,
        "source": "JNE     ??Upload_Temperature_LUT_10pa",
        "offsets": [0x1D5E3],
    },
    "PSR_mode_1_command": {
        "line": 522,
        "source": "CALLA   #SPI_COMMANDs",
        "offsets": [0x1D71C, 0x1D802],
    },
    "PSR_mode_1_data_source": {
        "line": 523,
        "source": "MOV.B   &dataBuff + 2, R12s",
        "offsets": [0x1D8D8],
    },
    "PSR_mode_1_data_call": {
        "line": 523,
        "source": "CALLA   #SPI_DATAs",
        "offsets": [0x1D9EE, 0x1DAD1],
    },
    "PSR_mode_1_join_jump": {
        "line": 523,
        "source": "JMP     ??Upload_Temperature_LUT_11pa",
        "offsets": [0x1DB82],
    },
    "PSR_other_command": {
        "line": 527,
        "source": "CALLA   #SPI_COMMANDs",
        "offsets": [0x1DCBC, 0x1DDA2],
    },
    "PSR_other_data_source": {
        "line": 528,
        "source": "MOV.B   &dataBuff + 2, R12s",
        "offsets": [0x1DE78],
    },
    "PSR_other_data_call": {
        "line": 528,
        "source": "CALLA   #SPI_DATAs",
        "offsets": [0x1DF8E, 0x1E071],
    },
    "lut0_pointer": {
        "line": 553,
        "source": "MOV.W   #dataBuff + 4, R13s",
        "offsets": [0x1E159],
    },
    "lut0_call": {
        "line": 553,
        "source": "CALLA   #EPD_Load_LUTs",
        "offsets": [0x1E26F, 0x1E356],
    },
    "lut1_command": {
        "line": 555,
        "source": "CALLA   #SPI_COMMANDs",
        "offsets": [0x1E467, 0x1E54D],
    },
    "lut1_pretest_jump": {
        "line": 556,
        "source": "JMP     ??Upload_Temperature_LUT_12pa",
        "offsets": [0x1E604],
    },
    "lut1_data": {
        "line": 558,
        "source": "CALLA   #SPI_DATAs",
        "offsets": [0x1E73D, 0x1E820],
    },
    "lut1_less_than_backedge": {
        "line": 556,
        "source": "JL      ??Upload_Temperature_LUT_1pa",
        "offsets": [0x1E8DB],
    },
}

DISPLAY_CALLERS = (
    ("EPD_Display_White", 0x26, 1420, (0x38B82, 0x38C74)),
    ("EPD_Display_Black", 0x25, 1492, (0x3AD99, 0x3AE8B)),
    ("EPD_Display_Yellow", 0x24, 1555, (0x3D1A2, 0x3D294)),
    ("EPD_Display_Red", 0x23, 1619, (0x3F5BA, 0x3F6AC)),
    ("EPD_Display_line_4bit", 0x22, 1677, (0x41915, 0x41A07)),
    ("EPD_Display_Dot", 0x20, 1738, (0x439CB, 0x43ABD)),
    ("EPD_Display_Dot_4bit", 0x1F, 1794, (0x46045, 0x46137)),
)

SOURCE_RECORD_RE = re.compile(
    rb" File: (?P<file>[^\x00\r\n]+), Line: (?P<line>\d+) \n"
    rb" Source: (?P<source>[ -~]+)"
)
DIRECT_CALL_RE = re.compile(
    rb" File: (?P<file>[^\x00\r\n]+), Line: (?P<line>\d+) \n"
    rb" Source: (?P<source>CALLA\s+#(?P<symbol>[A-Za-z0-9_?$@.]+)s)"
    rb"\xff\xff\x80\x00\x00\x00\xff\xff\x9d\x00\x5b"
    rb"(?P<operator>[\x5d\x5e])(?P<target_id>.)(?P<addend>.{4})",
    re.DOTALL,
)

EXPECTED_UPLOAD_DIRECT_CALLS = (
    (0x1BF52, 498, "SPI_COMMAND", 0x5E, 0x19),
    (0x1C142, 499, "check_busy_high", 0x5E, 0x18),
    (0x1C340, 501, "SPI_GET_DATA", 0x5E, 0x1C),
    (0x1C7D6, 506, "?Mul32", 0x5D, 0x02),
    (0x1C9E0, 509, "ReadData", 0x5D, 0x03),
    (0x1D378, 518, "ReadData", 0x5D, 0x03),
    (0x1D71C, 522, "SPI_COMMAND", 0x5E, 0x19),
    (0x1D9EE, 523, "SPI_DATA", 0x5E, 0x16),
    (0x1DCBC, 527, "SPI_COMMAND", 0x5E, 0x19),
    (0x1DF8E, 528, "SPI_DATA", 0x5E, 0x16),
    (0x1E26F, 553, "EPD_Load_LUT", 0x5E, 0x1D),
    (0x1E467, 555, "SPI_COMMAND", 0x5E, 0x19),
    (0x1E73D, 558, "SPI_DATA", 0x5E, 0x16),
)

EXPECTED_EPD_LOAD_LUT_DIRECT_CALLS = (
    (0x1B4F5, 465, "SPI_COMMAND", 0x5E, 0x19),
    (0x1B7C0, 468, "SPI_DATA", 0x5E, 0x16),
)


class ProofError(ValueError):
    """Raised when the pinned object or an observed record changes."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _hex(value: int) -> str:
    return f"0x{value:X}"


def _section_marker(section_id: int) -> bytes:
    return bytes((0xC7, section_id, 0, 0, 0, 0))


def _find_all(
    payload: bytes, needle: bytes, *, start: int = 0, end: int | None = None
) -> list[int]:
    limit = len(payload) if end is None else end
    result: list[int] = []
    cursor = start
    while True:
        offset = payload.find(needle, cursor, limit)
        if offset < 0:
            return result
        result.append(offset)
        cursor = offset + 1


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProofError(message)


def _assert_bytes_at(payload: bytes, label: str, offset: int, expected: bytes) -> None:
    actual = payload[offset : offset + len(expected)]
    _require(
        actual == expected,
        f"{label} bytes mismatch at {_hex(offset)}: expected {expected.hex()}, got {actual.hex()}",
    )


def _source_records(payload: bytes, *, start: int, end: int) -> list[dict[str, Any]]:
    return [
        {
            "offset": match.start(),
            "file": Path(match.group("file").decode("ascii", "replace")).name,
            "line": int(match.group("line")),
            "source": match.group("source").decode("ascii"),
        }
        for match in SOURCE_RECORD_RE.finditer(payload, start, end)
    ]


def _namespace_1_symbol_records(payload: bytes) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for offset in _find_all(payload, b"\xcd\x00\x00\x00"):
        if offset + 5 > len(payload):
            continue
        record_length = payload[offset + 4]
        body = payload[offset + 5 : offset + 5 + record_length]
        if len(body) < 9 or body[:4] != b"\x01\x00\x00\x00":
            continue
        name_length = body[4]
        if len(body) != 4 + 1 + name_length + 4 or body[-4:] != b"\xff" * 4:
            continue
        raw_name = body[5 : 5 + name_length]
        if not raw_name or any(value < 0x20 or value > 0x7E for value in raw_name):
            continue
        records.append(
            {
                "index": len(records),
                "offset": offset,
                "name": raw_name.decode("ascii"),
            }
        )
    return records


def _direct_call_records(
    payload: bytes, *, start: int, end: int
) -> list[dict[str, Any]]:
    return [
        {
            "record_file_offset": match.start(),
            "source_file": Path(match.group("file").decode("ascii", "replace")).name,
            "source_line": int(match.group("line")),
            "symbol": match.group("symbol").decode("ascii"),
            "operator": match.group("operator")[0],
            "target_id": match.group("target_id")[0],
            "addend": int.from_bytes(match.group("addend"), "little"),
        }
        for match in DIRECT_CALL_RE.finditer(payload, start, end)
    ]


def _assert_direct_call_inventory(
    records: list[dict[str, Any]],
    *,
    label: str,
    expected: tuple[tuple[int, int, str, int, int], ...],
) -> None:
    actual = [
        (
            int(record["record_file_offset"]),
            int(record["source_line"]),
            str(record["symbol"]),
            int(record["operator"]),
            int(record["target_id"]),
        )
        for record in records
    ]
    _require(actual == list(expected), f"{label} direct CALLA inventory changed")
    _require(
        all(record["source_file"] == "E2801.c" for record in records),
        f"{label} direct CALLA source file changed",
    )
    _require(
        all(int(record["addend"]) == 0 for record in records),
        f"{label} direct CALLA addend changed",
    )


def _assert_source_record(
    records: list[dict[str, Any]],
    *,
    label: str,
    line: int,
    source: str,
    offsets: list[int],
) -> None:
    found = [
        int(record["offset"])
        for record in records
        if record["file"] == "E2801.c"
        and record["line"] == line
        and record["source"] == source
    ]
    _require(
        found == offsets,
        f"{label} source records changed: expected {[_hex(x) for x in offsets]}, "
        f"found {[_hex(x) for x in found]}",
    )


def _extract_tagged_bytes(
    payload: bytes, *, section_id: int, marker_offset: int
) -> tuple[bytes, int]:
    _assert_bytes_at(
        payload,
        f"section 0x{section_id:02X} marker",
        marker_offset,
        _section_marker(section_id),
    )
    cursor = marker_offset + 6
    decoded = bytearray()
    while cursor + 1 < len(payload) and payload[cursor] == 0x36:
        decoded.append(payload[cursor + 1])
        cursor += 2
    return bytes(decoded), cursor


def _prove_sections(payload: bytes) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for name, item in FUNCTION_SECTIONS.items():
        marker = int(item["marker_offset"])
        end = int(item["encoded_end_offset"])
        section_id = int(item["section_id"])
        next_id = int(item["next_section_id"])
        _assert_bytes_at(payload, f"{name} marker", marker, _section_marker(section_id))
        _assert_bytes_at(payload, f"{name} next marker", end, _section_marker(next_id))
        report[name] = {
            "section_id": f"0x{section_id:02X}",
            "marker_file_offset": _hex(marker),
            "encoded_end_file_offset": _hex(end),
            "next_section_id": f"0x{next_id:02X}",
            "range_kind": "UBROF file-record range, not linked code address",
        }
    return report


def _prove_arrays(payload: bytes) -> dict[str, Any]:
    arrays: dict[str, Any] = {}
    symbol_records = _namespace_1_symbol_records(payload)
    for name, item in TAGGED_ARRAYS.items():
        name_evidence = NAMESPACE_1_SYMBOL_EVIDENCE[name]
        name_index = int(name_evidence["index"])
        _require(name_index < len(symbol_records), f"{name} name index is missing")
        name_record = symbol_records[name_index]
        _require(name_record["name"] == name, f"{name} namespace name changed")
        _require(
            name_record["offset"] == name_evidence["record_offset"],
            f"{name} namespace name-record offset changed",
        )
        decoded, end = _extract_tagged_bytes(
            payload,
            section_id=int(item["section_id"]),
            marker_offset=int(item["marker_offset"]),
        )
        digest = _sha256(decoded)
        _require(len(decoded) == item["decoded_length"], f"{name} length changed")
        _require(digest == item["decoded_sha256"], f"{name} digest changed")
        _require(end == item["encoded_end_offset"], f"{name} encoded end changed")
        _assert_bytes_at(
            payload,
            f"{name} next marker",
            end,
            _section_marker(int(item["next_section_id"])),
        )
        arrays[name] = {
            "section_id": f"0x{int(item['section_id']):02X}",
            "decoded_bytes": len(decoded),
            "decoded_sha256": digest,
            "raw_bytes_emitted": False,
            "report_key_is_candidate_symbol_label": True,
            "namespace_1_name_record": {
                "index": name_index,
                "file_offset": _hex(int(name_record["offset"])),
            },
            "symbol_name_to_section_binding_proven": False,
            "link_to_runtime_dataBuff_upload_proven": False,
            "standalone_E2802_content_comparison_performed": False,
        }
    return arrays


def _prove_upload(payload: bytes) -> dict[str, Any]:
    upload = FUNCTION_SECTIONS["Upload_Temperature_LUT"]
    start = int(upload["marker_offset"])
    end = int(upload["encoded_end_offset"])
    records = _source_records(payload, start=start, end=end)
    load_lut = FUNCTION_SECTIONS["EPD_Load_LUT"]
    load_lut_start = int(load_lut["marker_offset"])
    load_lut_end = int(load_lut["encoded_end_offset"])
    load_lut_records = _source_records(payload, start=load_lut_start, end=load_lut_end)
    upload_direct_calls = _direct_call_records(payload, start=start, end=end)
    load_lut_direct_calls = _direct_call_records(
        payload, start=load_lut_start, end=load_lut_end
    )
    _assert_direct_call_inventory(
        upload_direct_calls,
        label="Upload_Temperature_LUT",
        expected=EXPECTED_UPLOAD_DIRECT_CALLS,
    )
    _assert_direct_call_inventory(
        load_lut_direct_calls,
        label="EPD_Load_LUT",
        expected=EXPECTED_EPD_LOAD_LUT_DIRECT_CALLS,
    )

    symbol_records = _namespace_1_symbol_records(payload)
    read_data_name = NAMESPACE_1_SYMBOL_EVIDENCE["ReadData"]
    read_data_index = int(read_data_name["index"])
    _require(read_data_index < len(symbol_records), "ReadData name index is missing")
    read_data_name_record = symbol_records[read_data_index]
    _require(
        read_data_name_record["name"] == "ReadData",
        "external symbol index 0x03 is no longer paired with ReadData",
    )
    _require(
        read_data_name_record["offset"] == read_data_name["record_offset"],
        "ReadData namespace name-record offset changed",
    )

    command_name_report: dict[str, Any] = {}
    for name, item in COMMAND_ENUM_ANCHORS.items():
        value = int(item["value"])
        anchor = (
            b"N"
            + bytes((len(name),))
            + name.encode("ascii")
            + bytes((0, 4))
            + f"0x{value:02X}".encode("ascii")
        )
        offset = int(item["offset"])
        _assert_bytes_at(payload, f"{name} command enum", offset, anchor)
        _require(
            _find_all(payload, anchor) == [offset],
            f"{name} command enum occurrence inventory changed",
        )
        command_name_report[name] = {
            "value": f"0x{value:02X}",
            "file_offset": _hex(offset),
            "evidence": "identity-pinned embedded enum record",
        }

    _assert_bytes_at(
        payload,
        "dataBuff backing-section start",
        int(DATABUFF_STORAGE["start_marker_offset"]),
        _section_marker(int(DATABUFF_STORAGE["section_id"])),
    )
    _assert_bytes_at(
        payload,
        "dataBuff backing-section end",
        int(DATABUFF_STORAGE["end_marker_offset"]),
        bytes.fromhex("c70e00000a00"),
    )
    _assert_bytes_at(
        payload,
        "two-byte ReadData ABI setup and external call",
        int(READ_DATA_TWO_BYTE["argument_setup_and_call_offset"]),
        bytes.fromhex(str(READ_DATA_TWO_BYTE["argument_setup_and_call_bytes"])),
    )
    two_byte_source = READ_DATA_TWO_BYTE["source_record"]
    _assert_source_record(
        records,
        label="two-byte ReadData call",
        line=int(two_byte_source["line"]),
        source=str(two_byte_source["source"]),
        offsets=list(two_byte_source["offsets"]),
    )
    _assert_bytes_at(
        payload,
        "2508-byte read setup",
        int(READ_DATA_2508["argument_setup_offset"]),
        bytes.fromhex(str(READ_DATA_2508["argument_setup_bytes"])),
    )
    _assert_bytes_at(
        payload,
        "2508-byte read address and call",
        int(READ_DATA_2508["address_and_call_offset"]),
        bytes.fromhex(str(READ_DATA_2508["address_and_call_bytes"])),
    )
    for label, item in READ_DATA_2508["source_records"].items():
        _assert_source_record(
            records,
            label=f"ReadData {label}",
            line=int(item["line"]),
            source=str(item["source"]),
            offsets=list(item["offsets"]),
        )
    for label, item in UPLOAD_SOURCE_RECORDS.items():
        _assert_source_record(
            records,
            label=label,
            line=int(item["line"]),
            source=str(item["source"]),
            offsets=list(item["offsets"]),
        )
    for label, item in EPD_LOAD_LUT_SOURCE_RECORDS.items():
        _assert_source_record(
            load_lut_records,
            label=f"EPD_Load_LUT {label}",
            line=int(item["line"]),
            source=str(item["source"]),
            offsets=list(item["offsets"]),
        )

    signature_report: dict[str, Any] = {}
    for label, item in UPLOAD_SIGNATURES.items():
        signature = bytes.fromhex(str(item["bytes"]))
        offset = int(item["offset"])
        _assert_bytes_at(payload, label, offset, signature)
        occurrences = _find_all(payload, signature, start=start, end=end)
        expected_occurrences = list(item.get("expected_occurrences", [offset]))
        _require(
            occurrences == expected_occurrences,
            f"{label} occurrence inventory changed inside Upload_Temperature_LUT",
        )
        signature_report[label] = {
            "file_offset": _hex(offset),
            "occurrences_in_upload_function": len(occurrences),
            "branch_specific_offset_is_pinned": True,
        }
    load_lut_signature_report: dict[str, Any] = {}
    for label, item in EPD_LOAD_LUT_SIGNATURES.items():
        signature = bytes.fromhex(str(item["bytes"]))
        offset = int(item["offset"])
        _assert_bytes_at(payload, label, offset, signature)
        _require(
            _find_all(payload, signature, start=load_lut_start, end=load_lut_end)
            == [offset],
            f"EPD_Load_LUT {label} occurrence inventory changed",
        )
        load_lut_signature_report[label] = {
            "file_offset": _hex(offset),
            "occurrences_in_EPD_Load_LUT": 1,
        }

    command_lines = [
        int(record["line"])
        for record in records
        if record["source"] == "CALLA   #SPI_COMMANDs"
    ]
    _require(
        command_lines == [498, 498, 522, 522, 527, 527, 555, 555],
        "direct SPI_COMMAND source-record inventory changed",
    )
    checked_named_helpers = {
        "EPD_Init": "#EPD_Inits",
        "reset": "#resets",
        "setPON": "#setPONs",
        "setPOF": "#setPOFs",
        "EPD_Sleep": "#EPD_Sleeps",
    }
    named_helper_counts = {
        name: sum(token in str(record["source"]) for record in records)
        for name, token in checked_named_helpers.items()
    }
    _require(
        not any(named_helper_counts.values()),
        f"observed named helper calls changed: {named_helper_counts}",
    )

    direct_command_values = (0x40, 0x00, 0x00, 0x21)
    checked_absent_direct_commands = {
        "PWR": 0x01,
        "PLL": 0x30,
        "E9": 0xE9,
        "PON": 0x04,
        "DRF": 0x12,
        "POF": 0x02,
    }
    observed_checked_values = sorted(
        set(direct_command_values) & set(checked_absent_direct_commands.values())
    )
    _require(
        not observed_checked_values,
        "checked direct SPI_COMMAND value unexpectedly appeared",
    )

    direct_call_report = [
        {
            "record_file_offset": _hex(int(record["record_file_offset"])),
            "source_line": int(record["source_line"]),
            "symbol": str(record["symbol"]),
            "relocation_operator": f"0x{int(record['operator']):02X}",
            "target_id": f"0x{int(record['target_id']):02X}",
            "relocation_classification": (
                "external-index"
                if int(record["operator"]) == 0x5D
                else "local-section-relative"
            ),
        }
        for record in upload_direct_calls
    ]

    return {
        "function_section_id": "0x1E",
        "command_enum_anchors": command_name_report,
        "source_annotated_named_direct_CALLA_inventory": direct_call_report,
        "preload": {
            "temperature_sequence": [
                "SPI_COMMAND(0x40)",
                "check_busy_high",
                "SPI_GET_DATA",
            ],
            "temperature_command_name_from_embedded_enum": "TSC",
            "ReadData_ABI": {
                "argument_order": ["address", "destination", "count"],
                "register_assignment": {
                    "address": "R12:R13 (copied from R7:R6)",
                    "destination": "R14",
                    "count": "R15",
                },
                "evidence": (
                    "both line-509 and line-518 call setups plus paired "
                    "0x5D external relocations"
                ),
            },
            "observed_ReadData_calls": [
                {
                    "source_line": 509,
                    "operation": "ReadData(address, stack_destination, 2)",
                    "count": 2,
                    "argument_setup_file_offset": "0x1C959",
                    "paired_CALLA_record_file_offset": "0x1C9E0",
                    "source_relocation_record_file_offsets": ["0x1C9E0", "0x1CAC3"],
                },
                {
                    "source_line": 518,
                    "operation": "ReadData(selected_address, dataBuff, 2508)",
                    "count": 2_508,
                    "argument_setup_file_offset": "0x1D20B",
                    "address_and_call_file_offset": "0x1D2F7",
                    "paired_CALLA_record_file_offset": "0x1D378",
                    "source_relocation_record_file_offsets": ["0x1D378", "0x1D45B"],
                },
            ],
            "bulk_read": {
                "operation": "ReadData(selected_address, dataBuff, 2508)",
                "count_hex": "0x09CC",
                "count_bytes": 2_508,
                "destination": {
                    "symbol": "dataBuff",
                    "section_id": "0x0E",
                    "section_offset": 0,
                    "backing_section_extent_bytes": int(
                        DATABUFF_STORAGE["section_extent_bytes"]
                    ),
                    "symbol_capacity_bytes_proven": False,
                },
                "reader_relocation_classification": "external-index",
                "reader_external_symbol_index": "0x03",
                "reader_name_evidence": {
                    "paired_debug_source_symbol": "ReadData",
                    "namespace_1_name_index": read_data_index,
                    "namespace_1_name_record_file_offset": _hex(
                        int(read_data_name_record["offset"])
                    ),
                },
                "reader_external_index_is_local_section_id": False,
                "reader_definition_present_in_this_object": False,
                "physical_transport_proven": False,
            },
            "PSR_V_mode_branch": {
                "command": "0x00",
                "if_V_mode_equals_1": "dataBuff[2] | 0x20",
                "otherwise": "dataBuff[2] & 0xDF",
                "PSR_is_inside_Upload_Temperature_LUT": True,
                "control_flow": {
                    "compare_source_record_file_offset": "0x1D52E",
                    "not_equal_branch_source_record_file_offset": "0x1D5E3",
                    "mode_1_join_jump_source_record_file_offset": "0x1DB82",
                    "mutually_exclusive_paths_and_join_proven": True,
                },
                "legacy_bit_0x20_is_SPD1657_3bit_proof": False,
            },
        },
        "lut0": {
            "command": "0x20",
            "source": "dataBuff + 4",
            "count_hex": "0x031F",
            "count_bytes": 799,
            "callee_section_id": "0x1D",
            "callee_count_contract": (
                "R13 source and R14 count are copied into the helper loop; "
                "one SPI_DATA call occurs per unsigned counter iteration"
            ),
            "callee_argument_registers": {
                "command": "R12=0x20",
                "source": "R13=dataBuff+4 -> R10",
                "count": "R14=0x031F -> R11",
                "loop_counter": "R8 starts at 0",
            },
            "callee_loop_proven": True,
        },
        "lut1": {
            "command": "0x21",
            "value": "0xFF",
            "count_hex": "0x02C0",
            "count_bytes": 704,
            "command_callee_section_id": "0x19",
            "data_callee_section_id": "0x16",
            "loop_control_flow": {
                "pretest_jump_source_record_file_offset": "0x1E604",
                "less_than_backedge_source_record_file_offset": "0x1E8DB",
                "counter_clear_and_pretest_jump_proven": True,
                "increment_compare_0x02C0_and_backedge_proven": True,
                "exact_iteration_count_proven": True,
            },
        },
        "effective_command_order": [
            {"command": "0x40", "dispatch": "direct SPI_COMMAND"},
            {
                "command": "0x00",
                "dispatch": "direct SPI_COMMAND",
                "source_paths": 2,
                "executions_per_invocation": 1,
            },
            {"command": "0x20", "dispatch": "EPD_Load_LUT helper"},
            {"command": "0x21", "dispatch": "direct SPI_COMMAND"},
        ],
        "source_annotated_named_direct_SPI_COMMAND_values": [
            f"0x{value:02X}" for value in direct_command_values
        ],
        "source_annotated_named_direct_PSR_observed": True,
        "negative_direct_command_observation": {
            "checked_command_values": {
                name: f"0x{value:02X}"
                for name, value in checked_absent_direct_commands.items()
            },
            "observed_checked_values": [
                f"0x{value:02X}" for value in observed_checked_values
            ],
            "scope": (
                "complete source-annotated named direct SPI_COMMAND CALLA "
                "inventory inside pinned section 0x1E"
            ),
            "indirect_unannotated_or_cross_object_paths_ruled_out": False,
        },
        "observed_named_helper_call_anchor_counts": named_helper_counts,
        "pinned_ubrof_signatures": signature_report,
        "EPD_Load_LUT_pinned_loop_signatures": load_lut_signature_report,
    }


def _prove_direct_callers(payload: bytes) -> dict[str, Any]:
    for name, (
        section_id,
        marker,
        end,
        next_section_id,
        branch_label_count,
    ) in DISPLAY_SECTIONS.items():
        _assert_bytes_at(
            payload, f"{name} section marker", marker, _section_marker(section_id)
        )
        _assert_bytes_at(
            payload,
            f"{name} next section marker",
            end,
            _section_marker(next_section_id),
        )
        _require(marker < end, f"{name} section range is invalid")
        branch_label_anchor = b"??" + name.encode("ascii") + b"_"
        _require(
            len(_find_all(payload, branch_label_anchor, start=marker, end=end))
            == branch_label_count,
            f"{name} branch-label anchor inventory changed",
        )

    observed = [
        record
        for record in _direct_call_records(payload, start=0, end=len(payload))
        if record["symbol"] == "Upload_Temperature_LUT"
    ]

    expected = [
        {
            "record_file_offset": source_offsets[0],
            "source_file": "E2801.c",
            "source_line": line,
            "symbol": "Upload_Temperature_LUT",
            "operator": 0x5E,
            "target_id": 0x1E,
            "addend": 0,
        }
        for _name, _section, line, source_offsets in DISPLAY_CALLERS
    ]
    _require(observed == expected, "direct Upload_Temperature_LUT callers changed")
    all_upload_source_records = [
        int(record["offset"])
        for record in _source_records(payload, start=0, end=len(payload))
        if record["file"] == "E2801.c"
        and record["source"] == "CALLA   #Upload_Temperature_LUTs"
    ]
    expected_source_records = [
        offset
        for _name, _section, _line, offsets in DISPLAY_CALLERS
        for offset in offsets
    ]
    _require(
        all_upload_source_records == expected_source_records,
        "Upload_Temperature_LUT source-record inventory changed",
    )
    for name, section_id, _line, source_offsets in DISPLAY_CALLERS:
        (
            expected_section,
            marker,
            end,
            _next_section_id,
            _branch_label_count,
        ) = DISPLAY_SECTIONS[name]
        _require(expected_section == section_id, f"{name} section ID differs")
        _require(
            all(marker <= offset < end for offset in source_offsets),
            f"{name} call records are outside its section",
        )

    init = FUNCTION_SECTIONS["EPD_Init"]
    upload = FUNCTION_SECTIONS["Upload_Temperature_LUT"]
    init_records = _source_records(
        payload,
        start=int(init["marker_offset"]),
        end=int(init["encoded_end_offset"]),
    )
    upload_records = _source_records(
        payload,
        start=int(upload["marker_offset"]),
        end=int(upload["encoded_end_offset"]),
    )
    _require(
        not any(
            "#Upload_Temperature_LUTs" in str(row["source"]) for row in init_records
        ),
        "EPD_Init gained a direct upload call",
    )
    _require(
        not any("#EPD_Inits" in str(row["source"]) for row in upload_records),
        "Upload_Temperature_LUT gained a direct init call",
    )
    _require(
        not _find_all(
            payload,
            bytes((0x5E, int(upload["section_id"]))),
            start=int(init["marker_offset"]),
            end=int(init["encoded_end_offset"]),
        ),
        "EPD_Init gained a local relocation to Upload_Temperature_LUT",
    )
    _require(
        not _find_all(
            payload,
            bytes((0x5E, int(init["section_id"]))),
            start=int(upload["marker_offset"]),
            end=int(upload["encoded_end_offset"]),
        ),
        "Upload_Temperature_LUT gained a local relocation to EPD_Init",
    )

    callers = [
        {
            "function": name,
            "caller_section_id": f"0x{section_id:02X}",
            "section_marker_file_offset": _hex(DISPLAY_SECTIONS[name][1]),
            "section_end_file_offset": _hex(DISPLAY_SECTIONS[name][2]),
            "source_line": line,
            "paired_CALLA_record_file_offset": _hex(source_offsets[0]),
            "source_relocation_record_file_offsets": [
                _hex(offset) for offset in source_offsets
            ],
            "target_section_id": "0x1E",
            "relocation_classification": "local-section-relative",
            "all_call_records_within_caller_section": True,
            "function_name_branch_label_anchor_count": DISPLAY_SECTIONS[name][4],
        }
        for name, section_id, line, source_offsets in DISPLAY_CALLERS
    ]
    return {
        "evidence_kind": "paired CALLA debug-source and observed 0x5E relocation",
        "direct_display_caller_count": len(callers),
        "paired_CALLA_record_count": len(observed),
        "source_relocation_record_count": len(all_upload_source_records),
        "source_relocation_records_per_logical_CALLA": 2,
        "direct_display_callers": callers,
        "negative_edge_observation": {
            "EPD_Init_to_Upload": {
                "source_annotated_named_direct_CALLA_observed": False,
                "local_section_relocation_observed": False,
            },
            "Upload_to_EPD_Init": {
                "source_annotated_named_direct_CALLA_observed": False,
                "local_section_relocation_observed": False,
            },
            "scope": "direct named/local-relocation evidence in the two pinned sections",
            "indirect_or_cross_object_paths_ruled_out": False,
        },
        "init_before_upload_order_proven": False,
        "PUBLIC_or_EXTERN_table_resolved": False,
    }


def prove_object(path: Path = DEFAULT_OBJECT_PATH) -> dict[str, Any]:
    """Validate *path* and return metadata-only evidence."""

    if not path.is_file():
        raise ProofError(f"required object is missing: {path}")
    payload = path.read_bytes()
    digest = _sha256(payload)
    _require(
        len(payload) == EXPECTED_OBJECT_SIZE,
        f"object size mismatch: expected {EXPECTED_OBJECT_SIZE}, got {len(payload)}",
    )
    _require(
        digest == EXPECTED_OBJECT_SHA256,
        f"object SHA-256 mismatch: expected {EXPECTED_OBJECT_SHA256}, got {digest}",
    )
    _require(payload[:2] == b"\x01\x0a", "UBROF10 identity marker changed")

    sections = _prove_sections(payload)
    arrays = _prove_arrays(payload)
    upload = _prove_upload(payload)
    callers = _prove_direct_callers(payload)

    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": "legacy_2020_iar_e2801_object_only",
        "safety": {
            "offline_read_only": True,
            "hardware_accessed": False,
            "serial_or_COM_accessed": False,
            "device_network_accessed": False,
            "firmware_written_or_flashed": False,
            "visible_refresh_requested": False,
            "raw_LUT_or_waveform_emitted": False,
            "live_approved": False,
        },
        "object": {
            "relative_path": OBJECT_RELATIVE_PATH.as_posix(),
            "size_bytes": len(payload),
            "sha256": digest,
            "UBROF_version_byte": 10,
            "compiler": "IAR MSP430 5.30.1.20284",
            "target": "430X",
            "embedded_source": (
                "D:/E2801/Firmware_BX/20200527_E2801_BX_V0_0_1 - "
                "OTP Test - VDG_HDG - 34pin/E2801.c"
            ),
        },
        "function_sections": sections,
        "tagged_arrays": arrays,
        "upload_temperature_lut": upload,
        "direct_call_graph": callers,
        "adjudication": {
            "legacy_runtime_upload_geometry": "R20/799(dataBuff+4) then R21/704(0xFF)",
            "PSR_placement": "inside Upload_Temperature_LUT before R20/R21",
            "standalone_E2802_comparison_performed": False,
            "cross_object_or_cross_version_corroboration_claimed": False,
            "current_SPD1657_ABI_proven": False,
            "dual_controller_loading_proven": False,
            "runtime_to_factory_OTP_recovery_proven": False,
            "safe_live_panel_sequence_derivable": False,
        },
        "not_proven": [
            "SPD1657 command or payload ABI",
            "current STM32 535/704 or 800-byte runtime profile contract",
            "a root caller that establishes EPD_Init before LUT upload",
            "which physical storage or transport supplies ReadData",
            "that the full 0x0A00 backing-section extent is dataBuff symbol capacity",
            "a decoded symbol-definition binding DATA0/DATA1 names to sections 0x14/0x15",
            "that tagged DATA0/DATA1 are selected by this runtime upload",
            "an E2802 comparison performed by this standalone proof",
            "dual-controller loading, cold reset, or factory-OTP recovery",
        ],
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--object", type=Path, default=DEFAULT_OBJECT_PATH)
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = prove_object(args.object)
    except (OSError, ProofError) as error:
        print(f"E2801 r43 proof failed: {error}", file=sys.stderr)
        return 2
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    json.dump(
        report,
        sys.stdout,
        ensure_ascii=False,
        indent=None if args.compact else 2,
        sort_keys=True,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
