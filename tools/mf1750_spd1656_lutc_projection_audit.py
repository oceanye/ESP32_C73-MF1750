#!/usr/bin/env python3
"""Falsify direct SPD1656-LUTC field transfer onto local 11-byte records.

The pinned SPD1656 manual gives one exact 11-byte layout, but only for its
R20/LUTC VCOM table: one RP byte, two packed 2-bit level bytes, and eight TP
bytes.  Local SPD1657/E2802 candidates also contain source- or
geometry-bounded 11-byte records.  Equal width is not an ABI proof, so this
offline audit does three deliberately separate things:

* identity-check and text-extract the relevant SPD1656 manual pages;
* project the documented layout over every retained local record in both raw
  and bitwise-complement views;
* sweep every byte offset as a possible zero-termination field so byte zero is
  not selected merely because the adjacent manual names it RP.

Only counts, hashes, coordinates, and boolean decisions are emitted.  No raw
waveform record, key, plaintext payload, firmware include, authorization, or
hardware operation is produced.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import unicodedata
from typing import Any, Final, Sequence


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.application.durable_io import (  # noqa: E402
    DurableWriteError,
    write_new_bytes_durable,
)
from tools import mf1750_spd1657_record_semantics_audit as records  # noqa: E402


KIND: Final = "mf1750-spd1656-lutc-projection-audit"
SCHEMA_VERSION: Final = 1
MANUAL: Final = REPO_ROOT / "参考资料" / "Solomon-SPD1656.pdf"
MANUAL_BYTES: Final = 2_339_387
MANUAL_SHA256: Final = (
    "1f3f5db0600ee6e8133a4c31f9a3f59c1b5bfcc1a916be98ae848ec64581de07"
)
MANUAL_PAGE_COUNT: Final = 44
PYMUPDF_VERSION: Final = "1.28.2"
RECORD_BYTES: Final = 11
RECORDS_PER_LOCAL_CATEGORY: Final = 8
ACTIVE_DATASET_IDS: Final = (
    "legacy_active_535",
    "iar_DATA0_first799",
    "iar_DATA1_704",
    "WF20_25",
    "WF23_25",
)

PAGE_TEXT_SHA256: Final = {
    13: "cad8dd4642270d625ad20c0509b3765c9feaff226f3c8eaf95c2e524ba365f30",
    15: "49c78c944a483011934dc58a3b6f226351e12833a732b9c2fe9d7c3015a30e80",
    17: "b7e070620ea07d239e1efac3058ffe9568d24c62961f488b3bdb3a8441b34840",
    27: "8c164d8953dcbadd685a278aa36a50e04794aaea87908a41cf6d1ddc050497c3",
    28: "fff1195529cf4b0360e706d265cac9f91fce9a252584dd3f1a1b2470649c2fb0",
    29: "6af77b230e0efe690c023b4044aaa0706b5a3249b4a572dcee11d8ac54ab6e3e",
}
PAGE_ANCHORS: Final = {
    13: (
        "There are 20 groups, each group contains 8 phases, totally 160 phases",
        "TP[nX] = 0 indicates phase skipped.",
        "RP[n] = 0 indicates No repeat, End of LUT",
    ),
    15: (
        "VCOM LUT (T0~T9)",
        "See command LUTC (R20h) for details",
    ),
    17: (
        "LUTC W 0 0 0 1 0 0 0 0 0 20h",
        "Phase repeat times [7:0]",
    ),
    27: (
        "This command builds up VCOM Look-Up Table (LUT).",
        "each group is of 11 bytes. Total parameter is 220 byte.",
        "1st parameter: RP[7:0] ~ repeat number.",
        "2nd and 3rd parameter:",
        "4th and 11th parameter:",
        "00h ~ No Repeat, End of LUT.",
        "00h ~ Phase Skip",
    ),
    28: (
        "This command builds LUTB for black.",
        "each group is of 13 bytes. Total parameter is 260 byte.",
    ),
    29: (
        "This command builds LUT for XON.",
        "each group is of 10 bytes. Total parameter is 200 byte.",
    ),
}

SPD1656_LUTC_FACTS: Final[dict[str, Any]] = {
    "document": "Solomon Systech SPD1656 Rev 1.1, Jan 2020",
    "command": "R20/LUTC",
    "role": "VCOM look-up table",
    "group_count": 20,
    "group_bytes": 11,
    "payload_bytes": 220,
    "phases_per_group": 8,
    "field_layout_zero_based": {
        "repeat_RP": {"byte_offset": 0, "bits": "7:0"},
        "levels_LVL1_to_LVL4": {
            "byte_offset": 1,
            "bit_slots_msb_to_lsb": ["7:6", "5:4", "3:2", "1:0"],
        },
        "levels_LVL5_to_LVL8": {
            "byte_offset": 2,
            "bit_slots_msb_to_lsb": ["7:6", "5:4", "3:2", "1:0"],
        },
        "phase_frame_counts_TP1_to_TP8": {
            "byte_offsets_inclusive": [3, 10],
            "bits": "7:0",
        },
    },
    "RP_zero_documented_meaning": "No Repeat, End of LUT",
    "RP_nonzero_range": [1, 255],
    "TP_zero_documented_meaning": "Phase Skip",
    "TP_nonzero_frame_range": [1, 255],
    "level_codes": {
        "0": "VCOM_DC",
        "1": "VSH + VCOM_DC",
        "2": "VSL + VCOM_DC",
        "3": "HiZ",
    },
    "adjacent_same_controller_geometries": {
        "R21_to_R28_color": {
            "group_count": 20,
            "group_bytes": 13,
            "payload_bytes": 260,
            "level_bits": 3,
        },
        "R29_XON": {
            "group_count": 20,
            "group_bytes": 10,
            "payload_bytes": 200,
            "selection_bits": 1,
        },
    },
}


class Spd1656ProjectionAuditError(RuntimeError):
    """Raised when a pinned input or a required audit invariant changes."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Spd1656ProjectionAuditError(message)


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
    _require(MANUAL.is_file(), f"missing SPD1656 manual: {MANUAL}")
    payload = MANUAL.read_bytes()
    _require(len(payload) == MANUAL_BYTES, "SPD1656 manual size changed")
    _require(_sha256(payload) == MANUAL_SHA256, "SPD1656 manual identity changed")
    try:
        import pymupdf
    except ImportError as error:  # pragma: no cover - environment failure path
        raise Spd1656ProjectionAuditError(
            "PyMuPDF is required for pinned primary-document text extraction"
        ) from error
    _require(
        str(getattr(pymupdf, "__version__", "unknown")) == PYMUPDF_VERSION,
        "PyMuPDF version changed; revalidate pinned page-text extraction",
    )

    try:
        document = pymupdf.open(stream=payload, filetype="pdf")
    except Exception as error:  # pragma: no cover - library failure path
        raise Spd1656ProjectionAuditError("cannot parse pinned SPD1656 PDF") from error
    try:
        _require(document.page_count == MANUAL_PAGE_COUNT, "manual page count changed")
        page_evidence = []
        for page_number, expected_hash in PAGE_TEXT_SHA256.items():
            normalized = _normalize_pdf_text(
                document.load_page(page_number - 1).get_text("text")
            )
            digest = _sha256(normalized.encode("utf-8"))
            _require(digest == expected_hash, f"manual page {page_number} text changed")
            missing = [
                anchor
                for anchor in PAGE_ANCHORS[page_number]
                if anchor not in normalized
            ]
            _require(not missing, f"manual page {page_number} lost required anchors")
            page_evidence.append(
                {
                    "pdf_page_1_based": page_number,
                    "printed_page": f"P {page_number}/44",
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
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "page_count": MANUAL_PAGE_COUNT,
        "revision": "Rev 1.1, Jan 2020",
        "extractor": {
            "name": "PyMuPDF",
            "version": str(getattr(pymupdf, "__version__", "unknown")),
            "network_accessed": False,
        },
        "pages": page_evidence,
        "facts": SPD1656_LUTC_FACTS,
        "facts_canonical_sha256": _sha256(_canonical_bytes(SPD1656_LUTC_FACTS)),
        "raw_pdf_or_full_page_text_emitted": False,
    }


def _transform(record: bytes, *, complemented: bool) -> bytes:
    _require(len(record) == RECORD_BYTES, "local record width changed")
    mask = 0xFF if complemented else 0
    return bytes(value ^ mask for value in record)


def _category_records(category: bytes, *, complemented: bool) -> tuple[bytes, ...]:
    _require(
        len(category) == RECORDS_PER_LOCAL_CATEGORY * RECORD_BYTES,
        "local category geometry changed",
    )
    return tuple(
        _transform(category[offset : offset + RECORD_BYTES], complemented=complemented)
        for offset in range(0, len(category), RECORD_BYTES)
    )


def _termination_summary(
    categories: Sequence[bytes], *, complemented: bool, candidate_offset: int
) -> dict[str, Any]:
    _require(0 <= candidate_offset < RECORD_BYTES, "candidate offset is out of range")
    first_zero_histogram: Counter[int] = Counter()
    zero_candidate_records = 0
    zero_candidate_nonzero_records = 0
    no_zero = 0
    candidate_suffix_clean = 0
    candidate_suffix_violated = 0
    whole_zero_suffix_clean = 0
    first_zero_record_all_zero = 0
    nonzero_record_after_first_zero = 0
    all_zero_records = 0

    for category in categories:
        projected = _category_records(category, complemented=complemented)
        all_zero_records += sum(not any(record) for record in projected)
        zero_indices = [
            index
            for index, record in enumerate(projected)
            if record[candidate_offset] == 0
        ]
        zero_candidate_records += len(zero_indices)
        zero_candidate_nonzero_records += sum(
            record[candidate_offset] == 0 and any(record) for record in projected
        )
        if not zero_indices:
            no_zero += 1
            continue
        first = zero_indices[0]
        first_zero_histogram[first] += 1
        suffix = projected[first:]
        if all(record[candidate_offset] == 0 for record in suffix):
            candidate_suffix_clean += 1
        else:
            candidate_suffix_violated += 1
        if all(not any(record) for record in suffix):
            whole_zero_suffix_clean += 1
        if not any(projected[first]):
            first_zero_record_all_zero += 1
        if any(any(record) for record in projected[first + 1 :]):
            nonzero_record_after_first_zero += 1

    category_count = len(categories)
    _require(
        no_zero + candidate_suffix_clean + candidate_suffix_violated == category_count,
        "termination category accounting changed",
    )
    return {
        "candidate_byte_offset": candidate_offset,
        "category_count": category_count,
        "categories_with_no_zero_candidate": no_zero,
        "categories_with_zero_candidate": category_count - no_zero,
        "categories_with_candidate_zero_suffix": candidate_suffix_clean,
        "categories_with_later_nonzero_candidate": candidate_suffix_violated,
        "categories_with_whole_zero_record_suffix": whole_zero_suffix_clean,
        "categories_whose_first_zero_candidate_record_is_all_zero": (
            first_zero_record_all_zero
        ),
        "categories_with_nonzero_record_after_first_zero_candidate": (
            nonzero_record_after_first_zero
        ),
        "first_zero_group_index_histogram_zero_based": {
            str(index): first_zero_histogram[index]
            for index in sorted(first_zero_histogram)
        },
        "zero_candidate_record_count": zero_candidate_records,
        "zero_candidate_but_nonzero_record_count": zero_candidate_nonzero_records,
        "all_zero_record_count": all_zero_records,
    }


def _level_codes(record: bytes) -> tuple[int, ...]:
    return tuple(
        (record[byte_offset] >> shift) & 0x03
        for byte_offset in (1, 2)
        for shift in (6, 4, 2, 0)
    )


def _documented_projection(
    categories: Sequence[bytes], *, complemented: bool
) -> dict[str, Any]:
    projected = [
        record
        for category in categories
        for record in _category_records(category, complemented=complemented)
    ]
    level_counts: Counter[int] = Counter()
    level_by_phase = [Counter() for _ in range(8)]
    for record in projected:
        codes = _level_codes(record)
        level_counts.update(codes)
        for phase_index, code in enumerate(codes):
            level_by_phase[phase_index][code] += 1
    tp_values = [value for record in projected for value in record[3:11]]
    termination = _termination_summary(
        categories,
        complemented=complemented,
        candidate_offset=0,
    )
    return {
        "view": "bitwise_complement" if complemented else "raw",
        "record_count": len(projected),
        "documented_field_offsets": {
            "RP": 0,
            "packed_LVL": [1, 2],
            "TP_inclusive": [3, 10],
        },
        "RP": {
            "zero_count": sum(record[0] == 0 for record in projected),
            "nonzero_count": sum(record[0] != 0 for record in projected),
            "termination_shape": termination,
        },
        "LVL": {
            "two_bit_code_counts": {str(code): level_counts[code] for code in range(4)},
            "code_counts_by_phase_slot": [
                {str(code): counts[code] for code in range(4)}
                for counts in level_by_phase
            ],
            "phase_slot_order_proven_for_local_format": False,
            "electrical_level_mapping_proven_for_local_format": False,
        },
        "TP": {
            "zero_count": tp_values.count(0),
            "nonzero_count": len(tp_values) - tp_values.count(0),
            "value_count": len(tp_values),
            "frame_count_semantics_proven_for_local_format": False,
        },
        "raw_records_or_field_values_emitted": False,
    }


def _offset_sweep(
    categories: Sequence[bytes], *, complemented: bool
) -> list[dict[str, Any]]:
    return [
        _termination_summary(
            categories,
            complemented=complemented,
            candidate_offset=offset,
        )
        for offset in range(RECORD_BYTES)
    ]


def _dataset_report(dataset: records.Dataset) -> dict[str, Any]:
    _require(
        len(dataset.categories) == dataset.category_count,
        f"{dataset.dataset_id} category count changed",
    )
    return {
        "dataset_id": dataset.dataset_id,
        "body_bytes": len(dataset.body),
        "body_sha256": _sha256(dataset.body),
        "category_count": dataset.category_count,
        "records_per_category": RECORDS_PER_LOCAL_CATEGORY,
        "record_bytes": RECORD_BYTES,
        "record_count": len(dataset.records),
        "provenance": dataset.provenance,
        "views": {
            "raw": {
                "documented_spd1656_projection": _documented_projection(
                    dataset.categories, complemented=False
                ),
                "all_candidate_byte_offsets": _offset_sweep(
                    dataset.categories, complemented=False
                ),
            },
            "bitwise_complement": {
                "documented_spd1656_projection": _documented_projection(
                    dataset.categories, complemented=True
                ),
                "all_candidate_byte_offsets": _offset_sweep(
                    dataset.categories, complemented=True
                ),
            },
        },
        "raw_records_or_payload_bytes_emitted": False,
    }


def _aggregate_active(datasets: dict[str, records.Dataset]) -> dict[str, Any]:
    categories = tuple(
        category
        for dataset_id in ACTIVE_DATASET_IDS
        for category in datasets[dataset_id].categories
    )
    raw_sweep = _offset_sweep(categories, complemented=False)
    complement_sweep = _offset_sweep(categories, complemented=True)
    maximum_whole_zero_suffix = max(
        row["categories_with_whole_zero_record_suffix"] for row in complement_sweep
    )
    maximum_offsets = [
        row["candidate_byte_offset"]
        for row in complement_sweep
        if row["categories_with_whole_zero_record_suffix"] == maximum_whole_zero_suffix
    ]
    documented_complement = _documented_projection(categories, complemented=True)
    return {
        "dataset_ids": list(ACTIVE_DATASET_IDS),
        "inactive_commented_table_excluded": True,
        "category_count": len(categories),
        "record_count": len(categories) * RECORDS_PER_LOCAL_CATEGORY,
        "raw": {
            "documented_spd1656_projection": _documented_projection(
                categories, complemented=False
            ),
            "all_candidate_byte_offsets": raw_sweep,
        },
        "bitwise_complement": {
            "documented_spd1656_projection": documented_complement,
            "all_candidate_byte_offsets": complement_sweep,
            "maximum_whole_zero_suffix_category_count": maximum_whole_zero_suffix,
            "byte_offsets_at_that_maximum": maximum_offsets,
            "documented_RP_offset_is_unique_maximum": maximum_offsets == [0],
        },
    }


def _pair_field_difference(
    left: records.Dataset, right: records.Dataset
) -> dict[str, Any]:
    _require(
        left.category_count == right.category_count,
        "paired category count changed",
    )
    _require(len(left.records) == len(right.records), "paired record count changed")
    pairs = tuple(zip(left.records, right.records))
    rp = sum(a[0] != b[0] for a, b in pairs)
    lvl = sum(a[index] != b[index] for a, b in pairs for index in (1, 2))
    tp = sum(a[index] != b[index] for a, b in pairs for index in range(3, 11))
    return {
        "left": left.dataset_id,
        "right": right.dataset_id,
        "compared_record_count": len(pairs),
        "different_byte_positions_under_adjacent_layout": {
            "RP_byte_0": rp,
            "packed_LVL_bytes_1_2": lvl,
            "TP_bytes_3_10": tp,
            "total": rp + lvl + tp,
        },
        "field_names_apply_to_local_format_proven": False,
    }


def build_report() -> dict[str, Any]:
    """Build a deterministic metadata-only adjacent-layout projection report."""

    source_tables = records._parse_source_tables()
    datasets, iar_provenance = records._load_datasets(source_tables)
    _require(
        tuple(datasets)
        == (
            "legacy_commented_535",
            *ACTIVE_DATASET_IDS,
        ),
        "record-semantics dataset inventory changed",
    )
    dataset_reports = {
        dataset_id: _dataset_report(dataset) for dataset_id, dataset in datasets.items()
    }
    active = _aggregate_active(datasets)
    raw_rp = active["raw"]["documented_spd1656_projection"]["RP"]
    complement_rp = active["bitwise_complement"]["documented_spd1656_projection"]["RP"]
    _require(raw_rp["zero_count"] == 0, "active raw RP-zero count changed")
    _require(
        not active["bitwise_complement"]["documented_RP_offset_is_unique_maximum"],
        "documented RP offset unexpectedly became unique",
    )

    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": "offline_identity_pinned_metadata_only_adjacent_layout_falsification",
        "primary_adjacent_document": _manual_evidence(),
        "local_datasets": dataset_reports,
        "iar_provenance": iar_provenance,
        "active_dataset_aggregate": active,
        "paired_profile_field_region_difference": _pair_field_difference(
            datasets["WF20_25"], datasets["WF23_25"]
        ),
        "adjudication": {
            "direct_primary_fact": (
                "SPD1656 R20/LUTC VCOM uses 20 groups of 11 bytes; each group is "
                "RP + two packed LVL bytes + eight TP bytes"
            ),
            "local_direct_fact": (
                "local candidates use eight 11-byte GROUP records per category, "
                "including source-labeled non-VCOM categories"
            ),
            "same_eleven_byte_width_is_structural_similarity_only": True,
            "strict_geometry_and_command_role_conflicts": {
                "SPD1656_R20": "VCOM only, 20*11=220, no local seven-byte header",
                "SPD1656_color_R21_to_R28": "20*13=260 per color LUT",
                "local_legacy_R20": "7 + 6*(8*11) = 535",
                "local_mode1_candidate_R20": "7 + 9*(8*11) = 799",
                "local_mode1_candidate_R21": "704 bytes",
            },
            "active_raw_projection": {
                "RP_zero_record_count": raw_rp["zero_count"],
                "category_count_without_RP_zero": raw_rp["termination_shape"][
                    "categories_with_no_zero_candidate"
                ],
                "literal_SPD1656_zero_termination_shape_observed": False,
            },
            "active_complement_projection": {
                "RP_zero_record_count": complement_rp["zero_count"],
                "categories_with_whole_zero_record_suffix": complement_rp[
                    "termination_shape"
                ]["categories_with_whole_zero_record_suffix"],
                "categories_with_nonzero_record_after_first_RP_zero": complement_rp[
                    "termination_shape"
                ]["categories_with_nonzero_record_after_first_zero_candidate"],
                "categories_with_no_RP_zero": complement_rp["termination_shape"][
                    "categories_with_no_zero_candidate"
                ],
                "supports_active_low_or_complemented_structure_as_a_hypothesis": True,
                "proves_controller_side_complement": False,
            },
            "documented_RP_byte_offset_uniquely_identified_by_zero_suffix": False,
            "local_GROUP_record_is_one_SPD1656_phase_proven": False,
            "local_group_contains_eight_phases_proven": False,
            "local_RP_LVL_TP_field_names_proven": False,
            "local_FF_is_terminator_skip_or_noop_proven": False,
            "local_voltage_polarity_duration_or_repeat_semantics_proven": False,
            "direct_SPD1656_parser_or_voltage_code_transfer_allowed": False,
            "safe_next_evidence": [
                "same-version SPD1657/E2802 record decoder or field specification",
                "same-version loader that reads fields rather than forwarding bytes",
                "full command/data/chip-select capture plus known payload identity",
                "readback or paired profiles changing one vendor-defined field only",
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
        Spd1656ProjectionAuditError,
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
