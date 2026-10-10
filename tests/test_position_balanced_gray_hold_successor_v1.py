from __future__ import annotations

from pathlib import Path

import pytest

from tools import mf1750_position_balanced_gray_hold_successor_v1_once as runner
from tools import mf1750_position_balanced_gray_hold_successor_v1_pack as pack
from tools import (
    mf1750_position_balanced_gray_hold_successor_v1_white_successor_v1_once as white_runner,
)
from tools import (
    mf1750_position_balanced_gray_hold_successor_v1_white_successor_v1_pack as white_pack,
)


def test_hold_package_is_two_manual_actions_outside_all_candidates() -> None:
    report = pack.build_report()
    contract = report["contract"]
    actions = report["actions"]
    assert report["contract_id"] == pack.CONTRACT_ID
    assert [item["ordinal"] for item in actions] == [1, 2]
    assert [item["driver_role"] for item in actions] == [
        "ReverseSource",
        "ReverseTarget",
    ]
    assert contract["hold_windows"] == [
        {"x": 64, "y": 8, "width": 320, "height": 24, "cs1_code": 5, "cs2_code": 5},
        {"x": 64, "y": 568, "width": 320, "height": 24, "cs1_code": 6, "cs2_code": 6},
    ]
    assert contract["windows_outside_candidate_grid"] is True
    assert contract["windows_nonoverlapping"] is True
    assert contract["g3_candidate_cells_retained"] == 128
    assert contract["source_action_replayed"] is False
    assert contract["g1_g2_g3_embedded_or_replayed"] is False
    assert contract["boot_auto_action"] is False
    assert contract["startup_refresh"] is False
    assert contract["factory_otp_white_successor_embedded"] is False
    assert contract["qualified_hold_colours"] == 0
    assert contract["qualified_gray_levels"] == 0


def test_clean_transport_is_exact_and_has_no_post_pon_mutation() -> None:
    transport = pack.build_report()["contract"]["clean_ptlw_transport"]
    assert transport["full_code7_prestage_bytes_per_controller"] == 153600
    assert transport["ptlw_payloads_hex"] == [
        "0040017f0008001f01",
        "0040017f0238024f01",
    ]
    assert transport["cropped_dtm_bytes_per_controller"] == [3840, 3840]
    assert transport["target_codes"] == [5, 6]
    assert transport["post_pon_ptlw"] is False
    assert transport["post_pon_cdi"] is False
    assert transport["post_pon_btst2"] is False
    assert transport["command_0x86"] is False

    source = pack.driver_path().read_text(encoding="utf-8")
    refresh = source.split("bool phRefreshTreatmentsIdentically()", 1)[1].split(
        "}  // namespace", 1
    )[0]
    assert [line.strip() for line in refresh.splitlines() if "epdCommand(" in line] == [
        "epdCommand(PON);",
        "epdCommand(DRF);",
        "epdCommand(POF);",
    ]
    assert "phWritePartialWindow" not in refresh
    assert "CDI" not in refresh
    assert "BTST2" not in refresh
    assert "0x86" not in refresh


def test_g4_presence_is_a_hard_failure_before_g3_selection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source_report = pack.source_pack.build_report()
    monkeypatch.setattr(
        pack.source_pack, "dry_validate", lambda **_: {"result": "PASS"}
    )
    monkeypatch.setattr(pack.source_pack, "build_report", lambda: source_report)
    g3_path = tmp_path / "missing-g3.json"
    g4_path = tmp_path / "present-g4.json"
    g4_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(pack, "SOURCE_G3_PATH", g3_path)
    monkeypatch.setattr(pack, "SOURCE_G4_PATH", g4_path)
    with pytest.raises(pack.PositionBalancedGrayHoldPackError, match="forbidden G4"):
        pack.validate_source_authority(require_live=False)


def test_missing_g3_is_pending_offline_and_rejected_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_report = pack.source_pack.build_report()
    monkeypatch.setattr(
        pack.source_pack, "dry_validate", lambda **_: {"result": "PASS"}
    )
    monkeypatch.setattr(pack.source_pack, "build_report", lambda: source_report)
    missing_root = pack.REPO_ROOT / ".test-output/unit-missing-pbghs1"
    monkeypatch.setattr(pack, "SOURCE_G3_PATH", missing_root / "missing-g3.json")
    monkeypatch.setattr(pack, "SOURCE_G4_PATH", missing_root / "missing-g4.json")
    assert pack.validate_source_authority(require_live=False)["state"] == (
        "PENDING_EXACT_G3_COMPLETE"
    )
    with pytest.raises(pack.PositionBalancedGrayHoldPackError, match="G3 COMPLETE"):
        pack.validate_source_authority(require_live=True)


def test_white_successor_defaults_to_h2_and_requires_explicit_h1() -> None:
    report = white_pack.build_report(verify_artifacts=False)
    contract = report["contract"]
    assert report["contract_id"] == white_pack.CONTRACT_ID
    assert contract["accepted_source_complete_ordinals_default"] == [2]
    assert contract["explicit_h1_stop_ordinal"] == 1
    assert contract["h1_requires_explicit_selection"] is True
    assert contract["main_campaign_resume_after_containment"] is False
    assert white_runner._source_terminal_paths() == {  # noqa: SLF001
        1: runner.ACTION_OUTPUTS[1].resolve(),
        2: runner.ACTION_OUTPUTS[2].resolve(),
    }
    parsed = white_runner._parse_args(  # noqa: SLF001
        [
            "diagnose-j2-off",
            "--base-url",
            "http://192.0.2.1",
            "--source-terminal-evidence",
            str(runner.ACTION_OUTPUTS[1]),
            "--confirm-j2-off",
            "--confirm-explicit-h1-stop",
        ]
    )
    assert parsed.confirm_explicit_h1_stop is True


def test_white_default_path_rejects_h1_without_explicit_selection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    h1 = tmp_path / "h1.json"
    h2 = tmp_path / "h2.json"
    h1.write_text("{}", encoding="utf-8")
    h2.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(white_runner, "_source_terminal_paths", lambda: {1: h1, 2: h2})
    with pytest.raises(white_runner.WhiteSuccessorV1Error, match="source path differs"):
        white_runner._validate_source_terminal(  # noqa: SLF001
            h1, confirm_optional_l4_source=False
        )


def test_offline_artifacts_and_compiled_markers_are_sealed() -> None:
    assert (
        pack.dry_validate(require_live_source=False, verify_artifacts=True)["result"]
        == "PASS"
    )
    assert white_pack.dry_validate(verify_artifacts=True)["result"] == "PASS"
