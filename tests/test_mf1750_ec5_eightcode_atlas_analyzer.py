from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools import mf1750_ec5_eightcode_atlas as atlas
from tools import mf1750_ec5_eightcode_atlas_analyzer as analyzer


ACTION = "a" * 64
RESULT = "b" * 64


def _observation(code_groups: dict[int, str]) -> dict:
    slots = []
    for side in ("L", "R"):
        for slot in range(8):
            code = slot if side == "L" else 7 - slot
            slots.append(
                {
                    "slot_id": f"{side}{slot}",
                    "appearance_group": code_groups[code],
                    "uncertain": False,
                }
            )
    return {
        "schema_version": 1,
        "kind": analyzer.OBSERVATION_KIND,
        "layout_id": atlas.LAYOUT_ID,
        "atlas_action_id": ACTION,
        "atlas_result_sha256": RESULT,
        "operator_blinded_to_code_positions": True,
        "pseudocolor_preview_withheld": True,
        "slots": slots,
        "supervised_safety": {
            "electrical_normal": True,
            "temperature_c": 35.0,
            "esp32_did_not_restart": True,
        },
    }


def test_eight_consistent_groups_yield_eight_direct_state_candidates() -> None:
    observation = _observation({code: f"G{code}" for code in range(8)})
    result = analyzer.analyze_observation(observation)
    assert result["conclusive_cross_controller_grouping"] is True
    assert result["visually_distinct_direct_state_count"] == 8
    assert result["u04_distinct_from_u05"] is True
    assert result["u07_distinct_from_all_formal_codes"] is True
    assert result["classification"] == "BLIND_DIRECT_STATE_GROUPING_COMPLETE"
    assert result["formal_color_qualification"] is False


def test_u07_alias_to_blue_yields_seven_groups_and_exact_alias_cluster() -> None:
    groups = {code: f"G{code}" for code in range(8)}
    groups[7] = groups[5]
    result = analyzer.analyze_observation(_observation(groups))
    assert result["visually_distinct_direct_state_count"] == 7
    assert result["u04_distinct_from_u05"] is True
    assert result["u07_distinct_from_all_formal_codes"] is False
    aliases = [item for item in result["alias_clusters"] if item["is_alias_cluster"]]
    assert aliases == [{"appearance_group": "G5", "codes": [5, 7], "is_alias_cluster": True}]


def test_controller_mismatch_is_inconclusive_and_does_not_invent_count() -> None:
    observation = _observation({code: f"G{code}" for code in range(8)})
    right_for_code4 = next(item for item in observation["slots"] if item["slot_id"] == "R3")
    right_for_code4["appearance_group"] = "DIFFERENT"
    result = analyzer.analyze_observation(observation)
    assert result["conclusive_cross_controller_grouping"] is False
    assert result["mismatched_codes"] == [4]
    assert result["visually_distinct_direct_state_count"] is None
    assert result["u04_distinct_from_u05"] is None


def test_uncertain_slot_is_inconclusive() -> None:
    observation = _observation({code: f"G{code}" for code in range(8)})
    slot = next(item for item in observation["slots"] if item["slot_id"] == "L7")
    slot["uncertain"] = True
    slot["appearance_group"] = None
    result = analyzer.analyze_observation(observation)
    assert result["uncertain_codes"] == [7]
    assert result["visually_distinct_direct_state_count"] is None


def test_duplicate_or_missing_slot_fails_closed() -> None:
    observation = _observation({code: f"G{code}" for code in range(8)})
    observation["slots"][-1]["slot_id"] = "L0"
    with pytest.raises(analyzer.EightCodeAtlasAnalysisError, match="unique"):
        analyzer.analyze_observation(observation)


def test_unblinded_or_bad_safety_shape_fails_closed() -> None:
    observation = _observation({code: f"G{code}" for code in range(8)})
    observation["operator_blinded_to_code_positions"] = False
    with pytest.raises(analyzer.EightCodeAtlasAnalysisError, match="not blinded"):
        analyzer.analyze_observation(observation)
    observation = _observation({code: f"G{code}" for code in range(8)})
    observation["supervised_safety"]["temperature_c"] = float("nan")
    with pytest.raises(analyzer.EightCodeAtlasAnalysisError, match="finite"):
        analyzer.analyze_observation(observation)


def test_cli_round_trip_and_duplicate_json_rejection(tmp_path: Path) -> None:
    tool = Path("tools/mf1750_ec5_eightcode_atlas_analyzer.py")
    path = tmp_path / "observation.json"
    path.write_text(
        json.dumps(_observation({code: f"G{code}" for code in range(8)})),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, str(tool), "--observation", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout)["visually_distinct_direct_state_count"] == 8

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    rejected = subprocess.run(
        [sys.executable, str(tool), "--observation", str(duplicate)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert rejected.returncode == 2
    assert "duplicate JSON key" in rejected.stderr


def test_input_is_not_mutated() -> None:
    observation = _observation({code: f"G{code}" for code in range(8)})
    original = copy.deepcopy(observation)
    analyzer.analyze_observation(observation)
    assert observation == original
