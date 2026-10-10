#!/usr/bin/env python3
"""Construct and prove the offline G1/S1 root-cause 2x2 V3 bundle.

V2 froze the global and per-half MAP-to-target transition contracts, but its
spatial metrics still differed across the two B levels.  V3 starts from those
deep-validated V2 rasters and jointly exchanges pixels only inside one
``(controller half, MAP old code)`` group.  Such an exchange cannot alter a
per-half transition cell, histogram, or changed-pixel count.  A deterministic
joint solver then drives the preregistered spatial-metric differences to exact
zero independently at the high and low A levels.

This file has no HTTP, device, upload, refresh, claim, or authorization path.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
from typing import Any, Mapping, Optional, Sequence
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.color_pipeline import encode_rgb_png, reference_palette  # noqa: E402
from host.epd_frame import (  # noqa: E402
    CONTROLLER_FRAME_BYTES,
    FRAME_BYTES,
    HEIGHT,
    WIDTH,
    controller_stream,
    fnv1a,
    pack_pixels,
    validate_frame,
)
from host.visible_refresh_campaign import (  # noqa: E402
    CAMPAIGN_KIND,
    build_fixed_action_declaration,
    build_session_contract,
    describe_action_offline,
    seal_campaign_contract,
)
from tools import g1_s1_clustered_quality_candidate as clustered  # noqa: E402
from tools import g1_s1_low_spatial_diagnostic as low_spatial  # noqa: E402
from tools import g1_s1_root_cause_2x2_candidate as v2  # noqa: E402


SCHEMA_VERSION = 3
MANIFEST_KIND = "mf1750-g1-s1-root-cause-2x2-v3-offline-bundle"
PROOF_KIND = "mf1750-g1-s1-root-cause-2x2-v3-joint-proof"
MANIFEST_HASH_SCOPE = (
    "entire V3 manifest excluding manifest_integrity; UTF-8 JSON with sorted "
    "keys, no whitespace, ensure_ascii=false, allow_nan=false"
)
PROOF_HASH_SCOPE = (
    "entire V3 proof excluding proof_integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
ALGORITHM_ID = "same-map-group-joint-spatial-equality-solver-v1"
SOLVER_PRNG = "splitmix64-v1-modulo-index"
SOLVER_SEED = 1
SOLVER_MAX_PROPOSALS = 150_000
SOLVER_OBJECTIVE_WEIGHTS = (1, 1, 100, 2)
METRIC_ORDER = (
    "internal_left_edges",
    "internal_right_edges",
    "controller_seam",
    "boundary_pixels",
)
PREREGISTERED_METRICS = (
    "total_four_neighbour_edges",
    "internal_left_edges",
    "internal_right_edges",
    "boundary_pixels",
    "controller_seam",
)
VARIANT_NAMES = v2.VARIANT_NAMES
CAMPAIGN_CELL_ORDER = (
    "low-balanced",
    "low-unbalanced",
    "high-balanced",
    "high-unbalanced",
)
PHYSICAL_CODE_ORDER = v2.PHYSICAL_CODE_ORDER
GLOBAL_COUNTS = v2.GLOBAL_COUNTS
GLOBAL_TRANSITION_MATRIX = v2.GLOBAL_TRANSITION_MATRIX
EXPECTED_CHANGED_PIXELS = v2.EXPECTED_CHANGED_PIXELS
V2_MANIFEST_FILE_SHA256 = v2.EXPECTED_MANIFEST_FILE_SHA256
V2_MANIFEST_CANONICAL_SHA256 = v2.EXPECTED_MANIFEST_CANONICAL_SHA256

CONTACT_GUTTER = 4
CONTACT_WIDTH = 2 * WIDTH + CONTACT_GUTTER
CONTACT_HEIGHT = 2 * HEIGHT + CONTACT_GUTTER
CONTACT_LAYOUT = {
    "high-unbalanced": [0, 0],
    "high-balanced": [WIDTH + CONTACT_GUTTER, 0],
    "low-unbalanced": [0, HEIGHT + CONTACT_GUTTER],
    "low-balanced": [WIDTH + CONTACT_GUTTER, HEIGHT + CONTACT_GUTTER],
}
REQUIRED_FILES = frozenset(
    {
        "manifest.json",
        "proof-manifest.json",
        "contact-sheet.png",
        *(f"{name}.frame.bin" for name in VARIANT_NAMES),
        *(f"{name}.strict-final.png" for name in VARIANT_NAMES),
    }
)

EXPECTED_PROOF_FILE_SHA256: Optional[str] = (
    "3b1a41fc2b772adf12286a7ae41745ef074a50b401e377597041fc38081115ef"
)
EXPECTED_PROOF_CANONICAL_SHA256: Optional[str] = (
    "9566f7198b5fa2ed26b3cc386a9faa23a8a99ff7bace604e164eb7b159b87be5"
)
EXPECTED_MANIFEST_FILE_SHA256: Optional[str] = (
    "17a820d84cb24fe0950a9653d6f6831104e0d872f7167c47f262c18fad559bfb"
)
EXPECTED_MANIFEST_CANONICAL_SHA256: Optional[str] = (
    "3f4852af1151d5c56db1d7c540f3c131ae6c05de1dce8db625864b2900d0e6d7"
)


class V3FactorialError(RuntimeError):
    """Raised when the V3 exact joint contract cannot be proven."""


@dataclass(frozen=True)
class VariantArtifacts:
    codes: bytes
    frame: bytes
    strict_png: bytes


@dataclass(frozen=True)
class V3Artifacts:
    variants: Mapping[str, VariantArtifacts]
    contact_png: bytes
    proof: Mapping[str, Any]
    proof_bytes: bytes
    manifest: Mapping[str, Any]
    manifest_bytes: bytes

    def files(self) -> dict[str, bytes]:
        result = {
            "manifest.json": self.manifest_bytes,
            "proof-manifest.json": self.proof_bytes,
            "contact-sheet.png": self.contact_png,
        }
        for name, variant in self.variants.items():
            result[f"{name}.frame.bin"] = variant.frame
            result[f"{name}.strict-final.png"] = variant.strict_png
        return result


def _sha256(payload: bytes | bytearray | memoryview) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise V3FactorialError(f"canonical JSON encoding failed: {error}") from error


def _matrix_record(matrix: Sequence[Sequence[int]]) -> list[list[int]]:
    return [list(row) for row in matrix]


def _half_bytes(codes: bytes, side: int) -> bytes:
    x0 = side * (WIDTH // 2)
    return b"".join(
        codes[y * WIDTH + x0 : y * WIDTH + x0 + WIDTH // 2]
        for y in range(HEIGHT)
    )


def _counts(codes: bytes) -> tuple[int, ...]:
    return tuple(codes.count(code) for code in PHYSICAL_CODE_ORDER)


def _metric_vector(codes: bytes | bytearray) -> tuple[int, int, int, int]:
    metrics = low_spatial.spatial_metrics(bytes(codes))
    return (
        metrics["controllers"][0]["total_internal_edges"]["different"],
        metrics["controllers"][1]["total_internal_edges"]["different"],
        metrics["controller_seam"]["different"],
        metrics["boundary_pixels"]["count"],
    )


def _total_edges(vector: Sequence[int]) -> int:
    return vector[0] + vector[1] + vector[2]


def _neighbours(position: int) -> tuple[int, ...]:
    y_value, x_value = divmod(position, WIDTH)
    result: list[int] = []
    if x_value:
        result.append(position - 1)
    if x_value + 1 < WIDTH:
        result.append(position + 1)
    if y_value:
        result.append(position - WIDTH)
    if y_value + 1 < HEIGHT:
        result.append(position + WIDTH)
    return tuple(result)


def _local_edge_counts(
    codes: bytearray, edges: set[tuple[int, int]]
) -> tuple[int, int, int]:
    counts = [0, 0, 0]
    for first, second in edges:
        if codes[first] == codes[second]:
            continue
        first_x = first % WIDTH
        second_x = second % WIDTH
        if first_x == WIDTH // 2 - 1 and second_x == WIDTH // 2:
            counts[2] += 1
        elif first_x < WIDTH // 2 and second_x < WIDTH // 2:
            counts[0] += 1
        else:
            counts[1] += 1
    return tuple(counts)


def _is_boundary(codes: bytearray, position: int) -> bool:
    return any(codes[position] != codes[other] for other in _neighbours(position))


def _swap_delta(
    codes: bytearray, first: int, second: int
) -> tuple[int, int, int, int]:
    edges: set[tuple[int, int]] = set()
    affected = {first, second}
    for position in (first, second):
        for other in _neighbours(position):
            affected.add(other)
            edges.add((min(position, other), max(position, other)))
    before_edges = _local_edge_counts(codes, edges)
    before_boundary = sum(_is_boundary(codes, position) for position in affected)
    codes[first], codes[second] = codes[second], codes[first]
    after_edges = _local_edge_counts(codes, edges)
    after_boundary = sum(_is_boundary(codes, position) for position in affected)
    codes[first], codes[second] = codes[second], codes[first]
    return (
        after_edges[0] - before_edges[0],
        after_edges[1] - before_edges[1],
        after_edges[2] - before_edges[2],
        after_boundary - before_boundary,
    )


class _SplitMix64:
    def __init__(self, seed: int) -> None:
        self.state = seed & 0xFFFFFFFFFFFFFFFF

    def next_u64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        value = self.state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return value ^ (value >> 31)

    def below(self, upper: int) -> int:
        if upper < 1:
            raise V3FactorialError("solver PRNG received an empty range")
        return self.next_u64() % upper


def _allocation_groups(prior_codes: bytes) -> tuple[tuple[int, ...], ...]:
    if len(prior_codes) != WIDTH * HEIGHT:
        raise V3FactorialError("MAP prior length differs from the panel geometry")
    ranks = {code: index for index, code in enumerate(PHYSICAL_CODE_ORDER)}
    groups: list[list[int]] = [[] for _ in range(2 * len(PHYSICAL_CODE_ORDER))]
    for position, old_code in enumerate(prior_codes):
        if old_code not in ranks:
            raise V3FactorialError("MAP prior contains a non-physical code")
        side = 0 if position % WIDTH < WIDTH // 2 else 1
        groups[side * len(PHYSICAL_CODE_ORDER) + ranks[old_code]].append(position)
    return tuple(tuple(group) for group in groups)


def _objective(delta: Sequence[int]) -> int:
    return sum(
        weight * value * value
        for weight, value in zip(SOLVER_OBJECTIVE_WEIGHTS, delta)
    )


def _joint_solve_level(
    prior_codes: bytes,
    *,
    spatial: str,
    unbalanced_codes: bytes,
    balanced_codes: bytes,
) -> tuple[bytes, bytes, dict[str, Any]]:
    """Jointly make all preregistered nonredundant metrics exactly equal."""

    if spatial not in {"high", "low"}:
        raise V3FactorialError("joint solver spatial level must be high or low")
    variants = [bytearray(unbalanced_codes), bytearray(balanced_codes)]
    groups = _allocation_groups(prior_codes)
    initial_vectors = [_metric_vector(codes) for codes in variants]
    difference = [
        initial_vectors[0][index] - initial_vectors[1][index]
        for index in range(len(METRIC_ORDER))
    ]
    initial_difference = tuple(difference)
    score = _objective(difference)
    rng = _SplitMix64(SOLVER_SEED)
    trace = hashlib.sha256()
    accepted = 0
    proposals_used = 0
    for proposal in range(SOLVER_MAX_PROPOSALS):
        proposals_used = proposal + 1
        variant_index = rng.below(2)
        codes = variants[variant_index]
        group = groups[rng.below(len(groups))]
        first = group[rng.below(len(group))]
        second = group[rng.below(len(group))]
        if codes[first] == codes[second]:
            continue
        swap_delta = _swap_delta(codes, first, second)
        sign = 1 if variant_index == 0 else -1
        candidate_difference = [
            difference[index] + sign * swap_delta[index]
            for index in range(len(METRIC_ORDER))
        ]
        candidate_score = _objective(candidate_difference)
        accept = candidate_score < score
        if candidate_score == score:
            accept = rng.below(8) == 0
        if not accept:
            continue
        codes[first], codes[second] = codes[second], codes[first]
        difference = candidate_difference
        score = candidate_score
        accepted += 1
        trace.update(
            struct.pack(
                ">IBIIhhhh",
                proposal,
                variant_index,
                first,
                second,
                *swap_delta,
            )
        )
        if score == 0:
            break
    if score != 0 or difference != [0, 0, 0, 0]:
        raise V3FactorialError(
            f"{spatial} joint solver exhausted its proposal budget at delta={difference}"
        )
    final_codes = (bytes(variants[0]), bytes(variants[1]))
    final_vectors = tuple(_metric_vector(codes) for codes in final_codes)
    if final_vectors[0] != final_vectors[1]:
        raise V3FactorialError(f"{spatial} solver metric replay differs from its objective")
    return (
        final_codes[0],
        final_codes[1],
        {
            "spatial_level": spatial,
            "seed": SOLVER_SEED,
            "prng": SOLVER_PRNG,
            "maximum_proposals": SOLVER_MAX_PROPOSALS,
            "proposals_used": proposals_used,
            "accepted_swaps": accepted,
            "metric_order": list(METRIC_ORDER),
            "objective_weights": list(SOLVER_OBJECTIVE_WEIGHTS),
            "initial_unbalanced": list(initial_vectors[0]),
            "initial_balanced": list(initial_vectors[1]),
            "initial_difference_unbalanced_minus_balanced": list(initial_difference),
            "final_unbalanced": list(final_vectors[0]),
            "final_balanced": list(final_vectors[1]),
            "final_difference_unbalanced_minus_balanced": [0, 0, 0, 0],
            "final_objective": 0,
            "accepted_swap_trace_sha256": trace.hexdigest(),
            "accepted_swap_trace_encoding": (
                "concatenated accepted records: proposal u32be, variant u8 "
                "(0=unbalanced,1=balanced), first u32be, second u32be, "
                "four signed metric deltas i16be"
            ),
        },
    )


def _strict_preview(codes: bytes) -> bytes:
    return low_spatial._strict_preview(codes)


def _rgb(codes: bytes) -> bytes:
    colours = {entry.code: bytes(entry.preview_rgb) for entry in reference_palette().entries}
    result = bytearray(len(codes) * 3)
    offset = 0
    for code in codes:
        try:
            colour = colours[code]
        except KeyError as error:
            raise V3FactorialError(f"contact sheet received non-physical code {code}") from error
        result[offset : offset + 3] = colour
        offset += 3
    return bytes(result)


def _contact_sheet(variants: Mapping[str, VariantArtifacts]) -> bytes:
    white = b"\xff\xff\xff"
    canvas = bytearray(white * (CONTACT_WIDTH * CONTACT_HEIGHT))
    for name in VARIANT_NAMES:
        x0, y0 = CONTACT_LAYOUT[name]
        source = _rgb(variants[name].codes)
        for row in range(HEIGHT):
            source_start = row * WIDTH * 3
            target_start = ((y0 + row) * CONTACT_WIDTH + x0) * 3
            canvas[target_start : target_start + WIDTH * 3] = source[
                source_start : source_start + WIDTH * 3
            ]
    return encode_rgb_png(CONTACT_WIDTH, CONTACT_HEIGHT, canvas)


def _controller_records(frame: bytes) -> list[dict[str, Any]]:
    records = []
    for number, mapping in enumerate(v2.CONTROLLER_MAPPINGS, start=1):
        stream = controller_stream(frame, mapping)
        if len(stream) != CONTROLLER_FRAME_BYTES:
            raise V3FactorialError(f"CS{number} stream length changed")
        records.append(
            {
                "controller": f"CS{number}",
                "mapping": v2._mapping_record(mapping),
                "dtm_bytes": len(stream),
                "dtm_sha256": _sha256(stream),
                "dtm_fnv1a": f"0x{fnv1a(stream):08X}",
            }
        )
    return records


def _variant_record(
    name: str, prior_codes: bytes, variant: VariantArtifacts
) -> dict[str, Any]:
    spatial, load = name.split("-", 1)
    matrices = (
        (v2.BALANCED_LEFT_MATRIX, v2.BALANCED_RIGHT_MATRIX)
        if load == "balanced"
        else (v2.UNBALANCED_LEFT_MATRIX, v2.UNBALANCED_RIGHT_MATRIX)
    )
    half_counts = (
        (v2.BALANCED_LEFT_COUNTS, v2.BALANCED_RIGHT_COUNTS)
        if load == "balanced"
        else (v2.UNBALANCED_LEFT_COUNTS, v2.UNBALANCED_RIGHT_COUNTS)
    )
    codes = variant.codes
    global_matrix = low_spatial._transition_matrix(prior_codes, codes)
    left_matrix = low_spatial._transition_matrix(
        prior_codes, codes, x0=0, x1=WIDTH // 2
    )
    right_matrix = low_spatial._transition_matrix(
        prior_codes, codes, x0=WIDTH // 2, x1=WIDTH
    )
    left_codes, right_codes = _half_bytes(codes, 0), _half_bytes(codes, 1)
    counts = (_counts(codes), _counts(left_codes), _counts(right_codes))
    changed_left = sum(
        prior_codes[y * WIDTH + x] != codes[y * WIDTH + x]
        for y in range(HEIGHT)
        for x in range(WIDTH // 2)
    )
    changed_right = sum(
        prior_codes[y * WIDTH + x] != codes[y * WIDTH + x]
        for y in range(HEIGHT)
        for x in range(WIDTH // 2, WIDTH)
    )
    if (
        global_matrix != GLOBAL_TRANSITION_MATRIX
        or left_matrix != matrices[0]
        or right_matrix != matrices[1]
        or counts != (GLOBAL_COUNTS, half_counts[0], half_counts[1])
        or changed_left + changed_right != EXPECTED_CHANGED_PIXELS
    ):
        raise V3FactorialError(f"{name} lost a transition/count invariant")
    metrics = low_spatial.spatial_metrics(codes)
    vector = _metric_vector(codes)
    return {
        "factors": {
            "controller_internal_spatial_frequency": spatial,
            "half_load": load,
        },
        "frame": {
            "file": f"{name}.frame.bin",
            "bytes": len(variant.frame),
            "encoding": "canonical-row-major-two-4bit-codes-per-byte-even-x-high-nibble",
            "sha256": _sha256(variant.frame),
            "fnv1a": f"0x{fnv1a(variant.frame):08X}",
            "codes_sha256": _sha256(codes),
        },
        "controllers": _controller_records(variant.frame),
        "counts": {
            "code_order": list(PHYSICAL_CODE_ORDER),
            "global": list(counts[0]),
            "left": list(counts[1]),
            "right": list(counts[2]),
            "left_minus_right": [
                left - right for left, right in zip(counts[1], counts[2])
            ],
            "half_imbalance_l1": sum(
                abs(left - right) for left, right in zip(counts[1], counts[2])
            ),
        },
        "transitions_from_map_prior": {
            "row_old_codes": list(PHYSICAL_CODE_ORDER),
            "column_new_codes": list(PHYSICAL_CODE_ORDER),
            "global": _matrix_record(global_matrix),
            "left": _matrix_record(left_matrix),
            "right": _matrix_record(right_matrix),
            "global_canonical_sha256": _sha256(_canonical_json(_matrix_record(global_matrix))),
            "left_canonical_sha256": _sha256(_canonical_json(_matrix_record(left_matrix))),
            "right_canonical_sha256": _sha256(_canonical_json(_matrix_record(right_matrix))),
            "changed_pixels": changed_left + changed_right,
            "unchanged_pixels": WIDTH * HEIGHT - changed_left - changed_right,
            "changed_left": changed_left,
            "changed_right": changed_right,
        },
        "preregistered_spatial_metrics": {
            "total_four_neighbour_edges": _total_edges(vector),
            "internal_left_edges": vector[0],
            "internal_right_edges": vector[1],
            "boundary_pixels": vector[3],
            "controller_seam": vector[2],
        },
        "spatial_metrics": metrics,
        "strict_preview": {
            "file": f"{name}.strict-final.png",
            "bytes": len(variant.strict_png),
            "sha256": _sha256(variant.strict_png),
            "width": WIDTH,
            "height": HEIGHT,
            "semantics": "strict reference-palette rendering of the exact V3 six-code cell",
        },
    }


def _non_preregistered_residuals(
    records: Mapping[str, Mapping[str, Any]], spatial: str
) -> dict[str, Any]:
    """Expose, but do not silently include, every richer oracle residual."""

    unbalanced = records[f"{spatial}-unbalanced"]["spatial_metrics"]
    balanced = records[f"{spatial}-balanced"]["spatial_metrics"]
    controller_residuals = {}
    for side, controller in enumerate(("CS1", "CS2")):
        first = unbalanced["controllers"][side]
        second = balanced["controllers"][side]
        controller_residuals[controller] = {
            "horizontal_internal_edges": first["horizontal_internal"]["different"]
            - second["horizontal_internal"]["different"],
            "vertical_edges": first["vertical"]["different"]
            - second["vertical"]["different"],
            "internal_boundary_pixels": first["internal_boundary_pixels"]["count"]
            - second["internal_boundary_pixels"]["count"],
        }
    first_matrix = unbalanced["controller_seam"]["pair_matrix"]
    second_matrix = balanced["controller_seam"]["pair_matrix"]
    matrix_l1 = sum(
        abs(first_matrix[row][column] - second_matrix[row][column])
        for row in range(6)
        for column in range(6)
    )
    residual_values = [
        value
        for controller in controller_residuals.values()
        for value in controller.values()
    ]
    residual_values.extend(
        (
            unbalanced["horizontal_internal"]["different"]
            - balanced["horizontal_internal"]["different"],
            unbalanced["horizontal_full_including_seam"]["different"]
            - balanced["horizontal_full_including_seam"]["different"],
            unbalanced["vertical"]["different"]
            - balanced["vertical"]["different"],
            unbalanced["seam_additional_boundary_endpoints"]
            - balanced["seam_additional_boundary_endpoints"],
        )
    )
    return {
        "sign": "unbalanced-minus-balanced",
        "controllers": controller_residuals,
        "full_horizontal_internal_edges": unbalanced["horizontal_internal"]["different"]
        - balanced["horizontal_internal"]["different"],
        "full_horizontal_including_seam_edges": unbalanced[
            "horizontal_full_including_seam"
        ]["different"]
        - balanced["horizontal_full_including_seam"]["different"],
        "full_vertical_edges": unbalanced["vertical"]["different"]
        - balanced["vertical"]["different"],
        "seam_additional_boundary_endpoints": unbalanced[
            "seam_additional_boundary_endpoints"
        ]
        - balanced["seam_additional_boundary_endpoints"],
        "seam_pair_matrix_exact": first_matrix == second_matrix,
        "seam_pair_matrix_cellwise_l1": matrix_l1,
        "all_non_preregistered_metrics_exact": not any(residual_values)
        and first_matrix == second_matrix,
    }


def _seal(document: dict[str, Any], *, field: str, scope: str) -> dict[str, Any]:
    sealed = json.loads(_canonical_json(document).decode("utf-8"))
    sealed[field] = {
        "canonical_sha256": _sha256(_canonical_json(sealed)),
        "canonical_sha256_scope": scope,
    }
    return sealed


def _check_frozen_hash(actual: str, expected: Optional[str], *, label: str) -> None:
    if expected is not None and actual != expected:
        raise V3FactorialError(f"frozen {label} identity changed")


def build_v3_artifacts() -> V3Artifacts:
    """Deep-audit V2, solve both A levels jointly, and build all V3 bytes."""

    v2_artifacts = v2.build_factorial_artifacts()
    if (
        _sha256(v2_artifacts.manifest_bytes) != V2_MANIFEST_FILE_SHA256
        or v2_artifacts.manifest["manifest_integrity"]["canonical_sha256"]
        != V2_MANIFEST_CANONICAL_SHA256
        or v2_artifacts.manifest["classification"]["strict_metric_orthogonality_proven"]
        is not False
    ):
        raise V3FactorialError("V2 seed audit identity or non-strict classification changed")
    prior_codes, _ = low_spatial.generate_diagnostic_codes()
    if _sha256(prior_codes) != v2.MAP_CODES_SHA256:
        raise V3FactorialError("MAP prior identity changed")

    solved_codes: dict[str, bytes] = {}
    solver_records: dict[str, Any] = {}
    for spatial in ("high", "low"):
        unbalanced, balanced, solver_record = _joint_solve_level(
            prior_codes,
            spatial=spatial,
            unbalanced_codes=v2_artifacts.variants[f"{spatial}-unbalanced"].codes,
            balanced_codes=v2_artifacts.variants[f"{spatial}-balanced"].codes,
        )
        solved_codes[f"{spatial}-unbalanced"] = unbalanced
        solved_codes[f"{spatial}-balanced"] = balanced
        solver_records[spatial] = solver_record

    variants: dict[str, VariantArtifacts] = {}
    records: dict[str, Any] = {}
    for name in VARIANT_NAMES:
        codes = solved_codes[name]
        frame = pack_pixels(codes)
        validate_frame(frame)
        if len(frame) != FRAME_BYTES:
            raise V3FactorialError(f"{name} frame length changed")
        variant = VariantArtifacts(codes, frame, _strict_preview(codes))
        variants[name] = variant
        records[name] = _variant_record(name, prior_codes, variant)

    for spatial in ("high", "low"):
        first = records[f"{spatial}-unbalanced"]["preregistered_spatial_metrics"]
        second = records[f"{spatial}-balanced"]["preregistered_spatial_metrics"]
        if first != second:
            raise V3FactorialError(f"{spatial} preregistered metrics are not exactly equal")
    for load in ("unbalanced", "balanced"):
        high = records[f"high-{load}"]
        low = records[f"low-{load}"]
        if high["counts"] != low["counts"] or high["transitions_from_map_prior"] != low[
            "transitions_from_map_prior"
        ]:
            raise V3FactorialError(f"{load} B manipulation differs across A levels")

    high_total = records["high-unbalanced"]["preregistered_spatial_metrics"][
        "total_four_neighbour_edges"
    ]
    low_total = records["low-unbalanced"]["preregistered_spatial_metrics"][
        "total_four_neighbour_edges"
    ]
    if high_total <= 10 * low_total:
        raise V3FactorialError("V3 high/low spatial manipulation separation is insufficient")

    proof_unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": PROOF_KIND,
        "algorithm": {
            "id": ALGORITHM_ID,
            "deterministic": True,
            "joint_across_B_within_each_A": True,
            "exchange_group": ["controller_half", "map_prior_old_code"],
            "exchange_invariant": (
                "swapping final codes only inside one group preserves every per-half "
                "old-to-new transition cell, histogram, and changed-pixel count"
            ),
            "randomness": False,
        },
        "source_v2": {
            "kind": v2.MANIFEST_KIND,
            "manifest_file_sha256": V2_MANIFEST_FILE_SHA256,
            "manifest_canonical_sha256": V2_MANIFEST_CANONICAL_SHA256,
            "strict_metric_orthogonality_proven": False,
            "eligible_as_seed_only": True,
            "eligible_for_v3_strict_gate": False,
        },
        "preregistration": {
            "metrics": list(PREREGISTERED_METRICS),
            "comparison": "unbalanced minus balanced within the same A level",
            "required_absolute_tolerance_by_metric": {
                metric: 0 for metric in PREREGISTERED_METRICS
            },
            "all_metrics_exact_not_tolerance": True,
        },
        "exact_shared_invariants": {
            "global_counts": list(GLOBAL_COUNTS),
            "global_transition_matrix": _matrix_record(GLOBAL_TRANSITION_MATRIX),
            "global_transition_canonical_sha256": _sha256(
                _canonical_json(_matrix_record(GLOBAL_TRANSITION_MATRIX))
            ),
            "changed_pixels_from_map_prior": EXPECTED_CHANGED_PIXELS,
        },
        "factor_B_exact_effect": {
            "balanced_half_imbalance_l1": 4,
            "unbalanced_half_imbalance_l1": 186_896,
            "effect_difference_l1": 186_892,
            "same_balanced_half_transition_matrices_at_high_and_low_A": True,
            "same_unbalanced_half_transition_matrices_at_high_and_low_A": True,
        },
        "solver": {
            "prng": SOLVER_PRNG,
            "seed_per_A_level": SOLVER_SEED,
            "maximum_proposals_per_A_level": SOLVER_MAX_PROPOSALS,
            "objective": "weighted sum of squared unbalanced-minus-balanced metric deltas",
            "levels": solver_records,
        },
        "output_proof": {
            name: {
                "codes_sha256": records[name]["frame"]["codes_sha256"],
                "frame_sha256": records[name]["frame"]["sha256"],
                "global_transition_canonical_sha256": records[name][
                    "transitions_from_map_prior"
                ]["global_canonical_sha256"],
                "left_transition_canonical_sha256": records[name][
                    "transitions_from_map_prior"
                ]["left_canonical_sha256"],
                "right_transition_canonical_sha256": records[name][
                    "transitions_from_map_prior"
                ]["right_canonical_sha256"],
                "changed_pixels": records[name]["transitions_from_map_prior"][
                    "changed_pixels"
                ],
                "preregistered_spatial_metrics": records[name][
                    "preregistered_spatial_metrics"
                ],
            }
            for name in VARIANT_NAMES
        },
        "non_preregistered_residual_audit": {
            spatial: _non_preregistered_residuals(records, spatial)
            for spatial in ("high", "low")
        },
        "decision": {
            "strict_selected_metric_orthogonality_proven": True,
            "all_reported_spatial_metrics_orthogonality_proven": False,
            "selected_metric_strict_gate_pass": True,
            "hardware_qualified": False,
            "hardware_tested": False,
            "upload_authorized": False,
            "claim_created": False,
            "authorization_created": False,
            "network_io_performed": False,
            "device_io_performed": False,
        },
    }
    proof = _seal(proof_unsigned, field="proof_integrity", scope=PROOF_HASH_SCOPE)
    proof_bytes = _canonical_json(proof)
    _check_frozen_hash(
        proof["proof_integrity"]["canonical_sha256"],
        EXPECTED_PROOF_CANONICAL_SHA256,
        label="V3 proof canonical",
    )
    _check_frozen_hash(
        _sha256(proof_bytes), EXPECTED_PROOF_FILE_SHA256, label="V3 proof file"
    )

    contact_png = _contact_sheet(variants)
    manifest_unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "classification": {
            "experimental": True,
            "root_cause_audit_only": True,
            "simulation_only": True,
            "formal": False,
            "hardware_qualified": False,
            "hardware_tested": False,
            "upload_authorized": False,
            "causal_attribution_authorized": False,
            "strict_metric_orthogonality_proven": False,
            "strict_selected_metric_orthogonality_proven": True,
            "all_reported_spatial_metrics_orthogonality_proven": False,
        },
        "prior": {
            "fixture": low_spatial.MAP_FIXTURE,
            "frame_sha256": v2.MAP_FRAME_SHA256,
            "codes_sha256": v2.MAP_CODES_SHA256,
            "one_fresh_map_required_before_each_cell": True,
        },
        "proof_manifest": {
            "file": "proof-manifest.json",
            "bytes": len(proof_bytes),
            "sha256": _sha256(proof_bytes),
            "canonical_sha256": proof["proof_integrity"]["canonical_sha256"],
        },
        "design": {
            "factor_A": "controller_internal_spatial_frequency: high/low",
            "factor_B": "left_right_pigment_transition_load: unbalanced/balanced",
            "cell_order": list(VARIANT_NAMES),
            "preregistered_metrics": list(PREREGISTERED_METRICS),
            "tolerance_by_metric": {metric: 0 for metric in PREREGISTERED_METRICS},
            "strict_selected_metric_orthogonality_proven": True,
            "all_reported_spatial_metrics_orthogonality_proven": False,
            "minimum_high_to_low_total_edge_ratio": high_total / low_total,
        },
        "variants": records,
        "contact_sheet": {
            "file": "contact-sheet.png",
            "bytes": len(contact_png),
            "sha256": _sha256(contact_png),
            "width": CONTACT_WIDTH,
            "height": CONTACT_HEIGHT,
            "gutter_pixels": CONTACT_GUTTER,
            "layout_xy": CONTACT_LAYOUT,
            "semantics": "four strict reference-palette previews; no model blur or display simulation",
        },
        "required_file_set": sorted(REQUIRED_FILES),
        "limitations": [
            "Exact orthogonality is proven only for the preregistered raster metrics, not electrical energy or waveform stress.",
            "Horizontal/vertical decomposition, per-half boundary pixels, and the seam code-pair matrix retain disclosed residuals and are not claimed exact.",
            "The cells preserve MAP transitions but do not preserve source-image semantics or establish subjective quality.",
            "V3 is offline evidence only; every future cell still needs an independent MAP-to-cell action and runtime safety review.",
            "No file in this bundle is an upload, refresh, claim, or authorization artifact.",
        ],
        "transport": {
            "mode": "offline",
            "endpoint": None,
            "method": None,
            "device_io_performed": False,
            "network_io_performed": False,
            "refresh_runner_implemented": False,
            "claim_created": False,
            "authorization_created": False,
            "upload_authorized": False,
        },
    }
    manifest = _seal(
        manifest_unsigned, field="manifest_integrity", scope=MANIFEST_HASH_SCOPE
    )
    manifest_bytes = _canonical_json(manifest)
    _check_frozen_hash(
        manifest["manifest_integrity"]["canonical_sha256"],
        EXPECTED_MANIFEST_CANONICAL_SHA256,
        label="V3 manifest canonical",
    )
    _check_frozen_hash(
        _sha256(manifest_bytes),
        EXPECTED_MANIFEST_FILE_SHA256,
        label="V3 manifest file",
    )
    validate_strict_manifests(manifest, proof)
    return V3Artifacts(
        variants, contact_png, proof, proof_bytes, manifest, manifest_bytes
    )


def _validate_integrity(
    document: Mapping[str, Any], *, field: str, scope: str, label: str
) -> None:
    unsigned = dict(document)
    integrity = unsigned.pop(field, None)
    expected = {
        "canonical_sha256": _sha256(_canonical_json(unsigned)),
        "canonical_sha256_scope": scope,
    }
    if integrity != expected:
        raise V3FactorialError(f"{label} canonical integrity is invalid")


def validate_strict_manifests(
    manifest: Mapping[str, Any], proof: Mapping[str, Any]
) -> None:
    """Apply the V3 strict gate; V2 and any tolerance claim are rejected."""

    if not isinstance(manifest, Mapping) or manifest.get("kind") != MANIFEST_KIND:
        raise V3FactorialError("strict V3 gate rejects a non-V3 manifest (including V2)")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise V3FactorialError("strict V3 manifest schema version is invalid")
    if not isinstance(proof, Mapping) or proof.get("kind") != PROOF_KIND:
        raise V3FactorialError("strict V3 gate requires the V3 joint proof manifest")
    if proof.get("schema_version") != SCHEMA_VERSION:
        raise V3FactorialError("strict V3 proof schema version is invalid")
    _validate_integrity(
        proof, field="proof_integrity", scope=PROOF_HASH_SCOPE, label="V3 proof"
    )
    _validate_integrity(
        manifest,
        field="manifest_integrity",
        scope=MANIFEST_HASH_SCOPE,
        label="V3 manifest",
    )
    classification = manifest.get("classification", {})
    if (
        classification.get("strict_metric_orthogonality_proven") is not False
        or classification.get("strict_selected_metric_orthogonality_proven") is not True
        or classification.get("all_reported_spatial_metrics_orthogonality_proven")
        is not False
        or classification.get("upload_authorized") is not False
        or classification.get("hardware_qualified") is not False
    ):
        raise V3FactorialError("V3 classification is not strict offline-only evidence")
    decision = proof.get("decision", {})
    if (
        decision.get("strict_selected_metric_orthogonality_proven") is not True
        or decision.get("all_reported_spatial_metrics_orthogonality_proven")
        is not False
        or decision.get("selected_metric_strict_gate_pass") is not True
        or any(
            decision.get(field) is not False
            for field in (
                "hardware_qualified",
                "hardware_tested",
                "upload_authorized",
                "claim_created",
                "authorization_created",
                "network_io_performed",
                "device_io_performed",
            )
        )
    ):
        raise V3FactorialError("V3 proof decision is not strict zero-I/O evidence")
    preregistration = proof.get("preregistration", {})
    if (
        preregistration.get("metrics") != list(PREREGISTERED_METRICS)
        or preregistration.get("all_metrics_exact_not_tolerance") is not True
        or preregistration.get("required_absolute_tolerance_by_metric")
        != {metric: 0 for metric in PREREGISTERED_METRICS}
        or manifest.get("design", {}).get("tolerance_by_metric")
        != {metric: 0 for metric in PREREGISTERED_METRICS}
    ):
        raise V3FactorialError("V3 preregistered metrics are missing or use tolerance")
    if proof.get("source_v2") != {
        "kind": v2.MANIFEST_KIND,
        "manifest_file_sha256": V2_MANIFEST_FILE_SHA256,
        "manifest_canonical_sha256": V2_MANIFEST_CANONICAL_SHA256,
        "strict_metric_orthogonality_proven": False,
        "eligible_as_seed_only": True,
        "eligible_for_v3_strict_gate": False,
    }:
        raise V3FactorialError("V3 proof does not bind the frozen rejected V2 seed")
    if proof.get("exact_shared_invariants") != {
        "global_counts": list(GLOBAL_COUNTS),
        "global_transition_matrix": _matrix_record(GLOBAL_TRANSITION_MATRIX),
        "global_transition_canonical_sha256": _sha256(
            _canonical_json(_matrix_record(GLOBAL_TRANSITION_MATRIX))
        ),
        "changed_pixels_from_map_prior": EXPECTED_CHANGED_PIXELS,
    }:
        raise V3FactorialError("V3 proof shared invariant declaration is invalid")
    if proof.get("factor_B_exact_effect") != {
        "balanced_half_imbalance_l1": 4,
        "unbalanced_half_imbalance_l1": 186_896,
        "effect_difference_l1": 186_892,
        "same_balanced_half_transition_matrices_at_high_and_low_A": True,
        "same_unbalanced_half_transition_matrices_at_high_and_low_A": True,
    }:
        raise V3FactorialError("V3 exact B-effect declaration is invalid")
    solver = proof.get("solver", {})
    levels = solver.get("levels", {}) if isinstance(solver, Mapping) else {}
    if (
        solver.get("prng") != SOLVER_PRNG
        or solver.get("seed_per_A_level") != SOLVER_SEED
        or solver.get("maximum_proposals_per_A_level") != SOLVER_MAX_PROPOSALS
        or not isinstance(levels, Mapping)
        or set(levels) != {"high", "low"}
    ):
        raise V3FactorialError("V3 solver identity or level set is invalid")
    for spatial in ("high", "low"):
        level = levels[spatial]
        trace_sha = level.get("accepted_swap_trace_sha256")
        if (
            level.get("spatial_level") != spatial
            or level.get("seed") != SOLVER_SEED
            or level.get("prng") != SOLVER_PRNG
            or level.get("maximum_proposals") != SOLVER_MAX_PROPOSALS
            or level.get("metric_order") != list(METRIC_ORDER)
            or level.get("objective_weights") != list(SOLVER_OBJECTIVE_WEIGHTS)
            or level.get("final_difference_unbalanced_minus_balanced") != [0, 0, 0, 0]
            or level.get("final_unbalanced") != level.get("final_balanced")
            or level.get("final_objective") != 0
            or type(level.get("proposals_used")) is not int
            or not 1 <= level["proposals_used"] <= SOLVER_MAX_PROPOSALS
            or type(level.get("accepted_swaps")) is not int
            or not 1 <= level["accepted_swaps"] <= level["proposals_used"]
            or not isinstance(trace_sha, str)
            or len(trace_sha) != 64
            or any(character not in "0123456789abcdef" for character in trace_sha)
        ):
            raise V3FactorialError(f"V3 {spatial} solver certificate is invalid")
    residuals = proof.get("non_preregistered_residual_audit", {})
    if (
        not isinstance(residuals, Mapping)
        or set(residuals) != {"high", "low"}
        or any(
            residuals[spatial].get("all_non_preregistered_metrics_exact") is not False
            for spatial in ("high", "low")
        )
    ):
        raise V3FactorialError("V3 proof hides or misclassifies richer metric residuals")
    proof_bytes = _canonical_json(proof)
    if manifest.get("proof_manifest") != {
        "file": "proof-manifest.json",
        "bytes": len(proof_bytes),
        "sha256": _sha256(proof_bytes),
        "canonical_sha256": proof["proof_integrity"]["canonical_sha256"],
    }:
        raise V3FactorialError("V3 manifest/proof SHA binding is invalid")
    records = manifest.get("variants")
    outputs = proof.get("output_proof")
    if not isinstance(records, Mapping) or not isinstance(outputs, Mapping):
        raise V3FactorialError("V3 variants or output proof is missing")
    if set(records) != set(VARIANT_NAMES) or set(outputs) != set(VARIANT_NAMES):
        raise V3FactorialError("V3 variant set is not the frozen 2x2")
    for name in VARIANT_NAMES:
        record = records[name]
        transition = record["transitions_from_map_prior"]
        if (
            record["counts"]["global"] != list(GLOBAL_COUNTS)
            or transition["global"] != _matrix_record(GLOBAL_TRANSITION_MATRIX)
            or transition["changed_pixels"] != EXPECTED_CHANGED_PIXELS
        ):
            raise V3FactorialError(f"{name} global invariant proof is invalid")
        expected_output = {
            "codes_sha256": record["frame"]["codes_sha256"],
            "frame_sha256": record["frame"]["sha256"],
            "global_transition_canonical_sha256": transition[
                "global_canonical_sha256"
            ],
            "left_transition_canonical_sha256": transition[
                "left_canonical_sha256"
            ],
            "right_transition_canonical_sha256": transition[
                "right_canonical_sha256"
            ],
            "changed_pixels": transition["changed_pixels"],
            "preregistered_spatial_metrics": record[
                "preregistered_spatial_metrics"
            ],
        }
        if outputs[name] != expected_output:
            raise V3FactorialError(f"{name} proof/output SHA binding is invalid")
    for spatial in ("high", "low"):
        unbalanced = records[f"{spatial}-unbalanced"]
        balanced = records[f"{spatial}-balanced"]
        if (
            unbalanced["preregistered_spatial_metrics"]
            != balanced["preregistered_spatial_metrics"]
        ):
            raise V3FactorialError(f"{spatial} B levels fail exact spatial equality")
    for load, expected_l1 in (("unbalanced", 186_896), ("balanced", 4)):
        high, low = records[f"high-{load}"], records[f"low-{load}"]
        if (
            high["counts"] != low["counts"]
            or high["transitions_from_map_prior"]
            != low["transitions_from_map_prior"]
            or high["counts"]["half_imbalance_l1"] != expected_l1
        ):
            raise V3FactorialError(f"{load} B effect is not exact across A")
    if manifest.get("required_file_set") != sorted(REQUIRED_FILES):
        raise V3FactorialError("V3 required file set is invalid")
    transport = manifest.get("transport", {})
    if any(
        transport.get(field) is not False
        for field in (
            "device_io_performed",
            "network_io_performed",
            "refresh_runner_implemented",
            "claim_created",
            "authorization_created",
            "upload_authorized",
        )
    ):
        raise V3FactorialError("V3 transport must remain zero-I/O and unauthorized")


def _p0_frame_record(frame: bytes) -> dict[str, Any]:
    validate_frame(frame)
    controllers = []
    for number, mapping in enumerate(v2.CONTROLLER_MAPPINGS, start=1):
        stream = controller_stream(frame, mapping)
        controllers.append(
            {
                "controller": f"CS{number}",
                "mapping": v2._mapping_record(mapping),
                "dtm_bytes": len(stream),
                "dtm_sha256": _sha256(stream),
                "dtm_fnv1a": f"0x{fnv1a(stream):08X}",
            }
        )
    return {
        "width": WIDTH,
        "height": HEIGHT,
        "bits_per_pixel": 4,
        "bytes": len(frame),
        "sha256": _sha256(frame),
        "fnv1a": f"0x{fnv1a(frame):08X}",
        "controllers": controllers,
    }


def compile_p0_campaign(
    *,
    panel: Mapping[str, Any],
    firmware: Mapping[str, Any],
    minimum_interval_seconds: int | float,
    planned_cooldown_seconds: int | float,
    campaign_id: str = "n4-v3-selected-metric-2x2-v1",
) -> dict[str, Any]:
    """Compile four independent MAP-to-cell sessions with no execution path."""

    artifacts = build_v3_artifacts()
    prior_codes, _ = low_spatial.generate_diagnostic_codes()
    map_frame = pack_pixels(prior_codes)
    map_record = _p0_frame_record(map_frame)
    actions = []
    sessions = []
    for cell_name in CAMPAIGN_CELL_ORDER:
        session_id = f"n4-v3-{cell_name}"
        map_action = build_fixed_action_declaration(
            campaign_id=campaign_id,
            session_id=session_id,
            cell_id=cell_name,
            action_id=f"{cell_name}-map-primer",
            phase="map-primer",
            frame=map_record,
        )
        target_action = build_fixed_action_declaration(
            campaign_id=campaign_id,
            session_id=session_id,
            cell_id=cell_name,
            action_id=f"{cell_name}-target",
            phase="target",
            frame=_p0_frame_record(artifacts.variants[cell_name].frame),
            prior_action_identity_sha256=map_action["action_identity_sha256"],
            prior_scope="same_cell",
            minimum_interval_since_prior_seconds=minimum_interval_seconds,
        )
        actions.extend((map_action, target_action))
        sessions.append(
            build_session_contract(
                session_id=session_id,
                cell_id=cell_name,
                power_mode="controller_fresh_boot",
                planned_cooldown_seconds=planned_cooldown_seconds,
                final_power_off_required=True,
                action_identity_sha256s=(
                    map_action["action_identity_sha256"],
                    target_action["action_identity_sha256"],
                ),
            )
        )
    return seal_campaign_contract(
        {
            "schema_version": 1,
            "kind": CAMPAIGN_KIND,
            "campaign_id": campaign_id,
            "panel": dict(panel),
            "firmware": dict(firmware),
            "actions": actions,
            "sessions": sessions,
            "classification": {
                "offline_compiled": True,
                "hardware_execution_authorized": False,
                "automatic_execution": False,
                "automatic_retry": False,
                "automatic_recovery": False,
                "network_io_performed": False,
                "device_io_performed": False,
            },
        }
    )


def describe_p0_campaign_offline(
    campaign: Mapping[str, Any],
    *,
    limit_profile: Mapping[str, Any],
    evaluated_at: str,
) -> dict[str, Any]:
    """Describe all eight actions; targets remain blocked until their MAP PASS."""

    descriptions = [
        describe_action_offline(
            campaign,
            action_identity_sha256=action["action_identity_sha256"],
            limit_profile=limit_profile,
            evaluated_at=evaluated_at,
        )
        for action in campaign["actions"]
    ]
    return {
        "mode": "describe-only",
        "campaign_canonical_sha256": campaign["integrity"]["canonical_sha256"],
        "actions": descriptions,
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "claim_created": False,
        "authorization_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
    }


def _safe_directory(path: Path, *, label: str, must_exist: bool) -> Path:
    try:
        return clustered._safe_directory(path, label=label, must_exist=must_exist)
    except Exception as error:
        raise V3FactorialError(str(error)) from error


def validate_v3_directory(directory: Path) -> Mapping[str, Any]:
    """Deep-regenerate and compare every byte in a V3 bundle."""

    resolved = _safe_directory(directory, label="V3 bundle directory", must_exist=True)
    entries = tuple(resolved.iterdir())
    if any(entry.is_symlink() for entry in entries):
        raise V3FactorialError("V3 bundle must not contain symlinks")
    actual_files = {entry.name for entry in entries if entry.is_file()}
    if actual_files != REQUIRED_FILES or any(not entry.is_file() for entry in entries):
        raise V3FactorialError(
            f"V3 bundle file set must be exactly {sorted(REQUIRED_FILES)}"
        )
    manifest_bytes = (resolved / "manifest.json").read_bytes()
    proof_bytes = (resolved / "proof-manifest.json").read_bytes()
    try:
        manifest = clustered._load_json_strict(manifest_bytes)
        proof = clustered._load_json_strict(proof_bytes)
    except Exception as error:
        raise V3FactorialError(str(error)) from error
    if (
        not isinstance(manifest, dict)
        or not isinstance(proof, dict)
        or manifest_bytes != _canonical_json(manifest)
        or proof_bytes != _canonical_json(proof)
    ):
        raise V3FactorialError("V3 manifests must be canonical JSON")
    validate_strict_manifests(manifest, proof)
    expected = build_v3_artifacts()
    if manifest != expected.manifest or proof != expected.proof:
        raise V3FactorialError("V3 manifests differ from deterministic deep regeneration")
    for filename, payload in expected.files().items():
        if (resolved / filename).read_bytes() != payload:
            raise V3FactorialError(f"V3 file {filename} differs from regeneration")
    return manifest


def write_v3_directory(output_dir: Path) -> Mapping[str, Any]:
    """Atomically create one new V3 bundle and refuse overwrites."""

    destination = _safe_directory(output_dir, label="V3 output directory", must_exist=False)
    artifacts = build_v3_artifacts()
    temporary = destination.parent / f".{destination.name}.tmp-{uuid.uuid4().hex}"
    try:
        clustered._reject_symlink_ancestors(
            temporary.parent, label="V3 temporary output directory"
        )
        temporary.mkdir(mode=0o700)
        for filename, payload in artifacts.files().items():
            with (temporary / filename).open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        os.rename(temporary, destination)
    except Exception as error:
        if temporary.exists() and temporary.is_dir() and not temporary.is_symlink():
            for filename in REQUIRED_FILES:
                candidate = temporary / filename
                if candidate.exists() and candidate.is_file() and not candidate.is_symlink():
                    try:
                        candidate.unlink()
                    except OSError:
                        pass
            try:
                temporary.rmdir()
            except OSError:
                pass
        if isinstance(error, V3FactorialError):
            raise
        raise V3FactorialError(f"could not create V3 bundle: {error}") from error
    return validate_v3_directory(destination)


validate_candidate_directory = validate_v3_directory


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output-dir", type=Path, help="new local offline V3 bundle")
    mode.add_argument("--validate-dir", type=Path, help="existing local offline V3 bundle")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.output_dir is not None:
            manifest = write_v3_directory(args.output_dir)
            mode, directory = "generated", args.output_dir
        else:
            manifest = validate_v3_directory(args.validate_dir)
            mode, directory = "validated", args.validate_dir
    except (V3FactorialError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(
        _canonical_json(
            {
                "ok": True,
                "mode": mode,
                "directory": os.fspath(directory),
                "kind": manifest["kind"],
                "manifest_canonical_sha256": manifest["manifest_integrity"][
                    "canonical_sha256"
                ],
                "strict_metric_orthogonality_proven": False,
                "strict_selected_metric_orthogonality_proven": True,
                "device_io_performed": False,
                "network_io_performed": False,
                "claim_created": False,
                "authorization_created": False,
                "upload_authorized": False,
            }
        ).decode("utf-8")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
