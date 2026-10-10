#include "ec5_runtime_lut_luma_gray_v1_identity.inc"

namespace rllg = mf1750_runtime_lut_luma_gray_v1;

static constexpr const char *kClassification =
    "EXPERIMENTAL_CAMERA_RELATIVE_LUMA_GRAY_CANDIDATES_ZERO_QUALIFIED_GRAY_LEVELS";
static constexpr const char *kProfileSource =
    "factory_otp_white_and_legacy_complete_535_active_commented_headers";
static constexpr const char *kIdentityRevision =
    "runtime-lut-luma-gray-two-page-source-anchor-single-app-boot-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_LUMA_GRAY_EXPLORATORY_DEVICE_V1";
static constexpr const char *kLayoutId = rllg::kVariantKey;
static constexpr const char *kBuildTag = rllg::kBuildTag;
static constexpr const char *kBootLabel = "EC5 LUMA-GRAY exploratory ladder";
static constexpr const char *kTestId = rllg::kTestId;
static constexpr const char *kCampaignId = rllg::kCampaignId;
static constexpr const char *kContractId = rllg::kContractId;
static constexpr const char *kVersionKind = "mf1750-ec5-luma-gray-v1-version";
static constexpr const char *kManifestKind = "mf1750-ec5-luma-gray-v1-manifest";
static constexpr const char *kStatusKind = "mf1750-ec5-luma-gray-v1-status";
static constexpr const char *kReportKind = "mf1750-ec5-luma-gray-v1-report";
static constexpr const char *kBaselineRole = "FACTORY_OTP_WHITE_HEALTH_ANCHOR";

static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"controller_results_evaluated_independently\":true,"
    "\"controller_color_equivalence_claimed\":false,"
    "\"pages\":2,\"recipes_per_page\":16,\"total_recipes\":32,"
    "\"candidate_cells_per_controller_per_page\":64,"
    "\"repeats_per_recipe_per_controller\":4,"
    "\"required_valid_repeats\":\"4_of_4\","
    "\"grid_rows\":8,\"grid_columns_per_controller\":8,"
    "\"grid_x0_local\":20,\"grid_y0\":40,"
    "\"grid_x1_local_exclusive\":492,\"grid_y1_exclusive\":560,"
    "\"cell_width\":52,\"cell_height\":58,\"gap_x\":8,\"gap_y\":8,"
    "\"source_anchor_codes\":[3,7],"
    "\"source_anchor_colour_names_claimed\":false,"
    "\"factory_otp_per_cell_black_white_source_implemented\":false,"
    "\"source_model_change\":\"active_L535_code3_code7_transport_anchors_replace_unproven_factory_OTP_per_cell_black_white\","
    "\"page_target_codes\":[3,7],\"middle_codes\":[0,1,2,3,4,5,6,7],"
    "\"factory_otp_white_ordinals\":[1,5],"
    "\"main_campaign_contains_final_recovery\":false,"
    "\"independent_fresh_factory_otp_white_containment_required\":true,"
    "\"true_neutral_gray_claimed\":false,\"qualified_gray_levels\":0,"
    "\"qualified_brightness_levels\":0,\"candidate_only\":true,"
    "\"camera_relative_gray_only_without_coplanar_neutral_card\":true,"
    "\"position_dispersion_p95_delta_e76_max\":6.6032,"
    "\"gray_candidate_relative_neutral_locus_ab_distance_max\":8.0,"
    "\"gray_candidate_repeats_passing\":\"3_of_4\","
    "\"gray_candidate_lstar_min\":15.0,\"gray_candidate_lstar_max\":85.0,"
    "\"minimum_adjacent_candidate_delta_lstar\":8.0,"
    "\"qualification_relative_neutral_locus_ab_distance_max\":5.0,"
    "\"qualification_target_repeat_delta_e76_max\":6.6032,"
    "\"qualification_fresh_runs\":3,"
    "\"qualification_observation_seconds\":[5,60,600],"
    "\"qualification_performed_by_this_campaign\":false,"
    "\"spatial_dither\":false,\"spatial_mixing\":false,"
    "\"ptlw_command_issued\":false,\"cropped_dtm\":false,"
    "\"all_action_dtm_transport\":\"packed_frame_per_controller\","
    "\"global_header_sequence\":[null,\"active\",\"commented\",\"active\",null,\"active\",\"commented\",\"active\"],"
    "\"campaign_boot_binding_key\":\"boot_lg1\","
    "\"device_enforced_same_boot\":true,\"reboot_resume_allowed\":false,"
    "\"post_containment_resume_allowed\":false}";

static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":false,\"window_refresh\":false,"
    "\"command_0x83\":false,\"command_0x86\":false,"
    "\"unknown_commands\":false,\"mid_refresh_power_cut\":false,"
    "\"spi_frequency_sweep\":false,\"full_screen_global_refresh\":true,"
    "\"same_palette_hold_probe\":false,\"cross_palette_hold_probe\":false,"
    "\"local_hold_claimed\":false,\"history_brightness_screening\":true,"
    "\"true_neutral_gray_claimed\":false,\"qualified_gray_levels\":0,"
    "\"qualified_brightness_levels\":0,\"candidate_only\":true,"
    "\"independent_fresh_white_containment_required\":true,"
    "\"busy_qualified_arm_execute_dispatch\":true,"
    "\"device_enforced_same_boot\":true,\"runtime_code7_used_as_white\":false";

static constexpr const char *kNvsNamespace = rllg::kNvsNamespace;
static constexpr const char *kNvsKey = "cursor_lg1";
static constexpr const char *kNvsBootKey = rllg::kNvsBootKey;
static constexpr const char *kVersionRoute = "/api/ec5/luma-gray-v1/version";
static constexpr const char *kManifestRoute = "/api/ec5/luma-gray-v1/manifest";
static constexpr const char *kStatusRoute = "/api/ec5/luma-gray-v1/status";
static constexpr const char *kReportRoute = "/api/ec5/luma-gray-v1/report";
static constexpr const char *kArmRoute = "/api/ec5/luma-gray-v1/arm";
static constexpr const char *kExecuteRoute = "/api/ec5/luma-gray-v1/execute";

static constexpr const char *kBuildHeader = "X-EC5-Build-Tag";
static constexpr const char *kTestHeader = "X-EC5-Test-Id";
static constexpr const char *kCampaignHeader = "X-EC5-Campaign-Id";
static constexpr const char *kActionHeader = "X-EC5-Action-Id";
static constexpr const char *kOrdinalHeader = "X-EC5-Ordinal";
static constexpr const char *kDescriptorHeader = "X-EC5-Descriptor-Id";
static constexpr const char *kBootNonceHeader = "X-EC5-Boot-Nonce";
static constexpr const char *kArmNonceHeader = "X-EC5-Arm-Nonce";
static constexpr const char *kIntentHeader = "X-EC5-Intent";
static constexpr const char *kArmIntent = "ARM_ONE_FIXED_LUMA_GRAY_V1_EXPLORATORY_ACTION";
static constexpr const char *kExecuteIntent = "EXECUTE_ARMED_LUMA_GRAY_V1_EXPLORATORY_ACTION_ONCE";

#define RLLG_ACTION(ORDINAL, DRIVER_ROLE, ROLE, BRANCH, DESCRIPTOR, ACTION, PRIOR, FRAME_SHA, DTM_SHA, FRAME_FNV, DTM_FNV, H0, H1, H2, H3, H4, H5, H6, H7) \
  {ORDINAL, DRIVER_ROLE, ROLE, 1, BRANCH, DESCRIPTOR, ACTION, PRIOR, FRAME_SHA, DTM_SHA, DTM_SHA, FRAME_FNV, DTM_FNV, DTM_FNV, {H0, H1, H2, H3, H4, H5, H6, H7}}

static constexpr ActionDescriptor kActions[] = {
    RLLG_ACTION(1, EpdChromaGridRole::White, "FACTORY_OTP_WHITE_HEALTH_ANCHOR", "L535_LUMA_GRAY_EXPLORATORY_2PAGE_4X_REPEAT_V1_FACTORY_OTP_WHITE_HEALTH_ANCHOR", "1f507bd6fd65e630ba1202d2f427b59e2d311180494590c1926364a09bd8f88c", "6af04385a8eb34055f12fb70af6dfd7bc498942a44e8bb602eba029fa2b2532a", nullptr, "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d", "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158", 0x13340DC5UL, 0xB7A855C5UL, 0, 614400, 0, 0, 0, 0, 0, 0),
    RLLG_ACTION(2, EpdChromaGridRole::Source, "PAGE1_ACTIVE_SOURCE_ANCHORS_3_7", "L535_LUMA_GRAY_EXPLORATORY_2PAGE_4X_REPEAT_V1_PAGE1_ACTIVE_SOURCE_ANCHORS_3_7", "e021b9435c227d072ad6016b7cd2c69a5d30bac61b712a88f17e41d5f159df07", "c0fbc4fdba5bb6a1caff510c2b5f373e3d03c8c8bde07ad4ca33555e199097e5", "6af04385a8eb34055f12fb70af6dfd7bc498942a44e8bb602eba029fa2b2532a", "f6ba2d8781e6d986a865ff2504ef825c016597af56dcd8c0d2a207130d323048", "1a75b6485b7dd5bab843786b069ad22fb17459b50562e254c4952d0f5bd04b57", 0x5410A745UL, 0xD7AA85C5UL, 0, 0, 0, 193024, 0, 0, 0, 421376),
    RLLG_ACTION(3, EpdChromaGridRole::Mid, "PAGE1_COMMENTED_MIDDLE_CODES_0_7", "L535_LUMA_GRAY_EXPLORATORY_2PAGE_4X_REPEAT_V1_PAGE1_COMMENTED_MIDDLE_CODES_0_7", "e6abe5e077cf590282966cc666af41ac9c40392cb64d6d81b84952739b76dc1d", "4b27ae57ba6fd8848c66413f580013cc51a558c3205bd7a99771c93251672a53", "c0fbc4fdba5bb6a1caff510c2b5f373e3d03c8c8bde07ad4ca33555e199097e5", "2060bd9c15596d523be2501878946229c95b581c769f40daec88ef7cce300f52", "3db06a28c153f6a484e2e25cbbb99abcd18d3c51b931906f14c13e3243901ada", 0x6BCEDA45UL, 0x0D461F65UL, 48256, 48256, 48256, 48256, 48256, 48256, 48256, 276608),
    RLLG_ACTION(4, EpdChromaGridRole::Target, "PAGE1_ACTIVE_TARGET_CODE3", "L535_LUMA_GRAY_EXPLORATORY_2PAGE_4X_REPEAT_V1_PAGE1_ACTIVE_TARGET_CODE3", "7a140f2d880ddbb31915a7acec1d5d2125e45bc49a57fb5fe6fffe8c826ac179", "d91d22d0a5725bcd08bda5ce61e6cb115cd420fadc9e642a95392bb8337e36d8", "4b27ae57ba6fd8848c66413f580013cc51a558c3205bd7a99771c93251672a53", "1714bf0f1daf154385f4fbe8f0c1203210c5c91ca099633c96faf96b4eac1b9e", "d414e3f3c7f160d06e93a970f39214032b1069f8cded3dc04eacf887c173668d", 0x04485DC5UL, 0x28B27DC5UL, 0, 0, 0, 386048, 0, 0, 0, 228352),
    RLLG_ACTION(5, EpdChromaGridRole::White, "FACTORY_OTP_WHITE_PAGE_SEPARATOR", "L535_LUMA_GRAY_EXPLORATORY_2PAGE_4X_REPEAT_V1_FACTORY_OTP_WHITE_PAGE_SEPARATOR", "ac41fea0c7687438a1638761a88dd38558e1687e1d81e60ca985e07fbd98bd5b", "074e6c382e054ad50c8f7d2ab2d1364cae0054ab5dac599c444a27c54cff9f5e", "d91d22d0a5725bcd08bda5ce61e6cb115cd420fadc9e642a95392bb8337e36d8", "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d", "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158", 0x13340DC5UL, 0xB7A855C5UL, 0, 614400, 0, 0, 0, 0, 0, 0),
    RLLG_ACTION(6, EpdChromaGridRole::Source, "PAGE2_ACTIVE_SOURCE_ANCHORS_3_7", "L535_LUMA_GRAY_EXPLORATORY_2PAGE_4X_REPEAT_V1_PAGE2_ACTIVE_SOURCE_ANCHORS_3_7", "17bd405007eca6d55783f972d06cee0372ca2e7b9ed37e87a49ff7f97fa83145", "ba10904348f65abb816375d1fae680663e021b59d69a31bfe1964ae25e6c40ea", "074e6c382e054ad50c8f7d2ab2d1364cae0054ab5dac599c444a27c54cff9f5e", "f6ba2d8781e6d986a865ff2504ef825c016597af56dcd8c0d2a207130d323048", "1a75b6485b7dd5bab843786b069ad22fb17459b50562e254c4952d0f5bd04b57", 0x5410A745UL, 0xD7AA85C5UL, 0, 0, 0, 193024, 0, 0, 0, 421376),
    RLLG_ACTION(7, EpdChromaGridRole::Mid, "PAGE2_COMMENTED_MIDDLE_CODES_0_7", "L535_LUMA_GRAY_EXPLORATORY_2PAGE_4X_REPEAT_V1_PAGE2_COMMENTED_MIDDLE_CODES_0_7", "6f2d06dc9bd868c01d12011d04d79a14309f0fb029fb95913fe98d78124c3f5d", "3335c169add3fcaf277df42b7d053bbcaf7edf7e478d2042effd5b6173643343", "ba10904348f65abb816375d1fae680663e021b59d69a31bfe1964ae25e6c40ea", "2060bd9c15596d523be2501878946229c95b581c769f40daec88ef7cce300f52", "3db06a28c153f6a484e2e25cbbb99abcd18d3c51b931906f14c13e3243901ada", 0x6BCEDA45UL, 0x0D461F65UL, 48256, 48256, 48256, 48256, 48256, 48256, 48256, 276608),
    RLLG_ACTION(8, EpdChromaGridRole::ReverseSource, "PAGE2_ACTIVE_TARGET_CODE7", "L535_LUMA_GRAY_EXPLORATORY_2PAGE_4X_REPEAT_V1_PAGE2_ACTIVE_TARGET_CODE7", "5e345976495bdf8f34501af790d563783f4afe1a9bb8d6a9fd2307a316aee55b", "d8972e344c2acaa0c6e43a9ea34dc00c18acc7e4970ef339fb7d01a38e18752f", "3335c169add3fcaf277df42b7d053bbcaf7edf7e478d2042effd5b6173643343", "f27255891c2b00350b2f7aca6f0719116c6a29262008b7621ef4b7df66b099f2", "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd", 0x7C918DC5UL, 0x285715C5UL, 0, 0, 0, 0, 0, 0, 0, 614400),
};

#undef RLLG_ACTION
