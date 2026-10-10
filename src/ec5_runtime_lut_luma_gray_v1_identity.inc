#pragma once

namespace mf1750_runtime_lut_luma_gray_v1 {

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

static constexpr uint8_t kRoleCount = 5;
static constexpr uint8_t kRoleIdentityCount = 5;
static constexpr uint8_t kSeparatorCode = 7;
static constexpr uint8_t kTargetCodePage1 = 3;
static constexpr uint8_t kTargetCodePage2 = 7;
static constexpr uint8_t kSourceAnchorCodes[2] = {3, 7};
static constexpr uint8_t kFactoryWhiteFrameFillByte = 0x11;
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
static constexpr uint8_t kRecipeAtCell[64] = {
    0, 1, 2, 3, 0, 1, 2, 3, 4, 5, 6, 7, 5, 6, 7, 4,
    8, 9, 10, 11, 10, 11, 8, 9, 12, 13, 14, 15, 15, 12, 13, 14,
    0, 5, 10, 15, 15, 14, 13, 12, 4, 9, 14, 3, 11, 10, 9, 8,
    8, 13, 2, 7, 7, 6, 5, 4, 12, 1, 6, 11, 3, 2, 1, 0,
};
static constexpr char kVariantKey[] =
    "L535_LUMA_GRAY_EXPLORATORY_2PAGE_4X_REPEAT_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_LUMA_GRAY_EXPLORATORY_2PAGE_V1_2026-08-28";
static constexpr char kTestId[] = "EC5-LUMA-GRAY-EXPLORATORY-2PAGE-V1";
static constexpr char kCampaignId[] = "EC5_LUMA_GRAY_EXPLORATORY_2PAGE_V1";
static constexpr char kContractId[] =
    "db671c68cc1141231cbb0baf5f0667e6cdc292095af7b4f3cf9c3d5001d1b260";
static constexpr char kNvsNamespace[] = "rllg_v1";
static constexpr char kNvsBootKey[] = "boot_lg1";

// Full-frame only. Dummy windows retain the inherited, compile-time window
// guard but are never sent to the panel by this campaign.
static constexpr Window kWindows[3] = {
    {48, 64, 160, 120, 3, 3},
    {304, 240, 160, 120, 5, 5},
    {48, 416, 160, 120, 6, 6},
};

// Indexed by White/Source/Mid/Target/ReverseSource.  Page-2 source and middle
// actions intentionally reuse the exact Source/Mid identities.
static constexpr ActionIdentity kActions[kRoleIdentityCount] = {
    {"FACTORY_OTP_WHITE_HEALTH_ANCHOR", "L535_LUMA_GRAY_EXPLORATORY_2PAGE_4X_REPEAT_V1_FACTORY_OTP_WHITE_HEALTH_ANCHOR",
     "1f507bd6fd65e630ba1202d2f427b59e2d311180494590c1926364a09bd8f88c", "6af04385a8eb34055f12fb70af6dfd7bc498942a44e8bb602eba029fa2b2532a",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d", "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158", "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL, {0, 614400, 0, 0, 0, 0, 0, 0}},
    {"PAGE1_ACTIVE_SOURCE_ANCHORS_3_7", "L535_LUMA_GRAY_EXPLORATORY_2PAGE_4X_REPEAT_V1_PAGE1_ACTIVE_SOURCE_ANCHORS_3_7",
     "e021b9435c227d072ad6016b7cd2c69a5d30bac61b712a88f17e41d5f159df07", "c0fbc4fdba5bb6a1caff510c2b5f373e3d03c8c8bde07ad4ca33555e199097e5",
     "f6ba2d8781e6d986a865ff2504ef825c016597af56dcd8c0d2a207130d323048", "1a75b6485b7dd5bab843786b069ad22fb17459b50562e254c4952d0f5bd04b57", "1a75b6485b7dd5bab843786b069ad22fb17459b50562e254c4952d0f5bd04b57",
     0x5410A745UL, 0xD7AA85C5UL, 0xD7AA85C5UL, {0, 0, 0, 193024, 0, 0, 0, 421376}},
    {"PAGE1_COMMENTED_MIDDLE_CODES_0_7", "L535_LUMA_GRAY_EXPLORATORY_2PAGE_4X_REPEAT_V1_PAGE1_COMMENTED_MIDDLE_CODES_0_7",
     "e6abe5e077cf590282966cc666af41ac9c40392cb64d6d81b84952739b76dc1d", "4b27ae57ba6fd8848c66413f580013cc51a558c3205bd7a99771c93251672a53",
     "2060bd9c15596d523be2501878946229c95b581c769f40daec88ef7cce300f52", "3db06a28c153f6a484e2e25cbbb99abcd18d3c51b931906f14c13e3243901ada", "3db06a28c153f6a484e2e25cbbb99abcd18d3c51b931906f14c13e3243901ada",
     0x6BCEDA45UL, 0x0D461F65UL, 0x0D461F65UL, {48256, 48256, 48256, 48256, 48256, 48256, 48256, 276608}},
    {"PAGE1_ACTIVE_TARGET_CODE3", "L535_LUMA_GRAY_EXPLORATORY_2PAGE_4X_REPEAT_V1_PAGE1_ACTIVE_TARGET_CODE3",
     "7a140f2d880ddbb31915a7acec1d5d2125e45bc49a57fb5fe6fffe8c826ac179", "d91d22d0a5725bcd08bda5ce61e6cb115cd420fadc9e642a95392bb8337e36d8",
     "1714bf0f1daf154385f4fbe8f0c1203210c5c91ca099633c96faf96b4eac1b9e", "d414e3f3c7f160d06e93a970f39214032b1069f8cded3dc04eacf887c173668d", "d414e3f3c7f160d06e93a970f39214032b1069f8cded3dc04eacf887c173668d",
     0x04485DC5UL, 0x28B27DC5UL, 0x28B27DC5UL, {0, 0, 0, 386048, 0, 0, 0, 228352}},
    {"PAGE2_ACTIVE_TARGET_CODE7", "L535_LUMA_GRAY_EXPLORATORY_2PAGE_4X_REPEAT_V1_PAGE2_ACTIVE_TARGET_CODE7",
     "5e345976495bdf8f34501af790d563783f4afe1a9bb8d6a9fd2307a316aee55b", "d8972e344c2acaa0c6e43a9ea34dc00c18acc7e4970ef339fb7d01a38e18752f",
     "f27255891c2b00350b2f7aca6f0719116c6a29262008b7621ef4b7df66b099f2", "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd", "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     0x7C918DC5UL, 0x285715C5UL, 0x285715C5UL, {0, 0, 0, 0, 0, 0, 0, 614400}},
};

static_assert(kGridX1Exclusive <= 512 && kGridY1Exclusive <= 600 &&
                  (kGridX0 & 1U) == 0 && (kCellWidth & 1U) == 0 &&
                  (kGapX & 1U) == 0 && !kCs2VerticalMirror,
              "LUMA-GRAY packed-grid geometry changed");
static_assert(sizeof(kRecipeAtCell) == 64 && kRoleIdentityCount == 5,
              "LUMA-GRAY recipe/role identity count changed");

}  // namespace mf1750_runtime_lut_luma_gray_v1
