#!/usr/bin/env python3
"""Seal the V2 atlas, OFF evidence, analysis, and white containment.

This builder is offline-only and writes once with O_EXCL.  It does not infer
electrical OFF from a camera image: exact relay OFF query receipts are bound
separately and remain commanded-state rather than load-side voltage proof.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

from tools import mf1750_camera_capture_evidence as camera
from tools import mf1750_runtime_lut_same_r20_parity_4x8_v2_once as once
from tools import mf1750_runtime_lut_same_r20_parity_4x8_v2_pack as pack
from tools import mf1750_same_r20_position_balanced_4x8_analyzer as analyzer


SCHEMA_VERSION = 1
KIND = "mf1750-same-r20-position-balanced-4x8-evidence-bundle"
INTEGRITY_ALGORITHM = analyzer.INTEGRITY_ALGORITHM


class PositionBalancedBundleError(RuntimeError):
    """Raised when one immutable input or output contract differs."""


def _canonical(value: Any) -> bytes:
    return analyzer.canonical_json(value)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read(path: Path, *, label: str) -> bytes:
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise PositionBalancedBundleError(
                f"{label} must be a regular non-symlink file"
            )
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise PositionBalancedBundleError(f"cannot read {label}: {exc}") from exc
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or len(payload) != after.st_size:
        raise PositionBalancedBundleError(f"{label} changed while read")
    return payload


def _load(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    payload = _read(path, label=label)
    try:
        root = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=analyzer._reject_duplicate_keys,  # noqa: SLF001
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {item}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise PositionBalancedBundleError(f"{label} is invalid JSON: {exc}") from exc
    if not isinstance(root, dict):
        raise PositionBalancedBundleError(f"{label} root must be an object")
    return payload, root


def _verify_standard_integrity(root: Mapping[str, Any], *, label: str) -> str:
    integrity = root.get("integrity")
    if not isinstance(integrity, Mapping):
        raise PositionBalancedBundleError(f"{label} integrity is missing")
    body = dict(root)
    body.pop("integrity", None)
    observed = _sha(_canonical(body))
    if (
        integrity.get("algorithm") != INTEGRITY_ALGORITHM
        or integrity.get("sha256") != observed
    ):
        raise PositionBalancedBundleError(f"{label} integrity differs")
    return observed


def _verify_relay_receipt(path: Path, *, label: str) -> dict[str, Any]:
    payload, root = _load(path, label=label)
    integrity = root.get("integrity")
    if not isinstance(integrity, Mapping):
        raise PositionBalancedBundleError(f"{label} integrity is missing")
    body = dict(root)
    body.pop("integrity", None)
    observed = _sha(_canonical(body))
    expected_root_keys = {
        "schema_version",
        "kind",
        "queried_at",
        "rebind",
        "expected_identity",
        "channel",
        "commanded_state",
        "off_gate_passed",
        "electrical_state_proven",
        "contact_switch_performed",
        "on_authorized",
        "automatic_retry_performed",
        "output_write_contract",
        "integrity",
    }
    if set(root) != expected_root_keys:
        raise PositionBalancedBundleError(f"{label} receipt keys differ")
    expected_identity = root.get("expected_identity")
    rebind = root.get("rebind")
    expected_identity_keys = {
        "model",
        "vid",
        "pid",
        "serial_number",
        "port",
        "pnp_instance_id",
        "usb_location",
    }
    if (
        not isinstance(expected_identity, Mapping)
        or set(expected_identity) != expected_identity_keys
        or not all(
            isinstance(expected_identity.get(field), str)
            and bool(expected_identity.get(field))
            for field in expected_identity_keys
        )
        or not isinstance(rebind, Mapping)
        or set(rebind) != {"path", "bytes", "sha256", "rebind_id", "canonical_sha256"}
    ):
        raise PositionBalancedBundleError(f"{label} relay binding differs")
    for field in ("sha256", "canonical_sha256"):
        value = rebind.get(field)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise PositionBalancedBundleError(f"{label} rebind {field} is invalid")
    if (
        set(integrity) != {"algorithm", "canonical_sha256", "scope"}
        or integrity.get("algorithm") != "sha256"
        or integrity.get("canonical_sha256") != observed
        or not isinstance(integrity.get("scope"), str)
        or not integrity.get("scope")
        or root.get("schema_version") != 1
        or root.get("kind") != "mf17506-zave-relay-exact-bound-query-receipt"
        or root.get("channel") != 1
        or root.get("commanded_state") != "OFF"
        or root.get("off_gate_passed") is not True
        or root.get("electrical_state_proven") is not False
        or root.get("contact_switch_performed") is not False
        or root.get("on_authorized") is not False
        or root.get("automatic_retry_performed") is not False
        or root.get("output_write_contract") != "O_EXCL"
    ):
        raise PositionBalancedBundleError(f"{label} is not an exact OFF receipt")
    _parse_timestamp(root.get("queried_at"), label=f"{label}.queried_at")
    return {
        "path": path.as_posix(),
        "file_sha256": _sha(payload),
        "canonical_sha256": observed,
        "queried_at": root.get("queried_at"),
        "commanded_state": "OFF",
        "electrical_state_proven": False,
        "expected_identity": dict(expected_identity),
        "rebind": dict(rebind),
    }


def _validate_shared_relay_receipts(
    receipts: Sequence[Mapping[str, Any]],
) -> None:
    if len(receipts) != 3:
        raise PositionBalancedBundleError(
            "white, atlas, and post-white require three exact OFF receipts"
        )
    first = receipts[0]
    if any(
        receipt.get("expected_identity") != first.get("expected_identity")
        or receipt.get("rebind") != first.get("rebind")
        for receipt in receipts[1:]
    ):
        raise PositionBalancedBundleError(
            "white, atlas, and post-white OFF receipts do not bind the same relay"
        )
    file_hashes = [receipt.get("file_sha256") for receipt in receipts]
    if len(set(file_hashes)) != len(file_hashes):
        raise PositionBalancedBundleError(
            "white, atlas, and post-white require three distinct exact OFF receipts"
        )


def _parse_timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise PositionBalancedBundleError(f"{label} is missing")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        result = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise PositionBalancedBundleError(f"{label} is invalid") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise PositionBalancedBundleError(f"{label} must be timezone-aware")
    return result


def _validate_action(path: Path) -> dict[str, Any]:
    payload, root = _load(path, label="V2 action result")
    canonical_integrity = _verify_standard_integrity(root, label="V2 action result")
    expected = pack.build_report()["actions"][0]
    action = root.get("action")
    terminal = root.get("terminal_report")
    if (
        not isinstance(action, Mapping)
        or not isinstance(terminal, Mapping)
        or root.get("outcome") != "complete_pass"
        or root.get("firmware_sha256") != once.FIRMWARE_SHA256
        or root.get("visible_refreshes") != 1
        or root.get("no_retry") is not True
        or root.get("no_recovery") is not True
        or root.get("no_autochain") is not True
        or action.get("action_id") != expected["action_id"]
        or action.get("descriptor_id") != expected["descriptor_id"]
        or action.get("frame_sha256") != expected["frame"]["sha256"]
        or action.get("ordinal") != expected["ordinal"]
        or action.get("role") != expected["role"]
        or terminal.get("campaign_id") != pack.CAMPAIGN_ID
        or terminal.get("contract_id") != pack.build_report()["contract_id"]
        or terminal.get("terminal_state") != "COMPLETE"
        or terminal.get("driver_call_count_for_action") != 1
    ):
        raise PositionBalancedBundleError("V2 action result binding differs")
    created_at = root.get("created_at")
    _parse_timestamp(created_at, label="V2 action result.created_at")
    return {
        "path": path.as_posix(),
        "file_sha256": _sha(payload),
        "canonical_integrity_sha256": canonical_integrity,
        "action_id": expected["action_id"],
        "descriptor_id": action.get("descriptor_id"),
        "frame_sha256": action.get("frame_sha256"),
        "ordinal": action.get("ordinal"),
        "role": action.get("role"),
        "campaign_id": terminal.get("campaign_id"),
        "test_id": terminal.get("test_id"),
        "contract_id": terminal.get("contract_id"),
        "firmware_sha256": root.get("firmware_sha256"),
        "boot_nonce": root.get("boot_nonce"),
        "created_at": created_at,
        "outcome": "complete_pass",
    }


def _validate_external_white(path: Path, *, label: str) -> dict[str, Any]:
    payload, root = _load(path, label=label)
    canonical_integrity = _verify_standard_integrity(root, label=label)
    terminal = root.get("terminal_report")
    action = root.get("action")
    role = action.get("role") if isinstance(action, Mapping) else None
    if (
        root.get("outcome") != "complete_pass"
        or root.get("visible_refreshes") != 1
        or root.get("no_retry") is not True
        or root.get("no_recovery") is not True
        or root.get("no_autochain") is not True
        or not isinstance(role, str)
        or not any(token in role.upper() for token in ("WHITE", "FACTORY_OTP"))
        or not isinstance(terminal, Mapping)
        or terminal.get("terminal_state") != "COMPLETE"
        or terminal.get("driver_call_count_for_action") != 1
    ):
        raise PositionBalancedBundleError(f"{label} is not one terminal white action")
    created_at = root.get("created_at")
    _parse_timestamp(created_at, label=f"{label}.created_at")
    return {
        "path": path.as_posix(),
        "file_sha256": _sha(payload),
        "canonical_integrity_sha256": canonical_integrity,
        "action_id": action.get("action_id"),
        "descriptor_id": action.get("descriptor_id"),
        "frame_sha256": action.get("frame_sha256"),
        "ordinal": action.get("ordinal"),
        "role": role,
        "campaign_id": terminal.get("campaign_id"),
        "test_id": terminal.get("test_id"),
        "contract_id": terminal.get("contract_id"),
        "firmware_sha256": root.get("firmware_sha256"),
        "boot_nonce": root.get("boot_nonce"),
        "created_at": created_at,
    }


def _capture_time(root: Mapping[str, Any], *, label: str) -> datetime:
    timing = root.get("capture_timing")
    text = timing.get("completed_at") if isinstance(timing, Mapping) else None
    if not isinstance(text, str):
        raise PositionBalancedBundleError(f"{label} completion time is missing")
    return _parse_timestamp(text, label=f"{label} completion time")


def _validate_capture_set(
    captures: Sequence[Path],
    photos: Sequence[Path],
    *,
    label: str,
    expected_action: Mapping[str, Any],
    off_receipt: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], datetime, datetime]:
    if len(captures) != 3 or len(photos) != 3:
        raise PositionBalancedBundleError(f"{label} requires three captures/photos")
    records: list[dict[str, Any]] = []
    completed: list[datetime] = []
    setup: dict[str, Any] | None = None
    capture_ids: set[str] = set()
    photo_hashes: set[str] = set()
    receipt_time = _parse_timestamp(
        off_receipt.get("queried_at"), label=f"{label} OFF receipt time"
    )
    action_time = _parse_timestamp(
        expected_action.get("created_at"), label=f"{label} action time"
    )
    if action_time > receipt_time:
        raise PositionBalancedBundleError(
            f"{label} OFF receipt predates its bound action result"
        )
    for index, (capture_path, photo_path) in enumerate(
        zip(captures, photos, strict=True), 1
    ):
        try:
            root = camera.validate_capture_evidence(capture_path)
        except camera.CameraCaptureEvidenceError as exc:
            raise PositionBalancedBundleError(
                f"{label} capture {index} failed camera sidecar validation: {exc}"
            ) from exc
        capture_payload = _read(capture_path, label=f"{label} capture {index}")
        photo_payload = _read(photo_path, label=f"{label} photo {index}")
        photo = root.get("photo")
        camera_record = root.get("camera")
        coverage = root.get("coverage")
        action_record = root.get("action_result")
        if (
            root.get("kind") != "mf1750-camera-capture-evidence"
            or root.get("capture_binding") != camera.BINDING_LOCKED_RETAINED
            or root.get("output_write_contract") != "O_EXCL"
            or not isinstance(photo, Mapping)
            or photo.get("sha256") != _sha(photo_payload)
            or not isinstance(camera_record, Mapping)
            or not isinstance(coverage, Mapping)
            or coverage.get("full_panel_visible") is not True
            or coverage.get("full_panel_uncropped") is not True
            or coverage.get("scope") != camera.COVERAGE_FULL
            or not isinstance(action_record, Mapping)
            or action_record.get("file_sha256") != expected_action.get("file_sha256")
        ):
            raise PositionBalancedBundleError(f"{label} capture {index} differs")
        try:
            bound_photo = camera._resolve_evidence_path(  # noqa: SLF001
                photo.get("path"),
                sidecar_path=capture_path,
                label=f"{label} capture {index} photo.path",
            )
        except camera.CameraCaptureEvidenceError as exc:
            raise PositionBalancedBundleError(str(exc)) from exc
        if bound_photo.resolve() != Path(photo_path).resolve():
            raise PositionBalancedBundleError(
                f"{label} capture {index} is not bound to the supplied photo path"
            )
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
            "frame_sha256",
        ):
            if root.get(field) != expected_action.get(field):
                raise PositionBalancedBundleError(
                    f"{label} capture {index} {field} differs from bound action"
                )
        before = camera_record.get("effective_settings_before_frame")
        after = camera_record.get("effective_settings_after_frame")
        if not isinstance(before, Mapping) or dict(before) != dict(after or {}):
            raise PositionBalancedBundleError(
                f"{label} capture {index} effective camera settings changed"
            )
        this_setup = {
            "camera_id": camera_record.get("camera_id"),
            "camera_instance_id": camera_record.get("instance_id"),
            "camera_index": camera_record.get("index"),
            "backend": camera_record.get("backend"),
            "mount_id": coverage.get("mount_id"),
            "requested_settings": dict(camera_record.get("requested_settings", {})),
            "effective_settings": dict(before),
        }
        if setup is None:
            setup = this_setup
        if this_setup != setup:
            raise PositionBalancedBundleError(f"{label} camera lock changed")
        timing = root.get("capture_timing")
        if not isinstance(timing, Mapping):
            raise PositionBalancedBundleError(f"{label} capture timing is missing")
        started = _parse_timestamp(
            timing.get("started_at"), label=f"{label} capture {index} start time"
        )
        frame_time = _parse_timestamp(
            timing.get("frame_retrieved_at"),
            label=f"{label} capture {index} frame time",
        )
        instant = _capture_time(root, label=f"{label} capture {index}")
        if not receipt_time <= started <= frame_time <= instant:
            raise PositionBalancedBundleError(
                f"{label} capture {index} is not after the exact OFF receipt"
            )
        completed.append(instant)
        capture_id = root.get("capture_id")
        photo_sha256 = _sha(photo_payload)
        if (
            not isinstance(capture_id, str)
            or capture_id in capture_ids
            or photo_sha256 in photo_hashes
        ):
            raise PositionBalancedBundleError(
                f"{label} captures must have distinct IDs and photo bytes"
            )
        capture_ids.add(capture_id)
        photo_hashes.add(photo_sha256)
        records.append(
            {
                "capture_path": capture_path.as_posix(),
                "capture_file_sha256": _sha(capture_payload),
                "capture_id": capture_id,
                "capture_binding": camera.BINDING_LOCKED_RETAINED,
                "photo_path": photo_path.as_posix(),
                "photo_sha256": photo_sha256,
                "completed_at": instant.isoformat(),
                "mount_id": setup["mount_id"],
                "bound_action_id": expected_action.get("action_id"),
                "off_receipt_canonical_sha256": off_receipt.get("canonical_sha256"),
            }
        )
    if completed != sorted(completed) or len(set(completed)) != len(completed):
        raise PositionBalancedBundleError(f"{label} captures are not chronological")
    if setup is None:
        raise PositionBalancedBundleError(f"{label} capture set is empty")
    return records, setup, completed[0], completed[-1]


def _validate_post_white_clean(
    path: Path, *, post_white: Mapping[str, Any]
) -> dict[str, Any]:
    payload, root = _load(path, label="post-white clean analysis")
    canonical_integrity = _verify_standard_integrity(
        root, label="post-white clean analysis"
    )
    analysis = root.get("analysis")
    bindings = root.get("bindings")
    if (
        root.get("kind") != "mf1750-camera-post-capture-analysis"
        or not isinstance(analysis, Mapping)
        or analysis.get("verdict") != "PASS"
        or not isinstance(bindings, Mapping)
    ):
        raise PositionBalancedBundleError("post-white clean visual gate did not pass")
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
        "frame_sha256",
    ):
        if root.get(field) != post_white.get(field):
            raise PositionBalancedBundleError(
                f"post-white clean analysis {field} differs from post-white action"
            )
    action_binding = bindings.get("action_result")
    capture_binding = bindings.get("capture_sidecar")
    if not isinstance(action_binding, Mapping) or not isinstance(
        capture_binding, Mapping
    ):
        raise PositionBalancedBundleError(
            "post-white clean analysis bindings are incomplete"
        )
    if action_binding.get("file_sha256") != post_white.get(
        "file_sha256"
    ) or action_binding.get("canonical_integrity_sha256") != post_white.get(
        "canonical_integrity_sha256"
    ):
        raise PositionBalancedBundleError(
            "post-white clean analysis action-result binding differs"
        )
    try:
        bound_action_path = camera._resolve_evidence_path(  # noqa: SLF001
            action_binding.get("path"),
            sidecar_path=path,
            label="post-white clean action_result.path",
        )
        bound_capture_path = camera._resolve_evidence_path(  # noqa: SLF001
            capture_binding.get("path"),
            sidecar_path=path,
            label="post-white clean capture_sidecar.path",
        )
        clean_capture = camera.validate_capture_evidence(bound_capture_path)
    except camera.CameraCaptureEvidenceError as exc:
        raise PositionBalancedBundleError(str(exc)) from exc
    if (
        bound_action_path.resolve() != Path(post_white["path"]).resolve()
        or _sha(_read(bound_action_path, label="post-white bound action"))
        != post_white.get("file_sha256")
        or clean_capture.get("action_id") != post_white.get("action_id")
        or clean_capture.get("role") != post_white.get("role")
        or clean_capture.get("action_result", {}).get("file_sha256")
        != post_white.get("file_sha256")
    ):
        raise PositionBalancedBundleError(
            "post-white clean capture is not bound to the post-white action"
        )
    clean_capture_payload = _read(
        bound_capture_path, label="post-white clean capture sidecar"
    )
    clean_integrity = clean_capture.get("integrity")
    if (
        capture_binding.get("file_sha256") != _sha(clean_capture_payload)
        or capture_binding.get("capture_id") != clean_capture.get("capture_id")
        or capture_binding.get("capture_binding")
        != clean_capture.get("capture_binding")
        or not isinstance(clean_integrity, Mapping)
        or capture_binding.get("canonical_integrity_sha256")
        != clean_integrity.get("sha256")
    ):
        raise PositionBalancedBundleError(
            "post-white clean capture-sidecar binding differs"
        )
    timing = clean_capture.get("capture_timing")
    if not isinstance(timing, Mapping):
        raise PositionBalancedBundleError("post-white clean capture timing is missing")
    capture_started_at = timing.get("started_at")
    capture_frame_at = timing.get("frame_retrieved_at")
    capture_completed_at = timing.get("completed_at")
    capture_started = _parse_timestamp(
        capture_started_at, label="post-white clean capture start time"
    )
    capture_frame = _parse_timestamp(
        capture_frame_at, label="post-white clean capture frame time"
    )
    capture_completed = _parse_timestamp(
        capture_completed_at, label="post-white clean capture completion time"
    )
    if not capture_started <= capture_frame <= capture_completed:
        raise PositionBalancedBundleError(
            "post-white clean capture timing is not chronological"
        )
    return {
        "path": path.as_posix(),
        "file_sha256": _sha(payload),
        "canonical_integrity_sha256": canonical_integrity,
        "analysis_id": root.get("analysis_id"),
        "verdict": "PASS",
        "action_id": post_white.get("action_id"),
        "capture_id": clean_capture.get("capture_id"),
        "capture_started_at": capture_started_at,
        "capture_completed_at": capture_completed_at,
    }


def _validate_post_white_off_chronology(
    *,
    post_white: Mapping[str, Any],
    post_white_off: Mapping[str, Any],
    clean: Mapping[str, Any],
) -> None:
    action_time = _parse_timestamp(
        post_white.get("created_at"), label="post-white action result.created_at"
    )
    receipt_time = _parse_timestamp(
        post_white_off.get("queried_at"), label="post-white OFF receipt.queried_at"
    )
    capture_started = _parse_timestamp(
        clean.get("capture_started_at"),
        label="post-white clean capture start time",
    )
    capture_completed = _parse_timestamp(
        clean.get("capture_completed_at"),
        label="post-white clean capture completion time",
    )
    if not action_time <= receipt_time <= capture_started <= capture_completed:
        raise PositionBalancedBundleError(
            "post-white OFF receipt must follow the post-white action and precede "
            "the post-white clean capture"
        )


def build_bundle(
    *,
    pre_white_result: Path,
    white_off_receipt: Path,
    white_captures: Sequence[Path],
    white_photos: Sequence[Path],
    action_result: Path,
    atlas_off_receipt: Path,
    atlas_captures: Sequence[Path],
    atlas_photos: Sequence[Path],
    analysis_path: Path,
    post_white_result: Path,
    post_white_off_receipt: Path,
    post_white_clean_analysis: Path,
) -> dict[str, Any]:
    pre_white = _validate_external_white(pre_white_result, label="pre-white result")
    post_white = _validate_external_white(post_white_result, label="post-white result")
    action = _validate_action(action_result)
    white_off = _verify_relay_receipt(white_off_receipt, label="white OFF receipt")
    atlas_off = _verify_relay_receipt(atlas_off_receipt, label="atlas OFF receipt")
    post_white_off = _verify_relay_receipt(
        post_white_off_receipt, label="post-white OFF receipt"
    )
    _validate_shared_relay_receipts((white_off, atlas_off, post_white_off))
    white_set, white_setup, _white_first, white_last = _validate_capture_set(
        white_captures,
        white_photos,
        label="white OFF",
        expected_action=pre_white,
        off_receipt=white_off,
    )
    atlas_set, atlas_setup, _atlas_first, atlas_last = _validate_capture_set(
        atlas_captures,
        atlas_photos,
        label="retained atlas OFF",
        expected_action=action,
        off_receipt=atlas_off,
    )
    if white_setup != atlas_setup:
        raise PositionBalancedBundleError(
            "white and retained-atlas camera instance, mount, or locked settings differ"
        )
    if white_last > _parse_timestamp(
        action.get("created_at"), label="V2 action result.created_at"
    ):
        raise PositionBalancedBundleError(
            "V2 action result predates completion of the white OFF capture set"
        )
    if atlas_last > _parse_timestamp(
        post_white.get("created_at"), label="post-white result.created_at"
    ):
        raise PositionBalancedBundleError(
            "post-white action result predates retained-atlas capture completion"
        )
    analysis_payload, analysis = _load(analysis_path, label="4x8 analysis")
    _verify_standard_integrity(analysis, label="4x8 analysis")
    if (
        analysis.get("kind") != analyzer.KIND
        or analysis.get("campaign_id") != pack.CAMPAIGN_ID
        or analysis.get("contract_id") != pack.build_report()["contract_id"]
        or [item["sha256"] for item in analysis["photo_sets"]["white"]]
        != [item["photo_sha256"] for item in white_set]
        or [item["sha256"] for item in analysis["photo_sets"]["atlas"]]
        != [item["photo_sha256"] for item in atlas_set]
    ):
        raise PositionBalancedBundleError("4x8 analysis input binding differs")
    clean = _validate_post_white_clean(post_white_clean_analysis, post_white=post_white)
    _validate_post_white_off_chronology(
        post_white=post_white,
        post_white_off=post_white_off,
        clean=clean,
    )
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "campaign_id": pack.CAMPAIGN_ID,
        "contract_id": pack.build_report()["contract_id"],
        "firmware_sha256": once.FIRMWARE_SHA256,
        "external_containment": {
            "pre_white": pre_white,
            "white_off_receipt": white_off,
            "post_white": post_white,
            "post_white_off_receipt": post_white_off,
            "post_white_clean_analysis": clean,
        },
        "atlas_action": action,
        "white_off_captures": white_set,
        "retained_atlas_off_captures": atlas_set,
        "locked_camera_setup": white_setup,
        "position_balanced_analysis": {
            "path": analysis_path.as_posix(),
            "file_sha256": _sha(analysis_payload),
            "analysis_id": analysis.get("analysis_id"),
            "classification": analysis.get("classification"),
            "absolute_colour_proven": False,
            "electrical_controller_equivalence_proven": False,
        },
        "off_evidence_boundary": {
            "relay_commanded_off_proven": True,
            "load_side_electrical_off_proven": bool(
                white_off["electrical_state_proven"]
                and atlas_off["electrical_state_proven"]
                and post_white_off["electrical_state_proven"]
            ),
        },
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "output_write_contract": "O_EXCL",
    }
    result["bundle_id"] = _sha(_canonical(result))
    result["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": _sha(_canonical(result)),
    }
    return result


def write_new(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(
            value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
        ).encode("utf-8")
        + b"\n"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise PositionBalancedBundleError(f"output already exists: {path}") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--pre-white-result", type=Path, required=True)
    parser.add_argument("--white-off-receipt", type=Path, required=True)
    parser.add_argument("--white-capture", type=Path, action="append", required=True)
    parser.add_argument("--white-photo", type=Path, action="append", required=True)
    parser.add_argument("--action-result", type=Path, required=True)
    parser.add_argument("--atlas-off-receipt", type=Path, required=True)
    parser.add_argument("--atlas-capture", type=Path, action="append", required=True)
    parser.add_argument("--atlas-photo", type=Path, action="append", required=True)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--post-white-result", type=Path, required=True)
    parser.add_argument("--post-white-off-receipt", type=Path, required=True)
    parser.add_argument("--post-white-clean-analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        value = build_bundle(
            pre_white_result=args.pre_white_result,
            white_off_receipt=args.white_off_receipt,
            white_captures=args.white_capture,
            white_photos=args.white_photo,
            action_result=args.action_result,
            atlas_off_receipt=args.atlas_off_receipt,
            atlas_captures=args.atlas_capture,
            atlas_photos=args.atlas_photo,
            analysis_path=args.analysis,
            post_white_result=args.post_white_result,
            post_white_off_receipt=args.post_white_off_receipt,
            post_white_clean_analysis=args.post_white_clean_analysis,
        )
        write_new(args.output, value)
    except PositionBalancedBundleError as exc:
        print(f"same-R20 4x8 bundle error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
