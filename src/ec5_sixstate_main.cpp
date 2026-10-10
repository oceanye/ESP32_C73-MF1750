#include <Arduino.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <esp_system.h>

#include <cstdio>
#include <cstring>

#include "epd_config.h"
#include "epd_driver.h"

// Stage B is deliberately absent from release/main, N7, and the one-shot EC5
// pilot. Only the two dedicated PlatformIO environments select this source.
#if MF1750_ENABLE_SIXSTATE_PROBE != 1
#error "EC5 six-state firmware requires MF1750_ENABLE_SIXSTATE_PROBE=1"
#endif
#if MF1750_ENABLE_UNKNOWN_PROBE != 0
#error "EC5 six-state firmware cannot include the one-shot unknown probe"
#endif
#if EPD_ENABLE_TEST_PATTERN != 0
#error "EC5 six-state firmware must never refresh during boot"
#endif
#ifndef MF1750_UNKNOWN_PROBE_CODE
#error "EC5 six-state firmware requires one compile-time candidate"
#endif

#if MF1750_UNKNOWN_PROBE_CODE == 4
static constexpr uint8_t kCandidateCode = 4;
static constexpr const char *kCandidateHex = "0x4";
static constexpr const char *kCandidateTag = "U04";
static constexpr const char *kBuildTag =
    "MF1750_EC5_SIXSTATE_U04_MIRROR24_NODITHER_V1_2026-08-09";
static constexpr const char *kTestId = "EC5-SIXSTATE-U04-M24-NODITHER-V1";
static constexpr const char *kNvsNamespace = "mf1750_six_u04";
static constexpr const char *kTargetFrameSha256 =
    "81b0ed1b715551ddb2546d4f123c5c3d479bc8802ff9d2570e38d9b57b4645e6";
static constexpr const char *kTargetDtmSha256 =
    "c4efd83606b72c49b7c0d67865e4df98ef31e5d40f071299558e10c5a212dd0f";
static constexpr uint32_t kTargetFrameFnv1a = 0x263BD845UL;
static constexpr uint32_t kTargetDtmFnv1a = 0xEF6ED905UL;
static constexpr const char *kActionIds[9] = {
    "d7d54e2e9b9a5186648e1a9ffa80a9bbaf38d8b5fe8a4417d817249763269f7f",
    "96a7f25e518d73b95bba227019a55e7079c0f032b76be0ff0b1e28ffc8a08889",
    "96ad630b04e3694fb8faaec777fb52f8d9c10418ab5b1703613ea7726f18d797",
    "b6f11bf3fd5cc846a7cfae397901c0a0db427d01c84c7b935e2287c2e9b9b883",
    "f0e7a98abac0803125f6dd958376a94e5d8dd8f43206ba9dab55499e4249effa",
    "bc14534cf8ccb44a0253a0e21d18c0475c23b5365aa8e77947f32c41d5659bb4",
    "130d1d45b042da063d13da2152da9cf858e161c9f815b53a774ad96934adca07",
    "356a1008610064ea4ef2fe7b087a7f56aca4b7746a52d1ec1b79fc3a2c33dde7",
    "50325669e03b79d8b3ceedbdccbe5535404f23ec708c133d5a18479f2e536132",
};
#elif MF1750_UNKNOWN_PROBE_CODE == 7
static constexpr uint8_t kCandidateCode = 7;
static constexpr const char *kCandidateHex = "0x7";
static constexpr const char *kCandidateTag = "U07";
static constexpr const char *kBuildTag =
    "MF1750_EC5_SIXSTATE_U07_MIRROR24_NODITHER_V1_2026-08-09";
static constexpr const char *kTestId = "EC5-SIXSTATE-U07-M24-NODITHER-V1";
static constexpr const char *kNvsNamespace = "mf1750_six_u07";
static constexpr const char *kTargetFrameSha256 =
    "149ba0f5c3fd779d6870f655b53d726d6d1297e016331de4d394e411410e0e21";
static constexpr const char *kTargetDtmSha256 =
    "139a0aa919d78a1aa572db49a7c90fe3a4f29476ab4d80ba3bb0f439f0191b3d";
static constexpr uint32_t kTargetFrameFnv1a = 0xF93BD8C5UL;
static constexpr uint32_t kTargetDtmFnv1a = 0xE4D43B45UL;
static constexpr const char *kActionIds[9] = {
    "c037750456f9424f4458ce3fd1018ab960a36a0f1e27c40f67731adf9209ea52",
    "85a5ccf1ee7ffa627284d4d425d906f82692f620a94ec8c6bac5d9e577bad319",
    "0709bf9c163aa0e5824f6c961b01bd43190010b08781d72718fd5a57e3e5c3d7",
    "ec1a6b185f347d4c165517998bd43faea27a669f7d77b28b33cf0874c5b52a55",
    "4da75af12b7ab91d2d7c322e55b1f1d82ecf899e0b8f647647391c27d303a2a2",
    "b031d599ae4143ba9f876989e49701907f5f176df24a2104f8e0919bb25a7f09",
    "627ac0034982dd9f9de064290296c9ee63905cf69fcc3217b536457629df34cb",
    "0b11eac7e9a4a8d207d78fe5dcfc40c61ea76a2dfc4d45d5ca3467f9d983754b",
    "5b37c1c107b00acef854287eb52737f7859417cfb0aaf5e59ba216bdbb806bb1",
};
#else
#error "EC5 six-state candidate must be exactly 4 or 7"
#endif

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600 &&
                  EPD_FRAME_BYTES == 307200 && EPD_CONTROLLER_WIDTH == 512 &&
                  EPD_CONTROLLER_FRAME_BYTES == 153600,
              "EC5 six-state geometry differs from frozen assets");
static_assert(EPD_CS1_SOURCE_HALF == 0 && !EPD_CS1_FLIP_X &&
                  !EPD_CS1_FLIP_Y && !EPD_CS1_NIBBLE_SWAP &&
                  EPD_CS2_SOURCE_HALF == 1 && !EPD_CS2_FLIP_X &&
                  !EPD_CS2_FLIP_Y && !EPD_CS2_NIBBLE_SWAP,
              "EC5 six-state mapping differs from frozen assets");

namespace {

WebServer server(80);
Preferences progressStore;

static constexpr const char *kLayoutId = "EC5_SIXSTATE_MIRROR24_NODITHER_V1";
static constexpr const char *kVersionRoute = "/api/ec5/sixstate/version";
static constexpr const char *kManifestRoute = "/api/ec5/sixstate/manifest";
static constexpr const char *kStatusRoute = "/api/ec5/sixstate/status";
static constexpr const char *kReportRoute = "/api/ec5/sixstate/report";
static constexpr const char *kArmRoute = "/api/ec5/sixstate/arm";
static constexpr const char *kExecuteRoute = "/api/ec5/sixstate/execute";
static constexpr const char *kProgressKey = "progress";
static constexpr const char *kFaultLatchKey = "fault";

static constexpr const char *kBuildHeader = "X-EC5-Build-Tag";
static constexpr const char *kTestHeader = "X-EC5-Test-Id";
static constexpr const char *kActionHeader = "X-EC5-Action-Id";
static constexpr const char *kOrdinalHeader = "X-EC5-Ordinal";
static constexpr const char *kBootNonceHeader = "X-EC5-Boot-Nonce";
static constexpr const char *kArmNonceHeader = "X-EC5-Arm-Nonce";
static constexpr const char *kIntentHeader = "X-EC5-Intent";
static constexpr const char *kArmIntent =
    "ARM_ONE_FIXED_SIXSTATE_REFRESH_NOT_HARDWARE_AUTHORIZATION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ONE_FIXED_SIXSTATE_REFRESH_NOT_HARDWARE_AUTHORIZATION";
static constexpr const char *kSafetyScope =
    "device_accidental_post_interlock_not_hardware_authorization";

static constexpr const char *kPrimerFrameSha256 =
    "94ee82ae66fe8372e8c1d977a158dc60d55c36da86fc44f8b2a9a01c6d47ab0e";
static constexpr const char *kPrimerDtmSha256 =
    "f5bb17a5726f851da2bf322ffea8f0ea791f70788184ada4261b89aa43dc39af";
static constexpr uint32_t kPrimerFrameFnv1a = 0xE4F04785UL;
static constexpr uint32_t kPrimerDtmFnv1a = 0x58214425UL;
static constexpr const char *kWhiteFrameSha256 =
    "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d";
static constexpr const char *kWhiteDtmSha256 =
    "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158";
static constexpr uint32_t kWhiteFrameFnv1a = 0x13340DC5UL;
static constexpr uint32_t kWhiteDtmFnv1a = 0xB7A855C5UL;

static constexpr uint8_t kProgressMagic = 0xB6;
static constexpr uint8_t kFirstOrdinal = 1;
static constexpr uint8_t kCompletedOrdinal = 10;
static constexpr uint32_t kCooldownMs = 150000UL;

enum class PendingPhase : uint8_t {
  Virgin = 0,
  Claimed = 1,
  Consumed = 2,
  Fault = 3,
};

enum class DeviceState : uint8_t {
  BootSelfCheck,
  Ready,
  Cooldown,
  Armed,
  Queued,
  Running,
  CampaignComplete,
  FaultLocked,
};

struct RoleIdentity {
  const char *frameSha256;
  const char *dtmSha256;
  uint32_t frameFnv1a;
  uint32_t dtmFnv1a;
};

DeviceState deviceState = DeviceState::BootSelfCheck;
PendingPhase pendingPhase = PendingPhase::Fault;
bool storeReady = false;
bool fixtureSelfCheckPassed = false;
bool gpioInitialized = false;
volatile bool executePending = false;
bool currentActionDriverCalled = false;
uint8_t nextOrdinal = 0;
uint8_t queuedOrdinal = 0;
uint32_t cooldownDeadlineMs = 0;
uint32_t bootNonceHigh = 0;
uint32_t bootNonceLow = 0;
uint32_t armNonceHigh = 0;
uint32_t armNonceLow = 0;
uint32_t totalDriverCallsThisBoot = 0;
uint32_t jobQueuedAtMs = 0;
uint32_t jobStartedAtMs = 0;
uint32_t jobFinishedAtMs = 0;
String publishedReport =
    "{\"schema_version\":1,\"valid\":false,\"error\":\"no_execute_report\"}";

const char *stateName(DeviceState state) {
  switch (state) {
    case DeviceState::BootSelfCheck: return "boot_self_check";
    case DeviceState::Ready: return "ready";
    case DeviceState::Cooldown: return "cooldown";
    case DeviceState::Armed: return "armed";
    case DeviceState::Queued: return "queued";
    case DeviceState::Running: return "running";
    case DeviceState::CampaignComplete: return "campaign_complete";
    case DeviceState::FaultLocked: return "fault_locked";
  }
  return "fault_locked";
}

const char *phaseName(PendingPhase phase) {
  switch (phase) {
    case PendingPhase::Virgin: return "virgin";
    case PendingPhase::Claimed: return "claimed";
    case PendingPhase::Consumed: return "consumed";
    case PendingPhase::Fault: return "fault";
  }
  return "fault";
}

uint8_t roundForOrdinal(uint8_t ordinal) {
  return ordinal >= 1 && ordinal <= 9 ? static_cast<uint8_t>((ordinal - 1) / 3 + 1) : 0;
}

EpdSixStateRole roleForOrdinal(uint8_t ordinal) {
  switch ((ordinal - 1) % 3) {
    case 0: return EpdSixStateRole::Primer;
    case 1: return EpdSixStateRole::Target;
    default: return EpdSixStateRole::White;
  }
}

const char *roleName(EpdSixStateRole role) {
  switch (role) {
    case EpdSixStateRole::Primer: return "primer";
    case EpdSixStateRole::Target: return "target";
    case EpdSixStateRole::White: return "white";
  }
  return "invalid";
}

RoleIdentity identityForRole(EpdSixStateRole role) {
  switch (role) {
    case EpdSixStateRole::Primer:
      return {kPrimerFrameSha256, kPrimerDtmSha256,
              kPrimerFrameFnv1a, kPrimerDtmFnv1a};
    case EpdSixStateRole::Target:
      return {kTargetFrameSha256, kTargetDtmSha256,
              kTargetFrameFnv1a, kTargetDtmFnv1a};
    case EpdSixStateRole::White:
      return {kWhiteFrameSha256, kWhiteDtmSha256,
              kWhiteFrameFnv1a, kWhiteDtmFnv1a};
  }
  return {"", "", 0, 0};
}

String hex32(uint32_t value) {
  char output[9] = {};
  std::snprintf(output, sizeof(output), "%08lx", static_cast<unsigned long>(value));
  return String(output);
}

String bootNonce() { return hex32(bootNonceHigh) + hex32(bootNonceLow); }
String armNonce() { return hex32(armNonceHigh) + hex32(armNonceLow); }

String ordinalString(uint8_t ordinal) {
  char output[4] = {};
  std::snprintf(output, sizeof(output), "%u", static_cast<unsigned>(ordinal));
  return String(output);
}

const char *actionIdForOrdinal(uint8_t ordinal) {
  return ordinal >= 1 && ordinal <= 9 ? kActionIds[ordinal - 1] : "";
}

uint32_t progressWord(uint8_t ordinal, PendingPhase phase) {
  return (static_cast<uint32_t>(kProgressMagic) << 24) |
         (static_cast<uint32_t>(kCandidateCode) << 16) |
         (static_cast<uint32_t>(ordinal) << 8) |
         static_cast<uint8_t>(phase);
}

bool decodeProgress(uint32_t word, uint8_t *ordinal, PendingPhase *phase) {
  const uint8_t magic = word >> 24;
  const uint8_t candidate = (word >> 16) & 0xFF;
  const uint8_t decodedOrdinal = (word >> 8) & 0xFF;
  const uint8_t decodedPhase = word & 0xFF;
  if (magic != kProgressMagic || candidate != kCandidateCode ||
      decodedOrdinal < kFirstOrdinal || decodedOrdinal > kCompletedOrdinal ||
      decodedPhase > static_cast<uint8_t>(PendingPhase::Fault)) {
    return false;
  }
  *ordinal = decodedOrdinal;
  *phase = static_cast<PendingPhase>(decodedPhase);
  return true;
}

bool persistProgress(uint8_t ordinal, PendingPhase phase) {
  if (!storeReady) return false;
  const uint32_t expected = progressWord(ordinal, phase);
  if (progressStore.putUInt(kProgressKey, expected) != sizeof(uint32_t)) return false;
  const uint32_t actual = progressStore.getUInt(kProgressKey, 0xFFFFFFFFUL);
  if (actual != expected) return false;
  nextOrdinal = ordinal;
  pendingPhase = phase;
  return true;
}

bool progressStillIs(uint8_t ordinal, PendingPhase phase) {
  if (!storeReady) return false;
  return progressStore.getUInt(kProgressKey, 0xFFFFFFFFUL) ==
         progressWord(ordinal, phase);
}

bool cooldownElapsed() {
  return cooldownDeadlineMs == 0 ||
         static_cast<int32_t>(millis() - cooldownDeadlineMs) >= 0;
}

uint32_t cooldownRemainingMs() {
  if (cooldownElapsed()) return 0;
  return cooldownDeadlineMs - millis();
}

bool requestHasBodyOrArguments() {
  if (server.args() != 0 || server.hasArg("plain")) return true;
  const String contentType = server.header("Content-Type");
  const String transferEncoding = server.header("Transfer-Encoding");
  const String contentLength = server.header("Content-Length");
  if (!contentType.isEmpty() || !transferEncoding.isEmpty()) return true;
  return !contentLength.isEmpty() && contentLength != "0";
}

bool exactHeader(const char *name, const String &expected) {
  return server.hasHeader(name) && server.header(name) == expected;
}

const char *validateMutationContract(const char *intent, bool requireArmNonce) {
  if (requestHasBodyOrArguments()) return "body_or_arguments_forbidden";
  if (!exactHeader(kBuildHeader, String(kBuildTag))) return "build_tag_mismatch";
  if (!exactHeader(kTestHeader, String(kTestId))) return "test_id_mismatch";
  if (!exactHeader(kActionHeader, String(actionIdForOrdinal(nextOrdinal))))
    return "action_id_mismatch";
  if (!exactHeader(kOrdinalHeader, ordinalString(nextOrdinal)))
    return "ordinal_mismatch";
  if (!exactHeader(kBootNonceHeader, bootNonce())) return "boot_nonce_mismatch";
  if (!exactHeader(kIntentHeader, String(intent))) return "intent_mismatch";
  if (requireArmNonce && !exactHeader(kArmNonceHeader, armNonce()))
    return "arm_nonce_missing_or_stale";
  return nullptr;
}

String busyStageJson(const EpdBusyStageEvidence &stage) {
  return String("{\"gate_entry_level\":") + String(stage.gateEntryLevel) +
         ",\"pre_command_level\":" + String(stage.preCommandLevel) +
         ",\"wait_entry_level\":" + String(stage.waitEntryLevel) +
         ",\"wait_exit_level\":" + String(stage.waitExitLevel) +
         ",\"pre_command_idle_ok\":" +
         (stage.preCommandIdleOk ? "true" : "false") +
         ",\"assertion_after_idle\":" +
         (stage.assertionAfterIdle ? "true" : "false") +
         ",\"pre_command_wait_ms\":" + String(stage.preCommandWaitMs) +
         ",\"wait_ms\":" + String(stage.waitMs) +
         ",\"assertion_latency_ms\":" + String(stage.assertionLatencyMs) + "}";
}

String driverJson(const EpdOperationReport &report) {
  return String("{\"operation_id\":") + String(report.operationId) +
         ",\"valid\":" + (report.valid ? "true" : "false") +
         ",\"running\":" + (report.running ? "true" : "false") +
         ",\"sequence_ok\":" + (report.sequenceOk ? "true" : "false") +
         ",\"wait_timed_out\":" + (report.waitTimedOut ? "true" : "false") +
         ",\"busy_assertion_missing\":" +
         (report.busyAssertionMissing ? "true" : "false") +
         ",\"pre_command_idle_failure\":" +
         (report.preCommandIdleFailure ? "true" : "false") +
         ",\"mapping_applied\":" + (report.mappingApplied ? "true" : "false") +
         ",\"input_frame_fnv1a\":\"0x" + hex32(report.inputFrameFnv1a) +
         "\",\"cs1_dtm_fnv1a\":\"0x" + hex32(report.cs1DtmFnv1a) +
         "\",\"cs2_dtm_fnv1a\":\"0x" + hex32(report.cs2DtmFnv1a) +
         "\",\"spi_hz\":" + String(report.spiHz) +
         ",\"total_ms\":" + String(report.totalMs) +
         ",\"upload_ms\":{\"cs1\":" + String(report.cs1UploadMs) +
         ",\"cs2\":" + String(report.cs2UploadMs) + "}" +
         ",\"busy_seen\":{\"pon\":" + (report.ponBusySeen ? "true" : "false") +
         ",\"drf\":" + (report.drfBusySeen ? "true" : "false") +
         ",\"pof\":" + (report.pofBusySeen ? "true" : "false") +
         ",\"post_psr\":" + (report.postPsrBusySeen ? "true" : "false") + "}" +
         ",\"busy_stages\":{\"reset\":" + busyStageJson(report.resetBusy) +
         ",\"pon\":" + busyStageJson(report.ponBusy) +
         ",\"drf\":" + busyStageJson(report.drfBusy) +
         ",\"pof\":" + busyStageJson(report.pofBusy) +
         ",\"post_psr\":" + busyStageJson(report.postPsrBusy) + "}" +
         ",\"wait_ms\":{\"pon\":" + String(report.ponWaitMs) +
         ",\"drf\":" + String(report.drfWaitMs) +
         ",\"pof\":" + String(report.pofWaitMs) +
         ",\"post_psr\":" + String(report.postPsrWaitMs) + "}" +
         ",\"last_wait_stage\":\"" + String(report.lastWaitStage) +
         "\",\"timeout_stage\":\"" + String(report.timeoutStage) +
         "\",\"busy_missing_stage\":\"" + String(report.busyMissingStage) +
         "\",\"pre_command_busy_stage\":\"" + String(report.preCommandBusyStage) +
         "\",\"safe_finish\":{\"busy_before_pins_low\":" +
         String(report.safeFinishBusyBeforePinsLow) +
         ",\"busy_after_pins_low\":" + String(report.safeFinishBusyAfterPinsLow) +
         ",\"busy_after_5ms\":" + String(report.safeFinishBusyAfter5Ms) +
         ",\"final_gpio\":{\"busy\":" + String(report.finalBusyLevel) +
         ",\"rst\":" + String(report.finalRstLevel) +
         ",\"cs1\":" + String(report.finalCs1Level) +
         ",\"cs2\":" + String(report.finalCs2Level) + "}}}";
}

void publishFault(const char *error) {
  publishedReport =
      String("{\"schema_version\":1,\"kind\":\"mf1750-ec5-sixstate-report\",") +
      "\"valid\":false,\"terminal_state\":\"FAULT_LOCKED\",\"error\":\"" +
      error + "\",\"build_tag\":\"" + kBuildTag +
      "\",\"test_id\":\"" + kTestId +
      "\",\"candidate_code\":" + String(kCandidateCode) +
      ",\"next_ordinal\":" + String(nextOrdinal) +
      ",\"pending_phase\":\"" + phaseName(pendingPhase) +
      "\",\"no_retry\":true,\"no_recovery\":true}";
}

void enterFault(const char *error) {
  executePending = false;
  deviceState = DeviceState::FaultLocked;
  if (storeReady) {
    // A second monotonic key makes malformed-request faults sticky even if the
    // structured progress update itself fails. There is intentionally no
    // firmware or network path that writes this latch back to false.
    progressStore.putBool(kFaultLatchKey, true);
    if (nextOrdinal >= 1 && nextOrdinal <= 10) {
      persistProgress(nextOrdinal, PendingPhase::Fault);
    }
  }
  pendingPhase = PendingPhase::Fault;
  publishFault(error);
}

void rejectMutation(int status, const char *error) {
  enterFault(error);
  server.send(status, "application/json",
              String("{\"accepted\":false,\"fault_locked\":true,\"error\":\"") +
                  error + "\",\"no_retry\":true,\"no_recovery\":true}");
}

String sequenceJson() {
  String output = "[";
  for (uint8_t ordinal = 1; ordinal <= 9; ++ordinal) {
    if (ordinal > 1) output += ',';
    const EpdSixStateRole role = roleForOrdinal(ordinal);
    const RoleIdentity identity = identityForRole(role);
    output += String("{\"ordinal\":") + String(ordinal) +
              ",\"round\":" + String(roundForOrdinal(ordinal)) +
              ",\"role\":\"" + roleName(role) +
              "\",\"action_id\":\"" + actionIdForOrdinal(ordinal) +
              "\",\"frame_sha256\":\"" + identity.frameSha256 +
              "\",\"frame_fnv1a\":\"0x" + hex32(identity.frameFnv1a) +
              "\",\"cs1_dtm_sha256\":\"" + identity.dtmSha256 +
              "\",\"cs2_dtm_sha256\":\"" + identity.dtmSha256 +
              "\",\"cs1_dtm_fnv1a\":\"0x" + hex32(identity.dtmFnv1a) +
              "\",\"cs2_dtm_fnv1a\":\"0x" + hex32(identity.dtmFnv1a) + "\"}";
  }
  output += ']';
  return output;
}

String versionJson() {
  return String("{\"schema_version\":1,\"kind\":\"mf1750-ec5-sixstate-version\",") +
         "\"build_tag\":\"" + kBuildTag + "\",\"test_id\":\"" + kTestId +
         "\",\"candidate_id\":\"" + kCandidateTag +
         "\",\"candidate_code\":\"" + kCandidateHex +
         "\",\"driver_api_version\":\"" + EPD_DRIVER_API_VERSION +
         "\",\"layout_id\":\"" + kLayoutId +
         "\",\"startup_refresh\":false,\"raw_frame_ingress\":false," +
         "\"lut_modification\":false,\"automatic_execute\":false," +
         "\"fixed_action_count\":9,\"cooldown_ms\":150000," +
         "\"persistent_progress\":true,\"retry\":false,\"recovery\":false," +
         "\"not_hardware_authorization\":true}";
}

String manifestJson() {
  return String("{\"schema_version\":1,\"kind\":\"mf1750-ec5-sixstate-manifest\",") +
         "\"build_tag\":\"" + kBuildTag + "\",\"test_id\":\"" + kTestId +
         "\",\"candidate_id\":\"" + kCandidateTag +
         "\",\"candidate_code\":" + String(kCandidateCode) +
         ",\"layout_id\":\"" + kLayoutId +
         "\",\"geometry\":{\"width\":1024,\"height\":600," +
         "\"frame_bytes\":307200,\"packing\":\"row_major_4bpp_even_x_high_nibble\"," +
         "\"roi_count\":12,\"roi_width\":24,\"roi_height\":24," +
         "\"candidate_pixels\":6912,\"background_code\":1}," +
         "\"initial_codes\":[1,0,3,2,5,6],\"y0\":[48,144,240,336,432,528]," +
         "\"roi_x0\":{\"cs1\":244,\"cs2\":756}," +
         "\"mapping_cs1\":[0,0,0,0],\"mapping_cs2\":[1,0,0,0]," +
         "\"sequence\":" + sequenceJson() +
         ",\"safety\":{\"dithering\":false,\"spatial_mixing\":false," +
         "\"uniform_single_code_rois\":true,\"bodyless_mutations\":true," +
         "\"exact_build_test_action_ordinal_boot_arm_nonce\":true," +
         "\"claim_before_driver\":true,\"max_driver_calls_per_action\":1," +
         "\"cooldown_from_previous_completion_ms\":150000," +
         "\"reboot_cooldown_is_conservatively_restarted\":true," +
         "\"network_reset_clear_retry_recovery_routes\":false," +
         "\"not_hardware_authorization\":true}}";
}

String gpioJson() {
  if (!gpioInitialized) return "{\"initialized\":false}";
  return String("{\"initialized\":true,\"busy\":") + String(epdReadBusy()) +
         ",\"rst\":" + String(digitalRead(EPD_PIN_RST)) +
         ",\"cs1\":" + String(digitalRead(EPD_PIN_CS)) +
         ",\"cs2\":" + String(digitalRead(EPD_PIN_CS2)) + "}";
}

String statusJson() {
  const bool hasAction = nextOrdinal >= 1 && nextOrdinal <= 9;
  const EpdSixStateRole role = hasAction ? roleForOrdinal(nextOrdinal)
                                         : EpdSixStateRole::White;
  return String("{\"schema_version\":1,\"kind\":\"mf1750-ec5-sixstate-status\",") +
         "\"build_tag\":\"" + kBuildTag + "\",\"test_id\":\"" + kTestId +
         "\",\"boot_nonce\":\"" + bootNonce() +
         "\",\"candidate_code\":" + String(kCandidateCode) +
         ",\"state\":\"" + stateName(deviceState) +
         "\",\"next_ordinal\":" + String(nextOrdinal) +
         ",\"next_round\":" + String(hasAction ? roundForOrdinal(nextOrdinal) : 0) +
         ",\"next_role\":" + (hasAction ? String("\"") + roleName(role) + "\"" : "null") +
         ",\"next_action_id\":" +
         (hasAction ? String("\"") + actionIdForOrdinal(nextOrdinal) + "\"" : "null") +
         ",\"pending_phase\":\"" + phaseName(pendingPhase) +
         "\",\"fixture_self_check_passed\":" +
         (fixtureSelfCheckPassed ? "true" : "false") +
         ",\"execute_pending\":" + (executePending ? "true" : "false") +
         ",\"current_action_driver_called\":" +
         (currentActionDriverCalled ? "true" : "false") +
         ",\"total_driver_calls_this_boot\":" + String(totalDriverCallsThisBoot) +
         ",\"cooldown_ms\":150000,\"cooldown_remaining_ms\":" +
         String(cooldownRemainingMs()) + ",\"gpio\":" + gpioJson() +
         ",\"no_retry\":true,\"no_recovery\":true}";
}

void publishNoExecuteReport() {
  const bool hasAction = nextOrdinal >= 1 && nextOrdinal <= 9;
  publishedReport =
      String("{\"schema_version\":1,\"kind\":\"mf1750-ec5-sixstate-report\",") +
      "\"valid\":false,\"terminal_state\":\"NOT_EXECUTED\"," +
      "\"error\":\"no_execute_report\",\"build_tag\":\"" + kBuildTag +
      "\",\"test_id\":\"" + kTestId + "\",\"boot_nonce\":\"" +
      bootNonce() + "\",\"candidate_code\":" + String(kCandidateCode) +
      ",\"next_ordinal\":" + String(nextOrdinal) +
      ",\"next_action_id\":" +
      (hasAction ? String("\"") + actionIdForOrdinal(nextOrdinal) + "\"" :
                   "null") +
      ",\"pending_phase\":\"" + phaseName(pendingPhase) +
      "\",\"driver_called\":false,\"no_retry\":true,\"no_recovery\":true}";
}

bool requireReadOnly() {
  if (!requestHasBodyOrArguments()) return true;
  server.send(400, "application/json",
              "{\"error\":\"read_only_route_rejects_body_or_arguments\"}");
  return false;
}

void handleArm() {
  if (deviceState != DeviceState::Ready || pendingPhase != PendingPhase::Virgin ||
      nextOrdinal < 1 || nextOrdinal > 9 || !cooldownElapsed()) {
    rejectMutation(409, "arm_not_ready_or_cooldown_active");
    return;
  }
  const char *contractError = validateMutationContract(kArmIntent, false);
  if (contractError) {
    rejectMutation(400, contractError);
    return;
  }
  if (!fixtureSelfCheckPassed || !gpioInitialized || !storeReady) {
    rejectMutation(503, "arm_preflight_failed");
    return;
  }
  armNonceHigh = esp_random();
  armNonceLow = esp_random();
  if ((armNonceHigh | armNonceLow) == 0) armNonceLow = 1;
  if (!persistProgress(nextOrdinal, PendingPhase::Claimed)) {
    rejectMutation(503, "persistent_claim_write_failed");
    return;
  }
  currentActionDriverCalled = false;
  deviceState = DeviceState::Armed;
  server.send(201, "application/json",
              String("{\"accepted\":true,\"armed\":true,\"build_tag\":\"") +
                  kBuildTag + "\",\"test_id\":\"" + kTestId +
                  "\",\"ordinal\":" + String(nextOrdinal) +
                  ",\"round\":" + String(roundForOrdinal(nextOrdinal)) +
                  ",\"role\":\"" + roleName(roleForOrdinal(nextOrdinal)) +
                  "\",\"action_id\":\"" + actionIdForOrdinal(nextOrdinal) +
                  "\",\"boot_nonce\":\"" + bootNonce() +
                  "\",\"arm_nonce\":\"" + armNonce() +
                  "\",\"persistent_phase\":\"claimed\"," +
                  "\"not_hardware_authorization\":true}");
}

void handleExecute() {
  if (deviceState != DeviceState::Armed || pendingPhase != PendingPhase::Claimed ||
      nextOrdinal < 1 || nextOrdinal > 9 || currentActionDriverCalled) {
    rejectMutation(409, "execute_duplicate_stale_or_not_armed");
    return;
  }
  const char *contractError = validateMutationContract(kExecuteIntent, true);
  if (contractError) {
    rejectMutation(400, contractError);
    return;
  }
  if (!fixtureSelfCheckPassed || !gpioInitialized || !storeReady) {
    rejectMutation(503, "execute_preflight_failed");
    return;
  }
  queuedOrdinal = nextOrdinal;
  if (!persistProgress(queuedOrdinal, PendingPhase::Consumed)) {
    rejectMutation(503, "persistent_consumed_write_failed");
    return;
  }
  jobQueuedAtMs = millis();
  executePending = true;
  deviceState = DeviceState::Queued;
  server.send(202, "application/json",
              String("{\"accepted\":true,\"queued\":true,\"build_tag\":\"") +
                  kBuildTag + "\",\"test_id\":\"" + kTestId +
                  "\",\"boot_nonce\":\"" + bootNonce() +
                  "\",\"candidate_code\":" + String(kCandidateCode) +
                  ",\"ordinal\":" + String(queuedOrdinal) + ",\"round\":" +
                  String(roundForOrdinal(queuedOrdinal)) + ",\"role\":\"" +
                  roleName(roleForOrdinal(queuedOrdinal)) +
                  "\",\"action_id\":\"" + actionIdForOrdinal(queuedOrdinal) +
                  "\",\"execute_consumed\":true,\"no_retry\":true," +
                  "\"no_recovery\":true}");
}

void installRoutes() {
  static const char *headers[] = {
      "Content-Type", "Content-Length", "Transfer-Encoding", kBuildHeader,
      kTestHeader, kActionHeader, kOrdinalHeader, kBootNonceHeader,
      kArmNonceHeader, kIntentHeader,
  };
  server.collectHeaders(headers, sizeof(headers) / sizeof(headers[0]));
  server.on(kVersionRoute, HTTP_GET, []() {
    if (requireReadOnly()) server.send(200, "application/json", versionJson());
  });
  server.on(kManifestRoute, HTTP_GET, []() {
    if (requireReadOnly()) server.send(200, "application/json", manifestJson());
  });
  server.on(kStatusRoute, HTTP_GET, []() {
    if (requireReadOnly()) server.send(200, "application/json", statusJson());
  });
  server.on(kReportRoute, HTTP_GET, []() {
    if (requireReadOnly()) server.send(200, "application/json", publishedReport);
  });
  server.on(kArmRoute, HTTP_POST, handleArm);
  server.on(kExecuteRoute, HTTP_POST, handleExecute);
  server.onNotFound([]() {
    if (server.method() == HTTP_POST) {
      rejectMutation(404, "unknown_mutation_route");
    } else {
      server.send(404, "application/json", "{\"error\":\"not_found\"}");
    }
  });
}

void startWiFi() {
  if (std::strlen(WIFI_STA_SSID) > 0) {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_STA_SSID, WIFI_STA_PASSWORD);
    const uint32_t startedAt = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - startedAt < 15000UL) {
      delay(250);
    }
    if (WiFi.status() == WL_CONNECTED) {
      Serial.printf("EC5 six-state WiFi STA IP: %s\n",
                    WiFi.localIP().toString().c_str());
      return;
    }
  }
  WiFi.mode(WIFI_AP);
  WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASSWORD);
  Serial.printf("EC5 six-state WiFi AP IP: %s\n",
                WiFi.softAPIP().toString().c_str());
}

void executeQueuedAction() {
  if (!executePending) return;
  const uint8_t ordinal = queuedOrdinal;
  if (deviceState != DeviceState::Queued || ordinal != nextOrdinal ||
      ordinal < 1 || ordinal > 9 || currentActionDriverCalled ||
      !progressStillIs(ordinal, PendingPhase::Consumed)) {
    enterFault("runtime_consumed_claim_readback_failed");
    return;
  }
  executePending = false;
  deviceState = DeviceState::Running;
  currentActionDriverCalled = true;
  ++totalDriverCallsThisBoot;
  const EpdSixStateRole role = roleForOrdinal(ordinal);
  const char *actionId = actionIdForOrdinal(ordinal);
  const RoleIdentity identity = identityForRole(role);
  jobStartedAtMs = millis();
  const bool driverResult = epdDisplayCompiledSixState(role);
  jobFinishedAtMs = millis();
  const EpdOperationReport &driver = epdGetLastOperationReport();

  bool progressCommitted = false;
  if (driverResult) {
    progressCommitted = persistProgress(static_cast<uint8_t>(ordinal + 1),
                                        PendingPhase::Virgin);
  }
  if (!driverResult || !progressCommitted) {
    enterFault(driverResult ? "next_ordinal_commit_failed" : "driver_failed");
  } else if (nextOrdinal == kCompletedOrdinal) {
    deviceState = DeviceState::CampaignComplete;
    cooldownDeadlineMs = 0;
  } else {
    cooldownDeadlineMs = jobFinishedAtMs + kCooldownMs;
    deviceState = DeviceState::Cooldown;
  }

  publishedReport =
      String("{\"schema_version\":1,\"kind\":\"mf1750-ec5-sixstate-report\",") +
      "\"valid\":true,\"build_tag\":\"" + kBuildTag +
      "\",\"test_id\":\"" + kTestId +
      "\",\"boot_nonce\":\"" + bootNonce() +
      "\",\"candidate_code\":" + String(kCandidateCode) +
      ",\"ordinal\":" + String(ordinal) +
      ",\"round\":" + String(roundForOrdinal(ordinal)) +
      ",\"role\":\"" + roleName(role) +
      "\",\"action_id\":\"" + actionId +
      "\",\"terminal_state\":\"" +
      (driverResult && progressCommitted ? "COMPLETED" : "FAULT_LOCKED") +
      "\",\"result\":" +
      (driverResult && progressCommitted ? "true" : "false") +
      ",\"driver_called\":true,\"driver_call_count_for_action\":1," +
      "\"expected_identity\":{\"frame_sha256\":\"" + identity.frameSha256 +
      "\",\"frame_fnv1a\":\"0x" + hex32(identity.frameFnv1a) +
      "\",\"cs1_dtm_sha256\":\"" + identity.dtmSha256 +
      "\",\"cs2_dtm_sha256\":\"" + identity.dtmSha256 +
      "\",\"cs1_dtm_fnv1a\":\"0x" + hex32(identity.dtmFnv1a) +
      "\",\"cs2_dtm_fnv1a\":\"0x" + hex32(identity.dtmFnv1a) +
      "\"},\"next_ordinal\":" + String(nextOrdinal) +
      ",\"pending_phase\":\"" + phaseName(pendingPhase) +
      "\",\"cooldown_ms\":" +
      String(driverResult && progressCommitted && nextOrdinal <= 9 ? kCooldownMs : 0) +
      ",\"job_queued_at_ms\":" + String(jobQueuedAtMs) +
      ",\"job_started_at_ms\":" + String(jobStartedAtMs) +
      ",\"job_finished_at_ms\":" + String(jobFinishedAtMs) +
      ",\"no_retry\":true,\"no_recovery\":true,\"driver\":" +
      driverJson(driver) + "}";
}

void updateCooldownState() {
  if (deviceState == DeviceState::Cooldown && pendingPhase == PendingPhase::Virgin &&
      nextOrdinal >= 1 && nextOrdinal <= 9 && cooldownElapsed()) {
    cooldownDeadlineMs = 0;
    currentActionDriverCalled = false;
    armNonceHigh = 0;
    armNonceLow = 0;
    deviceState = DeviceState::Ready;
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(50);
  Serial.println("\nMF1750 EC5 six-state no-dither Stage B booting");
  Serial.printf("Build: %s\n", kBuildTag);
  Serial.printf("Candidate: %s; fixed actions: 9; cooldown: 150 s\n", kCandidateHex);
  Serial.println("No startup refresh, raw ingress, LUT change, retry, or recovery");
  Serial.println("Device interlock is NOT hardware authorization");

  bootNonceHigh = esp_random();
  bootNonceLow = esp_random();
  fixtureSelfCheckPassed = epdValidateCompiledSixStateFixtures();
  epdBegin();
  gpioInitialized = true;

  storeReady = progressStore.begin(kNvsNamespace, false);
  if (!fixtureSelfCheckPassed || !storeReady) {
    enterFault(!fixtureSelfCheckPassed ? "compiled_fixture_self_check_failed"
                                      : "persistent_progress_store_open_failed");
  } else {
    uint32_t stored = progressStore.getUInt(kProgressKey, 0xFFFFFFFFUL);
    if (stored == 0xFFFFFFFFUL) {
      if (!persistProgress(kFirstOrdinal, PendingPhase::Virgin)) {
        enterFault("initial_progress_write_failed");
      }
    } else if (!decodeProgress(stored, &nextOrdinal, &pendingPhase)) {
      nextOrdinal = kFirstOrdinal;
      enterFault("persistent_progress_invalid");
    }

    if (deviceState != DeviceState::FaultLocked) {
      if (progressStore.getBool(kFaultLatchKey, false)) {
        enterFault("persistent_fault_latch_seen_at_boot");
      } else if (pendingPhase != PendingPhase::Virgin) {
        enterFault("pending_claim_seen_at_boot");
      } else if (nextOrdinal == kCompletedOrdinal) {
        deviceState = DeviceState::CampaignComplete;
      } else {
        // No trusted wall clock is available. On every reboot after action 1,
        // restart a full cooldown, which can only lengthen the required gap.
        if (nextOrdinal > kFirstOrdinal) {
          cooldownDeadlineMs = millis() + kCooldownMs;
          deviceState = DeviceState::Cooldown;
        } else {
          deviceState = DeviceState::Ready;
        }
      }
    }
  }

  if (deviceState != DeviceState::FaultLocked) {
    publishNoExecuteReport();
  }

  startWiFi();
  installRoutes();
  server.begin();
  Serial.printf("Read-only manifest: %s\n", kManifestRoute);
  Serial.printf("Bodyless arm: POST %s\n", kArmRoute);
  Serial.printf("Bodyless execute: POST %s\n", kExecuteRoute);
}

void loop() {
  server.handleClient();
  executeQueuedAction();
  updateCooldownState();
  delay(2);
}
