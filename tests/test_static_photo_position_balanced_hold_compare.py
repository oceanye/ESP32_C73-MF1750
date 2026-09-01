from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from host.static_photo.common import canonical_sha256
from host.static_photo.position_balanced_hold_compare import (
    COMPARISON_KIND,
    DEFAULT_REVIEW_THRESHOLDS,
    FROZEN_SNAPSHOTS,
    IDENTITY_CONTRACT_KIND,
    PROBE_SPEC,
    PositionBalancedHoldCompareError,
    compare_position_balanced_hold,
    export_position_balanced_hold_comparison,
    seal_position_balanced_hold_identity_contract,
    verify_position_balanced_hold_comparison,
)


def _digest(value: str | bytes) -> str:
    payload = value if isinstance(value, bytes) else value.encode()
    return hashlib.sha256(payload).hexdigest()


def _seal(value: dict) -> dict:
    result = deepcopy(value)
    result["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": canonical_sha256(value),
    }
    return result


def _write_json(path: Path, value: dict) -> tuple[bytes, str]:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    path.write_bytes(payload)
    return payload, _digest(payload)


def _settings() -> dict:
    return {
        "fourcc": "MJPG",
        "frame_width": 4000,
        "frame_height": 3000,
        "fps": 10.0,
        "autofocus": 0.0,
        "focus": 20.0,
        "auto_exposure": 0.25,
        "exposure": -4.0,
        "auto_white_balance": 0.0,
        "white_balance_temperature": 4600.0,
    }


def _camera(*, index: int = 0) -> dict:
    settings = _settings()
    return {
        "camera_id": "48MP USB Camera",
        "instance_id": "@device_pnp_vid_32e4&pid_4801_hold_fixture",
        "index": index,
        "backend": "DSHOW",
        "requested_settings": settings,
        "effective_settings_before_frame": deepcopy(settings),
        "effective_settings_after_frame": deepcopy(settings),
        "set_results": {key: True for key in settings},
    }


def _camera_lock(camera: dict, *, full: bool) -> dict:
    return {
        "camera_id": camera["camera_id"],
        "camera_instance_id": camera["instance_id"],
        "camera_usb_identity": "VID_32E4:PID_4801",
        "camera_index": camera["index"],
        "backend": camera["backend"],
        "requested_settings": deepcopy(camera["requested_settings"]),
        "effective_settings_before_frame": deepcopy(
            camera["effective_settings_before_frame"]
        ),
        "effective_settings_after_frame": deepcopy(
            camera["effective_settings_after_frame"]
        ),
        "setting_write_results": deepcopy(camera["set_results"]),
        "manual_focus_exposure_white_balance_gate": True,
        "mount_id": "fixed-hold-mount",
        "full_panel_visible": full,
        "coverage_scope": "full_panel" if full else "partial_panel",
    }


def _candidate_cell(
    controller: str,
    recipe: int,
    repeat: int,
    snapshot: str,
    *,
    bad_edge: tuple[str, int, int] | None,
) -> dict:
    index = recipe * 4 + repeat
    row, column = divmod(index, 8)
    shift = {"t0": 0.0, "t1": 1.0, "t2": 2.0}[snapshot]
    clean = bad_edge != (controller, recipe, repeat)
    return {
        "sample_id": f"{controller}-R{recipe:02d}-P{repeat}",
        "controller": controller,
        "recipe": recipe,
        "repeat_position": repeat,
        "row": row,
        "column": column,
        "local_roi": {"x": column * 10, "y": row * 10, "width": 8, "height": 8},
        "panel_roi": {
            "x": column * 10 + (0 if controller == "CS1" else 512),
            "y": row * 10,
            "width": 8,
            "height": 8,
        },
        "central_inset_fraction": 0.2,
        "lab": [30.0 + recipe * 2 + repeat * 0.05 + shift, 5.0, -8.0],
        "bottom_edge_clean": clean,
        "horizontal_stripe_absent": clean,
        "vertical_stripe_absent": clean,
        "roi_visible": True,
    }


def _probe_cells(snapshot: str, *, retain_h1: bool = True) -> list[dict]:
    levels = {
        "t0": {"H1": 90.0, "H2": 90.0},
        "t1": {"H1": 51.0, "H2": 91.0},
        "t2": {"H1": 52.0 if retain_h1 else 82.0, "H2": 57.0},
    }[snapshot]
    values = []
    for controller in ("CS1", "CS2"):
        for probe in ("H1", "H2"):
            spec = PROBE_SPEC[probe]
            values.append(
                {
                    "sample_id": f"{controller}-{probe}",
                    "controller": controller,
                    "probe": probe,
                    "local_roi": {
                        key: spec[key] for key in ("x", "y", "width", "height")
                    },
                    "panel_roi": {
                        "x": spec["x"] + (0 if controller == "CS1" else 512),
                        "y": spec["y"],
                        "width": spec["width"],
                        "height": spec["height"],
                    },
                    "lab": [levels[probe], 0.0, 0.0],
                    "top_edge_clean": True,
                    "right_edge_clean": True,
                    "bottom_edge_clean": True,
                    "left_edge_clean": True,
                    "central_inset_purity_pass": True,
                    "roi_visible": True,
                }
            )
    return values


def _snapshot(
    root: Path,
    key: str,
    *,
    visible_recipes: range,
    probes_visible: bool,
    camera_index: int = 0,
    bad_edge: tuple[str, int, int] | None = None,
    retain_h1: bool = True,
    prior_override: str | None = None,
    boot_override: str | None = None,
) -> tuple[Path, dict]:
    frozen = FROZEN_SNAPSHOTS[key]
    folder = root / key
    folder.mkdir(parents=True)
    action_path = folder / "action.json"
    action_identity = {
        "ordinal": frozen["ordinal"],
        "action_id": frozen["action_id"],
        "descriptor_id": frozen["descriptor_id"],
        "prior_action_id": prior_override or frozen["prior_action_id"],
        "role": frozen["role"],
    }
    boot_nonce = boot_override or ("v3-boot" if key == "t0" else "hold-boot")
    action_root = _seal(
        {
            "schema_version": 1,
            "kind": frozen["result_kind"],
            "firmware_sha256": frozen["firmware_sha256"],
            "boot_nonce": boot_nonce,
            "action": action_identity,
            "terminal_report": {
                "campaign_id": frozen["campaign_id"],
                "contract_id": frozen["contract_id"],
                "terminal_state": "COMPLETE",
                "result": True,
                "ordinal": frozen["ordinal"],
                "descriptor_id": frozen["descriptor_id"],
                "action_id": frozen["action_id"],
                "role": frozen["role"],
                "driver_called": True,
                "driver_call_count_for_action": 1,
                "total_driver_call_count": frozen["total_driver_call_count"],
                "no_retry": True,
                "no_recovery": True,
            },
            "outcome": "complete_pass",
            "visible_refreshes": 1,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        }
    )
    action_payload, action_file_sha = _write_json(action_path, action_root)

    photo_path = folder / "capture.jpg"
    photo_payload = f"synthetic-hold-photo-{key}".encode()
    photo_path.write_bytes(photo_payload)
    photo_sha = _digest(photo_payload)

    camera = _camera(index=camera_index)
    full = len(visible_recipes) == 16
    capture_id = _digest(f"capture-{key}")
    sidecar_path = folder / "capture.json"
    sidecar_root = _seal(
        {
            "schema_version": 1,
            "kind": f"synthetic-{key}-capture",
            "capture_binding": "live_synchronized",
            "campaign_id": frozen["campaign_id"],
            "test_id": frozen["test_id"],
            "contract_id": frozen["contract_id"],
            "ordinal": frozen["ordinal"],
            "action_id": frozen["action_id"],
            "descriptor_id": frozen["descriptor_id"],
            "role": frozen["role"],
            "capture_id": capture_id,
            "camera": camera,
            "coverage": {
                "scope": "full_panel" if full else "partial_panel",
                "full_panel_visible": full,
                "full_panel_uncropped": full,
                "mount_id": "fixed-hold-mount",
            },
            "action_result": {
                "path": str(action_path),
                "bytes": len(action_payload),
                "file_sha256": action_file_sha,
                "canonical_integrity_sha256": action_root["integrity"]["sha256"],
            },
            "photo": {
                "path": str(photo_path),
                "bytes": len(photo_payload),
                "sha256": photo_sha,
            },
        }
    )
    sidecar_payload, sidecar_sha = _write_json(sidecar_path, sidecar_root)

    measurements = [
        _candidate_cell(
            controller,
            recipe,
            repeat,
            key,
            bad_edge=bad_edge,
        )
        for controller in ("CS1", "CS2")
        for recipe in visible_recipes
        for repeat in range(4)
    ]
    observation = _seal(
        {
            "schema_version": 1,
            "kind": f"synthetic-{key}-observation",
            "stage": frozen["stage"],
            "controller_policy": "CS1_AND_CS2_EVALUATED_SEPARATELY",
            "spatial_dither": False,
            "roi_manifest_sha256": _digest("common-hold-roi-manifest"),
            "measurements": measurements,
            "hold_probe_measurements": (
                _probe_cells(key, retain_h1=retain_h1) if probes_visible else []
            ),
            "qualified_colour_count": 0,
            "qualified_gray_levels": 0,
            "qualified_brightness_levels": 0,
            "automatic_colour_qualification": False,
        }
    )
    analysis = _seal(
        {
            "schema_version": 1,
            "kind": frozen["analysis_kind"],
            "campaign_id": frozen["campaign_id"],
            "test_id": frozen["test_id"],
            "contract_id": frozen["contract_id"],
            "stage": frozen["stage"],
            "source_evidence": {
                "action": {
                    "path": str(action_path),
                    "bytes": len(action_payload),
                    "file_sha256": action_file_sha,
                    "canonical_integrity_sha256": action_root["integrity"]["sha256"],
                },
                "capture_sidecar": {
                    "path": str(sidecar_path),
                    "bytes": len(sidecar_payload),
                    "file_sha256": sidecar_sha,
                    "canonical_integrity_sha256": sidecar_root["integrity"]["sha256"],
                    "capture_id": capture_id,
                },
                "photo": {
                    "path": str(photo_path),
                    "bytes": len(photo_payload),
                    "file_sha256": photo_sha,
                },
            },
            "camera_lock": _camera_lock(camera, full=full),
            "geometry": {"gate_pass": True, "method": "FIXED_HOLD_HOMOGRAPHY"},
            "capture_quality": {
                "geometry_gate_pass": True,
                "manual_camera_lock_gate_pass": True,
                "exposure_gate_pass": True,
                "coarse_uniformity_gate_pass": True,
            },
            "observation_document": observation,
            "method": {
                "controllers_pooled": False,
                "spatial_dither": False,
                "rectification_scale": 2,
            },
            "quality_thresholds": {"geometry": "synthetic-common"},
            "hardware_accessed": False,
            "camera_accessed": False,
            "network_requests": 0,
        }
    )
    analysis_path = folder / "analysis.json"
    analysis_payload, analysis_sha = _write_json(analysis_path, analysis)
    entry = {
        "label": frozen["label"],
        "campaign_id": frozen["campaign_id"],
        "test_id": frozen["test_id"],
        "contract_id": frozen["contract_id"],
        "stage": frozen["stage"],
        "analysis_kind": frozen["analysis_kind"],
        "analysis": {
            "file_sha256": analysis_sha,
            "canonical_integrity_sha256": analysis["integrity"]["sha256"],
        },
        "action": {
            "ordinal": frozen["ordinal"],
            "action_id": frozen["action_id"],
            "descriptor_id": frozen["descriptor_id"],
            "prior_action_id": frozen["prior_action_id"],
            "role": frozen["role"],
            "firmware_sha256": frozen["firmware_sha256"],
            "result_kind": frozen["result_kind"],
            "file_sha256": action_file_sha,
            "canonical_integrity_sha256": action_root["integrity"]["sha256"],
        },
        "capture_sidecar": {
            "file_sha256": sidecar_sha,
            "canonical_integrity_sha256": sidecar_root["integrity"]["sha256"],
            "capture_id": capture_id,
        },
        "jpeg": {"file_sha256": photo_sha},
    }
    assert analysis_payload
    return analysis_path, entry


def _case(
    tmp_path: Path,
    *,
    visible_recipes: range = range(16),
    probes_visible: bool = True,
    t2_camera_index: int = 0,
    t2_bad_edge: tuple[str, int, int] | None = None,
    retain_h1: bool = True,
    t2_prior_override: str | None = None,
    t2_boot_override: str | None = None,
) -> tuple[dict[str, Path], dict]:
    paths: dict[str, Path] = {}
    entries = {}
    for key in ("t0", "t1", "t2"):
        path, entry = _snapshot(
            tmp_path,
            key,
            visible_recipes=visible_recipes,
            probes_visible=probes_visible,
            camera_index=t2_camera_index if key == "t2" else 0,
            bad_edge=t2_bad_edge if key == "t2" else None,
            retain_h1=retain_h1,
            prior_override=t2_prior_override if key == "t2" else None,
            boot_override=t2_boot_override if key == "t2" else None,
        )
        paths[key] = path
        entries[key] = entry
    contract = seal_position_balanced_hold_identity_contract(
        {
            "schema_version": 1,
            "kind": IDENTITY_CONTRACT_KIND,
            "comparison_id": "position-balanced-hold-fixture",
            "snapshots": entries,
            "review_thresholds": deepcopy(DEFAULT_REVIEW_THRESHOLDS),
            "probe_spec": deepcopy(PROBE_SPEC),
            "qualification_boundary": {
                "camera_relative_review_only": True,
                "controller_palette_evidence_pass_forbidden": True,
                "direct_passed_evidence_generation_forbidden": True,
                "qualified_colour_count": 0,
                "qualified_gray_levels": 0,
                "qualified_brightness_levels": 0,
            },
        }
    )
    return paths, contract


def _compare(case: tuple[dict[str, Path], dict]) -> dict:
    paths, contract = case
    return compare_position_balanced_hold(
        paths["t0"], paths["t1"], paths["t2"], identity_contract=contract
    )


def test_full_t0_t1_t2_emits_two_review_drafts_without_qualification(
    tmp_path: Path,
) -> None:
    result = _compare(_case(tmp_path))
    verify_position_balanced_hold_comparison(result)

    assert result["kind"] == COMPARISON_KIND
    assert result["comparability"]["full_128_cell_coverage"] is True
    assert result["probe_review"]["h1_retained_at_t2"] is True
    assert result["probe_review"]["h2_appeared_at_t2"] is True
    assert result["same_profile_local_hold_review_draft"]["status"].startswith(
        "REVIEW_DRAFT_SUPPORTS"
    )
    assert result["commented_retains_active_directional_cross_lut_review_draft"][
        "status"
    ].startswith("REVIEW_DRAFT_SUPPORTS")
    assert result["qualification_boundary"]["qualified_colour_count"] == 0
    assert (
        result["qualification_boundary"]["controller_palette_evidence_passed"] is False
    )


def test_partial_without_visible_probes_is_review_and_cross_lut_untested(
    tmp_path: Path,
) -> None:
    result = _compare(_case(tmp_path, visible_recipes=range(3), probes_visible=False))

    assert result["comparability"]["visible_cell_count"] == 24
    assert result["same_profile_local_hold_review_draft"]["status"] == (
        "REVIEW_DRAFT_PARTIAL_OR_GATE_FAILED"
    )
    assert (
        result["commented_retains_active_directional_cross_lut_review_draft"]["status"]
        == "UNTESTED_PROBES_NOT_VISIBLE"
    )
    for transition in result["candidate_comparisons"].values():
        reviewed = [
            item
            for item in transition["recipe_results"]
            if item["status"] == "REVIEWED_COMPLETE_REPLICA_SET"
        ]
        assert len(reviewed) == 6


def test_action_chain_prior_action_is_deeply_checked(tmp_path: Path) -> None:
    case = _case(tmp_path, t2_prior_override=_digest("wrong-prior"))
    with pytest.raises(
        PositionBalancedHoldCompareError, match="action chain prior_action_id"
    ):
        _compare(case)


def test_h1_h2_must_share_same_boot(tmp_path: Path) -> None:
    with pytest.raises(PositionBalancedHoldCompareError, match="boot nonce differs"):
        _compare(_case(tmp_path, t2_boot_override="other-hold-boot"))


def test_exact_camera_instance_index_and_settings_are_required(tmp_path: Path) -> None:
    with pytest.raises(PositionBalancedHoldCompareError, match="camera instance/index"):
        _compare(_case(tmp_path, t2_camera_index=1))


def test_tampered_jpeg_breaks_deep_hash_binding(tmp_path: Path) -> None:
    case = _case(tmp_path)
    t2 = json.loads(case[0]["t2"].read_text(encoding="utf-8"))
    Path(t2["source_evidence"]["photo"]["path"]).write_bytes(b"tampered")
    with pytest.raises(PositionBalancedHoldCompareError, match="JPEG byte/hash"):
        _compare(case)


def test_candidate_edge_failure_stays_review_only(tmp_path: Path) -> None:
    result = _compare(_case(tmp_path, t2_bad_edge=("CS1", 0, 0)))
    recipe = next(
        item
        for item in result["candidate_comparisons"]["t2_vs_t0"]["recipe_results"]
        if item["controller"] == "CS1" and item["recipe"] == 0
    )
    assert recipe["four_edge_purity_gate_pass"] is False
    assert recipe["review_gate_pass"] is False
    assert (
        result["qualification_boundary"]["controller_palette_evidence_passed"] is False
    )


def test_failed_h1_retention_rejects_directional_cross_lut_draft(
    tmp_path: Path,
) -> None:
    result = _compare(_case(tmp_path, retain_h1=False))
    assert result["probe_review"]["h1_retained_at_t2"] is False
    assert (
        result["commented_retains_active_directional_cross_lut_review_draft"]["status"]
        == "REVIEW_DRAFT_GATE_FAILED"
    )


def test_contract_rejects_non_frozen_h2_identity(tmp_path: Path) -> None:
    _paths, sealed = _case(tmp_path)
    unsigned = deepcopy(sealed)
    unsigned.pop("integrity")
    unsigned["snapshots"]["t2"]["action"]["action_id"] = _digest("generic-h2")
    with pytest.raises(PositionBalancedHoldCompareError, match="t2.action.action_id"):
        seal_position_balanced_hold_identity_contract(unsigned)


def test_integrity_export_is_exclusive_and_tamper_is_detected(tmp_path: Path) -> None:
    result = _compare(_case(tmp_path / "case"))
    output = tmp_path / "review" / "hold.json"
    assert export_position_balanced_hold_comparison(result, output) == output
    loaded = json.loads(output.read_text(encoding="utf-8"))
    verify_position_balanced_hold_comparison(loaded)
    with pytest.raises(PositionBalancedHoldCompareError, match="already exists"):
        export_position_balanced_hold_comparison(result, output)
    loaded["qualification_boundary"]["qualified_colour_count"] = 1
    with pytest.raises(PositionBalancedHoldCompareError, match="canonical SHA-256"):
        verify_position_balanced_hold_comparison(loaded)
