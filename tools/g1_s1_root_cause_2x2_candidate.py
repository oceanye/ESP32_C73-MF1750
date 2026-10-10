#!/usr/bin/env python3
"""Build or deeply validate the frozen offline G1/S1 2x2 root-cause audit.

The crossed factors are controller-internal spatial frequency (high/low) and
left/right pigment-transition load (balanced/unbalanced).  All four variants
exactly preserve the failed ordered candidate's global six-code histogram and
the MAP-prior-to-final global 6x6 transition matrix.  This module has no
network, device, ingress, upload, refresh, or runner surface.
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
from tools import g1_s1_clustered_quality_candidate as clustered  # noqa: E402
from tools import g1_s1_low_spatial_diagnostic as low_spatial  # noqa: E402
from tools import g1_s1_macro4_quality_candidate as macro4  # noqa: E402
from tools import g1_s1_panel_candidate as panel_candidate  # noqa: E402


SCHEMA_VERSION = 1
MANIFEST_KIND = "mf1750-g1-s1-root-cause-2x2-offline-audit"
MANIFEST_HASH_SCOPE = (
    "entire manifest excluding manifest_integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
ALGORITHM_ID = "map-transition-crossed-spatial-half-load-v1"
HIGH_PHASE_SIDE = 5
PHYSICAL_CODE_ORDER = (0, 1, 2, 3, 5, 6)
ALLOCATION_BLOCK_ORDER = (3, 2, 5, 6, 1, 0)
CONTROLLER_MAPPINGS = (ControllerMapping(0), ControllerMapping(1))
VARIANT_NAMES = (
    "high-unbalanced",
    "high-balanced",
    "low-unbalanced",
    "low-balanced",
)
REQUIRED_FILES = frozenset(
    {
        "manifest.json",
        *(f"{name}.frame.bin" for name in VARIANT_NAMES),
        *(f"{name}.strict-final.png" for name in VARIANT_NAMES),
    }
)

HARDWARE_DIR = REPO_ROOT / ".test-output" / "hardware"
FAILED_DIR = HARDWARE_DIR / "G1S1_AWORDERED_20260806_204800"
LOW_DIR = HARDWARE_DIR / "G1S1_LOW_SPATIAL_TRANSITION_MATCHED_20260806_231430"
CLUSTERED_DIR = HARDWARE_DIR / "G1S1_QUALITY_CLUSTERED_TRANSITION_MATCHED_OFFLINE_20260806"
MACRO4_DIR = HARDWARE_DIR / "G1S1_QUALITY_MACRO4_BLUE_NOISE_OFFLINE_20260807"

INPUT_IDENTITIES = {
    "failed_ordered": {
        "artifact_id": FAILED_DIR.name,
        "manifest_file_sha256": "88702d79b71ff1c901bd71f2315c3c0e7aeae8c31945f322d6be5f13c8ce272a",
        "manifest_canonical_sha256": "523c008465037e1cd4db6d2c4de61d170293f72712c854fd4a1d68356c7c695f",
        "frame_sha256": "28ce21501a93c667b81bf474e9811100c8d5ebb7116359e82ee081cebde07e25",
        "codes_sha256": "8e662425d568a942ca5f4cac806d215edb58cebbc526826bdaafde4f7c66a097",
    },
    "low_spatial": {
        "artifact_id": LOW_DIR.name,
        "manifest_file_sha256": "07146b9254414e1454d9143f4af5706a8c5f69eb9125dce341206bbc441afb4d",
        "manifest_canonical_sha256": "594d31031b4413ac83c376854dcd35f522e1ae769613908f3fa7289d5fece91d",
        "frame_sha256": "ba373d138c525fd7e59cc6c4ae6037191fa41388507b347da9f6f8bdece9fc65",
        "codes_sha256": "caafec835cc5ef8a91767d71293100b6763442d337737fc0594e40ff9f8edbfa",
    },
    "clustered": {
        "artifact_id": CLUSTERED_DIR.name,
        "manifest_file_sha256": "2d705b418a815efae41dda762c3d23ff9d2027c7a53856a3d16c89ffb073e8d8",
        "manifest_canonical_sha256": "f8db6634e35cfa850f3592acfbb100248d6312799bc3c86fedb10bc550cbbe62",
        "frame_sha256": "eabb228afd79fc09e2b2e613594f3d06e9d1d608ac2c1b05ee6a3cf38b8f7b9a",
        "codes_sha256": "8c277487749a326c56ef7627541e51f58bca6b5f3f34937a8b93b46f188d7ecd",
    },
    "macro4": {
        "artifact_id": MACRO4_DIR.name,
        "manifest_file_sha256": "7c6f8569eb8a1cba9de144b7c660e79b932c1abbcbb5d6aa334ac694056420ad",
        "manifest_canonical_sha256": "85abb1a948079eba89b7ca854c4b6b867e3b5f6716f5819c22765b610c2e900b",
        "frame_sha256": "1f509baa655d84fe13da65441f22929f32a43a0ac66d45d753f7a3d394a2281d",
        "codes_sha256": "b772e30ba2fa2f500b02ffbe62605ea7954d805c890c411b2eb1c95809090688",
    },
}

MAP_FRAME_SHA256 = "1deedf924e40c676c2080fec08dfe5da10a8c1bb53b699ec4a85b0b6101b5c36"
MAP_CODES_SHA256 = "26c031d2d5811ccd2d3e2269af4eaafea75a4642e438af1114b8c9fcc2c60126"

GLOBAL_TRANSITION_MATRIX = (
    (20892, 12495, 1676, 1779, 1309, 1385),
    (173762, 87874, 37055, 47055, 41835, 38227),
    (6596, 12366, 3694, 1698, 3549, 1377),
    (17564, 14467, 2444, 7507, 1324, 3766),
    (19743, 9870, 1271, 5664, 4805, 2839),
    (8026, 7521, 3913, 3516, 1822, 3714),
)
UNBALANCED_LEFT_MATRIX = (
    (12714, 5675, 1609, 1109, 7, 118),
    (93351, 48790, 33475, 30820, 2026, 2594),
    (3062, 7829, 3066, 678, 0, 5),
    (12985, 6181, 2086, 6808, 461, 1031),
    (8596, 6013, 1155, 692, 0, 8),
    (3075, 4493, 3899, 2787, 0, 2),
)
UNBALANCED_RIGHT_MATRIX = tuple(
    tuple(GLOBAL_TRANSITION_MATRIX[row][column] - UNBALANCED_LEFT_MATRIX[row][column]
          for column in range(6))
    for row in range(6)
)
BALANCED_LEFT_MATRIX = low_spatial.LEFT_TRANSITION_MATRIX
BALANCED_RIGHT_MATRIX = low_spatial.RIGHT_TRANSITION_MATRIX
GLOBAL_COUNTS = (246583, 144593, 50053, 67219, 54644, 51308)
UNBALANCED_LEFT_COUNTS = (133783, 78981, 45290, 42894, 2494, 3758)
UNBALANCED_RIGHT_COUNTS = (112800, 65612, 4763, 24325, 52150, 47550)
BALANCED_LEFT_COUNTS = (123292, 72296, 25027, 33609, 27322, 25654)
BALANCED_RIGHT_COUNTS = (123291, 72297, 25026, 33610, 27322, 25654)
EXPECTED_CHANGED_PIXELS = 485_914

EXPECTED_VARIANTS = {
    "high-unbalanced": {
        "codes_sha256": "26c3a6b5eb045bec94e561450a73ea40556e11f88d4158c0bc017155058d13ed",
        "frame_sha256": "87acba7df1fd4e7db6838cc2ccadb301e5946b86891540abf45fd33e3e8803b6",
        "frame_fnv1a": "0x502F593E",
        "strict_sha256": "eb527c4b69421bb2e137430779273b63eb0079e7667304d13ffb9795ca2e08b1",
        "controller_internal_edges": (294038, 336288),
        "controller_seam": 281,
        "total_edges": 630607,
        "boundary_pixels": 593599,
        "controllers": (
            ("e67b7b9bcbdde0cdff5a9b36731b7647994e1679708fd93f42e8d74d06d5d09c", "0xABC39491"),
            ("dd6c6aa7bb5f25ae6711f8d7f4a36c4be00ab0fb94eb4581cecc631ece8a6d86", "0x962BF0EA"),
        ),
    },
    "high-balanced": {
        "codes_sha256": "c95c2addaa04529ab6ddafbc65c8dbd5c0de3fc49c3a76e12aaade1976596176",
        "frame_sha256": "a861d58e1dd9801e42340c69cd1ffb9684a2bbd9b462e298377fd88acc9efcb2",
        "frame_fnv1a": "0x0140A572",
        "strict_sha256": "e377ed59559ba28f6327ea434fcd01fcf52c1b40cc994c49cb59b08382a69710",
        "controller_internal_edges": (306065, 306246),
        "controller_seam": 330,
        "total_edges": 612641,
        "boundary_pixels": 601120,
        "controllers": (
            ("73e1e63846c48e4588388ddb24a543ae216e636a0d9f02b8050aa3560c85bc0e", "0x5D533EBF"),
            ("4bc115adb90edbcb79c73b3b80da3fbf376f86bd86187c05baeaf02a75c6b8cb", "0x3BACEAEC"),
        ),
    },
    "low-unbalanced": {
        "codes_sha256": "c0a1e8ccd4ea248c75e93dc0a4e54e4403c7836e2ca829de89ab9a963f150b44",
        "frame_sha256": "6c8b0e36866eb65c32ed032752a8ec05a941261c2315bcd53ea2ceefd01e9f81",
        "frame_fnv1a": "0x42199150",
        "strict_sha256": "cbc3be99b3c67398002a79413f90d83984552ce8bc6a3011437d51aa9efd0992",
        "controller_internal_edges": (15102, 15479),
        "controller_seam": 484,
        "total_edges": 31065,
        "boundary_pixels": 53934,
        "controllers": (
            ("e49ae04d1d48664a467745c0605fa16c750ca1d241cec9d27771dea0ffe13011", "0x0F64E7E9"),
            ("9aea45ad6be1dfd8418aba0804f4b2065376adb27c10baa996e3e4aa128e4258", "0x4C523214"),
        ),
    },
    "low-balanced": {
        "codes_sha256": "caafec835cc5ef8a91767d71293100b6763442d337737fc0594e40ff9f8edbfa",
        "frame_sha256": "ba373d138c525fd7e59cc6c4ae6037191fa41388507b347da9f6f8bdece9fc65",
        "frame_fnv1a": "0xA9641618",
        "strict_sha256": "39c10018dda091bb5af0ebad26b006c1c5e7c3374096de086e7cc8debcc42205",
        "controller_internal_edges": (14786, 14319),
        "controller_seam": 460,
        "total_edges": 29565,
        "boundary_pixels": 52072,
        "controllers": (
            ("c85a03621501c8bb0c535467a1581ab451f5bb0fc50fc4227c31e576d23d6070", "0xCB085C03"),
            ("bf25594c886c2046512eecf24795f8c2a5dacf1d9c565501658a6e6ea9889bd7", "0x9ABD749A"),
        ),
    },
}

EXPECTED_MANIFEST_FILE_SHA256 = "b25efedae7d3ff5947c7b5c546879b6fbce44f67ae59d410581b4d745e8db055"
EXPECTED_MANIFEST_CANONICAL_SHA256 = "7e0be9f7473b69ee0f612fed21e3ede955fcd0f28a7fe044fb5469a3165315f1"


class FactorialCandidateError(RuntimeError):
    """Raised when the offline crossed-control contract cannot be proven."""


@dataclass(frozen=True)
class VariantArtifacts:
    codes: bytes
    frame: bytes
    strict_png: bytes


@dataclass(frozen=True)
class FactorialArtifacts:
    variants: Mapping[str, VariantArtifacts]
    manifest: Mapping[str, Any]
    manifest_bytes: bytes

    def files(self) -> dict[str, bytes]:
        result = {"manifest.json": self.manifest_bytes}
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
        raise FactorialCandidateError(f"canonical JSON encoding failed: {error}") from error


def _matrix_record(matrix: Sequence[Sequence[int]]) -> list[list[int]]:
    return [list(row) for row in matrix]


def _matrix_columns(matrix: Sequence[Sequence[int]]) -> tuple[int, ...]:
    return tuple(sum(matrix[row][column] for row in range(6)) for column in range(6))


def _matrix_rows(matrix: Sequence[Sequence[int]]) -> tuple[int, ...]:
    return tuple(sum(row) for row in matrix)


def _half_bytes(codes: bytes, side: int) -> bytes:
    x0 = side * (WIDTH // 2)
    return b"".join(codes[y * WIDTH + x0 : y * WIDTH + x0 + WIDTH // 2] for y in range(HEIGHT))


def _counts(codes: bytes) -> tuple[int, ...]:
    return tuple(codes.count(code) for code in PHYSICAL_CODE_ORDER)


def _mapping_record(mapping: ControllerMapping) -> dict[str, int | bool]:
    return {
        "source_half": mapping.source_half,
        "flip_x": mapping.flip_x,
        "flip_y": mapping.flip_y,
        "nibble_swap": mapping.nibble_swap,
    }


def validate_algebraic_contract() -> None:
    """Prove the exact matrix and histogram constraints without raster generation."""

    prior_left = low_spatial.OLD_LEFT_CAPACITIES
    prior_right = low_spatial.OLD_RIGHT_CAPACITIES
    if _matrix_rows(GLOBAL_TRANSITION_MATRIX) != tuple(
        left + right for left, right in zip(prior_left, prior_right)
    ):
        raise FactorialCandidateError("global transition rows do not match the MAP prior")
    if _matrix_columns(GLOBAL_TRANSITION_MATRIX) != GLOBAL_COUNTS:
        raise FactorialCandidateError("global transition columns do not match frozen counts")
    splits = (
        (UNBALANCED_LEFT_MATRIX, UNBALANCED_RIGHT_MATRIX,
         UNBALANCED_LEFT_COUNTS, UNBALANCED_RIGHT_COUNTS),
        (BALANCED_LEFT_MATRIX, BALANCED_RIGHT_MATRIX,
         BALANCED_LEFT_COUNTS, BALANCED_RIGHT_COUNTS),
    )
    for left, right, left_counts, right_counts in splits:
        if _matrix_rows(left) != prior_left or _matrix_rows(right) != prior_right:
            raise FactorialCandidateError("half transition rows do not match prior capacities")
        if _matrix_columns(left) != left_counts or _matrix_columns(right) != right_counts:
            raise FactorialCandidateError("half transition columns do not match half counts")
        if any(
            left[row][column] + right[row][column] != GLOBAL_TRANSITION_MATRIX[row][column]
            for row in range(6) for column in range(6)
        ):
            raise FactorialCandidateError("half transition matrices do not reconstruct global matrix")
    if max(abs(a - b) for a, b in zip(BALANCED_LEFT_COUNTS, BALANCED_RIGHT_COUNTS)) != 1:
        raise FactorialCandidateError("balanced split exceeds the exact one-pixel parity bound")
    if sum(abs(a - b) for a, b in zip(UNBALANCED_LEFT_COUNTS, UNBALANCED_RIGHT_COUNTS)) != 186_896:
        raise FactorialCandidateError("unbalanced half-load identity changed")


def _validate_one_input(
    directory: Path,
    identity: Mapping[str, str],
    validator: Any,
) -> Mapping[str, Any]:
    try:
        manifest = validator(directory)
    except Exception as error:
        raise FactorialCandidateError(
            f"audited input {identity['artifact_id']} failed deep validation: {error}"
        ) from error
    manifest_bytes = (directory / "manifest.json").read_bytes()
    frame = (directory / "frame.bin").read_bytes()
    codes = unpack_pixels(frame)
    if (
        _sha256(manifest_bytes) != identity["manifest_file_sha256"]
        or manifest.get("manifest_integrity", {}).get("canonical_sha256")
        != identity["manifest_canonical_sha256"]
        or _sha256(frame) != identity["frame_sha256"]
        or _sha256(codes) != identity["codes_sha256"]
    ):
        raise FactorialCandidateError(
            f"audited input {identity['artifact_id']} identity differs from the frozen contract"
        )
    return manifest


def audit_fixed_inputs() -> tuple[bytes, Mapping[str, Mapping[str, Any]]]:
    """Deep-validate all relevant existing candidates and return the MAP prior."""

    validate_algebraic_contract()
    validators = {
        "failed_ordered": panel_candidate.validate_candidate_directory,
        "low_spatial": low_spatial.validate_diagnostic_directory,
        "clustered": clustered.validate_clustered_directory,
        "macro4": macro4.validate_macro4_directory,
    }
    directories = {
        "failed_ordered": FAILED_DIR,
        "low_spatial": LOW_DIR,
        "clustered": CLUSTERED_DIR,
        "macro4": MACRO4_DIR,
    }
    manifests = {
        name: _validate_one_input(directories[name], INPUT_IDENTITIES[name], validators[name])
        for name in validators
    }
    prior_codes, low_codes = low_spatial.generate_diagnostic_codes()
    prior_frame = pack_pixels(prior_codes)
    if _sha256(prior_frame) != MAP_FRAME_SHA256 or _sha256(prior_codes) != MAP_CODES_SHA256:
        raise FactorialCandidateError("MAP prior identity differs from the frozen contract")
    if _sha256(low_codes) != INPUT_IDENTITIES["low_spatial"]["codes_sha256"]:
        raise FactorialCandidateError("low-spatial reconstruction differs from its audited bundle")
    failed_codes = unpack_pixels((FAILED_DIR / "frame.bin").read_bytes())
    if (
        low_spatial._transition_matrix(prior_codes, failed_codes) != GLOBAL_TRANSITION_MATRIX
        or low_spatial._transition_matrix(prior_codes, failed_codes, x0=0, x1=WIDTH // 2)
        != UNBALANCED_LEFT_MATRIX
        or low_spatial._transition_matrix(prior_codes, failed_codes, x0=WIDTH // 2, x1=WIDTH)
        != UNBALANCED_RIGHT_MATRIX
    ):
        raise FactorialCandidateError("failed reference transition matrices changed")
    return prior_codes, manifests


def _position_order(positions: list[int], *, side: int, spatial: str) -> list[int]:
    if spatial == "low":
        return positions
    if spatial != "high":
        raise FactorialCandidateError("spatial factor must be high or low")
    x0 = side * (WIDTH // 2)
    return sorted(
        positions,
        key=lambda index: (
            ((index // WIDTH) % HIGH_PHASE_SIDE) * HIGH_PHASE_SIDE
            + ((index % WIDTH - x0) % HIGH_PHASE_SIDE),
            (index // WIDTH) // HIGH_PHASE_SIDE,
            (index % WIDTH - x0) // HIGH_PHASE_SIDE,
            index,
        ),
    )


def generate_variant_codes(prior_codes: bytes, *, spatial: str, load: str) -> bytes:
    """Generate one cell while preserving its exact frozen half matrices."""

    if len(prior_codes) != WIDTH * HEIGHT or set(prior_codes) - set(PHYSICAL_CODE_ORDER):
        raise FactorialCandidateError("prior codes violate the fixed six-code raster contract")
    if load == "balanced":
        matrices = (BALANCED_LEFT_MATRIX, BALANCED_RIGHT_MATRIX)
    elif load == "unbalanced":
        matrices = (UNBALANCED_LEFT_MATRIX, UNBALANCED_RIGHT_MATRIX)
    else:
        raise FactorialCandidateError("load factor must be balanced or unbalanced")
    ranks = {code: rank for rank, code in enumerate(PHYSICAL_CODE_ORDER)}
    output = bytearray(WIDTH * HEIGHT)
    for side, matrix in enumerate(matrices):
        x0 = side * (WIDTH // 2)
        x1 = x0 + WIDTH // 2
        positions = {code: [] for code in PHYSICAL_CODE_ORDER}
        for y_value in range(HEIGHT):
            row = y_value * WIDTH
            for x_value in range(x0, x1):
                position = row + x_value
                positions[prior_codes[position]].append(position)
        for old_rank, old_code in enumerate(PHYSICAL_CODE_ORDER):
            ordered = _position_order(positions[old_code], side=side, spatial=spatial)
            offset = 0
            for new_code in ALLOCATION_BLOCK_ORDER:
                count = matrix[old_rank][ranks[new_code]]
                end = offset + count
                for position in ordered[offset:end]:
                    output[position] = new_code
                offset = end
            if offset != len(ordered):
                raise FactorialCandidateError("allocation did not consume an old-code mask")
    codes = bytes(output)
    expected = matrices
    if (
        low_spatial._transition_matrix(prior_codes, codes) != GLOBAL_TRANSITION_MATRIX
        or low_spatial._transition_matrix(prior_codes, codes, x0=0, x1=WIDTH // 2) != expected[0]
        or low_spatial._transition_matrix(prior_codes, codes, x0=WIDTH // 2, x1=WIDTH) != expected[1]
    ):
        raise FactorialCandidateError("generated variant lost an exact transition invariant")
    return codes


def _controller_records(frame: bytes, expected: Sequence[Sequence[str]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for number, (mapping, identity) in enumerate(zip(CONTROLLER_MAPPINGS, expected), start=1):
        stream = controller_stream(frame, mapping)
        actual = (_sha256(stream), f"0x{fnv1a(stream):08X}")
        if len(stream) != CONTROLLER_FRAME_BYTES or actual != tuple(identity):
            raise FactorialCandidateError(f"CS{number} DTM identity changed")
        records.append(
            {
                "controller": f"CS{number}",
                "mapping": _mapping_record(mapping),
                "dtm_bytes": len(stream),
                "dtm_sha256": actual[0],
                "dtm_fnv1a": actual[1],
            }
        )
    return records


def _variant_record(
    name: str,
    prior_codes: bytes,
    artifacts: VariantArtifacts,
) -> dict[str, Any]:
    spatial, load = name.split("-", 1)
    expected = EXPECTED_VARIANTS[name]
    codes, frame, strict_png = artifacts.codes, artifacts.frame, artifacts.strict_png
    metrics = low_spatial.spatial_metrics(codes)
    left_codes = _half_bytes(codes, 0)
    right_codes = _half_bytes(codes, 1)
    global_matrix = low_spatial._transition_matrix(prior_codes, codes)
    left_matrix = low_spatial._transition_matrix(prior_codes, codes, x0=0, x1=WIDTH // 2)
    right_matrix = low_spatial._transition_matrix(prior_codes, codes, x0=WIDTH // 2, x1=WIDTH)
    counts = (_counts(codes), _counts(left_codes), _counts(right_codes))
    target_counts = (
        GLOBAL_COUNTS,
        BALANCED_LEFT_COUNTS if load == "balanced" else UNBALANCED_LEFT_COUNTS,
        BALANCED_RIGHT_COUNTS if load == "balanced" else UNBALANCED_RIGHT_COUNTS,
    )
    changed_left = sum(
        prior_codes[y * WIDTH + x] != codes[y * WIDTH + x]
        for y in range(HEIGHT) for x in range(WIDTH // 2)
    )
    changed_right = sum(
        prior_codes[y * WIDTH + x] != codes[y * WIDTH + x]
        for y in range(HEIGHT) for x in range(WIDTH // 2, WIDTH)
    )
    actual_identity = {
        "codes_sha256": _sha256(codes),
        "frame_sha256": _sha256(frame),
        "frame_fnv1a": f"0x{fnv1a(frame):08X}",
        "strict_sha256": _sha256(strict_png),
        "controller_internal_edges": tuple(
            record["total_internal_edges"]["different"] for record in metrics["controllers"]
        ),
        "controller_seam": metrics["controller_seam"]["different"],
        "total_edges": metrics["total_four_neighbour_edges"]["different"],
        "boundary_pixels": metrics["boundary_pixels"]["count"],
    }
    for key, value in actual_identity.items():
        if value != expected[key]:
            raise FactorialCandidateError(f"{name} frozen {key} identity changed")
    if counts != target_counts or global_matrix != GLOBAL_TRANSITION_MATRIX:
        raise FactorialCandidateError(f"{name} count/global-transition invariant changed")
    if changed_left + changed_right != EXPECTED_CHANGED_PIXELS:
        raise FactorialCandidateError(f"{name} changed-pixel invariant changed")
    return {
        "factors": {"controller_internal_spatial_frequency": spatial, "half_load": load},
        "frame": {
            "file": f"{name}.frame.bin",
            "bytes": len(frame),
            "encoding": "canonical-row-major-two-4bit-codes-per-byte-even-x-high-nibble",
            "sha256": actual_identity["frame_sha256"],
            "fnv1a": actual_identity["frame_fnv1a"],
            "codes_sha256": actual_identity["codes_sha256"],
        },
        "controllers": _controller_records(frame, expected["controllers"]),
        "counts": {
            "code_order": list(PHYSICAL_CODE_ORDER),
            "global": list(counts[0]),
            "left": list(counts[1]),
            "right": list(counts[2]),
            "left_minus_right": [left - right for left, right in zip(counts[1], counts[2])],
            "half_imbalance_l1": sum(abs(left - right) for left, right in zip(counts[1], counts[2])),
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
        "spatial_metrics": metrics,
        "strict_preview": {
            "file": f"{name}.strict-final.png",
            "bytes": len(strict_png),
            "sha256": actual_identity["strict_sha256"],
            "width": WIDTH,
            "height": HEIGHT,
            "semantics": "strict reference-palette rendering of the exact six-code cell",
        },
    }


def build_factorial_artifacts() -> FactorialArtifacts:
    """Deep-audit inputs and regenerate all four frozen offline cells."""

    prior_codes, audited_manifests = audit_fixed_inputs()
    variants: dict[str, VariantArtifacts] = {}
    records: dict[str, Any] = {}
    for name in VARIANT_NAMES:
        spatial, load = name.split("-", 1)
        codes = generate_variant_codes(prior_codes, spatial=spatial, load=load)
        frame = pack_pixels(codes)
        validate_frame(frame)
        if len(frame) != FRAME_BYTES:
            raise FactorialCandidateError(f"{name} frame length changed")
        strict_png = low_spatial._strict_preview(codes)
        variant = VariantArtifacts(codes, frame, strict_png)
        variants[name] = variant
        records[name] = _variant_record(name, prior_codes, variant)

    totals = {name: records[name]["spatial_metrics"]["total_four_neighbour_edges"]["different"]
              for name in VARIANT_NAMES}
    imbalances = {name: records[name]["counts"]["half_imbalance_l1"] for name in VARIANT_NAMES}
    if not min(totals["high-unbalanced"], totals["high-balanced"]) > 10 * max(
        totals["low-unbalanced"], totals["low-balanced"]
    ):
        raise FactorialCandidateError("high/low spatial manipulation separation is insufficient")
    if set(imbalances[name] for name in VARIANT_NAMES if name.split("-", 1)[1] == "balanced") != {4}:
        raise FactorialCandidateError("balanced factor manipulation identity changed")
    if set(imbalances[name] for name in VARIANT_NAMES if name.split("-", 1)[1] == "unbalanced") != {186_896}:
        raise FactorialCandidateError("unbalanced factor manipulation identity changed")

    audit_records = {
        name: {
            **dict(identity),
            "deep_validated": True,
            "kind": audited_manifests[name]["kind"],
            "eligible_as_constraint_reference": name in {"failed_ordered", "low_spatial"},
            "raster_identical_to_generated_cell": name == "low_spatial",
            "generated_cell_identity": "low-balanced" if name == "low_spatial" else None,
            "constraint_reference_reason": {
                "failed_ordered": (
                    "shares the frozen MAP-prior global transition and unbalanced split; "
                    "it is a constraint source only and its raster is not any generated 2x2 cell"
                ),
                "low_spatial": (
                    "shares the frozen MAP-prior global transition and balanced split; "
                    "its raster is exactly the generated low-balanced cell"
                ),
                "clustered": "excluded: uses the low-spatial prior and a different global transition contract",
                "macro4": "excluded: uses the low-spatial prior and different global histogram/transitions",
            }[name],
        }
        for name, identity in INPUT_IDENTITIES.items()
    }
    manifest: dict[str, Any] = {
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
        },
        "algorithm": {
            "id": ALGORITHM_ID,
            "deterministic": True,
            "physical_code_order": list(PHYSICAL_CODE_ORDER),
            "allocation_block_order": list(ALLOCATION_BLOCK_ORDER),
            "low_position_order": "top-left row-major inside each half and old-code mask",
            "high_position_order": (
                "5x5 local phase rank, then phase-tile row/column, then absolute row-major; "
                "applied independently inside each half and old-code mask"
            ),
            "high_phase_side": HIGH_PHASE_SIDE,
            "runtime_solver": None,
            "randomness": False,
        },
        "design": {
            "factor_A": {
                "name": "controller_internal_spatial_frequency",
                "levels": ["high", "low"],
                "manipulation": "position order only; transition-cell counts are unchanged",
            },
            "factor_B": {
                "name": "left_right_pigment_transition_load",
                "levels": ["balanced", "unbalanced"],
                "manipulation": "frozen integer split of every global old-code to new-code cell",
            },
            "cell_order": list(VARIANT_NAMES),
            "exact_shared_invariants": {
                "global_counts": list(GLOBAL_COUNTS),
                "global_transition_matrix": _matrix_record(GLOBAL_TRANSITION_MATRIX),
                "global_transition_canonical_sha256": _sha256(
                    _canonical_json(_matrix_record(GLOBAL_TRANSITION_MATRIX))
                ),
                "changed_pixels_from_map_prior": EXPECTED_CHANGED_PIXELS,
            },
            "manipulation_checks": {
                "total_edges": totals,
                "half_imbalance_l1": imbalances,
                "minimum_high_to_maximum_low_edge_ratio": min(
                    totals["high-unbalanced"], totals["high-balanced"]
                ) / max(totals["low-unbalanced"], totals["low-balanced"]),
            },
            "orthogonality_audit": {
                "algebraic_2x2_crossing_proven": True,
                "global_histogram_exactly_equal": True,
                "global_transition_matrix_exactly_equal": True,
                "factor_construction_crossed": True,
                "exact_spatial_metric_match_within_each_A_level": False,
                "exact_seam_match_across_cells": False,
                "status": "bounded_residual_covariates_not_strict_metric_orthogonality",
                "fail_closed_consequence": (
                    "the bundle is an offline manipulation audit only and cannot by itself support "
                    "formal causal attribution, upload, refresh, or hardware qualification"
                ),
                "residual_covariates": {
                    "high_total_edge_spread": abs(totals["high-unbalanced"] - totals["high-balanced"]),
                    "low_total_edge_spread": abs(totals["low-unbalanced"] - totals["low-balanced"]),
                    "seam_by_cell": {
                        name: records[name]["spatial_metrics"]["controller_seam"]["different"]
                        for name in VARIANT_NAMES
                    },
                },
            },
        },
        "prior": {
            "fixture": low_spatial.MAP_FIXTURE,
            "frame_sha256": MAP_FRAME_SHA256,
            "codes_sha256": MAP_CODES_SHA256,
            "semantics": "the frozen last-visible MAP state used by the job2/job4 diagnostic contract",
        },
        "audited_existing_candidates": audit_records,
        "variants": records,
        "required_file_set": sorted(REQUIRED_FILES),
        "limitations": [
            "The four cells preserve exact global counts and global transitions, but do not preserve source-image semantics.",
            "Exact equality of total edge and seam metrics across the two B levels was not proven; the residuals are explicit.",
            "Pixel counts, transition cells, and four-neighbour edges are not measured electrical energy or waveform cost.",
            "The 5x5 high-frequency allocator is a deterministic diagnostic manipulation, not a quality algorithm.",
            "No cell is authorized for ingress, upload, refresh, or a hardware claim.",
        ],
        "transport": {
            "mode": "offline",
            "endpoint": None,
            "method": None,
            "device_io_performed": False,
            "network_io_performed": False,
            "refresh_runner_implemented": False,
            "upload_authorized": False,
        },
    }
    manifest["manifest_integrity"] = {
        "canonical_sha256": _sha256(_canonical_json(manifest)),
        "canonical_sha256_scope": MANIFEST_HASH_SCOPE,
    }
    if (
        EXPECTED_MANIFEST_CANONICAL_SHA256 is not None
        and manifest["manifest_integrity"]["canonical_sha256"]
        != EXPECTED_MANIFEST_CANONICAL_SHA256
    ):
        raise FactorialCandidateError("frozen manifest canonical identity changed")
    manifest_bytes = _canonical_json(manifest)
    if EXPECTED_MANIFEST_FILE_SHA256 is not None and _sha256(manifest_bytes) != EXPECTED_MANIFEST_FILE_SHA256:
        raise FactorialCandidateError("frozen manifest file identity changed")
    return FactorialArtifacts(variants, manifest, manifest_bytes)


def _safe_directory(path: Path, *, label: str, must_exist: bool) -> Path:
    try:
        return clustered._safe_directory(path, label=label, must_exist=must_exist)
    except Exception as error:
        raise FactorialCandidateError(str(error)) from error


def validate_factorial_directory(directory: Path) -> Mapping[str, Any]:
    """Reject non-contract files and compare every byte with deep regeneration."""

    resolved = _safe_directory(directory, label="2x2 audit directory", must_exist=True)
    entries = tuple(resolved.iterdir())
    if any(entry.is_symlink() for entry in entries):
        raise FactorialCandidateError("2x2 audit directory must not contain symlinks")
    actual_files = {entry.name for entry in entries if entry.is_file()}
    if actual_files != REQUIRED_FILES or any(not entry.is_file() for entry in entries):
        raise FactorialCandidateError(
            f"2x2 audit directory file set must be exactly {sorted(REQUIRED_FILES)}"
        )
    manifest_bytes = (resolved / "manifest.json").read_bytes()
    try:
        manifest = clustered._load_json_strict(manifest_bytes)
    except Exception as error:
        raise FactorialCandidateError(str(error)) from error
    if not isinstance(manifest, dict) or manifest_bytes != _canonical_json(manifest):
        raise FactorialCandidateError("2x2 audit manifest is not canonical JSON")
    unsigned = dict(manifest)
    integrity = unsigned.pop("manifest_integrity", None)
    if integrity != {
        "canonical_sha256": _sha256(_canonical_json(unsigned)),
        "canonical_sha256_scope": MANIFEST_HASH_SCOPE,
    }:
        raise FactorialCandidateError("2x2 audit manifest canonical integrity is invalid")
    expected = build_factorial_artifacts()
    if manifest != expected.manifest or manifest_bytes != expected.manifest_bytes:
        raise FactorialCandidateError("2x2 audit manifest does not match deep regeneration")
    for filename, payload in expected.files().items():
        if (resolved / filename).read_bytes() != payload:
            raise FactorialCandidateError(f"2x2 audit file {filename} differs from regeneration")
    return manifest


def write_factorial_directory(output_dir: Path) -> Mapping[str, Any]:
    """Atomically create one new offline bundle and refuse all overwrites."""

    destination = _safe_directory(output_dir, label="output directory", must_exist=False)
    artifacts = build_factorial_artifacts()
    temporary = destination.parent / f".{destination.name}.tmp-{uuid.uuid4().hex}"
    try:
        clustered._reject_symlink_ancestors(temporary.parent, label="temporary output directory")
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
        if isinstance(error, FactorialCandidateError):
            raise
        raise FactorialCandidateError(f"could not create 2x2 audit bundle: {error}") from error
    return validate_factorial_directory(destination)


validate_candidate_directory = validate_factorial_directory


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output-dir", type=Path, help="new local offline 2x2 bundle")
    mode.add_argument("--validate-dir", type=Path, help="existing local offline 2x2 bundle")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.output_dir is not None:
            manifest = write_factorial_directory(args.output_dir)
            mode = "generated"
            directory = args.output_dir
        else:
            manifest = validate_factorial_directory(args.validate_dir)
            mode = "validated"
            directory = args.validate_dir
    except (FactorialCandidateError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(
        _canonical_json(
            {
                "ok": True,
                "mode": mode,
                "directory": os.fspath(directory),
                "kind": manifest["kind"],
                "manifest_canonical_sha256": manifest["manifest_integrity"]["canonical_sha256"],
                "frame_sha256_by_cell": {
                    name: manifest["variants"][name]["frame"]["sha256"] for name in VARIANT_NAMES
                },
                "strict_metric_orthogonality_proven": False,
                "device_io_performed": False,
                "upload_authorized": False,
            }
        ).decode("utf-8")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
