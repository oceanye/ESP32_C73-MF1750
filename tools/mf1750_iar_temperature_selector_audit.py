#!/usr/bin/env python3
"""Reproduce the legacy E2801/E2802 temperature-selector disassembly audit.

The audit links each exact delivered UBROF10 object in a fresh ASCII-only
temporary directory.  It uses an identity-pinned official IAR XLINK and an
identity-pinned TI-distributed MSP430 GNU objdump.  All unresolved externals
are assigned deterministic *synthetic* addresses, and only
``Upload_Temperature_LUT`` is retained as a link root.

The resulting Intel HEX is checksum-validated before its address map is
compared with objdump.  The report contains identities, hashes, counts,
semantic conclusions, and evidence boundaries only.  It never contains raw
object code, disassembly, LUT/payload bytes, or a hardware execution path.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
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


KIND = "mf1750-iar-temperature-selector-audit"
SCHEMA_VERSION = 1

XLINK_VERSION = "6.1.3.56"
XLINK_VERSION_BANNER = f"IAR Universal Linker V{XLINK_VERSION}"
EXPECTED_XLINK = {
    "size_bytes": 1_806_336,
    "sha256": "99295d17da4d125f421ec7fe6524e1ed6c3753b80fa87b9e1c7ba320ea469d6c",
}

OBJDUMP_VERSION = "2.26.20160125"
OBJDUMP_VERSION_BANNER = (
    f"GNU objdump (Mitto Systems Limited - msp430-gcc 7.3.2.154) {OBJDUMP_VERSION}"
)
EXPECTED_OBJDUMP = {
    "size_bytes": 993_964,
    "sha256": "9ff1039e992f653dd9e26d4322e33a4d820234d8d6d674674082e4592e80cacb",
}

TI_MSP430_GCC_SOURCE = (
    "https://software-dl.ti.com/msp430/msp430_public_sw/mcu/msp430/"
    "MSPGCC/6_1_0_0/index_FDS.html"
)
TI_MSP430_GCC_ARCHIVE = {
    "filename": "msp430-gcc-7.3.2.154_win64.7z",
    "size_bytes": 19_602_448,
    "sha256": "b49c53f716069b6ce6bc1c7cd913dc5d938fc9081c57519b139091126eeb6ef0",
}
TI_IAR_ARCHIVE = {
    "filename": "slac050ba.fresh.zip",
    "size_bytes": 385_225_224,
    "sha256": "af0453d7ea0b25975060ce160f079ffab5f6b84f103458fcbb036a933b338c6f",
}

LINK_ROOT = "Upload_Temperature_LUT"
CODE_PLACEMENT = "-Z(CODE)CODE=10000-EFFFF"
DATA_PLACEMENT = "-Z(DATA)DATA16_Z,DATA16_C,CSTACK,DATA16_AN=0200-FFFF"
EXTERNAL_DEFINITIONS = (
    ("delay", 0xF0000),
    ("?ShiftLeft32_12", 0xF0010),
    ("?Mul32", 0xF0020),
    ("ReadData", 0xF0030),
    ("Section_Erase", 0xF0040),
    ("Page_Program", 0xF0050),
    ("?cstart_init_zero", 0xF0060),
    ("?longjmp_r4", 0xF0070),
    ("?longjmp_r5", 0xF0080),
    ("?setjmp_r4", 0xF0090),
    ("?setjmp_r5", 0xF00A0),
)


EXPECTED_LINKS: dict[str, dict[str, Any]] = {
    "E2801.r43": {
        "source_size_bytes": 315_632,
        "source_sha256": (
            "404b950ea65b754a335b90be24683281ebee9dab52e362fd6d49170b4b8a38a3"
        ),
        "ubrof_version_byte": 10,
        "intel_hex_size_bytes": 1_957,
        "intel_hex_sha256": (
            "6a7caf73896ffc26d65673a5ab050a7b2536f215a1d26590aab5f93ad5b1631d"
        ),
        "emitted_memory_bytes": 684,
        "emitted_address_start": 0x10000,
        "emitted_address_end_inclusive": 0x102AB,
        "address_byte_manifest_sha256": (
            "902a87a337de565ab666a4bf3bc2be90a0c5339e3464aab964ba9ed49d587243"
        ),
        "xlink_code_bytes": 684,
        "xlink_data_bytes": 2_561,
        "xlink_absolute_symbols": 11,
        "function_start": 0x1002E,
        "function_end_exclusive": 0x1012A,
        "function_bytes": 252,
        "function_sha256": (
            "bbf72104f4f7d576fc801b6a869a7351e69240b9bdb430dad359af574c5de697"
        ),
        "function_instruction_lines": 94,
        "normalized_disassembly_bytes": 3_813,
        "normalized_disassembly_sha256": (
            "f8b246824aafc57a38d2dc9cf74883ef2d5d2049ec059a31cb41295b60b7896e"
        ),
    },
    "E2802.r43": {
        "source_size_bytes": 328_062,
        "source_sha256": (
            "19fb74c05444880ea6a403d697307e47a874998b5529ee84dd0592ecae16c9ce"
        ),
        "ubrof_version_byte": 10,
        "intel_hex_size_bytes": 1_364,
        "intel_hex_sha256": (
            "b5fea7e06a54bf1e28d24fbe3e3bd3cde0db034b1d36e7cb31b6862de49561e6"
        ),
        "emitted_memory_bytes": 472,
        "emitted_address_start": 0x10000,
        "emitted_address_end_inclusive": 0x101D7,
        "address_byte_manifest_sha256": (
            "2afcf41d770a0e03226ea7ac5678df2bc8b05a6c2375efb7ea9b24e1af167b8e"
        ),
        "xlink_code_bytes": 472,
        "xlink_data_bytes": 2_560,
        "xlink_absolute_symbols": 11,
        "function_start": 0x10020,
        "function_end_exclusive": 0x100E0,
        "function_bytes": 192,
        "function_sha256": (
            "73486fe35326c8c3fd2b58b1d0e5f3f69f942be125ef653612e505a7d79346dc"
        ),
        "function_instruction_lines": 77,
        "normalized_disassembly_bytes": 3_078,
        "normalized_disassembly_sha256": (
            "7165f94b46a1fdef4ee2aab9900e78371bdea42f88612d021dbecea529f6430e"
        ),
    },
}


# These are deliberately targeted semantic anchors, not a raw disassembly
# transcript.  Whole-function byte and normalized-line hashes close the gaps
# between the selected anchors.
EXPECTED_INSTRUCTIONS: dict[str, dict[int, str]] = {
    "E2801.r43": {
        0x10038: "mov.b #64, r12",
        0x1003C: "calla #65834",
        0x10040: "calla #65536",
        0x10044: "mov #25, r9",
        0x10048: "calla #66082",
        0x10052: "cmp #30, r10",
        0x10058: "mov r10, r12",
        0x1005A: "mov r11, r13",
        0x1005C: "mov #4096, r14",
        0x10062: "calla #983072",
        0x10066: "add #4096, r12",
        0x10076: "mov #2, r15",
        0x1007E: "calla #983088",
        0x10082: "inc r10",
        0x10088: "mov.b #1, r8",
        0x1008A: "mov.b @r1, r15",
        0x1008E: "cmp r15, r9",
        0x10090: "jge $+20",
        0x10094: "mov.b 1(r1), r15",
        0x1009A: "cmp r15, r9",
        0x1009C: "jl $+8",
        0x100B2: "jnz $-102",
        0x100B4: "cmp.b #0, r8",
        0x100B6: "jnz $+108",
        0x100B8: "mov #2508, r15",
        0x100BC: "mov #580, r14",
        0x100C4: "calla #983088",
        0x100C8: "cmp.b #1, &0x0c44",
        0x100D4: "mov.b &0x0246,r12",
        0x100D8: "bis.b #32, r12",
        0x100E8: "mov.b &0x0246,r12",
        0x100EC: "and.b #223, r12",
        0x100F4: "mov #799, r14",
        0x100F8: "mov #584, r13",
        0x100FC: "mov #32, r12",
        0x10100: "calla #65550",
        0x10104: "mov.b #33, r12",
        0x10110: "mov.b #-1, r12",
        0x10118: "cmp #704, r11",
        0x1011C: "jl $-12",
        0x10128: "reta",
    },
    "E2802.r43": {
        0x1002A: "mov #25, r9",
        0x10034: "cmp #30, r10",
        0x1003A: "mov r10, r12",
        0x1003C: "mov r11, r13",
        0x1003E: "mov #4096, r14",
        0x10044: "calla #983072",
        0x10048: "add #4096, r12",
        0x10058: "mov #2, r15",
        0x10060: "calla #983088",
        0x10064: "inc r10",
        0x1006A: "mov.b #1, r8",
        0x1006C: "mov.b @r1, r15",
        0x10070: "cmp r15, r9",
        0x10072: "jge $+20",
        0x10076: "mov.b 1(r1), r15",
        0x1007C: "cmp r15, r9",
        0x1007E: "jl $+8",
        0x10094: "jnz $-102",
        0x10096: "cmp.b #0, r8",
        0x10098: "jnz $+64",
        0x1009A: "mov #2508, r15",
        0x1009E: "mov #580, r14",
        0x100A6: "calla #983088",
        0x100AA: "mov #799, r14",
        0x100AE: "mov #584, r13",
        0x100B2: "mov #32, r12",
        0x100B6: "calla #65536",
        0x100BA: "mov.b #33, r12",
        0x100C6: "mov.b #-1, r12",
        0x100CE: "cmp #704, r11",
        0x100D2: "jl $-12",
        0x100DE: "reta",
    },
}


class TemperatureSelectorAuditError(RuntimeError):
    """An input identity, tool output, or semantic invariant changed."""


@dataclass(frozen=True)
class IntelHexImage:
    """A checksum-validated, non-overlapping Intel HEX address map."""

    memory: dict[int, int]
    record_count: int
    data_record_count: int
    extended_segment_records: int
    extended_linear_records: int


@dataclass(frozen=True)
class ObjdumpInstruction:
    """One parsed objdump instruction; raw text remains process-local."""

    address: int
    encoded_bytes: bytes
    normalized_instruction: str
    stripped_line: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TemperatureSelectorAuditError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pin_file(path: Path, expected: dict[str, Any], label: str) -> bytes:
    _require(path.is_file(), f"{label} is missing: {path}")
    payload = path.read_bytes()
    _require(
        len(payload) == expected["size_bytes"],
        f"{label} size mismatch: expected {expected['size_bytes']}, got {len(payload)}",
    )
    digest = _sha256(payload)
    _require(
        digest == expected["sha256"],
        f"{label} SHA-256 mismatch: expected {expected['sha256']}, got {digest}",
    )
    return payload


def _pin_tool(
    path: Path,
    expected: dict[str, Any],
    *,
    label: str,
    version_args: list[str],
    version_banner: str,
    encoding: str,
) -> dict[str, Any]:
    payload = _pin_file(path, expected, label)
    completed = subprocess.run(
        [str(path), *version_args],
        check=False,
        capture_output=True,
        timeout=30,
    )
    output = (completed.stdout + completed.stderr).decode(encoding)
    _require(completed.returncode == 0, f"{label} version probe failed")
    _require(version_banner in output, f"{label} version banner changed")
    return {
        "version": XLINK_VERSION if label == "XLINK" else OBJDUMP_VERSION,
        "size_bytes": len(payload),
        "sha256": _sha256(payload),
        "version_banner_sha256": _sha256(version_banner.encode("utf-8")),
    }


def parse_intel_hex(payload: bytes) -> IntelHexImage:
    """Parse Intel HEX types 00/01/02/04 with checksum and overlap checks."""

    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError as error:
        raise TemperatureSelectorAuditError("Intel HEX is not ASCII") from error

    memory: dict[int, int] = {}
    base_address = 0
    record_count = 0
    data_record_count = 0
    segment_records = 0
    linear_records = 0
    eof_seen = False

    for line_number, line in enumerate(text.splitlines(), start=1):
        _require(not eof_seen, "Intel HEX has records after EOF")
        _require(bool(line) and line.startswith(":"), f"invalid HEX line {line_number}")
        encoded = line[1:]
        _require(len(encoded) % 2 == 0, f"odd HEX length on line {line_number}")
        try:
            record = bytes.fromhex(encoded)
        except ValueError as error:
            raise TemperatureSelectorAuditError(
                f"non-hexadecimal Intel HEX line {line_number}"
            ) from error
        _require(len(record) >= 5, f"short Intel HEX line {line_number}")
        byte_count = record[0]
        _require(
            len(record) == byte_count + 5,
            f"Intel HEX byte count mismatch on line {line_number}",
        )
        _require(
            sum(record) & 0xFF == 0,
            f"Intel HEX checksum mismatch on line {line_number}",
        )
        offset = int.from_bytes(record[1:3], "big")
        record_type = record[3]
        data = record[4:-1]
        record_count += 1

        if record_type == 0x00:
            _require(
                offset + byte_count <= 0x10000, "Intel HEX data crosses a 64K window"
            )
            absolute = base_address + offset
            _require(
                absolute + byte_count <= 0x1_0000_0000,
                "Intel HEX address exceeds 32 bits",
            )
            for index, value in enumerate(data):
                address = absolute + index
                _require(
                    address not in memory, f"Intel HEX data overlap at 0x{address:X}"
                )
                memory[address] = value
            data_record_count += 1
        elif record_type == 0x01:
            _require(byte_count == 0 and offset == 0, "malformed Intel HEX EOF")
            eof_seen = True
        elif record_type == 0x02:
            _require(
                byte_count == 2 and offset == 0, "malformed segment-address record"
            )
            base_address = int.from_bytes(data, "big") << 4
            segment_records += 1
        elif record_type == 0x04:
            _require(byte_count == 2 and offset == 0, "malformed linear-address record")
            base_address = int.from_bytes(data, "big") << 16
            linear_records += 1
        else:
            raise TemperatureSelectorAuditError(
                f"unsupported Intel HEX record type 0x{record_type:02X}"
            )

    _require(record_count > 0, "Intel HEX is empty")
    _require(eof_seen, "Intel HEX EOF record is missing")
    _require(bool(memory), "Intel HEX contains no data")
    return IntelHexImage(
        memory=memory,
        record_count=record_count,
        data_record_count=data_record_count,
        extended_segment_records=segment_records,
        extended_linear_records=linear_records,
    )


def _address_byte_manifest_sha256(memory: dict[int, int]) -> str:
    digest = hashlib.sha256()
    for address in sorted(memory):
        _require(0 <= address <= 0xFFFF_FFFF, "address manifest exceeds 32 bits")
        digest.update(address.to_bytes(4, "little"))
        digest.update(bytes((memory[address],)))
    return digest.hexdigest()


def parse_objdump_instructions(payload: bytes) -> list[ObjdumpInstruction]:
    """Parse instruction rows using objdump's tab-separated MSP430 layout."""

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise TemperatureSelectorAuditError("objdump output is not UTF-8") from error

    instructions: list[ObjdumpInstruction] = []
    seen_addresses: set[int] = set()
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        address_text = parts[0].strip()
        if not re.fullmatch(r"[0-9A-Fa-f]+:", address_text):
            continue
        byte_tokens = parts[1].strip().split()
        if not byte_tokens or any(
            re.fullmatch(r"[0-9A-Fa-f]{2}", token) is None for token in byte_tokens
        ):
            continue
        address = int(address_text[:-1], 16)
        _require(
            address not in seen_addresses, f"duplicate objdump address 0x{address:X}"
        )
        normalized_parts: list[str] = []
        for field in parts[2:]:
            stripped = field.strip()
            if stripped.startswith(";"):
                break
            if stripped:
                normalized_parts.append(stripped)
        if not normalized_parts:
            continue
        instructions.append(
            ObjdumpInstruction(
                address=address,
                encoded_bytes=bytes.fromhex("".join(byte_tokens)),
                normalized_instruction=" ".join(normalized_parts),
                stripped_line=line.strip(),
            )
        )
        seen_addresses.add(address)
    _require(bool(instructions), "objdump emitted no parseable instructions")
    return instructions


def _link_arguments(output: Path, object_copy: Path) -> list[str]:
    return [
        "-Fintel-extended",
        "-o",
        str(output),
        "-cmsp430",
        CODE_PLACEMENT,
        DATA_PLACEMENT,
        *(f"-D{name}=0x{address:X}" for name, address in EXTERNAL_DEFINITIONS),
        f"-g{LINK_ROOT}",
        str(object_copy),
    ]


def _parse_xlink_summary(payload: bytes) -> dict[str, int]:
    text = payload.decode("cp1252")
    _require(XLINK_VERSION_BANNER in text, "XLINK link banner changed")
    _require("Errors: none" in text, "XLINK reported errors")
    _require("Warnings: none" in text, "XLINK reported warnings")
    code_match = re.search(r"(?m)^\s*([0-9][0-9 ]*) bytes of CODE memory\s*$", text)
    data_match = re.search(
        r"(?m)^\s*([0-9][0-9 ]*) bytes of DATA memory "
        r"\(\+\s*([0-9][0-9 ]*) absolute \)\s*$",
        text,
    )
    _require(code_match is not None, "XLINK CODE count is missing")
    _require(data_match is not None, "XLINK DATA count is missing")

    def number(match: re.Match[str], group: int) -> int:
        return int(match.group(group).replace(" ", ""))

    return {
        "code_bytes": number(code_match, 1),
        "data_bytes": number(data_match, 1),
        "absolute_symbols": number(data_match, 2),
    }


def _assert_function(
    name: str,
    image: IntelHexImage,
    instructions: list[ObjdumpInstruction],
) -> dict[str, Any]:
    expected = EXPECTED_LINKS[name]
    addresses = sorted(image.memory)
    _require(
        len(addresses) == expected["emitted_memory_bytes"],
        f"{name} emitted byte count changed",
    )
    _require(
        addresses[0] == expected["emitted_address_start"]
        and addresses[-1] == expected["emitted_address_end_inclusive"],
        f"{name} emitted address range changed",
    )
    _require(
        addresses == list(range(addresses[0], addresses[-1] + 1)),
        f"{name} emitted image is no longer contiguous",
    )
    manifest_sha = _address_byte_manifest_sha256(image.memory)
    _require(
        manifest_sha == expected["address_byte_manifest_sha256"],
        f"{name} address-byte manifest changed",
    )

    start = int(expected["function_start"])
    end = int(expected["function_end_exclusive"])
    function_payload = bytes(image.memory[address] for address in range(start, end))
    _require(
        len(function_payload) == expected["function_bytes"],
        f"{name} function size changed",
    )
    function_sha = _sha256(function_payload)
    _require(
        function_sha == expected["function_sha256"],
        f"{name} function SHA-256 changed",
    )

    function_rows = [row for row in instructions if start <= row.address < end]
    _require(
        len(function_rows) == expected["function_instruction_lines"],
        f"{name} instruction-line count changed",
    )
    _require(
        sum(len(row.encoded_bytes) for row in function_rows) == len(function_payload),
        f"{name} objdump rows do not cover the complete function",
    )
    for row in function_rows:
        observed = bytes(
            image.memory[address]
            for address in range(row.address, row.address + len(row.encoded_bytes))
        )
        _require(observed == row.encoded_bytes, f"{name} objdump/HEX byte mismatch")

    normalized_payload = (
        "\n".join(row.stripped_line for row in function_rows) + "\n"
    ).encode("utf-8")
    _require(
        len(normalized_payload) == expected["normalized_disassembly_bytes"],
        f"{name} normalized disassembly length changed",
    )
    normalized_sha = _sha256(normalized_payload)
    _require(
        normalized_sha == expected["normalized_disassembly_sha256"],
        f"{name} normalized disassembly SHA-256 changed",
    )

    by_address = {row.address: row.normalized_instruction for row in function_rows}
    for address, expected_instruction in EXPECTED_INSTRUCTIONS[name].items():
        _require(
            by_address.get(address) == expected_instruction,
            f"{name} semantic instruction changed at 0x{address:X}",
        )
    r9_references = [
        row.normalized_instruction
        for row in function_rows
        if re.search(r"(?:^|[ ,])r9(?:$|[ ,])", row.normalized_instruction)
    ]
    _require(
        r9_references == ["mov #25, r9", "cmp r15, r9", "cmp r15, r9"],
        f"{name} selector-register use changed",
    )
    instruction_text = "\n".join(row.normalized_instruction for row in function_rows)
    if name == "E2801.r43":
        _require("&0x0247" not in instruction_text, "E2801 dataBuff[3] became used")
    else:
        _require("&0x0246" not in instruction_text, "E2802 dataBuff[2] became used")
        _require("&0x0247" not in instruction_text, "E2802 dataBuff[3] became used")
        _require("mov.b #64, r12" not in instruction_text, "E2802 gained TSC command")

    return {
        "intel_hex_size_bytes": expected["intel_hex_size_bytes"],
        "intel_hex_sha256": expected["intel_hex_sha256"],
        "intel_hex_record_count": image.record_count,
        "intel_hex_data_record_count": image.data_record_count,
        "intel_hex_extended_segment_records": image.extended_segment_records,
        "intel_hex_extended_linear_records": image.extended_linear_records,
        "emitted_memory_bytes": len(addresses),
        "emitted_address_start": f"0x{addresses[0]:X}",
        "emitted_address_end_inclusive": f"0x{addresses[-1]:X}",
        "address_byte_manifest_sha256": manifest_sha,
        "function": {
            "name": LINK_ROOT,
            "synthetic_start": f"0x{start:X}",
            "synthetic_end_inclusive": f"0x{end - 1:X}",
            "byte_count": len(function_payload),
            "sha256": function_sha,
            "instruction_line_count": len(function_rows),
            "normalized_disassembly_bytes": len(normalized_payload),
            "normalized_disassembly_sha256": normalized_sha,
        },
    }


def _run_one(
    name: str,
    object_path: Path,
    xlink_path: Path,
    objdump_path: Path,
) -> dict[str, Any]:
    expected = EXPECTED_LINKS[name]
    source_identity = {
        "size_bytes": expected["source_size_bytes"],
        "sha256": expected["source_sha256"],
    }
    source_payload = _pin_file(object_path, source_identity, name)
    _require(
        source_payload[1] == expected["ubrof_version_byte"],
        f"{name} UBROF version byte changed",
    )

    with tempfile.TemporaryDirectory(prefix="mf1750-iar-selector-") as temp_name:
        _require(temp_name.isascii(), "temporary link path is not ASCII-only")
        temp_dir = Path(temp_name)
        object_copy = temp_dir / name
        output_path = temp_dir / "out.hex"
        shutil.copyfile(object_path, object_copy)
        _require(
            _sha256(object_copy.read_bytes()) == expected["source_sha256"],
            f"{name} temporary copy identity changed",
        )

        environment = os.environ.copy()
        environment.pop("XLINK_ENVPAR", None)
        completed = subprocess.run(
            [str(xlink_path), *_link_arguments(output_path, object_copy)],
            cwd=temp_dir,
            env=environment,
            check=False,
            capture_output=True,
            timeout=30,
        )
        _require(completed.returncode == 0, f"{name} XLINK failed")
        _require(not completed.stderr, f"{name} XLINK unexpectedly used stderr")
        link_counts = _parse_xlink_summary(completed.stdout)
        _require(output_path.is_file(), f"{name} XLINK did not emit Intel HEX")
        intel_hex = output_path.read_bytes()
        _require(
            len(intel_hex) == expected["intel_hex_size_bytes"],
            f"{name} Intel HEX size changed",
        )
        _require(
            _sha256(intel_hex) == expected["intel_hex_sha256"],
            f"{name} Intel HEX SHA-256 changed",
        )
        _require(
            link_counts
            == {
                "code_bytes": expected["xlink_code_bytes"],
                "data_bytes": expected["xlink_data_bytes"],
                "absolute_symbols": expected["xlink_absolute_symbols"],
            },
            f"{name} XLINK memory summary changed",
        )

        image = parse_intel_hex(intel_hex)
        disassembly = subprocess.run(
            [str(objdump_path), "-D", "-b", "ihex", "-m", "msp:14", str(output_path)],
            cwd=temp_dir,
            check=False,
            capture_output=True,
            timeout=30,
        )
        _require(disassembly.returncode == 0, f"{name} objdump failed")
        _require(not disassembly.stderr, f"{name} objdump unexpectedly used stderr")
        _require(b"file format ihex" in disassembly.stdout, "objdump format changed")
        instructions = parse_objdump_instructions(disassembly.stdout)
        linked = _assert_function(name, image, instructions)
        linked["xlink_summary"] = link_counts

    return {
        "source_object": {
            "name": name,
            "size_bytes": len(source_payload),
            "sha256": _sha256(source_payload),
            "ubrof_version_byte": source_payload[1],
        },
        "synthetic_linked_image": linked,
    }


def _semantic_facts(name: str) -> dict[str, Any]:
    common: dict[str, Any] = {
        "selector_temperature_source": "fixed_immediate",
        "selector_temperature_celsius": 25,
        "temperature_slot_count": 30,
        "first_logical_slot_address": "0x1000",
        "logical_slot_stride_bytes": "0x1000",
        "last_logical_slot_address": "0x1E000",
        "slot_header_read_bytes": 2,
        "match_predicate": "header[1] <= 25 < header[0]",
        "first_matching_slot_wins": True,
        "no_match_status": 1,
        "no_match_skips_bulk_read_and_lut_upload": True,
        "matched_slot_bulk_read_bytes": 2508,
        "bulk_read_uses_same_selected_logical_address": True,
        "lut0_command": "0x20",
        "lut0_source_offset_in_dataBuff": 4,
        "lut0_byte_count": 799,
        "lut1_command": "0x21",
        "lut1_byte_count": 704,
        "lut1_byte_value": "0xFF",
        "lut1_is_generated_loop_not_dataBuff": True,
        "current_800_byte_runtime_wrapper_abi_proven": False,
    }
    if name == "E2801.r43":
        common.update(
            {
                "tsc_command_0x40_before_selection": True,
                "busy_wait_after_tsc_command": True,
                "spi_get_data_called": True,
                "spi_get_data_result_register": "R12",
                "spi_get_data_result_copied_to_selector_register": False,
                "selector_register": "R9",
                "psr_write_inside_upload": True,
                "psr_source": "dataBuff[2]",
                "psr_bytes_written": 1,
                "psr_v_mode_transform": "OR 0x20 or AND 0xDF",
                "dataBuff_3_used_inside_upload": False,
            }
        )
    else:
        common.update(
            {
                "tsc_command_0x40_before_selection": False,
                "spi_get_data_called": False,
                "selector_register": "R9",
                "psr_write_inside_upload": False,
                "dataBuff_2_used_inside_upload": False,
                "dataBuff_3_used_inside_upload": False,
            }
        )
    return common


def build_report(
    xlink_path: Path,
    objdump_path: Path,
    iar_root: Path = graph.DEFAULT_IAR_ROOT,
) -> dict[str, Any]:
    """Run the deterministic two-object audit and return metadata-only JSON."""

    xlink_identity = _pin_tool(
        xlink_path,
        EXPECTED_XLINK,
        label="XLINK",
        version_args=[],
        version_banner=XLINK_VERSION_BANNER,
        encoding="cp1252",
    )
    objdump_identity = _pin_tool(
        objdump_path,
        EXPECTED_OBJDUMP,
        label="objdump",
        version_args=["--version"],
        version_banner=OBJDUMP_VERSION_BANNER,
        encoding="utf-8",
    )

    object_dir = iar_root / graph.OBJECT_DIR_REL
    objects: dict[str, Any] = {}
    for name in EXPECTED_LINKS:
        row = _run_one(name, object_dir / name, xlink_path, objdump_path)
        row["semantic_facts"] = _semantic_facts(name)
        objects[name.removesuffix(".r43")] = row

    external_manifest = [
        {"symbol": name, "synthetic_address": f"0x{address:X}"}
        for name, address in EXTERNAL_DEFINITIONS
    ]
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "scope": {
            "source_objects": 2,
            "source_objects_modified": False,
            "temporary_copies_only": True,
            "temporary_paths_ascii_only": True,
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "device_network_accessed": False,
            "flashed": False,
            "visible_refreshes": 0,
            "live_token_or_claim_generated": False,
            "raw_object_code_emitted": False,
            "raw_disassembly_emitted": False,
            "raw_waveform_or_payload_emitted": False,
        },
        "identity": {
            "xlink": xlink_identity,
            "objdump": objdump_identity,
            "tool_distribution_provenance": {
                "xlink_archive": TI_IAR_ARCHIVE,
                "objdump_archive": TI_MSP430_GCC_ARCHIVE,
                "objdump_official_source": TI_MSP430_GCC_SOURCE,
            },
        },
        "deterministic_synthetic_link_contract": {
            "output_format": "intel-extended",
            "processor": "msp430",
            "code_placement": "CODE=0x10000..0xEFFFF",
            "data_segments": ["DATA16_Z", "DATA16_C", "CSTACK", "DATA16_AN"],
            "data_placement": "0x0200..0xFFFF",
            "link_root": LINK_ROOT,
            "dummy_external_count": len(EXTERNAL_DEFINITIONS),
            "dummy_external_base": "0xF0000",
            "dummy_external_stride_bytes": 16,
            "dummy_external_manifest_sha256": _sha256(
                _canonical_bytes(external_manifest)
            ),
            "dummy_externals_have_implementations": False,
            "synthetic_addresses_are_original_physical_addresses": False,
        },
        "objects": objects,
        "cross_object_adjudication": {
            "both_selectors_use_fixed_25_celsius": True,
            "both_search_30_temperature_slots": True,
            "both_match_lower_inclusive_upper_exclusive": True,
            "both_read_2508_bytes_after_a_match": True,
            "both_send_799_bytes_to_0x20": True,
            "both_generate_704_ff_bytes_for_0x21": True,
            "E2801_reads_tsc_but_does_not_use_result_for_selection": True,
            "E2802_does_not_read_tsc_inside_upload": True,
            "legacy_temperature_selection_is_dynamic": False,
            "legacy_2508_byte_slot_proves_current_800_byte_wrapper_abi": False,
        },
        "evidence_boundaries": {
            "linked_addresses_and_dummy_externals_are_analysis_only": True,
            "original_physical_memory_map_proven": False,
            "ReadData_provider_or_transport_proven": False,
            "functions_executed": False,
            "objects_are_legacy_delivered_ubrof10_not_current_spd1657_firmware": True,
            "current_spd1657_800_byte_abi_proven": False,
            "current_dual_controller_loading_contract_proven": False,
            "electrical_or_lut_safety_proven": False,
            "authorizes_live_hardware_action": False,
        },
        "adjudication": {
            "verdict": (
                "LEGACY_E2801_AND_E2802_SELECT_FIXED_25C_SLOT_AND_UPLOAD_"
                "799_PLUS_GENERATED_704_BYTES"
            ),
            "why": (
                "Exact source objects, deterministic linked images, function bytes, "
                "and pinned-tool disassembly all agree. E2801's TSC read does not "
                "feed R9, while E2802 has no TSC read in this function. This is "
                "legacy software evidence only and does not establish the current "
                "SPD1657 transport, 800-byte ABI, dual-controller contract, or safety."
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
    parser.add_argument("--objdump", type=Path, required=True)
    parser.add_argument("--iar-root", type=Path, default=graph.DEFAULT_IAR_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = build_report(args.xlink, args.objdump, args.iar_root)
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
        TemperatureSelectorAuditError,
        UnicodeError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
