from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from tools import mf1750_runtime_lut_same_r20_parity_4x8_v2_pack as pack
from tools import mf1750_same_r20_position_balanced_4x8_analyzer as analyzer


def _write_g1(path: Path) -> None:
    value = {
        "schema_version": 1,
        "kind": analyzer.G1_KIND,
        "geometry_quality": {
            "homography_logical_to_photo": np.eye(3).tolist(),
            "homography_inliers": 128,
            "homography_correspondences": 128,
            "homography_inlier_fraction": 1.0,
            "homography_inlier_rmse_px": 0.0,
            "homography_inlier_p95_px": 0.0,
        },
    }
    value["integrity"] = {
        "algorithm": analyzer.INTEGRITY_ALGORITHM,
        "sha256": analyzer.sha256_bytes(analyzer.canonical_json(value)),
    }
    path.write_text(json.dumps(value), encoding="utf-8")


COLORS_BGR = (
    (25, 25, 25),
    (230, 230, 230),
    (20, 220, 230),
    (30, 40, 220),
    (200, 80, 40),
    (220, 110, 35),
    (45, 145, 50),
    (175, 175, 175),
)


def _atlas(
    *, right_code_shift: int | None = None, position_shift: bool = False
) -> np.ndarray:
    image = np.full((600, 1024, 3), COLORS_BGR[7], dtype=np.uint8)
    for controller in range(2):
        for row, codes in enumerate(pack.CODE_ROWS):
            for column, code in enumerate(codes):
                x, y, width, height = pack.cell_bounds(row, column)
                x += controller * 512
                colour = np.array(COLORS_BGR[code], dtype=np.int16)
                if controller == 1 and code == right_code_shift:
                    colour = np.clip(colour + np.array((45, -35, 25)), 0, 255)
                if position_shift and controller == 0 and code == 2 and row == 2:
                    colour = np.clip(colour + 80, 0, 255)
                image[y : y + height, x : x + width] = colour.astype(np.uint8)
    return image


def _write_set(
    tmp_path: Path,
    *,
    right_code_shift: int | None = None,
    position_shift: bool = False,
    noisy_white: bool = False,
) -> tuple[Path, list[Path], list[Path]]:
    g1 = tmp_path / "g1.json"
    _write_g1(g1)
    whites: list[Path] = []
    atlases: list[Path] = []
    for index in range(3):
        white = np.full((600, 1024, 3), 230, dtype=np.uint8)
        if noisy_white and index == 2:
            white[:, :512] = (60, 100, 210)
        white_path = tmp_path / f"white-{index}.png"
        atlas_path = tmp_path / f"atlas-{index}.png"
        assert cv2.imwrite(str(white_path), white)
        assert cv2.imwrite(
            str(atlas_path),
            _atlas(
                right_code_shift=right_code_shift,
                position_shift=position_shift,
            ),
        )
        whites.append(white_path)
        atlases.append(atlas_path)
    return g1, whites, atlases


def test_symmetric_atlas_is_camera_relative_parity_candidate(tmp_path: Path) -> None:
    g1, whites, atlases = _write_set(tmp_path)
    result = analyzer.analyze(g1_analysis=g1, white_photos=whites, atlas_photos=atlases)
    assert result["classification"] == analyzer.CAMERA_RELATIVE_PARITY_CANDIDATE
    assert result["absolute_colour_proven"] is False
    for item in result["controller_comparison"]["per_code"]:
        assert [ctrl["sample_count"] for ctrl in item["controllers"]] == [12, 12]
        assert [ctrl["position_count"] for ctrl in item["controllers"]] == [4, 4]


def test_one_code_right_side_shift_is_code_dependent_mismatch(tmp_path: Path) -> None:
    g1, whites, atlases = _write_set(tmp_path, right_code_shift=2)
    result = analyzer.analyze(g1_analysis=g1, white_photos=whites, atlas_photos=atlases)
    assert result["classification"] == (
        analyzer.CODE_DEPENDENT_CONTROLLER_MISMATCH_CANDIDATE
    )


def test_one_of_four_positions_shifted_is_position_inconclusive(tmp_path: Path) -> None:
    g1, whites, atlases = _write_set(tmp_path, position_shift=True)
    result = analyzer.analyze(g1_analysis=g1, white_photos=whites, atlas_photos=atlases)
    assert result["classification"] == analyzer.POSITION_DEPENDENT_INCONCLUSIVE


def test_noisy_new_white_baseline_fails_first(tmp_path: Path) -> None:
    g1, whites, atlases = _write_set(tmp_path, noisy_white=True)
    result = analyzer.analyze(g1_analysis=g1, white_photos=whites, atlas_photos=atlases)
    assert result["classification"] == analyzer.WHITE_BASELINE_OR_GEOMETRY_INVALID
    assert result["white_temporal_noise"]["pass"] is False


def test_severely_underexposed_frames_fail_closed_before_parity(
    tmp_path: Path,
) -> None:
    g1, whites, atlases = _write_set(tmp_path)
    for path in (*whites, *atlases):
        assert cv2.imwrite(str(path), np.full((600, 1024, 3), 12, dtype=np.uint8))

    result = analyzer.analyze(g1_analysis=g1, white_photos=whites, atlas_photos=atlases)

    assert result["classification"] == (analyzer.LOW_EXPOSURE_OR_DYNAMIC_RANGE_INVALID)
    quality = result["exposure_quality"]
    assert quality["pass"] is False
    assert quality["minimum_observed_panel_median_lstar"] < (
        analyzer.MIN_PANEL_MEDIAN_LSTAR
    )
    assert quality["fixed_panel_median_floor_lstar"] == 25.0


def test_atlas_dynamic_range_compression_fails_closed_at_normal_lightness(
    tmp_path: Path,
) -> None:
    g1, whites, atlases = _write_set(tmp_path)
    for path in atlases:
        assert cv2.imwrite(str(path), np.full((600, 1024, 3), 128, dtype=np.uint8))

    result = analyzer.analyze(g1_analysis=g1, white_photos=whites, atlas_photos=atlases)

    assert result["classification"] == (analyzer.LOW_EXPOSURE_OR_DYNAMIC_RANGE_INVALID)
    quality = result["exposure_quality"]
    assert quality["minimum_observed_panel_median_lstar"] > (
        analyzer.MIN_PANEL_MEDIAN_LSTAR
    )
    assert quality["minimum_observed_atlas_p95_minus_p05_lstar"] == 0.0
    assert quality["pass"] is False


def test_output_is_o_excl(tmp_path: Path) -> None:
    output = tmp_path / "result.json"
    analyzer.write_new(output, {"ok": True})
    try:
        analyzer.write_new(output, {"ok": False})
    except analyzer.PositionBalancedAnalysisError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("second write unexpectedly overwrote evidence")
