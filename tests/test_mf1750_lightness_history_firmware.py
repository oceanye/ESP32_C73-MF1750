from copy import deepcopy
import json

import pytest

from host.static_photo import lightness_history as algorithm
from host.static_photo.common import verify_integrity
from tools import mf1750_lightness_history_firmware as pack


@pytest.fixture(scope="module")
def contract():
    return pack.contract()


def test_all_single_pixel_recipes_have_four_quadrants_on_each_controller():
    for recipe in algorithm.recipes():
        for positions in recipe["positions"].values():
            assert len(positions) == 4
            assert {(p["row"] // 4, p["column"] // 4) for p in positions} == {
                (0, 0),
                (0, 1),
                (1, 0),
                (1, 1),
            }
            for stage in algorithm.STAGES:
                code = recipe[
                    {"SOURCE": "source", "MIDDLE": "middle", "TARGET": "target"}[stage]
                ]["code"]
                controller = 0 if positions is recipe["positions"]["cs1"] else 1
                frame = algorithm.frame(stage)
                for p in positions:
                    roi = p["local_roi"]
                    for y in range(roi["y"], roi["y"] + roi["height"]):
                        start = y * 512 + controller * 256 + roi["x"] // 2
                        assert frame[start : start + 20] == bytes([code * 17]) * 20


def test_contract_separates_actions_levels_and_physical_replicates(contract):
    assert contract["action_count"] == 3
    assert contract["level_counts"] == [3, 5, 10]
    assert contract["recipes_per_target"] == 8
    assert [a["global_header"] for a in contract["actions"]] == [
        "active",
        "commented",
        "active",
    ]
    for a in contract["actions"]:
        assert a["profile"]["cs1"] == a["profile"]["cs2"]
        assert a["waveform_internal_phase"] == "OPAQUE"
        assert a["frame"]["bytes"] == 307200
        assert a["visible_refresh_count"] == 1
    assert (
        contract["actions"][0]["profile"]["cs1"]["r20_prefix_sha256"]
        != contract["actions"][1]["profile"]["cs1"]["r20_prefix_sha256"]
    )
    assert (
        contract["actions"][2]["prior_action_id"] == contract["actions"][1]["action_id"]
    )
    body = deepcopy(contract)
    identity = body.pop("contract_id")
    assert algorithm.digest(algorithm.canonical(body)) == identity


@pytest.mark.parametrize("stage", ["WHITE", "REPEAT", "0", None])
def test_no_factory_white_or_unplanned_frame(stage):
    with pytest.raises(ValueError):
        algorithm.frame(stage)


def test_blank_results_never_award_qualification(contract):
    blank = algorithm.blank_observations(contract)
    assert len(blank["observations"]) == 128
    report = algorithm.analyze_bound(blank, contract)
    verify_integrity(report, "analysis")
    assert report["verdict"] == "HOLD_FOR_EVIDENCE"
    assert report["qualified_count"] == 0
    assert not report["ten_levels_need_more_distinct_recipes"]
    blank["requested_levels"] = 10
    assert algorithm.analyze_bound(blank, contract)[
        "ten_levels_need_more_distinct_recipes"
    ]


@pytest.mark.parametrize(
    "change",
    [
        "contract",
        "action",
        "profile",
        "frame",
        "roi",
        "controller",
        "recipe",
        "missing",
        "duplicate",
    ],
)
def test_wrong_action_or_geometry_cannot_be_relabelled(contract, change):
    data = algorithm.blank_observations(contract)
    if change == "contract":
        data["history_contract_id"] = "old"
    elif change in ("action", "profile", "frame"):
        key = {
            "action": "action_sha256",
            "profile": "profile_id",
            "frame": "frame_sha256",
        }[change]
        data["identity"][key] = "old"
    elif change == "roi":
        data["observations"][0]["roi"]["x"] += 2
    elif change == "controller":
        data["observations"][0]["controller"] = "CS2"
    elif change == "recipe":
        data["observations"][0]["recipe_id"] = "old-v3"
    elif change == "missing":
        data["observations"].pop()
    else:
        data["observations"][0] = deepcopy(data["observations"][1])
    with pytest.raises(ValueError):
        algorithm.analyze_bound(data, contract)


def test_seal_detects_modified_compiled_binary(tmp_path):
    source = tmp_path / "source.cpp"
    binary = tmp_path / "firmware.bin"
    log = tmp_path / "build.log"
    source.write_bytes(b"source")
    binary.write_bytes(b"binary")
    log.write_bytes(b"compile")
    manifest = pack.attach_integrity(
        {"contract_id": "c", "inputs": [pack.bind(source)], "outputs": []}
    )
    pack.write_new(tmp_path / "manifest.json", manifest)
    report = pack.attach_integrity(
        {
            "contract_id": "c",
            "result": "PASS",
            "manifest": pack.bind(tmp_path / "manifest.json"),
            "log": pack.bind(log),
            "artifacts": [pack.bind(binary)],
        }
    )
    pack.write_new(tmp_path / "build-report.json", report)
    assert pack.verify_package(tmp_path)["contract_id"] == "c"
    binary.write_bytes(b"changed")
    with pytest.raises(ValueError, match="compiled build binding"):
        pack.verify_package(tmp_path)


def test_write_new_preserves_existing_evidence(tmp_path):
    path = tmp_path / "evidence.json"
    pack.write_new(path, {"original": True})
    with pytest.raises(FileExistsError):
        pack.write_new(path, {"original": False})
    assert json.loads(path.read_text()) == {"original": True}
