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

// One immutable empirical H3 atlas action. This firmware does not contain a
// recovery action: recovery requires reflashing the separately identified
// factory-OTP-only build and a second authorization. Startup never refreshes.
#if MF1750_ENABLE_RUNTIME_LUT_EMPIRICAL_H3 != 1
#error "Empirical H3 main requires its isolated driver fixture"
#endif

#ifndef EPD_ENABLE_TEST_PATTERN
#error "Empirical H3 main requires explicit EPD_ENABLE_TEST_PATTERN=0"
#endif

#if EPD_ENABLE_TEST_PATTERN != 0
#error "Empirical H3 main must never refresh during startup"
#endif

#if (MF1750_RUNTIME_LUT_PROFILE_WF20_25 + \
     MF1750_RUNTIME_LUT_PROFILE_WF23_25) != 1
#error "Empirical H3 main requires exactly one explicit profile"
#endif

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600,
              "empirical H3 main is frozen for the 1024x600 panel");
static_assert(EPD_FRAME_BYTES == 307200 &&
                  EPD_CONTROLLER_FRAME_BYTES == 153600,
              "empirical H3 main requires frozen cascade geometry");

namespace {

WebServer server(80);
Preferences cursorStore;

static constexpr const char *kClassification =
    "EMPIRICAL_H3_REAL_PANEL_CAMPAIGN_NOT_LIVE_AUTHORIZATION";
static constexpr const char *kIdentityRevision =
    "runtime-lut-empirical-h3-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_EMPIRICAL_H3_DEVICE_V1";
static constexpr const char *kLayoutId =
    "EC5_EIGHTCODE_DUAL_BALANCED_64_V1";
static constexpr const char *kTestId = "EC5-RUNTIME-LUT-EMPIRICAL-H3-V1";
#if MF1750_RUNTIME_LUT_PROFILE_WF20_25 == 1
static constexpr const char *kBuildTag =
    "MF1750_EC5_RUNTIME_LUT_H3_WF20_25_V1_2026-08-11";
static constexpr const char *kExpectedProfileId = "WF20_25";
static constexpr const char *kEnvironmentId = "ec5_runtime_lut_wf20_25";
static constexpr const char *kCampaignId = "EC5_EMPIRICAL_H3_WF20_25_V1";
static constexpr const char *kContractId =
    "83053b14a8033b135a824e1e83a157134feedabfb5518977424a894db5854f51";
static constexpr const char *kNvsNamespace = "rlt_w20_v1";
static constexpr const char *kDescriptorId =
    "055c9832f81992094e5c156471c62cf99f36d07bf3c1702568be91f21eb860eb";
static constexpr const char *kActionId =
    "aa1deb1ef432ef9816e9749614e4087a15d5b6a4fc215ee92df43230e195ad51";
static constexpr const char *kGeneratedIncludeSha256 =
    "8009f2c5523bd4c592474cc15e6b0b4a8b0a74053a09e69d4926d9f5abffb626";
static constexpr const char *kRecoveryEnvironmentId = "ec5_otp_white_wf20_25";
static constexpr const char *kRecoveryPlatformioConfig =
    "platformio.otp_white_wf20_25.ini";
static constexpr const char *kRecoveryNvsNamespace = "otpw_w20_v1";
static constexpr const char *kRecoveryActionId =
    "6495a2c5182bf0879a4c288c26dd0d24bdbc8f1a5794d5dfac898049d11dbd82";
extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF20_25|ROLE=RUNTIME|SHA256=055c9832f81992094e5c156471c62cf99f36d07bf3c1702568be91f21eb860eb\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
#elif MF1750_RUNTIME_LUT_PROFILE_WF23_25 == 1
static constexpr const char *kBuildTag =
    "MF1750_EC5_RUNTIME_LUT_H3_WF23_25_V1_2026-08-11";
static constexpr const char *kExpectedProfileId = "WF23_25";
static constexpr const char *kEnvironmentId = "ec5_runtime_lut_wf23_25";
static constexpr const char *kCampaignId = "EC5_EMPIRICAL_H3_WF23_25_V1";
static constexpr const char *kContractId =
    "0d69f55551cd9fdc9d77c4c39daade15ac2019ce725d982007091a9d441dc5c3";
static constexpr const char *kNvsNamespace = "rlt_w23_v1";
static constexpr const char *kDescriptorId =
    "1c30da6cfcea2c5d14d779bc395977b8d4b2f3ff598d953702a3313ca72885c1";
static constexpr const char *kActionId =
    "fd3e4294c56c8b5545413c193563a6bfde5b8abf3784e4f42da25b7cf4f85fb9";
static constexpr const char *kGeneratedIncludeSha256 =
    "ee289bc89e9f76f936ca5f2dd0c503f8cc8c8d786c01fc26615c33b9251cb9ff";
static constexpr const char *kRecoveryEnvironmentId = "ec5_otp_white_wf23_25";
static constexpr const char *kRecoveryPlatformioConfig =
    "platformio.otp_white_wf23_25.ini";
static constexpr const char *kRecoveryNvsNamespace = "otpw_w23_v1";
static constexpr const char *kRecoveryActionId =
    "4acae8345b3084657c50f1babc1a5fc3f91898e0b5c64ee6be67459d730c9856";
extern "C" const char kTransactionDescriptorMarker[];
asm(".section .rodata.ec5_tx_descriptor,\"a\"\n"
    ".global kTransactionDescriptorMarker\n"
    ".type kTransactionDescriptorMarker,@object\n"
    "kTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=RUNTIME|SHA256=1c30da6cfcea2c5d14d779bc395977b8d4b2f3ff598d953702a3313ca72885c1\"\n"
    ".size kTransactionDescriptorMarker,.-kTransactionDescriptorMarker\n"
    ".previous\n");
#endif

static constexpr const char *kNvsKey = "used_v1";
static constexpr const char *kVersionRoute =
    "/api/ec5/runtime-lut-h3/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/runtime-lut-h3/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/runtime-lut-h3/status";
static constexpr const char *kReportRoute =
    "/api/ec5/runtime-lut-h3/report";
static constexpr const char *kArmRoute = "/api/ec5/runtime-lut-h3/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/runtime-lut-h3/execute";

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
    "ARM_ONE_FIXED_EMPIRICAL_H3_ATLAS_NOT_HARDWARE_AUTHORIZATION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ONE_FIXED_EMPIRICAL_H3_ATLAS_ONCE";

static constexpr const char *kAtlasFrameSha256 =
    "77454fe933f79b301ecb55b2a065276e0f4fe122bf8416746f71f9b92e90637b";
static constexpr const char *kAtlasCs1DtmSha256 =
    "85cd5683ae2d9c5bf9e97bea539a905cdf244983befaeba7e5321aa73ed774f7";
static constexpr const char *kAtlasCs2DtmSha256 =
    "cfb5bba82a9421e4c3a13ed10731105d78852a05238ca52ddf3bd9cdd099b943";

static constexpr uint8_t kPhaseReady = 0;
static constexpr uint8_t kPhaseArmed = 1;
static constexpr uint8_t kPhaseConsumed = 2;
static constexpr uint8_t kPhaseFault = 3;
static constexpr uint8_t kActionCount = 1;
static constexpr uint8_t kTerminalOrdinal = 2;

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

uint16_t encodeCursor(uint8_t phase, uint8_t ordinal) {
  return static_cast<uint16_t>((static_cast<uint16_t>(phase) << 8) | ordinal);
}

bool cursorFieldsValid(uint8_t phase, uint8_t ordinal) {
  if (phase == kPhaseReady) return ordinal == 1 || ordinal == kTerminalOrdinal;
  return phase <= kPhaseFault && ordinal == 1;
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
  if (!exactHeader(kBuildHeader, kBuildTag))
    return "build_tag_missing_or_mismatch";
  if (!exactHeader(kTestHeader, kTestId))
    return "test_id_missing_or_mismatch";
  if (!exactHeader(kCampaignHeader, kCampaignId))
    return "campaign_id_missing_or_mismatch";
  if (!exactHeader(kActionHeader, kActionId))
    return "action_id_missing_or_mismatch";
  if (!exactHeader(kOrdinalHeader, "1"))
    return "ordinal_missing_or_mismatch";
  if (!exactHeader(kDescriptorHeader, kDescriptorId))
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

String identityJson() {
  return String("\"build_tag\":\"") + kBuildTag + "\",\"test_id\":\"" +
         kTestId + "\",\"campaign_id\":\"" + kCampaignId +
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
  const EpdEmpiricalH3ProfileManifest &profile =
      epdGetEmpiricalH3ProfileManifest();
  return String("{\"profile_id\":\"") + profile.profileId +
         "\",\"compiled_profile_count\":1,\"auto_selected\":false," +
         "\"generated_include_sha256\":\"" + kGeneratedIncludeSha256 +
         "\"," +
         "\"source_artifact_sha256\":\"" + profile.sourceArtifactSha256 +
         "\",\"decoded_plaintext_sha256\":\"" +
         profile.decodedPlaintextSha256 +
         "\",\"decoded_header_sha256\":\"" +
         profile.decodedHeaderSha256 + "\",\"pwr_payload_sha256\":\"" +
         profile.powerPayloadSha256 + "\",\"pll_payload_sha256\":\"" +
         profile.pllPayloadSha256 + "\",\"r20_payload_sha256\":\"" +
         profile.r20PayloadSha256 + "\",\"r21_payload_sha256\":\"" +
         profile.r21PayloadSha256 + "\",\"apparent_temperature_min_c\":" +
         String(profile.apparentTemperatureMinC) +
         ",\"apparent_temperature_max_c\":" +
         String(profile.apparentTemperatureMaxC) +
         ",\"requested_gate_positive_mv\":" +
         String(profile.requestedGatePositiveMv) +
         ",\"requested_gate_negative_mv\":" +
         String(profile.requestedGateNegativeMv) +
         ",\"requested_full_source_positive_mv\":" +
         String(profile.requestedFullSourcePositiveMv) +
         ",\"requested_full_source_negative_mv\":" +
         String(profile.requestedFullSourceNegativeMv) +
         ",\"requested_vsh_lv_mv\":" + String(profile.requestedVshLvMv) +
         ",\"requested_vsl_lv_mv\":" + String(profile.requestedVslLvMv) +
         ",\"requested_vsh_lv2_mv\":" + String(profile.requestedVshLv2Mv) +
         ",\"requested_vsl_lv2_mv\":" + String(profile.requestedVslLv2Mv) +
         ",\"requested_frame_rate_hz\":" +
         String(profile.requestedFrameRateHz) +
         ",\"electrical_values_source\":"
         "\"generated_include_metadata\"," +
         "\"panel_or_fpl_limits_proven\":" +
         (profile.panelOrFplLimitsProven ? "true" : "false") +
         ",\"h3_header_binding_proven\":" +
         (profile.h3HeaderBindingProven ? "true" : "false") +
         ",\"empirical_h3\":true,\"vendor_proven_sequence\":false," +
         "\"live_authorized\":false}";
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

String recoveryContractJson() {
  return "\"external_factory_otp_white_recovery\":{"
         "\"embedded_in_this_binary\":false,\"requires_reflash\":true,"
         "\"separate_exact_authorization_required\":true,"
         "\"runtime_payload_absent\":true,\"hard_reset_before_white\":true,"
         "\"factory_psr\":\"5F69\","
         "\"platformio_config\":\"" + String(kRecoveryPlatformioConfig) +
         "\","
         "\"main_source\":\"src/ec5_factory_otp_white_recovery_main.cpp\","
         "\"environment\":\"" + String(kRecoveryEnvironmentId) +
         "\",\"nvs_namespace\":\"" + String(kRecoveryNvsNamespace) +
         "\",\"action_ordinal\":2,\"action_id\":\"" +
         String(kRecoveryActionId) + "\","
         "\"bodyless_arm_execute\":true,\"permanent_nvs_cursor\":true}";
}

String actionJson() {
  return String("{\"ordinal\":1,\"role\":") +
         "\"EMPIRICAL_H3_EIGHT_CODE_ATLAS\",\"descriptor_id\":\"" +
         kDescriptorId + "\",\"action_id\":\"" + kActionId +
         "\",\"frame_sha256\":\"" + kAtlasFrameSha256 +
         "\",\"cs1_dtm_sha256\":\"" + kAtlasCs1DtmSha256 +
         "\",\"cs2_dtm_sha256\":\"" + kAtlasCs2DtmSha256 + "\"}";
}

String nvsContractJson() {
  return String("\"nvs_contract\":{\"namespace\":\"") + kNvsNamespace +
         "\",\"key\":\"" + kNvsKey +
         "\",\"encoding\":\"uint16_high_byte_phase_low_byte_ordinal\"," +
         "\"initial_cursor\":1,\"terminal_cursor\":2,"
         "\"clear_route\":false,\"persistent_across_reboot\":true}";
}

String versionJson() {
  return String("{\"schema_version\":1,\"kind\":") +
         "\"mf1750-ec5-runtime-lut-empirical-h3-version\"," +
         identityJson() + ",\"classification\":\"" + kClassification +
         "\",\"profile\":" + profileJson() +
         ",\"action_count\":1,\"startup_refresh\":false,"
         "\"raw_ingress\":false,\"retry\":false,"
         "\"automatic_chaining\":false,\"profile_switch\":false,"
         "\"vendor_proven\":false,\"live_authorized\":false}";
}

String manifestJson() {
  return String("{\"schema_version\":1,\"kind\":") +
         "\"mf1750-ec5-runtime-lut-empirical-h3-manifest\"," +
         identityJson() + ",\"classification\":\"" + kClassification +
         "\",\"profile\":" + profileJson() +
         ",\"layout_id\":\"" + kLayoutId +
         "\",\"empirical\":true,\"vendor_proven\":false,"
         "\"live_authorized_until_exact_token\":false,"
         "\"action_count\":1,\"one_driver_call_per_action\":true,"
         "\"startup_refresh\":false,\"raw_frame_ingress\":false,"
         "\"raw_lut_ingress\":false,\"electrical_parameter_ingress\":false,"
         "\"timing_parameter_ingress\":false,\"retry\":false,"
         "\"automatic_chaining\":false,\"profile_switch\":false,"
         "\"vcom_write\":false,\"vcom_sweep\":false,"
         "\"runtime_sequence\":{"
         "\"factory_dual_init_first\":true,\"factory_e0_per_controller\":true,"
         "\"global_init_and_config_scope\":\"ToBoth\","
         "\"runtime_psr\":\"5FE9\",\"tres_reissued\":\"512x600\","
         "\"pwr_source\":\"0F_PLUS_HEADER_0_TO_4\","
         "\"pll_source\":\"HEADER_6\",\"hidden_e9_data\":\"01\","
         "\"global_exact_order\":[\"PSR_5FE9\","
         "\"PWR_FROM_SELECTED_HEADER\",\"IDLE_GATE_AFTER_PWR\","
         "\"PLL_FROM_SELECTED_HEADER\",\"TRES_512X600\"],"
         "\"per_controller_exact_order\":[\"E9_01\","
         "\"IDLE_GATE_AFTER_E9\",\"R20_799\",\"R21_704FF\"],"
         "\"pwr_idle_gate\":true,"
         "\"e9_idle_gate_per_controller\":true,"
         "\"idle_gate_failure_stops_all_later_commands\":true,"
         "\"r20_bytes\":799,\"r21_bytes\":704,\"r21_all_ff\":true,"
         "\"waveform_controller_order\":[\"CS1\",\"CS2\"],"
         "\"waveform_broadcast\":false,\"waveform_readback\":false,"
         "\"single_busy_observes_master_only\":true,"
         "\"slave_profile_acceptance_proven\":false,"
         "\"dtm_per_controller_then_synchronous_refresh\":true},"
         "\"command_emission_policy\":{"
         "\"arbitrary_command_api\":false,"
         "\"forbidden_registers\":[\"90h\",\"91h\"]},"
         "\"actions\":[" + actionJson() + "]," + assumptionsJson() +
         "," + recoveryContractJson() + "," + nvsContractJson() + "}";
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
  const bool cursorValid = refreshCursorEvidence();
  return String("{\"schema_version\":1,\"kind\":") +
         "\"mf1750-ec5-runtime-lut-empirical-h3-status\"," +
         identityJson() + ",\"profile_id\":\"" + kExpectedProfileId +
         "\",\"boot_nonce\":\"" + bootNonce() + "\",\"state\":\"" +
         stateName(state) + "\",\"phase\":" + String(persistentPhase) +
         ",\"phase_name\":\"" + phaseName(persistentPhase) +
         "\",\"cursor_raw\":" + String(cursorRaw) +
         ",\"next_ordinal\":" + String(nextOrdinal) +
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
         ",\"total_driver_call_count\":" + String(totalDriverCallCount) +
         "," + gpioJson() + "}";
}

void publishNoExecuteReport() {
  publishedReport =
      String("{\"schema_version\":1,\"kind\":") +
      "\"mf1750-ec5-runtime-lut-empirical-h3-report\",\"valid\":false," +
      identityJson() + ",\"terminal_state\":\"NOT_EXECUTED\"," +
      "\"result\":false,\"error\":\"no_execute_report\"," +
      "\"driver_called\":false,\"driver_call_count_for_action\":0,"
      "\"no_retry\":true,\"no_recovery_in_this_binary\":true}";
}

void publishFaultReport(const char *error, bool driverCalled,
                        const EpdOperationReport *driver = nullptr) {
  publishedReport =
      String("{\"schema_version\":1,\"kind\":") +
      "\"mf1750-ec5-runtime-lut-empirical-h3-report\",\"valid\":" +
      (driverCalled ? "true" : "false") + "," + identityJson() +
      ",\"ordinal\":1,\"action_id\":\"" + kActionId +
      "\",\"terminal_state\":\"FAULT\",\"result\":false,\"error\":\"" +
      error + "\",\"driver_called\":" +
      (driverCalled ? "true" : "false") +
      ",\"driver_call_count_for_action\":" +
      String(driverCalled ? driverCallCountForAction : 0) +
      ",\"no_retry\":true,\"no_recovery_in_this_binary\":true" +
      (driver ? String(",\"driver\":") + epdDiagnosticReportJson()
              : String("")) +
      "}";
}

void enterFault(const char *error, bool driverCalled = false,
                const EpdOperationReport *driver = nullptr) {
  executePending = false;
  persistCursor(kPhaseFault, 1);
  state = RuntimeState::FaultLocked;
  publishFaultReport(error, driverCalled, driver);
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
      nextOrdinal != 1) {
    rejectMutation(409, "arm_duplicate_complete_or_not_ready");
    return;
  }
  const char *contractError = validateMutationContract(kArmIntent, false);
  if (contractError) {
    rejectMutation(400, contractError);
    return;
  }
  if (!fixtureSelfCheckPassed || !gpioInitialized || !storeReady) {
    rejectMutation(503, "arm_preflight_not_ready");
    return;
  }
  armNonceHigh = esp_random();
  armNonceLow = esp_random();
  if ((armNonceHigh | armNonceLow) == 0) armNonceLow = 1;
  driverCallCountForAction = 0;
  if (!persistCursor(kPhaseArmed, 1)) {
    rejectMutation(503, "persistent_armed_write_failed");
    return;
  }
  state = RuntimeState::Armed;
  server.send(201, "application/json",
              String("{\"accepted\":true,\"armed\":true,") +
                  identityJson() + ",\"ordinal\":1,\"action_id\":\"" +
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
      nextOrdinal != 1) {
    rejectMutation(409, "execute_duplicate_stale_or_not_armed");
    return;
  }
  const char *contractError = validateMutationContract(kExecuteIntent, true);
  if (contractError) {
    rejectMutation(400, contractError);
    return;
  }
  if (!fixtureSelfCheckPassed || !gpioInitialized || !storeReady ||
      driverCallCountForAction != 0) {
    rejectMutation(503, "execute_preflight_not_ready");
    return;
  }
  // Consume durably before acknowledging or dispatching the visible action.
  if (!persistCursor(kPhaseConsumed, 1)) {
    rejectMutation(503, "persistent_consumed_write_failed");
    return;
  }
  jobQueuedAtMs = millis();
  state = RuntimeState::Queued;
  executePending = true;
  server.send(202, "application/json",
              String("{\"accepted\":true,\"job_id\":1,") +
                  identityJson() + ",\"action_id\":\"" + kActionId +
                  "\",\"execute_consumed\":true,\"no_retry\":true," +
                  "\"no_recovery_in_this_binary\":true}");
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
    const uint32_t startedAt = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - startedAt < 15000UL)
      delay(250);
    if (WiFi.status() == WL_CONNECTED) return;
  }
  WiFi.mode(WIFI_AP);
  WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASSWORD);
}

void executePendingAction() {
  if (!executePending) return;
  if (!refreshCursorEvidence() || persistentPhase != kPhaseConsumed ||
      nextOrdinal != 1 || state != RuntimeState::Queued ||
      driverCallCountForAction != 0) {
    enterFault("runtime_queue_or_cursor_mismatch");
    return;
  }
  executePending = false;
  state = RuntimeState::Running;
  jobStartedAtMs = millis();
  ++driverCallCountForAction;
  ++totalDriverCallCount;
  const bool result = epdDisplayCompiledEmpiricalH3(
      EpdEmpiricalH3Role::RuntimeEightCodeAtlas);
  jobFinishedAtMs = millis();
  const EpdOperationReport &driver = epdGetLastOperationReport();
  if (!result) {
    persistCursor(kPhaseFault, 1);
    state = RuntimeState::FaultLocked;
    publishFaultReport("driver_operation_failed", true, &driver);
    return;
  }
  if (!persistCursor(kPhaseReady, kTerminalOrdinal)) {
    enterFault("persistent_terminal_write_failed", true, &driver);
    return;
  }
  state = RuntimeState::Complete;
  publishedReport =
      String("{\"schema_version\":1,\"kind\":") +
      "\"mf1750-ec5-runtime-lut-empirical-h3-report\",\"valid\":true," +
      identityJson() + ",\"profile_id\":\"" + kExpectedProfileId +
      "\",\"ordinal\":1,\"action_id\":\"" + kActionId +
      "\",\"terminal_state\":\"COMPLETE\",\"result\":true,"
      "\"driver_called\":true,\"driver_call_count_for_action\":1,"
      "\"total_driver_call_count\":" + String(totalDriverCallCount) +
      ",\"next_ordinal\":2,\"campaign_complete\":true,"
      "\"no_retry\":true,\"no_recovery_in_this_binary\":true,"
      "\"job_queued_at_ms\":" + String(jobQueuedAtMs) +
      ",\"job_started_at_ms\":" + String(jobStartedAtMs) +
      ",\"job_finished_at_ms\":" + String(jobFinishedAtMs) +
      ",\"driver\":" + epdDiagnosticReportJson() + "}";
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(50);
  Serial.printf("\nMF1750 EC5 empirical H3 runtime-LUT boot: %s\n",
                kExpectedProfileId);
  Serial.println("Empirical/not vendor-proven/not live-authorized");
  Serial.println("No startup refresh/raw ingress/retry/autochain/profile switch");

  bootNonceHigh = esp_random();
  bootNonceLow = esp_random();
  if ((bootNonceHigh | bootNonceLow) == 0) bootNonceLow = 1;

  runningAppElfShaValid = loadRunningAppElfSha256();

  const EpdEmpiricalH3ProfileManifest &profile =
      epdGetEmpiricalH3ProfileManifest();
  fixtureSelfCheckPassed =
      runningAppElfShaValid &&
      std::strcmp(profile.profileId, kExpectedProfileId) == 0 &&
      !profile.liveAuthorized && !profile.vendorProvenSequence &&
      !profile.profileAutoSelected && epdValidateCompiledEmpiricalH3Fixtures();
  storeReady = cursorStore.begin(kNvsNamespace, false /* readOnly */);
  const bool cursorValid = refreshCursorEvidence();
  if (!runningAppElfShaValid) {
    state = RuntimeState::FaultLocked;
    publishFaultReport("running_app_elf_sha256_self_check_failed", false);
  } else if (!fixtureSelfCheckPassed) {
    state = RuntimeState::FaultLocked;
    publishFaultReport("compiled_fixture_self_check_failed", false);
  } else if (!storeReady) {
    state = RuntimeState::FaultLocked;
    publishFaultReport("cursor_store_open_failed", false);
  } else if (!cursorValid) {
    state = RuntimeState::FaultLocked;
    publishFaultReport("persistent_cursor_invalid", false);
  } else if (persistentPhase != kPhaseReady) {
    enterFault("non_ready_cursor_seen_at_boot");
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
}

void loop() {
  server.handleClient();
  executePendingAction();
  delay(2);
}
