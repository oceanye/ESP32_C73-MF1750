#!/usr/bin/env python3
"""Audit IAR E2801/E2802 type, symbol, and line metadata with official XLIB.

This offline helper runs only ``LIST-OBJECT-CODE`` from the identity-pinned
official IAR Universal Librarian 6.1.3.56 against temporary copies of the two
delivered UBROF10 objects.  It parses a deliberately bounded metadata surface:

* array dimensions and their named symbol bindings;
* selected function prototypes;
* ``Upload_Temperature_LUT`` local symbols and source ranges; and
* internal-section relocation operands targeting ``DATA0``/``DATA1``.

The transient XLIB list contains object-code records and is deleted before the
tool returns.  The emitted JSON contains metadata only: no object bytes, LUT
bytes, waveform bytes, payloads, serial/device-network operations, or hardware
authorization.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Final

from host.application.durable_io import write_new_bytes_durable
from tools import mf1750_iar_data0_data1_compatibility_audit as compatibility
from tools import mf1750_iar_r43_cross_object_graph as graph
from tools import mf1750_iar_xlib_external_index_audit as xlib_audit


KIND: Final = "mf1750-iar-xlib-type-symbol-audit"
SCHEMA_VERSION: Final = 1

XLIB_VERSION: Final = xlib_audit.XLIB_VERSION
XLIB_VERSION_BANNER: Final = xlib_audit.VERSION_BANNER
EXPECTED_XLIB: Final = xlib_audit.EXPECTED_XLIB

OBJECTS: Final[dict[str, dict[str, Any]]] = {
    name: {
        "filename": row["filename"],
        "size_bytes": row["size_bytes"],
        "sha256": row["sha256"],
        "ubrof_version_byte": row["ubrof_version_byte"],
        "compiler_version": row["compiler_version"],
        "target": row["target"],
        "embedded_source": row["embedded_source"],
        "source_file": f"{name}.c",
    }
    for name, row in compatibility.OBJECTS.items()
}

# The identifiers are part of the exact two-object contract.  The audit also
# scans for extra ARRAY1 records and rejects them, so this is not a cherry-picked
# dimension inventory.
EXPECTED_ARRAY_TYPES: Final[dict[str, dict[str, Any]]] = {
    "0077": {
        "storage_type_id": "0076",
        "element_type": "unsigned char",
        "elements": 1_503,
        "const": True,
        "bindings": ["DATA0"],
    },
    "0079": {
        "storage_type_id": "0078",
        "element_type": "unsigned char",
        "elements": 704,
        "const": True,
        "bindings": ["DATA1"],
    },
    "00A9": {
        "storage_type_id": "00A8",
        "element_type": "unsigned char",
        "elements": 2_560,
        "const": False,
        "bindings": ["dataBuff"],
    },
    "00AB": {
        "storage_type_id": "00AA",
        "element_type": "unsigned char",
        "elements": 8,
        "const": False,
        "bindings": ["dataBuff2"],
    },
    "00B2": {
        "storage_type_id": "00B1",
        "element_type": "unsigned char",
        "elements": 2,
        "const": False,
        "bindings": ["BUF"],
    },
    "00B4": {
        "storage_type_id": "00B3",
        "element_type": "unsigned char",
        "elements": 1_024,
        "const": False,
        "bindings": ["GetTempBuf", "lut_otp"],
    },
    "00B6": {
        "storage_type_id": "00B5",
        "element_type": "unsigned char",
        "elements": 3,
        "const": False,
        "bindings": ["chk_code"],
    },
}

EXPECTED_FUNCTIONS: Final[dict[str, dict[str, Any]]] = {
    "ReadData": {
        "linkage": "EXTERNAL",
        "symbol_type_id": "0066",
        "function_type_id": "0067",
        "return": "void",
        "parameters": ["uint8_t", "uint16_t", "uint8_t *", "uint16_t"],
        "source_filename": "SPI.h",
        "source_line": 100,
    },
    "EPD_Load_LUT": {
        "linkage": "PUBLIC_REL",
        "symbol_type_id": "007E",
        "function_type_id": "007F",
        "return": "void",
        "parameters": ["uint16_t", "uint8_t *", "uint16_t"],
        "source_filename": None,
        "source_line": {"E2801": 462, "E2802": 339},
    },
    "EPD_Load_LUT_const": {
        "linkage": "PUBLIC_REL",
        "symbol_type_id": "0080",
        "function_type_id": "0081",
        "return": "void",
        "parameters": ["uint16_t", "const uint8_t *", "uint16_t"],
        "source_filename": None,
        "source_line": {"E2801": 451, "E2802": 328},
    },
    "Upload_Temperature_LUT": {
        "linkage": "PUBLIC_REL",
        "symbol_type_id": "0087",
        "function_type_id": "0088",
        "return": "uint8_t",
        "parameters": [],
        "source_filename": None,
        "source_line": {"E2801": 487, "E2802": 364},
    },
}

EXPECTED_UPLOAD_LOCALS: Final[list[tuple[str, str]]] = [
    ("a", "00B0"),
    ("status", "0069"),
    ("TemperatureAddress", "0082"),
    ("i", "0082"),
    ("TemperatureAddress_23_16", "0069"),
    ("TemperatureAddress_15_0", "00A7"),
    ("BUF", "00B1"),
    ("LUT_idx", "00B0"),
]

EXPECTED_SOURCE_FILE_ROWS: Final[dict[str, dict[int, tuple[str, int]]]] = {
    "E2801": {
        2: ("E2801.c", 2_026),
        4: ("LUT.h", 146),
        5: ("SPI.h", 104),
    },
    "E2802": {
        2: ("E2802.c", 2_144),
        4: ("LUT.h", 146),
        5: ("SPI.h", 104),
    },
}

BASE_WIDTH_NAMES: Final[dict[str, str]] = {
    "void": "void",
    "unsigned char": "uint8_t",
    "unsigned int": "uint16_t",
    "unsigned long": "uint32_t",
    "int": "int16_t",
}

RECORD_RE = re.compile(r"^\s+(?P<tag>t_[A-Za-z0-9_]+)\s*(?P<body>.*)$")
TYPE_RE = re.compile(r"^\[(?P<id>[0-9A-Fa-f]+)\]\s+(?P<body>.*)$")
ARRAY_RE = re.compile(
    r"^ARRAY1\s+(?P<element>.+?)\s+(?P<count>[0-9A-Fa-f]{8})\s+"
    r"(?P<size>[0-9A-Fa-f]{8})$"
)
SYMBOL_NAME_RE = re.compile(r"N(?P<id>[0-9A-Fa-f]+)\"(?P<name>[^\"]+)\"")
TYPE_REF_RE = re.compile(r"\[(?P<id>[0-9A-Fa-f]+)\]")
SOURCE_FILE_RE = re.compile(
    r"^\s*(?P<index>\d+):\s+\d+\s+\d{2}:\d{2}:\d{2}\s+"
    r"\d{2}/[A-Za-z]{3}/\d{4}\s+(?P<lines>\d+)\s+li\s+"
    r"(?P<directory>\d+)\s+'(?P<filename>[^']+)'\s*$"
)
SUB_DEF_FUNC_RE = re.compile(
    r"F-INDEX\s*=\s*(?P<function_index>[0-9A-Fa-f]+)\s+"
    r"FILE\s+(?P<file_index>[0-9A-Fa-f]+)\s+"
    r"LINE\s+(?P<line>[0-9A-Fa-f]+)\s+FDEF\s+(?P<fdef>[0-9A-Fa-f]+)"
)
PUSH_REL_RE = re.compile(r"^\((?P<section>[0-9A-Fa-f]+)\)\s+(?P<addend>[0-9A-Fa-f]+)$")
ORG_REL_RE = re.compile(r"^\((?P<section>[0-9A-Fa-f]+)\)\s+[0-9A-Fa-f]+$")


class IarTypeSymbolAuditError(RuntimeError):
    """An input identity, official-tool result, or metadata invariant changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise IarTypeSymbolAuditError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pin_xlib(path: Path) -> dict[str, Any]:
    try:
        return xlib_audit._pin_xlib(path)
    except xlib_audit.XlibAuditError as error:
        raise IarTypeSymbolAuditError(str(error)) from error


def _pin_object(path: Path, contract: dict[str, Any]) -> bytes:
    _require(path.is_file(), f"object is missing: {path}")
    payload = path.read_bytes()
    _require(
        len(payload) == int(contract["size_bytes"]),
        f"{path.name} size mismatch",
    )
    digest = _sha256(payload)
    _require(
        digest == contract["sha256"],
        f"{path.name} SHA-256 mismatch: expected {contract['sha256']}, got {digest}",
    )
    _require(payload[:2] == b"\x01\x0a", f"{path.name} is not pinned UBROF10")
    return payload


def _run_list_object_code(xlib_path: Path, object_path: Path) -> bytes:
    """Run the sole allowed XLIB operation and return its transient list."""

    with tempfile.TemporaryDirectory(prefix="mf1750-iar-type-") as temp_dir:
        temporary_root = Path(temp_dir)
        object_copy = temporary_root / object_path.name
        output_path = temporary_root / "list.txt"
        shutil.copyfile(object_path, object_copy)
        command_stream = (
            "ON-ERROR-EXIT\r\n"
            f'LIST-OBJECT-CODE "{object_copy}" "{output_path}"\r\n'
            "EXIT\r\n"
        ).encode("ascii")
        completed = subprocess.run(
            [str(xlib_path)],
            input=command_stream,
            check=False,
            capture_output=True,
            timeout=30,
        )
        combined = completed.stdout + completed.stderr
        _require(
            XLIB_VERSION_BANNER.encode("ascii") in combined,
            "XLIB process version banner changed",
        )
        _require(
            completed.returncode == 0,
            "LIST-OBJECT-CODE failed with return code "
            f"{completed.returncode}: {combined.decode('cp1252').strip()!r}",
        )
        _require(output_path.is_file(), "LIST-OBJECT-CODE did not create a list")
        payload = output_path.read_bytes()
        _require(payload, "LIST-OBJECT-CODE created an empty list")
        return payload


def _records(lines: list[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line_number, line in enumerate(lines, start=1):
        match = RECORD_RE.match(line)
        if match is not None:
            if current is not None:
                result.append(current)
            current = {
                "tag": match.group("tag"),
                "parts": [match.group("body").rstrip()],
                "list_line": line_number,
            }
            continue
        if current is not None:
            current["parts"].append(line.strip())
    if current is not None:
        result.append(current)
    return result


def _joined(record: dict[str, Any]) -> str:
    return "".join(str(part).strip() for part in record["parts"])


def _parse_source_range(record: dict[str, Any]) -> dict[str, Any]:
    _require(record["tag"] == "t_source_range1", "expected t_source_range1")
    text = _joined(record)
    _require(text.startswith("[") and text.endswith("]"), "invalid source range")
    inner = text[1:-1]
    relative = re.fullmatch(
        r"(?P<start_line>\d+):(?P<start_column>\d+)-"
        r"(?:(?P<end_line>\d+):)?(?P<end_column>\d+)",
        inner,
    )
    path: str | None = None
    if relative is None:
        absolute = re.fullmatch(
            r"(?P<path>.*)\\(?P<start_line>\d+):(?P<start_column>\d+)-"
            r"(?:(?P<end_line>\d+):)?(?P<end_column>\d+)",
            inner,
        )
        _require(absolute is not None, f"unsupported source range: {text}")
        match = absolute
        path = str(match.group("path"))
    else:
        match = relative
    start_line = int(match.group("start_line"))
    end_line_text = match.group("end_line")
    return {
        "path": path,
        "start_line": start_line,
        "start_column": int(match.group("start_column")),
        "end_line": start_line if end_line_text is None else int(end_line_text),
        "end_column": int(match.group("end_column")),
        "xlib_list_line": int(record["list_line"]),
    }


def _parse_source_files(lines: list[str]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for line in lines:
        match = SOURCE_FILE_RE.match(line)
        if match is None:
            continue
        index = int(match.group("index"))
        _require(index not in result, f"duplicate source-file index {index}")
        result[index] = {
            "filename": match.group("filename"),
            "declared_lines": int(match.group("lines")),
            "directory_index": int(match.group("directory")),
        }
    _require(len(result) == 10, "source-file table no longer contains ten rows")
    return result


def _parse_types(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        if record["tag"] != "t_type":
            continue
        head = str(record["parts"][0]).strip()
        match = TYPE_RE.match(head)
        _require(match is not None, f"unsupported t_type head: {head}")
        type_id = match.group("id").upper().zfill(4)
        body = match.group("body")
        _require(type_id not in result, f"duplicate type id {type_id}")
        row: dict[str, Any] = {
            "type_id": type_id,
            "head": body,
            "list_line": int(record["list_line"]),
        }
        array = ARRAY_RE.fullmatch(body)
        if array is not None:
            count = int(array.group("count"), 16)
            size = int(array.group("size"), 16)
            _require(count == size, f"array {type_id} count/size diverged")
            row.update(
                {
                    "kind": "array",
                    "element_type": array.group("element"),
                    "elements": count,
                    "encoded_size": size,
                }
            )
        elif body.startswith("FUNCTION "):
            function = re.fullmatch(r"FUNCTION\s+(.+?)\s+(ANSI|K&R)", body)
            _require(function is not None, f"unsupported function type {body}")
            parameters: list[str] = []
            parts = [str(part).strip() for part in record["parts"][1:]]
            if "Parameter types:" in parts:
                marker = parts.index("Parameter types:")
                parameters = [part for part in parts[marker + 1 :] if part]
            row.update(
                {
                    "kind": "function",
                    "return_type": function.group(1),
                    "calling_style": function.group(2),
                    "parameter_types": parameters,
                }
            )
        elif body.startswith("FUNC_ATTR "):
            target = TYPE_REF_RE.search(body)
            _require(target is not None, f"FUNC_ATTR {type_id} lacks target")
            row.update(
                {"kind": "function_attribute", "target": target.group("id").upper()}
            )
        elif body.startswith("POINTER "):
            target = TYPE_REF_RE.search(body)
            _require(target is not None, f"POINTER {type_id} lacks target")
            row.update({"kind": "pointer", "target": target.group("id").upper()})
        elif body.startswith("DATA_ATTR "):
            target = TYPE_REF_RE.search(body)
            qualifiers = []
            if "const" in _joined(record):
                qualifiers.append("const")
            if "volatile" in _joined(record):
                qualifiers.append("volatile")
            if target is not None:
                row.update(
                    {
                        "kind": "data_attribute",
                        "target": target.group("id").upper(),
                        "qualifiers": qualifiers,
                    }
                )
            else:
                base = re.search(
                    r"DATA_ATTR\s+(?:__data16\s+)?(.+?)\s+GEN\s+", _joined(record)
                )
                _require(base is not None, f"DATA_ATTR {type_id} lacks base")
                row.update(
                    {
                        "kind": "data_attribute",
                        "base": base.group(1),
                        "qualifiers": qualifiers,
                    }
                )
        else:
            row["kind"] = "other"
        result[type_id] = row
    _require(len(result) == 83, f"expected 83 type records, got {len(result)}")
    return result


def _type_display(type_token: str, types: dict[str, dict[str, Any]]) -> str:
    if re.fullmatch(r"\[[0-9A-Fa-f]+\]", type_token):
        type_id = type_token[1:-1].upper().zfill(4)
        row = types[type_id]
        kind = row["kind"]
        if kind == "pointer":
            return f"{_type_display('[' + row['target'] + ']', types)} *"
        if kind == "data_attribute":
            if "target" in row:
                value = _type_display(f"[{row['target']}]", types)
            else:
                value = BASE_WIDTH_NAMES.get(str(row["base"]), str(row["base"]))
            if "const" in row["qualifiers"]:
                value = f"const {value}"
            if "volatile" in row["qualifiers"]:
                value = f"volatile {value}"
            return value
        if kind == "array":
            element = BASE_WIDTH_NAMES.get(
                str(row["element_type"]), str(row["element_type"])
            )
            return f"{element}[{row['elements']}]"
        raise IarTypeSymbolAuditError(f"cannot display type {type_id}: {kind}")
    return BASE_WIDTH_NAMES.get(type_token, type_token)


def _parse_symbol(record: dict[str, Any]) -> dict[str, Any] | None:
    _require(record["tag"] == "t_symbol_def2", "expected t_symbol_def2")
    text = _joined(record)
    name = SYMBOL_NAME_RE.search(text)
    if name is None:
        return None
    head = str(record["parts"][0]).strip()
    storage_match = re.match(r"(?P<storage>[A-Z0-9_?]+)", head)
    _require(storage_match is not None, f"symbol storage is missing: {head}")
    after_name = text[name.end() :]
    type_ref = TYPE_REF_RE.search(after_name)
    section = re.search(r"\((?P<section>[0-9A-Fa-f]+)\)", head)
    return {
        "name_id": name.group("id").upper().zfill(4),
        "name": name.group("name"),
        "storage": storage_match.group("storage"),
        "section_id": None if section is None else int(section.group("section"), 16),
        "type_id": (
            None if type_ref is None else type_ref.group("id").upper().zfill(4)
        ),
        "list_line": int(record["list_line"]),
    }


def _annotate_symbols(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    block_stack: list[str] = []
    for index, record in enumerate(records):
        if record["tag"] == "t_block_begin3":
            name = SYMBOL_NAME_RE.search(_joined(record))
            _require(name is not None, "block begin lacks scoped name")
            block_stack.append(name.group("name"))
            continue
        if record["tag"] == "t_block_end":
            _require(bool(block_stack), "unbalanced t_block_end")
            block_stack.pop()
            continue
        if record["tag"] != "t_symbol_def2":
            continue
        symbol = _parse_symbol(record)
        if symbol is None:
            continue
        symbol["block_path"] = list(block_stack)
        previous = records[index - 1] if index > 0 else None
        following = records[index + 1] if index + 1 < len(records) else None
        symbol["preceding_source_range"] = (
            _parse_source_range(previous)
            if previous is not None and previous["tag"] == "t_source_range1"
            else None
        )
        symbol["following_source_range"] = (
            _parse_source_range(following)
            if following is not None and following["tag"] == "t_source_range1"
            else None
        )
        result.append(symbol)
    _require(not block_stack, "unbalanced t_block_begin3")
    return result


def _unique_symbol(
    symbols: list[dict[str, Any]],
    name: str,
    *,
    storage: str | None = None,
    direct_block: str | None = None,
) -> dict[str, Any]:
    matches = [row for row in symbols if row["name"] == name]
    if storage is not None:
        matches = [row for row in matches if row["storage"] == storage]
    if direct_block is not None:
        matches = [
            row
            for row in matches
            if row["block_path"] and row["block_path"][-1] == direct_block
        ]
    _require(len(matches) == 1, f"expected one {name} symbol, got {len(matches)}")
    return matches[0]


def _function_signature(
    symbol: dict[str, Any], types: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    symbol_type_id = str(symbol["type_id"])
    wrapper = types[symbol_type_id]
    _require(wrapper["kind"] == "function_attribute", "function wrapper changed")
    function_type_id = str(wrapper["target"])
    function = types[function_type_id]
    _require(function["kind"] == "function", "function type changed")
    return {
        "symbol_type_id": symbol_type_id,
        "function_type_id": function_type_id,
        "return": _type_display(str(function["return_type"]), types),
        "parameters": [
            _type_display(str(parameter), types)
            for parameter in function["parameter_types"]
        ],
        "xlib_spelling": {
            "return": function["return_type"],
            "parameters": list(function["parameter_types"]),
            "calling_style": function["calling_style"],
        },
    }


def _next_record(
    records: list[dict[str, Any]], start_line: int, tag: str, limit: int = 6
) -> dict[str, Any] | None:
    start_index = next(
        index for index, row in enumerate(records) if row["list_line"] == start_line
    )
    for record in records[start_index + 1 : start_index + 1 + limit]:
        if record["tag"] == tag:
            return record
    return None


def _block_range(records: list[dict[str, Any]], function_name: str) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if record["tag"] != "t_block_begin3":
            continue
        name = SYMBOL_NAME_RE.search(_joined(record))
        if name is None or name.group("name") != function_name:
            continue
        _require(index + 1 < len(records), f"{function_name} block is truncated")
        _require(
            records[index + 1]["tag"] == "t_source_range1",
            f"{function_name} block lacks source range",
        )
        matches.append(_parse_source_range(records[index + 1]))
    _require(len(matches) == 1, f"expected one {function_name} block")
    return matches[0]


def _function_evidence(
    object_name: str,
    records: list[dict[str, Any]],
    symbols: list[dict[str, Any]],
    types: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, expected in EXPECTED_FUNCTIONS.items():
        symbol = _unique_symbol(symbols, name, storage=str(expected["linkage"]))
        signature = _function_signature(symbol, types)
        _require(
            signature["symbol_type_id"] == expected["symbol_type_id"],
            f"{object_name} {name} symbol type changed",
        )
        _require(
            signature["function_type_id"] == expected["function_type_id"],
            f"{object_name} {name} function type changed",
        )
        _require(signature["return"] == expected["return"], f"{name} return changed")
        _require(
            signature["parameters"] == expected["parameters"],
            f"{object_name} {name} parameters changed",
        )
        source = symbol["following_source_range"]
        _require(source is not None, f"{object_name} {name} source range is missing")
        expected_line_value = expected["source_line"]
        expected_line = (
            int(expected_line_value[object_name])
            if isinstance(expected_line_value, dict)
            else int(expected_line_value)
        )
        _require(
            source["start_line"] == expected_line,
            f"{object_name} {name} source line changed",
        )
        if expected["source_filename"] is not None:
            _require(
                str(source["path"]).endswith(str(expected["source_filename"])),
                f"{object_name} {name} source file changed",
            )
        row: dict[str, Any] = {
            "linkage": symbol["storage"],
            "signature": signature,
            "declaration_or_definition_range": source,
        }
        if symbol["storage"] == "PUBLIC_REL":
            sub_def = _next_record(records, symbol["list_line"], "t_sub_def_func")
            _require(
                sub_def is not None, f"{object_name} {name} t_sub_def_func missing"
            )
            parsed = SUB_DEF_FUNC_RE.search(_joined(sub_def))
            _require(parsed is not None, f"{object_name} {name} t_sub_def_func changed")
            debug_line = int(parsed.group("line"), 16)
            _require(debug_line == expected_line, f"{object_name} {name} line mismatch")
            row["definition_metadata"] = {
                "function_index": int(parsed.group("function_index"), 16),
                "file_index": int(parsed.group("file_index"), 16),
                "line": debug_line,
                "fdef": f"0x{int(parsed.group('fdef'), 16):08X}",
            }
            row["body_range"] = _block_range(records, name)
        else:
            row["external_declaration_only"] = True
        result[name] = row
    return result


def _array_inventory(
    records: list[dict[str, Any]],
    symbols: list[dict[str, Any]],
    types: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    arrays = {key: row for key, row in types.items() if row["kind"] == "array"}
    _require(
        set(arrays) == set(EXPECTED_ARRAY_TYPES),
        f"ARRAY1 type inventory changed: {sorted(arrays)}",
    )
    result: list[dict[str, Any]] = []
    for array_type_id in sorted(arrays):
        expected = EXPECTED_ARRAY_TYPES[array_type_id]
        array = arrays[array_type_id]
        _require(
            array["element_type"] == expected["element_type"]
            and array["elements"] == expected["elements"],
            f"array type {array_type_id} changed",
        )
        storage_type_id = str(expected["storage_type_id"])
        storage_type = types[storage_type_id]
        _require(
            storage_type["kind"] == "data_attribute"
            and storage_type.get("target") == array_type_id,
            f"array storage wrapper {storage_type_id} changed",
        )
        is_const = "const" in storage_type["qualifiers"]
        _require(is_const is expected["const"], "array constness changed")
        bindings = [row for row in symbols if row["type_id"] == storage_type_id]
        binding_names = sorted(row["name"] for row in bindings)
        _require(
            binding_names == sorted(expected["bindings"]),
            f"array bindings changed for {array_type_id}: {binding_names}",
        )
        binding_rows: list[dict[str, Any]] = []
        for symbol in sorted(bindings, key=lambda row: str(row["name"]).casefold()):
            source = (
                symbol["following_source_range"]
                if symbol["storage"] == "PUBLIC_REL"
                else symbol["preceding_source_range"]
            )
            binding_rows.append(
                {
                    "name": symbol["name"],
                    "storage": symbol["storage"],
                    "section_id": (
                        None
                        if symbol["section_id"] is None
                        else f"0x{int(symbol['section_id']):04X}"
                    ),
                    "block_path": symbol["block_path"],
                    "source_range": source,
                }
            )
        result.append(
            {
                "array_type_id": array_type_id,
                "storage_type_id": storage_type_id,
                "element_type": array["element_type"],
                "element_bytes": 1,
                "elements": array["elements"],
                "bytes": array["encoded_size"],
                "const": is_const,
                "declaration": (
                    f"{'const ' if is_const else ''}unsigned char[{array['elements']}]"
                ),
                "bindings": binding_rows,
            }
        )
    return result


def _upload_locals(
    symbols: list[dict[str, Any]], types: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, expected_type in EXPECTED_UPLOAD_LOCALS:
        symbol = _unique_symbol(
            symbols,
            name,
            direct_block="Upload_Temperature_LUT",
        )
        _require(symbol["type_id"] == expected_type, f"upload local {name} changed")
        type_display = _type_display(f"[{expected_type}]", types)
        source = symbol["preceding_source_range"]
        rows.append(
            {
                "name": name,
                "storage": symbol["storage"],
                "type_id": expected_type,
                "normalized_type": type_display,
                "explicit_source_range": source,
                "source_range_status": (
                    "NOT_EMITTED_FOR_THIS_SYMBOL"
                    if source is None
                    else "DIRECT_XLIB_SOURCE_RANGE"
                ),
            }
        )
    _require(
        [row["name"] for row in rows] == [name for name, _ in EXPECTED_UPLOAD_LOCALS],
        "upload local order changed",
    )
    _require(rows[0]["explicit_source_range"] is None, "a gained a direct line range")
    _require(
        all(row["explicit_source_range"] is not None for row in rows[1:]),
        "an upload local lost its source range",
    )
    return rows


def _relocation_inventory(
    records: list[dict[str, Any]], symbols: list[dict[str, Any]]
) -> dict[str, Any]:
    counts: Counter[int] = Counter()
    definition_origins: Counter[int] = Counter()
    for record in records:
        if record["tag"] == "t_push_rel":
            match = PUSH_REL_RE.fullmatch(str(record["parts"][0]).strip())
            _require(match is not None, "unsupported t_push_rel record")
            counts[int(match.group("section"), 16)] += 1
        elif record["tag"] == "t_org_rel1":
            match = ORG_REL_RE.fullmatch(str(record["parts"][0]).strip())
            _require(match is not None, "unsupported t_org_rel1 record")
            definition_origins[int(match.group("section"), 16)] += 1

    rows = [
        {"section_id": f"0x{section:04X}", "reference_operands": count}
        for section, count in sorted(counts.items())
    ]
    target_rows: dict[str, Any] = {}
    for name in ("DATA0", "DATA1"):
        symbol = _unique_symbol(symbols, name, storage="PUBLIC_REL")
        section = int(symbol["section_id"])
        _require(counts[section] == 0, f"{name} gained a t_push_rel reference")
        _require(
            definition_origins[section] == 1,
            f"{name} section definition-origin count changed",
        )
        target_rows[name] = {
            "section_id": f"0x{section:04X}",
            "t_push_rel_reference_operands": counts[section],
            "t_org_rel1_definition_origins": definition_origins[section],
        }
    return {
        "operand_family_scanned": "all t_push_rel records in official XLIB list",
        "t_push_rel_records": sum(counts.values()),
        "referenced_section_count": len(counts),
        "section_reference_count_projection_sha256": _sha256(_canonical_bytes(rows)),
        "targets": target_rows,
        "zero_same_object_section_references_to_both_arrays": True,
        "definition_origins_are_not_counted_as_references": True,
    }


def _source_file_projection(
    object_name: str, source_files: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    expected = EXPECTED_SOURCE_FILE_ROWS[object_name]
    for index, (filename, lines) in expected.items():
        _require(source_files[index]["filename"] == filename, "source file changed")
        _require(source_files[index]["declared_lines"] == lines, "line count changed")
    return [{"file_index": index, **source_files[index]} for index in sorted(expected)]


def _restore_pinned_producer_paths(value: Any, producer_directory: str) -> None:
    """Restore spaces that XLIB drops exactly at a wrapped path boundary.

    XLIB indents continuation lines but does not preserve a whitespace path
    character when the wrap occurs on that character.  The directory is
    independently present in the identity-pinned embedded producer path, while
    XLIB still supplies the basename and line/column range.  Never infer a new
    directory from the visually wrapped rendering.
    """

    if isinstance(value, list):
        for item in value:
            _restore_pinned_producer_paths(item, producer_directory)
        return
    if not isinstance(value, dict):
        return
    if {
        "path",
        "start_line",
        "start_column",
        "end_line",
        "end_column",
    }.issubset(value) and value["path"] is not None:
        rendered_path = str(value["path"])
        filename = rendered_path.rsplit("\\", 1)[-1]
        _require(bool(filename), "wrapped XLIB source basename is empty")
        value["path"] = f"{producer_directory}\\{filename}"
        value["path_identity_basis"] = (
            "pinned embedded producer directory plus XLIB source basename"
        )
        return
    for item in value.values():
        _restore_pinned_producer_paths(item, producer_directory)


def _parse_object_listing(
    object_name: str, payload: bytes, contract: dict[str, Any]
) -> dict[str, Any]:
    try:
        text = payload.decode("cp1252")
    except UnicodeDecodeError as error:
        raise IarTypeSymbolAuditError(f"XLIB list is not cp1252: {error}") from error
    _require(XLIB_VERSION_BANNER in text, "XLIB list version banner changed")
    _require(
        re.search(r"Command\s+= list-object-code", text) is not None,
        "XLIB operation heading changed",
    )
    lines = text.splitlines()
    records = _records(lines)
    types = _parse_types(records)
    symbols = _annotate_symbols(records)
    source_files = _parse_source_files(lines)

    functions = _function_evidence(object_name, records, symbols, types)
    arrays = _array_inventory(records, symbols, types)
    locals_rows = _upload_locals(symbols, types)
    relocations = _relocation_inventory(records, symbols)

    producer_directory, separator, producer_filename = str(
        contract["embedded_source"]
    ).rpartition("\\")
    _require(separator == "\\", "embedded producer path lost its directory")
    _require(
        producer_filename == contract["source_file"],
        "embedded producer source filename changed",
    )
    for metadata in (functions, arrays, locals_rows):
        _restore_pinned_producer_paths(metadata, producer_directory)

    upload_body = functions["Upload_Temperature_LUT"]["body_range"]
    expected_upload = (487, 563) if object_name == "E2801" else (364, 442)
    _require(
        (upload_body["start_line"], upload_body["end_line"]) == expected_upload,
        f"{object_name} upload body range changed",
    )

    type_projection = [
        {
            "type_id": type_id,
            "head": row["head"],
            "kind": row["kind"],
            "parameter_types": row.get("parameter_types"),
        }
        for type_id, row in sorted(types.items())
    ]
    selected_projection = {
        "arrays": arrays,
        "functions": functions,
        "upload_locals": locals_rows,
        "relocations": relocations,
    }
    return {
        "identity": {
            "relative_path": str(
                graph.IAR_ROOT_REL / graph.OBJECT_DIR_REL / str(contract["filename"])
            ).replace("\\", "/"),
            "size_bytes": contract["size_bytes"],
            "sha256": contract["sha256"],
            "ubrof_version_byte": contract["ubrof_version_byte"],
            "compiler_version": contract["compiler_version"],
            "target": contract["target"],
            "embedded_source": contract["embedded_source"],
        },
        "official_list_metadata": {
            "type_record_count": len(types),
            "array_type_record_count": len(arrays),
            "symbol_definition_record_count": sum(
                1 for record in records if record["tag"] == "t_symbol_def2"
            ),
            "source_range_record_count": sum(
                1 for record in records if record["tag"] == "t_source_range1"
            ),
            "block_begin_record_count": sum(
                1 for record in records if record["tag"] == "t_block_begin3"
            ),
            "selected_source_files": _source_file_projection(object_name, source_files),
            "normalized_type_projection_sha256": _sha256(
                _canonical_bytes(type_projection)
            ),
            "selected_metadata_projection_sha256": _sha256(
                _canonical_bytes(selected_projection)
            ),
        },
        "array_dimensions": arrays,
        "selected_function_types": functions,
        "upload_temperature_lut_locals": locals_rows,
        "array_relocation_references": relocations,
    }


def build_report(
    xlib_path: Path,
    iar_root: Path = graph.DEFAULT_IAR_ROOT,
    *,
    runner: Any = _run_list_object_code,
) -> dict[str, Any]:
    """Build the deterministic, metadata-only two-object report."""

    xlib_identity = _pin_xlib(xlib_path)
    object_dir = iar_root / graph.OBJECT_DIR_REL
    objects: dict[str, Any] = {}
    for name, contract in OBJECTS.items():
        object_path = object_dir / str(contract["filename"])
        _pin_object(object_path, contract)
        list_payload = runner(xlib_path, object_path)
        objects[name] = _parse_object_listing(name, list_payload, contract)

    e2801 = objects["E2801"]
    e2802 = objects["E2802"]
    _require(
        e2801["official_list_metadata"]["normalized_type_projection_sha256"]
        == e2802["official_list_metadata"]["normalized_type_projection_sha256"],
        "E2801/E2802 normalized type projections differ",
    )
    _require(
        [
            (row["declaration"], [binding["name"] for binding in row["bindings"]])
            for row in e2801["array_dimensions"]
        ]
        == [
            (row["declaration"], [binding["name"] for binding in row["bindings"]])
            for row in e2802["array_dimensions"]
        ],
        "E2801/E2802 array declarations differ",
    )
    for function_name in EXPECTED_FUNCTIONS:
        _require(
            e2801["selected_function_types"][function_name]["signature"]
            == e2802["selected_function_types"][function_name]["signature"],
            f"E2801/E2802 {function_name} signatures differ",
        )
    _require(
        [
            (row["name"], row["normalized_type"])
            for row in e2801["upload_temperature_lut_locals"]
        ]
        == [
            (row["name"], row["normalized_type"])
            for row in e2802["upload_temperature_lut_locals"]
        ],
        "E2801/E2802 upload locals differ",
    )

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "scope": {
            "offline_read_only": True,
            "source_objects": 2,
            "temporary_object_copies_only": True,
            "temporary_LIST_OBJECT_CODE_outputs_deleted": True,
            "source_objects_modified": False,
            "hardware_accessed": False,
            "serial_or_COM8_accessed": False,
            "device_network_accessed": False,
            "firmware_written_or_flashed": False,
            "reset_requested": False,
            "visible_refreshes": 0,
            "raw_object_code_emitted": False,
            "raw_LUT_waveform_or_payload_bytes_emitted": False,
            "live_token_or_claim_generated": False,
        },
        "identity": {
            "official_xlib": xlib_identity,
            "objects": {name: row["identity"] for name, row in objects.items()},
        },
        "official_tool_contract": {
            "executable_argv": ["<identity-pinned-xlib.exe>"],
            "stdin_lines_exact_template": [
                "ON-ERROR-EXIT",
                'LIST-OBJECT-CODE "<temporary-copy-of-E2801-or-E2802.r43>" '
                '"<temporary-list-output>"',
                "EXIT",
            ],
            "line_terminator": "CRLF",
            "operation": "LIST-OBJECT-CODE",
            "source_object_is_copied_before_tool_invocation": True,
            "list_output_is_transient_and_never_emitted": True,
            "parsed_metadata_families": [
                "t_type",
                "t_symbol_def2",
                "t_source_range1",
                "t_sub_def_func",
                "t_block_begin3/t_block_end",
                "t_push_rel",
                "t_org_rel1",
                "source-file table",
            ],
        },
        "objects": objects,
        "cross_object_adjudication": {
            "selected_normalized_type_projection_identical": True,
            "all_seven_array_type_dimensions_identical": True,
            "DATA0_type_is_const_unsigned_char_1503": True,
            "DATA1_type_is_const_unsigned_char_704": True,
            "dataBuff_type_is_unsigned_char_2560": True,
            "ReadData_signature_identical": True,
            "EPD_Load_LUT_signature_identical": True,
            "upload_local_name_and_type_sequence_identical": True,
            "DATA0_t_push_rel_references": {"E2801": 0, "E2802": 0},
            "DATA1_t_push_rel_references": {"E2801": 0, "E2802": 0},
            "array_constants_are_not_active_upload_sources": True,
        },
        "evidence_boundaries": {
            "directly_proves_declared_DATA0_1503_and_DATA1_704_types": True,
            "directly_proves_declared_dataBuff_2560_capacity": True,
            "directly_proves_selected_function_signatures": True,
            "directly_proves_selected_upload_local_types": True,
            "directly_proves_zero_same_object_t_push_rel_array_references": True,
            "DATA0_internal_799_subobject_or_field_boundary_proven": False,
            "current_800_byte_wrapper_ABI_proven": False,
            "category_phase_or_electrical_field_names_proven": False,
            "same_generation_final_link_provider_proven": False,
            "external_unpublished_consumer_excluded": False,
            "dual_controller_destination_or_commit_proven": False,
            "factory_OTP_or_white_recovery_contract_proven": False,
            "authorizes_live_hardware_action": False,
            "generates_runtime_waveform_payload": False,
        },
        "verdict": (
            "Official XLIB type metadata closes the prior capacity/type gap: the "
            "two exact legacy objects both declare DATA0 as const unsigned char[1503], "
            "DATA1 as const unsigned char[704], and dataBuff as unsigned char[2560]. "
            "It also fixes the selected function prototypes and upload-local types. "
            "Neither object contains a t_push_rel reference to the DATA0 or DATA1 "
            "section. These facts do not name a 799-byte subobject, explain the "
            "current 800-byte wrapper, bind category/phase/electrical fields, establish "
            "the final linked provider, or prove a dual-controller/recovery contract."
        ),
    }
    report["integrity"] = {
        "canonical_encoding": (
            "UTF-8 sorted-key compact JSON excluding integrity; metadata only"
        ),
        "canonical_sha256": _sha256(_canonical_bytes(report)),
    }
    return report


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlib", required=True, type=Path)
    parser.add_argument("--iar-root", type=Path, default=graph.DEFAULT_IAR_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = build_report(args.xlib.resolve(), args.iar_root.resolve())
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
    except (IarTypeSymbolAuditError, OSError, subprocess.SubprocessError) as error:
        print(f"IAR XLIB type/symbol audit failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
