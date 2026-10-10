#!/usr/bin/env python3
"""Cross-audit the pinned JD79661AA datasheet, GxEPD2 source, and 79661.csv.

This is a metadata-only public-source audit.  Network access is disabled unless
``--allow-network`` is supplied, and then it is limited to the three pinned
public URLs declared below.  The tool never emits capture bytes, constructs a
waveform payload, or accesses serial, hardware, flash, or a device network.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
import io
import json
from pathlib import Path
import re
import sys
from typing import Any, Final
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.application.durable_io import (  # noqa: E402
    DurableWriteError,
    write_new_bytes_durable,
)
from tools import mf1750_79661_capture_semantics_audit as capture_audit  # noqa: E402


KIND: Final = "jd79661aa-datasheet-gxepd2-capture-cross-audit"
SCHEMA_VERSION: Final = 2
DEFAULT_CAPTURE: Final = capture_audit.DEFAULT_CAPTURE

GXEPD2_COMMIT: Final = capture_audit.GXEPD2_COMMIT
PDF_URL: Final = (
    "https://v4.cecdn.yun300.cn/100001_1909185148/"
    "JD79661AA%20V1.0.4_20230720%20spec.pdf"
)
GX_SOURCE_URL: Final = capture_audit.GXEPD2_SOURCE_URL
GX_HEADER_URL: Final = capture_audit.GXEPD2_HEADER_URL
URLS: Final = {
    "datasheet_pdf": PDF_URL,
    "gxepd2_source": GX_SOURCE_URL,
    "gxepd2_header": GX_HEADER_URL,
}
EXPECTED_IDENTITIES: Final = {
    "datasheet_pdf": (
        3_386_370,
        "fc18052e01fe9d0aba00e15c9c87919659b44d0d2132f8d538bc2045bac67625",
    ),
    "gxepd2_source": capture_audit.GXEPD2_PUBLIC_IDENTITIES[
        "GxEPD2_213c_GDEY0213F51.cpp"
    ],
    "gxepd2_header": capture_audit.GXEPD2_PUBLIC_IDENTITIES[
        "GxEPD2_213c_GDEY0213F51.h"
    ],
}

EXPECTED_PDF_PAGES: Final = 78
EXPECTED_PDFPLUMBER_VERSION: Final = "0.11.10"
EXPECTED_EXTRACTED_TEXT_SHA256: Final = (
    "f2f42bba490d960d288def378f4a81c8d2eba1d6d37a261967b01ef9e3198326"
)
EXPECTED_CRITICAL_PAGE_TEXT: Final = {
    18: (2_634, "821abb420870f2aecf264882ebed3f5bd5b1e9335bd1246ba378d3f71db031c3"),
    19: (2_093, "3fb9521a59e1e164ef75a59c79d0ecfc7e77cbb41323fe84f9b5a9f510bd9a73"),
    20: (1_399, "92de698e982f6f384555a4304c9d77ac148288521b790e18c03a95a0d986d671"),
    21: (1_609, "a56ef9360a25bf992ab9d17456503cb68c4ecd9061f7aac19c239358d41728cf"),
    31: (1_120, "84364f3a5b254b0121e8e81c7c8e41787f7beb017bc75e25954aa3f54a326933"),
    33: (497, "ef16134a3085417e011d975861fd77d19a72831e233771f065f40d96e7053b57"),
    43: (1_122, "6f69706c3fe8d409b66d27daad89ea7cbe189822506e9fa2e413d0a9e73acf30"),
    56: (785, "95db74d035f9905d6788424f8663d61fc55dfb2a3e58798628a72ed1c15684a7"),
    58: (853, "0e3dc2803d50ff42356dd46ba45874745011b6829e78fa4ae5ba7bb7eca544eb"),
    62: (275, "9957dd2a9c3f092a4b1beb50aabfe8ddb8c34932512181cb1fec602de496fe9a"),
    63: (1_707, "7a21b84f47c493922235143700c225e8534ab331396ef9dc50d797b4e26f2870"),
    64: (783, "8ae6b87b378deecc5e0ec212f7b44fd98e5d70227c6a718f2b6c27738faed85a"),
}

EXPECTED_REGISTER_COMMANDS: Final = frozenset(
    {
        0x00,
        0x01,
        0x02,
        0x04,
        0x06,
        0x07,
        0x10,
        0x11,
        0x12,
        0x17,
        0x30,
        0x40,
        0x41,
        0x42,
        0x43,
        0x50,
        0x51,
        0x61,
        0x65,
        0x70,
        0x80,
        0x81,
        0x82,
        0x83,
        0x90,
        0x91,
        0x92,
        0x9F,
        0xE3,
        0xE4,
    }
)

# Parameter rows disclosed by the public register table for the commands used
# by the pinned GxEPD2 initialization.  Command 0x60 is intentionally absent:
# it appears only as an R60H default-setting row in the MTP map, not in the SPI
# register table or register-description section.
DOCUMENTED_PARAMETER_COUNTS: Final = {
    0x00: 2,
    0x01: 6,
    0x04: 0,
    0x06: 7,
    0x30: 1,
    0x50: 1,
    0x61: 4,
    0xE3: 1,
}
COMMAND_NAMES: Final = {
    0x00: "PSR",
    0x01: "PWR",
    0x04: "PON",
    0x06: "BTST",
    0x30: "PLL",
    0x50: "CDI",
    0x61: "TRES",
    0xE3: "PWS",
}

EXPECTED_INIT_TRACE: Final = tuple(
    (group[0], tuple(group[1:])) for group in capture_audit.GXEPD2_INIT_GROUPS
)


class DatasheetAuditError(RuntimeError):
    """Raised when a pinned identity or semantic invariant changes."""


class _RejectRedirects(HTTPRedirectHandler):
    """Fail before urllib follows a redirect outside the three exact URLs."""

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        del req, fp, code, msg, headers
        raise DatasheetAuditError(f"network redirect refused: {newurl}")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DatasheetAuditError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _identity(name: str, payload: bytes, *, enforce_pins: bool) -> dict[str, Any]:
    expected_bytes, expected_sha256 = EXPECTED_IDENTITIES[name]
    result = {
        "url": URLS[name],
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "matches_pin": len(payload) == expected_bytes
        and _sha256(payload) == expected_sha256,
    }
    if enforce_pins:
        _require(result["matches_pin"], f"{name} identity changed")
    return result


def _fetch(name: str, timeout_seconds: float = 30.0) -> bytes:
    _require(name in URLS, f"unrecognized pinned input: {name}")
    url = URLS[name]
    parsed = urlsplit(url)
    _require(parsed.scheme == "https", f"pinned URL is not HTTPS: {name}")
    _require(parsed.hostname is not None, f"pinned URL has no hostname: {name}")
    headers = {"User-Agent": "ESP32-C73-static-audit/1"}
    if name == "datasheet_pdf":
        headers["Referer"] = "https://www.good-display.com/"
    request = Request(url, headers=headers, method="GET")
    opener = build_opener(_RejectRedirects())
    with opener.open(request, timeout=timeout_seconds) as response:
        _require(response.geturl() == url, f"final URL changed for {name}")
        _require(response.status == 200, f"HTTP status changed for {name}")
        return response.read()


def fetch_pinned_inputs() -> dict[str, bytes]:
    """Fetch only the three public URLs fixed in ``URLS``."""

    return {name: _fetch(name) for name in URLS}


def _extract_pdf_text(
    pdf_payload: bytes,
) -> tuple[list[str], dict[str, str], str]:
    try:
        import pdfplumber
    except ImportError as error:  # pragma: no cover - environment failure
        raise DatasheetAuditError(
            "pdfplumber is required for PDF extraction"
        ) from error

    try:
        with pdfplumber.open(io.BytesIO(pdf_payload)) as document:
            pages = [page.extract_text() or "" for page in document.pages]
            metadata = {
                str(key): str(value) for key, value in (document.metadata or {}).items()
            }
    except Exception as error:  # pragma: no cover - parser failure is tool failure
        raise DatasheetAuditError(f"could not parse pinned PDF: {error}") from error
    return pages, metadata, str(pdfplumber.__version__)


def _critical_page_identities(pages: Sequence[str]) -> dict[str, dict[str, Any]]:
    return {
        str(page_number): {
            "characters": len(pages[page_number - 1]),
            "sha256": _sha256(pages[page_number - 1].encode("utf-8")),
        }
        for page_number in EXPECTED_CRITICAL_PAGE_TEXT
    }


def _register_commands(pages: Sequence[str]) -> set[int]:
    table = "\n".join((pages[17], pages[18]))
    return {
        int(value, 16)
        for value in re.findall(r"\bR([0-9A-F]{2})H\b", table, flags=re.IGNORECASE)
    }


def _pdf_semantics(
    pages: Sequence[str],
    metadata: Mapping[str, str],
    *,
    extractor_version: str,
    enforce_pins: bool,
) -> dict[str, Any]:
    _require(len(pages) >= 64, "PDF has too few pages for the audited sections")
    joined = "\f".join(pages)
    full_text_sha256 = _sha256(joined.encode("utf-8"))
    critical = _critical_page_identities(pages)
    commands = _register_commands(pages)
    if enforce_pins:
        _require(
            extractor_version == EXPECTED_PDFPLUMBER_VERSION,
            "pdfplumber version changed",
        )
        _require(len(pages) == EXPECTED_PDF_PAGES, "PDF page count changed")
        _require(
            full_text_sha256 == EXPECTED_EXTRACTED_TEXT_SHA256,
            "full extracted PDF text identity changed",
        )
        for page_number, expected in EXPECTED_CRITICAL_PAGE_TEXT.items():
            observed = critical[str(page_number)]
            _require(
                (observed["characters"], observed["sha256"]) == expected,
                f"critical PDF page {page_number} text identity changed",
            )
        _require(commands == EXPECTED_REGISTER_COMMANDS, "register table changed")

    page_21 = pages[20]
    page_63 = pages[62]
    page_64 = pages[63]
    normalized_64 = re.sub(r"\s+", " ", page_64)
    token_pages = {
        token: [
            page_number
            for page_number, text in enumerate(pages, 1)
            if re.search(rf"\b{token}h\b", text, flags=re.IGNORECASE)
        ]
        for token in ("20", "21")
    }
    command_20_diagram = (
        "LUT0 R10h Data stop" in normalized_64 and "(20h) (11h)" in normalized_64
    )
    lut_register_select = (
        "LUT selection setting" in page_21 and "Using LUT from register" in page_21
    )
    mtp_r60 = "R60H" in page_63 and "S2G[5:0]" in page_63 and "G2S[5:0]" in page_63
    if enforce_pins:
        _require(command_20_diagram, "page 64 LUT0 (20h) marker changed")
        _require(lut_register_select, "PSR LUT register-select description changed")
        _require(mtp_r60, "MTP R60H default rows changed")
        _require(token_pages["20"] == [23, 24, 47, 48, 64], "20h token pages changed")
        _require(token_pages["21"] == [23, 24, 47, 48], "21h token pages changed")

    return {
        "page_count": len(pages),
        "document_content_version": "V1.0.4",
        "document_content_controller": "JD79661AA",
        "text_extractor": "pdfplumber",
        "text_extractor_version": extractor_version,
        "pdf_internal_title": metadata.get("Title"),
        "pdf_internal_title_matches_document_content": metadata.get("Title")
        == "JD79661AA",
        "pdf_internal_author": metadata.get("Author"),
        "pdf_internal_creation_date": metadata.get("CreationDate"),
        "full_extracted_text_characters": len(joined),
        "full_extracted_text_sha256": full_text_sha256,
        "critical_page_text_identities": critical,
        "register_table": {
            "page_numbers": [18, 19],
            "command_count": len(commands),
            "commands": [f"0x{command:02x}" for command in sorted(commands)],
            "command_0x20_present": 0x20 in commands,
            "command_0x21_present": 0x21 in commands,
            "command_0xe9_present": 0xE9 in commands,
        },
        "lut_disclosures": {
            "psr_lut_en_bit_disclosed": lut_register_select,
            "psr_lut_en_meaning": "1 selects LUT from register; 0 selects MTP",
            "mtp_total_bytes": 6_144,
            "mtp_compressed_lut_address_range": "0x0000..0x15df",
            "mtp_compressed_lut_bytes": 0x15E0,
            "register_lut_payload_format_disclosed": False,
            "register_lut_payload_length_disclosed": False,
        },
        "opcode_adjudication": {
            "0x20": {
                "formal_register_table_entry": 0x20 in commands,
                "register_description_section": False,
                "register_restriction_table_entry": False,
                "page_64_waveform_diagram_label": "LUT0 (20h)"
                if command_20_diagram
                else None,
                "page_64_position": "between temperature sensing and R10h data start",
                "case_insensitive_20h_text_occurrences": sum(
                    len(re.findall(r"\b20h\b", text, flags=re.IGNORECASE))
                    for text in pages
                ),
                "case_insensitive_20h_text_occurrence_pages": token_pages["20"],
                "parameter_count_or_payload_format_disclosed": False,
                "bounded_meaning": (
                    "command-like LUT0 timing marker only; the public PDF does not "
                    "define a register-write ABI"
                ),
            },
            "0x21": {
                "formal_register_table_entry": 0x21 in commands,
                "lut1_or_waveform_command_reference": False,
                "case_insensitive_21h_text_occurrences": len(
                    re.findall(r"\b21h\b", joined, flags=re.IGNORECASE)
                ),
                "case_insensitive_21h_text_occurrence_pages": token_pages["21"],
                "occurrences_are_voltage_code_table_values": True,
                "bounded_meaning": "no command meaning is disclosed in this PDF",
            },
            "0xe9": {
                "formal_register_table_entry": 0xE9 in commands,
                "case_insensitive_token_occurrences": len(
                    re.findall(r"\be9h?\b", joined, flags=re.IGNORECASE)
                ),
                "bounded_meaning": "absent from the public PDF",
            },
        },
        "mtp_r60_default_rows_present": mtp_r60,
    }


def _strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//[^\r\n]*", "", source)


def _extract_function(source: str, name: str) -> str:
    marker = f"::{name}("
    start = source.find(marker)
    _require(start >= 0, f"source function not found: {name}")
    opening = source.find("{", start)
    _require(opening >= 0, f"source function body not found: {name}")
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1 : index]
    raise DatasheetAuditError(f"unterminated source function: {name}")


def _header_dimension(header: str, name: str) -> int:
    match = re.search(rf"\b{name}\s*=\s*(\d+)\s*;", header)
    _require(match is not None, f"header dimension not found: {name}")
    assert match is not None
    return int(match.group(1))


def _resolve_source_byte(token: str, dimensions: Mapping[str, int]) -> int:
    compact = re.sub(r"\s+", "", token)
    if re.fullmatch(r"0x[0-9A-Fa-f]+|\d+", compact):
        value = int(compact, 0)
    else:
        match = re.fullmatch(r"(WIDTH|HEIGHT)([/%%])256", compact)
        _require(match is not None, f"non-literal init byte: {token}")
        assert match is not None
        base = dimensions[match.group(1)]
        value = base // 256 if match.group(2) == "/" else base % 256
    _require(0 <= value <= 0xFF, f"init byte outside uint8 range: {token}")
    return value


def _source_init_trace(
    source: str, header: str
) -> tuple[tuple[int, tuple[int, ...]], ...]:
    clean = _strip_comments(source)
    body = _extract_function(clean, "_InitDisplay")
    dimensions = {
        "WIDTH": _header_dimension(header, "WIDTH"),
        "HEIGHT": _header_dimension(header, "HEIGHT"),
    }
    trace: list[tuple[int, list[int]]] = []
    for kind, token in re.findall(r"_write(Command|Data)\(([^()]*)\)\s*;", body):
        value = _resolve_source_byte(token, dimensions)
        if kind == "Command":
            trace.append((value, []))
        else:
            _require(bool(trace), "source data occurs before an init command")
            trace[-1][1].append(value)
    if re.search(r"\b_PowerOn\s*\(\s*\)\s*;", body):
        power_on = _extract_function(clean, "_PowerOn")
        match = re.search(r"_writeCommand\(([^()]*)\)\s*;", power_on)
        _require(match is not None, "_PowerOn has no literal command")
        assert match is not None
        trace.append((_resolve_source_byte(match.group(1), dimensions), []))
    return tuple((command, tuple(data)) for command, data in trace)


def _init_documentation_cross(
    trace: Sequence[tuple[int, Sequence[int]]],
    documented_commands: set[int],
) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    for ordinal, (command, data) in enumerate(trace):
        formal = command in documented_commands
        mtp_default_only = command == 0x60 and not formal
        expected_count = DOCUMENTED_PARAMETER_COUNTS.get(command)
        if formal:
            status = "formal_register_table"
        elif mtp_default_only:
            status = "mtp_default_map_only"
        else:
            status = "absent_from_public_pdf_register_table"
        groups.append(
            {
                "ordinal": ordinal,
                "command": f"0x{command:02x}",
                "source_comment_name_if_formal": COMMAND_NAMES.get(command),
                "source_data_bytes": len(data),
                "datasheet_status": status,
                "datasheet_parameter_rows": expected_count,
                "parameter_count_exactly_matches_datasheet": expected_count == len(data)
                if expected_count is not None
                else False,
            }
        )
    serialized_bytes = sum(1 + len(data) for _, data in trace)
    documented = [
        group
        for group in groups
        if group["datasheet_status"] == "formal_register_table"
    ]
    exact = [
        group
        for group in documented
        if group["parameter_count_exactly_matches_datasheet"]
    ]
    pwr = next(group for group in groups if group["command"] == "0x01")
    psr_data = next(data for command, data in trace if command == 0x00)
    return {
        "source_command_groups": len(trace),
        "source_data_bytes": sum(len(data) for _, data in trace),
        "flattened_command_plus_data_bytes": serialized_bytes,
        "flattened_sha256": capture_audit.GXEPD2_INIT_FLAT_SHA256,
        "groups": groups,
        "formal_register_table_command_groups": len(documented),
        "absent_from_formal_register_table_groups": len(trace) - len(documented),
        "formal_groups_with_exact_parameter_count": len(exact),
        "pwr_source_parameter_count": pwr["source_data_bytes"],
        "pwr_datasheet_parameter_rows": pwr["datasheet_parameter_rows"],
        "pwr_short_write_explicitly_permitted_by_public_pdf": False,
        "psr_source_lut_en_bit": (psr_data[1] >> 7) & 1,
        "psr_source_fopt_bit": (psr_data[1] >> 5) & 1,
        "datasheet_fully_supports_43_byte_init": False,
        "raw_flattened_init_emitted": False,
    }


def _flatten_trace(trace: Sequence[tuple[int, Sequence[int]]]) -> bytes:
    flattened = bytearray()
    for command, data in trace:
        flattened.append(command)
        flattened.extend(data)
    return bytes(flattened)


def _fragment_localization(
    trace: Sequence[tuple[int, Sequence[int]]],
    public_cross: Mapping[str, Any],
) -> dict[str, Any]:
    fragment = public_cross["flattened_init_cross_check"]
    source_offset = int(fragment["maximal_fragment_source_offset"])
    capture_offset = int(fragment["maximal_fragment_capture_offset"])
    length = int(fragment["longest_common_contiguous_fragment_bytes"])
    end = source_offset + length

    group_rows: list[dict[str, Any]] = []
    cursor = 0
    for command, data in trace:
        group_end = cursor + 1 + len(data)
        overlap_start = max(cursor, source_offset)
        overlap_end = min(group_end, end)
        if overlap_start < overlap_end:
            fully_covered = overlap_start == cursor and overlap_end == group_end
            group_rows.append(
                {
                    "command": f"0x{command:02x}",
                    "serialized_group_bytes": group_end - cursor,
                    "overlap_bytes": overlap_end - overlap_start,
                    "group_fully_covered": fully_covered,
                    "formal_register_table_entry": command
                    in EXPECTED_REGISTER_COMMANDS,
                    "datasheet_name": COMMAND_NAMES.get(command),
                }
            )
        cursor = group_end

    complete = [row for row in group_rows if row["group_fully_covered"]]
    documented_bytes = sum(
        row["serialized_group_bytes"]
        for row in complete
        if row["formal_register_table_entry"]
    )
    return {
        "capture_mosi_offset": capture_offset,
        "gxepd2_flattened_init_offset": source_offset,
        "fragment_bytes": length,
        "inside_first_57_byte_timing_run": capture_offset + length <= 57,
        "overlapped_source_groups": group_rows,
        "fully_covered_source_group_count": len(complete),
        "documented_complete_group_bytes": documented_bytes,
        "undocumented_complete_group_bytes": length - documented_bytes,
        "precise_source_localization": (
            "the complete undocumented 0x03 group followed by the complete "
            "documented 0x06 BTST group"
        ),
        "capture_dc_or_command_boundaries_recovered": False,
        "exact_generator_or_panel_proven": False,
        "raw_fragment_emitted": False,
    }


def build_report(
    blobs: Mapping[str, bytes],
    *,
    capture_path: Path = DEFAULT_CAPTURE,
    enforce_pins: bool = True,
    network_accessed: bool = False,
) -> dict[str, Any]:
    missing = sorted(set(URLS) - set(blobs))
    _require(not missing, "missing inputs: " + ", ".join(missing))
    identities = {
        name: _identity(name, blobs[name], enforce_pins=enforce_pins) for name in URLS
    }

    pages, metadata, extractor_version = _extract_pdf_text(blobs["datasheet_pdf"])
    pdf = _pdf_semantics(
        pages,
        metadata,
        extractor_version=extractor_version,
        enforce_pins=enforce_pins,
    )
    source = blobs["gxepd2_source"].decode("utf-8")
    header = blobs["gxepd2_header"].decode("utf-8")
    trace = _source_init_trace(source, header)
    if enforce_pins:
        _require(trace == EXPECTED_INIT_TRACE, "pinned GxEPD2 init trace changed")
    flattened = _flatten_trace(trace)
    if enforce_pins:
        _require(len(flattened) == 43, "GxEPD2 flattened init length changed")
        _require(
            _sha256(flattened) == capture_audit.GXEPD2_INIT_FLAT_SHA256,
            "GxEPD2 flattened init hash changed",
        )

    capture = capture_audit.load_capture(capture_path.resolve())
    timing = capture_audit._timing_report(capture)
    public_cross = capture_audit._gxepd2_public_source_cross_check(capture, timing)
    localization = _fragment_localization(trace, public_cross)
    if enforce_pins:
        _require(
            localization["fully_covered_source_group_count"] == 2,
            "fragment no longer covers exactly two source groups",
        )
        _require(
            localization["documented_complete_group_bytes"] == 8,
            "documented fragment coverage changed",
        )

    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "valid": True,
        "source_identity": {
            "good_display_datasheet_page": "https://www.good-display.com/companyfile/1422.html",
            "gxepd2_repository": "https://github.com/ZinggJM/GxEPD2",
            "gxepd2_commit": GXEPD2_COMMIT,
            "files": identities,
        },
        "datasheet": pdf,
        "gxepd2_init_cross": _init_documentation_cross(
            trace, set(EXPECTED_REGISTER_COMMANDS)
        ),
        "capture_fragment_localization": localization,
        "capture_identity": {
            "bytes": len(capture.payload),
            "sha256": _sha256(capture.payload),
            "decoded_rows": len(capture.mosi),
            "raw_capture_or_mosi_bytes_emitted": False,
        },
        "bounded_conclusion": {
            "command_0x20": (
                "The public JD79661AA PDF shows only a LUT0 (20h) marker in a "
                "timing diagram; it does not disclose a parameter length or LUT ABI."
            ),
            "command_0x21": (
                "The public PDF gives no 0x21 command; its 21h tokens are voltage "
                "table encodings, not a LUT1 definition."
            ),
            "command_0xe9": (
                "The public PDF does not mention E9; only the pinned third-party "
                "GxEPD2 init writes E9 with one data byte."
            ),
            "init_43_bytes": (
                "The PDF formally lists 8 of 15 GxEPD2 init opcodes; seven of those "
                "eight have the disclosed parameter count, while PWR is a 2-byte "
                "prefix of six disclosed parameter rows.  The manual therefore does "
                "not independently support the complete 43-byte sequence."
            ),
            "fragment_12_bytes": (
                "The match is now localized to complete 0x03 and 0x06 source groups; "
                "only the 8-byte 0x06 BTST group is formally documented.  Missing "
                "D/C, CS, and SCLK still prevent transaction recovery."
            ),
            "portable_to_spd1657": False,
            "recovers_spd1657_or_e2802_runtime_waveform_abi": False,
            "authorizes_live_hardware_action": False,
        },
        "safety": {
            "metadata_only": True,
            "network_accessed": network_accessed,
            "network_scope": (
                "one Good Display CDN PDF and two immutable raw GitHub commit URLs"
                if network_accessed
                else "none"
            ),
            "public_internet_only": network_accessed,
            "network_urls_identity_pinned": True,
            "https_get_only": True,
            "network_redirects_allowed": False,
            "device_network_accessed": False,
            "serial_or_com_accessed": False,
            "hardware_accessed": False,
            "flash_written": False,
            "display_refreshed": False,
            "live_payload_generated": False,
            "raw_pdf_or_source_embedded": False,
        },
    }
    report["report_canonical_sha256"] = _sha256(_canonical_bytes(report))
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit pinned JD79661AA public evidence without device I/O."
    )
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="fetch only the three public URLs pinned in this tool",
    )
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--gx-source", type=Path)
    parser.add_argument("--gx-header", type=Path)
    parser.add_argument("--capture", type=Path, default=DEFAULT_CAPTURE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser


def _local_inputs(args: argparse.Namespace) -> dict[str, bytes]:
    paths = {
        "datasheet_pdf": args.pdf,
        "gxepd2_source": args.gx_source,
        "gxepd2_header": args.gx_header,
    }
    _require(
        all(path is not None for path in paths.values()),
        "use --allow-network or provide --pdf, --gx-source, and --gx-header",
    )
    result: dict[str, bytes] = {}
    for name, path in paths.items():
        assert path is not None
        _require(path.is_file() and not path.is_symlink(), f"missing local {name}")
        result[name] = path.read_bytes()
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        local_supplied = any(
            path is not None for path in (args.pdf, args.gx_source, args.gx_header)
        )
        if args.allow_network:
            _require(not local_supplied, "do not mix --allow-network and local inputs")
            blobs = fetch_pinned_inputs()
            network_accessed = True
        else:
            blobs = _local_inputs(args)
            network_accessed = False
        report = build_report(
            blobs,
            capture_path=args.capture,
            enforce_pins=True,
            network_accessed=network_accessed,
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
        DatasheetAuditError,
        DurableWriteError,
        OSError,
        UnicodeError,
        capture_audit.CaptureSemanticsAuditError,
    ) as error:
        print(f"JD79661AA datasheet cross-audit failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
