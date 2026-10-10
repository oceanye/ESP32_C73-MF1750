from __future__ import annotations

import copy

import numpy as np
import pytest

from tools import (
    mf1750_raw_p16_crossover_position_balanced_photo_analyzer as geometry,
)
from tools import (
    mf1750_raw_p16_crossover_w2_discovery_successor_clean_white_residual as screen,
)
from tools import (
    mf1750_raw_p16_crossover_w2_discovery_successor_pack as pack,
)


CORNERS = np.asarray(
    [[100.0, 100.0], [1900.0, 100.0], [1900.0, 1100.0], [100.0, 1100.0]]
)


def _binding(stage: str) -> dict:
    return {
        "stage": stage,
        "capture_alignment": {
            "instance_id": "vid_32e4&pid_4801-fixed",
            "mount_id": "mf1750-48mp-fixed-20260828",
            "requested_settings": {"exposure": -6.0},
            "effective_settings_before_frame": {"exposure": -6.0},
            "effective_settings_after_frame": {"exposure": -6.0},
            "photo_width": 2000,
            "photo_height": 1200,
        },
        "analysis_path": f"{stage}.analysis.json",
        "external_post_capture_verdict": "PASS",
        "external_post_capture_verdict_used_for_residual_classification": False,
    }


def _patch_sources(
    monkeypatch: pytest.MonkeyPatch, w1: np.ndarray, w2: np.ndarray
) -> None:
    def load(_path, *, stage):
        rgb = w1 if stage == "w1-after-t1" else w2
        return copy.deepcopy(_binding(stage)), rgb, {}

    monkeypatch.setattr(screen, "_load_white", load)


def _verify_seal(report: dict) -> None:
    unsigned = {key: value for key, value in report.items() if key != "integrity"}
    assert report["integrity"] == {
        "algorithm": screen.INTEGRITY_ALGORITHM,
        "sha256": screen.strict.sha256_bytes(screen.strict.canonical_json(unsigned)),
    }


def test_identical_locked_white_frames_pass_without_using_external_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    w1 = np.full((1200, 2000, 3), 220, dtype=np.uint8)
    _patch_sources(monkeypatch, w1, w1.copy())

    report = screen.evaluate("w1.json", "w2.json", panel_corners=CORNERS)

    assert report["summary"]["classification"] == "PASS"
    assert report["summary"]["external_post_capture_verdict_used"] is False
    assert report["absolute_white_proven"] is False
    assert report["qualified_colour_count"] == 0
    assert report["formal_gate_changed"] is False
    assert len(report["atlas_samples"]) == 64
    assert len(report["full_panel_grid"]["samples"]) == 24 * 12
    _verify_seal(report)


def test_one_retained_atlas_rectangle_fails_atlas_maximum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cv2, _np = geometry.base._import_cv()  # noqa: SLF001
    w1 = np.full((1200, 2000, 3), 220, dtype=np.uint8)
    w2 = w1.copy()
    homography, _report = geometry._fit_panel_homography(  # noqa: SLF001
        CORNERS, photo_width=2000, photo_height=1200
    )
    cell = geometry._all_logical_cells()[5]  # noqa: SLF001
    x, y, width, height = cell["logical_bounds"]
    polygon = geometry.base._project(  # noqa: SLF001
        homography,
        ((x, y), (x + width, y), (x + width, y + height), (x, y + height)),
    )
    cv2.fillConvexPoly(w2, np.rint(polygon).astype(np.int32), (180, 20, 20))
    _patch_sources(monkeypatch, w1, w2)

    report = screen.evaluate("w1.json", "w2.json", panel_corners=CORNERS)

    assert report["summary"]["classification"] == "FAIL"
    assert report["summary"]["atlas_residual_candidate_detected"] is True
    assert (
        report["summary"]["component_classifications"]["atlas_cell_maximum"] == "FAIL"
    )


def test_horizontal_colour_stripe_is_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    w1 = np.full((1200, 2000, 3), 220, dtype=np.uint8)
    w2 = w1.copy()
    w2[520:680, 100:1900] = (40, 100, 180)
    _patch_sources(monkeypatch, w1, w2)

    report = screen.evaluate("w1.json", "w2.json", panel_corners=CORNERS)

    assert report["summary"]["classification"] == "FAIL"
    assert report["summary"]["horizontal_stripe_candidate_detected"] is True
    assert (
        report["summary"]["component_classifications"]["horizontal_row_median_maximum"]
        == "FAIL"
    )


def test_camera_alignment_mismatch_fails_before_pixel_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    white = np.full((1200, 2000, 3), 220, dtype=np.uint8)

    def load(_path, *, stage):
        binding = _binding(stage)
        if stage == pack.STAGE:
            binding["capture_alignment"]["mount_id"] = "moved"
        return binding, white, {}

    monkeypatch.setattr(screen, "_load_white", load)
    with pytest.raises(screen.WhiteResidualScreenError, match="camera instance"):
        screen.evaluate("w1.json", "w2.json", panel_corners=CORNERS)


def test_expected_w2_identity_is_derived_from_fresh_pack() -> None:
    expected = screen._expected_white(pack.STAGE)  # noqa: SLF001
    report = pack.build_white_report()

    assert expected["campaign_id"] == pack.CONFIG.campaign_id
    assert expected["contract_id"] == report["contract_id"]
    assert expected["action_id"] == report["action"]["action_id"]
    assert expected["descriptor_id"] == report["action"]["descriptor_id"]
    assert expected["firmware_sha256"] == pack.WHITE_ARTIFACTS[pack.STAGE]["bin_sha256"]


def test_thresholds_and_exclusive_writer_are_frozen(tmp_path) -> None:
    assert screen._classify(6.0, pass_max=6.0, review_max=10.0) == "PASS"  # noqa: SLF001
    assert screen._classify(6.1, pass_max=6.0, review_max=10.0) == "REVIEW"  # noqa: SLF001
    assert screen._classify(10.1, pass_max=6.0, review_max=10.0) == "FAIL"  # noqa: SLF001
    output = tmp_path / "residual.json"
    screen._write_exclusive(output, b"first\n")  # noqa: SLF001
    with pytest.raises(screen.WhiteResidualScreenError, match="overwrite"):
        screen._write_exclusive(output, b"second\n")  # noqa: SLF001
