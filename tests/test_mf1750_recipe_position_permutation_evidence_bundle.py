from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools import mf1750_recipe_position_permutation_evidence_bundle as bundle


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    unsigned = dict(value)
    unsigned.pop("integrity", None)
    unsigned["integrity"] = {
        "algorithm": bundle.INTEGRITY_ALGORITHM,
        "sha256": bundle._sha256_bytes(bundle._canonical_json(unsigned)),
    }
    return unsigned


def _write(path: Path, value: dict[str, Any]) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _settings() -> dict[str, float | int]:
    return {
        "autofocus": 0.0,
        "auto_exposure": 0.25,
        "auto_white_balance": 0.0,
        "focus": 12.0,
        "exposure": -6.0,
        "white_balance_temperature": 4600.0,
        "frame_width": 1920,
        "frame_height": 1080,
    }


def _action(path: Path, ordinal: int) -> Path:
    action = bundle.once.base.runner.ACTIONS[ordinal - 1]
    minute = (ordinal - 1) * 2
    return _write(
        path,
        _seal(
            {
                "schema_version": 1,
                "kind": bundle.ACTION_RESULT_KIND,
                "created_at": f"2026-08-28T10:{minute:02d}:00+08:00",
                "firmware_sha256": bundle.once.FIRMWARE_SHA256,
                "boot_nonce": "batch2-same-boot",
                "action": {
                    "ordinal": ordinal,
                    "action_id": action["action_id"],
                    "descriptor_id": action["descriptor_id"],
                    "role": action["role"],
                    "branch": action["branch"],
                },
                "terminal_report": {
                    "boot_nonce": "batch2-same-boot",
                    "ordinal": ordinal,
                },
                "outcome": "complete_pass",
                "visible_refreshes": 1,
                "no_retry": True,
                "no_recovery": True,
                "no_autochain": True,
            }
        ),
    )


def _capture(path: Path, action_path: Path, ordinal: int) -> Path:
    action = bundle.once.base.runner.ACTIONS[ordinal - 1]
    minute = (ordinal - 1) * 2 + 1
    settings = _settings()
    root = {
        "capture_binding": bundle.camera.BINDING_LIVE,
        "campaign_id": bundle.pack.CAMPAIGN_ID,
        "contract_id": bundle.once.base.runner.CONTRACT_ID,
        "firmware_sha256": bundle.once.FIRMWARE_SHA256,
        "boot_nonce": "batch2-same-boot",
        "ordinal": ordinal,
        "action_id": action["action_id"],
        "descriptor_id": action["descriptor_id"],
        "capture_id": f"{ordinal:064x}",
        "captured_at": f"2026-08-28T10:{minute:02d}:00+08:00",
        "action_result": {
            "file_sha256": bundle._sha256_bytes(action_path.read_bytes())
        },
        "camera": {
            "camera_id": "camera-1",
            "instance_id": "instance-1",
            "index": 0,
            "backend": "DSHOW",
            "requested_settings": settings,
            "effective_settings_before_frame": settings,
            "effective_settings_after_frame": settings,
            "read_failures": 0,
        },
        "photo": {
            "sha256": "abcd"[ordinal - 1] * 64,
            "width": 1920,
            "height": 1080,
        },
        "coverage": {
            "scope": bundle.camera.COVERAGE_FULL,
            "full_panel_visible": True,
            "full_panel_uncropped": True,
            "mount_id": "fixed-mount-1",
        },
    }
    return _write(path, _seal(root))


def _noise(path: Path) -> Path:
    settings = _settings()
    return _write(
        path,
        _seal(
            {
                "schema_version": bundle.batch1_bundle.noise_report.SCHEMA_VERSION,
                "kind": bundle.batch1_bundle.noise_report.KIND,
                "baseline_id": "8" * 64,
                "layout": {"id": bundle.white_gate.LAYOUT_ID, "patch_count": 60},
                "geometry_reference": {"file_sha256": "9" * 64},
                "capture_contract": {
                    "capture_count": 3,
                    "capture_binding": bundle.camera.BINDING_LIVE,
                    "coverage_scope": bundle.camera.COVERAGE_FULL,
                    "same_factory_white_action": True,
                    "locked_camera_and_mount": {
                        "camera_id": "camera-1",
                        "camera_instance_id": "instance-1",
                        "camera_index": 0,
                        "backend": "DSHOW",
                        "mount_id": "fixed-mount-1",
                        "requested_settings": settings,
                        "effective_settings": settings,
                    },
                },
                "summary": {"repeat_noise_p95_de76": 1.0},
                "classification": {"valid_repeat_noise_baseline": True},
            }
        ),
    )


def _cells(*, permuted: bool) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for controller in range(2):
        for row in range(8):
            for column in range(8):
                source = (column + 3) % 8 if permuted else column
                middle = 7 - row if permuted else row
                result.append(
                    {
                        "controller": controller,
                        "row": row,
                        "column": column,
                        "cell_id": f"C{controller}-R{row}-K{column}",
                        "recipe_id": f"REDPINK-A{source}-B{middle}-A0",
                        "camera_relative_lab": [
                            40.0 + source,
                            10.0 + middle,
                            2.0 + controller,
                        ],
                        "all_corners_inside_photo": True,
                        "inner_patch_valid_fraction": 1.0,
                    }
                )
    return result


def _p0_grid(path: Path) -> Path:
    return _write(
        path,
        _seal(
            {
                "schema_version": 1,
                "kind": bundle.comparison.BASE_KIND,
                "source_photo": {"sha256": "0" * 64},
                "campaign_layout": {
                    "id": bundle.P0_LAYOUT_ID,
                    "action_ordinal": 4,
                },
                "grid_judgement": {"enough_to_interpret_grid_camera_relatively": True},
                "cells": _cells(permuted=False),
            }
        ),
    )


def _anchor(path: Path, p0_grid: Path) -> Path:
    p0 = json.loads(p0_grid.read_text(encoding="utf-8"))
    settings = _settings()
    camera_lock = {
        "camera_tuple": {
            "camera_id": "camera-1",
            "instance_id": "instance-1",
            "index": 0,
            "backend": "DSHOW",
        },
        "mount_id": "fixed-mount-1",
        "requested_settings": settings,
        "effective_settings_before_frame": settings,
        "effective_settings_after_frame": settings,
        "effective_readback_equal": True,
        "manual_control_contract": dict(bundle.REQUIRED_MANUAL_CAMERA_SETTINGS),
    }
    camera_lock["signature_sha256"] = bundle._sha256_bytes(
        bundle._canonical_json(camera_lock)
    )
    cell_anchors = []
    for controller in range(2):
        for row in range(8):
            for column in range(8):
                cell_anchors.append(
                    {
                        "cell_id": f"C{controller}-R{row}-K{column}",
                        "controller": controller,
                        "row": row,
                        "column": column,
                        "recipe_id": f"REDPINK-A{column}-B{row}-A0",
                    }
                )
    recipe_map = []
    for row in range(8):
        for column in range(8):
            recipe_map.append(
                {
                    "recipe_id": f"REDPINK-A{column}-B{row}-A0",
                    "source_code": column,
                    "middle_code": row,
                    "target_code": 0,
                    "p0_cells": [
                        f"C{controller}-R{row}-K{column}" for controller in range(2)
                    ],
                }
            )
    return _write(
        path,
        _seal(
            {
                "schema_version": 1,
                "kind": bundle.G1_ANCHOR_KIND,
                "anchor_id": "1" * 64,
                "created_at": "2026-08-28T09:56:00+08:00",
                "capture": {
                    "path": "g1-capture.json",
                    "bytes": 100,
                    "capture_id": "2" * 64,
                    "capture_binding": bundle.camera.BINDING_RETROSPECTIVE,
                    "captured_at": "2026-08-28T09:55:00+08:00",
                    "file_sha256": "3" * 64,
                    "canonical_integrity_sha256": "4" * 64,
                    "campaign_id": "historical-campaign",
                    "test_id": "historical-test",
                    "action_id": "7" * 64,
                    "ordinal": 4,
                    "role": "HISTORICAL_ACTION4_RETAINED_STATE",
                },
                "photo": {
                    "path": "g1-photo.png",
                    "bytes": 1000,
                    "sha256": "0" * 64,
                    "width": 1920,
                    "height": 1080,
                    "mode": "RGB",
                    "coverage_scope": bundle.camera.COVERAGE_FULL,
                    "full_panel_visible": True,
                    "full_panel_uncropped": True,
                },
                "camera_lock": camera_lock,
                "grid_analysis": {
                    "layout_id": bundle.P0_LAYOUT_ID,
                    "file_sha256": bundle._sha256_bytes(p0_grid.read_bytes()),
                    "canonical_integrity_sha256": p0["integrity"]["sha256"],
                    "kind": bundle.g1_anchor.GRID_KIND,
                    "action_ordinal": 4,
                    "source_photo_sha256": "0" * 64,
                },
                "geometry_p0": {
                    "coordinate_space": "frozen logical 1024x600 to captured photo pixels",
                    "layout_id": bundle.P0_LAYOUT_ID,
                    "action_ordinal": 4,
                    "homography_logical_to_photo": [
                        [1.0, 0.0, 0.0],
                        [0.0, 1.0, 0.0],
                        [0.0, 0.0, 1.0],
                    ],
                    "quality_gate": {
                        "unique_cell_contour_support": 128,
                        "support_by_controller": [64, 64],
                        "homography_inliers": 128,
                        "homography_correspondences": 128,
                        "minimum_inner_patch_valid_fraction": 1.0,
                        "all_cell_corners_inside_photo": True,
                    },
                    "cell_anchors": cell_anchors,
                    "p0_recipe_map": recipe_map,
                },
                "classification": {
                    "state": bundle.G1_CLASSIFICATION,
                    "geometry_anchor_pass": True,
                    "p0_position_baseline_pass": True,
                    "retrospective_only": True,
                    "live_action_evidence": False,
                    "temporal_action_continuity_proven": False,
                    "action_causality_proven": False,
                    "absolute_colour_proven": False,
                    "qualified_colour_proven": False,
                    "input_live_binding_was_not_propagated": False,
                },
                "evidence_boundaries": {"device_io_performed": False},
                "output_write_contract": "O_EXCL",
            }
        ),
    )


def _p1_grid(path: Path) -> Path:
    mapping = []
    for controller in range(2):
        for row in range(8):
            for column in range(8):
                source = (column + 3) % 8
                middle = 7 - row
                mapping.append(
                    {
                        "controller": controller,
                        "physical_row": row,
                        "physical_column": column,
                        "source_code": source,
                        "middle_code": middle,
                        "target_code": 0,
                        "recipe_id": f"REDPINK-A{source}-B{middle}-A0",
                    }
                )
    return _write(
        path,
        _seal(
            {
                "schema_version": bundle.p1_grid.SCHEMA_VERSION,
                "kind": bundle.p1_grid.KIND,
                "source_photo": {
                    "bytes": 1000,
                    "sha256": "c" * 64,
                    "width": 1920,
                    "height": 1080,
                },
                "campaign_layout": {
                    "id": bundle.P1_LAYOUT_ID,
                    "action_ordinal": 3,
                    "source_column_shift_mod8": 3,
                    "middle_row_reversed": True,
                    "fixed_target_code": 0,
                },
                "method": {
                    "perspective_rectified": True,
                    "physical_colour_calibrated": False,
                    "device_io_performed": False,
                },
                "geometry_quality": {
                    "unique_cell_contour_support": 128,
                    "homography_inlier_fraction": 1.0,
                    "homography_inlier_rmse_px": 1.0,
                    "sampling": {
                        "minimum_inner_patch_valid_fraction": 1.0,
                        "all_cell_corners_inside_photo": True,
                        "minimum_projected_cell_width_px": 40.0,
                        "minimum_projected_cell_height_px": 40.0,
                    },
                },
                "grid_judgement": {
                    "enough_to_interpret_grid_camera_relatively": True,
                    "verdict": "SUFFICIENT_CAMERA_RELATIVE_GRID_READOUT",
                    "blocking_reasons": [],
                    "camera_relative_only": True,
                    "photo_dimensions": [1920, 1080],
                },
                "cells": _cells(permuted=True),
                "recipe_physical_mapping": mapping,
                "output_write_contract": "O_EXCL",
            }
        ),
    )


def _comparison(path: Path, p0: Path, p1: Path) -> Path:
    p0_root = json.loads(p0.read_text(encoding="utf-8"))
    p1_root = json.loads(p1.read_text(encoding="utf-8"))
    return _write(
        path,
        _seal(
            {
                "schema_version": bundle.comparison.SCHEMA_VERSION,
                "kind": bundle.comparison.KIND,
                "comparison_id": "5" * 64,
                "inputs": {
                    "baseline": {
                        "file_sha256": bundle._sha256_bytes(p0.read_bytes()),
                        "canonical_integrity_sha256": p0_root["integrity"]["sha256"],
                    },
                    "permuted": {
                        "file_sha256": bundle._sha256_bytes(p1.read_bytes()),
                        "canonical_integrity_sha256": p1_root["integrity"]["sha256"],
                    },
                },
                "mapping": {
                    "source_at_physical_column": "(column + 3) mod 8",
                    "middle_at_physical_row": "7 - row",
                    "target_code": 0,
                    "bijection_verified": True,
                },
                "controllers": [
                    {"controller": 0, "recipe_linked_candidate": True},
                    {"controller": 1, "recipe_linked_candidate": True},
                ],
                "classification": {
                    "state": "BOTH_CONTROLLERS_RECIPE_LINKED_CANDIDATE",
                    "recipe_linked_controller_count": 2,
                    "qualified_new_colour": False,
                    "qualified_brightness_level": False,
                },
                "output_write_contract": "O_EXCL",
            }
        ),
    )


def _white(path: Path, *, passed: bool = True) -> Path:
    deltas = [1.0] * 60
    patches = []
    for controller in range(2):
        for row in range(6):
            for column in range(5):
                patches.append(
                    {
                        "controller": controller,
                        "row": row,
                        "column": column,
                        "camera_relative_de76": deltas[len(patches)],
                    }
                )
    return _write(
        path,
        _seal(
            {
                "schema_version": bundle.white_gate.SCHEMA_VERSION,
                "kind": bundle.white_gate.KIND,
                "analysis_id": "6" * 64,
                "layout": {
                    "id": bundle.white_gate.LAYOUT_ID,
                    "controllers": 2,
                    "patch_count": 60,
                },
                "inputs": {
                    "candidate": {"sha256": "d" * 64},
                    "geometry_reference": {"sha256": "9" * 64},
                },
                "thresholds": {
                    "repeat_noise_p95_de76": 1.0,
                    "patch_grid_p95_de76": 4.0,
                    "patch_grid_max_de76": 8.0,
                },
                "summary": {
                    "patch_count": 60,
                    "camera_relative_de76_median": 1.0,
                    "camera_relative_de76_p95": 1.0,
                    "camera_relative_de76_max": 1.0,
                    "all_panel_regions_match_reference": passed,
                },
                "patches": patches,
                "classification": {
                    "pass": passed,
                    "state": (
                        "PANEL_WIDE_CAMERA_RELATIVE_FACTORY_WHITE_MATCH"
                        if passed
                        else "PANEL_WIDE_CAMERA_RELATIVE_FACTORY_WHITE_MISMATCH"
                    ),
                    "absolute_white_proven": False,
                },
                "output_write_contract": "O_EXCL",
            }
        ),
    )


@pytest.fixture(autouse=True)
def _offline_validator_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bundle.once, "_validate_complete_report", lambda *_: None)

    def validate_capture(path: Path) -> dict[str, Any]:
        return json.loads(Path(path).read_text(encoding="utf-8"))

    monkeypatch.setattr(bundle.camera, "validate_capture_evidence", validate_capture)


def _inputs(tmp_path: Path) -> tuple[Any, ...]:
    actions = [
        _action(tmp_path / bundle.once.ACTION_OUTPUT_NAMES[ordinal], ordinal)
        for ordinal in range(1, 5)
    ]
    captures = [
        _capture(tmp_path / f"capture-{ordinal}.json", actions[ordinal - 1], ordinal)
        for ordinal in range(1, 5)
    ]
    p0 = _p0_grid(tmp_path / "g1-p0-grid.json")
    anchor = _anchor(tmp_path / "g1-anchor.json", p0)
    p1 = _p1_grid(tmp_path / "p1-grid.json")
    recipe = _comparison(tmp_path / "recipe-comparison.json", p0, p1)
    white = _white(tmp_path / "terminal-white.json")
    return actions, captures, _noise(tmp_path / "noise.json"), anchor, p1, recipe, white


def _reseal_file(path: Path, mutate: Any) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    unsigned = dict(value)
    unsigned.pop("integrity")
    mutate(unsigned)
    _write(path, _seal(unsigned))


def test_builds_sealed_exploratory_bundle_and_batch3_prerequisite(
    tmp_path: Path,
) -> None:
    report = bundle.build_bundle(*_inputs(tmp_path))
    assert report["kind"] == bundle.KIND
    assert len(report["action_results"]) == 4
    assert len(report["captures"]) == 4
    assert report["campaign_identity"]["visible_refresh_count"] == 4
    assert report["classification"] == {
        "state": "RECIPE_LINKED_EXPLORATORY_CANDIDATE",
        "recipe_comparison_state": "BOTH_CONTROLLERS_RECIPE_LINKED_CANDIDATE",
        "recipe_linked_controller_count": 2,
        "recipe_linked_exploratory_only": True,
        "qualified_new_colour": False,
        "qualified_brightness_level": False,
        "absolute_colour_proven": False,
    }
    terminal = report["terminal_white_prerequisite"]
    assert terminal["eligible"] is True
    assert terminal["ordinal"] == 4
    assert terminal["patch_count"] == 60
    assert terminal["batch3_binding_contract"]["deep_verify_terminal_subobject"]
    unsigned = dict(report)
    integrity = unsigned.pop("integrity")
    assert integrity["sha256"] == bundle._sha256_bytes(bundle._canonical_json(unsigned))


def test_action_integrity_tamper_is_rejected(tmp_path: Path) -> None:
    inputs = list(_inputs(tmp_path))
    actions = inputs[0]
    value = json.loads(actions[0].read_text(encoding="utf-8"))
    value["visible_refreshes"] = 2
    actions[0].write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(
        bundle.RecipePositionPermutationEvidenceBundleError, match="integrity"
    ):
        bundle.build_bundle(*inputs)


def test_resealed_action_boot_discontinuity_is_rejected(tmp_path: Path) -> None:
    inputs = list(_inputs(tmp_path))
    actions = inputs[0]

    def mutate(value: dict[str, Any]) -> None:
        value["boot_nonce"] = "different-boot"
        value["terminal_report"]["boot_nonce"] = "different-boot"

    _reseal_file(actions[2], mutate)
    with pytest.raises(
        bundle.RecipePositionPermutationEvidenceBundleError, match="boot continuity"
    ):
        bundle.build_bundle(*inputs)


def test_capture_must_be_live_full_panel_and_same_camera(tmp_path: Path) -> None:
    inputs = list(_inputs(tmp_path))
    captures = inputs[1]

    def mutate(value: dict[str, Any]) -> None:
        value["coverage"]["scope"] = bundle.camera.COVERAGE_PARTIAL

    _reseal_file(captures[1], mutate)
    with pytest.raises(
        bundle.RecipePositionPermutationEvidenceBundleError,
        match="full-panel binding",
    ):
        bundle.build_bundle(*inputs)


def test_action_capture_timeline_must_be_strictly_interleaved(tmp_path: Path) -> None:
    inputs = list(_inputs(tmp_path))
    captures = inputs[1]

    def mutate(value: dict[str, Any]) -> None:
        value["captured_at"] = "2026-08-28T10:02:30+08:00"

    _reseal_file(captures[0], mutate)
    with pytest.raises(
        bundle.RecipePositionPermutationEvidenceBundleError,
        match="strictly interleaved",
    ):
        bundle.build_bundle(*inputs)


def test_g1_anchor_camera_lock_must_match_live_captures(tmp_path: Path) -> None:
    inputs = list(_inputs(tmp_path))
    anchor = inputs[3]

    def mutate(value: dict[str, Any]) -> None:
        value["camera_lock"]["mount_id"] = "different-mount"
        lock = dict(value["camera_lock"])
        lock.pop("signature_sha256")
        value["camera_lock"]["signature_sha256"] = bundle._sha256_bytes(
            bundle._canonical_json(lock)
        )

    _reseal_file(anchor, mutate)
    with pytest.raises(
        bundle.RecipePositionPermutationEvidenceBundleError,
        match="G-1 anchor and Batch-2 captures",
    ):
        bundle.build_bundle(*inputs)


def test_g1_anchor_must_be_retrospective_not_live_action(tmp_path: Path) -> None:
    inputs = list(_inputs(tmp_path))
    anchor = inputs[3]

    def mutate(value: dict[str, Any]) -> None:
        value["classification"]["live_action_evidence"] = True

    _reseal_file(anchor, mutate)
    with pytest.raises(
        bundle.RecipePositionPermutationEvidenceBundleError,
        match="retrospective boundary",
    ):
        bundle.build_bundle(*inputs)


def test_p1_recipe_mapping_tamper_is_rejected(tmp_path: Path) -> None:
    inputs = list(_inputs(tmp_path))
    p1 = inputs[4]

    def mutate(value: dict[str, Any]) -> None:
        value["recipe_physical_mapping"][0]["source_code"] = 0

    _reseal_file(p1, mutate)
    with pytest.raises(
        bundle.RecipePositionPermutationEvidenceBundleError,
        match=r"P1 mapping\[0\] recipe binding",
    ):
        bundle.build_bundle(*inputs)


def test_p1_geometry_gate_tamper_is_rejected(tmp_path: Path) -> None:
    inputs = list(_inputs(tmp_path))
    p1 = inputs[4]

    def mutate(value: dict[str, Any]) -> None:
        value["geometry_quality"]["homography_inlier_fraction"] = 0.2

    _reseal_file(p1, mutate)
    with pytest.raises(
        bundle.RecipePositionPermutationEvidenceBundleError,
        match="P1 grid identity",
    ):
        bundle.build_bundle(*inputs)


def test_comparison_must_bind_exact_g1_p0_grid(tmp_path: Path) -> None:
    inputs = list(_inputs(tmp_path))
    recipe = inputs[5]

    def mutate(value: dict[str, Any]) -> None:
        value["inputs"]["baseline"]["file_sha256"] = "f" * 64

    _reseal_file(recipe, mutate)
    with pytest.raises(
        bundle.RecipePositionPermutationEvidenceBundleError,
        match="P0/P1 binding",
    ):
        bundle.build_bundle(*inputs)


def test_recipe_classification_internal_mismatch_is_rejected(tmp_path: Path) -> None:
    inputs = list(_inputs(tmp_path))
    recipe = inputs[5]

    def mutate(value: dict[str, Any]) -> None:
        value["classification"]["recipe_linked_controller_count"] = 1

    _reseal_file(recipe, mutate)
    with pytest.raises(
        bundle.RecipePositionPermutationEvidenceBundleError,
        match="internally inconsistent",
    ):
        bundle.build_bundle(*inputs)


def test_terminal_white_patch_summary_tamper_is_rejected(tmp_path: Path) -> None:
    inputs = list(_inputs(tmp_path))
    white = inputs[6]

    def mutate(value: dict[str, Any]) -> None:
        value["summary"]["camera_relative_de76_p95"] = 0.5

    _reseal_file(white, mutate)
    with pytest.raises(
        bundle.RecipePositionPermutationEvidenceBundleError,
        match="internally inconsistent",
    ):
        bundle.build_bundle(*inputs)


def test_terminal_white_patch_coordinate_tamper_is_rejected(tmp_path: Path) -> None:
    inputs = list(_inputs(tmp_path))
    white = inputs[6]

    def mutate(value: dict[str, Any]) -> None:
        value["patches"][0]["row"] = 99

    _reseal_file(white, mutate)
    with pytest.raises(
        bundle.RecipePositionPermutationEvidenceBundleError,
        match="coordinate differs",
    ):
        bundle.build_bundle(*inputs)


def test_terminal_white_failed_gate_is_rejected(tmp_path: Path) -> None:
    inputs = list(_inputs(tmp_path))
    inputs[6] = _white(tmp_path / "failed-white.json", passed=False)
    with pytest.raises(
        bundle.RecipePositionPermutationEvidenceBundleError,
        match="sixty-patch white gate",
    ):
        bundle.build_bundle(*inputs)


def test_exclusive_output_and_cli(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    output = tmp_path / "bundle.json"
    argv: list[str] = []
    for path in inputs[0]:
        argv.extend(("--action-output", str(path)))
    for path in inputs[1]:
        argv.extend(("--capture-sidecar", str(path)))
    argv.extend(
        (
            "--repeat-noise-report",
            str(inputs[2]),
            "--p0-g-minus-1-anchor",
            str(inputs[3]),
            "--p1-grid-analysis",
            str(inputs[4]),
            "--recipe-comparison",
            str(inputs[5]),
            "--terminal-white-gate",
            str(inputs[6]),
            "--output",
            str(output),
        )
    )
    assert bundle.main(argv) == 0
    assert output.is_file()
    assert bundle.main(argv) == 2
