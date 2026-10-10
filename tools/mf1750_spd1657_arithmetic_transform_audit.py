#!/usr/bin/env python3
"""Audit the recovered SPD1657 waveform arithmetic family offline.

This audit is intentionally metadata-output-only.  It pins the two vendor
wrappers and uses the existing profile loader to recover their keys and decrypt
their existing 800-byte plaintext only in memory.  It also pins the labeled
legacy 535-byte initializer and the IAR 1503/704-byte constants, then checks
exact length equations, 11-byte record segmentation, fixed-width padding,
simple record-reordering transforms, and a small explicitly bounded family of
byte-checksum hypotheses.

No waveform bytes, keys, plaintext, runtime payload, or authorization material
are emitted or written, and no include, firmware, or flashable runtime payload
is generated.  Structural equality and checksum coincidence are never
promoted to category, phase, duration, repeat, voltage, or controller
semantics.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from functools import reduce
import hashlib
import json
from operator import xor
from pathlib import Path
import sys
from typing import Any, Callable, Final


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.application.durable_io import (  # noqa: E402
    DurableWriteError,
    write_new_bytes_durable,
)
from tools import mf1750_iar_r43_cross_object_graph as iar_graph  # noqa: E402
from tools import mf1750_spd1657_category_alignment_audit as alignment  # noqa: E402
from tools import mf1750_spd1657_phase_geometry_audit as geometry  # noqa: E402
from tools import mf1750_spd1657_vendor_profile_pack as profile_pack  # noqa: E402


KIND: Final = "mf1750-spd1657-arithmetic-transform-audit"
SCHEMA_VERSION: Final = 2

HEADER_BYTES: Final = 7
RECORD_BYTES: Final = 11
RECORDS_PER_ROW: Final = 8
ROW_BYTES: Final = RECORD_BYTES * RECORDS_PER_ROW
PROFILE_ROWS: Final = 9
LEGACY_ROWS: Final = 6
SECONDARY_ROWS: Final = 8
PROFILE_BODY_BYTES: Final = PROFILE_ROWS * ROW_BYTES
LEGACY_BODY_BYTES: Final = LEGACY_ROWS * ROW_BYTES
SECONDARY_BYTES: Final = SECONDARY_ROWS * ROW_BYTES
PROFILE_WIRE_BYTES: Final = HEADER_BYTES + PROFILE_BODY_BYTES
PROFILE_WRAPPER_PLAINTEXT_BYTES: Final = PROFILE_WIRE_BYTES + 1
DATA0_BYTES: Final = PROFILE_WIRE_BYTES + SECONDARY_BYTES

FF_RECORD: Final = b"\xff" * RECORD_BYTES
FF_ROW: Final = b"\xff" * ROW_BYTES
FF_704: Final = b"\xff" * SECONDARY_BYTES


class ArithmeticTransformAuditError(RuntimeError):
    """Raised when an identity or a bounded structural invariant changes."""


@dataclass(frozen=True)
class RecordDataset:
    """One pinned record region held only in memory."""

    dataset_id: str
    body: bytes
    provenance: dict[str, Any]

    @property
    def records(self) -> tuple[bytes, ...]:
        return tuple(
            self.body[offset : offset + RECORD_BYTES]
            for offset in range(0, len(self.body), RECORD_BYTES)
        )

    @property
    def rows(self) -> tuple[bytes, ...]:
        return tuple(
            self.body[offset : offset + ROW_BYTES]
            for offset in range(0, len(self.body), ROW_BYTES)
        )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ArithmeticTransformAuditError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _split_records(payload: bytes) -> tuple[bytes, ...]:
    _require(len(payload) % RECORD_BYTES == 0, "record region is not 11-byte aligned")
    return tuple(
        payload[offset : offset + RECORD_BYTES]
        for offset in range(0, len(payload), RECORD_BYTES)
    )


def _split_rows(payload: bytes) -> tuple[bytes, ...]:
    _require(len(payload) % ROW_BYTES == 0, "record region is not 88-byte aligned")
    return tuple(
        payload[offset : offset + ROW_BYTES]
        for offset in range(0, len(payload), ROW_BYTES)
    )


def _ff_mask(row: bytes) -> tuple[bool, ...]:
    _require(len(row) == ROW_BYTES, "FF mask received a non-88-byte row")
    return tuple(record == FF_RECORD for record in _split_records(row))


def _row_summary(index: int, row: bytes) -> dict[str, Any]:
    records = _split_records(row)
    mask = _ff_mask(row)
    first_ff = next((offset for offset, value in enumerate(mask) if value), None)
    active_after_first_ff = (
        []
        if first_ff is None
        else [
            offset
            for offset in range(first_ff + 1, RECORDS_PER_ROW)
            if not mask[offset]
        ]
    )
    return {
        "row_index": index,
        "bytes": len(row),
        "sha256": _sha256(row),
        "record_count": len(records),
        "all_ff": row == FF_ROW,
        "all_ff_record_indices": [offset for offset, value in enumerate(mask) if value],
        "non_all_ff_record_count": sum(not value for value in mask),
        "all_ff_records_form_only_a_trailing_suffix": not active_after_first_ff,
        "non_all_ff_record_after_first_all_ff_indices": active_after_first_ff,
        "raw_bytes_emitted": False,
    }


def _dataset_summary(dataset: RecordDataset) -> dict[str, Any]:
    records = dataset.records
    rows = dataset.rows
    active = tuple(record for record in records if record != FF_RECORD)
    row_summaries = [_row_summary(index, row) for index, row in enumerate(rows)]
    _require(
        all(row["all_ff_records_form_only_a_trailing_suffix"] for row in row_summaries),
        f"{dataset.dataset_id} acquired an active record after all-FF padding",
    )
    return {
        "dataset_id": dataset.dataset_id,
        "bytes": len(dataset.body),
        "sha256": _sha256(dataset.body),
        "row_bytes": ROW_BYTES,
        "row_count": len(rows),
        "records_per_row": RECORDS_PER_ROW,
        "record_bytes": RECORD_BYTES,
        "record_count": len(records),
        "non_all_ff_record_count": len(active),
        "all_ff_record_count": len(records) - len(active),
        "non_all_ff_records_starting_with_ff_ff": sum(
            record[:2] == b"\xff\xff" for record in active
        ),
        "record_byte0_zero_count": sum(record[0] == 0 for record in records),
        "non_all_ff_record_byte0_zero_count": sum(record[0] == 0 for record in active),
        "all_rows_have_active_prefix_then_optional_all_ff_suffix": all(
            row["all_ff_records_form_only_a_trailing_suffix"] for row in row_summaries
        ),
        "rows": row_summaries,
        "provenance": dataset.provenance,
        "raw_record_or_payload_bytes_emitted": False,
    }


def _load_evidence(
    iar_root: Path,
) -> tuple[
    dict[str, RecordDataset],
    dict[str, bytes],
    bytes,
    bytes,
    dict[str, Any],
]:
    legacy, labels, legacy_provenance = geometry._load_legacy()
    _require(len(legacy) == 535, "legacy initializer length changed")
    _require(
        labels == ["VCOM", "Black", "White", "Yellow", "Red", "Power"],
        "legacy labels changed",
    )

    materials = {
        profile_id: profile_pack.load_profile(profile_id)
        for profile_id in ("WF20_25", "WF23_25")
    }
    profiles = {
        profile_id: material.plaintext for profile_id, material in materials.items()
    }
    for profile_id, plaintext in profiles.items():
        _require(
            len(plaintext) == PROFILE_WRAPPER_PLAINTEXT_BYTES,
            f"{profile_id} decoded length changed",
        )
        _require(plaintext[-1:] == b"\x00", f"{profile_id} trailing byte changed")

    data0, data1, iar_provenance = alignment._load_iar_arrays(iar_root)
    _require(len(data0) == DATA0_BYTES, "IAR DATA0 length changed")
    _require(len(data1) == SECONDARY_BYTES, "IAR DATA1 length changed")
    _require(data0[PROFILE_WIRE_BYTES:] == FF_704, "DATA0 FF704 suffix changed")

    datasets = {
        "legacy_wf_data_535": RecordDataset(
            dataset_id="legacy_wf_data_535",
            body=legacy[HEADER_BYTES:],
            provenance={
                **legacy_provenance,
                "outer_bytes": len(legacy),
                "outer_sha256": _sha256(legacy),
                "header_bytes": HEADER_BYTES,
                "vendor_labels_direct_only_for_this_dataset": labels,
            },
        ),
        "iar_DATA0_first799": RecordDataset(
            dataset_id="iar_DATA0_first799",
            body=data0[HEADER_BYTES:PROFILE_WIRE_BYTES],
            provenance={
                "outer_symbol": "DATA0",
                "outer_bytes": len(data0),
                "outer_sha256": _sha256(data0),
                "slice_bytes": PROFILE_WIRE_BYTES,
                "slice_sha256": _sha256(data0[:PROFILE_WIRE_BYTES]),
                "internal_799_boundary_declared_by_symbol_or_subobject": False,
            },
        ),
        "iar_DATA1_704": RecordDataset(
            dataset_id="iar_DATA1_704",
            body=data1,
            provenance={
                "outer_symbol": "DATA1",
                "outer_bytes": len(data1),
                "outer_sha256": _sha256(data1),
                "relation_to_DATA0_rows_declared_by_vendor": False,
            },
        ),
    }
    for profile_id, material in materials.items():
        datasets[profile_id] = RecordDataset(
            dataset_id=profile_id,
            body=material.plaintext[HEADER_BYTES:PROFILE_WIRE_BYTES],
            provenance={
                "source_path": material.spec.source_relative.as_posix(),
                "source_sha256": material.spec.source_sha256,
                "wrapper_bytes": material.spec.wrapper_bytes,
                "wrapper_sha256": material.spec.wrapper_sha256,
                "decoded_bytes": len(material.plaintext),
                "decoded_sha256": material.spec.plaintext_sha256,
                "identity_pinned_by_vendor_profile_pack": True,
            },
        )

    _require(len(datasets["legacy_wf_data_535"].rows) == LEGACY_ROWS, "legacy rows")
    _require(len(datasets["iar_DATA0_first799"].rows) == PROFILE_ROWS, "DATA0 rows")
    _require(len(datasets["iar_DATA1_704"].rows) == SECONDARY_ROWS, "DATA1 rows")
    _require(len(datasets["WF20_25"].rows) == PROFILE_ROWS, "WF20 rows")
    _require(len(datasets["WF23_25"].rows) == PROFILE_ROWS, "WF23 rows")
    return datasets, profiles, legacy, data0, data1, iar_provenance


def _simple_checksum_candidates(payload: bytes) -> dict[str, int]:
    return {
        "sum_mod_256": sum(payload) & 0xFF,
        "twos_complement_sum_mod_256": (-sum(payload)) & 0xFF,
        "ones_complement_sum_mod_256": (~sum(payload)) & 0xFF,
        "xor": reduce(xor, payload, 0),
    }


def _outer_suffix_checksum_audit(profiles: dict[str, bytes]) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for profile_id, payload in profiles.items():
        prefix = payload[:PROFILE_WIRE_BYTES]
        suffix = payload[PROFILE_WIRE_BYTES]
        candidates = _simple_checksum_candidates(prefix)
        rows[profile_id] = {
            "prefix_bytes": len(prefix),
            "suffix_offset": PROFILE_WIRE_BYTES,
            "suffix_is_zero": suffix == 0,
            "candidate_algorithms_tested": list(candidates),
            "matching_candidate_algorithms": [
                name for name, value in candidates.items() if value == suffix
            ],
            "simple_checksum_match_exists": any(
                value == suffix for value in candidates.values()
            ),
            "raw_prefix_or_suffix_value_emitted": False,
        }
    _require(
        all(not row["simple_checksum_match_exists"] for row in rows.values()),
        "a profile suffix acquired a simple whole-prefix checksum match",
    )
    return {
        "profiles": rows,
        "bounded_conclusion": (
            "the shared trailing zero is not sum, two's-complement sum, one's-"
            "complement sum, or XOR of the preceding 799 bytes"
        ),
        "does_not_exclude_crc_mac_or_other_integrity_scheme": True,
        "trailing_zero_is_encryption_padding_or_controller_terminator_proven": False,
    }


ChecksumFunction = Callable[[bytes], int]


def _record_checksum_audit(datasets: dict[str, RecordDataset]) -> dict[str, Any]:
    algorithms: dict[str, ChecksumFunction] = {
        "sum_other_bytes_mod_256": lambda payload: sum(payload) & 0xFF,
        "twos_complement_sum_other_bytes_mod_256": (
            lambda payload: (-sum(payload)) & 0xFF
        ),
        "ones_complement_sum_other_bytes_mod_256": (
            lambda payload: (~sum(payload)) & 0xFF
        ),
        "xor_other_bytes": lambda payload: reduce(xor, payload, 0),
    }

    active_by_dataset = {
        dataset_id: tuple(record for record in dataset.records if record != FF_RECORD)
        for dataset_id, dataset in datasets.items()
    }
    active_by_dataset["combined_all_identity_pinned_datasets"] = tuple(
        record
        for dataset_id in sorted(datasets)
        for record in active_by_dataset[dataset_id]
    )

    results: dict[str, Any] = {}
    for dataset_id, records in active_by_dataset.items():
        _require(records, f"{dataset_id} has no active records for checksum audit")
        algorithm_rows: dict[str, Any] = {}
        for algorithm_name, function in algorithms.items():
            matches_by_target = []
            for target_index in range(RECORD_BYTES):
                matches = sum(
                    record[target_index]
                    == function(record[:target_index] + record[target_index + 1 :])
                    for record in records
                )
                matches_by_target.append(matches)
            maximum = max(matches_by_target)
            algorithm_rows[algorithm_name] = {
                "active_record_count": len(records),
                "maximum_match_count_at_any_candidate_check_byte": maximum,
                "candidate_byte_indices_at_maximum": [
                    index
                    for index, count in enumerate(matches_by_target)
                    if count == maximum
                ],
                "universal_match_at_any_candidate_check_byte": maximum == len(records),
                "per_candidate_byte_match_counts": matches_by_target,
            }
        results[dataset_id] = algorithm_rows

    _require(
        not any(
            row["universal_match_at_any_candidate_check_byte"]
            for dataset_rows in results.values()
            for row in dataset_rows.values()
        ),
        "a simple checksum unexpectedly matches every active record",
    )
    return {
        "scope": (
            "all 11 byte positions tested as a possible check byte over non-all-FF "
            "records only"
        ),
        "algorithms": list(algorithms),
        "datasets": results,
        "universal_simple_checksum_relation_found": False,
        "bounded_negative_only": True,
        "does_not_test_or_exclude_crc_mac_or_field_encoding": True,
        "does_not_assign_a_checksum_field": True,
    }


def _shared_active_record_summary(
    left: RecordDataset, right: RecordDataset
) -> dict[str, Any]:
    left_counter = Counter(record for record in left.records if record != FF_RECORD)
    right_counter = Counter(record for record in right.records if record != FF_RECORD)
    shared = left_counter & right_counter
    low_information = {
        record
        for record in shared
        if record.count(0xFF) >= 10 and len(set(record)) <= 2
    }
    return {
        "left": left.dataset_id,
        "right": right.dataset_id,
        "shared_unique_non_all_ff_record_count": len(shared),
        "shared_non_all_ff_record_count_with_multiplicity": sum(shared.values()),
        "shared_unique_low_information_filler_compatible_record_count": len(
            low_information
        ),
        "shared_unique_non_low_information_record_count": len(
            set(shared) - low_information
        ),
        "raw_records_emitted": False,
        "shared_record_assigns_semantics": False,
    }


def _same_length_transform_screen(
    left_id: str, left: bytes, right_id: str, right: bytes
) -> dict[str, Any]:
    _require(len(left) == len(right), "simple transform screen lengths differ")
    _require(
        (len(left) - HEADER_BYTES) % ROW_BYTES == 0,
        "transform screen body geometry changed",
    )
    left_body = left[HEADER_BYTES:]
    right_body = right[HEADER_BYTES:]
    left_records = _split_records(left_body)
    right_records = _split_records(right_body)
    left_rows = _split_rows(left_body)
    right_rows = _split_rows(right_body)
    xor_deltas = {a ^ b for a, b in zip(left, right)}
    additive_deltas = {(b - a) & 0xFF for a, b in zip(left, right)}
    return {
        "left": left_id,
        "right": right_id,
        "bytes": len(left),
        "exact_identity": left == right,
        "whole_payload_bytewise_complement": bytes((~value) & 0xFF for value in left)
        == right,
        "record_multisets_equal": Counter(left_records) == Counter(right_records),
        "row_multisets_equal": Counter(left_rows) == Counter(right_rows),
        "record_byte_reversal_multiset_equal": (
            Counter(record[::-1] for record in left_records) == Counter(right_records)
        ),
        "single_uniform_xor_delta": len(xor_deltas) == 1,
        "distinct_xor_delta_count": len(xor_deltas),
        "single_uniform_additive_mod256_delta": len(additive_deltas) == 1,
        "distinct_additive_mod256_delta_count": len(additive_deltas),
        "transform_family_is_exhaustive": False,
        "field_or_record_semantics_assigned": False,
    }


def _row_reordering_screen(left: RecordDataset, right: RecordDataset) -> dict[str, Any]:
    exact_nontrivial_row_pairs: list[list[int]] = []
    record_multiset_nontrivial_row_pairs: list[list[int]] = []
    ff_mask_nontrivial_row_pairs: list[list[int]] = []
    for left_index, left_row in enumerate(left.rows):
        left_mask = _ff_mask(left_row)
        for right_index, right_row in enumerate(right.rows):
            right_mask = _ff_mask(right_row)
            both_all_ff = left_row == right_row == FF_ROW
            if left_row == right_row and not both_all_ff:
                exact_nontrivial_row_pairs.append([left_index, right_index])
            if (
                Counter(_split_records(left_row)) == Counter(_split_records(right_row))
                and not both_all_ff
            ):
                record_multiset_nontrivial_row_pairs.append([left_index, right_index])
            if left_mask == right_mask and not all(left_mask):
                ff_mask_nontrivial_row_pairs.append([left_index, right_index])
    return {
        "left": left.dataset_id,
        "right": right.dataset_id,
        "exact_non_all_ff_row_pairs": exact_nontrivial_row_pairs,
        "record_multiset_equivalent_non_all_ff_row_pairs": (
            record_multiset_nontrivial_row_pairs
        ),
        "equal_nontrivial_all_ff_mask_row_pairs": ff_mask_nontrivial_row_pairs,
        "exact_row_or_record_reordering_assigns_category_semantics": False,
        "all_ff_mask_equality_assigns_category_semantics": False,
    }


def _aligned_data0_data1(data0: RecordDataset, data1: RecordDataset) -> dict[str, Any]:
    _require(len(data0.rows) == PROFILE_ROWS, "DATA0 structural row count changed")
    _require(len(data1.rows) == SECONDARY_ROWS, "DATA1 structural row count changed")
    offsets: list[dict[str, Any]] = []
    for offset in (0, 1):
        left_rows = data0.rows[offset : offset + SECONDARY_ROWS]
        right_rows = data1.rows
        exact_row_indices = [
            index
            for index, (left_row, right_row) in enumerate(zip(left_rows, right_rows))
            if left_row == right_row
        ]
        non_all_ff_exact_row_indices = [
            index for index in exact_row_indices if left_rows[index] != FF_ROW
        ]
        mask_equal_indices = [
            index
            for index, (left_row, right_row) in enumerate(zip(left_rows, right_rows))
            if _ff_mask(left_row) == _ff_mask(right_row)
        ]
        nontrivial_mask_equal_indices = [
            index for index in mask_equal_indices if not all(_ff_mask(left_rows[index]))
        ]
        left_records = tuple(
            record for row in left_rows for record in _split_records(row)
        )
        right_records = data1.records
        exact_record_indices = [
            index
            for index, pair in enumerate(zip(left_records, right_records))
            if pair[0] == pair[1]
        ]
        non_all_ff_exact_record_indices = [
            index for index in exact_record_indices if left_records[index] != FF_RECORD
        ]
        offsets.append(
            {
                "DATA0_leading_row_offset": offset,
                "compared_rows": SECONDARY_ROWS,
                "compared_records": SECONDARY_ROWS * RECORDS_PER_ROW,
                "exact_row_indices": exact_row_indices,
                "non_all_ff_exact_row_indices": non_all_ff_exact_row_indices,
                "equal_all_ff_mask_row_indices": mask_equal_indices,
                "equal_nontrivial_all_ff_mask_row_indices": (
                    nontrivial_mask_equal_indices
                ),
                "exact_record_count": len(exact_record_indices),
                "non_all_ff_exact_record_count": len(non_all_ff_exact_record_indices),
            }
        )
    _require(
        all(not row["non_all_ff_exact_row_indices"] for row in offsets),
        "DATA0/DATA1 acquired an aligned active row identity",
    )
    _require(
        all(not row["equal_nontrivial_all_ff_mask_row_indices"] for row in offsets),
        "DATA0/DATA1 acquired an aligned nontrivial FF-mask identity",
    )
    _require(
        all(row["non_all_ff_exact_record_count"] == 0 for row in offsets),
        "DATA0/DATA1 acquired an aligned active record identity",
    )
    return {
        "tested_offsets": offsets,
        "offset_selected_as_semantic_mapping": None,
        "active_row_record_or_mask_alignment_found": False,
    }


def _header_electrical_delta(profiles: dict[str, bytes]) -> dict[str, Any]:
    left = profiles["WF20_25"][:HEADER_BYTES]
    right = profiles["WF23_25"][:HEADER_BYTES]
    equal = [index for index, pair in enumerate(zip(left, right)) if pair[0] == pair[1]]
    different = [index for index in range(HEADER_BYTES) if index not in equal]
    _require(equal == [0, 5, 6], "profile header equality coordinates changed")
    _require(different == [1, 2, 3, 4], "profile header delta coordinates changed")
    return {
        "compared_profiles": ["WF20_25", "WF23_25"],
        "header_bytes": HEADER_BYTES,
        "equal_byte_indices": equal,
        "different_byte_indices": different,
        "current_armcc_loader_binding": {
            "command_0x01": "literal 0x0F followed by decoded header[0:5]",
            "command_0x30": "decoded header[6]",
            "header_byte5_forwarded_to_dedicated_header_command": False,
            "header_byte5_included_in_opaque_R20_payload": True,
            "referenced_from_prior_identity_pinned_audit": True,
            "reproduced_by_this_tool": False,
            "this_tool_only_computes_profile_header_coordinate_delta": True,
            "binding_source": (
                "identity-pinned current ArmCC loadWF disassembly already audited by "
                "mf1750_spd1657_reverse_delta"
            ),
        },
        "public_spd1657_manual_projection": {
            "same_gate_level_selector_position": left[0] == right[0],
            "all_four_intermediate_source_level_positions_differ": all(
                left[index] != right[index] for index in range(1, 5)
            ),
            "same_pll_request_position": left[6] == right[6],
            "raw_header_values_emitted": False,
            "mapping_referenced_from_prior_identity_pinned_audit": True,
            "manual_loaded_or_parsed_by_this_tool": False,
            "reproduced_by_this_tool": False,
            "manual_assigns_brightness_or_contrast_semantics": False,
            "profile_difference_is_safe_for_live_use_proven": False,
        },
        "record_body_fields_inferred_from_header_delta": False,
    }


def build_report(iar_root: Path = iar_graph.DEFAULT_IAR_ROOT) -> dict[str, Any]:
    """Build the deterministic metadata-only arithmetic/transform report."""

    datasets, profiles, legacy, data0, data1, iar_provenance = _load_evidence(iar_root)
    data0_first = data0[:PROFILE_WIRE_BYTES]
    data0_second = data0[PROFILE_WIRE_BYTES:]
    _require(data0 == data0_first + data0_second, "DATA0 split reconstruction failed")
    _require(data0_second == FF_704, "DATA0 suffix ceased to be generated FF704")

    same_length_payloads = {
        "WF20_25_first799": profiles["WF20_25"][:PROFILE_WIRE_BYTES],
        "WF23_25_first799": profiles["WF23_25"][:PROFILE_WIRE_BYTES],
        "iar_DATA0_first799": data0_first,
    }
    transform_pairs = []
    pair_ids = tuple(same_length_payloads)
    for left_index, left_id in enumerate(pair_ids):
        for right_id in pair_ids[left_index + 1 :]:
            transform_pairs.append(
                _same_length_transform_screen(
                    left_id,
                    same_length_payloads[left_id],
                    right_id,
                    same_length_payloads[right_id],
                )
            )
    _require(
        all(
            not row[key]
            for row in transform_pairs
            for key in (
                "exact_identity",
                "whole_payload_bytewise_complement",
                "record_multisets_equal",
                "row_multisets_equal",
                "record_byte_reversal_multiset_equal",
                "single_uniform_xor_delta",
                "single_uniform_additive_mod256_delta",
            )
        ),
        "a simple transform unexpectedly became exact",
    )

    data0_dataset = datasets["iar_DATA0_first799"]
    data1_dataset = datasets["iar_DATA1_704"]
    r20_like_ids = (
        "legacy_wf_data_535",
        "iar_DATA0_first799",
        "WF20_25",
        "WF23_25",
    )
    shared_with_data1 = [
        _shared_active_record_summary(datasets[dataset_id], data1_dataset)
        for dataset_id in r20_like_ids
    ]
    _require(
        all(
            row["shared_unique_non_all_ff_record_count"] == 0
            for row in shared_with_data1
        ),
        "DATA1 acquired a shared non-all-FF record with an R20-like body",
    )

    data0_data1_reordering = _row_reordering_screen(data0_dataset, data1_dataset)
    _require(
        not data0_data1_reordering["exact_non_all_ff_row_pairs"],
        "DATA0/DATA1 acquired an exact active row pair",
    )
    _require(
        not data0_data1_reordering["record_multiset_equivalent_non_all_ff_row_pairs"],
        "DATA0/DATA1 acquired a record-reordered active row pair",
    )
    _require(
        not data0_data1_reordering["equal_nontrivial_all_ff_mask_row_pairs"],
        "DATA0/DATA1 acquired a nontrivial FF-mask row pair",
    )

    wf_shared = _shared_active_record_summary(datasets["WF20_25"], datasets["WF23_25"])
    _require(
        wf_shared["shared_unique_non_all_ff_record_count"] == 1
        and wf_shared["shared_unique_low_information_filler_compatible_record_count"]
        == 1
        and wf_shared["shared_unique_non_low_information_record_count"] == 0,
        "WF20/WF23 shared active-record classification changed",
    )

    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": "offline_identity_pinned_metadata_output_only",
        "material_handling": {
            "existing_vendor_wrappers_read": True,
            "vendor_key_material_recovered_in_memory_by_load_profile": True,
            "existing_plaintext_decrypted_in_memory_by_load_profile": True,
            "decrypted_profile_count": len(profiles),
            "plaintext_bytes_per_profile": PROFILE_WRAPPER_PLAINTEXT_BYTES,
            "profile_pack_render_or_write_path_called": False,
            "raw_key_plaintext_or_waveform_bytes_emitted": False,
            "raw_key_plaintext_or_waveform_bytes_written": False,
            "include_or_firmware_generated": False,
            "flashable_runtime_payload_generated": False,
        },
        "arithmetic_family": {
            "legacy_535": {
                "equation": "535 = 7 + 6*8*11",
                "header_bytes": HEADER_BYTES,
                "structural_rows": LEGACY_ROWS,
                "records_per_row": RECORDS_PER_ROW,
                "record_bytes": RECORD_BYTES,
                "identity_sha256": _sha256(legacy),
            },
            "profile_first_799": {
                "equation": "799 = 7 + 9*8*11",
                "header_bytes": HEADER_BYTES,
                "structural_rows": PROFILE_ROWS,
                "records_per_row": RECORDS_PER_ROW,
                "record_bytes": RECORD_BYTES,
                "profile_sha256": {
                    profile_id: _sha256(payload[:PROFILE_WIRE_BYTES])
                    for profile_id, payload in profiles.items()
                },
            },
            "profile_decoded_800": {
                "equation": "800 = 7 + 9*8*11 + 1",
                "outer_suffix_bytes": 1,
                "outer_suffix_is_zero_in_both_profiles": all(
                    payload[-1:] == b"\x00" for payload in profiles.values()
                ),
                "suffix_part_of_any_11_byte_record": False,
            },
            "secondary_704": {
                "equation": "704 = 8*8*11",
                "structural_rows": SECONDARY_ROWS,
                "records_per_row": RECORDS_PER_ROW,
                "record_bytes": RECORD_BYTES,
                "segmentation_is_arithmetically_exact": True,
                "segmentation_assigns_LUT_category_or_controller_semantics": False,
                "iar_DATA1_sha256": _sha256(data1),
                "generated_FF704_sha256": _sha256(FF_704),
            },
            "iar_DATA0_1503": {
                "equations": [
                    "1503 = 799 + 704",
                    "1503 = 7 + 17*8*11",
                ],
                "bytes": len(data0),
                "sha256": _sha256(data0),
                "exactly_first799_concatenated_with_FF704": (
                    data0 == data0_first + FF_704
                ),
                "internal_799_boundary_declared_by_symbol_or_subobject": False,
                "concatenation_proves_R20_R21_semantics": False,
            },
            "all_equations_exact": True,
            "arithmetic_assigns_record_fields_or_register_destination": False,
        },
        "datasets": {
            dataset_id: _dataset_summary(dataset)
            for dataset_id, dataset in datasets.items()
        },
        "iar_cross_object_provenance": iar_provenance,
        "DATA0_DATA1_relationship": {
            "DATA0_suffix_vs_DATA1": {
                "both_bytes": SECONDARY_BYTES,
                "DATA0_suffix_all_ff": data0_second == FF_704,
                "DATA1_all_ff": data1 == FF_704,
                "equal": data0_second == data1,
                "shared_unique_non_all_ff_record_count": 0,
                "DATA1_is_the_active_current_R21_upload_source_proven": False,
            },
            "aligned_offsets_0_and_1": _aligned_data0_data1(
                data0_dataset, data1_dataset
            ),
            "arbitrary_row_and_record_reordering": data0_data1_reordering,
            "R20_like_bodies_vs_DATA1_shared_active_records": shared_with_data1,
            "bounded_conclusion": (
                "the retained DATA1 has no exact non-all-FF 11-byte record in common "
                "with legacy535, DATA0-first799, WF20, or WF23; DATA0-first799 and "
                "DATA1 also have no exact nontrivial FF-mask row pair, so current "
                "content supplies no active record-reordering bridge"
            ),
            "category_or_register_pairing_proven": False,
        },
        "simple_transform_screen": {
            "same_length_first799_pairs": transform_pairs,
            "WF20_vs_WF23_shared_active_records": wf_shared,
            "bounded_transform_family": [
                "identity",
                "whole-payload bytewise complement",
                "arbitrary 11-byte record permutation",
                "arbitrary 88-byte row permutation",
                "byte reversal within every record plus arbitrary record permutation",
                "one uniform XOR byte delta",
                "one uniform additive mod-256 byte delta",
            ],
            "exact_transform_found": False,
            "other_transforms_excluded": False,
        },
        "terminator_repeat_duration_boundary": {
            "all_datasets_have_active_prefix_then_optional_all_ff_suffix_per_row": all(
                _dataset_summary(dataset)[
                    "all_rows_have_active_prefix_then_optional_all_ff_suffix"
                ]
                for dataset in datasets.values()
            ),
            "non_all_ff_record_starting_ff_ff_count_across_all_datasets": sum(
                record[:2] == b"\xff\xff"
                for dataset in datasets.values()
                for record in dataset.records
                if record != FF_RECORD
            ),
            "raw_record_byte0_zero_count_across_all_datasets": sum(
                record[0] == 0
                for dataset in datasets.values()
                for record in dataset.records
            ),
            "spd1656_direct_raw_projection": {
                "published_RP_zero_means_no_repeat_or_end": True,
                "published_TP_zero_means_phase_skipped": True,
                "local_all_ff_record_would_not_be_RP_zero_or_TP_zero": True,
                "direct_unmodified_spd1656_repeat_duration_parser_transfer_proven": False,
                "bitwise_complement_or_active_low_decode_proven": False,
            },
            "trailing_all_ff_is_compatible_with_fixed_width_padding": True,
            "trailing_all_ff_is_a_controller_terminator_proven": False,
            "record_byte0_is_repeat_count_proven": False,
            "any_record_byte_is_duration_proven": False,
        },
        "checksum_hypotheses": {
            "outer_profile_suffix": _outer_suffix_checksum_audit(profiles),
            "per_record": _record_checksum_audit(datasets),
        },
        "electrical_header_delta": _header_electrical_delta(profiles),
        "adjudication": {
            "new_bounded_facts": [
                "704 admits an exact metadata-only 8*8*11 segmentation",
                "DATA0 is exactly first799 plus FF704 but has no declared internal symbol boundary",
                "DATA0-first799 and DATA1 share neither an active record nor a nontrivial FF-mask row",
                "the tested simple checksum family matches neither outer suffix nor every active record",
                "WF20 and WF23 differ only at header positions 1..4 among their seven header bytes",
            ],
            "reproducible_structural_transform_yields_new_waveform": False,
            "record_order_mapping_proven": False,
            "category_mapping_proven": False,
            "phase_mapping_proven": False,
            "repeat_or_duration_field_proven": False,
            "checksum_field_proven": False,
            "electrical_header_loader_binding_referenced_from_prior_identity_pinned_audit": True,
            "electrical_header_loader_binding_reproduced_by_this_tool": False,
            "public_manual_mapping_reproduced_by_this_tool": False,
            "electrical_record_field_proven": False,
            "safe_next_evidence_needed": [
                "same-build 800-byte loader or relocation-resolved consumer",
                "controller documentation for R20/R21 parameter ABI",
                "transaction-complete SPI capture with CS and D/C attribution",
                "vendor-labeled non-filler rows spanning both register destinations",
            ],
        },
        "safety": {
            "offline_only": True,
            "existing_profile_plaintext_materialized_in_memory": True,
            "hardware_accessed": False,
            "serial_or_COM8_accessed": False,
            "device_network_accessed": False,
            "firmware_or_flash_written": False,
            "display_refresh_attempted": False,
            "authorization_token_generated_or_claimed": False,
            "runtime_or_recovery_release_modified": False,
            "runtime_payload_generated": False,
            "profile_plaintext_or_key_written_to_disk": False,
            "raw_waveform_plaintext_key_or_payload_emitted": False,
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
    parser.add_argument("--iar-root", type=Path, default=iar_graph.DEFAULT_IAR_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = build_report(args.iar_root)
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
        ArithmeticTransformAuditError,
        alignment.CategoryAlignmentAuditError,
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
