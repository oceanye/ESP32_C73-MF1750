#!/usr/bin/env python3
"""Analyze one formally captured RAW-P16 crossover 4x8 atlas.

This analyzer is deliberately separate from the retained endpoint 4x2
analyzer.  The three accepted stages are bound to their frozen crossover
contract, action, firmware, and waveform-profile identities before any image
measurement is reported.  Geometry is supplied from the *current* photograph
as ordered panel corners; no historical G1 homography is reused.

The result remains camera-relative and non-qualifying.  It can compare the
four positions of each code and corresponding CS1/CS2 positions in one locked
capture.  It cannot prove an absolute, stable, or newly usable colour.
Importing or running this module performs no camera, device, network, serial,
relay, firmware, or display operation.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Mapping, Sequence
import json
import math
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.color_pipeline.color import (  # noqa: E402
    delta_e_ciede2000,
)
from tools import mf1750_camera_capture_evidence as camera  # noqa: E402
from tools import mf1750_raw_p16_crossover_position_balanced_pack as pack  # noqa: E402
from tools import mf1750_raw_p16_retained_atlas_photo_analyzer as base  # noqa: E402


SCHEMA_VERSION = 1
KIND = "mf1750-raw-p16-crossover-position-balanced-single-frame-analysis-v1"
INTEGRITY_ALGORITHM = base.INTEGRITY_ALGORITHM
CONTROLLER_COUNT = 2
CONTROLLER_WIDTH = 512
LOGICAL_WIDTH = 1024
LOGICAL_HEIGHT = 600
MIN_PANEL_AREA_FRACTION = 0.08
MIN_PROJECTED_CELL_SIDE_PX = 20.0
POSITION_SIMILAR_DE00 = 3.0
POSITION_OBVIOUS_DE00 = 5.0

# Independent partial-coverage mode.  These values deliberately do not relax
# the full-panel homography above: callers must opt into the separate helper.
PARTIAL_MODE = "PARTIAL_DUAL_3X8_TOP_ROWS_V1"
PARTIAL_SELECTED_ROWS = (0, 1, 2)
PARTIAL_SELECTED_COLUMNS = tuple(range(8))
PARTIAL_SELECTED_CELL_COUNT = 48
PARTIAL_REPLICATES_PER_CODE_PER_CONTROLLER = 3
PARTIAL_MIN_BLOCK_SIDE_PX = 240.0
PARTIAL_MAX_BLOCK_ASPECT_RATIO = 6.0
PARTIAL_MIN_PROJECTED_CELL_SIDE_PX = 24.0
PARTIAL_MIN_PROJECTED_CELL_AREA_PX2 = 1500.0
PARTIAL_MIN_COMBINED_AREA_FRACTION = 0.045725

# Keep one shared exception family for the two RAW-P16 photo analyzers.
CrossoverPhotoAnalysisError = base.RawP16PhotoAnalysisError


def _expected(
    stage: pack.Stage,
) -> tuple[pack.StageConfig, dict[str, Any], dict[str, Any]]:
    try:
        cfg = pack.STAGES[stage]
    except KeyError as error:
        raise CrossoverPhotoAnalysisError(
            f"unknown crossover stage {stage!r}"
        ) from error
    report = pack.build_report(stage)
    return cfg, report, report["actions"][0]


def _runtime_action(expected_action: Mapping[str, Any]) -> dict[str, Any]:
    """Return the frozen subset emitted in the host action-result object."""

    return {
        "ordinal": 1,
        "role": expected_action["role"],
        "branch": expected_action["branch"],
        "descriptor_id": expected_action["descriptor_id"],
        "action_id": expected_action["action_id"],
        "frame_sha256": expected_action["frame"]["sha256"],
        "cs1_dtm_sha256": expected_action["cs1_dtm"]["sha256"],
        "cs2_dtm_sha256": expected_action["cs2_dtm"]["sha256"],
        "palette_source": expected_action["palette_source"],
        "global_header": expected_action["global_header"],
        "profile_id": expected_action["profile_id"],
        "global_tuple_id": expected_action["global_tuple_id"],
        "waveform_binding": expected_action["waveform_binding"],
        "boot_admission": expected_action["boot_admission"],
    }


def _validate_action(
    stage: pack.Stage, action_root: Mapping[str, Any]
) -> dict[str, Any]:
    """Require the exact T1, T2, or T3 action/profile/firmware binding."""

    cfg, report, expected_action = _expected(stage)
    action = base._mapping(action_root.get("action"), label="action result.action")  # noqa: SLF001
    terminal = base._mapping(  # noqa: SLF001
        action_root.get("terminal_report"), label="action result.terminal_report"
    )
    expected_runtime = _runtime_action(expected_action)
    for field, expected_value in expected_runtime.items():
        if action.get(field) != expected_value:
            raise CrossoverPhotoAnalysisError(
                f"RAW-P16 crossover {stage} action {field} differs"
            )

    expected_result_kind = f"mf1750-ec5-{cfg.route_slug}-result"
    if (
        action_root.get("kind") != expected_result_kind
        or action_root.get("outcome") != "complete_pass"
        or action_root.get("visible_refreshes") != 1
        or action_root.get("firmware_sha256") != pack.ARTIFACTS[stage]["bin_sha256"]
    ):
        raise CrossoverPhotoAnalysisError(
            f"RAW-P16 crossover {stage} result identity differs"
        )

    terminal_expected = {
        "terminal_state": "COMPLETE",
        "result": True,
        "valid": True,
        "campaign_id": cfg.campaign_id,
        "test_id": cfg.test_id,
        "contract_id": report["contract_id"],
        "build_tag": cfg.build_tag,
        "action_id": expected_action["action_id"],
        "descriptor_id": expected_action["descriptor_id"],
        "ordinal": 1,
        "role": expected_action["role"],
        "driver_called": True,
        "driver_call_count_for_action": 1,
    }
    for field, expected_value in terminal_expected.items():
        if terminal.get(field) != expected_value:
            raise CrossoverPhotoAnalysisError(
                f"RAW-P16 crossover {stage} terminal {field} differs"
            )
    driver = base._mapping(terminal.get("driver"), label="terminal.driver")  # noqa: SLF001
    if (
        driver.get("valid") is not True
        or driver.get("sequence_ok") is not True
        or driver.get("wait_timeout") is not False
        or driver.get("failure_stage") != "none"
    ):
        raise CrossoverPhotoAnalysisError(
            f"RAW-P16 crossover {stage} terminal driver evidence differs"
        )

    geometry = report["contract"]["geometry"]
    if (
        geometry.get("grid_rows") != 4
        or geometry.get("grid_columns_per_controller") != 8
        or geometry.get("row_codes") != [list(row) for row in pack.CODE_ROWS]
        or geometry.get("samples_per_code_per_controller_per_frame") != 4
        or geometry.get("same_layout_both_controllers") is not True
        or geometry.get("spatial_dither") is not False
    ):
        raise CrossoverPhotoAnalysisError(
            f"offline RAW-P16 crossover {stage} 4x8 geometry differs"
        )
    return {
        "stage": stage,
        "campaign_id": cfg.campaign_id,
        "test_id": cfg.test_id,
        "contract_id": report["contract_id"],
        "action_id": expected_action["action_id"],
        "descriptor_id": expected_action["descriptor_id"],
        "role": expected_action["role"],
        "frame_sha256": expected_action["frame"]["sha256"],
        "cs1_dtm_sha256": expected_action["cs1_dtm"]["sha256"],
        "cs2_dtm_sha256": expected_action["cs2_dtm"]["sha256"],
        "firmware_sha256": pack.ARTIFACTS[stage]["bin_sha256"],
        "profile_id": expected_action["profile_id"],
        "global_tuple_id": expected_action["global_tuple_id"],
        "waveform_binding": expected_action["waveform_binding"],
        "global_header": expected_action["global_header"],
    }


def _logical_cell(controller: int, row: int, column: int) -> dict[str, Any]:
    if controller not in (0, 1) or row not in range(4) or column not in range(8):
        raise CrossoverPhotoAnalysisError(
            "cell is outside exact 2-controller position-balanced 4x8 layout"
        )
    x = pack.GRID_X0 + column * (pack.CELL_WIDTH + pack.GAP_X)
    y = pack.GRID_Y_BY_ROW[row]
    x += controller * CONTROLLER_WIDTH
    code = pack.CODE_ROWS[row][column]
    return {
        "cell_id": f"CS{controller + 1}-R{row}-C{column}-CODE{code}",
        "controller": controller,
        "row": row,
        "column": column,
        "position_index_for_code": sum(
            pack.CODE_ROWS[prior_row][prior_column] == code
            for prior_row in range(4)
            for prior_column in range(8)
            if (prior_row, prior_column) < (row, column)
        ),
        "code": code,
        "logical_bounds": [x, y, pack.CELL_WIDTH, pack.CELL_HEIGHT],
        "logical_center": [
            x + pack.CELL_WIDTH / 2.0,
            y + pack.CELL_HEIGHT / 2.0,
        ],
    }


def _all_logical_cells() -> list[dict[str, Any]]:
    return [
        _logical_cell(controller, row, column)
        for controller in range(CONTROLLER_COUNT)
        for row in range(pack.GRID_ROWS)
        for column in range(pack.GRID_COLUMNS)
    ]


def _coerce_panel_corners(value: str | Any) -> Any:
    _cv2, np = base._import_cv()  # noqa: SLF001
    if isinstance(value, str):
        return base._parse_panel_corners(value)  # noqa: SLF001
    corners = np.asarray(value, dtype=np.float64)
    if corners.shape != (4, 2) or not np.all(np.isfinite(corners)):
        raise CrossoverPhotoAnalysisError(
            "panel corners must be a finite 4x2 TL,TR,BR,BL array"
        )
    ordered = base._order_quad(corners)  # noqa: SLF001
    if not np.allclose(ordered, corners, rtol=0.0, atol=1e-6):
        raise CrossoverPhotoAnalysisError("panel corners must be ordered TL,TR,BR,BL")
    return corners


def _fit_panel_homography(
    panel_corners: str | Any, *, photo_width: int, photo_height: int
) -> tuple[Any, dict[str, Any]]:
    cv2, np = base._import_cv()  # noqa: SLF001
    corners = _coerce_panel_corners(panel_corners)
    if not cv2.isContourConvex(np.rint(corners).astype(np.int32)):
        raise CrossoverPhotoAnalysisError("panel corner quadrilateral is not convex")
    panel_area = abs(float(cv2.contourArea(corners.astype(np.float32))))
    area_fraction = panel_area / float(photo_width * photo_height)
    if area_fraction < MIN_PANEL_AREA_FRACTION:
        raise CrossoverPhotoAnalysisError(
            "current-photo panel quadrilateral is too small for formal sampling"
        )
    if not np.all(
        (corners[:, 0] >= 0)
        & (corners[:, 0] < photo_width)
        & (corners[:, 1] >= 0)
        & (corners[:, 1] < photo_height)
    ):
        raise CrossoverPhotoAnalysisError(
            "current-photo panel corners leave the formal photo"
        )
    logical_panel = np.asarray(
        [
            [0, 0],
            [LOGICAL_WIDTH, 0],
            [LOGICAL_WIDTH, LOGICAL_HEIGHT],
            [0, LOGICAL_HEIGHT],
        ],
        dtype=np.float32,
    )
    homography = cv2.getPerspectiveTransform(
        logical_panel, corners.astype(np.float32)
    ).astype(np.float64)
    if (
        not np.all(np.isfinite(homography))
        or abs(float(np.linalg.det(homography))) < 1e-12
    ):
        raise CrossoverPhotoAnalysisError("current-photo panel homography is singular")

    minimum_side = math.inf
    for cell in _all_logical_cells():
        x, y, width, height = cell["logical_bounds"]
        projected = base._project(  # noqa: SLF001
            homography,
            ((x, y), (x + width, y), (x + width, y + height), (x, y + height)),
        )
        if not np.all(
            (projected[:, 0] >= 0)
            & (projected[:, 0] < photo_width)
            & (projected[:, 1] >= 0)
            & (projected[:, 1] < photo_height)
        ):
            raise CrossoverPhotoAnalysisError(
                f"{cell['cell_id']} projected bounds leave the formal photo"
            )
        minimum_side = min(
            minimum_side,
            *(
                float(np.linalg.norm(projected[(index + 1) % 4] - projected[index]))
                for index in range(4)
            ),
        )
    if minimum_side < MIN_PROJECTED_CELL_SIDE_PX:
        raise CrossoverPhotoAnalysisError(
            "projected crossover cells are too small for formal sampling"
        )
    return homography, {
        "source": "EXPLICIT_CURRENT_PHOTO_PANEL_CORNERS",
        "historical_g1_homography_reused": False,
        "logical_coordinate_convention": "MF1750 full panel 1024x600",
        "homography_logical_to_current_photo": [
            [round(float(component), 12) for component in row]
            for row in homography.tolist()
        ],
        "supplied_panel_corners_tl_tr_br_bl": [
            [round(float(component), 6) for component in row]
            for row in corners.tolist()
        ],
        "panel_area_fraction_of_photo": round(area_fraction, 9),
        "minimum_required_panel_area_fraction": MIN_PANEL_AREA_FRACTION,
        "minimum_projected_cell_side_px": round(float(minimum_side), 6),
        "minimum_required_projected_cell_side_px": MIN_PROJECTED_CELL_SIDE_PX,
        "all_projected_cells_inside_photo": True,
        "automatic_cell_lattice_reprojection_proven": False,
        "manual_corner_precision_limitation": (
            "the current-photo panel corners are operator supplied and are not "
            "an independent cell-lattice reprojection proof"
        ),
        "sampling_geometry_admitted": True,
    }


def _fit_partial_dual_controller_blocks(
    partial_blocks: Mapping[str, Any], *, photo_width: int, photo_height: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fit two explicit top-three-row controller blocks, fail closed.

    Each supplied quadrilateral covers the complete eight-column extent of
    rows 0..2 for exactly one controller.  It is intentionally not treated as
    a full-panel fit and cannot evaluate row 3 or the bottom edge.
    """

    cv2, np = base._import_cv()  # noqa: SLF001
    if not isinstance(partial_blocks, Mapping) or set(partial_blocks) != {
        "CS1",
        "CS2",
    }:
        raise CrossoverPhotoAnalysisError(
            "partial blocks must be an exact CS1/CS2 object"
        )
    if (
        type(photo_width) is not int
        or type(photo_height) is not int
        or photo_width <= 0
        or photo_height <= 0
    ):
        raise CrossoverPhotoAnalysisError("partial photo dimensions are invalid")

    corners_by_controller: dict[str, Any] = {}
    block_areas: dict[str, float] = {}
    minimum_block_side = math.inf
    maximum_block_aspect = 0.0
    for controller in ("CS1", "CS2"):
        corners = _coerce_panel_corners(partial_blocks[controller])
        if not cv2.isContourConvex(np.rint(corners).astype(np.int32)):
            raise CrossoverPhotoAnalysisError(
                f"{controller} partial block quadrilateral is not convex"
            )
        if not np.all(
            (corners[:, 0] >= 0)
            & (corners[:, 0] < photo_width)
            & (corners[:, 1] >= 0)
            & (corners[:, 1] < photo_height)
        ):
            raise CrossoverPhotoAnalysisError(
                f"{controller} partial block leaves the photo"
            )
        sides = [
            float(np.linalg.norm(corners[(index + 1) % 4] - corners[index]))
            for index in range(4)
        ]
        shortest = min(sides)
        aspect = max(sides) / shortest if shortest > 0.0 else math.inf
        if shortest < PARTIAL_MIN_BLOCK_SIDE_PX:
            raise CrossoverPhotoAnalysisError(
                f"{controller} partial block shortest side is below the gate"
            )
        if aspect > PARTIAL_MAX_BLOCK_ASPECT_RATIO:
            raise CrossoverPhotoAnalysisError(
                f"{controller} partial block aspect ratio is implausible"
            )
        area = abs(float(cv2.contourArea(corners.astype(np.float32))))
        if area <= 0.0:
            raise CrossoverPhotoAnalysisError(
                f"{controller} partial block area is empty"
            )
        corners_by_controller[controller] = corners
        block_areas[controller] = area
        minimum_block_side = min(minimum_block_side, shortest)
        maximum_block_aspect = max(maximum_block_aspect, aspect)

    if float(np.mean(corners_by_controller["CS1"][:, 0])) >= float(
        np.mean(corners_by_controller["CS2"][:, 0])
    ):
        raise CrossoverPhotoAnalysisError(
            "partial blocks are not ordered CS1-left then CS2-right"
        )
    intersection_area, _intersection = cv2.intersectConvexConvex(
        corners_by_controller["CS1"].astype(np.float32),
        corners_by_controller["CS2"].astype(np.float32),
    )
    if float(intersection_area) > 1.0:
        raise CrossoverPhotoAnalysisError("partial CS1/CS2 blocks overlap")

    combined_area_fraction = sum(block_areas.values()) / float(
        photo_width * photo_height
    )
    if combined_area_fraction < PARTIAL_MIN_COMBINED_AREA_FRACTION:
        raise CrossoverPhotoAnalysisError(
            "partial controller blocks are too small for admitted sampling"
        )

    homographies: dict[str, Any] = {}
    minimum_cell_side = math.inf
    minimum_cell_area = math.inf
    selected_cells = [
        cell
        for cell in _all_logical_cells()
        if cell["row"] in PARTIAL_SELECTED_ROWS
    ]
    if len(selected_cells) != PARTIAL_SELECTED_CELL_COUNT:
        raise CrossoverPhotoAnalysisError("partial selected-cell count differs")

    for controller_index, controller in enumerate(("CS1", "CS2")):
        logical_x0 = controller_index * CONTROLLER_WIDTH + pack.GRID_X0
        logical_x1 = (
            logical_x0
            + (pack.GRID_COLUMNS - 1) * (pack.CELL_WIDTH + pack.GAP_X)
            + pack.CELL_WIDTH
        )
        logical_y0 = pack.GRID_Y_BY_ROW[PARTIAL_SELECTED_ROWS[0]]
        logical_y1 = (
            pack.GRID_Y_BY_ROW[PARTIAL_SELECTED_ROWS[-1]] + pack.CELL_HEIGHT
        )
        source = np.asarray(
            [
                [logical_x0, logical_y0],
                [logical_x1, logical_y0],
                [logical_x1, logical_y1],
                [logical_x0, logical_y1],
            ],
            dtype=np.float32,
        )
        homography = cv2.getPerspectiveTransform(
            source, corners_by_controller[controller].astype(np.float32)
        ).astype(np.float64)
        if (
            not np.all(np.isfinite(homography))
            or abs(float(np.linalg.det(homography))) < 1e-12
        ):
            raise CrossoverPhotoAnalysisError(
                f"{controller} partial homography is singular"
            )
        homographies[controller] = homography
        for cell in selected_cells:
            if cell["controller"] != controller_index:
                continue
            x, y, width, height = cell["logical_bounds"]
            projected = base._project(  # noqa: SLF001
                homography,
                (
                    (x, y),
                    (x + width, y),
                    (x + width, y + height),
                    (x, y + height),
                ),
            )
            if not np.all(
                (projected[:, 0] >= 0)
                & (projected[:, 0] < photo_width)
                & (projected[:, 1] >= 0)
                & (projected[:, 1] < photo_height)
            ):
                raise CrossoverPhotoAnalysisError(
                    f"{cell['cell_id']} projected partial bounds leave the photo"
                )
            sides = [
                float(
                    np.linalg.norm(projected[(index + 1) % 4] - projected[index])
                )
                for index in range(4)
            ]
            area = abs(float(cv2.contourArea(projected.astype(np.float32))))
            minimum_cell_side = min(minimum_cell_side, min(sides))
            minimum_cell_area = min(minimum_cell_area, area)

    if minimum_cell_side < PARTIAL_MIN_PROJECTED_CELL_SIDE_PX:
        raise CrossoverPhotoAnalysisError(
            "projected partial cells are too narrow for sampling"
        )
    if minimum_cell_area < PARTIAL_MIN_PROJECTED_CELL_AREA_PX2:
        raise CrossoverPhotoAnalysisError(
            "projected partial cells have insufficient sample area"
        )

    counts: dict[tuple[int, int], int] = defaultdict(int)
    for cell in selected_cells:
        counts[(int(cell["controller"]), int(cell["code"]))] += 1
    if any(
        counts[(controller, code)]
        != PARTIAL_REPLICATES_PER_CODE_PER_CONTROLLER
        for controller in range(CONTROLLER_COUNT)
        for code in range(8)
    ):
        raise CrossoverPhotoAnalysisError(
            "partial rows do not supply three replicates per controller/code"
        )

    return homographies, {
        "source": "EXPLICIT_CURRENT_PHOTO_DUAL_CONTROLLER_TOP_3X8_BLOCKS",
        "mode": PARTIAL_MODE,
        "historical_g1_homography_reused": False,
        "logical_coordinate_convention": "MF1750 full panel 1024x600",
        "selected_rows": list(PARTIAL_SELECTED_ROWS),
        "selected_columns": list(PARTIAL_SELECTED_COLUMNS),
        "selected_cell_count": PARTIAL_SELECTED_CELL_COUNT,
        "replicates_per_code_per_controller_per_frame": (
            PARTIAL_REPLICATES_PER_CODE_PER_CONTROLLER
        ),
        "supplied_block_corners_tl_tr_br_bl": {
            controller: [
                [round(float(component), 6) for component in row]
                for row in corners_by_controller[controller].tolist()
            ]
            for controller in ("CS1", "CS2")
        },
        "homography_logical_to_current_photo_by_controller": {
            controller: [
                [round(float(component), 12) for component in row]
                for row in homographies[controller].tolist()
            ]
            for controller in ("CS1", "CS2")
        },
        "combined_block_area_fraction_of_photo": round(
            combined_area_fraction, 9
        ),
        "minimum_required_combined_block_area_fraction": (
            PARTIAL_MIN_COMBINED_AREA_FRACTION
        ),
        "minimum_block_side_px": round(float(minimum_block_side), 6),
        "minimum_required_block_side_px": PARTIAL_MIN_BLOCK_SIDE_PX,
        "maximum_block_aspect_ratio": round(float(maximum_block_aspect), 6),
        "maximum_allowed_block_aspect_ratio": PARTIAL_MAX_BLOCK_ASPECT_RATIO,
        "minimum_projected_cell_side_px": round(float(minimum_cell_side), 6),
        "minimum_required_projected_cell_side_px": (
            PARTIAL_MIN_PROJECTED_CELL_SIDE_PX
        ),
        "minimum_projected_cell_area_px2": round(float(minimum_cell_area), 6),
        "minimum_required_projected_cell_area_px2": (
            PARTIAL_MIN_PROJECTED_CELL_AREA_PX2
        ),
        "all_projected_selected_cells_inside_photo": True,
        "automatic_full_cell_lattice_reprojection_proven": False,
        "full_panel_geometry_evaluated": False,
        "outside_selected_roi": "NOT_EVALUATED_OUTSIDE_SELECTED_ROI",
        "sampling_geometry_admitted": True,
    }


def _position_category(maximum_de00: float) -> str:
    if maximum_de00 < POSITION_SIMILAR_DE00:
        return "NO_OBVIOUS_POSITION_DIFFERENCE_IN_THIS_CAPTURE"
    if maximum_de00 < POSITION_OBVIOUS_DE00:
        return "BORDERLINE_POSITION_DEPENDENCE_CANDIDATE"
    return "OBVIOUS_POSITION_DEPENDENCE_CANDIDATE"


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        raise CrossoverPhotoAnalysisError("cannot take a percentile of no values")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _comparison_codes(
    *, stage: pack.Stage, cells: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Project rich cell records into the comparator's exact code schema."""

    _cv2, np = base._import_cv()  # noqa: SLF001
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for cell in cells:
        grouped[(cell["controller"], cell["code"])].append(cell)
    profiles = {
        0: pack.STAGES[stage].cs1_profile,
        1: pack.STAGES[stage].cs2_profile,
    }
    result: list[dict[str, Any]] = []
    for code in range(8):
        controllers: list[dict[str, Any]] = []
        for controller in range(CONTROLLER_COUNT):
            samples = sorted(
                grouped[(controller, code)],
                key=lambda item: (item["row"], item["column"]),
            )
            if len(samples) != 4:
                raise CrossoverPhotoAnalysisError(
                    f"controller {controller} code {code} does not have four positions"
                )
            positions = [
                {
                    "row": int(item["row"]),
                    "column": int(item["column"]),
                    "camera_relative_lab": [
                        round(float(component), 6)
                        for component in item["camera_relative_lab_d65_from_rgb_median"]
                    ],
                }
                for item in samples
            ]
            labs = np.asarray(
                [item["camera_relative_lab"] for item in positions],
                dtype=np.float64,
            )
            center = np.median(labs, axis=0)
            dispersions = [float(np.linalg.norm(sample - center)) for sample in labs]
            controllers.append(
                {
                    "controller": controller,
                    "profile": profiles[controller],
                    "positions": positions,
                    "center_lab": [
                        round(float(component), 9) for component in center.tolist()
                    ],
                    "position_dispersion_de76": [
                        round(value, 9) for value in dispersions
                    ],
                    "position_dispersion_p95_de76": round(
                        _percentile(dispersions, 0.95), 9
                    ),
                }
            )
        result.append({"code": code, "controllers": controllers})
    return result


def _comparison_projection(
    *,
    stage: pack.Stage,
    action_identity: Mapping[str, Any],
    camera_lock: Mapping[str, Any],
    geometry: Mapping[str, Any],
    cells: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return the exact stable projection consumed by the T1/T2 comparator."""

    camera_lock_id = base._sha256_bytes(  # noqa: SLF001
        base._canonical_json(dict(camera_lock))  # noqa: SLF001
    )
    return {
        "stage": stage,
        "campaign_id": action_identity["campaign_id"],
        "contract_id": action_identity["contract_id"],
        "action_id": action_identity["action_id"],
        "frame_sha256": action_identity["frame_sha256"],
        "cs1_dtm_sha256": action_identity["cs1_dtm_sha256"],
        "cs2_dtm_sha256": action_identity["cs2_dtm_sha256"],
        "layout": {
            "id": pack.layout.VARIANT_KEY,
            "controller_count": CONTROLLER_COUNT,
            "rows": pack.GRID_ROWS,
            "columns_per_controller": pack.GRID_COLUMNS,
            "row_codes": [list(row) for row in pack.CODE_ROWS],
            "positions_per_code_per_controller": 4,
            "same_dtm_both_controllers": True,
        },
        "geometry": {
            "valid": True,
            "fixed_camera": True,
            "camera_lock_id": camera_lock_id,
            "homography_logical_to_photo": geometry[
                "homography_logical_to_current_photo"
            ],
            "sampling_geometry_admitted": geometry["sampling_geometry_admitted"],
            "historical_g1_homography_reused": geometry[
                "historical_g1_homography_reused"
            ],
            "all_projected_cells_inside_photo": geometry[
                "all_projected_cells_inside_photo"
            ],
            "automatic_cell_lattice_reprojection_proven": geometry[
                "automatic_cell_lattice_reprojection_proven"
            ],
            "panel_area_fraction_of_photo": geometry["panel_area_fraction_of_photo"],
            "minimum_required_panel_area_fraction": geometry[
                "minimum_required_panel_area_fraction"
            ],
            "minimum_projected_cell_side_px": geometry[
                "minimum_projected_cell_side_px"
            ],
            "minimum_required_projected_cell_side_px": geometry[
                "minimum_required_projected_cell_side_px"
            ],
        },
        "codes": _comparison_codes(stage=stage, cells=cells),
    }


def _position_summary(cells: list[dict[str, Any]]) -> dict[str, Any]:
    _cv2, np = base._import_cv()  # noqa: SLF001
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    by_position: dict[tuple[int, int, int], dict[str, Any]] = {}
    for cell in cells:
        grouped[(cell["controller"], cell["code"])].append(cell)
        by_position[(cell["controller"], cell["row"], cell["column"])] = cell

    controller_code_groups: list[dict[str, Any]] = []
    for controller in range(CONTROLLER_COUNT):
        for code in range(8):
            samples = sorted(
                grouped[(controller, code)],
                key=lambda item: (item["row"], item["column"]),
            )
            if len(samples) != 4:
                raise CrossoverPhotoAnalysisError(
                    f"controller {controller} code {code} does not have four positions"
                )
            labs = np.asarray(
                [item["camera_relative_lab_d65_from_rgb_median"] for item in samples],
                dtype=np.float64,
            )
            reference = np.median(labs, axis=0)
            delta_e = [float(delta_e_ciede2000(sample, reference)) for sample in labs]
            maximum = max(delta_e)
            controller_code_groups.append(
                {
                    "controller": controller,
                    "code": code,
                    "sample_count": 4,
                    "cell_ids": [item["cell_id"] for item in samples],
                    "camera_relative_lab_component_median": [
                        round(float(component), 6) for component in reference.tolist()
                    ],
                    "delta_e00_to_group_median": [round(value, 6) for value in delta_e],
                    "maximum_delta_e00_to_group_median": round(maximum, 6),
                    "heuristic_category": _position_category(maximum),
                    "qualification_effect": "NONE",
                }
            )

    pairs: list[dict[str, Any]] = []
    for row in range(pack.GRID_ROWS):
        for column in range(pack.GRID_COLUMNS):
            left = by_position[(0, row, column)]
            right = by_position[(1, row, column)]
            left_lab = left["camera_relative_lab_d65_from_rgb_median"]
            right_lab = right["camera_relative_lab_d65_from_rgb_median"]
            de00 = float(delta_e_ciede2000(left_lab, right_lab))
            pairs.append(
                {
                    "row": row,
                    "column": column,
                    "code": left["code"],
                    "left_cell_id": left["cell_id"],
                    "right_cell_id": right["cell_id"],
                    "delta_e00_camera_relative": round(de00, 6),
                    "delta_e76_camera_relative": round(
                        float(math.dist(left_lab, right_lab)), 6
                    ),
                    "qualification_effect": "NONE",
                }
            )
    largest_pair = max(pairs, key=lambda item: item["delta_e00_camera_relative"])
    largest_group = max(
        controller_code_groups,
        key=lambda item: item["maximum_delta_e00_to_group_median"],
    )
    return {
        "samples_per_code_per_controller": 4,
        "controller_code_groups": controller_code_groups,
        "same_position_controller_pairs": pairs,
        "largest_position_dependence_candidate": largest_group,
        "largest_same_position_controller_difference": largest_pair,
        "heuristic_thresholds_delta_e00": {
            "similar_exclusive": POSITION_SIMILAR_DE00,
            "obvious_inclusive": POSITION_OBVIOUS_DE00,
        },
        "position_balance_proven": False,
        "controller_equivalence_proven": False,
        "reason": (
            "one locked retained frame can flag camera-relative candidates only; "
            "repeat captures and cross-stage controls are still required"
        ),
    }


def analyze(
    *,
    stage: pack.Stage,
    photo_path: Path,
    capture_sidecar_path: Path,
    action_result_path: Path,
    panel_corners: str | Any,
) -> dict[str, Any]:
    """Deep-validate and analyze one frozen-stage crossover atlas capture."""

    photo_path = Path(photo_path).resolve()
    capture_sidecar_path = Path(capture_sidecar_path).resolve()
    action_result_path = Path(action_result_path).resolve()
    try:
        capture_root = camera.validate_capture_evidence(capture_sidecar_path)
    except camera.CameraCaptureEvidenceError as error:
        raise CrossoverPhotoAnalysisError(
            f"formal capture evidence rejected: {error}"
        ) from error
    camera_lock = base._validate_fixed_capture(capture_root)  # noqa: SLF001
    action_payload, action_root = base._load_json(  # noqa: SLF001
        action_result_path, label="action result"
    )
    action_identity = _validate_action(stage, action_root)

    sidecar_action = base._mapping(  # noqa: SLF001
        capture_root.get("action_result"), label="capture.action_result"
    )
    sidecar_photo = base._mapping(  # noqa: SLF001
        capture_root.get("photo"), label="capture.photo"
    )
    resolved_action = (
        capture_sidecar_path.parent / str(sidecar_action.get("path"))
    ).resolve()
    resolved_photo = (
        capture_sidecar_path.parent / str(sidecar_photo.get("path"))
    ).resolve()
    if resolved_action != action_result_path or resolved_photo != photo_path:
        raise CrossoverPhotoAnalysisError(
            "explicit photo/action paths differ from formal capture bindings"
        )
    photo_payload = base._read_stable_regular(photo_path, label="formal photo")  # noqa: SLF001
    if sidecar_photo.get("sha256") != base._sha256_bytes(  # noqa: SLF001
        photo_payload
    ) or sidecar_action.get("file_sha256") != base._sha256_bytes(action_payload):  # noqa: SLF001
        raise CrossoverPhotoAnalysisError(
            "formal crossover photo/action SHA-256 binding differs"
        )
    for field in (
        "campaign_id",
        "test_id",
        "contract_id",
        "firmware_sha256",
        "action_id",
        "descriptor_id",
        "role",
        "frame_sha256",
    ):
        if capture_root.get(field) != action_identity[field]:
            raise CrossoverPhotoAnalysisError(
                f"capture sidecar {field} differs from exact {stage} binding"
            )

    rgb = base._decode_rgb(photo_payload)  # noqa: SLF001
    homography, geometry = _fit_panel_homography(
        panel_corners, photo_width=rgb.shape[1], photo_height=rgb.shape[0]
    )
    cells = [
        base._sample_cell(rgb, homography, cell)  # noqa: SLF001
        for cell in _all_logical_cells()
    ]
    summary = _position_summary(cells)
    comparison_projection = _comparison_projection(
        stage=stage,
        action_identity=action_identity,
        camera_lock=camera_lock,
        geometry=geometry,
        cells=cells,
    )
    sidecar_payload = base._read_stable_regular(  # noqa: SLF001
        capture_sidecar_path, label="capture sidecar"
    )
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "stage": stage,
        "campaign_id": action_identity["campaign_id"],
        "contract_id": action_identity["contract_id"],
        "action_id": action_identity["action_id"],
        "frame_sha256": action_identity["frame_sha256"],
        "cs1_dtm_sha256": action_identity["cs1_dtm_sha256"],
        "cs2_dtm_sha256": action_identity["cs2_dtm_sha256"],
        "source_evidence": {
            "photo": {
                "path": str(photo_path),
                "bytes": len(photo_payload),
                "sha256": base._sha256_bytes(photo_payload),  # noqa: SLF001
                "width": rgb.shape[1],
                "height": rgb.shape[0],
            },
            "capture_sidecar": {
                "path": str(capture_sidecar_path),
                "bytes": len(sidecar_payload),
                "sha256": base._sha256_bytes(sidecar_payload),  # noqa: SLF001
                "canonical_integrity_sha256": base._sha256(  # noqa: SLF001
                    base._mapping(  # noqa: SLF001
                        capture_root.get("integrity"), label="capture.integrity"
                    ).get("sha256"),
                    label="capture.integrity.sha256",
                ),
            },
            "action_result": {
                "path": str(action_result_path),
                "bytes": len(action_payload),
                "sha256": base._sha256_bytes(action_payload),  # noqa: SLF001
                "canonical_integrity_sha256": base._sha256(  # noqa: SLF001
                    base._mapping(  # noqa: SLF001
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
            "rows_per_controller": pack.GRID_ROWS,
            "columns_per_controller": pack.GRID_COLUMNS,
            "row_codes": [list(row) for row in pack.CODE_ROWS],
            "samples_per_code_per_controller": 4,
            "same_layout_both_controllers": True,
            "spatial_dither": False,
            "legacy_endpoint_4x2_analyzer_used": False,
        },
        "geometry": geometry,
        "measurement_method": {
            "rgb_statistic": "per-channel median over projected inner 60% polygon",
            "spread_statistic": "per-channel median absolute deviation",
            "lab_derivation": "camera JPEG RGB interpreted as sRGB D65/2deg Lab",
            "delta_e": "CIEDE2000 plus Delta-E76",
            "physical_colour_calibrated": False,
            "absolute_colour_measurement": False,
            "repeatability_measurement": False,
        },
        "cells": cells,
        "position_balanced_summary": summary,
        "comparison_projection": comparison_projection,
        "classification": {
            "state": "CAMERA_RELATIVE_CROSSOVER_POSITION_COMPARISON_ONLY",
            "camera_relative_candidates_only": True,
            "absolute_colour_proven": False,
            "stable_colour_proven": False,
            "repeatable_colour_proven": False,
            "qualified_new_colour": False,
            "qualified_colour_count": 0,
            "cross_stage_equivalence_proven": False,
        },
        "hardware_io_performed_by_analyzer": False,
        "camera_access_performed_by_analyzer": False,
        "visible_refresh_authorized": False,
        "output_write_contract": "O_EXCL",
    }
    result["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": base._sha256_bytes(base._canonical_json(result)),  # noqa: SLF001
    }
    return result


def _render_overlay(photo_payload: bytes, report: Mapping[str, Any]) -> bytes:
    cv2, np = base._import_cv()  # noqa: SLF001
    rgb = base._decode_rgb(photo_payload)  # noqa: SLF001
    canvas = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    geometry = base._mapping(report.get("geometry"), label="report.geometry")  # noqa: SLF001
    homography = np.asarray(
        geometry.get("homography_logical_to_current_photo"), dtype=np.float64
    )
    for cell in _all_logical_cells():
        x, y, width, height = cell["logical_bounds"]
        polygon = np.rint(
            base._project(  # noqa: SLF001
                homography,
                ((x, y), (x + width, y), (x + width, y + height), (x, y + height)),
            )
        ).astype(np.int32)
        colour = (255, 255, 0) if cell["controller"] == 0 else (0, 165, 255)
        cv2.polylines(canvas, [polygon], True, colour, 3, cv2.LINE_AA)
        center = np.rint(
            base._project(homography, (cell["logical_center"],))[0]  # noqa: SLF001
        ).astype(int)
        cv2.putText(
            canvas,
            str(cell["code"]),
            (int(center[0]) - 8, int(center[1]) + 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )
    encoded, buffer = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not encoded:
        raise CrossoverPhotoAnalysisError("crossover overlay JPEG encoding failed")
    return bytes(buffer)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--stage", choices=tuple(pack.STAGES), required=True)
    parser.add_argument("--photo", type=Path, required=True)
    parser.add_argument("--capture-sidecar", type=Path, required=True)
    parser.add_argument("--action-result", type=Path, required=True)
    parser.add_argument(
        "--panel-corners",
        required=True,
        help="current-photo TLx,TLy;TRx,TRy;BRx,BRy;BLx,BLy",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overlay-output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = analyze(
            stage=args.stage,
            photo_path=args.photo,
            capture_sidecar_path=args.capture_sidecar,
            action_result_path=args.action_result,
            panel_corners=args.panel_corners,
        )
        base._write_exclusive(args.output, report)  # noqa: SLF001
        if args.overlay_output is not None:
            payload = base._read_stable_regular(args.photo, label="formal photo")  # noqa: SLF001
            base._write_bytes_exclusive(  # noqa: SLF001
                args.overlay_output,
                _render_overlay(payload, report),
                label="crossover geometry overlay",
            )
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False))
    except CrossoverPhotoAnalysisError as error:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "kind": "mf1750-raw-p16-crossover-photo-analysis-error",
                    "valid": False,
                    "error": str(error),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
