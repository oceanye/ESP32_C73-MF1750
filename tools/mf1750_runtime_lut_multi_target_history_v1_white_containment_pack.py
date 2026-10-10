#!/usr/bin/env python3
"""Offline identity pack for multi-target-history V1 fresh OTP-white containment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "MF1750_EC5_MULTI_TARGET_HISTORY_8X8_AB_BA_V1_WHITE_CONTAINMENT_2026-08-24"
TEST_ID = "EC5-MULTI-TARGET-HISTORY-8X8-AB-BA-V1-WHITE-CONTAINMENT"
CAMPAIGN_ID = "EC5_MULTI_TARGET_HISTORY_8X8_AB_BA_V1_WHITE_CONTAINMENT"
SOURCE_CAMPAIGN_ID = "EC5_MULTI_TARGET_HISTORY_8X8_AB_BA_V1"
ENVIRONMENT = "ec5_runtime_lut_multi_target_history_v1_white_containment"
PROFILE_ID = "WF23_25"
CONTRACT_ID = "56d037a9347269a6658aa47126ccd9ed9f1e1b568b3690ab7abe77be2b385428"
NVS_NAMESPACE = "rlmthw_v1"
NVS_KEY = "used_mthw1"
DESCRIPTOR_ID = "aa5298e792d28a266d2e217407d8fe3ff8b320c3e0d2e101b1b5005ab7f00e36"
ACTION_ID = "6c36c36d8b27fe7259cc2c698d20325d35f73dbacbe4f3ba924f25a97d6a7edc"
FRAME_SHA256 = "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
DTM_SHA256 = "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158"
FRAME_FNV1A = 0x13340DC5
DTM_FNV1A = 0xB7A855C5
DEVICE_API_VERSION = (
    "MF1750_EC5_MULTI_TARGET_HISTORY_8X8_AB_BA_V1_WHITE_CONTAINMENT_DEVICE_V1"
)
IDENTITY_REVISION = "runtime-lut-multi-target-history-v1-white-containment-v1"
CLASSIFICATION = "FACTORY_OTP_WHITE_MULTI_TARGET_HISTORY_CAMPAIGN_CONTAINMENT_ONE_ACTION_NO_RUNTIME_PAYLOAD"
CLAIM_KIND = "mf1750-runtime-lut-multi-target-history-v1-white-containment-claim"
RESULT_KIND = "mf1750-runtime-lut-multi-target-history-v1-white-containment-result"
DESCRIPTOR_MARKER = (
    "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
    "ROLE=MULTI_TARGET_HISTORY_OTP_WHITE_CONTAINMENT|SHA256=" + DESCRIPTOR_ID
)
FIRMWARE_BIN = REPO_ROOT / Path(
    ".pio/build-runtime-lut-multi-target-history-v1-white-containment/"
    "ec5_runtime_lut_multi_target_history_v1_white_containment/firmware.bin"
)
FIRMWARE_ELF = REPO_ROOT / Path(
    ".pio/build-runtime-lut-multi-target-history-v1-white-containment/"
    "ec5_runtime_lut_multi_target_history_v1_white_containment/firmware.elf"
)
# Bound to the clean 2026-08-24 build of the dedicated environment.
FIRMWARE_BIN_BYTES = 786_512
FIRMWARE_BIN_SHA256 = "f6e943b302e752ca3dcafaa6ce3c724e3ed9484e03472169d1f88c76b792d9f2"
FIRMWARE_ELF_BYTES = 13_214_104
FIRMWARE_ELF_SHA256 = "88ee12f604db97fbe435b5b23897db35f5df33594d1cc2027702fe0a32fd8180"
BASE_ROUTE = "/api/ec5/runtime-lut-multi-target-history-v1/white-containment"
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
                raise ValueError(
                    f"multi-target-history containment {name} binding differs"
                )
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
        "kind": "mf1750-runtime-lut-multi-target-history-v1-white-containment-pack",
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
