#include <Arduino.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WebServer.h>
#include <esp_system.h>

#include <cstdio>
#include <cstring>

#include "epd_config.h"
#include "epd_driver.h"

// Dedicated experimental build only. The complete comparison frame is
// compile-time fixed; this source is excluded from all other environments.
#if MF1750_ENABLE_U04_U05_COMPARE != 1
#error "U04/U05 comparison requires MF1750_ENABLE_U04_U05_COMPARE=1"
#endif

#ifndef EPD_ENABLE_TEST_PATTERN
#error "U04/U05 comparison requires explicit EPD_ENABLE_TEST_PATTERN=0"
#endif

#if EPD_ENABLE_TEST_PATTERN != 0
#error "U04/U05 comparison must never refresh during boot"
#endif

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600,
              "U04/U05 comparison is frozen for the 1024x600 panel");
static_assert(EPD_FRAME_BYTES == 307200 &&
                  EPD_CONTROLLER_FRAME_BYTES == 153600,
              "U04/U05 comparison requires frozen 4bpp cascade geometry");
static_assert(EPD_CS1_SOURCE_HALF == 0 && !EPD_CS1_FLIP_X &&
                  !EPD_CS1_FLIP_Y && !EPD_CS1_NIBBLE_SWAP &&
                  EPD_CS2_SOURCE_HALF == 1 && !EPD_CS2_FLIP_X &&
                  !EPD_CS2_FLIP_Y && !EPD_CS2_NIBBLE_SWAP,
              "U04/U05 comparison mapping differs from MAP_ORIENT_V1");

namespace {

WebServer server(80);
Preferences priorU04Store;
Preferences activeClaimStore;

static constexpr const char *kLayoutId =
    "EC5_U04_U05_QUAD64_DIAGONAL_V1";
static constexpr const char *kIdentityRevision = "u04-u05-compare-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_U04_U05_COMPARE_DEVICE_V1";
static constexpr const char *kBuildTag =
    "MF1750_EC5_U04_U05_QUAD64_DIAGONAL_V1_2026-08-09";
static constexpr const char *kTestId = "EC5-U04-U05-Q64-DIAGONAL-V1";
static constexpr const char *kActionId =
    "70db952b1d708511e1fdcb166b43cd5828fe232562b14d341d848942787d1700";
static constexpr const char *kFrameSha256 =
    "c3f1d19adb80169339d32a7e7e61bb5f3a0db9e2e823080412ea91227eaa310d";
static constexpr const char *kCs1DtmSha256 =
    "583a45a83f38139ea823294a1a0d6f4175bed44876ec94d883fcc04329dfdb50";
static constexpr const char *kCs2DtmSha256 =
    "a9c4ced54fc456f424f615c6885dd661517ebdc8a12ee9581d1420e1a9996ad3";
static constexpr uint32_t kFrameFnv1a = 0x9A7A3DC5UL;
static constexpr uint32_t kCs1DtmFnv1a = 0x65B20DC5UL;
static constexpr uint32_t kCs2DtmFnv1a = 0xD9B20DC5UL;

static constexpr const char *kVersionRoute = "/api/ec5/version";
static constexpr const char *kManifestRoute = "/api/ec5/manifest";
static constexpr const char *kStatusRoute = "/api/ec5/status";
static constexpr const char *kReportRoute = "/api/ec5/report";
static constexpr const char *kArmRoute = "/api/ec5/arm";
static constexpr const char *kExecuteRoute = "/api/ec5/execute";
static constexpr const char *kPriorU04Namespace = "mf1750_ec5v2";
static constexpr const char *kPriorU04Key = "u04v2_phase";
static constexpr const char *kActiveClaimNamespace = "mf1750_ec5cmp";
static constexpr const char *kActiveClaimKey = "u45cmp_phase";
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

enum class CompareState : uint8_t {
  BootSelfCheck,
  Ready,
  Armed,
  Queued,
  Running,
  Completed,
  FaultLocked,
};

CompareState compareState = CompareState::BootSelfCheck;
bool fixtureSelfCheckPassed = false;
bool driverFixtureGuardPassed = false;
bool gpioInitialized = false;
bool nvsStoresReady = false;
bool priorU04StoreReady = false;
bool activeClaimStoreReady = false;
bool priorU04KeyPresent = false;
bool priorU04Match = false;
bool activeKeyPresent = false;
bool activeVirgin = false;
bool migrationReady = false;
bool bootMigrationValidated = false;
bool readOnlyFaultLocked = false;
bool executeConsumed = false;
volatile bool executePending = false;
uint8_t persistentPhase = kPersistentInvalid;
uint8_t priorU04Phase = kPersistentInvalid;
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

const char *compareStateName(CompareState state) {
  switch (state) {
    case CompareState::BootSelfCheck:
      return "boot_self_check";
    case CompareState::Ready:
      return "ready";
    case CompareState::Armed:
      return "armed";
    case CompareState::Queued:
      return "queued";
    case CompareState::Running:
      return "running";
    case CompareState::Completed:
      return "completed";
    case CompareState::FaultLocked:
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

bool activeStateMatchesDevice() {
  switch (compareState) {
    case CompareState::BootSelfCheck:
    case CompareState::Ready:
      return activeVirgin;
    case CompareState::Armed:
      return activeKeyPresent && activePhase == kPersistentClaimed;
    case CompareState::Queued:
    case CompareState::Running:
    case CompareState::Completed:
      return activeKeyPresent && activePhase == kPersistentConsumed;
    case CompareState::FaultLocked:
      return activeVirgin ||
             (activeKeyPresent &&
              (activePhase == kPersistentConsumed ||
               activePhase == kPersistentFault));
  }
  return false;
}

bool refreshNvsEvidence() {
  nvsStoresReady = priorU04StoreReady && activeClaimStoreReady;
  if (priorU04StoreReady) {
    priorU04KeyPresent = priorU04Store.isKey(kPriorU04Key);
    priorU04Phase =
        priorU04Store.getUChar(kPriorU04Key, kPersistentVirgin);
  } else {
    priorU04KeyPresent = false;
    priorU04Phase = kPersistentInvalid;
  }
  priorU04Match = priorU04StoreReady && priorU04KeyPresent &&
                  priorU04Phase == kPersistentConsumed;

  if (activeClaimStoreReady) {
    activeKeyPresent = activeClaimStore.isKey(kActiveClaimKey);
    activePhase =
        activeClaimStore.getUChar(kActiveClaimKey, kPersistentVirgin);
  } else {
    activeKeyPresent = false;
    activePhase = kPersistentInvalid;
  }
  persistentPhase = activePhase;
  activeVirgin = activeClaimStoreReady && !activeKeyPresent &&
                 activePhase == kPersistentVirgin;
  migrationReady = nvsStoresReady && priorU04Match &&
                   (bootMigrationValidated ? activeStateMatchesDevice()
                                           : activeVirgin);
  return migrationReady;
}

bool persistPhase(uint8_t phase) {
  // The corrected-v2 U04 prerequisite handle is read-only. All mutations are
  // isolated to the dedicated comparison namespace and key.
  if (!activeClaimStoreReady) return false;
  if (activeClaimStore.putUChar(kActiveClaimKey, phase) != sizeof(uint8_t)) {
    return false;
  }
  activeKeyPresent = activeClaimStore.isKey(kActiveClaimKey);
  activePhase =
      activeClaimStore.getUChar(kActiveClaimKey, kPersistentInvalid);
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
         kPriorU04Namespace + "\",\"key\":\"" + kPriorU04Key +
         "\",\"expected_present\":true,\"expected_phase\":2," +
         "\"read_only\":true},\"active\":{\"namespace\":\"" +
         kActiveClaimNamespace + "\",\"key\":\"" + kActiveClaimKey +
         "\",\"expected_present\":false,\"expected_phase\":0," +
         "\"read_only\":false}}";
}

String nvsEvidenceJson() {
  return String("\"legacy_key_present\":") +
         (priorU04KeyPresent ? "true" : "false") +
         ",\"legacy_phase\":" + String(priorU04Phase) +
         ",\"legacy_match\":" + (priorU04Match ? "true" : "false") +
         ",\"active_key_present\":" +
         (activeKeyPresent ? "true" : "false") +
         ",\"active_phase\":" + String(activePhase) +
         ",\"active_virgin\":" + (activeVirgin ? "true" : "false") +
         ",\"migration_ready\":" + (migrationReady ? "true" : "false");
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
         "mf1750-ec5-u04-u05-compare-version\",\"build_tag\":\"" +
         kBuildTag + "\",\"device_api_version\":\"" + kDeviceApiVersion +
         "\",\"identity_revision\":\"" + kIdentityRevision +
         "\",\"driver_api_version\":\"" + EPD_DRIVER_API_VERSION +
         "\",\"layout_id\":\"" + kLayoutId +
         "\",\"compiled_codes\":[4,5],\"automatic_execute\":false," +
         "\"startup_refresh\":false,\"raw_frame_ingress\":false," +
         "\"dither\":false,\"lut_modification\":false,\"retry\":false," +
         "\"recovery\":false,\"boot_fixture_guard\":" +
         "\"exact_driver_action_validator\",\"persistent_claim\":true," +
         "\"arm_required\":true,\"execute_limit_per_binary\":1," +
         "\"safety_scope\":\"" + kSafetyScope + "\"}";
}

String manifestJson() {
  refreshNvsEvidence();
  return String("{\"schema_version\":3,\"kind\":\"") +
         "mf1750-ec5-compiled-fixture-manifest\",\"scope\":" +
         "\"experimental_scaffold_not_hardware_authorization\"," +
         "\"layout_id\":\"" + kLayoutId + "\",\"test_id\":\"" +
         kTestId + "\",\"action_id\":\"" + kActionId +
         "\",\"sequence_class\":" +
         "\"white_initial_fixed_nodither_diagonal_crossover\"," +
         "\"repetition\":1,\"width\":1024,\"height\":600," +
         "\"frame_bytes\":307200,\"pixel_packing\":" +
         "\"row_major_4bpp_even_x_high_nibble\",\"background_code\":1," +
         "\"rois\":[" +
         "{\"roi_id\":\"CS1_TOP_U04\",\"controller\":\"CS1\"," +
         "\"vertical_position\":\"top\",\"code\":4,\"x0\":224," +
         "\"x1\":288,\"y0\":188,\"y1\":252}," +
         "{\"roi_id\":\"CS1_BOTTOM_U05\",\"controller\":\"CS1\"," +
         "\"vertical_position\":\"bottom\",\"code\":5,\"x0\":224," +
         "\"x1\":288,\"y0\":348,\"y1\":412}," +
         "{\"roi_id\":\"CS2_TOP_U05\",\"controller\":\"CS2\"," +
         "\"vertical_position\":\"top\",\"code\":5,\"x0\":736," +
         "\"x1\":800,\"y0\":188,\"y1\":252}," +
         "{\"roi_id\":\"CS2_BOTTOM_U04\",\"controller\":\"CS2\"," +
         "\"vertical_position\":\"bottom\",\"code\":4,\"x0\":736," +
         "\"x1\":800,\"y0\":348,\"y1\":412}]," +
         "\"histogram\":{\"1\":598016,\"4\":8192,\"5\":8192}," +
         "\"frame_sha256\":\"" + kFrameSha256 +
         "\",\"frame_fnv1a\":\"0x" + hex32(kFrameFnv1a) +
         "\",\"cs1_dtm_sha256\":\"" + kCs1DtmSha256 +
         "\",\"cs1_dtm_fnv1a\":\"0x" + hex32(kCs1DtmFnv1a) +
         "\",\"cs2_dtm_sha256\":\"" + kCs2DtmSha256 +
         "\",\"cs2_dtm_fnv1a\":\"0x" + hex32(kCs2DtmFnv1a) +
         "\",\"mapping_cs1\":[0,0,0,0],\"mapping_cs2\":[1,0,0,0]," +
         "\"build_tag\":\"" + kBuildTag +
         "\",\"device_api_version\":\"" + kDeviceApiVersion +
         "\",\"identity_revision\":\"" + kIdentityRevision +
         "\",\"otp_mode\":\"existing_on_chip_otp_unchanged\"," +
         "\"dither\":false,\"mutation_contract\":{\"bodyless\":true," +
         "\"exact_build_test_action_boot_nonce\":true," +
         "\"arm_nonce_required_for_execute\":true," +
         "\"not_hardware_authorization\":true}," +
         "\"exact_driver_fixture_guard_required\":true," +
         nvsContractJson() + "," + nvsEvidenceJson() +
         ",\"manifest_payload_sha256\":null,\"binary_sha256\":null," +
         "\"external_build_sidecar_required\":true}";
}

String gpioJson() {
  if (!gpioInitialized) {
    return "\"gpio_initialized\":false,\"busy\":null,\"rst\":null," \
           "\"cs\":null,\"cs2\":null";
  }
  return String("\"gpio_initialized\":true,\"busy\":") +
         String(epdReadBusy()) + ",\"rst\":" +
         String(digitalRead(EPD_PIN_RST)) + ",\"cs\":" +
         String(digitalRead(EPD_PIN_CS)) + ",\"cs2\":" +
         String(digitalRead(EPD_PIN_CS2));
}

String statusJson() {
  refreshNvsEvidence();
  return String("{\"schema_version\":3,\"kind\":\"") +
         "mf1750-ec5-u04-u05-compare-status\",\"boot_nonce\":\"" +
         bootNonce() + "\",\"build_tag\":\"" + kBuildTag +
         "\",\"device_api_version\":\"" + kDeviceApiVersion +
         "\",\"identity_revision\":\"" + kIdentityRevision +
         "\",\"layout_id\":\"" + kLayoutId + "\",\"test_id\":\"" +
         kTestId + "\",\"action_id\":\"" + kActionId +
         "\",\"state\":\"" + compareStateName(compareState) +
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
         ",\"driver_call_count\":" + String(driverCallCount) + "," +
         gpioJson() + "," + nvsContractJson() + "," + nvsEvidenceJson() + "}";
}

String driverEvidenceJson(const EpdOperationReport &report) {
  return String("{\"driver_evidence_schema_version\":2,\"operation_id\":") +
         String(report.operationId) +
         ",\"valid\":" + (report.valid ? "true" : "false") +
         ",\"running\":" + (report.running ? "true" : "false") +
         ",\"sequence_ok\":" + (report.sequenceOk ? "true" : "false") +
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
         ",\"rst\":" + String(report.finalRstLevel) + ",\"cs\":" +
         String(report.finalCs1Level) + ",\"cs2\":" +
         String(report.finalCs2Level) + "}}}";
}

void publishNoExecuteReport() {
  refreshNvsEvidence();
  publishedReport =
      String("{\"schema_version\":3,\"kind\":\"") +
      "mf1750-ec5-u04-u05-compare-report\",\"valid\":false," +
      "\"test_id\":\"" + kTestId + "\",\"build_tag\":\"" + kBuildTag +
      "\",\"device_api_version\":\"" + kDeviceApiVersion +
      "\",\"identity_revision\":\"" + kIdentityRevision +
      "\",\"layout_id\":\"" + kLayoutId + "\",\"boot_nonce\":\"" +
      bootNonce() + "\",\"action_id\":\"" + kActionId +
      "\",\"terminal_state\":\"NOT_EXECUTED\"," +
      "\"error\":\"no_execute_report\",\"driver_fixture_guard_passed\":" +
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
      "mf1750-ec5-u04-u05-compare-report\",\"valid\":false," +
      "\"test_id\":\"" + kTestId + "\",\"build_tag\":\"" + kBuildTag +
      "\",\"device_api_version\":\"" + kDeviceApiVersion +
      "\",\"identity_revision\":\"" + kIdentityRevision +
      "\",\"layout_id\":\"" + kLayoutId + "\",\"boot_nonce\":\"" +
      bootNonce() + "\",\"action_id\":\"" + kActionId +
      "\",\"terminal_state\":\"FAULT_LOCKED\",\"error\":\"" + error +
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
  persistPhase(kPersistentFault);
  compareState = CompareState::FaultLocked;
  publishRejectedMutation(error);
}

void enterReadOnlyFault(const char *error) {
  // Prerequisite or boot failures never mutate either namespace.
  readOnlyFaultLocked = true;
  executePending = false;
  executeConsumed = true;
  compareState = CompareState::FaultLocked;
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
  if (!migrationReady || !priorU04Match || !activeVirgin) {
    rejectNvsMismatch(503, "arm_nvs_migration_mismatch");
    return;
  }
  if (compareState != CompareState::Ready || executeConsumed ||
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
  if (!persistPhase(kPersistentClaimed)) {
    rejectMutation(503, "persistent_claim_write_failed");
    return;
  }
  compareState = CompareState::Armed;
  refreshNvsEvidence();
  publishNoExecuteReport();
  server.send(
      201, "application/json",
      String("{\"accepted\":true,\"armed\":true,\"test_id\":\"") +
          kTestId + "\",\"build_tag\":\"" + kBuildTag +
          "\",\"action_id\":\"" + kActionId +
          "\",\"device_api_version\":\"" + kDeviceApiVersion +
          "\",\"identity_revision\":\"" + kIdentityRevision +
          "\",\"boot_nonce\":\"" + bootNonce() +
          "\",\"arm_nonce\":\"" + armNonce() +
          "\",\"persistent_phase\":1,\"migration_ready\":" +
          (migrationReady ? "true" : "false") +
          ",\"safety_scope\":\"" + kSafetyScope +
          "\",\"not_hardware_authorization\":true}");
}

void handleExecute() {
  ++executeRequestCount;
  refreshNvsEvidence();
  if (!migrationReady || !priorU04Match || !activeKeyPresent ||
      activePhase != kPersistentClaimed) {
    rejectNvsMismatch(503, "execute_nvs_migration_mismatch");
    return;
  }
  if (compareState != CompareState::Armed || executeConsumed ||
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
  // Commit CONSUMED and verify it before the display job can be queued.
  if (!persistPhase(kPersistentConsumed)) {
    rejectMutation(503, "persistent_consumed_write_failed");
    return;
  }
  executeConsumed = true;
  jobQueuedAtMs = millis();
  compareState = CompareState::Queued;
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
                  (migrationReady ? "true" : "false") +
                  ",\"no_retry\":true,\"no_recovery\":true}");
}

void installRoutes() {
  static const char *requestHeaders[] = {
      "Content-Type",   "Content-Length",  "Transfer-Encoding",
      kBuildHeader,     kTestHeader,        kActionHeader,
      kBootNonceHeader, kArmNonceHeader,    kIntentHeader,
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
      Serial.printf("EC5 compare WiFi STA IP: %s\n",
                    WiFi.localIP().toString().c_str());
      return;
    }
  }
  WiFi.mode(WIFI_AP);
  WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASSWORD);
  Serial.printf("EC5 compare WiFi AP IP: %s\n",
                WiFi.softAPIP().toString().c_str());
}

void executePendingComparison() {
  if (!executePending) return;
  if (!persistentPhaseIs(kPersistentConsumed)) {
    enterReadOnlyFault("runtime_claim_readback_failed");
    return;
  }
  if (compareState != CompareState::Queued || driverCallCount != 0) {
    enterPersistentFault("runtime_queue_state_failed");
    return;
  }
  executePending = false;
  compareState = CompareState::Running;
  jobStartedAtMs = millis();
  ++driverCallCount;
  const bool result = epdDisplayCompiledU04U05Compare();
  jobFinishedAtMs = millis();
  const EpdOperationReport &driver = epdGetLastOperationReport();
  compareState = result ? CompareState::Completed : CompareState::FaultLocked;
  refreshNvsEvidence();
  publishedReport =
      String("{\"schema_version\":3,\"kind\":\"") +
      "mf1750-ec5-u04-u05-compare-report\",\"valid\":true," +
      "\"test_id\":\"" + kTestId + "\",\"build_tag\":\"" + kBuildTag +
      "\",\"device_api_version\":\"" + kDeviceApiVersion +
      "\",\"identity_revision\":\"" + kIdentityRevision +
      "\",\"layout_id\":\"" + kLayoutId + "\",\"boot_nonce\":\"" +
      bootNonce() + "\",\"action_id\":\"" + kActionId +
      "\",\"job_id\":1,\"terminal_state\":\"" +
      compareStateName(compareState) + "\",\"result\":" +
      (result ? "true" : "false") +
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
  Serial.println("\nMF1750 EC5 fixed U04/U05 comparison booting");
  Serial.printf("Build: %s\n", kBuildTag);
  Serial.println("No startup refresh/raw ingress/dither/retry/recovery");
  Serial.println("Network interlock is NOT hardware authorization");

  bootNonceHigh = esp_random();
  bootNonceLow = esp_random();
  // The action's exact fixture validator runs before GPIO/SPI initialization.
  driverFixtureGuardPassed = epdValidateCompiledU04U05CompareFixture();
  fixtureSelfCheckPassed = driverFixtureGuardPassed;

  // Frozen order: fixture guard, corrected-v2 U04 read-only evidence, then the
  // independent comparison store. The prior namespace is never writable here.
  priorU04StoreReady =
      priorU04Store.begin(kPriorU04Namespace, true /* readOnly */);
  if (priorU04StoreReady) {
    priorU04KeyPresent = priorU04Store.isKey(kPriorU04Key);
    priorU04Phase =
        priorU04Store.getUChar(kPriorU04Key, kPersistentVirgin);
  }
  activeClaimStoreReady =
      activeClaimStore.begin(kActiveClaimNamespace, false /* readOnly */);
  refreshNvsEvidence();
  bootMigrationValidated = migrationReady;
  refreshNvsEvidence();

  if (!driverFixtureGuardPassed) {
    enterReadOnlyFault("compiled_fixture_self_check_failed");
  } else if (!priorU04StoreReady) {
    enterReadOnlyFault("prior_u04_store_open_failed");
  } else if (!activeClaimStoreReady) {
    enterReadOnlyFault("active_claim_store_open_failed");
  } else if (!priorU04Match) {
    enterReadOnlyFault("prior_corrected_u04_not_consumed");
  } else if (!activeVirgin) {
    enterReadOnlyFault("comparison_claim_not_virgin");
  } else {
    epdBegin();
    gpioInitialized = true;
    compareState = CompareState::Ready;
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
  executePendingComparison();
  delay(2);
}
