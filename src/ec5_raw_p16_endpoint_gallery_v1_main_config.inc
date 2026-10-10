#include "ec5_raw_p16_endpoint_gallery_v1_identity.inc"

namespace rp16 = mf1750_raw_p16_endpoint_gallery_v1;

static constexpr const char *kClassification =
    "EXPERIMENTAL_L535_ACTIVE_RAW_ENDPOINT_OBSERVATIONS_NOT_UNIQUE_OR_QUALIFIED_COLOURS";
static constexpr const char *kProfileSource =
    "legacy_complete_535_active_global_cs1_active535_cs2_commented535";
static constexpr const char *kIdentityRevision =
    "raw-p16-endpoint-gallery-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_RAW_P16_ENDPOINT_GALLERY_DEVICE_V1";
static constexpr const char *kLayoutId = rp16::kVariantKey;
static constexpr const char *kBuildTag = rp16::kBuildTag;
static constexpr const char *kBootLabel = "EC5 RAW-P16 endpoint gallery V1";
static constexpr const char *kTestId = rp16::kTestId;
static constexpr const char *kCampaignId = rp16::kCampaignId;
static constexpr const char *kContractId = rp16::kContractId;
static constexpr const char *kVersionKind =
    "mf1750-ec5-raw-p16-endpoint-gallery-v1-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-raw-p16-endpoint-gallery-v1-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-raw-p16-endpoint-gallery-v1-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-raw-p16-endpoint-gallery-v1-report";
static constexpr const char *kBaselineRole =
    "EXTERNAL_CLEAN_FACTORY_OTP_WHITE_REQUIRED";
static constexpr const char *kExternalWhiteAnchorJson =
    "\"external_containment\":{"
    "\"outside_campaign\":true,"
    "\"factory_otp_white_before_required\":true,"
    "\"clean_white_operator_or_camera_gate_required\":true,"
    "\"runtime_code7_accepted_as_white_anchor\":false,"
    "\"pre_campaign_id\":"
    "\"EC5_RAW_P16_ENDPOINT_GALLERY_PRE_WHITE_ANCHOR_V1B\","
    "\"pre_contract_id\":"
    "\"d6c88b8df003f42fe9415682d412e4d5cd1c15ceb2ee7423c927a603d0332c61\","
    "\"pre_nvs_namespace\":\"rp16gpw_v1b\","
    "\"pre_factory_otp_white_only\":true,\"pre_automatic\":false,"
    "\"factory_otp_white_after_required\":true,"
    "\"post_campaign_id\":"
    "\"EC5_RAW_P16_ENDPOINT_GALLERY_WHITE_CONTAINMENT_V1\","
    "\"post_contract_id\":"
    "\"1d08798ba1a4012623c64625cec2edfaeb160aa3b20f0a2a98406994b55cce14\","
    "\"post_nvs_namespace\":\"rp16gw_v1\","
    "\"automatic\":false,\"white_actions_in_campaign\":0}";
static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"grid_rows\":4,\"grid_columns_per_controller\":2,"
    "\"row_codes\":[[0,1],[2,3],[4,5],[6,7]],"
    "\"grid_x_by_column\":[36,276],"
    "\"grid_y_by_row\":[36,180,324,468],"
    "\"grid_x1_local_exclusive\":476,\"grid_y1_exclusive\":564,"
    "\"cell_width\":200,\"cell_height\":96,"
    "\"gap_x\":40,\"gap_y\":48,\"background_code\":7,"
    "\"border\":false,\"same_layout_both_controllers\":true,"
    "\"controller_dtm_byte_identical\":true,"
    "\"controller_r20_payloads_byte_identical\":false,"
    "\"cs2_position_mirrored\":false,\"spatial_dither\":false,"
    "\"endpoint_observations_per_controller\":8,"
    "\"endpoint_observations_total\":16,"
    "\"unique_transport_codes\":8,"
    "\"unique_colours_claimed\":0,\"qualified_colours\":0,"
    "\"runtime_code7_is_factory_white\":false,"
    "\"factory_otp_white_ordinals\":[],\"runtime_lut_ordinals\":[1],"
    "\"one_visible_refresh_per_action\":true,"
    "\"active_global_tuple_id\":"
    "\"741848b5bf2cc07b642293d5aa3b216f1ac6eb9cdc36e7099e4230a8a837ad42\","
    "\"cs1_r20_prefix_sha256\":"
    "\"716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b\","
    "\"cs2_r20_prefix_sha256\":"
    "\"2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26\"}";
static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":false,\"window_refresh\":false,"
    "\"command_0x83\":false,\"command_0x86\":false,"
    "\"unknown_commands\":false,\"mid_refresh_power_cut\":false,"
    "\"spi_frequency_sweep\":false,\"full_screen_global_refresh\":true,"
    "\"raw_endpoint_gallery\":true,\"position_balanced_atlas\":false,"
    "\"same_palette_hold_probe\":false,"
    "\"cross_palette_hold_probe\":false,\"local_hold_claimed\":false,"
    "\"colour_qualification\":false,"
    "\"busy_qualified_arm_execute_dispatch\":true,"
    "\"main_campaign_resume_after_containment\":false,"
    "\"device_enforced_same_boot\":true";

static constexpr const char *kNvsNamespace = rp16::kNvsNamespace;
static constexpr const char *kNvsKey = "cursor_p16g";
static constexpr const char *kNvsBootKey = rp16::kNvsBootKey;
static constexpr const char *kVersionRoute =
    "/api/ec5/raw-p16-endpoint-gallery-v1/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/raw-p16-endpoint-gallery-v1/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/raw-p16-endpoint-gallery-v1/status";
static constexpr const char *kReportRoute =
    "/api/ec5/raw-p16-endpoint-gallery-v1/report";
static constexpr const char *kArmRoute =
    "/api/ec5/raw-p16-endpoint-gallery-v1/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/raw-p16-endpoint-gallery-v1/execute";

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
    "ARM_ONE_FIXED_RAW_P16_ENDPOINT_GALLERY_NOT_HARDWARE_AUTHORIZATION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ONE_ARMED_RAW_P16_ENDPOINT_GALLERY_ONCE";

static constexpr ActionDescriptor kActions[] = {{
    1,
    EpdChromaGridRole::Source,
    "RAW_P16_ACTIVE_ENDPOINT_GALLERY",
    1,
    "L535_ACTIVE_RAW_P16_ENDPOINT_GALLERY_2X4_V1_ACTIVE_GLOBAL_CODE0_TO_7_BOTH_CONTROLLERS",
    "146bbe7c331c10d410375c90d8879816427337ef21008c3e666ff74fe50b47e4",
    "9f5b84a12ac93c85898d2e843db6a5a4d174daa6ce0f18ffd8da974737f0a088",
    nullptr,
    "46e86cf0ca6c537aaf694dda7eaf599a39992e0eac004858e413b6821bff94d9",
    "d141dbb111518bf45d74ab644fb804a6d2f8272ec13cfce13b6de061e6a53606",
    "d141dbb111518bf45d74ab644fb804a6d2f8272ec13cfce13b6de061e6a53606",
    0xA47049C5UL,
    0xED2673C5UL,
    0xED2673C5UL,
    {38400, 38400, 38400, 38400, 38400, 38400, 38400, 345600},
}};
