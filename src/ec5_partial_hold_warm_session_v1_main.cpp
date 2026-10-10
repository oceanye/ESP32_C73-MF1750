#include <Arduino.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <esp_system.h>

#include <cstdio>
#include <cstring>

#include "epd_config.h"
#include "ec5_partial_hold_warm_session_v1_epd_driver.h"

#if !defined(MF1750_PARTIAL_HOLD_WARM_SESSION_V1_BUILD) || \
    MF1750_PARTIAL_HOLD_WARM_SESSION_V1_BUILD != 1
#error "This entry point is exclusive to warm-session V1"
#endif
#if !defined(EPD_ENABLE_TEST_PATTERN) || EPD_ENABLE_TEST_PATTERN != 0
#error "Warm-session V1 must never refresh at startup"
#endif

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600 &&
                  EPD_FRAME_BYTES == 307200 &&
                  EPD_CONTROLLER_FRAME_BYTES == 153600,
              "warm-session geometry differs");

namespace {

WebServer server(80);
Preferences cursorStore;

static constexpr uint8_t kPhaseReady = 0;
static constexpr uint8_t kPhaseArmed = 1;
static constexpr uint8_t kPhaseConsumed = 2;
static constexpr uint8_t kPhaseFault = 3;
static constexpr uint8_t kActionCount = 5;
static constexpr uint8_t kTerminalOrdinal = 6;

struct ActionDescriptor {
  uint8_t ordinal;
  EpdPartialHoldWarmRole driverRole;
  const char *role;
  const char *branch;
  const char *descriptorId;
  const char *actionId;
  const char *priorActionId;
  const char *frameSha256;
  const char *cs1DtmSha256;
  const char *cs2DtmSha256;
};

#include "ec5_partial_hold_warm_session_v1_main_config.inc"

static_assert(sizeof(kActions) / sizeof(kActions[0]) == kActionCount,
              "warm session requires exactly five actions");

static constexpr const char *kVersionRoute =
    "/api/ec5/partial-hold-warm-session-v1/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/partial-hold-warm-session-v1/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/partial-hold-warm-session-v1/status";
static constexpr const char *kReportRoute =
    "/api/ec5/partial-hold-warm-session-v1/report";
static constexpr const char *kArmRoute =
    "/api/ec5/partial-hold-warm-session-v1/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/partial-hold-warm-session-v1/execute";

static constexpr const char *kBuildHeader = "X-EC5-Build-Tag";
static constexpr const char *kTestHeader = "X-EC5-Test-Id";
static constexpr const char *kCampaignHeader = "X-EC5-Campaign-Id";
static constexpr const char *kActionHeader = "X-EC5-Action-Id";
static constexpr const char *kOrdinalHeader = "X-EC5-Ordinal";
static constexpr const char *kDescriptorHeader = "X-EC5-Descriptor-Id";
static constexpr const char *kBootNonceHeader = "X-EC5-Boot-Nonce";
static constexpr const char *kArmNonceHeader = "X-EC5-Arm-Nonce";
static constexpr const char *kIntentHeader = "X-EC5-Intent";

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
uint32_t totalDriverCallCount = 0;
uint8_t driverCallCountForAction = 0;
uint32_t jobQueuedAtMs = 0;
uint32_t jobStartedAtMs = 0;
uint32_t jobFinishedAtMs = 0;
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

const char *warmStateName(EpdPartialHoldWarmState value) {
  switch (value) {
    case EpdPartialHoldWarmState::Cold:
      return "cold";
    case EpdPartialHoldWarmState::WarmExpectRed:
      return "warm_expect_red";
    case EpdPartialHoldWarmState::WarmExpectBlue:
      return "warm_expect_blue";
    case EpdPartialHoldWarmState::WarmExpectGreen:
      return "warm_expect_green";
    case EpdPartialHoldWarmState::WarmExpectRecovery:
      return "warm_expect_white_recovery";
    case EpdPartialHoldWarmState::Closed:
      return "closed_safe_pof";
    case EpdPartialHoldWarmState::Fault:
      return "fault_safe_pof_requested";
  }
  return "fault";
}

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
  cursorRaw = keyPresent ? cursorStore.getUShort(kNvsKey, 0)
                         : encodeCursor(kPhaseReady, 1);
  persistentPhase = static_cast<uint8_t>(cursorRaw >> 8);
  nextOrdinal = static_cast<uint8_t>(cursorRaw & 0xFFU);
  return cursorFieldsValid(persistentPhase, nextOrdinal);
}

bool persistCursor(uint8_t phase, uint8_t ordinal) {
  if (!storeReady || !cursorFieldsValid(phase, ordinal)) return false;
  const uint16_t wanted = encodeCursor(phase, ordinal);
  if (cursorStore.putUShort(kNvsKey, wanted) != sizeof(uint16_t)) return false;
  return refreshCursorEvidence() && keyPresent && cursorRaw == wanted;
}

const ActionDescriptor *actionForOrdinal(uint8_t ordinal) {
  if (ordinal < 1 || ordinal > kActionCount) return nullptr;
  const ActionDescriptor &action = kActions[ordinal - 1];
  return action.ordinal == ordinal ? &action : nullptr;
}

const ActionDescriptor *currentAction() { return actionForOrdinal(nextOrdinal); }

String hex32(uint32_t value) {
  char output[9] = {};
  snprintf(output, sizeof(output), "%08lx",
           static_cast<unsigned long>(value));
  return String(output);
}

String bootNonce() { return hex32(bootNonceHigh) + hex32(bootNonceLow); }
String armNonce() { return hex32(armNonceHigh) + hex32(armNonceLow); }

bool requestHasBodyOrArguments() {
  if (server.args() != 0 || server.hasArg("plain")) return true;
  const String contentType = server.header("Content-Type");
  const String transferEncoding = server.header("Transfer-Encoding");
  const String contentLength = server.header("Content-Length");
  if (!contentType.isEmpty() || !transferEncoding.isEmpty()) return true;
  return !contentLength.isEmpty() && contentLength != "0";
}

bool exactHeader(const char *name, const String &wanted) {
  return server.hasHeader(name) && server.header(name) == wanted;
}

String identityJson() {
  return String("\"build_tag\":\"") + kBuildTag +
         "\",\"test_id\":\"" + kTestId +
         "\",\"campaign_id\":\"" + kCampaignId +
         "\",\"contract_id\":\"" + kContractId + "\"";
}

String actionJson(const ActionDescriptor &action) {
  return String("{\"ordinal\":") + String(action.ordinal) +
         ",\"role\":\"" + action.role + "\",\"branch\":\"" +
         action.branch + "\",\"descriptor_id\":\"" +
         action.descriptorId + "\",\"action_id\":\"" + action.actionId +
         "\",\"prior_action_id\":" +
         (action.priorActionId ? String("\"") + action.priorActionId + "\""
                               : "null") +
         ",\"frame_sha256\":\"" + action.frameSha256 +
         "\",\"cs1_dtm_sha256\":\"" + action.cs1DtmSha256 +
         "\",\"cs2_dtm_sha256\":\"" + action.cs2DtmSha256 + "\"}";
}

String versionJson() {
  return String("{\"schema_version\":1,\"kind\":") +
         "\"mf1750-partial-hold-warm-session-version\"," +
         identityJson() +
         ",\"device_api_version\":\"MF1750_EC5_PARTIAL_HOLD_WARM_SESSION_DEVICE_V1\"," +
         "\"identity_revision\":\"partial-hold-warm-session-v1\"," +
         "\"spi_hz\":1000000,\"startup_refresh\":false," +
         "\"boot_resume\":false,\"retry\":false,\"autochain\":false," +
         "\"physical_power_control\":false}";
}

String manifestJson() {
  String actions = "[";
  for (uint8_t i = 0; i < kActionCount; ++i) {
    if (i) actions += ',';
    actions += actionJson(kActions[i]);
  }
  actions += ']';
  return String("{\"schema_version\":1,\"kind\":") +
         "\"mf1750-partial-hold-warm-session-manifest\"," +
         identityJson() + ",\"classification\":\"" + kClassification +
         "\",\"action_count\":5,\"actions\":" + actions +
         ",\"one_driver_call_per_action\":true," +
         "\"same_boot_required\":true,\"boot_resume\":false," +
         "\"unexpected_reboot_requires_physical_cut_before_recovery\":true," +
         "\"prepare_count\":1,\"hard_reset_count\":1," +
         "\"runtime_lut_upload_count\":1,\"pon_count\":1," +
         "\"patch_drf_without_pon_count\":3,\"success_pof_count\":1," +
         "\"max_warm_gap_ms\":120000,\"ptlw_command\":131," +
         "\"ptlw_payload_bytes\":9," +
         "\"ptlw_endpoint_contract\":\"xe=x+w-1;ye=y+h-1\"," +
         "\"cropped_dtm\":true,\"cdi\":255," +
         "\"partial_refresh\":true,\"command_0x83\":true," +
         "\"command_0x86\":false,\"mid_refresh_power_cut\":false," +
         "\"retry\":false,\"autochain\":false," +
         "\"physical_power_control\":false}";
}

String statusJson() {
  const ActionDescriptor *action = currentAction();
  return String("{\"schema_version\":1,\"kind\":") +
         "\"mf1750-partial-hold-warm-session-status\"," + identityJson() +
         ",\"state\":\"" + stateName(state) +
         "\",\"warm_state\":\"" +
         warmStateName(epdGetPartialHoldWarmSessionState()) +
         "\",\"warm_remaining_ms\":" +
         String(epdGetPartialHoldWarmSessionRemainingMs()) +
         ",\"phase\":" + String(persistentPhase) +
         ",\"next_ordinal\":" + String(nextOrdinal) +
         ",\"next_action_id\":" +
         (action ? String("\"") + action->actionId + "\"" : "null") +
         ",\"boot_nonce\":\"" + bootNonce() +
         "\",\"arm_nonce\":" +
         (state == RuntimeState::Armed ? String("\"") + armNonce() + "\""
                                       : "null") +
         ",\"fixture_self_check_passed\":" +
         (fixtureSelfCheckPassed ? "true" : "false") +
         ",\"no_retry\":true,\"no_autochain\":true}";
}

String driverJson(const EpdOperationReport &report) {
  return String("{\"operation_id\":") + String(report.operationId) +
         ",\"valid\":" + (report.valid ? "true" : "false") +
         ",\"sequence_ok\":" + (report.sequenceOk ? "true" : "false") +
         ",\"spi_hz\":" + String(report.spiHz) +
         ",\"frame_fnv1a\":" + String(report.inputFrameFnv1a) +
         ",\"cs1_dtm_fnv1a\":" + String(report.cs1DtmFnv1a) +
         ",\"cs2_dtm_fnv1a\":" + String(report.cs2DtmFnv1a) +
         ",\"pon_busy_seen\":" + (report.ponBusySeen ? "true" : "false") +
         ",\"drf_busy_seen\":" + (report.drfBusySeen ? "true" : "false") +
         ",\"pof_busy_seen\":" + (report.pofBusySeen ? "true" : "false") +
         ",\"total_ms\":" + String(report.totalMs) +
         ",\"failure_stage\":\"" + report.failureStage + "\"}";
}

void publishFault(const char *error, const ActionDescriptor *action,
                  bool driverCalled = false,
                  const EpdOperationReport *driver = nullptr) {
  publishedReport =
      String("{\"schema_version\":1,\"kind\":") +
      "\"mf1750-partial-hold-warm-session-report\",\"valid\":false," +
      identityJson() + ",\"boot_nonce\":\"" + bootNonce() +
      "\",\"terminal_state\":\"FAULT\",\"result\":false,\"error\":\"" +
      error +
      "\",\"driver_called\":" + (driverCalled ? "true" : "false") +
      ",\"ordinal\":" + String(action ? action->ordinal : 0) +
      ",\"action_id\":" +
      (action ? String("\"") + action->actionId + "\"" : "null") +
      (driver ? String(",\"driver\":") + driverJson(*driver) : "") + "}";
}

void enterFault(const char *error, const ActionDescriptor *action,
                bool driverCalled = false,
                const EpdOperationReport *driver = nullptr) {
  executePending = false;
  epdAbortPartialHoldWarmSession(error);
  if (storeReady) {
    const uint8_t ordinal = action ? action->ordinal
                                   : (nextOrdinal <= kActionCount ? nextOrdinal : 1);
    persistCursor(kPhaseFault, ordinal);
  }
  state = RuntimeState::FaultLocked;
  publishFault(error, action, driverCalled, driver);
}

void rejectMutation(int code, const char *error,
                    const ActionDescriptor *action) {
  enterFault(error, action);
  server.send(code, "application/json", publishedReport);
}

const char *validateMutation(const ActionDescriptor &action,
                             const char *intent, bool requireArmNonce) {
  if (requestHasBodyOrArguments()) return "body_or_arguments_forbidden";
  if (!exactHeader(kBuildHeader, kBuildTag)) return "build_tag_mismatch";
  if (!exactHeader(kTestHeader, kTestId)) return "test_id_mismatch";
  if (!exactHeader(kCampaignHeader, kCampaignId)) return "campaign_id_mismatch";
  if (!exactHeader(kActionHeader, action.actionId)) return "action_id_mismatch";
  if (!exactHeader(kOrdinalHeader, String(action.ordinal))) return "ordinal_mismatch";
  if (!exactHeader(kDescriptorHeader, action.descriptorId))
    return "descriptor_id_mismatch";
  if (!exactHeader(kBootNonceHeader, bootNonce())) return "boot_nonce_mismatch";
  if (!exactHeader(kIntentHeader, intent)) return "intent_mismatch";
  if (!requireArmNonce && server.hasHeader(kArmNonceHeader))
    return "arm_nonce_forbidden";
  if (requireArmNonce && !exactHeader(kArmNonceHeader, armNonce()))
    return "arm_nonce_mismatch";
  return nullptr;
}

void handleArm() {
  if (!refreshCursorEvidence()) {
    rejectMutation(503, "arm_cursor_invalid", nullptr);
    return;
  }
  const ActionDescriptor *action = currentAction();
  if (state != RuntimeState::Ready || persistentPhase != kPhaseReady ||
      !action || executePending) {
    rejectMutation(409, "arm_not_ready", action);
    return;
  }
  const char *error = validateMutation(*action, kArmIntent, false);
  if (error) {
    rejectMutation(400, error, action);
    return;
  }
  armNonceHigh = esp_random();
  armNonceLow = esp_random();
  if ((armNonceHigh | armNonceLow) == 0) armNonceLow = 1;
  if (!persistCursor(kPhaseArmed, action->ordinal)) {
    rejectMutation(503, "persistent_arm_failed", action);
    return;
  }
  state = RuntimeState::Armed;
  server.send(200, "application/json",
              String("{\"accepted\":true,\"armed\":true,") +
                  identityJson() + ",\"ordinal\":" +
                  String(action->ordinal) + ",\"action_id\":\"" +
                  action->actionId + "\",\"boot_nonce\":\"" +
                  bootNonce() + "\",\"arm_nonce\":\"" + armNonce() +
                  "\",\"no_retry\":true,\"no_autochain\":true}");
}

void handleExecute() {
  if (!refreshCursorEvidence()) {
    rejectMutation(503, "execute_cursor_invalid", nullptr);
    return;
  }
  const ActionDescriptor *action = currentAction();
  if (state != RuntimeState::Armed || persistentPhase != kPhaseArmed ||
      !action || executePending) {
    rejectMutation(409, "execute_not_armed", action);
    return;
  }
  const char *error = validateMutation(*action, kExecuteIntent, true);
  if (error) {
    rejectMutation(400, error, action);
    return;
  }
  if (!persistCursor(kPhaseConsumed, action->ordinal)) {
    rejectMutation(503, "persistent_consumed_failed", action);
    return;
  }
  jobQueuedAtMs = millis();
  driverCallCountForAction = 0;
  executePending = true;
  state = RuntimeState::Queued;
  server.send(202, "application/json",
              String("{\"accepted\":true,\"execute_consumed\":true,") +
                  identityJson() + ",\"ordinal\":" +
                  String(action->ordinal) + ",\"action_id\":\"" +
                  action->actionId + "\",\"no_retry\":true," +
                  "\"no_autochain\":true}");
}

void installRoutes() {
  static const char *headers[] = {
      "Content-Type",       "Content-Length",   "Transfer-Encoding",
      kBuildHeader,         kTestHeader,          kCampaignHeader,
      kActionHeader,        kOrdinalHeader,       kDescriptorHeader,
      kBootNonceHeader,     kArmNonceHeader,      kIntentHeader,
  };
  server.collectHeaders(headers, sizeof(headers) / sizeof(headers[0]));
  server.on(kVersionRoute, HTTP_GET, []() {
    server.send(200, "application/json", versionJson());
  });
  server.on(kManifestRoute, HTTP_GET, []() {
    server.send(200, "application/json", manifestJson());
  });
  server.on(kStatusRoute, HTTP_GET, []() {
    server.send(200, "application/json", statusJson());
  });
  server.on(kReportRoute, HTTP_GET, []() {
    server.send(200, "application/json", publishedReport);
  });
  server.on(kArmRoute, HTTP_POST, handleArm);
  server.on(kExecuteRoute, HTTP_POST, handleExecute);
  server.onNotFound([]() {
    if (server.method() == HTTP_POST) {
      rejectMutation(404, "unknown_mutation_route", currentAction());
    } else {
      server.send(404, "application/json", "{\"error\":\"not_found\"}");
    }
  });
}

void startWiFi() {
  if (strlen(WIFI_STA_SSID) > 0) {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_STA_SSID, WIFI_STA_PASSWORD);
    const uint32_t started = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - started < 15000UL) {
      delay(250);
    }
    if (WiFi.status() == WL_CONNECTED) return;
  }
  WiFi.mode(WIFI_AP);
  WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASSWORD);
}

void restartHttpListener() {
  server.stop();
  delay(10);
  server.begin();
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
      epdDisplayCompiledPartialHoldWarmSession(action->driverRole);
  jobFinishedAtMs = millis();
  const EpdOperationReport &driver = epdGetLastOperationReport();
  if (!result) {
    enterFault("driver_operation_failed", action, true, &driver);
    restartHttpListener();
    return;
  }
  const uint8_t following = action->ordinal + 1;
  if (!persistCursor(kPhaseReady, following)) {
    enterFault("persistent_next_ready_failed", action, true, &driver);
    restartHttpListener();
    return;
  }
  state = following == kTerminalOrdinal ? RuntimeState::Complete
                                        : RuntimeState::Ready;
  publishedReport =
      String("{\"schema_version\":1,\"kind\":") +
      "\"mf1750-partial-hold-warm-session-report\",\"valid\":true," +
      identityJson() + ",\"boot_nonce\":\"" + bootNonce() +
      "\",\"terminal_state\":\"COMPLETE\",\"ordinal\":" +
      String(action->ordinal) +
      ",\"action_id\":\"" + action->actionId +
      "\",\"role\":\"" + action->role +
      "\",\"result\":true,\"driver_called\":true," +
      "\"driver_call_count_for_action\":1," +
      "\"total_driver_call_count\":" + String(totalDriverCallCount) +
      ",\"next_ordinal\":" + String(following) +
      ",\"campaign_complete\":" +
      (following == kTerminalOrdinal ? "true" : "false") +
      ",\"warm_state\":\"" +
      warmStateName(epdGetPartialHoldWarmSessionState()) +
      "\",\"job_queued_at_ms\":" + String(jobQueuedAtMs) +
      ",\"job_started_at_ms\":" + String(jobStartedAtMs) +
      ",\"job_finished_at_ms\":" + String(jobFinishedAtMs) +
      ",\"no_retry\":true,\"no_autochain\":true,\"driver\":" +
      driverJson(driver) + "}";
  restartHttpListener();
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(50);
  bootNonceHigh = esp_random();
  bootNonceLow = esp_random();
  if ((bootNonceHigh | bootNonceLow) == 0) bootNonceLow = 1;

  epdBegin();
  fixtureSelfCheckPassed =
      epdValidateCompiledPartialHoldWarmSessionFixtures();
  storeReady = cursorStore.begin(kNvsNamespace, false);
  bool cursorValid = storeReady && refreshCursorEvidence();
  if (storeReady && !keyPresent) cursorValid = persistCursor(kPhaseReady, 1);

  if (!fixtureSelfCheckPassed) {
    enterFault("compiled_fixture_self_check_failed", nullptr);
  } else if (!storeReady || !cursorValid) {
    enterFault("cursor_store_invalid", nullptr);
  } else if (persistentPhase == kPhaseReady && nextOrdinal == 1) {
    state = RuntimeState::Ready;
    publishedReport =
        String("{\"schema_version\":1,\"kind\":") +
        "\"mf1750-partial-hold-warm-session-report\",\"valid\":false," +
        identityJson() + ",\"boot_nonce\":\"" + bootNonce() +
        "\",\"terminal_state\":\"NOT_EXECUTED\",\"result\":false," +
        "\"driver_called\":false,\"error\":\"not_executed\"," +
        "\"next_ordinal\":1}";
  } else if (persistentPhase == kPhaseReady &&
             nextOrdinal == kTerminalOrdinal) {
    // A completed campaign is already safely POF. It is not replayable.
    state = RuntimeState::Complete;
    publishedReport =
        String("{\"schema_version\":1,\"kind\":") +
        "\"mf1750-partial-hold-warm-session-report\",\"valid\":true," +
        identityJson() + ",\"boot_nonce\":\"" + bootNonce() +
        "\",\"terminal_state\":\"COMPLETE\",\"result\":true," +
        "\"campaign_complete\":true,\"replay_allowed\":false}";
  } else {
    // Any reboot after baseline destroys the in-RAM warm-session proof. Never
    // resume action 2..5 from NVS and never re-run a consumed action. GPIOs
    // are held LOW, but software cannot prove whether a reset interrupted an
    // energized phase, so external physical cut is required before recovery.
    enterFault("same_boot_warm_session_evidence_lost", currentAction());
  }

  startWiFi();
  installRoutes();
  server.begin();
}

void loop() {
  server.handleClient();
  executePendingAction();
  if (!epdServicePartialHoldWarmSession() &&
      state != RuntimeState::FaultLocked && state != RuntimeState::Complete) {
    const EpdOperationReport &driver = epdGetLastOperationReport();
    enterFault("warm_session_lease_expired", currentAction(), true, &driver);
    restartHttpListener();
  }
  delay(2);
}
