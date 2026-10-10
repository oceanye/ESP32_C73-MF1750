"""PAL1 photo-analyzer wrapper tests: recipe/blank/stage identity, no device."""
from __future__ import annotations

import pytest

from tools import mf1750_pal1_photo_analyzer as pal1
from tools import mf1750_lh3_dose_photo_analyzer as dose

ACTION = {"stage": "PAL1", "ordinal": 1, "action_id": "a" * 64,
          "descriptor_id": "b" * 64, "profile_id": "P",
          "frame": {"sha256": "f" * 64}}
CONTRACT = {"contract_id": "e" * 64, "actions": [ACTION]}
BLANK = {"identity": {"action_sha256": "a" * 64, "frame_sha256": "f" * 64,
                      "profile_id": "P", "test_phase": "SCREEN"}}


def _live():
    return {"kind": "mf1750-pal1-result-v1", "protocol_verdict": "PASS",
            "ordinal": 1, "contract_id": CONTRACT["contract_id"],
            "boot_nonce": "5b4d25e139b138d9", "run_id": "RUN",
            "campaign_complete": True,
            "report": {"action_id": ACTION["action_id"],
                       "descriptor_id": ACTION["descriptor_id"],
                       "contract_id": CONTRACT["contract_id"],
                       "terminal_state": "COMPLETE", "result": True}}


def test_central_fraction_knob():
    from tools import mf1750_lh3_dose_photo_analyzer as dose_mod
    from tools import mf1750_lh1_rebound_v2_middle_photo_analyzer as middle
    dose_mod.apply_central_fraction(None)
    assert middle.CENTRAL_FRACTION == 0.6
    dose_mod.apply_central_fraction(0.3)
    assert middle.CENTRAL_FRACTION == 0.3
    dose_mod.apply_central_fraction(0.6)  # restore
    with pytest.raises(SystemExit):
        dose_mod.apply_central_fraction(0.1)
    with pytest.raises(SystemExit):
        dose_mod.apply_central_fraction(1.5)


def test_recipe_cell_pal1_pattern():
    assert pal1.recipe_cell("PAL1-C0-R0") == (0, 0)
    assert pal1.recipe_cell("PAL1-C7-R7") == (7, 7)
    with pytest.raises(SystemExit):
        pal1.recipe_cell("LH3D-S7-D0-R0")  # dose pattern rejected
    with pytest.raises(SystemExit):
        pal1.recipe_cell("PAL1-C8-R0")


def test_validate_blank_pal1_grid():
    entries = []
    for ctrl in ("CS1", "CS2"):
        for code in range(8):
            for row in range(8):
                entries.append({"controller": ctrl,
                                "recipe_id": f"PAL1-C{code}-R{row}",
                                "comparison_id": f"PAL1_C{code}",
                                "position": "TL",
                                "roi": {"x": 68 + code * 48, "y": 64 + row * 60,
                                        "width": 40, "height": 52}})
    assert pal1.validate_blank(entries) is entries
    bad = list(entries)
    bad[0] = {**bad[0], "comparison_id": "DOSE_C0"}
    with pytest.raises(SystemExit, match="comparison_id"):
        pal1.validate_blank(bad)


def test_stage_identity_pal1_binding():
    identity, action = pal1.stage_identity(BLANK, CONTRACT, "PAL1", _live())
    assert action is ACTION
    assert identity["action_sha256"] == ACTION["action_id"]
    assert identity["contract_id"] == CONTRACT["contract_id"]
    assert identity["boot_nonce"] == "5b4d25e139b138d9"
    assert identity["campaign_complete"] is True
    bad = _live()
    bad["kind"] = "mf1750-lh3-dose-result-v1"
    with pytest.raises(SystemExit):
        pal1.stage_identity(BLANK, CONTRACT, "PAL1", bad)
    bad = _live()
    bad["ordinal"] = 2
    with pytest.raises(SystemExit):
        pal1.stage_identity(BLANK, CONTRACT, "PAL1", bad)


def test_wrapper_knobs_do_not_leak_back():
    # configure() mutates the dose module; the dose tool's own tests must not
    # observe the PAL1 knobs (they configure nothing). This test pins the
    # current module constants after configure() so any leak is explicit.
    pal1.configure()
    assert dose.STAGE_ORDINAL == {"PAL1": 1}
    dose.STAGE_ORDINAL = {"DOSE1": 2, "DOSE2": 3}  # restore for other tests
    dose.RECIPE = __import__("re").compile(r"LH3D-S7-D([0-7])-R([0-7])")
    dose.RESULT_KIND = "mf1750-lh3-dose-result-v1"
    dose.EXTRACTION_KIND = "mf1750-lh3-dose-extraction-v1"
    dose.STAGE_CONTRACT_KEY = "dose_stage_contract"
    dose.COMPARISON_PREFIX = "DOSE_C"
    dose.ANALYZER_VERSION = "mf1750-lh3-dose-photo-analyzer-v1"
