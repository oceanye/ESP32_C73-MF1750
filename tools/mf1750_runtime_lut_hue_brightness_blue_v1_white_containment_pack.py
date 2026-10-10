#!/usr/bin/env python3
"""Offline identity pack for the brightness campaign's fresh OTP-white containment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "MF1750_EC5_TARGET_HUE_BLUE_BRIGHTNESS_V1_WHITE_CONTAINMENT_2026-08-24"
TEST_ID = "EC5-TARGET-HUE-BLUE-BRIGHTNESS-V1-WHITE-CONTAINMENT"
CAMPAIGN_ID = "EC5_TARGET_HUE_BLUE_BRIGHTNESS_V1_WHITE_CONTAINMENT"
SOURCE_CAMPAIGN_ID = "EC5_TARGET_HUE_BLUE_BRIGHTNESS_8X8_ABA_V1"
ENVIRONMENT = "ec5_runtime_lut_hue_brightness_blue_v1_white_containment"
PROFILE_ID = "WF23_25"
CONTRACT_ID = "ae9096e36998a956674db4b879685038b8b8d905b51b4db318c1387053fd0865"
NVS_NAMESPACE = "rlhbcw_v1"
NVS_KEY = "used_hbcw1"
DESCRIPTOR_ID = "0ce0319922e7e332a946f70315dadac10d4baa02051b746b15af292cdbb83baf"
ACTION_ID = "808d5fb9c582f944a96ea72754a7bdfb6f8996dc93cdbcf2f2f2f35e89838555"
FRAME_SHA256 = "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
DTM_SHA256 = "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158"
FRAME_FNV1A = 0x13340DC5
DTM_FNV1A = 0xB7A855C5
DEVICE_API_VERSION = (
    "MF1750_EC5_TARGET_HUE_BLUE_BRIGHTNESS_V1_WHITE_CONTAINMENT_DEVICE_V1"
)
IDENTITY_REVISION = "target-hue-blue-brightness-v1-white-containment-v1"
CLASSIFICATION = (
    "FACTORY_OTP_WHITE_BRIGHTNESS_CAMPAIGN_CONTAINMENT_ONE_ACTION_NO_RUNTIME_PAYLOAD"
)
CLAIM_KIND = "mf1750-target-hue-blue-brightness-v1-white-containment-claim"
RESULT_KIND = "mf1750-target-hue-blue-brightness-v1-white-containment-result"
DESCRIPTOR_MARKER = (
    "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
    "ROLE=BRIGHTNESS_BLUE_OTP_WHITE_CONTAINMENT|SHA256=" + DESCRIPTOR_ID
)
FIRMWARE_BIN = REPO_ROOT / Path(
    ".pio/build-runtime-lut-hue-brightness-blue-v1-white-containment/"
    "ec5_runtime_lut_hue_brightness_blue_v1_white_containment/firmware.bin"
)
FIRMWARE_ELF = REPO_ROOT / Path(
    ".pio/build-runtime-lut-hue-brightness-blue-v1-white-containment/"
    "ec5_runtime_lut_hue_brightness_blue_v1_white_containment/firmware.elf"
)
# Bound to the clean 2026-08-24 build of the dedicated environment.
FIRMWARE_BIN_BYTES = 786_448
FIRMWARE_BIN_SHA256 = "82e49e994570c9fb43ccbd7a7faa59adb55f5290d663aae2eee305250bcea12f"
FIRMWARE_ELF_BYTES = 13_214_100
FIRMWARE_ELF_SHA256 = "d1e895623fac56586cc6029d84644580dbbf76369ba6dd09badb7ac89e616250"
BASE_ROUTE = "/api/ec5/target-hue-blue-brightness-v1/white-containment"
ARM_INTENT = "ARM_ONE_FIXED_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION"
EXECUTE_INTENT = "EXECUTE_ONE_FIXED_FACTORY_OTP_WHITE_ONCE"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    action = {
        "ordinal": 1,
        "role": "FACTORY_OTP_WHITE_RECOVERY",
        "descriptor_id": DESCRIPTOR_ID,
        "action_id": ACTION_ID,
        "frame_sha256": FRAME_SHA256,
        "cs1_dtm_sha256": DTM_SHA256,
        "cs2_dtm_sha256": DTM_SHA256,
    }
    contract = {
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "source_campaign_id": SOURCE_CAMPAIGN_ID,
        "environment": ENVIRONMENT,
        "profile_id": PROFILE_ID,
        "contract_id": CONTRACT_ID,
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
    return {
        "schema_version": 1,
        "kind": "mf1750-target-hue-blue-brightness-v1-white-containment-pack",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "contract": contract,
        "action": action,
        "artifacts": artifacts,
        "artifact_binding_status": binding_status,
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
