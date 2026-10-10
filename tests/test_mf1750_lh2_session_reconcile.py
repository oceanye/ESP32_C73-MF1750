"""Tests for the LH2 MAP session reconciliation: Y<->L* helpers and key
assertions on the sealed reconcile-analysis.json (illumination facts,
attribution verdicts, corrected level counts, seal integrity)."""
from __future__ import annotations

import json
from pathlib import Path

from tools import mf1750_lh2_session_reconcile as rc
from tools.mf1750_lh1_lh4_once import canonical, digest

OUT = Path(".test-output/offline/LH2_MAP_SESSION_RECONCILE_20260919_V1/reconcile-analysis.json")


def test_y_lstar_roundtrip():
    for lstar in (0.5, 3.0, 18.0, 36.5, 44.2, 65.8):
        assert abs(rc.lstar_of_y(rc.y_of_lstar(lstar)) - lstar) < 1e-9
    assert rc.y_of_lstar(44.2) > rc.y_of_lstar(36.4)


def test_sealed_reconcile_output():
    doc = json.loads(OUT.read_text(encoding="utf-8"))
    body = {k: v for k, v in doc.items() if k != "integrity"}
    assert digest(canonical(body)) == doc["integrity"]["sha256"], "seal mismatch"

    il = doc["illumination"]
    # sessions are NOT the same illumination level at the panel
    assert il["camera_settings_identical"] is True
    for ctrl in ("CS1", "CS2"):
        anchor = il["white_anchor_cell_M7C4"][ctrl]
        assert anchor["morning_lstar"] - anchor["night_lstar"] > 5.0
        assert 1.3 < anchor["y_gain"] < 1.8
    assert il["per_cell_lstar_delta_morning_minus_night"]["min"] > 0.0
    assert il["chroma_le8_cells"]["night"] > 40
    assert il["chroma_le8_cells"]["morning"] == 0
    assert il["white_anchor_vs_20260917_bright"]["CS1"] < 0.85

    at = doc["attribution"]
    assert "artefact" in at["NEUTRAL_drop_4_to_1"]["verdict"]
    assert "boundary" in at["RO_gain_1_to_2_CS1"]["verdict"]
    # every night 'neutral' MAP level resolves chromatic (C*>8) in the morning
    for item in at["NEUTRAL_drop_4_to_1"]["evidence"][
            "night_neutral_map_levels_remeasured_in_morning"]:
        assert item["night_L_hue_chroma"][2] <= 8.0
        assert item["morning_L_hue_chroma"][2] > 8.0
    # mixed reference did not change headline counts
    assert at["mixed_reference_assessment"]["headline_counts_unchanged"] is True

    cc = doc["conclusions"]
    assert cc["illumination_same_level"] is False
    assert cc["night_neutral_4_levels_valid"] is False
    assert cc["credible_family_levels_morning"]["CS1"]["RO"] == 2
    assert cc["credible_family_levels_morning"]["CS2"]["RO"] == 1
    assert cc["credible_family_levels_morning"]["CS1"]["NEUTRAL"] == 1
    assert cc["qualified_count"] == 0
