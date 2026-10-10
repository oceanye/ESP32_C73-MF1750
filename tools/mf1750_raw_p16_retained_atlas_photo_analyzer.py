#!/usr/bin/env python3
"""Analyze one formally captured retained RAW-P16 endpoint atlas.

The physical layout is fixed to four rows by two columns *per controller*.
Codes are row-major within each controller: ``code = row * 2 + column``.
This module deliberately has no compatibility path for the historical two-row
by four-column same-R20 analyzer.

The analysis is camera-relative.  RGB, derived sRGB/D65 Lab, and Delta-E values
are useful for comparing cells inside this one locked capture only.  They do
not qualify an absolute colour, a stable colour, or a newly usable panel state.
Importing or running the analyzer performs no camera, relay, serial, network,
firmware, or display operation.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.color_pipeline.color import (  # noqa: E402
    delta_e_ciede2000,
    srgb8_to_lab,
)
from tools import mf1750_camera_capture_evidence as camera  # noqa: E402
from tools import mf1750_raw_p16_endpoint_gallery_v1_pack as pack  # noqa: E402


SCHEMA_VERSION = 1
KIND = "mf1750-raw-p16-retained-atlas-camera-relative-analysis"
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
TARGET_CAMERA_ID = camera.TARGET_CAMERA_FRIENDLY_NAME
TARGET_USB_TOKEN = camera.TARGET_CAMERA_USB_TOKEN
EXCLUDED_USB_TOKEN = camera.EXCLUDED_BINOCULAR_USB_TOKEN
EXPECTED_CAPTURE_SCHEMA = camera.SCHEMA_VERSION
EXPECTED_CAPTURE_BINDING = camera.BINDING_LOCKED_RETAINED
EXPECTED_CAMERA_PROFILE: dict[str, Any] = {
    "fourcc": "MJPG",
    "frame_width": 4000,
    "frame_height": 3000,
    "fps": 15.0,
    "autofocus": 0.0,
    "focus": 79.0,
    "auto_exposure": 0.25,
    "exposure": -6.0,
    "auto_white_balance": 0.0,
    "white_balance_temperature": 4600.0,
}
ACCEPTED_DSHOW_MANUAL_READBACK = {
    "autofocus": (0.0, 2.0),
    "auto_exposure": (-1.0, 0.25),
    "auto_white_balance": (0.0,),
}
CONTROLLER_COUNT = 2
CONTROLLER_WIDTH = 512
LOGICAL_WIDTH = 1024
LOGICAL_HEIGHT = 600
GRID_ROWS = 4
GRID_COLUMNS_PER_CONTROLLER = 2
CELL_INNER_FRACTION = 0.60
AUTO_MIN_SUPPORT = 14
AUTO_ALLOWED_SUPPORT_COUNTS = frozenset({14, 16})
MAX_REPROJECTION_RMSE_PX = 5.0
MAX_REPROJECTION_P95_PX = 8.0
MIN_PROJECTED_CELL_SIDE_PX = 80.0
PAIR_SIMILAR_DE00 = 3.0
PAIR_OBVIOUS_DE00 = 5.0
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RawP16PhotoAnalysisError(RuntimeError):
    """A RAW-P16 evidence, camera lock, geometry, or output gate failed."""


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
    except (TypeError, ValueError) as error:
        raise RawP16PhotoAnalysisError(
            f"record contains a non-canonical JSON value: {error}"
        ) from error


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
            raise RawP16PhotoAnalysisError(
                f"{label} must be a regular non-symlink file: {path}"
            )
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise RawP16PhotoAnalysisError(f"cannot read {label}: {error}") from error
    before_id = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_id = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_id != after_id or len(payload) != after.st_size:
        raise RawP16PhotoAnalysisError(f"{label} changed while it was read")
    return payload


def _load_json(path: Path, *, label: str) -> tuple[bytes, Mapping[str, Any]]:
    payload = _read_stable_regular(path, label=label)
    try:
        root = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise RawP16PhotoAnalysisError(
            f"{label} is not strict UTF-8 JSON: {error}"
        ) from error
    if not isinstance(root, Mapping):
        raise RawP16PhotoAnalysisError(f"{label} root must be an object")
    return payload, root


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RawP16PhotoAnalysisError(f"{label} must be an object")
    return value


def _number(value: Any, *, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise RawP16PhotoAnalysisError(f"{label} must be a finite number")
    return float(value)


def _sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise RawP16PhotoAnalysisError(f"{label} must be lowercase SHA-256")
    return value


def _import_cv() -> tuple[Any, Any]:
    try:
        import cv2
        import numpy as np
    except ImportError as error:
        raise RawP16PhotoAnalysisError(
            "OpenCV and NumPy are required for RAW-P16 photo analysis"
        ) from error
    return cv2, np


def _decode_rgb(photo_payload: bytes) -> Any:
    _cv2, np = _import_cv()
    try:
        with Image.open(BytesIO(photo_payload)) as opened:
            if opened.format != "JPEG":
                raise RawP16PhotoAnalysisError("formal photo must be JPEG")
            opened.load()
            rgb = opened.convert("RGB")
            if rgb.size != (
                EXPECTED_CAMERA_PROFILE["frame_width"],
                EXPECTED_CAMERA_PROFILE["frame_height"],
            ):
                raise RawP16PhotoAnalysisError(
                    "formal photo dimensions differ from locked 4000x3000 profile"
                )
            return np.asarray(rgb, dtype=np.uint8).copy()
    except RawP16PhotoAnalysisError:
        raise
    except (OSError, ValueError) as error:
        raise RawP16PhotoAnalysisError(f"cannot decode formal JPEG: {error}") from error


def _same_number(observed: Any, expected: float, *, label: str) -> None:
    value = _number(observed, label=label)
    tolerance = 0.001 if label.endswith("fps") else 0.0
    if not math.isclose(value, expected, rel_tol=0.0, abs_tol=tolerance):
        raise RawP16PhotoAnalysisError(
            f"{label} differs from locked value {expected:g}"
        )


def _validate_fixed_capture(
    capture_root: Mapping[str, Any],
    *,
    expected_coverage_scope: str = camera.COVERAGE_FULL,
) -> dict[str, Any]:
    if expected_coverage_scope not in {
        camera.COVERAGE_FULL,
        camera.COVERAGE_PARTIAL,
    }:
        raise RawP16PhotoAnalysisError("expected capture coverage scope is invalid")
    if (
        capture_root.get("schema_version") != EXPECTED_CAPTURE_SCHEMA
        or capture_root.get("kind") != camera.KIND
    ):
        raise RawP16PhotoAnalysisError(
            "capture must be current schema-v2 formal 48MP evidence"
        )
    if capture_root.get("capture_binding") != EXPECTED_CAPTURE_BINDING:
        raise RawP16PhotoAnalysisError(
            "capture must be locked-retained evidence for the displayed atlas"
        )
    coverage = _mapping(capture_root.get("coverage"), label="capture.coverage")
    expected_full = expected_coverage_scope == camera.COVERAGE_FULL
    if (
        coverage.get("scope") != expected_coverage_scope
        or coverage.get("full_panel_visible") is not expected_full
        or coverage.get("full_panel_uncropped") is not expected_full
    ):
        if expected_full:
            raise RawP16PhotoAnalysisError(
                "capture must declare the complete, visible, uncropped panel"
            )
        raise RawP16PhotoAnalysisError(
            "capture must truthfully declare partial-panel coverage"
        )
    mount_id = coverage.get("mount_id")
    if not isinstance(mount_id, str) or not mount_id:
        raise RawP16PhotoAnalysisError("capture mount_id is missing")

    record = _mapping(capture_root.get("camera"), label="capture.camera")
    if record.get("camera_id") != TARGET_CAMERA_ID:
        raise RawP16PhotoAnalysisError(
            "capture is not the MF1750 48MP VID_32E4:PID_4801 camera"
        )
    instance = record.get("instance_id")
    if not isinstance(instance, str):
        raise RawP16PhotoAnalysisError("capture camera instance is missing")
    folded_instance = instance.casefold()
    if TARGET_USB_TOKEN not in folded_instance or EXCLUDED_USB_TOKEN in folded_instance:
        raise RawP16PhotoAnalysisError(
            "capture camera instance is not the allowed 48MP USB device"
        )
    if str(record.get("backend", "")).casefold() != "dshow":
        raise RawP16PhotoAnalysisError("capture backend must be DirectShow")

    requested = _mapping(
        record.get("requested_settings"), label="camera.requested_settings"
    )
    for field, expected in EXPECTED_CAMERA_PROFILE.items():
        observed = requested.get(field)
        if isinstance(expected, str):
            if observed != expected:
                raise RawP16PhotoAnalysisError(
                    f"requested {field} differs from locked value {expected}"
                )
        else:
            _same_number(observed, float(expected), label=f"requested.{field}")

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
        raise RawP16PhotoAnalysisError(
            "effective camera settings changed around the formal frame"
        )
    for field in (
        "fourcc",
        "frame_width",
        "frame_height",
        "focus",
        "exposure",
        "white_balance_temperature",
    ):
        expected = EXPECTED_CAMERA_PROFILE[field]
        observed = before.get(field)
        if isinstance(expected, str):
            if observed != expected:
                raise RawP16PhotoAnalysisError(f"effective {field} differs")
        else:
            _same_number(observed, float(expected), label=f"effective.{field}")
    _same_number(before.get("fps"), 15.000015000015, label="effective.fps")
    for field, accepted in ACCEPTED_DSHOW_MANUAL_READBACK.items():
        observed = _number(before.get(field), label=f"effective.{field}")
        if observed not in accepted:
            raise RawP16PhotoAnalysisError(
                f"effective {field} is not an accepted DirectShow manual encoding"
            )
    set_results = _mapping(record.get("set_results"), label="camera.set_results")
    required_writes = {field for field, value in requested.items() if value is not None}
    if not required_writes.issubset(set_results) or any(
        set_results.get(field) is not True for field in required_writes
    ):
        raise RawP16PhotoAnalysisError("one or more locked camera writes failed")
    if record.get("read_failures") != 0:
        raise RawP16PhotoAnalysisError("formal capture has camera read failures")
    warmup = record.get("warmup_frames_requested")
    if (
        type(warmup) is not int
        or warmup < 5
        or record.get("warmup_frames_completed") != warmup
    ):
        raise RawP16PhotoAnalysisError(
            "formal capture requires at least five completed warmup frames"
        )
    return {
        "camera_id": TARGET_CAMERA_ID,
        "usb_vid": "32E4",
        "usb_pid": "4801",
        "excluded_camera_vid_pid": "1BCF:0B15",
        "instance_id": instance,
        "backend": "DSHOW",
        "mount_id": mount_id,
        "requested_settings": dict(requested),
        "effective_settings": before,
        "effective_readback_equal": True,
        "write_results_all_true": True,
        "fixed_exposure_boundary": -6.0,
    }


def _validate_action(action_root: Mapping[str, Any]) -> dict[str, Any]:
    expected_report = pack.build_report(verify_artifacts=False)
    expected_action = expected_report["actions"][0]
    action = _mapping(action_root.get("action"), label="action result.action")
    terminal = _mapping(
        action_root.get("terminal_report"), label="action result.terminal_report"
    )
    expected = {
        "action_id": expected_action["action_id"],
        "descriptor_id": expected_action["descriptor_id"],
        "ordinal": 1,
        "role": "RAW_P16_ACTIVE_ENDPOINT_GALLERY",
        "branch": expected_action["branch"],
        "profile_id": expected_action["profile_id"],
        "global_tuple_id": expected_action["global_tuple_id"],
        "frame_sha256": expected_action["frame"]["sha256"],
    }
    for field, value in expected.items():
        if action.get(field) != value:
            raise RawP16PhotoAnalysisError(f"RAW-P16 action {field} differs")
    if (
        action_root.get("kind") != "mf1750-ec5-raw-p16-endpoint-gallery-v1-result"
        or action_root.get("outcome") != "complete_pass"
        or action_root.get("visible_refreshes") != 1
        or action_root.get("firmware_sha256") != pack.FIRMWARE_BIN_SHA256
    ):
        raise RawP16PhotoAnalysisError("RAW-P16 action result identity differs")
    terminal_expected = {
        "terminal_state": "COMPLETE",
        "result": True,
        "valid": True,
        "campaign_id": pack.CAMPAIGN_ID,
        "test_id": pack.TEST_ID,
        "contract_id": expected_report["contract_id"],
        "build_tag": pack.BUILD_TAG,
        "action_id": expected_action["action_id"],
        "descriptor_id": expected_action["descriptor_id"],
        "ordinal": 1,
        "role": "RAW_P16_ACTIVE_ENDPOINT_GALLERY",
        "driver_called": True,
        "driver_call_count_for_action": 1,
    }
    for field, value in terminal_expected.items():
        if terminal.get(field) != value:
            raise RawP16PhotoAnalysisError(f"RAW-P16 terminal {field} differs")
    driver = _mapping(terminal.get("driver"), label="terminal.driver")
    if (
        driver.get("valid") is not True
        or driver.get("sequence_ok") is not True
        or driver.get("wait_timeout") is not False
        or driver.get("failure_stage") != "none"
    ):
        raise RawP16PhotoAnalysisError("RAW-P16 terminal driver evidence differs")
    geometry = expected_report["contract"]["geometry"]
    if (
        geometry["grid_rows"] != 4
        or geometry["grid_columns_per_controller"] != 2
        or geometry["row_codes"] != [[0, 1], [2, 3], [4, 5], [6, 7]]
    ):
        raise RawP16PhotoAnalysisError("offline RAW-P16 4x2 geometry differs")
    return {
        "campaign_id": pack.CAMPAIGN_ID,
        "test_id": pack.TEST_ID,
        "contract_id": expected_report["contract_id"],
        "action_id": expected_action["action_id"],
        "descriptor_id": expected_action["descriptor_id"],
        "frame_sha256": expected_action["frame"]["sha256"],
        "layout_id": pack.VARIANT_KEY,
    }


def _logical_cell(controller: int, row: int, column: int) -> dict[str, Any]:
    if controller not in (0, 1) or row not in range(4) or column not in range(2):
        raise RawP16PhotoAnalysisError("cell is outside exact 2-controller 4x2 layout")
    code = row * 2 + column
    x, y, width, height = pack.cell_bounds(row, column)
    x += controller * CONTROLLER_WIDTH
    return {
        "cell_id": f"C{controller}-CODE{code}",
        "endpoint_id": f"RAW-P16/MIXED-R20/CS{controller + 1}/C{code}",
        "controller": controller,
        "row": row,
        "column": column,
        "code": code,
        "logical_bounds": [x, y, width, height],
        "logical_center": [x + width / 2.0, y + height / 2.0],
    }


def _all_logical_cells() -> list[dict[str, Any]]:
    return [
        _logical_cell(controller, row, column)
        for controller in range(CONTROLLER_COUNT)
        for row in range(GRID_ROWS)
        for column in range(GRID_COLUMNS_PER_CONTROLLER)
    ]


def _order_quad(points: Any) -> Any:
    _cv2, np = _import_cv()
    points = np.asarray(points, dtype=np.float64).reshape(4, 2)
    ordered = np.empty((4, 2), dtype=np.float64)
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).reshape(-1)
    ordered[0] = points[int(np.argmin(sums))]
    ordered[2] = points[int(np.argmax(sums))]
    ordered[1] = points[int(np.argmin(differences))]
    ordered[3] = points[int(np.argmax(differences))]
    if len({tuple(item) for item in ordered.tolist()}) != 4:
        raise RawP16PhotoAnalysisError("quadrilateral corner order is degenerate")
    return ordered


def _detect_rectangles(rgb: Any) -> list[dict[str, Any]]:
    cv2, np = _import_cv()
    height, width = rgb.shape[:2]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    image_area = float(width * height)
    candidates: list[dict[str, Any]] = []
    # Two fixed edge thresholds are intentionally combined.  A pale endpoint in
    # the current daylight repeat is below the primary threshold but has the
    # same four-corner lattice support at the conservative secondary threshold.
    # The later exact 14/16 coverage and all-inlier homography gates prevent the
    # secondary pass from silently admitting an unrelated rectangle.
    for canny_low, canny_high in ((20, 70), (15, 55)):
        edges = cv2.Canny(gray, canny_low, canny_high)
        edges = cv2.morphologyEx(
            edges,
            cv2.MORPH_CLOSE,
            np.ones((5, 5), dtype=np.uint8),
            iterations=1,
        )
        contours, _hierarchy = cv2.findContours(
            edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
        )
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if not image_area * 0.0025 <= area <= image_area * 0.015:
                continue
            perimeter = float(cv2.arcLength(contour, True))
            polygon = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
            if len(polygon) != 4 or not cv2.isContourConvex(polygon):
                continue
            _x, _y, box_width, box_height = cv2.boundingRect(contour)
            if box_height < 1 or not 1.2 <= box_width / box_height <= 4.0:
                continue
            corners = _order_quad(polygon.reshape(4, 2))
            center = corners.mean(axis=0)
            candidates.append(
                {
                    "area_px2": area,
                    "center": center,
                    "corners": corners,
                    "canny_threshold": [canny_low, canny_high],
                }
            )
    deduplicated: list[dict[str, Any]] = []
    centre_threshold = min(width, height) * 0.008
    for candidate in sorted(
        candidates, key=lambda item: item["area_px2"], reverse=True
    ):
        if all(
            float(np.linalg.norm(candidate["center"] - kept["center"]))
            > centre_threshold
            for kept in deduplicated
        ):
            deduplicated.append(candidate)
    if len(deduplicated) not in AUTO_ALLOWED_SUPPORT_COUNTS:
        raise RawP16PhotoAnalysisError(
            "automatic geometry requires exactly 14 or 16 unique cell rectangles; "
            f"detected {len(deduplicated)}"
        )
    return deduplicated


def _split_four_rows(candidates: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    ordered = sorted(candidates, key=lambda item: float(item["center"][1]))
    gaps = [
        float(ordered[index + 1]["center"][1] - ordered[index]["center"][1])
        for index in range(len(ordered) - 1)
    ]
    split_indices = sorted(
        (index + 1 for index in sorted(range(len(gaps)), key=gaps.__getitem__)[-3:])
    )
    rows: list[list[dict[str, Any]]] = []
    start = 0
    for end in (*split_indices, len(ordered)):
        rows.append(
            sorted(ordered[start:end], key=lambda item: float(item["center"][0]))
        )
        start = end
    counts = [len(row) for row in rows]
    if counts not in ([2, 4, 4, 4], [4, 4, 4, 4]):
        raise RawP16PhotoAnalysisError(
            f"detected cell row coverage {counts!r} is not RAW-P16 14/16 support"
        )
    return rows


def _reprojection_statistics(
    homography: Any, correspondences: list[dict[str, Any]]
) -> dict[str, Any]:
    cv2, np = _import_cv()
    source = np.asarray(
        [[item["logical_center"] for item in correspondences]], dtype=np.float32
    )
    projected = cv2.perspectiveTransform(source, homography)[0]
    observed = np.asarray(
        [item["observed_center"] for item in correspondences], dtype=np.float64
    )
    errors = np.linalg.norm(projected.astype(np.float64) - observed, axis=1)
    rmse = float(math.sqrt(float(np.mean(errors**2))))
    p95 = float(np.percentile(errors, 95))
    return {
        "rmse_px": rmse,
        "p95_px": p95,
        "maximum_px": float(np.max(errors)),
        "errors_px": errors,
    }


def _fit_auto_homography(
    candidates: list[dict[str, Any]],
) -> tuple[Any, list[dict[str, Any]], dict[str, Any]]:
    cv2, np = _import_cv()
    rows = _split_four_rows(candidates)
    correspondences: list[dict[str, Any]] = []
    global_columns = (
        _logical_cell(0, 0, 0)["logical_center"][0],
        _logical_cell(0, 0, 1)["logical_center"][0],
        _logical_cell(1, 0, 0)["logical_center"][0],
        _logical_cell(1, 0, 1)["logical_center"][0],
    )
    for row_index in range(1, 4):
        for global_column, candidate in enumerate(rows[row_index]):
            correspondences.append(
                {
                    "row": row_index,
                    "global_column": global_column,
                    "logical_center": [
                        global_columns[global_column],
                        _logical_cell(0, row_index, 0)["logical_center"][1],
                    ],
                    "observed_center": candidate["center"].tolist(),
                    "detected_corners": candidate["corners"].tolist(),
                }
            )
    source = np.asarray(
        [item["logical_center"] for item in correspondences], dtype=np.float32
    )
    target = np.asarray(
        [item["observed_center"] for item in correspondences], dtype=np.float32
    )
    initial, initial_mask = cv2.findHomography(source, target, cv2.RANSAC, 4.0)
    if initial is None or initial_mask is None or int(initial_mask.sum()) != 12:
        raise RawP16PhotoAnalysisError(
            "lower three RAW-P16 rows do not define a complete homography"
        )
    top_logical = np.asarray(
        [
            [
                [
                    global_columns[column],
                    _logical_cell(0, 0, 0)["logical_center"][1],
                ]
                for column in range(4)
            ]
        ],
        dtype=np.float32,
    )
    top_predictions = cv2.perspectiveTransform(top_logical, initial)[0]
    used_columns: set[int] = set()
    match_limit = (
        min(
            float(np.linalg.norm(top_predictions[index + 1] - top_predictions[index]))
            for index in range(3)
        )
        * 0.20
    )
    for candidate in rows[0]:
        distances = np.linalg.norm(top_predictions - candidate["center"], axis=1)
        column = int(np.argmin(distances))
        if column in used_columns or float(distances[column]) > match_limit:
            raise RawP16PhotoAnalysisError(
                "top-row rectangles do not match unique RAW-P16 columns"
            )
        used_columns.add(column)
        correspondences.append(
            {
                "row": 0,
                "global_column": column,
                "logical_center": top_logical[0, column].tolist(),
                "observed_center": candidate["center"].tolist(),
                "detected_corners": candidate["corners"].tolist(),
            }
        )
    source = np.asarray(
        [item["logical_center"] for item in correspondences], dtype=np.float32
    )
    target = np.asarray(
        [item["observed_center"] for item in correspondences], dtype=np.float32
    )
    homography, mask = cv2.findHomography(source, target, cv2.RANSAC, 4.0)
    if homography is None or mask is None or int(mask.sum()) != len(correspondences):
        raise RawP16PhotoAnalysisError("RAW-P16 cell homography has outliers")
    statistics = _reprojection_statistics(homography, correspondences)
    if (
        statistics["rmse_px"] > MAX_REPROJECTION_RMSE_PX
        or statistics["p95_px"] > MAX_REPROJECTION_P95_PX
    ):
        raise RawP16PhotoAnalysisError(
            "RAW-P16 cell homography reprojection error exceeds the fixed gate"
        )
    return homography, correspondences, statistics


def _parse_panel_corners(value: str) -> Any:
    _cv2, np = _import_cv()
    try:
        pairs = [
            [float(component) for component in pair.split(",")]
            for pair in value.split(";")
        ]
    except ValueError as error:
        raise RawP16PhotoAnalysisError(
            "panel corners must be TLx,TLy;TRx,TRy;BRx,BRy;BLx,BLy"
        ) from error
    if len(pairs) != 4 or any(len(pair) != 2 for pair in pairs):
        raise RawP16PhotoAnalysisError(
            "panel corners must contain exactly four ordered x,y pairs"
        )
    corners = np.asarray(pairs, dtype=np.float64)
    if not np.all(np.isfinite(corners)):
        raise RawP16PhotoAnalysisError("panel corners must be finite")
    if not np.allclose(_order_quad(corners), corners, rtol=0.0, atol=1e-6):
        raise RawP16PhotoAnalysisError("panel corners must be ordered TL,TR,BR,BL")
    return corners


def _fit_explicit_homography(
    panel_corners: Any, candidates: list[dict[str, Any]]
) -> tuple[Any, list[dict[str, Any]], dict[str, Any]]:
    cv2, np = _import_cv()
    logical_panel = np.asarray(
        [
            [0.0, 0.0],
            [LOGICAL_WIDTH, 0.0],
            [LOGICAL_WIDTH, LOGICAL_HEIGHT],
            [0.0, LOGICAL_HEIGHT],
        ],
        dtype=np.float32,
    )
    seed = cv2.getPerspectiveTransform(logical_panel, panel_corners.astype(np.float32))
    cells = _all_logical_cells()
    logical_centres = np.asarray(
        [[[float(v) for v in cell["logical_center"]] for cell in cells]],
        dtype=np.float32,
    )
    predictions = cv2.perspectiveTransform(logical_centres, seed)[0]
    spacings = []
    for row in range(4):
        for controller in range(2):
            left_index = controller * 8 + row * 2
            spacings.append(
                float(
                    np.linalg.norm(
                        predictions[left_index + 1] - predictions[left_index]
                    )
                )
            )
    match_limit = min(spacings) * 0.25
    correspondences: list[dict[str, Any]] = []
    used: set[int] = set()
    for candidate in candidates:
        distances = np.linalg.norm(predictions - candidate["center"], axis=1)
        index = int(np.argmin(distances))
        if index in used or float(distances[index]) > match_limit:
            raise RawP16PhotoAnalysisError(
                "explicit panel corners do not match unique detected RAW-P16 cells"
            )
        used.add(index)
        cell = cells[index]
        correspondences.append(
            {
                "row": cell["row"],
                "global_column": cell["controller"] * 2 + cell["column"],
                "logical_center": list(cell["logical_center"]),
                "observed_center": candidate["center"].tolist(),
                "detected_corners": candidate["corners"].tolist(),
            }
        )
    if len(correspondences) < AUTO_MIN_SUPPORT:
        raise RawP16PhotoAnalysisError(
            "explicit geometry has insufficient cell support"
        )
    source = np.asarray(
        [item["logical_center"] for item in correspondences], dtype=np.float32
    )
    target = np.asarray(
        [item["observed_center"] for item in correspondences], dtype=np.float32
    )
    refined, mask = cv2.findHomography(source, target, cv2.RANSAC, 4.0)
    if refined is None or mask is None or int(mask.sum()) != len(correspondences):
        raise RawP16PhotoAnalysisError("explicit geometry refinement has outliers")
    statistics = _reprojection_statistics(refined, correspondences)
    if (
        statistics["rmse_px"] > MAX_REPROJECTION_RMSE_PX
        or statistics["p95_px"] > MAX_REPROJECTION_P95_PX
    ):
        raise RawP16PhotoAnalysisError(
            "explicit geometry refinement exceeds the reprojection gate"
        )
    return refined, correspondences, statistics


def _project(homography: Any, points: Sequence[Sequence[float]]) -> Any:
    cv2, np = _import_cv()
    source = np.asarray([[list(point) for point in points]], dtype=np.float32)
    return cv2.perspectiveTransform(source, homography)[0].astype(np.float64)


def _geometry_report(
    homography: Any,
    correspondences: list[dict[str, Any]],
    statistics: Mapping[str, Any],
    *,
    photo_width: int,
    photo_height: int,
    source: str,
    supplied_panel_corners: Any | None,
) -> dict[str, Any]:
    _cv2, np = _import_cv()
    projected_panel = _project(
        homography,
        (
            (0, 0),
            (LOGICAL_WIDTH, 0),
            (LOGICAL_WIDTH, LOGICAL_HEIGHT),
            (0, LOGICAL_HEIGHT),
        ),
    )
    if not np.all(
        (projected_panel[:, 0] >= 0)
        & (projected_panel[:, 0] < photo_width)
        & (projected_panel[:, 1] >= 0)
        & (projected_panel[:, 1] < photo_height)
    ):
        raise RawP16PhotoAnalysisError(
            "projected logical panel leaves the formal photo"
        )
    minimum_side = math.inf
    for cell in _all_logical_cells():
        x, y, width, height = cell["logical_bounds"]
        projected = _project(
            homography,
            ((x, y), (x + width, y), (x + width, y + height), (x, y + height)),
        )
        sides = [
            float(np.linalg.norm(projected[(index + 1) % 4] - projected[index]))
            for index in range(4)
        ]
        minimum_side = min(minimum_side, *sides)
    if minimum_side < MIN_PROJECTED_CELL_SIDE_PX:
        raise RawP16PhotoAnalysisError("projected RAW-P16 cells are too small")
    support = sorted(
        (
            {
                "row": int(item["row"]),
                "global_column": int(item["global_column"]),
                "logical_center": [round(float(v), 6) for v in item["logical_center"]],
                "observed_center": [
                    round(float(v), 6) for v in item["observed_center"]
                ],
                "reprojection_error_px": round(
                    float(statistics["errors_px"][index]), 6
                ),
            }
            for index, item in enumerate(correspondences)
        ),
        key=lambda item: (item["row"], item["global_column"]),
    )
    return {
        "source": source,
        "historical_g1_homography_reused": False,
        "historical_g1_nonreuse_reason": (
            "current camera mount/pose and exposure differ; geometry was fitted "
            "from this exact photo"
        ),
        "logical_coordinate_convention": "MF1750 full panel 1024x600",
        "homography_logical_to_current_photo": [
            [round(float(value), 12) for value in row] for row in homography.tolist()
        ],
        "supplied_panel_corners_tl_tr_br_bl": (
            None
            if supplied_panel_corners is None
            else [
                [round(float(value), 6) for value in row]
                for row in supplied_panel_corners.tolist()
            ]
        ),
        "projected_panel_corners_tl_tr_br_bl": [
            [round(float(value), 6) for value in row]
            for row in projected_panel.tolist()
        ],
        "detected_cell_support": len(correspondences),
        "minimum_required_cell_support": AUTO_MIN_SUPPORT,
        "support": support,
        "reprojection_rmse_px": round(float(statistics["rmse_px"]), 6),
        "reprojection_p95_px": round(float(statistics["p95_px"]), 6),
        "reprojection_maximum_px": round(float(statistics["maximum_px"]), 6),
        "maximum_allowed_rmse_px": MAX_REPROJECTION_RMSE_PX,
        "maximum_allowed_p95_px": MAX_REPROJECTION_P95_PX,
        "minimum_projected_cell_side_px": round(float(minimum_side), 6),
        "all_projected_panel_corners_inside_photo": True,
        "geometry_sufficient": True,
    }


def _sample_cell(rgb: Any, homography: Any, cell: Mapping[str, Any]) -> dict[str, Any]:
    cv2, np = _import_cv()
    x, y, width, height = cell["logical_bounds"]
    margin_x = width * (1.0 - CELL_INNER_FRACTION) / 2.0
    margin_y = height * (1.0 - CELL_INNER_FRACTION) / 2.0
    inner = (
        (x + margin_x, y + margin_y),
        (x + width - margin_x, y + margin_y),
        (x + width - margin_x, y + height - margin_y),
        (x + margin_x, y + height - margin_y),
    )
    projected = _project(homography, inner)
    height_px, width_px = rgb.shape[:2]
    if not np.all(
        (projected[:, 0] >= 0)
        & (projected[:, 0] < width_px)
        & (projected[:, 1] >= 0)
        & (projected[:, 1] < height_px)
    ):
        raise RawP16PhotoAnalysisError(f"{cell['cell_id']} inner ROI leaves photo")
    mask = np.zeros((height_px, width_px), dtype=np.uint8)
    cv2.fillConvexPoly(mask, np.rint(projected).astype(np.int32), 255)
    pixels = rgb[mask == 255]
    if len(pixels) < 1000:
        raise RawP16PhotoAnalysisError(f"{cell['cell_id']} has too few ROI pixels")
    median = np.median(pixels.astype(np.float64), axis=0)
    mad = np.median(np.abs(pixels.astype(np.float64) - median), axis=0)
    rgb8 = tuple(int(round(float(value))) for value in median)
    lab = srgb8_to_lab(rgb8)
    return {
        **dict(cell),
        "projected_inner_roi_corners": [
            [round(float(value), 6) for value in row] for row in projected.tolist()
        ],
        "inner_fraction": CELL_INNER_FRACTION,
        "sample_count": int(len(pixels)),
        "robust_rgb_median": [round(float(value), 6) for value in median.tolist()],
        "robust_rgb_mad": [round(float(value), 6) for value in mad.tolist()],
        "camera_relative_lab_d65_from_rgb_median": [
            round(float(value), 6) for value in lab
        ],
    }


def _pair_summary(
    cells: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_key = {(item["controller"], item["code"]): item for item in cells}
    pairs: list[dict[str, Any]] = []
    similar: list[int] = []
    borderline: list[int] = []
    obvious: list[int] = []
    for code in range(8):
        left = by_key[(0, code)]
        right = by_key[(1, code)]
        lab_left = left["camera_relative_lab_d65_from_rgb_median"]
        lab_right = right["camera_relative_lab_d65_from_rgb_median"]
        de00 = float(delta_e_ciede2000(lab_left, lab_right))
        de76 = math.dist(lab_left, lab_right)
        if de00 < PAIR_SIMILAR_DE00:
            category = "NO_OBVIOUS_DIFFERENCE_IN_THIS_CAPTURE"
            similar.append(code)
        elif de00 < PAIR_OBVIOUS_DE00:
            category = "BORDERLINE_CAMERA_RELATIVE_DIFFERENCE"
            borderline.append(code)
        else:
            category = "OBVIOUS_CAMERA_RELATIVE_DIFFERENCE_CANDIDATE"
            obvious.append(code)
        pairs.append(
            {
                "code": code,
                "left_cell_id": left["cell_id"],
                "right_cell_id": right["cell_id"],
                "delta_e00_camera_relative": round(de00, 6),
                "delta_e76_camera_relative": round(de76, 6),
                "delta_lstar_camera_relative": round(
                    float(lab_right[0] - lab_left[0]), 6
                ),
                "heuristic_category": category,
                "qualification_effect": "NONE",
            }
        )
    ordered = sorted(
        pairs, key=lambda item: item["delta_e00_camera_relative"], reverse=True
    )
    summary = {
        "heuristic_only": True,
        "similar_threshold_delta_e00_exclusive": PAIR_SIMILAR_DE00,
        "obvious_threshold_delta_e00_inclusive": PAIR_OBVIOUS_DE00,
        "codes_without_obvious_left_right_difference": similar,
        "borderline_left_right_codes": borderline,
        "obvious_left_right_difference_candidates": obvious,
        "largest_left_right_difference": ordered[0],
        "smallest_left_right_difference": ordered[-1],
        "controller_equivalence_proven": False,
        "reason": (
            "one retained, locked-camera frame can flag relative differences but "
            "cannot prove controller equivalence, repeatability, or stability"
        ),
    }
    return pairs, summary


def analyze(
    *,
    photo_path: Path,
    capture_sidecar_path: Path,
    action_result_path: Path,
    panel_corners: Any | None = None,
) -> dict[str, Any]:
    """Deep-validate and analyze one current formal retained-atlas photograph."""

    photo_path = Path(photo_path).resolve()
    capture_sidecar_path = Path(capture_sidecar_path).resolve()
    action_result_path = Path(action_result_path).resolve()
    try:
        capture_root = camera.validate_capture_evidence(capture_sidecar_path)
    except camera.CameraCaptureEvidenceError as error:
        raise RawP16PhotoAnalysisError(
            f"formal capture evidence rejected: {error}"
        ) from error
    camera_lock = _validate_fixed_capture(capture_root)
    action_payload, action_root = _load_json(action_result_path, label="action result")
    action_identity = _validate_action(action_root)

    sidecar_action = _mapping(
        capture_root.get("action_result"), label="capture.action_result"
    )
    sidecar_photo = _mapping(capture_root.get("photo"), label="capture.photo")
    resolved_action = (
        capture_sidecar_path.parent / str(sidecar_action.get("path"))
    ).resolve()
    resolved_photo = (
        capture_sidecar_path.parent / str(sidecar_photo.get("path"))
    ).resolve()
    if resolved_action != action_result_path or resolved_photo != photo_path:
        raise RawP16PhotoAnalysisError(
            "explicit photo/action paths differ from the formal capture bindings"
        )
    photo_payload = _read_stable_regular(photo_path, label="formal photo")
    if sidecar_photo.get("sha256") != _sha256_bytes(
        photo_payload
    ) or sidecar_action.get("file_sha256") != _sha256_bytes(action_payload):
        raise RawP16PhotoAnalysisError("formal photo/action SHA-256 binding differs")
    rgb = _decode_rgb(photo_payload)
    candidates = _detect_rectangles(rgb)
    supplied = None
    if panel_corners is None:
        homography, correspondences, statistics = _fit_auto_homography(candidates)
        geometry_source = "AUTO_CURRENT_PHOTO_14_OR_16_CELL_LATTICE"
    else:
        supplied = (
            _parse_panel_corners(panel_corners)
            if isinstance(panel_corners, str)
            else panel_corners
        )
        homography, correspondences, statistics = _fit_explicit_homography(
            supplied, candidates
        )
        geometry_source = "EXPLICIT_CURRENT_PANEL_CORNERS_REFINED_BY_CELL_LATTICE"
    geometry = _geometry_report(
        homography,
        correspondences,
        statistics,
        photo_width=rgb.shape[1],
        photo_height=rgb.shape[0],
        source=geometry_source,
        supplied_panel_corners=supplied,
    )
    cells = [_sample_cell(rgb, homography, cell) for cell in _all_logical_cells()]
    pairs, visible_summary = _pair_summary(cells)
    sidecar_payload = _read_stable_regular(
        capture_sidecar_path, label="capture sidecar"
    )
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source_evidence": {
            "photo": {
                "path": str(photo_path),
                "bytes": len(photo_payload),
                "sha256": _sha256_bytes(photo_payload),
                "width": rgb.shape[1],
                "height": rgb.shape[0],
            },
            "capture_sidecar": {
                "path": str(capture_sidecar_path),
                "bytes": len(sidecar_payload),
                "sha256": _sha256_bytes(sidecar_payload),
                "canonical_integrity_sha256": _sha256(
                    _mapping(
                        capture_root.get("integrity"), label="capture.integrity"
                    ).get("sha256"),
                    label="capture.integrity.sha256",
                ),
            },
            "action_result": {
                "path": str(action_result_path),
                "bytes": len(action_payload),
                "sha256": _sha256_bytes(action_payload),
                "canonical_integrity_sha256": _sha256(
                    _mapping(
                        action_root.get("integrity"), label="action.integrity"
                    ).get("sha256"),
                    label="action.integrity.sha256",
                ),
            },
        },
        "action_binding": action_identity,
        "camera_lock": camera_lock,
        "layout": {
            "logical_width": LOGICAL_WIDTH,
            "logical_height": LOGICAL_HEIGHT,
            "controller_count": CONTROLLER_COUNT,
            "controller_width": CONTROLLER_WIDTH,
            "rows_per_controller": GRID_ROWS,
            "columns_per_controller": GRID_COLUMNS_PER_CONTROLLER,
            "code_mapping": "row-major: code = row*2 + column",
            "row_codes": [[0, 1], [2, 3], [4, 5], [6, 7]],
            "historical_2x4_analyzer_used": False,
        },
        "geometry": geometry,
        "measurement_method": {
            "rgb_statistic": "per-channel median over projected inner 60% polygon",
            "spread_statistic": "per-channel median absolute deviation",
            "lab_derivation": "camera JPEG RGB interpreted as sRGB and converted to D65/2deg CIE Lab",
            "delta_e": "CIEDE2000 plus Delta-E76",
            "physical_colour_calibrated": False,
            "absolute_colour_measurement": False,
            "repeatability_measurement": False,
        },
        "cells": cells,
        "left_right_code_pairs": pairs,
        "visible_differentiation_summary": visible_summary,
        "classification": {
            "state": "CAMERA_RELATIVE_RETAINED_ENDPOINT_COMPARISON_ONLY",
            "camera_relative_candidates_only": True,
            "absolute_colour_proven": False,
            "stable_colour_proven": False,
            "repeatable_colour_proven": False,
            "qualified_new_colour": False,
            "qualified_colour_count": 0,
            "controller_equivalence_proven": False,
        },
        "hardware_io_performed_by_analyzer": False,
        "camera_access_performed_by_analyzer": False,
        "visible_refresh_authorized": False,
        "output_write_contract": "O_EXCL",
    }
    result["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": _sha256_bytes(_canonical_json(result)),
    }
    return result


def _write_exclusive(path: Path, report: Mapping[str, Any]) -> None:
    payload = (
        json.dumps(
            report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        ).encode("utf-8")
        + b"\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
    except FileExistsError as error:
        raise RawP16PhotoAnalysisError(
            f"refusing to overwrite output: {path}"
        ) from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _render_geometry_overlay(photo_payload: bytes, report: Mapping[str, Any]) -> bytes:
    cv2, np = _import_cv()
    rgb = _decode_rgb(photo_payload)
    canvas = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    geometry = _mapping(report.get("geometry"), label="report.geometry")
    homography = np.asarray(
        geometry.get("homography_logical_to_current_photo"), dtype=np.float64
    )
    panel = np.rint(
        _project(
            homography,
            (
                (0, 0),
                (LOGICAL_WIDTH, 0),
                (LOGICAL_WIDTH, LOGICAL_HEIGHT),
                (0, LOGICAL_HEIGHT),
            ),
        )
    ).astype(np.int32)
    cv2.polylines(canvas, [panel], True, (0, 255, 255), 8, cv2.LINE_AA)
    for cell in _all_logical_cells():
        x, y, width, height = cell["logical_bounds"]
        corners = np.rint(
            _project(
                homography,
                (
                    (x, y),
                    (x + width, y),
                    (x + width, y + height),
                    (x, y + height),
                ),
            )
        ).astype(np.int32)
        colour = (255, 255, 0) if cell["controller"] == 0 else (0, 165, 255)
        cv2.polylines(canvas, [corners], True, colour, 6, cv2.LINE_AA)
        center = np.rint(_project(homography, (cell["logical_center"],))[0]).astype(int)
        cv2.putText(
            canvas,
            f"C{cell['controller']}:{cell['code']}",
            (int(center[0]) - 45, int(center[1]) + 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            5,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            f"C{cell['controller']}:{cell['code']}",
            (int(center[0]) - 45, int(center[1]) + 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )
    for support in geometry.get("support", []):
        item = _mapping(support, label="geometry.support item")
        observed = item.get("observed_center")
        if not isinstance(observed, list) or len(observed) != 2:
            raise RawP16PhotoAnalysisError("geometry overlay support differs")
        cv2.circle(
            canvas,
            (int(round(float(observed[0]))), int(round(float(observed[1])))),
            14,
            (0, 255, 0),
            -1,
            cv2.LINE_AA,
        )
    encoded, buffer = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not encoded:
        raise RawP16PhotoAnalysisError("geometry overlay JPEG encoding failed")
    return bytes(buffer)


def _write_bytes_exclusive(path: Path, payload: bytes, *, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
    except FileExistsError as error:
        raise RawP16PhotoAnalysisError(
            f"refusing to overwrite {label}: {path}"
        ) from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--photo", type=Path, required=True)
    parser.add_argument("--capture-sidecar", type=Path, required=True)
    parser.add_argument("--action-result", type=Path, required=True)
    parser.add_argument(
        "--panel-corners",
        help="optional current-photo TLx,TLy;TRx,TRy;BRx,BRy;BLx,BLy seed",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--overlay-output",
        type=Path,
        help="geometry QA JPEG; defaults to <output>.geometry-overlay.jpg",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    overlay_output = args.overlay_output or Path(
        str(args.output) + ".geometry-overlay.jpg"
    )
    try:
        report = analyze(
            photo_path=args.photo,
            capture_sidecar_path=args.capture_sidecar,
            action_result_path=args.action_result,
            panel_corners=args.panel_corners,
        )
        if args.output.resolve() == overlay_output.resolve():
            raise RawP16PhotoAnalysisError("report and overlay outputs must differ")
        if args.output.exists():
            raise RawP16PhotoAnalysisError(
                f"refusing to overwrite output: {args.output}"
            )
        photo_payload = _read_stable_regular(args.photo, label="formal photo")
        overlay_payload = _render_geometry_overlay(photo_payload, report)
        unsigned = dict(report)
        unsigned.pop("integrity", None)
        unsigned["geometry_overlay"] = {
            "path": str(overlay_output),
            "bytes": len(overlay_payload),
            "sha256": _sha256_bytes(overlay_payload),
            "purpose": "human QA of current-photo cell mapping; not colour qualification",
        }
        unsigned["integrity"] = {
            "algorithm": INTEGRITY_ALGORITHM,
            "sha256": _sha256_bytes(_canonical_json(unsigned)),
        }
        report = unsigned
        _write_bytes_exclusive(
            overlay_output, overlay_payload, label="geometry overlay"
        )
        try:
            _write_exclusive(args.output, report)
        except Exception:
            overlay_output.unlink(missing_ok=True)
            raise
    except RawP16PhotoAnalysisError as error:
        print(f"RAW-P16 photo analysis error: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "output": str(args.output),
                "geometry_overlay": str(overlay_output),
                "integrity_sha256": report["integrity"]["sha256"],
                "classification": report["classification"]["state"],
                "obvious_left_right_codes": report["visible_differentiation_summary"][
                    "obvious_left_right_difference_candidates"
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
