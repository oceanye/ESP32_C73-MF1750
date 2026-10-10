#!/usr/bin/env python3
"""Audit the compiled empirical-H3/control trace pair without hardware I/O.

The audit works on exact BIN/ELF artifacts.  It extracts command arguments
from the compiled Xtensa call sites, hashes payload symbols directly from ELF
sections, compares normalized machine-code bodies for the shared factory,
BUSY, DTM, refresh, and cleanup helpers, and hashes the compiler dependency
manifests.  It never scans arbitrary firmware bytes for opcode values.

The accepted control is intentionally a delete-only command-stream-and-
duration control.  It is not time matched: each controller omits 1505 SPI
bytes and five source-level yields along with R20/R21.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import struct
import subprocess
import sys
from typing import Any, Final, Mapping, Sequence

from tools import mf1750_ec5_h3_matched_control_compiled_identity as control_compiled
from tools import mf1750_ec5_h3_matched_control_contract as control_contract
from tools import mf1750_ec5_runtime_lut_release as h3_release


SCHEMA_VERSION: Final = 1
KIND: Final = "mf1750-ec5-h3-matched-compiled-trace-audit"
PROFILE_ID: Final = "WF20_25"
REPO_ROOT: Final = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES: Final = 64_000_000

TREATMENT_CONFIG: Final = REPO_ROOT / "platformio.runtime_lut_wf20_25.ini"
CONTROL_CONFIG: Final = REPO_ROOT / "platformio.h3_matched_control_wf20_25.ini"

TREATMENT_DISPLAY = "epdDisplayCompiledEmpiricalH3(EpdEmpiricalH3Role)"
TREATMENT_WRITE = (
    "(anonymous namespace)::h3WriteFixedPayload((anonymous namespace)::"
    "H3FixedCommand, unsigned char const*, unsigned int)"
)
TREATMENT_UPLOAD = "(anonymous namespace)::h3UploadFixedWaveformToController(bool)"
CONTROL_DISPLAY = "epdDisplayCompiledH3MatchedControl(EpdH3MatchedControlRole)"
CONTROL_WRITE = (
    "(anonymous namespace)::h3mcWriteFixedPayload((anonymous namespace)::"
    "H3MatchedFixedCommand, unsigned char const*, unsigned int)"
)

COMMON_FUNCTION_PATTERNS: Final[Mapping[str, str]] = {
    "epd_command": "(anonymous namespace)::epdCommand(unsigned char)",
    "epd_data": "(anonymous namespace)::epdData(unsigned char)",
    "controller_select": "(anonymous namespace)::setActiveControllers(bool, bool)",
    "busy_wait": "(anonymous namespace)::epdWaitIdle(char const*, unsigned int, bool)",
    "factory_cascade_init": "epdInitResolutionSelected",
    "cascade_prepare": "epdPrepareCascade(unsigned int)",
    "mapped_dtm_stream": "epdStreamPackedFrameController(unsigned char const*, bool)",
    "refresh_closure": "(anonymous namespace)::epdSecondSettingAndRefresh()",
    "precommand_idle_gate": (
        "(anonymous namespace)::epdRequireIdleBeforeCommand(char const*)"
    ),
    "fail_safe_power_off": (
        "(anonymous namespace)::epdRequestFailSafePowerOff(char const*)"
    ),
    "safe_failed_finish": (
        "(anonymous namespace)::epdFinishFailedOperationSafe(unsigned int, "
        "char const*, int)"
    ),
    "operation_finish": (
        "(anonymous namespace)::epdFinishOperation(unsigned int, bool)"
    ),
}

TREATMENT_PAYLOAD_SYMBOLS: Final[Mapping[str, str]] = {
    "runtime_psr": (
        "(anonymous namespace)::h3ApplyFixedGlobalRuntimeConfigToBothControllers()"
        "::kRuntimePsr"
    ),
    "power": ("mf1750::runtime_lut::wf20_25_empirical_h3::kPowerPayload"),
    "pll": "mf1750::runtime_lut::wf20_25_empirical_h3::kPllPayload",
    "tres": (
        "(anonymous namespace)::h3ApplyFixedGlobalRuntimeConfigToBothControllers()"
        "::kControllerTres"
    ),
    "e9": (
        "(anonymous namespace)::h3UploadFixedWaveformToController(bool)::kHiddenEnable"
    ),
    "r20": "mf1750::runtime_lut::wf20_25_empirical_h3::kR20Payload",
    "r21": "mf1750::runtime_lut::wf20_25_empirical_h3::kR21Payload",
}

CONTROL_PAYLOAD_SYMBOLS: Final[Mapping[str, str]] = {
    "runtime_psr": "(anonymous namespace)::H3MC_RUNTIME_PSR",
    "power": "(anonymous namespace)::H3MC_POWER_PAYLOAD",
    "pll": "(anonymous namespace)::H3MC_PLL_PAYLOAD",
    "tres": "(anonymous namespace)::H3MC_CONTROLLER_TRES",
    "e9": "(anonymous namespace)::H3MC_HIDDEN_ENABLE",
}

EXPECTED_SMALL_PAYLOADS: Final[Mapping[str, bytes]] = {
    "runtime_psr": bytes.fromhex("5fe9"),
    "power": bytes.fromhex("0f002334323a"),
    "pll": bytes.fromhex("02"),
    "tres": bytes.fromhex("02000258"),
    "e9": bytes.fromhex("01"),
}
EXPECTED_R20_SHA256: Final = (
    "3cab2e2915205400bfdb0c2749a3e1e606cb6f190b8f3638849c532449a0ca26"
)
EXPECTED_R21_SHA256: Final = (
    "24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f"
)

NM_LINE_RE = re.compile(
    r"^(?P<address>[0-9A-Fa-f]+)\s+(?P<size>[0-9A-Fa-f]+)\s+"
    r"(?P<type>\S)\s+(?P<name>.+)$"
)
DISASSEMBLY_LINE_RE = re.compile(
    r"^\s*(?P<address>[0-9A-Fa-f]+):\s+"
    r"(?P<encoding>(?:[0-9A-Fa-f]{2,8}\s+)+)\s*"
    r"(?P<asm>.*?)\s*$"
)


class MatchedTraceAuditError(ValueError):
    """The compiled pair failed a trace or provenance invariant."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise MatchedTraceAuditError("value is not canonical JSON") from error


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    root = deepcopy(dict(unsigned))
    root["audit_id"] = _sha256(_canonical(root))
    root["integrity"] = {
        "algorithm": "sha256",
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
        "canonical_sha256": _sha256(_canonical(root)),
    }
    return root


def validate_seal(root: Mapping[str, Any]) -> str:
    integrity = root.get("integrity")
    if not isinstance(integrity, Mapping):
        raise MatchedTraceAuditError("trace audit integrity is absent")
    unsigned = {key: value for key, value in root.items() if key != "integrity"}
    wanted = _sha256(_canonical(unsigned))
    if (
        integrity.get("algorithm") != "sha256"
        or integrity.get("scope")
        != "entire object excluding integrity; canonical UTF-8 JSON"
        or integrity.get("canonical_sha256") != wanted
    ):
        raise MatchedTraceAuditError("trace audit canonical integrity differs")
    audit_body = {key: value for key, value in unsigned.items() if key != "audit_id"}
    if unsigned.get("audit_id") != _sha256(_canonical(audit_body)):
        raise MatchedTraceAuditError("trace audit ID differs")
    return wanted


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MatchedTraceAuditError(message)


def _read_regular(path: Path, *, label: str, maximum: int = MAX_FILE_BYTES) -> bytes:
    candidate = Path(path)
    try:
        before = candidate.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise MatchedTraceAuditError(f"{label} must be a non-symlink regular file")
        if before.st_size <= 0 or before.st_size > maximum:
            raise MatchedTraceAuditError(f"{label} size is invalid")
        payload = candidate.read_bytes()
        after = candidate.lstat()
    except OSError as error:
        raise MatchedTraceAuditError(f"could not read {label}: {error}") from error
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or len(payload) != after.st_size:
        raise MatchedTraceAuditError(f"{label} changed while being read")
    return payload


def _file_record(path: Path, *, label: str) -> dict[str, Any]:
    resolved = Path(path).resolve(strict=True)
    payload = _read_regular(resolved, label=label)
    return {
        "path": str(resolved),
        "bytes": len(payload),
        "sha256": _sha256(payload),
    }


def _tool_default(name: str) -> Path:
    discovered = shutil.which(name)
    if discovered:
        return Path(discovered)
    profile = os.environ.get("USERPROFILE")
    if profile:
        candidate = (
            Path(profile)
            / ".platformio/packages/toolchain-xtensa-esp32s3/bin"
            / f"xtensa-esp32s3-elf-{name}.exe"
        )
        if candidate.is_file():
            return candidate
    raise MatchedTraceAuditError(f"could not locate xtensa tool {name!r}")


def _run_tool(tool: Path, arguments: Sequence[str], *, label: str) -> str:
    executable = Path(tool).resolve(strict=True)
    try:
        completed = subprocess.run(
            [str(executable), *arguments],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise MatchedTraceAuditError(f"could not execute {label}: {error}") from error
    if completed.returncode != 0:
        raise MatchedTraceAuditError(
            f"{label} failed with {completed.returncode}: {completed.stderr.strip()}"
        )
    return completed.stdout


def _nm_symbols(nm_tool: Path, elf_path: Path) -> dict[str, dict[str, Any]]:
    output = _run_tool(
        nm_tool,
        ["-S", "-C", "--defined-only", str(elf_path)],
        label=f"nm {elf_path.name}",
    )
    result: dict[str, dict[str, Any]] = {}
    for line in output.splitlines():
        match = NM_LINE_RE.match(line)
        if match is None:
            continue
        name = match.group("name")
        if name in result:
            result[name]["occurrences"] = int(result[name]["occurrences"]) + 1
            continue
        result[name] = {
            "address": int(match.group("address"), 16),
            "size": int(match.group("size"), 16),
            "type": match.group("type"),
            "occurrences": 1,
        }
    _require(bool(result), f"no symbols decoded from {elf_path}")
    return result


def _symbol_exact(
    symbols: Mapping[str, Mapping[str, Any]], name: str
) -> tuple[str, Mapping[str, Any]]:
    item = symbols.get(name)
    if item is None:
        raise MatchedTraceAuditError(f"required symbol {name!r} is absent")
    if item.get("occurrences") != 1:
        raise MatchedTraceAuditError(f"required symbol {name!r} is not unique")
    return name, item


def _symbol_contains(
    symbols: Mapping[str, Mapping[str, Any]], token: str
) -> tuple[str, Mapping[str, Any]]:
    matches = [
        (name, item)
        for name, item in symbols.items()
        if token in name and item.get("occurrences") == 1
    ]
    if len(matches) != 1:
        raise MatchedTraceAuditError(
            f"symbol token {token!r} has {len(matches)} matches, expected one"
        )
    return matches[0]


def _elf_sections(payload: bytes) -> list[dict[str, int]]:
    _require(payload[:4] == b"\x7fELF", "ELF magic differs")
    _require(payload[4] == 1 and payload[5] == 1, "ELF is not 32-bit little-endian")
    _require(len(payload) >= 52, "ELF header is truncated")
    section_offset = struct.unpack_from("<I", payload, 0x20)[0]
    entry_size = struct.unpack_from("<H", payload, 0x2E)[0]
    section_count = struct.unpack_from("<H", payload, 0x30)[0]
    _require(entry_size >= 40 and section_count > 0, "ELF section table is invalid")
    _require(
        section_offset + entry_size * section_count <= len(payload),
        "ELF section table is out of range",
    )
    sections: list[dict[str, int]] = []
    for index in range(section_count):
        cursor = section_offset + index * entry_size
        _name, _type, _flags, address, offset, size = struct.unpack_from(
            "<IIIIII", payload, cursor
        )
        if size and offset + size <= len(payload):
            sections.append({"address": address, "offset": offset, "size": size})
    return sections


def _symbol_bytes(
    elf_payload: bytes,
    sections: Sequence[Mapping[str, int]],
    *,
    name: str,
    symbol: Mapping[str, Any],
) -> bytes:
    address = int(symbol["address"])
    size = int(symbol["size"])
    _require(size > 0, f"symbol {name!r} has zero size")
    for section in sections:
        start = int(section["address"])
        end = start + int(section["size"])
        if start <= address and address + size <= end:
            offset = int(section["offset"]) + address - start
            return elf_payload[offset : offset + size]
    raise MatchedTraceAuditError(f"symbol {name!r} is not inside a file-backed section")


def _payloads(
    elf_payload: bytes,
    symbols: Mapping[str, Mapping[str, Any]],
    wanted: Mapping[str, str],
) -> tuple[dict[str, bytes], dict[str, Any]]:
    sections = _elf_sections(elf_payload)
    raw: dict[str, bytes] = {}
    report: dict[str, Any] = {}
    for role, symbol_name in wanted.items():
        name, symbol = _symbol_exact(symbols, symbol_name)
        payload = _symbol_bytes(elf_payload, sections, name=name, symbol=symbol)
        raw[role] = payload
        item: dict[str, Any] = {
            "symbol": name,
            "bytes": len(payload),
            "sha256": _sha256(payload),
            "raw_bytes_emitted": False,
        }
        if role in EXPECTED_SMALL_PAYLOADS:
            item["value_hex"] = payload.hex()
        if role == "r21":
            item["all_ff"] = payload == b"\xff" * len(payload)
        report[role] = item
    return raw, report


def _disassemble(
    objdump_tool: Path,
    elf_path: Path,
    symbol_name: str,
    symbol: Mapping[str, Any],
) -> list[dict[str, Any]]:
    address = int(symbol["address"])
    size = int(symbol["size"])
    _require(size > 0 and symbol["type"].lower() == "t", f"{symbol_name} is not text")
    output = _run_tool(
        objdump_tool,
        [
            "-d",
            "-C",
            f"--start-address=0x{address:x}",
            f"--stop-address=0x{address + size:x}",
            str(elf_path),
        ],
        label=f"objdump {symbol_name}",
    )
    records: list[dict[str, Any]] = []
    for line in output.splitlines():
        match = DISASSEMBLY_LINE_RE.match(line)
        if match is None:
            continue
        records.append(
            {
                "address": int(match.group("address"), 16),
                "asm": match.group("asm").strip(),
            }
        )
    _require(bool(records), f"no disassembly records for {symbol_name}")
    return records


def _normalize_asm(assembly: str) -> str | None:
    value = assembly.strip()
    if value == ".byte 00":
        return None
    value = re.sub(r"\b[0-9a-f]{8}\s+<([^>]+)>", r"<\1>", value)
    value = re.sub(r"<_stext\+0x[0-9a-f]+>", "<LITERAL>", value)
    value = re.sub(r"\+0x[0-9a-f]+>", "+<REL>>", value)
    value = re.sub(r"\$constprop\$\d+", "$constprop$", value)
    value = re.sub(r"^(mov|movi|l32i|s32i|addi)\.n\b", r"\1", value)
    same_or = re.fullmatch(r"or\s+(a\d+),\s*(a\d+),\s*\2", value)
    if same_or is not None:
        value = f"mov {same_or.group(1)}, {same_or.group(2)}"
    return re.sub(r"\s+", " ", value).strip()


def _normalized_digest(records: Sequence[Mapping[str, Any]]) -> tuple[int, str]:
    lines = [
        normalized
        for record in records
        if (normalized := _normalize_asm(str(record["asm"]))) is not None
    ]
    return len(lines), _sha256(("\n".join(lines) + "\n").encode("utf-8"))


def _compiled_common_functions(
    *,
    treatment_symbols: Mapping[str, Mapping[str, Any]],
    control_symbols: Mapping[str, Mapping[str, Any]],
    treatment_elf: Path,
    control_elf: Path,
    objdump_tool: Path,
) -> tuple[dict[str, Any], str]:
    report: dict[str, Any] = {}
    for role, pattern in COMMON_FUNCTION_PATTERNS.items():
        if pattern == "epdInitResolutionSelected":
            treatment_name, treatment_symbol = _symbol_contains(
                treatment_symbols, pattern
            )
            control_name, control_symbol = _symbol_contains(control_symbols, pattern)
        else:
            treatment_name, treatment_symbol = _symbol_exact(treatment_symbols, pattern)
            control_name, control_symbol = _symbol_exact(control_symbols, pattern)
        treatment_records = _disassemble(
            objdump_tool, treatment_elf, treatment_name, treatment_symbol
        )
        control_records = _disassemble(
            objdump_tool, control_elf, control_name, control_symbol
        )
        treatment_count, treatment_digest = _normalized_digest(treatment_records)
        control_count, control_digest = _normalized_digest(control_records)
        _require(
            treatment_count == control_count and treatment_digest == control_digest,
            f"compiled common function {role} differs after semantic normalization",
        )
        report[role] = {
            "treatment_symbol": treatment_name,
            "control_symbol": control_name,
            "treatment_machine_bytes": int(treatment_symbol["size"]),
            "control_machine_bytes": int(control_symbol["size"]),
            "normalized_instruction_count": treatment_count,
            "normalized_instruction_sha256": treatment_digest,
            "normalized_equal": True,
            "raw_disassembly_emitted": False,
        }
    aggregate = _sha256(_canonical(report))
    return report, aggregate


def _calls(records: Sequence[Mapping[str, Any]], token: str) -> list[int]:
    return [
        index
        for index, record in enumerate(records)
        if str(record["asm"]).startswith(("call8", "callx8"))
        and token in str(record["asm"])
    ]


def _last_register_value(
    records: Sequence[Mapping[str, Any]],
    call_index: int,
    register: str,
    *,
    role_zero_register: str | None = None,
) -> int:
    for index in range(call_index - 1, max(-1, call_index - 10), -1):
        asm = str(records[index]["asm"])
        immediate = re.fullmatch(
            rf"movi(?:\.n)?\s+{re.escape(register)},\s*(0x[0-9a-fA-F]+|\d+)",
            asm,
        )
        if immediate is not None:
            return int(immediate.group(1), 0)
        moved = re.fullmatch(rf"mov(?:\.n)?\s+{re.escape(register)},\s*(a\d+)", asm)
        if moved is not None:
            if moved.group(1) == role_zero_register:
                return 0
            raise MatchedTraceAuditError(
                f"unresolved {register} source {moved.group(1)} before call"
            )
        same_or = re.fullmatch(rf"or\s+{re.escape(register)},\s*(a\d+),\s*\1", asm)
        if same_or is not None:
            if same_or.group(1) == role_zero_register:
                return 0
            raise MatchedTraceAuditError(
                f"unresolved {register} OR source {same_or.group(1)} before call"
            )
    raise MatchedTraceAuditError(f"no {register} assignment before compiled call")


def _compiled_call_surface(
    *,
    treatment_symbols: Mapping[str, Mapping[str, Any]],
    control_symbols: Mapping[str, Mapping[str, Any]],
    treatment_elf: Path,
    control_elf: Path,
    objdump_tool: Path,
) -> dict[str, Any]:
    _, treatment_display_symbol = _symbol_exact(treatment_symbols, TREATMENT_DISPLAY)
    _, treatment_upload_symbol = _symbol_exact(treatment_symbols, TREATMENT_UPLOAD)
    _, treatment_write_symbol = _symbol_exact(treatment_symbols, TREATMENT_WRITE)
    _, control_display_symbol = _symbol_exact(control_symbols, CONTROL_DISPLAY)
    _, control_write_symbol = _symbol_exact(control_symbols, CONTROL_WRITE)
    treatment_display = _disassemble(
        objdump_tool,
        treatment_elf,
        TREATMENT_DISPLAY,
        treatment_display_symbol,
    )
    treatment_upload = _disassemble(
        objdump_tool,
        treatment_elf,
        TREATMENT_UPLOAD,
        treatment_upload_symbol,
    )
    control_display = _disassemble(
        objdump_tool, control_elf, CONTROL_DISPLAY, control_display_symbol
    )
    treatment_write = _disassemble(
        objdump_tool, treatment_elf, TREATMENT_WRITE, treatment_write_symbol
    )
    control_write = _disassemble(
        objdump_tool, control_elf, CONTROL_WRITE, control_write_symbol
    )

    treatment_global_calls = _calls(treatment_display, "h3WriteFixedPayload")
    treatment_upload_calls = _calls(treatment_upload, "h3WriteFixedPayload")
    control_calls = _calls(control_display, "h3mcWriteFixedPayload")
    treatment_global = [
        {
            "command": _last_register_value(
                treatment_display, index, "a10", role_zero_register="a2"
            ),
            "data_bytes": _last_register_value(treatment_display, index, "a12"),
        }
        for index in treatment_global_calls
    ]
    treatment_upload_template = [
        {
            "command": _last_register_value(treatment_upload, index, "a10"),
            "data_bytes": _last_register_value(treatment_upload, index, "a12"),
        }
        for index in treatment_upload_calls
    ]
    control_sequence = [
        {
            "command": _last_register_value(
                control_display, index, "a10", role_zero_register="a2"
            ),
            "data_bytes": _last_register_value(control_display, index, "a12"),
        }
        for index in control_calls
    ]
    _require(
        treatment_global
        == [
            {"command": 0x00, "data_bytes": 2},
            {"command": 0x01, "data_bytes": 6},
            {"command": 0x30, "data_bytes": 1},
            {"command": 0x61, "data_bytes": 4},
        ],
        "compiled treatment global command sequence differs",
    )
    _require(
        treatment_upload_template
        == [
            {"command": 0xE9, "data_bytes": 1},
            {"command": 0x20, "data_bytes": 799},
            {"command": 0x21, "data_bytes": 704},
        ],
        "compiled treatment upload template differs",
    )
    _require(
        control_sequence
        == [
            {"command": 0x00, "data_bytes": 2},
            {"command": 0x01, "data_bytes": 6},
            {"command": 0x30, "data_bytes": 1},
            {"command": 0x61, "data_bytes": 4},
            {"command": 0xE9, "data_bytes": 1},
            {"command": 0xE9, "data_bytes": 1},
        ],
        "compiled control command sequence differs",
    )

    upload_invocations = _calls(treatment_display, "h3UploadFixedWaveformToController")
    upload_controllers = [
        _last_register_value(treatment_display, index, "a10", role_zero_register="a2")
        for index in upload_invocations
    ]
    _require(upload_controllers == [0, 1], "treatment upload CS order differs")
    _require(
        not any(
            "h3UploadFixedWaveformToController" in name for name in control_symbols
        ),
        "control ELF contains the treatment upload function",
    )
    _require(
        not any(
            "kR20Payload" in name or "kR21Payload" in name for name in control_symbols
        ),
        "control ELF contains treatment payload symbols",
    )

    treatment_dtm_calls = _calls(treatment_display, "epdStreamPackedFrameController")
    control_dtm_calls = _calls(control_display, "epdStreamPackedFrameController")
    treatment_dtm_order = [
        _last_register_value(treatment_display, index, "a11", role_zero_register="a2")
        for index in treatment_dtm_calls
    ]
    control_dtm_order = [
        _last_register_value(control_display, index, "a11", role_zero_register="a2")
        for index in control_dtm_calls
    ]
    _require(
        treatment_dtm_order == control_dtm_order == [0, 1],
        "compiled DTM CS order differs",
    )
    _require(
        len(_calls(treatment_display, "epdPrepareCascade")) == 1
        and len(_calls(control_display, "epdPrepareCascade")) == 1,
        "compiled cascade-prepare call count differs",
    )
    _require(
        len(_calls(treatment_display, "epdSecondSettingAndRefresh")) == 1
        and len(_calls(control_display, "epdSecondSettingAndRefresh")) == 1,
        "compiled refresh-closure call count differs",
    )
    _require(
        len(_calls(treatment_display, "epdWaitIdle")) == 1
        and len(_calls(treatment_upload, "epdWaitIdle")) == 1
        and len(_calls(control_display, "epdWaitIdle")) == 3,
        "compiled PWR/E9 idle-gate inventory differs",
    )
    _require(
        len(_calls(treatment_write, "epdCommand")) == 1
        and len(_calls(treatment_write, "epdData")) == 1
        and len(_calls(treatment_write, "__yield")) == 1,
        "compiled treatment payload writer call surface differs",
    )
    _require(
        len(_calls(control_write, "epdCommand")) == 1
        and len(_calls(control_write, "epdData")) == 1
        and not _calls(control_write, "__yield"),
        "compiled control payload writer call surface differs",
    )
    _require(
        any(
            re.fullmatch(r"movi\s+a5,\s*255", str(row["asm"]))
            for row in treatment_write
        ),
        "compiled treatment writer lost its 256-byte yield cadence",
    )

    return {
        "treatment_global_commands": [
            {**item, "command": f"0x{item['command']:02X}"} for item in treatment_global
        ],
        "treatment_per_controller_template": [
            {**item, "command": f"0x{item['command']:02X}"}
            for item in treatment_upload_template
        ],
        "treatment_upload_controller_order": ["CS1", "CS2"],
        "control_direct_commands": [
            {**item, "command": f"0x{item['command']:02X}"} for item in control_sequence
        ],
        "control_R20_R21_compiled_command_calls": 0,
        "control_R20_R21_payload_symbols": 0,
        "dtm_controller_order": ["CS1", "CS2"],
        "common_cascade_prepare_calls_each": 1,
        "common_refresh_closure_calls_each": 1,
        "effective_idle_gates_each": 3,
        "treatment_payload_writer_has_256_byte_yield_cadence": True,
        "control_payload_writer_has_yield": False,
        "whole_BIN_opcode_scan_performed": False,
    }


def _normalized_path(path: Path) -> str:
    resolved = path.resolve(strict=True)
    try:
        return f"repo/{resolved.relative_to(REPO_ROOT).as_posix()}"
    except ValueError:
        pass
    profile = os.environ.get("USERPROFILE")
    if profile:
        platformio_root = Path(profile).resolve() / ".platformio"
        try:
            return f"platformio/{resolved.relative_to(platformio_root).as_posix()}"
        except ValueError:
            pass
    return resolved.as_posix()


def _dependency_paths(dep_file: Path) -> list[Path]:
    text = _read_regular(dep_file, label=f"dependency file {dep_file.name}").decode(
        "utf-8"
    )
    flattened = text.replace("\\\r\n", " ").replace("\\\n", " ")
    separator = flattened.find(": ")
    _require(separator >= 0, f"dependency file {dep_file} has no target separator")
    try:
        tokens = shlex.split(flattened[separator + 2 :], posix=True)
    except ValueError as error:
        raise MatchedTraceAuditError(
            f"dependency file {dep_file} could not be parsed"
        ) from error
    result: list[Path] = []
    for token in tokens:
        candidate = Path(token)
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
        if candidate.is_file():
            result.append(candidate.resolve(strict=True))
    _require(bool(result), f"dependency file {dep_file} resolved no inputs")
    return result


def _manifest_rows(paths: Sequence[Path]) -> list[dict[str, Any]]:
    unique = {_normalized_path(path): path.resolve(strict=True) for path in paths}
    rows: list[dict[str, Any]] = []
    for normalized, path in sorted(unique.items()):
        payload = _read_regular(path, label=f"manifest input {normalized}")
        rows.append(
            {
                "path_id": normalized,
                "bytes": len(payload),
                "sha256": _sha256(payload),
            }
        )
    return rows


def _build_manifest(
    *,
    elf_path: Path,
    config_path: Path,
    nm_tool: Path,
    objdump_tool: Path,
) -> dict[str, Any]:
    build_dir = elf_path.parent
    dep_files = sorted((build_dir / "src").glob("*.d"), key=lambda path: path.name)
    object_files = sorted((build_dir / "src").glob("*.o"), key=lambda path: path.name)
    _require(
        len(dep_files) == 2, f"expected two transaction dependency files in {build_dir}"
    )
    _require(
        len(object_files) == 2, f"expected two transaction object files in {build_dir}"
    )
    dependencies: list[Path] = []
    for dep_file in dep_files:
        dependencies.extend(_dependency_paths(dep_file))
    dependency_rows = _manifest_rows(dependencies)
    local_rows = [row for row in dependency_rows if row["path_id"].startswith("repo/")]
    external_rows = [row for row in dependency_rows if row not in local_rows]

    build_inputs = [config_path, *dep_files, *object_files, build_dir / "firmware.map"]
    build_rows = _manifest_rows(build_inputs)
    tool_paths = [nm_tool, objdump_tool]
    for sibling in (
        "xtensa-esp32s3-elf-g++.exe",
        "xtensa-esp32s3-elf-gcc.exe",
        "xtensa-esp32s3-elf-ld.exe",
        "xtensa-esp32s3-elf-objcopy.exe",
    ):
        candidate = objdump_tool.parent / sibling
        if candidate.is_file():
            tool_paths.append(candidate)
    package_manifest = objdump_tool.parent.parent / "package.json"
    if package_manifest.is_file():
        tool_paths.append(package_manifest)
    tool_rows = _manifest_rows(tool_paths)

    return {
        "compiler_dependency_files": [_normalized_path(path) for path in dep_files],
        "transitive_dependency_count": len(dependency_rows),
        "transitive_dependency_manifest_sha256": _sha256(_canonical(dependency_rows)),
        "repo_local_dependencies": local_rows,
        "external_dependency_count": len(external_rows),
        "external_dependency_manifest_sha256": _sha256(_canonical(external_rows)),
        "build_inputs": build_rows,
        "build_input_manifest_sha256": _sha256(_canonical(build_rows)),
        "toolchain_files": tool_rows,
        "toolchain_manifest_sha256": _sha256(_canonical(tool_rows)),
        "dependency_contents_emitted": False,
        "map_or_object_contents_emitted": False,
    }


def _trace_event(
    event: str,
    *,
    controller: str | None = None,
    command: str | None = None,
    data_bytes: int | None = None,
    data_sha256: str | None = None,
    upload_span: bool = False,
    evidence: str,
) -> dict[str, Any]:
    item: dict[str, Any] = {"event": event, "evidence": evidence}
    if controller is not None:
        item["controller"] = controller
    if command is not None:
        item["command"] = command
    if data_bytes is not None:
        item["data_bytes"] = data_bytes
    if data_sha256 is not None:
        item["data_sha256"] = data_sha256
    if upload_span:
        item["treatment_only_upload_span"] = True
    return item


def _build_traces(
    *,
    payloads: Mapping[str, Mapping[str, Any]],
    common_digest: str,
    frame_identity: Mapping[str, Any],
) -> dict[str, Any]:
    shared_prefix = [
        _trace_event(
            "COMMON_FACTORY_CASCADE_INIT",
            evidence=f"compiled-common:{common_digest}",
        ),
        _trace_event("SELECT_BOTH_RUNTIME_CONFIG", evidence="compiled-call-immediate"),
    ]
    for command, role in (("0x00", "runtime_psr"), ("0x01", "power")):
        row = payloads[role]
        shared_prefix.append(
            _trace_event(
                "COMMAND_DATA",
                controller="BOTH",
                command=command,
                data_bytes=int(row["bytes"]),
                data_sha256=str(row["sha256"]),
                evidence="compiled-call-immediate+ELF-symbol",
            )
        )
    shared_prefix.append(
        _trace_event("BUSY_IDLE_GATE", controller="BOTH", evidence="compiled-call")
    )
    for command, role in (("0x30", "pll"), ("0x61", "tres")):
        row = payloads[role]
        shared_prefix.append(
            _trace_event(
                "COMMAND_DATA",
                controller="BOTH",
                command=command,
                data_bytes=int(row["bytes"]),
                data_sha256=str(row["sha256"]),
                evidence="compiled-call-immediate+ELF-symbol",
            )
        )

    treatment = deepcopy(shared_prefix)
    control = deepcopy(shared_prefix)
    for controller in ("CS1", "CS2"):
        retained = [
            _trace_event(
                "SELECT_CONTROLLER",
                controller=controller,
                evidence="compiled-call-argument",
            ),
            _trace_event(
                "COMMAND_DATA",
                controller=controller,
                command="0xE9",
                data_bytes=int(payloads["e9"]["bytes"]),
                data_sha256=str(payloads["e9"]["sha256"]),
                evidence="compiled-call-immediate+ELF-symbol",
            ),
            _trace_event(
                "BUSY_IDLE_GATE", controller=controller, evidence="compiled-call"
            ),
        ]
        treatment.extend(deepcopy(retained))
        control.extend(deepcopy(retained))
        for command, role in (("0x20", "r20"), ("0x21", "r21")):
            row = payloads[role]
            treatment.append(
                _trace_event(
                    "COMMAND_DATA",
                    controller=controller,
                    command=command,
                    data_bytes=int(row["bytes"]),
                    data_sha256=str(row["sha256"]),
                    upload_span=True,
                    evidence="compiled-call-immediate+ELF-symbol",
                )
            )

    suffix = [
        _trace_event(
            "DTM_STREAM",
            controller="CS1",
            data_bytes=int(frame_identity["cs1_dtm_bytes"]),
            data_sha256=str(frame_identity["cs1_dtm_sha256"]),
            evidence="compiled-common+frozen-frame-identity",
        ),
        _trace_event(
            "DTM_STREAM",
            controller="CS2",
            data_bytes=int(frame_identity["cs2_dtm_bytes"]),
            data_sha256=str(frame_identity["cs2_dtm_sha256"]),
            evidence="compiled-common+frozen-frame-identity",
        ),
        _trace_event("SELECT_BOTH_REFRESH", evidence="compiled-call-argument"),
        _trace_event(
            "COMMON_PON_DRF_POF_CLEANUP",
            evidence=f"compiled-common:{common_digest}",
        ),
    ]
    treatment.extend(deepcopy(suffix))
    control.extend(deepcopy(suffix))
    stripped = [
        event for event in treatment if not event.get("treatment_only_upload_span")
    ]
    removed = [event for event in treatment if event.get("treatment_only_upload_span")]
    _require(
        len(removed) == 4, "treatment trace does not have exactly four upload spans"
    )
    _require(stripped == control, "normalized retained trace is not exactly equal")
    _require(
        [
            (event["controller"], event["command"], event["data_bytes"])
            for event in removed
        ]
        == [
            ("CS1", "0x20", 799),
            ("CS1", "0x21", 704),
            ("CS2", "0x20", 799),
            ("CS2", "0x21", 704),
        ],
        "removed upload-span identity differs",
    )
    return {
        "treatment_events": treatment,
        "control_events": control,
        "treatment_trace_sha256": _sha256(_canonical(treatment)),
        "control_trace_sha256": _sha256(_canonical(control)),
        "stripped_treatment_trace_sha256": _sha256(_canonical(stripped)),
        "strip_exact_four_upload_spans_equals_control": True,
        "removed_upload_spans": removed,
        "removed_upload_span_count": 4,
        "retained_event_count": len(control),
    }


def audit_pair(
    *,
    treatment_release_file: Path,
    control_elf_file: Path,
    control_binary_file: Path,
    control_transaction_source_file: Path,
    nm_tool: Path | None = None,
    objdump_tool: Path | None = None,
) -> dict[str, Any]:
    """Deep-audit one exact compiled treatment/control pair offline."""

    control_contract.validate_contract(PROFILE_ID)
    nm_path = (nm_tool or _tool_default("nm")).resolve(strict=True)
    objdump_path = (objdump_tool or _tool_default("objdump")).resolve(strict=True)
    treatment_release_path = Path(treatment_release_file).resolve(strict=True)
    try:
        treatment_root = h3_release.load_release(treatment_release_path)
        treatment_summary = h3_release.validate_release(treatment_root)
    except h3_release.RuntimeLutReleaseError as error:
        raise MatchedTraceAuditError(
            f"treatment release validation failed: {error}"
        ) from error
    _require(treatment_root["profile_id"] == PROFILE_ID, "treatment profile differs")
    runtime = treatment_root["compiled_images"]["runtime"]
    treatment_elf = Path(runtime["firmware"]["elf"]["path"]).resolve(strict=True)
    treatment_binary = Path(runtime["firmware"]["binary"]["path"]).resolve(strict=True)
    treatment_elf_payload = _read_regular(treatment_elf, label="treatment ELF")
    treatment_binary_payload = _read_regular(treatment_binary, label="treatment binary")
    _require(
        _sha256(treatment_elf_payload) == runtime["firmware"]["elf"]["sha256"],
        "treatment release ELF hash differs",
    )
    _require(
        _sha256(treatment_binary_payload) == runtime["firmware"]["binary"]["sha256"],
        "treatment release binary hash differs",
    )

    control_elf = Path(control_elf_file).resolve(strict=True)
    control_binary = Path(control_binary_file).resolve(strict=True)
    control_source = Path(control_transaction_source_file).resolve(strict=True)
    try:
        control_identity = control_compiled.validate_image(
            PROFILE_ID,
            control_contract.ROLE_CONTROL,
            elf_file=control_elf,
            binary_file=control_binary,
            transaction_source_file=control_source,
        )
    except control_compiled.MatchedControlCompiledIdentityError as error:
        raise MatchedTraceAuditError(
            f"control compiled identity failed: {error}"
        ) from error
    control_elf_payload = _read_regular(control_elf, label="control ELF")

    treatment_symbols = _nm_symbols(nm_path, treatment_elf)
    control_symbols = _nm_symbols(nm_path, control_elf)
    treatment_raw, treatment_payload_report = _payloads(
        treatment_elf_payload, treatment_symbols, TREATMENT_PAYLOAD_SYMBOLS
    )
    control_raw, control_payload_report = _payloads(
        control_elf_payload, control_symbols, CONTROL_PAYLOAD_SYMBOLS
    )
    for role, expected in EXPECTED_SMALL_PAYLOADS.items():
        _require(treatment_raw[role] == expected, f"treatment {role} payload differs")
        _require(control_raw[role] == expected, f"control {role} payload differs")
        _require(
            treatment_raw[role] == control_raw[role],
            f"treatment/control {role} payload differs",
        )
    _require(len(treatment_raw["r20"]) == 799, "treatment R20 length differs")
    _require(_sha256(treatment_raw["r20"]) == EXPECTED_R20_SHA256, "R20 hash differs")
    _require(len(treatment_raw["r21"]) == 704, "treatment R21 length differs")
    _require(_sha256(treatment_raw["r21"]) == EXPECTED_R21_SHA256, "R21 hash differs")
    _require(treatment_raw["r21"] == b"\xff" * 704, "treatment R21 is not all FF")

    common_functions, common_digest = _compiled_common_functions(
        treatment_symbols=treatment_symbols,
        control_symbols=control_symbols,
        treatment_elf=treatment_elf,
        control_elf=control_elf,
        objdump_tool=objdump_path,
    )
    call_surface = _compiled_call_surface(
        treatment_symbols=treatment_symbols,
        control_symbols=control_symbols,
        treatment_elf=treatment_elf,
        control_elf=control_elf,
        objdump_tool=objdump_path,
    )
    combined_payload_report = deepcopy(treatment_payload_report)
    for role in EXPECTED_SMALL_PAYLOADS:
        combined_payload_report[role]["control_symbol"] = control_payload_report[role][
            "symbol"
        ]
        combined_payload_report[role]["treatment_control_exact_equal"] = True

    frame_identity = runtime["transaction_descriptor"]["payload_identity"]
    control_frame_identity = control_identity["transaction_descriptor"][
        "payload_identity"
    ]
    _require(
        frame_identity == control_frame_identity,
        "treatment/control frozen frame and DTM identity differs",
    )
    traces = _build_traces(
        payloads=combined_payload_report,
        common_digest=common_digest,
        frame_identity=frame_identity,
    )

    treatment_manifest = _build_manifest(
        elf_path=treatment_elf,
        config_path=TREATMENT_CONFIG,
        nm_tool=nm_path,
        objdump_tool=objdump_path,
    )
    control_manifest = _build_manifest(
        elf_path=control_elf,
        config_path=CONTROL_CONFIG,
        nm_tool=nm_path,
        objdump_tool=objdump_path,
    )

    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "valid": True,
        "profile_id": PROFILE_ID,
        "classification": ("E9_ONLY_NO_R20_R21_COMMAND_STREAM_AND_DURATION_CONTROL"),
        "scope": {
            "offline_read_only": True,
            "hardware_accessed": False,
            "serial_or_COM_accessed": False,
            "device_network_accessed": False,
            "firmware_written_or_flashed": False,
            "visible_refresh_requested": False,
            "raw_payload_or_disassembly_emitted": False,
        },
        "identity": {
            "treatment_release": {
                "path": str(treatment_release_path),
                "release_id": treatment_root["release_id"],
                "canonical_sha256": treatment_summary["canonical_sha256"],
            },
            "treatment_elf": _file_record(treatment_elf, label="treatment ELF"),
            "treatment_binary": _file_record(
                treatment_binary, label="treatment binary"
            ),
            "control_elf": _file_record(control_elf, label="control ELF"),
            "control_binary": _file_record(control_binary, label="control binary"),
            "control_transaction_descriptor_sha256": control_identity[
                "transaction_descriptor_sha256"
            ],
            "control_hardware_action_id": control_identity["hardware_action_id"],
        },
        "compiled_payload_symbols": combined_payload_report,
        "compiled_call_surface": call_surface,
        "compiled_common_functions": {
            "aggregate_sha256": common_digest,
            "all_normalized_equal": True,
            "normalization": (
                "drop alignment zero bytes; normalize Xtensa narrow aliases, "
                "same-register OR-as-move, addresses, constprop ordinals, and "
                "section-relative branch labels; retain operations/registers/immediates/callees"
            ),
            "functions": common_functions,
        },
        "normalized_trace": traces,
        "transitive_build_manifest": {
            "treatment": treatment_manifest,
            "control": control_manifest,
        },
        "causal_scope": {
            "strict_payload_only_control": False,
            "time_matched_control": False,
            "fixed_duration_quiet_slot_present": False,
            "dummy_or_empty_R20_R21_writes_in_control": False,
            "treatment_only_SPI_bytes_per_controller": 1_505,
            "treatment_only_selected_CS_transitions_per_controller": 3_010,
            "treatment_only_source_yields_per_controller": 5,
            "wall_clock_upload_duration_measured": False,
            "T_equals_C_classification": "NO_DETECTABLE_INCREMENTAL_EFFECT",
            "T_not_equal_C_classification": (
                "INCREMENTAL_VISIBLE_EFFECT_OF_COMBINED_R20_R21_COMMAND_STREAM"
            ),
            "T_not_equal_C_proves_799_704_ABI": False,
            "T_not_equal_C_distinguishes_R20_from_R21": False,
            "controller_acceptance_or_readback_proven": False,
            "single_BUSY_proves_CS2_state": False,
        },
        "evidence_boundaries": {
            "compiled_sender_path_proven": True,
            "controller_received_or_accepted_payload_proven": False,
            "complete_dynamic_instruction_trace_proven": False,
            "normalized_common_function_equivalence_is_not_literal_pointer_equivalence": True,
            "payload_literals_are_independently_hashed_from_ELF_symbols": True,
            "framework_dependency_contents_are_hashed_not_emitted": True,
            "whole_binary_opcode_absence_is_not_used": True,
        },
        "execution_eligible_after_this_audit_alone": False,
        "live_authorized": False,
    }
    result = _seal(unsigned)
    validate_seal(result)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--treatment-release", type=Path, required=True)
    parser.add_argument("--control-elf", type=Path, required=True)
    parser.add_argument("--control-binary", type=Path, required=True)
    parser.add_argument("--control-transaction-source", type=Path, required=True)
    parser.add_argument("--nm", type=Path)
    parser.add_argument("--objdump", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = audit_pair(
            treatment_release_file=args.treatment_release,
            control_elf_file=args.control_elf,
            control_binary_file=args.control_binary,
            control_transaction_source_file=args.control_transaction_source,
            nm_tool=args.nm,
            objdump_tool=args.objdump,
        )
    except (MatchedTraceAuditError, OSError, KeyError, TypeError) as error:
        print(f"matched trace audit error: {error}", file=sys.stderr)
        return 2
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
