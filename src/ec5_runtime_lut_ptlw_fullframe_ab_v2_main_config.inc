#include "ec5_runtime_lut_ptlw_fullframe_ab_v2_identity.inc"

namespace rlpffab = mf1750_runtime_lut_ptlw_fullframe_ab_v2;

static constexpr const char *kClassification =
    "EXPERIMENTAL_SPD1657_L535_FULLFRAME_VS_PTLW_AB_PER_ACTION_EXACT_DUAL_REV_QUALIFIED_WITH_FACTORY_OTP_WHITE_ANCHORS";
static constexpr const char *kProfileSource =
    "factory_otp_white_plus_legacy_complete_535_reference_active_global";
static constexpr const char *kIdentityRevision =
    "runtime-lut-ptlw-fullframe-ab-v2";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_RUNTIME_LUT_PTLW_FULLFRAME_AB_DEVICE_V2";
static constexpr const char *kLayoutId = rlpffab::kVariantKey;
static constexpr const char *kBuildTag = rlpffab::kBuildTag;
static constexpr const char *kBootLabel =
    "EC5 per-action REV-qualified L535 full-frame versus PTLW A/B V2";
static constexpr const char *kTestId = rlpffab::kTestId;
static constexpr const char *kCampaignId = rlpffab::kCampaignId;
static constexpr const char *kContractId = rlpffab::kContractId;
static constexpr const char *kQualifierPrerequisiteBundleId =
    "4f10da14df6ecf4df4631214a57ca6be0fb1b51df395bca0e407b59229b8968f";
static constexpr const char *kVersionKind =
    "mf1750-ec5-runtime-lut-ptlw-fullframe-ab-v2-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-runtime-lut-ptlw-fullframe-ab-v2-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-runtime-lut-ptlw-fullframe-ab-v2-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-runtime-lut-ptlw-fullframe-ab-v2-report";
static constexpr const char *kBaselineRole =
    "FACTORY_OTP_WHITE_HEALTH_ANCHOR";

static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"factory_otp_anchor_ordinal\":1,\"factory_otp_reset_ordinal\":3,"
    "\"factory_otp_recovery_ordinal\":5,"
    "\"factory_otp_white_frame_fill_byte\":17,"
    "\"factory_otp_white_frame_bytes\":307200,"
    "\"factory_otp_white_refresh_uses_shared_btst2\":true,"
    "\"anchor_established_by_firmware\":true,"
    "\"external_factory_white_anchor_required\":false,"
    "\"fresh_white_before_each_treatment\":true,"
    "\"runtime_transport_codes\":[5,7],"
    "\"runtime_code7_visible_action_reachable\":false,"
    "\"runtime_code7_full_dtm_prestage\":true,"
    "\"runtime_code7_prestage_no_refresh\":true,"
    "\"runtime_code7_prestage_bytes_per_controller\":153600,"
    "\"runtime_code7_prestage_sha256\":"
    "\"3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd\","
    "\"ptlw_command\":131,\"ptlw_payload_bytes\":9,\"ptlw_mode\":1,"
    "\"ptlw_payload_hex\":\"00b0014f00f0016701\","
    "\"ptlw_endpoint_contract\":\"xe=x+w-1;ye=y+h-1\","
    "\"window\":{\"x\":176,\"y\":240,\"width\":160,"
    "\"height\":120,\"cs1_code\":5,\"cs2_code\":5},"
    "\"treatment_a\":{\"ordinal\":2,\"ptlw\":false,"
    "\"dtm_transport\":\"FULL_CONTROLLER_COMPOSITE_NO_PTLW\","
    "\"target_dtm_bytes_per_controller\":153600,\"target_dtm_sha256\":"
    "\"352e61d15eb963fe2e1b37a07664be885ec6c8a0e1383bb3e96869fe517ca3ed\","
    "\"combined_dtm_bytes_per_controller\":307200,"
    "\"combined_dtm_sha256\":"
    "\"5f592d3f581cddb9b625a17a1507b7df4a01e16da8e8fefc94783910a33bc190\"},"
    "\"treatment_b\":{\"ordinal\":4,\"ptlw\":true,"
    "\"ptlw_writes_per_controller\":1,"
    "\"dtm_transport\":\"INCLUSIVE_PTLW_UNIFORM_CROPPED_WINDOW\","
    "\"target_dtm_bytes_per_controller\":9600,\"target_dtm_sha256\":"
    "\"b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3\","
    "\"combined_dtm_bytes_per_controller\":163200,"
    "\"combined_dtm_sha256\":"
    "\"a84b59d945284e204a5d1b3d4d7a139a3e429d6cc557ec7645cabfb1cc48146f\"},"
    "\"same_final_controller_sram\":true,"
    "\"same_logical_frame\":true,"
    "\"logical_frame_sha256\":"
    "\"c0b69123df2d5f80702d75301b453b1c46ff9fa945bea99fdcf75f298c2f9576\","
    "\"logical_frame_histogram\":[0,0,0,0,0,38400,0,576000],"
    "\"common_refresh_sequence\":[\"PON_BUSY_COMPLETE_60S_GATE\","
    "\"DRF_00_BUSY_COMPLETE_60S_GATE\","
    "\"POF_00_BUSY_COMPLETE_60S_GATE\"],"
    "\"runtime_treatment_action_stage_cdi\":false,"
    "\"runtime_treatment_action_stage_btst2\":false,"
    "\"runtime_treatment_repeat_ptlw_after_pon_busy\":false,"
    "\"command_0x86\":false,"
    "\"extra_dtm_prefix_or_suffix_byte\":false,"
    "\"packed_bpp\":4,\"cs2_position_mirrored\":false,"
    "\"runtime_lut_profile_id\":"
    "\"LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535\","
    "\"global_header_profile\":\"legacy_active\","
    "\"cs1_r20_prefix_bytes\":535,\"cs1_r20_prefix_sha256\":"
    "\"716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b\","
    "\"cs2_r20_prefix_bytes\":535,\"cs2_r20_prefix_sha256\":"
    "\"2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26\","
    "\"r21_bytes\":704,\"r21_sha256\":"
    "\"24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f\","
    "\"camera_required\":false,\"busy_idle_level_required\":1,"
    "\"ordinal_1_raw_levels_accepted\":[1],"
    "\"fresh_low_admission_forbidden\":true,"
    "\"j2_off_raw0_allowed_only_on_read_only_get_diagnostic\":true,"
    "\"later_ordinal_raw_levels_accepted\":[0,1],"
    "\"late_low_is_never_treated_as_idle\":true,"
    "\"late_low_requires_same_boot_prior_complete\":true,"
    "\"late_low_requires_prior_safe_finish_high\":true,"
    "\"late_low_requires_ram_only_firmware_eligibility\":true,"
    "\"late_pof_sleep_low_eligible_boot_default\":false,"
    "\"late_pof_sleep_low_eligible_consumed_before_qualification\":true,"
    "\"per_action_revision_qualifier_required\":true,"
    "\"unqualified_busy_zero_accepted\":false}";

static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":true,\"window_refresh\":true,"
    "\"command_0x83\":true,\"command_0x86\":false,"
    "\"mid_refresh_power_cut\":false,\"spi_frequency_sweep\":false,"
    "\"full_screen_global_refresh\":true,"
    "\"factory_otp_white_actions\":true,"
    "\"same_palette_hold_probe\":false,"
    "\"cross_palette_hold_probe\":false,"
    "\"ptlw_fullframe_ab_probe\":true,"
    "\"runtime_code7_full_dtm_prestage\":true,"
    "\"runtime_treatment_action_stage_cdi\":false,"
    "\"runtime_treatment_action_stage_btst2\":false,"
    "\"runtime_treatment_repeat_ptlw_after_pon_busy\":false,"
    "\"busy_qualified_arm_execute_dispatch\":true";

static constexpr const char *kNvsNamespace = rlpffab::kNvsNamespace;
static constexpr const char *kNvsKey = rlpffab::kNvsKey;
static constexpr const char *kVersionRoute =
    "/api/ec5/runtime-lut-ptlw-fullframe-ab-v2/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/runtime-lut-ptlw-fullframe-ab-v2/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/runtime-lut-ptlw-fullframe-ab-v2/status";
static constexpr const char *kReportRoute =
    "/api/ec5/runtime-lut-ptlw-fullframe-ab-v2/report";
static constexpr const char *kArmRoute =
    "/api/ec5/runtime-lut-ptlw-fullframe-ab-v2/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/runtime-lut-ptlw-fullframe-ab-v2/execute";

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
    "ARM_ONE_FIXED_PER_ACTION_REV_QUALIFIED_FACTORY_WHITE_OR_L535_FULLFRAME_PTLW_AB_V2_ACTION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ARMED_PER_ACTION_REV_QUALIFIED_FACTORY_WHITE_OR_L535_FULLFRAME_PTLW_AB_V2_ACTION_ONCE";

static constexpr const char *kWhiteFrameSha256 =
    "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d";
static constexpr const char *kWhiteDtmSha256 =
    "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158";

#define RLPFFAB_V2_RUNTIME_ACTION(ORDINAL, DRIVER_ROLE, INDEX, PRIOR)          \
  {                                                                          \
    ORDINAL, DRIVER_ROLE, rlpffab::kActions[INDEX].role, 1,                   \
        rlpffab::kActions[INDEX].branch,                                      \
        rlpffab::kActions[INDEX].descriptorId,                                \
        rlpffab::kActions[INDEX].actionId, PRIOR,                             \
        rlpffab::kActions[INDEX].frameSha256,                                 \
        rlpffab::kActions[INDEX].cs1DtmSha256,                                \
        rlpffab::kActions[INDEX].cs2DtmSha256,                                \
        rlpffab::kActions[INDEX].frameFnv1a,                                  \
        rlpffab::kActions[INDEX].cs1DtmFnv1a,                                 \
        rlpffab::kActions[INDEX].cs2DtmFnv1a,                                 \
        {rlpffab::kActions[INDEX].histogram[0],                               \
         rlpffab::kActions[INDEX].histogram[1],                               \
         rlpffab::kActions[INDEX].histogram[2],                               \
         rlpffab::kActions[INDEX].histogram[3],                               \
         rlpffab::kActions[INDEX].histogram[4],                               \
         rlpffab::kActions[INDEX].histogram[5],                               \
         rlpffab::kActions[INDEX].histogram[6],                               \
         rlpffab::kActions[INDEX].histogram[7]}                               \
  }

static constexpr ActionDescriptor kActions[] = {
    {1, EpdChromaGridRole::White, "FACTORY_OTP_WHITE_HEALTH_ANCHOR", 1,
     "FACTORY_OTP_FULL_FRAME_0X11_HEALTH_ANCHOR",
     "dfb473d1b8c9718b5b5ed01998e032cc600298689f227e5465031e79b3ae7947",
     "0abe5067ebcc7771684a148da4eb8b1e8cf202dbbea63961e48d7436965f5359",
     nullptr, kWhiteFrameSha256, kWhiteDtmSha256, kWhiteDtmSha256,
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    RLPFFAB_V2_RUNTIME_ACTION(
        2, EpdChromaGridRole::Source, 0,
        "0abe5067ebcc7771684a148da4eb8b1e8cf202dbbea63961e48d7436965f5359"),
    {3, EpdChromaGridRole::White, "FACTORY_OTP_WHITE_CROSSOVER_RESET", 1,
     "FACTORY_OTP_FULL_FRAME_0X11_CROSSOVER_RESET",
     "8f8e72b28dfb3d841ba948e11b07bce1e16b531cc2e38c10bcf70cccac58db09",
     "08da585051415b36c628e49c946e13a2a463213d0e251214f21ebc17e922db30",
     rlpffab::kActions[0].actionId, kWhiteFrameSha256, kWhiteDtmSha256,
     kWhiteDtmSha256, 0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    RLPFFAB_V2_RUNTIME_ACTION(
        4, EpdChromaGridRole::Mid, 1,
        "08da585051415b36c628e49c946e13a2a463213d0e251214f21ebc17e922db30"),
    {5, EpdChromaGridRole::White, "FACTORY_OTP_WHITE_RECOVERY", 1,
     "FACTORY_OTP_FULL_FRAME_0X11_RECOVERY",
     "4ccbb0ab883826dc36a6bb002d521a24e0e1cd68bbebfe237e4d6f037c86b73a",
     "88e5a34985f651c01243c78698b267710efa5e77a191d28d2f4c1f89e0d23682",
     rlpffab::kActions[1].actionId, kWhiteFrameSha256, kWhiteDtmSha256,
     kWhiteDtmSha256, 0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
};

#undef RLPFFAB_V2_RUNTIME_ACTION
