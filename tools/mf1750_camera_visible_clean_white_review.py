#!/usr/bin/env python3
"""Build and validate a conservative camera-visible clean-white review.

The tool is offline-only.  It reads an already-completed factory-white action,
an already-sealed camera capture sidecar and its exact JPEG, and an exact-bound
relay-OFF receipt.  It never opens a camera, relay, serial port, or network
connection and never flashes or refreshes a display.

A ``PASS`` is deliberately narrow: the retained frame shows a white field and
does not show obvious colour blocks/blotches, gross horizontal/vertical
stripes, or an obvious centre-seam anomaly.  It is not an absolute white-point,
uniformity, gray-level, colour-level, or retained-continuity qualification.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_camera_capture_evidence as camera  # noqa: E402
from tools.mf17506_stage23 import relay_exact_bound_switch as relay  # noqa: E402


SCHEMA_VERSION = 1
KIND = "mf1750-camera-visible-clean-white-review"
OUTPUT_WRITE_CONTRACT = "O_EXCL"
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
CLASSIFICATION_STATE = "CAMERA_VISIBLE_CLEAN_WHITE_REVIEW"
PASS_SCOPE = (
    "NO_OBVIOUS_COLOUR_BLOCKS_BLOTCHES_GROSS_HORIZONTAL_OR_VERTICAL_STRIPES_"
    "OR_CENTER_SEAM_ANOMALY_IN_THIS_FRAME"
)
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_PHOTO_BYTES = 128 * 1024 * 1024
CONFIDENCES = frozenset({"LOW", "MEDIUM", "HIGH"})
FACTORY_WHITE_ROLES = frozenset(
    {
        camera.FACTORY_OTP_WHITE_ACTION_ROLE,
        camera.FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE,
    }
)
QUALIFICATION_LIMITS = {
    "camera_relative_only": True,
    "absolute_white_point_proven": False,
    "spatial_uniformity_proven": False,
    "qualified_white_or_gray_level": False,
    "qualified_level_count": 0,
    "retained_action_to_capture_continuity_proven": False,
    "weak_or_low_contrast_residual_excluded": False,
}
OFFLINE_EXECUTION = {
    "hardware_accessed": False,
    "camera_accessed": False,
    "relay_accessed": False,
    "serial_or_com_accessed": False,
    "network_accessed": False,
    "firmware_flashed": False,
    "display_refreshed": False,
}


class CameraVisibleCleanWhiteReviewError(RuntimeError):
    """The review request or one of its bound evidence files is invalid."""


class _DuplicateKeyError(ValueError):
    pass


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise CameraVisibleCleanWhiteReviewError(
            f"value is not canonical-JSON encodable: {error}"
        ) from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    root = dict(unsigned)
    root["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": _sha256(_canonical_json_bytes(root)),
    }
    return root


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result


def _read_stable_regular(path: Path, *, label: str, maximum: int) -> bytes:
    path = Path(path)
    try:
        before = path.lstat()
    except OSError as error:
        raise CameraVisibleCleanWhiteReviewError(
            f"cannot stat {label}: {error}"
        ) from error
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise CameraVisibleCleanWhiteReviewError(
            f"{label} must be a regular non-symlink file"
        )
    if before.st_size < 1 or before.st_size > maximum:
        raise CameraVisibleCleanWhiteReviewError(f"{label} size is outside its limit")
    try:
        payload = path.read_bytes()
        after = path.stat()
    except OSError as error:
        raise CameraVisibleCleanWhiteReviewError(
            f"cannot read {label}: {error}"
        ) from error
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or len(payload) != before.st_size:
        raise CameraVisibleCleanWhiteReviewError(f"{label} changed while being read")
    return payload


def _load_json(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    payload = _read_stable_regular(path, label=label, maximum=MAX_JSON_BYTES)
    try:
        value = json.loads(payload, object_pairs_hook=_reject_duplicate_keys)
    except (_DuplicateKeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CameraVisibleCleanWhiteReviewError(
            f"{label} is not strict UTF-8 JSON: {error}"
        ) from error
    if not isinstance(value, dict):
        raise CameraVisibleCleanWhiteReviewError(f"{label} root must be an object")
    return payload, value


def _require_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CameraVisibleCleanWhiteReviewError(f"{label} must be an object")
    return value


def _require_text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CameraVisibleCleanWhiteReviewError(f"{label} must be non-empty text")
    return value


def _require_bool(value: Any, *, label: str) -> bool:
    if type(value) is not bool:
        raise CameraVisibleCleanWhiteReviewError(f"{label} must be boolean")
    return value


def _timestamp(value: Any, *, label: str) -> tuple[str, datetime]:
    text = _require_text(value, label=label)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise CameraVisibleCleanWhiteReviewError(
            f"{label} is not an ISO-8601 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CameraVisibleCleanWhiteReviewError(f"{label} must include a UTC offset")
    return text, parsed


def _relative_source(path: Path, *, output_path: Path, label: str) -> str:
    base = output_path.parent.resolve()
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(base)
    except ValueError as error:
        raise CameraVisibleCleanWhiteReviewError(
            f"{label} must be inside the review output directory tree"
        ) from error
    if not relative.parts:
        raise CameraVisibleCleanWhiteReviewError(
            f"{label} cannot be the output directory"
        )
    return PurePosixPath(*relative.parts).as_posix()


def _resolve_source(value: Any, *, review_path: Path, label: str) -> Path:
    text = _require_text(value, label=label)
    pure = PurePosixPath(text)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise CameraVisibleCleanWhiteReviewError(
            f"{label} must be a safe relative POSIX path"
        )
    base = review_path.parent.resolve()
    candidate = review_path.parent.joinpath(*pure.parts).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as error:
        raise CameraVisibleCleanWhiteReviewError(
            f"{label} escapes the review tree"
        ) from error
    return candidate


def _capture_bound_path(
    sidecar: Mapping[str, Any],
    *,
    sidecar_path: Path,
    section: str,
) -> Path:
    record = _require_mapping(sidecar.get(section), label=f"capture.{section}")
    text = _require_text(record.get("path"), label=f"capture.{section}.path")
    pure = PurePosixPath(text)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise CameraVisibleCleanWhiteReviewError(
            f"capture.{section}.path is not a safe relative POSIX path"
        )
    return sidecar_path.parent.joinpath(*pure.parts).resolve()


def _validated_observation(
    *,
    reviewer: str,
    method: str,
    confidence: str,
    camera_visible_white_field: bool,
    obvious_colour_blocks_or_blotches_visible: bool,
    obvious_gross_horizontal_stripes_visible: bool,
    obvious_gross_vertical_stripes_visible: bool,
    obvious_center_seam_anomaly_visible: bool,
    limitations_observed: Sequence[str],
) -> dict[str, Any]:
    clean_confidence = _require_text(confidence, label="review confidence").upper()
    if clean_confidence not in CONFIDENCES:
        raise CameraVisibleCleanWhiteReviewError("review confidence is invalid")
    limitations: list[str] = []
    for item in limitations_observed:
        text = _require_text(item, label="observed limitation")
        if text not in limitations:
            limitations.append(text)
    return {
        "reviewer": _require_text(reviewer, label="reviewer"),
        "method": _require_text(method, label="review method"),
        "review_confidence": clean_confidence,
        "camera_visible_white_field": _require_bool(
            camera_visible_white_field, label="camera_visible_white_field"
        ),
        "full_display_active_area_visible_in_frame": True,
        "obvious_colour_blocks_or_colour_blotches_visible": _require_bool(
            obvious_colour_blocks_or_blotches_visible,
            label="obvious_colour_blocks_or_colour_blotches_visible",
        ),
        "obvious_gross_horizontal_stripes_visible": _require_bool(
            obvious_gross_horizontal_stripes_visible,
            label="obvious_gross_horizontal_stripes_visible",
        ),
        "obvious_gross_vertical_stripes_visible": _require_bool(
            obvious_gross_vertical_stripes_visible,
            label="obvious_gross_vertical_stripes_visible",
        ),
        "obvious_center_seam_anomaly_visible": _require_bool(
            obvious_center_seam_anomaly_visible,
            label="obvious_center_seam_anomaly_visible",
        ),
        "limitations_observed": limitations,
    }


def _classification(observation: Mapping[str, Any]) -> dict[str, Any]:
    defect_visible = any(
        observation[field]
        for field in (
            "obvious_colour_blocks_or_colour_blotches_visible",
            "obvious_gross_horizontal_stripes_visible",
            "obvious_gross_vertical_stripes_visible",
            "obvious_center_seam_anomaly_visible",
        )
    )
    if observation["camera_visible_white_field"] is not True or defect_visible:
        verdict = "FAIL"
        reason = (
            "the retained frame does not show a camera-visible white field without "
            "an obvious colour block/blotch, gross stripe, or centre-seam anomaly"
        )
    elif observation["review_confidence"] == "LOW":
        verdict = "REVIEW"
        reason = (
            "no scoped obvious defect was reported, but LOW review confidence cannot "
            "earn PASS"
        )
    else:
        verdict = "PASS"
        reason = (
            "the full active area is visible as a camera-relative white field with no "
            "obvious colour blocks/blotches, gross horizontal/vertical stripes, or "
            "obvious centre-seam anomaly in this retained frame"
        )
    return {
        "state": CLASSIFICATION_STATE,
        "verdict": verdict,
        "camera_visible_clean_white_review_passed": verdict == "PASS",
        "pass_scope": PASS_SCOPE,
        "reason": reason,
        **QUALIFICATION_LIMITS,
    }


def _validate_source_evidence(
    *,
    action_result_path: Path,
    capture_sidecar_path: Path,
    photo_path: Path,
    relay_off_receipt_path: Path,
) -> dict[str, Any]:
    action_result_path = Path(action_result_path)
    capture_sidecar_path = Path(capture_sidecar_path)
    photo_path = Path(photo_path)
    relay_off_receipt_path = Path(relay_off_receipt_path)

    action_payload = _read_stable_regular(
        action_result_path, label="action result", maximum=MAX_JSON_BYTES
    )
    sidecar_payload = _read_stable_regular(
        capture_sidecar_path, label="capture sidecar", maximum=MAX_JSON_BYTES
    )
    photo_payload = _read_stable_regular(
        photo_path, label="capture JPEG", maximum=MAX_PHOTO_BYTES
    )
    relay_payload, relay_root = _load_json(
        relay_off_receipt_path, label="relay-OFF receipt"
    )

    try:
        capture_root = camera.validate_capture_evidence(capture_sidecar_path)
    except (camera.CameraCaptureEvidenceError, OSError) as error:
        raise CameraVisibleCleanWhiteReviewError(
            f"capture evidence validation failed: {error}"
        ) from error
    try:
        relay_root = relay.validate_receipt(relay_root)
    except (relay.RelayExactBoundSwitchError, ValueError) as error:
        raise CameraVisibleCleanWhiteReviewError(
            f"relay-OFF receipt validation failed: {error}"
        ) from error

    if (
        _capture_bound_path(
            capture_root,
            sidecar_path=capture_sidecar_path,
            section="action_result",
        )
        != action_result_path.resolve()
    ):
        raise CameraVisibleCleanWhiteReviewError(
            "provided action result is not the capture-bound action result"
        )
    if (
        _capture_bound_path(
            capture_root,
            sidecar_path=capture_sidecar_path,
            section="photo",
        )
        != photo_path.resolve()
    ):
        raise CameraVisibleCleanWhiteReviewError(
            "provided JPEG is not the capture-bound JPEG"
        )

    if action_payload != _read_stable_regular(
        action_result_path, label="action result replay", maximum=MAX_JSON_BYTES
    ):
        raise CameraVisibleCleanWhiteReviewError(
            "action result changed during validation"
        )
    if sidecar_payload != _read_stable_regular(
        capture_sidecar_path, label="capture sidecar replay", maximum=MAX_JSON_BYTES
    ):
        raise CameraVisibleCleanWhiteReviewError(
            "capture sidecar changed during validation"
        )
    if photo_payload != _read_stable_regular(
        photo_path, label="capture JPEG replay", maximum=MAX_PHOTO_BYTES
    ):
        raise CameraVisibleCleanWhiteReviewError(
            "capture JPEG changed during validation"
        )
    if relay_payload != _read_stable_regular(
        relay_off_receipt_path, label="relay-OFF receipt replay", maximum=MAX_JSON_BYTES
    ):
        raise CameraVisibleCleanWhiteReviewError(
            "relay-OFF receipt changed during validation"
        )

    coverage = _require_mapping(capture_root.get("coverage"), label="capture coverage")
    if (
        coverage.get("scope") != camera.COVERAGE_FULL
        or coverage.get("full_panel_visible") is not True
        or coverage.get("full_panel_uncropped") is not True
    ):
        raise CameraVisibleCleanWhiteReviewError(
            "clean-white review requires full-panel uncropped capture coverage"
        )
    if capture_root.get("capture_binding") not in {
        camera.BINDING_RETROSPECTIVE,
        camera.BINDING_LOCKED_RETAINED,
    }:
        raise CameraVisibleCleanWhiteReviewError(
            "clean-white review requires retrospective retained capture evidence"
        )
    if capture_root.get("role") not in FACTORY_WHITE_ROLES:
        raise CameraVisibleCleanWhiteReviewError(
            "capture action is not an admitted factory-white role"
        )
    action_record = _require_mapping(
        capture_root.get("action_result"), label="capture action_result"
    )
    if (
        action_record.get("outcome") != "complete_pass"
        or action_record.get("terminal_state") != "COMPLETE"
        or action_record.get("visible_refreshes") != 1
    ):
        raise CameraVisibleCleanWhiteReviewError(
            "factory-white action is not one COMPLETE visible refresh"
        )
    photo_record = _require_mapping(capture_root.get("photo"), label="capture photo")
    quality = _require_mapping(
        photo_record.get("quality_metrics"), label="capture photo quality_metrics"
    )
    if (
        quality.get("camera_relative_only") is not True
        or quality.get("absolute_colour_qualification") is not False
    ):
        raise CameraVisibleCleanWhiteReviewError(
            "capture does not preserve camera-relative qualification limits"
        )
    if (
        relay_root.get("target_state") != "OFF"
        or relay_root.get("commanded_state") != "OFF"
        or relay_root.get("target_gate_passed") is not True
        or relay_root.get("off_gate_passed") is not True
        or relay_root.get("electrical_state_proven") is not False
    ):
        raise CameraVisibleCleanWhiteReviewError(
            "relay receipt is not an exact commanded-OFF gate"
        )

    _, action_root = _load_json(action_result_path, label="action result JSON")
    _action_created_text, action_created = _timestamp(
        action_root.get("created_at"), label="action result created_at"
    )
    relay_switched_text, relay_switched = _timestamp(
        relay_root.get("switched_at"), label="relay switched_at"
    )
    capture_text, captured = _timestamp(
        capture_root.get("captured_at"), label="capture captured_at"
    )
    if not action_created <= relay_switched <= captured:
        raise CameraVisibleCleanWhiteReviewError(
            "expected action-result <= relay-OFF <= retained-capture chronology"
        )

    return {
        "action_payload": action_payload,
        "action_root": action_root,
        "capture_sidecar_payload": sidecar_payload,
        "capture": capture_root,
        "photo_payload": photo_payload,
        "relay_payload": relay_payload,
        "relay": relay_root,
        "relay_switched_at": relay_switched_text,
        "captured_at": capture_text,
    }


def _build_record(
    *,
    output_path: Path,
    action_result_path: Path,
    capture_sidecar_path: Path,
    photo_path: Path,
    relay_off_receipt_path: Path,
    reviewed_at: str,
    observation: Mapping[str, Any],
    source: Mapping[str, Any],
) -> dict[str, Any]:
    capture_root = source["capture"]
    relay_root = source["relay"]
    photo_record = _require_mapping(capture_root["photo"], label="capture photo")
    action_record = _require_mapping(
        capture_root["action_result"], label="capture action_result"
    )
    reviewed_text, reviewed = _timestamp(reviewed_at, label="reviewed_at")
    _captured_text, captured = _timestamp(
        capture_root["captured_at"], label="capture captured_at"
    )
    if reviewed < captured:
        raise CameraVisibleCleanWhiteReviewError(
            "reviewed_at cannot precede the retained capture"
        )
    classification = _classification(observation)
    relay_integrity = _require_mapping(relay_root["integrity"], label="relay integrity")
    review_id = _sha256(
        _canonical_json_bytes(
            {
                "action_id": capture_root["action_id"],
                "capture_id": capture_root["capture_id"],
                "photo_sha256": photo_record["sha256"],
                "relay_receipt_canonical_sha256": relay_integrity["canonical_sha256"],
                "reviewed_at": reviewed_text,
                "observation": observation,
            }
        )
    )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "review_id": review_id,
        "reviewed_at": reviewed_text,
        "campaign_id": capture_root["campaign_id"],
        "test_id": capture_root["test_id"],
        "contract_id": capture_root["contract_id"],
        "firmware_sha256": capture_root["firmware_sha256"],
        "action_id": capture_root["action_id"],
        "descriptor_id": capture_root["descriptor_id"],
        "capture_id": capture_root["capture_id"],
        "action_binding": {
            "role": capture_root["role"],
            "ordinal": capture_root["ordinal"],
            "outcome": action_record["outcome"],
            "terminal_state": action_record["terminal_state"],
            "visible_refreshes": action_record["visible_refreshes"],
            "canonical_integrity_sha256": action_record["canonical_integrity_sha256"],
        },
        "capture_binding": {
            "binding": capture_root["capture_binding"],
            "camera_id": capture_root["camera"]["camera_id"],
            "camera_instance_id": capture_root["camera"]["instance_id"],
            "mount_id": capture_root["coverage"]["mount_id"],
            "scope": capture_root["coverage"]["scope"],
            "full_panel_visible": capture_root["coverage"]["full_panel_visible"],
            "full_panel_uncropped": capture_root["coverage"]["full_panel_uncropped"],
            "camera_relative_only": True,
            "retained_action_to_capture_continuity_proven": False,
        },
        "relay_post_action_off": {
            "switched_at": relay_root["switched_at"],
            "channel": relay_root["channel"],
            "contact_path": relay_root["contact_path"],
            "target_state": relay_root["target_state"],
            "commanded_state": relay_root["commanded_state"],
            "target_gate_passed": relay_root["target_gate_passed"],
            "off_gate_passed": relay_root["off_gate_passed"],
            "electrical_state_proven": relay_root["electrical_state_proven"],
        },
        "offline_visual_review": dict(observation),
        "classification": classification,
        "source_evidence": {
            "action_result": {
                "path": _relative_source(
                    action_result_path,
                    output_path=output_path,
                    label="action result",
                ),
                "bytes": len(source["action_payload"]),
                "file_sha256": _sha256(source["action_payload"]),
                "canonical_integrity_sha256": action_record[
                    "canonical_integrity_sha256"
                ],
            },
            "capture_sidecar": {
                "path": _relative_source(
                    capture_sidecar_path,
                    output_path=output_path,
                    label="capture sidecar",
                ),
                "bytes": len(source["capture_sidecar_payload"]),
                "file_sha256": _sha256(source["capture_sidecar_payload"]),
                "canonical_integrity_sha256": capture_root["integrity"]["sha256"],
            },
            "photo": {
                "path": _relative_source(
                    photo_path, output_path=output_path, label="capture JPEG"
                ),
                "bytes": len(source["photo_payload"]),
                "file_sha256": _sha256(source["photo_payload"]),
                "width": photo_record["width"],
                "height": photo_record["height"],
                "mode": photo_record["mode"],
            },
            "relay_off_receipt": {
                "path": _relative_source(
                    relay_off_receipt_path,
                    output_path=output_path,
                    label="relay-OFF receipt",
                ),
                "bytes": len(source["relay_payload"]),
                "file_sha256": _sha256(source["relay_payload"]),
                "canonical_integrity_sha256": relay_integrity["canonical_sha256"],
            },
        },
        "offline_execution": dict(OFFLINE_EXECUTION),
        "output_write_contract": OUTPUT_WRITE_CONTRACT,
    }
    return _seal(unsigned)


def _reserve_output(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
    except FileExistsError as error:
        raise CameraVisibleCleanWhiteReviewError(
            f"refusing to overwrite review output: {path}"
        ) from error
    except OSError as error:
        raise CameraVisibleCleanWhiteReviewError(
            f"cannot reserve review output: {error}"
        ) from error


def _write_reserved(fd: int, payload: bytes) -> None:
    written = 0
    while written < len(payload):
        count = os.write(fd, payload[written:])
        if count < 1:
            raise CameraVisibleCleanWhiteReviewError("short write to review output")
        written += count
    os.fsync(fd)


def create_review(
    *,
    action_result_path: Path,
    capture_sidecar_path: Path,
    photo_path: Path,
    relay_off_receipt_path: Path,
    output_path: Path,
    reviewed_at: str,
    reviewer: str,
    method: str,
    confidence: str,
    camera_visible_white_field: bool,
    obvious_colour_blocks_or_blotches_visible: bool,
    obvious_gross_horizontal_stripes_visible: bool,
    obvious_gross_vertical_stripes_visible: bool,
    obvious_center_seam_anomaly_visible: bool,
    limitations_observed: Sequence[str] = (),
) -> dict[str, Any]:
    """Create one O_EXCL-sealed offline review and deep-replay it."""

    output_path = Path(output_path)
    sources = tuple(
        Path(path).resolve()
        for path in (
            action_result_path,
            capture_sidecar_path,
            photo_path,
            relay_off_receipt_path,
        )
    )
    if len(set(sources)) != len(sources) or output_path.resolve() in set(sources):
        raise CameraVisibleCleanWhiteReviewError(
            "review output and all four source files must be distinct"
        )
    observation = _validated_observation(
        reviewer=reviewer,
        method=method,
        confidence=confidence,
        camera_visible_white_field=camera_visible_white_field,
        obvious_colour_blocks_or_blotches_visible=(
            obvious_colour_blocks_or_blotches_visible
        ),
        obvious_gross_horizontal_stripes_visible=(
            obvious_gross_horizontal_stripes_visible
        ),
        obvious_gross_vertical_stripes_visible=obvious_gross_vertical_stripes_visible,
        obvious_center_seam_anomaly_visible=obvious_center_seam_anomaly_visible,
        limitations_observed=limitations_observed,
    )
    source = _validate_source_evidence(
        action_result_path=Path(action_result_path),
        capture_sidecar_path=Path(capture_sidecar_path),
        photo_path=Path(photo_path),
        relay_off_receipt_path=Path(relay_off_receipt_path),
    )
    record = _build_record(
        output_path=output_path,
        action_result_path=Path(action_result_path),
        capture_sidecar_path=Path(capture_sidecar_path),
        photo_path=Path(photo_path),
        relay_off_receipt_path=Path(relay_off_receipt_path),
        reviewed_at=reviewed_at,
        observation=observation,
        source=source,
    )
    fd: int | None = _reserve_output(output_path)
    committed = False
    try:
        assert fd is not None
        _write_reserved(fd, _canonical_json_bytes(record) + b"\n")
        os.close(fd)
        fd = None
        validated = validate_review(output_path)
        committed = True
        return validated
    finally:
        if fd is not None:
            os.close(fd)
        if not committed:
            output_path.unlink(missing_ok=True)


def validate_review(review_path: Path) -> dict[str, Any]:
    """Deep-validate a review, all source files, and all conservative limits."""

    review_path = Path(review_path)
    _payload, root = _load_json(review_path, label="clean-white review")
    if set(root) != {
        "schema_version",
        "kind",
        "review_id",
        "reviewed_at",
        "campaign_id",
        "test_id",
        "contract_id",
        "firmware_sha256",
        "action_id",
        "descriptor_id",
        "capture_id",
        "action_binding",
        "capture_binding",
        "relay_post_action_off",
        "offline_visual_review",
        "classification",
        "source_evidence",
        "offline_execution",
        "output_write_contract",
        "integrity",
    }:
        raise CameraVisibleCleanWhiteReviewError("review top-level keys differ")
    if (
        root.get("schema_version") != SCHEMA_VERSION
        or root.get("kind") != KIND
        or root.get("output_write_contract") != OUTPUT_WRITE_CONTRACT
    ):
        raise CameraVisibleCleanWhiteReviewError("review root contract differs")
    integrity = _require_mapping(root.get("integrity"), label="review integrity")
    if set(integrity) != {"algorithm", "sha256"}:
        raise CameraVisibleCleanWhiteReviewError("review integrity keys differ")
    unsigned = dict(root)
    unsigned.pop("integrity")
    if integrity.get("algorithm") != INTEGRITY_ALGORITHM or integrity.get(
        "sha256"
    ) != _sha256(_canonical_json_bytes(unsigned)):
        raise CameraVisibleCleanWhiteReviewError("review canonical integrity differs")

    evidence = _require_mapping(root.get("source_evidence"), label="source_evidence")
    if set(evidence) != {
        "action_result",
        "capture_sidecar",
        "photo",
        "relay_off_receipt",
    }:
        raise CameraVisibleCleanWhiteReviewError("source_evidence keys differ")
    paths = {
        name: _resolve_source(
            _require_mapping(evidence.get(name), label=f"source_evidence.{name}").get(
                "path"
            ),
            review_path=review_path,
            label=f"source_evidence.{name}.path",
        )
        for name in evidence
    }
    source = _validate_source_evidence(
        action_result_path=paths["action_result"],
        capture_sidecar_path=paths["capture_sidecar"],
        photo_path=paths["photo"],
        relay_off_receipt_path=paths["relay_off_receipt"],
    )
    observation_root = _require_mapping(
        root.get("offline_visual_review"), label="offline_visual_review"
    )
    if set(observation_root) != {
        "reviewer",
        "method",
        "review_confidence",
        "camera_visible_white_field",
        "full_display_active_area_visible_in_frame",
        "obvious_colour_blocks_or_colour_blotches_visible",
        "obvious_gross_horizontal_stripes_visible",
        "obvious_gross_vertical_stripes_visible",
        "obvious_center_seam_anomaly_visible",
        "limitations_observed",
    }:
        raise CameraVisibleCleanWhiteReviewError("offline_visual_review keys differ")
    limitations = observation_root.get("limitations_observed")
    if not isinstance(limitations, list):
        raise CameraVisibleCleanWhiteReviewError(
            "offline_visual_review limitations must be an array"
        )
    observation = _validated_observation(
        reviewer=observation_root.get("reviewer"),
        method=observation_root.get("method"),
        confidence=observation_root.get("review_confidence"),
        camera_visible_white_field=observation_root.get("camera_visible_white_field"),
        obvious_colour_blocks_or_blotches_visible=observation_root.get(
            "obvious_colour_blocks_or_colour_blotches_visible"
        ),
        obvious_gross_horizontal_stripes_visible=observation_root.get(
            "obvious_gross_horizontal_stripes_visible"
        ),
        obvious_gross_vertical_stripes_visible=observation_root.get(
            "obvious_gross_vertical_stripes_visible"
        ),
        obvious_center_seam_anomaly_visible=observation_root.get(
            "obvious_center_seam_anomaly_visible"
        ),
        limitations_observed=limitations,
    )
    if observation_root.get("full_display_active_area_visible_in_frame") is not True:
        raise CameraVisibleCleanWhiteReviewError(
            "review does not affirm full active-area visibility"
        )
    expected = _build_record(
        output_path=review_path,
        action_result_path=paths["action_result"],
        capture_sidecar_path=paths["capture_sidecar"],
        photo_path=paths["photo"],
        relay_off_receipt_path=paths["relay_off_receipt"],
        reviewed_at=root.get("reviewed_at"),
        observation=observation,
        source=source,
    )
    if root != expected:
        differing = sorted(
            key for key, value in expected.items() if root.get(key) != value
        )
        raise CameraVisibleCleanWhiteReviewError(
            "review binding or qualification fields differ: " + ", ".join(differing)
        )
    return dict(root)


def _presence(value: str) -> bool:
    return value == "present"


def _yes_no(value: str) -> bool:
    return value == "yes"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", allow_abbrev=False)
    build.add_argument("--action-result", type=Path, required=True)
    build.add_argument("--capture-sidecar", type=Path, required=True)
    build.add_argument("--photo", type=Path, required=True)
    build.add_argument("--relay-off-receipt", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--reviewed-at", required=True)
    build.add_argument("--reviewer", required=True)
    build.add_argument("--method", required=True)
    build.add_argument("--confidence", choices=sorted(CONFIDENCES), required=True)
    build.add_argument(
        "--camera-visible-white-field", choices=("yes", "no"), required=True
    )
    build.add_argument(
        "--obvious-colour-blocks-or-blotches",
        choices=("absent", "present"),
        required=True,
    )
    build.add_argument(
        "--obvious-gross-horizontal-stripes",
        choices=("absent", "present"),
        required=True,
    )
    build.add_argument(
        "--obvious-gross-vertical-stripes",
        choices=("absent", "present"),
        required=True,
    )
    build.add_argument(
        "--obvious-center-seam-anomaly",
        choices=("absent", "present"),
        required=True,
    )
    build.add_argument("--limitation", action="append", default=[])
    validate = subparsers.add_parser("validate", allow_abbrev=False)
    validate.add_argument("--review", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            record = validate_review(args.review)
        else:
            record = create_review(
                action_result_path=args.action_result,
                capture_sidecar_path=args.capture_sidecar,
                photo_path=args.photo,
                relay_off_receipt_path=args.relay_off_receipt,
                output_path=args.output,
                reviewed_at=args.reviewed_at,
                reviewer=args.reviewer,
                method=args.method,
                confidence=args.confidence,
                camera_visible_white_field=_yes_no(args.camera_visible_white_field),
                obvious_colour_blocks_or_blotches_visible=_presence(
                    args.obvious_colour_blocks_or_blotches
                ),
                obvious_gross_horizontal_stripes_visible=_presence(
                    args.obvious_gross_horizontal_stripes
                ),
                obvious_gross_vertical_stripes_visible=_presence(
                    args.obvious_gross_vertical_stripes
                ),
                obvious_center_seam_anomaly_visible=_presence(
                    args.obvious_center_seam_anomaly
                ),
                limitations_observed=args.limitation,
            )
    except (CameraVisibleCleanWhiteReviewError, OSError) as error:
        print(f"camera-visible clean-white review error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
