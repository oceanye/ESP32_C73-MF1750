from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from host.color_pipeline import RasterImage
from host.static_photo.blue_history import build_blue_history_bundle
from host.static_photo.history_palette import (
    HistoryPalette,
    HistoryRecipe,
    QualificationLevel,
    RetentionMode,
)
from host.static_photo.photo_render import build_photo_bundle
from host.static_photo.recipe_quantizer import (
    RecipeRenderMode,
    _delta_e00,
    quantize_to_history_recipes,
)
from host.static_photo.stage3_gate import (
    Stage3BlockedError,
    Stage3EvidenceStatus,
    request_lut_write,
)
from tools.mf17506_stage23.relay_contract import (
    PowerState,
    PowerStateMachine,
    RelayContractError,
)
from tools.mf17506_stage23.session_dry_run import run_dry_session


def _palette() -> HistoryPalette:
    definitions = (
        ("white", 1, 1, (95.0, 0.0, 0.0), (245, 245, 240)),
        ("yellow", 2, 2, (82.0, -3.0, 75.0), (225, 205, 15)),
        ("red", 3, 3, (48.0, 60.0, 35.0), (185, 30, 40)),
        ("blue-history", 3, 4, (42.0, 12.0, -50.0), (45, 85, 165)),
    )
    recipes = tuple(
        HistoryRecipe(
            recipe_id,
            source,
            target,
            2000,
            10,
            "factory_otp",
            23.0,
            26.0,
            RetentionMode.SAFE_POWER_OFF,
            1,
            lab,
            rgb,
            (1.0, 1.0, 1.0),
            1.0,
            1.0,
            1.0,
            True,
            f"m-{recipe_id}",
            hashlib.sha256(recipe_id.encode()).hexdigest(),
            QualificationLevel.QUALIFIED,
        )
        for recipe_id, source, target, lab, rgb in definitions
    )
    return HistoryPalette(
        "qualified-fixture",
        hashlib.sha256(b"calibration").hexdigest(),
        "factory_otp",
        recipes,
    )


def test_vector_delta_e_matches_scalar_shape_and_quantizers_are_deterministic() -> None:
    values = np.asarray(((50.0, 2.6772, -79.7751), (50.0, 0.0, 0.0)))
    distances = _delta_e00(values, np.asarray((50.0, 0.0, -82.7485)))
    assert distances.shape == (2,)
    assert distances[0] == pytest.approx(2.0425, abs=0.0001)
    image = RasterImage(8, 8, "RGB", bytes((80, 100, 170)) * 64)
    for mode in RecipeRenderMode:
        first = quantize_to_history_recipes(image, _palette(), mode=mode)
        second = quantize_to_history_recipes(image, _palette(), mode=mode)
        assert first.recipe_indices == second.recipe_indices
        assert first.dual_frame.primer == second.dual_frame.primer
        assert first.dual_frame.target == second.dual_frame.target
        assert first.report["live_authorized"] is False


def test_panel_photo_bundle_contains_four_offline_candidates(tmp_path: Path) -> None:
    image = np.zeros((600, 1024, 3), dtype=np.uint8)
    image[:, :256] = (245, 245, 245)
    image[:, 256:512] = (220, 210, 20)
    image[:, 512:768] = (185, 30, 40)
    image[:, 768:] = (45, 85, 165)
    source = tmp_path / "source.png"
    assert cv2.imwrite(str(source), image[:, :, ::-1])
    result = build_photo_bundle(
        source,
        _palette(),
        output_dir=tmp_path / "rendered",
        recipe_cell_px=8,
    )
    manifest = json.loads(
        (tmp_path / "rendered" / "PHOTO-BUNDLE-MANIFEST.json").read_text("utf-8")
    )
    assert result["candidate_count"] == 4
    assert result["live_authorized"] is False
    assert len(manifest["candidates"]) == 4
    assert manifest["selected_candidate"] is None
    assert (tmp_path / "rendered" / "comparison-contact-sheet.png").is_file()
    for mode in RecipeRenderMode:
        directory = tmp_path / "rendered" / mode.value
        assert (directory / "primer.bin").stat().st_size == 307200
        assert (directory / "target.bin").stat().st_size == 307200


def test_relay_dry_run_uses_one_session_cycle_and_fault_latches(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    build_blue_history_bundle(bundle)
    success = run_dry_session(
        bundle / "BLUE-HISTORY-MANIFEST.json",
        output_dir=tmp_path / "success",
    )
    success_report = json.loads(
        (tmp_path / "success" / "DRY-RUN-REPORT.json").read_text("utf-8")
    )
    assert success["terminal"] == "DRY_RUN_SUCCESS_SAFE_OFF"
    assert success["completed_action_count"] == 6
    assert success_report["relay_fake_calls"].count("command_on") == 1
    assert success_report["relay_fake_calls"].count("command_off") == 2
    assert success_report["visible_refreshes_performed"] == 0

    failed = run_dry_session(
        bundle / "BLUE-HISTORY-MANIFEST.json",
        output_dir=tmp_path / "failed",
        fail_operation="command_on",
    )
    assert failed["terminal"] == "DRY_RUN_FAULT_LATCHED"
    assert failed["final_state"] == "FAULT_LATCHED"
    assert failed["completed_action_count"] == 0

    machine = PowerStateMachine()
    with pytest.raises(RelayContractError, match="requires RUN_READY"):
        machine.start_action("not-ready")
    assert machine.state is PowerState.SAFE_OFF


def test_stage_three_lut_write_remains_hard_blocked_even_with_boolean_flags() -> None:
    synthetic_all_true = Stage3EvidenceStatus(True, True, True, True, True)
    assert synthetic_all_true.evidence_gates_complete is True
    with pytest.raises(Stage3BlockedError, match="not implemented or authorized"):
        request_lut_write(synthetic_all_true)
