"""Tests for the LH3 dose photo analyzer: recipe/grid pinning, stage identity
binding, blank validation, mapping inheritance reuse, and the dark-session
detector regression on a column-coded synthetic frame."""
from __future__ import annotations

import json

import numpy as np
import pytest

from tools import mf1750_lh3_dose_photo_analyzer as analyzer

ACTION1 = {"stage": "DOSE1", "ordinal": 2, "action_id": "a" * 64,
           "descriptor_id": "b" * 64, "profile_id": "P",
           "frame": {"sha256": "f" * 64}}
ACTION2 = {"stage": "DOSE2", "ordinal": 3, "action_id": "c" * 64,
           "descriptor_id": "d" * 64, "profile_id": "P",
           "frame": {"sha256": "f" * 64}}
CONTRACT = {"contract_id": "e" * 64,
            "actions": [{"stage": "SOURCE"}, ACTION1, ACTION2]}
BLANK = {"identity": {"action_sha256": "c" * 64, "frame_sha256": "f" * 64,
                      "profile_id": "P", "test_phase": "SCREEN"}}


def _live(ordinal=2, action=ACTION1, boot="4d53de6fe4b39d3b"):
    return {"kind": "mf1750-lh3-dose-result-v1", "protocol_verdict": "PASS",
            "ordinal": ordinal, "contract_id": CONTRACT["contract_id"],
            "boot_nonce": boot, "run_id": "RUN", "campaign_complete": ordinal == 3,
            "report": {"action_id": action["action_id"],
                       "descriptor_id": action["descriptor_id"],
                       "contract_id": CONTRACT["contract_id"],
                       "terminal_state": "COMPLETE", "result": True}}


def test_recipe_cell():
    assert analyzer.recipe_cell("LH3D-S7-D0-R0") == (0, 0)
    assert analyzer.recipe_cell("LH3D-S7-D7-R7") == (7, 7)
    with pytest.raises(SystemExit):
        analyzer.recipe_cell("LH3D-S7-D8-R0")
    with pytest.raises(SystemExit):
        analyzer.recipe_cell("LH2-S7-M0-H0")


def _blank_entry(controller, code, row):
    return {"controller": controller, "recipe_id": f"LH3D-S7-D{code}-R{row}",
            "comparison_id": f"DOSE_C{code}",
            "position": ("T" if row < 4 else "B") + ("L" if code < 4 else "R"),
            "roi": {"x": 68 + code * 48, "y": 64 + row * 60, "width": 40, "height": 52}}


def _entries():
    return [_blank_entry(ctrl, code, row)
            for ctrl in ("CS1", "CS2") for code in range(8) for row in range(8)]


def test_validate_blank_grid_pinning():
    entries = _entries()
    assert analyzer.validate_blank(entries) is entries
    bad = _entries()
    bad[0]["recipe_id"] = "LH3D-S7-D1-R0"  # grid col 0, recipe says code 1
    with pytest.raises(SystemExit, match="mismatch"):
        analyzer.validate_blank(bad)
    bad = _entries()
    bad[0]["roi"]["x"] += 1  # off grid
    with pytest.raises(SystemExit, match="off grid"):
        analyzer.validate_blank(bad)
    bad = _entries()
    bad[0]["comparison_id"] = "DOSE_C7"
    with pytest.raises(SystemExit, match="comparison_id"):
        analyzer.validate_blank(bad)
    with pytest.raises(SystemExit, match="128"):
        analyzer.validate_blank(_entries()[:-1])


def test_stage_identity_binds_contract_action():
    identity, action = analyzer.stage_identity(BLANK, CONTRACT, "DOSE1", _live())
    assert action is ACTION1
    assert identity["action_sha256"] == ACTION1["action_id"]
    assert identity["frame_sha256"] == ACTION1["frame"]["sha256"]
    assert identity["contract_id"] == CONTRACT["contract_id"]
    assert identity["boot_nonce"] == "4d53de6fe4b39d3b"
    identity2, action2 = analyzer.stage_identity(BLANK, CONTRACT, "DOSE2", _live(3, ACTION2))
    assert action2 is ACTION2
    assert identity2["action_sha256"] == ACTION2["action_id"]
    # Same frame sha for both stages; the action id is the discriminator.
    assert identity["frame_sha256"] == identity2["frame_sha256"]
    assert identity["action_sha256"] != identity2["action_sha256"]


def test_stage_identity_rejects_mismatched_evidence():
    with pytest.raises(SystemExit, match="bind"):
        analyzer.stage_identity(BLANK, CONTRACT, "DOSE1", _live(3, ACTION2))
    with pytest.raises(SystemExit, match="PASS"):
        analyzer.stage_identity(BLANK, CONTRACT, "DOSE1",
                                {**_live(), "protocol_verdict": "FAIL_STOP"})
    bad = _live()
    bad["boot_nonce"] = "not-a-nonce"
    with pytest.raises(SystemExit, match="boot"):
        analyzer.stage_identity(BLANK, CONTRACT, "DOSE1", bad)
    bad = _live()
    bad["contract_id"] = "0" * 64
    with pytest.raises(SystemExit, match="contract"):
        analyzer.stage_identity(BLANK, CONTRACT, "DOSE1", bad)


def test_middle_mapping_inheritance_reused(tmp_path):
    good = {"mapping_evidence": {"mapping": {
        "side_to_ctrl": {"CS1": "left", "CS2": "right"},
        "transform_per_side": {"left": "identity", "right": "identity"}}}}
    path = tmp_path / "middle.json"
    path.write_text(json.dumps(good), encoding="utf-8")
    assert analyzer.load_middle_mapping(path) == good["mapping_evidence"]["mapping"]
    path.write_text(json.dumps({"mapping_evidence": {"mapping": {
        "side_to_ctrl": {"CS1": "right", "CS2": "left"},
        "transform_per_side": {"left": "identity", "right": "identity"}}}}),
        encoding="utf-8")
    with pytest.raises(SystemExit):
        analyzer.load_middle_mapping(path)


def _synthetic_dose_frame() -> np.ndarray:
    """Two 8x8 column-coded grids on a bright background, axis aligned."""
    img = np.full((3000, 4000, 3), (178, 155, 147), np.uint8)
    palette = [
        (76, 51, 113), (122, 106, 138), (99, 79, 128), (89, 38, 35),
        (120, 103, 137), (95, 47, 43), (98, 80, 51), (255, 255, 255),
    ]
    for x0 in (1700, 2680):
        for r in range(8):
            for c in range(7):  # code 7 column stays white (undetected)
                x = x0 + c * 100
                y = 680 + r * 108
                img[y:y + 82, x:x + 78] = palette[c]
    return img


def test_dark_session_detector_on_dose_frame():
    from tools import mf1750_lh1_rebound_v2_middle_photo_analyzer as base
    img = (_synthetic_dose_frame().astype(np.float32) * 0.55).clip(0, 255).astype(np.uint8)
    centers = analyzer.detect_centers(img)
    comps = base.grid_components(centers)
    assert len(comps) == 2
    for comp in comps:
        assert len(comp) == 56  # 64 cells minus the invisible white code-7 column
        # The base complete-row seeding cannot run on a column-coded frame...
        with pytest.raises(SystemExit):
            base.assign_lattice(comp)
        # ...but the dose left-anchored seeding recovers all 56 real cells.
        lattice, _theta = analyzer.assign_dose_lattice(comp)
        assert len(lattice) == 56
        assert {r for r, _ in lattice} == set(range(8))
        assert {c for _, c in lattice} == set(range(7))  # col 7 stays absent


def test_dose_lattice_tolerates_internal_gap():
    # Unit-level: a regular 7-pitch lattice missing interior column 3 and the
    # trailing column 7 must seed with indices {0,1,2,4,5,6}.
    pts = np.array([[100.0 + 70 * c + 2 * r, 500.0 + 80 * r]
                    for r in range(8) for c in (0, 1, 2, 4, 5, 6)])
    lattice, _theta = analyzer.assign_dose_lattice(pts)
    assert len(lattice) == 48
    assert {c for _, c in lattice} == {0, 1, 2, 4, 5, 6}
    assert {r for r, _ in lattice} == set(range(8))


def test_dose_lattice_candidate_set_with_irregular_gaps():
    # PAL2 OTP pattern: five visible columns {0,1,3,4,6} where the naive
    # pitch/gap walk mis-assigns (median gap 1.33x pitch); the candidate-set
    # residual search must recover the exact indices.
    import numpy as np
    analyzer.MIN_ROW_CELLS = 5
    try:
        pts = np.array([[100.0 + 80 * c + 1.5 * r, 500.0 + 90 * r]
                        for r in range(8) for c in (0, 1, 3, 4, 6)])
        lattice, _theta = analyzer.assign_dose_lattice(pts)
    finally:
        analyzer.MIN_ROW_CELLS = 6
    assert len(lattice) == 40
    assert {c for _, c in lattice} == {0, 1, 3, 4, 6}
    assert {r for r, _ in lattice} == set(range(8))


def test_grid_components_drops_spurious_clusters():
    import numpy as np
    analyzer.MIN_COMPONENT_CELLS = 40
    try:
        grid = np.array([[100.0 + 60 * c, 500.0 + 70 * r]
                         for r in range(8) for c in range(5)])
        grid2 = grid + np.array([700.0, 30.0])
        spurious = np.array([[30.0, 20.0], [35.0, 25.0]])
        comps = analyzer.grid_components(np.vstack([grid, grid2, spurious]))
    finally:
        analyzer.MIN_COMPONENT_CELLS = 50
    assert len(comps) == 2
    assert sorted(len(c) for c in comps) == [40, 40]
