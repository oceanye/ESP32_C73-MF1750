#include "ec5_position_balanced_gray_hold_successor_v1_identity.inc"

namespace pbghs1 = mf1750_position_balanced_gray_hold_successor_v1;

static constexpr const char *kClassification =
    "EXPERIMENTAL_F1_G3_CANDIDATE_SPECIFIC_CLEAN_PTLW_LOCAL_HOLD_"
    "QUALIFICATION_ONLY";
static constexpr const char *kProfileSource =
    "G3_external_position_balanced_C3_C7_plus_legacy_active_commented_L535";
static constexpr const char *kIdentityRevision =
    "position-balanced-gray-hold-successor-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_DEVICE_V1";
static constexpr const char *kLayoutId = pbghs1::kVariantKey;
static constexpr const char *kBuildTag = pbghs1::kBuildTag;
static constexpr const char *kBootLabel =
    "EC5 post-G3 position-balanced gray HOLD successor V1";
static constexpr const char *kTestId = pbghs1::kTestId;
static constexpr const char *kCampaignId = pbghs1::kCampaignId;
static constexpr const char *kContractId = pbghs1::kContractId;
static constexpr const char *kVersionKind =
    "mf1750-ec5-position-balanced-gray-hold-successor-v1-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-position-balanced-gray-hold-successor-v1-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-position-balanced-gray-hold-successor-v1-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-position-balanced-gray-hold-successor-v1-report";
static constexpr const char *kBaselineRole =
    "EXTERNAL_V3_G3_COMPLETE_NOT_REPLAYED_THEN_H1";

__attribute__((used)) static const char kCompiledIdentityMarker[] =
    "MF1750_EC5_PBGHS1_COMPILED_IDENTITY_V1|"
    "CONTRACT=329e0bb6075291cc2bbdc1045a642b055b06fb8d312d2a7761b1332358e04229|"
    "H1=366e5e3f337ec2cbe713f906af0f79a083e531de836e80b9b38066c7951255f5|"
    "H2=ba7557595d9780f8ef0354abf0083b43735b5a642411aa63ce08a247f40e253c";

static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"source_campaign_id\":\"EC5_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3\","
    "\"source_contract_id\":\"a114a46bec02b5de80c1f63757723e90cf8e101a81429a8f47eabadc471e3b88\","
    "\"source_required_ordinal\":3,"
    "\"source_required_action_id\":\"f6c6bb92ae708ac325c4bca53ed12d82f19f41fa84adb1ddd8c68e35c40b86ee\","
    "\"source_g1_g2_g3_replayed\":false,\"source_g4_accepted\":false,"
    "\"g4_presence_is_hard_failure\":true,"
    "\"j2_off_app_only_flash_required\":true,"
    "\"candidate_grid\":{\"x0_local\":68,\"y0\":64,"
      "\"x1_local_exclusive\":444,\"y1_exclusive\":536,"
      "\"rows\":8,\"columns\":8,\"cell_width\":40,"
      "\"cell_height\":52,\"gap_x\":8,\"gap_y\":8},"
    "\"hold_windows\":["
      "{\"role\":\"H1\",\"x\":64,\"y\":8,\"width\":320,"
       "\"height\":24,\"cs1_code\":5,\"cs2_code\":5,"
       "\"global_header\":\"active\"},"
      "{\"role\":\"H2\",\"x\":64,\"y\":568,\"width\":320,"
       "\"height\":24,\"cs1_code\":6,\"cs2_code\":6,"
       "\"global_header\":\"commented\"}],"
    "\"windows_outside_candidate_grid\":true,"
    "\"windows_nonoverlapping\":true,"
    "\"g3_candidate_cells_retained\":128,"
    "\"all_g3_candidate_replicas_intended_to_be_retained\":true,"
    "\"full_code7_prestage_bytes_per_controller\":153600,"
    "\"full_code7_prestage_sha256\":"
      "\"3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd\","
    "\"ptlw_command\":131,\"ptlw_payload_bytes\":9,\"ptlw_mode\":1,"
    "\"ptlw_endpoint_contract\":\"xe=x+w-1;ye=y+h-1\","
    "\"ptlw_payloads_hex\":[\"0040017f0008001f01\","
      "\"0040017f0238024f01\"],"
    "\"cropped_dtm_bytes_per_controller\":[3840,3840],"
    "\"runtime_dtm_transport\":"
      "\"FULL_CODE7_PRESTAGE_THEN_INCLUSIVE_PTLW_UNIFORM_CROP\","
    "\"runtime_treatment_action_stage_cdi\":false,"
    "\"runtime_treatment_action_stage_btst2\":false,"
    "\"runtime_treatment_repeat_ptlw_after_pon_busy\":false,"
    "\"command_0x86\":false,\"qualified_hold_colours\":0,"
    "\"qualified_gray_levels\":0,\"spatial_dither\":false,"
    "\"independent_factory_otp_white_successor_required\":true,"
    "\"factory_otp_white_successor_embedded\":false}";

static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":true,\"window_refresh\":true,"
    "\"command_0x83\":true,\"command_0x86\":false,"
    "\"unknown_commands\":false,\"mid_refresh_power_cut\":false,"
    "\"spi_frequency_sweep\":false,\"full_screen_global_refresh\":false,"
    "\"cross_palette_hold_probe\":true,\"local_hold_claimed\":false,"
    "\"source_g3_replayed\":false,\"g4_accepted\":false,"
    "\"qualified_hold_colours\":0,\"qualified_gray_levels\":0,"
    "\"automatic_chaining\":false,\"retry\":false,"
    "\"fallback\":false,\"recovery\":false,"
    "\"independent_factory_otp_white_containment_required\":true";

static constexpr const char *kNvsNamespace = pbghs1::kNvsNamespace;
static constexpr const char *kNvsKey = pbghs1::kNvsKey;
static constexpr const char *kNvsBootKey = pbghs1::kNvsBootKey;
static constexpr const char *kVersionRoute =
    "/api/ec5/position-balanced-gray-hold-successor-v1/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/position-balanced-gray-hold-successor-v1/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/position-balanced-gray-hold-successor-v1/status";
static constexpr const char *kReportRoute =
    "/api/ec5/position-balanced-gray-hold-successor-v1/report";
static constexpr const char *kArmRoute =
    "/api/ec5/position-balanced-gray-hold-successor-v1/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/position-balanced-gray-hold-successor-v1/execute";

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
    "ARM_ONE_FIXED_POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1_ACTION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ARMED_POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1_ACTION_ONCE";

#define PBGHS1_ACTION(ORDINAL, DRIVER_ROLE, INDEX, PRIOR)                    \
  {                                                                          \
    ORDINAL, DRIVER_ROLE, pbghs1::kActions[INDEX].role, 1,                   \
        pbghs1::kActions[INDEX].branch,                                      \
        pbghs1::kActions[INDEX].descriptorId,                                \
        pbghs1::kActions[INDEX].actionId, PRIOR,                             \
        pbghs1::kActions[INDEX].frameSha256,                                 \
        pbghs1::kActions[INDEX].cs1DtmSha256,                                \
        pbghs1::kActions[INDEX].cs2DtmSha256,                                \
        pbghs1::kActions[INDEX].frameFnv1a,                                  \
        pbghs1::kActions[INDEX].cs1DtmFnv1a,                                 \
        pbghs1::kActions[INDEX].cs2DtmFnv1a,                                 \
        {pbghs1::kActions[INDEX].histogram[0],                               \
         pbghs1::kActions[INDEX].histogram[1],                               \
         pbghs1::kActions[INDEX].histogram[2],                               \
         pbghs1::kActions[INDEX].histogram[3],                               \
         pbghs1::kActions[INDEX].histogram[4],                               \
         pbghs1::kActions[INDEX].histogram[5],                               \
         pbghs1::kActions[INDEX].histogram[6],                               \
         pbghs1::kActions[INDEX].histogram[7]}                               \
  }

static constexpr ActionDescriptor kActions[] = {
    PBGHS1_ACTION(
        1, EpdChromaGridRole::ReverseSource, 4,
        "f6c6bb92ae708ac325c4bca53ed12d82f19f41fa84adb1ddd8c68e35c40b86ee"),
    PBGHS1_ACTION(2, EpdChromaGridRole::ReverseTarget, 5,
                  pbghs1::kActions[4].actionId),
};

#undef PBGHS1_ACTION
