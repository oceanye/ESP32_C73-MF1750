#!/usr/bin/env python3
"""Offline W1-flat-field coarse screen for three sealed RAW-P16 T1 frames.

This is deliberately a *screening* tool, not a replacement for the formal
T1 position/temporal gate.  It deep-validates the three existing T1 analyses
and their capture evidence, deep-validates one W1 post-capture analysis, then
samples the W1 white photograph through each T1 homography.  No camera,
network, serial, relay, firmware, or display operation is available here.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
import json
import math
import os
from pathlib import Path
import statistics
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.color_pipeline.color import (  # noqa: E402
    delta_e_ciede2000,
    srgb8_to_lab,
)
from tools import mf1750_camera_capture_evidence as camera  # noqa: E402
from tools import mf1750_camera_post_capture_analysis as post  # noqa: E402
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_position_balanced_photo_analyzer as photo,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t1_t2_profile_comparison as strict,
)


SCHEMA_VERSION = 1
KIND = "mf1750-raw-p16-crossover-t1-white-normalized-coarse-screen-v1"
METHOD_ID = "t1-three-frame-w1-white-flat-field-coarse-screen-v1"
INTEGRITY_ALGORITHM = strict.INTEGRITY_ALGORITHM
WHITE_REFERENCE_MIN_LSTAR = 25.0
NORMALIZATION_TARGET_RGB = 220.0
VALID_POSITIONS_PER_FRAME = 3
VALID_FRAMES_PER_GROUP = 2
DOMINANT_BUCKET_POSITIONS = 3
POSITION_PASS_MAX_DE00 = 8.0
POSITION_REVIEW_MAX_DE00 = 12.0
TEMPORAL_PASS_MAX_DE76 = 3.0
TEMPORAL_REVIEW_MAX_DE76 = 6.0


class CoarseScreenError(RuntimeError):
    """Raised when evidence is invalid or output cannot be created safely."""


def _read_and_hash(path: Path, *, label: str) -> tuple[bytes, str]:
    try:
        payload = strict._read_stable_regular(path, label=label)  # noqa: SLF001
    except strict.CrossoverProfileComparisonError as error:
        raise CoarseScreenError(str(error)) from error
    return payload, strict.sha256_bytes(payload)


def _require_equal(observed: Any, expected: Any, *, label: str) -> None:
    if observed != expected:
        raise CoarseScreenError(f"{label} differs")


def _capture_alignment(capture: Mapping[str, Any]) -> dict[str, Any]:
    camera_record = capture["camera"]
    coverage = capture["coverage"]
    source_photo = capture["photo"]
    return {
        "instance_id": camera_record["instance_id"],
        "mount_id": coverage["mount_id"],
        "requested_settings": camera_record["requested_settings"],
        "effective_settings_before_frame": camera_record[
            "effective_settings_before_frame"
        ],
        "effective_settings_after_frame": camera_record[
            "effective_settings_after_frame"
        ],
        "photo_width": source_photo["width"],
        "photo_height": source_photo["height"],
    }


def _validate_capture_alignment(fingerprints: Sequence[Mapping[str, Any]]) -> None:
    if len(fingerprints) != 4:
        raise CoarseScreenError("capture alignment requires three T1 and one W1 record")
    reference = dict(fingerprints[0])
    for index, fingerprint in enumerate(fingerprints[1:], 2):
        if dict(fingerprint) != reference:
            raise CoarseScreenError(
                f"T1/W1 capture alignment fingerprint {index} differs"
            )


def _deep_validate_t1_source(
    analysis_path: Path, frame: Mapping[str, Any], *, index: int
) -> tuple[dict[str, Any], bytes]:
    """Re-read and byte-bind the capture, action, and JPEG behind one T1 JSON."""

    try:
        _analysis_payload, root = strict._load_json(  # noqa: SLF001
            analysis_path, label=f"T1 analysis {index}"
        )
    except strict.CrossoverProfileComparisonError as error:
        raise CoarseScreenError(str(error)) from error
    source = root["source_evidence"]
    records: dict[str, dict[str, Any]] = {}
    payloads: dict[str, bytes] = {}
    for name in ("capture_sidecar", "action_result", "photo"):
        declared = source[name]
        path = Path(declared["path"]).resolve()
        payload, digest = _read_and_hash(path, label=f"T1 {index} {name}")
        _require_equal(
            len(payload), declared["bytes"], label=f"T1 {index} {name} bytes"
        )
        _require_equal(digest, declared["sha256"], label=f"T1 {index} {name} SHA-256")
        records[name] = {
            "path": path.as_posix(),
            "bytes": len(payload),
            "file_sha256": digest,
        }
        payloads[name] = payload

    capture_path = Path(source["capture_sidecar"]["path"]).resolve()
    try:
        validated_capture = camera.validate_capture_evidence(capture_path)
    except Exception as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        raise CoarseScreenError(
            f"T1 {index} capture evidence deep validation failed: {error}"
        ) from error
    capture_integrity = validated_capture["integrity"]["sha256"]
    _require_equal(
        capture_integrity,
        source["capture_sidecar"]["canonical_integrity_sha256"],
        label=f"T1 {index} capture canonical integrity",
    )
    try:
        action_root = json.loads(payloads["action_result"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CoarseScreenError(f"T1 {index} action is not UTF-8 JSON") from error
    _require_equal(
        action_root.get("integrity", {}).get("sha256"),
        source["action_result"]["canonical_integrity_sha256"],
        label=f"T1 {index} action canonical integrity",
    )

    try:
        rgb = photo.base._decode_rgb(payloads["photo"])  # noqa: SLF001
    except photo.CrossoverPhotoAnalysisError as error:
        raise CoarseScreenError(f"T1 {index} photo decode failed: {error}") from error
    _require_equal(rgb.shape[1], source["photo"]["width"], label="T1 photo width")
    _require_equal(rgb.shape[0], source["photo"]["height"], label="T1 photo height")
    records["capture_sidecar"]["canonical_integrity_sha256"] = capture_integrity
    records["action_result"]["canonical_integrity_sha256"] = action_root["integrity"][
        "sha256"
    ]
    records["photo"]["width"] = int(rgb.shape[1])
    records["photo"]["height"] = int(rgb.shape[0])
    alignment = _capture_alignment(validated_capture)
    _require_equal(
        alignment["photo_width"], records["photo"]["width"], label="T1 photo width"
    )
    _require_equal(
        alignment["photo_height"],
        records["photo"]["height"],
        label="T1 photo height",
    )
    return {
        "analysis_path": Path(frame["path"]).as_posix(),
        "analysis_bytes": frame["bytes"],
        "analysis_file_sha256": frame["file_sha256"],
        "analysis_canonical_integrity_sha256": frame["integrity_sha256"],
        "source_evidence": records,
        "capture_alignment": alignment,
    }, payloads["photo"]


def _deep_validate_w1(path: Path) -> tuple[dict[str, Any], bytes]:
    resolved = path.resolve()
    try:
        root = post.validate_post_capture_analysis(resolved)
    except post.PostCaptureAnalysisError as error:
        raise CoarseScreenError(
            f"W1 analysis deep validation failed: {error}"
        ) from error
    expected = camera.RAW_P16_CROSSOVER_WHITE_CONTAINMENT_BINDINGS[0]
    for field in (
        "campaign_id",
        "test_id",
        "contract_id",
        "firmware_sha256",
        "action_id",
        "descriptor_id",
        "role",
    ):
        _require_equal(root.get(field), expected[field], label=f"W1 {field}")
    analysis = root["analysis"]
    if (
        analysis.get("verdict") != "PASS"
        or analysis.get("candidate_detected") is not True
        or analysis.get("coverage", {}).get("capture_scope") != "full_panel"
        or analysis.get("coverage", {}).get("full_panel_visible") is not True
    ):
        raise CoarseScreenError("W1 post-capture analysis is not a full-panel PASS")

    analysis_payload, analysis_digest = _read_and_hash(resolved, label="W1 analysis")
    capture_binding = root["bindings"]["capture_sidecar"]
    capture_path = (resolved.parent / capture_binding["path"]).resolve()
    try:
        validated_capture = camera.validate_capture_evidence(capture_path)
    except Exception as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        raise CoarseScreenError(
            f"W1 capture evidence deep validation failed: {error}"
        ) from error
    photo_binding = root["bindings"]["photo"]
    photo_path = (resolved.parent / photo_binding["path"]).resolve()
    photo_payload, photo_digest = _read_and_hash(photo_path, label="W1 photo")
    _require_equal(len(photo_payload), photo_binding["bytes"], label="W1 photo bytes")
    _require_equal(photo_digest, photo_binding["sha256"], label="W1 photo SHA-256")
    try:
        rgb = photo.base._decode_rgb(photo_payload)  # noqa: SLF001
    except photo.CrossoverPhotoAnalysisError as error:
        raise CoarseScreenError(f"W1 photo decode failed: {error}") from error
    alignment = _capture_alignment(validated_capture)
    _require_equal(alignment["photo_width"], rgb.shape[1], label="W1 photo width")
    _require_equal(alignment["photo_height"], rgb.shape[0], label="W1 photo height")
    return {
        "analysis_path": resolved.as_posix(),
        "analysis_bytes": len(analysis_payload),
        "analysis_file_sha256": analysis_digest,
        "analysis_canonical_integrity_sha256": root["integrity"]["sha256"],
        "analysis_id": root["analysis_id"],
        "campaign_id": root["campaign_id"],
        "contract_id": root["contract_id"],
        "action_id": root["action_id"],
        "capture_sidecar": dict(capture_binding),
        "capture_alignment": alignment,
        "photo": {
            "path": photo_path.as_posix(),
            "bytes": len(photo_payload),
            "file_sha256": photo_digest,
            "width": int(rgb.shape[1]),
            "height": int(rgb.shape[0]),
        },
    }, photo_payload


def _coarse_bucket(lab: Sequence[float]) -> str:
    """Return an intentionally broad, camera-relative colour family."""

    lightness, a_value, b_value = (float(value) for value in lab)
    chroma = math.hypot(a_value, b_value)
    if chroma < 12.0:
        if lightness < 25.0:
            return "NEUTRAL_DARK"
        if lightness >= 85.0:
            return "NEUTRAL_LIGHT"
        return "NEUTRAL_MID"
    hue = math.degrees(math.atan2(b_value, a_value)) % 360.0
    if hue < 50.0 or hue >= 330.0:
        return "RED_ORANGE"
    if hue < 130.0:
        return "YELLOW_OLIVE"
    if hue < 250.0:
        return "GREEN_CYAN"
    return "BLUE_VIOLET"


def _metric_classification(value: float, *, pass_max: float, review_max: float) -> str:
    if value <= pass_max:
        return "PASS"
    if value <= review_max:
        return "REVIEW"
    return "FAIL"


def _mean_vector(vectors: Sequence[Sequence[float]]) -> list[float]:
    if not vectors:
        raise CoarseScreenError("cannot average an empty vector set")
    return [statistics.fmean(vector[index] for vector in vectors) for index in range(3)]


def _median_vector(vectors: Sequence[Sequence[float]]) -> list[float]:
    if not vectors:
        raise CoarseScreenError("cannot take an empty vector median")
    return [
        statistics.median(vector[index] for vector in vectors) for index in range(3)
    ]


def _rounded_vector(vector: Sequence[float]) -> list[float]:
    return [round(float(value), 9) for value in vector]


def _normalized_cell(
    t1_cell: Mapping[str, Any], white_cell: Mapping[str, Any]
) -> dict[str, Any]:
    white_lab = white_cell["camera_relative_lab_d65_from_rgb_median"]
    white_lstar = float(white_lab[0])
    result: dict[str, Any] = {
        "cell_id": t1_cell["cell_id"],
        "controller": t1_cell["controller"],
        "row": t1_cell["row"],
        "column": t1_cell["column"],
        "code": t1_cell["code"],
        "white_reference_rgb_median": white_cell["robust_rgb_median"],
        "white_reference_lab": white_lab,
        "white_reference_lstar": round(white_lstar, 9),
        "valid": white_lstar >= WHITE_REFERENCE_MIN_LSTAR,
    }
    if result["valid"] is not True:
        result.update(
            invalid_reason="WHITE_REFERENCE_LSTAR_BELOW_25",
            normalized_rgb=None,
            normalized_lab=None,
            coarse_bucket=None,
        )
        return result
    t1_rgb = [float(value) for value in t1_cell["robust_rgb_median"]]
    white_rgb = [float(value) for value in white_cell["robust_rgb_median"]]
    if any(value <= 0.0 for value in white_rgb):
        raise CoarseScreenError(f"{t1_cell['cell_id']} has zero W1 RGB denominator")
    normalized = [
        min(255.0, max(0.0, NORMALIZATION_TARGET_RGB * value / reference))
        for value, reference in zip(t1_rgb, white_rgb, strict=True)
    ]
    normalized_rgb8 = tuple(int(round(value)) for value in normalized)
    lab = list(srgb8_to_lab(normalized_rgb8))
    result.update(
        invalid_reason=None,
        t1_rgb_median=t1_rgb,
        normalized_rgb=_rounded_vector(normalized),
        normalized_rgb8=list(normalized_rgb8),
        normalized_lab=_rounded_vector(lab),
        coarse_bucket=_coarse_bucket(lab),
    )
    return result


def _group_result(
    frames: Sequence[Mapping[str, Any]], *, controller: int, code: int
) -> dict[str, Any]:
    frame_records: list[dict[str, Any]] = []
    for frame_index, frame in enumerate(frames, 1):
        cells = [
            cell
            for cell in frame["cells"]
            if cell["controller"] == controller and cell["code"] == code
        ]
        cells.sort(key=lambda item: (item["row"], item["column"]))
        if len(cells) != 4:
            raise CoarseScreenError("controller/code group does not contain four cells")
        valid = [cell for cell in cells if cell["valid"] is True]
        frame_records.append(
            {
                "frame_index": frame_index,
                "valid_position_count": len(valid),
                "frame_eligible": len(valid) >= VALID_POSITIONS_PER_FRAME,
                "cells": cells,
                "center_lab_mean": (
                    _rounded_vector(
                        _mean_vector([cell["normalized_lab"] for cell in valid])
                    )
                    if len(valid) >= VALID_POSITIONS_PER_FRAME
                    else None
                ),
            }
        )
    eligible_frames = [item for item in frame_records if item["frame_eligible"]]
    positions: list[dict[str, Any]] = []
    expected_positions = strict._expected_positions(code)  # noqa: SLF001
    for row, column in expected_positions:
        samples = [
            next(
                cell
                for cell in frame["cells"]
                if cell["controller"] == controller
                and cell["row"] == row
                and cell["column"] == column
            )
            for frame in eligible_frames
        ]
        valid_samples = [sample for sample in samples if sample["valid"] is True]
        bucket_counts = Counter(sample["coarse_bucket"] for sample in valid_samples)
        dominant = (
            sorted(bucket_counts.items(), key=lambda item: (-item[1], item[0]))[0]
            if bucket_counts
            else (None, 0)
        )
        position = {
            "row": row,
            "column": column,
            "valid_frame_count": len(valid_samples),
            "position_eligible": (
                len(valid_samples) >= VALID_FRAMES_PER_GROUP
                and dominant[1] >= VALID_FRAMES_PER_GROUP
            ),
            "frame_buckets": [sample["coarse_bucket"] for sample in valid_samples],
        }
        if position["position_eligible"]:
            position.update(
                dominant_bucket=dominant[0],
                dominant_bucket_frame_count=dominant[1],
                normalized_lab_median=_rounded_vector(
                    _median_vector(
                        [sample["normalized_lab"] for sample in valid_samples]
                    )
                ),
            )
        else:
            position.update(
                dominant_bucket=None,
                dominant_bucket_frame_count=dominant[1],
                normalized_lab_median=None,
            )
        positions.append(position)

    eligible_positions = [item for item in positions if item["position_eligible"]]
    sufficient = (
        len(eligible_frames) >= VALID_FRAMES_PER_GROUP
        and len(eligible_positions) >= DOMINANT_BUCKET_POSITIONS
    )
    if not sufficient:
        return {
            "controller": controller,
            "controller_label": f"CS{controller + 1}",
            "code": code,
            "classification": "FAIL",
            "diagnostic_reason": "INSUFFICIENT_VALID_WHITE_REFERENCE_COVERAGE",
            "eligible_frame_count": len(eligible_frames),
            "eligible_position_count": len(eligible_positions),
            "frame_results": frame_records,
            "position_results": positions,
            "dominant_bucket": None,
            "dominant_bucket_position_count": 0,
            "position_maximum_de00": None,
            "temporal_center_maximum_de76": None,
        }

    position_bucket_counts = Counter(
        item["dominant_bucket"] for item in eligible_positions
    )
    dominant_bucket, dominant_count = sorted(
        position_bucket_counts.items(), key=lambda item: (-item[1], item[0])
    )[0]
    position_labs = [item["normalized_lab_median"] for item in eligible_positions]
    group_center = _median_vector(position_labs)
    position_de00 = [
        float(delta_e_ciede2000(item["normalized_lab_median"], group_center))
        for item in eligible_positions
    ]
    frame_centers = [item["center_lab_mean"] for item in eligible_frames]
    temporal_center = _mean_vector(frame_centers)
    temporal_de76 = [math.dist(item, temporal_center) for item in frame_centers]
    position_maximum = max(position_de00)
    temporal_maximum = max(temporal_de76)
    bucket_class = "PASS" if dominant_count >= DOMINANT_BUCKET_POSITIONS else "FAIL"
    position_class = _metric_classification(
        position_maximum,
        pass_max=POSITION_PASS_MAX_DE00,
        review_max=POSITION_REVIEW_MAX_DE00,
    )
    temporal_class = _metric_classification(
        temporal_maximum,
        pass_max=TEMPORAL_PASS_MAX_DE76,
        review_max=TEMPORAL_REVIEW_MAX_DE76,
    )
    ranks = {"PASS": 0, "REVIEW": 1, "FAIL": 2}
    classification = max((bucket_class, position_class, temporal_class), key=ranks.get)
    return {
        "controller": controller,
        "controller_label": f"CS{controller + 1}",
        "code": code,
        "classification": classification,
        "diagnostic_reason": (
            "COARSE_SCREEN_ALL_COMPONENTS_PASS"
            if classification == "PASS"
            else "COARSE_SCREEN_COMPONENT_REQUIRES_REVIEW"
            if classification == "REVIEW"
            else "COARSE_SCREEN_COMPONENT_FAILED"
        ),
        "eligible_frame_count": len(eligible_frames),
        "eligible_position_count": len(eligible_positions),
        "frame_results": frame_records,
        "position_results": positions,
        "dominant_bucket": dominant_bucket,
        "dominant_bucket_position_count": dominant_count,
        "dominant_bucket_fraction_of_nominal_four": round(dominant_count / 4.0, 9),
        "bucket_classification": bucket_class,
        "normalized_group_center_lab_median": _rounded_vector(group_center),
        "position_delta_e00_to_group_center": [
            round(value, 9) for value in position_de00
        ],
        "position_maximum_de00": round(position_maximum, 9),
        "position_classification": position_class,
        "temporal_frame_center_labs_mean": frame_centers,
        "temporal_center_lab_mean": _rounded_vector(temporal_center),
        "temporal_center_delta_e76": [round(value, 9) for value in temporal_de76],
        "temporal_center_maximum_de76": round(temporal_maximum, 9),
        "temporal_classification": temporal_class,
    }


def _maximum_optional(records: Sequence[Mapping[str, Any]], field: str) -> float | None:
    values = [
        float(record[field])
        for record in records
        if isinstance(record.get(field), (int, float))
        and not isinstance(record.get(field), bool)
    ]
    return round(max(values), 9) if values else None


def screen(t1_analyses: Sequence[Path], w1_analysis: Path) -> dict[str, Any]:
    """Build a sealed, non-formal coarse-screen report without hardware I/O."""

    try:
        strict_frames = strict._load_stage(t1_analyses, stage=strict.T1_STAGE)  # noqa: SLF001
    except strict.CrossoverProfileComparisonError as error:
        raise CoarseScreenError(str(error)) from error
    t1_bindings: list[dict[str, Any]] = []
    for index, (path, frame) in enumerate(
        zip(t1_analyses, strict_frames, strict=True), 1
    ):
        binding, _photo_payload = _deep_validate_t1_source(
            Path(path), frame, index=index
        )
        t1_bindings.append(binding)
    w1_binding, w1_photo_payload = _deep_validate_w1(Path(w1_analysis))
    _validate_capture_alignment(
        [
            *(binding["capture_alignment"] for binding in t1_bindings),
            w1_binding["capture_alignment"],
        ]
    )
    try:
        w1_rgb = photo.base._decode_rgb(w1_photo_payload)  # noqa: SLF001
    except photo.CrossoverPhotoAnalysisError as error:
        raise CoarseScreenError(f"cannot decode W1 photo: {error}") from error

    normalized_frames: list[dict[str, Any]] = []
    for index, (path, frame) in enumerate(
        zip(t1_analyses, strict_frames, strict=True), 1
    ):
        try:
            _payload, root = strict._load_json(  # noqa: SLF001
                Path(path).resolve(), label=f"T1 analysis {index}"
            )
        except strict.CrossoverProfileComparisonError as error:
            raise CoarseScreenError(str(error)) from error
        _cv2, np = photo.base._import_cv()  # noqa: SLF001
        homography = np.asarray(
            root["geometry"]["homography_logical_to_current_photo"], dtype=np.float64
        )
        white_cells = {
            (cell["controller"], cell["row"], cell["column"]): photo.base._sample_cell(  # noqa: SLF001
                w1_rgb, homography, cell
            )
            for cell in photo._all_logical_cells()  # noqa: SLF001
        }
        normalized_cells = [
            _normalized_cell(
                cell,
                white_cells[(cell["controller"], cell["row"], cell["column"])],
            )
            for cell in root["cells"]
        ]
        normalized_frames.append(
            {
                "frame_index": index,
                "analysis_file_sha256": frame["file_sha256"],
                "homography_logical_to_w1_photo": root["geometry"][
                    "homography_logical_to_current_photo"
                ],
                "cells": normalized_cells,
            }
        )

    groups = [
        _group_result(normalized_frames, controller=controller, code=code)
        for controller in range(2)
        for code in range(8)
    ]
    counts = Counter(item["classification"] for item in groups)
    eligible = counts["PASS"] == 16
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "method_id": METHOD_ID,
        "screening_only": True,
        "formal_gate_evaluated": False,
        "qualified_colour_count": 0,
        "formal_advance_to_t2_permitted": False,
        "eligible_for_t2_discovery": eligible,
        "consumed_t1_state_changed": False,
        "input_bindings": {"t1_analyses": t1_bindings, "w1_analysis": w1_binding},
        "normalization_contract": {
            "formula": "clip(220*T1_RGB/W1_RGB,0,255)",
            "target_rgb": NORMALIZATION_TARGET_RGB,
            "white_reference_min_lstar": WHITE_REFERENCE_MIN_LSTAR,
            "white_sampling_geometry": "EACH_T1_HOMOGRAPHY_APPLIED_TO_W1_PHOTO",
            "normalized_rgb_quantization_before_lab": "ROUND_TO_UINT8",
            "lab_space": "sRGB_D65_2DEG_CIE_LAB",
            "absolute_colour_calibrated": False,
        },
        "threshold_contract": {
            "valid_positions_per_group_per_frame_minimum": VALID_POSITIONS_PER_FRAME,
            "valid_frames_per_group_minimum": VALID_FRAMES_PER_GROUP,
            "dominant_bucket_positions_of_nominal_four_minimum": DOMINANT_BUCKET_POSITIONS,
            "position_pass_maximum_de00": POSITION_PASS_MAX_DE00,
            "position_review_maximum_de00": POSITION_REVIEW_MAX_DE00,
            "temporal_pass_maximum_de76": TEMPORAL_PASS_MAX_DE76,
            "temporal_review_maximum_de76": TEMPORAL_REVIEW_MAX_DE76,
            "automatic_threshold_relaxation": False,
        },
        "group_results": groups,
        "summary": {
            "state": "PASS_COARSE_SCREEN" if eligible else "COARSE_SCREEN_NOT_ALL_PASS",
            "group_count": len(groups),
            "classification_counts": {
                state: counts[state] for state in ("PASS", "REVIEW", "FAIL")
            },
            "maximum_position_de00": _maximum_optional(groups, "position_maximum_de00"),
            "maximum_temporal_center_de76": _maximum_optional(
                groups, "temporal_center_maximum_de76"
            ),
            "screening_only": True,
            "formal_gate_evaluated": False,
            "qualified_colour_count": 0,
            "formal_advance_to_t2_permitted": False,
            "eligible_for_t2_discovery": eligible,
            "does_not_reverse_consumed_t1": True,
        },
        "evidence_boundaries": {
            "camera_relative_flat_field_screen_only": True,
            "w1_is_not_a_calibrated_white_standard": True,
            "formal_t1_gate_unchanged": True,
            "device_io_performed": False,
            "network_accessed": False,
            "camera_accessed": False,
            "serial_or_com_accessed": False,
            "relay_accessed": False,
            "firmware_flashed": False,
            "display_refreshed": False,
        },
        "output_write_contract": "O_EXCL",
    }
    report["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": strict.sha256_bytes(strict.canonical_json(report)),
    }
    return report


def _serialized(report: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def write_exclusive(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as error:
        raise CoarseScreenError(f"refusing to overwrite output: {path}") from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "--t1-analysis", type=Path, nargs=3, required=True, metavar="JSON"
    )
    parser.add_argument("--w1-analysis", type=Path, required=True, metavar="JSON")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = screen(args.t1_analysis, args.w1_analysis)
        payload = _serialized(report)
        write_exclusive(args.output, payload)
    except CoarseScreenError as error:
        print(f"RAW-P16 T1 coarse-screen error: {error}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(payload)
    return 0 if report["eligible_for_t2_discovery"] is True else 3


if __name__ == "__main__":
    raise SystemExit(main())
