from __future__ import annotations

import copy

import pytest

from tools import (
    mf1750_raw_p16_crossover_t1_successor_t2_white_normalized_coarse_comparison as comparison,
)


POSITIONS = ((0, 0), (1, 2), (2, 5), (3, 7))


def _group(controller: int, code: int, base: list[float], state="PASS") -> dict:
    return {
        "controller": controller,
        "code": code,
        "classification": state,
        "position_results": [
            {
                "row": row,
                "column": column,
                "position_eligible": True,
                "normalized_lab_median": [
                    base[0] + index * 0.1,
                    base[1],
                    base[2],
                ],
            }
            for index, (row, column) in enumerate(POSITIONS)
        ],
    }


def _reports(model: str) -> tuple[dict, dict]:
    active = [50.0, 24.0, 12.0]
    commented = [35.0, -16.0, -20.0]
    t1_groups = []
    t2_groups = []
    for code in range(8):
        offset = [float(code), 0.0, 0.0]
        t1_active = [a + b for a, b in zip(active, offset, strict=True)]
        t1_commented = [a + b for a, b in zip(commented, offset, strict=True)]
        if model == "ambiguous":
            t1_active = t1_commented = [42.5 + code, 4.0, -4.0]
        t1_groups.extend([_group(0, code, t1_active), _group(1, code, t1_commented)])
        if model == "profile":
            t2_cs1, t2_cs2 = t1_commented, t1_active
        elif model == "position":
            t2_cs1, t2_cs2 = t1_active, t1_commented
        elif model == "ambiguous":
            middle = [42.5 + code, 4.0, -4.0]
            t2_cs1 = t2_cs2 = middle
        else:
            t2_cs1 = t2_cs2 = [95.0, -60.0, 60.0]
        t2_groups.extend([_group(0, code, t2_cs1), _group(1, code, t2_cs2)])
    return {"group_results": t1_groups}, {"group_results": t2_groups}


def test_profile_swap_is_pass_profile_following_candidate() -> None:
    result = comparison.compare_reports(*_reports("profile"))

    assert result["summary"]["state"] == ("PROFILE_FOLLOWING_COARSE_CANDIDATES_PRESENT")
    assert result["summary"]["candidate_classification_counts"] == {
        "PASS": 8,
        "REVIEW": 0,
        "FAIL": 0,
    }
    assert result["summary"]["coarse_judgement_counts"] == {
        comparison.PROFILE_FOLLOWING: 8,
        comparison.POSITION_FOLLOWING: 0,
        comparison.INCONCLUSIVE: 0,
    }
    assert all(
        item["coarse_judgement"] == comparison.PROFILE_FOLLOWING
        and item["qualification_effect"] == "NONE"
        for item in result["code_results"]
    )


def test_physical_side_model_is_pass_position_following_candidate() -> None:
    result = comparison.compare_reports(*_reports("position"))

    assert result["summary"]["state"] == (
        "POSITION_FOLLOWING_COARSE_CANDIDATES_PRESENT"
    )
    assert result["summary"]["candidate_classification_counts"]["PASS"] == 8
    assert all(
        item["coarse_judgement"] == comparison.POSITION_FOLLOWING
        for item in result["code_results"]
    )


def test_ambiguous_models_are_review_not_false_pass() -> None:
    result = comparison.compare_reports(*_reports("ambiguous"))

    assert result["summary"]["state"] == "MIXED_OR_INCONCLUSIVE_COARSE_CANDIDATES"
    assert result["summary"]["candidate_classification_counts"]["PASS"] == 0
    assert result["summary"]["candidate_classification_counts"]["REVIEW"] == 8
    assert all(
        item["coarse_judgement"] == comparison.INCONCLUSIVE
        for item in result["code_results"]
    )


def test_failed_source_group_blocks_only_its_code() -> None:
    t1, t2 = _reports("profile")
    target = next(
        item
        for item in t2["group_results"]
        if item["controller"] == 1 and item["code"] == 5
    )
    target["classification"] = "FAIL"

    result = comparison.compare_reports(t1, t2)

    assert result["code_results"][5]["candidate_classification"] == "FAIL"
    assert result["code_results"][4]["candidate_classification"] == "PASS"
    assert result["summary"]["candidate_classification_counts"] == {
        "PASS": 7,
        "REVIEW": 0,
        "FAIL": 1,
    }


def test_outside_both_model_review_thresholds_fails() -> None:
    result = comparison.compare_reports(*_reports("far"))

    assert result["summary"]["candidate_classification_counts"]["FAIL"] == 8


def test_missing_position_or_duplicate_group_fails_closed() -> None:
    t1, t2 = _reports("profile")
    broken = copy.deepcopy(t2)
    broken["group_results"][0]["position_results"].pop()
    with pytest.raises(
        comparison.DiscoveryCoarseComparisonError, match="four positions"
    ):
        comparison.compare_reports(t1, broken)

    duplicate = copy.deepcopy(t2)
    duplicate["group_results"][1]["controller"] = 0
    with pytest.raises(comparison.DiscoveryCoarseComparisonError, match="identity"):
        comparison.compare_reports(t1, duplicate)


def test_threshold_edges_and_exclusive_output(tmp_path) -> None:
    assert comparison._model_classification(8.0) == "PASS"  # noqa: SLF001
    assert comparison._model_classification(8.0001) == "REVIEW"  # noqa: SLF001
    assert comparison._model_classification(12.0) == "REVIEW"  # noqa: SLF001
    assert comparison._model_classification(12.0001) == "FAIL"  # noqa: SLF001
    output = tmp_path / "comparison.json"
    comparison._write_exclusive(output, b"first\n")  # noqa: SLF001
    with pytest.raises(comparison.DiscoveryCoarseComparisonError, match="overwrite"):
        comparison._write_exclusive(output, b"second\n")  # noqa: SLF001


def test_summary_never_qualifies_or_changes_formal_gate() -> None:
    result = comparison.compare_reports(*_reports("profile"))
    summary = result["summary"]

    assert summary["screening_only"] is True
    assert summary["formal_gate_evaluated"] is False
    assert summary["formal_gate_changed"] is False
    assert summary["formal_advance_to_t2_permitted"] is False
    assert summary["qualified_colour_count"] == 0
    assert summary["profile_following_proven"] is False
