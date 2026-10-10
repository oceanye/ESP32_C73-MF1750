#!/usr/bin/env python3
"""Offline pack for the fresh RAW-P16 pre-gallery factory-OTP white anchor."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "MF1750_EC5_RAW_P16_ENDPOINT_GALLERY_PRE_WHITE_ANCHOR_V1_2026-08-28"
TEST_ID = "EC5-RAW-P16-ENDPOINT-GALLERY-PRE-WHITE-ANCHOR-V1"
CAMPAIGN_ID = "EC5_RAW_P16_ENDPOINT_GALLERY_PRE_WHITE_ANCHOR_V1"
TARGET_CAMPAIGN_ID = "EC5_RAW_P16_ENDPOINT_GALLERY_V1"
PURPOSE = "pre_gallery_factory_otp_white_anchor"
ENVIRONMENT = "ec5_raw_p16_endpoint_gallery_pre_white_anchor_v1"
PROFILE_ID = "WF23_25"
CONTRACT_ID = "c8ae63b7ab46fb2a22fc245fd8f4f2b810ea54ecf19cc71758dc3703aca2196c"
NVS_NAMESPACE = "rp16gpw_v1"
NVS_KEY = "used_p16p"
BASE_ROUTE = "/api/ec5/raw-p16-endpoint-gallery-v1/pre-white-anchor"
DEVICE_API_VERSION = "MF1750_EC5_RAW_P16_ENDPOINT_GALLERY_PRE_WHITE_ANCHOR_DEVICE_V1"
IDENTITY_REVISION = "raw-p16-endpoint-gallery-pre-white-anchor-v1"
CLASSIFICATION = (
    "FACTORY_OTP_WHITE_RAW_P16_ENDPOINT_GALLERY_PRE_ANCHOR_"
    "ONE_ACTION_NO_RUNTIME_PAYLOAD"
)
DESCRIPTOR_ID = "2cc71145bcd1d868c6b7d80bc25f7ac031a57dbf3ae4a234cf7e1680135144d3"
ACTION_ID = "3b939eb962e43cc7c232cddb14f3d97d3d48de9c796154ff0a42eed311379a74"
FRAME_SHA256 = "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
DTM_SHA256 = "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158"
FRAME_FNV1A = 0x13340DC5
DTM_FNV1A = 0xB7A855C5
DESCRIPTOR_MARKER = (
    "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
    "ROLE=OTP_WHITE_RAW_P16_ENDPOINT_GALLERY_PRE_ANCHOR|SHA256=" + DESCRIPTOR_ID
)
FIRMWARE_BIN = REPO_ROOT / (
    ".pio/build-raw-p16-endpoint-gallery-pre-white-anchor-v1/"
    "ec5_raw_p16_endpoint_gallery_pre_white_anchor_v1/firmware.bin"
)
FIRMWARE_ELF = REPO_ROOT / (
    ".pio/build-raw-p16-endpoint-gallery-pre-white-anchor-v1/"
    "ec5_raw_p16_endpoint_gallery_pre_white_anchor_v1/firmware.elf"
)
FIRMWARE_BIN_BYTES = 786_592
FIRMWARE_BIN_SHA256 = "29ecaf18c5825d44caffbaa817d55a211441304e47023a814365ac420baa42ad"
FIRMWARE_ELF_BYTES = 13_214_500
FIRMWARE_ELF_SHA256 = "ad94830b13194f32b3cbb179f4306b0631b4e45e6567c0cf77306a5fd838f9ca"
ARM_INTENT = "ARM_ONE_FIXED_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION"
EXECUTE_INTENT = "EXECUTE_ONE_FIXED_FACTORY_OTP_WHITE_ONCE"
CLAIM_KIND = "mf1750-raw-p16-endpoint-gallery-pre-white-anchor-claim"
RESULT_KIND = "mf1750-raw-p16-endpoint-gallery-pre-white-anchor-result"


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
        "schema": "mf1750-raw-p16-endpoint-gallery-pre-white-anchor-contract-v1",
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
    }


def action_basis() -> dict[str, Any]:
    return {
        "schema": "mf1750-raw-p16-endpoint-gallery-pre-white-anchor-action-v1",
        "campaign_id": CAMPAIGN_ID,
        "purpose": PURPOSE,
        "ordinal": 1,
        "role": "FACTORY_OTP_WHITE_PRE_GALLERY_ANCHOR",
        "frame_sha256": FRAME_SHA256,
        "cs1_dtm_sha256": DTM_SHA256,
        "cs2_dtm_sha256": DTM_SHA256,
    }


def descriptor_basis() -> dict[str, Any]:
    return {
        "schema": "mf1750-ec5-transaction-descriptor-binding-v1",
        "profile_id": PROFILE_ID,
        "role": "OTP_WHITE_RAW_P16_ENDPOINT_GALLERY_PRE_ANCHOR",
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
        raise ValueError("RAW-P16 pre-white contract identity differs")
    if _canonical_sha256(action_basis()) != ACTION_ID:
        raise ValueError("RAW-P16 pre-white action identity differs")
    if _canonical_sha256(descriptor_basis()) != DESCRIPTOR_ID:
        raise ValueError("RAW-P16 pre-white descriptor identity differs")
    status = artifact_binding_status()
    if verify_artifacts and any(
        item["verified"] is not True for item in status.values()
    ):
        raise ValueError("RAW-P16 pre-white artifact binding differs")
    action = {
        "ordinal": 1,
        "role": "FACTORY_OTP_WHITE_PRE_GALLERY_ANCHOR",
        "descriptor_id": DESCRIPTOR_ID,
        "action_id": ACTION_ID,
        "purpose": PURPOSE,
        "frame_sha256": FRAME_SHA256,
        "cs1_dtm_sha256": DTM_SHA256,
        "cs2_dtm_sha256": DTM_SHA256,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-raw-p16-endpoint-gallery-pre-white-anchor-pack",
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
