#!/usr/bin/env python3
"""Localize WF20/WF23 opaque profile changes for colour experiments.

This offline audit compares the two identity-pinned, decoded 800-byte vendor
profiles without emitting their bytes or assigning LUT field semantics.  It
separates the seven-byte prefix, the 9 x 8 x 11-byte structural body, and the
trailing byte; reports per-block and per-record change counts; and states the
matched-control design needed to distinguish profile-dependent colour effects
from prefix-derived PWR changes.

It does not build a waveform, splice profiles, access hardware, or authorize a
visible refresh.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Final, Iterable


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.application.durable_io import (  # noqa: E402
    DurableWriteError,
    write_new_bytes_durable,
)
from tools import mf1750_spd1657_vendor_profile_pack as profile_pack  # noqa: E402


KIND: Final = "mf1750-spd1657-profile-color-delta"
SCHEMA_VERSION: Final = 1
PROFILE_IDS: Final = ("WF20_25", "WF23_25")
PROFILE_BYTES: Final = 800
PREFIX_BYTES: Final = 7
BLOCK_COUNT: Final = 9
RECORDS_PER_BLOCK: Final = 8
RECORD_BYTES: Final = 11
BLOCK_BYTES: Final = RECORDS_PER_BLOCK * RECORD_BYTES
BODY_BYTES: Final = BLOCK_COUNT * BLOCK_BYTES
SUFFIX_BYTES: Final = 1
R20_BYTES: Final = 799
R21_BYTES: Final = 704
R21_SHA256: Final = "24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f"


class ProfileColorDeltaError(RuntimeError):
    """Raised when a frozen identity or comparison invariant changes."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProfileColorDeltaError(message)


def _ranges(indices: Iterable[int], *, unit: str) -> list[dict[str, Any]]:
    ordered = sorted(set(indices))
    if not ordered:
        return []
    rows: list[dict[str, Any]] = []
    start = previous = ordered[0]
    for value in ordered[1:]:
        if value == previous + 1:
            previous = value
            continue
        rows.append(
            {
                "start": start,
                "end_exclusive": previous + 1,
                "count": previous - start + 1,
                "unit": unit,
            }
        )
        start = previous = value
    rows.append(
        {
            "start": start,
            "end_exclusive": previous + 1,
            "count": previous - start + 1,
            "unit": unit,
        }
    )
    return rows


def _difference_indices(left: bytes, right: bytes) -> list[int]:
    _require(len(left) == len(right), "comparison lengths differ")
    return [index for index, pair in enumerate(zip(left, right)) if pair[0] != pair[1]]


def _comparison(left: bytes, right: bytes, *, unit: str = "byte") -> dict[str, Any]:
    different = _difference_indices(left, right)
    different_set = set(different)
    equal = [index for index in range(len(left)) if index not in different_set]
    return {
        "bytes": len(left),
        "equal_byte_positions": len(equal),
        "different_byte_positions": len(different),
        "equal_position_ranges": _ranges(equal, unit=unit),
        "different_position_ranges": _ranges(different, unit=unit),
        "raw_byte_values_emitted": False,
    }


def _records(payload: bytes) -> list[bytes]:
    _require(len(payload) % RECORD_BYTES == 0, "body is not record aligned")
    return [
        payload[offset : offset + RECORD_BYTES]
        for offset in range(0, len(payload), RECORD_BYTES)
    ]


def _load_profiles() -> tuple[
    profile_pack.ProfileMaterial, profile_pack.ProfileMaterial
]:
    materials = tuple(
        profile_pack.load_profile(profile_id) for profile_id in PROFILE_IDS
    )
    for profile_id, material in zip(PROFILE_IDS, materials):
        _require(material.spec.profile_id == profile_id, "profile order changed")
        _require(len(material.plaintext) == PROFILE_BYTES, f"{profile_id} size changed")
        _require(
            _sha256(material.plaintext) == material.spec.plaintext_sha256,
            f"{profile_id} decoded identity changed",
        )
    _require(
        PREFIX_BYTES + BODY_BYTES + SUFFIX_BYTES == PROFILE_BYTES,
        "profile geometry changed",
    )
    return materials  # type: ignore[return-value]


def _body_report(left: bytes, right: bytes) -> dict[str, Any]:
    left_records = _records(left)
    right_records = _records(right)
    _require(
        len(left_records) == len(right_records) == BLOCK_COUNT * RECORDS_PER_BLOCK,
        "record count changed",
    )

    per_record_differences = [
        sum(a != b for a, b in zip(left_record, right_record))
        for left_record, right_record in zip(left_records, right_records)
    ]
    exact_equal_records = [
        index for index, count in enumerate(per_record_differences) if count == 0
    ]
    block_rows: list[dict[str, Any]] = []
    for block_index in range(BLOCK_COUNT):
        record_start = block_index * RECORDS_PER_BLOCK
        record_end = record_start + RECORDS_PER_BLOCK
        block_counts = per_record_differences[record_start:record_end]
        left_block = left[block_index * BLOCK_BYTES : (block_index + 1) * BLOCK_BYTES]
        right_block = right[block_index * BLOCK_BYTES : (block_index + 1) * BLOCK_BYTES]
        different_bytes = sum(block_counts)
        bit_hamming_distance = sum(
            (a ^ b).bit_count() for a, b in zip(left_block, right_block)
        )
        unsigned_byte_l1_distance = sum(
            abs(a - b) for a, b in zip(left_block, right_block)
        )
        exact_equal_local = [
            local_index for local_index, count in enumerate(block_counts) if count == 0
        ]
        block_rows.append(
            {
                "block_index": block_index,
                "decoded_offset": PREFIX_BYTES + block_index * BLOCK_BYTES,
                "bytes": BLOCK_BYTES,
                "record_start_index": record_start,
                "record_end_exclusive": record_end,
                "different_byte_positions": different_bytes,
                "equal_byte_positions": BLOCK_BYTES - different_bytes,
                "bit_hamming_distance": bit_hamming_distance,
                "unsigned_byte_l1_distance": unsigned_byte_l1_distance,
                "records_with_any_difference": sum(count > 0 for count in block_counts),
                "exact_equal_record_count": len(exact_equal_local),
                "exact_equal_local_record_indices": exact_equal_local,
                "different_byte_count_by_local_record": block_counts,
                "whole_block_exact_equal": different_bytes == 0,
                "raw_byte_values_emitted": False,
            }
        )

    ranked = sorted(
        block_rows,
        key=lambda row: (
            -int(row["different_byte_positions"]),
            int(row["block_index"]),
        ),
    )
    bit_ranked = sorted(
        block_rows,
        key=lambda row: (-int(row["bit_hamming_distance"]), int(row["block_index"])),
    )
    l1_ranked = sorted(
        block_rows,
        key=lambda row: (
            -int(row["unsigned_byte_l1_distance"]),
            int(row["block_index"]),
        ),
    )
    changed_record_ranked = sorted(
        block_rows,
        key=lambda row: (
            -int(row["records_with_any_difference"]),
            int(row["block_index"]),
        ),
    )
    comparison = _comparison(left, right)
    return {
        **comparison,
        "geometry": {
            "structural_block_count": BLOCK_COUNT,
            "records_per_block": RECORDS_PER_BLOCK,
            "record_bytes": RECORD_BYTES,
            "block_bytes": BLOCK_BYTES,
            "record_count": len(left_records),
        },
        "record_comparison": {
            "exact_equal_record_count": len(exact_equal_records),
            "records_with_any_difference": len(left_records) - len(exact_equal_records),
            "exact_equal_record_indices": exact_equal_records,
            "exact_equal_record_ranges": _ranges(exact_equal_records, unit="record"),
            "different_byte_count_by_record": per_record_differences,
            "different_counts_by_record_byte_index": [
                sum(
                    left_record[byte_index] != right_record[byte_index]
                    for left_record, right_record in zip(left_records, right_records)
                )
                for byte_index in range(RECORD_BYTES)
            ],
        },
        "structural_blocks": block_rows,
        "blocks_ranked_by_descending_positional_byte_mismatch": [
            {
                "block_index": row["block_index"],
                "different_byte_positions": row["different_byte_positions"],
            }
            for row in ranked
        ],
        "blocks_ranked_by_descending_bit_hamming_distance": [
            {
                "block_index": row["block_index"],
                "bit_hamming_distance": row["bit_hamming_distance"],
            }
            for row in bit_ranked
        ],
        "blocks_ranked_by_descending_unsigned_byte_l1_distance": [
            {
                "block_index": row["block_index"],
                "unsigned_byte_l1_distance": row["unsigned_byte_l1_distance"],
            }
            for row in l1_ranked
        ],
        "blocks_ranked_by_descending_changed_record_count": [
            {
                "block_index": row["block_index"],
                "records_with_any_difference": row["records_with_any_difference"],
            }
            for row in changed_record_ranked
        ],
        "whole_block_exact_equal_indices": [
            row["block_index"] for row in block_rows if row["whole_block_exact_equal"]
        ],
    }


def build_report() -> dict[str, Any]:
    """Build the identity-pinned, metadata-only colour-delta report."""

    wf20, wf23 = _load_profiles()
    left = wf20.plaintext
    right = wf23.plaintext
    left_body = left[PREFIX_BYTES : PREFIX_BYTES + BODY_BYTES]
    right_body = right[PREFIX_BYTES : PREFIX_BYTES + BODY_BYTES]
    body = _body_report(left_body, right_body)

    prefix = _comparison(left[:PREFIX_BYTES], right[:PREFIX_BYTES])
    suffix = _comparison(left[-SUFFIX_BYTES:], right[-SUFFIX_BYTES:])
    full = _comparison(left, right)
    r20 = _comparison(left[:R20_BYTES], right[:R20_BYTES])
    power = _comparison(wf20.power_payload, wf23.power_payload)
    pll = _comparison(wf20.pll_payload, wf23.pll_payload)
    wf20_blocks = [
        left_body[offset : offset + BLOCK_BYTES]
        for offset in range(0, BODY_BYTES, BLOCK_BYTES)
    ]
    wf23_blocks = [
        right_body[offset : offset + BLOCK_BYTES]
        for offset in range(0, BODY_BYTES, BLOCK_BYTES)
    ]
    shared_invariant_block = wf20_blocks[5]

    _require(full["different_byte_positions"] == 357, "full delta changed")
    _require(prefix["different_byte_positions"] == 4, "prefix delta changed")
    _require(body["different_byte_positions"] == 353, "body delta changed")
    _require(suffix["different_byte_positions"] == 0, "suffix delta changed")
    _require(r20["different_byte_positions"] == 357, "R20 candidate delta changed")
    _require(power["different_byte_positions"] == 4, "PWR delta changed")
    _require(pll["different_byte_positions"] == 0, "PLL delta changed")
    _require(
        wf20_blocks[5] == wf20_blocks[8] == wf23_blocks[5] == wf23_blocks[8],
        "cross-profile invariant block identity changed",
    )

    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": "offline_identity_pinned_metadata_only_color_experiment_localization",
        "profiles": {
            material.spec.profile_id: {
                "decoded_bytes": len(material.plaintext),
                "decoded_sha256": material.spec.plaintext_sha256,
                "source_path": material.spec.source_relative.as_posix(),
                "source_bytes": material.source_bytes,
                "source_sha256": material.spec.source_sha256,
                "wrapper_bytes": material.spec.wrapper_bytes,
                "wrapper_sha256": material.spec.wrapper_sha256,
                "prefix_sha256": material.spec.header_sha256,
                "r20_candidate_sha256": material.spec.r20_sha256,
                "identity_pinned_by_vendor_profile_loader": True,
                "filename_numeric_tokens_have_no_proven_temperature_semantics": True,
                "raw_plaintext_or_waveform_bytes_emitted": False,
            }
            for material in (wf20, wf23)
        },
        "same_envelope_comparison": {
            "full_800": full,
            "opaque_prefix_7": prefix,
            "structural_body_9x8x11": body,
            "opaque_suffix_1": suffix,
        },
        "empirical_h3_transport_context": {
            "candidate_r20_first_799": r20,
            "derived_power_payload": {
                **power,
                "construction": "fixed leading byte plus decoded prefix offsets 0..4",
                "different_decoded_prefix_offsets": [1, 2, 3, 4],
                "electrical_values_emitted": False,
            },
            "derived_pll_payload": {
                **pll,
                "construction": "decoded prefix offset 6",
                "same_between_profiles": True,
                "electrical_values_emitted": False,
            },
            "constructed_r21": {
                "bytes": R21_BYTES,
                "sha256": R21_SHA256,
                "same_between_profiles": True,
                "vendor_supplied_profile_bytes": False,
                "raw_bytes_emitted": False,
            },
            "direct_WF20_T_vs_WF23_T_is_body_only_comparison": False,
            "reason": (
                "the empirical transactions differ in four prefix-derived PWR "
                "positions as well as 357 candidate-R20 positions"
            ),
        },
        "color_experiment_design": {
            "primary_observable": "same_atlas_position_hue_or_color_class_change",
            "brightness_only_change_counts_as_new_color": False,
            "saturation_uniformity_ghosting_and_brightness_recorded_separately": True,
            "required_matched_pairs": [
                {
                    "control": "WF20 header-matched factory init with no R20/R21",
                    "treatment": "complete identity-pinned WF20 empirical H3",
                },
                {
                    "control": "WF23 header-matched factory init with no R20/R21",
                    "treatment": "complete identity-pinned WF23 empirical H3",
                },
            ],
            "compare_within_each_profile_before_cross_profile_effect_comparison": True,
            "same_DTM_atlas_and_controller_order_required": True,
            "header_body_block_or_record_splicing_allowed": False,
            "single_block_or_single_record_live_mutation_authorized": False,
            "whole_vendor_profile_identity_must_be_preserved": True,
            "matched_pair_proves_individual_R20_R21_field_or_category": False,
        },
        "bounded_findings": {
            "full_equal_positions": full["equal_byte_positions"],
            "full_different_positions": full["different_byte_positions"],
            "prefix_different_positions": prefix["different_byte_positions"],
            "body_different_positions": body["different_byte_positions"],
            "exact_equal_records": body["record_comparison"][
                "exact_equal_record_count"
            ],
            "whole_equal_structural_blocks": body["whole_block_exact_equal_indices"],
            "zero_based_block_5_and_8_four_way_identity": {
                "identities": [
                    "WF20_25.block[5]",
                    "WF20_25.block[8]",
                    "WF23_25.block[5]",
                    "WF23_25.block[8]",
                ],
                "all_equal": True,
                "bytes_each": BLOCK_BYTES,
                "sha256": _sha256(shared_invariant_block),
                "each_block_is_uniform": len(set(shared_invariant_block)) == 1,
                "uniform_byte_value_emitted": False,
                "controller_meaning_assigned": False,
            },
            "unique_maximum_by_positional_byte_mismatch": body[
                "blocks_ranked_by_descending_positional_byte_mismatch"
            ][0],
            "maximum_by_bit_hamming_distance": body[
                "blocks_ranked_by_descending_bit_hamming_distance"
            ][0],
            "maximum_by_unsigned_byte_l1_distance": body[
                "blocks_ranked_by_descending_unsigned_byte_l1_distance"
            ][0],
            "maximum_changed_record_count_is_tied": True,
            "positional_byte_mismatch_is_only_one_distance_metric": True,
            "distance_metric_rankings_disagree": True,
            "every_record_byte_index_varies_somewhere": all(
                count > 0
                for count in body["record_comparison"][
                    "different_counts_by_record_byte_index"
                ]
            ),
            "profile_pair_difference_establishes_color_category_mapping": False,
            "profile_pair_difference_establishes_phase_or_electrical_fields": False,
        },
        "semantic_boundary": {
            "block_is_structural_not_named_color_category": True,
            "record_is_structural_not_named_phase_group": True,
            "block_5_or_8_invariance_proves_fixed_color_behavior": False,
            "block_7_positional_byte_mismatch_maximum_proves_color_role": False,
            "profile_filename_tokens_prove_temperature_band": False,
            "eleven_byte_field_layout_recovered": False,
            "category_order_recovered": False,
            "phase_repeat_voltage_or_duration_recovered": False,
            "dual_controller_acceptance_proven": False,
        },
        "safety": {
            "offline_only": True,
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "device_network_accessed": False,
            "firmware_or_flash_written": False,
            "display_refresh_attempted": False,
            "authorization_token_generated_or_claimed": False,
            "runtime_payload_generated_or_modified": False,
            "profile_hybrid_or_splice_generated": False,
            "raw_waveform_bytes_emitted": False,
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
        ProfileColorDeltaError,
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
