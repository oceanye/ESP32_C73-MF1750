from copy import deepcopy
import json
import math

import pytest

from host.static_photo import lightness_test as suite
from host.static_photo.common import verify_integrity
from tools import mf1750_lightness_test as cli
from tools import (
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_pack as geometry,
)


def dataset(count=3, controllers=("CS1", "CS2")):
    data = suite.blank_observations(geometry.recipe_map())
    data.update(
        data_origin="TEST_FIXTURE",
        protocol_result="PASS",
        image_result="PASS",
        observations=[],
    )
    data["identity"] = {key: "synthetic-test-only" for key in data["identity"]}
    for key in ("firmware_sha256", "action_sha256", "frame_sha256"):
        data["identity"][key] = "a" * 64
    data["identity"]["temperature_c"] = 25.0
    for controller in controllers:
        for rank in range(count):
            for position, offset in zip(
                suite.POSITIONS, (-0.3, -0.1, 0.1, 0.3), strict=True
            ):
                data["observations"].append(
                    {
                        "controller": controller,
                        "comparison_id": "ONE_TRACK",
                        "recipe_id": f"R{rank}",
                        "position": position,
                        "roi": {
                            "x": (10 if position[1] == "L" else 270) + (rank % 4) * 50,
                            "y": (10 if position[0] == "T" else 310) + (rank // 4) * 60,
                            "width": 40,
                            "height": 50,
                        },
                        "lab": [15 + 8 * rank + offset, 25.0, 20.0],
                        "noise": {
                            "sample_count": 10,
                            "lstar_mad": 0.01,
                            "lstar_ci95_half_width": 0.1,
                            "delta_e00_mad": 0.01,
                            "delta_e00_ci95_half_width": 0.1,
                        },
                        "quality_pass": True,
                        "single_pixel_uniform": True,
                        "measurement_evidence_sha256": "a" * 64,
                    }
                )
    return data


def test_three_levels_are_candidates_not_qualified():
    result = suite.analyze_observations(dataset())
    verify_integrity(result, "report")
    assert [g["candidate_level_count"] for g in result["groups"]] == [3, 3]
    assert all(g["requested_level_screen_pass"] for g in result["groups"])
    assert result["verdict"] == "HOLD_FOR_EVIDENCE"
    assert result["qualified_count"] == 0
    assert not result["live_authorization"]
    assert set(result["later_gates"].values()) == {"NOT_EVALUATED"}


@pytest.mark.parametrize("count", [5, 10])
def test_more_levels_do_not_skip_lifecycle_or_grant_qualification(count):
    data = dataset(count)
    data["requested_levels"] = count
    report = suite.analyze_observations(data)
    assert all(g["candidate_level_count"] == count for g in report["groups"])
    assert report["qualified_count"] == 0
    assert report["verdict"] == "HOLD_FOR_EVIDENCE"


def test_two_levels_and_many_photos_do_not_make_three_levels():
    data = dataset(2)
    for row in data["observations"]:
        row["noise"]["sample_count"] = 100
    assert all(
        g["candidate_level_count"] == 2
        for g in suite.analyze_observations(data)["groups"]
    )
    data["observations"].append(deepcopy(data["observations"][0]))
    with pytest.raises(suite.LightnessTestError, match="duplicate"):
        suite.analyze_observations(data)


def test_controllers_and_target_groups_are_not_pooled():
    data = dataset(2)
    data["observations"][0]["comparison_id"] = "DIFFERENT_TARGET"
    report = suite.analyze_observations(data)
    assert all(g["candidate_level_count"] <= 2 for g in report["groups"])
    assert not any(g["requested_level_screen_pass"] for g in report["groups"])


def test_missing_controller_is_explicit():
    report = suite.analyze_observations(dataset(3, ("CS1",)))
    assert report["missing_controllers"] == ["CS2"]
    assert report["qualified_count"] == 0


def test_aliasing_one_roi_under_different_recipe_is_rejected():
    data = dataset()
    data["observations"][4]["roi"] = deepcopy(data["observations"][0]["roi"])
    with pytest.raises(suite.LightnessTestError, match="one physical ROI"):
        suite.analyze_observations(data)


def test_position_labels_must_match_physical_quadrants():
    data = dataset()
    data["observations"][0]["roi"]["x"] = 300
    with pytest.raises(suite.LightnessTestError, match="physical ROI quadrant"):
        suite.analyze_observations(data)


def test_missing_experiment_phase_cannot_pass_screen():
    data = dataset()
    data["identity"]["test_phase"] = None
    result = suite.analyze_observations(data)
    assert "test_phase" in result["identity_and_protocol"]["missing_bindings"]
    assert not any(g["requested_level_screen_pass"] for g in result["groups"])


def test_adjacent_hue_similarity_is_not_whole_chain_similarity():
    data = dataset()
    for row in data["observations"]:
        angle = math.radians(4 * int(row["recipe_id"][1:]))
        row["lab"][1:] = [30 * math.cos(angle), 30 * math.sin(angle)]
    assert all(
        g["candidate_level_count"] == 2
        for g in suite.analyze_observations(data)["groups"]
    )


@pytest.mark.parametrize(
    "failure",
    [
        "missing_position",
        "position",
        "noise",
        "quality",
        "dither",
        "neutral",
        "captures",
    ],
)
def test_invalid_optical_signal_cannot_pass_ladder(failure):
    data = dataset()
    for row in data["observations"]:
        if row["recipe_id"] == "R1":
            if failure == "position" and row["position"] == "BR":
                row["lab"][0] += 20
            elif failure == "noise":
                row["noise"]["lstar_mad"] = 10
            elif failure == "quality":
                row["quality_pass"] = False
            elif failure == "dither":
                row["single_pixel_uniform"] = False
            elif failure == "neutral":
                row["lab"][1:] = [1, 2]
            elif failure == "captures":
                row["noise"]["sample_count"] = 9
    if failure == "missing_position":
        data["observations"] = [
            r
            for r in data["observations"]
            if not (r["recipe_id"] == "R1" and r["position"] == "BR")
        ]
    result = suite.analyze_observations(data)
    assert not any(g["requested_level_screen_pass"] for g in result["groups"])


def test_local_rank_reversal_rejected_even_when_medians_separate():
    data = dataset(2)
    for row in data["observations"]:
        row["lab"][0] = 40 + 3 * int(row["recipe_id"][1:])
        if row["position"] == "TL":
            row["lab"][0] += 2 if row["recipe_id"] == "R0" else -2
    result = suite.analyze_observations(data)
    assert not any(
        p["candidate_pair_pass"] for g in result["groups"] for p in g["pairs"]
    )


@pytest.mark.parametrize(
    "failure",
    [
        "nan",
        "bool",
        "bad_camera",
        "phase_guess",
        "threshold_change",
        "bad_roi",
        "override",
    ],
)
def test_malformed_or_incompatible_data_is_rejected(failure):
    data = dataset()
    if failure in ("nan", "bool"):
        data["observations"][0]["lab"][0] = float("nan") if failure == "nan" else True
    elif failure == "bad_camera":
        data["camera"]["usb_id"] = "VID_1BCF:PID_0B15"
    elif failure == "phase_guess":
        data["waveform_internal_phase"] = "DRIVE"
    elif failure == "threshold_change":
        data["threshold_version"] = "relaxed"
    elif failure == "bad_roi":
        data["observations"][0]["roi"]["width"] = 1024
    else:
        data["observations"][0]["boot"] = "foreign"
    with pytest.raises(ValueError):
        suite.analyze_observations(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("protocol_result", "FAIL"),
        ("protocol_result", "UNKNOWN"),
        ("image_result", "FAIL"),
    ],
)
def test_optics_cannot_override_failed_or_missing_review(field, value):
    data = dataset()
    data[field] = value
    report = suite.analyze_observations(data)
    assert not any(g["requested_level_screen_pass"] for g in report["groups"])
    assert report["verdict"] == (
        "FAIL_STOP"
        if field == "protocol_result" and value == "FAIL"
        else "HOLD_FOR_EVIDENCE"
    )


def test_unknown_temperature_and_calibration_not_invented():
    data = dataset()
    data["identity"]["temperature_c"] = None
    report = suite.analyze_observations(data)
    assert "temperature_c" in report["identity_and_protocol"]["missing_bindings"]
    assert not any(g["requested_level_screen_pass"] for g in report["groups"])
    data["lab_space"] = "calibrated"
    with pytest.raises(ValueError, match="calibration"):
        suite.analyze_observations(data)


def test_history_geometry_and_blank_package_are_non_executable(tmp_path):
    output = tmp_path / "package"
    assert cli.create_package(output)["cells"] == 128
    data = json.loads((output / "observations.blank.json").read_text(encoding="utf-8"))
    assert len(data["observations"]) == 128
    for controller in suite.CONTROLLERS:
        for recipe in geometry.recipe_map():
            found = [
                r
                for r in data["observations"]
                if r["controller"] == controller
                and r["recipe_id"] == recipe["recipe_id"]
            ]
            assert {r["position"] for r in found} == set(suite.POSITIONS)
            assert all(r["lab"] is None for r in found)
    plan = json.loads((output / "test-plan.json").read_text(encoding="utf-8"))
    verify_integrity(plan, "plan")
    assert (
        plan["history_screen"]["required_separate_visible_actions_per_construction"]
        == 3
    )
    assert not plan["live_entry"]["runner_generated"]
    assert plan["frame_rate_branch"]["selected_test_values"] is None
    report = json.loads((output / "blank-evaluation.json").read_text(encoding="utf-8"))
    assert report["verdict"] == "HOLD_FOR_EVIDENCE"
    assert report["qualified_count"] == 0
    before = (output / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        cli.create_package(output)
    assert before == (output / "manifest.json").read_bytes()


def test_field_data_requires_real_hashes_and_no_implicit_overwrite(tmp_path):
    data = dataset()
    data["data_origin"] = "FIELD_DERIVED"
    source = tmp_path / "source.json"
    source.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="existing hashed"):
        cli.checked_analysis(data, source)
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}", encoding="utf-8")
    data["evidence_files"] = [cli.bind(evidence)]
    with pytest.raises(ValueError, match="not bound"):
        cli.checked_analysis(data, source)
    for row in data["observations"]:
        row["measurement_evidence_sha256"] = data["evidence_files"][0]["sha256"]
    source.write_text(json.dumps(data), encoding="utf-8")
    report = cli.checked_analysis(data, source)
    assert report["qualified_count"] == 0  # A matching file hash is not physical proof.
    output = tmp_path / "out.json"
    cli.write_new(output, report)
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        cli.write_new(output, report)
    assert output.read_bytes() == before
    evidence.write_text('{"changed":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        cli.checked_analysis(data, source)
