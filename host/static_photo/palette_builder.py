"""Build a non-qualified history palette from mirrored screening analyses."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from host.color_pipeline.color import delta_e_ciede2000, lab_to_srgb8

from .common import (
    StaticPhotoContractError,
    canonical_json_bytes,
    canonical_sha256,
    file_sha256,
    verify_integrity,
)
from .history_palette import (
    HistoryPalette,
    HistoryRecipe,
    QualificationLevel,
    RetentionMode,
)


class PaletteBuildError(ValueError):
    """Raised when screening analyses cannot form a traceable candidate palette."""


def _load_analysis(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
        raw = json.loads(payload)
    except (OSError, json.JSONDecodeError) as error:
        raise PaletteBuildError(f"cannot load analysis: {error}") from error
    if not isinstance(raw, Mapping):
        raise PaletteBuildError("analysis must be an object")
    try:
        verify_integrity(raw, "history analysis")
    except StaticPhotoContractError as error:
        raise PaletteBuildError(str(error)) from error
    result = dict(raw)
    if result.get("kind") != "MF17506_BLUE_HISTORY_PHOTO_ANALYSIS":
        raise PaletteBuildError("analysis kind differs")
    return result, payload


def build_screening_palette(
    analysis_files: Sequence[str | Path],
    *,
    output_file: str | Path,
    palette_id: str,
    primer_dwell_ms: int,
    temperature_min_c: float,
    temperature_max_c: float,
) -> dict[str, Any]:
    if not isinstance(analysis_files, (tuple, list)) or len(analysis_files) < 2:
        raise PaletteBuildError("at least A and A-prime analyses are required")
    analyses: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for value in analysis_files:
        path = Path(value)
        analysis, payload = _load_analysis(path)
        analyses.append(analysis)
        evidence.append(
            {
                "file": str(path.resolve()),
                "file_sha256": file_sha256(payload),
                "canonical_sha256": analysis["integrity"]["canonical_sha256"],
                "batch_id": analysis["batch_id"],
                "timepoint_seconds": analysis["timepoint_seconds"],
            }
        )
    if {analysis["batch_id"] for analysis in analyses} != {"A", "A-prime"}:
        raise PaletteBuildError("screening palette requires both A and A-prime")
    calibration_ids = {
        analysis["calibration"]["canonical_sha256"] for analysis in analyses
    }
    plan_ids = {analysis["plan_manifest"]["canonical_sha256"] for analysis in analyses}
    if len(calibration_ids) != 1 or len(plan_ids) != 1:
        raise PaletteBuildError("analysis calibration or plan identity differs")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for analysis in analyses:
        for measurement in analysis["measurements"]:
            grouped.setdefault(measurement["recipe_id"], []).append(measurement)
    if len(grouped) != 16:
        raise PaletteBuildError("screening analysis must cover exactly 16 recipes")
    measurement_evidence = {
        "kind": "MF17506_SCREENING_PALETTE_MEASUREMENT_SET",
        "analyses": sorted(
            evidence, key=lambda item: (item["batch_id"], item["timepoint_seconds"])
        ),
        "plan_canonical_sha256": next(iter(plan_ids)),
        "calibration_canonical_sha256": next(iter(calibration_ids)),
    }
    measurement_sha = canonical_sha256(measurement_evidence)
    recipes: list[HistoryRecipe] = []
    for recipe_id, items in sorted(grouped.items()):
        if {item["controller"] for item in items} != {"CS1", "CS2"}:
            raise PaletteBuildError(f"recipe {recipe_id} lacks controller mirror")
        sources = {item["source_code"] for item in items}
        targets = {item["target_code"] for item in items}
        if len(sources) != 1 or len(targets) != 1:
            raise PaletteBuildError(f"recipe {recipe_id} code identity differs")
        labs = [tuple(item["corrected_median_lab"]) for item in items]
        mean_lab_array = np.mean(np.asarray(labs, dtype=np.float64), axis=0)
        mean_lab = tuple(float(value) for value in mean_lab_array)
        pairwise = [
            delta_e_ciede2000(labs[left], labs[right])
            for left in range(len(labs))
            for right in range(left + 1, len(labs))
        ]
        std_values = np.asarray([item["corrected_std_lab"] for item in items])
        recipes.append(
            HistoryRecipe(
                recipe_id,
                next(iter(sources)),
                next(iter(targets)),
                primer_dwell_ms,
                len(items),
                "factory_otp",
                temperature_min_c,
                temperature_max_c,
                RetentionMode.POWERED_IDLE,
                8,
                mean_lab,
                lab_to_srgb8(mean_lab),
                tuple(float(value) for value in np.max(std_values, axis=0)),
                max(pairwise),
                max(pairwise),
                0.0,
                False,
                f"screening-{measurement_sha[:16]}-{recipe_id}",
                measurement_sha,
                QualificationLevel.CANDIDATE,
            )
        )
    palette = HistoryPalette(
        palette_id,
        next(iter(calibration_ids)),
        "factory_otp",
        tuple(recipes),
    )
    output = Path(output_file)
    if output.exists():
        raise PaletteBuildError("output file already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(palette.mapping()) + b"\n"
    output.write_bytes(payload)
    return {
        "file": str(output.resolve()),
        "file_sha256": file_sha256(payload),
        "canonical_sha256": palette.mapping()["integrity"]["canonical_sha256"],
        "recipe_count": len(palette.recipes),
        "qualified_recipe_count": len(palette.qualified_recipes),
        "qualification_level": "SCREENING_CANDIDATE_ONLY",
        "rendering_allowed": False,
        "device_io_performed": False,
    }
