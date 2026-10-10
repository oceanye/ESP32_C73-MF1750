#!/usr/bin/env python3
"""Exact post-P1 factory-OTP white successor identity.

The successor is a fresh campaign with one white action.  It accepts only the
sealed ordinal-1 COMPLETE evidence produced by
``EC5_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1``.  A fault, an early stop, another
ordinal, or another build cannot enter this containment branch.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_p1_active_endpoint_atlas_4x8_v1_pack as source_pack  # noqa: E402


BUILD_TAG = (
    "MF1750_EC5_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_"
    "FACTORY_OTP_WHITE_SUCCESSOR_V1_2026-09-01"
)
TEST_ID = (
    "EC5-P1-ACTIVE-ENDPOINT-ATLAS-4X8-V1-"
    "FACTORY-OTP-WHITE-SUCCESSOR-V1"
)
CAMPAIGN_ID = (
    "EC5_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_"
    "FACTORY_OTP_WHITE_SUCCESSOR_V1"
)
SOURCE_CAMPAIGN_ID = source_pack.CAMPAIGN_ID
SOURCE_ORDINAL = 1
SOURCE_ROLE = source_pack.ROLE
SOURCE_MAIN_CONTRACT_ID = (
    "d36450e7cf69ad2e5e612f9df5b5abe0d33a036f9c3198a79a9e0e97a89a59f2"
)
SOURCE_ARTIFACTS = {
    "bin_bytes": 799_024,
    "bin_sha256": "f5c83b357c1db3dd065669e36d0ac9a09edfe47c720fadecad98c196a81652ed",
    "elf_bytes": 13_286_576,
    "elf_sha256": "c6eb0203cd7b5cd2373199ead8857cb793e495a459bced12aa3fd5160e5b7a7c",
}
SOURCE_FIRMWARE_BIN = (
    REPO_ROOT
    / ".pio/build-p1-active-endpoint-atlas-4x8-v1"
    / "ec5_p1_active_endpoint_atlas_4x8_v1"
    / "firmware.bin"
)
SOURCE_FIRMWARE_ELF = SOURCE_FIRMWARE_BIN.with_name("firmware.elf")
PROFILE_ID = "WF23_25"
NVS_NAMESPACE = "p1ae4x8w1"
NVS_KEY = "used_p1aew1"
FRAME_SHA256 = "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
DTM_SHA256 = "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158"
FRAME_FNV1A = 0x13340DC5
DTM_FNV1A = 0xB7A855C5
DEVICE_API_VERSION = (
    "MF1750_EC5_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_"
    "WHITE_SUCCESSOR_DEVICE_V1"
)
IDENTITY_REVISION = "p1-active-endpoint-atlas-4x8-v1-white-successor-v1"
CLASSIFICATION = (
    "FACTORY_OTP_WHITE_AFTER_P1_ACTIVE_ENDPOINT_ATLAS_ORDINAL1_COMPLETE_"
    "ONE_ACTION_NO_RUNTIME_PAYLOAD"
)
BASE_ROUTE = "/api/ec5/p1-active-endpoint-atlas-4x8-v1/white-successor-v1"
ARM_INTENT = (
    "ARM_ONE_FIXED_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_"
    "FACTORY_OTP_WHITE_SUCCESSOR_NOT_HARDWARE_AUTHORIZATION"
)
EXECUTE_INTENT = (
    "EXECUTE_ONE_FIXED_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_"
    "FACTORY_OTP_WHITE_SUCCESSOR_ONCE"
)
CLAIM_KIND = (
    "mf1750-p1-active-endpoint-atlas-4x8-v1-white-successor-v1-claim"
)
RESULT_KIND = (
    "mf1750-p1-active-endpoint-atlas-4x8-v1-white-successor-v1-result"
)
BUILD_ROOT = "build-p1-active-endpoint-atlas-4x8-v1-white-v1"
ENVIRONMENT = "ec5_p1_active_endpoint_atlas_4x8_v1_white_v1"
FIRMWARE_BIN = REPO_ROOT / ".pio" / BUILD_ROOT / ENVIRONMENT / "firmware.bin"
FIRMWARE_ELF = REPO_ROOT / ".pio" / BUILD_ROOT / ENVIRONMENT / "firmware.elf"
ZERO_SHA256 = "0" * 64

# Bound after a clean compile.  Zeroes deliberately make every live path fail
# closed until the exact candidate has been reviewed and patched here.
FIRMWARE_BIN_BYTES = 787_392
FIRMWARE_BIN_SHA256 = "4f67f065993dfce3f6ffaeb2b5afb5a89f82c4563c9ad83b79c505311af24ef3"
FIRMWARE_ELF_BYTES = 13_214_736
FIRMWARE_ELF_SHA256 = "cc3f9131b8b92e41e6b73c973b270837beed19a86b22cdc6f72f0107dd8d642e"


class P1WhiteSuccessorPackError(RuntimeError):
    """Raised before an unsealed or wrong-lineage successor can be used."""


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


def identity_source_path() -> Path:
    return (
        REPO_ROOT
        / ".pio/generated-p1-active-endpoint-atlas-4x8-v1-white-v1"
        / "ec5_p1_active_endpoint_atlas_4x8_v1_white_successor_v1_identity.inc"
    )


def main_source_path() -> Path:
    return (
        REPO_ROOT
        / ".pio/generated-p1-active-endpoint-atlas-4x8-v1-white-v1"
        / "ec5_p1_active_endpoint_atlas_4x8_v1_white_successor_v1_main.cpp"
    )


def _compiled_string(source: str, name: str) -> str:
    match = re.search(
        rf"static constexpr const char \*{re.escape(name)}\s*=\s*\"([^\"]+)\";",
        source,
    )
    if match is None:
        raise P1WhiteSuccessorPackError(f"compiled string {name} missing")
    return match.group(1)


def compiled_identity_marker(report: Mapping[str, Any] | None = None) -> str:
    value = build_report() if report is None else report
    return (
        "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
        "ROLE=OTP_WHITE_AFTER_P1_ACTIVE_ENDPOINT_ATLAS_ORDINAL1_COMPLETE|"
        f"SHA256={value['descriptor_id']}"
    )


def validate_compiled_identity_sources(report: Mapping[str, Any]) -> dict[str, Any]:
    identity_path = identity_source_path()
    main_path = main_source_path()
    for path in (identity_path, main_path):
        if not path.is_file() or path.is_symlink():
            raise P1WhiteSuccessorPackError("generated P1 white source missing or unsafe")
    identity = identity_path.read_text(encoding="utf-8")
    main = main_path.read_text(encoding="utf-8")
    contract = report["contract"]
    expected = {
        "kCampaignId": CAMPAIGN_ID,
        "kSourceCampaignId": SOURCE_CAMPAIGN_ID,
        "kSourceMainContractId": contract["source_main_contract_id"],
        "kBuildTag": BUILD_TAG,
        "kContractId": report["contract_id"],
        "kNvsNamespace": NVS_NAMESPACE,
        "kDescriptorId": report["descriptor_id"],
        "kActionId": report["action_id"],
        "kAcceptedSourceActionsSha256": contract[
            "accepted_source_complete_actions_sha256"
        ],
        "kSourceFirmwareBinSha256": contract["source_main_artifacts"][
            "bin_sha256"
        ],
        "kSourceFirmwareElfSha256": contract["source_main_artifacts"][
            "elf_sha256"
        ],
    }
    if any(_compiled_string(identity, name) != value for name, value in expected.items()):
        raise P1WhiteSuccessorPackError("generated P1 white identity differs")
    required_main = (
        f'kClassification =\n    "{CLASSIFICATION}"',
        f'kDeviceApiVersion =\n    "{DEVICE_API_VERSION}"',
        f'kTestId =\n    "{TEST_ID}"',
        f'kNvsKey = "{NVS_KEY}"',
        '\\"accepted_source_complete_ordinals\\":[1]',
        '\\"source_main_nvs_boot_key\\":\\"boot_p1a\\"',
        '\\"source_main_completed_p1_only\\":true',
    )
    if any(token not in main for token in required_main):
        raise P1WhiteSuccessorPackError("generated P1 white main identity differs")
    marker = compiled_identity_marker(report)
    if identity.count(marker) != 1:
        raise P1WhiteSuccessorPackError("generated P1 white marker differs")
    return {
        "verified": True,
        "identity_path": identity_path.relative_to(REPO_ROOT).as_posix(),
        "main_path": main_path.relative_to(REPO_ROOT).as_posix(),
        "marker_sha256": _sha(marker.encode("ascii")),
    }


def validate_compiled_identity_binary(report: Mapping[str, Any]) -> dict[str, Any]:
    if not artifacts_are_sealed():
        raise P1WhiteSuccessorPackError("P1 white artifacts are not sealed")
    marker = compiled_identity_marker(report).encode("ascii")
    counts = {
        "bin": FIRMWARE_BIN.read_bytes().count(marker),
        "elf": FIRMWARE_ELF.read_bytes().count(marker),
    }
    if counts != {"bin": 1, "elf": 1}:
        raise P1WhiteSuccessorPackError(
            f"P1 white compiled marker count differs: {counts}"
        )
    return {"verified": True, "counts": counts, "marker_sha256": _sha(marker)}


def _source_artifacts() -> dict[str, Any]:
    raw = getattr(source_pack, "ARTIFACTS", None)
    value: Any = deepcopy(SOURCE_ARTIFACTS)
    if isinstance(raw, Mapping):
        value = deepcopy(dict(raw))
        if source_pack.VARIANT_KEY in value:
            value = value[source_pack.VARIANT_KEY]
        if not isinstance(value, Mapping):
            raise P1WhiteSuccessorPackError("P1 source artifact shape differs")
        value = dict(value)
    aliases = {
        "bin_bytes": ("bin_bytes", "firmware_bin_bytes"),
        "bin_sha256": ("bin_sha256", "firmware_bin_sha256"),
        "elf_bytes": ("elf_bytes", "firmware_elf_bytes"),
        "elf_sha256": ("elf_sha256", "firmware_elf_sha256"),
    }
    normalized: dict[str, Any] = {}
    if isinstance(value.get("firmware.bin"), Mapping) and isinstance(
        value.get("firmware.elf"), Mapping
    ):
        normalized = {
            "bin_bytes": value["firmware.bin"].get("bytes"),
            "bin_sha256": value["firmware.bin"].get("sha256"),
            "elf_bytes": value["firmware.elf"].get("bytes"),
            "elf_sha256": value["firmware.elf"].get("sha256"),
        }
    else:
        for output, names in aliases.items():
            for name in names:
                if name in value:
                    normalized[output] = value[name]
                    break
    if (
        set(normalized) != set(aliases)
        or not isinstance(normalized["bin_bytes"], int)
        or not isinstance(normalized["elf_bytes"], int)
        or normalized["bin_bytes"] <= 0
        or normalized["elf_bytes"] <= 0
        or any(
            not isinstance(normalized[name], str)
            or len(normalized[name]) != 64
            or normalized[name] == ZERO_SHA256
            for name in ("bin_sha256", "elf_sha256")
        )
    ):
        raise P1WhiteSuccessorPackError("P1 source artifacts remain unsealed")
    if normalized != SOURCE_ARTIFACTS:
        raise P1WhiteSuccessorPackError("P1 source artifacts differ from exact binding")
    return normalized


def source_artifacts_are_sealed() -> bool:
    try:
        _source_artifacts()
    except P1WhiteSuccessorPackError:
        return False
    for path, size, digest in (
        (
            SOURCE_FIRMWARE_BIN,
            SOURCE_ARTIFACTS["bin_bytes"],
            SOURCE_ARTIFACTS["bin_sha256"],
        ),
        (
            SOURCE_FIRMWARE_ELF,
            SOURCE_ARTIFACTS["elf_bytes"],
            SOURCE_ARTIFACTS["elf_sha256"],
        ),
    ):
        if not path.is_file() or path.is_symlink():
            return False
        payload = path.read_bytes()
        if len(payload) != size or _sha(payload) != digest:
            return False
    sealed = getattr(source_pack, "artifacts_are_sealed", None)
    return True if sealed is None else bool(sealed())


def _report(source: Mapping[str, Any], source_artifacts: Mapping[str, Any]) -> dict[str, Any]:
    actions = source.get("actions")
    if not isinstance(actions, list) or len(actions) != 1:
        raise P1WhiteSuccessorPackError("P1 source action count differs")
    item = actions[0]
    accepted = [
        {
            "ordinal": item["ordinal"],
            "descriptor_id": item["descriptor_id"],
            "action_id": item["action_id"],
            "role": item["role"],
        }
    ]
    expected = {
        "ordinal": SOURCE_ORDINAL,
        "descriptor_id": item["descriptor_id"],
        "action_id": item["action_id"],
        "role": SOURCE_ROLE,
    }
    if accepted != [expected]:
        raise P1WhiteSuccessorPackError(
            "white successor accepts P1 ordinal-1 COMPLETE only"
        )
    if source.get("campaign_id") != SOURCE_CAMPAIGN_ID:
        raise P1WhiteSuccessorPackError("P1 source campaign differs")
    if source.get("contract_id") != SOURCE_MAIN_CONTRACT_ID:
        raise P1WhiteSuccessorPackError("P1 source contract differs")
    accepted_sha256 = _sha(_canonical(accepted))
    descriptor_payload = {
        "schema": "mf1750-p1-active-endpoint-atlas-4x8-v1-white-successor-descriptor-v1",
        "profile_id": PROFILE_ID,
        "role": "FACTORY_OTP_WHITE_RECOVERY_AFTER_P1_ORDINAL1_COMPLETE",
        "source_campaign_id": SOURCE_CAMPAIGN_ID,
        "source_main_contract_id": source["contract_id"],
        "source_main_artifacts": deepcopy(dict(source_artifacts)),
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
            "MF1750_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_WHITE_SUCCESSOR_V1|"
            f"{descriptor_id}"
        ).encode("ascii")
    )
    contract = {
        "schema": "mf1750-p1-active-endpoint-atlas-4x8-v1-white-successor-contract-v1",
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "source_campaign_id": SOURCE_CAMPAIGN_ID,
        "source_main_contract_id": source["contract_id"],
        "source_main_artifacts": deepcopy(dict(source_artifacts)),
        "accepted_source_complete_actions": accepted,
        "accepted_source_complete_actions_sha256": accepted_sha256,
        "accepted_source_ordinals": [SOURCE_ORDINAL],
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
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-p1-active-endpoint-atlas-4x8-v1-white-successor-offline-identity-v1",
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
            "source_main_artifacts": deepcopy(dict(source_artifacts)),
            "accepted_source_complete_actions": accepted,
            "accepted_source_complete_actions_sha256": accepted_sha256,
            "main_campaign_resume_after_containment": False,
        },
    }


def build_report(*, verify_artifacts: bool = False) -> dict[str, Any]:
    source = source_pack.build_report()
    report = _report(source, _source_artifacts())
    if verify_artifacts:
        if not artifacts_are_sealed():
            raise P1WhiteSuccessorPackError("P1 white successor artifacts are unsealed")
        for label, path, size, digest in (
            ("bin", FIRMWARE_BIN, FIRMWARE_BIN_BYTES, FIRMWARE_BIN_SHA256),
            ("elf", FIRMWARE_ELF, FIRMWARE_ELF_BYTES, FIRMWARE_ELF_SHA256),
        ):
            if not path.is_file() or path.is_symlink():
                raise P1WhiteSuccessorPackError(f"P1 white {label} missing")
            payload = path.read_bytes()
            if len(payload) != size or _sha(payload) != digest:
                raise P1WhiteSuccessorPackError(f"P1 white {label} differs")
        validate_compiled_identity_sources(report)
        validate_compiled_identity_binary(report)
    return report


def dry_validate(*, require_sealed: bool = False, verify_artifacts: bool = False) -> dict[str, Any]:
    source_sealed = source_artifacts_are_sealed()
    successor_sealed = artifacts_are_sealed()
    if require_sealed and not source_sealed:
        raise P1WhiteSuccessorPackError("P1 source artifacts are unsealed")
    report = build_report(verify_artifacts=verify_artifacts)
    if require_sealed and not successor_sealed:
        raise P1WhiteSuccessorPackError("P1 white successor artifacts are unsealed")
    contract = report["contract"]
    if (
        contract["accepted_source_ordinals"] != [1]
        or contract["source_fault_not_accepted"] is not True
        or contract["source_early_stop_not_accepted"] is not True
        or contract["autochain"] is not False
        or contract["one_visible_refresh"] is not True
    ):
        raise P1WhiteSuccessorPackError("P1 white successor contract differs")
    return {
        "schema_version": 1,
        "kind": "mf1750-p1-active-endpoint-atlas-4x8-v1-white-successor-dry-validation",
        "result": (
            "PASS"
            if require_sealed
            else (
                "OFFLINE_IDENTITY_PASS_LIVE_GATE_PENDING"
                if source_sealed and successor_sealed
                else "BLOCKED_WAITING_FOR_SOURCE_OR_SUCCESSOR_SEAL"
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
        "accepted_source_ordinals": [1],
        "source_artifacts_sealed": source_sealed,
        "successor_artifacts_sealed": successor_sealed,
        "artifacts_verified": verify_artifacts,
    }


# Compatibility exports required by the frozen one-shot containment validator.
# They are derived from the same report used by generated C++ and therefore do
# not create a second identity authority.
_REPORT = build_report(verify_artifacts=False)
CONTRACT_ID = _REPORT["contract_id"]
DESCRIPTOR_ID = _REPORT["descriptor_id"]
ACTION_ID = _REPORT["action_id"]
DESCRIPTOR_MARKER = compiled_identity_marker(_REPORT)


if __name__ == "__main__":
    print(json.dumps(dry_validate(), indent=2, sort_keys=True))
