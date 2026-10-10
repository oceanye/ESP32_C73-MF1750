#!/usr/bin/env python3
"""Seal the MF1750 G-1 locked-camera Action-4 P0 geometry anchor.

This is a pure-offline evidence combiner.  It deep-validates one existing
camera capture sidecar and one 128-cell Action-4 grid-analysis report, then
freezes their exact photo, camera lock, homography, and P0 recipe positions.
The resulting record is deliberately retrospective geometry evidence only;
it never upgrades a delayed retained-screen photograph to live-action proof.
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
import re
import stat
from typing import Any

import numpy as np

from tools import mf1750_camera_capture_evidence as camera


SCHEMA_VERSION = 1
KIND = "mf1750-g1-locked-full-panel-p0-geometry-anchor"
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
GRID_KIND = "mf1750-redpink-v2-dual-8x8-camera-relative-grid-photo-analysis"
GRID_LAYOUT_ID = "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_V2"
CLASSIFICATION = "RETROSPECTIVE_GEOMETRY_AND_P0_ONLY"
MANUAL_CONTROLS = {
    "autofocus": 0.0,
    "auto_exposure": 0.25,
    "auto_white_balance": 0.0,
}
DSHOW_MANUAL_RAW_VALUES = {
    "autofocus": (0.0, 2.0),
    "auto_exposure": (-1.0, 0.25),
    "auto_white_balance": (0.0,),
}
LOCKED_NUMERIC_FIELDS = ("focus", "exposure", "white_balance_temperature")
MAX_RMSE_PX = 2.0
MAX_P95_PX = 3.0
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class G1P0GeometryAnchorError(RuntimeError):
    """Raised when a G-1 anchor input or exclusive output is invalid."""


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
        raise G1P0GeometryAnchorError(
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
            raise G1P0GeometryAnchorError(
                f"{label} must be a regular non-symlink file: {path}"
            )
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise G1P0GeometryAnchorError(f"cannot read {label}: {exc}") from exc
    before_id = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_id = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_id != after_id or len(payload) != after.st_size:
        raise G1P0GeometryAnchorError(f"{label} changed while it was read")
    return payload


def _load_json(path: Path, *, label: str) -> tuple[bytes, Mapping[str, Any]]:
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
        raise G1P0GeometryAnchorError(
            f"{label} is not strict UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(root, Mapping):
        raise G1P0GeometryAnchorError(f"{label} root must be an object")
    return payload, root


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise G1P0GeometryAnchorError(f"{label} must be an object")
    return value


def _text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise G1P0GeometryAnchorError(f"{label} must be a non-empty string")
    return value


def _sha256(value: Any, *, label: str) -> str:
    text = _text(value, label=label)
    if not _SHA256_RE.fullmatch(text):
        raise G1P0GeometryAnchorError(f"{label} must be lowercase SHA-256")
    return text


def _number(value: Any, *, label: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise G1P0GeometryAnchorError(f"{label} must be a finite number")
    return float(value)


def _verify_integrity(root: Mapping[str, Any], *, label: str) -> str:
    integrity = _mapping(root.get("integrity"), label=f"{label}.integrity")
    if set(integrity) != {"algorithm", "sha256"}:
        raise G1P0GeometryAnchorError(f"{label}.integrity keys differ")
    if integrity.get("algorithm") != INTEGRITY_ALGORITHM:
        raise G1P0GeometryAnchorError(f"{label}.integrity algorithm differs")
    declared = _sha256(integrity.get("sha256"), label=f"{label}.integrity.sha256")
    unsigned = dict(root)
    unsigned.pop("integrity", None)
    if _sha256_bytes(_canonical_json(unsigned)) != declared:
        raise G1P0GeometryAnchorError(f"{label}.integrity SHA-256 differs")
    return declared


def _camera_lock(root: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    coverage = _mapping(root.get("coverage"), label="capture.coverage")
    if (
        coverage.get("scope") != camera.COVERAGE_FULL
        or coverage.get("full_panel_visible") is not True
        or coverage.get("full_panel_uncropped") is not True
    ):
        raise G1P0GeometryAnchorError(
            "capture must be full_panel, fully visible, and uncropped"
        )
    mount_id = _text(coverage.get("mount_id"), label="capture.coverage.mount_id")
    record = _mapping(root.get("camera"), label="capture.camera")
    camera_tuple = {
        "camera_id": _text(record.get("camera_id"), label="camera.camera_id"),
        "instance_id": _text(record.get("instance_id"), label="camera.instance_id"),
        "index": record.get("index"),
        "backend": _text(record.get("backend"), label="camera.backend"),
    }
    if type(camera_tuple["index"]) is not int or camera_tuple["index"] < 0:
        raise G1P0GeometryAnchorError("camera.index must be a non-negative integer")
    requested = dict(
        _mapping(record.get("requested_settings"), label="camera.requested_settings")
    )
    before = dict(
        _mapping(
            record.get("effective_settings_before_frame"),
            label="camera.effective_settings_before_frame",
        )
    )
    after = dict(
        _mapping(
            record.get("effective_settings_after_frame"),
            label="camera.effective_settings_after_frame",
        )
    )
    if before != after:
        raise G1P0GeometryAnchorError(
            "camera effective readback changed around the captured frame"
        )
    set_results = dict(_mapping(record.get("set_results"), label="camera.set_results"))
    required_lock_writes = {
        "autofocus",
        "focus",
        "auto_exposure",
        "exposure",
        "auto_white_balance",
        "white_balance_temperature",
    }
    if not required_lock_writes.issubset(set_results):
        raise G1P0GeometryAnchorError(
            "camera.set_results is missing one or more lock-setting writes"
        )
    if any(type(value) is not bool for value in set_results.values()):
        raise G1P0GeometryAnchorError("camera.set_results values must be booleans")
    failed_writes = sorted(
        field for field, success in set_results.items() if not success
    )
    if failed_writes:
        raise G1P0GeometryAnchorError(
            f"camera setting writes failed: {failed_writes!r}"
        )

    backend = camera_tuple["backend"].upper()
    accepted_raw_values = (
        DSHOW_MANUAL_RAW_VALUES
        if "DSHOW" in backend
        else {field: (expected,) for field, expected in MANUAL_CONTROLS.items()}
    )
    effective_raw_modes: dict[str, float] = {}
    normalized_modes: dict[str, bool] = {}
    normalization_used = False
    for field, expected in MANUAL_CONTROLS.items():
        if _number(requested.get(field), label=f"requested.{field}") != expected:
            raise G1P0GeometryAnchorError(f"requested.{field} must equal {expected:g}")
        raw = _number(before.get(field), label=f"effective.{field}")
        if raw not in accepted_raw_values[field]:
            raise G1P0GeometryAnchorError(
                f"effective.{field} raw value {raw:g} is not an accepted "
                f"{backend} manual-mode encoding"
            )
        effective_raw_modes[field] = raw
        normalized_modes[field] = True
        normalization_used = normalization_used or raw != expected
    for field in LOCKED_NUMERIC_FIELDS:
        requested_value = _number(requested.get(field), label=f"requested.{field}")
        effective_value = _number(before.get(field), label=f"effective.{field}")
        if effective_value != requested_value:
            raise G1P0GeometryAnchorError(
                f"effective.{field} must equal its requested locked value"
            )
    if type(record.get("read_failures")) is not int or record["read_failures"] != 0:
        raise G1P0GeometryAnchorError("camera.read_failures must equal zero")
    warmup_requested = record.get("warmup_frames_requested")
    warmup_completed = record.get("warmup_frames_completed")
    if (
        type(warmup_requested) is not int
        or warmup_requested < 1
        or warmup_completed != warmup_requested
    ):
        raise G1P0GeometryAnchorError("camera warmup must be positive and complete")
    lock = {
        "camera_tuple": camera_tuple,
        "mount_id": mount_id,
        "requested_settings": requested,
        "effective_settings_before_frame": before,
        "effective_settings_after_frame": after,
        "set_results": set_results,
        "effective_readback_equal": True,
        "manual_control_contract": dict(MANUAL_CONTROLS),
        "manual_mode_readback_normalization": {
            "policy": (
                "DSHOW_DRIVER_SPECIFIC_RAW_ENUM_V1"
                if "DSHOW" in backend
                else "EXACT_REQUESTED_VALUE_V1"
            ),
            "backend": camera_tuple["backend"],
            "effective_raw_values": effective_raw_modes,
            "accepted_raw_values": {
                field: list(values) for field, values in accepted_raw_values.items()
            },
            "normalized_manual_state": normalized_modes,
            "driver_specific_normalization_used": normalization_used,
        },
    }
    lock["signature_sha256"] = _sha256_bytes(_canonical_json(lock))
    return lock, coverage


def _validate_cells(
    cells: Any, *, width: int, height: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(cells, list) or len(cells) != 128:
        raise G1P0GeometryAnchorError("grid report must contain exactly 128 cells")
    anchors: list[dict[str, Any]] = []
    by_key: dict[tuple[int, int, int], Mapping[str, Any]] = {}
    for item in cells:
        cell = _mapping(item, label="grid cell")
        controller, row, column = (
            cell.get("controller"),
            cell.get("row"),
            cell.get("column"),
        )
        key = (controller, row, column)
        if (
            type(controller) is not int
            or controller not in (0, 1)
            or type(row) is not int
            or row not in range(8)
            or type(column) is not int
            or column not in range(8)
            or key in by_key
        ):
            raise G1P0GeometryAnchorError("grid cell coverage is not unique 2x8x8")
        expected_id = f"C{controller}-R{row}-K{column}"
        expected_recipe = f"REDPINK-A{column}-B{row}-A0"
        if (
            cell.get("cell_id") != expected_id
            or cell.get("recipe_id") != expected_recipe
        ):
            raise G1P0GeometryAnchorError("grid cell identity/recipe mapping differs")
        if (
            cell.get("all_corners_inside_photo") is not True
            or _number(
                cell.get("inner_patch_valid_fraction"),
                label=f"{expected_id}.inner_patch_valid_fraction",
            )
            != 1.0
            or cell.get("contour_support_detected") is not True
        ):
            raise G1P0GeometryAnchorError(
                f"{expected_id} geometry support is incomplete"
            )
        bounds = cell.get("logical_bounds")
        corners = cell.get("projected_photo_corners")
        if not isinstance(bounds, list) or len(bounds) != 4:
            raise G1P0GeometryAnchorError(f"{expected_id}.logical_bounds differs")
        if not isinstance(corners, list) or len(corners) != 4:
            raise G1P0GeometryAnchorError(f"{expected_id}.projected corners differ")
        for corner in corners:
            if not isinstance(corner, list) or len(corner) != 2:
                raise G1P0GeometryAnchorError(f"{expected_id}.projected corner differs")
            x = _number(corner[0], label=f"{expected_id}.corner.x")
            y = _number(corner[1], label=f"{expected_id}.corner.y")
            if not (0 <= x < width and 0 <= y < height):
                raise G1P0GeometryAnchorError(f"{expected_id} corner is outside photo")
        by_key[key] = cell
        anchors.append(
            {
                "cell_id": expected_id,
                "controller": controller,
                "row": row,
                "column": column,
                "recipe_id": expected_recipe,
                "logical_bounds": list(bounds),
                "projected_photo_corners": [list(corner) for corner in corners],
            }
        )
    anchors.sort(key=lambda item: (item["controller"], item["row"], item["column"]))
    recipes: list[dict[str, Any]] = []
    for row in range(8):
        for column in range(8):
            recipes.append(
                {
                    "recipe_id": f"REDPINK-A{column}-B{row}-A0",
                    "source_code": column,
                    "middle_code": row,
                    "target_code": 0,
                    "p0_cells": [
                        by_key[(controller, row, column)]["cell_id"]
                        for controller in range(2)
                    ],
                }
            )
    return anchors, recipes


def _validate_grid(
    path: Path, photo: Mapping[str, Any]
) -> tuple[bytes, Mapping[str, Any], str, dict[str, Any]]:
    payload, root = _load_json(path, label="grid analysis")
    expected_keys = {
        "schema_version",
        "kind",
        "source_photo",
        "campaign_layout",
        "method",
        "geometry_quality",
        "grid_judgement",
        "cells",
        "row_column_differences",
        "smooth_spatial_models",
        "candidate_ranking_metadata",
        "cell_candidate_ranking",
        "recipe_candidate_ranking",
        "integrity",
    }
    if set(root) != expected_keys:
        raise G1P0GeometryAnchorError("grid analysis top-level keys differ")
    if root.get("schema_version") != 1 or root.get("kind") != GRID_KIND:
        raise G1P0GeometryAnchorError("grid analysis schema identity differs")
    integrity = _verify_integrity(root, label="grid analysis")
    source = _mapping(root.get("source_photo"), label="grid.source_photo")
    for field in ("bytes", "sha256", "width", "height"):
        if source.get(field) != photo.get(field):
            raise G1P0GeometryAnchorError(
                f"grid source photo {field} differs from capture sidecar"
            )
    width, height = source.get("width"), source.get("height")
    if type(width) is not int or type(height) is not int or min(width, height) < 1:
        raise G1P0GeometryAnchorError("grid source dimensions are invalid")
    layout = _mapping(root.get("campaign_layout"), label="grid.campaign_layout")
    if layout.get("id") != GRID_LAYOUT_ID or layout.get("action_ordinal") != 4:
        raise G1P0GeometryAnchorError("grid must be the frozen Action-4 layout")
    method = _mapping(root.get("method"), label="grid.method")
    if (
        method.get("perspective_rectified") is not True
        or method.get("all_128_logical_cells_sampled") is not True
        or method.get("physical_colour_calibrated") is not False
    ):
        raise G1P0GeometryAnchorError("grid analysis method differs")
    judgement = _mapping(root.get("grid_judgement"), label="grid.grid_judgement")
    if (
        judgement.get("enough_to_interpret_grid_camera_relatively") is not True
        or judgement.get("verdict") != "SUFFICIENT_CAMERA_RELATIVE_GRID_READOUT"
        or judgement.get("blocking_reasons") != []
        or judgement.get("camera_relative_only") is not True
        or judgement.get("photo_dimensions") != [width, height]
    ):
        raise G1P0GeometryAnchorError("grid judgement is not sufficient")
    geometry = _mapping(root.get("geometry_quality"), label="grid.geometry_quality")
    exact = {
        "unique_cell_contour_support": 128,
        "expected_coloured_contour_support_for_action": 128,
        "support_by_controller": [64, 64],
        "homography_inliers": 128,
        "homography_correspondences": 128,
    }
    for field, value in exact.items():
        if geometry.get(field) != value:
            raise G1P0GeometryAnchorError(f"grid geometry {field} differs")
    if (
        _number(
            geometry.get("support_fraction_of_action_expectation"),
            label="geometry.support_fraction",
        )
        != 1.0
        or _number(
            geometry.get("homography_inlier_fraction"),
            label="geometry.inlier_fraction",
        )
        != 1.0
    ):
        raise G1P0GeometryAnchorError("grid geometry support is not complete")
    rmse = _number(geometry.get("homography_inlier_rmse_px"), label="geometry.rmse")
    p95 = _number(geometry.get("homography_inlier_p95_px"), label="geometry.p95")
    if rmse > MAX_RMSE_PX or p95 > MAX_P95_PX:
        raise G1P0GeometryAnchorError("grid homography residual exceeds G-1 gate")
    sampling = _mapping(geometry.get("sampling"), label="geometry.sampling")
    if (
        sampling.get("all_cell_corners_inside_photo") is not True
        or _number(
            sampling.get("minimum_inner_patch_valid_fraction"),
            label="sampling.minimum_inner_patch_valid_fraction",
        )
        != 1.0
        or _number(
            sampling.get("minimum_projected_cell_width_px"),
            label="sampling.minimum_projected_cell_width_px",
        )
        < 20.0
        or _number(
            sampling.get("minimum_projected_cell_height_px"),
            label="sampling.minimum_projected_cell_height_px",
        )
        < 20.0
    ):
        raise G1P0GeometryAnchorError("grid sampling geometry is insufficient")
    try:
        homography = np.asarray(
            geometry.get("homography_logical_to_photo"), dtype=np.float64
        )
    except (TypeError, ValueError) as exc:
        raise G1P0GeometryAnchorError("grid homography is invalid") from exc
    if (
        homography.shape != (3, 3)
        or not np.all(np.isfinite(homography))
        or abs(float(np.linalg.det(homography))) <= 1e-12
    ):
        raise G1P0GeometryAnchorError("grid homography is invalid")
    anchors, recipes = _validate_cells(root.get("cells"), width=width, height=height)
    geometry_p0 = {
        "coordinate_space": "frozen logical 1024x600 to captured photo pixels",
        "layout_id": GRID_LAYOUT_ID,
        "action_ordinal": 4,
        "homography_logical_to_photo": homography.astype(float).tolist(),
        "quality_gate": {
            "unique_cell_contour_support": 128,
            "support_by_controller": [64, 64],
            "homography_inliers": 128,
            "homography_correspondences": 128,
            "homography_inlier_rmse_px": rmse,
            "homography_inlier_p95_px": p95,
            "maximum_allowed_rmse_px": MAX_RMSE_PX,
            "maximum_allowed_p95_px": MAX_P95_PX,
            "minimum_inner_patch_valid_fraction": 1.0,
            "all_cell_corners_inside_photo": True,
        },
        "cell_anchors": anchors,
        "p0_recipe_map": recipes,
    }
    return payload, root, integrity, geometry_p0


def build_anchor(
    capture_sidecar_path: Path, grid_analysis_path: Path
) -> dict[str, Any]:
    """Build and canonically seal one offline G-1 geometry/P0 anchor."""

    sidecar_path = Path(capture_sidecar_path)
    grid_path = Path(grid_analysis_path)
    try:
        capture_root = camera.validate_capture_evidence(sidecar_path)
    except camera.CameraCaptureEvidenceError as exc:
        raise G1P0GeometryAnchorError(str(exc)) from exc
    capture_payload = _read_stable_regular(sidecar_path, label="capture sidecar")
    capture_integrity = _sha256(
        _mapping(capture_root.get("integrity"), label="capture.integrity").get(
            "sha256"
        ),
        label="capture.integrity.sha256",
    )
    binding = capture_root.get("capture_binding")
    if binding not in {
        camera.BINDING_LIVE,
        camera.BINDING_RETROSPECTIVE,
        camera.BINDING_LOCKED_RETAINED,
    }:
        raise G1P0GeometryAnchorError("capture binding is invalid")
    camera_lock, coverage = _camera_lock(capture_root)
    photo = _mapping(capture_root.get("photo"), label="capture.photo")
    try:
        photo_path = camera._resolve_evidence_path(
            photo.get("path"),
            sidecar_path=sidecar_path,
            label="capture.photo.path",
        )
        photo_payload = camera._read_stable_regular(photo_path, label="bound photo")
    except camera.CameraCaptureEvidenceError as exc:
        raise G1P0GeometryAnchorError(str(exc)) from exc
    photo_sha = _sha256_bytes(photo_payload)
    if photo.get("sha256") != photo_sha or photo.get("bytes") != len(photo_payload):
        raise G1P0GeometryAnchorError("capture photo binding changed after validation")
    grid_payload, grid_root, grid_integrity, geometry_p0 = _validate_grid(
        grid_path, photo
    )
    capture_record = {
        "path": str(sidecar_path),
        "bytes": len(capture_payload),
        "file_sha256": _sha256_bytes(capture_payload),
        "canonical_integrity_sha256": capture_integrity,
        "capture_id": _text(capture_root.get("capture_id"), label="capture_id"),
        "capture_binding": binding,
        "captured_at": _text(capture_root.get("captured_at"), label="captured_at"),
        "campaign_id": _text(capture_root.get("campaign_id"), label="campaign_id"),
        "test_id": _text(capture_root.get("test_id"), label="test_id"),
        "action_id": _sha256(capture_root.get("action_id"), label="action_id"),
        "ordinal": capture_root.get("ordinal"),
        "role": _text(capture_root.get("role"), label="role"),
    }
    if type(capture_record["ordinal"]) is not int or capture_record["ordinal"] < 1:
        raise G1P0GeometryAnchorError("capture ordinal is invalid")
    photo_record = {
        "path": str(photo_path),
        "bytes": len(photo_payload),
        "sha256": photo_sha,
        "width": photo.get("width"),
        "height": photo.get("height"),
        "mode": photo.get("mode"),
        "coverage_scope": coverage.get("scope"),
        "full_panel_visible": True,
        "full_panel_uncropped": True,
    }
    source = _mapping(grid_root.get("source_photo"), label="grid.source_photo")
    grid_record = {
        "path": str(grid_path),
        "bytes": len(grid_payload),
        "file_sha256": _sha256_bytes(grid_payload),
        "canonical_integrity_sha256": grid_integrity,
        "kind": GRID_KIND,
        "layout_id": GRID_LAYOUT_ID,
        "action_ordinal": 4,
        "source_photo_sha256": source.get("sha256"),
    }
    anchor_id = _sha256_bytes(
        _canonical_json(
            {
                "method": "g1-locked-full-panel-action4-p0-geometry-anchor-v1",
                "capture_file_sha256": capture_record["file_sha256"],
                "photo_sha256": photo_sha,
                "grid_analysis_file_sha256": grid_record["file_sha256"],
                "camera_lock_signature_sha256": camera_lock["signature_sha256"],
            }
        )
    )
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "anchor_id": anchor_id,
        "created_at": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "capture": capture_record,
        "photo": photo_record,
        "camera_lock": camera_lock,
        "grid_analysis": grid_record,
        "geometry_p0": geometry_p0,
        "classification": {
            "state": CLASSIFICATION,
            "geometry_anchor_pass": True,
            "p0_position_baseline_pass": True,
            "retrospective_only": True,
            "live_action_evidence": False,
            "temporal_action_continuity_proven": False,
            "action_causality_proven": False,
            "absolute_colour_proven": False,
            "qualified_colour_proven": False,
            "input_live_binding_was_not_propagated": binding == camera.BINDING_LIVE,
        },
        "evidence_boundaries": {
            "retained_screen_photo_used_only_for_geometry_and_p0_positions": True,
            "capture_sidecar_binding_preserved_as_input_metadata_only": True,
            "delayed_capture_does_not_prove_the_historical_action": True,
            "camera_mount_and_settings_are_declared_evidence_not_physical_authentication": True,
            "camera_relative_not_absolute_colour": True,
            "device_camera_network_serial_relay_io_performed_by_builder": False,
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
        descriptor = os.open(path, flags, 0o644)
    except FileExistsError as exc:
        raise G1P0GeometryAnchorError(
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
    parser.add_argument("--capture-sidecar", type=Path, required=True)
    parser.add_argument("--grid-analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = build_anchor(args.capture_sidecar, args.grid_analysis)
        _write_exclusive(
            args.output,
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            ).encode("utf-8")
            + b"\n",
        )
    except G1P0GeometryAnchorError as exc:
        print(f"G-1 P0 geometry anchor error: {exc}", file=os.sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
