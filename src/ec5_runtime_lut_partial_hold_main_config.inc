#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_V3_BUILD)
#include "ec5_runtime_lut_partial_hold_v3_identity.inc"
namespace rlph = mf1750_runtime_lut_partial_hold_v3;
#define RLPH_WHITE_CODE_JSON "7"
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_V2_BUILD)
#include "ec5_runtime_lut_partial_hold_v2_identity.inc"
namespace rlph = mf1750_runtime_lut_partial_hold_v2;
#define RLPH_WHITE_CODE_JSON "1"
#else
#include "ec5_runtime_lut_partial_hold_identity.inc"
namespace rlph = mf1750_runtime_lut_partial_hold;
#define RLPH_WHITE_CODE_JSON "3"
#endif

static constexpr const char *kClassification =
    "EXPERIMENTAL_SPD1657_L535_RUNTIME_LUT_PTLW_LOCAL_HOLD_CANDIDATE";
static constexpr const char *kProfileSource =
    "legacy_complete_535_reference_active_global";
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_V3_BUILD)
static constexpr const char *kIdentityRevision =
    "runtime-lut-partial-hold-v3";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_DEVICE_V3";
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_V2_BUILD)
static constexpr const char *kIdentityRevision =
    "runtime-lut-partial-hold-v2";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_DEVICE_V2";
#else
static constexpr const char *kIdentityRevision =
    "runtime-lut-partial-hold-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_DEVICE_V1";
#endif
static constexpr const char *kLayoutId = rlph::kVariantKey;
static constexpr const char *kBuildTag = rlph::kBuildTag;
static constexpr const char *kBootLabel = "EC5 runtime-LUT partial HOLD";
static constexpr const char *kTestId = rlph::kTestId;
static constexpr const char *kCampaignId = rlph::kCampaignId;
static constexpr const char *kContractId = rlph::kContractId;
static constexpr const char *kVersionKind =
    "mf1750-ec5-runtime-lut-partial-hold-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-runtime-lut-partial-hold-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-runtime-lut-partial-hold-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-runtime-lut-partial-hold-report";
static constexpr const char *kBaselineRole = "RUNTIME_LUT_WHITE_BASELINE";
static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"ptlw_command\":131,\"ptlw_payload_bytes\":9,"
    "\"ptlw_endpoint_contract\":\"xe=x+w-1;ye=y+h-1\","
    "\"cropped_dtm\":true,\"packed_bpp\":4,"
    "\"white_transport_code\":" RLPH_WHITE_CODE_JSON ","
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
    "\"full_screen_global_refresh\":true,"
    "\"same_palette_hold_probe\":true,"
    "\"cross_palette_hold_probe\":false";

static constexpr const char *kNvsNamespace = rlph::kNvsNamespace;
static constexpr const char *kNvsKey = "cursor_v1";

static constexpr const char *kVersionRoute =
    "/api/ec5/runtime-lut-partial-hold/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/runtime-lut-partial-hold/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/runtime-lut-partial-hold/status";
static constexpr const char *kReportRoute =
    "/api/ec5/runtime-lut-partial-hold/report";
static constexpr const char *kArmRoute =
    "/api/ec5/runtime-lut-partial-hold/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/runtime-lut-partial-hold/execute";

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
    "ARM_ONE_FIXED_L535_RUNTIME_LUT_PTLW_ACTION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ARMED_L535_RUNTIME_LUT_PTLW_ACTION_ONCE";

#define RLPH_ACTION(ORDINAL, DRIVER_ROLE, INDEX, PRIOR)                       \
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
    RLPH_ACTION(1, EpdChromaGridRole::White, 0, nullptr),
    RLPH_ACTION(2, EpdChromaGridRole::Source, 1,
                rlph::kActions[0].actionId),
    RLPH_ACTION(3, EpdChromaGridRole::Mid, 2,
                rlph::kActions[1].actionId),
    RLPH_ACTION(4, EpdChromaGridRole::Target, 3,
                rlph::kActions[2].actionId),
    RLPH_ACTION(5, EpdChromaGridRole::White, 4,
                rlph::kActions[3].actionId),
};

#undef RLPH_ACTION
