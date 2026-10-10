#include <Arduino.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <esp_ota_ops.h>
#include <esp_system.h>

#include <cstdio>
#include <cstring>

#include "epd_config.h"
#include "epd_diagnostics.h"
#include "epd_driver.h"

#if MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY != 1
#error "OTP-white recovery main requires its isolated fixture"
#endif

#ifndef EPD_ENABLE_TEST_PATTERN
#error "OTP-white recovery requires explicit EPD_ENABLE_TEST_PATTERN=0"
#endif

#if EPD_ENABLE_TEST_PATTERN != 0
#error "OTP-white recovery must never refresh during startup"
#endif

#if (MF1750_OTP_WHITE_FOR_PROFILE_WF20_25 + \
     MF1750_OTP_WHITE_FOR_PROFILE_WF23_25) != 1
#error "OTP-white recovery must bind exactly one campaign profile"
#endif

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600 &&
                  EPD_FRAME_BYTES == 307200 &&
                  EPD_CONTROLLER_FRAME_BYTES == 153600,
              "OTP-white recovery requires frozen cascade geometry");

namespace {

WebServer server(80);
Preferences usedStore;

static constexpr const char *kClassification =
    "FACTORY_OTP_WHITE_RECOVERY_ONE_ACTION_NO_RUNTIME_PAYLOAD";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_EMPIRICAL_H3_DEVICE_V1";
static constexpr const char *kIdentityRevision = "otp-white-recovery-v1";
static constexpr const char *kTestId =
    "EC5-FACTORY-OTP-WHITE-RECOVERY-V1";
static constexpr const char *kFrameSha256 =
    "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d";
static constexpr const char *kDtmSha256 =
    "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158";

#if MF1750_OTP_WHITE_FOR_PROFILE_WF20_25 == 1
static constexpr const char *kProfileId = "WF20_25";
static constexpr const char *kEnvironmentId = "ec5_otp_white_wf20_25";
static constexpr const char *kCampaignId = "EC5_EMPIRICAL_H3_WF20_25_V1";
static constexpr const char *kBuildTag =
    "MF1750_EC5_FACTORY_OTP_WHITE_WF20_25_V1_2026-08-11";
static constexpr const char *kContractId =
    "83053b14a8033b135a824e1e83a157134feedabfb5518977424a894db5854f51";
static constexpr const char *kNvsNamespace = "otpw_w20_v1";
static constexpr const char *kDescriptorId =
    "221fac09353639ebf31b5173b5bf10bd40d025ebeaebcc057e137f3e588f289c";
static constexpr const char *kActionId =
    "6495a2c5182bf0879a4c288c26dd0d24bdbc8f1a5794d5dfac898049d11dbd82";
extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF20_25|ROLE=OTP_WHITE|SHA256=221fac09353639ebf31b5173b5bf10bd40d025ebeaebcc057e137f3e588f289c\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
#elif MF1750_OTP_WHITE_FOR_PROFILE_WF23_25 == 1
static constexpr const char *kProfileId = "WF23_25";
static constexpr const char *kEnvironmentId = "ec5_otp_white_wf23_25";
static constexpr const char *kCampaignId = "EC5_EMPIRICAL_H3_WF23_25_V1";
static constexpr const char *kBuildTag =
    "MF1750_EC5_FACTORY_OTP_WHITE_WF23_25_V1_2026-08-11";
static constexpr const char *kContractId =
    "0d69f55551cd9fdc9d77c4c39daade15ac2019ce725d982007091a9d441dc5c3";
static constexpr const char *kNvsNamespace = "otpw_w23_v1";
static constexpr const char *kDescriptorId =
    "caf98b119d3355727d234f5452adfc5fb0ccc9e1f5a37e8a7c1076cbc253e8db";
static constexpr const char *kActionId =
    "4acae8345b3084657c50f1babc1a5fc3f91898e0b5c64ee6be67459d730c9856";
extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE|SHA256=caf98b119d3355727d234f5452adfc5fb0ccc9e1f5a37e8a7c1076cbc253e8db\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
#endif

static constexpr const char *kNvsKey = "used_v1";
static constexpr const char *kVersionRoute =
    "/api/ec5/factory-otp-white/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/factory-otp-white/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/factory-otp-white/status";
static constexpr const char *kReportRoute =
    "/api/ec5/factory-otp-white/report";
static constexpr const char *kArmRoute =
    "/api/ec5/factory-otp-white/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/factory-otp-white/execute";
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
    "ARM_ONE_FIXED_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ONE_FIXED_FACTORY_OTP_WHITE_ONCE";
static constexpr uint8_t kPhaseReady = 0;
static constexpr uint8_t kPhaseArmed = 1;
static constexpr uint8_t kPhaseConsumed = 2;
static constexpr uint8_t kPhaseFault = 3;
static constexpr uint8_t kActionOrdinal = 2;
static constexpr uint8_t kTerminalOrdinal = 3;

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
bool runningAppElfShaValid = false;
bool gpioInitialized = false;
bool storeReady = false;
bool keyPresent = false;
bool executePending = false;
uint8_t persistentPhase = kPhaseReady;
uint8_t nextOrdinal = kActionOrdinal;
uint16_t cursorRaw = kActionOrdinal;
uint32_t bootNonceHigh = 0;
uint32_t bootNonceLow = 0;
uint32_t armNonceHigh = 0;
uint32_t armNonceLow = 0;
uint32_t armRequestCount = 0;
uint32_t executeRequestCount = 0;
uint32_t totalDriverCallCount = 0;
uint8_t driverCallCountForAction = 0;
uint32_t queuedAtMs = 0;
uint32_t startedAtMs = 0;
uint32_t finishedAtMs = 0;
char runningAppElfSha256[65] = {};
String publishedReport =
    "{\"schema_version\":1,\"valid\":false,\"error\":\"boot_self_check\"}";

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

String hex32(uint32_t value) {
  char output[9] = {};
  snprintf(output, sizeof(output), "%08lx",
           static_cast<unsigned long>(value));
  return String(output);
}

String bootNonce() { return hex32(bootNonceHigh) + hex32(bootNonceLow); }
String armNonce() { return hex32(armNonceHigh) + hex32(armNonceLow); }

bool loadRunningAppElfSha256() {
  std::memset(runningAppElfSha256, 0, sizeof(runningAppElfSha256));
  const esp_app_desc_t *description = esp_ota_get_app_description();
  if (description == nullptr) return false;

  static constexpr char kLowerHex[] = "0123456789abcdef";
  for (size_t index = 0; index < sizeof(description->app_elf_sha256);
       ++index) {
    const uint8_t value = description->app_elf_sha256[index];
    runningAppElfSha256[index * 2] = kLowerHex[value >> 4];
    runningAppElfSha256[index * 2 + 1] = kLowerHex[value & 0x0FU];
  }
  runningAppElfSha256[64] = '\0';
  return true;
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

uint16_t encodeCursor(uint8_t phase, uint8_t ordinal) {
  return static_cast<uint16_t>((static_cast<uint16_t>(phase) << 8) | ordinal);
}

bool cursorFieldsValid(uint8_t phase, uint8_t ordinal) {
  if (phase == kPhaseReady)
    return ordinal == kActionOrdinal || ordinal == kTerminalOrdinal;
  return phase <= kPhaseFault && ordinal == kActionOrdinal;
}

bool refreshCursorEvidence() {
  if (!storeReady) return false;
  keyPresent = usedStore.isKey(kNvsKey);
  cursorRaw = keyPresent ? usedStore.getUShort(kNvsKey, 0)
                         : encodeCursor(kPhaseReady, kActionOrdinal);
  persistentPhase = static_cast<uint8_t>((cursorRaw >> 8) & 0xFFU);
  nextOrdinal = static_cast<uint8_t>(cursorRaw & 0xFFU);
  return cursorFieldsValid(persistentPhase, nextOrdinal);
}

bool persistCursor(uint8_t phase, uint8_t ordinal) {
  if (!storeReady || !cursorFieldsValid(phase, ordinal)) return false;
  const uint16_t wanted = encodeCursor(phase, ordinal);
  if (usedStore.putUShort(kNvsKey, wanted) != sizeof(uint16_t)) return false;
  if (!refreshCursorEvidence()) return false;
  return keyPresent && cursorRaw == wanted && persistentPhase == phase &&
         nextOrdinal == ordinal;
}

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

const char *validateMutationContract(const char *intent,
                                     bool requireArmNonce) {
  if (requestHasBodyOrArguments()) return "body_or_arguments_forbidden";
  if (!exactHeader(kBuildHeader, kBuildTag)) return "build_tag_mismatch";
  if (!exactHeader(kTestHeader, kTestId)) return "test_id_mismatch";
  if (!exactHeader(kCampaignHeader, kCampaignId)) return "campaign_id_mismatch";
  if (!exactHeader(kActionHeader, kActionId)) return "action_id_mismatch";
  if (!exactHeader(kOrdinalHeader, "2")) return "ordinal_mismatch";
  if (!exactHeader(kDescriptorHeader, kDescriptorId))
    return "descriptor_id_mismatch";
  if (!exactHeader(kBootNonceHeader, bootNonce())) return "boot_nonce_mismatch";
  if (!exactHeader(kIntentHeader, intent)) return "intent_mismatch";
  if (!requireArmNonce && server.hasHeader(kArmNonceHeader))
    return "arm_nonce_forbidden";
  if (requireArmNonce && !exactHeader(kArmNonceHeader, armNonce()))
    return "arm_nonce_mismatch";
  return nullptr;
}

String identityJson() {
  return String("\"build_tag\":\"") + kBuildTag + "\",\"test_id\":\"" +
         kTestId + "\",\"campaign_id\":\"" + kCampaignId +
         "\",\"profile_id\":\"" + kProfileId +
         "\",\"environment\":\"" + kEnvironmentId +
         "\",\"device_api_version\":\"" + kDeviceApiVersion +
         "\",\"identity_revision\":\"" + kIdentityRevision +
         "\",\"running_app_elf_sha256\":\"" + runningAppElfSha256 +
         "\",\"contract_id\":\"" + kContractId +
         "\",\"transaction_descriptor_sha256\":\"" + kDescriptorId +
         "\",\"transaction_descriptor_marker\":\"" +
         kTransactionDescriptorMarker + "\"";
}

String profileJson() {
  return String("{\"profile_id\":\"") + kProfileId +
         "\",\"compiled_profile_count\":1,\"auto_selected\":false,"
         "\"apparent_temperature_min_c\":0,"
         "\"apparent_temperature_max_c\":37,"
         "\"temperature_policy\":"
         "\"factory_otp_existing_observed_ceiling_not_vendor_band\","
         "\"temperature_limit_is_safety_qualification\":false,"
         "\"inherits_selected_vendor_profile_band\":false}";
}

String assumptionsJson() {
  return "\"unproven_assumptions\":["
         "{\"id\":\"U1\",\"status\":\"unproven\","
         "\"claim\":\"PSR_5F69_TO_5FE9_BIT_DERIVATION_AND_INSERTION\"},"
         "{\"id\":\"U2\",\"status\":\"unproven\","
         "\"claim\":\"MODE0_HEADER_PWR_PLL_REUSED_FOR_800_BYTE_MODE1_AND_ORDER\"},"
         "{\"id\":\"U3\",\"status\":\"unproven\","
         "\"claim\":\"HIDDEN_E9_DUAL_CONTROLLER_AND_BUSY_SEMANTICS\"},"
         "{\"id\":\"U4\",\"status\":\"unproven\","
         "\"claim\":\"H3_SEQUENCE_IS_CROSS_GENERATION_FROM_2020_IAR\"},"
         "{\"id\":\"U5\",\"status\":\"unproven\","
         "\"claim\":\"CS1_THEN_CS2_WITHOUT_READBACK_SINGLE_BUSY_CANNOT_PROVE_CS2_ACCEPTANCE\"},"
         "{\"id\":\"U6\",\"status\":\"unproven\","
         "\"claim\":\"FILENAME_TEMPERATURE_PANEL_FPL_FILM_LOT_MATCH_VCOM_NOT_WRITTEN_OR_SWEPT\"},"
         "{\"id\":\"U7\",\"status\":\"unproven\","
         "\"claim\":\"POST_POF_CLEANUP_AND_RUNTIME_TO_OTP_RECOVERY_EXTRAPOLATION\"}]";
}

String actionJson() {
  return String("{\"ordinal\":2,\"role\":") +
         "\"FACTORY_OTP_WHITE_RECOVERY\",\"descriptor_id\":\"" +
         kDescriptorId + "\",\"action_id\":\"" + kActionId +
         "\",\"frame_sha256\":\"" + kFrameSha256 +
         "\",\"cs1_dtm_sha256\":\"" + kDtmSha256 +
         "\",\"cs2_dtm_sha256\":\"" + kDtmSha256 + "\"}";
}

String nvsContractJson() {
  return String("\"nvs_contract\":{\"namespace\":\"") + kNvsNamespace +
         "\",\"key\":\"" + kNvsKey +
         "\",\"encoding\":\"uint16_high_byte_phase_low_byte_ordinal\","
         "\"initial_cursor\":2,\"terminal_cursor\":3,"
         "\"clear_route\":false,\"persistent_across_reboot\":true}";
}

String versionJson() {
  return String("{\"schema_version\":1,\"kind\":") +
         "\"mf1750-ec5-factory-otp-white-recovery-version\"," + identityJson() +
         ",\"classification\":\"" + kClassification +
         "\",\"profile\":" + profileJson() +
         ",\"action_count\":1,\"startup_refresh\":false,"
         "\"raw_ingress\":false,\"retry\":false,"
         "\"automatic_chaining\":false,\"profile_switch\":false,"
         "\"runtime_payload_present\":false,\"live_authorized\":false}";
}

String manifestJson() {
  return String("{\"schema_version\":1,\"kind\":") +
         "\"mf1750-ec5-factory-otp-white-recovery-manifest\"," + identityJson() +
         ",\"classification\":\"" + kClassification +
         "\",\"action_count\":1,\"one_driver_call_per_action\":true,"
         "\"startup_refresh\":false,\"raw_frame_ingress\":false,"
         "\"raw_lut_ingress\":false,"
         "\"electrical_parameter_ingress\":false,"
         "\"timing_parameter_ingress\":false,"
         "\"runtime_payload_present\":false,\"generated_include\":null,"
         "\"runtime_psr_present\":false,\"hidden_lut_command_present\":false,"
         "\"r20_present\":false,\"r21_present\":false,"
         "\"vcom_write\":false,\"vcom_sweep\":false,"
         "\"vcom_write_or_sweep\":false,\"retry\":false,"
         "\"automatic_chaining\":false,\"automatic_recovery\":false,"
         "\"profile_switch\":false,"
         "\"requires_new_exact_authorization\":true,"
         "\"j2_state_is_operator_assertion_not_firmware_detection\":true,"
         "\"factory_path\":{\"hard_reset\":true,\"psr\":\"5F69\","
         "\"tres\":\"512x600\",\"e0_per_controller\":true,"
         "\"dtm_controller_order\":[\"CS1\",\"CS2\"],"
         "\"synchronous_refresh\":true},\"actions\":[" + actionJson() +
         "]," + assumptionsJson() + "," + nvsContractJson() + "}";
}

String gpioJson() {
  if (!gpioInitialized)
    return "\"gpio_initialized\":false,\"busy\":null,\"rst\":null,"
           "\"cs\":null,\"cs2\":null,\"sck\":null,\"dc\":null,"
           "\"mosi\":null";
  return String("\"gpio_initialized\":true,\"busy\":") +
         String(epdReadBusy()) + ",\"rst\":" +
         String(digitalRead(EPD_PIN_RST)) + ",\"cs\":" +
         String(digitalRead(EPD_PIN_CS)) + ",\"cs2\":" +
         String(digitalRead(EPD_PIN_CS2)) + ",\"sck\":" +
         String(digitalRead(EPD_PIN_SCK)) + ",\"dc\":" +
         String(digitalRead(EPD_PIN_DC)) + ",\"mosi\":" +
         String(digitalRead(EPD_PIN_MOSI));
}

String statusJson() {
  const bool valid = refreshCursorEvidence();
  return String("{\"schema_version\":1,\"kind\":") +
         "\"mf1750-ec5-factory-otp-white-recovery-status\"," + identityJson() +
         ",\"profile_id\":\"" + kProfileId +
         "\",\"boot_nonce\":\"" + bootNonce() + "\",\"state\":\"" +
         stateName(state) + "\",\"phase\":" + String(persistentPhase) +
         ",\"phase_name\":\"" + phaseName(persistentPhase) +
         "\",\"cursor_raw\":" + String(cursorRaw) +
         ",\"next_ordinal\":" + String(nextOrdinal) +
         ",\"campaign_complete\":" +
         (persistentPhase == kPhaseReady && nextOrdinal == kTerminalOrdinal
              ? "true"
              : "false") +
         ",\"cursor_valid\":" + (valid ? "true" : "false") +
         ",\"persistent_key_present\":" +
         (keyPresent ? "true" : "false") +
         ",\"fixture_self_check_passed\":" +
         (fixtureSelfCheckPassed ? "true" : "false") +
         ",\"execute_pending\":" + (executePending ? "true" : "false") +
         ",\"arm_request_count\":" + String(armRequestCount) +
         ",\"execute_request_count\":" + String(executeRequestCount) +
         ",\"total_driver_call_count\":" +
         String(totalDriverCallCount) + "," + gpioJson() + "}";
}

void publishNoExecute() {
  publishedReport = String("{\"schema_version\":1,\"kind\":") +
                    "\"mf1750-ec5-factory-otp-white-recovery-report\",\"valid\":false," +
                    identityJson() +
                    ",\"terminal_state\":\"NOT_EXECUTED\"," +
                    "\"result\":false,\"driver_called\":false,"
                    "\"driver_call_count_for_action\":0,"
                    "\"no_retry\":true}";
}

void publishFault(const char *error, bool called,
                  const EpdOperationReport *driver = nullptr) {
  publishedReport = String("{\"schema_version\":1,\"kind\":") +
                    "\"mf1750-ec5-factory-otp-white-recovery-report\",\"valid\":" +
                    (called ? "true" : "false") + "," + identityJson() +
                    ",\"ordinal\":2,\"action_id\":\"" + kActionId +
                    "\",\"terminal_state\":\"FAULT\",\"result\":false," +
                    "\"error\":\"" + error + "\",\"driver_called\":" +
                    (called ? "true" : "false") +
                    ",\"driver_call_count_for_action\":" +
                    String(called ? driverCallCountForAction : 0) +
                    ",\"no_retry\":true" +
                    (driver ? String(",\"driver\":") +
                                  epdDiagnosticReportJson()
                            : String("")) +
                    "}";
}

void enterFault(const char *error, bool called = false,
                const EpdOperationReport *driver = nullptr) {
  executePending = false;
  persistCursor(kPhaseFault, kActionOrdinal);
  state = RuntimeState::FaultLocked;
  publishFault(error, called, driver);
}

void rejectMutation(int statusCode, const char *error) {
  enterFault(error);
  server.send(statusCode, "application/json",
              String("{\"accepted\":false,\"fault_locked\":true,") +
                  "\"error\":\"" + error + "\",\"no_retry\":true}");
}

void handleArm() {
  ++armRequestCount;
  if (!refreshCursorEvidence()) {
    rejectMutation(503, "arm_cursor_invalid");
    return;
  }
  if (state != RuntimeState::Ready || persistentPhase != kPhaseReady ||
      nextOrdinal != kActionOrdinal) {
    rejectMutation(409, "arm_duplicate_complete_or_not_ready");
    return;
  }
  const char *error = validateMutationContract(kArmIntent, false);
  if (error) {
    rejectMutation(400, error);
    return;
  }
  if (!fixtureSelfCheckPassed || !gpioInitialized || !storeReady ||
      driverCallCountForAction != 0) {
    rejectMutation(503, "arm_preflight_not_ready");
    return;
  }
  armNonceHigh = esp_random();
  armNonceLow = esp_random();
  if ((armNonceHigh | armNonceLow) == 0) armNonceLow = 1;
  driverCallCountForAction = 0;
  if (!persistCursor(kPhaseArmed, kActionOrdinal)) {
    rejectMutation(503, "persistent_armed_write_failed");
    return;
  }
  state = RuntimeState::Armed;
  server.send(201, "application/json",
              String("{\"accepted\":true,\"armed\":true,") +
                  identityJson() + ",\"ordinal\":2,\"action_id\":\"" +
                  kActionId + "\",\"boot_nonce\":\"" + bootNonce() +
                  "\",\"arm_nonce\":\"" + armNonce() +
                  "\",\"not_hardware_authorization\":true}");
}

void handleExecute() {
  ++executeRequestCount;
  if (!refreshCursorEvidence()) {
    rejectMutation(503, "execute_cursor_invalid");
    return;
  }
  if (state != RuntimeState::Armed || persistentPhase != kPhaseArmed ||
      nextOrdinal != kActionOrdinal) {
    rejectMutation(409, "execute_duplicate_stale_or_not_armed");
    return;
  }
  const char *error = validateMutationContract(kExecuteIntent, true);
  if (error) {
    rejectMutation(400, error);
    return;
  }
  if (!fixtureSelfCheckPassed || !gpioInitialized || !storeReady ||
      driverCallCountForAction != 0) {
    rejectMutation(503, "execute_preflight_not_ready");
    return;
  }
  if (!persistCursor(kPhaseConsumed, kActionOrdinal)) {
    rejectMutation(503, "persistent_consumed_write_failed");
    return;
  }
  queuedAtMs = millis();
  state = RuntimeState::Queued;
  executePending = true;
  server.send(202, "application/json",
              String("{\"accepted\":true,\"job_id\":2,") + identityJson() +
                  ",\"action_id\":\"" + kActionId +
                  "\",\"execute_consumed\":true,\"no_retry\":true}");
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
      rejectMutation(404, "unknown_mutation_route");
      return;
    }
    server.send(404, "application/json", "{\"error\":\"not_found\"}");
  });
}

void startWiFi() {
  if (strlen(WIFI_STA_SSID) > 0) {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_STA_SSID, WIFI_STA_PASSWORD);
    const uint32_t began = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - began < 15000UL)
      delay(250);
    if (WiFi.status() == WL_CONNECTED) return;
  }
  WiFi.mode(WIFI_AP);
  WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASSWORD);
}

void executePendingAction() {
  if (!executePending) return;
  if (!refreshCursorEvidence() || persistentPhase != kPhaseConsumed ||
      nextOrdinal != kActionOrdinal || state != RuntimeState::Queued ||
      driverCallCountForAction != 0) {
    enterFault("runtime_queue_or_cursor_mismatch");
    return;
  }
  executePending = false;
  state = RuntimeState::Running;
  startedAtMs = millis();
  ++driverCallCountForAction;
  ++totalDriverCallCount;
  const bool result = epdDisplayCompiledFactoryOtpWhiteRecovery();
  finishedAtMs = millis();
  const EpdOperationReport &driver = epdGetLastOperationReport();
  if (!result) {
    persistCursor(kPhaseFault, kActionOrdinal);
    state = RuntimeState::FaultLocked;
    publishFault("driver_operation_failed", true, &driver);
    return;
  }
  if (!persistCursor(kPhaseReady, kTerminalOrdinal)) {
    enterFault("persistent_complete_write_failed", true, &driver);
    return;
  }
  state = RuntimeState::Complete;
  publishedReport = String("{\"schema_version\":1,\"kind\":") +
                    "\"mf1750-ec5-factory-otp-white-recovery-report\",\"valid\":true," +
                    identityJson() +
                    ",\"profile_id\":\"" + kProfileId +
                    "\",\"ordinal\":2,\"action_id\":\"" + kActionId +
                    "\",\"terminal_state\":\"COMPLETE\",\"result\":true," +
                    "\"driver_called\":true,"
                    "\"driver_call_count_for_action\":1,"
                    "\"total_driver_call_count\":" +
                    String(totalDriverCallCount) +
                    ",\"next_ordinal\":3,\"campaign_complete\":true,"
                    "\"no_retry\":true,\"job_queued_at_ms\":" +
                    String(queuedAtMs) + ",\"job_started_at_ms\":" +
                    String(startedAtMs) + ",\"job_finished_at_ms\":" +
                    String(finishedAtMs) + ",\"driver\":" +
                    epdDiagnosticReportJson() + "}";
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(50);
  Serial.printf("\nMF1750 dedicated OTP-white recovery boot: %s\n", kProfileId);
  Serial.println("No startup refresh/runtime payload/raw ingress/retry/autochain");
  bootNonceHigh = esp_random();
  bootNonceLow = esp_random();
  if ((bootNonceHigh | bootNonceLow) == 0) bootNonceLow = 1;
  runningAppElfShaValid = loadRunningAppElfSha256();
  fixtureSelfCheckPassed = runningAppElfShaValid &&
                           epdValidateCompiledFactoryOtpWhiteRecoveryFixture();
  storeReady = usedStore.begin(kNvsNamespace, false /* readOnly */);
  const bool valid = refreshCursorEvidence();
  if (!runningAppElfShaValid) {
    state = RuntimeState::FaultLocked;
    publishFault("running_app_elf_sha256_self_check_failed", false);
  } else if (!fixtureSelfCheckPassed) {
    state = RuntimeState::FaultLocked;
    publishFault("compiled_fixture_self_check_failed", false);
  } else if (!storeReady) {
    state = RuntimeState::FaultLocked;
    publishFault("cursor_store_open_failed", false);
  } else if (!valid) {
    state = RuntimeState::FaultLocked;
    publishFault("persistent_cursor_invalid", false);
  } else if (persistentPhase == kPhaseReady &&
             nextOrdinal == kTerminalOrdinal) {
    state = RuntimeState::Complete;
    publishNoExecute();
  } else if (persistentPhase != kPhaseReady ||
             nextOrdinal != kActionOrdinal) {
    enterFault("non_unused_cursor_seen_at_boot");
  } else {
    epdBegin();
    gpioInitialized = true;
    state = RuntimeState::Ready;
    publishNoExecute();
  }
  startWiFi();
  installRoutes();
  server.begin();
}

void loop() {
  server.handleClient();
  executePendingAction();
  delay(2);
}
