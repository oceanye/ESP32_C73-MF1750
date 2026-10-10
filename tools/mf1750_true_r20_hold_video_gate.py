#!/usr/bin/env python3
"""Detect protected-ROI transient changes in true-R20 HOLD videos."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any

import cv2
import numpy as np

from tools import mf1750_same_r20_atlas_photo_analyzer as common
from tools import mf1750_true_r20_hold_photo_gate as static_gate


SCHEMA_VERSION = 1
KIND = "mf1750-true-r20-three-roi-transient-hold-video-gate"
INTEGRITY_ALGORITHM = common.INTEGRITY_ALGORITHM


class TrueR20HoldVideoGateError(RuntimeError):
    """Raised when video/reference evidence or output is invalid."""


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
        raise TrueR20HoldVideoGateError(
            f"record contains a non-canonical JSON value: {exc}"
        ) from exc


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _projected_mask(
    homography: np.ndarray,
    dimensions: tuple[int, int],
    bounds: tuple[int, int, int, int],
) -> np.ndarray:
    x, y, width, height = bounds
    corners = np.float32(
        [[[x, y], [x + width, y], [x + width, y + height], [x, y + height]]]
    )
    projected = cv2.perspectiveTransform(corners, homography)[0]
    center = np.mean(projected, axis=0)
    inner = center + 0.58 * (projected - center)
    mask = np.zeros((dimensions[1], dimensions[0]), dtype=np.uint8)
    cv2.fillConvexPoly(mask, np.rint(inner).astype(np.int32), 255)
    if np.count_nonzero(mask) < 64:
        raise TrueR20HoldVideoGateError("one projected ROI has too few pixels")
    return mask > 0


def _sample_lab(frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
    pixels = frame[mask]
    if len(pixels) < 64:
        raise TrueR20HoldVideoGateError("one video ROI has too few pixels")
    rgb = np.median(pixels[:, ::-1].astype(np.float64), axis=0)
    return common._lab_from_rgb(rgb)


def evaluate_samples(
    samples: Mapping[str, np.ndarray],
    *,
    protected_keys: Sequence[str],
    background_keys: Sequence[str],
    pre_roll_frames: int,
    threshold_de76: float | None,
) -> dict[str, Any]:
    """Evaluate sampled Lab time series; exposed for deterministic tests."""

    if pre_roll_frames < 2:
        raise TrueR20HoldVideoGateError("pre-roll must contain at least two frames")
    if not samples:
        raise TrueR20HoldVideoGateError("sample series are empty")
    lengths = {value.shape[0] for value in samples.values()}
    if len(lengths) != 1:
        raise TrueR20HoldVideoGateError("sample series lengths differ")
    frame_count = next(iter(lengths))
    if frame_count <= pre_roll_frames:
        raise TrueR20HoldVideoGateError("video contains no post-roll frames")

    results: list[dict[str, Any]] = []
    for key in [*protected_keys, *background_keys]:
        series = samples.get(key)
        if series is None or series.shape != (frame_count, 3):
            raise TrueR20HoldVideoGateError(f"sample series {key} differs")
        if not np.all(np.isfinite(series)):
            raise TrueR20HoldVideoGateError(f"sample series {key} is non-finite")
        baseline = np.median(series[:pre_roll_frames], axis=0)
        deltas = np.linalg.norm(series - baseline, axis=1)
        post = deltas[pre_roll_frames:]
        maximum = float(np.max(post))
        p95 = float(np.percentile(post, 95))
        results.append(
            {
                "key": key,
                "role": "protected" if key in protected_keys else "background",
                "baseline_lab": baseline.astype(float).tolist(),
                "post_roll_de76_max": maximum,
                "post_roll_de76_p95": p95,
                "within_threshold": (
                    None if threshold_de76 is None else maximum <= threshold_de76
                ),
            }
        )
    protected_pass = (
        None
        if threshold_de76 is None
        else all(
            item["within_threshold"] for item in results if item["role"] == "protected"
        )
    )
    background_pass = (
        None
        if threshold_de76 is None
        else all(
            item["within_threshold"] for item in results if item["role"] == "background"
        )
    )
    return {
        "series": results,
        "protected_pass": protected_pass,
        "background_stability_pass": background_pass,
        "transient_gate_pass": (
            None
            if protected_pass is None or background_pass is None
            else protected_pass and background_pass
        ),
    }


def analyze(
    video_path: Path,
    reference_grid_path: Path,
    *,
    stage: str,
    repeat_noise_p95_de76: float | None = None,
    pre_roll_frames: int = 10,
    minimum_duration_seconds: float = 25.0,
) -> dict[str, Any]:
    """Analyze one already-recorded video without device or camera I/O."""

    normalized_stage = stage.upper()
    if normalized_stage not in {"A", "B", "C", "WHITE"}:
        raise TrueR20HoldVideoGateError("stage must be A, B, C, or WHITE")
    if pre_roll_frames < 2:
        raise TrueR20HoldVideoGateError("pre-roll must contain at least two frames")
    if not math.isfinite(minimum_duration_seconds) or minimum_duration_seconds <= 0:
        raise TrueR20HoldVideoGateError("minimum duration must be positive")
    if repeat_noise_p95_de76 is not None and (
        not math.isfinite(repeat_noise_p95_de76) or repeat_noise_p95_de76 < 0
    ):
        raise TrueR20HoldVideoGateError("repeat noise must be finite and nonnegative")

    try:
        video_payload = common._read_stable_regular(video_path, label="refresh video")
        reference_payload, _, homography, dimensions = static_gate._load_reference(
            reference_grid_path
        )
    except (
        common.SameR20AtlasAnalysisError,
        static_gate.TrueR20HoldPhotoGateError,
    ) as exc:
        raise TrueR20HoldVideoGateError(str(exc)) from exc

    protected_names = {
        "A": (),
        "B": ("A",),
        "C": ("A", "B"),
        "WHITE": (),
    }[normalized_stage]
    masks: dict[str, np.ndarray] = {}
    for controller in range(2):
        for name in protected_names:
            key = f"C{controller}-{name}"
            masks[key] = _projected_mask(
                homography,
                dimensions,
                static_gate._global_bounds(controller, static_gate.ROI_LOCAL[name]),
            )
        for name, local in static_gate.BACKGROUND_LOCAL.items():
            key = f"C{controller}-{name}"
            masks[key] = _projected_mask(
                homography,
                dimensions,
                static_gate._global_bounds(controller, local),
            )

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise TrueR20HoldVideoGateError("cannot open refresh video")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    declared_frames = int(round(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
    if not math.isfinite(fps) or fps <= 0:
        capture.release()
        raise TrueR20HoldVideoGateError("video FPS is invalid")
    sampled: dict[str, list[np.ndarray]] = {key: [] for key in masks}
    observed_frames = 0
    observed_dimensions: tuple[int, int] | None = None
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame is None or frame.ndim != 3 or frame.shape[2] != 3:
                raise TrueR20HoldVideoGateError("video contains an invalid frame")
            current_dimensions = (frame.shape[1], frame.shape[0])
            if current_dimensions != dimensions:
                raise TrueR20HoldVideoGateError("video/reference dimensions differ")
            observed_dimensions = current_dimensions
            for key, mask in masks.items():
                sampled[key].append(_sample_lab(frame, mask))
            observed_frames += 1
    finally:
        capture.release()
    if observed_dimensions is None or observed_frames <= pre_roll_frames:
        raise TrueR20HoldVideoGateError("video contains too few decoded frames")
    duration = observed_frames / fps
    arrays = {
        key: np.asarray(value, dtype=np.float64) for key, value in sampled.items()
    }
    threshold = (
        None if repeat_noise_p95_de76 is None else max(4.0, 3.0 * repeat_noise_p95_de76)
    )
    protected_keys = [
        f"C{controller}-{name}" for controller in range(2) for name in protected_names
    ]
    background_keys = [
        f"C{controller}-{name}"
        for controller in range(2)
        for name in static_gate.BACKGROUND_LOCAL
    ]
    evaluation = evaluate_samples(
        arrays,
        protected_keys=protected_keys,
        background_keys=background_keys,
        pre_roll_frames=pre_roll_frames,
        threshold_de76=threshold,
    )
    duration_pass = duration >= minimum_duration_seconds
    raw_gate = evaluation["transient_gate_pass"]
    final_gate = None if raw_gate is None else raw_gate and duration_pass
    state = (
        "NO_PROTECTED_ROI_AT_THIS_STAGE"
        if not protected_names and normalized_stage in {"A", "WHITE"}
        else (
            "NO_TRANSIENT_PROTECTED_ROI_CHANGE_CANDIDATE"
            if final_gate is True
            else (
                "TRANSIENT_OR_BACKGROUND_CHANGE_DETECTED"
                if final_gate is False and duration_pass
                else "INCONCLUSIVE_NOISE_OR_DURATION_GATE"
            )
        )
    )
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "analysis_id": _sha256_bytes(
            _canonical_json(
                {
                    "video_sha256": _sha256_bytes(video_payload),
                    "reference_sha256": _sha256_bytes(reference_payload),
                    "stage": normalized_stage,
                    "method": "true-r20-protected-roi-video-v1",
                }
            )
        ),
        "stage": normalized_stage,
        "source_video": {
            "path": str(video_path),
            "bytes": len(video_payload),
            "sha256": _sha256_bytes(video_payload),
            "fps": fps,
            "declared_frame_count": declared_frames,
            "decoded_frame_count": observed_frames,
            "duration_seconds": duration,
            "width": dimensions[0],
            "height": dimensions[1],
        },
        "reference_grid": {
            "path": str(reference_grid_path),
            "bytes": len(reference_payload),
            "sha256": _sha256_bytes(reference_payload),
        },
        "thresholds": {
            "repeat_noise_p95_de76": repeat_noise_p95_de76,
            "transient_maximum_de76": threshold,
            "pre_roll_frames": pre_roll_frames,
            "minimum_duration_seconds": minimum_duration_seconds,
        },
        "protected_rois": list(protected_names),
        "evaluation": evaluation,
        "duration_gate_pass": duration_pass,
        "classification": {
            "state": state,
            "transient_gate_pass": final_gate,
            "qualified_cross_r20_hold": False,
            "requires_bound_static_photo_gate": True,
        },
        "evidence_boundaries": {
            "camera_relative_de76_not_calibrated_de00": True,
            "locked_camera_exposure_white_balance_focus_required": True,
            "compiled_payload_does_not_prove_bus_reception": True,
            "device_or_camera_io_performed_by_analysis": False,
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
        raise TrueR20HoldVideoGateError(
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
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--reference-grid-analysis", type=Path, required=True)
    parser.add_argument("--stage", choices=("A", "B", "C", "WHITE"), required=True)
    parser.add_argument("--repeat-noise-p95-de76", type=float)
    parser.add_argument("--pre-roll-frames", type=int, default=10)
    parser.add_argument("--minimum-duration-seconds", type=float, default=25.0)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = analyze(
            args.video,
            args.reference_grid_analysis,
            stage=args.stage,
            repeat_noise_p95_de76=args.repeat_noise_p95_de76,
            pre_roll_frames=args.pre_roll_frames,
            minimum_duration_seconds=args.minimum_duration_seconds,
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
    except TrueR20HoldVideoGateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
