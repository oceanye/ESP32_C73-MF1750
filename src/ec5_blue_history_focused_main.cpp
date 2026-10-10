#include <Arduino.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <esp_system.h>

#include <cstdio>
#include <cstring>

#include "epd_config.h"
#include "ec5_blue_history_focused_epd_driver.h"

// Isolated factory-OTP spatial-blue history focused. Every visible action
// is a fixed compiled frame and requires a separate bodyless ARM and EXECUTE
// request. There is no startup refresh, raw ingress, runtime LUT or electrical
// write, automatic chaining, retry, recovery, or NVS clear route.
#if MF1750_ENABLE_BLUE_HISTORY_FOCUSED != 1
#error "Blue history focused requires MF1750_ENABLE_BLUE_HISTORY_FOCUSED=1"
#endif

#ifndef EPD_ENABLE_TEST_PATTERN
#error "Blue history focused requires explicit EPD_ENABLE_TEST_PATTERN=0"
#endif

#if EPD_ENABLE_TEST_PATTERN != 0
#error "Blue history focused must never refresh during startup"
#endif

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600,
              "Blue history focused is frozen for the 1024x600 panel");
static_assert(EPD_FRAME_BYTES == 307200 &&
                  EPD_CONTROLLER_FRAME_BYTES == 153600,
              "Blue history focused requires frozen 4bpp cascade geometry");
static_assert(EPD_CS1_SOURCE_HALF == 0 && !EPD_CS1_FLIP_X &&
                  !EPD_CS1_FLIP_Y && !EPD_CS1_NIBBLE_SWAP &&
                  EPD_CS2_SOURCE_HALF == 1 && !EPD_CS2_FLIP_X &&
                  !EPD_CS2_FLIP_Y && !EPD_CS2_NIBBLE_SWAP,
              "Blue history focused mapping differs from MAP_ORIENT_V1");

namespace {

WebServer server(80);
Preferences cursorStore;

static constexpr const char *kClassification =
    "FACTORY_OTP_FIXED_BLUE_HISTORY_16_RECIPE_NO_RUNTIME_LUT";
static constexpr const char *kProfileSource = "factory_otp";
static constexpr const char *kIdentityRevision = "blue-history-focused-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_BLUE_HISTORY_FOCUSED_DEVICE_V1";
static constexpr const char *kLayoutId =
    "dual-controller-16-blue-history-large-blocks-v1";
static constexpr const char *kBuildTag =
    "MF1750_EC5_BLUE_HISTORY_FOCUSED_V1_2026-08-20";
static constexpr const char *kTestId = "EC5-BLUE-HISTORY-FOCUSED-V1";
static constexpr const char *kCampaignId =
    "EC5_BLUE_HISTORY_FOCUSED_CAMPAIGN_V1";
static constexpr const char *kContractId =
    "3d3de39d4630fc5e6203f6403f35256a32c4b8cf005f1d5c879ef59b630a678d";

static constexpr const char *kNvsNamespace = "mf1750_bhf1";
static constexpr const char *kNvsKey = "cursor_v1";

static constexpr const char *kVersionRoute =
    "/api/ec5/blue-history-focused/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/blue-history-focused/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/blue-history-focused/status";
static constexpr const char *kReportRoute =
    "/api/ec5/blue-history-focused/report";
static constexpr const char *kArmRoute =
    "/api/ec5/blue-history-focused/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/blue-history-focused/execute";

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
    "ARM_ONE_FIXED_FACTORY_OTP_BLUE_HISTORY_FOCUSED_ACTION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ARMED_FACTORY_OTP_BLUE_HISTORY_FOCUSED_ACTION_ONCE";

static constexpr uint8_t kPhaseReady = 0;
static constexpr uint8_t kPhaseArmed = 1;
static constexpr uint8_t kPhaseConsumed = 2;
static constexpr uint8_t kPhaseFault = 3;
static constexpr uint8_t kActionCount = 6;
static constexpr uint8_t kTerminalOrdinal = kActionCount + 1;

struct ActionDescriptor {
  uint8_t ordinal;
  EpdBlueHistoryFocusedRole driverRole;
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

static constexpr const char *kAPrimerFrameSha256 =
    "6fef23f683694f434b3cb06209a5e77d458248b46c7a9c49932c503b725f9527";
static constexpr const char *kAPrimerDtmSha256 =
    "f99960532731f22224ad88302f9518cc6d15c159a40e3116f52ab7f23e658980";
static constexpr const char *kATargetFrameSha256 =
    "b5350449a22c5a77315c5e2148aa3a84a9b84411445579f349c8f888f1fe6a5a";
static constexpr const char *kTarget4DtmSha256 =
    "faecfc32d3f9a1f3d5ea82a5f81754bb281e0245dc2d4da8de9011aba4395e94";
static constexpr const char *kTarget7DtmSha256 =
    "962d9e8d678e7626837a08f69c25998206056201744c138d39fbd4c7bf8efa29";
static constexpr const char *kWhiteFrameSha256 =
    "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d";
static constexpr const char *kWhiteDtmSha256 =
    "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158";
static constexpr const char *kAPrimePrimerFrameSha256 =
    "2d43f6da6ebdf58afaceff41c2359d7c82f336884df5f8fcf3d52574f8d8c186";
static constexpr const char *kAPrimePrimerDtmSha256 =
    "2c25744b8e0df4cf6f0cc7b2a9bbfa3052c96eda4900ae48a1ba67bf75b2162f";
static constexpr const char *kAPrimeTargetFrameSha256 =
    "1c547c7e4f18c7712450866dfe50e2afff069cd12901d39a343af83281e3f72c";

static constexpr ActionDescriptor kActions[] = {
    {1,
     EpdBlueHistoryFocusedRole::APrimer,
     "A_PRIMER_SOURCE_CODES_0_TO_7",
     1,
     "A_PRIMER_CS1_TARGET4_CS2_TARGET7",
     "7f3115729885e1c04957f0b45d382fa0299cf2bf7bcf5cb253a43d226b94ad83",
     "bd2cc213997298f425e31747b25e3b42fc6b598154998b659d5b5b090865d1d4",
     nullptr,
     kAPrimerFrameSha256,
     kAPrimerDtmSha256,
     kAPrimerDtmSha256,
     0x539AF5C5UL,
     0xA21BC9C5UL,
     0xA21BC9C5UL,
     {56320, 220160, 56320, 56320, 56320, 56320, 56320, 56320}},
    {2,
     EpdBlueHistoryFocusedRole::ATarget,
     "A_TARGET_BLUE_CODES_4_AND_7",
     1,
     "A_TARGET_CS1_CODE4_CS2_CODE7",
     "055d40162a5c511d042df3ef9a156f041874e556d900854150d6286586b29d95",
     "b91ffe5a8157e2351017bb2cdf58076bebf3fbb4ccd46df8129d8a54deee7931",
     "bd2cc213997298f425e31747b25e3b42fc6b598154998b659d5b5b090865d1d4",
     kATargetFrameSha256,
     kTarget4DtmSha256,
     kTarget7DtmSha256,
     0x6BD595C5UL,
     0x90821DC5UL,
     0x8337A5C5UL,
     {0, 163840, 0, 0, 225280, 0, 0, 225280}},
    {3,
     EpdBlueHistoryFocusedRole::White,
     "A_WHITE_RECOVERY",
     1,
     "A_FACTORY_OTP_WHITE_RECOVERY",
     "d6e0c9e849a8cc3b8d5303a2c121fbe614facec57bf4e8a1ba56c583d5194ae6",
     "3e06f8c30050f905a61c65e0a8549562e06108f44a4cc245d70cff469a36b68c",
     "b91ffe5a8157e2351017bb2cdf58076bebf3fbb4ccd46df8129d8a54deee7931",
     kWhiteFrameSha256,
     kWhiteDtmSha256,
     kWhiteDtmSha256,
     0x13340DC5UL,
     0xB7A855C5UL,
     0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {4,
     EpdBlueHistoryFocusedRole::APrimePrimer,
     "A_PRIME_PRIMER_SOURCE_CODES_7_TO_0",
     2,
     "A_PRIME_PRIMER_CS1_TARGET7_CS2_TARGET4",
     "bd45164d312a1bd713a9fb50b040c6d118def395156bb3052bdcc620b7ed0d36",
     "c98a2d296e505338f715f0d08f3f0320d7bcd33c0d9ad5cc29d990074ab57ff3",
     "3e06f8c30050f905a61c65e0a8549562e06108f44a4cc245d70cff469a36b68c",
     kAPrimePrimerFrameSha256,
     kAPrimePrimerDtmSha256,
     kAPrimePrimerDtmSha256,
     0x5760B5C5UL,
     0x99FEA9C5UL,
     0x99FEA9C5UL,
     {56320, 220160, 56320, 56320, 56320, 56320, 56320, 56320}},
    {5,
     EpdBlueHistoryFocusedRole::APrimeTarget,
     "A_PRIME_TARGET_BLUE_CODES_7_AND_4",
     2,
     "A_PRIME_TARGET_CS1_CODE7_CS2_CODE4",
     "5a55764ef440644a52848149c70742f7d7a14db6aadcadd1f6d9ecfa3e2b0bd0",
     "da351c575d0c5ba340141b993da4d833f6b97e2e50cb911c87e4069fdffb33ae",
     "c98a2d296e505338f715f0d08f3f0320d7bcd33c0d9ad5cc29d990074ab57ff3",
     kAPrimeTargetFrameSha256,
     kTarget7DtmSha256,
     kTarget4DtmSha256,
     0x093595C5UL,
     0x8337A5C5UL,
     0x90821DC5UL,
     {0, 163840, 0, 0, 225280, 0, 0, 225280}},
    {6,
     EpdBlueHistoryFocusedRole::White,
     "A_PRIME_WHITE_RECOVERY",
     2,
     "A_PRIME_FACTORY_OTP_WHITE_RECOVERY",
     "34f27cf6f8c0b1d8a86030fbe85d29aaefc1691e9d4db006753b9087cae117d9",
     "d416eef5239b6349ead14d1afac0d62871309d947e77cdadadc8be229990d4a0",
     "da351c575d0c5ba340141b993da4d833f6b97e2e50cb911c87e4069fdffb33ae",
     kWhiteFrameSha256,
     kWhiteDtmSha256,
     kWhiteDtmSha256,
     0x13340DC5UL,
     0xB7A855C5UL,
     0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
};

static_assert(sizeof(kActions) / sizeof(kActions[0]) == kActionCount,
              "Blue history focused must contain exactly six actions");

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

String anchorContractJson() {
  return "\"external_clean_white_anchor\":{"
         "\"campaign_id\":\"EC5_DITHER_COLOR_ATLAS_CAMPAIGN_V1\","
         "\"ordinal\":2,"
         "\"role\":\"OTP_WHITE_RECOVERY\","
         "\"action_id\":"
         "\"35639e1fddd4cfbcccbaa529faa89a046496b171b695eb678737e6ed4a35eac3\","
         "\"evidence_bound_at_release_materialization\":true,"
         "\"validated_by_device\":false,"
         "\"required_host_gate_for_ordinal_1\":true}";
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
         "\",\"transport_code_histogram\":" + histogramJson(action) +
         "}";
}

String versionJson() {
  refreshCursorEvidence();
  return String("{\"schema_version\":3,\"kind\":") +
         "\"mf1750-ec5-blue-history-focused-version\"," + identityJson() +
         ",\"classification\":\"" + kClassification +
         "\",\"layout_id\":\"" + kLayoutId +
         "\",\"driver_api_version\":\"" + EPD_DRIVER_API_VERSION +
         "\",\"profile_source\":\"" + kProfileSource +
         "\",\"action_count\":" + String(kActionCount) +
         ",\"automatic_execute\":false," +
         "\"automatic_chaining\":false,\"startup_refresh\":false," +
         "\"raw_frame_ingress\":false,\"runtime_lut_write\":false," +
         "\"electrical_parameter_write\":false,\"dither\":false," +
         "\"spatial_mixing\":false,\"history_transition_test\":true," +
         "\"single_pixel_multi_pigment_claim\":false," +
         "\"physical_colour_claim\":false,\"retry\":false," +
         "\"recovery\":false," +
         nvsContractJson() + "," + anchorContractJson() + "}";
}

String manifestJson() {
  String output = String("{\"schema_version\":3,\"kind\":") +
                  "\"mf1750-ec5-blue-history-focused-manifest\"," +
                  identityJson() + ",\"classification\":\"" +
                  kClassification + "\",\"layout_id\":\"" + kLayoutId +
                  "\",\"profile_source\":\"" + kProfileSource +
                  "\",\"action_count\":" + String(kActionCount) +
                  ",\"round_count\":2,"
                  "\"history_layout\":{" 
                  "\"controller_count\":2,\"recipe_count\":16,"
                  "\"target_codes\":[4,7],\"source_codes\":[0,1,2,3,4,5,6,7],"
                  "\"cell_width\":220,\"cell_height\":128,"
                  "\"cell_gap_x\":8,\"cell_gap_y\":8,"
                  "\"half_margin_x\":32,\"margin_y\":32,"
                  "\"a_source_order\":\"0_to_7\","
                  "\"a_prime_source_order\":\"7_to_0\","
                  "\"photo_timepoints_after_target_seconds\":[5,60,600]},"
                  "\"factory_otp\":true,\"custom_lut_or_waveform\":false,"
                  "\"synchronous_both_controllers\":true,"
                  "\"one_driver_call_per_action\":true,"
                  "\"automatic_chaining\":false,\"startup_refresh\":false,"
                  "\"raw_frame_ingress\":false,\"runtime_lut_write\":false,"
                  "\"electrical_parameter_write\":false,\"dither\":false,"
                  "\"spatial_mixing\":false,\"history_transition_test\":true,"
                  "\"single_pixel_multi_pigment_claim\":false,"
                  "\"physical_colour_claim\":false,\"retry\":false,"
                  "\"recovery\":false,\"actions\":[";
  for (uint8_t index = 0; index < kActionCount; ++index) {
    if (index != 0) output += ',';
    output += actionJson(kActions[index]);
  }
  output += String("],") + nvsContractJson() + "," + anchorContractJson() +
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
  return String("{\"schema_version\":3,\"kind\":") +
         "\"mf1750-ec5-blue-history-focused-status\"," + identityJson() +
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
      String("{\"schema_version\":3,\"kind\":") +
      "\"mf1750-ec5-blue-history-focused-report\",\"valid\":false," +
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
      String("{\"schema_version\":3,\"kind\":") +
      "\"mf1750-ec5-blue-history-focused-report\",\"valid\":" +
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
      Serial.printf("EC5 blue history focused WiFi STA IP: %s\n",
                    WiFi.localIP().toString().c_str());
      return;
    }
  }
  WiFi.mode(WIFI_AP);
  WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASSWORD);
  Serial.printf("EC5 blue history focused WiFi AP IP: %s\n",
                WiFi.softAPIP().toString().c_str());
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

  executePending = false;
  state = RuntimeState::Running;
  jobStartedAtMs = millis();
  ++driverCallCountForAction;
  ++totalDriverCallCount;
  const bool result =
      epdDisplayCompiledBlueHistoryFocused(action->driverRole);
  jobFinishedAtMs = millis();
  const EpdOperationReport &driver = epdGetLastOperationReport();

  if (!result) {
    persistCursor(kPhaseFault, action->ordinal);
    state = RuntimeState::FaultLocked;
    publishFaultReport("driver_operation_failed", action, true, &driver);
    return;
  }

  const uint8_t completedOrdinal = action->ordinal;
  const uint8_t followingOrdinal = completedOrdinal + 1;
  if (!persistCursor(kPhaseReady, followingOrdinal)) {
    enterFault("persistent_next_ready_write_failed", action, true, &driver);
    return;
  }
  state = followingOrdinal == kTerminalOrdinal ? RuntimeState::Complete
                                               : RuntimeState::Ready;
  publishedReport =
      String("{\"schema_version\":3,\"kind\":") +
      "\"mf1750-ec5-blue-history-focused-report\",\"valid\":true," +
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
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(50);
  Serial.println("\nMF1750 EC5 factory-OTP blue history focused booting");
  Serial.printf("Build: %s\n", kBuildTag);
  Serial.println("Factory OTP only: transport codes are not colour claims");
  Serial.println(
      "No startup refresh/raw ingress/LUT/electrical write/auto-chain/retry");

  bootNonceHigh = esp_random();
  bootNonceLow = esp_random();
  if ((bootNonceHigh | bootNonceLow) == 0) bootNonceLow = 1;

  fixtureSelfCheckPassed = epdValidateCompiledBlueHistoryFocusedFixtures();
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
