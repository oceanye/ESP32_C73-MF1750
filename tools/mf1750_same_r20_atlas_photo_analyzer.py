#!/usr/bin/env python3
"""Sample the same-R20 2x4 atlas through a bound camera homography.

The analyzer reuses a verified dual-8x8 grid homography captured without
moving the camera.  It reports camera-relative left/right differences only;
without chart calibration and a repeated noise baseline it cannot establish
absolute colour or controller equivalence.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
from typing import Any

import cv2
import numpy as np


SCHEMA_VERSION = 1
KIND = "mf1750-same-r20-dual-controller-2x4-camera-relative-atlas-analysis"
REFERENCE_KIND = "mf1750-redpink-v2-dual-8x8-camera-relative-grid-photo-analysis"
REFERENCE_LAYOUT = "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_V2"
LAYOUT_ID = "L535_SAME_R20_DUAL_CONTROLLER_PARITY_2X4_V1"
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
LOGICAL_WIDTH = 1024
LOGICAL_HEIGHT = 600
CONTROLLER_WIDTH = 512
GRID_X0 = 40
GRID_Y0 = 120
GRID_ROWS = 2
GRID_COLUMNS = 4
CELL_WIDTH = 96
CELL_HEIGHT = 120
GAP_X = 20
GAP_Y = 40
INNER_CROP_FRACTION = 0.56
ALIGNMENT_CONTRAST_FLOOR_DE76 = 5.0
ALIGNMENT_MIN_CONTRASTING_CELLS = 8


class SameR20AtlasAnalysisError(RuntimeError):
    """Raised when photo/reference evidence or output is invalid."""


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
        raise SameR20AtlasAnalysisError(
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
            raise SameR20AtlasAnalysisError(
                f"{label} must be a regular non-symlink file: {path}"
            )
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise SameR20AtlasAnalysisError(f"cannot read {label}: {exc}") from exc
    before_id = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_id = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_id != after_id or len(payload) != after.st_size:
        raise SameR20AtlasAnalysisError(f"{label} changed while read")
    return payload


def _load_json(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    payload = _read_stable_regular(path, label=label)
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {item}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SameR20AtlasAnalysisError(
            f"{label} is not strict UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise SameR20AtlasAnalysisError(f"{label} root must be an object")
    return payload, value


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SameR20AtlasAnalysisError(f"{label} must be an object")
    return value


def _verify_integrity(root: Mapping[str, Any]) -> str:
    integrity = _mapping(root.get("integrity"), label="reference.integrity")
    if set(integrity) != {"algorithm", "sha256"}:
        raise SameR20AtlasAnalysisError("reference integrity keys differ")
    if integrity.get("algorithm") != INTEGRITY_ALGORITHM:
        raise SameR20AtlasAnalysisError("reference integrity algorithm differs")
    declared = integrity.get("sha256")
    if not isinstance(declared, str) or len(declared) != 64:
        raise SameR20AtlasAnalysisError("reference integrity SHA differs")
    unsigned = dict(root)
    unsigned.pop("integrity", None)
    if _sha256_bytes(_canonical_json(unsigned)) != declared:
        raise SameR20AtlasAnalysisError("reference integrity SHA differs")
    return declared


def _lab_from_rgb(rgb: np.ndarray) -> np.ndarray:
    sample = np.uint8(np.clip(np.rint(rgb), 0, 255)).reshape(1, 1, 3)
    lab = cv2.cvtColor(sample, cv2.COLOR_RGB2LAB)[0, 0].astype(np.float64)
    lab[0] *= 100.0 / 255.0
    lab[1:] -= 128.0
    return lab


def _logical_bounds(
    controller: int, row: int, column: int
) -> tuple[int, int, int, int]:
    x0 = controller * CONTROLLER_WIDTH + GRID_X0 + column * (CELL_WIDTH + GAP_X)
    y0 = GRID_Y0 + row * (CELL_HEIGHT + GAP_Y)
    return x0, y0, x0 + CELL_WIDTH, y0 + CELL_HEIGHT


def _decode_image(path: Path) -> tuple[bytes, np.ndarray]:
    payload = _read_stable_regular(path, label="atlas photo")
    image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.ndim != 3 or image.shape[2] != 3:
        raise SameR20AtlasAnalysisError("atlas photo is not a colour image")
    return payload, image


def _sample_rectified(
    image: np.ndarray, homography: np.ndarray
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        inverse = np.linalg.inv(homography)
    except np.linalg.LinAlgError as exc:
        raise SameR20AtlasAnalysisError("reference homography is singular") from exc
    rectified = cv2.warpPerspective(
        image,
        inverse,
        (LOGICAL_WIDTH, LOGICAL_HEIGHT),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )
    valid_source = np.full(image.shape[:2], 255, dtype=np.uint8)
    validity = cv2.warpPerspective(
        valid_source,
        inverse,
        (LOGICAL_WIDTH, LOGICAL_HEIGHT),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    records: list[dict[str, Any]] = []
    contrast_count = 0
    valid_fractions: list[float] = []
    for controller in range(2):
        for row in range(GRID_ROWS):
            for column in range(GRID_COLUMNS):
                x0, y0, x1, y1 = _logical_bounds(controller, row, column)
                margin_x = round(CELL_WIDTH * (1.0 - INNER_CROP_FRACTION) / 2.0)
                margin_y = round(CELL_HEIGHT * (1.0 - INNER_CROP_FRACTION) / 2.0)
                patch = rectified[
                    y0 + margin_y : y1 - margin_y,
                    x0 + margin_x : x1 - margin_x,
                ]
                valid_patch = validity[
                    y0 + margin_y : y1 - margin_y,
                    x0 + margin_x : x1 - margin_x,
                ]
                valid = valid_patch > 0
                valid_fraction = float(np.mean(valid))
                valid_fractions.append(valid_fraction)
                if patch.size == 0 or np.count_nonzero(valid) < 64:
                    raise SameR20AtlasAnalysisError("one atlas cell is not visible")
                rgb_pixels = patch[valid][:, ::-1].astype(np.float64)
                median_rgb = np.median(rgb_pixels, axis=0)
                mad_rgb = np.median(np.abs(rgb_pixels - median_rgb), axis=0)
                lab = _lab_from_rgb(median_rgb)

                ring = rectified[max(0, y0 - 8) : y0, x0:x1]
                ring_valid = validity[max(0, y0 - 8) : y0, x0:x1] > 0
                if ring.size and np.count_nonzero(ring_valid) >= 32:
                    ring_rgb = np.median(
                        ring[ring_valid][:, ::-1].astype(np.float64), axis=0
                    )
                    contrast = float(np.linalg.norm(lab - _lab_from_rgb(ring_rgb)))
                else:
                    contrast = 0.0
                contrast_count += int(contrast >= ALIGNMENT_CONTRAST_FLOOR_DE76)
                code = row * GRID_COLUMNS + column
                records.append(
                    {
                        "cell_id": f"C{controller}-CODE{code}",
                        "controller": controller,
                        "row": row,
                        "column": column,
                        "code": code,
                        "logical_bounds": [x0, y0, x1, y1],
                        "inner_patch_valid_fraction": valid_fraction,
                        "robust_rgb_median": median_rgb.astype(float).tolist(),
                        "robust_rgb_mad": mad_rgb.astype(float).tolist(),
                        "camera_relative_lab": lab.astype(float).tolist(),
                        "cell_to_top_separator_de76": contrast,
                    }
                )
    return records, {
        "minimum_inner_patch_valid_fraction": min(valid_fractions),
        "contrasting_cell_count": contrast_count,
        "minimum_required_contrasting_cells": ALIGNMENT_MIN_CONTRASTING_CELLS,
        "reference_homography_alignment_guard_pass": (
            min(valid_fractions) >= 0.98
            and contrast_count >= ALIGNMENT_MIN_CONTRASTING_CELLS
        ),
    }


def analyze(
    photo_path: Path,
    reference_grid_path: Path,
    *,
    role: str,
    repeat_noise_p95_de76: float | None = None,
) -> dict[str, Any]:
    """Return an offline camera-relative paired-controller report."""

    normalized_role = role.upper()
    if normalized_role not in {"AA", "CC"}:
        raise SameR20AtlasAnalysisError("role must be AA or CC")
    if repeat_noise_p95_de76 is not None and (
        not math.isfinite(repeat_noise_p95_de76) or repeat_noise_p95_de76 < 0
    ):
        raise SameR20AtlasAnalysisError("repeat noise must be finite and nonnegative")

    reference_payload, reference = _load_json(
        reference_grid_path, label="reference grid"
    )
    if reference.get("schema_version") != 1 or reference.get("kind") != REFERENCE_KIND:
        raise SameR20AtlasAnalysisError("reference schema identity differs")
    layout = _mapping(reference.get("campaign_layout"), label="reference layout")
    if layout.get("id") != REFERENCE_LAYOUT:
        raise SameR20AtlasAnalysisError("reference layout identity differs")
    judgement = _mapping(reference.get("grid_judgement"), label="reference judgement")
    if judgement.get("enough_to_interpret_grid_camera_relatively") is not True:
        raise SameR20AtlasAnalysisError("reference geometry is insufficient")
    reference_integrity = _verify_integrity(reference)
    geometry = _mapping(reference.get("geometry_quality"), label="reference geometry")
    raw_homography = geometry.get("homography_logical_to_photo")
    try:
        homography = np.asarray(raw_homography, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise SameR20AtlasAnalysisError("reference homography differs") from exc
    if homography.shape != (3, 3) or not np.all(np.isfinite(homography)):
        raise SameR20AtlasAnalysisError("reference homography differs")

    photo_payload, image = _decode_image(photo_path)
    source_photo = _mapping(reference.get("source_photo"), label="reference photo")
    if image.shape[1] != source_photo.get("width") or image.shape[
        0
    ] != source_photo.get("height"):
        raise SameR20AtlasAnalysisError("atlas and reference dimensions differ")
    cells, alignment = _sample_rectified(image, homography)
    by_key = {(item["controller"], item["code"]): item for item in cells}
    pairs: list[dict[str, Any]] = []
    for code in range(8):
        left = by_key[(0, code)]
        right = by_key[(1, code)]
        left_lab = np.asarray(left["camera_relative_lab"], dtype=np.float64)
        right_lab = np.asarray(right["camera_relative_lab"], dtype=np.float64)
        pairs.append(
            {
                "code": code,
                "camera_relative_de76": float(np.linalg.norm(left_lab - right_lab)),
                "absolute_lstar_difference": float(abs(left_lab[0] - right_lab[0])),
                "cs1_lab": left_lab.astype(float).tolist(),
                "cs2_lab": right_lab.astype(float).tolist(),
            }
        )
    deltas = [item["camera_relative_de76"] for item in pairs]
    threshold = (
        None if repeat_noise_p95_de76 is None else max(4.0, 3.0 * repeat_noise_p95_de76)
    )
    pair_gate = (
        None
        if threshold is None
        or not alignment["reference_homography_alignment_guard_pass"]
        else all(item <= threshold for item in deltas)
    )
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "analysis_id": _sha256_bytes(
            _canonical_json(
                {
                    "photo_sha256": _sha256_bytes(photo_payload),
                    "reference_file_sha256": _sha256_bytes(reference_payload),
                    "role": normalized_role,
                    "method": "same-r20-reference-homography-paired-atlas-v1",
                }
            )
        ),
        "role": normalized_role,
        "layout": {
            "id": LAYOUT_ID,
            "controller_count": 2,
            "rows": GRID_ROWS,
            "columns_per_controller": GRID_COLUMNS,
            "code_mapping": "code = row * 4 + column",
            "same_dtm_both_controllers": True,
        },
        "source_photo": {
            "path": str(photo_path),
            "bytes": len(photo_payload),
            "sha256": _sha256_bytes(photo_payload),
            "width": int(image.shape[1]),
            "height": int(image.shape[0]),
        },
        "reference_geometry": {
            "path": str(reference_grid_path),
            "bytes": len(reference_payload),
            "file_sha256": _sha256_bytes(reference_payload),
            "canonical_integrity_sha256": reference_integrity,
            "camera_must_not_have_moved": True,
        },
        "geometry_guard": alignment,
        "cells": cells,
        "left_right_pairs": pairs,
        "paired_summary": {
            "camera_relative_de76_median": float(np.median(deltas)),
            "camera_relative_de76_p95": float(np.percentile(deltas, 95)),
            "camera_relative_de76_max": float(max(deltas)),
            "repeat_noise_p95_de76": repeat_noise_p95_de76,
            "exploratory_threshold_de76": threshold,
            "all_pairs_within_exploratory_threshold": pair_gate,
        },
        "classification": {
            "state": (
                "CAMERA_RELATIVE_CONTROLLER_MATCH_CANDIDATE"
                if pair_gate is True
                else (
                    "CAMERA_RELATIVE_CONTROLLER_MISMATCH_CANDIDATE"
                    if pair_gate is False
                    else "INCONCLUSIVE_NEEDS_NOISE_BASELINE_OR_GEOMETRY"
                )
            ),
            "controller_equivalence_proven": False,
            "absolute_colour_proven": False,
            "qualified_new_colour": False,
        },
        "evidence_boundaries": {
            "camera_relative_de76_not_calibrated_de00": True,
            "reference_homography_reuse_requires_fixed_camera": True,
            "compiled_identical_payload_does_not_prove_bus_reception": True,
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
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, flags, 0o644)
    except FileExistsError as exc:
        raise SameR20AtlasAnalysisError(
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
    parser.add_argument("--photo", type=Path, required=True)
    parser.add_argument("--reference-grid-analysis", type=Path, required=True)
    parser.add_argument("--role", choices=("AA", "CC"), required=True)
    parser.add_argument("--repeat-noise-p95-de76", type=float)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = analyze(
            args.photo,
            args.reference_grid_analysis,
            role=args.role,
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
    except SameR20AtlasAnalysisError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
