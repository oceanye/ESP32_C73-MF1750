from __future__ import annotations

import copy

import numpy as np
import pytest

from tools import (
    mf1750_raw_p16_crossover_t2_discovery_successor_white_normalized_coarse_screen as screen,
)
from tools import (
    mf1750_raw_p16_crossover_w2_discovery_successor_pack as w2_pack,
)


ALIGNMENT = {
    "instance_id": "vid_32e4&pid_4801-fixed",
    "mount_id": "mf1750-48mp-fixed-20260828",
    "requested_settings": {"exposure": -6.0},
    "effective_settings_before_frame": {"exposure": -6.0},
    "effective_settings_after_frame": {"exposure": -6.0},
    "photo_width": 1024,
    "photo_height": 600,
}


def _root(index: int) -> dict:
    colours = {
        0: [150.0, 30.0, 40.0],
        1: [220.0, 220.0, 220.0],
        2: [210.0, 190.0, 20.0],
        3: [30.0, 30.0, 30.0],
        4: [30.0, 120.0, 70.0],
        5: [30.0, 70.0, 160.0],
        6: [70.0, 80.0, 160.0],
        7: [100.0, 50.0, 130.0],
    }
    cells = []
    for cell in screen.analyzer.legacy._all_logical_cells():  # noqa: SLF001
        item = dict(cell)
        item["robust_rgb_median"] = colours[cell["code"]]
        cells.append(item)
    return {
        "geometry": {
            "homography_logical_to_current_photo": [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
            ]
        },
        "cells": cells,
        "index": index,
    }


def _patch_inputs(monkeypatch: pytest.MonkeyPatch, *, residual_state="PASS") -> None:
    def deep_t2(path, *, index):
        return _root(index), {
            "analysis_path": str(path),
            "analysis_file_sha256": f"{index}" * 64,
            "capture_alignment": copy.deepcopy(ALIGNMENT),
        }

    def validate_residual(_path):
        return (
            {
                "summary": {"classification": residual_state},
                "integrity": {"sha256": "a" * 64},
                "input_bindings": {"fresh_successor_w2": {"analysis_path": "w2.json"}},
            },
            b"residual",
        )

    def load_white(_path, *, stage):
        assert stage == w2_pack.STAGE
        return (
            {
                "analysis_path": "w2.json",
                "capture_alignment": copy.deepcopy(ALIGNMENT),
            },
            np.full((600, 1024, 3), 220, dtype=np.uint8),
            {},
        )

    monkeypatch.setattr(screen, "_deep_t2", deep_t2)
    monkeypatch.setattr(screen.residual, "validate_report", validate_residual)
    monkeypatch.setattr(screen.residual, "_load_white", load_white)


def _verify_seal(report: dict) -> None:
    unsigned = {key: value for key, value in report.items() if key != "integrity"}
    assert report["integrity"] == {
        "algorithm": screen.INTEGRITY_ALGORITHM,
        "sha256": screen.strict.sha256_bytes(screen.strict.canonical_json(unsigned)),
    }


def test_three_frames_plus_algorithmic_w2_pass_all_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_inputs(monkeypatch)

    report = screen.screen(
        ["t2-1.json", "t2-2.json", "t2-3.json"],
        "w2.json",
        "w2-residual.json",
    )

    assert report["summary"]["classification_counts"] == {
        "PASS": 16,
        "REVIEW": 0,
        "FAIL": 0,
    }
    assert report["coarse_profile_comparison_ready"] is True
    assert report["formal_gate_evaluated"] is False
    assert report["formal_gate_changed"] is False
    assert report["qualified_colour_count"] == 0
    assert (
        report["normalization_contract"][
            "external_post_capture_verdict_used_as_white_algorithm"
        ]
        is False
    )
    assert all(
        "t2_rgb_median" in cell and "t1_rgb_median" not in cell
        for group in report["group_results"]
        for frame in group["frame_results"]
        for cell in frame["cells"]
        if cell["valid"]
    )
    _verify_seal(report)


def test_nonpass_w2_residual_blocks_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_inputs(monkeypatch, residual_state="REVIEW")
    with pytest.raises(screen.T2CoarseScreenError, match="must PASS"):
        screen.screen(
            ["t2-1.json", "t2-2.json", "t2-3.json"],
            "w2.json",
            "w2-residual.json",
        )


def test_mismatched_camera_lock_blocks_screen(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_inputs(monkeypatch)
    original = screen._deep_t2  # noqa: SLF001

    def changed(path, *, index):
        root, binding = original(path, index=index)
        if index == 2:
            binding["capture_alignment"]["mount_id"] = "moved"
        return root, binding

    monkeypatch.setattr(screen, "_deep_t2", changed)
    with pytest.raises(screen.T2CoarseScreenError, match="fingerprint"):
        screen.screen(
            ["t2-1.json", "t2-2.json", "t2-3.json"],
            "w2.json",
            "w2-residual.json",
        )


def test_exactly_three_distinct_t2_analyses_are_required() -> None:
    with pytest.raises(screen.T2CoarseScreenError, match="three distinct"):
        screen.screen(["same.json"] * 3, "w2.json", "w2-residual.json")


def test_normalized_cell_uses_t2_field_name() -> None:
    t2 = {
        "cell_id": "CS1-R0-C0-CODE0",
        "controller": 0,
        "row": 0,
        "column": 0,
        "code": 0,
        "robust_rgb_median": [80.0, 40.0, 20.0],
    }
    white = {
        "robust_rgb_median": [220.0, 220.0, 220.0],
        "camera_relative_lab_d65_from_rgb_median": [90.0, 0.0, 0.0],
    }

    result = screen._normalized_t2_cell(t2, white)  # noqa: SLF001

    assert result["t2_rgb_median"] == [80.0, 40.0, 20.0]
    assert "t1_rgb_median" not in result
