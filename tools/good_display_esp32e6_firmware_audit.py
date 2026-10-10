#!/usr/bin/env python3
"""Audit Good Display's official ESP32E6-E01 firmware bundle offline.

The audit is deliberately read-only.  It verifies a frozen vendor ZIP and its
three flash images, parses ESP32 partition/application containers, and reports
only static evidence.  Raw byte matches are never promoted to panel-register
or runtime-waveform evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import sys
from typing import Any
from zipfile import BadZipFile, ZipFile


KIND = "good-display-esp32e6-e01-official-firmware-static-audit"
SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VENDOR_ZIP = (
    REPO_ROOT
    / ".test-output"
    / "offline"
    / "good_display_esp32e6_e01_firmware_20260604"
    / "7.3in_Firmware_Wifi_USB_SD.zip"
)

OFFICIAL_SOURCE = {
    "product_page": "https://www.good-display.com/product/586.html",
    "resource_page": "https://www.good-display.com/companyfile/2071.html",
    "download_redirect": (
        "https://www.good-display.com/comp/xcompanyFile/downloadNew.do"
        "?appId=24&fid=2700&id=2071"
    ),
    "cdn_url": (
        "https://v4.cecdn.yun300.cn/100001_1909185148/"
        "7.3%E2%80%9C%20Firmware%20%20-Wifi.%20USB.%20SD-.zip"
    ),
    "resource_title": (
        '7.3" ESP32E6-E01 Driver Board - Firmware Flashing via WiFi/USB/SD'
    ),
    "published_at": "2026-06-04 13:48:00",
}

EXPECTED_ZIP = {
    "bytes": 1_156_950,
    "sha256": "8eaff3e3a68da354c6ad1fc62a1d6b6ee2144df64198ab35a544e5a96f868a96",
}

EXPECTED_IMAGES = {
    "GDEP073E01wifi.bin": {
        "bytes": 16_777_216,
        "sha256": "df8959b99304d3b6d0b7e560cc4db03a5edb9ffe28640f7428d662285b548508",
        "app_partition_sha256": (
            "09b1838ddd7deb61da0973b60d6029623b02f75ed85d46d1f8dbcd6c8b6338b9"
        ),
        "validation_sha256": (
            "df1a985fa339e1bd0f07b1abf3c418b229b8d6a45cd7196a411cad7bbf1d3703"
        ),
    },
    "SD.bin": {
        "bytes": 4_194_304,
        "sha256": "86d9da5e0200ccbf0a5ef7a90a1b89bc06b554d591a3a24cdb99d2648672dcf5",
        "app_partition_sha256": (
            "2c9baa139f23667391da5c8d8c533708bfaca87b2ea693c66d34ca103fac0c4a"
        ),
        "validation_sha256": (
            "fbbe0f3fb8982a6660fcec584c88ffef65b7bb6b0c3e46534b42e91327db3a66"
        ),
    },
    "usb.bin": {
        "bytes": 4_194_304,
        "sha256": "f21bd62bd2171e4fa30c527847b60313dba746cc16eb44a3ecba9e178551cdad",
        "app_partition_sha256": (
            "7479dcf4f3cd0a2d03ec794f4bf9069b24270a09d421bdcc9c2cf3c413fa39f0"
        ),
        "validation_sha256": (
            "83cce6e9875c08f4f182fe8d079cff068d9796547ef4070ffb621fb0a03dff7d"
        ),
    },
}

EXPECTED_PARTITION_MD5 = "98f492a471b542a1572d58e33e614dc8"
APP_OFFSET = 0x10000
APP_SIZE = 0x300000
ASCII_RE = re.compile(rb"[\x20-\x7e]{4,}")


class FirmwareAuditError(ValueError):
    """Raised when a frozen identity or ESP container invariant is violated."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise FirmwareAuditError(message)


def _cstring(data: bytes) -> str:
    return data.split(b"\0", 1)[0].decode("ascii", "replace")


def _hex(value: int) -> str:
    return f"0x{value:x}"


def _parse_partition_table(flash: bytes) -> dict[str, Any]:
    table = flash[0x8000:0x9000]
    _expect(len(table) == 0x1000, "flash image is too short for partition table")
    entries: list[dict[str, Any]] = []
    md5_offset: int | None = None
    stored_md5: bytes | None = None
    for offset in range(0, len(table), 32):
        entry = table[offset : offset + 32]
        if entry[:2] == b"\xaa\x50":
            part_type, subtype, part_offset, size = struct.unpack_from(
                "<BBII", entry, 2
            )
            entries.append(
                {
                    "label": _cstring(entry[12:28]),
                    "type": f"0x{part_type:02x}",
                    "subtype": f"0x{subtype:02x}",
                    "offset": _hex(part_offset),
                    "bytes": size,
                    "flags": _hex(struct.unpack_from("<I", entry, 28)[0]),
                }
            )
            continue
        if entry[:2] == b"\xeb\xeb":
            md5_offset = offset
            stored_md5 = entry[16:32]
            break
        if entry == b"\xff" * 32:
            break
        raise FirmwareAuditError(
            f"unexpected partition-table entry magic at 0x{offset:x}"
        )
    _expect(md5_offset is not None and stored_md5 is not None, "partition MD5 missing")
    calculated = hashlib.md5(table[:md5_offset]).hexdigest()  # noqa: S324
    stored = stored_md5.hex()
    _expect(calculated == stored, "partition-table MD5 validation failed")
    _expect(stored == EXPECTED_PARTITION_MD5, "partition-table identity mismatch")
    expected_layout = [
        ("nvs", "0x9000", 0x5000),
        ("otadata", "0xe000", 0x2000),
        ("app0", "0x10000", 0x300000),
        ("spiffs", "0x310000", 0xE0000),
        ("coredump", "0x3f0000", 0x10000),
    ]
    _expect(
        [(item["label"], item["offset"], item["bytes"]) for item in entries]
        == expected_layout,
        "partition-table layout mismatch",
    )
    return {
        "offset": "0x8000",
        "entries": entries,
        "md5": stored,
        "md5_valid": True,
        "identical_expected_layout": True,
    }


def _parse_app_image(
    flash: bytes, expected: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    partition = flash[APP_OFFSET : APP_OFFSET + APP_SIZE]
    _expect(len(partition) == APP_SIZE, "flash image is too short for app0")
    partition_sha = _sha256(partition)
    _expect(
        partition_sha == expected["app_partition_sha256"],
        "app0 partition identity mismatch",
    )
    _expect(partition[0] == 0xE9, "ESP application magic is not 0xe9")
    segment_count = partition[1]
    _expect(1 <= segment_count <= 16, "implausible ESP segment count")
    spi_mode = partition[2]
    size_freq = partition[3]
    entry_addr = struct.unpack_from("<I", partition, 4)[0]
    chip_id = struct.unpack_from("<H", partition, 12)[0]
    hash_appended = bool(partition[23])

    offset = 24
    checksum = 0xEF
    segments: list[dict[str, Any]] = []
    segment_data: list[dict[str, Any]] = []
    for index in range(segment_count):
        _expect(offset + 8 <= len(partition), "truncated ESP segment header")
        load_address, size = struct.unpack_from("<II", partition, offset)
        data_offset = offset + 8
        end = data_offset + size
        _expect(end <= len(partition), "truncated ESP segment data")
        data = partition[data_offset:end]
        for value in data:
            checksum ^= value
        item = {
            "index": index,
            "app_file_offset": _hex(data_offset),
            "load_address": _hex(load_address),
            "bytes": size,
            "sha256": _sha256(data),
        }
        segments.append(item)
        segment_data.append(
            {
                **item,
                "app_file_offset_int": data_offset,
                "load_address_int": load_address,
                "data": data,
            }
        )
        offset = end

    checksum_offset = ((offset + 16) // 16) * 16 - 1
    _expect(checksum_offset < len(partition), "ESP checksum is out of range")
    stored_checksum = partition[checksum_offset]
    _expect(stored_checksum == checksum, "ESP image checksum validation failed")
    validation_offset = checksum_offset + 1
    validation = partition[validation_offset : validation_offset + 32]
    _expect(hash_appended, "ESP image does not declare an appended SHA-256")
    _expect(len(validation) == 32, "truncated ESP validation SHA-256")
    calculated_validation = _sha256(partition[:validation_offset])
    _expect(
        validation.hex() == calculated_validation,
        "ESP appended SHA-256 validation failed",
    )
    _expect(
        calculated_validation == expected["validation_sha256"],
        "ESP validation SHA-256 identity mismatch",
    )

    description_offset = partition.find(struct.pack("<I", 0xABCD5432), 24, 512)
    _expect(description_offset >= 0, "ESP application description missing")
    desc = partition[description_offset : description_offset + 256]
    _expect(len(desc) == 256, "truncated ESP application description")
    flash_sizes = {
        0: "1MB",
        1: "2MB",
        2: "4MB",
        3: "8MB",
        4: "16MB",
        5: "32MB",
        6: "64MB",
        7: "128MB",
    }
    flash_speeds = {0: "40MHz", 1: "26.7MHz", 2: "20MHz", 0xF: "80MHz"}
    flash_modes = {0: "QIO", 1: "QOUT", 2: "DIO", 3: "DOUT"}
    report = {
        "partition_offset": _hex(APP_OFFSET),
        "partition_bytes": APP_SIZE,
        "partition_sha256": partition_sha,
        "magic": "0xe9",
        "chip": "ESP32-S3" if chip_id == 9 else f"unknown-id-{chip_id}",
        "chip_id": chip_id,
        "entry_address": _hex(entry_addr),
        "flash_mode": flash_modes.get(spi_mode, f"unknown-{spi_mode}"),
        "flash_size": flash_sizes.get(size_freq >> 4, f"unknown-{size_freq >> 4}"),
        "flash_frequency": flash_speeds.get(
            size_freq & 0xF, f"unknown-{size_freq & 0xF}"
        ),
        "segment_count": segment_count,
        "segments": segments,
        "checksum": f"0x{stored_checksum:02x}",
        "checksum_valid": True,
        "validation_sha256": calculated_validation,
        "validation_sha256_valid": True,
        "actual_image_bytes": validation_offset + 32,
        "application_description": {
            "version": _cstring(desc[16:48]),
            "project_name": _cstring(desc[48:80]),
            "compile_time": _cstring(desc[80:96]),
            "compile_date": _cstring(desc[96:112]),
            "idf_version": _cstring(desc[112:144]),
            "elf_sha256_prefix": desc[144:176].hex(),
        },
    }
    return report, segment_data


def _strings(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for segment in segments:
        data = segment["data"]
        for match in ASCII_RE.finditer(data):
            offset = match.start()
            found.append(
                {
                    "text": match.group().decode("ascii"),
                    "segment_index": segment["index"],
                    "segment_offset": _hex(offset),
                    "app_file_offset": _hex(segment["app_file_offset_int"] + offset),
                    "virtual_address": _hex(segment["load_address_int"] + offset),
                }
            )
    return found


def _literal_occurrences(
    strings: list[dict[str, Any]], needle: str, *, exact: bool = False
) -> list[dict[str, Any]]:
    lowered = needle.lower()
    result = []
    for item in strings:
        text = item["text"]
        matched = text.lower() == lowered if exact else lowered in text.lower()
        if matched:
            result.append(item)
    return result


def _business_literal_report(strings: list[dict[str, Any]]) -> dict[str, Any]:
    terms = [
        "SPD1657",
        "SPD1656",
        "ED2208",
        "WF20_25",
        "WF23_25",
        "waveform",
        "brightness",
        "CS2",
        "SL_CSB",
        "dual controller",
        "second controller",
        "0x20",
        "0x21",
    ]
    direct: dict[str, list[dict[str, Any]]] = {
        term: _literal_occurrences(strings, term) for term in terms
    }
    lut_token = []
    number_tokens: dict[str, list[dict[str, Any]]] = {}
    for item in strings:
        if re.search(r"(?i)(?<![A-Za-z0-9_])lut(?![A-Za-z0-9_])", item["text"]):
            lut_token.append(item)
    for token in ("799", "704", "2508"):
        number_tokens[token] = [
            item
            for item in strings
            if re.search(rf"(?<!\d){token}(?!\d)", item["text"])
        ]
    direct["LUT_token"] = lut_token
    direct.update({f"decimal_{key}": value for key, value in number_tokens.items()})
    return {
        "occurrences": direct,
        "all_controller_runtime_profile_terms_absent": all(
            not direct[key]
            for key in (
                "SPD1657",
                "SPD1656",
                "ED2208",
                "WF20_25",
                "WF23_25",
                "waveform",
                "LUT_token",
                "0x20",
                "0x21",
            )
        ),
    }


def _scan_pattern(
    segments: list[dict[str, Any]], pattern: bytes, *, limit: int = 12
) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    count = 0
    for segment in segments:
        start = 0
        while True:
            offset = segment["data"].find(pattern, start)
            if offset < 0:
                break
            count += 1
            if len(hits) < limit:
                hits.append(
                    {
                        "segment_index": segment["index"],
                        "segment_offset": _hex(offset),
                        "app_file_offset": _hex(
                            segment["app_file_offset_int"] + offset
                        ),
                        "virtual_address": _hex(segment["load_address_int"] + offset),
                    }
                )
            start = offset + 1
    return {
        "pattern_hex": pattern.hex(),
        "count": count,
        "first_hits": hits,
        "classification": "raw_untyped_byte_pattern_only",
        "instruction_or_panel_semantics_proven": False,
    }


def _raw_pattern_report(segments: list[dict[str, Any]]) -> dict[str, Any]:
    patterns = {
        "known_local_e6_init_prefix": bytes.fromhex("aa495520080918"),
        "adjacent_0x20_0x21": bytes.fromhex("2021"),
    }
    for value in (799, 704, 2508, 535, 544, 800):
        patterns[f"{value}_le16"] = value.to_bytes(2, "little")
        patterns[f"{value}_le32"] = value.to_bytes(4, "little")
    return {name: _scan_pattern(segments, value) for name, value in patterns.items()}


def _find_string(strings: list[dict[str, Any]], exact_text: str) -> dict[str, Any]:
    matches = _literal_occurrences(strings, exact_text, exact=True)
    _expect(len(matches) == 1, f"expected one string literal: {exact_text!r}")
    return matches[0]


def _find_word_literals(
    segments: list[dict[str, Any]], value: int
) -> list[dict[str, Any]]:
    pattern = struct.pack("<I", value)
    result = []
    for segment in segments:
        start = 0
        while True:
            offset = segment["data"].find(pattern, start)
            if offset < 0:
                break
            result.append(
                {
                    "segment_index": segment["index"],
                    "virtual_address": _hex(segment["load_address_int"] + offset),
                    "app_file_offset": _hex(segment["app_file_offset_int"] + offset),
                    "raw_bytes": pattern.hex(),
                }
            )
            start = offset + 1
    return result


def _decode_l32r_references(
    segments: list[dict[str, Any]], target: int
) -> list[dict[str, Any]]:
    """Find Xtensa L32R encodings targeting one literal-pool word.

    Xtensa L32R is a three-byte RRI16 instruction.  The scan deliberately
    returns candidates; fixed addresses below are also checked with the vendor
    toolchain's objdump, because a byte sweep alone does not prove control-flow
    reachability.
    """

    result = []
    for segment in segments:
        base = segment["load_address_int"]
        if not (0x40000000 <= base < 0x50000000):
            continue
        data = segment["data"]
        for offset in range(len(data) - 2):
            first, low, high = data[offset : offset + 3]
            if first & 0x0F != 1:
                continue
            immediate = low | (high << 8)
            if immediate & 0x8000:
                immediate -= 0x10000
            address = base + offset
            decoded_target = ((address + 3) & ~3) + immediate * 4
            if decoded_target == target:
                result.append(
                    {
                        "virtual_address": _hex(address),
                        "target": _hex(target),
                        "register": f"a{first >> 4}",
                        "raw_bytes": data[offset : offset + 3].hex(),
                        "classification": "candidate_l32r_instruction",
                    }
                )
    return result


def _bytes_at_virtual_address(
    segments: list[dict[str, Any]], address: int, size: int
) -> bytes:
    for segment in segments:
        base = segment["load_address_int"]
        data = segment["data"]
        if base <= address and address + size <= base + len(data):
            start = address - base
            return data[start : start + size]
    raise FirmwareAuditError(f"virtual address {_hex(address)} is not mapped")


def _sd_instruction_evidence(
    strings: list[dict[str, Any]], segments: list[dict[str, Any]]
) -> dict[str, Any]:
    spi_text = _find_string(strings, "Starting SPI initialization...")
    spi_done = _find_string(strings, "SPI initialization completed")
    scan_text = _find_string(strings, "Scanning available images...")
    sd_text = _find_string(strings, "Starting SD card initialization...")
    for item in (spi_text, spi_done, scan_text, sd_text):
        item["address_int"] = int(item["virtual_address"], 16)

    def evidence_for(item: dict[str, Any]) -> dict[str, Any]:
        literals = _find_word_literals(segments, item["address_int"])
        executable_literals = [
            literal
            for literal in literals
            if 0x40000000 <= int(literal["virtual_address"], 16) < 0x50000000
        ]
        refs = []
        for literal in executable_literals:
            refs.extend(
                _decode_l32r_references(segments, int(literal["virtual_address"], 16))
            )
        clean_item = {key: value for key, value in item.items() if key != "address_int"}
        return {
            "string": clean_item,
            "pointer_literals": literals,
            "l32r_candidates": refs,
        }

    spi = evidence_for(spi_text)
    spi_done_report = evidence_for(spi_done)
    scan = evidence_for(scan_text)
    sd_start = evidence_for(sd_text)

    anchors = {
        "spi_function_entry": (0x420024DC, "36c100"),
        "spi_string_l32r": (0x420024E2, "b1dcf6"),
        "sd_spi_begin_argument_window": (
            0x420024F0,
            "3c0e2cfd0cdc1c5b20a220101120a58800",
        ),
        "setup_calls_spi_function": (0x420026E8, "25dfff"),
        "scan_function_entry": (0x42002350, "36c100"),
        "scan_string_l32r": (0x4200235E, "b131f7"),
        "setup_calls_scan_function": (0x420026EB, "65c6ff"),
    }
    verified_anchors = {}
    for name, (address, expected_hex) in anchors.items():
        actual = _bytes_at_virtual_address(
            segments, address, len(bytes.fromhex(expected_hex))
        ).hex()
        _expect(actual == expected_hex, f"SD instruction anchor changed: {name}")
        verified_anchors[name] = {
            "virtual_address": _hex(address),
            "raw_bytes": actual,
            "identity_match": True,
        }

    _expect(
        any(item["virtual_address"] == "0x420024e2" for item in spi["l32r_candidates"]),
        "SD SPI string L32R reference not found",
    )
    _expect(
        any(
            item["virtual_address"] == "0x4200235e" for item in scan["l32r_candidates"]
        ),
        "SD scan string L32R reference not found",
    )
    return {
        "custom_string_paths": {
            "spi_initialization": spi,
            "spi_initialized": spi_done_report,
            "scan_images": scan,
            "sd_card_initialization": sd_start,
        },
        "verified_raw_instruction_anchors": verified_anchors,
        "objdump_decode": {
            "tool": "xtensa-esp32s3-elf-objdump",
            "spi_function": "0x420024dc entry; 0x420024e2 l32r a11,0x42000054",
            "spi_call": "0x420026e8 call8 0x420024dc",
            "scan_function": "0x42002350 entry; 0x4200235e l32r a11,0x42000024",
            "scan_call": "0x420026eb call8 0x42002350",
        },
        "bounded_interpretation": {
            "custom_sd_spi_setup_path_supported": True,
            "argument_order": ["SCK=GPIO21", "MISO=GPIO13", "MOSI=GPIO47", "SS=GPIO48"],
            "argument_basis": (
                "immediate arguments at 0x420024f0..0x420024fe and the adjacent "
                "vendor diagnostic string"
            ),
            "this_is_sd_card_spi_not_panel_lut_transport": True,
            "panel_spi_call_graph_recovered": False,
            "controller_command_0x20_or_0x21_proven": False,
            "runtime_waveform_length_799_704_or_2508_proven": False,
        },
    }


def _host_ui_report(strings: list[dict[str, Any]]) -> dict[str, Any]:
    adjust = _literal_occurrences(strings, "adjustContrast")
    all_text = "\n".join(item["text"] for item in strings)
    return {
        "title_present": "Image Dithering to Epaper" in all_text,
        "real_palette_literal": (
            "REAL_PALETTE = [[255,255,255],[0,0,0],[160,32,32],"
            "[240,224,80],[80,128,184],[96,128,80]]"
        )
        in all_text,
        "driver_palette_literal": (
            "DRIVER_PALETTE = [[255,255,255],[0,0,0],[255,0,0],"
            "[255,255,0],[0,0,255],[0,255,0]]"
        )
        in all_text,
        "dither_algorithms": {
            name: name.lower() in all_text.lower()
            for name in (
                "Floyd-Steinberg",
                "Atkinson",
                "Stucki",
                "Jarvis-Judice-Ninke",
            )
        },
        "adjust_contrast_occurrences": adjust,
        "adjust_contrast_occurrence_count": len(adjust),
        "adjust_contrast_definition_only": len(adjust) == 1,
        "brightness_literal_present": "brightness" in all_text.lower(),
        "classification": "embedded_browser_image_preprocessing_javascript",
        "panel_brightness_or_contrast_register_proven": False,
    }


def _sd_color_report(strings: list[dict[str, Any]]) -> dict[str, Any]:
    expected = {
        "black": "Black (0x0): ",
        "white": "White (0x1): ",
        "yellow": "Yellow (0x2): ",
        "red": "Red (0x3): ",
        "blue": "Blue (0x5): ",
        "green": "Green (0x6): ",
    }
    occurrences = {
        name: _literal_occurrences(strings, text, exact=True)
        for name, text in expected.items()
    }
    return {
        "bmp_color_diagnostics": occurrences,
        "all_six_driver_codes_present": all(
            len(value) == 1 for value in occurrences.values()
        ),
        "driver_color_codes": {
            "black": 0,
            "white": 1,
            "yellow": 2,
            "red": 3,
            "blue": 5,
            "green": 6,
        },
        "classification": "image_pixel_code_mapping_not_runtime_lut",
    }


def _analyze_image(name: str, flash: bytes) -> dict[str, Any]:
    expected = EXPECTED_IMAGES[name]
    _expect(len(flash) == expected["bytes"], f"{name}: size mismatch")
    flash_sha = _sha256(flash)
    _expect(flash_sha == expected["sha256"], f"{name}: SHA-256 mismatch")
    partition_table = _parse_partition_table(flash)
    app, segments = _parse_app_image(flash, expected)
    strings = _strings(segments)
    report: dict[str, Any] = {
        "bytes": len(flash),
        "sha256": flash_sha,
        "identity_match": True,
        "partition_table": partition_table,
        "app": app,
        "ascii_string_count": len(strings),
        "business_literals": _business_literal_report(strings),
        "raw_patterns": _raw_pattern_report(segments),
    }
    if name == "GDEP073E01wifi.bin":
        report["embedded_host_ui"] = _host_ui_report(strings)
    if name == "SD.bin":
        report["sd_pixel_codes"] = _sd_color_report(strings)
        report["instruction_level"] = _sd_instruction_evidence(strings, segments)
    return report


def build_report(vendor_zip: Path = DEFAULT_VENDOR_ZIP) -> dict[str, Any]:
    try:
        zip_bytes = vendor_zip.read_bytes()
    except OSError as error:
        raise FirmwareAuditError(
            f"cannot read vendor ZIP: {vendor_zip}: {error}"
        ) from error
    zip_sha = _sha256(zip_bytes)
    _expect(len(zip_bytes) == EXPECTED_ZIP["bytes"], "vendor ZIP size mismatch")
    _expect(zip_sha == EXPECTED_ZIP["sha256"], "vendor ZIP SHA-256 mismatch")

    try:
        with ZipFile(vendor_zip) as archive:
            corrupt = archive.testzip()
            _expect(corrupt is None, f"vendor ZIP CRC failure: {corrupt}")
            file_entries = [item for item in archive.infolist() if not item.is_dir()]
            by_basename: dict[str, Any] = {}
            for item in file_entries:
                path = PurePosixPath(item.filename.replace("\\", "/"))
                _expect(not path.is_absolute(), "absolute path in vendor ZIP")
                _expect(".." not in path.parts, "parent traversal in vendor ZIP")
                _expect(path.name not in by_basename, "duplicate ZIP basename")
                by_basename[path.name] = item
            _expect(
                set(by_basename) == set(EXPECTED_IMAGES),
                "vendor ZIP file set mismatch",
            )
            images = {
                name: _analyze_image(name, archive.read(by_basename[name]))
                for name in sorted(EXPECTED_IMAGES)
            }
            entries = [
                {
                    "basename": name,
                    "archive_name_ascii": ascii(by_basename[name].filename),
                    "bytes": by_basename[name].file_size,
                    "compressed_bytes": by_basename[name].compress_size,
                    "crc32": f"0x{by_basename[name].CRC:08x}",
                    "sha256": images[name]["sha256"],
                }
                for name in sorted(EXPECTED_IMAGES)
            ]
    except BadZipFile as error:
        raise FirmwareAuditError(f"invalid vendor ZIP: {error}") from error

    literal_negative = all(
        image["business_literals"]["all_controller_runtime_profile_terms_absent"]
        for image in images.values()
    )
    init_prefix_absent = all(
        image["raw_patterns"]["known_local_e6_init_prefix"]["count"] == 0
        for image in images.values()
    )
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "source": OFFICIAL_SOURCE,
        "vendor_zip": {
            "path": str(vendor_zip),
            "bytes": len(zip_bytes),
            "sha256": zip_sha,
            "identity_match": True,
            "crc_all_entries_valid": True,
            "entries": entries,
        },
        "images": images,
        "cross_image_findings": {
            "all_partition_tables_identical": len(
                {image["partition_table"]["md5"] for image in images.values()}
            )
            == 1,
            "controller_runtime_profile_literals_absent": literal_negative,
            "known_local_e6_init_prefix_absent_as_contiguous_bytes": init_prefix_absent,
            "raw_0x20_0x21_or_numeric_hits_are_abi_evidence": False,
            "spd1657_or_ed2208_abi_recovered": False,
            "runtime_lut_payload_recovered": False,
            "dual_panel_controller_delivery_recovered": False,
            "panel_brightness_or_contrast_control_recovered": False,
            "host_dither_pipeline_recovered": True,
            "sd_six_color_pixel_code_mapping_recovered": True,
            "sd_card_spi_initialization_path_supported": True,
        },
        "evidence_levels": {
            "direct_literals": (
                "embedded browser dithering/palette JavaScript, SD BMP color-code "
                "diagnostics, and SD-card SPI diagnostics"
            ),
            "instruction_level": (
                "identity-pinned SD-card SPI/scan string L32R and local call anchors only"
            ),
            "raw_coincidences": (
                "0x20/0x21 byte pairs and little-endian 799/704/2508 scans; no "
                "controller semantics assigned"
            ),
            "unknown": (
                "stripped-symbol panel transport call graph, controller family, runtime "
                "LUT ABI, dual-controller routing, and panel brightness/contrast registers"
            ),
        },
        "bounded_conclusion": (
            "The official bundle proves host-side six-palette dithering and an SD-card SPI "
            "initialization path. It does not provide a recoverable SPD1657/ED2208 runtime-"
            "LUT contract or a panel brightness/contrast register contract. Raw constants "
            "must not be used to construct a live payload."
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
        },
    }


def canonical_sha256(report: dict[str, Any]) -> str:
    encoded = json.dumps(
        report, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("ascii")
    return _sha256(encoded)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit a frozen Good Display ESP32E6-E01 firmware ZIP offline."
    )
    parser.add_argument("--vendor-zip", type=Path, default=DEFAULT_VENDOR_ZIP)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_report(args.vendor_zip)
    except FirmwareAuditError as error:
        json.dump(
            {"kind": KIND, "schema_version": SCHEMA_VERSION, "error": str(error)},
            sys.stdout,
            ensure_ascii=True,
            indent=2,
        )
        sys.stdout.write("\n")
        return 2
    rendered = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
