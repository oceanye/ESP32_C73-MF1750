from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from tools import mf1750_ec5_dither_effects_extension_campaign as campaign
from tools import mf1750_ec5_dither_effects_extension_contract as contract
from tools import mf1750_ec5_dither_effects_extension_physical_once as physical


ROOT = Path(__file__).resolve().parents[1]
STAGED = (
    ROOT / ".test-output/offline/"
    "MF1750_EC5_DITHER_EFFECTS_EXTENSION_STAGED_RELEASE_20260818_V2/"
    "dither-effects-extension-staged-release.json"
)


def test_contract_and_campaign_freeze_four_non_live_actions() -> None:
    manifest = contract.campaign_manifest()
    compiled = campaign.build_campaign()
    assert manifest["execution_eligible"] is False
    assert manifest["custom_lut_or_waveform"] is False
    assert manifest["raw_frame_ingress"] is False
    assert manifest["runtime_lut_write"] is False
    assert manifest["normal_step_requires_reflash_reset_or_j2_cycle"] is False
    assert len(contract.DESCRIPTORS) == campaign.ACTION_COUNT == 4
    assert compiled["action_count"] == 4
    assert compiled["white_checkpoint_ordinals"] == [2, 4]
    assert compiled["device_contract"]["same_firmware_without_reset_or_reflash"] is True
    assert compiled["device_contract"]["automatic_chaining"] is False
    assert (
        compiled["classification_contract"]["device_accessed_by_this_compiler"] is False
    )

    actions = compiled["actions"]
    assert [row["ordinal"] for row in actions] == [1, 2, 3, 4]
    assert [row["role"] for row in actions] == list(contract.ROLES)
    assert len({row["action_id"] for row in actions}) == 4
    assert actions[0]["action_identity_preimage"]["prior_static_action_id"] is None
    for previous, current in zip(actions, actions[1:]):
        assert (
            current["action_identity_preimage"]["prior_static_action_id"]
            == previous["action_id"]
        )


def test_authorizations_are_exact_unique_and_single_action_only() -> None:
    actions = campaign.build_actions()
    values = [campaign.required_authorization(action) for action in actions]
    assert len(set(values)) == 4
    for ordinal, (action, authorization) in enumerate(
        zip(actions, values, strict=True), start=1
    ):
        assert f"ORDINAL_{ordinal:02d}" in authorization
        assert action["action_id"].upper() in authorization
        assert authorization.endswith("__NO_RETRY_NO_RECOVERY_NO_AUTOCHAIN")


def test_materialized_staged_release_is_exact_and_not_executable() -> None:
    checked = campaign.validate_staged_release(STAGED)
    assert checked == {
        "file": str(STAGED.resolve()),
        "bytes": 11438,
        "file_sha256": physical.EXPECTED_STAGED_RELEASE_FILE_SHA256,
        "canonical_sha256": physical.EXPECTED_STAGED_RELEASE_CANONICAL_SHA256,
        "execution_eligible": False,
        "live_authorized": False,
        "action_count": 4,
        "firmware_binary_sha256": physical.EXPECTED_FIRMWARE_BINARY_SHA256,
        "firmware_elf_sha256": physical.EXPECTED_FIRMWARE_ELF_SHA256,
        "predecessor_action_id": contract.PREDECESSOR_ACTION_ID,
        "predecessor_evidence_pending": True,
        "visible_refresh_authorized_by_release": 0,
    }


def test_physical_runner_rejects_staged_release_before_any_device_path() -> None:
    with pytest.raises(
        physical.DitherEffectsExtensionPhysicalError,
        match="real release identity differs",
    ):
        physical.load_release(STAGED)


def test_physical_runner_binds_two_white_roles_and_dynamic_real_evidence() -> None:
    assert physical._ENGINE_CONTRACT.WHITE_ROLES == (  # noqa: SLF001
        contract.ROLE_WHITE_AFTER_GRADIENTS,
        contract.ROLE_WHITE_AFTER_EFFECTS,
    )
    assert physical._stable_hashes() == {  # noqa: SLF001
        "campaign file": physical.EXPECTED_CAMPAIGN_FILE_SHA256,
        "campaign canonical": physical.EXPECTED_CAMPAIGN_CANONICAL_SHA256,
        "staged release file": physical.EXPECTED_STAGED_RELEASE_FILE_SHA256,
        "staged release canonical": physical.EXPECTED_STAGED_RELEASE_CANONICAL_SHA256,
        "firmware binary": physical.EXPECTED_FIRMWARE_BINARY_SHA256,
        "firmware ELF": physical.EXPECTED_FIRMWARE_ELF_SHA256,
    }
    source = (ROOT / "tools/mf1750_ec5_dither_effects_extension_campaign.py").read_text(
        encoding="utf-8"
    )
    for token in (
        "atlas_once.validate_result",
        "atlas_once.validate_observation",
        'result.get("outcome") != "complete_pass"',
        'observation.get("visual", {}).get("full_clean_white") is not True',
        '"execution_eligible": True',
        '"live_authorized": False',
        '"visible_refresh_authorized_by_release": 0',
    ):
        assert token in source


def test_physical_runner_accepts_exact_spatial_mixing_device_surfaces() -> None:
    identity = {
        "schema_version": contract.TOP_SCHEMA_VERSION,
        "build_tag": contract.BUILD_TAG,
        "test_id": contract.TEST_ID,
        "campaign_id": contract.CAMPAIGN_ID,
        "device_api_version": contract.DEVICE_API_VERSION,
        "identity_revision": contract.IDENTITY_REVISION,
        "contract_id": contract.campaign_manifest()["contract_id"],
    }
    safety = {
        "automatic_chaining": False,
        "startup_refresh": False,
        "raw_frame_ingress": False,
        "runtime_lut_write": False,
        "electrical_parameter_write": False,
        "dither": True,
        "spatial_mixing": True,
        "single_pixel_multi_pigment_claim": False,
        "physical_colour_claim": False,
        "retry": False,
        "recovery": False,
    }
    version = {
        **identity,
        "kind": f"{physical.DEVICE_KIND_PREFIX}-version",
        "classification": contract.CLASSIFICATION,
        "layout_id": contract.LAYOUT_ID,
        "driver_api_version": "MF1750_R16_CASCADE_V3",
        "profile_source": "factory_otp",
        "action_count": campaign.ACTION_COUNT,
        "automatic_execute": False,
        **safety,
        "nvs_contract": physical._expected_nvs_contract(),  # noqa: SLF001
        "external_clean_white_anchor": (
            physical._expected_static_device_anchor()  # noqa: SLF001
        ),
    }
    actions = campaign.build_actions()
    manifest = {
        **identity,
        "kind": f"{physical.DEVICE_KIND_PREFIX}-manifest",
        "classification": contract.CLASSIFICATION,
        "layout_id": contract.LAYOUT_ID,
        "profile_source": "factory_otp",
        "action_count": campaign.ACTION_COUNT,
        "round_count": 1,
        "dither_layout": {
            "controller_count": 2,
            "controller_halves_semantically_identical": True,
            "controller_pattern_phase_identical": True,
            "mask": "bayer-8x8-rank-0-to-63",
            "mixture_resolution_units": 64,
            "appearance_names_are_hypotheses": True,
            "pair_gradients": {
                "rows": 7,
                "x0_local": 24,
                "width": 464,
                "y0": 14,
                "row_height": 72,
                "row_gap": 10,
            },
            "effects_chart": {
                "warm_trifield": True,
                "cool_trifield": True,
                "neutral_ramp": True,
                "native_blocks": 6,
                "detail_widths_pixels": [1, 2, 4, 8],
            },
        },
        "factory_otp": True,
        "custom_lut_or_waveform": False,
        "synchronous_both_controllers": True,
        "one_driver_call_per_action": True,
        **safety,
        "actions": [physical.engine._device_action(action) for action in actions],
        "nvs_contract": physical._expected_nvs_contract(),  # noqa: SLF001
        "external_clean_white_anchor": (
            physical._expected_static_device_anchor()  # noqa: SLF001
        ),
    }
    with physical._bound_engine():  # noqa: SLF001
        assert physical._effects_validate_version(version) == version  # noqa: SLF001
        assert (  # noqa: SLF001
            physical._effects_validate_manifest(manifest, actions) == manifest
        )
        invalid = deepcopy(version)
        invalid["dither"] = False
        with pytest.raises(
            physical.DitherEffectsExtensionPhysicalError,
            match="spatial-mixing fields differ",
        ):
            physical._effects_validate_version(invalid)  # noqa: SLF001
