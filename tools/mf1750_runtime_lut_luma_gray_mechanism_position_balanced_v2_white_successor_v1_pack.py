#!/usr/bin/env python3
"""Independent factory-OTP white successor for LUMA/GRAY mechanism V2."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v2_pack as source_pack,
)


BUILD_TAG = (
    "MF1750_EC5_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V2_"
    "FACTORY_OTP_WHITE_SUCCESSOR_V1_2026-09-01"
)
TEST_ID = (
    "EC5-LUMA-GRAY-MECHANISM-POSITION-BALANCED-V2-"
    "FACTORY-OTP-WHITE-SUCCESSOR-V1"
)
CAMPAIGN_ID = (
    "EC5_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V2_"
    "FACTORY_OTP_WHITE_SUCCESSOR_V1"
)
SOURCE_CAMPAIGN_ID = source_pack.CAMPAIGN_ID
SOURCE_MAIN_CONTRACT_ID = source_pack.build_report()["contract_id"]
PROFILE_ID = "WF23_25"
NVS_NAMESPACE = "lgmpb2w_v1"
NVS_KEY = "used_lgmpb2w1"
FRAME_SHA256 = "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
DTM_SHA256 = "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158"
FRAME_FNV1A = 0x13340DC5
DTM_FNV1A = 0xB7A855C5
DEVICE_API_VERSION = (
    "MF1750_EC5_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V2_"
    "WHITE_SUCCESSOR_DEVICE_V1"
)
IDENTITY_REVISION = "luma-gray-mechanism-position-balanced-v2-white-successor-v1"
CLASSIFICATION = (
    "FACTORY_OTP_WHITE_AFTER_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V2_"
    "ONE_ACTION_NO_RUNTIME_PAYLOAD"
)
BASE_ROUTE = "/api/ec5/luma-gray-mechanism-position-balanced-v2/white-successor-v1"
ARM_INTENT = (
    "ARM_ONE_FIXED_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V2_"
    "FACTORY_OTP_WHITE_SUCCESSOR_NOT_HARDWARE_AUTHORIZATION"
)
EXECUTE_INTENT = (
    "EXECUTE_ONE_FIXED_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V2_"
    "FACTORY_OTP_WHITE_SUCCESSOR_ONCE"
)
CLAIM_KIND = "mf1750-luma-gray-mechanism-position-balanced-v2-white-successor-v1-claim"
RESULT_KIND = "mf1750-luma-gray-mechanism-position-balanced-v2-white-successor-v1-result"

BUILD_ROOT = "b-luma-gray-mpb-v2-white-v1"
ENVIRONMENT = "ec5_luma_gray_mpb_v2_white_v1"
FIRMWARE_BIN = REPO_ROOT / ".pio" / BUILD_ROOT / ENVIRONMENT / "firmware.bin"
FIRMWARE_ELF = REPO_ROOT / ".pio" / BUILD_ROOT / ENVIRONMENT / "firmware.elf"
ZERO_SHA256 = "0" * 64
FIRMWARE_BIN_BYTES = 787_440
FIRMWARE_BIN_SHA256 = "70fc1512945549d3c1321398b846a7d15389bb5dc4661f0a65965b113edca1d7"
FIRMWARE_ELF_BYTES = 13_214_356
FIRMWARE_ELF_SHA256 = "6b750b7ebaa3c19a31912c56576f09be4903101f8f60047f42f8606fa1d8570e"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def artifacts_are_sealed() -> bool:
    return (
        FIRMWARE_BIN_BYTES > 0
        and FIRMWARE_ELF_BYTES > 0
        and FIRMWARE_BIN_SHA256 != ZERO_SHA256
        and FIRMWARE_ELF_SHA256 != ZERO_SHA256
    )


def artifact_paths() -> tuple[Path, Path]:
    return FIRMWARE_BIN, FIRMWARE_ELF


def _compiled_string(source: str, name: str) -> str:
    match = re.search(
        rf"static\s+constexpr\s+(?:const\s+)?char\s*\*?\s*{re.escape(name)}(?:\[\])?\s*=(?P<body>.*?);",
        source,
        re.DOTALL,
    )
    if match is None:
        raise RuntimeError(f"white successor compiled identity {name} missing")
    values = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', match.group("body"))
    if not values:
        raise RuntimeError(f"white successor compiled identity {name} empty")
    return "".join(bytes(value, "utf-8").decode("unicode_escape") for value in values)


def compiled_identity_marker() -> str:
    report = build_report(verify_artifacts=False)
    return (
        "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
        "ROLE=OTP_WHITE_AFTER_LGMPB2_G3_OR_G4_COMPLETE|"
        f"SHA256={report['descriptor_id']}"
    )


def validate_compiled_identity_source() -> dict[str, Any]:
    report = build_report(verify_artifacts=False)
    path = REPO_ROOT / "src/ec5_runtime_lut_luma_gray_mechanism_position_balanced_v2_white_successor_v1_identity.inc"
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("white successor identity source missing or unsafe")
    source = path.read_text(encoding="utf-8")
    expected = {
        "kCampaignId": CAMPAIGN_ID,
        "kSourceCampaignId": SOURCE_CAMPAIGN_ID,
        "kSourceMainContractId": SOURCE_MAIN_CONTRACT_ID,
        "kBuildTag": BUILD_TAG,
        "kContractId": report["contract_id"],
        "kNvsNamespace": NVS_NAMESPACE,
        "kDescriptorId": report["descriptor_id"],
        "kActionId": report["action_id"],
    }
    if any(_compiled_string(source, name) != value for name, value in expected.items()):
        raise RuntimeError("white successor compiled identity differs")
    marker = compiled_identity_marker()
    if source.count(marker) != 1:
        raise RuntimeError("white successor compiled marker source differs")
    return {"verified": True, "path": path.relative_to(REPO_ROOT).as_posix(), "marker": marker}


def validate_compiled_identity_binary() -> dict[str, Any]:
    if not artifacts_are_sealed():
        raise RuntimeError("white successor artifacts are not sealed")
    marker = compiled_identity_marker().encode("ascii")
    counts = {
        "bin": FIRMWARE_BIN.read_bytes().count(marker),
        "elf": FIRMWARE_ELF.read_bytes().count(marker),
    }
    if counts != {"bin": 1, "elf": 1}:
        raise RuntimeError(f"white successor compiled marker count differs: {counts}")
    return {"verified": True, "marker_sha256": _sha(marker), "counts": counts}


def build_report(*, verify_artifacts: bool = False) -> dict[str, Any]:
    source = source_pack.build_report()
    accepted = [
        {
            "ordinal": item["ordinal"],
            "descriptor_id": item["descriptor_id"],
            "action_id": item["action_id"],
            "role": item["role"],
        }
        for item in source["actions"]
        if item["ordinal"] in (3, 4)
    ]
    descriptor_payload = {
        "schema": "mf1750-luma-gray-mechanism-position-balanced-v2-white-successor-descriptor-v1",
        "profile_id": PROFILE_ID,
        "role": "FACTORY_OTP_WHITE_RECOVERY",
        "source_campaign_id": SOURCE_CAMPAIGN_ID,
        "source_main_contract_id": SOURCE_MAIN_CONTRACT_ID,
        "accepted_source_complete_actions": accepted,
        "source_terminal_evidence_required_before_any_live_request": True,
        "main_campaign_resume_after_containment": False,
        "frame_sha256": FRAME_SHA256,
        "cs1_dtm_sha256": DTM_SHA256,
        "cs2_dtm_sha256": DTM_SHA256,
    }
    descriptor_id = _sha(_canonical(descriptor_payload))
    action_id = _sha(
        (
            "MF1750_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V2_WHITE_SUCCESSOR_V1|"
            f"{descriptor_id}"
        ).encode("ascii")
    )
    contract = {
        "schema": "mf1750-luma-gray-mechanism-position-balanced-v2-white-successor-contract-v1",
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "source_campaign_id": SOURCE_CAMPAIGN_ID,
        "source_main_contract_id": SOURCE_MAIN_CONTRACT_ID,
        "accepted_source_complete_actions": accepted,
        "accepted_source_ordinals": [3, 4],
        "source_terminal_evidence_required_before_any_live_request": True,
        "source_fault_not_accepted": True,
        "profile_id": PROFILE_ID,
        "base_route": BASE_ROUTE,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "action_id": action_id,
        "descriptor_id": descriptor_id,
        "factory_otp": True,
        "runtime_lut_write": False,
        "custom_waveform_write": False,
        "one_visible_refresh": True,
        "startup_refresh": False,
        "retry": False,
        "fallback": False,
        "automatic_recovery": False,
        "autochain": False,
        "main_campaign_resume_after_containment": False,
        "qualified_gray_levels": 0,
        "qualified_brightness_levels": 0,
        "true_neutral_gray_claimed": False,
    }
    report = {
        "schema_version": 1,
        "kind": "mf1750-luma-gray-mechanism-position-balanced-v2-white-successor-offline-identity-v1",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "camera_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
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
        "source_main_binding": {
            "expected_contract_id": SOURCE_MAIN_CONTRACT_ID,
            "observed_contract_id": source["contract_id"],
            "accepted_source_complete_actions": deepcopy(accepted),
            "main_campaign_resume_after_containment": False,
        },
    }
    if verify_artifacts:
        if not artifacts_are_sealed():
            raise RuntimeError("white successor artifacts are not sealed")
        for path, size, digest in (
            (FIRMWARE_BIN, FIRMWARE_BIN_BYTES, FIRMWARE_BIN_SHA256),
            (FIRMWARE_ELF, FIRMWARE_ELF_BYTES, FIRMWARE_ELF_SHA256),
        ):
            payload = path.read_bytes()
            if len(payload) != size or _sha(payload) != digest:
                raise RuntimeError(f"white successor artifact differs: {path}")
    return report


def dry_validate(*, verify_artifacts: bool = False) -> dict[str, Any]:
    report = build_report(verify_artifacts=verify_artifacts)
    source = validate_compiled_identity_source()
    binary = validate_compiled_identity_binary() if verify_artifacts else None
    return {
        "schema_version": 1,
        "kind": "mf1750-luma-gray-mechanism-position-balanced-v2-white-successor-v1-dry-validation",
        "result": "PASS",
        "offline_only": True,
        "network_requests": 0,
        "hardware_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "contract_id": report["contract_id"],
        "descriptor_id": report["descriptor_id"],
        "action_id": report["action_id"],
        "compiled_identity_source": source,
        "compiled_identity_binary": binary,
        "artifacts_sealed": artifacts_are_sealed(),
    }


_REPORT = build_report()
CONTRACT_ID = _REPORT["contract_id"]
DESCRIPTOR_ID = _REPORT["descriptor_id"]
ACTION_ID = _REPORT["action_id"]


if __name__ == "__main__":
    print(json.dumps(build_report(), indent=2, sort_keys=True))
