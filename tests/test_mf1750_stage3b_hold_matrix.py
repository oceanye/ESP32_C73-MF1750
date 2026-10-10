from __future__ import annotations

import hashlib

import pytest

from tools import mf1750_stage3b_hold_matrix as hold


def _measurement(delta: list[list[float]], std: float = 0.2) -> dict:
    return {
        "schema_version": 1,
        "kind": "mf1750-stage3b-calibrated-hold-measurements",
        "camera_calibrated": True,
        "controllers": {
            name: {
                "delta_e_from_before": delta,
                "within_cell_delta_e_std": [[std] * 8 for _ in range(8)],
            }
            for name in ("CS1", "CS2")
        },
    }


def test_frames_cover_all_64_transitions_without_dither() -> None:
    base = hold.build_frame("base_rows")
    overlay = hold.build_frame("overlay_columns")
    assert hashlib.sha256(base).hexdigest() == hold.BASE_FRAME_SHA256
    assert hashlib.sha256(overlay).hexdigest() == hold.OVERLAY_FRAME_SHA256
    for source in range(8):
        for target in range(8):
            y = source * 75 + 20
            for controller in range(2):
                x = controller * 512 + target * 64 + 20
                assert base[(y * 1024 + x) // 2] == (source << 4) | source
                assert overlay[(y * 1024 + x) // 2] == (target << 4) | target


def test_universal_hold_column_is_found() -> None:
    delta = [[9.0] * 8 for _ in range(8)]
    for row in delta:
        row[6] = 0.5
    result = hold.evaluate(_measurement(delta), delta_e_limit=2.0, within_std_limit=1.0)
    for controller in ("CS1", "CS2"):
        assert result["controllers"][controller]["universal_hold_codes"] == [6]
    assert result["both_controllers_masked_overlay_candidate"] is True
    assert result["true_partial_refresh_proven"] is False


def test_source_specific_hold_mapping_is_found() -> None:
    delta = [[9.0] * 8 for _ in range(8)]
    for source in range(8):
        delta[source][7 - source] = 0.5
    result = hold.evaluate(_measurement(delta), delta_e_limit=2.0, within_std_limit=1.0)
    assert result["controllers"]["CS1"]["universal_hold_codes"] == []
    assert result["controllers"]["CS1"]["source_specific_hold_codes"] == list(
        reversed(range(8))
    )
    assert result["both_controllers_masked_overlay_candidate"] is True


def test_uncalibrated_camera_is_rejected() -> None:
    value = _measurement([[0.0] * 8 for _ in range(8)])
    value["camera_calibrated"] = False
    with pytest.raises(hold.HoldMatrixError, match="calibrated"):
        hold.evaluate(value, delta_e_limit=2.0, within_std_limit=1.0)
