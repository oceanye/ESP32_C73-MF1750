#include "ec5_runtime_lut_same_r20_parity_4x8_v2_identity.inc"

namespace srp = mf1750_runtime_lut_same_r20_parity_4x8_v2;

static constexpr const char *kClassification =
    "EXPERIMENTAL_POSITION_BALANCED_SAME_R20_CONTROLLER_PARITY_NOT_ABSOLUTE_COLOUR_QUALIFICATION";
static constexpr const char *kProfileSource =
    "legacy_complete_535_active_symmetric_controller_tuple";
static constexpr const char *kIdentityRevision =
    "same-r20-dual-controller-position-balanced-4x8-v2";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_SAME_R20_PARITY_4X8_DEVICE_V2";
static constexpr const char *kLayoutId = srp::kVariantKey;
static constexpr const char *kBuildTag = srp::kBuildTag;
static constexpr const char *kBootLabel = "EC5 same-R20 parity 4x8 V2";
static constexpr const char *kBootSummary =
    "One fixed active L535 position-balanced 4x8 full-frame atlas; "
    "runtime code 7 is also the unqualified background";
static constexpr const char *kTestId = srp::kTestId;
static constexpr const char *kCampaignId = srp::kCampaignId;
static constexpr const char *kContractId = srp::kContractId;
static constexpr const char *kVersionKind =
    "mf1750-ec5-same-r20-parity-4x8-v2-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-same-r20-parity-4x8-v2-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-same-r20-parity-4x8-v2-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-same-r20-parity-4x8-v2-report";
static constexpr const char *kBaselineRole =
    "EXTERNAL_FACTORY_OTP_WHITE_BEFORE_AND_AFTER_REQUIRED";
static constexpr const char *kExternalWhiteAnchorJson =
    "\"external_containment\":{"
    "\"outside_campaign\":true,"
    "\"factory_otp_white_before_required\":true,"
    "\"factory_otp_white_after_required\":true,"
    "\"off_white_photos_before_atlas_required\":3,"
    "\"off_retained_atlas_photos_required\":3,"
    "\"post_white_clean_visual_gate_required\":true,"
    "\"white_actions_in_campaign\":0}";
static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"grid_rows\":4,\"grid_columns_per_controller\":8,"
    "\"row_codes\":[[0,1,2,3,4,5,6,7],[6,7,0,1,2,3,4,5],"
    "[5,4,7,6,1,0,3,2],[3,2,5,4,7,6,1,0]],"
    "\"grid_x0_local\":20,\"grid_y_by_row\":[44,180,316,452],"
    "\"grid_x1_local_exclusive\":492,\"grid_y1_exclusive\":552,"
    "\"cell_width\":52,\"cell_height\":100,"
    "\"gap_x\":8,\"gap_y\":36,\"background_code\":7,"
    "\"border\":false,\"same_layout_both_controllers\":true,"
    "\"controller_dtm_byte_identical\":true,"
    "\"cs2_position_mirrored\":false,\"spatial_dither\":false,"
    "\"factory_otp_white_ordinals\":[],\"runtime_lut_ordinals\":[1],"
    "\"one_visible_refresh_per_action\":true,"
    "\"required_samples_per_code_per_controller\":12,"
    "\"qualified_colours\":0,\"colour_equivalence_claimed\":false,"
    "\"controller_bus_capture_claimed\":false,"
    "\"active_global_tuple_id\":"
    "\"4ba82591a96bc789f1ec2ea17ab81d4ae7e8986386cad8264a8dac48f021e820\"}";
static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":false,\"window_refresh\":false,"
    "\"command_0x83\":false,\"command_0x86\":false,"
    "\"unknown_commands\":false,\"mid_refresh_power_cut\":false,"
    "\"spi_frequency_sweep\":false,\"full_screen_global_refresh\":true,"
    "\"same_r20_controller_parity_probe\":true,"
    "\"position_balanced_atlas\":true,\"same_palette_hold_probe\":false,"
    "\"cross_palette_hold_probe\":false,\"local_hold_claimed\":false,"
    "\"colour_qualification\":false,"
    "\"human_observation_gate_after_every_action\":false,"
    "\"busy_qualified_arm_execute_dispatch\":true,"
    "\"main_campaign_resume_after_containment\":false,"
    "\"device_enforced_same_boot\":true";

static constexpr const char *kNvsNamespace = srp::kNvsNamespace;
static constexpr const char *kNvsKey = "cursor_s4v2";
static constexpr const char *kNvsBootKey = srp::kNvsBootKey;
static constexpr const char *kVersionRoute =
    "/api/ec5/same-r20-parity-4x8-v2/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/same-r20-parity-4x8-v2/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/same-r20-parity-4x8-v2/status";
static constexpr const char *kReportRoute =
    "/api/ec5/same-r20-parity-4x8-v2/report";
static constexpr const char *kArmRoute =
    "/api/ec5/same-r20-parity-4x8-v2/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/same-r20-parity-4x8-v2/execute";

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
    "ARM_ONE_FIXED_SAME_R20_4X8_PARITY_ACTION_NOT_HARDWARE_AUTHORIZATION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ONE_ARMED_SAME_R20_4X8_PARITY_ACTION_ONCE";

static constexpr ActionDescriptor kActions[] = {{
    1,
    EpdChromaGridRole::Source,
    "SAME_R20_ACTIVE_ACTIVE_POSITION_BALANCED_4X8_ATLAS",
    1,
    "L535_SAME_R20_DUAL_CONTROLLER_PARITY_4X8_V2_ACTIVE_ACTIVE_POSITION_BALANCED_ATLAS",
    "7f668842d3d4fca179049b309c298d0ff2d359c6bdd26550704e6929f1108cda",
    "2eef95155b78ee27b13e5971c40618106779495c80e0e3ef833eb2484f420476",
    nullptr,
    "1ff9588f4f7d00d7e9dd0a89d2c4fb08c25db7e6e044ee467af6187b3270ad23",
    "2edcd090619b3a690b1d23db70df9b7648bad40b0512887df8a380a6f53fd1cb",
    "2edcd090619b3a690b1d23db70df9b7648bad40b0512887df8a380a6f53fd1cb",
    0x7F8C2EC5UL,
    0x8BA37FC5UL,
    0x8BA37FC5UL,
    {41600, 41600, 41600, 41600, 41600, 41600, 41600, 323200},
}};
