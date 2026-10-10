from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from tools import (
    mf1750_raw_p16_crossover_t4_matched_swap_human_observation as subject,
)


def _input() -> dict:
    root = subject.input_template()
    root["observed_at"] = "2026-08-31T20:00:00+08:00"
    root["operator"] = {
        "operator_id": "conversation-user",
        "operator_verbatim": "逐格与冻结 T3 A 参考比较。",
    }
    root["supervision"] = {
        field: True for field in subject.SUPERVISION_KEYS - {"supervision_verbatim"}
    } | {"supervision_verbatim": "T3 参考可见，光线与视角稳定。"}
    root["artifacts"] = {
        field: {"observed": False, "operator_verbatim": "未见"}
        for field in subject.ARTIFACT_FIELDS
    }
    for item in root["replicates"]:
        item.update(
            {
                "t4_cs1_matches_t3_a": "A_CS2",
                "t4_cs2_matches_t3_a": "A_CS1",
                "t4_sides_equal": False,
                "stable": True,
                "operator_verbatim": "交叉侧匹配",
            }
        )
        if item["code"] in subject.CONTROL_CODES:
            item.update(
                {
                    "t4_cs1_matches_t3_a": "BOTH_A_SIDES_SAME",
                    "t4_cs2_matches_t3_a": "BOTH_A_SIDES_SAME",
                    "t4_sides_equal": True,
                    "operator_verbatim": "两侧相同，控制码不区分",
                }
            )
    return root


def _set_code(
    root: dict, code: int, *, mode: str, rows: tuple[int, ...] = (0, 1, 2)
) -> None:
    values = {
        "profile": ("A_CS2", "A_CS1", False),
        "physical": ("A_CS1", "A_CS2", False),
        "control": ("BOTH_A_SIDES_SAME", "BOTH_A_SIDES_SAME", True),
        "unclear": ("UNCLEAR", "UNCLEAR", None),
    }
    left, right, equal = values[mode]
    for item in root["replicates"]:
        if item["code"] == code and item["row"] in rows:
            item.update(
                {
                    "t4_cs1_matches_t3_a": left,
                    "t4_cs2_matches_t3_a": right,
                    "t4_sides_equal": equal,
                    "operator_verbatim": mode,
                }
            )


def _t3_action() -> dict:
    return {
        "campaign_id": "a" * 64,
        "contract_id": "b" * 64,
        "descriptor_id": "c" * 64,
        "action_id": "d" * 64,
        "frame_sha256": "e" * 64,
        "cs1_dtm_sha256": "f" * 64,
        "cs2_dtm_sha256": "1" * 64,
        "profile_map": {
            "global_header": "active",
            "CS1": "active",
            "CS2": "commented",
        },
    }


def _t4_binding() -> dict:
    return {
        "path": "T4.json",
        "bytes": 1,
        "file_sha256": "2" * 64,
        "canonical_integrity_sha256": "3" * 64,
        "stage": subject.T4_STAGE,
        "campaign_id": "4" * 64,
        "test_id": "T4",
        "contract_id": "5" * 64,
        "descriptor_id": "6" * 64,
        "action_id": "7" * 64,
        "role": "POSITION_BALANCED_ATLAS",
        "round": 4,
        "firmware_sha256": "8" * 64,
        "frame_sha256": "e" * 64,
        "cs1_dtm_sha256": "f" * 64,
        "cs2_dtm_sha256": "1" * 64,
        "profile_id": "RAW_P16_T4_CA",
        "global_tuple_id": "9" * 64,
        "profile_map": {
            "global_header": "active",
            "CS1": "commented",
            "CS2": "active",
        },
    }


def test_template_has_exact_three_visible_replicates_for_each_code() -> None:
    template = subject.input_template()
    positions = [
        (item["code"], item["row"], item["column"]) for item in template["replicates"]
    ]
    assert len(positions) == len(set(positions)) == 24
    assert sorted(positions) == sorted(subject._expected_positions())  # noqa: SLF001
    assert {item["code"] for item in template["replicates"]} == set(range(8))


def test_three_of_three_profile_following_is_strong_pass() -> None:
    source = subject._validate_input(_input())  # noqa: SLF001
    result = subject._derive(source)  # noqa: SLF001
    assert result["screening_state"] == "PASS"
    assert result["matched_swap_conclusion"] == "PROFILE_FOLLOWING_STRONG"
    assert result["profile_hypothesis"] == "SUPPORTED"
    assert result["control_summary"]["all_non_discriminating"] is True


def test_four_candidates_with_three_primary_is_supported() -> None:
    source = _input()
    _set_code(source, 7, mode="unclear")
    result = subject._derive(subject._validate_input(source))  # noqa: SLF001
    assert result["screening_state"] == "PASS"
    assert result["matched_swap_conclusion"] == "PROFILE_FOLLOWING_SUPPORTED"


def test_two_of_three_is_review_only_and_can_make_overall_inconclusive() -> None:
    source = _input()
    for code in (0, 1):
        _set_code(source, code, mode="unclear", rows=(2,))
    result = subject._derive(subject._validate_input(source))  # noqa: SLF001
    by_code = {item["code"]: item for item in result["code_results"]}
    assert by_code[0]["classification"] == "REVIEW_PROFILE_TREND"
    assert by_code[1]["classification"] == "REVIEW_PROFILE_TREND"
    assert result["screening_state"] == "REVIEW"
    assert result["matched_swap_conclusion"] == "INCONCLUSIVE_MIXED"


def test_physical_side_following_is_valid_refutation_not_data_failure() -> None:
    source = _input()
    for code in subject.CANDIDATE_CODES:
        _set_code(source, code, mode="physical")
    result = subject._derive(subject._validate_input(source))  # noqa: SLF001
    assert result["screening_state"] == "PASS"
    assert result["matched_swap_conclusion"] == "PHYSICAL_SIDE_FOLLOWING_STRONG"
    assert result["profile_hypothesis"] == "REFUTED_BY_PHYSICAL_SIDE_FOLLOWING"


@pytest.mark.parametrize("failure", ["control", "artifact", "unstable", "supervision"])
def test_quality_failure_never_becomes_profile_or_physical_conclusion(
    failure: str,
) -> None:
    source = _input()
    if failure == "control":
        _set_code(source, 2, mode="profile")
    elif failure == "artifact":
        source["artifacts"]["horizontal_stripe"]["observed"] = True
    elif failure == "unstable":
        source["replicates"][0]["stable"] = False
    else:
        source["supervision"]["ambient_light_stable"] = False
    result = subject._derive(subject._validate_input(source))  # noqa: SLF001
    assert result["screening_state"] == "FAIL_DATA_QUALITY"
    assert result["matched_swap_conclusion"] == "INCONCLUSIVE_INPUT_OR_CONTROL_GATE"
    assert result["profile_hypothesis"] == "NOT_EVALUATED"


def test_input_rejects_duplicate_or_wrong_layout_position() -> None:
    duplicate = _input()
    duplicate["replicates"][1] = deepcopy(duplicate["replicates"][0])
    with pytest.raises(
        subject.T4MatchedSwapHumanObservationError,
        match="position set differs",
    ):
        subject._validate_input(duplicate)  # noqa: SLF001

    wrong = _input()
    wrong["replicates"][0]["column"] = 7
    with pytest.raises(
        subject.T4MatchedSwapHumanObservationError,
        match="code/position differs",
    ):
        subject._validate_input(wrong)  # noqa: SLF001


def test_build_report_binds_matched_swap_and_never_claims_colour(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    t3_path = tmp_path / "t3.json"
    t4_path = tmp_path / "t4.json"
    input_path = tmp_path / "input.json"
    t3_path.write_text("{}", encoding="utf-8")
    t4_path.write_text("{}", encoding="utf-8")
    input_path.write_text(json.dumps(_input(), ensure_ascii=False), encoding="utf-8")
    t3_root = {
        "integrity": {"sha256": "a" * 64},
        "automatic_conclusion": "PARTIAL_CAMERA_SCREEN_REVIEW",
    }
    monkeypatch.setattr(
        subject,
        "_t3_reference",
        lambda _path: (t3_root, b"{}", _t3_action()),
    )
    monkeypatch.setattr(
        subject,
        "_validate_t4_action_result",
        lambda _path: (_t4_binding(), {}),
    )
    report = subject.build_report(
        t3_partial_report_path=t3_path,
        t4_action_result_path=t4_path,
        operator_input_path=input_path,
    )
    assert report["matched_swap"]["only_profile_assignment_swapped"] is True
    assert report["derived"]["matched_swap_conclusion"] == "PROFILE_FOLLOWING_STRONG"
    assert report["classification_boundary"]["camera_evidence_in_this_report"] is False
    assert report["classification_boundary"]["qualified_colour_count"] == 0
    assert report["offline_execution"] == {
        "hardware_accessed": False,
        "camera_accessed": False,
        "network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
    }


def test_build_report_rejects_nonmatched_frame_or_profile_map(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(_input(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(
        subject,
        "_t3_reference",
        lambda _path: (
            {"integrity": {"sha256": "a" * 64}, "automatic_conclusion": "REVIEW"},
            b"{}",
            _t3_action(),
        ),
    )
    bad = _t4_binding()
    bad["frame_sha256"] = "0" * 64
    monkeypatch.setattr(subject, "_validate_t4_action_result", lambda _path: (bad, {}))
    with pytest.raises(
        subject.T4MatchedSwapHumanObservationError,
        match="frame/DTM differ",
    ):
        subject.build_report(
            t3_partial_report_path=tmp_path / "t3.json",
            t4_action_result_path=tmp_path / "t4.json",
            operator_input_path=input_path,
        )


def test_contract_explains_profile_vs_physical_and_no_io() -> None:
    contract = subject.describe_contract()
    assert contract["comparison"]["profile_following"].startswith("B-CS1")
    assert contract["candidate_codes"] == [0, 1, 4, 6, 7]
    assert contract["control_codes"] == [2, 3, 5]
    assert contract["replicates_per_code"] == 3
    assert contract["no_hardware_or_camera_io"] is True
    assert contract["rejected_action_ids"] == [
        subject.FAILED_T4_V1_ACTION_ID,
        subject.FAILED_T4_V2_ACTION_ID,
    ]


@pytest.mark.parametrize(
    "failed_action_id",
    [subject.FAILED_T4_V1_ACTION_ID, subject.FAILED_T4_V2_ACTION_ID],
)
def test_failed_unmutated_t4_v1_v2_action_results_are_permanently_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failed_action_id: str
) -> None:
    action_result = tmp_path / "failed-t4-action-result.json"
    action_result.write_text("{}", encoding="utf-8")
    failed = {
        "action": {"action_id": failed_action_id},
        "terminal_report": {"action_id": failed_action_id},
    }
    monkeypatch.setattr(subject, "_read_json", lambda *_args, **_kwargs: (b"{}", failed))
    monkeypatch.setattr(subject, "_verify_integrity", lambda *_args, **_kwargs: "a" * 64)
    monkeypatch.setattr(
        subject,
        "_t4_contract",
        lambda: {
            "action": {},
            "config": object(),
        },
    )
    with pytest.raises(
        subject.T4MatchedSwapHumanObservationError,
        match="failed T4 V1/V2 action result is permanently rejected",
    ):
        subject._validate_t4_action_result(action_result)  # noqa: SLF001


def test_frozen_t4_v3_pack_interface_is_the_exact_active_header_ca_swap() -> None:
    contract = subject._t4_contract()  # noqa: SLF001
    assert contract["pack"].STAGE == subject.T4_STAGE
    assert contract["action"]["action_id"] not in subject.REJECTED_ACTION_IDS
    assert all(
        action_id in tuple(contract["pack"].non_reusable_action_ids())
        for action_id in subject.REJECTED_ACTION_IDS
    )
    assert contract["action"]["action_id"] == (
        "90d769f4e139829bd5aed23ae03aa831be8b4b67159a3463f8747dbeb2c2baee"
    )
    assert contract["profile_map"] == {
        "global_header": "active",
        "CS1": "commented",
        "CS2": "active",
    }
    assert contract["action"]["round"] == 4
    assert contract["action"]["frame"]["sha256"] == (
        "1ff9588f4f7d00d7e9dd0a89d2c4fb08c25db7e6e044ee467af6187b3270ad23"
    )
    assert contract["action"]["cs1_dtm"]["sha256"] == (
        "2edcd090619b3a690b1d23db70df9b7648bad40b0512887df8a380a6f53fd1cb"
    )
    assert contract["action"]["cs2_dtm"]["sha256"] == (
        "2edcd090619b3a690b1d23db70df9b7648bad40b0512887df8a380a6f53fd1cb"
    )
