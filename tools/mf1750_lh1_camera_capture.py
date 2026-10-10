#!/usr/bin/env python3
"""Generic MF1750 camera capture bound to an explicit action/white anchor.

This tool deliberately does not infer action identity from a legacy atlas schema.
It captures one frame, writes the JPEG and a strict O_EXCL sidecar, and keeps
current camera observation separate from historical action evidence.
"""

from __future__ import annotations
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from tools.mf1750_camera_capture_evidence import (
    CameraCaptureEvidenceError,
    _decode_jpeg,
    _default_capture_backend,
    _normalise_requested_settings,
    _resolve_exact_mf1750_camera,
    _validated_authenticated_device,
)

SCHEMA_VERSION = 1
TARGET_USB = ("32E4", "4801")


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canon(d: Mapping[str, Any]) -> str:
    return _sha(
        json.dumps(
            {k: v for k, v in d.items() if k != "integrity"},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _read_anchor(path: Path) -> tuple[bytes, dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise CameraCaptureEvidenceError("anchor must be a regular file")
    b = path.read_bytes()

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise CameraCaptureEvidenceError("duplicate anchor JSON key")
            value[key] = item
        return value

    try:
        d = json.loads(b.decode("utf-8-sig"), object_pairs_hook=unique)
    except Exception as e:
        raise CameraCaptureEvidenceError(f"anchor is not JSON: {e}") from e
    if not isinstance(d, dict):
        raise CameraCaptureEvidenceError("anchor root must be object")
    integrity = d.get("integrity", {})
    stated = integrity.get("sha256", integrity.get("canonical_sha256"))
    if not stated or stated != _canon(d):
        raise CameraCaptureEvidenceError("anchor integrity missing or mismatched")
    return b, d


def _device_ref(dev: Mapping[str, Any]) -> dict[str, Any]:
    got = _validated_authenticated_device(dev)
    return {
        "friendly_name": got["friendly_name"],
        "alternative_name": got["alternative_name"],
        "pnp_instance_id": got["pnp_instance_id"],
        "directshow_index": got["directshow_index"],
        "usb_vid": got["usb_vid"],
        "usb_pid": got["usb_pid"],
    }


def capture(
    *,
    anchor_path: Path,
    photo_path: Path,
    sidecar_path: Path,
    run_id: str,
    camera_id: str = "48MP USB Camera",
    camera_index: int | None = None,
    requested_settings: Mapping[str, Any] | None = None,
    warmup_frames: int = 5,
    jpeg_quality: int = 95,
    coverage_scope: str = "full_panel",
    coverage_note: str | None = None,
    capture_backend: Callable | None = None,
    device_resolver: Callable | None = None,
) -> dict[str, Any]:
    if not run_id or any(c in run_id for c in "\x00\r\n"):
        raise CameraCaptureEvidenceError("run_id is invalid")
    if photo_path.resolve() == sidecar_path.resolve():
        raise CameraCaptureEvidenceError("photo and sidecar paths must differ")
    if camera_index is not None and (type(camera_index) is not int or camera_index < 0):
        raise CameraCaptureEvidenceError("camera_index invalid")
    if not 0 <= warmup_frames <= 300:
        raise CameraCaptureEvidenceError("warmup_frames out of range")
    if not 1 <= jpeg_quality <= 100:
        raise CameraCaptureEvidenceError("jpeg_quality out of range")
    anchor_bytes, anchor = _read_anchor(anchor_path)
    resolver = device_resolver or _resolve_exact_mf1750_camera
    before = _device_ref(resolver())
    if camera_id not in {"48MP USB Camera", "MF1750_48MP_USB_CAMERA"}:
        raise CameraCaptureEvidenceError(
            "camera_id must identify VID_32E4:PID_4801 target"
        )
    if camera_index is not None and camera_index != before["directshow_index"]:
        raise CameraCaptureEvidenceError(
            "camera_index differs from authenticated target"
        )
    settings = _normalise_requested_settings(
        requested_settings
        or {
            "fourcc": "MJPG",
            "frame_width": 4000,
            "frame_height": 3000,
            "fps": 15,
            "autofocus": 0,
            "focus": 79,
            "auto_exposure": 0.25,
            "exposure": -6,
            "auto_white_balance": 0,
            "white_balance_temperature": 4600,
        }
    )
    photo_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    handles = []
    for path, label in ((photo_path, "photo"), (sidecar_path, "sidecar")):
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            handles.append(os.fdopen(fd, "wb"))
        except FileExistsError as e:
            for handle in handles:
                handle.close()
            raise CameraCaptureEvidenceError(f"{label} already exists (O_EXCL)") from e
    started = _now()
    payload = b""
    try:
        if capture_backend is not None:
            payload, diag = capture_backend(
                before["directshow_index"], settings, warmup_frames, jpeg_quality
            )
        else:
            payload, diag = _default_capture_backend(
                before["directshow_index"],
                settings,
                warmup_frames,
                jpeg_quality,
                _device_resolver=resolver,
            )
        if not isinstance(payload, bytes) or not payload:
            raise CameraCaptureEvidenceError("capture returned empty bytes")
        backend_device = _device_ref(diag.get("authenticated_device"))
        if backend_device != before:
            raise CameraCaptureEvidenceError("camera identity changed during capture")
        after = _device_ref(resolver())
        if after != before:
            raise CameraCaptureEvidenceError("camera identity changed after capture")
        if str(diag.get("backend", "")).casefold() != "dshow":
            raise CameraCaptureEvidenceError("capture backend is not DirectShow")
        if diag.get("warmup_frames_completed") != warmup_frames:
            raise CameraCaptureEvidenceError("warmup count mismatch")
        decoded = _decode_jpeg(payload)
        frame_at = diag.get("frame_retrieved_at") or started
        frame_utc = diag.get("frame_retrieved_at_utc") or frame_at
        anchor_ref = {
            "path": str(anchor_path),
            "bytes": len(anchor_bytes),
            "file_sha256": _sha(anchor_bytes),
            "canonical_sha256": _canon(anchor),
        }
        rec = {
            "schema_version": SCHEMA_VERSION,
            "kind": "mf1750-lh1-camera-capture",
            "run_id": run_id,
            "stage": "CURRENT_CAMERA_OBSERVATION",
            "historical_action_anchor": anchor_ref,
            "camera": {
                "id": "48MP USB Camera",
                "usb_vid": "32E4",
                "usb_pid": "4801",
                "authenticated_before": before,
                "authenticated_after": after,
                "backend": diag["backend"],
                "requested_settings": settings,
                "effective_settings_before_frame": diag.get(
                    "effective_settings_before_frame"
                ),
                "effective_settings_after_frame": diag.get(
                    "effective_settings_after_frame"
                ),
                "set_results": diag.get("set_results"),
                "read_failures": diag.get("read_failures"),
                "warmup_frames_completed": diag.get("warmup_frames_completed"),
                "manual_lock_proven": False,
                "manual_lock_note": "Set requests and readback are recorded; lock/stability requires separate review.",
                "raw_supported": False,
                "iso_supported": False,
                "hardware_trigger_supported": False,
                "unsupported_features_note": "Capture backend exposes no RAW, ISO or authenticated hardware trigger.",
            },
            "capture_timing": {
                "started_at": started,
                "frame_retrieved_at": frame_at,
                "frame_retrieved_at_utc": frame_utc,
                "completed_at": _now(),
                "hardware_frame_timestamp": None,
                "hardware_frame_timestamp_null_reason": "DirectShow/OpenCV backend has no authenticated hardware timestamp",
            },
            "coverage": {
                "scope": coverage_scope,
                "full_panel_validity": "UNKNOWN",
                "full_panel_validity_requires_review": True,
                "note": coverage_note,
            },
            "photo": {
                "path": str(photo_path),
                "bytes": len(payload),
                "sha256": _sha(payload),
                "decoded": decoded,
                "origin": "captured_by_tool",
            },
            "observation": {
                "lab_space": "camera-relative",
                "calibrated_lab": False,
                "roi": None,
                "temperature_c": None,
                "candidate_lightness": None,
                "verdict": "INCONCLUSIVE",
            },
            "output_write_contract": "O_EXCL",
        }
        rec["integrity"] = {
            "algorithm": "sha256-canonical-json-without-integrity",
            "sha256": _canon(rec),
        }
        handles[0].write(payload)
        handles[1].write(
            (
                json.dumps(rec, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
            ).encode()
        )
        return rec
    except Exception as exc:
        # Preserve failed capture bytes and the failure instead of deleting evidence.
        if payload and handles[0].tell() == 0:
            handles[0].write(payload)
        failure = {
            "kind": "mf1750-lh1-camera-capture-failure",
            "run_id": run_id,
            "started_at": started,
            "finished_at": _now(),
            "error": str(exc),
            "stage": "CURRENT_CAMERA_OBSERVATION",
            "usable_optical_evidence": False,
            "historical_action_anchor_file_sha256": _sha(anchor_bytes),
        }
        failure["integrity"] = {
            "algorithm": "sha256-canonical-json-without-integrity",
            "sha256": _canon(failure),
        }
        if handles[1].tell() == 0:
            handles[1].write(
                (json.dumps(failure, ensure_ascii=False, indent=2) + "\n").encode()
            )
        raise
    finally:
        for handle in handles:
            handle.flush()
            os.fsync(handle.fileno())
            handle.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--anchor", required=True, type=Path)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--photo", required=True, type=Path)
    ap.add_argument("--sidecar", required=True, type=Path)
    ap.add_argument("--camera-index", type=int)
    ap.add_argument("--warmup-frames", type=int, default=5)
    ap.add_argument("--jpeg-quality", type=int, default=95)
    ap.add_argument("--coverage-scope", default="full_panel")
    ap.add_argument("--coverage-note")
    ns = ap.parse_args()
    try:
        capture(
            anchor_path=ns.anchor,
            photo_path=ns.photo,
            sidecar_path=ns.sidecar,
            run_id=ns.run_id,
            camera_index=ns.camera_index,
            warmup_frames=ns.warmup_frames,
            jpeg_quality=ns.jpeg_quality,
            coverage_scope=ns.coverage_scope,
            coverage_note=ns.coverage_note,
        )
    except (CameraCaptureEvidenceError, OSError, ValueError) as e:
        ap.error(str(e))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
