#!/usr/bin/env python3
"""Cross-check the pinned Good Display GDEP073E01 source and binary contract.

The only optional network operation fetches one exact public Good Display ZIP.
The archive is parsed in memory and only identities, dimensions, code sets, and
tag histograms are emitted.  This tool has no device, serial, flashing, refresh,
or waveform-payload path.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zipfile import BadZipFile, ZipFile


KIND = "good-display-gdep073e01-source-binary-six-color-contract-audit"
SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_RESOURCE_PAGE = "https://www.good-display.com/companyfile/1435.html"
SOURCE_ZIP_URL = "https://v4.cecdn.yun300.cn/100001_1909185148/ESP32-GDEP073E01.zip"
DEFAULT_CROSS_IMAGE_REPORT = (
    REPO_ROOT
    / ".test-output"
    / "offline"
    / "good_display_esp32e6_cross_image_panel_audit_20260812.json"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output"
    / "offline"
    / "good_display_gdep073e01_source_binary_contract_audit_20260812.json"
)

EXPECTED_SOURCE_ZIP_BYTES = 191_983
EXPECTED_SOURCE_ZIP_SHA256 = (
    "3c0136e7bfc45925d134f3dd550813faac4dc7fd2023daa382db88649099a430"
)
EXPECTED_CROSS_REPORT_BYTES = 27_378
EXPECTED_CROSS_REPORT_SHA256 = (
    "3f82c21dca0d59f4c35bd8a390dbea26497dd29b3fb6e502a2ba2c95f1bd7f4b"
)
EXPECTED_CROSS_REPORT_KIND = "good-display-esp32e6-e01-cross-image-panel-audit"

ROOT = "ESP32/GDEP073E01/"
SOURCE_CPP = ROOT + "Display_EPD_W21.cpp"
SOURCE_HEADER = ROOT + "Display_EPD_W21.h"
SOURCE_SPI_CPP = ROOT + "Display_EPD_W21_spi.cpp"
SOURCE_SPI_HEADER = ROOT + "Display_EPD_W21_spi.h"
SOURCE_SKETCH = ROOT + "GDEP073E01.ino"
SOURCE_IMAGE = ROOT + "image.h"
EXPECTED_MEMBER_IDENTITIES: Mapping[str, tuple[int, str]] = {
    SOURCE_CPP: (
        10_002,
        "9d0690776bc3c42dc6351a4b3c8fa9f120f1eddbc036b4e439438f6f38da6456",
    ),
    SOURCE_HEADER: (
        1_768,
        "150e9bf8a51ce6039424ddb98c9b44cafc6f23961a491899f7c6d5c586c5d71a",
    ),
    SOURCE_SPI_CPP: (
        493,
        "3864303de8b0f62e92b7798f6f720f0e06925fcc426b4562ec0068850eb77f29",
    ),
    SOURCE_SPI_HEADER: (
        628,
        "e04d8b3959ea7102fdbe0e19d49992cb1d47aba1af27ee6a5036fa53324642ba",
    ),
    SOURCE_SKETCH: (
        2_329,
        "d582c259b1974b85ee5b0b8e3bb56eb5f0ca14df63b7a25a65b745c5668d9f5a",
    ),
    SOURCE_IMAGE: (
        1_968_083,
        "0f2a69cd768f626ba58bbb4a5cbe4f314137b550d1e39023baf70a959d4bf050",
    ),
}
EXPECTED_MEMBER_NAMES = (ROOT, *EXPECTED_MEMBER_IDENTITIES)

EXPECTED_8BIT_DEFINES = {
    "Black": 0x00,
    "White": 0x11,
    "Green": 0x66,
    "Blue": 0x55,
    "Red": 0x33,
    "Yellow": 0x22,
    "Clean": 0x77,
}
EXPECTED_4BIT_DEFINES = {
    "black": 0x00,
    "white": 0x01,
    "green": 0x06,
    "blue": 0x05,
    "red": 0x03,
    "yellow": 0x02,
    "clean": 0x07,
}
COLOR_NAMES = ("black", "white", "yellow", "red", "blue", "green")
EXPECTED_NATIVE_BY_NAME = {
    "black": 0,
    "white": 1,
    "yellow": 2,
    "red": 3,
    "blue": 5,
    "green": 6,
}
EXPECTED_TAG_TO_NATIVE = {
    0x00: 0,
    0xFF: 1,
    0xFC: 2,
    0xE0: 3,
    0x03: 5,
    0x1C: 6,
}
EXPECTED_TAG_NAME = {
    0x00: "black",
    0xFF: "white",
    0xFC: "yellow",
    0xE0: "red",
    0x03: "blue",
    0x1C: "green",
}
EXPECTED_IMAGE_TAG_COUNTS = {
    0x00: 80_246,
    0x03: 78_729,
    0x1C: 12_006,
    0xE0: 95_570,
    0xFC: 17_541,
    0xFF: 99_908,
}
EXPECTED_BINARY_TAG_TO_NATIVE = {
    0: 0,
    29: 5,
    76: 3,
    150: 6,
    226: 2,
    255: 1,
}
EXPECTED_SOLID_FUNCTIONS = {
    "EPD_Display_White": 0x11,
    "EPD_Display_Black": 0x00,
    "EPD_Display_Yellow": 0x22,
    "EPD_Display_red": 0x33,
    "EPD_Display_blue": 0x55,
    "EPD_Display_Green": 0x66,
}
EXPECTED_DEMO_CALLS = [
    "EPD_Display_White",
    "EPD_Display_Black",
    "EPD_Display_Yellow",
    "EPD_Display_blue",
    "EPD_Display_Green",
    "EPD_Display_red",
]
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


class AuditError(RuntimeError):
    """Raised when an identity pin or semantic contract changes."""


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _relative_or_absolute(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(  # type: ignore[override]
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        raise AuditError(f"vendor source URL redirected; refusing target: {newurl}")


def _validate_source_url(url: str) -> None:
    expected = urlsplit(SOURCE_ZIP_URL)
    actual = urlsplit(url)
    _expect(url == SOURCE_ZIP_URL, "network URL is not the single pinned source URL")
    _expect(actual.scheme == "https", "source URL must use HTTPS")
    _expect(actual.hostname == expected.hostname, "source URL host differs from pin")
    _expect(actual.path == expected.path, "source URL path differs from pin")
    _expect(not actual.query and not actual.fragment, "source URL must have no suffix")


def _fetch_source_zip(url: str, timeout_seconds: float = 30.0) -> bytes:
    _validate_source_url(url)
    request = Request(
        url,
        headers={
            "User-Agent": "ESP32-C73-metadata-only-static-audit/1",
            "Referer": SOURCE_RESOURCE_PAGE,
        },
    )
    opener = build_opener(_RejectRedirect())
    try:
        with opener.open(request, timeout=timeout_seconds) as response:  # noqa: S310
            _expect(response.geturl() == SOURCE_ZIP_URL, "source response URL drift")
            return response.read()
    except HTTPError as exc:
        raise AuditError(f"vendor source fetch failed: HTTP {exc.code}") from exc


def fetch_pinned_source_zip(
    fetcher: Callable[[str], bytes] = _fetch_source_zip,
) -> bytes:
    """Fetch exactly one pinned public-vendor URL."""

    return fetcher(SOURCE_ZIP_URL)


def _strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//[^\r\n]*", "", source)


def _extract_function(source: str, name: str) -> str:
    match = re.search(
        rf"\b{re.escape(name)}\s*\([^;{{}}]*\)\s*\{{",
        source,
    )
    if match is None:
        raise AuditError(f"function not found: {name}")
    opening = match.end() - 1
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1 : index]
    raise AuditError(f"unterminated function: {name}")


def _parse_defines(source: str) -> dict[str, int]:
    return {
        name: int(value, 0)
        for name, value in re.findall(
            r"^\s*#define\s+([A-Za-z_]\w*)\s+(0[xX][0-9A-Fa-f]+|\d+)\b",
            source,
            flags=re.MULTILINE,
        )
    }


def _resolve_byte(token: str, defines: Mapping[str, int]) -> int:
    token = token.strip()
    if token in defines:
        value = defines[token]
    elif re.fullmatch(r"0[xX][0-9A-Fa-f]+|\d+", token):
        value = int(token, 0)
    else:
        raise AuditError(f"non-literal command/data token: {token}")
    _expect(0 <= value <= 0xFF, f"command/data byte out of range: {token}")
    return value


def _read_source_zip(
    raw: bytes, *, enforce_pins: bool
) -> tuple[dict[str, bytes], dict[str, Any]]:
    archive_identity = {
        "bytes": len(raw),
        "sha256": _sha256(raw),
        "matches_pin": len(raw) == EXPECTED_SOURCE_ZIP_BYTES
        and _sha256(raw) == EXPECTED_SOURCE_ZIP_SHA256,
    }
    if enforce_pins and not archive_identity["matches_pin"]:
        raise AuditError("Good Display source ZIP identity differs from the pin")

    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            _expect(len(names) == len(set(names)), "source ZIP has duplicate names")
            _expect(
                tuple(names) == EXPECTED_MEMBER_NAMES,
                "source ZIP member set/order drift",
            )
            _expect(archive.testzip() is None, "source ZIP CRC check failed")
            blobs = {name: archive.read(name) for name in EXPECTED_MEMBER_IDENTITIES}
            manifest = []
            for info in infos:
                payload = b"" if info.is_dir() else blobs[info.filename]
                expected = EXPECTED_MEMBER_IDENTITIES.get(info.filename)
                matches_pin = (
                    info.is_dir()
                    if expected is None
                    else len(payload) == expected[0] and _sha256(payload) == expected[1]
                )
                if enforce_pins and not matches_pin:
                    raise AuditError(f"source member identity drift: {info.filename}")
                manifest.append(
                    {
                        "name": info.filename,
                        "directory": info.is_dir(),
                        "bytes": len(payload),
                        "compressed_bytes": info.compress_size,
                        "crc32": f"{info.CRC:08x}",
                        "sha256": _sha256(payload),
                        "matches_pin": matches_pin,
                    }
                )
    except BadZipFile as exc:
        raise AuditError("Good Display source input is not a valid ZIP") from exc

    archive_identity.update(
        {
            "crc_all_members_valid": True,
            "member_count_including_directory": len(manifest),
            "members": manifest,
        }
    )
    return blobs, archive_identity


def _header_contract(header: str) -> dict[str, Any]:
    marker_8 = header.find("//8bit")
    marker_4 = header.find("//4bit")
    marker_commands = header.find("#define PSR", marker_4)
    _expect(
        0 <= marker_8 < marker_4 < marker_commands,
        "header color-contract markers not found",
    )
    defines_8 = _parse_defines(header[marker_8:marker_4])
    defines_4 = _parse_defines(header[marker_4:marker_commands])
    _expect(defines_8 == EXPECTED_8BIT_DEFINES, "header 8-bit color contract drift")
    _expect(defines_4 == EXPECTED_4BIT_DEFINES, "header 4-bit color contract drift")

    all_defines = _parse_defines(header)
    width = all_defines.get("EPD_WIDTH")
    height = all_defines.get("EPD_HEIGHT")
    _expect(width is not None and height is not None, "panel geometry defines missing")
    _expect(width > 0 and height > 0 and width % 2 == 0, "invalid panel geometry")

    native_by_name = {name: defines_4[name] for name in COLOR_NAMES}
    native_codes = sorted(native_by_name.values())
    _expect(
        native_by_name == EXPECTED_NATIVE_BY_NAME,
        "header six-color native-code mapping drift",
    )
    _expect(4 not in native_codes, "native code 4 entered the header color contract")
    _expect(defines_4["clean"] == 7, "header no longer designates code 7 Clean")
    return {
        "panel": "GDEP073E01",
        "geometry": {"width": width, "height": height},
        "eight_bit_repeated_nibble_defines": defines_8,
        "four_bit_defines": defines_4,
        "six_color_native_by_name": native_by_name,
        "six_color_native_codes": native_codes,
        "native_code4_declared_as_color": False,
        "native_code7_symbol": "clean",
        "native_code7_declared_as_color": False,
    }


def _color_get_contract(source: str) -> dict[str, Any]:
    body = _extract_function(source, "Color_get")
    mapping: dict[int, int] = {}
    for input_token, case_body in re.findall(
        r"\bcase\s+(0[xX][0-9A-Fa-f]+)\s*:(.*?)\bbreak\s*;",
        body,
        flags=re.DOTALL,
    ):
        output = re.search(r"\bdatas\s*=\s*(0[xX][0-9A-Fa-f]+)\s*;", case_body)
        _expect(
            output is not None, f"Color_get case has no literal result: {input_token}"
        )
        mapping[int(input_token, 16)] = int(output.group(1), 16)
    default_block = re.search(r"\bdefault\s*:(.*?)\bbreak\s*;", body, flags=re.DOTALL)
    _expect(default_block is not None, "Color_get default branch missing")
    default = re.search(
        r"\bdatas\s*=\s*(0[xX][0-9A-Fa-f]+)\s*;", default_block.group(1)
    )
    _expect(default is not None, "Color_get default result missing")
    default_code = int(default.group(1), 16)
    _expect(mapping == EXPECTED_TAG_TO_NATIVE, "Color_get six-tag mapping drift")
    _expect(default_code == 0, "Color_get default is no longer native black")
    records = [
        {
            "semantic_comment": EXPECTED_TAG_NAME[tag],
            "input_tag": f"0x{tag:02x}",
            "native_code": mapping[tag],
        }
        for tag in EXPECTED_TAG_TO_NATIVE
    ]
    output_codes = sorted(set(mapping.values()))
    return {
        "mapping": records,
        "input_tags": sorted(mapping),
        "output_native_codes": output_codes,
        "default_native_code": default_code,
        "native_code4_emitted": 4 in output_codes,
        "native_code7_emitted": 7 in output_codes,
    }


def _init_trace(source: str, header: str) -> list[dict[str, str]]:
    clean = _strip_comments(source)
    body = _extract_function(clean, "EPD_init")
    defines = _parse_defines(header + "\n" + source)
    events: list[list[Any]] = []
    for kind, token in re.findall(
        r"EPD_W21_Write(CMD|DATA)\s*\(\s*([^()]*)\s*\)\s*;", body
    ):
        value = _resolve_byte(token, defines)
        if kind == "CMD":
            events.append([value, []])
        else:
            _expect(bool(events), "EPD_init data precedes its first command")
            events[-1][1].append(value)
    trace = [
        {"command": f"0x{int(command):02x}", "data_hex": bytes(data).hex()}
        for command, data in events
    ]
    expected = [
        {"command": f"0x{command:02x}", "data_hex": bytes(data).hex()}
        for command, data in EXPECTED_INIT_TRACE
    ]
    _expect(trace == expected, "official source EPD_init trace drift")
    return trace


def _picture_display_contract(
    source: str, *, width: int, height: int
) -> dict[str, Any]:
    body = _extract_function(_strip_comments(source), "PIC_display")
    compact = re.sub(r"\s+", "", body)
    required = (
        "EPD_W21_WriteCMD(0x10);",
        f"for(i=0;i<{height};i++)",
        f"for(j=0;j<{width}/2;j++)",
        f"temp1=picData[i*{width}+k++];",
        f"temp2=picData[i*{width}+k++];",
        "data_H=Color_get(temp1)<<4;",
        "data_L=Color_get(temp2);",
        "data=data_H|data_L;",
        "EPD_W21_WriteDATA(data);",
        "EPD_W21_WriteCMD(0x12);",
    )
    missing = [item for item in required if item not in compact]
    _expect(not missing, "PIC_display packing contract drift: " + ", ".join(missing))
    input_bytes = width * height
    panel_bytes = input_bytes // 2
    return {
        "typed_commands": ["0x10", "0x12"],
        "input_tag_bytes": input_bytes,
        "panel_data_bytes": panel_bytes,
        "pixels_per_panel_byte": 2,
        "first_pixel_position": "high_nibble",
        "second_pixel_position": "low_nibble",
        "each_pixel_passes_through_Color_get": True,
    }


def _solid_and_demo_contract(
    source: str, sketch: str, *, panel_bytes: int
) -> dict[str, Any]:
    solids: dict[str, dict[str, Any]] = {}
    for function_name, expected_byte in EXPECTED_SOLID_FUNCTIONS.items():
        body = _extract_function(_strip_comments(source), function_name)
        compact = re.sub(r"\s+", "", body)
        match = re.search(
            r"for\(i=0;i<(\d+);i\+\+\)\{EPD_W21_WriteDATA"
            r"\((0[xX][0-9A-Fa-f]+)\);\}",
            compact,
        )
        _expect(match is not None, f"solid fill loop not found: {function_name}")
        count = int(match.group(1))
        repeated_byte = int(match.group(2), 16)
        _expect(count == panel_bytes, f"solid fill length drift: {function_name}")
        _expect(
            repeated_byte == expected_byte,
            f"solid fill code drift: {function_name}",
        )
        _expect(
            repeated_byte >> 4 == repeated_byte & 0x0F,
            f"solid fill no longer repeats one nibble: {function_name}",
        )
        solids[function_name] = {
            "panel_data_bytes": count,
            "repeated_byte": f"0x{repeated_byte:02x}",
            "native_code": repeated_byte & 0x0F,
        }

    calls = re.findall(r"\b(EPD_Display_[A-Za-z]+)\s*\(\s*\)\s*;", sketch)
    _expect(calls == EXPECTED_DEMO_CALLS, "six-solid-color sketch call order drift")
    codes = sorted({item["native_code"] for item in solids.values()})
    _expect(codes == sorted(EXPECTED_NATIVE_BY_NAME.values()), "solid code set drift")
    return {
        "sketch_call_order": calls,
        "solid_functions": solids,
        "solid_native_codes": codes,
        "orange_or_code4_demo_present": False,
        "clean_or_code7_demo_present": False,
    }


def _image_tag_contract(
    image_source: str,
    *,
    input_bytes: int,
    color_get_tags: Sequence[int],
    enforce_pins: bool,
) -> dict[str, Any]:
    clean = _strip_comments(image_source)
    match = re.search(
        r"\bgImage_1\s*\[\s*(\d+)\s*\]\s*=\s*\{(.*?)\}\s*;",
        clean,
        flags=re.DOTALL,
    )
    _expect(match is not None, "gImage_1 initializer not found")
    declared = int(match.group(1))
    tags = [
        int(token, 16)
        for token in re.findall(r"0[xX]([0-9A-Fa-f]{2})\b", match.group(2))
    ]
    counts = Counter(tags)
    _expect(declared == input_bytes, "gImage_1 declared length differs from geometry")
    _expect(len(tags) == declared, "gImage_1 initializer token count drift")
    _expect(set(counts) == set(color_get_tags), "image tag set differs from Color_get")
    if enforce_pins:
        _expect(dict(counts) == EXPECTED_IMAGE_TAG_COUNTS, "image tag histogram drift")
    return {
        "declared_input_bytes": declared,
        "initializer_token_count": len(tags),
        "distinct_tag_count": len(counts),
        "tag_counts": {f"0x{tag:02x}": counts[tag] for tag in sorted(counts)},
        "tag_set_exactly_matches_Color_get_inputs": True,
        "contains_native_panel_payload": False,
        "raw_image_or_payload_emitted": False,
    }


def _cross_image_contract(
    raw: bytes,
    *,
    path_label: str,
    source_trace: Sequence[Mapping[str, str]],
    width: int,
    height: int,
    input_bytes: int,
    panel_bytes: int,
    source_native_codes: Sequence[int],
    enforce_pins: bool,
) -> dict[str, Any]:
    identity = {
        "path": path_label,
        "bytes": len(raw),
        "sha256": _sha256(raw),
        "matches_pin": len(raw) == EXPECTED_CROSS_REPORT_BYTES
        and _sha256(raw) == EXPECTED_CROSS_REPORT_SHA256,
    }
    if enforce_pins and not identity["matches_pin"]:
        raise AuditError("cross-image binary report identity differs from the pin")
    try:
        report = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AuditError("cross-image binary report is not valid UTF-8 JSON") from exc
    _expect(
        report.get("kind") == EXPECTED_CROSS_REPORT_KIND
        and report.get("schema_version") == 1,
        "cross-image binary report kind/schema drift",
    )
    safety = report.get("safety", {})
    _expect(
        safety.get("offline_static_analysis_only") is True, "binary audit not offline"
    )
    for field in (
        "device_network_accessed",
        "display_refreshed",
        "flash_written",
        "hardware_accessed",
        "serial_or_com_accessed",
    ):
        _expect(safety.get(field) is False, f"binary audit safety drift: {field}")

    findings = report.get("cross_image_findings", {})
    geometry = findings.get("panel_geometry")
    _expect(geometry == {"height": height, "width": width}, "binary geometry drift")
    _expect(
        findings.get("unpacked_tag_frame_bytes") == input_bytes,
        "binary input size drift",
    )
    _expect(
        findings.get("packed_frame_bytes") == panel_bytes, "binary panel size drift"
    )
    binary_mapping = {
        int(tag): int(code)
        for tag, code in findings.get("unpacked_tag_to_panel_code", {}).items()
    }
    _expect(
        binary_mapping == EXPECTED_BINARY_TAG_TO_NATIVE,
        "binary six-tag mapping drift",
    )
    binary_codes = sorted(set(binary_mapping.values()))
    _expect(
        binary_codes == list(source_native_codes),
        "source and binary native-code sets differ",
    )

    images = report.get("images", {})
    traces = [image.get("typed_init_trace") for image in images.values()]
    _expect(len(traces) == 3, "binary audit image count drift")
    _expect(
        all(trace == list(source_trace) for trace in traces),
        "source and binary typed init traces differ",
    )
    runtime = report.get("runtime_waveform_boundary", {})
    for field in (
        "dual_controller_delivery_recovered",
        "runtime_lut_length_2508_recovered",
        "runtime_lut_length_704_recovered",
        "runtime_waveform_abi_recovered",
        "typed_command_0x20_recovered",
        "typed_command_0x21_recovered",
    ):
        _expect(runtime.get(field) is False, f"binary runtime boundary drift: {field}")

    return {
        "report_identity": identity,
        "official_bundle_zip_sha256": report.get("base_official_bundle", {}).get(
            "zip_sha256"
        ),
        "binary_image_count": len(traces),
        "all_binary_init_traces_match_source": True,
        "geometry_matches_source": True,
        "frame_sizes_match_source": True,
        "binary_input_tags": sorted(binary_mapping),
        "binary_tag_to_native_code": {
            str(tag): binary_mapping[tag] for tag in sorted(binary_mapping)
        },
        "binary_native_codes": binary_codes,
        "binary_native_code4_present": 4 in binary_codes,
        "binary_native_code7_present": 7 in binary_codes,
        "runtime_waveform_abi_recovered": False,
    }


def build_report(
    source_zip: bytes,
    cross_image_report: bytes,
    *,
    cross_image_path: str = "synthetic-cross-image-report.json",
    enforce_pins: bool = True,
    network_accessed: bool = False,
) -> dict[str, Any]:
    blobs, archive_identity = _read_source_zip(source_zip, enforce_pins=enforce_pins)
    header_text = blobs[SOURCE_HEADER].decode("latin-1")
    cpp_text = blobs[SOURCE_CPP].decode("latin-1")
    sketch_text = blobs[SOURCE_SKETCH].decode("latin-1")
    image_text = blobs[SOURCE_IMAGE].decode("latin-1")

    header = _header_contract(header_text)
    color_get = _color_get_contract(cpp_text)
    _expect(
        color_get["output_native_codes"] == header["six_color_native_codes"],
        "Color_get output set differs from the header contract",
    )
    trace = _init_trace(cpp_text, header_text)
    geometry = header["geometry"]
    display = _picture_display_contract(
        cpp_text,
        width=geometry["width"],
        height=geometry["height"],
    )
    solids = _solid_and_demo_contract(
        cpp_text,
        sketch_text,
        panel_bytes=display["panel_data_bytes"],
    )
    image = _image_tag_contract(
        image_text,
        input_bytes=display["input_tag_bytes"],
        color_get_tags=color_get["input_tags"],
        enforce_pins=enforce_pins,
    )
    cross = _cross_image_contract(
        cross_image_report,
        path_label=cross_image_path,
        source_trace=trace,
        width=geometry["width"],
        height=geometry["height"],
        input_bytes=display["input_tag_bytes"],
        panel_bytes=display["panel_data_bytes"],
        source_native_codes=header["six_color_native_codes"],
        enforce_pins=enforce_pins,
    )

    source_tags = color_get["input_tags"]
    binary_tags = cross["binary_input_tags"]
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "official_2024_source": {
            "resource_page": SOURCE_RESOURCE_PAGE,
            "download_url": SOURCE_ZIP_URL,
            "archive_identity": archive_identity,
            "header_contract": header,
            "Color_get": color_get,
            "PIC_display": display,
            "typed_init_trace": trace,
            "solid_color_demo": solids,
            "image_h_tag_aggregate": image,
        },
        "official_2026_binary_cross_reference": cross,
        "identity_pinned_comparison": {
            "source_native_codes": header["six_color_native_codes"],
            "binary_native_codes": cross["binary_native_codes"],
            "native_code_sets_exactly_equal": True,
            "source_input_tags": source_tags,
            "binary_input_tags": binary_tags,
            "input_tag_sets_equal": source_tags == binary_tags,
            "input_tags_are_transport_or_converter_format_not_native_codes": True,
            "source_and_binary_init_traces_exactly_equal": True,
            "source_and_binary_geometry_exactly_equal": True,
            "source_and_binary_frame_sizes_exactly_equal": True,
        },
        "bounded_conclusion": {
            "official_six_color_native_code_contract": [0, 1, 2, 3, 5, 6],
            "official_source_and_binary_consistent": True,
            "native_code4_is_in_official_contract": False,
            "native_code7_is_a_header_clean_symbol_not_a_demo_or_converter_color": True,
            "orange_contract_recovered": False,
            "runtime_lut_or_waveform_semantics_recovered": False,
            "portable_to_mf17506_dual_1024x600": False,
            "interpretation": (
                "The pinned Good Display source and recovered official binaries agree "
                "only on native codes 0/1/2/3/5/6. Code 4 is absent, while code 7 is "
                "named Clean in the header and is absent from Color_get, image tags, "
                "six solid demos, and the recovered binary code set."
            ),
        },
        "metadata_only": {
            "source_member_contents_emitted": False,
            "image_pixels_or_initializer_emitted": False,
            "panel_payload_emitted": False,
            "waveform_or_lut_payload_emitted": False,
            "only_identities_contracts_counts_and_histograms_emitted": True,
        },
        "safety": {
            "static_analysis_only": True,
            "network_accessed": network_accessed,
            "network_accessed_url_count": 1 if network_accessed else 0,
            "network_scope": SOURCE_ZIP_URL if network_accessed else "none",
            "network_was_single_public_vendor_url_only": network_accessed,
            "network_redirects_allowed": False,
            "source_archive_persisted": False,
            "device_network_accessed": False,
            "serial_or_com_accessed": False,
            "hardware_accessed": False,
            "flash_performed": False,
            "display_refreshed": False,
            "visible_refreshes": 0,
            "live_payload_generated": False,
            "authorization_or_token_generated": False,
        },
    }
    report["report_canonical_sha256"] = _sha256(_canonical_bytes(report))
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit one pinned Good Display GDEP073E01 source ZIP against a local "
            "binary audit (metadata only; no device I/O)."
        )
    )
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="fetch the one exact public Good Display source ZIP URL",
    )
    parser.add_argument(
        "--source-zip",
        type=Path,
        help="offline copy of the exact pinned Good Display source ZIP",
    )
    parser.add_argument(
        "--cross-image-report",
        type=Path,
        default=DEFAULT_CROSS_IMAGE_REPORT,
        help="local identity-pinned 2026 cross-image binary audit JSON",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.allow_network:
            if args.source_zip is not None:
                raise AuditError("do not combine --allow-network and --source-zip")
            source_zip = fetch_pinned_source_zip()
            network_accessed = True
        else:
            if args.source_zip is None:
                raise AuditError("use --allow-network or provide --source-zip")
            source_zip = args.source_zip.read_bytes()
            network_accessed = False
        cross_raw = args.cross_image_report.read_bytes()
        report = build_report(
            source_zip,
            cross_raw,
            cross_image_path=_relative_or_absolute(args.cross_image_report),
            enforce_pins=True,
            network_accessed=network_accessed,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (AuditError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
