#!/usr/bin/env python3
"""Seal the complete offline evidence aggregate for Batch-3 true-R20 HOLD.

The builder performs no device, camera, network, serial, relay, flash, reset,
or display operation.  It deep-validates four completed action results, the
pre/after synchronized photographs for every stage, four static photo gates,
four refresh-video sidecars and video gates, one sealed repeat-noise baseline,
the terminal 60-patch factory-white gate, and the sealed Batch-1 and Batch-2
prerequisites.  Its conclusions remain camera-relative and ROI-sampled.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any

from tools import mf1750_camera_capture_evidence as camera
from tools import mf1750_camera_video_capture_evidence as video_evidence
from tools import mf1750_factory_white_reference_photo_gate as white_gate
from tools import (
    mf1750_recipe_position_permutation_batch3_prerequisite as batch2_prerequisite,
)
from tools import mf1750_runtime_lut_true_r20_partial_hold_v1_once as true_once
from tools import mf1750_runtime_lut_true_r20_partial_hold_v1_pack as true_pack
from tools import mf1750_same_r20_parity_evidence_bundle as batch1_builder
from tools import mf1750_true_r20_hold_photo_gate as static_gate
from tools import mf1750_true_r20_hold_video_gate as video_gate


SCHEMA_VERSION = 1
KIND = "mf1750-true-r20-partial-hold-evidence-bundle-v1"
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
STAGES = ("A", "B", "C", "WHITE")
MINIMUM_VIDEO_DURATION_SECONDS = 25.0
EXPECTED_PROTECTED = {
    "A": (),
    "B": ("A",),
    "C": ("A", "B"),
    "WHITE": (),
}
EXPECTED_NEW = {"A": ("A",), "B": ("B",), "C": ("C",), "WHITE": ()}
EXPECTED_WHITE = {
    "A": ("B", "C"),
    "B": ("C",),
    "C": (),
    "WHITE": ("A", "B", "C"),
}


class TrueR20PartialHoldEvidenceBundleError(RuntimeError):
    """Raised when one aggregate input or cross-binding differs."""


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
        raise TrueR20PartialHoldEvidenceBundleError(
            f"record contains a non-canonical JSON value: {exc}"
        ) from exc


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TrueR20PartialHoldEvidenceBundleError(f"{label} must be an object")
    return value


def _sha(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or camera.SHA256_RE.fullmatch(value) is None:
        raise TrueR20PartialHoldEvidenceBundleError(f"{label} is not lowercase SHA-256")
    return value


def _number(value: Any, *, label: str, nonnegative: bool = False) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise TrueR20PartialHoldEvidenceBundleError(f"{label} must be finite")
    result = float(value)
    if nonnegative and result < 0:
        raise TrueR20PartialHoldEvidenceBundleError(f"{label} must be nonnegative")
    return result


def _time(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise TrueR20PartialHoldEvidenceBundleError(f"{label} must be a timestamp")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise TrueR20PartialHoldEvidenceBundleError(f"{label} is not ISO-8601") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise TrueR20PartialHoldEvidenceBundleError(
            f"{label} must include a UTC offset"
        )
    return result


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _load_sealed(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        payload, root = camera._load_strict_json(path, label=label)  # noqa: SLF001
    except camera.CameraCaptureEvidenceError as exc:
        raise TrueR20PartialHoldEvidenceBundleError(str(exc)) from exc
    integrity = _mapping(root.get("integrity"), label=f"{label}.integrity")
    if set(integrity) != {"algorithm", "sha256"}:
        raise TrueR20PartialHoldEvidenceBundleError(f"{label} integrity keys differ")
    if integrity.get("algorithm") != INTEGRITY_ALGORITHM:
        raise TrueR20PartialHoldEvidenceBundleError(
            f"{label} integrity algorithm differs"
        )
    declared = _sha(integrity.get("sha256"), label=f"{label}.integrity.sha256")
    unsigned = dict(root)
    unsigned.pop("integrity", None)
    if _sha256_bytes(_canonical_json(unsigned)) != declared:
        raise TrueR20PartialHoldEvidenceBundleError(
            f"{label} canonical integrity differs"
        )
    return payload, dict(root)


def _binding(path: Path, payload: bytes, root: Mapping[str, Any]) -> dict[str, Any]:
    integrity = _mapping(root.get("integrity"), label=f"{path}.integrity")
    return {
        "path": str(path),
        "file_sha256": _sha256_bytes(payload),
        "canonical_integrity_sha256": integrity["sha256"],
    }


def _load_batch1(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        root, file_sha256 = true_once._load_batch1_evidence(path)  # noqa: SLF001
    except true_once.base.runner.RecheckError as exc:
        raise TrueR20PartialHoldEvidenceBundleError(str(exc)) from exc
    integrity = _mapping(root.get("integrity"), label="Batch-1 integrity")
    return root, {
        "path": str(path),
        "file_sha256": file_sha256,
        "canonical_integrity_sha256": integrity["sha256"],
        "campaign_id": root["campaign_id"],
        "contract_id": root["contract_id"],
        "requirements_id": true_pack.BATCH1_EVIDENCE_REQUIREMENTS_ID,
    }


def _validate_batch2(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        return batch2_prerequisite.validate(path)
    except batch2_prerequisite.Batch3PrerequisiteError as exc:
        raise TrueR20PartialHoldEvidenceBundleError(str(exc)) from exc


def _validate_action_results(
    paths: Sequence[Path],
    batch1_binding: Mapping[str, Any],
    batch2_binding: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    if len(paths) != 4:
        raise TrueR20PartialHoldEvidenceBundleError(
            "exactly four Batch-3 action results are required"
        )
    expected_actions = true_once.base.runner.ACTIONS
    records: list[dict[str, Any]] = []
    boot_nonce: str | None = None
    prior_sha256: str | None = None
    prior_created: datetime | None = None
    for ordinal, raw_path in enumerate(paths, 1):
        path = Path(raw_path)
        payload, root = _load_sealed(path, label=f"action result ordinal {ordinal}")
        try:
            _payload, _root, identity = camera._load_action_result(path)  # noqa: SLF001
        except camera.CameraCaptureEvidenceError as exc:
            raise TrueR20PartialHoldEvidenceBundleError(str(exc)) from exc
        expected = expected_actions[ordinal - 1]
        terminal = _mapping(
            root.get("terminal_report"),
            label=f"action result ordinal {ordinal}.terminal_report",
        )
        if (
            root.get("schema_version") != 1
            or root.get("kind") != f"{true_pack.DEVICE_KIND_PREFIX}-result"
            or root.get("firmware_sha256") != true_once.FIRMWARE_BIN_SHA256
            or root.get("outcome") != "complete_pass"
            or root.get("visible_refreshes") != 1
            or root.get("no_retry") is not True
            or root.get("no_recovery") is not True
            or root.get("no_autochain") is not True
            or identity["campaign_id"] != true_pack.CAMPAIGN_ID
            or identity["test_id"] != true_pack.TEST_ID
            or identity["contract_id"] != true_pack.CONTRACT_ID
            or identity["ordinal"] != ordinal
            or identity["action_id"] != expected["action_id"]
            or identity["descriptor_id"] != expected["descriptor_id"]
            or identity["role"] != expected["role"]
            or identity["frame_sha256"] != expected["frame_sha256"]
            or terminal.get("driver_called") is not True
            or terminal.get("driver_call_count_for_action") != 1
        ):
            raise TrueR20PartialHoldEvidenceBundleError(
                f"action result ordinal {ordinal} identity or terminal differs"
            )
        current_boot = identity["boot_nonce"]
        try:
            true_once.v3._validate_complete_report(  # noqa: SLF001
                terminal, ordinal, current_boot
            )
        except true_once.base.runner.RecheckError as exc:
            raise TrueR20PartialHoldEvidenceBundleError(
                f"action ordinal {ordinal} COMPLETE report differs: {exc}"
            ) from exc
        if boot_nonce is None:
            boot_nonce = current_boot
        elif current_boot != boot_nonce:
            raise TrueR20PartialHoldEvidenceBundleError(
                "Batch-3 action boot continuity differs"
            )
        created = _time(
            identity["action_result_created_at"],
            label=f"action result ordinal {ordinal}.created_at",
        )
        if prior_created is not None and created <= prior_created:
            raise TrueR20PartialHoldEvidenceBundleError(
                "Batch-3 action result times are not strictly increasing"
            )
        prior_created = created
        local_prior = root.get("prior_local_evidence")
        if ordinal == 1:
            if local_prior is not None:
                raise TrueR20PartialHoldEvidenceBundleError(
                    "action ordinal 1 unexpectedly has prior local evidence"
                )
        else:
            local_prior = _mapping(
                local_prior, label=f"action ordinal {ordinal}.prior_local_evidence"
            )
            if (
                local_prior.get("boot_nonce") != boot_nonce
                or local_prior.get("prior_result_sha256") != prior_sha256
            ):
                raise TrueR20PartialHoldEvidenceBundleError(
                    f"action ordinal {ordinal} prior-result chain differs"
                )
        batch1 = _mapping(
            root.get("batch1_evidence_binding"),
            label=f"action ordinal {ordinal}.batch1_evidence_binding",
        )
        if (
            batch1.get("file_sha256") != batch1_binding["file_sha256"]
            or batch1.get("requirements_id")
            != true_pack.BATCH1_EVIDENCE_REQUIREMENTS_ID
            or batch1.get("campaign_id") != true_once.BATCH1_CAMPAIGN_ID
            or batch1.get("contract_id") != true_once.BATCH1_CONTRACT_ID
        ):
            raise TrueR20PartialHoldEvidenceBundleError(
                f"action ordinal {ordinal} Batch-1 binding differs"
            )
        batch2 = _mapping(
            root.get("batch2_evidence_binding"),
            label=f"action ordinal {ordinal}.batch2_evidence_binding",
        )
        batch2_terminal = _mapping(
            batch2.get("terminal_white_prerequisite"),
            label=f"action ordinal {ordinal}.batch2 terminal prerequisite",
        )
        if (
            dict(batch2) != dict(batch2_binding)
            or batch2.get("file_sha256") != batch2_binding["file_sha256"]
            or batch2.get("canonical_integrity_sha256")
            != batch2_binding["canonical_integrity_sha256"]
            or batch2.get("bundle_id") != batch2_binding["bundle_id"]
            or batch2_terminal.get("prerequisite_id")
            != batch2_binding["terminal_white_prerequisite"]["prerequisite_id"]
        ):
            raise TrueR20PartialHoldEvidenceBundleError(
                f"action ordinal {ordinal} Batch-2 binding differs"
            )
        prior_sha256 = _sha256_bytes(payload)
        records.append(
            {
                "ordinal": ordinal,
                "path": str(path),
                "file_sha256": prior_sha256,
                "canonical_integrity_sha256": root["integrity"]["sha256"],
                "action_id": expected["action_id"],
                "descriptor_id": expected["descriptor_id"],
                "role": expected["role"],
                "boot_nonce": current_boot,
                "created_at": identity["action_result_created_at"],
                "outcome": "complete_pass",
                "visible_refreshes": 1,
            }
        )
    assert boot_nonce is not None
    return records, boot_nonce


def _photo_capture(path: Path) -> dict[str, Any]:
    try:
        root = camera.validate_capture_evidence(path)
        payload = camera._read_stable_regular(path, label="photo capture sidecar")  # noqa: SLF001
        photo = _mapping(root.get("photo"), label="photo capture.photo")
        photo_path = camera._resolve_evidence_path(  # noqa: SLF001
            photo.get("path"), sidecar_path=path, label="photo capture.photo.path"
        )
        photo_payload = camera._read_stable_regular(  # noqa: SLF001
            photo_path, label="bound photo"
        )
    except camera.CameraCaptureEvidenceError as exc:
        raise TrueR20PartialHoldEvidenceBundleError(str(exc)) from exc
    coverage = _mapping(root.get("coverage"), label="photo capture.coverage")
    camera_record = _mapping(root.get("camera"), label="photo capture.camera")
    requested = _mapping(
        camera_record.get("requested_settings"), label="photo requested settings"
    )
    effective_before = _mapping(
        camera_record.get("effective_settings_before_frame"),
        label="photo effective settings before",
    )
    effective_after = _mapping(
        camera_record.get("effective_settings_after_frame"),
        label="photo effective settings after",
    )
    if (
        root.get("capture_binding") != camera.BINDING_LIVE
        or coverage.get("scope") != camera.COVERAGE_FULL
        or coverage.get("full_panel_visible") is not True
        or coverage.get("full_panel_uncropped") is not True
        or dict(effective_before) != dict(effective_after)
        or camera_record.get("read_failures") != 0
    ):
        raise TrueR20PartialHoldEvidenceBundleError(
            "photo capture is not locked live full-panel evidence"
        )
    try:
        batch1_builder.noise_report._require_locked_settings(  # noqa: SLF001
            requested,
            effective_before,
            backend=camera_record.get("backend"),
            label="photo camera",
        )
    except batch1_builder.noise_report.FactoryWhiteRepeatNoiseReportError as exc:
        raise TrueR20PartialHoldEvidenceBundleError(str(exc)) from exc
    signature = {
        "camera_id": camera_record.get("camera_id"),
        "instance_id": camera_record.get("instance_id"),
        "index": camera_record.get("index"),
        "backend": camera_record.get("backend"),
        "mount_id": coverage.get("mount_id"),
        "requested_settings": dict(requested),
        "effective_settings": dict(effective_before),
    }
    if any(
        signature.get(key) in (None, "")
        for key in ("camera_id", "instance_id", "backend", "mount_id")
    ):
        raise TrueR20PartialHoldEvidenceBundleError(
            "photo camera identity tuple is incomplete"
        )
    return {
        "path": str(path),
        "sidecar_file_sha256": _sha256_bytes(payload),
        "canonical_integrity_sha256": root["integrity"]["sha256"],
        "capture_id": root["capture_id"],
        "captured_at": root["captured_at"],
        "campaign_id": root["campaign_id"],
        "contract_id": root["contract_id"],
        "firmware_sha256": root["firmware_sha256"],
        "boot_nonce": root["boot_nonce"],
        "ordinal": root["ordinal"],
        "action_id": root["action_id"],
        "descriptor_id": root["descriptor_id"],
        "action_result_file_sha256": root["action_result"]["file_sha256"],
        "photo_path": str(photo_path),
        "photo_bytes": len(photo_payload),
        "photo_sha256": _sha256_bytes(photo_payload),
        "photo_width": photo["width"],
        "photo_height": photo["height"],
        "camera_signature": signature,
    }


def _video_capture(path: Path) -> dict[str, Any]:
    try:
        root = video_evidence.validate(path)
        payload = camera._read_stable_regular(path, label="video capture sidecar")  # noqa: SLF001
    except (
        video_evidence.CameraVideoCaptureEvidenceError,
        camera.CameraCaptureEvidenceError,
    ) as exc:
        raise TrueR20PartialHoldEvidenceBundleError(str(exc)) from exc
    camera_record = _mapping(root.get("camera"), label="video capture.camera")
    coverage = _mapping(root.get("coverage"), label="video capture.coverage")
    video = _mapping(root.get("video"), label="video capture.video")
    timing = _mapping(root.get("capture_timing"), label="video capture.timing")
    return {
        "path": str(path),
        "sidecar_file_sha256": _sha256_bytes(payload),
        "canonical_integrity_sha256": root["integrity"]["sha256"],
        "capture_id": root["capture_id"],
        "captured_at": root["captured_at"],
        "stage": root["stage"],
        "campaign_id": root["campaign_id"],
        "contract_id": root["contract_id"],
        "firmware_sha256": root["firmware_sha256"],
        "boot_nonce": root["boot_nonce"],
        "ordinal": root["ordinal"],
        "action_id": root["action_id"],
        "descriptor_id": root["descriptor_id"],
        "action_result_file_sha256": root["action_result"]["file_sha256"],
        "video_sha256": video["sha256"],
        "video_bytes": video["bytes"],
        "video_width": video["width"],
        "video_height": video["height"],
        "fps": float(video["fps"]),
        "decoded_frame_count": video["decoded_frame_count"],
        "duration_seconds": float(video["duration_seconds"]),
        "pre_roll_frames": root["pre_roll_frames"],
        "minimum_duration_seconds": float(root["minimum_duration_seconds"]),
        "started_at": timing["started_at"],
        "refresh_started_at": timing["refresh_started_at"],
        "refresh_completed_at": timing["refresh_completed_at"],
        "completed_at": timing["completed_at"],
        "camera_signature": {
            "camera_id": camera_record["camera_id"],
            "instance_id": camera_record["instance_id"],
            "index": camera_record["index"],
            "backend": camera_record["backend"],
            "mount_id": coverage["mount_id"],
            "requested_settings": dict(camera_record["requested_settings"]),
            "effective_settings": dict(
                camera_record["effective_settings_before_video"]
            ),
        },
    }


def _validate_static_gate(
    path: Path,
    *,
    stage: str,
    before_photo_sha256: str,
    after_photo_sha256: str,
    white_photo_sha256: str,
    geometry_sha256: str,
    repeat_noise_p95_de76: float,
) -> dict[str, Any]:
    payload, root = _load_sealed(path, label=f"{stage} static gate")
    layout = _mapping(root.get("layout"), label=f"{stage} static layout")
    inputs = _mapping(root.get("inputs"), label=f"{stage} static inputs")
    thresholds = _mapping(root.get("thresholds"), label=f"{stage} static thresholds")
    classification = _mapping(
        root.get("classification"), label=f"{stage} static classification"
    )
    if (
        root.get("schema_version") != static_gate.SCHEMA_VERSION
        or root.get("kind") != static_gate.KIND
        or root.get("stage") != stage
        or layout.get("id") != static_gate.LAYOUT_ID
        or layout.get("same_coordinates_both_controllers") is not True
        or layout.get("cs2_mirrored") is not False
        or thresholds.get("repeat_noise_p95_de76") != repeat_noise_p95_de76
        or classification.get("state") != "STATIC_HOLD_GATE_PASS_VIDEO_STILL_REQUIRED"
        or classification.get("static_gate_pass") is not True
        or classification.get("transient_no_flash_proven") is not False
        or classification.get("qualified_cross_r20_hold") is not False
        or classification.get("qualified_new_colour") is not False
        or root.get("output_write_contract") != "O_EXCL"
    ):
        raise TrueR20PartialHoldEvidenceBundleError(f"{stage} static gate did not pass")
    wanted_inputs = {
        "before": before_photo_sha256,
        "after": after_photo_sha256,
        "factory_white_reference": white_photo_sha256,
        "reference_grid": geometry_sha256,
    }
    for name, wanted in wanted_inputs.items():
        item = _mapping(inputs.get(name), label=f"{stage} static input {name}")
        if item.get("sha256") != wanted:
            raise TrueR20PartialHoldEvidenceBundleError(
                f"{stage} static {name} photo/geometry binding differs"
            )
    protected = root.get("protected_hold_results")
    new = root.get("new_roi_results")
    white = root.get("expected_white_results")
    pairs = root.get("new_roi_left_right_results")
    background = root.get("background_results")
    edges = root.get("edge_results")
    expected_counts = {
        "protected": 2 * len(EXPECTED_PROTECTED[stage]),
        "new": 2 * len(EXPECTED_NEW[stage]),
        "white": 2 * len(EXPECTED_WHITE[stage]),
        "pairs": len(EXPECTED_NEW[stage]),
        "background": 4,
        "edges": 2
        * len(
            {
                "A": ("A",),
                "B": ("A", "B"),
                "C": ("A", "B", "C"),
                "WHITE": (),
            }[stage]
        ),
    }
    observed = {
        "protected": protected,
        "new": new,
        "white": white,
        "pairs": pairs,
        "background": background,
        "edges": edges,
    }
    if any(
        not isinstance(observed[name], list)
        or len(observed[name]) != expected_counts[name]
        for name in observed
    ):
        raise TrueR20PartialHoldEvidenceBundleError(
            f"{stage} static result coverage differs"
        )
    if (
        any(item.get("within_hold_threshold") is not True for item in protected)
        or any(item.get("new_colour_change_detected") is not True for item in new)
        or any(item.get("within_white_threshold") is not True for item in white)
        or any(item.get("within_pair_threshold") is not True for item in pairs)
        or any(
            item.get("within_background_threshold") is not True for item in background
        )
        or any(item.get("bottom_edge_anomaly") is not False for item in edges)
    ):
        raise TrueR20PartialHoldEvidenceBundleError(
            f"{stage} static detail gate differs"
        )
    return {
        **_binding(path, payload, root),
        "stage": stage,
        "analysis_id": root.get("analysis_id"),
        "before_photo_sha256": before_photo_sha256,
        "after_photo_sha256": after_photo_sha256,
        "static_gate_pass": True,
    }


def _validate_video_gate(
    path: Path,
    *,
    stage: str,
    capture: Mapping[str, Any],
    geometry_sha256: str,
    repeat_noise_p95_de76: float,
) -> dict[str, Any]:
    payload, root = _load_sealed(path, label=f"{stage} video gate")
    source = _mapping(root.get("source_video"), label=f"{stage} source video")
    reference = _mapping(root.get("reference_grid"), label=f"{stage} video reference")
    thresholds = _mapping(root.get("thresholds"), label=f"{stage} video thresholds")
    evaluation = _mapping(root.get("evaluation"), label=f"{stage} video evaluation")
    classification = _mapping(
        root.get("classification"), label=f"{stage} video classification"
    )
    expected_state = (
        "NO_PROTECTED_ROI_AT_THIS_STAGE"
        if not EXPECTED_PROTECTED[stage]
        else "NO_TRANSIENT_PROTECTED_ROI_CHANGE_CANDIDATE"
    )
    source_fps = _number(source.get("fps"), label=f"{stage} source video FPS")
    source_duration = _number(
        source.get("duration_seconds"), label=f"{stage} source video duration"
    )
    minimum_duration = _number(
        thresholds.get("minimum_duration_seconds"),
        label=f"{stage} minimum video duration",
        nonnegative=True,
    )
    if (
        root.get("schema_version") != video_gate.SCHEMA_VERSION
        or root.get("kind") != video_gate.KIND
        or root.get("stage") != stage
        or root.get("protected_rois") != list(EXPECTED_PROTECTED[stage])
        or source.get("sha256") != capture["video_sha256"]
        or source.get("bytes") != capture["video_bytes"]
        or source.get("width") != capture["video_width"]
        or source.get("height") != capture["video_height"]
        or source_fps != capture["fps"]
        or source.get("decoded_frame_count") != capture["decoded_frame_count"]
        or source_duration != capture["duration_seconds"]
        or reference.get("sha256") != geometry_sha256
        or thresholds.get("repeat_noise_p95_de76") != repeat_noise_p95_de76
        or thresholds.get("pre_roll_frames") != capture["pre_roll_frames"]
        or minimum_duration != capture["minimum_duration_seconds"]
        or minimum_duration < MINIMUM_VIDEO_DURATION_SECONDS
        or root.get("duration_gate_pass") is not True
        or evaluation.get("protected_pass") is not True
        or evaluation.get("background_stability_pass") is not True
        or evaluation.get("transient_gate_pass") is not True
        or classification.get("state") != expected_state
        or classification.get("transient_gate_pass") is not True
        or classification.get("qualified_cross_r20_hold") is not False
        or root.get("output_write_contract") != "O_EXCL"
    ):
        raise TrueR20PartialHoldEvidenceBundleError(
            f"{stage} video duration/background/protected gate did not pass"
        )
    series = evaluation.get("series")
    expected_keys = {
        *(
            f"C{controller}-{name}"
            for controller in range(2)
            for name in EXPECTED_PROTECTED[stage]
        ),
        *(
            f"C{controller}-{name}"
            for controller in range(2)
            for name in static_gate.BACKGROUND_LOCAL
        ),
    }
    if (
        not isinstance(series, list)
        or {item.get("key") for item in series} != expected_keys
        or any(item.get("within_threshold") is not True for item in series)
    ):
        raise TrueR20PartialHoldEvidenceBundleError(
            f"{stage} video series coverage differs"
        )
    return {
        **_binding(path, payload, root),
        "stage": stage,
        "analysis_id": root.get("analysis_id"),
        "source_video_sha256": capture["video_sha256"],
        "duration_seconds": capture["duration_seconds"],
        "protected_rois": list(EXPECTED_PROTECTED[stage]),
        "background_stability_pass": True,
        "transient_gate_pass": True,
    }


def _validate_terminal_white(
    path: Path,
    *,
    candidate_photo_sha256: str,
    reference_photo_sha256: str,
    geometry_sha256: str,
    repeat_noise_p95_de76: float,
) -> dict[str, Any]:
    payload, root = _load_sealed(path, label="Batch-3 terminal white gate")
    layout = _mapping(root.get("layout"), label="terminal white layout")
    inputs = _mapping(root.get("inputs"), label="terminal white inputs")
    thresholds = _mapping(root.get("thresholds"), label="terminal white thresholds")
    summary = _mapping(root.get("summary"), label="terminal white summary")
    classification = _mapping(
        root.get("classification"), label="terminal white classification"
    )
    patches = root.get("patches")
    expected_p95_threshold = max(4.0, 3.0 * repeat_noise_p95_de76)
    expected_max_threshold = max(8.0, 1.5 * expected_p95_threshold)
    if (
        root.get("schema_version") != white_gate.SCHEMA_VERSION
        or root.get("kind") != white_gate.KIND
        or layout.get("id") != white_gate.LAYOUT_ID
        or layout.get("controllers") != 2
        or layout.get("patch_count") != 60
        or layout.get("panel_wide_discrete_patch_sampling") is not True
        or thresholds.get("repeat_noise_p95_de76") != repeat_noise_p95_de76
        or thresholds.get("patch_grid_p95_de76") != expected_p95_threshold
        or thresholds.get("patch_grid_max_de76") != expected_max_threshold
        or summary.get("patch_count") != 60
        or summary.get("all_panel_regions_match_reference") is not True
        or not isinstance(patches, list)
        or len(patches) != 60
        or classification.get("state")
        != "PANEL_WIDE_CAMERA_RELATIVE_FACTORY_WHITE_MATCH"
        or classification.get("pass") is not True
        or classification.get("absolute_white_proven") is not False
        or root.get("output_write_contract") != "O_EXCL"
    ):
        raise TrueR20PartialHoldEvidenceBundleError(
            "Batch-3 terminal 60-patch white gate did not pass"
        )
    wanted = {
        "candidate": candidate_photo_sha256,
        "factory_white_reference": reference_photo_sha256,
        "geometry_reference": geometry_sha256,
    }
    for name, sha256 in wanted.items():
        item = _mapping(inputs.get(name), label=f"terminal white input {name}")
        if item.get("sha256") != sha256:
            raise TrueR20PartialHoldEvidenceBundleError(
                f"terminal white {name} binding differs"
            )
    seen: set[tuple[int, int, int]] = set()
    deltas: list[float] = []
    for index, raw in enumerate(patches):
        patch = _mapping(raw, label=f"terminal white patch {index}")
        coordinate = (
            patch.get("controller"),
            patch.get("row"),
            patch.get("column"),
        )
        if (
            any(type(item) is not int for item in coordinate)
            or coordinate[0] not in (0, 1)
            or coordinate in seen
        ):
            raise TrueR20PartialHoldEvidenceBundleError(
                "terminal white patch coordinates differ"
            )
        seen.add(coordinate)
        deltas.append(
            _number(
                patch.get("camera_relative_de76"),
                label=f"terminal white patch {index} delta",
                nonnegative=True,
            )
        )
    observed = {
        "camera_relative_de76_median": _percentile(deltas, 0.5),
        "camera_relative_de76_p95": _percentile(deltas, 0.95),
        "camera_relative_de76_max": max(deltas),
    }
    if (
        any(summary.get(name) != value for name, value in observed.items())
        or observed["camera_relative_de76_p95"] > expected_p95_threshold
        or observed["camera_relative_de76_max"] > expected_max_threshold
    ):
        raise TrueR20PartialHoldEvidenceBundleError(
            "terminal white patch summary or threshold differs"
        )
    return {
        **_binding(path, payload, root),
        "analysis_id": root.get("analysis_id"),
        "candidate_photo_sha256": candidate_photo_sha256,
        "patch_count": 60,
        "camera_relative_factory_white_match": True,
    }


def build_bundle(
    *,
    batch1_bundle_path: Path,
    batch2_bundle_path: Path,
    repeat_noise_report_path: Path,
    reference_grid_analysis_path: Path,
    action_paths: Sequence[Path],
    pre_capture_paths: Sequence[Path],
    after_capture_paths: Sequence[Path],
    static_gate_paths: Sequence[Path],
    video_capture_paths: Sequence[Path],
    video_gate_paths: Sequence[Path],
    terminal_white_gate_path: Path,
) -> dict[str, Any]:
    """Deep-validate and return the sealed Batch-3 aggregate in memory."""

    for label, paths in (
        ("pre capture", pre_capture_paths),
        ("after capture", after_capture_paths),
        ("static gate", static_gate_paths),
        ("video capture", video_capture_paths),
        ("video gate", video_gate_paths),
    ):
        if len(paths) != 4:
            raise TrueR20PartialHoldEvidenceBundleError(
                f"exactly four {label} inputs are required"
            )
    batch1_root, batch1_binding = _load_batch1(Path(batch1_bundle_path))
    batch2_root, batch2_binding = _validate_batch2(Path(batch2_bundle_path))
    try:
        noise_binding, repeat_noise = batch1_builder._validate_noise_report(  # noqa: SLF001
            Path(repeat_noise_report_path)
        )
    except batch1_builder.SameR20ParityEvidenceBundleError as exc:
        raise TrueR20PartialHoldEvidenceBundleError(str(exc)) from exc
    baseline = _mapping(
        batch1_root.get("repeat_noise_baseline"), label="Batch-1 noise baseline"
    )
    if (
        baseline.get("file_sha256") != noise_binding["file_sha256"]
        or baseline.get("canonical_integrity_sha256")
        != noise_binding["canonical_integrity_sha256"]
        or baseline.get("reference_geometry_sha256")
        != noise_binding["reference_geometry_sha256"]
        or baseline.get("repeat_noise_p95_de76") != repeat_noise
    ):
        raise TrueR20PartialHoldEvidenceBundleError(
            "Batch-1 and sealed repeat-noise bindings differ"
        )
    reference_payload, reference_root = _load_sealed(
        Path(reference_grid_analysis_path), label="reference grid analysis"
    )
    geometry_sha256 = _sha256_bytes(reference_payload)
    if geometry_sha256 != noise_binding["reference_geometry_sha256"]:
        raise TrueR20PartialHoldEvidenceBundleError(
            "reference geometry differs from sealed repeat-noise baseline"
        )

    action_results, boot_nonce = _validate_action_results(
        action_paths, batch1_binding, batch2_binding
    )
    pre_captures = [_photo_capture(Path(path)) for path in pre_capture_paths]
    after_captures = [_photo_capture(Path(path)) for path in after_capture_paths]
    video_captures = [_video_capture(Path(path)) for path in video_capture_paths]

    terminal2 = batch2_binding["terminal_white_prerequisite"]
    if (
        pre_captures[0]["sidecar_file_sha256"]
        != terminal2["capture_sidecar_file_sha256"]
        or pre_captures[0]["photo_sha256"] != terminal2["photo_sha256"]
        or pre_captures[0]["action_result_file_sha256"]
        != terminal2["action_result_file_sha256"]
        or pre_captures[0]["boot_nonce"] != terminal2["campaign_boot_nonce"]
        or pre_captures[0]["captured_at"] != terminal2["captured_at"]
    ):
        raise TrueR20PartialHoldEvidenceBundleError(
            "Batch-3 initial white capture differs from Batch-2 terminal anchor"
        )
    for ordinal in range(1, 4):
        prior = after_captures[ordinal - 1]
        current = pre_captures[ordinal]
        if any(
            current[field] != prior[field]
            for field in ("sidecar_file_sha256", "capture_id", "photo_sha256")
        ):
            raise TrueR20PartialHoldEvidenceBundleError(
                f"stage {STAGES[ordinal]} pre-capture is not prior stage after-capture"
            )

    common_signature = pre_captures[0]["camera_signature"]
    all_capture_signatures = [
        *(item["camera_signature"] for item in pre_captures),
        *(item["camera_signature"] for item in after_captures),
        *(item["camera_signature"] for item in video_captures),
    ]
    if any(item != common_signature for item in all_capture_signatures):
        raise TrueR20PartialHoldEvidenceBundleError(
            "Batch-3 photo/video camera, mount, or manual readback differs"
        )
    if common_signature != noise_binding["camera_signature"]:
        raise TrueR20PartialHoldEvidenceBundleError(
            "Batch-3 camera signature differs from repeat-noise baseline"
        )
    for ordinal, (after, video) in enumerate(
        zip(after_captures, video_captures, strict=True), 1
    ):
        action = action_results[ordinal - 1]
        if any(
            after[field] != action[wanted]
            for field, wanted in (
                ("action_id", "action_id"),
                ("descriptor_id", "descriptor_id"),
                ("action_result_file_sha256", "file_sha256"),
                ("boot_nonce", "boot_nonce"),
            )
        ) or any(
            video[field] != action[wanted]
            for field, wanted in (
                ("action_id", "action_id"),
                ("descriptor_id", "descriptor_id"),
                ("action_result_file_sha256", "file_sha256"),
                ("boot_nonce", "boot_nonce"),
            )
        ):
            raise TrueR20PartialHoldEvidenceBundleError(
                f"action ordinal {ordinal} photo/video binding differs"
            )
        if after["ordinal"] != ordinal or video["ordinal"] != ordinal:
            raise TrueR20PartialHoldEvidenceBundleError(
                f"action ordinal {ordinal} capture ordinal differs"
            )
        if video["stage"] != STAGES[ordinal - 1]:
            raise TrueR20PartialHoldEvidenceBundleError(
                f"action ordinal {ordinal} video stage differs"
            )
        if not (
            _time(pre_captures[ordinal - 1]["captured_at"], label="pre capture time")
            < _time(video["started_at"], label="video start")
            < _time(video["completed_at"], label="video completion")
            < _time(after["captured_at"], label="after capture time")
        ):
            raise TrueR20PartialHoldEvidenceBundleError(
                f"action ordinal {ordinal} pre/video/after timing differs"
            )

    static_bindings: list[dict[str, Any]] = []
    video_gate_bindings: list[dict[str, Any]] = []
    for index, stage in enumerate(STAGES):
        static_bindings.append(
            _validate_static_gate(
                Path(static_gate_paths[index]),
                stage=stage,
                before_photo_sha256=pre_captures[index]["photo_sha256"],
                after_photo_sha256=after_captures[index]["photo_sha256"],
                white_photo_sha256=pre_captures[0]["photo_sha256"],
                geometry_sha256=geometry_sha256,
                repeat_noise_p95_de76=repeat_noise,
            )
        )
        video_gate_bindings.append(
            _validate_video_gate(
                Path(video_gate_paths[index]),
                stage=stage,
                capture=video_captures[index],
                geometry_sha256=geometry_sha256,
                repeat_noise_p95_de76=repeat_noise,
            )
        )
    terminal_white = _validate_terminal_white(
        Path(terminal_white_gate_path),
        candidate_photo_sha256=after_captures[3]["photo_sha256"],
        reference_photo_sha256=pre_captures[0]["photo_sha256"],
        geometry_sha256=geometry_sha256,
        repeat_noise_p95_de76=repeat_noise,
    )

    shared2 = batch2_binding["shared_analysis_bindings"]
    noise2 = _mapping(
        shared2.get("repeat_noise_baseline"),
        label="Batch-2 shared repeat-noise binding",
    )
    if (
        shared2.get("repeat_noise_p95_de76") != repeat_noise
        or shared2.get("reference_geometry_sha256") != geometry_sha256
        or noise2.get("file_sha256") != noise_binding["file_sha256"]
        or noise2.get("canonical_integrity_sha256")
        != noise_binding["canonical_integrity_sha256"]
    ):
        raise TrueR20PartialHoldEvidenceBundleError(
            "Batch-2 shared noise or geometry binding differs"
        )
    if batch2_binding["shared_camera_lock"] != common_signature:
        raise TrueR20PartialHoldEvidenceBundleError(
            "Batch-2 and Batch-3 shared camera lock differs"
        )

    stages: list[dict[str, Any]] = []
    for index, stage in enumerate(STAGES):
        stages.append(
            {
                "ordinal": index + 1,
                "stage": stage,
                "action_result": deepcopy(action_results[index]),
                "pre_capture": deepcopy(pre_captures[index]),
                "after_capture": deepcopy(after_captures[index]),
                "static_gate": deepcopy(static_bindings[index]),
                "video_capture": deepcopy(video_captures[index]),
                "video_gate": deepcopy(video_gate_bindings[index]),
                "protected_rois": list(EXPECTED_PROTECTED[stage]),
                "static_gate_pass": True,
                "duration_gate_pass": True,
                "background_stability_pass": True,
                "transient_gate_pass": True,
            }
        )
    bundle_id = _sha256_bytes(
        _canonical_json(
            {
                "campaign_id": true_pack.CAMPAIGN_ID,
                "contract_id": true_pack.CONTRACT_ID,
                "batch1_file_sha256": batch1_binding["file_sha256"],
                "batch2_file_sha256": batch2_binding["file_sha256"],
                "action_result_sha256": [
                    item["file_sha256"] for item in action_results
                ],
                "after_photo_sha256": [item["photo_sha256"] for item in after_captures],
                "video_sha256": [item["video_sha256"] for item in video_captures],
                "static_gate_sha256": [item["file_sha256"] for item in static_bindings],
                "video_gate_sha256": [
                    item["file_sha256"] for item in video_gate_bindings
                ],
                "terminal_white_gate_sha256": terminal_white["file_sha256"],
            }
        )
    )
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "bundle_id": bundle_id,
        "campaign_identity": {
            "campaign_id": true_pack.CAMPAIGN_ID,
            "test_id": true_pack.TEST_ID,
            "contract_id": true_pack.CONTRACT_ID,
            "requirements_id": true_pack.BATCH1_EVIDENCE_REQUIREMENTS_ID,
            "firmware_bin_sha256": true_once.FIRMWARE_BIN_SHA256,
            "firmware_bin_bytes": true_once.FIRMWARE_BIN_BYTES,
            "boot_nonce": boot_nonce,
            "action_ids": list(true_pack.ACTION_IDS),
            "descriptor_ids": list(true_pack.DESCRIPTOR_IDS),
        },
        "batch1_prerequisite": batch1_binding,
        "batch2_terminal_white_prerequisite": batch2_binding,
        "repeat_noise_baseline": noise_binding,
        "reference_geometry": {
            **_binding(
                Path(reference_grid_analysis_path), reference_payload, reference_root
            ),
            "repeat_noise_p95_de76": repeat_noise,
        },
        "shared_camera_lock": common_signature,
        "stages": stages,
        "terminal_white_60_patch_gate": terminal_white,
        "classification": {
            "state": "BATCH3_CAMERA_RELATIVE_ROI_HOLD_EVIDENCE_COMPLETE",
            "aggregate_gate_pass": True,
            "all_four_actions_complete_pass": True,
            "static_roi_hold_gates_pass": True,
            "sampled_video_transient_gates_pass": True,
            "terminal_60_patch_factory_white_gate_pass": True,
            "qualified_cross_r20_hold": False,
            "qualified_new_colour": False,
            "absolute_colour_proven": False,
        },
        "evidence_boundaries": {
            "camera_relative_de76_not_calibrated_de00": True,
            "static_results_are_roi_medians_not_all_pixels": True,
            "video_results_are_sampled_rois_not_all_pixels": True,
            "no_area_percentage_or_full_pixel_hold_claim": True,
            "center_seam_not_specifically_qualified": True,
            "long_term_retention_not_tested": True,
            "no_absolute_colour_or_colour_name_claim": True,
            "transport_codes_are_not_colour_names": True,
            "compiled_payload_identity_not_bus_capture": True,
            "video_sidecar_live_timing_is_external_orchestrator_evidence": True,
            "bundle_builder_performed_no_device_or_camera_io": True,
        },
        "output_write_contract": "O_EXCL",
    }
    unsigned["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": _sha256_bytes(_canonical_json(unsigned)),
    }
    return unsigned


def _write_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise TrueR20PartialHoldEvidenceBundleError(
            f"refusing to overwrite evidence bundle: {path}"
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--batch1-bundle", type=Path, required=True)
    parser.add_argument("--batch2-bundle", type=Path, required=True)
    parser.add_argument("--repeat-noise-report", type=Path, required=True)
    parser.add_argument("--reference-grid-analysis", type=Path, required=True)
    parser.add_argument("--action-result", type=Path, action="append", required=True)
    parser.add_argument(
        "--pre-capture-sidecar", type=Path, action="append", required=True
    )
    parser.add_argument(
        "--after-capture-sidecar", type=Path, action="append", required=True
    )
    parser.add_argument("--static-gate", type=Path, action="append", required=True)
    parser.add_argument(
        "--video-capture-sidecar", type=Path, action="append", required=True
    )
    parser.add_argument("--video-gate", type=Path, action="append", required=True)
    parser.add_argument("--terminal-white-gate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = build_bundle(
            batch1_bundle_path=args.batch1_bundle,
            batch2_bundle_path=args.batch2_bundle,
            repeat_noise_report_path=args.repeat_noise_report,
            reference_grid_analysis_path=args.reference_grid_analysis,
            action_paths=args.action_result,
            pre_capture_paths=args.pre_capture_sidecar,
            after_capture_paths=args.after_capture_sidecar,
            static_gate_paths=args.static_gate,
            video_capture_paths=args.video_capture_sidecar,
            video_gate_paths=args.video_gate,
            terminal_white_gate_path=args.terminal_white_gate,
        )
        payload = (
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            ).encode("utf-8")
            + b"\n"
        )
        _write_exclusive(args.output, payload)
        sys.stdout.buffer.write(payload)
        return 0
    except TrueR20PartialHoldEvidenceBundleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
