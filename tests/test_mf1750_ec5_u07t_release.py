from __future__ import annotations

from pathlib import Path
import json

import pytest

from tools import mf1750_ec5_u07t_identity as identity
from tools import mf1750_ec5_u07t_release as release


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = (
    ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_U07T_TECHNICAL_RELEASE_OFFLINE_20260809_V1"
)


@pytest.mark.skipif(not BUNDLE.is_dir(), reason="offline U07T release not built")
def test_frozen_offline_release_deeply_replays() -> None:
    with pytest.raises(release.U07TReleaseError, match="invalidated"):
        release.validate_release(BUNDLE)
    manifest = json.loads((BUNDLE / release.MANIFEST_FILE).read_text(encoding="utf-8"))
    assert manifest["variant"]["action_id"] == identity.FROZEN_ACTION_ID
    assert manifest["safety"]["classification"] == (
        "TECHNICAL_DESCRIPTIVE_NOT_QUALIFIED"
    )
    assert manifest["safety"]["formal_u07_action_consumed"] is False
    assert manifest["safety"]["formal_u07_qualification_inferred"] is False
    assert manifest["prerequisites"]["boundary"] == {
        "corrected_u04_complete_pass": True,
        "u04_five_minute_short_hold_passed": True,
        "u04_thirty_minute_observation": "SKIPPED_BY_OPERATOR",
        "formal_u07_review_gate_satisfied": False,
        "after_u04_white_complete_pass": True,
        "after_u04_white_manual_visual_and_electrical_pass": True,
        "formal_u07_qualification_inferred": False,
    }
    assert (BUNDLE / release.QUARANTINE_MARKER).is_file()


@pytest.mark.skipif(not BUNDLE.is_dir(), reason="offline U07T release not built")
@pytest.mark.parametrize(
    "forbidden",
    [
        identity.FORMAL_U07_ACTION_ID,
        "d1874fb778b7af16a8e2c89687987d187e0fbed3a6ee279c966d427e633969a9",
    ],
)
def test_binary_gate_rejects_formal_or_provisional_action_token(
    forbidden: str,
) -> None:
    firmware = (BUNDLE / "firmware-u07t.bin").read_bytes()
    with pytest.raises(release.U07TReleaseError, match="forbidden"):
        release._validate_firmware(firmware + forbidden.encode("ascii"))  # noqa: SLF001


def test_release_declares_separate_recovery_boundary() -> None:
    assert release.SAFETY[
        "post_action_screen_remains_u07t_until_separate_recovery"
    ] is True
    assert release.SAFETY["formal_after_u07_white_action_must_not_be_reused"] is True
    assert release.SAFETY["no_intervening_visible_refresh_required"] is True
