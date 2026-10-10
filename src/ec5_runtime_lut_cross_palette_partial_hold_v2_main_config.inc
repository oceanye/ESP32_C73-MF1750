#include "ec5_runtime_lut_cross_palette_partial_hold_v2_identity.inc"

namespace rlcxph2 = mf1750_runtime_lut_cross_palette_partial_hold_v2;

static constexpr const char *kClassification =
    "EXPERIMENTAL_SPD1657_L535_CROSS_GLOBAL_HEADER_PARTIAL_HOLD_CLEAN_PTLW_V2_PER_ACTION_EXACT_DUAL_REV_QUALIFIED_WITH_FACTORY_OTP_WHITE_ANCHORS";
static constexpr const char *kProfileSource =
    "factory_otp_white_plus_legacy_complete_535_reference_active_and_commented_globals";
static constexpr const char *kIdentityRevision =
    "runtime-lut-cross-palette-partial-hold-v2";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_DEVICE_V2";
static constexpr const char *kLayoutId = rlcxph2::kVariantKey;
static constexpr const char *kBuildTag = rlcxph2::kBuildTag;
static constexpr const char *kBootLabel =
    "EC5 clean-PTLW cross-profile partial HOLD V2";
static constexpr const char *kTestId = rlcxph2::kTestId;
static constexpr const char *kCampaignId = rlcxph2::kCampaignId;
static constexpr const char *kContractId = rlcxph2::kContractId;
static constexpr const char *kQualifierPrerequisiteBundleId =
    "4f10da14df6ecf4df4631214a57ca6be0fb1b51df395bca0e407b59229b8968f";
static constexpr const char *kVersionKind =
    "mf1750-ec5-runtime-lut-cross-palette-partial-hold-v2-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-runtime-lut-cross-palette-partial-hold-v2-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-runtime-lut-cross-palette-partial-hold-v2-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-runtime-lut-cross-palette-partial-hold-v2-report";
static constexpr const char *kBaselineRole =
    "FACTORY_OTP_WHITE_HEALTH_ANCHOR";

static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"factory_otp_anchor_ordinal\":1,\"factory_otp_recovery_ordinal\":5,"
    "\"factory_otp_white_frame_fill_byte\":17,"
    "\"factory_otp_white_frame_bytes\":307200,"
    "\"factory_otp_white_refresh_uses_shared_btst2\":true,"
    "\"anchor_established_by_firmware\":true,"
    "\"external_factory_white_anchor_required\":false,"
    "\"runtime_transport_codes\":[5,6,3],"
    "\"runtime_code7_visible_action_reachable\":false,"
    "\"runtime_code7_full_dtm_prestage\":true,"
    "\"runtime_code7_prestage_no_refresh\":true,"
    "\"runtime_code7_prestage_bytes_per_controller\":153600,"
    "\"runtime_code7_prestage_sha256\":"
    "\"3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd\","
    "\"ptlw_command\":131,\"ptlw_payload_bytes\":9,\"ptlw_mode\":1,"
    "\"ptlw_endpoint_contract\":\"xe=x+w-1;ye=y+h-1\","
    "\"ptlw_payloads_hex\":[\"003000cf004000b701\","
    "\"013001cf00f0016701\",\"003000cf01a0021701\"],"
    "\"windows\":["
    "{\"x\":48,\"y\":64,\"width\":160,\"height\":120,"
    "\"cs1_code\":5,\"cs2_code\":5},"
    "{\"x\":304,\"y\":240,\"width\":160,\"height\":120,"
    "\"cs1_code\":6,\"cs2_code\":6},"
    "{\"x\":48,\"y\":416,\"width\":160,\"height\":120,"
    "\"cs1_code\":3,\"cs2_code\":3}],"
    "\"windows_disjoint\":true,\"cs2_position_mirrored\":false,"
    "\"runtime_actions\":["
    "{\"ordinal\":2,\"global_header\":\"active\",\"code\":5,"
    "\"ptlw_writes_per_controller\":1,"
    "\"target_dtm_sha256\":"
    "\"b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3\","
    "\"combined_dtm_sha256\":"
    "\"a84b59d945284e204a5d1b3d4d7a139a3e429d6cc557ec7645cabfb1cc48146f\"},"
    "{\"ordinal\":3,\"global_header\":\"commented\",\"code\":6,"
    "\"ptlw_writes_per_controller\":1,"
    "\"target_dtm_sha256\":"
    "\"3102928873c21656da937b86e5821d4cf5c6d8ce664daba4db714447ac805d70\","
    "\"combined_dtm_sha256\":"
    "\"0292d1cc5fd192cb91b00fb180305aca8dfa996a5c2de89536f8de3599fb5cef\"},"
    "{\"ordinal\":4,\"global_header\":\"active\",\"code\":3,"
    "\"ptlw_writes_per_controller\":1,"
    "\"target_dtm_sha256\":"
    "\"6455e53da64c1ffd5644ab3b85d50d51b72ce699666cb7467d821e29e5732faa\","
    "\"combined_dtm_sha256\":"
    "\"2a8e8b98eac99a8fc8b22f06b9aa60f0056201dafcbb240a1ccd489b1a896a38\"}],"
    "\"runtime_target_dtm_bytes_per_controller\":9600,"
    "\"runtime_combined_dtm_bytes_per_controller\":163200,"
    "\"runtime_dtm_transport\":"
    "\"FULL_CODE7_PRESTAGE_THEN_INCLUSIVE_PTLW_UNIFORM_CROP\","
    "\"common_runtime_refresh_sequence\":["
    "\"PON_BUSY_COMPLETE_60S_GATE\","
    "\"DRF_00_BUSY_COMPLETE_60S_GATE\","
    "\"POF_00_BUSY_COMPLETE_60S_GATE\"],"
    "\"runtime_treatment_action_stage_cdi\":false,"
    "\"runtime_treatment_action_stage_btst2\":false,"
    "\"runtime_treatment_repeat_ptlw_after_pon_busy\":false,"
    "\"command_0x86\":false,\"extra_dtm_prefix_or_suffix_byte\":false,"
    "\"runtime_lut_profile_id\":"
    "\"ACTIVE_CODE5_TO_COMMENTED_CODE6_TO_ACTIVE_CODE3__"
    "CS1_ACTIVE535__CS2_COMMENTED535__CLEAN_PTLW_V2\","
    "\"global_header_profile_sequence\":[null,\"active\","
    "\"commented\",\"active\",null],"
    "\"global_header_switching\":true,"
    "\"cs1_r20_prefix_bytes\":535,\"cs1_r20_prefix_sha256\":"
    "\"716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b\","
    "\"cs2_r20_prefix_bytes\":535,\"cs2_r20_prefix_sha256\":"
    "\"2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26\","
    "\"r21_bytes\":704,\"r21_sha256\":"
    "\"24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f\","
    "\"sequential_hold_observation_required\":true,"
    "\"human_observation_gate_after_each_action\":true,"
    "\"busy_idle_level_required\":1,\"ordinal_1_raw_levels_accepted\":[1],"
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
    "\"cross_palette_hold_probe\":true,"
    "\"ptlw_fullframe_ab_probe\":false,"
    "\"runtime_code7_full_dtm_prestage\":true,"
    "\"runtime_treatment_action_stage_cdi\":false,"
    "\"runtime_treatment_action_stage_btst2\":false,"
    "\"runtime_treatment_repeat_ptlw_after_pon_busy\":false,"
    "\"busy_qualified_arm_execute_dispatch\":true";

static constexpr const char *kNvsNamespace = rlcxph2::kNvsNamespace;
static constexpr const char *kNvsKey = rlcxph2::kNvsKey;
static constexpr const char *kVersionRoute =
    "/api/ec5/runtime-lut-cross-palette-partial-hold-v2/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/runtime-lut-cross-palette-partial-hold-v2/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/runtime-lut-cross-palette-partial-hold-v2/status";
static constexpr const char *kReportRoute =
    "/api/ec5/runtime-lut-cross-palette-partial-hold-v2/report";
static constexpr const char *kArmRoute =
    "/api/ec5/runtime-lut-cross-palette-partial-hold-v2/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/runtime-lut-cross-palette-partial-hold-v2/execute";

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
    "ARM_ONE_FIXED_PER_ACTION_REV_QUALIFIED_FACTORY_WHITE_OR_L535_CROSS_PALETTE_PARTIAL_HOLD_V2_ACTION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ARMED_PER_ACTION_REV_QUALIFIED_FACTORY_WHITE_OR_L535_CROSS_PALETTE_PARTIAL_HOLD_V2_ACTION_ONCE";

static constexpr const char *kWhiteFrameSha256 =
    "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d";
static constexpr const char *kWhiteDtmSha256 =
    "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158";

#define RLCXPH2_RUNTIME_ACTION(ORDINAL, DRIVER_ROLE, INDEX, PRIOR)            \
  {                                                                          \
    ORDINAL, DRIVER_ROLE, rlcxph2::kActions[INDEX].role, 1,                   \
        rlcxph2::kActions[INDEX].branch,                                      \
        rlcxph2::kActions[INDEX].descriptorId,                                \
        rlcxph2::kActions[INDEX].actionId, PRIOR,                             \
        rlcxph2::kActions[INDEX].frameSha256,                                 \
        rlcxph2::kActions[INDEX].cs1DtmSha256,                                \
        rlcxph2::kActions[INDEX].cs2DtmSha256,                                \
        rlcxph2::kActions[INDEX].frameFnv1a,                                  \
        rlcxph2::kActions[INDEX].cs1DtmFnv1a,                                 \
        rlcxph2::kActions[INDEX].cs2DtmFnv1a,                                 \
        {rlcxph2::kActions[INDEX].histogram[0],                               \
         rlcxph2::kActions[INDEX].histogram[1],                               \
         rlcxph2::kActions[INDEX].histogram[2],                               \
         rlcxph2::kActions[INDEX].histogram[3],                               \
         rlcxph2::kActions[INDEX].histogram[4],                               \
         rlcxph2::kActions[INDEX].histogram[5],                               \
         rlcxph2::kActions[INDEX].histogram[6],                               \
         rlcxph2::kActions[INDEX].histogram[7]}                               \
  }

static constexpr ActionDescriptor kActions[] = {
    {1, EpdChromaGridRole::White, "FACTORY_OTP_WHITE_HEALTH_ANCHOR", 1,
     "FACTORY_OTP_FULL_FRAME_0X11_HEALTH_ANCHOR",
     "87e3cdb030c71be006e54ff4663bf55d854d2acf9f3b06edc8846e91e01d3de5",
     "21c44e19182683611ece953b1744012319ad6570540eff583d1ca3cac187068f",
     nullptr, kWhiteFrameSha256, kWhiteDtmSha256, kWhiteDtmSha256,
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    RLCXPH2_RUNTIME_ACTION(
        2, EpdChromaGridRole::Source, 0,
        "21c44e19182683611ece953b1744012319ad6570540eff583d1ca3cac187068f"),
    RLCXPH2_RUNTIME_ACTION(3, EpdChromaGridRole::Mid, 1,
                          rlcxph2::kActions[0].actionId),
    RLCXPH2_RUNTIME_ACTION(4, EpdChromaGridRole::Target, 2,
                          rlcxph2::kActions[1].actionId),
    {5, EpdChromaGridRole::White, "FACTORY_OTP_WHITE_RECOVERY", 1,
     "FACTORY_OTP_FULL_FRAME_0X11_RECOVERY",
     "ab913fc1d92e65b08a4b9919d036105d78446cc54256d3462a404393b0ff756f",
     "5097983e4887425fb4a1ca9932a5d43fa59ae323b779876c04d81844b50f2c61",
     rlcxph2::kActions[2].actionId, kWhiteFrameSha256, kWhiteDtmSha256,
     kWhiteDtmSha256, 0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
};

#undef RLCXPH2_RUNTIME_ACTION
