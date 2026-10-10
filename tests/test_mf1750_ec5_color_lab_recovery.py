from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import pytest

from tools import mf1750_ec5_color_lab_campaign as superseded_campaign
from tools import mf1750_ec5_color_lab_contract as superseded_contract
from tools import mf1750_ec5_color_lab_recovery_campaign as campaign
from tools import mf1750_ec5_color_lab_recovery_compiled_identity as identity
from tools import mf1750_ec5_color_lab_recovery_contract as contract


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/ec5_color_lab_recovery_main.cpp"
CONFIG = ROOT / "platformio.color_lab_recovery.ini"
BUILD = ROOT / ".pio/build/esp32-s3-devkitc-1-ec5-color-lab-recovery"
BUNDLE = (
    ROOT
    / ".test-output/hardware/MF1750_EC5_COLOR_LAB_RECOVERY_REAL_COMPARE_BOUND_20260810_V3_SELF_CONTAINED"
)


def _literal(source: str, name: str) -> str:
    match = re.search(
        rf'static constexpr const char \*{re.escape(name)}\s*=\s*"([^"]+)";',
        source,
    )
    assert match is not None, name
    return match.group(1)


def _between(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    return source[begin : source.index(end, begin)]


def test_recovery_identity_and_every_action_id_are_new() -> None:
    manifest = contract.campaign_manifest()
    assert manifest["contract_id"] == (
        "52eb05232f6ad2fe001c6fe0e6c96864c69a9a058a4626e84eb5cbe1377d4736"
    )
    assert contract.CAMPAIGN_ID == "EC5_COLOR_LAB_RECOVERY_CAMPAIGN_V1"
    assert contract.BUILD_TAG == "MF1750_EC5_COLOR_LAB_RECOVERY_V1_2026-08-10"
    assert contract.TEST_ID == "EC5-COLOR-LAB-RECOVERY-V1"
    assert contract.DEVICE_API_VERSION == (
        "MF1750_EC5_COLOR_LAB_RECOVERY_DEVICE_V1"
    )
    assert contract.IDENTITY_REVISION == "color-lab-recovery-v1"
    assert len(contract.DESCRIPTORS) == 23
    assert all(
        new["hardware_action_id"] != old["hardware_action_id"]
        and new["descriptor_id"] != old["descriptor_id"]
        for new, old in zip(
            contract.DESCRIPTORS, superseded_contract.DESCRIPTORS, strict=True
        )
    )
    assert len({item["hardware_action_id"] for item in contract.DESCRIPTORS}) == 23
    assert contract.DESCRIPTORS[0]["hardware_action_id"] == (
        "04ace39dc527f7fa4d6141f2ccd128a5b97c2a6832e526e98d1d24573795aa95"
    )
    assert contract.DESCRIPTORS[-1]["hardware_action_id"] == (
        "402bcad1424195543edd100f58c342d2b897e244d720c0c08156ca49eaf3e753"
    )


def test_recovery_reuses_only_frame_bytes_not_campaign_identity() -> None:
    for new, old in zip(
        contract.DESCRIPTORS, superseded_contract.DESCRIPTORS, strict=True
    ):
        assert new["role"] == old["role"]
        assert new["frame_sha256"] == old["frame_sha256"]
        assert new["cs1_dtm_sha256"] == old["cs1_dtm_sha256"]
        assert new["cs2_dtm_sha256"] == old["cs2_dtm_sha256"]
        descriptor_preimage = {
            key: value
            for key, value in new.items()
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
        ).hexdigest() == new["descriptor_id"]
        assert hashlib.sha256(
            contract.canonical_json_bytes(new["action_identity_preimage"])
        ).hexdigest() == new["hardware_action_id"]


def test_new_nvs_namespace_ignores_old_fault_without_erasing_anything() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert contract.NVS_NAMESPACE == "mf1750_ec5clr"
    assert contract.NVS_KEY == "cursor_r1"
    assert len(contract.NVS_NAMESPACE) <= 15
    assert _literal(source, "kNvsNamespace") == contract.NVS_NAMESPACE
    assert _literal(source, "kNvsKey") == contract.NVS_KEY
    setup = _between(source, "void setup()", "void loop()")
    assert "cursorStore.begin(kNvsNamespace, false /* readOnly */)" in setup
    assert "mf1750_ec5cl" not in setup
    for forbidden in (
        "cursorStore.clear(",
        "cursorStore.remove(",
        "nvs_flash_erase",
        "WiFi.disconnect(true",
        "esp_wifi_restore",
    ):
        assert forbidden not in source
    migration = contract.campaign_manifest()["recovery_migration"]
    assert migration == {
        "old_nvs_namespace": "mf1750_ec5cl",
        "old_nvs_key": "cursor",
        "old_state_ignored_not_cleared": True,
        "global_nvs_clear": False,
        "wifi_credentials_preserved": True,
    }


def test_firmware_literals_table_and_payload_kinds_match_recovery_contract() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    manifest = contract.campaign_manifest()
    for name, wanted in {
        "kIdentityRevision": contract.IDENTITY_REVISION,
        "kDeviceApiVersion": contract.DEVICE_API_VERSION,
        "kLayoutId": contract.LAYOUT_ID,
        "kBuildTag": contract.BUILD_TAG,
        "kTestId": contract.TEST_ID,
        "kCampaignId": contract.CAMPAIGN_ID,
        "kContractId": manifest["contract_id"],
    }.items():
        assert _literal(source, name) == wanted
    table = _between(
        source, "static constexpr ActionDescriptor kActions[] = {", "#undef"
    )
    for item in contract.DESCRIPTORS:
        assert item["descriptor_id"] in table
        assert item["hardware_action_id"] in table
    for old in superseded_contract.DESCRIPTORS:
        assert old["descriptor_id"] not in table
        assert old["hardware_action_id"] not in table
    for kind in ("version", "manifest", "status", "report"):
        assert f"mf1750-ec5-color-lab-recovery-{kind}" in source
    compiled_campaign = campaign.build_campaign()
    assert compiled_campaign["device_contract"]["arm_intent"] == _literal(
        source, "kArmIntent"
    )
    assert compiled_campaign["device_contract"]["execute_intent"] == _literal(
        source, "kExecuteIntent"
    )


def test_runtime_remains_one_shot_fail_closed_with_no_startup_refresh() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    setup = _between(source, "void setup()", "void loop()")
    worker = _between(source, "void executePendingAction()", "}  // namespace")
    assert "epdDisplayCompiledColorLab" not in setup
    assert source.count("epdDisplayCompiledColorLab(") == 1
    assert worker.count("epdDisplayCompiledColorLab(action->driverRole)") == 1
    assert "requestHasBodyOrArguments()" in source
    assert "body_or_arguments_forbidden" in source
    assert "enterFault(error, action)" in source
    assert r'\"automatic_chaining\":false' in source
    assert r'\"startup_refresh\":false' in source
    assert r'\"raw_frame_ingress\":false' in source
    assert r'\"retry\":false' in source
    assert r'\"recovery\":false' in source


def test_platformio_build_isolated_from_superseded_main() -> None:
    config = CONFIG.read_text(encoding="utf-8")
    assert "esp32-s3-devkitc-1-ec5-color-lab-recovery" in config
    assert "+<ec5_color_lab_recovery_main.cpp>" in config
    assert "-<ec5_color_lab_main.cpp>" in config
    assert "EPD_ENABLE_TEST_PATTERN=0" in config


def test_clean_built_bin_and_elf_link_and_compiled_symbols() -> None:
    binary = BUILD / "firmware.bin"
    elf = BUILD / "firmware.elf"
    assert binary.is_file() and elf.is_file()
    report = identity.validate(elf)
    assert report["valid"] is True
    assert report["contract_id"] == contract.campaign_manifest()["contract_id"]
    assert report["action_count"] == 23
    link = campaign._binary_elf_link(binary.read_bytes(), elf.read_bytes())
    assert link["exact_match"] is True
    assert link["selected_elf_sha256"] == report["elf_sha256"]


def test_real_recovery_release_replays_compare_and_permanent_incident_claim() -> None:
    release_file = BUNDLE / "color-lab-recovery-real-release.json"
    checked = campaign.validate_materialized_release(release_file)
    assert checked["execution_eligible"] is True
    assert checked["canonical_sha256"] == (
        "93a7f1e617909d7fad9ff1dbff59b9e83d3951d9c6519084da1da22536cf1d4a"
    )
    root = json.loads(release_file.read_text(encoding="utf-8"))
    boundary = root["recovery_boundary"]
    assert boundary["old_action_id"] == (
        superseded_contract.DESCRIPTORS[0]["hardware_action_id"]
    )
    assert boundary["incident_result"]["outcome"] == (
        "unknown_do_not_retry_or_recover"
    )
    assert boundary["old_authorization_remains_consumed"] is True
    assert boundary["old_claim_must_not_be_removed_or_reused"] is True
    assert boundary["old_fault_state_ignored_not_cleared"] is True
    assert boundary["global_nvs_clear"] is False
    assert boundary["wifi_credentials_preserved"] is True
    assert root["predecessor_binding"]["latest_visible_state"] == (
        "u04_u05_compare_four_blue_patches"
    )


def test_self_contained_bundle_is_sealed_and_authorizes_no_refresh() -> None:
    checked = campaign.validate_bundle(BUNDLE / "bundle-manifest.json")
    assert checked["execution_eligible"] is True
    assert checked["visible_refresh_authorized_by_bundle"] == 0
    assert checked["file_sha256"] == (
        "94aa9aa23fbd23bf37dda142f7e7ba5a6f69c5db309adcdd8707dfac8bd32dcc"
    )
    assert checked["canonical_sha256"] == (
        "ffda1caa8c362f9adcdabc60ba2a41f1c2a310daf4c225a2d01f84301571aa0c"
    )


def test_superseded_v2_release_is_fail_closed() -> None:
    old_release = (
        ROOT
        / ".test-output/hardware/MF1750_EC5_COLOR_LAB_REAL_COMPARE_BOUND_20260809_V2_SELF_CONTAINED/color-lab-real-release.json"
    )
    with pytest.raises(
        superseded_campaign.ColorLabCampaignError,
        match="release is superseded.*V3_SELF_CONTAINED",
    ):
        superseded_campaign.validate_materialized_release(old_release)
