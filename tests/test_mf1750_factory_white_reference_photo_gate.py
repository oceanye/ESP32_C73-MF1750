from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from tools import mf1750_factory_white_reference_photo_gate as gate
from tools import mf1750_same_r20_atlas_photo_analyzer as common


def _reference(path: Path) -> Path:
    unsigned = {
        "schema_version": 1,
        "kind": common.REFERENCE_KIND,
        "campaign_layout": {"id": common.REFERENCE_LAYOUT},
        "source_photo": {"width": 1024, "height": 600},
        "geometry_quality": {
            "homography_logical_to_photo": np.eye(3).tolist(),
        },
        "grid_judgement": {
            "enough_to_interpret_grid_camera_relatively": True,
        },
    }
    unsigned["integrity"] = {
        "algorithm": common.INTEGRITY_ALGORITHM,
        "sha256": common._sha256_bytes(common._canonical_json(unsigned)),
    }
    path.write_text(json.dumps(unsigned), encoding="utf-8")
    return path


def _photo(path: Path, value: int, *, fault: bool = False) -> Path:
    image = np.full((600, 1024, 3), value, dtype=np.uint8)
    if fault:
        image[300:560, 520:990] = (20, 20, 220)
    assert cv2.imwrite(str(path), image)
    return path


def test_matching_factory_white_passes(tmp_path: Path) -> None:
    reference_grid = _reference(tmp_path / "grid.json")
    white = _photo(tmp_path / "white.png", 240)
    candidate = _photo(tmp_path / "candidate.png", 239)
    result = gate.analyze(
        candidate,
        white,
        reference_grid,
        repeat_noise_p95_de76=1.0,
    )
    assert result["classification"]["pass"] is True
    assert result["summary"]["patch_count"] == 60
    assert result["classification"]["absolute_white_proven"] is False


def test_coloured_half_panel_fails(tmp_path: Path) -> None:
    reference_grid = _reference(tmp_path / "grid.json")
    white = _photo(tmp_path / "white.png", 240)
    candidate = _photo(tmp_path / "candidate.png", 240, fault=True)
    result = gate.analyze(
        candidate,
        white,
        reference_grid,
        repeat_noise_p95_de76=1.0,
    )
    assert result["classification"]["pass"] is False
    assert result["summary"]["camera_relative_de76_max"] > 8.0


def test_missing_noise_stays_inconclusive(tmp_path: Path) -> None:
    result = gate.analyze(
        _photo(tmp_path / "candidate.png", 239),
        _photo(tmp_path / "white.png", 240),
        _reference(tmp_path / "grid.json"),
    )
    assert result["classification"]["pass"] is None


def test_identical_input_path_is_rejected(tmp_path: Path) -> None:
    white = _photo(tmp_path / "white.png", 240)
    with pytest.raises(gate.FactoryWhiteReferencePhotoGateError, match="must differ"):
        gate.analyze(white, white, _reference(tmp_path / "grid.json"))
