#!/usr/bin/env python3
"""Build and deeply validate the offline G1/S1 low-spatial diagnostic bundle.

The diagnostic starts from the canonical ``map-orient-v1`` state.  It keeps
the failed job2 candidate's full-panel six-colour histogram and global 6x6
old-to-new transition-count matrix exactly, while balancing final colour
counts between controllers and arranging each old-colour mask into contiguous
row-major blocks.  This is a root-cause diagnostic, not an algorithm result.

This module is deliberately offline-only: it has no URL, requester, ingress,
upload, authorization, or device API.  Its CLI can only create a new local
bundle or deeply validate an existing one.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Optional, Sequence
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.color_pipeline import encode_rgb_png, reference_palette  # noqa: E402
from host.color_pipeline.color import linear_channel_to_srgb  # noqa: E402
from host.epd_frame import (  # noqa: E402
    CONTROLLER_FRAME_BYTES,
    FRAME_BYTES,
    HEIGHT,
    WIDTH,
    ControllerMapping,
    controller_stream,
    fnv1a,
    generate_fixture,
    pack_pixels,
    unpack_pixels,
    validate_frame,
)
from host.halftone_optimization import OverlapObservationModel  # noqa: E402
from tools.local_path_safety import (  # noqa: E402
    LocalPathSafetyError,
    require_local_regular_path_syntax,
)


SCHEMA_VERSION = 1
MANIFEST_KIND = "mf1750-g1-s1-low-spatial-transition-diagnostic"
ALGORITHM_ID = "g1-s1-low-spatial-transition-matched-v1"
MANIFEST_HASH_SCOPE = (
    "entire manifest excluding manifest_integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)

PHYSICAL_CODE_ORDER = (0, 1, 2, 3, 5, 6)
ALLOCATION_BLOCK_ORDER = (3, 2, 5, 6, 1, 0)
FIXED_CONTROLLER_MAPPINGS = (
    ControllerMapping(0, False, False, False),
    ControllerMapping(1, False, False, False),
)

REQUIRED_FILES = frozenset(
    {
        "frame.bin",
        "strict-final.png",
        "transition-map.png",
        "model.png",
        "manifest.json",
    }
)

# Frozen identities for the known prior state and the failed job2 candidate.
MAP_FIXTURE = "map-orient-v1"
MAP_FRAME_SHA256 = "1deedf924e40c676c2080fec08dfe5da10a8c1bb53b699ec4a85b0b6101b5c36"
MAP_FRAME_FNV1A = "0x9D04142D"
MAP_CS1_DTM_FNV1A = "0xF26832DD"
MAP_CS2_DTM_FNV1A = "0xFE199FF5"

FAILED_CANDIDATE_MANIFEST_FILE_SHA256 = (
    "88702d79b71ff1c901bd71f2315c3c0e7aeae8c31945f322d6be5f13c8ce272a"
)
FAILED_CANDIDATE_MANIFEST_CANONICAL_SHA256 = (
    "523c008465037e1cd4db6d2c4de61d170293f72712c854fd4a1d68356c7c695f"
)
FAILED_CANDIDATE_SIMULATION_REPORT_SHA256 = (
    "b8e822af02ca6c332a077052d78d5f2b9def81385b204016976551dbe214053a"
)
FAILED_CANDIDATE_CODES_SHA256 = (
    "8e662425d568a942ca5f4cac806d215edb58cebbc526826bdaafde4f7c66a097"
)
FAILED_CANDIDATE_FRAME_SHA256 = (
    "28ce21501a93c667b81bf474e9811100c8d5ebb7116359e82ee081cebde07e25"
)
FAILED_CANDIDATE_FRAME_FNV1A = "0x657DB1B5"
FAILED_CANDIDATE_CS1_DTM_FNV1A = "0x43E97823"
FAILED_CANDIDATE_CS2_DTM_FNV1A = "0xE8FA6243"

# Rows are old MAP codes and columns are new codes, both in PHYSICAL_CODE_ORDER.
GLOBAL_TRANSITION_MATRIX = (
    (20892, 12495, 1676, 1779, 1309, 1385),
    (173762, 87874, 37055, 47055, 41835, 38227),
    (6596, 12366, 3694, 1698, 3549, 1377),
    (17564, 14467, 2444, 7507, 1324, 3766),
    (19743, 9870, 1271, 5664, 4805, 2839),
    (8026, 7521, 3913, 3516, 1822, 3714),
)

# Frozen integer split.  Its constraints and weighted-L1 objective are
# re-evaluated below; no optimization package or runtime solver is required.
LEFT_TRANSITION_MATRIX = (
    (11220, 6710, 900, 955, 703, 744),
    (86127, 43556, 18367, 23323, 20736, 18947),
    (3298, 6183, 1847, 849, 1775, 688),
    (11027, 9082, 1534, 4713, 832, 2364),
    (7356, 3677, 473, 2110, 1791, 1057),
    (4264, 3088, 1906, 1659, 1485, 1854),
)
RIGHT_TRANSITION_MATRIX = tuple(
    tuple(GLOBAL_TRANSITION_MATRIX[row][column] - LEFT_TRANSITION_MATRIX[row][column]
          for column in range(6))
    for row in range(6)
)

OLD_LEFT_CAPACITIES = (21232, 211056, 14640, 29552, 16464, 14256)
OLD_RIGHT_CAPACITIES = (18304, 214752, 14640, 17520, 27728, 14256)
TARGET_TOTAL_COUNTS = (246583, 144593, 50053, 67219, 54644, 51308)
TARGET_LEFT_COUNTS = (123292, 72296, 25027, 33609, 27322, 25654)
TARGET_RIGHT_COUNTS = (123291, 72297, 25026, 33610, 27322, 25654)
FAILED_LEFT_COUNTS = (133783, 78981, 45290, 42894, 2494, 3758)
FAILED_RIGHT_COUNTS = (112800, 65612, 4763, 24325, 52150, 47550)

SPLIT_OBJECTIVE_VALUE = 48_106_656
SPLIT_OLD_GREEN_CONTRIBUTION = 47_044_800
HALF_TRANSITION_CELLWISE_L1_FROM_FAILED = 107_348

EXPECTED_CODES_SHA256 = "caafec835cc5ef8a91767d71293100b6763442d337737fc0594e40ff9f8edbfa"
EXPECTED_FRAME_SHA256 = "ba373d138c525fd7e59cc6c4ae6037191fa41388507b347da9f6f8bdece9fc65"
EXPECTED_FRAME_FNV1A = "0xA9641618"
EXPECTED_CS1_DTM_SHA256 = "c85a03621501c8bb0c535467a1581ab451f5bb0fc50fc4227c31e576d23d6070"
EXPECTED_CS1_DTM_FNV1A = "0xCB085C03"
EXPECTED_CS2_DTM_SHA256 = "bf25594c886c2046512eecf24795f8c2a5dacf1d9c565501658a6e6ea9889bd7"
EXPECTED_CS2_DTM_FNV1A = "0x9ABD749A"

EXPECTED_UNCHANGED_PIXELS = 128_486
EXPECTED_CHANGED_PIXELS = 485_914

FAILED_SPATIAL_METRICS = {
    "horizontal_internal": {"different": 209648, "possible": 613200},
    "controller_seam": {"different": 242, "possible": 600},
    "vertical": {"different": 294563, "possible": 613376},
    "total_four_neighbour_edges": {"different": 504453, "possible": 1227176},
    "boundary_pixels": {"count": 443560, "possible": 614400},
}


class DiagnosticError(RuntimeError):
    """Raised when an offline diagnostic artifact fails closed."""


@dataclass(frozen=True)
class DiagnosticArtifacts:
    """All deterministic bytes in one diagnostic bundle."""

    frame: bytes
    strict_final_png: bytes
    transition_map_png: bytes
    model_png: bytes
    manifest: Mapping[str, Any]
    manifest_bytes: bytes

    def files(self) -> dict[str, bytes]:
        return {
            "frame.bin": self.frame,
            "strict-final.png": self.strict_final_png,
            "transition-map.png": self.transition_map_png,
            "model.png": self.model_png,
            "manifest.json": self.manifest_bytes,
        }


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
        raise DiagnosticError(f"canonical JSON encoding failed: {error}") from error


def _sha256(payload: bytes | bytearray | memoryview) -> str:
    return hashlib.sha256(payload).hexdigest()


def _matrix_rows(matrix: Sequence[Sequence[int]]) -> tuple[int, ...]:
    return tuple(sum(row) for row in matrix)


def _matrix_columns(matrix: Sequence[Sequence[int]]) -> tuple[int, ...]:
    return tuple(sum(matrix[row][column] for row in range(6)) for column in range(6))


def _matrix_record(matrix: Sequence[Sequence[int]]) -> list[list[int]]:
    return [list(row) for row in matrix]


def _counts(codes: bytes | bytearray | memoryview) -> tuple[int, ...]:
    raw = bytes(codes)
    return tuple(raw.count(code) for code in PHYSICAL_CODE_ORDER)


def _mapping_record(mapping: ControllerMapping) -> dict[str, int | bool]:
    return {
        "source_half": mapping.source_half,
        "flip_x": mapping.flip_x,
        "flip_y": mapping.flip_y,
        "nibble_swap": mapping.nibble_swap,
    }


def split_objective(matrix: Sequence[Sequence[int]] = LEFT_TRANSITION_MATRIX) -> int:
    """Return J=sum(|S_r*X_rc-L_r*T_rc|) for the frozen integer split."""

    if len(matrix) != 6 or any(len(row) != 6 for row in matrix):
        raise DiagnosticError("transition split must be a 6x6 matrix")
    total = 0
    for row in range(6):
        source_total = OLD_LEFT_CAPACITIES[row] + OLD_RIGHT_CAPACITIES[row]
        for column in range(6):
            value = matrix[row][column]
            if type(value) is not int or not 0 <= value <= GLOBAL_TRANSITION_MATRIX[row][column]:
                raise DiagnosticError("transition split contains an invalid integer cell")
            total += abs(
                source_total * value
                - OLD_LEFT_CAPACITIES[row] * GLOBAL_TRANSITION_MATRIX[row][column]
            )
    return total


def validate_frozen_contract() -> None:
    """Validate all matrix/count constraints before constructing any artifact."""

    if _matrix_rows(GLOBAL_TRANSITION_MATRIX) != tuple(
        left + right for left, right in zip(OLD_LEFT_CAPACITIES, OLD_RIGHT_CAPACITIES)
    ):
        raise DiagnosticError("global transition rows do not match prior MAP capacities")
    if _matrix_columns(GLOBAL_TRANSITION_MATRIX) != TARGET_TOTAL_COUNTS:
        raise DiagnosticError("global transition columns do not match failed final counts")
    if _matrix_rows(LEFT_TRANSITION_MATRIX) != OLD_LEFT_CAPACITIES:
        raise DiagnosticError("left transition rows do not match prior left capacities")
    if _matrix_rows(RIGHT_TRANSITION_MATRIX) != OLD_RIGHT_CAPACITIES:
        raise DiagnosticError("right transition rows do not match prior right capacities")
    if _matrix_columns(LEFT_TRANSITION_MATRIX) != TARGET_LEFT_COUNTS:
        raise DiagnosticError("left transition columns do not match target left counts")
    if _matrix_columns(RIGHT_TRANSITION_MATRIX) != TARGET_RIGHT_COUNTS:
        raise DiagnosticError("right transition columns do not match target right counts")
    if tuple(left + right for left, right in zip(TARGET_LEFT_COUNTS, TARGET_RIGHT_COUNTS)) != TARGET_TOTAL_COUNTS:
        raise DiagnosticError("left/right target counts do not reconstruct full target counts")
    if tuple(left - right for left, right in zip(TARGET_LEFT_COUNTS, TARGET_RIGHT_COUNTS)) != (1, -1, 1, -1, 0, 0):
        raise DiagnosticError("odd-count allocation rule changed")
    if split_objective() != SPLIT_OBJECTIVE_VALUE:
        raise DiagnosticError("frozen weighted-L1 split objective changed")


def generate_diagnostic_codes() -> tuple[bytes, bytes]:
    """Return ``(prior_codes, diagnostic_codes)`` without file or device I/O."""

    validate_frozen_contract()
    prior_frame = generate_fixture(MAP_FIXTURE)
    validate_frame(prior_frame)
    if _sha256(prior_frame) != MAP_FRAME_SHA256 or f"0x{fnv1a(prior_frame):08X}" != MAP_FRAME_FNV1A:
        raise DiagnosticError("canonical MAP prior identity changed")
    prior_codes = unpack_pixels(prior_frame)
    if len(prior_codes) != WIDTH * HEIGHT:
        raise DiagnosticError("canonical MAP prior pixel count changed")

    code_rank = {code: rank for rank, code in enumerate(PHYSICAL_CODE_ORDER)}
    result = bytearray(WIDTH * HEIGHT)
    half_width = WIDTH // 2
    for side, transition_matrix in enumerate((LEFT_TRANSITION_MATRIX, RIGHT_TRANSITION_MATRIX)):
        positions = {code: [] for code in PHYSICAL_CODE_ORDER}
        x0 = side * half_width
        x1 = x0 + half_width
        for y in range(HEIGHT):
            row = y * WIDTH
            for x in range(x0, x1):
                index = row + x
                positions[prior_codes[index]].append(index)
        expected_capacities = OLD_LEFT_CAPACITIES if side == 0 else OLD_RIGHT_CAPACITIES
        if tuple(len(positions[code]) for code in PHYSICAL_CODE_ORDER) != expected_capacities:
            raise DiagnosticError("prior MAP half capacities changed")

        for old_rank, old_code in enumerate(PHYSICAL_CODE_ORDER):
            ordered_positions = positions[old_code]
            offset = 0
            for new_code in ALLOCATION_BLOCK_ORDER:
                count = transition_matrix[old_rank][code_rank[new_code]]
                end = offset + count
                for index in ordered_positions[offset:end]:
                    result[index] = new_code
                offset = end
            if offset != len(ordered_positions):
                raise DiagnosticError("transition allocation did not consume an old-code mask")

    codes = bytes(result)
    if _sha256(codes) != EXPECTED_CODES_SHA256:
        raise DiagnosticError("diagnostic code-stream identity changed")
    return prior_codes, codes


def _transition_matrix(prior: bytes, final: bytes, *, x0: int = 0, x1: int = WIDTH) -> tuple[tuple[int, ...], ...]:
    ranks = {code: rank for rank, code in enumerate(PHYSICAL_CODE_ORDER)}
    matrix = [[0 for _ in range(6)] for _ in range(6)]
    for y in range(HEIGHT):
        row = y * WIDTH
        for x in range(x0, x1):
            index = row + x
            try:
                old_rank = ranks[prior[index]]
                new_rank = ranks[final[index]]
            except KeyError as error:
                raise DiagnosticError(f"non-physical code in transition stream: {error}") from error
            matrix[old_rank][new_rank] += 1
    return tuple(tuple(row) for row in matrix)


def _fraction(different: int, possible: int) -> dict[str, int | float]:
    return {
        "different": different,
        "possible": possible,
        "ratio": different / possible,
    }


def _boundary_pixels(codes: bytes, *, x0: int, x1: int) -> int:
    count = 0
    for y in range(HEIGHT):
        row = y * WIDTH
        for x in range(x0, x1):
            code = codes[row + x]
            if (
                (x > x0 and codes[row + x - 1] != code)
                or (x + 1 < x1 and codes[row + x + 1] != code)
                or (y > 0 and codes[row - WIDTH + x] != code)
                or (y + 1 < HEIGHT and codes[row + WIDTH + x] != code)
            ):
                count += 1
    return count


def spatial_metrics(codes: bytes) -> dict[str, Any]:
    """Return deterministic 4-neighbour metrics with controller seam separate."""

    if len(codes) != WIDTH * HEIGHT:
        raise DiagnosticError("spatial metrics require one unpacked full-panel code stream")
    half_width = WIDTH // 2
    controller_records: list[dict[str, Any]] = []
    total_internal_h = 0
    total_v = 0
    internal_boundary_total = 0
    for side, label in ((0, "CS1"), (1, "CS2")):
        x0 = side * half_width
        x1 = x0 + half_width
        horizontal = sum(
            codes[y * WIDTH + x] != codes[y * WIDTH + x + 1]
            for y in range(HEIGHT)
            for x in range(x0, x1 - 1)
        )
        vertical = sum(
            codes[y * WIDTH + x] != codes[(y + 1) * WIDTH + x]
            for y in range(HEIGHT - 1)
            for x in range(x0, x1)
        )
        boundary = _boundary_pixels(codes, x0=x0, x1=x1)
        total_internal_h += horizontal
        total_v += vertical
        internal_boundary_total += boundary
        controller_records.append(
            {
                "controller": label,
                "horizontal_internal": _fraction(horizontal, HEIGHT * (half_width - 1)),
                "vertical": _fraction(vertical, (HEIGHT - 1) * half_width),
                "total_internal_edges": _fraction(
                    horizontal + vertical,
                    HEIGHT * (half_width - 1) + (HEIGHT - 1) * half_width,
                ),
                "internal_boundary_pixels": {
                    "count": boundary,
                    "possible": HEIGHT * half_width,
                    "ratio": boundary / (HEIGHT * half_width),
                },
            }
        )

    seam_matrix = [[0 for _ in range(6)] for _ in range(6)]
    ranks = {code: rank for rank, code in enumerate(PHYSICAL_CODE_ORDER)}
    seam_different = 0
    for y in range(HEIGHT):
        left = codes[y * WIDTH + half_width - 1]
        right = codes[y * WIDTH + half_width]
        seam_matrix[ranks[left]][ranks[right]] += 1
        seam_different += left != right

    full_boundary = _boundary_pixels(codes, x0=0, x1=WIDTH)
    full_horizontal = total_internal_h + seam_different
    total_edges = full_horizontal + total_v
    total_possible = HEIGHT * (WIDTH - 1) + (HEIGHT - 1) * WIDTH
    return {
        "definition": "undirected four-neighbour code-difference edges on the unpacked 1024x600 raster",
        "controllers": controller_records,
        "horizontal_internal": _fraction(total_internal_h, 2 * HEIGHT * (half_width - 1)),
        "controller_seam": {
            **_fraction(seam_different, HEIGHT),
            "definition": "rows y=0..599 where code[y,511] != code[y,512]",
            "pair_matrix": seam_matrix,
            "pair_matrix_code_order": list(PHYSICAL_CODE_ORDER),
            "matching": HEIGHT - seam_different,
        },
        "horizontal_full_including_seam": _fraction(full_horizontal, HEIGHT * (WIDTH - 1)),
        "vertical": _fraction(total_v, (HEIGHT - 1) * WIDTH),
        "total_four_neighbour_edges": _fraction(total_edges, total_possible),
        "boundary_pixels": {
            "count": full_boundary,
            "possible": WIDTH * HEIGHT,
            "ratio": full_boundary / (WIDTH * HEIGHT),
        },
        "seam_additional_boundary_endpoints": full_boundary - internal_boundary_total,
    }


def _strict_preview(codes: bytes) -> bytes:
    colours = {entry.code: entry.preview_rgb for entry in reference_palette().entries}
    rgb = bytearray(len(codes) * 3)
    offset = 0
    for code in codes:
        try:
            colour = colours[code]
        except KeyError as error:
            raise DiagnosticError(f"preview received a non-physical code: {code}") from error
        rgb[offset : offset + 3] = bytes(colour)
        offset += 3
    return encode_rgb_png(WIDTH, HEIGHT, rgb)


def _transition_colour(index: int) -> tuple[int, int, int]:
    # The red component is unique for all 36 entries, so the legend is
    # unambiguous without relying on a platform colour library.
    return (
        (17 + 73 * index) & 0xFF,
        (43 + 151 * index) & 0xFF,
        (91 + 199 * index) & 0xFF,
    )


def _transition_preview(prior: bytes, final: bytes) -> tuple[bytes, list[dict[str, Any]]]:
    ranks = {code: rank for rank, code in enumerate(PHYSICAL_CODE_ORDER)}
    rgb = bytearray(len(final) * 3)
    legend = []
    for old_rank, old_code in enumerate(PHYSICAL_CODE_ORDER):
        for new_rank, new_code in enumerate(PHYSICAL_CODE_ORDER):
            index = old_rank * 6 + new_rank
            legend.append(
                {
                    "old_code": old_code,
                    "new_code": new_code,
                    "rgb": list(_transition_colour(index)),
                }
            )
    offset = 0
    for old_code, new_code in zip(prior, final):
        index = ranks[old_code] * 6 + ranks[new_code]
        rgb[offset : offset + 3] = bytes(_transition_colour(index))
        offset += 3
    return encode_rgb_png(WIDTH, HEIGHT, rgb), legend


def _model_preview(codes: bytes) -> tuple[bytes, Mapping[str, Any]]:
    model = OverlapObservationModel.gaussian_simulation()
    linear = model.render_linear_rgb(codes, WIDTH, HEIGHT, palette=reference_palette())
    rgb = bytearray(len(linear))
    for index, value in enumerate(linear):
        channel = min(1.0, max(0.0, float(value)))
        rgb[index] = min(255, max(0, int(round(linear_channel_to_srgb(channel) * 255.0))))
    return encode_rgb_png(WIDTH, HEIGHT, rgb), model.metadata()


def _file_record(filename: str, payload: bytes, *, semantics: str) -> dict[str, Any]:
    return {
        "file": filename,
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "width": WIDTH,
        "height": HEIGHT,
        "semantics": semantics,
    }


def build_diagnostic_artifacts() -> DiagnosticArtifacts:
    """Rebuild every artifact byte and fail if any frozen identity changes."""

    prior_codes, codes = generate_diagnostic_codes()
    frame = pack_pixels(codes)
    validate_frame(frame)
    if len(frame) != FRAME_BYTES:
        raise DiagnosticError("diagnostic packed frame length changed")
    if _sha256(frame) != EXPECTED_FRAME_SHA256 or f"0x{fnv1a(frame):08X}" != EXPECTED_FRAME_FNV1A:
        raise DiagnosticError("diagnostic packed frame identity changed")

    controller_records = []
    expected = (
        (EXPECTED_CS1_DTM_SHA256, EXPECTED_CS1_DTM_FNV1A),
        (EXPECTED_CS2_DTM_SHA256, EXPECTED_CS2_DTM_FNV1A),
    )
    for index, (mapping, identities) in enumerate(zip(FIXED_CONTROLLER_MAPPINGS, expected), start=1):
        stream = controller_stream(frame, mapping)
        sha256 = _sha256(stream)
        fnv = f"0x{fnv1a(stream):08X}"
        if len(stream) != CONTROLLER_FRAME_BYTES or (sha256, fnv) != identities:
            raise DiagnosticError(f"CS{index} diagnostic DTM identity changed")
        controller_records.append(
            {
                "controller": f"CS{index}",
                "mapping": _mapping_record(mapping),
                "dtm_bytes": len(stream),
                "dtm_sha256": sha256,
                "dtm_fnv1a": fnv,
            }
        )

    global_matrix = _transition_matrix(prior_codes, codes)
    left_matrix = _transition_matrix(prior_codes, codes, x0=0, x1=WIDTH // 2)
    right_matrix = _transition_matrix(prior_codes, codes, x0=WIDTH // 2, x1=WIDTH)
    if global_matrix != GLOBAL_TRANSITION_MATRIX:
        raise DiagnosticError("generated global transition matrix changed")
    if left_matrix != LEFT_TRANSITION_MATRIX or right_matrix != RIGHT_TRANSITION_MATRIX:
        raise DiagnosticError("generated controller transition split changed")

    counts_total = _counts(codes)
    counts_left = _counts(b"".join(codes[y * WIDTH : y * WIDTH + WIDTH // 2] for y in range(HEIGHT)))
    counts_right = _counts(b"".join(codes[y * WIDTH + WIDTH // 2 : (y + 1) * WIDTH] for y in range(HEIGHT)))
    if (counts_total, counts_left, counts_right) != (
        TARGET_TOTAL_COUNTS,
        TARGET_LEFT_COUNTS,
        TARGET_RIGHT_COUNTS,
    ):
        raise DiagnosticError("generated final colour counts changed")

    changed = sum(old != new for old, new in zip(prior_codes, codes))
    unchanged = len(codes) - changed
    if (unchanged, changed) != (EXPECTED_UNCHANGED_PIXELS, EXPECTED_CHANGED_PIXELS):
        raise DiagnosticError("generated changed/unchanged counts changed")

    metrics = spatial_metrics(codes)
    if (
        metrics["horizontal_internal"]["different"] != 13462
        or metrics["controller_seam"]["different"] != 460
        or metrics["vertical"]["different"] != 15643
        or metrics["total_four_neighbour_edges"]["different"] != 29565
        or metrics["boundary_pixels"]["count"] != 52072
    ):
        raise DiagnosticError("generated spatial metrics changed")

    strict_png = _strict_preview(codes)
    transition_png, transition_legend = _transition_preview(prior_codes, codes)
    model_png, model_metadata = _model_preview(codes)

    old_green_objective = sum(
        abs(
            (OLD_LEFT_CAPACITIES[5] + OLD_RIGHT_CAPACITIES[5])
            * LEFT_TRANSITION_MATRIX[5][column]
            - OLD_LEFT_CAPACITIES[5] * GLOBAL_TRANSITION_MATRIX[5][column]
        )
        for column in range(6)
    )
    if old_green_objective != SPLIT_OLD_GREEN_CONTRIBUTION:
        raise DiagnosticError("old-green split-objective contribution changed")

    failed_edges = FAILED_SPATIAL_METRICS["total_four_neighbour_edges"]["different"]
    new_edges = metrics["total_four_neighbour_edges"]["different"]
    base_manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "algorithm": {
            "id": ALGORITHM_ID,
            "physical_code_order": list(PHYSICAL_CODE_ORDER),
            "controller_processing": "independent logical 512x600 halves",
            "old_mask_position_order": "top-left row-major within each controller half",
            "new_code_block_order": list(ALLOCATION_BLOCK_ORDER),
            "randomness": False,
            "bayer_or_threshold_map": False,
            "split": {
                "variable": "integer X_rc in [0,T_rc]",
                "constraints": [
                    "sum_c X_rc = old_left_capacity_r",
                    "sum_r X_rc = target_left_count_c",
                    "right_rc = T_rc - X_rc",
                ],
                "objective_id": "row-capacity-proportional-weighted-l1-v1",
                "objective": "J=sum_rc(abs(S_r*X_rc-L_r*T_rc)); S_r=L_r+R_r",
                "objective_value": SPLIT_OBJECTIVE_VALUE,
                "frozen_solution": True,
                "runtime_solver": None,
                "runtime_optimality_proof": False,
                "deterministic_tie_break_definition": (
                    "after primary J, lexicographically minimize row-major X_rc in physical code order"
                ),
                "not_minimax": True,
                "not_per_transition_cell_balanced": True,
                "old_green_objective_contribution": SPLIT_OLD_GREEN_CONTRIBUTION,
                "old_green_objective_ratio": SPLIT_OLD_GREEN_CONTRIBUTION / SPLIT_OBJECTIVE_VALUE,
            },
        },
        "prior_state": {
            "declared_last_visible_frame": True,
            "frame": {
                "fixture": MAP_FIXTURE,
                "bytes": FRAME_BYTES,
                "sha256": MAP_FRAME_SHA256,
                "fnv1a": MAP_FRAME_FNV1A,
                "cs1_dtm_fnv1a": MAP_CS1_DTM_FNV1A,
                "cs2_dtm_fnv1a": MAP_CS2_DTM_FNV1A,
            },
        },
        "failed_reference": {
            "run": "G1S1_AWORDERED_RUN1_20260806_212715",
            "job_id": 2,
            "operation_id": 2,
            "algorithm": "area-weighted-ordered-8x8",
            "evaluation": "inconclusive",
            "authorization_state": "unknown_do_not_retry",
            "manifest_file_sha256": FAILED_CANDIDATE_MANIFEST_FILE_SHA256,
            "manifest_canonical_sha256": FAILED_CANDIDATE_MANIFEST_CANONICAL_SHA256,
            "simulation_report_sha256": FAILED_CANDIDATE_SIMULATION_REPORT_SHA256,
            "codes_sha256": FAILED_CANDIDATE_CODES_SHA256,
            "frame_sha256": FAILED_CANDIDATE_FRAME_SHA256,
            "frame_fnv1a": FAILED_CANDIDATE_FRAME_FNV1A,
            "cs1_dtm_fnv1a": FAILED_CANDIDATE_CS1_DTM_FNV1A,
            "cs2_dtm_fnv1a": FAILED_CANDIDATE_CS2_DTM_FNV1A,
            "left_final_counts": list(FAILED_LEFT_COUNTS),
            "right_final_counts": list(FAILED_RIGHT_COUNTS),
            "left_minus_right_final_counts": [
                left - right for left, right in zip(FAILED_LEFT_COUNTS, FAILED_RIGHT_COUNTS)
            ],
            "spatial_metrics": FAILED_SPATIAL_METRICS,
        },
        "diagnostic": {
            "frame": {
                "file": "frame.bin",
                "bytes": len(frame),
                "encoding": "canonical-row-major-two-4bit-codes-per-byte-even-x-high-nibble",
                "sha256": _sha256(frame),
                "codes_sha256": _sha256(codes),
                "fnv1a": f"0x{fnv1a(frame):08X}",
            },
            "controllers": controller_records,
            "counts": {
                "code_order": list(PHYSICAL_CODE_ORDER),
                "total": list(counts_total),
                "left": list(counts_left),
                "right": list(counts_right),
                "left_minus_right": [left - right for left, right in zip(counts_left, counts_right)],
                "odd_extra_rule": (
                    "odd totals occur for codes 0,1,2,3; alternating odd ranks assign the extra "
                    "pixel left for codes 0 and 2 and right for codes 1 and 3"
                ),
                "per_code_absolute_half_difference_max": 1,
            },
            "transitions": {
                "code_order": list(PHYSICAL_CODE_ORDER),
                "global": _matrix_record(global_matrix),
                "left": _matrix_record(left_matrix),
                "right": _matrix_record(right_matrix),
                "old_left_capacities": list(OLD_LEFT_CAPACITIES),
                "old_right_capacities": list(OLD_RIGHT_CAPACITIES),
                "global_exactly_matches_failed_reference": True,
                "half_matrices_match_failed_reference": False,
                "half_matrices_cellwise_l1_from_failed_reference": HALF_TRANSITION_CELLWISE_L1_FROM_FAILED,
            },
            "changed_pixels_from_prior": {
                "unchanged": unchanged,
                "changed": changed,
                "changed_ratio": changed / len(codes),
                "global_exactly_matches_failed_reference": True,
            },
            "spatial_metrics": metrics,
            "spatial_comparison_to_failed": {
                "total_different_edges_reduction": failed_edges - new_edges,
                "total_different_edges_reduction_ratio": (failed_edges - new_edges) / failed_edges,
                "failed_to_diagnostic_edge_ratio": failed_edges / new_edges,
                "seam_changed_from": 242,
                "seam_changed_to": 460,
            },
        },
        "previews": {
            "strict_final": _file_record(
                "strict-final.png",
                strict_png,
                semantics="strict reference-palette rendering of final six-code stream",
            ),
            "transition_map": {
                **_file_record(
                    "transition-map.png",
                    transition_png,
                    semantics="36-class old MAP code to diagnostic final code visualization",
                ),
                "legend": transition_legend,
            },
            "model": {
                **_file_record(
                    "model.png",
                    model_png,
                    semantics="uncalibrated Gaussian overlap observation simulation",
                ),
                "observation_model": model_metadata,
            },
        },
        "classification": {
            "experimental": True,
            "formal": False,
            "hardware_qualified": False,
            "hardware_tested": False,
            "simulation_only": True,
            "upload_authorized": False,
        },
        "transport": {
            "mode": "offline",
            "device_io_performed": False,
            "network_io_performed": False,
            "ingress_performed": False,
            "endpoint": None,
            "method": None,
            "upload_authorized": False,
        },
        "interpretation": {
            "intervention": (
                "jointly lowers controller-internal spatial edges and balances per-controller "
                "final/transition allocation while preserving full-panel histogram and global transitions"
            ),
            "if_nominal": (
                "supports that full-panel final histogram and global 6x6 transition counts are not "
                "individually sufficient deterministic causes in that run"
            ),
            "if_same_failure": (
                "supports that high spatial frequency and original half imbalance are not necessary "
                "conditions; shared load, waveform/history, or episodic device state remain compatible"
            ),
            "limitations": [
                "one run cannot separate controller-internal spatial frequency from half-load balance",
                "controller transition cells are not individually balanced and the split is not minimax",
                "the controller seam increases from 242/600 to 460/600 and remains a covariate",
                "pixel transition counts are not measured electrical energy, time, or optical cost",
                "no outcome qualifies ordered dithering or any other mixing algorithm",
                "one outcome cannot generalize across panels, temperature, waveform, or repetitions",
            ],
            "future_factorial_design": [
                "high-frequency plus original imbalance (existing failed reference)",
                "low-frequency plus original imbalance",
                "low-frequency plus balanced halves (this diagnostic)",
                "high-frequency plus balanced halves",
            ],
        },
    }
    integrity = _sha256(_canonical_json(base_manifest))
    manifest = dict(base_manifest)
    manifest["manifest_integrity"] = {
        "canonical_sha256": integrity,
        "canonical_sha256_scope": MANIFEST_HASH_SCOPE,
    }
    manifest_bytes = _canonical_json(manifest)
    return DiagnosticArtifacts(
        frame=frame,
        strict_final_png=strict_png,
        transition_map_png=transition_png,
        model_png=model_png,
        manifest=manifest,
        manifest_bytes=manifest_bytes,
    )


def _reject_symlink_ancestors(path: Path, *, label: str) -> None:
    current = path.absolute()
    while True:
        if os.path.lexists(current) and current.is_symlink():
            raise DiagnosticError(f"{label} must not traverse a symlink")
        parent = current.parent
        if parent == current:
            return
        current = parent


def _safe_directory(path: Path, *, label: str, must_exist: bool) -> Path:
    try:
        require_local_regular_path_syntax(path, label=label)
    except LocalPathSafetyError as error:
        raise DiagnosticError(str(error)) from error
    _reject_symlink_ancestors(path if must_exist else path.parent, label=label)
    if must_exist:
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise DiagnosticError(f"{label} does not exist: {error}") from error
        if path.is_symlink() or not resolved.is_dir():
            raise DiagnosticError(f"{label} must be a real local directory")
        return resolved
    if os.path.lexists(path):
        raise DiagnosticError(f"{label} already exists; refusing to overwrite it")
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as error:
        raise DiagnosticError(f"{label} parent does not exist: {error}") from error
    if not parent.is_dir() or parent.is_symlink():
        raise DiagnosticError(f"{label} parent must be a real local directory")
    return parent / path.name


def _load_json_strict(payload: bytes) -> Any:
    def reject_constant(value: str) -> None:
        raise DiagnosticError(f"manifest contains forbidden JSON constant {value}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise DiagnosticError(f"manifest contains duplicate key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except DiagnosticError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DiagnosticError(f"manifest is not strict UTF-8 JSON: {error}") from error


def validate_diagnostic_directory(directory: Path) -> Mapping[str, Any]:
    """Deeply regenerate and compare a diagnostic bundle byte-for-byte."""

    resolved = _safe_directory(directory, label="diagnostic directory", must_exist=True)
    try:
        entries = tuple(resolved.iterdir())
    except OSError as error:
        raise DiagnosticError(f"could not enumerate diagnostic directory: {error}") from error
    if any(entry.is_symlink() for entry in entries):
        raise DiagnosticError("diagnostic directory must not contain symlinks")
    actual_files = {entry.name for entry in entries if entry.is_file()}
    if actual_files != REQUIRED_FILES or any(not entry.is_file() for entry in entries):
        raise DiagnosticError(
            f"diagnostic directory file set must be exactly {sorted(REQUIRED_FILES)}"
        )

    try:
        manifest_bytes = (resolved / "manifest.json").read_bytes()
    except OSError as error:
        raise DiagnosticError(f"could not read diagnostic manifest: {error}") from error
    manifest = _load_json_strict(manifest_bytes)
    if not isinstance(manifest, dict):
        raise DiagnosticError("diagnostic manifest root must be an object")
    if manifest_bytes != _canonical_json(manifest):
        raise DiagnosticError("diagnostic manifest is not canonical JSON")
    integrity = manifest.get("manifest_integrity")
    if not isinstance(integrity, Mapping):
        raise DiagnosticError("diagnostic manifest integrity record is missing")
    unsigned = dict(manifest)
    unsigned.pop("manifest_integrity", None)
    if integrity != {
        "canonical_sha256": _sha256(_canonical_json(unsigned)),
        "canonical_sha256_scope": MANIFEST_HASH_SCOPE,
    }:
        raise DiagnosticError("diagnostic manifest canonical integrity is invalid")

    expected = build_diagnostic_artifacts()
    if manifest != expected.manifest or manifest_bytes != expected.manifest_bytes:
        raise DiagnosticError("diagnostic manifest does not match deep regeneration")
    for filename, expected_payload in expected.files().items():
        try:
            payload = (resolved / filename).read_bytes()
        except OSError as error:
            raise DiagnosticError(f"could not read diagnostic file {filename}: {error}") from error
        if payload != expected_payload:
            raise DiagnosticError(f"diagnostic file {filename} does not match deep regeneration")
    return manifest


def write_diagnostic_directory(output_dir: Path) -> Mapping[str, Any]:
    """Atomically create a new deterministic bundle without overwriting paths."""

    destination = _safe_directory(output_dir, label="output directory", must_exist=False)
    artifacts = build_diagnostic_artifacts()
    temporary = destination.parent / f".{destination.name}.tmp-{uuid.uuid4().hex}"
    _reject_symlink_ancestors(temporary.parent, label="temporary output directory")
    try:
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
        if isinstance(error, DiagnosticError):
            raise
        raise DiagnosticError(f"could not create diagnostic bundle: {error}") from error
    return validate_diagnostic_directory(destination)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate or deeply validate the offline G1/S1 low-spatial diagnostic bundle."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output-dir", type=Path, help="new local bundle directory")
    mode.add_argument("--validate-dir", type=Path, help="existing local bundle directory")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.output_dir is not None:
            manifest = write_diagnostic_directory(args.output_dir)
            mode = "generated"
            directory = args.output_dir
        else:
            manifest = validate_diagnostic_directory(args.validate_dir)
            mode = "validated"
            directory = args.validate_dir
    except (DiagnosticError, OSError, ValueError) as error:
        parser.exit(2, f"error: {error}\n")
    summary = {
        "ok": True,
        "mode": mode,
        "directory": os.fspath(directory),
        "kind": manifest["kind"],
        "frame_sha256": manifest["diagnostic"]["frame"]["sha256"],
        "frame_fnv1a": manifest["diagnostic"]["frame"]["fnv1a"],
        "manifest_canonical_sha256": manifest["manifest_integrity"]["canonical_sha256"],
        "device_io_performed": False,
        "upload_authorized": False,
    }
    print(_canonical_json(summary).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
