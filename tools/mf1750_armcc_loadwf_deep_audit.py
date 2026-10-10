#!/usr/bin/env python3
"""Deep, metadata-only proof of the ArmCC ``loadWF`` object contract.

The target is the single CROF object in the supplied vendor archive.  This
tool deliberately emits no customer-key value, decrypted waveform byte, or
runtime payload.  It also contains no hardware, serial, or network code.

The earlier :mod:`tools.mf1750_spd1657_reverse_delta` audit already provides a
small CROF relocation and DWARF-v3 reader.  This proof reuses those parsers and
adds the missing instruction-level CFG, decrypt-gate state machine, complete
function inventory, macro audit, and strict same-object negative findings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_spd1657_reverse_delta as reverse_delta  # noqa: E402


KIND = "mf1750-armcc-loadwf-deep-audit"
SCHEMA_VERSION = 1
DEFAULT_LIBRARY = reverse_delta.DEFAULT_REFERENCE_ROOT / reverse_delta.LIBRARY_REL

EXPECTED_LIBRARY_BYTES = 65_082
EXPECTED_LIBRARY_SHA256 = reverse_delta.EXPECTED_IDENTITIES["library"]
EXPECTED_OBJECT_BYTES = 64_664
EXPECTED_OBJECT_SHA256 = reverse_delta.EXPECTED_IDENTITIES["library_object"]
EXPECTED_OBJECT_NAME = reverse_delta.EXPECTED_OBJECT_NAME
EXPECTED_OBJECT_ARCHIVE_OFFSET = 0x1A2

CODE_STREAM_MEMBER_OFFSET = 0x3C
EXECUTABLE_END = 0x1408
COMMENT_START = 0x140C
EXPECTED_EXECUTABLE_SHA256 = (
    "51d7e843c3a1a95601c16c895a91f96ae182146d5560ee377502c111832e1f7c"
)
EXPECTED_EXECUTABLE_WITH_PADDING_SHA256 = (
    "fbb004d0bb1abf1608d1e67fd5c83e2713e53a1bb857230de2cf506b56f49339"
)

LOADWF_START = 0x4B4
LOADWF_SIZE = 0x88
TEST_START = 0x116C
TEST_SIZE = 0xCC
TEST_RELOCATION_MEMBER_OFFSET = 0xABE4
TEST_RELOCATION_BYTES = 0x60
EXPECTED_TEST_RELOCATION_SHA256 = (
    "dc8c4a85eb6ab598cbd7976409b240f54e453b8e48fc60e1fc8697e293178dae"
)


class DeepAuditError(ValueError):
    """Raised when the identity-pinned object no longer proves the contract."""


FUNCTION_LAYOUT = (
    ("AES_CBC_decrypt_buffer", 0x0000, 0x0042),
    ("AES_init_ctx_iv", 0x0042, 0x001E),
    ("AddRoundKey", 0x0060, 0x0038),
    ("InvCipher", 0x0098, 0x0040),
    ("InvMixColumns", 0x00D8, 0x0102),
    ("InvShiftRows", 0x01DA, 0x0032),
    ("InvSubBytes", 0x020C, 0x002E),
    ("KeyExpansion", 0x023C, 0x0168),
    ("Multiply", 0x03A8, 0x007A),
    ("ShiftRows", 0x0422, 0x0032),
    ("SubBytes", 0x0454, 0x002E),
    ("XorWithIv", 0x0482, 0x001A),
    ("getSBoxInvert", 0x049C, 0x0008),
    ("getSBoxValue", 0x04A8, 0x0008),
    ("loadWF", LOADWF_START, LOADWF_SIZE),
    ("md5_process", 0x0558, 0x08AC),
    ("mysha256", 0x0E64, 0x02E4),
    ("test_decrypt_cbc_check_key", TEST_START, TEST_SIZE),
    ("tiny_md5", 0x124C, 0x002E),
    ("tiny_md5_finish", 0x127C, 0x00CE),
    ("tiny_md5_starts", 0x1350, 0x001A),
    ("tiny_md5_update", 0x1374, 0x0080),
    ("xtime", 0x13F4, 0x0014),
)

EXPECTED_TEST_RELOCATIONS = (
    (0x24, 0xEC, 0x0A, "__aeabi_memcpy"),
    (0x3C, 0xEC, 0x0A, "__aeabi_memcpy"),
    (0x62, 0xEC, 0x0A, "__aeabi_memcpy"),
    (0x9C, 0xE5, 0x0A, "mysha256"),
    (0xA6, 0xE6, 0x0A, "tiny_md5"),
    (0xB0, 0xAC, 0x0A, "AES_init_ctx_iv"),
    (0xBC, 0xAB, 0x0A, "AES_CBC_decrypt_buffer"),
    (0xCC, 0xC2, 0x02, "key_success"),
    (0xD0, 0xC3, 0x02, "wf_success"),
    (0xD4, 0xBC, 0x02, "in"),
    (0xD8, 0xBD, 0x02, "iniKey"),
    (0xDC, 0xBE, 0x02, "ciniKey"),
)

MACRO_RECORDS = (
    (0x90A7, 26, "E5_3Bit_Mode", "0"),
    (0x90B8, 27, "NXP_LPC114_Platform", "1"),
    (0x90D0, 28, "Show_Debug_LOG", "0"),
    (0x90E3, 34, "WF_DeCode_SIZE", "544"),
    (0x90F8, 35, "WF_SIZE", "535"),
    (0x9106, 43, "AES_BLOCKLEN", "16"),
    (0x9118, 44, "AES_keyExpSize", "240"),
    (0x912D, 46, "M_LEN", "64"),
)

FORBIDDEN_RETAINED_TOKENS = (
    "E5_3Bit_Mode 1",
    "E5_3Bit_Mode=1",
    "WF_DeCode_SIZE 800",
    "WF_DeCode_SIZE=800",
    "WF_SIZE 799",
    "WF_SIZE=799",
    "WF_SIZE 800",
    "WF_SIZE=800",
    "WF23_25",
    "decode800",
    "mode1",
)

CONSTDATA_LAYOUT = (
    ("md5_padding", 0x17FB, 64),
    ("sbox", 0x183B, 256),
    ("rsbox", 0x193B, 256),
    ("Rcon", 0x1A3B, 11),
    ("alignment_padding", 0x1A46, 14),
    ("sha256_K", 0x1A54, 256),
    ("LUT1_DATA", 0x1B54, 704),
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DeepAuditError(message)


def _parse_ar(payload: bytes) -> list[dict[str, Any]]:
    _require(payload.startswith(b"!<arch>\n"), "library is not a Unix ar archive")
    position = 8
    raw_records: list[dict[str, Any]] = []
    while position < len(payload):
        header = payload[position : position + 60]
        _require(
            len(header) == 60 and header[58:60] == b"`\n",
            "invalid ar member header",
        )
        raw_name = header[:16].decode("ascii", errors="replace").strip()
        try:
            size = int(header[48:58].decode("ascii").strip())
        except ValueError as error:
            raise DeepAuditError("invalid ar member size") from error
        data_offset = position + 60
        end = data_offset + size
        _require(end <= len(payload), "truncated ar member")
        raw_records.append(
            {
                "raw_name": raw_name,
                "header_offset": position,
                "data_offset": data_offset,
                "bytes": size,
                "body": payload[data_offset:end],
            }
        )
        position = end + (size & 1)
    _require(position == len(payload), "ar member walk did not end at EOF")

    string_table = next(
        (record["body"] for record in raw_records if record["raw_name"] == "//"),
        b"",
    )
    for record in raw_records:
        raw_name = record["raw_name"]
        name = raw_name
        if raw_name.startswith("/") and raw_name[1:].isdigit() and string_table:
            tail = string_table[int(raw_name[1:]) :]
            stops = [
                offset
                for token in (b"/\n", b"\n", b"/")
                if (offset := tail.find(token)) >= 0
            ]
            name = tail[: min(stops) if stops else len(tail)].decode(
                "ascii", errors="replace"
            )
        elif raw_name.endswith("/") and raw_name not in ("/", "//"):
            name = raw_name[:-1]
        record["name"] = name
    return raw_records


def _parse_archive_symbol_index(body: bytes) -> list[str]:
    _require(len(body) >= 4, "truncated archive symbol index")
    count = struct.unpack_from(">I", body, 0)[0]
    table_end = 4 + 4 * count
    _require(table_end <= len(body), "truncated archive symbol offsets")
    offsets = struct.unpack_from(f">{count}I", body, 4)
    _require(
        set(offsets) == {0x166},
        "archive symbols no longer point to the sole object header",
    )
    names = body[table_end:].rstrip(b"\x00").split(b"\x00")
    _require(len(names) == count, "archive symbol-name count changed")
    return [name.decode("ascii") for name in names]


def _read_object(library_path: Path) -> tuple[bytes, dict[str, Any]]:
    library = library_path.read_bytes()
    _require(len(library) == EXPECTED_LIBRARY_BYTES, "library size changed")
    _require(
        _sha256(library) == EXPECTED_LIBRARY_SHA256,
        "library SHA-256 identity changed",
    )
    records = _parse_ar(library)
    _require(
        [(record["raw_name"], record["bytes"]) for record in records]
        == [("/", 210), ("//", 20), ("/0", EXPECTED_OBJECT_BYTES)],
        "archive member inventory changed",
    )
    symbol_names = _parse_archive_symbol_index(records[0]["body"])
    objects = [record for record in records if record["raw_name"] not in ("/", "//")]
    _require(len(objects) == 1, "archive no longer contains exactly one object")
    obj = objects[0]
    _require(obj["name"] == EXPECTED_OBJECT_NAME, "object member name changed")
    _require(
        obj["data_offset"] == EXPECTED_OBJECT_ARCHIVE_OFFSET,
        "object archive offset changed",
    )
    body = obj["body"]
    _require(_sha256(body) == EXPECTED_OBJECT_SHA256, "object identity changed")
    return body, {
        "path": str(library_path),
        "bytes": len(library),
        "sha256": _sha256(library),
        "ar_record_count": len(records),
        "object_member_count": len(objects),
        "object": {
            "name": obj["name"],
            "archive_data_offset": obj["data_offset"],
            "bytes": len(body),
            "sha256": _sha256(body),
            "magic_hex": body[:8].hex(),
        },
        "archive_public_symbols": symbol_names,
    }


def _scan_dwarf_cus(body: bytes) -> list[dict[str, Any]]:
    abbreviations = reverse_delta._parse_dwarf_abbreviations(  # noqa: SLF001
        body, reverse_delta.DWARF_ABBREV_OFFSET
    )
    header_tail = b"\x03\x00\x00\x00\x00\x00\x04"
    reports: list[dict[str, Any]] = []
    for offset in range(len(body) - 11):
        if body[offset + 4 : offset + 11] != header_tail:
            continue
        unit_length = struct.unpack_from("<I", body, offset)[0]
        expected_bytes = unit_length + 4
        if expected_bytes < 11 or offset + expected_bytes > len(body):
            continue
        try:
            dies = reverse_delta._parse_dwarf_cu(  # noqa: SLF001
                body, offset, expected_bytes, abbreviations
            )
        except reverse_delta.ReverseAuditError:
            continue
        if not dies or dies[0]["tag"] != 0x11:
            continue
        root = dies[0]["attributes"]
        subprograms = []
        for die in dies:
            if die["tag"] != 0x2E:
                continue
            attributes = die["attributes"]
            name = attributes.get(0x03)
            if not isinstance(name, str):
                continue
            subprograms.append(
                {
                    "name": name,
                    "die_offset": die["offset"],
                    "bytes": attributes.get(0x12),
                    "external": bool(attributes.get(0x3F, 0)),
                    "decl_line": attributes.get(0x3B),
                }
            )
        reports.append(
            {
                "member_offset": offset,
                "bytes": expected_bytes,
                "name": root.get(0x03),
                "subprograms": subprograms,
            }
        )
    return reports


def _function_inventory(body: bytes) -> dict[str, Any]:
    cus = _scan_dwarf_cus(body)
    function_dies = [function for cu in cus for function in cu["subprograms"]]
    dwarf_sizes = {function["name"]: function["bytes"] for function in function_dies}
    expected_names = {name for name, _, _ in FUNCTION_LAYOUT}
    _require(
        len(function_dies) == len(FUNCTION_LAYOUT),
        "DWARF function count changed",
    )
    _require(set(dwarf_sizes) == expected_names, "DWARF function names changed")

    stream = body[CODE_STREAM_MEMBER_OFFSET:]
    executable = stream[:EXECUTABLE_END]
    with_padding = stream[:COMMENT_START]
    _require(
        _sha256(executable) == EXPECTED_EXECUTABLE_SHA256,
        "executable stream identity changed",
    )
    _require(
        _sha256(with_padding) == EXPECTED_EXECUTABLE_WITH_PADDING_SHA256,
        "executable padding boundary changed",
    )
    _require(
        stream[COMMENT_START:].startswith(b"Component: ARM Compiler 5.06"),
        "comment boundary changed",
    )

    function_reports = []
    for index, (name, start, size) in enumerate(FUNCTION_LAYOUT):
        _require(dwarf_sizes[name] == size, f"DWARF size changed for {name}")
        end = start + size
        next_start = (
            FUNCTION_LAYOUT[index + 1][1]
            if index + 1 < len(FUNCTION_LAYOUT)
            else COMMENT_START
        )
        _require(end <= next_start, f"function layout overlaps at {name}")
        function_reports.append(
            {
                "name": name,
                "code_stream_start": start,
                "member_start": CODE_STREAM_MEMBER_OFFSET + start,
                "bytes": size,
                "sha256": _sha256(stream[start:end]),
                "literal_or_alignment_bytes_after": next_start - end,
                "dwarf_external": next(
                    function["external"]
                    for function in function_dies
                    if function["name"] == name
                ),
                "dwarf_decl_line": next(
                    function["decl_line"]
                    for function in function_dies
                    if function["name"] == name
                ),
            }
        )
    return {
        "dwarf_compilation_units": len(cus),
        "dwarf_subprograms": len(function_dies),
        "code_stream_member_offset": CODE_STREAM_MEMBER_OFFSET,
        "executable_bytes": len(executable),
        "executable_sha256": _sha256(executable),
        "alignment_before_comment_bytes": COMMENT_START - EXECUTABLE_END,
        "comment_member_offset": CODE_STREAM_MEMBER_OFFSET + COMMENT_START,
        "functions": function_reports,
    }


def _read_rel_rows(
    body: bytes,
    offset: int,
    expected: tuple[tuple[int, int, int, str], ...],
) -> list[dict[str, Any]]:
    rows = []
    for index, (wanted_offset, wanted_symbol, wanted_type, name) in enumerate(expected):
        reloc_offset, info = struct.unpack_from("<II", body, offset + 8 * index)
        symbol = info >> 8
        reloc_type = info & 0xFF
        _require(
            (reloc_offset, symbol, reloc_type)
            == (wanted_offset, wanted_symbol, wanted_type),
            f"relocation changed for {name} at row {index}",
        )
        rows.append(
            {
                "offset": reloc_offset,
                "symbol_index": symbol,
                "relocation_type": (
                    "ARM_THM_CALL" if reloc_type == 0x0A else "ARM_ABS32"
                ),
                "symbol_name": name,
            }
        )
    return rows


def _thumb_ldr_literal_target(code: bytes, instruction_offset: int) -> int:
    halfword = struct.unpack_from("<H", code, instruction_offset)[0]
    _require(halfword & 0xF800 == 0x4800, "expected Thumb LDR literal")
    pc = (instruction_offset + 4) & ~0x03
    return pc + (halfword & 0xFF) * 4


def _thumb_conditional_branch_target(code: bytes, instruction_offset: int) -> int:
    halfword = struct.unpack_from("<H", code, instruction_offset)[0]
    _require(halfword & 0xF000 == 0xD000, "expected Thumb conditional branch")
    displacement = (halfword & 0xFF) << 1
    if displacement & 0x100:
        displacement -= 0x200
    return instruction_offset + 4 + displacement


def _thumb_cbz_target(code: bytes, instruction_offset: int) -> int:
    halfword = struct.unpack_from("<H", code, instruction_offset)[0]
    _require(halfword & 0xF500 == 0xB100, "expected Thumb CBZ/CBNZ")
    immediate = (((halfword >> 9) & 1) << 5) | ((halfword >> 3) & 0x1F)
    return instruction_offset + 4 + immediate * 2


def _thumb_unconditional_branch_target(code: bytes, instruction_offset: int) -> int:
    halfword = struct.unpack_from("<H", code, instruction_offset)[0]
    _require(halfword & 0xF800 == 0xE000, "expected Thumb unconditional branch")
    displacement = (halfword & 0x7FF) << 1
    if displacement & 0x800:
        displacement -= 0x1000
    return instruction_offset + 4 + displacement


def _loadwf_proof(body: bytes, formal: dict[str, Any]) -> dict[str, Any]:
    stream = body[CODE_STREAM_MEMBER_OFFSET:]
    code = stream[LOADWF_START : LOADWF_START + LOADWF_SIZE]
    _require(
        _sha256(code) == reverse_delta.EXPECTED_LOADWF_CODE_SHA256,
        "loadWF code identity changed",
    )
    _require(
        _thumb_conditional_branch_target(code, 0x1C) == 0x84,
        "loadWF key-failure branch changed",
    )
    _require(
        _thumb_cbz_target(code, 0x22) == 0x80,
        "loadWF wf-failure branch changed",
    )
    _require(
        _thumb_unconditional_branch_target(code, 0x82) == 0x7E,
        "loadWF E2 exit branch changed",
    )
    _require(
        _thumb_unconditional_branch_target(code, 0x86) == 0x7E,
        "loadWF E1 exit branch changed",
    )

    load_relocs = formal["relocation_section"]["entries"]
    _require(
        [(row["offset"], row["symbol_index"]) for row in load_relocs]
        == [(row[0], row[1]) for row in reverse_delta.EXPECTED_LOADWF_RELOCATIONS],
        "loadWF relocation list changed",
    )
    literal_targets = {
        "customer_key_strlen": _thumb_ldr_literal_target(code, 0x04),
        "customer_key_decrypt_arg": _thumb_ldr_literal_target(code, 0x0E),
        "key_success": _thumb_ldr_literal_target(code, 0x16),
        "wf_success": _thumb_ldr_literal_target(code, 0x1E),
        "pwr_d_first": _thumb_ldr_literal_target(code, 0x26),
        "in_first": _thumb_ldr_literal_target(code, 0x2A),
        "pll_d_first": _thumb_ldr_literal_target(code, 0x4C),
        "pwr_d_write": _thumb_ldr_literal_target(code, 0x52),
        "pll_d_write": _thumb_ldr_literal_target(code, 0x5C),
        "in_write": _thumb_ldr_literal_target(code, 0x68),
        "lut1_write": _thumb_ldr_literal_target(code, 0x74),
    }
    _require(
        literal_targets
        == {
            "customer_key_strlen": 0x88,
            "customer_key_decrypt_arg": 0x88,
            "key_success": 0x8C,
            "wf_success": 0x90,
            "pwr_d_first": 0x94,
            "in_first": 0x98,
            "pll_d_first": 0x9C,
            "pwr_d_write": 0x94,
            "pll_d_write": 0x9C,
            "in_write": 0x98,
            "lut1_write": 0xA0,
        },
        "loadWF literal dataflow changed",
    )

    expected_write_sequences = (
        (0x50, "062210490120fff7feff"),
        (0x5A, "01220f493020fff7feff"),
        (0x64, "40f217220b492020fff7feff"),
        (0x70, "4ff430720a492120fff7feff"),
    )
    for offset, expected_hex in expected_write_sequences:
        expected = bytes.fromhex(expected_hex)
        _require(
            code[offset : offset + len(expected)] == expected,
            f"writeEPD call sequence changed at loadWF+0x{offset:X}",
        )

    nodes = [
        {"id": "entry_key_gate", "start": 0x00, "end_exclusive": 0x1E},
        {"id": "wf_gate", "start": 0x1E, "end_exclusive": 0x24},
        {"id": "success_writes", "start": 0x24, "end_exclusive": 0x7E},
        {"id": "shared_return", "start": 0x7E, "end_exclusive": 0x80},
        {"id": "return_e2", "start": 0x80, "end_exclusive": 0x84},
        {"id": "return_e1", "start": 0x84, "end_exclusive": 0x88},
    ]
    edges = [
        ["entry_key_gate", "return_e1", "key_success == 0"],
        ["entry_key_gate", "wf_gate", "key_success != 0"],
        ["wf_gate", "return_e2", "wf_success == 0"],
        ["wf_gate", "success_writes", "wf_success != 0"],
        ["success_writes", "shared_return", "fallthrough, r0 = 0x00"],
        ["return_e2", "shared_return", "r0 = 0xE2"],
        ["return_e1", "shared_return", "r0 = 0xE1"],
    ]
    return {
        "prototype_from_dwarf": "unsigned char loadWF(unsigned char const *wf_buffer)",
        "code_stream_range": [LOADWF_START, LOADWF_START + LOADWF_SIZE],
        "member_range": [
            CODE_STREAM_MEMBER_OFFSET + LOADWF_START,
            CODE_STREAM_MEMBER_OFFSET + LOADWF_START + LOADWF_SIZE,
        ],
        "sha256": _sha256(code),
        "cfg": {
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "cyclomatic_complexity": len(edges) - len(nodes) + 2,
            "loops": 0,
        },
        "call_sites": [
            {"offset": 0x06, "callee": "strlen"},
            {"offset": 0x12, "callee": "test_decrypt_cbc_check_key"},
            {"offset": 0x56, "callee": "writeEPD"},
            {"offset": 0x60, "callee": "writeEPD"},
            {"offset": 0x6C, "callee": "writeEPD"},
            {"offset": 0x78, "callee": "writeEPD"},
        ],
        "literal_targets": literal_targets,
        "success_transactions": [
            {
                "ordinal": 1,
                "command": "0x01",
                "parameter_bytes": 6,
                "pointer": "pwr_d",
                "source": "fixed 0x0F followed by decoded in[0..4]",
            },
            {
                "ordinal": 2,
                "command": "0x30",
                "parameter_bytes": 1,
                "pointer": "pll_d",
                "source": "decoded in[6]",
            },
            {
                "ordinal": 3,
                "command": "0x20",
                "parameter_bytes": 535,
                "pointer": "in",
                "source": "decoded in[0..534]",
            },
            {
                "ordinal": 4,
                "command": "0x21",
                "parameter_bytes": 704,
                "pointer": "LUT1_DATA",
                "source": "independent library-resident symbol",
            },
        ],
        "pseudocode": [
            "key_len = strlen(customer_key)",
            "test_decrypt_cbc_check_key(wf_buffer, customer_key, key_len)",
            "if key_success == 0: return 0xE1",
            "if wf_success == 0: return 0xE2",
            "pwr_d = [0x0F, in[0], in[1], in[2], in[3], in[4]]",
            "pll_d = [in[6]]",
            "writeEPD(0x01, pwr_d, 6)",
            "writeEPD(0x30, pll_d, 1)",
            "writeEPD(0x20, in, 535)",
            "writeEPD(0x21, LUT1_DATA, 704)",
            "return 0x00",
        ],
        "writer_result_checked": False,
        "controller_or_chip_select_argument_present": False,
        "reset_busy_refresh_or_recovery_call_present": False,
    }


def _decrypt_gate_proof(body: bytes) -> dict[str, Any]:
    reloc_payload = body[
        TEST_RELOCATION_MEMBER_OFFSET : TEST_RELOCATION_MEMBER_OFFSET
        + TEST_RELOCATION_BYTES
    ]
    _require(
        _sha256(reloc_payload) == EXPECTED_TEST_RELOCATION_SHA256,
        "decrypt-check relocation payload changed",
    )
    rows = _read_rel_rows(
        body, TEST_RELOCATION_MEMBER_OFFSET, EXPECTED_TEST_RELOCATIONS
    )
    stream = body[CODE_STREAM_MEMBER_OFFSET:]
    code = stream[TEST_START : TEST_START + TEST_SIZE]
    _require(
        _sha256(code)
        == "ba955f2bf76c68bcc859707e68edae7b3a51884f4da695975a0841376d0219b2",
        "decrypt-check code identity changed",
    )
    # The exact straight-line success tail is part of the reachability proof.
    _require(
        code[0x8C:0xC6]
        == bytes.fromhex(
            "baf1010f19d101200d49087044a90f48fff7feff40aa31460c48fff7feff"
            "40aa44a96846fff7feff4ff4087206496846fff7feff012003490870"
        ),
        "decrypt-check success tail changed",
    )
    return {
        "code_stream_range": [TEST_START, TEST_START + TEST_SIZE],
        "member_range": [
            CODE_STREAM_MEMBER_OFFSET + TEST_START,
            CODE_STREAM_MEMBER_OFFSET + TEST_START + TEST_SIZE,
        ],
        "sha256": _sha256(code),
        "relocation_section": {
            "name": ".reli.test_decrypt_cbc_check_key",
            "member_offset": TEST_RELOCATION_MEMBER_OFFSET,
            "bytes": TEST_RELOCATION_BYTES,
            "sha256": _sha256(reloc_payload),
            "entries": rows,
        },
        "wrapper_contract": {
            "total_input_length_argument_present": False,
            "fixed_ciphertext_copy_bytes": 544,
            "wrapped_length_offsets": [544, 545],
            "wrapped_length_byte_order": "big-endian",
            "wrapped_key_offset": 546,
            "iniKey_capacity_bytes_from_dwarf": 75,
            "ciniKey_capacity_bytes_from_dwarf": 75,
            "length_bound_checked_before_iniKey_copy": False,
            "length_bound_checked_before_iniKey_xor": False,
            "length_bound_checked_before_iniKey_terminator": False,
            "caller_buffer_bound_checked_before_fixed_copy": False,
            "length_equality_check_occurs_after_unsafe_operations": True,
        },
        "key_and_aes_flow": [
            "clear key_success and wf_success",
            "copy exactly 544 wrapper bytes into global in",
            "read a 16-bit big-endian wrapped length",
            "copy wrapped field into iniKey and XOR it with wrapper prefix",
            "append a zero byte, then copy caller key into ciniKey",
            "require exact length and byte equality against caller key",
            "derive a 32-byte SHA-256 result and a 16-byte MD5 result",
            "use SHA-256 result as AES-256 key and MD5 result as CBC IV",
            "AES-CBC decrypt exactly 544 bytes in global in",
        ],
        "normal_return_flag_state_machine": [
            {
                "state": "entry",
                "key_success": 0,
                "wf_success": 0,
            },
            {
                "state": "key_mismatch_normal_return",
                "key_success": 0,
                "wf_success": 0,
            },
            {
                "state": "key_match_transient_before_crypto_calls_return",
                "key_success": 1,
                "wf_success": 0,
                "observable_by_loadWF_after_normal_return": False,
            },
            {
                "state": "key_match_normal_return",
                "key_success": 1,
                "wf_success": 1,
            },
        ],
        "normal_single_thread_return_pairs": [[0, 0], [1, 1]],
        "loadwf_e2_pair": [1, 0],
        "loadwf_e2_reachable_from_normal_single_thread_helper_return": False,
        "e2_branch_exists_in_loadwf_machine_code": True,
        "e2_exception_scope": (
            "external concurrent mutation, memory corruption, or another model-external "
            "fault is not ruled out"
        ),
        "plaintext_magic_checked": False,
        "plaintext_format_checked": False,
        "padding_checked": False,
        "integrity_or_authentication_checked": False,
        "aes_callee_error_status_checked": False,
        "wf_success_semantics": (
            "the straight-line decrypt sequence returned; it is not proof that plaintext "
            "is a valid waveform"
        ),
        "key_material_emitted": False,
    }


def _macro_audit(body: bytes) -> dict[str, Any]:
    macros = []
    for offset, line, name, value in MACRO_RECORDS:
        encoded = bytes((0x01, line)) + f"{name} {value}".encode() + b"\x00"
        _require(
            body[offset : offset + len(encoded)] == encoded,
            f"DWARF macro record changed for {name}",
        )
        _require(body.count(encoded) == 1, f"DWARF macro is not unique: {name}")
        macros.append(
            {
                "name": name,
                "value": value,
                "source_line": line,
                "record_member_offset": offset,
            }
        )
    retained = body.decode("latin-1")
    forbidden_counts = {
        token: retained.lower().count(token.lower())
        for token in FORBIDDEN_RETAINED_TOKENS
    }
    _require(
        all(count == 0 for count in forbidden_counts.values()),
        "a forbidden mode-1/800 retained token appeared",
    )
    return {
        "source_macro_records": macros,
        "other_debug_build_markers": {
            "DEBUG_1_present": b"DEBUG 1" in body,
            "__EVAL_1_present": b"__EVAL 1" in body,
            "compiler_debug_option_present": b"--debug" in body,
            "compiler_optimization_option": "-O0" if b" -O0 " in body else None,
            "split_sections_present": b"--split_sections" in body,
        },
        "interpretation": (
            "--debug/DEBUG=1 describe build/debug metadata; Show_Debug_LOG=0 is the "
            "retained source logging switch"
        ),
        "forbidden_retained_token_counts": forbidden_counts,
    }


def _constdata_audit(body: bytes) -> list[dict[str, Any]]:
    reports = []
    for name, start, size in CONSTDATA_LAYOUT:
        payload = body[start : start + size]
        _require(len(payload) == size, f"truncated constdata item: {name}")
        reports.append(
            {
                "name": name,
                "member_range": [start, start + size],
                "bytes": size,
                "sha256": _sha256(payload),
                "all_ff": payload == b"\xff" * size,
                "all_zero": payload == b"\x00" * size,
                "raw_bytes_emitted": False,
            }
        )
    lut1 = next(item for item in reports if item["name"] == "LUT1_DATA")
    _require(
        lut1["sha256"] == reverse_delta.EXPECTED_IDENTITIES["lut1_ff_704"]
        and lut1["all_ff"],
        "LUT1_DATA identity changed",
    )
    return reports


def build_report(library_path: Path = DEFAULT_LIBRARY) -> dict[str, Any]:
    library_path = library_path.resolve()
    _require(library_path.is_file(), f"library does not exist: {library_path}")
    body, archive = _read_object(library_path)
    formal = reverse_delta._audit_formal_loader_bindings(body)  # noqa: SLF001
    functions = _function_inventory(body)
    macros = _macro_audit(body)
    constants = _constdata_audit(body)
    loadwf = _loadwf_proof(body, formal)
    decrypt_gate = _decrypt_gate_proof(body)

    dwarf_arrays = formal["dwarf"]["array_types"]
    _require(dwarf_arrays["iniKey"]["bytes"] == 75, "iniKey bound changed")
    _require(dwarf_arrays["ciniKey"]["bytes"] == 75, "ciniKey bound changed")

    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": "offline_metadata_only_same_armcc_archive",
        "archive": archive,
        "compiler_and_macros": macros,
        "function_inventory": functions,
        "global_arrays_from_dwarf": dwarf_arrays,
        "constdata": constants,
        "loadwf": loadwf,
        "decrypt_gate": decrypt_gate,
        "strict_negative_findings": {
            "second_archive_object_member_present": False,
            "second_loadwf_dwarf_subprogram_present": False,
            "runtime_mode_argument_or_mode_global_relocated_by_loadwf": False,
            "loadwf_loop_or_alternate_transaction_branch_present": False,
            "retained_mode1_or_decode800_macro_present": False,
            "retained_wf_size_799_or_800_macro_present": False,
            "retained_wf23_symbol_or_token_present": False,
            "independent_non_ff_lut1_payload_present": False,
            "same_object_799_byte_write_present": False,
            "same_object_plaintext_validity_check_present": False,
            "source_level_inactive_mode1_branch_recoverable_from_object": False,
            "never_existed_in_original_source_proven": False,
            "explanation": (
                "the sole retained build is E5_3Bit_Mode=0, decode=544, WF_SIZE=535; "
                "an inactive preprocessor branch or non-emitted source cannot be recovered "
                "or disproved from this object"
            ),
        },
        "evidence_grades": {
            "definitions": {
                "A": "direct, identity-pinned same-object code/relocation/DWARF evidence",
                "B": "same-delivery build, archive-index, macro, or source corroboration",
                "C": "cross-generation evidence; never promoted to the current ABI",
                "U": "unknown or not recoverable from the retained object",
            },
            "A": [
                "loadWF CFG, return branches, six calls, and four fixed transactions",
                "decrypt helper dataflow, unsafe length ordering, and AES call chain",
                "normal-return flag pairs (0,0)/(1,1), making E2 normally unreachable",
                "DWARF array sizes and complete 23-function inventory",
                "independent 704-byte all-FF LUT1_DATA binding",
            ],
            "B": [
                "single object member and 15-symbol archive index",
                "ArmCC -O0 --split_sections --debug build markers",
                "retained macros E5_3Bit_Mode=0, WF_DeCode_SIZE=544, WF_SIZE=535",
            ],
            "C": [
                "not used by this same-object proof; legacy 799+704 evidence remains separate",
            ],
            "U": [
                "inactive/preprocessed mode-1 source and its would-be 800-byte ABI",
                "plaintext field semantics and all-FF LUT1 controller meaning",
                "panel/FPL suitability, dual-controller delivery, and recovery behavior",
                "effects or success of the external writeEPD implementation",
            ],
        },
        "safety": {
            "offline_only": True,
            "target_library_modified": False,
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "device_network_accessed": False,
            "firmware_or_flash_written": False,
            "display_refresh_attempted": False,
            "customer_key_material_emitted": False,
            "raw_plaintext_emitted": False,
            "runtime_payload_generated": False,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deep-audit the local ArmCC loadWF object without emitting payload data."
    )
    parser.add_argument("--library", type=Path, default=DEFAULT_LIBRARY)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_report(args.library)
    except (DeepAuditError, reverse_delta.ReverseAuditError) as error:
        json.dump(
            {"kind": KIND, "schema_version": SCHEMA_VERSION, "error": str(error)},
            sys.stdout,
            ensure_ascii=True,
            indent=2,
        )
        sys.stdout.write("\n")
        return 2
    json.dump(report, sys.stdout, ensure_ascii=True, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
