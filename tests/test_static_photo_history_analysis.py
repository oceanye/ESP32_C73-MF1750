from __future__ import annotations

import json
from pathlib import Path

from host.static_photo.blue_history import build_blue_history_bundle
from host.static_photo.common import attach_integrity, canonical_json_bytes
from host.static_photo.history_analysis import analyze_history_photo
from host.static_photo.palette_builder import build_screening_palette


def _identity_calibration(path: Path) -> None:
    report = attach_integrity(
        {
            "schema_version": 1,
            "kind": "MF17506_CAMERA_SESSION_CALIBRATION",
            "calibration_mode": "REFERENCED_CALIBRATION",
            "quality": {"qualified": True},
            "model": {
                "matrix_rows_xyz_from_linear_rgb_plus_one": [
                    [0.4124564, 0.3575761, 0.1804375, 0.0],
                    [0.2126729, 0.7151522, 0.0721750, 0.0],
                    [0.0193339, 0.1191920, 0.9503041, 0.0],
                ]
            },
        }
    )
    path.write_bytes(canonical_json_bytes(report) + b"\n")


def test_mirrored_history_analysis_builds_screening_only_palette(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    build_blue_history_bundle(bundle)
    calibration = tmp_path / "calibration.json"
    _identity_calibration(calibration)
    corners = ((0.0, 0.0), (1023.0, 0.0), (1023.0, 599.0), (0.0, 599.0))
    analyses = []
    for batch in ("A", "A-prime"):
        output = tmp_path / f"analysis-{batch}"
        result = analyze_history_photo(
            bundle / f"{batch}-target-preview.png",
            panel_corners=corners,
            calibration_file=calibration,
            plan_manifest_file=bundle / "BLUE-HISTORY-MANIFEST.json",
            batch_id=batch,
            timepoint_seconds=60,
            output_dir=output,
        )
        assert result["measurement_count"] == 16
        assert result["device_io_performed"] is False
        analyses.append(output / "HISTORY-PHOTO-ANALYSIS.json")
    palette_result = build_screening_palette(
        analyses,
        output_file=tmp_path / "HISTORY-PALETTE.json",
        palette_id="screening-blue-v1",
        primer_dwell_ms=2000,
        temperature_min_c=24.0,
        temperature_max_c=26.0,
    )
    palette = json.loads((tmp_path / "HISTORY-PALETTE.json").read_text("utf-8"))
    assert palette_result["recipe_count"] == 16
    assert palette_result["qualified_recipe_count"] == 0
    assert palette_result["rendering_allowed"] is False
    assert all(
        recipe["qualification_level"] == "CANDIDATE" for recipe in palette["recipes"]
    )
    assert all(recipe["minimum_recipe_cell_px"] == 8 for recipe in palette["recipes"])
