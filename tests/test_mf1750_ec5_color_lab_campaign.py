from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from tools import mf1750_ec5_color_lab_campaign as campaign
from tools import mf1750_ec5_color_lab_contract as contract


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIRECTORY = REPO_ROOT / "tests" / "fixtures" / "ec5_color_lab"
FROZEN_ACTION_IDS = (
    "ecbd9684f901a33c2a8f483b9cdd2795c3a759aa6f5fd4e0ea514b658fbfcdbf",
    "b822084c1bc3730b48baa2c043735a160d805d767ace38194211401717468f99",
    "dda166efc7955ab35d57b5d90ac773c17130bbdf86671f6819e0508574ab383c",
    "f4f029aad202d04fe1da3dc62ce32a3100ee2af7197159b05667a3cbbbfc7a36",
    "5dc1934ef1803c6ea669ca16906a30cdfde819f57577b605461e7fdad792b06e",
    "225888ba99a09c0756fc5f71d083ab0fadae789128d6e7c07a6e4cd84be8af41",
    "8bd418db27f6f49e6a97b3bf2130c6a0388cace39feebfd158c9bd2496e5eb3c",
    "cf238fe37eb76a3a415fdea5d080fd5980e9e03d627867c6ddc6628c69b6ba51",
    "9424b75e30382c36a31e3cd5ad591cef2b830373aff223ceefa52b391ed84f18",
    "6ea14f9b7b635857a822e2c578a801a3b1485d9332b14ab14d46edcc68a88dd0",
    "800c89da0e12d45a70a75a7ca6bd6508b9ff895ba7d19e1a3378c29ecb19193e",
    "eae829a63f626a8532920b79daf710c965b5e18840f9cdcae2372356a83d676f",
    "1458bd2648c4513163740c30de6d2024a09decf74ba3d1a89a5c7819da676121",
    "f9ea7c4c8fbad989de3860511d64a37ac107b8bc71634e16bc918c61ac6c1503",
    "813ea6f1bf39a76b77a0b0e9100aaba1e068410d2411822b8a5d3f34e817fd1e",
    "13e9fb6bfbbac5c5e2bd6061684e522fb4c07cc1cf2ae79a1b35022d43dd9861",
    "c6f3668eef796b3e43dea227772a1b1627b2ea4eb61d9999b62bf8648a7f858b",
    "bb3045f988d84d4e3c70f2acea4cedcbaad55fae4b002cc99067f39cc0232c6f",
    "588222c323994fc0ec0e12816465345f9abc363b6f4eea76b16a0db61f8edc23",
    "d70883ca065ed47029f9273640329eaea1533a4eef46a763a2972aca0936794a",
    "f315c38bdff3a3c82a8e45df1c71fb7183902b03bb694477f4ba6bb20e98b875",
    "d6140a5bd60c25c500cac79f60e855f643370c3ccab225eb4e4b4bfb44d12d51",
    "db8297118746ae176d6484579834eb1003a745b23cb158198a720ef6621fc8b7",
)


def _write(path: Path, value: object) -> None:
    path.write_bytes(campaign.canonical_json_bytes(value))


def test_compiler_reuses_exact_firmware_contract_and_frozen_ids() -> None:
    root = campaign.build_campaign()
    actions = root["actions"]
    assert root["firmware_contract_id"] == (
        "7a5c7f1ecf5265fdffe0b3b3d2448c00106d49f128cb3a15e5b41ad7e97b968a"
    )
    assert root["firmware_contract"] == contract.campaign_manifest()
    assert tuple(item["action_id"] for item in actions) == FROZEN_ACTION_IDS
    assert tuple(item["hardware_action_id"] for item in actions) == FROZEN_ACTION_IDS
    assert [item["ordinal"] for item in actions] == list(range(1, 24))
    assert len(set(FROZEN_ACTION_IDS)) == 23


def test_sequence_is_fixed_nodither_and_first_round_stops_on_white() -> None:
    root = campaign.build_campaign()
    actions = root["actions"]
    assert [item["role"] for item in actions[:11]] == [
        contract.ROLE_WHITE,
        contract.ROLE_U07_ISOLATED,
        contract.ROLE_WHITE,
        contract.ROLE_ATLAS,
        contract.ROLE_WHITE,
        contract.ROLE_U04_PRIMER,
        contract.ROLE_U04_TARGET,
        contract.ROLE_WHITE,
        contract.ROLE_U07_PRIMER,
        contract.ROLE_U07_TARGET,
        contract.ROLE_WHITE,
    ]
    assert actions[4]["ordinal"] == campaign.FIRST_SAFE_STOP_ORDINAL
    assert actions[4]["role"] == contract.ROLE_WHITE
    assert actions[10]["ordinal"] == campaign.FIRST_FULL_ROUND_STOP_ORDINAL
    assert actions[10]["role"] == contract.ROLE_WHITE
    assert tuple(
        item["ordinal"]
        for item in actions
        if item["ordinal"] in campaign.RECOMMENDED_SAFE_STOP_ORDINALS
    ) == (5, 11, 23)
    assert all(item["frame"]["spatial_dithering"] is False for item in actions)
    assert all(item["frame"]["physical_colour_claim"] is False for item in actions)
    assert root["device_contract"]["same_firmware_without_reset_or_reflash"] is True
    assert root["device_contract"]["automatic_chaining"] is False
    assert root["device_contract"]["automatic_retry"] is False
    assert root["device_contract"]["automatic_recovery"] is False


def test_static_prior_chain_and_authorizations_are_unique() -> None:
    actions = campaign.build_actions()
    for index, action in enumerate(actions):
        expected = None if index == 0 else actions[index - 1]["action_id"]
        assert action["action_identity_preimage"]["prior_static_action_id"] == expected
    authorizations = [campaign.required_authorization(action) for action in actions]
    assert len(set(authorizations)) == 23
    assert authorizations[0].endswith(
        f"ACTION_{FROZEN_ACTION_IDS[0].upper()}__NO_RETRY_NO_RECOVERY"
    )


def test_compile_validate_is_immutable_and_tamper_evident(tmp_path: Path) -> None:
    path = tmp_path / "campaign.json"
    campaign.generate_campaign(path)
    checked = campaign.validate_campaign(path)
    assert checked["action_count"] == 23
    assert checked["first_safe_stop_ordinal"] == 5
    with pytest.raises(campaign.ColorLabCampaignError, match="overwrite"):
        campaign.generate_campaign(path)

    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["actions"][0]["role"] = "ATLAS_0_7"
    _write(tmp_path / "tampered.json", tampered)
    with pytest.raises(campaign.ColorLabCampaignError, match="integrity"):
        campaign.validate_campaign(tmp_path / "tampered.json")


def test_synthetic_materialization_is_valid_but_never_execution_eligible(
    tmp_path: Path,
) -> None:
    campaign_file = tmp_path / "campaign.json"
    release_file = tmp_path / "synthetic-release.json"
    campaign.generate_campaign(campaign_file)
    release = campaign.materialize_synthetic_release(
        campaign_file=campaign_file,
        fixture_directory=FIXTURE_DIRECTORY,
        output_file=release_file,
    )
    assert release["evidence_mode"] == campaign.SYNTHETIC_MODE
    assert release["execution_eligible"] is False
    assert release["state"] == "SYNTHETIC_OFFLINE_NOT_FOR_DEVICE"
    assert release["safety"]["network_requests"] == 0
    assert release["safety"]["claim_created"] is False
    checked = campaign.validate_materialized_release(release_file)
    assert checked["execution_eligible"] is False


def test_superseded_marker_disables_an_otherwise_valid_release(tmp_path: Path) -> None:
    campaign_file = tmp_path / "campaign.json"
    release_file = tmp_path / "synthetic-release.json"
    campaign.generate_campaign(campaign_file)
    campaign.materialize_synthetic_release(
        campaign_file=campaign_file,
        fixture_directory=FIXTURE_DIRECTORY,
        output_file=release_file,
    )
    marker = {
        "schema_version": 1,
        "kind": campaign.SUPERSEDED_MARKER_KIND,
        "state": campaign.SUPERSEDED_MARKER_STATE,
        "reason": "firmware BIN and ELF references point to mutable .pio build output",
        "superseded_by": campaign.V2_SELF_CONTAINED_RELEASE_DIRECTORY,
        "visible_refresh_authorized": False,
        "device_access_performed": False,
        "claim_created": False,
    }
    (tmp_path / campaign.SUPERSEDED_MARKER_NAME).write_bytes(
        campaign.canonical_json_bytes(marker)
    )
    with pytest.raises(campaign.ColorLabCampaignError, match="release is superseded"):
        campaign.validate_materialized_release(release_file)


def test_even_resealed_synthetic_release_cannot_claim_execution_eligibility(
    tmp_path: Path,
) -> None:
    campaign_file = tmp_path / "campaign.json"
    release_file = tmp_path / "synthetic-release.json"
    campaign.generate_campaign(campaign_file)
    release = campaign.materialize_synthetic_release(
        campaign_file=campaign_file,
        fixture_directory=FIXTURE_DIRECTORY,
        output_file=release_file,
    )
    unsigned = deepcopy(release)
    unsigned.pop("integrity")
    unsigned["execution_eligible"] = True
    _write(tmp_path / "forged.json", campaign._seal(unsigned))  # noqa: SLF001
    with pytest.raises(campaign.ColorLabCampaignError, match="safety boundary"):
        campaign.validate_materialized_release(tmp_path / "forged.json")


def test_fixture_hash_is_part_of_the_synthetic_boundary(tmp_path: Path) -> None:
    fixture_directory = tmp_path / "fixtures"
    fixture_directory.mkdir()
    for spec in campaign.SYNTHETIC_FIXTURES.values():
        source = FIXTURE_DIRECTORY / spec["file"]
        (fixture_directory / spec["file"]).write_bytes(source.read_bytes())
    target = fixture_directory / campaign.SYNTHETIC_FIXTURES["result"]["file"]
    target.write_bytes(target.read_bytes() + b"\n")
    campaign_file = tmp_path / "campaign.json"
    campaign.generate_campaign(campaign_file)
    with pytest.raises(campaign.ColorLabCampaignError, match="fixture"):
        campaign.materialize_synthetic_release(
            campaign_file=campaign_file,
            fixture_directory=fixture_directory,
            output_file=tmp_path / "release.json",
        )
