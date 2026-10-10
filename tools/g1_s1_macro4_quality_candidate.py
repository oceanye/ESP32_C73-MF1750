#!/usr/bin/env python3
"""Build or deeply validate the fixed offline G1/S1 macro4 quality candidate.

This tool has no device, upload, or refresh mode.  It reduces the frozen
1024x600 mapped monitor target to 256x150 with an explicitly specified 4x4
integer BOX filter, runs the fixed area-weighted blue-noise quantizer, and
replicates every resulting physical code to one 4x4 macro pixel.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Optional, Sequence
import uuid

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.application import simulation  # noqa: E402
from host.application.simulation import SimulationAlgorithm  # noqa: E402
from host.color_pipeline import (  # noqa: E402
    DitherMode,
    RasterImage,
    build_protection_constraints,
    reference_palette,
)
from host.epd_frame import (  # noqa: E402
    FRAME_BYTES,
    HEIGHT,
    WIDTH,
    ControllerMapping,
    fnv1a,
    pack_pixels,
    unpack_pixels,
    validate_frame,
)
from host.gamut_mapping import build_synthetic_reference_profile  # noqa: E402
from host.halftone_optimization import (  # noqa: E402
    BlueNoiseOptions,
    quantize_area_weighted_blue_noise,
)
from tools import g1_s1_clustered_quality_candidate as shared  # noqa: E402
from tools import g1_s1_low_spatial_diagnostic as low_spatial  # noqa: E402
from tools import g1_s1_panel_candidate as panel_candidate  # noqa: E402


SCHEMA_VERSION = 1
MANIFEST_KIND = "mf1750-g1-s1-macro4-quality-candidate"
MANIFEST_HASH_SCOPE = (
    "entire manifest excluding manifest_integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
ALGORITHM_ID = "low-resolution-area-weighted-blue-noise-nearest-macro-v1"
MACRO_FACTOR = 4
LOW_WIDTH = WIDTH // MACRO_FACTOR
LOW_HEIGHT = HEIGHT // MACRO_FACTOR
SEED = 0x4D463137
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
BASELINE_SOURCE_SHA256 = "b8400d6c901fcfefac49eafb2b2db4dadfdc5615392640dfe4cef7efe068f101"
BASELINE_MAPPED_SHA256 = "22488999efd344e2f3462de09ca1db6eb36e95ab4a728f3481990acc3503d1ef"
BASELINE_MAPPED_RGB8_SHA256 = "f1800002ce534e33a481f42f0cf72775daa603b389335b764cc0f37ba649002e"

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

EXPECTED_LOW_RGB8_SHA256 = "b91d3173f6ae5d33bf98db618af052be3b06972bf8192e1d26b72afe3dd3dffb"
EXPECTED_AREA_WEIGHTS_SHA256 = "18b6f33a411a9318cc15ffec6a004f835365724f6e6925523d889390117a81a3"
EXPECTED_PROTECTION_MASK_SHA256 = "2c0dd4e13bc5ba5455c8939c00208572512221776ef024498cc41fb597536b3a"
EXPECTED_LOCKED_PIXELS = 3146
EXPECTED_LOW_CODES_SHA256 = "cfa277b9df0dbdedc06c2c19239e1fdf5b8b824ba66128438b43e8327138ca41"
EXPECTED_CODES_SHA256 = "b772e30ba2fa2f500b02ffbe62605ea7954d805c890c411b2eb1c95809090688"
EXPECTED_FRAME_SHA256 = "1f509baa655d84fe13da65441f22929f32a43a0ac66d45d753f7a3d394a2281d"
EXPECTED_FRAME_FNV1A = "0x092C9775"
EXPECTED_STRICT_SHA256 = "9f9494fafb76cad80d72156aa011993175b9013da941ff9998395666cbe6812e"
EXPECTED_MODEL_SHA256 = "cc6a97094ba24273b79527ffcb814f2b2dce0d67e0dd7a58f8207f8f8069e63c"
EXPECTED_CONTROLLER_IDENTITIES = (
    ("a36a9288154d882916a6562d44d86c41278ea45ffbfcbc2afe634616d5a52fcc", "0x3F1601D5"),
    ("d9bf80b6433bba8356502ce62ce44450da7339902413d9018d4ee6c959fb231d", "0x52ECC935"),
)
EXPECTED_SPATIAL = {
    "horizontal_internal": 62560,
    "controller_seam": 232,
    "vertical": 64204,
    "total_edges": 126996,
    "boundary_pixels": 216192,
}
EXPECTED_CONTROLLER_INTERNAL_EDGES = (53836, 72928)
EXPECTED_CHANGED_PIXELS = 459679


class Macro4CandidateError(RuntimeError):
    """Raised when the fixed offline candidate contract cannot be proven."""


@dataclass(frozen=True)
class Macro4Artifacts:
    codes: bytes
    frame: bytes
    source_png: bytes
    mapped_png: bytes
    strict_png: bytes
    model_png: bytes
    manifest: Mapping[str, Any]
    manifest_bytes: bytes

    def files(self) -> dict[str, bytes]:
        return {
            "frame.bin": self.frame,
            "source.png": self.source_png,
            "mapped.png": self.mapped_png,
            "strict-final.png": self.strict_png,
            "model.png": self.model_png,
            "manifest.json": self.manifest_bytes,
        }


def _sha256(payload: bytes | bytearray | memoryview) -> str:
    return shared._sha256(payload)


def _canonical_json(value: Any) -> bytes:
    return shared._canonical_json(value)


def _decode_fixed_rgb_png(payload: bytes) -> bytes:
    try:
        with Image.open(BytesIO(payload)) as image:
            image.load()
            if image.size != (WIDTH, HEIGHT):
                raise Macro4CandidateError("mapped PNG dimensions differ from the fixed panel")
            decoded = image.convert("RGB").tobytes()
    except Macro4CandidateError:
        raise
    except Exception as error:
        raise Macro4CandidateError(f"could not decode fixed mapped PNG: {error}") from error
    if len(decoded) != WIDTH * HEIGHT * 3:
        raise Macro4CandidateError("decoded mapped RGB length is invalid")
    return decoded


def box_downsample_4x4_half_up(rgb8: bytes) -> bytes:
    """Two-stage uint8 BOX: horizontal half-up, then vertical half-up."""

    if len(rgb8) != WIDTH * HEIGHT * 3:
        raise Macro4CandidateError("BOX input must be the fixed RGB8 panel raster")
    horizontal = bytearray(LOW_WIDTH * HEIGHT * 3)
    for y_value in range(HEIGHT):
        input_row = y_value * WIDTH * 3
        output_row = y_value * LOW_WIDTH * 3
        for low_x in range(LOW_WIDTH):
            source = input_row + low_x * MACRO_FACTOR * 3
            target = output_row + low_x * 3
            for channel in range(3):
                total = sum(rgb8[source + step * 3 + channel] for step in range(MACRO_FACTOR))
                horizontal[target + channel] = (total + 2) // 4
    low = bytearray(LOW_WIDTH * LOW_HEIGHT * 3)
    for low_y in range(LOW_HEIGHT):
        for low_x in range(LOW_WIDTH):
            target = (low_y * LOW_WIDTH + low_x) * 3
            for channel in range(3):
                total = sum(
                    horizontal[((low_y * MACRO_FACTOR + step) * LOW_WIDTH + low_x) * 3 + channel]
                    for step in range(MACRO_FACTOR)
                )
                low[target + channel] = (total + 2) // 4
    return bytes(low)


def expand_codes_4x4(low_codes: bytes) -> bytes:
    if len(low_codes) != LOW_WIDTH * LOW_HEIGHT:
        raise Macro4CandidateError("low-resolution code count is invalid")
    allowed = set(shared.PHYSICAL_CODE_ORDER)
    if any(code not in allowed for code in low_codes):
        raise Macro4CandidateError("low-resolution raster contains an invalid physical code")
    output = bytearray(WIDTH * HEIGHT)
    for low_y in range(LOW_HEIGHT):
        expanded_row = b"".join(
            bytes((low_codes[low_y * LOW_WIDTH + low_x],)) * MACRO_FACTOR
            for low_x in range(LOW_WIDTH)
        )
        for repeat in range(MACRO_FACTOR):
            start = (low_y * MACRO_FACTOR + repeat) * WIDTH
            output[start : start + WIDTH] = expanded_row
    return bytes(output)


def _validate_fixed_inputs() -> tuple[Mapping[str, Any], bytes, bytes, Mapping[str, Any], bytes]:
    try:
        baseline = panel_candidate.validate_candidate_directory(BASELINE_DIR)
        prior = low_spatial.validate_diagnostic_directory(PRIOR_DIR)
    except Exception as error:
        raise Macro4CandidateError(f"fixed input deep validation failed: {error}") from error
    baseline_manifest_bytes = (BASELINE_DIR / "manifest.json").read_bytes()
    prior_manifest_bytes = (PRIOR_DIR / "manifest.json").read_bytes()
    if _sha256(baseline_manifest_bytes) != BASELINE_MANIFEST_FILE_SHA256:
        raise Macro4CandidateError("baseline manifest file identity changed")
    if baseline.get("manifest_integrity", {}).get("canonical_sha256") != BASELINE_MANIFEST_CANONICAL_SHA256:
        raise Macro4CandidateError("baseline manifest canonical identity changed")
    if _sha256(prior_manifest_bytes) != PRIOR_MANIFEST_FILE_SHA256:
        raise Macro4CandidateError("prior manifest file identity changed")
    if prior.get("manifest_integrity", {}).get("canonical_sha256") != PRIOR_MANIFEST_CANONICAL_SHA256:
        raise Macro4CandidateError("prior manifest canonical identity changed")
    source_png = (BASELINE_DIR / "source.png").read_bytes()
    mapped_png = (BASELINE_DIR / "mapped.png").read_bytes()
    baseline_frame = (BASELINE_DIR / "frame.bin").read_bytes()
    prior_frame = (PRIOR_DIR / "frame.bin").read_bytes()
    fixed = (
        (_sha256(source_png), BASELINE_SOURCE_SHA256, "source PNG"),
        (_sha256(mapped_png), BASELINE_MAPPED_SHA256, "mapped PNG"),
        (_sha256(baseline_frame), BASELINE_FRAME_SHA256, "baseline frame"),
        (_sha256(prior_frame), PRIOR_FRAME_SHA256, "prior frame"),
        (_sha256(unpack_pixels(prior_frame)), PRIOR_CODES_SHA256, "prior codes"),
    )
    for actual, expected, label in fixed:
        if actual != expected:
            raise Macro4CandidateError(f"{label} identity changed")
    if f"0x{fnv1a(prior_frame):08X}" != PRIOR_FRAME_FNV1A:
        raise Macro4CandidateError("prior frame FNV identity changed")
    return baseline, source_png, mapped_png, prior, prior_frame


def _controller_records(frame: bytes) -> list[dict[str, Any]]:
    records = shared._controller_records(frame)
    for record, (expected_sha, expected_fnv) in zip(records, EXPECTED_CONTROLLER_IDENTITIES):
        if record["dtm_sha256"] != expected_sha or record["dtm_fnv1a"] != expected_fnv:
            raise Macro4CandidateError("controller DTM identity differs from the frozen contract")
    return records


def _controller_internal_edges(codes: bytes, x0: int, x1: int) -> dict[str, Any]:
    horizontal = sum(
        codes[y_value * WIDTH + x_value] != codes[y_value * WIDTH + x_value + 1]
        for y_value in range(HEIGHT)
        for x_value in range(x0, x1 - 1)
    )
    vertical = sum(
        codes[y_value * WIDTH + x_value] != codes[(y_value + 1) * WIDTH + x_value]
        for y_value in range(HEIGHT - 1)
        for x_value in range(x0, x1)
    )
    return {
        "horizontal_internal": horizontal,
        "vertical": vertical,
        "total_internal_edges": horizontal + vertical,
    }


def _macro_grid_metrics(codes: bytes) -> dict[str, Any]:
    horizontal_grid = horizontal_inside = vertical_grid = vertical_inside = 0
    for y_value in range(HEIGHT):
        row = y_value * WIDTH
        for x_value in range(WIDTH - 1):
            if codes[row + x_value] == codes[row + x_value + 1]:
                continue
            if (x_value + 1) % MACRO_FACTOR == 0:
                horizontal_grid += 1
            else:
                horizontal_inside += 1
    for y_value in range(HEIGHT - 1):
        for x_value in range(WIDTH):
            if codes[y_value * WIDTH + x_value] == codes[(y_value + 1) * WIDTH + x_value]:
                continue
            if (y_value + 1) % MACRO_FACTOR == 0:
                vertical_grid += 1
            else:
                vertical_inside += 1
    return {
        "definition": "four-neighbour code-difference edges split by 4x4 macro boundaries",
        "horizontal_macro_boundaries": horizontal_grid,
        "horizontal_inside_macro": horizontal_inside,
        "vertical_macro_boundaries": vertical_grid,
        "vertical_inside_macro": vertical_inside,
    }


def _file_record(filename: str, payload: bytes, semantics: str) -> dict[str, Any]:
    return {
        "file": filename,
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "width": WIDTH,
        "height": HEIGHT,
        "semantics": semantics,
    }


def build_macro4_artifacts() -> Macro4Artifacts:
    baseline, source_png, mapped_png, prior_manifest, prior_frame = _validate_fixed_inputs()
    mapped_rgb8 = _decode_fixed_rgb_png(mapped_png)
    if _sha256(mapped_rgb8) != BASELINE_MAPPED_RGB8_SHA256:
        raise Macro4CandidateError("decoded mapped RGB8 identity changed")
    low_rgb8 = box_downsample_4x4_half_up(mapped_rgb8)
    if _sha256(low_rgb8) != EXPECTED_LOW_RGB8_SHA256:
        raise Macro4CandidateError("low-resolution BOX raster identity changed")

    palette = reference_palette()
    profile = build_synthetic_reference_profile(palette)
    options = panel_candidate._simulation_options(
        SimulationAlgorithm.AREA_WEIGHTED_BLUE_NOISE,
        seed=SEED,
        dbs_evaluations=panel_candidate.DEFAULT_DBS_EVALUATIONS,
    )
    low_image = RasterImage(LOW_WIDTH, LOW_HEIGHT, "RGB", low_rgb8)
    weights, area_report = simulation._area_weights(low_image, palette, profile, options)
    constraints = build_protection_constraints(
        low_image,
        palette=palette,
        options=simulation._pipeline_options(options, DitherMode.NONE),
    )
    quantized = quantize_area_weighted_blue_noise(
        LOW_WIDTH,
        LOW_HEIGHT,
        weights,
        palette=palette,
        options=BlueNoiseOptions(seed=SEED),
        solver_id="g1-discrete-area-weight-solver-v1",
        code_constraints=constraints,
    )
    low_codes = bytes(quantized.codes)
    report = dict(quantized.report)
    if _sha256(low_codes) != EXPECTED_LOW_CODES_SHA256:
        raise Macro4CandidateError("low-resolution code identity differs from the frozen contract")
    if report["area_weights"]["canonical_binary64_sha256"] != EXPECTED_AREA_WEIGHTS_SHA256:
        raise Macro4CandidateError("area-weight identity differs from the frozen contract")
    if report["code_constraints"]["mask_sha256"] != EXPECTED_PROTECTION_MASK_SHA256:
        raise Macro4CandidateError("protection-mask identity differs from the frozen contract")
    if report["code_constraints"]["locked_pixels"] != EXPECTED_LOCKED_PIXELS:
        raise Macro4CandidateError("locked-pixel count differs from the frozen contract")

    codes = expand_codes_4x4(low_codes)
    frame = pack_pixels(codes)
    validate_frame(frame)
    if _sha256(codes) != EXPECTED_CODES_SHA256:
        raise Macro4CandidateError("full code identity differs from the frozen contract")
    if _sha256(frame) != EXPECTED_FRAME_SHA256 or f"0x{fnv1a(frame):08X}" != EXPECTED_FRAME_FNV1A:
        raise Macro4CandidateError("frame identity differs from the frozen contract")
    strict_png = shared._strict_preview(codes)
    model_png, observation_model = shared._model_preview(codes)
    if _sha256(strict_png) != EXPECTED_STRICT_SHA256 or _sha256(model_png) != EXPECTED_MODEL_SHA256:
        raise Macro4CandidateError("preview identity differs from the frozen contract")

    spatial = shared.spatial_metrics(codes)
    for name, expected in EXPECTED_SPATIAL.items():
        if spatial[name]["count"] != expected:
            raise Macro4CandidateError(f"spatial metric {name} differs from the frozen contract")
    controller_edges = [
        _controller_internal_edges(codes, 0, WIDTH // 2),
        _controller_internal_edges(codes, WIDTH // 2, WIDTH),
    ]
    if tuple(item["total_internal_edges"] for item in controller_edges) != EXPECTED_CONTROLLER_INTERNAL_EDGES:
        raise Macro4CandidateError("per-controller edge counts differ from the frozen contract")
    prior_codes = unpack_pixels(prior_frame)
    transition = shared._transition_record(prior_codes, codes)
    if transition["changed_pixels"] != EXPECTED_CHANGED_PIXELS:
        raise Macro4CandidateError("prior transition count differs from the frozen contract")

    counts_global = shared._counts(codes)
    counts_left = shared._counts(codes, x0=0, x1=WIDTH // 2)
    counts_right = shared._counts(codes, x0=WIDTH // 2, x1=WIDTH)
    controllers = _controller_records(frame)
    low_report = {
        "width": LOW_WIDTH,
        "height": LOW_HEIGHT,
        "mapped_rgb8_sha256": _sha256(low_rgb8),
        "codes_sha256": _sha256(low_codes),
        "code_counts": [low_codes.count(code) for code in shared.PHYSICAL_CODE_ORDER],
        "area_weight_report": area_report,
        "quantization_report": report,
    }
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "classification": {
            "experimental": True,
            "simulation_only": True,
            "formal": False,
            "hardware_qualified": False,
            "hardware_tested": False,
            "upload_authorized": False,
            "preview_review_status": "pending_runtime_authorization_record",
        },
        "algorithm": {
            "id": ALGORITHM_ID,
            "seed": SEED,
            "downsample": {
                "source": "byte-identical decoded mapped.png RGB8",
                "input_dimensions": [WIDTH, HEIGHT],
                "output_dimensions": [LOW_WIDTH, LOW_HEIGHT],
                "method": "separable 4-sample uint8 mean with half-up rounding, horizontal then vertical",
                "factor": MACRO_FACTOR,
                "output_rgb8_sha256": _sha256(low_rgb8),
            },
            "low_resolution": low_report,
            "upsample": {
                "method": "nearest-neighbour exact physical-code replication",
                "macro_pixel_width": MACRO_FACTOR,
                "macro_pixel_height": MACRO_FACTOR,
            },
            "options": panel_candidate._options_mapping(options),
        },
        "evidence": {
            "baseline_blue_noise": {
                "artifact_id": BASELINE_DIR.name,
                "deep_validator": "tools.g1_s1_panel_candidate.validate_candidate_directory",
                "manifest_file_sha256": BASELINE_MANIFEST_FILE_SHA256,
                "manifest_canonical_sha256": BASELINE_MANIFEST_CANONICAL_SHA256,
                "frame_sha256": BASELINE_FRAME_SHA256,
                "source_png_sha256": BASELINE_SOURCE_SHA256,
                "mapped_png_sha256": BASELINE_MAPPED_SHA256,
                "mapped_rgb8_sha256": BASELINE_MAPPED_RGB8_SHA256,
                "simulation_report_canonical_sha256": baseline["simulation"]["report_canonical_sha256"],
            },
            "true_screen_prior": {
                "artifact_id": PRIOR_DIR.name,
                "deep_validator": "tools.g1_s1_low_spatial_diagnostic.validate_diagnostic_directory",
                "manifest_file_sha256": PRIOR_MANIFEST_FILE_SHA256,
                "manifest_canonical_sha256": PRIOR_MANIFEST_CANONICAL_SHA256,
                "frame_sha256": PRIOR_FRAME_SHA256,
                "frame_fnv1a": PRIOR_FRAME_FNV1A,
                "codes_sha256": PRIOR_CODES_SHA256,
                "hardware_state_claim": "caller must separately verify this is still the displayed prior",
                "prior_manifest_kind": prior_manifest["kind"],
            },
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
            "controllers": controllers,
            "counts": {
                "code_order": list(shared.PHYSICAL_CODE_ORDER),
                "global": counts_global,
                "left": counts_left,
                "right": counts_right,
                "left_minus_right": [left - right for left, right in zip(counts_left, counts_right)],
            },
            "spatial_metrics": spatial,
            "controller_internal_edges": [
                {"controller": "CS1", **controller_edges[0]},
                {"controller": "CS2", **controller_edges[1]},
            ],
            "macro_grid_metrics": _macro_grid_metrics(codes),
            "transition_from_true_screen_prior": transition,
        },
        "previews": {
            "source": _file_record("source.png", source_png, "byte-identical frozen source monitor rendering"),
            "mapped": _file_record("mapped.png", mapped_png, "byte-identical frozen continuous mapped target"),
            "strict_final": _file_record("strict-final.png", strict_png, "exact physical six-code macro4 rendering"),
            "model": _file_record("model.png", model_png, "uncalibrated Gaussian overlap monitor simulation"),
        },
        "observation_model": observation_model,
        "comparisons": {
            "failed_ordered_total_edges": {"count": 504453, "possible": 1227176},
            "passed_low_spatial_total_edges": {"count": 29565, "possible": 1227176},
            "candidate_total_edges_reduction_vs_failed": {
                "count": 504453 - EXPECTED_SPATIAL["total_edges"],
                "ratio": 1.0 - EXPECTED_SPATIAL["total_edges"] / 504453,
            },
            "candidate_controller_edges_as_fraction_of_failed": [
                EXPECTED_CONTROLLER_INTERNAL_EDGES[0] / 211852,
                EXPECTED_CONTROLLER_INTERNAL_EDGES[1] / 292359,
            ],
        },
        "limitations": [
            "This is an experimental safety-reduced area-weighted blue-noise variant, not the full-resolution algorithm qualification.",
            "The 4x4 macro pixels deliberately trade fine spatial detail for fewer code boundaries and remain visible at close range.",
            "The synthetic palette/profile and shared Gaussian kernel are not measured MF-1750 colour or optical characterization.",
            "Code-difference edges and transition counts are diagnostic proxies, not electrical energy or waveform-cost measurements.",
            "A successful display would apply only to this exact frame/build/mapping and would not close the earlier ordered-frame timeout root cause.",
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
    manifest["manifest_integrity"] = {
        "canonical_sha256": _sha256(_canonical_json(manifest)),
        "canonical_sha256_scope": MANIFEST_HASH_SCOPE,
    }
    manifest_bytes = _canonical_json(manifest)
    return Macro4Artifacts(
        codes,
        frame,
        source_png,
        mapped_png,
        strict_png,
        model_png,
        manifest,
        manifest_bytes,
    )


def _safe_directory(path: Path, *, label: str, must_exist: bool) -> Path:
    try:
        return shared._safe_directory(path, label=label, must_exist=must_exist)
    except Exception as error:
        raise Macro4CandidateError(str(error)) from error


def validate_macro4_directory(directory: Path) -> Mapping[str, Any]:
    resolved = _safe_directory(directory, label="macro4 directory", must_exist=True)
    entries = tuple(resolved.iterdir())
    if any(entry.is_symlink() for entry in entries):
        raise Macro4CandidateError("macro4 directory must not contain symlinks")
    actual_files = {entry.name for entry in entries if entry.is_file()}
    if actual_files != REQUIRED_FILES or any(not entry.is_file() for entry in entries):
        raise Macro4CandidateError(f"macro4 directory file set must be exactly {sorted(REQUIRED_FILES)}")
    manifest_bytes = (resolved / "manifest.json").read_bytes()
    try:
        manifest = shared._load_json_strict(manifest_bytes)
    except Exception as error:
        raise Macro4CandidateError(str(error)) from error
    if not isinstance(manifest, dict) or manifest_bytes != _canonical_json(manifest):
        raise Macro4CandidateError("macro4 manifest is not canonical JSON")
    unsigned = dict(manifest)
    integrity = unsigned.pop("manifest_integrity", None)
    if integrity != {
        "canonical_sha256": _sha256(_canonical_json(unsigned)),
        "canonical_sha256_scope": MANIFEST_HASH_SCOPE,
    }:
        raise Macro4CandidateError("macro4 manifest canonical integrity is invalid")
    expected = build_macro4_artifacts()
    if manifest != expected.manifest or manifest_bytes != expected.manifest_bytes:
        raise Macro4CandidateError("macro4 manifest does not match deep regeneration")
    for filename, expected_payload in expected.files().items():
        if (resolved / filename).read_bytes() != expected_payload:
            raise Macro4CandidateError(f"macro4 file {filename} does not match deep regeneration")
    return manifest


def write_macro4_directory(output_dir: Path) -> Mapping[str, Any]:
    destination = _safe_directory(output_dir, label="output directory", must_exist=False)
    artifacts = build_macro4_artifacts()
    temporary = destination.parent / f".{destination.name}.tmp-{uuid.uuid4().hex}"
    try:
        shared._reject_symlink_ancestors(temporary.parent, label="temporary output directory")
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
        if isinstance(error, Macro4CandidateError):
            raise
        raise Macro4CandidateError(f"could not create macro4 bundle: {error}") from error
    return validate_macro4_directory(destination)


# Runner implementations may use either name without weakening the contract.
validate_candidate_directory = validate_macro4_directory


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output-dir", type=Path, help="new local macro4 bundle directory")
    mode.add_argument("--validate-dir", type=Path, help="existing local macro4 bundle directory")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.output_dir is not None:
            manifest = write_macro4_directory(args.output_dir)
            mode = "generated"
            directory = args.output_dir
        else:
            manifest = validate_macro4_directory(args.validate_dir)
            mode = "validated"
            directory = args.validate_dir
    except (Macro4CandidateError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    output = manifest["output"]["frame"]
    print(
        _canonical_json(
            {
                "ok": True,
                "mode": mode,
                "directory": str(directory),
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
