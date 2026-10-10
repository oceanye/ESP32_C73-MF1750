from __future__ import annotations

import copy

import numpy as np
import pytest

from tools import (
    mf1750_raw_p16_crossover_w2_discovery_successor_clean_white_residual as frozen,
)
from tools import (
    mf1750_raw_p16_crossover_w2_discovery_successor_pack as w2_pack,
)
from tools import (
    mf1750_raw_p16_crossover_w3_discovery_successor_v2_clean_white_residual as screen,
)
from tools import (
    mf1750_raw_p16_crossover_w3_discovery_successor_v2_white_pack as w3_pack,
)


CORNERS = np.asarray(
    [[100.0, 100.0], [1900.0, 100.0], [1900.0, 1100.0], [100.0, 1100.0]]
)


def _binding(stage: str, *, exposure: float = -3.0) -> dict:
    return {
        "stage": stage,
        "capture_alignment": {
            "instance_id": "vid_32e4&pid_4801-fixed",
            "mount_id": "mf1750-48mp-fixed-20260828",
            "requested_settings": {"exposure": exposure},
            "effective_settings_before_frame": {"exposure": exposure},
            "effective_settings_after_frame": {"exposure": exposure},
            "photo_width": 4000,
            "photo_height": 3000,
        },
        "analysis_path": f"{stage}.analysis.json",
        "external_post_capture_verdict": "PASS",
        "external_post_capture_verdict_used_for_residual_classification": False,
    }


def _patch_sources(
    monkeypatch: pytest.MonkeyPatch, w2: np.ndarray, w3: np.ndarray
) -> None:
    def load(_path, *, stage):
        rgb = w2 if stage == w2_pack.STAGE else w3
        return copy.deepcopy(_binding(stage)), rgb, {}

    monkeypatch.setattr(screen, "_load_white", load)


def _verify_seal(report: dict) -> None:
    unsigned = {key: value for key, value in report.items() if key != "integrity"}
    assert report["integrity"] == {
        "algorithm": screen.INTEGRITY_ALGORITHM,
        "sha256": screen.strict.sha256_bytes(screen.strict.canonical_json(unsigned)),
    }


def test_identical_exact_exp3_white_frames_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    w2 = np.full((1200, 2000, 3), 220, dtype=np.uint8)
    _patch_sources(monkeypatch, w2, w2.copy())

    report = screen.evaluate("w2.json", "w3.json", panel_corners=CORNERS)

    assert report["summary"]["classification"] == "PASS"
    assert report["summary"]["external_post_capture_verdict_used"] is False
    assert report["absolute_white_proven"] is False
    assert report["qualified_colour_count"] == 0
    assert len(report["atlas_samples"]) == 64
    assert len(report["full_panel_grid"]["samples"]) == 24 * 12
    assert all(
        "pre_w2_rgb_median" in sample
        and "post_w3_rgb_median" in sample
        and "delta_e00_pre_w2_to_post_w3" in sample
        and "w1_rgb_median" not in sample
        and "w2_rgb_median" not in sample
        for sample in report["atlas_samples"]
    )
    assert report["threshold_contract"]["automatic_threshold_relaxation"] is False
    _verify_seal(report)


def test_horizontal_colour_stripe_is_still_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    w2 = np.full((1200, 2000, 3), 220, dtype=np.uint8)
    w3 = w2.copy()
    w3[520:680, 100:1900] = (40, 100, 180)
    _patch_sources(monkeypatch, w2, w3)

    report = screen.evaluate("w2.json", "w3.json", panel_corners=CORNERS)

    assert report["summary"]["classification"] == "FAIL"
    assert report["summary"]["horizontal_stripe_candidate_detected"] is True
    assert (
        report["summary"]["component_classifications"]["horizontal_row_median_maximum"]
        == "FAIL"
    )


def test_nonexact_exposure_and_alignment_mismatch_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    white = np.full((1200, 2000, 3), 220, dtype=np.uint8)

    def wrong_exposure(_path, *, stage):
        return _binding(stage, exposure=-6.0), white, {}

    monkeypatch.setattr(screen, "_load_white", wrong_exposure)
    with pytest.raises(screen.WhiteResidualV2ScreenError, match="exposure=-3"):
        screen.evaluate("w2.json", "w3.json", panel_corners=CORNERS)

    def moved_mount(_path, *, stage):
        binding = _binding(stage)
        if stage == w3_pack.STAGE:
            binding["capture_alignment"]["mount_id"] = "moved"
        return binding, white, {}

    monkeypatch.setattr(screen, "_load_white", moved_mount)
    with pytest.raises(screen.WhiteResidualV2ScreenError, match="camera instance"):
        screen.evaluate("w2.json", "w3.json", panel_corners=CORNERS)


def test_w2_and_w3_identities_are_pack_derived() -> None:
    expected_w2 = screen._expected_white(w2_pack.STAGE)  # noqa: SLF001
    expected_w3 = screen._expected_white(w3_pack.STAGE)  # noqa: SLF001
    w2_report = w2_pack.build_white_report()
    w3_report = w3_pack.build_white_report()

    assert expected_w2["contract_id"] == w2_report["contract_id"]
    assert expected_w2["action_id"] == w2_report["action"]["action_id"]
    assert expected_w3["campaign_id"] == w3_pack.CONFIG.campaign_id
    assert expected_w3["contract_id"] == w3_report["contract_id"]
    assert expected_w3["descriptor_id"] == w3_report["action"]["descriptor_id"]
    assert expected_w3["action_id"] == w3_report["action"]["action_id"]
    assert expected_w3["contract_id"] == (
        "69be4f9fa69df03d861b1de6f01e289aca492fd4ad87a5ea1ef18f99dc2516a4"
    )
    assert expected_w3["descriptor_id"] == (
        "5f14f576721f5f4143f7a577d92bc97d4ce5646aa98bc3f4edb52cfb9da7b24f"
    )
    assert expected_w3["action_id"] == (
        "b37e6e5846eecff74b0d478dcdcf5223cdb20f2aa794a2b7f264c42bc21a87e9"
    )
    assert expected_w3["marker_role"] == (
        "OTP_WHITE_RAW_P16_CROSSOVER_W3_DISCOVERY_SUCCESSOR_V2"
    )
    assert expected_w3["firmware_sha256"] == (
        "40c4be2f1213b61e68482e94d482217e8e4f8db4c7102074575a9da81a3f0ee2"
    )
    assert w3_pack.WHITE_ARTIFACTS[w3_pack.STAGE] == {
        "bin_bytes": 787_200,
        "bin_sha256": (
            "40c4be2f1213b61e68482e94d482217e8e4f8db4c7102074575a9da81a3f0ee2"
        ),
        "elf_bytes": 13_214_964,
        "elf_sha256": (
            "84c593afa474fbe8facdb78a5f4db6f88f96807c835bad0e60d21962c0bf3ecd"
        ),
    }


def test_thresholds_match_frozen_v1_and_writer_is_exclusive(tmp_path) -> None:
    assert screen.EXPECTED_THRESHOLD_CONTRACT == {
        "atlas_cell_p95_pass_maximum_de00": frozen.ATLAS_P95_PASS_DE00,
        "atlas_cell_p95_review_maximum_de00": frozen.ATLAS_P95_REVIEW_DE00,
        "atlas_cell_maximum_pass_maximum_de00": frozen.ATLAS_MAX_PASS_DE00,
        "atlas_cell_maximum_review_maximum_de00": frozen.ATLAS_MAX_REVIEW_DE00,
        "grid_p95_pass_maximum_de00": frozen.GRID_P95_PASS_DE00,
        "grid_p95_review_maximum_de00": frozen.GRID_P95_REVIEW_DE00,
        "stripe_row_median_pass_maximum_de00": (frozen.STRIPE_ROW_MEDIAN_PASS_DE00),
        "stripe_row_median_review_maximum_de00": (frozen.STRIPE_ROW_MEDIAN_REVIEW_DE00),
    }
    output = tmp_path / "residual.json"
    screen._write_exclusive(output, b"first\n")  # noqa: SLF001
    with pytest.raises(screen.WhiteResidualV2ScreenError, match="overwrite"):
        screen._write_exclusive(output, b"second\n")  # noqa: SLF001
