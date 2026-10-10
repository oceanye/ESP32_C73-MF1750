#!/usr/bin/env python3
"""Seal four-frame repeat evidence for the Same-R20 AA atlas.

The first frame must be the synchronized live capture of action ordinal 1.
The remaining three frames must be locked-camera captures of the retained
screen state.  This program performs no camera, panel, relay, serial, or
network I/O; it only validates already-sealed inputs and writes one new
``O_EXCL`` report.

The result is deliberately narrow.  A repeated left/right delta is labelled
only as a *camera-relative repeat mismatch candidate*.  It does not prove a
controller defect, a hardware defect, absolute colour, or controller
inequivalence.  The retained sidecars also cannot, by themselves, prove the
operator's physical J2-OFF assertion.
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
import stat
import statistics
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_camera_capture_evidence as camera  # noqa: E402
from tools import mf1750_runtime_lut_same_r20_parity_v1_once as same_once  # noqa: E402
from tools import mf1750_runtime_lut_same_r20_parity_v1_pack as same_pack  # noqa: E402
from tools import (  # noqa: E402
    mf1750_same_r20_aa_cc_paired_comparison as atlas_contract,
)


SCHEMA_VERSION = 1
KIND = "mf1750-same-r20-aa-four-frame-retained-repeat-report-v1"
METHOD_ID = "same-r20-aa-left-right-four-frame-repeat-majority-v1"
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
FRAME_COUNT = 4
RETAINED_FRAME_COUNT = 3
CODE_COUNT = 8
CONSISTENT_EXCEEDANCE_MINIMUM = 3
EXPECTED_ANALYSIS_ROLE = "AA"
EXPECTED_ACTION_ROLE = same_pack.ROLES[0]
RETAINED_PROCEDURE_MARKER = "retained-state-repeat-not-a-new-action"

ANALYSIS_TOP_LEVEL_KEYS = {
    "schema_version",
    "kind",
    "analysis_id",
    "role",
    "layout",
    "source_photo",
    "reference_geometry",
    "geometry_guard",
    "cells",
    "left_right_pairs",
    "paired_summary",
    "classification",
    "evidence_boundaries",
    "output_write_contract",
    "integrity",
}


class SameR20AARetainedRepeatReportError(RuntimeError):
    """Raised when an input or exclusive output is invalid."""


class _DuplicateKeyError(ValueError):
    pass


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
        raise SameR20AARetainedRepeatReportError(
            f"record contains a non-canonical JSON value: {exc}"
        ) from exc


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_stable_regular(path: Path, *, label: str) -> bytes:
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise SameR20AARetainedRepeatReportError(
                f"{label} must be a regular non-symlink file: {path}"
            )
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise SameR20AARetainedRepeatReportError(f"cannot read {label}: {exc}") from exc
    before_id = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_id = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_id != after_id or len(payload) != after.st_size:
        raise SameR20AARetainedRepeatReportError(f"{label} changed while read")
    return payload


def _load_json(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    payload = _read_stable_regular(path, label=label)
    try:
        root = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {item}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SameR20AARetainedRepeatReportError(
            f"{label} is not strict UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(root, dict):
        raise SameR20AARetainedRepeatReportError(f"{label} root must be an object")
    return payload, root


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SameR20AARetainedRepeatReportError(f"{label} must be an object")
    return value


def _number(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SameR20AARetainedRepeatReportError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise SameR20AARetainedRepeatReportError(f"{label} must be a finite number")
    return result


def _same_number(first: float, second: float) -> bool:
    return math.isclose(first, second, rel_tol=1e-12, abs_tol=1e-9)


def _sha256(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise SameR20AARetainedRepeatReportError(f"{label} must be a lowercase SHA-256")
    return value


def _verify_integrity(root: Mapping[str, Any], *, label: str) -> str:
    integrity = _mapping(root.get("integrity"), label=f"{label}.integrity")
    if set(integrity) != {"algorithm", "sha256"}:
        raise SameR20AARetainedRepeatReportError(f"{label}.integrity keys differ")
    if integrity.get("algorithm") != INTEGRITY_ALGORITHM:
        raise SameR20AARetainedRepeatReportError(f"{label}.integrity algorithm differs")
    declared = _sha256(integrity.get("sha256"), label=f"{label}.integrity.sha256")
    unsigned = dict(root)
    unsigned.pop("integrity", None)
    if _sha256_bytes(_canonical_json(unsigned)) != declared:
        raise SameR20AARetainedRepeatReportError(f"{label}.integrity SHA differs")
    return declared


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        raise SameR20AARetainedRepeatReportError("percentile input is empty")
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1.0 - weight) + ordered[upper] * weight)


def _validate_analysis(path: Path, *, frame_index: int) -> dict[str, Any]:
    label = f"analysis frame {frame_index}"
    payload, root = _load_json(path, label=label)
    if set(root) != ANALYSIS_TOP_LEVEL_KEYS:
        raise SameR20AARetainedRepeatReportError(f"{label} top-level keys differ")
    if (
        root.get("schema_version") != atlas_contract.ANALYSIS_SCHEMA_VERSION
        or root.get("kind") != atlas_contract.ANALYSIS_KIND
        or root.get("role") != EXPECTED_ANALYSIS_ROLE
    ):
        raise SameR20AARetainedRepeatReportError(
            f"{label} schema identity or role differs"
        )
    integrity = _verify_integrity(root, label=label)
    try:
        layout = atlas_contract._validate_layout(root, label=label)
        source_photo = atlas_contract._validate_source_photo(root, label=label)
        reference_geometry = atlas_contract._validate_reference_geometry(
            root, label=label
        )
        cells, minimum_valid_fraction, contrasting_count = (
            atlas_contract._validate_cells(root, label=label)
        )
        atlas_contract._validate_geometry_guard(
            root,
            minimum_cell_valid_fraction=minimum_valid_fraction,
            contrasting_cell_count=contrasting_count,
            label=label,
        )
        deltas = atlas_contract._validate_pairs(root, cells, label=label)
        atlas_contract._validate_boundaries(root, label=label)
    except atlas_contract.SameR20AACCComparisonError as exc:
        raise SameR20AARetainedRepeatReportError(str(exc)) from exc

    analysis_id = _sha256(root.get("analysis_id"), label=f"{label}.analysis_id")
    expected_analysis_id = _sha256_bytes(
        _canonical_json(
            {
                "photo_sha256": source_photo["sha256"],
                "reference_file_sha256": reference_geometry["file_sha256"],
                "role": EXPECTED_ANALYSIS_ROLE,
                "method": atlas_contract.ANALYSIS_METHOD_ID,
            }
        )
    )
    if analysis_id != expected_analysis_id:
        raise SameR20AARetainedRepeatReportError(f"{label}.analysis_id binding differs")

    summary = _mapping(root.get("paired_summary"), label=f"{label}.paired_summary")
    expected_summary_keys = {
        "camera_relative_de76_median",
        "camera_relative_de76_p95",
        "camera_relative_de76_max",
        "repeat_noise_p95_de76",
        "exploratory_threshold_de76",
        "all_pairs_within_exploratory_threshold",
    }
    if set(summary) != expected_summary_keys:
        raise SameR20AARetainedRepeatReportError(f"{label}.paired_summary keys differ")
    noise = _number(
        summary.get("repeat_noise_p95_de76"),
        label=f"{label}.paired_summary.repeat_noise_p95_de76",
    )
    threshold = _number(
        summary.get("exploratory_threshold_de76"),
        label=f"{label}.paired_summary.exploratory_threshold_de76",
    )
    expected_threshold = max(4.0, 3.0 * noise)
    expected_gate = all(delta <= expected_threshold for delta in deltas)
    if (
        noise < 0.0
        or not _same_number(threshold, expected_threshold)
        or not _same_number(
            _number(
                summary.get("camera_relative_de76_median"),
                label=f"{label}.paired_summary.camera_relative_de76_median",
            ),
            statistics.median(deltas),
        )
        or not _same_number(
            _number(
                summary.get("camera_relative_de76_p95"),
                label=f"{label}.paired_summary.camera_relative_de76_p95",
            ),
            _percentile(deltas, 0.95),
        )
        or not _same_number(
            _number(
                summary.get("camera_relative_de76_max"),
                label=f"{label}.paired_summary.camera_relative_de76_max",
            ),
            max(deltas),
        )
        or summary.get("all_pairs_within_exploratory_threshold") is not expected_gate
    ):
        raise SameR20AARetainedRepeatReportError(
            f"{label}.paired_summary derived fields differ"
        )
    classification = _mapping(
        root.get("classification"), label=f"{label}.classification"
    )
    expected_classification = {
        "state": (
            "CAMERA_RELATIVE_CONTROLLER_MATCH_CANDIDATE"
            if expected_gate
            else "CAMERA_RELATIVE_CONTROLLER_MISMATCH_CANDIDATE"
        ),
        "controller_equivalence_proven": False,
        "absolute_colour_proven": False,
        "qualified_new_colour": False,
    }
    if dict(classification) != expected_classification:
        raise SameR20AARetainedRepeatReportError(
            f"{label}.classification differs from recomputed gate"
        )
    return {
        "path": str(path),
        "payload": payload,
        "file_sha256": _sha256_bytes(payload),
        "canonical_integrity_sha256": integrity,
        "analysis_id": analysis_id,
        "layout": layout,
        "source_photo": source_photo,
        "reference_geometry": reference_geometry,
        "noise": noise,
        "threshold": expected_threshold,
        "deltas": deltas,
        "input_classification_state": expected_classification["state"],
    }


def _manual_request_is_locked(settings: Mapping[str, Any], *, label: str) -> None:
    expected = {"autofocus": 0.0, "auto_exposure": 0.25, "auto_white_balance": 0.0}
    for field, wanted in expected.items():
        value = _number(settings.get(field), label=f"{label}.{field}")
        if value != wanted:
            raise SameR20AARetainedRepeatReportError(f"{label}.{field} is not locked")
    for field in ("focus", "exposure", "white_balance_temperature"):
        _number(settings.get(field), label=f"{label}.{field}")


def _validate_capture(path: Path, *, frame_index: int) -> dict[str, Any]:
    label = f"capture sidecar frame {frame_index}"
    payload_before = _read_stable_regular(path, label=label)
    try:
        root = camera.validate_capture_evidence(path)
    except camera.CameraCaptureEvidenceError as exc:
        raise SameR20AARetainedRepeatReportError(str(exc)) from exc
    payload_after = _read_stable_regular(path, label=label)
    if payload_before != payload_after:
        raise SameR20AARetainedRepeatReportError(f"{label} changed while validated")

    expected_binding = (
        camera.BINDING_LIVE if frame_index == 1 else camera.BINDING_LOCKED_RETAINED
    )
    expected_action = same_once.base.runner.ACTIONS[0]
    if (
        root.get("capture_binding") != expected_binding
        or root.get("campaign_id") != same_pack.CAMPAIGN_ID
        or root.get("test_id") != same_pack.TEST_ID
        or root.get("contract_id") != same_once.base.runner.CONTRACT_ID
        or root.get("firmware_sha256") != same_once.FIRMWARE_SHA256
        or root.get("ordinal") != 1
        or root.get("action_id") != expected_action["action_id"]
        or root.get("descriptor_id") != expected_action["descriptor_id"]
        or root.get("role") != EXPECTED_ACTION_ROLE
        or root.get("frame_sha256") != expected_action["frame_sha256"]
    ):
        raise SameR20AARetainedRepeatReportError(
            f"{label} Same-R20 AA action identity, role, ordinal, or binding differs"
        )

    action = _mapping(root.get("action_result"), label=f"{label}.action_result")
    if (
        action.get("outcome") != "complete_pass"
        or action.get("terminal_state") != "COMPLETE"
        or action.get("visible_refreshes") != 1
    ):
        raise SameR20AARetainedRepeatReportError(
            f"{label} historical action completion differs"
        )
    coverage = _mapping(root.get("coverage"), label=f"{label}.coverage")
    if (
        coverage.get("scope") != camera.COVERAGE_FULL
        or coverage.get("full_panel_visible") is not True
        or coverage.get("full_panel_uncropped") is not True
    ):
        raise SameR20AARetainedRepeatReportError(f"{label} is not full-panel evidence")
    camera_record = _mapping(root.get("camera"), label=f"{label}.camera")
    requested = _mapping(
        camera_record.get("requested_settings"),
        label=f"{label}.camera.requested_settings",
    )
    effective_before = _mapping(
        camera_record.get("effective_settings_before_frame"),
        label=f"{label}.camera.effective_settings_before_frame",
    )
    effective_after = _mapping(
        camera_record.get("effective_settings_after_frame"),
        label=f"{label}.camera.effective_settings_after_frame",
    )
    _manual_request_is_locked(requested, label=f"{label}.camera.requested_settings")
    if dict(effective_before) != dict(effective_after):
        raise SameR20AARetainedRepeatReportError(
            f"{label} effective camera settings drifted within the frame"
        )
    set_results = _mapping(
        camera_record.get("set_results"), label=f"{label}.camera.set_results"
    )
    if not set_results or any(value is not True for value in set_results.values()):
        raise SameR20AARetainedRepeatReportError(
            f"{label} has a failed camera setting write"
        )
    if camera_record.get("read_failures") != 0:
        raise SameR20AARetainedRepeatReportError(f"{label} has camera read failures")

    photo = _mapping(root.get("photo"), label=f"{label}.photo")
    requested_width = requested.get("frame_width")
    requested_height = requested.get("frame_height")
    effective_width = effective_before.get("frame_width")
    effective_height = effective_before.get("frame_height")
    if (
        requested_width != photo.get("width")
        or requested_height != photo.get("height")
        or not _same_number(
            _number(effective_width, label=f"{label}.effective.frame_width"),
            float(photo.get("width")),
        )
        or not _same_number(
            _number(effective_height, label=f"{label}.effective.frame_height"),
            float(photo.get("height")),
        )
    ):
        raise SameR20AARetainedRepeatReportError(
            f"{label} camera and photo geometry differ"
        )

    assessment = _mapping(
        root.get("automated_assessment"), label=f"{label}.automated_assessment"
    )
    limitations = assessment.get("limitations")
    if frame_index > 1 and (
        not isinstance(limitations, list)
        or RETAINED_PROCEDURE_MARKER not in limitations
        or camera.LOCKED_RETAINED_LIMITATION not in limitations
    ):
        raise SameR20AARetainedRepeatReportError(
            f"{label} retained-state limitations differ"
        )
    try:
        captured_at = datetime.fromisoformat(str(root.get("captured_at")))
    except ValueError as exc:
        raise SameR20AARetainedRepeatReportError(
            f"{label}.captured_at is invalid"
        ) from exc
    if captured_at.tzinfo is None:
        raise SameR20AARetainedRepeatReportError(
            f"{label}.captured_at must include a UTC offset"
        )
    integrity = _mapping(root.get("integrity"), label=f"{label}.integrity")
    signature = {
        "camera_id": camera_record.get("camera_id"),
        "instance_id": camera_record.get("instance_id"),
        "index": camera_record.get("index"),
        "backend": camera_record.get("backend"),
        "mount_id": coverage.get("mount_id"),
        "requested_settings": dict(requested),
        "effective_settings": dict(effective_before),
        "set_results": dict(set_results),
        "warmup_frames_requested": camera_record.get("warmup_frames_requested"),
        "warmup_frames_completed": camera_record.get("warmup_frames_completed"),
        "photo_width": photo.get("width"),
        "photo_height": photo.get("height"),
    }
    return {
        "path": str(path),
        "file_sha256": _sha256_bytes(payload_before),
        "canonical_integrity_sha256": integrity.get("sha256"),
        "capture_id": root.get("capture_id"),
        "capture_binding": expected_binding,
        "captured_at": root.get("captured_at"),
        "captured_at_value": captured_at,
        "boot_nonce": root.get("boot_nonce"),
        "action_result_sha256": action.get("file_sha256"),
        "photo": dict(photo),
        "signature": signature,
    }


def _cross_validate(
    analyses: Sequence[Mapping[str, Any]],
    captures: Sequence[Mapping[str, Any]],
) -> tuple[float, float, dict[str, Any]]:
    first_analysis = analyses[0]
    first_capture = captures[0]
    common_geometry = first_analysis["reference_geometry"]
    common_photo_geometry = (
        first_analysis["source_photo"]["width"],
        first_analysis["source_photo"]["height"],
    )
    prior_time: datetime | None = None
    photo_hashes: set[str] = set()
    capture_ids: set[str] = set()
    analysis_ids: set[str] = set()
    for frame_index, (analysis, capture) in enumerate(
        zip(analyses, captures, strict=True), 1
    ):
        if analysis["layout"] != first_analysis["layout"]:
            raise SameR20AARetainedRepeatReportError(
                f"analysis frame {frame_index} layout differs"
            )
        for key in ("bytes", "file_sha256", "canonical_integrity_sha256"):
            if analysis["reference_geometry"][key] != common_geometry[key]:
                raise SameR20AARetainedRepeatReportError(
                    f"analysis frame {frame_index} reference geometry differs"
                )
        if (
            analysis["source_photo"]["width"],
            analysis["source_photo"]["height"],
        ) != common_photo_geometry:
            raise SameR20AARetainedRepeatReportError(
                f"analysis frame {frame_index} photo geometry differs"
            )
        if not _same_number(float(analysis["noise"]), float(first_analysis["noise"])):
            raise SameR20AARetainedRepeatReportError(
                f"analysis frame {frame_index} repeat-noise binding differs"
            )
        if not _same_number(
            float(analysis["threshold"]), float(first_analysis["threshold"])
        ):
            raise SameR20AARetainedRepeatReportError(
                f"analysis frame {frame_index} threshold differs"
            )
        photo = capture["photo"]
        source = analysis["source_photo"]
        for key in ("bytes", "sha256", "width", "height"):
            if source[key] != photo[key]:
                raise SameR20AARetainedRepeatReportError(
                    f"frame {frame_index} analysis/photo binding differs"
                )
        if capture["signature"] != first_capture["signature"]:
            raise SameR20AARetainedRepeatReportError(
                f"capture frame {frame_index} camera or mount signature differs"
            )
        for key in ("boot_nonce", "action_result_sha256"):
            if capture[key] != first_capture[key]:
                raise SameR20AARetainedRepeatReportError(
                    f"capture frame {frame_index} action continuity fields differ"
                )
        captured_at = capture["captured_at_value"]
        if prior_time is not None and captured_at <= prior_time:
            raise SameR20AARetainedRepeatReportError(
                f"capture frame {frame_index} is not later than its predecessor"
            )
        prior_time = captured_at
        photo_hashes.add(str(photo["sha256"]))
        capture_ids.add(str(capture["capture_id"]))
        analysis_ids.add(str(analysis["analysis_id"]))
    if (
        len(photo_hashes) != FRAME_COUNT
        or len(capture_ids) != FRAME_COUNT
        or len(analysis_ids) != FRAME_COUNT
    ):
        raise SameR20AARetainedRepeatReportError(
            "all four photos, captures, and analyses must be distinct"
        )
    return (
        float(first_analysis["noise"]),
        float(first_analysis["threshold"]),
        dict(first_capture["signature"]),
    )


def build_report(
    analysis_paths: Sequence[Path], capture_sidecar_paths: Sequence[Path]
) -> dict[str, Any]:
    """Validate four paired frames and return a sealed offline repeat report."""

    if len(analysis_paths) != FRAME_COUNT or len(capture_sidecar_paths) != FRAME_COUNT:
        raise SameR20AARetainedRepeatReportError(
            "exactly four analyses and four capture sidecars are required"
        )
    if len({Path(path).resolve() for path in analysis_paths}) != FRAME_COUNT:
        raise SameR20AARetainedRepeatReportError("analysis paths must be distinct")
    if len({Path(path).resolve() for path in capture_sidecar_paths}) != FRAME_COUNT:
        raise SameR20AARetainedRepeatReportError(
            "capture sidecar paths must be distinct"
        )
    analyses = [
        _validate_analysis(Path(path), frame_index=index)
        for index, path in enumerate(analysis_paths, 1)
    ]
    captures = [
        _validate_capture(Path(path), frame_index=index)
        for index, path in enumerate(capture_sidecar_paths, 1)
    ]
    noise, threshold, camera_signature = _cross_validate(analyses, captures)

    per_code: list[dict[str, Any]] = []
    consistent_codes: list[int] = []
    unanimous_codes: list[int] = []
    for code in range(CODE_COUNT):
        deltas = [float(analysis["deltas"][code]) for analysis in analyses]
        exceedance_indices = [
            index for index, delta in enumerate(deltas, 1) if delta > threshold
        ]
        exceedance_count = len(exceedance_indices)
        consistent = exceedance_count >= CONSISTENT_EXCEEDANCE_MINIMUM
        unanimous = exceedance_count == FRAME_COUNT
        if consistent:
            consistent_codes.append(code)
        if unanimous:
            unanimous_codes.append(code)
        per_code.append(
            {
                "code": code,
                "four_frame_camera_relative_de76": deltas,
                "camera_relative_de76_median": float(statistics.median(deltas)),
                "camera_relative_de76_min": float(min(deltas)),
                "camera_relative_de76_max": float(max(deltas)),
                "camera_relative_de76_p95": _percentile(deltas, 0.95),
                "exploratory_threshold_de76": threshold,
                "threshold_exceedance_count": exceedance_count,
                "threshold_exceedance_frame_indices": exceedance_indices,
                "consistent_threshold_exceedance_3_of_4": consistent,
                "unanimous_threshold_exceedance_4_of_4": unanimous,
                "classification": (
                    "CAMERA_RELATIVE_REPEAT_MISMATCH_CANDIDATE"
                    if consistent
                    else "NO_REPEATABLE_CAMERA_RELATIVE_MISMATCH_RESOLVED"
                ),
            }
        )

    frame_bindings = []
    for frame_index, (analysis, capture) in enumerate(
        zip(analyses, captures, strict=True), 1
    ):
        frame_bindings.append(
            {
                "frame_index": frame_index,
                "analysis": {
                    "path": analysis["path"],
                    "file_sha256": analysis["file_sha256"],
                    "canonical_integrity_sha256": analysis[
                        "canonical_integrity_sha256"
                    ],
                    "analysis_id": analysis["analysis_id"],
                    "role": EXPECTED_ANALYSIS_ROLE,
                    "source_photo_sha256": analysis["source_photo"]["sha256"],
                    "input_classification_state": analysis[
                        "input_classification_state"
                    ],
                },
                "capture": {
                    "path": capture["path"],
                    "file_sha256": capture["file_sha256"],
                    "canonical_integrity_sha256": capture["canonical_integrity_sha256"],
                    "capture_id": capture["capture_id"],
                    "capture_binding": capture["capture_binding"],
                    "captured_at": capture["captured_at"],
                    "photo_sha256": capture["photo"]["sha256"],
                },
            }
        )

    mismatch_candidate = bool(consistent_codes)
    expected_action = same_once.base.runner.ACTIONS[0]
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "report_id": _sha256_bytes(
            _canonical_json(
                {
                    "analysis_file_sha256": [
                        analysis["file_sha256"] for analysis in analyses
                    ],
                    "capture_sidecar_file_sha256": [
                        capture["file_sha256"] for capture in captures
                    ],
                    "method": METHOD_ID,
                    "threshold": threshold,
                }
            )
        ),
        "method_id": METHOD_ID,
        "campaign_id": same_pack.CAMPAIGN_ID,
        "contract_id": same_once.base.runner.CONTRACT_ID,
        "firmware_sha256": same_once.FIRMWARE_SHA256,
        "action_binding": {
            "ordinal": 1,
            "role": EXPECTED_ACTION_ROLE,
            "action_id": expected_action["action_id"],
            "descriptor_id": expected_action["descriptor_id"],
            "frame_sha256": expected_action["frame_sha256"],
            "historical_action_visible_refreshes": 1,
            "same_action_result_all_four_frames": True,
            "same_boot_nonce_all_four_frames": True,
        },
        "capture_sequence": {
            "frame_count": FRAME_COUNT,
            "live_synchronized_frame_count": 1,
            "locked_retained_frame_count": RETAINED_FRAME_COUNT,
            "first_frame_live_then_three_retained": True,
            "strictly_increasing_capture_times": True,
            "all_photos_and_captures_distinct": True,
            "frame_bindings": frame_bindings,
        },
        "shared_bindings": {
            "layout": analyses[0]["layout"],
            "reference_geometry": {
                "bytes": analyses[0]["reference_geometry"]["bytes"],
                "file_sha256": analyses[0]["reference_geometry"]["file_sha256"],
                "canonical_integrity_sha256": analyses[0]["reference_geometry"][
                    "canonical_integrity_sha256"
                ],
                "camera_must_not_have_moved": True,
            },
            "photo_geometry": {
                "width": analyses[0]["source_photo"]["width"],
                "height": analyses[0]["source_photo"]["height"],
            },
            "camera_and_mount_signature": camera_signature,
        },
        "thresholds": {
            "repeat_noise_p95_de76": noise,
            "exploratory_threshold_de76": threshold,
            "exploratory_threshold_formula": ("max(4.0, 3.0 * repeat_noise_p95_de76)"),
            "per_frame_exceedance_rule": "camera_relative_de76 > threshold",
            "consistent_exceedance_required_frames": (CONSISTENT_EXCEEDANCE_MINIMUM),
            "consistent_exceedance_total_frames": FRAME_COUNT,
            "consistent_exceedance_rule": "at least 3 of 4 frames exceed threshold",
            "why_not_2_of_4": (
                "2 of 4 is a tie and is not treated as a repeat-majority result"
            ),
        },
        "per_code": per_code,
        "summary": {
            "code_count": CODE_COUNT,
            "consistent_threshold_exceedance_code_count": len(consistent_codes),
            "consistent_threshold_exceedance_codes": consistent_codes,
            "unanimous_threshold_exceedance_code_count": len(unanimous_codes),
            "unanimous_threshold_exceedance_codes": unanimous_codes,
        },
        "classification": {
            "state": (
                "CAMERA_RELATIVE_REPEAT_MISMATCH_CANDIDATE"
                if mismatch_candidate
                else "NO_REPEATABLE_CAMERA_RELATIVE_MISMATCH_RESOLVED"
            ),
            "camera_relative_repeat_mismatch_candidate": mismatch_candidate,
            "controller_mismatch_proven": False,
            "hardware_mismatch_proven": False,
            "controller_equivalence_proven": False,
            "absolute_colour_proven": False,
            "qualified_new_colour": False,
        },
        "campaign_control": {
            "next_same_campaign_ordinal_allowed": not mismatch_candidate,
            "campaign_disposition": (
                "STOPPED_AT_ORDINAL_1_CAMERA_MISMATCH_CANDIDATE"
                if mismatch_candidate
                else "ORDINAL_1_REPEAT_GATE_PASSED_SUBJECT_TO_OTHER_GATES"
            ),
            "planned_ordinal_2_role": same_once.base.runner.ACTIONS[1]["role"],
            "planned_ordinal_2_is_recovery": False,
            "planned_ordinal_2_must_not_be_used_as_recovery": True,
            "original_ordinal_1_action_was_not_modified_by_this_tool": True,
        },
        "retained_capture_semantics": {
            "capture_tool_performed_display_refreshes": 0,
            "capture_tool_performed_relay_operations": 0,
            "retained_captures_are_not_new_actions": True,
            "physical_j2_off_proven_by_these_inputs": False,
            "physical_j2_off_requires_external_relay_or_operator_evidence": True,
        },
        "evidence_boundaries": {
            "camera_relative_de76_not_calibrated_de00": True,
            "repeat_majority_is_candidate_not_controller_or_hardware_proof": True,
            "same_action_binding_does_not_prove_retained_state_continuity": True,
            "locked_camera_does_not_remove_spatial_illumination_bias": True,
            "no_absolute_colour_or_new_colour_claim": True,
            "device_io_performed": False,
            "network_io_performed": False,
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
        raise SameR20AARetainedRepeatReportError(
            f"refusing to overwrite existing output: {path}"
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
    parser.add_argument(
        "--analysis",
        type=Path,
        action="append",
        required=True,
        help="repeat exactly four times: live analysis first, then retained repeats",
    )
    parser.add_argument(
        "--capture-sidecar",
        type=Path,
        action="append",
        required=True,
        help="repeat exactly four times in the same order as --analysis",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = build_report(args.analysis, args.capture_sidecar)
        payload = (
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False).encode(
                "utf-8"
            )
            + b"\n"
        )
        _write_exclusive(args.output, payload)
        sys.stdout.buffer.write(payload)
        return 0
    except SameR20AARetainedRepeatReportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
