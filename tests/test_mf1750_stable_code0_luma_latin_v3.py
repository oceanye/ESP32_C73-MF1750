from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from tools import mf1750_stable_code0_luma_latin_v3_once as once
from tools import mf1750_stable_code0_luma_latin_v3_pack as pack


def test_pack_is_sealed_and_all_four_actions_are_compiled() -> None:
    report = pack.build_report()
    checked = pack.dry_validate(verify_source=True, verify_artifacts=True)
    assert checked["result"] == "PASS"
    assert checked["identity_state"] == "FINAL_ALL_L1_L4_BOUND"
    assert [item["ordinal"] for item in report["actions"]] == [1, 2, 3, 4]
    assert report["actions"][2]["frame"] == report["actions"][3]["frame"]
    assert report["actions"][2]["cs1_dtm"] == report["actions"][3]["cs1_dtm"]
    assert report["actions"][2]["cs2_dtm"] == report["actions"][3]["cs2_dtm"]
    assert report["actions"][2]["action_id"] != report["actions"][3]["action_id"]


def test_latin_layout_and_cs2_decoder_are_position_balanced() -> None:
    recipes = pack.recipe_map()
    assert len(recipes) == 128
    for controller in (0, 1):
        rows = [item for item in recipes if item["controller"] == controller]
        assert Counter(item["middle"]["code"] for item in rows) == Counter(
            {code: 8 for code in range(8)}
        )
        for row in range(8):
            assert {
                item["middle"]["code"]
                for item in rows
                if item["physical_row"] == row
            } == set(range(8))
        for column in range(8):
            assert {
                item["middle"]["code"]
                for item in rows
                if item["physical_column"] == column
            } == set(range(8))
    for item in recipes:
        assert item["source"] == {"global_header": "active", "code": 7}
        assert item["middle"]["global_header"] == "commented"
        assert item["target"] == {"global_header": "active", "code": 0}
        if item["controller"] == 1:
            assert item["decoder"]["transform"] == "rotate_180_from_cs1"
            assert item["decoder"]["logical_row"] == 7 - item["physical_row"]
            assert item["decoder"]["logical_column"] == 7 - item["physical_column"]


def test_controller_roles_and_alternative_branch_are_explicit() -> None:
    contract = pack.build_report()["contract"]
    registry = contract["target_hue_registry"]
    assert registry["cs2_role"] == "RED_FAMILY_PRIMARY_OBSERVATION"
    assert registry["cs1_role"] == "CONTROLLER_SPECIFIC_INTERNAL_CONTROL"
    assert registry["controller_color_equivalence_claimed"] is False
    policy = contract["source_authority"]["schedule_policy"]
    assert policy["not_sequential_after_luma_gray_mechanism_v2"] is True
    assert policy["no_intervening_panel_refresh_since_w11_white_required"] is True
    assert contract["l4_identical_target_repeat"]["autochain"] is False


def test_compiled_sources_bind_active_and_commented_535_and_l4() -> None:
    driver = (pack.REPO_ROOT / "src/ec5_stable_code0_luma_latin_v3_driver.inc").read_text(
        encoding="utf-8"
    )
    config = (
        pack.REPO_ROOT / "src/ec5_stable_code0_luma_latin_v3_main_config.inc"
    ).read_text(encoding="utf-8")
    report = pack.build_report()
    assert "ph_lut::active::kTransmittedR20PrefixBytes == 535" in driver
    assert "ph_lut::commented::kTransmittedR20PrefixBytes == 535" in driver
    for action in report["actions"][:3]:
        assert action["descriptor_id"] in config
        assert action["action_id"] in config
    assert "scl3::kL4DescriptorId" in config
    assert "scl3::kL4ActionId" in config


def test_l4_requires_separate_permission_before_any_request(monkeypatch: pytest.MonkeyPatch) -> None:
    touched = False

    def requester(*args: object, **kwargs: object) -> object:
        nonlocal touched
        touched = True
        raise AssertionError("requester must not be reached")

    with pytest.raises(once.base.runner.RecheckError, match="own explicit"):
        once.run_once(
            "http://127.0.0.1",
            4,
            claims=Path("unused"),
            output=Path("unused.json"),
            requester=requester,
            confirm_j2_on=True,
            confirm_gnd_normal=True,
            confirm_source_w11_camera_white=True,
            confirm_no_intervening_refresh_since_w11_white=False,
        )
    assert touched is False


def test_l2_uses_prior_complete_not_false_w11_no_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(once.pack, "validate_source_authority", lambda: {"verified": True})
    monkeypatch.setattr(once, "_verify_local_artifacts", lambda: None)
    monkeypatch.setattr(
        once,
        "_validate_diagnostic",
        lambda path, base_url: {"boot_nonce": "0123456789abcdef"},
    )
    observed: dict[str, object] = {}

    def fake_run(base_url: str, ordinal: int, **kwargs: object) -> dict[str, object]:
        observed.update({"base_url": base_url, "ordinal": ordinal, **kwargs})
        return {"ok": True}

    monkeypatch.setattr(once.v3, "run_once", fake_run)
    result = once.run_once(
        "http://127.0.0.1",
        2,
        claims=Path("claims"),
        output=Path("result.json"),
        requester=lambda *args, **kwargs: (200, {}),
        confirm_j2_on=True,
        confirm_gnd_normal=True,
        confirm_source_w11_camera_white=True,
        confirm_no_intervening_refresh_since_w11_white=False,
    )
    assert result == {"ok": True}
    assert observed["ordinal"] == 2


@pytest.mark.parametrize("entry", ["diagnose", "l1"])
def test_v2_alternative_branch_collision_blocks_before_any_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entry: str
) -> None:
    output_root = tmp_path / "v2-output"
    output_root.mkdir()
    (output_root / "action.json").write_text("{}", encoding="utf-8")
    claims_root = tmp_path / "v2-claims"
    monkeypatch.setattr(once, "ALTERNATIVE_V2_OUTPUT_ROOT", output_root)
    monkeypatch.setattr(once, "ALTERNATIVE_V2_CLAIMS_ROOT", claims_root)
    touched = False

    def requester(*args: object, **kwargs: object) -> object:
        nonlocal touched
        touched = True
        raise AssertionError("requester must not be reached")

    with pytest.raises(once.base.runner.RecheckError, match="alternative W11"):
        if entry == "diagnose":
            once.diagnose_j2_off(
                "http://127.0.0.1",
                confirm_j2_off=True,
                confirm_no_intervening_refresh_since_w11_white=True,
                requester=requester,
            )
        else:
            once.run_once(
                "http://127.0.0.1",
                1,
                claims=tmp_path / "claims",
                output=tmp_path / "output.json",
                requester=requester,
                confirm_j2_on=True,
                confirm_gnd_normal=True,
                confirm_source_w11_camera_white=True,
                confirm_no_intervening_refresh_since_w11_white=True,
            )
    assert touched is False
