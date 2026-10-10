#!/usr/bin/env python3
"""Compare the local 8x11 record geometry with SSD1680A's exact 8-group ABI.

SSD1680A is a useful adjacent Solomon controller because its public manual
defines eight groups.  Its actual ABI is nevertheless seven bytes per group
per LUT and uses command 0x32 for a 227-byte LUT block.  This audit pins the
manual, extracts those facts, and projects every possible contiguous 7-byte
window of the local 11-byte records without promoting the adjacent field names
to SPD1657/E2802 facts.

Only hashes, counts, dimensions, and decisions are emitted.  No raw waveform
record, key, plaintext payload, firmware include, authorization, or hardware
operation is produced.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import unicodedata
from typing import Any, Final, Iterable


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.application.durable_io import (  # noqa: E402
    DurableWriteError,
    write_new_bytes_durable,
)
from tools import mf1750_spd1656_lutc_projection_audit as spd1656  # noqa: E402
from tools import mf1750_spd1657_patent_11byte_audit as patent  # noqa: E402
from tools import mf1750_spd1657_record_semantics_audit as records  # noqa: E402


KIND: Final = "mf1750-ssd1680a-8group-projection-audit"
SCHEMA_VERSION: Final = 1
MANUAL: Final = (
    REPO_ROOT
    / ".test-output"
    / "offline"
    / "public_sources"
    / "SSD1680A_Rev0.20_Feb2020.pdf"
)
MANUAL_SOURCE_URL: Final = "https://v4.cecdn.yun300.cn/100001_1909185148/SSD1680A.pdf"
MANUAL_REFERRER_URL: Final = "https://www.good-display.com/companyfile/44/"
MANUAL_BYTES: Final = 1_257_063
MANUAL_SHA256: Final = (
    "92ccb43dbcb847707ff907de9989ea18214c968f3584b7493e7460d9268a43bc"
)
MANUAL_PAGE_COUNT: Final = 47
PYMUPDF_VERSION: Final = "1.28.2"
LOCAL_RECORD_BYTES: Final = 11
ADJACENT_GROUP_BYTES: Final = 7
GROUPS_PER_LUT: Final = 8
CONTIGUOUS_WINDOW_STARTS: Final = tuple(
    range(LOCAL_RECORD_BYTES - ADJACENT_GROUP_BYTES + 1)
)
ACTIVE_DATASET_IDS: Final = (
    "legacy_active_535",
    "iar_DATA0_first799",
    "iar_DATA1_704",
    "WF20_25",
    "WF23_25",
)

PAGE_TEXT_SHA256: Final = {
    14: "263cb412e29d26e0ed01b675b2079cbdfa33ad9396e6f27ce177cd99c4fdbc2f",
    15: "8f109ab1fd70611823d5253b6649fbe056cea2bf1fbcc8b101c481c0ba3a486d",
    25: "b078834dfede32e855bc998fe344ce9c3b7e631ecd68dcd62b3435f25859ef20",
    29: "f377bb7adb73050fa5d66e694554a1036de5da2b766733690c026bc9978dedba",
}
PAGE_ANCHORS: Final = {
    14: (
        "there are 8 groups (Group0 to Group7)",
        "each group has 4 phases (Phase A to Phase D)",
        "When TP[nX] = 0, the phase is skipped.",
        "RP[n] = 0 indicates that the group is skipped",
        "SR[nXY] = 0 indicates that the sub-group is skipped",
        "00 VSS DCVCOM",
        "11 VSH2 Floating",
    ),
    15: (
        "there are 233 bytes in the waveform setting",
        "WS byte 0~226",
        "defined by Register 0x32",
        "225 XON3CD XON3AB",
        "226 XON7CD XON7AB",
        "Figure 6-6 : Waveform Setting mapping",
    ),
    25: (
        "0 0 20 0 0 1 0 0 0 0 0 Master Activation",
        "0 0 21 0 0 1 0 0 0 0 1 Display Update Control",
        "RAM content option for Display Update",
    ),
    29: (
        "0 0 32 0 0 1 1 0 0 1 0 Write LUT register",
        "Write LUT register from MCU interface [227 bytes]",
        "VS[nX-LUTm], TP[nX], RP[n], SR[nXY], FR and XON[nXY]",
    ),
}

SSD1680A_FACTS: Final[dict[str, Any]] = {
    "document": "Solomon Systech SSD1680A Rev 0.20, Feb 2020",
    "color_system": "Red/Black/White adjacent controller",
    "lut_names_in_mapping_order": ["LUTC", "LUTR", "LUTW", "LUTB"],
    "lut_count": 4,
    "groups_per_lut": 8,
    "phases_per_group": 4,
    "state_repeat_fields_per_group": 2,
    "group_bytes_per_lut": 7,
    "bytes_per_lut": 56,
    "field_layout_zero_based_within_one_lut_group": {
        "repeat_RP": {"byte_offset": 0, "bits": "7:0", "zero": "group skipped"},
        "phase_A_to_D": {
            "byte_offsets_inclusive": [1, 4],
            "VS_bits": "7:6",
            "TP_bits": "5:0",
            "TP_zero": "phase skipped",
        },
        "state_repeat_AB": {
            "byte_offset": 5,
            "bits": "7:0",
            "zero": "sub-group skipped",
        },
        "state_repeat_CD": {
            "byte_offset": 6,
            "bits": "7:0",
            "zero": "sub-group skipped",
        },
    },
    "per_lut_byte_ranges_inclusive": {
        "LUTC": [0, 55],
        "LUTR": [56, 111],
        "LUTW": [112, 167],
        "LUTB": [168, 223],
    },
    "register_0x32": {
        "role": "Write LUT register from MCU interface",
        "payload_bytes": 227,
        "four_luts_bytes": 224,
        "FR_byte_offset": 224,
        "XON_byte_offsets_inclusive": [225, 226],
    },
    "full_waveform_setting": {
        "bytes": 233,
        "EOPT_byte_offset": 227,
        "VGH_byte_offset": 228,
        "source_voltage_byte_offsets_inclusive": [229, 231],
        "VCOM_byte_offset": 232,
    },
    "command_role_boundary": {
        "0x20": "Master Activation; not a LUT payload command",
        "0x21": "Display Update Control 1; two parameter bytes",
        "0x32": "227-byte MCU waveform LUT write",
    },
    "controller_side_bitwise_complement_documented_in_cited_mapping": False,
}


class Ssd1680aProjectionAuditError(RuntimeError):
    """Raised when a pinned input or required audit invariant changes."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Ssd1680aProjectionAuditError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _normalize_pdf_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _manual_evidence() -> dict[str, Any]:
    _require(MANUAL.is_file(), f"missing SSD1680A manual: {MANUAL}")
    payload = MANUAL.read_bytes()
    _require(len(payload) == MANUAL_BYTES, "SSD1680A manual size changed")
    _require(_sha256(payload) == MANUAL_SHA256, "SSD1680A manual identity changed")
    try:
        import pymupdf
    except ImportError as error:  # pragma: no cover - environment failure path
        raise Ssd1680aProjectionAuditError(
            "PyMuPDF is required for pinned primary-document text extraction"
        ) from error
    _require(
        str(getattr(pymupdf, "__version__", "unknown")) == PYMUPDF_VERSION,
        "PyMuPDF version changed; revalidate pinned page-text extraction",
    )
    try:
        document = pymupdf.open(stream=payload, filetype="pdf")
    except Exception as error:  # pragma: no cover - library failure path
        raise Ssd1680aProjectionAuditError(
            "cannot parse pinned SSD1680A PDF"
        ) from error
    try:
        _require(document.page_count == MANUAL_PAGE_COUNT, "manual page count changed")
        pages = []
        for page_number, expected_hash in PAGE_TEXT_SHA256.items():
            normalized = _normalize_pdf_text(
                document.load_page(page_number - 1).get_text("text")
            )
            digest = _sha256(normalized.encode("utf-8"))
            _require(digest == expected_hash, f"manual page {page_number} changed")
            missing = [
                anchor
                for anchor in PAGE_ANCHORS[page_number]
                if anchor not in normalized
            ]
            _require(not missing, f"manual page {page_number} lost required anchors")
            pages.append(
                {
                    "pdf_page_1_based": page_number,
                    "printed_page": f"P {page_number}/47",
                    "normalized_text_utf8_bytes": len(normalized.encode("utf-8")),
                    "normalized_text_sha256": digest,
                    "required_anchor_count": len(PAGE_ANCHORS[page_number]),
                    "all_required_anchors_present": True,
                    "page_text_emitted": False,
                }
            )
    finally:
        document.close()
    return {
        "path": MANUAL.relative_to(REPO_ROOT).as_posix(),
        "source_url": MANUAL_SOURCE_URL,
        "referrer_url": MANUAL_REFERRER_URL,
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "page_count": MANUAL_PAGE_COUNT,
        "revision": "Rev 0.20, Feb 2020",
        "document_class": "official Solomon Systech product-preview datasheet",
        "extractor": {
            "name": "PyMuPDF",
            "version": str(getattr(pymupdf, "__version__", "unknown")),
            "network_accessed_by_offline_audit": False,
        },
        "pages": pages,
        "facts": SSD1680A_FACTS,
        "facts_canonical_sha256": _sha256(_canonical_bytes(SSD1680A_FACTS)),
        "raw_pdf_or_full_page_text_emitted": False,
    }


def _transform(record: bytes, *, complemented: bool) -> bytes:
    _require(len(record) == LOCAL_RECORD_BYTES, "local record width changed")
    mask = 0xFF if complemented else 0
    return bytes(value ^ mask for value in record)


def _window_projection(
    local_records: Iterable[bytes], *, start: int, complemented: bool
) -> dict[str, Any]:
    _require(start in CONTIGUOUS_WINDOW_STARTS, "candidate window start changed")
    projected = [
        _transform(record, complemented=complemented)[
            start : start + ADJACENT_GROUP_BYTES
        ]
        for record in local_records
    ]
    _require(
        all(len(record) == ADJACENT_GROUP_BYTES for record in projected),
        "candidate window width changed",
    )
    voltage_codes: Counter[int] = Counter()
    phase_lengths: list[int] = []
    for record in projected:
        for phase_byte in record[1:5]:
            voltage_codes[(phase_byte >> 6) & 0x03] += 1
            phase_lengths.append(phase_byte & 0x3F)
    state_repeats = [value for record in projected for value in record[5:7]]
    return {
        "view": "bitwise_complement" if complemented else "raw",
        "candidate_start_offset_in_local_11_byte_record": start,
        "candidate_end_offset_inclusive": start + ADJACENT_GROUP_BYTES - 1,
        "record_count": len(projected),
        "syntactically_valid_under_adjacent_bit_domains": len(projected),
        "invalid_record_count_under_adjacent_bit_domains": 0,
        "adjacent_RP_zero_count": sum(record[0] == 0 for record in projected),
        "adjacent_VS_two_bit_code_counts": {
            str(code): voltage_codes[code] for code in range(4)
        },
        "adjacent_TP_zero_count": phase_lengths.count(0),
        "adjacent_TP_value_count": len(phase_lengths),
        "adjacent_SR_zero_count": state_repeats.count(0),
        "adjacent_SR_value_count": len(state_repeats),
        "all_seven_projected_bytes_zero_record_count": sum(
            not any(record) for record in projected
        ),
        "unexplained_local_bytes_per_record": LOCAL_RECORD_BYTES - ADJACENT_GROUP_BYTES,
        "field_names_or_zero_semantics_apply_to_local_format_proven": False,
        "raw_records_or_field_values_emitted": False,
    }


def _load_local_evidence() -> tuple[dict[str, records.Dataset], dict[str, Any]]:
    source_tables = records._parse_source_tables()
    datasets, iar_provenance = records._load_datasets(source_tables)
    _require(
        tuple(datasets) == ("legacy_commented_535", *ACTIVE_DATASET_IDS),
        "record-semantics dataset inventory changed",
    )
    for dataset in datasets.values():
        _require(
            all(len(record) == LOCAL_RECORD_BYTES for record in dataset.records),
            f"{dataset.dataset_id} record width changed",
        )
        _require(
            len(dataset.records) == dataset.category_count * GROUPS_PER_LUT,
            f"{dataset.dataset_id} group count changed",
        )
    return datasets, iar_provenance


def _local_geometry(datasets: dict[str, records.Dataset]) -> dict[str, Any]:
    active_records = tuple(
        record
        for dataset_id in ACTIVE_DATASET_IDS
        for record in datasets[dataset_id].records
    )
    category_count = sum(datasets[item].category_count for item in ACTIVE_DATASET_IDS)
    _require(category_count == 41, "active category aggregate changed")
    _require(len(active_records) == 328, "active record aggregate changed")
    views = {}
    for complemented in (False, True):
        name = "bitwise_complement" if complemented else "raw"
        rows = [
            _window_projection(active_records, start=start, complemented=complemented)
            for start in CONTIGUOUS_WINDOW_STARTS
        ]
        views[name] = {
            "candidate_windows": rows,
            "candidate_window_count": len(rows),
            "all_windows_accept_every_record_by_bit_domain": all(
                row["syntactically_valid_under_adjacent_bit_domains"]
                == len(active_records)
                for row in rows
            ),
            "unique_window_identified_by_validity": False,
        }
    return {
        "dataset_ids": list(datasets),
        "active_dataset_ids": list(ACTIVE_DATASET_IDS),
        "inactive_commented_table_excluded_from_aggregate": True,
        "datasets": {
            dataset_id: {
                "body_bytes": len(dataset.body),
                "body_sha256": _sha256(dataset.body),
                "category_count": dataset.category_count,
                "groups_per_category": GROUPS_PER_LUT,
                "local_record_bytes": LOCAL_RECORD_BYTES,
                "record_count": len(dataset.records),
                "provenance": dataset.provenance,
                "raw_records_or_payload_bytes_emitted": False,
            }
            for dataset_id, dataset in datasets.items()
        },
        "active_aggregate": {
            "category_count": category_count,
            "record_count": len(active_records),
            "views": views,
        },
        "local_category_formula": "8 groups * 11 bytes = 88 bytes",
        "adjacent_one_lut_formula": "8 groups * 7 bytes = 56 bytes",
        "per_category_or_lut_width_delta_bytes": 32,
        "contiguous_adjacent_window_start_offsets_swept": list(
            CONTIGUOUS_WINDOW_STARTS
        ),
    }


def _hybrid_lineage_boundary() -> dict[str, Any]:
    color = spd1656.SPD1656_LUTC_FACTS["adjacent_same_controller_geometries"][  # type: ignore[index]
        "R21_to_R28_color"
    ]
    return {
        "local_observed_geometry": {
            "groups_per_category": 8,
            "record_bytes": 11,
            "category_bytes": 88,
            "candidate_R20_bytes": 799,
            "candidate_R21_bytes": 704,
        },
        "SSD1680A": {
            "matches_local_group_count": True,
            "matches_local_record_width": False,
            "group_bytes_per_lut": 7,
            "command_0x20_role_matches_local_payload_sink": False,
            "command_0x21_role_matches_local_payload_sink": False,
            "waveform_write_command": "0x32",
            "waveform_write_bytes": 227,
        },
        "SPD1656": {
            "manual_sha256": spd1656.MANUAL_SHA256,
            "VCOM_matches_local_record_width": True,
            "VCOM_matches_local_group_count": False,
            "VCOM_group_count": spd1656.SPD1656_LUTC_FACTS["group_count"],
            "VCOM_group_bytes": spd1656.SPD1656_LUTC_FACTS["group_bytes"],
            "VCOM_R20_payload_bytes": spd1656.SPD1656_LUTC_FACTS["payload_bytes"],
            "color_group_count": color["group_count"],
            "color_group_bytes": color["group_bytes"],
            "color_payload_bytes": color["payload_bytes"],
        },
        "no_single_adjacent_manual_matches_group_count_record_width_command_role_and_payload_length": True,
        "hybrid_8_groups_times_11_bytes_is_an_arithmetic_recombination_not_an_ABI": True,
        "candidate_layout_matrix": {
            "SPD1656_VCOM": {
                "direct_source_layout": "1 RP + 2 packed LVL + 8 TP = 11 bytes",
                "same_manufacturer": True,
                "matches_local_record_bytes": True,
                "matches_local_group_count": False,
                "matches_local_non_VCOM_command_role": False,
                "transfer_allowed": False,
            },
            "SSD1680A": {
                "direct_source_layout": "1 RP + 4 combined VS/TP + 2 SR = 7 bytes",
                "same_manufacturer": True,
                "matches_local_record_bytes": False,
                "matches_local_group_count": True,
                "matches_local_command_roles": False,
                "transfer_allowed": False,
            },
            "unpublished_phase_expansion": {
                "arithmetic_only": "1 RP + 8 combined VS/TP + 2 SR = 11 bytes",
                "eight_phase_two_SR_controller_source_found": False,
                "symmetric_one_SR_per_phase_pair_would_instead_require_bytes": 13,
                "local_field_layout_proven": False,
                "transfer_allowed": False,
            },
            "Philips_Apollo_particular_design": {
                "direct_source_layout": (
                    "8 selector bytes + row time + inter-frame delay + frame count "
                    "= 11 bytes"
                ),
                "same_manufacturer": False,
                "publication": patent.PRIMARY_PATENT_FACTS["publication"],
                "matches_local_record_bytes": True,
                "local_literal_example_decoded": False,
                "transfer_allowed": False,
            },
        },
    }


def build_report() -> dict[str, Any]:
    """Build a deterministic, metadata-only adjacent-controller report."""

    datasets, iar_provenance = _load_local_evidence()
    local = _local_geometry(datasets)
    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": "offline_identity_pinned_metadata_only_adjacent_abi_falsification",
        "primary_adjacent_document": _manual_evidence(),
        "local_evidence": local,
        "iar_provenance": iar_provenance,
        "hybrid_lineage_boundary": _hybrid_lineage_boundary(),
        "adjudication": {
            "direct_primary_fact": (
                "SSD1680A uses four LUTs, each with eight 7-byte groups; command "
                "0x32 receives the combined 227-byte LUT block"
            ),
            "local_direct_fact": (
                "local candidates use eight 11-byte records per category and observed "
                "R20/R21 candidate lengths of 799/704 bytes"
            ),
            "eight_group_similarity_is_real_but_insufficient": True,
            "four_extra_local_bytes_per_record_explained": False,
            "contiguous_seven_byte_alignment_identified": False,
            "raw_or_complement_view_identified": False,
            "local_RP_VS_TP_SR_field_names_proven": False,
            "local_zero_skip_repeat_or_voltage_semantics_proven": False,
            "SSD1680A_command_0x20_or_0x21_field_transfer_allowed": False,
            "SSD1680A_electrical_code_or_timing_transfer_allowed": False,
            "safe_next_evidence": [
                "same-version SPD1657/E2802 record decoder or field specification",
                "same-version loader that consumes fields instead of forwarding bytes",
                "full command/data/chip-select capture with a known payload identity",
                "paired vendor profiles changing one documented field only",
            ],
            "hardware_experiment_or_payload_generation_authorized": False,
        },
        "material_handling": {
            "existing_wrappers_decoded_in_memory_by_pinned_loader": True,
            "manual_pages_text_extracted_in_memory": True,
            "raw_key_plaintext_record_or_waveform_bytes_emitted": False,
            "raw_key_plaintext_record_or_waveform_bytes_written": False,
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
            "runtime_payload_generated_or_modified": False,
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
        Ssd1680aProjectionAuditError,
        records.RecordSemanticsAuditError,
        DurableWriteError,
        OSError,
        UnicodeError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
