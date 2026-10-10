#!/usr/bin/env python3
"""Prove the delivered IAR final-image provider chain without hardware access.

The audit invokes one identity-pinned, read-only XLIB operation against the
delivered absolute ``C2_Example.d43``.  It reconstructs the bytes described by
the decoded UBROF ``t_org (01)``/``t_abs_var`` records and compares them with
the delivered TI-TXT byte for byte.  It then resolves decoded call-frame and
direct-call records to establish the final main/EPD provider chain.

Separately delivered E2801/E2802 objects are inspected only as orphan legacy
candidates.  Their local upload edges are never promoted into the current
final image.  The report is metadata-only and has no serial, device-network,
flash, reset, refresh, or physical-action interface.
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
from typing import Any

from host.application.durable_io import write_new_bytes_durable
from tools import mf1750_iar_project_config_chain_audit as project_chain
from tools import mf1750_iar_r43_cross_object_graph as graph


KIND = "mf1750-iar-final-d43-provider-chain-audit"
SCHEMA_VERSION = 1
XLIB_VERSION = "6.1.3.56"
VERSION_BANNER = f"IAR Universal Librarian V{XLIB_VERSION}"

EXPECTED_XLIB = (
    550_912,
    "ea11101e1365065c5899dc1db644eb8d6f0ff769abc477119770355d98804284",
)

EXPECTED_FILES: dict[str, tuple[int, str]] = {
    "C2_Example.ewp": (
        82_056,
        "409e32ff9ecb6714efea2fd2478ce6fbf1821f55984989f01760d456bdb79582",
    ),
    "C2_Example.dep": (
        11_281,
        "8b59303fa9d7a0b1ce453b117009ef4b468e1cac81e8a615e30ea026aa7dbaeb",
    ),
    "Debug/Exe/C2_Example.d43": (
        39_332,
        "56e915d88b4b26ca29baaea766015e43d8f9ba222095650f9a1bebbe6c3906c0",
    ),
    "Debug/Exe/C2_Example.txt": (
        6_150,
        "593194d980f66852223a47493f788ea671335f47b4f1b5c9880d83b9a04ddb49",
    ),
    "Debug/Obj/DELAY.r43": (
        1_774,
        "82eaf1f5ae2ee28f7df7dafb7e9ecf8b46731d7f98784a4731d9b49f638c96da",
    ),
    "Debug/Obj/E6_73.r43": (
        109_582,
        "0f4d22c6d07f79d9ededffd50f155dc96d802b0e90bf908c30f2b85f1714ee2f",
    ),
    "Debug/Obj/main.r43": (
        29_684,
        "76ada9c8846226457ef74537a345ca1e057e8c11abc1002423424dfffd2640f4",
    ),
    "Debug/Obj/E2801.r43": (
        315_632,
        "404b950ea65b754a335b90be24683281ebee9dab52e362fd6d49170b4b8a38a3",
    ),
    "Debug/Obj/E2802.r43": (
        328_062,
        "19fb74c05444880ea6a403d697307e47a874998b5529ee84dd0592ecae16c9ce",
    ),
}

DIRECT_PROJECT_OBJECTS = ("DELAY.r43", "E6_73.r43", "main.r43")
DISPLAY_FUNCTIONS = (
    "EPD_Display_White",
    "EPD_Display_Black",
    "EPD_Display_Yellow",
    "EPD_Display_Red",
    "EPD_Display_Blue",
    "EPD_Display_Green",
)

EXPECTED_FUNCTIONS: dict[str, tuple[str, int, int]] = {
    "delay": ("DELAY", 0xA7BA, 0x0C),
    "EPD_Init": ("E6_73", 0xA00C, 0x17C),
    "EPD_Display_Red": ("E6_73", 0xA268, 0x80),
    "EPD_Display_Blue": ("E6_73", 0xA2E8, 0x80),
    "EPD_Display_Green": ("E6_73", 0xA368, 0x80),
    "EPD_Display_White": ("E6_73", 0xA3E8, 0x80),
    "EPD_Display_Yellow": ("E6_73", 0xA468, 0x80),
    "EPD_Display_Black": ("E6_73", 0xA4E8, 0x7E),
    "SPI_DATA": ("E6_73", 0xA566, 0x7C),
    "SPI_COMMAND": ("E6_73", 0xA5E2, 0x7C),
    "reset": ("E6_73", 0xA65E, 0x5A),
    "SetClockSystem_25MHz": ("main", 0xA6B8, 0x58),
    "SetVcoreUp": ("main", 0xA710, 0x56),
    "spi_9b_init": ("E6_73", 0xA766, 0x2A),
    "check_busy_high": ("E6_73", 0xA790, 0x16),
    "main": ("main", 0xA188, 0xE0),
}

EXPECTED_MAIN_CALLS = (
    (0xA190, "SetClockSystem_25MHz", 79),
    (0xA1EC, "spi_9b_init", 101),
    (0xA1F8, "delay", 104),
    (0xA208, "delay", 107),
    (0xA20C, "EPD_Init", 111),
    (0xA210, "EPD_Display_White", 114),
    (0xA218, "delay", 115),
    (0xA21C, "EPD_Display_Black", 116),
    (0xA224, "delay", 117),
    (0xA228, "EPD_Display_Red", 118),
    (0xA230, "delay", 119),
    (0xA234, "EPD_Display_Yellow", 120),
    (0xA23C, "delay", 121),
    (0xA240, "EPD_Display_Blue", 122),
    (0xA248, "delay", 123),
    (0xA24C, "EPD_Display_Green", 124),
    (0xA254, "delay", 125),
    (0xA258, "EPD_Display_White", 126),
)

SCOPED_NAME_RE = re.compile(r"^\s*t_scoped_name\s+(N[0-9A-Fa-f]+):\s+NAME\s+'([^']+)'")
MODULE_RE = re.compile(r"^\s*t_beg_(pgm|lib)\s+.*'([^']+)'\s*$")
END_RE = re.compile(r"^\s*t_end\s+")
ORG_RE = re.compile(r"^\s*t_org\s+\((\d+)\)\s+([0-9A-Fa-f]{8})")
ABS_VAR_RE = re.compile(r"^\s*t_abs_var\s+([0-9A-Fa-f]+)\s*$")
ABS_CONTINUATION_RE = re.compile(r"^\s{20,}([0-9A-Fa-f]+)\s*$")
PUBLIC_CODE_RE = re.compile(
    r"^\s*t_symbol_def2\s+PUBLIC_REL\s+\(0001\)\s+"
    r"([0-9A-Fa-f]{8})\s+(N[0-9A-Fa-f]+)"
)
LOCAL_DATA_RE = re.compile(
    r"^\s*t_symbol_def2\s+LOCAL_REL\s+\(0002\)\s+"
    r"([0-9A-Fa-f]{8})\s+(N[0-9A-Fa-f]+)"
)
FRAME_RE = re.compile(
    r"^\s*t_call_frame_info\s+.*TOT=0x([0-9A-Fa-f]+)\s+"
    r"FUNC=\s*(N[0-9A-Fa-f]+)"
)
DIRECT_TARGET_RE = re.compile(r"^\s*direct_call\s+(N[0-9A-Fa-f]+)")
DIRECT_EVENT_RE = re.compile(r"^\s*\d+\s+@0x([0-9A-Fa-f]+)\s+Direct call\(\[([0-9]+):")
MACRO_RE = re.compile(r"^\s*t_macro\s+'([^']+)'(?:\s+(.*?))?\s*$")


class FinalD43AuditError(RuntimeError):
    """An input identity or decoded final-image invariant changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FinalD43AuditError(message)


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
    return f"0x{value:04X}"


def _pin(path: Path, expected: tuple[int, str], label: str) -> bytes:
    _require(path.is_file(), f"{label} is missing: {path}")
    payload = path.read_bytes()
    _require(
        len(payload) == expected[0],
        f"{label} size mismatch: expected {expected[0]}, got {len(payload)}",
    )
    digest = _sha256(payload)
    _require(
        digest == expected[1],
        f"{label} SHA-256 mismatch: expected {expected[1]}, got {digest}",
    )
    return payload


def _pin_xlib(path: Path) -> dict[str, Any]:
    payload = _pin(path, EXPECTED_XLIB, "XLIB")
    return {
        "filename": path.name,
        "version": XLIB_VERSION,
        "size_bytes": len(payload),
        "sha256": _sha256(payload),
    }


def _run_xlib_list_object_code(xlib_path: Path, d43_path: Path) -> bytes:
    """Decode a copied final D43 with the one allowed read-only XLIB command."""

    with tempfile.TemporaryDirectory(prefix="mf1750-final-d43-") as temp_dir:
        object_copy = Path(temp_dir) / "C2_Example.d43"
        output_path = Path(temp_dir) / "object-code.txt"
        shutil.copyfile(d43_path, object_copy)
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
            VERSION_BANNER.encode("ascii") in combined,
            "XLIB process version banner changed",
        )
        _require(
            completed.returncode == 0,
            "LIST-OBJECT-CODE failed with return code "
            f"{completed.returncode}: {combined.decode('cp1252').strip()!r}",
        )
        _require(output_path.is_file(), "LIST-OBJECT-CODE did not create output")
        payload = output_path.read_bytes()
        _require(payload, "LIST-OBJECT-CODE created an empty output")
        return payload


def _parse_ti_txt(payload: bytes) -> dict[str, Any]:
    try:
        tokens = payload.decode("ascii").split()
    except UnicodeDecodeError as error:
        raise FinalD43AuditError(f"TI-TXT is not ASCII: {error}") from error
    segments: list[tuple[int, bytes]] = []
    start: int | None = None
    data = bytearray()
    terminated = False
    for index, token in enumerate(tokens):
        if token == "q":
            _require(index == len(tokens) - 1, "TI-TXT has tokens after terminator")
            terminated = True
            break
        if token.startswith("@"):
            if start is not None:
                segments.append((start, bytes(data)))
            try:
                start = int(token[1:], 16)
            except ValueError as error:
                raise FinalD43AuditError(f"invalid TI-TXT address: {token}") from error
            data = bytearray()
            continue
        _require(start is not None, "TI-TXT data precedes its address")
        _require(bool(re.fullmatch(r"[0-9A-Fa-f]{2}", token)), "invalid TI-TXT byte")
        data.append(int(token, 16))
    if start is not None:
        segments.append((start, bytes(data)))
    _require(terminated, "TI-TXT terminator is missing")
    _require(
        [(address, len(block)) for address, block in segments]
        == [(0xA000, 2_000), (0xFFFE, 2)],
        "TI-TXT segment layout changed",
    )
    memory: dict[int, int] = {}
    for address, block in segments:
        for offset, value in enumerate(block):
            absolute = address + offset
            _require(absolute not in memory, "TI-TXT segments overlap")
            memory[absolute] = value
    return {"segments": segments, "memory": memory}


def _contiguous_segments(memory: dict[int, int]) -> list[tuple[int, bytes]]:
    _require(memory, "decoded absolute UBROF memory is empty")
    segments: list[tuple[int, bytes]] = []
    start: int | None = None
    previous: int | None = None
    data = bytearray()
    for address in sorted(memory):
        if previous is None or address != previous + 1:
            if start is not None:
                segments.append((start, bytes(data)))
            start = address
            data = bytearray()
        data.append(memory[address])
        previous = address
    assert start is not None
    segments.append((start, bytes(data)))
    return segments


def parse_xlib_object_code(payload: bytes) -> dict[str, Any]:
    """Parse the bounded record families emitted for the pinned absolute D43."""

    try:
        text = payload.decode("cp1252")
    except UnicodeDecodeError as error:
        raise FinalD43AuditError(f"XLIB list is not cp1252: {error}") from error
    _require(VERSION_BANNER in text, "XLIB list version banner changed")
    lines = text.splitlines()

    scoped_names: dict[str, str] = {}
    for line in lines:
        match = SCOPED_NAME_RE.match(line)
        if match is None:
            continue
        identifier = match.group(1).upper()
        name = match.group(2)
        _require(identifier not in scoped_names, f"duplicate scoped name {identifier}")
        scoped_names[identifier] = name

    modules: list[dict[str, str]] = []
    public_code_symbols: list[dict[str, Any]] = []
    local_data_symbols: list[dict[str, Any]] = []
    function_frames: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    macros: dict[str, set[str]] = {}
    memory: dict[int, int] = {}
    code_origin_count = 0
    code_abs_var_count = 0
    current_module: str | None = None
    current_origin: int | None = None
    write_address: int | None = None
    current_frame: dict[str, Any] | None = None
    last_direct_target: str | None = None

    index = 0
    while index < len(lines):
        line = lines[index]
        match = MODULE_RE.match(line)
        if match is not None:
            current_module = match.group(2)
            modules.append({"kind": match.group(1), "name": current_module})
            current_origin = None
            write_address = None
            current_frame = None
            last_direct_target = None
            index += 1
            continue
        if END_RE.match(line):
            current_module = None
            current_origin = None
            write_address = None
            current_frame = None
            last_direct_target = None
            index += 1
            continue
        match = ORG_RE.match(line)
        if match is not None:
            segment = int(match.group(1))
            address = int(match.group(2), 16)
            if segment == 1:
                current_origin = address
                write_address = address
                code_origin_count += 1
            else:
                current_origin = None
                write_address = None
            current_frame = None
            last_direct_target = None
            index += 1
            continue
        match = ABS_VAR_RE.match(line)
        if match is not None:
            encoded = match.group(1)
            next_index = index + 1
            while next_index < len(lines):
                continuation = ABS_CONTINUATION_RE.match(lines[next_index])
                if continuation is None:
                    break
                encoded += continuation.group(1)
                next_index += 1
            _require(len(encoded) % 2 == 0, "odd-length t_abs_var payload")
            if write_address is not None:
                code_abs_var_count += 1
                for value in bytes.fromhex(encoded):
                    _require(
                        write_address not in memory,
                        f"overlapping decoded byte at {_hex(write_address)}",
                    )
                    memory[write_address] = value
                    write_address += 1
            index = next_index
            continue
        match = PUBLIC_CODE_RE.match(line)
        if match is not None:
            _require(current_module is not None, "public code symbol outside a module")
            name_id = match.group(2).upper()
            _require(name_id in scoped_names, f"unresolved public code ID {name_id}")
            public_code_symbols.append(
                {
                    "owner": current_module,
                    "address": int(match.group(1), 16),
                    "name_id": name_id,
                    "name": scoped_names[name_id],
                }
            )
        match = LOCAL_DATA_RE.match(line)
        if match is not None:
            _require(current_module is not None, "local data symbol outside a module")
            name_id = match.group(2).upper()
            _require(name_id in scoped_names, f"unresolved local data ID {name_id}")
            local_data_symbols.append(
                {
                    "owner": current_module,
                    "address": int(match.group(1), 16),
                    "name_id": name_id,
                    "name": scoped_names[name_id],
                }
            )
        match = FRAME_RE.match(line)
        if match is not None:
            _require(current_module is not None, "call frame outside a module")
            _require(current_origin is not None, "call frame lacks a code origin")
            current_frame = {
                "owner": current_module,
                "start": current_origin,
                "size": int(match.group(1), 16),
                "name_id": match.group(2).upper(),
            }
            function_frames.append(current_frame)
            last_direct_target = None
        match = DIRECT_TARGET_RE.match(line)
        if match is not None:
            last_direct_target = match.group(1).upper()
        match = DIRECT_EVENT_RE.match(line)
        if match is not None:
            _require(current_frame is not None, "direct call lacks a current frame")
            _require(last_direct_target is not None, "direct call lacks a target")
            calls.append(
                {
                    "owner": current_frame["owner"],
                    "caller_id": current_frame["name_id"],
                    "address": current_frame["start"] + int(match.group(1), 16),
                    "target_id": last_direct_target,
                    "source_line": int(match.group(2)),
                }
            )
        match = MACRO_RE.match(line)
        if match is not None:
            macros.setdefault(match.group(1), set()).add((match.group(2) or "").strip())
        index += 1

    _require(len(scoped_names) == len(set(scoped_names)), "scoped-name IDs overlap")
    frame_ids = [str(row["name_id"]) for row in function_frames]
    _require(len(frame_ids) == len(set(frame_ids)), "call-frame IDs overlap")
    for row in function_frames:
        identifier = str(row["name_id"])
        _require(identifier in scoped_names, f"unresolved call-frame ID {identifier}")
        row["name"] = scoped_names[identifier]
    for row in calls:
        caller_id = str(row["caller_id"])
        target_id = str(row["target_id"])
        _require(caller_id in scoped_names, f"unresolved caller ID {caller_id}")
        _require(target_id in scoped_names, f"unresolved target ID {target_id}")
        row["caller"] = scoped_names[caller_id]
        row["target"] = scoped_names[target_id]

    return {
        "scoped_names": scoped_names,
        "modules": modules,
        "public_code_symbols": public_code_symbols,
        "local_data_symbols": local_data_symbols,
        "function_frames": function_frames,
        "calls": calls,
        "macros": macros,
        "memory": memory,
        "code_origin_count": code_origin_count,
        "code_abs_var_count": code_abs_var_count,
        "indirect_call_text_rows": sum("Indirect call" in line for line in lines),
        "embedded_v1_1_path_rows": sum(
            "E6_73_sample code_V1.1_20231030" in line for line in lines
        ),
        "embedded_v1_2_path_rows": sum(
            "E6_73_sample code_V1.2_20250116" in line for line in lines
        ),
    }


def _validate_direct_call_machine_bytes(parsed: dict[str, Any]) -> None:
    frames = {str(row["name_id"]): row for row in parsed["function_frames"]}
    memory = parsed["memory"]
    for call in parsed["calls"]:
        target_id = str(call["target_id"])
        _require(target_id in frames, f"call target {target_id} has no decoded frame")
        target_address = int(frames[target_id]["start"])
        _require(target_address <= 0xFFFF, "CALLA target exceeds bounded encoding")
        address = int(call["address"])
        try:
            actual = bytes(memory[address + offset] for offset in range(4))
        except KeyError as error:
            raise FinalD43AuditError(
                f"call site {_hex(address)} is absent from reconstructed memory"
            ) from error
        expected = b"\xb0\x13" + target_address.to_bytes(2, "little")
        _require(
            actual == expected,
            f"call-site machine target mismatch at {_hex(address)}",
        )


def _legacy_upload_rows(name: str, payload: bytes) -> dict[str, Any]:
    try:
        object_report, edges = graph._object_report(name, payload)
    except (ValueError, RuntimeError) as error:
        raise FinalD43AuditError(
            f"legacy object parse failed for {name}: {error}"
        ) from error
    upload_edges = [
        edge for edge in edges if edge["callee_symbol"] == "Upload_Temperature_LUT"
    ]
    _require(len(upload_edges) == 7, f"{name} upload edge count changed")
    _require(
        all(
            edge["relocation_classification"] == "local-section-relative"
            for edge in upload_edges
        ),
        f"{name} gained a nonlocal upload edge",
    )
    expected_callers = {
        "EPD_Display_White",
        "EPD_Display_Black",
        "EPD_Display_Yellow",
        "EPD_Display_Red",
        "EPD_Display_line_4bit",
        "EPD_Display_Dot",
        "EPD_Display_Dot_4bit",
    }
    actual_callers = {
        str(edge["caller_symbols"][0])
        for edge in upload_edges
        if len(edge["caller_symbols"]) == 1
    }
    _require(actual_callers == expected_callers, f"{name} upload caller set changed")
    return {
        "EPD_Init_section_id": object_report["target_sections"]["EPD_Init"][0],
        "Upload_Temperature_LUT_section_id": object_report["target_sections"][
            "Upload_Temperature_LUT"
        ][0],
        "local_upload_edge_count": len(upload_edges),
        "local_upload_callers": sorted(actual_callers),
        "EPD_Init_calls_upload": any(
            edge["caller_section_id"] == object_report["target_sections"]["EPD_Init"][0]
            for edge in upload_edges
        ),
        "edge_evidence": "paired CALLA debug-source record plus local-section relocation",
    }


def _metadata_segments(segments: list[tuple[int, bytes]]) -> list[dict[str, Any]]:
    return [
        {
            "start_address": _hex(address),
            "size_bytes": len(block),
            "sha256": _sha256(block),
        }
        for address, block in segments
    ]


def build_report(
    xlib_path: Path, iar_root: Path = graph.DEFAULT_IAR_ROOT
) -> dict[str, Any]:
    xlib_identity = _pin_xlib(xlib_path)
    pinned: dict[str, bytes] = {}
    identity_rows: dict[str, dict[str, Any]] = {}
    for relative, expected in EXPECTED_FILES.items():
        payload = _pin(iar_root / Path(relative), expected, relative)
        pinned[relative] = payload
        identity_rows[relative] = {
            "size_bytes": len(payload),
            "sha256": _sha256(payload),
        }

    try:
        project = project_chain._parse_project(pinned["C2_Example.ewp"])
        dependency = graph.parse_dependency_graph(pinned["C2_Example.dep"])
    except (ValueError, RuntimeError) as error:
        raise FinalD43AuditError(f"project/dependency parse failed: {error}") from error
    debug = project["configurations"]["Debug"]
    _require(
        dependency["final_d43_direct_project_r43_input_names"]
        == list(DIRECT_PROJECT_OBJECTS),
        "direct project object set changed",
    )
    _require(
        debug["link"]["primary_output"] == "C2_Example.d43", "EWP D43 output changed"
    )
    _require(
        debug["link"]["extra_output"] == "C2_Example.txt", "EWP TI-TXT output changed"
    )

    direct_payloads = {
        name: pinned[f"Debug/Obj/{name}"] for name in DIRECT_PROJECT_OBJECTS
    }
    _require(
        all(
            b"Upload_Temperature_LUT" not in payload
            for payload in direct_payloads.values()
        ),
        "a direct project object gained an upload marker",
    )

    xlib_listing = _run_xlib_list_object_code(
        xlib_path, iar_root / "Debug/Exe/C2_Example.d43"
    )
    parsed = parse_xlib_object_code(xlib_listing)
    _require(len(parsed["scoped_names"]) == 248, "scoped-name count changed")
    _require(len(parsed["modules"]) == 31, "decoded module count changed")
    _require(
        len(parsed["public_code_symbols"]) == 25, "public code symbol count changed"
    )
    _require(len(parsed["function_frames"]) == 19, "call-frame count changed")
    _require(len(parsed["calls"]) == 188, "direct-call count changed")
    _require(parsed["code_origin_count"] == 25, "code-origin count changed")
    _require(parsed["code_abs_var_count"] == 62, "code t_abs_var count changed")
    _require(
        parsed["indirect_call_text_rows"] == 0, "decoded indirect-call row appeared"
    )
    _require(parsed["embedded_v1_1_path_rows"] > 0, "V1.1 embedded lineage disappeared")
    _require(parsed["embedded_v1_2_path_rows"] == 0, "V1.2 embedded lineage appeared")

    module_names = [str(row["name"]) for row in parsed["modules"]]
    _require(module_names.count("DELAY") == 1, "DELAY final module ownership changed")
    _require(module_names.count("E6_73") == 1, "E6_73 final module ownership changed")
    _require(module_names.count("main") == 1, "main final module ownership changed")
    _require(
        "E2801" not in module_names and "E2802" not in module_names,
        "legacy module entered final D43",
    )

    frame_by_name = {str(row["name"]): row for row in parsed["function_frames"]}
    _require(
        len(frame_by_name) == len(parsed["function_frames"]), "frame names overlap"
    )
    for name, (owner, start, size) in EXPECTED_FUNCTIONS.items():
        _require(name in frame_by_name, f"final frame {name} is missing")
        row = frame_by_name[name]
        _require(
            (row["owner"], row["start"], row["size"]) == (owner, start, size),
            f"final frame ownership/address changed for {name}",
        )

    public_rows = {
        str(row["name"]): (str(row["owner"]), int(row["address"]))
        for row in parsed["public_code_symbols"]
    }
    for name, (owner, start, _size) in EXPECTED_FUNCTIONS.items():
        _require(
            public_rows.get(name) == (owner, start),
            f"public ownership changed for {name}",
        )

    _validate_direct_call_machine_bytes(parsed)
    main_calls = [row for row in parsed["calls"] if row["caller"] == "main"]
    main_actual = [
        (int(row["address"]), str(row["target"]), int(row["source_line"]))
        for row in main_calls
    ]
    _require(
        tuple(main_actual) == EXPECTED_MAIN_CALLS, "exact main call sequence changed"
    )

    init_calls = [row for row in parsed["calls"] if row["caller"] == "EPD_Init"]
    init_counts = Counter(str(row["target"]) for row in init_calls)
    _require(
        init_counts
        == Counter(
            {
                "reset": 1,
                "check_busy_high": 1,
                "delay": 1,
                "SPI_COMMAND": 13,
                "SPI_DATA": 35,
            }
        ),
        "EPD_Init call distribution changed",
    )
    display_summaries: dict[str, dict[str, int]] = {}
    expected_display_counts = Counter(
        {"SPI_DATA": 7, "SPI_COMMAND": 5, "check_busy_high": 3}
    )
    for name in DISPLAY_FUNCTIONS:
        calls = [row for row in parsed["calls"] if row["caller"] == name]
        counts = Counter(str(row["target"]) for row in calls)
        _require(counts == expected_display_counts, f"{name} call distribution changed")
        display_summaries[name] = dict(sorted(counts.items()))

    scoped_values = set(parsed["scoped_names"].values())
    _require(
        "Upload_Temperature_LUT" not in scoped_values,
        "final upload scoped name appeared",
    )
    _require(
        not any(row["target"] == "Upload_Temperature_LUT" for row in parsed["calls"]),
        "final upload direct call appeared",
    )
    _require(
        b"Upload_Temperature_LUT" not in pinned["Debug/Exe/C2_Example.d43"],
        "final D43 upload marker appeared",
    )

    d43_segments = _contiguous_segments(parsed["memory"])
    ti_txt = _parse_ti_txt(pinned["Debug/Exe/C2_Example.txt"])
    _require(
        [(address, len(block)) for address, block in d43_segments]
        == [(0xA000, 2_000), (0xFFFE, 2)],
        "decoded D43 memory layout changed",
    )
    _require(parsed["memory"] == ti_txt["memory"], "D43 and TI-TXT bytes differ")

    macro_expectations = {
        "CSB_L": {"P6OUT&=0xF7"},
        "CSB_H": {"P6OUT|=0x08"},
        "P6OUT": {"(PCOUT_H)"},
    }
    for name, expected in macro_expectations.items():
        _require(parsed["macros"].get(name) == expected, f"macro {name} changed")
    pcout_h_addresses = sorted(
        {
            int(row["address"])
            for row in parsed["local_data_symbols"]
            if row["name"] == "PCOUT_H"
        }
    )
    _require(pcout_h_addresses == [0x0243], "PCOUT_H address changed")
    low_signature = bytes.fromhex("F2C24302")
    high_signature = bytes.fromhex("F2D24302")
    controller_rows: dict[str, Any] = {}
    for name in ("SPI_DATA", "SPI_COMMAND"):
        frame = frame_by_name[name]
        start = int(frame["start"])
        block = bytes(
            parsed["memory"][address]
            for address in range(start, start + int(frame["size"]))
        )
        _require(block.count(low_signature) == 1, f"{name} CSB-low count changed")
        _require(block.count(high_signature) == 1, f"{name} CSB-high count changed")
        _require(block.find(low_signature) == 4, f"{name} CSB-low offset changed")
        _require(block.find(high_signature) == 110, f"{name} CSB-high offset changed")
        controller_rows[name] = {
            "function_start": _hex(start),
            "function_size_bytes": int(frame["size"]),
            "fixed_CSB_low_write_count": 1,
            "fixed_CSB_low_instruction_offset": 4,
            "fixed_CSB_high_write_count": 1,
            "fixed_CSB_high_instruction_offset": 110,
        }

    legacy = {
        name: _legacy_upload_rows(name, pinned[f"Debug/Obj/{name}"])
        for name in ("E2801.r43", "E2802.r43")
    }

    relevant_function_rows = {
        name: {
            "owner_module": str(frame_by_name[name]["owner"]),
            "start_address": _hex(int(frame_by_name[name]["start"])),
            "size_bytes": int(frame_by_name[name]["size"]),
            "visibility": "PUBLIC_REL" if name in public_rows else "local call frame",
        }
        for name in EXPECTED_FUNCTIONS
    }
    main_call_rows = [
        {
            "call_site": _hex(address),
            "target": target,
            "source_line": source_line,
        }
        for address, target, source_line in EXPECTED_MAIN_CALLS
    ]
    memory_concat = b"".join(block for _address, block in d43_segments)

    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "offline_read_only": True,
            "hardware_accessed": False,
            "serial_or_COM_accessed": False,
            "device_network_accessed": False,
            "firmware_written_or_flashed": False,
            "reset_requested": False,
            "visible_refresh_requested": False,
            "physical_action_token_or_claim_created": False,
            "raw_D43_or_object_bytes_emitted": False,
            "raw_LUT_or_waveform_emitted": False,
        },
        "identity": {
            "xlib": xlib_identity,
            "delivered_artifacts": identity_rows,
        },
        "project_and_dependency_chain": {
            "EWP_Debug_declared_sources": debug["declared_sources"],
            "EWP_Debug_primary_output": debug["link"]["primary_output"],
            "EWP_Debug_extra_output": debug["link"]["extra_output"],
            "DEP_direct_project_r43_inputs": dependency[
                "final_d43_direct_project_r43_input_names"
            ],
            "DEP_direct_toolkit_r43_inputs": dependency[
                "final_d43_direct_toolkit_r43_input_names"
            ],
            "E2801_or_E2802_is_direct_input": False,
        },
        "absolute_D43_decode": {
            "official_tool_operation": "LIST-OBJECT-CODE",
            "returncode": 0,
            "decoded_module_count": len(parsed["modules"]),
            "decoded_module_names": module_names,
            "scoped_name_count": len(parsed["scoped_names"]),
            "public_code_symbol_count": len(parsed["public_code_symbols"]),
            "call_frame_count": len(parsed["function_frames"]),
            "direct_call_count": len(parsed["calls"]),
            "all_direct_calls_machine_target_validated": True,
            "decoded_indirect_call_text_rows": parsed["indirect_call_text_rows"],
            "embedded_source_lineage": "E6_73_sample code_V1.1_20231030",
            "delivered_workspace_directory_lineage": "E6_73_sample code_V1.2_20250116",
            "is_claimed_as_a_V1_2_rebuild": False,
        },
        "D43_TI_TXT_exact_equivalence": {
            "D43_decoded_t_org_01_count": parsed["code_origin_count"],
            "D43_decoded_t_abs_var_count": parsed["code_abs_var_count"],
            "total_unique_bytes": len(parsed["memory"]),
            "segments": _metadata_segments(d43_segments),
            "concatenated_data_sha256": _sha256(memory_concat),
            "address_sets_equal": True,
            "byte_mismatch_count": 0,
            "byte_for_byte_equal": True,
            "reset_vector": "0xA000",
        },
        "final_provider_and_call_chain": {
            "relevant_functions": relevant_function_rows,
            "main_direct_calls": main_call_rows,
            "EPD_Init_direct_call_count": len(init_calls),
            "EPD_Init_target_counts": dict(sorted(init_counts.items())),
            "display_target_counts": display_summaries,
            "Upload_Temperature_LUT_scoped_name_present": False,
            "Upload_Temperature_LUT_direct_call_present": False,
            "Upload_Temperature_LUT_marker_present_in_D43": False,
            "resolved_current_EPD_Init_provider": "E6_73",
            "resolved_current_display_provider": "E6_73",
            "resolved_current_runtime_upload_provider": None,
        },
        "fixed_software_controller_endpoint": {
            "CSB_macros": {
                name: next(iter(values)) for name, values in macro_expectations.items()
            },
            "decoded_absolute_register_address": "0x0243",
            "decoded_CSB_bit_mask": "0x08",
            "transport_functions": controller_rows,
            "verdict": "ONE_FIXED_CSB_SOFTWARE_ENDPOINT_IN_CURRENT_FINAL",
            "physical_controller_identity_or_fanout_proven": False,
            "dual_controller_load_or_commit_semantics_proven": False,
        },
        "separate_legacy_candidates": legacy,
        "adjudication": {
            "current_final_named_runtime_upload_path": "NOT_FOUND",
            "legacy_upload_edges_are_in_final": False,
            "legacy_upload_edges_are_exact_local_candidate_evidence": True,
            "main_to_EPD_Init_and_six_display_calls_are_exact_final_evidence": True,
            "provider_verdict": (
                "The pinned final D43 assigns EPD_Init and all six display routines to "
                "module E6_73. Its exact main path contains no named upload call. E2801 "
                "and E2802 each contain seven exact local display-to-upload edges, but "
                "neither object is a DEP direct input nor a decoded final module."
            ),
        },
        "evidence_boundaries": {
            "absolute_D43_was_decoded_directly_not_relinked": True,
            "TI_TXT_is_same_EWP_Debug_extra_output": True,
            "source_name_overlap_does_not_select_a_legacy_provider": True,
            "absence_of_named_upload_does_not_prove_controller_capability_absent": True,
            "fixed_software_CSB_does_not_prove_physical_chip_count": True,
            "legacy_orphan_edges_do_not_supply_a_current_final_runtime_LUT": True,
            "no_LUT_bytes_or_electrical_parameters_are_inferred": True,
        },
    }
    report["integrity"] = {
        "canonical_encoding": "UTF-8 sorted-key compact JSON excluding integrity",
        "canonical_sha256": _sha256(_canonical_bytes(report)),
    }
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlib", type=Path, required=True)
    parser.add_argument("--iar-root", type=Path, default=graph.DEFAULT_IAR_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = build_report(args.xlib, args.iar_root)
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
            write_new_bytes_durable(args.output, payload)
    except (OSError, subprocess.SubprocessError, FinalD43AuditError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
