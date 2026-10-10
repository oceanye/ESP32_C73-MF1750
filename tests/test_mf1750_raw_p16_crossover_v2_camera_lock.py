from __future__ import annotations

import copy

import pytest

from tools import mf1750_camera_capture_evidence as camera
from tools import mf1750_raw_p16_crossover_v2_camera_lock as lock
from tools import mf1750_raw_p16_retained_atlas_photo_analyzer as frozen


def _capture(*, exposure: float = -3.0) -> dict:
    requested = {
        "fourcc": "MJPG",
        "frame_width": 4000,
        "frame_height": 3000,
        "fps": 15.0,
        "autofocus": 0.0,
        "focus": 79.0,
        "auto_exposure": 0.25,
        "exposure": exposure,
        "auto_white_balance": 0.0,
        "white_balance_temperature": 4600.0,
    }
    effective = {
        "fourcc": "MJPG",
        "frame_width": 4000,
        "frame_height": 3000,
        "fps": 15.000015000015,
        "autofocus": 2,
        "focus": 79,
        "auto_exposure": -1,
        "exposure": exposure,
        "auto_white_balance": 0,
        "white_balance_temperature": 4600,
    }
    return {
        "schema_version": camera.SCHEMA_VERSION,
        "kind": camera.KIND,
        "capture_binding": camera.BINDING_LOCKED_RETAINED,
        "coverage": {
            "scope": camera.COVERAGE_FULL,
            "full_panel_visible": True,
            "full_panel_uncropped": True,
            "mount_id": "mf1750-48mp-fixed-20260828",
        },
        "camera": {
            "camera_id": camera.TARGET_CAMERA_FRIENDLY_NAME,
            "instance_id": (
                r"@device_pnp_\\?\usb#vid_32e4&pid_4801&mi_00#fixed\global"
            ),
            "backend": "DSHOW",
            "requested_settings": requested,
            "effective_settings_before_frame": effective,
            "effective_settings_after_frame": copy.deepcopy(effective),
            "set_results": {field: True for field in requested},
            "read_failures": 0,
            "warmup_frames_requested": 10,
            "warmup_frames_completed": 10,
        },
    }


def test_exact_exposure_minus_three_camera_lock_is_accepted() -> None:
    result = lock.validate_fixed_capture(_capture())

    assert result["camera_contract_revision"] == lock.CAMERA_CONTRACT_REVISION
    assert result["fixed_exposure_boundary"] == -3.0
    assert result["requested_settings"]["exposure"] == -3.0
    assert result["effective_settings"]["exposure"] == -3.0


@pytest.mark.parametrize("exposure", [-6.0, -4.0, -2.0])
def test_other_exposures_are_rejected(exposure: float) -> None:
    with pytest.raises(lock.V2CameraLockError, match="requested.exposure differs"):
        lock.validate_fixed_capture(_capture(exposure=exposure))


def test_wrong_device_and_changed_effective_readback_are_rejected() -> None:
    wrong = _capture()
    wrong["camera"]["instance_id"] = "usb#vid_1bcf&pid_0b15#binocular"
    with pytest.raises(lock.V2CameraLockError, match="allowed 48MP USB device"):
        lock.validate_fixed_capture(wrong)

    changed = _capture()
    changed["camera"]["effective_settings_after_frame"]["exposure"] = -4
    with pytest.raises(lock.V2CameraLockError, match="changed around"):
        lock.validate_fixed_capture(changed)


def test_frozen_v1_contract_remains_exposure_minus_six() -> None:
    with pytest.raises(
        frozen.RawP16PhotoAnalysisError, match="requested.exposure differs"
    ):
        frozen._validate_fixed_capture(_capture(exposure=-3.0))  # noqa: SLF001

    result = frozen._validate_fixed_capture(_capture(exposure=-6.0))  # noqa: SLF001
    assert result["fixed_exposure_boundary"] == -6.0
