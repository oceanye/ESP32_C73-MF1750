from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pytest

from tools import (
    mf1750_raw_p16_crossover_t2_discovery_successor_v2_white_normalized_coarse_screen as screen,
)
from tools import (
    mf1750_raw_p16_crossover_w3_discovery_successor_v2_white_pack as w3_pack,
)


ALIGNMENT = {
    "instance_id": "vid_32e4&pid_4801-fixed",
    "mount_id": "mf1750-48mp-fixed-20260828",
    "requested_settings": {"exposure": -3.0},
    "effective_settings_before_frame": {"exposure": -3.0},
    "effective_settings_after_frame": {"exposure": -3.0},
    "photo_width": 4000,
    "photo_height": 3000,
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


def _patch_inputs(
    monkeypatch: pytest.MonkeyPatch, *, residual_state: str = "PASS"
) -> None:
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
                "input_bindings": {
                    "fresh_successor_v2_w3": {"analysis_path": "w3.json"}
                },
            },
            b"residual",
        )

    def load_white(_path, *, stage):
        assert stage == w3_pack.STAGE
        return (
            {
                "analysis_path": "w3.json",
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


def test_three_exact_exp3_frames_plus_clean_w3_pass_all_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_inputs(monkeypatch)

    report = screen.screen(
        ["t2-v2-1.json", "t2-v2-2.json", "t2-v2-3.json"],
        "w3.json",
        "w2-w3-residual.json",
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
    assert report["normalization_contract"]["white_reference_min_lstar"] == 25.0
    assert report["normalization_contract"]["automatic_threshold_relaxation"] is False
    assert report["threshold_contract"] == {
        **screen.EXPECTED_COARSE_THRESHOLDS,
        "automatic_threshold_relaxation": False,
    }
    assert all(
        "t2_v2_rgb_median" in cell and "t1_rgb_median" not in cell
        for group in report["group_results"]
        for frame in group["frame_results"]
        for cell in frame["cells"]
        if cell["valid"]
    )
    _verify_seal(report)


def test_nonpass_w2_w3_residual_blocks_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_inputs(monkeypatch, residual_state="REVIEW")
    with pytest.raises(screen.T2V2CoarseScreenError, match="must PASS"):
        screen.screen(
            ["t2-v2-1.json", "t2-v2-2.json", "t2-v2-3.json"],
            "w3.json",
            "w2-w3-residual.json",
        )


def test_alignment_and_exact_exposure_are_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_inputs(monkeypatch)
    original = screen._deep_t2  # noqa: SLF001

    def moved(path, *, index):
        root, binding = original(path, index=index)
        if index == 2:
            binding["capture_alignment"]["mount_id"] = "moved"
        return root, binding

    monkeypatch.setattr(screen, "_deep_t2", moved)
    with pytest.raises(screen.T2V2CoarseScreenError, match="fingerprint"):
        screen.screen(
            ["t2-v2-1.json", "t2-v2-2.json", "t2-v2-3.json"],
            "w3.json",
            "w2-w3-residual.json",
        )

    _patch_inputs(monkeypatch)
    original = screen._deep_t2  # noqa: SLF001

    def underexposed(path, *, index):
        root, binding = original(path, index=index)
        binding["capture_alignment"]["requested_settings"]["exposure"] = -6.0
        return root, binding

    monkeypatch.setattr(screen, "_deep_t2", underexposed)
    with pytest.raises(screen.T2V2CoarseScreenError, match="exposure=-3"):
        screen.screen(
            ["t2-v2-1.json", "t2-v2-2.json", "t2-v2-3.json"],
            "w3.json",
            "w2-w3-residual.json",
        )


def test_exactly_three_distinct_t2_v2_analyses_are_required() -> None:
    with pytest.raises(screen.T2V2CoarseScreenError, match="three distinct"):
        screen.screen(["same.json"] * 3, "w3.json", "w2-w3-residual.json")


def test_lstar_25_gate_and_t2_v2_field_name_are_preserved() -> None:
    t2 = {
        "cell_id": "CS1-R0-C0-CODE0",
        "controller": 0,
        "row": 0,
        "column": 0,
        "code": 0,
        "robust_rgb_median": [80.0, 40.0, 20.0],
    }
    valid_white = {
        "robust_rgb_median": [220.0, 220.0, 220.0],
        "camera_relative_lab_d65_from_rgb_median": [25.0, 0.0, 0.0],
    }
    invalid_white = {
        "robust_rgb_median": [220.0, 220.0, 220.0],
        "camera_relative_lab_d65_from_rgb_median": [24.999999, 0.0, 0.0],
    }

    valid = screen._normalized_t2_v2_cell(t2, valid_white)  # noqa: SLF001
    invalid = screen._normalized_t2_v2_cell(t2, invalid_white)  # noqa: SLF001

    assert valid["valid"] is True
    assert valid["t2_v2_rgb_median"] == [80.0, 40.0, 20.0]
    assert "t1_rgb_median" not in valid
    assert invalid["valid"] is False
    assert invalid["invalid_reason"] == "WHITE_REFERENCE_LSTAR_BELOW_25"


def test_cli_names_only_v2_w3_chain() -> None:
    args = screen.parse_args(
        [
            "--t2-analysis",
            "t2-v2-1.json",
            "t2-v2-2.json",
            "t2-v2-3.json",
            "--w3-analysis",
            "w3.json",
            "--w2-w3-residual",
            "w2-w3.json",
            "--output",
            "coarse.json",
        ]
    )
    assert args.t2_analysis == [
        Path("t2-v2-1.json"),
        Path("t2-v2-2.json"),
        Path("t2-v2-3.json"),
    ]
    assert args.w3_analysis == Path("w3.json")
    assert args.w2_w3_residual == Path("w2-w3.json")
