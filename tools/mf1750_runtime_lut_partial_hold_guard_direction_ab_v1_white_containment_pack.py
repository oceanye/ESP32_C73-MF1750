#!/usr/bin/env python3
"""Offline identity pack for guard-direction A/B OTP-white containment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = (
    "MF1750_EC5_RUNTIME_LUT_PTLW_GUARD_DIRECTION_AB_WHITE_CONTAINMENT_V1_2026-08-24"
)
TEST_ID = "EC5-RUNTIME-LUT-PTLW-GUARD-DIRECTION-AB-WHITE-CONTAINMENT-V1"
CAMPAIGN_ID = "EC5_RUNTIME_LUT_PTLW_GUARD_DIRECTION_AB_WHITE_CONTAINMENT_V1"
SOURCE_CAMPAIGN_ID = "EC5_RUNTIME_LUT_PTLW_GUARD_DIRECTION_AB_V1"
ENVIRONMENT = "ec5_runtime_lut_partial_hold_guard_direction_ab_v1_white_containment"
PROFILE_ID = "WF23_25"
CONTRACT_ID = "5f1dd4cd9eff1c1824bab257fb2014665320d6493c64461daecb2ea3d2b56296"
NVS_NAMESPACE = "rlph_gdw_v1"
NVS_KEY = "used_gdw1"
DESCRIPTOR_ID = "d466ee023380509cdfa4d593f73028288a4c877a93fef17162343de662cbafd5"
ACTION_ID = "ff0c34170da3d20660e35dc79a57107ff42123979f38f488b9609b1292a9ba0b"
FRAME_SHA256 = "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
DTM_SHA256 = "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158"
FRAME_FNV1A = 0x13340DC5
DTM_FNV1A = 0xB7A855C5
DEVICE_API_VERSION = (
    "MF1750_EC5_RUNTIME_LUT_PTLW_GUARD_DIRECTION_AB_WHITE_CONTAINMENT_DEVICE_V1"
)
IDENTITY_REVISION = "runtime-lut-ptlw-guard-direction-ab-white-containment-v1"
CLASSIFICATION = (
    "FACTORY_OTP_WHITE_GUARD_DIRECTION_AB_CONTAINMENT_ONE_ACTION_NO_RUNTIME_PAYLOAD"
)
CLAIM_KIND = "mf1750-guard-direction-ab-white-containment-claim"
RESULT_KIND = "mf1750-guard-direction-ab-white-containment-result"
DESCRIPTOR_MARKER = (
    "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
    "ROLE=OTP_WHITE_GUARD_DIRECTION_AB_CONTAINMENT|SHA256=" + DESCRIPTOR_ID
)
FIRMWARE_BIN = REPO_ROOT / Path(
    ".pio/build-runtime-lut-partial-hold-guard-direction-ab-v1-white-containment/"
    "ec5_runtime_lut_partial_hold_guard_direction_ab_v1_white_containment/"
    "firmware.bin"
)
FIRMWARE_ELF = REPO_ROOT / Path(
    ".pio/build-runtime-lut-partial-hold-guard-direction-ab-v1-white-containment/"
    "ec5_runtime_lut_partial_hold_guard_direction_ab_v1_white_containment/"
    "firmware.elf"
)
FIRMWARE_BIN_BYTES = 786_544
FIRMWARE_BIN_SHA256 = "41fbf8a5c60f749ef1321a1397552c0e84696aae7975c5571d1b8b085cd9667d"
FIRMWARE_ELF_BYTES = 13_214_128
FIRMWARE_ELF_SHA256 = "7f4f2b3873fdc04870d3cc8ad5cdf0e971beaa4fc602b8d3688898f842424154"
BASE_ROUTE = "/api/ec5/runtime-lut-ptlw-guard-direction-ab-v1/white-containment"
ARM_INTENT = "ARM_ONE_FIXED_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION"
EXECUTE_INTENT = "EXECUTE_ONE_FIXED_FACTORY_OTP_WHITE_ONCE"


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
        raise ValueError("guard-direction A/B containment artifact binding differs")
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
        "use_after_guard_action_2_or_4_abnormal": True,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-guard-direction-ab-white-containment-pack",
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
