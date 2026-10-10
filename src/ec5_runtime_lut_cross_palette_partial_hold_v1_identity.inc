#pragma once

namespace mf1750_runtime_lut_cross_palette_partial_hold_v1 {

struct Window {
  uint16_t x;
  uint16_t y;
  uint16_t width;
  uint16_t height;
  uint8_t cs1Code;
  uint8_t cs2Code;
};

struct ActionIdentity {
  const char *role;
  const char *branch;
  const char *descriptorId;
  const char *actionId;
  const char *frameSha256;
  const char *cs1DtmSha256;
  const char *cs2DtmSha256;
  uint32_t frameFnv1a;
  uint32_t cs1DtmFnv1a;
  uint32_t cs2DtmFnv1a;
  uint32_t histogram[8];
};

static constexpr uint8_t kRoleCount = 3;
static constexpr uint8_t kActionCount = 3;
static constexpr uint8_t kWhiteCode = 7;
static constexpr uint8_t kPartialWindowCommand = 0x83;
static constexpr uint8_t kPartialWindowPayloadBytes = 9;
static constexpr uint8_t kPartialWindowMode = 0x01;
static constexpr bool kCs2VerticalMirror = false;
static constexpr bool kSeparateCsWindowCommands = true;
static constexpr bool kPtlwYEndOneMore = false;
static constexpr bool kExternalFactoryWhiteAnchorRequired = false;
static constexpr bool kFactoryOtpAnchorActionsReachable = true;
static constexpr bool kRepeatPtlwAfterPonBusy = true;
static constexpr bool kRuntimeCode7ActionReachable = false;
static constexpr char kVariantKey[] =
    "L535_CROSS_GLOBAL_HEADER_PARTIAL_HOLD_BUSY_QUALIFIED_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_2026-08-24";
static constexpr char kTestId[] =
    "EC5-RUNTIME-LUT-CROSS-PALETTE-PARTIAL-HOLD-V1";
static constexpr char kCampaignId[] =
    "EC5_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1";
static constexpr char kContractId[] =
    "81ee6e25c412e59d096f40554aaeb252e8e83f21b0060708afee11de5404a3d5";
static constexpr char kNvsNamespace[] = "rlxph_v1";
static constexpr char kProfileId[] =
    "ACTIVE_CODE5_TO_COMMENTED_CODE6_TO_ACTIVE_CODE3__CS1_ACTIVE535__CS2_COMMENTED535";

// Each ROI is local to both 512x600 controllers.  The endpoint contract is
// inclusive: xe=x+width-1 and ye=y+height-1.
static constexpr Window kWindows[kActionCount] = {
    {48, 64, 160, 120, 5, 5},
    {304, 240, 160, 120, 6, 6},
    {48, 416, 160, 120, 3, 3},
};

static constexpr ActionIdentity kActions[kActionCount] = {
    {"PATCH_A_ACTIVE_CODE5",
     "L535_ACTIVE_GLOBAL_REPEAT_PTLW_CODE5_ROI_A",
     "4deba4a6222aa6beff8947e99770ab3793b5ca78ff5b3d5cd63ee223c3c41173",
     "800fbd472e271db8ffe553ed4642a94b01b4c5e085ac8e2b5c7cd39d45ccf6fe",
     "4a32204eba92434a4c331dd6e373892b8e38da19f3524d48072cc958fbaa1202",
     "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3",
     "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3",
     0xDA6EDDC5UL, 0x77244145UL, 0x77244145UL,
     {0, 0, 0, 0, 0, 38400, 0, 576000}},
    {"PATCH_B_COMMENTED_CODE6_HOLD_A",
     "L535_COMMENTED_GLOBAL_REPEAT_PTLW_CODE6_ROI_B_HOLD_A",
     "4573fcc784e1f2de3062d6e766349c0a17330a67799c2350c49253859df58142",
     "0b41b2887d339ac248cc302c2c17efba4f84689127d5542865bc6e6bc7081af4",
     "959bd1c654e9afc64a49b27120bfede923d7b8c6485264495dcf900ba795e672",
     "3102928873c21656da937b86e5821d4cf5c6d8ce664daba4db714447ac805d70",
     "3102928873c21656da937b86e5821d4cf5c6d8ce664daba4db714447ac805d70",
     0x918A3AC5UL, 0xD47193C5UL, 0xD47193C5UL,
     {0, 0, 0, 0, 0, 38400, 38400, 537600}},
    {"PATCH_C_ACTIVE_CODE3_HOLD_AB",
     "L535_ACTIVE_GLOBAL_REPEAT_PTLW_CODE3_ROI_C_HOLD_AB",
     "aa5e5a108db3612b4e4747c98011b7fe0e867156bb3713c3f2a2c160f3a8d9fb",
     "1375b90952de650f4b128aa8ff3e9d027e3662c8657f96ec3cb93b23c36523e0",
     "363568d495566faa8a6f0f05a137d6e2c4aa006b160d2e5c853770bc7e57df60",
     "6455e53da64c1ffd5644ab3b85d50d51b72ce699666cb7467d821e29e5732faa",
     "6455e53da64c1ffd5644ab3b85d50d51b72ce699666cb7467d821e29e5732faa",
     0x500412C5UL, 0x06890D45UL, 0x06890D45UL,
     {0, 0, 0, 38400, 0, 38400, 38400, 499200}},
};

static_assert(sizeof(kWindows) / sizeof(kWindows[0]) == kActionCount,
              "cross-profile partial HOLD requires exactly three windows");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kActionCount,
              "cross-profile partial HOLD requires exactly three identities");
static_assert(!kExternalFactoryWhiteAnchorRequired &&
                  kFactoryOtpAnchorActionsReachable &&
                  kRepeatPtlwAfterPonBusy && !kRuntimeCode7ActionReachable,
              "cross-profile partial HOLD anchor contract changed");

}  // namespace mf1750_runtime_lut_cross_palette_partial_hold_v1

