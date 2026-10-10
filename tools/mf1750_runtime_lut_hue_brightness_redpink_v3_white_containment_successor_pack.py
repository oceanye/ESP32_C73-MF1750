#!/usr/bin/env python3
"""Offline identity pack for the isolated Red/pink V3 OTP-white successor."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_runtime_lut_hue_brightness_redpink_v2_pack as source_pack,
)


BUILD_TAG = (
    "MF1750_EC5_TARGET_HUE_REDPINK_BRIGHTNESS_V3_WHITE_CONTAINMENT_"
    "SUCCESSOR_SINGLE_APP_BOOT_V1_2026-08-28"
)
TEST_ID = "EC5-TARGET-HUE-REDPINK-BRIGHTNESS-V3-WHITE-CONTAINMENT-SUCCESSOR"
CAMPAIGN_ID = "EC5_TARGET_HUE_REDPINK_BRIGHTNESS_V3_WHITE_CONTAINMENT_SUCCESSOR"
SOURCE_CAMPAIGN_ID = "EC5_TARGET_HUE_REDPINK_BRIGHTNESS_8X8_ABA_V2"
SOURCE_MAIN_CONTRACT_ID = (
    "1308b6eb60ea786a2e1db2a2c984809fd446e9b1e32b1d14a54bf0356128ff8c"
)
ENVIRONMENT = "ec5_runtime_lut_hue_brightness_redpink_v3_white_containment_successor"
PROFILE_ID = "WF23_25"
NVS_NAMESPACE = "rlhrpcw_v3s"
NVS_KEY = "used_rp3s"
BASE_ROUTE = "/api/ec5/target-hue-redpink-brightness-v3/white-containment-successor"
DEVICE_API_VERSION = (
    "MF1750_EC5_TARGET_HUE_REDPINK_BRIGHTNESS_V3_WHITE_CONTAINMENT_SUCCESSOR_DEVICE_V1"
)
IDENTITY_REVISION = "target-hue-redpink-brightness-v3-white-containment-successor-v1"
CLASSIFICATION = (
    "FACTORY_OTP_WHITE_REDPINK_BRIGHTNESS_V3_SUCCESSOR_ONE_ACTION_NO_RUNTIME_PAYLOAD"
)

PREDECESSOR_V2_CAMPAIGN_ID = "EC5_TARGET_HUE_REDPINK_BRIGHTNESS_V2_WHITE_CONTAINMENT"
PREDECESSOR_V2_CONTRACT_ID = (
    "73f6bb1db45aa5ec570e854067cb2ad29d6994206a8816e1eadfa7fc763c2c92"
)
PREDECESSOR_V2_ACTION_ID = (
    "4c0c5e414242832925d864cd89b64f5592b516c70bb6669683645022b265f87b"
)
PREDECESSOR_V2_FIRMWARE_BIN_SHA256 = (
    "161e7c60f03d85aa4a50d4a9f03de927acdb99f6507c696f57500d95d7aee4ce"
)
PREDECESSOR_V2_FIRMWARE_ELF_SHA256 = (
    "3d759a03e42b9f6c4c2d18add6f1683432713353cb434cc3e04d506c5ccdea03"
)
PREDECESSOR_EXPECTED_CLASSIFICATION = (
    "FACTORY_OTP_WHITE_BRIGHTNESS_CAMPAIGN_CONTAINMENT_ONE_ACTION_NO_RUNTIME_PAYLOAD"
)
PREDECESSOR_OBSERVED_CLASSIFICATION = (
    "FACTORY_OTP_WHITE_REDPINK_BRIGHTNESS_CONTAINMENT_ONE_ACTION_NO_RUNTIME_PAYLOAD"
)
PREDECESSOR_FLASH_FILE = REPO_ROOT / Path(
    ".test-output/hardware/"
    "MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_WHITE_CONTAINMENT_20260827_V2/"
    "app-only-single-boot-flash.json"
)
PREDECESSOR_FLASH_BYTES = 7_038
PREDECESSOR_FLASH_FILE_SHA256 = (
    "bfbd6799ca0bc16d81f67ee55addc137244452fb2d732364465b80e804572023"
)
PREDECESSOR_FLASH_INTEGRITY_SHA256 = (
    "9d16ea4d96bc122aaa333b58b95ab5b5f88a87dcbcebb718ed8c716357de15eb"
)
PREDECESSOR_DIAGNOSTIC_FILE = REPO_ROOT / Path(
    ".test-output/hardware/"
    "MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_WHITE_CONTAINMENT_20260827_V2/"
    "j2-off-diagnostic.json"
)
PREDECESSOR_DIAGNOSTIC_BYTES = 16_291
PREDECESSOR_DIAGNOSTIC_FILE_SHA256 = (
    "67f906ce5821b3227ee5b03f74cb4ea81e96138e7eb3a333654972b768c916a7"
)
PREDECESSOR_DIAGNOSTIC_INTEGRITY_SHA256 = (
    "0cd81471308b9ca6dd543d451394d453622cfbe582343eef271f5b0b14ac0406"
)
PREDECESSOR_ACTION_OUTPUT = REPO_ROOT / Path(
    ".test-output/hardware/"
    "MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_WHITE_CONTAINMENT_20260827_V2/"
    "action-01-factory-otp-white.json"
)
PREDECESSOR_CLAIM = REPO_ROOT / Path(
    ".test-output/hardware/"
    ".mf1750_target_hue_redpink_brightness_white_containment_v2_claims/"
    f"{PREDECESSOR_V2_ACTION_ID}.json"
)

FRAME_SHA256 = "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
DTM_SHA256 = "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158"
FRAME_FNV1A = 0x13340DC5
DTM_FNV1A = 0xB7A855C5

# Filled only after the canonical payloads are finalized below.
DESCRIPTOR_ID = "8e91f5692722cc75e7ceaf32f89a330083ec39116d0e690f09387f389bd4694d"
ACTION_ID = "76517f9d6ba090cef2f4f3fd32bcda6a5466b41aeeef5ce31a5520ac1dbbceed"
CONTRACT_ID = "1618436e99a0ee1afd9ce16e534f3cf7e34151ddb5f0d6a757aee860aff1a227"

CLAIM_KIND = "mf1750-target-hue-redpink-brightness-v3-white-containment-successor-claim"
RESULT_KIND = (
    "mf1750-target-hue-redpink-brightness-v3-white-containment-successor-result"
)
DESCRIPTOR_MARKER = (
    "MF1750_EC5_TX_DESCRIPTOR_V3|PROFILE=WF23_25|"
    "ROLE=BRIGHTNESS_REDPINK_OTP_WHITE_SUCCESSOR|SHA256=" + DESCRIPTOR_ID
)
ARM_INTENT = (
    "ARM_ONE_FIXED_REDPINK_V3_SUCCESSOR_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION"
)
EXECUTE_INTENT = "EXECUTE_ONE_FIXED_REDPINK_V3_SUCCESSOR_FACTORY_OTP_WHITE_ONCE"

FIRMWARE_BIN = REPO_ROOT / Path(
    ".pio/build-rp-v3-white-successor/ec5_rp_v3_white_successor/firmware.bin"
)
FIRMWARE_ELF = REPO_ROOT / Path(
    ".pio/build-rp-v3-white-successor/ec5_rp_v3_white_successor/firmware.elf"
)
FIRMWARE_BIN_BYTES = 789_200
FIRMWARE_BIN_SHA256 = "3721b60c23662fb34fa467fc6873bf858fb579c7c01ab2a486f9456ca1da1cfb"
FIRMWARE_ELF_BYTES = 13_215_844
FIRMWARE_ELF_SHA256 = "2baf26d20280d316063f6bd26bc7f39e7526d47e5af09a46c4f34346464c7797"

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _read_sealed_json(path: Path, *, label: str) -> Mapping[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} is missing or not a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} root is not an object")
    integrity = value.get("integrity")
    if not isinstance(integrity, Mapping):
        raise ValueError(f"{label} integrity is missing")
    body = dict(value)
    body.pop("integrity", None)
    observed = _canonical_sha256(body)
    if (
        integrity.get("algorithm") != "sha256-canonical-json-without-integrity"
        or integrity.get("sha256") != observed
    ):
        raise ValueError(f"{label} canonical integrity differs")
    return value


def predecessor_binding() -> dict[str, Any]:
    return {
        "predecessor_v2_campaign_id": PREDECESSOR_V2_CAMPAIGN_ID,
        "predecessor_v2_contract_id": PREDECESSOR_V2_CONTRACT_ID,
        "predecessor_v2_action_id": PREDECESSOR_V2_ACTION_ID,
        "predecessor_v2_firmware_bin_sha256": (PREDECESSOR_V2_FIRMWARE_BIN_SHA256),
        "predecessor_v2_firmware_elf_sha256": (PREDECESSOR_V2_FIRMWARE_ELF_SHA256),
        "predecessor_v2_flash_file_sha256": PREDECESSOR_FLASH_FILE_SHA256,
        "predecessor_v2_flash_integrity_sha256": (PREDECESSOR_FLASH_INTEGRITY_SHA256),
        "predecessor_v2_diagnostic_file_sha256": (PREDECESSOR_DIAGNOSTIC_FILE_SHA256),
        "predecessor_v2_diagnostic_integrity_sha256": (
            PREDECESSOR_DIAGNOSTIC_INTEGRITY_SHA256
        ),
        "predecessor_v2_expected_classification": (PREDECESSOR_EXPECTED_CLASSIFICATION),
        "predecessor_v2_observed_classification": (PREDECESSOR_OBSERVED_CLASSIFICATION),
        "predecessor_v2_diagnostic_get_count": 4,
        "predecessor_v2_diagnostic_post_count": 0,
        "predecessor_v2_claim_count": 0,
        "predecessor_v2_visible_refresh_count": 0,
        "predecessor_v2_terminal_blocked": True,
        "predecessor_v2_action_never_claimed_or_executed": True,
        "not_retry_of_predecessor": True,
        "supersedes_failed_unmutated_v2": True,
        "does_not_reauthorize_v2": True,
        "predecessor_binding_enforcement": (
            "host_artifact_preflight_plus_compiled_echo"
        ),
    }


SUCCESSOR_BINDING = {
    "source_campaign_id": SOURCE_CAMPAIGN_ID,
    "source_main_contract_id": SOURCE_MAIN_CONTRACT_ID,
    "source_main_contract_exact_binding": True,
    "source_main_device_enforced_same_boot": True,
    "source_main_direct_exact_post_resume_after_reboot": False,
    "source_main_nvs_boot_key": source_pack.NVS_BOOT_KEY,
    "main_campaign_resume_after_containment": False,
    "containment_terminal_for_source_campaign": True,
    "ordinal4_no_visible_difference_branch": True,
    "source_main_ordinals_5_and_6_forbidden_after_branch": True,
    "relay_off_required_before_containment": True,
    **predecessor_binding(),
}


def _descriptor_payload() -> dict[str, Any]:
    return {
        "schema": (
            "mf1750-target-hue-redpink-brightness-v3-white-containment-"
            "successor-action-descriptor-v1"
        ),
        "profile_id": PROFILE_ID,
        "role": "FACTORY_OTP_WHITE_RECOVERY",
        "classification": CLASSIFICATION,
        **SUCCESSOR_BINDING,
        "frame_sha256": FRAME_SHA256,
        "cs1_dtm_sha256": DTM_SHA256,
        "cs2_dtm_sha256": DTM_SHA256,
    }


def _action() -> dict[str, Any]:
    return {
        "ordinal": 1,
        "role": "FACTORY_OTP_WHITE_RECOVERY",
        "descriptor_id": DESCRIPTOR_ID,
        "action_id": ACTION_ID,
        "frame_sha256": FRAME_SHA256,
        "cs1_dtm_sha256": DTM_SHA256,
        "cs2_dtm_sha256": DTM_SHA256,
    }


def _contract_payload(action: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": (
            "mf1750-target-hue-redpink-brightness-v3-white-containment-"
            "successor-contract-v1"
        ),
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        **SUCCESSOR_BINDING,
        "environment": ENVIRONMENT,
        "profile_id": PROFILE_ID,
        "classification": CLASSIFICATION,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "base_route": BASE_ROUTE,
        "actions": [dict(action)],
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
    }


def _validate_predecessor_evidence() -> dict[str, Any]:
    expected_files = (
        (
            PREDECESSOR_FLASH_FILE,
            PREDECESSOR_FLASH_BYTES,
            PREDECESSOR_FLASH_FILE_SHA256,
            "predecessor flash evidence",
        ),
        (
            PREDECESSOR_DIAGNOSTIC_FILE,
            PREDECESSOR_DIAGNOSTIC_BYTES,
            PREDECESSOR_DIAGNOSTIC_FILE_SHA256,
            "predecessor diagnostic evidence",
        ),
    )
    for path, byte_count, wanted_sha, label in expected_files:
        if (
            not path.is_file()
            or path.is_symlink()
            or path.stat().st_size != byte_count
            or _sha256(path) != wanted_sha
        ):
            raise ValueError(f"{label} file binding differs")

    flash = _read_sealed_json(PREDECESSOR_FLASH_FILE, label="predecessor flash")
    diagnostic = _read_sealed_json(
        PREDECESSOR_DIAGNOSTIC_FILE, label="predecessor diagnostic"
    )
    if flash["integrity"].get("sha256") != PREDECESSOR_FLASH_INTEGRITY_SHA256:
        raise ValueError("predecessor flash recorded integrity differs")
    if diagnostic["integrity"].get("sha256") != PREDECESSOR_DIAGNOSTIC_INTEGRITY_SHA256:
        raise ValueError("predecessor diagnostic recorded integrity differs")
    if (
        flash.get("outcome") != "app_only_write_verify_single_boot_pass"
        or flash.get("success") is not True
        or flash.get("j2_confirmed_off") is not True
        or flash.get("binary", {}).get("preflight_verified") is not True
        or flash.get("binary", {}).get("observed_sha256")
        != PREDECESSOR_V2_FIRMWARE_BIN_SHA256
    ):
        raise ValueError("predecessor flash terminal state differs")
    if (
        diagnostic.get("outcome") != "j2_off_diagnostic_failed_no_claim"
        or diagnostic.get("stage") != "preflight_validate_exact_identity"
        or diagnostic.get("error", {}).get("message")
        != "version classification differs"
        or diagnostic.get("claim_state") != "not_created"
        or diagnostic.get("permanent_claims_created") != 0
        or diagnostic.get("network") != {"get": 4, "post": 0}
        or diagnostic.get("visible_refreshes_confirmed") != 0
        or diagnostic.get("visible_refresh_may_have_occurred") is not False
        or diagnostic.get("no_retry") is not True
        or diagnostic.get("no_recovery") is not True
    ):
        raise ValueError("predecessor diagnostic terminal state differs")
    transcript = diagnostic.get("transcript")
    if (
        not isinstance(transcript, list)
        or [item.get("endpoint") for item in transcript]
        != ["version", "manifest", "status", "report"]
        or any(item.get("method") != "GET" for item in transcript)
        or any(item.get("status") != 200 for item in transcript)
    ):
        raise ValueError("predecessor diagnostic transcript differs")
    version, manifest, status, report = [item.get("body", {}) for item in transcript]
    if (
        version.get("classification") != PREDECESSOR_OBSERVED_CLASSIFICATION
        or manifest.get("classification") != PREDECESSOR_OBSERVED_CLASSIFICATION
        or version.get("contract_id") != PREDECESSOR_V2_CONTRACT_ID
        or version.get("running_app_elf_sha256") != PREDECESSOR_V2_FIRMWARE_ELF_SHA256
        or version.get("action_count") != 1
        or status.get("persistent_key_present") is not False
        or status.get("arm_request_count") != 0
        or status.get("execute_request_count") != 0
        or status.get("total_driver_call_count") != 0
        or status.get("busy") != 0
        or report.get("terminal_state") != "NOT_EXECUTED"
        or report.get("driver_called") is not False
        or report.get("driver_call_count_for_action") != 0
    ):
        raise ValueError("predecessor read-only fresh-state evidence differs")
    if PREDECESSOR_ACTION_OUTPUT.exists() or PREDECESSOR_CLAIM.exists():
        raise ValueError("predecessor action or claim unexpectedly exists")
    return {
        "verified": True,
        "flash_file_sha256": PREDECESSOR_FLASH_FILE_SHA256,
        "diagnostic_file_sha256": PREDECESSOR_DIAGNOSTIC_FILE_SHA256,
        "diagnostic_network": {"get": 4, "post": 0},
        "claim_count": 0,
        "visible_refresh_count": 0,
        "action_never_executed": True,
        "terminal_blocked": True,
        "not_retry": True,
    }


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
            "verified": (
                present
                and byte_count > 0
                and SHA256_RE.fullmatch(wanted) is not None
                and observed_bytes == byte_count
                and observed_sha256 == wanted
            ),
            "observed_bytes": observed_bytes,
            "observed_sha256": observed_sha256,
        }
    return result


def build_report(*, verify_artifacts: bool = True) -> dict[str, Any]:
    source_contract = source_pack.build_report()["contract_id"]
    if source_contract != SOURCE_MAIN_CONTRACT_ID:
        raise ValueError("source main contract binding differs")
    if _canonical_sha256(_descriptor_payload()) != DESCRIPTOR_ID:
        raise ValueError("V3 successor descriptor identity differs")
    wanted_action = hashlib.sha256(
        (
            "MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_WHITE_CONTAINMENT_"
            "SUCCESSOR_ACTION_V3|" + DESCRIPTOR_ID
        ).encode("ascii")
    ).hexdigest()
    if wanted_action != ACTION_ID:
        raise ValueError("V3 successor action identity differs")
    action = _action()
    contract_payload = _contract_payload(action)
    if _canonical_sha256(contract_payload) != CONTRACT_ID:
        raise ValueError("V3 successor contract identity differs")
    predecessor = _validate_predecessor_evidence()
    bindings = artifact_binding_status()
    if verify_artifacts:
        for key in ("firmware_bin", "firmware_elf"):
            if bindings[key]["verified"] is not True:
                raise ValueError(f"V3 successor {key} binding differs")
    return {
        "schema_version": 1,
        "kind": (
            "mf1750-target-hue-redpink-brightness-v3-white-containment-successor-pack"
        ),
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "contract": {**contract_payload, "contract_id": CONTRACT_ID},
        "action": action,
        "successor_binding": dict(SUCCESSOR_BINDING),
        "predecessor_evidence": predecessor,
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
        "artifact_binding_status": bindings,
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
