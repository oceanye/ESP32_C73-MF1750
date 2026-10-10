#!/usr/bin/env python3
"""Offline pack for the fresh RAW-P16 factory-OTP white containment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "MF1750_EC5_RAW_P16_ENDPOINT_GALLERY_WHITE_CONTAINMENT_V1_2026-08-28"
TEST_ID = "EC5-RAW-P16-ENDPOINT-GALLERY-WHITE-CONTAINMENT-V1"
CAMPAIGN_ID = "EC5_RAW_P16_ENDPOINT_GALLERY_WHITE_CONTAINMENT_V1"
SOURCE_CAMPAIGN_ID = "EC5_RAW_P16_ENDPOINT_GALLERY_V1"
ENVIRONMENT = "ec5_raw_p16_endpoint_gallery_v1_white_containment"
PROFILE_ID = "WF23_25"
CONTRACT_ID = "1d08798ba1a4012623c64625cec2edfaeb160aa3b20f0a2a98406994b55cce14"
NVS_NAMESPACE = "rp16gw_v1"
NVS_KEY = "used_p16w"
BASE_ROUTE = "/api/ec5/raw-p16-endpoint-gallery-v1/white-containment"
DEVICE_API_VERSION = "MF1750_EC5_RAW_P16_ENDPOINT_GALLERY_WHITE_CONTAINMENT_DEVICE_V1"
IDENTITY_REVISION = "raw-p16-endpoint-gallery-white-containment-v1"
CLASSIFICATION = (
    "FACTORY_OTP_WHITE_RAW_P16_ENDPOINT_GALLERY_CONTAINMENT_"
    "ONE_ACTION_NO_RUNTIME_PAYLOAD"
)
DESCRIPTOR_ID = "03920a12ad8f0b96e2dc6ae8281fa07da3cfb8ccc84da86dfb3f2cf2334f84dc"
ACTION_ID = "12a146d8ad678165e1061fda3e7569743e28d663ee349b46ee900196b95d8cd6"
FRAME_SHA256 = "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
DTM_SHA256 = "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158"
FRAME_FNV1A = 0x13340DC5
DTM_FNV1A = 0xB7A855C5
DESCRIPTOR_MARKER = (
    "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
    "ROLE=OTP_WHITE_RAW_P16_ENDPOINT_GALLERY_CONTAINMENT|SHA256=" + DESCRIPTOR_ID
)
FIRMWARE_BIN = REPO_ROOT / (
    ".pio/build-raw-p16-endpoint-gallery-v1-white-containment/"
    "ec5_raw_p16_endpoint_gallery_v1_white_containment/firmware.bin"
)
FIRMWARE_ELF = REPO_ROOT / (
    ".pio/build-raw-p16-endpoint-gallery-v1-white-containment/"
    "ec5_raw_p16_endpoint_gallery_v1_white_containment/firmware.elf"
)
FIRMWARE_BIN_BYTES = 786_448
FIRMWARE_BIN_SHA256 = "8c33085d0c9e0f03d651ad82a99a6336275f881fe9eb9e296cf526b5f80503c1"
FIRMWARE_ELF_BYTES = 13_214_304
FIRMWARE_ELF_SHA256 = "b65a4562b987de7adabe1d561504f1cf9c1b91d41b676ace32fd7adf81ab3a2a"
ARM_INTENT = "ARM_ONE_FIXED_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION"
EXECUTE_INTENT = "EXECUTE_ONE_FIXED_FACTORY_OTP_WHITE_ONCE"
CLAIM_KIND = "mf1750-raw-p16-endpoint-gallery-white-containment-claim"
RESULT_KIND = "mf1750-raw-p16-endpoint-gallery-white-containment-result"


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
        raise ValueError("RAW-P16 white-containment artifact binding differs")
    action = {
        "ordinal": 1,
        "role": "FACTORY_OTP_WHITE_CONTAINMENT",
        "descriptor_id": DESCRIPTOR_ID,
        "action_id": ACTION_ID,
        "frame_sha256": FRAME_SHA256,
        "cs1_dtm_sha256": DTM_SHA256,
        "cs2_dtm_sha256": DTM_SHA256,
    }
    contract = {
        "schema": "mf1750-raw-p16-endpoint-gallery-white-containment-contract-v1",
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "source_campaign_id": SOURCE_CAMPAIGN_ID,
        "profile_id": PROFILE_ID,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "base_route": BASE_ROUTE,
        "factory_otp_white_only": True,
        "runtime_payload": False,
        "startup_refresh": False,
        "retry": False,
        "automatic_recovery": False,
        "autochain": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-raw-p16-endpoint-gallery-white-containment-pack",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "contract_id": hashlib.sha256(
            json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
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
