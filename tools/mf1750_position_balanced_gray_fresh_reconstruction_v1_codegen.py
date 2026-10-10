#!/usr/bin/env python3
"""Generate isolated reconstruction firmware sources after every gate seals.

The generator is deliberately unusable with the provisional template report.
It preserves the reviewed F1 V3 transport implementation byte-for-byte at the
source boundary while replacing only campaign identity, action cardinality,
and the compiled three-action table.
"""

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
    mf1750_position_balanced_gray_fresh_reconstruction_v1_pack as pack,
)


class FreshReconstructionCodegenError(RuntimeError):
    """Raised before any unsealed or drifted source can be generated."""


SOURCE_MAIN = (
    REPO_ROOT
    / "src/ec5_runtime_lut_luma_gray_mechanism_position_balanced_v3_main.cpp"
)
SOURCE_MAIN_BYTES = 39_590
SOURCE_MAIN_SHA256 = (
    "50f5d0913c07f1c07550ce1589a3de2b15de4a10de4ad138b0f47b98afbca749"
)
SOURCE_DRIVER = (
    REPO_ROOT
    / "src/ec5_runtime_lut_luma_gray_mechanism_position_balanced_v3_epd_driver.cpp"
)
SOURCE_DRIVER_SHA256 = (
    "2429001d67ade0bc27143b41aa566d1eeec65b3d905796269d30e75205aeb551"
)
OUTPUT_ROOT = REPO_ROOT / ".pio" / pack.CONFIG.generated_src_root
MAIN_NAME = "ec5_position_balanced_gray_fresh_reconstruction_v1_main.cpp"
DRIVER_NAME = "ec5_position_balanced_gray_fresh_reconstruction_v1_epd_driver.cpp"
IDENTITY_NAME = "ec5_position_balanced_gray_fresh_reconstruction_v1_identity.inc"
CONFIG_NAME = "ec5_position_balanced_gray_fresh_reconstruction_v1_main_config.inc"
NEW_BUILD_MACRO = "MF1750_POSITION_BALANCED_GRAY_FRESH_RECONSTRUCTION_V1_BUILD"
OLD_BUILD_MACRO = (
    "MF1750_RUNTIME_LUT_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3_BUILD"
)
NAMESPACE = "mf1750_position_balanced_gray_fresh_reconstruction_v1"


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_frozen(path: Path, *, size: int | None, sha256: str) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise FreshReconstructionCodegenError(f"frozen source missing: {path}")
    payload = path.read_bytes()
    if (size is not None and len(payload) != size) or _sha(payload) != sha256:
        raise FreshReconstructionCodegenError(f"frozen source changed: {path}")
    return payload


def _cxx(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _render_identity(report: Mapping[str, Any]) -> str:
    return f"""#pragma once

namespace {NAMESPACE} {{

static constexpr char kVariantKey[] = {_cxx(pack.VARIANT_KEY)};
static constexpr char kBuildTag[] = {_cxx(pack.BUILD_TAG)};
static constexpr char kTestId[] = {_cxx(pack.TEST_ID)};
static constexpr char kCampaignId[] = {_cxx(pack.CAMPAIGN_ID)};
static constexpr char kContractId[] = {_cxx(str(report['contract_id']))};
static constexpr char kNvsNamespace[] = {_cxx(pack.NVS_NAMESPACE)};
static constexpr char kNvsBootKey[] = {_cxx(pack.NVS_BOOT_KEY)};

}}  // namespace {NAMESPACE}
"""


def _action_cpp(action: Mapping[str, Any]) -> str:
    role = action["driver_role"]
    prior = (
        "nullptr"
        if action["prior_static_action_id"] is None
        else _cxx(str(action["prior_static_action_id"]))
    )
    histogram = ", ".join(str(value) for value in action["frame"]["histogram"])
    return f"""    PBGFR1_ACTION({action['ordinal']}, EpdChromaGridRole::{role},
                  {_cxx(str(action['role']))},
                  {_cxx(str(action['branch']))},
                  {_cxx(str(action['descriptor_id']))},
                  {_cxx(str(action['action_id']))},
                  {prior},
                  {_cxx(str(action['frame']['sha256']))},
                  {_cxx(str(action['cs1_dtm']['sha256']))},
                  {_cxx(str(action['cs2_dtm']['sha256']))},
                  0x{action['frame']['fnv1a']:08X}UL,
                  0x{action['cs1_dtm']['fnv1a']:08X}UL,
                  0x{action['cs2_dtm']['fnv1a']:08X}UL,
                  {histogram})"""


def _render_main_config(report: Mapping[str, Any]) -> str:
    actions = report["actions"]
    marker = (
        "MF1750_EC5_PBGFR1_COMPILED_IDENTITY_V1|"
        f"CONTRACT={report['contract_id']}|"
        + "|".join(f"R{item['ordinal']}={item['action_id']}" for item in actions)
    )
    geometry = report["contract"]["geometry"]
    history = {
        **geometry,
        "global_header_sequence": [item["global_header"] for item in actions],
        "source_code": 7,
        "middle_codes": list(range(8)),
        "target_codes": [3, 7],
        "g4_present": False,
        "optical_frame_and_controller_dtm_byte_identical_to_first_f1_v3": True,
        "same_geometry_and_camera_settings_as_first_construction_required": True,
        "spatial_dither": False,
        "full_screen_global_refresh": True,
        "partial_refresh": False,
        "campaign_boot_binding_key": pack.NVS_BOOT_KEY,
        "device_enforced_same_boot": True,
        "reboot_resume_allowed": False,
    }
    capabilities = {
        "partial_refresh": False,
        "window_refresh": False,
        "command_0x83": False,
        "command_0x86": False,
        "unknown_commands": False,
        "mid_refresh_power_cut": False,
        "spi_frequency_sweep": False,
        "full_screen_global_refresh": True,
        "history_brightness_screening": True,
        "same_geometry_camera_comparison_required": True,
        "true_neutral_gray_claimed": False,
        "qualified_colors": 0,
        "qualified_gray_levels": 0,
        "qualified_brightness_levels": 0,
        "candidate_only": True,
        "independent_fresh_white_containment_required": True,
        "busy_qualified_arm_execute_dispatch": True,
        "device_enforced_same_boot": True,
        "g4_present": False,
        "autochain": False,
        "runtime_code7_used_as_white": False,
    }
    source = report["contract"]["source_authority"]
    source_tuple = source.get("source_tuple", {})
    profile_source = (
        "completed_position_balanced_gray_hold_successor_factory_OTP_white_"
        "plus_claim_relay_off_48MP_camera_relative_clean_white_review_"
        f"source_action_{source_tuple.get('action_id', 'UNSEALED')}"
    )
    action_rows = ",\n".join(_action_cpp(action) for action in actions)
    history_json = json.dumps(history, sort_keys=True, separators=(",", ":"))
    capability_json = json.dumps(
        capabilities, sort_keys=True, separators=(",", ":")
    )[1:-1]
    return f"""#include "{IDENTITY_NAME}"

static constexpr const char *kCompiledIdentityMarker = {_cxx(marker)};

namespace pbgfr1 = {NAMESPACE};

static constexpr const char *kClassification = {_cxx(pack.CLASSIFICATION)};
static constexpr const char *kProfileSource = {_cxx(profile_source)};
static constexpr const char *kIdentityRevision = {_cxx(pack.IDENTITY_REVISION)};
static constexpr const char *kDeviceApiVersion = {_cxx(pack.DEVICE_API_VERSION)};
static constexpr const char *kLayoutId = pbgfr1::kVariantKey;
static constexpr const char *kBuildTag = pbgfr1::kBuildTag;
static constexpr const char *kBootLabel =
    "EC5 position-balanced gray fresh reconstruction V1";
static constexpr const char *kTestId = pbgfr1::kTestId;
static constexpr const char *kCampaignId = pbgfr1::kCampaignId;
static constexpr const char *kContractId = pbgfr1::kContractId;
static constexpr const char *kVersionKind =
    "mf1750-position-balanced-gray-fresh-reconstruction-v1-version";
static constexpr const char *kManifestKind =
    "mf1750-position-balanced-gray-fresh-reconstruction-v1-manifest";
static constexpr const char *kStatusKind =
    "mf1750-position-balanced-gray-fresh-reconstruction-v1-status";
static constexpr const char *kReportKind =
    "mf1750-position-balanced-gray-fresh-reconstruction-v1-report";
static constexpr const char *kBaselineRole = "G1_ACTIVE_C7_SOURCE";

static constexpr const char *kHistoryLayoutJson = {_cxx(history_json)};
static constexpr const char *kCampaignCapabilitiesJson =
    {_cxx(capability_json)};

static constexpr const char *kNvsNamespace = pbgfr1::kNvsNamespace;
static constexpr const char *kNvsKey = {_cxx(pack.NVS_KEY)};
static constexpr const char *kNvsBootKey = pbgfr1::kNvsBootKey;
static constexpr const char *kVersionRoute = {_cxx(pack.BASE_ROUTE + '/version')};
static constexpr const char *kManifestRoute = {_cxx(pack.BASE_ROUTE + '/manifest')};
static constexpr const char *kStatusRoute = {_cxx(pack.BASE_ROUTE + '/status')};
static constexpr const char *kReportRoute = {_cxx(pack.BASE_ROUTE + '/report')};
static constexpr const char *kArmRoute = {_cxx(pack.BASE_ROUTE + '/arm')};
static constexpr const char *kExecuteRoute = {_cxx(pack.BASE_ROUTE + '/execute')};

static constexpr const char *kBuildHeader = "X-EC5-Build-Tag";
static constexpr const char *kTestHeader = "X-EC5-Test-Id";
static constexpr const char *kCampaignHeader = "X-EC5-Campaign-Id";
static constexpr const char *kActionHeader = "X-EC5-Action-Id";
static constexpr const char *kOrdinalHeader = "X-EC5-Ordinal";
static constexpr const char *kDescriptorHeader = "X-EC5-Descriptor-Id";
static constexpr const char *kBootNonceHeader = "X-EC5-Boot-Nonce";
static constexpr const char *kArmNonceHeader = "X-EC5-Arm-Nonce";
static constexpr const char *kIntentHeader = "X-EC5-Intent";
static constexpr const char *kArmIntent = {_cxx(pack.ARM_INTENT)};
static constexpr const char *kExecuteIntent = {_cxx(pack.EXECUTE_INTENT)};

#define PBGFR1_ACTION(ORDINAL, DRIVER_ROLE, ROLE, BRANCH, DESCRIPTOR, ACTION, PRIOR, FRAME_SHA, CS1_SHA, CS2_SHA, FRAME_FNV, CS1_FNV, CS2_FNV, H0, H1, H2, H3, H4, H5, H6, H7) \\
  {{ORDINAL, DRIVER_ROLE, ROLE, 1, BRANCH, DESCRIPTOR, ACTION, PRIOR, FRAME_SHA, CS1_SHA, CS2_SHA, FRAME_FNV, CS1_FNV, CS2_FNV, {{H0, H1, H2, H3, H4, H5, H6, H7}}}}

static constexpr ActionDescriptor kActions[] = {{
{action_rows},
}};

#undef PBGFR1_ACTION
"""


def _render_main() -> str:
    payload = _read_frozen(
        SOURCE_MAIN, size=SOURCE_MAIN_BYTES, sha256=SOURCE_MAIN_SHA256
    ).decode("utf-8")
    replacements = {
        OLD_BUILD_MACRO: NEW_BUILD_MACRO,
        "static constexpr uint8_t kActionCount = 4;":
            "static constexpr uint8_t kActionCount = 3;",
        '#include "ec5_runtime_lut_luma_gray_mechanism_position_balanced_v3_main_config.inc"':
            f'#include "{CONFIG_NAME}"',
    }
    for old, new in replacements.items():
        expected = 1
        if payload.count(old) != expected:
            raise FreshReconstructionCodegenError(
                f"frozen main replacement surface differs: {old}"
            )
        payload = payload.replace(old, new)
    return payload


def _render_driver() -> str:
    _read_frozen(SOURCE_DRIVER, size=None, sha256=SOURCE_DRIVER_SHA256)
    relative = Path("../../src") / SOURCE_DRIVER.name
    return (
        "// Frozen F1 V3 optical transport; campaign identity lives in main.\n"
        "#include <SPI.h>\n"
        f'#include "{relative.as_posix()}"\n'
    )


def render_sources(report: Mapping[str, Any]) -> dict[str, bytes]:
    """Pure renderer used by tests; callers must not compile template output."""

    if len(report.get("actions", [])) != 3 or report.get("contract", {}).get(
        "g4_present"
    ) is not False:
        raise FreshReconstructionCodegenError("three-action report required")
    return {
        MAIN_NAME: _render_main().encode("utf-8"),
        DRIVER_NAME: _render_driver().encode("utf-8"),
        IDENTITY_NAME: _render_identity(report).encode("utf-8"),
        CONFIG_NAME: _render_main_config(report).encode("utf-8"),
    }


def generate() -> dict[str, Any]:
    """Write generated sources only after both external authorities seal."""

    report = pack.build_report()
    sources = render_sources(report)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    written: dict[str, dict[str, Any]] = {}
    for name, payload in sources.items():
        path = OUTPUT_ROOT / name
        path.write_bytes(payload)
        written[name] = {
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "bytes": len(payload),
            "sha256": _sha(payload),
        }
    return {
        "result": "PASS",
        "sealed_report_required": True,
        "contract_id": report["contract_id"],
        "generated": written,
        "frozen_source_main_sha256": SOURCE_MAIN_SHA256,
        "frozen_source_driver_sha256": SOURCE_DRIVER_SHA256,
    }


if __name__ == "__main__":
    print(json.dumps(generate(), indent=2, sort_keys=True))
