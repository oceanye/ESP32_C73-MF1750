#pragma once

namespace mf1750_p1_active_endpoint_atlas_4x8_v1 {

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
    {4, 5, 6, 7, 0, 1, 2, 3},
    {1, 2, 3, 4, 5, 6, 7, 0},
    {5, 6, 7, 0, 1, 2, 3, 4},
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
static constexpr char kVariantKey[] = "P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_2026-09-01";
static constexpr char kTestId[] = "EC5-P1-ACTIVE-ENDPOINT-ATLAS-4X8-V1";
static constexpr char kCampaignId[] =
    "EC5_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1";
static constexpr char kContractId[] =
    "d36450e7cf69ad2e5e612f9df5b5abe0d33a036f9c3198a79a9e0e97a89a59f2";
static constexpr char kNvsNamespace[] = "p1ae4x8v1";
static constexpr char kNvsBootKey[] = "boot_p1a";

// Full-frame only. This inherited driver type is never emitted as PTLW.
static constexpr Window kWindows[1] = {{20, 44, 52, 100, 0, 0}};

static constexpr ActionIdentity kActions[kRoleIdentityCount] = {{
    "P1_ACTIVE_COMPLETE_PROFILE_POSITION_BALANCED_4X8_ENDPOINT_ATLAS",
    "P1_FRESH_ONE_SHOT_ACTIVE_ACTIVE_ENDPOINT_ATLAS_4X8_V1",
    "14a1b108c74e8898a1e5cc235ff93fdc8b315aebc45fc4682481a6aa915187d2",
    "7d14bc5f70da46f1eb3a86ab1c54734dffa1e9dcac62147a1d62bcedb25e9526",
    "d8ee6b0889c8c2e92e3d0d34410f93d90f924816c59987de496ef0ca27ac1768",
    "b64c835514b4b6110002c1c2cb366a93bf804f5953229107fa52b27de83dfe0f",
    "b64c835514b4b6110002c1c2cb366a93bf804f5953229107fa52b27de83dfe0f",
    0xBA8135C5UL,
    0xFA8EE9C5UL,
    0xFA8EE9C5UL,
    {41600, 41600, 41600, 41600, 41600, 41600, 41600, 323200},
}};

static_assert(kGridRows == 4 && kGridColumns == 8,
              "P1 endpoint atlas geometry changed");
static_assert(kGridX1Exclusive <= 512 && kGridY1Exclusive <= 600 &&
                  (kGridX0 & 1U) == 0 && (kCellWidth & 1U) == 0 &&
                  (kGapX & 1U) == 0 && !kCs2VerticalMirror,
              "P1 packed-grid geometry changed");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kRoleIdentityCount,
              "P1 endpoint role identity changed");

}  // namespace mf1750_p1_active_endpoint_atlas_4x8_v1
