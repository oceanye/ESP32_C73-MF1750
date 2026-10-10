#!/usr/bin/env python3
"""Offline identity pack for the brightness campaign's fresh OTP-white containment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tools import mf1750_runtime_lut_hue_brightness_redpink_v1_pack as source_pack


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = (
    "MF1750_EC5_TARGET_HUE_REDPINK_BRIGHTNESS_V1_WHITE_CONTAINMENT_"
    "SOURCE_SAME_BOOT_V1_2026-08-27"
)
TEST_ID = "EC5-TARGET-HUE-REDPINK-BRIGHTNESS-V1-WHITE-CONTAINMENT"
CAMPAIGN_ID = "EC5_TARGET_HUE_REDPINK_BRIGHTNESS_V1_WHITE_CONTAINMENT"
SOURCE_CAMPAIGN_ID = "EC5_TARGET_HUE_REDPINK_BRIGHTNESS_8X8_ABA_V1"
SOURCE_MAIN_CONTRACT_ID = (
    "df7ecdc4ef3d443766045e7c242cbb9109cb3f3f6415ad926c70babf7f000278"
)
ENVIRONMENT = "ec5_runtime_lut_hue_brightness_redpink_v1_white_containment"
PROFILE_ID = "WF23_25"
CONTRACT_ID = "10867bcecf8da5a4e716bd34547d437c7a426a3b4318a64a1bce3c1963c79020"
NVS_NAMESPACE = "rlhrpcw_v1"
NVS_KEY = "used_rpcw1"
DESCRIPTOR_ID = "bfa5851856cec82f5dae397208d38591aea941ba339f10a1b9d1d86a93026b49"
ACTION_ID = "3f51f507d3d7f739cf66100177223d34aca3b6cfea1d027ca84cf5eb82d94f54"
FRAME_SHA256 = "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
DTM_SHA256 = "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158"
FRAME_FNV1A = 0x13340DC5
DTM_FNV1A = 0xB7A855C5
DEVICE_API_VERSION = (
    "MF1750_EC5_TARGET_HUE_REDPINK_BRIGHTNESS_V1_WHITE_CONTAINMENT_DEVICE_V1"
)
IDENTITY_REVISION = (
    "target-hue-redpink-brightness-v1-white-containment-source-same-boot-v2"
)
CLASSIFICATION = (
    "FACTORY_OTP_WHITE_BRIGHTNESS_CAMPAIGN_CONTAINMENT_ONE_ACTION_NO_RUNTIME_PAYLOAD"
)
CLAIM_KIND = "mf1750-target-hue-redpink-brightness-v1-white-containment-claim"
RESULT_KIND = "mf1750-target-hue-redpink-brightness-v1-white-containment-result"
DESCRIPTOR_MARKER = (
    "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
    "ROLE=BRIGHTNESS_REDPINK_OTP_WHITE_CONTAINMENT|SHA256=" + DESCRIPTOR_ID
)
FIRMWARE_BIN = REPO_ROOT / Path(
    ".pio/build-runtime-lut-hue-brightness-redpink-v1-white-containment/"
    "ec5_runtime_lut_hue_brightness_redpink_v1_white_containment/firmware.bin"
)
FIRMWARE_ELF = REPO_ROOT / Path(
    ".pio/build-runtime-lut-hue-brightness-redpink-v1-white-containment/"
    "ec5_runtime_lut_hue_brightness_redpink_v1_white_containment/firmware.elf"
)
# Bound to the clean 2026-08-27 build of the dedicated environment.
FIRMWARE_BIN_BYTES = 787_216
FIRMWARE_BIN_SHA256 = "277ee4168dbc0034889dd620d1dbe1931bac32b3260abe98a695df09d1c3d513"
FIRMWARE_ELF_BYTES = 13_214_292
FIRMWARE_ELF_SHA256 = "a6ea106b99c3a91e0e3362ea6110b05070e45869ef6d3d8cf76de3a3dec0c9db"
BASE_ROUTE = "/api/ec5/target-hue-redpink-brightness-v1/white-containment"
ARM_INTENT = (
    "ARM_ONE_FIXED_REDPINK_BRIGHTNESS_FACTORY_OTP_WHITE_"
    "CONTAINMENT_NOT_HARDWARE_AUTHORIZATION"
)
EXECUTE_INTENT = (
    "EXECUTE_ONE_FIXED_REDPINK_BRIGHTNESS_FACTORY_OTP_WHITE_CONTAINMENT_ONCE"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _descriptor_payload() -> dict[str, Any]:
    return {
        "schema": (
            "mf1750-target-hue-redpink-brightness-v1-white-containment-"
            "action-descriptor-v2"
        ),
        "profile_id": PROFILE_ID,
        "role": "FACTORY_OTP_WHITE_RECOVERY",
        "source_campaign_id": SOURCE_CAMPAIGN_ID,
        "source_main_contract_id": SOURCE_MAIN_CONTRACT_ID,
        "source_main_contract_exact_binding": True,
        "source_main_device_enforced_same_boot": True,
        "source_main_direct_exact_post_resume_after_reboot": False,
        "main_campaign_resume_after_containment": False,
        "frame_sha256": FRAME_SHA256,
        "cs1_dtm_sha256": DTM_SHA256,
        "cs2_dtm_sha256": DTM_SHA256,
    }


def _action() -> dict[str, Any]:
    return {
        "ordinal": 1,
        "role": "FACTORY_OTP_WHITE_RECOVERY",
        "descriptor_id": DESCRIPTOR_ID,
        "action_id": ACTION_ID,
        "frame_sha256": FRAME_SHA256,
        "cs1_dtm_sha256": DTM_SHA256,
        "cs2_dtm_sha256": DTM_SHA256,
    }


def _contract_payload(action: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "mf1750-target-hue-redpink-brightness-v1-white-containment-contract-v1",
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "source_campaign_id": SOURCE_CAMPAIGN_ID,
        "source_main_contract_id": SOURCE_MAIN_CONTRACT_ID,
        "source_main_contract_exact_binding": True,
        "source_main_device_enforced_same_boot": True,
        "source_main_direct_exact_post_resume_after_reboot": False,
        "main_campaign_resume_after_containment": False,
        "containment_terminal_for_source_campaign": True,
        "source_main_nvs_boot_key": source_pack.NVS_BOOT_KEY,
        "ordinal4_no_visible_difference_branch": True,
        "source_main_ordinals_5_and_6_forbidden_after_branch": True,
        "relay_off_required_before_containment": True,
        "environment": ENVIRONMENT,
        "profile_id": PROFILE_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "base_route": BASE_ROUTE,
        "actions": [action],
        "busy_qualification": {
            "raw_idle_level": 1,
            "host_preflight_required": True,
            "firmware_arm_required": True,
            "firmware_execute_required": True,
            "firmware_dispatch_required": True,
            "busy_zero_accepted": False,
        },
        "fresh_identity": True,
        "independent_nvs_and_claims": True,
        "campaign_nvs_dependency": False,
        "factory_otp_white_only": True,
        "runtime_payload": False,
        "startup_refresh": False,
        "retry": False,
        "automatic_recovery": False,
        "autochain": False,
        "ordinal_skip": False,
    }


def artifact_binding_status() -> dict[str, Any]:
    """Report exact local artifact presence without accessing any device."""

    result: dict[str, Any] = {}
    for key, path, byte_count, wanted in (
        ("firmware_bin", FIRMWARE_BIN, FIRMWARE_BIN_BYTES, FIRMWARE_BIN_SHA256),
        ("firmware_elf", FIRMWARE_ELF, FIRMWARE_ELF_BYTES, FIRMWARE_ELF_SHA256),
    ):
        present = path.is_file() and not path.is_symlink()
        observed_bytes = path.stat().st_size if present else None
        observed_sha256 = _sha256(path) if present else None
        result[key] = {
            "present": present,
            "verified": (
                present
                and byte_count > 0
                and observed_bytes == byte_count
                and observed_sha256 == wanted
            ),
            "observed_bytes": observed_bytes,
            "observed_sha256": observed_sha256,
        }
    return result


def build_report(*, verify_artifacts: bool = True) -> dict[str, Any]:
    """Return the independent one-action contract and local artifact proof."""

    source_contract_observed = source_pack.build_report()["contract_id"]
    if source_contract_observed != SOURCE_MAIN_CONTRACT_ID:
        raise ValueError("red/pink source main contract binding differs")
    if _canonical_sha256(_descriptor_payload()) != DESCRIPTOR_ID:
        raise ValueError("red/pink containment descriptor identity differs")
    wanted_action_id = hashlib.sha256(
        (
            "MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_WHITE_CONTAINMENT_ACTION_V1|"
            + DESCRIPTOR_ID
        ).encode("ascii")
    ).hexdigest()
    if wanted_action_id != ACTION_ID:
        raise ValueError("red/pink containment action identity differs")

    artifacts = {
        "firmware_bin": {
            "path": str(FIRMWARE_BIN),
            "bytes": FIRMWARE_BIN_BYTES,
            "sha256": FIRMWARE_BIN_SHA256,
        },
        "firmware_elf": {
            "path": str(FIRMWARE_ELF),
            "bytes": FIRMWARE_ELF_BYTES,
            "sha256": FIRMWARE_ELF_SHA256,
        },
    }
    binding_status = artifact_binding_status()
    if verify_artifacts:
        for name, key in (("BIN", "firmware_bin"), ("ELF", "firmware_elf")):
            if binding_status[key]["verified"] is not True:
                raise ValueError(f"brightness containment {name} binding differs")
    action = _action()
    contract_payload = _contract_payload(action)
    if _canonical_sha256(contract_payload) != CONTRACT_ID:
        raise ValueError("red/pink containment contract identity differs")
    contract = {**contract_payload, "contract_id": CONTRACT_ID}
    return {
        "schema_version": 1,
        "kind": "mf1750-target-hue-redpink-brightness-v1-white-containment-pack",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "contract": contract,
        "source_main_binding": {
            "expected_contract_id": SOURCE_MAIN_CONTRACT_ID,
            "observed_contract_id": source_contract_observed,
            "exact": True,
            "device_enforced_same_boot": True,
            "direct_exact_post_resume_after_reboot": False,
            "nvs_boot_key": source_pack.NVS_BOOT_KEY,
            "resume_allowed_after_containment": False,
            "ordinal4_no_visible_difference_branch": True,
            "source_main_ordinals_5_and_6_forbidden_after_branch": True,
            "relay_off_required_before_containment": True,
        },
        "action": action,
        "artifacts": artifacts,
        "artifact_binding_status": binding_status,
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
