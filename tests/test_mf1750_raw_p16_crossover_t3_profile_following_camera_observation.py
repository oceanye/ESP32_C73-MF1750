from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

from tools import mf1750_camera_capture_evidence as camera
from tools import (
    mf1750_raw_p16_crossover_position_balanced_photo_analyzer as geometry,
)
from tools import (
    mf1750_raw_p16_crossover_profile_following_human_observation as human,
)
from tools import (
    mf1750_raw_p16_crossover_t3_profile_following_camera_observation as subject,
)
from tools import (
    mf1750_raw_p16_crossover_w3_discovery_successor_v2_white_pack as w3_pack,
)


WHITE_LEVEL = 180
PALETTE = {
    "CS1": (
        (80, 70, 30),
        (20, 20, 20),
        (30, 100, 30),
        (160, 160, 160),
        (130, 120, 50),
        (30, 50, 130),
        (140, 100, 30),
        (20, 20, 20),
    ),
    "CS2": (
        (130, 30, 30),
        (130, 60, 90),
        (30, 100, 30),
        (160, 160, 160),
        (100, 60, 30),
        (30, 50, 130),
        (120, 30, 80),
        (25, 25, 60),
    ),
}


def _logical_atlas(*, white_level: int = WHITE_LEVEL) -> np.ndarray:
    scale = white_level / WHITE_LEVEL
    panel = np.zeros(
        (geometry.LOGICAL_HEIGHT, geometry.LOGICAL_WIDTH, 3), dtype=np.uint8
    )
    for controller_index, controller in enumerate(human.CONTROLLERS):
        background = np.asarray(PALETTE[controller][7], dtype=float) * scale
        x0 = controller_index * geometry.CONTROLLER_WIDTH
        x1 = (controller_index + 1) * geometry.CONTROLLER_WIDTH
        panel[:, x0:x1] = np.rint(background).astype(np.uint8)
    for cell in geometry._all_logical_cells():  # noqa: SLF001
        x, y, width, height = cell["logical_bounds"]
        controller = f"CS{cell['controller'] + 1}"
        value = np.asarray(PALETTE[controller][cell["code"]], dtype=float) * scale
        panel[y : y + height, x : x + width] = np.rint(value).astype(np.uint8)
    return panel


def _white(level: int = WHITE_LEVEL) -> np.ndarray:
    return np.full(
        (geometry.LOGICAL_HEIGHT, geometry.LOGICAL_WIDTH, 3), level, dtype=np.uint8
    )


def _truthful_seed() -> dict:
    labels = {
        "CS1": ["olive", "black", "green", "white", "yellow", "blue", "gold", "navy"],
        "CS2": ["red", "pink", "green", "white", "brown", "blue", "magenta", "purple"],
    }
    return {
        "schema_version": subject.SCHEMA_VERSION,
        "kind": subject.SEED_KIND,
        "stage": human.AC_STAGE,
        "observed_at": "2026-08-31T10:00:00+08:00",
        "operator": {
            "operator_id": "operator-1",
            "operator_verbatim": "I inspected both sides and all four rows.",
        },
        "supervision": {
            "supervisor_id": "supervisor-1",
            "continuous_supervision": True,
            "action_complete_reviewed": True,
            "no_intervening_visible_refresh": True,
            "ambient_light_stable": True,
            "viewing_angle_stable": True,
            "display_stable_through_observation": True,
            "four_replicates_checked": True,
            "electrical_state_normal": True,
            "esp32_restart_observed": False,
            "j2_state_during_observation": "OFF",
            "supervision_verbatim": "Continuously supervised; J2 recorded OFF.",
        },
        "controls_verbatim": "Codes 2, 3, and 5 matched across the two sides.",
        "artifacts": {
            field: {"observed": False, "operator_verbatim": "Not observed."}
            for field in human.ARTIFACT_FIELDS
        },
        "controllers": {
            controller: {
                "code_labels_verbatim": labels[controller],
                "all_four_replicates_human_confirmed": True,
                "all_labels_stable_human_confirmed": True,
            }
            for controller in human.CONTROLLERS
        },
    }


def _fake_geometry(offset: float = 0.0) -> dict:
    return {
        "supplied_panel_corners_tl_tr_br_bl": [
            [500.0 + offset, 500.0],
            [3500.0 + offset, 500.0],
            [3500.0 + offset, 2500.0],
            [500.0 + offset, 2500.0],
        ]
    }


def test_clean_synthetic_panels_pass_all_decisive_camera_checks() -> None:
    atlas = _logical_atlas()
    result = subject.screen_logical_panels(
        _white(), [atlas, atlas.copy(), atlas.copy()]
    )

    assert result["diagnostic_state"] == subject.PASS
    assert result["machine_confidence"] == "HIGH"
    assert result["four_replicate_consistency"]["group_count"] == 48
    assert result["three_frame_temporal_stability"]["cell_count"] == 64
    assert len(result["frames"]) == 3
    assert all(len(frame["cells"]) == 64 for frame in result["frames"])
    assert (
        result["controls"]["maximum_cross_controller_delta_e00"]["diagnostic_state"]
        == subject.PASS
    )


def test_partial_dual_3x8_screen_compares_all_codes_but_earns_no_formal_claim() -> None:
    atlas = _logical_atlas()
    result = subject.screen_partial_logical_panels(
        _white(), [atlas, atlas.copy(), atlas.copy()]
    )

    assert result["mode"] == subject.PARTIAL_MODE
    assert result["selected_rows"] == [0, 1, 2]
    assert result["selected_columns"] == list(range(8))
    assert result["selected_cell_count_per_frame"] == 48
    assert result["three_replicate_consistency"]["group_count"] == 48
    assert all(
        group["replicate_count"] == 3
        for group in result["three_replicate_consistency"]["groups"]
    )
    assert result["three_frame_temporal_stability"]["cell_count"] == 48
    assert all(len(frame["cells"]) == 48 for frame in result["frames"])
    assert [item["code"] for item in result["profile_code_comparison"]] == list(
        range(8)
    )
    assert all(
        item["samples_per_profile"] == 9
        and item["formal_profile_following_effect"] == "NONE"
        for item in result["profile_code_comparison"]
    )
    assert result["artifacts"]["bottom_edge"] == {
        "diagnostic_state": "NOT_EVALUATED",
        "scope": "NOT_EVALUATED_OUTSIDE_SELECTED_ROI",
        "samples": [],
    }
    assert result["formal_full_panel_evidence"] is False
    assert result["profile_following_decision_earned"] is False
    assert result["w4_post_white_full_screen_seal_earned"] is False


def test_partial_screen_is_invariant_to_row3_and_bottom_pixels() -> None:
    atlas = _logical_atlas()
    baseline = subject.screen_partial_logical_panels(
        _white(), [atlas, atlas.copy(), atlas.copy()]
    )
    changed = atlas.copy()
    changed[452:600, :] = (255, 0, 255)
    observed = subject.screen_partial_logical_panels(
        _white(), [atlas, changed, atlas.copy()]
    )

    assert observed == baseline
    assert observed["outside_roi"] == "NOT_EVALUATED_OUTSIDE_SELECTED_ROI"


def test_partial_geometry_drift_rejects_rms_or_max_without_expanding_roi() -> None:
    base = {
        "supplied_block_corners_tl_tr_br_bl": {
            "CS1": [[500.0, 400.0], [1800.0, 400.0], [1800.0, 1500.0], [500.0, 1500.0]],
            "CS2": [[2200.0, 400.0], [3500.0, 400.0], [3500.0, 1500.0], [2200.0, 1500.0]],
        }
    }
    moved = deepcopy(base)
    moved["supplied_block_corners_tl_tr_br_bl"]["CS2"][2][0] += 16.0
    report = subject._partial_geometry_drift_screen(  # noqa: SLF001
        [base, moved, base, base]
    )

    assert report["diagnostic_state"] == subject.FAIL
    assert report["fixed_mount_drift_gate_passed"] is False
    assert report["automatic_roi_expansion"] is False
    assert report["full_panel_geometry_evaluated"] is False


def test_partial_cli_binds_three_independent_v2_action_snapshots() -> None:
    args = subject.parse_args(
        [
            "generate-partial",
            "--white-photo",
            "white.jpg",
            "--white-sidecar",
            "white.json",
            "--white-action-result",
            "white-action.json",
            "--white-human-authority",
            "white-authority.json",
            "--atlas-photo",
            "atlas-1.jpg",
            "atlas-2.jpg",
            "atlas-3.jpg",
            "--atlas-sidecar",
            "atlas-1.json",
            "atlas-2.json",
            "atlas-3.json",
            "--atlas-action-result",
            "action-1.json",
            "action-2.json",
            "action-3.json",
            "--white-partial-blocks",
            '{"CS1": [], "CS2": []}',
            "--atlas-partial-blocks",
            '{"CS1": [], "CS2": []}',
            '{"CS1": [], "CS2": []}',
            '{"CS1": [], "CS2": []}',
            "--report-output",
            "report.json",
        ]
    )

    assert args.atlas_action_result == [
        Path("action-1.json"),
        Path("action-2.json"),
        Path("action-3.json"),
    ]


def test_partial_report_rejects_repeated_action_snapshot_path() -> None:
    repeated_action = Path("repeated-action.json")

    with pytest.raises(
        subject.T3CameraObservationError,
        match="three distinct atlas action snapshot paths",
    ):
        subject.build_partial_report(
            white_photo_path=Path("white.jpg"),
            white_capture_sidecar_path=Path("white.json"),
            white_action_result_path=Path("white-action.json"),
            white_human_authority_path=Path("white-authority.json"),
            atlas_photo_paths=[
                Path("atlas-1.jpg"),
                Path("atlas-2.jpg"),
                Path("atlas-3.jpg"),
            ],
            atlas_capture_sidecar_paths=[
                Path("atlas-1.json"),
                Path("atlas-2.json"),
                Path("atlas-3.json"),
            ],
            atlas_action_result_paths=[repeated_action] * 3,
            white_partial_blocks={},
            atlas_partial_blocks=[{}, {}, {}],
        )


@pytest.mark.parametrize(
    ("level", "expected"),
    [(70, subject.REVIEW), (40, subject.FAIL)],
)
def test_white_lstar_is_review_then_hard_fail_without_relaxation(
    level: int, expected: str
) -> None:
    atlas = _logical_atlas(white_level=level)
    result = subject.screen_logical_panels(
        _white(level), [atlas, atlas.copy(), atlas.copy()]
    )

    assert result["diagnostic_state"] == expected
    assert result["white_reference"]["minimum_lstar_hard_boundary"] == 25.0


def test_uniform_low_information_frames_are_review_never_pass() -> None:
    atlas = np.full_like(_white(), 80)
    result = subject.screen_logical_panels(
        _white(), [atlas, atlas.copy(), atlas.copy()]
    )

    assert result["machine_confidence"] == "LOW"
    assert result["diagnostic_state"] == subject.REVIEW


def test_obvious_four_copy_disagreement_fails_frozen_8_12_gate() -> None:
    atlas = _logical_atlas()
    target = next(
        cell
        for cell in geometry._all_logical_cells()  # noqa: SLF001
        if cell["controller"] == 0 and cell["code"] == 0
    )
    x, y, width, height = target["logical_bounds"]
    atlas[y : y + height, x : x + width] = (170, 20, 170)
    result = subject.screen_logical_panels(
        _white(), [atlas, atlas.copy(), atlas.copy()]
    )

    assert subject.POSITION_PASS_MAX_DE00 == 8.0
    assert subject.POSITION_REVIEW_MAX_DE00 == 12.0
    assert (
        result["four_replicate_consistency"]["maximum_delta_e00"]["diagnostic_state"]
        == subject.FAIL
    )
    assert result["diagnostic_state"] == subject.FAIL


def test_cross_controller_control_mismatch_fails() -> None:
    atlas = _logical_atlas()
    for cell in geometry._all_logical_cells():  # noqa: SLF001
        if cell["controller"] == 1 and cell["code"] == 2:
            x, y, width, height = cell["logical_bounds"]
            atlas[y : y + height, x : x + width] = (170, 20, 20)
    result = subject.screen_logical_panels(
        _white(), [atlas, atlas.copy(), atlas.copy()]
    )

    assert (
        result["controls"]["maximum_cross_controller_delta_e00"]["diagnostic_state"]
        == subject.FAIL
    )
    assert result["diagnostic_state"] == subject.FAIL


def test_stripe_and_bottom_edge_anomalies_fail() -> None:
    atlas = _logical_atlas()
    target = geometry._all_logical_cells()[0]  # noqa: SLF001
    x, y, width, height = target["logical_bounds"]
    atlas[y + height // 2 : y + height, x : x + width] = (170, 170, 170)
    atlas[566:590, 20:492] = (170, 170, 170)
    result = subject.screen_logical_panels(
        _white(), [atlas, atlas.copy(), atlas.copy()]
    )

    assert (
        result["artifacts"]["horizontal_stripe"]["maximum_band_delta_e00"][
            "diagnostic_state"
        ]
        == subject.FAIL
    )
    assert (
        result["artifacts"]["bottom_edge"]["maximum_delta_e00"]["diagnostic_state"]
        == subject.FAIL
    )


def test_each_capture_geometry_drift_is_review_then_fail() -> None:
    review = subject._geometry_drift_screen(  # noqa: SLF001
        [_fake_geometry(0), _fake_geometry(20), _fake_geometry(0), _fake_geometry(0)]
    )
    fail = subject._geometry_drift_screen(  # noqa: SLF001
        [_fake_geometry(0), _fake_geometry(40), _fake_geometry(0), _fake_geometry(0)]
    )

    assert (
        review["maximum_corresponding_corner_drift_photo_px"]["diagnostic_state"]
        == subject.REVIEW
    )
    assert (
        fail["maximum_corresponding_corner_drift_photo_px"]["diagnostic_state"]
        == subject.FAIL
    )


def test_missing_seed_caps_camera_only_screen_at_review() -> None:
    pixel = {"diagnostic_state": subject.PASS, "machine_confidence": "HIGH"}
    conclusion, reasons = subject._combine_screen(  # noqa: SLF001
        pixel_screen=pixel,
        geometry_screen=subject._geometry_drift_screen(  # noqa: SLF001
            [_fake_geometry()] * 4
        ),
        human_seed_screen=subject._missing_human_seed_screen(),  # noqa: SLF001
    )

    assert conclusion == "HUMAN_CAMERA_SCREEN_REVIEW"
    assert any("no operator seed" in reason for reason in reasons)


def test_truthful_compact_seed_expands_to_exact_64_cells() -> None:
    seed = subject._validate_seed(_truthful_seed())  # noqa: SLF001
    compact = subject._compact_from_seed(seed)  # noqa: SLF001

    assert compact is not None
    expanded, expansion = human._expand_compact_operator_input(  # noqa: SLF001
        compact, expected_stage=human.AC_STAGE
    )
    assert len(expanded["cells"]) == 64
    assert expansion["expanded_cell_count"] == 64
    assert expanded["operator"] == seed["operator"]


def test_unfilled_seed_template_is_never_accepted_as_human_fact() -> None:
    with pytest.raises(subject.T3CameraObservationError, match="unfilled template"):
        subject._validate_seed(subject.seed_template())  # noqa: SLF001


def test_exposure_minus_3_is_explicitly_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = deepcopy(subject.EXPECTED_CAMERA_PROFILE)
    profile["exposure"] = -3.0
    monkeypatch.setattr(subject, "EXPECTED_CAMERA_PROFILE", profile)

    with pytest.raises(subject.T3CameraObservationError, match="exposure=-6"):
        subject._validate_camera_profile_choice()  # noqa: SLF001


def test_w3_v2_white_capture_allowlist_matches_final_pack() -> None:
    binding = next(
        item
        for item in camera.RAW_P16_CROSSOVER_WHITE_CONTAINMENT_BINDINGS
        if item["stage"] == w3_pack.STAGE
    )
    report = w3_pack.build_white_report()
    action = report["action"]

    assert binding["campaign_id"] == w3_pack.CONFIG.campaign_id
    assert binding["test_id"] == w3_pack.CONFIG.test_id
    assert binding["contract_id"] == report["contract_id"]
    assert (
        binding["firmware_sha256"]
        == w3_pack.WHITE_ARTIFACTS[w3_pack.STAGE]["bin_sha256"]
    )
    assert binding["action_id"] == action["action_id"]
    assert binding["descriptor_id"] == action["descriptor_id"]


def test_dual_o_excl_outputs_and_compact_validation(tmp_path: Path) -> None:
    compact = subject._compact_from_seed(  # noqa: SLF001
        subject._validate_seed(_truthful_seed())  # noqa: SLF001
    )
    report = {"generated_compact_human_input": {"content": compact}}
    report_path = tmp_path / "screen.json"
    compact_path = tmp_path / "human-compact.json"

    subject.write_report_and_compact_exclusive(
        report_path=report_path, compact_path=compact_path, report=report
    )
    loaded = json.loads(compact_path.read_text(encoding="utf-8"))
    assert loaded == compact
    subject.validate_compact_output(report=report, compact_path=compact_path)
    with pytest.raises(subject.T3CameraObservationError, match="overwrite"):
        subject.write_report_and_compact_exclusive(
            report_path=report_path, compact_path=compact_path, report=report
        )


def test_frozen_offline_contract_binds_readme_profile_and_5_4a_thresholds() -> None:
    contract = subject._validate_offline_contract()  # noqa: SLF001

    assert contract["camera_id"] == "USB_VID_32E4_PID_4801"
    assert contract["selected_exposure"] == -6.0
    assert contract["fresh_v2_exposure_minus_3_admitted"] is False
    assert contract["decisive_four_replicate_delta_e00_thresholds"] == {
        "pass_max": 8.0,
        "review_max": 12.0,
    }
