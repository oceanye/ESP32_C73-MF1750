#!/usr/bin/env python3
"""Factory-OTP white successor for reconstruction R3 COMPLETE only."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_position_balanced_gray_fresh_reconstruction_v1_pack as source_pack,
)

BUILD_TAG = (
    "MF1750_EC5_POSITION_BALANCED_GRAY_FRESH_RECONSTRUCTION_V1_"
    "FACTORY_OTP_WHITE_SUCCESSOR_V1_2026-09-01"
)
TEST_ID = (
    "EC5-POSITION-BALANCED-GRAY-FRESH-RECONSTRUCTION-V1-"
    "FACTORY-OTP-WHITE-SUCCESSOR-V1"
)
CAMPAIGN_ID = (
    "EC5_POSITION_BALANCED_GRAY_FRESH_RECONSTRUCTION_V1_"
    "FACTORY_OTP_WHITE_SUCCESSOR_V1"
)
SOURCE_CAMPAIGN_ID = source_pack.CAMPAIGN_ID
SOURCE_ORDINAL = 3
PROFILE_ID = "WF23_25"
NVS_NAMESPACE = "pbgfrw1"
NVS_KEY = "used_pbgfrw1"
FRAME_SHA256 = "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
DTM_SHA256 = "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158"
FRAME_FNV1A = 0x13340DC5
DTM_FNV1A = 0xB7A855C5
DEVICE_API_VERSION = (
    "MF1750_EC5_POSITION_BALANCED_GRAY_FRESH_RECONSTRUCTION_V1_"
    "WHITE_SUCCESSOR_DEVICE_V1"
)
IDENTITY_REVISION = (
    "position-balanced-gray-fresh-reconstruction-v1-white-successor-v1"
)
CLASSIFICATION = (
    "FACTORY_OTP_WHITE_AFTER_FRESH_RECONSTRUCTION_R3_COMPLETE_"
    "ONE_ACTION_NO_RUNTIME_PAYLOAD"
)
BASE_ROUTE = (
    "/api/ec5/position-balanced-gray-fresh-reconstruction-v1/white-successor-v1"
)
ARM_INTENT = (
    "ARM_ONE_FIXED_POSITION_BALANCED_GRAY_FRESH_RECONSTRUCTION_V1_"
    "FACTORY_OTP_WHITE_SUCCESSOR_NOT_HARDWARE_AUTHORIZATION"
)
EXECUTE_INTENT = (
    "EXECUTE_ONE_FIXED_POSITION_BALANCED_GRAY_FRESH_RECONSTRUCTION_V1_"
    "FACTORY_OTP_WHITE_SUCCESSOR_ONCE"
)
CLAIM_KIND = (
    "mf1750-position-balanced-gray-fresh-reconstruction-v1-"
    "white-successor-v1-claim"
)
RESULT_KIND = (
    "mf1750-position-balanced-gray-fresh-reconstruction-v1-"
    "white-successor-v1-result"
)
BUILD_ROOT = "b-position-balanced-gray-fresh-reconstruction-v1-white-v1"
ENVIRONMENT = "ec5_position_balanced_gray_fresh_reconstruction_v1_white_v1"
FIRMWARE_BIN = REPO_ROOT / ".pio" / BUILD_ROOT / ENVIRONMENT / "firmware.bin"
FIRMWARE_ELF = REPO_ROOT / ".pio" / BUILD_ROOT / ENVIRONMENT / "firmware.elf"
ZERO_SHA256 = "0" * 64
FIRMWARE_BIN_BYTES = 787616
FIRMWARE_BIN_SHA256 = "e78cd7b18d8c020d09f1fc554cd4f0f2063cfcd8c3b590391ed637b0260bba45"
FIRMWARE_ELF_BYTES = 13214872
FIRMWARE_ELF_SHA256 = "24d8af57ed719de1cfffd6adcc9a355c74473179f653aadfaf41448ce102f8bb"


class ReconstructionWhiteSuccessorPackError(RuntimeError):
    """Raised before a non-R3 or unsealed white successor can be used."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def artifacts_are_sealed() -> bool:
    return (
        FIRMWARE_BIN_BYTES > 0
        and FIRMWARE_ELF_BYTES > 0
        and FIRMWARE_BIN_SHA256 != ZERO_SHA256
        and FIRMWARE_ELF_SHA256 != ZERO_SHA256
    )


def artifact_paths() -> tuple[Path, Path]:
    return FIRMWARE_BIN, FIRMWARE_ELF


def _report(source: Mapping[str, Any], *, source_sealed: bool) -> dict[str, Any]:
    item = source["actions"][SOURCE_ORDINAL - 1]
    accepted = [
        {
            "ordinal": item["ordinal"],
            "descriptor_id": item["descriptor_id"],
            "action_id": item["action_id"],
            "role": item["role"],
        }
    ]
    if accepted != [
        {
            "ordinal": 3,
            "descriptor_id": item["descriptor_id"],
            "action_id": item["action_id"],
            "role": "G3_ACTIVE_C3_C7_TARGET",
        }
    ]:
        raise ReconstructionWhiteSuccessorPackError(
            "white successor accepts reconstruction R3 COMPLETE only"
        )
    source_artifacts = deepcopy(source_pack.ARTIFACTS)
    accepted_sha256 = _sha(_canonical(accepted))
    descriptor_payload = {
        "schema": (
            "mf1750-position-balanced-gray-fresh-reconstruction-v1-"
            "white-successor-descriptor-v1"
        ),
        "profile_id": PROFILE_ID,
        "role": "FACTORY_OTP_WHITE_RECOVERY_AFTER_RECONSTRUCTION_R3_COMPLETE",
        "source_campaign_id": SOURCE_CAMPAIGN_ID,
        "source_main_contract_id": source["contract_id"],
        "source_main_artifacts": source_artifacts,
        "accepted_source_complete_actions": accepted,
        "accepted_source_complete_actions_sha256": accepted_sha256,
        "source_terminal_evidence_required_before_any_live_request": True,
        "source_fault_or_early_stop_accepted": False,
        "main_campaign_resume_after_containment": False,
        "frame_sha256": FRAME_SHA256,
        "cs1_dtm_sha256": DTM_SHA256,
        "cs2_dtm_sha256": DTM_SHA256,
    }
    descriptor_id = _sha(_canonical(descriptor_payload))
    action_id = _sha(
        (
            "MF1750_POSITION_BALANCED_GRAY_FRESH_RECONSTRUCTION_V1_"
            f"WHITE_SUCCESSOR_V1|{descriptor_id}"
        ).encode("ascii")
    )
    contract = {
        "schema": (
            "mf1750-position-balanced-gray-fresh-reconstruction-v1-"
            "white-successor-contract-v1"
        ),
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "source_campaign_id": SOURCE_CAMPAIGN_ID,
        "source_main_contract_id": source["contract_id"],
        "source_main_artifacts": source_artifacts,
        "source_main_sealed": source_sealed,
        "accepted_source_complete_actions": accepted,
        "accepted_source_complete_actions_sha256": accepted_sha256,
        "accepted_source_ordinals": [3],
        "source_terminal_evidence_required_before_any_live_request": True,
        "source_fault_not_accepted": True,
        "source_early_stop_not_accepted": True,
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
        "boot_action": False,
        "retry": False,
        "fallback": False,
        "automatic_recovery": False,
        "autochain": False,
        "main_campaign_resume_after_containment": False,
        "qualified_colors": 0,
        "qualified_gray_levels": 0,
        "qualified_brightness_levels": 0,
        "true_neutral_gray_claimed": False,
    }
    return {
        "schema_version": 1,
        "kind": (
            "mf1750-position-balanced-gray-fresh-reconstruction-v1-"
            "white-successor-offline-identity-v1"
        ),
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
            "expected_contract_id": source["contract_id"],
            "source_main_artifacts": source_artifacts,
            "accepted_source_complete_actions": accepted,
            "accepted_source_complete_actions_sha256": accepted_sha256,
            "main_campaign_resume_after_containment": False,
        },
    }


def template_report() -> dict[str, Any]:
    source = source_pack.build_report()
    source_sealed = source_pack.artifacts_are_sealed()
    report = _report(source, source_sealed=source_sealed)
    report["identity_status"] = (
        "SEALED_OFFLINE_RECONSTRUCTION_R3_LIVE_GATE_PENDING"
        if source_sealed and artifacts_are_sealed()
        else "PROVISIONAL_UNSEALED_DO_NOT_COMPILE_OR_EXECUTE"
    )
    return report


def build_report(*, verify_artifacts: bool = False) -> dict[str, Any]:
    source = source_pack.build_report()
    if not source_pack.artifacts_are_sealed():
        raise ReconstructionWhiteSuccessorPackError(
            "source reconstruction firmware artifacts are unsealed"
        )
    report = _report(source, source_sealed=True)
    if verify_artifacts:
        if not artifacts_are_sealed():
            raise ReconstructionWhiteSuccessorPackError(
                "white successor artifacts are unsealed"
            )
        for label, path, size, digest in (
            ("bin", FIRMWARE_BIN, FIRMWARE_BIN_BYTES, FIRMWARE_BIN_SHA256),
            ("elf", FIRMWARE_ELF, FIRMWARE_ELF_BYTES, FIRMWARE_ELF_SHA256),
        ):
            if not path.is_file() or path.is_symlink():
                raise ReconstructionWhiteSuccessorPackError(
                    f"white successor {label} missing"
                )
            payload = path.read_bytes()
            if len(payload) != size or _sha(payload) != digest:
                raise ReconstructionWhiteSuccessorPackError(
                    f"white successor {label} differs"
                )
    return report


def dry_validate(
    *, require_sealed: bool = False, verify_artifacts: bool = False
) -> dict[str, Any]:
    offline_sealed = source_pack.artifacts_are_sealed() and artifacts_are_sealed()
    report = (
        build_report(verify_artifacts=verify_artifacts)
        if require_sealed or offline_sealed
        else template_report()
    )
    contract = report["contract"]
    if (
        contract["accepted_source_ordinals"] != [3]
        or contract["source_fault_not_accepted"] is not True
        or contract["source_early_stop_not_accepted"] is not True
        or contract["autochain"] is not False
        or contract["qualified_gray_levels"] != 0
    ):
        raise ReconstructionWhiteSuccessorPackError(
            "white successor containment contract differs"
        )
    return {
        "schema_version": 1,
        "kind": (
            "mf1750-position-balanced-gray-fresh-reconstruction-v1-"
            "white-successor-dry-validation"
        ),
        "result": (
            "PASS"
            if require_sealed
            else (
                "OFFLINE_IDENTITY_PASS_RECONSTRUCTION_R3_LIVE_GATE_PENDING"
                if offline_sealed
                else "BLOCKED_WAITING_FOR_RECONSTRUCTION_SEAL_AND_R3_COMPLETE"
            )
        ),
        "offline_only": True,
        "network_requests": 0,
        "hardware_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "contract_id": report["contract_id"],
        "descriptor_id": report["descriptor_id"],
        "action_id": report["action_id"],
        "accepted_source_ordinals": [3],
        "fault_or_early_stop_accepted": False,
        "source_main_sealed": contract["source_main_sealed"],
        "artifacts_verified": verify_artifacts,
        "qualified_colors": 0,
        "qualified_gray_levels": 0,
        "qualified_brightness_levels": 0,
    }


if __name__ == "__main__":
    print(json.dumps(dry_validate(), indent=2, sort_keys=True))
