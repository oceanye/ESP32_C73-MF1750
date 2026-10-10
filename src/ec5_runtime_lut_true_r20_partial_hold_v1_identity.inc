#pragma once

namespace mf1750_runtime_lut_true_r20_partial_hold_v1 {

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
  const char *tupleName;
  const char *cs1TupleSha256;
  const char *cs2TupleSha256;
};

static constexpr uint8_t kRoleCount = 3;
static constexpr uint8_t kRuntimeActionCount = 3;
static constexpr uint8_t kCampaignActionCount = 4;
static constexpr uint8_t kWhiteCode = 7;
static constexpr uint32_t kFullControllerDtmBytes = 153600;
static constexpr uint32_t kCroppedDtmBytes = 9600;
static constexpr uint8_t kPartialWindowCommand = 0x83;
static constexpr uint8_t kPartialWindowPayloadBytes = 9;
static constexpr uint8_t kPartialWindowMode = 0x01;
static constexpr bool kCs2VerticalMirror = false;
static constexpr bool kSeparateCsWindowCommands = true;
static constexpr bool kPtlwYEndOneMore = false;
static constexpr bool kExternalFactoryWhiteAnchorRequired = true;
static constexpr bool kFactoryOtpRecoveryActionReachable = true;
static constexpr bool kRuntimeCode7ActionReachable = false;
static constexpr bool kRuntimeCode7PrestageReachable = true;
static constexpr bool kRepeatPtlwAfterPonBusy = false;
static constexpr bool kActionStageCdi = false;
static constexpr bool kActionStageBtst2 = false;
static constexpr bool kCommand0x86Reachable = false;
static constexpr bool kHistoricalGlobalHeaderOnlyCrossLut = false;
static constexpr bool kCompleteTupleSwitchedPerAction = true;
static constexpr bool kSameTupleBothControllersPerAction = true;
static constexpr bool kCandidateCodesRequireBatch1Evidence = true;

static constexpr char kVariantKey[] =
    "L535_TRUE_R20_TUPLE_SWITCH_PARTIAL_HOLD_CLEAN_PTLW_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_RUNTIME_LUT_TRUE_R20_PARTIAL_HOLD_V1_2026-08-28";
static constexpr char kTestId[] =
    "EC5-RUNTIME-LUT-TRUE-R20-PARTIAL-HOLD-V1";
static constexpr char kCampaignId[] =
    "EC5_RUNTIME_LUT_TRUE_R20_PARTIAL_HOLD_V1";
static constexpr char kContractId[] =
    "38698de14b6a2a7a96e072d4de025cb0708ae167b81c348f6c4337dc3654eb63";
static constexpr char kNvsNamespace[] = "tr20ph_v1";
static constexpr char kNvsKey[] = "cursor_tr20ph1";
static constexpr char kProfileId[] =
    "ACTIVE_BOTH_CS_CODE0_TO_COMMENTED_BOTH_CS_CODE0_TO_"
    "ACTIVE_BOTH_CS_CODE2_CLEAN_PTLW_V1";
static constexpr char kBatch1EvidenceRequirementsId[] =
    "51ded712517377821322a83eb1264afd7a69c08678c9a69a2c3b7f6d697ae547";

static constexpr char kActiveTupleSha256[] =
    "5d8da091246acc0a19414fff463e1f1160053bd652adb386638c30b7ed442586";
static constexpr char kCommentedTupleSha256[] =
    "626b2770b8b807992e5e1bd7751e0142f1a19e5069b864a83680b86b4466b4fd";
static constexpr char kActivePowerSha256[] =
    "f8f668ee0ab3b9c33f41c05bd62b6e2b857c5e069af6be33b054e24bd24390f2";
static constexpr char kCommentedPowerSha256[] =
    "e571c5cf13938b4f4e12b7152ef5ac7d4970ca1d7fd5aa5568b3bf5ab5b208c9";
static constexpr char kActivePllSha256[] =
    "dbc1b4c900ffe48d575b5da5c638040125f65db0fe3e24494b76ea986457d986";
static constexpr char kCommentedPllSha256[] =
    "084fed08b978af4d7d196a7446a86b58009e636b611db16211b65a9aadff29c5";
static constexpr char kActiveR20PrefixSha256[] =
    "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b";
static constexpr char kCommentedR20PrefixSha256[] =
    "2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26";
static constexpr char kR21Sha256[] =
    "24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f";
static constexpr uint16_t kR20PrefixBytes = 535;
static constexpr uint16_t kR21Bytes = 704;

static constexpr Window kWindows[kRuntimeActionCount] = {
    {48, 64, 160, 120, 0, 0},
    {304, 240, 160, 120, 0, 0},
    {48, 416, 160, 120, 2, 2},
};
static constexpr bool kUseCommentedTuple[kRuntimeActionCount] = {
    false, true, false,
};
static constexpr uint8_t
    kPtlwPayloads[kRuntimeActionCount][kPartialWindowPayloadBytes] = {
        {0x00, 0x30, 0x00, 0xCF, 0x00, 0x40, 0x00, 0xB7, 0x01},
        {0x01, 0x30, 0x01, 0xCF, 0x00, 0xF0, 0x01, 0x67, 0x01},
        {0x00, 0x30, 0x00, 0xCF, 0x01, 0xA0, 0x02, 0x17, 0x01},
};

static constexpr char kPreloadDtmSha256[] =
    "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd";
static constexpr uint32_t kPreloadDtmFnv1a = 0x285715C5UL;
static constexpr char kTargetDtmSha256[kRuntimeActionCount][65] = {
    "e9a15a094703faaea3fdf53af7e04da21717008ab4bb228799712b2fced03c65",
    "e9a15a094703faaea3fdf53af7e04da21717008ab4bb228799712b2fced03c65",
    "ae31576c7d64c6049fae05f84e2da5f69ece700f378690452b0075981fe27d6e",
};
static constexpr uint32_t kTargetDtmFnv1a[kRuntimeActionCount] = {
    0x0E5DBBC5UL, 0x0E5DBBC5UL, 0xE4406DC5UL,
};
static constexpr char kCombinedDtmSha256[kRuntimeActionCount][65] = {
    "73871e076e8a8b3af18e19616312a9d502e66330dfbdd506b700b5cf882d6825",
    "73871e076e8a8b3af18e19616312a9d502e66330dfbdd506b700b5cf882d6825",
    "332cbe2a8acbaa06fb5c02c3603f1b82ea3cdc749b199d531458df3f26d0cdf2",
};
static constexpr uint32_t kCombinedDtmFnv1a[kRuntimeActionCount] = {
    0x706833C5UL, 0x706833C5UL, 0x464AE5C5UL,
};

static constexpr ActionIdentity kActions[kRuntimeActionCount] = {
    {"PATCH_A_ACTIVE_TUPLE_CANDIDATE_CODE0",
     "TRUE_ACTIVE_PWR_PLL_R20_R21_BOTH_CS_CODE0_ROI_A",
     "4d317d9f0a96a85c8ba30fb52c3661d47fa7b7de3dcc7ef35fccd7dbd869e8a5",
     "9dde1d9805c5c08880a7cce3be4844faacdafe3e250de1a8dc8b2bbda8a17a48",
     "d577c19d7d83e33e4d13c9a338b706ebc505ed432beb19d93e6e879a6799cddd",
     kCombinedDtmSha256[0], kCombinedDtmSha256[0], 0x5AD03AC5UL,
     kCombinedDtmFnv1a[0], kCombinedDtmFnv1a[0],
     {38400, 0, 0, 0, 0, 0, 0, 576000}, "active",
     kActiveTupleSha256, kActiveTupleSha256},
    {"PATCH_B_COMMENTED_TUPLE_CANDIDATE_CODE0_HOLD_A",
     "TRUE_COMMENTED_PWR_PLL_R20_R21_BOTH_CS_CODE0_ROI_B_HOLD_A",
     "07e0cdff9718da18f7dbfa084ce41b7af7b0b7a0c9591ca57453b962984f055e",
     "cef8f2bb0ddd3ec96c2929a754b22a403fcb38e34ff7278ef2fb4c83ea1ea29f",
     "d1425bc9ddd85d9a74f2741befc450b2e3060fea421575d022ee2de8f1016376",
     kCombinedDtmSha256[1], kCombinedDtmSha256[1], 0xEAA4E7C5UL,
     kCombinedDtmFnv1a[1], kCombinedDtmFnv1a[1],
     {76800, 0, 0, 0, 0, 0, 0, 537600}, "commented",
     kCommentedTupleSha256, kCommentedTupleSha256},
    {"PATCH_C_ACTIVE_TUPLE_CANDIDATE_CODE2_HOLD_AB",
     "TRUE_ACTIVE_PWR_PLL_R20_R21_BOTH_CS_CODE2_ROI_C_HOLD_AB",
     "000f0991160242f035fee116b37342597b79f38d41cd2011e50cab40ce94aa14",
     "ef7996a165effed3fff26dc1595b6a484f3abab06ed73ae4e9faeaeb72a56444",
     "689b38f633a012b61e7b42da73617e2a3a39838bd713bfaea76534e9305a5360",
     kCombinedDtmSha256[2], kCombinedDtmSha256[2], 0x21E858C5UL,
     kCombinedDtmFnv1a[2], kCombinedDtmFnv1a[2],
     {76800, 0, 38400, 0, 0, 0, 0, 499200}, "active",
     kActiveTupleSha256, kActiveTupleSha256},
};

static_assert(kWindows[0].x + kWindows[0].width - 1 == 0x00CF &&
                  kWindows[0].y + kWindows[0].height - 1 == 0x00B7 &&
                  kWindows[1].x + kWindows[1].width - 1 == 0x01CF &&
                  kWindows[1].y + kWindows[1].height - 1 == 0x0167 &&
                  kWindows[2].x + kWindows[2].width - 1 == 0x00CF &&
                  kWindows[2].y + kWindows[2].height - 1 == 0x0217,
              "true-R20 clean PTLW inclusive endpoints changed");
static_assert(kUseCommentedTuple[0] == false &&
                  kUseCommentedTuple[1] == true &&
                  kUseCommentedTuple[2] == false,
              "true-R20 complete tuple sequence changed");
static_assert(kHistoricalGlobalHeaderOnlyCrossLut == false &&
                  kCompleteTupleSwitchedPerAction &&
                  kSameTupleBothControllersPerAction &&
                  kCandidateCodesRequireBatch1Evidence &&
                  kExternalFactoryWhiteAnchorRequired &&
                  kFactoryOtpRecoveryActionReachable &&
                  kRuntimeCode7PrestageReachable &&
                  !kRuntimeCode7ActionReachable &&
                  !kRepeatPtlwAfterPonBusy && !kActionStageCdi &&
                  !kActionStageBtst2 && !kCommand0x86Reachable,
              "true-R20 safety or transport contract changed");

}  // namespace mf1750_runtime_lut_true_r20_partial_hold_v1
