from __future__ import annotations

import copy

import pytest

from tools import (
    mf1750_raw_p16_crossover_t2_discovery_successor_pack as frozen_pack,
)
from tools import (
    mf1750_raw_p16_crossover_t2_discovery_successor_photo_analyzer as frozen_analyzer,
)
from tools import (
    mf1750_raw_p16_crossover_t2_discovery_successor_v2_pack as pack,
)
from tools import (
    mf1750_raw_p16_crossover_t2_discovery_successor_v2_photo_analyzer as analyzer,
)


def _action_result() -> dict:
    report = pack.build_report()
    expected = report["actions"][0]
    return {
        "kind": f"mf1750-ec5-{pack.CONFIG.route_slug}-result",
        "outcome": "complete_pass",
        "visible_refreshes": 1,
        "firmware_sha256": pack.ARTIFACTS[pack.STAGE]["bin_sha256"],
        "action": analyzer._runtime_action(expected),  # noqa: SLF001
        "terminal_report": {
            "terminal_state": "COMPLETE",
            "result": True,
            "valid": True,
            "campaign_id": pack.CONFIG.campaign_id,
            "test_id": pack.CONFIG.test_id,
            "contract_id": report["contract_id"],
            "build_tag": pack.CONFIG.build_tag,
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


def test_only_fresh_v2_identity_is_accepted() -> None:
    identity = analyzer._validate_action(_action_result())  # noqa: SLF001
    report = pack.build_report()
    action = report["actions"][0]

    assert identity["stage"] == pack.STAGE
    assert identity["campaign_id"] == pack.CONFIG.campaign_id
    assert identity["contract_id"] == report["contract_id"]
    assert identity["descriptor_id"] == action["descriptor_id"]
    assert identity["action_id"] == action["action_id"]
    assert identity["contract_id"] == (
        "3a9dc65fcc4985cbb27195c340e910e7531b118cd8279a52dac9b49ce9558b77"
    )
    assert identity["descriptor_id"] == (
        "e80021a5d42db51180cd95873d48d979d70c6881c1dd8642b2c5b7299f126e65"
    )
    assert identity["action_id"] == (
        "c184e610cc2ac464ca152eb1af7a0a9f746e5d92c38da53b673de9c0dcdcfd1f"
    )
    assert identity["role"] == "RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_V2_ATLAS"


def test_consumed_v1_and_mutated_v2_are_rejected() -> None:
    frozen_report = frozen_pack.build_report()
    frozen_action = frozen_report["actions"][0]
    frozen_result = {
        "kind": f"mf1750-ec5-{frozen_pack.CONFIG.route_slug}-result",
        "outcome": "complete_pass",
        "visible_refreshes": 1,
        "firmware_sha256": frozen_pack.ARTIFACTS[frozen_pack.STAGE]["bin_sha256"],
        "action": frozen_analyzer._runtime_action(frozen_action),  # noqa: SLF001
        "terminal_report": {},
    }
    with pytest.raises(
        analyzer.CrossoverDiscoveryV2PhotoAnalysisError,
        match="successor V2 action role differs",
    ):
        analyzer._validate_action(frozen_result)  # noqa: SLF001

    changed = copy.deepcopy(_action_result())
    changed["action"]["frame_sha256"] = "0" * 64
    with pytest.raises(
        analyzer.CrossoverDiscoveryV2PhotoAnalysisError,
        match="frame_sha256 differs",
    ):
        analyzer._validate_action(changed)  # noqa: SLF001


def test_projection_reuses_ca_layout_but_keeps_v2_identity() -> None:
    cells = []
    for cell in analyzer.legacy._all_logical_cells():  # noqa: SLF001
        item = dict(cell)
        item["camera_relative_lab_d65_from_rgb_median"] = [
            40.0 + item["code"],
            2.0,
            -3.0,
        ]
        cells.append(item)
    identity = analyzer._validate_action(_action_result())  # noqa: SLF001
    projection = analyzer._comparison_projection(  # noqa: SLF001
        action_identity=identity,
        camera_lock_report={"fixed_exposure_boundary": -3.0},
        geometry={
            "homography_logical_to_current_photo": [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
            ],
            "sampling_geometry_admitted": True,
            "historical_g1_homography_reused": False,
            "all_projected_cells_inside_photo": True,
            "automatic_cell_lattice_reprojection_proven": False,
            "panel_area_fraction_of_photo": 0.5,
            "minimum_required_panel_area_fraction": 0.08,
            "minimum_projected_cell_side_px": 40.0,
            "minimum_required_projected_cell_side_px": 20.0,
        },
        cells=cells,
    )

    assert projection["stage"] == pack.STAGE
    assert projection["campaign_id"] == pack.CONFIG.campaign_id
    assert projection["codes"][0]["controllers"][0]["profile"] == "commented"
    assert projection["codes"][0]["controllers"][1]["profile"] == "active"
    assert all(
        len(controller["positions"]) == 4
        for code in projection["codes"]
        for controller in code["controllers"]
    )


def test_capture_plan_and_cli_are_exact_v2_only() -> None:
    assert pack.ARTIFACTS[pack.STAGE] == {
        "bin_bytes": 801_088,
        "bin_sha256": (
            "ce8e85b7d88fc25bb41a04a08b6b29c6227396890aee53244e5033f9df8bbed8"
        ),
        "elf_bytes": 13_294_940,
        "elf_sha256": (
            "05b25c8699a861e301367a77e53f9a39de57d97a140f8609b5f2935c381d8f1d"
        ),
    }
    assert pack.CAPTURE_PLAN["camera_logical_id"] == "USB_VID_32E4_PID_4801"
    assert pack.CAPTURE_PLAN["exposure"] == -3
    assert pack.CAPTURE_PLAN["frame_width"] == 4000
    assert pack.CAPTURE_PLAN["frame_height"] == 3000
    assert pack.CAPTURE_PLAN["retained_atlas_frame_count"] == 3
    assert pack.CAPTURE_PLAN["white_reference_min_lstar"] == 25.0
    assert pack.CAPTURE_PLAN["automatic_threshold_relaxation"] is False

    argv = [
        "--stage",
        pack.STAGE,
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
    assert analyzer.parse_args(argv).stage == pack.STAGE
    with pytest.raises(SystemExit):
        analyzer.parse_args([*argv[:1], frozen_pack.STAGE, *argv[2:]])
