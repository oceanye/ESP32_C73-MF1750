#pragma once

namespace mf1750_lightness_hold_function_chain_v1 {

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

static constexpr uint8_t kRoleCount = 6;
static constexpr uint8_t kRoleIdentityCount = 6;
static constexpr uint8_t kHoldActionCount = 2;
static constexpr uint8_t kSeparatorCode = 7;
static constexpr uint8_t kSourceCode = 7;
static constexpr uint8_t kTargetCode = 0;
static constexpr uint8_t kPreloadCode = 7;
static constexpr uint32_t kFullControllerDtmBytes = 153600;
static constexpr uint32_t kCroppedDtmBytes = 4608;
static constexpr uint8_t kPartialWindowCommand = 0x83;
static constexpr uint8_t kPartialWindowPayloadBytes = 9;
static constexpr uint8_t kPartialWindowMode = 0x01;
static constexpr bool kCs2VerticalMirror = false;
static constexpr bool kSeparateCsWindowCommands = true;
static constexpr bool kPtlwYEndOneMore = false;
static constexpr bool kRuntimeCode7PrestageReachable = true;
static constexpr bool kRepeatPtlwAfterPonBusy = false;
static constexpr bool kActionStageCdi = false;
static constexpr bool kActionStageBtst2 = false;
static constexpr bool kCommand0x86Reachable = false;
static constexpr bool kSourceAuthoritySealed = true;

static constexpr uint8_t kGridRows = 8;
static constexpr uint8_t kGridColumns = 8;
static constexpr uint16_t kGridX0 = 20;
static constexpr uint16_t kGridY0 = 40;
static constexpr uint16_t kCellWidth = 52;
static constexpr uint16_t kCellHeight = 58;
static constexpr uint16_t kGapX = 8;
static constexpr uint16_t kGapY = 8;
static constexpr uint16_t kGridX1Exclusive = 492;
static constexpr uint16_t kGridY1Exclusive = 560;

static constexpr char kVariantKey[] = "LIGHTNESS_HOLD_FUNCTION_CHAIN_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_2026-09-01";
static constexpr char kTestId[] =
    "EC5-LIGHTNESS-HOLD-FUNCTION-CHAIN-V1";
static constexpr char kCampaignId[] =
    "EC5_LIGHTNESS_HOLD_FUNCTION_CHAIN_V1";
static constexpr char kContractId[] =
    "ad14f5394a5c6e284885aa504ea0d99fec0ccb1dcf8053759dba025b8606f3e3";
static constexpr char kNvsNamespace[] = "lhfc_v1";
static constexpr char kNvsKey[] = "cur_lhfc1";
static constexpr char kNvsBootKey[] = "boot_lh1";
static constexpr char kActiveProfileId[] =
    "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";
static constexpr char kCommentedProfileId[] =
    "LEGACY_COMMENTED_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";

// Candidate cells occupy local x=[20,492), y=[40,560).  These windows are
// therefore entirely outside the grid in the top/bottom white side bands.
static constexpr Window kHoldWindows[kHoldActionCount] = {
    {64, 8, 384, 24, 5, 5},
    {64, 568, 384, 24, 6, 6},
};
static constexpr uint8_t
    kPtlwPayloads[kHoldActionCount][kPartialWindowPayloadBytes] = {
        {0x00, 0x40, 0x01, 0xBF, 0x00, 0x08, 0x00, 0x1F, 0x01},
        {0x00, 0x40, 0x01, 0xBF, 0x02, 0x38, 0x02, 0x4F, 0x01},
};

static constexpr char kPreloadDtmSha256[] =
    "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd";
static constexpr uint32_t kPreloadDtmFnv1a = 0x285715C5UL;
static constexpr char kTargetDtmSha256[kHoldActionCount][65] = {
    "83b73bd0618e126d73acde723d16cda37607e230478f61a919993abdfb996596",
    "8dfd8ce92af324752892f6bc50cb9d093fe4c894744adf960310a5b12441f4a0",
};
static constexpr uint32_t kTargetDtmFnv1a[kHoldActionCount] = {
    0x4E1CD7C5UL,
    0x820D65C5UL,
};
static constexpr char kCombinedDtmSha256[kHoldActionCount][65] = {
    "443f06b6e0d1c6606da3504ce219c9f9fbf736f59b0810a6efb3c1af0d81b06a",
    "855d32c50409c7017dd3c1d4ea88df52f5cde1ed019f92ce5e156e3fc9106417",
};
static constexpr uint32_t kCombinedDtmFnv1a[kHoldActionCount] = {
    0xBD174FC5UL,
    0xF107DDC5UL,
};

// Indexed by the public role enum: White, Source, Mid, Target,
// ReverseSource(H1), ReverseTarget(H2).  White is fixture-only and unreachable
// from the five-action main campaign.
static constexpr ActionIdentity kActions[kRoleIdentityCount] = {
    {"UNREACHABLE_WHITE_FIXTURE",
     "LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_UNREACHABLE_WHITE_FIXTURE",
     "0000000000000000000000000000000000000000000000000000000000000000",
     "0000000000000000000000000000000000000000000000000000000000000000",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {"L1_FIXED_ACTIVE_SOURCE_CODE7",
     "LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_L1_FIXED_ACTIVE_SOURCE_CODE7",
     "db65ab65f9f32e1070af5c21c3d6f45d94dcd1bf7b7055732ded454c5e0bea47",
     "d21f725a283b7f6cb33f8ee8b8e0351e8d1698addf90b7431ce205eff83caf60",
     "f27255891c2b00350b2f7aca6f0719116c6a29262008b7621ef4b7df66b099f2",
     "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     0x7C918DC5UL, 0x285715C5UL, 0x285715C5UL,
     {0, 0, 0, 0, 0, 0, 0, 614400}},
    {"L2_COMMENTED_MIDDLE_LATIN_C0_C7",
     "LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_L2_COMMENTED_MIDDLE_LATIN_C0_C7",
     "3bbeb6a06d2ec9bbb50b28c798414d2db1d624710ce394376326b578fe46b4d3",
     "221cd4c242a37fde29dfb7b98066973523be041dddff015f4094e87d8be887fa",
     "03265f52002f241e4681631d5efd2686045a533c3a8ab8977bcd2bbd01961416",
     "890ea1f455e80bfe262ae53f6741409d1737603ff5a642f1d58f241ab258e1f3",
     "b28a0b79555000bed6c9a991e0ca3e8317661e38adaf7cb1293b9f3b5510c253",
     0x41A370C5UL, 0x02229BC5UL, 0xA4741A45UL,
     {48256, 48256, 48256, 48256, 48256, 48256, 48256, 276608}},
    {"L3_FIXED_ACTIVE_TARGET_CODE0",
     "LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_L3_FIXED_ACTIVE_TARGET_CODE0",
     "7fc5609667d673d59051fe08e6fec08fe92e91d87e6920f3897a35229913276f",
     "af6aa5c8a62d212da2a53d440c1798aa82dbc0dae45a47767bb791a2ef49d32f",
     "9c771f6a89f72bdd64c38ddd99489accad9c5ed554d1841740517ea1100f7af4",
     "f36eeda01f7cdd5cda9147cece0a543009a217235c38b1ab3f636f24b2e4f4aa",
     "f36eeda01f7cdd5cda9147cece0a543009a217235c38b1ab3f636f24b2e4f4aa",
     0x2CC36BC5UL, 0x4FA004C5UL, 0x4FA004C5UL,
     {386048, 0, 0, 0, 0, 0, 0, 228352}},
    {"H1_ACTIVE_CODE5_TOP_PROBE_HOLD_GRID",
     "LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_H1_ACTIVE_CODE5_TOP_PROBE_HOLD_GRID",
     "af5bbbc6cfacb06b0f6ed3acb98e327723d4b60f8f69bac0002a2c2f4389a182",
     "69f639ae9523cb0d656c56adea605b32ee1adf5634014b4f0b90d89e4d579156",
     "a12c79fd3cf92fc99c8cd60dfa8eb89e58dad3383f179a5fb11e5ba853d84f92",
     "443f06b6e0d1c6606da3504ce219c9f9fbf736f59b0810a6efb3c1af0d81b06a",
     "443f06b6e0d1c6606da3504ce219c9f9fbf736f59b0810a6efb3c1af0d81b06a",
     0x7E367BC5UL, 0xBD174FC5UL, 0xBD174FC5UL,
     {386048, 0, 0, 0, 0, 18432, 0, 209920}},
    {"H2_COMMENTED_CODE6_BOTTOM_PROBE_HOLD_GRID_AND_H1",
     "LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_H2_COMMENTED_CODE6_BOTTOM_PROBE_HOLD_GRID_AND_H1",
     "4a55af059f6abad6f55bd7647068cd55e5962dac60cc9f9ef8246b4fdeff6407",
     "3e9b5a096ee556caf8cb7c87df7a2c7fb94f9e53621d03c93fd013cc6fa41e7a",
     "4c27ca27ed668b4f4d77c8a6ee0ff385c847233cdaae6620844813e97fdd938b",
     "855d32c50409c7017dd3c1d4ea88df52f5cde1ed019f92ce5e156e3fc9106417",
     "855d32c50409c7017dd3c1d4ea88df52f5cde1ed019f92ce5e156e3fc9106417",
     0x9E1C37C5UL, 0xF107DDC5UL, 0xF107DDC5UL,
     {386048, 0, 0, 0, 0, 18432, 18432, 191488}},
};

static_assert(kGridX1Exclusive == 492 && kGridY1Exclusive == 560 &&
                  kHoldWindows[0].y + kHoldWindows[0].height <= kGridY0 &&
                  kHoldWindows[1].y >= kGridY1Exclusive,
              "HOLD probes must not overlap the 8x8 candidate grid");
static_assert(kHoldWindows[0].x + kHoldWindows[0].width - 1 == 0x01BF &&
                  kHoldWindows[0].y + kHoldWindows[0].height - 1 == 0x001F &&
                  kHoldWindows[1].x + kHoldWindows[1].width - 1 == 0x01BF &&
                  kHoldWindows[1].y + kHoldWindows[1].height - 1 == 0x024F,
              "inclusive PTLW endpoints changed");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kRoleIdentityCount &&
                  kSourceAuthoritySealed &&
                  !kRepeatPtlwAfterPonBusy && !kActionStageCdi &&
                  !kActionStageBtst2 && !kCommand0x86Reachable,
              "lightness-HOLD fail-closed/transport contract changed");

}  // namespace mf1750_lightness_hold_function_chain_v1
