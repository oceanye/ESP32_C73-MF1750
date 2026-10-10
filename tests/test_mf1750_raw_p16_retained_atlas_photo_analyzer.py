from __future__ import annotations

import copy
import math

import numpy as np
import pytest

from tools import mf1750_camera_capture_evidence as camera
from tools import mf1750_raw_p16_retained_atlas_photo_analyzer as analyzer


def _camera_record() -> dict:
    requested = {
        "fourcc": "MJPG",
        "frame_width": 4000,
        "frame_height": 3000,
        "fps": 15.0,
        "autofocus": 0.0,
        "focus": 79.0,
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
        **requested,
        "fps": 15.000015000015,
        "autofocus": 2,
        "auto_exposure": -1,
    }
    return {
        "schema_version": camera.SCHEMA_VERSION,
        "kind": camera.KIND,
        "capture_binding": camera.BINDING_LOCKED_RETAINED,
        "coverage": {
            "scope": camera.COVERAGE_FULL,
            "full_panel_visible": True,
            "full_panel_uncropped": True,
            "mount_id": "mf1750-48mp-fixed",
        },
        "camera": {
            "camera_id": camera.TARGET_CAMERA_FRIENDLY_NAME,
            "instance_id": (
                r"@device_pnp_\\?\usb#vid_32e4&pid_4801&mi_00#"
                r"6&22675d4e&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"
            ),
            "backend": "DSHOW",
            "requested_settings": requested,
            "effective_settings_before_frame": effective,
            "effective_settings_after_frame": copy.deepcopy(effective),
            "set_results": {
                key: True for key, value in requested.items() if value is not None
            },
            "read_failures": 0,
            "warmup_frames_requested": 5,
            "warmup_frames_completed": 5,
        },
    }


def _project(homography: np.ndarray, point: list[float]) -> np.ndarray:
    homogeneous = homography @ np.asarray([point[0], point[1], 1.0])
    return homogeneous[:2] / homogeneous[2]


def test_layout_is_only_four_by_two_row_major_per_controller() -> None:
    cells = analyzer._all_logical_cells()

    assert len(cells) == 16
    assert [item["code"] for item in cells[:8]] == list(range(8))
    assert [item["code"] for item in cells[8:]] == list(range(8))
    assert [(item["row"], item["column"]) for item in cells[:8]] == [
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
        (2, 0),
        (2, 1),
        (3, 0),
        (3, 1),
    ]
    assert cells[2]["logical_bounds"][:2] == [36, 180]
    assert cells[8]["logical_bounds"][0] == 548
    assert not hasattr(analyzer, "GRID_COLUMNS_OLD_2X4")


def test_detects_and_fits_current_photo_style_fourteen_cell_lattice() -> None:
    cv2, _np = analyzer._import_cv()
    rgb = np.full((3000, 4000, 3), 18, dtype=np.uint8)
    logical_panel = np.asarray(
        [[0, 0], [1024, 0], [1024, 600], [0, 600]], dtype=np.float32
    )
    photo_panel = np.asarray(
        [[700, 650], [3000, 710], [3100, 2020], [600, 1950]], dtype=np.float32
    )
    homography = cv2.getPerspectiveTransform(logical_panel, photo_panel)
    cv2.fillConvexPoly(rgb, np.rint(photo_panel).astype(np.int32), (215, 225, 235))
    colours = {
        1: (20, 95, 70),
        2: (15, 40, 180),
        3: (150, 70, 35),
        4: (20, 20, 35),
        5: (150, 35, 65),
        6: (30, 80, 110),
        7: (165, 155, 60),
    }
    for cell in analyzer._all_logical_cells():
        if cell["code"] == 0:
            continue
        x, y, width, height = cell["logical_bounds"]
        polygon = analyzer._project(
            homography,
            ((x, y), (x + width, y), (x + width, y + height), (x, y + height)),
        )
        cv2.fillConvexPoly(
            rgb,
            np.rint(polygon).astype(np.int32),
            colours[cell["code"]],
        )

    candidates = analyzer._detect_rectangles(rgb)
    fitted, correspondences, statistics = analyzer._fit_auto_homography(candidates)

    assert len(candidates) == 14
    assert len(correspondences) == 14
    assert statistics["rmse_px"] < 1.0
    predicted = _project(fitted, [888.0, 516.0])
    expected = _project(homography, [888.0, 516.0])
    assert np.linalg.norm(predicted - expected) < 2.0


def test_sampling_uses_row_major_code_not_historical_two_by_four() -> None:
    rgb = np.full((600, 1024, 3), 240, dtype=np.uint8)
    colours = {
        code: (10 + code * 20, 20 + code * 15, 30 + code * 10) for code in range(8)
    }
    for cell in analyzer._all_logical_cells():
        x, y, width, height = cell["logical_bounds"]
        colour = colours[cell["code"]]
        rgb[y : y + height, x : x + width] = colour

    identity = np.eye(3, dtype=np.float64)
    sampled = [
        analyzer._sample_cell(rgb, identity, cell)
        for cell in analyzer._all_logical_cells()
    ]

    assert sampled[2]["cell_id"] == "C0-CODE2"
    assert sampled[2]["row"] == 1
    assert sampled[2]["column"] == 0
    assert sampled[2]["robust_rgb_median"] == [50.0, 50.0, 50.0]
    assert sampled[10]["cell_id"] == "C1-CODE2"
    assert sampled[10]["robust_rgb_median"] == [50.0, 50.0, 50.0]


def test_fixed_camera_gate_accepts_only_48mp_manual_exposure_minus_six() -> None:
    capture = _camera_record()

    lock = analyzer._validate_fixed_capture(capture)

    assert lock["usb_vid"] == "32E4"
    assert lock["usb_pid"] == "4801"
    assert lock["fixed_exposure_boundary"] == -6.0

    wrong_camera = copy.deepcopy(capture)
    wrong_camera["camera"]["camera_id"] = "USB Camera"
    wrong_camera["camera"]["instance_id"] = (
        r"@device_pnp_\\?\usb#vid_1bcf&pid_0b15&mi_00#x#{guid}\global"
    )
    with pytest.raises(analyzer.RawP16PhotoAnalysisError, match="48MP"):
        analyzer._validate_fixed_capture(wrong_camera)

    wrong_exposure = copy.deepcopy(capture)
    wrong_exposure["camera"]["requested_settings"]["exposure"] = -3.0
    wrong_exposure["camera"]["effective_settings_before_frame"]["exposure"] = -3.0
    wrong_exposure["camera"]["effective_settings_after_frame"]["exposure"] = -3.0
    with pytest.raises(analyzer.RawP16PhotoAnalysisError, match="exposure"):
        analyzer._validate_fixed_capture(wrong_exposure)


def test_partial_coverage_requires_explicit_opt_in_and_never_relaxes_full_default() -> None:
    partial = _camera_record()
    partial["coverage"].update(
        {
            "scope": camera.COVERAGE_PARTIAL,
            "full_panel_visible": False,
            "full_panel_uncropped": False,
        }
    )

    with pytest.raises(
        analyzer.RawP16PhotoAnalysisError, match="complete, visible, uncropped"
    ):
        analyzer._validate_fixed_capture(partial)

    lock = analyzer._validate_fixed_capture(
        partial, expected_coverage_scope=camera.COVERAGE_PARTIAL
    )
    assert lock["fixed_exposure_boundary"] == -6.0

    with pytest.raises(
        analyzer.RawP16PhotoAnalysisError, match="partial-panel coverage"
    ):
        analyzer._validate_fixed_capture(
            _camera_record(), expected_coverage_scope=camera.COVERAGE_PARTIAL
        )


def test_pairwise_summary_is_explicitly_nonqualifying() -> None:
    cells = []
    for controller in range(2):
        for code in range(8):
            lab = [50.0, 0.0, 0.0]
            if controller == 1 and code == 5:
                lab = [75.0, 25.0, 20.0]
            cells.append(
                {
                    "controller": controller,
                    "code": code,
                    "cell_id": f"C{controller}-CODE{code}",
                    "camera_relative_lab_d65_from_rgb_median": lab,
                }
            )

    pairs, summary = analyzer._pair_summary(cells)

    assert summary["obvious_left_right_difference_candidates"] == [5]
    assert summary["controller_equivalence_proven"] is False
    assert pairs[5]["qualification_effect"] == "NONE"
    assert math.isfinite(pairs[5]["delta_e00_camera_relative"])


@pytest.mark.parametrize(
    "value",
    (
        "0,0;100,0;100,100",
        "0,0;0,100;100,100;100,0",
        "0,0;100,0;nan,100;0,100",
    ),
)
def test_explicit_current_photo_corners_fail_closed(value: str) -> None:
    with pytest.raises(analyzer.RawP16PhotoAnalysisError):
        analyzer._parse_panel_corners(value)
