#pragma once

namespace mf1750_runtime_lut_partial_hold_v4 {

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
    "L535_ACTIVE_GLOBAL_Y_INCLUSIVE_CODE7_PACKED_BASELINE_V4";
static constexpr char kBuildTag[] =
    "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_L535_ACTIVE_V4_2026-08-23";
static constexpr char kTestId[] =
    "EC5-RUNTIME-LUT-PARTIAL-HOLD-L535-ACTIVE-V4";
static constexpr char kCampaignId[] =
    "EC5_RUNTIME_LUT_PARTIAL_HOLD_L535_ACTIVE_V4";
static constexpr char kContractId[] =
    "f4d3ea598761fd833d15a263d690dc0d75931da106d81e53e93605ecc19ecd42";
static constexpr char kNvsNamespace[] = "rlph_l535a_v4";
static constexpr char kProfileId[] =
    "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";

static constexpr Window kWindows[3] = {
    {48, 64, 160, 120, 3, 3},
    {304, 240, 160, 120, 5, 5},
    {48, 416, 160, 120, 6, 6},
};

static constexpr ActionIdentity kActions[kActionCount] = {
    {"RUNTIME_LUT_WHITE_BASELINE",
     "L535_ACTIVE_GLOBAL_PACKED_FRAME_CODE7_WHITE",
     "0a78d34505ee03d0b1c2d2d83bc1f2eeaca431481d8cb77bb7213e036f83ad8b",
     "08b774e47a269ea480b8e4369fad4918110ea0dc1124f94c4c61c94c913ef9ba",
     "f27255891c2b00350b2f7aca6f0719116c6a29262008b7621ef4b7df66b099f2",
     "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     0x7C918DC5UL, 0x285715C5UL, 0x285715C5UL,
     {0, 0, 0, 0, 0, 0, 0, 614400}},
    {"PATCH_A",
     "L535_ACTIVE_GLOBAL_PTLW_CODE3_DARK_A",
     "a082e06180f485c167a4b18a6764ea73afefdd85be97d5f1f90f13a1146b52cc",
     "5807b39019d394c8f5f6942a128b297dc4c88e2da225d96a0485ef1bfe072c24",
     "89696fbebcc192494863d1e83f95b3a76a810def6a1a3efc8526f989c04f47a7",
     "6455e53da64c1ffd5644ab3b85d50d51b72ce699666cb7467d821e29e5732faa",
     "6455e53da64c1ffd5644ab3b85d50d51b72ce699666cb7467d821e29e5732faa",
     0xC30B65C5UL, 0x06890D45UL, 0x06890D45UL,
     {0, 0, 0, 38400, 0, 0, 0, 576000}},
    {"PATCH_B",
     "L535_ACTIVE_GLOBAL_PTLW_CODE5_BLUE_B_HOLD_A",
     "b4d113909b2ed0dcd0e0df1a7380e610edc3ac511f5cf3237159b7418b07c6fd",
     "d0b27ebc4dc8066381b1848898a56f05733d9f1b9798ef24af2b8a5450286a5a",
     "a604bb9d01b47d520c1c6cac9311f5f4761cd7e30361e3f13c79602c545e6f3a",
     "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3",
     "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3",
     0x0D48B5C5UL, 0x77244145UL, 0x77244145UL,
     {0, 0, 0, 38400, 0, 38400, 0, 537600}},
    {"PATCH_C",
     "L535_ACTIVE_GLOBAL_PTLW_CODE6_GREEN_C_HOLD_AB",
     "bf5451f859de07ffa66967c6028c8cdb5feb7b0003fa998fa5185152f4f5b0af",
     "24db2dbb46c9fd462c3396013c3d9aa700ec8eebcc6b57d5056f193d1fcd2a5d",
     "92c0c0a116e2bf1f78a652bbfb56f3705d254df104dd4b9d36a56907f1d1b4b7",
     "3102928873c21656da937b86e5821d4cf5c6d8ce664daba4db714447ac805d70",
     "3102928873c21656da937b86e5821d4cf5c6d8ce664daba4db714447ac805d70",
     0x302E12C5UL, 0xD47193C5UL, 0xD47193C5UL,
     {0, 0, 0, 38400, 0, 38400, 38400, 499200}},
    {"RUNTIME_LUT_WHITE_RECOVERY",
     "L535_ACTIVE_GLOBAL_PACKED_FRAME_CODE7_WHITE_RECOVERY",
     "89043fdcda7cadafeb2fd1c9e54d66dc24543bf488f6d8b628d08a02917833d2",
     "6f18f820a5430253b9cda3de3ba8ee7119390ad3ae4002ffb8a730385b74a80d",
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

}  // namespace mf1750_runtime_lut_partial_hold_v4
