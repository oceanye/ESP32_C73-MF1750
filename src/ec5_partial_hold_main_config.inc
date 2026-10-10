#include "ec5_partial_hold_identity.inc"

namespace ph = mf1750_partial_hold;

static constexpr const char *kClassification =
    "EXPERIMENTAL_SPD1657_PTLW_FACTORY_OTP_LOCAL_HOLD_CANDIDATE";
static constexpr const char *kProfileSource = "factory_otp";
static constexpr const char *kIdentityRevision = "partial-hold-v1";
static constexpr const char *kDeviceApiVersion =
    "MF1750_EC5_PARTIAL_HOLD_DEVICE_V1";
static constexpr const char *kLayoutId = ph::kVariantKey;
static constexpr const char *kBuildTag = ph::kBuildTag;
static constexpr const char *kBootLabel = "EC5 partial HOLD";
static constexpr const char *kTestId = ph::kTestId;
static constexpr const char *kCampaignId = ph::kCampaignId;
static constexpr const char *kContractId = ph::kContractId;
static constexpr const char *kVersionKind =
    "mf1750-ec5-partial-hold-version";
static constexpr const char *kManifestKind =
    "mf1750-ec5-partial-hold-manifest";
static constexpr const char *kStatusKind =
    "mf1750-ec5-partial-hold-status";
static constexpr const char *kReportKind =
    "mf1750-ec5-partial-hold-report";
static constexpr const char *kBaselineRole = "WHITE_BASELINE";
#if MF1750_PARTIAL_HOLD_VARIANT == 5 || MF1750_PARTIAL_HOLD_VARIANT == 7
static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"ptlw_command\":131,\"ptlw_payload_bytes\":9,"
    "\"ptlw_endpoint_contract\":\"xe=x+w-1;ye=y+h-1\","
    "\"cropped_dtm\":true,\"packed_bpp\":4,"
    "\"sequential_hold_observation_required\":true,"
    "\"camera_required\":false}";
#else
static constexpr const char *kHistoryLayoutJson =
    "{\"controller_count\":2,\"controller_width\":512,\"height\":600,"
    "\"ptlw_command\":131,\"ptlw_payload_bytes\":9,"
    "\"ptlw_endpoint_contract\":\"xe=x+w-1;ye=y+h\","
    "\"cropped_dtm\":true,\"packed_bpp\":4,"
    "\"sequential_hold_observation_required\":true,"
    "\"camera_required\":false}";
#endif
static constexpr const char *kCampaignCapabilitiesJson =
    "\"partial_refresh\":true,\"window_refresh\":true,"
    "\"command_0x83\":true,\"command_0x86\":false,"
    "\"mid_refresh_power_cut\":false,"
    "\"spi_frequency_sweep\":false,"
    "\"full_screen_global_refresh\":true";

static constexpr const char *kNvsNamespace = ph::kNvsNamespace;
static constexpr const char *kNvsKey = "cursor_v1";

static constexpr const char *kVersionRoute =
    "/api/ec5/partial-hold/version";
static constexpr const char *kManifestRoute =
    "/api/ec5/partial-hold/manifest";
static constexpr const char *kStatusRoute =
    "/api/ec5/partial-hold/status";
static constexpr const char *kReportRoute =
    "/api/ec5/partial-hold/report";
static constexpr const char *kArmRoute = "/api/ec5/partial-hold/arm";
static constexpr const char *kExecuteRoute =
    "/api/ec5/partial-hold/execute";

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
    "ARM_ONE_FIXED_EXPERIMENTAL_PTLW_ACTION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ARMED_EXPERIMENTAL_PTLW_ACTION_ONCE";

#define PH_ACTION(ORDINAL, DRIVER_ROLE, INDEX, PRIOR)                         \
  {                                                                          \
    ORDINAL, DRIVER_ROLE, ph::kActions[INDEX].role, 1,                       \
        ph::kActions[INDEX].branch, ph::kActions[INDEX].descriptorId,        \
        ph::kActions[INDEX].actionId, PRIOR,                                 \
        ph::kActions[INDEX].frameSha256, ph::kActions[INDEX].cs1DtmSha256,   \
        ph::kActions[INDEX].cs2DtmSha256, ph::kActions[INDEX].frameFnv1a,    \
        ph::kActions[INDEX].cs1DtmFnv1a, ph::kActions[INDEX].cs2DtmFnv1a,    \
        {ph::kActions[INDEX].histogram[0], ph::kActions[INDEX].histogram[1], \
         ph::kActions[INDEX].histogram[2], ph::kActions[INDEX].histogram[3], \
         ph::kActions[INDEX].histogram[4], ph::kActions[INDEX].histogram[5], \
         ph::kActions[INDEX].histogram[6], ph::kActions[INDEX].histogram[7]} \
  }

static constexpr ActionDescriptor kActions[] = {
    PH_ACTION(1, EpdChromaGridRole::White, 0, nullptr),
    PH_ACTION(2, EpdChromaGridRole::Source, 1, ph::kActions[0].actionId),
    PH_ACTION(3, EpdChromaGridRole::Mid, 2, ph::kActions[1].actionId),
    PH_ACTION(4, EpdChromaGridRole::Target, 3, ph::kActions[2].actionId),
    PH_ACTION(5, EpdChromaGridRole::White, 4, ph::kActions[3].actionId),
};

#undef PH_ACTION
