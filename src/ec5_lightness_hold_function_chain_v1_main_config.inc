#include "ec5_lightness_hold_function_chain_v1_identity.inc"

namespace lhfc1 = mf1750_lightness_hold_function_chain_v1;

static constexpr const char *kClassification =
    "EXPERIMENTAL_STABLE_CODE0_LATIN_CONSTRUCTION_PLUS_CLEAN_PTLW_"
    "CROSS_LUT_LOCAL_HOLD_CANDIDATES_ONLY";
static constexpr const char *kProfileSource =
    "V3_exact_packed_grid_plus_legacy_complete_535_active_commented_globals";
static constexpr const char *kIdentityRevision =
    "lightness-hold-function-chain-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_LIGHTNESS_HOLD_FUNCTION_CHAIN_DEVICE_V1";
static constexpr const char *kLayoutId = lhfc1::kVariantKey;
static constexpr const char *kBuildTag = lhfc1::kBuildTag;
static constexpr const char *kBootLabel =
    "EC5 lightness construction plus cross-LUT local HOLD V1";
static constexpr const char *kTestId = lhfc1::kTestId;
static constexpr const char *kCampaignId = lhfc1::kCampaignId;
static constexpr const char *kContractId = lhfc1::kContractId;
static constexpr const char *kVersionKind =
    "mf1750-ec5-lightness-hold-function-chain-v1-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-lightness-hold-function-chain-v1-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-lightness-hold-function-chain-v1-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-lightness-hold-function-chain-v1-report";
static constexpr const char *kBaselineRole =
    "L1_FIXED_ACTIVE_SOURCE_CODE7";

static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"candidate_cells_per_controller\":64,"
    "\"candidate_cells_total_observations\":128,"
    "\"grid_rows\":8,\"grid_columns_per_controller\":8,"
    "\"grid_x0_local\":20,\"grid_y0\":40,"
    "\"grid_x1_local_exclusive\":492,\"grid_y1_exclusive\":560,"
    "\"cell_width\":52,\"cell_height\":58,\"gap_x\":8,\"gap_y\":8,"
    "\"source_global_header\":\"active\",\"source_code\":7,"
    "\"middle_global_header\":\"commented\","
    "\"middle_codes\":[0,1,2,3,4,5,6,7],"
    "\"target_global_header\":\"active\",\"target_code\":0,"
    "\"profile_sequence\":[\"active\",\"commented\",\"active\","
    "\"active\",\"commented\"],"
    "\"cs1_layout\":\"latin_code=(row+column)%8\","
    "\"cs2_layout\":\"rotate_180_of_cs1\","
    "\"controller_color_equivalence_claimed\":false,"
    "\"qualified_colors\":0,\"qualified_gray_levels\":0,"
    "\"brightness_candidates_only\":true,\"spatial_dither\":false,"
    "\"hold_windows\":["
      "{\"role\":\"H1\",\"x\":64,\"y\":8,\"width\":384,"
       "\"height\":24,\"code\":5,\"global_header\":\"active\"},"
      "{\"role\":\"H2\",\"x\":64,\"y\":568,\"width\":384,"
       "\"height\":24,\"code\":6,\"global_header\":\"commented\"}],"
    "\"hold_windows_nonoverlap_candidate_grid\":true,"
    "\"runtime_code7_full_dtm_prestage\":true,"
    "\"runtime_code7_prestage_bytes_per_controller\":153600,"
    "\"runtime_code7_prestage_sha256\":"
      "\"3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd\","
    "\"ptlw_command\":131,\"ptlw_payload_bytes\":9,\"ptlw_mode\":1,"
    "\"ptlw_endpoint_contract\":\"xe=x+w-1;ye=y+h-1\","
    "\"ptlw_payloads_hex\":[\"004001bf0008001f01\","
      "\"004001bf0238024f01\"],"
    "\"runtime_target_dtm_bytes_per_controller\":4608,"
    "\"runtime_dtm_transport\":"
      "\"FULL_CODE7_PRESTAGE_THEN_INCLUSIVE_PTLW_UNIFORM_CROP\","
    "\"runtime_treatment_action_stage_cdi\":false,"
    "\"runtime_treatment_action_stage_btst2\":false,"
    "\"runtime_treatment_repeat_ptlw_after_pon_busy\":false,"
    "\"command_0x86\":false,"
    "\"source_authority\":{"
      "\"authority_kind\":\"V3_WHITE_SUCCESSOR_COMPLETE_CAPTURE_RELAY_OFF_PLUS_INDEPENDENT_CLEAN_WHITE_REVIEW\","
      "\"sealed\":true,"
      "\"state\":\"SEALED\","
      "\"missing_requirements\":[],"
      "\"source_action_sha256\":\"9ebc3ca4f32ceba8cbb356aece938d28e922e016f875ab10aa082338993b509b\","
      "\"source_action_canonical_sha256\":\"555b94739704096bde278ee3e0c3eb5ac901ccc7d390481f725093467a6c414b\","
      "\"source_capture_sha256\":\"479c7451ca87c60cbef614895e3a3866a8415d0f3ccf3ad82668ae321bb459ae\","
      "\"source_capture_canonical_sha256\":\"7e9f7b6b9edb1e246da06316153e24e846761bc1c02fdf3a02fa5d1384ac7362\","
      "\"source_photo_sha256\":\"f04bc44ad4e92007f7ffd2a730a28fe602acf18d34b98d2540c5959c7a46d92a\","
      "\"source_relay_off_sha256\":\"1fa84d45b7374fce680bdadcde0edb2142adfa408b5511edfa75dd20f0b09626\","
      "\"source_relay_off_canonical_sha256\":\"5ebe1472699eccfd53b4b7013f67de6e818734342d6a4f680b148f7a5ce19400\","
      "\"clean_white_review_sha256\":\"50ce755e3ed04790819c326bbbb1e6a2fdc3c6b587899f02b00da588d5e2d625\","
      "\"clean_white_review_canonical_sha256\":\"7de626ce68c5dc2952a0c17cdc41cd59ced97191f14344713f71bcb6b4a5ab40\","
      "\"clean_white_review_id\":\"b0a62b0c7dbf178fa6a2763d0bebf417b61dda6bd86bab701c84f658ae2ba96f\","
      "\"review_digest_invented\":false,"
      "\"required_before_any_device_request\":true},"
    "\"independent_factory_otp_white_successor_required\":true,"
    "\"factory_otp_white_successor_embedded\":false}";

static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":true,\"window_refresh\":true,"
    "\"command_0x83\":true,\"command_0x86\":false,"
    "\"unknown_commands\":false,\"mid_refresh_power_cut\":false,"
    "\"spi_frequency_sweep\":false,\"full_screen_global_refresh\":true,"
    "\"cross_palette_hold_probe\":true,\"local_hold_claimed\":false,"
    "\"history_brightness_screening\":true,"
    "\"brightness_candidates_only\":true,\"qualified_brightness_levels\":0,"
    "\"source_authority_sealed\":true,\"live_authorized\":true,"
    "\"automatic_chaining\":false,\"retry\":false,\"recovery\":false,"
    "\"independent_factory_otp_white_containment_required\":true";

static constexpr const char *kNvsNamespace = lhfc1::kNvsNamespace;
static constexpr const char *kNvsKey = lhfc1::kNvsKey;
static constexpr const char *kNvsBootKey = lhfc1::kNvsBootKey;
static constexpr const char *kVersionRoute =
    "/api/ec5/lightness-hold-function-chain-v1/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/lightness-hold-function-chain-v1/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/lightness-hold-function-chain-v1/status";
static constexpr const char *kReportRoute =
    "/api/ec5/lightness-hold-function-chain-v1/report";
static constexpr const char *kArmRoute =
    "/api/ec5/lightness-hold-function-chain-v1/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/lightness-hold-function-chain-v1/execute";

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
    "ARM_ONE_FIXED_LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_ACTION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ARMED_LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_ACTION_ONCE";

#define LHFC1_ACTION(ORDINAL, DRIVER_ROLE, INDEX, PRIOR)                     \
  {                                                                          \
    ORDINAL, DRIVER_ROLE, lhfc1::kActions[INDEX].role, 1,                    \
        lhfc1::kActions[INDEX].branch,                                       \
        lhfc1::kActions[INDEX].descriptorId,                                 \
        lhfc1::kActions[INDEX].actionId, PRIOR,                              \
        lhfc1::kActions[INDEX].frameSha256,                                  \
        lhfc1::kActions[INDEX].cs1DtmSha256,                                 \
        lhfc1::kActions[INDEX].cs2DtmSha256,                                 \
        lhfc1::kActions[INDEX].frameFnv1a,                                   \
        lhfc1::kActions[INDEX].cs1DtmFnv1a,                                  \
        lhfc1::kActions[INDEX].cs2DtmFnv1a,                                  \
        {lhfc1::kActions[INDEX].histogram[0],                                \
         lhfc1::kActions[INDEX].histogram[1],                                \
         lhfc1::kActions[INDEX].histogram[2],                                \
         lhfc1::kActions[INDEX].histogram[3],                                \
         lhfc1::kActions[INDEX].histogram[4],                                \
         lhfc1::kActions[INDEX].histogram[5],                                \
         lhfc1::kActions[INDEX].histogram[6],                                \
         lhfc1::kActions[INDEX].histogram[7]}                                \
  }

static constexpr ActionDescriptor kActions[] = {
    LHFC1_ACTION(1, EpdChromaGridRole::Source, 1, nullptr),
    LHFC1_ACTION(2, EpdChromaGridRole::Mid, 2,
                 lhfc1::kActions[1].actionId),
    LHFC1_ACTION(3, EpdChromaGridRole::Target, 3,
                 lhfc1::kActions[2].actionId),
    LHFC1_ACTION(4, EpdChromaGridRole::ReverseSource, 4,
                 lhfc1::kActions[3].actionId),
    LHFC1_ACTION(5, EpdChromaGridRole::ReverseTarget, 5,
                 lhfc1::kActions[4].actionId),
};

#undef LHFC1_ACTION
