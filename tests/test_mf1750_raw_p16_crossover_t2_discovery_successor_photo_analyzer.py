from __future__ import annotations

import copy

import pytest

from tools import mf1750_raw_p16_crossover_position_balanced_pack as legacy_pack
from tools import (
    mf1750_raw_p16_crossover_position_balanced_photo_analyzer as legacy,
)
from tools import (
    mf1750_raw_p16_crossover_t2_discovery_successor_pack as pack,
)
from tools import (
    mf1750_raw_p16_crossover_t2_discovery_successor_photo_analyzer as analyzer,
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


def test_only_fresh_successor_identity_is_accepted() -> None:
    identity = analyzer._validate_action(_action_result())  # noqa: SLF001
    report = pack.build_report()
    action = report["actions"][0]

    assert identity["stage"] == pack.STAGE
    assert identity["campaign_id"] == pack.CONFIG.campaign_id
    assert identity["contract_id"] == report["contract_id"]
    assert identity["action_id"] == action["action_id"]
    assert identity["firmware_sha256"] == pack.ARTIFACTS[pack.STAGE]["bin_sha256"]
    assert identity["role"] == "RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_ATLAS"


def test_frozen_t2_and_mutated_successor_are_rejected() -> None:
    frozen = legacy_pack.build_report("t2-ca")
    frozen_action = frozen["actions"][0]
    frozen_result = {
        "kind": f"mf1750-ec5-{legacy_pack.STAGES['t2-ca'].route_slug}-result",
        "outcome": "complete_pass",
        "visible_refreshes": 1,
        "firmware_sha256": legacy_pack.ARTIFACTS["t2-ca"]["bin_sha256"],
        "action": legacy._runtime_action(frozen_action),  # noqa: SLF001
        "terminal_report": {},
    }
    with pytest.raises(
        analyzer.CrossoverDiscoveryPhotoAnalysisError,
        match="successor action role differs",
    ):
        analyzer._validate_action(frozen_result)  # noqa: SLF001

    changed = copy.deepcopy(_action_result())
    changed["action"]["frame_sha256"] = "0" * 64
    with pytest.raises(
        analyzer.CrossoverDiscoveryPhotoAnalysisError,
        match="frame_sha256 differs",
    ):
        analyzer._validate_action(changed)  # noqa: SLF001


def test_projection_reuses_ca_profiles_but_keeps_fresh_stage() -> None:
    cells = []
    for cell in legacy._all_logical_cells():  # noqa: SLF001
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
        camera_lock={"mount": "fixed"},
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


def test_cli_stage_cannot_name_frozen_t2() -> None:
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
        analyzer.parse_args([*argv[:1], "t2-ca", *argv[2:]])
