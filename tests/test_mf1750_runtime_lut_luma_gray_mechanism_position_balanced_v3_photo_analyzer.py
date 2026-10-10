from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from tools import (
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_observation as observation,
)
from tools import (
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_pack as pack,
)
from tools import (
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_photo_analyzer as analyzer,
)


def _synthetic_panel(*, bottom_stripe: bool = False) -> np.ndarray:
    image = np.full((600, 1024, 3), 220, dtype=np.uint8)
    palettes = (
        [(35 + code * 5, 65 + code * 7, 110 + code * 14) for code in range(8)],
        [(45 + code * 4, 85 + code * 6, 95 + code * 12) for code in range(8)],
    )
    for controller, mapping in enumerate(
        (pack.CS1_RECIPE_AT_CELL, pack.CS2_RECIPE_AT_CELL)
    ):
        for cell, recipe in enumerate(mapping):
            row, column = divmod(cell, 8)
            x0, y0, x1, y1 = analyzer._cell_bounds(  # noqa: SLF001
                controller, row, column
            )
            rgb = palettes[controller][recipe % 8]
            image[y0:y1, x0:x1] = tuple(reversed(rgb))
            if bottom_stripe and controller == 0 and row == 0 and column == 0:
                image[y1 - 8 : y1, x0:x1] = 0
    return image


def _synthetic_sparse_target_panel() -> np.ndarray:
    image = np.full((600, 1024, 3), 220, dtype=np.uint8)
    for controller, mapping in enumerate(
        (pack.CS1_RECIPE_AT_CELL, pack.CS2_RECIPE_AT_CELL)
    ):
        for cell, recipe in enumerate(mapping):
            if recipe >= 8:
                continue
            row, column = divmod(cell, 8)
            x0, y0, x1, y1 = analyzer._cell_bounds(  # noqa: SLF001
                controller, row, column
            )
            image[y0:y1, x0:x1] = (145, 65, 30)
    return image


def _cells_from_image(image: np.ndarray) -> tuple[list[dict], dict]:
    homography, geometry = analyzer._fit_geometry(image)  # noqa: SLF001
    rectified, validity = analyzer._rectify(image, homography)  # noqa: SLF001
    cells: list[dict] = []
    for controller in range(2):
        raw = [
            analyzer._sample_cell(  # noqa: SLF001
                rectified,
                validity,
                controller=controller,
                row=row,
                column=column,
            )
            for row in range(8)
            for column in range(8)
        ]
        cells.extend(analyzer._normalise_controller(raw)["cells"])  # noqa: SLF001
    return cells, geometry


def _evidence(tmp_path: Path, *, ordinal: int = 3) -> dict:
    tmp_path.mkdir(parents=True, exist_ok=True)
    action = tmp_path / "action.json"
    sidecar = tmp_path / "capture.json"
    photo = tmp_path / "photo.jpg"
    action.write_bytes(b"action")
    sidecar.write_bytes(b"sidecar")
    photo.write_bytes(b"photo")
    return {
        "action": {
            "ordinal": ordinal,
            "path": str(action),
            "bytes": 6,
            "file_sha256": hashlib.sha256(b"action").hexdigest(),
            "canonical_integrity_sha256": "a" * 64,
        },
        "capture_sidecar": {
            "path": str(sidecar),
            "bytes": 7,
            "file_sha256": hashlib.sha256(b"sidecar").hexdigest(),
            "canonical_integrity_sha256": "b" * 64,
            "capture_id": "c" * 64,
        },
        "photo": {
            "path": str(photo),
            "bytes": 5,
            "file_sha256": hashlib.sha256(b"photo").hexdigest(),
        },
    }


def _observation(
    tmp_path: Path, *, bottom_stripe: bool = False, ordinal: int = 3
) -> dict:
    cells, _geometry = _cells_from_image(_synthetic_panel(bottom_stripe=bottom_stripe))
    return analyzer._observation_document(  # noqa: SLF001
        cells=cells,
        evidence=_evidence(tmp_path, ordinal=ordinal),
        stage=f"G{ordinal}",
    )


def _write_json(path: Path, value: dict) -> bytes:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    path.write_bytes(payload)
    return payload


def _camera_lock(*, exposure: float = -4.0) -> dict:
    settings = {
        "fourcc": "MJPG",
        "frame_width": 4000,
        "frame_height": 3000,
        "fps": 10.0,
        "autofocus": 0.0,
        "focus": 20.0,
        "auto_exposure": 0.25,
        "exposure": exposure,
        "auto_white_balance": 0.0,
        "white_balance_temperature": 4600.0,
    }
    return {
        "camera_id": "48MP USB Camera",
        "camera_instance_id": "@device_pnp_vid_32e4&pid_4801",
        "camera_usb_identity": "VID_32E4:PID_4801",
        "camera_index": 0,
        "backend": "DSHOW",
        "requested_settings": settings,
        "effective_settings_before_frame": deepcopy(settings),
        "effective_settings_after_frame": deepcopy(settings),
        "setting_write_results": {key: True for key in settings},
        "manual_focus_exposure_white_balance_gate": True,
        "mount_id": "fixed-v3",
        "full_panel_visible": True,
    }


def _analysis_report(
    tmp_path: Path, *, stage: str, observation_document: dict, exposure: float = -4.0
) -> dict:
    source = {}
    for label, payload in (
        ("action", b"a"),
        ("capture_sidecar", b"c"),
        ("photo", b"p"),
    ):
        path = tmp_path / f"{stage.lower()}-{label}.bin"
        path.write_bytes(payload)
        source[label] = {
            "path": str(path),
            "bytes": len(payload),
            "file_sha256": hashlib.sha256(payload).hexdigest(),
        }
    screen = analyzer.screen_observation(observation_document)
    return analyzer._seal(  # noqa: SLF001
        {
            "schema_version": 1,
            "kind": analyzer.KIND,
            "campaign_id": pack.CAMPAIGN_ID,
            "test_id": pack.TEST_ID,
            "contract_id": pack.build_report()["contract_id"],
            "stage": stage,
            "source_evidence": source,
            "camera_lock": _camera_lock(exposure=exposure),
            "observation_document": observation_document,
            "controller_local_screen": screen,
            "hardware_accessed": False,
            "camera_accessed": False,
            "network_requests": 0,
        }
    )


def test_v3_manifest_and_dedicated_geometry_cover_128_uniform_cells() -> None:
    manifest = observation.roi_manifest()
    assert manifest["sample_count"] == 128
    assert manifest["controller_policy"] == "CS1_AND_CS2_EVALUATED_SEPARATELY"
    image = _synthetic_panel()
    cells, geometry = _cells_from_image(image)
    assert len(cells) == 128
    assert geometry["gate_pass"] is True
    assert geometry["support_by_controller"] == [64, 64]
    assert geometry["minimum_projected_cell_side_px"] >= 39.0
    for controller in range(2):
        mapping = (
            pack.CS1_RECIPE_AT_CELL if controller == 0 else pack.CS2_RECIPE_AT_CELL
        )
        assert all(mapping.count(recipe) == 4 for recipe in range(16))
    assert pack.build_report()["contract"]["spatial_dither"] is False


def test_fixed_mount_reference_can_verify_sparse_visible_target_cells() -> None:
    support = analyzer._reference_alignment_support(  # noqa: SLF001
        _synthetic_sparse_target_panel(), np.eye(3, dtype=np.float64)
    )
    assert support["gate_pass"] is True
    assert support["unique_assignment_count"] >= 48
    assert all(value >= 24 for value in support["support_by_controller"])
    assert all(
        len(value["rows"]) >= 4 and len(value["columns"]) >= 6
        for value in support["coordinate_coverage"].values()
    )


def test_generated_observation_is_consumable_and_never_qualifies(
    tmp_path: Path,
) -> None:
    document = _observation(tmp_path)
    screen = analyzer.screen_observation(document)
    assert screen["recipes_per_controller"] == 16
    assert screen["replicates_per_recipe"] == 4
    assert len(screen["recipe_results"]) == 32
    assert screen["qualified_colour_count"] == 0
    assert screen["qualified_gray_levels"] == 0
    assert screen["qualified_brightness_levels"] == 0
    assert all(
        item["edge_and_visibility_gates_pass"] for item in screen["recipe_results"]
    )

    source = tmp_path / "observation.json"
    result = tmp_path / "evaluation.json"
    _write_json(source, document)
    evaluated = observation.evaluate(source, result)
    assert evaluated["qualified_colour_count"] == 0
    assert evaluated["qualified_gray_levels"] == 0
    assert evaluated["qualified_brightness_levels"] == 0
    assert evaluated["summary"]["incomplete_controller_recipes"] == 0
    assert result.is_file()


def test_controller_local_screen_does_not_pool_large_side_offset(
    tmp_path: Path,
) -> None:
    document = _observation(tmp_path)
    for item in document["measurements"]:
        if item["controller"] == "CS2":
            item["lab"][0] = max(0.0, item["lab"][0] - 25.0)
    unsigned = deepcopy(document)
    unsigned.pop("integrity")
    document["integrity"]["sha256"] = hashlib.sha256(
        analyzer._canonical(unsigned)  # noqa: SLF001
    ).hexdigest()
    screen = analyzer.screen_observation(document)
    assert screen["controller_policy"] == "CS1_AND_CS2_NEVER_POOLED"
    assert {item["controller"] for item in screen["recipe_results"]} == {
        "CS1",
        "CS2",
    }
    assert len(screen["recipe_results"]) == 32


def test_bottom_stripe_is_not_silently_accepted(tmp_path: Path) -> None:
    document = _observation(tmp_path, bottom_stripe=True)
    affected = next(
        item
        for item in document["measurements"]
        if item["controller"] == "CS1" and item["row"] == 0 and item["column"] == 0
    )
    assert affected["bottom_edge_clean"] is False
    assert affected["horizontal_stripe_absent"] is False
    screen = analyzer.screen_observation(document)
    recipe = next(
        item
        for item in screen["recipe_results"]
        if item["controller"] == "CS1" and item["recipe"] == affected["recipe"]
    )
    assert recipe["edge_and_visibility_gates_pass"] is False
    assert recipe["qualified_level"] is False


def test_camera_lock_accepts_only_manual_48mp_and_rejects_binocular() -> None:
    lock = _camera_lock()
    camera = {
        "camera_id": lock["camera_id"],
        "instance_id": lock["camera_instance_id"],
        "index": lock["camera_index"],
        "backend": lock["backend"],
        "requested_settings": lock["requested_settings"],
        "effective_settings_before_frame": lock["effective_settings_before_frame"],
        "effective_settings_after_frame": lock["effective_settings_after_frame"],
        "set_results": lock["setting_write_results"],
    }
    sidecar = {
        "camera": camera,
        "coverage": {
            "scope": "full_panel",
            "full_panel_visible": True,
            "full_panel_uncropped": True,
            "mount_id": "fixed-v3",
        },
    }
    result = analyzer._camera_lock(sidecar)  # noqa: SLF001
    assert result["camera_usb_identity"] == "VID_32E4:PID_4801"
    assert result["manual_focus_exposure_white_balance_gate"] is True

    binocular = deepcopy(sidecar)
    binocular["camera"]["instance_id"] = "vid_1bcf&pid_0b15"
    with pytest.raises(analyzer.PhotoAnalysisError, match="48MP"):
        analyzer._camera_lock(binocular)  # noqa: SLF001

    automatic = deepcopy(sidecar)
    automatic["camera"]["requested_settings"]["auto_white_balance"] = 1.0
    with pytest.raises(analyzer.PhotoAnalysisError, match="freeze"):
        analyzer._camera_lock(automatic)  # noqa: SLF001


def test_capture_binding_is_exact_to_action_photo_and_v3_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    action_path = tmp_path / "action.json"
    photo_path = tmp_path / "photo.jpg"
    sidecar_path = tmp_path / "capture.json"
    action_payload = b"sealed-action"
    photo_payload = b"sealed-photo"
    action_path.write_bytes(action_payload)
    photo_path.write_bytes(photo_payload)
    sidecar_path.write_bytes(b"sealed-sidecar")
    expected_action = pack.build_report()["actions"][2]
    terminal = {
        "ordinal": 3,
        "canonical_integrity_sha256": "d" * 64,
        "action_id": expected_action["action_id"],
    }
    lock = _camera_lock()
    sidecar = {
        "capture_binding": "live_synchronized",
        "campaign_id": pack.CAMPAIGN_ID,
        "test_id": pack.TEST_ID,
        "contract_id": pack.build_report()["contract_id"],
        "firmware_sha256": pack.ARTIFACTS["bin_sha256"],
        "ordinal": 3,
        "action_id": expected_action["action_id"],
        "descriptor_id": expected_action["descriptor_id"],
        "role": expected_action["role"],
        "frame_sha256": expected_action["frame"]["sha256"],
        "capture_id": "e" * 64,
        "integrity": {"sha256": "f" * 64},
        "action_result": {
            "path": action_path.name,
            "bytes": len(action_payload),
            "file_sha256": hashlib.sha256(action_payload).hexdigest(),
            "canonical_integrity_sha256": terminal["canonical_integrity_sha256"],
        },
        "photo": {
            "path": photo_path.name,
            "bytes": len(photo_payload),
            "sha256": hashlib.sha256(photo_payload).hexdigest(),
        },
        "camera": {
            "camera_id": lock["camera_id"],
            "instance_id": lock["camera_instance_id"],
            "index": lock["camera_index"],
            "backend": lock["backend"],
            "requested_settings": lock["requested_settings"],
            "effective_settings_before_frame": lock["effective_settings_before_frame"],
            "effective_settings_after_frame": lock["effective_settings_after_frame"],
            "set_results": lock["setting_write_results"],
        },
        "coverage": {
            "scope": "full_panel",
            "full_panel_visible": True,
            "full_panel_uncropped": True,
            "mount_id": "fixed-v3",
        },
    }
    monkeypatch.setattr(
        analyzer.capture_evidence,
        "validate_capture_evidence",
        lambda _path: deepcopy(sidecar),
    )
    monkeypatch.setattr(
        analyzer.runner,
        "validate_terminal_evidence",
        lambda _path: deepcopy(terminal),
    )
    validated, evidence, camera_lock, resolved_action = (
        analyzer._validate_capture_binding(photo_path, sidecar_path)  # noqa: SLF001
    )
    assert validated["action_id"] == expected_action["action_id"]
    assert resolved_action == action_path.resolve()
    assert evidence["photo"]["file_sha256"] == hashlib.sha256(photo_payload).hexdigest()
    assert camera_lock["camera_usb_identity"] == "VID_32E4:PID_4801"

    photo_path.write_bytes(b"changed-after-sidecar")
    with pytest.raises(analyzer.PhotoAnalysisError, match="JPEG byte/hash"):
        analyzer._validate_capture_binding(photo_path, sidecar_path)  # noqa: SLF001


def test_repeat_comparison_requires_exact_settings_and_remains_coarse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    g3_observation = _observation(tmp_path / "g3", ordinal=3)
    g4_observation = deepcopy(g3_observation)
    g4_observation["stage"] = "G4"
    g4_observation["action_evidence"]["ordinal"] = 4
    unsigned = deepcopy(g4_observation)
    unsigned.pop("integrity")
    g4_observation["integrity"]["sha256"] = hashlib.sha256(
        analyzer._canonical(unsigned)  # noqa: SLF001
    ).hexdigest()

    g3_report = _analysis_report(
        tmp_path, stage="G3", observation_document=g3_observation
    )
    g4_report = _analysis_report(
        tmp_path, stage="G4", observation_document=g4_observation
    )
    g3_path, g4_path = tmp_path / "g3.json", tmp_path / "g4.json"
    _write_json(g3_path, g3_report)
    _write_json(g4_path, g4_report)

    def validate_sources(photo_path: Path, sidecar_path: Path):
        stage = "G3" if sidecar_path.name.startswith("g3-") else "G4"
        action_path = tmp_path / f"{stage.lower()}-action.bin"
        sources = {}
        for label, path in (
            ("action", action_path),
            ("capture_sidecar", sidecar_path),
            ("photo", photo_path),
        ):
            payload = path.read_bytes()
            sources[label] = {
                "path": str(path),
                "bytes": len(payload),
                "file_sha256": hashlib.sha256(payload).hexdigest(),
            }
        sources["action"]["ordinal"] = 3 if stage == "G3" else 4
        return {}, sources, _camera_lock(), action_path.resolve()

    monkeypatch.setattr(analyzer, "_validate_capture_binding", validate_sources)
    result = analyzer.compare_repeat(g3_path, g4_path)
    assert result["comparability"]["requested_and_effective_settings_exactly_equal"]
    assert result["qualification_boundary"]["qualified_colour_count"] == 0
    assert result["qualification_boundary"]["qualified_gray_levels"] == 0
    assert all(
        item["coarse_repeat_gate_pass"]
        for item in result["controller_results"].values()
    )

    different = _analysis_report(
        tmp_path, stage="G4", observation_document=g4_observation, exposure=-5.0
    )
    different_path = tmp_path / "g4-different.json"
    _write_json(different_path, different)
    with pytest.raises(analyzer.PhotoAnalysisError, match="lock|settings"):
        analyzer.compare_repeat(g3_path, different_path)


def test_analyzer_source_has_no_live_io_entrypoint() -> None:
    source = Path(analyzer.__file__).read_text(encoding="utf-8")
    assert "cv2.VideoCapture" not in source
    assert "requests." not in source
    assert "serial.Serial" not in source
    assert 'relay_accessed": True' not in source
    assert 'camera_accessed": True' not in source
