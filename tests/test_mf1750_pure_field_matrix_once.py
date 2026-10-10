from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from tools import mf1750_ec5_runtime_lut_contract as contract
from tools import mf1750_ec5_runtime_lut_physical_once as physical
from tools import mf1750_pure_field_matrix_once as runner


def _write(path: Path, value: dict) -> Path:
    path.write_bytes(contract.canonical_json_bytes(value) + b"\n")
    return path


def _result(candidate, ordinal: int) -> dict:
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


def _loaded():
    return runner._release(runner.DEFAULT_RELEASE)  # noqa: SLF001


def test_describe_freezes_eight_by_sixteen_search() -> None:
    value = runner.describe()
    assert value["candidate_order"] == [
        "M0_H20",
        "M0_H23",
        "H1_H20",
        "H1_H23",
        "H2_H20",
        "H2_H23",
        "H3_H20",
        "H3_H23",
    ]
    assert value["treatment_screens"] == 8
    assert value["white_recoveries"] == 8
    assert value["total_endpoint_observations"] == 128
    assert value["camera_hook_reserved"] is True
    assert value["camera_calibration_complete"] is False
    assert value["unattended_autochain_enabled"] is False


@pytest.mark.parametrize("key", ["M0_H20", "H1_H23", "H2_H20", "H3_H23"])
def test_context_binds_flat_frame_and_independent_white(key: str) -> None:
    release, candidates = _loaded()
    context = runner.load_context(release, candidates[key])
    treatment = context.action(1)
    recovery = context.action(2)
    assert treatment["payload_identity"]["frame_sha256"] == (
        "d2c08f7986ded9dc3bba93970cba7659ff773b36b3564cdfa3325bca4d8e970f"
    )
    assert treatment["role"] == "PURE_FIELD_UNIFORM_CODE_ATLAS"
    assert recovery["role"] == contract.ROLE_WHITE
    assert context.binding(1)["nvs_namespace"] != context.binding(2)["nvs_namespace"]
    assert context.binding(1)["firmware_binary_sha256"] != (
        context.binding(2)["firmware_binary_sha256"]
    )


def test_no_new_then_white_allows_next_treatment(tmp_path: Path) -> None:
    _release, candidates = _loaded()
    order = list(candidates)
    previous = candidates[order[0]]
    treatment = _write(tmp_path / "treatment.json", _result(previous, 1))
    decision = _write(
        tmp_path / "decision.json",
        runner.record_decision(previous, treatment, runner.NO_NEW, "striped", "operator"),
    )
    recovery = _write(tmp_path / "white.json", _result(previous, 2))
    args = argparse.Namespace(
        candidate=order[1],
        ordinal=1,
        decision=None,
        prior_decision=decision,
        prior_recovery_result=recovery,
    )
    runner._check_progression(args, order, candidates)  # noqa: SLF001


def test_suspected_new_stops_next_unswapped_candidate(tmp_path: Path) -> None:
    _release, candidates = _loaded()
    order = list(candidates)
    previous = candidates[order[0]]
    treatment = _write(tmp_path / "treatment.json", _result(previous, 1))
    decision = _write(
        tmp_path / "decision.json",
        runner.record_decision(
            previous, treatment, runner.SUSPECTED_NEW, "uniform orange", "camera_reviewed"
        ),
    )
    recovery = _write(tmp_path / "white.json", _result(previous, 2))
    args = argparse.Namespace(
        candidate=order[1],
        ordinal=1,
        decision=None,
        prior_decision=decision,
        prior_recovery_result=recovery,
    )
    with pytest.raises(runner.PureFieldError, match="blocks"):
        runner._check_progression(args, order, candidates)  # noqa: SLF001


def test_white_requires_current_candidate_decision() -> None:
    _release, candidates = _loaded()
    first = next(iter(candidates))
    args = argparse.Namespace(
        candidate=first,
        ordinal=2,
        decision=None,
        prior_decision=None,
        prior_recovery_result=None,
    )
    with pytest.raises(runner.PureFieldError, match="requires"):
        runner._check_progression(args, list(candidates), candidates)  # noqa: SLF001
