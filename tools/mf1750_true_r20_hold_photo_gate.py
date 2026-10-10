#!/usr/bin/env python3
"""Evaluate static frames from the true-R20 three-ROI HOLD campaign.

The gate compares before/after photographs to a bound factory-white reference
using a fixed camera homography.  All distances are camera-relative DE76.
Video evidence remains separately required to establish absence of transient
flashing during refresh.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

import cv2
import numpy as np

from tools import mf1750_same_r20_atlas_photo_analyzer as common


SCHEMA_VERSION = 1
KIND = "mf1750-true-r20-three-roi-static-hold-camera-relative-gate"
LAYOUT_ID = "L535_TRUE_R20_SWITCH_THREE_ROI_HOLD_V1"
INTEGRITY_ALGORITHM = common.INTEGRITY_ALGORITHM
ROI_LOCAL = {
    "A": (48, 64, 160, 120),
    "B": (304, 240, 160, 120),
    "C": (48, 416, 160, 120),
}
BACKGROUND_LOCAL = {
    "BG_TOP": (240, 72, 32, 88),
    "BG_BOTTOM": (240, 432, 32, 88),
}


class TrueR20HoldPhotoGateError(RuntimeError):
    """Raised when bound evidence or exclusive output is invalid."""


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
        raise TrueR20HoldPhotoGateError(
            f"record contains a non-canonical JSON value: {exc}"
        ) from exc


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load_reference(
    path: Path,
) -> tuple[bytes, dict[str, Any], np.ndarray, tuple[int, int]]:
    try:
        payload, root = common._load_json(path, label="reference grid")
        if root.get("schema_version") != 1 or root.get("kind") != common.REFERENCE_KIND:
            raise TrueR20HoldPhotoGateError("reference schema identity differs")
        layout = common._mapping(root.get("campaign_layout"), label="reference layout")
        if layout.get("id") != common.REFERENCE_LAYOUT:
            raise TrueR20HoldPhotoGateError("reference layout identity differs")
        judgement = common._mapping(
            root.get("grid_judgement"), label="reference judgement"
        )
        if judgement.get("enough_to_interpret_grid_camera_relatively") is not True:
            raise TrueR20HoldPhotoGateError("reference geometry is insufficient")
        common._verify_integrity(root)
        geometry = common._mapping(
            root.get("geometry_quality"), label="reference geometry"
        )
        homography = np.asarray(
            geometry.get("homography_logical_to_photo"), dtype=np.float64
        )
        source = common._mapping(root.get("source_photo"), label="reference photo")
        dimensions = (int(source.get("width")), int(source.get("height")))
    except (common.SameR20AtlasAnalysisError, TypeError, ValueError) as exc:
        if isinstance(exc, TrueR20HoldPhotoGateError):
            raise
        raise TrueR20HoldPhotoGateError(str(exc)) from exc
    if homography.shape != (3, 3) or not np.all(np.isfinite(homography)):
        raise TrueR20HoldPhotoGateError("reference homography differs")
    if dimensions[0] < 1 or dimensions[1] < 1:
        raise TrueR20HoldPhotoGateError("reference dimensions differ")
    return payload, root, homography, dimensions


def _decode(
    path: Path, dimensions: tuple[int, int], *, label: str
) -> tuple[bytes, np.ndarray]:
    try:
        payload, image = common._decode_image(path)
    except common.SameR20AtlasAnalysisError as exc:
        raise TrueR20HoldPhotoGateError(f"{label}: {exc}") from exc
    if (image.shape[1], image.shape[0]) != dimensions:
        raise TrueR20HoldPhotoGateError(f"{label} dimensions differ")
    return payload, image


def _rectify(image: np.ndarray, homography: np.ndarray) -> np.ndarray:
    try:
        inverse = np.linalg.inv(homography)
    except np.linalg.LinAlgError as exc:
        raise TrueR20HoldPhotoGateError("reference homography is singular") from exc
    return cv2.warpPerspective(
        image,
        inverse,
        (common.LOGICAL_WIDTH, common.LOGICAL_HEIGHT),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )


def _median_lab(image: np.ndarray, bounds: tuple[int, int, int, int]) -> np.ndarray:
    x, y, width, height = bounds
    inset_x = max(2, round(width * 0.20))
    inset_y = max(2, round(height * 0.20))
    patch = image[y + inset_y : y + height - inset_y, x + inset_x : x + width - inset_x]
    if patch.size == 0:
        raise TrueR20HoldPhotoGateError("sampling patch is empty")
    rgb = np.median(patch.reshape(-1, 3)[:, ::-1].astype(np.float64), axis=0)
    return common._lab_from_rgb(rgb)


def _edge_labs(
    image: np.ndarray, bounds: tuple[int, int, int, int]
) -> dict[str, np.ndarray]:
    x, y, width, height = bounds
    strip = 6
    inset = 12
    patches = {
        "top": image[y : y + strip, x + inset : x + width - inset],
        "bottom": image[y + height - strip : y + height, x + inset : x + width - inset],
        "left": image[y + inset : y + height - inset, x : x + strip],
        "right": image[y + inset : y + height - inset, x + width - strip : x + width],
    }
    result: dict[str, np.ndarray] = {}
    for name, patch in patches.items():
        if patch.size == 0:
            raise TrueR20HoldPhotoGateError("edge sampling patch is empty")
        rgb = np.median(patch.reshape(-1, 3)[:, ::-1].astype(np.float64), axis=0)
        result[name] = common._lab_from_rgb(rgb)
    return result


def _global_bounds(
    controller: int, local: tuple[int, int, int, int]
) -> tuple[int, int, int, int]:
    x, y, width, height = local
    return controller * common.CONTROLLER_WIDTH + x, y, width, height


def _distance(first: np.ndarray, second: np.ndarray) -> float:
    return float(np.linalg.norm(first - second))


def analyze(
    before_photo: Path,
    after_photo: Path,
    white_reference_photo: Path,
    reference_grid_path: Path,
    *,
    stage: str,
    repeat_noise_p95_de76: float | None = None,
) -> dict[str, Any]:
    """Evaluate one A/B/C/WHITE stage without device I/O."""

    normalized_stage = stage.upper()
    if normalized_stage not in {"A", "B", "C", "WHITE"}:
        raise TrueR20HoldPhotoGateError("stage must be A, B, C, or WHITE")
    if repeat_noise_p95_de76 is not None and (
        not math.isfinite(repeat_noise_p95_de76) or repeat_noise_p95_de76 < 0
    ):
        raise TrueR20HoldPhotoGateError("repeat noise must be finite and nonnegative")

    reference_payload, _, homography, dimensions = _load_reference(reference_grid_path)
    before_payload, before_image = _decode(
        before_photo, dimensions, label="before photo"
    )
    after_payload, after_image = _decode(after_photo, dimensions, label="after photo")
    white_payload, white_image = _decode(
        white_reference_photo, dimensions, label="white reference photo"
    )
    resolved_paths = {
        Path(before_photo).resolve(),
        Path(after_photo).resolve(),
        Path(white_reference_photo).resolve(),
    }
    if len(resolved_paths) != 3:
        raise TrueR20HoldPhotoGateError("before/after/white paths must be distinct")

    rectified = {
        "before": _rectify(before_image, homography),
        "after": _rectify(after_image, homography),
        "white": _rectify(white_image, homography),
    }
    labs: dict[str, dict[int, dict[str, np.ndarray]]] = {
        moment: {controller: {} for controller in range(2)} for moment in rectified
    }
    for moment, image in rectified.items():
        for controller in range(2):
            for name, local in {**ROI_LOCAL, **BACKGROUND_LOCAL}.items():
                labs[moment][controller][name] = _median_lab(
                    image, _global_bounds(controller, local)
                )

    protected = {
        "A": (),
        "B": ("A",),
        "C": ("A", "B"),
        "WHITE": (),
    }[normalized_stage]
    newly_written = {
        "A": ("A",),
        "B": ("B",),
        "C": ("C",),
        "WHITE": (),
    }[normalized_stage]
    expected_white = {
        "A": ("B", "C"),
        "B": ("C",),
        "C": (),
        "WHITE": ("A", "B", "C"),
    }[normalized_stage]
    hold_threshold = (
        None if repeat_noise_p95_de76 is None else max(4.0, 3.0 * repeat_noise_p95_de76)
    )
    change_threshold = (
        None if hold_threshold is None else max(8.0, 2.0 * hold_threshold)
    )
    edge_threshold = None if hold_threshold is None else max(8.0, hold_threshold + 4.0)

    protected_results: list[dict[str, Any]] = []
    new_results: list[dict[str, Any]] = []
    white_results: list[dict[str, Any]] = []
    edge_results: list[dict[str, Any]] = []
    for controller in range(2):
        for name in protected:
            delta = _distance(
                labs["before"][controller][name], labs["after"][controller][name]
            )
            protected_results.append(
                {
                    "controller": controller,
                    "roi": name,
                    "before_after_de76": delta,
                    "within_hold_threshold": (
                        None if hold_threshold is None else delta <= hold_threshold
                    ),
                }
            )
        for name in newly_written:
            delta = _distance(
                labs["after"][controller][name], labs["white"][controller][name]
            )
            new_results.append(
                {
                    "controller": controller,
                    "roi": name,
                    "after_vs_white_de76": delta,
                    "new_colour_change_detected": (
                        None if change_threshold is None else delta >= change_threshold
                    ),
                }
            )
        for name in expected_white:
            delta = _distance(
                labs["after"][controller][name], labs["white"][controller][name]
            )
            white_results.append(
                {
                    "controller": controller,
                    "roi": name,
                    "after_vs_white_de76": delta,
                    "within_white_threshold": (
                        None if hold_threshold is None else delta <= hold_threshold
                    ),
                }
            )
        coloured_after = {
            "A": ("A",),
            "B": ("A", "B"),
            "C": ("A", "B", "C"),
            "WHITE": (),
        }[normalized_stage]
        for name in coloured_after:
            bounds = _global_bounds(controller, ROI_LOCAL[name])
            center = labs["after"][controller][name]
            edges = _edge_labs(rectified["after"], bounds)
            distances = {
                edge: _distance(value, center) for edge, value in edges.items()
            }
            other_max = max(distances["top"], distances["left"], distances["right"])
            bottom_excess = distances["bottom"] - other_max
            edge_results.append(
                {
                    "controller": controller,
                    "roi": name,
                    "edge_to_center_de76": distances,
                    "bottom_excess_over_other_edges_de76": bottom_excess,
                    "bottom_edge_anomaly": (
                        None
                        if edge_threshold is None
                        else distances["bottom"] > edge_threshold
                        and bottom_excess > 4.0
                    ),
                }
            )

    pair_results: list[dict[str, Any]] = []
    for name in newly_written:
        delta = _distance(labs["after"][0][name], labs["after"][1][name])
        pair_results.append(
            {
                "roi": name,
                "cs1_cs2_de76": delta,
                "within_pair_threshold": (
                    None if hold_threshold is None else delta <= hold_threshold
                ),
            }
        )
    background_results: list[dict[str, Any]] = []
    for controller in range(2):
        for name in BACKGROUND_LOCAL:
            delta = _distance(
                labs["after"][controller][name], labs["white"][controller][name]
            )
            background_results.append(
                {
                    "controller": controller,
                    "roi": name,
                    "after_vs_white_de76": delta,
                    "within_background_threshold": (
                        None if hold_threshold is None else delta <= hold_threshold
                    ),
                }
            )

    static_gate = None
    if hold_threshold is not None:
        static_gate = (
            all(item["within_hold_threshold"] for item in protected_results)
            and all(item["new_colour_change_detected"] for item in new_results)
            and all(item["within_white_threshold"] for item in white_results)
            and all(item["within_pair_threshold"] for item in pair_results)
            and all(item["within_background_threshold"] for item in background_results)
            and all(item["bottom_edge_anomaly"] is False for item in edge_results)
        )

    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "analysis_id": _sha256_bytes(
            _canonical_json(
                {
                    "stage": normalized_stage,
                    "before": _sha256_bytes(before_payload),
                    "after": _sha256_bytes(after_payload),
                    "white": _sha256_bytes(white_payload),
                    "reference": _sha256_bytes(reference_payload),
                    "method": "true-r20-static-hold-gate-v1",
                }
            )
        ),
        "stage": normalized_stage,
        "layout": {
            "id": LAYOUT_ID,
            "controller_local_rois": {
                key: list(value) for key, value in ROI_LOCAL.items()
            },
            "same_coordinates_both_controllers": True,
            "cs2_mirrored": False,
        },
        "inputs": {
            "before": {
                "path": str(before_photo),
                "bytes": len(before_payload),
                "sha256": _sha256_bytes(before_payload),
            },
            "after": {
                "path": str(after_photo),
                "bytes": len(after_payload),
                "sha256": _sha256_bytes(after_payload),
            },
            "factory_white_reference": {
                "path": str(white_reference_photo),
                "bytes": len(white_payload),
                "sha256": _sha256_bytes(white_payload),
            },
            "reference_grid": {
                "path": str(reference_grid_path),
                "bytes": len(reference_payload),
                "sha256": _sha256_bytes(reference_payload),
            },
        },
        "thresholds": {
            "repeat_noise_p95_de76": repeat_noise_p95_de76,
            "hold_pair_white_background_de76": hold_threshold,
            "new_colour_minimum_change_de76": change_threshold,
            "bottom_edge_de76": edge_threshold,
        },
        "protected_hold_results": protected_results,
        "new_roi_results": new_results,
        "expected_white_results": white_results,
        "new_roi_left_right_results": pair_results,
        "background_results": background_results,
        "edge_results": edge_results,
        "classification": {
            "state": (
                "STATIC_HOLD_GATE_PASS_VIDEO_STILL_REQUIRED"
                if static_gate is True
                else (
                    "STATIC_HOLD_GATE_FAIL"
                    if static_gate is False
                    else "INCONCLUSIVE_NEEDS_REPEAT_NOISE_BASELINE"
                )
            ),
            "static_gate_pass": static_gate,
            "transient_no_flash_proven": False,
            "qualified_cross_r20_hold": False,
            "qualified_new_colour": False,
        },
        "evidence_boundaries": {
            "camera_relative_de76_not_calibrated_de00": True,
            "static_frames_cannot_exclude_transient_flash": True,
            "video_gate_is_required": True,
            "device_io_performed": False,
        },
        "output_write_contract": "O_EXCL",
    }
    unsigned["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": _sha256_bytes(_canonical_json(unsigned)),
    }
    return unsigned


def _write_exclusive(path: Path, payload: bytes) -> None:
    try:
        common._write_exclusive(path, payload)
    except common.SameR20AtlasAnalysisError as exc:
        raise TrueR20HoldPhotoGateError(str(exc)) from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--before-photo", type=Path, required=True)
    parser.add_argument("--after-photo", type=Path, required=True)
    parser.add_argument("--white-reference-photo", type=Path, required=True)
    parser.add_argument("--reference-grid-analysis", type=Path, required=True)
    parser.add_argument("--stage", choices=("A", "B", "C", "WHITE"), required=True)
    parser.add_argument("--repeat-noise-p95-de76", type=float)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = analyze(
            args.before_photo,
            args.after_photo,
            args.white_reference_photo,
            args.reference_grid_analysis,
            stage=args.stage,
            repeat_noise_p95_de76=args.repeat_noise_p95_de76,
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
    except TrueR20HoldPhotoGateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
