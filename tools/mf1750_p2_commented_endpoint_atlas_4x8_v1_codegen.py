#!/usr/bin/env python3
"""Generate isolated P2-C firmware sources from frozen P1 mechanics."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_p2_commented_endpoint_atlas_4x8_v1_pack as pack  # noqa: E402


PREFIX = "ec5_p2_commented_endpoint_atlas_4x8_v1"
OUTPUT_ROOT = REPO_ROOT / ".pio/generated-p2-commented-endpoint-atlas-4x8-v1"
TEMPLATES = {
    "program.inc": (
        REPO_ROOT / "src/ec5_p1_active_endpoint_atlas_4x8_v1_program.inc",
        44_810,
        "fdad0f85503861c49609598685357a63889793a33bd8b79a6645800b48c19bbd",
    ),
    "driver.inc": (
        REPO_ROOT / "src/ec5_p1_active_endpoint_atlas_4x8_v1_driver.inc",
        39_164,
        "a62b5562e568345696739ee35e6d44e6307c6e8181f626203459d4bd9f0a6bf3",
    ),
}


class P2CodegenError(RuntimeError):
    pass


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _cxx(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _frozen(name: str) -> str:
    path, size, digest = TEMPLATES[name]
    payload = path.read_bytes()
    if len(payload) != size or _sha(payload) != digest:
        raise P2CodegenError(f"frozen P1 {name} changed")
    return payload.decode("utf-8")


def _replace_exact(value: str, old: str, new: str, count: int) -> str:
    if value.count(old) != count:
        raise P2CodegenError(f"replacement surface differs: {old}")
    return value.replace(old, new)


def _render_identity(report: Mapping[str, Any]) -> str:
    action = report["actions"][0]
    hist = ", ".join(str(item) for item in action["frame"]["histogram"])
    rows = ",\n".join(
        "    {" + ", ".join(str(code) for code in row) + "}"
        for row in pack.CODE_ROWS
    )
    return f'''#pragma once

namespace mf1750_p2_commented_endpoint_atlas_4x8_v1 {{
struct Window {{ uint16_t x; uint16_t y; uint16_t width; uint16_t height; uint8_t cs1Code; uint8_t cs2Code; }};
struct ActionIdentity {{ const char *role; const char *branch; const char *descriptorId; const char *actionId; const char *frameSha256; const char *cs1DtmSha256; const char *cs2DtmSha256; uint32_t frameFnv1a; uint32_t cs1DtmFnv1a; uint32_t cs2DtmFnv1a; uint32_t histogram[8]; }};
static constexpr uint8_t kRoleCount = 1, kRoleIdentityCount = 1, kSeparatorCode = 7, kTargetCode = 0, kFactoryWhiteFrameFillByte = 0x11, kPartialWindowCommand = 0x83, kPartialWindowPayloadBytes = 9, kPartialWindowMode = 0x01;
static constexpr bool kCs2VerticalMirror = false, kSeparateCsWindowCommands = true, kPtlwYEndOneMore = false;
static constexpr uint8_t kGridRows = 4, kGridColumns = 8;
static constexpr uint16_t kGridX0 = 20, kGridY0 = 44, kGridYByRow[4] = {{44, 180, 316, 452}}, kCellWidth = 52, kCellHeight = 100, kGapX = 8, kGapY = 36, kGridX1Exclusive = 492, kGridY1Exclusive = 552;
static constexpr uint8_t kCodeRows[4][8] = {{
{rows}
}};
static constexpr char kActiveProfileId[] = "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_ACTIVE535";
static constexpr char kCommentedProfileId[] = {_cxx(action['profile_id'])};
static constexpr char kVariantKey[] = {_cxx(pack.VARIANT_KEY)};
static constexpr char kBuildTag[] = {_cxx(pack.BUILD_TAG)};
static constexpr char kTestId[] = {_cxx(pack.TEST_ID)};
static constexpr char kCampaignId[] = {_cxx(pack.CAMPAIGN_ID)};
static constexpr char kContractId[] = {_cxx(report['contract_id'])};
static constexpr char kNvsNamespace[] = {_cxx(pack.NVS_NAMESPACE)};
static constexpr char kNvsBootKey[] = {_cxx(pack.NVS_BOOT_KEY)};
// P2-C has one immutable commented tuple; no runtime selector may activate
// the legacy active tuple.
static constexpr bool kCommentedProfileCompileTimeOnly = true;
static_assert(kCommentedProfileCompileTimeOnly, "P2-C active-profile selection is forbidden");
static constexpr Window kWindows[1] = {{{{20, 44, 52, 100, 0, 0}}}};
static constexpr ActionIdentity kActions[1] = {{{{
    {_cxx(action['role'])}, {_cxx(action['branch'])}, {_cxx(action['descriptor_id'])},
    {_cxx(action['action_id'])}, {_cxx(action['frame']['sha256'])},
    {_cxx(action['cs1_dtm']['sha256'])}, {_cxx(action['cs2_dtm']['sha256'])},
    0x{action['frame']['fnv1a']:08X}UL, 0x{action['cs1_dtm']['fnv1a']:08X}UL,
    0x{action['cs2_dtm']['fnv1a']:08X}UL, {{{hist}}}
}}}};
static_assert(kGridX1Exclusive <= 512 && kGridY1Exclusive <= 600 && (kGridX0 & 1U) == 0 && (kCellWidth & 1U) == 0 && (kGapX & 1U) == 0 && !kCs2VerticalMirror, "P2-C packed-grid geometry changed");
}}  // namespace mf1750_p2_commented_endpoint_atlas_4x8_v1
'''


def _render_config(report: Mapping[str, Any]) -> str:
    action = report["actions"][0]
    return f'''#include "{PREFIX}_identity.inc"
namespace p2c = mf1750_p2_commented_endpoint_atlas_4x8_v1;
static constexpr const char *kClassification = {_cxx(pack.CLASSIFICATION)};
static constexpr const char *kProfileSource = "legacy_complete_535_commented_symmetric_controller_tuple";
static constexpr const char *kIdentityRevision = {_cxx(pack.IDENTITY_REVISION)};
static constexpr const char *kDeviceApiVersion = {_cxx(pack.DEVICE_API_VERSION)};
static constexpr const char *kLayoutId = p2c::kVariantKey;
static constexpr const char *kBuildTag = p2c::kBuildTag;
static constexpr const char *kBootLabel = "EC5 P2 commented endpoint atlas 4x8 V1";
static constexpr const char *kBootSummary = "One fresh one-shot complete commented-profile C/C 4x8 endpoint atlas";
static constexpr const char *kTestId = p2c::kTestId;
static constexpr const char *kCampaignId = p2c::kCampaignId;
static constexpr const char *kContractId = p2c::kContractId;
static constexpr const char *kVersionKind = "mf1750-ec5-p2-commented-endpoint-atlas-4x8-v1-version";
static constexpr const char *kManifestKind = "mf1750-ec5-p2-commented-endpoint-atlas-4x8-v1-manifest";
static constexpr const char *kStatusKind = "mf1750-ec5-p2-commented-endpoint-atlas-4x8-v1-status";
static constexpr const char *kReportKind = "mf1750-ec5-p2-commented-endpoint-atlas-4x8-v1-report";
static constexpr const char *kBaselineRole = "EXTERNAL_FRESH_FACTORY_OTP_WHITE_BEFORE_AND_INDEPENDENT_SUCCESSOR_AFTER_REQUIRED";
static constexpr const char *kExternalWhiteAnchorJson = "\\\"external_containment\\\":{{\\\"outside_campaign\\\":true,\\\"factory_otp_white_before_required\\\":true,\\\"factory_otp_white_after_required\\\":true,\\\"successor_identity_bound_after_main_artifact_seal\\\":true,\\\"post_white_clean_visual_gate_required\\\":true,\\\"white_actions_in_campaign\\\":0}}";
static constexpr const char *kHistoryLayoutJson = "{{\\\"controller_count\\\":2,\\\"controller_width\\\":512,\\\"height\\\":600,\\\"grid_rows\\\":4,\\\"grid_columns_per_controller\\\":8,\\\"row_codes\\\":[[0,1,2,3,4,5,6,7],[4,5,6,7,0,1,2,3],[1,2,3,4,5,6,7,0],[5,6,7,0,1,2,3,4]],\\\"grid_x0_local\\\":20,\\\"grid_y_by_row\\\":[44,180,316,452],\\\"grid_x1_local_exclusive\\\":492,\\\"grid_y1_exclusive\\\":552,\\\"cell_width\\\":52,\\\"cell_height\\\":100,\\\"gap_x\\\":8,\\\"gap_y\\\":36,\\\"background_code\\\":7,\\\"border\\\":false,\\\"same_layout_both_controllers\\\":true,\\\"controller_dtm_byte_identical\\\":true,\\\"cs2_position_mirrored\\\":false,\\\"spatial_dither\\\":false,\\\"fresh_one_shot\\\":true,\\\"source_history_actions\\\":0,\\\"middle_history_actions\\\":0,\\\"identical_target_repeat_actions\\\":0,\\\"factory_otp_white_ordinals\\\":[],\\\"runtime_lut_ordinals\\\":[1],\\\"one_visible_refresh_per_action\\\":true,\\\"samples_per_code_per_controller_per_frame\\\":4,\\\"qualified_colours\\\":0,\\\"qualified_lightness_levels\\\":0,\\\"commented_global_tuple_id\\\":\\\"{action['global_tuple_id']}\\\"}}";
static constexpr const char *kCampaignCapabilitiesJson = "\\\"partial_refresh\\\":false,\\\"window_refresh\\\":false,\\\"command_0x83\\\":false,\\\"command_0x86\\\":false,\\\"unknown_commands\\\":false,\\\"mid_refresh_power_cut\\\":false,\\\"spi_frequency_sweep\\\":false,\\\"full_screen_global_refresh\\\":true,\\\"fresh_one_shot_endpoint_atlas\\\":true,\\\"complete_profile_tuple\\\":true,\\\"position_balanced_atlas\\\":true,\\\"same_palette_hold_probe\\\":false,\\\"cross_palette_hold_probe\\\":false,\\\"local_hold_claimed\\\":false,\\\"colour_qualification\\\":false,\\\"lightness_qualification\\\":false,\\\"history_sequence\\\":false,\\\"identical_target_repeat\\\":false,\\\"busy_qualified_arm_execute_dispatch\\\":true,\\\"main_campaign_resume_after_containment\\\":false,\\\"device_enforced_same_boot\\\":true";
static constexpr const char *kNvsNamespace = p2c::kNvsNamespace;
static constexpr const char *kNvsKey = {_cxx(pack.NVS_KEY)};
static constexpr const char *kNvsBootKey = p2c::kNvsBootKey;
static constexpr const char *kVersionRoute = "{pack.BASE_ROUTE}/version";
static constexpr const char *kManifestRoute = "{pack.BASE_ROUTE}/manifest";
static constexpr const char *kStatusRoute = "{pack.BASE_ROUTE}/status";
static constexpr const char *kReportRoute = "{pack.BASE_ROUTE}/report";
static constexpr const char *kArmRoute = "{pack.BASE_ROUTE}/arm";
static constexpr const char *kExecuteRoute = "{pack.BASE_ROUTE}/execute";
static constexpr const char *kBuildHeader = "X-EC5-Build-Tag", *kTestHeader = "X-EC5-Test-Id", *kCampaignHeader = "X-EC5-Campaign-Id", *kActionHeader = "X-EC5-Action-Id", *kOrdinalHeader = "X-EC5-Ordinal", *kDescriptorHeader = "X-EC5-Descriptor-Id", *kBootNonceHeader = "X-EC5-Boot-Nonce", *kArmNonceHeader = "X-EC5-Arm-Nonce", *kIntentHeader = "X-EC5-Intent";
static constexpr const char *kArmIntent = "ARM_ONE_FIXED_P2_COMMENTED_ENDPOINT_ATLAS_NOT_HARDWARE_AUTHORIZATION";
static constexpr const char *kExecuteIntent = "EXECUTE_ONE_ARMED_P2_COMMENTED_ENDPOINT_ATLAS_ONCE";
static constexpr ActionDescriptor kActions[] = {{{{1, EpdChromaGridRole::Source, {_cxx(action['role'])}, 1, {_cxx(action['branch'])}, {_cxx(action['descriptor_id'])}, {_cxx(action['action_id'])}, nullptr, {_cxx(action['frame']['sha256'])}, {_cxx(action['cs1_dtm']['sha256'])}, {_cxx(action['cs2_dtm']['sha256'])}, 0x{action['frame']['fnv1a']:08X}UL, 0x{action['cs1_dtm']['fnv1a']:08X}UL, 0x{action['cs2_dtm']['fnv1a']:08X}UL, {{{', '.join(str(item) for item in action['frame']['histogram'])}}}}}}};
'''


def render_sources(report: Mapping[str, Any]) -> dict[str, bytes]:
    old_prefix = "ec5_p1_active_endpoint_atlas_4x8_v1"
    old_macro = "MF1750_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_BUILD"
    new_macro = "MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_BUILD"
    program = _frozen("program.inc")
    program = _replace_exact(program, old_macro, new_macro, 2)
    program = _replace_exact(program, old_prefix, PREFIX, 1)
    program = _replace_exact(
        program,
        "const bool active = action.driverRole == EpdChromaGridRole::Source;",
        "const bool active = false;  // P2-C is frozen to the commented tuple.",
        1,
    )
    driver = _frozen("driver.inc")
    driver = driver.replace(old_macro, new_macro)
    driver = _replace_exact(driver, f'{old_prefix}_identity.inc', f'{PREFIX}_identity.inc', 1)
    driver = _replace_exact(
        driver,
        "namespace ph = mf1750_p1_active_endpoint_atlas_4x8_v1;",
        "namespace ph = mf1750_p2_commented_endpoint_atlas_4x8_v1;",
        1,
    )
    # Keep the generic frozen helper for other campaigns, but make the P2
    # facade fail closed if a future call site ever passes ``false``.  The
    # normal P2 call is compiled with ``true`` below; this guard ensures an
    # accidental active-profile selector cannot silently reach the panel.
    driver = _replace_exact(
        driver,
        "bool phApplyRuntimeLutGlobalConfig(bool useCommentedGlobal = false) {",
        """bool phApplyRuntimeLutGlobalConfig(bool useCommentedGlobal = false) {
#if defined(MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_BUILD)
  if (!useCommentedGlobal) return false;  // P2-C commented tuple is immutable.
#endif""",
        1,
    )
    profile_gate = """#if defined(MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_BUILD) || \\
    defined(MF1750_RUNTIME_LUT_SAME_R20_PARITY_4X8_V2_BUILD)
  if (role == EpdChromaGridRole::Mid) useCommentedGlobal = true;"""
    driver = _replace_exact(
        driver,
        profile_gate,
        """#if defined(MF1750_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_BUILD)
  useCommentedGlobal = true;
#elif defined(MF1750_RUNTIME_LUT_SAME_R20_PARITY_4X8_V2_BUILD)
  if (role == EpdChromaGridRole::Mid) useCommentedGlobal = true;""",
        1,
    )
    return {
        f"{PREFIX}_main.cpp": f'#include "{PREFIX}_program.inc"\n'.encode(),
        f"{PREFIX}_epd_driver.cpp": (
            '#include "ec5_chroma_grid_epd_driver.h"\n\n'
            '#include <SPI.h>\n#include <esp_heap_caps.h>\n'
            '#include <mbedtls/sha256.h>\n\n'
            '#include "../../src/epd_driver.cpp"\n'
            f'#include "{PREFIX}_driver.inc"\n'
        ).encode(),
        f"{PREFIX}_program.inc": program.encode(),
        f"{PREFIX}_driver.inc": driver.encode(),
        f"{PREFIX}_identity.inc": _render_identity(report).encode(),
        f"{PREFIX}_main_config.inc": _render_config(report).encode(),
    }


def generate() -> dict[str, Any]:
    report = pack.build_report()
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
    return {"result": "PASS", "contract_id": report["contract_id"], "generated": evidence}


if __name__ == "__main__":
    print(json.dumps(generate(), indent=2, sort_keys=True))
