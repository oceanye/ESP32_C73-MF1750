"""Offline six-primary area-mixing analysis for MF-1750.

The panel's formal frame contract remains six colours.  This module predicts
spatial mixtures by averaging calibrated tristimulus values in CIE XYZ, ranks
fixed-size tile recipes with CIEDE2000, and can render a repeated tile as a
canonical frame.  It deliberately contains no device, network, serial,
waveform, voltage, or refresh functionality.

Predictions are only first-order optical estimates.  They are not measured
panel colours and must not be promoted to measurements in Stage D/E records.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Iterator, Mapping, Sequence, Tuple

from host.color_pipeline import (
    Palette,
    PaletteError,
    delta_e_ciede2000,
    lab_to_srgb8,
    palette_from_mapping,
    srgb8_to_lab,
)
from host.color_pipeline.color import Lab, lab_to_xyz, xyz_to_lab
from host.epd_frame import HEIGHT, PHYSICAL_COLOR_CODES, WIDTH, pack_pixels, validate_frame

from .offline import COLOR_NAME_BY_CODE, COLOR_ORDER, frame_identity


AREA_MIX_SCHEMA_VERSION = 1
AREA_MIX_MODEL_VERSION = "xyz-area-v1"
AREA_MIX_LAYOUT_VERSION = "bayer-threshold-interval-v1"
AREA_MIX_ANALYSIS_ID_SCOPE = (
    "canonical UTF-8 JSON of schema/model/layout versions, formal color order, "
    "palette hash, target Lab, input space, tile side, candidate counts and tile codes"
)
AREA_MIX_TILE_SHA256_SCOPE = "row-major tile; one byte per pixel containing a formal color code"
SUPPORTED_LAB_CHROMA_COMPONENT_LIMIT = 200.0
SUPPORTED_TILE_SIDES = (2, 4)
DEFAULT_TILE_SIDE = 4
DEFAULT_RESULT_LIMIT = 8
MAX_RESULT_LIMIT = 32


class AreaMixError(ValueError):
    """Raised when an offline area-mixing request violates its contract."""


def _validated_lab(values: Sequence[float], label: str) -> Lab:
    try:
        length = len(values)
    except TypeError as error:
        raise AreaMixError(f"{label} must contain exactly three components") from error
    if length != 3:
        raise AreaMixError(f"{label} must contain exactly three components")
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        for value in values
    ):
        raise AreaMixError(f"{label} components must be numeric and not boolean")
    result = tuple(float(value) for value in values)
    if not all(math.isfinite(value) for value in result):
        raise AreaMixError(f"{label} components must be finite")
    if not 0.0 <= result[0] <= 100.0:
        raise AreaMixError(f"{label} lightness must be in [0, 100]")
    if any(abs(value) > SUPPORTED_LAB_CHROMA_COMPONENT_LIMIT for value in result[1:]):
        raise AreaMixError(
            f"{label} a* and b* must be in "
            f"[-{SUPPORTED_LAB_CHROMA_COMPONENT_LIMIT:g}, "
            f"{SUPPORTED_LAB_CHROMA_COMPONENT_LIMIT:g}]"
        )
    try:
        xyz = lab_to_xyz(result)
    except (ArithmeticError, ValueError) as error:
        raise AreaMixError(f"{label} cannot be converted safely to CIE XYZ") from error
    if not all(math.isfinite(value) for value in xyz):
        raise AreaMixError(f"{label} converts to non-finite CIE XYZ")
    return result  # type: ignore[return-value]


def _tile_side(value: int) -> int:
    if type(value) is not int or value not in SUPPORTED_TILE_SIDES:
        raise AreaMixError(f"tile_side must be one of {list(SUPPORTED_TILE_SIDES)}")
    return value


def _result_limit(value: int) -> int:
    if type(value) is not int or not 1 <= value <= MAX_RESULT_LIMIT:
        raise AreaMixError(f"limit must be an integer in [1, {MAX_RESULT_LIMIT}]")
    return value


def _compositions(total: int, parts: int, prefix: Tuple[int, ...] = ()) -> Iterator[Tuple[int, ...]]:
    """Yield weak integer compositions in a stable lexicographic order."""

    if parts == 1:
        yield prefix + (total,)
        return
    for value in range(total + 1):
        yield from _compositions(total - value, parts - 1, prefix + (value,))


_BAYER = {
    2: (
        (0, 2),
        (3, 1),
    ),
    4: (
        (0, 8, 2, 10),
        (12, 4, 14, 6),
        (3, 11, 1, 9),
        (15, 7, 13, 5),
    ),
}


def render_area_mix_tile(tile_side: int, counts: Sequence[int]) -> Tuple[int, ...]:
    """Return one row-major Bayer-distributed tile with exact requested counts."""

    side = _tile_side(tile_side)
    if not isinstance(counts, (tuple, list)) or len(counts) != len(COLOR_ORDER):
        raise AreaMixError("counts must contain one value for each formal colour")
    if any(type(value) is not int or value < 0 for value in counts):
        raise AreaMixError("area-mix counts must be non-negative integers")
    normalized = tuple(counts)
    if sum(normalized) != side * side:
        raise AreaMixError("area-mix counts must sum to tile_side squared")

    ordered_positions = sorted(
        ((threshold, x_value, y_value) for y_value, row in enumerate(_BAYER[side]) for x_value, threshold in enumerate(row)),
        key=lambda item: item[0],
    )
    tile = [COLOR_ORDER[0]] * (side * side)
    # A contiguous interval of Bayer ranks for each colour yields the classic
    # spatially dispersed ordered-dither mask for a two-colour mix.  It also
    # divides the threshold lattice into dispersed, exact-count regions for
    # multi-colour recipes.  Interleaving colours before applying Bayer ranks
    # is intentionally avoided: rank parity maps to rows in a Bayer matrix and
    # would turn a nominal 50/50 recipe into directional bands.
    rank_codes = tuple(
        code
        for code, count in zip(COLOR_ORDER, normalized)
        for _ in range(count)
    )
    for code, (_, x_value, y_value) in zip(rank_codes, ordered_positions):
        tile[y_value * side + x_value] = code
    return tuple(tile)


@dataclass(frozen=True)
class AreaMixRecipe:
    """One exact six-primary tile recipe and its unmeasured prediction."""

    tile_side: int
    counts: Tuple[int, ...]
    predicted_lab: Lab
    predicted_srgb: Tuple[int, int, int]
    delta_e00: float

    def __post_init__(self) -> None:
        side = _tile_side(self.tile_side)
        if not isinstance(self.counts, tuple) or len(self.counts) != len(COLOR_ORDER):
            raise AreaMixError("recipe counts must be a six-item tuple")
        if any(type(value) is not int or value < 0 for value in self.counts):
            raise AreaMixError("recipe counts must be non-negative integers")
        if sum(self.counts) != side * side:
            raise AreaMixError("recipe counts must sum to tile_side squared")
        if any(code not in PHYSICAL_COLOR_CODES for code in COLOR_ORDER):
            raise AreaMixError("internal formal colour order is invalid")
        _validated_lab(self.predicted_lab, "predicted Lab")
        if (
            not isinstance(self.predicted_srgb, tuple)
            or len(self.predicted_srgb) != 3
            or any(type(value) is not int or not 0 <= value <= 255 for value in self.predicted_srgb)
        ):
            raise AreaMixError("predicted_srgb must contain three 8-bit integers")
        if isinstance(self.delta_e00, bool) or not isinstance(self.delta_e00, (int, float)):
            raise AreaMixError("delta_e00 must be numeric")
        if not math.isfinite(float(self.delta_e00)) or self.delta_e00 < 0:
            raise AreaMixError("delta_e00 must be finite and non-negative")

    @property
    def tile(self) -> Tuple[int, ...]:
        return render_area_mix_tile(self.tile_side, self.counts)

    def frame(self) -> bytes:
        """Repeat the formal six-code tile over a canonical 1024x600 frame."""

        side = self.tile_side
        tile = self.tile
        frame = pack_pixels(
            tile[(y_value % side) * side + (x_value % side)]
            for y_value in range(HEIGHT)
            for x_value in range(WIDTH)
        )
        validate_frame(frame)
        return frame

    def to_dict(self, rank: int) -> dict[str, Any]:
        if type(rank) is not int or rank < 1:
            raise AreaMixError("candidate rank must be a positive integer")
        tile = self.tile
        frame = self.frame()
        identity = frame_identity(frame).to_dict()
        pixels = self.tile_side * self.tile_side
        return {
            "rank": rank,
            "counts": [
                {
                    "code": code,
                    "name": COLOR_NAME_BY_CODE[code],
                    "pixels": count,
                    "fraction": count / pixels,
                }
                for code, count in zip(COLOR_ORDER, self.counts)
            ],
            "predicted_lab": {
                "l": self.predicted_lab[0],
                "a": self.predicted_lab[1],
                "b": self.predicted_lab[2],
            },
            "predicted_preview_srgb": list(self.predicted_srgb),
            "predicted_delta_e00": self.delta_e00,
            "measured_lab": None,
            "measured_delta_e00": None,
            "model_residual_delta_e00": None,
            "prediction_confidence": None,
            "transition_cost": None,
            "energy_j": None,
            "ghosting_metric": None,
            "tile_codes": [
                list(tile[row * self.tile_side : (row + 1) * self.tile_side])
                for row in range(self.tile_side)
            ],
            "tile_sha256": hashlib.sha256(bytes(tile)).hexdigest(),
            "tile_sha256_scope": AREA_MIX_TILE_SHA256_SCOPE,
            "frame_identity": identity,
        }


@dataclass(frozen=True)
class AreaMixAnalysis:
    """Ranked, auditable result for one target colour."""

    palette: Palette
    target_lab: Lab
    target_input_space: str
    target_input_values: Tuple[float | int, float | int, float | int]
    tile_side: int
    recipe_space_size: int
    recipes: Tuple[AreaMixRecipe, ...]
    uncalibrated_simulation: bool

    def report(self, *, rendered_candidate_rank: int | None = None) -> dict[str, Any]:
        if rendered_candidate_rank is not None and (
            type(rendered_candidate_rank) is not int
            or not 1 <= rendered_candidate_rank <= len(self.recipes)
        ):
            raise AreaMixError("rendered_candidate_rank is outside the candidate list")
        core_identity = {
            "schema_version": AREA_MIX_SCHEMA_VERSION,
            "model_version": AREA_MIX_MODEL_VERSION,
            "layout_version": AREA_MIX_LAYOUT_VERSION,
            "color_order": list(COLOR_ORDER),
            "palette_sha256": self.palette.canonical_sha256,
            "target_lab": list(self.target_lab),
            "target_input_space": self.target_input_space,
            "tile_side": self.tile_side,
            "candidate_counts": [list(recipe.counts) for recipe in self.recipes],
            "candidate_tile_codes": [list(recipe.tile) for recipe in self.recipes],
        }
        canonical = json.dumps(
            core_identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        analysis_id = f"MF1750-EC-MIX-{hashlib.sha256(canonical).hexdigest()[:12].upper()}"
        candidates = [
            recipe.to_dict(rank) for rank, recipe in enumerate(self.recipes, 1)
        ]
        palette_payload = self.palette.canonical_mapping()
        palette_payload["canonical_sha256"] = self.palette.canonical_sha256
        report = {
            "schema_version": AREA_MIX_SCHEMA_VERSION,
            "kind": "mf1750-six-primary-area-mix-analysis",
            "analysis_id": analysis_id,
            "analysis_id_scope": AREA_MIX_ANALYSIS_ID_SCOPE,
            "panel_model": "MF-17506-M009F-T",
            "color_codes": list(COLOR_ORDER),
            "hardware_tested": False,
            "offline_only": True,
            "device_io_performed": False,
            "network_io_performed": False,
            "waveform_changed": False,
            "voltage_changed": False,
            "formal_api_compatible": True,
            "prediction_is_measurement": False,
            "target": {
                "input_space": self.target_input_space,
                "input_values": list(self.target_input_values),
                "lab_d65_2deg": {
                    "l": self.target_lab[0],
                    "a": self.target_lab[1],
                    "b": self.target_lab[2],
                },
                "preview_srgb": list(lab_to_srgb8(self.target_lab)),
            },
            "palette": palette_payload,
            "model": {
                "model_version": AREA_MIX_MODEL_VERSION,
                "layout_version": AREA_MIX_LAYOUT_VERSION,
                "tile_side": self.tile_side,
                "tile_pixels": self.tile_side * self.tile_side,
                "recipe_space_size": self.recipe_space_size,
                "area_average_domain": "CIE XYZ D65 derived from palette Lab",
                "ranking_metric": "CIEDE2000",
                "layout": "contiguous color-count intervals on Bayer threshold order",
                "uncalibrated_simulation": self.uncalibrated_simulation,
                "limitations": (
                    "first-order spatial-average prediction; panel scattering, edge fields, "
                    "viewing distance, transition history, and measurement uncertainty are unmodelled"
                ),
            },
            "candidates": candidates,
            "artifact_selection": {
                "frame_output_requested": rendered_candidate_rank is not None,
                "rendered_candidate_rank": rendered_candidate_rank,
                "selected_frame_identity": (
                    None
                    if rendered_candidate_rank is None
                    else candidates[rendered_candidate_rank - 1]["frame_identity"]
                ),
            },
        }
        validate_area_mix_report(report)
        return report


def analyze_area_mixes(
    palette: Palette,
    target_lab: Sequence[float],
    *,
    tile_side: int = DEFAULT_TILE_SIDE,
    limit: int = DEFAULT_RESULT_LIMIT,
    allow_uncalibrated_simulation: bool = False,
    target_input_space: str = "Lab",
    target_input_values: Sequence[float | int] | None = None,
) -> AreaMixAnalysis:
    """Rank exact tile recipes for one target without performing device I/O."""

    if not isinstance(palette, Palette):
        raise AreaMixError("palette must be a host.color_pipeline.Palette")
    if type(allow_uncalibrated_simulation) is not bool:
        raise AreaMixError("allow_uncalibrated_simulation must be boolean")
    if not palette.calibrated and not allow_uncalibrated_simulation:
        raise AreaMixError(
            "a calibrated D65/2deg panel palette is required; use the explicit "
            "simulation opt-in only for non-hardware planning"
        )
    if target_input_space not in ("Lab", "sRGB8"):
        raise AreaMixError("target_input_space must be 'Lab' or 'sRGB8'")

    target = _validated_lab(target_lab, "target Lab")
    side = _tile_side(tile_side)
    result_limit = _result_limit(limit)
    if target_input_values is None:
        raw_input = target
    else:
        try:
            raw_input = tuple(target_input_values)
        except TypeError as error:
            raise AreaMixError(
                "target_input_values must contain exactly three components"
            ) from error
    if len(raw_input) != 3:
        raise AreaMixError("target_input_values must contain exactly three components")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in raw_input):
        raise AreaMixError("target_input_values must be numeric and not boolean")
    if not all(math.isfinite(float(value)) for value in raw_input):
        raise AreaMixError("target_input_values must be finite")
    if target_input_space == "sRGB8" and any(type(value) is not int or not 0 <= value <= 255 for value in raw_input):
        raise AreaMixError("sRGB8 input values must be integers in [0, 255]")
    if target_input_space == "Lab":
        derived_target = _validated_lab(raw_input, "target input Lab")
    else:
        derived_target = srgb8_to_lab(raw_input)  # type: ignore[arg-type]
    if any(
        not math.isclose(expected, actual, rel_tol=0.0, abs_tol=1e-12)
        for expected, actual in zip(target, derived_target)
    ):
        raise AreaMixError("target_input_values do not reproduce target_lab")

    entries = tuple(palette.entry(code) for code in COLOR_ORDER)
    xyz_values = tuple(
        lab_to_xyz(_validated_lab(entry.lab, f"palette code {entry.code} Lab"))
        for entry in entries
    )
    tile_pixels = side * side
    ranked = []
    for counts in _compositions(tile_pixels, len(COLOR_ORDER)):
        mixed_xyz = tuple(
            sum(count * xyz[channel] for count, xyz in zip(counts, xyz_values)) / tile_pixels
            for channel in range(3)
        )
        predicted = xyz_to_lab(mixed_xyz)
        distance = delta_e_ciede2000(target, predicted)
        ranked.append((distance, counts, predicted))
    ranked.sort(key=lambda item: (item[0], item[1]))

    recipes = tuple(
        AreaMixRecipe(
            tile_side=side,
            counts=counts,
            predicted_lab=predicted,
            predicted_srgb=lab_to_srgb8(predicted),
            delta_e00=distance,
        )
        for distance, counts, predicted in ranked[:result_limit]
    )
    return AreaMixAnalysis(
        palette=palette,
        target_lab=target,
        target_input_space=target_input_space,
        target_input_values=tuple(raw_input),  # type: ignore[arg-type]
        tile_side=side,
        recipe_space_size=math.comb(tile_pixels + len(COLOR_ORDER) - 1, len(COLOR_ORDER) - 1),
        recipes=recipes,
        uncalibrated_simulation=not palette.calibrated,
    )


_ANALYSIS_ID_RE = re.compile(r"MF1750-EC-MIX-[0-9A-F]{12}\Z")
_REPORT_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "analysis_id",
        "analysis_id_scope",
        "panel_model",
        "color_codes",
        "hardware_tested",
        "offline_only",
        "device_io_performed",
        "network_io_performed",
        "waveform_changed",
        "voltage_changed",
        "formal_api_compatible",
        "prediction_is_measurement",
        "target",
        "palette",
        "model",
        "candidates",
        "artifact_selection",
    }
)
_CANDIDATE_KEYS = frozenset(
    {
        "rank",
        "counts",
        "predicted_lab",
        "predicted_preview_srgb",
        "predicted_delta_e00",
        "measured_lab",
        "measured_delta_e00",
        "model_residual_delta_e00",
        "prediction_confidence",
        "transition_cost",
        "energy_j",
        "ghosting_metric",
        "tile_codes",
        "tile_sha256",
        "tile_sha256_scope",
        "frame_identity",
    }
)


def _report_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AreaMixError(f"{label} must be an object")
    return value


def _exact_report_keys(
    value: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    if set(value) != expected:
        raise AreaMixError(
            f"{label} keys differ: missing={sorted(expected - set(value))}, "
            f"extra={sorted(set(value) - expected)}"
        )


def _lab_mapping(value: object, label: str) -> Lab:
    mapping = _report_mapping(value, label)
    if set(mapping) != {"l", "a", "b"}:
        raise AreaMixError(f"{label} must contain exactly l, a and b")
    return _validated_lab((mapping["l"], mapping["a"], mapping["b"]), label)


def _same_float_tuple(first: Sequence[float], second: Sequence[float]) -> bool:
    return len(first) == len(second) and all(
        math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12)
        for left, right in zip(first, second)
    )


def validate_area_mix_report(report: Mapping[str, Any]) -> None:
    """Apply cross-item invariants that JSON Schema cannot express alone."""

    report = _report_mapping(report, "area-mix report")
    _exact_report_keys(report, _REPORT_KEYS, "area-mix report")
    constants = {
        "schema_version": AREA_MIX_SCHEMA_VERSION,
        "kind": "mf1750-six-primary-area-mix-analysis",
        "analysis_id_scope": AREA_MIX_ANALYSIS_ID_SCOPE,
        "panel_model": "MF-17506-M009F-T",
        "color_codes": list(COLOR_ORDER),
        "hardware_tested": False,
        "offline_only": True,
        "device_io_performed": False,
        "network_io_performed": False,
        "waveform_changed": False,
        "voltage_changed": False,
        "formal_api_compatible": True,
        "prediction_is_measurement": False,
    }
    for field, expected in constants.items():
        if report[field] != expected or type(report[field]) is not type(expected):
            raise AreaMixError(f"area-mix report {field} violates its constant")
    if not isinstance(report["analysis_id"], str) or _ANALYSIS_ID_RE.fullmatch(
        report["analysis_id"]
    ) is None:
        raise AreaMixError("area-mix analysis_id is invalid")

    target_mapping = _report_mapping(report["target"], "target")
    if set(target_mapping) != {
        "input_space",
        "input_values",
        "lab_d65_2deg",
        "preview_srgb",
    }:
        raise AreaMixError("target keys differ from the contract")
    target = _lab_mapping(target_mapping["lab_d65_2deg"], "target Lab")
    input_space = target_mapping["input_space"]
    input_values = target_mapping["input_values"]
    if not isinstance(input_values, list) or len(input_values) != 3:
        raise AreaMixError("target input_values must contain three values")
    if input_space == "Lab":
        derived_target = _validated_lab(input_values, "target input Lab")
    elif input_space == "sRGB8":
        if any(type(value) is not int or not 0 <= value <= 255 for value in input_values):
            raise AreaMixError("target sRGB8 input must contain three 8-bit integers")
        derived_target = srgb8_to_lab(input_values)
    else:
        raise AreaMixError("target input_space is invalid")
    if not _same_float_tuple(target, derived_target):
        raise AreaMixError("target input does not reproduce target Lab")
    if target_mapping["preview_srgb"] != list(lab_to_srgb8(target)):
        raise AreaMixError("target preview_srgb is inconsistent")

    palette_mapping = dict(_report_mapping(report["palette"], "palette"))
    palette_digest = palette_mapping.pop("canonical_sha256", None)
    try:
        palette = palette_from_mapping(palette_mapping)
    except PaletteError as error:
        raise AreaMixError(f"embedded palette is invalid: {error}") from error
    if palette_digest != palette.canonical_sha256:
        raise AreaMixError("embedded palette canonical_sha256 is inconsistent")

    model = _report_mapping(report["model"], "model")
    model_keys = {
        "model_version",
        "layout_version",
        "tile_side",
        "tile_pixels",
        "recipe_space_size",
        "area_average_domain",
        "ranking_metric",
        "layout",
        "uncalibrated_simulation",
        "limitations",
    }
    if set(model) != model_keys:
        raise AreaMixError("model keys differ from the contract")
    if model["model_version"] != AREA_MIX_MODEL_VERSION:
        raise AreaMixError("model_version is invalid")
    if model["layout_version"] != AREA_MIX_LAYOUT_VERSION:
        raise AreaMixError("layout_version is invalid")
    side = _tile_side(model["tile_side"])
    tile_pixels = side * side
    if model["tile_pixels"] != tile_pixels:
        raise AreaMixError("tile_pixels is inconsistent with tile_side")
    expected_space = math.comb(tile_pixels + len(COLOR_ORDER) - 1, len(COLOR_ORDER) - 1)
    if model["recipe_space_size"] != expected_space:
        raise AreaMixError("recipe_space_size is inconsistent with tile_side")
    if model["area_average_domain"] != "CIE XYZ D65 derived from palette Lab":
        raise AreaMixError("area_average_domain is invalid")
    if model["ranking_metric"] != "CIEDE2000":
        raise AreaMixError("ranking_metric is invalid")
    if model["layout"] != "contiguous color-count intervals on Bayer threshold order":
        raise AreaMixError("layout description is invalid")
    if type(model["uncalibrated_simulation"]) is not bool or model[
        "uncalibrated_simulation"
    ] != (not palette.calibrated):
        raise AreaMixError("uncalibrated_simulation is inconsistent with palette")
    if not isinstance(model["limitations"], str) or not model["limitations"]:
        raise AreaMixError("model limitations must be explicit")

    candidates = report["candidates"]
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= MAX_RESULT_LIMIT:
        raise AreaMixError("candidates must contain 1 through 32 items")
    palette_xyz = tuple(
        lab_to_xyz(_validated_lab(palette.entry(code).lab, f"palette code {code} Lab"))
        for code in COLOR_ORDER
    )
    identity_counts = []
    identity_tiles = []
    validated_identities = []
    seen_counts: set[Tuple[int, ...]] = set()
    for expected_rank, raw_candidate in enumerate(candidates, 1):
        candidate = _report_mapping(raw_candidate, f"candidate {expected_rank}")
        _exact_report_keys(candidate, _CANDIDATE_KEYS, f"candidate {expected_rank}")
        if type(candidate["rank"]) is not int or candidate["rank"] != expected_rank:
            raise AreaMixError("candidate ranks must be sequential from one")
        raw_counts = candidate["counts"]
        if not isinstance(raw_counts, list) or len(raw_counts) != len(COLOR_ORDER):
            raise AreaMixError("candidate counts must contain six ordered items")
        counts = []
        for index, (raw_count, code) in enumerate(zip(raw_counts, COLOR_ORDER)):
            count_mapping = _report_mapping(raw_count, f"candidate count {index}")
            if set(count_mapping) != {"code", "name", "pixels", "fraction"}:
                raise AreaMixError("candidate count keys differ from the contract")
            if count_mapping["code"] != code or count_mapping["name"] != COLOR_NAME_BY_CODE[code]:
                raise AreaMixError("candidate count color order is invalid")
            count = count_mapping["pixels"]
            if type(count) is not int or not 0 <= count <= tile_pixels:
                raise AreaMixError("candidate pixel count is invalid")
            fraction = count_mapping["fraction"]
            if isinstance(fraction, bool) or not isinstance(fraction, (int, float)):
                raise AreaMixError("candidate fraction must be numeric")
            if not math.isclose(float(fraction), count / tile_pixels, rel_tol=0.0, abs_tol=1e-15):
                raise AreaMixError("candidate fraction is inconsistent with pixel count")
            counts.append(count)
        if sum(counts) != tile_pixels:
            raise AreaMixError("candidate counts do not sum to tile_pixels")
        counts_tuple = tuple(counts)
        if counts_tuple in seen_counts:
            raise AreaMixError("candidate count recipes must be unique")
        seen_counts.add(counts_tuple)

        raw_tile = candidate["tile_codes"]
        if (
            not isinstance(raw_tile, list)
            or len(raw_tile) != side
            or any(not isinstance(row, list) or len(row) != side for row in raw_tile)
        ):
            raise AreaMixError("candidate tile dimensions are inconsistent")
        tile = tuple(value for row in raw_tile for value in row)
        if any(type(code) is not int or code not in COLOR_ORDER for code in tile):
            raise AreaMixError("candidate tile contains a non-formal color code")
        if tuple(tile.count(code) for code in COLOR_ORDER) != tuple(counts):
            raise AreaMixError("candidate tile does not reproduce its counts")
        if tile != render_area_mix_tile(side, counts):
            raise AreaMixError("candidate tile does not match the declared layout algorithm")
        if candidate["tile_sha256_scope"] != AREA_MIX_TILE_SHA256_SCOPE:
            raise AreaMixError("candidate tile_sha256_scope is invalid")
        if candidate["tile_sha256"] != hashlib.sha256(bytes(tile)).hexdigest():
            raise AreaMixError("candidate tile_sha256 is inconsistent")

        predicted = _lab_mapping(candidate["predicted_lab"], "candidate predicted Lab")
        mixed_xyz = tuple(
            sum(count * xyz[channel] for count, xyz in zip(counts, palette_xyz)) / tile_pixels
            for channel in range(3)
        )
        expected_predicted = xyz_to_lab(mixed_xyz)
        if not _same_float_tuple(predicted, expected_predicted):
            raise AreaMixError("candidate predicted Lab is inconsistent")
        if candidate["predicted_preview_srgb"] != list(lab_to_srgb8(predicted)):
            raise AreaMixError("candidate preview is inconsistent")
        expected_delta = delta_e_ciede2000(target, predicted)
        delta = candidate["predicted_delta_e00"]
        if (
            isinstance(delta, bool)
            or not isinstance(delta, (int, float))
            or not math.isclose(float(delta), expected_delta, rel_tol=0.0, abs_tol=1e-12)
        ):
            raise AreaMixError("candidate predicted_delta_e00 is inconsistent")
        for null_field in (
            "measured_lab",
            "measured_delta_e00",
            "model_residual_delta_e00",
            "prediction_confidence",
            "transition_cost",
            "energy_j",
            "ghosting_metric",
        ):
            if candidate[null_field] is not None:
                raise AreaMixError(f"unmeasured candidate field {null_field} must be null")

        frame = pack_pixels(
            tile[(y_value % side) * side + (x_value % side)]
            for y_value in range(HEIGHT)
            for x_value in range(WIDTH)
        )
        expected_identity = frame_identity(frame).to_dict()
        if candidate["frame_identity"] != expected_identity:
            raise AreaMixError("candidate frame identity is inconsistent")
        identity_counts.append(counts)
        identity_tiles.append(list(tile))
        validated_identities.append(expected_identity)

    expected_analysis = analyze_area_mixes(
        palette,
        target,
        tile_side=side,
        limit=len(candidates),
        allow_uncalibrated_simulation=not palette.calibrated,
        target_input_space=input_space,
        target_input_values=input_values,
    )
    if [recipe.counts for recipe in expected_analysis.recipes] != [
        tuple(counts) for counts in identity_counts
    ]:
        raise AreaMixError("candidate ranks are not the deterministic top-N recipes")

    selection = _report_mapping(report["artifact_selection"], "artifact_selection")
    if set(selection) != {
        "frame_output_requested",
        "rendered_candidate_rank",
        "selected_frame_identity",
    }:
        raise AreaMixError("artifact_selection keys differ from the contract")
    selected_rank = selection["rendered_candidate_rank"]
    if selected_rank is None:
        if selection["frame_output_requested"] is not False or selection[
            "selected_frame_identity"
        ] is not None:
            raise AreaMixError("artifact_selection null state is inconsistent")
    else:
        if type(selected_rank) is not int or not 1 <= selected_rank <= len(candidates):
            raise AreaMixError("rendered_candidate_rank is invalid")
        if selection["frame_output_requested"] is not True:
            raise AreaMixError("frame_output_requested is inconsistent")
        if selection["selected_frame_identity"] != validated_identities[selected_rank - 1]:
            raise AreaMixError("selected_frame_identity is inconsistent")

    identity_payload = {
        "schema_version": AREA_MIX_SCHEMA_VERSION,
        "model_version": AREA_MIX_MODEL_VERSION,
        "layout_version": AREA_MIX_LAYOUT_VERSION,
        "color_order": list(COLOR_ORDER),
        "palette_sha256": palette.canonical_sha256,
        "target_lab": list(target),
        "target_input_space": input_space,
        "tile_side": side,
        "candidate_counts": identity_counts,
        "candidate_tile_codes": identity_tiles,
    }
    canonical = json.dumps(
        identity_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    expected_analysis_id = (
        f"MF1750-EC-MIX-{hashlib.sha256(canonical).hexdigest()[:12].upper()}"
    )
    if report["analysis_id"] != expected_analysis_id:
        raise AreaMixError("analysis_id is inconsistent with its declared scope")
