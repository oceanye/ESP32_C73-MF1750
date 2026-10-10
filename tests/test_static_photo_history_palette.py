from __future__ import annotations

import hashlib

import pytest

from host.static_photo.dual_frame import DualFrameError, build_dual_frame
from host.static_photo.history_palette import (
    HistoryPalette,
    HistoryPaletteError,
    HistoryRecipe,
    QualificationLevel,
    RetentionMode,
    history_palette_from_mapping,
)


def _recipe(recipe_id: str, source: int, target: int) -> HistoryRecipe:
    return HistoryRecipe(
        recipe_id,
        source,
        target,
        2000,
        10,
        "factory_otp",
        23.0,
        26.0,
        RetentionMode.SAFE_POWER_OFF,
        1,
        (45.0 + source, 5.0, -35.0),
        (45, 90, 160),
        (1.0, 1.0, 1.0),
        1.2,
        1.0,
        1.5,
        True,
        f"measurement-{recipe_id}",
        hashlib.sha256(recipe_id.encode()).hexdigest(),
        QualificationLevel.QUALIFIED,
    )


def test_history_palette_round_trip_and_dual_frame() -> None:
    recipes = (_recipe("r0", 0, 4), _recipe("r1", 3, 7))
    palette = HistoryPalette(
        "qualified-blue-v1",
        hashlib.sha256(b"calibration").hexdigest(),
        "factory_otp",
        recipes,
    )
    assert history_palette_from_mapping(palette.mapping()) == palette
    result = build_dual_frame(
        recipes, bytes((0, 1, 1, 0, 0, 1, 1, 0)), width=4, height=2
    )
    assert result.primer == bytes((0x03, 0x30, 0x03, 0x30))
    assert result.target == bytes((0x47, 0x74, 0x47, 0x74))


def test_qualified_recipe_requires_recovery_and_ten_repeats() -> None:
    recipe = _recipe("r0", 0, 4)
    with pytest.raises(HistoryPaletteError, match="at least 10 repeats"):
        HistoryRecipe(
            recipe.recipe_id,
            recipe.primer_transport_code,
            recipe.target_transport_code,
            recipe.primer_dwell_ms,
            9,
            recipe.factory_profile_id,
            recipe.temperature_min_c,
            recipe.temperature_max_c,
            recipe.retention_mode,
            recipe.minimum_recipe_cell_px,
            recipe.measured_lab,
            recipe.preview_rgb,
            recipe.within_patch_std_lab,
            recipe.repeat_delta_e00,
            recipe.controller_delta_e00,
            recipe.retention_delta_e00,
            True,
            recipe.measurement_id,
            recipe.measurement_artifact_sha256,
            recipe.qualification_level,
        )
    with pytest.raises(DualFrameError, match="out-of-range"):
        build_dual_frame((recipe,), bytes((1, 0)), width=2, height=1)
