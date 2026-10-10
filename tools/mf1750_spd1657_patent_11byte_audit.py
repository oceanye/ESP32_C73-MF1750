#!/usr/bin/env python3
"""Compare local 11-byte LUT groups with one published Philips frame format.

This is an offline, metadata-only hypothesis audit.  It identity-checks the
two recovered vendor profiles and the legacy 535-byte table, then projects
their already-proven 11-byte group boundaries onto the field layout described
in US20070085819A1 / WO2005038765A1.  It emits counts, histograms, hashes, and
boolean compatibility tests only; it never emits waveform bytes, keys, or
plaintext and never constructs a runtime payload.

The patent describes a Philips/Apollo example, not SPD1657/E2802.  Matching the
record width is therefore only a structural clue.  This tool deliberately does
not transfer field names, voltage meanings, timing units, sentinel semantics,
or controller behavior to the local candidates.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Final, Iterable

from tools import mf1750_spd1657_phase_geometry_audit as geometry_audit
from tools import mf1750_spd1657_vendor_profile_pack as profile_pack


KIND: Final = "mf1750-spd1657-patent-11byte-audit"
SCHEMA_VERSION: Final = 1
REPO_ROOT: Final = Path(__file__).resolve().parents[1]

HEADER_BYTES: Final = 7
RECORD_BYTES: Final = 11
SELECTOR_BYTES: Final = 8
RECORDS_PER_CATEGORY: Final = 8
CATEGORY_BYTES: Final = RECORD_BYTES * RECORDS_PER_CATEGORY
VENDOR_CATEGORY_COUNT: Final = 9
LEGACY_CATEGORY_COUNT: Final = 6

PRIMARY_PATENT_FACTS: Final[dict[str, Any]] = {
    "publication": "US20070085819A1",
    "family_publication": "WO2005038765A1",
    "title": "Look-up tables with graylevel transition waveforms for bi-stable display",
    "assignee_at_publication": "Koninklijke Philips Electronics N.V.",
    "priority_date": "2004-10-14",
    "controller_example": "Philips Apollo ASIC",
    "html_url": "https://patents.google.com/patent/US20070085819A1/en",
    "pdf_url": (
        "https://patentimages.storage.googleapis.com/15/b0/f2/"
        "5212bb4dfdb944/US20070085819A1.pdf"
    ),
    "pdf_bytes_observed_2026_08_11": 1_095_324,
    "pdf_sha256_observed_2026_08_11": (
        "7596c486fccf3e58ab84a6241993272feee8e06b91ab4f49eaba404713f46cbe"
    ),
    "relevant_description_paragraphs": [37, 38, 48, 49, 50, 51],
    "particular_design": {
        "record_bytes": 11,
        "bytes_0_through_7": "32 ordered two-bit voltage selectors",
        "byte_8": "display row time",
        "byte_9": "inter-frame delay",
        "byte_10": "frame count",
        "three_level_example_codes": {
            "0": "0 V",
            "1": "+15 V",
            "2": "-15 V",
            "3": "not assigned by the example",
        },
        "sequence_end_may_be_indicated_by": "FF FF",
        "single_ff_in_sequence_field": "hardware-shaking escape",
        "record_may_grow_for_more_than_three_driver_voltages": True,
    },
}

# SHA-256 of compact, sorted, ASCII JSON for PRIMARY_PATENT_FACTS.  This pins
# the manually transcribed primary-source contract without making the offline
# tool fetch or execute network content.
PRIMARY_PATENT_FACTS_SHA256: Final = (
    "db4b4a7f717a9a3323e974827f5af1b59878e7027ab0118b38b879cebc5504b6"
)


class Patent11ByteAuditError(RuntimeError):
    """Raised when frozen evidence or audit invariants no longer hold."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return _sha256(payload)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Patent11ByteAuditError(message)


def _histogram(values: Iterable[int]) -> dict[str, int]:
    counts = Counter(values)
    return {f"{value:02X}": counts[value] for value in sorted(counts)}


def _selector_counts(records: Iterable[bytes]) -> dict[str, int]:
    counts: Counter[int] = Counter()
    for record in records:
        for value in record[:SELECTOR_BYTES]:
            counts.update(
                (
                    (value >> 6) & 0x03,
                    (value >> 4) & 0x03,
                    (value >> 2) & 0x03,
                    value & 0x03,
                )
            )
    return {str(code): counts[code] for code in range(4)}


def _position_summary(values: list[int], *, hypothesis: str) -> dict[str, Any]:
    return {
        "hypothesized_field_from_patent": hypothesis,
        "sample_count": len(values),
        "sha256_of_ordered_values": _sha256(bytes(values)),
        "unique_value_count": len(set(values)),
        "minimum": min(values),
        "maximum": max(values),
        "zero_count": values.count(0x00),
        "ff_count": values.count(0xFF),
        "value_histogram": _histogram(values),
        "field_semantics_or_units_proven_for_spd1657": False,
    }


def _split_records(
    payload: bytes,
    *,
    profile_id: str,
    category_count: int,
    has_outer_zero_sentinel: bool,
) -> tuple[bytes, list[list[bytes]], dict[str, Any]]:
    expected_body_bytes = category_count * CATEGORY_BYTES
    expected_bytes = HEADER_BYTES + expected_body_bytes + int(has_outer_zero_sentinel)
    _require(len(payload) == expected_bytes, f"{profile_id} geometry changed")
    body = payload[HEADER_BYTES : HEADER_BYTES + expected_body_bytes]
    categories = [
        [
            body[
                category_index * CATEGORY_BYTES
                + record_index * RECORD_BYTES : category_index * CATEGORY_BYTES
                + (record_index + 1) * RECORD_BYTES
            ]
            for record_index in range(RECORDS_PER_CATEGORY)
        ]
        for category_index in range(category_count)
    ]
    _require(
        all(len(record) == RECORD_BYTES for row in categories for record in row),
        f"{profile_id} record split changed",
    )
    if has_outer_zero_sentinel:
        sentinel_offset = HEADER_BYTES + expected_body_bytes
        _require(payload[sentinel_offset] == 0, f"{profile_id} sentinel changed")
        sentinel = {
            "present": True,
            "offset": sentinel_offset,
            "is_zero": True,
            "is_patent_ff_ff_sequence_terminator": False,
        }
    else:
        sentinel = {
            "present": False,
            "reason": "legacy declaration ends at its sixth 88-byte category",
        }
    return body, categories, sentinel


def _category_boundary_summary(
    category_index: int, records: list[bytes]
) -> dict[str, Any]:
    all_ff_flags = [record == b"\xff" * RECORD_BYTES for record in records]
    boundary_ff_ff_flags = [record[:2] == b"\xff\xff" for record in records]
    first_boundary = next(
        (index for index, value in enumerate(boundary_ff_ff_flags) if value), None
    )
    later_non_all_ff = (
        []
        if first_boundary is None
        else [
            index
            for index in range(first_boundary + 1, len(records))
            if not all_ff_flags[index]
        ]
    )
    trailing_all_ff = 0
    for value in reversed(all_ff_flags):
        if not value:
            break
        trailing_all_ff += 1
    return {
        "category_index": category_index,
        "record_count": len(records),
        "all_ff_record_count": sum(all_ff_flags),
        "non_all_ff_record_count": len(records) - sum(all_ff_flags),
        "first_record_boundary_with_ff_ff": first_boundary,
        "non_all_ff_record_count_after_first_boundary_ff_ff": len(later_non_all_ff),
        "trailing_all_ff_record_count": trailing_all_ff,
        "literal_category_as_one_patent_sequence_has_early_terminator_conflict": bool(
            later_non_all_ff
        ),
        "raw_record_bytes_emitted": False,
    }


def _profile_audit(
    *,
    profile_id: str,
    payload: bytes,
    category_count: int,
    has_outer_zero_sentinel: bool,
    source: dict[str, Any],
) -> dict[str, Any]:
    body, categories, sentinel = _split_records(
        payload,
        profile_id=profile_id,
        category_count=category_count,
        has_outer_zero_sentinel=has_outer_zero_sentinel,
    )
    records = [record for category in categories for record in category]
    active_records = [record for record in records if record != b"\xff" * RECORD_BYTES]
    _require(active_records, f"{profile_id} unexpectedly has no non-FF records")

    all_selector_counts = _selector_counts(records)
    active_selector_counts = _selector_counts(active_records)
    timing_values = {
        8: [record[8] for record in records],
        9: [record[9] for record in records],
        10: [record[10] for record in records],
    }
    active_timing_values = {
        8: [record[8] for record in active_records],
        9: [record[9] for record in active_records],
        10: [record[10] for record in active_records],
    }
    category_summaries = [
        _category_boundary_summary(index, category)
        for index, category in enumerate(categories)
    ]
    categories_without_boundary_ff_ff = [
        item["category_index"]
        for item in category_summaries
        if item["first_record_boundary_with_ff_ff"] is None
    ]
    categories_with_early_terminator_conflict = [
        item["category_index"]
        for item in category_summaries
        if item["literal_category_as_one_patent_sequence_has_early_terminator_conflict"]
    ]

    active_starting_ff_ff = [
        record for record in active_records if record[:2] == b"\xff\xff"
    ]
    active_starting_single_ff = [
        record for record in active_records if record[0] == 0xFF and record[1] != 0xFF
    ]
    active_all_timing_ff = [
        record for record in active_records if record[8:] == b"\xff\xff\xff"
    ]
    active_all_selector_ff = [
        record for record in active_records if record[:8] == b"\xff" * 8
    ]
    code_3_count = active_selector_counts["3"]

    return {
        "profile_id": profile_id,
        "identity": {
            "bytes": len(payload),
            "sha256": _sha256(payload),
            "body_bytes": len(body),
            "body_sha256": _sha256(body),
            "source": source,
        },
        "local_geometry": {
            "header_bytes": HEADER_BYTES,
            "category_count": category_count,
            "bytes_per_category": CATEGORY_BYTES,
            "records_per_category": RECORDS_PER_CATEGORY,
            "bytes_per_record": RECORD_BYTES,
            "record_count": len(records),
            "non_all_ff_record_count": len(active_records),
            "all_ff_record_count": len(records) - len(active_records),
            "outer_sentinel": sentinel,
        },
        "patent_selector_projection": {
            "projected_bytes": "record[0:8]",
            "selectors_per_record": 32,
            "high_bits_first_within_each_byte": True,
            "all_records_code_counts": all_selector_counts,
            "non_all_ff_records_code_counts": active_selector_counts,
            "non_all_ff_selector_count": len(active_records) * 32,
            "unassigned_code_3_count_in_non_all_ff_records": code_3_count,
            "unassigned_code_3_present_in_non_all_ff_records": code_3_count > 0,
            "non_all_ff_records_with_all_32_selectors_code_3": len(
                active_all_selector_ff
            ),
            "literal_three_level_example_completely_decodes_local_selectors": (
                code_3_count == 0
            ),
            "drive_state_mapping_proven_for_spd1657": False,
        },
        "patent_timing_position_projection": {
            "all_records": {
                "byte_8": _position_summary(
                    timing_values[8], hypothesis="display row time"
                ),
                "byte_9": _position_summary(
                    timing_values[9], hypothesis="inter-frame delay"
                ),
                "byte_10": _position_summary(
                    timing_values[10], hypothesis="frame count"
                ),
            },
            "non_all_ff_records": {
                "byte_8": _position_summary(
                    active_timing_values[8], hypothesis="display row time"
                ),
                "byte_9": _position_summary(
                    active_timing_values[9], hypothesis="inter-frame delay"
                ),
                "byte_10": _position_summary(
                    active_timing_values[10], hypothesis="frame count"
                ),
            },
            "non_all_ff_records_with_all_three_projected_timing_bytes_ff": len(
                active_all_timing_ff
            ),
            "timing_units_or_valid_ranges_stated_for_spd1657": False,
        },
        "patent_escape_and_terminator_projection": {
            "non_all_ff_records_starting_ff_ff": len(active_starting_ff_ff),
            "non_all_ff_records_starting_single_ff_then_non_ff": len(
                active_starting_single_ff
            ),
            "categories_with_any_record_boundary_ff_ff": sum(
                item["first_record_boundary_with_ff_ff"] is not None
                for item in category_summaries
            ),
            "category_indices_without_record_boundary_ff_ff": (
                categories_without_boundary_ff_ff
            ),
            "category_indices_with_non_all_ff_after_first_boundary_ff_ff": (
                categories_with_early_terminator_conflict
            ),
            "all_observed_all_ff_records_are_trailing_within_each_category": all(
                item["all_ff_record_count"] == item["trailing_all_ff_record_count"]
                for item in category_summaries
            ),
            "observed_boundary_ff_ff_never_precedes_a_later_non_all_ff_record": (
                not categories_with_early_terminator_conflict
            ),
            "body_ends_with_ff_ff": body.endswith(b"\xff\xff"),
            "category_summaries": category_summaries,
            "literal_patent_parser_applicability_proven": False,
            "category_is_one_independent_patent_sequence_proven": False,
        },
        "raw_header_body_record_key_or_plaintext_emitted": False,
    }


def build_report() -> dict[str, Any]:
    facts_sha256 = _canonical_json_sha256(PRIMARY_PATENT_FACTS)
    _require(
        facts_sha256 == PRIMARY_PATENT_FACTS_SHA256,
        "primary patent fact contract changed",
    )

    materials = {
        profile_id: profile_pack.load_profile(profile_id)
        for profile_id in ("WF20_25", "WF23_25")
    }
    legacy, labels, legacy_source = geometry_audit._load_legacy()
    _require(
        labels == ["VCOM", "Black", "White", "Yellow", "Red", "Power"],
        "legacy labels changed",
    )

    profiles = {
        profile_id: _profile_audit(
            profile_id=profile_id,
            payload=material.plaintext,
            category_count=VENDOR_CATEGORY_COUNT,
            has_outer_zero_sentinel=True,
            source={
                "path": material.spec.source_relative.as_posix(),
                "source_sha256": material.spec.source_sha256,
                "wrapper_sha256": material.wrapper_sha256,
                "plaintext_sha256": material.spec.plaintext_sha256,
                "identity_checked_by_vendor_profile_pack": True,
            },
        )
        for profile_id, material in materials.items()
    }
    profiles["legacy535"] = _profile_audit(
        profile_id="legacy535",
        payload=legacy,
        category_count=LEGACY_CATEGORY_COUNT,
        has_outer_zero_sentinel=False,
        source={
            **legacy_source,
            "category_labels": labels,
            "identity_checked_by_phase_geometry_audit": True,
        },
    )

    literal_example_decodes_every_profile = all(
        profile["patent_selector_projection"][
            "literal_three_level_example_completely_decodes_local_selectors"
        ]
        for profile in profiles.values()
    )
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": "offline_identity_pinned_metadata_only_hypothesis_test",
        "primary_patent": {
            **PRIMARY_PATENT_FACTS,
            "facts_canonical_sha256": facts_sha256,
            "pdf_downloaded_or_network_accessed_by_this_offline_tool": False,
            "facts_are_manual_transcription_from_primary_patent": True,
        },
        "profiles": profiles,
        "adjudication": {
            "exact_record_width_match": True,
            "local_candidates_are_same_philips_apollo_format_proven": False,
            "local_candidates_are_spd1657_field_abi_proven": False,
            "literal_three_level_example_decodes_every_local_selector": (
                literal_example_decodes_every_profile
            ),
            "observed_all_ff_padding_is_positionally_compatible_with_an_optional_trailing_terminator": all(
                profile["patent_escape_and_terminator_projection"][
                    "all_observed_all_ff_records_are_trailing_within_each_category"
                ]
                and profile["patent_escape_and_terminator_projection"][
                    "observed_boundary_ff_ff_never_precedes_a_later_non_all_ff_record"
                ]
                for profile in profiles.values()
            ),
            "fixed_eight_record_category_structure_decisively_contradicts_optional_ff_ff_terminator": False,
            "fixed_eight_record_category_structure_proves_optional_ff_ff_terminator": False,
            "terminator_structure_reason": (
                "every observed all-FF record is trailing within its local category, "
                "but some categories have no boundary FF FF, the patent makes the "
                "terminator optional, and a local category is not proven to be one "
                "Philips display sequence"
            ),
            "ff_ff_has_same_terminator_meaning_locally_proven": False,
            "single_ff_has_same_hardware_shaking_meaning_locally_proven": False,
            "bytes_8_9_10_have_patent_timing_semantics_locally_proven": False,
            "category_or_group_is_a_patent_sequence_or_frame_proven": False,
            "compatibility_class": (
                "width_and_trailing_ff_alignment_are_structural_clues_only_not_spd1657_abi_proof"
            ),
            "safe_use": (
                "retain the 11-byte patent layout only as a comparison hypothesis for "
                "future same-build decoder or SPI/readback evidence"
            ),
            "must_not_use_for": [
                "renaming local fields",
                "assigning local voltage levels or timing units",
                "editing or generating LUT payloads",
                "authorizing a visible refresh",
            ],
        },
        "safety": {
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "device_network_accessed": False,
            "firmware_written_or_flashed": False,
            "visible_refresh_attempted": False,
            "runtime_or_recovery_release_modified": False,
            "runtime_payload_created_or_modified": False,
            "raw_waveform_key_or_plaintext_emitted": False,
        },
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Emit a metadata-only comparison of local 11-byte groups with "
            "US20070085819A1."
        )
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _parse_args(argv)
    try:
        report = build_report()
    except (
        Patent11ByteAuditError,
        profile_pack.ProfilePackError,
        geometry_audit.PhaseGeometryAuditError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
