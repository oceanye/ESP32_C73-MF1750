from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from tools import mf1750_ec5_dither_atlas_photo_analyzer as analyzer


ROOT = Path(__file__).resolve().parents[1]
PREVIEW = (
    ROOT
    / ".test-output"
    / "offline"
    / "MF1750_EC5_DITHER_COLOR_ATLAS_OFFLINE_20260810_V1"
    / "strict-preview.png"
)


def test_strict_preview_yields_seventy_symmetric_roi_measurements(
    tmp_path: Path,
) -> None:
    output = tmp_path / "analysis"
    summary = analyzer.analyze(PREVIEW, output_dir=output)
    report = json.loads((output / "photo-analysis.json").read_text("utf-8"))

    assert summary["roi_count"] == 70
    assert summary["left_right_summary"] == {
        "count": 35,
        "mean_camera_delta_e76": 0.0,
        "maximum_camera_delta_e76": 0.0,
    }
    assert len(report["roi_measurements"]) == 70
    assert report["white_reference"] == {
        "provided": False,
        "source_rectangle": None,
        "uncalibrated_white_paper": True,
        "usable_for_camera_relative_normalization": False,
    }
    assert all(
        item["white_reference_relative"] is None for item in report["roi_measurements"]
    )
    assert report["evidence_boundaries"]["camera_relative_only"] is True
    assert (
        report["evidence_boundaries"]["new_single_pixel_pigment_state_inferred"]
        is False
    )
    unsigned = dict(report)
    unsigned.pop("integrity")
    assert report["integrity"]["canonical_sha256"] == analyzer._sha256(unsigned)
    assert (output / "rectified.png").is_file()
    assert (output / "annotated.png").is_file()


def test_rejects_nonconvex_or_tiny_corner_registration(tmp_path: Path) -> None:
    with pytest.raises(analyzer.PhotoAnalysisError, match="convex quad"):
        analyzer.analyze(
            PREVIEW,
            output_dir=tmp_path / "bad",
            corners_text="0,0 5,5 10,10 5,0",
        )


def test_refuses_to_overwrite_nonempty_output_directory(tmp_path: Path) -> None:
    output = tmp_path / "occupied"
    output.mkdir()
    (output / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(analyzer.PhotoAnalysisError, match="must not already contain"):
        analyzer.analyze(PREVIEW, output_dir=output)


def test_a4_white_reference_adds_camera_relative_measurements(tmp_path: Path) -> None:
    preview = cv2.imread(str(PREVIEW), cv2.IMREAD_COLOR)
    assert preview is not None
    canvas = np.full((800, 1400, 3), 96, dtype=np.uint8)
    canvas[100:700, 300:1324] = preview
    canvas[150:500, 20:250] = (210, 220, 230)
    photo = tmp_path / "panel-with-a4.png"
    assert cv2.imwrite(str(photo), canvas)

    output = tmp_path / "with-reference"
    summary = analyzer.analyze(
        photo,
        output_dir=output,
        corners_text="300,100 1323,100 1323,699 300,699",
        white_reference_text="20,150,250,500",
    )
    report = json.loads((output / "photo-analysis.json").read_text("utf-8"))
    reference = report["white_reference"]

    assert summary["roi_count"] == 70
    assert reference["provided"] is True
    assert reference["source_rectangle"] == {
        "x": 20,
        "y": 150,
        "x1_exclusive": 250,
        "y1_exclusive": 500,
        "pixel_count": 80500,
    }
    assert reference["camera_median_rgb"] == [230.0, 220.0, 210.0]
    assert reference["per_channel_high_clipped_fraction_rgb"] == [0.0, 0.0, 0.0]
    assert reference["any_channel_high_clipped_fraction"] == 0.0
    assert reference["usable_for_camera_relative_normalization"] is True
    assert report["evidence_boundaries"]["white_reference_provided"] is True
    relative = report["roi_measurements"][0]["white_reference_relative"]
    assert relative is not None
    assert len(relative["camera_mean_lab_offset_from_white_reference"]) == 3
    assert len(relative["camera_median_rgb_ratio_to_white_reference"]) == 3
    assert len(relative["camera_neutralized_median_rgb"]) == 3


@pytest.mark.parametrize(
    ("rectangle", "message"),
    [
        ("-1,0,100,100", "escapes the source photo"),
        ("0,0,10,10", "rectangle is too small"),
        ("0,0,nan,100", "non-finite coordinate"),
    ],
)
def test_rejects_invalid_a4_white_reference(
    tmp_path: Path, rectangle: str, message: str
) -> None:
    with pytest.raises(analyzer.PhotoAnalysisError, match=message):
        analyzer.analyze(
            PREVIEW,
            output_dir=tmp_path / "bad-reference",
            white_reference_text=rectangle,
        )
