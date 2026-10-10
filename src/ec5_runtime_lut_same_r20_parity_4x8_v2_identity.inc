#pragma once

namespace mf1750_runtime_lut_same_r20_parity_4x8_v2 {

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

static constexpr uint8_t kRoleCount = 1;
static constexpr uint8_t kRoleIdentityCount = 1;
static constexpr uint8_t kSeparatorCode = 7;
static constexpr uint8_t kTargetCode = 0;
static constexpr uint8_t kFactoryWhiteFrameFillByte = 0x11;
static constexpr uint8_t kPartialWindowCommand = 0x83;
static constexpr uint8_t kPartialWindowPayloadBytes = 9;
static constexpr uint8_t kPartialWindowMode = 0x01;
static constexpr bool kCs2VerticalMirror = false;
static constexpr bool kSeparateCsWindowCommands = true;
static constexpr bool kPtlwYEndOneMore = false;
static constexpr uint8_t kGridRows = 4;
static constexpr uint8_t kGridColumns = 8;
static constexpr uint16_t kGridX0 = 20;
static constexpr uint16_t kGridY0 = 44;
static constexpr uint16_t kGridYByRow[4] = {44, 180, 316, 452};
static constexpr uint8_t kCodeRows[4][8] = {
    {0, 1, 2, 3, 4, 5, 6, 7},
    {6, 7, 0, 1, 2, 3, 4, 5},
    {5, 4, 7, 6, 1, 0, 3, 2},
    {3, 2, 5, 4, 7, 6, 1, 0},
};
static constexpr uint16_t kCellWidth = 52;
static constexpr uint16_t kCellHeight = 100;
static constexpr uint16_t kGapX = 8;
static constexpr uint16_t kGapY = 36;
static constexpr uint16_t kGridX1Exclusive = 492;
static constexpr uint16_t kGridY1Exclusive = 552;
static constexpr char kActiveProfileId[] =
    "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_ACTIVE535";
static constexpr char kCommentedProfileId[] =
    "LEGACY_COMMENTED_HEADER__CS1_COMMENTED535__CS2_COMMENTED535";
static constexpr char kVariantKey[] =
    "L535_SAME_R20_DUAL_CONTROLLER_PARITY_4X8_V2";
static constexpr char kBuildTag[] =
    "MF1750_EC5_SAME_R20_PARITY_4X8_V2_2026-08-28";
static constexpr char kTestId[] = "EC5-SAME-R20-PARITY-4X8-V2";
static constexpr char kCampaignId[] = "EC5_SAME_R20_PARITY_4X8_V2";
static constexpr char kContractId[] =
    "9e70a54e0ed1c3756357b2f3026e5651a7d1246294da6915397573b9b897a1ff";
static constexpr char kNvsNamespace[] = "sr20p4v2";
static constexpr char kNvsBootKey[] = "boot_s4v2";

// Full-frame only.  This inherited driver type is never emitted as PTLW.
static constexpr Window kWindows[1] = {{20, 44, 52, 100, 0, 0}};

static constexpr ActionIdentity kActions[kRoleIdentityCount] = {
    {"SAME_R20_ACTIVE_ACTIVE_POSITION_BALANCED_4X8_ATLAS",
     "L535_SAME_R20_DUAL_CONTROLLER_PARITY_4X8_V2_ACTIVE_ACTIVE_POSITION_BALANCED_ATLAS",
     "7f668842d3d4fca179049b309c298d0ff2d359c6bdd26550704e6929f1108cda",
     "2eef95155b78ee27b13e5971c40618106779495c80e0e3ef833eb2484f420476",
     "1ff9588f4f7d00d7e9dd0a89d2c4fb08c25db7e6e044ee467af6187b3270ad23",
     "2edcd090619b3a690b1d23db70df9b7648bad40b0512887df8a380a6f53fd1cb",
     "2edcd090619b3a690b1d23db70df9b7648bad40b0512887df8a380a6f53fd1cb",
     0x7F8C2EC5UL,
     0x8BA37FC5UL,
     0x8BA37FC5UL,
     {41600, 41600, 41600, 41600, 41600, 41600, 41600, 323200}},
};

static_assert(kGridRows == 4 && kGridColumns == 8,
              "position-balanced atlas geometry changed");
static_assert(kGridX1Exclusive <= 512 && kGridY1Exclusive <= 600 &&
                  (kGridX0 & 1U) == 0 && (kCellWidth & 1U) == 0 &&
                  (kGapX & 1U) == 0 && !kCs2VerticalMirror,
              "position-balanced packed-grid geometry changed");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kRoleIdentityCount,
              "position-balanced role identity changed");

}  // namespace mf1750_runtime_lut_same_r20_parity_4x8_v2
