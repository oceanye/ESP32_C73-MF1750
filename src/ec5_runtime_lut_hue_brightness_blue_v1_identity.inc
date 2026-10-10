#pragma once

namespace mf1750_runtime_lut_hue_brightness_blue_v1 {

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
static constexpr uint8_t kWhiteCode = 7;
static constexpr uint8_t kTargetCode = 5;
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
    "ACTIVE_CODE5_HIGH_CONFIDENCE_BLUE_UNCALIBRATED";
static constexpr char kVariantKey[] =
    "L535_TARGET_HUE_BLUE_BRIGHTNESS_HISTORY_8X8_ABA_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_TARGET_HUE_BLUE_BRIGHTNESS_8X8_ABA_V1_2026-08-24";
static constexpr char kTestId[] =
    "EC5-TARGET-HUE-BLUE-BRIGHTNESS-8X8-ABA-V1";
static constexpr char kCampaignId[] =
    "EC5_TARGET_HUE_BLUE_BRIGHTNESS_8X8_ABA_V1";
static constexpr char kContractId[] =
    "3d5dee5165a86ec470205bcd970c4d76fceb68599d4a54cc1aea882dae2bfee7";
static constexpr char kNvsNamespace[] = "rlhbb_v1";

// Cross-profile brightness screening is full-frame only. These valid dummy
// windows satisfy the shared immutable geometry guard and are never sent.
static constexpr Window kWindows[3] = {
    {48, 64, 160, 120, 3, 3},
    {304, 240, 160, 120, 5, 5},
    {48, 416, 160, 120, 6, 6},
};

static constexpr ActionIdentity kActions[kRoleIdentityCount] = {
    {"RUNTIME_LUT_WHITE_BASELINE",
     "L535_TARGET_HUE_BLUE_BRIGHTNESS_RUNTIME_WHITE_ACTIVE",
     "4b33b38c95e21b39112649b53dd28beb9d716f0326d573487b94699d2c4996be",
     "8466e0beb4912320c8b55dd9c28c7eb6e24e0376696371c84d957e388cb2ec4a",
     "f27255891c2b00350b2f7aca6f0719116c6a29262008b7621ef4b7df66b099f2",
     "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     0x7C918DC5UL,
     0x285715C5UL,
     0x285715C5UL,
     {0, 0, 0, 0, 0, 0, 0, 614400}},
    {"BLUE_LADDER_SOURCE_GRID_ACTIVE",
     "L535_TARGET_HUE_BLUE_BRIGHTNESS_SOURCE_COLUMNS_ACTIVE",
     "8eed0cfc72d64127a600dbe0591cc25111f921605093dca13f8f864890255035",
     "72346766e7cb957555dc7505e93edecb060addb3389d1cc3517846ee54cb5916",
     "fe420d9010e95b0347e7c468d18fb2283f4d5ede420a1ca811dafe9a1ebab853",
     "8aae76f672eb482772dd40b53840f70171db753477bb887cffb6b80dbb94dc74",
     "8aae76f672eb482772dd40b53840f70171db753477bb887cffb6b80dbb94dc74",
     0x5A43EDC5UL,
     0x1E3045C5UL,
     0x1E3045C5UL,
     {48256, 48256, 48256, 48256, 48256, 48256, 48256, 276608}},
    {"BLUE_LADDER_MIDDLE_GRID_COMMENTED",
     "L535_TARGET_HUE_BLUE_BRIGHTNESS_MIDDLE_ROWS_COMMENTED",
     "f7c77eb86ad77d2c75c82599ac387851d6de7bbec74149ed9bb932a9690d263c",
     "5076949066e825b5b6f5e4c3fb8b49713f9b7734a57f9ecb5e01604729ef0d39",
     "5d9d3fa7a873128c12ee4e2ab55e88ddf4e2388b6efd90a041c48b05f51e2dc3",
     "bfed84706002d390db5e5cc69b5111304e8fd5f6cdd251f6092229af3bc09f81",
     "bfed84706002d390db5e5cc69b5111304e8fd5f6cdd251f6092229af3bc09f81",
     0x199F2BC5UL,
     0xA0586A45UL,
     0xA0586A45UL,
     {48256, 48256, 48256, 48256, 48256, 48256, 48256, 276608}},
    {"BLUE_LADDER_FIXED_TARGET_ACTIVE_CODE5",
     "L535_TARGET_HUE_BLUE_BRIGHTNESS_FIXED_TARGET_ACTIVE_CODE5",
     "0339ef8b9a082ee64737c2e5040a674aa58f00c69c3d69ebc3f8f1b257b36c16",
     "5cc57eca3e37b261e8d5b3a5f77ad7857ed005cd553e07cfea5d3ad045b70122",
     "b67e352d9bba5947f5ea338ec93ed55147c46f3195015397e9393318c9d5ec7b",
     "fdde217c450f8081772e7e54e2cdabd0e7de5bf8af4fe123e8f46576caaa10af",
     "fdde217c450f8081772e7e54e2cdabd0e7de5bf8af4fe123e8f46576caaa10af",
     0xCFC80DC5UL,
     0xB5F255C5UL,
     0xB5F255C5UL,
     {0, 0, 0, 0, 0, 386048, 0, 228352}},
};

static_assert(kGridRows == 8 && kGridColumns == 8 && kTargetCode == 5,
              "blue brightness recipe cube changed");
static_assert(kGridX1Exclusive <= 512 && kGridY1Exclusive <= 600 &&
                  (kGridX0 & 1U) == 0 && (kCellWidth & 1U) == 0 &&
                  (kGapX & 1U) == 0 && !kCs2VerticalMirror,
              "blue brightness packed-grid geometry changed");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kRoleIdentityCount,
              "blue brightness role identities changed");

}  // namespace mf1750_runtime_lut_hue_brightness_blue_v1
