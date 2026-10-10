#!/usr/bin/env python3
"""Offline identity pack for the brightness campaign's fresh OTP-white containment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = (
    "MF1750_EC5_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_V1_WHITE_CONTAINMENT_2026-08-26"
)
TEST_ID = "EC5-TARGET-HUE-YELLOW-OLIVE-BRIGHTNESS-V1-WHITE-CONTAINMENT"
CAMPAIGN_ID = "EC5_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_V1_WHITE_CONTAINMENT"
SOURCE_CAMPAIGN_ID = "EC5_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_8X8_ABA_V1"
ENVIRONMENT = "ec5_runtime_lut_hue_brightness_yellow_olive_v1_white_containment"
PROFILE_ID = "WF23_25"
CONTRACT_ID = "fbedf22afbe6129e2824b9726f8be16f8b949c77cf02eb49d9707166d1ec095b"
NVS_NAMESPACE = "rlhyocw_v1"
NVS_KEY = "used_yocw1"
DESCRIPTOR_ID = "99e0f93b79a8aef9e1e3256c76aec517d0bf37be8ee1b5d3074ee83c3296c3be"
ACTION_ID = "ac05c0d290e91a33e92f3eccb00bce68d35b6852bae813dfabbb6950d485d45b"
FRAME_SHA256 = "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
DTM_SHA256 = "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158"
FRAME_FNV1A = 0x13340DC5
DTM_FNV1A = 0xB7A855C5
DEVICE_API_VERSION = (
    "MF1750_EC5_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_V1_WHITE_CONTAINMENT_DEVICE_V1"
)
IDENTITY_REVISION = "target-hue-yellow-olive-brightness-v1-white-containment-v1"
CLASSIFICATION = (
    "FACTORY_OTP_WHITE_BRIGHTNESS_CAMPAIGN_CONTAINMENT_ONE_ACTION_NO_RUNTIME_PAYLOAD"
)
CLAIM_KIND = "mf1750-target-hue-yellow-olive-brightness-v1-white-containment-claim"
RESULT_KIND = "mf1750-target-hue-yellow-olive-brightness-v1-white-containment-result"
DESCRIPTOR_MARKER = (
    "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
    "ROLE=BRIGHTNESS_YELLOW_OLIVE_OTP_WHITE_CONTAINMENT|SHA256=" + DESCRIPTOR_ID
)
FIRMWARE_BIN = REPO_ROOT / Path(
    ".pio/build-runtime-lut-hue-brightness-yellow-olive-v1-white-containment/"
    "ec5_runtime_lut_hue_brightness_yellow_olive_v1_white_containment/firmware.bin"
)
FIRMWARE_ELF = REPO_ROOT / Path(
    ".pio/build-runtime-lut-hue-brightness-yellow-olive-v1-white-containment/"
    "ec5_runtime_lut_hue_brightness_yellow_olive_v1_white_containment/firmware.elf"
)
# Bound to the clean 2026-08-26 build of the dedicated environment.
FIRMWARE_BIN_BYTES = 786_544
FIRMWARE_BIN_SHA256 = "80dfebbd0f609203d1b4f7f9784389815bf0f54d8e3efb4b5fa42febc0b61ec1"
FIRMWARE_ELF_BYTES = 13_214_132
FIRMWARE_ELF_SHA256 = "4e846aca492bac6dc2d460c87aeb46a76eba97fc292fc5dde8536b73f84ee8e8"
BASE_ROUTE = "/api/ec5/target-hue-yellow-olive-brightness-v1/white-containment"
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
        "kind": "mf1750-target-hue-yellow-olive-brightness-v1-white-containment-pack",
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
