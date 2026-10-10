from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from tools import mf1750_same_r20_atlas_photo_analyzer as analyzer


def _sign(value: dict) -> dict:
    value = dict(value)
    value["integrity"] = {
        "algorithm": analyzer.INTEGRITY_ALGORITHM,
        "sha256": analyzer._sha256_bytes(analyzer._canonical_json(value)),
    }
    return value


def _reference(path: Path) -> Path:
    root = _sign(
        {
            "schema_version": 1,
            "kind": analyzer.REFERENCE_KIND,
            "source_photo": {
                "path": "reference.png",
                "bytes": 1,
                "sha256": "0" * 64,
                "width": analyzer.LOGICAL_WIDTH,
                "height": analyzer.LOGICAL_HEIGHT,
            },
            "campaign_layout": {"id": analyzer.REFERENCE_LAYOUT},
            "grid_judgement": {"enough_to_interpret_grid_camera_relatively": True},
            "geometry_quality": {"homography_logical_to_photo": np.eye(3).tolist()},
        }
    )
    path.write_text(json.dumps(root), encoding="utf-8")
    return path


def _photo(path: Path, *, right_offset: int = 0) -> Path:
    image = np.full(
        (analyzer.LOGICAL_HEIGHT, analyzer.LOGICAL_WIDTH, 3),
        245,
        dtype=np.uint8,
    )
    colours = [
        (20, 20, 20),
        (30, 30, 210),
        (30, 210, 30),
        (210, 30, 30),
        (30, 180, 210),
        (210, 120, 30),
        (180, 30, 180),
        (210, 210, 210),
    ]
    for controller in range(2):
        for code, colour in enumerate(colours):
            row, column = divmod(code, 4)
            x0, y0, x1, y1 = analyzer._logical_bounds(controller, row, column)
            adjusted = tuple(
                max(0, min(255, channel + (right_offset if controller else 0)))
                for channel in colour
            )
            image[y0:y1, x0:x1] = adjusted[::-1]
    assert cv2.imwrite(str(path), image)
    return path


def test_identical_controller_atlas_is_camera_relative_match(tmp_path: Path) -> None:
    result = analyzer.analyze(
        _photo(tmp_path / "atlas.png"),
        _reference(tmp_path / "reference.json"),
        role="AA",
        repeat_noise_p95_de76=0.5,
    )
    assert result["geometry_guard"]["reference_homography_alignment_guard_pass"]
    assert (
        result["classification"]["state"]
        == "CAMERA_RELATIVE_CONTROLLER_MATCH_CANDIDATE"
    )
    assert result["paired_summary"]["camera_relative_de76_max"] == 0.0
    assert result["classification"]["controller_equivalence_proven"] is False


def test_shifted_right_controller_is_mismatch_candidate(tmp_path: Path) -> None:
    result = analyzer.analyze(
        _photo(tmp_path / "atlas.png", right_offset=35),
        _reference(tmp_path / "reference.json"),
        role="CC",
        repeat_noise_p95_de76=0.5,
    )
    assert (
        result["classification"]["state"]
        == "CAMERA_RELATIVE_CONTROLLER_MISMATCH_CANDIDATE"
    )


def test_without_noise_baseline_stays_inconclusive(tmp_path: Path) -> None:
    result = analyzer.analyze(
        _photo(tmp_path / "atlas.png"),
        _reference(tmp_path / "reference.json"),
        role="AA",
    )
    assert (
        result["classification"]["state"]
        == "INCONCLUSIVE_NEEDS_NOISE_BASELINE_OR_GEOMETRY"
    )


def test_tampered_reference_is_rejected(tmp_path: Path) -> None:
    reference = _reference(tmp_path / "reference.json")
    value = json.loads(reference.read_text("utf-8"))
    value["source_photo"]["width"] += 1
    reference.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(analyzer.SameR20AtlasAnalysisError, match="integrity"):
        analyzer.analyze(
            _photo(tmp_path / "atlas.png"),
            reference,
            role="AA",
        )


def test_exclusive_output_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "analysis.json"
    analyzer._write_exclusive(output, b"first")
    with pytest.raises(
        analyzer.SameR20AtlasAnalysisError, match="refusing to overwrite"
    ):
        analyzer._write_exclusive(output, b"second")
