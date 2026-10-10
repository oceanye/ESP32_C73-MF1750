#pragma once

namespace mf1750_runtime_lut_partial_hold_v3 {

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

static constexpr uint8_t kRoleCount = 4;
static constexpr uint8_t kActionCount = 5;
static constexpr uint8_t kWhiteCode = 7;
static constexpr uint8_t kPartialWindowCommand = 0x83;
static constexpr uint8_t kPartialWindowPayloadBytes = 9;
static constexpr uint8_t kPartialWindowMode = 0x01;
static constexpr bool kCs2VerticalMirror = false;
static constexpr bool kSeparateCsWindowCommands = true;
static constexpr bool kPtlwYEndOneMore = false;
static constexpr char kVariantKey[] =
    "L535_ACTIVE_GLOBAL_DISJOINT_Y_INCLUSIVE_CODE7_COMMON_WHITE";
static constexpr char kBuildTag[] =
    "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_L535_ACTIVE_V3_2026-08-23";
static constexpr char kTestId[] =
    "EC5-RUNTIME-LUT-PARTIAL-HOLD-L535-ACTIVE-V3";
static constexpr char kCampaignId[] =
    "EC5_RUNTIME_LUT_PARTIAL_HOLD_L535_ACTIVE_V3";
static constexpr char kContractId[] =
    "4d0d17e3e02e6af2d0759b8d81b7acc6eb172072526ef5aba7c91b2a4e566402";
static constexpr char kNvsNamespace[] = "rlph_l535a_v3";
static constexpr char kProfileId[] =
    "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";

static constexpr Window kWindows[3] = {
    {48, 64, 160, 120, 3, 3},
    {304, 240, 160, 120, 5, 5},
    {48, 416, 160, 120, 6, 6},
};

static constexpr ActionIdentity kActions[kActionCount] = {
    {"RUNTIME_LUT_WHITE_BASELINE",
     "L535_ACTIVE_GLOBAL_FULL_WHITE_CODE7",
     "1574488d764bf79d01ba597b87a3584985b77e202d71d5813d1661e234ea4f1c",
     "92f8f0dae944bd554f64afb880ec588a8066cc3ce9d330384790e07e5f91abca",
     "f27255891c2b00350b2f7aca6f0719116c6a29262008b7621ef4b7df66b099f2",
     "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     0x7C918DC5UL, 0x285715C5UL, 0x285715C5UL,
     {0, 0, 0, 0, 0, 0, 0, 614400}},
    {"PATCH_A",
     "L535_ACTIVE_GLOBAL_PTLW_CODE3_BLACK_A",
     "01ca1876a9422ba39dc8567dc586eab1c9e0ec398944cb2edd43e7900f4b7569",
     "c2e367fde9fca5d0c4a2f836d9b58c3b38c70d690a23c3d7bb7112079e7c9b82",
     "89696fbebcc192494863d1e83f95b3a76a810def6a1a3efc8526f989c04f47a7",
     "6455e53da64c1ffd5644ab3b85d50d51b72ce699666cb7467d821e29e5732faa",
     "6455e53da64c1ffd5644ab3b85d50d51b72ce699666cb7467d821e29e5732faa",
     0xC30B65C5UL, 0x06890D45UL, 0x06890D45UL,
     {0, 0, 0, 38400, 0, 0, 0, 576000}},
    {"PATCH_B",
     "L535_ACTIVE_GLOBAL_PTLW_CODE5_BLUE_B_HOLD_A",
     "bd1aa7031b593c914bb571cd99b47b5fd7b04c9c07fd6dfe1c3fb5607b873f01",
     "db5bd5bc34e2eccfa18d2019d6111e0531c902810367f395cde78ee8ff1e7388",
     "a604bb9d01b47d520c1c6cac9311f5f4761cd7e30361e3f13c79602c545e6f3a",
     "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3",
     "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3",
     0x0D48B5C5UL, 0x77244145UL, 0x77244145UL,
     {0, 0, 0, 38400, 0, 38400, 0, 537600}},
    {"PATCH_C",
     "L535_ACTIVE_GLOBAL_PTLW_CODE6_GREEN_C_HOLD_AB",
     "2da5ec395a1ba2cc794dad3af573030d2c52baec649ab1652e88e4e0c61fc06a",
     "b24139d197047b8985d1555327382ae274566b73f03003294a7167a80c5ef5d5",
     "92c0c0a116e2bf1f78a652bbfb56f3705d254df104dd4b9d36a56907f1d1b4b7",
     "3102928873c21656da937b86e5821d4cf5c6d8ce664daba4db714447ac805d70",
     "3102928873c21656da937b86e5821d4cf5c6d8ce664daba4db714447ac805d70",
     0x302E12C5UL, 0xD47193C5UL, 0xD47193C5UL,
     {0, 0, 0, 38400, 0, 38400, 38400, 499200}},
    {"RUNTIME_LUT_WHITE_RECOVERY",
     "L535_ACTIVE_GLOBAL_FULL_WHITE_CODE7_RECOVERY",
     "0b604fc29229c7dbe0fdc6ca376eaf36ece2c695b03ee11e8c260b2e8d468445",
     "404dfc15c2e2da4511e4657504be66d309fd1408554e918c27ab50b76f03b928",
     "f27255891c2b00350b2f7aca6f0719116c6a29262008b7621ef4b7df66b099f2",
     "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     0x7C918DC5UL, 0x285715C5UL, 0x285715C5UL,
     {0, 0, 0, 0, 0, 0, 0, 614400}},
};

static_assert(sizeof(kWindows) / sizeof(kWindows[0]) == 3,
              "runtime-LUT partial HOLD V3 requires three windows");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kActionCount,
              "runtime-LUT partial HOLD V3 requires five actions");

}  // namespace mf1750_runtime_lut_partial_hold_v3
