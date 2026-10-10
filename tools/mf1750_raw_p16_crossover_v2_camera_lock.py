#!/usr/bin/env python3
"""Validate the exact offline camera contract for fresh RAW-P16 V2 evidence.

This module deliberately does not replace the frozen exposure=-6 validator used
by the V1 evidence chain.  Fresh V2 captures must use the same 48MP DirectShow
device, fixed mount, 4000x3000 MJPG mode, focus, white balance, and manual
controls, with the single explicit change ``exposure=-3``.

Importing or calling this module performs no camera or device I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tools import mf1750_camera_capture_evidence as camera
from tools import mf1750_raw_p16_retained_atlas_photo_analyzer as frozen


CAMERA_CONTRACT_REVISION = "raw-p16-crossover-fresh-v2-48mp-exposure-minus-3"
EXPECTED_EXPOSURE = -3.0
EXPECTED_CAMERA_PROFILE: dict[str, Any] = {
    **frozen.EXPECTED_CAMERA_PROFILE,
    "exposure": EXPECTED_EXPOSURE,
}


class V2CameraLockError(RuntimeError):
    """Raised when a capture differs from the exact fresh-V2 camera lock."""


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    try:
        return frozen._mapping(value, label=label)  # noqa: SLF001
    except frozen.RawP16PhotoAnalysisError as error:
        raise V2CameraLockError(str(error)) from error


def _same_number(observed: Any, expected: float, *, label: str) -> None:
    try:
        frozen._same_number(observed, expected, label=label)  # noqa: SLF001
    except frozen.RawP16PhotoAnalysisError as error:
        raise V2CameraLockError(str(error)) from error


def _number(observed: Any, *, label: str) -> float:
    try:
        return frozen._number(observed, label=label)  # noqa: SLF001
    except frozen.RawP16PhotoAnalysisError as error:
        raise V2CameraLockError(str(error)) from error


def validate_fixed_capture(capture_root: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact V2 camera lock or reject the capture fail-closed."""

    if (
        capture_root.get("schema_version") != frozen.EXPECTED_CAPTURE_SCHEMA
        or capture_root.get("kind") != camera.KIND
    ):
        raise V2CameraLockError(
            "capture must be current schema-v2 formal 48MP evidence"
        )
    if capture_root.get("capture_binding") != frozen.EXPECTED_CAPTURE_BINDING:
        raise V2CameraLockError(
            "capture must be locked-retained evidence for the displayed atlas"
        )

    coverage = _mapping(capture_root.get("coverage"), label="capture.coverage")
    if (
        coverage.get("scope") != camera.COVERAGE_FULL
        or coverage.get("full_panel_visible") is not True
        or coverage.get("full_panel_uncropped") is not True
    ):
        raise V2CameraLockError(
            "capture must declare the complete, visible, uncropped panel"
        )
    mount_id = coverage.get("mount_id")
    if not isinstance(mount_id, str) or not mount_id:
        raise V2CameraLockError("capture mount_id is missing")

    record = _mapping(capture_root.get("camera"), label="capture.camera")
    if record.get("camera_id") != frozen.TARGET_CAMERA_ID:
        raise V2CameraLockError(
            "capture is not the MF1750 48MP VID_32E4:PID_4801 camera"
        )
    instance = record.get("instance_id")
    if not isinstance(instance, str):
        raise V2CameraLockError("capture camera instance is missing")
    folded_instance = instance.casefold()
    if (
        frozen.TARGET_USB_TOKEN not in folded_instance
        or frozen.EXCLUDED_USB_TOKEN in folded_instance
    ):
        raise V2CameraLockError(
            "capture camera instance is not the allowed 48MP USB device"
        )
    if str(record.get("backend", "")).casefold() != "dshow":
        raise V2CameraLockError("capture backend must be DirectShow")

    requested = _mapping(
        record.get("requested_settings"), label="camera.requested_settings"
    )
    for field, expected in EXPECTED_CAMERA_PROFILE.items():
        observed = requested.get(field)
        if isinstance(expected, str):
            if observed != expected:
                raise V2CameraLockError(
                    f"requested {field} differs from locked value {expected}"
                )
        else:
            _same_number(observed, float(expected), label=f"requested.{field}")

    before = dict(
        _mapping(
            record.get("effective_settings_before_frame"),
            label="camera.effective_settings_before_frame",
        )
    )
    after = dict(
        _mapping(
            record.get("effective_settings_after_frame"),
            label="camera.effective_settings_after_frame",
        )
    )
    if before != after:
        raise V2CameraLockError(
            "effective camera settings changed around the formal frame"
        )
    for field in (
        "fourcc",
        "frame_width",
        "frame_height",
        "focus",
        "exposure",
        "white_balance_temperature",
    ):
        expected = EXPECTED_CAMERA_PROFILE[field]
        observed = before.get(field)
        if isinstance(expected, str):
            if observed != expected:
                raise V2CameraLockError(f"effective {field} differs")
        else:
            _same_number(observed, float(expected), label=f"effective.{field}")
    _same_number(before.get("fps"), 15.000015000015, label="effective.fps")
    for field, accepted in frozen.ACCEPTED_DSHOW_MANUAL_READBACK.items():
        observed = _number(before.get(field), label=f"effective.{field}")
        if observed not in accepted:
            raise V2CameraLockError(
                f"effective {field} is not an accepted DirectShow manual encoding"
            )

    set_results = _mapping(record.get("set_results"), label="camera.set_results")
    required_writes = {field for field, value in requested.items() if value is not None}
    if not required_writes.issubset(set_results) or any(
        set_results.get(field) is not True for field in required_writes
    ):
        raise V2CameraLockError("one or more locked camera writes failed")
    if record.get("read_failures") != 0:
        raise V2CameraLockError("formal capture has camera read failures")
    warmup = record.get("warmup_frames_requested")
    if (
        type(warmup) is not int
        or warmup < 5
        or record.get("warmup_frames_completed") != warmup
    ):
        raise V2CameraLockError(
            "formal capture requires at least five completed warmup frames"
        )

    return {
        "camera_contract_revision": CAMERA_CONTRACT_REVISION,
        "camera_id": frozen.TARGET_CAMERA_ID,
        "usb_vid": "32E4",
        "usb_pid": "4801",
        "excluded_camera_vid_pid": "1BCF:0B15",
        "instance_id": instance,
        "backend": "DSHOW",
        "mount_id": mount_id,
        "requested_settings": dict(requested),
        "effective_settings": before,
        "effective_readback_equal": True,
        "write_results_all_true": True,
        "fixed_exposure_boundary": EXPECTED_EXPOSURE,
    }
