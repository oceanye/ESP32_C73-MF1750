from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from host.color_pipeline.color import srgb8_to_lab
from host.static_photo.chart_calibration import ChartCapture, calibrate_chart
from host.static_photo.chart_spec import (
    ChartPatch,
    ChartSpec,
    ReferenceGrade,
    chart_spec_from_mapping,
)


def _colours() -> list[tuple[int, int, int]]:
    return [
        (
            (index * 47 + 31) % 206 + 25,
            (index * 83 + 17) % 206 + 25,
            (index * 29 + 71) % 206 + 25,
        )
        for index in range(24)
    ]


def _spec(referenced: bool = True) -> ChartSpec:
    colours = _colours()
    patches = tuple(
        ChartPatch(
            f"P{index + 1:02d}",
            index // 6,
            index % 6,
            srgb8_to_lab(colours[index]) if referenced else None,
        )
        for index in range(24)
    )
    return ChartSpec(
        "synthetic-24-v1",
        "synthetic",
        "fixture",
        4,
        6,
        ReferenceGrade.VENDOR_REFERENCE if referenced else ReferenceGrade.LAYOUT_ONLY,
        "synthetic test values",
        hashlib.sha256(b"synthetic references").hexdigest() if referenced else None,
        "D65",
        "2deg",
        0.2,
        patches,
    )


def _photo(path: Path) -> None:
    image = np.zeros((640, 960, 3), dtype=np.uint8)
    for index, rgb in enumerate(_colours()):
        row, column = divmod(index, 6)
        image[row * 160 : (row + 1) * 160, column * 160 : (column + 1) * 160] = rgb[
            ::-1
        ]
    assert cv2.imwrite(str(path), image)


def test_referenced_three_capture_chart_calibration_is_traceable(
    tmp_path: Path,
) -> None:
    spec = _spec()
    assert chart_spec_from_mapping(spec.mapping()) == spec
    photos = []
    for ordinal in range(3):
        path = tmp_path / f"chart-{ordinal}.png"
        _photo(path)
        photos.append(path)
    corners = ((0.0, 0.0), (959.0, 0.0), (959.0, 639.0), (0.0, 639.0))
    result = calibrate_chart(
        spec,
        tuple(ChartCapture(path, corners) for path in photos),
        output_dir=tmp_path / "out",
    )
    report = json.loads(
        (tmp_path / "out" / "CAMERA-CALIBRATION.json").read_text("utf-8")
    )

    assert result["calibration_mode"] == "REFERENCED_CALIBRATION"
    assert result["qualified"] is True
    assert report["quality"]["qualified"] is True
    assert report["quality"]["delta_e00_summary"]["median_fit"] < 0.2
    assert report["quality"]["delta_e00_summary"]["median_leave_one_out"] < 0.5
    assert len(report["patches"]) == 24
    assert report["evidence_boundaries"]["device_io_performed"] is False
    assert (tmp_path / "out" / "chart-annotated.png").is_file()
    assert (tmp_path / "out" / "patch-measurements.csv").is_file()


def test_layout_only_single_capture_stays_camera_relative(tmp_path: Path) -> None:
    path = tmp_path / "chart.png"
    _photo(path)
    corners = ((0.0, 0.0), (959.0, 0.0), (959.0, 639.0), (0.0, 639.0))
    result = calibrate_chart(
        _spec(referenced=False),
        (ChartCapture(path, corners),),
        output_dir=tmp_path / "relative",
    )
    report = json.loads(
        (tmp_path / "relative" / "CAMERA-CALIBRATION.json").read_text("utf-8")
    )
    assert result["calibration_mode"] == "CAMERA_RELATIVE"
    assert result["qualified"] is False
    assert report["model"]["matrix_rows_xyz_from_linear_rgb_plus_one"] is None
    assert all(item["delta_e00"] is None for item in report["patches"])
