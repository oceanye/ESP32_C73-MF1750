"""Empty, optimizer-readable 6x6 transition profile scaffolding."""

from __future__ import annotations

from typing import Any, Mapping

from .offline import COLOR_ORDER


NULL_MEASUREMENT_FIELDS = (
    "initial_lab_mean",
    "final_lab_mean",
    "delta_e00_mean",
    "delta_e00_sd",
    "cs1_minus_cs2_delta_e00",
    "position_effect_delta_e00",
    "ghosting_metric_mean",
    "busy_ms_mean",
    "peak_current_a_mean",
    "energy_j_mean",
    "temperature_rise_c_mean",
    "recovery_pass_rate",
)

_PROFILE_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "panel_model",
        "color_codes",
        "hardware_tested",
        "generated_at",
        "cells",
    }
)
_CELL_KEYS = frozenset({"old_code", "new_code", "sample_count", *NULL_MEASUREMENT_FIELDS})


def build_empty_transition_profile() -> dict[str, Any]:
    """Return all 36 transitions with every unmeasured value explicitly null."""

    cells = []
    for old_code in COLOR_ORDER:
        for new_code in COLOR_ORDER:
            cell: dict[str, Any] = {
                "old_code": old_code,
                "new_code": new_code,
                "sample_count": 0,
            }
            cell.update({field: None for field in NULL_MEASUREMENT_FIELDS})
            cells.append(cell)
    return {
        "schema_version": 1,
        "kind": "mf1750-six-by-six-transition-profile",
        "panel_model": "MF-17506-M009F-T",
        "color_codes": list(COLOR_ORDER),
        "hardware_tested": False,
        "generated_at": None,
        "cells": cells,
    }


def validate_transition_profile(profile: Mapping[str, Any]) -> None:
    """Apply semantic checks JSON Schema cannot compactly express across 36 cells."""

    if not isinstance(profile, Mapping) or set(profile) != _PROFILE_KEYS:
        raise ValueError("transition profile has missing or unknown top-level keys")
    if profile["schema_version"] != 1:
        raise ValueError("transition profile schema_version must be 1")
    if profile["kind"] != "mf1750-six-by-six-transition-profile":
        raise ValueError("transition profile kind is invalid")
    if profile["panel_model"] != "MF-17506-M009F-T":
        raise ValueError("transition profile panel_model is invalid")
    if profile["color_codes"] != list(COLOR_ORDER):
        raise ValueError("transition profile color_codes are not frozen")
    if type(profile["hardware_tested"]) is not bool:
        raise ValueError("transition profile hardware_tested must be a boolean")

    expected = {(old, new) for old in COLOR_ORDER for new in COLOR_ORDER}
    cells = profile["cells"]
    if not isinstance(cells, list) or len(cells) != len(expected):
        raise ValueError("transition profile must contain exactly 36 cells")
    seen: set[tuple[int, int]] = set()
    for index, cell in enumerate(cells):
        if not isinstance(cell, Mapping) or set(cell) != _CELL_KEYS:
            raise ValueError(f"transition profile cell {index} has invalid keys")
        pair = (cell["old_code"], cell["new_code"])
        if pair not in expected:
            raise ValueError(f"transition profile cell {index} has an invalid color pair")
        if pair in seen:
            raise ValueError(f"transition profile contains duplicate pair {pair}")
        seen.add(pair)
        sample_count = cell["sample_count"]
        if type(sample_count) is not int or sample_count < 0:
            raise ValueError(f"transition profile cell {index} has invalid sample_count")
        if sample_count == 0 and any(cell[field] is not None for field in NULL_MEASUREMENT_FIELDS):
            raise ValueError(
                f"transition profile cell {index} must keep unmeasured values null"
            )
    if seen != expected:
        raise ValueError("transition profile does not contain every old/new pair exactly once")
