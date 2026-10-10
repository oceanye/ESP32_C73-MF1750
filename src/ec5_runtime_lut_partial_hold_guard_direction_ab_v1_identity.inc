#pragma once

namespace mf1750_runtime_lut_partial_hold_guard_direction_ab_v1 {

enum class GuardDirection : uint8_t { Top8 = 0, Bottom8 = 1 };

struct Window {
  uint16_t x;
  uint16_t y;
  uint16_t width;
  uint16_t height;
  uint8_t cs1Code;
  uint8_t cs2Code;
  GuardDirection cs1Guard;
  GuardDirection cs2Guard;
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

static constexpr uint8_t kRoleCount = 2;
static constexpr uint8_t kActionCount = 2;
static constexpr uint8_t kWhiteCode = 7;
static constexpr uint8_t kBlueCode = 5;
static constexpr uint8_t kGuardRows = 8;
static constexpr uint16_t kStreamRows = 128;
static constexpr size_t kStreamBytes = 10240;
static constexpr uint8_t kPartialWindowCommand = 0x83;
static constexpr uint8_t kPartialWindowPayloadBytes = 9;
static constexpr uint8_t kPartialWindowMode = 0x01;
static constexpr bool kCs2VerticalMirror = false;
static constexpr bool kSeparateCsWindowCommands = true;
static constexpr bool kExternalFactoryWhiteAnchorRequired = false;
static constexpr bool kFactoryOtpAnchorActionsReachable = true;
static constexpr bool kRepeatPtlwAfterPonBusy = true;
static constexpr bool kRuntimeCode7ActionReachable = false;
static constexpr char kVariantKey[] =
    "L535_FACTORY_WHITE_PTLW_GUARD_DIRECTION_CONTROLLER_SWAP_AB_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_RUNTIME_LUT_PTLW_GUARD_DIRECTION_AB_V1_2026-08-24";
static constexpr char kTestId[] =
    "EC5-RUNTIME-LUT-PTLW-GUARD-DIRECTION-AB-V1";
static constexpr char kCampaignId[] =
    "EC5_RUNTIME_LUT_PTLW_GUARD_DIRECTION_AB_V1";
static constexpr char kContractId[] =
    "c1ca226b7b5934dfba75daa7f03419c31438246638c86356d480e0abba84590c";
static constexpr char kNvsNamespace[] = "rlph_gdab_v1";
static constexpr char kProfileId[] =
    "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";

// The logical blue ROI always remains y=240..359.  Every PTLW declares 128
// rows and every DTM streams all 128 rows: either eight leading or eight
// trailing code-7 guard rows around the same 120 code-5 target rows.
static constexpr Window kWindows[kActionCount] = {
    {176, 240, 160, 120, 5, 5, GuardDirection::Bottom8,
     GuardDirection::Top8},
    {176, 240, 160, 120, 5, 5, GuardDirection::Top8,
     GuardDirection::Bottom8},
};

static constexpr ActionIdentity kActions[kActionCount] = {
    {"PATCH_A",
     "CODE5_BLUE_CS1_BOTTOM8_CS2_TOP8_SWAP_A",
     "8a66c05a20fc6fa6fdabf672ff8048ba116a5ff3388dcbea28f380d8fae95947",
     "871ffb507935b28849d3bef351199e1b8f149d1f96624ab709a7d2e7b725cb90",
     "c0b69123df2d5f80702d75301b453b1c46ff9fa945bea99fdcf75f298c2f9576",
     "aef979e3d8e8ffd5418a4ed3d5cf53a717fed933f4bd9887c9883fc2a6068caa",
     "c65c24867a086f0baf581081092bba1d7c52c408cf5aee2241139033aa370cb7",
     0x2E339DC5UL, 0xB58021C5UL, 0xCAE821C5UL,
     {0, 0, 0, 0, 0, 38400, 0, 576000}},
    {"PATCH_B",
     "CODE5_BLUE_CS1_TOP8_CS2_BOTTOM8_SWAP_B",
     "98befb1bbf1c8907e7679b8ca89fcb70d83a499a82bdd795557cae8927a45082",
     "002f4384ef433a082826f10b09ea9ce4d7461aaccea50869d0a18b662da42193",
     "c0b69123df2d5f80702d75301b453b1c46ff9fa945bea99fdcf75f298c2f9576",
     "c65c24867a086f0baf581081092bba1d7c52c408cf5aee2241139033aa370cb7",
     "aef979e3d8e8ffd5418a4ed3d5cf53a717fed933f4bd9887c9883fc2a6068caa",
     0x2E339DC5UL, 0xCAE821C5UL, 0xB58021C5UL,
     {0, 0, 0, 0, 0, 38400, 0, 576000}},
};

static_assert(sizeof(kWindows) / sizeof(kWindows[0]) == kActionCount,
              "guard-direction A/B requires exactly two windows");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kActionCount,
              "guard-direction A/B requires exactly two partial identities");
static_assert(kStreamRows == 128 && kStreamBytes == 10240 &&
                  kGuardRows == 8 && !kExternalFactoryWhiteAnchorRequired &&
                  kFactoryOtpAnchorActionsReachable &&
                  kRepeatPtlwAfterPonBusy && !kRuntimeCode7ActionReachable,
              "guard-direction transport contract changed");

}  // namespace mf1750_runtime_lut_partial_hold_guard_direction_ab_v1
