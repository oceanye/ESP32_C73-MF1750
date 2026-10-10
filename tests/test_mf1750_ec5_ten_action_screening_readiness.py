from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from tools import mf1750_ec5_ten_action_screening_readiness as readiness


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def root() -> dict[str, object]:
    return readiness.build_readiness(
        c20_control_file=(
            REPO_ROOT / ".test-output/hardware/"
            "MF1750_EC5_H3_MATCHED_CONTROL_C_FIRST_RELEASES_20260813_V10/"
            "WF20_25-release.json"
        ),
        c20_treatment_file=(
            REPO_ROOT / ".test-output/hardware/"
            "MF1750_EC5_EMPIRICAL_H3_RELEASES_20260812_V7/"
            "WF20_25-release.json"
        ),
        c23_control_file=(
            REPO_ROOT / ".test-output/hardware/"
            "MF1750_EC5_H3_C23_MATCHED_CONTROL_RELEASE_20260817_V1/"
            "WF23_25-C23-release.json"
        ),
        c23_treatment_file=(
            REPO_ROOT / ".test-output/hardware/"
            "MF1750_EC5_EMPIRICAL_H3_RELEASES_20260812_V7/"
            "WF23_25-release.json"
        ),
        dither_release_file=(
            REPO_ROOT / ".test-output/hardware/"
            "MF1750_EC5_DITHER_COLOR_ATLAS_RELEASE_OFFLINE_20260810_V1/"
            "dither-color-atlas-real-release.json"
        ),
    )


def test_exact_five_pairs_ten_actions_are_offline_schedulable(
    root: dict[str, object],
) -> None:
    summary = readiness.validate_readiness(root)
    assert summary["valid"] is True
    assert summary["pair_count"] == 5
    assert summary["visible_action_count"] == 10
    assert summary["color_screen_count"] == 5
    assert summary["white_recovery_count"] == 5
    assert summary["same_evening_scheduling_allowed"] is True
    assert summary["execution_gate_reached"] is False
    assert summary["live_authorized"] is False
    assert summary["device_io_performed"] is False
    assert summary["visible_refreshes"] == 0

    actions = root["schedule"]["actions"]  # type: ignore[index]
    assert [item["visible_ordinal"] for item in actions] == list(range(1, 11))
    assert [item["visible_class"] for item in actions] == [
        "COLOR_SCREEN",
        "WHITE_RECOVERY",
    ] * 5
    assert len({item["hardware_action_id"] for item in actions}) == 10
    assert all(item["automatic_advance"] is False for item in actions)
    assert all(item["automatic_retry"] is False for item in actions)

    decision = root["screening_decision"]  # type: ignore[index]
    assert decision["ten_action_screening_can_confirm_new_color"] is False
    assert decision["ten_action_screening_can_select_candidate_for_verification"]
    assert (
        decision["candidate_followup"][
            "run_all_137_plus_qualification_actions_immediately"
        ]
        is False
    )


def test_integrity_tamper_fails_before_any_live_effect(
    root: dict[str, object],
) -> None:
    tampered = deepcopy(root)
    tampered["schedule"]["actions"][0]["visible_ordinal"] = 99  # type: ignore[index]
    with pytest.raises(readiness.TenActionReadinessError, match="integrity"):
        readiness.validate_readiness(tampered)
