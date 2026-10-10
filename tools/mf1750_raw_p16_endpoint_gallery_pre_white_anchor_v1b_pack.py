#!/usr/bin/env python3
"""Offline pack for the successor RAW-P16 pre-gallery OTP-white anchor."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "MF1750_EC5_RAW_P16_ENDPOINT_GALLERY_PRE_WHITE_ANCHOR_V1B_2026-08-28"
TEST_ID = "EC5-RAW-P16-ENDPOINT-GALLERY-PRE-WHITE-ANCHOR-V1B"
CAMPAIGN_ID = "EC5_RAW_P16_ENDPOINT_GALLERY_PRE_WHITE_ANCHOR_V1B"
TARGET_CAMPAIGN_ID = "EC5_RAW_P16_ENDPOINT_GALLERY_V1"
PURPOSE = "successor_pre_gallery_factory_otp_white_anchor"
ENVIRONMENT = "ec5_raw_p16_endpoint_gallery_pre_white_anchor_v1b"
PROFILE_ID = "WF23_25"
CONTRACT_ID = "d6c88b8df003f42fe9415682d412e4d5cd1c15ceb2ee7423c927a603d0332c61"
NVS_NAMESPACE = "rp16gpw_v1b"
NVS_KEY = "used_p16pb"
BASE_ROUTE = "/api/ec5/raw-p16-endpoint-gallery-pre-white-anchor-v1b"
DEVICE_API_VERSION = "MF1750_EC5_RAW_P16_ENDPOINT_GALLERY_PRE_WHITE_ANCHOR_DEVICE_V1B"
IDENTITY_REVISION = "raw-p16-endpoint-gallery-pre-white-anchor-v1b"
CLASSIFICATION = (
    "FACTORY_OTP_WHITE_RAW_P16_ENDPOINT_GALLERY_PRE_ANCHOR_"
    "SUCCESSOR_V1B_ONE_ACTION_NO_RUNTIME_PAYLOAD"
)
DESCRIPTOR_ID = "ba9442de357eb7c14da7ded2e171f2ceacca0b2fdd00575500a78ebeadb28dd3"
ACTION_ID = "e66d01310335accc78c0ce00d05bfe0bb2e1842b5826ab221d10207c38de740e"
ACTION_ROLE = "FACTORY_OTP_WHITE_PRE_GALLERY_ANCHOR_SUCCESSOR_V1B"
DESCRIPTOR_ROLE = "OTP_WHITE_RAW_P16_ENDPOINT_GALLERY_PRE_ANCHOR_SUCCESSOR_V1B"
FRAME_SHA256 = "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
DTM_SHA256 = "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158"
FRAME_FNV1A = 0x13340DC5
DTM_FNV1A = 0xB7A855C5
DESCRIPTOR_MARKER = (
    "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE="
    + DESCRIPTOR_ROLE
    + "|SHA256="
    + DESCRIPTOR_ID
)
FIRMWARE_BIN = REPO_ROOT / (
    ".pio/build-raw-p16-endpoint-gallery-pre-white-anchor-v1b/"
    "ec5_raw_p16_endpoint_gallery_pre_white_anchor_v1b/firmware.bin"
)
FIRMWARE_ELF = REPO_ROOT / (
    ".pio/build-raw-p16-endpoint-gallery-pre-white-anchor-v1b/"
    "ec5_raw_p16_endpoint_gallery_pre_white_anchor_v1b/firmware.elf"
)
FIRMWARE_BIN_BYTES = 786_704
FIRMWARE_BIN_SHA256 = "54f7e6f588a35730add6a5edd16e7e4b375e273d467d717277ec0a4cde413bc6"
FIRMWARE_ELF_BYTES = 13_214_676
FIRMWARE_ELF_SHA256 = "70101044f9207eb8df43ee8e719158f3d8441be058bf172980681e195fa5d5a7"
ARM_INTENT = "ARM_ONE_FIXED_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION"
EXECUTE_INTENT = "EXECUTE_ONE_FIXED_FACTORY_OTP_WHITE_ONCE"
CLAIM_KIND = "mf1750-raw-p16-endpoint-gallery-pre-white-anchor-v1b-claim"
RESULT_KIND = "mf1750-raw-p16-endpoint-gallery-pre-white-anchor-v1b-result"


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


def contract() -> dict[str, Any]:
    return {
        "schema": "mf1750-raw-p16-endpoint-gallery-pre-white-anchor-contract-v1b",
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "target_campaign_id": TARGET_CAMPAIGN_ID,
        "purpose": PURPOSE,
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
        "proxy_use": False,
        "redirect_follow": False,
        "artifact_validation_before_claim": True,
    }


def action_basis() -> dict[str, Any]:
    return {
        "schema": "mf1750-raw-p16-endpoint-gallery-pre-white-anchor-action-v1b",
        "campaign_id": CAMPAIGN_ID,
        "purpose": PURPOSE,
        "ordinal": 1,
        "role": ACTION_ROLE,
        "frame_sha256": FRAME_SHA256,
        "cs1_dtm_sha256": DTM_SHA256,
        "cs2_dtm_sha256": DTM_SHA256,
    }


def descriptor_basis() -> dict[str, Any]:
    return {
        "schema": "mf1750-ec5-transaction-descriptor-binding-v1",
        "profile_id": PROFILE_ID,
        "role": DESCRIPTOR_ROLE,
        "campaign_id": CAMPAIGN_ID,
        "contract_id": CONTRACT_ID,
        "action_id": ACTION_ID,
    }


def _canonical_sha256(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def build_report(*, verify_artifacts: bool = True) -> dict[str, Any]:
    frozen_contract = contract()
    if _canonical_sha256(frozen_contract) != CONTRACT_ID:
        raise ValueError("RAW-P16 successor pre-white contract identity differs")
    if _canonical_sha256(action_basis()) != ACTION_ID:
        raise ValueError("RAW-P16 successor pre-white action identity differs")
    if _canonical_sha256(descriptor_basis()) != DESCRIPTOR_ID:
        raise ValueError("RAW-P16 successor pre-white descriptor identity differs")
    status = artifact_binding_status()
    if verify_artifacts and any(
        item["verified"] is not True for item in status.values()
    ):
        raise ValueError("RAW-P16 successor pre-white artifact binding differs")
    action = {
        "ordinal": 1,
        "role": ACTION_ROLE,
        "descriptor_id": DESCRIPTOR_ID,
        "action_id": ACTION_ID,
        "purpose": PURPOSE,
        "frame_sha256": FRAME_SHA256,
        "cs1_dtm_sha256": DTM_SHA256,
        "cs2_dtm_sha256": DTM_SHA256,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-raw-p16-endpoint-gallery-pre-white-anchor-v1b-pack",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "contract_id": CONTRACT_ID,
        "contract": frozen_contract,
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
