#!/usr/bin/env python3
"""Locate common panel code in three identity-pinned Good Display apps.

This audit is offline and read-only.  It proves only the panel paths that can
be tied to typed command/data helpers and reachable image-display callers.
Untyped constants are never promoted to a runtime-waveform ABI.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
from typing import Any, Mapping, Sequence
from zipfile import ZipFile


KIND = "good-display-esp32e6-e01-cross-image-panel-audit"
SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_TOOL = REPO_ROOT / "tools" / "good_display_esp32e6_firmware_audit.py"
DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output"
    / "offline"
    / "good_display_esp32e6_cross_image_panel_audit_20260812.json"
)
DEFAULT_ELF_ROOT = (
    REPO_ROOT
    / ".test-output"
    / "offline"
    / "good_display_esp32e6_e01_firmware_20260604"
    / "elf"
)
DEFAULT_OBJDUMP = (
    Path.home()
    / ".platformio"
    / "packages"
    / "toolchain-xtensa-esp32s3"
    / "bin"
    / "xtensa-esp32s3-elf-objdump.exe"
)
VENDOR_E6_SOURCE = (
    REPO_ROOT
    / "\u53c2\u8003\u8d44\u6599"
    / "E6_73_sample code_V1.2_20250116"
    / "E6_73_sample code_V1.2_20250116"
    / "E6_73.c"
)

EXPECTED_OBJDUMP = {
    "bytes_sha256": (
        "697fdbe10be334df695fd2905b53837a6f9f244145862bef2fee383a2c7d0def"
    ),
    "version_prefix": ("GNU objdump (crosstool-NG esp-2021r2-patch5) 2.35.1.20201223"),
}
EXPECTED_VENDOR_SOURCE = {
    "bytes_sha256": (
        "8f511aca743bcd55d751d6d935261733b5931eb2fa101bb6d9f815cd0a8b06e9"
    ),
}

EXPECTED_INIT_TRACE: tuple[tuple[int, tuple[int, ...]], ...] = (
    (0xAA, (0x49, 0x55, 0x20, 0x08, 0x09, 0x18)),
    (0x01, (0x3F,)),
    (0x00, (0x5F, 0x69)),
    (0x03, (0x00, 0x54, 0x00, 0x44)),
    (0x05, (0x40, 0x1F, 0x1F, 0x2C)),
    (0x06, (0x6F, 0x1F, 0x17, 0x49)),
    (0x08, (0x6F, 0x1F, 0x1F, 0x22)),
    (0x30, (0x08,)),
    (0x50, (0x3F,)),
    (0x60, (0x02, 0x00)),
    (0x61, (0x03, 0x20, 0x01, 0xE0)),
    (0x84, (0x01,)),
    (0xE3, (0x2F,)),
    (0x04, ()),
)
EXPECTED_INIT_NORMALIZED_SHA256 = (
    "a1df5af1b60171e0ebf5e2632aa11a1395da90236061a37a75c8d10605274baa"
)
EXPECTED_COMMAND_NORMALIZED_SHA256 = (
    "7e5e289e7c6cf86726372bf555b9d1e946565a4f63761dd10b05f17ca5704d22"
)
EXPECTED_DATA_NORMALIZED_SHA256 = (
    "77bae5f030cc0c06c4af32c15e2afa336a9d8d977f6c04ad49d66fd6ed6a4526"
)
EXPECTED_PACKED_DISPLAY_NORMALIZED_SHA256 = (
    "e89347d0f8630501725d60cc8d603f7c88ad84d13d57c318e566cdb091562c9c"
)
EXPECTED_SPI_WRAPPER_NORMALIZED_SHA256 = (
    "fb744f223d3ba3d88aa588373b997f268d3ad57deb7cf5d24af0a43325409351"
)

IMAGE_SPECS: Mapping[str, Mapping[str, Any]] = {
    "GDEP073E01wifi.bin": {
        "elf": "GDEP073E01wifi.synthetic.elf",
        "elf_sha256": (
            "754192223d62a4ae67bb4f1135d50e5d908d88d1825dbcff0917c581a41f6915"
        ),
        "functions": {
            "init": (
                0x42002D7C,
                0x42002E84,
                "e2a8f61d7200f448a324fab197b4a262b094c450519576ee7de1119c975bf585",
            ),
            "unpacked_packer": (
                0x42002E9C,
                0x42002EF4,
                "549741a4c55a45e3d69f48c4f66de4465f9c4910806c57762309df85e2be51d1",
            ),
            "packed_display": (
                0x42002EF4,
                0x42002F54,
                "5f2cd745bc68b7e00270c2c9a2bb547b675b9e9c8d4b3db7fc0e3fccf8493143",
            ),
            "tx_wrapper": (
                0x42002F54,
                0x42002F64,
                "f8b647f6b03c138f7ab0a9dc9d21131db172fe89425b8761b69f4df8febb7599",
            ),
            "command": (
                0x42002F64,
                0x42002F88,
                "341bf806e87c0d73518bddbf16d2a087a6494c747adc1d5d862b4d50955d8f18",
            ),
            "data": (
                0x42002F88,
                0x42002FAC,
                "b0dc8b292c06cfbf97a8b0f8f13a1df08b6e4b0ea172cc7fb07acfb9320311e3",
            ),
            "color_converter": (
                0x42098938,
                0x42098972,
                "09d598f03150aa170f6afc70aa2d7c5cf56dbf86f00a622402dda5afd3017b2f",
            ),
        },
        "caller_chain": {
            "init_calls": ["0x42003f14", "0x420040b9", "0x4200411a"],
            "unpacked_packer_call": "0x42003f1d",
            "packed_display_calls": ["0x420040c1", "0x42004124"],
        },
        "backend": "arduino_spiclass_transfer_shape",
        "spi_transfer_shape": (0x42004B34, 0x42004B52),
    },
    "SD.bin": {
        "elf": "SD.synthetic.elf",
        "elf_sha256": (
            "afac8cc65c11fd442abf5391f7a2929916cf962caac6acfed3dc49a3211754a7"
        ),
        "functions": {
            "init": (
                0x4200214C,
                0x42002254,
                "d70f283cd7da7c1891528db9cb5867314da0aa0e19f3e517d0d77c897057ceda",
            ),
            "packed_display": (
                0x4200226C,
                0x420022CC,
                "9d410c6c2142c1954784d185ace02df541b56dbf8f1d9e1d9afb1ed2d7da011b",
            ),
            "tx_wrapper": (
                0x420022CC,
                0x42002308,
                "51f7b47662062ffa48e05a5d603f73af0f57daa38d3662d4219ccd5e2df8e707",
            ),
            "command": (
                0x42002308,
                0x4200232C,
                "9ee17220bf8234fcf5f16630c7a4317b0a230f11d38c4ed4fa212703a292b0e0",
            ),
            "data": (
                0x4200232C,
                0x42002350,
                "7dac1299c3cbebd25c07bb5f133cd0c1487ef6fd74ae88f7daf99954bcaafe66",
            ),
        },
        "caller_chain": {
            "bmp_processor_entry": "0x42002720",
            "bmp_success_string_xref": "0x42002b3d",
            "bmp_processor_call": "0x42002ca7",
            "success_test": "0x42002caa",
            "init_call": "0x42002caf",
            "packed_display_call": "0x42002cb7",
        },
        "backend": "gpio_bitbang_msb_first",
    },
    "usb.bin": {
        "elf": "usb.synthetic.elf",
        "elf_sha256": (
            "469f7656242e140dbd68157f4d006086053031462b594c65d218945a58657c48"
        ),
        "functions": {
            "init": (
                0x42001D54,
                0x42001E5C,
                "31312ed7f898b47ddd3f98624daee7b8afd3264e4d08202b9f6bab93a2619dc2",
            ),
            "unpacked_packer": (
                0x42001E74,
                0x42001ECC,
                "05b5a9ce2f0f829813a895eb4f65c6cac7c63cbed60cf46151fe9a904c7cf9d0",
            ),
            "tx_wrapper": (
                0x42001ECC,
                0x42001EDC,
                "302cec33af9b942ef7789dfdbced4ef44c2900cae9804e038737deb300d7e445",
            ),
            "command": (
                0x42001EDC,
                0x42001F00,
                "687ae837fe9018c94a0662105d634952f7a683b714260dd67e43415c1a6c8bac",
            ),
            "data": (
                0x42001F00,
                0x42001F24,
                "f8a36c25494bd3238b318c7fcb0f9be0c97c7a67a0c7b478663af8772bde9880",
            ),
            "color_converter": (
                0x42026D74,
                0x42026DAC,
                "f2018ecadea37acbd6122c2b519c91e91b29202369377b09ccef1fd445307375",
            ),
        },
        "caller_chain": {
            "init_call": "0x4200207b",
            "unpacked_packer_call": "0x42002080",
        },
        "backend": "arduino_spiclass_transfer_shape",
        "spi_transfer_shape": (0x420021C8, 0x420021E6),
    },
}

COLOR_TAG_MAP = {
    0: 0,
    29: 5,
    76: 3,
    150: 6,
    226: 2,
    255: 1,
}


class CrossImageAuditError(ValueError):
    """Raised when an identity or a pinned instruction invariant changes."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise CrossImageAuditError(message)


def _hex(value: int) -> str:
    return f"0x{value:x}"


def _load_base_tool() -> Any:
    spec = importlib.util.spec_from_file_location("good_display_base_audit", BASE_TOOL)
    _expect(spec is not None and spec.loader is not None, "cannot load base audit")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _elf_sections(data: bytes) -> list[dict[str, Any]]:
    _expect(data[:4] == b"\x7fELF", "synthetic view is not ELF")
    _expect(data[4:6] == b"\x01\x01", "synthetic view is not ELF32 little-endian")
    shoff = struct.unpack_from("<I", data, 32)[0]
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", data, 46)
    _expect(shentsize == 40 and shnum > 0, "unexpected ELF section table")
    _expect(shstrndx < shnum, "invalid ELF section-name index")

    headers = []
    for index in range(shnum):
        offset = shoff + index * shentsize
        _expect(offset + 40 <= len(data), "truncated ELF section header")
        name, section_type, flags, address, file_offset, size = struct.unpack_from(
            "<IIIIII", data, offset
        )
        headers.append(
            {
                "index": index,
                "name_offset": name,
                "type": section_type,
                "flags": flags,
                "address": address,
                "file_offset": file_offset,
                "bytes": size,
            }
        )
    names_header = headers[shstrndx]
    names = data[
        names_header["file_offset"] : names_header["file_offset"]
        + names_header["bytes"]
    ]
    result = []
    for header in headers:
        start = header["name_offset"]
        _expect(start < len(names), "invalid ELF section name")
        end = names.find(b"\0", start)
        _expect(end >= 0, "unterminated ELF section name")
        payload_start = header["file_offset"]
        payload_end = payload_start + header["bytes"]
        _expect(payload_end <= len(data), "truncated ELF section payload")
        result.append(
            {
                **header,
                "name": names[start:end].decode("ascii"),
                "data": data[payload_start:payload_end],
            }
        )
    return result


def _verify_synthetic_view(
    path: Path, expected_sha256: str, segments: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    data = path.read_bytes()
    _expect(_sha256(data) == expected_sha256, f"synthetic ELF identity changed: {path}")
    by_name = {item["name"]: item for item in _elf_sections(data)}
    verified = []
    for segment in segments:
        section = by_name.get(f".seg{segment['index']}")
        _expect(section is not None, "synthetic ELF segment section missing")
        payload = segment["data"]
        _expect(section["address"] == segment["load_address_int"], "ELF VMA drift")
        _expect(section["data"] == payload, "ELF segment payload drift")
        verified.append(
            {
                "section": section["name"],
                "virtual_address": _hex(section["address"]),
                "bytes": len(payload),
                "sha256": _sha256(payload),
            }
        )
    return {
        "path": str(path),
        "bytes": len(data),
        "sha256": expected_sha256,
        "derived_view_matches_pinned_app_segments": True,
        "segments": verified,
    }


def _bytes_at(segments: Sequence[Mapping[str, Any]], start: int, end: int) -> bytes:
    _expect(start < end, "invalid function interval")
    for segment in segments:
        base = segment["load_address_int"]
        data = segment["data"]
        if base <= start and end <= base + len(data):
            return data[start - base : end - base]
    raise CrossImageAuditError(f"unmapped interval {_hex(start)}..{_hex(end)}")


_DISASSEMBLY_RE = re.compile(
    r"^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+([^\s]+)(?:\s+(.*?))?(?:\s+<.*)?$"
)


def _disassemble(
    objdump: Path, elf: Path, start: int, end: int
) -> list[dict[str, Any]]:
    result = subprocess.run(
        [
            str(objdump),
            "-d",
            f"--start-address={start}",
            f"--stop-address={end}",
            str(elf),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="ascii",
        errors="strict",
        check=False,
    )
    _expect(result.returncode == 0, f"objdump failed: {result.stderr.strip()}")
    records = []
    for line in result.stdout.splitlines():
        match = _DISASSEMBLY_RE.match(line)
        if match is None:
            continue
        operands = re.sub(r"\s+<.*$", "", (match.group(4) or "").strip())
        records.append(
            {
                "address": int(match.group(1), 16),
                "raw": match.group(2),
                "mnemonic": match.group(3),
                "operands": operands,
            }
        )
    _expect(records and records[0]["address"] == start, "function decode start drift")
    return records


def _normalized_lines(
    records: Sequence[Mapping[str, Any]],
    *,
    start: int,
    targets: Mapping[int, str] | None = None,
    normalize_literals: bool = False,
) -> list[str]:
    target_names = targets or {}
    result = []
    for record in records:
        mnemonic = str(record["mnemonic"])
        operands = str(record["operands"])
        if mnemonic.startswith("call") and mnemonic != "callx8":
            target = int(operands.removeprefix("0x"), 16)
            operands = f"<{target_names.get(target, 'CALL')}>"
        elif normalize_literals and mnemonic == "l32r":
            operands = re.sub(r",\s*(?:0x)?[0-9a-f]+$", ", <LITERAL>", operands)
        elif mnemonic in {"bne", "j"}:
            match = re.search(r"([0-9a-f]{8})$", operands)
            if match is not None:
                relative = int(match.group(1), 16) - start
                operands = operands[: match.start(1)] + f"<SELF{relative:+#x}>"
        result.append(f"{mnemonic} {operands}".rstrip())
    return result


def _digest_lines(lines: Sequence[str]) -> tuple[int, int, str]:
    payload = "\n".join(lines).encode("ascii")
    return len(lines), len(payload), _sha256(payload)


def _immediate_a10(record: Mapping[str, Any]) -> int | None:
    if record["mnemonic"] not in {"movi", "movi.n"}:
        return None
    match = re.fullmatch(r"a10,\s*(0x[0-9a-f]+|-?\d+)", str(record["operands"]))
    return None if match is None else int(match.group(1), 0)


def _typed_trace(
    records: Sequence[Mapping[str, Any]], command: int, data: int
) -> tuple[tuple[int, tuple[int, ...]], ...]:
    result: list[list[Any]] = []
    for index, record in enumerate(records[:-1]):
        value = _immediate_a10(record)
        following = records[index + 1]
        if value is None or following["mnemonic"] != "call8":
            continue
        target = int(str(following["operands"]).removeprefix("0x"), 16)
        if target == command:
            result.append([value, []])
        elif target == data:
            _expect(bool(result), "data helper precedes command helper")
            result[-1][1].append(value)
    return tuple((int(command_byte), tuple(values)) for command_byte, values in result)


def _function_report(
    name: str,
    spec: Sequence[Any],
    segments: Sequence[Mapping[str, Any]],
    objdump: Path,
    elf: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    start, end, expected_sha = int(spec[0]), int(spec[1]), str(spec[2])
    payload = _bytes_at(segments, start, end)
    actual_sha = _sha256(payload)
    _expect(actual_sha == expected_sha, f"{name} raw function identity changed")
    records = _disassemble(objdump, elf, start, end)
    return (
        {
            "virtual_address": _hex(start),
            "end_virtual_address_exclusive": _hex(end),
            "bytes": len(payload),
            "sha256": actual_sha,
            "instruction_count": len(records),
        },
        records,
    )


def _instruction_summary(records: Sequence[Mapping[str, Any]]) -> list[str]:
    return [
        f"{_hex(int(item['address']))}: {item['mnemonic']} {item['operands']}".rstrip()
        for item in records
    ]


def _analyze_image(
    name: str,
    spec: Mapping[str, Any],
    segments: Sequence[Mapping[str, Any]],
    objdump: Path,
    elf_root: Path,
) -> dict[str, Any]:
    elf = elf_root / str(spec["elf"])
    synthetic = _verify_synthetic_view(elf, str(spec["elf_sha256"]), segments)
    functions: dict[str, Any] = {}
    decoded: dict[str, list[dict[str, Any]]] = {}
    for function_name, function_spec in spec["functions"].items():
        functions[function_name], decoded[function_name] = _function_report(
            f"{name}:{function_name}", function_spec, segments, objdump, elf
        )

    command_address = int(spec["functions"]["command"][0])
    data_address = int(spec["functions"]["data"][0])
    init_address = int(spec["functions"]["init"][0])
    init_lines = _normalized_lines(decoded["init"], start=init_address)
    init_count, init_bytes, init_sha = _digest_lines(init_lines)
    _expect(init_sha == EXPECTED_INIT_NORMALIZED_SHA256, "init normalization drift")
    trace = _typed_trace(decoded["init"], command_address, data_address)
    _expect(trace == EXPECTED_INIT_TRACE, "typed init trace drift")

    helper_findings = {}
    for helper, expected_sha in (
        ("command", EXPECTED_COMMAND_NORMALIZED_SHA256),
        ("data", EXPECTED_DATA_NORMALIZED_SHA256),
    ):
        address = int(spec["functions"][helper][0])
        lines = _normalized_lines(decoded[helper], start=address)
        count, normalized_bytes, digest = _digest_lines(lines)
        _expect(digest == expected_sha, f"{helper} helper normalization drift")
        helper_findings[helper] = {
            "normalized_instruction_count": count,
            "normalized_disassembly_bytes": normalized_bytes,
            "normalized_disassembly_sha256": digest,
            "trace": (
                ["select_low:gpio2", "dc_low:gpio3", "transmit", "select_high:gpio2"]
                if helper == "command"
                else [
                    "select_low:gpio2",
                    "dc_high:gpio3",
                    "transmit",
                    "select_high:gpio2",
                ]
            ),
        }

    backend: dict[str, Any]
    if spec["backend"] == "gpio_bitbang_msb_first":
        backend = {
            "classification": "panel_gpio_bitbang_msb_first",
            "clock_gpio": 12,
            "data_gpio": 11,
            "bits_per_byte": 8,
            "instruction_evidence": _instruction_summary(decoded["tx_wrapper"]),
            "is_sd_card_spi": False,
        }
    else:
        tx_address = int(spec["functions"]["tx_wrapper"][0])
        tx_lines = _normalized_lines(
            decoded["tx_wrapper"],
            start=tx_address,
            normalize_literals=True,
        )
        _, _, tx_sha = _digest_lines(tx_lines)
        _expect(tx_sha == EXPECTED_SPI_WRAPPER_NORMALIZED_SHA256, "SPI wrapper drift")
        shape_start, shape_end = spec["spi_transfer_shape"]
        shape_records = _disassemble(objdump, elf, shape_start, shape_end)
        shape_text = "\n".join(_instruction_summary(shape_records))
        for required in ("l8ui a8, a2, 24", "extui a11, a3, 0, 8", "beqz"):
            _expect(required in shape_text, "SPIClass transfer-shape anchor missing")
        backend = {
            "classification": "arduino_spiclass_transfer_uint8_shape_match",
            "classification_is_source_shape_not_retained_symbol": True,
            "normalized_wrapper_sha256": tx_sha,
            "transfer_shape_virtual_address": _hex(shape_start),
            "transfer_shape_end_exclusive": _hex(shape_end),
            "transfer_shape_instruction_evidence": _instruction_summary(shape_records),
            "is_sd_card_spi": False,
        }

    image_report: dict[str, Any] = {
        "synthetic_disassembly_view": synthetic,
        "functions": functions,
        "normalized_common_code": {
            "init": {
                "instruction_count": init_count,
                "normalized_disassembly_bytes": init_bytes,
                "normalized_disassembly_sha256": init_sha,
            },
            "command_data_helpers": helper_findings,
        },
        "typed_init_trace": [
            {"command": f"0x{command:02x}", "data_hex": bytes(data).hex()}
            for command, data in trace
        ],
        "typed_init_command_count": len(trace),
        "typed_command_or_data_byte_count": sum(1 + len(data) for _, data in trace),
        "panel_transport_backend": backend,
        "caller_chain": spec["caller_chain"],
    }

    if "packed_display" in decoded:
        start = int(spec["functions"]["packed_display"][0])
        targets = {command_address: "CMD", data_address: "DATA"}
        busy_call = 0x42002D6C if name.startswith("GDEP") else 0x4200213C
        targets[busy_call] = "BUSY"
        lines = _normalized_lines(
            decoded["packed_display"], start=start, targets=targets
        )
        count, normalized_bytes, digest = _digest_lines(lines)
        _expect(
            digest == EXPECTED_PACKED_DISPLAY_NORMALIZED_SHA256,
            "packed-display normalization drift",
        )
        image_report["packed_display"] = {
            "normalized_instruction_count": count,
            "normalized_disassembly_bytes": normalized_bytes,
            "normalized_disassembly_sha256": digest,
            "input_bytes": 192_000,
            "panel_data_bytes": 192_000,
            "pixel_layout": "two_4bit_pixel_codes_per_byte",
            "typed_commands": ["0x10", "0x04", "0x06", "0x12", "0x02"],
        }

    if "unpacked_packer" in decoded:
        packer_text = "\n".join(_instruction_summary(decoded["unpacked_packer"]))
        for required in ("movi", "l8ui", "slli", "or", "extui"):
            _expect(
                required in packer_text, "unpacked packer instruction anchor missing"
            )
        image_report["unpacked_pixel_packer"] = {
            "input_tag_bytes": 384_000,
            "panel_data_bytes": 192_000,
            "first_pixel_position": "high_nibble",
            "second_pixel_position": "low_nibble",
            "mapping": {str(key): value for key, value in COLOR_TAG_MAP.items()},
            "tag_value_origin_inference": (
                "0/29/76/150/226/255 coincide with integer grayscale tags for "
                "black/blue/red/green/yellow/white; this is an inference, not a "
                "controller color-mixing mode"
            ),
            "typed_commands": ["0x10", "0x12"],
            "semantic_trace_sha256": _sha256(
                json.dumps(
                    [
                        "command:0x10",
                        "input_tag_bytes:384000",
                        "map:first->high_nibble",
                        "map:second->low_nibble",
                        "panel_data_bytes:192000",
                        "command:0x12",
                        "data:0x00",
                        "busy",
                    ],
                    separators=(",", ":"),
                ).encode("ascii")
            ),
        }
    return image_report


def _vendor_source_cross_reference() -> dict[str, Any]:
    data = VENDOR_E6_SOURCE.read_bytes()
    digest = _sha256(data)
    _expect(
        digest == EXPECTED_VENDOR_SOURCE["bytes_sha256"],
        "vendor E6 source identity changed",
    )
    text = data.decode("ascii")
    required = (
        "SPI_COMMAND(0xAA);",
        "SPI_DATA(0x49);",
        "SPI_DATA(0x55);",
        "SPI_COMMAND(TRES);",
        "SPI_DATA(0x03);",
        "SPI_DATA(0x20);",
        "SPI_DATA(0x01);",
        "SPI_DATA(0xE0);",
        "for(i=0;i<192000;i++)",
    )
    _expect(
        all(value in text for value in required), "vendor E6 source anchors changed"
    )
    return {
        "path": str(VENDOR_E6_SOURCE),
        "sha256": digest,
        "common_family_evidence": {
            "unlock": "AA:495520080918",
            "resolution": "61:032001e0",
            "packed_frame_bytes": 192_000,
        },
        "bounded_differences": {
            "source_epd_init_btst2": "06:6f1f1717",
            "three_apps_init_btst2": "06:6f1f1749",
            "source_later_display_btst2": "06:6f1f1749",
            "three_apps_init_ends_with_power_on_0x04": True,
            "therefore_exact_source_function_identity_claimed": False,
        },
    }


def build_report(
    *, objdump: Path = DEFAULT_OBJDUMP, elf_root: Path = DEFAULT_ELF_ROOT
) -> dict[str, Any]:
    base = _load_base_tool()
    base_report = base.build_report()

    objdump_data = objdump.read_bytes()
    _expect(
        _sha256(objdump_data) == EXPECTED_OBJDUMP["bytes_sha256"],
        "objdump identity changed",
    )
    version = subprocess.run(
        [str(objdump), "--version"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="ascii",
        check=False,
    )
    _expect(version.returncode == 0, "objdump version query failed")
    version_line = version.stdout.splitlines()[0]
    _expect(
        version_line == EXPECTED_OBJDUMP["version_prefix"],
        "objdump version changed",
    )

    with ZipFile(base.DEFAULT_VENDOR_ZIP) as archive:
        entries = {
            Path(item.filename.replace("\\", "/")).name: item
            for item in archive.infolist()
            if not item.is_dir()
        }
        images = {}
        for name, spec in IMAGE_SPECS.items():
            _, segments = base._parse_app_image(
                archive.read(entries[name]), base.EXPECTED_IMAGES[name]
            )
            images[name] = _analyze_image(name, spec, segments, objdump, elf_root)

    init_hashes = {
        image["normalized_common_code"]["init"]["normalized_disassembly_sha256"]
        for image in images.values()
    }
    command_hashes = {
        image["normalized_common_code"]["command_data_helpers"]["command"][
            "normalized_disassembly_sha256"
        ]
        for image in images.values()
    }
    data_hashes = {
        image["normalized_common_code"]["command_data_helpers"]["data"][
            "normalized_disassembly_sha256"
        ]
        for image in images.values()
    }
    _expect(
        len(init_hashes) == len(command_hashes) == len(data_hashes) == 1,
        "common hash drift",
    )

    sd_instruction = base_report["images"]["SD.bin"]["instruction_level"]
    sd_spi = sd_instruction["bounded_interpretation"]
    _expect(
        sd_spi["custom_sd_spi_setup_path_supported"] is True,
        "SD SPI base evidence drift",
    )
    _expect(
        sd_spi["argument_order"]
        == ["SCK=GPIO21", "MISO=GPIO13", "MOSI=GPIO47", "SS=GPIO48"],
        "SD SPI pin evidence drift",
    )

    typed_init_commands = {command for command, _ in EXPECTED_INIT_TRACE}
    recovered_display_commands = {0x10, 0x04, 0x06, 0x12, 0x02}
    typed_commands = sorted(typed_init_commands | recovered_display_commands)
    _expect(0x20 not in typed_commands and 0x21 not in typed_commands, "ABI overclaim")
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "base_official_bundle": {
            "zip_sha256": base_report["vendor_zip"]["sha256"],
            "all_image_identities_verified": True,
        },
        "disassembler": {
            "path": str(objdump),
            "sha256": EXPECTED_OBJDUMP["bytes_sha256"],
            "version": version_line,
        },
        "images": images,
        "cross_image_findings": {
            "common_init_normalized_sha256": next(iter(init_hashes)),
            "common_init_present_in_all_three_apps": True,
            "common_command_helper_normalized_sha256": next(iter(command_hashes)),
            "common_data_helper_normalized_sha256": next(iter(data_hashes)),
            "typed_panel_command_data_path_recovered": True,
            "panel_image_packing_recovered": True,
            "panel_geometry": {"width": 800, "height": 480},
            "packed_frame_bytes": 192_000,
            "unpacked_tag_frame_bytes": 384_000,
            "unpacked_tag_to_panel_code": {
                str(key): value for key, value in COLOR_TAG_MAP.items()
            },
            "sd_card_spi": {
                "function": "0x420024dc",
                "pins": {
                    "sck": 21,
                    "miso": 13,
                    "mosi": 47,
                    "ss": 48,
                },
                "string_xref_supported": True,
            },
            "sd_panel_transport": {
                "backend": "gpio_bitbang_msb_first",
                "clock_gpio": 12,
                "data_gpio": 11,
            },
            "sd_card_spi_and_panel_transport_are_distinct": True,
            "wifi_usb_panel_transport": (
                "stripped Arduino SPIClass::transfer(uint8_t) source-shape path"
            ),
            "generic_esp_idf_spi_presence_alone_used_as_panel_evidence": False,
        },
        "vendor_e6_source_cross_reference": _vendor_source_cross_reference(),
        "runtime_waveform_boundary": {
            "typed_commands_in_recovered_init_and_display_paths": [
                f"0x{value:02x}" for value in typed_commands
            ],
            "typed_command_0x20_recovered": False,
            "typed_command_0x21_recovered": False,
            "runtime_lut_length_704_recovered": False,
            "runtime_lut_length_2508_recovered": False,
            "runtime_waveform_abi_recovered": False,
            "dual_controller_delivery_recovered": False,
            "bounded_scope": (
                "negative only for the recovered typed init/display caller graph; "
                "raw constants elsewhere remain untyped unknowns"
            ),
        },
        "bounded_conclusion": (
            "The three apps share one normalized E6 OTP-init routine and typed "
            "command/data framing. WiFi and USB map six grayscale tag bytes to "
            "4-bit panel codes and pack two pixels per byte; SD consumes the same "
            "192000-byte packed layout. The SD-card SPI path is separate from the "
            "SD panel bitbang path. None of this recovers a 0x20/0x21 runtime-LUT "
            "ABI, 704/2508-byte payload, or dual-controller contract."
        ),
        "live_payload_generated": False,
        "live_test_authorized": False,
        "safety": {
            "offline_static_analysis_only": True,
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "device_network_accessed": False,
            "flash_written": False,
            "display_refreshed": False,
            "authorization_or_token_generated": False,
        },
    }


def canonical_sha256(report: Mapping[str, Any]) -> str:
    data = json.dumps(
        report, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("ascii")
    return _sha256(data)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit common panel code in three frozen ESP32E6 apps offline."
    )
    parser.add_argument("--objdump", type=Path, default=DEFAULT_OBJDUMP)
    parser.add_argument("--elf-root", type=Path, default=DEFAULT_ELF_ROOT)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_report(objdump=args.objdump, elf_root=args.elf_root)
    except (CrossImageAuditError, OSError) as error:
        json.dump(
            {"kind": KIND, "schema_version": SCHEMA_VERSION, "error": str(error)},
            sys.stdout,
            ensure_ascii=True,
            indent=2,
        )
        sys.stdout.write("\n")
        return 2
    rendered = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
