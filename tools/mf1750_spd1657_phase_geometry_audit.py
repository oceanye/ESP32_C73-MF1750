#!/usr/bin/env python3
"""Audit SPD1657 candidate LUT geometry without assigning phase semantics.

This tool is deliberately metadata-only and offline.  It identity-checks the
two decoded vendor profiles and the labeled legacy 535-byte table, then emits
byte/nibble distributions, exact group equality, and cross-profile deltas.  It
does not emit waveform bytes, infer voltage or duration fields, access hardware,
or construct a runtime payload.

The repeated 11-byte width is a proven record boundary in these local files.
It is *not* proof that the records use SPD1656's 11-byte VCOM ABI.  SPD1656
uses 20x11 bytes for VCOM but 20x13 bytes for each 3-bit color LUT, while these
SPD1657/E2802 candidates use 8x11 bytes under every labeled/indexed category.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Final, Iterable

from tools import e2802_r43_lut_proof as iar_proof
from tools import mf1750_spd1657_reverse_delta as reverse_delta
from tools import mf1750_spd1657_vendor_profile_pack as profile_pack


KIND: Final = "mf1750-spd1657-phase-geometry-audit"
SCHEMA_VERSION: Final = 1
REPO_ROOT: Final = Path(__file__).resolve().parents[1]
REFERENCE_ROOT: Final = profile_pack.DEFAULT_REFERENCE_ROOT
LEGACY_SOURCE: Final = REFERENCE_ROOT / "User" / "EDP_init.c"
LEGACY_SOURCE_SHA256: Final = (
    "1b6bbcf35cefc338f7ab9b76c04c869f9a82e800c4ccaa52d204d9fd6e53b7a5"
)
LEGACY_LUT_SHA256: Final = (
    "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b"
)
SPD1656_MANUAL: Final = REPO_ROOT / "参考资料" / "Solomon-SPD1656.pdf"
SPD1656_MANUAL_SHA256: Final = (
    "1f3f5db0600ee6e8133a4c31f9a3f59c1b5bfcc1a916be98ae848ec64581de07"
)

HEADER_BYTES: Final = 7
GROUP_BYTES: Final = 11
GROUPS_PER_CATEGORY: Final = 8
CATEGORY_BYTES: Final = GROUP_BYTES * GROUPS_PER_CATEGORY
PROFILE_CATEGORIES: Final = 9
LEGACY_CATEGORIES: Final = 6

SPD1656_SOURCE_COMMIT: Final = "01356147a9a5e10c1599908d636b4776277766a3"
SPD1656_SOURCE_BASE: Final = (
    "https://github.com/ts-manuel/Understanding-ACeP-Tecnology/blob/"
    + SPD1656_SOURCE_COMMIT
    + "/matlab/"
)
SPD1656_SOURCE_HASHES: Final = {
    "read_flash.m": "47435968aa1d46c5231e7e9734186f0c059cd9993cadb8b9570773dea7eaeb40",
    "lutv2wave.m": "ef44108d55f5de8f2c036a3c136a449c240d901193a9db672fea407282ae5076",
    "lutc2wave.m": "0c9c3fd6247c9692a9a8b28aeaa80e265d117a605b61a148fdd5cc6663cdb948",
}


class PhaseGeometryAuditError(RuntimeError):
    """Raised when frozen local evidence no longer matches the audit."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PhaseGeometryAuditError(message)


def _histogram(values: Iterable[int], width: int = 2) -> dict[str, int]:
    counts = Counter(values)
    return {f"{value:0{width}X}": counts[value] for value in sorted(counts)}


def _nibble_histogram(payload: bytes) -> dict[str, dict[str, int]]:
    upper = Counter(value >> 4 for value in payload)
    lower = Counter(value & 0x0F for value in payload)
    combined = upper + lower

    def render(counts: Counter[int]) -> dict[str, int]:
        return {f"{value:X}": counts[value] for value in range(16)}

    return {
        "upper": render(upper),
        "lower": render(lower),
        "combined": render(combined),
    }


def _two_bit_projection(payload: bytes) -> dict[str, Any]:
    counts: Counter[int] = Counter()
    for value in payload:
        counts.update(((value >> 6) & 3, (value >> 4) & 3, (value >> 2) & 3, value & 3))
    return {
        "classification": "structural_projection_only",
        "counts": {str(value): counts[value] for value in range(4)},
        "drive_state_mapping_proven": False,
    }


def _group_rows(body: bytes, category_count: int) -> list[list[bytes]]:
    _require(
        len(body) == category_count * CATEGORY_BYTES,
        "category body geometry changed",
    )
    return [
        [
            body[
                category * CATEGORY_BYTES + group * GROUP_BYTES : category
                * CATEGORY_BYTES
                + (group + 1) * GROUP_BYTES
            ]
            for group in range(GROUPS_PER_CATEGORY)
        ]
        for category in range(category_count)
    ]


def _position_statistics(groups: list[bytes]) -> list[dict[str, Any]]:
    return [
        {
            "byte_index": byte_index,
            "ff_count": values.count(0xFF),
            "zero_count": values.count(0x00),
            "unique_value_count": len(set(values)),
            "value_histogram": _histogram(values),
            "upper_nibble_histogram": _histogram(
                (value >> 4 for value in values), width=1
            ),
            "lower_nibble_histogram": _histogram(
                (value & 0x0F for value in values), width=1
            ),
        }
        for byte_index in range(GROUP_BYTES)
        for values in [[group[byte_index] for group in groups]]
    ]


def _duplicate_group_clusters(rows: list[list[bytes]]) -> list[dict[str, Any]]:
    coordinates: defaultdict[bytes, list[list[int]]] = defaultdict(list)
    for category_index, category in enumerate(rows):
        for group_index, group in enumerate(category):
            coordinates[group].append([category_index, group_index])
    clusters = [
        {
            "sha256": _sha256(group),
            "coordinates": coords,
            "all_ff": group == b"\xff" * GROUP_BYTES,
        }
        for group, coords in coordinates.items()
        if len(coords) > 1
    ]
    return sorted(
        clusters,
        key=lambda item: (
            not bool(item["all_ff"]),
            item["coordinates"][0],
            str(item["sha256"]),
        ),
    )


def _profile_statistics(
    *,
    profile_id: str,
    full_payload: bytes,
    category_count: int,
    category_labels: list[str] | None,
    sentinel_offset: int | None,
) -> dict[str, Any]:
    _require(len(full_payload) >= HEADER_BYTES, f"{profile_id} is shorter than header")
    body_end = HEADER_BYTES + category_count * CATEGORY_BYTES
    _require(
        len(full_payload) == body_end + (1 if sentinel_offset is not None else 0),
        f"{profile_id} total geometry changed",
    )
    if sentinel_offset is not None:
        _require(sentinel_offset == body_end, f"{profile_id} sentinel offset changed")

    header = full_payload[:HEADER_BYTES]
    body = full_payload[HEADER_BYTES:body_end]
    rows = _group_rows(body, category_count)
    flat_groups = [group for category in rows for group in category]
    categories: list[dict[str, Any]] = []
    for category_index, (category_payload, groups) in enumerate(
        zip(
            (
                body[index * CATEGORY_BYTES : (index + 1) * CATEGORY_BYTES]
                for index in range(category_count)
            ),
            rows,
        )
    ):
        categories.append(
            {
                "index": category_index,
                "label": (
                    category_labels[category_index]
                    if category_labels is not None
                    else None
                ),
                "bytes": len(category_payload),
                "sha256": _sha256(category_payload),
                "ff_count": category_payload.count(0xFF),
                "zero_count": category_payload.count(0x00),
                "all_ff": category_payload == b"\xff" * CATEGORY_BYTES,
                "not_all_ff_group_indices": [
                    index
                    for index, group in enumerate(groups)
                    if group != b"\xff" * GROUP_BYTES
                ],
                "position_statistics_across_eight_groups": _position_statistics(groups),
                "groups": [
                    {
                        "index": group_index,
                        "bytes": len(group),
                        "sha256": _sha256(group),
                        "ff_count": group.count(0xFF),
                        "zero_count": group.count(0x00),
                        "non_ff_count": len(group) - group.count(0xFF),
                        "unique_value_count": len(set(group)),
                        "all_ff": group == b"\xff" * GROUP_BYTES,
                        "byte_histogram": _histogram(group),
                        "nibble_histogram": _nibble_histogram(group),
                    }
                    for group_index, group in enumerate(groups)
                ],
            }
        )

    result: dict[str, Any] = {
        "profile_id": profile_id,
        "bytes": len(full_payload),
        "sha256": _sha256(full_payload),
        "header": {"bytes": HEADER_BYTES, "sha256": _sha256(header)},
        "body": {
            "bytes": len(body),
            "sha256": _sha256(body),
            "category_count": category_count,
            "groups_per_category": GROUPS_PER_CATEGORY,
            "bytes_per_group": GROUP_BYTES,
            "group_count": len(flat_groups),
            "ff_count": body.count(0xFF),
            "zero_count": body.count(0x00),
            "byte_histogram": _histogram(body),
            "nibble_histogram": _nibble_histogram(body),
            "two_bit_projection": _two_bit_projection(body),
            "first_byte_histogram_across_groups": _histogram(
                group[0] for group in flat_groups
            ),
            "first_byte_zero_count": sum(group[0] == 0 for group in flat_groups),
            "all_ff_group_count": sum(
                group == b"\xff" * GROUP_BYTES for group in flat_groups
            ),
            "all_ff_group_coordinates": [
                [category_index, group_index]
                for category_index, category in enumerate(rows)
                for group_index, group in enumerate(category)
                if group == b"\xff" * GROUP_BYTES
            ],
            "position_statistics_across_all_groups": _position_statistics(flat_groups),
            "duplicate_group_clusters": _duplicate_group_clusters(rows),
        },
        "categories": categories,
        "raw_header_or_body_bytes_emitted": False,
    }
    if sentinel_offset is None:
        result["sentinel"] = {
            "present": False,
            "reason": "legacy 535-byte declaration ends after six 88-byte categories",
        }
    else:
        sentinel = full_payload[sentinel_offset]
        result["sentinel"] = {
            "present": True,
            "offset": sentinel_offset,
            "outside_group_body": sentinel_offset == body_end,
            "is_zero": sentinel == 0,
            "included_in_any_11_byte_group": False,
        }
    return result


def _load_legacy() -> tuple[bytes, list[str], dict[str, Any]]:
    source = LEGACY_SOURCE.read_bytes()
    _require(
        _sha256(source) == LEGACY_SOURCE_SHA256,
        "legacy EDP_init.c identity changed",
    )
    legacy = reverse_delta._extract_initializer(source, "wf_data")
    _require(len(legacy) == 535, "legacy wf_data length changed")
    _require(_sha256(legacy) == LEGACY_LUT_SHA256, "legacy wf_data identity changed")

    source_text = source.decode("latin-1")
    declaration = re.search(r"\bwf_data\s*\[\s*535\s*\]\s*=", source_text)
    _require(declaration is not None, "legacy wf_data declaration disappeared")
    body = reverse_delta._extract_braced_body(
        source_text, declaration.start(), "legacy wf_data"
    )
    labels: list[str] = []
    for label in re.findall(r"//\s*(VCOM|Black|White|Yellow|Red|Power)-GROUP1\b", body):
        if label not in labels:
            labels.append(label)
    _require(
        labels == ["VCOM", "Black", "White", "Yellow", "Red", "Power"],
        "legacy category labels changed",
    )
    return (
        legacy,
        labels,
        {
            "source_path": LEGACY_SOURCE.relative_to(REPO_ROOT).as_posix(),
            "source_bytes": len(source),
            "source_sha256": _sha256(source),
            "initializer_sha256": _sha256(legacy),
            "labels_are_vendor_comments": True,
        },
    )


def _compare_profiles(
    left_name: str,
    left: bytes,
    left_categories: int,
    right_name: str,
    right: bytes,
    right_categories: int,
    *,
    include_common_trailing_sentinel: bool = False,
) -> dict[str, Any]:
    common_categories = min(left_categories, right_categories)
    common_body_bytes = common_categories * CATEGORY_BYTES
    left_body = left[HEADER_BYTES : HEADER_BYTES + common_body_bytes]
    right_body = right[HEADER_BYTES : HEADER_BYTES + common_body_bytes]
    left_rows = _group_rows(left_body, common_categories)
    right_rows = _group_rows(right_body, common_categories)

    groups = [
        {
            "category_index": category,
            "group_index": group,
            "equal": left_rows[category][group] == right_rows[category][group],
            "different_byte_count": sum(
                a != b
                for a, b in zip(left_rows[category][group], right_rows[category][group])
            ),
        }
        for category in range(common_categories)
        for group in range(GROUPS_PER_CATEGORY)
    ]
    sentinel_equal = None
    if include_common_trailing_sentinel:
        left_offset = HEADER_BYTES + left_categories * CATEGORY_BYTES
        right_offset = HEADER_BYTES + right_categories * CATEGORY_BYTES
        _require(
            left_offset < len(left) and right_offset < len(right),
            "requested sentinel comparison is out of range",
        )
        sentinel_equal = left[left_offset] == right[right_offset]

    header_equal = sum(
        a == b for a, b in zip(left[:HEADER_BYTES], right[:HEADER_BYTES])
    )
    body_equal = sum(a == b for a, b in zip(left_body, right_body))
    return {
        "left": left_name,
        "right": right_name,
        "common_category_count": common_categories,
        "compared_header_bytes": HEADER_BYTES,
        "equal_header_positions": header_equal,
        "compared_body_bytes": common_body_bytes,
        "equal_body_positions": body_equal,
        "different_body_positions": common_body_bytes - body_equal,
        "trailing_sentinel_compared": include_common_trailing_sentinel,
        "trailing_sentinel_equal": sentinel_equal,
        "equal_positions_in_compared_header_body_and_optional_sentinel": (
            header_equal + body_equal + (1 if sentinel_equal else 0)
        ),
        "category_different_byte_counts": [
            sum(
                a != b
                for a, b in zip(
                    left_body[index * CATEGORY_BYTES : (index + 1) * CATEGORY_BYTES],
                    right_body[index * CATEGORY_BYTES : (index + 1) * CATEGORY_BYTES],
                )
            )
            for index in range(common_categories)
        ],
        "different_byte_counts_by_group_byte_index": [
            sum(
                left_rows[category][group][byte_index]
                != right_rows[category][group][byte_index]
                for category in range(common_categories)
                for group in range(GROUPS_PER_CATEGORY)
            )
            for byte_index in range(GROUP_BYTES)
        ],
        "exact_equal_group_coordinates": [
            [item["category_index"], item["group_index"]]
            for item in groups
            if item["equal"]
        ],
        "groups": groups,
    }


def _loader_forwarding_evidence() -> dict[str, Any]:
    library = reverse_delta._audit_library(REFERENCE_ROOT)
    source_path = REFERENCE_ROOT / "Sample Code" / "E28xx.c"
    source = source_path.read_bytes()
    source_text = source.decode("latin-1")
    write_epd = reverse_delta._extract_function(source_text, "writeEPD")
    send_multiple = reverse_delta._extract_function(source_text, "sendMutipleSPIData")
    adapter_forwards_pointer_and_length = (
        re.search(
            r"sendSPICommand\s*\(\s*spi_c\s*\)\s*;.*"
            r"sendMutipleSPIData\s*\(\s*spi_d\s*,\s*len\s*\)\s*;",
            write_epd,
            flags=re.DOTALL,
        )
        is not None
    )
    bulk_is_incrementing_byte_loop = (
        re.search(
            r"for\s*\([^;]*;\s*i\s*<\s*counter\s*;[^)]*\).*"
            r"sendSPIData\s*\(\s*\*\s*data\s*\)\s*;.*"
            r"data\s*\+\+\s*;",
            send_multiple,
            flags=re.DOTALL,
        )
        is not None
    )
    _require(adapter_forwards_pointer_and_length, "delivered writeEPD shape changed")
    _require(bulk_is_incrementing_byte_loop, "delivered bulk SPI loop changed")

    iar = iar_proof.prove_object()
    object_payload = iar_proof.DEFAULT_OBJECT_PATH.read_bytes()
    section_records = iar_proof._source_records(
        object_payload, start=0x1648E, end=0x16B80
    )
    record_summary = [
        {
            "file_offset": f"0x{int(record['file_offset']):X}",
            "source_line": int(record["source_line"]),
            "source": str(record["source"]),
        }
        for record in section_records
    ]
    _require(
        [item["source_line"] for item in record_summary]
        == [342, 342, 343, 345, 345, 343],
        "legacy EPD_Load_LUT source-annotated control flow changed",
    )

    return {
        "current_armcc": {
            "library_path": library["path"],
            "library_sha256": library["sha256"],
            "loadwf_code_sha256": library["formal_loader_bindings"]["loadwf_code"][
                "sha256"
            ],
            "writeepd_call_count": sum(
                entry["symbol_name"] == "writeEPD"
                for entry in library["formal_loader_bindings"]["relocation_section"][
                    "entries"
                ]
            ),
            "delivered_adapter_source_path": source_path.relative_to(
                REPO_ROOT
            ).as_posix(),
            "delivered_adapter_source_sha256": _sha256(source),
            "writeepd_forwards_original_pointer_and_length": (
                adapter_forwards_pointer_and_length
            ),
            "bulk_writer_reads_one_byte_then_increments_pointer": (
                bulk_is_incrementing_byte_loop
            ),
            "record_reordering_in_delivered_adapter_observed": False,
            "scope_limit": (
                "the linked library calls an external writeEPD; sequential identity is "
                "proven for the delivered adapter source, not every possible replacement"
            ),
        },
        "legacy_iar_e2802": {
            "object_path": iar["object"]["relative_path"],
            "object_sha256": iar["object"]["sha256"],
            "upload_lut0": iar["upload_temperature_lut"]["lut0"],
            "epd_load_lut_section_id": "0x1D",
            "epd_load_lut_section_marker_file_offset": "0x1648E",
            "source_annotated_control_flow": record_summary,
            "only_direct_callees_observed_in_section": ["SPI_COMMANDs", "SPI_DATAs"],
            "loop_and_single_byte_spi_forwarding_supported": True,
            "inline_byte_identity_and_pointer_increment_fully_disassembled": False,
            "record_reordering_observed": False,
        },
        "conclusion": (
            "current delivered glue is an ordered opaque byte stream; the old IAR path "
            "also supports a forwarding loop but is not used to assign record fields"
        ),
    }


def _spd1656_negative_evidence(profiles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    manual = SPD1656_MANUAL.read_bytes()
    _require(
        _sha256(manual) == SPD1656_MANUAL_SHA256,
        "local SPD1656 manual identity changed",
    )
    return {
        "local_manual": {
            "path": SPD1656_MANUAL.relative_to(REPO_ROOT).as_posix(),
            "bytes": len(manual),
            "sha256": _sha256(manual),
            "revision": "SPD1656 Rev 1.1, Jan 2020",
            "relevant_pages": [13, 15, 17, 27, 28, 29],
        },
        "published_spd1656_geometry": {
            "vcom_command": "0x20",
            "vcom_bytes": 220,
            "vcom_formula": "20 groups * 11 bytes",
            "vcom_record_fields": (
                "repeat byte + two packed 2-bit level bytes + eight frame counts"
            ),
            "color_commands": "0x21..0x28",
            "bytes_per_color_lut": 260,
            "color_formula": "20 groups * 13 bytes",
            "color_record_fields": (
                "repeat byte + four packed 3-bit-in-nibble level bytes + eight frame counts"
            ),
        },
        "third_party_reverse_engineering_source_code": {
            "commit": SPD1656_SOURCE_COMMIT,
            "files": {
                name: {
                    "url": SPD1656_SOURCE_BASE + name,
                    "sha256": digest,
                }
                for name, digest in SPD1656_SOURCE_HASHES.items()
            },
            "read_flash_passes_raw_slices_without_complement": True,
            "lutv2wave_consumes_20_by_11": True,
            "lutc2wave_consumes_20_by_13": True,
            "network_fetched_or_executed_by_this_offline_tool": False,
        },
        "local_first_byte_zero_counts": {
            profile_id: profile["body"]["first_byte_zero_count"]
            for profile_id, profile in profiles.items()
        },
        "compatibility_conclusion": {
            "same_11_byte_width_as_spd1656_vcom_is_geometry_only": True,
            "local_11_byte_rows_cover_non_vcom_categories": True,
            "direct_spd1656_vcom_parser_transfer_proven": False,
            "direct_spd1656_color_parser_transfer_proven": False,
            "bitwise_complement_is_part_of_spd1656_parser": False,
            "bitwise_complement_is_valid_spd1657_decoder_proven": False,
            "repeat_level_or_frame_count_semantics_transfer_proven": False,
        },
    }


def build_report() -> dict[str, Any]:
    materials = {
        profile_id: profile_pack.load_profile(profile_id)
        for profile_id in ("WF20_25", "WF23_25")
    }
    legacy, labels, legacy_source = _load_legacy()
    payloads = {
        profile_id: material.plaintext for profile_id, material in materials.items()
    }
    payloads["legacy535"] = legacy
    profiles = {
        profile_id: _profile_statistics(
            profile_id=profile_id,
            full_payload=material.plaintext,
            category_count=PROFILE_CATEGORIES,
            category_labels=None,
            sentinel_offset=799,
        )
        for profile_id, material in materials.items()
    }
    profiles["legacy535"] = _profile_statistics(
        profile_id="legacy535",
        full_payload=legacy,
        category_count=LEGACY_CATEGORIES,
        category_labels=labels,
        sentinel_offset=None,
    )
    profiles["legacy535"]["source"] = legacy_source

    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": "offline_metadata_only_no_payload_generation",
        "safety": {
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "device_network_accessed": False,
            "firmware_written_or_flashed": False,
            "visible_refresh_attempted": False,
            "runtime_payload_created_or_modified": False,
            "raw_waveform_bytes_emitted": False,
        },
        "profiles": profiles,
        "comparisons": {
            "WF20_25_vs_WF23_25": _compare_profiles(
                "WF20_25",
                payloads["WF20_25"],
                PROFILE_CATEGORIES,
                "WF23_25",
                payloads["WF23_25"],
                PROFILE_CATEGORIES,
                include_common_trailing_sentinel=True,
            ),
            "WF20_25_vs_legacy535_first_six_categories": _compare_profiles(
                "WF20_25",
                payloads["WF20_25"],
                PROFILE_CATEGORIES,
                "legacy535",
                payloads["legacy535"],
                LEGACY_CATEGORIES,
            ),
            "WF23_25_vs_legacy535_first_six_categories": _compare_profiles(
                "WF23_25",
                payloads["WF23_25"],
                PROFILE_CATEGORIES,
                "legacy535",
                payloads["legacy535"],
                LEGACY_CATEGORIES,
            ),
        },
        "loader_forwarding_evidence": _loader_forwarding_evidence(),
        "spd1656_relation": _spd1656_negative_evidence(profiles),
        "bounded_mode1_interpretation": {
            "evidence_class": "B_structural_geometry_plus_C_semantic_cross_consistency",
            "direct_geometry": {
                "formula": "9 categories * 8 groups * 11 bytes",
                "supports_vcom_plus_eight_target_categories_model": True,
                "all_ff_category_indices_in_both_vendor_profiles": [5, 8],
            },
            "conditional_mapping_only": {
                "assumption": (
                    "category 0 is VCOM and categories 1..8 map in order to target "
                    "codes 0..7"
                ),
                "then_all_ff_target_codes": [4, 7],
                "compatible_with_six_color_and_otp_code_4_equals_7_context": True,
                "direct_abi_or_loader_proof": False,
            },
            "counterweight": {
                "legacy_mode0_category_5_vendor_label": "Power",
                "same_generation_mode1_loader_present": False,
                "therefore_unique_category_to_pixel_code_mapping_proven": False,
            },
            "use_limit": (
                "retain as cross-version structural consistency only; do not use it to "
                "name fields, assign voltages or durations, or generate a new payload"
            ),
        },
        "semantic_boundary": {
            "proven": {
                "profile_formula": "7 + 9 * (8 * 11) + 1",
                "legacy_formula": "7 + 6 * (8 * 11)",
                "legacy_category_labels": labels,
                "profile_sentinel_is_zero_and_outside_group_body": True,
                "groups_are_forwarded_as_part_of_an_ordered_byte_stream_by_delivered_glue": True,
            },
            "not_proven": {
                "group_is_a_chronological_phase_record": True,
                "any_byte_is_repeat_or_duration": True,
                "any_nibble_or_two_bit_projection_is_a_drive_level": True,
                "ff_means_disabled_end_skip_or_no_op": True,
                "zero_has_a_group_field_meaning": True,
                "bitwise_complement_is_the_controller_decoder": True,
                "category_index_maps_uniquely_to_a_pixel_code_or_color": True,
                "spd1656_field_semantics_apply_to_spd1657": True,
            },
            "wording_rule": (
                "call these 11-byte groups/records, not phases, until an SPD1657 field "
                "definition, same-build decoder, or decisive SPI/readback evidence exists"
            ),
        },
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit metadata-only SPD1657 category/group geometry evidence."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _parse_args(argv)
    try:
        report = build_report()
    except (
        PhaseGeometryAuditError,
        profile_pack.ProfilePackError,
        reverse_delta.ReverseAuditError,
        iar_proof.ProofError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
