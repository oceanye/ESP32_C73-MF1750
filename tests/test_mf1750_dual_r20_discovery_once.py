from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from tools import mf1750_dual_r20_discovery_once as dual
from tools import mf1750_ec5_runtime_lut_contract as contract
from tools import mf1750_ec5_runtime_lut_physical_once as physical


def _write(path: Path, value: dict) -> Path:
    path.write_bytes(contract.canonical_json_bytes(value) + b"\n")
    return path


def _result(candidate: dual.Candidate, ordinal: int) -> dict:
    image = candidate.treatment if ordinal == 1 else candidate.recovery
    return physical._seal(  # noqa: SLF001
        {
            "schema_version": 1,
            "kind": physical.RESULT_KIND,
            "release_id": candidate.release_id,
            "profile_id": candidate.profile_id,
            "ordinal": ordinal,
            "role": image.role,
            "hardware_action_id": image.action_id,
            "claim_file_sha256": "a" * 64,
            "visible_refreshes": 1,
            "outcome": "success",
            "retry_allowed": False,
        }
    )


def test_describe_binds_two_discovery_first_candidates() -> None:
    report = dual.describe()
    assert report["candidate_order"] == ["H20", "H23"]
    assert report["per_candidate_outcomes"] == 16
    assert report["single_pixel_codes_per_controller"] == 8
    assert report["spatial_dithering"] is False
    assert report["partial_refresh"] is False
    assert report["mid_refresh_power_cut"] is False
    assert report["decision_policy"][dual.NO_NEW].endswith("next_candidate")
    assert report["decision_policy"][dual.SUSPECTED_NEW].endswith(
        "left_right_swap_replication"
    )


@pytest.mark.parametrize("key", ["H20", "H23"])
def test_context_has_exact_split_and_independent_actions(key: str) -> None:
    candidate = dual.CANDIDATES[key]
    context = dual.load_context(candidate)
    assert context.profile_id == candidate.profile_id
    assert context.binding(1)["firmware_binary_sha256"] == (
        candidate.treatment.binary_sha256
    )
    assert context.binding(2)["firmware_binary_sha256"] == (
        candidate.recovery.binary_sha256
    )
    assert context.action(1)["role"] == candidate.treatment.role
    assert context.action(2)["role"] == contract.ROLE_WHITE
    assert context.action(1)["automatic_chaining"] is False
    assert context.action(1)["retry"] is False


def test_no_new_allows_next_candidate_after_white(tmp_path: Path) -> None:
    h20 = dual.CANDIDATES["H20"]
    treatment = _write(tmp_path / "h20-treatment.json", _result(h20, 1))
    decision_value = dual.record_decision(h20, treatment, dual.NO_NEW, "six colours")
    decision = _write(tmp_path / "h20-decision.json", decision_value)
    recovery = _write(tmp_path / "h20-white.json", _result(h20, 2))
    args = argparse.Namespace(
        ordinal=1,
        decision=None,
        prior_decision=decision,
        prior_recovery_result=recovery,
    )
    dual._check_progression(args, dual.CANDIDATES["H23"])


def test_suspected_new_blocks_next_candidate_and_selects_swap(tmp_path: Path) -> None:
    h20 = dual.CANDIDATES["H20"]
    treatment = _write(tmp_path / "h20-treatment.json", _result(h20, 1))
    decision_value = dual.record_decision(
        h20, treatment, dual.SUSPECTED_NEW, "possible cyan"
    )
    assert decision_value["left_right_swap_required"] is True
    decision = _write(tmp_path / "h20-decision.json", decision_value)
    recovery = _write(tmp_path / "h20-white.json", _result(h20, 2))
    args = argparse.Namespace(
        ordinal=1,
        decision=None,
        prior_decision=decision,
        prior_recovery_result=recovery,
    )
    with pytest.raises(dual.DualR20Error, match="blocks H23"):
        dual._check_progression(args, dual.CANDIDATES["H23"])


def test_recovery_requires_operator_decision() -> None:
    args = argparse.Namespace(
        ordinal=2,
        decision=None,
        prior_decision=None,
        prior_recovery_result=None,
    )
    with pytest.raises(dual.DualR20Error, match="requires this candidate"):
        dual._check_progression(args, dual.CANDIDATES["H20"])


def test_firmware_source_has_no_forbidden_experiment_paths() -> None:
    driver = Path("src/ec5_dual_r20_h20_driver.inc").read_text(encoding="utf-8")
    main = Path("src/ec5_dual_r20_h20_main.cpp").read_text(encoding="utf-8")
    assert "h3_cs1_profile::kR20Payload" in driver
    assert "h3_cs2_profile::kR20Payload" in driver
    assert "MF1750_DUAL_R20_GLOBAL_WF20_25" in driver
    assert "MF1750_DUAL_R20_GLOBAL_WF23_25" in driver
    for forbidden in ("partial_refresh", "mid_refresh_power_cut", "0x86"):
        assert forbidden not in driver.lower()
        assert forbidden not in main.lower()
    assert '\\"automatic_chaining\\":false' in main
    assert '\\"retry\\":false' in main


def test_cli_describe_is_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert dual.main(["describe"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["kind"] == "mf1750-dual-r20-discovery-first-plan"
