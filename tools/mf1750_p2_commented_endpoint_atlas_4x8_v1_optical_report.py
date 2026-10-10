#!/usr/bin/env python3
"""Seal the P2-C ordinal-1 camera-relative optical diagnostic.

The program is offline.  It accepts ten retained clean-white captures and ten
captures of the one completed P2-C action, authenticates their camera/action
bindings, fits the current 4x8 lattice from the 56 visible coloured blocks,
and reports CS1, CS2, four-position, and cross-controller measurements.  It
does not qualify a colour or lightness level and performs no hardware I/O.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Mapping, Sequence
from itertools import combinations
import json
import math
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.color_pipeline.color import delta_e_ciede2000  # noqa: E402
from tools import mf1750_camera_capture_evidence as camera  # noqa: E402
from tools import mf1750_p2_commented_endpoint_atlas_4x8_v1_pack as pack  # noqa: E402
from tools import mf1750_raw_p16_retained_atlas_photo_analyzer as base  # noqa: E402


SCHEMA_VERSION = 2
KIND = "mf1750-p2-commented-endpoint-atlas-4x8-v1-optical-report-v2"
CAPTURE_COUNT = 10
CONTROLLER_WIDTH = 512
LOGICAL_WIDTH = 1024
LOGICAL_HEIGHT = 600
INNER_FRACTION = 0.60
MAX_GRID_RMSE_PX = 3.0
MAX_GRID_P95_PX = 4.0
MAX_GRID_ERROR_PX = 5.0
MAX_ROI_HIGH_CLIP_FRACTION = 0.05
EXPECTED_CAMERA = {
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
CANDIDATE_SEPARATION_V1 = {
    "minimum_absolute_delta_lstar": 2.0,
    "minimum_delta_e00": 3.0,
    "maximum_same_hue_angle_degrees": 5.0,
    "noise_gate_formula": "max(5*MAD, 95% normal-mean CI half-width)",
    "required_fresh_chain_direction_reproduction_fraction": 1.0,
    "required_independent_fresh_chain_count": 3,
}
POSITION_GATE = {
    "controller_cell_centered_absolute_delta_lstar_p95_maximum": 3.0,
    "controller_cell_centered_delta_e76_p95_maximum": 5.0,
}
CROSS_CONTROLLER_V1 = {
    "absolute_delta_lstar_p95_maximum": 3.0,
    "delta_e76_p95_maximum": 5.0,
    "hue_drift_degrees_maximum": 5.0,
}


class P2OpticalReportError(RuntimeError):
    """The P2-C optical evidence set is incomplete or inconsistent."""


def _seal(root: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(root)
    result["integrity"] = {
        "algorithm": base.INTEGRITY_ALGORITHM,
        "sha256": base._sha256_bytes(base._canonical_json(result)),  # noqa: SLF001
    }
    return result


def _logical_cell(controller: int, row: int, column: int) -> dict[str, Any]:
    x = pack.GRID_X0 + column * (pack.CELL_WIDTH + pack.GAP_X)
    x += controller * CONTROLLER_WIDTH
    y = pack.GRID_Y_BY_ROW[row]
    code = pack.CODE_ROWS[row][column]
    return {
        "cell_id": f"CS{controller + 1}-R{row}-C{column}-CODE{code}",
        "controller": controller,
        "controller_name": f"CS{controller + 1}",
        "row": row,
        "column": column,
        "code": code,
        "logical_bounds": [x, y, pack.CELL_WIDTH, pack.CELL_HEIGHT],
        "logical_center": [x + pack.CELL_WIDTH / 2, y + pack.CELL_HEIGHT / 2],
    }


def _cells() -> list[dict[str, Any]]:
    return [
        _logical_cell(controller, row, column)
        for controller in range(2)
        for row in range(pack.GRID_ROWS)
        for column in range(pack.GRID_COLUMNS)
    ]


def _runtime_action(expected: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ordinal": 1,
        "role": expected["role"],
        "branch": expected["branch"],
        "descriptor_id": expected["descriptor_id"],
        "action_id": expected["action_id"],
        "frame_sha256": expected["frame"]["sha256"],
        "cs1_dtm_sha256": expected["cs1_dtm"]["sha256"],
        "cs2_dtm_sha256": expected["cs2_dtm"]["sha256"],
        "palette_source": expected["palette_source"],
        "global_header": expected["global_header"],
        "profile_id": expected["profile_id"],
        "global_tuple_id": expected["global_tuple_id"],
        "waveform_binding": expected["waveform_binding"],
        "boot_admission": expected["boot_admission"],
    }


def _validate_action(root: Mapping[str, Any]) -> dict[str, Any]:
    expected = pack.REPORT["actions"][0]
    action = base._mapping(root.get("action"), label="action.action")  # noqa: SLF001
    terminal = base._mapping(  # noqa: SLF001
        root.get("terminal_report"), label="action.terminal_report"
    )
    for field, value in _runtime_action(expected).items():
        if action.get(field) != value:
            raise P2OpticalReportError(f"P2-C action {field} differs")
    if (
        root.get("kind")
        != "mf1750-ec5-p2-commented-endpoint-atlas-4x8-v1-result"
        or root.get("outcome") != "complete_pass"
        or root.get("visible_refreshes") != 1
        or root.get("firmware_sha256")
        != pack.ARTIFACTS["firmware.bin"]["sha256"]
    ):
        raise P2OpticalReportError("P2-C result identity or refresh count differs")
    expected_terminal = {
        "terminal_state": "COMPLETE",
        "result": True,
        "valid": True,
        "campaign_id": pack.CAMPAIGN_ID,
        "test_id": pack.TEST_ID,
        "contract_id": pack.REPORT["contract_id"],
        "build_tag": pack.BUILD_TAG,
        "action_id": expected["action_id"],
        "descriptor_id": expected["descriptor_id"],
        "ordinal": 1,
        "role": pack.ROLE,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "campaign_complete": True,
    }
    for field, value in expected_terminal.items():
        if terminal.get(field) != value:
            raise P2OpticalReportError(f"P2-C terminal {field} differs")
    driver = base._mapping(terminal.get("driver"), label="terminal.driver")  # noqa: SLF001
    if (
        driver.get("valid") is not True
        or driver.get("sequence_ok") is not True
        or driver.get("wait_timeout") is not False
        or driver.get("failure_stage") != "none"
        or driver.get("failure_code") != 0
        or driver.get("running") is not False
    ):
        raise P2OpticalReportError("P2-C terminal driver evidence differs")
    return {
        "campaign_id": pack.CAMPAIGN_ID,
        "test_id": pack.TEST_ID,
        "contract_id": pack.REPORT["contract_id"],
        "firmware_sha256": pack.ARTIFACTS["firmware.bin"]["sha256"],
        "running_app_elf_sha256": root.get("running_app_elf_sha256"),
        "boot_nonce": root.get("boot_nonce"),
        "action_id": expected["action_id"],
        "descriptor_id": expected["descriptor_id"],
        "frame_sha256": expected["frame"]["sha256"],
        "cs1_dtm_sha256": expected["cs1_dtm"]["sha256"],
        "cs2_dtm_sha256": expected["cs2_dtm"]["sha256"],
        "profile_id": expected["profile_id"],
        "global_tuple_id": expected["global_tuple_id"],
        "waveform_internal_phase": "OPAQUE",
        "driver": {
            "operation_id": driver.get("operation_id"),
            "spi_hz": driver.get("spi_hz"),
            "cs1_upload_ms": driver.get("cs1_upload_ms"),
            "cs2_upload_ms": driver.get("cs2_upload_ms"),
            "pon_ms": driver.get("pon_ms"),
            "drf_ms": driver.get("drf_ms"),
            "pof_ms": driver.get("pof_ms"),
            "post_psr_ms": driver.get("post_psr_ms"),
            "total_ms": driver.get("total_ms"),
            "busy_evidence": {
                "pon_busy_seen": driver.get("pon_busy_seen"),
                "drf_busy_seen": driver.get("drf_busy_seen"),
                "pof_busy_seen": driver.get("pof_busy_seen"),
                "post_psr_busy_seen": driver.get("post_psr_busy_seen"),
                "busy_assertion_missing": driver.get("busy_assertion_missing"),
                "busy_missing_stage": driver.get("busy_missing_stage"),
            },
        },
    }


def _same_number(actual: Any, expected: float, *, label: str) -> None:
    if isinstance(actual, bool) or not isinstance(actual, (int, float)):
        raise P2OpticalReportError(f"{label} is not numeric")
    tolerance = 0.001 if label.endswith("fps") else 0.0
    if not math.isclose(float(actual), expected, rel_tol=0.0, abs_tol=tolerance):
        raise P2OpticalReportError(f"{label} differs from {expected:g}")


def _camera_lock(root: Mapping[str, Any]) -> dict[str, Any]:
    coverage = base._mapping(root.get("coverage"), label="capture.coverage")  # noqa: SLF001
    record = base._mapping(root.get("camera"), label="capture.camera")  # noqa: SLF001
    if (
        coverage.get("scope") != camera.COVERAGE_FULL
        or coverage.get("full_panel_visible") is not True
        or coverage.get("full_panel_uncropped") is not True
        or coverage.get("mount_id") != "MF1750-P2-C-20260905-A"
    ):
        raise P2OpticalReportError("capture coverage or mount differs")
    instance = str(record.get("instance_id", "")).casefold()
    if (
        record.get("camera_id") != camera.TARGET_CAMERA_FRIENDLY_NAME
        or camera.TARGET_CAMERA_USB_TOKEN not in instance
        or camera.EXCLUDED_BINOCULAR_USB_TOKEN in instance
        or str(record.get("backend", "")).upper() != "DSHOW"
    ):
        raise P2OpticalReportError("capture is not the allowed 48MP DirectShow camera")
    requested = base._mapping(  # noqa: SLF001
        record.get("requested_settings"), label="camera.requested_settings"
    )
    for field, expected in EXPECTED_CAMERA.items():
        actual = requested.get(field)
        if isinstance(expected, str):
            if actual != expected:
                raise P2OpticalReportError(f"requested {field} differs")
        else:
            _same_number(actual, expected, label=f"requested.{field}")
    before = dict(
        base._mapping(  # noqa: SLF001
            record.get("effective_settings_before_frame"),
            label="camera.effective_settings_before_frame",
        )
    )
    after = dict(
        base._mapping(  # noqa: SLF001
            record.get("effective_settings_after_frame"),
            label="camera.effective_settings_after_frame",
        )
    )
    if before != after:
        raise P2OpticalReportError("effective camera settings changed around frame")
    for field in (
        "fourcc",
        "frame_width",
        "frame_height",
        "focus",
        "exposure",
        "white_balance_temperature",
    ):
        expected = EXPECTED_CAMERA[field]
        actual = before.get(field)
        if isinstance(expected, str):
            if actual != expected:
                raise P2OpticalReportError(f"effective {field} differs")
        else:
            _same_number(actual, expected, label=f"effective.{field}")
    _same_number(before.get("fps"), 15.000015000015, label="effective.fps")
    accepted_modes = {
        "autofocus": {0.0, 2.0},
        "auto_exposure": {-1.0, 0.25},
        "auto_white_balance": {0.0},
    }
    for field, accepted in accepted_modes.items():
        actual = before.get(field)
        if not isinstance(actual, (int, float)) or float(actual) not in accepted:
            raise P2OpticalReportError(f"effective {field} is not manual")
    writes = base._mapping(record.get("set_results"), label="camera.set_results")  # noqa: SLF001
    required = {field for field, value in requested.items() if value is not None}
    if any(writes.get(field) is not True for field in required):
        raise P2OpticalReportError("a requested camera setting write failed")
    if record.get("read_failures") != 0:
        raise P2OpticalReportError("camera read failure is nonzero")
    return {
        "camera_id": record["camera_id"],
        "instance_id": record["instance_id"],
        "backend": record["backend"],
        "mount_id": coverage["mount_id"],
        "requested_settings": dict(requested),
        "effective_settings": before,
        "raw_capture_supported": False,
        "iso_control_supported": False,
        "hardware_trigger_supported": False,
    }


def _load_capture(path: Path) -> tuple[Mapping[str, Any], bytes, Any, dict[str, Any]]:
    try:
        root = camera.validate_capture_evidence(path)
    except camera.CameraCaptureEvidenceError as error:
        raise P2OpticalReportError(f"capture rejected: {path}: {error}") from error
    photo_record = base._mapping(root.get("photo"), label="capture.photo")  # noqa: SLF001
    try:
        photo_path = camera._resolve_evidence_path(  # noqa: SLF001
            photo_record.get("path"), sidecar_path=path, label="capture photo"
        )
    except camera.CameraCaptureEvidenceError as error:
        raise P2OpticalReportError(str(error)) from error
    payload = base._read_stable_regular(photo_path, label="capture photo")  # noqa: SLF001
    if base._sha256_bytes(payload) != photo_record.get("sha256"):  # noqa: SLF001
        raise P2OpticalReportError("capture photo SHA-256 differs")
    rgb = base._decode_rgb(payload)  # noqa: SLF001
    lock = _camera_lock(root)
    return root, payload, rgb, {
        "sidecar_path": str(path.resolve()),
        "sidecar_sha256": base._sha256_bytes(path.read_bytes()),  # noqa: SLF001
        "capture_id": root.get("capture_id"),
        "capture_binding": root.get("capture_binding"),
        "captured_at": root.get("captured_at"),
        "photo_path": str(photo_path),
        "photo_sha256": photo_record.get("sha256"),
        "camera_lock": lock,
    }


def _fit_grid(rgb: Any) -> tuple[Any, dict[str, Any]]:
    cv2, np = base._import_cv()  # noqa: SLF001
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 20, 70)
    edges = cv2.morphologyEx(
        edges, cv2.MORPH_CLOSE, np.ones((5, 5), dtype=np.uint8), iterations=1
    )
    image_area = float(rgb.shape[0] * rgb.shape[1])
    contours, _hierarchy = cv2.findContours(
        edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
    )
    candidates: list[dict[str, Any]] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        perimeter = float(cv2.arcLength(contour, True))
        polygon = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
        if not (
            image_area * 0.0007 <= area <= image_area * 0.004
            and len(polygon) == 4
            and cv2.isContourConvex(polygon)
        ):
            continue
        _x, _y, width, height = cv2.boundingRect(contour)
        if height < 1 or not 0.2 <= width / height <= 1.25:
            continue
        candidates.append(
            {
                "area": area,
                "center": np.mean(polygon.reshape(4, 2), axis=0),
            }
        )
    kept: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: item["area"], reverse=True):
        if all(
            float(np.linalg.norm(candidate["center"] - other["center"])) > 24.0
            for other in kept
        ):
            kept.append(candidate)
    if len(kept) != 56:
        raise P2OpticalReportError(
            f"current P2-C image must expose 56 unique colour rectangles; got {len(kept)}"
        )
    ordered = sorted(kept, key=lambda item: float(item["center"][1]))
    row_groups = [
        sorted(ordered[index * 14 : (index + 1) * 14], key=lambda item: item["center"][0])
        for index in range(4)
    ]
    hypotheses: list[dict[str, Any]] = []
    all_cells = _cells()
    for omitted_code in range(8):
        logical: list[list[float]] = []
        observed: list[Any] = []
        for row in range(4):
            expected = sorted(
                [
                    cell
                    for cell in all_cells
                    if cell["row"] == row and cell["code"] != omitted_code
                ],
                key=lambda cell: cell["logical_center"][0],
            )
            for cell, candidate in zip(expected, row_groups[row], strict=True):
                logical.append(cell["logical_center"])
                observed.append(candidate["center"])
        homography, _mask = cv2.findHomography(
            np.asarray(logical, dtype=np.float32),
            np.asarray(observed, dtype=np.float32),
            0,
        )
        projected = cv2.perspectiveTransform(
            np.asarray([logical], dtype=np.float32), homography
        )[0]
        errors = np.linalg.norm(projected - np.asarray(observed), axis=1)
        hypotheses.append(
            {
                "omitted_code": omitted_code,
                "homography": homography,
                "errors": errors,
                "rmse": math.sqrt(float(np.mean(errors**2))),
                "p95": float(np.percentile(errors, 95)),
                "maximum": float(np.max(errors)),
            }
        )
    hypotheses.sort(key=lambda item: item["rmse"])
    winner = hypotheses[0]
    if (
        winner["rmse"] > MAX_GRID_RMSE_PX
        or winner["p95"] > MAX_GRID_P95_PX
        or winner["maximum"] > MAX_GRID_ERROR_PX
        or hypotheses[1]["rmse"] <= MAX_GRID_RMSE_PX
    ):
        raise P2OpticalReportError("visible-cell lattice does not have one unique fit")
    panel = cv2.perspectiveTransform(
        np.asarray(
            [[[0, 0], [LOGICAL_WIDTH, 0], [LOGICAL_WIDTH, LOGICAL_HEIGHT], [0, LOGICAL_HEIGHT]]],
            dtype=np.float32,
        ),
        winner["homography"],
    )[0]
    return winner["homography"], {
        "source": "CURRENT_PHOTO_56_VISIBLE_CELL_LATTICE",
        "automatic_cell_lattice_reprojection_proven": True,
        "historical_homography_reused": False,
        "visible_rectangle_count": 56,
        "unique_omitted_input_code_hypothesis": winner["omitted_code"],
        "omitted_code_interpretation": (
            "geometry-only observation: this input code was not edge-separated from "
            "the current background; it is not an absolute white qualification"
        ),
        "homography_logical_to_photo": [
            [round(float(value), 12) for value in row]
            for row in winner["homography"].tolist()
        ],
        "projected_panel_corners_tl_tr_br_bl": [
            [round(float(value), 6) for value in row] for row in panel.tolist()
        ],
        "reprojection_rmse_px": round(winner["rmse"], 6),
        "reprojection_p95_px": round(winner["p95"], 6),
        "reprojection_maximum_px": round(winner["maximum"], 6),
        "alternative_omitted_code_hypotheses": [
            {
                "omitted_code": item["omitted_code"],
                "rmse_px": round(item["rmse"], 6),
                "p95_px": round(item["p95"], 6),
                "maximum_px": round(item["maximum"], 6),
            }
            for item in hypotheses
        ],
    }


def _rectified_samples(rgb: Any, homography: Any) -> dict[str, dict[str, Any]]:
    cv2, np = base._import_cv()  # noqa: SLF001
    rectified = cv2.warpPerspective(
        rgb,
        np.linalg.inv(homography),
        (LOGICAL_WIDTH, LOGICAL_HEIGHT),
        flags=cv2.INTER_LINEAR,
    )
    result: dict[str, dict[str, Any]] = {}
    for cell in _cells():
        x, y, width, height = cell["logical_bounds"]
        mx = width * (1 - INNER_FRACTION) / 2
        my = height * (1 - INNER_FRACTION) / 2
        x0, x1 = int(math.ceil(x + mx)), int(math.floor(x + width - mx))
        y0, y1 = int(math.ceil(y + my)), int(math.floor(y + height - my))
        pixels = rectified[y0:y1, x0:x1].reshape(-1, 3).astype(np.float64)
        median = np.median(pixels, axis=0)
        rgb8 = tuple(int(round(float(value))) for value in median)
        result[cell["cell_id"]] = {
            "lab": [float(value) for value in base.srgb8_to_lab(rgb8)],
            "rgb_median": [float(value) for value in median],
            "rgb_mad": [
                float(value) for value in np.median(np.abs(pixels - median), axis=0)
            ],
            "high_clip_fraction": float(np.mean(np.any(pixels >= 250, axis=1))),
            "sample_count": int(len(pixels)),
        }
    return result


def _median_lab(samples: Sequence[Sequence[float]]) -> list[float]:
    _cv2, np = base._import_cv()  # noqa: SLF001
    return [float(value) for value in np.median(np.asarray(samples), axis=0)]


def _ci95(values: Sequence[float]) -> float:
    _cv2, np = base._import_cv()  # noqa: SLF001
    data = np.asarray(values, dtype=np.float64)
    return float(1.96 * np.std(data, ddof=1) / math.sqrt(len(data)))


def _mad(values: Sequence[float]) -> float:
    _cv2, np = base._import_cv()  # noqa: SLF001
    data = np.asarray(values, dtype=np.float64)
    return float(np.median(np.abs(data - np.median(data))))


def _p95(values: Sequence[float]) -> float:
    _cv2, np = base._import_cv()  # noqa: SLF001
    return float(np.percentile(np.asarray(values, dtype=np.float64), 95))


def _hue(lab: Sequence[float]) -> float | None:
    chroma = math.hypot(lab[1], lab[2])
    if chroma < 5.0:
        return None
    return math.degrees(math.atan2(lab[2], lab[1])) % 360.0


def _hue_distance(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    delta = abs(left - right) % 360.0
    return min(delta, 360.0 - delta)


def _analyse_cells(
    baseline_frames: Sequence[Mapping[str, Mapping[str, Any]]],
    post_frames: Sequence[Mapping[str, Mapping[str, Any]]],
) -> tuple[list[dict[str, Any]], list[float]]:
    global_baseline_reference = _median_lab(
        [
            frame[cell["cell_id"]]["lab"]
            for frame in baseline_frames
            for cell in _cells()
        ]
    )
    output: list[dict[str, Any]] = []
    for cell in _cells():
        cell_id = cell["cell_id"]
        before = [frame[cell_id] for frame in baseline_frames]
        after = [frame[cell_id] for frame in post_frames]
        before_lab = _median_lab([item["lab"] for item in before])
        after_lab = _median_lab([item["lab"] for item in after])
        normalized_after_lab = [
            after_lab[index]
            + global_baseline_reference[index]
            - before_lab[index]
            for index in range(3)
        ]
        l_values = [item["lab"][0] for item in before]
        before_de00 = [delta_e_ciede2000(item["lab"], before_lab) for item in before]
        l_mad = _mad(l_values)
        l_ci = _ci95(l_values)
        de_mad = _mad(before_de00)
        de_ci = _ci95(before_de00)
        post_de00 = [delta_e_ciede2000(item["lab"], after_lab) for item in after]
        output.append(
            {
                **cell,
                "baseline_camera_relative_lab": [round(value, 6) for value in before_lab],
                "post_camera_relative_lab": [round(value, 6) for value in after_lab],
                "baseline_normalized_post_camera_relative_lab": [
                    round(value, 6) for value in normalized_after_lab
                ],
                "delta_lstar_post_minus_baseline": round(after_lab[0] - before_lab[0], 6),
                "delta_e76_post_vs_baseline": round(math.dist(after_lab, before_lab), 6),
                "delta_e00_post_vs_baseline": round(
                    float(delta_e_ciede2000(after_lab, before_lab)), 6
                ),
                "baseline_noise": {
                    "sample_count": CAPTURE_COUNT,
                    "lstar_mad": round(l_mad, 9),
                    "lstar_ci95_half_width": round(l_ci, 9),
                    "lstar_noise_gate": round(max(5 * l_mad, l_ci), 9),
                    "delta_e00_to_median_mad": round(de_mad, 9),
                    "delta_e00_to_median_ci95_half_width": round(de_ci, 9),
                    "delta_e00_noise_gate": round(max(5 * de_mad, de_ci), 9),
                },
                "post_repeat": {
                    "sample_count": CAPTURE_COUNT,
                    "delta_e00_to_median_p95": round(_p95(post_de00), 9),
                    "delta_e00_to_median_maximum": round(max(post_de00), 9),
                },
                "quality": {
                    "baseline_maximum_high_clip_fraction": round(
                        max(item["high_clip_fraction"] for item in before), 9
                    ),
                    "post_maximum_high_clip_fraction": round(
                        max(item["high_clip_fraction"] for item in after), 9
                    ),
                },
            }
        )
    return output, global_baseline_reference


def _summaries(cells: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[int, int], list[Mapping[str, Any]]] = defaultdict(list)
    by_position: dict[tuple[int, int, int], Mapping[str, Any]] = {}
    for cell in cells:
        grouped[(cell["controller"], cell["code"])].append(cell)
        by_position[(cell["controller"], cell["row"], cell["column"])] = cell
    groups: list[dict[str, Any]] = []
    centers: dict[tuple[int, int], list[float]] = {}
    local_pass: dict[int, bool] = {0: True, 1: True}
    for controller in range(2):
        for code in range(8):
            samples = sorted(
                grouped[(controller, code)], key=lambda item: (item["row"], item["column"])
            )
            labs = [
                item["baseline_normalized_post_camera_relative_lab"]
                for item in samples
            ]
            center = _median_lab(labs)
            centers[(controller, code)] = center
            dl = [abs(item[0] - center[0]) for item in labs]
            de76 = [math.dist(item, center) for item in labs]
            gate_pass = _p95(dl) <= 3.0 and _p95(de76) <= 5.0
            local_pass[controller] = local_pass[controller] and gate_pass
            groups.append(
                {
                    "controller": f"CS{controller + 1}",
                    "code": code,
                    "four_positions": [item["cell_id"] for item in samples],
                    "baseline_normalized_camera_relative_lab_component_median": [
                        round(value, 6) for value in center
                    ],
                    "absolute_delta_lstar_to_center_p95": round(_p95(dl), 6),
                    "delta_e76_to_center_p95": round(_p95(de76), 6),
                    "position_gate_pass_in_this_retained_state": gate_pass,
                    "qualification_effect": "NONE",
                }
            )
    controller_pairs: list[dict[str, Any]] = []
    for row in range(4):
        for column in range(8):
            left = by_position[(0, row, column)]
            right = by_position[(1, row, column)]
            lab1 = left["baseline_normalized_post_camera_relative_lab"]
            lab2 = right["baseline_normalized_post_camera_relative_lab"]
            hue_delta = _hue_distance(_hue(lab1), _hue(lab2))
            controller_pairs.append(
                {
                    "row": row,
                    "column": column,
                    "code": left["code"],
                    "cs1_cell_id": left["cell_id"],
                    "cs2_cell_id": right["cell_id"],
                    "absolute_delta_lstar": round(abs(lab2[0] - lab1[0]), 6),
                    "delta_e76": round(math.dist(lab1, lab2), 6),
                    "delta_e00": round(float(delta_e_ciede2000(lab1, lab2)), 6),
                    "hue_drift_degrees": (
                        None if hue_delta is None else round(hue_delta, 6)
                    ),
                }
            )
    pairwise: list[dict[str, Any]] = []
    for controller in range(2):
        controller_cells = [cell for cell in cells if cell["controller"] == controller]
        for code1, code2 in combinations(range(8), 2):
            lab1, lab2 = centers[(controller, code1)], centers[(controller, code2)]
            hue_delta = _hue_distance(_hue(lab1), _hue(lab2))
            related_cells = [
                item for item in controller_cells if item["code"] in {code1, code2}
            ]
            l_noise = max(item["baseline_noise"]["lstar_noise_gate"] for item in related_cells)
            de_noise = max(
                item["baseline_noise"]["delta_e00_noise_gate"] for item in related_cells
            )
            dl = abs(lab2[0] - lab1[0])
            de00 = float(delta_e_ciede2000(lab1, lab2))
            same_hue_candidate = (
                hue_delta is not None
                and hue_delta <= CANDIDATE_SEPARATION_V1["maximum_same_hue_angle_degrees"]
                and dl >= CANDIDATE_SEPARATION_V1["minimum_absolute_delta_lstar"]
                and de00 >= CANDIDATE_SEPARATION_V1["minimum_delta_e00"]
                and dl > l_noise
                and de00 > de_noise
            )
            pairwise.append(
                {
                    "controller": f"CS{controller + 1}",
                    "code_pair": [code1, code2],
                    "absolute_delta_lstar": round(dl, 6),
                    "delta_e00": round(de00, 6),
                    "hue_angle_difference_degrees": (
                        None if hue_delta is None else round(hue_delta, 6)
                    ),
                    "lstar_noise_gate": round(l_noise, 6),
                    "delta_e00_noise_gate": round(de_noise, 6),
                    "same_hue_lightness_candidate_in_this_camera_relative_state": (
                        same_hue_candidate
                    ),
                    "qualified": False,
                }
            )
    hue_values = [
        item["hue_drift_degrees"]
        for item in controller_pairs
        if item["hue_drift_degrees"] is not None
    ]
    cross_gate = {
        "absolute_delta_lstar_p95": round(
            _p95([item["absolute_delta_lstar"] for item in controller_pairs]), 6
        ),
        "delta_e76_p95": round(_p95([item["delta_e76"] for item in controller_pairs]), 6),
        "hue_drift_degrees_p95": None if not hue_values else round(_p95(hue_values), 6),
    }
    cross_gate["preliminary_gate_pass"] = (
        cross_gate["absolute_delta_lstar_p95"] <= 3.0
        and cross_gate["delta_e76_p95"] <= 5.0
        and cross_gate["hue_drift_degrees_p95"] is not None
        and cross_gate["hue_drift_degrees_p95"] <= 5.0
        and all(local_pass.values())
    )
    return {
        "controller_code_four_position_groups": groups,
        "controller_local_position_gate": {
            "thresholds": POSITION_GATE,
            "CS1_all_codes_pass_in_this_retained_state": local_pass[0],
            "CS2_all_codes_pass_in_this_retained_state": local_pass[1],
            "qualification_effect": "NONE",
        },
        "same_position_cross_controller_pairs": controller_pairs,
        "cross_controller_v1_preliminary": {
            "thresholds": CROSS_CONTROLLER_V1,
            **cross_gate,
            "controller_optical_match_qualified": False,
        },
        "code_pair_separation": pairwise,
        "same_hue_lightness_candidates": [
            item
            for item in pairwise
            if item["same_hue_lightness_candidate_in_this_camera_relative_state"]
        ],
    }


def build_report(
    action_path: Path,
    baseline_paths: Sequence[Path],
    post_paths: Sequence[Path],
) -> tuple[dict[str, Any], bytes, Any]:
    if len(baseline_paths) != CAPTURE_COUNT or len(post_paths) != CAPTURE_COUNT:
        raise P2OpticalReportError("exactly ten baseline and ten post sidecars are required")
    action_payload, action_root = base._load_json(action_path, label="P2-C action")  # noqa: SLF001
    try:
        camera._verify_integrity(action_root, label="P2-C action")  # noqa: SLF001
    except camera.CameraCaptureEvidenceError as error:
        raise P2OpticalReportError(str(error)) from error
    action_identity = _validate_action(action_root)
    baseline = [_load_capture(Path(path)) for path in baseline_paths]
    post = [_load_capture(Path(path)) for path in post_paths]
    baseline_roots = [item[0] for item in baseline]
    post_roots = [item[0] for item in post]
    if any(root.get("capture_binding") != camera.BINDING_LOCKED_RETAINED for root in baseline_roots):
        raise P2OpticalReportError("white baseline must remain locked-retained evidence")
    if post_roots[0].get("capture_binding") != camera.BINDING_LIVE or any(
        root.get("capture_binding") != camera.BINDING_LOCKED_RETAINED
        for root in post_roots[1:]
    ):
        raise P2OpticalReportError("post captures must be one live plus nine retained frames")
    white_binding = camera.P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_WHITE_SUCCESSOR_BINDING
    for root in baseline_roots:
        for field in ("campaign_id", "test_id", "contract_id", "firmware_sha256", "action_id", "descriptor_id", "role"):
            if root.get(field) != white_binding[field]:
                raise P2OpticalReportError(f"white baseline {field} differs")
    for root in post_roots:
        for field in ("campaign_id", "test_id", "contract_id", "firmware_sha256", "action_id", "descriptor_id", "frame_sha256"):
            if root.get(field) != action_identity[field]:
                raise P2OpticalReportError(f"post capture {field} differs")
    locks = [item[3]["camera_lock"] for item in (*baseline, *post)]
    if any(lock != locks[0] for lock in locks[1:]):
        raise P2OpticalReportError("camera lock differs across the twenty captures")
    capture_ids = [item[3]["capture_id"] for item in (*baseline, *post)]
    photo_hashes = [item[3]["photo_sha256"] for item in (*baseline, *post)]
    if len(set(capture_ids)) != 20 or len(set(photo_hashes)) != 20:
        raise P2OpticalReportError("capture IDs and photo hashes must be unique")
    homography, geometry = _fit_grid(post[0][2])
    baseline_frames = [_rectified_samples(item[2], homography) for item in baseline]
    post_frames = [_rectified_samples(item[2], homography) for item in post]
    cells, global_baseline_reference = _analyse_cells(
        baseline_frames, post_frames
    )
    summary = _summaries(cells)
    maximum_clip = max(
        max(
            cell["quality"]["baseline_maximum_high_clip_fraction"],
            cell["quality"]["post_maximum_high_clip_fraction"],
        )
        for cell in cells
    )
    run_seed = {
        "boot_nonce": action_identity["boot_nonce"],
        "action_id": action_identity["action_id"],
        "capture_ids": capture_ids,
    }
    report = _seal(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "run_id": base._sha256_bytes(base._canonical_json(run_seed)),  # noqa: SLF001
            "created_at": camera._now(),  # noqa: SLF001
            "panel": {
                "model": "MF-17506-M009F-T",
                "logical_resolution": [1024, 600],
                "technology": "E6 Spectra 6",
                "physical_unit_serial": None,
                "physical_unit_serial_null_reason": "no authenticated panel serial capture",
            },
            "controllers": [
                {"controller": "CS1", "revision": "SPD1657B rev 0x04"},
                {"controller": "CS2", "revision": "SPD1657B rev 0x04"},
            ],
            "source_state": {
                "state": "retained clean factory-OTP white successor",
                "action_identity": white_binding,
                "continuity_electrically_proven": False,
                "operator_clean_white_confirmation_bound": True,
            },
            "target_state": {
                "state": "P2-C commented-profile position-balanced 4x8 endpoint atlas",
                "input_codes": list(range(8)),
                "spatial_dither": False,
            },
            "test_phase": "P2_C_ORDINAL_1_ENDPOINT_DIAGNOSTIC",
            "temperature_c": None,
            "temperature_null_reason": "no authenticated thermometer capture in this run",
            "action_binding": action_identity,
            "protocol": {
                "arm_count": 1,
                "execute_count": 1,
                "driver_count": 1,
                "visible_refresh_count": 1,
                "retry_count": 0,
                "recovery_count": 0,
                "identity_and_protocol_pass": True,
            },
            "camera": locks[0],
            "capture_evidence": {
                "baseline": [item[3] for item in baseline],
                "post": [item[3] for item in post],
                "baseline_capture_count": 10,
                "post_capture_count": 10,
            },
            "geometry": geometry,
            "measurement": {
                "space": "camera-relative Lab derived from JPEG RGB as sRGB D65/2deg",
                "calibrated_lab": False,
                "delta_e76_and_delta_e00_reported_separately": True,
                "global_baseline_reference_camera_relative_lab": [
                    round(value, 6) for value in global_baseline_reference
                ],
                "spatial_normalization": (
                    "post_Lab + global_white_baseline_median_Lab - "
                    "same_ROI_white_baseline_median_Lab"
                ),
                "spatial_normalization_scope": (
                    "camera-relative comparison only; it is not spectral, colour-card, "
                    "or absolute Lab calibration"
                ),
                "rectification": "INTER_LINEAR current-photo lattice homography",
                "roi": "inner 60 percent of each logical cell",
                "baseline_noise_ci_method": "normal-mean 1.96*s/sqrt(n), n=10",
                "threshold_version": "candidate-separation-v1",
                "thresholds": CANDIDATE_SEPARATION_V1,
                "maximum_roi_high_clip_fraction": round(maximum_clip, 9),
                "maximum_allowed_roi_high_clip_fraction": MAX_ROI_HIGH_CLIP_FRACTION,
                "image_and_optical_evidence_valid": (
                    maximum_clip <= MAX_ROI_HIGH_CLIP_FRACTION
                ),
            },
            "cells": cells,
            "summaries": summary,
            "decision": {
                "verdict": "HOLD_FOR_EVIDENCE",
                "diagnostic_classification": "ENDPOINT_ONLY_WITH_CAMERA_RELATIVE_LIGHTNESS_CANDIDATES",
                "position_reproducibility_proven": False,
                "same_hue_lightness_qualified": False,
                "hold_completed": False,
                "independent_fresh_white_reconstruction_completed": False,
                "retention_completed": False,
                "both_controllers_individually_qualified": False,
                "controller_optical_match_qualified": False,
                "qualified_colour_or_lightness_slot_count": 0,
                "reason": (
                    "one completed P2-C action plus repeated retained photos can only "
                    "produce a diagnostic; HOLD, three independent fresh chains, fresh-white "
                    "reconstruction, retention, and controller qualification remain absent"
                ),
            },
            "phase_field_policy": {
                "unknown_waveform_internal_phase": "OPAQUE",
                "reset_shake_drive_fields_inferred": False,
            },
            "hardware_io_performed_by_analyzer": False,
            "camera_access_performed_by_analyzer": False,
            "output_write_contract": "O_EXCL",
            "action_result": {
                "path": str(action_path.resolve()),
                "bytes": len(action_payload),
                "sha256": base._sha256_bytes(action_payload),  # noqa: SLF001
                "canonical_integrity_sha256": base._mapping(  # noqa: SLF001
                    action_root.get("integrity"), label="action.integrity"
                ).get("sha256"),
            },
        }
    )
    return report, post[0][1], homography


def _overlay(photo_payload: bytes, homography: Any) -> bytes:
    cv2, np = base._import_cv()  # noqa: SLF001
    rgb = base._decode_rgb(photo_payload)  # noqa: SLF001
    canvas = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    for cell in _cells():
        x, y, width, height = cell["logical_bounds"]
        polygon = cv2.perspectiveTransform(
            np.asarray([[[x, y], [x + width, y], [x + width, y + height], [x, y + height]]], dtype=np.float32),
            homography,
        )[0]
        colour = (255, 255, 0) if cell["controller"] == 0 else (0, 165, 255)
        cv2.polylines(canvas, [np.rint(polygon).astype(np.int32)], True, colour, 3, cv2.LINE_AA)
        center = cv2.perspectiveTransform(
            np.asarray([[cell["logical_center"]]], dtype=np.float32), homography
        )[0, 0]
        cv2.putText(
            canvas,
            str(cell["code"]),
            (int(center[0]) - 8, int(center[1]) + 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )
    ok, encoded = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not ok:
        raise P2OpticalReportError("overlay encoding failed")
    return bytes(encoded)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--action-result", type=Path, required=True)
    parser.add_argument("--baseline-sidecar", action="append", type=Path, required=True)
    parser.add_argument("--post-sidecar", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overlay-output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report, photo_payload, homography = build_report(
            args.action_result, args.baseline_sidecar, args.post_sidecar
        )
        base._write_exclusive(args.output, report)  # noqa: SLF001
        base._write_bytes_exclusive(  # noqa: SLF001
            args.overlay_output, _overlay(photo_payload, homography), label="P2-C overlay"
        )
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False))
    except (P2OpticalReportError, base.RawP16PhotoAnalysisError) as error:
        print(
            json.dumps(
                {"schema_version": SCHEMA_VERSION, "kind": f"{KIND}-error", "valid": False, "error": str(error)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
