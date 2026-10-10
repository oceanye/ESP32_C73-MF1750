from __future__ import annotations

from copy import deepcopy
import json

import pytest

from tools import mf1750_p2_retained_clean_white_human_review as review


REPORTED_AT = "2026-09-04T08:00:00+08:00"
RECORDED_AT = "2026-09-04T08:00:01+08:00"
VERBATIM = (
    "全屏干净白，且无色块、边框、色斑、横竖线、底边间隔线或中心接缝异常"
)


def _arguments() -> dict:
    return {
        "reported_at": REPORTED_AT,
        "operator_verbatim": VERBATIM,
        "confirm_full_screen_clean_white": True,
        "confirm_no_visible_colour_block_border_stain_or_fixed_line": True,
        "confirm_direct_current_visual_inspection": True,
        "confirm_source_message_is_explicit_clean_white_confirmation": True,
        "recorded_at": RECORDED_AT,
    }


def test_latest_p1_white_machine_authority_is_exactly_bound() -> None:
    authority = review.validate_source_machine_authority()

    assert authority["source_action_id"] == review.EXPECTED_SOURCE_ACTION_ID
    assert authority["relay_off_commanded_and_queried"] is True
    assert authority["electrical_state_proven"] is False
    assert tuple(authority["files"]) == review.SOURCE_FILE_NAMES
    assert all(
        set(binding) == {"path", "bytes", "file_sha256", "canonical_sha256"}
        for binding in authority["files"].values()
    )


def test_review_preserves_verbatim_time_and_all_source_file_seals(tmp_path) -> None:
    output = tmp_path / "retained-clean-white-human-review.json"

    result = review.create_review(output_path=output, **_arguments())

    assert result["raw_operator_observation"]["operator_verbatim"] == VERBATIM
    assert result["raw_operator_observation"]["reported_at"] == REPORTED_AT
    assert result["recorded_at"] == RECORDED_AT
    assert result["machine_authority_binding"]["source_action_id"] == (
        review.EXPECTED_SOURCE_ACTION_ID
    )
    assert set(result["machine_authority_binding"]["files"]) == set(
        review.SOURCE_FILE_NAMES
    )
    assert result["evidence_boundaries"] == review.EVIDENCE_BOUNDARIES
    assert result["offline_execution"] == review.OFFLINE_EXECUTION
    assert review.validate_review(output) == result


def test_missing_explicit_clean_white_confirmation_writes_nothing(tmp_path) -> None:
    output = tmp_path / "must-not-exist.json"
    arguments = _arguments()
    arguments["confirm_full_screen_clean_white"] = False

    with pytest.raises(
        review.RetainedCleanWhiteHumanReviewError,
        match="explicit current clean-white",
    ):
        review.create_review(output_path=output, **arguments)

    assert not output.exists()


def test_report_before_bound_relay_off_is_rejected(tmp_path) -> None:
    output = tmp_path / "must-not-exist.json"
    arguments = _arguments()
    arguments["reported_at"] = "2026-09-01T20:00:00+08:00"

    with pytest.raises(
        review.RetainedCleanWhiteHumanReviewError,
        match="cannot precede the bound relay-OFF",
    ):
        review.create_review(output_path=output, **arguments)

    assert not output.exists()


def test_output_is_o_excl_and_first_record_is_preserved(tmp_path) -> None:
    output = tmp_path / "retained-clean-white-human-review.json"
    first = review.create_review(output_path=output, **_arguments())
    before = output.read_bytes()

    with pytest.raises(
        review.RetainedCleanWhiteHumanReviewError,
        match="refusing to overwrite",
    ):
        review.create_review(output_path=output, **_arguments())

    assert output.read_bytes() == before
    assert review.validate_review(output) == first


def test_tampered_verbatim_is_rejected_even_if_integrity_is_not_updated(
    tmp_path,
) -> None:
    output = tmp_path / "retained-clean-white-human-review.json"
    review.create_review(output_path=output, **_arguments())
    root = json.loads(output.read_text(encoding="utf-8"))
    root["raw_operator_observation"]["operator_verbatim"] = "tampered"
    output.write_bytes(review.canonical_json_bytes(root) + b"\n")

    with pytest.raises(
        review.RetainedCleanWhiteHumanReviewError,
        match="canonical integrity",
    ):
        review.validate_review(output)


def test_resealed_qualification_escalation_is_rejected(tmp_path) -> None:
    output = tmp_path / "retained-clean-white-human-review.json"
    review.create_review(output_path=output, **_arguments())
    root = json.loads(output.read_text(encoding="utf-8"))
    root.pop("integrity")
    root["evidence_boundaries"] = deepcopy(review.EVIDENCE_BOUNDARIES)
    root["evidence_boundaries"]["no_intervening_visible_refresh_proven"] = True
    output.write_bytes(review.canonical_json_bytes(review._seal(root)) + b"\n")  # noqa: SLF001

    with pytest.raises(
        review.RetainedCleanWhiteHumanReviewError,
        match="semantics differ",
    ):
        review.validate_review(output)


def test_cli_requires_all_four_explicit_confirmation_flags() -> None:
    with pytest.raises(SystemExit):
        review._parser().parse_args(  # noqa: SLF001
            [
                "seal",
                "--reported-at",
                REPORTED_AT,
                "--operator-verbatim",
                VERBATIM,
            ]
        )
