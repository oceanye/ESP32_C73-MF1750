#include <Arduino.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <esp_system.h>

#include <cstdio>
#include <cstring>

#include "epd_config.h"
#include "ec5_chroma_grid_epd_driver.h"

// Isolated fixed-input campaign. Every visible action is compiled into the
// firmware and requires a separate bodyless ARM and EXECUTE request. There is
// no startup refresh, raw ingress, electrical write, automatic chaining,
// retry, automatic recovery, or NVS clear route.
#if MF1750_ENABLE_CHROMA_GRID != 1
#error "Chroma grid requires MF1750_ENABLE_CHROMA_GRID=1"
#endif

#if (defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD) || \
     defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
     defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_GUARD_DIRECTION_AB_V1_BUILD) || \
     defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_ENDPOINT_AB_V1_BUILD)) && \
    (MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY != 1 || \
     MF1750_OTP_WHITE_FOR_PROFILE_WF20_25 != 0 || \
     MF1750_OTP_WHITE_FOR_PROFILE_WF23_25 != 1)
#error "repeat-PTLW V2 requires the isolated WF23 factory-OTP white fixture"
#endif

#ifndef EPD_ENABLE_TEST_PATTERN
#error "Chroma grid requires explicit EPD_ENABLE_TEST_PATTERN=0"
#endif

#if EPD_ENABLE_TEST_PATTERN != 0
#error "Chroma grid must never refresh during startup"
#endif

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600,
              "Chroma grid is frozen for the 1024x600 panel");
static_assert(EPD_FRAME_BYTES == 307200 &&
                  EPD_CONTROLLER_FRAME_BYTES == 153600,
              "Chroma grid requires frozen 4bpp cascade geometry");
static_assert(EPD_CS1_SOURCE_HALF == 0 && !EPD_CS1_FLIP_X &&
                  !EPD_CS1_FLIP_Y && !EPD_CS1_NIBBLE_SWAP &&
                  EPD_CS2_SOURCE_HALF == 1 && !EPD_CS2_FLIP_X &&
                  !EPD_CS2_FLIP_Y && !EPD_CS2_NIBBLE_SWAP,
              "Chroma grid mapping differs from MAP_ORIENT_V1");

namespace {

WebServer server(80);
Preferences cursorStore;

static constexpr uint8_t kPhaseReady = 0;
static constexpr uint8_t kPhaseArmed = 1;
static constexpr uint8_t kPhaseConsumed = 2;
static constexpr uint8_t kPhaseFault = 3;
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V1_BUILD)
static constexpr uint8_t kActionCount = 3;
#else
static constexpr uint8_t kActionCount = 5;
#endif
static constexpr uint8_t kTerminalOrdinal = kActionCount + 1;

struct ActionDescriptor {
  uint8_t ordinal;
  EpdChromaGridRole driverRole;
  const char *role;
  uint8_t round;
  const char *branch;
  const char *descriptorId;
  const char *actionId;
  const char *priorActionId;
  const char *frameSha256;
  const char *cs1DtmSha256;
  const char *cs2DtmSha256;
  uint32_t frameFnv1a;
  uint32_t cs1DtmFnv1a;
  uint32_t cs2DtmFnv1a;
  uint32_t histogram[8];
};

#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_GUARD_DIRECTION_AB_V1_BUILD)
#include "ec5_runtime_lut_partial_hold_guard_direction_ab_v1_main_config.inc"
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_ENDPOINT_AB_V1_BUILD)
#include "ec5_runtime_lut_partial_hold_endpoint_ab_v1_main_config.inc"
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD)
#include "ec5_runtime_lut_partial_hold_repeat_ptlw_v3_main_config.inc"
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD)
#include "ec5_runtime_lut_partial_hold_repeat_ptlw_v2_main_config.inc"
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V1_BUILD)
#include "ec5_runtime_lut_partial_hold_repeat_ptlw_v1_main_config.inc"
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_V4_BUILD)
#include "ec5_runtime_lut_partial_hold_v4_main_config.inc"
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_V3_BUILD)
#include "ec5_runtime_lut_partial_hold_main_config.inc"
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_V2_BUILD)
#include "ec5_runtime_lut_partial_hold_main_config.inc"
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD)
#include "ec5_runtime_lut_partial_hold_main_config.inc"
#elif defined(MF1750_PARTIAL_HOLD_BUILD)
#include "ec5_partial_hold_main_config.inc"
#elif !defined(MF1750_SINGLE_PIXEL_CUBE_BUILD)

static constexpr const char *kClassification =
    "FACTORY_OTP_FIXED_CHROMA_HISTORY_NO_RUNTIME_LUT";
static constexpr const char *kProfileSource = "factory_otp";
static constexpr const char *kIdentityRevision = "chroma-grid-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_CHROMA_GRID_DEVICE_V1";
static constexpr const char *kLayoutId =
    "dual-controller-mirrored-8x8-white-gap-chroma-history-v1";
static constexpr const char *kBuildTag =
    "MF1750_EC5_CHROMA_GRID_V1_2026-08-21";
static constexpr const char *kBootLabel = "EC5 Chroma grid";
static constexpr const char *kTestId = "EC5-CHROMA-GRID-V1";
static constexpr const char *kCampaignId = "EC5_CHROMA_GRID_V1";
static constexpr const char *kContractId =
    "ff24c93b431f4ea95eea0738c37564133c4f2e436e4d8060f7f47dad8fe55405";
static constexpr const char *kVersionKind =
    "mf1750-ec5-chroma-grid-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-chroma-grid-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-chroma-grid-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-chroma-grid-report";
static constexpr const char *kBaselineRole = "CHROMA_WHITE_BASELINE";
static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"sequences_per_controller\":64,"
    "\"roi_count\":128,\"old_axis\":\"row\","
    "\"history_branch_axis\":\"column\","
    "\"cs2_position_mirrored\":true,"
    "\"grid_x0_local\":34,\"grid_x1_local_exclusive\":478,"
    "\"grid_y0\":30,\"grid_y1_exclusive\":570,"
    "\"cell_width\":52,\"cell_height\":64,"
    "\"gap_x\":4,\"gap_y\":4}";
static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":false,\"window_refresh\":false,"
    "\"command_0x86\":false,\"mid_refresh_power_cut\":false,"
    "\"spi_frequency_sweep\":false,"
    "\"full_screen_global_refresh\":true";

static constexpr const char *kNvsNamespace = "mf1750_cg1";
static constexpr const char *kNvsKey = "cursor_v1";

static constexpr const char *kVersionRoute =
    "/api/ec5/chroma-grid/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/chroma-grid/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/chroma-grid/status";
static constexpr const char *kReportRoute =
    "/api/ec5/chroma-grid/report";
static constexpr const char *kArmRoute =
    "/api/ec5/chroma-grid/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/chroma-grid/execute";

static constexpr const char *kBuildHeader = "X-EC5-Build-Tag";
static constexpr const char *kTestHeader = "X-EC5-Test-Id";
static constexpr const char *kCampaignHeader = "X-EC5-Campaign-Id";
static constexpr const char *kActionHeader = "X-EC5-Action-Id";
static constexpr const char *kOrdinalHeader = "X-EC5-Ordinal";
static constexpr const char *kDescriptorHeader = "X-EC5-Descriptor-Id";
static constexpr const char *kBootNonceHeader = "X-EC5-Boot-Nonce";
static constexpr const char *kArmNonceHeader = "X-EC5-Arm-Nonce";
static constexpr const char *kIntentHeader = "X-EC5-Intent";
static constexpr const char *kArmIntent =
    "ARM_ONE_FIXED_FACTORY_OTP_CHROMA_GRID_ACTION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ARMED_FACTORY_OTP_CHROMA_GRID_ACTION_ONCE";

static constexpr const char *kSourceFrameSha256 =
    "213d3eab11966579f8cab7577dff315897f96a72e9030a236f60ca899295b8de";
static constexpr const char *kSourceCs1DtmSha256 =
    "0eba448b460d31d3d28a6d9e6d62fa0193f6eaabe769d9fc846658c4b0ac64e2";
static constexpr const char *kSourceCs2DtmSha256 =
    "8ae4ae3058ab1ffab4152f4c2e714e88fce7a0c4ace3bf472c59b7a520119079";
static constexpr const char *kMidFrameSha256 =
    "8047a36612272c3e5e03717b00184e151d16fe67caf972c70ff0caea88d63054";
static constexpr const char *kMidCs1DtmSha256 =
    "c2143d36c7a2be633c6e0fa63bf2e63cc08533a428cf219e3246891e2d18b987";
static constexpr const char *kMidCs2DtmSha256 =
    "b17caf38ae1aefcd01b63675cf0f4027850bc65c8f3f590339aa29a55c53b8cd";
static constexpr const char *kTargetFrameSha256 =
    "c2e5289bfa44ffba8daf374edd70e34216ea13e08a3e58764feed9f13efa2036";
static constexpr const char *kTargetCs1DtmSha256 =
    "26535f9244d6af9c0899ec851cb84b469f01d949baf9602988d98c2377e1a72f";
static constexpr const char *kTargetCs2DtmSha256 =
    "3430064d6abd1273837db198e2901f20512726794b64e6f32886c5e9fbb5b57c";
static constexpr const char *kWhiteFrameSha256 =
    "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d";
static constexpr const char *kWhiteDtmSha256 =
    "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158";

static constexpr ActionDescriptor kActions[] = {
    {1,
     EpdChromaGridRole::White,
     "CHROMA_WHITE_BASELINE",
     1,
     "FACTORY_OTP_WHITE_BASELINE",
     "032ca22f88ab82e8c6088750194b2539779f0ced441ae0ef4fdcb16a7cc91623",
     "fca6ae290e3257bfe04b7190e533e0fd94822ff69ee4e252a0b45b0ea9c9dc98",
     nullptr,
     kWhiteFrameSha256,
     kWhiteDtmSha256,
     kWhiteDtmSha256,
     0x13340DC5UL,
     0xB7A855C5UL,
     0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {2,
     EpdChromaGridRole::Source,
     "CHROMA_SOURCE_GRID",
     1,
     "SOURCE_0_TO_7_WHITE_GAPS",
     "9b0f1a15589355ce0709aa865a710b79510cde656239284f0123bb67048c8297",
     "97d8543a7635098cdfc797df105ad45a5292095f6632d9086181cae0114dd07a",
     "fca6ae290e3257bfe04b7190e533e0fd94822ff69ee4e252a0b45b0ea9c9dc98",
     kSourceFrameSha256,
     kSourceCs1DtmSha256,
     kSourceCs2DtmSha256,
     0xD1A5ADC5UL,
     0xF9AFC5C5UL,
     0x0AAFC5C5UL,
     {53248, 241664, 53248, 53248, 53248, 53248, 53248, 53248}},
    {3,
     EpdChromaGridRole::Mid,
     "CHROMA_MID_GRID",
     1,
     "MID_CODES_4_AND_7",
     "3686f3f2f74dc89d6baf0c7d485a2f5467809067c8331ea362ae6f932a1ad2b8",
     "5bcc1508faacdce42759c2e20d5afaecff1691227510ce3918c26f4c7ec9ad3d",
     "97d8543a7635098cdfc797df105ad45a5292095f6632d9086181cae0114dd07a",
     kMidFrameSha256,
     kMidCs1DtmSha256,
     kMidCs2DtmSha256,
     0x6163EDC5UL,
     0x33D245C5UL,
     0x23AE45C5UL,
     {0, 188416, 0, 0, 212992, 0, 0, 212992}},
    {4,
     EpdChromaGridRole::Target,
     "CHROMA_TARGET_GRID",
     1,
     "TARGET_CODES_2_3_5_6_AFTER_SOURCE_MID",
     "b995ab62097f9cbc99ddce3f9be5180060e8fbb2e8348d957816fcb3f7ea9f52",
     "9d91e22e703b4b5cd48e99f3e9fb69cd750fd55dc7f8b3d0c5c35c005206fc1f",
     "5bcc1508faacdce42759c2e20d5afaecff1691227510ce3918c26f4c7ec9ad3d",
     kTargetFrameSha256,
     kTargetCs1DtmSha256,
     kTargetCs2DtmSha256,
     0xD3FE2DC5UL,
     0x9E5C65C5UL,
     0xD0BE65C5UL,
     {0, 188416, 106496, 106496, 0, 106496, 106496, 0}},
    {5,
     EpdChromaGridRole::White,
     "CHROMA_WHITE_RECOVERY",
     1,
     "FACTORY_OTP_WHITE_RECOVERY",
     "abbbe570497b77842e51d66127934153589c54cdc49ac8fdcad788de0205cfb3",
     "3acb67dbf1d9fa6365b602cdaadb3c29738ade62f0008bc1656dc02bccf49c8b",
     "9d91e22e703b4b5cd48e99f3e9fb69cd750fd55dc7f8b3d0c5c35c005206fc1f",
     kWhiteFrameSha256,
     kWhiteDtmSha256,
     kWhiteDtmSha256,
     0x13340DC5UL,
     0xB7A855C5UL,
     0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
};

#else
#include "ec5_single_pixel_cube_main_config.inc"
#endif

static_assert(sizeof(kActions) / sizeof(kActions[0]) == kActionCount,
              "compiled campaign action count differs");

enum class RuntimeState : uint8_t {
  BootSelfCheck,
  Ready,
  Armed,
  Queued,
  Running,
  Complete,
  FaultLocked,
};

RuntimeState state = RuntimeState::BootSelfCheck;
bool fixtureSelfCheckPassed = false;
bool gpioInitialized = false;
bool storeReady = false;
bool keyPresent = false;
bool executePending = false;
uint8_t persistentPhase = kPhaseReady;
uint8_t nextOrdinal = 1;
uint16_t cursorRaw = 1;
uint32_t bootNonceHigh = 0;
uint32_t bootNonceLow = 0;
uint32_t armNonceHigh = 0;
uint32_t armNonceLow = 0;
uint32_t armRequestCount = 0;
uint32_t executeRequestCount = 0;
uint32_t totalDriverCallCount = 0;
uint8_t driverCallCountForAction = 0;
uint32_t jobQueuedAtMs = 0;
uint32_t jobStartedAtMs = 0;
uint32_t jobFinishedAtMs = 0;
String publishedReport =
    "{\"schema_version\":3,\"valid\":false,\"error\":\"boot_self_check\"}";

const char *stateName(RuntimeState value) {
  switch (value) {
    case RuntimeState::BootSelfCheck:
      return "boot_self_check";
    case RuntimeState::Ready:
      return "ready";
    case RuntimeState::Armed:
      return "armed";
    case RuntimeState::Queued:
      return "queued";
    case RuntimeState::Running:
      return "running";
    case RuntimeState::Complete:
      return "complete";
    case RuntimeState::FaultLocked:
      return "fault_locked";
  }
  return "fault_locked";
}

const char *phaseName(uint8_t phase) {
  switch (phase) {
    case kPhaseReady:
      return "READY";
    case kPhaseArmed:
      return "ARMED";
    case kPhaseConsumed:
      return "CONSUMED";
    case kPhaseFault:
      return "FAULT";
  }
  return "INVALID";
}

String hex32(uint32_t value) {
  char output[9] = {};
  snprintf(output, sizeof(output), "%08lx",
           static_cast<unsigned long>(value));
  return String(output);
}

String bootNonce() { return hex32(bootNonceHigh) + hex32(bootNonceLow); }
String armNonce() { return hex32(armNonceHigh) + hex32(armNonceLow); }

uint16_t encodeCursor(uint8_t phase, uint8_t ordinal) {
  return static_cast<uint16_t>((static_cast<uint16_t>(phase) << 8) | ordinal);
}

bool cursorFieldsValid(uint8_t phase, uint8_t ordinal) {
  if (phase == kPhaseReady) return ordinal >= 1 && ordinal <= kTerminalOrdinal;
  return phase <= kPhaseFault && ordinal >= 1 && ordinal <= kActionCount;
}

bool refreshCursorEvidence() {
  if (!storeReady) return false;
  keyPresent = cursorStore.isKey(kNvsKey);
  cursorRaw =
      keyPresent ? cursorStore.getUShort(kNvsKey, 0) : encodeCursor(0, 1);
  persistentPhase = static_cast<uint8_t>((cursorRaw >> 8) & 0xFFU);
  nextOrdinal = static_cast<uint8_t>(cursorRaw & 0xFFU);
  return cursorFieldsValid(persistentPhase, nextOrdinal);
}

bool persistCursor(uint8_t phase, uint8_t ordinal) {
  if (!storeReady || !cursorFieldsValid(phase, ordinal)) return false;
  const uint16_t wanted = encodeCursor(phase, ordinal);
  if (cursorStore.putUShort(kNvsKey, wanted) != sizeof(uint16_t)) return false;
  if (!refreshCursorEvidence()) return false;
  return keyPresent && cursorRaw == wanted && persistentPhase == phase &&
         nextOrdinal == ordinal;
}

const ActionDescriptor *actionForOrdinal(uint8_t ordinal) {
  if (ordinal < 1 || ordinal > kActionCount) return nullptr;
  const ActionDescriptor &action = kActions[ordinal - 1];
  return action.ordinal == ordinal ? &action : nullptr;
}

const ActionDescriptor *currentAction() { return actionForOrdinal(nextOrdinal); }

bool requestHasBodyOrArguments() {
  if (server.args() != 0 || server.hasArg("plain")) return true;
  const String contentType = server.header("Content-Type");
  const String transferEncoding = server.header("Transfer-Encoding");
  const String contentLength = server.header("Content-Length");
  if (!contentType.isEmpty() || !transferEncoding.isEmpty()) return true;
  return !contentLength.isEmpty() && contentLength != "0";
}

bool requireReadOnlyRequest() {
  if (!requestHasBodyOrArguments()) return true;
  server.send(400, "application/json",
              "{\"error\":\"read_only_route_rejects_body_or_arguments\"}");
  return false;
}

bool exactHeader(const char *name, const String &expected) {
  return server.hasHeader(name) && server.header(name) == expected;
}

const char *validateMutationContract(const ActionDescriptor &action,
                                     const char *intent,
                                     bool requireArmNonce) {
  if (requestHasBodyOrArguments()) return "body_or_arguments_forbidden";
  if (!exactHeader(kBuildHeader, kBuildTag))
    return "build_tag_missing_or_mismatch";
  if (!exactHeader(kTestHeader, kTestId))
    return "test_id_missing_or_mismatch";
  if (!exactHeader(kCampaignHeader, kCampaignId))
    return "campaign_id_missing_or_mismatch";
  if (!exactHeader(kActionHeader, action.actionId))
    return "action_id_missing_or_mismatch";
  if (!exactHeader(kOrdinalHeader, String(action.ordinal)))
    return "ordinal_missing_or_mismatch";
  if (!exactHeader(kDescriptorHeader, action.descriptorId))
    return "descriptor_id_missing_or_mismatch";
  if (!exactHeader(kBootNonceHeader, bootNonce()))
    return "boot_nonce_missing_or_stale";
  if (!exactHeader(kIntentHeader, intent)) return "intent_missing_or_mismatch";
  if (!requireArmNonce && server.hasHeader(kArmNonceHeader))
    return "arm_nonce_forbidden_during_arm";
  if (requireArmNonce && !exactHeader(kArmNonceHeader, armNonce()))
    return "arm_nonce_missing_or_stale";
  return nullptr;
}

String nvsContractJson() {
  return String("\"nvs_contract\":{\"namespace\":\"") + kNvsNamespace +
         "\",\"key\":\"" + kNvsKey +
         "\",\"encoding\":\"uint16 high_byte_phase low_byte_next_ordinal\"," +
         "\"phases\":{\"READY\":0,\"ARMED\":1,\"CONSUMED\":2,\"FAULT\":3}," +
         "\"initial_key_present\":false,\"initial_value\":1," +
         "\"initial_next_ordinal\":1,\"terminal_next_ordinal\":" +
         String(kTerminalOrdinal) + "}";
}

String baselineContractJson() {
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V1_BUILD)
  return String("\"baseline_contract\":{") +
         "\"ordinal\":null,\"role\":\"" + kBaselineRole +
         "\",\"external_anchor_required\":true,"
         "\"anchor_established_by_firmware\":false,"
         "\"one_visible_refresh_required\":false,"
         "\"code7_baseline_action_reachable\":false,"
         "\"recovery_action_reachable\":false}";
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_GUARD_DIRECTION_AB_V1_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_ENDPOINT_AB_V1_BUILD)
  return String("\"baseline_contract\":{") +
         "\"ordinal\":1,\"role\":\"" + kBaselineRole +
         "\",\"external_anchor_required\":false,"
         "\"anchor_established_by_firmware\":true,"
         "\"one_visible_refresh_required\":true,"
         "\"runtime_code7_action_reachable\":false,"
         "\"factory_otp_recovery_ordinal\":5}";
#else
  return String("\"baseline_contract\":{") +
         "\"ordinal\":1,\"role\":\"" + kBaselineRole +
         "\",\"external_anchor_required\":false,"
         "\"one_visible_refresh_required\":true}";
#endif
}

String identityJson() {
  return String("\"build_tag\":\"") + kBuildTag + "\",\"test_id\":\"" +
         kTestId + "\",\"campaign_id\":\"" + kCampaignId +
         "\",\"device_api_version\":\"" + kDeviceApiVersion +
         "\",\"identity_revision\":\"" + kIdentityRevision +
         "\",\"contract_id\":\"" + kContractId + "\"";
}

String histogramJson(const ActionDescriptor &action) {
  String output = "[";
  for (uint8_t index = 0; index < 8; ++index) {
    if (index != 0) output += ',';
    output += String(action.histogram[index]);
  }
  output += ']';
  return output;
}

String actionJson(const ActionDescriptor &action) {
  return String("{\"ordinal\":") + String(action.ordinal) +
         ",\"descriptor_id\":\"" + action.descriptorId +
         "\",\"action_id\":\"" + action.actionId +
         "\",\"prior_static_action_id\":" +
         (action.priorActionId ? String("\"") + action.priorActionId + "\""
                               : String("null")) +
         ",\"role\":\"" + action.role + "\",\"round\":" +
         String(action.round) + ",\"branch\":\"" + action.branch +
         "\",\"frame_sha256\":\"" + action.frameSha256 +
         "\",\"cs1_dtm_sha256\":\"" + action.cs1DtmSha256 +
         "\",\"cs2_dtm_sha256\":\"" + action.cs2DtmSha256 +
         "\",\"transport_code_histogram\":" + histogramJson(action) + "}";
}

String versionJson() {
  refreshCursorEvidence();
  return String("{\"schema_version\":3,\"kind\":\"") + kVersionKind +
         "\"," + identityJson() +
         ",\"classification\":\"" + kClassification +
         "\",\"layout_id\":\"" + kLayoutId +
         "\",\"driver_api_version\":\"" + EPD_DRIVER_API_VERSION +
         "\",\"profile_source\":\"" + kProfileSource +
         "\",\"action_count\":" + String(kActionCount) +
         ",\"automatic_execute\":false," +
         "\"automatic_chaining\":false,\"startup_refresh\":false," +
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD)
                  "\"factory_otp\":true,\"custom_lut_or_waveform\":true,"
                  "\"raw_frame_ingress\":false,\"runtime_lut_write\":true,"
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_GUARD_DIRECTION_AB_V1_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_ENDPOINT_AB_V1_BUILD)
                  "\"factory_otp\":true,\"custom_lut_or_waveform\":true,"
                  "\"raw_frame_ingress\":false,\"runtime_lut_write\":true,"
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD)
         "\"raw_frame_ingress\":false,\"runtime_lut_write\":true," +
#else
         "\"raw_frame_ingress\":false,\"runtime_lut_write\":false," +
#endif
         "\"electrical_parameter_write\":false,\"dither\":false," +
         "\"spatial_mixing\":false,\"retry\":false,\"recovery\":false," +
         kCampaignCapabilitiesJson + "," +
         nvsContractJson() + "," + baselineContractJson() + "}";
}

String manifestJson() {
  String output = String("{\"schema_version\":3,\"kind\":\"") +
                  kManifestKind + "\"," +
                  identityJson() + ",\"classification\":\"" +
                  kClassification + "\",\"layout_id\":\"" + kLayoutId +
                  "\",\"profile_source\":\"" + kProfileSource +
                  "\",\"action_count\":" + String(kActionCount) +
                  ",\"round_count\":1,\"history_layout\":" +
                  kHistoryLayoutJson + "," +
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD)
                  "\"factory_otp\":true,\"custom_lut_or_waveform\":true,"
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_GUARD_DIRECTION_AB_V1_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_ENDPOINT_AB_V1_BUILD)
                  "\"factory_otp\":true,\"custom_lut_or_waveform\":true,"
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD)
                  "\"factory_otp\":false,\"custom_lut_or_waveform\":true,"
#else
                  "\"factory_otp\":true,\"custom_lut_or_waveform\":false,"
#endif
                  "\"synchronous_both_controllers\":true,"
                  "\"one_driver_call_per_action\":true,"
                  "\"automatic_chaining\":false,\"startup_refresh\":false,"
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD)
                  "\"raw_frame_ingress\":false,\"runtime_lut_write\":true,"
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_GUARD_DIRECTION_AB_V1_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_ENDPOINT_AB_V1_BUILD)
                  "\"raw_frame_ingress\":false,\"runtime_lut_write\":true,"
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD)
                  "\"raw_frame_ingress\":false,\"runtime_lut_write\":true,"
#else
                  "\"raw_frame_ingress\":false,\"runtime_lut_write\":false,"
#endif
                  "\"electrical_parameter_write\":false,\"dither\":false,"
                  "\"spatial_mixing\":false,\"retry\":false,"
                  "\"recovery\":false," + kCampaignCapabilitiesJson +
                  ",\"actions\":[";
  for (uint8_t index = 0; index < kActionCount; ++index) {
    if (index != 0) output += ',';
    output += actionJson(kActions[index]);
  }
  output += String("],") + nvsContractJson() + "," + baselineContractJson() +
            "}";
  return output;
}

String gpioJson() {
  if (!gpioInitialized)
    return "\"gpio_initialized\":false,\"busy\":null,\"rst\":null,"
           "\"cs\":null,\"cs2\":null";
  return String("\"gpio_initialized\":true,\"busy\":") +
         String(epdReadBusy()) + ",\"rst\":" +
         String(digitalRead(EPD_PIN_RST)) + ",\"cs\":" +
         String(digitalRead(EPD_PIN_CS)) + ",\"cs2\":" +
         String(digitalRead(EPD_PIN_CS2));
}

String statusJson() {
  const bool cursorValid = refreshCursorEvidence();
  const ActionDescriptor *action = currentAction();
  const String current = action && persistentPhase != kPhaseReady
                             ? actionJson(*action)
                             : String("null");
  return String("{\"schema_version\":3,\"kind\":\"") + kStatusKind +
         "\"," + identityJson() +
         ",\"classification\":\"" + kClassification +
         "\",\"boot_nonce\":\"" + bootNonce() +
         "\",\"state\":\"" + stateName(state) + "\",\"phase\":" +
         String(persistentPhase) + ",\"phase_name\":\"" +
         phaseName(persistentPhase) + "\",\"cursor_raw\":" +
         String(cursorRaw) + ",\"next_ordinal\":" + String(nextOrdinal) +
         ",\"current_action\":" + current +
         ",\"campaign_complete\":" +
         (nextOrdinal == kTerminalOrdinal && persistentPhase == kPhaseReady
              ? "true"
              : "false") +
         ",\"fixture_self_check_passed\":" +
         (fixtureSelfCheckPassed ? "true" : "false") +
         ",\"cursor_valid\":" + (cursorValid ? "true" : "false") +
         ",\"persistent_key_present\":" +
         (keyPresent ? "true" : "false") +
         ",\"execute_pending\":" + (executePending ? "true" : "false") +
         ",\"arm_request_count\":" + String(armRequestCount) +
         ",\"execute_request_count\":" + String(executeRequestCount) +
         ",\"total_driver_call_count\":" +
         String(totalDriverCallCount) + "," + gpioJson() + "," +
         nvsContractJson() + "}";
}

String driverEvidenceJson(const EpdOperationReport &report) {
  return String("{\"driver_evidence_schema_version\":2,\"operation_id\":") +
         String(report.operationId) +
         ",\"valid\":" + (report.valid ? "true" : "false") +
         ",\"running\":" + (report.running ? "true" : "false") +
         ",\"sequence_ok\":" +
         (report.sequenceOk ? "true" : "false") +
         ",\"wait_timeout\":" +
         (report.waitTimedOut ? "true" : "false") +
         ",\"busy_assertion_missing\":" +
         (report.busyAssertionMissing ? "true" : "false") +
         ",\"mapping_applied\":" +
         (report.mappingApplied ? "true" : "false") +
         ",\"pon_busy_seen\":" + (report.ponBusySeen ? "true" : "false") +
         ",\"drf_busy_seen\":" + (report.drfBusySeen ? "true" : "false") +
         ",\"pof_busy_seen\":" + (report.pofBusySeen ? "true" : "false") +
         ",\"post_psr_busy_seen\":" +
         (report.postPsrBusySeen ? "true" : "false") +
         ",\"pre_command_idle_failure\":" +
         (report.preCommandIdleFailure ? "true" : "false") +
         ",\"failure_stage\":\"" + String(report.failureStage) +
         "\",\"failure_code\":" + String(report.failureCode) +
         ",\"spi_hz\":" + String(report.spiHz) +
         ",\"free_psram_before\":" + String(report.freePsramBefore) +
         ",\"largest_psram_block_before\":" +
         String(report.largestPsramBlockBefore) +
         ",\"input_fnv1a\":" + String(report.inputFrameFnv1a) +
         ",\"cs1_dtm_fnv1a\":" + String(report.cs1DtmFnv1a) +
         ",\"cs2_dtm_fnv1a\":" + String(report.cs2DtmFnv1a) +
         ",\"total_ms\":" + String(report.totalMs) +
         ",\"cs1_upload_ms\":" + String(report.cs1UploadMs) +
         ",\"cs2_upload_ms\":" + String(report.cs2UploadMs) +
         ",\"pon_ms\":" + String(report.ponWaitMs) +
         ",\"drf_ms\":" + String(report.drfWaitMs) +
         ",\"pof_ms\":" + String(report.pofWaitMs) +
         ",\"post_psr_ms\":" + String(report.postPsrWaitMs) +
         ",\"last_wait_stage\":\"" + String(report.lastWaitStage) +
         "\",\"timeout_stage\":\"" + String(report.timeoutStage) +
         "\",\"busy_missing_stage\":\"" +
         String(report.busyMissingStage) +
         "\",\"pre_command_busy_stage\":\"" +
         String(report.preCommandBusyStage) +
         "\",\"safe_finish\":{\"busy_before_pins_low\":" +
         String(report.safeFinishBusyBeforePinsLow) +
         ",\"busy_after_pins_low\":" +
         String(report.safeFinishBusyAfterPinsLow) +
         ",\"busy_after_5ms\":" + String(report.safeFinishBusyAfter5Ms) +
         ",\"final_gpio\":{\"busy\":" + String(report.finalBusyLevel) +
         ",\"rst\":" + String(report.finalRstLevel) +
         ",\"cs\":" + String(report.finalCs1Level) +
         ",\"cs2\":" + String(report.finalCs2Level) + "}}}";
}

void publishNoExecuteReport() {
  publishedReport =
      String("{\"schema_version\":3,\"kind\":\"") + kReportKind +
      "\",\"valid\":false," +
      identityJson() + ",\"classification\":\"" + kClassification +
      "\",\"boot_nonce\":\"" + bootNonce() +
      "\",\"ordinal\":null,\"descriptor_id\":null,\"action_id\":null," +
      "\"terminal_state\":\"NOT_EXECUTED\",\"result\":false," +
      "\"error\":\"no_execute_report\",\"driver_called\":false," +
      "\"driver_call_count_for_action\":0,\"total_driver_call_count\":" +
      String(totalDriverCallCount) + ",\"phase\":" +
      String(persistentPhase) + ",\"next_ordinal\":" +
      String(nextOrdinal) +
      ",\"no_retry\":true,\"no_recovery\":true}";
}

void publishFaultReport(const char *error, const ActionDescriptor *action,
                        bool driverCalled, const EpdOperationReport *driver) {
  const String actionFields =
      action ? String("\"ordinal\":") + String(action->ordinal) +
                   ",\"descriptor_id\":\"" + action->descriptorId +
                   "\",\"action_id\":\"" + action->actionId +
                   "\",\"role\":\"" + action->role +
                   "\",\"round\":" + String(action->round) +
                   ",\"branch\":\"" + action->branch + "\""
             : String("\"ordinal\":null,\"descriptor_id\":null,"
                      "\"action_id\":null,\"role\":null,\"round\":null,"
                      "\"branch\":null");
  publishedReport =
      String("{\"schema_version\":3,\"kind\":\"") + kReportKind +
      "\",\"valid\":" +
      (driverCalled ? "true" : "false") + "," + identityJson() +
      ",\"classification\":\"" + kClassification +
      "\",\"boot_nonce\":\"" + bootNonce() + "\"," + actionFields +
      ",\"job_id\":" +
      (action ? String(action->ordinal) : String("null")) +
      ",\"terminal_state\":\"FAULT\",\"result\":false,\"error\":\"" +
      error + "\",\"driver_called\":" +
      (driverCalled ? "true" : "false") +
      ",\"driver_call_count_for_action\":" +
      String(driverCalled ? driverCallCountForAction : 0) +
      ",\"total_driver_call_count\":" + String(totalDriverCallCount) +
      ",\"phase\":" + String(persistentPhase) +
      ",\"phase_name\":\"" + phaseName(persistentPhase) +
      "\",\"next_ordinal\":" + String(nextOrdinal) +
      ",\"no_retry\":true,\"no_recovery\":true" +
      (driver ? String(",\"driver\":") + driverEvidenceJson(*driver)
              : String("")) +
      "}";
}

void enterFault(const char *error, const ActionDescriptor *action,
                bool driverCalled = false,
                const EpdOperationReport *driver = nullptr) {
  executePending = false;
  uint8_t ordinal = action ? action->ordinal : nextOrdinal;
  if (ordinal < 1 || ordinal > kActionCount) ordinal = kActionCount;
  persistCursor(kPhaseFault, ordinal);
  state = RuntimeState::FaultLocked;
  publishFaultReport(error, action, driverCalled, driver);
}

void rejectMutation(int statusCode, const char *error,
                    const ActionDescriptor *action) {
  enterFault(error, action);
  server.send(statusCode, "application/json",
              String("{\"accepted\":false,\"fault_locked\":true,") +
                  "\"error\":\"" + error +
                  "\",\"no_retry\":true,\"no_recovery\":true}");
}

void handleArm() {
  ++armRequestCount;
  if (!refreshCursorEvidence()) {
    rejectMutation(503, "arm_cursor_invalid", nullptr);
    return;
  }
  const ActionDescriptor *action = currentAction();
  if (state != RuntimeState::Ready || persistentPhase != kPhaseReady ||
      !action) {
    rejectMutation(409, "arm_duplicate_complete_or_not_ready", action);
    return;
  }
  const char *contractError =
      validateMutationContract(*action, kArmIntent, false);
  if (contractError) {
    rejectMutation(400, contractError, action);
    return;
  }
  if (!fixtureSelfCheckPassed || !gpioInitialized || !storeReady) {
    rejectMutation(503, "arm_preflight_not_ready", action);
    return;
  }
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_GUARD_DIRECTION_AB_V1_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_ENDPOINT_AB_V1_BUILD)
  if (epdReadBusy() != 1) {
    rejectMutation(503, "arm_busy_not_idle_high", action);
    return;
  }
#endif

  armNonceHigh = esp_random();
  armNonceLow = esp_random();
  if ((armNonceHigh | armNonceLow) == 0) armNonceLow = 1;
  driverCallCountForAction = 0;
  if (!persistCursor(kPhaseArmed, action->ordinal)) {
    rejectMutation(503, "persistent_armed_write_failed", action);
    return;
  }
  state = RuntimeState::Armed;
  server.send(
      201, "application/json",
      String("{\"accepted\":true,\"armed\":true,") + identityJson() +
          ",\"classification\":\"" + kClassification +
          "\",\"ordinal\":" + String(action->ordinal) +
          ",\"descriptor_id\":\"" + action->descriptorId +
          "\",\"action_id\":\"" + action->actionId +
          "\",\"role\":\"" + action->role +
          "\",\"round\":" + String(action->round) +
          ",\"branch\":\"" + action->branch +
          "\",\"boot_nonce\":\"" + bootNonce() +
          "\",\"arm_nonce\":\"" + armNonce() +
          "\",\"phase\":1,\"phase_name\":\"ARMED\"," +
          "\"not_hardware_authorization\":true}");
}

void handleExecute() {
  ++executeRequestCount;
  if (!refreshCursorEvidence()) {
    rejectMutation(503, "execute_cursor_invalid", nullptr);
    return;
  }
  const ActionDescriptor *action = currentAction();
  if (state != RuntimeState::Armed || persistentPhase != kPhaseArmed ||
      !action) {
    rejectMutation(409, "execute_duplicate_stale_or_not_armed", action);
    return;
  }
  const char *contractError =
      validateMutationContract(*action, kExecuteIntent, true);
  if (contractError) {
    rejectMutation(400, contractError, action);
    return;
  }
  if (!fixtureSelfCheckPassed || !gpioInitialized || !storeReady ||
      driverCallCountForAction != 0) {
    rejectMutation(503, "execute_preflight_not_ready", action);
    return;
  }
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_GUARD_DIRECTION_AB_V1_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_ENDPOINT_AB_V1_BUILD)
  if (epdReadBusy() != 1) {
    rejectMutation(503, "execute_busy_not_idle_high", action);
    return;
  }
#endif
  // Consume the one-shot durably before acknowledging or dispatching it.
  if (!persistCursor(kPhaseConsumed, action->ordinal)) {
    rejectMutation(503, "persistent_consumed_write_failed", action);
    return;
  }
  jobQueuedAtMs = millis();
  state = RuntimeState::Queued;
  executePending = true;
  server.send(
      202, "application/json",
      String("{\"accepted\":true,\"job_id\":") +
          String(action->ordinal) + "," + identityJson() +
          ",\"classification\":\"" + kClassification +
          "\",\"ordinal\":" + String(action->ordinal) +
          ",\"descriptor_id\":\"" + action->descriptorId +
          "\",\"action_id\":\"" + action->actionId +
          "\",\"role\":\"" + action->role +
          "\",\"round\":" + String(action->round) +
          ",\"branch\":\"" + action->branch +
          "\",\"boot_nonce\":\"" + bootNonce() +
          "\",\"execute_consumed\":true,\"phase\":2," +
          "\"phase_name\":\"CONSUMED\",\"no_retry\":true," +
          "\"no_recovery\":true}");
}

void installRoutes() {
  static const char *headers[] = {
      "Content-Type",      "Content-Length",    "Transfer-Encoding",
      kBuildHeader,        kTestHeader,          kCampaignHeader,
      kActionHeader,       kOrdinalHeader,       kDescriptorHeader,
      kBootNonceHeader,    kArmNonceHeader,      kIntentHeader,
  };
  server.collectHeaders(headers, sizeof(headers) / sizeof(headers[0]));
  server.on(kVersionRoute, HTTP_GET, []() {
    if (requireReadOnlyRequest())
      server.send(200, "application/json", versionJson());
  });
  server.on(kManifestRoute, HTTP_GET, []() {
    if (requireReadOnlyRequest())
      server.send(200, "application/json", manifestJson());
  });
  server.on(kStatusRoute, HTTP_GET, []() {
    if (requireReadOnlyRequest())
      server.send(200, "application/json", statusJson());
  });
  server.on(kReportRoute, HTTP_GET, []() {
    if (requireReadOnlyRequest())
      server.send(200, "application/json", publishedReport);
  });
  server.on(kArmRoute, HTTP_POST, handleArm);
  server.on(kExecuteRoute, HTTP_POST, handleExecute);
  server.onNotFound([]() {
    if (server.method() == HTTP_POST) {
      rejectMutation(404, "unknown_mutation_route", currentAction());
      return;
    }
    server.send(404, "application/json", "{\"error\":\"not_found\"}");
  });
}

void startWiFi() {
  if (strlen(WIFI_STA_SSID) > 0) {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_STA_SSID, WIFI_STA_PASSWORD);
    const uint32_t startedAt = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - startedAt < 15000UL) {
      delay(250);
    }
    if (WiFi.status() == WL_CONNECTED) {
      Serial.printf("%s WiFi STA IP: %s\n", kBootLabel,
                    WiFi.localIP().toString().c_str());
      return;
    }
  }
  WiFi.mode(WIFI_AP);
  WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASSWORD);
  Serial.printf("%s WiFi AP IP: %s\n", kBootLabel,
                WiFi.softAPIP().toString().c_str());
}

void restartHttpListenerAfterBlockingPanelIo() {
#ifdef MF1750_PARTIAL_HOLD_BUILD
  // A Spectra-6 refresh blocks loop()/handleClient() for roughly 30-35 s.
  // Closing and reopening the listener after panel I/O discards any stale
  // half-open poll connection without rebooting or replaying the action.
  server.stop();
  delay(10);
  server.begin();
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD)
  // A Spectra-6 refresh blocks loop()/handleClient() for roughly 30-35 s.
  // Closing and reopening the listener after panel I/O discards any stale
  // half-open poll connection without rebooting or replaying the action.
  server.stop();
  delay(10);
  server.begin();
#endif
}

void executePendingAction() {
  if (!executePending) return;
  const ActionDescriptor *action = currentAction();
  if (!refreshCursorEvidence() || persistentPhase != kPhaseConsumed ||
      state != RuntimeState::Queued || !action ||
      driverCallCountForAction != 0) {
    enterFault("runtime_queue_or_cursor_mismatch", action);
    return;
  }
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_GUARD_DIRECTION_AB_V1_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_ENDPOINT_AB_V1_BUILD)
  if (epdReadBusy() != 1) {
    enterFault("dispatch_busy_not_idle_high", action);
    return;
  }
#endif

  executePending = false;
  state = RuntimeState::Running;
  jobStartedAtMs = millis();
  ++driverCallCountForAction;
  ++totalDriverCallCount;
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_GUARD_DIRECTION_AB_V1_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_ENDPOINT_AB_V1_BUILD)
  const bool result = action->driverRole == EpdChromaGridRole::White
                          ? epdDisplayCompiledFactoryOtpWhiteRecovery()
                          : epdDisplayCompiledChromaGrid(action->driverRole);
#else
  const bool result = epdDisplayCompiledChromaGrid(action->driverRole);
#endif
  jobFinishedAtMs = millis();
  const EpdOperationReport &driver = epdGetLastOperationReport();

  if (!result) {
    persistCursor(kPhaseFault, action->ordinal);
    state = RuntimeState::FaultLocked;
    publishFaultReport("driver_operation_failed", action, true, &driver);
    restartHttpListenerAfterBlockingPanelIo();
    return;
  }

  const uint8_t completedOrdinal = action->ordinal;
  const uint8_t followingOrdinal = completedOrdinal + 1;
  if (!persistCursor(kPhaseReady, followingOrdinal)) {
    enterFault("persistent_next_ready_write_failed", action, true, &driver);
    restartHttpListenerAfterBlockingPanelIo();
    return;
  }
  state = followingOrdinal == kTerminalOrdinal ? RuntimeState::Complete
                                               : RuntimeState::Ready;
  publishedReport =
      String("{\"schema_version\":3,\"kind\":\"") + kReportKind +
      "\",\"valid\":true," +
      identityJson() + ",\"classification\":\"" + kClassification +
      "\",\"boot_nonce\":\"" + bootNonce() +
      "\",\"ordinal\":" + String(completedOrdinal) +
      ",\"descriptor_id\":\"" + action->descriptorId +
      "\",\"action_id\":\"" + action->actionId +
      "\",\"role\":\"" + action->role +
      "\",\"round\":" + String(action->round) +
      ",\"branch\":\"" + action->branch +
      "\",\"job_id\":" + String(completedOrdinal) +
      ",\"terminal_state\":\"COMPLETE\",\"result\":true," +
      "\"driver_called\":true,\"driver_call_count_for_action\":1," +
      "\"total_driver_call_count\":" + String(totalDriverCallCount) +
      ",\"phase\":0,\"phase_name\":\"READY\",\"next_ordinal\":" +
      String(followingOrdinal) + ",\"campaign_complete\":" +
      (followingOrdinal == kTerminalOrdinal ? "true" : "false") +
      ",\"no_retry\":true,\"no_recovery\":true," +
      "\"job_queued_at_ms\":" + String(jobQueuedAtMs) +
      ",\"job_started_at_ms\":" + String(jobStartedAtMs) +
       ",\"job_finished_at_ms\":" + String(jobFinishedAtMs) +
       ",\"driver\":" + driverEvidenceJson(driver) + "}";
  restartHttpListenerAfterBlockingPanelIo();
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(50);
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_GUARD_DIRECTION_AB_V1_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_ENDPOINT_AB_V1_BUILD)
  Serial.printf("\nMF1750 %s campaign booting\n", kBootLabel);
#else
  Serial.printf("\nMF1750 %s factory-OTP campaign booting\n", kBootLabel);
#endif
  Serial.printf("Build: %s\n", kBuildTag);
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_GUARD_DIRECTION_AB_V1_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_ENDPOINT_AB_V1_BUILD)
  Serial.println(
      "Factory-OTP white anchors plus fixed L535 partial actions; "
      "transport codes are not colour claims");
  Serial.println(
      "No startup refresh/raw ingress/electrical write/auto-chain/retry");
#else
  Serial.println("Factory OTP only: transport codes are not colour claims");
  Serial.println(
      "No startup refresh/raw ingress/LUT/electrical write/auto-chain/retry");
#endif

  bootNonceHigh = esp_random();
  bootNonceLow = esp_random();
  if ((bootNonceHigh | bootNonceLow) == 0) bootNonceLow = 1;

#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_GUARD_DIRECTION_AB_V1_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_ENDPOINT_AB_V1_BUILD)
  fixtureSelfCheckPassed = epdValidateCompiledChromaGridFixtures() &&
                           epdValidateCompiledFactoryOtpWhiteRecoveryFixture();
#else
  fixtureSelfCheckPassed = epdValidateCompiledChromaGridFixtures();
#endif
  storeReady = cursorStore.begin(kNvsNamespace, false /* readOnly */);
  const bool cursorValid = refreshCursorEvidence();

  if (!fixtureSelfCheckPassed) {
    state = RuntimeState::FaultLocked;
    publishFaultReport("compiled_fixture_self_check_failed", nullptr, false,
                       nullptr);
  } else if (!storeReady) {
    state = RuntimeState::FaultLocked;
    publishFaultReport("cursor_store_open_failed", nullptr, false, nullptr);
  } else if (!cursorValid) {
    state = RuntimeState::FaultLocked;
    publishFaultReport("persistent_cursor_invalid", nullptr, false, nullptr);
  } else if (persistentPhase != kPhaseReady) {
    // A reboot after ARM/EXECUTE or fault never resumes or retries an action.
    enterFault("non_ready_cursor_seen_at_boot", currentAction(), false,
               nullptr);
  } else {
    epdBegin();
    gpioInitialized = true;
    state = nextOrdinal == kTerminalOrdinal ? RuntimeState::Complete
                                            : RuntimeState::Ready;
    publishNoExecuteReport();
  }

  startWiFi();
  installRoutes();
  server.begin();
  Serial.printf("Read-only manifest: %s\n", kManifestRoute);
  Serial.printf("Bodyless per-action ARM: POST %s\n", kArmRoute);
  Serial.printf("Bodyless per-action EXECUTE: POST %s\n", kExecuteRoute);
}

void loop() {
  server.handleClient();
  executePendingAction();
  delay(2);
}


