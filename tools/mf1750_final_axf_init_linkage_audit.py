#!/usr/bin/env python3
"""Audit the delivered STM32 final images and WF23 build linkage offline.

The audit is identity-pinned and read-only.  It parses the seven delivered
Arm/ELF AXF files, reconstructs the linked ``epdInitial`` call traces without
third-party disassemblers, and checks the paired MAP files and Keil metadata.
It never emits waveform plaintext/key material and performs no hardware,
serial, network, flashing, or refresh action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
from typing import Any
from zipfile import ZipFile


KIND = "mf1750-final-axf-init-linkage-audit"
SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE_ROOT = REPO_ROOT / "参考资料" / "REG-API-oqc(1)(1)" / "REG-API-oqc"
DEFAULT_VENDOR_ARCHIVE = REPO_ROOT / "参考资料" / "REG-API-oqc(1)(1).zip"

OUTPUT_REL = Path("Output")
WF23_REL = Path("Projects/MDK-ARM/12")
PROJECT_REL = Path("Projects/MDK-ARM/atk_f103.uvprojx")
EDITOR_STATE_REL = Path("Projects/MDK-ARM/atk_f103.uvguix.Administrator")
WF23_ARCHIVE_ENTRY = "REG-API-oqc/Projects/MDK-ARM/12"

EXPECTED_VENDOR_ARCHIVE_SHA256 = (
    "c8174a2c9082a826c7e77029da8d6bc54eee498421580badb2753eb911aa9ead"
)
EXPECTED_WF23_SOURCE_SHA256 = (
    "c75d23a0f290deb8416619028284c53726bd399921a2dc0ffe043bef7f227c5d"
)
EXPECTED_WF23_WRAPPER_SHA256 = (
    "d01caa5581b69ab82d7bb34175d21220e4c08582eb55ce5f9f6391700cd6ebb4"
)
EXPECTED_PROJECT_SHA256 = (
    "2a4c9093b153e74a56d5821c6eadd1e46cb0d3d809abb7b23acb484af2f7a9a8"
)
EXPECTED_EDITOR_STATE_SHA256 = (
    "313c944967fbec713ea4fc318d264e43533cc0b23bcb3e53b873cd12fe1fd800"
)

# The normalized trace is encoded as compact JSON arrays:
# ["reset"], ["busy"], or ["write", target, command, data-array].
EXPECTED_DUAL_TRACE = (
    ("reset",),
    ("write", "both", 0xAA, (0x49, 0x55, 0x20, 0x08, 0x09, 0x18)),
    ("write", "both", 0x00, (0x5F, 0x69)),
    ("busy",),
    ("write", "both", 0xE0, (0x01,)),
    ("busy",),
    ("write", "both", 0x01, (0x3F,)),
    ("write", "both", 0x03, (0x00, 0x54, 0x00, 0x44)),
    ("write", "both", 0x05, (0x40, 0x1F, 0x1F, 0x2C)),
    ("write", "both", 0x06, (0x6F, 0x1F, 0x16, 0x25)),
    ("write", "both", 0x08, (0x6F, 0x1F, 0x1F, 0x22)),
    ("write", "both", 0x13, (0x00, 0x04)),
    ("write", "both", 0x30, (0x08,)),
    ("write", "both", 0x41, (0x00,)),
    ("write", "both", 0x50, (0x3F,)),
    ("write", "both", 0x60, (0x02, 0x00)),
    ("write", "both", 0x61, (0x02, 0x00, 0x02, 0x58)),
    ("busy",),
    ("write", "both", 0x84, (0x01,)),
    ("write", "both", 0x86, (0x00,)),
    ("write", "both", 0xE3, (0x2F,)),
    ("write", "both", 0xE5, (0x00,)),
)
EXPECTED_DUAL_TRACE_SHA256 = (
    "9eb1db5d22278d66a5483c38833b20f7ef0cffa3065b16c01d31841346b7fd31"
)

EXPECTED_IMAGES: tuple[dict[str, Any], ...] = (
    {
        "name": "jiaxian-M009F-T_OQC_GX-手动",
        "axf_bytes": 1_040_892,
        "axf_sha256": "c85755ede50cc689cb86ed08dd6b874558a91a6a567ea4faa28aa61c81a77000",
        "map_bytes": 269_797,
        "map_sha256": "808721a8eac6bd2e781fd0e1256a248bd1f43314dc4703ce0940b0053dcae020",
        "epd_va": 0x080029D4,
        "epd_file_offset": 0x2A08,
        "epd_bytes": 374,
        "epd_sha256": "04f91bbb7eee690c8f87bdba28097d4525abd9065766440250ded34d70c5af12",
        "call_count": 63,
        "trace_sha256": EXPECTED_DUAL_TRACE_SHA256,
        "dual": True,
    },
    {
        "name": "jiaxian-M009F-T_OQC_GX",
        "axf_bytes": 716_188,
        "axf_sha256": "7b239c5ba4b9ac17a3d7bf3e55984ec9c51c2a908652018ffeb237315b060ff6",
        "map_bytes": 265_216,
        "map_sha256": "186369ef93f837c2b177b9abe1e383b3891be11489ebe328dbc6af751eeb0feb",
        "epd_va": 0x08002480,
        "epd_file_offset": 0x24B4,
        "epd_bytes": 374,
        "epd_sha256": "ee4176022b8cfb407f26d7991c661e2f27d79facb8892cc8fdbcb59457779ca8",
        "call_count": 63,
        "trace_sha256": EXPECTED_DUAL_TRACE_SHA256,
        "dual": True,
    },
    {
        "name": "jiaxian-M009F-T_OQC_GX自动",
        "axf_bytes": 1_039_580,
        "axf_sha256": "437cec91669bde669600af35bde2c9e270073b5860e24c49a649d9d0e1859a2e",
        "map_bytes": 271_793,
        "map_sha256": "9ed9da831c093a3830256cccdf2037ba514fc1539cfaad2dd498d7aab4482c79",
        "epd_va": 0x08002990,
        "epd_file_offset": 0x29C4,
        "epd_bytes": 374,
        "epd_sha256": "8ec4b4b7df90d4fb3e0f890e18aeb664d90c774f3fbe94dda90aad23ef61603c",
        "call_count": 63,
        "trace_sha256": EXPECTED_DUAL_TRACE_SHA256,
        "dual": True,
    },
    {
        "name": "jiaxian-M009F-T_OQC_YX",
        "axf_bytes": 1_036_752,
        "axf_sha256": "b346a46c67281f51dfc674010acba5621f83e1d9632da9d3b0abd34941154e44",
        "map_bytes": 270_513,
        "map_sha256": "f7b10f233ce26930293105ba7949b2963217f0c189e76d18b70be31207ce48dd",
        "epd_va": 0x08002888,
        "epd_file_offset": 0x28BC,
        "epd_bytes": 374,
        "epd_sha256": "7c6261eaf012a4ee35f1dc34543304ccf91f9ad28ab11fca2d923720a1a6edee",
        "call_count": 63,
        "trace_sha256": EXPECTED_DUAL_TRACE_SHA256,
        "dual": True,
    },
    {
        "name": "jiaxian-M032F_OQC_CJ",
        "axf_bytes": 1_309_652,
        "axf_sha256": "858f771957ce3311e15def0a5be540eebcb6b5ccaf01efef505483aaa7ba9428",
        "map_bytes": 258_973,
        "map_sha256": "1512216a78ab60a536e8bfa7acc810cc4734ee5b06a243298cb3517243c0d79e",
        "epd_va": 0x0800281C,
        "epd_file_offset": 0x2850,
        "epd_bytes": 366,
        "epd_sha256": "ffbc2ebeed5c26df77d9df79613c3ea3c73d8ad91e825dbec2a4b0880fe6fc03",
        "call_count": 61,
        "trace_sha256": "f80495d3798b2f37897733f5a0b392bc61befbbecc3b28b8e3c0fba90674a5c5",
        "dual": False,
    },
    {
        "name": "jiaxian-M032F_OQC_GX",
        "axf_bytes": 1_040_932,
        "axf_sha256": "e6fedd11d5347356d17d0c18746a523f95601336766ce34a13a4ed2b5037dd9a",
        "map_bytes": 269_797,
        "map_sha256": "13afc18dc3ef42a046b0732b29f0a700695e7c21ac6879abb98074d587efc8d8",
        "epd_va": 0x080029D4,
        "epd_file_offset": 0x2A08,
        "epd_bytes": 374,
        "epd_sha256": "f37979a9b174250447bc7eb94a7341466a560222d3fd99d7636e10e2a51e00f1",
        "call_count": 63,
        "trace_sha256": EXPECTED_DUAL_TRACE_SHA256,
        "dual": True,
    },
    {
        "name": "WF-79667-168X384",
        "axf_bytes": 1_307_664,
        "axf_sha256": "e2191a11288dbe39eb9044fee3c42256ab0807a525dfdca88d869709237547ef",
        "map_bytes": 257_903,
        "map_sha256": "1780f036ef953d8f5de0a985e56089e91781cebfeecdf4312dd9a09174f60d3a",
        "epd_va": 0x08002770,
        "epd_file_offset": 0x27A4,
        "epd_bytes": 384,
        "epd_sha256": "3a06a367d09427918f926e90c2eec9abf24e73a46ac1f403e5908021edfd3144",
        "call_count": 64,
        "trace_sha256": "68b00b19b2fefeb060d18475556a2677ce4079f7deb1c371cb7b2edbf031d206",
        "dual": False,
    },
)

EXPECTED_DUAL_SET = tuple(item["name"] for item in EXPECTED_IMAGES if item["dual"])
FORBIDDEN_LOADER_MARKERS = (
    b"loadWF",
    b"WF23_25",
    b"E5_3Bit_Mode 1",
    b"WF_DeCode_SIZE 800",
    b"WF_SIZE 799",
)
FORBIDDEN_LOADER_SYMBOLS = {"loadWF", "WF23_25", "LUT1_DATA"}
NOOTP_REMOVAL = b"Removing main.o(i.EPD_initial_noOTP), (288 bytes)."


class AuditError(RuntimeError):
    """Raised when an identity or structural invariant changes."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_pinned(path: Path, expected_bytes: int, expected_sha256: str) -> bytes:
    _require(path.is_file(), f"missing evidence file: {path}")
    data = path.read_bytes()
    _require(len(data) == expected_bytes, f"unexpected size for {path}")
    _require(_sha256(data) == expected_sha256, f"identity mismatch for {path}")
    return data


def _c_string(data: bytes, offset: int) -> str:
    _require(0 <= offset < len(data), "ELF string offset out of range")
    end = data.find(b"\0", offset)
    _require(end >= 0, "unterminated ELF string")
    return data[offset:end].decode("utf-8", errors="replace")


def _parse_elf32_symbols(
    blob: bytes,
) -> tuple[list[tuple[int, ...]], list[dict[str, int | str]]]:
    _require(blob[:4] == b"\x7fELF", "AXF is not ELF")
    _require(blob[4:6] == b"\x01\x01", "AXF is not 32-bit little-endian ELF")
    header = struct.unpack_from("<HHIIIIIHHHHHH", blob, 16)
    _require(header[1] == 40, "AXF machine is not ARM")
    section_offset = header[5]
    section_entry_bytes = header[10]
    section_count = header[11]
    _require(section_entry_bytes >= 40 and section_count > 0, "invalid ELF sections")
    sections = [
        struct.unpack_from(
            "<IIIIIIIIII", blob, section_offset + index * section_entry_bytes
        )
        for index in range(section_count)
    ]

    symbols: list[dict[str, int | str]] = []
    for section in sections:
        if section[1] != 2:  # SHT_SYMTAB
            continue
        string_section = sections[section[6]]
        strings = blob[string_section[4] : string_section[4] + string_section[5]]
        raw = blob[section[4] : section[4] + section[5]]
        entry_bytes = section[9] or 16
        _require(entry_bytes >= 16, "invalid ELF symbol entry size")
        for offset in range(0, len(raw) - 15, entry_bytes):
            name_offset, value, size, info, other, section_index = struct.unpack_from(
                "<IIIBBH", raw, offset
            )
            name = _c_string(strings, name_offset) if name_offset else ""
            symbols.append(
                {
                    "name": name,
                    "value": value,
                    "size": size,
                    "info": info,
                    "other": other,
                    "section_index": section_index,
                }
            )
    _require(symbols, "AXF has no symbol table")
    return sections, symbols


def _thumb_bl_target(address: int, first: int, second: int) -> int:
    sign = (first >> 10) & 1
    j1 = (second >> 13) & 1
    j2 = (second >> 11) & 1
    i1 = (~(j1 ^ sign)) & 1
    i2 = (~(j2 ^ sign)) & 1
    displacement = (
        (sign << 24)
        | (i1 << 23)
        | (i2 << 22)
        | ((first & 0x03FF) << 12)
        | ((second & 0x07FF) << 1)
    )
    if displacement & (1 << 24):
        displacement -= 1 << 25
    return (address + 4 + displacement) & 0xFFFFFFFF


def _trace_epd_initial(
    code: bytes, address: int, symbols: list[dict[str, int | str]]
) -> tuple[list[list[Any]], int]:
    symbol_at: dict[int, str] = {}
    supported = {
        "reset",
        "EPD_Check_Busy",
        "EPD_WriteCMD_ToBoth",
        "EPD_WriteDATA_ToBoth",
        "sendSPICommand",
        "sendSPIData",
    }
    for symbol in symbols:
        name = str(symbol["name"])
        if name in supported:
            symbol_at[int(symbol["value"]) & ~1] = name

    calls: list[tuple[str, int | None]] = []
    r0: int | None = None
    offset = 0
    while offset + 2 <= len(code):
        first = struct.unpack_from("<H", code, offset)[0]
        instruction_address = address + offset
        if first & 0xF800 == 0x2000:  # MOVS Rd, #imm8
            if (first >> 8) & 7 == 0:
                r0 = first & 0xFF
            offset += 2
            continue
        if offset + 4 <= len(code):
            second = struct.unpack_from("<H", code, offset + 2)[0]
            if first & 0xF800 == 0xF000 and second & 0xD000 == 0xD000:
                target = _thumb_bl_target(instruction_address, first, second)
                _require(
                    target in symbol_at, f"unsupported epdInitial BL target {target:#x}"
                )
                calls.append((symbol_at[target], r0))
                r0 = None
                offset += 4
                continue
        if first & 0xF800 in (0xE800, 0xF000, 0xF800):
            offset += 4
        else:
            offset += 2

    trace: list[list[Any]] = []
    for name, value in calls:
        if name == "reset":
            trace.append(["reset"])
        elif name == "EPD_Check_Busy":
            trace.append(["busy"])
        elif name in ("EPD_WriteCMD_ToBoth", "sendSPICommand"):
            _require(value is not None, "command call has no immediate r0 value")
            target = "both" if name == "EPD_WriteCMD_ToBoth" else "legacy"
            trace.append(["write", target, value, []])
        elif name in ("EPD_WriteDATA_ToBoth", "sendSPIData"):
            _require(value is not None, "data call has no immediate r0 value")
            _require(
                bool(trace) and trace[-1][0] == "write",
                "data call does not follow a command",
            )
            trace[-1][3].append(value)
    return trace, len(calls)


def _canonical_trace_hash(trace: list[list[Any]]) -> str:
    payload = json.dumps(trace, ensure_ascii=True, separators=(",", ":")).encode(
        "ascii"
    )
    return _sha256(payload)


def _expected_dual_trace_as_lists() -> list[list[Any]]:
    result: list[list[Any]] = []
    for item in EXPECTED_DUAL_TRACE:
        if item[0] == "write":
            result.append([item[0], item[1], item[2], list(item[3])])
        else:
            result.append([item[0]])
    return result


def _audit_image(reference_root: Path, expected: dict[str, Any]) -> dict[str, Any]:
    name = str(expected["name"])
    axf_path = reference_root / OUTPUT_REL / f"{name}.axf"
    map_path = reference_root / OUTPUT_REL / f"{name}.map"
    axf = _read_pinned(
        axf_path, int(expected["axf_bytes"]), str(expected["axf_sha256"])
    )
    map_data = _read_pinned(
        map_path, int(expected["map_bytes"]), str(expected["map_sha256"])
    )

    sections, symbols = _parse_elf32_symbols(axf)
    epd_symbols = [
        symbol
        for symbol in symbols
        if symbol["name"] == "epdInitial" and int(symbol["size"]) > 0
    ]
    _require(len(epd_symbols) == 1, f"{name}: epdInitial is not unique")
    epd = epd_symbols[0]
    epd_va = int(epd["value"]) & ~1
    section = sections[int(epd["section_index"])]
    epd_file_offset = section[4] + epd_va - section[3]
    epd_bytes = int(epd["size"])
    code = axf[epd_file_offset : epd_file_offset + epd_bytes]

    _require(epd_va == expected["epd_va"], f"{name}: epdInitial VA changed")
    _require(
        epd_file_offset == expected["epd_file_offset"],
        f"{name}: epdInitial file offset changed",
    )
    _require(epd_bytes == expected["epd_bytes"], f"{name}: epdInitial size changed")
    _require(
        _sha256(code) == expected["epd_sha256"],
        f"{name}: epdInitial identity changed",
    )

    trace, call_count = _trace_epd_initial(code, epd_va, symbols)
    trace_sha256 = _canonical_trace_hash(trace)
    _require(call_count == expected["call_count"], f"{name}: call count changed")
    _require(trace_sha256 == expected["trace_sha256"], f"{name}: init trace changed")
    if expected["dual"]:
        _require(
            trace == _expected_dual_trace_as_lists(), f"{name}: dual trace changed"
        )

    symbol_names = {str(symbol["name"]) for symbol in symbols}
    forbidden_symbol_hits = sorted(FORBIDDEN_LOADER_SYMBOLS & symbol_names)
    marker_hits = [
        marker.decode("ascii")
        for marker in FORBIDDEN_LOADER_MARKERS
        if marker in axf or marker in map_data
    ]
    _require(not forbidden_symbol_hits, f"{name}: forbidden loader symbol found")
    _require(not marker_hits, f"{name}: forbidden loader marker found")
    _require(NOOTP_REMOVAL in map_data, f"{name}: dormant noOTP removal missing")

    return {
        "name": name,
        "axf": {
            "bytes": len(axf),
            "sha256": _sha256(axf),
            "epd_initial_va": f"0x{epd_va:08X}",
            "epd_initial_file_offset": f"0x{epd_file_offset:X}",
            "epd_initial_bytes": epd_bytes,
            "epd_initial_sha256": _sha256(code),
        },
        "map": {
            "bytes": len(map_data),
            "sha256": _sha256(map_data),
            "dormant_nootp_removed": True,
        },
        "factory_init": {
            "call_count": call_count,
            "transaction_count": len(trace),
            "normalized_trace_sha256": trace_sha256,
            "write_target": "both" if expected["dual"] else "legacy",
            "shared_dual_trace": bool(expected["dual"]),
        },
        "loader_search": {
            "forbidden_symbol_hits": forbidden_symbol_hits,
            "forbidden_marker_hits": marker_hits,
            "named_or_fingerprinted_800_loader_found": False,
        },
    }


def _extract_initializer(source: bytes) -> bytes:
    text = source.decode("ascii")
    _require("WF23_25[SIZE]" in text, "WF23 declaration is missing")
    body = text.split("{", 1)[1].split("}", 1)[0]
    values = bytes(int(value, 16) for value in re.findall(r"0x([0-9A-Fa-f]{2})", body))
    _require(len(values) == 876, "WF23 initializer length changed")
    return values


def _audit_wf23_linkage(reference_root: Path, vendor_archive: Path) -> dict[str, Any]:
    wf23 = _read_pinned(reference_root / WF23_REL, 5_776, EXPECTED_WF23_SOURCE_SHA256)
    wrapper = _extract_initializer(wf23)
    _require(
        _sha256(wrapper) == EXPECTED_WF23_WRAPPER_SHA256,
        "WF23 wrapper identity mismatch",
    )
    project = _read_pinned(
        reference_root / PROJECT_REL, 22_696, EXPECTED_PROJECT_SHA256
    ).decode("utf-8-sig")
    editor = _read_pinned(
        reference_root / EDITOR_STATE_REL, 196_072, EXPECTED_EDITOR_STATE_SHA256
    ).decode("utf-8-sig")

    project_paths = re.findall(r"<FilePath>([^<]+)</FilePath>", project)
    listed_in_project = any(
        path.replace("\\", "/").lower().endswith("/projects/mdk-arm/12")
        or "wf23_25" in path.lower()
        for path in project_paths
    )
    editor_names = re.findall(r"<Name>([^<]+)</Name>", editor)
    editor_matches = [
        name
        for name in editor_names
        if name.replace("\\", "/").lower().endswith("/projects/mdk-arm/12")
    ]
    _require(not listed_in_project, "WF23 unexpectedly entered the Keil project")
    _require(len(editor_matches) == 1, "WF23 editor-only document is not unique")

    archive = _read_pinned(
        vendor_archive,
        vendor_archive.stat().st_size,
        EXPECTED_VENDOR_ARCHIVE_SHA256,
    )
    # Re-open by path so ZipFile can seek without retaining another emitted copy.
    _require(_sha256(archive) == EXPECTED_VENDOR_ARCHIVE_SHA256, "archive changed")
    with ZipFile(vendor_archive) as package:
        archived_wf23 = package.read(WF23_ARCHIVE_ENTRY)
    _require(archived_wf23 == wf23, "archive/extracted WF23 mismatch")

    return {
        "path": WF23_REL.as_posix(),
        "source_bytes": len(wf23),
        "source_sha256": _sha256(wf23),
        "initializer_bytes": len(wrapper),
        "initializer_sha256": _sha256(wrapper),
        "vendor_archive_sha256": _sha256(archive),
        "archive_entry_matches_extracted_file": True,
        "listed_in_keil_project": False,
        "opened_as_editor_document": True,
        "editor_document_match_count": len(editor_matches),
        "editor_document_suffix": "Projects/MDK-ARM/12",
        "linked_final_image_reference_found": False,
        "classification": "vendor-supplied-editor-only-not-built",
        "waveform_plaintext_or_key_emitted": False,
    }


def build_report(
    reference_root: Path = DEFAULT_REFERENCE_ROOT,
    vendor_archive: Path = DEFAULT_VENDOR_ARCHIVE,
) -> dict[str, Any]:
    images = [_audit_image(reference_root, expected) for expected in EXPECTED_IMAGES]
    dual_names = tuple(
        image["name"] for image in images if image["factory_init"]["shared_dual_trace"]
    )
    _require(dual_names == EXPECTED_DUAL_SET, "shared dual-init set changed")
    _require(
        all(
            image["loader_search"]["named_or_fingerprinted_800_loader_found"] is False
            for image in images
        ),
        "an identity-pinned final image contains an 800-loader fingerprint",
    )
    wf23 = _audit_wf23_linkage(reference_root, vendor_archive)

    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "identity_pinned_final_axf_map_pairs": len(images),
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "device_network_accessed": False,
            "firmware_written": False,
            "visible_refresh_requested": False,
            "waveform_plaintext_or_key_emitted": False,
        },
        "images": images,
        "shared_dual_factory_init": {
            "image_count": len(dual_names),
            "images": list(dual_names),
            "normalized_encoding": "compact-json-v1",
            "normalized_trace_sha256": EXPECTED_DUAL_TRACE_SHA256,
            "transaction_count": len(EXPECTED_DUAL_TRACE),
            "all_writes_use_both_chip_selects": True,
            "psr_bytes": [0x5F, 0x69],
            "psr_lut_en": False,
            "cascade_e0_value": 0x01,
            "tres_per_controller": [512, 600],
            "runtime_lut_upload_in_trace": False,
        },
        "same_build_loader_search": {
            "axf_count": len(images),
            "map_count": len(images),
            "markers_checked": [
                marker.decode("ascii") for marker in FORBIDDEN_LOADER_MARKERS
            ],
            "symbols_checked": sorted(FORBIDDEN_LOADER_SYMBOLS),
            "all_markers_and_symbols_absent": True,
            "same_build_800_byte_loader_found": False,
            "scope_note": (
                "This is an exact negative over the seven delivered final AXF/MAP "
                "pairs, not proof that an unpublished anonymous loader cannot exist."
            ),
        },
        "wf23_linkage": wf23,
        "verdict": {
            "same_panel_factory_dual_init_proven": True,
            "wf23_vendor_identity_proven": True,
            "wf23_linked_or_reachable_in_final_images": False,
            "same_build_800_byte_loader_proven": False,
            "dual_runtime_mode1_contract_proven": False,
            "h3_live_execution_unlocked_by_this_audit": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-root", type=Path, default=DEFAULT_REFERENCE_ROOT)
    parser.add_argument("--vendor-archive", type=Path, default=DEFAULT_VENDOR_ARCHIVE)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = build_report(args.reference_root, args.vendor_archive)
    except (AuditError, OSError, KeyError, ValueError) as exc:
        print(f"audit failed: {exc}", file=sys.stderr)
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
