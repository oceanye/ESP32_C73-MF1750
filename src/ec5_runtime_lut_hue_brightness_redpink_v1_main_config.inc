#include "ec5_runtime_lut_hue_brightness_redpink_v1_identity.inc"

namespace rlhbrp = mf1750_runtime_lut_hue_brightness_redpink_v1;

static constexpr const char *kClassification =
    "EXPERIMENTAL_L535_REDPINK_HISTORY_BRIGHTNESS_CANDIDATES_NOT_QUALIFIED_LEVELS";
static constexpr const char *kProfileSource =
    "factory_otp_white_and_legacy_complete_535_reference_active_and_commented_global_headers";
static constexpr const char *kIdentityRevision =
    "runtime-lut-target-hue-redpink-brightness-factory-white-same-boot-v2";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_TARGET_HUE_REDPINK_BRIGHTNESS_DEVICE_V1";
static constexpr const char *kLayoutId = rlhbrp::kVariantKey;
static constexpr const char *kBuildTag = rlhbrp::kBuildTag;
static constexpr const char *kBootLabel =
    "EC5 target-hue red/pink brightness-candidate ladder";
static constexpr const char *kTestId = rlhbrp::kTestId;
static constexpr const char *kCampaignId = rlhbrp::kCampaignId;
static constexpr const char *kContractId = rlhbrp::kContractId;
static constexpr const char *kVersionKind =
    "mf1750-ec5-target-hue-redpink-brightness-v1-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-target-hue-redpink-brightness-v1-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-target-hue-redpink-brightness-v1-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-target-hue-redpink-brightness-v1-report";
static constexpr const char *kBaselineRole =
    "FACTORY_OTP_WHITE_HEALTH_ANCHOR";
static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"candidate_cells_per_controller\":64,"
    "\"candidate_cells_total_observations\":128,"
    "\"unique_recipes\":64,"
    "\"duplicate_recipe_across_controllers\":true,"
    "\"controller_color_equivalence_claimed\":false,"
    "\"shared_red_or_pink_hue_claimed\":false,"
    "\"controller_payload_binding\":"
    "\"CS1_ACTIVE535_AND_CS2_COMMENTED535_FIXED\","
    "\"cs2_position_mirrored\":false,"
    "\"grid_rows\":8,\"grid_columns_per_controller\":8,"
    "\"grid_x0_local\":20,\"grid_y0\":40,"
    "\"grid_x1_local_exclusive\":492,\"grid_y1_exclusive\":560,"
    "\"cell_width\":52,\"cell_height\":58,\"gap_x\":8,\"gap_y\":8,"
    "\"row_axis\":\"commented_middle_code_0_to_7\","
    "\"column_axis\":\"active_source_code_0_to_7\","
    "\"horizontal_comparison_group\":"
    "\"eight_adjacent_source_histories_same_middle_and_target\","
    "\"target_hue_id\":"
    "\"ACTIVE_CODE0_CS2_RED_CS1_OLIVE_YELLOWGREEN_CONTROLLER_SPECIFIC_UNCALIBRATED\","
    "\"target_global_header\":\"active\","
    "\"target_transport_code\":0,\"target_repeat_count\":2,"
    "\"target_hue_catalog_id\":"
    "\"94eabf2d00b2f0e90e86201f54923029b25182c140c757023b77f8f302165fd8\","
    "\"cs1_target_visual_candidate\":\"olive/yellow-green\","
    "\"cs2_target_visual_candidate\":\"red\","
    "\"selection_not_guess\":true,\"qualified_brightness_levels\":0,"
    "\"brightness_candidates_only\":true,\"spatial_dither\":false,"
    "\"separator_gutter_history_interaction_qualified\":false,"
    "\"runtime_code7_semantics\":"
    "\"unqualified_separator_and_background_transport_code_not_white\","
    "\"runtime_code7_used_as_white\":false,"
    "\"factory_otp_white_ordinals\":[1,6],"
    "\"factory_otp_white_fill_byte\":17,"
    "\"palette_source_sequence\":[\"FACTORY_OTP\",\"L535_RUNTIME\","
    "\"L535_RUNTIME\",\"L535_RUNTIME\",\"L535_RUNTIME\",\"FACTORY_OTP\"],"
    "\"global_header_sequence\":[null,\"active\",\"commented\","
    "\"active\",\"active\",null],"
    "\"target_repeat_separate_manual_decision_action\":true,"
    "\"target_repeat_automatic_dispatch\":false,"
    "\"skip_target_repeat_within_main_allowed\":false,"
    "\"same_boot_prior_complete_required\":true,"
    "\"device_enforced_same_boot\":true,"
    "\"campaign_boot_nonce_persisted_before_any_action\":true,"
    "\"campaign_boot_binding_key\":\"boot_rpb1\","
    "\"direct_exact_post_resume_after_reboot\":false,"
    "\"main_campaign_resume_after_containment\":false,"
    "\"skip_to_factory_white_allowed\":false,"
    "\"ptlw_command_issued\":false,\"cropped_dtm\":false,"
    "\"all_action_dtm_transport\":\"packed_frame_per_controller\","
    "\"cs1_r20_prefix_bytes\":535,"
    "\"cs1_r20_prefix_sha256\":"
    "\"716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b\","
    "\"cs2_r20_prefix_bytes\":535,"
    "\"cs2_r20_prefix_sha256\":"
    "\"2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26\","
    "\"r21_bytes\":704,\"r21_sha256\":"
    "\"24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f\"}";
static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":false,\"window_refresh\":false,"
    "\"command_0x83\":false,\"command_0x86\":false,"
    "\"unknown_commands\":false,\"mid_refresh_power_cut\":false,"
    "\"spi_frequency_sweep\":false,\"full_screen_global_refresh\":true,"
    "\"same_palette_hold_probe\":false,\"cross_palette_hold_probe\":false,"
    "\"local_hold_claimed\":false,\"history_brightness_screening\":true,"
    "\"target_repeat_stability_probe\":true,"
    "\"target_repeat_operator_decision_required\":true,"
    "\"ordinal4_clear_visible_hit_required_for_repeat\":true,"
    "\"ordinal4_no_visible_difference_seals_main\":true,"
    "\"main_campaign_resume_after_containment\":false,"
    "\"device_enforced_same_boot\":true,"
    "\"brightness_candidates_only\":true,\"qualified_brightness_levels\":0,"
    "\"human_observation_gate_after_every_action\":true,"
    "\"busy_qualified_arm_execute_dispatch\":true,"
    "\"runtime_code7_used_as_white\":false";

static constexpr const char *kNvsNamespace = rlhbrp::kNvsNamespace;
static constexpr const char *kNvsKey = "cursor_rpb1";
static constexpr const char *kNvsBootKey = rlhbrp::kNvsBootKey;
static constexpr const char *kVersionRoute =
    "/api/ec5/target-hue-redpink-brightness-v1/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/target-hue-redpink-brightness-v1/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/target-hue-redpink-brightness-v1/status";
static constexpr const char *kReportRoute =
    "/api/ec5/target-hue-redpink-brightness-v1/report";
static constexpr const char *kArmRoute =
    "/api/ec5/target-hue-redpink-brightness-v1/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/target-hue-redpink-brightness-v1/execute";

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
    "ARM_ONE_FIXED_REDPINK_HUE_BRIGHTNESS_CANDIDATE_ACTION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ARMED_REDPINK_HUE_BRIGHTNESS_CANDIDATE_ACTION_ONCE";

#define RLHBRP_ACTION(ORDINAL, DRIVER_ROLE, ROLE, BRANCH, DESCRIPTOR, ACTION, \
                      PRIOR, FRAME_SHA, DTM_SHA, FRAME_FNV, DTM_FNV, H0, H1, \
                      H2, H3, H4, H5, H6, H7)                                \
  {                                                                          \
    ORDINAL, DRIVER_ROLE, ROLE, 1, BRANCH, DESCRIPTOR, ACTION, PRIOR,         \
        FRAME_SHA, DTM_SHA, DTM_SHA, FRAME_FNV, DTM_FNV, DTM_FNV,            \
        {H0, H1, H2, H3, H4, H5, H6, H7}                                    \
  }

static constexpr ActionDescriptor kActions[] = {
    RLHBRP_ACTION(
        1, EpdChromaGridRole::White, "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
        "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_V1_FACTORY_OTP_WHITE_HEALTH_ANCHOR",
        "01d9bbd297aace51e98a26eeeaa078f306fa9defae9dd5c4170ea8afb00a0b60",
        "c2182c1a5b2556cea046f165f329bc0f92d7354ad80d93f4bddb5ffb521a372e",
        nullptr,
        "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
        "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
        0x13340DC5UL, 0xB7A855C5UL, 0, 614400, 0, 0, 0, 0, 0, 0),
    RLHBRP_ACTION(
        2, EpdChromaGridRole::Source, "REDPINK_SOURCE_GRID_ACTIVE",
        "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_V1_REDPINK_SOURCE_GRID_ACTIVE",
        "027cdd2bb2dc125e4e84154dae62af05a257bd4459750c7de89bb474a75c5bcb",
        "03a4f94f6f004faf52163b20da3f2ca114980e638373c2a609e16103ee615f3b",
        "c2182c1a5b2556cea046f165f329bc0f92d7354ad80d93f4bddb5ffb521a372e",
        "fe420d9010e95b0347e7c468d18fb2283f4d5ede420a1ca811dafe9a1ebab853",
        "8aae76f672eb482772dd40b53840f70171db753477bb887cffb6b80dbb94dc74",
        0x5A43EDC5UL, 0x1E3045C5UL, 48256, 48256, 48256, 48256,
        48256, 48256, 48256, 276608),
    RLHBRP_ACTION(
        3, EpdChromaGridRole::Mid, "REDPINK_MIDDLE_GRID_COMMENTED",
        "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_V1_REDPINK_MIDDLE_GRID_COMMENTED",
        "3810a6891a1eda112a29d9cb7703913606e7a435ad7ef1f490027c33d09f0695",
        "e570b76426768a48b8a6543591b2a9ccc47022d017be8440c5445e88111ab665",
        "03a4f94f6f004faf52163b20da3f2ca114980e638373c2a609e16103ee615f3b",
        "5d9d3fa7a873128c12ee4e2ab55e88ddf4e2388b6efd90a041c48b05f51e2dc3",
        "bfed84706002d390db5e5cc69b5111304e8fd5f6cdd251f6092229af3bc09f81",
        0x199F2BC5UL, 0xA0586A45UL, 48256, 48256, 48256, 48256,
        48256, 48256, 48256, 276608),
    RLHBRP_ACTION(
        4, EpdChromaGridRole::Target,
        "REDPINK_FIXED_TARGET_ACTIVE_CODE0",
        "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_V1_REDPINK_FIXED_TARGET_ACTIVE_CODE0",
        "638edabb02aaf4a87b221c66e10a64bc37442e4f9368a22e58a2888ace0b24ee",
        "691b4feec6b9e0a196913ad0470fdb143009da44449f70a9ca7c2314dc81e975",
        "e570b76426768a48b8a6543591b2a9ccc47022d017be8440c5445e88111ab665",
        "9c771f6a89f72bdd64c38ddd99489accad9c5ed554d1841740517ea1100f7af4",
        "f36eeda01f7cdd5cda9147cece0a543009a217235c38b1ab3f636f24b2e4f4aa",
        0x2CC36BC5UL, 0x4FA004C5UL, 386048, 0, 0, 0, 0, 0, 0,
        228352),
    RLHBRP_ACTION(
        5, EpdChromaGridRole::Target,
        "REDPINK_FIXED_TARGET_REPEAT_ACTIVE_CODE0",
        "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_V1_REDPINK_FIXED_TARGET_REPEAT_ACTIVE_CODE0",
        "79b0ccb13a172a3d584038ec54345aa4bef88b830346d8c469e89e7585a40f7f",
        "394db520ff69acebe138b2de8fc7f0ab6a2eff2220bc896d7fccdbe7a7607624",
        "691b4feec6b9e0a196913ad0470fdb143009da44449f70a9ca7c2314dc81e975",
        "9c771f6a89f72bdd64c38ddd99489accad9c5ed554d1841740517ea1100f7af4",
        "f36eeda01f7cdd5cda9147cece0a543009a217235c38b1ab3f636f24b2e4f4aa",
        0x2CC36BC5UL, 0x4FA004C5UL, 386048, 0, 0, 0, 0, 0, 0,
        228352),
    RLHBRP_ACTION(
        6, EpdChromaGridRole::White, "FACTORY_OTP_WHITE_RECOVERY",
        "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_V1_FACTORY_OTP_WHITE_RECOVERY",
        "e9d82bf6006175a9deac244b2a3f1aeda498146ebd328510e93a80fa6e523552",
        "2bd9bc1802da049e738c1f76821c6adcb2a1361fecdebe5c33d16851e1bad12b",
        "394db520ff69acebe138b2de8fc7f0ab6a2eff2220bc896d7fccdbe7a7607624",
        "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
        "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
        0x13340DC5UL, 0xB7A855C5UL, 0, 614400, 0, 0, 0, 0, 0, 0),
};

#undef RLHBRP_ACTION
