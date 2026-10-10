#!/usr/bin/env python3
"""Seal one factory-OTP white successor for the P2-C endpoint atlas.

This module is an offline identity authority only.  The successor accepts one
specific ordinal-1 COMPLETE result from the separately sealed P2 commented /
commented 4x8 endpoint-atlas campaign.  It never accepts an early stop, fault,
foreign build, or a second source action and it never chains itself.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SOURCE_PACK_MODULE = "tools.mf1750_p2_commented_endpoint_atlas_4x8_v1_pack"
SOURCE_BUILD_REPORT = (
    REPO_ROOT
    / "docs/MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_OFFLINE_BUILD_2026-09-03.json"
)

BUILD_TAG = (
    "MF1750_EC5_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_"
    "FACTORY_OTP_WHITE_SUCCESSOR_V1_2026-09-03"
)
TEST_ID = "EC5-P2-COMMENTED-ENDPOINT-ATLAS-4X8-V1-WHITE-SUCCESSOR-V1"
CAMPAIGN_ID = "EC5_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_WHITE_SUCCESSOR_V1"
SOURCE_CAMPAIGN_ID = "EC5_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1"
SOURCE_ORDINAL = 1
PROFILE_ID = "WF23_25"
NVS_NAMESPACE = "p2catwsv1"
NVS_KEY = "used_p2cw1"
FRAME_SHA256 = "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
DTM_SHA256 = "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158"
FRAME_FNV1A = 0x13340DC5
DTM_FNV1A = 0xB7A855C5
DEVICE_API_VERSION = (
    "MF1750_EC5_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_WHITE_SUCCESSOR_DEVICE_V1"
)
IDENTITY_REVISION = "p2-commented-endpoint-atlas-4x8-v1-white-successor-v1"
CLASSIFICATION = (
    "FACTORY_OTP_WHITE_AFTER_P2_COMMENTED_ENDPOINT_ATLAS_ORDINAL1_COMPLETE_"
    "ONE_ACTION_NO_RUNTIME_PAYLOAD"
)
BASE_ROUTE = "/api/ec5/p2-commented-endpoint-atlas-4x8-v1/white-successor-v1"
ARM_INTENT = (
    "ARM_ONE_FIXED_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_"
    "FACTORY_OTP_WHITE_SUCCESSOR_NOT_HARDWARE_AUTHORIZATION"
)
EXECUTE_INTENT = (
    "EXECUTE_ONE_FIXED_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_"
    "FACTORY_OTP_WHITE_SUCCESSOR_ONCE"
)
CLAIM_KIND = "mf1750-p2-commented-endpoint-atlas-4x8-v1-white-successor-v1-claim"
RESULT_KIND = "mf1750-p2-commented-endpoint-atlas-4x8-v1-white-successor-v1-result"
BUILD_ROOT = "br_lhr4"
ENVIRONMENT = "ec5_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1"
BUILD_ENVIRONMENT = "lhr4"
GENERATED_ROOT = REPO_ROOT / ".pio/g_lhr4"
FIRMWARE_BIN = REPO_ROOT / ".pio" / BUILD_ROOT / BUILD_ENVIRONMENT / "firmware.bin"
FIRMWARE_ELF = REPO_ROOT / ".pio" / BUILD_ROOT / BUILD_ENVIRONMENT / "firmware.elf"
ZERO_SHA256 = "0" * 64

# These bindings are patched only after the independent P2-C main build report
# and binaries exist.  Zero values deliberately block codegen/build/live use.
SOURCE_MAIN_CONTRACT_ID = (
    "6eb7be2835fac28df8922c86ab6236a7bd8cc81152ea72ad3be47bdc266ac216"
)
SOURCE_MAIN_DESCRIPTOR_ID = (
    "dcbbb2f433c84d8804678f41a77cca21c14705383b5893b36fb8e9f3e036c9bc"
)
SOURCE_MAIN_ACTION_ID = (
    "ec26e0f76f194f0e6c58a2879310dfccd9d110656bff62dc4f230086105777b9"
)
SOURCE_MAIN_ROLE = "P2_COMMENTED_COMPLETE_PROFILE_POSITION_BALANCED_4X8_ENDPOINT_ATLAS"
SOURCE_BUILD_REPORT_FILE_SHA256 = (
    "e2c1adce901971fa2472967c8f237507861ac697e3fc3ef9b8ed51a5301a2d06"
)
SOURCE_ARTIFACTS = {
    "bin_bytes": 798_496,
    "bin_sha256": "61d7704f4dfbcfd3b2ec21aa1eb571b400bf5ee391ababe6e4da1dc54010935d",
    "elf_bytes": 13_286_496,
    "elf_sha256": "451b7663aabd40a0771161c334c41f1f9be39ff0d47b2b7a7342b4edda9f7ac1",
}

# These are patched after a deterministic compile of this successor.  Keeping
# them zero makes every artifact-verifying or live path fail closed.
FIRMWARE_BIN_BYTES = 787_568
FIRMWARE_BIN_SHA256 = "dc93c95a956eecf7d9cb753e5fb82ea16e5f2142694a8fcd22157481570d2de6"
FIRMWARE_ELF_BYTES = 13_214_764
FIRMWARE_ELF_SHA256 = "ff3793efde294bf981f3b1932799fdc574917fe33c0f1d15bf636367c5aba067"


class P2CommentedWhiteSuccessorPackError(RuntimeError):
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


def _is_sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9a-f]{64}", value) is not None
        and value != ZERO_SHA256
    )


def _source_pack() -> Any:
    try:
        return importlib.import_module(SOURCE_PACK_MODULE)
    except (ImportError, AttributeError) as error:
        raise P2CommentedWhiteSuccessorPackError(
            "sealed P2-C source pack is not available"
        ) from error


def _source_action(source: Mapping[str, Any]) -> Mapping[str, Any]:
    actions = source.get("actions")
    if not isinstance(actions, list):
        contract = source.get("contract")
        actions = contract.get("actions") if isinstance(contract, Mapping) else None
    if (
        not isinstance(actions, list)
        or len(actions) != 1
        or not isinstance(actions[0], Mapping)
    ):
        raise P2CommentedWhiteSuccessorPackError("P2-C source action count differs")
    return actions[0]


def _source_artifact_paths(module: Any) -> tuple[Path, Path]:
    paths = getattr(module, "artifact_paths", None)
    if callable(paths):
        values = tuple(Path(item) for item in paths())
        if len(values) == 2:
            return values[0], values[1]
    build_dir = getattr(module, "BUILD_DIR", None)
    if build_dir is not None:
        root = Path(build_dir)
        return root / "firmware.bin", root / "firmware.elf"
    raise P2CommentedWhiteSuccessorPackError("P2-C source artifact paths missing")


def _source_nvs_boot_key(module: Any) -> str:
    value = getattr(module, "NVS_BOOT_KEY", None)
    if not isinstance(value, str) or not value:
        raise P2CommentedWhiteSuccessorPackError("P2-C source boot key missing")
    return value


def source_nvs_boot_key() -> str:
    return _source_nvs_boot_key(_source_pack())


def _read_source_build_report() -> dict[str, Any]:
    if not SOURCE_BUILD_REPORT.is_file() or SOURCE_BUILD_REPORT.is_symlink():
        raise P2CommentedWhiteSuccessorPackError("P2-C offline build report missing")
    payload = SOURCE_BUILD_REPORT.read_bytes()
    if not _is_sha(SOURCE_BUILD_REPORT_FILE_SHA256):
        raise P2CommentedWhiteSuccessorPackError(
            "P2-C offline build report hash is not sealed"
        )
    if _sha(payload) != SOURCE_BUILD_REPORT_FILE_SHA256:
        raise P2CommentedWhiteSuccessorPackError("P2-C offline build report differs")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise P2CommentedWhiteSuccessorPackError(
            "P2-C offline build report is not JSON"
        ) from error
    if not isinstance(value, dict):
        raise P2CommentedWhiteSuccessorPackError(
            "P2-C offline build report root differs"
        )
    return value


def _normalized_source_artifacts(module: Any) -> dict[str, Any]:
    artifact_map = getattr(module, "ARTIFACTS", None)
    if (
        isinstance(artifact_map, Mapping)
        and isinstance(artifact_map.get("firmware.bin"), Mapping)
        and isinstance(artifact_map.get("firmware.elf"), Mapping)
    ):
        normalized = {
            "bin_bytes": artifact_map["firmware.bin"].get("bytes"),
            "bin_sha256": artifact_map["firmware.bin"].get("sha256"),
            "elf_bytes": artifact_map["firmware.elf"].get("bytes"),
            "elf_sha256": artifact_map["firmware.elf"].get("sha256"),
        }
        if normalized != SOURCE_ARTIFACTS:
            raise P2CommentedWhiteSuccessorPackError(
                "P2-C source artifacts differ from exact white-successor binding"
            )
        return normalized
    aliases = (
        ("FIRMWARE_BIN_BYTES", "FIRMWARE_BIN_SIZE"),
        ("FIRMWARE_BIN_SHA256",),
        ("FIRMWARE_ELF_BYTES", "FIRMWARE_ELF_SIZE"),
        ("FIRMWARE_ELF_SHA256",),
    )
    values: list[Any] = []
    for names in aliases:
        found = None
        for name in names:
            if hasattr(module, name):
                found = getattr(module, name)
                break
        values.append(found)
    normalized = {
        "bin_bytes": values[0],
        "bin_sha256": values[1],
        "elf_bytes": values[2],
        "elf_sha256": values[3],
    }
    if normalized != SOURCE_ARTIFACTS:
        raise P2CommentedWhiteSuccessorPackError(
            "P2-C source artifacts differ from exact white-successor binding"
        )
    if (
        not isinstance(normalized["bin_bytes"], int)
        or not isinstance(normalized["elf_bytes"], int)
        or normalized["bin_bytes"] <= 0
        or normalized["elf_bytes"] <= 0
        or not _is_sha(normalized["bin_sha256"])
        or not _is_sha(normalized["elf_sha256"])
    ):
        raise P2CommentedWhiteSuccessorPackError("P2-C source artifacts are unsealed")
    return normalized


def _validated_source() -> tuple[
    Any, dict[str, Any], Mapping[str, Any], dict[str, Any]
]:
    module = _source_pack()
    report_builder = getattr(module, "build_report", None)
    if not callable(report_builder):
        raise P2CommentedWhiteSuccessorPackError("P2-C source report builder missing")
    source = report_builder()
    if not isinstance(source, dict):
        raise P2CommentedWhiteSuccessorPackError("P2-C source report differs")
    action = _source_action(source)
    artifacts = _normalized_source_artifacts(module)
    offline = _read_source_build_report()
    expected = {
        "campaign_id": SOURCE_CAMPAIGN_ID,
        "contract_id": SOURCE_MAIN_CONTRACT_ID,
    }
    if any(source.get(key) != value for key, value in expected.items()):
        raise P2CommentedWhiteSuccessorPackError("P2-C source identity differs")
    if (
        action.get("ordinal") != SOURCE_ORDINAL
        or action.get("descriptor_id") != SOURCE_MAIN_DESCRIPTOR_ID
        or action.get("action_id") != SOURCE_MAIN_ACTION_ID
        or action.get("role") != SOURCE_MAIN_ROLE
    ):
        raise P2CommentedWhiteSuccessorPackError("P2-C source action differs")
    if (
        offline.get("campaign_id") != SOURCE_CAMPAIGN_ID
        or offline.get("contract_id") != SOURCE_MAIN_CONTRACT_ID
    ):
        raise P2CommentedWhiteSuccessorPackError(
            "P2-C offline build report identity differs"
        )
    source_bin, source_elf = _source_artifact_paths(module)
    for label, path, size, digest in (
        ("bin", source_bin, artifacts["bin_bytes"], artifacts["bin_sha256"]),
        ("elf", source_elf, artifacts["elf_bytes"], artifacts["elf_sha256"]),
    ):
        if not path.is_file() or path.is_symlink():
            raise P2CommentedWhiteSuccessorPackError(f"P2-C source {label} missing")
        payload = path.read_bytes()
        if len(payload) != size or _sha(payload) != digest:
            raise P2CommentedWhiteSuccessorPackError(f"P2-C source {label} differs")
    sealed = getattr(module, "artifacts_are_sealed", None)
    if callable(sealed) and sealed() is not True:
        raise P2CommentedWhiteSuccessorPackError("P2-C source pack is not sealed")
    return module, source, action, artifacts


def source_artifacts_are_sealed() -> bool:
    try:
        _validated_source()
    except (OSError, P2CommentedWhiteSuccessorPackError):
        return False
    return True


def artifacts_are_sealed() -> bool:
    return (
        FIRMWARE_BIN_BYTES > 0
        and FIRMWARE_ELF_BYTES > 0
        and _is_sha(FIRMWARE_BIN_SHA256)
        and _is_sha(FIRMWARE_ELF_SHA256)
    )


def artifact_paths() -> tuple[Path, Path]:
    return FIRMWARE_BIN, FIRMWARE_ELF


def identity_source_path() -> Path:
    return GENERATED_ROOT / (
        "ec5_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_identity.inc"
    )


def main_source_path() -> Path:
    return GENERATED_ROOT / (
        "ec5_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_main.cpp"
    )


def _compiled_string(source: str, name: str) -> str:
    match = re.search(
        rf"static constexpr const char \*{re.escape(name)}\s*=\s*\"([^\"]+)\";",
        source,
    )
    if match is None:
        raise P2CommentedWhiteSuccessorPackError(f"compiled string {name} missing")
    return match.group(1)


def compiled_identity_marker(report: Mapping[str, Any] | None = None) -> str:
    value = build_report() if report is None else report
    return (
        "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
        "ROLE=OTP_WHITE_AFTER_P2_COMMENTED_ENDPOINT_ATLAS_ORDINAL1_COMPLETE|"
        f"SHA256={value['descriptor_id']}"
    )


def validate_compiled_identity_sources(report: Mapping[str, Any]) -> dict[str, Any]:
    identity_path = identity_source_path()
    main_path = main_source_path()
    for path in (identity_path, main_path):
        if not path.is_file() or path.is_symlink():
            raise P2CommentedWhiteSuccessorPackError(
                "generated P2-C white source missing"
            )
    identity = identity_path.read_text(encoding="utf-8")
    main = main_path.read_text(encoding="utf-8")
    contract = report["contract"]
    expected = {
        "kCampaignId": CAMPAIGN_ID,
        "kSourceCampaignId": SOURCE_CAMPAIGN_ID,
        "kSourceMainContractId": contract["source_main_contract_id"],
        "kSourceMainOfflineBuildSha256": contract[
            "source_main_offline_build_file_sha256"
        ],
        "kBuildTag": BUILD_TAG,
        "kContractId": report["contract_id"],
        "kNvsNamespace": NVS_NAMESPACE,
        "kDescriptorId": report["descriptor_id"],
        "kActionId": report["action_id"],
        "kAcceptedSourceActionsSha256": contract[
            "accepted_source_complete_actions_sha256"
        ],
        "kSourceFirmwareBinSha256": contract["source_main_artifacts"]["bin_sha256"],
        "kSourceFirmwareElfSha256": contract["source_main_artifacts"]["elf_sha256"],
    }
    if any(
        _compiled_string(identity, name) != value for name, value in expected.items()
    ):
        raise P2CommentedWhiteSuccessorPackError(
            "generated P2-C white identity differs"
        )
    required_main = (
        f'kClassification =\n    "{CLASSIFICATION}"',
        f'kDeviceApiVersion =\n    "{DEVICE_API_VERSION}"',
        f'kTestId =\n    "{TEST_ID}"',
        f'kNvsKey = "{NVS_KEY}"',
        '\\"accepted_source_complete_ordinals\\":[1]',
        f'\\"source_main_nvs_boot_key\\":\\"{source_nvs_boot_key()}\\"',
        '\\"source_main_completed_p2_commented_only\\":true',
    )
    if any(token not in main for token in required_main):
        raise P2CommentedWhiteSuccessorPackError("generated P2-C white main differs")
    marker = compiled_identity_marker(report)
    if identity.count(marker) != 1:
        raise P2CommentedWhiteSuccessorPackError("generated P2-C white marker differs")
    return {
        "verified": True,
        "identity_path": identity_path.relative_to(REPO_ROOT).as_posix(),
        "main_path": main_path.relative_to(REPO_ROOT).as_posix(),
        "marker_sha256": _sha(marker.encode("ascii")),
    }


def validate_compiled_identity_binary(report: Mapping[str, Any]) -> dict[str, Any]:
    if not artifacts_are_sealed():
        raise P2CommentedWhiteSuccessorPackError("P2-C white artifacts are unsealed")
    marker = compiled_identity_marker(report).encode("ascii")
    counts = {
        "bin": FIRMWARE_BIN.read_bytes().count(marker),
        "elf": FIRMWARE_ELF.read_bytes().count(marker),
    }
    if counts != {"bin": 1, "elf": 1}:
        raise P2CommentedWhiteSuccessorPackError(
            f"P2-C white compiled marker count differs: {counts}"
        )
    return {"verified": True, "counts": counts, "marker_sha256": _sha(marker)}


def _report(
    source: Mapping[str, Any], action: Mapping[str, Any], artifacts: Mapping[str, Any]
) -> dict[str, Any]:
    accepted = [
        {
            "ordinal": SOURCE_ORDINAL,
            "descriptor_id": SOURCE_MAIN_DESCRIPTOR_ID,
            "action_id": SOURCE_MAIN_ACTION_ID,
            "role": SOURCE_MAIN_ROLE,
        }
    ]
    accepted_sha256 = _sha(_canonical(accepted))
    descriptor_payload = {
        "schema": "mf1750-p2-commented-endpoint-atlas-4x8-v1-white-successor-descriptor-v1",
        "profile_id": PROFILE_ID,
        "role": "FACTORY_OTP_WHITE_RECOVERY_AFTER_P2_COMMENTED_ORDINAL1_COMPLETE",
        "source_campaign_id": SOURCE_CAMPAIGN_ID,
        "source_main_contract_id": SOURCE_MAIN_CONTRACT_ID,
        "source_main_offline_build_file_sha256": SOURCE_BUILD_REPORT_FILE_SHA256,
        "source_main_artifacts": deepcopy(dict(artifacts)),
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
            "MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_WHITE_SUCCESSOR_V1|"
            f"{descriptor_id}"
        ).encode("ascii")
    )
    contract = {
        "schema": "mf1750-p2-commented-endpoint-atlas-4x8-v1-white-successor-contract-v1",
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "source_campaign_id": SOURCE_CAMPAIGN_ID,
        "source_main_contract_id": SOURCE_MAIN_CONTRACT_ID,
        "source_main_offline_build_file_sha256": SOURCE_BUILD_REPORT_FILE_SHA256,
        "source_main_artifacts": deepcopy(dict(artifacts)),
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
        "full_busy_required": True,
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
        "kind": "mf1750-p2-commented-endpoint-atlas-4x8-v1-white-successor-offline-identity-v1",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "camera_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "campaign_id": CAMPAIGN_ID,
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
            "source_main_offline_build_file_sha256": SOURCE_BUILD_REPORT_FILE_SHA256,
            "source_main_artifacts": deepcopy(dict(artifacts)),
            "accepted_source_complete_actions": accepted,
            "accepted_source_complete_actions_sha256": accepted_sha256,
            "main_campaign_resume_after_containment": False,
        },
    }


# Exact workspace compile inputs and repair report; device identity is checked live.
LH4_SOURCE_SHA256 = {
    ".pio/g_lhr4/ec5_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_epd_driver.cpp": "0e34ed03c6655d906b0e23cef5f8c383db2f395d57665c7698ac44098d859f32",
    ".pio/g_lhr4/ec5_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_identity.inc": "f9040ad5b3dfb268678e241a456c725acc7922cef9dc59318ff37d24bbebe623",
    ".pio/g_lhr4/ec5_p2_commented_endpoint_atlas_4x8_v1_white_successor_v1_main.cpp": "a45d1544e1312a29af5ac3dcf75d2eebeedf62ece5e64138b6aad94b2dc85096",
    ".test-output/offline/MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_LINEAGE_REPAIR_20260912_LH4/lineage-repair-offline-build.json": "95dcd87d16519b4cd98b116641fc8d067e5b45b51503b603e5eba9beec359a54",
    "platformio.lhr4.ini": "0a734b6de6aec71d8834a0a1421f3457c278c8550f67f41fc31ccd529c924e19",
    "src/ec5_factory_otp_white_recovery_driver.inc": "99b610de70989e82fdaea709f015410af52afd99654eacc05ce2c22d7c9c7aaf",
    "src/epd_config.h": "e8b13cf413192f344db27ec34491d0a764adb3a126173ac126c1774d418f1a8d",
    "src/epd_diagnostics.h": "a9db79d969eddfbf59ba57e7aee03d4a6017dd7374078b1fdc61c7abef7ce03f",
    "src/epd_driver.cpp": "386acdd3e2fef3d22e4b97551330d310b86d1aafc5085df35a676e9b8dad2f6c",
    "src/epd_driver.h": "3bbddfe8893e3024b0d745b0342dd1be576ebb6be7017ef4704952636ad42343",
    "src/wifi_secrets.h": "98828cee0d4e4d9283c4d721ee76950a05dffb1ec62b190cc7eb79f5701ce437",
}


def validate_lh4_sources() -> None:
    for relative, expected in LH4_SOURCE_SHA256.items():
        path = REPO_ROOT / relative
        if (
            not path.is_file()
            or path.is_symlink()
            or _sha(path.read_bytes()) != expected
        ):
            raise P2CommentedWhiteSuccessorPackError(
                f"LH4 source or report differs: {relative}"
            )


def build_report(*, verify_artifacts: bool = False) -> dict[str, Any]:
    _module, source, action, artifacts = _validated_source()
    report = _report(source, action, artifacts)
    if verify_artifacts:
        validate_lh4_sources()
        if not artifacts_are_sealed():
            raise P2CommentedWhiteSuccessorPackError(
                "P2-C white artifacts are unsealed"
            )
        for label, path, size, digest in (
            ("bin", FIRMWARE_BIN, FIRMWARE_BIN_BYTES, FIRMWARE_BIN_SHA256),
            ("elf", FIRMWARE_ELF, FIRMWARE_ELF_BYTES, FIRMWARE_ELF_SHA256),
        ):
            if not path.is_file() or path.is_symlink():
                raise P2CommentedWhiteSuccessorPackError(f"P2-C white {label} missing")
            payload = path.read_bytes()
            if len(payload) != size or _sha(payload) != digest:
                raise P2CommentedWhiteSuccessorPackError(f"P2-C white {label} differs")
        validate_compiled_identity_sources(report)
        validate_compiled_identity_binary(report)
    return report


def dry_validate(
    *, require_sealed: bool = False, verify_artifacts: bool = False
) -> dict[str, Any]:
    source_sealed = source_artifacts_are_sealed()
    successor_sealed = artifacts_are_sealed()
    if require_sealed and not source_sealed:
        raise P2CommentedWhiteSuccessorPackError("P2-C source artifacts are unsealed")
    report = build_report(verify_artifacts=verify_artifacts)
    if require_sealed and not successor_sealed:
        raise P2CommentedWhiteSuccessorPackError("P2-C white artifacts are unsealed")
    contract = report["contract"]
    if (
        contract["accepted_source_ordinals"] != [1]
        or contract["source_fault_not_accepted"] is not True
        or contract["source_early_stop_not_accepted"] is not True
        or contract["autochain"] is not False
        or contract["one_visible_refresh"] is not True
        or contract["full_busy_required"] is not True
    ):
        raise P2CommentedWhiteSuccessorPackError(
            "P2-C white successor contract differs"
        )
    return {
        "schema_version": 1,
        "kind": "mf1750-p2-commented-endpoint-atlas-4x8-v1-white-successor-dry-validation",
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


def _compatibility_exports() -> tuple[str, str, str, str]:
    try:
        report = build_report(verify_artifacts=False)
    except (OSError, P2CommentedWhiteSuccessorPackError):
        return ZERO_SHA256, ZERO_SHA256, ZERO_SHA256, "BLOCKED_UNSEALED_P2_C_SOURCE"
    return (
        report["contract_id"],
        report["descriptor_id"],
        report["action_id"],
        compiled_identity_marker(report),
    )


CONTRACT_ID, DESCRIPTOR_ID, ACTION_ID, DESCRIPTOR_MARKER = _compatibility_exports()


if __name__ == "__main__":
    try:
        print(json.dumps(dry_validate(), indent=2, sort_keys=True))
    except (OSError, P2CommentedWhiteSuccessorPackError) as error:
        raise SystemExit(f"P2-C white successor pack blocked: {error}") from error
