#include "ec5_runtime_lut_same_r20_parity_v1_identity.inc"

namespace srp = mf1750_runtime_lut_same_r20_parity_v1;

static constexpr const char *kClassification =
    "EXPERIMENTAL_SAME_R20_CONTROLLER_PARITY_NOT_COLOUR_QUALIFICATION";
static constexpr const char *kProfileSource =
    "factory_otp_white_and_legacy_complete_535_active_or_commented_"
    "symmetric_controller_tuple";
static constexpr const char *kIdentityRevision =
    "same-r20-dual-controller-parity-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_SAME_R20_PARITY_DEVICE_V1";
static constexpr const char *kLayoutId = srp::kVariantKey;
static constexpr const char *kBuildTag = srp::kBuildTag;
static constexpr const char *kBootLabel = "EC5 same-R20 parity 2x4";
static constexpr const char *kTestId = srp::kTestId;
static constexpr const char *kCampaignId = srp::kCampaignId;
static constexpr const char *kContractId = srp::kContractId;
static constexpr const char *kVersionKind =
    "mf1750-ec5-same-r20-parity-v1-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-same-r20-parity-v1-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-same-r20-parity-v1-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-same-r20-parity-v1-report";
static constexpr const char *kBaselineRole =
    "V3_FACTORY_OTP_WHITE_SUCCESSOR_REQUIRED_BEFORE_CAMPAIGN";
static constexpr const char *kExternalWhiteAnchorJson =
    "\"external_white_anchor\":{"
    "\"campaign_id\":"
    "\"EC5_TARGET_HUE_REDPINK_BRIGHTNESS_V3_WHITE_CONTAINMENT_SUCCESSOR\","
    "\"contract_id\":"
    "\"1618436e99a0ee1afd9ce16e534f3cf7e34151ddb5f0d6a757aee860aff1a227\","
    "\"action_id\":"
    "\"76517f9d6ba090cef2f4f3fd32bcda6a5466b41aeeef5ce31a5520ac1dbbceed\","
    "\"firmware_bin_sha256\":"
    "\"3721b60c23662fb34fa467fc6873bf858fb579c7c01ab2a486f9456ca1da1cfb\","
    "\"firmware_elf_sha256\":"
    "\"2baf26d20280d316063f6bd26bc7f39e7526d47e5af09a46c4f34346464c7797\","
    "\"required_outcome\":\"complete_pass\","
    "\"required_clean_white_visual_gate\":true,"
    "\"resume_source_campaign\":false,"
    "\"evidence_path\":"
    "\".test-output/hardware/MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_WHITE_"
    "CONTAINMENT_SUCCESSOR_20260828_V3/action-01-factory-otp-white.json\"}";
static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"grid_rows\":2,\"grid_columns_per_controller\":4,"
    "\"codes\":[0,1,2,3,4,5,6,7],"
    "\"grid_x0_local\":40,\"grid_y0\":120,"
    "\"grid_x1_local_exclusive\":484,\"grid_y1_exclusive\":400,"
    "\"cell_width\":96,\"cell_height\":120,"
    "\"gap_x\":20,\"gap_y\":40,"
    "\"same_layout_both_controllers\":true,"
    "\"controller_dtm_byte_identical\":true,"
    "\"cs2_position_mirrored\":false,\"spatial_dither\":false,"
    "\"factory_otp_white_ordinals\":[2,4],"
    "\"runtime_lut_ordinals\":[1,3],"
    "\"one_visible_refresh_per_action\":true,"
    "\"qualified_colours\":0,\"colour_equivalence_claimed\":false,"
    "\"controller_bus_capture_claimed\":false,"
    "\"active_global_tuple_id\":"
    "\"4ba82591a96bc789f1ec2ea17ab81d4ae7e8986386cad8264a8dac48f021e820\","
    "\"commented_global_tuple_id\":"
    "\"1d4efb64203093929779a31321695100a6c778367157d633a2dcccabdbdc4038\"}";
static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":false,\"window_refresh\":false,"
    "\"command_0x83\":false,\"command_0x86\":false,"
    "\"unknown_commands\":false,\"mid_refresh_power_cut\":false,"
    "\"spi_frequency_sweep\":false,\"full_screen_global_refresh\":true,"
    "\"same_r20_controller_parity_probe\":true,"
    "\"same_palette_hold_probe\":false,\"cross_palette_hold_probe\":false,"
    "\"local_hold_claimed\":false,\"colour_qualification\":false,"
    "\"human_observation_gate_after_every_action\":true,"
    "\"busy_qualified_arm_execute_dispatch\":true,"
    "\"main_campaign_resume_after_containment\":false,"
    "\"device_enforced_same_boot\":true";

static constexpr const char *kNvsNamespace = srp::kNvsNamespace;
static constexpr const char *kNvsKey = "cursor_srp1";
static constexpr const char *kNvsBootKey = srp::kNvsBootKey;
static constexpr const char *kVersionRoute =
    "/api/ec5/same-r20-parity-v1/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/same-r20-parity-v1/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/same-r20-parity-v1/status";
static constexpr const char *kReportRoute =
    "/api/ec5/same-r20-parity-v1/report";
static constexpr const char *kArmRoute =
    "/api/ec5/same-r20-parity-v1/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/same-r20-parity-v1/execute";

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
    "ARM_ONE_FIXED_SAME_R20_PARITY_ACTION_NOT_HARDWARE_AUTHORIZATION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ONE_ARMED_SAME_R20_PARITY_ACTION_ONCE";

#define SRP_ACTION(ORDINAL, DRIVER_ROLE, ROLE, BRANCH, DESCRIPTOR, ACTION,     \
                   PRIOR, FRAME_SHA, DTM_SHA, FRAME_FNV, DTM_FNV, H0, H1, H2, \
                   H3, H4, H5, H6, H7)                                        \
  {                                                                            \
    ORDINAL, DRIVER_ROLE, ROLE, 1, BRANCH, DESCRIPTOR, ACTION, PRIOR,           \
        FRAME_SHA, DTM_SHA, DTM_SHA, FRAME_FNV, DTM_FNV, DTM_FNV,              \
        {H0, H1, H2, H3, H4, H5, H6, H7}                                      \
  }

static constexpr ActionDescriptor kActions[] = {
    SRP_ACTION(
        1, EpdChromaGridRole::Source, "SAME_R20_ACTIVE_ACTIVE_ATLAS",
        "L535_SAME_R20_DUAL_CONTROLLER_PARITY_2X4_V1_SAME_R20_ACTIVE_ACTIVE_ATLAS",
        "246de22c2a8f450752a960230bd88de7a62ce42300c7f6401bbb562d07ef76ba",
        "7dd101c61553c9a10b97beeb7c3c8ce26e79c410d3b2ac3040db572065fd49f4",
        nullptr,
        "79182e188e32cd320cdaec36dee4410d06d603b1a155c8328bb63cfbdfbab2d6",
        "f85f377c573d9747821c0264ec3b59e488cd99732c566e54b3454486813682da",
        0x93B39DC5UL, 0xA1E81DC5UL, 23040, 23040, 23040, 23040, 23040,
        23040, 23040, 453120),
    SRP_ACTION(
        2, EpdChromaGridRole::White,
        "FACTORY_OTP_WHITE_AFTER_ACTIVE_ACTIVE",
        "L535_SAME_R20_DUAL_CONTROLLER_PARITY_2X4_V1_FACTORY_OTP_WHITE_AFTER_ACTIVE_ACTIVE",
        "becf21026a58d964c576698dd007904c600b1a5f46a3d02d241d83b7583da7b3",
        "f4d447808e151be7860e3a59afe41e5030072fabdb51a566c83c83a642318816",
        "7dd101c61553c9a10b97beeb7c3c8ce26e79c410d3b2ac3040db572065fd49f4",
        "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
        "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
        0x13340DC5UL, 0xB7A855C5UL, 0, 614400, 0, 0, 0, 0, 0, 0),
    SRP_ACTION(
        3, EpdChromaGridRole::Mid,
        "SAME_R20_COMMENTED_COMMENTED_ATLAS",
        "L535_SAME_R20_DUAL_CONTROLLER_PARITY_2X4_V1_SAME_R20_COMMENTED_COMMENTED_ATLAS",
        "556b730c7c115dc956f7b547064df0145ccfdfc55cd2bf8dd7e170718cbb2af2",
        "e62b7b784ddd4108f18606d9b34b0341c41bc82225576fa4ae0849117de2b381",
        "f4d447808e151be7860e3a59afe41e5030072fabdb51a566c83c83a642318816",
        "79182e188e32cd320cdaec36dee4410d06d603b1a155c8328bb63cfbdfbab2d6",
        "f85f377c573d9747821c0264ec3b59e488cd99732c566e54b3454486813682da",
        0x93B39DC5UL, 0xA1E81DC5UL, 23040, 23040, 23040, 23040, 23040,
        23040, 23040, 453120),
    SRP_ACTION(
        4, EpdChromaGridRole::White,
        "FACTORY_OTP_WHITE_AFTER_COMMENTED_COMMENTED",
        "L535_SAME_R20_DUAL_CONTROLLER_PARITY_2X4_V1_FACTORY_OTP_WHITE_AFTER_COMMENTED_COMMENTED",
        "10b8d5e08e484f6973b2980e1aa9565cdf3e4402468077e64ccf820469818a21",
        "711ba3e2310347645f6734537041959eb6f6dd419d26882bdc4264ad66fdc717",
        "e62b7b784ddd4108f18606d9b34b0341c41bc82225576fa4ae0849117de2b381",
        "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
        "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
        0x13340DC5UL, 0xB7A855C5UL, 0, 614400, 0, 0, 0, 0, 0, 0),
};

#undef SRP_ACTION
