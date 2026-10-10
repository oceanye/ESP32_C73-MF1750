#!/usr/bin/env python3
"""Compare frozen waveform byte structures without assigning field semantics.

This offline audit loads two decoded 800-byte vendor profiles, the labeled
legacy 535-byte initializer, the legacy IAR 704-byte DATA1 constant, and the
independent ArmCC 704-byte constant.  It emits only identities and structural
statistics: byte-position equality, 11-byte record grouping, change clusters,
entropy, and exact-repeat metadata.  It never emits raw waveform bytes,
constructs a runtime payload, or authorizes hardware use.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Final, Iterable, Sequence


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.application.durable_io import (  # noqa: E402
    DurableWriteError,
    write_new_bytes_durable,
)
from tools import e2802_r43_lut_proof as iar_proof  # noqa: E402
from tools import mf1750_spd1657_reverse_delta as reverse_delta  # noqa: E402
from tools import mf1750_spd1657_vendor_profile_pack as profile_pack  # noqa: E402


KIND: Final = "mf1750-spd1657-waveform-invariant-stats"
SCHEMA_VERSION: Final = 1
REFERENCE_ROOT: Final = profile_pack.DEFAULT_REFERENCE_ROOT

RECORD_BYTES: Final = 11
RECORDS_PER_BLOCK: Final = 8
PROFILE_PREFIX_BYTES: Final = 7
PROFILE_RECORD_BYTES: Final = 9 * RECORDS_PER_BLOCK * RECORD_BYTES
PROFILE_SUFFIX_BYTES: Final = 1
LEGACY_535_RECORD_BYTES: Final = 6 * RECORDS_PER_BLOCK * RECORD_BYTES

LEGACY_535_SOURCE_REL: Final = Path("User/EDP_init.c")
LEGACY_535_SOURCE_BYTES: Final = 32_220
LEGACY_535_SOURCE_SHA256: Final = (
    "1b6bbcf35cefc338f7ab9b76c04c869f9a82e800c4ccaa52d204d9fd6e53b7a5"
)
LEGACY_535_SHA256: Final = (
    "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b"
)

ARMCC_LUT1_START: Final = 0x1B54
ARMCC_LUT1_END: Final = 0x1E14


class WaveformStatsError(RuntimeError):
    """Raised when a frozen identity or structural invariant changes."""


@dataclass(frozen=True)
class Dataset:
    """One identity-pinned byte array and its record-bearing region."""

    name: str
    payload: bytes
    record_offset: int
    record_bytes: int
    provenance: dict[str, Any]

    @property
    def records_payload(self) -> bytes:
        return self.payload[self.record_offset : self.record_offset + self.record_bytes]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WaveformStatsError(message)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _ranges(indices: Iterable[int], *, unit: str = "byte") -> list[dict[str, Any]]:
    ordered = sorted(set(indices))
    if not ordered:
        return []
    result: list[dict[str, Any]] = []
    start = previous = ordered[0]
    for value in ordered[1:]:
        if value == previous + 1:
            previous = value
            continue
        result.append(
            {
                "start": start,
                "end_exclusive": previous + 1,
                "count": previous - start + 1,
                "unit": unit,
            }
        )
        start = previous = value
    result.append(
        {
            "start": start,
            "end_exclusive": previous + 1,
            "count": previous - start + 1,
            "unit": unit,
        }
    )
    return result


def _shannon_entropy(payload: Sequence[int]) -> float:
    if not payload:
        return 0.0
    counts = Counter(payload)
    total = len(payload)
    value = -sum(
        (count / total) * math.log2(count / total) for count in counts.values()
    )
    # Avoid serializing negative zero for a uniform byte array.
    return 0.0 if abs(value) < 0.5e-12 else round(value, 12)


def _split_records(payload: bytes) -> list[bytes]:
    _require(
        len(payload) % RECORD_BYTES == 0,
        f"record region is not divisible by {RECORD_BYTES}",
    )
    return [
        payload[offset : offset + RECORD_BYTES]
        for offset in range(0, len(payload), RECORD_BYTES)
    ]


def _same_byte_runs(payload: bytes) -> list[tuple[int, int]]:
    if not payload:
        return []
    result: list[tuple[int, int]] = []
    start = 0
    for offset in range(1, len(payload) + 1):
        if offset == len(payload) or payload[offset] != payload[start]:
            result.append((start, offset))
            start = offset
    return result


def _record_streaks(records: list[bytes]) -> list[dict[str, Any]]:
    if not records:
        return []
    result: list[dict[str, Any]] = []
    start = 0
    for index in range(1, len(records) + 1):
        if index == len(records) or records[index] != records[start]:
            if index - start > 1:
                result.append(
                    {
                        "start_record": start,
                        "end_record_exclusive": index,
                        "record_count": index - start,
                        "record_sha256": _sha256(records[start]),
                    }
                )
            start = index
    return result


def _minimal_record_period(records: list[bytes]) -> int:
    if not records:
        return 0
    for period in range(1, len(records) + 1):
        if len(records) % period == 0 and all(
            record == records[index % period] for index, record in enumerate(records)
        ):
            return period
    return len(records)


def _dataset_statistics(dataset: Dataset) -> dict[str, Any]:
    record_payload = dataset.records_payload
    _require(
        dataset.record_offset + dataset.record_bytes <= len(dataset.payload),
        f"{dataset.name} record region exceeds payload",
    )
    records = _split_records(record_payload)
    duplicate_coordinates: dict[bytes, list[int]] = {}
    for index, record in enumerate(records):
        duplicate_coordinates.setdefault(record, []).append(index)
    duplicate_clusters = [
        {
            "record_sha256": _sha256(record),
            "record_indices": indices,
            "record_count": len(indices),
            "uniform_record": len(set(record)) == 1,
        }
        for record, indices in duplicate_coordinates.items()
        if len(indices) > 1
    ]
    duplicate_clusters.sort(
        key=lambda item: (
            -int(item["record_count"]),
            list(item["record_indices"]),
            str(item["record_sha256"]),
        )
    )

    same_byte_runs = _same_byte_runs(record_payload)
    long_runs = [
        {
            "start": start,
            "end_exclusive": end,
            "bytes": end - start,
            "byte_value_emitted": False,
        }
        for start, end in same_byte_runs
        if end - start >= RECORD_BYTES
    ]
    value_counts = sorted(Counter(record_payload).values(), reverse=True)
    block_reports = []
    for block_index in range(len(records) // RECORDS_PER_BLOCK):
        block = b"".join(
            records[
                block_index * RECORDS_PER_BLOCK : (block_index + 1) * RECORDS_PER_BLOCK
            ]
        )
        block_reports.append(
            {
                "block_index": block_index,
                "bytes": len(block),
                "sha256": _sha256(block),
                "shannon_entropy_bits_per_byte": _shannon_entropy(block),
                "unique_byte_count": len(set(block)),
                "unique_record_count": len(
                    set(
                        records[
                            block_index * RECORDS_PER_BLOCK : (block_index + 1)
                            * RECORDS_PER_BLOCK
                        ]
                    )
                ),
            }
        )

    prefix = dataset.payload[: dataset.record_offset]
    suffix = dataset.payload[dataset.record_offset + dataset.record_bytes :]
    period = _minimal_record_period(records)
    return {
        "bytes": len(dataset.payload),
        "sha256": _sha256(dataset.payload),
        "provenance": dataset.provenance,
        "record_region": {
            "offset": dataset.record_offset,
            "bytes": len(record_payload),
            "sha256": _sha256(record_payload),
            "record_bytes": RECORD_BYTES,
            "record_count": len(records),
            "records_per_structural_block": RECORDS_PER_BLOCK,
            "structural_block_count": len(block_reports),
            "prefix_bytes": len(prefix),
            "prefix_sha256": _sha256(prefix) if prefix else None,
            "suffix_bytes": len(suffix),
            "suffix_sha256": _sha256(suffix) if suffix else None,
        },
        "entropy_and_concentration": {
            "shannon_entropy_bits_per_byte": _shannon_entropy(record_payload),
            "unique_byte_count": len(set(record_payload)),
            "four_largest_symbol_counts_without_values": value_counts[:4],
            "record_byte_index_entropy_bits": [
                _shannon_entropy([record[index] for record in records])
                for index in range(RECORD_BYTES)
            ],
            "record_byte_index_unique_value_counts": [
                len({record[index] for record in records})
                for index in range(RECORD_BYTES)
            ],
            "raw_symbol_values_emitted": False,
        },
        "exact_record_repetition": {
            "unique_record_count": len(set(records)),
            "duplicate_cluster_count": len(duplicate_clusters),
            "records_participating_in_duplicate_clusters": sum(
                int(cluster["record_count"]) for cluster in duplicate_clusters
            ),
            "adjacent_equal_pair_count": sum(
                left == right for left, right in zip(records, records[1:])
            ),
            "uniform_record_count": sum(len(set(record)) == 1 for record in records),
            "minimal_exact_record_period": period,
            "whole_sequence_is_single_record_repeat": period == 1,
            "adjacent_equal_streaks": _record_streaks(records),
            "duplicate_record_clusters": duplicate_clusters,
            "equal_record_pairs_by_lag_1_to_8": [
                {
                    "lag_records": lag,
                    "compared_pairs": len(records) - lag,
                    "equal_pairs": sum(
                        records[index] == records[index + lag]
                        for index in range(len(records) - lag)
                    ),
                }
                for lag in range(1, min(RECORDS_PER_BLOCK, len(records) - 1) + 1)
            ],
        },
        "same_byte_runs": {
            "run_count": len(same_byte_runs),
            "longest_run_bytes": max(
                (end - start for start, end in same_byte_runs), default=0
            ),
            "runs_at_least_one_record": long_runs,
            "byte_values_emitted": False,
        },
        "structural_blocks": block_reports,
        "raw_waveform_bytes_emitted": False,
    }


def _pairwise_comparison(
    *,
    left_name: str,
    left: bytes,
    right_name: str,
    right: bytes,
    left_offset_basis: int,
    right_offset_basis: int,
    record_aligned: bool,
    interpretation: str,
) -> dict[str, Any]:
    _require(len(left) == len(right), "pairwise comparison lengths differ")
    equal = [index for index, pair in enumerate(zip(left, right)) if pair[0] == pair[1]]
    different = [
        index for index, pair in enumerate(zip(left, right)) if pair[0] != pair[1]
    ]
    result: dict[str, Any] = {
        "left": left_name,
        "right": right_name,
        "bytes": len(left),
        "left_offset_basis": left_offset_basis,
        "right_offset_basis": right_offset_basis,
        "equal_byte_positions": len(equal),
        "different_byte_positions": len(different),
        "equal_position_ranges": _ranges(equal),
        "different_position_ranges": _ranges(different),
        "longest_equal_position_run": max(
            (int(row["count"]) for row in _ranges(equal)), default=0
        ),
        "longest_different_position_run": max(
            (int(row["count"]) for row in _ranges(different)), default=0
        ),
        "interpretation": interpretation,
        "raw_byte_values_emitted": False,
    }
    if not record_aligned:
        return result

    _require(len(left) % RECORD_BYTES == 0, "record comparison is not 11-byte aligned")
    left_records = _split_records(left)
    right_records = _split_records(right)
    equal_record_indices = [
        index
        for index, pair in enumerate(zip(left_records, right_records))
        if pair[0] == pair[1]
    ]
    different_by_record = [
        sum(a != b for a, b in zip(left_record, right_record))
        for left_record, right_record in zip(left_records, right_records)
    ]
    equal_inside_nonidentical_records = sum(
        RECORD_BYTES - different_by_record[index]
        for index in range(len(left_records))
        if index not in set(equal_record_indices)
    )
    result["record_comparison"] = {
        "record_bytes": RECORD_BYTES,
        "record_count": len(left_records),
        "exact_equal_record_count": len(equal_record_indices),
        "exact_equal_record_indices": equal_record_indices,
        "exact_equal_record_ranges": _ranges(equal_record_indices, unit="record"),
        "records_with_any_difference": sum(count > 0 for count in different_by_record),
        "different_byte_count_by_record": different_by_record,
        "different_counts_by_record_byte_index": [
            sum(
                left_record[index] != right_record[index]
                for left_record, right_record in zip(left_records, right_records)
            )
            for index in range(RECORD_BYTES)
        ],
        "equal_positions_inside_nonidentical_records": (
            equal_inside_nonidentical_records
        ),
    }
    return result


def _three_way_common_region(
    *,
    first_name: str,
    first: bytes,
    second_name: str,
    second: bytes,
    third_name: str,
    third: bytes,
) -> dict[str, Any]:
    _require(len(first) == len(second) == len(third), "three-way lengths differ")
    _require(len(first) % RECORD_BYTES == 0, "three-way region is not record aligned")
    classes: dict[str, list[int]] = {
        "all_equal": [],
        f"{first_name}_equals_{second_name}_only": [],
        f"{first_name}_equals_{third_name}_only": [],
        f"{second_name}_equals_{third_name}_only": [],
        "all_distinct": [],
    }
    for index, (a, b, c) in enumerate(zip(first, second, third)):
        if a == b == c:
            key = "all_equal"
        elif a == b:
            key = f"{first_name}_equals_{second_name}_only"
        elif a == c:
            key = f"{first_name}_equals_{third_name}_only"
        elif b == c:
            key = f"{second_name}_equals_{third_name}_only"
        else:
            key = "all_distinct"
        classes[key].append(index)

    record_triplets = zip(
        _split_records(first), _split_records(second), _split_records(third)
    )
    exact_equal_records = [
        index for index, (a, b, c) in enumerate(record_triplets) if a == b == c
    ]
    return {
        "datasets": [first_name, second_name, third_name],
        "bytes": len(first),
        "record_count": len(first) // RECORD_BYTES,
        "classes": {
            name: {
                "byte_positions": len(indices),
                "position_ranges": _ranges(indices),
                "counts_by_record_byte_index": [
                    sum(index % RECORD_BYTES == byte_index for index in indices)
                    for byte_index in range(RECORD_BYTES)
                ],
            }
            for name, indices in classes.items()
        },
        "exact_equal_record_indices": exact_equal_records,
        "exact_equal_record_count": len(exact_equal_records),
        "interpretation": (
            "index-aligned structural coincidence only; no shared field meaning is "
            "assigned across generations"
        ),
        "raw_byte_values_emitted": False,
    }


def _four_way_invariants(names: list[str], payloads: list[bytes]) -> dict[str, Any]:
    _require(len(names) == len(payloads) == 4, "four-way input count changed")
    _require(
        len({len(payload) for payload in payloads}) == 1, "four-way lengths differ"
    )
    byte_count = len(payloads[0])
    _require(byte_count % RECORD_BYTES == 0, "four-way region is not record aligned")
    all_equal = [
        index for index, values in enumerate(zip(*payloads)) if len(set(values)) == 1
    ]
    record_rows = [_split_records(payload) for payload in payloads]
    exact_records = [
        index for index, values in enumerate(zip(*record_rows)) if len(set(values)) == 1
    ]
    return {
        "datasets": names,
        "bytes": byte_count,
        "record_count": byte_count // RECORD_BYTES,
        "all_equal_byte_positions": len(all_equal),
        "all_equal_position_ranges": _ranges(all_equal),
        "all_equal_counts_by_record_byte_index": [
            sum(index % RECORD_BYTES == byte_index for index in all_equal)
            for byte_index in range(RECORD_BYTES)
        ],
        "exact_equal_record_indices": exact_records,
        "exact_equal_record_count": len(exact_records),
        "interpretation": (
            "index-aligned structural coincidence only; invariance across these four "
            "artifacts does not establish a field or controller semantic"
        ),
        "raw_byte_values_emitted": False,
    }


def _load_datasets() -> dict[str, Dataset]:
    result: dict[str, Dataset] = {}
    for profile_id in ("WF20_25", "WF23_25"):
        material = profile_pack.load_profile(profile_id)
        _require(len(material.plaintext) == 800, f"{profile_id} length changed")
        _require(
            _sha256(material.plaintext) == material.spec.plaintext_sha256,
            f"{profile_id} decoded identity changed",
        )
        result[profile_id] = Dataset(
            name=profile_id,
            payload=material.plaintext,
            record_offset=PROFILE_PREFIX_BYTES,
            record_bytes=PROFILE_RECORD_BYTES,
            provenance={
                "source_path": material.spec.source_relative.as_posix(),
                "source_bytes": material.source_bytes,
                "source_sha256": material.spec.source_sha256,
                "wrapper_bytes": material.spec.wrapper_bytes,
                "wrapper_sha256": material.spec.wrapper_sha256,
                "decoded_sha256": material.spec.plaintext_sha256,
                "identity_pinned_by_profile_pack": True,
            },
        )

    legacy_source_path = REFERENCE_ROOT / LEGACY_535_SOURCE_REL
    _require(legacy_source_path.is_file(), "legacy 535 source is missing")
    legacy_source = legacy_source_path.read_bytes()
    _require(
        len(legacy_source) == LEGACY_535_SOURCE_BYTES, "legacy source size changed"
    )
    _require(
        _sha256(legacy_source) == LEGACY_535_SOURCE_SHA256,
        "legacy source identity changed",
    )
    legacy_535 = reverse_delta._extract_initializer(legacy_source, "wf_data")
    _require(len(legacy_535) == 535, "legacy wf_data length changed")
    _require(_sha256(legacy_535) == LEGACY_535_SHA256, "legacy wf_data changed")
    result["legacy_wf_data_535"] = Dataset(
        name="legacy_wf_data_535",
        payload=legacy_535,
        record_offset=PROFILE_PREFIX_BYTES,
        record_bytes=LEGACY_535_RECORD_BYTES,
        provenance={
            "source_path": LEGACY_535_SOURCE_REL.as_posix(),
            "source_bytes": len(legacy_source),
            "source_sha256": _sha256(legacy_source),
            "initializer_name": "wf_data",
            "initializer_sha256": _sha256(legacy_535),
            "identity_pinned": True,
        },
    )

    iar_report = iar_proof.prove_object()
    iar_object = iar_proof.DEFAULT_OBJECT_PATH.read_bytes()
    iar_contract = iar_proof.DATA_SECTIONS["DATA1"]
    iar_data1, encoded_end = iar_proof.extract_tagged_bytes(
        iar_object,
        section_id=int(iar_contract["section_id"]),
        marker_offset=int(iar_contract["marker_offset"]),
    )
    _require(
        encoded_end == int(iar_contract["encoded_end_offset"]), "IAR DATA1 end changed"
    )
    _require(len(iar_data1) == 704, "IAR DATA1 length changed")
    _require(
        _sha256(iar_data1) == reverse_delta.EXPECTED_IDENTITIES["legacy_iar_data1"],
        "IAR DATA1 identity changed",
    )
    result["legacy_iar_data1_704"] = Dataset(
        name="legacy_iar_data1_704",
        payload=iar_data1,
        record_offset=0,
        record_bytes=len(iar_data1),
        provenance={
            "source_path": iar_report["object"]["relative_path"],
            "source_bytes": iar_report["object"]["size_bytes"],
            "source_sha256": iar_report["object"]["sha256"],
            "ubrof_section_id": iar_report["tagged_arrays"]["DATA1"]["section_id"],
            "decoded_sha256": _sha256(iar_data1),
            "identity_pinned_by_iar_proof": True,
        },
    )

    library_path = REFERENCE_ROOT / reverse_delta.LIBRARY_REL
    _require(library_path.is_file(), "ArmCC library is missing")
    library = library_path.read_bytes()
    _require(
        _sha256(library) == reverse_delta.EXPECTED_IDENTITIES["library"],
        "ArmCC library identity changed",
    )
    object_body, archive_data_offset = reverse_delta._parse_ar_member(
        library, reverse_delta.EXPECTED_OBJECT_NAME
    )
    _require(
        _sha256(object_body) == reverse_delta.EXPECTED_IDENTITIES["library_object"],
        "ArmCC object identity changed",
    )
    armcc_lut1 = object_body[ARMCC_LUT1_START:ARMCC_LUT1_END]
    _require(len(armcc_lut1) == 704, "ArmCC LUT1 length changed")
    _require(
        _sha256(armcc_lut1) == reverse_delta.EXPECTED_IDENTITIES["lut1_ff_704"],
        "ArmCC LUT1 identity changed",
    )
    result["armcc_lut1_704"] = Dataset(
        name="armcc_lut1_704",
        payload=armcc_lut1,
        record_offset=0,
        record_bytes=len(armcc_lut1),
        provenance={
            "source_path": reverse_delta.LIBRARY_REL.as_posix(),
            "source_bytes": len(library),
            "source_sha256": _sha256(library),
            "archive_member": reverse_delta.EXPECTED_OBJECT_NAME,
            "archive_member_data_offset": archive_data_offset,
            "archive_member_bytes": len(object_body),
            "archive_member_sha256": _sha256(object_body),
            "member_slice": {
                "start": ARMCC_LUT1_START,
                "end_exclusive": ARMCC_LUT1_END,
            },
            "decoded_sha256": _sha256(armcc_lut1),
            "identity_pinned": True,
        },
    )
    return result


def build_report() -> dict[str, Any]:
    """Build an identity-pinned, metadata-only structural comparison."""

    datasets = _load_datasets()
    wf20 = datasets["WF20_25"]
    wf23 = datasets["WF23_25"]
    legacy535 = datasets["legacy_wf_data_535"]
    iar704 = datasets["legacy_iar_data1_704"]
    armcc704 = datasets["armcc_lut1_704"]
    dataset_reports = {
        name: _dataset_statistics(dataset) for name, dataset in datasets.items()
    }

    profile_full = _pairwise_comparison(
        left_name=wf20.name,
        left=wf20.payload,
        right_name=wf23.name,
        right=wf23.payload,
        left_offset_basis=0,
        right_offset_basis=0,
        record_aligned=False,
        interpretation="same-envelope profile comparison",
    )
    profile_header = _pairwise_comparison(
        left_name=wf20.name,
        left=wf20.payload[:PROFILE_PREFIX_BYTES],
        right_name=wf23.name,
        right=wf23.payload[:PROFILE_PREFIX_BYTES],
        left_offset_basis=0,
        right_offset_basis=0,
        record_aligned=False,
        interpretation="opaque prefix comparison",
    )
    profile_records = _pairwise_comparison(
        left_name=wf20.name,
        left=wf20.records_payload,
        right_name=wf23.name,
        right=wf23.records_payload,
        left_offset_basis=PROFILE_PREFIX_BYTES,
        right_offset_basis=PROFILE_PREFIX_BYTES,
        record_aligned=True,
        interpretation=(
            "same-envelope 11-byte record comparison; equal means invariant only "
            "across these two supplied profiles"
        ),
    )
    profile_suffix = _pairwise_comparison(
        left_name=wf20.name,
        left=wf20.payload[-PROFILE_SUFFIX_BYTES:],
        right_name=wf23.name,
        right=wf23.payload[-PROFILE_SUFFIX_BYTES:],
        left_offset_basis=len(wf20.payload) - PROFILE_SUFFIX_BYTES,
        right_offset_basis=len(wf23.payload) - PROFILE_SUFFIX_BYTES,
        record_aligned=False,
        interpretation="opaque trailing-byte comparison",
    )

    common_535_bytes = LEGACY_535_RECORD_BYTES
    common_704_bytes = 64 * RECORD_BYTES
    first_48 = {
        name: dataset.records_payload[:common_535_bytes]
        for name, dataset in datasets.items()
    }
    first_64 = {
        name: dataset.records_payload[:common_704_bytes]
        for name, dataset in datasets.items()
        if len(dataset.records_payload) >= common_704_bytes
    }

    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": "offline_identity_pinned_metadata_only_no_payload_generation",
        "datasets": dataset_reports,
        "comparisons": {
            "same_envelope_profiles": {
                "full_800": profile_full,
                "opaque_prefix_7": profile_header,
                "record_body_792": profile_records,
                "opaque_suffix_1": profile_suffix,
            },
            "legacy_535_index_alignment_only": {
                "WF20_25_vs_legacy_wf_data_535": _pairwise_comparison(
                    left_name=wf20.name,
                    left=first_48[wf20.name],
                    right_name=legacy535.name,
                    right=first_48[legacy535.name],
                    left_offset_basis=PROFILE_PREFIX_BYTES,
                    right_offset_basis=PROFILE_PREFIX_BYTES,
                    record_aligned=True,
                    interpretation=(
                        "cross-generation first-48-record index alignment only"
                    ),
                ),
                "WF23_25_vs_legacy_wf_data_535": _pairwise_comparison(
                    left_name=wf23.name,
                    left=first_48[wf23.name],
                    right_name=legacy535.name,
                    right=first_48[legacy535.name],
                    left_offset_basis=PROFILE_PREFIX_BYTES,
                    right_offset_basis=PROFILE_PREFIX_BYTES,
                    record_aligned=True,
                    interpretation=(
                        "cross-generation first-48-record index alignment only"
                    ),
                ),
            },
            "legacy_704_pair": _pairwise_comparison(
                left_name=iar704.name,
                left=iar704.records_payload,
                right_name=armcc704.name,
                right=armcc704.records_payload,
                left_offset_basis=0,
                right_offset_basis=0,
                record_aligned=True,
                interpretation=(
                    "two separately sourced 704-byte constants; equality does not "
                    "prove equivalent use"
                ),
            ),
            "profile_first_64_vs_legacy_iar_704_index_alignment_only": {
                "WF20_25": _pairwise_comparison(
                    left_name=wf20.name,
                    left=first_64[wf20.name],
                    right_name=iar704.name,
                    right=iar704.records_payload,
                    left_offset_basis=PROFILE_PREFIX_BYTES,
                    right_offset_basis=0,
                    record_aligned=True,
                    interpretation=(
                        "cross-generation first-64-record index alignment only"
                    ),
                ),
                "WF23_25": _pairwise_comparison(
                    left_name=wf23.name,
                    left=first_64[wf23.name],
                    right_name=iar704.name,
                    right=iar704.records_payload,
                    left_offset_basis=PROFILE_PREFIX_BYTES,
                    right_offset_basis=0,
                    record_aligned=True,
                    interpretation=(
                        "cross-generation first-64-record index alignment only"
                    ),
                ),
            },
            "common_first_48_records": {
                "three_way_profiles_and_legacy_535": _three_way_common_region(
                    first_name=wf20.name,
                    first=first_48[wf20.name],
                    second_name=wf23.name,
                    second=first_48[wf23.name],
                    third_name=legacy535.name,
                    third=first_48[legacy535.name],
                ),
                "four_way_including_legacy_iar_704": _four_way_invariants(
                    [wf20.name, wf23.name, legacy535.name, iar704.name],
                    [
                        first_48[wf20.name],
                        first_48[wf23.name],
                        first_48[legacy535.name],
                        first_48[iar704.name],
                    ],
                ),
            },
        },
        "bounded_findings": {
            "same_envelope_profile_pair": {
                "full_equal_positions": profile_full["equal_byte_positions"],
                "full_different_positions": profile_full["different_byte_positions"],
                "record_body_equal_positions": profile_records["equal_byte_positions"],
                "record_body_different_positions": profile_records[
                    "different_byte_positions"
                ],
                "exact_equal_records": profile_records["record_comparison"][
                    "exact_equal_record_count"
                ],
                "equal_positions_inside_nonidentical_records": profile_records[
                    "record_comparison"
                ]["equal_positions_inside_nonidentical_records"],
                "every_record_byte_index_varies_somewhere": all(
                    count > 0
                    for count in profile_records["record_comparison"][
                        "different_counts_by_record_byte_index"
                    ]
                ),
                "profile_dependent_opaque_coordinate_count": profile_records[
                    "different_byte_positions"
                ],
                "pair_invariant_opaque_coordinate_count": profile_records[
                    "equal_byte_positions"
                ],
                "pair_invariant_is_not_universal_invariant": True,
            },
            "entropy_bits_per_byte": {
                name: dataset_reports[name]["entropy_and_concentration"][
                    "shannon_entropy_bits_per_byte"
                ]
                for name in datasets
            },
            "legacy_704_constants_are_not_identical": (
                iar704.payload != armcc704.payload
            ),
            "cross_generation_alignment_establishes_field_semantics": False,
            "profile_variation_establishes_voltage_or_phase_semantics": False,
        },
        "semantic_boundary": {
            "eleven_bytes_are_treated_as_structural_records_only": True,
            "voltage_fields_assigned": False,
            "phase_or_duration_fields_assigned": False,
            "pixel_code_or_color_mapping_assigned": False,
            "uniform_or_repeated_byte_meaning_assigned": False,
            "cross_generation_record_index_equivalence_claimed": False,
            "runtime_payload_generated": False,
            "live_hardware_use_authorized": False,
        },
        "safety": {
            "offline_only": True,
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "device_network_accessed": False,
            "firmware_or_flash_written": False,
            "display_refresh_attempted": False,
            "authorization_token_generated_or_claimed": False,
            "raw_waveform_bytes_emitted": False,
            "runtime_payload_generated": False,
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
        WaveformStatsError,
        profile_pack.ProfilePackError,
        reverse_delta.ReverseAuditError,
        iar_proof.ProofError,
        DurableWriteError,
        OSError,
        UnicodeError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
