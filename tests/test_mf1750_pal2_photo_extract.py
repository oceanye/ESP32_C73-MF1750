"""PAL2 photo extractor tests: kit/evidence binding, no device."""
from __future__ import annotations

import pytest

from tools import mf1750_pal2_photo_extract as pal2
from tools import mf1750_lh3_dose_photo_analyzer as dose

ACTION = {"stage": "PAL2", "ordinal": 1, "action_id": "a" * 64,
          "descriptor_id": "b" * 64, "profile_id": "OTP_PRODUCTION_STOCK",
          "frame": {"sha256": "f" * 64}}
CONTRACT = {"kind": "mf1750-pal2-analysis-kit-v1", "contract_id": "e" * 64,
            "action_count": 1, "actions": [ACTION]}
BLANK = {"identity": {"action_sha256": "a" * 64, "frame_sha256": "f" * 64,
                      "profile_id": "OTP_PRODUCTION_STOCK", "test_phase": "SCREEN"}}


def _evidence():
    return {"kind": "mf1750-pal2-frame-evidence-v1", "frame_sha256": "f" * 64,
            "refresh_report": {"path": "r.json", "bytes": 1, "sha256": "1" * 64},
            "camera_review": {"path": "c.json", "bytes": 1, "sha256": "2" * 64},
            "integrity": {"sha256": "3" * 64}}


def test_recipe_cell_pal2_pattern():
    pal2.configure()
    assert pal2.dose.RECIPE.fullmatch("PAL2-C5-R7")
    with pytest.raises(SystemExit):
        dose.recipe_cell("PAL1-C0-R0")  # PAL1 pattern rejected after configure
    with pytest.raises(SystemExit):
        dose.recipe_cell("LH3D-S7-D0-R0")


def test_stage_identity_binds_kit_and_evidence():
    identity, action = pal2.pal2_stage_identity(BLANK, CONTRACT, "PAL2", _evidence())
    assert action is ACTION
    assert identity["action_sha256"] == ACTION["action_id"]
    assert identity["frame_sha256"] == ACTION["frame"]["sha256"]
    assert identity["contract_id"] == CONTRACT["contract_id"]
    assert identity["boot_nonce"] is None
    assert identity["production_no_campaign_boot"] is True
    assert identity["frame_evidence_sha256"] == "3" * 64


def test_stage_identity_rejects_mismatch():
    bad = _evidence()
    bad["frame_sha256"] = "0" * 64
    with pytest.raises(SystemExit, match="frame evidence"):
        pal2.pal2_stage_identity(BLANK, CONTRACT, "PAL2", bad)
    bad = _evidence()
    del bad["camera_review"]
    with pytest.raises(SystemExit, match="camera_review"):
        pal2.pal2_stage_identity(BLANK, CONTRACT, "PAL2", bad)
    with pytest.raises(SystemExit, match="kind"):
        pal2.pal2_stage_identity(BLANK, CONTRACT, "PAL2",
                                 {**_evidence(), "kind": "other"})
    bad_contract = {**CONTRACT, "kind": "mf1750-lightness-history-firmware-contract-v1"}
    with pytest.raises(SystemExit, match="kit"):
        pal2.pal2_stage_identity(BLANK, bad_contract, "PAL2", _evidence())


def test_wrapper_knobs_restored():
    # The wrapper mutates the shared dose module; restore the dose defaults so
    # test order can never leak PAL2 knobs into the dose analyzer tests.
    import re
    dose.RECIPE = re.compile(r"LH3D-S7-D([0-7])-R([0-7])")
    dose.STAGE_ORDINAL = {"DOSE1": 2, "DOSE2": 3}
    dose.RESULT_KIND = "mf1750-lh3-dose-result-v1"
    dose.EXTRACTION_KIND = "mf1750-lh3-dose-extraction-v1"
    dose.STAGE_CONTRACT_KEY = "dose_stage_contract"
    dose.ANALYZER_VERSION = "mf1750-lh3-dose-photo-analyzer-v1"
    dose.COMPARISON_PREFIX = "DOSE_C"
    dose.stage_identity = dose.__dict__.get("stage_identity")
    assert dose.RECIPE.fullmatch("LH3D-S7-D0-R0")
