#include "ec5_runtime_lut_hue_brightness_blue_v1_identity.inc"

namespace rlhbb = mf1750_runtime_lut_hue_brightness_blue_v1;

static constexpr const char *kClassification =
    "EXPERIMENTAL_L535_BLUE_HUE_HISTORY_BRIGHTNESS_CANDIDATES_NOT_QUALIFIED_LEVELS";
static constexpr const char *kProfileSource =
    "legacy_complete_535_reference_active_and_commented_global_headers";
static constexpr const char *kIdentityRevision =
    "runtime-lut-target-hue-blue-brightness-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_TARGET_HUE_BLUE_BRIGHTNESS_DEVICE_V1";
static constexpr const char *kLayoutId = rlhbb::kVariantKey;
static constexpr const char *kBuildTag = rlhbb::kBuildTag;
static constexpr const char *kBootLabel =
    "EC5 target-hue blue brightness-candidate ladder";
static constexpr const char *kTestId = rlhbb::kTestId;
static constexpr const char *kCampaignId = rlhbb::kCampaignId;
static constexpr const char *kContractId = rlhbb::kContractId;
static constexpr const char *kVersionKind =
    "mf1750-ec5-target-hue-blue-brightness-v1-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-target-hue-blue-brightness-v1-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-target-hue-blue-brightness-v1-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-target-hue-blue-brightness-v1-report";
static constexpr const char *kBaselineRole = "RUNTIME_LUT_WHITE_BASELINE";
static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"candidate_cells_per_controller\":64,"
    "\"candidate_cells_total_observations\":128,"
    "\"unique_recipes\":64,"
    "\"duplicate_recipe_across_controllers\":true,"
    "\"controller_color_equivalence_claimed\":false,"
    "\"cs2_position_mirrored\":false,"
    "\"grid_rows\":8,\"grid_columns_per_controller\":8,"
    "\"grid_x0_local\":20,\"grid_y0\":40,"
    "\"grid_x1_local_exclusive\":492,"
    "\"grid_y1_exclusive\":560,"
    "\"cell_width\":52,\"cell_height\":58,"
    "\"gap_x\":8,\"gap_y\":8,"
    "\"row_axis\":\"commented_middle_code_0_to_7\","
    "\"column_axis\":\"active_source_code_0_to_7\","
    "\"horizontal_comparison_group\":"
    "\"eight_adjacent_source_histories_same_middle_and_target\","
    "\"target_hue_id\":"
    "\"ACTIVE_CODE5_HIGH_CONFIDENCE_BLUE_UNCALIBRATED\","
    "\"target_global_header\":\"active\","
    "\"target_transport_code\":5,"
    "\"target_repeat_count\":2,"
    "\"qualified_brightness_levels\":0,"
    "\"brightness_candidates_only\":true,"
    "\"spatial_dither\":false,"
    "\"white_gutter_history_interaction_qualified\":false,"
    "\"ptlw_command_issued\":false,\"cropped_dtm\":false,"
    "\"all_action_dtm_transport\":\"packed_frame_per_controller\","
    "\"global_header_sequence\":["
    "\"active\",\"active\",\"commented\","
    "\"active\",\"active\",\"active\"],"
    "\"cs1_r20_prefix_bytes\":535,"
    "\"cs1_r20_prefix_sha256\":"
    "\"716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b\","
    "\"cs2_r20_prefix_bytes\":535,"
    "\"cs2_r20_prefix_sha256\":"
    "\"2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26\","
    "\"r21_bytes\":704,\"r21_sha256\":"
    "\"24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f\","
    "\"strict_same_boot_prior_complete_required\":true,"
    "\"skip_to_white_recovery_allowed\":false,"
    "\"failure_containment_firmware_sha256\":"
    "\"82e49e994570c9fb43ccbd7a7faa59adb55f5290d663aae2eee305250bcea12f\","
    "\"failure_containment_contract_id\":"
    "\"ae9096e36998a956674db4b879685038b8b8d905b51b4db318c1387053fd0865\","
    "\"failure_containment_nvs_namespace\":\"rlhbcw_v1\","
    "\"failure_containment_campaign_nvs_dependency\":false}";
static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":false,\"window_refresh\":false,"
    "\"command_0x83\":false,\"command_0x86\":false,"
    "\"mid_refresh_power_cut\":false,"
    "\"spi_frequency_sweep\":false,"
    "\"full_screen_global_refresh\":true,"
    "\"same_palette_hold_probe\":false,"
    "\"cross_palette_hold_probe\":false,"
    "\"history_brightness_screening\":true,"
    "\"target_repeat_stability_probe\":true,"
    "\"busy_qualified_arm_execute_dispatch\":true,"
    "\"local_hold_claimed\":false";

static constexpr const char *kNvsNamespace = rlhbb::kNvsNamespace;
static constexpr const char *kNvsKey = "cursor_hbb1";
static constexpr const char *kVersionRoute =
    "/api/ec5/target-hue-blue-brightness-v1/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/target-hue-blue-brightness-v1/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/target-hue-blue-brightness-v1/status";
static constexpr const char *kReportRoute =
    "/api/ec5/target-hue-blue-brightness-v1/report";
static constexpr const char *kArmRoute =
    "/api/ec5/target-hue-blue-brightness-v1/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/target-hue-blue-brightness-v1/execute";

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
    "ARM_ONE_FIXED_BLUE_HUE_BRIGHTNESS_CANDIDATE_ACTION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ARMED_BLUE_HUE_BRIGHTNESS_CANDIDATE_ACTION_ONCE";

#define RLHBB_ACTION(ORDINAL, DRIVER_ROLE, ROLE, BRANCH, DESCRIPTOR, ACTION,  \
                     PRIOR, FRAME_SHA, DTM_SHA, FRAME_FNV, DTM_FNV, H0, H1,  \
                     H2, H3, H4, H5, H6, H7)                                \
  {                                                                          \
    ORDINAL, DRIVER_ROLE, ROLE, 1, BRANCH, DESCRIPTOR, ACTION, PRIOR,         \
        FRAME_SHA, DTM_SHA, DTM_SHA, FRAME_FNV, DTM_FNV, DTM_FNV,            \
        {H0, H1, H2, H3, H4, H5, H6, H7}                                    \
  }

static constexpr ActionDescriptor kActions[] = {
    RLHBB_ACTION(
        1, EpdChromaGridRole::White, "RUNTIME_LUT_WHITE_BASELINE",
        "L535_TARGET_HUE_BLUE_BRIGHTNESS_HISTORY_8X8_ABA_V1_RUNTIME_LUT_WHITE_BASELINE",
        "4b33b38c95e21b39112649b53dd28beb9d716f0326d573487b94699d2c4996be",
        "8466e0beb4912320c8b55dd9c28c7eb6e24e0376696371c84d957e388cb2ec4a",
        nullptr,
        "f27255891c2b00350b2f7aca6f0719116c6a29262008b7621ef4b7df66b099f2",
        "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
        0x7C918DC5UL, 0x285715C5UL, 0, 0, 0, 0, 0, 0, 0, 614400),
    RLHBB_ACTION(
        2, EpdChromaGridRole::Source, "BLUE_LADDER_SOURCE_GRID_ACTIVE",
        "L535_TARGET_HUE_BLUE_BRIGHTNESS_HISTORY_8X8_ABA_V1_BLUE_LADDER_SOURCE_GRID_ACTIVE",
        "8eed0cfc72d64127a600dbe0591cc25111f921605093dca13f8f864890255035",
        "72346766e7cb957555dc7505e93edecb060addb3389d1cc3517846ee54cb5916",
        "8466e0beb4912320c8b55dd9c28c7eb6e24e0376696371c84d957e388cb2ec4a",
        "fe420d9010e95b0347e7c468d18fb2283f4d5ede420a1ca811dafe9a1ebab853",
        "8aae76f672eb482772dd40b53840f70171db753477bb887cffb6b80dbb94dc74",
        0x5A43EDC5UL, 0x1E3045C5UL, 48256, 48256, 48256, 48256,
        48256, 48256, 48256, 276608),
    RLHBB_ACTION(
        3, EpdChromaGridRole::Mid, "BLUE_LADDER_MIDDLE_GRID_COMMENTED",
        "L535_TARGET_HUE_BLUE_BRIGHTNESS_HISTORY_8X8_ABA_V1_BLUE_LADDER_MIDDLE_GRID_COMMENTED",
        "f7c77eb86ad77d2c75c82599ac387851d6de7bbec74149ed9bb932a9690d263c",
        "5076949066e825b5b6f5e4c3fb8b49713f9b7734a57f9ecb5e01604729ef0d39",
        "72346766e7cb957555dc7505e93edecb060addb3389d1cc3517846ee54cb5916",
        "5d9d3fa7a873128c12ee4e2ab55e88ddf4e2388b6efd90a041c48b05f51e2dc3",
        "bfed84706002d390db5e5cc69b5111304e8fd5f6cdd251f6092229af3bc09f81",
        0x199F2BC5UL, 0xA0586A45UL, 48256, 48256, 48256, 48256,
        48256, 48256, 48256, 276608),
    RLHBB_ACTION(
        4, EpdChromaGridRole::Target,
        "BLUE_LADDER_FIXED_TARGET_ACTIVE_CODE5",
        "L535_TARGET_HUE_BLUE_BRIGHTNESS_HISTORY_8X8_ABA_V1_BLUE_LADDER_FIXED_TARGET_ACTIVE_CODE5",
        "0339ef8b9a082ee64737c2e5040a674aa58f00c69c3d69ebc3f8f1b257b36c16",
        "5cc57eca3e37b261e8d5b3a5f77ad7857ed005cd553e07cfea5d3ad045b70122",
        "5076949066e825b5b6f5e4c3fb8b49713f9b7734a57f9ecb5e01604729ef0d39",
        "b67e352d9bba5947f5ea338ec93ed55147c46f3195015397e9393318c9d5ec7b",
        "fdde217c450f8081772e7e54e2cdabd0e7de5bf8af4fe123e8f46576caaa10af",
        0xCFC80DC5UL, 0xB5F255C5UL, 0, 0, 0, 0, 0, 386048, 0,
        228352),
    RLHBB_ACTION(
        5, EpdChromaGridRole::Target,
        "BLUE_LADDER_FIXED_TARGET_REPEAT_ACTIVE_CODE5",
        "L535_TARGET_HUE_BLUE_BRIGHTNESS_HISTORY_8X8_ABA_V1_BLUE_LADDER_FIXED_TARGET_REPEAT_ACTIVE_CODE5",
        "008d5667fa51d096b59271ee2686c89cb305217a0a7a379a901ffd8b2fbfc2b1",
        "12319c944a6eb7a1cf0dd059d1567a58bf28f1aa1353ca344354b359937987ed",
        "5cc57eca3e37b261e8d5b3a5f77ad7857ed005cd553e07cfea5d3ad045b70122",
        "b67e352d9bba5947f5ea338ec93ed55147c46f3195015397e9393318c9d5ec7b",
        "fdde217c450f8081772e7e54e2cdabd0e7de5bf8af4fe123e8f46576caaa10af",
        0xCFC80DC5UL, 0xB5F255C5UL, 0, 0, 0, 0, 0, 386048, 0,
        228352),
    RLHBB_ACTION(
        6, EpdChromaGridRole::White, "RUNTIME_LUT_WHITE_RECOVERY",
        "L535_TARGET_HUE_BLUE_BRIGHTNESS_HISTORY_8X8_ABA_V1_RUNTIME_LUT_WHITE_RECOVERY",
        "0e972d9f141331368063b6b3981d85d8e4500543cce046ef91907ee75828217a",
        "4f357c544af0f4dbbd244f8e672c6fd074a99f2e7a06d0622b9c91bf5fab23e0",
        "12319c944a6eb7a1cf0dd059d1567a58bf28f1aa1353ca344354b359937987ed",
        "f27255891c2b00350b2f7aca6f0719116c6a29262008b7621ef4b7df66b099f2",
        "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
        0x7C918DC5UL, 0x285715C5UL, 0, 0, 0, 0, 0, 0, 0, 614400),
};

#undef RLHBB_ACTION
