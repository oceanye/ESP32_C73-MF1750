#include "ec5_runtime_lut_partial_hold_repeat_ptlw_v2_identity.inc"

namespace rlph = mf1750_runtime_lut_partial_hold_repeat_ptlw_v2;

static constexpr const char *kClassification =
    "EXPERIMENTAL_SPD1657_L535_REPEAT_PTLW_WITH_FACTORY_OTP_WHITE_ANCHORS";
static constexpr const char *kProfileSource =
    "factory_otp_white_plus_legacy_complete_535_reference_active_global";
static constexpr const char *kIdentityRevision =
    "runtime-lut-partial-hold-repeat-ptlw-v2";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_DEVICE_V2";
static constexpr const char *kLayoutId = rlph::kVariantKey;
static constexpr const char *kBuildTag = rlph::kBuildTag;
static constexpr const char *kBootLabel =
    "EC5 factory-white anchored repeat-PTLW V2";
static constexpr const char *kTestId = rlph::kTestId;
static constexpr const char *kCampaignId = rlph::kCampaignId;
static constexpr const char *kContractId = rlph::kContractId;
static constexpr const char *kVersionKind =
    "mf1750-ec5-runtime-lut-repeat-ptlw-v2-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-runtime-lut-repeat-ptlw-v2-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-runtime-lut-repeat-ptlw-v2-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-runtime-lut-repeat-ptlw-v2-report";
static constexpr const char *kBaselineRole =
    "FACTORY_OTP_WHITE_HEALTH_ANCHOR";
static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"factory_otp_anchor_ordinal\":1,"
    "\"factory_otp_recovery_ordinal\":5,"
    "\"factory_otp_white_frame_fill_byte\":17,"
    "\"factory_otp_white_frame_bytes\":307200,"
    "\"anchor_established_by_firmware\":true,"
    "\"external_factory_white_anchor_required\":false,"
    "\"runtime_code7_action_reachable\":false,"
    "\"runtime_transport_codes\":[3,5,6],"
    "\"ptlw_command\":131,\"ptlw_payload_bytes\":9,"
    "\"ptlw_endpoint_contract\":\"xe=x+w-1;ye=y+h-1\","
    "\"ptlw_mode\":1,\"ptlw_writes_per_controller\":2,"
    "\"initial_ptlw_before_cropped_dtm\":true,"
    "\"repeat_ptlw_after_pon_busy\":true,"
    "\"pre_pon_cdi_ff_preserved\":true,"
    "\"post_pon_sequence\":[\"PTLW_CS1\",\"PTLW_CS2\","
    "\"CDI_FF_BOTH\",\"BTST2\",\"DRF\"],"
    "\"pon_timeout_ms\":60000,\"cropped_dtm\":true,"
    "\"packed_bpp\":4,\"windows_disjoint\":true,"
    "\"cs2_position_mirrored\":false,"
    "\"runtime_lut_profile_id\":"
    "\"LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535\","
    "\"global_header_profile\":\"legacy_active\","
    "\"cs1_r20_prefix_bytes\":535,"
    "\"cs1_r20_prefix_sha256\":"
    "\"716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b\","
    "\"cs2_r20_prefix_bytes\":535,"
    "\"cs2_r20_prefix_sha256\":"
    "\"2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26\","
    "\"r21_bytes\":704,"
    "\"r21_sha256\":"
    "\"24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f\","
    "\"sequential_hold_observation_required\":true,"
    "\"camera_required\":false}";
static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":true,\"window_refresh\":true,"
    "\"command_0x83\":true,\"command_0x86\":false,"
    "\"mid_refresh_power_cut\":false,"
    "\"spi_frequency_sweep\":false,"
    "\"full_screen_global_refresh\":true,"
    "\"factory_otp_white_actions\":true,"
    "\"same_palette_hold_probe\":true,"
    "\"cross_palette_hold_probe\":false";

static constexpr const char *kNvsNamespace = rlph::kNvsNamespace;
static constexpr const char *kNvsKey = "cursor_rptv2";

static constexpr const char *kVersionRoute =
    "/api/ec5/runtime-lut-repeat-ptlw-v2/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/runtime-lut-repeat-ptlw-v2/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/runtime-lut-repeat-ptlw-v2/status";
static constexpr const char *kReportRoute =
    "/api/ec5/runtime-lut-repeat-ptlw-v2/report";
static constexpr const char *kArmRoute =
    "/api/ec5/runtime-lut-repeat-ptlw-v2/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/runtime-lut-repeat-ptlw-v2/execute";

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
    "ARM_ONE_FIXED_FACTORY_WHITE_OR_L535_REPEAT_PTLW_V2_ACTION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ARMED_FACTORY_WHITE_OR_L535_REPEAT_PTLW_V2_ACTION_ONCE";

static constexpr const char *kWhiteFrameSha256 =
    "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d";
static constexpr const char *kWhiteDtmSha256 =
    "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158";

#define RLPH_V2_PARTIAL_ACTION(ORDINAL, DRIVER_ROLE, INDEX, PRIOR)           \
  {                                                                          \
    ORDINAL, DRIVER_ROLE, rlph::kActions[INDEX].role, 1,                     \
        rlph::kActions[INDEX].branch, rlph::kActions[INDEX].descriptorId,    \
        rlph::kActions[INDEX].actionId, PRIOR,                               \
        rlph::kActions[INDEX].frameSha256,                                   \
        rlph::kActions[INDEX].cs1DtmSha256,                                  \
        rlph::kActions[INDEX].cs2DtmSha256,                                  \
        rlph::kActions[INDEX].frameFnv1a,                                    \
        rlph::kActions[INDEX].cs1DtmFnv1a,                                   \
        rlph::kActions[INDEX].cs2DtmFnv1a,                                   \
        {rlph::kActions[INDEX].histogram[0],                                 \
         rlph::kActions[INDEX].histogram[1],                                 \
         rlph::kActions[INDEX].histogram[2],                                 \
         rlph::kActions[INDEX].histogram[3],                                 \
         rlph::kActions[INDEX].histogram[4],                                 \
         rlph::kActions[INDEX].histogram[5],                                 \
         rlph::kActions[INDEX].histogram[6],                                 \
         rlph::kActions[INDEX].histogram[7]}                                 \
  }

static constexpr ActionDescriptor kActions[] = {
    {1,
     EpdChromaGridRole::White,
     "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
     1,
     "FACTORY_OTP_FULL_FRAME_0X11_HEALTH_ANCHOR",
     "ac59eceed7b6d6ccb2defaae78ee309d32f9e11e31ec692ef94b0ebc9de9bafc",
     "9d4d2606c8a813a8fa0edf41f567e874361ce482a76edd0fa3ae5259cd810c31",
     nullptr,
     kWhiteFrameSha256,
     kWhiteDtmSha256,
     kWhiteDtmSha256,
     0x13340DC5UL,
     0xB7A855C5UL,
     0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    RLPH_V2_PARTIAL_ACTION(
        2, EpdChromaGridRole::Source, 0,
        "9d4d2606c8a813a8fa0edf41f567e874361ce482a76edd0fa3ae5259cd810c31"),
    RLPH_V2_PARTIAL_ACTION(3, EpdChromaGridRole::Mid, 1,
                           rlph::kActions[0].actionId),
    RLPH_V2_PARTIAL_ACTION(4, EpdChromaGridRole::Target, 2,
                           rlph::kActions[1].actionId),
    {5,
     EpdChromaGridRole::White,
     "FACTORY_OTP_WHITE_RECOVERY",
     1,
     "FACTORY_OTP_FULL_FRAME_0X11_RECOVERY",
     "ec00674ddaddb3afe912fd75d900e201e7aa1410d162cd769c27ada9dd62b8d2",
     "81b62d87de778922166399b83f562144f3cd86414214bc9d662651c184f71990",
     rlph::kActions[2].actionId,
     kWhiteFrameSha256,
     kWhiteDtmSha256,
     kWhiteDtmSha256,
     0x13340DC5UL,
     0xB7A855C5UL,
     0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
};

#undef RLPH_V2_PARTIAL_ACTION
