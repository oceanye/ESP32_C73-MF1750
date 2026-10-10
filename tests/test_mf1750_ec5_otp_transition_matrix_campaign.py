from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from tools import mf1750_ec5_otp_transition_matrix_campaign as campaign
from tools import mf1750_ec5_otp_transition_matrix_contract as contract


FROZEN_CONTRACT_ID = (
    "6057b31eb8dd9e1a9a8222e937469465b9bac1991ef4a634f77f5aa8daebf8ca"
)
FROZEN_DESCRIPTOR_IDS = (
    "21d96bae9d994271a7916005b173d74b2113049d3ec7a8832655333105df8a9e",
    "fcb96838b86404b766a27989b0f6cf7465a77b28ba2cdb262fa1a609e5eada5a",
    "dcfcea2c8ab503fc2808f4c366e439bc216a189a0697d2f9d71b20108ba65f4f",
)
FROZEN_ACTION_IDS = (
    "056e47fedeafeda9568e7a6f25e7abca2a0659ea67534ab12f8114e2ea6eb27b",
    "a95d3c00bcb974b2740ec27103b6eb8e1f9ec7d43cfb100893fab47da6890d7c",
    "54190f82f4797d1e0d46b2e002f6cbad006bdcdd7eb73b6ae5c0325acbfcae77",
)
FROZEN_FRAME_AND_DTM_SHA256 = (
    (
        "01529ea97197e5435370a0eb77a9cabff167c129237952b7a627a0f4903744dc",
        "208c3d8e03329bbba08bb54cb5f84a9568349295ed750c749aad0e29f259017f",
        "d66c999e89ace23dd3a112c53e9ca1f7bbbc984772e08af4359dcd843740cb1c",
    ),
    (
        "e3f476f24176e4b5d0f196e6c3d912dabf5044f2cbac0a59bf63806d8d051a38",
        "4a980b33107b1d0c1da6282952d5adf8c32334af46be8f2e82aceb4c30a94387",
        "70d4f642ec98bb034de65fb350d51285e7f644dd42c5aa3e89de5b607f4643c3",
    ),
    (
        "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
        "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
        "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
    ),
)


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(campaign.canonical_json_bytes(value))


def _synthetic_identity_artifact() -> bytes:
    """Return inert bytes that get materialization as far as anchor replay."""
    needles = [
        contract.BUILD_TAG,
        contract.TEST_ID,
        contract.CAMPAIGN_ID,
        contract.DEVICE_API_VERSION,
        contract.campaign_manifest()["contract_id"],
        contract.NVS_NAMESPACE,
        contract.NVS_KEY,
        *campaign.ENDPOINTS.values(),
    ]
    needles.extend(
        identity
        for descriptor in contract.DESCRIPTORS
        for identity in (
            str(descriptor["descriptor_id"]),
            str(descriptor["hardware_action_id"]),
        )
    )
    return b"synthetic-non-firmware\0" + b"\0".join(
        item.encode("ascii") for item in needles
    )


def _materialize_arguments(tmp_path: Path) -> dict[str, Path]:
    return {
        "campaign_file": tmp_path / "campaign.json",
        "firmware_binary": tmp_path / "firmware.bin",
        "firmware_elf": tmp_path / "firmware.elf",
        "panel_file": tmp_path / "panel.json",
        "recovery_release_file": tmp_path / "missing-recovery-release.json",
        "anchor_result_file": tmp_path / "missing-anchor-result.json",
        "anchor_observation_file": tmp_path / "missing-anchor-observation.json",
        "anchor_claim_registry": tmp_path / "missing-anchor-claims",
        "formal_u07_claim_registry": tmp_path / "missing-formal-u07-claims",
        "output_file": tmp_path / "must-not-exist-release.json",
    }


def test_three_actions_have_exact_chain_identities_frames_and_both_dtm() -> None:
    contract.validate_contract()
    root = campaign.build_campaign()
    actions = root["actions"]

    assert root["action_count"] == 3
    assert root["firmware_contract_id"] == FROZEN_CONTRACT_ID
    assert root["firmware_contract"]["contract_id"] == FROZEN_CONTRACT_ID
    assert root["first_predecessor_action_id"] == campaign.FIRST_PREDECESSOR_ACTION_ID
    assert [action["ordinal"] for action in actions] == [1, 2, 3]
    assert [action["role"] for action in actions] == list(contract.ROLES)
    assert tuple(action["descriptor_id"] for action in actions) == (
        FROZEN_DESCRIPTOR_IDS
    )
    assert tuple(action["action_id"] for action in actions) == FROZEN_ACTION_IDS
    assert tuple(action["hardware_action_id"] for action in actions) == (
        FROZEN_ACTION_IDS
    )

    for index, (action, frozen_hashes) in enumerate(
        zip(actions, FROZEN_FRAME_AND_DTM_SHA256, strict=True)
    ):
        expected_prior = None if index == 0 else FROZEN_ACTION_IDS[index - 1]
        assert (
            action["action_identity_preimage"]["prior_static_action_id"]
            == expected_prior
        )
        assert (
            action["expected_prior_ordinal"]
            == (None if index == 0 else index)
        )
        assert (
            action["expected_prior_role"]
            == (None if index == 0 else contract.ROLES[index - 1])
        )

        frame = action["frame"]["frame"]
        controllers = frame["controllers"]
        assert frame["bytes"] == 307_200
        assert [item["controller"] for item in controllers] == ["CS1", "CS2"]
        assert [item["source_half"] for item in controllers] == [0, 1]
        assert [item["bytes"] for item in controllers] == [153_600, 153_600]
        assert (
            frame["sha256"],
            controllers[0]["sha256"],
            controllers[1]["sha256"],
        ) == frozen_hashes
        assert action["frame_sha256"] == frame["sha256"]
        assert action["cs1_dtm_sha256"] == controllers[0]["sha256"]
        assert action["cs2_dtm_sha256"] == controllers[1]["sha256"]


def test_campaign_is_explicitly_factory_otp_without_runtime_or_electrical_writes(
) -> None:
    root = campaign.build_campaign()
    firmware_contract = root["firmware_contract"]

    assert root["firmware_contract_id"] == firmware_contract["contract_id"]
    assert root["classification"] == {
        "profile_source": "factory_otp",
        "runtime_lut_or_waveform_changed": False,
        "transition_history_experiment": True,
        "physical_colour_claim": False,
        "device_accessed_by_this_compiler": False,
        "visible_refresh_authorized_by_this_compiler": False,
    }
    assert firmware_contract["profile_source"] == "factory_otp"
    assert firmware_contract["custom_lut_or_waveform"] is False
    assert firmware_contract["runtime_lut_write"] is False
    assert firmware_contract["electrical_parameter_write"] is False
    assert firmware_contract["raw_frame_ingress"] is False
    assert firmware_contract["startup_refresh"] is False
    assert all(
        action["frame"]["profile_source"] == "factory_otp"
        and action["frame"]["runtime_lut_write"] is False
        for action in root["actions"]
    )


def test_compile_and_validate_are_deterministic_immutable_and_tamper_evident(
    tmp_path: Path,
) -> None:
    first_file = tmp_path / "first.json"
    second_file = tmp_path / "second.json"
    first = campaign.generate_campaign(first_file)
    second = campaign.generate_campaign(second_file)

    assert first == second == campaign.build_campaign()
    assert first_file.read_bytes() == second_file.read_bytes()
    assert campaign.validate_campaign(first_file)["actions"] == first["actions"]
    assert campaign.validate_campaign(second_file)["file_sha256"] == (
        campaign.validate_campaign(first_file)["file_sha256"]
    )
    with pytest.raises(campaign.OtpTransitionMatrixCampaignError, match="overwrite"):
        campaign.generate_campaign(first_file)

    tampered = deepcopy(first)
    tampered["actions"][1]["frame"]["runtime_lut_write"] = True
    _write_json(tmp_path / "tampered.json", tampered)
    with pytest.raises(campaign.OtpTransitionMatrixCampaignError, match="integrity"):
        campaign.validate_campaign(tmp_path / "tampered.json")

    tampered.pop("integrity")
    _write_json(
        tmp_path / "resealed-tampered.json",
        campaign._seal(tampered),  # noqa: SLF001
    )
    with pytest.raises(campaign.OtpTransitionMatrixCampaignError, match="differs"):
        campaign.validate_campaign(tmp_path / "resealed-tampered.json")


def test_validate_rejects_duplicate_keys_and_non_regular_input(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_bytes(b'{"schema_version":1,"schema_version":1}')
    with pytest.raises(
        campaign.OtpTransitionMatrixCampaignError, match="duplicate JSON key"
    ):
        campaign.validate_campaign(duplicate)

    directory = tmp_path / "directory.json"
    directory.mkdir()
    with pytest.raises(
        campaign.OtpTransitionMatrixCampaignError, match="regular non-symlink file"
    ):
        campaign.validate_campaign(directory)


def test_validate_rejects_symlink_input(tmp_path: Path) -> None:
    target = tmp_path / "campaign.json"
    campaign.generate_campaign(target)
    link = tmp_path / "campaign-link.json"
    try:
        link.symlink_to(target.name)
    except OSError as error:
        pytest.skip(f"file symlinks are unavailable: {error}")

    with pytest.raises(
        campaign.OtpTransitionMatrixCampaignError, match="regular non-symlink file"
    ):
        campaign.validate_campaign(link)


def test_materializer_cannot_pass_or_emit_release_without_firmware(
    tmp_path: Path,
) -> None:
    arguments = _materialize_arguments(tmp_path)
    campaign.generate_campaign(arguments["campaign_file"])

    with pytest.raises(
        campaign.OtpTransitionMatrixCampaignError,
        match="could not read OTP transition-matrix firmware binary",
    ):
        campaign.materialize_real_release(**arguments)
    assert not arguments["output_file"].exists()
    assert not arguments["anchor_claim_registry"].exists()


def test_materializer_cannot_pass_or_emit_release_without_anchor(
    tmp_path: Path,
) -> None:
    arguments = _materialize_arguments(tmp_path)
    campaign.generate_campaign(arguments["campaign_file"])
    inert_artifact = _synthetic_identity_artifact()
    arguments["firmware_binary"].write_bytes(inert_artifact)
    arguments["firmware_elf"].write_bytes(inert_artifact)
    _write_json(
        arguments["panel_file"],
        {
            "model": "TEST-NOT-A-PANEL",
            "serial": "TEST-NOT-A-SERIAL",
            "board_id": "TEST-NOT-A-BOARD",
            "pcb_revision": "TEST-NOT-A-REVISION",
        },
    )

    with pytest.raises(RuntimeError):
        campaign.materialize_real_release(**arguments)
    assert not arguments["output_file"].exists()
    assert not arguments["anchor_claim_registry"].exists()


def test_binary_elf_link_requires_real_formats_and_exact_embedded_elf_hash() -> None:
    with pytest.raises(
        campaign.OtpTransitionMatrixCampaignError,
        match="does not bind",
    ):
        campaign._binary_elf_link(  # noqa: SLF001
            _synthetic_identity_artifact(), _synthetic_identity_artifact()
        )

    elf = b"\x7fELF" + b"\0" * 252
    binary = bytearray(b"\0" * 208)
    binary[0] = 0xE9
    binary[32:36] = bytes.fromhex("3254cdab")
    binary[176:208] = hashlib.sha256(elf).digest()
    link = campaign._binary_elf_link(bytes(binary), elf)  # noqa: SLF001
    assert link["exact_match"] is True
    assert link["selected_elf_sha256"] == hashlib.sha256(elf).hexdigest()

    binary[-1] ^= 1
    with pytest.raises(
        campaign.OtpTransitionMatrixCampaignError,
        match="does not bind",
    ):
        campaign._binary_elf_link(bytes(binary), elf)  # noqa: SLF001


def test_authorization_is_unique_per_action_and_never_implies_chaining() -> None:
    root = campaign.build_campaign()
    actions = root["actions"]
    authorizations = [campaign.required_authorization(action) for action in actions]

    assert len(set(authorizations)) == 3
    for ordinal, (action, authorization) in enumerate(
        zip(actions, authorizations, strict=True), start=1
    ):
        assert authorization == (
            "AUTHORIZE_ONE_VISIBLE_EC5_OTP_MATRIX_"
            f"ORDINAL_{ordinal:02d}__ACTION_{action['action_id'].upper()}"
            "__NO_RETRY_NO_RECOVERY_NO_AUTOCHAIN"
        )
        assert action["maximum_arm_posts"] == 1
        assert action["maximum_execute_posts"] == 1
        assert action["retry_allowed"] is False
        assert action["automatic_chaining"] is False
        assert "explicit_single_action_authorization" in action[
            "required_host_gates"
        ]

    device = root["device_contract"]
    assert device["maximum_arm_posts_per_action"] == 1
    assert device["maximum_execute_posts_per_action"] == 1
    assert device["automatic_chaining"] is False
    assert device["automatic_retry"] is False
    assert device["automatic_recovery"] is False
    assert root["firmware_contract"]["automatic_chaining"] is False
    with pytest.raises(campaign.OtpTransitionMatrixCampaignError, match="malformed"):
        campaign.required_authorization({"ordinal": True, "action_id": "not-an-id"})
    with pytest.raises(campaign.OtpTransitionMatrixCampaignError, match="malformed"):
        campaign.required_authorization({"ordinal": 1, "action_id": 123})
