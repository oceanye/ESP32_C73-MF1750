from __future__ import annotations

import copy
from collections import Counter

import numpy as np
import pytest

from tools import mf1750_raw_p16_crossover_position_balanced_pack as pack
from tools import mf1750_raw_p16_crossover_position_balanced_photo_analyzer as analyzer
from tools import mf1750_raw_p16_retained_atlas_photo_analyzer as endpoint


def _action_result(stage: pack.Stage) -> dict:
    cfg = pack.STAGES[stage]
    report = pack.build_report(stage)
    expected = report["actions"][0]
    return {
        "kind": f"mf1750-ec5-{cfg.route_slug}-result",
        "outcome": "complete_pass",
        "visible_refreshes": 1,
        "firmware_sha256": pack.ARTIFACTS[stage]["bin_sha256"],
        "action": analyzer._runtime_action(expected),
        "terminal_report": {
            "terminal_state": "COMPLETE",
            "result": True,
            "valid": True,
            "campaign_id": cfg.campaign_id,
            "test_id": cfg.test_id,
            "contract_id": report["contract_id"],
            "build_tag": cfg.build_tag,
            "action_id": expected["action_id"],
            "descriptor_id": expected["descriptor_id"],
            "ordinal": 1,
            "role": expected["role"],
            "driver_called": True,
            "driver_call_count_for_action": 1,
            "driver": {
                "valid": True,
                "sequence_ok": True,
                "wait_timeout": False,
                "failure_stage": "none",
            },
        },
    }


def test_new_layout_is_4x8_per_controller_without_changing_old_4x2() -> None:
    cells = analyzer._all_logical_cells()

    assert len(cells) == 64
    assert len(endpoint._all_logical_cells()) == 16
    assert [item["code"] for item in cells[:8]] == list(pack.CODE_ROWS[0])
    assert [item["code"] for item in cells[32:40]] == list(pack.CODE_ROWS[0])
    counts = Counter((item["controller"], item["code"]) for item in cells)
    assert set(counts.values()) == {4}
    assert all(item["position_index_for_code"] in range(4) for item in cells)
    assert cells[0]["logical_bounds"] == [20, 44, 52, 100]
    assert cells[32]["logical_bounds"] == [532, 44, 52, 100]


@pytest.mark.parametrize("stage", tuple(pack.STAGES))
def test_each_stage_requires_its_exact_action_contract_and_profile(
    stage: pack.Stage,
) -> None:
    result = _action_result(stage)

    identity = analyzer._validate_action(stage, result)

    expected = pack.build_report(stage)["actions"][0]
    assert identity["stage"] == stage
    assert identity["action_id"] == expected["action_id"]
    assert identity["profile_id"] == expected["profile_id"]
    assert identity["global_tuple_id"] == expected["global_tuple_id"]
    assert identity["waveform_binding"] == expected["waveform_binding"]


def test_stage_cross_binding_and_profile_mutation_fail_closed() -> None:
    t1 = _action_result("t1-ac")

    with pytest.raises(analyzer.CrossoverPhotoAnalysisError, match="t2-ca action"):
        analyzer._validate_action("t2-ca", t1)

    changed_profile = copy.deepcopy(t1)
    changed_profile["action"]["profile_id"] = pack.build_report("t2-ca")["actions"][0][
        "profile_id"
    ]
    with pytest.raises(
        analyzer.CrossoverPhotoAnalysisError, match="profile_id differs"
    ):
        analyzer._validate_action("t1-ac", changed_profile)

    changed_binding = copy.deepcopy(t1)
    changed_binding["action"]["waveform_binding"]["cs1"]["name"] = "commented"
    with pytest.raises(
        analyzer.CrossoverPhotoAnalysisError, match="waveform_binding differs"
    ):
        analyzer._validate_action("t1-ac", changed_binding)


def test_current_photo_corners_sample_all_four_positions_per_code() -> None:
    cv2, _np = analyzer.base._import_cv()
    rgb = np.full((3000, 4000, 3), 235, dtype=np.uint8)
    corners = np.asarray(
        [[500, 400], [3500, 500], [3400, 2600], [600, 2500]],
        dtype=np.float64,
    )
    homography, geometry = analyzer._fit_panel_homography(
        corners, photo_width=4000, photo_height=3000
    )
    colours = {
        code: (20 + code * 20, 35 + code * 15, 50 + code * 10) for code in range(8)
    }
    for cell in analyzer._all_logical_cells():
        x, y, width, height = cell["logical_bounds"]
        polygon = analyzer.base._project(
            homography,
            ((x, y), (x + width, y), (x + width, y + height), (x, y + height)),
        )
        cv2.fillConvexPoly(
            rgb,
            np.rint(polygon).astype(np.int32),
            colours[cell["code"]],
        )

    cells = [
        analyzer.base._sample_cell(rgb, homography, cell)
        for cell in analyzer._all_logical_cells()
    ]
    summary = analyzer._position_summary(cells)
    action_identity = analyzer._validate_action("t1-ac", _action_result("t1-ac"))
    projection = analyzer._comparison_projection(
        stage="t1-ac",
        action_identity=action_identity,
        camera_lock={"mount_id": "fixed", "exposure": -6},
        geometry=geometry,
        cells=cells,
    )

    assert geometry["historical_g1_homography_reused"] is False
    assert geometry["automatic_cell_lattice_reprojection_proven"] is False
    assert geometry["sampling_geometry_admitted"] is True
    assert len(cells) == 64
    assert len(summary["controller_code_groups"]) == 16
    assert len(summary["same_position_controller_pairs"]) == 32
    assert all(item["sample_count"] == 4 for item in summary["controller_code_groups"])
    assert all(
        item["maximum_delta_e00_to_group_median"] < 0.1
        for item in summary["controller_code_groups"]
    )
    assert set(projection) == {
        "stage",
        "campaign_id",
        "contract_id",
        "action_id",
        "frame_sha256",
        "cs1_dtm_sha256",
        "cs2_dtm_sha256",
        "layout",
        "geometry",
        "codes",
    }
    assert projection["layout"] == {
        "id": pack.layout.VARIANT_KEY,
        "controller_count": 2,
        "rows": 4,
        "columns_per_controller": 8,
        "row_codes": [list(row) for row in pack.CODE_ROWS],
        "positions_per_code_per_controller": 4,
        "same_dtm_both_controllers": True,
    }
    assert set(projection["geometry"]) == {
        "valid",
        "fixed_camera",
        "camera_lock_id",
        "homography_logical_to_photo",
        "sampling_geometry_admitted",
        "historical_g1_homography_reused",
        "all_projected_cells_inside_photo",
        "automatic_cell_lattice_reprojection_proven",
        "panel_area_fraction_of_photo",
        "minimum_required_panel_area_fraction",
        "minimum_projected_cell_side_px",
        "minimum_required_projected_cell_side_px",
    }
    assert len(projection["codes"]) == 8
    assert projection["codes"][0]["code"] == 0
    assert [
        (item["row"], item["column"])
        for item in projection["codes"][0]["controllers"][0]["positions"]
    ] == [(0, 0), (1, 2), (2, 5), (3, 7)]
    assert projection["codes"][0]["controllers"][0]["profile"] == "active"
    assert projection["codes"][0]["controllers"][1]["profile"] == "commented"


def _partial_blocks() -> dict[str, list[list[float]]]:
    return {
        "CS1": [[500, 400], [1800, 400], [1800, 1500], [500, 1500]],
        "CS2": [[2200, 400], [3500, 400], [3500, 1500], [2200, 1500]],
    }


def test_independent_partial_geometry_maps_exact_dual_3x8_selected_cells() -> None:
    homographies, report = analyzer._fit_partial_dual_controller_blocks(  # noqa: SLF001
        _partial_blocks(), photo_width=4000, photo_height=3000
    )
    selected = [
        cell
        for cell in analyzer._all_logical_cells()  # noqa: SLF001
        if cell["row"] in analyzer.PARTIAL_SELECTED_ROWS
    ]
    counts = Counter((item["controller"], item["code"]) for item in selected)

    assert set(homographies) == {"CS1", "CS2"}
    assert len(selected) == 48
    assert set(counts.values()) == {3}
    assert report["mode"] == analyzer.PARTIAL_MODE
    assert report["selected_rows"] == [0, 1, 2]
    assert report["selected_columns"] == list(range(8))
    assert report["selected_cell_count"] == 48
    assert report["minimum_projected_cell_side_px"] >= 24.0
    assert report["minimum_projected_cell_area_px2"] >= 1500.0
    assert report["full_panel_geometry_evaluated"] is False
    assert report["outside_selected_roi"] == "NOT_EVALUATED_OUTSIDE_SELECTED_ROI"


@pytest.mark.parametrize(
    "blocks",
    (
        {"CS1": [[500, 400], [1800, 400], [1800, 1500], [500, 1500]]},
        {
            "CS1": [[500, 400], [1800, 400], [1800, 1500], [500, 1500]],
            "CS2": [[1200, 500], [2500, 500], [2500, 1600], [1200, 1600]],
        },
        {
            "CS1": [[500, 400], [700, 400], [700, 600], [500, 600]],
            "CS2": [[2200, 400], [2400, 400], [2400, 600], [2200, 600]],
        },
    ),
)
def test_partial_geometry_fails_closed_for_missing_overlap_or_small_blocks(
    blocks: dict,
) -> None:
    with pytest.raises(analyzer.CrossoverPhotoAnalysisError):
        analyzer._fit_partial_dual_controller_blocks(  # noqa: SLF001
            blocks, photo_width=4000, photo_height=3000
        )


def test_position_summary_flags_one_changed_position_without_qualifying_colour() -> (
    None
):
    cells = []
    for cell in analyzer._all_logical_cells():
        item = dict(cell)
        item["camera_relative_lab_d65_from_rgb_median"] = [50.0, 0.0, 0.0]
        if (
            item["controller"] == 1
            and item["code"] == 6
            and item["position_index_for_code"] == 2
        ):
            item["camera_relative_lab_d65_from_rgb_median"] = [72.0, 18.0, 10.0]
        cells.append(item)

    summary = analyzer._position_summary(cells)
    target = next(
        item
        for item in summary["controller_code_groups"]
        if item["controller"] == 1 and item["code"] == 6
    )

    assert target["heuristic_category"] == "OBVIOUS_POSITION_DEPENDENCE_CANDIDATE"
    assert target["qualification_effect"] == "NONE"
    assert summary["position_balance_proven"] is False
    assert summary["controller_equivalence_proven"] is False


@pytest.mark.parametrize(
    "corners",
    (
        "0,0;100,0;100,100",
        "0,0;0,100;100,100;100,0",
        "0,0;100,0;nan,100;0,100",
    ),
)
def test_current_photo_corners_fail_closed(corners: str) -> None:
    with pytest.raises(analyzer.CrossoverPhotoAnalysisError):
        analyzer._fit_panel_homography(corners, photo_width=4000, photo_height=3000)


def test_cli_stage_is_frozen_to_t1_t2_t3() -> None:
    args = analyzer.parse_args(
        [
            "--stage",
            "t3-ac-repeat",
            "--photo",
            "atlas.jpg",
            "--capture-sidecar",
            "atlas.capture.json",
            "--action-result",
            "action.json",
            "--panel-corners",
            "500,400;3500,500;3400,2600;600,2500",
            "--output",
            "analysis.json",
        ]
    )

    assert args.stage == "t3-ac-repeat"
