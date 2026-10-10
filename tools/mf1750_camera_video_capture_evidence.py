#!/usr/bin/env python3
"""Seal and validate externally recorded true-R20 refresh-video evidence.

This module performs no camera, device, network, serial, relay, flash, reset,
or display operation.  ``seal`` accepts a capture-orchestrator manifest for a
video that has already been recorded synchronously around one completed
action.  It verifies the exact action and video bytes, camera/mount lock,
manual-control readbacks, refresh timing, duration, and canonical seal.  The
manifest is therefore an evidence-binding interface, not a video recorder and
not independent proof that the external recorder's timestamps are truthful.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any

from tools import mf1750_camera_capture_evidence as photo_evidence
from tools import mf1750_factory_white_repeat_noise_report as noise_report


SCHEMA_VERSION = 1
KIND = "mf1750-true-r20-refresh-video-capture-evidence-v1"
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
CAPTURE_BINDING = "live_synchronized"
COVERAGE_SCOPE = "full_panel"
STAGES = ("A", "B", "C", "WHITE")


class CameraVideoCaptureEvidenceError(RuntimeError):
    """Raised when one video sidecar or its bound files differ."""


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CameraVideoCaptureEvidenceError(
            f"record contains a non-canonical JSON value: {exc}"
        ) from exc


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CameraVideoCaptureEvidenceError(f"{label} must be an object")
    return value


def _text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CameraVideoCaptureEvidenceError(f"{label} must be non-empty text")
    return value


def _sha(value: Any, *, label: str) -> str:
    text = _text(value, label=label)
    if photo_evidence.SHA256_RE.fullmatch(text) is None:
        raise CameraVideoCaptureEvidenceError(f"{label} is not lowercase SHA-256")
    return text


def _number(value: Any, *, label: str, positive: bool = False) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise CameraVideoCaptureEvidenceError(f"{label} must be finite")
    number = float(value)
    if positive and number <= 0:
        raise CameraVideoCaptureEvidenceError(f"{label} must be positive")
    return number


def _time(value: Any, *, label: str) -> datetime:
    text = _text(value, label=label)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise CameraVideoCaptureEvidenceError(f"{label} is not ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CameraVideoCaptureEvidenceError(f"{label} must include a UTC offset")
    return parsed


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        _payload, value = photo_evidence._load_strict_json(  # noqa: SLF001
            path, label="video capture manifest"
        )
    except photo_evidence.CameraCaptureEvidenceError as exc:
        raise CameraVideoCaptureEvidenceError(str(exc)) from exc
    if "integrity" in value:
        raise CameraVideoCaptureEvidenceError("unsealed manifest must omit integrity")
    return dict(value)


def _resolve(value: Any, *, sidecar_path: Path, label: str) -> Path:
    try:
        return photo_evidence._resolve_evidence_path(  # noqa: SLF001
            value, sidecar_path=sidecar_path, label=label
        )
    except photo_evidence.CameraCaptureEvidenceError as exc:
        raise CameraVideoCaptureEvidenceError(str(exc)) from exc


def _read(path: Path, *, label: str) -> bytes:
    try:
        return photo_evidence._read_stable_regular(path, label=label)  # noqa: SLF001
    except photo_evidence.CameraCaptureEvidenceError as exc:
        raise CameraVideoCaptureEvidenceError(str(exc)) from exc


def _validate_root(
    value: Mapping[str, Any], *, sidecar_path: Path, require_integrity: bool
) -> dict[str, Any]:
    expected_keys = {
        "schema_version",
        "kind",
        "capture_id",
        "capture_binding",
        "campaign_id",
        "test_id",
        "contract_id",
        "firmware_sha256",
        "boot_nonce",
        "ordinal",
        "action_id",
        "descriptor_id",
        "role",
        "stage",
        "captured_at",
        "action_result",
        "camera",
        "coverage",
        "video",
        "capture_timing",
        "pre_roll_frames",
        "minimum_duration_seconds",
        "evidence_boundaries",
        "output_write_contract",
    }
    if require_integrity:
        expected_keys.add("integrity")
    if set(value) != expected_keys:
        raise CameraVideoCaptureEvidenceError("video sidecar top-level keys differ")
    if value.get("schema_version") != SCHEMA_VERSION or value.get("kind") != KIND:
        raise CameraVideoCaptureEvidenceError("video sidecar schema identity differs")
    if value.get("capture_binding") != CAPTURE_BINDING:
        raise CameraVideoCaptureEvidenceError(
            "video sidecar is not live_synchronized evidence"
        )
    if value.get("output_write_contract") != "O_EXCL":
        raise CameraVideoCaptureEvidenceError("output write contract differs")
    if value.get("stage") not in STAGES:
        raise CameraVideoCaptureEvidenceError("video stage differs")

    if require_integrity:
        integrity = _mapping(value.get("integrity"), label="integrity")
        if set(integrity) != {"algorithm", "sha256"}:
            raise CameraVideoCaptureEvidenceError("integrity keys differ")
        if integrity.get("algorithm") != INTEGRITY_ALGORITHM:
            raise CameraVideoCaptureEvidenceError("integrity algorithm differs")
        declared = _sha(integrity.get("sha256"), label="integrity.sha256")
        unsigned = dict(value)
        unsigned.pop("integrity", None)
        if _sha256_bytes(_canonical_json(unsigned)) != declared:
            raise CameraVideoCaptureEvidenceError("canonical integrity differs")

    action_record = _mapping(value.get("action_result"), label="action_result")
    if set(action_record) != {
        "path",
        "bytes",
        "file_sha256",
        "canonical_integrity_sha256",
        "outcome",
        "terminal_state",
        "visible_refreshes",
    }:
        raise CameraVideoCaptureEvidenceError("action_result keys differ")
    action_path = _resolve(
        action_record.get("path"),
        sidecar_path=sidecar_path,
        label="action_result.path",
    )
    try:
        action_payload, _action_root, action_identity = (
            photo_evidence._load_action_result(action_path)  # noqa: SLF001
        )
    except photo_evidence.CameraCaptureEvidenceError as exc:
        raise CameraVideoCaptureEvidenceError(str(exc)) from exc
    if (
        action_record.get("bytes") != len(action_payload)
        or action_record.get("file_sha256") != _sha256_bytes(action_payload)
        or action_record.get("canonical_integrity_sha256")
        != action_identity["canonical_integrity_sha256"]
        or action_record.get("outcome") != "complete_pass"
        or action_record.get("terminal_state") != "COMPLETE"
        or action_record.get("visible_refreshes") != 1
    ):
        raise CameraVideoCaptureEvidenceError("action_result binding differs")
    for field in (
        "campaign_id",
        "test_id",
        "contract_id",
        "firmware_sha256",
        "boot_nonce",
        "ordinal",
        "action_id",
        "descriptor_id",
        "role",
    ):
        if value.get(field) != action_identity[field]:
            raise CameraVideoCaptureEvidenceError(
                f"video sidecar {field} differs from action"
            )

    camera = _mapping(value.get("camera"), label="camera")
    if set(camera) != {
        "camera_id",
        "instance_id",
        "index",
        "backend",
        "requested_settings",
        "effective_settings_before_video",
        "effective_settings_after_video",
        "read_failures",
    }:
        raise CameraVideoCaptureEvidenceError("camera keys differ")
    _text(camera.get("camera_id"), label="camera.camera_id")
    _text(camera.get("instance_id"), label="camera.instance_id")
    if type(camera.get("index")) is not int or camera["index"] < 0:
        raise CameraVideoCaptureEvidenceError("camera.index differs")
    backend = _text(camera.get("backend"), label="camera.backend")
    requested = _mapping(
        camera.get("requested_settings"), label="camera.requested_settings"
    )
    effective_before = _mapping(
        camera.get("effective_settings_before_video"),
        label="camera.effective_settings_before_video",
    )
    effective_after = _mapping(
        camera.get("effective_settings_after_video"),
        label="camera.effective_settings_after_video",
    )
    if dict(effective_before) != dict(effective_after):
        raise CameraVideoCaptureEvidenceError("effective camera readbacks drifted")
    try:
        noise_report._require_locked_settings(  # noqa: SLF001
            requested,
            effective_before,
            backend=backend,
            label="video camera",
        )
    except noise_report.FactoryWhiteRepeatNoiseReportError as exc:
        raise CameraVideoCaptureEvidenceError(str(exc)) from exc
    if camera.get("read_failures") != 0:
        raise CameraVideoCaptureEvidenceError("video camera read failures differ")

    coverage = _mapping(value.get("coverage"), label="coverage")
    if set(coverage) != {
        "scope",
        "full_panel_visible",
        "full_panel_uncropped",
        "mount_id",
    }:
        raise CameraVideoCaptureEvidenceError("coverage keys differ")
    if (
        coverage.get("scope") != COVERAGE_SCOPE
        or coverage.get("full_panel_visible") is not True
        or coverage.get("full_panel_uncropped") is not True
    ):
        raise CameraVideoCaptureEvidenceError("video is not full-panel evidence")
    _text(coverage.get("mount_id"), label="coverage.mount_id")

    video = _mapping(value.get("video"), label="video")
    if set(video) != {
        "path",
        "bytes",
        "sha256",
        "width",
        "height",
        "fps",
        "declared_frame_count",
        "decoded_frame_count",
        "duration_seconds",
    }:
        raise CameraVideoCaptureEvidenceError("video keys differ")
    video_path = _resolve(
        video.get("path"), sidecar_path=sidecar_path, label="video.path"
    )
    video_payload = _read(video_path, label="bound refresh video")
    if video.get("bytes") != len(video_payload) or video.get("sha256") != _sha256_bytes(
        video_payload
    ):
        raise CameraVideoCaptureEvidenceError("video byte binding differs")
    for field in ("width", "height", "decoded_frame_count"):
        if type(video.get(field)) is not int or video[field] < 1:
            raise CameraVideoCaptureEvidenceError(f"video.{field} differs")
    if (
        type(video.get("declared_frame_count")) is not int
        or video["declared_frame_count"] < 0
    ):
        raise CameraVideoCaptureEvidenceError("video.declared_frame_count differs")
    fps = _number(video.get("fps"), label="video.fps", positive=True)
    duration = _number(
        video.get("duration_seconds"), label="video.duration_seconds", positive=True
    )
    decoded_duration = video["decoded_frame_count"] / fps
    if not math.isclose(duration, decoded_duration, rel_tol=0.0, abs_tol=1e-6):
        raise CameraVideoCaptureEvidenceError(
            "video duration/frame/FPS binding differs"
        )
    pre_roll = value.get("pre_roll_frames")
    if (
        type(pre_roll) is not int
        or pre_roll < 2
        or pre_roll >= video["decoded_frame_count"]
    ):
        raise CameraVideoCaptureEvidenceError("pre-roll frame count differs")
    minimum_duration = _number(
        value.get("minimum_duration_seconds"),
        label="minimum_duration_seconds",
        positive=True,
    )
    if duration < minimum_duration:
        raise CameraVideoCaptureEvidenceError("video duration gate did not pass")

    timing = _mapping(value.get("capture_timing"), label="capture_timing")
    if set(timing) != {
        "started_at",
        "refresh_started_at",
        "refresh_completed_at",
        "completed_at",
        "clock_source",
        "hardware_frame_timestamp",
        "hardware_frame_timestamp_null_reason",
    }:
        raise CameraVideoCaptureEvidenceError("capture_timing keys differ")
    started = _time(timing.get("started_at"), label="capture_timing.started_at")
    refresh_started = _time(
        timing.get("refresh_started_at"),
        label="capture_timing.refresh_started_at",
    )
    refresh_completed = _time(
        timing.get("refresh_completed_at"),
        label="capture_timing.refresh_completed_at",
    )
    completed = _time(timing.get("completed_at"), label="capture_timing.completed_at")
    if not started < refresh_started < refresh_completed < completed:
        raise CameraVideoCaptureEvidenceError("video/refresh timing order differs")
    if value.get("captured_at") != timing.get("started_at"):
        raise CameraVideoCaptureEvidenceError("captured_at must equal video start")
    action_result_created = _time(
        action_identity["action_result_created_at"],
        label="action result created_at",
    )
    if not refresh_completed <= action_result_created <= completed:
        raise CameraVideoCaptureEvidenceError(
            "action result is not temporally enclosed after refresh completion"
        )
    observed_wall_duration = (completed - started).total_seconds()
    if not math.isclose(
        observed_wall_duration,
        duration,
        rel_tol=0.0,
        abs_tol=max(0.2, 2.0 / fps),
    ):
        raise CameraVideoCaptureEvidenceError(
            "video wall-clock and decoded duration differ"
        )
    observed_pre_roll = (refresh_started - started).total_seconds()
    minimum_pre_roll = (pre_roll - 1) / fps
    if observed_pre_roll < minimum_pre_roll:
        raise CameraVideoCaptureEvidenceError(
            "video timestamp does not contain the declared pre-roll"
        )
    if timing.get("clock_source") != "host_wall_clock":
        raise CameraVideoCaptureEvidenceError("capture clock source differs")
    if timing.get("hardware_frame_timestamp") is not None:
        raise CameraVideoCaptureEvidenceError("hardware frame timestamp must be null")
    _text(
        timing.get("hardware_frame_timestamp_null_reason"),
        label="hardware frame timestamp null reason",
    )

    boundaries = _mapping(value.get("evidence_boundaries"), label="evidence_boundaries")
    required_boundaries = {
        "external_capture_orchestrator_asserts_live_synchronization": True,
        "validator_does_not_operate_camera_or_device": True,
        "file_timestamps_alone_do_not_prove_synchronization": True,
        "separate_video_content_gate_required": True,
    }
    if dict(boundaries) != required_boundaries:
        raise CameraVideoCaptureEvidenceError("video evidence boundaries differ")

    capture_id = _sha256_bytes(
        _canonical_json(
            {
                "action_id": action_identity["action_id"],
                "stage": value["stage"],
                "captured_at": value["captured_at"],
                "video_sha256": video["sha256"],
            }
        )
    )
    if value.get("capture_id") != capture_id:
        raise CameraVideoCaptureEvidenceError("video capture_id differs")
    return dict(value)


def validate(sidecar_path: Path) -> dict[str, Any]:
    """Deep-validate one sealed video sidecar and both bound files."""

    sidecar_path = Path(sidecar_path)
    try:
        _payload, root = photo_evidence._load_strict_json(  # noqa: SLF001
            sidecar_path, label="video capture sidecar"
        )
    except photo_evidence.CameraCaptureEvidenceError as exc:
        raise CameraVideoCaptureEvidenceError(str(exc)) from exc
    return _validate_root(root, sidecar_path=sidecar_path, require_integrity=True)


def seal_manifest(manifest_path: Path, output_path: Path) -> dict[str, Any]:
    """Validate an external-recorder manifest and exclusively seal it."""

    output_path = Path(output_path)
    unsigned = _load_manifest(Path(manifest_path))
    _validate_root(unsigned, sidecar_path=output_path, require_integrity=False)
    sealed = dict(unsigned)
    sealed["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": _sha256_bytes(_canonical_json(unsigned)),
    }
    payload = (
        json.dumps(
            sealed,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(output_path, flags, 0o600)
    except FileExistsError as exc:
        raise CameraVideoCaptureEvidenceError(
            f"refusing to overwrite existing video sidecar: {output_path}"
        ) from exc
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return validate(output_path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    seal = commands.add_parser("seal", help="seal one external recorder manifest")
    seal.add_argument("--manifest", type=Path, required=True)
    seal.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("validate", help="deep-validate one sealed sidecar")
    check.add_argument("sidecar", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = (
            seal_manifest(args.manifest, args.output)
            if args.command == "seal"
            else validate(args.sidecar)
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0
    except CameraVideoCaptureEvidenceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
