#!/usr/bin/env python3
"""Audit the legacy IAR DATA0/DATA1 constants and upload compatibility.

The two delivered UBROF10 objects retain public ``DATA0`` and ``DATA1``
entries.  Earlier byte extraction could identify section 0x14/0x15 content,
but could not bind those convenient names to the sections or establish
whether any executable path referenced them.  This audit closes that narrow
gap with identity-pinned official XLIB/XLINK output:

* XLIB fixes the ordered PUBLIC/EXTERN inventories and producer metadata.
* XLINK binds DATA0/DATA1 to DATA16_C segment parts 20/21 and their extents.
* A second link roots every other PUBLIC entry.  DATA0 and DATA1 remain
  ``NOT NEEDED`` while every segment part except those two and CSTACK is
  included, which is direct negative relocation/reachability evidence for
  the exact objects.
* Object content is compared using lengths, SHA-256 values, FF counts, and
  88-byte structural-record geometry only.  Raw LUT bytes are never emitted.

The result is legacy compatibility evidence, not an SPD1657 waveform ABI,
phase/electrical interpretation, live payload, or hardware authorization.
No serial, device-network, flashing, reset, refresh, token, or claim path is
implemented here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from host.application.durable_io import write_new_bytes_durable
from tools import mf1750_iar_project_config_chain_audit as project_chain
from tools import mf1750_iar_r43_cross_object_graph as graph
from tools import mf1750_iar_temperature_selector_audit as selector
from tools import mf1750_iar_xlib_external_index_audit as xlib_audit


KIND = "mf1750-iar-data0-data1-compatibility-audit"
SCHEMA_VERSION = 1

XLINK_VERSION_BANNER = selector.XLINK_VERSION_BANNER
XLIB_VERSION_BANNER = xlib_audit.VERSION_BANNER
EXPECTED_XLINK = selector.EXPECTED_XLINK
EXPECTED_XLIB = xlib_audit.EXPECTED_XLIB

CODE_PLACEMENT = selector.CODE_PLACEMENT
DATA_PLACEMENT = selector.DATA_PLACEMENT
EXTERNAL_DEFINITIONS = selector.EXTERNAL_DEFINITIONS

ARRAY_NAMES = ("DATA0", "DATA1")
FF_704_SHA256 = "24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f"
FF_88_SHA256 = "fc351643198ac4ec4e78649c99ad06b4cd45b554005990cdc70e520b49dd9bf0"

OBJECTS: dict[str, dict[str, Any]] = {
    "E2801": {
        "filename": "E2801.r43",
        "size_bytes": 315_632,
        "sha256": "404b950ea65b754a335b90be24683281ebee9dab52e362fd6d49170b4b8a38a3",
        "ubrof_version_byte": 10,
        "compiler_version": "5.30.1.20284",
        "target": "430X",
        "embedded_source": (
            "D:\\E2801\\Firmware_BX\\20200527_E2801_BX_V0_0_1 - "
            "OTP Test - VDG_HDG - 34pin\\E2801.c"
        ),
        "embedded_source_occurrences": 1_139,
        "xlib_module_date": "30/Jun/2020",
        "xlib_module_crc16": "40AE",
        "entry_count": 50,
        "entry_table_sha256": "3ba430450952a909340975bece17439bf6f286108839c2d0dd98eca2ed82f660",
        "external_count": 11,
        "external_table_sha256": "ea38135f911e56966412d0bf5383d2c04df005dfdecec4453eecfce79f6eab1b",
        "all_other_public_roots": 48,
        "reachable_link_code_bytes": 5_604,
        "reachable_link_data_bytes": 2_585,
        "segment_part_count": 51,
        "array_root_module_map_sha256": (
            "9c4cf89933be0421406f9332b2ca1dc71c40b5388d0dd4d4ef4d6317e1fab3c7"
        ),
        "all_other_roots_module_map_sha256": (
            "de47a3ad0f0d0192e11d9055d00d1288084a3f1e88990266f7b2c679a5dc0e4a"
        ),
        "arrays": {
            "DATA0": {
                "section_id": 0x14,
                "marker_offset": 0x519E,
                "encoded_end_offset": 0x5D62,
                "next_section_id": 0x15,
                "decoded_bytes": 1_503,
                "decoded_sha256": "eafe51e741f2e0922a2404abcc016473a203e9824bf91fd550f74ee6e05b8bc5",
            },
            "DATA1": {
                "section_id": 0x15,
                "marker_offset": 0x5D62,
                "encoded_end_offset": 0x62E8,
                "next_section_id": 0x18,
                "decoded_bytes": 704,
                "decoded_sha256": "6dbd5a232419da637084683867933a7f60ce06d28a5034136d0f0efae3015e6a",
            },
        },
    },
    "E2802": {
        "filename": "E2802.r43",
        "size_bytes": 328_062,
        "sha256": "19fb74c05444880ea6a403d697307e47a874998b5529ee84dd0592ecae16c9ce",
        "ubrof_version_byte": 10,
        "compiler_version": "5.30.1.20284",
        "target": "430X",
        "embedded_source": (
            "D:\\E2802\\20200923_3_inch\\20200807_E2802_V0_0_4 - "
            "for verification\\E2802.c"
        ),
        "embedded_source_occurrences": 1_236,
        "xlib_module_date": "23/Sep/2020",
        "xlib_module_crc16": "A3BC",
        "entry_count": 49,
        "entry_table_sha256": "6a48fc442a1f4a1b35bca5d6131a541524e34d21b4e7c310058b83a28179218f",
        "external_count": 11,
        "external_table_sha256": "ea38135f911e56966412d0bf5383d2c04df005dfdecec4453eecfce79f6eab1b",
        "all_other_public_roots": 47,
        "reachable_link_code_bytes": 6_228,
        "reachable_link_data_bytes": 2_585,
        "segment_part_count": 50,
        "array_root_module_map_sha256": (
            "21a7beb1a945a41bdd46d3671fa81be668d6c2ebcfb369723679766b7091d131"
        ),
        "all_other_roots_module_map_sha256": (
            "0368ad535401d7e185f730a009ce0e3b1bc60fbcaa08f07f7a337122da5b5ecc"
        ),
        "arrays": {
            "DATA0": {
                "section_id": 0x14,
                "marker_offset": 0x53D0,
                "encoded_end_offset": 0x5F94,
                "next_section_id": 0x15,
                "decoded_bytes": 1_503,
                "decoded_sha256": "eafe51e741f2e0922a2404abcc016473a203e9824bf91fd550f74ee6e05b8bc5",
            },
            "DATA1": {
                "section_id": 0x15,
                "marker_offset": 0x5F94,
                "encoded_end_offset": 0x651A,
                "next_section_id": 0x18,
                "decoded_bytes": 704,
                "decoded_sha256": "6dbd5a232419da637084683867933a7f60ce06d28a5034136d0f0efae3015e6a",
            },
        },
    },
}

MODULE_RE = re.compile(r"^\s*\d+\.\s+Pgm\s+(?P<name>\S+)\s*$")
DATE_RE = re.compile(
    r"^\s*(?P<date>\d{2}/[A-Za-z]{3}/\d{4})\s+\d+\.\s+Pgm\s+(?P<name>\S+)\s*$"
)
CRC_RE = re.compile(r"^\s*(?P<crc>[0-9A-F]{4})\s+\d+\.\s+Pgm\s+(?P<name>\S+)\s*$")
SEGMENT_PART_RE = re.compile(r"^\s*Segment part (?P<part>\d+)\.(?P<tail>.*)$")
SPAN_RE = re.compile(
    r"^\s*Relative segment, address: (?P<start>[0-9A-F]+) - "
    r"(?P<end>[0-9A-F]+) \(0x(?P<bytes>[0-9a-f]+) bytes\), align: "
    r"(?P<align>\d+)\s*$"
)
ENTRY_RE = re.compile(
    r"^\s*(?P<name>DATA0|DATA1)\s+(?P<address>[0-9A-F]*)"
    r"(?:\s+(?P<ref_by>.*?))?\s*$"
)


class DataCompatibilityAuditError(RuntimeError):
    """An identity, official-tool, map, or content invariant changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DataCompatibilityAuditError(message)


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


def _section_marker(section_id: int) -> bytes:
    return bytes((0xC7, section_id, 0, 0, 0, 0))


def _pin_xlink(path: Path) -> dict[str, Any]:
    _require(path.is_file(), f"XLINK executable is missing: {path}")
    payload = path.read_bytes()
    _require(
        len(payload) == int(EXPECTED_XLINK["size_bytes"]),
        "XLINK size mismatch",
    )
    digest = _sha256(payload)
    _require(digest == EXPECTED_XLINK["sha256"], "XLINK SHA-256 mismatch")
    completed = subprocess.run(
        [str(path)],
        check=False,
        capture_output=True,
        timeout=30,
    )
    output = (completed.stdout + completed.stderr).decode("cp1252")
    _require(completed.returncode == 0, "XLINK version probe failed")
    _require(XLINK_VERSION_BANNER in output, "XLINK version banner changed")
    return {
        "filename": path.name,
        "version": selector.XLINK_VERSION,
        "size_bytes": len(payload),
        "sha256": digest,
    }


def _pin_xlib(path: Path) -> dict[str, Any]:
    try:
        return xlib_audit._pin_xlib(path)
    except xlib_audit.XlibAuditError as error:
        raise DataCompatibilityAuditError(str(error)) from error


def _pin_object(path: Path, contract: dict[str, Any]) -> bytes:
    _require(path.is_file(), f"object is missing: {path}")
    payload = path.read_bytes()
    _require(len(payload) == contract["size_bytes"], f"{path.name} size changed")
    _require(_sha256(payload) == contract["sha256"], f"{path.name} SHA changed")
    _require(payload[:2] == b"\x01\x0a", f"{path.name} is not pinned UBROF10")
    compiler = str(contract["compiler_version"]).encode("ascii")
    target = str(contract["target"]).encode("ascii")
    source = str(contract["embedded_source"]).encode("ascii")
    _require(payload.count(compiler) == 1, f"{path.name} compiler token changed")
    _require(payload.count(target) == 1, f"{path.name} target token changed")
    _require(
        payload.count(source) == contract["embedded_source_occurrences"],
        f"{path.name} embedded source lineage changed",
    )
    return payload


def _extract_tagged_array(
    payload: bytes,
    *,
    label: str,
    contract: dict[str, Any],
) -> bytes:
    section_id = int(contract["section_id"])
    marker_offset = int(contract["marker_offset"])
    marker = _section_marker(section_id)
    _require(
        payload[marker_offset : marker_offset + len(marker)] == marker,
        f"{label} section marker changed",
    )
    cursor = marker_offset + len(marker)
    decoded = bytearray()
    while cursor + 1 < len(payload) and payload[cursor] == 0x36:
        decoded.append(payload[cursor + 1])
        cursor += 2
    result = bytes(decoded)
    _require(cursor == contract["encoded_end_offset"], f"{label} end changed")
    _require(len(result) == contract["decoded_bytes"], f"{label} length changed")
    _require(_sha256(result) == contract["decoded_sha256"], f"{label} SHA changed")
    next_marker = _section_marker(int(contract["next_section_id"]))
    _require(
        payload[cursor : cursor + len(next_marker)] == next_marker,
        f"{label} next section changed",
    )
    return result


def _byte_metadata(payload: bytes) -> dict[str, Any]:
    return {
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "ff_count": payload.count(0xFF),
        "non_ff_count": len(payload) - payload.count(0xFF),
        "unique_byte_count": len(set(payload)),
        "all_ff": bool(payload) and all(value == 0xFF for value in payload),
        "raw_bytes_emitted": False,
    }


def _structural_records(payload: bytes, *, prefix_bytes: int) -> dict[str, Any]:
    _require(0 <= prefix_bytes <= len(payload), "invalid structural prefix")
    body = payload[prefix_bytes:]
    _require(len(body) % 88 == 0, "structural body is not a multiple of 88")
    rows = [body[index : index + 88] for index in range(0, len(body), 88)]
    row_hashes = [_sha256(row) for row in rows]
    all_ff_indices = [
        index for index, digest in enumerate(row_hashes) if digest == FF_88_SHA256
    ]
    non_ff_indices = [
        index for index in range(len(rows)) if index not in all_ff_indices
    ]
    return {
        "prefix_bytes": prefix_bytes,
        "record_width_bytes": 88,
        "record_count": len(rows),
        "record_sha256": row_hashes,
        "all_ff_record_indices": all_ff_indices,
        "non_all_ff_record_indices": non_ff_indices,
        "record_semantics_proven": False,
        "category_phase_or_electrical_semantics_proven": False,
    }


def build_content_comparison(iar_root: Path = graph.DEFAULT_IAR_ROOT) -> dict[str, Any]:
    """Return identity-pinned array metadata without invoking external tools."""

    object_dir = iar_root / graph.OBJECT_DIR_REL
    arrays_by_object: dict[str, dict[str, bytes]] = {}
    object_metadata: dict[str, Any] = {}
    for name, contract in OBJECTS.items():
        path = object_dir / str(contract["filename"])
        payload = _pin_object(path, contract)
        arrays = {
            label: _extract_tagged_array(
                payload,
                label=f"{name}.{label}",
                contract=contract["arrays"][label],
            )
            for label in ARRAY_NAMES
        }
        arrays_by_object[name] = arrays
        object_metadata[name] = {
            "relative_path": path.relative_to(graph.REPO_ROOT).as_posix(),
            "size_bytes": len(payload),
            "sha256": _sha256(payload),
            "ubrof_version_byte": payload[1],
            "compiler": f"IAR MSP430 {contract['compiler_version']}",
            "target": contract["target"],
            "embedded_source": contract["embedded_source"],
            "embedded_source_record_occurrences": contract[
                "embedded_source_occurrences"
            ],
        }

    e1 = arrays_by_object["E2801"]
    e2 = arrays_by_object["E2802"]
    _require(e1["DATA0"] == e2["DATA0"], "E2801/E2802 DATA0 changed")
    _require(e1["DATA1"] == e2["DATA1"], "E2801/E2802 DATA1 changed")

    data0 = e1["DATA0"]
    data0_first = data0[:799]
    data0_second = data0[799:]
    data1 = e1["DATA1"]
    generated_ff704 = b"\xff" * 704

    _require(len(data0) == 799 + 704, "DATA0 arithmetic geometry changed")
    _require(len(data0_first) == 799, "DATA0 prefix length changed")
    _require(len(data0_second) == 704, "DATA0 suffix length changed")
    _require(data0_second == generated_ff704, "DATA0 suffix is no longer FF704")
    _require(_sha256(generated_ff704) == FF_704_SHA256, "FF704 hash changed")
    _require(data1 != generated_ff704, "DATA1 unexpectedly became FF704")

    return {
        "objects": object_metadata,
        "cross_object_content_identity": {
            "whole_object_bytes_equal": False,
            "DATA0_bytes_equal": True,
            "DATA1_bytes_equal": True,
            "DATA0_first_799_bytes_equal": True,
            "DATA0_last_704_bytes_equal": True,
        },
        "content": {
            "DATA0_whole": {
                **_byte_metadata(data0),
                "geometry": _structural_records(data0, prefix_bytes=7),
            },
            "DATA0_first_799": {
                **_byte_metadata(data0_first),
                "geometry": _structural_records(data0_first, prefix_bytes=7),
                "boundary_equation": "799 = 7 + 9*88",
            },
            "DATA0_last_704": {
                **_byte_metadata(data0_second),
                "geometry": _structural_records(data0_second, prefix_bytes=0),
                "boundary_equation": "704 = 8*88",
            },
            "DATA1_whole": {
                **_byte_metadata(data1),
                "geometry": _structural_records(data1, prefix_bytes=0),
                "boundary_equation": "704 = 8*88",
            },
            "runtime_generated_FF704": {
                **_byte_metadata(generated_ff704),
                "geometry": _structural_records(generated_ff704, prefix_bytes=0),
                "origin": "legacy Upload_Temperature_LUT immediate-0xFF loop",
                "stored_array_source": False,
            },
        },
        "equality_matrix": {
            "DATA0_equals_first799_concatenated_with_generated_FF704": (
                data0 == data0_first + generated_ff704
            ),
            "DATA0_last704_equals_runtime_generated_FF704": (
                data0_second == generated_ff704
            ),
            "DATA1_equals_DATA0_last704": data1 == data0_second,
            "DATA1_equals_runtime_generated_FF704": data1 == generated_ff704,
        },
    }


def _run_xlib_metadata(xlib_path: Path, object_path: Path) -> dict[str, Any]:
    try:
        externals = xlib_audit._run_xlib_list(
            xlib_path,
            object_path,
            command="LIST-EXTERNALS",
            expected_kind="Ext",
        )
        entries = xlib_audit._run_xlib_list(
            xlib_path,
            object_path,
            command="LIST-ENTRIES",
            expected_kind="Ent",
        )
    except xlib_audit.XlibAuditError as error:
        raise DataCompatibilityAuditError(str(error)) from error
    _require(externals["status"] == "PARSED", "XLIB external list failed")
    _require(entries["status"] == "PARSED", "XLIB entry list failed")

    with tempfile.TemporaryDirectory(prefix="mf1750-xlib-data-meta-") as temp_name:
        temp_dir = Path(temp_name)
        object_copy = temp_dir / object_path.name
        shutil.copyfile(object_path, object_copy)
        date_path = temp_dir / "date.txt"
        crc_path = temp_dir / "crc.txt"
        commands = (
            "ON-ERROR-EXIT\r\n"
            f'LIST-DATE-STAMPS "{object_copy}" "{date_path}"\r\n'
            f'LIST-CRC "{object_copy}" "{crc_path}"\r\n'
            "EXIT\r\n"
        )
        completed = subprocess.run(
            [str(xlib_path)],
            input=commands.encode("ascii"),
            check=False,
            capture_output=True,
            timeout=30,
        )
        combined = (completed.stdout + completed.stderr).decode("cp1252")
        _require(completed.returncode == 0, "XLIB date/CRC commands failed")
        _require(XLIB_VERSION_BANNER in combined, "XLIB process banner changed")
        _require(date_path.is_file() and crc_path.is_file(), "XLIB metadata missing")
        date_text = date_path.read_text("cp1252")
        crc_text = crc_path.read_text("cp1252")

    date_rows = [
        match.groupdict()
        for line in date_text.splitlines()
        if (match := DATE_RE.match(line)) is not None
    ]
    crc_rows = [
        match.groupdict()
        for line in crc_text.splitlines()
        if (match := CRC_RE.match(line)) is not None
    ]
    _require(len(date_rows) == 1, "XLIB module date inventory changed")
    _require(len(crc_rows) == 1, "XLIB module CRC inventory changed")
    _require(date_rows[0]["name"] == object_path.stem, "XLIB date module changed")
    _require(crc_rows[0]["name"] == object_path.stem, "XLIB CRC module changed")

    return {
        "module": object_path.stem,
        "entries": list(entries["symbols"]),
        "entry_table_sha256": entries["table_sha256"],
        "externals": list(externals["symbols"]),
        "external_table_sha256": externals["table_sha256"],
        "module_date": date_rows[0]["date"],
        "module_crc16": crc_rows[0]["crc"],
    }


def _module_map_projection(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    starts = [index for index, line in enumerate(lines) if "MODULE MAP" in line]
    ends = [
        index for index, line in enumerate(lines) if "END OF CROSS REFERENCE" in line
    ]
    _require(len(starts) == 1 and len(ends) == 1, "XLINK module-map bounds changed")
    _require(starts[0] < ends[0], "XLINK module-map order changed")
    projection = lines[starts[0] : ends[0] + 1]
    projection = [
        (
            re.sub(
                r"^(\s*FILE NAME\s*:)\s+.*$",
                r"\1 <IDENTITY_PINNED_ASCII_TEMP_OBJECT>",
                line,
            )
            if re.match(r"^\s*FILE NAME\s*:", line)
            else line
        )
        for line in projection
    ]
    return "\n".join(projection) + "\n"


def parse_xlink_module_map(payload: bytes) -> dict[str, Any]:
    """Parse only segment/ref metadata from one official XLINK map."""

    text = payload.decode("cp1252")
    _require(XLINK_VERSION_BANNER in text, "XLINK map banner changed")
    projection = _module_map_projection(text)
    lines = text.replace("\r\n", "\n").split("\n")

    parts: list[dict[str, Any]] = []
    target_rows: dict[str, dict[str, Any]] = {}
    part_line_indices: list[int] = []
    for index, line in enumerate(lines):
        if SEGMENT_PART_RE.match(line):
            part_line_indices.append(index)
    _require(part_line_indices, "XLINK map contains no segment parts")

    for ordinal, index in enumerate(part_line_indices):
        match = SEGMENT_PART_RE.match(lines[index])
        assert match is not None
        part = int(match.group("part"))
        tail = match.group("tail").strip()
        needed = "NOT NEEDED" not in tail

        prior = index - 1
        span_match = SPAN_RE.match(lines[prior]) if prior >= 0 else None
        if span_match is not None:
            segment_index = prior - 1
            span = {
                "start": _hex(int(span_match.group("start"), 16)),
                "end_inclusive": _hex(int(span_match.group("end"), 16)),
                "bytes": int(span_match.group("bytes"), 16),
                "alignment_power": int(span_match.group("align")),
            }
        else:
            segment_index = prior
            span = None
        _require(segment_index >= 0, "XLINK segment name missing")
        segment = lines[segment_index].strip()
        _require(bool(segment), "XLINK segment name is empty")

        end = (
            part_line_indices[ordinal + 1]
            if ordinal + 1 < len(part_line_indices)
            else len(lines)
        )
        block = lines[index:end]
        entries: list[dict[str, Any]] = []
        for block_line in block:
            entry_match = ENTRY_RE.match(block_line)
            if entry_match is None:
                continue
            name = entry_match.group("name")
            address_text = entry_match.group("address") or ""
            ref_by = (entry_match.group("ref_by") or "").strip()
            row = {
                "name": name,
                "address": None if not address_text else _hex(int(address_text, 16)),
                "ref_by": [] if not ref_by else [ref_by],
            }
            entries.append(row)
            _require(name not in target_rows, f"duplicate XLINK entry {name}")
            target_rows[name] = {
                "segment": segment,
                "segment_part": part,
                "needed": needed,
                "span": span,
                **row,
            }
        parts.append(
            {
                "segment": segment,
                "segment_part": part,
                "needed": needed,
                "root": "ROOT" in tail,
                "span": span,
                "target_entries": entries,
            }
        )

    def memory_count(kind: str) -> int:
        match = re.search(rf"^\s*([0-9 ]+) bytes of {kind} memory", text, re.MULTILINE)
        return 0 if match is None else int(match.group(1).replace(" ", ""))

    absolute_match = re.search(r"\(\+\s*([0-9 ]+) absolute\s*\)", text)
    errors = re.findall(r"^Errors:\s*(\S+)", text, re.MULTILINE)
    warnings = re.findall(r"^Warnings:\s*(\S+)", text, re.MULTILINE)
    _require(errors == ["none"], "XLINK map contains errors")
    _require(len(warnings) == 1, "XLINK warning summary changed")

    return {
        "module_map_projection_sha256": _sha256(projection.encode("cp1252")),
        "segment_part_count": len(parts),
        "unique_segment_part_count": len({int(row["segment_part"]) for row in parts}),
        "included_segment_parts": sum(bool(row["needed"]) for row in parts),
        "not_needed_segment_parts": [
            {
                "segment": row["segment"],
                "segment_part": row["segment_part"],
            }
            for row in parts
            if not row["needed"]
        ],
        "target_entries": target_rows,
        "memory_summary": {
            "code_bytes": memory_count("CODE"),
            "data_bytes": memory_count("DATA"),
            "absolute_symbols": (
                0
                if absolute_match is None
                else int(absolute_match.group(1).replace(" ", ""))
            ),
        },
        "errors": "none",
        "warnings": warnings[0],
    }


def _run_xlink_map(
    xlink_path: Path,
    object_path: Path,
    *,
    roots: list[str],
) -> dict[str, Any]:
    _require(bool(roots), "XLINK root list is empty")
    _require(len(roots) == len(set(roots)), "XLINK root list has duplicates")
    _require(all("\r" not in root and "\n" not in root for root in roots), "bad root")
    with tempfile.TemporaryDirectory(prefix="mf1750-xlink-data-map-") as temp_name:
        temp_dir = Path(temp_name)
        object_copy = temp_dir / object_path.name
        output_path = temp_dir / "linked.hex"
        map_path = temp_dir / "linked.map"
        shutil.copyfile(object_path, object_copy)
        arguments = [
            str(xlink_path),
            "-Fintel-extended",
            "-o",
            str(output_path),
            "-cmsp430",
            CODE_PLACEMENT,
            DATA_PLACEMENT,
            *(f"-D{name}=0x{address:X}" for name, address in EXTERNAL_DEFINITIONS),
            f"-g{','.join(roots)}",
            "-xemi",
            "-l",
            str(map_path),
            str(object_copy),
        ]
        completed = subprocess.run(
            arguments,
            check=False,
            capture_output=True,
            timeout=30,
        )
        combined = (completed.stdout + completed.stderr).decode("cp1252")
        _require(completed.returncode == 0, f"XLINK map link failed: {combined!r}")
        _require(XLINK_VERSION_BANNER in combined, "XLINK process banner changed")
        _require(map_path.is_file(), "XLINK map was not generated")
        parsed = parse_xlink_module_map(map_path.read_bytes())
    parsed["forced_public_roots"] = len(roots)
    parsed["synthetic_external_definitions"] = len(EXTERNAL_DEFINITIONS)
    parsed["temporary_outputs_discarded"] = True
    return parsed


def _validate_tool_rows(
    name: str,
    contract: dict[str, Any],
    xlib_row: dict[str, Any],
    array_link: dict[str, Any],
    reachability_link: dict[str, Any],
) -> None:
    _require(xlib_row["module"] == name, f"{name} XLIB module changed")
    _require(len(xlib_row["entries"]) == contract["entry_count"], "entry count")
    _require(
        xlib_row["entry_table_sha256"] == contract["entry_table_sha256"],
        f"{name} entry table changed",
    )
    _require(len(xlib_row["externals"]) == contract["external_count"], "external count")
    _require(
        xlib_row["external_table_sha256"] == contract["external_table_sha256"],
        f"{name} external table changed",
    )
    _require(xlib_row["module_date"] == contract["xlib_module_date"], "module date")
    _require(xlib_row["module_crc16"] == contract["xlib_module_crc16"], "module CRC")
    _require(set(ARRAY_NAMES).issubset(xlib_row["entries"]), "array PUBLICs missing")

    _require(
        array_link["segment_part_count"] == contract["segment_part_count"], "part count"
    )
    _require(
        array_link["module_map_projection_sha256"]
        == contract["array_root_module_map_sha256"],
        f"{name} array-root module map changed",
    )
    _require(array_link["memory_summary"]["data_bytes"] == 2_207, "array root data")
    _require(array_link["memory_summary"]["code_bytes"] == 0, "array root code")
    _require(array_link["memory_summary"]["absolute_symbols"] == 11, "absolute count")
    _require(array_link["warnings"] == "1", "array-root warning changed")
    for label, part, byte_count in (("DATA0", 20, 1_503), ("DATA1", 21, 704)):
        row = array_link["target_entries"].get(label)
        _require(row is not None, f"{name} {label} map binding missing")
        _require(row["segment"] == "DATA16_C", f"{name} {label} segment changed")
        _require(row["segment_part"] == part, f"{name} {label} part changed")
        _require(row["needed"], f"{name} {label} array root not included")
        _require(row["span"]["bytes"] == byte_count, f"{name} {label} span changed")
        _require(
            row["ref_by"] == ["Absolute parts (?ABS_ENTRY_MOD)"],
            f"{name} {label} gained a natural reference",
        )

    _require(
        reachability_link["forced_public_roots"] == contract["all_other_public_roots"],
        f"{name} public-root count changed",
    )
    _require(
        reachability_link["segment_part_count"] == contract["segment_part_count"],
        f"{name} reachability part count changed",
    )
    _require(
        reachability_link["module_map_projection_sha256"]
        == contract["all_other_roots_module_map_sha256"],
        f"{name} all-other-roots module map changed",
    )
    _require(
        reachability_link["included_segment_parts"]
        == contract["segment_part_count"] - 3,
        f"{name} included part count changed",
    )
    expected_not_needed = {
        ("CSTACK", 7),
        ("DATA16_C", 20),
        ("DATA16_C", 21),
    }
    actual_not_needed = {
        (row["segment"], int(row["segment_part"]))
        for row in reachability_link["not_needed_segment_parts"]
    }
    _require(actual_not_needed == expected_not_needed, f"{name} reachability changed")
    for label in ARRAY_NAMES:
        row = reachability_link["target_entries"].get(label)
        _require(row is not None, f"{name} {label} negative binding missing")
        _require(not row["needed"], f"{name} {label} became reachable")
        _require(row["address"] is None, f"{name} {label} got an address")
        _require(row["ref_by"] == [], f"{name} {label} gained a reference")
    summary = reachability_link["memory_summary"]
    _require(
        summary["code_bytes"] == contract["reachable_link_code_bytes"], "code bytes"
    )
    _require(
        summary["data_bytes"] == contract["reachable_link_data_bytes"], "data bytes"
    )
    _require(summary["absolute_symbols"] == 11, "absolute symbols")
    _require(reachability_link["warnings"] == "none", "reachability warning")


def _project_lineage(iar_root: Path) -> dict[str, Any]:
    report = project_chain.build_report(iar_root)
    rows = report["producer_and_provider_ownership"]
    result: dict[str, Any] = {}
    for name in ("E2801.r43", "E2802.r43"):
        row = rows[name]
        _require(not row["dependency_output_inventory_member"], f"{name} entered DEP")
        _require(
            not row["final_d43_direct_project_input"], f"{name} entered final link"
        )
        _require(not row["project_declared_source_family"], f"{name} entered project")
        _require(
            row["provider_status"] == "ORPHAN_OBJECT_PROVIDER_CANDIDATE_NOT_LINKED",
            f"{name} provider status changed",
        )
        result[name.removesuffix(".r43")] = {
            "embedded_producer_source": row["producer_source_embedded_in_object"],
            "project_declared_source_family": row["project_declared_source_family"],
            "dependency_output_inventory_member": row[
                "dependency_output_inventory_member"
            ],
            "final_d43_direct_project_input": row["final_d43_direct_project_input"],
            "provider_status": row["provider_status"],
            "provider_object_proven_for_current_final_upload": row[
                "provider_object_proven_for_current_final_upload"
            ],
        }
    adjudication = report["adjudication"]
    _require(not adjudication["E2801_or_E2802_directly_linked"], "final link changed")
    _require(
        not adjudication["current_Debug_Upload_Temperature_LUT_present"],
        "upload appeared",
    )
    return {
        "project_chain_report_canonical_sha256": report["report_canonical_sha256"],
        "delivered_project_declared_sources": report["project"][
            "project_level_sources"
        ],
        "objects": result,
        "current_Debug_E2801_or_E2802_directly_linked": adjudication[
            "E2801_or_E2802_directly_linked"
        ],
        "current_Debug_Upload_Temperature_LUT_present": adjudication[
            "current_Debug_Upload_Temperature_LUT_present"
        ],
        "delivered_configuration_verdict": adjudication["verdict"],
    }


def build_report(
    xlink_path: Path,
    xlib_path: Path,
    iar_root: Path = graph.DEFAULT_IAR_ROOT,
) -> dict[str, Any]:
    """Run the deterministic metadata-only compatibility audit."""

    xlink_identity = _pin_xlink(xlink_path)
    xlib_identity = _pin_xlib(xlib_path)
    content = build_content_comparison(iar_root)
    object_dir = iar_root / graph.OBJECT_DIR_REL

    object_tool_evidence: dict[str, Any] = {}
    entries_by_object: dict[str, list[str]] = {}
    externals_by_object: dict[str, list[str]] = {}
    for name, contract in OBJECTS.items():
        object_path = object_dir / str(contract["filename"])
        xlib_row = _run_xlib_metadata(xlib_path, object_path)
        entries = list(xlib_row["entries"])
        array_link = _run_xlink_map(
            xlink_path,
            object_path,
            roots=list(ARRAY_NAMES),
        )
        reachability_link = _run_xlink_map(
            xlink_path,
            object_path,
            roots=[entry for entry in entries if entry not in ARRAY_NAMES],
        )
        _validate_tool_rows(name, contract, xlib_row, array_link, reachability_link)
        entries_by_object[name] = entries
        externals_by_object[name] = list(xlib_row["externals"])
        object_tool_evidence[name] = {
            "xlib": {
                "module_date": xlib_row["module_date"],
                "module_crc16": xlib_row["module_crc16"],
                "PUBLIC_entry_count": len(entries),
                "PUBLIC_entry_table_sha256": xlib_row["entry_table_sha256"],
                "EXTERN_count": len(xlib_row["externals"]),
                "EXTERN_table_sha256": xlib_row["external_table_sha256"],
                "DATA0_and_DATA1_are_PUBLIC_entries": True,
            },
            "array_identity_link": {
                "forced_roots": list(ARRAY_NAMES),
                "module_map_projection_sha256": array_link[
                    "module_map_projection_sha256"
                ],
                "segment_part_count": array_link["segment_part_count"],
                "memory_summary": array_link["memory_summary"],
                "bindings": {
                    label: array_link["target_entries"][label] for label in ARRAY_NAMES
                },
                "natural_reference_sites": [],
                "only_ref_by_is_synthetic_force_root": True,
            },
            "all_other_public_roots_link": {
                "forced_public_root_count": reachability_link["forced_public_roots"],
                "module_map_projection_sha256": reachability_link[
                    "module_map_projection_sha256"
                ],
                "segment_part_count": reachability_link["segment_part_count"],
                "included_segment_parts": reachability_link["included_segment_parts"],
                "not_needed_segment_parts": reachability_link[
                    "not_needed_segment_parts"
                ],
                "memory_summary": reachability_link["memory_summary"],
                "DATA0": reachability_link["target_entries"]["DATA0"],
                "DATA1": reachability_link["target_entries"]["DATA1"],
                "natural_reference_sites": [],
                "all_non_array_non_stack_segment_parts_included": True,
            },
        }

    _require(
        set(entries_by_object["E2801"]) - set(entries_by_object["E2802"]) == {"for_AX"},
        "E2801/E2802 PUBLIC difference changed",
    )
    _require(
        not set(entries_by_object["E2802"]) - set(entries_by_object["E2801"]),
        "E2802 gained a PUBLIC absent from E2801",
    )
    _require(
        externals_by_object["E2801"] == externals_by_object["E2802"],
        "E2801/E2802 EXTERN tables diverged",
    )

    lineage = _project_lineage(iar_root)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "scope": {
            "offline_read_only": True,
            "source_objects": 2,
            "temporary_ascii_path_copies_only": True,
            "source_objects_modified": False,
            "hardware_accessed": False,
            "serial_or_COM8_accessed": False,
            "device_network_accessed": False,
            "firmware_written_or_flashed": False,
            "reset_requested": False,
            "visible_refreshes": 0,
            "live_token_or_claim_generated": False,
            "raw_object_code_emitted": False,
            "raw_LUT_or_waveform_bytes_emitted": False,
            "live_payload_generated": False,
        },
        "identity": {
            "xlink": xlink_identity,
            "xlib": xlib_identity,
            "objects": content["objects"],
        },
        "tool_contract": {
            "xlib_commands": [
                "LIST-ENTRIES",
                "LIST-EXTERNALS",
                "LIST-DATE-STAMPS",
                "LIST-CRC",
            ],
            "xlink_output_format": "intel-extended temporary output discarded",
            "xlink_cross_reference": "-xemi",
            "xlink_code_placement": CODE_PLACEMENT,
            "xlink_data_placement": DATA_PLACEMENT,
            "synthetic_external_definition_count": len(EXTERNAL_DEFINITIONS),
            "synthetic_externals_are_not_provider_implementations": True,
            "array_identity_roots": list(ARRAY_NAMES),
            "reachability_roots": "every XLIB PUBLIC except DATA0 and DATA1",
        },
        "object_tool_evidence": object_tool_evidence,
        "content_comparison": {
            "cross_object_content_identity": content["cross_object_content_identity"],
            "content": content["content"],
            "equality_matrix": content["equality_matrix"],
        },
        "producer_and_configuration_lineage": {
            **lineage,
            "same_compiler_version": True,
            "same_target_family": True,
            "same_UBROF_version": True,
            "same_EXTERNS_in_same_order": True,
            "PUBLIC_set_difference_E2801_minus_E2802": ["for_AX"],
            "PUBLIC_set_difference_E2802_minus_E2801": [],
            "whole_objects_byte_identical": False,
            "module_dates_identical": False,
            "module_CRC16_identical": False,
            "embedded_source_paths_identical": False,
            "identical_arrays_most_likely_reused_constants": (
                "inference_only_not_producer_copy_proof"
            ),
        },
        "upload_source_adjudication": {
            "legacy_active_upload_R20": {
                "command": "0x20",
                "source": "dataBuff+4 after external ReadData",
                "bytes": 799,
                "DATA0_or_DATA1_reference": False,
            },
            "legacy_active_upload_R21": {
                "command": "0x21",
                "source": "immediate 0xFF generated in a 704-iteration loop",
                "bytes": 704,
                "DATA0_or_DATA1_reference": False,
            },
            "DATA0_storage_and_length_direct_object_evidence": True,
            "DATA1_storage_and_length_direct_object_evidence": True,
            "DATA0_internal_799_symbol_or_subobject_boundary_declared": False,
            "DATA0_last704_exactly_matches_active_generated_FF704": True,
            "DATA0_1503_is_more_than_only_799_plus_704_arithmetic": True,
            "why_more_than_arithmetic": (
                "official XLINK proves a 1503-byte DATA0 object; metadata extraction "
                "proves its exact last 704 bytes are FF and align to eight 88-byte "
                "structural records, matching the independently generated active R21"
            ),
            "DATA0_or_DATA1_used_by_active_upload": False,
            "DATA0_or_DATA1_reachable_from_any_other_object_PUBLIC": False,
            "DATA0_or_DATA1_default_role_proven": False,
            "DATA0_or_DATA1_factory_role_proven": False,
            "best_bounded_classification": (
                "DIRECT_INITIALIZED_CONSTANT_AND_STRUCTURAL_CORROBORATION;_"
                "UNREFERENCED_IN_THE_TWO_OBJECT_CLOSURES_AND_DELIVERED_CONFIG;_"
                "NOT_THE_ACTIVE_UPLOAD_SOURCE"
            ),
        },
        "evidence_boundaries": {
            "array_name_to_UBROF_section_binding_proven": True,
            "array_extents_proven_by_official_XLINK": True,
            "all_natural_same_object_reference_sites": [],
            "unpublished_external_consumer_excluded": False,
            "current_SPD1657_800_byte_ABI_proven": False,
            "current_535_or_704_byte_ABI_proven": False,
            "category_phase_or_electrical_fields_proven": False,
            "88_byte_record_semantics_proven": False,
            "dual_controller_loading_or_commit_proven": False,
            "factory_OTP_or_white_recovery_proven": False,
            "authorizes_live_hardware_action": False,
            "generates_live_payload": False,
        },
        "verdict": (
            "DATA0[1503] is direct initialized-object evidence and its exact "
            "DATA0[799:1503] == FF*704 equality is structural corroboration, not "
            "mere arithmetic.  However, 799 is not a declared subobject boundary, "
            "DATA0/DATA1 have zero natural references in either complete object "
            "closure, and the delivered project does not link either provider.  "
            "The active legacy upload independently sends dataBuff+4/799 then "
            "generated-FF/704; it does not load either retained constant."
        ),
    }
    report["integrity"] = {
        "canonical_encoding": (
            "UTF-8 sorted-key compact JSON excluding integrity; no raw LUT bytes"
        ),
        "canonical_sha256": _sha256(_canonical_bytes(report)),
    }
    return report


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlink", type=Path, required=True)
    parser.add_argument("--xlib", type=Path, required=True)
    parser.add_argument("--iar-root", type=Path, default=graph.DEFAULT_IAR_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = build_report(
            args.xlink.resolve(),
            args.xlib.resolve(),
            args.iar_root.resolve(),
        )
        payload = (
            json.dumps(
                report,
                ensure_ascii=False,
                sort_keys=True,
                indent=None if args.compact else 2,
            )
            + "\n"
        ).encode("utf-8")
        if args.output is None:
            sys.stdout.buffer.write(payload)
        else:
            write_new_bytes_durable(args.output.resolve(), payload)
    except (
        DataCompatibilityAuditError,
        OSError,
        subprocess.SubprocessError,
        project_chain.ProjectChainError,
    ) as error:
        print(f"DATA0/DATA1 compatibility audit failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
