#!/usr/bin/env python3
"""Build or deeply validate one offline clustered G1/S1 quality candidate.

The only source is the frozen, deeply validated area-weighted blue-noise
bundle.  Every 32x32 tile (and the 32x24 bottom residual tiles) keeps that
source frame's exact six-code histogram and, within each fixed true-screen
prior code, its exact transition counts.  Pixels are rearranged into
contiguous code blocks along a deterministic Hilbert path.  This module has
no network, device, upload, or refresh surface.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
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
    pack_pixels,
    unpack_pixels,
    validate_frame,
)
from host.halftone_optimization import OverlapObservationModel  # noqa: E402
from tools import g1_s1_low_spatial_diagnostic as low_spatial  # noqa: E402
from tools import g1_s1_panel_candidate as blue_noise  # noqa: E402
from tools.local_path_safety import (  # noqa: E402
    LocalPathSafetyError,
    require_local_regular_path_syntax,
)


SCHEMA_VERSION = 1
MANIFEST_KIND = "mf1750-g1-s1-clustered-quality-candidate"
MANIFEST_HASH_SCOPE = (
    "entire manifest excluding manifest_integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
ALGORITHM_ID = "g1-s1-per-tile-hilbert-cluster-v1"
TILE_SIDE = 32
COUNTERFACTUAL_TILE_SIDE = 16
PHYSICAL_CODE_ORDER = (0, 1, 2, 3, 5, 6)
CLUSTER_CODE_ORDER = (3, 2, 5, 6, 1, 0)
CONTROLLER_MAPPINGS = (ControllerMapping(0), ControllerMapping(1))
PREVIEW_FILES = {
    "source": "source.png",
    "mapped": "mapped.png",
    "strict_final": "strict-final.png",
    "model": "model.png",
}
REQUIRED_FILES = frozenset({"frame.bin", "manifest.json", *PREVIEW_FILES.values()})

BASELINE_DIR = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "G1S1_QUALITY_BLUE_NOISE_OFFLINE_20260806"
)
BASELINE_MANIFEST_FILE_SHA256 = "69244cebe2e37c0d26404b85b9d89471cd95d492a9599481e5f34968c3159a48"
BASELINE_MANIFEST_CANONICAL_SHA256 = "9f43658ffccb3e19dadfcda8a98ba78e5bbf1c06f02d24e57f476bfecda45b94"
BASELINE_FRAME_SHA256 = "eed46ab43bebe1b1056736d43d0189ea26650ff81fe5af1dd52a5882e447faf9"
BASELINE_FRAME_FNV1A = "0xB932966C"
BASELINE_CODES_SHA256 = "7dfa89c197472be138093510003da10dfc1d82b61e65392383305bf122e7aed0"
BASELINE_SOURCE_SHA256 = "b8400d6c901fcfefac49eafb2b2db4dadfdc5615392640dfe4cef7efe068f101"
BASELINE_MAPPED_SHA256 = "22488999efd344e2f3462de09ca1db6eb36e95ab4a728f3481990acc3503d1ef"

EXPECTED_CODES_SHA256 = "8c277487749a326c56ef7627541e51f58bca6b5f3f34937a8b93b46f188d7ecd"
EXPECTED_FRAME_SHA256 = "eabb228afd79fc09e2b2e613594f3d06e9d1d608ac2c1b05ee6a3cf38b8f7b9a"
EXPECTED_FRAME_FNV1A = "0xFA096DEB"

PRIOR_DIR = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "G1S1_LOW_SPATIAL_TRANSITION_MATCHED_20260806_231430"
)
PRIOR_MANIFEST_FILE_SHA256 = "07146b9254414e1454d9143f4af5706a8c5f69eb9125dce341206bbc441afb4d"
PRIOR_MANIFEST_CANONICAL_SHA256 = "594d31031b4413ac83c376854dcd35f522e1ae769613908f3fa7289d5fece91d"
PRIOR_FRAME_SHA256 = "ba373d138c525fd7e59cc6c4ae6037191fa41388507b347da9f6f8bdece9fc65"
PRIOR_FRAME_FNV1A = "0xA9641618"
PRIOR_CODES_SHA256 = "caafec835cc5ef8a91767d71293100b6763442d337737fc0594e40ff9f8edbfa"

FAILED_REFERENCE = {
    "artifact_id": "G1S1_AWORDERED_20260806_204800",
    "frame_sha256": "28ce21501a93c667b81bf474e9811100c8d5ebb7116359e82ee081cebde07e25",
    "frame_fnv1a": "0x657DB1B5",
    "codes_sha256": "8e662425d568a942ca5f4cac806d215edb58cebbc526826bdaafde4f7c66a097",
}
FAILED_METRIC_COUNTS = {
    "horizontal_internal": (209_648, 613_200),
    "controller_seam": (242, 600),
    "vertical": (294_563, 613_376),
    "total_edges": (504_453, 1_227_176),
    "boundary_pixels": (443_560, 614_400),
}


class ClusteredCandidateError(RuntimeError):
    """Raised when an offline candidate contract cannot be proven."""


@dataclass(frozen=True)
class ClusteredArtifacts:
    codes: bytes
    frame: bytes
    source_png: bytes
    mapped_png: bytes
    strict_final_png: bytes
    model_png: bytes
    manifest: Mapping[str, Any]
    manifest_bytes: bytes

    def files(self) -> dict[str, bytes]:
        return {
            "frame.bin": self.frame,
            "source.png": self.source_png,
            "mapped.png": self.mapped_png,
            "strict-final.png": self.strict_final_png,
            "model.png": self.model_png,
            "manifest.json": self.manifest_bytes,
        }


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
        raise ClusteredCandidateError(f"value is not canonical-JSON encodable: {error}") from error


def _mapping_record(mapping: ControllerMapping) -> dict[str, int | bool]:
    return {
        "source_half": mapping.source_half,
        "flip_x": mapping.flip_x,
        "flip_y": mapping.flip_y,
        "nibble_swap": mapping.nibble_swap,
    }


def _counts(codes: bytes, *, x0: int = 0, x1: int = WIDTH) -> list[int]:
    result = [0] * len(PHYSICAL_CODE_ORDER)
    by_code = {code: index for index, code in enumerate(PHYSICAL_CODE_ORDER)}
    for y_value in range(HEIGHT):
        row = y_value * WIDTH
        for x_value in range(x0, x1):
            result[by_code[codes[row + x_value]]] += 1
    return result


def hilbert_path(side: int) -> tuple[tuple[int, int], ...]:
    """Return a deterministic order-N Hilbert path for a power-of-two square."""

    if type(side) is not int or side <= 0 or side & (side - 1):
        raise ClusteredCandidateError("Hilbert side must be a positive power of two")
    points: list[tuple[int, int]] = []
    for distance in range(side * side):
        x_value = y_value = 0
        state = distance
        scale = 1
        while scale < side:
            rx = 1 & (state // 2)
            ry = 1 & (state ^ rx)
            if ry == 0:
                if rx == 1:
                    x_value = scale - 1 - x_value
                    y_value = scale - 1 - y_value
                x_value, y_value = y_value, x_value
            x_value += scale * rx
            y_value += scale * ry
            state //= 4
            scale *= 2
        points.append((x_value, y_value))
    if len(set(points)) != side * side:
        raise ClusteredCandidateError("Hilbert implementation did not cover the square exactly")
    if any(
        abs(first[0] - second[0]) + abs(first[1] - second[1]) != 1
        for first, second in zip(points, points[1:])
    ):
        raise ClusteredCandidateError("Hilbert implementation is not four-neighbour continuous")
    return tuple(points)


def _tile_histograms(codes: bytes, side: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    by_code = {code: index for index, code in enumerate(PHYSICAL_CODE_ORDER)}
    for y0 in range(0, HEIGHT, side):
        tile_height = min(side, HEIGHT - y0)
        for x0 in range(0, WIDTH, side):
            tile_width = min(side, WIDTH - x0)
            values = [0] * len(PHYSICAL_CODE_ORDER)
            for y_value in range(y0, y0 + tile_height):
                row = y_value * WIDTH
                for x_value in range(x0, x0 + tile_width):
                    values[by_code[codes[row + x_value]]] += 1
            records.append(
                {
                    "x": x0,
                    "y": y0,
                    "width": tile_width,
                    "height": tile_height,
                    "counts": values,
                }
            )
    return records


def _tile_prior_transitions(
    prior_codes: bytes, final_codes: bytes, side: int
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    index = {code: position for position, code in enumerate(PHYSICAL_CODE_ORDER)}
    for y0 in range(0, HEIGHT, side):
        tile_height = min(side, HEIGHT - y0)
        for x0 in range(0, WIDTH, side):
            tile_width = min(side, WIDTH - x0)
            matrix = [[0] * len(PHYSICAL_CODE_ORDER) for _ in PHYSICAL_CODE_ORDER]
            for y_value in range(y0, y0 + tile_height):
                row = y_value * WIDTH
                for x_value in range(x0, x0 + tile_width):
                    matrix[index[prior_codes[row + x_value]]][index[final_codes[row + x_value]]] += 1
            records.append(
                {
                    "x": x0,
                    "y": y0,
                    "width": tile_width,
                    "height": tile_height,
                    "matrix": matrix,
                }
            )
    return records


def _cluster_codes_for_analysis(
    base_codes: bytes,
    prior_codes: bytes,
    *,
    tile_side: int = TILE_SIDE,
) -> bytes:
    """Cluster each tile/prior-code cell while preserving its transition counts."""

    if tile_side not in (TILE_SIDE, COUNTERFACTUAL_TILE_SIDE):
        raise ClusteredCandidateError("tile_side is fixed to the audited 32 or 16 analysis path")
    for label, raster in (("base", base_codes), ("prior", prior_codes)):
        if len(raster) != WIDTH * HEIGHT or any(
            code not in PHYSICAL_CODE_ORDER for code in raster
        ):
            raise ClusteredCandidateError(
                f"{label} codes violate the fixed six-code raster contract"
            )
    path = hilbert_path(tile_side)
    output = bytearray(WIDTH * HEIGHT)
    by_code = {code: index for index, code in enumerate(PHYSICAL_CODE_ORDER)}
    for y0 in range(0, HEIGHT, tile_side):
        tile_height = min(tile_side, HEIGHT - y0)
        for x0 in range(0, WIDTH, tile_side):
            tile_width = min(tile_side, WIDTH - x0)
            for prior_code in PHYSICAL_CODE_ORDER:
                histogram = [0] * len(PHYSICAL_CODE_ORDER)
                positions: list[tuple[int, int]] = []
                for x_value, y_value in path:
                    if x_value >= tile_width or y_value >= tile_height:
                        continue
                    position = (y0 + y_value) * WIDTH + x0 + x_value
                    if prior_codes[position] != prior_code:
                        continue
                    positions.append((x_value, y_value))
                    histogram[by_code[base_codes[position]]] += 1
                labels = bytearray()
                for code in CLUSTER_CODE_ORDER:
                    labels.extend(bytes([code]) * histogram[by_code[code]])
                if len(labels) != len(positions):
                    raise ClusteredCandidateError("tile/prior-code allocation lost pixels")
                for (x_value, y_value), code in zip(positions, labels):
                    output[(y0 + y_value) * WIDTH + x0 + x_value] = code
    clustered = bytes(output)
    if _tile_histograms(clustered, tile_side) != _tile_histograms(base_codes, tile_side):
        raise ClusteredCandidateError("clustered output did not preserve every tile histogram")
    if _tile_prior_transitions(prior_codes, clustered, tile_side) != _tile_prior_transitions(
        prior_codes, base_codes, tile_side
    ):
        raise ClusteredCandidateError(
            "clustered output did not preserve every tile/prior-code transition matrix"
        )
    return clustered


def cluster_codes(base_codes: bytes, prior_codes: bytes) -> bytes:
    """Return the sole public candidate: the fixed 32px clustered raster."""

    return _cluster_codes_for_analysis(base_codes, prior_codes, tile_side=TILE_SIDE)


def _fraction(count: int, possible: int) -> dict[str, int | float]:
    return {"count": count, "possible": possible, "ratio": count / possible}


def spatial_metrics(codes: bytes) -> dict[str, Any]:
    if len(codes) != WIDTH * HEIGHT:
        raise ClusteredCandidateError("spatial metric raster length is invalid")
    horizontal_internal = seam = vertical = 0
    boundary = bytearray(WIDTH * HEIGHT)
    for y_value in range(HEIGHT):
        row = y_value * WIDTH
        for x_value in range(WIDTH - 1):
            if codes[row + x_value] == codes[row + x_value + 1]:
                continue
            if x_value == WIDTH // 2 - 1:
                seam += 1
            else:
                horizontal_internal += 1
            boundary[row + x_value] = 1
            boundary[row + x_value + 1] = 1
    for y_value in range(HEIGHT - 1):
        row = y_value * WIDTH
        next_row = row + WIDTH
        for x_value in range(WIDTH):
            if codes[row + x_value] == codes[next_row + x_value]:
                continue
            vertical += 1
            boundary[row + x_value] = 1
            boundary[next_row + x_value] = 1
    full_horizontal = horizontal_internal + seam
    return {
        "definition": "undirected four-neighbour code-difference edges; controller seam is x=511 to x=512",
        "horizontal_internal": _fraction(horizontal_internal, HEIGHT * (WIDTH - 2)),
        "controller_seam": _fraction(seam, HEIGHT),
        "horizontal_full": _fraction(full_horizontal, HEIGHT * (WIDTH - 1)),
        "vertical": _fraction(vertical, (HEIGHT - 1) * WIDTH),
        "total_edges": _fraction(
            full_horizontal + vertical,
            HEIGHT * (WIDTH - 1) + (HEIGHT - 1) * WIDTH,
        ),
        "boundary_pixels": _fraction(sum(boundary), WIDTH * HEIGHT),
    }


def _compact_reference_metrics(values: Mapping[str, tuple[int, int]]) -> dict[str, Any]:
    return {name: _fraction(count, possible) for name, (count, possible) in values.items()}


def _metric_delta(candidate: Mapping[str, Any], reference: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in (
        "horizontal_internal",
        "controller_seam",
        "vertical",
        "total_edges",
        "boundary_pixels",
    ):
        candidate_count = int(candidate[name]["count"])
        reference_count = int(reference[name]["count"])
        result[name] = {
            "count_delta": candidate_count - reference_count,
            "ratio_delta": float(candidate[name]["ratio"]) - float(reference[name]["ratio"]),
        }
    return result


def _transition_matrix(old: bytes, new: bytes, *, x0: int = 0, x1: int = WIDTH) -> list[list[int]]:
    matrix = [[0] * len(PHYSICAL_CODE_ORDER) for _ in PHYSICAL_CODE_ORDER]
    index = {code: position for position, code in enumerate(PHYSICAL_CODE_ORDER)}
    for y_value in range(HEIGHT):
        row = y_value * WIDTH
        for x_value in range(x0, x1):
            matrix[index[old[row + x_value]]][index[new[row + x_value]]] += 1
    return matrix


def _transition_record(old: bytes, new: bytes) -> dict[str, Any]:
    global_matrix = _transition_matrix(old, new)
    left_matrix = _transition_matrix(old, new, x0=0, x1=WIDTH // 2)
    right_matrix = _transition_matrix(old, new, x0=WIDTH // 2, x1=WIDTH)
    unchanged = sum(global_matrix[index][index] for index in range(len(PHYSICAL_CODE_ORDER)))
    return {
        "row_old_codes": list(PHYSICAL_CODE_ORDER),
        "column_new_codes": list(PHYSICAL_CODE_ORDER),
        "global": global_matrix,
        "left": left_matrix,
        "right": right_matrix,
        "unchanged_pixels": unchanged,
        "changed_pixels": WIDTH * HEIGHT - unchanged,
        "changed_ratio": (WIDTH * HEIGHT - unchanged) / (WIDTH * HEIGHT),
    }


def _strict_preview(codes: bytes) -> bytes:
    colours = {entry.code: entry.preview_rgb for entry in reference_palette().entries}
    rgb = bytearray(len(codes) * 3)
    for index, code in enumerate(codes):
        rgb[index * 3 : index * 3 + 3] = bytes(colours[code])
    return encode_rgb_png(WIDTH, HEIGHT, rgb)


def _model_preview(codes: bytes) -> tuple[bytes, Mapping[str, Any]]:
    palette = reference_palette()
    model = OverlapObservationModel.gaussian_simulation()
    linear = model.render_linear_rgb(codes, WIDTH, HEIGHT, palette=palette)
    rgb = bytearray(WIDTH * HEIGHT * 3)
    for index, value in enumerate(linear):
        channel = linear_channel_to_srgb(min(1.0, max(0.0, float(value))))
        rgb[index] = min(255, max(0, int(math.floor(channel * 255.0 + 0.5))))
    return encode_rgb_png(WIDTH, HEIGHT, rgb), model.metadata()


def _validate_fixed_inputs() -> tuple[Mapping[str, Any], bytes, bytes, bytes, Mapping[str, Any], bytes]:
    """Deep-validate and rebind the frozen source and true-screen prior."""

    try:
        base_manifest = blue_noise.validate_candidate_directory(BASELINE_DIR)
    except Exception as error:
        raise ClusteredCandidateError(f"frozen blue-noise baseline failed deep validation: {error}") from error
    base_manifest_bytes = (BASELINE_DIR / "manifest.json").read_bytes()
    base_frame = (BASELINE_DIR / "frame.bin").read_bytes()
    source_png = (BASELINE_DIR / "source.png").read_bytes()
    mapped_png = (BASELINE_DIR / "mapped.png").read_bytes()
    if (
        _sha256(base_manifest_bytes) != BASELINE_MANIFEST_FILE_SHA256
        or base_manifest.get("manifest_integrity", {}).get("canonical_sha256")
        != BASELINE_MANIFEST_CANONICAL_SHA256
        or _sha256(base_frame) != BASELINE_FRAME_SHA256
        or f"0x{fnv1a(base_frame):08X}" != BASELINE_FRAME_FNV1A
        or _sha256(unpack_pixels(base_frame)) != BASELINE_CODES_SHA256
        or _sha256(source_png) != BASELINE_SOURCE_SHA256
        or _sha256(mapped_png) != BASELINE_MAPPED_SHA256
    ):
        raise ClusteredCandidateError("frozen blue-noise baseline identity differs from the contract")
    if (
        base_manifest.get("options", {}).get("value", {}).get("algorithm")
        != "area-weighted-blue-noise"
        or base_manifest.get("options", {}).get("value", {}).get("seed") != 1_296_445_751
        or base_manifest.get("transport", {}).get("mode") != "offline"
    ):
        raise ClusteredCandidateError("frozen baseline algorithm or offline provenance differs")

    try:
        prior_manifest = low_spatial.validate_diagnostic_directory(PRIOR_DIR)
    except Exception as error:
        raise ClusteredCandidateError(f"true-screen prior failed deep validation: {error}") from error
    prior_manifest_bytes = (PRIOR_DIR / "manifest.json").read_bytes()
    prior_frame = (PRIOR_DIR / "frame.bin").read_bytes()
    if (
        _sha256(prior_manifest_bytes) != PRIOR_MANIFEST_FILE_SHA256
        or prior_manifest.get("manifest_integrity", {}).get("canonical_sha256")
        != PRIOR_MANIFEST_CANONICAL_SHA256
        or _sha256(prior_frame) != PRIOR_FRAME_SHA256
        or f"0x{fnv1a(prior_frame):08X}" != PRIOR_FRAME_FNV1A
        or _sha256(unpack_pixels(prior_frame)) != PRIOR_CODES_SHA256
    ):
        raise ClusteredCandidateError("true-screen prior identity differs from the frozen contract")
    return base_manifest, base_frame, source_png, mapped_png, prior_manifest, prior_frame


def _controller_records(frame: bytes) -> list[dict[str, Any]]:
    records = []
    for number, mapping in enumerate(CONTROLLER_MAPPINGS, start=1):
        stream = controller_stream(frame, mapping)
        records.append(
            {
                "controller": f"CS{number}",
                "mapping": _mapping_record(mapping),
                "dtm_bytes": CONTROLLER_FRAME_BYTES,
                "dtm_sha256": _sha256(stream),
                "dtm_fnv1a": f"0x{fnv1a(stream):08X}",
            }
        )
    return records


def _file_record(filename: str, payload: bytes, semantics: str) -> dict[str, Any]:
    return {
        "file": filename,
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "width": WIDTH,
        "height": HEIGHT,
        "semantics": semantics,
    }


def build_clustered_artifacts() -> ClusteredArtifacts:
    """Deep-bind inputs and build the sole 32x32 clustered candidate."""

    base_manifest, base_frame, source_png, mapped_png, prior_manifest, prior_frame = (
        _validate_fixed_inputs()
    )
    base_codes = unpack_pixels(base_frame)
    prior_codes = unpack_pixels(prior_frame)
    codes = cluster_codes(base_codes, prior_codes)
    tile_histograms = _tile_histograms(base_codes, TILE_SIDE)
    tile_prior_transitions = _tile_prior_transitions(prior_codes, base_codes, TILE_SIDE)
    counterfactual_codes = _cluster_codes_for_analysis(
        base_codes, prior_codes, tile_side=COUNTERFACTUAL_TILE_SIDE
    )
    frame = pack_pixels(codes)
    validate_frame(frame)
    if (
        _sha256(codes) != EXPECTED_CODES_SHA256
        or _sha256(frame) != EXPECTED_FRAME_SHA256
        or f"0x{fnv1a(frame):08X}" != EXPECTED_FRAME_FNV1A
    ):
        raise ClusteredCandidateError("clustered output identity differs from the frozen contract")
    strict_png = _strict_preview(codes)
    model_png, observation_model = _model_preview(codes)

    candidate_metrics = spatial_metrics(codes)
    base_metrics = spatial_metrics(base_codes)
    prior_metrics = spatial_metrics(prior_codes)
    failed_metrics = _compact_reference_metrics(FAILED_METRIC_COUNTS)
    counterfactual_metrics = spatial_metrics(counterfactual_codes)
    counts_global = _counts(codes)
    counts_left = _counts(codes, x0=0, x1=WIDTH // 2)
    counts_right = _counts(codes, x0=WIDTH // 2, x1=WIDTH)
    if counts_global != _counts(base_codes):
        raise ClusteredCandidateError("global code counts changed from the baseline")

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "classification": {
            "experimental": True,
            "visual_risk_reduction_experiment": True,
            "simulation_only": True,
            "formal": False,
            "hardware_qualified": False,
            "hardware_tested": False,
            "upload_authorized": False,
        },
        "algorithm": {
            "id": ALGORITHM_ID,
            "deterministic": True,
            "tile_side": TILE_SIDE,
            "grid_columns": math.ceil(WIDTH / TILE_SIDE),
            "grid_rows": math.ceil(HEIGHT / TILE_SIDE),
            "bottom_residual_height": HEIGHT % TILE_SIDE,
            "path": "standard order-5 Hilbert d2xy; residual tiles filter out-of-bounds points without reordering",
            "code_block_order": list(CLUSTER_CODE_ORDER),
            "tile_histogram_contract": "each output tile has exactly the baseline frame's six per-code counts",
            "tile_histogram_records": tile_histograms,
            "tile_histogram_canonical_sha256": _sha256(_canonical_json(tile_histograms)),
            "tile_prior_transition_contract": "within every tile and every fixed prior code, output new-code counts exactly equal the baseline blue-noise counts",
            "tile_prior_transition_canonical_sha256": _sha256(
                _canonical_json(tile_prior_transitions)
            ),
            "prior_code_group_order": list(PHYSICAL_CODE_ORDER),
            "spatial_position_preserved_within_tile": False,
        },
        "evidence": {
            "baseline": {
                "artifact_id": BASELINE_DIR.name,
                "deep_validator": "tools.g1_s1_panel_candidate.validate_candidate_directory",
                "manifest_file_sha256": BASELINE_MANIFEST_FILE_SHA256,
                "manifest_canonical_sha256": BASELINE_MANIFEST_CANONICAL_SHA256,
                "frame_sha256": BASELINE_FRAME_SHA256,
                "frame_fnv1a": BASELINE_FRAME_FNV1A,
                "codes_sha256": BASELINE_CODES_SHA256,
                "source_png_sha256": BASELINE_SOURCE_SHA256,
                "mapped_png_sha256": BASELINE_MAPPED_SHA256,
                "algorithm": base_manifest["options"]["value"]["algorithm"],
                "seed": base_manifest["options"]["value"]["seed"],
            },
            "true_screen_prior": {
                "artifact_id": PRIOR_DIR.name,
                "deep_validator": "tools.g1_s1_low_spatial_diagnostic.validate_diagnostic_directory",
                "manifest_file_sha256": PRIOR_MANIFEST_FILE_SHA256,
                "manifest_canonical_sha256": PRIOR_MANIFEST_CANONICAL_SHA256,
                "frame_sha256": PRIOR_FRAME_SHA256,
                "frame_fnv1a": PRIOR_FRAME_FNV1A,
                "codes_sha256": PRIOR_CODES_SHA256,
                "hardware_state_claim": "caller-supplied current prior; this offline tool performs no device verification",
            },
            "failed_ordered_reference": dict(FAILED_REFERENCE),
        },
        "output": {
            "frame": {
                "file": "frame.bin",
                "encoding": "canonical-row-major-two-4bit-codes-per-byte-even-x-high-nibble",
                "bytes": FRAME_BYTES,
                "sha256": _sha256(frame),
                "fnv1a": f"0x{fnv1a(frame):08X}",
                "codes_sha256": _sha256(codes),
            },
            "controllers": _controller_records(frame),
            "counts": {
                "code_order": list(PHYSICAL_CODE_ORDER),
                "global": counts_global,
                "left": counts_left,
                "right": counts_right,
                "left_minus_right": [left - right for left, right in zip(counts_left, counts_right)],
            },
            "spatial_metrics": candidate_metrics,
            "transition_from_true_screen_prior": _transition_record(prior_codes, codes),
        },
        "comparisons": {
            "baseline_blue_noise": {
                "metrics": base_metrics,
                "candidate_minus_reference": _metric_delta(candidate_metrics, base_metrics),
            },
            "failed_ordered": {
                "metrics": failed_metrics,
                "candidate_minus_reference": _metric_delta(candidate_metrics, failed_metrics),
            },
            "passed_low_spatial": {
                "metrics": prior_metrics,
                "candidate_minus_reference": _metric_delta(candidate_metrics, prior_metrics),
            },
            "tile16_counterfactual_only": {
                "generated_as_hardware_candidate": False,
                "reason": "reported only to assess whether the fixed 32px tile may look over-blocked",
                "tile_side": COUNTERFACTUAL_TILE_SIDE,
                "spatial_metrics": counterfactual_metrics,
            },
        },
        "previews": {
            "source": _file_record(
                "source.png", source_png, "byte-identical frozen source monitor rendering"
            ),
            "mapped": _file_record(
                "mapped.png", mapped_png, "byte-identical frozen continuous mapped target"
            ),
            "strict_final": _file_record(
                "strict-final.png", strict_png, "strict physical six-code clustered rendering"
            ),
            "model": _file_record(
                "model.png", model_png, "uncalibrated Gaussian overlap monitor simulation"
            ),
        },
        "observation_model": observation_model,
        "limitations": [
            "This is a visual-risk-reduction experiment, not a formal or hardware-qualified result.",
            "Per-tile histograms and fixed-prior transition counts are preserved, but source pixel positions, edges, and text semantics inside each tile are rearranged.",
            "The candidate exactly preserves the blue-noise baseline's global, logical-half, and per-tile-by-prior-code transition counts from the fixed current prior, while rearranging transition locations and spatial frequency.",
            "Relative to the failed ordered reference, other variables remain different; one display result cannot isolate every causal factor.",
            "Monitor previews cannot reproduce reflective colour, illumination, waveform history, ghosting, temperature, or panel variation.",
            "The 32px tile grid and fixed code order can create visible blocking; the 16px result is metrics-only and is not emitted as a second candidate.",
        ],
        "transport": {
            "mode": "offline",
            "endpoint": None,
            "method": None,
            "device_io_performed": False,
            "network_io_performed": False,
            "refresh_runner_implemented": False,
            "hardware_tested": False,
            "upload_authorized": False,
        },
    }
    del prior_manifest  # its fixed identity is already recorded above
    unsigned = _canonical_json(manifest)
    manifest["manifest_integrity"] = {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": MANIFEST_HASH_SCOPE,
    }
    manifest_bytes = _canonical_json(manifest)
    return ClusteredArtifacts(
        codes=codes,
        frame=frame,
        source_png=source_png,
        mapped_png=mapped_png,
        strict_final_png=strict_png,
        model_png=model_png,
        manifest=manifest,
        manifest_bytes=manifest_bytes,
    )


def _reject_symlink_ancestors(path: Path, *, label: str) -> None:
    current = path.absolute()
    while True:
        if os.path.lexists(current) and current.is_symlink():
            raise ClusteredCandidateError(f"{label} must not traverse a symlink")
        parent = current.parent
        if parent == current:
            return
        current = parent


def _safe_directory(path: Path, *, label: str, must_exist: bool) -> Path:
    try:
        require_local_regular_path_syntax(path, label=label)
    except LocalPathSafetyError as error:
        raise ClusteredCandidateError(str(error)) from error
    _reject_symlink_ancestors(path if must_exist else path.parent, label=label)
    if must_exist:
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise ClusteredCandidateError(f"{label} does not exist: {error}") from error
        if path.is_symlink() or not resolved.is_dir():
            raise ClusteredCandidateError(f"{label} must be a real local directory")
        return resolved
    if os.path.lexists(path):
        raise ClusteredCandidateError(f"{label} already exists; refusing overwrite")
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as error:
        raise ClusteredCandidateError(f"{label} parent does not exist: {error}") from error
    if not parent.is_dir() or parent.is_symlink():
        raise ClusteredCandidateError(f"{label} parent must be a real local directory")
    return parent / path.name


def _load_json_strict(payload: bytes) -> Any:
    def reject_constant(value: str) -> None:
        raise ClusteredCandidateError(f"manifest contains forbidden JSON constant {value}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ClusteredCandidateError(f"manifest contains duplicate key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except ClusteredCandidateError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ClusteredCandidateError(f"manifest is not strict UTF-8 JSON: {error}") from error


def validate_clustered_directory(directory: Path) -> Mapping[str, Any]:
    """Deeply reconstruct every output byte and reject non-contract files."""

    resolved = _safe_directory(directory, label="clustered directory", must_exist=True)
    entries = tuple(resolved.iterdir())
    if any(entry.is_symlink() for entry in entries):
        raise ClusteredCandidateError("clustered directory must not contain symlinks")
    actual_files = {entry.name for entry in entries if entry.is_file()}
    if actual_files != REQUIRED_FILES or any(not entry.is_file() for entry in entries):
        raise ClusteredCandidateError(
            f"clustered directory file set must be exactly {sorted(REQUIRED_FILES)}"
        )
    manifest_bytes = (resolved / "manifest.json").read_bytes()
    manifest = _load_json_strict(manifest_bytes)
    if not isinstance(manifest, dict) or manifest_bytes != _canonical_json(manifest):
        raise ClusteredCandidateError("clustered manifest is not canonical JSON")
    integrity = manifest.get("manifest_integrity")
    unsigned = dict(manifest)
    unsigned.pop("manifest_integrity", None)
    if integrity != {
        "canonical_sha256": _sha256(_canonical_json(unsigned)),
        "canonical_sha256_scope": MANIFEST_HASH_SCOPE,
    }:
        raise ClusteredCandidateError("clustered manifest canonical integrity is invalid")
    expected = build_clustered_artifacts()
    if manifest != expected.manifest or manifest_bytes != expected.manifest_bytes:
        raise ClusteredCandidateError("clustered manifest does not match deep regeneration")
    for filename, expected_payload in expected.files().items():
        payload = (resolved / filename).read_bytes()
        if payload != expected_payload:
            raise ClusteredCandidateError(
                f"clustered file {filename} does not match deep regeneration"
            )
    return manifest


def write_clustered_directory(output_dir: Path) -> Mapping[str, Any]:
    """Create one new offline bundle atomically and refuse all overwrites."""

    destination = _safe_directory(output_dir, label="output directory", must_exist=False)
    artifacts = build_clustered_artifacts()
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
        if isinstance(error, ClusteredCandidateError):
            raise
        raise ClusteredCandidateError(f"could not create clustered bundle: {error}") from error
    return validate_clustered_directory(destination)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output-dir", type=Path, help="new local clustered bundle directory")
    mode.add_argument("--validate-dir", type=Path, help="existing local clustered bundle directory")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.output_dir is not None:
            manifest = write_clustered_directory(args.output_dir)
            mode = "generated"
            directory = args.output_dir
        else:
            manifest = validate_clustered_directory(args.validate_dir)
            mode = "validated"
            directory = args.validate_dir
    except (ClusteredCandidateError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    output = manifest["output"]["frame"]
    print(
        _canonical_json(
            {
                "ok": True,
                "mode": mode,
                "directory": os.fspath(directory),
                "kind": manifest["kind"],
                "frame_sha256": output["sha256"],
                "frame_fnv1a": output["fnv1a"],
                "device_io_performed": False,
                "upload_authorized": False,
            }
        ).decode("utf-8")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
