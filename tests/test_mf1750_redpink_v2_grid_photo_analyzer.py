from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from tools import mf1750_redpink_v2_grid_photo_analyzer as analyzer


PALETTE_RGB = np.array(
    [
        [188, 52, 78],
        [217, 153, 145],
        [203, 116, 115],
        [55, 50, 79],
        [171, 103, 65],
        [53, 93, 180],
        [45, 111, 94],
        [239, 238, 232],
    ],
    dtype=np.float64,
)


def _logical_grid(
    ordinal: int, *, paired_outlier: tuple[int, int] | None = None
) -> np.ndarray:
    image = np.full(
        (analyzer.LOGICAL_HEIGHT, analyzer.LOGICAL_WIDTH, 3),
        [238, 238, 233],
        dtype=np.uint8,
    )
    for controller in range(2):
        for row in range(8):
            for column in range(8):
                if ordinal == 2:
                    rgb = PALETTE_RGB[column].copy()
                elif ordinal == 3:
                    # Runtime code 7 behaves as the unqualified separator/hold
                    # path in this campaign.  The real action-03 photo retains
                    # source-column colours in its eighth row, so model that
                    # evidence instead of inventing a white physical colour.
                    rgb = PALETTE_RGB[row if row < 7 else column].copy()
                else:
                    rgb = np.array(
                        [160, 165, 72] if controller == 0 else [187, 74, 100],
                        dtype=np.float64,
                    )
                    smooth_scale = 0.90 + 0.025 * row + 0.012 * column
                    rgb *= smooth_scale
                    if paired_outlier == (row, column):
                        rgb += np.array([38, 34, 30], dtype=np.float64)
                x0, y0, x1, y1 = analyzer._logical_bounds(controller, row, column)
                image[y0:y1, x0:x1] = np.clip(rgb[::-1], 0, 255).astype(np.uint8)
    return image


def _photo_bytes(
    ordinal: int,
    *,
    paired_outlier: tuple[int, int] | None = None,
    crop_panel_bottom: bool = False,
) -> bytes:
    logical = _logical_grid(ordinal, paired_outlier=paired_outlier)
    source = np.float32(
        [
            [0, 0],
            [analyzer.LOGICAL_WIDTH, 0],
            [analyzer.LOGICAL_WIDTH, analyzer.LOGICAL_HEIGHT],
            [0, analyzer.LOGICAL_HEIGHT],
        ]
    )
    bottom_y = 930 if crop_panel_bottom else 830
    destination = np.float32(
        [[150, 105], [1290, 72], [1328, bottom_y], [112, bottom_y - 14]]
    )
    matrix = cv2.getPerspectiveTransform(source, destination)
    photo = np.full((900, 1440, 3), [213, 210, 206], dtype=np.uint8)
    warped = cv2.warpPerspective(
        logical,
        matrix,
        (photo.shape[1], photo.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )
    coverage = cv2.warpPerspective(
        np.full(logical.shape[:2], 255, dtype=np.uint8),
        matrix,
        (photo.shape[1], photo.shape[0]),
        flags=cv2.INTER_NEAREST,
    )
    photo[coverage > 0] = warped[coverage > 0]
    rng = np.random.default_rng(1750 + ordinal)
    noise = rng.normal(0.0, 1.2, photo.shape)
    photo = np.clip(photo.astype(np.float64) + noise, 0, 255).astype(np.uint8)
    ok, encoded = cv2.imencode(".jpg", photo, [cv2.IMWRITE_JPEG_QUALITY, 94])
    assert ok
    return encoded.tobytes()


def _write_photo(
    path: Path,
    ordinal: int,
    *,
    paired_outlier: tuple[int, int] | None = None,
    crop_panel_bottom: bool = False,
) -> bytes:
    payload = _photo_bytes(
        ordinal,
        paired_outlier=paired_outlier,
        crop_panel_bottom=crop_panel_bottom,
    )
    path.write_bytes(payload)
    return payload


def _write_low_chroma_high_resolution_photo(path: Path) -> bytes:
    """Create a 4000x3000 dual grid that saturation contours cannot see."""

    logical = np.full(
        (analyzer.LOGICAL_HEIGHT, analyzer.LOGICAL_WIDTH, 3),
        [235, 235, 235],
        dtype=np.uint8,
    )
    for controller in range(2):
        for row in range(8):
            for column in range(8):
                # Both BGR colours have deliberately low saturation but a
                # strong luminance edge against the separator/background.
                base = np.array(
                    [151, 156, 161] if controller == 0 else [132, 137, 142],
                    dtype=np.int16,
                )
                base += row + column // 2
                x0, y0, x1, y1 = analyzer._logical_bounds(controller, row, column)
                logical[y0:y1, x0:x1] = np.clip(base, 0, 255).astype(np.uint8)
    source = np.float32(
        [
            [0, 0],
            [analyzer.LOGICAL_WIDTH, 0],
            [analyzer.LOGICAL_WIDTH, analyzer.LOGICAL_HEIGHT],
            [0, analyzer.LOGICAL_HEIGHT],
        ]
    )
    destination = np.float32([[520, 640], [3440, 585], [3500, 2690], [570, 2615]])
    matrix = cv2.getPerspectiveTransform(source, destination)
    photo = np.full((3000, 4000, 3), [205, 203, 201], dtype=np.uint8)
    warped = cv2.warpPerspective(
        logical,
        matrix,
        (photo.shape[1], photo.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )
    coverage = cv2.warpPerspective(
        np.full(logical.shape[:2], 255, dtype=np.uint8),
        matrix,
        (photo.shape[1], photo.shape[0]),
        flags=cv2.INTER_NEAREST,
    )
    photo[coverage > 0] = warped[coverage > 0]
    ok, encoded = cv2.imencode(".jpg", photo, [cv2.IMWRITE_JPEG_QUALITY, 94])
    assert ok
    payload = encoded.tobytes()
    path.write_bytes(payload)
    return payload


def test_action2_fits_white_like_eighth_column_and_binds_sha256(tmp_path: Path) -> None:
    photo = tmp_path / "camera-action-02.jpg"
    payload = _write_photo(photo, 2, crop_panel_bottom=True)

    report = analyzer.analyze(photo)

    assert report["source_photo"]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert report["campaign_layout"]["action_ordinal"] == 2
    assert report["grid_judgement"]["enough_to_interpret_grid_camera_relatively"]
    assert (
        report["geometry_quality"]["visible_columns_used_to_initialize_each_side"] == 7
    )
    assert len(report["cells"]) == 128
    assert {cell["column"] for cell in report["cells"]} == set(range(8))
    assert report["candidate_ranking_metadata"]["screening_applicable"] is False


def test_action3_perspective_grid_reports_rows_columns_and_all_cells(
    tmp_path: Path,
) -> None:
    photo = tmp_path / "camera-action-03.jpg"
    _write_photo(photo, 3)

    report = analyzer.analyze(photo)

    assert (
        report["grid_judgement"]["verdict"] == "SUFFICIENT_CAMERA_RELATIVE_GRID_READOUT"
    )
    assert report["geometry_quality"]["homography_inlier_rmse_px"] < 3.0
    assert (
        report["geometry_quality"]["sampling"]["minimum_inner_patch_valid_fraction"]
        == 1.0
    )
    assert len(report["row_column_differences"]) == 32
    assert len(report["recipe_candidate_ranking"]) == 64
    assert all(len(cell["camera_relative_lab"]) == 3 for cell in report["cells"])


def test_action4_paired_outlier_ranks_above_smooth_gradient(tmp_path: Path) -> None:
    photo = tmp_path / "camera-action-04.jpg"
    _write_photo(photo, 4, paired_outlier=(5, 3))

    report = analyzer.analyze(photo)

    ranking = report["recipe_candidate_ranking"]
    target = next(item for item in ranking if item["row"] == 5 and item["column"] == 3)
    assert ranking.index(target) < 3
    assert target["paired_obvious_spatial_outlier"] is True
    assert report["candidate_ranking_metadata"]["obvious_paired_recipe_count"] >= 1
    assert (
        report["candidate_ranking_metadata"]["camera_relative_spatial_assessment"]
        == "OBVIOUS_PAIRED_CELL_OUTLIER_BEYOND_SMOOTH_SPATIAL_TREND"
    )


def test_low_chroma_4000x3000_dual_grid_uses_strict_edge_fallback(
    tmp_path: Path,
) -> None:
    photo = tmp_path / "g1-low-chroma-action-04.jpg"
    payload = _write_low_chroma_high_resolution_photo(photo)

    report = analyzer.analyze(photo, ordinal=4)

    geometry = report["geometry_quality"]
    assert report["source_photo"]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert geometry["rectangle_detection_method"] == analyzer._EDGE_DETECTION_METHOD
    assert geometry["saturation_contour_threshold"] is None
    assert geometry["unique_cell_contour_support"] == 128
    assert geometry["support_by_controller"] == [64, 64]
    assert geometry["homography_inliers"] == 128
    assert geometry["homography_correspondences"] == 128
    assert geometry["homography_inlier_rmse_px"] <= 2.0
    assert geometry["homography_inlier_p95_px"] <= 3.0
    assert geometry["sampling"]["all_cell_corners_inside_photo"] is True
    assert len(report["cells"]) == 128
    assert all(cell["contour_support_detected"] for cell in report["cells"])
    assert all(len(cell["camera_relative_lab"]) == 3 for cell in report["cells"])
    observations = [cell["contour_observation"] for cell in report["cells"]]
    assert len(observations) == 128
    assert all(item["independent_detected_contour"] for item in observations)
    assert all(item["not_geometry_inferred"] for item in observations)
    assert all(item["contour_area_px2"] > 0 for item in observations)
    assert all(item["rectangularity"] >= 0.55 for item in observations)
    assert all(
        item["detection_method"] == analyzer._EDGE_DETECTION_METHOD
        for item in observations
    )
    assert "strict closed-edge 2x8x8 fallback" in geometry["mapping_basis"]


def test_legacy_saturation_path_does_not_gain_edge_metadata(tmp_path: Path) -> None:
    photo = tmp_path / "camera-action-04.jpg"
    _write_photo(photo, 4)

    report = analyzer.analyze(photo)

    geometry = report["geometry_quality"]
    assert geometry["saturation_contour_threshold"] in analyzer._THRESHOLDS
    assert "rectangle_detection_method" not in geometry
    assert "edge_canny_thresholds" not in geometry
    assert all("contour_observation" not in cell for cell in report["cells"])


def test_analysis_rejects_photo_without_grid(tmp_path: Path) -> None:
    photo = tmp_path / "empty.jpg"
    ok, encoded = cv2.imencode(".jpg", np.full((600, 800, 3), 220, dtype=np.uint8))
    assert ok
    photo.write_bytes(encoded.tobytes())

    with pytest.raises(
        analyzer.GridPhotoAnalysisError, match="no saturation threshold"
    ):
        analyzer.analyze(photo, ordinal=4)


def test_integrity_is_deterministic_and_covers_report_without_integrity(
    tmp_path: Path,
) -> None:
    photo = tmp_path / "camera-action-03.jpg"
    _write_photo(photo, 3)

    first = analyzer.analyze(photo)
    second = analyzer.analyze(photo)
    integrity = first.pop("integrity")

    assert first == {key: value for key, value in second.items() if key != "integrity"}
    assert (
        integrity["sha256"]
        == hashlib.sha256(analyzer._canonical_json(first)).hexdigest()
    )


def test_cli_output_uses_exclusive_creation(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    photo = tmp_path / "camera-action-04.jpg"
    output = tmp_path / "analysis.json"
    _write_photo(photo, 4)

    assert (
        analyzer.main(
            [
                "analyze",
                "--photo",
                str(photo),
                "--ordinal",
                "4",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    stdout, stderr = capfd.readouterr()
    assert stderr == ""
    assert json.loads(stdout)["source_photo"]["path"] == str(photo)
    original = output.read_bytes()

    assert (
        analyzer.main(
            [
                "analyze",
                "--photo",
                str(photo),
                "--ordinal",
                "4",
                "--output",
                str(output),
            ]
        )
        == 2
    )
    _, stderr = capfd.readouterr()
    assert "refusing to overwrite" in stderr
    assert output.read_bytes() == original
