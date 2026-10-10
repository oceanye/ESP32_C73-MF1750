#include "ec5_runtime_lut_partial_hold_endpoint_ab_v1_identity.inc"

namespace rlph = mf1750_runtime_lut_partial_hold_endpoint_ab_v1;

static constexpr const char *kClassification =
    "EXPERIMENTAL_SPD1657_L535_PTLW_YEND_CONTROLLER_SWAP_AB_BUSY_QUALIFIED_WITH_FACTORY_OTP_WHITE_ANCHORS";
static constexpr const char *kProfileSource =
    "factory_otp_white_plus_legacy_complete_535_reference_active_global";
static constexpr const char *kIdentityRevision =
    "runtime-lut-partial-hold-endpoint-ab-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_ENDPOINT_AB_DEVICE_V1";
static constexpr const char *kLayoutId = rlph::kVariantKey;
static constexpr const char *kBuildTag = rlph::kBuildTag;
static constexpr const char *kBootLabel =
    "EC5 BUSY-qualified PTLW Y-end controller-swap A/B V1";
static constexpr const char *kTestId = rlph::kTestId;
static constexpr const char *kCampaignId = rlph::kCampaignId;
static constexpr const char *kContractId = rlph::kContractId;
static constexpr const char *kVersionKind =
    "mf1750-ec5-runtime-lut-ptlw-yend-ab-v1-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-runtime-lut-ptlw-yend-ab-v1-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-runtime-lut-ptlw-yend-ab-v1-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-runtime-lut-ptlw-yend-ab-v1-report";
static constexpr const char *kBaselineRole =
    "FACTORY_OTP_WHITE_HEALTH_ANCHOR";
static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"factory_otp_anchor_ordinal\":1,\"factory_otp_reset_ordinal\":3,"
    "\"factory_otp_recovery_ordinal\":5,"
    "\"factory_otp_white_frame_fill_byte\":17,"
    "\"factory_otp_white_frame_bytes\":307200,"
    "\"anchor_established_by_firmware\":true,"
    "\"external_factory_white_anchor_required\":false,"
    "\"runtime_code7_action_reachable\":false,"
    "\"runtime_transport_codes\":[5],"
    "\"ptlw_command\":131,\"ptlw_payload_bytes\":9,\"ptlw_mode\":1,"
    "\"ptlw_endpoint_contract\":\"PER_CONTROLLER_ACTION_MATRIX\","
    "\"endpoint_matrix\":["
    "{\"ordinal\":2,\"cs1\":\"ye=y+h-1\",\"cs2\":\"ye=y+h\"},"
    "{\"ordinal\":4,\"cs1\":\"ye=y+h\",\"cs2\":\"ye=y+h-1\"}],"
    "\"dtm_rows_per_controller\":120,"
    "\"dtm_bytes_per_controller\":9600,"
    "\"ptlw_writes_per_controller\":2,"
    "\"initial_ptlw_before_cropped_dtm\":true,"
    "\"repeat_ptlw_after_pon_busy\":true,"
    "\"pre_pon_cdi_ff_preserved\":true,"
    "\"post_pon_sequence\":[\"PTLW_CS1\",\"PTLW_CS2\","
    "\"CDI_FF_BOTH\",\"BTST2\",\"DRF\"],"
    "\"pon_timeout_ms\":60000,\"cropped_dtm\":true,"
    "\"packed_bpp\":4,\"windows_disjoint\":false,"
    "\"same_roi_crossover\":true,\"fresh_white_before_each_treatment\":true,"
    "\"exact_spd1657a_local_manual_y_end\":\"y+h-1\","
    "\"adjacent_gx_experimental_comparator_y_end\":\"y+h\","
    "\"adjacent_reference_121_row_ptlw_with_120_row_dtm\":true,"
    "\"adjacent_reference_comparator_is_predicted_fix\":false,"
    "\"physical_bottom_equals_logical_y_end_proven\":false,"
    "\"observation_must_record\":[\"FPC_DIRECTION\","
    "\"PHYSICAL_ANOMALY_EDGE\",\"MAPPED_LOGICAL_EDGE_IF_KNOWN\","
    "\"CS1_VS_CS2\"],"
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
    "\"r21_bytes\":704,\"r21_sha256\":"
    "\"24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f\","
    "\"sequential_hold_observation_required\":true,"
    "\"camera_required\":false,\"busy_idle_level_required\":1,"
    "\"busy_zero_accepted\":false}";
static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":true,\"window_refresh\":true,"
    "\"command_0x83\":true,\"command_0x86\":false,"
    "\"mid_refresh_power_cut\":false,\"spi_frequency_sweep\":false,"
    "\"full_screen_global_refresh\":true,"
    "\"factory_otp_white_actions\":true,"
    "\"same_palette_hold_probe\":true,"
    "\"cross_palette_hold_probe\":false,"
    "\"ptlw_endpoint_controller_swap_probe\":true,"
    "\"busy_qualified_arm_execute_dispatch\":true";

static constexpr const char *kNvsNamespace = rlph::kNvsNamespace;
static constexpr const char *kNvsKey = "cursor_yeab1";
static constexpr const char *kVersionRoute =
    "/api/ec5/runtime-lut-ptlw-yend-ab-v1/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/runtime-lut-ptlw-yend-ab-v1/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/runtime-lut-ptlw-yend-ab-v1/status";
static constexpr const char *kReportRoute =
    "/api/ec5/runtime-lut-ptlw-yend-ab-v1/report";
static constexpr const char *kArmRoute =
    "/api/ec5/runtime-lut-ptlw-yend-ab-v1/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/runtime-lut-ptlw-yend-ab-v1/execute";

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
    "ARM_ONE_FIXED_BUSY_QUALIFIED_FACTORY_WHITE_OR_PTLW_YEND_AB_V1_ACTION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ARMED_BUSY_QUALIFIED_FACTORY_WHITE_OR_PTLW_YEND_AB_V1_ACTION_ONCE";

static constexpr const char *kWhiteFrameSha256 =
    "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d";
static constexpr const char *kWhiteDtmSha256 =
    "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158";

#define RLPH_ENDPOINT_AB_PARTIAL_ACTION(ORDINAL, DRIVER_ROLE, INDEX, PRIOR)  \
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
    {1, EpdChromaGridRole::White, "FACTORY_OTP_WHITE_HEALTH_ANCHOR", 1,
     "FACTORY_OTP_FULL_FRAME_0X11_HEALTH_ANCHOR",
     "37c81d7033925f1ad8310228c9a950d1d9d955736b9b908b5420de8ad1ebe1cc",
     "26299f00ab84004527886ecb883c4c61259c97600b0a73a28470264c8425e840",
     nullptr, kWhiteFrameSha256, kWhiteDtmSha256, kWhiteDtmSha256,
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    RLPH_ENDPOINT_AB_PARTIAL_ACTION(
        2, EpdChromaGridRole::Source, 0,
        "26299f00ab84004527886ecb883c4c61259c97600b0a73a28470264c8425e840"),
    {3, EpdChromaGridRole::White, "FACTORY_OTP_WHITE_CROSSOVER_RESET", 1,
     "FACTORY_OTP_FULL_FRAME_0X11_CROSSOVER_RESET",
     "1cc3d643edbbbea74681686a7896035324362969ae5ddfab1b86169c2f88accb",
     "24cde17c7bf5f0f4a57e20b0269febe5f311e60c60184e08f61c2b6c8360fed4",
     rlph::kActions[0].actionId, kWhiteFrameSha256, kWhiteDtmSha256,
     kWhiteDtmSha256, 0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    RLPH_ENDPOINT_AB_PARTIAL_ACTION(
        4, EpdChromaGridRole::Mid, 1,
        "24cde17c7bf5f0f4a57e20b0269febe5f311e60c60184e08f61c2b6c8360fed4"),
    {5, EpdChromaGridRole::White, "FACTORY_OTP_WHITE_RECOVERY", 1,
     "FACTORY_OTP_FULL_FRAME_0X11_RECOVERY",
     "40b59a30c51e403bfcebe7d98cb64ab7fffe656262461e84d5b91d85a28e5975",
     "adb775d90132251d19cca2b3413a4bfda336433ef84d1f3cdec257980dba0d69",
     rlph::kActions[1].actionId, kWhiteFrameSha256, kWhiteDtmSha256,
     kWhiteDtmSha256, 0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
};

#undef RLPH_ENDPOINT_AB_PARTIAL_ACTION
