from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from tools import mf1750_camera_capture_evidence as camera
from tools import mf1750_camera_video_capture_evidence as video


def _action(path: Path) -> dict[str, object]:
    root: dict[str, object] = {
        "schema_version": 1,
        "kind": "test-action-result",
        "created_at": "2026-08-28T10:00:25+08:00",
        "outcome": "complete_pass",
        "boot_nonce": "batch3-boot",
        "firmware_sha256": "5" * 64,
        "visible_refreshes": 1,
        "action": {
            "action_id": "1" * 64,
            "descriptor_id": "2" * 64,
            "ordinal": 1,
            "role": "ACTIVE_R20_ROI_A",
            "frame_sha256": "4" * 64,
        },
        "terminal_report": {
            "terminal_state": "COMPLETE",
            "result": True,
            "valid": True,
            "campaign_id": "BATCH3",
            "test_id": "TRUE-R20",
            "contract_id": "3" * 64,
            "build_tag": "TRUE-R20-BUILD",
            "boot_nonce": "batch3-boot",
            "action_id": "1" * 64,
            "descriptor_id": "2" * 64,
            "ordinal": 1,
            "role": "ACTIVE_R20_ROI_A",
        },
    }
    sealed = camera._seal(root)  # noqa: SLF001
    path.write_text(json.dumps(sealed, sort_keys=True), encoding="utf-8")
    return sealed


def _manifest(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, object]]:
    action_path = tmp_path / "action.json"
    action = _action(action_path)
    video_path = tmp_path / "refresh.mkv"
    video_payload = b"offline-refresh-video-fixture"
    video_path.write_bytes(video_payload)
    settings = {
        "autofocus": 0.0,
        "auto_exposure": 0.25,
        "auto_white_balance": 0.0,
        "focus": 12.0,
        "exposure": -6.0,
        "white_balance_temperature": 4600.0,
    }
    dshow_effective = dict(settings)
    dshow_effective["autofocus"] = 2.0
    dshow_effective["auto_exposure"] = -1.0
    unsigned: dict[str, object] = {
        "schema_version": video.SCHEMA_VERSION,
        "kind": video.KIND,
        "capture_id": "",
        "capture_binding": video.CAPTURE_BINDING,
        "campaign_id": "BATCH3",
        "test_id": "TRUE-R20",
        "contract_id": "3" * 64,
        "firmware_sha256": "5" * 64,
        "boot_nonce": "batch3-boot",
        "ordinal": 1,
        "action_id": "1" * 64,
        "descriptor_id": "2" * 64,
        "role": "ACTIVE_R20_ROI_A",
        "stage": "A",
        "captured_at": "2026-08-28T10:00:00+08:00",
        "action_result": {
            "path": action_path.name,
            "bytes": len(action_path.read_bytes()),
            "file_sha256": hashlib.sha256(action_path.read_bytes()).hexdigest(),
            "canonical_integrity_sha256": action["integrity"]["sha256"],
            "outcome": "complete_pass",
            "terminal_state": "COMPLETE",
            "visible_refreshes": 1,
        },
        "camera": {
            "camera_id": "camera-1",
            "instance_id": "instance-1",
            "index": 0,
            "backend": "DSHOW",
            "requested_settings": settings,
            "effective_settings_before_video": dshow_effective,
            "effective_settings_after_video": dict(dshow_effective),
            "read_failures": 0,
        },
        "coverage": {
            "scope": video.COVERAGE_SCOPE,
            "full_panel_visible": True,
            "full_panel_uncropped": True,
            "mount_id": "fixed-mount-1",
        },
        "video": {
            "path": video_path.name,
            "bytes": len(video_payload),
            "sha256": hashlib.sha256(video_payload).hexdigest(),
            "width": 1920,
            "height": 1080,
            "fps": 10.0,
            "declared_frame_count": 300,
            "decoded_frame_count": 300,
            "duration_seconds": 30.0,
        },
        "capture_timing": {
            "started_at": "2026-08-28T10:00:00+08:00",
            "refresh_started_at": "2026-08-28T10:00:05+08:00",
            "refresh_completed_at": "2026-08-28T10:00:20+08:00",
            "completed_at": "2026-08-28T10:00:30+08:00",
            "clock_source": "host_wall_clock",
            "hardware_frame_timestamp": None,
            "hardware_frame_timestamp_null_reason": (
                "external recorder does not expose hardware timestamps"
            ),
        },
        "pre_roll_frames": 20,
        "minimum_duration_seconds": 25.0,
        "evidence_boundaries": {
            "external_capture_orchestrator_asserts_live_synchronization": True,
            "validator_does_not_operate_camera_or_device": True,
            "file_timestamps_alone_do_not_prove_synchronization": True,
            "separate_video_content_gate_required": True,
        },
        "output_write_contract": "O_EXCL",
    }
    unsigned["capture_id"] = hashlib.sha256(
        video._canonical_json(  # noqa: SLF001
            {
                "action_id": "1" * 64,
                "stage": "A",
                "captured_at": unsigned["captured_at"],
                "video_sha256": unsigned["video"]["sha256"],
            }
        )
    ).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(unsigned, sort_keys=True), encoding="utf-8")
    return manifest_path, tmp_path / "capture.video.json", video_path, unsigned


def test_seal_and_deep_validate_external_video_sidecar(tmp_path: Path) -> None:
    manifest, output, _video_path, unsigned = _manifest(tmp_path)
    sealed = video.seal_manifest(manifest, output)
    assert sealed["capture_id"] == unsigned["capture_id"]
    assert sealed["video"]["duration_seconds"] == 30.0
    assert video.validate(output) == sealed

    with pytest.raises(video.CameraVideoCaptureEvidenceError, match="overwrite"):
        video.seal_manifest(manifest, output)


def test_dshow_raw_manual_readback_is_not_accepted_for_another_backend(
    tmp_path: Path,
) -> None:
    manifest, output, _video_path, unsigned = _manifest(tmp_path)
    changed = deepcopy(unsigned)
    changed["camera"]["backend"] = "MSMF"
    manifest.write_text(json.dumps(changed, sort_keys=True), encoding="utf-8")

    with pytest.raises(
        video.CameraVideoCaptureEvidenceError,
        match="not an accepted MSMF manual-mode encoding",
    ):
        video.seal_manifest(manifest, output)


def test_video_byte_or_camera_readback_tamper_is_rejected(tmp_path: Path) -> None:
    manifest, output, video_path, _unsigned = _manifest(tmp_path)
    video.seal_manifest(manifest, output)
    video_path.write_bytes(b"tampered")
    with pytest.raises(video.CameraVideoCaptureEvidenceError, match="byte binding"):
        video.validate(output)

    second = tmp_path / "second"
    second.mkdir()
    manifest, output, _video_path, unsigned = _manifest(second)
    changed = deepcopy(unsigned)
    changed["camera"]["effective_settings_after_video"] = dict(
        changed["camera"]["effective_settings_after_video"]
    )
    changed["camera"]["effective_settings_after_video"]["exposure"] = -5.0
    manifest.write_text(json.dumps(changed, sort_keys=True), encoding="utf-8")
    with pytest.raises(
        video.CameraVideoCaptureEvidenceError, match="readbacks drifted"
    ):
        video.seal_manifest(manifest, output)


def test_short_or_misordered_refresh_video_is_rejected(tmp_path: Path) -> None:
    manifest, output, _video_path, unsigned = _manifest(tmp_path)
    changed = deepcopy(unsigned)
    changed["minimum_duration_seconds"] = 31.0
    manifest.write_text(json.dumps(changed, sort_keys=True), encoding="utf-8")
    with pytest.raises(video.CameraVideoCaptureEvidenceError, match="duration gate"):
        video.seal_manifest(manifest, output)

    changed = deepcopy(unsigned)
    changed["capture_timing"]["refresh_completed_at"] = "2026-08-28T09:59:59+08:00"
    manifest.write_text(json.dumps(changed, sort_keys=True), encoding="utf-8")
    with pytest.raises(video.CameraVideoCaptureEvidenceError, match="timing order"):
        video.seal_manifest(manifest, output)
