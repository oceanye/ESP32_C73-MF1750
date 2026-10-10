#include "ec5_h3_c23_matched_control_driver.h"

#include <cstring>

#include "epd_diagnostics.h"

namespace {

static constexpr char kH3mcProfileId[] = "WF23_25";
static constexpr char kH3mcEnvironmentId[] =
    "ec5_h3_c23_matched_no_r20_r21_wf23_25";
static constexpr char kH3mcCampaignId[] =
    "EC5_H3_C23_MATCHED_NO_R20_R21_WF23_25_V1";
static constexpr char kH3mcBuildTag[] =
    "MF1750_EC5_H3_C23_NO_R20_R21_WF23_25_V1_2026-08-13";
static constexpr char kH3mcTestId[] =
    "EC5-H3-C23-MATCHED-NO-R20-R21-V1";
static constexpr char kH3mcContractId[] =
    "435ecd217664de1a4e1f67ded31e8ce2bc1fffbd38759b5e1830aef5bc0ad882";
static constexpr char kH3mcDescriptorId[] =
    "f0eb7840ac1e8d245884d4303ca82d913b062615f72e6905871db12117dc5dad";
static constexpr char kH3mcActionId[] =
    "9d60aa592daddd02ab2419e30d529b18ef90d3861253a81672dc6fedee3b2835";
static constexpr char kH3mcNvsNamespace[] = "h3c23ctl_v1";
static constexpr char kH3mcBaseRoute[] =
    "/api/ec5/h3-c23-control-v1";
static constexpr char kH3mcClassification[] =
    "WF23_HEADER_MATCHED_DELETE_ONLY_CONTROL_NOT_AUTHORIZATION";
static constexpr char kH3mcKindPrefix[] =
    "mf1750-ec5-h3-c23-matched-no-r20-r21";
static constexpr char kH3mcIdentityRevision[] =
    "h3-c23-matched-no-r20-r21-v1";
static constexpr char kH3mcDeviceApiVersion[] =
    "MF1750_EC5_H3_C23_MATCHED_CONTROL_DEVICE_V1";
static constexpr char kH3mcRole[] =
    "H3_C23_MATCHED_NO_R20_R21_EIGHT_CODE_ATLAS";
static constexpr char kH3mcArmIntent[] =
    "ARM_ONE_C23_NO_R20_R21_ATLAS_NOT_AUTHORIZATION";
static constexpr char kH3mcExecuteIntent[] =
    "EXECUTE_ONE_C23_NO_R20_R21_ATLAS_ONCE";
static constexpr char kH3mcFrameSha256[] =
    "77454fe933f79b301ecb55b2a065276e0f4fe122bf8416746f71f9b92e90637b";
static constexpr char kH3mcCs1DtmSha256[] =
    "85cd5683ae2d9c5bf9e97bea539a905cdf244983befaeba7e5321aa73ed774f7";
static constexpr char kH3mcCs2DtmSha256[] =
    "cfb5bba82a9421e4c3a13ed10731105d78852a05238ca52ddf3bd9cdd099b943";
static constexpr uint8_t kH3mcActionOrdinal = 1;
static constexpr uint8_t kH3mcTerminalOrdinal = 2;

static_assert(sizeof(kH3mcNvsNamespace) - 1 <= 15,
              "ESP32 Preferences namespace is limited to 15 characters");

extern "C" const char kH3mcTransactionDescriptorMarker[];
asm(".section .rodata.h3mc_tx_descriptor,\"a\"\n"
    ".global kH3mcTransactionDescriptorMarker\n"
    ".type kH3mcTransactionDescriptorMarker,@object\n"
    "kH3mcTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_H3_C23_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=NO_R20_R21|SHA256=f0eb7840ac1e8d245884d4303ca82d913b062615f72e6905871db12117dc5dad\"\n"
    ".size kH3mcTransactionDescriptorMarker,.-kH3mcTransactionDescriptorMarker\n"
    ".previous\n");

extern "C" const char kH3mcCommandAuditMarker[];
asm(".section .rodata.h3mc_command_audit,\"a\"\n"
    ".global kH3mcCommandAuditMarker\n"
    ".type kH3mcCommandAuditMarker,@object\n"
    "kH3mcCommandAuditMarker:\n"
    ".asciz \"MF1750_EC5_H3_C23_COMMAND_AUDIT_V1|R20_COMMAND_WRITES=0|R21_COMMAND_WRITES=0|R20_BYTES=0|R21_BYTES=0|DESIGN=WF23_E9_ONLY_DELETE_ONLY_NOT_TIME_MATCHED\"\n"
    ".size kH3mcCommandAuditMarker,.-kH3mcCommandAuditMarker\n"
    ".previous\n");

bool h3mcOnceValidateFixture() {
  const EpdH3C23MatchedControlManifest &profile =
      epdGetH3C23MatchedControlManifest();
  return std::strcmp(profile.profileId, kH3mcProfileId) == 0 &&
         profile.matchedNegativeControl && !profile.r20CommandPresent &&
         !profile.r21CommandPresent && !profile.runtimePayloadPresent &&
         !profile.vendorProvenSequence && !profile.liveAuthorized &&
         !profile.profileAutoSelected &&
         epdValidateCompiledH3C23MatchedControlFixture();
}

bool h3mcOnceExecuteFixture() {
  return epdDisplayCompiledH3C23MatchedControl(
      EpdH3C23MatchedControlRole::EightCodeAtlasWithoutR20R21);
}

String h3mcOnceProfileJson() {
  const EpdH3C23MatchedControlManifest &profile =
      epdGetH3C23MatchedControlManifest();
  return String("{\"profile_id\":\"") + profile.profileId +
         "\",\"compiled_profile_count\":1,\"auto_selected\":false," +
         "\"source_artifact_sha256\":\"" + profile.sourceArtifactSha256 +
         "\",\"decoded_header_sha256\":\"" +
         profile.decodedHeaderSha256 + "\",\"pwr_payload_sha256\":\"" +
         profile.powerPayloadSha256 + "\",\"pll_payload_sha256\":\"" +
         profile.pllPayloadSha256 +
         "\",\"apparent_temperature_min_c\":" +
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
         "\"matched_wf23_25_constants\"," +
         "\"panel_or_fpl_limits_proven\":false,"
         "\"r20_command_writes\":0,\"r21_command_writes\":0,"
         "\"r20_payload_bytes\":0,\"r21_payload_bytes\":0," +
         "\"empirical_cross_version\":true,\"matched_negative_control\":true," +
         "\"vendor_proven_sequence\":false,\"live_authorized\":false}";
}

String h3mcOnceSequenceJson() {
  return "\"r20_command_writes\":0,\"r21_command_writes\":0,"
         "\"r20_payload_bytes\":0,\"r21_payload_bytes\":0,"
         "\"control_design\":"
         "\"WF23_E9_ONLY_NO_R20_R21_DELETE_ONLY_NOT_TIME_MATCHED\","
         "\"strict_payload_only_control\":false,"
         "\"time_matched_control\":false,"
         "\"dummy_clocks_inserted\":false,"
         "\"empty_r20_or_r21_commands_inserted\":false,"
         "\"per_controller_removed_spi_bytes_and_edges\":1505,"
         "\"per_controller_removed_cooperative_yields\":5,"
         "\"e9_and_busy_gate_preserved\":true,"
         "\"matched_sequence\":{"
         "\"factory_dual_init_first\":true,\"factory_psr\":\"5F69\","
         "\"factory_e0_per_controller\":true,"
         "\"global_exact_order\":[\"PSR_5FE9\","
         "\"PWR_FROM_WF23_25_HEADER\",\"IDLE_GATE_AFTER_PWR\","
         "\"PLL_FROM_WF23_25_HEADER\",\"TRES_512X600\"],"
         "\"per_controller_exact_order\":[\"CS1_E9_01\","
         "\"IDLE_GATE_AFTER_CS1_E9\",\"CS2_E9_01\","
         "\"IDLE_GATE_AFTER_CS2_E9\"],"
         "\"r20_command_writes\":0,\"r21_command_writes\":0,"
         "\"r20_bytes\":0,\"r21_bytes\":0,"
         "\"dtm_frame_identical_to_t23_atlas\":true,"
         "\"dtm_controller_order\":[\"CS1\",\"CS2\"],"
         "\"synchronous_refresh\":true,\"waveform_readback\":false,"
         "\"single_busy_observes_master_only\":true},"
         "\"no_difference_interpretation\":"
         "\"NO_DETECTABLE_INCREMENTAL_EFFECT\","
         "\"payload_only_attribution_proven\":false,"
         "\"separate_otp_white_recovery_required\":true";
}

String h3mcOnceReportFields() {
  return "\"r20_command_writes\":0,\"r21_command_writes\":0,"
         "\"r20_payload_bytes\":0,\"r21_payload_bytes\":0,"
         "\"matched_negative_control\":true,"
         "\"control_design\":"
         "\"WF23_E9_ONLY_NO_R20_R21_DELETE_ONLY_NOT_TIME_MATCHED\","
         "\"strict_payload_only_control\":false,"
         "\"time_matched_control\":false,"
         "\"dummy_clocks_inserted\":false,"
         "\"empty_r20_or_r21_commands_inserted\":false,"
         "\"per_controller_removed_spi_bytes_and_edges\":1505,"
         "\"per_controller_removed_cooperative_yields\":5,"
         "\"no_difference_interpretation\":"
         "\"NO_DETECTABLE_INCREMENTAL_EFFECT\"";
}

String h3mcOnceDriverJson() {
  const String base = epdDiagnosticReportJson();
  if (!base.startsWith("{")) return "{}";
  return String("{\"c23_matched_no_r20_r21_control\":true,") +
         "\"r20_command_writes\":0,\"r21_command_writes\":0,"
         "\"r20_payload_bytes\":0,\"r21_payload_bytes\":0," +
         "\"control_design\":"
         "\"WF23_E9_ONLY_NO_R20_R21_DELETE_ONLY_NOT_TIME_MATCHED\","
         "\"strict_payload_only_control\":false,"
         "\"time_matched_control\":false,"
         "\"dummy_clocks_inserted\":false,"
         "\"empty_r20_or_r21_commands_inserted\":false,"
         "\"per_controller_removed_spi_bytes_and_edges\":1505,"
         "\"per_controller_removed_cooperative_yields\":5," +
         base.substring(1);
}

}  // namespace

#include "ec5_h3_matched_control_once_main.inc"

