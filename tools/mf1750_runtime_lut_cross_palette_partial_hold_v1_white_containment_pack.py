#!/usr/bin/env python3
"""Offline identity pack for the fresh one-action OTP-white containment image."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


BUILD_TAG = (
    "MF1750_EC5_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_"
    "WHITE_CONTAINMENT_2026-08-24"
)
TEST_ID = "EC5-RUNTIME-LUT-CROSS-PALETTE-PARTIAL-HOLD-WHITE-CONTAINMENT-V1"
CAMPAIGN_ID = "EC5_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_WHITE_CONTAINMENT"
ENVIRONMENT = "ec5_runtime_lut_cross_palette_partial_hold_v1_white_containment"
PROFILE_ID = "WF23_25"
CONTRACT_ID = "3b2c350e3bd0da41b251b83233db0f983af24cb4a6275386334f65fd4cb6f899"
NVS_NAMESPACE = "rlxphcw_v1"
NVS_KEY = "used_cxw1"
DESCRIPTOR_ID = "c1b96d538c3398160d1e839f27aeb99a2a70271a1ec623c9a2cff1936618c65c"
ACTION_ID = "d6cd1f2debd3eceb9168b8b614a1937bcedf6044ba98ef84b9f99c1a9255a5eb"
FRAME_SHA256 = "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
DTM_SHA256 = "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158"
FRAME_FNV1A = 0x13340DC5
DTM_FNV1A = 0xB7A855C5
DEVICE_API_VERSION = (
    "MF1750_EC5_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_"
    "WHITE_CONTAINMENT_DEVICE_V1"
)
IDENTITY_REVISION = "cross-palette-partial-hold-white-containment-v1"
CLASSIFICATION = "FACTORY_OTP_WHITE_RECOVERY_ONE_ACTION_NO_RUNTIME_PAYLOAD"
DESCRIPTOR_MARKER = (
    "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
    "ROLE=OTP_WHITE_CONTAINMENT|SHA256=" + DESCRIPTOR_ID
)
FIRMWARE_BIN = Path(
    ".pio/build-runtime-lut-cross-palette-partial-hold-v1-white-containment/"
    "ec5_runtime_lut_cross_palette_partial_hold_v1_white_containment/firmware.bin"
)
FIRMWARE_ELF = Path(
    ".pio/build-runtime-lut-cross-palette-partial-hold-v1-white-containment/"
    "ec5_runtime_lut_cross_palette_partial_hold_v1_white_containment/firmware.elf"
)
FIRMWARE_BIN_BYTES = 786_528
FIRMWARE_BIN_SHA256 = (
    "af13dcd2cf9190d81410898f585e66d663a0ccfeebfd36f856f99acc21c9fd53"
)
FIRMWARE_ELF_BYTES = 13_214_020
FIRMWARE_ELF_SHA256 = (
    "2871645352d38f115a57853376feebdad82ffdc184850efc39988dcdf5bd5775"
)
BASE_ROUTE = "/api/ec5/runtime-lut-cross-palette-partial-hold-v1/white-containment"
ARM_INTENT = "ARM_ONE_FIXED_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION"
EXECUTE_INTENT = "EXECUTE_ONE_FIXED_FACTORY_OTP_WHITE_ONCE"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_binding_status() -> dict[str, Any]:
    """Report artifact availability without making offline describe brittle."""

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
                and observed_bytes == byte_count
                and observed_sha256 == wanted
            ),
            "observed_bytes": observed_bytes,
            "observed_sha256": observed_sha256,
        }
    return result


def build_report(*, verify_artifacts: bool = True) -> dict[str, Any]:
    """Return the exact immutable one-action contract and optional file proof."""

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
                raise ValueError(f"containment {name} binding differs")
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
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-cross-palette-partial-hold-white-containment-pack",
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
