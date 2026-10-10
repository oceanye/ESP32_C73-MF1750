#pragma once

namespace mf1750_runtime_lut_hue_brightness_redpink_v2 {

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
    "ACTIVE_CODE0_CS2_RED_CS1_OLIVE_YELLOWGREEN_CONTROLLER_SPECIFIC_UNCALIBRATED";
static constexpr char kVariantKey[] =
    "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_V2";
static constexpr char kBuildTag[] =
    "MF1750_EC5_TARGET_HUE_REDPINK_BRIGHTNESS_8X8_ABA_"
    "SINGLE_APP_BOOT_FLASH_VERIFY_V2_2026-08-27";
static constexpr char kTestId[] =
    "EC5-TARGET-HUE-REDPINK-BRIGHTNESS-8X8-ABA-V2";
static constexpr char kCampaignId[] =
    "EC5_TARGET_HUE_REDPINK_BRIGHTNESS_8X8_ABA_V2";
static constexpr char kContractId[] =
    "1308b6eb60ea786a2e1db2a2c984809fd446e9b1e32b1d14a54bf0356128ff8c";
static constexpr char kNvsNamespace[] = "rlhbrp_v2";
static constexpr char kNvsBootKey[] = "boot_rpb2";

// Full-frame only. These valid dummy windows satisfy the inherited geometry
// guard and are never sent as PTLW commands by this campaign.
static constexpr Window kWindows[3] = {
    {48, 64, 160, 120, 3, 3},
    {304, 240, 160, 120, 5, 5},
    {48, 416, 160, 120, 6, 6},
};

// Indexed by White/Source/Mid/Target. Repeated target and factory-white
// ordinals retain distinct action IDs in main_config while reusing exact
// compiled frame identities here.
static constexpr ActionIdentity kActions[kRoleIdentityCount] = {
    {"FACTORY_OTP_WHITE_HEALTH_ANCHOR",
     "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_V2_FACTORY_OTP_WHITE_HEALTH_ANCHOR",
     "a15984ff9d49a9f582f66e6b531ece72cceecc1a5da4d05114a29cd8728595d6",
     "5b49a9dd08873f820e319cc4f25a3f1e7f361ff472240f7b0976fc3d7b629c82",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL,
     0xB7A855C5UL,
     0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {"REDPINK_SOURCE_GRID_ACTIVE",
     "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_V2_REDPINK_SOURCE_GRID_ACTIVE",
     "f8be9c4b7a116bba02550a52d7d487129d21191d146b74daed2dd96753e5a997",
     "571c2123a04183e6b844056c98d8f09f8868bbfabbe4df1ad6e2f0dc2cc6cd0d",
     "fe420d9010e95b0347e7c468d18fb2283f4d5ede420a1ca811dafe9a1ebab853",
     "8aae76f672eb482772dd40b53840f70171db753477bb887cffb6b80dbb94dc74",
     "8aae76f672eb482772dd40b53840f70171db753477bb887cffb6b80dbb94dc74",
     0x5A43EDC5UL,
     0x1E3045C5UL,
     0x1E3045C5UL,
     {48256, 48256, 48256, 48256, 48256, 48256, 48256, 276608}},
    {"REDPINK_MIDDLE_GRID_COMMENTED",
     "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_V2_REDPINK_MIDDLE_GRID_COMMENTED",
     "500e3afbb4121920136a5f8bfe1a7a55efb76373fcd7c226afa4a4c4d2f82fe6",
     "fe222580dd4910e6655ecf7376e8d243d46af724674b20c88adef28d9547eba8",
     "5d9d3fa7a873128c12ee4e2ab55e88ddf4e2388b6efd90a041c48b05f51e2dc3",
     "bfed84706002d390db5e5cc69b5111304e8fd5f6cdd251f6092229af3bc09f81",
     "bfed84706002d390db5e5cc69b5111304e8fd5f6cdd251f6092229af3bc09f81",
     0x199F2BC5UL,
     0xA0586A45UL,
     0xA0586A45UL,
     {48256, 48256, 48256, 48256, 48256, 48256, 48256, 276608}},
    {"REDPINK_FIXED_TARGET_ACTIVE_CODE0",
     "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_V2_REDPINK_FIXED_TARGET_ACTIVE_CODE0",
     "77d9f6a4e2022fc3afb341379f6cdc2e9381706367d8bfbf13edba7758ed4809",
     "b7498932338a3165b6339acfe8ab675e77eac925487d3da7436bb92b6baff826",
     "9c771f6a89f72bdd64c38ddd99489accad9c5ed554d1841740517ea1100f7af4",
     "f36eeda01f7cdd5cda9147cece0a543009a217235c38b1ab3f636f24b2e4f4aa",
     "f36eeda01f7cdd5cda9147cece0a543009a217235c38b1ab3f636f24b2e4f4aa",
     0x2CC36BC5UL,
     0x4FA004C5UL,
     0x4FA004C5UL,
     {386048, 0, 0, 0, 0, 0, 0, 228352}},
};

static_assert(kGridRows == 8 && kGridColumns == 8 && kTargetCode == 0,
              "red/pink brightness recipe cube changed");
static_assert(kSeparatorCode == 7 && kFactoryWhiteFrameFillByte == 0x11,
              "separator/factory-white transport identities changed");
static_assert(kGridX1Exclusive <= 512 && kGridY1Exclusive <= 600 &&
                  (kGridX0 & 1U) == 0 && (kCellWidth & 1U) == 0 &&
                  (kGapX & 1U) == 0 && !kCs2VerticalMirror,
              "red/pink brightness packed-grid geometry changed");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kRoleIdentityCount,
              "red/pink brightness role identities changed");

}  // namespace mf1750_runtime_lut_hue_brightness_redpink_v2
