#include "ec5_partial_hold_warm_session_v1_identity.inc"

namespace warmcfg = mf1750_partial_hold_warm_session_v1;

static constexpr const char *kClassification =
    "EXPERIMENTAL_SPD1657_L535_STRICT_PTLW_WARM_SESSION";
static constexpr const char *kBuildTag = warmcfg::kBuildTag;
static constexpr const char *kTestId = warmcfg::kTestId;
static constexpr const char *kCampaignId = warmcfg::kCampaignId;
static constexpr const char *kContractId = warmcfg::kContractId;
static constexpr const char *kNvsNamespace = warmcfg::kNvsNamespace;
static constexpr const char *kNvsKey = "cursor_v1";
static constexpr const char *kArmIntent =
    "ARM_ONE_FIXED_WARM_SESSION_PTLW_ACTION";
static constexpr const char *kExecuteIntent =
    "EXECUTE_ARMED_WARM_SESSION_PTLW_ACTION_ONCE";

#define WARM_ACTION(ORDINAL, DRIVER_ROLE, INDEX, PRIOR)                       \
  {                                                                          \
    ORDINAL, DRIVER_ROLE, warmcfg::kActions[INDEX].role,                     \
        warmcfg::kActions[INDEX].branch,                                     \
        warmcfg::kActions[INDEX].descriptorId,                               \
        warmcfg::kActions[INDEX].actionId, PRIOR,                            \
        warmcfg::kActions[INDEX].frameSha256,                                \
        warmcfg::kActions[INDEX].cs1DtmSha256,                               \
        warmcfg::kActions[INDEX].cs2DtmSha256                                \
  }

static constexpr ActionDescriptor kActions[] = {
    WARM_ACTION(1, EpdPartialHoldWarmRole::WhiteBaseline, 0, nullptr),
    WARM_ACTION(2, EpdPartialHoldWarmRole::RedA, 1,
                warmcfg::kActions[0].actionId),
    WARM_ACTION(3, EpdPartialHoldWarmRole::BlueB, 2,
                warmcfg::kActions[1].actionId),
    WARM_ACTION(4, EpdPartialHoldWarmRole::GreenC, 3,
                warmcfg::kActions[2].actionId),
    WARM_ACTION(5, EpdPartialHoldWarmRole::WhiteRecovery, 4,
                warmcfg::kActions[3].actionId),
};

#undef WARM_ACTION
