from __future__ import annotations

import numpy as np

from tools import mf1750_stable_code0_luma_latin_v3_photo_analyzer as analyzer


def test_bottom_edge_classifier_requires_dark_bottom_specific_excess() -> None:
    assert (
        analyzer.classify_bottom_edge_stripe(
            bottom_delta_l_star=-5.0,
            bottom_de76_excess=3.0,
        )
        == "PRESENT"
    )
    assert (
        analyzer.classify_bottom_edge_stripe(
            bottom_delta_l_star=-3.0,
            bottom_de76_excess=1.5,
        )
        == "UNCERTAIN"
    )
    assert (
        analyzer.classify_bottom_edge_stripe(
            bottom_delta_l_star=5.0,
            bottom_de76_excess=8.0,
        )
        == "CLEAR"
    )


def test_controller_local_white_normalization_removes_local_lab_offset() -> None:
    cells = []
    for index, offset in enumerate((0.0, 5.0, -4.0)):
        separator = np.array([50.0 + offset, 2.0 + offset, -3.0 + offset])
        cells.append(
            {
                "row": index,
                "column": 0,
                "center_lab": separator + np.array([-20.0, 8.0, 4.0]),
                "separator_lab": separator,
            }
        )
    normalized = analyzer._normalise_controller_cells(cells)  # noqa: SLF001
    values = [
        item["illumination_normalized_camera_relative_lab"]
        for item in normalized["cells"]
    ]
    assert np.allclose(values[0], values[1])
    assert np.allclose(values[1], values[2])


def _synthetic_cells(controller: int) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for row in range(8):
        for column in range(8):
            code = analyzer.pack.middle_code(controller, row, column)
            result.append(
                {
                    "controller": controller,
                    "row": row,
                    "column": column,
                    "illumination_normalized_camera_relative_lab": np.array(
                        [30.0 + code, 20.0, 5.0]
                    ),
                    "bottom_edge_stripe": "CLEAR",
                }
            )
    return result


def test_controller_summary_accepts_repeatable_same_hue_luma_ladder() -> None:
    summary = analyzer._controller_summary(1, _synthetic_cells(1))  # noqa: SLF001
    assert summary["between_middle_median_delta_l_star"] == 7.0
    assert summary["same_hue_gate_pass"] is True
    assert summary["position_repeat_gate_pass"] is True
    assert summary["strict_luma_mechanism_review_candidate"] is True
    assert summary["bottom_edge_stripe_counts"] == {
        "CLEAR": 64,
        "PRESENT": 0,
        "UNCERTAIN": 0,
    }


def test_controller_summary_does_not_pool_other_controller() -> None:
    cs1 = _synthetic_cells(0)
    cs2 = _synthetic_cells(1)
    for item in cs2:
        item["illumination_normalized_camera_relative_lab"] = np.array(
            [80.0, -20.0, 30.0]
        )
    summary = analyzer._controller_summary(0, cs1)  # noqa: SLF001
    assert summary["controller"] == "CS1"
    assert summary["controller_local_only"] is True
    assert summary["between_middle_median_delta_l_star"] == 7.0


def _json_repeat_cells(controller: int, *, offset: float = 0.0) -> list[dict[str, object]]:
    result = []
    for item in _synthetic_cells(controller):
        result.append(
            {
                "controller": f"CS{controller + 1}",
                "physical_row": item["row"],
                "physical_column": item["column"],
                "illumination_normalized_camera_relative_lab": (
                    np.asarray(item["illumination_normalized_camera_relative_lab"])
                    + np.array([offset, 0.0, 0.0])
                ).tolist(),
            }
        )
    return result


def test_repeat_comparison_removes_controller_wide_exposure_offset() -> None:
    l3 = _json_repeat_cells(1)
    l4 = _json_repeat_cells(1, offset=18.0)
    result = analyzer._controller_repeat_comparison("CS2", l3, l4)  # noqa: SLF001
    assert result["raw_controller_median_delta_lab"][0] == 18.0
    assert result["centered_cell_absolute_delta_l_star"]["maximum"] == 0.0
    assert result["maximum_middle_code_centered_median_delta_l_star"] == 0.0
    assert result["middle_code_centered_lightness_pearson"] == 1.0
    assert result["l4_over_l3_middle_code_span_retention"] == 1.0
    assert result["centered_lightness_repeat_gate_pass"] is True


def test_repeat_comparison_rejects_changed_middle_code_shape() -> None:
    l3 = _json_repeat_cells(1)
    l4 = _json_repeat_cells(1)
    for item in l4:
        row = int(item["physical_row"])
        column = int(item["physical_column"])
        code = analyzer.pack.middle_code(1, row, column)
        item["illumination_normalized_camera_relative_lab"][0] += (code % 2) * 8.0
    result = analyzer._controller_repeat_comparison("CS2", l3, l4)  # noqa: SLF001
    assert result["centered_lightness_repeat_gate_pass"] is False


def _camera_binding(exposure: float) -> dict[str, dict[str, object]]:
    return {
        "requested_settings": {"exposure": exposure, "focus": 79.0},
        "effective_settings_before_frame": {"exposure": int(exposure), "focus": 79},
        "effective_settings_after_frame": {"exposure": int(exposure), "focus": 79},
    }


def test_camera_comparability_requires_all_three_setting_records() -> None:
    same = analyzer._camera_settings_comparability(  # noqa: SLF001
        _camera_binding(-4.0), _camera_binding(-4.0)
    )
    assert same["camera_settings_exactly_equal"] is True
    assert same["camera_exposure_equal"] is True

    different = analyzer._camera_settings_comparability(  # noqa: SLF001
        _camera_binding(-6.0), _camera_binding(-4.0)
    )
    assert different["camera_settings_exactly_equal"] is False
    assert different["camera_settings_except_exposure_equal"] is True
    assert different["camera_exposure_equal"] is False
