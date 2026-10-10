#!/usr/bin/env python3
"""Seal Batch-1 same-R20 action and camera evidence for true-R20 HOLD.

The builder is deliberately offline.  It accepts the four immutable action
results and synchronized full-panel captures, a sealed factory-white repeat
noise baseline, AA/CC paired-atlas analyses, and two factory-white reference
gates.  It validates every canonical seal and identity before exclusively
creating the exact prerequisite bundle consumed by the true-R20 runner.
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

from tools import mf1750_camera_capture_evidence as camera
from tools import mf1750_factory_white_reference_photo_gate as white_gate
from tools import mf1750_factory_white_repeat_noise_report as noise_report
from tools import mf1750_runtime_lut_same_r20_parity_v1_once as same_once
from tools import mf1750_runtime_lut_same_r20_parity_v1_pack as same_pack
from tools import mf1750_same_r20_aa_cc_paired_comparison as aa_cc_comparison
from tools import mf1750_same_r20_atlas_photo_analyzer as atlas


SCHEMA_VERSION = 1
KIND = "mf1750-same-r20-parity-evidence-bundle-v1"
INTEGRITY_ALGORITHM = atlas.INTEGRITY_ALGORITHM
ACTION_RESULT_KIND = "mf1750-ec5-same-r20-parity-v1-result"
CANDIDATE_CODES = [0, 0, 2]
REQUIRED_MANUAL_CAMERA_SETTINGS = {
    "autofocus": 0.0,
    "auto_exposure": 0.25,
    "auto_white_balance": 0.0,
}


class SameR20ParityEvidenceBundleError(RuntimeError):
    """Raised when an input binding or exclusive output is invalid."""


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
        raise SameR20ParityEvidenceBundleError(
            f"record contains a non-canonical JSON value: {exc}"
        ) from exc


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        payload, root = atlas._load_json(path, label=label)
        atlas._verify_integrity(root)
    except atlas.SameR20AtlasAnalysisError as exc:
        raise SameR20ParityEvidenceBundleError(str(exc)) from exc
    return payload, root


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SameR20ParityEvidenceBundleError(f"{label} must be an object")
    return value


def _validate_action(
    path: Path,
    *,
    ordinal: int,
    action_id: str,
    descriptor_id: str,
    output_name: str,
) -> dict[str, Any]:
    if path.name != output_name:
        raise SameR20ParityEvidenceBundleError(
            f"action ordinal {ordinal} filename differs"
        )
    payload, root = _load(path, label=f"action ordinal {ordinal}")
    action = _mapping(root.get("action"), label=f"action ordinal {ordinal}.action")
    terminal = _mapping(
        root.get("terminal_report"), label=f"action ordinal {ordinal}.terminal_report"
    )
    if (
        root.get("schema_version") != 1
        or root.get("kind") != ACTION_RESULT_KIND
        or root.get("outcome") != "complete_pass"
        or root.get("firmware_sha256") != same_once.FIRMWARE_SHA256
        or root.get("no_autochain") is not True
        or root.get("no_retry") is not True
        or root.get("no_recovery") is not True
        or action.get("ordinal") != ordinal
        or action.get("action_id") != action_id
        or action.get("descriptor_id") != descriptor_id
        or terminal.get("campaign_id") != same_pack.CAMPAIGN_ID
        or terminal.get("contract_id") != same_once.base.runner.CONTRACT_ID
        or terminal.get("action_id") != action_id
        or terminal.get("descriptor_id") != descriptor_id
        or terminal.get("driver_call_count_for_action") != 1
        or terminal.get("driver_called") is not True
    ):
        raise SameR20ParityEvidenceBundleError(
            f"action ordinal {ordinal} identity or terminal evidence differs"
        )
    return {
        "ordinal": ordinal,
        "action_id": action_id,
        "output_name": output_name,
        "outcome": "complete_pass",
        "output_sha256": _sha256_bytes(payload),
    }


def _validate_atlas(path: Path, *, role: str) -> tuple[str, str, str, str, float]:
    payload, root = _load(path, label=f"{role} atlas analysis")
    layout = _mapping(root.get("layout"), label=f"{role} atlas layout")
    geometry = _mapping(root.get("geometry_guard"), label=f"{role} geometry")
    paired = _mapping(root.get("paired_summary"), label=f"{role} paired summary")
    classification = _mapping(
        root.get("classification"), label=f"{role} classification"
    )
    source_photo = _mapping(root.get("source_photo"), label=f"{role} source photo")
    reference_geometry = _mapping(
        root.get("reference_geometry"), label=f"{role} reference geometry"
    )
    cells = root.get("cells")
    pairs = root.get("left_right_pairs")
    if (
        root.get("schema_version") != atlas.SCHEMA_VERSION
        or root.get("kind") != atlas.KIND
        or root.get("role") != role
        or layout.get("id") != atlas.LAYOUT_ID
        or geometry.get("reference_homography_alignment_guard_pass") is not True
        or not isinstance(cells, list)
        or len(cells) != 16
        or not isinstance(pairs, list)
        or len(pairs) != 8
        or paired.get("repeat_noise_p95_de76") is None
        or paired.get("all_pairs_within_exploratory_threshold") is not True
        or classification.get("state") != "CAMERA_RELATIVE_CONTROLLER_MATCH_CANDIDATE"
    ):
        raise SameR20ParityEvidenceBundleError(f"{role} atlas gate did not pass")
    photo_sha256 = source_photo.get("sha256")
    if not isinstance(photo_sha256, str) or len(photo_sha256) != 64:
        raise SameR20ParityEvidenceBundleError(f"{role} source photo SHA differs")
    geometry_sha256 = reference_geometry.get("file_sha256")
    repeat_noise = paired.get("repeat_noise_p95_de76")
    if not isinstance(geometry_sha256, str) or len(geometry_sha256) != 64:
        raise SameR20ParityEvidenceBundleError(f"{role} reference geometry SHA differs")
    if type(repeat_noise) not in (int, float):
        raise SameR20ParityEvidenceBundleError(f"{role} repeat-noise value differs")
    return (
        _sha256_bytes(payload),
        str(root["integrity"]["sha256"]),
        photo_sha256,
        geometry_sha256,
        float(repeat_noise),
    )


def _validate_white(path: Path, *, label: str) -> tuple[str, str, str, str, float]:
    payload, root = _load(path, label=label)
    layout = _mapping(root.get("layout"), label=f"{label}.layout")
    summary = _mapping(root.get("summary"), label=f"{label}.summary")
    classification = _mapping(
        root.get("classification"), label=f"{label}.classification"
    )
    thresholds = _mapping(root.get("thresholds"), label=f"{label}.thresholds")
    inputs = _mapping(root.get("inputs"), label=f"{label}.inputs")
    candidate = _mapping(inputs.get("candidate"), label=f"{label}.inputs.candidate")
    geometry = _mapping(
        inputs.get("geometry_reference"),
        label=f"{label}.inputs.geometry_reference",
    )
    if (
        root.get("schema_version") != white_gate.SCHEMA_VERSION
        or root.get("kind") != white_gate.KIND
        or layout.get("id") != white_gate.LAYOUT_ID
        or layout.get("patch_count") != 60
        or thresholds.get("repeat_noise_p95_de76") is None
        or summary.get("all_panel_regions_match_reference") is not True
        or classification.get("pass") is not True
        or classification.get("state")
        != "PANEL_WIDE_CAMERA_RELATIVE_FACTORY_WHITE_MATCH"
    ):
        raise SameR20ParityEvidenceBundleError(f"{label} gate did not pass")
    photo_sha256 = candidate.get("sha256")
    if not isinstance(photo_sha256, str) or len(photo_sha256) != 64:
        raise SameR20ParityEvidenceBundleError(f"{label} candidate photo SHA differs")
    geometry_sha256 = geometry.get("sha256")
    repeat_noise = thresholds.get("repeat_noise_p95_de76")
    if not isinstance(geometry_sha256, str) or len(geometry_sha256) != 64:
        raise SameR20ParityEvidenceBundleError(
            f"{label} reference geometry SHA differs"
        )
    if type(repeat_noise) not in (int, float):
        raise SameR20ParityEvidenceBundleError(f"{label} repeat-noise value differs")
    return (
        _sha256_bytes(payload),
        str(root["integrity"]["sha256"]),
        photo_sha256,
        geometry_sha256,
        float(repeat_noise),
    )


def _validate_noise_report(path: Path) -> tuple[dict[str, Any], float]:
    payload, root = _load(path, label="factory-white repeat-noise report")
    layout = _mapping(root.get("layout"), label="noise report.layout")
    capture_contract = _mapping(
        root.get("capture_contract"), label="noise report.capture_contract"
    )
    setup = _mapping(
        capture_contract.get("locked_camera_and_mount"),
        label="noise report locked camera and mount",
    )
    summary = _mapping(root.get("summary"), label="noise report.summary")
    classification = _mapping(
        root.get("classification"), label="noise report.classification"
    )
    geometry = _mapping(
        root.get("geometry_reference"), label="noise report.geometry_reference"
    )
    p95 = summary.get("repeat_noise_p95_de76")
    geometry_sha256 = geometry.get("file_sha256")
    if (
        root.get("schema_version") != noise_report.SCHEMA_VERSION
        or root.get("kind") != noise_report.KIND
        or layout.get("id") != white_gate.LAYOUT_ID
        or layout.get("patch_count") != 60
        or capture_contract.get("capture_count", 0) < noise_report.MINIMUM_CAPTURE_COUNT
        or capture_contract.get("capture_binding") != camera.BINDING_LIVE
        or capture_contract.get("coverage_scope") != camera.COVERAGE_FULL
        or capture_contract.get("same_factory_white_action") is not True
        or classification.get("valid_repeat_noise_baseline") is not True
        or type(p95) not in (int, float)
        or not math.isfinite(float(p95))
        or float(p95) < 0
        or not isinstance(geometry_sha256, str)
        or len(geometry_sha256) != 64
    ):
        raise SameR20ParityEvidenceBundleError(
            "factory-white repeat-noise report gate did not pass"
        )
    return (
        {
            "path": str(path),
            "file_sha256": _sha256_bytes(payload),
            "canonical_integrity_sha256": root["integrity"]["sha256"],
            "baseline_id": root.get("baseline_id"),
            "reference_geometry_sha256": geometry_sha256,
            "capture_count": capture_contract["capture_count"],
            "repeat_noise_p95_de76": float(p95),
            "camera_signature": {
                "camera_id": setup.get("camera_id"),
                "instance_id": setup.get("camera_instance_id"),
                "index": setup.get("camera_index"),
                "backend": setup.get("backend"),
                "mount_id": setup.get("mount_id"),
                "requested_settings": setup.get("requested_settings"),
                "effective_settings": setup.get("effective_settings"),
            },
        },
        float(p95),
    )


def _validate_aa_cc_comparison(
    path: Path,
    *,
    aa_file_sha256: str,
    cc_file_sha256: str,
    reference_geometry_sha256: str,
    repeat_noise_p95_de76: float,
) -> dict[str, Any]:
    payload, root = _load(path, label="AA-vs-CC paired comparison")
    inputs = _mapping(root.get("inputs"), label="AA-vs-CC inputs")
    aa_input = _mapping(inputs.get("aa"), label="AA-vs-CC AA input")
    cc_input = _mapping(inputs.get("cc"), label="AA-vs-CC CC input")
    shared = _mapping(root.get("shared_bindings"), label="AA-vs-CC shared bindings")
    shared_geometry = _mapping(
        shared.get("reference_geometry"), label="AA-vs-CC reference geometry"
    )
    summary = _mapping(root.get("summary"), label="AA-vs-CC summary")
    counts = _mapping(
        summary.get("classification_counts"), label="AA-vs-CC classification counts"
    )
    classification = _mapping(
        root.get("classification"), label="AA-vs-CC classification"
    )
    allowed_states = {
        "CONTROLLER_INCONSISTENT_CODES_PRESENT",
        "R20_LINKED_EXPLORATORY_EFFECT_CODES_PRESENT",
        "NO_RESOLVED_AA_TO_CC_EFFECT",
    }
    expected_count_keys = {
        aa_cc_comparison.R20_LINKED_EXPLORATORY_EFFECT,
        aa_cc_comparison.NO_RESOLVED_EFFECT,
        aa_cc_comparison.CONTROLLER_INCONSISTENT,
    }
    if (
        root.get("schema_version") != aa_cc_comparison.SCHEMA_VERSION
        or root.get("kind") != aa_cc_comparison.KIND
        or aa_input.get("file_sha256") != aa_file_sha256
        or cc_input.get("file_sha256") != cc_file_sha256
        or aa_input.get("role") != "AA"
        or cc_input.get("role") != "CC"
        or shared_geometry.get("file_sha256") != reference_geometry_sha256
        or shared.get("repeat_noise_p95_de76") != repeat_noise_p95_de76
        or shared.get("aa_controller_pair_gate_pass") is not True
        or shared.get("cc_controller_pair_gate_pass") is not True
        or summary.get("code_count") != 8
        or summary.get("controller_code_delta_count") != 16
        or set(counts) != expected_count_keys
        or any(type(value) is not int or value < 0 for value in counts.values())
        or sum(value for value in counts.values() if type(value) is int) != 8
        or len(root.get("controller_code_deltas", [])) != 16
        or len(root.get("code_results", [])) != 8
        or classification.get("state") not in allowed_states
        or classification.get("absolute_colour_proven") is not False
        or classification.get("qualified_new_colour") is not False
        or classification.get("r20_causality_proven") is not False
        or root.get("output_write_contract") != "O_EXCL"
    ):
        raise SameR20ParityEvidenceBundleError(
            "AA-vs-CC paired comparison gate differs"
        )
    return {
        "path": str(path),
        "file_sha256": _sha256_bytes(payload),
        "canonical_integrity_sha256": root["integrity"]["sha256"],
        "comparison_id": root.get("comparison_id"),
        "classification_state": classification["state"],
        "classification_counts": dict(counts),
        "absolute_colour_proven": False,
        "qualified_new_colour": False,
    }


def _same_number(value: Any, wanted: float) -> bool:
    return type(value) in (int, float) and float(value) == wanted


def _validate_capture_sidecars(
    paths: Sequence[Path],
    *,
    action_results: Sequence[Mapping[str, Any]],
    expected_photo_sha256: Sequence[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if len(paths) != 4:
        raise SameR20ParityEvidenceBundleError(
            "exactly four synchronized capture sidecars are required"
        )
    if len(action_results) != 4 or len(expected_photo_sha256) != 4:
        raise SameR20ParityEvidenceBundleError("internal capture binding count differs")

    bindings: list[dict[str, Any]] = []
    common_signature: dict[str, Any] | None = None
    common_boot_nonce: str | None = None
    prior_captured_at: datetime | None = None
    actions = same_once.base.runner.ACTIONS
    for ordinal, raw_path in enumerate(paths, 1):
        path = Path(raw_path)
        try:
            sidecar_payload = atlas._read_stable_regular(
                path, label=f"capture sidecar ordinal {ordinal}"
            )
            root = camera.validate_capture_evidence(path)
        except (
            atlas.SameR20AtlasAnalysisError,
            camera.CameraCaptureEvidenceError,
        ) as exc:
            raise SameR20ParityEvidenceBundleError(str(exc)) from exc

        action = actions[ordinal - 1]
        action_record = _mapping(
            root.get("action_result"),
            label=f"capture sidecar ordinal {ordinal}.action_result",
        )
        photo = _mapping(
            root.get("photo"), label=f"capture sidecar ordinal {ordinal}.photo"
        )
        coverage = _mapping(
            root.get("coverage"), label=f"capture sidecar ordinal {ordinal}.coverage"
        )
        camera_record = _mapping(
            root.get("camera"), label=f"capture sidecar ordinal {ordinal}.camera"
        )
        requested = _mapping(
            camera_record.get("requested_settings"),
            label=f"capture sidecar ordinal {ordinal}.camera.requested_settings",
        )
        effective_before = _mapping(
            camera_record.get("effective_settings_before_frame"),
            label=f"capture sidecar ordinal {ordinal}.camera.effective_before",
        )
        effective_after = _mapping(
            camera_record.get("effective_settings_after_frame"),
            label=f"capture sidecar ordinal {ordinal}.camera.effective_after",
        )
        if (
            root.get("capture_binding") != camera.BINDING_LIVE
            or root.get("campaign_id") != same_pack.CAMPAIGN_ID
            or root.get("contract_id") != same_once.base.runner.CONTRACT_ID
            or root.get("firmware_sha256") != same_once.FIRMWARE_SHA256
            or root.get("ordinal") != ordinal
            or root.get("action_id") != action["action_id"]
            or root.get("descriptor_id") != action["descriptor_id"]
            or action_record.get("file_sha256")
            != action_results[ordinal - 1]["output_sha256"]
            or photo.get("sha256") != expected_photo_sha256[ordinal - 1]
        ):
            raise SameR20ParityEvidenceBundleError(
                f"capture sidecar ordinal {ordinal} action or photo binding differs"
            )
        if (
            coverage.get("scope") != camera.COVERAGE_FULL
            or coverage.get("full_panel_visible") is not True
            or coverage.get("full_panel_uncropped") is not True
        ):
            raise SameR20ParityEvidenceBundleError(
                f"capture sidecar ordinal {ordinal} is not full-panel evidence"
            )
        for field, wanted in REQUIRED_MANUAL_CAMERA_SETTINGS.items():
            if not _same_number(requested.get(field), wanted):
                raise SameR20ParityEvidenceBundleError(
                    f"capture sidecar ordinal {ordinal} camera {field} is not locked"
                )
        if dict(effective_before) != dict(effective_after):
            raise SameR20ParityEvidenceBundleError(
                f"capture sidecar ordinal {ordinal} effective camera settings drifted"
            )
        if camera_record.get("read_failures") != 0:
            raise SameR20ParityEvidenceBundleError(
                f"capture sidecar ordinal {ordinal} has camera read failures"
            )

        signature = {
            "camera_id": camera_record.get("camera_id"),
            "instance_id": camera_record.get("instance_id"),
            "index": camera_record.get("index"),
            "backend": camera_record.get("backend"),
            "mount_id": coverage.get("mount_id"),
            "requested_settings": dict(requested),
            "effective_settings": dict(effective_before),
            "photo_width": photo.get("width"),
            "photo_height": photo.get("height"),
        }
        if common_signature is None:
            common_signature = signature
        elif signature != common_signature:
            raise SameR20ParityEvidenceBundleError(
                f"capture sidecar ordinal {ordinal} camera or mount signature differs"
            )
        boot_nonce = root.get("boot_nonce")
        if common_boot_nonce is None:
            common_boot_nonce = str(boot_nonce)
        elif boot_nonce != common_boot_nonce:
            raise SameR20ParityEvidenceBundleError(
                f"capture sidecar ordinal {ordinal} boot continuity differs"
            )
        try:
            captured_at = datetime.fromisoformat(str(root.get("captured_at")))
        except ValueError as exc:
            raise SameR20ParityEvidenceBundleError(
                f"capture sidecar ordinal {ordinal} capture time is invalid"
            ) from exc
        if prior_captured_at is not None and captured_at <= prior_captured_at:
            raise SameR20ParityEvidenceBundleError(
                f"capture sidecar ordinal {ordinal} is not later than its predecessor"
            )
        prior_captured_at = captured_at
        integrity = _mapping(
            root.get("integrity"),
            label=f"capture sidecar ordinal {ordinal}.integrity",
        )
        bindings.append(
            {
                "ordinal": ordinal,
                "path": str(path),
                "sidecar_file_sha256": _sha256_bytes(sidecar_payload),
                "canonical_integrity_sha256": integrity.get("sha256"),
                "capture_id": root.get("capture_id"),
                "captured_at": root.get("captured_at"),
                "action_id": root.get("action_id"),
                "descriptor_id": root.get("descriptor_id"),
                "action_result_sha256": action_record.get("file_sha256"),
                "photo_sha256": photo.get("sha256"),
                "capture_binding": camera.BINDING_LIVE,
                "coverage_scope": camera.COVERAGE_FULL,
            }
        )
    assert common_signature is not None
    return bindings, {
        **common_signature,
        "boot_nonce": common_boot_nonce,
        "manual_controls_required": dict(REQUIRED_MANUAL_CAMERA_SETTINGS),
        "same_signature_all_four_captures": True,
        "strictly_increasing_capture_times": True,
    }


def build_bundle(
    action_paths: Sequence[Path],
    capture_sidecar_paths: Sequence[Path],
    repeat_noise_report_path: Path,
    aa_cc_comparison_path: Path,
    aa_analysis: Path,
    white_after_aa_analysis: Path,
    cc_analysis: Path,
    white_after_cc_analysis: Path,
) -> dict[str, Any]:
    """Validate all Batch-1 evidence and return the exact sealed bundle."""

    if len(action_paths) != 4:
        raise SameR20ParityEvidenceBundleError(
            "exactly four action outputs are required"
        )
    actions = same_once.base.runner.ACTIONS
    action_results = [
        _validate_action(
            Path(path),
            ordinal=index,
            action_id=str(actions[index - 1]["action_id"]),
            descriptor_id=str(actions[index - 1]["descriptor_id"]),
            output_name=same_once.ACTION_OUTPUT_NAMES[index],
        )
        for index, path in enumerate(action_paths, 1)
    ]
    noise_binding, repeat_noise_p95 = _validate_noise_report(repeat_noise_report_path)
    aa_file_sha, aa_integrity, aa_photo_sha, aa_geometry_sha, aa_noise = (
        _validate_atlas(aa_analysis, role="AA")
    )
    (
        white_aa_file_sha,
        white_aa_integrity,
        white_aa_photo_sha,
        white_aa_geometry_sha,
        white_aa_noise,
    ) = _validate_white(white_after_aa_analysis, label="white after AA analysis")
    cc_file_sha, cc_integrity, cc_photo_sha, cc_geometry_sha, cc_noise = (
        _validate_atlas(cc_analysis, role="CC")
    )
    (
        white_cc_file_sha,
        white_cc_integrity,
        white_cc_photo_sha,
        white_cc_geometry_sha,
        white_cc_noise,
    ) = _validate_white(white_after_cc_analysis, label="white after CC analysis")
    if any(
        value != noise_binding["reference_geometry_sha256"]
        for value in (
            aa_geometry_sha,
            white_aa_geometry_sha,
            cc_geometry_sha,
            white_cc_geometry_sha,
        )
    ):
        raise SameR20ParityEvidenceBundleError(
            "analysis and repeat-noise geometry bindings differ"
        )
    if any(
        value != repeat_noise_p95
        for value in (aa_noise, white_aa_noise, cc_noise, white_cc_noise)
    ):
        raise SameR20ParityEvidenceBundleError(
            "analysis repeat-noise values differ from the sealed baseline"
        )
    aa_cc_binding = _validate_aa_cc_comparison(
        aa_cc_comparison_path,
        aa_file_sha256=aa_file_sha,
        cc_file_sha256=cc_file_sha,
        reference_geometry_sha256=aa_geometry_sha,
        repeat_noise_p95_de76=repeat_noise_p95,
    )
    capture_bindings, camera_lock = _validate_capture_sidecars(
        capture_sidecar_paths,
        action_results=action_results,
        expected_photo_sha256=(
            aa_photo_sha,
            white_aa_photo_sha,
            cc_photo_sha,
            white_cc_photo_sha,
        ),
    )
    comparable_camera_lock = {
        key: camera_lock[key]
        for key in (
            "camera_id",
            "instance_id",
            "index",
            "backend",
            "mount_id",
            "requested_settings",
            "effective_settings",
        )
    }
    if noise_binding["camera_signature"] != comparable_camera_lock:
        raise SameR20ParityEvidenceBundleError(
            "Batch-1 captures differ from repeat-noise camera or mount"
        )
    report = same_pack.build_report()
    profiles = report["contract"]["profiles"]
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "campaign_id": same_pack.CAMPAIGN_ID,
        "contract_schema": "mf1750-same-r20-parity-contract-v1",
        "contract_id": same_once.base.runner.CONTRACT_ID,
        "action_ids": list(same_once.base.runner.ACTION_IDS),
        "active_global_tuple_id": profiles["active"]["global_tuple_id"],
        "commented_global_tuple_id": profiles["commented"]["global_tuple_id"],
        "outcome": "PASS",
        "active_same_r20_both_controllers": True,
        "commented_same_r20_both_controllers": True,
        "aa_left_right_parity_pass": True,
        "cc_left_right_parity_pass": True,
        "terminal_factory_white_clean_pass": True,
        "candidate_transport_codes_authorized": CANDIDATE_CODES,
        "candidate_codes_are_not_colour_names": True,
        "terminal_factory_white_is_latest_bound_batch1_capture": True,
        "clean_white_visual_outcomes": {
            "ordinal_2": "PASS",
            "ordinal_4": "PASS",
        },
        "automatic_analysis": {
            "active_same_side": "PASS",
            "active_cross_side": "PASS",
            "commented_same_side": "PASS",
            "commented_cross_side": "PASS",
        },
        "capture_evidence_complete": True,
        "repeat_noise_evidence_complete": True,
        "repeat_noise_baseline": noise_binding,
        "aa_cc_comparison": aa_cc_binding,
        "capture_bindings": capture_bindings,
        "camera_lock": camera_lock,
        "action_results": action_results,
        "analysis_bindings": {
            "aa_atlas": {
                "path": str(aa_analysis),
                "file_sha256": aa_file_sha,
                "canonical_integrity_sha256": aa_integrity,
                "source_photo_sha256": aa_photo_sha,
                "reference_geometry_sha256": aa_geometry_sha,
                "repeat_noise_p95_de76": aa_noise,
                "interpretation": "panel geometry and eight paired codes passed",
            },
            "white_after_aa": {
                "path": str(white_after_aa_analysis),
                "file_sha256": white_aa_file_sha,
                "canonical_integrity_sha256": white_aa_integrity,
                "source_photo_sha256": white_aa_photo_sha,
                "reference_geometry_sha256": white_aa_geometry_sha,
                "repeat_noise_p95_de76": white_aa_noise,
            },
            "cc_atlas": {
                "path": str(cc_analysis),
                "file_sha256": cc_file_sha,
                "canonical_integrity_sha256": cc_integrity,
                "source_photo_sha256": cc_photo_sha,
                "reference_geometry_sha256": cc_geometry_sha,
                "repeat_noise_p95_de76": cc_noise,
                "interpretation": "panel geometry and eight paired codes passed",
            },
            "white_after_cc": {
                "path": str(white_after_cc_analysis),
                "file_sha256": white_cc_file_sha,
                "canonical_integrity_sha256": white_cc_integrity,
                "source_photo_sha256": white_cc_photo_sha,
                "reference_geometry_sha256": white_cc_geometry_sha,
                "repeat_noise_p95_de76": white_cc_noise,
            },
        },
        "evidence_boundaries": {
            "camera_relative_de76_not_calibrated_de00": True,
            "same_side_pass_means_geometry_and_complete_cell_coverage": True,
            "cross_side_pass_means_same_code_camera_relative_parity": True,
            "compiled_payload_identity_not_bus_capture": True,
            "every_analysis_photo_bound_to_live_synchronized_action_capture": True,
            "full_panel_camera_coverage_required": True,
            "manual_camera_controls_and_mount_locked_across_batch": True,
            "analysis_threshold_bound_to_sealed_repeat_noise_report": True,
            "aa_cc_comparison_is_exploratory_not_causal": True,
            "external_refresh_after_last_bound_capture_not_proven": True,
            "candidate_codes_are_transport_codes_only": True,
            "no_absolute_colour_or_new_colour_claim": True,
            "device_io_performed_by_bundle_builder": False,
        },
        "output_write_contract": "O_EXCL",
    }
    unsigned["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": _sha256_bytes(_canonical_json(unsigned)),
    }
    return unsigned


def _write_exclusive(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, flags, 0o644)
    except FileExistsError as exc:
        raise SameR20ParityEvidenceBundleError(
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
    parser.add_argument("--action-output", type=Path, action="append", required=True)
    parser.add_argument("--capture-sidecar", type=Path, action="append", required=True)
    parser.add_argument("--repeat-noise-report", type=Path, required=True)
    parser.add_argument("--aa-cc-comparison", type=Path, required=True)
    parser.add_argument("--aa-analysis", type=Path, required=True)
    parser.add_argument("--white-after-aa-analysis", type=Path, required=True)
    parser.add_argument("--cc-analysis", type=Path, required=True)
    parser.add_argument("--white-after-cc-analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = build_bundle(
            args.action_output,
            args.capture_sidecar,
            args.repeat_noise_report,
            args.aa_cc_comparison,
            args.aa_analysis,
            args.white_after_aa_analysis,
            args.cc_analysis,
            args.white_after_cc_analysis,
        )
        payload = (
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False).encode(
                "utf-8"
            )
            + b"\n"
        )
        _write_exclusive(args.output, payload)
        sys.stdout.buffer.write(payload)
        return 0
    except SameR20ParityEvidenceBundleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
