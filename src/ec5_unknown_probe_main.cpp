#include <Arduino.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WebServer.h>
#include <esp_system.h>

#include <cstdio>

#include "epd_config.h"
#include "epd_driver.h"

// This source is intentionally excluded from every production build. The
// dedicated EC5 environments explicitly select it with epd_driver.cpp while
// excluding main.cpp and n7_main.cpp.
#if MF1750_ENABLE_UNKNOWN_PROBE != 1
#error "EC5 requires MF1750_ENABLE_UNKNOWN_PROBE=1"
#endif

#ifndef MF1750_UNKNOWN_PROBE_CODE
#error "EC5 requires exactly one compiled MF1750_UNKNOWN_PROBE_CODE"
#endif

#ifndef EPD_ENABLE_TEST_PATTERN
#error "EC5 requires an explicit EPD_ENABLE_TEST_PATTERN=0 build flag"
#endif

#if EPD_ENABLE_TEST_PATTERN != 0
#error "EC5 must never refresh during boot"
#endif

#if MF1750_UNKNOWN_PROBE_CODE == 0x4
static constexpr uint8_t kCandidateCode = 0x4;
static constexpr const char *kCandidateHex = "0x4";
static constexpr const char *kTestId = "EC5-U04-I02-P01-L64M1";
static constexpr const char *kBuildTag =
    "MF1750_EC5_U04_MIRROR64_CENTER_V2_CORRECTED_2026-08-09";
static constexpr const char *kFrameSha256 =
    "5a2e797ea058797f01fefe6d073bbb28f39bbbf71c078c1af72dbb8fc3e5877e";
static constexpr const char *kDtmSha256 =
    "a8056cdd450f70709ec75a0a04000dfbfb1f06000ae596420902156bec7bab00";
static constexpr const char *kActionId =
    "f03e53525df228719e1e48042e6d924887acb0a9d14d7a00416cc3590830c8d3";
static constexpr const char *kLegacyClaimKey = "u04_phase";
static constexpr const char *kActiveClaimKey = "u04v2_phase";
static constexpr bool kLegacyExpectedPresent = true;
static constexpr uint8_t kLegacyExpectedPhase = 2;
static constexpr uint32_t kFrameFnv1a = 0x68533DC5UL;
static constexpr uint32_t kDtmFnv1a = 0x15B7EDC5UL;
#elif MF1750_UNKNOWN_PROBE_CODE == 0x7
static constexpr uint8_t kCandidateCode = 0x7;
static constexpr const char *kCandidateHex = "0x7";
static constexpr const char *kTestId = "EC5-U07-I02-P01-L64M1";
static constexpr const char *kBuildTag =
    "MF1750_EC5_U07_MIRROR64_CENTER_V2_CORRECTED_2026-08-09";
static constexpr const char *kFrameSha256 =
    "d9d43888c68b483776bb43a53cc1084b8549d00d9ff70ef2f1227fafe0ac7b3e";
static constexpr const char *kDtmSha256 =
    "2e21712aeca3eeec9e24d9312f4a601c7b0212792f7d3419a150442cc80ea6ac";
static constexpr const char *kActionId =
    "8f427d1262afb4d4d430033451cf7afc6f319b172c836fcdf1e16a02a13746ae";
static constexpr const char *kLegacyClaimKey = "u07_phase";
static constexpr const char *kActiveClaimKey = "u07v2_phase";
static constexpr bool kLegacyExpectedPresent = false;
static constexpr uint8_t kLegacyExpectedPhase = 0;
static constexpr uint32_t kFrameFnv1a = 0xA1C5ADC5UL;
static constexpr uint32_t kDtmFnv1a = 0x97F125C5UL;
#else
#error "MF1750_UNKNOWN_PROBE_CODE must be the single candidate 0x4 or 0x7"
#endif

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600,
              "EC5 fixture is frozen for the 1024x600 panel only");
static_assert(EPD_FRAME_BYTES == 307200,
              "EC5 fixture requires the frozen 4bpp frame size");
static_assert(EPD_CONTROLLER_WIDTH == 512 &&
                  EPD_CONTROLLER_FRAME_BYTES == 153600,
              "EC5 fixture requires two 512x600 controller halves");
static_assert(EPD_CS1_SOURCE_HALF == 0 && !EPD_CS1_FLIP_X &&
                  !EPD_CS1_FLIP_Y && !EPD_CS1_NIBBLE_SWAP,
              "EC5 CS1 mapping differs from the frozen fixture identity");
static_assert(EPD_CS2_SOURCE_HALF == 1 && !EPD_CS2_FLIP_X &&
                  !EPD_CS2_FLIP_Y && !EPD_CS2_NIBBLE_SWAP,
              "EC5 CS2 mapping differs from the frozen fixture identity");

namespace {

WebServer server(80);
Preferences legacyClaimStore;
Preferences activeClaimStore;

static constexpr const char *kLayoutId = "EC5_MIRROR64_CENTER_V1";
static constexpr const char *kIdentityRevision = "corrected-v2";
static constexpr const char *kDeviceApiVersion = "MF1750_EC5_DEVICE_V3";
static constexpr const char *kVersionRoute = "/api/ec5/version";
static constexpr const char *kManifestRoute = "/api/ec5/manifest";
static constexpr const char *kStatusRoute = "/api/ec5/status";
static constexpr const char *kReportRoute = "/api/ec5/report";
static constexpr const char *kArmRoute = "/api/ec5/arm";
static constexpr const char *kExecuteRoute = "/api/ec5/execute";
static constexpr const char *kLegacyClaimNamespace = "mf1750_ec5";
static constexpr const char *kActiveClaimNamespace = "mf1750_ec5v2";
static constexpr const char *kBuildHeader = "X-EC5-Build-Tag";
static constexpr const char *kTestHeader = "X-EC5-Test-Id";
static constexpr const char *kActionHeader = "X-EC5-Action-Id";
static constexpr const char *kBootNonceHeader = "X-EC5-Boot-Nonce";
static constexpr const char *kArmNonceHeader = "X-EC5-Arm-Nonce";
static constexpr const char *kIntentHeader = "X-EC5-Intent";
static constexpr const char *kArmIntent =
    "ARM_ONE_VISIBLE_REFRESH_EXPERIMENTAL_NOT_HARDWARE_AUTHORIZATION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ONE_VISIBLE_REFRESH_EXPERIMENTAL_NOT_HARDWARE_AUTHORIZATION";
static constexpr const char *kSafetyScope =
    "accidental_post_interlock_not_hardware_authorization";

static constexpr uint8_t kPersistentVirgin = 0;
static constexpr uint8_t kPersistentClaimed = 1;
static constexpr uint8_t kPersistentConsumed = 2;
static constexpr uint8_t kPersistentFault = 3;
static constexpr uint8_t kPersistentInvalid = 0xFF;

enum class ProbeState : uint8_t {
  BootSelfCheck,
  Ready,
  Armed,
  Queued,
  Running,
  Completed,
  FaultLocked,
};

ProbeState probeState = ProbeState::BootSelfCheck;
bool fixtureSelfCheckPassed = false;
bool driverFixtureGuardPassed = false;
bool gpioInitialized = false;
bool nvsStoresReady = false;
bool legacyClaimStoreReady = false;
bool activeClaimStoreReady = false;
bool legacyKeyPresent = false;
bool legacyMatch = false;
bool activeKeyPresent = false;
bool activeVirgin = false;
bool migrationReady = false;
bool bootMigrationValidated = false;
bool readOnlyFaultLocked = false;
bool executeConsumed = false;
volatile bool executePending = false;
uint8_t persistentPhase = kPersistentInvalid;
uint8_t legacyPhase = kPersistentInvalid;
uint8_t activePhase = kPersistentInvalid;
uint32_t armRequestCount = 0;
uint32_t executeRequestCount = 0;
uint32_t driverCallCount = 0;
uint32_t jobQueuedAtMs = 0;
uint32_t jobStartedAtMs = 0;
uint32_t jobFinishedAtMs = 0;
uint32_t bootNonceHigh = 0;
uint32_t bootNonceLow = 0;
uint32_t armNonceHigh = 0;
uint32_t armNonceLow = 0;
String publishedReport =
    "{\"schema_version\":3,\"valid\":false,\"error\":\"no_execute_report\"}";

const char *probeStateName(ProbeState state) {
  switch (state) {
    case ProbeState::BootSelfCheck:
      return "boot_self_check";
    case ProbeState::Ready:
      return "ready";
    case ProbeState::Armed:
      return "armed";
    case ProbeState::Queued:
      return "queued";
    case ProbeState::Running:
      return "running";
    case ProbeState::Completed:
      return "completed";
    case ProbeState::FaultLocked:
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

String bootNonce() {
  return hex32(bootNonceHigh) + hex32(bootNonceLow);
}

String armNonce() {
  return hex32(armNonceHigh) + hex32(armNonceLow);
}

bool activeStateMatchesProbe() {
  switch (probeState) {
    case ProbeState::BootSelfCheck:
    case ProbeState::Ready:
      return activeVirgin;
    case ProbeState::Armed:
      return activeKeyPresent && activePhase == kPersistentClaimed;
    case ProbeState::Queued:
    case ProbeState::Running:
    case ProbeState::Completed:
      return activeKeyPresent && activePhase == kPersistentConsumed;
    case ProbeState::FaultLocked:
      return activeVirgin ||
             (activeKeyPresent &&
              (activePhase == kPersistentConsumed ||
               activePhase == kPersistentFault));
  }
  return false;
}

bool refreshNvsEvidence() {
  nvsStoresReady = legacyClaimStoreReady && activeClaimStoreReady;
  if (legacyClaimStoreReady) {
    legacyKeyPresent = legacyClaimStore.isKey(kLegacyClaimKey);
    legacyPhase = legacyClaimStore.getUChar(kLegacyClaimKey, kPersistentVirgin);
  } else {
    legacyKeyPresent = false;
    legacyPhase = kPersistentInvalid;
  }
  legacyMatch = legacyClaimStoreReady &&
                legacyKeyPresent == kLegacyExpectedPresent &&
                legacyPhase == kLegacyExpectedPhase;

  if (activeClaimStoreReady) {
    activeKeyPresent = activeClaimStore.isKey(kActiveClaimKey);
    activePhase = activeClaimStore.getUChar(kActiveClaimKey, kPersistentVirgin);
  } else {
    activeKeyPresent = false;
    activePhase = kPersistentInvalid;
  }
  persistentPhase = activePhase;
  activeVirgin = activeClaimStoreReady && !activeKeyPresent &&
                 activePhase == kPersistentVirgin;
  migrationReady = nvsStoresReady && legacyMatch &&
                   (bootMigrationValidated ? activeStateMatchesProbe()
                                           : activeVirgin);
  return migrationReady;
}

bool persistPhase(uint8_t phase) {
  // The legacy handle is opened read-only and is never used here. All V2
  // irreversible state transitions are isolated in the active namespace.
  if (!activeClaimStoreReady) return false;
  if (activeClaimStore.putUChar(kActiveClaimKey, phase) != sizeof(uint8_t)) {
    return false;
  }
  activeKeyPresent = activeClaimStore.isKey(kActiveClaimKey);
  activePhase = activeClaimStore.getUChar(kActiveClaimKey, kPersistentInvalid);
  persistentPhase = activePhase;
  activeVirgin = !activeKeyPresent && activePhase == kPersistentVirgin;
  return activeKeyPresent && activePhase == phase;
}

bool persistentPhaseIs(uint8_t expected) {
  refreshNvsEvidence();
  return migrationReady && activeKeyPresent && activePhase == expected;
}

String nvsContractJson() {
  return String("\"nvs_contract\":{\"legacy\":{\"namespace\":\"") +
         kLegacyClaimNamespace + "\",\"key\":\"" + kLegacyClaimKey +
         "\",\"expected_present\":" +
         (kLegacyExpectedPresent ? "true" : "false") +
         ",\"expected_phase\":" + String(kLegacyExpectedPhase) +
         ",\"read_only\":true},\"active\":{\"namespace\":\"" +
         kActiveClaimNamespace + "\",\"key\":\"" + kActiveClaimKey +
         "\",\"expected_present\":false,\"expected_phase\":0," +
         "\"read_only\":false}}";
}

String nvsEvidenceJson() {
  return String("\"legacy_key_present\":") +
         (legacyKeyPresent ? "true" : "false") +
         ",\"legacy_phase\":" + String(legacyPhase) +
         ",\"legacy_match\":" + (legacyMatch ? "true" : "false") +
         ",\"active_key_present\":" +
         (activeKeyPresent ? "true" : "false") +
         ",\"active_phase\":" + String(activePhase) +
         ",\"active_virgin\":" + (activeVirgin ? "true" : "false") +
         ",\"migration_ready\":" + (migrationReady ? "true" : "false");
}

bool requestHasBodyOrArguments() {
  if (server.args() != 0) return true;
  if (server.hasArg("plain")) return true;
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

const char *validateIdentityContract(const char *expectedIntent) {
  if (requestHasBodyOrArguments()) return "body_or_arguments_forbidden";
  if (!exactHeader(kBuildHeader, String(kBuildTag)))
    return "build_tag_missing_or_mismatch";
  if (!exactHeader(kTestHeader, String(kTestId)))
    return "test_id_missing_or_mismatch";
  if (!exactHeader(kActionHeader, String(kActionId)))
    return "action_id_missing_or_mismatch";
  if (!exactHeader(kBootNonceHeader, bootNonce()))
    return "boot_nonce_missing_or_stale";
  if (!exactHeader(kIntentHeader, String(expectedIntent)))
    return "intent_missing_or_mismatch";
  return nullptr;
}

String versionJson() {
  return String("{\"schema_version\":3,\"kind\":\"") +
         "mf1750-ec5-unknown-probe-version\",\"build_tag\":\"" + kBuildTag +
         "\",\"device_api_version\":\"" + kDeviceApiVersion +
         "\",\"identity_revision\":\"" + kIdentityRevision +
         "\",\"driver_api_version\":\"" + EPD_DRIVER_API_VERSION +
         "\",\"candidate_code\":\"" + kCandidateHex +
         "\",\"layout_id\":\"" + kLayoutId +
         "\",\"automatic_execute\":false,\"startup_refresh\":false," +
         "\"raw_frame_ingress\":false,\"retry\":false,\"recovery\":false," +
         "\"boot_fixture_guard\":\"exact_driver_action_validator\"," +
         "\"persistent_claim\":true,\"arm_required\":true," +
         "\"execute_limit_per_binary_candidate\":1,\"safety_scope\":\"" +
         kSafetyScope + "\"}";
}

String manifestJson() {
  refreshNvsEvidence();
  return String("{\"schema_version\":3,\"kind\":\"") +
         "mf1750-ec5-compiled-fixture-manifest\",\"scope\":" +
         "\"experimental_scaffold_not_hardware_authorization\",\"layout_id\":\"" +
         kLayoutId + "\",\"test_id\":\"" + kTestId +
         "\",\"action_id\":\"" + kActionId +
         "\",\"candidate_code\":" + String(kCandidateCode) +
         ",\"candidate_code_hex\":\"" + kCandidateHex +
         "\",\"intended_initial_code\":1,\"sequence_class\":" +
         "\"white_initial_single_probe\",\"repetition\":1,\"width\":1024," +
         "\"height\":600,\"frame_bytes\":307200,\"pixel_packing\":" +
         "\"row_major_4bpp_even_x_high_nibble\",\"roi_cs1\":" +
         "{\"x0\":224,\"x1\":288,\"y0\":268,\"y1\":332},\"roi_cs2\":" +
         "{\"x0\":736,\"x1\":800,\"y0\":268,\"y1\":332}," +
         "\"guard_cs1\":{\"x0\":192,\"x1\":320,\"y0\":236,\"y1\":364}," +
         "\"guard_cs2\":{\"x0\":704,\"x1\":832,\"y0\":236,\"y1\":364}," +
         "\"known_white_pixels\":606208,\"unknown_pixels\":8192," +
         "\"frame_sha256\":\"" + kFrameSha256 +
         "\",\"frame_fnv1a\":\"0x" + hex32(kFrameFnv1a) +
         "\",\"cs1_dtm_sha256\":\"" + kDtmSha256 +
         "\",\"cs1_dtm_fnv1a\":\"0x" + hex32(kDtmFnv1a) +
         "\",\"cs2_dtm_sha256\":\"" + kDtmSha256 +
         "\",\"cs2_dtm_fnv1a\":\"0x" + hex32(kDtmFnv1a) +
         "\",\"mapping_cs1\":[0,0,0,0],\"mapping_cs2\":[1,0,0,0]," +
         "\"build_tag\":\"" + kBuildTag +
         "\",\"device_api_version\":\"" + kDeviceApiVersion +
         "\",\"identity_revision\":\"" + kIdentityRevision +
         "\",\"otp_mode\":\"existing_on_chip_otp_unchanged\"," +
         "\"mutation_contract\":{\"bodyless\":true," +
         "\"exact_build_test_action_boot_nonce\":true," +
         "\"arm_nonce_required_for_execute\":true," +
         "\"not_hardware_authorization\":true}," +
         "\"exact_driver_fixture_guard_required\":true," +
         nvsContractJson() + "," + nvsEvidenceJson() + "," +
         "\"manifest_payload_sha256\":null,\"binary_sha256\":null," +
         "\"external_build_sidecar_required\":true}";
}

String gpioJson() {
  if (!gpioInitialized) {
    return "\"gpio_initialized\":false,\"busy\":null,\"rst\":null," \
           "\"cs\":null,\"cs2\":null";
  }
  return String("\"gpio_initialized\":true,\"busy\":") +
         String(epdReadBusy()) + ",\"rst\":" + String(digitalRead(EPD_PIN_RST)) +
         ",\"cs\":" + String(digitalRead(EPD_PIN_CS)) + ",\"cs2\":" +
         String(digitalRead(EPD_PIN_CS2));
}

String statusJson() {
  refreshNvsEvidence();
  return String("{\"schema_version\":3,\"kind\":\"") +
         "mf1750-ec5-unknown-probe-status\",\"boot_nonce\":\"" + bootNonce() +
         "\",\"build_tag\":\"" + kBuildTag +
         "\",\"device_api_version\":\"" + kDeviceApiVersion +
         "\",\"identity_revision\":\"" + kIdentityRevision +
         "\",\"test_id\":\"" +
         kTestId + "\",\"action_id\":\"" +
         kActionId + "\",\"state\":\"" +
         probeStateName(probeState) +
         "\",\"fixture_self_check_passed\":" +
         (fixtureSelfCheckPassed ? "true" : "false") +
         ",\"driver_fixture_guard_passed\":" +
         (driverFixtureGuardPassed ? "true" : "false") +
          ",\"claim_store_ready\":" + (nvsStoresReady ? "true" : "false") +
         ",\"persistent_phase\":" + String(persistentPhase) +
         ",\"arm_request_count\":" + String(armRequestCount) +
         ",\"execute_consumed\":" + (executeConsumed ? "true" : "false") +
         ",\"execute_pending\":" + (executePending ? "true" : "false") +
         ",\"execute_request_count\":" + String(executeRequestCount) +
         ",\"driver_call_count\":" + String(driverCallCount) + "," + gpioJson() +
         "," + nvsContractJson() + "," + nvsEvidenceJson() +
         "}";
}

String driverEvidenceJson(const EpdOperationReport &report) {
  return String("{\"driver_evidence_schema_version\":2,\"operation_id\":") +
         String(report.operationId) +
         ",\"valid\":" + (report.valid ? "true" : "false") +
         ",\"running\":" + (report.running ? "true" : "false") +
         ",\"sequence_ok\":" + (report.sequenceOk ? "true" : "false") +
         ",\"wait_timeout\":" + (report.waitTimedOut ? "true" : "false") +
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
         "\",\"busy_missing_stage\":\"" + String(report.busyMissingStage) +
         "\",\"pre_command_busy_stage\":\"" +
         String(report.preCommandBusyStage) +
         "\",\"safe_finish\":{\"busy_before_pins_low\":" +
         String(report.safeFinishBusyBeforePinsLow) +
         ",\"busy_after_pins_low\":" + String(report.safeFinishBusyAfterPinsLow) +
         ",\"busy_after_5ms\":" + String(report.safeFinishBusyAfter5Ms) +
         ",\"final_gpio\":{\"busy\":" + String(report.finalBusyLevel) +
         ",\"rst\":" + String(report.finalRstLevel) + ",\"cs\":" +
         String(report.finalCs1Level) + ",\"cs2\":" +
         String(report.finalCs2Level) + "}}}";
}

void publishNoExecuteReport() {
  refreshNvsEvidence();
  publishedReport =
      String("{\"schema_version\":3,\"kind\":\"") +
      "mf1750-ec5-unknown-probe-report\",\"valid\":false,\"test_id\":\"" +
      kTestId + "\",\"build_tag\":\"" + kBuildTag +
      "\",\"device_api_version\":\"" + kDeviceApiVersion +
      "\",\"identity_revision\":\"" + kIdentityRevision +
      "\",\"boot_nonce\":\"" + bootNonce() + "\",\"action_id\":\"" +
      kActionId + "\",\"candidate_code\":" + String(kCandidateCode) +
      ",\"terminal_state\":\"NOT_EXECUTED\",\"error\":\"no_execute_report\"," +
      "\"driver_fixture_guard_passed\":" +
      (driverFixtureGuardPassed ? "true" : "false") +
      ",\"execute_consumed\":false,\"driver_called\":false," +
      "\"persistent_phase\":" + String(persistentPhase) +
      ",\"no_retry\":true,\"no_recovery\":true," + nvsContractJson() +
      "," + nvsEvidenceJson() + "}";
}

void publishRejectedMutation(const char *error) {
  refreshNvsEvidence();
  publishedReport =
      String("{\"schema_version\":3,\"kind\":\"") +
      "mf1750-ec5-unknown-probe-report\",\"valid\":false,\"test_id\":\"" +
      kTestId + "\",\"build_tag\":\"" + kBuildTag +
      "\",\"device_api_version\":\"" + kDeviceApiVersion +
      "\",\"identity_revision\":\"" + kIdentityRevision +
      "\",\"boot_nonce\":\"" + bootNonce() +
      "\",\"action_id\":\"" + kActionId +
      "\",\"candidate_code\":" + String(kCandidateCode) +
      ",\"terminal_state\":\"FAULT_LOCKED\",\"error\":\"" + error +
      "\",\"driver_fixture_guard_passed\":" +
      (driverFixtureGuardPassed ? "true" : "false") +
      ",\"execute_consumed\":true,\"driver_called\":false," +
      "\"persistent_phase\":" + String(persistentPhase) +
      ",\"no_retry\":true,\"no_recovery\":true," + nvsContractJson() +
      "," + nvsEvidenceJson() + "}";
}

void enterPersistentFault(const char *error) {
  readOnlyFaultLocked = false;
  executePending = false;
  executeConsumed = true;
  // No network route clears this value. A failed write still leaves any prior
  // claim/consumed value non-virgin, which also locks the next boot.
  persistPhase(kPersistentFault);
  probeState = ProbeState::FaultLocked;
  publishRejectedMutation(error);
}

void enterReadOnlyFault(const char *error) {
  // Migration/boot faults must never mutate either namespace. In particular,
  // do not create an active FAULT value to disguise absent or unexpected
  // legacy evidence.
  readOnlyFaultLocked = true;
  executePending = false;
  executeConsumed = true;
  probeState = ProbeState::FaultLocked;
  refreshNvsEvidence();
  publishRejectedMutation(error);
}

void rejectMutation(int httpStatus, const char *error) {
  refreshNvsEvidence();
  if (readOnlyFaultLocked || !bootMigrationValidated || !migrationReady ||
      !driverFixtureGuardPassed) {
    enterReadOnlyFault(error);
  } else {
    enterPersistentFault(error);
  }
  server.send(httpStatus, "application/json",
              String("{\"accepted\":false,\"fault_locked\":true,") +
                  "\"error\":\"" + error +
                  "\",\"no_retry\":true,\"no_recovery\":true}");
}

void rejectNvsMismatch(int httpStatus, const char *error) {
  enterReadOnlyFault(error);
  server.send(httpStatus, "application/json",
              String("{\"accepted\":false,\"fault_locked\":true,") +
                  "\"error\":\"" + error +
                  "\",\"nvs_read_only_failure\":true," +
                  "\"no_retry\":true,\"no_recovery\":true}");
}

void handleArm() {
  ++armRequestCount;
  refreshNvsEvidence();
  if (!migrationReady || !legacyMatch || !activeVirgin) {
    rejectNvsMismatch(503, "arm_nvs_migration_mismatch");
    return;
  }
  if (probeState != ProbeState::Ready || executeConsumed ||
      activePhase != kPersistentVirgin) {
    rejectMutation(409, "arm_duplicate_or_not_virgin");
    return;
  }

  const char *contractError = validateIdentityContract(kArmIntent);
  if (contractError != nullptr) {
    rejectMutation(400, contractError);
    return;
  }
  if (!fixtureSelfCheckPassed || !gpioInitialized || !nvsStoresReady) {
    rejectMutation(503, "arm_preflight_not_ready");
    return;
  }

  armNonceHigh = esp_random();
  armNonceLow = esp_random();
  if ((armNonceHigh | armNonceLow) == 0) armNonceLow = 1;
  // Persisting CLAIMED is the irreversible claim-before-display boundary.
  if (!persistPhase(kPersistentClaimed)) {
    rejectMutation(503, "persistent_claim_write_failed");
    return;
  }
  probeState = ProbeState::Armed;
  refreshNvsEvidence();
  publishNoExecuteReport();
  server.send(
      201, "application/json",
      String("{\"accepted\":true,\"armed\":true,\"test_id\":\"") + kTestId +
          "\",\"build_tag\":\"" + kBuildTag + "\",\"action_id\":\"" +
          kActionId + "\",\"device_api_version\":\"" + kDeviceApiVersion +
          "\",\"identity_revision\":\"" + kIdentityRevision +
          "\",\"boot_nonce\":\"" +
          bootNonce() + "\",\"arm_nonce\":\"" + armNonce() +
          "\",\"persistent_phase\":1,\"migration_ready\":" +
          (migrationReady ? "true" : "false") +
          ",\"safety_scope\":\"" + kSafetyScope +
          "\",\"not_hardware_authorization\":true}");
}

void handleExecute() {
  ++executeRequestCount;
  refreshNvsEvidence();
  if (!migrationReady || !legacyMatch || !activeKeyPresent ||
      activePhase != kPersistentClaimed) {
    rejectNvsMismatch(503, "execute_nvs_migration_mismatch");
    return;
  }
  if (probeState != ProbeState::Armed || executeConsumed ||
      activePhase != kPersistentClaimed) {
    rejectMutation(409, "execute_duplicate_stale_or_not_armed");
    return;
  }

  const char *contractError = validateIdentityContract(kExecuteIntent);
  if (contractError != nullptr) {
    rejectMutation(400, contractError);
    return;
  }
  if (!exactHeader(kArmNonceHeader, armNonce())) {
    rejectMutation(400, "arm_nonce_missing_or_stale");
    return;
  }
  if (!fixtureSelfCheckPassed || !gpioInitialized || !nvsStoresReady) {
    rejectMutation(503, "execute_preflight_not_ready");
    return;
  }

  // CONSUMED is committed and read back before a display job can be queued.
  // A reset at any later instruction therefore boots FAULT_LOCKED, never retry.
  if (!persistPhase(kPersistentConsumed)) {
    rejectMutation(503, "persistent_consumed_write_failed");
    return;
  }
  executeConsumed = true;

  jobQueuedAtMs = millis();
  probeState = ProbeState::Queued;
  refreshNvsEvidence();
  executePending = true;
  server.send(202, "application/json",
              String("{\"accepted\":true,\"job_id\":1,\"test_id\":\"") +
                  kTestId + "\",\"build_tag\":\"" + kBuildTag +
                  "\",\"action_id\":\"" + kActionId +
                  "\",\"device_api_version\":\"" + kDeviceApiVersion +
                  "\",\"identity_revision\":\"" + kIdentityRevision +
                  "\",\"boot_nonce\":\"" + bootNonce() +
                  "\",\"execute_consumed\":true,\"persistent_phase\":2," +
                  "\"migration_ready\":" +
                  (migrationReady ? "true" : "false") + "," +
                  "\"no_retry\":true,\"no_recovery\":true}");
}

void installRoutes() {
  static const char *requestHeaders[] = {
      "Content-Type",   "Content-Length",  "Transfer-Encoding",
      kBuildHeader,     kTestHeader,         kActionHeader,
      kBootNonceHeader, kArmNonceHeader,     kIntentHeader,
  };
  server.collectHeaders(requestHeaders,
                        sizeof(requestHeaders) / sizeof(requestHeaders[0]));

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
    const uint32_t startedAt = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - startedAt < 15000UL) {
      delay(250);
    }
    if (WiFi.status() == WL_CONNECTED) {
      Serial.printf("EC5 WiFi STA IP: %s\n", WiFi.localIP().toString().c_str());
      return;
    }
  }
  WiFi.mode(WIFI_AP);
  WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASSWORD);
  Serial.printf("EC5 WiFi AP IP: %s\n", WiFi.softAPIP().toString().c_str());
}

void executePendingProbe() {
  if (!executePending) {
    return;
  }
  if (!persistentPhaseIs(kPersistentConsumed)) {
    enterReadOnlyFault("runtime_claim_readback_failed");
    return;
  }
  if (probeState != ProbeState::Queued || driverCallCount != 0) {
    enterPersistentFault("runtime_queue_state_failed");
    return;
  }
  executePending = false;
  probeState = ProbeState::Running;
  jobStartedAtMs = millis();
  ++driverCallCount;
  const bool result = epdDisplayCompiledUnknownProbe();
  jobFinishedAtMs = millis();
  const EpdOperationReport &driver = epdGetLastOperationReport();
  probeState = result ? ProbeState::Completed : ProbeState::FaultLocked;
  refreshNvsEvidence();
  publishedReport =
      String("{\"schema_version\":3,\"kind\":\"") +
      "mf1750-ec5-unknown-probe-report\",\"valid\":true,\"test_id\":\"" +
      kTestId + "\",\"build_tag\":\"" + kBuildTag +
      "\",\"device_api_version\":\"" + kDeviceApiVersion +
      "\",\"identity_revision\":\"" + kIdentityRevision +
      "\",\"boot_nonce\":\"" + bootNonce() +
      "\",\"action_id\":\"" + kActionId +
      "\",\"candidate_code\":" + String(kCandidateCode) +
      ",\"job_id\":1,\"terminal_state\":\"" + probeStateName(probeState) +
      "\",\"result\":" + (result ? "true" : "false") +
      ",\"driver_fixture_guard_passed\":" +
      (driverFixtureGuardPassed ? "true" : "false") +
      ",\"execute_consumed\":true,\"driver_called\":true," +
      "\"driver_call_count\":1,\"persistent_phase\":2," +
      "\"no_retry\":true,\"no_recovery\":true,\"job_queued_at_ms\":" +
      String(jobQueuedAtMs) + ",\"job_started_at_ms\":" +
      String(jobStartedAtMs) + ",\"job_finished_at_ms\":" +
      String(jobFinishedAtMs) + ",\"driver\":" + driverEvidenceJson(driver) +
      "," + nvsContractJson() + "," + nvsEvidenceJson() + "}";
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(50);
  Serial.println("\nMF1750 EC5 isolated unknown-code probe booting");
  Serial.printf("Build: %s\n", kBuildTag);
  Serial.printf("Compiled candidate: %s; fixture: %s\n", kCandidateHex, kTestId);
  Serial.println("No startup refresh/raw ingress/retry/recovery");
  Serial.println("Network interlock is NOT hardware authorization");

  bootNonceHigh = esp_random();
  bootNonceLow = esp_random();
  // Run the exact action-side compiled frame/DTM guard on every boot, even if
  // an older persistent claim later keeps mutation routes locked. The helper
  // performs no GPIO, SPI, reset, or panel operation, so GET status/report can
  // prove the guard result while J2 is disconnected.
  driverFixtureGuardPassed = epdValidateCompiledUnknownProbeFixture();
  fixtureSelfCheckPassed = driverFixtureGuardPassed;
  // Migration order is frozen: exact guard, legacy read-only open/read, active
  // read-write open/read, then validation. Opening the active namespace may
  // create its namespace metadata, but no key is written unless a later ARM or
  // EXECUTE transition is explicitly accepted.
  legacyClaimStoreReady =
      legacyClaimStore.begin(kLegacyClaimNamespace, true /* readOnly */);
  if (legacyClaimStoreReady) {
    legacyKeyPresent = legacyClaimStore.isKey(kLegacyClaimKey);
    legacyPhase =
        legacyClaimStore.getUChar(kLegacyClaimKey, kPersistentVirgin);
  }
  activeClaimStoreReady =
      activeClaimStore.begin(kActiveClaimNamespace, false /* readOnly */);
  refreshNvsEvidence();
  bootMigrationValidated = migrationReady;
  refreshNvsEvidence();

  if (!driverFixtureGuardPassed) {
    enterReadOnlyFault("compiled_fixture_self_check_failed");
    Serial.println(
        "EC5 exact driver fixture guard failed; display remains locked");
  } else if (!legacyClaimStoreReady) {
    enterReadOnlyFault("legacy_claim_store_open_failed");
    Serial.println("EC5 legacy read-only claim store unavailable");
  } else if (!activeClaimStoreReady) {
    enterReadOnlyFault("active_claim_store_open_failed");
    Serial.println("EC5 active claim store unavailable");
  } else if (!legacyMatch) {
    enterReadOnlyFault("legacy_migration_mismatch");
    Serial.println("EC5 legacy claim evidence does not match corrected V2");
  } else if (!activeVirgin) {
    enterReadOnlyFault("active_v2_not_virgin");
    Serial.println("EC5 corrected V2 active claim is not absent/virgin");
  } else {
    // This initializes safe GPIO/SPI idle levels only. The compile-time
    // startup pattern flag is zero; no display call occurs during setup.
    epdBegin();
    gpioInitialized = true;
    probeState = ProbeState::Ready;
    refreshNvsEvidence();
    publishNoExecuteReport();
  }

  startWiFi();
  installRoutes();
  server.begin();
  Serial.printf("Read-only manifest: %s\n", kManifestRoute);
  Serial.printf("Bodyless arm route: POST %s\n", kArmRoute);
  Serial.printf("Bodyless execute route: POST %s\n", kExecuteRoute);
}

void loop() {
  server.handleClient();
  executePendingProbe();
  delay(2);
}
