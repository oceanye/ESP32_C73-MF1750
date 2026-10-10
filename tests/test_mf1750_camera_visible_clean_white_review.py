from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
from typing import Any

from PIL import Image
import pytest

from tools import mf1750_camera_capture_evidence as camera
from tools import mf1750_camera_visible_clean_white_review as review
from tools.mf17506_stage23 import relay_exact_bound_switch as relay


def _jpeg() -> bytes:
    output = BytesIO()
    Image.new("RGB", (96, 64), (211, 216, 224)).save(output, format="JPEG", quality=92)
    return output.getvalue()


def _authenticated_device() -> dict[str, Any]:
    return {
        "enumerator": camera.DIRECTSHOW_DEVICE_ENUMERATOR,
        "friendly_name": camera.TARGET_CAMERA_FRIENDLY_NAME,
        "alternative_name": (
            r"@device_pnp_\\?\usb#vid_32e4&pid_4801&mi_00#"
            r"6&22675d4e&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"
        ),
        "pnp_instance_id": r"USB\VID_32E4&PID_4801&MI_00\6&22675D4E&0&0000",
        "directshow_index": 0,
        "usb_vid": "32E4",
        "usb_pid": "4801",
    }


def _write_action(path: Path) -> dict[str, Any]:
    action_id = "1" * 64
    descriptor_id = "2" * 64
    root = camera._seal(
        {
            "schema_version": 1,
            "kind": "synthetic-generic-factory-white-result",
            "created_at": "2026-09-01T10:00:00+08:00",
            "outcome": "complete_pass",
            "boot_nonce": "fixture-boot-nonce",
            "firmware_sha256": "3" * 64,
            "visible_refreshes": 1,
            "action": {
                "action_id": action_id,
                "descriptor_id": descriptor_id,
                "ordinal": 1,
                "role": camera.FACTORY_OTP_WHITE_ACTION_ROLE,
                "frame_sha256": "4" * 64,
            },
            "terminal_report": {
                "terminal_state": "COMPLETE",
                "result": True,
                "valid": True,
                "campaign_id": "GENERIC_NON_W11_FACTORY_WHITE_CAMPAIGN",
                "test_id": "GENERIC-NON-W11-FACTORY-WHITE-TEST",
                "contract_id": "5" * 64,
                "build_tag": "GENERIC_NON_W11_FACTORY_WHITE_BUILD",
                "boot_nonce": "fixture-boot-nonce",
                "action_id": action_id,
                "descriptor_id": descriptor_id,
                "ordinal": 1,
                "role": camera.FACTORY_OTP_WHITE_ACTION_ROLE,
            },
        }
    )
    path.write_text(
        json.dumps(root, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return root


def _write_capture(action_path: Path, photo_path: Path, sidecar_path: Path) -> None:
    requested = {
        "autofocus": 0,
        "focus": 79,
        "auto_exposure": 0.25,
        "exposure": -5,
        "auto_white_balance": 0,
        "white_balance_temperature": 6500,
    }
    effective = camera._normalise_requested_settings(requested)
    set_results = {
        field: True for field, value in effective.items() if value is not None
    }
    camera.capture_locked_retained(
        action_result_path=action_path,
        photo_path=photo_path,
        sidecar_path=sidecar_path,
        camera_id=camera.TARGET_CAMERA_LOGICAL_ID,
        camera_instance_id=_authenticated_device()["pnp_instance_id"],
        mount_id="generic-fixed-camera-mount",
        coverage_scope=camera.COVERAGE_FULL,
        requested_settings=requested,
        warmup_frames=3,
        limitations=("retained fixture; no hardware accessed",),
        capture_backend=lambda *_args: (
            _jpeg(),
            {
                "backend": "DSHOW",
                "authenticated_device": _authenticated_device(),
                "set_results": set_results,
                "effective_settings_before_frame": effective,
                "effective_settings_after_frame": dict(effective),
                "warmup_frames_completed": 3,
                "read_failures": 0,
                "frame_retrieved_at": "2026-09-01T10:03:00+08:00",
                "frame_retrieved_at_utc": "2026-09-01T02:03:00+00:00",
            },
        ),
        _device_resolver=_authenticated_device,
    )


def _relay_receipt(*, switched_at: str = "2026-09-01T10:02:00+08:00") -> dict[str, Any]:
    unsigned = {
        "schema_version": relay.SCHEMA_VERSION,
        "kind": relay.KIND,
        "switched_at": switched_at,
        "rebind": {},
        "expected_identity": {},
        "channel": 1,
        "contact_path": relay.CONTACT_PATH,
        "target_state": "OFF",
        "commanded_state": "OFF",
        "target_gate_passed": True,
        "off_gate_passed": True,
        "electrical_state_proven": False,
        "contact_switch_performed": True,
        "feedback_command_count": 1,
        "independent_query_count": 1,
        "automatic_retry_performed": False,
        "automatic_recovery_performed": False,
        "authority": {},
        "software_binding": {},
        "output_write_contract": relay.OUTPUT_WRITE_CONTRACT,
    }
    root = dict(unsigned)
    root["integrity"] = {
        "algorithm": "sha256",
        "canonical_sha256": review._sha256(relay.canonical_json_bytes(unsigned)),
        "scope": relay.INTEGRITY_SCOPE,
    }
    return root


def _write_relay(path: Path, **kwargs: Any) -> dict[str, Any]:
    root = _relay_receipt(**kwargs)
    relay.validate_receipt(root)
    path.write_bytes(relay.canonical_json_bytes(root) + b"\n")
    return root


def _fixture(tmp_path: Path) -> dict[str, Path]:
    action = tmp_path / "factory-white-action.json"
    photo = tmp_path / "retained-white.jpg"
    sidecar = tmp_path / "retained-white.capture.json"
    relay_off = tmp_path / "relay-post-action-off.json"
    output = tmp_path / "retained-white.clean-white-review.json"
    _write_action(action)
    _write_capture(action, photo, sidecar)
    _write_relay(relay_off)
    return {
        "action": action,
        "photo": photo,
        "sidecar": sidecar,
        "relay": relay_off,
        "output": output,
    }


def _create(paths: dict[str, Path], **updates: Any) -> dict[str, Any]:
    arguments = {
        "action_result_path": paths["action"],
        "capture_sidecar_path": paths["sidecar"],
        "photo_path": paths["photo"],
        "relay_off_receipt_path": paths["relay"],
        "output_path": paths["output"],
        "reviewed_at": "2026-09-01T10:04:00+08:00",
        "reviewer": "offline-test-reviewer",
        "method": "visual inspection of an already-retained JPEG",
        "confidence": "MEDIUM",
        "camera_visible_white_field": True,
        "obvious_colour_blocks_or_blotches_visible": False,
        "obvious_gross_horizontal_stripes_visible": False,
        "obvious_gross_vertical_stripes_visible": False,
        "obvious_center_seam_anomaly_visible": False,
        "limitations_observed": ("uneven fixture illumination",),
    }
    arguments.update(updates)
    return review.create_review(**arguments)


def test_generic_non_w11_pass_preserves_all_qualification_limits(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)

    result = _create(paths)

    assert result["campaign_id"] == "GENERIC_NON_W11_FACTORY_WHITE_CAMPAIGN"
    assert result["classification"] == {
        "state": review.CLASSIFICATION_STATE,
        "verdict": "PASS",
        "camera_visible_clean_white_review_passed": True,
        "pass_scope": review.PASS_SCOPE,
        "reason": (
            "the full active area is visible as a camera-relative white field with no "
            "obvious colour blocks/blotches, gross horizontal/vertical stripes, or "
            "obvious centre-seam anomaly in this retained frame"
        ),
        **review.QUALIFICATION_LIMITS,
    }
    assert (
        result["capture_binding"]["retained_action_to_capture_continuity_proven"]
        is False
    )
    assert result["relay_post_action_off"]["commanded_state"] == "OFF"
    assert result["relay_post_action_off"]["electrical_state_proven"] is False
    assert result["offline_execution"] == review.OFFLINE_EXECUTION
    assert review.validate_review(paths["output"]) == result


def test_output_is_o_excl_and_existing_bytes_are_preserved(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    first = _create(paths)
    before = paths["output"].read_bytes()

    with pytest.raises(
        review.CameraVisibleCleanWhiteReviewError, match="refusing to overwrite"
    ):
        _create(paths)

    assert paths["output"].read_bytes() == before
    assert review.validate_review(paths["output"]) == first


@pytest.mark.parametrize(
    "updates",
    (
        {"camera_visible_white_field": False},
        {"obvious_colour_blocks_or_blotches_visible": True},
        {"obvious_gross_horizontal_stripes_visible": True},
        {"obvious_gross_vertical_stripes_visible": True},
        {"obvious_center_seam_anomaly_visible": True},
    ),
)
def test_any_scoped_visible_defect_prevents_pass(
    tmp_path: Path, updates: dict[str, Any]
) -> None:
    paths = _fixture(tmp_path)

    result = _create(paths, **updates)

    assert result["classification"]["verdict"] == "FAIL"
    assert result["classification"]["camera_visible_clean_white_review_passed"] is False


def test_low_confidence_without_visible_defect_is_review_not_pass(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)

    result = _create(paths, confidence="LOW")

    assert result["classification"]["verdict"] == "REVIEW"
    assert result["classification"]["camera_visible_clean_white_review_passed"] is False


def test_provided_action_must_be_the_exact_capture_bound_path(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    copied = tmp_path / "identical-but-not-bound-action.json"
    copied.write_bytes(paths["action"].read_bytes())

    with pytest.raises(
        review.CameraVisibleCleanWhiteReviewError, match="not the capture-bound action"
    ):
        _create(paths, action_result_path=copied)

    assert not paths["output"].exists()


def test_photo_tamper_is_rejected_by_capture_deep_replay(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    paths["photo"].write_bytes(paths["photo"].read_bytes() + b"tamper")

    with pytest.raises(
        review.CameraVisibleCleanWhiteReviewError,
        match="capture evidence validation failed",
    ):
        _create(paths)

    assert not paths["output"].exists()


def test_relay_off_must_precede_the_retained_capture(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    paths["relay"].unlink()
    _write_relay(paths["relay"], switched_at="2026-09-01T10:05:00+08:00")

    with pytest.raises(review.CameraVisibleCleanWhiteReviewError, match="chronology"):
        _create(paths)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("camera_relative_only", False),
        ("absolute_white_point_proven", True),
        ("spatial_uniformity_proven", True),
        ("qualified_level_count", 1),
        ("retained_action_to_capture_continuity_proven", True),
    ),
)
def test_resealed_qualification_escalation_fails_closed(
    tmp_path: Path, field: str, value: Any
) -> None:
    paths = _fixture(tmp_path)
    _create(paths)
    root = json.loads(paths["output"].read_text(encoding="utf-8"))
    root.pop("integrity")
    root["classification"][field] = value
    paths["output"].write_bytes(
        review._canonical_json_bytes(review._seal(root)) + b"\n"
    )

    with pytest.raises(
        review.CameraVisibleCleanWhiteReviewError,
        match="qualification fields differ",
    ):
        review.validate_review(paths["output"])


def test_source_path_escape_fails_closed_even_when_resealed(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    _create(paths)
    root = json.loads(paths["output"].read_text(encoding="utf-8"))
    root.pop("integrity")
    root["source_evidence"]["photo"]["path"] = "../retained-white.jpg"
    paths["output"].write_bytes(
        review._canonical_json_bytes(review._seal(root)) + b"\n"
    )

    with pytest.raises(
        review.CameraVisibleCleanWhiteReviewError, match="safe relative POSIX path"
    ):
        review.validate_review(paths["output"])
