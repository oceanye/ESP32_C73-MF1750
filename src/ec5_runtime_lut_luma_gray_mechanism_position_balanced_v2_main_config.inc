#include "ec5_runtime_lut_luma_gray_mechanism_position_balanced_v2_identity.inc"

static constexpr const char *kCompiledIdentityMarker =
    "MF1750_EC5_LGMPB2_COMPILED_IDENTITY_V1|CONTRACT=b9baafc7b0e4966a23eb1189372e36d690e8df84d8e17f4c8cbc3536be46f019|G1=5ceab793eb464bac3350f5e08b34d000338a4d1e5e254fe9746867bc27acd1ca|G2=c160bb98b5d28297480fe53f7c96b2f295fd39a03961c025926266d700491bec|G3=8595a460ea089f580516d793c6c1adb7acef1748c9ad42c28cf2394e1686d92d|G4=26310ffc6c3d2781592f4211b28677450ebd98b03468f49cda765ddf933b76be";

namespace lgmpb2 =
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v2;

static constexpr const char *kClassification =
    "EXPERIMENTAL_HISTORY_MECHANISM_POSITION_BALANCED_CANDIDATES_ZERO_QUALIFIED_GRAY_OR_BRIGHTNESS_LEVELS";
static constexpr const char *kProfileSource =
    "completed_W11_factory_OTP_white_plus_legacy_complete_535_active_commented_headers";
static constexpr const char *kIdentityRevision =
    "luma-gray-mechanism-position-balanced-v2";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_LUMA_GRAY_MECHANISM_POSITION_BALANCED_DEVICE_V2";
static constexpr const char *kLayoutId = lgmpb2::kVariantKey;
static constexpr const char *kBuildTag = lgmpb2::kBuildTag;
static constexpr const char *kBootLabel =
    "EC5 LUMA/GRAY mechanism position-balanced V2";
static constexpr const char *kTestId = lgmpb2::kTestId;
static constexpr const char *kCampaignId = lgmpb2::kCampaignId;
static constexpr const char *kContractId = lgmpb2::kContractId;
static constexpr const char *kVersionKind =
    "mf1750-ec5-luma-gray-mechanism-position-balanced-v2-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-luma-gray-mechanism-position-balanced-v2-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-luma-gray-mechanism-position-balanced-v2-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-luma-gray-mechanism-position-balanced-v2-report";
static constexpr const char *kBaselineRole = "G1_ACTIVE_C7_SOURCE";

static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"grid_rows\":8,\"grid_columns_per_controller\":8,"
    "\"candidate_cells_per_controller\":64,\"recipes\":16,"
    "\"repeats_per_recipe_per_controller\":4,"
    "\"required_valid_repeats\":\"4_of_4\","
    "\"grid_x0_local\":68,\"grid_y0\":64,"
    "\"grid_x1_local_exclusive\":444,\"grid_y1_exclusive\":536,"
    "\"cell_width\":40,\"cell_height\":52,\"gap_x\":8,\"gap_y\":8,"
    "\"border_pixels\":0,\"central_roi\":true,"
    "\"cs2_semantic_rotation_degrees\":180,"
    "\"source_code\":7,\"middle_codes\":[0,1,2,3,4,5,6,7],"
    "\"target_codes\":[3,7],"
    "\"global_header_sequence\":[\"active\",\"commented\",\"active\",\"active\"],"
    "\"g4_payload_byte_identical_to_g3\":true,"
    "\"g4_independent_explicit_manual_or_host_selection\":true,"
    "\"g4_automatic_chain\":false,"
    "\"spatial_dither\":false,\"spatial_mixing\":false,"
    "\"cell_fill_uniform_code\":true,"
    "\"full_screen_global_refresh\":true,\"partial_refresh\":false,"
    "\"source_gate_W11_complete\":true,"
    "\"source_gate_camera_visible_clean_white_review\":true,"
    "\"source_gate_absolute_white_or_uniformity_qualified\":false,"
    "\"true_neutral_gray_claimed\":false,\"qualified_gray_levels\":0,"
    "\"qualified_brightness_levels\":0,\"candidate_only\":true,"
    "\"independent_factory_otp_white_successor_required\":true,"
    "\"campaign_boot_binding_key\":\"boot_lgmpb2\","
    "\"device_enforced_same_boot\":true,\"reboot_resume_allowed\":false}";

static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":false,\"window_refresh\":false,"
    "\"command_0x83\":false,\"command_0x86\":false,"
    "\"unknown_commands\":false,\"mid_refresh_power_cut\":false,"
    "\"spi_frequency_sweep\":false,\"full_screen_global_refresh\":true,"
    "\"local_hold_claimed\":false,\"history_brightness_screening\":true,"
    "\"true_neutral_gray_claimed\":false,\"qualified_gray_levels\":0,"
    "\"qualified_brightness_levels\":0,\"candidate_only\":true,"
    "\"independent_fresh_white_containment_required\":true,"
    "\"busy_qualified_arm_execute_dispatch\":true,"
    "\"device_enforced_same_boot\":true,"
    "\"g4_manual_or_host_selection_only\":true,"
    "\"g4_autochain\":false,\"runtime_code7_used_as_white\":false";

static constexpr const char *kNvsNamespace = lgmpb2::kNvsNamespace;
static constexpr const char *kNvsKey = "cur_lgmpb2";
static constexpr const char *kNvsBootKey = lgmpb2::kNvsBootKey;
static constexpr const char *kVersionRoute =
    "/api/ec5/luma-gray-mechanism-position-balanced-v2/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/luma-gray-mechanism-position-balanced-v2/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/luma-gray-mechanism-position-balanced-v2/status";
static constexpr const char *kReportRoute =
    "/api/ec5/luma-gray-mechanism-position-balanced-v2/report";
static constexpr const char *kArmRoute =
    "/api/ec5/luma-gray-mechanism-position-balanced-v2/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/luma-gray-mechanism-position-balanced-v2/execute";

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
    "ARM_ONE_FIXED_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V2_ACTION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ONE_ARMED_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V2_ACTION_ONCE";

#define LGMPB2_ACTION(ORDINAL, DRIVER_ROLE, ROLE, BRANCH, DESCRIPTOR, ACTION, PRIOR, FRAME_SHA, CS1_SHA, CS2_SHA, FRAME_FNV, CS1_FNV, CS2_FNV, H0, H1, H2, H3, H4, H5, H6, H7) \
  {ORDINAL, DRIVER_ROLE, ROLE, 1, BRANCH, DESCRIPTOR, ACTION, PRIOR, FRAME_SHA, CS1_SHA, CS2_SHA, FRAME_FNV, CS1_FNV, CS2_FNV, {H0, H1, H2, H3, H4, H5, H6, H7}}

static constexpr ActionDescriptor kActions[] = {
    LGMPB2_ACTION(1, EpdChromaGridRole::Source,
                  "G1_ACTIVE_C7_SOURCE",
                  "L535_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V2_G1_ACTIVE_C7_SOURCE",
                  "c7caf54674dfa96ffa20d4c740d600b8aeda49ca6a5e803180281ab4c5c75ef9",
                  "5ceab793eb464bac3350f5e08b34d000338a4d1e5e254fe9746867bc27acd1ca",
                  nullptr,
                  "f27255891c2b00350b2f7aca6f0719116c6a29262008b7621ef4b7df66b099f2",
                  "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
                  "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
                  0x7C918DC5UL, 0x285715C5UL, 0x285715C5UL,
                  0, 0, 0, 0, 0, 0, 0, 614400),
    LGMPB2_ACTION(2, EpdChromaGridRole::Mid,
                  "G2_COMMENTED_C0_TO_C7_POSITION_BALANCED_MIDDLE",
                  "L535_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V2_G2_COMMENTED_C0_TO_C7_POSITION_BALANCED_MIDDLE",
                  "acb020c92e3591cf78c252fde36771a64da52655510108cd558d15a45a53584d",
                  "c160bb98b5d28297480fe53f7c96b2f295fd39a03961c025926266d700491bec",
                  "5ceab793eb464bac3350f5e08b34d000338a4d1e5e254fe9746867bc27acd1ca",
                  "297b30361ab0afa88bc47f8b5acf3835974610fb39aee2efaba3b6d9e9b610bd",
                  "1f7040ffa8c18d8b67cf1908bb161c21b8a21d1dd5d504f4dddf6d5ec7a0002a",
                  "b1295d5b0a0865bd0ecdd3d1aaa2548de407b947e16f67d8ccfbd8d4bd82b2ec",
                  0x510CAFC5UL, 0x63478BC5UL, 0x1C01EE45UL,
                  33280, 33280, 33280, 33280, 33280, 33280, 33280, 381440),
    LGMPB2_ACTION(3, EpdChromaGridRole::Target,
                  "G3_ACTIVE_C3_C7_TARGET",
                  "L535_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V2_G3_ACTIVE_C3_C7_TARGET",
                  "722742e133c173f33b2290f8c34d2f8543cf0063eb2224c98c5583724e159e88",
                  "8595a460ea089f580516d793c6c1adb7acef1748c9ad42c28cf2394e1686d92d",
                  "c160bb98b5d28297480fe53f7c96b2f295fd39a03961c025926266d700491bec",
                  "82f40036c115b3dea4d00099ef915aa693007abf73e1ddcf4d436f72807e1a1c",
                  "4e308b31900ba1e8d5d4c3a0a3a3d837771b45865a6eb5adb2b5c17f6cf5a428",
                  "77e6c478da1b3f17950da85fac2759bca95fb80a6654fd3f83e2f3af719abcf1",
                  0xDC41DAC5UL, 0xCF468BC5UL, 0xC06314C5UL,
                  0, 0, 0, 133120, 0, 0, 0, 481280),
    LGMPB2_ACTION(4, EpdChromaGridRole::ReverseSource,
                  "G4_ACTIVE_C3_C7_IDENTICAL_TARGET_REPEAT_MANUAL_ONLY",
                  "L535_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V2_G4_ACTIVE_C3_C7_IDENTICAL_TARGET_REPEAT_MANUAL_ONLY",
                  "c4ebdc9987cbed7600f7a2379cc5d2bb51033e11152818351030b95822eb4636",
                  "26310ffc6c3d2781592f4211b28677450ebd98b03468f49cda765ddf933b76be",
                  "8595a460ea089f580516d793c6c1adb7acef1748c9ad42c28cf2394e1686d92d",
                  "82f40036c115b3dea4d00099ef915aa693007abf73e1ddcf4d436f72807e1a1c",
                  "4e308b31900ba1e8d5d4c3a0a3a3d837771b45865a6eb5adb2b5c17f6cf5a428",
                  "77e6c478da1b3f17950da85fac2759bca95fb80a6654fd3f83e2f3af719abcf1",
                  0xDC41DAC5UL, 0xCF468BC5UL, 0xC06314C5UL,
                  0, 0, 0, 133120, 0, 0, 0, 481280),
};

#undef LGMPB2_ACTION
