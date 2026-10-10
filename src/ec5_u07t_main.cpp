#include <Arduino.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <esp_system.h>

#include <cstdio>
#include <cstring>

#include "epd_config.h"
#include "epd_driver.h"

// Independent technical-only 0x7 probe. This source is selected only by the
// dedicated U07T PlatformIO environment. It deliberately reuses the driver's
// fixed no-ingress 0x7 fixture, but owns a different action identity and NVS
// key from formal corrected-v2 U07.
#if MF1750_ENABLE_U07T_TECHNICAL != 1
#error "U07T requires MF1750_ENABLE_U07T_TECHNICAL=1"
#endif

#if MF1750_ENABLE_UNKNOWN_PROBE != 1
#error "U07T requires the compiled unknown-probe driver"
#endif

#if MF1750_UNKNOWN_PROBE_CODE != 7
#error "U07T is frozen to candidate code 0x7"
#endif

#ifndef EPD_ENABLE_TEST_PATTERN
#error "U07T requires explicit EPD_ENABLE_TEST_PATTERN=0"
#endif

#if EPD_ENABLE_TEST_PATTERN != 0
#error "U07T must never refresh during startup"
#endif

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600,
              "U07T is frozen for the 1024x600 panel");
static_assert(EPD_FRAME_BYTES == 307200 &&
                  EPD_CONTROLLER_FRAME_BYTES == 153600,
              "U07T requires the frozen 4bpp cascade geometry");
static_assert(EPD_CS1_SOURCE_HALF == 0 && !EPD_CS1_FLIP_X &&
                  !EPD_CS1_FLIP_Y && !EPD_CS1_NIBBLE_SWAP &&
                  EPD_CS2_SOURCE_HALF == 1 && !EPD_CS2_FLIP_X &&
                  !EPD_CS2_FLIP_Y && !EPD_CS2_NIBBLE_SWAP,
              "U07T mapping differs from MAP_ORIENT_V1");

namespace {

WebServer server(80);
// The only handle for the formal corrected-v2 namespace is read-only. Both
// formal keys are read through this handle and no write/clear/remove API is
// ever called on it.
Preferences formalV2Store;
// The independent technical key is the sole persistent mutation target.
Preferences technicalClaimStore;

static constexpr const char *kClassification =
    "TECHNICAL_DESCRIPTIVE_NOT_QUALIFIED";
static constexpr const char *kIdentityRevision = "u07t-technical-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_U07T_DEVICE_V1";
static constexpr const char *kLayoutId = "EC5_MIRROR64_CENTER_V1";
static constexpr const char *kBuildTag =
    "MF1750_EC5_U07T_MIRROR64_CENTER_TECHNICAL_V1_2026-08-09";
static constexpr const char *kTestId = "EC5-U07T-I01-P01-L64M1";
static constexpr const char *kActionId =
    "303bb39e496f39caef782aadacb0d63e6d4f9b42df550d4c799a4248a8041310";
static constexpr const char *kFrameSha256 =
    "d9d43888c68b483776bb43a53cc1084b8549d00d9ff70ef2f1227fafe0ac7b3e";
static constexpr const char *kDtmSha256 =
    "2e21712aeca3eeec9e24d9312f4a601c7b0212792f7d3419a150442cc80ea6ac";
static constexpr uint32_t kFrameFnv1a = 0xA1C5ADC5UL;
static constexpr uint32_t kDtmFnv1a = 0x97F125C5UL;
static constexpr uint8_t kCandidateCode = 7;

static constexpr const char *kFormalNamespace = "mf1750_ec5v2";
static constexpr const char *kFormalU04Key = "u04v2_phase";
static constexpr const char *kFormalU07Key = "u07v2_phase";
static constexpr const char *kTechnicalNamespace = "mf1750_ec5t";
static constexpr const char *kTechnicalKey = "u07t_phase";

static constexpr const char *kVersionRoute = "/api/ec5/version";
static constexpr const char *kManifestRoute = "/api/ec5/manifest";
static constexpr const char *kStatusRoute = "/api/ec5/status";
static constexpr const char *kReportRoute = "/api/ec5/report";
static constexpr const char *kArmRoute = "/api/ec5/arm";
static constexpr const char *kExecuteRoute = "/api/ec5/execute";
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

static constexpr uint8_t kVirgin = 0;
static constexpr uint8_t kClaimed = 1;
static constexpr uint8_t kConsumed = 2;
static constexpr uint8_t kFault = 3;
static constexpr uint8_t kInvalid = 0xFF;

enum class TechnicalState : uint8_t {
  BootSelfCheck,
  Ready,
  Armed,
  Queued,
  Running,
  Completed,
  FaultLocked,
};

TechnicalState state = TechnicalState::BootSelfCheck;
bool fixtureSelfCheckPassed = false;
bool driverFixtureGuardPassed = false;
bool gpioInitialized = false;
bool formalStoreReady = false;
bool technicalStoreReady = false;
bool nvsStoresReady = false;
bool formalU04KeyPresent = false;
bool formalU04Match = false;
bool formalU07KeyPresent = false;
bool formalU07Match = false;
bool formalPrerequisitesMatch = false;
bool technicalKeyPresent = false;
bool technicalVirgin = false;
bool migrationReady = false;
bool bootMigrationValidated = false;
bool readOnlyFaultLocked = false;
bool executeConsumed = false;
volatile bool executePending = false;
uint8_t formalU04Phase = kInvalid;
uint8_t formalU07Phase = kInvalid;
uint8_t technicalPhase = kInvalid;
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

const char *stateName(TechnicalState value) {
  switch (value) {
    case TechnicalState::BootSelfCheck:
      return "boot_self_check";
    case TechnicalState::Ready:
      return "ready";
    case TechnicalState::Armed:
      return "armed";
    case TechnicalState::Queued:
      return "queued";
    case TechnicalState::Running:
      return "running";
    case TechnicalState::Completed:
      return "completed";
    case TechnicalState::FaultLocked:
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

bool technicalStateMatches() {
  switch (state) {
    case TechnicalState::BootSelfCheck:
    case TechnicalState::Ready:
      return technicalVirgin;
    case TechnicalState::Armed:
      return technicalKeyPresent && technicalPhase == kClaimed;
    case TechnicalState::Queued:
    case TechnicalState::Running:
    case TechnicalState::Completed:
      return technicalKeyPresent && technicalPhase == kConsumed;
    case TechnicalState::FaultLocked:
      return technicalVirgin ||
             (technicalKeyPresent &&
              (technicalPhase == kConsumed || technicalPhase == kFault));
  }
  return false;
}

bool refreshNvsEvidence() {
  if (formalStoreReady) {
    formalU04KeyPresent = formalV2Store.isKey(kFormalU04Key);
    formalU04Phase = formalV2Store.getUChar(kFormalU04Key, kVirgin);
    formalU07KeyPresent = formalV2Store.isKey(kFormalU07Key);
    formalU07Phase = formalV2Store.getUChar(kFormalU07Key, kVirgin);
  } else {
    formalU04KeyPresent = false;
    formalU04Phase = kInvalid;
    formalU07KeyPresent = false;
    formalU07Phase = kInvalid;
  }
  formalU04Match = formalStoreReady && formalU04KeyPresent &&
                   formalU04Phase == kConsumed;
  formalU07Match = formalStoreReady && !formalU07KeyPresent &&
                   formalU07Phase == kVirgin;
  formalPrerequisitesMatch = formalU04Match && formalU07Match;

  if (technicalStoreReady) {
    technicalKeyPresent = technicalClaimStore.isKey(kTechnicalKey);
    technicalPhase = technicalClaimStore.getUChar(kTechnicalKey, kVirgin);
  } else {
    technicalKeyPresent = false;
    technicalPhase = kInvalid;
  }
  technicalVirgin = technicalStoreReady && !technicalKeyPresent &&
                    technicalPhase == kVirgin;
  nvsStoresReady = formalStoreReady && technicalStoreReady;
  migrationReady = nvsStoresReady && formalPrerequisitesMatch &&
                   (bootMigrationValidated ? technicalStateMatches()
                                           : technicalVirgin);
  return migrationReady;
}

bool persistTechnicalPhase(uint8_t phase) {
  // This is the only persistent write statement in U07T. formalV2Store is
  // read-only and formal u07v2_phase is never created, changed, or cleared.
  if (!technicalStoreReady) return false;
  if (technicalClaimStore.putUChar(kTechnicalKey, phase) != sizeof(uint8_t))
    return false;
  technicalKeyPresent = technicalClaimStore.isKey(kTechnicalKey);
  technicalPhase =
      technicalClaimStore.getUChar(kTechnicalKey, kInvalid);
  technicalVirgin = !technicalKeyPresent && technicalPhase == kVirgin;
  return technicalKeyPresent && technicalPhase == phase;
}

bool technicalPhaseIs(uint8_t expected) {
  refreshNvsEvidence();
  return migrationReady && technicalKeyPresent && technicalPhase == expected;
}

String nvsContractJson() {
  return String("\"nvs_contract\":{\"formal_u04\":{\"namespace\":\"") +
         kFormalNamespace + "\",\"key\":\"" + kFormalU04Key +
         "\",\"expected_present\":true,\"expected_phase\":2," +
         "\"read_only\":true},\"formal_u07\":{\"namespace\":\"" +
         kFormalNamespace + "\",\"key\":\"" + kFormalU07Key +
         "\",\"expected_present\":false,\"expected_phase\":0," +
         "\"read_only\":true,\"never_write_or_clear\":true}," +
         "\"active\":{\"namespace\":\"" + kTechnicalNamespace +
         "\",\"key\":\"" + kTechnicalKey +
         "\",\"expected_present\":false,\"expected_phase\":0," +
         "\"read_only\":false}}";
}

String nvsEvidenceJson() {
  return String("\"formal_store_ready\":") +
         (formalStoreReady ? "true" : "false") +
         ",\"formal_u04_key_present\":" +
         (formalU04KeyPresent ? "true" : "false") +
         ",\"formal_u04_phase\":" + String(formalU04Phase) +
         ",\"formal_u04_match\":" +
         (formalU04Match ? "true" : "false") +
         ",\"formal_u07_key_present\":" +
         (formalU07KeyPresent ? "true" : "false") +
         ",\"formal_u07_phase\":" + String(formalU07Phase) +
         ",\"formal_u07_match\":" +
         (formalU07Match ? "true" : "false") +
         ",\"formal_prerequisites_match\":" +
         (formalPrerequisitesMatch ? "true" : "false") +
         ",\"active_store_ready\":" +
         (technicalStoreReady ? "true" : "false") +
         ",\"active_key_present\":" +
         (technicalKeyPresent ? "true" : "false") +
         ",\"active_phase\":" + String(technicalPhase) +
         ",\"active_virgin\":" +
         (technicalVirgin ? "true" : "false") +
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

const char *validateIdentityContract(const char *intent) {
  if (requestHasBodyOrArguments()) return "body_or_arguments_forbidden";
  if (!exactHeader(kBuildHeader, String(kBuildTag)))
    return "build_tag_missing_or_mismatch";
  if (!exactHeader(kTestHeader, String(kTestId)))
    return "test_id_missing_or_mismatch";
  if (!exactHeader(kActionHeader, String(kActionId)))
    return "action_id_missing_or_mismatch";
  if (!exactHeader(kBootNonceHeader, bootNonce()))
    return "boot_nonce_missing_or_stale";
  if (!exactHeader(kIntentHeader, String(intent)))
    return "intent_missing_or_mismatch";
  return nullptr;
}

String versionJson() {
  refreshNvsEvidence();
  return String("{\"schema_version\":3,\"kind\":") +
         "\"mf1750-ec5-u07t-version\",\"build_tag\":\"" + kBuildTag +
         "\",\"device_api_version\":\"" + kDeviceApiVersion +
         "\",\"identity_revision\":\"" + kIdentityRevision +
         "\",\"classification\":\"" + kClassification +
         "\",\"driver_api_version\":\"" + EPD_DRIVER_API_VERSION +
         "\",\"candidate_code\":\"0x7\",\"layout_id\":\"" + kLayoutId +
         "\",\"automatic_execute\":false,\"startup_refresh\":false," +
         "\"raw_frame_ingress\":false,\"dither\":false," +
         "\"lut_modified\":false,\"retry\":false,\"recovery\":false," +
         "\"persistent_claim\":true,\"arm_required\":true," +
         "\"formal_u07_unclaimed_and_virgin\":" +
         (formalU07Match ? "true" : "false") +
         ",\"safety_scope\":\"" + kSafetyScope + "\"," +
         nvsContractJson() + "," + nvsEvidenceJson() + "}";
}

String manifestJson() {
  refreshNvsEvidence();
  return String("{\"schema_version\":3,\"kind\":") +
         "\"mf1750-ec5-u07t-compiled-fixture-manifest\"," +
         "\"scope\":\"technical_descriptive_not_formal_qualification\"," +
         "\"classification\":\"" + kClassification +
         "\",\"layout_id\":\"" + kLayoutId + "\",\"test_id\":\"" +
         kTestId + "\",\"action_id\":\"" + kActionId +
         "\",\"candidate_code\":7,\"candidate_code_hex\":\"0x7\"," +
         "\"intended_initial_code\":1," +
         "\"sequence_class\":\"white_initial_single_technical_probe\"," +
         "\"repetition\":1,\"width\":1024,\"height\":600," +
         "\"frame_bytes\":307200," +
         "\"pixel_packing\":\"row_major_4bpp_even_x_high_nibble\"," +
         "\"roi_cs1\":{\"x0\":224,\"x1\":288,\"y0\":268,\"y1\":332}," +
         "\"roi_cs2\":{\"x0\":736,\"x1\":800,\"y0\":268,\"y1\":332}," +
         "\"known_white_pixels\":606208,\"candidate_pixels\":8192," +
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
         "\"dither\":false,\"spatial_mixing\":false," +
         "\"raw_frame_ingress\":false,\"startup_refresh\":false," +
         "\"retry\":false,\"recovery\":false,\"lut_modified\":false," +
         "\"formal_u07_unclaimed_and_virgin\":" +
         (formalU07Match ? "true" : "false") + "," +
         nvsContractJson() + "," + nvsEvidenceJson() +
         ",\"manifest_payload_sha256\":null,\"binary_sha256\":null," +
         "\"external_build_sidecar_required\":true}";
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
  refreshNvsEvidence();
  return String("{\"schema_version\":3,\"kind\":\"mf1750-ec5-u07t-status\",") +
         "\"boot_nonce\":\"" + bootNonce() + "\",\"build_tag\":\"" +
         kBuildTag + "\",\"device_api_version\":\"" + kDeviceApiVersion +
         "\",\"identity_revision\":\"" + kIdentityRevision +
         "\",\"classification\":\"" + kClassification +
         "\",\"layout_id\":\"" + kLayoutId + "\",\"test_id\":\"" +
         kTestId + "\",\"action_id\":\"" + kActionId +
         "\",\"state\":\"" + stateName(state) +
         "\",\"fixture_self_check_passed\":" +
         (fixtureSelfCheckPassed ? "true" : "false") +
         ",\"driver_fixture_guard_passed\":" +
         (driverFixtureGuardPassed ? "true" : "false") +
         ",\"claim_store_ready\":" + (nvsStoresReady ? "true" : "false") +
         ",\"persistent_phase\":" + String(technicalPhase) +
         ",\"arm_request_count\":" + String(armRequestCount) +
         ",\"execute_consumed\":" + (executeConsumed ? "true" : "false") +
         ",\"execute_pending\":" + (executePending ? "true" : "false") +
         ",\"execute_request_count\":" + String(executeRequestCount) +
         ",\"driver_call_count\":" + String(driverCallCount) +
         ",\"formal_u07_unclaimed_and_virgin\":" +
         (formalU07Match ? "true" : "false") + "," + gpioJson() + "," +
         nvsContractJson() + "," + nvsEvidenceJson() + "}";
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
         ",\"rst\":" + String(report.finalRstLevel) +
         ",\"cs\":" + String(report.finalCs1Level) +
         ",\"cs2\":" + String(report.finalCs2Level) + "}}}";
}

void publishNoExecuteReport() {
  refreshNvsEvidence();
  publishedReport =
      String("{\"schema_version\":3,\"kind\":\"mf1750-ec5-u07t-report\",") +
      "\"valid\":false,\"test_id\":\"" + kTestId +
      "\",\"build_tag\":\"" + kBuildTag +
      "\",\"device_api_version\":\"" + kDeviceApiVersion +
      "\",\"identity_revision\":\"" + kIdentityRevision +
      "\",\"classification\":\"" + kClassification +
      "\",\"boot_nonce\":\"" + bootNonce() + "\",\"action_id\":\"" +
      kActionId +
      "\",\"candidate_code\":7,\"terminal_state\":\"NOT_EXECUTED\"," +
      "\"error\":\"no_execute_report\"," +
      "\"driver_fixture_guard_passed\":" +
      (driverFixtureGuardPassed ? "true" : "false") +
      ",\"execute_consumed\":false,\"driver_called\":false," +
      "\"persistent_phase\":" + String(technicalPhase) +
      ",\"formal_u07_unclaimed_and_virgin\":" +
      (formalU07Match ? "true" : "false") + "," +
      "\"no_retry\":true,\"no_recovery\":true," + nvsContractJson() +
      "," + nvsEvidenceJson() + "}";
}

void publishRejectedMutation(const char *error) {
  refreshNvsEvidence();
  publishedReport =
      String("{\"schema_version\":3,\"kind\":\"mf1750-ec5-u07t-report\",") +
      "\"valid\":false,\"test_id\":\"" + kTestId +
      "\",\"build_tag\":\"" + kBuildTag +
      "\",\"device_api_version\":\"" + kDeviceApiVersion +
      "\",\"identity_revision\":\"" + kIdentityRevision +
      "\",\"classification\":\"" + kClassification +
      "\",\"boot_nonce\":\"" + bootNonce() + "\",\"action_id\":\"" +
      kActionId +
      "\",\"candidate_code\":7,\"terminal_state\":\"FAULT_LOCKED\"," +
      "\"error\":\"" + error +
      "\",\"driver_fixture_guard_passed\":" +
      (driverFixtureGuardPassed ? "true" : "false") +
      ",\"execute_consumed\":true,\"driver_called\":false," +
      "\"persistent_phase\":" + String(technicalPhase) +
      ",\"formal_u07_unclaimed_and_virgin\":" +
      (formalU07Match ? "true" : "false") + "," +
      "\"no_retry\":true,\"no_recovery\":true," + nvsContractJson() +
      "," + nvsEvidenceJson() + "}";
}

void enterReadOnlyFault(const char *error) {
  // Formal/prerequisite/NVS readback faults never write even the technical
  // fault phase, and necessarily never mutate formal corrected-v2 state.
  readOnlyFaultLocked = true;
  executePending = false;
  executeConsumed = true;
  state = TechnicalState::FaultLocked;
  refreshNvsEvidence();
  publishRejectedMutation(error);
}

void enterPersistentFault(const char *error) {
  readOnlyFaultLocked = false;
  executePending = false;
  executeConsumed = true;
  persistTechnicalPhase(kFault);
  state = TechnicalState::FaultLocked;
  publishRejectedMutation(error);
}

void rejectMutation(int httpStatus, const char *error) {
  refreshNvsEvidence();
  if (readOnlyFaultLocked || !bootMigrationValidated || !migrationReady ||
      !formalPrerequisitesMatch || !driverFixtureGuardPassed) {
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
  if (!migrationReady || !formalPrerequisitesMatch || !technicalVirgin) {
    rejectNvsMismatch(503, "arm_nvs_migration_mismatch");
    return;
  }
  if (state != TechnicalState::Ready || executeConsumed ||
      technicalPhase != kVirgin) {
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
  if (!persistTechnicalPhase(kClaimed)) {
    rejectMutation(503, "persistent_claim_write_failed");
    return;
  }
  state = TechnicalState::Armed;
  refreshNvsEvidence();
  publishNoExecuteReport();
  server.send(201, "application/json",
              String("{\"accepted\":true,\"armed\":true,\"test_id\":\"") +
                  kTestId + "\",\"build_tag\":\"" + kBuildTag +
                  "\",\"action_id\":\"" + kActionId +
                  "\",\"device_api_version\":\"" + kDeviceApiVersion +
                  "\",\"identity_revision\":\"" + kIdentityRevision +
                  "\",\"classification\":\"" + kClassification +
                  "\",\"boot_nonce\":\"" + bootNonce() +
                  "\",\"arm_nonce\":\"" + armNonce() +
                  "\",\"persistent_phase\":1,\"migration_ready\":true," +
                  "\"formal_u07_unclaimed_and_virgin\":" +
                  (formalU07Match ? "true" : "false") + "," +
                  "\"safety_scope\":\"" + kSafetyScope +
                  "\",\"not_hardware_authorization\":true}");
}

void handleExecute() {
  ++executeRequestCount;
  refreshNvsEvidence();
  if (!migrationReady || !formalPrerequisitesMatch || !technicalKeyPresent ||
      technicalPhase != kClaimed) {
    rejectNvsMismatch(503, "execute_nvs_migration_mismatch");
    return;
  }
  if (state != TechnicalState::Armed || executeConsumed) {
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
  if (!persistTechnicalPhase(kConsumed)) {
    rejectMutation(503, "persistent_consumed_write_failed");
    return;
  }
  executeConsumed = true;
  jobQueuedAtMs = millis();
  state = TechnicalState::Queued;
  refreshNvsEvidence();
  executePending = true;
  server.send(202, "application/json",
              String("{\"accepted\":true,\"job_id\":1,\"test_id\":\"") +
                  kTestId + "\",\"build_tag\":\"" + kBuildTag +
                  "\",\"action_id\":\"" + kActionId +
                  "\",\"device_api_version\":\"" + kDeviceApiVersion +
                  "\",\"identity_revision\":\"" + kIdentityRevision +
                  "\",\"classification\":\"" + kClassification +
                  "\",\"boot_nonce\":\"" + bootNonce() +
                  "\",\"execute_consumed\":true,\"persistent_phase\":2," +
                  "\"migration_ready\":true," +
                  "\"formal_u07_unclaimed_and_virgin\":" +
                  (formalU07Match ? "true" : "false") + "," +
                  "\"no_retry\":true,\"no_recovery\":true}");
}

void installRoutes() {
  static const char *headers[] = {
      "Content-Type",   "Content-Length",  "Transfer-Encoding",
      kBuildHeader,     kTestHeader,        kActionHeader,
      kBootNonceHeader, kArmNonceHeader,    kIntentHeader,
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
    const uint32_t startedAt = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - startedAt < 15000UL) {
      delay(250);
    }
    if (WiFi.status() == WL_CONNECTED) {
      Serial.printf("EC5 U07T WiFi STA IP: %s\n",
                    WiFi.localIP().toString().c_str());
      return;
    }
  }
  WiFi.mode(WIFI_AP);
  WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASSWORD);
  Serial.printf("EC5 U07T WiFi AP IP: %s\n",
                WiFi.softAPIP().toString().c_str());
}

void executePendingTechnicalProbe() {
  if (!executePending) return;
  // Re-read both formal keys and the independent technical key immediately
  // before the sole driver call.
  if (!technicalPhaseIs(kConsumed) || !formalPrerequisitesMatch) {
    enterReadOnlyFault("runtime_nvs_readback_failed");
    return;
  }
  if (state != TechnicalState::Queued || driverCallCount != 0) {
    enterPersistentFault("runtime_queue_state_failed");
    return;
  }
  executePending = false;
  state = TechnicalState::Running;
  jobStartedAtMs = millis();
  ++driverCallCount;
  const bool result = epdDisplayCompiledUnknownProbe();
  jobFinishedAtMs = millis();
  const EpdOperationReport &driver = epdGetLastOperationReport();
  state = result ? TechnicalState::Completed : TechnicalState::FaultLocked;
  refreshNvsEvidence();
  publishedReport =
      String("{\"schema_version\":3,\"kind\":\"mf1750-ec5-u07t-report\",") +
      "\"valid\":true,\"test_id\":\"" + kTestId +
      "\",\"build_tag\":\"" + kBuildTag +
      "\",\"device_api_version\":\"" + kDeviceApiVersion +
      "\",\"identity_revision\":\"" + kIdentityRevision +
      "\",\"classification\":\"" + kClassification +
      "\",\"boot_nonce\":\"" + bootNonce() + "\",\"action_id\":\"" +
      kActionId + "\",\"candidate_code\":7,\"job_id\":1," +
      "\"terminal_state\":\"" + stateName(state) + "\",\"result\":" +
      (result ? "true" : "false") +
      ",\"driver_fixture_guard_passed\":" +
      (driverFixtureGuardPassed ? "true" : "false") +
      ",\"execute_consumed\":true,\"driver_called\":true," +
      "\"driver_call_count\":1,\"persistent_phase\":2," +
      "\"formal_u07_unclaimed_and_virgin\":" +
      (formalU07Match ? "true" : "false") + "," +
      "\"no_retry\":true,\"no_recovery\":true," +
      "\"job_queued_at_ms\":" + String(jobQueuedAtMs) +
      ",\"job_started_at_ms\":" + String(jobStartedAtMs) +
      ",\"job_finished_at_ms\":" + String(jobFinishedAtMs) +
      ",\"driver\":" + driverEvidenceJson(driver) + "," +
      nvsContractJson() + "," + nvsEvidenceJson() + "}";
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(50);
  Serial.println("\nMF1750 EC5 independent technical U07T probe booting");
  Serial.printf("Build: %s\n", kBuildTag);
  Serial.println("Classification: TECHNICAL_DESCRIPTIVE_NOT_QUALIFIED");
  Serial.println("No startup refresh/raw ingress/dither/retry/recovery/LUT edit");
  Serial.println("Formal corrected-v2 NVS is read-only; host verifies claims");
  Serial.println("Network interlock is NOT hardware authorization");

  bootNonceHigh = esp_random();
  bootNonceLow = esp_random();
  driverFixtureGuardPassed = epdValidateCompiledUnknownProbeFixture();
  fixtureSelfCheckPassed = driverFixtureGuardPassed;

  // Frozen boot order: exact no-I/O driver guard; formal namespace opened
  // read-only and both keys read; independent technical namespace opened;
  // then the complete prerequisite/virgin-state gate is evaluated.
  formalStoreReady =
      formalV2Store.begin(kFormalNamespace, true /* readOnly */);
  if (formalStoreReady) {
    formalU04KeyPresent = formalV2Store.isKey(kFormalU04Key);
    formalU04Phase = formalV2Store.getUChar(kFormalU04Key, kVirgin);
    formalU07KeyPresent = formalV2Store.isKey(kFormalU07Key);
    formalU07Phase = formalV2Store.getUChar(kFormalU07Key, kVirgin);
  }
  technicalStoreReady =
      technicalClaimStore.begin(kTechnicalNamespace, false /* readOnly */);
  refreshNvsEvidence();
  bootMigrationValidated = migrationReady;
  refreshNvsEvidence();

  if (!driverFixtureGuardPassed) {
    enterReadOnlyFault("compiled_fixture_self_check_failed");
  } else if (!formalStoreReady) {
    enterReadOnlyFault("formal_v2_read_only_store_open_failed");
  } else if (!technicalStoreReady) {
    enterReadOnlyFault("technical_claim_store_open_failed");
  } else if (!formalU04Match) {
    enterReadOnlyFault("formal_u04_not_consumed");
  } else if (!formalU07Match) {
    enterReadOnlyFault("formal_u07_not_virgin");
  } else if (!technicalVirgin) {
    enterReadOnlyFault("technical_u07t_not_virgin");
  } else {
    epdBegin();
    gpioInitialized = true;
    state = TechnicalState::Ready;
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
  executePendingTechnicalProbe();
  delay(2);
}
