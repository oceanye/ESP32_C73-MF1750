#include "ec5_stable_code0_luma_latin_v3_identity.inc"

namespace scl3 = mf1750_stable_code0_luma_latin_v3;

static constexpr const char *kClassification =
    "EXPERIMENTAL_STABLE_ACTIVE_CODE0_HISTORY_LUMA_CANDIDATES_"
    "CS2_RED_FAMILY_PRIMARY_CS1_CONTROLLER_SPECIFIC_CONTROL";
static constexpr const char *kProfileSource =
    "legacy_complete_535_reference_active_and_commented_global_headers";
static constexpr const char *kIdentityRevision =
    "stable-code0-luma-latin-v3";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_STABLE_CODE0_LUMA_LATIN_DEVICE_V3";
static constexpr const char *kLayoutId = scl3::kVariantKey;
static constexpr const char *kBuildTag = scl3::kBuildTag;
static constexpr const char *kBootLabel =
    "EC5 stable active-code0 luma Latin V3";
static constexpr const char *kTestId = scl3::kTestId;
static constexpr const char *kCampaignId = scl3::kCampaignId;
static constexpr const char *kContractId = scl3::kContractId;
static constexpr const char *kVersionKind =
    "mf1750-ec5-stable-code0-luma-latin-v3-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-stable-code0-luma-latin-v3-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-stable-code0-luma-latin-v3-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-stable-code0-luma-latin-v3-report";
static constexpr const char *kBaselineRole =
    "L1_FIXED_ACTIVE_SOURCE_CODE7";

static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"candidate_cells_per_controller\":64,"
    "\"candidate_cells_total_observations\":128,"
    "\"middle_repeat_count_per_controller\":8,"
    "\"grid_rows\":8,\"grid_columns_per_controller\":8,"
    "\"grid_x0_local\":20,\"grid_y0\":40,"
    "\"grid_x1_local_exclusive\":492,\"grid_y1_exclusive\":560,"
    "\"cell_width\":52,\"cell_height\":58,\"gap_x\":8,\"gap_y\":8,"
    "\"source_global_header\":\"active\",\"source_code\":7,"
    "\"middle_global_header\":\"commented\","
    "\"middle_codes\":[0,1,2,3,4,5,6,7],"
    "\"target_global_header\":\"active\",\"target_code\":0,"
    "\"profile_sequence\":[\"active\",\"commented\",\"active\",\"active\"],"
    "\"cs1_layout\":\"latin_code=(row+column)%8\","
    "\"cs2_layout\":\"rotate_180_of_cs1\","
    "\"cs2_decoder\":\"logical=(7-row,7-column);code=(logical_row+logical_column)%8\","
    "\"cs2_role\":\"RED_FAMILY_PRIMARY_OBSERVATION\","
    "\"cs1_role\":\"CONTROLLER_SPECIFIC_INTERNAL_CONTROL\","
    "\"controller_color_equivalence_claimed\":false,"
    "\"target_hue_id\":\"ACTIVE_CODE0_CS2_RED_FAMILY_PRIMARY_CS1_CONTROLLER_SPECIFIC_INTERNAL_CONTROL_UNCALIBRATED\","
    "\"qualified_brightness_levels\":0,"
    "\"spatial_dither\":false,\"ptlw_command_issued\":false,"
    "\"cropped_dtm\":false,"
    "\"all_action_dtm_transport\":\"packed_frame_per_controller\","
    "\"l4_identical_target_repeat\":true,"
    "\"l4_automatic_dispatch\":false,\"l4_autochain\":false,"
    "\"source_authority\":{"
      "\"authority_kind\":\"W11_COMPLETE_PLUS_CAMERA_VISIBLE_CLEAN_WHITE_REVIEW\","
      "\"required_before_any_device_request\":true,"
      "\"w11_campaign_id\":\"EC5_RAW_P16_CROSSOVER_W11_AFTER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V5_WHITE_V1\","
      "\"w11_contract_id\":\"52aa5c78ba61abef70327a3e86df368668857e8d99e67c59c406371f757ba85f\","
      "\"w11_descriptor_id\":\"076563342d74ff2aae8439c084b98a97fa7823cb54e29394ab859e0a716fc411\","
      "\"w11_action_id\":\"80a9fd85ff4b93ce365b699f1caa8d7835cbeeeaf738194f70cccc0f7500b595\","
      "\"w11_action_file_sha256\":\"e48ee37c34e6984f15656267e8d915a8552b210f8dd465610ca1c438ee79c3b0\","
      "\"camera_review_file_sha256\":\"c88d22d8ab241daeccb28e01a722c166fdc07bef50f7c55024ba57204008d9a9\","
      "\"camera_review_state\":\"CAMERA_VISIBLE_CLEAN_WHITE_CONTAINMENT_REVIEW\","
      "\"camera_relative_only\":true,"
      "\"absolute_white_point_proven\":false,"
      "\"spatial_uniformity_proven\":false,"
      "\"schedule_policy\":{"
        "\"branch\":\"ALTERNATIVE_FIRST_EXPERIMENT_AFTER_W11_WHITE_ONLY\","
        "\"no_intervening_panel_refresh_since_w11_white_required\":true,"
        "\"not_sequential_after_luma_gray_mechanism_v2\":true,"
        "\"if_another_campaign_ran\":\"REQUIRE_FRESH_INDEPENDENT_FACTORY_OTP_WHITE_AND_NEW_SUCCESSOR_BINDING\","
        "\"operator_reconfirmation_required_before_diagnostic_and_run\":true}}}";

static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":false,\"window_refresh\":false,"
    "\"command_0x83\":false,\"command_0x86\":false,"
    "\"unknown_commands\":false,\"mid_refresh_power_cut\":false,"
    "\"spi_frequency_sweep\":false,\"full_screen_global_refresh\":true,"
    "\"same_palette_hold_probe\":false,\"cross_palette_hold_probe\":false,"
    "\"local_hold_claimed\":false,\"history_brightness_screening\":true,"
    "\"target_repeat_stability_probe\":true,"
    "\"l4_identical_target_repeat\":true,"
    "\"l4_separate_manual_action\":true,"
    "\"l4_automatic_dispatch\":false,"
    "\"device_enforced_same_boot\":true,"
    "\"brightness_candidates_only\":true,\"qualified_brightness_levels\":0,"
    "\"human_or_camera_observation_gate_after_l3_and_l4\":true,"
    "\"busy_qualified_arm_execute_dispatch\":true,"
    "\"independent_factory_otp_white_containment_required\":true";

static constexpr const char *kNvsNamespace = scl3::kNvsNamespace;
static constexpr const char *kNvsKey = "cur_scl3";
static constexpr const char *kNvsBootKey = scl3::kNvsBootKey;
static constexpr const char *kVersionRoute =
    "/api/ec5/stable-code0-luma-latin-v3/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/stable-code0-luma-latin-v3/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/stable-code0-luma-latin-v3/status";
static constexpr const char *kReportRoute =
    "/api/ec5/stable-code0-luma-latin-v3/report";
static constexpr const char *kArmRoute =
    "/api/ec5/stable-code0-luma-latin-v3/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/stable-code0-luma-latin-v3/execute";

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
    "ARM_ONE_FIXED_STABLE_CODE0_LUMA_LATIN_V3_ACTION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ARMED_STABLE_CODE0_LUMA_LATIN_V3_ACTION_ONCE";

#define SCL3_ACTION(ORDINAL, DRIVER_ROLE, ROLE, BRANCH, DESCRIPTOR, ACTION,  \
                    PRIOR, FRAME_SHA, CS1_DTM_SHA, CS2_DTM_SHA, FRAME_FNV,   \
                    CS1_DTM_FNV, CS2_DTM_FNV, H0, H1, H2, H3, H4, H5, H6, \
                    H7)                                                      \
  {                                                                          \
    ORDINAL, DRIVER_ROLE, ROLE, 1, BRANCH, DESCRIPTOR, ACTION, PRIOR,         \
        FRAME_SHA, CS1_DTM_SHA, CS2_DTM_SHA, FRAME_FNV, CS1_DTM_FNV,         \
        CS2_DTM_FNV, {H0, H1, H2, H3, H4, H5, H6, H7}                       \
  }

static constexpr ActionDescriptor kActions[] = {
    SCL3_ACTION(
        1, EpdChromaGridRole::Source, "L1_FIXED_ACTIVE_SOURCE_CODE7",
        "STABLE_CODE0_LUMA_LATIN_V3_L1_FIXED_ACTIVE_SOURCE_CODE7",
        "6056c7ba401c3abe2ff022a126c6a54cfec9d8594dc5e8faee8785c9b5556eee",
        "83b0e955ff0d88076737e8e13946602c696829bcef159691ce4ef074abfaf62e",
        nullptr,
        "f27255891c2b00350b2f7aca6f0719116c6a29262008b7621ef4b7df66b099f2",
        "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
        "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
        0x7C918DC5UL, 0x285715C5UL, 0x285715C5UL,
        0, 0, 0, 0, 0, 0, 0, 614400),
    SCL3_ACTION(
        2, EpdChromaGridRole::Mid, "L2_COMMENTED_MIDDLE_LATIN_C0_C7",
        "STABLE_CODE0_LUMA_LATIN_V3_L2_COMMENTED_MIDDLE_LATIN_C0_C7",
        "61c5c9ebc88279e1015106e06b9702a725c0ebaa09af3a802f2939bd30b15615",
        "c7606fc0d16eed0e7dc9d211441da551579a168d85bcba336c32e724396c2ad8",
        "83b0e955ff0d88076737e8e13946602c696829bcef159691ce4ef074abfaf62e",
        "03265f52002f241e4681631d5efd2686045a533c3a8ab8977bcd2bbd01961416",
        "890ea1f455e80bfe262ae53f6741409d1737603ff5a642f1d58f241ab258e1f3",
        "b28a0b79555000bed6c9a991e0ca3e8317661e38adaf7cb1293b9f3b5510c253",
        0x41A370C5UL, 0x02229BC5UL, 0xA4741A45UL,
        48256, 48256, 48256, 48256, 48256, 48256, 48256, 276608),
    SCL3_ACTION(
        3, EpdChromaGridRole::Target, "L3_FIXED_ACTIVE_TARGET_CODE0",
        "STABLE_CODE0_LUMA_LATIN_V3_L3_FIXED_ACTIVE_TARGET_CODE0",
        "371a59e807fde7515027870c69707a5aaa29997925c571d3176b65d8ec3a2cd2",
        "185d103527cebf9bd36153ca9d0ba4eb6152c57d39dbf177ecd5a24d6309d4a5",
        "c7606fc0d16eed0e7dc9d211441da551579a168d85bcba336c32e724396c2ad8",
        "9c771f6a89f72bdd64c38ddd99489accad9c5ed554d1841740517ea1100f7af4",
        "f36eeda01f7cdd5cda9147cece0a543009a217235c38b1ab3f636f24b2e4f4aa",
        "f36eeda01f7cdd5cda9147cece0a543009a217235c38b1ab3f636f24b2e4f4aa",
        0x2CC36BC5UL, 0x4FA004C5UL, 0x4FA004C5UL,
        386048, 0, 0, 0, 0, 0, 0, 228352),
    SCL3_ACTION(
        4, EpdChromaGridRole::Target,
        "L4_IDENTICAL_ACTIVE_TARGET_CODE0_REPEAT",
        "STABLE_CODE0_LUMA_LATIN_V3_L4_IDENTICAL_ACTIVE_TARGET_CODE0_REPEAT",
        scl3::kL4DescriptorId, scl3::kL4ActionId, scl3::kL4PriorActionId,
        scl3::kL4FrameSha256, scl3::kL4Cs1DtmSha256,
        scl3::kL4Cs2DtmSha256, scl3::kL4FrameFnv1a,
        scl3::kL4Cs1DtmFnv1a, scl3::kL4Cs2DtmFnv1a,
        386048, 0, 0, 0, 0, 0, 0, 228352),
};

#undef SCL3_ACTION
