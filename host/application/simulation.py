"""Software-only G1/S1 orchestration for MF-1750 monitor previews.

The module composes the canonical C2 quantizer, G1 gamut mapping and S1
spatial optimizers.  It has no network, serial, GPIO or device dependency.
Every result is explicitly a monitor simulation and is never upload-authorized.
"""

from __future__ import annotations

from array import array
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
import struct
from typing import Any, Mapping, Optional

from host.color_pipeline import (
    DitherMode,
    Palette,
    PipelineOptions,
    RasterImage,
    UNCONSTRAINED_PHYSICAL_CODE,
    build_protection_constraints,
    encode_rgb_png,
    palette_from_mapping,
    quantize_image,
    reference_palette,
    srgb8_to_lab,
)
from host.color_pipeline.color import linear_channel_to_srgb
from host.epd_frame import (
    FRAME_BYTES,
    HEIGHT,
    PHYSICAL_COLOR_CODES,
    WIDTH,
    fnv1a,
    pack_pixels,
    unpack_pixels,
    validate_frame,
)
from host.gamut_mapping import (
    AreaWeightOptions,
    AreaWeightSolver,
    GamutProfile,
    MappingMode,
    MappingOptions,
    map_raster,
    validate_mapping_report,
)
from host.halftone_optimization import (
    ALLOWED_CODES,
    AREA_WEIGHTED_BLUE_NOISE_ALGORITHM,
    AREA_WEIGHTED_ORDERED_ALGORITHM,
    DBS_ALGORITHM,
    DBS_COVERAGE_CONTRACT,
    DBS_PROPOSAL_TRACE_ENCODING,
    DBS_REPORT_SCHEMA_VERSION,
    DBS_TILE_GRID_CONTRACT,
    BlueNoiseOptions,
    DBSOptions,
    OverlapObservationModel,
    SpatialKernel,
    optimize_multicolor_dbs,
    quantize_area_weighted_blue_noise,
    quantize_area_weighted_ordered,
    quantize_blue_noise,
)


SIMULATION_REPORT_SCHEMA_VERSION = 1
SIMULATION_REPORT_KIND = "mf1750-g1-s1-monitor-simulation-report"
SIMULATION_REPORT_HASH_SCOPE = (
    "entire report excluding report_integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
SOFT_PROOF_LIMITATION = (
    "Monitor soft proof only: panel reflection, ambient illumination, waveform "
    "history, manufacturing variation and measured optical kernels are not modelled."
)


class SimulationError(ValueError):
    """Raised when a G1/S1 simulation request or artifact is inconsistent."""


class SimulationAlgorithm(str, Enum):
    NONE = "none"
    FLOYD_STEINBERG = "floyd-steinberg"
    ATKINSON = "atkinson"
    ORDERED_BAYER = "ordered-bayer-8x8"
    HASHED_THRESHOLD = "hashed-threshold"
    BLUE_NOISE = "blue-noise"
    AREA_WEIGHTED_ORDERED = "area-weighted-ordered-8x8"
    AREA_WEIGHTED_BLUE_NOISE = "area-weighted-blue-noise"
    MULTICOLOR_DBS = "multicolor-dbs"
    OVERLAP_AWARE_DBS = "overlap-aware-dbs"


_C2_ALGORITHM = {
    SimulationAlgorithm.NONE: DitherMode.NONE,
    SimulationAlgorithm.FLOYD_STEINBERG: DitherMode.FLOYD_STEINBERG,
    SimulationAlgorithm.ATKINSON: DitherMode.ATKINSON,
    SimulationAlgorithm.ORDERED_BAYER: DitherMode.ORDERED_BAYER,
    SimulationAlgorithm.HASHED_THRESHOLD: DitherMode.HASHED_THRESHOLD,
}


@dataclass(frozen=True)
class SimulationBudget:
    max_evaluations: int = 1024
    max_accepted_moves: int = 256
    stagnation_evaluations: int = 512

    def __post_init__(self) -> None:
        for label in (
            "max_evaluations",
            "max_accepted_moves",
            "stagnation_evaluations",
        ):
            value = getattr(self, label)
            if type(value) is not int or not 1 <= value <= 1_000_000:
                raise SimulationError(f"{label} must be an integer in [1, 1000000]")
        if self.max_accepted_moves > self.max_evaluations:
            raise SimulationError("max_accepted_moves cannot exceed max_evaluations")
        if self.stagnation_evaluations > self.max_evaluations:
            raise SimulationError("stagnation_evaluations cannot exceed max_evaluations")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "kind": "deterministic-work-v1",
            "max_evaluations": self.max_evaluations,
            "max_accepted_moves": self.max_accepted_moves,
            "stagnation_evaluations": self.stagnation_evaluations,
            "wall_clock_deadline_used": False,
        }


@dataclass(frozen=True)
class SimulationOptions:
    algorithm: SimulationAlgorithm | str = SimulationAlgorithm.ATKINSON
    mapping: MappingOptions = field(default_factory=MappingOptions)
    seed: int = 0x4D463137
    budget: Optional[SimulationBudget] = None
    white_protection: bool = True
    preserve_edges: bool = True
    text_mode: bool = False
    area_weight_lut_bits: int = 4

    def __post_init__(self) -> None:
        try:
            algorithm = (
                self.algorithm
                if isinstance(self.algorithm, SimulationAlgorithm)
                else SimulationAlgorithm(self.algorithm)
            )
        except (TypeError, ValueError) as error:
            raise SimulationError("unknown simulation algorithm") from error
        object.__setattr__(self, "algorithm", algorithm)
        if type(self.mapping) is not MappingOptions:
            raise SimulationError("mapping must be MappingOptions")
        if type(self.seed) is not int or not 0 <= self.seed <= 0xFFFFFFFF:
            raise SimulationError("seed must be a uint32 integer")
        for label in ("white_protection", "preserve_edges", "text_mode"):
            if type(getattr(self, label)) is not bool:
                raise SimulationError(f"{label} must be boolean")
        if type(self.area_weight_lut_bits) is not int or not 2 <= self.area_weight_lut_bits <= 6:
            raise SimulationError("area_weight_lut_bits must be an integer in [2, 6]")
        dbs = algorithm in {
            SimulationAlgorithm.MULTICOLOR_DBS,
            SimulationAlgorithm.OVERLAP_AWARE_DBS,
        }
        if dbs and type(self.budget) is not SimulationBudget:
            raise SimulationError("DBS algorithms require a deterministic SimulationBudget")
        if not dbs and self.budget is not None:
            raise SimulationError("fixed-complexity algorithms require budget=None")


@dataclass(frozen=True)
class SimulationResult:
    width: int
    height: int
    frame: bytes
    codes: bytes
    source_png: bytes
    mapped_png: bytes
    final_png: bytes
    model_png: bytes
    palette: Palette
    report: Mapping[str, Any]

    @property
    def previews(self) -> dict[str, bytes]:
        return {
            "source": self.source_png,
            "mapped": self.mapped_png,
            "final": self.final_png,
            "model": self.model_png,
        }

    def validated_snapshot(self) -> "SimulationResult":
        report = json.loads(_canonical_json(self.report).decode("utf-8"))
        frame = bytes(self.frame)
        codes = bytes(self.codes)
        dimensions = _require_mapping(report.get("dimensions"), "simulation dimensions")
        if dimensions != {"width": self.width, "height": self.height}:
            raise SimulationError("result dimensions differ from the simulation report")
        if type(self.palette) is not Palette:
            raise SimulationError("result palette must be a Palette")
        if report.get("palette") != self.palette.canonical_mapping() or report.get(
            "palette_canonical_sha256"
        ) != self.palette.canonical_sha256:
            raise SimulationError("result palette differs from the simulation report")
        if len(codes) != self.width * self.height:
            raise SimulationError("simulation result code count differs from its dimensions")
        if codes != unpack_pixels(frame, self.width, self.height):
            raise SimulationError("simulation codes do not match the packed frame")
        previews = {key: bytes(value) for key, value in self.previews.items()}
        validate_simulation_report(report, frame=frame, previews=previews)
        return SimulationResult(
            self.width,
            self.height,
            frame,
            codes,
            previews["source"],
            previews["mapped"],
            previews["final"],
            previews["model"],
            self.palette,
            report,
        )


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
        raise SimulationError(f"simulation report is not canonical JSON: {error}") from error


def _pipeline_options(options: SimulationOptions, dither: DitherMode) -> PipelineOptions:
    return PipelineOptions(
        dither=dither,
        seed=options.seed,
        white_protection=options.white_protection,
        preserve_edges=options.preserve_edges,
        text_mode=options.text_mode,
    )


def _preview_png(width: int, height: int, codes: bytes, palette: Palette) -> bytes:
    colours = {entry.code: entry.preview_rgb for entry in palette.entries}
    rgb = b"".join(bytes(colours[code]) for code in codes)
    return encode_rgb_png(width, height, rgb)


def _model_preview(
    width: int,
    height: int,
    codes: bytes,
    palette: Palette,
    model: OverlapObservationModel,
) -> bytes:
    linear = model.render_linear_rgb(codes, width, height, palette=palette)
    rgb = bytearray(width * height * 3)
    for index, value in enumerate(linear):
        channel = linear_channel_to_srgb(min(1.0, max(0.0, float(value))))
        rgb[index] = min(255, max(0, int(math.floor(channel * 255.0 + 0.5))))
    return encode_rgb_png(width, height, rgb)


def _identity_model() -> OverlapObservationModel:
    kernel = SpatialKernel(1, 1, (1.0,))
    return OverlapObservationModel(
        "s1-identity-1x1-simulation-v1",
        tuple((code, kernel) for code in ALLOWED_CODES),
    )


def _area_weights(
    image: RasterImage,
    palette: Palette,
    profile: GamutProfile,
    options: SimulationOptions,
) -> tuple[array, dict[str, Any]]:
    if image.mode != "RGB":
        raise SimulationError("area-weighted simulation requires mapped RGB input")
    levels = (1 << options.area_weight_lut_bits) - 1
    solver_options = AreaWeightOptions(
        tile_side=2,
        intent=options.mapping.intent,
        cache_entries=min(65536, (levels + 1) ** 3),
    )
    solver = AreaWeightSolver(
        palette,
        profile,
        options=solver_options,
        allow_unqualified_simulation=True,
    )
    result = array("d", [0.0]) * (image.width * image.height * len(ALLOWED_CODES))
    cache: dict[tuple[int, int, int], tuple[float, ...]] = {}
    source = image.pixels
    for pixel in range(image.width * image.height):
        offset = pixel * 3
        key = tuple(
            int(math.floor((source[offset + channel] * levels / 255.0) + 0.5))
            for channel in range(3)
        )
        weights = cache.get(key)
        if weights is None:
            representative = tuple(
                int(math.floor((value * 255.0 / levels) + 0.5)) for value in key
            )
            target_lab = srgb8_to_lab(representative)
            # The rounded canonical sRGB matrix yields white at
            # L*=100.0000039.  Match the mapper's tiny conversion tolerance
            # before passing the value to the strict area solver.
            normalized_lab = (
                min(100.0, max(0.0, target_lab[0])),
                target_lab[1],
                target_lab[2],
            )
            weights = solver.solve(normalized_lab).weights
            cache[key] = weights
        target = pixel * len(ALLOWED_CODES)
        result[target : target + len(ALLOWED_CODES)] = array("d", weights)
    return result, {
        "solver": "g1-discrete-area-weight-solver-v1",
        "profile_id": profile.profile_id,
        "profile_canonical_sha256": profile.canonical_sha256,
        "palette_id": palette.palette_id,
        "palette_canonical_sha256": palette.canonical_sha256,
        "options": solver_options.to_mapping(),
        "tile_side": 2,
        "recipe_space_size": solver.recipe_space_size,
        "target_lut_bits_per_srgb_channel": options.area_weight_lut_bits,
        "target_lut_unique_entries": len(cache),
        "target_lut_approximation": True,
        "physical_code_order": list(ALLOWED_CODES),
    }


def simulate_raster(
    image: RasterImage,
    *,
    palette: Palette | None = None,
    profile: GamutProfile | None = None,
    options: SimulationOptions | None = None,
) -> SimulationResult:
    """Run one bounded software simulation on an even-width raster."""

    if type(image) is not RasterImage or image.width % 2:
        raise SimulationError("simulation input must be an even-width RasterImage")
    selected_palette = reference_palette() if palette is None else palette
    if type(selected_palette) is not Palette:
        raise SimulationError("palette must be Palette or None")
    selected = SimulationOptions() if options is None else options
    if type(selected) is not SimulationOptions:
        raise SimulationError("options must be SimulationOptions or None")
    if selected.mapping.mode is MappingMode.GAMUT_MAP and type(profile) is not GamutProfile:
        raise SimulationError("gamut-map simulation requires a GamutProfile")
    if selected.algorithm in {
        SimulationAlgorithm.AREA_WEIGHTED_ORDERED,
        SimulationAlgorithm.AREA_WEIGHTED_BLUE_NOISE,
    } and selected.mapping.mode is not MappingMode.GAMUT_MAP:
        raise SimulationError("area-weighted algorithms require gamut mapping to be enabled")
    mapping = map_raster(
        image,
        palette=selected_palette if selected.mapping.mode is MappingMode.GAMUT_MAP else None,
        profile=profile if selected.mapping.mode is MappingMode.GAMUT_MAP else None,
        options=selected.mapping,
        allow_unqualified_simulation=True,
    )
    mapped = mapping.mapped_image
    algorithm = selected.algorithm
    protection_options = _pipeline_options(selected, DitherMode.NONE)
    code_constraints = build_protection_constraints(
        mapped,
        palette=selected_palette,
        options=protection_options,
    )
    area_report: Mapping[str, Any] | None = None
    initializer_report: Mapping[str, Any] | None = None
    model = OverlapObservationModel.gaussian_simulation()

    if algorithm in _C2_ALGORITHM:
        quantization = quantize_image(
            mapped,
            palette=selected_palette,
            options=_pipeline_options(selected, _C2_ALGORITHM[algorithm]),
            allow_uncalibrated_palette=True,
        )
        codes = quantization.codes
        halftone_report = quantization.report.to_dict()
        engine = "canonical-c2"
    elif algorithm is SimulationAlgorithm.BLUE_NOISE:
        quantization = quantize_blue_noise(
            mapped,
            palette=selected_palette,
            options=BlueNoiseOptions(seed=selected.seed),
            code_constraints=code_constraints,
        )
        codes = quantization.codes
        halftone_report = quantization.report
        engine = "s1-blue-noise-legacy-nearest-two-baseline"
    elif algorithm in {
        SimulationAlgorithm.AREA_WEIGHTED_ORDERED,
        SimulationAlgorithm.AREA_WEIGHTED_BLUE_NOISE,
    }:
        if type(profile) is not GamutProfile:
            raise SimulationError("area-weighted simulation requires a bound gamut profile")
        weights, area_report = _area_weights(mapped, selected_palette, profile, selected)
        if algorithm is SimulationAlgorithm.AREA_WEIGHTED_ORDERED:
            quantization = quantize_area_weighted_ordered(
                mapped.width,
                mapped.height,
                weights,
                palette=selected_palette,
                seed=selected.seed,
                solver_id="g1-discrete-area-weight-solver-v1",
                code_constraints=code_constraints,
            )
            engine = "g1-area-weights-plus-s1-ordered-bayer"
        else:
            quantization = quantize_area_weighted_blue_noise(
                mapped.width,
                mapped.height,
                weights,
                palette=selected_palette,
                options=BlueNoiseOptions(seed=selected.seed),
                solver_id="g1-discrete-area-weight-solver-v1",
                code_constraints=code_constraints,
            )
            engine = "g1-area-weights-plus-s1-blue-noise"
        codes = quantization.codes
        halftone_report = quantization.report
        area_report = {
            **area_report,
            "weights_canonical_binary64_sha256": halftone_report["area_weights"][
                "canonical_binary64_sha256"
            ],
        }
    else:
        initializer = quantize_image(
            mapped,
            palette=selected_palette,
            options=_pipeline_options(selected, DitherMode.FLOYD_STEINBERG),
            allow_uncalibrated_palette=True,
        )
        initializer_report = initializer.report.to_dict()
        model = (
            _identity_model()
            if algorithm is SimulationAlgorithm.MULTICOLOR_DBS
            else OverlapObservationModel.gaussian_simulation()
        )
        assert selected.budget is not None
        optimized = optimize_multicolor_dbs(
            mapped,
            initializer.codes,
            palette=selected_palette,
            model=model,
            options=DBSOptions(
                seed=selected.seed,
                max_evaluations=selected.budget.max_evaluations,
                max_accepted_moves=selected.budget.max_accepted_moves,
                stagnation_evaluations=selected.budget.stagnation_evaluations,
                time_limit_seconds=None,
            ),
            code_constraints=code_constraints,
        )
        codes = optimized.codes
        halftone_report = optimized.report
        engine = "s1-multicolor-dbs"

    if set(codes).difference(PHYSICAL_COLOR_CODES):
        raise AssertionError("simulation emitted a non-physical colour code")
    if any(
        fixed != UNCONSTRAINED_PHYSICAL_CODE and codes[index] != fixed
        for index, fixed in enumerate(code_constraints)
    ):
        raise AssertionError("simulation output violates a protection constraint")
    frame = pack_pixels(codes, mapped.width, mapped.height)
    validate_frame(frame, mapped.width, mapped.height)
    final_png = _preview_png(mapped.width, mapped.height, codes, selected_palette)
    source_png = mapping.source_preview_png()
    mapped_png = mapping.mapped_preview_png()
    model_png = _model_preview(mapped.width, mapped.height, codes, selected_palette, model)
    counts = {code: 0 for code in ALLOWED_CODES}
    for code in codes:
        counts[code] += 1
    mapping_report = mapping.report.to_dict()
    previews = {
        "source": source_png,
        "mapped": mapped_png,
        "final": final_png,
        "model": model_png,
    }
    report: dict[str, Any] = {
        "schema_version": SIMULATION_REPORT_SCHEMA_VERSION,
        "kind": SIMULATION_REPORT_KIND,
        "dimensions": {"width": mapped.width, "height": mapped.height},
        "source_raster_sha256": hashlib.sha256(image.pixels).hexdigest(),
        "palette": selected_palette.canonical_mapping(),
        "palette_canonical_sha256": selected_palette.canonical_sha256,
        "mapping": {
            "report": mapping_report,
            "report_canonical_sha256": mapping_report["report_integrity"]["canonical_sha256"],
            "mapped_rgb8_sha256": hashlib.sha256(mapped.pixels).hexdigest(),
        },
        "halftone": {
            "algorithm": algorithm.value,
            "engine": engine,
            "seed": selected.seed,
            "budget": None if selected.budget is None else selected.budget.to_mapping(),
            "area_weights": area_report,
            "initializer_report": initializer_report,
            "report": halftone_report,
        },
        "protections": {
            "white": selected.white_protection,
            "edge": selected.preserve_edges,
            "text": selected.text_mode,
            "contract": "canonical-C2-protection-constraints-v1",
            "unconstrained_sentinel": UNCONSTRAINED_PHYSICAL_CODE,
            "constraint_mask_sha256": hashlib.sha256(code_constraints).hexdigest(),
            "locked_pixels": sum(
                value != UNCONSTRAINED_PHYSICAL_CODE
                for value in code_constraints
            ),
            "locked_code_counts": {
                str(code): sum(value == code for value in code_constraints)
                for code in ALLOWED_CODES
            },
        },
        "observation_model": model.metadata(),
        "previews": {
            stage: {
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
                "width": mapped.width,
                "height": mapped.height,
                "semantics": {
                    "source": "server-normalized source monitor rendering",
                    "mapped": "continuous G1 target monitor rendering",
                    "final": "strict rendering from final physical six-code stream",
                    "model": "uncalibrated S1 overlapping optical observation simulation",
                }[stage],
            }
            for stage, payload in previews.items()
        },
        "output": {
            "codes_sha256": hashlib.sha256(codes).hexdigest(),
            "frame_bytes": len(frame),
            "frame_sha256": hashlib.sha256(frame).hexdigest(),
            "frame_fnv1a": f"0x{fnv1a(frame):08X}",
            "usage": [
                {
                    "code": entry.code,
                    "name": entry.name,
                    "count": counts[entry.code],
                    "ratio": counts[entry.code] / len(codes),
                }
                for entry in selected_palette.entries
            ],
        },
        "qualification": {
            "simulation_only": True,
            "formal_upload_authorized": False,
            "hardware_qualified": False,
            "reason_codes": [
                "synthetic_or_untrusted_gamut_characterization",
                "unmeasured_observation_kernels",
                "no_runtime_panel_waveform_temperature_binding",
            ],
            "limitation": SOFT_PROOF_LIMITATION,
        },
        "hardware_tested": False,
        "device_io_performed": False,
    }
    canonical = _canonical_json(report)
    report["report_integrity"] = {
        "canonical_sha256": hashlib.sha256(canonical).hexdigest(),
        "canonical_sha256_scope": SIMULATION_REPORT_HASH_SCOPE,
    }
    validate_simulation_report(report, frame=frame, previews=previews)
    return SimulationResult(
        mapped.width,
        mapped.height,
        frame,
        bytes(codes),
        source_png,
        mapped_png,
        final_png,
        model_png,
        selected_palette,
        report,
    )


def simulate_panel(
    image: RasterImage,
    **kwargs: Any,
) -> SimulationResult:
    if (image.width, image.height) != (WIDTH, HEIGHT):
        raise SimulationError(
            f"panel simulation requires {WIDTH}x{HEIGHT}; got {image.width}x{image.height}"
        )
    result = simulate_raster(image, **kwargs)
    if len(result.frame) != FRAME_BYTES:
        raise AssertionError("panel simulation frame length invariant failed")
    validate_frame(result.frame)
    return result


simulate_panel_image = simulate_panel


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SimulationError(f"{label} must be an object")
    return value


def _verify_integrity(report: Mapping[str, Any]) -> None:
    integrity = _require_mapping(report.get("report_integrity"), "report_integrity")
    if integrity.get("canonical_sha256_scope") != SIMULATION_REPORT_HASH_SCOPE:
        raise SimulationError("simulation report hash scope is invalid")
    unsigned = dict(report)
    del unsigned["report_integrity"]
    expected = hashlib.sha256(_canonical_json(unsigned)).hexdigest()
    if integrity.get("canonical_sha256") != expected:
        raise SimulationError("simulation report integrity hash does not match")


def _verify_subreport_integrity(report: Mapping[str, Any], label: str) -> None:
    integrity = _require_mapping(report.get("report_integrity"), f"{label} integrity")
    digest = integrity.get("canonical_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise SimulationError(f"{label} canonical hash is invalid")
    unsigned = dict(report)
    del unsigned["report_integrity"]
    if hashlib.sha256(_canonical_json(unsigned)).hexdigest() != digest:
        raise SimulationError(f"{label} integrity hash does not match")


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise SimulationError(f"{label} fields differ from the contract")


def _sha256_text(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise SimulationError(f"{label} must be 64 lowercase hex digits")
    return value


def _validate_dbs_proposal_coverage(
    search: Mapping[str, Any],
    *,
    width: int,
    height: int,
    locked_pixels: int,
) -> None:
    coverage = _require_mapping(search.get("coverage"), "DBS proposal coverage")
    _exact_keys(
        coverage,
        {
            "contract",
            "unlocked_pixels",
            "unique_primary_pixels",
            "unique_touched_pixels",
            "primary_coverage_ratio",
            "proposal_trace_sha256",
            "proposal_trace_encoding",
            "proposal_trace_samples",
            "horizontal_split",
            "tile_grid",
        },
        "DBS proposal coverage",
    )
    if coverage.get("contract") != DBS_COVERAGE_CONTRACT:
        raise SimulationError("DBS proposal coverage contract is invalid")

    evaluations = search.get("evaluations")
    proposals = search.get("proposals")
    if (
        type(evaluations) is not int
        or evaluations < 0
        or type(proposals) is not int
        or not 0 <= proposals <= evaluations
    ):
        raise SimulationError("DBS proposal/evaluation counts are invalid")
    expected_unlocked = width * height - locked_pixels
    unlocked = coverage.get("unlocked_pixels")
    unique_primary = coverage.get("unique_primary_pixels")
    unique_touched = coverage.get("unique_touched_pixels")
    if type(unlocked) is not int or unlocked != expected_unlocked:
        raise SimulationError("DBS unlocked pixel count differs from protections")
    if (
        type(unique_primary) is not int
        or type(unique_touched) is not int
        or not 0 <= unique_primary <= min(unlocked, proposals)
        or not unique_primary <= unique_touched <= min(unlocked, proposals * 2)
    ):
        raise SimulationError("DBS unique proposal coverage counts are invalid")
    ratio = coverage.get("primary_coverage_ratio")
    expected_ratio = unique_primary / unlocked if unlocked else 0.0
    if (
        isinstance(ratio, bool)
        or not isinstance(ratio, (int, float))
        or not math.isfinite(float(ratio))
        or float(ratio) != expected_ratio
    ):
        raise SimulationError("DBS primary coverage ratio is invalid")
    trace_sha256 = _sha256_text(
        coverage.get("proposal_trace_sha256"), "DBS proposal trace SHA-256"
    )
    if coverage.get("proposal_trace_encoding") != DBS_PROPOSAL_TRACE_ENCODING:
        raise SimulationError("DBS proposal trace encoding is invalid")

    samples = coverage.get("proposal_trace_samples")
    if not isinstance(samples, list) or len(samples) != min(32, proposals):
        raise SimulationError("DBS proposal trace samples are invalid")
    sample_digest = hashlib.sha256()
    no_partner = 0xFFFFFFFFFFFFFFFF
    for ordinal, raw_sample in enumerate(samples, start=1):
        sample = _require_mapping(raw_sample, "DBS proposal trace sample")
        _exact_keys(
            sample,
            {"proposal", "operation", "pixels"},
            "DBS proposal trace sample",
        )
        operation = sample.get("operation")
        pixels = sample.get("pixels")
        expected_length = 1 if operation == "single-recolour" else 2
        if (
            sample.get("proposal") != ordinal
            or operation not in {"single-recolour", "pair-swap"}
            or not isinstance(pixels, list)
            or len(pixels) != expected_length
            or any(type(pixel) is not int or not 0 <= pixel < width * height for pixel in pixels)
            or (len(pixels) == 2 and pixels[0] == pixels[1])
        ):
            raise SimulationError("DBS proposal trace sample is inconsistent")
        partner = pixels[1] if len(pixels) == 2 else no_partner
        sample_digest.update(
            struct.pack(">QBQQ", ordinal, int(len(pixels) == 2), pixels[0], partner)
        )
    if proposals <= 32 and sample_digest.hexdigest() != trace_sha256:
        raise SimulationError("DBS complete proposal samples do not match trace SHA-256")

    horizontal = _require_mapping(
        coverage.get("horizontal_split"), "DBS horizontal proposal split"
    )
    _exact_keys(
        horizontal,
        {"split_x", "left_proposals", "right_proposals"},
        "DBS horizontal proposal split",
    )
    left = horizontal.get("left_proposals")
    right = horizontal.get("right_proposals")
    if (
        horizontal.get("split_x") != width // 2
        or type(left) is not int
        or type(right) is not int
        or left < 0
        or right < 0
        or left + right != proposals
    ):
        raise SimulationError("DBS horizontal proposal split is inconsistent")

    tile_grid = _require_mapping(coverage.get("tile_grid"), "DBS proposal tile grid")
    _exact_keys(
        tile_grid,
        {
            "contract",
            "columns",
            "rows",
            "panel_1024x600_exact_64x60",
            "exact_tile_width",
            "exact_tile_height",
            "proposal_counts",
            "nonempty_tiles",
            "empty_tiles",
            "minimum_proposals",
            "maximum_proposals",
        },
        "DBS proposal tile grid",
    )
    columns = min(16, width)
    rows = min(10, height)
    panel_grid = width == 1024 and height == 600
    counts = tile_grid.get("proposal_counts")
    if (
        tile_grid.get("contract") != DBS_TILE_GRID_CONTRACT
        or tile_grid.get("columns") != columns
        or tile_grid.get("rows") != rows
        or tile_grid.get("panel_1024x600_exact_64x60") is not panel_grid
        or tile_grid.get("exact_tile_width") != (64 if panel_grid else None)
        or tile_grid.get("exact_tile_height") != (60 if panel_grid else None)
        or not isinstance(counts, list)
        or len(counts) != columns * rows
        or any(type(value) is not int or value < 0 for value in counts)
        or sum(counts) != proposals
    ):
        raise SimulationError("DBS proposal tile grid is inconsistent")
    nonempty = sum(value > 0 for value in counts)
    if (
        tile_grid.get("nonempty_tiles") != nonempty
        or tile_grid.get("empty_tiles") != len(counts) - nonempty
        or tile_grid.get("minimum_proposals") != min(counts)
        or tile_grid.get("maximum_proposals") != max(counts)
    ):
        raise SimulationError("DBS proposal tile statistics are inconsistent")


def validate_simulation_report(
    report: Mapping[str, Any],
    *,
    frame: bytes | bytearray | memoryview | None = None,
    previews: Mapping[str, bytes] | None = None,
) -> None:
    """Validate report identity and, when supplied, every artifact byte."""

    if not isinstance(report, Mapping):
        raise SimulationError("simulation report must be an object")
    _exact_keys(
        report,
        {
            "schema_version",
            "kind",
            "dimensions",
            "source_raster_sha256",
            "palette",
            "palette_canonical_sha256",
            "mapping",
            "halftone",
            "protections",
            "observation_model",
            "previews",
            "output",
            "qualification",
            "hardware_tested",
            "device_io_performed",
            "report_integrity",
        },
        "simulation report",
    )
    if report.get("schema_version") != SIMULATION_REPORT_SCHEMA_VERSION or type(report.get("schema_version")) is not int:
        raise SimulationError("simulation report schema_version is invalid")
    if report.get("kind") != SIMULATION_REPORT_KIND:
        raise SimulationError("simulation report kind is invalid")
    if report.get("hardware_tested") is not False or report.get("device_io_performed") is not False:
        raise SimulationError("simulation report cannot claim hardware/device execution")
    qualification = _require_mapping(report.get("qualification"), "qualification")
    if (
        qualification.get("simulation_only") is not True
        or qualification.get("formal_upload_authorized") is not False
        or qualification.get("hardware_qualified") is not False
    ):
        raise SimulationError("simulation qualification is not fail-closed")
    _verify_integrity(report)
    dimensions = _require_mapping(report.get("dimensions"), "dimensions")
    _exact_keys(dimensions, {"width", "height"}, "simulation dimensions")
    width, height = dimensions.get("width"), dimensions.get("height")
    if type(width) is not int or width <= 0 or type(height) is not int or height <= 0 or width % 2:
        raise SimulationError("simulation dimensions are invalid")
    try:
        palette = palette_from_mapping(_require_mapping(report.get("palette"), "palette"))
    except ValueError as error:
        raise SimulationError(f"simulation palette is invalid: {error}") from error
    if report.get("palette_canonical_sha256") != palette.canonical_sha256:
        raise SimulationError("simulation palette canonical hash does not match")
    source_hash = _sha256_text(
        report.get("source_raster_sha256"), "simulation source raster SHA-256"
    )
    mapping = _require_mapping(report.get("mapping"), "mapping")
    _exact_keys(
        mapping,
        {"report", "report_canonical_sha256", "mapped_rgb8_sha256"},
        "simulation mapping wrapper",
    )
    mapping_report = _require_mapping(mapping.get("report"), "mapping report")
    validate_mapping_report(mapping_report)
    if mapping.get("report_canonical_sha256") != mapping_report["report_integrity"]["canonical_sha256"]:
        raise SimulationError("mapping report identity does not match")
    mapping_source = _require_mapping(
        mapping_report.get("source_raster"), "mapping source raster"
    )
    mapping_output = _require_mapping(
        mapping_report.get("mapped_raster"), "mapping mapped raster"
    )
    mapping_profile = mapping_report.get("profile")
    if mapping_profile is None:
        if mapping_output.get("profile_canonical_sha256") is not None:
            raise SimulationError("legacy mapping output unexpectedly carries a profile")
    else:
        mapping_profile = _require_mapping(mapping_profile, "mapping profile")
        if (
            mapping_profile.get("canonical_sha256")
            != mapping_output.get("profile_canonical_sha256")
            or mapping_profile.get("palette_id") != palette.palette_id
            or mapping_profile.get("palette_canonical_sha256")
            != palette.canonical_sha256
        ):
            raise SimulationError("mapping profile is not bound to the simulation palette")
    if mapping_source.get("sha256") != source_hash:
        raise SimulationError("mapping source raster identity does not match")
    if (
        mapping_source.get("width") != width
        or mapping_source.get("height") != height
        or mapping_output.get("width") != width
        or mapping_output.get("height") != height
    ):
        raise SimulationError("mapping raster dimensions do not match the simulation")
    halftone = _require_mapping(report.get("halftone"), "halftone")
    _exact_keys(
        halftone,
        {
            "algorithm",
            "engine",
            "seed",
            "budget",
            "area_weights",
            "initializer_report",
            "report",
        },
        "simulation halftone wrapper",
    )
    try:
        algorithm = SimulationAlgorithm(halftone.get("algorithm"))
    except (TypeError, ValueError) as error:
        raise SimulationError("halftone algorithm is invalid") from error
    if type(halftone.get("seed")) is not int or not 0 <= halftone["seed"] <= 0xFFFFFFFF:
        raise SimulationError("halftone seed is not a uint32")
    halftone_report = _require_mapping(halftone.get("report"), "halftone report")
    _verify_subreport_integrity(halftone_report, "halftone report")
    mapped_hash = _sha256_text(
        mapping.get("mapped_rgb8_sha256"), "mapped RGB8 identity"
    )
    reported_input_hash = None
    if isinstance(halftone_report.get("input_raster"), Mapping):
        reported_input_hash = halftone_report["input_raster"].get("sha256")
    elif "input_raster_sha256" in halftone_report:
        reported_input_hash = halftone_report.get("input_raster_sha256")
    elif isinstance(halftone_report.get("input"), Mapping):
        reported_input_hash = halftone_report["input"].get("raster_sha256")
    if reported_input_hash is not None and reported_input_hash != mapped_hash:
        raise SimulationError("halftone input does not match the mapped RGB8 raster")
    output = _require_mapping(report.get("output"), "output")
    _exact_keys(
        output,
        {"codes_sha256", "frame_bytes", "frame_sha256", "frame_fnv1a", "usage"},
        "simulation output",
    )
    output_codes_hash = _sha256_text(
        output.get("codes_sha256"), "simulation output code SHA-256"
    )
    _sha256_text(output.get("frame_sha256"), "simulation output frame SHA-256")
    if output.get("frame_bytes") != width * height // 2:
        raise SimulationError("simulation output frame byte count is invalid")
    if (
        not isinstance(output.get("frame_fnv1a"), str)
        or len(output["frame_fnv1a"]) != 10
        or not output["frame_fnv1a"].startswith("0x")
    ):
        raise SimulationError("simulation output FNV-1a is invalid")

    expected_engine = {
        SimulationAlgorithm.NONE: "canonical-c2",
        SimulationAlgorithm.FLOYD_STEINBERG: "canonical-c2",
        SimulationAlgorithm.ATKINSON: "canonical-c2",
        SimulationAlgorithm.ORDERED_BAYER: "canonical-c2",
        SimulationAlgorithm.HASHED_THRESHOLD: "canonical-c2",
        SimulationAlgorithm.BLUE_NOISE: "s1-blue-noise-legacy-nearest-two-baseline",
        SimulationAlgorithm.AREA_WEIGHTED_ORDERED: "g1-area-weights-plus-s1-ordered-bayer",
        SimulationAlgorithm.AREA_WEIGHTED_BLUE_NOISE: "g1-area-weights-plus-s1-blue-noise",
        SimulationAlgorithm.MULTICOLOR_DBS: "s1-multicolor-dbs",
        SimulationAlgorithm.OVERLAP_AWARE_DBS: "s1-multicolor-dbs",
    }[algorithm]
    if halftone.get("engine") != expected_engine:
        raise SimulationError("halftone engine does not match the selected algorithm")

    protections = _require_mapping(report.get("protections"), "protections")
    _exact_keys(
        protections,
        {
            "white",
            "edge",
            "text",
            "contract",
            "unconstrained_sentinel",
            "constraint_mask_sha256",
            "locked_pixels",
            "locked_code_counts",
        },
        "simulation protections",
    )
    if any(type(protections.get(key)) is not bool for key in ("white", "edge", "text")):
        raise SimulationError("simulation protection switches must be boolean")
    if (
        protections.get("contract") != "canonical-C2-protection-constraints-v1"
        or protections.get("unconstrained_sentinel") != UNCONSTRAINED_PHYSICAL_CODE
    ):
        raise SimulationError("simulation protection contract is invalid")
    constraint_hash = _sha256_text(
        protections.get("constraint_mask_sha256"), "protection mask SHA-256"
    )
    locked_pixels = protections.get("locked_pixels")
    if type(locked_pixels) is not int or not 0 <= locked_pixels <= width * height:
        raise SimulationError("protected pixel count is invalid")
    locked_counts = _require_mapping(
        protections.get("locked_code_counts"), "protected code counts"
    )
    if set(locked_counts) != {str(code) for code in ALLOWED_CODES} or any(
        type(value) is not int or value < 0 for value in locked_counts.values()
    ):
        raise SimulationError("protected code counts are invalid")
    if sum(locked_counts.values()) != locked_pixels:
        raise SimulationError("protected code counts do not sum to locked_pixels")
    expected_constraint_evidence = {
        "provided": True,
        "locked_pixels": locked_pixels,
        "mask_sha256": constraint_hash,
        "unconstrained_sentinel": UNCONSTRAINED_PHYSICAL_CODE,
    }

    c2_algorithms = set(_C2_ALGORITHM)
    if algorithm in c2_algorithms:
        if halftone_report.get("kind") != "mf1750-color-quantization-report":
            raise SimulationError("C2 algorithm has the wrong halftone report kind")
        if (
            halftone_report.get("width") != width
            or halftone_report.get("height") != height
            or halftone_report.get("frame_bytes") != output.get("frame_bytes")
            or halftone_report.get("frame_sha256") != output.get("frame_sha256")
            or halftone_report.get("frame_fnv1a") != output.get("frame_fnv1a")
        ):
            raise SimulationError("C2 halftone output differs from the simulation frame")
        c2_options = _require_mapping(
            halftone_report.get("options"), "C2 halftone options"
        )
        if (
            c2_options.get("requested_dither") != algorithm.value
            or c2_options.get("seed") != halftone.get("seed")
            or c2_options.get("white_protection") is not protections.get("white")
            or c2_options.get("requested_edge_preservation") is not protections.get("edge")
            or c2_options.get("text_mode") is not protections.get("text")
        ):
            raise SimulationError("C2 options differ from the requested simulation controls")
        c2_palette = _require_mapping(
            halftone_report.get("palette"), "C2 halftone palette"
        )
        if c2_palette.get("canonical_sha256") != palette.canonical_sha256:
            raise SimulationError("C2 palette differs from the simulation palette")
        if (
            halftone.get("budget") is not None
            or halftone.get("area_weights") is not None
            or halftone.get("initializer_report") is not None
        ):
            raise SimulationError("C2 wrapper contains inapplicable S1 evidence")
    elif algorithm in {
        SimulationAlgorithm.BLUE_NOISE,
        SimulationAlgorithm.AREA_WEIGHTED_ORDERED,
        SimulationAlgorithm.AREA_WEIGHTED_BLUE_NOISE,
    }:
        expected_kind = {
            SimulationAlgorithm.BLUE_NOISE: "mf1750-blue-noise-quantization-report",
            SimulationAlgorithm.AREA_WEIGHTED_ORDERED: "mf1750-area-weighted-ordered-quantization-report",
            SimulationAlgorithm.AREA_WEIGHTED_BLUE_NOISE: "mf1750-area-weighted-blue-noise-quantization-report",
        }[algorithm]
        if halftone_report.get("kind") != expected_kind:
            raise SimulationError("blue-noise report kind differs from the algorithm")
        if (
            halftone_report.get("width") != width
            or halftone_report.get("height") != height
            or halftone_report.get("codes_sha256") != output_codes_hash
            or halftone_report.get("seed") != halftone.get("seed")
        ):
            raise SimulationError("blue-noise output identity differs from the simulation")
        blue_palette = _require_mapping(
            halftone_report.get("palette"), "blue-noise palette"
        )
        if blue_palette.get("canonical_sha256") != palette.canonical_sha256:
            raise SimulationError("blue-noise palette differs from the simulation palette")
        if halftone_report.get("code_constraints") != expected_constraint_evidence:
            raise SimulationError("blue-noise protection evidence differs from the simulation")
        if halftone.get("budget") is not None or halftone.get("initializer_report") is not None:
            raise SimulationError("blue-noise wrapper contains an inapplicable budget/initializer")
        expected_algorithm = {
            SimulationAlgorithm.BLUE_NOISE: "legacy-nearest-two-ciede2000-with-void-and-cluster-v1",
            SimulationAlgorithm.AREA_WEIGHTED_ORDERED: AREA_WEIGHTED_ORDERED_ALGORITHM,
            SimulationAlgorithm.AREA_WEIGHTED_BLUE_NOISE: AREA_WEIGHTED_BLUE_NOISE_ALGORITHM,
        }[algorithm]
        if halftone_report.get("algorithm") != expected_algorithm:
            raise SimulationError("halftone report algorithm identity is invalid")
        if algorithm is SimulationAlgorithm.BLUE_NOISE:
            if halftone.get("area_weights") is not None:
                raise SimulationError("legacy blue noise cannot claim G1 area weights")
            legacy_weights = _require_mapping(
                halftone_report.get("mixing_weights"), "legacy blue-noise weights"
            )
            if (
                legacy_weights.get("nearest_two_delta_e_ratio_used") is not True
                or legacy_weights.get("g1_six_colour_area_weight_contract") is not False
                or legacy_weights.get("recommended_for_new_area_weighted_pipeline")
                is not False
            ):
                raise SimulationError("legacy blue-noise weight semantics are invalid")
            threshold = _require_mapping(
                halftone_report.get("threshold_map"), "blue-noise threshold map"
            )
            _verify_subreport_integrity(threshold, "blue-noise threshold map")
            if (
                threshold.get("algorithm") != "deterministic-void-and-cluster-ranked-threshold-v1"
                or threshold.get("seed") != halftone.get("seed")
            ):
                raise SimulationError("legacy blue-noise threshold identity is invalid")
        elif algorithm is SimulationAlgorithm.AREA_WEIGHTED_BLUE_NOISE:
            thresholds = halftone_report.get("threshold_maps")
            if not isinstance(thresholds, list) or len(thresholds) != len(ALLOWED_CODES):
                raise SimulationError("area-weighted blue noise requires six threshold maps")
            for index, threshold_value in enumerate(thresholds):
                _verify_subreport_integrity(
                    _require_mapping(threshold_value, f"threshold map {index}"),
                    f"threshold map {index}",
                )
            assignment = _require_mapping(
                halftone_report.get("assignment"), "blue-noise area assignment"
            )
            if (
                assignment.get("method") != "categorical Gumbel-max"
                or assignment.get("decorrelated_channels") is not True
                or assignment.get("threshold_algorithm")
                != "deterministic-void-and-cluster-ranked-threshold-v1"
                or assignment.get("channel_seeds")
                != [threshold["seed"] for threshold in thresholds]
            ):
                raise SimulationError("area blue-noise assignment evidence is invalid")
        else:
            assignment = _require_mapping(
                halftone_report.get("assignment"), "ordered area assignment"
            )
            _exact_keys(
                assignment,
                {
                    "method",
                    "threshold_algorithm",
                    "period_width",
                    "period_height",
                    "rank_phase",
                },
                "ordered area assignment",
            )
            if (
                assignment.get("method") != "categorical inverse CDF"
                or assignment.get("threshold_algorithm")
                != "phase-seeded-bayer-8x8-rank-map-v1"
                or assignment.get("period_width") != 8
                or assignment.get("period_height") != 8
                or assignment.get("rank_phase") != (halftone["seed"] & 63)
            ):
                raise SimulationError("ordered area threshold algorithm is invalid")
        if algorithm is not SimulationAlgorithm.BLUE_NOISE:
            area_evidence = _require_mapping(
                halftone.get("area_weights"), "G1 area-weight evidence"
            )
            _exact_keys(
                area_evidence,
                {
                    "solver",
                    "profile_id",
                    "profile_canonical_sha256",
                    "palette_id",
                    "palette_canonical_sha256",
                    "options",
                    "tile_side",
                    "recipe_space_size",
                    "target_lut_bits_per_srgb_channel",
                    "target_lut_unique_entries",
                    "target_lut_approximation",
                    "physical_code_order",
                    "weights_canonical_binary64_sha256",
                },
                "G1 area-weight evidence",
            )
            if mapping_profile is None:
                raise SimulationError("area-weight evidence requires a mapped profile")
            area_options = _require_mapping(
                area_evidence.get("options"), "G1 area solver options"
            )
            lut_bits = area_evidence.get("target_lut_bits_per_srgb_channel")
            if (
                area_evidence.get("solver") != "g1-discrete-area-weight-solver-v1"
                or area_evidence.get("profile_id") != mapping_profile.get("id")
                or area_evidence.get("profile_canonical_sha256")
                != mapping_profile.get("canonical_sha256")
                or area_evidence.get("palette_id") != palette.palette_id
                or area_evidence.get("palette_canonical_sha256")
                != palette.canonical_sha256
                or area_evidence.get("tile_side") != 2
                or area_evidence.get("recipe_space_size") != 126
                or area_evidence.get("physical_code_order") != list(ALLOWED_CODES)
                or area_evidence.get("target_lut_approximation") is not True
                or type(lut_bits) is not int
                or not 2 <= lut_bits <= 6
                or area_options.get("tile_side") != 2
                or area_options.get("intent")
                != mapping_report["options"]["intent"]
                or area_options.get("cache_entries")
                != min(65536, (1 << lut_bits) ** 3)
            ):
                raise SimulationError("G1 area-weight evidence is internally inconsistent")
            expected_area_options = {
                "tile_side": 2,
                "intent": mapping_report["options"]["intent"],
                "delta_e_weight": 1.0,
                "grain_weight": 0.025,
                "color_count_weight": 0.01,
                "max_colors": 6,
                "cache_entries": min(65536, (1 << lut_bits) ** 3),
            }
            if area_options != expected_area_options:
                raise SimulationError("G1 area solver options differ from the contract")
            unique_targets = area_evidence.get("target_lut_unique_entries")
            if (
                type(unique_targets) is not int
                or not 0 < unique_targets <= (1 << lut_bits) ** 3
            ):
                raise SimulationError("G1 area-weight LUT evidence is invalid")
            nested_weights = _require_mapping(
                halftone_report.get("area_weights"), "halftone area weights"
            )
            _exact_keys(
                nested_weights,
                {
                    "solver_id",
                    "contract",
                    "canonical_binary64_sha256",
                    "canonical_binary64_scope",
                    "nearest_two_delta_e_ratio_used",
                },
                "halftone area weights",
            )
            if (
                nested_weights.get("solver_id") != area_evidence.get("solver")
                or nested_weights.get("contract")
                != "six finite non-negative weights per pixel; sum=1"
                or nested_weights.get("canonical_binary64_scope")
                != "top-left row-major, physical code order, IEEE-754 binary64 big-endian"
                or nested_weights.get("nearest_two_delta_e_ratio_used") is not False
                or nested_weights.get("canonical_binary64_sha256")
                != area_evidence.get("weights_canonical_binary64_sha256")
            ):
                raise SimulationError("area-weight assignment differs from its G1 evidence")
            _sha256_text(
                nested_weights.get("canonical_binary64_sha256"),
                "area-weight binary64 SHA-256",
            )
    else:
        if halftone_report.get("kind") != "mf1750-overlap-aware-halftone-optimization-report":
            raise SimulationError("DBS report kind differs from the algorithm")
        dbs_dimensions = _require_mapping(
            halftone_report.get("dimensions"), "DBS dimensions"
        )
        dbs_output = _require_mapping(halftone_report.get("output"), "DBS output")
        dbs_input = _require_mapping(halftone_report.get("input"), "DBS input")
        dbs_search = _require_mapping(halftone_report.get("search"), "DBS search")
        dbs_schema = halftone_report.get("schema_version")
        if type(dbs_schema) is not int or dbs_schema not in {
            1,
            DBS_REPORT_SCHEMA_VERSION,
        }:
            raise SimulationError("DBS report schema_version is unsupported")
        if dbs_schema == 1:
            if "coverage" in dbs_search:
                raise SimulationError("legacy DBS report unexpectedly carries v2 coverage")
        else:
            _validate_dbs_proposal_coverage(
                dbs_search,
                width=width,
                height=height,
                locked_pixels=locked_pixels,
            )
        if (
            halftone_report.get("algorithm") != DBS_ALGORITHM
            or dbs_dimensions != {"width": width, "height": height}
            or dbs_output.get("codes_sha256") != output_codes_hash
            or dbs_input.get("raster_sha256") != mapped_hash
            or dbs_search.get("seed") != halftone.get("seed")
            or dbs_search.get("code_constraints") != expected_constraint_evidence
        ):
            raise SimulationError("DBS evidence differs from the simulation output/input")
        if halftone.get("area_weights") is not None:
            raise SimulationError("DBS cannot claim G1 area-weight evidence")
        budget = _require_mapping(halftone.get("budget"), "DBS wrapper budget")
        if budget.get("wall_clock_deadline_used") is not False:
            raise SimulationError("application DBS must not use a wall-clock deadline")
        dbs_budget = _require_mapping(halftone_report.get("budget"), "DBS report budget")
        for key in ("max_evaluations", "max_accepted_moves", "stagnation_evaluations"):
            if dbs_budget.get(key) != budget.get(key):
                raise SimulationError("DBS report budget differs from the request")
        if dbs_budget.get("time_limit_seconds") is not None:
            raise SimulationError("application DBS report enabled a wall-clock deadline")
        initializer = _require_mapping(
            halftone.get("initializer_report"), "DBS initializer report"
        )
        _verify_subreport_integrity(initializer, "DBS initializer report")
        if (
            initializer.get("kind") != "mf1750-color-quantization-report"
            or initializer.get("width") != width
            or initializer.get("height") != height
            or initializer.get("frame_sha256") != dbs_input.get("initial_frame_sha256")
        ):
            raise SimulationError("DBS initializer differs from its optimization input")
        dbs_palette = _require_mapping(
            halftone_report.get("palette"), "DBS palette"
        )
        initializer_palette = _require_mapping(
            initializer.get("palette"), "DBS initializer palette"
        )
        initializer_input = _require_mapping(
            initializer.get("input_raster"), "DBS initializer input"
        )
        initializer_options = _require_mapping(
            initializer.get("options"), "DBS initializer options"
        )
        if (
            dbs_palette.get("canonical_sha256") != palette.canonical_sha256
            or initializer_palette.get("canonical_sha256")
            != palette.canonical_sha256
            or initializer_input.get("sha256") != mapped_hash
            or initializer_options.get("requested_dither")
            != DitherMode.FLOYD_STEINBERG.value
            or initializer_options.get("seed") != halftone.get("seed")
            or initializer_options.get("white_protection")
            is not protections.get("white")
            or initializer_options.get("requested_edge_preservation")
            is not protections.get("edge")
            or initializer_options.get("text_mode") is not protections.get("text")
        ):
            raise SimulationError("DBS initializer/palette/options are inconsistent")

    expected_model = (
        _identity_model().metadata()
        if algorithm is SimulationAlgorithm.MULTICOLOR_DBS
        else OverlapObservationModel.gaussian_simulation().metadata()
    )
    if report.get("observation_model") != expected_model:
        raise SimulationError("observation model differs from the selected algorithm")
    if algorithm in {
        SimulationAlgorithm.MULTICOLOR_DBS,
        SimulationAlgorithm.OVERLAP_AWARE_DBS,
    } and halftone_report.get("observation_model") != expected_model:
        raise SimulationError("DBS subreport observation model differs from the simulation")

    usage = output.get("usage")
    if not isinstance(usage, list) or len(usage) != len(palette.entries):
        raise SimulationError("simulation usage table is invalid")
    for item, entry in zip(usage, palette.entries):
        if not isinstance(item, Mapping):
            raise SimulationError("simulation usage entry must be an object")
        _exact_keys(item, {"code", "name", "count", "ratio"}, "usage entry")
        count = item.get("count")
        if (
            item.get("code") != entry.code
            or item.get("name") != entry.name
            or type(count) is not int
            or count < 0
            or item.get("ratio") != count / (width * height)
        ):
            raise SimulationError("simulation usage entry is inconsistent")
    if sum(item["count"] for item in usage) != width * height:
        raise SimulationError("simulation usage counts do not cover the raster")

    codes: bytes | None = None
    if frame is not None:
        raw_frame = bytes(validate_frame(frame, width, height))
        if len(raw_frame) != output.get("frame_bytes"):
            raise SimulationError("simulation frame byte count does not match")
        if hashlib.sha256(raw_frame).hexdigest() != output.get("frame_sha256"):
            raise SimulationError("simulation frame SHA-256 does not match")
        if f"0x{fnv1a(raw_frame):08X}" != output.get("frame_fnv1a"):
            raise SimulationError("simulation frame FNV-1a does not match")
        codes = unpack_pixels(raw_frame, width, height)
        if hashlib.sha256(codes).hexdigest() != output.get("codes_sha256"):
            raise SimulationError("simulation code stream SHA-256 does not match")
        expected_final = _preview_png(width, height, codes, palette)
        actual_counts = {code: codes.count(code) for code in ALLOWED_CODES}
        if any(
            item["count"] != actual_counts[item["code"]]
            for item in usage
        ):
            raise SimulationError("simulation usage counts differ from the frame")
    else:
        expected_final = None
    preview_report = _require_mapping(report.get("previews"), "previews")
    if set(preview_report) != {"source", "mapped", "final", "model"}:
        raise SimulationError("simulation preview stages differ from the contract")
    expected_semantics = {
        "source": "server-normalized source monitor rendering",
        "mapped": "continuous G1 target monitor rendering",
        "final": "strict rendering from final physical six-code stream",
        "model": "uncalibrated S1 overlapping optical observation simulation",
    }
    for stage, value in preview_report.items():
        metadata = _require_mapping(value, f"preview {stage}")
        _exact_keys(
            metadata,
            {"sha256", "bytes", "width", "height", "semantics"},
            f"preview {stage}",
        )
        _sha256_text(metadata.get("sha256"), f"preview {stage} SHA-256")
        if (
            type(metadata.get("bytes")) is not int
            or metadata["bytes"] <= 0
            or metadata.get("width") != width
            or metadata.get("height") != height
            or metadata.get("semantics") != expected_semantics[stage]
        ):
            raise SimulationError(f"preview {stage} metadata is inconsistent")
    if previews is not None:
        if set(previews) != set(preview_report):
            raise SimulationError("supplied preview stages differ from the report")
        for stage, payload in previews.items():
            raw = bytes(payload)
            metadata = _require_mapping(preview_report[stage], f"preview {stage}")
            if len(raw) != metadata.get("bytes") or hashlib.sha256(raw).hexdigest() != metadata.get("sha256"):
                raise SimulationError(f"preview {stage} bytes do not match the report")
        if expected_final is not None and bytes(previews["final"]) != expected_final:
            raise SimulationError("final preview is not rendered from the frame code stream")


__all__ = [
    "SIMULATION_REPORT_HASH_SCOPE",
    "SIMULATION_REPORT_KIND",
    "SIMULATION_REPORT_SCHEMA_VERSION",
    "SOFT_PROOF_LIMITATION",
    "SimulationAlgorithm",
    "SimulationBudget",
    "SimulationError",
    "SimulationOptions",
    "SimulationResult",
    "simulate_panel",
    "simulate_panel_image",
    "simulate_raster",
    "validate_simulation_report",
]
