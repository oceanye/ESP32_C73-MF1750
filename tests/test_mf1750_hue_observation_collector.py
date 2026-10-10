from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from host.extended_color.mf1750_hue_observations import (
    HueObservationError,
    build_observation_template,
    summarize_observation_document,
    validate_observation_document,
)
from tools import mf1750_hue_observation_collector as collector
from tools import mf1750_runtime_lut_hue_brightness_blue_v1_pack as blue
from tools.mf1750_target_hue_catalog import describe as describe_catalog


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/mf1750_hue_observation_collector.py"


def _template() -> dict[str, object]:
    return build_observation_template(describe_catalog(), blue.build_report())


def _complete_first_candidate(document: dict[str, object]) -> dict[str, object]:
    candidate = document["candidates"][0]
    candidate["classification"] = {
        "observed_hue_id": "B",
        "lightness_rank": 1,
        "priority_mark": "priority",
        "notes": ["controlled-light review candidate"],
    }
    candidate["qualification_requested"] = True
    for field in ("lightness_relationship", "local_hold", "factory_white_recovery"):
        candidate[field] = {
            "status": "pass",
            "evidence_id": f"{field.upper()}-EVIDENCE-1",
            "notes": [],
        }
    for observation in candidate["observations"]:
        repetition = observation["repetition"]
        observation["run_id"] = f"BLUE-RUN-{repetition}"
        observation["controller_agreement"] = {
            "status": "pass",
            "evidence_note": "fixed-light left/right agreement",
        }
        for controller in ("CS1", "CS2"):
            record = observation["controllers"][controller]
            record["target_repeat"] = {
                "before": {
                    "uniformity": "uniform",
                    "color_word": "blue",
                    "lab_d65_2deg": [45.0, 2.0, -38.0],
                },
                "after": {
                    "uniformity": "uniform",
                    "color_word": "blue",
                    "lab_d65_2deg": [45.2, 2.1, -38.1],
                },
                "stability": "stable",
            }
            record["persistence"] = {
                point: {
                    "uniformity": "uniform",
                    "color_word": "blue",
                    "lab_d65_2deg": [45.1, 2.0, -38.0],
                    "retention": "stable",
                }
                for point in ("5s", "60s", "600s")
            }
    return document


def test_generate_binds_catalog_and_all_64_blue_recipes_without_colour_claim() -> None:
    first = _template()
    second = _template()
    assert first == second
    assert len(first["template_id"]) == 64
    assert first["source"]["target_hue_id"] == "B"
    assert first["source"]["recipe_count"] == 64
    assert len(first["candidates"]) == 64
    assert first["evidence_boundary"]["qualified_recipe_count_at_generation"] == 0
    assert (
        first["evidence_boundary"]["qualified_unique_colour_count_at_generation"]
        is None
    )
    assert first["evidence_boundary"]["history_recipes_are_not_unique_colours"]
    assert all(candidate["candidate_only"] for candidate in first["candidates"])
    assert not any("qualified" in candidate for candidate in first["candidates"])


def test_blank_template_validates_with_zero_qualified_recipes() -> None:
    template = _template()
    report = validate_observation_document(template, _template())
    assert report["valid"] is True
    assert report["candidate_recipe_count"] == 64
    assert report["qualification_requested_count"] == 0
    assert report["qualified_recipe_count"] == 0
    assert report["qualified_unique_colour_count"] is None
    assert all(
        result["blockers"] == ["qualification_not_requested"]
        for result in report["qualification_results"]
    )


def test_operator_cannot_insert_a_qualified_claim() -> None:
    document = _template()
    document["candidates"][0]["qualified"] = True
    with pytest.raises(HueObservationError, match="keys differ"):
        validate_observation_document(document, _template())


def test_missing_lab_never_qualifies_a_requested_candidate() -> None:
    document = _complete_first_candidate(deepcopy(_template()))
    candidate = document["candidates"][0]
    candidate["observations"][0]["controllers"]["CS1"]["target_repeat"]["after"][
        "lab_d65_2deg"
    ] = None
    report = validate_observation_document(document, _template())
    first = report["qualification_results"][0]
    assert first["qualified"] is False
    assert "r1_CS1_after_sample_incomplete" in first["blockers"]


def test_fewer_than_three_independent_repetitions_never_qualifies() -> None:
    document = _complete_first_candidate(deepcopy(_template()))
    document["candidates"][0]["observations"] = document["candidates"][0][
        "observations"
    ][:2]
    report = validate_observation_document(document, _template())
    first = report["qualification_results"][0]
    assert first["qualified"] is False
    assert "fewer_than_three_independent_repetitions" in first["blockers"]


def test_missing_local_hold_evidence_never_qualifies() -> None:
    document = _complete_first_candidate(deepcopy(_template()))
    document["candidates"][0]["local_hold"] = {
        "status": "pending",
        "evidence_id": None,
        "notes": [],
    }
    report = validate_observation_document(document, _template())
    first = report["qualification_results"][0]
    assert first["qualified"] is False
    assert "local_hold_not_pass" in first["blockers"]


def test_all_explicit_gates_can_qualify_a_recipe_but_not_claim_uniqueness() -> None:
    document = _complete_first_candidate(deepcopy(_template()))
    validation = validate_observation_document(document, _template())
    assert validation["qualified_recipe_count"] == 1
    assert validation["qualified_unique_colour_count"] is None
    assert validation["qualification_results"][0]["qualified"] is True
    summary = summarize_observation_document(document, _template())
    assert summary["qualified_recipe_count"] == 1
    assert summary["qualified_unique_colour_count"] is None
    assert summary["priority_recipe_ids"] == ["BLUE-A0-B0-A5"]
    assert summary["hue_assignment_counts"]["B"] == 1
    assert summary["hue_assignment_counts"]["unassigned"] == 63


def test_cli_generate_validate_and_summary_are_deterministic_json(
    tmp_path: Path,
) -> None:
    template_path = tmp_path / "observations.json"
    generated = subprocess.run(
        [sys.executable, str(SCRIPT), "generate"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    assert (
        generated
        == subprocess.run(
            [sys.executable, str(SCRIPT), "generate"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout
    )
    json.loads(generated)
    template_path.write_text(generated, encoding="utf-8")

    validated = subprocess.run(
        [sys.executable, str(SCRIPT), "validate", str(template_path)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    summarized = subprocess.run(
        [sys.executable, str(SCRIPT), "summary", str(template_path)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    assert json.loads(validated)["qualified_recipe_count"] == 0
    assert json.loads(summarized)["qualified_recipe_count"] == 0
    assert json.loads(summarized)["qualified_unique_colour_count"] is None
    assert collector.generate() == json.loads(generated)
