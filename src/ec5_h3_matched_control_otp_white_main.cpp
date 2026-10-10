#include <cstring>

#include "epd_diagnostics.h"
#include "epd_driver.h"

#if MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY != 1 || \
    MF1750_OTP_WHITE_FOR_PROFILE_WF20_25 != 1 || \
    MF1750_OTP_WHITE_FOR_PROFILE_WF23_25 != 0
#error "Matched-control recovery requires isolated WF20_25 factory OTP white"
#endif

namespace {

static constexpr char kH3mcProfileId[] = "WF20_25";
static constexpr char kH3mcEnvironmentId[] =
    "ec5_h3_matched_control_otp_white_wf20_25";
static constexpr char kH3mcCampaignId[] =
    "EC5_H3_MATCHED_NO_R20_R21_WF20_25_C_FIRST_V2";
static constexpr char kH3mcBuildTag[] =
    "MF1750_EC5_H3_MATCHED_CONTROL_OTP_WHITE_WF20_25_C_FIRST_V2_2026-08-11";
static constexpr char kH3mcTestId[] =
    "EC5-H3-MATCHED-CONTROL-OTP-WHITE-C-FIRST-V2";
static constexpr char kH3mcContractId[] =
    "25267914e74b249cc4bd1cc821437ea700a3c41a75140d82862c86357b3a63fe";
static constexpr char kH3mcDescriptorId[] =
    "b0ee745bb3b2ef669ce42833f928dad4d9b125c9ea659897178ec8e2d7989017";
static constexpr char kH3mcActionId[] =
    "b2084e70dad18b5b7465d745394abc5ff14aa28bbd5cef50d1229fc43f096235";
static constexpr char kH3mcNvsNamespace[] = "h3crw20_v2";
static constexpr char kH3mcBaseRoute[] =
    "/api/ec5/h3-matched-control-white-v2";
static constexpr char kH3mcClassification[] =
    "MATCHED_CONTROL_FACTORY_OTP_WHITE_RECOVERY_ONLY_NOT_AUTHORIZED";
static constexpr char kH3mcKindPrefix[] =
    "mf1750-ec5-h3-matched-control-otp-white";
static constexpr char kH3mcIdentityRevision[] =
    "h3-matched-control-otp-white-c-first-v2";
static constexpr char kH3mcDeviceApiVersion[] =
    "MF1750_EC5_H3_MATCHED_CONTROL_DEVICE_V2";
static constexpr char kH3mcRole[] =
    "H3_MATCHED_CONTROL_FACTORY_OTP_WHITE_RECOVERY";
static constexpr char kH3mcArmIntent[] =
    "ARM_ONE_MATCHED_CONTROL_FACTORY_OTP_WHITE_NOT_AUTHORIZATION";
static constexpr char kH3mcExecuteIntent[] =
    "EXECUTE_ONE_MATCHED_CONTROL_FACTORY_OTP_WHITE_ONCE";
static constexpr char kH3mcFrameSha256[] =
    "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d";
static constexpr char kH3mcCs1DtmSha256[] =
    "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158";
static constexpr char kH3mcCs2DtmSha256[] =
    "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158";
static constexpr uint8_t kH3mcActionOrdinal = 2;
static constexpr uint8_t kH3mcTerminalOrdinal = 3;

static_assert(sizeof(kH3mcNvsNamespace) - 1 <= 15,
              "ESP32 Preferences namespace is limited to 15 characters");

extern "C" const char kH3mcTransactionDescriptorMarker[];
asm(".section .rodata.h3mc_tx_descriptor,\"a\"\n"
    ".global kH3mcTransactionDescriptorMarker\n"
    ".type kH3mcTransactionDescriptorMarker,@object\n"
    "kH3mcTransactionDescriptorMarker:\n"
    ".asciz \"MF1750_EC5_H3_MATCHED_CONTROL_TX_DESCRIPTOR_V2|PROFILE=WF20_25|ROLE=OTP_WHITE|SHA256=b0ee745bb3b2ef669ce42833f928dad4d9b125c9ea659897178ec8e2d7989017\"\n"
    ".size kH3mcTransactionDescriptorMarker,.-kH3mcTransactionDescriptorMarker\n"
    ".previous\n");

extern "C" const char kH3mcCommandAuditMarker[];
asm(".section .rodata.h3mc_command_audit,\"a\"\n"
    ".global kH3mcCommandAuditMarker\n"
    ".type kH3mcCommandAuditMarker,@object\n"
    "kH3mcCommandAuditMarker:\n"
    ".asciz \"MF1750_EC5_H3_MATCHED_CONTROL_COMMAND_AUDIT_V2|FACTORY_OTP_ONLY=1|CONTROL_SEQUENCE=0|RUNTIME_PAYLOAD=0\"\n"
    ".size kH3mcCommandAuditMarker,.-kH3mcCommandAuditMarker\n"
    ".previous\n");

bool h3mcOnceValidateFixture() {
  return epdValidateCompiledFactoryOtpWhiteRecoveryFixture();
}

bool h3mcOnceExecuteFixture() {
  return epdDisplayCompiledFactoryOtpWhiteRecovery();
}

String h3mcOnceProfileJson() {
  return "{\"profile_id\":\"WF20_25\",\"compiled_profile_count\":1,"
         "\"auto_selected\":false,\"apparent_temperature_min_c\":0,"
         "\"apparent_temperature_max_c\":37,"
         "\"temperature_policy\":"
         "\"factory_otp_existing_observed_ceiling_not_vendor_band\","
         "\"temperature_limit_is_safety_qualification\":false}";
}

String h3mcOnceSequenceJson() {
  return "\"factory_otp_white_sequence\":{\"hard_reset\":true,"
         "\"psr\":\"5F69\",\"tres\":\"512x600\","
         "\"e0_per_controller\":true,"
         "\"dtm_controller_order\":[\"CS1\",\"CS2\"],"
         "\"synchronous_refresh\":true},"
         "\"matched_control_sequence_present\":false,"
         "\"runtime_payload_present\":false,"
         "\"r20_command_writes\":0,\"r21_command_writes\":0";
}

String h3mcOnceReportFields() {
  return "\"factory_otp_only\":true,\"matched_control_sequence\":false,"
         "\"runtime_payload_present\":false";
}

String h3mcOnceDriverJson() {
  const String base = epdDiagnosticReportJson();
  if (!base.startsWith("{")) return "{}";
  return String("{\"factory_otp_white\":true,") +
         "\"matched_no_r20_r21_control\":false," + base.substring(1);
}

}  // namespace

#include "ec5_h3_matched_control_once_main.inc"
