#!/usr/bin/env python3
"""Reproduce the legacy E2802.r43 LUT evidence without touching hardware.

This helper is intentionally identity-pinned.  File offsets and IAR UBROF
record signatures are meaningful only after the complete object size and
SHA-256 have matched.  The result corroborates the legacy 2020 E2802 object;
it is not evidence for an SPD1657 ABI or for safe live-panel execution.
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
    "E6_73_sample code_V1.2_20250116/Debug/Obj/E2802.r43"
)
DEFAULT_OBJECT_PATH = REPO_ROOT / OBJECT_RELATIVE_PATH

EXPECTED_OBJECT_SIZE = 328_062
EXPECTED_OBJECT_SHA256 = (
    "19fb74c05444880ea6a403d697307e47a874998b5529ee84dd0592ecae16c9ce"
)

SCHEMA_VERSION = 3

# These are UBROF file ranges, not linked target addresses.  The object is
# relocatable and interleaves machine-code records with source/debug records.
FUNCTION_SECTIONS = {
    "EPD_Init": {
        "section_id": 0x2D,
        "marker_offset": 0x764E,
        "encoded_end_offset": 0x15DCE,
        "next_section_id": 0x2C,
    },
    "Upload_Temperature_LUT": {
        "section_id": 0x1E,
        "marker_offset": 0x16B80,
        "encoded_end_offset": 0x187B3,
        "next_section_id": 0x2A,
    },
}

# ``dataBuff`` resolves to section 0x0E at offset zero.  The second marker
# carries the section-relative end offset 0x0A00 in UBROF's encoded field, so
# 2560 bytes is the extent of the backing section, not a proven symbol-size or
# capacity claim for ``dataBuff``.  Keeping the exact encoded bytes here avoids
# pretending that this helper is a general UBROF parser.
DATABUFF_STORAGE = {
    "section_id": 0x0E,
    "start_marker_offset": 0x535E,
    "start_marker_bytes": "c70e00000000",
    "end_marker_offset": 0x536B,
    "end_marker_bytes": "c70e00000a00",
    "backing_section_extent_bytes": 0x0A00,
}

READ_DATA_2508 = {
    "argument_setup_offset": 0x17BE6,
    "argument_setup_bytes": "373f4037cc09373e405e0e00000000",
    "address_and_call_offset": 0x17CC9,
    "address_and_call_bytes": "370d46374c475d0300000000",
    "source_records": {
        "destination_dataBuff": {
            "line": 397,
            "source": "MOV.W   #dataBuff, R14s",
            "offsets": [0x17C41],
        },
        "ReadData_call": {
            "line": 397,
            "source": "CALLA   #ReadDatas",
            "offsets": [0x17D4A, 0x17E24],
        },
    },
    "count_hex": 0x09CC,
    "count_bytes": 2_508,
    "destination_section_id": 0x0E,
    "destination_offset": 0,
    "reader_relocation_operator": 0x5D,
    "reader_external_symbol_index": 0x03,
    "reader_relocation_addend": 0,
}

PSR_BRANCH = {
    "mode_source_records": {
        "line": 107,
        "source": "MOV.B   &dataBuff + 14, &V_modes",
        "offsets": [0xAFB3, 0xB088],
    },
    "command_call_offsets": [0xB463, 0xBC6B],
    "mode_1_transform": {
        "offset": 0xB715,
        "bytes": "377cd03720005e1600000000",
        "expression": "dataBuff[16] | 0x20",
    },
    "other_mode_transform": {
        "offset": 0xBF1D,
        "bytes": "377cf037df005e1600000000",
        "expression": "dataBuff[16] & 0xDF",
    },
    "second_parameter": "dataBuff[17]",
}

PLL_BRANCH = {
    "mode_source_records": {
        "line": 108,
        "source": "MOV.B   &dataBuff + 15, &Dyna_PLLs",
        "offsets": [0xB160, 0xB237],
    },
    "command_call_offsets": [0xFECF, 0x1042B],
    "mode_1_transform": {
        "offset": 0x10181,
        "bytes": "377cd25e1600000000",
        "expression": "dataBuff[42] | 0x08",
    },
    "other_mode_transform": {
        "offset": 0x106DD,
        "bytes": "377cf037f7005e1600000000",
        "expression": "dataBuff[42] & 0xF7",
    },
}

# Command literals are immediately followed by a relocation to section 0x19,
# the local SPI_COMMAND import.  ``call_offsets`` point at that relocation.
INIT_COMMANDS = (
    {
        "name": "CMDH",
        "command": 0xAA,
        "call_offsets": [0x8283],
        "parameters": ["0x49", "0x55", "0x20", "0x08", "0x09", "0x18"],
        "condition": "always",
    },
    {
        "name": "PWR",
        "command": 0x01,
        "call_offsets": [0x9D88],
        "parameters": "dataBuff[18:24]",
        "condition": "always",
    },
    {
        "name": "PSR",
        "command": 0x00,
        "call_offsets": [0xB463, 0xBC6B],
        "parameters": "V_mode branch over dataBuff[16], then dataBuff[17]",
        "condition": "one of two V_mode branches",
    },
    {
        "name": "POFS",
        "command": 0x03,
        "call_offsets": [0xC3AE],
        "parameters": "dataBuff[24:28]",
        "condition": "always",
    },
    {
        "name": "BTST1",
        "command": 0x05,
        "call_offsets": [0xD042],
        "parameters": "dataBuff[28:32]",
        "condition": "always",
    },
    {
        "name": "BTST2",
        "command": 0x06,
        "call_offsets": [0xDCD6],
        "parameters": "dataBuff[32:36]",
        "condition": "always",
    },
    {
        "name": "BTST3",
        "command": 0x08,
        "call_offsets": [0xE967],
        "parameters": "dataBuff[36:40]",
        "condition": "always",
    },
    {
        "name": "IPC",
        "command": 0x13,
        "call_offsets": [0xF5FB],
        "parameters": "dataBuff[40:42]",
        "condition": "always",
    },
    {
        "name": "PLL",
        "command": 0x30,
        "call_offsets": [0xFECF, 0x1042B],
        "parameters": "Dyna_PLL branch over dataBuff[42]",
        "condition": "one of two Dyna_PLL branches",
    },
    {
        "name": "TSE",
        "command": 0x41,
        "call_offsets": [0x108C2],
        "parameters": "dataBuff[43]",
        "condition": "always",
    },
    {
        "name": "CDI",
        "command": 0x50,
        "call_offsets": [0x10D52],
        "parameters": "dataBuff[44]",
        "condition": "always",
    },
    {
        "name": "TCON",
        "command": 0x60,
        "call_offsets": [0x111E2],
        "parameters": "dataBuff[45:47]",
        "condition": "always",
    },
    {
        "name": "TRES",
        "command": 0x61,
        "call_offsets": [0x1191E],
        "parameters": "dataBuff[47:51]",
        "condition": "always",
    },
    {
        "name": "PON",
        "command": 0x04,
        "call_offsets": [0x12A76],
        "parameters": [],
        "condition": "SWITCH_FUNCTION in {0x10, 0x11, 0x12}",
    },
    {
        "name": "AMV",
        "command": 0x80,
        "call_offsets": [0x12E40],
        "parameters": "dataBuff[51:53]",
        "condition": "SWITCH_FUNCTION in {0x10, 0x11, 0x12}",
    },
    {
        "name": "POF",
        "command": 0x02,
        "call_offsets": [0x1375F],
        "parameters": ["0x00"],
        "condition": "SWITCH_FUNCTION in {0x10, 0x11, 0x12}",
    },
    {
        "name": "VV",
        "command": 0x81,
        "call_offsets": [0x13D04],
        "parameters": "SPI_GET_DATA -> dataBuff[53]",
        "condition": "SWITCH_FUNCTION in {0x10, 0x11, 0x12}",
    },
    {
        "name": "VDCS",
        "command": 0x82,
        "call_offsets": [0x1419D],
        "parameters": "dataBuff[53]",
        "condition": "SWITCH_FUNCTION in {0x10, 0x11, 0x12}",
    },
    {
        "name": "T_VDCS",
        "command": 0x84,
        "call_offsets": [0x1462D],
        "parameters": "dataBuff[54]",
        "condition": "SWITCH_FUNCTION in {0x10, 0x11, 0x12}",
    },
    {
        "name": "AGID",
        "command": 0x86,
        "call_offsets": [0x14ABD],
        "parameters": "dataBuff[55]",
        "condition": "SWITCH_FUNCTION in {0x10, 0x11, 0x12}",
    },
    {
        "name": "PWS",
        "command": 0xE3,
        "call_offsets": [0x14F4D],
        "parameters": "dataBuff[56]",
        "condition": "SWITCH_FUNCTION in {0x10, 0x11, 0x12}",
    },
    {
        "name": "CCSET",
        "command": 0xE0,
        "call_offsets": [0x153DD],
        "parameters": "dataBuff[57]",
        "condition": "SWITCH_FUNCTION in {0x10, 0x11, 0x12}",
    },
    {
        "name": "TSSET",
        "command": 0xE6,
        "call_offsets": [0x1586D],
        "parameters": "dataBuff[58]",
        "condition": "SWITCH_FUNCTION in {0x10, 0x11, 0x12}",
    },
)

FIXED_CMDH_PARAMETERS = (
    (0x49, 0x845F),
    (0x55, 0x863B),
    (0x20, 0x8817),
    (0x08, 0x89F3),
    (0x09, 0x8BCC),
    (0x18, 0x8DA8),
)


def _flow_command(name: str, command: int, line: int, offset: int) -> dict[str, Any]:
    return {
        "op": "SPI_COMMAND",
        "name": name,
        "command": command,
        "source_line": line,
        "signature_offset": offset,
    }


def _flow_data(value: int, line: int, offset: int) -> dict[str, Any]:
    return {
        "op": "SPI_DATA",
        "value": value,
        "source_line": line,
        "signature_offset": offset,
    }


def _flow_upload(line: int) -> dict[str, Any]:
    return {"op": "Upload_Temperature_LUT", "source_line": line}


def _flow_busy(line: int) -> dict[str, Any]:
    return {"op": "busy_wait_high", "source_line": line}


# Every source-level CALLA is represented by two IAR relocation/debug records.
# The ordered flows below retain one logical operation per pair.
DISPLAY_CALLERS = (
    {
        "function": "EPD_Display_White",
        "section_id": 0x26,
        "marker_offset": 0x3C3F3,
        "encoded_end_offset": 0x3E4BF,
        "next_section_id": 0x25,
        "upload_record_offsets": [0x3C73B, 0x3C824],
        "flow": [
            _flow_upload(1553),
            _flow_command("DTM", 0x10, 1558, 0x3C8B6),
            _flow_command("PON", 0x04, 1589, 0x3D59A),
            _flow_busy(1590),
            _flow_command("DRF", 0x12, 1593, 0x3D965),
            _flow_data(0x00, 1594, 0x3DB4B),
            _flow_busy(1595),
            _flow_command("POF", 0x02, 1598, 0x3DF10),
            _flow_data(0x00, 1599, 0x3E0F3),
            _flow_busy(1600),
        ],
    },
    {
        "function": "EPD_Display_Black",
        "section_id": 0x25,
        "marker_offset": 0x3E4BF,
        "encoded_end_offset": 0x4078F,
        "next_section_id": 0x24,
        "upload_record_offsets": [0x3E82B, 0x3E914],
        "flow": [
            _flow_upload(1612),
            _flow_command("DTM", 0x10, 1629, 0x3EA7B),
            _flow_command("DTM", 0x10, 1637, 0x3F17B),
            _flow_command("PON", 0x04, 1651, 0x3F86A),
            _flow_busy(1652),
            _flow_command("DRF", 0x12, 1656, 0x3FC35),
            _flow_data(0x00, 1657, 0x3FE1B),
            _flow_busy(1658),
            _flow_command("POF", 0x02, 1661, 0x401E0),
            _flow_data(0x00, 1662, 0x403C3),
            _flow_busy(1663),
        ],
    },
    {
        "function": "EPD_Display_Yellow",
        "section_id": 0x24,
        "marker_offset": 0x4078F,
        "encoded_end_offset": 0x42A67,
        "next_section_id": 0x23,
        "upload_record_offsets": [0x41D92, 0x41E7B],
        "flow": [
            _flow_command("DTM", 0x10, 1695, 0x40B4F),
            _flow_command("DTM", 0x10, 1703, 0x41256),
            _flow_command("PON", 0x04, 1716, 0x4194C),
            _flow_busy(1717),
            _flow_upload(1719),
            _flow_command("DRF", 0x12, 1721, 0x41F0D),
            _flow_data(0x00, 1722, 0x420F3),
            _flow_busy(1723),
            _flow_command("POF", 0x02, 1726, 0x424B8),
            _flow_data(0x00, 1727, 0x4269B),
            _flow_busy(1728),
        ],
    },
    {
        "function": "EPD_Display_Red",
        "section_id": 0x23,
        "marker_offset": 0x42A67,
        "encoded_end_offset": 0x44D21,
        "next_section_id": 0x22,
        "upload_record_offsets": [0x4404C, 0x44135],
        "flow": [
            _flow_command("DTM", 0x10, 1758, 0x42E24),
            _flow_command("DTM", 0x10, 1766, 0x4351C),
            _flow_command("PON", 0x04, 1774, 0x43C06),
            _flow_busy(1775),
            _flow_upload(1777),
            _flow_command("DRF", 0x12, 1779, 0x441C7),
            _flow_data(0x00, 1780, 0x443AD),
            _flow_busy(1781),
            _flow_command("POF", 0x02, 1784, 0x44772),
            _flow_data(0x00, 1785, 0x44955),
            _flow_busy(1786),
        ],
    },
    {
        "function": "EPD_Display_line_4bit",
        "section_id": 0x22,
        "marker_offset": 0x44D21,
        "encoded_end_offset": 0x4678C,
        "next_section_id": 0x21,
        "upload_record_offsets": [0x44FEE, 0x450D7],
        "flow": [
            _flow_upload(1799),
            _flow_command("DTM", 0x10, 1813, 0x45169),
            _flow_command("PON", 0x04, 1826, 0x45867),
            _flow_busy(1827),
            _flow_command("DRF", 0x12, 1829, 0x45C32),
            _flow_data(0x00, 1830, 0x45E18),
            _flow_busy(1831),
            _flow_command("POF", 0x02, 1834, 0x461DD),
            _flow_data(0x00, 1835, 0x463C0),
            _flow_busy(1836),
        ],
    },
    {
        "function": "EPD_Display_Dot",
        "section_id": 0x20,
        "marker_offset": 0x46BDD,
        "encoded_end_offset": 0x49101,
        "next_section_id": 0x1F,
        "upload_record_offsets": [0x46F94, 0x4707D],
        "flow": [
            _flow_upload(1859),
            _flow_command("DTM", 0x10, 1861, 0x4710F),
            _flow_command("PON", 0x04, 1890, 0x481DC),
            _flow_busy(1891),
            _flow_command("DRF", 0x12, 1893, 0x485A7),
            _flow_data(0x00, 1894, 0x4878D),
            _flow_busy(1895),
            _flow_command("POF", 0x02, 1897, 0x48B52),
            _flow_data(0x00, 1898, 0x48D35),
            _flow_busy(1899),
        ],
    },
    {
        "function": "EPD_Display_Dot_4bit",
        "section_id": 0x1F,
        "marker_offset": 0x49101,
        "encoded_end_offset": 0x4B66A,
        "next_section_id": 0x19,
        "upload_record_offsets": [0x494BA, 0x495A3],
        "flow": [
            _flow_upload(1914),
            _flow_command("DTM", 0x10, 1916, 0x49635),
            _flow_command("PON", 0x04, 1945, 0x4A745),
            _flow_busy(1946),
            _flow_command("DRF", 0x12, 1948, 0x4AB10),
            _flow_data(0x00, 1949, 0x4ACF6),
            _flow_busy(1950),
            _flow_command("POF", 0x02, 1952, 0x4B0BB),
            _flow_data(0x00, 1953, 0x4B29E),
            _flow_busy(1954),
        ],
    },
)

SOURCE_RECORD_RE = re.compile(
    rb" File: [^\x00\r\n]+E2802\.c, Line: (?P<line>\d+) \n"
    rb" Source: (?P<source>[ -~]+)"
)

# IAR UBROF section-content marker at section-relative offset zero.
DATA_SECTIONS = {
    "DATA0": {
        "section_id": 0x14,
        "marker_offset": 0x53D0,
        "decoded_length": 1_503,
        "decoded_sha256": (
            "eafe51e741f2e0922a2404abcc016473a203e9824bf91fd550f74ee6e05b8bc5"
        ),
        "encoded_end_offset": 0x5F94,
        "next_section_id": 0x15,
    },
    "DATA1": {
        "section_id": 0x15,
        "marker_offset": 0x5F94,
        "decoded_length": 704,
        "decoded_sha256": (
            "6dbd5a232419da637084683867933a7f60ce06d28a5034136d0f0efae3015e6a"
        ),
        "encoded_end_offset": 0x651A,
        "next_section_id": 0x18,
    },
}

# UBROF code records use 0x37 before literal instruction words and 0x5e for
# a section-relative relocation.  These signatures are globally unique in the
# identity-pinned object.  The FF call needs a small record-context prefix
# because MOV.B #-1,R12; CALL SPI_DATA also occurs in another function.
UPLOAD_SIGNATURES = {
    "upload_section_1e": {
        "offset": 0x16B80,
        "bytes": "c71e00000000",
    },
    "lut0_count_031f_and_dataBuff_plus_4": {
        "offset": 0x17EA7,
        "bytes": "373e40371f03373d405e0e00000004",
    },
    "lut0_command_20_and_call_section_1d": {
        "offset": 0x17F8E,
        "bytes": "373c403720005e1d00000000",
    },
    "lut1_command_21_and_call_section_19": {
        "offset": 0x18174,
        "bytes": "377c403721005e1900000000",
    },
    "lut1_loop_counter_clear_and_jump_to_compare": {
        "offset": 0x18358,
        "bytes": "370b435e1e000000ae",
    },
    "lut1_ff_and_call_section_16_context": {
        "offset": 0x18426,
        "bytes": "d00000006ed705b52f050205377c435e1600000000",
        "instruction_offset": 0x18432,
    },
    "lut1_increment_compare_02c0_and_loop_branch": {
        "offset": 0x1860E,
        "bytes": "371b53373b9037c0025e1e000000a6",
    },
}

SOURCE_ANCHORS = {
    "dataBuff_plus_4": {
        "offset": 0x17F60,
        "bytes": b"Source: MOV.W   #dataBuff + 4, R13s",
    },
}


class ProofError(ValueError):
    """Raised when the object does not satisfy the pinned proof contract."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _hex_offset(value: int) -> str:
    return f"0x{value:X}"


def _all_offsets(payload: bytes, needle: bytes) -> list[int]:
    offsets: list[int] = []
    start = 0
    while True:
        offset = payload.find(needle, start)
        if offset < 0:
            return offsets
        offsets.append(offset)
        start = offset + 1


def _section_marker(section_id: int) -> bytes:
    return bytes((0xC7, section_id, 0x00, 0x00, 0x00, 0x00))


def _assert_bytes_at(
    payload: bytes,
    *,
    label: str,
    expected_offset: int,
    signature: bytes,
) -> None:
    actual = payload[expected_offset : expected_offset + len(signature)]
    if actual != signature:
        raise ProofError(
            f"{label} bytes mismatch at {_hex_offset(expected_offset)}: "
            f"expected {signature.hex()}, got {actual.hex()}"
        )


def _assert_offsets(
    payload: bytes,
    *,
    label: str,
    signature: bytes,
    expected_offsets: list[int],
) -> None:
    offsets = _all_offsets(payload, signature)
    if offsets != expected_offsets:
        expected = ", ".join(_hex_offset(offset) for offset in expected_offsets)
        actual = ", ".join(_hex_offset(offset) for offset in offsets) or "none"
        raise ProofError(
            f"{label} offsets mismatch: expected {expected}, found {actual}"
        )


def _source_records(
    payload: bytes,
    *,
    start: int = 0,
    end: int | None = None,
) -> list[dict[str, Any]]:
    limit = len(payload) if end is None else end
    return [
        {
            "file_offset": match.start(),
            "source_line": int(match.group("line")),
            "source": match.group("source").decode("ascii"),
        }
        for match in SOURCE_RECORD_RE.finditer(payload, start, limit)
    ]


def _assert_source_records(
    payload: bytes,
    *,
    label: str,
    line: int,
    source: str,
    expected_offsets: list[int],
    start: int = 0,
    end: int | None = None,
) -> None:
    offsets = [
        int(record["file_offset"])
        for record in _source_records(payload, start=start, end=end)
        if record["source_line"] == line and record["source"] == source
    ]
    if offsets != expected_offsets:
        expected = ", ".join(_hex_offset(offset) for offset in expected_offsets)
        actual = ", ".join(_hex_offset(offset) for offset in offsets) or "none"
        raise ProofError(
            f"{label} source-record offsets mismatch: expected {expected}, "
            f"found {actual}"
        )


def _mov_b_immediate_r12(value: int) -> bytes:
    constant_generator = {
        0x00: bytes.fromhex("374c43"),
        0x01: bytes.fromhex("375c43"),
        0x02: bytes.fromhex("376c43"),
        0x04: bytes.fromhex("376c42"),
        0x08: bytes.fromhex("377c42"),
        0xFF: bytes.fromhex("377c43"),
    }
    if value in constant_generator:
        return constant_generator[value]
    return bytes.fromhex("377c4037") + value.to_bytes(2, "little")


def _assert_immediate_call(
    payload: bytes,
    *,
    label: str,
    value: int,
    call_offset: int,
    target_section_id: int,
) -> None:
    prefix = _mov_b_immediate_r12(value)
    _assert_bytes_at(
        payload,
        label=f"{label} immediate",
        expected_offset=call_offset - len(prefix),
        signature=prefix,
    )
    _assert_bytes_at(
        payload,
        label=f"{label} call relocation",
        expected_offset=call_offset,
        signature=bytes((0x5E, target_section_id, 0x00, 0x00, 0x00, 0x00)),
    )


def extract_tagged_bytes(
    payload: bytes,
    *,
    section_id: int,
    marker_offset: int,
) -> tuple[bytes, int]:
    """Decode consecutive UBROF ``36 <literal-byte>`` records.

    Returns the decoded bytes and the first file offset after the records.
    The caller verifies that the next section marker starts at that offset.
    """

    marker = _section_marker(section_id)
    actual_marker = payload[marker_offset : marker_offset + len(marker)]
    if actual_marker != marker:
        raise ProofError(
            f"section 0x{section_id:02X} marker mismatch at "
            f"{_hex_offset(marker_offset)}"
        )

    cursor = marker_offset + len(marker)
    decoded = bytearray()
    while cursor + 1 < len(payload) and payload[cursor] == 0x36:
        decoded.append(payload[cursor + 1])
        cursor += 2
    return bytes(decoded), cursor


def _assert_unique_at(
    payload: bytes,
    *,
    label: str,
    expected_offset: int,
    signature: bytes,
) -> None:
    offsets = _all_offsets(payload, signature)
    if offsets != [expected_offset]:
        rendered = ", ".join(_hex_offset(offset) for offset in offsets) or "none"
        raise ProofError(
            f"{label} signature offsets mismatch: expected "
            f"{_hex_offset(expected_offset)}, found {rendered}"
        )


def _verify_function_sections(payload: bytes) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, contract in FUNCTION_SECTIONS.items():
        section_id = int(contract["section_id"])
        marker_offset = int(contract["marker_offset"])
        encoded_end = int(contract["encoded_end_offset"])
        next_section_id = int(contract["next_section_id"])
        _assert_bytes_at(
            payload,
            label=f"{name} section marker",
            expected_offset=marker_offset,
            signature=_section_marker(section_id),
        )
        _assert_bytes_at(
            payload,
            label=f"{name} next section marker",
            expected_offset=encoded_end,
            signature=_section_marker(next_section_id),
        )
        result[name] = {
            "section_id": f"0x{section_id:02X}",
            "marker_file_offset": _hex_offset(marker_offset),
            "encoded_end_file_offset": _hex_offset(encoded_end),
            "next_section_id": f"0x{next_section_id:02X}",
            "range_kind": "UBROF file-record range, not linked code address",
        }
    return result


def _prove_read_data(payload: bytes) -> dict[str, Any]:
    _assert_bytes_at(
        payload,
        label="dataBuff start marker",
        expected_offset=int(DATABUFF_STORAGE["start_marker_offset"]),
        signature=bytes.fromhex(str(DATABUFF_STORAGE["start_marker_bytes"])),
    )
    _assert_bytes_at(
        payload,
        label="dataBuff end marker",
        expected_offset=int(DATABUFF_STORAGE["end_marker_offset"]),
        signature=bytes.fromhex(str(DATABUFF_STORAGE["end_marker_bytes"])),
    )
    _assert_unique_at(
        payload,
        label="ReadData 2508-byte argument setup",
        expected_offset=int(READ_DATA_2508["argument_setup_offset"]),
        signature=bytes.fromhex(str(READ_DATA_2508["argument_setup_bytes"])),
    )
    address_and_call_signature = bytes.fromhex(
        str(READ_DATA_2508["address_and_call_bytes"])
    )
    _assert_bytes_at(
        payload,
        label="ReadData selected-address setup and external-index call",
        expected_offset=int(READ_DATA_2508["address_and_call_offset"]),
        signature=address_and_call_signature,
    )
    reader_relocation = bytes(
        (
            int(READ_DATA_2508["reader_relocation_operator"]),
            int(READ_DATA_2508["reader_external_symbol_index"]),
        )
    ) + int(READ_DATA_2508["reader_relocation_addend"]).to_bytes(4, "little")
    reader_relocation_offset = (
        int(READ_DATA_2508["address_and_call_offset"])
        + len(address_and_call_signature)
        - len(reader_relocation)
    )
    _assert_bytes_at(
        payload,
        label="ReadData 0x5D external-index relocation",
        expected_offset=reader_relocation_offset,
        signature=reader_relocation,
    )
    for label, record in READ_DATA_2508["source_records"].items():
        _assert_source_records(
            payload,
            label=f"ReadData {label}",
            line=int(record["line"]),
            source=str(record["source"]),
            expected_offsets=list(record["offsets"]),
            start=int(FUNCTION_SECTIONS["Upload_Temperature_LUT"]["marker_offset"]),
            end=int(FUNCTION_SECTIONS["Upload_Temperature_LUT"]["encoded_end_offset"]),
        )
    return {
        "operation": "ReadData(selected_address, dataBuff, 2508)",
        "count_hex": "0x09CC",
        "count_bytes": int(READ_DATA_2508["count_bytes"]),
        "destination": {
            "symbol": "dataBuff",
            "section_id": "0x0E",
            "section_offset": 0,
            "backing_section_extent_bytes": int(
                DATABUFF_STORAGE["backing_section_extent_bytes"]
            ),
            "dataBuff_symbol_size_proven": False,
            "storage": "uninitialised UBROF section (BSS-like)",
        },
        "address_source": "R6:R7 selected by the preceding temperature table loop",
        "reader": {
            "name_from_source_record": "ReadData",
            "relocation_operator": f"0x{int(READ_DATA_2508['reader_relocation_operator']):02X}",
            "relocation_classification": "external-index",
            "external_symbol_index": f"0x{int(READ_DATA_2508['reader_external_symbol_index']):02X}",
            "relocation_addend": int(READ_DATA_2508["reader_relocation_addend"]),
            "external_index_is_target_section_id": False,
            "index_to_symbol_binding_independently_parsed": False,
            "implementation_location_proven": False,
            "provider_object_proven": False,
            "physical_transport_proven": False,
        },
        "evidence": {
            "argument_setup_file_offset": _hex_offset(
                int(READ_DATA_2508["argument_setup_offset"])
            ),
            "address_and_call_file_offset": _hex_offset(
                int(READ_DATA_2508["address_and_call_offset"])
            ),
            "reader_relocation_file_offset": _hex_offset(reader_relocation_offset),
            "destination_source_record_file_offset": "0x17C41",
            "ReadData_call_record_file_offsets": ["0x17D4A", "0x17E24"],
        },
    }


def _prove_init(payload: bytes) -> dict[str, Any]:
    init_start = int(FUNCTION_SECTIONS["EPD_Init"]["marker_offset"])
    init_end = int(FUNCTION_SECTIONS["EPD_Init"]["encoded_end_offset"])
    init_records = _source_records(payload, start=init_start, end=init_end)
    if any("#ReadDatas" in str(record["source"]) for record in init_records):
        raise ProofError("unexpected bulk ReadData call inside EPD_Init")

    for branch_name, branch in (("PSR", PSR_BRANCH), ("PLL", PLL_BRANCH)):
        mode_record = branch["mode_source_records"]
        _assert_source_records(
            payload,
            label=f"{branch_name} mode load",
            line=int(mode_record["line"]),
            source=str(mode_record["source"]),
            expected_offsets=list(mode_record["offsets"]),
            start=init_start,
            end=init_end,
        )
        for transform_name in ("mode_1_transform", "other_mode_transform"):
            transform = branch[transform_name]
            _assert_unique_at(
                payload,
                label=f"{branch_name} {transform_name}",
                expected_offset=int(transform["offset"]),
                signature=bytes.fromhex(str(transform["bytes"])),
            )

    commands: list[dict[str, Any]] = []
    for command in INIT_COMMANDS:
        value = int(command["command"])
        call_offsets = list(command["call_offsets"])
        for branch_index, call_offset in enumerate(call_offsets):
            _assert_immediate_call(
                payload,
                label=f"EPD_Init {command['name']} branch {branch_index}",
                value=value,
                call_offset=int(call_offset),
                target_section_id=0x19,
            )
        commands.append(
            {
                "name": str(command["name"]),
                "command": f"0x{value:02X}",
                "parameters": command["parameters"],
                "condition": str(command["condition"]),
                "command_call_relocation_file_offsets": [
                    _hex_offset(int(offset)) for offset in call_offsets
                ],
            }
        )

    for value, signature_offset in FIXED_CMDH_PARAMETERS:
        prefix = _mov_b_immediate_r12(value)
        _assert_bytes_at(
            payload,
            label=f"CMDH fixed parameter 0x{value:02X}",
            expected_offset=signature_offset,
            signature=prefix + bytes.fromhex("5e1600000000"),
        )

    _assert_source_records(
        payload,
        label="EPD_Init VV capture into dataBuff[53]",
        line=299,
        source="MOV.B   R12, &dataBuff + 53s",
        expected_offsets=[0x14109],
        start=init_start,
        end=init_end,
    )
    _assert_source_records(
        payload,
        label="EPD_Init final PON_flag clear",
        line=323,
        source="MOV.B   #0x0, &PON_flags",
        expected_offsets=[0x15D3E],
        start=init_start,
        end=init_end,
    )

    return {
        "metadata": {
            "V_mode": "dataBuff[14]",
            "Dyna_PLL": "dataBuff[15]",
            "SWITCH_FUNCTION": "dataBuff[59]",
            "IMAGE_SIZE": "dataBuff[60] * dataBuff[61] * dataBuff[62]",
            "FLASH_IMAGE_SIZE": "dataBuff[63] * dataBuff[64] * dataBuff[65]",
        },
        "ordered_command_table": commands,
        "PSR_V_mode_branch": {
            "command": "0x00",
            "if_V_mode_equals_1": [
                str(PSR_BRANCH["mode_1_transform"]["expression"]),
                str(PSR_BRANCH["second_parameter"]),
            ],
            "otherwise": [
                str(PSR_BRANCH["other_mode_transform"]["expression"]),
                str(PSR_BRANCH["second_parameter"]),
            ],
            "legacy_bit_0x20_is_SPD1657_3bit_proof": False,
        },
        "PLL_Dyna_PLL_branch": {
            "command": "0x30",
            "if_Dyna_PLL_equals_1": str(PLL_BRANCH["mode_1_transform"]["expression"]),
            "otherwise": str(PLL_BRANCH["other_mode_transform"]["expression"]),
        },
        "conditional_calibration": {
            "condition": "SWITCH_FUNCTION in {0x10, 0x11, 0x12}",
            "sequence": [
                "PON",
                "busy_wait_high",
                "AMV(dataBuff[51:53])",
                "busy_wait_high",
                "POF(0x00)",
                "busy_wait_high",
                "VV(read -> dataBuff[53])",
                "VDCS(dataBuff[53])",
                "T_VDCS(dataBuff[54])",
                "AGID(dataBuff[55])",
                "PWS(dataBuff[56])",
                "CCSET(dataBuff[57])",
                "TSSET(dataBuff[58])",
            ],
            "contains_DTM_or_DRF": False,
            "visible_refresh": False,
        },
        "final_state_write": "PON_flag = 0",
        "bulk_ReadData_inside_EPD_Init": False,
        "requires_prepopulated_dataBuff": True,
    }


def _display_flow_for_report(flow: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rendered: list[dict[str, Any]] = []
    for item in flow:
        row = {key: value for key, value in item.items() if key != "signature_offset"}
        if "command" in row:
            row["command"] = f"0x{int(row['command']):02X}"
        if "value" in row:
            row["value"] = f"0x{int(row['value']):02X}"
        if "signature_offset" in item:
            row["machine_signature_file_offset"] = _hex_offset(
                int(item["signature_offset"])
            )
        rendered.append(row)
    return rendered


def _prove_display_callers(payload: bytes) -> dict[str, Any]:
    reports: list[dict[str, Any]] = []
    all_upload_offsets: list[int] = []
    for caller in DISPLAY_CALLERS:
        name = str(caller["function"])
        section_id = int(caller["section_id"])
        start = int(caller["marker_offset"])
        end = int(caller["encoded_end_offset"])
        next_section_id = int(caller["next_section_id"])
        upload_offsets = list(caller["upload_record_offsets"])
        flow = list(caller["flow"])

        _assert_bytes_at(
            payload,
            label=f"{name} section marker",
            expected_offset=start,
            signature=_section_marker(section_id),
        )
        _assert_bytes_at(
            payload,
            label=f"{name} next section marker",
            expected_offset=end,
            signature=_section_marker(next_section_id),
        )

        upload_line = next(
            int(item["source_line"])
            for item in flow
            if item["op"] == "Upload_Temperature_LUT"
        )
        _assert_source_records(
            payload,
            label=f"{name} Upload_Temperature_LUT",
            line=upload_line,
            source="CALLA   #Upload_Temperature_LUTs",
            expected_offsets=upload_offsets,
            start=start,
            end=end,
        )
        all_upload_offsets.extend(upload_offsets)

        for item in flow:
            operation = str(item["op"])
            line = int(item["source_line"])
            if operation == "SPI_COMMAND":
                _assert_immediate_call(
                    payload,
                    label=f"{name} {item['name']} line {line}",
                    value=int(item["command"]),
                    call_offset=int(item["signature_offset"])
                    + len(_mov_b_immediate_r12(int(item["command"]))),
                    target_section_id=0x19,
                )
                source = "CALLA   #SPI_COMMANDs"
            elif operation == "SPI_DATA":
                _assert_immediate_call(
                    payload,
                    label=f"{name} SPI_DATA line {line}",
                    value=int(item["value"]),
                    call_offset=int(item["signature_offset"])
                    + len(_mov_b_immediate_r12(int(item["value"]))),
                    target_section_id=0x16,
                )
                source = "CALLA   #SPI_DATAs"
            elif operation == "busy_wait_high":
                source = "CALLA   #check_busy_highs"
            else:
                continue
            _assert_source_records(
                payload,
                label=f"{name} {operation} line {line}",
                line=line,
                source=source,
                expected_offsets=[
                    int(record["file_offset"])
                    for record in _source_records(payload, start=start, end=end)
                    if record["source_line"] == line and record["source"] == source
                ],
                start=start,
                end=end,
            )
            matching_count = sum(
                1
                for record in _source_records(payload, start=start, end=end)
                if record["source_line"] == line and record["source"] == source
            )
            if matching_count != 2:
                raise ProofError(
                    f"{name} {operation} line {line} has {matching_count} "
                    "source/relocation records, expected 2"
                )

        operation_names = [str(item.get("name", item["op"])) for item in flow]
        upload_index = next(
            index
            for index, item in enumerate(flow)
            if item["op"] == "Upload_Temperature_LUT"
        )
        drf_index = next(
            index for index, item in enumerate(flow) if item.get("name") == "DRF"
        )
        pon_index = next(
            index for index, item in enumerate(flow) if item.get("name") == "PON"
        )
        pof_index = next(
            index for index, item in enumerate(flow) if item.get("name") == "POF"
        )
        reports.append(
            {
                "function": name,
                "section_id": f"0x{section_id:02X}",
                "section_marker_file_offset": _hex_offset(start),
                "upload_source_line": upload_line,
                "upload_record_file_offsets": [
                    _hex_offset(offset) for offset in upload_offsets
                ],
                "upload_position": (
                    "after_PON_before_DRF" if pon_index < upload_index else "before_DTM"
                ),
                "ordered_flow": _display_flow_for_report(flow),
                "operation_names": operation_names,
                "upload_before_DRF": upload_index < drf_index,
                "PON_before_DRF_before_POF": pon_index < drf_index < pof_index,
                "ends_with_POF_0_and_busy": operation_names[-3:]
                == ["POF", "SPI_DATA", "busy_wait_high"],
            }
        )

    call_source = b" Source: CALLA   #Upload_Temperature_LUTs"
    actual_source_offsets = _all_offsets(payload, call_source)
    if len(actual_source_offsets) != 14:
        raise ProofError(
            "Upload_Temperature_LUT source-anchor count mismatch: "
            f"expected 14, got {len(actual_source_offsets)}"
        )
    # File-record offsets are the stable primary contract; this assertion also
    # rejects extra direct callers without depending on linker addresses.
    actual_file_offsets = [
        int(record["file_offset"])
        for record in _source_records(payload)
        if record["source"] == "CALLA   #Upload_Temperature_LUTs"
    ]
    if actual_file_offsets != all_upload_offsets:
        raise ProofError(
            "global Upload_Temperature_LUT caller records do not match the "
            "seven pinned display functions"
        )

    return {
        "logical_callers": 7,
        "UBROF_source_relocation_records": 14,
        "records_per_logical_CALLA": 2,
        "callers": reports,
        "named_blue_or_green_caller_present": any(
            needle in payload for needle in (b"EPD_Display_Blue", b"EPD_Display_Green")
        ),
        "invariants": {
            "Upload_before_DRF_in_all_callers": all(
                bool(report["upload_before_DRF"]) for report in reports
            ),
            "PON_before_DRF_before_POF_in_all_callers": all(
                bool(report["PON_before_DRF_before_POF"]) for report in reports
            ),
            "POF_0_then_busy_closure_in_all_callers": all(
                bool(report["ends_with_POF_0_and_busy"]) for report in reports
            ),
            "Upload_position_is_uniform": len(
                {str(report["upload_position"]) for report in reports}
            )
            == 1,
        },
    }


def _prove_direct_call_graph(payload: bytes) -> dict[str, Any]:
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
    init_to_upload = [
        record
        for record in init_records
        if "#Upload_Temperature_LUTs" in str(record["source"])
    ]
    upload_to_init = [
        record for record in upload_records if "#EPD_Inits" in str(record["source"])
    ]
    if init_to_upload or upload_to_init:
        raise ProofError("unexpected direct EPD_Init/Upload mutual call")

    absent_direct_targets = {
        "EPD_Init": b"#EPD_Inits",
        "reset": b"#resets",
        "setPON": b"#setPONs",
        "setPOF": b"#setPOFs",
        "EPD_Sleep": b"#EPD_Sleeps",
    }
    counts = {
        name: len(_all_offsets(payload, needle))
        for name, needle in absent_direct_targets.items()
    }
    if any(counts.values()):
        raise ProofError(f"unexpected helper direct-call anchors: {counts}")

    upload_spi_commands = [
        record
        for record in upload_records
        if record["source"] == "CALLA   #SPI_COMMANDs"
    ]
    if [int(record["source_line"]) for record in upload_spi_commands] != [434, 434]:
        raise ProofError(
            "Upload_Temperature_LUT direct SPI_COMMAND records are not the "
            "single pinned command-0x21 CALLA pair"
        )
    upload_busy_waits = [
        record for record in upload_records if "#check_busy_" in str(record["source"])
    ]
    if upload_busy_waits:
        raise ProofError("unexpected busy wait inside Upload_Temperature_LUT")

    return {
        "evidence_kind": "source-annotated direct CALLA/BRA anchors in this object",
        "EPD_Init_calls_Upload_Temperature_LUT": False,
        "Upload_Temperature_LUT_calls_EPD_Init": False,
        "direct_EPD_Init_callers_inside_this_object": 0,
        "direct_helper_call_anchor_counts": counts,
        "Upload_direct_SPI_COMMANDs": ["0x21"],
        "Upload_0x20_is_delegated_to_EPD_Load_LUT": True,
        "Upload_busy_wait_calls": 0,
        "Upload_contains_PSR_PWR_PLL_E9_PON_DRF_POF": False,
        "indirect_or_cross_object_calls_excluded": True,
        "init_before_upload_order_proven": False,
    }


def prove_object(path: Path = DEFAULT_OBJECT_PATH) -> dict[str, Any]:
    """Validate *path* and return metadata-only, importable audit evidence."""

    if not path.is_file():
        raise ProofError(f"required object is missing: {path}")
    payload = path.read_bytes()
    digest = _sha256(payload)
    if len(payload) != EXPECTED_OBJECT_SIZE:
        raise ProofError(
            f"object size mismatch: expected {EXPECTED_OBJECT_SIZE}, got {len(payload)}"
        )
    if digest != EXPECTED_OBJECT_SHA256:
        raise ProofError(
            f"object SHA-256 mismatch: expected {EXPECTED_OBJECT_SHA256}, got {digest}"
        )

    function_sections = _verify_function_sections(payload)
    read_data = _prove_read_data(payload)
    init = _prove_init(payload)
    direct_call_graph = _prove_direct_call_graph(payload)
    display_callers = _prove_display_callers(payload)

    arrays: dict[str, Any] = {}
    for label, contract in DATA_SECTIONS.items():
        section_id = int(contract["section_id"])
        marker_offset = int(contract["marker_offset"])
        decoded, encoded_end = extract_tagged_bytes(
            payload,
            section_id=section_id,
            marker_offset=marker_offset,
        )
        decoded_digest = _sha256(decoded)
        expected_length = int(contract["decoded_length"])
        expected_end = int(contract["encoded_end_offset"])
        expected_digest = str(contract["decoded_sha256"])
        next_section_id = int(contract["next_section_id"])
        if len(decoded) != expected_length:
            raise ProofError(
                f"{label} decoded length mismatch: expected {expected_length}, "
                f"got {len(decoded)}"
            )
        if encoded_end != expected_end:
            raise ProofError(
                f"{label} encoded end mismatch: expected {_hex_offset(expected_end)}, "
                f"got {_hex_offset(encoded_end)}"
            )
        if decoded_digest != expected_digest:
            raise ProofError(
                f"{label} decoded SHA-256 mismatch: expected {expected_digest}, "
                f"got {decoded_digest}"
            )
        next_marker = _section_marker(next_section_id)
        if payload[encoded_end : encoded_end + len(next_marker)] != next_marker:
            raise ProofError(
                f"{label} is not immediately followed by section "
                f"0x{next_section_id:02X}"
            )
        arrays[label] = {
            "section_id": f"0x{section_id:02X}",
            "marker_file_offset": _hex_offset(marker_offset),
            "encoded_payload_file_offset": _hex_offset(marker_offset + 6),
            "extraction_rule": "consume consecutive (0x36, value) byte pairs",
            "decoded_bytes": len(decoded),
            "decoded_sha256": decoded_digest,
            "encoded_end_file_offset": _hex_offset(encoded_end),
            "next_section_id": f"0x{next_section_id:02X}",
        }

    signatures: dict[str, Any] = {}
    for label, contract in UPLOAD_SIGNATURES.items():
        signature = bytes.fromhex(str(contract["bytes"]))
        expected_offset = int(contract["offset"])
        _assert_unique_at(
            payload,
            label=label,
            expected_offset=expected_offset,
            signature=signature,
        )
        evidence: dict[str, Any] = {
            "file_offset": _hex_offset(expected_offset),
            "hex": signature.hex(),
            "occurrences_in_object": 1,
        }
        if "instruction_offset" in contract:
            evidence["instruction_file_offset"] = _hex_offset(
                int(contract["instruction_offset"])
            )
        signatures[label] = evidence

    anchors: dict[str, Any] = {}
    for label, contract in SOURCE_ANCHORS.items():
        anchor = bytes(contract["bytes"])
        expected_offset = int(contract["offset"])
        _assert_unique_at(
            payload,
            label=label,
            expected_offset=expected_offset,
            signature=anchor,
        )
        anchors[label] = {
            "file_offset": _hex_offset(expected_offset),
            "ascii": anchor.decode("ascii"),
            "occurrences_in_object": 1,
        }

    return {
        "kind": "legacy-e2802-r43-lut-proof",
        "schema_version": SCHEMA_VERSION,
        "scope": "legacy_2020_iar_e2802_object_only",
        "not_proven": [
            "SPD1657 command or payload ABI",
            "current STM32 535/704 or 800-byte runtime profile contract",
            "dual-controller loading or live-panel safety",
            "a root caller that establishes EPD_Init before LUT upload",
            "the provider or transport implementation behind external symbol index 0x03",
            "dataBuff symbol size beyond its section-relative destination and backing-section extent",
            "runtime-to-factory-OTP or white-screen recovery",
            "reset, cold-power-cycle, PSR rollback, or recovery verification",
        ],
        "cross_version_limits": {
            "offsets_apply_only_after_exact_size_and_SHA256_match": True,
            "E2801_r43_offsets_or_PSR_placement_may_not_be_substituted": True,
            "current_E6_73_or_STM32_build_linkage_proven": False,
            "legacy_V_mode_bit_0x20_is_current_SPD1657_3bit_evidence": False,
        },
        "safety": {
            "offline_read_only": True,
            "hardware_accessed": False,
            "serial_accessed": False,
            "device_network_accessed": False,
            "firmware_written_or_flashed": False,
            "visible_refresh_attempted": False,
            "raw_waveform_emitted": False,
            "live_approved": False,
        },
        "object": {
            "relative_path": OBJECT_RELATIVE_PATH.as_posix(),
            "size_bytes": len(payload),
            "sha256": digest,
            "compiler": "IAR MSP430 5.30.1.20284",
            "target": "430X",
            "embedded_source": (
                "D:/E2802/20200923_3_inch/"
                "20200807_E2802_V0_0_4 - for verification/E2802.c"
            ),
        },
        "function_sections": function_sections,
        "direct_call_graph": direct_call_graph,
        "EPD_Init": init,
        "tagged_arrays": arrays,
        "upload_temperature_lut": {
            "function_section_id": "0x1E",
            "bulk_read": read_data,
            "lut0": {
                "command": "0x20",
                "source": "dataBuff + 4",
                "count_hex": "0x031F",
                "count_bytes": 799,
                "callee_section_id": "0x1D",
            },
            "lut1": {
                "command": "0x21",
                "value": "0xFF",
                "count_hex": "0x02C0",
                "count_bytes": 704,
                "command_callee_section_id": "0x19",
                "data_callee_section_id": "0x16",
            },
            "unique_ubrof_signatures": signatures,
            "unique_source_anchors": anchors,
            "contains_PSR_PWR_PLL_E9_refresh_or_recovery": False,
        },
        "display_refresh_callers": display_callers,
        "power_and_recovery_classification": {
            "display_level_refresh_power_closure": (
                "PON -> DRF(0x00) -> POF(0x00), with busy waits"
            ),
            "closure_proven_for_all_seven_display_callers": (
                display_callers["invariants"]["Upload_before_DRF_in_all_callers"]
                and display_callers["invariants"][
                    "PON_before_DRF_before_POF_in_all_callers"
                ]
                and display_callers["invariants"][
                    "POF_0_then_busy_closure_in_all_callers"
                ]
            ),
            "factory_or_OTP_recovery_closure": False,
            "reset_or_EPD_Sleep_called_by_these_paths": False,
            "safe_live_panel_sequence_derivable_from_object_alone": False,
        },
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify the identity-pinned legacy E2802.r43 LUT evidence."
    )
    parser.add_argument(
        "--object",
        type=Path,
        default=DEFAULT_OBJECT_PATH,
        help="E2802.r43 path (default: vendor reference under this repository)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = prove_object(args.object.resolve())
    except ProofError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    # ASCII-escaped JSON keeps redirected output deterministic on Windows even
    # when the active console code page is not UTF-8.
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
