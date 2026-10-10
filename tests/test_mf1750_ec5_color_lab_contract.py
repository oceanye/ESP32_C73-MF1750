from __future__ import annotations

import hashlib
from pathlib import Path

from tools import mf1750_ec5_color_lab_contract as contract
from tools import mf1750_ec5_eightcode_atlas as atlas
from tools import mf1750_ec5_sixstate_nodither as sixstate


ROOT = Path(__file__).resolve().parents[1]

EXPECTED_ACTION_IDS = (
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

BOOTSTRAP_ROLES = (
    contract.ROLE_WHITE,
    contract.ROLE_U07_ISOLATED,
    contract.ROLE_WHITE,
    contract.ROLE_ATLAS,
    contract.ROLE_WHITE,
)
ROUND_ROLES = (
    contract.ROLE_U04_PRIMER,
    contract.ROLE_U04_TARGET,
    contract.ROLE_WHITE,
    contract.ROLE_U07_PRIMER,
    contract.ROLE_U07_TARGET,
    contract.ROLE_WHITE,
)


def test_frozen_campaign_identity_and_twenty_three_action_sequence() -> None:
    manifest = contract.campaign_manifest()
    expected_roles = BOOTSTRAP_ROLES + ROUND_ROLES * 3
    assert len(contract.DESCRIPTORS) == 23
    assert tuple(item["ordinal"] for item in contract.DESCRIPTORS) == tuple(
        range(1, 24)
    )
    assert tuple(item["role"] for item in contract.DESCRIPTORS) == expected_roles
    assert tuple(item["hardware_action_id"] for item in contract.DESCRIPTORS) == (
        EXPECTED_ACTION_IDS
    )
    assert manifest["contract_id"] == (
        "7a5c7f1ecf5265fdffe0b3b3d2448c00106d49f128cb3a15e5b41ad7e97b968a"
    )


def test_each_action_and_descriptor_id_is_independently_canonical_and_chained() -> None:
    prior_action_id: str | None = None
    descriptor_ids: set[str] = set()
    action_ids: set[str] = set()
    for descriptor in contract.DESCRIPTORS:
        descriptor_preimage = {
            key: value
            for key, value in descriptor.items()
            if key
            not in {
                "descriptor_id",
                "hardware_action_id",
                "action_identity_preimage",
                "execution_eligible",
            }
        }
        assert hashlib.sha256(
            contract.canonical_json_bytes(descriptor_preimage)
        ).hexdigest() == descriptor["descriptor_id"]
        assert hashlib.sha256(
            contract.canonical_json_bytes(descriptor["action_identity_preimage"])
        ).hexdigest() == descriptor["hardware_action_id"]
        assert (
            descriptor["action_identity_preimage"]["prior_static_action_id"]
            == prior_action_id
        )
        assert descriptor["maximum_arm_posts"] == 1
        assert descriptor["maximum_execute_posts"] == 1
        assert descriptor["retry_allowed"] is False
        assert descriptor["recovery_included"] is False
        assert descriptor["automatic_chaining"] is False
        assert descriptor["execution_eligible"] is False
        descriptor_ids.add(descriptor["descriptor_id"])
        action_ids.add(descriptor["hardware_action_id"])
        prior_action_id = descriptor["hardware_action_id"]
    assert len(descriptor_ids) == 23
    assert len(action_ids) == 23


def test_role_bytes_are_recomputed_from_audited_atlas_and_stage_b_generators() -> None:
    assert contract.role_frame(contract.ROLE_WHITE) == atlas.build_frame("white")
    assert contract.role_frame(contract.ROLE_ATLAS) == atlas.build_frame("atlas")
    assert contract.role_frame(contract.ROLE_U04_PRIMER) == sixstate.build_frames(4)[0]
    assert contract.role_frame(contract.ROLE_U04_TARGET) == sixstate.build_frames(4)[1]
    assert contract.role_frame(contract.ROLE_U07_PRIMER) == sixstate.build_frames(7)[0]
    assert contract.role_frame(contract.ROLE_U07_TARGET) == sixstate.build_frames(7)[1]
    assert contract.role_frame(contract.ROLE_U04_PRIMER) == contract.role_frame(
        contract.ROLE_U07_PRIMER
    )
    assert contract.role_frame(contract.ROLE_U04_TARGET) != contract.role_frame(
        contract.ROLE_U07_TARGET
    )


def test_every_role_has_exact_frozen_full_frame_and_dual_dtm_identity() -> None:
    for role, frozen in contract.FROZEN_ROLE_SHA256.items():
        generated = contract.generated_role_identity(role)
        assert (
            generated["frame"]["sha256"],
            generated["cs1_dtm"]["sha256"],
            generated["cs2_dtm"]["sha256"],
        ) == frozen
        assert generated == contract.ROLE_IDENTITIES[role]
        assert generated["frame"]["bytes"] == atlas.FRAME_BYTES
        assert generated["cs1_dtm"]["bytes"] == atlas.CONTROLLER_FRAME_BYTES
        assert generated["cs2_dtm"]["bytes"] == atlas.CONTROLLER_FRAME_BYTES


def test_round_one_stop_is_authoritative_white_with_next_ordinal_twelve() -> None:
    manifest = contract.campaign_manifest()
    stop = contract.DESCRIPTORS[contract.ROUND_ONE_STOP_ORDINAL - 1]
    assert contract.ROUND_ONE_STOP_ORDINAL == 11
    assert stop["role"] == contract.ROLE_WHITE
    assert stop["frame_sha256"] == (
        "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
    )
    assert manifest["round_one_safe_stop_completed_ordinal"] == 11
    assert manifest["round_one_safe_stop_next_ordinal"] == 12


def test_atlas_and_targets_retain_their_manual_host_gates() -> None:
    atlas_action = contract.DESCRIPTORS[3]
    assert atlas_action["role"] == contract.ROLE_ATLAS
    assert {
        "isolated_u07_action_complete_pass_and_technical_claim",
        "isolated_u07_manual_observation",
        "immediately_preceding_clean_white_result_and_observation",
    }.issubset(atlas_action["required_host_gates"])
    for descriptor in contract.DESCRIPTORS:
        if descriptor["role"] == contract.ROLE_U04_TARGET:
            assert "u04_primer_map_fidelity_manual_pass" in descriptor[
                "required_host_gates"
            ]
        if descriptor["role"] == contract.ROLE_U07_TARGET:
            assert "u07_primer_map_fidelity_manual_pass" in descriptor[
                "required_host_gates"
            ]


def test_manifest_is_offline_blocked_and_requires_no_normal_step_power_cycle() -> None:
    manifest = contract.campaign_manifest()
    assert manifest["execution_eligible"] is False
    assert manifest["startup_refresh"] is False
    assert manifest["raw_frame_ingress"] is False
    assert manifest["dithering_present"] is False
    assert manifest["spatial_mixing_present"] is False
    assert manifest["automatic_chaining"] is False
    assert manifest["retry"] is False
    assert manifest["recovery"] is False
    assert manifest["normal_step_requires_reflash_reset_or_j2_cycle"] is False
    assert manifest["nvs_contract"] == {
        "namespace": "mf1750_ec5cl",
        "key": "cursor",
        "encoding": "uint16 high_byte_phase low_byte_next_ordinal",
        "initial_key_present": False,
        "initial_value": 1,
    }


def test_obsolete_invalid_u07t_action_is_absent() -> None:
    obsolete = "303bb39e"
    serialized = contract.canonical_json_bytes(contract.campaign_manifest())
    assert obsolete.encode("ascii") not in serialized
    assert obsolete not in (ROOT / "platformio.color_lab.ini").read_text(
        encoding="utf-8"
    )
