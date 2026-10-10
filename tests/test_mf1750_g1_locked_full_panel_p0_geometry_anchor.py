from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from tools import mf1750_g1_locked_full_panel_p0_geometry_anchor as anchor


WIDTH = 1920
HEIGHT = 1080


def _settings() -> tuple[dict[str, Any], dict[str, Any]]:
    requested = {
        "fourcc": "MJPG",
        "frame_width": WIDTH,
        "frame_height": HEIGHT,
        "fps": 30.0,
        "autofocus": 0.0,
        "focus": 12.0,
        "auto_exposure": 0.25,
        "exposure": -6.0,
        "auto_white_balance": 0.0,
        "white_balance_temperature": 4600.0,
        "brightness": None,
        "contrast": None,
        "saturation": None,
        "hue": None,
    }
    effective = {
        "fourcc": "MJPG",
        "frame_width": WIDTH,
        "frame_height": HEIGHT,
        "fps": 30.0,
        "autofocus": 2,
        "focus": 12,
        "auto_exposure": -1,
        "exposure": -6,
        "auto_white_balance": 0,
        "white_balance_temperature": 4600,
        "brightness": 0,
        "contrast": 32,
        "saturation": 64,
        "hue": 0,
    }
    return requested, effective


def _capture_root(photo_payload: bytes) -> dict[str, Any]:
    requested, effective = _settings()
    return {
        "capture_binding": "locked_retained_retrospective",
        "capture_id": "capture-g1",
        "captured_at": "2026-08-28T20:00:00.000+08:00",
        "campaign_id": "ACTION4-GEOMETRY-G1",
        "test_id": "ACTION4-GEOMETRY-G1-P0",
        "action_id": "1" * 64,
        "ordinal": 4,
        "role": "REDPINK_FIXED_TARGET_ACTIVE_CODE0",
        "camera": {
            "camera_id": "mf1750-camera",
            "instance_id": "usb-instance-one",
            "index": 0,
            "backend": "DSHOW",
            "requested_settings": requested,
            "effective_settings_before_frame": effective,
            "effective_settings_after_frame": deepcopy(effective),
            "set_results": {
                "fourcc": True,
                "frame_width": True,
                "frame_height": True,
                "fps": True,
                "autofocus": True,
                "focus": True,
                "auto_exposure": True,
                "exposure": True,
                "auto_white_balance": True,
                "white_balance_temperature": True,
            },
            "warmup_frames_requested": 10,
            "warmup_frames_completed": 10,
            "read_failures": 0,
        },
        "photo": {
            "path": "action4-g1.jpg",
            "bytes": len(photo_payload),
            "sha256": hashlib.sha256(photo_payload).hexdigest(),
            "width": WIDTH,
            "height": HEIGHT,
            "mode": "RGB",
        },
        "coverage": {
            "scope": "full_panel",
            "full_panel_visible": True,
            "full_panel_uncropped": True,
            "mount_id": "locked-mount-one",
        },
        "integrity": {
            "algorithm": anchor.INTEGRITY_ALGORITHM,
            "sha256": "2" * 64,
        },
    }


def _cells() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for controller in range(2):
        for row in range(8):
            for column in range(8):
                x0 = 100 + controller * 800 + column * 70
                y0 = 100 + row * 100
                result.append(
                    {
                        "cell_id": f"C{controller}-R{row}-K{column}",
                        "controller": controller,
                        "row": row,
                        "column": column,
                        "recipe_id": f"REDPINK-A{column}-B{row}-A0",
                        "logical_bounds": [
                            controller * 512 + 20 + column * 60,
                            40 + row * 66,
                            controller * 512 + 72 + column * 60,
                            98 + row * 66,
                        ],
                        "projected_photo_corners": [
                            [x0, y0],
                            [x0 + 45, y0],
                            [x0 + 45, y0 + 50],
                            [x0, y0 + 50],
                        ],
                        "all_corners_inside_photo": True,
                        "inner_patch_valid_fraction": 1.0,
                        "contour_support_detected": True,
                    }
                )
    return result


def _grid(photo_payload: bytes) -> dict[str, Any]:
    root: dict[str, Any] = {
        "schema_version": 1,
        "kind": anchor.GRID_KIND,
        "source_photo": {
            "path": "action4-g1.jpg",
            "bytes": len(photo_payload),
            "sha256": hashlib.sha256(photo_payload).hexdigest(),
            "width": WIDTH,
            "height": HEIGHT,
        },
        "campaign_layout": {
            "id": anchor.GRID_LAYOUT_ID,
            "action_ordinal": 4,
            "controllers_are_not_assumed_colour_equivalent": True,
        },
        "method": {
            "perspective_rectified": True,
            "all_128_logical_cells_sampled": True,
            "physical_colour_calibrated": False,
        },
        "geometry_quality": {
            "unique_cell_contour_support": 128,
            "expected_coloured_contour_support_for_action": 128,
            "support_fraction_of_action_expectation": 1.0,
            "support_by_controller": [64, 64],
            "homography_logical_to_photo": [
                [1.0, 0.0, 100.0],
                [0.0, 1.0, 100.0],
                [0.0, 0.0, 1.0],
            ],
            "homography_inliers": 128,
            "homography_correspondences": 128,
            "homography_inlier_fraction": 1.0,
            "homography_inlier_rmse_px": 0.6,
            "homography_inlier_p95_px": 1.1,
            "sampling": {
                "minimum_inner_patch_valid_fraction": 1.0,
                "all_cell_corners_inside_photo": True,
                "minimum_projected_cell_width_px": 45.0,
                "minimum_projected_cell_height_px": 50.0,
            },
        },
        "grid_judgement": {
            "enough_to_interpret_grid_camera_relatively": True,
            "verdict": "SUFFICIENT_CAMERA_RELATIVE_GRID_READOUT",
            "blocking_reasons": [],
            "camera_relative_only": True,
            "photo_dimensions": [WIDTH, HEIGHT],
        },
        "cells": _cells(),
        "row_column_differences": {},
        "smooth_spatial_models": {},
        "candidate_ranking_metadata": {},
        "cell_candidate_ranking": [],
        "recipe_candidate_ranking": [],
    }
    root["integrity"] = {
        "algorithm": anchor.INTEGRITY_ALGORITHM,
        "sha256": anchor._sha256_bytes(anchor._canonical_json(root)),
    }
    return root


def _install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    photo_payload = b"synthetic-action4-photo"
    (tmp_path / "action4-g1.jpg").write_bytes(photo_payload)
    sidecar = tmp_path / "action4-g1.capture.json"
    sidecar.write_text('{"deep-validator-input":true}\n', encoding="utf-8")
    capture_root = _capture_root(photo_payload)
    calls: list[Path] = []

    def validate(path: Path) -> dict[str, Any]:
        calls.append(Path(path))
        return deepcopy(capture_root)

    monkeypatch.setattr(anchor.camera, "validate_capture_evidence", validate)
    grid_root = _grid(photo_payload)
    grid = tmp_path / "action4-g1.grid-analysis.json"
    grid.write_text(json.dumps(grid_root, sort_keys=True), encoding="utf-8")
    capture_root["_validator_calls"] = calls
    return sidecar, grid, capture_root, grid_root


def test_build_anchor_freezes_lock_geometry_and_retrospective_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar, grid, capture_root, _ = _install(tmp_path, monkeypatch)

    report = anchor.build_anchor(sidecar, grid)

    assert capture_root["_validator_calls"] == [sidecar]
    assert report["kind"] == anchor.KIND
    assert report["camera_lock"]["camera_tuple"] == {
        "camera_id": "mf1750-camera",
        "instance_id": "usb-instance-one",
        "index": 0,
        "backend": "DSHOW",
    }
    assert report["camera_lock"]["effective_readback_equal"] is True
    normalization = report["camera_lock"]["manual_mode_readback_normalization"]
    assert normalization["policy"] == "DSHOW_DRIVER_SPECIFIC_RAW_ENUM_V1"
    assert normalization["effective_raw_values"] == {
        "autofocus": 2.0,
        "auto_exposure": -1.0,
        "auto_white_balance": 0.0,
    }
    assert normalization["driver_specific_normalization_used"] is True
    assert report["capture"]["captured_at"] == capture_root["captured_at"]
    assert report["grid_analysis"]["source_photo_sha256"] == report["photo"]["sha256"]
    assert len(report["geometry_p0"]["cell_anchors"]) == 128
    assert len(report["geometry_p0"]["p0_recipe_map"]) == 64
    assert report["classification"]["state"] == anchor.CLASSIFICATION
    assert report["classification"]["live_action_evidence"] is False
    assert report["classification"]["temporal_action_continuity_proven"] is False
    unsigned = deepcopy(report)
    integrity = unsigned.pop("integrity")
    assert integrity == {
        "algorithm": anchor.INTEGRITY_ALGORITHM,
        "sha256": anchor._sha256_bytes(anchor._canonical_json(unsigned)),
    }


def test_retrospective_input_is_never_upgraded_to_live_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar, grid, capture_root, _ = _install(tmp_path, monkeypatch)
    capture_root["capture_binding"] = "retrospective_unproven"

    report = anchor.build_anchor(sidecar, grid)

    assert report["capture"]["capture_binding"] == "retrospective_unproven"
    assert report["classification"]["retrospective_only"] is True
    assert report["classification"]["input_live_binding_was_not_propagated"] is False
    assert report["classification"]["action_causality_proven"] is False


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda root: root["coverage"].update(
                {"scope": "partial_panel", "full_panel_uncropped": False}
            ),
            "full_panel",
        ),
        (
            lambda root: root["camera"]["requested_settings"].update(
                {"auto_exposure": 1.0}
            ),
            "requested.auto_exposure",
        ),
        (
            lambda root: root["camera"]["effective_settings_after_frame"].update(
                {"focus": 13}
            ),
            "effective readback changed",
        ),
        (
            lambda root: root["camera"]["set_results"].update({"focus": False}),
            "setting writes failed",
        ),
        (
            lambda root: root["camera"]["effective_settings_before_frame"].update(
                {"exposure": -7}
            )
            or root["camera"]["effective_settings_after_frame"].update(
                {"exposure": -7}
            ),
            "effective.exposure must equal",
        ),
        (
            lambda root: root["camera"]["effective_settings_before_frame"].update(
                {"autofocus": 7}
            )
            or root["camera"]["effective_settings_after_frame"].update(
                {"autofocus": 7}
            ),
            "not an accepted DSHOW",
        ),
    ],
)
def test_rejects_unlocked_or_incomplete_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation,
    message: str,
) -> None:
    sidecar, grid, capture_root, _ = _install(tmp_path, monkeypatch)
    mutation(capture_root)

    with pytest.raises(anchor.G1P0GeometryAnchorError, match=message):
        anchor.build_anchor(sidecar, grid)


def test_rejects_grid_tamper_photo_mismatch_and_weak_geometry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar, grid, _, grid_root = _install(tmp_path, monkeypatch)
    grid_root["geometry_quality"]["homography_inlier_rmse_px"] = 2.1
    grid_root["integrity"] = {
        "algorithm": anchor.INTEGRITY_ALGORITHM,
        "sha256": anchor._sha256_bytes(
            anchor._canonical_json(
                {key: value for key, value in grid_root.items() if key != "integrity"}
            )
        ),
    }
    grid.write_text(json.dumps(grid_root, sort_keys=True), encoding="utf-8")
    with pytest.raises(anchor.G1P0GeometryAnchorError, match="residual"):
        anchor.build_anchor(sidecar, grid)

    grid_root = _grid(b"different-photo")
    grid.write_text(json.dumps(grid_root, sort_keys=True), encoding="utf-8")
    with pytest.raises(anchor.G1P0GeometryAnchorError, match="source photo bytes"):
        anchor.build_anchor(sidecar, grid)

    grid_root = _grid(b"synthetic-action4-photo")
    grid_root["campaign_layout"]["action_ordinal"] = 3
    grid.write_text(json.dumps(grid_root, sort_keys=True), encoding="utf-8")
    with pytest.raises(anchor.G1P0GeometryAnchorError, match="integrity"):
        anchor.build_anchor(sidecar, grid)


def test_main_writes_o_excl_and_refuses_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sidecar, grid, _, _ = _install(tmp_path, monkeypatch)
    output = tmp_path / "g1-anchor.json"
    arguments = [
        "--capture-sidecar",
        str(sidecar),
        "--grid-analysis",
        str(grid),
        "--output",
        str(output),
    ]

    assert anchor.main(arguments) == 0
    first = output.read_bytes()
    assert json.loads(first)["output_write_contract"] == "O_EXCL"
    assert anchor.main(arguments) == 2
    assert output.read_bytes() == first
    assert "refusing to overwrite" in capsys.readouterr().err
