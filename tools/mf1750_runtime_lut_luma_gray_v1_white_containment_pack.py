#!/usr/bin/env python3
"""Fresh one-action factory-OTP white containment identity for LUMA-GRAY-V1."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_luma_gray_v1_pack as source_pack  # noqa: E402

BUILD_TAG = "MF1750_EC5_LUMA_GRAY_V1_FACTORY_OTP_WHITE_CONTAINMENT_2026-08-28"
TEST_ID = "EC5-LUMA-GRAY-V1-FACTORY-OTP-WHITE-CONTAINMENT"
CAMPAIGN_ID = "EC5_LUMA_GRAY_V1_FACTORY_OTP_WHITE_CONTAINMENT"
SOURCE_CAMPAIGN_ID = source_pack.CAMPAIGN_ID
SOURCE_MAIN_CONTRACT_ID = source_pack.build_report()["contract_id"]
PROFILE_ID = "WF23_25"
NVS_NAMESPACE = "rllgw_v1"
NVS_KEY = "used_lgw1"
FRAME_SHA256 = "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
DTM_SHA256 = "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158"
FRAME_FNV1A = 0x13340DC5
DTM_FNV1A = 0xB7A855C5
DEVICE_API_VERSION = "MF1750_EC5_LUMA_GRAY_V1_WHITE_CONTAINMENT_DEVICE_V1"
IDENTITY_REVISION = "luma-gray-v1-white-containment-fresh-identity-v1"
CLASSIFICATION = (
    "FACTORY_OTP_WHITE_LUMA_GRAY_V1_CONTAINMENT_ONE_ACTION_NO_RUNTIME_PAYLOAD"
)
BASE_ROUTE = "/api/ec5/luma-gray-v1/white-containment"
ARM_INTENT = "ARM_ONE_FIXED_LUMA_GRAY_V1_FACTORY_OTP_WHITE_CONTAINMENT_NOT_HARDWARE_AUTHORIZATION"
EXECUTE_INTENT = "EXECUTE_ONE_FIXED_LUMA_GRAY_V1_FACTORY_OTP_WHITE_CONTAINMENT_ONCE"
CONTRACT_ID = "d75573f6413dd861411147047c3784e0560de44241017eafc3cf46c274b99736"
DESCRIPTOR_ID = "4cd35729e2d512bcac1f476019149784e312d2ce19c52cf30e156407c91e6b3f"
ACTION_ID = "4622f4035bfc9d8cab7b260e7911e9a70b86529eeeb0a4c23ad86a30ba63794d"
CLAIM_KIND = "mf1750-luma-gray-v1-white-containment-claim"
RESULT_KIND = "mf1750-luma-gray-v1-white-containment-result"
FIRMWARE_BIN = (
    REPO_ROOT
    / ".pio/build-runtime-lut-luma-gray-v1-white-containment/ec5_runtime_lut_luma_gray_v1_white_containment/firmware.bin"
)
FIRMWARE_ELF = (
    REPO_ROOT
    / ".pio/build-runtime-lut-luma-gray-v1-white-containment/ec5_runtime_lut_luma_gray_v1_white_containment/firmware.elf"
)
FIRMWARE_BIN_BYTES = 786_944
FIRMWARE_BIN_SHA256 = "9c428924e225ef1dea6b04be7508745190ed5cda0a1bc8d12bf10146addfd6b6"
FIRMWARE_ELF_BYTES = 13_214_240
FIRMWARE_ELF_SHA256 = "fc2024e559d9477b3bb29bb915b9645fac2836ec7516894fc1b1cd771caddeff"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def build_report(*, verify_artifacts: bool = False) -> dict[str, Any]:
    descriptor_payload = {
        "schema": "mf1750-luma-gray-v1-white-containment-descriptor-v1",
        "profile_id": PROFILE_ID,
        "role": "FACTORY_OTP_WHITE_RECOVERY",
        "source_campaign_id": SOURCE_CAMPAIGN_ID,
        "source_main_contract_id": SOURCE_MAIN_CONTRACT_ID,
        "main_campaign_resume_after_containment": False,
        "frame_sha256": FRAME_SHA256,
        "cs1_dtm_sha256": DTM_SHA256,
        "cs2_dtm_sha256": DTM_SHA256,
    }
    descriptor_id = _sha(_canonical(descriptor_payload))
    action_id = _sha(
        f"MF1750_LUMA_GRAY_V1_WHITE_CONTAINMENT|{descriptor_id}".encode("ascii")
    )
    contract = {
        "schema": "mf1750-luma-gray-v1-white-containment-contract-v1",
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "source_campaign_id": SOURCE_CAMPAIGN_ID,
        "source_main_contract_id": SOURCE_MAIN_CONTRACT_ID,
        "profile_id": PROFILE_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "action_id": action_id,
        "descriptor_id": descriptor_id,
        "factory_otp": True,
        "runtime_lut_write": False,
        "one_visible_refresh": True,
        "startup_refresh": False,
        "retry": False,
        "automatic_recovery": False,
        "main_campaign_resume_after_containment": False,
        "qualified_gray_levels": 0,
        "true_neutral_gray_claimed": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-luma-gray-v1-white-containment-offline-identity",
        "offline_only": True,
        "hardware_accessed": False,
        "contract_id": _sha(_canonical(contract)),
        "descriptor_id": descriptor_id,
        "action_id": action_id,
        "action": {
            "ordinal": 1,
            "role": "FACTORY_OTP_WHITE_RECOVERY",
            "descriptor_id": descriptor_id,
            "action_id": action_id,
            "frame_sha256": FRAME_SHA256,
            "cs1_dtm_sha256": DTM_SHA256,
            "cs2_dtm_sha256": DTM_SHA256,
        },
        "contract": contract,
    }


if __name__ == "__main__":
    print(json.dumps(build_report(), indent=2, sort_keys=True))
