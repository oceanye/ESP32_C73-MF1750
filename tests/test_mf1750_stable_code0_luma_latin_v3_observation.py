from __future__ import annotations

from copy import deepcopy

from tools import mf1750_stable_code0_luma_latin_v3_observation as observation


def _filled() -> dict[str, object]:
    value = observation.observation_template(include_l4=True)
    for capture in value["captures"].values():  # type: ignore[union-attr]
        capture["image_path"] = "offline-bound.jpg"
        capture["image_bytes"] = 123
        capture["image_sha256"] = "1" * 64
        capture["quality"] = {
            "both_controller_rois_visible": "PASS",
            "exposure_usable": "PASS",
            "focus_usable": "PASS",
            "glare_not_material": "PASS",
        }
    for item in value["measurements"]:  # type: ignore[index]
        code = int(item["middle_code"])
        item["lab"] = {"l_star": 35.0 + 3.0 * code, "a_star": 30.0, "b_star": 10.0}
        item["bottom_edge_stripe"] = "CLEAR"
    return value


def test_template_is_complete_and_decodable() -> None:
    value = observation.observation_template(include_l4=True)
    assert len(value["measurements"]) == 256
    assert {item["controller"] for item in value["measurements"]} == {"CS1", "CS2"}
    cs2 = [item for item in value["measurements"] if item["controller"] == "CS2"]
    assert all(item["decoder_transform"] == "rotate_180_from_cs1" for item in cs2)


def test_evaluator_never_auto_qualifies() -> None:
    result = observation.evaluate_observations(_filled(), verify_terminal=False)
    assert result["decision"] == "REVIEW_LUMA_MECHANISM_CANDIDATES"
    assert result["qualified_colour_count"] == 0
    assert result["qualified_gray_levels"] == 0
    assert result["automatic_qualification_forbidden"] is True
    assert set(result["controller_results"]) == {"CS1", "CS2"}


def test_bottom_edge_stripe_rejects() -> None:
    value = _filled()
    changed = deepcopy(value)
    changed["measurements"][0]["bottom_edge_stripe"] = "PRESENT"
    result = observation.evaluate_observations(changed, verify_terminal=False)
    assert result["decision"] == "REJECT_BOTTOM_EDGE_STRIPE_PRESENT"
