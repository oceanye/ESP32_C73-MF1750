from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from tools import mf1750_same_r20_atlas_photo_analyzer as common
from tools import mf1750_true_r20_hold_photo_gate as gate


def _sign(value: dict) -> dict:
    value = dict(value)
    value["integrity"] = {
        "algorithm": common.INTEGRITY_ALGORITHM,
        "sha256": common._sha256_bytes(common._canonical_json(value)),
    }
    return value


def _reference(path: Path) -> Path:
    value = _sign(
        {
            "schema_version": 1,
            "kind": common.REFERENCE_KIND,
            "source_photo": {
                "path": "reference.png",
                "bytes": 1,
                "sha256": "0" * 64,
                "width": common.LOGICAL_WIDTH,
                "height": common.LOGICAL_HEIGHT,
            },
            "campaign_layout": {"id": common.REFERENCE_LAYOUT},
            "grid_judgement": {"enough_to_interpret_grid_camera_relatively": True},
            "geometry_quality": {"homography_logical_to_photo": np.eye(3).tolist()},
        }
    )
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


COLOURS = {
    "A": (30, 30, 210),
    "B": (30, 180, 30),
    "C": (30, 200, 210),
}


def _photo(
    path: Path, coloured: tuple[str, ...], *, bottom_fault: str | None = None
) -> Path:
    image = np.full(
        (common.LOGICAL_HEIGHT, common.LOGICAL_WIDTH, 3), 245, dtype=np.uint8
    )
    for controller in range(2):
        for name in coloured:
            x, y, width, height = gate._global_bounds(controller, gate.ROI_LOCAL[name])
            image[y : y + height, x : x + width] = COLOURS[name][::-1]
            if bottom_fault == name:
                image[y + height - 6 : y + height, x : x + width] = 0
    assert cv2.imwrite(str(path), image)
    return path


def test_stage_b_holds_a_adds_b_and_preserves_white(tmp_path: Path) -> None:
    white = _photo(tmp_path / "white.png", ())
    before = _photo(tmp_path / "before.png", ("A",))
    after = _photo(tmp_path / "after.png", ("A", "B"))
    result = gate.analyze(
        before,
        after,
        white,
        _reference(tmp_path / "reference.json"),
        stage="B",
        repeat_noise_p95_de76=0.5,
    )
    assert (
        result["classification"]["state"]
        == "STATIC_HOLD_GATE_PASS_VIDEO_STILL_REQUIRED"
    )
    assert result["classification"]["qualified_cross_r20_hold"] is False


def test_protected_roi_change_fails_static_gate(tmp_path: Path) -> None:
    white = _photo(tmp_path / "white.png", ())
    before = _photo(tmp_path / "before.png", ("A",))
    after = _photo(tmp_path / "after.png", ("B",))
    result = gate.analyze(
        before,
        after,
        white,
        _reference(tmp_path / "reference.json"),
        stage="B",
        repeat_noise_p95_de76=0.5,
    )
    assert result["classification"]["state"] == "STATIC_HOLD_GATE_FAIL"
    assert result["protected_hold_results"][0]["within_hold_threshold"] is False


def test_bottom_edge_fault_is_detected(tmp_path: Path) -> None:
    white = _photo(tmp_path / "white.png", ())
    before = _photo(tmp_path / "before.png", ())
    after = _photo(tmp_path / "after.png", ("A",), bottom_fault="A")
    result = gate.analyze(
        before,
        after,
        white,
        _reference(tmp_path / "reference.json"),
        stage="A",
        repeat_noise_p95_de76=0.5,
    )
    assert result["classification"]["state"] == "STATIC_HOLD_GATE_FAIL"
    assert any(item["bottom_edge_anomaly"] for item in result["edge_results"])


def test_white_stage_confirms_all_three_rois_cleared(tmp_path: Path) -> None:
    white = _photo(tmp_path / "white.png", ())
    before = _photo(tmp_path / "before.png", ("A", "B", "C"))
    after = _photo(tmp_path / "after.png", ())
    result = gate.analyze(
        before,
        after,
        white,
        _reference(tmp_path / "reference.json"),
        stage="WHITE",
        repeat_noise_p95_de76=0.5,
    )
    assert (
        result["classification"]["state"]
        == "STATIC_HOLD_GATE_PASS_VIDEO_STILL_REQUIRED"
    )
    assert len(result["expected_white_results"]) == 6


def test_without_noise_baseline_remains_inconclusive(tmp_path: Path) -> None:
    white = _photo(tmp_path / "white.png", ())
    before = _photo(tmp_path / "before.png", ())
    after = _photo(tmp_path / "after.png", ("A",))
    result = gate.analyze(
        before,
        after,
        white,
        _reference(tmp_path / "reference.json"),
        stage="A",
    )
    assert (
        result["classification"]["state"] == "INCONCLUSIVE_NEEDS_REPEAT_NOISE_BASELINE"
    )
