#pragma once

namespace mf1750_partial_hold_warm_session_v1 {

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
static constexpr uint32_t kMaxWarmGapMs = 120000;
static constexpr char kVariantKey[] =
    "L535_ACTIVE_STRICT_PTLW_WARM_SESSION_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_PARTIAL_HOLD_WARM_SESSION_V1_2026-08-23";
static constexpr char kTestId[] = "EC5-PARTIAL-HOLD-WARM-SESSION-V1";
static constexpr char kCampaignId[] = "EC5_PARTIAL_HOLD_WARM_SESSION_V1";
static constexpr char kContractId[] =
    "a3d1efdf10bff5abaed06b9ddc0b3c7044487a25eca89ceadbb24d2d069fa905";
static constexpr char kNvsNamespace[] = "phwarm_v1";
static constexpr char kProfileId[] =
    "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";

static constexpr Window kWindows[3] = {
    {48, 64, 160, 120, 3, 3},
    {304, 240, 160, 120, 5, 5},
    {48, 416, 160, 120, 6, 6},
};

static constexpr ActionIdentity kActions[kActionCount] = {
    {"WARM_WHITE_BASELINE",
     "PREPARE_ONCE_L535_PACKED_CODE7_WHITE_PON_DRF_HOLD_POWER",
     "7cb329455ed593501b69943e9039f9a1f8447206ccdf36a8c341d3ff492fd837",
     "398790a19e64941ed5ef89b638e3215cea0cae142b5da837eb5555f355b2e6c4",
     "f27255891c2b00350b2f7aca6f0719116c6a29262008b7621ef4b7df66b099f2",
     "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     0x7C918DC5UL, 0x285715C5UL, 0x285715C5UL,
     {0, 0, 0, 0, 0, 0, 0, 614400}},
    {"WARM_RED_A",
     "NO_RESET_NO_PREPARE_PTLW_CODE3_RED_A_DRF_ONLY_HOLD_POWER",
     "fe1461a80e477f40c69c84dbf03c9c104a999dc9964abce91ff47da0f050f44f",
     "798c830728bf4c992d9290d645c719c60d2010df71dd644199cd49f63c5ec3bf",
     "89696fbebcc192494863d1e83f95b3a76a810def6a1a3efc8526f989c04f47a7",
     "6455e53da64c1ffd5644ab3b85d50d51b72ce699666cb7467d821e29e5732faa",
     "6455e53da64c1ffd5644ab3b85d50d51b72ce699666cb7467d821e29e5732faa",
     0xC30B65C5UL, 0x06890D45UL, 0x06890D45UL,
     {0, 0, 0, 38400, 0, 0, 0, 576000}},
    {"WARM_BLUE_B_HOLD_A",
     "NO_RESET_NO_PREPARE_PTLW_CODE5_BLUE_B_DRF_ONLY_HOLD_POWER",
     "b61a2e7f6b2e70ccc115292803a4ce1ade3e86d3cf82b670fdb05c2dfcae9e1c",
     "4b8700f4c47acfaf69d74e61732f93fb556630a64cdab31daf15290bc857cad3",
     "a604bb9d01b47d520c1c6cac9311f5f4761cd7e30361e3f13c79602c545e6f3a",
     "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3",
     "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3",
     0x0D48B5C5UL, 0x77244145UL, 0x77244145UL,
     {0, 0, 0, 38400, 0, 38400, 0, 537600}},
    {"WARM_GREEN_C_HOLD_AB",
     "NO_RESET_NO_PREPARE_PTLW_CODE6_GREEN_C_DRF_ONLY_HOLD_POWER",
     "9dc73040ca10146cf7541fd39b803bc792e468a4b6aac7e20b5d8baf3e5adf0c",
     "d9defb4a22cb91bea988aabe6f07b1d4d2d4a6c9b3367437d4bd2846a586c240",
     "92c0c0a116e2bf1f78a652bbfb56f3705d254df104dd4b9d36a56907f1d1b4b7",
     "3102928873c21656da937b86e5821d4cf5c6d8ce664daba4db714447ac805d70",
     "3102928873c21656da937b86e5821d4cf5c6d8ce664daba4db714447ac805d70",
     0x302E12C5UL, 0xD47193C5UL, 0xD47193C5UL,
     {0, 0, 0, 38400, 0, 38400, 38400, 499200}},
    {"WARM_WHITE_RECOVERY_SAFE_POF",
     "NO_RESET_NO_PREPARE_FULL_PTLW_PACKED_CODE7_WHITE_DRF_SAFE_POF",
     "c7eb7457db77fbda9434d15c94331ce55d578a445288cb96d882365aae0e6c22",
     "dc2c72d125e60010e70b1567752bc2d09f950d5d2448c5113bd0828a8bd3826a",
     "f27255891c2b00350b2f7aca6f0719116c6a29262008b7621ef4b7df66b099f2",
     "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     0x7C918DC5UL, 0x285715C5UL, 0x285715C5UL,
     {0, 0, 0, 0, 0, 0, 0, 614400}},
};

static_assert(sizeof(kWindows) / sizeof(kWindows[0]) == 3,
              "warm session requires three disjoint patch windows");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kActionCount,
              "warm session requires five one-shot actions");

}  // namespace mf1750_partial_hold_warm_session_v1
