"""Qualified history-recipe palette separate from the six physical colours."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any, Mapping

from host.color_pipeline.color import lab_to_srgb8

from .common import (
    StaticPhotoContractError,
    attach_integrity,
    finite_triple,
    require_exact_keys,
    require_sha256,
    require_text,
    verify_integrity,
)


HISTORY_PALETTE_SCHEMA_VERSION = 1
TRANSPORT_CODES = tuple(range(8))


class HistoryPaletteError(StaticPhotoContractError):
    """Raised when a history-recipe palette is unsafe or untraceable."""


class QualificationLevel(str, Enum):
    CANDIDATE = "CANDIDATE"
    QUALIFIED = "QUALIFIED"


class RetentionMode(str, Enum):
    POWERED_IDLE = "powered_idle"
    SAFE_POWER_OFF = "safe_power_off"


@dataclass(frozen=True)
class HistoryRecipe:
    recipe_id: str
    primer_transport_code: int
    target_transport_code: int
    primer_dwell_ms: int
    target_repeat_count: int
    factory_profile_id: str
    temperature_min_c: float
    temperature_max_c: float
    retention_mode: RetentionMode
    minimum_recipe_cell_px: int
    measured_lab: tuple[float, float, float]
    preview_rgb: tuple[int, int, int]
    within_patch_std_lab: tuple[float, float, float]
    repeat_delta_e00: float
    controller_delta_e00: float
    retention_delta_e00: float
    recovery_qualified: bool
    measurement_id: str
    measurement_artifact_sha256: str
    qualification_level: QualificationLevel

    def __post_init__(self) -> None:
        object.__setattr__(self, "recipe_id", require_text(self.recipe_id, "recipe_id"))
        object.__setattr__(
            self,
            "factory_profile_id",
            require_text(self.factory_profile_id, "factory_profile_id"),
        )
        object.__setattr__(
            self,
            "measurement_id",
            require_text(self.measurement_id, "measurement_id"),
        )
        for label in ("primer_transport_code", "target_transport_code"):
            value = getattr(self, label)
            if type(value) is not int or value not in TRANSPORT_CODES:
                raise HistoryPaletteError(f"{label} must be an integer in 0..7")
        if type(self.primer_dwell_ms) is not int or self.primer_dwell_ms < 0:
            raise HistoryPaletteError("primer_dwell_ms must be a non-negative integer")
        if type(self.target_repeat_count) is not int or self.target_repeat_count <= 0:
            raise HistoryPaletteError("target_repeat_count must be a positive integer")
        for label in ("temperature_min_c", "temperature_max_c"):
            value = getattr(self, label)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise HistoryPaletteError(f"{label} must be numeric")
            object.__setattr__(self, label, float(value))
        if self.temperature_min_c > self.temperature_max_c:
            raise HistoryPaletteError("temperature band is reversed")
        try:
            retention = (
                self.retention_mode
                if isinstance(self.retention_mode, RetentionMode)
                else RetentionMode(self.retention_mode)
            )
            qualification = (
                self.qualification_level
                if isinstance(self.qualification_level, QualificationLevel)
                else QualificationLevel(self.qualification_level)
            )
        except ValueError as error:
            raise HistoryPaletteError(
                "retention or qualification value differs"
            ) from error
        object.__setattr__(self, "retention_mode", retention)
        object.__setattr__(self, "qualification_level", qualification)
        if type(
            self.minimum_recipe_cell_px
        ) is not int or self.minimum_recipe_cell_px not in (
            1,
            2,
            4,
            8,
        ):
            raise HistoryPaletteError("minimum_recipe_cell_px must be one of 1,2,4,8")
        lab = finite_triple(self.measured_lab, f"recipe {self.recipe_id} measured_lab")
        if not 0.0 <= lab[0] <= 100.0:
            raise HistoryPaletteError("measured Lab L* must be in [0, 100]")
        object.__setattr__(self, "measured_lab", lab)
        std = finite_triple(
            self.within_patch_std_lab, f"recipe {self.recipe_id} within_patch_std_lab"
        )
        if any(value < 0 for value in std):
            raise HistoryPaletteError("within_patch_std_lab must be non-negative")
        object.__setattr__(self, "within_patch_std_lab", std)
        if (
            not isinstance(self.preview_rgb, (tuple, list))
            or len(self.preview_rgb) != 3
            or any(
                type(value) is not int or not 0 <= value <= 255
                for value in self.preview_rgb
            )
        ):
            raise HistoryPaletteError(
                "preview_rgb must contain three integers in [0,255]"
            )
        object.__setattr__(self, "preview_rgb", tuple(self.preview_rgb))
        for label in (
            "repeat_delta_e00",
            "controller_delta_e00",
            "retention_delta_e00",
        ):
            value = getattr(self, label)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or value < 0
            ):
                raise HistoryPaletteError(f"{label} must be non-negative")
            object.__setattr__(self, label, float(value))
        if type(self.recovery_qualified) is not bool:
            raise HistoryPaletteError("recovery_qualified must be boolean")
        require_sha256(self.measurement_artifact_sha256, "measurement_artifact_sha256")
        if qualification is QualificationLevel.QUALIFIED:
            if not self.recovery_qualified:
                raise HistoryPaletteError(
                    "qualified recipe requires recovery_qualified=true"
                )
            if self.target_repeat_count < 10:
                raise HistoryPaletteError(
                    "qualified recipe requires at least 10 repeats"
                )

    def mapping(self) -> dict[str, Any]:
        return {
            "recipe_id": self.recipe_id,
            "primer_transport_code": self.primer_transport_code,
            "target_transport_code": self.target_transport_code,
            "primer_dwell_ms": self.primer_dwell_ms,
            "target_repeat_count": self.target_repeat_count,
            "factory_profile_id": self.factory_profile_id,
            "temperature_band_c": [self.temperature_min_c, self.temperature_max_c],
            "retention_mode": self.retention_mode.value,
            "minimum_recipe_cell_px": self.minimum_recipe_cell_px,
            "measured_lab": list(self.measured_lab),
            "preview_rgb": list(self.preview_rgb),
            "within_patch_std_lab": list(self.within_patch_std_lab),
            "repeat_delta_e00": self.repeat_delta_e00,
            "controller_delta_e00": self.controller_delta_e00,
            "retention_delta_e00": self.retention_delta_e00,
            "recovery_qualified": self.recovery_qualified,
            "measurement_id": self.measurement_id,
            "measurement_artifact_sha256": self.measurement_artifact_sha256,
            "qualification_level": self.qualification_level.value,
        }


@dataclass(frozen=True)
class HistoryPalette:
    palette_id: str
    chart_calibration_sha256: str
    factory_profile_id: str
    recipes: tuple[HistoryRecipe, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "palette_id", require_text(self.palette_id, "palette_id")
        )
        object.__setattr__(
            self,
            "factory_profile_id",
            require_text(self.factory_profile_id, "factory_profile_id"),
        )
        require_sha256(self.chart_calibration_sha256, "chart_calibration_sha256")
        if not isinstance(self.recipes, (tuple, list)) or not self.recipes:
            raise HistoryPaletteError("history palette requires at least one recipe")
        if not all(isinstance(recipe, HistoryRecipe) for recipe in self.recipes):
            raise HistoryPaletteError("recipes must contain HistoryRecipe values")
        identifiers = [recipe.recipe_id for recipe in self.recipes]
        if len(set(identifiers)) != len(identifiers):
            raise HistoryPaletteError("recipe_id values must be unique")
        if any(
            recipe.factory_profile_id != self.factory_profile_id
            for recipe in self.recipes
        ):
            raise HistoryPaletteError("recipe factory_profile_id differs from palette")
        object.__setattr__(
            self,
            "recipes",
            tuple(sorted(self.recipes, key=lambda recipe: recipe.recipe_id)),
        )

    @property
    def qualified_recipes(self) -> tuple[HistoryRecipe, ...]:
        return tuple(
            recipe
            for recipe in self.recipes
            if recipe.qualification_level is QualificationLevel.QUALIFIED
        )

    def unsigned_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": HISTORY_PALETTE_SCHEMA_VERSION,
            "kind": "MF17506_HISTORY_RECIPE_PALETTE",
            "palette_id": self.palette_id,
            "chart_calibration_sha256": self.chart_calibration_sha256,
            "factory_profile_id": self.factory_profile_id,
            "recipes": [recipe.mapping() for recipe in self.recipes],
            "evidence_boundaries": {
                "separate_from_six_physical_colour_palette": True,
                "new_pigment_colour_claimed": False,
                "runtime_lut_used": False,
            },
        }

    def mapping(self) -> dict[str, Any]:
        return attach_integrity(self.unsigned_mapping())


_RECIPE_KEYS = {
    "recipe_id",
    "primer_transport_code",
    "target_transport_code",
    "primer_dwell_ms",
    "target_repeat_count",
    "factory_profile_id",
    "temperature_band_c",
    "retention_mode",
    "minimum_recipe_cell_px",
    "measured_lab",
    "preview_rgb",
    "within_patch_std_lab",
    "repeat_delta_e00",
    "controller_delta_e00",
    "retention_delta_e00",
    "recovery_qualified",
    "measurement_id",
    "measurement_artifact_sha256",
    "qualification_level",
}


def _recipe_from_mapping(raw: Mapping[str, Any], index: int) -> HistoryRecipe:
    require_exact_keys(raw, _RECIPE_KEYS, f"recipe {index}")
    temperature = raw["temperature_band_c"]
    if not isinstance(temperature, list) or len(temperature) != 2:
        raise HistoryPaletteError("temperature_band_c must contain min and max")
    lab = finite_triple(raw["measured_lab"], f"recipe {index} measured_lab")
    preview_raw = raw["preview_rgb"]
    preview = lab_to_srgb8(lab) if preview_raw is None else tuple(preview_raw)
    return HistoryRecipe(
        raw["recipe_id"],
        raw["primer_transport_code"],
        raw["target_transport_code"],
        raw["primer_dwell_ms"],
        raw["target_repeat_count"],
        raw["factory_profile_id"],
        temperature[0],
        temperature[1],
        RetentionMode(raw["retention_mode"]),
        raw["minimum_recipe_cell_px"],
        lab,
        preview,  # type: ignore[arg-type]
        finite_triple(raw["within_patch_std_lab"], f"recipe {index} std Lab"),
        raw["repeat_delta_e00"],
        raw["controller_delta_e00"],
        raw["retention_delta_e00"],
        raw["recovery_qualified"],
        raw["measurement_id"],
        raw["measurement_artifact_sha256"],
        QualificationLevel(raw["qualification_level"]),
    )


def history_palette_from_mapping(data: Mapping[str, Any]) -> HistoryPalette:
    try:
        unsigned = verify_integrity(data, "history palette")
        require_exact_keys(
            unsigned,
            {
                "schema_version",
                "kind",
                "palette_id",
                "chart_calibration_sha256",
                "factory_profile_id",
                "recipes",
                "evidence_boundaries",
            },
            "history palette",
        )
        if unsigned["schema_version"] != HISTORY_PALETTE_SCHEMA_VERSION:
            raise HistoryPaletteError("history palette schema_version differs")
        if unsigned["kind"] != "MF17506_HISTORY_RECIPE_PALETTE":
            raise HistoryPaletteError("history palette kind differs")
        if unsigned["evidence_boundaries"] != {
            "separate_from_six_physical_colour_palette": True,
            "new_pigment_colour_claimed": False,
            "runtime_lut_used": False,
        }:
            raise HistoryPaletteError("history palette evidence boundaries differ")
        raw_recipes = unsigned["recipes"]
        if not isinstance(raw_recipes, list):
            raise HistoryPaletteError("recipes must be a list")
        if not all(isinstance(raw, Mapping) for raw in raw_recipes):
            raise HistoryPaletteError("every recipe must be an object")
        return HistoryPalette(
            unsigned["palette_id"],
            unsigned["chart_calibration_sha256"],
            unsigned["factory_profile_id"],
            tuple(
                _recipe_from_mapping(raw, index)
                for index, raw in enumerate(raw_recipes)
                if isinstance(raw, Mapping)
            ),
        )
    except StaticPhotoContractError as error:
        if isinstance(error, HistoryPaletteError):
            raise
        raise HistoryPaletteError(str(error)) from error
    except (KeyError, TypeError, ValueError) as error:
        raise HistoryPaletteError(f"history palette value differs: {error}") from error


def load_history_palette(path: str | Path) -> HistoryPalette:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryPaletteError(f"cannot load history palette: {error}") from error
    if not isinstance(raw, Mapping):
        raise HistoryPaletteError("history palette must be an object")
    return history_palette_from_mapping(raw)
