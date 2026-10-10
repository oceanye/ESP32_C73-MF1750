#!/usr/bin/env python3
"""Prepare, compile and verify isolated three-action lightness firmware; no live I/O."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.static_photo import lightness_history as algorithm  # noqa: E402
from host.static_photo import lightness_test as optical  # noqa: E402
from host.static_photo.common import attach_integrity, verify_integrity  # noqa: E402
from tools.mf1750_runtime_lut_same_r20_parity_v1_pack import profile  # noqa: E402

PREFIX = "ec5_lightness_history_v1"
NAMESPACE = "mf1750_lightness_history_v1"
MACRO = "MF1750_LIGHTNESS_HISTORY_V1_BUILD"
OLD = "ec5_runtime_lut_luma_gray_mechanism_position_balanced_v3"
OLD_MACRO = "MF1750_RUNTIME_LUT_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3_BUILD"
CAMPAIGN = "EC5_LIGHTNESS_HISTORY_V1_20260911"
BUILD_TAG = "MF1750_EC5_LIGHTNESS_HISTORY_V1_2026-09-11"
ROUTE = "/api/ec5/lightness-history-v1"
PINNED = {
    f"src/{OLD}_main.cpp": "50f5d0913c07f1c07550ce1589a3de2b15de4a10de4ad138b0f47b98afbca749",
    f"src/{OLD}_driver.inc": "80aaef1e08e95b6dcffdc41aca39fb8755ad38dba6bbbc787259b1885e1857e7",
    "src/epd_driver.cpp": "386acdd3e2fef3d22e4b97551330d310b86d1aafc5085df35a676e9b8dad2f6c",
    "src/epd_driver.h": "3bbddfe8893e3024b0d745b0342dd1be576ebb6be7017ef4704952636ad42343",
    "src/epd_config.h": "e8b13cf413192f344db27ec34491d0a764adb3a126173ac126c1774d418f1a8d",
    "src/ec5_chroma_grid_epd_driver.h": "d1788eb691b3dcaf5bd62a82721de8032f20bbb29e5cf52ff97e7ec4d03e0b6a",
    "src/generated/spd1657_legacy_535_reference.inc": "cb40342fb212e232d1cfe789f60ccba9823bb0e35148f5cf916681e0c8991881",
}
SOURCE_WHITE = {
    "campaign_id": "EC5_P2_COMMENTED_ENDPOINT_ATLAS_4X8_V1_WHITE_SUCCESSOR_V1",
    "action_id": "677c37c9962f507e2110f644735c1a1c4be87286073b70d1babe8d42856e3b19",
    "firmware_sha256": "acf27e1358f869b4f5663e8a84ad4f38ab047557c90a9d64c4fa44c66c079277",
    "nvs_namespace": "p2catwsv1",
    "nvs_key": "used_p2cw1",
    "complete_cursor": 2,
    "terminal_evidence": None,
    "clean_white_review": None,
    "nvs_is_not_optical_or_electrical_proof": True,
}


def bind(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": algorithm.digest(data)}


def write_new(path, value):
    path = Path(path)
    if isinstance(value, dict):
        value = (
            json.dumps(
                value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
            )
            + "\n"
        )
    data = value.encode("utf-8") if isinstance(value, str) else value
    with path.open("xb") as stream:
        stream.write(data)


def frozen(path):
    data = (ROOT / path).read_bytes()
    if algorithm.digest(data) != PINNED[path]:
        raise ValueError(f"pinned dependency changed: {path}")
    return data.decode("utf-8")


def replace_once(value, before, after):
    if value.count(before) != 1:
        raise ValueError(f"template surface changed: {before[:100]}")
    return value.replace(before, after)


def replace_function(value, start, end, replacement):
    a = value.index(start)
    b = value.index(end, a)
    return value[:a] + replacement + "\n\n" + value[b:]


def contract():
    inputs = [bind(ROOT / p) for p in PINNED]
    for item, sha in zip(inputs, PINNED.values(), strict=True):
        if item["sha256"] != sha:
            raise ValueError(f"pinned dependency changed: {item['path']}")
    implementation = {
        p: bind(ROOT / p)["sha256"]
        for p in (
            "tools/mf1750_lightness_history_firmware.py",
            "host/static_photo/lightness_history.py",
            "host/static_photo/lightness_test.py",
        )
    }
    prior = None
    actions = []
    for ordinal, (stage, header) in enumerate(
        zip(algorithm.STAGES, algorithm.HEADERS, strict=True), 1
    ):
        frame = algorithm.frame(stage)
        p = profile(header)
        item = {
            "ordinal": ordinal,
            "stage": stage,
            "role": "LH1_" + stage,
            "driver_role": ("Source", "Mid", "Target")[ordinal - 1],
            "branch": "LH1_SYMMETRIC_" + stage,
            "global_header": header,
            "profile_id": p["id"],
            "profile": p,
            "profile_sha256": algorithm.digest(algorithm.canonical(p)),
            "prior_action_id": prior,
            "frame": algorithm.payload_identity(frame, True),
            "cs1_dtm": algorithm.payload_identity(
                algorithm.controller_stream(frame, 0)
            ),
            "cs2_dtm": algorithm.payload_identity(
                algorithm.controller_stream(frame, 1)
            ),
            "source_state": "FRESH_P2_FACTORY_WHITE"
            if ordinal == 1
            else "LH1_" + algorithm.STAGES[ordinal - 2],
            "target_state": "LH1_" + stage,
            "visible_refresh_count": 1,
            "waveform_internal_phase": "OPAQUE",
        }
        item["descriptor_id"] = algorithm.digest(
            algorithm.canonical(
                {
                    "campaign": CAMPAIGN,
                    "action": item,
                    "source_white": SOURCE_WHITE,
                    "implementation": implementation,
                }
            )
        )
        item["action_id"] = algorithm.digest(
            f"{CAMPAIGN}|{ordinal}|{item['descriptor_id']}".encode()
        )
        prior = item["action_id"]
        actions.append(item)
    body = {
        "kind": "mf1750-lightness-history-firmware-contract-v1",
        "algorithm_id": algorithm.TEST_ID,
        "campaign_id": CAMPAIGN,
        "build_tag": BUILD_TAG,
        "base_route": ROUTE,
        "nvs": {"namespace": "lhist_v1", "cursor": "cur_lh1", "boot": "boot_lh1"},
        "source_white": deepcopy(SOURCE_WHITE),
        "actions": actions,
        "recipes": algorithm.recipes(),
        "action_count": 3,
        "level_counts": [3, 5, 10],
        "recipes_per_target": 8,
        "level_count_is_refresh_count": False,
        "both_controllers_use_same_complete_tuple_per_action": True,
        "legacy_v3_asymmetric_r20_dispatch_reused": False,
        "old_boot_ip_com_or_white_anchor_reused": False,
        "thresholds": deepcopy(optical.THRESHOLDS),
        "identity_dependency_hashes": {p: sha for p, sha in PINNED.items()},
        "implementation_sha256": implementation,
        "startup_refresh": False,
        "autochain": False,
        "retry": False,
        "white_or_repeat_action": False,
        "raw_ingress": False,
        "frame_rate_sweep": False,
        "new_electrical_values": False,
        "post_flash_same_boot_diagnostic_required": True,
        "live_ready": False,
        "qualified_count": 0,
        "pending_physical_prerequisites": [
            "PWR/PLL/OTP-mode applicability review",
            "fresh white COMPLETE and visual evidence",
            "same-boot electrical and camera evidence",
            "separately sealed post-test white successor",
            "one-action field release",
        ],
    }
    body["contract_id"] = algorithm.digest(algorithm.canonical(body))
    return body


def identity_source(c):
    declarations = """#pragma once
#include <cstdint>
namespace mf1750_lightness_history_v1 {
struct Window { uint16_t x,y,width,height; uint8_t cs1Code,cs2Code; };
struct ActionIdentity { const char *role,*branch,*descriptorId,*actionId,*frameSha256,*cs1DtmSha256,*cs2DtmSha256; uint32_t frameFnv1a,cs1DtmFnv1a,cs2DtmFnv1a; uint32_t histogram[8]; };
static constexpr uint8_t kSeparatorCode=7,kSourceCode=7,kTargetCodes[2]={3,7},kFactoryWhiteFrameFillByte=0x11;
static constexpr uint8_t kPartialWindowCommand=0x83,kPartialWindowPayloadBytes=9,kPartialWindowMode=1;
static constexpr bool kCs2VerticalMirror=false,kSeparateCsWindowCommands=true,kPtlwYEndOneMore=false;
static constexpr uint8_t kGridRows=8,kGridColumns=8;
static constexpr uint16_t kGridX0=68,kGridY0=64,kCellWidth=40,kCellHeight=52,kGapX=8,kGapY=8,kGridX1Exclusive=444,kGridY1Exclusive=536;
static constexpr Window kWindows[]={{68,64,40,52,7,7}};
"""
    for label, cells in zip(("Cs1", "Cs2"), algorithm.placement(), strict=True):
        declarations += (
            f"static constexpr uint8_t kRecipeAtCell{label}[64]={{"
            + ",".join(map(str, cells))
            + "};\n"
        )
    declarations += "// Slot zero is unreachable: White and all repeat roles are rejected.\nstatic constexpr ActionIdentity kActions[4]={{},\n"
    for a in c["actions"]:
        fields = [a[k] for k in ("role", "branch", "descriptor_id", "action_id")] + [
            a[k]["sha256"] for k in ("frame", "cs1_dtm", "cs2_dtm")
        ]
        declarations += (
            "{"
            + ",".join(json.dumps(s) for s in fields)
            + ","
            + ",".join(
                f"0x{a[k]['fnv1a']:08X}UL" for k in ("frame", "cs1_dtm", "cs2_dtm")
            )
            + ",{"
            + ",".join(map(str, a["frame"]["histogram"]))
            + "}},\n"
        )
    return declarations + "};\n} // namespace\n"


def frame_source():
    return """#pragma once
#include <cstdint>
#include <cstring>
#include "ec5_lightness_history_v1_identity.inc"
namespace lh_frame {
inline bool build(unsigned role, uint8_t *frame, uint32_t histogram[8]) {
  using namespace mf1750_lightness_history_v1;
  if (role < 1 || role > 3 || !frame || !histogram) return false;
  std::memset(frame, 0x77, 307200);
  std::memset(histogram, 0, 8*sizeof(uint32_t));
  for (unsigned cs=0;cs<2;++cs) for(unsigned i=0;i<64;++i) {
    const unsigned recipe=(cs ? kRecipeAtCellCs2 : kRecipeAtCellCs1)[i];
    const uint8_t code=role==1 ? 7 : role==2 ? recipe%8 : kTargetCodes[recipe/8];
    const unsigned x=cs*512+kGridX0+(i%8)*(kCellWidth+kGapX);
    const unsigned y=kGridY0+(i/8)*(kCellHeight+kGapY);
    for(unsigned row=y;row<y+kCellHeight;++row)
      std::memset(frame+row*512+x/2,code*17,kCellWidth/2);
  }
  for(unsigned i=0;i<307200;++i) { ++histogram[frame[i]>>4]; ++histogram[frame[i]&15]; }
  return true;
}
} // namespace lh_frame
"""


def config_source(c):
    strings = {
        "kClassification": "EXPERIMENTAL_SAME_HUE_LIGHTNESS_SCREEN_ZERO_QUALIFIED",
        "kProfileSource": "complete_symmetric_L535_active_commented_tuples",
        "kIdentityRevision": "lightness-history-v1",
        "kDeviceApiVersion": "MF1750_LIGHTNESS_HISTORY_DEVICE_V1",
        "kLayoutId": "LH1_HISTORY_POSITION_BALANCED_8X8",
        "kBuildTag": BUILD_TAG,
        "kBootLabel": "MF1750 Lightness History V1",
        "kTestId": algorithm.TEST_ID,
        "kCampaignId": CAMPAIGN,
        "kContractId": c["contract_id"],
        "kBaselineRole": "LH1_SOURCE",
        "kNvsNamespace": "lhist_v1",
        "kNvsKey": "cur_lh1",
        "kNvsBootKey": "boot_lh1",
        "kArmIntent": "ARM_ONE_LIGHTNESS_HISTORY_ACTION",
        "kExecuteIntent": "EXECUTE_ONE_LIGHTNESS_HISTORY_ACTION_ONCE",
        "kCompiledIdentityMarker": "MF1750_LH1_COMPILED|CONTRACT="
        + c["contract_id"]
        + "|"
        + "|".join(f"S{a['ordinal']}={a['action_id']}" for a in c["actions"]),
    }
    for name in ("Version", "Manifest", "Status", "Report"):
        strings["k" + name + "Kind"] = "mf1750-lightness-history-v1-" + name.lower()
    for name in ("Version", "Manifest", "Status", "Report", "Arm", "Execute"):
        strings["k" + name + "Route"] = ROUTE + "/" + name.lower()
    for label, field in (
        ("Build", "Build-Tag"),
        ("Test", "Test-Id"),
        ("Campaign", "Campaign-Id"),
        ("Action", "Action-Id"),
        ("Ordinal", "Ordinal"),
        ("Descriptor", "Descriptor-Id"),
        ("BootNonce", "Boot-Nonce"),
        ("ArmNonce", "Arm-Nonce"),
        ("Intent", "Intent"),
    ):
        strings["k" + label + "Header"] = "X-EC5-" + field
    strings["kHistoryLayoutJson"] = json.dumps(
        {
            "recipes": 16,
            "cells_per_controller": 64,
            "positions_per_recipe": 4,
            "source_code": 7,
            "middle_codes": list(range(8)),
            "target_codes": [3, 7],
            "grid_rows": 8,
            "grid_columns": 8,
            "symmetric_tuple_sequence": ["AA", "CC", "AA"],
            "level_counts": [3, 5, 10],
            "recipes_per_target": 8,
            "spatial_dither": False,
            "source_white_observed": False,
        },
        separators=(",", ":"),
    )
    strings["kCampaignCapabilitiesJson"] = (
        '"partial_refresh":false,"full_screen_global_refresh":true,"lightness_qualification":false,"local_hold_claimed":false,"identical_target_repeat":false,"device_enforced_same_boot":true,"main_campaign_resume_after_containment":false'
    )
    source = (
        "\n".join(
            f"static constexpr const char *{k}={json.dumps(v)};"
            for k, v in strings.items()
        )
        + "\nstatic constexpr ActionDescriptor kActions[]={\n"
    )
    for a in c["actions"]:
        row = [
            str(a["ordinal"]),
            "EpdChromaGridRole::" + a["driver_role"],
            json.dumps(a["role"]),
            "1",
            json.dumps(a["branch"]),
            json.dumps(a["descriptor_id"]),
            json.dumps(a["action_id"]),
            json.dumps(a["prior_action_id"]) if a["prior_action_id"] else "nullptr",
        ]
        row += [json.dumps(a[k]["sha256"]) for k in ("frame", "cs1_dtm", "cs2_dtm")]
        row += [f"0x{a[k]['fnv1a']:08X}UL" for k in ("frame", "cs1_dtm", "cs2_dtm")]
        row += ["{" + ",".join(map(str, a["frame"]["histogram"])) + "}"]
        source += "{" + ",".join(row) + "},\n"
    return source + "};\n"


def source_gate_code():
    return """// NVS completion is necessary, not proof of retained optical/electrical state.
String lhRunId, lhSourceReview, lhPriorReview;
uint8_t lhQueuedOrdinal=0;
bool whiteSourceReady() {
  Preferences white;
  if (!white.begin("p2catwsv1", true)) return false;
  const bool ready=white.isKey("used_p2cw1") && white.getUShort("used_p2cw1",0)==2;
  white.end();
  return ready;
}
bool lhHexDigest(const String &v) {
  if(v.length()!=64) return false;
  for(unsigned i=0;i<64;++i) if(!((v[i]>='0'&&v[i]<='9')||(v[i]>='a'&&v[i]<='f'))) return false;
  return true;
}
bool lhRunIdValid(const String &v) {
  if(v.length()==0 || v.length()>64) return false;
  for(unsigned i=0;i<v.length();++i) if(!((v[i]>='0'&&v[i]<='9')||(v[i]>='A'&&v[i]<='Z')||(v[i]>='a'&&v[i]<='z')||v[i]=='_'||v[i]=='-')) return false;
  return true;
}
const char *lhReviewGate(const ActionDescriptor &action, bool executing) {
  if(!whiteSourceReady()) return "source_white_not_complete";
  const String run=server.header("X-LH-Run-Id");
  const String source=server.header("X-LH-Source-Review");
  const String prior=server.header("X-LH-Prior-Review");
  if(!lhRunIdValid(run)||!lhHexDigest(source)||!lhHexDigest(prior)) return "missing_or_invalid_review_binding";
  if(action.ordinal==1 && prior!=source) return "first_review_must_bind_white";
  if(action.ordinal>1 && prior==source) return "prior_review_cannot_reuse_white";
  if(executing || action.ordinal>1) {
    if(run!=lhRunId||source!=lhSourceReview) return "run_or_source_review_changed";
    if(executing && prior!=lhPriorReview) return "prior_review_changed_after_arm";
    if(!executing && prior==lhPriorReview) return "new_stage_review_required";
  }
  return nullptr;
}
void lhLatchReview() {
  lhRunId=server.header("X-LH-Run-Id");
  lhSourceReview=server.header("X-LH-Source-Review");
  lhPriorReview=server.header("X-LH-Prior-Review");
}
"""


def render(c):
    main = frozen(f"src/{OLD}_main.cpp").replace(OLD_MACRO, MACRO).replace(OLD, PREFIX)
    main = main.replace("LUMA/GRAY mechanism V3", "single-pixel lightness history V1")
    main = main.replace(
        '\\"electrical_parameter_write\\":false',
        '\\"caller_electrical_parameter_write\\":false,\\"fixed_profile_parameter_write\\":true',
    )
    main = main.replace(
        "Factory-OTP white anchors plus fixed active/commented L535 full-frame ",
        "External white required; fixed symmetric active/commented L535 full-frame ",
    )
    main = replace_once(
        main,
        "static constexpr uint8_t kActionCount = 4;",
        "static constexpr uint8_t kActionCount = 3;",
    )
    main = replace_once(
        main,
        "#if MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY != 1",
        "#if MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY != 0",
    )
    main = replace_once(
        main,
        "MF1750_OTP_WHITE_FOR_PROFILE_WF23_25 != 1",
        "MF1750_OTP_WHITE_FOR_PROFILE_WF23_25 != 0",
    )
    main = main.replace(
        "Red/pink brightness requires isolated WF23 factory-OTP white",
        "LH1 forbids in-campaign white recovery",
    )
    main = replace_once(
        main,
        "epdValidateCompiledChromaGridFixtures() &&\n                           epdValidateCompiledFactoryOtpWhiteRecoveryFixture()",
        "epdValidateCompiledChromaGridFixtures()",
    )
    main = replace_once(
        main,
        "const bool result = action->driverRole == EpdChromaGridRole::White\n                          ? epdDisplayCompiledFactoryOtpWhiteRecovery()\n                          : epdDisplayCompiledChromaGrid(action->driverRole);",
        "const bool result = epdDisplayCompiledChromaGrid(action->driverRole);",
    )
    main = main.replace(
        "CURRENT_V3_FACTORY_WHITE_COMPLETE_PLUS_CLAIM_RELAY_OFF_48MP_CAPTURE_JPEG_CAMERA_RELATIVE_CLEAN_WHITE_REVIEW",
        "P2_WHITE_SUCCESSOR_COMPLETE_PLUS_FRESH_REVIEW_REQUIRED_NOT_YET_OBSERVED",
    )
    main = main.replace('\\"factory_otp\\":true', '\\"factory_otp\\":false')
    transport = "String transportDispatchJson(const ActionDescriptor &action) {\n"
    for action in c["actions"]:
        payload = {
            "palette_source": "L535_RUNTIME",
            "global_header": action["global_header"],
            "controller_tuple_dispatch": "CC" if action["ordinal"] == 2 else "AA",
            "driver_entry": "epdDisplayCompiledChromaGrid",
            "profile_id": action["profile_id"],
            "profile_sha256": action["profile_sha256"],
            "source_state": action["source_state"],
            "target_state": action["target_state"],
            "cs1_profile": action["profile"]["cs1"],
            "cs2_profile": action["profile"]["cs2"],
        }
        fragment = "," + algorithm.canonical(payload).decode()[1:-1]
        transport += f"  if(action.ordinal=={action['ordinal']}) return String({json.dumps(fragment)});\n"
    transport += '  return String(",\\"transport_dispatch_error\\":true");\n}'
    main = replace_function(
        main,
        "String transportDispatchJson(",
        "String bootAdmissionJson(",
        transport,
    )
    anchor = "const char *validateMutationContract("
    main = replace_once(main, anchor, source_gate_code() + "\n" + anchor)
    main = replace_once(
        main,
        '  if (requestHasBodyOrArguments()) return "body_or_arguments_forbidden";',
        '  if (requestHasBodyOrArguments()) return "body_or_arguments_forbidden";\n  if (const char *reviewError=lhReviewGate(action, requireArmNonce)) return reviewError;',
    )
    main = replace_once(
        main,
        "  armNonceHigh = esp_random();",
        "  lhLatchReview();\n  armNonceHigh = esp_random();",
    )
    main = replace_once(
        main,
        "  executePending = false;\n  state = RuntimeState::Running;",
        '  if (!whiteSourceReady()) { enterFault("dispatch_source_white_not_complete", action); return; }\n  executePending = false;\n  state = RuntimeState::Running;',
    )
    main = replace_once(
        main,
        "  jobQueuedAtMs = millis();",
        "  lhQueuedOrdinal = action->ordinal;\n  jobQueuedAtMs = millis();",
    )
    main = replace_once(
        main,
        "  if (!executePending) return;\n  const ActionDescriptor *action = currentAction();\n  if (!refreshCursorEvidence() || persistentPhase != kPhaseConsumed ||",
        "  if (!executePending) return;\n  const ActionDescriptor *action = actionForOrdinal(lhQueuedOrdinal);\n  if (!refreshCursorEvidence() || nextOrdinal != lhQueuedOrdinal || persistentPhase != kPhaseConsumed ||",
    )
    main = replace_once(
        main,
        '      "Content-Type",      "Content-Length",    "Transfer-Encoding",',
        '      "X-LH-Run-Id", "X-LH-Source-Review", "X-LH-Prior-Review",\n      "Content-Type",      "Content-Length",    "Transfer-Encoding",',
    )
    main = replace_once(
        main,
        '         "\\",\\"compiled_identity_marker\\":\\"" + kCompiledIdentityMarker + "\\"";',
        '         "\\",\\"compiled_identity_marker\\":\\"" + kCompiledIdentityMarker + "\\"" +\n         ",\\"waveform_internal_phase\\":\\"OPAQUE\\",\\"qualified_count\\":0,\\"run_id\\":\\""+lhRunId+"\\",\\"source_review_sha256\\":\\""+lhSourceReview+"\\",\\"prior_review_sha256\\":\\""+lhPriorReview+"\\",\\"source_nvs_complete\\":"+(whiteSourceReady()?"true":"false")+",\\"review_digests_are_host_assertions_only\\":true";',
    )
    # Export actual command BUSY samples, not inferred waveform phases.
    busy_json = r"""String lhBusyJson(const EpdBusyStageEvidence &e) {
  return String("{\"gate_entry_level\":")+String(e.gateEntryLevel)+
    ",\"pre_command_level\":"+String(e.preCommandLevel)+
    ",\"wait_entry_level\":"+String(e.waitEntryLevel)+
    ",\"wait_exit_level\":"+String(e.waitExitLevel)+
    ",\"pre_command_idle_ok\":"+(e.preCommandIdleOk?"true":"false")+
    ",\"assertion_after_idle\":"+(e.assertionAfterIdle?"true":"false")+
    ",\"pre_command_wait_ms\":"+String(e.preCommandWaitMs)+
    ",\"wait_ms\":"+String(e.waitMs)+
    ",\"assertion_latency_ms\":"+String(e.assertionLatencyMs)+"}";
}
"""
    main = replace_once(
        main, "String driverEvidenceJson(", busy_json + "\nString driverEvidenceJson("
    )
    main = replace_once(
        main,
        "         String(report.operationId) +",
        r"""         String(report.operationId) +
         ",\"busy_stage_samples\":{\"unreached_level_sentinel\":255,\"reset\":"+lhBusyJson(report.resetBusy)+
         ",\"pon\":"+lhBusyJson(report.ponBusy)+",\"drf\":"+lhBusyJson(report.drfBusy)+
         ",\"pof\":"+lhBusyJson(report.pofBusy)+",\"post_psr\":"+lhBusyJson(report.postPsrBusy)+"}" +""",
    )
    main = replace_once(
        main,
        "  if (!result) {",
        """  const bool reportOk = driver.valid && !driver.running && driver.sequenceOk &&
      !driver.waitTimedOut && !driver.busyAssertionMissing && !driver.preCommandIdleFailure &&
      driver.mappingApplied && driver.ponBusySeen && driver.drfBusySeen && driver.pofBusySeen &&
      driver.inputFrameFnv1a==action->frameFnv1a && driver.cs1DtmFnv1a==action->cs1DtmFnv1a &&
      driver.cs2DtmFnv1a==action->cs2DtmFnv1a;
  if (!result || !reportOk) {""",
    )
    driver = (
        frozen(f"src/{OLD}_driver.inc")
        .replace(OLD_MACRO, MACRO)
        .replace(OLD, PREFIX)
        .replace(
            "mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3", NAMESPACE
        )
    )
    driver = replace_once(
        driver,
        "  return phRoleIndex(role) < PH_ROLE_COUNT;",
        "  return phRoleIndex(role) >= 1 && phRoleIndex(role) <= 3;",
    )
    driver = replace_once(
        driver,
        "bool phUploadRuntimeLutToController(bool secondController)",
        "bool phUploadRuntimeLutToController(bool secondController, bool useCommentedProfile)",
    )
    upload_start = driver.index("bool phUploadRuntimeLutToController")
    upload_end = driver.index("\n#endif", upload_start)
    segment = driver[upload_start:upload_end]
    segment = replace_once(
        segment, "  if (secondController) {", "  if (useCommentedProfile) {"
    )
    driver = driver[:upload_start] + segment + driver[upload_end:]
    driver = driver.replace(
        "phUploadRuntimeLutToController(false)",
        "phUploadRuntimeLutToController(false, useCommentedGlobal)",
    ).replace(
        "phUploadRuntimeLutToController(true)",
        "phUploadRuntimeLutToController(true, useCommentedGlobal)",
    )
    # The exact C++ frame generator is also compiled/executed by the native audit.
    begin = driver.index("bool phBuildExpectedFrame(")
    end = driver.index("\nbool ", begin + 5)
    driver = (
        driver[:begin]
        + """bool phBuildExpectedFrame(EpdChromaGridRole role, uint8_t *frame, uint32_t histogram[PH_CODE_COUNT]) {
  return phRoleValid(role) && phLayoutValid() && lh_frame::build(static_cast<unsigned>(role), frame, histogram);
}
"""
        + driver[end:]
    )
    a = driver.index("  static constexpr EpdChromaGridRole kRoles[] = {")
    b = driver.index("  };", a) + 5
    driver = (
        driver[:a]
        + "  static constexpr EpdChromaGridRole kRoles[] = {EpdChromaGridRole::Source,EpdChromaGridRole::Mid,EpdChromaGridRole::Target};\n"
        + driver[b:]
    )
    driver = '#include "lh_frame_fill.hpp"\n' + driver
    driver = driver.replace(
        "// Included only by the isolated red/pink brightness driver wrapper. Runtime\n// actions use exact active/commented L535 references and packed full frames;\n// factory-white actions bypass this entry and use the factory-OTP driver. No\n",
        "// Isolated LH1 full-frame history driver, symmetric complete tuples.\n// White and repeat roles are rejected before panel I/O. No\n",
    )
    return {
        f"{PREFIX}_main.cpp": main,
        f"{PREFIX}_driver.inc": driver,
        f"{PREFIX}_main_config.inc": config_source(c),
        f"{PREFIX}_identity.inc": identity_source(c),
        "lh_frame_fill.hpp": frame_source(),
        "frozen_epd_driver.cpp.inc": frozen("src/epd_driver.cpp"),
        f"{PREFIX}_epd_driver.cpp": f'#include "ec5_chroma_grid_epd_driver.h"\n#include <esp_heap_caps.h>\n#include <mbedtls/sha256.h>\n#include "frozen_epd_driver.cpp.inc"\n#include "{PREFIX}_driver.inc"\n',
    }


def verify_package(out):
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    verify_integrity(manifest, "manifest")
    for item in manifest["inputs"] + manifest["outputs"]:
        if bind(item["path"]) != item:
            raise ValueError("package binding differs: " + item["path"])
    if (out / "build-report.json").is_file():
        report = json.loads((out / "build-report.json").read_text(encoding="utf-8"))
        verify_integrity(report, "build report")
        if (
            report["contract_id"] != manifest["contract_id"]
            or report["result"] != "PASS"
        ):
            raise ValueError("build report identity/result mismatch")
        for item in [report["manifest"], report["log"]] + report["artifacts"]:
            if bind(item["path"]) != item:
                raise ValueError("compiled build binding differs: " + item["path"])
    return manifest


def prepare(out):
    out = out.resolve()
    c = contract()
    sources = render(c)
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(parents=True)
    gen = out / "generated"
    gen.mkdir()
    for name, source in sources.items():
        write_new(gen / name, source)
    for stage in algorithm.STAGES:
        write_new(out / (stage.lower() + ".frame4bpp"), algorithm.frame(stage))
    write_new(out / "contract.json", c)
    observations = algorithm.blank_observations(c)
    write_new(out / "observations.blank.json", observations)
    write_new(out / "blank-evaluation.json", algorithm.analyze_bound(observations, c))
    run_record = {
        "kind": "mf1750-lightness-history-construction-record-v1",
        "contract_id": c["contract_id"],
        "run_id": None,
        "panel_id": None,
        "data_origin": "UNFILLED",
        "qualified_count": 0,
        "fresh_white_terminal_evidence": None,
        "clean_white_review": None,
        "new_ipv4_mac_binding": None,
        "new_com_binding": None,
        "post_flash_same_boot_j2_off_diagnostic": None,
        "electrical_state_proven": None,
        "camera_usb_id": "VID_32E4:PID_4801",
        "actions": [],
        "later_gates": {
            name: None
            for name in (
                "local_hold",
                "fresh_white_reconstruction",
                "retention",
                "cross_controller_optical_matching",
                "qualification_review",
            )
        },
    }
    for action in c["actions"]:
        run_record["actions"].append(
            {
                "ordinal": action["ordinal"],
                "stage": action["stage"],
                "boot": None,
                "controller_revision": {"CS1": None, "CS2": None},
                "profile_id": action["profile_id"],
                "profile_sha256": action["profile_sha256"],
                "profile": action["profile"],
                "source_state": action["source_state"],
                "target_state": action["target_state"],
                "firmware_sha256": None,
                "action_sha256": action["action_id"],
                "frame_sha256": action["frame"]["sha256"],
                "controller_frame_sha256": {
                    "CS1": action["cs1_dtm"]["sha256"],
                    "CS2": action["cs2_dtm"]["sha256"],
                },
                "waveform_internal_phase": "OPAQUE",
                "experiment_phase": "SCREEN",
                "temperature_c": None,
                "illumination_id": None,
                "camera_requested_settings": None,
                "camera_effective_settings": None,
                "raw_supported": None,
                "iso_supported": None,
                "hardware_trigger_supported": None,
                "controller_local_rois": None,
                "run_id": None,
                "raw_action_status_paths": None,
                "busy_stage_samples": None,
                "raw_serial_timeline": None,
                "photos_and_sidecars": None,
                "human_observation": None,
                "derived_analysis": None,
                "actual_counts": None,
                "review_verdict": None,
                "review_digest": None,
                "next_action_authorization": None,
            }
        )
    write_new(out / "run-record.blank.json", run_record)
    relative = out.relative_to(ROOT).as_posix()
    ini = f"""[platformio]
default_envs = lh1
src_dir = {relative}/generated
build_dir = {relative}/build
[env:lh1]
platform = platformio/espressif32@7.0.1
board = esp32-s3-devkitc-1
framework = arduino
board_build.arduino.memory_type = qio_opi
board_build.psram_type = opi
build_src_filter = -<*> +<{PREFIX}_main.cpp> +<{PREFIX}_epd_driver.cpp>
build_flags =
  -I src
  -g0
  -D BOARD_HAS_PSRAM
  -D CORE_DEBUG_LEVEL=3
  -D EPD_ENABLE_TEST_PATTERN=0
  -D MF1750_ENABLE_CHROMA_GRID=1
  -D MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD=1
  -D {MACRO}=1
  -D MF1750_ENABLE_RUNTIME_LUT_EMPIRICAL_H3=0
  -D MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY=0
  -D MF1750_OTP_WHITE_FOR_PROFILE_WF20_25=0
  -D MF1750_OTP_WHITE_FOR_PROFILE_WF23_25=0
"""
    write_new(out / "platformio.ini", ini)
    inputs = [bind(ROOT / p) for p in PINNED]
    inputs += [
        bind(Path(__file__)),
        bind(ROOT / "host/static_photo/lightness_history.py"),
        bind(ROOT / "host/static_photo/lightness_test.py"),
        bind(ROOT / "host/static_photo/common.py"),
        bind(ROOT / "host/color_pipeline/color.py"),
        bind(ROOT / "tools/mf1750_runtime_lut_same_r20_parity_v1_pack.py"),
        bind(ROOT / "tools/mf1750_runtime_lut_partial_hold_pack.py"),
        bind(ROOT / "tools/mf1750_lightness_test.py"),
    ]
    # Local credentials stay local; only their file digest is included.
    if (ROOT / "src/wifi_secrets.h").is_file():
        inputs.append(bind(ROOT / "src/wifi_secrets.h"))
    write_new(
        out / "manifest.json",
        attach_integrity(
            {
                "kind": "mf1750-lightness-history-firmware-package-v1",
                "contract_id": c["contract_id"],
                "inputs": inputs,
                "outputs": [bind(p) for p in sorted(out.rglob("*")) if p.is_file()],
                "live_ready": False,
                "qualified_count": 0,
            }
        ),
    )
    verify_package(out)
    return {
        "result": "PASS_OFFLINE_PREPARED",
        "output": str(out),
        "contract_id": c["contract_id"],
        "action_count": 3,
        "hardware_accessed": False,
    }


def build(out):
    manifest = verify_package(out)
    if (out / "build").exists() or (out / "build.log").exists():
        raise FileExistsError("build evidence already exists; prepare a fresh package")
    pio = shutil.which("pio")
    if not pio:
        raise RuntimeError("PlatformIO missing")
    env = dict(
        os.environ,
        PLATFORMIO_SETTING_ENABLE_TELEMETRY="no",
        PLATFORMIO_SETTING_CHECK_PLATFORMIO_INTERVAL="0",
    )
    with (out / "build.log").open("xb") as log:
        process = subprocess.run(
            [pio, "run", "-c", str(out / "platformio.ini")],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if process.returncode:
        raise RuntimeError(
            f"compile failed ({process.returncode}); inspect {out / 'build.log'}"
        )
    verify_package(out)
    c = json.loads((out / "contract.json").read_text(encoding="utf-8"))
    artifacts = [bind(out / "build/lh1" / n) for n in ("firmware.bin", "firmware.elf")]
    markers = [c["contract_id"]] + [a["action_id"] for a in c["actions"]]
    for item in artifacts:
        data = Path(item["path"]).read_bytes()
        if any(m.encode() not in data for m in markers):
            raise ValueError("compiled identity marker missing")
    report = attach_integrity(
        {
            "kind": "mf1750-lightness-history-firmware-build-v1",
            "recorded_at": datetime.now().astimezone().isoformat(),
            "result": "PASS",
            "contract_id": c["contract_id"],
            "manifest": bind(out / "manifest.json"),
            "log": bind(out / "build.log"),
            "artifacts": artifacts,
            "marker_check": "PASS",
            "package_still_matches": True,
            "compiled_actions": 3,
            "hardware_accessed": False,
            "firmware_flashed": False,
            "visible_refresh_count": 0,
            "live_ready": False,
            "qualified_count": 0,
            "manifest_integrity": manifest["integrity"],
        }
    )
    write_new(out / "build-report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "build", "verify", "analyze"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        out = args.output_dir.resolve()
        if args.command == "prepare":
            result = prepare(out)
        elif args.command == "build":
            result = build(out)
        elif args.command == "verify":
            verify_package(out)
            result = {"result": "PASS", "hardware_accessed": False}
        else:
            verify_package(out)
            if args.input is None or args.report is None:
                raise ValueError("analyze requires --input and --report")
            from tools.mf1750_lightness_test import checked_analysis

            value = json.loads(args.input.read_text(encoding="utf-8"))
            verified = checked_analysis(
                value, args.input
            )  # Verify raw evidence files, not just reported values.
            c = json.loads((out / "contract.json").read_text(encoding="utf-8"))
            if value.get("data_origin") == "FIELD_DERIVED":
                built = json.loads(
                    (out / "build-report.json").read_text(encoding="utf-8")
                )
                binary = next(
                    item
                    for item in built["artifacts"]
                    if item["path"].endswith("firmware.bin")
                )
                if value.get("identity", {}).get("firmware_sha256") != binary["sha256"]:
                    raise ValueError(
                        "field measurements must bind this compiled firmware.bin"
                    )
            result = algorithm.analyze_bound(value, c)
            result.pop("integrity")
            result.update(
                input=bind(args.input),
                contract=bind(out / "contract.json"),
                verified_evidence_files=verified["verified_evidence_files"],
                verification_scope=verified["verification_scope"],
            )
            result = attach_integrity(result)
            write_new(args.report, result)
            result = {
                "verdict": result["verdict"],
                "qualified_count": 0,
                "output": str(args.report),
            }
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        print(
            json.dumps(
                {
                    "result": "FAIL_STOP",
                    "error": str(error),
                    "hardware_accessed": False,
                },
                ensure_ascii=False,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
