#pragma once

namespace mf1750_runtime_lut_hue_brightness_yellow_olive_v1 {

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
static constexpr uint8_t kRoleIdentityCount = 4;
static constexpr uint8_t kSeparatorCode = 7;
static constexpr uint8_t kFactoryWhiteFrameFillByte = 0x11;
static constexpr uint8_t kTargetCode = 2;
static constexpr uint8_t kPartialWindowCommand = 0x83;
static constexpr uint8_t kPartialWindowPayloadBytes = 9;
static constexpr uint8_t kPartialWindowMode = 0x01;
static constexpr bool kCs2VerticalMirror = false;
static constexpr bool kSeparateCsWindowCommands = true;
static constexpr bool kPtlwYEndOneMore = false;
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
static constexpr char kActiveProfileId[] =
    "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";
static constexpr char kCommentedProfileId[] =
    "LEGACY_COMMENTED_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";
static constexpr char kTargetHueId[] =
    "Y_ACTIVE_CODE2_CS1_YELLOW_OLIVE_CANDIDATE_UNCALIBRATED";
static constexpr char kTargetHueCatalogId[] =
    "94eabf2d00b2f0e90e86201f54923029b25182c140c757023b77f8f302165fd8";
static constexpr char kVariantKey[] =
    "L535_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_HISTORY_8X8_ABA_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_8X8_ABA_V1_2026-08-26";
static constexpr char kTestId[] =
    "EC5-TARGET-HUE-YELLOW-OLIVE-BRIGHTNESS-8X8-ABA-V1";
static constexpr char kCampaignId[] =
    "EC5_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_8X8_ABA_V1";
static constexpr char kContractId[] =
    "47cff189c5719306693af8c0fe6cec7f6ae42ea7b9c3f82bfba94eecd0484899";
static constexpr char kNvsNamespace[] = "rlhyob_v1";
static constexpr char kBootBindingNvsKey[] = "boot_yob1";

// Full-frame only. These valid dummy windows satisfy the inherited geometry
// guard and are never emitted as partial-window commands.
static constexpr Window kWindows[3] = {
    {48, 64, 160, 120, 3, 3},
    {304, 240, 160, 120, 5, 5},
    {48, 416, 160, 120, 6, 6},
};

// Indexed by EpdChromaGridRole. Repeat and recovery actions have independent
// action IDs in the main table while reusing these exact compiled fixtures.
static constexpr ActionIdentity kActions[kRoleIdentityCount] = {
    {"FACTORY_OTP_WHITE_HEALTH_ANCHOR",
     "L535_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_HISTORY_8X8_ABA_V1_FACTORY_OTP_WHITE_HEALTH_ANCHOR",
     "1dc425968891e72e4fb377ef692d1a092f3e62ee00a9beec454cc689c0607abd",
     "479f3cd677ac2c3b65fa9950fad622533b9c678bb0d7146394b0bf78aed83c52",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {"YELLOW_OLIVE_LADDER_SOURCE_GRID_ACTIVE",
     "L535_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_HISTORY_8X8_ABA_V1_YELLOW_OLIVE_LADDER_SOURCE_GRID_ACTIVE",
     "656dab642504883363dceb94411df7abbba0c4e21ebd06630839b649f458457f",
     "012f89ef6a8194cdcbff17720a833861825d7d9655f517c2da92e86d91caea29",
     "fe420d9010e95b0347e7c468d18fb2283f4d5ede420a1ca811dafe9a1ebab853",
     "8aae76f672eb482772dd40b53840f70171db753477bb887cffb6b80dbb94dc74",
     "8aae76f672eb482772dd40b53840f70171db753477bb887cffb6b80dbb94dc74",
     0x5A43EDC5UL, 0x1E3045C5UL, 0x1E3045C5UL,
     {48256, 48256, 48256, 48256, 48256, 48256, 48256, 276608}},
    {"YELLOW_OLIVE_LADDER_MIDDLE_GRID_COMMENTED",
     "L535_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_HISTORY_8X8_ABA_V1_YELLOW_OLIVE_LADDER_MIDDLE_GRID_COMMENTED",
     "dbc836f85c23355aed4866f6a7614981a0b59bdb51b05dc9e802b8133a4575ea",
     "1d307a7c22bf54340d90ec3eaee548040933b899c159480898a4d96dbf494f4a",
     "5d9d3fa7a873128c12ee4e2ab55e88ddf4e2388b6efd90a041c48b05f51e2dc3",
     "bfed84706002d390db5e5cc69b5111304e8fd5f6cdd251f6092229af3bc09f81",
     "bfed84706002d390db5e5cc69b5111304e8fd5f6cdd251f6092229af3bc09f81",
     0x199F2BC5UL, 0xA0586A45UL, 0xA0586A45UL,
     {48256, 48256, 48256, 48256, 48256, 48256, 48256, 276608}},
    {"YELLOW_OLIVE_LADDER_FIXED_TARGET_ACTIVE_CODE2",
     "L535_TARGET_HUE_YELLOW_OLIVE_BRIGHTNESS_HISTORY_8X8_ABA_V1_YELLOW_OLIVE_LADDER_FIXED_TARGET_ACTIVE_CODE2",
     "08af57d294e026daf2e9c85651f495dc24cae64d94a5ddfe41fdb6370459d361",
     "7cfe7a0c92411656fa0ba0f1f512393818ab86e750ec71f4e2adaee0fff6d0fa",
     "6f975c438ae87d017c221c0ecb98a241d875f714bc236bc513ebe2ebcfcc2ce6",
     "506b9b914ac2039346e28d16b12bee7df393e7437f15d4de47bd3a9ac2986b63",
     "506b9b914ac2039346e28d16b12bee7df393e7437f15d4de47bd3a9ac2986b63",
     0x47DA93C5UL, 0x762B98C5UL, 0x762B98C5UL,
     {0, 0, 386048, 0, 0, 0, 0, 228352}},
};

static_assert(kGridRows == 8 && kGridColumns == 8 && kTargetCode == 2,
              "yellow/olive brightness recipe cube changed");
static_assert(kSeparatorCode == 7 && kFactoryWhiteFrameFillByte == 0x11,
              "separator or factory-white frame identity changed");
static_assert(kGridX1Exclusive <= 512 && kGridY1Exclusive <= 600 &&
                  (kGridX0 & 1U) == 0 && (kCellWidth & 1U) == 0 &&
                  (kGapX & 1U) == 0 && !kCs2VerticalMirror,
              "yellow/olive brightness packed-grid geometry changed");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kRoleIdentityCount,
              "yellow/olive brightness role identities changed");

}  // namespace mf1750_runtime_lut_hue_brightness_yellow_olive_v1
