from __future__ import annotations

import numpy as np
import pytest

from tools import mf1750_true_r20_hold_video_gate as gate


def _series(
    *, transient: float = 0.0, background: float = 0.0
) -> dict[str, np.ndarray]:
    frame_count = 20
    result: dict[str, np.ndarray] = {}
    for key in ("C0-A", "C1-A"):
        values = np.tile(np.asarray([50.0, 2.0, 3.0]), (frame_count, 1))
        values[10:, 0] += transient
        result[key] = values
    for key in ("C0-BG_TOP", "C1-BG_TOP"):
        values = np.tile(np.asarray([90.0, 0.0, 0.0]), (frame_count, 1))
        values[10:, 0] += background
        result[key] = values
    return result


def test_constant_protected_and_background_series_pass() -> None:
    result = gate.evaluate_samples(
        _series(),
        protected_keys=("C0-A", "C1-A"),
        background_keys=("C0-BG_TOP", "C1-BG_TOP"),
        pre_roll_frames=5,
        threshold_de76=4.0,
    )
    assert result["transient_gate_pass"] is True


def test_protected_transient_fails() -> None:
    result = gate.evaluate_samples(
        _series(transient=20.0),
        protected_keys=("C0-A", "C1-A"),
        background_keys=("C0-BG_TOP", "C1-BG_TOP"),
        pre_roll_frames=5,
        threshold_de76=4.0,
    )
    assert result["protected_pass"] is False
    assert result["transient_gate_pass"] is False


def test_background_instability_fails_instead_of_being_subtracted() -> None:
    result = gate.evaluate_samples(
        _series(background=10.0),
        protected_keys=("C0-A", "C1-A"),
        background_keys=("C0-BG_TOP", "C1-BG_TOP"),
        pre_roll_frames=5,
        threshold_de76=4.0,
    )
    assert result["background_stability_pass"] is False
    assert result["transient_gate_pass"] is False


def test_missing_noise_threshold_stays_inconclusive() -> None:
    result = gate.evaluate_samples(
        _series(),
        protected_keys=("C0-A", "C1-A"),
        background_keys=("C0-BG_TOP", "C1-BG_TOP"),
        pre_roll_frames=5,
        threshold_de76=None,
    )
    assert result["transient_gate_pass"] is None


def test_invalid_series_shape_is_rejected() -> None:
    values = _series()
    values["C0-A"] = values["C0-A"][:, :2]
    with pytest.raises(gate.TrueR20HoldVideoGateError, match="differs"):
        gate.evaluate_samples(
            values,
            protected_keys=("C0-A", "C1-A"),
            background_keys=("C0-BG_TOP", "C1-BG_TOP"),
            pre_roll_frames=5,
            threshold_de76=4.0,
        )
