from __future__ import annotations

from pathlib import Path

import pytest

from tools import mf1750_ec5_u04_u05_compare_prerequisites as subject


REPO_ROOT = Path(__file__).resolve().parents[1]
HARDWARE = REPO_ROOT / ".test-output" / "hardware"
SESSION = HARDWARE / "MF1750_EC5_STAGE_A_CORRECTED_V2_PHYSICAL_SESSION_20260809_2143"
RELEASE = (
    HARDWARE
    / "MF1750_EC5_STAGE_A_CORRECTED_V2_RELEASE_OFFLINE_20260809_V1"
    / "release-manifest.json"
)
PANEL = (
    HARDWARE
    / "RC2G_N2_PHYSICAL_SESSION_20260808_2132"
    / "inputs"
    / "physical-panel.json"
)


@pytest.mark.skipif(not RELEASE.exists(), reason="physical evidence not present")
def test_real_u04_and_short_hold_boundary_replay() -> None:
    _, binding = subject.load_u04_result_binding(
        release_file=RELEASE,
        result_file=SESSION / "u04-target-result.json",
        panel_file=PANEL,
        claim_registry=HARDWARE / ".mf1750_ec5_claim_registry",
    )
    assert binding["outcome"] == "complete_pass"
    assert binding["action_id"] == subject.U04_ACTION_ID
    hold = subject.load_short_hold_boundary(
        SESSION / "u04-operator-observation-through-5min.json",
        u04_result_file=SESSION / "u04-target-result.json",
    )
    assert hold["five_minute_short_hold_passed"] is True
    assert hold["thirty_minute_observation"] == "SKIPPED_BY_OPERATOR"
    assert hold["thirty_minute_hold_required_for_comparison"] is False


@pytest.mark.skipif(not RELEASE.exists(), reason="physical evidence not present")
def test_real_white_result_claim_and_manual_observation_replay() -> None:
    context, _ = subject.load_u04_result_binding(
        release_file=RELEASE,
        result_file=SESSION / "u04-target-result.json",
        panel_file=PANEL,
        claim_registry=HARDWARE / ".mf1750_ec5_claim_registry",
    )
    white = subject.load_white_result_binding(
        context=context,
        release_file=RELEASE,
        u04_result_file=SESSION / "u04-target-result.json",
        white_result_file=SESSION / "u04-white-recovery-result.json",
        panel_file=PANEL,
        rc2g_binary_file=(
            HARDWARE
            / "RC2G_N2_PHYSICAL_SESSION_20260808_2132"
            / "q1-map-primer-result"
            / "FIRMWARE.bin"
        ),
        candidate_claim_registry=HARDWARE / ".mf1750_ec5_claim_registry",
        white_claim_registry=HARDWARE / ".mf1750_ec5_white_claims",
    )
    assert white["stage"] == "after-u04"
    assert white["action_id"] == subject.WHITE_ACTION_ID
    observation = subject.load_white_manual_observation(
        SESSION / "u04-white-recovery-manual-observation.json",
        white_result_file=SESSION / "u04-white-recovery-result.json",
    )
    assert observation["visual_and_electrical_pass"] is True

