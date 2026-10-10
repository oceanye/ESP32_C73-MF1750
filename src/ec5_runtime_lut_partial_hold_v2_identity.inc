#pragma once

namespace mf1750_runtime_lut_partial_hold_v2 {

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
static constexpr uint8_t kWhiteCode = 1;
static constexpr uint8_t kPartialWindowCommand = 0x83;
static constexpr uint8_t kPartialWindowPayloadBytes = 9;
static constexpr uint8_t kPartialWindowMode = 0x01;
static constexpr bool kCs2VerticalMirror = false;
static constexpr bool kSeparateCsWindowCommands = true;
static constexpr bool kPtlwYEndOneMore = false;
static constexpr char kVariantKey[] =
    "L535_ACTIVE_GLOBAL_DISJOINT_Y_INCLUSIVE_CODE1_WHITE";
static constexpr char kBuildTag[] =
    "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_L535_ACTIVE_V2_2026-08-23";
static constexpr char kTestId[] =
    "EC5-RUNTIME-LUT-PARTIAL-HOLD-L535-ACTIVE-V2";
static constexpr char kCampaignId[] =
    "EC5_RUNTIME_LUT_PARTIAL_HOLD_L535_ACTIVE_V2";
static constexpr char kContractId[] =
    "b8d9728dc68011cf5ccb43e3ac73b103ffdb9ebeb3ace264b992e6a1cec3658e";
static constexpr char kNvsNamespace[] = "rlph_l535a_v2";
static constexpr char kProfileId[] =
    "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";

static constexpr Window kWindows[3] = {
    {48, 64, 160, 120, 0, 0},
    {304, 240, 160, 120, 5, 5},
    {48, 416, 160, 120, 6, 6},
};

static constexpr ActionIdentity kActions[kActionCount] = {
    {"RUNTIME_LUT_WHITE_BASELINE",
     "L535_ACTIVE_GLOBAL_FULL_WHITE_CODE1",
     "af587a615d9267094d4b33512721e04c8d44787eecd9c6e1216c287366873098",
     "9aedd39355a5d8f7d74c9bbdf54b848954434b2d28e31795ec330ce2ea91ff41",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {"PATCH_A",
     "L535_ACTIVE_GLOBAL_PTLW_CODE0_A",
     "a80188b2d0d4d60d4339025a063010c5f5ed311674a9374d1f840b8b077c6bcc",
     "80ebc10b3e306cad797a86668ff9749a0b4df3ff37fb3ff4b50246b1514ff2f8",
     "c9779c60dd8b2928fc74f6b204e59ad32fc8d6ee2a114f3c30880a1390ba55a1",
     "e9a15a094703faaea3fdf53af7e04da21717008ab4bb228799712b2fced03c65",
     "e9a15a094703faaea3fdf53af7e04da21717008ab4bb228799712b2fced03c65",
     0xE1B392C5UL, 0x0E5DBBC5UL, 0x0E5DBBC5UL,
     {38400, 576000, 0, 0, 0, 0, 0, 0}},
    {"PATCH_B",
     "L535_ACTIVE_GLOBAL_PTLW_CODE5_B_HOLD_A",
     "2c77b22a80a4639854923f821133abb6548e556b6a540c011be9f7ceb4c009e2",
     "5d6a8823fd11b1d8cfde5c673da4d319d65a4ad7a986bb0098538d5b1292269a",
     "4aea759af7a8bad48d75f2b60731b1f5a86884b5c2d2b15521b84057234a720f",
     "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3",
     "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3",
     0xDBC306C5UL, 0x77244145UL, 0x77244145UL,
     {38400, 537600, 0, 0, 0, 38400, 0, 0}},
    {"PATCH_C",
     "L535_ACTIVE_GLOBAL_PTLW_CODE6_C_HOLD_AB",
     "247e18ddc643a7631d175d68e5c5a17b3886d3f6510c8d51c6b55469455aa5cb",
     "6d530a6b9ee467361125fa12db83897178d254c3161e3e2cb8879a6e8c2739dc",
     "0b234deaca061cc3f00446c4614aa7938bc26d54488c67ed0f888dfb6a63b0c6",
     "3102928873c21656da937b86e5821d4cf5c6d8ce664daba4db714447ac805d70",
     "3102928873c21656da937b86e5821d4cf5c6d8ce664daba4db714447ac805d70",
     0x42E93BC5UL, 0xD47193C5UL, 0xD47193C5UL,
     {38400, 499200, 0, 0, 0, 38400, 38400, 0}},
    {"RUNTIME_LUT_WHITE_RECOVERY",
     "L535_ACTIVE_GLOBAL_FULL_WHITE_CODE1_RECOVERY",
     "45d18738f64689f803ea5d663200c40842eac85f7f95ae31692fe1df7862db48",
     "a12246327da51abf9684f1c4f7d6e59b9d373ba5ae45f7cb8ea61245f3cbd7f6",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
};

static_assert(sizeof(kWindows) / sizeof(kWindows[0]) == 3,
              "runtime-LUT partial HOLD V2 requires three windows");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kActionCount,
              "runtime-LUT partial HOLD V2 requires five actions");

}  // namespace mf1750_runtime_lut_partial_hold_v2
