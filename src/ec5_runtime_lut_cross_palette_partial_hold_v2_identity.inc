#pragma once

namespace mf1750_runtime_lut_cross_palette_partial_hold_v2 {

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
static constexpr uint32_t kFullControllerDtmBytes = 153600;
static constexpr uint32_t kCroppedDtmBytes = 9600;
static constexpr uint8_t kPartialWindowCommand = 0x83;
static constexpr uint8_t kPartialWindowPayloadBytes = 9;
static constexpr uint8_t kPartialWindowMode = 0x01;
static constexpr bool kCs2VerticalMirror = false;
static constexpr bool kSeparateCsWindowCommands = true;
static constexpr bool kPtlwYEndOneMore = false;
static constexpr bool kExternalFactoryWhiteAnchorRequired = false;
static constexpr bool kFactoryOtpAnchorActionsReachable = true;
static constexpr bool kRuntimeCode7ActionReachable = false;
static constexpr bool kRuntimeCode7PrestageReachable = true;
static constexpr bool kRepeatPtlwAfterPonBusy = false;
static constexpr bool kActionStageCdi = false;
static constexpr bool kActionStageBtst2 = false;
static constexpr bool kCommand0x86Reachable = false;

static constexpr char kVariantKey[] =
    "L535_CROSS_GLOBAL_HEADER_PARTIAL_HOLD_CLEAN_PTLW_V2";
static constexpr char kBuildTag[] =
    "MF1750_EC5_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V2_2026-08-26";
static constexpr char kTestId[] =
    "EC5-RUNTIME-LUT-CROSS-PALETTE-PARTIAL-HOLD-V2";
static constexpr char kCampaignId[] =
    "EC5_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V2";
static constexpr char kContractId[] =
    "d9059cd99c9442fcf5ad4d74c360aaa6f6f18737cd9d090e4fa21b53ad06948b";
static constexpr char kNvsNamespace[] = "rlxph_v2";
static constexpr char kNvsKey[] = "cursor_cxph2";
static constexpr char kProfileId[] =
    "ACTIVE_CODE5_TO_COMMENTED_CODE6_TO_ACTIVE_CODE3__"
    "CS1_ACTIVE535__CS2_COMMENTED535__CLEAN_PTLW_V2";

// Three disjoint controller-local 160x120 ROIs. Both controllers use the
// same local coordinates. Endpoints are inclusive: xe=x+w-1, ye=y+h-1.
static constexpr Window kWindows[kActionCount] = {
    {48, 64, 160, 120, 5, 5},
    {304, 240, 160, 120, 6, 6},
    {48, 416, 160, 120, 3, 3},
};
static constexpr uint8_t
    kPtlwPayloads[kActionCount][kPartialWindowPayloadBytes] = {
        {0x00, 0x30, 0x00, 0xCF, 0x00, 0x40, 0x00, 0xB7, 0x01},
        {0x01, 0x30, 0x01, 0xCF, 0x00, 0xF0, 0x01, 0x67, 0x01},
        {0x00, 0x30, 0x00, 0xCF, 0x01, 0xA0, 0x02, 0x17, 0x01},
};

static constexpr char kPreloadDtmSha256[] =
    "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd";
static constexpr uint32_t kPreloadDtmFnv1a = 0x285715C5UL;
static constexpr char kTargetDtmSha256[kActionCount][65] = {
    "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3",
    "3102928873c21656da937b86e5821d4cf5c6d8ce664daba4db714447ac805d70",
    "6455e53da64c1ffd5644ab3b85d50d51b72ce699666cb7467d821e29e5732faa",
};
static constexpr uint32_t kTargetDtmFnv1a[kActionCount] = {
    0x77244145UL,
    0xD47193C5UL,
    0x06890D45UL,
};
static constexpr char kCombinedDtmSha256[kActionCount][65] = {
    "a84b59d945284e204a5d1b3d4d7a139a3e429d6cc557ec7645cabfb1cc48146f",
    "0292d1cc5fd192cb91b00fb180305aca8dfa996a5c2de89536f8de3599fb5cef",
    "2a8e8b98eac99a8fc8b22f06b9aa60f0056201dafcbb240a1ccd489b1a896a38",
};
static constexpr uint32_t kCombinedDtmFnv1a[kActionCount] = {
    0xD92EB945UL,
    0x367C0BC5UL,
    0x68938545UL,
};

// The frame identity models the intended visible cumulative state. The actual
// action transport identity is code7 prestage || current target crop.
static constexpr ActionIdentity kActions[kActionCount] = {
    {"PATCH_A_ACTIVE_CODE5",
     "L535_ACTIVE_GLOBAL_CODE7_PRESTAGE_SINGLE_PTLW_CODE5_ROI_A",
     "65706e2e0c9cafafdbc68bae63c34666dae31f8fe576cb172d80382125c9f4c6",
     "6ae993bbb78b2e2a6fc46a3d08ff139cf9df62c9e9b1c2ff31f1c98063851fb9",
     "4a32204eba92434a4c331dd6e373892b8e38da19f3524d48072cc958fbaa1202",
     kCombinedDtmSha256[0], kCombinedDtmSha256[0], 0xDA6EDDC5UL,
     kCombinedDtmFnv1a[0], kCombinedDtmFnv1a[0],
     {0, 0, 0, 0, 0, 38400, 0, 576000}},
    {"PATCH_B_COMMENTED_CODE6_HOLD_A",
     "L535_COMMENTED_GLOBAL_CODE7_PRESTAGE_SINGLE_PTLW_CODE6_ROI_B_HOLD_A",
     "55d682b82b0cd9c99a63543f56fcaab66289c81c3b5461394d375f7bfaaae641",
     "c2f74440be76c1a660551771df21d15b6d5a2d610ac378d3a22acbff00f20014",
     "959bd1c654e9afc64a49b27120bfede923d7b8c6485264495dcf900ba795e672",
     kCombinedDtmSha256[1], kCombinedDtmSha256[1], 0x918A3AC5UL,
     kCombinedDtmFnv1a[1], kCombinedDtmFnv1a[1],
     {0, 0, 0, 0, 0, 38400, 38400, 537600}},
    {"PATCH_C_ACTIVE_CODE3_HOLD_AB",
     "L535_ACTIVE_GLOBAL_CODE7_PRESTAGE_SINGLE_PTLW_CODE3_ROI_C_HOLD_AB",
     "a75380aa3d67794c497f0b798bc04e5ded9b9de690dccddaaeb489a584d6ee63",
     "e34c0e25c0e27e63fcdade01b10b619676fa429967042c70b29cd9d6daa3deff",
     "363568d495566faa8a6f0f05a137d6e2c4aa006b160d2e5c853770bc7e57df60",
     kCombinedDtmSha256[2], kCombinedDtmSha256[2], 0x500412C5UL,
     kCombinedDtmFnv1a[2], kCombinedDtmFnv1a[2],
     {0, 0, 0, 38400, 0, 38400, 38400, 499200}},
};

static_assert(kWindows[0].x + kWindows[0].width - 1 == 0x00CF &&
                  kWindows[0].y + kWindows[0].height - 1 == 0x00B7 &&
                  kWindows[1].x + kWindows[1].width - 1 == 0x01CF &&
                  kWindows[1].y + kWindows[1].height - 1 == 0x0167 &&
                  kWindows[2].x + kWindows[2].width - 1 == 0x00CF &&
                  kWindows[2].y + kWindows[2].height - 1 == 0x0217,
              "clean-PTLW cross-HOLD inclusive endpoints changed");
static_assert(sizeof(kPtlwPayloads) ==
                  kActionCount * kPartialWindowPayloadBytes &&
                  kPtlwPayloads[0][8] == kPartialWindowMode &&
                  kPtlwPayloads[1][8] == kPartialWindowMode &&
                  kPtlwPayloads[2][8] == kPartialWindowMode,
              "clean-PTLW cross-HOLD payloads changed");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kActionCount,
              "clean-PTLW cross-HOLD requires exactly three runtime actions");
static_assert(!kExternalFactoryWhiteAnchorRequired &&
                  kFactoryOtpAnchorActionsReachable &&
                  kRuntimeCode7PrestageReachable &&
                  !kRuntimeCode7ActionReachable &&
                  !kRepeatPtlwAfterPonBusy && !kActionStageCdi &&
                  !kActionStageBtst2 && !kCommand0x86Reachable,
              "clean-PTLW cross-HOLD action-stage contract changed");

}  // namespace mf1750_runtime_lut_cross_palette_partial_hold_v2
