#!/usr/bin/env python3
"""Offline identity pack for fresh endpoint-A/B factory-OTP white containment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

BUILD_TAG = "MF1750_EC5_RUNTIME_LUT_PTLW_YEND_AB_WHITE_CONTAINMENT_V1_2026-08-24"
TEST_ID = "EC5-RUNTIME-LUT-PTLW-YEND-AB-WHITE-CONTAINMENT-V1"
CAMPAIGN_ID = "EC5_RUNTIME_LUT_PTLW_YEND_AB_WHITE_CONTAINMENT_V1"
ENVIRONMENT = "ec5_runtime_lut_partial_hold_endpoint_ab_v1_white_containment"
PROFILE_ID = "WF23_25"
CONTRACT_ID = "f4c17d37419554a744bb59b198265b2d4c4c69b3deab124324e44610ed701dc6"
NVS_NAMESPACE = "rlph_yew_v1"
NVS_KEY = "used_yew1"
DESCRIPTOR_ID = "781adbb114f3322164c8d2e3bc83a7de42eb23f04076889aa6a7aff71aaf2501"
ACTION_ID = "0f4a24cdc7cbdea612ae534c72cc76ffc2e9fafdc916d18b68ea9d5dafe8f80b"
FRAME_SHA256 = "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
DTM_SHA256 = "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158"
FRAME_FNV1A = 0x13340DC5
DTM_FNV1A = 0xB7A855C5
DEVICE_API_VERSION = "MF1750_EC5_RUNTIME_LUT_PTLW_YEND_AB_WHITE_CONTAINMENT_DEVICE_V1"
IDENTITY_REVISION = "runtime-lut-ptlw-yend-ab-white-containment-v1"
CLASSIFICATION = (
    "FACTORY_OTP_WHITE_ENDPOINT_AB_CONTAINMENT_ONE_ACTION_NO_RUNTIME_PAYLOAD"
)
DESCRIPTOR_MARKER = (
    "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
    "ROLE=OTP_WHITE_ENDPOINT_AB_CONTAINMENT|SHA256=" + DESCRIPTOR_ID
)
FIRMWARE_BIN = REPO_ROOT / Path(
    ".pio/build-runtime-lut-partial-hold-endpoint-ab-v1-white-containment/"
    "ec5_runtime_lut_partial_hold_endpoint_ab_v1_white_containment/firmware.bin"
)
FIRMWARE_ELF = REPO_ROOT / Path(
    ".pio/build-runtime-lut-partial-hold-endpoint-ab-v1-white-containment/"
    "ec5_runtime_lut_partial_hold_endpoint_ab_v1_white_containment/firmware.elf"
)
FIRMWARE_BIN_BYTES = 786_416
FIRMWARE_BIN_SHA256 = "7580b95291b329e832b543168e84d52fa2b2ba838e90a779323870f3b124102d"
FIRMWARE_ELF_BYTES = 13_214_068
FIRMWARE_ELF_SHA256 = "2c069827c6e2d4615b48be8fb4f94029edf8d36718fd99fd20be42d996648af8"
BASE_ROUTE = "/api/ec5/runtime-lut-ptlw-yend-ab-v1/white-containment"
ARM_INTENT = "ARM_ONE_FIXED_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION"
EXECUTE_INTENT = "EXECUTE_ONE_FIXED_FACTORY_OTP_WHITE_ONCE"
CLAIM_KIND = "mf1750-endpoint-ab-white-containment-claim"
RESULT_KIND = "mf1750-endpoint-ab-white-containment-result"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_binding_status() -> dict[str, Any]:
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
            "verified": bool(
                present and observed_bytes == byte_count and observed_sha256 == wanted
            ),
            "observed_bytes": observed_bytes,
            "observed_sha256": observed_sha256,
        }
    return result


def build_report(*, verify_artifacts: bool = True) -> dict[str, Any]:
    status = artifact_binding_status()
    if verify_artifacts and any(
        item["verified"] is not True for item in status.values()
    ):
        raise ValueError("endpoint A/B containment artifact binding differs")
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
        "factory_otp_white_only": True,
        "runtime_payload": False,
        "startup_refresh": False,
        "retry": False,
        "automatic_recovery": False,
        "autochain": False,
        "ordinal_skip": False,
        "use_after_main_action_2_or_4_abnormal": True,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-endpoint-ab-white-containment-pack",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "contract": contract,
        "action": action,
        "artifacts": {
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
        },
        "artifact_binding_status": status,
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
