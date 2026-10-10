#include "ec5_runtime_lut_recipe_position_permutation_v1_identity.inc"

namespace rpp = mf1750_runtime_lut_recipe_position_permutation_v1;

static constexpr const char *kClassification =
    "EXPERIMENTAL_REDPINK_RECIPE_POSITION_PERMUTATION_NOT_QUALIFIED_COLOURS";
static constexpr const char *kProfileSource =
    "verified_external_factory_otp_white_then_legacy_complete_535_"
    "mixed_controller_r20_active_commented_global_sequence";
static constexpr const char *kIdentityRevision =
    "runtime-lut-redpink-recipe-position-permutation-p1-"
    "single-app-boot-flash-verify-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_REDPINK_RECIPE_POSITION_PERMUTATION_DEVICE_V1";
static constexpr const char *kLayoutId = rpp::kVariantKey;
static constexpr const char *kBuildTag = rpp::kBuildTag;
static constexpr const char *kBootLabel =
    "EC5 red/pink recipe-position permutation P1";
static constexpr const char *kTestId = rpp::kTestId;
static constexpr const char *kCampaignId = rpp::kCampaignId;
static constexpr const char *kContractId = rpp::kContractId;
static constexpr const char *kVersionKind =
    "mf1750-ec5-redpink-recipe-position-permutation-v1-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-redpink-recipe-position-permutation-v1-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-redpink-recipe-position-permutation-v1-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-redpink-recipe-position-permutation-v1-report";
static constexpr const char *kBaselineRole =
    "VERIFIED_EXTERNAL_FACTORY_OTP_CLEAN_WHITE_PRECONDITION";
static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"candidate_cells_per_controller\":64,"
    "\"candidate_cells_total_observations\":128,\"unique_recipes\":64,"
    "\"duplicate_recipe_across_controllers\":true,"
    "\"controller_color_equivalence_claimed\":false,"
    "\"mixed_controller_r20_intentionally_preserved\":true,"
    "\"controller_payload_binding\":"
    "\"CS1_ACTIVE535_AND_CS2_COMMENTED535_FIXED\","
    "\"grid_rows\":8,\"grid_columns_per_controller\":8,"
    "\"grid_x0_local\":20,\"grid_y0\":40,"
    "\"grid_x1_local_exclusive\":492,\"grid_y1_exclusive\":560,"
    "\"cell_width\":52,\"cell_height\":58,\"gap_x\":8,\"gap_y\":8,"
    "\"permutation_id\":\"P1_SOURCE_SHIFT3_MIDDLE_REVERSE\","
    "\"source_physical_to_code\":\"(column+3)%8\","
    "\"middle_physical_to_code\":\"7-row\","
    "\"fixed_target\":\"active_code_0\","
    "\"spatial_dither\":false,\"runtime_code7_used_as_white\":false,"
    "\"external_factory_white_precondition_required\":true,"
    "\"factory_otp_white_ordinal\":4,"
    "\"palette_source_sequence\":[\"L535_RUNTIME\",\"L535_RUNTIME\","
    "\"L535_RUNTIME\",\"FACTORY_OTP\"],"
    "\"global_header_sequence\":[\"active\",\"commented\","
    "\"active\",null],"
    "\"one_visible_refresh_per_ordinal\":true,"
    "\"device_enforced_same_boot\":true,"
    "\"campaign_boot_binding_key\":\"boot_rpp1\","
    "\"direct_exact_post_resume_after_reboot\":false,"
    "\"skip_to_factory_white_allowed\":false,"
    "\"ptlw_command_issued\":false,\"cropped_dtm\":false,"
    "\"all_action_dtm_transport\":\"packed_frame_per_controller\","
    "\"active_global_header_sha256\":"
    "\"48a53562060e9c822334a73f900dbd1323fd3fe096576ef75663b64216e275c8\","
    "\"commented_global_header_sha256\":"
    "\"473a4bf39f819aa6c9ef3dd6caeb637c20481485339c9b01ac49434c1032608f\","
    "\"cs1_r20_prefix_bytes\":535,\"cs1_r20_prefix_sha256\":"
    "\"716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b\","
    "\"cs2_r20_prefix_bytes\":535,\"cs2_r20_prefix_sha256\":"
    "\"2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26\","
    "\"r21_bytes\":704,\"r21_sha256\":"
    "\"24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f\"}";
static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":false,\"window_refresh\":false,"
    "\"command_0x83\":false,\"command_0x86\":false,"
    "\"unknown_commands\":false,\"mid_refresh_power_cut\":false,"
    "\"spi_frequency_sweep\":false,\"full_screen_global_refresh\":true,"
    "\"same_palette_hold_probe\":false,\"cross_palette_hold_probe\":false,"
    "\"local_hold_claimed\":false,"
    "\"recipe_position_permutation\":true,"
    "\"qualified_new_colours\":0,"
    "\"recipe_linked_candidates_only\":true,"
    "\"human_observation_gate_after_every_action\":true,"
    "\"busy_qualified_arm_execute_dispatch\":true,"
    "\"external_factory_white_precondition_required\":true,"
    "\"one_visible_refresh_per_ordinal\":true,"
    "\"runtime_code7_used_as_white\":false";

static constexpr const char *kNvsNamespace = rpp::kNvsNamespace;
static constexpr const char *kNvsKey = "cursor_rpp1";
static constexpr const char *kNvsBootKey = rpp::kNvsBootKey;
static constexpr const char *kVersionRoute =
    "/api/ec5/redpink-recipe-permutation-v1/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/redpink-recipe-permutation-v1/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/redpink-recipe-permutation-v1/status";
static constexpr const char *kReportRoute =
    "/api/ec5/redpink-recipe-permutation-v1/report";
static constexpr const char *kArmRoute =
    "/api/ec5/redpink-recipe-permutation-v1/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/redpink-recipe-permutation-v1/execute";

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
    "ARM_ONE_FIXED_REDPINK_RECIPE_POSITION_PERMUTATION_ACTION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ARMED_REDPINK_RECIPE_POSITION_PERMUTATION_ACTION_ONCE";

#define RPP_ACTION(ORDINAL, DRIVER_ROLE, ROLE, BRANCH, DESCRIPTOR, ACTION, \
                   PRIOR, FRAME_SHA, DTM_SHA, FRAME_FNV, DTM_FNV, H0, H1, \
                   H2, H3, H4, H5, H6, H7)                              \
  {                                                                     \
    ORDINAL, DRIVER_ROLE, ROLE, 1, BRANCH, DESCRIPTOR, ACTION, PRIOR,    \
        FRAME_SHA, DTM_SHA, DTM_SHA, FRAME_FNV, DTM_FNV, DTM_FNV,       \
        {H0, H1, H2, H3, H4, H5, H6, H7}                               \
  }

static constexpr ActionDescriptor kActions[] = {
    RPP_ACTION(
        1, EpdChromaGridRole::Source,
        "PERMUTED_SOURCE_GRID_ACTIVE_SHIFT3",
        "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_RECIPE_PERMUTATION_V1_PERMUTED_SOURCE_GRID_ACTIVE_SHIFT3",
        "57af72e88ad43fd80f29243ed475d6571c01c66c46cadc4ee8baf91aa5a92855",
        "afd5f9834cedb536ee50b62fd80f1a1b038786f8512e9594c34a515ba280cd00",
        nullptr,
        "dd4ee3f40ac007a778f4d041d6e5a219186a5d1e5c1bf5aca31cf510754dafd6",
        "edc0b5673c53be68b3ad2b74e376da5d6e9539870352c7630aac6d232b9e0508",
        0x58900DC5UL, 0x19E62DC5UL, 48256, 48256, 48256, 48256,
        48256, 48256, 48256, 276608),
    RPP_ACTION(
        2, EpdChromaGridRole::Mid,
        "PERMUTED_MIDDLE_GRID_COMMENTED_REVERSE",
        "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_RECIPE_PERMUTATION_V1_PERMUTED_MIDDLE_GRID_COMMENTED_REVERSE",
        "636c8f05f2e90e80ab779e977c9805a3f90f701dbb93f44d6ccde5b46affd677",
        "c75a829ed8116c228913525fff87db5fac41e127dc45013ee86386e9ee65dcbf",
        "afd5f9834cedb536ee50b62fd80f1a1b038786f8512e9594c34a515ba280cd00",
        "12b96bf001bee93f41417cfecdcd78a8941a4effbcd9a5d10c9f527e6bdf075b",
        "29c526661cb9e5a26fccee78de75adb1e4921f32c3cd8c9d0652418314de6b1b",
        0x5B663FC5UL, 0x9F3BCA45UL, 48256, 48256, 48256, 48256,
        48256, 48256, 48256, 276608),
    RPP_ACTION(
        3, EpdChromaGridRole::Target,
        "PERMUTED_FIXED_TARGET_ACTIVE_CODE0",
        "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_RECIPE_PERMUTATION_V1_PERMUTED_FIXED_TARGET_ACTIVE_CODE0",
        "f798106e2bbd5c130876e8d8c8919de45c086d16cc5398f39ea3f3b45e6f17d8",
        "8a9a17c4e69b20278b513965cde248e1e6036dceee8943e269ed0693d216b4c9",
        "c75a829ed8116c228913525fff87db5fac41e127dc45013ee86386e9ee65dcbf",
        "9c771f6a89f72bdd64c38ddd99489accad9c5ed554d1841740517ea1100f7af4",
        "f36eeda01f7cdd5cda9147cece0a543009a217235c38b1ab3f636f24b2e4f4aa",
        0x2CC36BC5UL, 0x4FA004C5UL, 386048, 0, 0, 0, 0, 0, 0,
        228352),
    RPP_ACTION(
        4, EpdChromaGridRole::White, "FACTORY_OTP_WHITE_RECOVERY",
        "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_RECIPE_PERMUTATION_V1_FACTORY_OTP_WHITE_RECOVERY",
        "4dd63a9e7d1abec4d656a5cf54446634454a70b6468d676f31ad1020cbb26a0d",
        "4d4b247bc8d398462102b3d8cabd1bf29970bda89cfb3d8f05b368f628000a99",
        "8a9a17c4e69b20278b513965cde248e1e6036dceee8943e269ed0693d216b4c9",
        "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
        "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
        0x13340DC5UL, 0xB7A855C5UL, 0, 614400, 0, 0, 0, 0, 0, 0),
};

#undef RPP_ACTION
