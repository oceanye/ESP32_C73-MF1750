from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools import (
    mf1750_raw_p16_crossover_t3_camera_capture_pack as pack,
)


CORNERS = "500,400;3500,500;3400,2600;600,2500"
MOUNT = "mf1750-48mp-fixed-daylight-v1"
PARTIAL_BLOCKS = json.dumps(
    {
        "CS1": [[500, 400], [1800, 400], [1800, 1500], [500, 1500]],
        "CS2": [[2200, 400], [3500, 400], [3500, 1500], [2200, 1500]],
    },
    separators=(",", ":"),
)


def test_contract_freezes_exact_48mp_exp6_four_frame_boundary() -> None:
    contract = pack.build_contract(mount_id=MOUNT, panel_corners=CORNERS)

    assert contract["camera"]["target"] == {
        "logical_id": "USB_VID_32E4_PID_4801",
        "friendly_name": "48MP USB Camera",
        "required_directshow_token": "vid_32e4&pid_4801",
        "excluded_directshow_token": "vid_1bcf&pid_0b15",
    }
    assert contract["camera"]["profile"] == {
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
    assert contract["slots"][pack.WHITE_SLOT]["required_accepted"] == 1
    assert contract["slots"][pack.T3_SLOT]["required_accepted"] == 3
    assert contract["slots"][pack.WHITE_SLOT]["maximum_attempts"] == 2
    assert contract["slots"][pack.T3_SLOT]["maximum_attempts"] == 5
    assert contract["attempt_boundary"]["maximum_total_attempts"] == 7
    assert contract["attempt_boundary"]["automatic_retry"] is False
    assert contract["attempt_boundary"]["admission_claim_written_before_corner_parsing"]
    assert contract["illumination"]["automatic_threshold_relaxation"] is False
    assert contract["geometry"]["two_phase_acquire_then_admit_required"] is True
    assert contract["geometry"]["corners_forbidden_during_acquire"] is True
    assert contract["geometry"]["per_frame_corners_recorded_independently"] is True
    assert contract["geometry"]["same_corners_reused_by_assumption"] is False
    assert (
        contract["geometry"]["maximum_cross_capture_corresponding_corner_drift_px"]
        == 30.0
    )
    assert contract["w4_following_boundary"] == {
        "core_four_frame_bundle_success_unlocks_w4": True,
        "camera_classification_required_before_safe_w4_white": False,
        "w4_post_white_is_independent_fifth_frame": True,
        "w4_post_white_included_in_this_bundle": False,
        "analysis_may_continue_after_white_containment": True,
    }
    assert (
        contract["slots"][pack.T3_SLOT]["action"]["action_id"]
        == "db009936f341cd612be9aa47d08a0a316ec2c581c3c88d35d089ce3fa5857104"
    )
    assert pack.DEFAULT_OUTPUT_ROOT.name == (
        "MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_CAMERA_DAYLIGHT_V1"
    )


def test_partial_contract_is_independent_and_cannot_promote_to_full_or_w4() -> None:
    full = pack.build_contract(mount_id=MOUNT)
    partial = pack.build_partial_contract(mount_id=MOUNT)

    assert full["camera"]["coverage_scope"] == pack.camera.COVERAGE_FULL
    assert full["camera"]["full_panel_visible"] is True
    assert partial["kind"] == pack.PARTIAL_CONTRACT_KIND
    assert partial["mode"] == pack.PARTIAL_MODE
    assert partial["camera"]["coverage_scope"] == pack.camera.COVERAGE_PARTIAL
    assert partial["camera"]["full_panel_visible"] is False
    assert partial["geometry"]["selected_rows"] == [0, 1, 2]
    assert partial["geometry"]["selected_columns"] == list(range(8))
    assert partial["geometry"]["selected_cell_count"] == 48
    assert partial["geometry"]["replicates_per_code_per_controller_per_frame"] == 3
    assert partial["geometry"]["outside_roi_status"] == (
        "NOT_EVALUATED_OUTSIDE_SELECTED_ROI"
    )
    assert partial["evidence"]["formal_full_panel_evidence"] is False
    assert partial["evidence"]["profile_following_decision_earned"] is False
    assert partial["w4_following_boundary"][
        "w4_post_white_full_screen_seal_earned"
    ] is False
    assert partial["w4_following_boundary"][
        "partial_roi_may_be_promoted_to_w4_full_white_seal"
    ] is False


def test_invalid_or_too_small_geometry_fails_before_contract_write(
    tmp_path: Path,
) -> None:
    with pytest.raises(pack.T3CameraCapturePackError, match="panel geometry rejected"):
        pack.ensure_contract(
            output_root=tmp_path,
            mount_id=MOUNT,
            panel_corners="1,1;10,1;10,10;1,10",
        )
    assert not (tmp_path / "capture-contract.json").exists()


def test_each_frame_can_record_its_own_valid_corners_but_drift_is_capped(
    tmp_path: Path,
) -> None:
    first = pack.ensure_contract(
        output_root=tmp_path,
        mount_id=MOUNT,
        panel_corners=CORNERS,
    )
    second = pack.ensure_contract(
        output_root=tmp_path,
        mount_id=MOUNT,
        panel_corners="502,401;3502,501;3402,2601;602,2501",
    )
    assert first == second
    geometry_a = {
        "supplied_panel_corners_tl_tr_br_bl": [
            [500.0, 400.0],
            [3500.0, 500.0],
            [3400.0, 2600.0],
            [600.0, 2500.0],
        ]
    }
    geometry_b = {
        "supplied_panel_corners_tl_tr_br_bl": [
            [530.0, 400.0],
            [3530.0, 500.0],
            [3430.0, 2600.0],
            [630.0, 2500.0],
        ]
    }
    assert (
        pack._corresponding_corner_drift(geometry_a, geometry_b)[  # noqa: SLF001
            "maximum_corresponding_corner_drift_px"
        ]
        == 30.0
    )
    geometry_b["supplied_panel_corners_tl_tr_br_bl"][0][0] = 531.0
    with pytest.raises(pack.T3CameraCapturePackError, match="corner drift rejected"):
        pack._corresponding_corner_drift(geometry_a, geometry_b)  # noqa: SLF001


def test_low_illumination_gate_fails_closed_without_threshold_relaxation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Rgb:
        shape = (3000, 4000, 3)

    monkeypatch.setattr(pack.geometry.base, "_decode_rgb", lambda _payload: _Rgb())

    def sample(_rgb, _homography, cell):
        lstar = 24.0 if cell["controller"] == 0 and cell["row"] == 0 else 80.0
        return {
            **cell,
            "camera_relative_lab_d65_from_rgb_median": [lstar, 0.0, 0.0],
        }

    monkeypatch.setattr(pack.geometry.base, "_sample_cell", sample)
    with pytest.raises(
        pack.T3CameraCapturePackError, match="low illumination rejected"
    ):
        pack._sample_gate(  # noqa: SLF001
            slot=pack.WHITE_SLOT,
            photo_payload=b"not-decoded-by-test-seam",
            panel_corners=CORNERS,
        )


def test_failed_camera_reads_consume_attempts_without_automatic_retry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    action = tmp_path / "source-action.json"
    action.write_bytes(b"{}")
    calls = 0

    monkeypatch.setattr(
        pack,
        "_validate_action_source",
        lambda slot, path, *, partial=False: {
            **pack._expected_action_identity(slot, partial=partial),
            "path": str(path),
        },
    )

    def fail_once(**_kwargs):
        nonlocal calls
        calls += 1
        claims = list((tmp_path / "claims").glob("*.claim.json"))
        assert len(claims) == calls
        raise pack.T3CameraCapturePackError("synthetic camera failure")

    first = pack.acquire_one(
        slot=pack.WHITE_SLOT,
        output_root=tmp_path,
        action_result_path=action,
        mount_id=MOUNT,
        capture_function=fail_once,
    )
    second = pack.acquire_one(
        slot=pack.WHITE_SLOT,
        output_root=tmp_path,
        action_result_path=action,
        mount_id=MOUNT,
        capture_function=fail_once,
    )
    assert first["acquired"] is False
    assert second["acquired"] is False
    assert first["camera_invocations"] == second["camera_invocations"] == 1
    assert first["automatic_retry_count"] == second["automatic_retry_count"] == 0
    assert calls == 2
    with pytest.raises(pack.T3CameraCapturePackError, match="budget 2 is exhausted"):
        pack.acquire_one(
            slot=pack.WHITE_SLOT,
            output_root=tmp_path,
            action_result_path=action,
            mount_id=MOUNT,
            capture_function=fail_once,
        )
    assert calls == 2


def _install_success_seams(
    monkeypatch: pytest.MonkeyPatch,
    *,
    t3_alignment_change: bool = False,
):
    registry: dict[Path, dict] = {}
    counter = 0

    monkeypatch.setattr(
        pack,
        "_validate_action_source",
        lambda slot, path, *, partial=False: {
            **pack._expected_action_identity(slot, partial=partial),
            "path": str(path),
        },
    )

    def capture(**kwargs):
        nonlocal counter
        counter += 1
        photo = Path(kwargs["photo_path"])
        sidecar = Path(kwargs["sidecar_path"])
        photo.parent.mkdir(parents=True, exist_ok=True)
        photo.write_bytes(f"unique-photo-{counter}".encode())
        sidecar.write_bytes(f"unique-sidecar-{counter}".encode())
        expected = (
            pack._expected_action_identity(pack.WHITE_SLOT)  # noqa: SLF001
            if counter == 1
            else pack._expected_action_identity(pack.T3_SLOT)  # noqa: SLF001
        )
        registry[sidecar.resolve()] = {
            **expected,
            "capture_id": f"capture-{counter}",
            "captured_at": f"2026-09-01T09:00:0{counter}+08:00",
            "integrity": {"sha256": f"{counter:064x}"},
        }
        return registry[sidecar.resolve()]

    monkeypatch.setattr(
        pack.camera,
        "validate_capture_evidence",
        lambda path: copy.deepcopy(registry[Path(path).resolve()]),
    )

    base_alignment = {
        "camera_id": "48MP USB Camera",
        "instance_id": "usb#vid_32e4&pid_4801#fixed",
        "backend": "DSHOW",
        "mount_id": MOUNT,
        "requested_settings": copy.deepcopy(pack.CAMERA_PROFILE),
        "effective_settings_before_frame": {"exposure": -6.0},
        "effective_settings_after_frame": {"exposure": -6.0},
        "photo_width": 4000,
        "photo_height": 3000,
    }

    def evaluate(*, slot, capture, panel_corners, **_kwargs):
        alignment = copy.deepcopy(base_alignment)
        if t3_alignment_change and slot == pack.T3_SLOT:
            alignment["instance_id"] = "usb#vid_32e4&pid_4801#changed"
        return {
            "camera_lock": {"fixed_exposure_boundary": -6.0},
            "alignment": alignment,
            "geometry": {
                "sampling_geometry_admitted": True,
                "supplied_panel_corners_tl_tr_br_bl": [
                    [float(component) for component in row] for row in panel_corners
                ],
            },
            "illumination": {
                "minimum_lstar": 50.0,
                "minimum_required_lstar": 25.0,
                "passed": True,
            },
        }

    monkeypatch.setattr(pack, "_evaluate_capture", evaluate)

    def validate_acquired(*, capture, **_kwargs):
        alignment = copy.deepcopy(base_alignment)
        if t3_alignment_change and capture["capture_id"] != "capture-1":
            alignment["instance_id"] = "usb#vid_32e4&pid_4801#changed"
        return {
            "camera_lock": {"fixed_exposure_boundary": -6.0},
            "alignment": alignment,
        }

    monkeypatch.setattr(pack, "_validate_acquired_capture", validate_acquired)
    return capture


def _install_partial_success_seams(monkeypatch: pytest.MonkeyPatch):
    registry: dict[Path, dict] = {}
    counter = 0
    monkeypatch.setattr(
        pack,
        "_validate_action_source",
        lambda slot, path, *, partial=False: {
            **pack._expected_action_identity(slot, partial=partial),
            "path": str(path),
        },
    )

    def capture(**kwargs):
        nonlocal counter
        assert kwargs["coverage_scope"] == pack.camera.COVERAGE_PARTIAL
        assert kwargs["automated_verdict"] == "INCONCLUSIVE"
        assert kwargs["assessment_confidence"] == "low"
        counter += 1
        photo = Path(kwargs["photo_path"])
        sidecar = Path(kwargs["sidecar_path"])
        photo.parent.mkdir(parents=True, exist_ok=True)
        photo.write_bytes(f"partial-photo-{counter}".encode())
        sidecar.write_bytes(f"partial-sidecar-{counter}".encode())
        expected = pack._expected_action_identity(  # noqa: SLF001
            pack.WHITE_SLOT if counter == 1 else pack.T3_SLOT,
            partial=True,
        )
        registry[sidecar.resolve()] = {
            **expected,
            "capture_id": f"partial-capture-{counter}",
            "captured_at": f"2026-09-01T10:00:0{counter}+08:00",
            "integrity": {"sha256": f"{counter + 100:064x}"},
        }
        return copy.deepcopy(registry[sidecar.resolve()])

    monkeypatch.setattr(
        pack.camera,
        "validate_capture_evidence",
        lambda path: copy.deepcopy(registry[Path(path).resolve()]),
    )
    alignment = {
        "camera_id": "48MP USB Camera",
        "instance_id": "usb#vid_32e4&pid_4801#fixed",
        "backend": "DSHOW",
        "mount_id": MOUNT,
        "requested_settings": copy.deepcopy(pack.CAMERA_PROFILE),
        "effective_settings_before_frame": {"exposure": -6.0},
        "effective_settings_after_frame": {"exposure": -6.0},
        "photo_width": 4000,
        "photo_height": 3000,
    }
    monkeypatch.setattr(
        pack,
        "_validate_partial_acquired_capture",
        lambda **_kwargs: {
            "camera_lock": {"fixed_exposure_boundary": -6.0},
            "alignment": copy.deepcopy(alignment),
        },
    )

    def evaluate(*, partial_blocks, **_kwargs):
        return {
            "camera_lock": {"fixed_exposure_boundary": -6.0},
            "alignment": copy.deepcopy(alignment),
            "geometry": {
                "mode": pack.PARTIAL_MODE,
                "selected_rows": [0, 1, 2],
                "selected_cell_count": 48,
                "sampling_geometry_admitted": True,
                "supplied_block_corners_tl_tr_br_bl": copy.deepcopy(
                    dict(partial_blocks)
                ),
            },
            "illumination": {
                "sample_count": 48,
                "minimum_lstar": 50.0,
                "minimum_required_lstar": 25.0,
                "side_specific_white_normalization_required": True,
                "raw_cross_side_rgb_equality_gate": False,
                "passed": True,
            },
            "evidence_scope": {
                "mode": pack.PARTIAL_MODE,
                "formal_full_panel_evidence": False,
                "full_panel_geometry_evaluated": False,
                "profile_following_decision_earned": False,
                "outside_roi": "NOT_EVALUATED_OUTSIDE_SELECTED_ROI",
            },
        }

    monkeypatch.setattr(pack, "_evaluate_partial_capture", evaluate)
    return capture


def test_partial_four_frame_bundle_stays_partial_and_profile_code_comparable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    action = tmp_path / "source-action.json"
    action.write_bytes(b"{}")
    capture = _install_partial_success_seams(monkeypatch)

    assert pack.acquire_partial_one(
        slot=pack.WHITE_SLOT,
        output_root=tmp_path,
        action_result_path=action,
        mount_id=MOUNT,
        capture_function=capture,
    )["acquired"]
    assert pack.admit_partial_one(
        slot=pack.WHITE_SLOT,
        attempt=1,
        output_root=tmp_path,
        partial_blocks=PARTIAL_BLOCKS,
    )["accepted"]
    for attempt in range(1, 4):
        assert pack.acquire_partial_one(
            slot=pack.T3_SLOT,
            output_root=tmp_path,
            action_result_path=action,
            mount_id=MOUNT,
            capture_function=capture,
        )["acquired"]
        assert pack.admit_partial_one(
            slot=pack.T3_SLOT,
            attempt=attempt,
            output_root=tmp_path,
            partial_blocks=PARTIAL_BLOCKS,
        )["accepted"]

    output = tmp_path / "partial-bundle.json"
    bundle = pack.seal_partial_bundle(output_root=tmp_path, output_path=output)
    assert bundle["kind"] == pack.PARTIAL_BUNDLE_KIND
    assert bundle["mode"] == pack.PARTIAL_MODE
    assert bundle["selected_cell_count_per_frame"] == 48
    assert bundle["replicates_per_code_per_controller_per_frame"] == 3
    assert bundle["profile_code_pair_comparison_available"] is True
    assert bundle["outside_roi"] == "NOT_EVALUATED_OUTSIDE_SELECTED_ROI"
    assert bundle["formal_full_panel_evidence"] is False
    assert bundle["full_panel_geometry_evaluated"] is False
    assert bundle["profile_following_decision_earned"] is False
    assert bundle["w4_post_white_full_screen_seal_earned"] is False
    assert bundle["partial_roi_may_be_promoted_to_full_panel_evidence"] is False
    assert pack.validate_partial_bundle(output) == bundle


def test_invalid_partial_blocks_consume_admission_and_never_expand_or_retry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    action = tmp_path / "source-action.json"
    action.write_bytes(b"{}")
    capture = _install_partial_success_seams(monkeypatch)
    assert pack.acquire_partial_one(
        slot=pack.WHITE_SLOT,
        output_root=tmp_path,
        action_result_path=action,
        mount_id=MOUNT,
        capture_function=capture,
    )["acquired"]
    rejected = pack.admit_partial_one(
        slot=pack.WHITE_SLOT,
        attempt=1,
        output_root=tmp_path,
        partial_blocks='{"CS1":[[1,1],[2,1],[2,2],[1,2]]}',
    )
    assert rejected["accepted"] is False
    assert rejected["camera_invocations_during_admit"] == 0
    assert rejected["formal_full_panel_evidence"] is False
    assert rejected["outside_roi"] == "NOT_EVALUATED_OUTSIDE_SELECTED_ROI"
    with pytest.raises(pack.T3CameraCapturePackError, match="terminal result"):
        pack.admit_partial_one(
            slot=pack.WHITE_SLOT,
            attempt=1,
            output_root=tmp_path,
            partial_blocks=PARTIAL_BLOCKS,
        )


def test_partial_block_drift_enforces_both_rms_and_maximum() -> None:
    base = {
        "supplied_block_corners_tl_tr_br_bl": json.loads(PARTIAL_BLOCKS)
    }
    moved = copy.deepcopy(base)
    moved["supplied_block_corners_tl_tr_br_bl"]["CS2"][2][0] += 16.0

    with pytest.raises(pack.T3CameraCapturePackError, match="block drift rejected"):
        pack._partial_corresponding_block_drift(base, moved)  # noqa: SLF001


def test_four_successes_seal_distinct_same_settings_hash_bound_bundle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    action = tmp_path / "source-action.json"
    action.write_bytes(b"{}")
    capture = _install_success_seams(monkeypatch)

    white_acquisition = pack.acquire_one(
        slot=pack.WHITE_SLOT,
        output_root=tmp_path,
        action_result_path=action,
        mount_id=MOUNT,
        capture_function=capture,
    )
    assert white_acquisition["acquired"] is True
    assert not list((tmp_path / "results").glob("*.result.json"))
    assert "panel_corners_tl_tr_br_bl" not in white_acquisition
    white = pack.admit_one(
        slot=pack.WHITE_SLOT,
        attempt=1,
        output_root=tmp_path,
        panel_corners=CORNERS,
    )
    assert white["accepted"] is True
    frame_corners = [
        "501,400;3501,500;3401,2600;601,2500",
        "502,400;3502,500;3402,2600;602,2500",
        "503,400;3503,500;3403,2600;603,2500",
    ]
    frames = []
    for attempt, corners in enumerate(frame_corners, start=1):
        acquisition = pack.acquire_one(
            slot=pack.T3_SLOT,
            output_root=tmp_path,
            action_result_path=action,
            mount_id=MOUNT,
            capture_function=capture,
        )
        assert acquisition["acquired"] is True
        frames.append(
            pack.admit_one(
                slot=pack.T3_SLOT,
                attempt=attempt,
                output_root=tmp_path,
                panel_corners=corners,
            )
        )
    assert all(item["accepted"] for item in frames)

    output = tmp_path / "sealed.json"
    bundle = pack.seal_bundle(output_root=tmp_path, output_path=output)
    assert bundle["accepted_counts"] == {
        pack.WHITE_SLOT: 1,
        pack.T3_SLOT: 3,
    }
    assert bundle["attempt_counts"] == {
        pack.WHITE_SLOT: 1,
        pack.T3_SLOT: 3,
    }
    assert bundle["same_exact_camera_mount_settings_and_dimensions"] is True
    assert bundle["per_frame_panel_corners_recorded_independently"] is True
    assert len(bundle["pairwise_cross_capture_geometry"]) == 6
    assert len({item["photo_sha256"] for item in bundle["t3_frames"]}) == 3
    assert pack.validate_bundle(output) == bundle


def test_changed_camera_alignment_rejects_t3_and_preserves_white(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    action = tmp_path / "source-action.json"
    action.write_bytes(b"{}")
    capture = _install_success_seams(monkeypatch, t3_alignment_change=True)
    assert pack.acquire_one(
        slot=pack.WHITE_SLOT,
        output_root=tmp_path,
        action_result_path=action,
        mount_id=MOUNT,
        capture_function=capture,
    )["acquired"]
    assert pack.admit_one(
        slot=pack.WHITE_SLOT,
        attempt=1,
        output_root=tmp_path,
        panel_corners=CORNERS,
    )["accepted"]
    assert pack.acquire_one(
        slot=pack.T3_SLOT,
        output_root=tmp_path,
        action_result_path=action,
        mount_id=MOUNT,
        capture_function=capture,
    )["acquired"]
    rejected = pack.admit_one(
        slot=pack.T3_SLOT,
        attempt=1,
        output_root=tmp_path,
        panel_corners=CORNERS,
    )
    assert rejected["accepted"] is False
    assert "differ from white" in rejected["error"]["message"]
    assert len(pack._accepted_results(tmp_path, pack.WHITE_SLOT)) == 1  # noqa: SLF001
    assert len(pack._accepted_results(tmp_path, pack.T3_SLOT)) == 0  # noqa: SLF001


def test_cli_exposes_no_camera_identity_or_setting_override() -> None:
    parser = pack._parser()  # noqa: SLF001
    acquire_parser = next(
        action.choices["acquire"]
        for action in parser._actions  # noqa: SLF001
        if getattr(action, "choices", None) and "acquire" in action.choices
    )
    option_strings = {
        option
        for action in acquire_parser._actions  # noqa: SLF001
        for option in action.option_strings
    }
    assert {
        "--camera-index",
        "--camera-instance-id",
        "--camera-id",
        "--exposure",
        "--width",
        "--height",
        "--fps",
        "--focus",
        "--white-balance-temperature",
        "--panel-corners",
    }.isdisjoint(option_strings)

    admit_parser = next(
        action.choices["admit"]
        for action in parser._actions  # noqa: SLF001
        if getattr(action, "choices", None) and "admit" in action.choices
    )
    admit_options = {
        option
        for action in admit_parser._actions  # noqa: SLF001
        for option in action.option_strings
    }
    assert "--panel-corners" in admit_options
    assert "--action-result" not in admit_options
    assert "--mount-id" not in admit_options


def test_legacy_capture_fails_before_any_write_or_camera(
    tmp_path: Path,
) -> None:
    calls = 0

    def forbidden_camera(**_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("legacy capture reached camera")

    with pytest.raises(
        pack.T3CameraCapturePackError, match="legacy capture is disabled"
    ):
        pack.capture_one(
            slot=pack.WHITE_SLOT,
            output_root=tmp_path,
            action_result_path=tmp_path / "does-not-matter.json",
            mount_id=MOUNT,
            panel_corners=CORNERS,
            capture_function=forbidden_camera,
        )
    assert calls == 0
    assert not list(tmp_path.iterdir())


def test_invalid_admission_is_terminal_and_never_reopens_camera(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    action = tmp_path / "source-action.json"
    action.write_bytes(b"{}")
    capture = _install_success_seams(monkeypatch)
    acquisition = pack.acquire_one(
        slot=pack.WHITE_SLOT,
        output_root=tmp_path,
        action_result_path=action,
        mount_id=MOUNT,
        capture_function=capture,
    )
    assert acquisition["acquired"] is True
    rejected = pack.admit_one(
        slot=pack.WHITE_SLOT,
        attempt=1,
        output_root=tmp_path,
        panel_corners="1,1;10,1;10,10;1,10",
    )
    assert rejected["accepted"] is False
    assert rejected["camera_invocations_during_admit"] == 0
    assert (
        tmp_path / "admissions" / "w3-white-reference-attempt-01.admission.json"
    ).is_file()
    with pytest.raises(pack.T3CameraCapturePackError, match="terminal result"):
        pack.admit_one(
            slot=pack.WHITE_SLOT,
            attempt=1,
            output_root=tmp_path,
            panel_corners=CORNERS,
        )
    assert len(list((tmp_path / "claims").glob("*.claim.json"))) == 1


def test_admit_resumes_same_claim_after_result_write_crash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    action = tmp_path / "source-action.json"
    action.write_bytes(b"{}")
    capture = _install_success_seams(monkeypatch)
    assert pack.acquire_one(
        slot=pack.WHITE_SLOT,
        output_root=tmp_path,
        action_result_path=action,
        mount_id=MOUNT,
        capture_function=capture,
    )["acquired"]

    original_write = pack._write_exclusive  # noqa: SLF001
    failed = False

    def crash_before_result(path, value):
        nonlocal failed
        if not failed and Path(path).name.endswith(".result.json"):
            failed = True
            raise OSError("synthetic crash before result persistence")
        original_write(path, value)

    monkeypatch.setattr(pack, "_write_exclusive", crash_before_result)
    with pytest.raises(OSError, match="synthetic crash"):
        pack.admit_one(
            slot=pack.WHITE_SLOT,
            attempt=1,
            output_root=tmp_path,
            panel_corners=CORNERS,
        )
    assert list((tmp_path / "admissions").glob("*.admission.json"))
    assert not list((tmp_path / "results").glob("*.result.json"))
    resumed = pack.admit_one(
        slot=pack.WHITE_SLOT,
        attempt=1,
        output_root=tmp_path,
        panel_corners=CORNERS,
    )
    assert resumed["accepted"] is True
    assert resumed["camera_invocations_during_admit"] == 0
    assert len(list((tmp_path / "claims").glob("*.claim.json"))) == 1


def test_claim_only_crash_blocks_another_camera_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    action = tmp_path / "source-action.json"
    action.write_bytes(b"{}")
    monkeypatch.setattr(
        pack,
        "_validate_action_source",
        lambda slot, path: {**pack._expected_action_identity(slot), "path": str(path)},
    )
    contract = pack.ensure_contract(output_root=tmp_path, mount_id=MOUNT)
    pack._claim_attempt(  # noqa: SLF001
        output_root=tmp_path,
        slot=pack.WHITE_SLOT,
        contract=contract,
        action_path=action,
        action_payload=action.read_bytes(),
    )
    calls = 0

    def forbidden_camera(**_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("camera reopened after unknown claim")

    with pytest.raises(pack.T3CameraCapturePackError, match="claim-only state"):
        pack.acquire_one(
            slot=pack.WHITE_SLOT,
            output_root=tmp_path,
            action_result_path=action,
            mount_id=MOUNT,
            capture_function=forbidden_camera,
        )
    assert calls == 0
    assert len(list((tmp_path / "claims").glob("*.claim.json"))) == 1


def test_photo_tamper_after_acquire_is_rejected_offline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    action = tmp_path / "source-action.json"
    action.write_bytes(b"{}")
    capture = _install_success_seams(monkeypatch)
    assert pack.acquire_one(
        slot=pack.WHITE_SLOT,
        output_root=tmp_path,
        action_result_path=action,
        mount_id=MOUNT,
        capture_function=capture,
    )["acquired"]
    photo = tmp_path / "evidence" / "w3-white-reference-attempt-01" / "camera.jpg"
    photo.write_bytes(b"tampered-after-acquisition")
    rejected = pack.admit_one(
        slot=pack.WHITE_SLOT,
        attempt=1,
        output_root=tmp_path,
        panel_corners=CORNERS,
    )
    assert rejected["accepted"] is False
    assert "capture file binding differs" in rejected["error"]["message"]


def test_bundle_rejects_successful_acquisition_without_admission(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    action = tmp_path / "source-action.json"
    action.write_bytes(b"{}")
    capture = _install_success_seams(monkeypatch)
    assert pack.acquire_one(
        slot=pack.WHITE_SLOT,
        output_root=tmp_path,
        action_result_path=action,
        mount_id=MOUNT,
        capture_function=capture,
    )["acquired"]
    with pytest.raises(pack.T3CameraCapturePackError, match="not terminal"):
        pack.build_bundle(output_root=tmp_path)


def test_setup_view_is_two_attempt_nonformal_ledger_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    action = tmp_path / "source-action.json"
    action.write_bytes(b"{}")
    capture = _install_success_seams(monkeypatch)
    first = pack.setup_view_once(
        output_root=tmp_path,
        action_result_path=action,
        mount_id=MOUNT,
        capture_function=capture,
    )
    second = pack.setup_view_once(
        output_root=tmp_path,
        action_result_path=action,
        mount_id=MOUNT,
        capture_function=capture,
    )
    assert first["captured"] is second["captured"] is True
    assert first["formal_evidence"] is second["formal_evidence"] is False
    assert first["eligible_for_core_bundle"] is False
    assert first["panel_corners_accepted_or_exported"] is False
    assert not (tmp_path / "capture-contract.json").exists()
    assert not (tmp_path / "claims").exists()
    assert len(list((tmp_path / "setup-claims").glob("*.claim.json"))) == 2
    with pytest.raises(pack.T3CameraCapturePackError, match="budget 2 is exhausted"):
        pack.setup_view_once(
            output_root=tmp_path,
            action_result_path=action,
            mount_id=MOUNT,
            capture_function=capture,
        )

    parser = pack._parser()  # noqa: SLF001
    setup_parser = next(
        item.choices["setup-view"]
        for item in parser._actions  # noqa: SLF001
        if getattr(item, "choices", None) and "setup-view" in item.choices
    )
    setup_options = {
        option
        for item in setup_parser._actions  # noqa: SLF001
        for option in item.option_strings
    }
    assert "--panel-corners" not in setup_options
    assert "--camera-index" not in setup_options
