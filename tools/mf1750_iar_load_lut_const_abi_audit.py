#!/usr/bin/env python3
"""Recover the legacy IAR LUT helper ABI without touching hardware.

The delivered E2801/E2802 UBROF10 objects contain two public functions named
``EPD_Load_LUT_const`` and ``EPD_Load_LUT``.  This audit uses identity-pinned
official IAR XLIB/XLINK executables plus the already pinned TI MSP430 objdump
to answer four deliberately narrow questions:

* which entry registers carry command, source pointer, and byte count;
* which command/data helpers are called and how the loop is bounded;
* whether the ``const`` helper itself selects DATA0 or DATA1; and
* whether any natural or external consumer of that helper is present.

All linked images live only in fresh ASCII temporary directories.  The JSON
contains identities, hashes, counts, and semantic facts; it never contains
object code, disassembly, LUT bytes, or a hardware action path.  The result is
legacy generic-helper evidence, not a current SPD1657 ABI or live-panel
authorization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from host.application.durable_io import write_new_bytes_durable
from tools import mf1750_iar_r43_cross_object_graph as graph
from tools import mf1750_iar_temperature_selector_audit as selector
from tools import mf1750_iar_xlib_external_index_audit as xlib_audit


KIND = "mf1750-iar-load-lut-const-abi-audit"
SCHEMA_VERSION = 2

FUNCTIONS = ("EPD_Load_LUT_const", "EPD_Load_LUT")
HELPERS = ("SPI_COMMAND", "SPI_DATA")

COMMON_LINK = {
    "intel_hex_size_bytes": 824,
    "intel_hex_sha256": (
        "c6a664d574b77bff3ddf7c814e86830895cf1f9f0a50acd4c60f41accc094928"
    ),
    "emitted_memory_bytes": 280,
    "emitted_address_start": 0x10000,
    "emitted_address_end_inclusive": 0x10117,
    "address_byte_manifest_sha256": (
        "ea3e2c97a161504aeb0365da0f4caceaac09a872916002d2ccded0df869eb667"
    ),
    "record_count": 20,
    "data_record_count": 18,
    "extended_segment_records": 1,
    "extended_linear_records": 0,
    "xlink_code_bytes": 280,
    "xlink_data_bytes": 0,
    "xlink_absolute_symbols": 11,
    "function_start": 0x10000,
    "function_end_exclusive": 0x10020,
    "function_bytes": 32,
    "function_sha256": (
        "28dcd41718bfd6d12be5ca137ea0a771d5a69babc4d57f67bebc45efa2711966"
    ),
    "function_instruction_lines": 14,
    "function_normalized_disassembly_bytes": 537,
    "function_normalized_disassembly_sha256": (
        "01e1fdb243546505df022a7a20c846fe8e64ceedffc42374dd9ca77194d58350"
    ),
    "helpers": {
        "SPI_COMMAND": {
            "start": 0x10020,
            "end_exclusive": 0x1009C,
            "bytes": 124,
            "sha256": (
                "119fd295ccd68967e3496cb035e8ba611c5bc1df12b62113ae9cde3686867ada"
            ),
            "instruction_lines": 37,
            "normalized_disassembly_bytes": 1_625,
            "normalized_disassembly_sha256": (
                "42eea10502b25ac28b0221d27e3504c7aad7edf5afbe6882e2a7f4a9db5f5aa9"
            ),
        },
        "SPI_DATA": {
            "start": 0x1009C,
            "end_exclusive": 0x10118,
            "bytes": 124,
            "sha256": (
                "9972945301c4117f5dfe4de36a4690a15db8a8d6999e92c523f6b2864f5ac546"
            ),
            "instruction_lines": 37,
            "normalized_disassembly_bytes": 1_625,
            "normalized_disassembly_sha256": (
                "f91085e57edacfd4773975c16281e57b8f2155bcdefb0b4746a92481e2302b18"
            ),
        },
    },
}

EXPECTED_INSTRUCTIONS = {
    0x10000: "pushm #4, r11",
    0x10002: "mov r13, r10",
    0x10004: "mov r14, r11",
    0x10006: "calla #65568",
    0x1000A: "clr r8",
    0x1000C: "jmp $+12",
    0x1000E: "mov.b @r10, r12",
    0x10010: "calla #65692",
    0x10014: "inc r10",
    0x10016: "inc r8",
    0x10018: "cmp r11, r8",
    0x1001A: "jnc $-12",
    0x1001C: "popm #4, r11",
    0x1001E: "reta",
}

SPI_DATA_SERIALIZATION_INSTRUCTIONS = {
    0x1009E: "mov.b r12, r10",
    0x100C8: "clr.b r11",
    0x100EA: "rla.b r10",
    0x100EC: "inc.b r11",
    0x100EE: "cmp.b #8, r11",
    0x100F0: "jc $+14",
    0x100F2: "cmp.b #0, r10",
    0x100F4: "jge $-40",
    0x100F6: "bis.b #64, &0x0223",
    0x100FE: "bic.b #64, &0x0223",
}

OBJECTS: dict[str, dict[str, Any]] = {
    "E2801.r43": {
        "size_bytes": 315_632,
        "sha256": "404b950ea65b754a335b90be24683281ebee9dab52e362fd6d49170b4b8a38a3",
        "entry_count": 50,
        "entry_table_sha256": (
            "3ba430450952a909340975bece17439bf6f286108839c2d0dd98eca2ed82f660"
        ),
        "external_count": 11,
        "external_table_sha256": (
            "ea38135f911e56966412d0bf5383d2c04df005dfdecec4453eecfce79f6eab1b"
        ),
        "all_calls": 339,
        "functions": {
            "EPD_Load_LUT_const": {
                "section_id": 0x2C,
                "origin_record_file_offset": 0x1AC24,
                "outgoing_calls": (
                    (0x1ADFF, 454, "SPI_COMMAND", 0x19),
                    (0x1B0D0, 457, "SPI_DATA", 0x16),
                ),
                "incoming_calls": (),
                "all_other_roots_code_bytes": 5_572,
            },
            "EPD_Load_LUT": {
                "section_id": 0x1D,
                "origin_record_file_offset": 0x1B31A,
                "outgoing_calls": (
                    (0x1B4F5, 465, "SPI_COMMAND", 0x19),
                    (0x1B7C0, 468, "SPI_DATA", 0x16),
                ),
                "incoming_calls": ((0x1E26F, 553, "Upload_Temperature_LUT", 0x1E),),
                "all_other_roots_code_bytes": 5_604,
            },
        },
    },
    "E2802.r43": {
        "size_bytes": 328_062,
        "sha256": "19fb74c05444880ea6a403d697307e47a874998b5529ee84dd0592ecae16c9ce",
        "entry_count": 49,
        "entry_table_sha256": (
            "6a48fc442a1f4a1b35bca5d6131a541524e34d21b4e7c310058b83a28179218f"
        ),
        "external_count": 11,
        "external_table_sha256": (
            "ea38135f911e56966412d0bf5383d2c04df005dfdecec4453eecfce79f6eab1b"
        ),
        "all_calls": 360,
        "functions": {
            "EPD_Load_LUT_const": {
                "section_id": 0x2C,
                "origin_record_file_offset": 0x15DCE,
                "outgoing_calls": (
                    (0x15FA9, 331, "SPI_COMMAND", 0x19),
                    (0x1625F, 334, "SPI_DATA", 0x16),
                ),
                "incoming_calls": (),
                "all_other_roots_code_bytes": 6_196,
            },
            "EPD_Load_LUT": {
                "section_id": 0x1D,
                "origin_record_file_offset": 0x1648E,
                "outgoing_calls": (
                    (0x16669, 342, "SPI_COMMAND", 0x19),
                    (0x16919, 345, "SPI_DATA", 0x16),
                ),
                "incoming_calls": ((0x1800F, 432, "Upload_Temperature_LUT", 0x1E),),
                "all_other_roots_code_bytes": 6_228,
            },
        },
    },
}

EXPECTED_GLOBAL_DIRECT_CALLS = 1_786
EXPECTED_OBJECT_MANIFEST_SHA256 = (
    "08f7b10936d066441c09843ee0345ec3f61ac3735ae521a1d892af100c0ba70d"
)


class LoadLutConstAbiAuditError(RuntimeError):
    """An identity, official-tool, link, graph, or ABI invariant changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LoadLutConstAbiAuditError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hex(value: int) -> str:
    return f"0x{value:X}"


def _pin_object(path: Path, contract: dict[str, Any]) -> bytes:
    _require(path.is_file(), f"object is missing: {path}")
    payload = path.read_bytes()
    _require(len(payload) == contract["size_bytes"], f"{path.name} size changed")
    _require(_sha256(payload) == contract["sha256"], f"{path.name} SHA-256 changed")
    _require(payload[:2] == b"\x01\x0a", f"{path.name} is no longer UBROF10")
    return payload


def _parse_link_summary(payload: bytes, *, expected_warnings: str) -> dict[str, int]:
    text = payload.decode("cp1252")
    _require(selector.XLINK_VERSION_BANNER in text, "XLINK banner changed")
    _require("Errors: none" in text, "XLINK reported errors")
    _require(f"Warnings: {expected_warnings}" in text, "XLINK warnings changed")
    code = re.search(r"(?m)^\s*([0-9][0-9 ]*) bytes of CODE memory\s*$", text)
    data = re.search(
        r"(?m)^\s*([0-9][0-9 ]*) bytes of DATA memory "
        r"\(\+\s*([0-9][0-9 ]*) absolute \)\s*$",
        text,
    )
    _require(code is not None and data is not None, "XLINK memory summary missing")
    return {
        "code_bytes": int(code.group(1).replace(" ", "")),
        "data_bytes": int(data.group(1).replace(" ", "")),
        "absolute_symbols": int(data.group(2).replace(" ", "")),
    }


def _cross_reference_status(text: str, symbol: str) -> str:
    module_marker = text.find("MODULE MAP")
    _require(module_marker >= 0, "XLINK MODULE MAP marker missing")
    prefix = text[:module_marker]
    rows = re.findall(
        rf"(?m)^\s{{8}}{re.escape(symbol)}\s+(NOT NEEDED|[0-9A-F]{{4,8}})\s*$",
        prefix,
    )
    _require(len(rows) == 1, f"XLINK cross-reference row changed for {symbol}")
    return rows[0]


def _module_entry(text: str, symbol: str) -> dict[str, Any]:
    lines = text.replace("\r\n", "\n").split("\n")
    starts = [index for index, line in enumerate(lines) if "MODULE MAP" in line]
    _require(len(starts) == 1, "XLINK MODULE MAP bounds changed")
    symbol_re = re.compile(
        rf"^\s+{re.escape(symbol)}(?:\s+(?P<address>[0-9A-F]{{8}}))?"
        rf"(?:\s+(?P<ref_by>.*))?\s*$"
    )
    matches: list[tuple[int, re.Match[str]]] = []
    for index in range(starts[0] + 1, len(lines)):
        match = symbol_re.match(lines[index])
        if match is not None and index > 0 and "====" in lines[index - 1]:
            matches.append((index, match))
    _require(len(matches) == 1, f"XLINK module entry changed for {symbol}")
    index, match = matches[0]
    part_index = index
    part_match: re.Match[str] | None = None
    while part_index > starts[0]:
        candidate = re.match(
            r"^\s*Segment part (?P<part>\d+)\.(?P<tail>.*)$", lines[part_index]
        )
        if candidate is not None:
            part_match = candidate
            break
        part_index -= 1
    _require(part_match is not None, f"XLINK segment part missing for {symbol}")
    tail = part_match.group("tail").strip()
    span: dict[str, Any] | None = None
    for prior in range(part_index - 1, max(starts[0], part_index - 4), -1):
        span_match = re.match(
            r"^\s*Relative segment, address: (?P<start>[0-9A-F]+) - "
            r"(?P<end>[0-9A-F]+) \(0x(?P<bytes>[0-9a-f]+) bytes\), "
            r"align: (?P<align>\d+)\s*$",
            lines[prior],
        )
        if span_match is not None:
            span = {
                "start": _hex(int(span_match.group("start"), 16)),
                "end_inclusive": _hex(int(span_match.group("end"), 16)),
                "bytes": int(span_match.group("bytes"), 16),
                "alignment_power": int(span_match.group("align")),
            }
            break
    incoming: list[str] = []
    incoming_match = re.search(r"Intra module refs:\s+(\S+)", tail)
    if incoming_match is not None:
        incoming.append(incoming_match.group(1))
        cursor = part_index + 1
        while cursor < index and "ENTRY" not in lines[cursor]:
            stripped = lines[cursor].strip()
            if stripped and not set(stripped) <= {"=", "-"}:
                incoming.extend(stripped.split())
            cursor += 1
    return {
        "segment": lines[part_index - (2 if span is not None else 1)].strip(),
        "segment_part": int(part_match.group("part")),
        "needed": "NOT NEEDED" not in tail,
        "root": "ROOT" in tail,
        "span": span,
        "address": (
            None
            if match.group("address") is None
            else _hex(int(match.group("address"), 16))
        ),
        "ref_by": (match.group("ref_by") or "").strip() or None,
        "incoming_intra_module_refs": incoming,
    }


def _run_xlink(
    xlink_path: Path,
    object_path: Path,
    *,
    roots: list[str],
) -> dict[str, Any]:
    _require(bool(roots), "XLINK root set is empty")
    _require(len(roots) == len(set(roots)), "XLINK root set has duplicates")
    with tempfile.TemporaryDirectory(prefix="mf1750-iar-lut-abi-") as temp_name:
        _require(temp_name.isascii(), "temporary link path is not ASCII-only")
        temp_dir = Path(temp_name)
        object_copy = temp_dir / object_path.name
        output_path = temp_dir / "linked.hex"
        map_path = temp_dir / "linked.map"
        shutil.copyfile(object_path, object_copy)
        environment = os.environ.copy()
        environment.pop("XLINK_ENVPAR", None)
        arguments = [
            str(xlink_path),
            "-Fintel-extended",
            "-o",
            str(output_path),
            "-cmsp430",
            selector.CODE_PLACEMENT,
            selector.DATA_PLACEMENT,
            *(
                f"-D{name}=0x{address:X}"
                for name, address in selector.EXTERNAL_DEFINITIONS
            ),
            f"-g{','.join(roots)}",
            "-xemi",
            "-l",
            str(map_path),
            str(object_copy),
        ]
        completed = subprocess.run(
            arguments,
            cwd=temp_dir,
            env=environment,
            check=False,
            capture_output=True,
            timeout=30,
        )
        _require(completed.returncode == 0, f"{object_path.name} XLINK failed")
        _require(not completed.stderr, "XLINK unexpectedly used stderr")
        expected_warnings = "none" if len(roots) == 1 else "1"
        summary = _parse_link_summary(
            completed.stdout,
            expected_warnings=expected_warnings,
        )
        _require(output_path.is_file() and map_path.is_file(), "XLINK output missing")
        map_text = map_path.read_text("cp1252")
        report: dict[str, Any] = {
            "root_count": len(roots),
            "xlink_summary": summary,
            "cross_reference": {
                name: _cross_reference_status(map_text, name)
                for name in (*FUNCTIONS, *HELPERS, "DATA0", "DATA1")
            },
            "module_entries": {
                name: _module_entry(map_text, name)
                for name in (*FUNCTIONS, *HELPERS, "DATA0", "DATA1")
            },
            "temporary_outputs_discarded": True,
        }
        return report


def _root_link_with_disassembly(
    xlink_path: Path,
    objdump_path: Path,
    object_path: Path,
    root: str,
) -> dict[str, Any]:
    # This intentionally repeats the small link wrapper instead of returning a
    # dead temporary path from _run_xlink.
    with tempfile.TemporaryDirectory(prefix="mf1750-iar-lut-abi-root-") as temp_name:
        _require(temp_name.isascii(), "temporary root-link path is not ASCII-only")
        temp_dir = Path(temp_name)
        object_copy = temp_dir / object_path.name
        output_path = temp_dir / "linked.hex"
        map_path = temp_dir / "linked.map"
        shutil.copyfile(object_path, object_copy)
        environment = os.environ.copy()
        environment.pop("XLINK_ENVPAR", None)
        arguments = [
            str(xlink_path),
            "-Fintel-extended",
            "-o",
            str(output_path),
            "-cmsp430",
            selector.CODE_PLACEMENT,
            selector.DATA_PLACEMENT,
            *(
                f"-D{name}=0x{address:X}"
                for name, address in selector.EXTERNAL_DEFINITIONS
            ),
            f"-g{root}",
            "-xemi",
            "-l",
            str(map_path),
            str(object_copy),
        ]
        completed = subprocess.run(
            arguments,
            cwd=temp_dir,
            env=environment,
            check=False,
            capture_output=True,
            timeout=30,
        )
        _require(completed.returncode == 0, f"{object_path.name} {root} link failed")
        _require(not completed.stderr, "root XLINK unexpectedly used stderr")
        summary = _parse_link_summary(completed.stdout, expected_warnings="none")
        intel_hex = output_path.read_bytes()
        map_text = map_path.read_text("cp1252")
        image = selector.parse_intel_hex(intel_hex)
        disassembly = subprocess.run(
            [str(objdump_path), "-D", "-b", "ihex", "-m", "msp:14", str(output_path)],
            cwd=temp_dir,
            check=False,
            capture_output=True,
            timeout=30,
        )
        _require(disassembly.returncode == 0, "objdump failed")
        _require(not disassembly.stderr, "objdump unexpectedly used stderr")
        instructions = selector.parse_objdump_instructions(disassembly.stdout)

        expected = COMMON_LINK
        _require(len(intel_hex) == expected["intel_hex_size_bytes"], "HEX size changed")
        _require(_sha256(intel_hex) == expected["intel_hex_sha256"], "HEX hash changed")
        addresses = sorted(image.memory)
        _require(
            len(addresses) == expected["emitted_memory_bytes"], "image size changed"
        )
        _require(
            addresses[0] == expected["emitted_address_start"]
            and addresses[-1] == expected["emitted_address_end_inclusive"],
            "image address range changed",
        )
        _require(
            addresses == list(range(addresses[0], addresses[-1] + 1)),
            "root-linked image is not contiguous",
        )
        _require(
            selector._address_byte_manifest_sha256(image.memory)
            == expected["address_byte_manifest_sha256"],
            "root-linked image manifest changed",
        )
        _require(
            summary
            == {
                "code_bytes": expected["xlink_code_bytes"],
                "data_bytes": expected["xlink_data_bytes"],
                "absolute_symbols": expected["xlink_absolute_symbols"],
            },
            "root-link memory summary changed",
        )

        function_start = expected["function_start"]
        function_end = expected["function_end_exclusive"]
        function_payload = bytes(
            image.memory[address] for address in range(function_start, function_end)
        )
        function_rows = [
            row for row in instructions if function_start <= row.address < function_end
        ]
        _require(
            len(function_payload) == expected["function_bytes"],
            "function byte count changed",
        )
        _require(
            _sha256(function_payload) == expected["function_sha256"],
            "function hash changed",
        )
        _require(
            len(function_rows) == expected["function_instruction_lines"],
            "function instruction count changed",
        )
        _require(
            sum(len(row.encoded_bytes) for row in function_rows)
            == len(function_payload),
            "objdump does not cover complete function",
        )
        by_address = {row.address: row.normalized_instruction for row in function_rows}
        _require(
            by_address == EXPECTED_INSTRUCTIONS, "function instruction ABI changed"
        )
        normalized = (
            "\n".join(row.stripped_line for row in function_rows) + "\n"
        ).encode("utf-8")
        _require(
            len(normalized) == expected["function_normalized_disassembly_bytes"],
            "normalized function disassembly length changed",
        )
        _require(
            _sha256(normalized) == expected["function_normalized_disassembly_sha256"],
            "normalized function disassembly changed",
        )

        helper_reports: dict[str, Any] = {}
        for helper, helper_contract in expected["helpers"].items():
            start = int(helper_contract["start"])
            end = int(helper_contract["end_exclusive"])
            payload = bytes(image.memory[address] for address in range(start, end))
            rows = [row for row in instructions if start <= row.address < end]
            helper_normalized = (
                "\n".join(row.stripped_line for row in rows) + "\n"
            ).encode("utf-8")
            _require(len(payload) == helper_contract["bytes"], f"{helper} size changed")
            _require(_sha256(payload) == helper_contract["sha256"], f"{helper} changed")
            _require(
                len(rows) == helper_contract["instruction_lines"],
                f"{helper} instruction count changed",
            )
            _require(
                len(helper_normalized)
                == helper_contract["normalized_disassembly_bytes"],
                f"{helper} normalized length changed",
            )
            _require(
                _sha256(helper_normalized)
                == helper_contract["normalized_disassembly_sha256"],
                f"{helper} normalized disassembly changed",
            )
            helper_by_address = {
                row.address: row.normalized_instruction for row in rows
            }
            _require(
                helper_by_address[start + 2] == "mov.b r12, r10",
                f"{helper} no longer consumes the low byte of R12",
            )
            if helper == "SPI_DATA":
                observed_serialization = {
                    address: helper_by_address.get(address)
                    for address in SPI_DATA_SERIALIZATION_INSTRUCTIONS
                }
                _require(
                    observed_serialization == SPI_DATA_SERIALIZATION_INSTRUCTIONS,
                    "SPI_DATA bit-serialization dataflow changed",
                )
            helper_reports[helper] = {
                "synthetic_start": _hex(start),
                "synthetic_end_inclusive": _hex(end - 1),
                "byte_count": len(payload),
                "sha256": _sha256(payload),
                "instruction_line_count": len(rows),
                "normalized_disassembly_sha256": _sha256(helper_normalized),
                "entry_consumes_R12_low_byte": True,
                "D7_to_D0_serialization_proven": helper == "SPI_DATA",
            }

        root_entry = _module_entry(map_text, root)
        _require(root_entry["segment"] == "CODE", "root segment changed")
        _require(root_entry["span"]["bytes"] == 32, "root span changed")
        _require(root_entry["address"] == "0x10000", "root address changed")
        _require(
            root_entry["ref_by"] == "Absolute parts (?ABS_ENTRY_MOD)",
            "root ref-by classification changed",
        )
        for helper in HELPERS:
            helper_entry = _module_entry(map_text, helper)
            _require(
                helper_entry["incoming_intra_module_refs"] == [root],
                f"{helper} incoming link edge changed",
            )
        for array in ("DATA0", "DATA1"):
            _require(
                _cross_reference_status(map_text, array) == "NOT NEEDED",
                f"{root} unexpectedly selected {array}",
            )

    return {
        "root": root,
        "xlink_summary": summary,
        "intel_hex": {
            "size_bytes": len(intel_hex),
            "sha256": _sha256(intel_hex),
            "record_count": image.record_count,
            "data_record_count": image.data_record_count,
            "extended_segment_records": image.extended_segment_records,
            "extended_linear_records": image.extended_linear_records,
            "emitted_memory_bytes": len(addresses),
            "emitted_address_start": _hex(addresses[0]),
            "emitted_address_end_inclusive": _hex(addresses[-1]),
            "address_byte_manifest_sha256": (
                selector._address_byte_manifest_sha256(image.memory)
            ),
        },
        "function": {
            "section_part": root_entry["segment_part"],
            "synthetic_start": _hex(function_start),
            "synthetic_end_inclusive": _hex(function_end - 1),
            "byte_count": len(function_payload),
            "sha256": _sha256(function_payload),
            "instruction_line_count": len(function_rows),
            "normalized_disassembly_sha256": _sha256(normalized),
        },
        "helpers": helper_reports,
        "DATA0_cross_reference": _cross_reference_status(map_text, "DATA0"),
        "DATA1_cross_reference": _cross_reference_status(map_text, "DATA1"),
        "temporary_outputs_discarded": True,
    }


def _call_projection(call: dict[str, Any]) -> tuple[int, int, str, int]:
    return (
        int(str(call["relocation_file_offset"]), 16),
        int(call["source_line"]),
        str(call["callee_symbol"]),
        int(str(call["target_id"]), 16),
    )


def _validate_object_graph(
    name: str,
    payload: bytes,
    contract: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        object_report, calls = graph._object_report(name, payload)
    except graph.GraphError as error:
        raise LoadLutConstAbiAuditError(str(error)) from error
    _require(len(calls) == contract["all_calls"], f"{name} call count changed")
    sections = {row["section_id"]: row for row in object_report["code_sections"]}
    functions: dict[str, Any] = {}
    for function, function_contract in contract["functions"].items():
        section_id = int(function_contract["section_id"])
        section = sections.get(_hex(section_id))
        _require(section is not None, f"{name} {function} section missing")
        _require(section["symbols"] == [function], f"{name} {function} name changed")
        _require(
            int(str(section["origin_record_file_offset"]), 16)
            == function_contract["origin_record_file_offset"],
            f"{name} {function} origin changed",
        )
        outgoing = [
            call for call in calls if call["caller_section_id"] == _hex(section_id)
        ]
        incoming = [call for call in calls if call["callee_symbol"] == function]
        _require(
            tuple(_call_projection(call) for call in outgoing)
            == function_contract["outgoing_calls"],
            f"{name} {function} outgoing calls changed",
        )
        incoming_projection = tuple(
            (
                int(str(call["relocation_file_offset"]), 16),
                int(call["source_line"]),
                str(call["caller_symbols"][0]),
                int(str(call["caller_section_id"]), 16),
            )
            for call in incoming
        )
        _require(
            incoming_projection == function_contract["incoming_calls"],
            f"{name} {function} incoming calls changed",
        )
        functions[function] = {
            "section_id": _hex(section_id),
            "origin_record_file_offset": section["origin_record_file_offset"],
            "outgoing_local_calls": [
                {
                    "callee": call["callee_symbol"],
                    "source_line": call["source_line"],
                    "relocation_file_offset": call["relocation_file_offset"],
                    "target_section_id": call["target_id"],
                }
                for call in outgoing
            ],
            "incoming_direct_calls": [
                {
                    "caller_symbols": call["caller_symbols"],
                    "source_line": call["source_line"],
                    "relocation_file_offset": call["relocation_file_offset"],
                    "classification": call["relocation_classification"],
                }
                for call in incoming
            ],
        }
    return functions, calls


def _natural_reference_link(
    xlink_path: Path,
    object_path: Path,
    entries: list[str],
    target: str,
    contract: dict[str, Any],
) -> dict[str, Any]:
    roots = [entry for entry in entries if entry != target]
    linked = _run_xlink(
        xlink_path,
        object_path,
        roots=roots,
    )
    summary = linked["xlink_summary"]
    _require(
        summary
        == {
            "code_bytes": contract["all_other_roots_code_bytes"],
            "data_bytes": 4_792,
            "absolute_symbols": 11,
        },
        f"{object_path.name} {target} all-other-roots summary changed",
    )
    target_status = linked["cross_reference"][target]
    target_entry = linked["module_entries"][target]
    expected_needed = target == "EPD_Load_LUT"
    _require(target_entry["segment"] == "CODE", f"{target} segment changed")
    _require(
        target_entry["segment_part"] == contract["section_id"],
        f"{target} section part changed",
    )
    _require(
        target_entry["needed"] == expected_needed, f"{target} reachability changed"
    )
    if expected_needed:
        _require(target_status != "NOT NEEDED", f"{target} lost natural consumer")
        _require(target_entry["span"]["bytes"] == 32, f"{target} span changed")
        _require(
            target_entry["incoming_intra_module_refs"] == ["Upload_Temperature_LUT"],
            f"{target} natural incoming reference changed",
        )
    else:
        _require(target_status == "NOT NEEDED", f"{target} gained a consumer")
        _require(target_entry["address"] is None, f"{target} gained an address")
        _require(target_entry["span"] is None, f"{target} gained an included span")
        _require(
            target_entry["incoming_intra_module_refs"] == [],
            f"{target} gained an intra-module reference",
        )
    return {
        "forced_public_root_count": len(roots),
        "target_was_not_forced": True,
        "target_cross_reference_status": target_status,
        "target_segment_part": target_entry["segment_part"],
        "target_needed": target_entry["needed"],
        "target_span_bytes": (
            None if target_entry["span"] is None else target_entry["span"]["bytes"]
        ),
        "incoming_intra_module_refs": target_entry["incoming_intra_module_refs"],
        "xlink_summary": summary,
        "temporary_outputs_discarded": True,
    }


def _global_consumer_scan(iar_root: Path) -> dict[str, Any]:
    object_dir = iar_root / graph.OBJECT_DIR_REL
    total_calls = 0
    const_calls: list[dict[str, Any]] = []
    load_calls: list[dict[str, Any]] = []
    for name in sorted(graph.EXPECTED_OBJECTS, key=str.casefold):
        payload = (object_dir / name).read_bytes()
        try:
            _, calls = graph._object_report(name, payload)
        except graph.GraphError as error:
            raise LoadLutConstAbiAuditError(str(error)) from error
        total_calls += len(calls)
        for call in calls:
            if call["callee_symbol"] not in FUNCTIONS:
                continue
            row = {
                "object": name,
                "caller_section_id": call["caller_section_id"],
                "caller_symbols": call["caller_symbols"],
                "callee": call["callee_symbol"],
                "source_line": call["source_line"],
                "relocation_file_offset": call["relocation_file_offset"],
                "classification": call["relocation_classification"],
            }
            (
                const_calls if call["callee_symbol"] == FUNCTIONS[0] else load_calls
            ).append(row)
    _require(total_calls == EXPECTED_GLOBAL_DIRECT_CALLS, "global call count changed")
    _require(not const_calls, "EPD_Load_LUT_const gained a direct consumer")
    _require(len(load_calls) == 43, "EPD_Load_LUT same-name call count changed")
    _require(
        all(row["classification"] == "local-section-relative" for row in load_calls),
        "EPD_Load_LUT gained an external consumer",
    )
    legacy_load_calls = [row for row in load_calls if row["object"] in OBJECTS]
    _require(
        len(legacy_load_calls) == 2
        and {row["object"] for row in legacy_load_calls} == set(OBJECTS),
        "E2801/E2802 EPD_Load_LUT consumers changed",
    )
    same_name_counts = {
        name: sum(row["object"] == name for row in load_calls)
        for name in sorted({row["object"] for row in load_calls}, key=str.casefold)
    }
    _require(
        same_name_counts
        == {
            "E2801.r43": 1,
            "E2802.r43": 1,
            "ED020OC2.r43": 27,
            "ED020OC4.r43": 14,
        },
        "EPD_Load_LUT same-name object inventory changed",
    )
    return {
        "objects_scanned": len(graph.EXPECTED_OBJECTS),
        "paired_direct_call_edges_scanned": total_calls,
        "EPD_Load_LUT_const_direct_consumer_edges": const_calls,
        "EPD_Load_LUT_same_spelling_local_edge_counts_by_object": same_name_counts,
        "E2801_E2802_EPD_Load_LUT_direct_consumer_edges": legacy_load_calls,
        "EPD_Load_LUT_const_observed_external_direct_consumer_count": 0,
        "EPD_Load_LUT_observed_external_direct_consumer_count": 0,
        "same_spelling_local_symbols_are_cross_object_consumers": False,
    }


def _official_external_table_scan(xlib_path: Path, iar_root: Path) -> dict[str, Any]:
    object_dir = iar_root / graph.OBJECT_DIR_REL
    parsed: list[str] = []
    version_bounded: list[str] = []
    declarations: dict[str, list[str]] = {function: [] for function in FUNCTIONS}
    for name in sorted(graph.EXPECTED_OBJECTS, key=str.casefold):
        try:
            row = xlib_audit._run_xlib_list(
                xlib_path,
                object_dir / name,
                command="LIST-EXTERNALS",
                expected_kind="Ext",
            )
        except xlib_audit.XlibAuditError as error:
            raise LoadLutConstAbiAuditError(str(error)) from error
        if row["status"] == "PARSED":
            parsed.append(name)
            for function in FUNCTIONS:
                if function in row["symbols"]:
                    declarations[function].append(name)
        else:
            _require(
                row["status"] == "UNSUPPORTED_STACK_USAGE_TAG_E2",
                f"{name} has an unknown XLIB status",
            )
            version_bounded.append(name)
    _require(len(parsed) == 26, "XLIB-parseable external-table count changed")
    _require(
        version_bounded == ["DELAY.r43", "E6_73.r43", "main.r43"],
        "XLIB E2 version-boundary inventory changed",
    )
    _require(
        declarations == {function: [] for function in FUNCTIONS},
        "a parseable object gained an external LUT-helper declaration",
    )
    return {
        "official_XLIB_parseable_external_tables": len(parsed),
        "official_XLIB_version_bounded_external_tables": version_bounded,
        "EPD_Load_LUT_const_external_declaration_objects": declarations[
            "EPD_Load_LUT_const"
        ],
        "EPD_Load_LUT_external_declaration_objects": declarations["EPD_Load_LUT"],
        "UBROF10_external_declaration_scan_complete": True,
        "UBROF11_external_declaration_scan_complete": False,
    }


def build_report(
    xlink_path: Path,
    xlib_path: Path,
    objdump_path: Path,
    iar_root: Path = graph.DEFAULT_IAR_ROOT,
) -> dict[str, Any]:
    """Build one deterministic metadata-only helper ABI report."""

    try:
        xlink_identity = selector._pin_tool(
            xlink_path,
            selector.EXPECTED_XLINK,
            label="XLINK",
            version_args=[],
            version_banner=selector.XLINK_VERSION_BANNER,
            encoding="cp1252",
        )
        objdump_identity = selector._pin_tool(
            objdump_path,
            selector.EXPECTED_OBJDUMP,
            label="objdump",
            version_args=["--version"],
            version_banner=selector.OBJDUMP_VERSION_BANNER,
            encoding="utf-8",
        )
        xlib_identity = xlib_audit._pin_xlib(xlib_path)
        graph_report = graph.build_report(iar_root)
    except (
        selector.TemperatureSelectorAuditError,
        xlib_audit.XlibAuditError,
        graph.GraphError,
    ) as error:
        raise LoadLutConstAbiAuditError(str(error)) from error

    _require(
        graph_report["identity"]["object_manifest_sha256"]
        == EXPECTED_OBJECT_MANIFEST_SHA256,
        "IAR object manifest changed",
    )
    object_dir = iar_root / graph.OBJECT_DIR_REL
    objects: dict[str, Any] = {}
    linked_function_hashes: set[str] = set()
    linked_image_hashes: set[str] = set()
    for filename, contract in OBJECTS.items():
        path = object_dir / filename
        payload = _pin_object(path, contract)
        try:
            entries = xlib_audit._run_xlib_list(
                xlib_path,
                path,
                command="LIST-ENTRIES",
                expected_kind="Ent",
            )
            externals = xlib_audit._run_xlib_list(
                xlib_path,
                path,
                command="LIST-EXTERNALS",
                expected_kind="Ext",
            )
        except xlib_audit.XlibAuditError as error:
            raise LoadLutConstAbiAuditError(str(error)) from error
        _require(entries["status"] == "PARSED", f"{filename} entries unavailable")
        _require(externals["status"] == "PARSED", f"{filename} externals unavailable")
        _require(
            len(entries["symbols"]) == contract["entry_count"]
            and entries["table_sha256"] == contract["entry_table_sha256"],
            f"{filename} XLIB entry table changed",
        )
        _require(
            len(externals["symbols"]) == contract["external_count"]
            and externals["table_sha256"] == contract["external_table_sha256"],
            f"{filename} XLIB external table changed",
        )
        _require(
            set(FUNCTIONS).issubset(entries["symbols"]),
            f"{filename} helper PUBLIC entries missing",
        )

        graph_functions, _ = _validate_object_graph(filename, payload, contract)
        functions: dict[str, Any] = {}
        for function in FUNCTIONS:
            root_link = _root_link_with_disassembly(
                xlink_path,
                objdump_path,
                path,
                function,
            )
            natural = _natural_reference_link(
                xlink_path,
                path,
                list(entries["symbols"]),
                function,
                contract["functions"][function],
            )
            _require(
                root_link["function"]["section_part"]
                == contract["functions"][function]["section_id"],
                f"{filename} {function} linked section changed",
            )
            linked_function_hashes.add(root_link["function"]["sha256"])
            linked_image_hashes.add(root_link["intel_hex"]["sha256"])
            functions[function] = {
                **graph_functions[function],
                "root_only_synthetic_link": root_link,
                "all_other_PUBLIC_roots_natural_reference_test": natural,
            }
        objects[filename.removesuffix(".r43")] = {
            "source_object": {
                "name": filename,
                "size_bytes": len(payload),
                "sha256": _sha256(payload),
                "ubrof_version_byte": payload[1],
            },
            "official_xlib": {
                "PUBLIC_entry_count": len(entries["symbols"]),
                "PUBLIC_entry_table_sha256": entries["table_sha256"],
                "EXTERNAL_entry_count": len(externals["symbols"]),
                "EXTERNAL_entry_table_sha256": externals["table_sha256"],
                "both_helpers_are_PUBLIC": True,
            },
            "functions": functions,
        }

    _require(
        linked_function_hashes == {COMMON_LINK["function_sha256"]},
        "four linked function bodies are no longer identical",
    )
    _require(
        linked_image_hashes == {COMMON_LINK["intel_hex_sha256"]},
        "four root-only linked images are no longer identical",
    )
    consumer_scan = _global_consumer_scan(iar_root)
    external_table_scan = _official_external_table_scan(xlib_path, iar_root)
    final_inputs = graph_report["dependency_graph"][
        "final_d43_direct_project_r43_input_names"
    ]
    _require(
        set(OBJECTS).isdisjoint(final_inputs),
        "legacy E2801/E2802 entered the delivered final D43 link",
    )

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "scope": {
            "source_objects": 2,
            "project_r43_objects_scanned_for_consumers": 29,
            "source_objects_modified": False,
            "temporary_copies_only": True,
            "temporary_outputs_discarded": True,
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "device_network_accessed": False,
            "flashed": False,
            "reset_requested": False,
            "visible_refreshes": 0,
            "live_token_or_claim_generated": False,
            "raw_object_code_emitted": False,
            "raw_disassembly_emitted": False,
            "raw_waveform_or_payload_emitted": False,
        },
        "identity": {
            "xlink": xlink_identity,
            "xlib": xlib_identity,
            "objdump": objdump_identity,
            "IAR_object_manifest_sha256": graph_report["identity"][
                "object_manifest_sha256"
            ],
            "final_d43": graph_report["identity"]["final_d43"],
        },
        "synthetic_link_contract": {
            "output_format": "intel-extended",
            "processor": "msp430",
            "code_placement": "CODE=0x10000..0xEFFFF",
            "data_placement": "DATA16_Z/DATA16_C/CSTACK/DATA16_AN=0x0200..0xFFFF",
            "synthetic_external_count": len(selector.EXTERNAL_DEFINITIONS),
            "synthetic_externals_have_implementations": False,
            "synthetic_addresses_are_original_physical_addresses": False,
        },
        "objects": objects,
        "register_abi": {
            "R12_on_entry": "command byte; passed unchanged to SPI_COMMAND",
            "R13_on_entry": "source byte pointer; copied to R10",
            "R14_on_entry": "unsigned byte count; copied to R11",
            "R8": "loop counter initialized to zero",
            "loop_pretest": "R8 unsigned-below R11; zero count sends no data bytes",
            "loop_body": "load byte at R10 into R12, call SPI_DATA, increment R10 and R8",
            "command_helper_calls_per_invocation": 1,
            "data_helper_calls_per_invocation": "exactly R14 unsigned iterations",
            "C_prototype_recovered_exactly": False,
            "why_not_exact_C_prototype": (
                "machine ABI proves register roles and byte consumption but does not "
                "preserve a complete source-level declaration or const qualifier"
            ),
        },
        "sender_dataflow_adjudication": {
            "complete_generic_sender_instruction_contract_pinned": True,
            "complete_SPI_DATA_machine_body_hash_pinned": True,
            "source_byte_loaded_once_per_counted_iteration": True,
            "source_pointer_increment_bytes": 1,
            "loop_counter_increment_per_byte": 1,
            "only_generic_sender_loop_bound": "unsigned R8 below caller-supplied R11",
            "data_value_controls_generic_sender_loop_or_termination": False,
            "eleven_or_eighty_eight_byte_record_stride_present": False,
            "NOT_XOR_RBIT_REV_or_byte_complement_in_generic_sender_present": False,
            "SPI_DATA_copies_R12_low_byte_before_serialization": True,
            "SPI_DATA_serialized_bit_count": 8,
            "SPI_DATA_wire_bit_order": "D7_to_D0",
            "SPI_DATA_bit_selection": (
                "test current shift-register sign bit, drive SDA, then RLA for next bit"
            ),
            "SPI_DATA_bitwise_complement_before_wire_present": False,
            "MCU_sender_side_fixed_length_original_byte_order_proven": True,
            "controller_internal_decode_or_complement_proven": False,
            "FF_or_zero_terminator_semantics_proven": False,
        },
        "cross_object_and_function_equivalence": {
            "root_only_links_compared": 4,
            "unique_function_body_sha256": sorted(linked_function_hashes),
            "unique_root_only_image_sha256": sorted(linked_image_hashes),
            "EPD_Load_LUT_const_equals_EPD_Load_LUT_machine_body": True,
            "E2801_equals_E2802_machine_body": True,
            "const_name_changes_machine_access_path": False,
        },
        "consumer_adjudication": {
            **consumer_scan,
            "official_external_table_scan": external_table_scan,
            "current_final_d43_direct_project_r43_inputs": final_inputs,
            "E2801_or_E2802_is_current_final_d43_direct_input": False,
            "generic_helper_is_active_runtime_upload": False,
            "active_legacy_upload_uses_EPD_Load_LUT": True,
            "active_legacy_upload_uses_EPD_Load_LUT_const": False,
        },
        "DATA0_DATA1_adjudication": {
            "both_root_only_const_links_include_DATA0": False,
            "both_root_only_const_links_include_DATA1": False,
            "both_all_other_PUBLIC_links_need_const_helper": False,
            "const_helper_has_embedded_global_array_selection": False,
            "const_helper_can_send_caller_supplied_constant_storage": True,
            "caller_supplying_DATA0_or_DATA1_found": False,
            "DATA0_or_DATA1_contents_are_function_ABI": False,
        },
        "evidence_boundaries": {
            "PUBLIC_symbol_is_not_a_consumer": True,
            "forced_root_is_not_a_natural_reference": True,
            "generic_pointer_sender_is_not_a_global_array_binding": True,
            "const_in_function_name_is_not_machine_enforced_constness": True,
            "three_UBROF11_PUBLIC_EXTERN_tables_remain_XLIB_version_bounded": True,
            "paired_direct_call_scan_still_covers_all_29_objects": True,
            "legacy_objects_are_not_current_SPD1657_firmware": True,
            "current_800_byte_wrapper_ABI_proven": False,
            "current_dual_controller_loading_contract_proven": False,
            "phase_or_electrical_field_semantics_proven": False,
            "controller_internal_decode_or_active_low_encoding_proven": False,
            "authorizes_live_hardware_action": False,
        },
        "adjudication": {
            "verdict": (
                "LEGACY_CONST_AND_MUTABLE_LUT_HELPERS_ARE_IDENTICAL_THREE_REGISTER_"
                "GENERIC_SENDERS_CONST_HELPER_HAS_NO_OBSERVED_CONSUMER_OR_DATA_ARRAY_BINDING"
            ),
            "why": (
                "Official XLIB exposes both PUBLIC entries. Official XLINK and pinned "
                "objdump recover the same complete 32-byte command/pointer/count loop "
                "for both functions in both objects. Root-only links need neither "
                "DATA0 nor DATA1; all other PUBLIC roots leave EPD_Load_LUT_const "
                "NOT NEEDED, whereas Upload_Temperature_LUT naturally retains "
                "EPD_Load_LUT. The 29-object paired relocation scan finds no const "
                "consumer. This closes the helper ABI only, not the current waveform "
                "payload or panel safety contract."
            ),
        },
    }
    report["integrity"] = {
        "canonical_encoding": "UTF-8 sorted-key compact JSON excluding integrity",
        "canonical_sha256": _sha256(_canonical_bytes(report)),
    }
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlink", type=Path, required=True)
    parser.add_argument("--xlib", type=Path, required=True)
    parser.add_argument("--objdump", type=Path, required=True)
    parser.add_argument("--iar-root", type=Path, default=graph.DEFAULT_IAR_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = build_report(
            args.xlink,
            args.xlib,
            args.objdump,
            args.iar_root,
        )
        indent = None if args.compact else 2
        payload = (
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=indent) + "\n"
        ).encode("utf-8")
        if args.output is None:
            sys.stdout.buffer.write(payload)
        else:
            write_new_bytes_durable(args.output, payload)
    except (
        OSError,
        subprocess.SubprocessError,
        UnicodeError,
        LoadLutConstAbiAuditError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
