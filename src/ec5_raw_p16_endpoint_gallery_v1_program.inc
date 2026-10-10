#include <Arduino.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <esp_system.h>

#include <cstdio>
#include <cstring>

#include "epd_config.h"
#include "ec5_chroma_grid_epd_driver.h"

// Isolated fixed-input RAW-P16 endpoint gallery campaign. Its only visible
// action is one compiled full-screen atlas. Factory-OTP white before and after
// this action belongs to independent containment campaigns.
// There is no startup refresh, raw ingress, electrical write, automatic
// chaining, retry, recovery, or NVS clear route.
#if MF1750_ENABLE_CHROMA_GRID != 1
#error "Chroma grid requires MF1750_ENABLE_CHROMA_GRID=1"
#endif

#if !defined(MF1750_RAW_P16_ENDPOINT_GALLERY_V1_BUILD)
#error "RAW-P16 endpoint gallery requires its isolated build macro"
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
static constexpr uint8_t kActionCount = 1;
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

#include "ec5_raw_p16_endpoint_gallery_v1_main_config.inc"

static_assert(sizeof(kActions) / sizeof(kActions[0]) == kActionCount,
              "Chroma grid action count changed");

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
bool campaignBootKeyPresent = false;
bool campaignBootMatchesCurrent = false;
bool executePending = false;
uint8_t persistentPhase = kPhaseReady;
uint8_t nextOrdinal = 1;
uint16_t cursorRaw = 1;
uint64_t persistedCampaignBootNonce = 0;
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

uint64_t currentBootNonceValue() {
  return (static_cast<uint64_t>(bootNonceHigh) << 32) |
         static_cast<uint64_t>(bootNonceLow);
}

String persistedCampaignBootNonceHex() {
  return hex32(static_cast<uint32_t>(persistedCampaignBootNonce >> 32)) +
         hex32(static_cast<uint32_t>(persistedCampaignBootNonce));
}

uint16_t encodeCursor(uint8_t phase, uint8_t ordinal) {
  return static_cast<uint16_t>((static_cast<uint16_t>(phase) << 8) | ordinal);
}

bool cursorFieldsValid(uint8_t phase, uint8_t ordinal) {
  if (phase == kPhaseReady) return ordinal >= 1 && ordinal <= kTerminalOrdinal;
  return phase <= kPhaseFault && ordinal >= 1 && ordinal <= kActionCount;
}

constexpr bool bootBindingAdmissionAllowed(bool cursorKeyExists,
                                           uint8_t phase, uint8_t ordinal,
                                           bool bootKeyExists,
                                           bool persistedMatchesCurrent) {
  return bootKeyExists
             ? persistedMatchesCurrent
             : (!cursorKeyExists && phase == kPhaseReady && ordinal == 1);
}

static_assert(bootBindingAdmissionAllowed(false, kPhaseReady, 1, false,
                                          false),
              "fresh campaign boot must be admitted once");
static_assert(!bootBindingAdmissionAllowed(true, kPhaseReady, 1, false,
                                           false),
              "existing cursor cannot create a missing boot binding");
static_assert(!bootBindingAdmissionAllowed(true, kPhaseReady, 2, false,
                                           false),
              "intermediate cursor cannot create a boot binding");
static_assert(!bootBindingAdmissionAllowed(true, kPhaseReady, 2, true,
                                           false),
              "rebooted intermediate cursor cannot resume");
static_assert(bootBindingAdmissionAllowed(true, kPhaseReady, 2, true, true),
              "same boot intermediate cursor remains admissible");

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

bool refreshCampaignBootBindingEvidence() {
  if (!storeReady) return false;
  campaignBootKeyPresent = cursorStore.isKey(kNvsBootKey);
  persistedCampaignBootNonce = campaignBootKeyPresent
                                     ? cursorStore.getULong64(kNvsBootKey, 0)
                                     : 0;
  campaignBootMatchesCurrent =
      campaignBootKeyPresent && persistedCampaignBootNonce != 0 &&
      persistedCampaignBootNonce == currentBootNonceValue();
  return campaignBootKeyPresent && persistedCampaignBootNonce != 0;
}

bool initializeOrValidateCampaignBootBinding() {
  if (!storeReady) return false;
  const bool bindingPresentAndValid = refreshCampaignBootBindingEvidence();
  if (!bootBindingAdmissionAllowed(keyPresent, persistentPhase, nextOrdinal,
                                   campaignBootKeyPresent,
                                   campaignBootMatchesCurrent)) {
    return false;
  }
  if (!campaignBootKeyPresent) {
    // The campaign boot identity is created exactly once, only for a wholly
    // fresh cursor. A legacy/intermediate cursor can never self-upgrade into a
    // resumable campaign after reboot or after running containment firmware.
    const uint64_t wanted = currentBootNonceValue();
    if (wanted == 0 ||
        cursorStore.putULong64(kNvsBootKey, wanted) != sizeof(uint64_t))
      return false;
  } else if (!bindingPresentAndValid) {
    return false;
  }
  return refreshCampaignBootBindingEvidence() && campaignBootMatchesCurrent;
}

bool campaignBootBindingAllowsMutation(uint8_t ordinal) {
  if (ordinal < 1 || ordinal > kActionCount) return false;
  return refreshCampaignBootBindingEvidence() &&
         campaignBootMatchesCurrent;
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
         String(kTerminalOrdinal) + ",\"campaign_boot_key\":\"" +
         kNvsBootKey +
         "\",\"campaign_boot_encoding\":"
         "\"uint64 high32_then_low32_hex_nonce\"," +
         "\"campaign_boot_initial_key_present\":false," +
         "\"campaign_boot_initialize_only_when_cursor_key_absent_ready_ordinal1\":"
         "true,\"campaign_boot_readback_required\":true," +
         "\"current_boot_exact_match_required\":true," +
         "\"reboot_resume_allowed\":false," +
         "\"post_containment_resume_allowed\":false}";
}

String baselineContractJson() {
  return String("\"baseline_contract\":{") +
         "\"ordinal\":null,\"role\":\"" + kBaselineRole +
         "\",\"external_anchor_required\":true,"
         "\"one_visible_refresh_required\":false}";
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

String transportDispatchJson(const ActionDescriptor &action) {
  if (action.driverRole == EpdChromaGridRole::White) {
    return ",\"palette_source\":\"FACTORY_OTP\",\"global_header\":null,"
           "\"profile_id\":null,\"global_tuple_id\":null,"
           "\"waveform_binding\":null,"
           "\"driver_entry\":"
           "\"epdDisplayCompiledFactoryOtpWhiteRecovery\"";
  }
  // This is the exact canonical mixed-R20 binding frozen by the offline pack.
  // Global-header "active" selects the PWR/PLL/header family; it does not make
  // the controller R20 payloads equal.
  return ",\"palette_source\":\"L535_RUNTIME\","
         "\"global_header\":\"active\","
         "\"profile_id\":"
         "\"LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535\","
         "\"global_tuple_id\":"
         "\"741848b5bf2cc07b642293d5aa3b216f1ac6eb9cdc36e7099e4230a8a837ad42\","
         "\"waveform_binding\":{"
         "\"controller_r20_payloads_byte_identical\":false,"
         "\"cs1_r20_prefix_bytes\":535,"
         "\"cs1_r20_prefix_sha256\":"
         "\"716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b\","
         "\"cs2_r20_prefix_bytes\":535,"
         "\"cs2_r20_prefix_sha256\":"
         "\"2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26\","
         "\"global_header\":\"active\","
         "\"global_header_sha256\":"
         "\"48a53562060e9c822334a73f900dbd1323fd3fe096576ef75663b64216e275c8\","
         "\"global_tuple_id\":"
         "\"741848b5bf2cc07b642293d5aa3b216f1ac6eb9cdc36e7099e4230a8a837ad42\","
         "\"id\":"
         "\"LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535\","
         "\"name\":\"active\",\"r21_bytes\":704,"
         "\"r21_sha256\":"
         "\"24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f\"},"
         "\"driver_entry\":\"epdDisplayCompiledChromaGrid\"";
}

String bootAdmissionJson(const ActionDescriptor &action) {
  const bool first = action.ordinal == 1;
  return String("{\"campaign_boot_binding_key\":\"") + kNvsBootKey +
         "\",\"admission\":\"" +
         (first ? "FRESH_CURSOR_AND_BOOT_KEY_ABSENT_ONLY"
                : "SAME_PERSISTED_CAMPAIGN_BOOT_ONLY") +
         "\",\"required_prior_terminal_state\":" +
         (first ? String("null") : String("\"COMPLETE\"")) +
         ",\"required_prior_ordinal\":" +
         (first ? String("null") : String(action.ordinal - 1)) +
         ",\"firmware_arm_gate\":true,\"firmware_execute_gate\":true," +
         "\"firmware_dispatch_gate\":true," +
         "\"reboot_resume_allowed\":false," +
         "\"post_containment_resume_allowed\":false}";
}

String actionJson(const ActionDescriptor &action) {
  return String("{\"ordinal\":") + String(action.ordinal) +
         ",\"descriptor_id\":\"" + action.descriptorId +
         "\",\"action_id\":\"" + action.actionId +
         "\",\"prior_static_action_id\":" +
         (action.priorActionId ? String("\"") + action.priorActionId + "\""
                               : String("null")) +
         ",\"boot_admission\":" + bootAdmissionJson(action) +
         ",\"role\":\"" + action.role + "\",\"round\":" +
         String(action.round) + ",\"branch\":\"" + action.branch +
         "\"" + transportDispatchJson(action) +
         ",\"frame_sha256\":\"" + action.frameSha256 +
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
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD)
         "\"raw_frame_ingress\":false,\"runtime_lut_write\":true," +
#else
         "\"raw_frame_ingress\":false,\"runtime_lut_write\":false," +
#endif
         "\"electrical_parameter_write\":false,\"dither\":false," +
         "\"spatial_mixing\":false,\"retry\":false,\"recovery\":false," +
         kCampaignCapabilitiesJson + "," +
         nvsContractJson() + "," + baselineContractJson() + "," +
         kExternalWhiteAnchorJson + "}";
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
                  "\"factory_otp\":false,\"custom_lut_or_waveform\":true,"
                  "\"synchronous_both_controllers\":true,"
                  "\"one_driver_call_per_action\":true,"
                  "\"automatic_chaining\":false,\"startup_refresh\":false,"
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD)
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
            "," + kExternalWhiteAnchorJson + "}";
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
  const bool campaignBootBindingValid = refreshCampaignBootBindingEvidence();
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
         ",\"campaign_boot_key_present\":" +
         (campaignBootKeyPresent ? "true" : "false") +
         ",\"persisted_campaign_boot_nonce\":" +
         (campaignBootBindingValid
              ? String("\"") + persistedCampaignBootNonceHex() + "\""
              : String("null")) +
         ",\"campaign_boot_matches_current\":" +
         (campaignBootMatchesCurrent ? "true" : "false") +
         ",\"device_enforced_same_boot\":true," +
         "\"reboot_resume_allowed\":false," +
         "\"post_containment_resume_allowed\":false" +
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
                   ",\"branch\":\"" + action->branch + "\"" +
                   transportDispatchJson(*action)
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
  if (action && !campaignBootBindingAllowsMutation(action->ordinal)) {
    rejectMutation(409, "arm_campaign_boot_binding_mismatch", action);
    return;
  }
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
  if (epdReadBusy() != 1) {
    rejectMutation(503, "arm_busy_not_idle_high", action);
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
          ",\"branch\":\"" + action->branch + "\"" +
          transportDispatchJson(*action) +
          ",\"boot_nonce\":\"" + bootNonce() +
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
  if (action && !campaignBootBindingAllowsMutation(action->ordinal)) {
    rejectMutation(409, "execute_campaign_boot_binding_mismatch", action);
    return;
  }
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
  if (epdReadBusy() != 1) {
    rejectMutation(503, "execute_busy_not_idle_high", action);
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
          ",\"branch\":\"" + action->branch + "\"" +
          transportDispatchJson(*action) +
          ",\"boot_nonce\":\"" + bootNonce() +
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
  if (!campaignBootBindingAllowsMutation(action->ordinal)) {
    enterFault("dispatch_campaign_boot_binding_mismatch", action);
    return;
  }
  if (epdReadBusy() != 1) {
    enterFault("dispatch_busy_not_idle_high", action);
    return;
  }

  executePending = false;
  state = RuntimeState::Running;
  jobStartedAtMs = millis();
  ++driverCallCountForAction;
  ++totalDriverCallCount;
  const bool result = epdDisplayCompiledChromaGrid(action->driverRole);
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
      ",\"branch\":\"" + action->branch + "\"" +
      transportDispatchJson(*action) +
      ",\"job_id\":" + String(completedOrdinal) +
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
  Serial.printf("\nMF1750 %s campaign booting\n", kBootLabel);
  Serial.printf("Build: %s\n", kBuildTag);
  Serial.println(
      "One fixed active L535 2x4-per-controller RAW-P16 endpoint atlas; "
      "runtime code 7 is an unqualified endpoint and background");
  Serial.println(
      "No startup refresh/raw ingress/electrical write/auto-chain/retry");

  bootNonceHigh = esp_random();
  bootNonceLow = esp_random();
  if ((bootNonceHigh | bootNonceLow) == 0) bootNonceLow = 1;

  fixtureSelfCheckPassed = epdValidateCompiledChromaGridFixtures();
  storeReady = cursorStore.begin(kNvsNamespace, false /* readOnly */);
  const bool cursorValid = refreshCursorEvidence();
  const bool campaignBootBindingValid =
      cursorValid && initializeOrValidateCampaignBootBinding();

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
  } else if (!campaignBootBindingValid) {
    // No reboot (including a return from the independent containment image)
    // may turn a persisted READY ordinal into a resumable main campaign.
    enterFault("campaign_boot_binding_mismatch_at_boot", currentAction(),
               false, nullptr);
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
