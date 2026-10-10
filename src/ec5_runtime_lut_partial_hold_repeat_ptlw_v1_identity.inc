#pragma once

namespace mf1750_runtime_lut_partial_hold_repeat_ptlw_v1 {

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
static constexpr bool kExternalFactoryWhiteAnchorRequired = true;
static constexpr bool kRepeatPtlwAfterPonBusy = true;
static constexpr bool kRuntimeCode7ActionReachable = false;
static constexpr char kVariantKey[] =
    "L535_ACTIVE_GLOBAL_REPEAT_PTLW_AFTER_PON_EXTERNAL_ANCHOR_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V1_2026-08-23";
static constexpr char kTestId[] =
    "EC5-RUNTIME-LUT-PARTIAL-HOLD-REPEAT-PTLW-V1";
static constexpr char kCampaignId[] =
    "EC5_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V1";
static constexpr char kContractId[] =
    "113ed500b51b70f607dd8acda96e1c17a5ebb91e98faf70ea5e3d4f6d9528e86";
static constexpr char kNvsNamespace[] = "rlph_rptlw_v1";
static constexpr char kProfileId[] =
    "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";

static constexpr Window kWindows[kActionCount] = {
    {48, 64, 160, 120, 3, 3},
    {304, 240, 160, 120, 5, 5},
    {48, 416, 160, 120, 6, 6},
};

static constexpr ActionIdentity kActions[kActionCount] = {
    {"PATCH_A",
     "L535_REPEAT_PTLW_AFTER_PON_CODE3_DARK_A",
     "ea74430f9c07fb5266a5e95b73e3dce64b6b22d8d95118628558ba3be9c2f176",
     "eedc04bc4ee4e8ef0ef577631ff4fc7ca509a68264684113951c798f6f30a260",
     "89696fbebcc192494863d1e83f95b3a76a810def6a1a3efc8526f989c04f47a7",
     "6455e53da64c1ffd5644ab3b85d50d51b72ce699666cb7467d821e29e5732faa",
     "6455e53da64c1ffd5644ab3b85d50d51b72ce699666cb7467d821e29e5732faa",
     0xC30B65C5UL,
     0x06890D45UL,
     0x06890D45UL,
     {0, 0, 0, 38400, 0, 0, 0, 576000}},
    {"PATCH_B",
     "L535_REPEAT_PTLW_AFTER_PON_CODE5_BLUE_B_HOLD_A",
     "3dcf7b758a7e34688f226bfc50407afd4e0fb0dbfe41c5fed29d026bb2c66288",
     "05a90e8f45cce8fffdb3ec3df120956ebbecd8643193c3ab82f68e51f75d994d",
     "a604bb9d01b47d520c1c6cac9311f5f4761cd7e30361e3f13c79602c545e6f3a",
     "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3",
     "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3",
     0x0D48B5C5UL,
     0x77244145UL,
     0x77244145UL,
     {0, 0, 0, 38400, 0, 38400, 0, 537600}},
    {"PATCH_C",
     "L535_REPEAT_PTLW_AFTER_PON_CODE6_GREEN_C_HOLD_AB",
     "b7ed6f5d7ba0c8c806f6a8031b6f5cac8c61d0474d410090aacaecf9d66b014a",
     "d4b11a4aebae1aae329968254ffa3914769b44726985151caf9902b9bd96c9d5",
     "92c0c0a116e2bf1f78a652bbfb56f3705d254df104dd4b9d36a56907f1d1b4b7",
     "3102928873c21656da937b86e5821d4cf5c6d8ce664daba4db714447ac805d70",
     "3102928873c21656da937b86e5821d4cf5c6d8ce664daba4db714447ac805d70",
     0x302E12C5UL,
     0xD47193C5UL,
     0xD47193C5UL,
     {0, 0, 0, 38400, 0, 38400, 38400, 499200}},
};

static_assert(sizeof(kWindows) / sizeof(kWindows[0]) == kActionCount,
              "repeat-PTLW probe requires exactly three windows");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kActionCount,
              "repeat-PTLW probe requires exactly three cropped actions");
static_assert(kExternalFactoryWhiteAnchorRequired &&
                  kRepeatPtlwAfterPonBusy &&
                  !kRuntimeCode7ActionReachable,
              "repeat-PTLW external-anchor safety contract changed");

}  // namespace mf1750_runtime_lut_partial_hold_repeat_ptlw_v1
