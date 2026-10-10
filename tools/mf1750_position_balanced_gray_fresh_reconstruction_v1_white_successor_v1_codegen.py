#!/usr/bin/env python3
"""Generate the isolated R3-only factory-OTP white successor sources."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_position_balanced_gray_fresh_reconstruction_v1_white_successor_v1_pack as pack,
)

SOURCE_MAIN = REPO_ROOT / "src/ec5_lightness_hold_function_chain_v1_white_successor_v1_main.cpp"
SOURCE_MAIN_BYTES = 27_987
SOURCE_MAIN_SHA256 = (
    "4825ceb880cddbfc5743fcdb336bb8cc50c555a2d75298e455eb91ad3051a462"
)
OUTPUT_ROOT = REPO_ROOT / ".pio/generated-position-balanced-gray-fresh-reconstruction-v1-white-v1"
MAIN_NAME = "ec5_position_balanced_gray_fresh_reconstruction_v1_white_successor_v1_main.cpp"
DRIVER_NAME = "ec5_position_balanced_gray_fresh_reconstruction_v1_white_successor_v1_epd_driver.cpp"
IDENTITY_NAME = "ec5_position_balanced_gray_fresh_reconstruction_v1_white_successor_v1_identity.inc"
OLD_MACRO = "MF1750_LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_WHITE_SUCCESSOR_V1_BUILD"
NEW_MACRO = "MF1750_POSITION_BALANCED_GRAY_FRESH_RECONSTRUCTION_V1_WHITE_SUCCESSOR_V1_BUILD"


class ReconstructionWhiteCodegenError(RuntimeError):
    """Raised before provisional or drifted white source generation."""


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _cxx(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _frozen_main() -> str:
    if not SOURCE_MAIN.is_file() or SOURCE_MAIN.is_symlink():
        raise ReconstructionWhiteCodegenError("frozen white main missing")
    payload = SOURCE_MAIN.read_bytes()
    if len(payload) != SOURCE_MAIN_BYTES or _sha(payload) != SOURCE_MAIN_SHA256:
        raise ReconstructionWhiteCodegenError("frozen white main changed")
    return payload.decode("utf-8")


def _render_identity(report: Mapping[str, Any]) -> str:
    contract = report["contract"]
    marker = (
        "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
        "ROLE=OTP_WHITE_AFTER_POSITION_BALANCED_GRAY_FRESH_RECONSTRUCTION_R3_COMPLETE|"
        f"SHA256={report['descriptor_id']}"
    )
    return f"""#pragma once

// Exact authority for one factory-OTP white action after reconstruction R3
// COMPLETE.  Fault, early-stop, R1, R2, and every G4 identity are rejected.
static constexpr const char *kProfileId = {_cxx(pack.PROFILE_ID)};
static constexpr const char *kEnvironmentId = {_cxx(pack.ENVIRONMENT)};
static constexpr const char *kCampaignId = {_cxx(pack.CAMPAIGN_ID)};
static constexpr const char *kSourceCampaignId = {_cxx(pack.SOURCE_CAMPAIGN_ID)};
static constexpr const char *kSourceMainContractId =
    {_cxx(str(contract['source_main_contract_id']))};
static constexpr const char *kBuildTag = {_cxx(pack.BUILD_TAG)};
static constexpr const char *kContractId = {_cxx(str(report['contract_id']))};
static constexpr const char *kNvsNamespace = {_cxx(pack.NVS_NAMESPACE)};
static constexpr const char *kDescriptorId = {_cxx(str(report['descriptor_id']))};
static constexpr const char *kActionId = {_cxx(str(report['action_id']))};
static constexpr const char *kAcceptedSourceActionsSha256 =
    {_cxx(str(contract['accepted_source_complete_actions_sha256']))};
static constexpr const char *kSourceFirmwareBinSha256 =
    {_cxx(str(contract['source_main_artifacts']['bin_sha256']))};
static constexpr const char *kSourceFirmwareElfSha256 =
    {_cxx(str(contract['source_main_artifacts']['elf_sha256']))};

extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\\"a\\"\\n"
    ".global kTransactionDescriptorMarker\\n"
    ".type kTransactionDescriptorMarker,@object\\n"
    "kTransactionDescriptorMarker:\\n"
    ".asciz \\"{marker}\\"\\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\\n"
    ".previous\\n");
"""


def _render_main() -> str:
    payload = _frozen_main()
    replacements = (
        (OLD_MACRO, NEW_MACRO, 3),
        (
            "FACTORY_OTP_WHITE_AFTER_LIGHTNESS_HOLD_H2_COMPLETE_ONE_ACTION_NO_RUNTIME_PAYLOAD",
            pack.CLASSIFICATION,
            1,
        ),
        (
            "MF1750_EC5_LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_WHITE_SUCCESSOR_DEVICE_V1",
            pack.DEVICE_API_VERSION,
            1,
        ),
        (
            "lightness-hold-function-chain-v1-white-successor-v1",
            pack.IDENTITY_REVISION,
            1,
        ),
        (
            "EC5-LIGHTNESS-HOLD-FUNCTION-CHAIN-V1-FACTORY-OTP-WHITE-SUCCESSOR-V1",
            pack.TEST_ID,
            1,
        ),
        (
            "ec5_lightness_hold_function_chain_v1_white_successor_v1_identity.inc",
            IDENTITY_NAME,
            1,
        ),
        ("used_lhfcw1", pack.NVS_KEY, 1),
        (
            "/api/ec5/lightness-hold-function-chain-v1/white-successor-v1",
            pack.BASE_ROUTE,
            6,
        ),
        (
            "ARM_ONE_FIXED_LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_FACTORY_OTP_WHITE_SUCCESSOR_NOT_HARDWARE_AUTHORIZATION",
            pack.ARM_INTENT,
            1,
        ),
        (
            "EXECUTE_ONE_FIXED_LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_FACTORY_OTP_WHITE_SUCCESSOR_ONCE",
            pack.EXECUTE_INTENT,
            1,
        ),
        ('\\"source_main_nvs_boot_key\\":\\"boot_lh1\\"',
         '\\"source_main_nvs_boot_key\\":\\"boot_pbgfr1\\"', 1),
        ('\\"accepted_source_complete_ordinals\\":[5]',
         '\\"accepted_source_complete_ordinals\\":[3]', 1),
        ("source_main_completed_h2_only", "source_main_completed_r3_only", 1),
    )
    for old, new, count in replacements:
        if payload.count(old) != count:
            raise ReconstructionWhiteCodegenError(
                f"frozen white replacement surface differs: {old}"
            )
        payload = payload.replace(old, new)
    return payload


def _render_driver() -> str:
    return (
        "// Frozen shared factory-OTP WF23 white driver.\n"
        "#include <SPI.h>\n"
        '#include "../../src/epd_driver.cpp"\n'
    )


def render_sources(report: Mapping[str, Any]) -> dict[str, bytes]:
    if report.get("contract", {}).get("accepted_source_ordinals") != [3]:
        raise ReconstructionWhiteCodegenError("R3-only white report required")
    return {
        MAIN_NAME: _render_main().encode("utf-8"),
        DRIVER_NAME: _render_driver().encode("utf-8"),
        IDENTITY_NAME: _render_identity(report).encode("utf-8"),
    }


def generate() -> dict[str, Any]:
    report = pack.build_report(verify_artifacts=False)
    sources = render_sources(report)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    evidence: dict[str, dict[str, Any]] = {}
    for name, payload in sources.items():
        path = OUTPUT_ROOT / name
        path.write_bytes(payload)
        evidence[name] = {
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "bytes": len(payload),
            "sha256": _sha(payload),
        }
    return {
        "result": "PASS",
        "contract_id": report["contract_id"],
        "accepted_source_ordinals": [3],
        "generated": evidence,
    }


if __name__ == "__main__":
    print(json.dumps(generate(), indent=2, sort_keys=True))
