from __future__ import annotations

import copy
from collections.abc import Callable
import json
from pathlib import Path

import pytest

from tools import (
    mf1750_raw_p16_crossover_w4_post_white_camera_capture as capture,
)


MOUNT_ID = "mf1750-48mp-fixed-daylight-v1"
CORNERS = "200,150;3800,150;3800,2850;200,2850"


def test_describe_exposes_exact_default_root_identity_and_camera_lock() -> None:
    description = capture.build_description()

    assert capture.DEFAULT_OUTPUT_ROOT.as_posix() == (
        ".test-output/hardware/"
        "MF1750_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_"
        "WHITE_CAMERA_DAYLIGHT_V1"
    )
    assert description["default_output_root"] == capture.DEFAULT_OUTPUT_ROOT.as_posix()
    assert description["w4_action"]["action_id"] == (
        "e621ea9a05da45da4a120c2b68fbdefcad5f4a48274a5ac5290f5fcc25d7c55b"
    )
    assert description["w4_action"]["contract_id"] == (
        "7edf2e1916d536aa8b7d6d77be19899aab4fc6816e8c48de1e1b621bff0b7d52"
    )
    assert description["camera"]["target"]["logical_id"] == ("USB_VID_32E4_PID_4801")
    assert description["camera"]["target"]["required_directshow_token"] == (
        "vid_32e4&pid_4801"
    )
    assert description["camera"]["target"]["excluded_directshow_token"] == (
        "vid_1bcf&pid_0b15"
    )
    assert description["camera"]["profile"] == {
        "fourcc": "MJPG",
        "frame_width": 4000,
        "frame_height": 3000,
        "fps": 15.0,
        "autofocus": 0.0,
        "focus": 79.0,
        "auto_exposure": 0.25,
        "exposure": -6.0,
        "auto_white_balance": 0.0,
        "white_balance_temperature": 4600.0,
    }
    assert description["lifecycle"] == ["acquire", "admit", "seal", "validate"]
    assert description["maximum_attempts"] == 2
    assert description["attempt_claim_o_excl_before_camera_open"] is True
    assert description["automatic_retry"] is False
    assert description["automatic_fallback"] is False
    assert description["automatic_chaining"] is False


def test_literal_identity_is_cross_checked_against_w4_pack() -> None:
    expected = capture._expected_action_identity()  # noqa: SLF001

    assert expected == {
        "stage": capture.W4_STAGE,
        "campaign_id": capture.W4_CAMPAIGN_ID,
        "test_id": capture.W4_TEST_ID,
        "build_tag": capture.W4_BUILD_TAG,
        "contract_id": capture.W4_CONTRACT_ID,
        "firmware_sha256": capture.W4_FIRMWARE_SHA256,
        "action_id": capture.W4_ACTION_ID,
        "descriptor_id": capture.W4_DESCRIPTOR_ID,
        "role": capture.W4_ACTION_ROLE,
        "frame_sha256": capture.W4_FRAME_SHA256,
        "ordinal": 1,
    }


def test_contract_freezes_two_phase_attempt_and_coarse_gate_boundaries() -> None:
    contract = capture.build_contract(mount_id=MOUNT_ID)

    assert contract["default_output_root"] == capture.DEFAULT_OUTPUT_ROOT.as_posix()
    assert contract["attempt_boundary"] == {
        "maximum_attempts": 2,
        "one_camera_frame_maximum_per_acquire_invocation": True,
        "claim_o_excl_before_camera_open": True,
        "failed_claim_permanently_consumed": True,
        "automatic_retry": False,
        "automatic_fallback": False,
        "automatic_chaining": False,
    }
    assert contract["two_phase_boundary"] == {
        "acquire_has_no_panel_corners": True,
        "admit_has_no_camera_access": True,
        "admission_claim_o_excl_before_corner_parse_or_analysis": True,
        "every_claim_has_terminal_accepted_or_rejected_result": True,
        "corners_apply_to_exact_acquired_jpeg": True,
        "one_admission_maximum_per_acquisition": True,
    }
    assert contract["coarse_screen"]["minimum_lstar_hard_boundary"] == 25.0
    assert contract["coarse_screen"]["all_64_cells_required"] is True
    assert contract["coarse_screen"]["absolute_colour_qualification"] is False
    assert contract["coarse_screen"]["terminal_accepted_classification"] == capture.PASS
    assert contract["coarse_screen"]["terminal_rejected_classifications"] == [
        capture.REVIEW,
        capture.FAIL,
    ]
    assert (
        contract["coarse_screen"][
            "rejected_attempt_allows_explicit_next_acquire_within_budget"
        ]
        is True
    )


def _patch_action_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        capture,
        "_validate_action_source",
        lambda path: {
            **capture._expected_action_identity(),  # noqa: SLF001
            "source_bytes": Path(path).stat().st_size,
        },
    )


def test_failed_acquires_claim_before_open_call_once_and_exhaust_two_attempts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "w4-action.json"
    source.write_bytes(b"{}")
    _patch_action_validator(monkeypatch)
    calls = 0

    def fake_failure(**_kwargs):
        nonlocal calls
        calls += 1
        claim = tmp_path / "claims" / f"attempt-{calls:02d}.claim.json"
        assert claim.is_file(), "claim must exist before the backend can open a camera"
        raise RuntimeError("synthetic backend failure")

    first = capture.acquire_one(
        output_root=tmp_path,
        action_result_path=source,
        mount_id=MOUNT_ID,
        capture_function=fake_failure,
    )
    second = capture.acquire_one(
        output_root=tmp_path,
        action_result_path=source,
        mount_id=MOUNT_ID,
        capture_function=fake_failure,
    )

    assert first["acquired"] is second["acquired"] is False
    assert first["camera_invocations"] == second["camera_invocations"] == 1
    assert first["automatic_retry_count"] == second["automatic_retry_count"] == 0
    assert calls == 2
    with pytest.raises(capture.W4PostWhiteCameraError, match="budget 2 is exhausted"):
        capture.acquire_one(
            output_root=tmp_path,
            action_result_path=source,
            mount_id=MOUNT_ID,
            capture_function=fake_failure,
        )
    assert calls == 2


def _install_success_seams(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[Path, dict], list[dict], Callable[..., dict]]:
    registry: dict[Path, dict] = {}
    calls: list[dict] = []
    _patch_action_validator(monkeypatch)

    def fake_capture(**kwargs):
        calls.append(copy.deepcopy(kwargs))
        photo_path = Path(kwargs["photo_path"])
        sidecar_path = Path(kwargs["sidecar_path"])
        photo_path.parent.mkdir(parents=True, exist_ok=True)
        photo_path.write_bytes(b"same-exact-acquired-jpeg")
        sidecar_path.write_bytes(b"synthetic-sidecar")
        record = {
            **capture._expected_action_identity(),  # noqa: SLF001
            "capture_id": "capture-w4-01",
            "captured_at": "2026-08-31T09:00:00.000+08:00",
            "integrity": {"sha256": "1" * 64},
        }
        registry[sidecar_path.resolve()] = record
        return record

    monkeypatch.setattr(
        capture.camera,
        "validate_capture_evidence",
        lambda path: copy.deepcopy(registry[Path(path).resolve()]),
    )
    monkeypatch.setattr(
        capture,
        "_validate_capture_lock",
        lambda **_kwargs: {"fixed_capture": True},
    )
    return registry, calls, fake_capture


def _evaluation(
    corners: list[list[float]],
    *,
    classification: str = capture.PASS,
    white_passed: bool = True,
) -> dict:
    return {
        "geometry": {"supplied_panel_corners_tl_tr_br_bl": corners},
        "full_screen_white_gate": {
            "sample_count": 64,
            "expected_sample_count": 64,
            "minimum_cell_lstar": 60.0,
            "minimum_required_lstar": 25.0,
            "passed": white_passed,
            "cells": [],
        },
        "coarse_no_residual_gate": {
            "classification": classification,
            "clean_white_candidate": classification == capture.PASS,
            "camera_relative_only": True,
            "absolute_colour_qualification": False,
        },
        "classification": classification,
    }


def _pass_evaluation(corners: list[list[float]]) -> dict:
    return _evaluation(corners)


def test_acquire_then_admit_binds_corners_to_same_jpeg_and_seals(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "w4-action.json"
    source.write_bytes(b"{}")
    registry, calls, fake_capture = _install_success_seams(monkeypatch)
    monkeypatch.setattr(
        capture,
        "_evaluate_photo",
        lambda payload, corners: _pass_evaluation(corners),
    )

    acquired = capture.acquire_one(
        output_root=tmp_path,
        action_result_path=source,
        mount_id=MOUNT_ID,
        capture_function=fake_capture,
    )
    assert acquired["acquired"] is True
    assert acquired["panel_corners_present"] is False
    assert acquired["capture"]["photo"]["sha256"] == capture._sha256_bytes(  # noqa: SLF001
        b"same-exact-acquired-jpeg"
    )
    assert len(calls) == 1
    call = calls[0]
    assert "panel_corners" not in call
    assert call["camera_id"] == "USB_VID_32E4_PID_4801"
    assert call["camera_index"] is None
    assert call["camera_instance_id"] is None
    assert call["requested_settings"] == capture.CAMERA_PROFILE

    with pytest.raises(
        capture.W4PostWhiteCameraError, match="must be admitted before another"
    ):
        capture.acquire_one(
            output_root=tmp_path,
            action_result_path=source,
            mount_id=MOUNT_ID,
            capture_function=fake_capture,
        )
    assert len(calls) == 1

    admitted = capture.admit_one(
        output_root=tmp_path,
        attempt=1,
        panel_corners=CORNERS,
    )
    assert admitted["evidence_admitted"] is True
    assert admitted["accepted"] is True
    assert admitted["terminal_state"] == "ACCEPTED"
    assert admitted["classification"] == capture.PASS
    assert admitted["photo_sha256"] == acquired["capture"]["photo"]["sha256"]
    assert admitted["camera_invocations_during_admit"] == 0
    assert len(calls) == 1

    sealed = capture.seal_capture(output_root=tmp_path)
    assert sealed["classification"] == capture.PASS
    assert sealed["photo_sha256"] == admitted["photo_sha256"]
    assert sealed["panel_corners_tl_tr_br_bl"] == admitted["panel_corners_tl_tr_br_bl"]
    validated = capture.validate_seal(tmp_path / "post-white-camera-seal.json")
    assert validated == sealed
    assert len(registry) == 1
    assert len(calls) == 1


def test_admit_output_is_o_excl(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "w4-action.json"
    source.write_bytes(b"{}")
    _registry, _calls, fake_capture = _install_success_seams(monkeypatch)
    monkeypatch.setattr(
        capture,
        "_evaluate_photo",
        lambda payload, corners: _pass_evaluation(corners),
    )
    capture.acquire_one(
        output_root=tmp_path,
        action_result_path=source,
        mount_id=MOUNT_ID,
        capture_function=fake_capture,
    )
    capture.admit_one(output_root=tmp_path, attempt=1, panel_corners=CORNERS)

    with pytest.raises(capture.W4PostWhiteCameraError, match="refusing to overwrite"):
        capture.admit_one(output_root=tmp_path, attempt=1, panel_corners=CORNERS)


@pytest.mark.parametrize(
    ("tamper_target", "error_match"),
    [
        ("acquisition-claim", "acquisition claim binding differs"),
        ("admission-acquisition", "admission acquisition binding differs"),
    ],
)
def test_seal_rejects_resigned_semantic_binding_tamper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tamper_target: str,
    error_match: str,
) -> None:
    source = tmp_path / "w4-action.json"
    source.write_bytes(b"{}")
    _registry, _calls, fake_capture = _install_success_seams(monkeypatch)
    monkeypatch.setattr(
        capture,
        "_evaluate_photo",
        lambda payload, corners: _pass_evaluation(corners),
    )
    capture.acquire_one(
        output_root=tmp_path,
        action_result_path=source,
        mount_id=MOUNT_ID,
        capture_function=fake_capture,
    )
    capture.admit_one(output_root=tmp_path, attempt=1, panel_corners=CORNERS)

    acquisition_path = tmp_path / "acquisitions" / "attempt-01.acquisition.json"
    admission_path = tmp_path / "admissions" / "attempt-01.claim.json"
    result_path = tmp_path / "results" / "attempt-01.result.json"
    acquisition = json.loads(acquisition_path.read_text(encoding="utf-8"))
    if tamper_target == "acquisition-claim":
        acquisition["claim"]["path"] = "C:/forged/not-the-attempt-claim.json"
        acquisition = capture._seal(acquisition)  # noqa: SLF001
        acquisition_path.write_bytes(capture._json_bytes(acquisition))  # noqa: SLF001

    admission = json.loads(admission_path.read_text(encoding="utf-8"))
    if tamper_target == "acquisition-claim":
        acquisition_payload = acquisition_path.read_bytes()
        admission["acquisition"] = {
            **capture._file_binding(  # noqa: SLF001
                acquisition_path, acquisition_payload
            ),
            "integrity_sha256": acquisition["integrity"]["sha256"],
        }
        admission["acquisition_integrity_sha256"] = acquisition["integrity"]["sha256"]
    else:
        admission["acquisition"]["path"] = "C:/forged/not-the-acquisition.json"
    admission = capture._seal(admission)  # noqa: SLF001
    admission_path.write_bytes(capture._json_bytes(admission))  # noqa: SLF001

    result = json.loads(result_path.read_text(encoding="utf-8"))
    admission_payload = admission_path.read_bytes()
    result["admission_claim"] = {
        **capture._file_binding(admission_path, admission_payload),  # noqa: SLF001
        "integrity_sha256": admission["integrity"]["sha256"],
    }
    result = capture._seal(result)  # noqa: SLF001
    result_path.write_bytes(capture._json_bytes(result))  # noqa: SLF001

    with pytest.raises(capture.W4PostWhiteCameraError, match=error_match):
        capture.build_seal(output_root=tmp_path)


@pytest.mark.parametrize("first_classification", [capture.REVIEW, capture.FAIL])
def test_non_pass_is_terminal_rejected_then_explicit_attempt_two_can_pass_and_seal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    first_classification: str,
) -> None:
    source = tmp_path / "w4-action.json"
    source.write_bytes(b"{}")
    _registry, calls, fake_capture = _install_success_seams(monkeypatch)
    evaluation_calls = 0

    def staged_evaluation(_payload, corners):
        nonlocal evaluation_calls
        evaluation_calls += 1
        classification = first_classification if evaluation_calls == 1 else capture.PASS
        return _evaluation(corners, classification=classification)

    monkeypatch.setattr(capture, "_evaluate_photo", staged_evaluation)
    first_acquisition = capture.acquire_one(
        output_root=tmp_path,
        action_result_path=source,
        mount_id=MOUNT_ID,
        capture_function=fake_capture,
    )
    assert first_acquisition["attempt"] == 1
    first_result = capture.admit_one(
        output_root=tmp_path, attempt=1, panel_corners=CORNERS
    )
    assert first_result["accepted"] is False
    assert first_result["evidence_admitted"] is False
    assert first_result["terminal_state"] == "REJECTED"
    assert first_result["classification"] == first_classification
    assert first_result["evaluation"]["classification"] == first_classification
    with pytest.raises(
        capture.W4PostWhiteCameraError,
        match="seal requires exactly one full-screen-white admitted capture",
    ):
        capture.seal_capture(output_root=tmp_path)

    second_acquisition = capture.acquire_one(
        output_root=tmp_path,
        action_result_path=source,
        mount_id=MOUNT_ID,
        capture_function=fake_capture,
    )
    assert second_acquisition["attempt"] == 2
    second_result = capture.admit_one(
        output_root=tmp_path, attempt=2, panel_corners=CORNERS
    )
    assert second_result["accepted"] is True
    assert second_result["classification"] == capture.PASS
    sealed = capture.seal_capture(output_root=tmp_path)
    assert sealed["attempt_count"] == 2
    assert sealed["admitted_attempt"] == 2
    assert sealed["classification"] == capture.PASS
    assert len(calls) == 2


def test_noncanonical_evaluation_exception_still_writes_terminal_rejection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "w4-action.json"
    source.write_bytes(b"{}")
    _registry, calls, fake_capture = _install_success_seams(monkeypatch)
    monkeypatch.setattr(
        capture,
        "_evaluate_photo",
        lambda payload, corners: {
            **_pass_evaluation(corners),
            "synthetic_noncanonical": float("nan"),
        },
    )
    capture.acquire_one(
        output_root=tmp_path,
        action_result_path=source,
        mount_id=MOUNT_ID,
        capture_function=fake_capture,
    )

    result = capture.admit_one(output_root=tmp_path, attempt=1, panel_corners=CORNERS)

    assert result["accepted"] is False
    assert result["terminal_state"] == "REJECTED"
    assert result["classification"] == capture.FAIL
    assert result["evaluation"] is None
    assert (tmp_path / "results" / "attempt-01.result.json").is_file()
    assert len(calls) == 1


@pytest.mark.parametrize("failure_mode", ["invalid-corners", "analysis-error"])
def test_admission_claim_precedes_parse_and_analysis_and_rejection_is_terminal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure_mode: str,
) -> None:
    source = tmp_path / "w4-action.json"
    source.write_bytes(b"{}")
    _registry, calls, fake_capture = _install_success_seams(monkeypatch)
    capture.acquire_one(
        output_root=tmp_path,
        action_result_path=source,
        mount_id=MOUNT_ID,
        capture_function=fake_capture,
    )
    admission_claim = tmp_path / "admissions" / "attempt-01.claim.json"
    terminal_result = tmp_path / "results" / "attempt-01.result.json"
    real_normalise = capture._normalise_panel_corners  # noqa: SLF001
    parse_observed = False
    analysis_observed = False

    def guarded_normalise(value):
        nonlocal parse_observed
        parse_observed = True
        assert admission_claim.is_file()
        return real_normalise(value)

    def guarded_evaluate(_payload, _corners):
        nonlocal analysis_observed
        analysis_observed = True
        assert admission_claim.is_file()
        raise RuntimeError("synthetic analysis failure")

    monkeypatch.setattr(capture, "_normalise_panel_corners", guarded_normalise)
    monkeypatch.setattr(capture, "_evaluate_photo", guarded_evaluate)
    corners = "1,1;10,1;10,10;1,10" if failure_mode == "invalid-corners" else CORNERS

    result = capture.admit_one(
        output_root=tmp_path,
        attempt=1,
        panel_corners=corners,
    )

    assert parse_observed is True
    assert analysis_observed is (failure_mode == "analysis-error")
    assert admission_claim.is_file()
    assert terminal_result.is_file()
    assert result["accepted"] is False
    assert result["terminal_state"] == "REJECTED"
    assert result["outcome"] == "REJECTED_FAIL_CLOSED_NO_READMISSION"
    assert result["camera_invocations_during_admit"] == 0
    assert len(calls) == 1
    with pytest.raises(capture.W4PostWhiteCameraError, match="refusing to overwrite"):
        capture.admit_one(
            output_root=tmp_path,
            attempt=1,
            panel_corners=CORNERS,
        )
    assert len(calls) == 1


def test_uniform_48mp_white_passes_actual_64_cell_and_residual_screen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    np = pytest.importorskip("numpy")
    rgb = np.full((3000, 4000, 3), 180, dtype=np.uint8)
    monkeypatch.setattr(capture.geometry.base, "_decode_rgb", lambda _payload: rgb)

    evaluation = capture._evaluate_photo(b"synthetic", CORNERS)  # noqa: SLF001

    assert evaluation["full_screen_white_gate"]["sample_count"] == 64
    assert evaluation["full_screen_white_gate"]["passed"] is True
    assert evaluation["coarse_no_residual_gate"]["classification"] == capture.PASS
    assert evaluation["coarse_no_residual_gate"]["clean_white_candidate"] is True


def test_bottom_residual_fails_actual_coarse_gate_without_absolute_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    np = pytest.importorskip("numpy")
    rgb = np.full((3000, 4000, 3), 180, dtype=np.uint8)
    rgb[2450:2851, 200:3801] = np.asarray([180, 80, 80], dtype=np.uint8)
    monkeypatch.setattr(capture.geometry.base, "_decode_rgb", lambda _payload: rgb)

    evaluation = capture._evaluate_photo(b"synthetic", CORNERS)  # noqa: SLF001

    assert evaluation["full_screen_white_gate"]["minimum_cell_lstar"] >= 25.0
    assert evaluation["coarse_no_residual_gate"]["classification"] == capture.FAIL
    assert evaluation["coarse_no_residual_gate"]["clean_white_candidate"] is False
    assert (
        evaluation["coarse_no_residual_gate"]["absolute_colour_qualification"] is False
    )


def test_low_illumination_is_hard_fail_and_never_admitted_as_white(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    np = pytest.importorskip("numpy")
    rgb = np.full((3000, 4000, 3), 20, dtype=np.uint8)
    monkeypatch.setattr(capture.geometry.base, "_decode_rgb", lambda _payload: rgb)

    evaluation = capture._evaluate_photo(b"synthetic", CORNERS)  # noqa: SLF001

    assert evaluation["full_screen_white_gate"]["passed"] is False
    assert evaluation["classification"] == capture.FAIL


def test_cli_has_no_camera_or_setting_override_and_corners_only_on_admit() -> None:
    parser = capture._parser()  # noqa: SLF001
    help_text = parser.format_help()
    assert "acquire" in help_text
    acquire = parser.parse_args(
        ["acquire", "--action-result", "action.json", "--mount-id", MOUNT_ID]
    )
    assert not hasattr(acquire, "panel_corners")
    assert not hasattr(acquire, "camera_index")
    assert not hasattr(acquire, "exposure")
    admit = parser.parse_args(["admit", "--attempt", "1", "--panel-corners", CORNERS])
    assert admit.panel_corners == CORNERS
    assert not hasattr(admit, "action_result")
