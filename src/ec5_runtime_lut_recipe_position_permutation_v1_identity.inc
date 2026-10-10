#pragma once

namespace mf1750_runtime_lut_recipe_position_permutation_v1 {

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
static constexpr uint8_t kTargetCode = 0;
static constexpr uint8_t kFactoryWhiteFrameFillByte = 0x11;
static constexpr uint8_t kSourceColumnShift = 3;
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
static constexpr char kVariantKey[] =
    "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_"
    "ABA_RECIPE_PERMUTATION_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_REDPINK_RECIPE_POSITION_PERMUTATION_P1_8X8_ACA_"
    "SINGLE_APP_BOOT_FLASH_VERIFY_V1_2026-08-28";
static constexpr char kTestId[] =
    "EC5-REDPINK-RECIPE-POSITION-PERMUTATION-P1-8X8-ACA-V1";
static constexpr char kCampaignId[] =
    "EC5_REDPINK_RECIPE_POSITION_PERMUTATION_P1_8X8_ACA_V1";
static constexpr char kContractId[] =
    "5c628ccd1755718a6cc7aa0163523122f083bd51085f356ce75c23ea62d4dda2";
static constexpr char kNvsNamespace[] = "rppp1";
static constexpr char kNvsBootKey[] = "boot_rpp1";

// Full-frame only. These valid dummy windows satisfy the inherited geometry
// guard and are never sent as PTLW commands by this campaign.
static constexpr Window kWindows[3] = {
    {48, 64, 160, 120, 3, 3},
    {304, 240, 160, 120, 5, 5},
    {48, 416, 160, 120, 6, 6},
};

// Indexed by the shared driver enum: White, Source, Mid, Target.  Main_config
// orders the four independently armed actions as Source, Mid, Target, White.
static constexpr ActionIdentity kActions[kRoleIdentityCount] = {
    {"FACTORY_OTP_WHITE_RECOVERY",
     "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_RECIPE_PERMUTATION_V1_FACTORY_OTP_WHITE_RECOVERY",
     "4dd63a9e7d1abec4d656a5cf54446634454a70b6468d676f31ad1020cbb26a0d",
     "4d4b247bc8d398462102b3d8cabd1bf29970bda89cfb3d8f05b368f628000a99",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL,
     0xB7A855C5UL,
     0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {"PERMUTED_SOURCE_GRID_ACTIVE_SHIFT3",
     "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_RECIPE_PERMUTATION_V1_PERMUTED_SOURCE_GRID_ACTIVE_SHIFT3",
     "57af72e88ad43fd80f29243ed475d6571c01c66c46cadc4ee8baf91aa5a92855",
     "afd5f9834cedb536ee50b62fd80f1a1b038786f8512e9594c34a515ba280cd00",
     "dd4ee3f40ac007a778f4d041d6e5a219186a5d1e5c1bf5aca31cf510754dafd6",
     "edc0b5673c53be68b3ad2b74e376da5d6e9539870352c7630aac6d232b9e0508",
     "edc0b5673c53be68b3ad2b74e376da5d6e9539870352c7630aac6d232b9e0508",
     0x58900DC5UL,
     0x19E62DC5UL,
     0x19E62DC5UL,
     {48256, 48256, 48256, 48256, 48256, 48256, 48256, 276608}},
    {"PERMUTED_MIDDLE_GRID_COMMENTED_REVERSE",
     "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_RECIPE_PERMUTATION_V1_PERMUTED_MIDDLE_GRID_COMMENTED_REVERSE",
     "636c8f05f2e90e80ab779e977c9805a3f90f701dbb93f44d6ccde5b46affd677",
     "c75a829ed8116c228913525fff87db5fac41e127dc45013ee86386e9ee65dcbf",
     "12b96bf001bee93f41417cfecdcd78a8941a4effbcd9a5d10c9f527e6bdf075b",
     "29c526661cb9e5a26fccee78de75adb1e4921f32c3cd8c9d0652418314de6b1b",
     "29c526661cb9e5a26fccee78de75adb1e4921f32c3cd8c9d0652418314de6b1b",
     0x5B663FC5UL,
     0x9F3BCA45UL,
     0x9F3BCA45UL,
     {48256, 48256, 48256, 48256, 48256, 48256, 48256, 276608}},
    {"PERMUTED_FIXED_TARGET_ACTIVE_CODE0",
     "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_RECIPE_PERMUTATION_V1_PERMUTED_FIXED_TARGET_ACTIVE_CODE0",
     "f798106e2bbd5c130876e8d8c8919de45c086d16cc5398f39ea3f3b45e6f17d8",
     "8a9a17c4e69b20278b513965cde248e1e6036dceee8943e269ed0693d216b4c9",
     "9c771f6a89f72bdd64c38ddd99489accad9c5ed554d1841740517ea1100f7af4",
     "f36eeda01f7cdd5cda9147cece0a543009a217235c38b1ab3f636f24b2e4f4aa",
     "f36eeda01f7cdd5cda9147cece0a543009a217235c38b1ab3f636f24b2e4f4aa",
     0x2CC36BC5UL,
     0x4FA004C5UL,
     0x4FA004C5UL,
     {386048, 0, 0, 0, 0, 0, 0, 228352}},
};

static_assert(kGridRows == 8 && kGridColumns == 8 && kTargetCode == 0 &&
                  kSourceColumnShift == 3,
              "recipe-position permutation changed");
static_assert(kSeparatorCode == 7 && kFactoryWhiteFrameFillByte == 0x11,
              "separator/factory-white transport identities changed");
static_assert(kGridX1Exclusive <= 512 && kGridY1Exclusive <= 600 &&
                  (kGridX0 & 1U) == 0 && (kCellWidth & 1U) == 0 &&
                  (kGapX & 1U) == 0 && !kCs2VerticalMirror,
              "recipe-position permutation packed-grid geometry changed");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kRoleIdentityCount,
              "recipe-position permutation role identities changed");

}  // namespace mf1750_runtime_lut_recipe_position_permutation_v1
