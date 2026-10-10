#!/usr/bin/env python3
"""Audit cross-generation SPD1657 category/record alignment offline.

This audit compares only identity-pinned local evidence:

* the vendor-comment-labeled legacy 535-byte ``wf_data`` initializer;
* the retained IAR ``DATA0`` first-799-byte slice and ``DATA1`` constant; and
* the decoded WF20_25 and WF23_25 800-byte profiles.

The report contains hashes, geometry, equality coordinates, and Hamming
distances.  It never emits a waveform byte, key, runtime payload, or field
value.  A shared ordinal, an all-FF match, or a nearest-distance result is not
promoted to a category, phase, voltage, or duration meaning.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from itertools import combinations, permutations
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
from tools import mf1750_iar_data0_data1_compatibility_audit as iar_arrays  # noqa: E402
from tools import mf1750_iar_r43_cross_object_graph as iar_graph  # noqa: E402
from tools import mf1750_spd1657_phase_geometry_audit as geometry  # noqa: E402
from tools import mf1750_spd1657_vendor_profile_pack as profile_pack  # noqa: E402


KIND: Final = "mf1750-spd1657-category-alignment-audit"
SCHEMA_VERSION: Final = 1

HEADER_BYTES: Final = 7
RECORD_BYTES: Final = 11
RECORDS_PER_ROW: Final = 8
ROW_BYTES: Final = RECORD_BYTES * RECORDS_PER_ROW
FF_RECORD: Final = b"\xff" * RECORD_BYTES
FF_ROW: Final = b"\xff" * ROW_BYTES
MAX_ASSIGNMENTS_EMITTED: Final = 8

LEGACY_ID: Final = "legacy_wf_data_535"
DATA0_ID: Final = "iar_DATA0_first799"
DATA1_ID: Final = "iar_DATA1_704"
WF20_ID: Final = "WF20_25"
WF23_ID: Final = "WF23_25"

LEGACY_LABELS: Final = ("VCOM", "Black", "White", "Yellow", "Red", "Power")


class CategoryAlignmentAuditError(RuntimeError):
    """An identity or structural invariant changed."""


@dataclass(frozen=True)
class Dataset:
    """One in-memory structural body; bytes are never serialized."""

    dataset_id: str
    body: bytes
    header: bytes | None
    suffix_bytes: int
    labels: tuple[str, ...] | None
    provenance: dict[str, Any]

    @property
    def rows(self) -> tuple[bytes, ...]:
        return tuple(
            self.body[offset : offset + ROW_BYTES]
            for offset in range(0, len(self.body), ROW_BYTES)
        )

    @property
    def records(self) -> tuple[bytes, ...]:
        return tuple(
            self.body[offset : offset + RECORD_BYTES]
            for offset in range(0, len(self.body), RECORD_BYTES)
        )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CategoryAlignmentAuditError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _byte_distance(left: bytes, right: bytes) -> int:
    _require(len(left) == len(right), "byte-distance lengths differ")
    return sum(a != b for a, b in zip(left, right))


def _bit_distance(left: bytes, right: bytes) -> int:
    _require(len(left) == len(right), "bit-distance lengths differ")
    return sum((a ^ b).bit_count() for a, b in zip(left, right))


def _all_ff_record_indices(row: bytes) -> list[int]:
    _require(len(row) == ROW_BYTES, "row width changed")
    return [
        index
        for index in range(RECORDS_PER_ROW)
        if row[index * RECORD_BYTES : (index + 1) * RECORD_BYTES] == FF_RECORD
    ]


def _non_ff_counts_by_record(row: bytes) -> list[int]:
    _require(len(row) == ROW_BYTES, "row width changed")
    return [
        sum(value != 0xFF for value in row[index : index + RECORD_BYTES])
        for index in range(0, ROW_BYTES, RECORD_BYTES)
    ]


def _load_iar_arrays(iar_root: Path) -> tuple[bytes, bytes, dict[str, Any]]:
    object_dir = iar_root / iar_graph.OBJECT_DIR_REL
    recovered: dict[str, dict[str, bytes]] = {}
    objects: dict[str, Any] = {}
    for object_id, contract in iar_arrays.OBJECTS.items():
        path = object_dir / str(contract["filename"])
        payload = iar_arrays._pin_object(path, contract)
        arrays = {
            name: iar_arrays._extract_tagged_array(
                payload,
                label=f"{object_id}.{name}",
                contract=contract["arrays"][name],
            )
            for name in iar_arrays.ARRAY_NAMES
        }
        recovered[object_id] = arrays
        objects[object_id] = {
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "object_size_bytes": len(payload),
            "object_sha256": _sha256(payload),
            "DATA0_section_id": int(contract["arrays"]["DATA0"]["section_id"]),
            "DATA1_section_id": int(contract["arrays"]["DATA1"]["section_id"]),
            "DATA0_encoded_end_is_DATA1_marker": (
                int(contract["arrays"]["DATA0"]["encoded_end_offset"])
                == int(contract["arrays"]["DATA1"]["marker_offset"])
            ),
        }

    _require(
        all(row["DATA0_encoded_end_is_DATA1_marker"] for row in objects.values()),
        "DATA0 and DATA1 are no longer adjacent UBROF sections",
    )

    _require(
        recovered["E2801"]["DATA0"] == recovered["E2802"]["DATA0"],
        "E2801/E2802 DATA0 content diverged",
    )
    _require(
        recovered["E2801"]["DATA1"] == recovered["E2802"]["DATA1"],
        "E2801/E2802 DATA1 content diverged",
    )
    data0 = recovered["E2802"]["DATA0"]
    data1 = recovered["E2802"]["DATA1"]
    _require(len(data0) == 1_503, "DATA0 length changed")
    _require(len(data1) == 704, "DATA1 length changed")
    _require(data0[799:] == b"\xff" * 704, "DATA0 FF704 suffix changed")
    return (
        data0,
        data1,
        {
            "objects": objects,
            "arrays_are_byte_identical_across_E2801_and_E2802": True,
            "DATA0_and_DATA1_are_adjacent_UBROF_sections": True,
            "adjacency_proves_a_logical_pair_or_category_mapping": False,
        },
    )


def _load_datasets(iar_root: Path) -> tuple[dict[str, Dataset], dict[str, Any]]:
    legacy, labels, legacy_source = geometry._load_legacy()
    _require(tuple(labels) == LEGACY_LABELS, "legacy labels changed")
    _require(len(legacy) == 535, "legacy initializer length changed")

    data0, data1, iar_provenance = _load_iar_arrays(iar_root)
    data0_first799 = data0[:799]
    _require(len(data0_first799) == HEADER_BYTES + 9 * ROW_BYTES, "DATA0 slice changed")

    materials = {
        profile_id: profile_pack.load_profile(profile_id)
        for profile_id in (WF20_ID, WF23_ID)
    }
    for profile_id, material in materials.items():
        _require(len(material.plaintext) == 800, f"{profile_id} length changed")
        _require(material.plaintext[799:] == b"\x00", f"{profile_id} suffix changed")

    datasets = {
        LEGACY_ID: Dataset(
            dataset_id=LEGACY_ID,
            body=legacy[HEADER_BYTES:],
            header=legacy[:HEADER_BYTES],
            suffix_bytes=0,
            labels=LEGACY_LABELS,
            provenance={
                **legacy_source,
                "label_provenance": "vendor comments on each GROUP1..GROUP8 row",
            },
        ),
        DATA0_ID: Dataset(
            dataset_id=DATA0_ID,
            body=data0_first799[HEADER_BYTES:],
            header=data0_first799[:HEADER_BYTES],
            suffix_bytes=0,
            labels=None,
            provenance={
                "provider": "E2801.r43 and E2802.r43 retained DATA0",
                "slice_bytes": len(data0_first799),
                "slice_sha256": _sha256(data0_first799),
                "whole_DATA0_bytes": len(data0),
                "whole_DATA0_sha256": _sha256(data0),
                "internal_799_boundary_declared_by_symbol_or_subobject": False,
            },
        ),
        DATA1_ID: Dataset(
            dataset_id=DATA1_ID,
            body=data1,
            header=None,
            suffix_bytes=0,
            labels=None,
            provenance={
                "provider": "E2801.r43 and E2802.r43 retained DATA1",
                "array_bytes": len(data1),
                "array_sha256": _sha256(data1),
                "declared_relation_to_DATA0_rows": False,
            },
        ),
    }
    for profile_id, material in materials.items():
        datasets[profile_id] = Dataset(
            dataset_id=profile_id,
            body=material.plaintext[HEADER_BYTES:799],
            header=material.plaintext[:HEADER_BYTES],
            suffix_bytes=1,
            labels=None,
            provenance={
                "source_path": material.spec.source_relative.as_posix(),
                "source_bytes": material.source_bytes,
                "source_sha256": material.spec.source_sha256,
                "wrapper_sha256": material.spec.wrapper_sha256,
                "decoded_sha256": material.spec.plaintext_sha256,
                "same_800_byte_envelope_family": True,
            },
        )

    for dataset in datasets.values():
        _require(len(dataset.body) % ROW_BYTES == 0, "body is not 88-byte aligned")
        _require(len(dataset.body) % RECORD_BYTES == 0, "body is not 11-byte aligned")
        if dataset.labels is not None:
            _require(len(dataset.labels) == len(dataset.rows), "label count changed")
    return datasets, iar_provenance


def _dataset_metadata(dataset: Dataset) -> dict[str, Any]:
    rows = dataset.rows
    records = dataset.records
    row_summaries = []
    for index, row in enumerate(rows):
        row_summaries.append(
            {
                "index": index,
                "vendor_label": dataset.labels[index] if dataset.labels else None,
                "sha256": _sha256(row),
                "all_ff": row == FF_ROW,
                "all_ff_record_indices": _all_ff_record_indices(row),
                "non_ff_byte_counts_by_record": _non_ff_counts_by_record(row),
            }
        )

    columns = []
    for column in range(RECORD_BYTES):
        values = [record[column] for record in records]
        distinct = len(set(values))
        constant_class = None
        if distinct == 1:
            if values[0] == 0xFF:
                constant_class = "all_ff"
            elif values[0] == 0:
                constant_class = "all_zero"
            else:
                constant_class = "constant_value_redacted"
        columns.append(
            {
                "record_byte_index": column,
                "distinct_value_count": distinct,
                "ff_count": values.count(0xFF),
                "zero_count": values.count(0),
                "constant": distinct == 1,
                "constant_class": constant_class,
            }
        )

    return {
        "payload_geometry": {
            "header_bytes": 0 if dataset.header is None else len(dataset.header),
            "row_bytes": ROW_BYTES,
            "row_count": len(rows),
            "records_per_row": RECORDS_PER_ROW,
            "record_bytes": RECORD_BYTES,
            "record_count": len(records),
            "suffix_bytes_outside_body": dataset.suffix_bytes,
        },
        "body_sha256": _sha256(dataset.body),
        "header_sha256": None if dataset.header is None else _sha256(dataset.header),
        "direct_vendor_labels": list(dataset.labels) if dataset.labels else [],
        "unlabeled_row_indices": [] if dataset.labels else list(range(len(rows))),
        "all_ff_row_indices": [
            index for index, row in enumerate(rows) if row == FF_ROW
        ],
        "rows": row_summaries,
        "record_byte_columns": columns,
        "provenance": dataset.provenance,
        "raw_values_emitted": False,
    }


def _exact_row_comparison(left: Dataset, right: Dataset) -> dict[str, Any]:
    matches = [
        {
            "left_row_index": left_index,
            "right_row_index": right_index,
            "row_sha256": _sha256(left_row),
            "all_ff": left_row == FF_ROW,
        }
        for left_index, left_row in enumerate(left.rows)
        for right_index, right_row in enumerate(right.rows)
        if left_row == right_row
    ]
    same_ordinal = [
        index
        for index, (left_row, right_row) in enumerate(zip(left.rows, right.rows))
        if left_row == right_row
    ]
    return {
        "left": left.dataset_id,
        "right": right.dataset_id,
        "exact_row_matches": matches,
        "exact_row_match_count": len(matches),
        "non_all_ff_exact_row_matches": [row for row in matches if not row["all_ff"]],
        "non_all_ff_exact_row_match_count": sum(not row["all_ff"] for row in matches),
        "same_ordinal_exact_row_indices": same_ordinal,
        "same_ordinal_non_all_ff_exact_row_indices": [
            index for index in same_ordinal if left.rows[index] != FF_ROW
        ],
        "exact_match_assigns_category_semantics": False,
    }


def _record_coordinates(dataset: Dataset) -> dict[bytes, list[list[int]]]:
    coordinates: dict[bytes, list[list[int]]] = {}
    for flat_index, record in enumerate(dataset.records):
        coordinates.setdefault(record, []).append(
            [flat_index // RECORDS_PER_ROW, flat_index % RECORDS_PER_ROW]
        )
    return coordinates


def _exact_record_comparison(left: Dataset, right: Dataset) -> dict[str, Any]:
    left_coordinates = _record_coordinates(left)
    right_coordinates = _record_coordinates(right)
    shared = []
    for record in sorted(
        left_coordinates.keys() & right_coordinates.keys(), key=_sha256
    ):
        left_rows = left_coordinates[record]
        right_rows = right_coordinates[record]
        shared.append(
            {
                "record_sha256": _sha256(record),
                "all_ff": record == FF_RECORD,
                "left_coordinates": left_rows,
                "right_coordinates": right_rows,
                "cross_coordinate_pair_count": len(left_rows) * len(right_rows),
            }
        )
    non_ff = [row for row in shared if not row["all_ff"]]
    return {
        "left": left.dataset_id,
        "right": right.dataset_id,
        "shared_unique_record_count": len(shared),
        "shared_unique_non_all_ff_record_count": len(non_ff),
        "shared_record_clusters": shared,
        "shared_non_all_ff_record_clusters": non_ff,
        "non_all_ff_cross_coordinate_pair_count": sum(
            row["cross_coordinate_pair_count"] for row in non_ff
        ),
        "exact_subrecord_identity_proves_complete_row_or_category_semantics": False,
    }


def _geometry_signature_matches(left: Dataset, right: Dataset) -> list[dict[str, Any]]:
    return [
        {
            "left_row_index": left_index,
            "right_row_index": right_index,
            "all_ff_record_indices": _all_ff_record_indices(left_row),
        }
        for left_index, left_row in enumerate(left.rows)
        for right_index, right_row in enumerate(right.rows)
        if _all_ff_record_indices(left_row) == _all_ff_record_indices(right_row)
    ]


def _optimal_assignments(distance_matrix: list[list[int]]) -> dict[str, Any]:
    _require(bool(distance_matrix), "assignment matrix is empty")
    source_count = len(distance_matrix)
    target_count = len(distance_matrix[0])
    _require(target_count >= source_count, "assignment target is too short")
    _require(
        all(len(row) == target_count for row in distance_matrix),
        "assignment matrix is ragged",
    )
    best_cost: int | None = None
    best: list[list[int]] = []
    best_count = 0
    for assignment in permutations(range(target_count), source_count):
        cost = sum(
            distance_matrix[index][target] for index, target in enumerate(assignment)
        )
        if best_cost is None or cost < best_cost:
            best_cost = cost
            best = [list(assignment)]
            best_count = 1
        elif cost == best_cost:
            best_count += 1
            if len(best) < MAX_ASSIGNMENTS_EMITTED:
                best.append(list(assignment))
    _require(best_cost is not None, "no assignment evaluated")
    positional = list(range(source_count))
    positional_cost = sum(
        distance_matrix[index][target] for index, target in enumerate(positional)
    )
    return {
        "minimum_total_byte_hamming_distance": best_cost,
        "optimal_assignment_count": best_count,
        "first_optimal_assignments": best,
        "optimal_assignment_list_truncated": best_count > len(best),
        "positional_assignment": positional,
        "positional_total_byte_hamming_distance": positional_cost,
        "positional_assignment_is_optimal": positional_cost == best_cost,
        "distance_optimization_proves_semantic_mapping": False,
    }


def _legacy_label_alignment(legacy: Dataset, target: Dataset) -> dict[str, Any]:
    _require(legacy.labels == LEGACY_LABELS, "legacy labels unavailable")
    byte_matrix = [
        [_byte_distance(left_row, right_row) for right_row in target.rows]
        for left_row in legacy.rows
    ]
    bit_matrix = [
        [_bit_distance(left_row, right_row) for right_row in target.rows]
        for left_row in legacy.rows
    ]
    rows = []
    for index, label in enumerate(LEGACY_LABELS):
        distances = byte_matrix[index]
        minimum = min(distances)
        exact_indices = [
            target_index
            for target_index, target_row in enumerate(target.rows)
            if target_row == legacy.rows[index]
        ]
        geometry_indices = [
            target_index
            for target_index, target_row in enumerate(target.rows)
            if _all_ff_record_indices(target_row)
            == _all_ff_record_indices(legacy.rows[index])
        ]
        rows.append(
            {
                "legacy_index": index,
                "legacy_vendor_label": label,
                "exact_byte_target_indices": exact_indices,
                "all_ff_mask_geometry_target_indices": geometry_indices,
                "nearest_byte_distance": minimum,
                "nearest_byte_distance_target_indices": [
                    target_index
                    for target_index, distance in enumerate(distances)
                    if distance == minimum
                ],
                "same_ordinal_byte_distance": (
                    distances[index] if index < len(target.rows) else None
                ),
                "same_ordinal_geometry_signature_equal": (
                    index < len(target.rows)
                    and _all_ff_record_indices(legacy.rows[index])
                    == _all_ff_record_indices(target.rows[index])
                ),
                "label_transferred": False,
            }
        )
    return {
        "source": legacy.dataset_id,
        "target": target.dataset_id,
        "byte_hamming_distance_matrix": byte_matrix,
        "bit_hamming_distance_matrix": bit_matrix,
        "labeled_rows": rows,
        "one_to_one_byte_distance_assignment": _optimal_assignments(byte_matrix),
        "full_labeled_row_exact_match_count": sum(
            bool(row["exact_byte_target_indices"]) for row in rows
        ),
        "labels_transferred": [],
        "position_or_distance_alone_is_label_evidence": False,
    }


def _aligned_column_comparison(
    left: Dataset,
    right: Dataset,
    *,
    left_row_offset: int = 0,
    right_row_offset: int = 0,
    row_count: int | None = None,
    alignment_basis: str,
) -> dict[str, Any]:
    available = min(
        len(left.rows) - left_row_offset,
        len(right.rows) - right_row_offset,
    )
    count = available if row_count is None else row_count
    _require(0 < count <= available, "invalid aligned row count")
    left_records = tuple(
        record
        for row in left.rows[left_row_offset : left_row_offset + count]
        for record in (
            row[index : index + RECORD_BYTES]
            for index in range(0, ROW_BYTES, RECORD_BYTES)
        )
    )
    right_records = tuple(
        record
        for row in right.rows[right_row_offset : right_row_offset + count]
        for record in (
            row[index : index + RECORD_BYTES]
            for index in range(0, ROW_BYTES, RECORD_BYTES)
        )
    )
    pairs = list(zip(left_records, right_records))
    active_pairs = [
        (left_record, right_record)
        for left_record, right_record in pairs
        if not (left_record == FF_RECORD and right_record == FF_RECORD)
    ]

    columns = []
    for column in range(RECORD_BYTES):
        equal = sum(
            left_record[column] == right_record[column]
            for left_record, right_record in pairs
        )
        equal_ff = sum(
            left_record[column] == right_record[column] == 0xFF
            for left_record, right_record in pairs
        )
        active_equal = sum(
            left_record[column] == right_record[column]
            for left_record, right_record in active_pairs
        )
        active_equal_ff = sum(
            left_record[column] == right_record[column] == 0xFF
            for left_record, right_record in active_pairs
        )
        columns.append(
            {
                "record_byte_index": column,
                "equal_count": equal,
                "different_count": len(pairs) - equal,
                "equal_ff_count": equal_ff,
                "equal_non_ff_count": equal - equal_ff,
                "active_record_equal_count": active_equal,
                "active_record_different_count": len(active_pairs) - active_equal,
                "active_record_equal_ff_count": active_equal_ff,
                "active_record_equal_non_ff_count": active_equal - active_equal_ff,
            }
        )

    exact_records = [
        {
            "aligned_record_index": index,
            "left_row_index": left_row_offset + index // RECORDS_PER_ROW,
            "right_row_index": right_row_offset + index // RECORDS_PER_ROW,
            "record_index_within_row": index % RECORDS_PER_ROW,
            "all_ff": left_record == FF_RECORD,
        }
        for index, (left_record, right_record) in enumerate(pairs)
        if left_record == right_record
    ]
    return {
        "left": left.dataset_id,
        "right": right.dataset_id,
        "left_row_offset": left_row_offset,
        "right_row_offset": right_row_offset,
        "aligned_row_count": count,
        "aligned_record_count": len(pairs),
        "both_all_ff_record_count": len(pairs) - len(active_pairs),
        "active_record_count": len(active_pairs),
        "alignment_basis": alignment_basis,
        "columns": columns,
        "fully_invariant_column_indices": [
            row["record_byte_index"] for row in columns if row["different_count"] == 0
        ],
        "active_record_fully_invariant_column_indices": [
            row["record_byte_index"]
            for row in columns
            if row["active_record_different_count"] == 0
        ],
        "exact_same_coordinate_records": exact_records,
        "exact_same_coordinate_non_all_ff_record_count": sum(
            not row["all_ff"] for row in exact_records
        ),
        "alignment_assigns_field_semantics": False,
    }


def _data1_offset_hypotheses(data1: Dataset, target: Dataset) -> dict[str, Any]:
    _require(len(data1.rows) == 8, "DATA1 row count changed")
    _require(len(target.rows) == 9, "offset target row count changed")
    non_ff_data1_indices = [
        index for index, row in enumerate(data1.rows) if row != FF_ROW
    ]
    hypotheses = []
    for offset in (0, 1):
        distances = [
            _byte_distance(data1_row, target.rows[index + offset])
            for index, data1_row in enumerate(data1.rows)
        ]
        exact = [index for index, distance in enumerate(distances) if distance == 0]
        hypotheses.append(
            {
                "target_leading_row_offset": offset,
                "row_byte_hamming_distances": distances,
                "total_byte_hamming_distance": sum(distances),
                "non_all_ff_DATA1_rows_total_byte_hamming_distance": sum(
                    distances[index] for index in non_ff_data1_indices
                ),
                "exact_row_indices_in_DATA1_coordinates": exact,
                "non_all_ff_exact_row_indices_in_DATA1_coordinates": [
                    index for index in exact if data1.rows[index] != FF_ROW
                ],
            }
        )
    by_total = min(row["total_byte_hamming_distance"] for row in hypotheses)
    by_active = min(
        row["non_all_ff_DATA1_rows_total_byte_hamming_distance"] for row in hypotheses
    )
    return {
        "DATA1": data1.dataset_id,
        "nine_row_target": target.dataset_id,
        "hypotheses": hypotheses,
        "minimum_total_distance_offsets": [
            row["target_leading_row_offset"]
            for row in hypotheses
            if row["total_byte_hamming_distance"] == by_total
        ],
        "minimum_non_all_ff_DATA1_distance_offsets": [
            row["target_leading_row_offset"]
            for row in hypotheses
            if row["non_all_ff_DATA1_rows_total_byte_hamming_distance"] == by_active
        ],
        "non_all_ff_exact_row_match_exists": any(
            row["non_all_ff_exact_row_indices_in_DATA1_coordinates"]
            for row in hypotheses
        ),
        "offset_selected_as_semantic_mapping": None,
        "distance_selects_R20_or_R21_category_semantics": False,
    }


def _header_comparisons(datasets: dict[str, Dataset]) -> dict[str, Any]:
    with_headers = [
        datasets[dataset_id] for dataset_id in (LEGACY_ID, DATA0_ID, WF20_ID, WF23_ID)
    ]
    result = {}
    for left, right in combinations(with_headers, 2):
        assert left.header is not None
        assert right.header is not None
        equal = [
            index
            for index, (left_value, right_value) in enumerate(
                zip(left.header, right.header)
            )
            if left_value == right_value
        ]
        result[f"{left.dataset_id}__vs__{right.dataset_id}"] = {
            "left": left.dataset_id,
            "right": right.dataset_id,
            "compared_positions": HEADER_BYTES,
            "equal_position_indices": equal,
            "different_position_indices": [
                index for index in range(HEADER_BYTES) if index not in equal
            ],
            "values_emitted": False,
            "equal_value_transfers_a_header_field_label": False,
        }
    return result


def _multiway_column_consensus(datasets: Iterable[Dataset]) -> dict[str, Any]:
    selected = tuple(datasets)
    _require(len(selected) >= 3, "multiway comparison needs at least three datasets")
    record_count = min(len(dataset.records) for dataset in selected)
    records = [dataset.records[:record_count] for dataset in selected]
    coordinates = list(zip(*records))
    active = [
        coordinate
        for coordinate in coordinates
        if not all(row == FF_RECORD for row in coordinate)
    ]
    columns = []
    for column in range(RECORD_BYTES):
        equal_count = sum(
            len({record[column] for record in coordinate}) == 1
            for coordinate in coordinates
        )
        equal_ff_count = sum(
            all(record[column] == 0xFF for record in coordinate)
            for coordinate in coordinates
        )
        active_equal_count = sum(
            len({record[column] for record in coordinate}) == 1 for coordinate in active
        )
        active_equal_ff_count = sum(
            all(record[column] == 0xFF for record in coordinate)
            for coordinate in active
        )
        columns.append(
            {
                "record_byte_index": column,
                "all_equal_count": equal_count,
                "all_equal_ff_count": equal_ff_count,
                "all_equal_non_ff_count": equal_count - equal_ff_count,
                "active_record_all_equal_count": active_equal_count,
                "active_record_all_equal_ff_count": active_equal_ff_count,
                "active_record_all_equal_non_ff_count": (
                    active_equal_count - active_equal_ff_count
                ),
            }
        )
    return {
        "datasets": [dataset.dataset_id for dataset in selected],
        "common_record_count": record_count,
        "active_record_count": len(active),
        "alignment_basis": "cross_generation_first_48_record_ordinal_hypothesis_only",
        "columns": columns,
        "fully_invariant_column_indices": [
            row["record_byte_index"]
            for row in columns
            if row["all_equal_count"] == record_count
        ],
        "active_record_fully_invariant_column_indices": [
            row["record_byte_index"]
            for row in columns
            if row["active_record_all_equal_count"] == len(active)
        ],
        "common_ordinal_alignment_is_semantically_proven": False,
        "multiway_equality_assigns_field_semantics": False,
    }


def build_report(iar_root: Path = iar_graph.DEFAULT_IAR_ROOT) -> dict[str, Any]:
    """Build the deterministic metadata-only alignment report."""

    datasets, iar_provenance = _load_datasets(iar_root)
    legacy = datasets[LEGACY_ID]
    data0 = datasets[DATA0_ID]
    data1 = datasets[DATA1_ID]
    wf20 = datasets[WF20_ID]
    wf23 = datasets[WF23_ID]

    exact_pairs = {
        f"{left_id}__vs__{right_id}": _exact_row_comparison(
            datasets[left_id], datasets[right_id]
        )
        for left_id, right_id in combinations(datasets, 2)
    }
    exact_record_pairs = {
        f"{left_id}__vs__{right_id}": _exact_record_comparison(
            datasets[left_id], datasets[right_id]
        )
        for left_id, right_id in combinations(datasets, 2)
    }
    geometry_pairs = {
        target.dataset_id: _geometry_signature_matches(legacy, target)
        for target in (data0, data1, wf20, wf23)
    }

    same_envelope_columns = _aligned_column_comparison(
        wf20,
        wf23,
        alignment_basis="same_800_byte_envelope_and_same_9x8x11_coordinate_geometry",
    )
    column_comparisons = {
        "WF20_25__vs__WF23_25": same_envelope_columns,
        "legacy__vs__DATA0_first_six_rows": _aligned_column_comparison(
            legacy,
            data0,
            row_count=6,
            alignment_basis="cross_generation_shared_ordinal_geometry_only",
        ),
        "legacy__vs__WF20_first_six_rows": _aligned_column_comparison(
            legacy,
            wf20,
            row_count=6,
            alignment_basis="cross_generation_shared_ordinal_geometry_only",
        ),
        "legacy__vs__WF23_first_six_rows": _aligned_column_comparison(
            legacy,
            wf23,
            row_count=6,
            alignment_basis="cross_generation_shared_ordinal_geometry_only",
        ),
        "DATA0__vs__DATA1_same_start": _aligned_column_comparison(
            data0,
            data1,
            row_count=8,
            alignment_basis="same_object_adjacent_sections_but_undeclared_row_relation",
        ),
        "DATA0_excluding_first__vs__DATA1": _aligned_column_comparison(
            data0,
            data1,
            left_row_offset=1,
            row_count=8,
            alignment_basis="alternative_exclude-leading-row_hypothesis_only",
        ),
        "DATA0__vs__WF20": _aligned_column_comparison(
            data0,
            wf20,
            alignment_basis="cross_generation_same_9x8x11_geometry_only",
        ),
        "DATA0__vs__WF23": _aligned_column_comparison(
            data0,
            wf23,
            alignment_basis="cross_generation_same_9x8x11_geometry_only",
        ),
    }

    column5 = same_envelope_columns["columns"][5]
    column9 = same_envelope_columns["columns"][9]
    _require(
        column5["active_record_equal_non_ff_count"] == 0,
        "same-envelope column 5 non-FF equality changed",
    )
    _require(
        column9["active_record_equal_non_ff_count"] == 0,
        "same-envelope column 9 non-FF equality changed",
    )

    label_alignments = {
        target.dataset_id: _legacy_label_alignment(legacy, target)
        for target in (data0, data1, wf20, wf23)
    }
    _require(
        all(
            alignment["full_labeled_row_exact_match_count"] == 0
            for alignment in label_alignments.values()
        ),
        "a legacy labeled row unexpectedly acquired an exact target match",
    )

    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": "offline_identity_pinned_metadata_only_category_record_alignment",
        "datasets": {
            dataset_id: _dataset_metadata(dataset)
            for dataset_id, dataset in datasets.items()
        },
        "iar_same_object_structure": iar_provenance,
        "header_coordinate_equality": _header_comparisons(datasets),
        "exact_complete_row_comparisons": exact_pairs,
        "exact_11byte_record_comparisons": exact_record_pairs,
        "legacy_all_ff_record_mask_geometry_matches": geometry_pairs,
        "legacy_label_alignment": label_alignments,
        "DATA1_against_nine_row_offset_hypotheses": {
            target.dataset_id: _data1_offset_hypotheses(data1, target)
            for target in (data0, wf20, wf23)
        },
        "record_byte_column_comparisons": column_comparisons,
        "five_way_first_48_record_consensus": _multiway_column_consensus(
            (legacy, data0, data1, wf20, wf23)
        ),
        "adjudication": {
            "legacy_labels_directly_proven_only_for_legacy_rows": list(LEGACY_LABELS),
            "DATA0_first_six_rows_can_be_named_from_legacy": False,
            "reason_DATA0_labels_not_transferred": {
                "exact_complete_labeled_row_matches": 0,
                "same_ordinal_all_ff_record_mask_matches": 0,
                "positional_byte_distance_assignment_is_global_optimum": label_alignments[
                    DATA0_ID
                ]["one_to_one_byte_distance_assignment"][
                    "positional_assignment_is_optimal"
                ],
                "distance_or_ordinal_is_semantic_evidence": False,
            },
            "DATA0_row0_is_unique_nearest_to_legacy_VCOM_by_byte_distance": (
                label_alignments[DATA0_ID]["labeled_rows"][0][
                    "nearest_byte_distance_target_indices"
                ]
                == [0]
            ),
            "DATA0_row0_may_therefore_be_named_VCOM": False,
            "DATA0_shares_a_non_all_ff_11byte_record_with_legacy": (
                exact_record_pairs[f"{LEGACY_ID}__vs__{DATA0_ID}"][
                    "shared_unique_non_all_ff_record_count"
                ]
                > 0
            ),
            "WF20_and_WF23_row0_share_the_only_legacy_non_all_ff_record_cluster": (
                exact_record_pairs[f"{LEGACY_ID}__vs__{WF20_ID}"][
                    "shared_non_all_ff_record_clusters"
                ][0]["left_coordinates"]
                == [[0, 5], [0, 6], [0, 7]]
                and exact_record_pairs[f"{LEGACY_ID}__vs__{WF20_ID}"][
                    "shared_non_all_ff_record_clusters"
                ][0]["right_coordinates"]
                == [[0, 3], [0, 4], [0, 5], [0, 6], [0, 7]]
                and exact_record_pairs[f"{LEGACY_ID}__vs__{WF23_ID}"][
                    "shared_non_all_ff_record_clusters"
                ][0]["right_coordinates"]
                == [[0, 6], [0, 7]]
            ),
            "WF20_WF23_row0_is_structurally_consistent_with_legacy_VCOM": True,
            "shared_row0_cluster_byte_count": 11,
            "shared_row0_cluster_ff_byte_count": 10,
            "shared_row0_cluster_non_ff_byte_count": 1,
            "shared_row0_cluster_distinct_value_count": 2,
            "shared_row0_cluster_is_low_information_filler_compatible": True,
            "shared_row0_cluster_supports_a_VCOM_category_candidate": False,
            "WF20_WF23_row0_is_therefore_proven_to_be_VCOM": False,
            "legacy_Power_index5_and_mode1_index5_have_same_complete_row": False,
            "all_ff_complete_row_identity_carries_a_color_or_power_label": False,
            "DATA0_DATA1_same_object_adjacency_proves_row_offset": False,
            "DATA1_non_all_ff_row_exact_match_to_DATA0_under_offset0_or1": False,
            "WF20_WF23_coordinate_indices_are_directly_comparable": True,
            "WF20_WF23_category_names_are_proven": False,
            "record_byte_column_indices_are_structurally_preserved_within_each_dataset": True,
            "every_record_byte_column_changes_somewhere_between_WF20_and_WF23": (
                not same_envelope_columns["fully_invariant_column_indices"]
            ),
            "same_envelope_columns_5_and_9_have_high_equality_but_all_active_equalities_are_FF": (
                column5["active_record_equal_count"]
                == column5["active_record_equal_ff_count"]
                and column9["active_record_equal_count"]
                == column9["active_record_equal_ff_count"]
            ),
            "DATA0_column9_is_constant_all_ff": (
                datasets[DATA0_ID].records
                and all(record[9] == 0xFF for record in datasets[DATA0_ID].records)
            ),
            "constant_or_stable_column_is_a_phase_timing_or_voltage_field": False,
            "any_of_11_columns_can_be_named_from_current_evidence": False,
            "category_mapping_proven": False,
            "phase_mapping_proven": False,
            "electrical_field_mapping_proven": False,
        },
        "evidence_grades": {
            "A_direct_vendor_label": [
                f"{LEGACY_ID}.row[{index}]={label}"
                for index, label in enumerate(LEGACY_LABELS)
            ],
            "B_same_envelope_coordinate_alignment": [
                "WF20_25 and WF23_25 rows 0..8, records 0..7, byte columns 0..10"
            ],
            "C_cross_generation_structural_hypotheses": [
                "legacy/DATA0/WF first-six row ordinals",
                "DATA1 versus nine-row target offsets 0 and 1",
                "nearest and globally optimized Hamming assignments",
            ],
            "U_unproven_names": [
                "all DATA0 rows",
                "all DATA1 rows",
                "all WF20_25/WF23_25 rows",
                "all 11 record-byte fields",
            ],
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
            "raw_waveform_bytes_or_key_emitted": False,
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
        CategoryAlignmentAuditError,
        geometry.PhaseGeometryAuditError,
        profile_pack.ProfilePackError,
        iar_arrays.DataCompatibilityAuditError,
        DurableWriteError,
        OSError,
        UnicodeError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
