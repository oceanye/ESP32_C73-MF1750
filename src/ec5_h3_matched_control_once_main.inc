// Shared fail-closed one-action HTTP/NVS envelope for the two matched-control
// images. The including main must provide the frozen kH3mc* constants, marker
// symbols, and action-specific validate/execute/JSON functions.

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

#ifndef EPD_ENABLE_TEST_PATTERN
#error "Matched-control images require explicit EPD_ENABLE_TEST_PATTERN=0"
#endif

#if EPD_ENABLE_TEST_PATTERN != 0
#error "Matched-control images must never refresh during startup"
#endif

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600 &&
                  EPD_FRAME_BYTES == 307200 &&
                  EPD_CONTROLLER_FRAME_BYTES == 153600,
              "matched-control images require frozen cascade geometry");
static_assert(kH3mcTerminalOrdinal == kH3mcActionOrdinal + 1,
              "one-action cursor must advance exactly once");

namespace {

WebServer h3mcServer(80);
Preferences h3mcCursorStore;

static constexpr char kH3mcNvsKey[] = "used_v2";
static constexpr char kH3mcBuildHeader[] = "X-EC5-Build-Tag";
static constexpr char kH3mcTestHeader[] = "X-EC5-Test-Id";
static constexpr char kH3mcCampaignHeader[] = "X-EC5-Campaign-Id";
static constexpr char kH3mcActionHeader[] = "X-EC5-Action-Id";
static constexpr char kH3mcOrdinalHeader[] = "X-EC5-Ordinal";
static constexpr char kH3mcDescriptorHeader[] = "X-EC5-Descriptor-Id";
static constexpr char kH3mcBootNonceHeader[] = "X-EC5-Boot-Nonce";
static constexpr char kH3mcArmNonceHeader[] = "X-EC5-Arm-Nonce";
static constexpr char kH3mcIntentHeader[] = "X-EC5-Intent";

static constexpr uint8_t kH3mcPhaseReady = 0;
static constexpr uint8_t kH3mcPhaseArmed = 1;
static constexpr uint8_t kH3mcPhaseConsumed = 2;
static constexpr uint8_t kH3mcPhaseFault = 3;

enum class H3mcState : uint8_t {
  BootSelfCheck,
  Ready,
  Armed,
  Queued,
  Running,
  Complete,
  FaultLocked,
};

H3mcState h3mcState = H3mcState::BootSelfCheck;
bool h3mcFixtureSelfCheckPassed = false;
bool h3mcRunningAppElfShaValid = false;
bool h3mcGpioInitialized = false;
bool h3mcStoreReady = false;
bool h3mcKeyPresent = false;
bool h3mcExecutePending = false;
uint8_t h3mcPersistentPhase = kH3mcPhaseReady;
uint8_t h3mcNextOrdinal = kH3mcActionOrdinal;
uint16_t h3mcCursorRaw = kH3mcActionOrdinal;
uint32_t h3mcBootNonceHigh = 0;
uint32_t h3mcBootNonceLow = 0;
uint32_t h3mcArmNonceHigh = 0;
uint32_t h3mcArmNonceLow = 0;
uint32_t h3mcArmRequestCount = 0;
uint32_t h3mcExecuteRequestCount = 0;
uint32_t h3mcTotalDriverCallCount = 0;
uint8_t h3mcDriverCallCountForAction = 0;
uint32_t h3mcQueuedAtMs = 0;
uint32_t h3mcStartedAtMs = 0;
uint32_t h3mcFinishedAtMs = 0;
char h3mcRunningAppElfSha256[65] = {};
String h3mcPublishedReport =
    "{\"schema_version\":1,\"valid\":false,"
    "\"error\":\"boot_self_check\"}";

const char *h3mcStateName(H3mcState value) {
  switch (value) {
    case H3mcState::BootSelfCheck:
      return "boot_self_check";
    case H3mcState::Ready:
      return "ready";
    case H3mcState::Armed:
      return "armed";
    case H3mcState::Queued:
      return "queued";
    case H3mcState::Running:
      return "running";
    case H3mcState::Complete:
      return "complete";
    case H3mcState::FaultLocked:
      return "fault_locked";
  }
  return "fault_locked";
}

const char *h3mcPhaseName(uint8_t phase) {
  switch (phase) {
    case kH3mcPhaseReady:
      return "READY";
    case kH3mcPhaseArmed:
      return "ARMED";
    case kH3mcPhaseConsumed:
      return "CONSUMED";
    case kH3mcPhaseFault:
      return "FAULT";
  }
  return "INVALID";
}

String h3mcHex32(uint32_t value) {
  char output[9] = {};
  snprintf(output, sizeof(output), "%08lx",
           static_cast<unsigned long>(value));
  return String(output);
}

String h3mcBootNonce() {
  return h3mcHex32(h3mcBootNonceHigh) + h3mcHex32(h3mcBootNonceLow);
}

String h3mcArmNonce() {
  return h3mcHex32(h3mcArmNonceHigh) + h3mcHex32(h3mcArmNonceLow);
}

bool h3mcLoadRunningAppElfSha256() {
  std::memset(h3mcRunningAppElfSha256, 0,
              sizeof(h3mcRunningAppElfSha256));
  const esp_app_desc_t *description = esp_ota_get_app_description();
  if (description == nullptr) return false;
  static constexpr char kLowerHex[] = "0123456789abcdef";
  for (size_t index = 0; index < sizeof(description->app_elf_sha256);
       ++index) {
    const uint8_t value = description->app_elf_sha256[index];
    h3mcRunningAppElfSha256[index * 2] = kLowerHex[value >> 4];
    h3mcRunningAppElfSha256[index * 2 + 1] = kLowerHex[value & 0x0FU];
  }
  h3mcRunningAppElfSha256[64] = '\0';
  return true;
}

uint16_t h3mcEncodeCursor(uint8_t phase, uint8_t ordinal) {
  return static_cast<uint16_t>((static_cast<uint16_t>(phase) << 8) | ordinal);
}

bool h3mcCursorFieldsValid(uint8_t phase, uint8_t ordinal) {
  if (phase == kH3mcPhaseReady)
    return ordinal == kH3mcActionOrdinal ||
           ordinal == kH3mcTerminalOrdinal;
  return phase <= kH3mcPhaseFault && ordinal == kH3mcActionOrdinal;
}

bool h3mcRefreshCursorEvidence() {
  if (!h3mcStoreReady) return false;
  h3mcKeyPresent = h3mcCursorStore.isKey(kH3mcNvsKey);
  h3mcCursorRaw =
      h3mcKeyPresent
          ? h3mcCursorStore.getUShort(kH3mcNvsKey, 0)
          : h3mcEncodeCursor(kH3mcPhaseReady, kH3mcActionOrdinal);
  h3mcPersistentPhase = static_cast<uint8_t>((h3mcCursorRaw >> 8) & 0xFFU);
  h3mcNextOrdinal = static_cast<uint8_t>(h3mcCursorRaw & 0xFFU);
  return h3mcCursorFieldsValid(h3mcPersistentPhase, h3mcNextOrdinal);
}

bool h3mcPersistCursor(uint8_t phase, uint8_t ordinal) {
  if (!h3mcStoreReady || !h3mcCursorFieldsValid(phase, ordinal)) return false;
  const uint16_t wanted = h3mcEncodeCursor(phase, ordinal);
  if (h3mcCursorStore.putUShort(kH3mcNvsKey, wanted) != sizeof(uint16_t))
    return false;
  if (!h3mcRefreshCursorEvidence()) return false;
  return h3mcKeyPresent && h3mcCursorRaw == wanted &&
         h3mcPersistentPhase == phase && h3mcNextOrdinal == ordinal;
}

bool h3mcRequestHasBodyOrArguments() {
  if (h3mcServer.args() != 0 || h3mcServer.hasArg("plain")) return true;
  const String contentType = h3mcServer.header("Content-Type");
  const String transferEncoding = h3mcServer.header("Transfer-Encoding");
  const String contentLength = h3mcServer.header("Content-Length");
  if (!contentType.isEmpty() || !transferEncoding.isEmpty()) return true;
  return !contentLength.isEmpty() && contentLength != "0";
}

bool h3mcRequireReadOnlyRequest() {
  if (!h3mcRequestHasBodyOrArguments()) return true;
  h3mcServer.send(
      400, "application/json",
      "{\"error\":\"read_only_route_rejects_body_or_arguments\"}");
  return false;
}

bool h3mcExactHeader(const char *name, const String &expected) {
  return h3mcServer.hasHeader(name) && h3mcServer.header(name) == expected;
}

const char *h3mcValidateMutationContract(const char *intent,
                                         bool requireArmNonce) {
  if (h3mcRequestHasBodyOrArguments()) return "body_or_arguments_forbidden";
  if (!h3mcExactHeader(kH3mcBuildHeader, kH3mcBuildTag))
    return "build_tag_missing_or_mismatch";
  if (!h3mcExactHeader(kH3mcTestHeader, kH3mcTestId))
    return "test_id_missing_or_mismatch";
  if (!h3mcExactHeader(kH3mcCampaignHeader, kH3mcCampaignId))
    return "campaign_id_missing_or_mismatch";
  if (!h3mcExactHeader(kH3mcActionHeader, kH3mcActionId))
    return "action_id_missing_or_mismatch";
  if (!h3mcExactHeader(kH3mcOrdinalHeader, String(kH3mcActionOrdinal)))
    return "ordinal_missing_or_mismatch";
  if (!h3mcExactHeader(kH3mcDescriptorHeader, kH3mcDescriptorId))
    return "descriptor_id_missing_or_mismatch";
  if (!h3mcExactHeader(kH3mcBootNonceHeader, h3mcBootNonce()))
    return "boot_nonce_missing_or_stale";
  if (!h3mcExactHeader(kH3mcIntentHeader, intent))
    return "intent_missing_or_mismatch";
  if (!requireArmNonce && h3mcServer.hasHeader(kH3mcArmNonceHeader))
    return "arm_nonce_forbidden_during_arm";
  if (requireArmNonce &&
      !h3mcExactHeader(kH3mcArmNonceHeader, h3mcArmNonce()))
    return "arm_nonce_missing_or_stale";
  return nullptr;
}

String h3mcIdentityJson() {
  return String("\"build_tag\":\"") + kH3mcBuildTag +
         "\",\"test_id\":\"" + kH3mcTestId +
         "\",\"campaign_id\":\"" + kH3mcCampaignId +
         "\",\"profile_id\":\"" + kH3mcProfileId +
         "\",\"environment\":\"" + kH3mcEnvironmentId +
         "\",\"device_api_version\":\"" + kH3mcDeviceApiVersion +
         "\",\"identity_revision\":\"" + kH3mcIdentityRevision +
         "\",\"running_app_elf_sha256\":\"" +
         h3mcRunningAppElfSha256 + "\",\"contract_id\":\"" +
         kH3mcContractId + "\",\"transaction_descriptor_sha256\":\"" +
         kH3mcDescriptorId +
         "\",\"transaction_descriptor_marker\":\"" +
         kH3mcTransactionDescriptorMarker +
         "\",\"command_audit_marker\":\"" + kH3mcCommandAuditMarker +
         "\"";
}

String h3mcActionJson() {
  return String("{\"ordinal\":") + String(kH3mcActionOrdinal) +
         ",\"role\":\"" + kH3mcRole + "\",\"descriptor_id\":\"" +
         kH3mcDescriptorId + "\",\"action_id\":\"" + kH3mcActionId +
         "\",\"frame_sha256\":\"" + kH3mcFrameSha256 +
         "\",\"cs1_dtm_sha256\":\"" + kH3mcCs1DtmSha256 +
         "\",\"cs2_dtm_sha256\":\"" + kH3mcCs2DtmSha256 + "\"}";
}

String h3mcNvsContractJson() {
  return String("\"nvs_contract\":{\"namespace\":\"") +
         kH3mcNvsNamespace + "\",\"key\":\"" + kH3mcNvsKey +
         "\",\"encoding\":"
         "\"uint16_high_byte_phase_low_byte_ordinal\"," +
         "\"initial_cursor\":" + String(kH3mcActionOrdinal) +
         ",\"terminal_cursor\":" + String(kH3mcTerminalOrdinal) +
         ",\"clear_route\":false,\"persistent_across_reboot\":true}";
}

String h3mcUnprovenRisksJson() {
  return "\"unproven_risks\":["
         "{\"id\":\"C1\",\"status\":\"unproven\","
         "\"claim\":\"PSR_5F69_TO_5FE9_DERIVATION_AND_INSERTION\"},"
         "{\"id\":\"C2\",\"status\":\"unproven\","
         "\"claim\":\"WF20_25_HEADER_PWR_PLL_BINDING_AND_ORDER\"},"
         "{\"id\":\"C3\",\"status\":\"unproven\","
         "\"claim\":\"E9_01_MEANING_AND_BUSY_SEMANTICS\"},"
         "{\"id\":\"C4\",\"status\":\"unproven\","
         "\"claim\":\"CROSS_GENERATION_SEQUENCE_ON_SPD1657_E2802\"},"
         "{\"id\":\"C5\",\"status\":\"unproven\","
         "\"claim\":\"CS2_ACCEPTANCE_WITHOUT_READBACK_AND_SINGLE_BUSY\"},"
         "{\"id\":\"C6\",\"status\":\"unproven\","
         "\"claim\":\"PANEL_FPL_FILM_LOT_TEMPERATURE_AND_VCOM_MATCH\"},"
         "{\"id\":\"C7\",\"status\":\"unproven\","
         "\"claim\":\"NO_R20_R21_RESULT_IDENTIFIES_HIDDEN_FALLBACK_STATE\"},"
         "{\"id\":\"C8\",\"status\":\"unproven\","
         "\"claim\":\"POST_POF_TO_FACTORY_OTP_RECOVERY_CONTRACT\"}]";
}

String h3mcVersionJson() {
  return String("{\"schema_version\":1,\"kind\":\"") +
         kH3mcKindPrefix + "-version\"," + h3mcIdentityJson() +
         ",\"classification\":\"" + kH3mcClassification +
         "\",\"profile\":" + h3mcOnceProfileJson() +
         ",\"action_count\":1,\"startup_refresh\":false,"
         "\"raw_ingress\":false,\"retry\":false,"
         "\"automatic_chaining\":false,\"automatic_recovery\":false,"
         "\"profile_switch\":false,"
         "\"live_authorized\":false}";
}

String h3mcManifestJson() {
  return String("{\"schema_version\":1,\"kind\":\"") +
         kH3mcKindPrefix + "-manifest\"," + h3mcIdentityJson() +
         ",\"classification\":\"" + kH3mcClassification +
         "\",\"profile\":" + h3mcOnceProfileJson() +
         ",\"action_count\":1,\"one_driver_call_per_action\":true,"
         "\"startup_refresh\":false,\"raw_frame_ingress\":false,"
         "\"raw_lut_ingress\":false,"
         "\"electrical_parameter_ingress\":false,"
         "\"timing_parameter_ingress\":false,\"retry\":false,"
         "\"automatic_chaining\":false,\"automatic_recovery\":false,"
         "\"profile_switch\":false,\"vcom_write\":false,"
         "\"vcom_sweep\":false,"
         "\"requires_new_exact_authorization\":true,"
         "\"j2_state_is_operator_assertion_not_firmware_detection\":true,"
         "\"actions\":[" + h3mcActionJson() + "]," +
         h3mcUnprovenRisksJson() + "," + h3mcOnceSequenceJson() + "," +
         h3mcNvsContractJson() + "}";
}

String h3mcGpioJson() {
  if (!h3mcGpioInitialized)
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

String h3mcStatusJson() {
  const bool cursorValid = h3mcRefreshCursorEvidence();
  return String("{\"schema_version\":1,\"kind\":\"") +
         kH3mcKindPrefix + "-status\"," + h3mcIdentityJson() +
         ",\"boot_nonce\":\"" + h3mcBootNonce() +
         "\",\"state\":\"" + h3mcStateName(h3mcState) +
         "\",\"phase\":" + String(h3mcPersistentPhase) +
         ",\"phase_name\":\"" + h3mcPhaseName(h3mcPersistentPhase) +
         "\",\"cursor_raw\":" + String(h3mcCursorRaw) +
         ",\"next_ordinal\":" + String(h3mcNextOrdinal) +
         ",\"campaign_complete\":" +
         (h3mcPersistentPhase == kH3mcPhaseReady &&
                  h3mcNextOrdinal == kH3mcTerminalOrdinal
              ? "true"
              : "false") +
         ",\"fixture_self_check_passed\":" +
         (h3mcFixtureSelfCheckPassed ? "true" : "false") +
         ",\"cursor_valid\":" + (cursorValid ? "true" : "false") +
         ",\"persistent_key_present\":" +
         (h3mcKeyPresent ? "true" : "false") +
         ",\"execute_pending\":" +
         (h3mcExecutePending ? "true" : "false") +
         ",\"arm_request_count\":" + String(h3mcArmRequestCount) +
         ",\"execute_request_count\":" +
         String(h3mcExecuteRequestCount) +
         ",\"total_driver_call_count\":" +
         String(h3mcTotalDriverCallCount) + "," + h3mcGpioJson() + "}";
}

void h3mcPublishNoExecuteReport() {
  h3mcPublishedReport =
      String("{\"schema_version\":1,\"kind\":\"") +
      kH3mcKindPrefix + "-report\",\"valid\":false," +
      h3mcIdentityJson() + ",\"terminal_state\":\"NOT_EXECUTED\"," +
      "\"result\":false,\"error\":\"no_execute_report\"," +
      "\"driver_called\":false,\"driver_call_count_for_action\":0,"
      "\"no_retry\":true," + h3mcOnceReportFields() + "}";
}

void h3mcPublishFaultReport(const char *error, bool driverCalled,
                            const EpdOperationReport *driver = nullptr) {
  h3mcPublishedReport =
      String("{\"schema_version\":1,\"kind\":\"") +
      kH3mcKindPrefix + "-report\",\"valid\":" +
      (driverCalled ? "true" : "false") + "," + h3mcIdentityJson() +
      ",\"job_id\":" + String(kH3mcActionOrdinal) +
      ",\"ordinal\":" + String(kH3mcActionOrdinal) +
      ",\"action_id\":\"" + kH3mcActionId +
      "\",\"terminal_state\":\"FAULT\",\"result\":false," +
      "\"error\":\"" + error + "\",\"driver_called\":" +
      (driverCalled ? "true" : "false") +
      ",\"driver_call_count_for_action\":" +
      String(driverCalled ? h3mcDriverCallCountForAction : 0) +
      ",\"no_retry\":true," + h3mcOnceReportFields() +
      (driver ? String(",\"driver\":") + h3mcOnceDriverJson()
              : String("")) +
      "}";
}

void h3mcEnterFault(const char *error, bool driverCalled = false,
                    const EpdOperationReport *driver = nullptr) {
  h3mcExecutePending = false;
  h3mcPersistCursor(kH3mcPhaseFault, kH3mcActionOrdinal);
  h3mcState = H3mcState::FaultLocked;
  h3mcPublishFaultReport(error, driverCalled, driver);
}

void h3mcRejectMutation(int statusCode, const char *error) {
  h3mcEnterFault(error);
  h3mcServer.send(statusCode, "application/json",
                   String("{\"accepted\":false,\"fault_locked\":true,") +
                       "\"error\":\"" + error +
                       "\",\"no_retry\":true}");
}

void h3mcHandleArm() {
  ++h3mcArmRequestCount;
  if (!h3mcRefreshCursorEvidence()) {
    h3mcRejectMutation(503, "arm_cursor_invalid");
    return;
  }
  if (h3mcState != H3mcState::Ready ||
      h3mcPersistentPhase != kH3mcPhaseReady ||
      h3mcNextOrdinal != kH3mcActionOrdinal) {
    h3mcRejectMutation(409, "arm_duplicate_complete_or_not_ready");
    return;
  }
  const char *error = h3mcValidateMutationContract(kH3mcArmIntent, false);
  if (error) {
    h3mcRejectMutation(400, error);
    return;
  }
  if (!h3mcFixtureSelfCheckPassed || !h3mcGpioInitialized ||
      !h3mcStoreReady || h3mcDriverCallCountForAction != 0) {
    h3mcRejectMutation(503, "arm_preflight_not_ready");
    return;
  }
  h3mcArmNonceHigh = esp_random();
  h3mcArmNonceLow = esp_random();
  if ((h3mcArmNonceHigh | h3mcArmNonceLow) == 0) h3mcArmNonceLow = 1;
  if (!h3mcPersistCursor(kH3mcPhaseArmed, kH3mcActionOrdinal)) {
    h3mcRejectMutation(503, "persistent_armed_write_failed");
    return;
  }
  h3mcState = H3mcState::Armed;
  h3mcServer.send(
      201, "application/json",
      String("{\"accepted\":true,\"armed\":true,") +
          h3mcIdentityJson() + ",\"ordinal\":" +
          String(kH3mcActionOrdinal) + ",\"action_id\":\"" +
          kH3mcActionId + "\",\"boot_nonce\":\"" + h3mcBootNonce() +
          "\",\"arm_nonce\":\"" + h3mcArmNonce() +
          "\",\"not_hardware_authorization\":true}");
}

void h3mcHandleExecute() {
  ++h3mcExecuteRequestCount;
  if (!h3mcRefreshCursorEvidence()) {
    h3mcRejectMutation(503, "execute_cursor_invalid");
    return;
  }
  if (h3mcState != H3mcState::Armed ||
      h3mcPersistentPhase != kH3mcPhaseArmed ||
      h3mcNextOrdinal != kH3mcActionOrdinal) {
    h3mcRejectMutation(409, "execute_duplicate_stale_or_not_armed");
    return;
  }
  const char *error = h3mcValidateMutationContract(kH3mcExecuteIntent, true);
  if (error) {
    h3mcRejectMutation(400, error);
    return;
  }
  if (!h3mcFixtureSelfCheckPassed || !h3mcGpioInitialized ||
      !h3mcStoreReady || h3mcDriverCallCountForAction != 0) {
    h3mcRejectMutation(503, "execute_preflight_not_ready");
    return;
  }
  if (!h3mcPersistCursor(kH3mcPhaseConsumed, kH3mcActionOrdinal)) {
    h3mcRejectMutation(503, "persistent_consumed_write_failed");
    return;
  }
  h3mcQueuedAtMs = millis();
  h3mcState = H3mcState::Queued;
  h3mcExecutePending = true;
  h3mcServer.send(
      202, "application/json",
      String("{\"accepted\":true,\"job_id\":") +
          String(kH3mcActionOrdinal) + "," + h3mcIdentityJson() +
          ",\"action_id\":\"" + kH3mcActionId +
          "\",\"execute_consumed\":true,\"no_retry\":true,"
          "\"automatic_chaining\":false}");
}

void h3mcInstallRoutes() {
  static const char *headers[] = {
      "Content-Type",         "Content-Length",
      "Transfer-Encoding",    kH3mcBuildHeader,
      kH3mcTestHeader,         kH3mcCampaignHeader,
      kH3mcActionHeader,       kH3mcOrdinalHeader,
      kH3mcDescriptorHeader,   kH3mcBootNonceHeader,
      kH3mcArmNonceHeader,     kH3mcIntentHeader,
  };
  h3mcServer.collectHeaders(headers, sizeof(headers) / sizeof(headers[0]));
  const String versionRoute = String(kH3mcBaseRoute) + "/version";
  const String manifestRoute = String(kH3mcBaseRoute) + "/manifest";
  const String statusRoute = String(kH3mcBaseRoute) + "/status";
  const String reportRoute = String(kH3mcBaseRoute) + "/report";
  const String armRoute = String(kH3mcBaseRoute) + "/arm";
  const String executeRoute = String(kH3mcBaseRoute) + "/execute";
  h3mcServer.on(versionRoute, HTTP_GET, []() {
    if (h3mcRequireReadOnlyRequest())
      h3mcServer.send(200, "application/json", h3mcVersionJson());
  });
  h3mcServer.on(manifestRoute, HTTP_GET, []() {
    if (h3mcRequireReadOnlyRequest())
      h3mcServer.send(200, "application/json", h3mcManifestJson());
  });
  h3mcServer.on(statusRoute, HTTP_GET, []() {
    if (h3mcRequireReadOnlyRequest())
      h3mcServer.send(200, "application/json", h3mcStatusJson());
  });
  h3mcServer.on(reportRoute, HTTP_GET, []() {
    if (h3mcRequireReadOnlyRequest())
      h3mcServer.send(200, "application/json", h3mcPublishedReport);
  });
  h3mcServer.on(armRoute, HTTP_POST, h3mcHandleArm);
  h3mcServer.on(executeRoute, HTTP_POST, h3mcHandleExecute);
  h3mcServer.onNotFound([]() {
    if (h3mcServer.method() == HTTP_POST) {
      h3mcRejectMutation(404, "unknown_mutation_route");
      return;
    }
    h3mcServer.send(404, "application/json", "{\"error\":\"not_found\"}");
  });
}

void h3mcStartWiFi() {
  if (std::strlen(WIFI_STA_SSID) > 0) {
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

void h3mcExecutePendingAction() {
  if (!h3mcExecutePending) return;
  if (!h3mcRefreshCursorEvidence() ||
      h3mcPersistentPhase != kH3mcPhaseConsumed ||
      h3mcNextOrdinal != kH3mcActionOrdinal ||
      h3mcState != H3mcState::Queued || h3mcDriverCallCountForAction != 0) {
    h3mcEnterFault("runtime_queue_or_cursor_mismatch");
    return;
  }
  h3mcExecutePending = false;
  h3mcState = H3mcState::Running;
  h3mcStartedAtMs = millis();
  ++h3mcDriverCallCountForAction;
  ++h3mcTotalDriverCallCount;
  const bool result = h3mcOnceExecuteFixture();
  h3mcFinishedAtMs = millis();
  const EpdOperationReport &driver = epdGetLastOperationReport();
  if (!result) {
    h3mcPersistCursor(kH3mcPhaseFault, kH3mcActionOrdinal);
    h3mcState = H3mcState::FaultLocked;
    h3mcPublishFaultReport("driver_operation_failed", true, &driver);
    return;
  }
  if (!h3mcPersistCursor(kH3mcPhaseReady, kH3mcTerminalOrdinal)) {
    h3mcEnterFault("persistent_terminal_write_failed", true, &driver);
    return;
  }
  h3mcState = H3mcState::Complete;
  h3mcPublishedReport =
      String("{\"schema_version\":1,\"kind\":\"") +
      kH3mcKindPrefix + "-report\",\"valid\":true," +
      h3mcIdentityJson() + ",\"profile_id\":\"" + kH3mcProfileId +
      "\",\"job_id\":" + String(kH3mcActionOrdinal) +
      ",\"ordinal\":" + String(kH3mcActionOrdinal) +
      ",\"action_id\":\"" + kH3mcActionId +
      "\",\"terminal_state\":\"COMPLETE\",\"result\":true," +
      "\"driver_called\":true,\"driver_call_count_for_action\":1,"
      "\"total_driver_call_count\":" +
      String(h3mcTotalDriverCallCount) + ",\"next_ordinal\":" +
      String(kH3mcTerminalOrdinal) +
      ",\"campaign_complete\":true,\"no_retry\":true,"
      "\"automatic_chaining\":false,\"job_queued_at_ms\":" +
      String(h3mcQueuedAtMs) + ",\"job_started_at_ms\":" +
      String(h3mcStartedAtMs) + ",\"job_finished_at_ms\":" +
      String(h3mcFinishedAtMs) + "," + h3mcOnceReportFields() +
      ",\"driver\":" + h3mcOnceDriverJson() + "}";
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(50);
  Serial.printf("\nMF1750 H3 matched-control boot: %s ordinal %u\n",
                kH3mcProfileId, static_cast<unsigned>(kH3mcActionOrdinal));
  Serial.println(
      "No startup refresh/raw ingress/retry/autochain/profile switch");
  h3mcBootNonceHigh = esp_random();
  h3mcBootNonceLow = esp_random();
  if ((h3mcBootNonceHigh | h3mcBootNonceLow) == 0) h3mcBootNonceLow = 1;
  h3mcRunningAppElfShaValid = h3mcLoadRunningAppElfSha256();
  h3mcFixtureSelfCheckPassed =
      h3mcRunningAppElfShaValid && h3mcOnceValidateFixture();
  h3mcStoreReady =
      h3mcCursorStore.begin(kH3mcNvsNamespace, false /* readOnly */);
  const bool cursorValid = h3mcRefreshCursorEvidence();
  if (!h3mcRunningAppElfShaValid) {
    h3mcState = H3mcState::FaultLocked;
    h3mcPublishFaultReport("running_app_elf_sha256_self_check_failed", false);
  } else if (!h3mcFixtureSelfCheckPassed) {
    h3mcState = H3mcState::FaultLocked;
    h3mcPublishFaultReport("compiled_fixture_self_check_failed", false);
  } else if (!h3mcStoreReady) {
    h3mcState = H3mcState::FaultLocked;
    h3mcPublishFaultReport("cursor_store_open_failed", false);
  } else if (!cursorValid) {
    h3mcState = H3mcState::FaultLocked;
    h3mcPublishFaultReport("persistent_cursor_invalid", false);
  } else if (h3mcPersistentPhase == kH3mcPhaseReady &&
             h3mcNextOrdinal == kH3mcTerminalOrdinal) {
    h3mcState = H3mcState::Complete;
    h3mcPublishNoExecuteReport();
  } else if (h3mcPersistentPhase != kH3mcPhaseReady ||
             h3mcNextOrdinal != kH3mcActionOrdinal) {
    h3mcEnterFault("non_unused_cursor_seen_at_boot");
  } else {
    epdBegin();
    h3mcGpioInitialized = true;
    h3mcState = H3mcState::Ready;
    h3mcPublishNoExecuteReport();
  }
  h3mcStartWiFi();
  h3mcInstallRoutes();
  h3mcServer.begin();
}

void loop() {
  h3mcServer.handleClient();
  h3mcExecutePendingAction();
  delay(2);
}
