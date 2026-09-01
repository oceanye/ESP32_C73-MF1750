from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from host.static_photo.common import canonical_sha256
from host.static_photo.fresh_reconstruction_compare import (
    ANALYSIS_KIND,
    DEFAULT_REVIEW_THRESHOLDS,
    FIRST_LABEL,
    FreshReconstructionCompareError,
    IDENTITY_CONTRACT_KIND,
    RECONSTRUCTION_LABEL,
    compare_fresh_white_reconstruction,
    export_fresh_reconstruction_comparison,
    seal_fresh_reconstruction_identity_contract,
    verify_fresh_reconstruction_comparison,
)


def _sha(label: str | bytes) -> str:
    payload = label if isinstance(label, bytes) else label.encode()
    return hashlib.sha256(payload).hexdigest()


def _seal(value: dict) -> dict:
    body = deepcopy(value)
    body["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": canonical_sha256(value),
    }
    return body


def _write_json(path: Path, value: dict) -> tuple[bytes, str]:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    path.write_bytes(payload)
    return payload, _sha(payload)


def _payload_identity(ordinal: int, field: str) -> dict:
    return {"bytes": 100 + ordinal, "sha256": _sha(f"payload-G{ordinal}-{field}")}


def _core_actions(prefix: str) -> list[dict]:
    roles = ("SOURCE", "MIDDLE", "TARGET")
    return [
        {
            "ordinal": ordinal,
            "action_id": _sha(f"{prefix}-action-{ordinal}"),
            "descriptor_id": _sha(f"{prefix}-descriptor-{ordinal}"),
            "role": roles[ordinal - 1],
            "frame": _payload_identity(ordinal, "frame"),
            "cs1_dtm": _payload_identity(ordinal, "cs1_dtm"),
            "cs2_dtm": _payload_identity(ordinal, "cs2_dtm"),
        }
        for ordinal in (1, 2, 3)
    ]


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


def _camera(override: dict | None = None) -> dict:
    settings = _settings()
    value = {
        "camera_id": "48MP USB Camera",
        "instance_id": "@device_pnp_vid_32e4&pid_4801_fixed",
        "index": 0,
        "backend": "DSHOW",
        "requested_settings": settings,
        "effective_settings_before_frame": deepcopy(settings),
        "effective_settings_after_frame": deepcopy(settings),
        "set_results": {key: True for key in settings},
    }
    if override:
        value.update(override)
    return value


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
        "mount_id": "fixed-mount",
        "full_panel_visible": full,
    }


def _cell(
    controller: str,
    recipe: int,
    repeat: int,
    *,
    reconstruction: bool,
    changed_recipe: tuple[str, int] | None,
    bad_edge: tuple[str, int, int] | None,
) -> dict:
    index = recipe * 4 + repeat
    row, column = divmod(index, 8)
    global_shift = 1.0 if reconstruction else 0.0
    changed = 10.0 if reconstruction and changed_recipe == (controller, recipe) else 0.0
    edge_clear = bad_edge != (controller, recipe, repeat)
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
        "lab": [
            25.0 + recipe * 2.0 + repeat * 0.05 + global_shift + changed,
            8.0 + recipe * 0.1,
            -12.0 + recipe * 0.1,
        ],
        "bottom_edge_clean": edge_clear,
        "horizontal_stripe_absent": edge_clear,
        "vertical_stripe_absent": True,
        "roi_visible": True,
    }


def _measurements(
    *,
    reconstruction: bool,
    visible_recipes: range,
    changed_recipe: tuple[str, int] | None = None,
    bad_edge: tuple[str, int, int] | None = None,
) -> list[dict]:
    return [
        _cell(
            controller,
            recipe,
            repeat,
            reconstruction=reconstruction,
            changed_recipe=changed_recipe,
            bad_edge=bad_edge,
        )
        for controller in ("CS1", "CS2")
        for recipe in visible_recipes
        for repeat in range(4)
    ]


def _construction(
    root: Path,
    *,
    prefix: str,
    label: str,
    reconstruction: bool,
    visible_recipes: range,
    changed_recipe: tuple[str, int] | None = None,
    bad_edge: tuple[str, int, int] | None = None,
    camera_override: dict | None = None,
    geometry_method: str = "SEALED_FIXED_MOUNT_HOMOGRAPHY",
) -> tuple[Path, dict]:
    folder = root / prefix
    folder.mkdir(parents=True)
    campaign = f"CAMPAIGN-{prefix}"
    test_id = f"TEST-{prefix}"
    contract_id = _sha(f"contract-{prefix}")
    core = _core_actions(prefix)
    action_identity = core[2]

    action_path = folder / "action-g3.json"
    action_root = _seal(
        {
            "schema_version": 1,
            "kind": f"test-{prefix}-result",
            "action": deepcopy(action_identity),
            "terminal_report": {
                "campaign_id": campaign,
                "test_id": test_id,
                "contract_id": contract_id,
            },
        }
    )
    action_payload, action_file_sha = _write_json(action_path, action_root)

    photo_path = folder / "photo.jpg"
    photo_payload = f"synthetic-jpeg-{prefix}".encode()
    photo_path.write_bytes(photo_payload)
    photo_sha = _sha(photo_payload)

    camera = _camera(camera_override)
    full = len(visible_recipes) == 16
    sidecar_path = folder / "capture.json"
    capture_id = _sha(f"capture-{prefix}")
    sidecar_root = _seal(
        {
            "schema_version": 1,
            "kind": f"test-{prefix}-capture",
            "capture_binding": "live_synchronized",
            "campaign_id": campaign,
            "test_id": test_id,
            "contract_id": contract_id,
            "ordinal": 3,
            "action_id": action_identity["action_id"],
            "descriptor_id": action_identity["descriptor_id"],
            "role": action_identity["role"],
            "capture_id": capture_id,
            "camera": camera,
            "coverage": {
                "scope": "full_panel" if full else "partial_panel",
                "full_panel_visible": full,
                "full_panel_uncropped": full,
                "mount_id": "fixed-mount",
                "note": None,
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
    sidecar_payload, sidecar_file_sha = _write_json(sidecar_path, sidecar_root)

    measurements = _measurements(
        reconstruction=reconstruction,
        visible_recipes=visible_recipes,
        changed_recipe=changed_recipe,
        bad_edge=bad_edge,
    )
    observation = _seal(
        {
            "schema_version": 1,
            "kind": "synthetic-position-balanced-v3-observation",
            "stage": "G3",
            "controller_policy": "CS1_AND_CS2_EVALUATED_SEPARATELY",
            "spatial_dither": False,
            "roi_manifest_sha256": _sha("common-roi-manifest"),
            "measurements": measurements,
            "thresholds": {
                "max_position_delta_e76": 8.0,
                "max_g3_g4_repeat_delta_e76": 8.0,
                "max_neutral_chroma": 10.0,
                "min_mechanism_delta_l": 4.0,
            },
            "qualified_colour_count": 0,
            "qualified_gray_levels": 0,
            "qualified_brightness_levels": 0,
            "automatic_colour_qualification": False,
        }
    )
    analysis = _seal(
        {
            "schema_version": 1,
            "kind": ANALYSIS_KIND,
            "campaign_id": campaign,
            "test_id": test_id,
            "contract_id": contract_id,
            "stage": "G3",
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
                    "file_sha256": sidecar_file_sha,
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
            "geometry": {"gate_pass": True, "method": geometry_method},
            "capture_quality": {
                "geometry_gate_pass": True,
                "full_panel_visible": full,
                "manual_camera_lock_gate_pass": True,
                "exposure_gate_pass": True,
                "coarse_uniformity_gate_pass": True,
            },
            "observation_document": observation,
            "controller_local_screen": {
                "controller_policy": "CS1_AND_CS2_NEVER_POOLED",
                "recipes_per_controller": 16,
                "replicates_per_recipe": 4,
                "qualified_colour_count": 0,
                "qualified_gray_levels": 0,
                "qualified_brightness_levels": 0,
            },
            "method": {
                "camera": "48MP VID_32E4:PID_4801 only",
                "rectification_scale": 2,
                "controllers_pooled": False,
                "spatial_dither": False,
            },
            "quality_thresholds": {"geometry": "synthetic-common"},
            "qualification_boundary": {
                "absolute_colour_claimed": False,
                "cross_controller_equivalence_claimed": False,
                "qualified_colour_count": 0,
                "qualified_gray_levels": 0,
                "qualified_brightness_levels": 0,
            },
            "hardware_accessed": False,
            "camera_accessed": False,
            "network_requests": 0,
        }
    )
    analysis_path = folder / "analysis.json"
    analysis_payload, analysis_file_sha = _write_json(analysis_path, analysis)
    contract_entry = {
        "label": label,
        "campaign_id": campaign,
        "test_id": test_id,
        "contract_id": contract_id,
        "stage": "G3",
        "analysis": {
            "file_sha256": analysis_file_sha,
            "canonical_integrity_sha256": analysis["integrity"]["sha256"],
        },
        "action": {
            "ordinal": 3,
            "action_id": action_identity["action_id"],
            "descriptor_id": action_identity["descriptor_id"],
            "role": action_identity["role"],
            "file_sha256": action_file_sha,
            "canonical_integrity_sha256": action_root["integrity"]["sha256"],
        },
        "capture_sidecar": {
            "file_sha256": sidecar_file_sha,
            "canonical_integrity_sha256": sidecar_root["integrity"]["sha256"],
            "capture_id": capture_id,
        },
        "jpeg": {"file_sha256": photo_sha},
        "packer": {
            "report_canonical_sha256": _sha(f"packer-report-{prefix}"),
            "core_actions": core,
        },
    }
    assert len(analysis_payload) > 0
    return analysis_path, contract_entry


def _case(
    tmp_path: Path,
    *,
    visible_recipes: range = range(16),
    changed_recipe: tuple[str, int] | None = None,
    bad_edge: tuple[str, int, int] | None = None,
    reconstruction_camera_override: dict | None = None,
    reconstruction_geometry_method: str = "SEALED_FIXED_MOUNT_HOMOGRAPHY",
) -> tuple[Path, Path, dict]:
    first_path, first = _construction(
        tmp_path,
        prefix="first",
        label=FIRST_LABEL,
        reconstruction=False,
        visible_recipes=visible_recipes,
    )
    reconstruction_path, reconstruction = _construction(
        tmp_path,
        prefix="reconstruction",
        label=RECONSTRUCTION_LABEL,
        reconstruction=True,
        visible_recipes=visible_recipes,
        changed_recipe=changed_recipe,
        bad_edge=bad_edge,
        camera_override=reconstruction_camera_override,
        geometry_method=reconstruction_geometry_method,
    )
    contract = seal_fresh_reconstruction_identity_contract(
        {
            "schema_version": 1,
            "kind": IDENTITY_CONTRACT_KIND,
            "comparison_id": "fresh-white-reconstruction-fixture",
            "first_construction": first,
            "fresh_reconstruction": reconstruction,
            "packer_isomorphism": {
                "method": "PACKER_THREE_FRAME_BYTE_IDENTITY",
                "required_ordinals": [1, 2, 3],
                "payload_fields": ["frame", "cs1_dtm", "cs2_dtm"],
                "bytewise_identity_required": True,
                "spatial_dithering_allowed": False,
            },
            "review_thresholds": deepcopy(DEFAULT_REVIEW_THRESHOLDS),
            "qualification_boundary": {
                "camera_relative_review_only": True,
                "controller_palette_evidence_pass_forbidden": True,
                "automatic_colour_or_gray_claim_forbidden": True,
                "qualified_colour_count": 0,
                "qualified_gray_levels": 0,
                "qualified_lightness_levels": 0,
            },
        }
    )
    return first_path, reconstruction_path, contract


def _compare(case: tuple[Path, Path, dict]) -> dict:
    first, reconstruction, contract = case
    return compare_fresh_white_reconstruction(
        first, reconstruction, identity_contract=contract
    )


def test_full_128_cell_fresh_reconstruction_review_passes_without_qualification(
    tmp_path: Path,
) -> None:
    result = _compare(_case(tmp_path))
    verify_fresh_reconstruction_comparison(result)

    assert result["decision"] == "FRESH_RECONSTRUCTION_REVIEW_PASS"
    assert len(result["cell_results"]) == 128
    assert len(result["recipe_results"]) == 32
    assert result["comparability"]["full_128_cell_coverage"] is True
    assert all(item["replica_count"] == 4 for item in result["recipe_results"])
    assert all(
        item["fresh_reconstruction_review_gate_pass"]
        for item in result["recipe_results"]
    )
    assert result["qualification_boundary"]["qualified_colour_count"] == 0
    assert result["qualification_boundary"]["qualified_gray_levels"] == 0
    assert result["qualification_boundary"]["qualified_lightness_levels"] == 0
    assert (
        result["evidence_draft"][
            "direct_controller_palette_evidence_conversion_allowed"
        ]
        is False
    )
    assert result["execution_boundary"]["hardware_accessed"] is False


def test_partial_camera_accepts_exact_visible_set_and_reviews_only_complete_recipes(
    tmp_path: Path,
) -> None:
    result = _compare(_case(tmp_path, visible_recipes=range(3)))

    assert result["decision"] == "FRESH_RECONSTRUCTION_REVIEW_FAIL"
    assert result["comparability"]["coverage_scope"] == "partial_panel"
    assert result["comparability"]["visible_cell_count"] == 24
    assert result["comparability"]["full_128_cell_coverage"] is False
    for controller in ("CS1", "CS2"):
        summary = result["controller_results"][controller]
        assert summary["visible_cell_count"] == 12
        assert summary["reviewed_complete_recipe_count"] == 3
        assert summary["untested_missing_replica_recipe_count"] == 13
        assert summary["fresh_reconstruction_review_pass"] is False
    reviewed = [
        item
        for item in result["recipe_results"]
        if item["status"] == "REVIEWED_COMPLETE_REPLICA_SET"
    ]
    untested = [
        item
        for item in result["recipe_results"]
        if item["status"] == "UNTESTED_MISSING_REPLICAS"
    ]
    assert len(reviewed) == 6
    assert all(item["fresh_reconstruction_review_gate_pass"] for item in reviewed)
    assert len(untested) == 26
    assert all(not item["fresh_reconstruction_review_gate_pass"] for item in untested)


def test_partial_camera_rejects_different_visible_cell_sets(tmp_path: Path) -> None:
    first, reconstruction, contract = _case(tmp_path, visible_recipes=range(4))
    root = json.loads(reconstruction.read_text(encoding="utf-8"))
    root.pop("integrity")
    observation = root["observation_document"]
    observation.pop("integrity")
    observation["measurements"].pop()
    root["observation_document"] = _seal(observation)
    changed = _seal(root)
    payload, digest = _write_json(reconstruction, changed)
    contract_unsigned = deepcopy(contract)
    contract_unsigned.pop("integrity")
    contract_unsigned["fresh_reconstruction"]["analysis"] = {
        "file_sha256": digest,
        "canonical_integrity_sha256": changed["integrity"]["sha256"],
    }
    rebound = seal_fresh_reconstruction_identity_contract(contract_unsigned)
    assert payload

    with pytest.raises(FreshReconstructionCompareError, match="sample IDs differ"):
        compare_fresh_white_reconstruction(
            first, reconstruction, identity_contract=rebound
        )


def test_partial_camera_does_not_fill_one_missing_replica_from_elsewhere(
    tmp_path: Path,
) -> None:
    first, reconstruction, contract = _case(tmp_path, visible_recipes=range(4))
    unsigned_contract = deepcopy(contract)
    unsigned_contract.pop("integrity")
    for path, contract_key in (
        (first, "first_construction"),
        (reconstruction, "fresh_reconstruction"),
    ):
        root = json.loads(path.read_text(encoding="utf-8"))
        root.pop("integrity")
        observation = root["observation_document"]
        observation.pop("integrity")
        observation["measurements"] = [
            cell
            for cell in observation["measurements"]
            if cell["sample_id"] != "CS1-R03-P3"
        ]
        root["observation_document"] = _seal(observation)
        changed = _seal(root)
        _payload, digest = _write_json(path, changed)
        unsigned_contract[contract_key]["analysis"] = {
            "file_sha256": digest,
            "canonical_integrity_sha256": changed["integrity"]["sha256"],
        }
    rebound = seal_fresh_reconstruction_identity_contract(unsigned_contract)
    result = compare_fresh_white_reconstruction(
        first, reconstruction, identity_contract=rebound
    )
    missing = next(
        item
        for item in result["recipe_results"]
        if item["controller"] == "CS1" and item["recipe"] == 3
    )

    assert missing["replica_count"] == 3
    assert missing["status"] == "UNTESTED_MISSING_REPLICAS"
    assert missing["fresh_reconstruction_review_gate_pass"] is False
    assert (
        result["controller_results"]["CS1"]["untested_missing_replica_recipe_count"]
        == 13
    )


def test_recipe_with_real_reconstruction_shift_fails_review(tmp_path: Path) -> None:
    result = _compare(_case(tmp_path, changed_recipe=("CS1", 0)))
    recipe = next(
        item
        for item in result["recipe_results"]
        if item["controller"] == "CS1" and item["recipe"] == 0
    )

    assert result["decision"] == "FRESH_RECONSTRUCTION_REVIEW_FAIL"
    assert recipe["reconstruction_metric_gate_pass"] is False
    assert recipe["controller_palette_evidence_passed"] is False


def test_edge_failure_is_reported_as_review_fail_not_qualification(
    tmp_path: Path,
) -> None:
    result = _compare(_case(tmp_path, bad_edge=("CS2", 2, 1)))
    recipe = next(
        item
        for item in result["recipe_results"]
        if item["controller"] == "CS2" and item["recipe"] == 2
    )
    assert result["decision"] == "FRESH_RECONSTRUCTION_REVIEW_FAIL"
    assert recipe["boundary_gate_pass"] is False
    assert recipe["fresh_reconstruction_review_gate_pass"] is False
    assert (
        result["qualification_boundary"]["controller_palette_evidence_passed"] is False
    )


def test_contract_rejects_same_campaign_or_g3_action(tmp_path: Path) -> None:
    _first, _reconstruction, sealed = _case(tmp_path)
    contract = deepcopy(sealed)
    contract.pop("integrity")
    contract["fresh_reconstruction"]["campaign_id"] = contract["first_construction"][
        "campaign_id"
    ]
    with pytest.raises(
        FreshReconstructionCompareError, match="campaigns must be different"
    ):
        seal_fresh_reconstruction_identity_contract(contract)


def test_contract_rejects_non_isomorphic_packer_payload(tmp_path: Path) -> None:
    _first, _reconstruction, sealed = _case(tmp_path)
    contract = deepcopy(sealed)
    contract.pop("integrity")
    contract["fresh_reconstruction"]["packer"]["core_actions"][1]["cs2_dtm"][
        "sha256"
    ] = _sha("different-optical-payload")
    with pytest.raises(FreshReconstructionCompareError, match="G2.cs2_dtm"):
        seal_fresh_reconstruction_identity_contract(contract)


def test_exact_48mp_settings_and_geometry_are_required(tmp_path: Path) -> None:
    camera_case = _case(
        tmp_path / "camera",
        reconstruction_camera_override={"index": 1},
    )
    with pytest.raises(FreshReconstructionCompareError, match="camera identity/index"):
        _compare(camera_case)

    geometry_case = _case(
        tmp_path / "geometry",
        reconstruction_geometry_method="DIFFERENT_GEOMETRY",
    )
    with pytest.raises(FreshReconstructionCompareError, match="geometry differs"):
        _compare(geometry_case)


def test_non_4000x3000_capture_is_rejected(tmp_path: Path) -> None:
    changed = _camera()
    requested = deepcopy(changed["requested_settings"])
    requested["frame_width"] = 1920
    changed["requested_settings"] = requested
    case = _case(tmp_path, reconstruction_camera_override=changed)
    with pytest.raises(FreshReconstructionCompareError, match="not 4000x3000"):
        _compare(case)


def test_source_jpeg_tampering_breaks_exact_hash_binding(tmp_path: Path) -> None:
    case = _case(tmp_path)
    reconstruction = case[1]
    report = json.loads(reconstruction.read_text(encoding="utf-8"))
    Path(report["source_evidence"]["photo"]["path"]).write_bytes(b"tampered")
    with pytest.raises(FreshReconstructionCompareError, match="JPEG byte/hash"):
        _compare(case)


def test_spatial_dither_boundary_is_rejected(tmp_path: Path) -> None:
    first, reconstruction, contract = _case(tmp_path)
    root = json.loads(reconstruction.read_text(encoding="utf-8"))
    root.pop("integrity")
    observation = root["observation_document"]
    observation.pop("integrity")
    observation["spatial_dither"] = True
    root["observation_document"] = _seal(observation)
    changed = _seal(root)
    _payload, digest = _write_json(reconstruction, changed)
    unsigned_contract = deepcopy(contract)
    unsigned_contract.pop("integrity")
    unsigned_contract["fresh_reconstruction"]["analysis"] = {
        "file_sha256": digest,
        "canonical_integrity_sha256": changed["integrity"]["sha256"],
    }
    rebound = seal_fresh_reconstruction_identity_contract(unsigned_contract)
    with pytest.raises(FreshReconstructionCompareError, match="observation boundary"):
        compare_fresh_white_reconstruction(
            first, reconstruction, identity_contract=rebound
        )


def test_comparison_integrity_export_and_tamper_detection(tmp_path: Path) -> None:
    result = _compare(_case(tmp_path / "case"))
    output = tmp_path / "result" / "fresh-reconstruction.json"
    assert export_fresh_reconstruction_comparison(result, output) == output
    loaded = json.loads(output.read_text(encoding="utf-8"))
    verify_fresh_reconstruction_comparison(loaded)

    loaded["recipe_results"][0]["controller"] = "CS2"
    with pytest.raises(FreshReconstructionCompareError, match="canonical SHA-256"):
        verify_fresh_reconstruction_comparison(loaded)
    with pytest.raises(FreshReconstructionCompareError, match="already exists"):
        export_fresh_reconstruction_comparison(result, output)
