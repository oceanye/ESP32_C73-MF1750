#include "ec5_p1_active_endpoint_atlas_4x8_v1_identity.inc"

namespace p1a = mf1750_p1_active_endpoint_atlas_4x8_v1;

static constexpr const char *kClassification =
    "EXPERIMENTAL_FRESH_ONE_SHOT_COMPLETE_ACTIVE_PROFILE_ENDPOINT_"
    "CANDIDATES_ZERO_QUALIFIED_LIGHTNESS_LEVELS";
static constexpr const char *kProfileSource =
    "legacy_complete_535_active_symmetric_controller_tuple";
static constexpr const char *kIdentityRevision =
    "p1-active-endpoint-atlas-4x8-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_P1_ACTIVE_ENDPOINT_ATLAS_4X8_DEVICE_V1";
static constexpr const char *kLayoutId = p1a::kVariantKey;
static constexpr const char *kBuildTag = p1a::kBuildTag;
static constexpr const char *kBootLabel = "EC5 P1 active endpoint atlas 4x8 V1";
static constexpr const char *kBootSummary =
    "One fresh one-shot complete active-profile 4x8 endpoint atlas; no "
    "source history, middle history, target repeat, HOLD, or autochain";
static constexpr const char *kTestId = p1a::kTestId;
static constexpr const char *kCampaignId = p1a::kCampaignId;
static constexpr const char *kContractId = p1a::kContractId;
static constexpr const char *kVersionKind =
    "mf1750-ec5-p1-active-endpoint-atlas-4x8-v1-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-p1-active-endpoint-atlas-4x8-v1-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-p1-active-endpoint-atlas-4x8-v1-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-p1-active-endpoint-atlas-4x8-v1-report";
static constexpr const char *kBaselineRole =
    "EXTERNAL_FRESH_FACTORY_OTP_WHITE_BEFORE_AND_INDEPENDENT_SUCCESSOR_AFTER_REQUIRED";
static constexpr const char *kExternalWhiteAnchorJson =
    "\"external_containment\":{"
    "\"outside_campaign\":true,"
    "\"factory_otp_white_before_required\":true,"
    "\"factory_otp_white_after_required\":true,"
    "\"successor_identity_bound_after_main_artifact_seal\":true,"
    "\"post_white_clean_visual_gate_required\":true,"
    "\"white_actions_in_campaign\":0}";
static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"grid_rows\":4,\"grid_columns_per_controller\":8,"
    "\"row_codes\":[[0,1,2,3,4,5,6,7],[4,5,6,7,0,1,2,3],"
    "[1,2,3,4,5,6,7,0],[5,6,7,0,1,2,3,4]],"
    "\"grid_x0_local\":20,\"grid_y_by_row\":[44,180,316,452],"
    "\"grid_x1_local_exclusive\":492,\"grid_y1_exclusive\":552,"
    "\"cell_width\":52,\"cell_height\":100,"
    "\"gap_x\":8,\"gap_y\":36,\"background_code\":7,"
    "\"border\":false,\"same_layout_both_controllers\":true,"
    "\"controller_dtm_byte_identical\":true,"
    "\"cs2_position_mirrored\":false,\"spatial_dither\":false,"
    "\"fresh_one_shot\":true,\"source_history_actions\":0,"
    "\"middle_history_actions\":0,"
    "\"identical_target_repeat_actions\":0,"
    "\"factory_otp_white_ordinals\":[],\"runtime_lut_ordinals\":[1],"
    "\"one_visible_refresh_per_action\":true,"
    "\"samples_per_code_per_controller_per_frame\":4,"
    "\"qualified_colours\":0,\"qualified_lightness_levels\":0,"
    "\"active_global_tuple_id\":"
    "\"4ba82591a96bc789f1ec2ea17ab81d4ae7e8986386cad8264a8dac48f021e820\"}";
static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":false,\"window_refresh\":false,"
    "\"command_0x83\":false,\"command_0x86\":false,"
    "\"unknown_commands\":false,\"mid_refresh_power_cut\":false,"
    "\"spi_frequency_sweep\":false,\"full_screen_global_refresh\":true,"
    "\"fresh_one_shot_endpoint_atlas\":true,"
    "\"complete_profile_tuple\":true,"
    "\"position_balanced_atlas\":true,\"same_palette_hold_probe\":false,"
    "\"cross_palette_hold_probe\":false,\"local_hold_claimed\":false,"
    "\"colour_qualification\":false,\"lightness_qualification\":false,"
    "\"history_sequence\":false,\"identical_target_repeat\":false,"
    "\"busy_qualified_arm_execute_dispatch\":true,"
    "\"main_campaign_resume_after_containment\":false,"
    "\"device_enforced_same_boot\":true";

static constexpr const char *kNvsNamespace = p1a::kNvsNamespace;
static constexpr const char *kNvsKey = "cursor_p1a";
static constexpr const char *kNvsBootKey = p1a::kNvsBootKey;
static constexpr const char *kVersionRoute =
    "/api/ec5/p1-active-endpoint-atlas-4x8-v1/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/p1-active-endpoint-atlas-4x8-v1/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/p1-active-endpoint-atlas-4x8-v1/status";
static constexpr const char *kReportRoute =
    "/api/ec5/p1-active-endpoint-atlas-4x8-v1/report";
static constexpr const char *kArmRoute =
    "/api/ec5/p1-active-endpoint-atlas-4x8-v1/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/p1-active-endpoint-atlas-4x8-v1/execute";

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
    "ARM_ONE_FIXED_P1_ACTIVE_ENDPOINT_ATLAS_NOT_HARDWARE_AUTHORIZATION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ONE_ARMED_P1_ACTIVE_ENDPOINT_ATLAS_ONCE";

static constexpr ActionDescriptor kActions[] = {{
    1,
    EpdChromaGridRole::Source,
    "P1_ACTIVE_COMPLETE_PROFILE_POSITION_BALANCED_4X8_ENDPOINT_ATLAS",
    1,
    "P1_FRESH_ONE_SHOT_ACTIVE_ACTIVE_ENDPOINT_ATLAS_4X8_V1",
    "14a1b108c74e8898a1e5cc235ff93fdc8b315aebc45fc4682481a6aa915187d2",
    "7d14bc5f70da46f1eb3a86ab1c54734dffa1e9dcac62147a1d62bcedb25e9526",
    nullptr,
    "d8ee6b0889c8c2e92e3d0d34410f93d90f924816c59987de496ef0ca27ac1768",
    "b64c835514b4b6110002c1c2cb366a93bf804f5953229107fa52b27de83dfe0f",
    "b64c835514b4b6110002c1c2cb366a93bf804f5953229107fa52b27de83dfe0f",
    0xBA8135C5UL,
    0xFA8EE9C5UL,
    0xFA8EE9C5UL,
    {41600, 41600, 41600, 41600, 41600, 41600, 41600, 323200},
}};
