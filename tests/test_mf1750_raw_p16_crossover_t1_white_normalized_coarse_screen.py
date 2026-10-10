from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools import (
    mf1750_raw_p16_crossover_t1_white_normalized_coarse_screen as screen,
)


REPOSITORY = Path(__file__).resolve().parents[1]
T1_ROOT = (
    REPOSITORY
    / ".test-output"
    / "hardware"
    / "MF1750_RAW_P16_CROSSOVER_T1_AC_20260830_V1"
)
W1_ROOT = (
    REPOSITORY
    / ".test-output"
    / "hardware"
    / "MF1750_RAW_P16_CROSSOVER_W1_AFTER_T1_WHITE_20260830_V1"
)
T1_ANALYSES = tuple(
    T1_ROOT / f"camera-t1-ac-retained-0{index}.analysis.json" for index in range(1, 4)
)
W1_ANALYSIS = W1_ROOT / "camera-action-01.analysis.json"
LIVE_REPLAY_AVAILABLE = all(path.is_file() for path in (*T1_ANALYSES, W1_ANALYSIS))
requires_live_replay = pytest.mark.skipif(
    not LIVE_REPLAY_AVAILABLE,
    reason="ignored sealed 2026-08-30 hardware evidence is unavailable",
)


def _verify_seal(report: dict) -> None:
    unsigned = {key: value for key, value in report.items() if key != "integrity"}
    assert report["integrity"] == {
        "algorithm": screen.INTEGRITY_ALGORITHM,
        "sha256": screen.strict.sha256_bytes(screen.strict.canonical_json(unsigned)),
    }


@requires_live_replay
def test_sealed_t1_w1_replay_passes_all_sixteen_coarse_groups() -> None:
    report = screen.screen(T1_ANALYSES, W1_ANALYSIS)

    assert report["kind"] == screen.KIND
    assert report["summary"]["classification_counts"] == {
        "PASS": 16,
        "REVIEW": 0,
        "FAIL": 0,
    }
    assert report["summary"]["maximum_position_de00"] == pytest.approx(
        5.384516695, abs=1e-9
    )
    assert 5.3 < report["summary"]["maximum_position_de00"] < 5.5
    assert report["summary"]["maximum_temporal_center_de76"] <= 0.70
    assert report["eligible_for_t2_discovery"] is True
    assert report["screening_only"] is True
    assert report["formal_gate_evaluated"] is False
    assert report["qualified_colour_count"] == 0
    assert report["formal_advance_to_t2_permitted"] is False
    assert report["consumed_t1_state_changed"] is False
    assert report["summary"]["does_not_reverse_consumed_t1"] is True
    assert all(group["classification"] == "PASS" for group in report["group_results"])
    _verify_seal(report)


@requires_live_replay
def test_report_deep_binds_three_t1_records_and_w1_photo() -> None:
    report = screen.screen(T1_ANALYSES, W1_ANALYSIS)

    bindings = report["input_bindings"]
    assert len(bindings["t1_analyses"]) == 3
    for path, binding in zip(T1_ANALYSES, bindings["t1_analyses"], strict=True):
        assert (
            binding["analysis_file_sha256"]
            == hashlib.sha256(path.read_bytes()).hexdigest()
        )
        assert set(binding["source_evidence"]) == {
            "capture_sidecar",
            "action_result",
            "photo",
        }
    w1_photo = W1_ROOT / "camera-w1-white-20260830-141600.jpg"
    assert (
        bindings["w1_analysis"]["photo"]["file_sha256"]
        == hashlib.sha256(w1_photo.read_bytes()).hexdigest()
    )
    assert bindings["w1_analysis"]["photo"]["width"] == 4000
    assert bindings["w1_analysis"]["photo"]["height"] == 3000
    fingerprints = [
        *(item["capture_alignment"] for item in bindings["t1_analyses"]),
        bindings["w1_analysis"]["capture_alignment"],
    ]
    assert all(item == fingerprints[0] for item in fingerprints[1:])
    assert "vid_32e4&pid_4801" in fingerprints[0]["instance_id"].lower()
    assert fingerprints[0]["mount_id"] == "mf1750-48mp-fixed-20260828"
    assert fingerprints[0]["photo_width"] == 4000
    assert fingerprints[0]["photo_height"] == 3000


@requires_live_replay
def test_tampered_t1_analysis_fails_before_screening(tmp_path: Path) -> None:
    tampered = tmp_path / "tampered-t1.json"
    root = json.loads(T1_ANALYSES[0].read_text("utf-8"))
    root["cells"][0]["robust_rgb_median"][0] += 1.0
    tampered.write_text(json.dumps(root), encoding="utf-8")

    with pytest.raises(screen.CoarseScreenError, match="integrity SHA"):
        screen.screen((tampered, T1_ANALYSES[1], T1_ANALYSES[2]), W1_ANALYSIS)


@requires_live_replay
def test_tampered_w1_analysis_fails_deep_validation(tmp_path: Path) -> None:
    tampered = tmp_path / "camera-action-01.analysis.json"
    root = json.loads(W1_ANALYSIS.read_text("utf-8"))
    root["analysis"]["confidence"] = "high"
    tampered.write_text(json.dumps(root), encoding="utf-8")

    with pytest.raises(screen.CoarseScreenError, match="deep validation failed"):
        screen.screen(T1_ANALYSES, tampered)


@pytest.mark.parametrize(
    ("value", "pass_max", "review_max", "expected"),
    (
        (8.0, 8.0, 12.0, "PASS"),
        (8.000001, 8.0, 12.0, "REVIEW"),
        (12.0, 8.0, 12.0, "REVIEW"),
        (12.000001, 8.0, 12.0, "FAIL"),
        (3.0, 3.0, 6.0, "PASS"),
        (3.000001, 3.0, 6.0, "REVIEW"),
        (6.0, 3.0, 6.0, "REVIEW"),
        (6.000001, 3.0, 6.0, "FAIL"),
    ),
)
def test_threshold_edges_are_frozen(
    value: float, pass_max: float, review_max: float, expected: str
) -> None:
    assert (
        screen._metric_classification(  # noqa: SLF001
            value, pass_max=pass_max, review_max=review_max
        )
        == expected
    )


def test_white_reference_below_lstar_25_is_invalid() -> None:
    t1 = {
        "cell_id": "CS1-R0-C0-CODE0",
        "controller": 0,
        "row": 0,
        "column": 0,
        "code": 0,
        "robust_rgb_median": [90.0, 30.0, 20.0],
    }
    white = {
        "robust_rgb_median": [20.0, 20.0, 20.0],
        "camera_relative_lab_d65_from_rgb_median": [24.999, 0.0, 0.0],
    }

    result = screen._normalized_cell(t1, white)  # noqa: SLF001

    assert result["valid"] is False
    assert result["normalized_rgb"] is None
    assert result["invalid_reason"] == "WHITE_REFERENCE_LSTAR_BELOW_25"


def test_coarse_buckets_are_intentionally_broad() -> None:
    assert screen._coarse_bucket([95.0, 1.0, 1.0]) == "NEUTRAL_LIGHT"  # noqa: SLF001
    assert screen._coarse_bucket([50.0, 30.0, 10.0]) == "RED_ORANGE"  # noqa: SLF001
    assert screen._coarse_bucket([60.0, -10.0, 30.0]) == "YELLOW_OLIVE"  # noqa: SLF001
    assert screen._coarse_bucket([40.0, -20.0, -15.0]) == "GREEN_CYAN"  # noqa: SLF001
    assert screen._coarse_bucket([30.0, 25.0, -40.0]) == "BLUE_VIOLET"  # noqa: SLF001


def test_position_requires_same_dominant_bucket_in_at_least_two_frames() -> None:
    positions = screen.strict._expected_positions(0)  # noqa: SLF001
    frames = []
    first_buckets = ("RED_ORANGE", "YELLOW_OLIVE", "GREEN_CYAN")
    for frame_index in range(3):
        cells = []
        for position_index, (row, column) in enumerate(positions):
            cells.append(
                {
                    "controller": 0,
                    "row": row,
                    "column": column,
                    "code": 0,
                    "valid": True,
                    "normalized_lab": [50.0, 30.0, 10.0],
                    "coarse_bucket": (
                        first_buckets[frame_index]
                        if position_index == 0
                        else "RED_ORANGE"
                    ),
                }
            )
        frames.append({"frame_index": frame_index + 1, "cells": cells})

    result = screen._group_result(frames, controller=0, code=0)  # noqa: SLF001

    first = result["position_results"][0]
    assert first["valid_frame_count"] == 3
    assert first["dominant_bucket_frame_count"] == 1
    assert first["position_eligible"] is False
    assert result["eligible_position_count"] == 3


def test_capture_alignment_requires_exact_camera_mount_settings_and_dimensions() -> (
    None
):
    fingerprint = {
        "instance_id": "48mp-instance",
        "mount_id": "fixed-mount",
        "requested_settings": {"exposure": -6.0},
        "effective_settings_before_frame": {"exposure": -6.0},
        "effective_settings_after_frame": {"exposure": -6.0},
        "photo_width": 4000,
        "photo_height": 3000,
    }
    screen._validate_capture_alignment([fingerprint] * 4)  # noqa: SLF001
    changed = dict(fingerprint)
    changed["mount_id"] = "moved"

    with pytest.raises(screen.CoarseScreenError, match="alignment fingerprint"):
        screen._validate_capture_alignment(  # noqa: SLF001
            [fingerprint, fingerprint, changed, fingerprint]
        )


def test_optional_maximum_handles_all_failed_groups() -> None:
    assert (
        screen._maximum_optional(  # noqa: SLF001
            [{"position_maximum_de00": None}], "position_maximum_de00"
        )
        is None
    )


def test_exclusive_writer_never_overwrites(tmp_path: Path) -> None:
    output = tmp_path / "coarse-screen.json"
    screen.write_exclusive(output, b"first\n")

    with pytest.raises(screen.CoarseScreenError, match="overwrite"):
        screen.write_exclusive(output, b"second\n")

    assert output.read_bytes() == b"first\n"


def test_exclusive_writer_removes_partial_file_on_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "partial.json"

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("injected fsync failure")

    monkeypatch.setattr(screen.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="injected"):
        screen.write_exclusive(output, b"partial")
    assert not output.exists()


def test_exactly_three_t1_analyses_are_required() -> None:
    with pytest.raises(screen.CoarseScreenError, match="exactly three"):
        screen.screen(T1_ANALYSES[:2], W1_ANALYSIS)
