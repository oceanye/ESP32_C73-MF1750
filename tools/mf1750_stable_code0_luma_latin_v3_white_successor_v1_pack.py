#!/usr/bin/env python3
"""Independent factory-OTP white successor for stable-code0 luma Latin V3."""

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
    mf1750_stable_code0_luma_latin_v3_pack as source_pack,
)


BUILD_TAG = (
    "MF1750_EC5_STABLE_CODE0_LUMA_LATIN_V3_"
    "FACTORY_OTP_WHITE_SUCCESSOR_V1_2026-09-01"
)
TEST_ID = (
    "EC5-STABLE-CODE0-LUMA-LATIN-V3-"
    "FACTORY-OTP-WHITE-SUCCESSOR-V1"
)
CAMPAIGN_ID = (
    "EC5_STABLE_CODE0_LUMA_LATIN_V3_"
    "FACTORY_OTP_WHITE_SUCCESSOR_V1"
)
SOURCE_CAMPAIGN_ID = source_pack.CAMPAIGN_ID
SOURCE_MAIN_CONTRACT_ID = source_pack.build_report()["contract_id"]
SOURCE_ARTIFACTS = deepcopy(source_pack.ARTIFACTS[source_pack.VARIANT_KEY])
PROFILE_ID = "WF23_25"
NVS_NAMESPACE = "scl3w_v1"
NVS_KEY = "used_scl3w1"
FRAME_SHA256 = "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
DTM_SHA256 = "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158"
FRAME_FNV1A = 0x13340DC5
DTM_FNV1A = 0xB7A855C5
DEVICE_API_VERSION = (
    "MF1750_EC5_STABLE_CODE0_LUMA_LATIN_V3_"
    "WHITE_SUCCESSOR_DEVICE_V1"
)
IDENTITY_REVISION = "stable-code0-luma-latin-v3-white-successor-v1"
CLASSIFICATION = (
    "FACTORY_OTP_WHITE_AFTER_STABLE_CODE0_LUMA_LATIN_V3_"
    "ONE_ACTION_NO_RUNTIME_PAYLOAD"
)
BASE_ROUTE = "/api/ec5/stable-code0-luma-latin-v3/white-successor-v1"
ARM_INTENT = (
    "ARM_ONE_FIXED_STABLE_CODE0_LUMA_LATIN_V3_"
    "FACTORY_OTP_WHITE_SUCCESSOR_NOT_HARDWARE_AUTHORIZATION"
)
EXECUTE_INTENT = (
    "EXECUTE_ONE_FIXED_STABLE_CODE0_LUMA_LATIN_V3_"
    "FACTORY_OTP_WHITE_SUCCESSOR_ONCE"
)
CLAIM_KIND = "mf1750-stable-code0-luma-latin-v3-white-successor-v1-claim"
RESULT_KIND = "mf1750-stable-code0-luma-latin-v3-white-successor-v1-result"

BUILD_ROOT = "b-stable-c0-luma-lat-v3-white-v1"
ENVIRONMENT = "ec5_stable_c0_luma_lat_v3_white_v1"
FIRMWARE_BIN = REPO_ROOT / ".pio" / BUILD_ROOT / ENVIRONMENT / "firmware.bin"
FIRMWARE_ELF = REPO_ROOT / ".pio" / BUILD_ROOT / ENVIRONMENT / "firmware.elf"
ZERO_SHA256 = "0" * 64
FIRMWARE_BIN_BYTES = 787_248
FIRMWARE_BIN_SHA256 = "804aadd5a9b82a02a01bc0431750790666d2ba56352d43b3add7f89245dff907"
FIRMWARE_ELF_BYTES = 13_214_376
FIRMWARE_ELF_SHA256 = "2c70314c8b54f012845370bddc56e5bcf8ef1f808a6854776f3105868108630a"


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
        "ROLE=OTP_WHITE_AFTER_STABLE_CODE0_LATIN_V3_L3_OR_L4_COMPLETE|"
        f"SHA256={report['descriptor_id']}"
    )


def validate_compiled_identity_source() -> dict[str, Any]:
    report = build_report(verify_artifacts=False)
    path = REPO_ROOT / "src/ec5_stable_code0_luma_latin_v3_white_successor_v1_identity.inc"
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
        "kAcceptedSourceActionsSha256": report["contract"][
            "accepted_source_complete_actions_sha256"
        ],
        "kSourceFirmwareBinSha256": str(SOURCE_ARTIFACTS["bin_sha256"]),
        "kSourceFirmwareElfSha256": str(SOURCE_ARTIFACTS["elf_sha256"]),
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
    accepted_sha256 = _sha(_canonical(accepted))
    descriptor_payload = {
        "schema": "mf1750-stable-code0-luma-latin-v3-white-successor-descriptor-v1",
        "profile_id": PROFILE_ID,
        "role": "FACTORY_OTP_WHITE_RECOVERY",
        "source_campaign_id": SOURCE_CAMPAIGN_ID,
        "source_main_contract_id": SOURCE_MAIN_CONTRACT_ID,
        "source_main_artifacts": deepcopy(SOURCE_ARTIFACTS),
        "accepted_source_complete_actions": accepted,
        "accepted_source_complete_actions_sha256": accepted_sha256,
        "source_terminal_evidence_required_before_any_live_request": True,
        "main_campaign_resume_after_containment": False,
        "frame_sha256": FRAME_SHA256,
        "cs1_dtm_sha256": DTM_SHA256,
        "cs2_dtm_sha256": DTM_SHA256,
    }
    descriptor_id = _sha(_canonical(descriptor_payload))
    action_id = _sha(
        (
            "MF1750_STABLE_CODE0_LUMA_LATIN_V3_WHITE_SUCCESSOR_V1|"
            f"{descriptor_id}"
        ).encode("ascii")
    )
    contract = {
        "schema": "mf1750-stable-code0-luma-latin-v3-white-successor-contract-v1",
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "source_campaign_id": SOURCE_CAMPAIGN_ID,
        "source_main_contract_id": SOURCE_MAIN_CONTRACT_ID,
        "source_main_artifacts": deepcopy(SOURCE_ARTIFACTS),
        "accepted_source_complete_actions": accepted,
        "accepted_source_complete_actions_sha256": accepted_sha256,
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
        "kind": "mf1750-stable-code0-luma-latin-v3-white-successor-offline-identity-v1",
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
            "source_main_artifacts": deepcopy(SOURCE_ARTIFACTS),
            "accepted_source_complete_actions": deepcopy(accepted),
            "accepted_source_complete_actions_sha256": accepted_sha256,
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
    source_validation = source_pack.dry_validate(
        verify_source=True,
        verify_artifacts=True,
    )
    if (
        source_validation.get("result") != "PASS"
        or source_validation.get("artifacts_sealed") is not True
        or source_validation.get("artifacts_verified") is not True
    ):
        raise RuntimeError("white successor source campaign is not sealed")
    source = validate_compiled_identity_source()
    binary = validate_compiled_identity_binary() if verify_artifacts else None
    return {
        "schema_version": 1,
        "kind": "mf1750-stable-code0-luma-latin-v3-white-successor-v1-dry-validation",
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
DESCRIPTOR_MARKER = compiled_identity_marker()


if __name__ == "__main__":
    print(json.dumps(build_report(), indent=2, sort_keys=True))
