#include "ec5_runtime_lut_partial_hold_repeat_ptlw_v1_identity.inc"

namespace rlph = mf1750_runtime_lut_partial_hold_repeat_ptlw_v1;

static constexpr const char *kClassification =
    "EXPERIMENTAL_SPD1657_L535_RUNTIME_LUT_POST_PON_REPEAT_PTLW_"
    "EXTERNAL_FACTORY_WHITE_ANCHOR_REQUIRED";
static constexpr const char *kProfileSource =
    "legacy_complete_535_reference_active_global";
static constexpr const char *kIdentityRevision =
    "runtime-lut-partial-hold-repeat-ptlw-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_DEVICE_V1";
static constexpr const char *kLayoutId = rlph::kVariantKey;
static constexpr const char *kBuildTag = rlph::kBuildTag;
static constexpr const char *kBootLabel =
    "EC5 runtime-LUT repeat-PTLW boundary probe";
static constexpr const char *kTestId = rlph::kTestId;
static constexpr const char *kCampaignId = rlph::kCampaignId;
static constexpr const char *kContractId = rlph::kContractId;
static constexpr const char *kVersionKind =
    "mf1750-ec5-runtime-lut-repeat-ptlw-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-runtime-lut-repeat-ptlw-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-runtime-lut-repeat-ptlw-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-runtime-lut-repeat-ptlw-report";
static constexpr const char *kBaselineRole =
    "EXTERNAL_FACTORY_OTP_CLEAN_WHITE";
static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"external_factory_white_anchor_required\":true,"
    "\"anchor_established_by_firmware\":false,"
    "\"anchor_model_code_not_transported\":7,"
    "\"runtime_code7_action_reachable\":false,"
    "\"full_white_dtm_transport\":null,"
    "\"ptlw_command\":131,\"ptlw_payload_bytes\":9,"
    "\"ptlw_endpoint_contract\":\"xe=x+w-1;ye=y+h-1\","
    "\"ptlw_mode\":1,\"ptlw_writes_per_controller\":2,"
    "\"initial_ptlw_before_cropped_dtm\":true,"
    "\"repeat_ptlw_after_pon_busy\":true,"
    "\"pre_pon_cdi_ff_preserved\":true,"
    "\"post_pon_sequence\":[\"PTLW_CS1\",\"PTLW_CS2\","
    "\"CDI_FF_BOTH\",\"BTST2\",\"DRF\"],"
    "\"cropped_dtm\":true,\"packed_bpp\":4,"
    "\"windows_disjoint\":true,\"cs2_position_mirrored\":false,"
    "\"runtime_lut_profile_id\":"
    "\"LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535\","
    "\"global_header_profile\":\"legacy_active\","
    "\"cs1_r20_prefix_bytes\":535,"
    "\"cs1_r20_prefix_sha256\":"
    "\"716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b\","
    "\"cs2_r20_prefix_bytes\":535,"
    "\"cs2_r20_prefix_sha256\":"
    "\"2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26\","
    "\"r21_bytes\":704,"
    "\"r21_sha256\":"
    "\"24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f\","
    "\"sequential_hold_observation_required\":true,"
    "\"camera_required\":false}";
static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":true,\"window_refresh\":true,"
    "\"command_0x83\":true,\"command_0x86\":false,"
    "\"mid_refresh_power_cut\":false,"
    "\"spi_frequency_sweep\":false,"
    "\"full_screen_global_refresh\":false,"
    "\"same_palette_hold_probe\":true,"
    "\"cross_palette_hold_probe\":false";

static constexpr const char *kNvsNamespace = rlph::kNvsNamespace;
static constexpr const char *kNvsKey = "cursor_rptlw_v1";

static constexpr const char *kVersionRoute =
    "/api/ec5/runtime-lut-repeat-ptlw/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/runtime-lut-repeat-ptlw/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/runtime-lut-repeat-ptlw/status";
static constexpr const char *kReportRoute =
    "/api/ec5/runtime-lut-repeat-ptlw/report";
static constexpr const char *kArmRoute =
    "/api/ec5/runtime-lut-repeat-ptlw/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/runtime-lut-repeat-ptlw/execute";

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
    "ARM_ONE_FIXED_L535_POST_PON_REPEAT_PTLW_ACTION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ARMED_L535_POST_PON_REPEAT_PTLW_ACTION_ONCE";

#define RLPH_REPEAT_ACTION(ORDINAL, DRIVER_ROLE, INDEX, PRIOR)                \
  {                                                                          \
    ORDINAL, DRIVER_ROLE, rlph::kActions[INDEX].role, 1,                     \
        rlph::kActions[INDEX].branch, rlph::kActions[INDEX].descriptorId,    \
        rlph::kActions[INDEX].actionId, PRIOR,                               \
        rlph::kActions[INDEX].frameSha256,                                   \
        rlph::kActions[INDEX].cs1DtmSha256,                                  \
        rlph::kActions[INDEX].cs2DtmSha256,                                  \
        rlph::kActions[INDEX].frameFnv1a,                                    \
        rlph::kActions[INDEX].cs1DtmFnv1a,                                  \
        rlph::kActions[INDEX].cs2DtmFnv1a,                                  \
        {rlph::kActions[INDEX].histogram[0],                                 \
         rlph::kActions[INDEX].histogram[1],                                 \
         rlph::kActions[INDEX].histogram[2],                                 \
         rlph::kActions[INDEX].histogram[3],                                 \
         rlph::kActions[INDEX].histogram[4],                                 \
         rlph::kActions[INDEX].histogram[5],                                 \
         rlph::kActions[INDEX].histogram[6],                                 \
         rlph::kActions[INDEX].histogram[7]}                                 \
  }

static constexpr ActionDescriptor kActions[] = {
    RLPH_REPEAT_ACTION(1, EpdChromaGridRole::Source, 0, nullptr),
    RLPH_REPEAT_ACTION(2, EpdChromaGridRole::Mid, 1,
                       rlph::kActions[0].actionId),
    RLPH_REPEAT_ACTION(3, EpdChromaGridRole::Target, 2,
                       rlph::kActions[1].actionId),
};

#undef RLPH_REPEAT_ACTION
