#include <Arduino.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <esp_system.h>

#include <cstring>

#include "ec5_power_qualifier_pon_pof_no_drf_v2.h"
#include "epd_config.h"

#if !defined(MF1750_POWER_QUALIFIER_PON_POF_NO_DRF_V2_BUILD) || \
    MF1750_POWER_QUALIFIER_PON_POF_NO_DRF_V2_BUILD != 1
#error "This main is restricted to the isolated PON/POF qualifier build"
#endif

#if EPD_ENABLE_TEST_PATTERN != 0
#error "Startup refresh is forbidden"
#endif

namespace {

static constexpr char kBuildTag[] =
    "MF1750_EC5_POWER_QUALIFIER_PON_POF_NO_DRF_V2_2026-08-25";
static constexpr char kTestId[] =
    "EC5-POWER-QUALIFIER-PON-POF-NO-DRF-V2";
static constexpr char kCampaignId[] =
    "EC5_POWER_QUALIFIER_PON_POF_NO_DRF_V2";
static constexpr char kContractId[] =
    "d1ae9cc592536a42ff5b611bb4580be25bc126087946a24f82a6cc0c3c04208f";
static constexpr char kDescriptorId[] =
    "aa2fedbb8db8c6c4706a0fe5300bafe9ef5a8265e7b91b8bc23712d725c5de30";
static constexpr char kActionId[] =
    "e6c73eb7ba9b6fd5b2af89cd51fe9422a5e34434f93379b53b9f2280025f1c6e";
static constexpr char kDeviceApiVersion[] =
    "MF1750_EC5_POWER_QUALIFIER_PON_POF_NO_DRF_DEVICE_V2";
static constexpr char kIdentityRevision[] =
    "power-qualifier-pon-pof-no-drf-v2";
static constexpr char kClassification[] =
    "SUPERVISED_POWER_PATH_QUALIFIER_PON_POF_NO_DRF";
static constexpr char kRole[] = "PON_POF_NO_DRF_POWER_PATH_PROBE";
static constexpr char kBranch[] =
    "PER_SAMPLE_RESET_EXACT_REV_READINESS_THEN_PON_THEN_POF_NO_DRF";

static constexpr char kNvsNamespace[] = "epdponpof_v2";
static constexpr char kNvsKey[] = "cursor_pp2";
static constexpr char kBaseRoute[] =
    "/api/ec5/power-qualifier-pon-pof-no-drf-v2";
static constexpr char kVersionRoute[] =
    "/api/ec5/power-qualifier-pon-pof-no-drf-v2/version";
static constexpr char kManifestRoute[] =
    "/api/ec5/power-qualifier-pon-pof-no-drf-v2/manifest";
static constexpr char kStatusRoute[] =
    "/api/ec5/power-qualifier-pon-pof-no-drf-v2/status";
static constexpr char kReportRoute[] =
    "/api/ec5/power-qualifier-pon-pof-no-drf-v2/report";
static constexpr char kQualifyRoute[] =
    "/api/ec5/power-qualifier-pon-pof-no-drf-v2/qualify";
static constexpr char kArmRoute[] =
    "/api/ec5/power-qualifier-pon-pof-no-drf-v2/arm";
static constexpr char kExecuteRoute[] =
    "/api/ec5/power-qualifier-pon-pof-no-drf-v2/execute";

static constexpr char kBuildHeader[] = "X-EC5-Build-Tag";
static constexpr char kTestHeader[] = "X-EC5-Test-Id";
static constexpr char kCampaignHeader[] = "X-EC5-Campaign-Id";
static constexpr char kBootNonceHeader[] = "X-EC5-Boot-Nonce";
static constexpr char kIntentHeader[] = "X-EC5-Intent";
static constexpr char kActionHeader[] = "X-EC5-Action-Id";
static constexpr char kDescriptorHeader[] = "X-EC5-Descriptor-Id";
static constexpr char kOrdinalHeader[] = "X-EC5-Ordinal";
static constexpr char kArmNonceHeader[] = "X-EC5-Arm-Nonce";
static constexpr char kQualificationNonceHeader[] =
    "X-EC5-Qualification-Nonce";
static constexpr char kQualifyIntent[] =
    "QUALIFY_PER_SAMPLE_RESET_EXACT_DUAL_REVISION_ONCE";
static constexpr char kArmIntent[] =
    "ARM_ONE_PON_POF_NO_DRF_POWER_PATH_PROBE_V2";
static constexpr char kExecuteIntent[] =
    "EXECUTE_ARMED_PON_POF_NO_DRF_POWER_PATH_PROBE_V2_ONCE";

enum PersistentPhase : uint8_t {
  kFresh = 0,
  kQualifyConsumed = 1,
  kQualified = 2,
  kArmed = 3,
  kProbeConsumed = 4,
  kComplete = 5,
  kFault = 6,
};

enum class RuntimeState : uint8_t {
  Boot,
  ReadyUnqualified,
  QualifyQueued,
  Qualifying,
  Qualified,
  Armed,
  ProbeQueued,
  Running,
  Complete,
  FaultLocked,
};

WebServer server(80);
Preferences store;
RuntimeState runtimeState = RuntimeState::Boot;
PersistentPhase phase = kFresh;
bool storeReady = false;
bool keyPresent = false;
bool qualifyPending = false;
bool probePending = false;
bool sameBootQualified = false;
uint32_t bootNonceHigh = 0;
uint32_t bootNonceLow = 0;
uint32_t armNonceHigh = 0;
uint32_t armNonceLow = 0;
uint32_t qualificationNonceHigh = 0;
uint32_t qualificationNonceLow = 0;
uint32_t qualifyRequestCount = 0;
uint32_t armRequestCount = 0;
uint32_t executeRequestCount = 0;
uint32_t qualifierCallCount = 0;
uint32_t probeCallCount = 0;
String publishedReport =
    "{\"schema_version\":4,\"valid\":false,\"error\":\"boot\"}";

const char *stateName(RuntimeState value) {
  switch (value) {
    case RuntimeState::Boot: return "boot";
    case RuntimeState::ReadyUnqualified: return "ready_unqualified";
    case RuntimeState::QualifyQueued: return "qualify_queued";
    case RuntimeState::Qualifying: return "qualifying";
    case RuntimeState::Qualified: return "qualified";
    case RuntimeState::Armed: return "armed";
    case RuntimeState::ProbeQueued: return "probe_queued";
    case RuntimeState::Running: return "running";
    case RuntimeState::Complete: return "complete";
    case RuntimeState::FaultLocked: return "fault_locked";
  }
  return "fault_locked";
}

const char *phaseName(PersistentPhase value) {
  switch (value) {
    case kFresh: return "FRESH";
    case kQualifyConsumed: return "QUALIFY_CONSUMED";
    case kQualified: return "QUALIFIED";
    case kArmed: return "ARMED";
    case kProbeConsumed: return "PROBE_CONSUMED";
    case kComplete: return "COMPLETE";
    case kFault: return "FAULT";
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
String qualificationNonce() {
  return hex32(qualificationNonceHigh) + hex32(qualificationNonceLow);
}

bool phaseValid(uint8_t value) { return value <= kFault; }

bool loadPhase() {
  if (!storeReady) return false;
  keyPresent = store.isKey(kNvsKey);
  if (!keyPresent) {
    phase = kFresh;
    return true;
  }
  const uint8_t value = store.getUChar(kNvsKey, 0xFF);
  if (!phaseValid(value)) return false;
  phase = static_cast<PersistentPhase>(value);
  return true;
}

bool persistPhase(PersistentPhase wanted) {
  if (!storeReady || store.putUChar(kNvsKey, wanted) != sizeof(uint8_t))
    return false;
  if (!loadPhase()) return false;
  return phase == wanted;
}

String identityJson() {
  return String("\"build_tag\":\"") + kBuildTag +
         "\",\"test_id\":\"" + kTestId +
         "\",\"campaign_id\":\"" + kCampaignId +
         "\",\"contract_id\":\"" + kContractId +
         "\",\"descriptor_id\":\"" + kDescriptorId +
         "\",\"action_id\":\"" + kActionId +
         "\",\"device_api_version\":\"" + kDeviceApiVersion +
         "\",\"identity_revision\":\"" + kIdentityRevision +
         "\",\"classification\":\"" + kClassification + "\"";
}

String actionJson() {
  return String("{\"ordinal\":1,\"descriptor_id\":\"") +
         kDescriptorId + "\",\"action_id\":\"" + kActionId +
         "\",\"prior_static_action_id\":" +
         "\"8cd8b3794bed065ae9cd64a002957e162673f17706ea2464e9397035389f58a4\"," +
         "\"role\":\"" + kRole +
         "\",\"round\":1,\"branch\":\"" + kBranch + "\"}";
}

String gpioJson() {
  return String("{\"busy\":") + String(ec5PowerQualifierV2ReadBusy()) +
         ",\"rst\":" + String(digitalRead(EPD_PIN_RST)) +
         ",\"cs1\":" + String(digitalRead(EPD_PIN_CS)) +
         ",\"cs2\":" + String(digitalRead(EPD_PIN_CS2)) +
         ",\"sck\":" + String(digitalRead(EPD_PIN_SCK)) +
         ",\"dc\":" + String(digitalRead(EPD_PIN_DC)) +
         ",\"mosi\":" + String(digitalRead(EPD_PIN_MOSI)) + "}";
}

bool qualifiedPinPosture() {
  return ec5PowerQualifierV2ReadBusy() == 1 && digitalRead(EPD_PIN_RST) == HIGH &&
         digitalRead(EPD_PIN_CS) == HIGH &&
         digitalRead(EPD_PIN_CS2) == HIGH &&
         digitalRead(EPD_PIN_SCK) == LOW &&
         digitalRead(EPD_PIN_DC) == LOW &&
         digitalRead(EPD_PIN_MOSI) == LOW;
}

String versionJson() {
  return String("{\"schema_version\":4,\"kind\":") +
         "\"mf1750-power-qualifier-pon-pof-no-drf-v2-version\"," +
         identityJson() + ",\"startup_refresh\":false," +
         "\"automatic_execute\":false,\"automatic_chaining\":false," +
         "\"retry\":false,\"recovery\":false," +
         "\"raw_frame_ingress\":false,\"runtime_lut_write\":false," +
         "\"ptlw_write\":false,\"visible_refresh\":false," +
         "\"visible_refresh_requests\":0,\"action_count\":1," +
         "\"nvs_contract\":{\"namespace\":\"" + kNvsNamespace +
         "\",\"key\":\"" + kNvsKey +
         "\",\"terminal_next_ordinal\":2},\"base_route\":\"" +
         kBaseRoute + "\"}";
}

String manifestJson() {
  return String("{\"schema_version\":4,\"kind\":") +
         "\"mf1750-power-qualifier-pon-pof-no-drf-v2-manifest\"," +
         identityJson() +
         ",\"residual_differences_from_historical_helper\":{" +
         "\"mosi_high_before_reset\":\"NOT_RESTORED_IN_V2\"," +
         "\"post_reset_tail_2us\":\"NOT_RESTORED_IN_V2\"," +
         "\"classification\":" +
         "\"V2_IS_PER_SAMPLE_RESET_ONLY_NOT_EXACT_LEGACY_TRANSACTION\"," +
         "\"v2_zero_revision_disposition\":" +
         "\"STOP_BEFORE_PON_AND_CREATE_FRESH_V3\"}" +
         ",\"nvs\":{\"namespace\":\"" + kNvsNamespace +
         "\",\"key\":\"" + kNvsKey +
         "\",\"terminal_next_ordinal\":2," +
         "\"missing_key_is_fresh_only\":true," +
         "\"nonterminal_phase_on_boot\":" +
         "\"FAULT_NO_RESUME_NO_RETRY\"," +
         "\"v1_namespace_and_key_must_not_be_erased\":true}," +
         "\"actions\":[" +
         actionJson() + "],\"action_count\":1," +
         "\"one_driver_call_per_action\":true," +
         "\"probe_sequence\":[" +
         "\"PON_BUSY_ASSERT_THEN_IDLE_COMPLETE_60S_GATE\"," +
         "\"POF_00_BUSY_ASSERT_THEN_IDLE_COMPLETE_60S_GATE\"]," +
         "\"pon_count\":1,\"pof_count\":1,\"drf_count\":0," +
         "\"dtm_bytes\":0,\"lut_bytes\":0,\"ptlw_writes\":0," +
         "\"visible_refresh_requests\":0,\"retry\":false," +
         "\"recovery\":false,\"autochain\":false," +
         "\"qualification\":{" +
         "\"reset_count\":5," +
         "\"reset_before_each_revision_sample\":true," +
         "\"final_posture_reset\":true," +
         "\"single_variable_change\":\"PER_SAMPLE_RESET_ONLY\"," +
         "\"exact_historical_transaction_reproduction\":false," +
         "\"legacy_mosi_high_before_reset_restored\":false," +
         "\"legacy_post_reset_tail_2us_restored\":false," +
         "\"segmented_cs_framing_changed\":false," +
         "\"cs1_revision_reads\":2,\"cs2_revision_reads\":2," +
         "\"expected_revision_bytes\":[1,1,4]," +
         "\"all_four_samples_exact_required\":true," +
         "\"same_boot_required\":true," +
         "\"zero_revision_result\":" +
         "\"STOP_BEFORE_PON_AND_DEFER_LEGACY_TRANSACTION_TO_V3\"," +
         "\"qualified_busy_level\":1," +
         "\"qualified_busy_stable_ms\":50," +
         "\"qualified_gpio\":{\"rst\":1,\"cs1\":1,\"cs2\":1," +
         "\"sck\":0,\"dc\":0,\"mosi\":0}}," +
         "\"probe\":{\"spi_hz\":1000000," +
         "\"exactly_one_pon\":true,\"exactly_one_pof\":true," +
         "\"pon_count\":1,\"pof_count\":1," +
         "\"drf_count\":0,\"dtm_bytes\":0,\"lut_bytes\":0," +
         "\"ptlw_writes\":0,\"command_0x86_count\":0," +
         "\"visible_refresh_requests\":0," +
         "\"failure_cleanup_matrix\":{" +
         "\"pon_not_sent\":{\"pof_cleanup_count\":0," +
         "\"reason\":\"NO_HIGH_VOLTAGE_PATH_WAS_ENTERED\"}," +
         "\"pon_sent_pof_not_sent\":{\"pof_cleanup_count\":1," +
         "\"reason\":\"ONE_FAIL_SAFE_POF_IS_REQUIRED\"}," +
         "\"pof_sent\":{\"additional_pof_cleanup_count\":0," +
         "\"maximum_total_pof_count\":1," +
         "\"reason\":\"A_SECOND_POF_IS_FORBIDDEN\"}}," +
         "\"post_pof\":[\"DELAY_6000MS\",\"PSR_4F6E\"," +
         "\"WAIT_IDLE\",\"DELAY_1000MS\",\"PINS_LOW\"]}," +
         "\"allowed_command_payload_sequence\":" +
         "[\"RESET_CS1_SAMPLE1\"," +
         "\"REV_CS1_SAMPLE1_70_EXPECT_010104\"," +
         "\"RESET_CS1_SAMPLE2\"," +
         "\"REV_CS1_SAMPLE2_70_EXPECT_010104\"," +
         "\"RESET_CS2_SAMPLE1\"," +
         "\"REV_CS2_SAMPLE1_70_EXPECT_010104\"," +
         "\"RESET_CS2_SAMPLE2\"," +
         "\"REV_CS2_SAMPLE2_70_EXPECT_010104\"," +
         "\"FINAL_POSTURE_RESET\"," +
         "\"AA_495520080918\",\"PWR_01_3F\",\"PSR_00_5F69\"," +
         "\"BTST1_05_401F1F2C\",\"BTST3_08_6F1F1F22\"," +
         "\"BTST2_06_6F1F1717\",\"POFS_03_00540044\"," +
         "\"TCON_60_0200\",\"PLL_30_08\",\"CDI_50_3F\"," +
         "\"TRES_61_02000258\",\"PWS_E3_2F\",\"T_VDCS_84_01\"," +
         "\"CCSET_CS1_E0_01\",\"CCSET_CS2_E0_01\"," +
         "\"SELECT_DUAL_BEFORE_PON\",\"PON_04\"," +
         "\"SELECT_DUAL_BEFORE_POF\",\"POF_02_00\"," +
         "\"SELECT_DUAL_BEFORE_POST_PSR\",\"PSR_00_4F6E\"]," +
         "\"forbidden_commands\":[\"DTM_0X10\",\"DTM_0X11\"," +
         "\"DRF_0X12\",\"DTM_0X13\",\"LUT_R20\",\"LUT_R21\"," +
         "\"PTLW_0X83\",\"COMMAND_0X86\"]," +
         "\"safety\":{\"startup_action\":false," +
         "\"automatic_execute\":false,\"automatic_retry\":false," +
         "\"automatic_recovery\":false,\"automatic_chaining\":false}}";
}

String statusJson() {
  loadPhase();
  return String("{\"schema_version\":4,\"kind\":") +
         "\"mf1750-power-qualifier-pon-pof-no-drf-v2-status\"," +
         identityJson() + ",\"boot_nonce\":\"" + bootNonce() +
         "\",\"state\":\"" + stateName(runtimeState) +
         "\",\"phase\":" + String(static_cast<unsigned>(phase)) +
         ",\"phase_name\":\"" + phaseName(phase) +
         "\",\"next_ordinal\":" + (phase == kComplete ? "2" : "1") +
         ",\"campaign_complete\":" +
         (phase == kComplete ? "true" : "false") +
         ",\"same_boot_qualified\":" +
         (sameBootQualified ? "true" : "false") +
         ",\"qualification_nonce\":" +
         (sameBootQualified
              ? String("\"") + qualificationNonce() + "\""
              : String("null")) +
         ",\"qualified_pin_posture\":" +
         (qualifiedPinPosture() ? "true" : "false") +
         ",\"qualify_pending\":" +
         (qualifyPending ? "true" : "false") +
         ",\"probe_pending\":" + (probePending ? "true" : "false") +
         ",\"qualify_request_count\":" + String(qualifyRequestCount) +
         ",\"arm_request_count\":" + String(armRequestCount) +
         ",\"execute_request_count\":" + String(executeRequestCount) +
         ",\"qualifier_call_count\":" + String(qualifierCallCount) +
         ",\"probe_call_count\":" + String(probeCallCount) +
         ",\"cursor_raw\":" + String(static_cast<unsigned>(phase)) +
         ",\"fixture_self_check_passed\":true," +
         "\"cursor_valid\":true,\"gpio_initialized\":true," +
         "\"execute_pending\":" + (probePending ? "true" : "false") +
         ",\"persistent_key_present\":" +
         (keyPresent ? "true" : "false") +
         ",\"qualification_consumed\":" +
         (phase >= kQualifyConsumed ? "true" : "false") +
         ",\"qualification_valid\":" +
         (sameBootQualified ? "true" : "false") +
         ",\"total_driver_call_count\":" + String(probeCallCount) +
         ",\"gpio\":" + gpioJson() + "}";
}

bool requestHasBodyOrArguments() {
  if (server.args() != 0 || server.hasArg("plain")) return true;
  const String contentLength = server.header("Content-Length");
  return (!server.header("Content-Type").isEmpty() ||
          !server.header("Transfer-Encoding").isEmpty() ||
          (!contentLength.isEmpty() && contentLength != "0"));
}

bool exactHeader(const char *name, const String &expected) {
  return server.hasHeader(name) && server.header(name) == expected;
}

bool baseMutationHeaders(const char *intent) {
  return !requestHasBodyOrArguments() && exactHeader(kBuildHeader, kBuildTag) &&
         exactHeader(kTestHeader, kTestId) &&
         exactHeader(kCampaignHeader, kCampaignId) &&
         exactHeader(kBootNonceHeader, bootNonce()) &&
         exactHeader(kIntentHeader, intent);
}

bool actionMutationHeaders(const char *intent, bool requireArmNonce) {
  return baseMutationHeaders(intent) && exactHeader(kActionHeader, kActionId) &&
         exactHeader(kDescriptorHeader, kDescriptorId) &&
         exactHeader(kOrdinalHeader, "1") &&
         exactHeader(kQualificationNonceHeader, qualificationNonce()) &&
         (!requireArmNonce || exactHeader(kArmNonceHeader, armNonce()));
}

void publishFault(const char *error) {
  publishedReport =
      String("{\"schema_version\":4,\"kind\":") +
      "\"mf1750-power-qualifier-pon-pof-no-drf-v2-report\"," +
      identityJson() + ",\"valid\":true,\"boot_nonce\":\"" +
      bootNonce() + "\",\"terminal_state\":\"FAULT\"," +
      "\"result\":false,\"error\":\"" + error +
      "\",\"qualification_nonce\":" +
      ((qualificationNonceHigh | qualificationNonceLow) != 0
           ? String("\"") + qualificationNonce() + "\""
           : String("null")) +
      ",\"phase\":" + String(static_cast<unsigned>(phase)) +
      ",\"phase_name\":\"" + phaseName(phase) +
      "\",\"readiness\":" + ec5PowerQualifierV2ReadinessJson() +
      ",\"probe\":" + ec5PowerQualifierV2ProbeJson() +
      ",\"no_retry\":true,\"no_recovery\":true," +
      "\"no_autochain\":true}";
}

void enterFault(const char *error) {
  qualifyPending = false;
  probePending = false;
  sameBootQualified = false;
  ec5PowerQualifierV2ForceSafeHold();
  persistPhase(kFault);
  runtimeState = RuntimeState::FaultLocked;
  publishFault(error);
}

void rejectMutation(int status, const char *error) {
  enterFault(error);
  server.send(status, "application/json",
              String("{\"accepted\":false,\"fault_locked\":true,") +
                  "\"error\":\"" + error +
                  "\",\"no_retry\":true,\"no_recovery\":true}");
}

void handleQualify() {
  ++qualifyRequestCount;
  if (!loadPhase() || runtimeState != RuntimeState::ReadyUnqualified ||
      phase != kFresh) {
    rejectMutation(409, "qualify_duplicate_or_not_fresh");
    return;
  }
  if (!baseMutationHeaders(kQualifyIntent)) {
    rejectMutation(400, "qualify_contract_mismatch_or_body_present");
    return;
  }
  if (!persistPhase(kQualifyConsumed)) {
    rejectMutation(503, "qualify_consumed_persist_failed");
    return;
  }
  runtimeState = RuntimeState::QualifyQueued;
  qualifyPending = true;
  server.send(202, "application/json",
              String("{\"accepted\":true,\"qualification_queued\":true,") +
                  identityJson() + ",\"boot_nonce\":\"" + bootNonce() +
                  "\",\"phase\":1,\"phase_name\":\"QUALIFY_CONSUMED\"," +
                  "\"no_retry\":true,\"no_recovery\":true}");
}

void handleArm() {
  ++armRequestCount;
  if (!loadPhase() || runtimeState != RuntimeState::Qualified ||
      phase != kQualified || !sameBootQualified) {
    rejectMutation(409, "arm_not_same_boot_qualified");
    return;
  }
  if (!actionMutationHeaders(kArmIntent, false)) {
    rejectMutation(400, "arm_contract_mismatch_or_body_present");
    return;
  }
  if (!qualifiedPinPosture()) {
    rejectMutation(503, "arm_busy_or_gpio_posture_changed");
    return;
  }
  armNonceHigh = esp_random();
  armNonceLow = esp_random();
  if ((armNonceHigh | armNonceLow) == 0) armNonceLow = 1;
  if (!persistPhase(kArmed)) {
    rejectMutation(503, "armed_persist_failed");
    return;
  }
  runtimeState = RuntimeState::Armed;
  server.send(201, "application/json",
              String("{\"accepted\":true,\"armed\":true,") +
                  identityJson() + ",\"ordinal\":1,\"boot_nonce\":\"" +
                  bootNonce() + "\",\"arm_nonce\":\"" + armNonce() +
                  "\",\"qualification_nonce\":\"" +
                  qualificationNonce() +
                  "\",\"phase\":3,\"phase_name\":\"ARMED\"}");
}

void handleExecute() {
  ++executeRequestCount;
  if (!loadPhase() || runtimeState != RuntimeState::Armed ||
      phase != kArmed || !sameBootQualified) {
    rejectMutation(409, "execute_not_armed_or_same_boot_qualified");
    return;
  }
  if (!actionMutationHeaders(kExecuteIntent, true)) {
    rejectMutation(400, "execute_contract_mismatch_or_body_present");
    return;
  }
  if (!qualifiedPinPosture() || probeCallCount != 0) {
    rejectMutation(503, "execute_busy_gpio_or_call_count_changed");
    return;
  }
  if (!persistPhase(kProbeConsumed)) {
    rejectMutation(503, "probe_consumed_persist_failed");
    return;
  }
  runtimeState = RuntimeState::ProbeQueued;
  probePending = true;
  server.send(202, "application/json",
              String("{\"accepted\":true,\"execute_consumed\":true,") +
                  identityJson() + ",\"ordinal\":1,\"boot_nonce\":\"" +
                  bootNonce() +
                  "\",\"qualification_nonce\":\"" +
                  qualificationNonce() +
                  "\",\"phase\":4,\"phase_name\":\"PROBE_CONSUMED\"," +
                  "\"no_retry\":true,\"no_recovery\":true}");
}

void restartHttpListener() {
  server.stop();
  delay(10);
  server.begin();
}

void executePendingWork() {
  if (qualifyPending) {
    qualifyPending = false;
    if (!loadPhase() || phase != kQualifyConsumed ||
        runtimeState != RuntimeState::QualifyQueued || qualifierCallCount != 0) {
      enterFault("qualification_queue_or_cursor_mismatch");
      return;
    }
    runtimeState = RuntimeState::Qualifying;
    ++qualifierCallCount;
    const bool result = ec5PowerQualifierV2RunReadinessOnce();
    const Ec5PowerQualifierV2ReadinessReport &readiness =
        ec5PowerQualifierV2ReadinessReport();
    if (!result || !readiness.qualified || !qualifiedPinPosture()) {
      enterFault("readiness_qualification_failed");
      restartHttpListener();
      return;
    }
    if (!persistPhase(kQualified)) {
      enterFault("qualified_persist_failed");
      restartHttpListener();
      return;
    }
    qualificationNonceHigh = esp_random();
    qualificationNonceLow = esp_random();
    if ((qualificationNonceHigh | qualificationNonceLow) == 0)
      qualificationNonceLow = 1;
    sameBootQualified = true;
    runtimeState = RuntimeState::Qualified;
    publishedReport =
        String("{\"schema_version\":4,\"kind\":") +
        "\"mf1750-power-qualifier-pon-pof-no-drf-v2-report\"," +
        identityJson() + ",\"valid\":true,\"boot_nonce\":\"" +
        bootNonce() + "\",\"terminal_state\":\"QUALIFIED\"," +
        "\"result\":true,\"phase\":2,\"phase_name\":\"QUALIFIED\"," +
        "\"qualification_nonce\":\"" + qualificationNonce() +
        "\",\"driver_called\":false," +
        "\"readiness\":" + ec5PowerQualifierV2ReadinessJson() +
        ",\"probe\":null,\"no_retry\":true," +
        "\"no_recovery\":true,\"no_autochain\":true}";
    restartHttpListener();
    return;
  }

  if (!probePending) return;
  probePending = false;
  if (!loadPhase() || phase != kProbeConsumed ||
      runtimeState != RuntimeState::ProbeQueued || probeCallCount != 0 ||
      !sameBootQualified || !qualifiedPinPosture()) {
    enterFault("probe_queue_cursor_or_gpio_mismatch");
    return;
  }
  runtimeState = RuntimeState::Running;
  ++probeCallCount;
  const bool result = ec5PowerQualifierV2RunPonPofOnce();
  const Ec5PowerQualifierV2ProbeReport &probe = ec5PowerQualifierV2ProbeReport();
  sameBootQualified = false;
  static constexpr uint8_t kExpectedCommandTrace[] = {
      0xAA, 0x01, 0x00, 0x05, 0x08, 0x06, 0x03, 0x60, 0x30,
      0x50, 0x61, 0xE3, 0x84, 0xE0, 0xE0, 0x04, 0x02, 0x00,
  };
  bool commandTraceExact =
      probe.commandCount == sizeof(kExpectedCommandTrace);
  for (uint8_t index = 0;
       commandTraceExact && index < sizeof(kExpectedCommandTrace); ++index) {
    commandTraceExact =
        probe.commandTrace[index] == kExpectedCommandTrace[index];
  }
  const bool exactSuccess =
      result && probe.valid && !probe.running && probe.sequenceOk &&
      probe.ponCommandSent && probe.pofCommandSent &&
      probe.postPsrCommandSent && probe.ponBusySeen && probe.pofBusySeen &&
      probe.ponIdleCompleted && probe.pofIdleCompleted &&
      probe.ponGateEntry == 1 && probe.pofGateEntry == 1 &&
      !probe.waitTimedOut && !probe.busyAssertionMissing &&
      !probe.preCommandIdleFailure && !probe.drfCommandSent &&
      !probe.dtmCommandSent && !probe.lutCommandSent &&
      !probe.ptlwCommandSent && !probe.command86Sent && commandTraceExact &&
      probe.spiHz == 1000000UL && probe.wireEventCount == 58 &&
      probe.wireFnv1a == 0xC12C52D5UL &&
      probe.safeFinishBusyBeforePinsLow == 1 &&
      probe.finalRst == 0 && probe.finalCs1 == 0 && probe.finalCs2 == 0 &&
      probe.finalSck == 0 && probe.finalDc == 0 && probe.finalMosi == 0;
  if (!exactSuccess) {
    enterFault("pon_pof_probe_failed_or_trace_mismatch");
    restartHttpListener();
    return;
  }
  if (!persistPhase(kComplete)) {
    enterFault("complete_persist_failed");
    restartHttpListener();
    return;
  }
  runtimeState = RuntimeState::Complete;
  publishedReport =
      String("{\"schema_version\":4,\"kind\":") +
      "\"mf1750-power-qualifier-pon-pof-no-drf-v2-report\"," +
      identityJson() + ",\"valid\":true,\"boot_nonce\":\"" +
      bootNonce() + "\",\"terminal_state\":\"COMPLETE\"," +
      "\"result\":true,\"ordinal\":1,\"role\":\"" + kRole +
      "\",\"branch\":\"" + kBranch +
      "\",\"phase\":5,\"phase_name\":\"COMPLETE\"," +
      "\"qualification_nonce\":\"" + qualificationNonce() +
      "\",\"driver_called\":true," +
      "\"driver_call_count_for_action\":1," +
      "\"total_driver_call_count\":1," +
      "\"next_ordinal\":2,\"campaign_complete\":true," +
      "\"qualifier_call_count\":" + String(qualifierCallCount) +
      ",\"probe_call_count\":" + String(probeCallCount) +
      ",\"readiness\":" + ec5PowerQualifierV2ReadinessJson() +
      ",\"probe\":" + ec5PowerQualifierV2ProbeJson() +
      ",\"driver\":" + ec5PowerQualifierV2ProbeJson() +
      ",\"no_retry\":true,\"no_recovery\":true," +
      "\"no_autochain\":true}";
  restartHttpListener();
}

void installRoutes() {
  static const char *headers[] = {
      "Content-Type", "Content-Length", "Transfer-Encoding",
      kBuildHeader, kTestHeader, kCampaignHeader, kBootNonceHeader,
      kIntentHeader, kActionHeader, kDescriptorHeader, kOrdinalHeader,
      kArmNonceHeader, kQualificationNonceHeader,
  };
  server.collectHeaders(headers, sizeof(headers) / sizeof(headers[0]));
  server.on(kVersionRoute, HTTP_GET, []() {
    if (requestHasBodyOrArguments())
      server.send(400, "application/json", "{\"error\":\"read_only_body\"}");
    else server.send(200, "application/json", versionJson());
  });
  server.on(kManifestRoute, HTTP_GET, []() {
    if (requestHasBodyOrArguments())
      server.send(400, "application/json", "{\"error\":\"read_only_body\"}");
    else server.send(200, "application/json", manifestJson());
  });
  server.on(kStatusRoute, HTTP_GET, []() {
    if (requestHasBodyOrArguments())
      server.send(400, "application/json", "{\"error\":\"read_only_body\"}");
    else server.send(200, "application/json", statusJson());
  });
  server.on(kReportRoute, HTTP_GET, []() {
    if (requestHasBodyOrArguments())
      server.send(400, "application/json", "{\"error\":\"read_only_body\"}");
    else server.send(200, "application/json", publishedReport);
  });
  server.on(kQualifyRoute, HTTP_POST, handleQualify);
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
  if (std::strlen(WIFI_STA_SSID) > 0) {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_STA_SSID, WIFI_STA_PASSWORD);
    const uint32_t started = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - started < 15000UL)
      delay(250);
    if (WiFi.status() == WL_CONNECTED) return;
  }
  WiFi.mode(WIFI_AP);
  WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASSWORD);
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(200);
  bootNonceHigh = esp_random();
  bootNonceLow = esp_random();
  if ((bootNonceHigh | bootNonceLow) == 0) bootNonceLow = 1;

  ec5PowerQualifierV2Begin();
  storeReady = store.begin(kNvsNamespace, false);
  if (!storeReady) {
    ec5PowerQualifierV2ForceSafeHold();
    runtimeState = RuntimeState::FaultLocked;
    publishFault("nvs_open_or_cursor_invalid");
  } else if (!loadPhase()) {
    enterFault("nvs_open_or_cursor_invalid");
  } else if (!keyPresent && phase == kFresh) {
    runtimeState = RuntimeState::ReadyUnqualified;
    publishedReport =
        String("{\"schema_version\":4,\"kind\":") +
        "\"mf1750-power-qualifier-pon-pof-no-drf-v2-report\"," +
        identityJson() + ",\"valid\":false,\"boot_nonce\":\"" +
        bootNonce() + "\",\"terminal_state\":\"NOT_EXECUTED\"," +
        "\"result\":false,\"error\":\"no_execute_report\"," +
        "\"no_retry\":true,\"no_recovery\":true," +
        "\"no_autochain\":true}";
  } else if (phase == kComplete) {
    runtimeState = RuntimeState::Complete;
    publishedReport =
        String("{\"schema_version\":4,\"kind\":") +
        "\"mf1750-power-qualifier-pon-pof-no-drf-v2-report\"," +
        identityJson() + ",\"valid\":false,\"boot_nonce\":\"" +
        bootNonce() + "\",\"terminal_state\":\"COMPLETE_PERSISTED\"," +
        "\"result\":true,\"campaign_complete\":true," +
        "\"no_retry\":true,\"no_recovery\":true," +
        "\"no_autochain\":true}";
  } else {
    // A reboot after qualification/arm/execute invalidates same-boot proof and
    // can never resume or retry either one-shot.
    enterFault("nonterminal_phase_seen_at_boot");
  }

  startWiFi();
  installRoutes();
  server.begin();
}

void loop() {
  server.handleClient();
  executePendingWork();
  delay(2);
}
