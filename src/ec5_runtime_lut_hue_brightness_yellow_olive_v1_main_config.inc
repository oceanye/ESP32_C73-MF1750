#include "ec5_runtime_lut_hue_brightness_yellow_olive_v1_identity.inc"

namespace rlhyo = mf1750_runtime_lut_hue_brightness_yellow_olive_v1;

static constexpr const char *kClassification =
    "EXPERIMENTAL_L535_YELLOW_OLIVE_CODE2_HISTORY_BRIGHTNESS_CANDIDATES_NOT_QUALIFIED_LEVELS";
static constexpr const char *kProfileSource =
    "factory_otp_white_and_legacy_complete_535_reference_active_and_commented_global_headers";
static constexpr const char *kIdentityRevision =
    "runtime-lut-target-hue-yellow-olive-brightness-factory-white-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_DEVICE_V1";
static constexpr const char *kLayoutId = rlhyo::kVariantKey;
static constexpr const char *kBuildTag = rlhyo::kBuildTag;
static constexpr const char *kBootLabel =
    "EC5 target-hue yellow/olive code2 brightness-candidate ladder";
static constexpr const char *kTestId = rlhyo::kTestId;
static constexpr const char *kCampaignId = rlhyo::kCampaignId;
static constexpr const char *kContractId = rlhyo::kContractId;
static constexpr const char *kVersionKind =
    "mf1750-ec5-target-hue-yellow-olive-brightness-v1-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-target-hue-yellow-olive-brightness-v1-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-target-hue-yellow-olive-brightness-v1-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-target-hue-yellow-olive-brightness-v1-report";
static constexpr const char *kBaselineRole =
    "FACTORY_OTP_WHITE_HEALTH_ANCHOR";
static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"candidate_cells_per_controller\":64,"
    "\"candidate_cells_total_observations\":128,"
    "\"unique_recipes\":64,"
    "\"duplicate_recipe_across_controllers\":true,"
    "\"controller_color_equivalence_claimed\":false,"
    "\"paired_controller_observations_not_colour_equivalent\":true,"
    "\"controller_payload_binding\":"
    "\"CS1_ACTIVE535_AND_CS2_COMMENTED535_FIXED\","
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
    "\"Y_ACTIVE_CODE2_CS1_YELLOW_OLIVE_CANDIDATE_UNCALIBRATED\","
    "\"target_hue_catalog_id\":"
    "\"94eabf2d00b2f0e90e86201f54923029b25182c140c757023b77f8f302165fd8\","
    "\"target_global_header\":\"active\","
    "\"target_transport_code\":2,"
    "\"target_repeat_count\":2,"
    "\"qualified_brightness_levels\":0,"
    "\"brightness_candidates_only\":true,"
    "\"spatial_dither\":false,"
    "\"white_gutter_history_interaction_qualified\":false,"
    "\"runtime_code7_semantics\":"
    "\"unqualified_separator_and_background_transport_code_not_white\","
    "\"runtime_code7_used_as_white\":false,"
    "\"factory_otp_white_ordinals\":[1,6],"
    "\"factory_otp_white_fill_byte\":17,"
    "\"ptlw_command_issued\":false,\"cropped_dtm\":false,"
    "\"all_action_dtm_transport\":\"packed_frame_per_controller\","
    "\"global_header_sequence\":[null,\"active\",\"commented\","
    "\"active\",\"active\",null],"
    "\"palette_source_sequence\":[\"FACTORY_OTP\",\"L535_RUNTIME\","
    "\"L535_RUNTIME\",\"L535_RUNTIME\",\"L535_RUNTIME\",\"FACTORY_OTP\"],"
    "\"cs1_r20_prefix_bytes\":535,"
    "\"cs1_r20_prefix_sha256\":"
    "\"716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b\","
    "\"cs2_r20_prefix_bytes\":535,"
    "\"cs2_r20_prefix_sha256\":"
    "\"2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26\","
    "\"r21_bytes\":704,\"r21_sha256\":"
    "\"24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f\","
    "\"strict_same_boot_prior_complete_required\":true,"
    "\"device_same_boot_binding\":"
    "\"uint64_first_fresh_setup_boot_nonce\","
    "\"device_same_boot_binding_nvs_key\":\"boot_yob1\","
    "\"device_same_boot_gate_points\":[\"setup\",\"arm\","
    "\"execute\",\"dispatch\"],"
    "\"reboot_fault_lock_before_epd_begin\":true,"
    "\"skip_to_factory_white_recovery_allowed\":false,"
    "\"ordinal4_no_difference_early_seal\":"
    "\"skip_5_and_6_then_fresh_containment\","
    "\"ordinal5_requires_visible_candidate_confirmation\":true,"
    "\"failure_containment_kind\":"
    "\"independent_fresh_identity_factory_otp_white\","
    "\"failure_containment_firmware_bytes\":786544,"
    "\"failure_containment_firmware_sha256\":"
    "\"80dfebbd0f609203d1b4f7f9784389815bf0f54d8e3efb4b5fa42febc0b61ec1\","
    "\"failure_containment_elf_bytes\":13214132,"
    "\"failure_containment_elf_sha256\":"
    "\"4e846aca492bac6dc2d460c87aeb46a76eba97fc292fc5dde8536b73f84ee8e8\","
    "\"failure_containment_contract_id\":"
    "\"fbedf22afbe6129e2824b9726f8be16f8b949c77cf02eb49d9707166d1ec095b\","
    "\"failure_containment_nvs_namespace\":\"rlhyocw_v1\","
    "\"failure_containment_nvs_key\":\"used_yocw1\","
    "\"failure_containment_base_route\":"
    "\"/api/ec5/target-hue-yellow-olive-brightness-v1/white-containment\","
    "\"failure_containment_descriptor_id\":"
    "\"99e0f93b79a8aef9e1e3256c76aec517d0bf37be8ee1b5d3074ee83c3296c3be\","
    "\"failure_containment_action_id\":"
    "\"ac05c0d290e91a33e92f3eccb00bce68d35b6852bae813dfabbb6950d485d45b\","
    "\"failure_containment_campaign_nvs_dependency\":false,"
    "\"main_campaign_resume_device_blocked_by_boot_binding\":true,"
    "\"main_campaign_resume_after_containment\":false}";
static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":false,\"window_refresh\":false,"
    "\"command_0x83\":false,\"command_0x86\":false,"
    "\"unknown_commands\":false,"
    "\"mid_refresh_power_cut\":false,"
    "\"spi_frequency_sweep\":false,"
    "\"full_screen_global_refresh\":true,"
    "\"same_palette_hold_probe\":false,"
    "\"cross_palette_hold_probe\":false,"
    "\"history_brightness_screening\":true,"
    "\"target_repeat_stability_probe\":true,"
    "\"busy_qualified_arm_execute_dispatch\":true,"
    "\"device_enforced_same_boot_nvs_binding\":true,"
    "\"negative_early_seal_after_ordinal4\":true,"
    "\"ordinal5_requires_visible_candidate_confirmation\":true,"
    "\"running_app_elf_sha256_reported\":true,"
    "\"human_observation_gate_after_target\":true,"
    "\"factory_otp_white_anchor_and_recovery\":true,"
    "\"runtime_code7_used_as_white\":false,"
    "\"local_hold_claimed\":false";

static constexpr const char *kNvsNamespace = rlhyo::kNvsNamespace;
static constexpr const char *kNvsKey = "cursor_yob1";
static constexpr const char *kBootBindingNvsKey = rlhyo::kBootBindingNvsKey;
static constexpr const char *kVersionRoute =
    "/api/ec5/target-hue-yellow-olive-brightness-v1/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/target-hue-yellow-olive-brightness-v1/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/target-hue-yellow-olive-brightness-v1/status";
static constexpr const char *kReportRoute =
    "/api/ec5/target-hue-yellow-olive-brightness-v1/report";
static constexpr const char *kArmRoute =
    "/api/ec5/target-hue-yellow-olive-brightness-v1/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/target-hue-yellow-olive-brightness-v1/execute";

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
    "ARM_ONE_FIXED_YELLOW_OLIVE_CODE2_BRIGHTNESS_CANDIDATE_ACTION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ARMED_YELLOW_OLIVE_CODE2_BRIGHTNESS_CANDIDATE_ACTION_ONCE";

#define RLHYO_ACTION(ORDINAL, DRIVER_ROLE, ROLE, BRANCH, DESCRIPTOR, ACTION, \
                     PRIOR, FRAME_SHA, DTM_SHA, FRAME_FNV, DTM_FNV, H0, H1, \
                     H2, H3, H4, H5, H6, H7)                                \
  {                                                                          \
    ORDINAL, DRIVER_ROLE, ROLE, 1, BRANCH, DESCRIPTOR, ACTION, PRIOR,         \
        FRAME_SHA, DTM_SHA, DTM_SHA, FRAME_FNV, DTM_FNV, DTM_FNV,            \
        {H0, H1, H2, H3, H4, H5, H6, H7}                                    \
  }

static constexpr ActionDescriptor kActions[] = {
    RLHYO_ACTION(
        1, EpdChromaGridRole::White, "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
        "L535_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_HISTORY_8X8_ABA_V1_FACTORY_OTP_WHITE_HEALTH_ANCHOR",
        "1dc425968891e72e4fb377ef692d1a092f3e62ee00a9beec454cc689c0607abd",
        "479f3cd677ac2c3b65fa9950fad622533b9c678bb0d7146394b0bf78aed83c52",
        nullptr,
        "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
        "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
        0x13340DC5UL, 0xB7A855C5UL, 0, 614400, 0, 0, 0, 0, 0, 0),
    RLHYO_ACTION(
        2, EpdChromaGridRole::Source,
        "YELLOW_OLIVE_LADDER_SOURCE_GRID_ACTIVE",
        "L535_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_HISTORY_8X8_ABA_V1_YELLOW_OLIVE_LADDER_SOURCE_GRID_ACTIVE",
        "656dab642504883363dceb94411df7abbba0c4e21ebd06630839b649f458457f",
        "012f89ef6a8194cdcbff17720a833861825d7d9655f517c2da92e86d91caea29",
        "479f3cd677ac2c3b65fa9950fad622533b9c678bb0d7146394b0bf78aed83c52",
        "fe420d9010e95b0347e7c468d18fb2283f4d5ede420a1ca811dafe9a1ebab853",
        "8aae76f672eb482772dd40b53840f70171db753477bb887cffb6b80dbb94dc74",
        0x5A43EDC5UL, 0x1E3045C5UL, 48256, 48256, 48256, 48256,
        48256, 48256, 48256, 276608),
    RLHYO_ACTION(
        3, EpdChromaGridRole::Mid,
        "YELLOW_OLIVE_LADDER_MIDDLE_GRID_COMMENTED",
        "L535_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_HISTORY_8X8_ABA_V1_YELLOW_OLIVE_LADDER_MIDDLE_GRID_COMMENTED",
        "dbc836f85c23355aed4866f6a7614981a0b59bdb51b05dc9e802b8133a4575ea",
        "1d307a7c22bf54340d90ec3eaee548040933b899c159480898a4d96dbf494f4a",
        "012f89ef6a8194cdcbff17720a833861825d7d9655f517c2da92e86d91caea29",
        "5d9d3fa7a873128c12ee4e2ab55e88ddf4e2388b6efd90a041c48b05f51e2dc3",
        "bfed84706002d390db5e5cc69b5111304e8fd5f6cdd251f6092229af3bc09f81",
        0x199F2BC5UL, 0xA0586A45UL, 48256, 48256, 48256, 48256,
        48256, 48256, 48256, 276608),
    RLHYO_ACTION(
        4, EpdChromaGridRole::Target,
        "YELLOW_OLIVE_LADDER_FIXED_TARGET_ACTIVE_CODE2",
        "L535_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_HISTORY_8X8_ABA_V1_YELLOW_OLIVE_LADDER_FIXED_TARGET_ACTIVE_CODE2",
        "08af57d294e026daf2e9c85651f495dc24cae64d94a5ddfe41fdb6370459d361",
        "7cfe7a0c92411656fa0ba0f1f512393818ab86e750ec71f4e2adaee0fff6d0fa",
        "1d307a7c22bf54340d90ec3eaee548040933b899c159480898a4d96dbf494f4a",
        "6f975c438ae87d017c221c0ecb98a241d875f714bc236bc513ebe2ebcfcc2ce6",
        "506b9b914ac2039346e28d16b12bee7df393e7437f15d4de47bd3a9ac2986b63",
        0x47DA93C5UL, 0x762B98C5UL, 0, 0, 386048, 0, 0, 0, 0,
        228352),
    RLHYO_ACTION(
        5, EpdChromaGridRole::Target,
        "YELLOW_OLIVE_LADDER_FIXED_TARGET_REPEAT_ACTIVE_CODE2",
        "L535_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_HISTORY_8X8_ABA_V1_YELLOW_OLIVE_LADDER_FIXED_TARGET_REPEAT_ACTIVE_CODE2",
        "83b27983aa3040a47130dd6cb2d7510655869797d53f32deb82cad49681b3cf8",
        "9fe8f7f1c271e4003e04ec42de0e2e27f623d0185bb942271d769ebe49cb180a",
        "7cfe7a0c92411656fa0ba0f1f512393818ab86e750ec71f4e2adaee0fff6d0fa",
        "6f975c438ae87d017c221c0ecb98a241d875f714bc236bc513ebe2ebcfcc2ce6",
        "506b9b914ac2039346e28d16b12bee7df393e7437f15d4de47bd3a9ac2986b63",
        0x47DA93C5UL, 0x762B98C5UL, 0, 0, 386048, 0, 0, 0, 0,
        228352),
    RLHYO_ACTION(
        6, EpdChromaGridRole::White, "FACTORY_OTP_WHITE_RECOVERY",
        "L535_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_HISTORY_8X8_ABA_V1_FACTORY_OTP_WHITE_RECOVERY",
        "3638dc93576652ecbfa6747d4a1c5bc40124f14141e4d1ea5c2d3e9a5546a5eb",
        "f2695ebfec6ed1e887ae5561696fe81591f6908454e0268df2b069d4826fa585",
        "9fe8f7f1c271e4003e04ec42de0e2e27f623d0185bb942271d769ebe49cb180a",
        "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
        "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
        0x13340DC5UL, 0xB7A855C5UL, 0, 614400, 0, 0, 0, 0, 0, 0),
};

#undef RLHYO_ACTION
