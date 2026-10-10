#pragma once

namespace mf1750_position_balanced_gray_hold_successor_v1 {

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
static constexpr uint8_t kPreloadCode = 7;
static constexpr uint8_t kTargetCodes[2] = {3, 7};
static constexpr uint32_t kFullControllerDtmBytes = 153600;
static constexpr uint32_t kCroppedDtmBytes = 3840;
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

static constexpr uint8_t kGridRows = 8;
static constexpr uint8_t kGridColumns = 8;
static constexpr uint16_t kGridX0 = 68;
static constexpr uint16_t kGridY0 = 64;
static constexpr uint16_t kCellWidth = 40;
static constexpr uint16_t kCellHeight = 52;
static constexpr uint16_t kGapX = 8;
static constexpr uint16_t kGapY = 8;
static constexpr uint16_t kGridX1Exclusive = 444;
static constexpr uint16_t kGridY1Exclusive = 536;
static constexpr uint8_t kRecipeAtCellCs1[64] = {
    0, 1, 2, 3, 0, 1, 2, 3, 4, 5, 6, 7, 5, 6, 7, 4,
    8, 9, 10, 11, 10, 11, 8, 9, 12, 13, 14, 15, 15, 12, 13, 14,
    0, 5, 10, 15, 15, 14, 13, 12, 4, 9, 14, 3, 11, 10, 9, 8,
    8, 13, 2, 7, 7, 6, 5, 4, 12, 1, 6, 11, 3, 2, 1, 0,
};
static constexpr uint8_t kRecipeAtCellCs2[64] = {
    0, 1, 2, 3, 11, 6, 1, 12, 4, 5, 6, 7, 7, 2, 13, 8,
    8, 9, 10, 11, 3, 14, 9, 4, 12, 13, 14, 15, 15, 10, 5, 0,
    14, 13, 12, 15, 15, 14, 13, 12, 9, 8, 11, 10, 11, 10, 9, 8,
    4, 7, 6, 5, 7, 6, 5, 4, 3, 2, 1, 0, 3, 2, 1, 0,
};

static constexpr char kVariantKey[] =
    "POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1_2026-09-01";
static constexpr char kTestId[] =
    "EC5-POSITION-BALANCED-GRAY-HOLD-SUCCESSOR-V1";
static constexpr char kCampaignId[] =
    "EC5_POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1";
static constexpr char kContractId[] =
    "329e0bb6075291cc2bbdc1045a642b055b06fb8d312d2a7761b1332358e04229";
static constexpr char kNvsNamespace[] = "pbghs_v1";
static constexpr char kNvsKey[] = "cur_pbghs1";
static constexpr char kNvsBootKey[] = "boot_pbg1";

// Both windows are outside the G3 grid in top/bottom white bands.  Local x is
// strictly below 400, preserving every one of the 128 candidate cells.
static constexpr Window kHoldWindows[kHoldActionCount] = {
    {64, 8, 320, 24, 5, 5},
    {64, 568, 320, 24, 6, 6},
};
static constexpr uint8_t
    kPtlwPayloads[kHoldActionCount][kPartialWindowPayloadBytes] = {
        {0x00, 0x40, 0x01, 0x7F, 0x00, 0x08, 0x00, 0x1F, 0x01},
        {0x00, 0x40, 0x01, 0x7F, 0x02, 0x38, 0x02, 0x4F, 0x01},
};

static constexpr char kPreloadDtmSha256[] =
    "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd";
static constexpr uint32_t kPreloadDtmFnv1a = 0x285715C5UL;
static constexpr char kTargetDtmSha256[kHoldActionCount][65] = {
    "e86cfae35c2983b1b2f08a25f98304112c13ca9f29ae12614023b6d9c5338650",
    "b83e2e4addf1e5e63473804579942f23828c7ae1a1251cd2b81e3588efc4551c",
};
static constexpr uint32_t kTargetDtmFnv1a[kHoldActionCount] = {
    0xE35578C5UL,
    0x211299C5UL,
};
static constexpr char kCombinedDtmSha256[kHoldActionCount][65] = {
    "9bd5dc646efed6e4cb688e7b845c74a8977aa7427b2da2ddd95de535da2ba574",
    "5324b93196ab0a447bef321ea2f2f276905283a171e5c4394e5ec54a9f6438a7",
};
static constexpr uint32_t kCombinedDtmFnv1a[kHoldActionCount] = {
    0x9BAFF0C5UL,
    0xD96D11C5UL,
};

// Indexed by White/Source/Mid/Target/ReverseSource(H1)/ReverseTarget(H2).
// Roles 0..3 are unreachable fixtures; the firmware exposes H1/H2 only.
static constexpr ActionIdentity kActions[kRoleIdentityCount] = {
    {"UNREACHABLE_WHITE", "PBGHS1_UNREACHABLE_WHITE", nullptr, nullptr,
     nullptr, nullptr, nullptr, 0, 0, 0, {0, 0, 0, 0, 0, 0, 0, 0}},
    {"UNREACHABLE_G1", "PBGHS1_UNREACHABLE_G1", nullptr, nullptr,
     nullptr, nullptr, nullptr, 0, 0, 0, {0, 0, 0, 0, 0, 0, 0, 0}},
    {"UNREACHABLE_G2", "PBGHS1_UNREACHABLE_G2", nullptr, nullptr,
     nullptr, nullptr, nullptr, 0, 0, 0, {0, 0, 0, 0, 0, 0, 0, 0}},
    {"EXTERNAL_G3_SOURCE_NOT_REPLAYED", "PBGHS1_EXTERNAL_G3", nullptr,
     nullptr,
     "82f40036c115b3dea4d00099ef915aa693007abf73e1ddcf4d436f72807e1a1c",
     nullptr, nullptr, 0xDC41DAC5UL, 0, 0,
     {0, 0, 0, 133120, 0, 0, 0, 481280}},
    {"H1_ACTIVE_CODE5_TOP_WHITE_BAND_HOLD_RETAIN_ALL_G3",
     "POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1_H1_ACTIVE_CODE5_TOP_WHITE_BAND_HOLD_RETAIN_ALL_G3",
     "74f7b9b1dc91314425d2b7af485202a8d3c4ad9caef4ea000c5ef22225fec1cf",
     "366e5e3f337ec2cbe713f906af0f79a083e531de836e80b9b38066c7951255f5",
     "ddca13addf5b2bdecceda0a28887eb537c251d9f2e31cbbcf90d287f25b1d7f0",
     "9bd5dc646efed6e4cb688e7b845c74a8977aa7427b2da2ddd95de535da2ba574",
     "9bd5dc646efed6e4cb688e7b845c74a8977aa7427b2da2ddd95de535da2ba574",
     0x0F270EC5UL, 0x9BAFF0C5UL, 0x9BAFF0C5UL,
     {0, 0, 0, 133120, 0, 15360, 0, 465920}},
    {"H2_COMMENTED_CODE6_BOTTOM_WHITE_BAND_HOLD_RETAIN_ALL_G3_AND_H1",
     "POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1_H2_COMMENTED_CODE6_BOTTOM_WHITE_BAND_HOLD_RETAIN_ALL_G3_AND_H1",
     "0110a55422874ffb3294af146be5e4955e226617624f20f20a653fb515f1d186",
     "ba7557595d9780f8ef0354abf0083b43735b5a642411aa63ce08a247f40e253c",
     "9af56422de21dadfbdb6dbcee9aa75efaf2ecaf8a081ebc32b2d9a7a90140676",
     "5324b93196ab0a447bef321ea2f2f276905283a171e5c4394e5ec54a9f6438a7",
     "5324b93196ab0a447bef321ea2f2f276905283a171e5c4394e5ec54a9f6438a7",
     0x7D6400C5UL, 0xD96D11C5UL, 0xD96D11C5UL,
     {0, 0, 0, 133120, 0, 15360, 15360, 450560}},
};

static_assert(kHoldWindows[0].x + kHoldWindows[0].width <= 400 &&
                  kHoldWindows[1].x + kHoldWindows[1].width <= 400 &&
                  kHoldWindows[0].y + kHoldWindows[0].height <= kGridY0 &&
                  kHoldWindows[1].y >= kGridY1Exclusive,
              "HOLD windows must remain in disjoint G3 white bands");
static_assert(!kRepeatPtlwAfterPonBusy && !kActionStageCdi &&
                  !kActionStageBtst2 && !kCommand0x86Reachable,
              "clean HOLD transport changed");

}  // namespace mf1750_position_balanced_gray_hold_successor_v1
