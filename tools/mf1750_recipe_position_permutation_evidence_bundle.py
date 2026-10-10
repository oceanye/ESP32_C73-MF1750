#!/usr/bin/env python3
"""Seal the Batch-2 recipe-position-permutation evidence bundle.

This builder is deliberately offline.  It validates four immutable action
results and their live synchronized full-panel captures, a separately sealed
G-1 locked-camera P0 anchor, the ordinal-3 P1 grid analysis and recipe
comparison, and the ordinal-4 sixty-patch factory-white gate.  The output is
an exploratory recipe-linkage record and never an absolute-colour or new-
colour qualification.
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
import sys
from typing import Any

from tools import mf1750_camera_capture_evidence as camera
from tools import mf1750_factory_white_reference_photo_gate as white_gate
from tools import mf1750_g1_locked_full_panel_p0_geometry_anchor as g1_anchor
from tools import mf1750_redpink_permuted_grid_photo_analyzer as p1_grid
from tools import mf1750_redpink_recipe_permutation_comparison as comparison
from tools import mf1750_runtime_lut_recipe_position_permutation_v1_once as once
from tools import mf1750_runtime_lut_recipe_position_permutation_v1_pack as pack
from tools import mf1750_same_r20_parity_evidence_bundle as batch1_bundle


SCHEMA_VERSION = 1
KIND = "mf1750-recipe-position-permutation-evidence-bundle-v1"
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
ACTION_RESULT_KIND = "mf1750-ec5-redpink-recipe-position-permutation-v1-result"
G1_ANCHOR_KIND = g1_anchor.KIND
G1_CLASSIFICATION = g1_anchor.CLASSIFICATION
P0_LAYOUT_ID = comparison.BASE_LAYOUT_ID
P1_LAYOUT_ID = p1_grid.LAYOUT_ID
REQUIRED_MANUAL_CAMERA_SETTINGS = {
    "autofocus": 0.0,
    "auto_exposure": 0.25,
    "auto_white_balance": 0.0,
}


class RecipePositionPermutationEvidenceBundleError(RuntimeError):
    """Raised when an input binding or exclusive output is invalid."""


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
        raise RecipePositionPermutationEvidenceBundleError(
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
            raise RecipePositionPermutationEvidenceBundleError(
                f"{label} must be a regular non-symlink file: {path}"
            )
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise RecipePositionPermutationEvidenceBundleError(
            f"cannot read {label}: {exc}"
        ) from exc
    before_id = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_id = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_id != after_id or len(payload) != after.st_size:
        raise RecipePositionPermutationEvidenceBundleError(
            f"{label} changed while read"
        )
    return payload


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RecipePositionPermutationEvidenceBundleError(f"{label} must be an object")
    return value


def _sha(value: Any, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise RecipePositionPermutationEvidenceBundleError(
            f"{label} must be a lowercase SHA-256"
        )
    return value


def _number(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RecipePositionPermutationEvidenceBundleError(
            f"{label} must be a finite number"
        )
    result = float(value)
    if not math.isfinite(result):
        raise RecipePositionPermutationEvidenceBundleError(
            f"{label} must be a finite number"
        )
    return result


def _aware_datetime(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise RecipePositionPermutationEvidenceBundleError(
            f"{label} must be an ISO timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise RecipePositionPermutationEvidenceBundleError(
            f"{label} must be an ISO timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RecipePositionPermutationEvidenceBundleError(
            f"{label} must include a UTC offset"
        )
    return parsed


def _load_sealed(path: Path, *, label: str) -> tuple[bytes, dict[str, Any], str]:
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
        raise RecipePositionPermutationEvidenceBundleError(
            f"{label} is not strict UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(root, dict):
        raise RecipePositionPermutationEvidenceBundleError(
            f"{label} root must be an object"
        )
    integrity = _mapping(root.get("integrity"), label=f"{label}.integrity")
    if set(integrity) != {"algorithm", "sha256"}:
        raise RecipePositionPermutationEvidenceBundleError(
            f"{label}.integrity keys differ"
        )
    if integrity.get("algorithm") != INTEGRITY_ALGORITHM:
        raise RecipePositionPermutationEvidenceBundleError(
            f"{label}.integrity algorithm differs"
        )
    declared = _sha(integrity.get("sha256"), label=f"{label}.integrity.sha256")
    unsigned = dict(root)
    unsigned.pop("integrity", None)
    if _sha256_bytes(_canonical_json(unsigned)) != declared:
        raise RecipePositionPermutationEvidenceBundleError(
            f"{label}.integrity SHA differs"
        )
    return payload, root, declared


def _same_number(value: Any, wanted: float) -> bool:
    return type(value) in (int, float) and float(value) == wanted


def _close_number(value: Any, wanted: float) -> bool:
    return type(value) in (int, float) and math.isclose(
        float(value), wanted, rel_tol=1e-12, abs_tol=1e-12
    )


def _camera_signature_from_capture(
    root: Mapping[str, Any], *, label: str
) -> dict[str, Any]:
    camera_record = _mapping(root.get("camera"), label=f"{label}.camera")
    coverage = _mapping(root.get("coverage"), label=f"{label}.coverage")
    photo = _mapping(root.get("photo"), label=f"{label}.photo")
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
    for field, wanted in REQUIRED_MANUAL_CAMERA_SETTINGS.items():
        if not _same_number(requested.get(field), wanted):
            raise RecipePositionPermutationEvidenceBundleError(
                f"{label} camera {field} is not manually locked"
            )
    if dict(effective_before) != dict(effective_after):
        raise RecipePositionPermutationEvidenceBundleError(
            f"{label} effective camera readback drifted"
        )
    if camera_record.get("read_failures") != 0:
        raise RecipePositionPermutationEvidenceBundleError(
            f"{label} has camera read failures"
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
    if any(
        signature[key] in (None, "")
        for key in ("camera_id", "instance_id", "backend", "mount_id")
    ):
        raise RecipePositionPermutationEvidenceBundleError(
            f"{label} camera tuple or mount is incomplete"
        )
    if type(signature["index"]) is not int:
        raise RecipePositionPermutationEvidenceBundleError(
            f"{label} camera index differs"
        )
    if any(
        type(signature[key]) is not int or signature[key] <= 0
        for key in ("photo_width", "photo_height")
    ):
        raise RecipePositionPermutationEvidenceBundleError(
            f"{label} photo dimensions differ"
        )
    return signature


def _validate_action(path: Path, ordinal: int) -> tuple[dict[str, Any], datetime, str]:
    expected_name = once.ACTION_OUTPUT_NAMES[ordinal]
    if path.name != expected_name:
        raise RecipePositionPermutationEvidenceBundleError(
            f"action ordinal {ordinal} filename differs"
        )
    payload, root, integrity = _load_sealed(path, label=f"action ordinal {ordinal}")
    expected = once.base.runner.ACTIONS[ordinal - 1]
    action = _mapping(root.get("action"), label=f"action ordinal {ordinal}.action")
    terminal = _mapping(
        root.get("terminal_report"),
        label=f"action ordinal {ordinal}.terminal_report",
    )
    boot_nonce = root.get("boot_nonce")
    if (
        root.get("schema_version") != 1
        or root.get("kind") != ACTION_RESULT_KIND
        or root.get("firmware_sha256") != once.FIRMWARE_SHA256
        or root.get("outcome") != "complete_pass"
        or root.get("visible_refreshes") != 1
        or root.get("no_retry") is not True
        or root.get("no_recovery") is not True
        or root.get("no_autochain") is not True
        or action.get("ordinal") != ordinal
        or action.get("action_id") != expected["action_id"]
        or action.get("descriptor_id") != expected["descriptor_id"]
        or action.get("role") != expected["role"]
        or action.get("branch") != expected["branch"]
        or not isinstance(boot_nonce, str)
        or not boot_nonce
        or terminal.get("boot_nonce") != boot_nonce
    ):
        raise RecipePositionPermutationEvidenceBundleError(
            f"action ordinal {ordinal} identity or one-refresh contract differs"
        )
    try:
        once._validate_complete_report(terminal, ordinal, boot_nonce)
    except Exception as exc:
        raise RecipePositionPermutationEvidenceBundleError(
            f"action ordinal {ordinal} terminal COMPLETE validation failed: {exc}"
        ) from exc
    created_at = _aware_datetime(
        root.get("created_at"), label=f"action ordinal {ordinal}.created_at"
    )
    compiled = pack.build_report()["actions"][ordinal - 1]
    binding = {
        "ordinal": ordinal,
        "path": str(path),
        "file_sha256": _sha256_bytes(payload),
        "canonical_integrity_sha256": integrity,
        "created_at": root["created_at"],
        "action_id": expected["action_id"],
        "descriptor_id": expected["descriptor_id"],
        "role": expected["role"],
        "outcome": "complete_pass",
        "visible_refreshes": 1,
        "frame_sha256": compiled["frame"]["sha256"],
        "frame_fnv1a": compiled["frame"]["fnv1a"],
        "cs1_dtm_sha256": compiled["cs1_dtm"]["sha256"],
        "cs2_dtm_sha256": compiled["cs2_dtm"]["sha256"],
        "global_header": compiled["global_header"],
        "global_header_sha256": compiled["global_header_sha256"],
        "cs1_r20_prefix_sha256": compiled["cs1_r20_prefix_sha256"],
        "cs2_r20_prefix_sha256": compiled["cs2_r20_prefix_sha256"],
        "r21_sha256": compiled["r21_sha256"],
    }
    return binding, created_at, boot_nonce


def _anchor_camera_signature(
    camera_lock: Mapping[str, Any], photo: Mapping[str, Any]
) -> dict[str, Any]:
    camera_tuple = _mapping(
        camera_lock.get("camera_tuple"), label="G-1 anchor.camera_lock.camera_tuple"
    )
    requested = _mapping(
        camera_lock.get("requested_settings"),
        label="G-1 anchor.camera_lock.requested_settings",
    )
    effective_before = _mapping(
        camera_lock.get("effective_settings_before_frame"),
        label="G-1 anchor.camera_lock.effective_settings_before_frame",
    )
    effective_after = _mapping(
        camera_lock.get("effective_settings_after_frame"),
        label="G-1 anchor.camera_lock.effective_settings_after_frame",
    )
    for field, wanted in REQUIRED_MANUAL_CAMERA_SETTINGS.items():
        if not _same_number(requested.get(field), wanted) or not _same_number(
            effective_before.get(field), wanted
        ):
            raise RecipePositionPermutationEvidenceBundleError(
                f"G-1 anchor camera {field} is not manually locked"
            )
    if camera_lock.get("effective_readback_equal") is not True or dict(
        effective_before
    ) != dict(effective_after):
        raise RecipePositionPermutationEvidenceBundleError(
            "G-1 anchor effective camera readback differs"
        )
    declared_manual = _mapping(
        camera_lock.get("manual_control_contract"),
        label="G-1 anchor.camera_lock.manual_control_contract",
    )
    if dict(declared_manual) != REQUIRED_MANUAL_CAMERA_SETTINGS:
        raise RecipePositionPermutationEvidenceBundleError(
            "G-1 anchor manual camera contract differs"
        )
    unsigned_lock = dict(camera_lock)
    declared_signature = _sha(
        unsigned_lock.pop("signature_sha256", None),
        label="G-1 anchor camera-lock signature SHA",
    )
    if _sha256_bytes(_canonical_json(unsigned_lock)) != declared_signature:
        raise RecipePositionPermutationEvidenceBundleError(
            "G-1 anchor camera-lock signature differs"
        )
    signature = {
        "camera_id": camera_tuple.get("camera_id"),
        "instance_id": camera_tuple.get("instance_id"),
        "index": camera_tuple.get("index"),
        "backend": camera_tuple.get("backend"),
        "mount_id": camera_lock.get("mount_id"),
        "requested_settings": dict(requested),
        "effective_settings": dict(effective_before),
        "photo_width": photo.get("width"),
        "photo_height": photo.get("height"),
    }
    return signature


def _validate_g1_geometry(geometry: Mapping[str, Any]) -> None:
    quality = _mapping(geometry.get("quality_gate"), label="G-1 geometry.quality_gate")
    homography = geometry.get("homography_logical_to_photo")
    anchors = geometry.get("cell_anchors")
    recipes = geometry.get("p0_recipe_map")
    if (
        geometry.get("layout_id") != P0_LAYOUT_ID
        or geometry.get("action_ordinal") != 4
        or not isinstance(homography, list)
        or len(homography) != 3
        or any(not isinstance(row, list) or len(row) != 3 for row in homography)
        or quality.get("unique_cell_contour_support") != 128
        or quality.get("support_by_controller") != [64, 64]
        or quality.get("homography_inliers") != 128
        or quality.get("homography_correspondences") != 128
        or quality.get("all_cell_corners_inside_photo") is not True
        or not _same_number(quality.get("minimum_inner_patch_valid_fraction"), 1.0)
        or not isinstance(anchors, list)
        or len(anchors) != 128
        or not isinstance(recipes, list)
        or len(recipes) != 64
    ):
        raise RecipePositionPermutationEvidenceBundleError(
            "G-1 anchor P0 geometry gate or cardinality differs"
        )
    for row_index, row in enumerate(homography):
        for column_index, value in enumerate(row):
            _number(
                value,
                label=f"G-1 homography[{row_index}][{column_index}]",
            )
    seen_cells: set[tuple[int, int, int]] = set()
    for index, raw in enumerate(anchors):
        item = _mapping(raw, label=f"G-1 cell_anchors[{index}]")
        controller = item.get("controller")
        row = item.get("row")
        column = item.get("column")
        if (
            type(controller) is not int
            or controller not in (0, 1)
            or type(row) is not int
            or row not in range(8)
            or type(column) is not int
            or column not in range(8)
        ):
            raise RecipePositionPermutationEvidenceBundleError(
                f"G-1 cell_anchors[{index}] coordinate differs"
            )
        key = (controller, row, column)
        if (
            key in seen_cells
            or item.get("cell_id") != f"C{controller}-R{row}-K{column}"
            or item.get("recipe_id") != f"REDPINK-A{column}-B{row}-A0"
        ):
            raise RecipePositionPermutationEvidenceBundleError(
                f"G-1 cell_anchors[{index}] P0 mapping differs"
            )
        seen_cells.add(key)
    seen_recipes: set[str] = set()
    for index, raw in enumerate(recipes):
        item = _mapping(raw, label=f"G-1 p0_recipe_map[{index}]")
        source = item.get("source_code")
        middle = item.get("middle_code")
        expected_recipe = f"REDPINK-A{source}-B{middle}-A0"
        expected_cells = [
            f"C{controller}-R{middle}-K{source}" for controller in range(2)
        ]
        if (
            type(source) is not int
            or source not in range(8)
            or type(middle) is not int
            or middle not in range(8)
            or item.get("target_code") != 0
            or item.get("recipe_id") != expected_recipe
            or item.get("p0_cells") != expected_cells
            or expected_recipe in seen_recipes
        ):
            raise RecipePositionPermutationEvidenceBundleError(
                f"G-1 p0_recipe_map[{index}] differs"
            )
        seen_recipes.add(expected_recipe)


def _validate_g1_anchor(path: Path) -> tuple[dict[str, Any], datetime, dict[str, Any]]:
    payload, root, integrity = _load_sealed(path, label="G-1 P0 anchor")
    capture = _mapping(root.get("capture"), label="G-1 anchor.capture")
    photo = _mapping(root.get("photo"), label="G-1 anchor.photo")
    camera_lock = _mapping(root.get("camera_lock"), label="G-1 anchor.camera_lock")
    grid = _mapping(root.get("grid_analysis"), label="G-1 anchor.grid_analysis")
    geometry = _mapping(root.get("geometry_p0"), label="G-1 anchor.geometry_p0")
    classification = _mapping(
        root.get("classification"), label="G-1 anchor.classification"
    )
    if (
        root.get("schema_version") != 1
        or root.get("kind") != G1_ANCHOR_KIND
        or not isinstance(root.get("anchor_id"), str)
        or capture.get("capture_binding")
        not in {camera.BINDING_LIVE, camera.BINDING_RETROSPECTIVE}
        or photo.get("coverage_scope") != camera.COVERAGE_FULL
        or photo.get("full_panel_visible") is not True
        or photo.get("full_panel_uncropped") is not True
        or grid.get("kind") != g1_anchor.GRID_KIND
        or grid.get("layout_id") != P0_LAYOUT_ID
        or grid.get("action_ordinal") != 4
        or classification.get("state") != G1_CLASSIFICATION
        or classification.get("geometry_anchor_pass") is not True
        or classification.get("p0_position_baseline_pass") is not True
        or classification.get("retrospective_only") is not True
        or classification.get("live_action_evidence") is not False
        or classification.get("temporal_action_continuity_proven") is not False
        or classification.get("action_causality_proven") is not False
        or classification.get("absolute_colour_proven") is not False
        or classification.get("qualified_colour_proven") is not False
        or root.get("output_write_contract") != "O_EXCL"
    ):
        raise RecipePositionPermutationEvidenceBundleError(
            "G-1 anchor identity or retrospective boundary differs"
        )
    capture_file = _sha(capture.get("file_sha256"), label="G-1 capture file SHA")
    capture_integrity = _sha(
        capture.get("canonical_integrity_sha256"),
        label="G-1 capture canonical SHA",
    )
    photo_sha = _sha(photo.get("sha256"), label="G-1 photo SHA")
    grid_file = _sha(grid.get("file_sha256"), label="G-1 grid file SHA")
    grid_integrity = _sha(
        grid.get("canonical_integrity_sha256"), label="G-1 grid canonical SHA"
    )
    if grid.get("source_photo_sha256") != photo_sha:
        raise RecipePositionPermutationEvidenceBundleError(
            "G-1 anchor grid and photo binding differs"
        )
    if any(
        type(photo.get(field)) is not int or photo[field] <= 0
        for field in ("bytes", "width", "height")
    ):
        raise RecipePositionPermutationEvidenceBundleError(
            "G-1 anchor photo size or dimensions differ"
        )
    _validate_g1_geometry(geometry)
    captured_at = _aware_datetime(
        capture.get("captured_at"), label="G-1 anchor.capture.captured_at"
    )
    created_at = _aware_datetime(root.get("created_at"), label="G-1 anchor.created_at")
    if created_at < captured_at:
        raise RecipePositionPermutationEvidenceBundleError(
            "G-1 anchor creation predates its capture"
        )
    signature = _anchor_camera_signature(camera_lock, photo)
    return (
        {
            "path": str(path),
            "file_sha256": _sha256_bytes(payload),
            "canonical_integrity_sha256": integrity,
            "anchor_id": root["anchor_id"],
            "capture": {
                "capture_id": capture.get("capture_id"),
                "capture_binding": capture["capture_binding"],
                "captured_at": capture["captured_at"],
                "file_sha256": capture_file,
                "canonical_integrity_sha256": capture_integrity,
            },
            "photo_sha256": photo_sha,
            "grid_analysis": {
                "file_sha256": grid_file,
                "canonical_integrity_sha256": grid_integrity,
            },
            "classification_state": G1_CLASSIFICATION,
            "live_action_evidence": False,
        },
        captured_at,
        signature,
    )


def _validate_p1_grid(path: Path) -> tuple[dict[str, Any], str]:
    payload, root, integrity = _load_sealed(path, label="P1 ordinal-3 grid analysis")
    layout = _mapping(root.get("campaign_layout"), label="P1 grid.campaign_layout")
    source_photo = _mapping(root.get("source_photo"), label="P1 grid.source_photo")
    method = _mapping(root.get("method"), label="P1 grid.method")
    geometry = _mapping(root.get("geometry_quality"), label="P1 grid.geometry_quality")
    judgement = _mapping(root.get("grid_judgement"), label="P1 grid.grid_judgement")
    sampling = _mapping(
        geometry.get("sampling"), label="P1 grid.geometry_quality.sampling"
    )
    source_width = source_photo.get("width")
    source_height = source_photo.get("height")
    support = geometry.get("unique_cell_contour_support")
    inlier_fraction = _number(
        geometry.get("homography_inlier_fraction"),
        label="P1 grid homography inlier fraction",
    )
    rmse = _number(
        geometry.get("homography_inlier_rmse_px"), label="P1 grid homography RMSE"
    )
    if (
        root.get("schema_version") != p1_grid.SCHEMA_VERSION
        or root.get("kind") != p1_grid.KIND
        or layout.get("id") != P1_LAYOUT_ID
        or layout.get("action_ordinal") != 3
        or layout.get("source_column_shift_mod8") != 3
        or layout.get("middle_row_reversed") is not True
        or layout.get("fixed_target_code") != 0
        or method.get("perspective_rectified") is not True
        or method.get("physical_colour_calibrated") is not False
        or method.get("device_io_performed") is not False
        or type(source_photo.get("bytes")) is not int
        or source_photo["bytes"] <= 0
        or type(source_width) is not int
        or source_width <= 0
        or type(source_height) is not int
        or source_height <= 0
        or type(support) is not int
        or support < math.ceil(0.72 * 128)
        or inlier_fraction < 0.80
        or rmse > 5.0
        or _number(
            sampling.get("minimum_inner_patch_valid_fraction"),
            label="P1 grid minimum patch fraction",
        )
        < 0.98
        or sampling.get("all_cell_corners_inside_photo") is not True
        or _number(
            sampling.get("minimum_projected_cell_width_px"),
            label="P1 grid minimum projected width",
        )
        < 20.0
        or _number(
            sampling.get("minimum_projected_cell_height_px"),
            label="P1 grid minimum projected height",
        )
        < 20.0
        or judgement.get("enough_to_interpret_grid_camera_relatively") is not True
        or judgement.get("verdict") != "SUFFICIENT_CAMERA_RELATIVE_GRID_READOUT"
        or judgement.get("blocking_reasons") != []
        or judgement.get("camera_relative_only") is not True
        or judgement.get("photo_dimensions") != [source_width, source_height]
        or root.get("output_write_contract") != "O_EXCL"
    ):
        raise RecipePositionPermutationEvidenceBundleError(
            "P1 grid identity or offline boundary differs"
        )
    try:
        comparison._validate_cells(root, permuted=True)
    except comparison.RecipePermutationComparisonError as exc:
        raise RecipePositionPermutationEvidenceBundleError(str(exc)) from exc
    for index, raw in enumerate(root["cells"]):
        cell = _mapping(raw, label=f"P1 cells[{index}]")
        if (
            cell.get("all_corners_inside_photo") is not True
            or _number(
                cell.get("inner_patch_valid_fraction"),
                label=f"P1 cells[{index}].inner_patch_valid_fraction",
            )
            < 0.98
        ):
            raise RecipePositionPermutationEvidenceBundleError(
                f"P1 cells[{index}] geometry support differs"
            )
    raw_mapping = root.get("recipe_physical_mapping")
    if not isinstance(raw_mapping, list) or len(raw_mapping) != 128:
        raise RecipePositionPermutationEvidenceBundleError(
            "P1 recipe-physical mapping must contain 128 entries"
        )
    seen: set[tuple[int, int, int]] = set()
    for index, raw in enumerate(raw_mapping):
        item = _mapping(raw, label=f"P1 mapping[{index}]")
        controller = item.get("controller")
        row = item.get("physical_row")
        column = item.get("physical_column")
        if (
            type(controller) is not int
            or controller not in (0, 1)
            or type(row) is not int
            or row not in range(8)
            or type(column) is not int
            or column not in range(8)
        ):
            raise RecipePositionPermutationEvidenceBundleError(
                f"P1 mapping[{index}] coordinate differs"
            )
        key = (controller, row, column)
        source = (column + 3) % 8
        middle = 7 - row
        if (
            key in seen
            or item.get("source_code") != source
            or item.get("middle_code") != middle
            or item.get("target_code") != 0
            or item.get("recipe_id") != f"REDPINK-A{source}-B{middle}-A0"
        ):
            raise RecipePositionPermutationEvidenceBundleError(
                f"P1 mapping[{index}] recipe binding differs"
            )
        seen.add(key)
    photo_sha = _sha(source_photo.get("sha256"), label="P1 source photo SHA")
    return (
        {
            "path": str(path),
            "file_sha256": _sha256_bytes(payload),
            "canonical_integrity_sha256": integrity,
            "layout_id": P1_LAYOUT_ID,
            "action_ordinal": 3,
            "source_photo_sha256": photo_sha,
            "source_photo_width": source_width,
            "source_photo_height": source_height,
            "cell_count": 128,
            "recipe_mapping_count": 128,
            "source_column_shift_mod8": 3,
            "middle_row_reversed": True,
            "target_code": 0,
        },
        photo_sha,
    )


def _validate_recipe_comparison(
    path: Path,
    *,
    p0_file_sha256: str,
    p0_integrity_sha256: str,
    p1_file_sha256: str,
    p1_integrity_sha256: str,
) -> dict[str, Any]:
    payload, root, integrity = _load_sealed(path, label="recipe comparison")
    inputs = _mapping(root.get("inputs"), label="recipe comparison.inputs")
    baseline = _mapping(inputs.get("baseline"), label="recipe comparison.baseline")
    permuted = _mapping(inputs.get("permuted"), label="recipe comparison.permuted")
    mapping = _mapping(root.get("mapping"), label="recipe comparison.mapping")
    classification = _mapping(
        root.get("classification"), label="recipe comparison.classification"
    )
    controllers = root.get("controllers")
    allowed_states = {
        "BOTH_CONTROLLERS_RECIPE_LINKED_CANDIDATE",
        "ONE_CONTROLLER_RECIPE_LINKED_CANDIDATE",
        "NO_RECIPE_LINKED_CANDIDATE",
    }
    if (
        root.get("schema_version") != comparison.SCHEMA_VERSION
        or root.get("kind") != comparison.KIND
        or baseline.get("file_sha256") != p0_file_sha256
        or baseline.get("canonical_integrity_sha256") != p0_integrity_sha256
        or permuted.get("file_sha256") != p1_file_sha256
        or permuted.get("canonical_integrity_sha256") != p1_integrity_sha256
        or mapping.get("source_at_physical_column") != "(column + 3) mod 8"
        or mapping.get("middle_at_physical_row") != "7 - row"
        or mapping.get("target_code") != 0
        or mapping.get("bijection_verified") is not True
        or not isinstance(controllers, list)
        or len(controllers) != 2
        or classification.get("state") not in allowed_states
        or classification.get("qualified_new_colour") is not False
        or classification.get("qualified_brightness_level") is not False
        or root.get("output_write_contract") != "O_EXCL"
    ):
        raise RecipePositionPermutationEvidenceBundleError(
            "recipe comparison identity, P0/P1 binding, or boundary differs"
        )
    linked_count = 0
    seen_controllers: set[int] = set()
    for index, raw in enumerate(controllers):
        item = _mapping(raw, label=f"recipe comparison.controllers[{index}]")
        controller = item.get("controller")
        if (
            type(controller) is not int
            or controller not in (0, 1)
            or controller in seen_controllers
        ):
            raise RecipePositionPermutationEvidenceBundleError(
                "recipe comparison controller coverage differs"
            )
        seen_controllers.add(controller)
        linked = item.get("recipe_linked_candidate")
        if type(linked) is not bool:
            raise RecipePositionPermutationEvidenceBundleError(
                "recipe comparison linked flag differs"
            )
        linked_count += int(linked)
    expected_state = (
        "BOTH_CONTROLLERS_RECIPE_LINKED_CANDIDATE"
        if linked_count == 2
        else (
            "ONE_CONTROLLER_RECIPE_LINKED_CANDIDATE"
            if linked_count == 1
            else "NO_RECIPE_LINKED_CANDIDATE"
        )
    )
    if (
        classification.get("recipe_linked_controller_count") != linked_count
        or classification.get("state") != expected_state
    ):
        raise RecipePositionPermutationEvidenceBundleError(
            "recipe comparison classification is internally inconsistent"
        )
    return {
        "path": str(path),
        "file_sha256": _sha256_bytes(payload),
        "canonical_integrity_sha256": integrity,
        "comparison_id": root.get("comparison_id"),
        "classification_state": expected_state,
        "recipe_linked_controller_count": linked_count,
        "qualified_new_colour": False,
        "qualified_brightness_level": False,
    }


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _validate_terminal_white_gate(
    path: Path,
    *,
    expected_photo_sha256: str,
    expected_geometry_sha256: str,
    repeat_noise_p95_de76: float,
) -> dict[str, Any]:
    payload, root, integrity = _load_sealed(path, label="ordinal-4 white gate")
    layout = _mapping(root.get("layout"), label="white gate.layout")
    inputs = _mapping(root.get("inputs"), label="white gate.inputs")
    candidate = _mapping(inputs.get("candidate"), label="white gate.candidate")
    geometry = _mapping(
        inputs.get("geometry_reference"), label="white gate.geometry_reference"
    )
    thresholds = _mapping(root.get("thresholds"), label="white gate.thresholds")
    summary = _mapping(root.get("summary"), label="white gate.summary")
    classification = _mapping(
        root.get("classification"), label="white gate.classification"
    )
    patches = root.get("patches")
    expected_threshold = max(4.0, 3.0 * repeat_noise_p95_de76)
    expected_maximum = max(8.0, 1.5 * expected_threshold)
    if (
        root.get("schema_version") != white_gate.SCHEMA_VERSION
        or root.get("kind") != white_gate.KIND
        or layout.get("id") != white_gate.LAYOUT_ID
        or layout.get("controllers") != 2
        or layout.get("rows") not in (None, white_gate.ROWS)
        or layout.get("columns_per_controller")
        not in (None, white_gate.COLUMNS_PER_CONTROLLER)
        or layout.get("patch_count") != 60
        or candidate.get("sha256") != expected_photo_sha256
        or geometry.get("sha256") != expected_geometry_sha256
        or not _same_number(
            thresholds.get("repeat_noise_p95_de76"), repeat_noise_p95_de76
        )
        or not _same_number(thresholds.get("patch_grid_p95_de76"), expected_threshold)
        or not _same_number(thresholds.get("patch_grid_max_de76"), expected_maximum)
        or not isinstance(patches, list)
        or len(patches) != 60
        or classification.get("pass") is not True
        or classification.get("state")
        != "PANEL_WIDE_CAMERA_RELATIVE_FACTORY_WHITE_MATCH"
        or classification.get("absolute_white_proven") is not False
        or root.get("output_write_contract") != "O_EXCL"
    ):
        raise RecipePositionPermutationEvidenceBundleError(
            "ordinal-4 sixty-patch white gate differs"
        )
    seen: set[tuple[int, int, int]] = set()
    deltas: list[float] = []
    for index, raw in enumerate(patches):
        patch = _mapping(raw, label=f"white gate.patches[{index}]")
        controller = patch.get("controller")
        row = patch.get("row")
        column = patch.get("column")
        if (
            type(controller) is not int
            or controller not in (0, 1)
            or type(row) is not int
            or row not in range(white_gate.ROWS)
            or type(column) is not int
            or column not in range(white_gate.COLUMNS_PER_CONTROLLER)
        ):
            raise RecipePositionPermutationEvidenceBundleError(
                f"white gate patch {index} coordinate differs"
            )
        key = (controller, row, column)
        if key in seen:
            raise RecipePositionPermutationEvidenceBundleError(
                f"white gate patch {index} is duplicated"
            )
        seen.add(key)
        delta = _number(
            patch.get("camera_relative_de76"),
            label=f"white gate.patches[{index}].camera_relative_de76",
        )
        if delta < 0:
            raise RecipePositionPermutationEvidenceBundleError(
                "white gate patch delta must be nonnegative"
            )
        deltas.append(delta)
    observed_median = _percentile(deltas, 0.5)
    observed_p95 = _percentile(deltas, 0.95)
    observed_max = max(deltas)
    expected_summary = {
        "patch_count": 60,
        "camera_relative_de76_median": observed_median,
        "camera_relative_de76_p95": observed_p95,
        "camera_relative_de76_max": observed_max,
    }
    if (
        any(
            not _close_number(summary.get(key), value)
            for key, value in expected_summary.items()
        )
        or summary.get("all_panel_regions_match_reference") is not True
    ):
        raise RecipePositionPermutationEvidenceBundleError(
            "ordinal-4 white gate summary is internally inconsistent"
        )
    if observed_p95 > expected_threshold or observed_max > expected_maximum:
        raise RecipePositionPermutationEvidenceBundleError(
            "ordinal-4 white patches exceed the sealed threshold"
        )
    return {
        "path": str(path),
        "file_sha256": _sha256_bytes(payload),
        "canonical_integrity_sha256": integrity,
        "analysis_id": root.get("analysis_id"),
        "source_photo_sha256": expected_photo_sha256,
        "reference_geometry_sha256": expected_geometry_sha256,
        "repeat_noise_p95_de76": repeat_noise_p95_de76,
        "patch_count": 60,
        "classification_state": classification["state"],
        "pass": True,
        "absolute_white_proven": False,
    }


def _validate_capture_sidecars(
    paths: Sequence[Path],
    *,
    action_results: Sequence[Mapping[str, Any]],
    action_times: Sequence[datetime],
    boot_nonce: str,
    p1_photo_sha256: str,
    white_photo_sha256: str,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[datetime]]:
    if len(paths) != 4:
        raise RecipePositionPermutationEvidenceBundleError(
            "exactly four live synchronized capture sidecars are required"
        )
    bindings: list[dict[str, Any]] = []
    times: list[datetime] = []
    common_signature: dict[str, Any] | None = None
    expected_photos: dict[int, str] = {3: p1_photo_sha256, 4: white_photo_sha256}
    for ordinal, raw_path in enumerate(paths, 1):
        path = Path(raw_path)
        sidecar_payload = _read_stable_regular(
            path, label=f"capture sidecar ordinal {ordinal}"
        )
        try:
            root = camera.validate_capture_evidence(path)
        except camera.CameraCaptureEvidenceError as exc:
            raise RecipePositionPermutationEvidenceBundleError(str(exc)) from exc
        expected = once.base.runner.ACTIONS[ordinal - 1]
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
        integrity = _mapping(
            root.get("integrity"), label=f"capture sidecar ordinal {ordinal}.integrity"
        )
        if (
            root.get("capture_binding") != camera.BINDING_LIVE
            or root.get("campaign_id") != pack.CAMPAIGN_ID
            or root.get("contract_id") != once.base.runner.CONTRACT_ID
            or root.get("firmware_sha256") != once.FIRMWARE_SHA256
            or root.get("boot_nonce") != boot_nonce
            or root.get("ordinal") != ordinal
            or root.get("action_id") != expected["action_id"]
            or root.get("descriptor_id") != expected["descriptor_id"]
            or action_record.get("file_sha256")
            != action_results[ordinal - 1]["file_sha256"]
            or coverage.get("scope") != camera.COVERAGE_FULL
            or coverage.get("full_panel_visible") is not True
            or coverage.get("full_panel_uncropped") is not True
        ):
            raise RecipePositionPermutationEvidenceBundleError(
                f"capture sidecar ordinal {ordinal} action/full-panel binding differs"
            )
        if (
            ordinal in expected_photos
            and photo.get("sha256") != expected_photos[ordinal]
        ):
            raise RecipePositionPermutationEvidenceBundleError(
                f"capture sidecar ordinal {ordinal} analysis photo binding differs"
            )
        signature = _camera_signature_from_capture(
            root, label=f"capture sidecar ordinal {ordinal}"
        )
        if common_signature is None:
            common_signature = signature
        elif signature != common_signature:
            raise RecipePositionPermutationEvidenceBundleError(
                f"capture sidecar ordinal {ordinal} camera or mount signature differs"
            )
        captured_at = _aware_datetime(
            root.get("captured_at"),
            label=f"capture sidecar ordinal {ordinal}.captured_at",
        )
        if captured_at <= action_times[ordinal - 1]:
            raise RecipePositionPermutationEvidenceBundleError(
                f"capture sidecar ordinal {ordinal} is not after its action result"
            )
        if times and captured_at <= times[-1]:
            raise RecipePositionPermutationEvidenceBundleError(
                f"capture sidecar ordinal {ordinal} is not later than its predecessor"
            )
        times.append(captured_at)
        bindings.append(
            {
                "ordinal": ordinal,
                "path": str(path),
                "sidecar_file_sha256": _sha256_bytes(sidecar_payload),
                "canonical_integrity_sha256": _sha(
                    integrity.get("sha256"),
                    label=f"capture sidecar ordinal {ordinal} canonical SHA",
                ),
                "capture_id": root.get("capture_id"),
                "captured_at": root["captured_at"],
                "action_id": expected["action_id"],
                "descriptor_id": expected["descriptor_id"],
                "action_result_sha256": action_record["file_sha256"],
                "photo_sha256": _sha(
                    photo.get("sha256"),
                    label=f"capture sidecar ordinal {ordinal} photo SHA",
                ),
                "capture_binding": camera.BINDING_LIVE,
                "coverage_scope": camera.COVERAGE_FULL,
            }
        )
    assert common_signature is not None
    return bindings, common_signature, times


def _validate_noise_report(path: Path) -> tuple[dict[str, Any], float]:
    try:
        binding, p95 = batch1_bundle._validate_noise_report(path)
    except batch1_bundle.SameR20ParityEvidenceBundleError as exc:
        raise RecipePositionPermutationEvidenceBundleError(str(exc)) from exc
    return binding, p95


def _classification_state(recipe_state: str) -> str:
    return {
        "BOTH_CONTROLLERS_RECIPE_LINKED_CANDIDATE": (
            "RECIPE_LINKED_EXPLORATORY_CANDIDATE"
        ),
        "ONE_CONTROLLER_RECIPE_LINKED_CANDIDATE": (
            "CONTROLLER_INCONSISTENT_EXPLORATORY_RESULT"
        ),
        "NO_RECIPE_LINKED_CANDIDATE": "NO_RECIPE_LINKED_EXPLORATORY_EFFECT",
    }[recipe_state]


def build_bundle(
    action_paths: Sequence[Path],
    capture_sidecar_paths: Sequence[Path],
    repeat_noise_report_path: Path,
    p0_g_minus_1_anchor_path: Path,
    p1_grid_analysis_path: Path,
    recipe_comparison_path: Path,
    terminal_white_gate_path: Path,
) -> dict[str, Any]:
    """Validate Batch-2 evidence and return one deterministic sealed bundle."""

    if len(action_paths) != 4:
        raise RecipePositionPermutationEvidenceBundleError(
            "exactly four action results are required"
        )
    action_bindings: list[dict[str, Any]] = []
    action_times: list[datetime] = []
    campaign_boot_nonce: str | None = None
    for ordinal, path in enumerate(action_paths, 1):
        binding, created_at, boot_nonce = _validate_action(Path(path), ordinal)
        if campaign_boot_nonce is None:
            campaign_boot_nonce = boot_nonce
        elif boot_nonce != campaign_boot_nonce:
            raise RecipePositionPermutationEvidenceBundleError(
                f"action ordinal {ordinal} boot continuity differs"
            )
        if action_times and created_at <= action_times[-1]:
            raise RecipePositionPermutationEvidenceBundleError(
                f"action ordinal {ordinal} time is not strictly increasing"
            )
        action_bindings.append(binding)
        action_times.append(created_at)
    assert campaign_boot_nonce is not None

    noise_binding, repeat_noise = _validate_noise_report(repeat_noise_report_path)
    p0_binding, p0_time, p0_camera_signature = _validate_g1_anchor(
        p0_g_minus_1_anchor_path
    )
    p1_binding, p1_photo_sha = _validate_p1_grid(p1_grid_analysis_path)
    white_payload, white_root, _ = _load_sealed(
        terminal_white_gate_path, label="ordinal-4 white gate prebinding"
    )
    del white_payload
    white_inputs = _mapping(
        white_root.get("inputs"), label="ordinal-4 white gate.inputs"
    )
    white_candidate = _mapping(
        white_inputs.get("candidate"), label="ordinal-4 white gate.candidate"
    )
    white_photo_sha = _sha(
        white_candidate.get("sha256"), label="ordinal-4 white candidate photo SHA"
    )
    capture_bindings, live_camera_signature, capture_times = _validate_capture_sidecars(
        capture_sidecar_paths,
        action_results=action_bindings,
        action_times=action_times,
        boot_nonce=campaign_boot_nonce,
        p1_photo_sha256=p1_photo_sha,
        white_photo_sha256=white_photo_sha,
    )
    if p0_time >= capture_times[0]:
        raise RecipePositionPermutationEvidenceBundleError(
            "G-1 P0 anchor must predate the first Batch-2 live capture"
        )
    for index in range(1, 4):
        if capture_times[index - 1] >= action_times[index]:
            raise RecipePositionPermutationEvidenceBundleError(
                "Batch-2 action/capture timeline is not strictly interleaved"
            )
    if (
        p1_binding["source_photo_width"] != live_camera_signature["photo_width"]
        or p1_binding["source_photo_height"] != live_camera_signature["photo_height"]
    ):
        raise RecipePositionPermutationEvidenceBundleError(
            "ordinal-3 P1 analysis dimensions differ from its capture"
        )
    if p0_camera_signature != live_camera_signature:
        raise RecipePositionPermutationEvidenceBundleError(
            "G-1 anchor and Batch-2 captures differ in camera/mount/manual readback"
        )
    comparable_live = {
        key: live_camera_signature[key]
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
    if noise_binding["camera_signature"] != comparable_live:
        raise RecipePositionPermutationEvidenceBundleError(
            "repeat-noise baseline and Batch-2 camera/mount lock differ"
        )

    comparison_binding = _validate_recipe_comparison(
        recipe_comparison_path,
        p0_file_sha256=p0_binding["grid_analysis"]["file_sha256"],
        p0_integrity_sha256=p0_binding["grid_analysis"]["canonical_integrity_sha256"],
        p1_file_sha256=p1_binding["file_sha256"],
        p1_integrity_sha256=p1_binding["canonical_integrity_sha256"],
    )
    if capture_bindings[2]["photo_sha256"] != p1_binding["source_photo_sha256"]:
        raise RecipePositionPermutationEvidenceBundleError(
            "ordinal-3 capture and P1 analysis photo differ"
        )
    terminal_white = _validate_terminal_white_gate(
        terminal_white_gate_path,
        expected_photo_sha256=capture_bindings[3]["photo_sha256"],
        expected_geometry_sha256=noise_binding["reference_geometry_sha256"],
        repeat_noise_p95_de76=repeat_noise,
    )

    terminal_evidence = {
        "ordinal": 4,
        "action_result_file_sha256": action_bindings[3]["file_sha256"],
        "action_result_canonical_integrity_sha256": action_bindings[3][
            "canonical_integrity_sha256"
        ],
        "capture_sidecar_file_sha256": capture_bindings[3]["sidecar_file_sha256"],
        "capture_canonical_integrity_sha256": capture_bindings[3][
            "canonical_integrity_sha256"
        ],
        "capture_id": capture_bindings[3]["capture_id"],
        "captured_at": capture_bindings[3]["captured_at"],
        "photo_sha256": capture_bindings[3]["photo_sha256"],
        "white_gate_file_sha256": terminal_white["file_sha256"],
        "white_gate_canonical_integrity_sha256": terminal_white[
            "canonical_integrity_sha256"
        ],
        "white_gate_analysis_id": terminal_white["analysis_id"],
        "reference_geometry_sha256": terminal_white["reference_geometry_sha256"],
        "repeat_noise_p95_de76": repeat_noise,
        "patch_count": 60,
        "campaign_boot_nonce": campaign_boot_nonce,
    }
    prerequisite_id = _sha256_bytes(_canonical_json(terminal_evidence))
    terminal_white_prerequisite = {
        "prerequisite_id": prerequisite_id,
        "eligible": True,
        **terminal_evidence,
        "classification_state": terminal_white["classification_state"],
        "terminal_is_latest_bound_batch2_capture": True,
        "external_refresh_after_terminal_capture_not_proven": True,
        "batch3_binding_contract": {
            "bind_bundle_kind": KIND,
            "bind_bundle_schema_version": SCHEMA_VERSION,
            "bind_bundle_id": "bundle_id",
            "bind_bundle_file_sha256": "whole bundle file bytes",
            "bind_bundle_canonical_integrity_sha256": "integrity.sha256",
            "bind_prerequisite_id": "terminal_white_prerequisite.prerequisite_id",
            "require_eligible_true": True,
            "deep_verify_terminal_subobject": True,
        },
    }

    recipe_state = comparison_binding["classification_state"]
    input_hashes = {
        "actions": [item["file_sha256"] for item in action_bindings],
        "captures": [item["sidecar_file_sha256"] for item in capture_bindings],
        "repeat_noise": noise_binding["file_sha256"],
        "g1_anchor": p0_binding["file_sha256"],
        "p1_grid": p1_binding["file_sha256"],
        "comparison": comparison_binding["file_sha256"],
        "terminal_white_gate": terminal_white["file_sha256"],
    }
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "bundle_id": _sha256_bytes(
            _canonical_json({"kind": KIND, "inputs": input_hashes})
        ),
        "campaign_identity": {
            "campaign_id": pack.CAMPAIGN_ID,
            "test_id": pack.TEST_ID,
            "layout_id": P1_LAYOUT_ID,
            "contract_id": once.base.runner.CONTRACT_ID,
            "firmware_sha256": once.FIRMWARE_SHA256,
            "firmware_bytes": once.FIRMWARE_BYTES,
            "campaign_boot_nonce": campaign_boot_nonce,
            "action_ids": list(once.base.runner.ACTION_IDS),
            "action_count": 4,
            "visible_refresh_count": 4,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        },
        "action_results": action_bindings,
        "captures": capture_bindings,
        "p0_g_minus_1_anchor": p0_binding,
        "p1_ordinal3_grid_analysis": p1_binding,
        "recipe_comparison": comparison_binding,
        "terminal_white_prerequisite": terminal_white_prerequisite,
        "shared_camera_lock": {
            **live_camera_signature,
            "manual_controls_required": dict(REQUIRED_MANUAL_CAMERA_SETTINGS),
            "g1_and_all_four_live_captures_same_signature": True,
            "all_effective_before_after_readbacks_equal": True,
            "all_four_live_captures_same_boot": True,
            "strictly_increasing_action_and_capture_timeline": True,
            "g1_captured_at": p0_binding["capture"]["captured_at"],
            "live_capture_times": [item["captured_at"] for item in capture_bindings],
        },
        "shared_analysis_bindings": {
            "repeat_noise_baseline": noise_binding,
            "reference_geometry_sha256": noise_binding["reference_geometry_sha256"],
            "repeat_noise_p95_de76": repeat_noise,
            "p0_grid_from_g1_anchor_file_sha256": p0_binding["grid_analysis"][
                "file_sha256"
            ],
            "p0_grid_from_g1_anchor_canonical_integrity_sha256": p0_binding[
                "grid_analysis"
            ]["canonical_integrity_sha256"],
            "p1_grid_file_sha256": p1_binding["file_sha256"],
            "p1_grid_canonical_integrity_sha256": p1_binding[
                "canonical_integrity_sha256"
            ],
            "comparison_binds_exact_g1_p0_and_ordinal3_p1": True,
            "terminal_white_gate_binds_ordinal4_photo": True,
            "terminal_white_gate_binds_repeat_noise_geometry": True,
        },
        "classification": {
            "state": _classification_state(recipe_state),
            "recipe_comparison_state": recipe_state,
            "recipe_linked_controller_count": comparison_binding[
                "recipe_linked_controller_count"
            ],
            "recipe_linked_exploratory_only": True,
            "qualified_new_colour": False,
            "qualified_brightness_level": False,
            "absolute_colour_proven": False,
        },
        "evidence_boundaries": {
            "g1_is_zero_refresh_retrospective_geometry_and_p0_anchor_only": True,
            "g1_is_not_live_action_evidence": True,
            "camera_relative_only": True,
            "recipe_linkage_is_exploratory": True,
            "one_permutation_cannot_qualify_a_new_colour": True,
            "absolute_colour_or_new_colour_not_proven": True,
            "compiled_payload_identity_not_bus_capture": True,
            "all_four_batch2_captures_live_synchronized_and_full_panel": True,
            "external_refresh_after_terminal_capture_not_proven": True,
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
        raise RecipePositionPermutationEvidenceBundleError(
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
    parser.add_argument("--p0-g-minus-1-anchor", type=Path, required=True)
    parser.add_argument("--p1-grid-analysis", type=Path, required=True)
    parser.add_argument("--recipe-comparison", type=Path, required=True)
    parser.add_argument("--terminal-white-gate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = build_bundle(
            args.action_output,
            args.capture_sidecar,
            args.repeat_noise_report,
            args.p0_g_minus_1_anchor,
            args.p1_grid_analysis,
            args.recipe_comparison,
            args.terminal_white_gate,
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
    except RecipePositionPermutationEvidenceBundleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
