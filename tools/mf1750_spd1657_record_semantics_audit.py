#!/usr/bin/env python3
"""Audit local SPD1657/E2802 record semantics without emitting waveform data.

This offline audit adds one source-level evidence item that earlier geometry
audits did not model: ``User/EDP_init.c`` contains a complete commented-out
535-byte table immediately before the compiled ``wf_data`` initializer.  Both
tables carry an inline seven-field header legend and forty-eight inline
``<category>-GROUP<n>`` labels.  The tool identity-pins those two tables, proves
which one was compiled and linked, and compares their coordinates without ever
serializing a waveform byte.

The same pinned GBK source also says that the 535-byte upload loop count varies
with chip specification.  That statement is preserved as source-author intent,
not promoted into proof that the supplied mode-1 wrapper uses 799 bytes.  The
actual mode-0 source dataflow is checked more narrowly as an adjacent
``0x20 -> i=0..534 -> wf_data[i]`` sequence.

It also screens the active table, the commented table, E2801/E2802 DATA0/DATA1,
and WF20_25/WF23_25 against narrowly stated adjacent format hypotheses.  Exact
record width, bit density, and source labels are reported as structural facts;
they are not promoted to SPD1657 duration, polarity, voltage, terminator, or
controller semantics.  No key, plaintext, raw record, payload, include,
firmware, authorization material, or hardware path is produced.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
from typing import Any, Final, Iterable


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.application.durable_io import (  # noqa: E402
    DurableWriteError,
    write_new_bytes_durable,
)
from tools import mf1750_spd1657_arithmetic_transform_audit as arithmetic  # noqa: E402
from tools import mf1750_spd1657_patent_11byte_audit as patent11  # noqa: E402
from tools import mf1750_spd1657_phase_geometry_audit as geometry  # noqa: E402
from tools import mf1750_spd1657_vendor_profile_pack as profile_pack  # noqa: E402


KIND: Final = "mf1750-spd1657-record-semantics-audit"
SCHEMA_VERSION: Final = 3

REFERENCE_ROOT: Final = profile_pack.DEFAULT_REFERENCE_ROOT
LEGACY_USER_ROOT: Final = REFERENCE_ROOT / "User"
LEGACY_SOURCE: Final = LEGACY_USER_ROOT / "EDP_init.c"
LEGACY_UART_DATA_DEAL_SOURCE: Final = LEGACY_USER_ROOT / "UartDataDeal.c"
LEGACY_USART_SOURCE: Final = REFERENCE_ROOT / "Drivers" / "SYSTEM" / "usart" / "usart.c"
LEGACY_OBJECT: Final = REFERENCE_ROOT / "Output" / "edp_init.o"
LEGACY_MAP: Final = REFERENCE_ROOT / "Output" / "WF-79667-168X384.map"
SPD1656_MANUAL: Final = REPO_ROOT / "参考资料" / "Solomon-SPD1656.pdf"

LEGACY_SOURCE_BYTES: Final = 32_220
LEGACY_SOURCE_SHA256: Final = (
    "1b6bbcf35cefc338f7ab9b76c04c869f9a82e800c4ccaa52d204d9fd6e53b7a5"
)
LEGACY_UART_DATA_DEAL_SOURCE_BYTES: Final = 5_047
LEGACY_UART_DATA_DEAL_SOURCE_SHA256: Final = (
    "da853aa6f02c2ec3da271d3bc6dc23c50467b3b6af4e5d8b113dc18304e5d897"
)
LEGACY_USART_SOURCE_BYTES: Final = 6_008
LEGACY_USART_SOURCE_SHA256: Final = (
    "dd3fcf761175113a73740d4b30de40e7c87dfe4500ef0f4c297cb47fda5be460"
)
ACTIVE_535_SHA256: Final = (
    "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b"
)
COMMENTED_535_SHA256: Final = (
    "2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26"
)
COMMENTED_SOURCE_REGION_BYTES: Final = 3_572
COMMENTED_SOURCE_REGION_SHA256: Final = (
    "52e61dd31132de3537223945ca44469e8846a56f02406fbcff2be311b80e378f"
)
ACTIVE_SOURCE_REGION_BYTES: Final = 3_470
ACTIVE_SOURCE_REGION_SHA256: Final = (
    "8ae0bd939759cd243b90587efd40a7486382774e8c0f4c7242d6ebf4281530b8"
)
LEGACY_OBJECT_BYTES: Final = 1_283_980
LEGACY_OBJECT_SHA256: Final = (
    "6854348d4b2dd797974d5d0c00fe806cf519a9a12271f54a9e4e81be864dac76"
)
LEGACY_MAP_BYTES: Final = 257_903
LEGACY_MAP_SHA256: Final = (
    "1780f036ef953d8f5de0a985e56089e91781cebfeecdf4312dd9a09174f60d3a"
)
LEGACY_USER_SOURCE_FILE_COUNT: Final = 21
LEGACY_USER_SOURCE_BYTES: Final = 1_965_112
LEGACY_USER_SOURCE_MANIFEST_SHA256: Final = (
    "c0df8659bc16bf37f3ef0739131a2791efd2c149f1c2a2a0eb91074c321df2ed"
)
SPD1656_MANUAL_BYTES: Final = 2_339_387
SPD1656_MANUAL_SHA256: Final = (
    "1f3f5db0600ee6e8133a4c31f9a3f59c1b5bfcc1a916be98ae848ec64581de07"
)

HEADER_BYTES: Final = 7
RECORD_BYTES: Final = 11
RECORDS_PER_CATEGORY: Final = 8
CATEGORY_BYTES: Final = RECORD_BYTES * RECORDS_PER_CATEGORY
LEGACY_CATEGORIES: Final = 6
PROFILE_CATEGORIES: Final = 9
SECONDARY_CATEGORIES: Final = 8
FF_RECORD: Final = b"\xff" * RECORD_BYTES

HEADER_LABELS: Final = (
    "VGHL",
    "VSHL_0",
    "VSH_1",
    "VSL_1",
    "VSHL_1",
    "VCOM",
    "PLL",
)
CATEGORY_LABELS: Final = ("VCOM", "Black", "White", "Yellow", "Red", "Power")
EXPECTED_RECORD_LABELS: Final = tuple(
    f"{category}-GROUP{group}"
    for category in CATEGORY_LABELS
    for group in range(1, RECORDS_PER_CATEGORY + 1)
)

LEGACY_UPLOAD_LOOP_COMMENT: Final = "循环次数根据不同的芯片规格有所不同"
LEGACY_UPLOAD_LOOP_COMMENT_LINE: Final = 1228
LEGACY_UPLOAD_LOOP_COMMENT_UTF8_SHA256: Final = (
    "f5639e6c050dcf2abd019363d768d17e3d13b37cebb0863d6a38163705bca52f"
)
LEGACY_EPD_INITIAL_DEFINITION_LINE: Final = 1138
LEGACY_EPD_INITIAL_END_LINE: Final = 1230
LEGACY_UPLOAD_COMMAND_LINE: Final = 1227
LEGACY_UPLOAD_DATA_LINE: Final = 1229
LEGACY_SEQUENTIAL_UPLOAD_PATTERN: Final = re.compile(
    r"EPD_WriteCMD\s*\(\s*0x20\s*\)\s*;\s*"
    r"for\s*\(\s*i\s*=\s*0\s*;\s*i\s*<\s*535\s*;\s*i\+\+\s*\)\s*"
    r"(?:\{\s*)?EPD_WriteDATA\s*\(\s*wf_data\s*\[\s*i\s*\]\s*\)\s*;"
    r"\s*(?:\})?",
    flags=re.DOTALL,
)


EINK_COMPACT_PATENT_FACTS: Final[dict[str, Any]] = {
    "publication": "TW201321879A",
    "us_family_grant": "US9196200B2",
    "title": "Method of establishing look-up table for electrophoretic display and device thereof",
    "original_assignee": "E Ink Holdings Inc",
    "priority_date": "2011-11-16",
    "html_url": "https://patents.google.com/patent/TW201321879A/en",
    "relevant_description_paragraphs": [
        120,
        121,
        122,
        123,
        142,
        143,
        155,
        156,
        157,
        158,
    ],
    "example": {
        "voltage_bits": 2,
        "duration_unit_count_bits": 4,
        "preferred_segment_count_range": [10, 20],
        "illustrated_segment_count": 12,
        "illustrated_unit_time_ms": 20,
        "illustrated_duration_range_ms": [0, 300],
        "approximate_bytes_per_temperature_interval": 90,
    },
}
EINK_COMPACT_PATENT_FACTS_SHA256: Final = (
    "6236dcca64fc665edebe6b29425a4e0b9c5e975ea1a5c4cb24232835b951f8d2"
)

GOOD_DISPLAY_GROUP_FACTS: Final[dict[str, Any]] = {
    "document": "GDEW0154M09 V2.0 Specification",
    "publisher": "Dalian Good Display Co., Ltd.",
    "url": (
        "https://www.e-paper-display.com/GDEW0154M09%20V2.0%20Specificationb92d.pdf"
        "?fileId=944&flag=all&id=51626c48-6583-407b-b60a-216032d33f35&method=picker&v=2.zip"
    ),
    "pdf_bytes_observed_2026_08_12": 2_772_123,
    "pdf_sha256_observed_2026_08_12": (
        "f127343db2b48a56215d253f7cb871892c882a744d540b9ec86fd75e458f8c88"
    ),
    "relevant_pdf_pages": [22, 35],
    "adjacent_contract": {
        "group_count": 8,
        "group_frame_rate_register": "R25H",
        "per_group_fields": "M[2:0] and N[2:0]",
        "set_lut_states_register": "R26H",
    },
    "same_controller_or_abi_as_spd1657_proven": False,
}
GOOD_DISPLAY_GROUP_FACTS_SHA256: Final = (
    "dcdd6379cf92d1d339a357cc424a32b7ac806393e237cdadf58648a0d1c54df5"
)


class RecordSemanticsAuditError(RuntimeError):
    """Raised when a frozen identity or bounded invariant changes."""


@dataclass(frozen=True)
class Dataset:
    """One record-bearing byte region retained only in memory."""

    dataset_id: str
    body: bytes
    category_count: int
    provenance: dict[str, Any]
    direct_record_labels: tuple[str, ...] = ()

    @property
    def records(self) -> tuple[bytes, ...]:
        return tuple(
            self.body[offset : offset + RECORD_BYTES]
            for offset in range(0, len(self.body), RECORD_BYTES)
        )

    @property
    def categories(self) -> tuple[bytes, ...]:
        return tuple(
            self.body[offset : offset + CATEGORY_BYTES]
            for offset in range(0, len(self.body), CATEGORY_BYTES)
        )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RecordSemanticsAuditError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return _sha256(_canonical_bytes(value))


def _read_pinned(path: Path, *, size: int, digest: str, label: str) -> bytes:
    _require(path.is_file(), f"missing {label}: {path}")
    payload = path.read_bytes()
    _require(len(payload) == size, f"{label} size changed")
    _require(_sha256(payload) == digest, f"{label} identity changed")
    return payload


def _elf32_section_headers(payload: bytes) -> tuple[list[tuple[int, ...]], list[str]]:
    """Parse the bounded ELF32 little-endian section table used by edp_init.o."""

    _require(len(payload) >= 52, "ELF32 header is truncated")
    _require(payload[:4] == b"\x7fELF", "object is not ELF")
    _require(payload[4] == 1, "object is not ELF32")
    _require(payload[5] == 1, "object is not little-endian ELF")
    _require(payload[6] == 1, "ELF identification version changed")
    section_offset = struct.unpack_from("<I", payload, 32)[0]
    section_entry_bytes, section_count, string_section_index = struct.unpack_from(
        "<HHH", payload, 46
    )
    _require(section_count > 0, "extended or empty ELF section count is unsupported")
    _require(section_entry_bytes >= 40, "ELF32 section header is too small")
    _require(string_section_index < section_count, "ELF section-name table is invalid")
    _require(
        section_offset + section_entry_bytes * section_count <= len(payload),
        "ELF section table is out of bounds",
    )
    sections = [
        struct.unpack_from(
            "<IIIIIIIIII", payload, section_offset + index * section_entry_bytes
        )
        for index in range(section_count)
    ]
    name_section = sections[string_section_index]
    name_start, name_bytes = name_section[4], name_section[5]
    _require(
        name_start + name_bytes <= len(payload), "ELF section names are out of bounds"
    )
    name_table = payload[name_start : name_start + name_bytes]

    def read_name(offset: int) -> str:
        _require(offset < len(name_table), "ELF section-name offset is out of bounds")
        end = name_table.find(b"\x00", offset)
        _require(end >= 0, "ELF section name is unterminated")
        return name_table[offset:end].decode("ascii")

    return sections, [read_name(section[0]) for section in sections]


def _bind_elf32_symbol(
    payload: bytes,
    *,
    symbol_name: str,
    expected_section: str,
    expected_size: int,
    expected_payload: bytes,
) -> dict[str, Any]:
    """Bind one ELF32 symbol to its exact section bytes without emitting them."""

    sections, section_names = _elf32_section_headers(payload)
    matches: list[dict[str, Any]] = []
    for symbol_section_index, symbol_section in enumerate(sections):
        if symbol_section[1] != 2:  # SHT_SYMTAB
            continue
        linked_string_index = symbol_section[6]
        _require(
            linked_string_index < len(sections), "ELF symbol string table is invalid"
        )
        string_section = sections[linked_string_index]
        string_start, string_bytes = string_section[4], string_section[5]
        _require(
            string_start + string_bytes <= len(payload),
            "ELF symbol strings are out of bounds",
        )
        string_table = payload[string_start : string_start + string_bytes]
        symbol_start, symbol_bytes = symbol_section[4], symbol_section[5]
        symbol_entry_bytes = symbol_section[9]
        _require(symbol_entry_bytes >= 16, "ELF32 symbol entry is too small")
        _require(
            symbol_start + symbol_bytes <= len(payload)
            and symbol_bytes % symbol_entry_bytes == 0,
            "ELF symbol table is out of bounds or misaligned",
        )
        for symbol_index, offset in enumerate(
            range(symbol_start, symbol_start + symbol_bytes, symbol_entry_bytes)
        ):
            name_offset, value, size, info, other, section_index = struct.unpack_from(
                "<IIIBBH", payload, offset
            )
            _require(
                name_offset < len(string_table), "ELF symbol-name offset is invalid"
            )
            name_end = string_table.find(b"\x00", name_offset)
            _require(name_end >= 0, "ELF symbol name is unterminated")
            name = string_table[name_offset:name_end].decode("ascii")
            if name != symbol_name:
                continue
            _require(section_index < len(sections), f"{symbol_name} section is invalid")
            data_section = sections[section_index]
            section_file_offset, section_bytes = data_section[4], data_section[5]
            _require(
                value + size <= section_bytes
                and section_file_offset + value + size <= len(payload),
                f"{symbol_name} bytes are out of section bounds",
            )
            symbol_payload = payload[
                section_file_offset + value : section_file_offset + value + size
            ]
            matches.append(
                {
                    "symbol_table_section_index": symbol_section_index,
                    "symbol_table_section_name": section_names[symbol_section_index],
                    "symbol_index": symbol_index,
                    "binding": info >> 4,
                    "type": info & 0x0F,
                    "other": other,
                    "section_index": section_index,
                    "section_name": section_names[section_index],
                    "section_relative_value": value,
                    "symbol_bytes": size,
                    "symbol_file_offset": section_file_offset + value,
                    "symbol_payload": symbol_payload,
                }
            )
    _require(len(matches) == 1, f"expected one {symbol_name} ELF symbol")
    match = matches[0]
    _require(match["type"] == 1, f"{symbol_name} is not an ELF object symbol")
    _require(
        match["section_name"] == expected_section, f"{symbol_name} section changed"
    )
    _require(match["symbol_bytes"] == expected_size, f"{symbol_name} size changed")
    _require(match["symbol_payload"] == expected_payload, f"{symbol_name} bytes differ")
    return {key: value for key, value in match.items() if key != "symbol_payload"} | {
        "symbol_payload_sha256": _sha256(match["symbol_payload"]),
        "raw_symbol_payload_emitted": False,
    }


def _load_pinned_user_source_corpus() -> tuple[str, dict[str, Any]]:
    paths = sorted(
        (*LEGACY_USER_ROOT.glob("*.c"), *LEGACY_USER_ROOT.glob("*.h")),
        key=lambda path: path.name.lower(),
    )
    manifest = []
    texts = []
    for path in paths:
        payload = path.read_bytes()
        manifest.append(
            {
                "path": path.name,
                "bytes": len(payload),
                "sha256": _sha256(payload),
            }
        )
        texts.append(payload.decode("latin-1"))
    _require(
        len(paths) == LEGACY_USER_SOURCE_FILE_COUNT,
        "legacy User C/H source file count changed",
    )
    _require(
        sum(row["bytes"] for row in manifest) == LEGACY_USER_SOURCE_BYTES,
        "legacy User C/H source byte count changed",
    )
    _require(
        _canonical_sha256(manifest) == LEGACY_USER_SOURCE_MANIFEST_SHA256,
        "legacy User C/H source manifest changed",
    )
    return "\n".join(texts), {
        "file_count": len(paths),
        "bytes": sum(row["bytes"] for row in manifest),
        "canonical_manifest_sha256": _canonical_sha256(manifest),
        "raw_source_or_manifest_entries_emitted": False,
    }


def _hex_values(line: str) -> bytes:
    values = [
        int(value, 16) for value in re.findall(r"\b0[xX]([0-9A-Fa-f]{1,2})\b", line)
    ]
    _require(all(0 <= value <= 0xFF for value in values), "source byte overflow")
    return bytes(values)


def _inline_label(line: str) -> str:
    return line.rsplit("//", 1)[-1].strip()


def _parse_source_tables() -> dict[str, Any]:
    source = _read_pinned(
        LEGACY_SOURCE,
        size=LEGACY_SOURCE_BYTES,
        digest=LEGACY_SOURCE_SHA256,
        label="legacy EDP_init.c",
    )
    text = source.decode("latin-1")
    lines = text.splitlines()
    source_lines_with_endings = source.splitlines(keepends=True)
    declaration_index = next(
        (
            index
            for index, line in enumerate(lines)
            if re.search(r"\bwf_data\s*\[\s*535\s*\]\s*=", line)
        ),
        None,
    )
    _require(declaration_index is not None, "wf_data[535] declaration disappeared")

    table_parts: dict[str, dict[str, Any]] = {
        "commented": {"header": None, "records": [], "line_numbers": []},
        "active": {"header": None, "records": [], "line_numbers": []},
    }
    for line_number, line in enumerate(
        lines[declaration_index + 1 :], declaration_index + 2
    ):
        if "};" in line:
            break
        values = _hex_values(line)
        if not values:
            continue
        kind = "commented" if line.lstrip().startswith("//") else "active"
        label = _inline_label(line)
        if label == ",".join(HEADER_LABELS):
            _require(len(values) == HEADER_BYTES, f"{kind} header width changed")
            _require(table_parts[kind]["header"] is None, f"duplicate {kind} header")
            table_parts[kind]["header"] = values
            table_parts[kind]["header_line_number"] = line_number
            continue
        match = re.fullmatch(
            r"(VCOM|Black|White|Yellow|Red|Power)-GROUP([1-8])",
            label,
        )
        _require(match is not None, f"unrecognized labeled wf_data line {line_number}")
        _require(
            len(values) == RECORD_BYTES, f"record width changed at line {line_number}"
        )
        table_parts[kind]["records"].append((label, values))
        table_parts[kind]["line_numbers"].append(line_number)

    active, labels, source_contract = geometry._load_legacy()
    _require(tuple(labels) == CATEGORY_LABELS, "legacy category labels changed")
    rendered: dict[str, Any] = {}
    payloads: dict[str, bytes] = {}
    for kind, expected_digest, expected_region_bytes, expected_region_digest in (
        (
            "commented",
            COMMENTED_535_SHA256,
            COMMENTED_SOURCE_REGION_BYTES,
            COMMENTED_SOURCE_REGION_SHA256,
        ),
        (
            "active",
            ACTIVE_535_SHA256,
            ACTIVE_SOURCE_REGION_BYTES,
            ACTIVE_SOURCE_REGION_SHA256,
        ),
    ):
        header = table_parts[kind]["header"]
        _require(isinstance(header, bytes), f"{kind} header missing")
        labeled_records = table_parts[kind]["records"]
        record_labels = tuple(label for label, _ in labeled_records)
        _require(
            record_labels == EXPECTED_RECORD_LABELS, f"{kind} record labels changed"
        )
        payload = header + b"".join(record for _, record in labeled_records)
        _require(len(payload) == 535, f"{kind} table length changed")
        _require(_sha256(payload) == expected_digest, f"{kind} table identity changed")
        region_start_line = table_parts[kind]["header_line_number"]
        region_end_line = table_parts[kind]["line_numbers"][-1]
        source_region = b"".join(
            source_lines_with_endings[region_start_line - 1 : region_end_line]
        )
        _require(
            len(source_region) == expected_region_bytes,
            f"{kind} source-region size changed",
        )
        _require(
            _sha256(source_region) == expected_region_digest,
            f"{kind} source-region identity changed",
        )
        payloads[kind] = payload
        rendered[kind] = {
            "source_form": (
                "commented_out_complete_table_byte_lines"
                if kind == "commented"
                else "active_initializer_byte_lines"
            ),
            "source_region": {
                "definition": (
                    "header through last labeled record inclusive, preserving original "
                    "line endings"
                ),
                "start_line_number": region_start_line,
                "end_line_number": region_end_line,
                "line_count": region_end_line - region_start_line + 1,
                "bytes": len(source_region),
                "sha256": _sha256(source_region),
                "raw_source_text_emitted": False,
            },
            "reconstructed_table": {
                "bytes": len(payload),
                "sha256": _sha256(payload),
                "raw_bytes_emitted": False,
            },
            "header_bytes": HEADER_BYTES,
            "header_labels": list(HEADER_LABELS),
            "header_label_is_inline_on_same_source_line": True,
            "header_line_number": table_parts[kind]["header_line_number"],
            "record_bytes": RECORD_BYTES,
            "record_count": len(labeled_records),
            "category_count": LEGACY_CATEGORIES,
            "records_per_category": RECORDS_PER_CATEGORY,
            "category_labels": list(CATEGORY_LABELS),
            "record_label_pattern": "<category>-GROUP<1..8>",
            "all_48_record_boundaries_directly_labeled_inline": True,
            "first_labeled_line_number": table_parts[kind]["line_numbers"][0],
            "last_labeled_line_number": table_parts[kind]["line_numbers"][-1],
            "raw_header_record_or_payload_bytes_emitted": False,
        }

    _require(
        payloads["active"] == active, "parsed active table differs from initializer"
    )
    return {
        "source": {
            **source_contract,
            "source_bytes": len(source),
            "source_sha256": _sha256(source),
            "declaration_line_number": declaration_index + 1,
        },
        "tables": rendered,
        "payloads": payloads,
        "direct_semantic_gain": {
            "eleven_byte_boundaries_are_only_arithmetic": False,
            "every_legacy_record_is_directly_named_as_a_GROUP_slot": True,
            "group_slot_is_a_chronological_phase_proven_by_local_source": False,
            "any_of_the_eleven_bytes_is_named_by_local_source": False,
        },
    }


def _compiled_status(active: bytes, commented: bytes) -> dict[str, Any]:
    object_payload = _read_pinned(
        LEGACY_OBJECT,
        size=LEGACY_OBJECT_BYTES,
        digest=LEGACY_OBJECT_SHA256,
        label="legacy edp_init.o",
    )
    map_payload = _read_pinned(
        LEGACY_MAP,
        size=LEGACY_MAP_BYTES,
        digest=LEGACY_MAP_SHA256,
        label="legacy link map",
    )
    map_text = map_payload.decode("latin-1")
    symbol_binding = _bind_elf32_symbol(
        object_payload,
        symbol_name="wf_data",
        expected_section=".data",
        expected_size=len(active),
        expected_payload=active,
    )
    symbol_rows = re.findall(
        r"^\s*wf_data\s+0x[0-9A-Fa-f]+\s+Data\s+535\s+edp_init\.o\(\.data\)\s*$",
        map_text,
        flags=re.MULTILINE,
    )
    return {
        "object": {
            "path": LEGACY_OBJECT.relative_to(REPO_ROOT).as_posix(),
            "bytes": len(object_payload),
            "sha256": _sha256(object_payload),
            "active_full_table_occurrence_count": object_payload.count(active),
            "commented_full_table_occurrence_count": object_payload.count(commented),
            "wf_data_elf32_symbol_binding": symbol_binding,
        },
        "link_map": {
            "path": LEGACY_MAP.relative_to(REPO_ROOT).as_posix(),
            "bytes": len(map_payload),
            "sha256": _sha256(map_payload),
            "wf_data_535_edp_init_data_symbol_row_count": len(symbol_rows),
        },
        "active_table_bound_to_wf_data_symbol_in_edp_init_object": True,
        "commented_exact_full_table_present_in_edp_init_object": (
            object_payload.count(commented) > 0
        ),
        "active_wf_data_535_linked_by_delivered_map": len(symbol_rows) == 1,
        "active_wf_data_symbol_content_compiled_and_linked_by_delivered_map": (
            len(symbol_rows) == 1
        ),
        "commented_source_lines_active_in_this_translation_unit": False,
        "commented_table_role_proven": False,
        "commented_table_runtime_authorized": False,
        "commented_table_safe_operational_status": (
            "inactive_source_bytes_role_unknown_unvalidated_comparison_only"
        ),
    }


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//[^\r\n]*", "", text)


def _source_upload_loop_comment(source_payload: bytes) -> dict[str, Any]:
    """Bind the delivered GBK comment to the exact ``EPD_initial`` upload."""

    try:
        text = source_payload.decode("gb18030")
    except UnicodeDecodeError as error:
        raise RecordSemanticsAuditError(
            "legacy EDP_init.c no longer decodes as GB18030"
        ) from error
    lines = text.splitlines()
    matches = [
        (line_number, line)
        for line_number, line in enumerate(lines, start=1)
        if LEGACY_UPLOAD_LOOP_COMMENT in line
    ]
    _require(len(matches) == 1, "chip-specific loop-count comment changed")
    line_number, line = matches[0]
    _require(
        line_number == LEGACY_UPLOAD_LOOP_COMMENT_LINE,
        "chip-specific loop-count comment line changed",
    )
    code, separator, comment = line.partition("//")
    normalized_comment = comment.strip()
    _require(separator == "//", "chip-specific loop-count comment marker changed")
    _require(
        normalized_comment == LEGACY_UPLOAD_LOOP_COMMENT,
        "chip-specific loop-count comment text changed",
    )
    _require(
        _sha256(normalized_comment.encode("utf-8"))
        == LEGACY_UPLOAD_LOOP_COMMENT_UTF8_SHA256,
        "chip-specific loop-count comment UTF-8 identity changed",
    )
    _require(
        len(lines) >= LEGACY_EPD_INITIAL_END_LINE,
        "legacy EPD_init.c is truncated before EPD_initial closes",
    )
    _require(
        re.fullmatch(
            r"\s*void\s+EPD_initial\s*\(\s*void\s*\)\s*",
            lines[LEGACY_EPD_INITIAL_DEFINITION_LINE - 1],
        )
        is not None,
        "EPD_initial definition line changed",
    )
    _require(
        lines[LEGACY_EPD_INITIAL_END_LINE - 1].strip() == "}",
        "EPD_initial closing line changed",
    )
    _require(
        LEGACY_EPD_INITIAL_DEFINITION_LINE
        < LEGACY_UPLOAD_COMMAND_LINE
        < line_number
        < LEGACY_UPLOAD_DATA_LINE
        < LEGACY_EPD_INITIAL_END_LINE,
        "chip-specific loop comment is outside the pinned EPD_initial function",
    )
    _require(
        LEGACY_UPLOAD_COMMAND_LINE == line_number - 1
        and re.fullmatch(
            r"\s*EPD_WriteCMD\s*\(\s*0x20\s*\)\s*;\s*",
            _strip_comments(lines[LEGACY_UPLOAD_COMMAND_LINE - 1]),
        )
        is not None,
        "commented loop is not immediately preceded by command 0x20",
    )
    _require(
        LEGACY_UPLOAD_DATA_LINE == line_number + 1
        and re.fullmatch(
            r"\s*EPD_WriteDATA\s*\(\s*wf_data\s*\[\s*i\s*\]\s*\)\s*;\s*",
            _strip_comments(lines[LEGACY_UPLOAD_DATA_LINE - 1]),
        )
        is not None,
        "commented loop is not immediately followed by wf_data[i] write",
    )
    _require(
        re.fullmatch(
            r"\s*for\s*\(\s*i\s*=\s*0\s*;\s*i\s*<\s*535\s*;\s*i\+\+\s*\)\s*",
            code,
        )
        is not None,
        "comment is no longer attached to the exact 535-byte loop header",
    )
    return {
        "source_encoding": "GB18030-compatible delivered source",
        "line_number": line_number,
        "normalized_comment": normalized_comment,
        "normalized_comment_utf8_sha256": _sha256(normalized_comment.encode("utf-8")),
        "attached_loop_initial_value": 0,
        "attached_loop_comparison": "i < 535",
        "attached_loop_increment": "i++",
        "attached_loop_iteration_count": 535,
        "direct_source_author_assertion": (
            "loop count varies according to different chip specifications"
        ),
        "establishes_535_is_not_asserted_as_universal_across_all_chips": True,
        "establishes_mode1_uses_799_or_800_bytes": False,
        "establishes_target_chip_or_controller_revision": False,
        "establishes_dual_controller_destination": False,
    }


def _source_execution_binding() -> dict[str, Any]:
    source_payload = LEGACY_SOURCE.read_bytes()
    source = source_payload.decode("latin-1")
    clean = _strip_comments(source)
    corpus, corpus_identity = _load_pinned_user_source_corpus()
    clean_corpus = _strip_comments(corpus)
    init_global = geometry.reverse_delta._extract_function(clean, "init_global_pata")
    epd_initial = geometry.reverse_delta._extract_function(clean, "EPD_initial")

    uart_data_deal_payload = _read_pinned(
        LEGACY_UART_DATA_DEAL_SOURCE,
        size=LEGACY_UART_DATA_DEAL_SOURCE_BYTES,
        digest=LEGACY_UART_DATA_DEAL_SOURCE_SHA256,
        label="legacy UartDataDeal.c",
    )
    usart_payload = _read_pinned(
        LEGACY_USART_SOURCE,
        size=LEGACY_USART_SOURCE_BYTES,
        digest=LEGACY_USART_SOURCE_SHA256,
        label="legacy usart.c",
    )
    uart_data_deal_text = _strip_comments(uart_data_deal_payload.decode("latin-1"))
    usart_text = _strip_comments(usart_payload.decode("latin-1"))
    uart_save = geometry.reverse_delta._extract_function(
        uart_data_deal_text, "Uart_save_wf_data"
    )
    usart_analyse = geometry.reverse_delta._extract_function(
        usart_text, "USART1_receiveDataNnalyse"
    )
    _require(
        len(
            re.findall(
                r"\bUart_save_wf_data\s*\(\s*uint8_t\s*\*\s*dat_buff\s*,\s*"
                r"uint16_t\s+buff_len\s*\)",
                uart_data_deal_text,
            )
        )
        == 1,
        "legacy UART waveform helper signature changed",
    )
    _require(
        re.search(r"#\s*define\s+WF_DATA_LENGTH\s+535\b", clean_corpus) is not None,
        "legacy WF_DATA_LENGTH definition changed",
    )
    uart_fixed_replacement = (
        re.search(
            r"memset\s*\(\s*wf_data\s*,\s*0\s*,\s*sizeof\s*\(\s*wf_data\s*\)\s*\)\s*;\s*"
            r"memcpy\s*\(\s*wf_data\s*,\s*dat_buff\s*,\s*WF_DATA_LENGTH\s*\)\s*;",
            uart_save,
            flags=re.DOTALL,
        )
        is not None
    )
    _require(uart_fixed_replacement, "legacy UART wf_data replacement changed")
    uart_buff_len_consumed = re.search(r"\bbuff_len\b", uart_save) is not None
    _require(not uart_buff_len_consumed, "legacy UART helper began consuming buff_len")
    uart_case5_calls_save = (
        re.search(
            r"case\s+5\s*:\s*"
            r"Uart_save_wf_data\s*\(\s*&\s*USART1_RData\s*\[\s*6\s*\]\s*,\s*"
            r"number_sum\s*-\s*9\s*\)\s*;",
            usart_analyse,
            flags=re.DOTALL,
        )
        is not None
    )
    _require(uart_case5_calls_save, "legacy UART case-5 waveform call changed")
    map_payload = _read_pinned(
        LEGACY_MAP,
        size=LEGACY_MAP_BYTES,
        digest=LEGACY_MAP_SHA256,
        label="legacy link map",
    )
    map_text = map_payload.decode("latin-1")
    linked_reference_patterns = {
        "startup_vector_to_USART1_IRQHandler": (
            r"startup_stm32f103xe\.o\(RESET\) refers to "
            r"usart\.o\(i\.USART1_IRQHandler\) for USART1_IRQHandler"
        ),
        "USART1_IRQHandler_to_receive_analyse": (
            r"usart\.o\(i\.USART1_IRQHandler\) refers to "
            r"usart\.o\(i\.USART1_receiveDataNnalyse\) for USART1_receiveDataNnalyse"
        ),
        "receive_analyse_to_Uart_save_wf_data": (
            r"usart\.o\(i\.USART1_receiveDataNnalyse\) refers to "
            r"uartdatadeal\.o\(i\.Uart_save_wf_data\) for Uart_save_wf_data"
        ),
        "Uart_save_wf_data_to_wf_data": (
            r"uartdatadeal\.o\(i\.Uart_save_wf_data\) refers to "
            r"edp_init\.o\(\.data\) for wf_data"
        ),
    }
    linked_reference_counts = {
        key: len(re.findall(pattern, map_text))
        for key, pattern in linked_reference_patterns.items()
    }
    _require(
        all(count == 1 for count in linked_reference_counts.values()),
        "legacy linked UART-to-wf_data reference chain changed",
    )

    assignments = {
        index: re.search(
            rf"EPD_setting\.(V{index}|VCOM|Frame)\s*=\s*wf_data\s*\[\s*{index}\s*\]",
            init_global,
        )
        is not None
        for index in range(1, HEADER_BYTES)
    }
    _require(all(assignments.values()), "header scalar assignments changed")
    _require(
        re.search(r"\bwf_data\s*\[\s*0\s*\]", clean_corpus) is None,
        "wf_data[0] acquired a scalar read",
    )
    pwr_uses_v1_v4 = (
        re.search(
            r"EPD_WriteCMD\s*\(\s*0x01\s*\)\s*;\s*"
            r"EPD_WriteDATA\s*\(\s*0x07\s*\)\s*;\s*"
            r"EPD_WriteDATA\s*\(\s*0x00\s*\)\s*;\s*"
            r"EPD_WriteDATA\s*\(\s*EPD_setting\.V1\s*\)\s*;\s*"
            r"EPD_WriteDATA\s*\(\s*EPD_setting\.V2\s*\)\s*;\s*"
            r"EPD_WriteDATA\s*\(\s*EPD_setting\.V3\s*\)\s*;\s*"
            r"EPD_WriteDATA\s*\(\s*EPD_setting\.V4\s*\)\s*;",
            epd_initial,
            flags=re.DOTALL,
        )
        is not None
    )
    _require(pwr_uses_v1_v4, "legacy ordered PWR scalar binding changed")
    dedicated_vcom_uses_separate_global = (
        re.search(
            r"EPD_WriteCMD\s*\(\s*0x82\s*\)\s*;\s*"
            r"EPD_WriteDATA\s*\(\s*vcom\s*\|\s*0x80\s*\)\s*;",
            epd_initial,
            flags=re.DOTALL,
        )
        is not None
    )
    dedicated_pll_is_literal = (
        re.search(
            r"EPD_WriteCMD\s*\(\s*0x30\s*\)\s*;\s*"
            r"EPD_WriteDATA\s*\(\s*0x08\s*\)\s*;",
            epd_initial,
            flags=re.DOTALL,
        )
        is not None
    )
    sequential_upload = LEGACY_SEQUENTIAL_UPLOAD_PATTERN.search(epd_initial)
    opaque_upload = sequential_upload is not None
    _require(dedicated_vcom_uses_separate_global, "legacy VCOM binding changed")
    _require(dedicated_pll_is_literal, "legacy PLL binding changed")
    _require(opaque_upload, "legacy sequential 535-byte upload changed")

    non_assignment_source = re.sub(
        r"EPD_setting\.(?:VCOM|Frame)\s*=\s*wf_data\s*\[\s*[56]\s*\]\s*;",
        "",
        clean_corpus,
    )
    vcom_assignment_count = len(
        re.findall(
            r"EPD_setting\.VCOM\s*=\s*wf_data\s*\[\s*5\s*\]",
            clean_corpus,
        )
    )
    frame_assignment_count = len(
        re.findall(
            r"EPD_setting\.Frame\s*=\s*wf_data\s*\[\s*6\s*\]",
            clean_corpus,
        )
    )
    _require(vcom_assignment_count == 2, "byte 5 assignment count changed")
    _require(frame_assignment_count == 2, "byte 6 assignment count changed")
    _require(
        "EPD_setting.VCOM" not in non_assignment_source,
        "EPD_setting.VCOM acquired a non-assignment use",
    )
    _require(
        "EPD_setting.Frame" not in non_assignment_source,
        "EPD_setting.Frame acquired a non-assignment use",
    )
    header_coordinates = []
    for index, label in enumerate(HEADER_LABELS):
        scalar_assignment = (
            f"EPD_setting.V{index}"
            if 1 <= index <= 4
            else "EPD_setting.VCOM"
            if index == 5
            else "EPD_setting.Frame"
            if index == 6
            else None
        )
        scalar_assignment_consumed = 1 <= index <= 4
        header_coordinates.append(
            {
                "index": index,
                "comment_label": label,
                "comment_label_evidence": "direct_inline_label_on_both_source_tables",
                "member_of_compiled_and_linked_active_wf_data_535": True,
                "direct_scalar_read_in_delivered_c_sources": (
                    bool(
                        re.search(
                            rf"\bwf_data\s*\[\s*{index}\s*\]",
                            clean_corpus,
                        )
                    )
                ),
                "scalar_assignment_target": scalar_assignment,
                "scalar_assignment_consumed_by_later_dedicated_command": (
                    scalar_assignment_consumed
                ),
                "forwarded_opaquely_as_member_of_command_0x20_payload": True,
                "dedicated_command_binding": (
                    "PWR_0x01_via_EPD_setting_V1_to_V4"
                    if 1 <= index <= 4
                    else "none_proven"
                ),
            }
        )

    loop_comment = _source_upload_loop_comment(source_payload)

    return {
        "evidence_scope": (
            "static identity-pinned delivered User C/H source dataflow; no hardware "
            "runtime observation"
        ),
        "source_corpus": corpus_identity,
        "mutable_wf_data_runtime_replacement": {
            "UartDataDeal_source": {
                "path": LEGACY_UART_DATA_DEAL_SOURCE.relative_to(REPO_ROOT).as_posix(),
                "bytes": len(uart_data_deal_payload),
                "sha256": _sha256(uart_data_deal_payload),
            },
            "usart_source": {
                "path": LEGACY_USART_SOURCE.relative_to(REPO_ROOT).as_posix(),
                "bytes": len(usart_payload),
                "sha256": _sha256(usart_payload),
            },
            "case_5_calls_Uart_save_wf_data_from_USART1_RData_plus_6": (
                uart_case5_calls_save
            ),
            "Uart_save_wf_data_clears_whole_global_then_copies_WF_DATA_LENGTH": (
                uart_fixed_replacement
            ),
            "WF_DATA_LENGTH": 535,
            "declared_buff_len_parameter_consumed_in_function_body": (
                uart_buff_len_consumed
            ),
            "link_map_reference_chain_counts": linked_reference_counts,
            "linked_interrupt_to_mutable_wf_data_path_exists": True,
            "path_requires_a_matching_runtime_UART_case_5_request": True,
            "path_itself_calls_EPD_initial_or_command_0x20": False,
            "compiled_initializer_contents_remain_unmodified_at_each_0x20_upload_proven": False,
            "runtime_bytes_at_each_upload_are_the_compiled_initializer_proven": False,
        },
        "header_coordinates": header_coordinates,
        "bytes_1_through_4_have_direct_PWR_execution_binding": pwr_uses_v1_v4,
        "byte_0_VGHL_has_direct_scalar_execution_binding": False,
        "byte_5_comment_label": "VCOM",
        "byte_5_assigned_to_struct_field": "EPD_setting.VCOM",
        "byte_5_assignment_count_in_source_corpus": vcom_assignment_count,
        "byte_5_struct_field_has_named_non_assignment_use_in_source_corpus": (
            "EPD_setting.VCOM" in non_assignment_source
        ),
        "dedicated_VCOM_command_0x82_uses_separate_global_vcom": (
            dedicated_vcom_uses_separate_global
        ),
        "byte_5_has_dedicated_VCOM_execution_binding": False,
        "byte_6_comment_label": "PLL",
        "byte_6_assigned_to_struct_field": "EPD_setting.Frame",
        "byte_6_assignment_count_in_source_corpus": frame_assignment_count,
        "byte_6_comment_and_struct_field_names_agree": False,
        "byte_6_struct_field_has_named_non_assignment_use_in_source_corpus": (
            "EPD_setting.Frame" in non_assignment_source
        ),
        "dedicated_PLL_command_0x30_uses_literal_not_byte_6": dedicated_pll_is_literal,
        "byte_6_has_dedicated_PLL_execution_binding": False,
        "all_535_bytes_forwarded_in_order_to_command_0x20": opaque_upload,
        "command_0x20_immediately_followed_by_exact_i0_to_i534_wf_data_loop": (
            opaque_upload
        ),
        "upload_loop_source_comment": loop_comment,
        "EPD_initial_explicitly_complements_or_decodes_records_before_0x20": False,
        "all_pre_call_mutations_of_wf_data_excluded": False,
        "source_labels_alone_define_numeric_units_or_safe_ranges": False,
    }


def _evidence_ladder(
    compiled: dict[str, Any], execution: dict[str, Any]
) -> dict[str, Any]:
    return {
        "level_1_comment_labels": {
            "evidence": (
                "both complete source tables carry the same header legend and all "
                "48 category-GROUP labels"
            ),
            "establishes": "source author naming and exact coordinate boundaries",
            "does_not_establish": (
                "which commented bytes were compiled or any internal 11-byte field role"
            ),
        },
        "level_2_compiled_and_linked_active_bytes": {
            "active_bytes_bound_to_wf_data_elf_symbol": compiled[
                "active_table_bound_to_wf_data_symbol_in_edp_init_object"
            ],
            "commented_exact_full_table_absent_from_edp_init_object": not compiled[
                "commented_exact_full_table_present_in_edp_init_object"
            ],
            "wf_data_535_symbol_present_in_link_map": compiled[
                "active_wf_data_535_linked_by_delivered_map"
            ],
            "establishes": "the active initializer is a linked 535-byte data object",
            "does_not_establish": (
                "that its initializer contents remain unmodified at an upload or that a "
                "hardware execution path ran"
            ),
        },
        "level_3_delivered_c_consumption": {
            "all_535_bytes_forwarded_in_order_to_command_0x20": execution[
                "all_535_bytes_forwarded_in_order_to_command_0x20"
            ],
            "header_bytes_1_through_4_also_bind_to_PWR_0x01": execution[
                "bytes_1_through_4_have_direct_PWR_execution_binding"
            ],
            "header_byte_0_has_only_opaque_0x20_forwarding": True,
            "header_byte_5_has_only_opaque_0x20_forwarding_after_no_named_field_use": (
                not execution[
                    "byte_5_struct_field_has_named_non_assignment_use_in_source_corpus"
                ]
            ),
            "header_byte_6_has_only_opaque_0x20_forwarding_after_no_named_field_use": (
                not execution[
                    "byte_6_struct_field_has_named_non_assignment_use_in_source_corpus"
                ]
            ),
            "linked_UART_path_can_replace_mutable_wf_data": execution[
                "mutable_wf_data_runtime_replacement"
            ]["linked_interrupt_to_mutable_wf_data_path_exists"],
            "compiled_initializer_is_the_runtime_upload_content_proven": False,
            "hardware_runtime_observed": False,
            "establishes": (
                "static delivered-source forwarding of the global's then-current 535 "
                "bytes only"
            ),
            "does_not_establish": (
                "initializer-content preservation, controller-side decode, electrical "
                "units, polarity, duration, or phase"
            ),
        },
    }


def _split_records(body: bytes) -> tuple[bytes, ...]:
    _require(len(body) % RECORD_BYTES == 0, "record body is not 11-byte aligned")
    return tuple(
        body[offset : offset + RECORD_BYTES]
        for offset in range(0, len(body), RECORD_BYTES)
    )


def _selector_counts(records: Iterable[bytes], *, complemented: bool) -> dict[str, int]:
    counts: Counter[int] = Counter()
    for record in records:
        for original in record[:8]:
            value = original ^ (0xFF if complemented else 0)
            counts.update(
                ((value >> 6) & 3, (value >> 4) & 3, (value >> 2) & 3, value & 3)
            )
    return {str(code): counts[code] for code in range(4)}


def _hamming_histogram(weights: Iterable[int]) -> dict[str, int]:
    counts = Counter(weights)
    return {str(weight): counts[weight] for weight in sorted(counts)}


def _dataset_semantics(dataset: Dataset) -> dict[str, Any]:
    _require(
        len(dataset.body) == dataset.category_count * CATEGORY_BYTES,
        f"{dataset.dataset_id} category geometry changed",
    )
    records = dataset.records
    active = tuple(record for record in records if record != FF_RECORD)
    _require(active, f"{dataset.dataset_id} has no active records")
    raw_weights = [sum(value.bit_count() for value in record) for record in active]
    complemented_weights = [RECORD_BYTES * 8 - weight for weight in raw_weights]
    raw_selector = _selector_counts(active, complemented=False)
    complement_selector = _selector_counts(active, complemented=True)
    raw_timing = [record[8:] for record in active]
    complement_timing = [bytes(value ^ 0xFF for value in row) for row in raw_timing]
    categories = dataset.categories
    trailing_ff_counts = []
    for category in categories:
        category_records = _split_records(category)
        count = 0
        for record in reversed(category_records):
            if record != FF_RECORD:
                break
            count += 1
        trailing_ff_counts.append(count)
        _require(
            all(
                record == FF_RECORD
                for record in category_records[len(category_records) - count :]
            )
            if count
            else True,
            "trailing FF accounting changed",
        )

    return {
        "dataset_id": dataset.dataset_id,
        "geometry": {
            "body_bytes": len(dataset.body),
            "body_sha256": _sha256(dataset.body),
            "category_count": dataset.category_count,
            "category_bytes": CATEGORY_BYTES,
            "records_per_category": RECORDS_PER_CATEGORY,
            "record_bytes": RECORD_BYTES,
            "record_count": len(records),
            "non_all_ff_record_count": len(active),
            "all_ff_record_count": len(records) - len(active),
            "trailing_all_ff_record_count_by_category": trailing_ff_counts,
            "direct_record_label_count": len(dataset.direct_record_labels),
        },
        "active_low_sparsity_screen": {
            "raw_one_bit_weight": {
                "minimum": min(raw_weights),
                "maximum": max(raw_weights),
                "mean": round(sum(raw_weights) / len(raw_weights), 6),
                "histogram": _hamming_histogram(raw_weights),
            },
            "bitwise_complement_one_bit_weight": {
                "minimum": min(complemented_weights),
                "maximum": max(complemented_weights),
                "mean": round(sum(complemented_weights) / len(complemented_weights), 6),
                "histogram": _hamming_histogram(complemented_weights),
                "records_at_most_24_one_bits": sum(
                    weight <= 24 for weight in complemented_weights
                ),
            },
            "all_active_records_have_at_most_24_set_bits_after_complement": all(
                weight <= 24 for weight in complemented_weights
            ),
            "all_ff_record_becomes_all_zero_under_complement": True,
            "controller_internal_complement_or_active_low_encoding_proven": False,
            "reason": (
                "complement sparsity is exact statistical structure, but the delivered "
                "legacy writer forwards original bytes and no controller decoder is available"
            ),
        },
        "philips_11byte_projection": {
            "raw_first_eight_bytes_two_bit_code_counts": raw_selector,
            "complemented_first_eight_bytes_two_bit_code_counts": complement_selector,
            "raw_literal_three_level_example_has_no_unassigned_code_3": (
                raw_selector["3"] == 0
            ),
            "complement_literal_three_level_example_has_no_unassigned_code_3": (
                complement_selector["3"] == 0
            ),
            "raw_non_all_ff_records_with_all_three_suffix_bytes_at_most_15": sum(
                all(value <= 15 for value in row) for row in raw_timing
            ),
            "complement_non_all_ff_records_with_all_three_suffix_bytes_at_most_15": sum(
                all(value <= 15 for value in row) for row in complement_timing
            ),
            "raw_all_ff_padding_retains_patent_optional_FF_FF_boundary": (
                len(records) > len(active)
            ),
            "complement_all_ff_padding_retains_patent_optional_FF_FF_boundary": False,
            "one_transform_satisfies_literal_three_level_example_and_FF_FF_boundary": False,
            "bytes_0_through_7_are_voltage_selectors_proven": False,
            "bytes_8_through_10_are_timing_fields_proven": False,
        },
        "provenance": dataset.provenance,
        "raw_header_record_plaintext_or_payload_bytes_emitted": False,
    }


def _load_datasets(
    source_tables: dict[str, Any],
) -> tuple[dict[str, Dataset], dict[str, Any]]:
    recovered, profiles, legacy, data0, data1, iar_provenance = (
        arithmetic._load_evidence(arithmetic.iar_graph.DEFAULT_IAR_ROOT)
    )
    active = source_tables["payloads"]["active"]
    commented = source_tables["payloads"]["commented"]
    _require(active == legacy, "legacy loader and source parser disagree")
    _require(len(data0) == 1_503 and len(data1) == 704, "IAR array sizes changed")
    _require(data0[799:] == b"\xff" * 704, "DATA0 trailing FF704 changed")

    datasets = {
        "legacy_commented_535": Dataset(
            dataset_id="legacy_commented_535",
            body=commented[HEADER_BYTES:],
            category_count=LEGACY_CATEGORIES,
            direct_record_labels=EXPECTED_RECORD_LABELS,
            provenance={
                "source_path": LEGACY_SOURCE.relative_to(REPO_ROOT).as_posix(),
                "outer_bytes": len(commented),
                "outer_sha256": _sha256(commented),
                "source_form": "commented_out_complete_table_byte_lines",
                "source_lines_active_in_this_translation_unit": False,
                "exact_full_table_present_in_current_edp_init_object": False,
                "role": "unknown",
                "runtime_authorized": False,
            },
        ),
        "legacy_active_535": Dataset(
            dataset_id="legacy_active_535",
            body=active[HEADER_BYTES:],
            category_count=LEGACY_CATEGORIES,
            direct_record_labels=EXPECTED_RECORD_LABELS,
            provenance={
                "source_path": LEGACY_SOURCE.relative_to(REPO_ROOT).as_posix(),
                "outer_bytes": len(active),
                "outer_sha256": _sha256(active),
                "source_form": "compiled_wf_data_initializer",
                "compiled_and_linked": True,
                "mutable_global_with_linked_UART_replacement_path": True,
                "initializer_contents_are_runtime_upload_bytes_at_every_call_proven": (
                    False
                ),
            },
        ),
        "iar_DATA0_first799": Dataset(
            dataset_id="iar_DATA0_first799",
            body=data0[HEADER_BYTES:799],
            category_count=PROFILE_CATEGORIES,
            provenance={
                "provider": "byte-identical E2801.r43 and E2802.r43 DATA0",
                "whole_DATA0_bytes": len(data0),
                "whole_DATA0_sha256": _sha256(data0),
                "first799_sha256": _sha256(data0[:799]),
                "internal_799_boundary_declared_by_symbol_or_subobject": False,
            },
        ),
        "iar_DATA1_704": Dataset(
            dataset_id="iar_DATA1_704",
            body=data1,
            category_count=SECONDARY_CATEGORIES,
            provenance={
                "provider": "byte-identical E2801.r43 and E2802.r43 DATA1",
                "outer_bytes": len(data1),
                "outer_sha256": _sha256(data1),
                "declared_relation_to_DATA0_rows": False,
            },
        ),
    }
    for profile_id in ("WF20_25", "WF23_25"):
        payload = profiles[profile_id]
        _require(len(payload) == 800, f"{profile_id} decoded length changed")
        datasets[profile_id] = Dataset(
            dataset_id=profile_id,
            body=payload[HEADER_BYTES:799],
            category_count=PROFILE_CATEGORIES,
            provenance={
                "source_path": profile_pack.PROFILES[
                    profile_id
                ].source_relative.as_posix(),
                "outer_bytes": len(payload),
                "outer_sha256": _sha256(payload),
                "identity_checked_by_vendor_profile_pack": True,
            },
        )
    return datasets, iar_provenance


def _shadow_active_comparison(commented: bytes, active: bytes) -> dict[str, Any]:
    _require(len(commented) == len(active) == 535, "legacy table lengths changed")
    commented_records = _split_records(commented[HEADER_BYTES:])
    active_records = _split_records(active[HEADER_BYTES:])
    shared_active = (set(commented_records) - {FF_RECORD}) & (
        set(active_records) - {FF_RECORD}
    )
    rows = []
    for category_index, category_label in enumerate(CATEGORY_LABELS):
        left = commented[
            HEADER_BYTES + category_index * CATEGORY_BYTES : HEADER_BYTES
            + (category_index + 1) * CATEGORY_BYTES
        ]
        right = active[
            HEADER_BYTES + category_index * CATEGORY_BYTES : HEADER_BYTES
            + (category_index + 1) * CATEGORY_BYTES
        ]
        left_records = _split_records(left)
        right_records = _split_records(right)
        rows.append(
            {
                "category_index": category_index,
                "direct_source_label": category_label,
                "equal_byte_positions": sum(a == b for a, b in zip(left, right)),
                "different_byte_positions": sum(a != b for a, b in zip(left, right)),
                "bit_hamming_distance": sum(
                    (a ^ b).bit_count() for a, b in zip(left, right)
                ),
                "same_coordinate_exact_record_indices": [
                    index
                    for index, pair in enumerate(zip(left_records, right_records))
                    if pair[0] == pair[1]
                ],
            }
        )
    return {
        "same_source_same_direct_label_geometry": True,
        "bytes": len(active),
        "equal_byte_positions": sum(a == b for a, b in zip(commented, active)),
        "different_byte_positions": sum(a != b for a, b in zip(commented, active)),
        "equal_header_position_indices": [
            index
            for index, pair in enumerate(
                zip(commented[:HEADER_BYTES], active[:HEADER_BYTES])
            )
            if pair[0] == pair[1]
        ],
        "different_header_position_indices": [
            index
            for index, pair in enumerate(
                zip(commented[:HEADER_BYTES], active[:HEADER_BYTES])
            )
            if pair[0] != pair[1]
        ],
        "shared_unique_non_all_ff_record_count": len(shared_active),
        "same_coordinate_exact_record_count": sum(
            left == right for left, right in zip(commented_records, active_records)
        ),
        "categories": rows,
        "one_is_a_simple_duplicate_of_the_other": commented == active,
        "content_relation_class": (
            "same_direct_labels_but_distinct_contents_no_shared_active_record"
        ),
        "difference_assigns_duration_voltage_or_phase_fields": False,
        "commented_table_role_proven": False,
        "commented_table_is_an_authorized_runtime_candidate": False,
        "raw_values_emitted": False,
    }


def _cross_dataset_exact_records(datasets: dict[str, Dataset]) -> list[dict[str, Any]]:
    commented = datasets["legacy_commented_535"]
    left_active = set(commented.records) - {FF_RECORD}
    result = []
    for dataset_id, dataset in datasets.items():
        if dataset_id == commented.dataset_id:
            continue
        shared = left_active & (set(dataset.records) - {FF_RECORD})
        result.append(
            {
                "left": commented.dataset_id,
                "right": dataset_id,
                "shared_unique_non_all_ff_record_count": len(shared),
                "raw_records_emitted": False,
                "exact_match_would_assign_semantics": False,
            }
        )
    return result


def _public_format_hypotheses() -> dict[str, Any]:
    _require(
        _canonical_sha256(EINK_COMPACT_PATENT_FACTS)
        == EINK_COMPACT_PATENT_FACTS_SHA256,
        "E Ink compact patent facts changed",
    )
    _require(
        _canonical_sha256(GOOD_DISPLAY_GROUP_FACTS) == GOOD_DISPLAY_GROUP_FACTS_SHA256,
        "Good Display group facts changed",
    )
    _require(
        patent11._canonical_json_sha256(patent11.PRIMARY_PATENT_FACTS)
        == patent11.PRIMARY_PATENT_FACTS_SHA256,
        "Philips 11-byte patent facts changed",
    )
    manual = _read_pinned(
        SPD1656_MANUAL,
        size=SPD1656_MANUAL_BYTES,
        digest=SPD1656_MANUAL_SHA256,
        label="SPD1656 manual",
    )
    return {
        "philips_apollo_11byte": {
            "source": {
                **patent11.PRIMARY_PATENT_FACTS,
                "facts_canonical_sha256": patent11.PRIMARY_PATENT_FACTS_SHA256,
            },
            "exact_width_match": True,
            "local_format_or_controller_identity_match_proven": False,
            "literal_raw_or_complement_projection_decodes_all_local_records": False,
        },
        "eink_compact_segment_example": {
            "source": {
                **EINK_COMPACT_PATENT_FACTS,
                "facts_canonical_sha256": EINK_COMPACT_PATENT_FACTS_SHA256,
            },
            "local_category_bytes": CATEGORY_BYTES,
            "patent_approximate_bytes_per_temperature_interval": 90,
            "numerical_nearness_is_exact_format_identity": False,
            "patent_defines_an_11byte_group_record": False,
            "local_two_bit_voltage_or_four_bit_duration_field_assigned": False,
        },
        "good_display_adjacent_eight_group_contract": {
            "source": {
                **GOOD_DISPLAY_GROUP_FACTS,
                "facts_canonical_sha256": GOOD_DISPLAY_GROUP_FACTS_SHA256,
                "pdf_loaded_or_network_accessed_by_this_offline_tool": False,
            },
            "same_eight_group_count_as_local_legacy_labels": True,
            "adjacent_document_places_group_frame_rate_in_separate_R25H_fields": True,
            "therefore_local_11byte_record_contains_no_timing_field": False,
            "therefore_any_local_record_byte_is_frame_rate": False,
            "safe_interpretation": (
                "same terminology is a comparison clue and a counterexample to "
                "inferring field placement from GROUP labels alone"
            ),
        },
        "spd1656_manual": {
            "path": SPD1656_MANUAL.relative_to(REPO_ROOT).as_posix(),
            "bytes": len(manual),
            "sha256": _sha256(manual),
            "revision": "Rev 1.1, Jan 2020",
            "vcom_geometry": "20 groups * 11 bytes",
            "color_geometry": "20 groups * 13 bytes",
            "local_direct_labeled_non_vcom_categories_use_8_groups_of_11_bytes": True,
            "direct_vcom_record_parser_transfer_proven": False,
            "direct_color_record_parser_transfer_proven": False,
            "strict_geometry_conflict_for_color_parser": True,
        },
        "network_accessed_by_this_offline_tool": False,
    }


def build_report() -> dict[str, Any]:
    """Build the deterministic, metadata-only record-semantics report."""

    source_tables = _parse_source_tables()
    active = source_tables["payloads"]["active"]
    commented = source_tables["payloads"]["commented"]
    compiled = _compiled_status(active, commented)
    _require(
        compiled["active_table_bound_to_wf_data_symbol_in_edp_init_object"],
        "active table is no longer bound to the wf_data ELF symbol",
    )
    _require(
        not compiled["commented_exact_full_table_present_in_edp_init_object"],
        "commented exact full table unexpectedly appeared in edp_init.o",
    )
    _require(
        compiled["active_wf_data_535_linked_by_delivered_map"],
        "active wf_data symbol is no longer linked",
    )
    datasets, iar_provenance = _load_datasets(source_tables)
    execution = _source_execution_binding()
    dataset_reports = {
        dataset_id: _dataset_semantics(dataset)
        for dataset_id, dataset in datasets.items()
    }
    _require(
        all(
            report["active_low_sparsity_screen"][
                "all_active_records_have_at_most_24_set_bits_after_complement"
            ]
            for report in dataset_reports.values()
        ),
        "complement sparsity bound changed",
    )
    _require(
        all(
            not report["philips_11byte_projection"][
                "raw_literal_three_level_example_has_no_unassigned_code_3"
            ]
            and not report["philips_11byte_projection"][
                "complement_literal_three_level_example_has_no_unassigned_code_3"
            ]
            for report in dataset_reports.values()
        ),
        "a raw or complemented dataset unexpectedly fits the literal three-level selector example",
    )
    shadow_comparison = _shadow_active_comparison(commented, active)
    _require(
        shadow_comparison["same_coordinate_exact_record_count"] == 0,
        "commented and active tables acquired an exact same-coordinate record",
    )
    _require(
        shadow_comparison["shared_unique_non_all_ff_record_count"] == 0,
        "commented and active tables acquired a shared active record",
    )

    source_report = {
        key: value for key, value in source_tables.items() if key != "payloads"
    }
    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": "offline_identity_pinned_metadata_output_only_record_semantics",
        "source_label_contract": source_report,
        "compiled_and_linked_status": compiled,
        "legacy_header_execution_binding": execution,
        "legacy_evidence_ladder": _evidence_ladder(compiled, execution),
        "datasets": dataset_reports,
        "commented_vs_active_same_source_comparison": shadow_comparison,
        "commented_table_cross_dataset_exact_record_screen": (
            _cross_dataset_exact_records(datasets)
        ),
        "iar_provenance": iar_provenance,
        "public_format_hypotheses": _public_format_hypotheses(),
        "adjudication": {
            "new_direct_result": (
                "the two same-source 535-byte tables directly label every 11-byte "
                "coordinate as category plus GROUP1..GROUP8"
            ),
            "active_legacy_table_is_compiled_and_linked": True,
            "active_legacy_initializer_is_runtime_upload_content_at_every_call_proven": (
                False
            ),
            "linked_UART_path_can_replace_wf_data_before_a_later_upload": True,
            "commented_legacy_source_lines_are_inactive": True,
            "commented_legacy_table_role_proven": False,
            "commented_legacy_table_is_an_authorized_runtime_candidate": False,
            "legacy_record_coordinate_has_direct_source_GROUP_label": True,
            "legacy_GROUP_slot_proven_to_be_chronological_phase": False,
            "eleven_internal_byte_roles_proven": False,
            "record_repeat_or_duration_field_proven": False,
            "record_drive_state_or_polarity_field_proven": False,
            "record_voltage_level_field_proven": False,
            "all_ff_record_terminator_skip_or_noop_semantics_proven": False,
            "bitwise_complement_is_controller_decoder_proven": False,
            "mode1_nine_category_mapping_proven": False,
            "DATA0_DATA1_category_or_controller_pairing_proven": False,
            "header_bytes_1_through_4_have_direct_legacy_PWR_binding": True,
            "header_byte_5_has_direct_legacy_VCOM_binding": False,
            "header_byte_6_has_direct_legacy_PLL_binding": False,
            "source_author_says_upload_loop_count_varies_by_chip_specification": True,
            "source_comment_proves_mode1_799_or_800_byte_length": False,
            "safe_next_evidence": [
                "same-build SPD1657 record decoder or field specification",
                "native loader showing field reads rather than opaque forwarding",
                "full command/data plus chip-select capture with known payload identity",
            ],
            "must_not_use_for": [
                "renaming the eleven record bytes",
                "editing duration polarity voltage or repeat fields",
                "promoting the commented table to a runtime candidate",
                "generating a waveform payload or firmware include",
                "authorizing hardware or a visible refresh",
            ],
        },
        "material_handling": {
            "existing_vendor_wrappers_read": True,
            "existing_profile_plaintext_decrypted_in_memory_by_load_profile": True,
            "raw_key_plaintext_waveform_or_record_bytes_emitted": False,
            "raw_key_plaintext_waveform_or_record_bytes_written": False,
            "profile_pack_render_or_write_path_called": False,
            "runtime_payload_include_or_firmware_generated": False,
        },
        "safety": {
            "offline_only": True,
            "hardware_accessed": False,
            "serial_or_COM8_accessed": False,
            "device_network_accessed": False,
            "firmware_or_flash_written": False,
            "display_refresh_attempted": False,
            "authorization_token_generated_or_claimed": False,
            "runtime_or_recovery_release_modified": False,
            "runtime_payload_generated": False,
            "profile_plaintext_key_or_raw_waveform_written_to_disk": False,
            "vendor_evidence_modified": False,
        },
    }
    report["integrity"] = {
        "canonical_encoding": "UTF-8 sorted-key compact JSON excluding integrity",
        "canonical_sha256": _sha256(_canonical_bytes(report)),
    }
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = build_report()
        payload = (
            json.dumps(
                report,
                ensure_ascii=False,
                indent=None if args.compact else 2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        if args.output is None:
            sys.stdout.buffer.write(payload)
        else:
            write_new_bytes_durable(args.output, payload)
    except (
        RecordSemanticsAuditError,
        arithmetic.ArithmeticTransformAuditError,
        geometry.PhaseGeometryAuditError,
        profile_pack.ProfilePackError,
        DurableWriteError,
        OSError,
        UnicodeError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
