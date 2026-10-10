#pragma once

namespace mf1750_runtime_lut_partial_hold {

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
static constexpr uint8_t kWhiteCode = 3;
static constexpr uint8_t kPartialWindowCommand = 0x83;
static constexpr uint8_t kPartialWindowPayloadBytes = 9;
static constexpr uint8_t kPartialWindowMode = 0x01;
static constexpr bool kCs2VerticalMirror = false;
static constexpr bool kSeparateCsWindowCommands = true;
static constexpr bool kPtlwYEndOneMore = false;
static constexpr char kVariantKey[] =
    "L535_ACTIVE_GLOBAL_DISJOINT_Y_INCLUSIVE";
static constexpr char kBuildTag[] =
    "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_L535_ACTIVE_V1_2026-08-22";
static constexpr char kTestId[] =
    "EC5-RUNTIME-LUT-PARTIAL-HOLD-L535-ACTIVE-V1";
static constexpr char kCampaignId[] =
    "EC5_RUNTIME_LUT_PARTIAL_HOLD_L535_ACTIVE_V1";
static constexpr char kContractId[] =
    "1b5a97c73beba17620bb76e3ba9de4392db530e223a7a1ca05da8fe525a3eda3";
static constexpr char kNvsNamespace[] = "rlph_l535a_v1";
static constexpr char kProfileId[] =
    "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";

static constexpr Window kWindows[3] = {
    {48, 64, 160, 120, 0, 0},
    {304, 240, 160, 120, 5, 5},
    {48, 416, 160, 120, 6, 6},
};

static constexpr ActionIdentity kActions[kActionCount] = {
    {"RUNTIME_LUT_WHITE_BASELINE",
     "L535_ACTIVE_GLOBAL_FULL_WHITE_CODE3",
     "8da07d661121f5044d57c64c4f6b861542a4b489e2405ba57f49201c48b0fddd",
     "02aae69330816563b1745e8f05f0ae3766e11c78b0f51507fcaae13a015796ec",
     "6c6af73a0c6dd4bfacb7ec9c8155f0381bea6826f7d6cf09ed88b03b1b238ad1",
     "a7437e6e5ad74aef2af347a540de9252f815c0dd28f2749b0e7a8d659080b318",
     "a7437e6e5ad74aef2af347a540de9252f815c0dd28f2749b0e7a8d659080b318",
     0xE2DA8DC5UL, 0x837B95C5UL, 0x837B95C5UL,
     {0, 0, 0, 614400, 0, 0, 0, 0}},
    {"PATCH_A",
     "L535_ACTIVE_GLOBAL_PTLW_CODE0_A",
     "c7f6969a17bf48f0ff61f1f92d1a28ca39c9e4ce01a50325737a3e1532d8c68c",
     "963d30efeae61726657137923b99ebd72ca4bec8c9277737b6745aab1031b9b3",
     "47cb015278afbfa5508f57b53fbb392c636c44f954f0b5027c8f57222b9eed17",
     "e9a15a094703faaea3fdf53af7e04da21717008ab4bb228799712b2fced03c65",
     "e9a15a094703faaea3fdf53af7e04da21717008ab4bb228799712b2fced03c65",
     0x22812AC5UL, 0x0E5DBBC5UL, 0x0E5DBBC5UL,
     {38400, 0, 0, 576000, 0, 0, 0, 0}},
    {"PATCH_B",
     "L535_ACTIVE_GLOBAL_PTLW_CODE5_B_HOLD_A",
     "9391d9d98e83afd9d18814e19a07d92b8653af570fbe0c4a4cc648a41474d1c5",
     "2277548bc8c296390e8f95bb662dca962bf2a805bcaac061c7815cc895714120",
     "f85e80adf7a20e2bcb90c8cd4f2c7b4fac76f359275fcb69b9c78c0327e337a3",
     "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3",
     "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3",
     0x1574A2C5UL, 0x77244145UL, 0x77244145UL,
     {38400, 0, 0, 537600, 0, 38400, 0, 0}},
    {"PATCH_C",
     "L535_ACTIVE_GLOBAL_PTLW_CODE6_C_HOLD_AB",
     "6e4b1c7402e6f22a20a3a36f50f6bc05731437d0d3e676268f1266d82417991a",
     "6346726248545c1cd0a859aa67e84483aa198e4efbd412c8f23facef44a7da18",
     "1498f675dc7f0444ca397c24c5ab456ebf582e1806680722532e193012e9bba3",
     "3102928873c21656da937b86e5821d4cf5c6d8ce664daba4db714447ac805d70",
     "3102928873c21656da937b86e5821d4cf5c6d8ce664daba4db714447ac805d70",
     0xC9C1EFC5UL, 0xD47193C5UL, 0xD47193C5UL,
     {38400, 0, 0, 499200, 0, 38400, 38400, 0}},
    {"RUNTIME_LUT_WHITE_RECOVERY",
     "L535_ACTIVE_GLOBAL_FULL_WHITE_CODE3_RECOVERY",
     "46943533f9b14e92141fddbed3bd9d7c6ace69feb4bd21771f54f9854a64ac9a",
     "437909a80d5236e3148a16afe0a4367d9d06b8f815b221219f7eec8508713710",
     "6c6af73a0c6dd4bfacb7ec9c8155f0381bea6826f7d6cf09ed88b03b1b238ad1",
     "a7437e6e5ad74aef2af347a540de9252f815c0dd28f2749b0e7a8d659080b318",
     "a7437e6e5ad74aef2af347a540de9252f815c0dd28f2749b0e7a8d659080b318",
     0xE2DA8DC5UL, 0x837B95C5UL, 0x837B95C5UL,
     {0, 0, 0, 614400, 0, 0, 0, 0}},
};

static_assert(sizeof(kWindows) / sizeof(kWindows[0]) == 3,
              "runtime-LUT partial HOLD requires three windows");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kActionCount,
              "runtime-LUT partial HOLD requires five actions");

}  // namespace mf1750_runtime_lut_partial_hold
