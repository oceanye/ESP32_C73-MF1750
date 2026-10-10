#pragma once

namespace mf1750_runtime_lut_multi_target_history_v1 {

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
static constexpr uint8_t kSeparatorCode = 7;
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
static constexpr char kVariantKey[] =
    "L535_MULTI_TARGET_HISTORY_8X8_AB_BA_FACTORY_WHITE_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_MULTI_TARGET_HISTORY_8X8_AB_BA_V1_2026-08-24";
static constexpr char kTestId[] =
    "EC5-MULTI-TARGET-HISTORY-8X8-AB-BA-V1";
static constexpr char kCampaignId[] =
    "EC5_MULTI_TARGET_HISTORY_8X8_AB_BA_V1";
static constexpr char kContractId[] =
    "7f653cc9412d9b90a2c17a471dd54bfe0605c4abad41eeabe76ba1828f1958da";
static constexpr char kNvsNamespace[] = "rlmth_v1";

// Full-frame only. These valid dummy windows satisfy the shared geometry
// guard and are never sent as PTLW commands by this campaign.
static constexpr Window kWindows[3] = {
    {48, 64, 160, 120, 3, 3},
    {304, 240, 160, 120, 5, 5},
    {48, 416, 160, 120, 6, 6},
};

// Indexed by EpdChromaGridRole. Repeated target actions reuse the same
// compiled frame/profile role while retaining distinct host action IDs.
static constexpr ActionIdentity kActions[kRoleIdentityCount] = {
    {"FACTORY_OTP_WHITE_HEALTH_ANCHOR",
     "L535_MULTI_TARGET_HISTORY_8X8_AB_BA_FACTORY_WHITE_V1_FACTORY_OTP_WHITE_HEALTH_ANCHOR",
     "84aa76944c69d73c732824f7398a6c498432461fc66df56a990c650746014baf",
     "3086cc9437813a88fb49febe0c68fbb958ab08ca9022d566c5cbbe44c6671788",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {"AB_ACTIVE_SOURCE_COLUMNS",
     "L535_MULTI_TARGET_HISTORY_8X8_AB_BA_FACTORY_WHITE_V1_AB_ACTIVE_SOURCE_COLUMNS",
     "77cb4f956342f0c612c7daf9eee97b6fe02fb268c52ff3fa276e9a23a0496e1c",
     "d4a965f907f2cf951d8be1cc80cf6c776a50621cff41a4addf8711392241ba32",
     "fe420d9010e95b0347e7c468d18fb2283f4d5ede420a1ca811dafe9a1ebab853",
     "8aae76f672eb482772dd40b53840f70171db753477bb887cffb6b80dbb94dc74",
     "8aae76f672eb482772dd40b53840f70171db753477bb887cffb6b80dbb94dc74",
     0x5A43EDC5UL, 0x1E3045C5UL, 0x1E3045C5UL,
     {48256, 48256, 48256, 48256, 48256, 48256, 48256, 276608}},
    {"AB_COMMENTED_TARGET_ROWS",
     "L535_MULTI_TARGET_HISTORY_8X8_AB_BA_FACTORY_WHITE_V1_AB_COMMENTED_TARGET_ROWS",
     "c99f99f140d4b792e4e988bf4a517567c0edffe899a0c00b91be6deb882e36ef",
     "54767eefbcc4feabe7afa1b8fafb88130793cbf793b0c00c4bbfee64c221f8e0",
     "5d9d3fa7a873128c12ee4e2ab55e88ddf4e2388b6efd90a041c48b05f51e2dc3",
     "bfed84706002d390db5e5cc69b5111304e8fd5f6cdd251f6092229af3bc09f81",
     "bfed84706002d390db5e5cc69b5111304e8fd5f6cdd251f6092229af3bc09f81",
     0x199F2BC5UL, 0xA0586A45UL, 0xA0586A45UL,
     {48256, 48256, 48256, 48256, 48256, 48256, 48256, 276608}},
    {"AB_COMMENTED_TARGET_ROWS_IDENTICAL_REPEAT",
     "L535_MULTI_TARGET_HISTORY_8X8_AB_BA_FACTORY_WHITE_V1_AB_COMMENTED_TARGET_ROWS_IDENTICAL_REPEAT",
     "b2507fcdde1672c93d01ba48cedea99b9837d52cf9e87b99f88734342c8a5d2d",
     "f6e7aef63716eb4eb81d1f38ca41c5f4430784b653a5674908d887f61acd2d36",
     "5d9d3fa7a873128c12ee4e2ab55e88ddf4e2388b6efd90a041c48b05f51e2dc3",
     "bfed84706002d390db5e5cc69b5111304e8fd5f6cdd251f6092229af3bc09f81",
     "bfed84706002d390db5e5cc69b5111304e8fd5f6cdd251f6092229af3bc09f81",
     0x199F2BC5UL, 0xA0586A45UL, 0xA0586A45UL,
     {48256, 48256, 48256, 48256, 48256, 48256, 48256, 276608}},
    {"BA_COMMENTED_SOURCE_COLUMNS",
     "L535_MULTI_TARGET_HISTORY_8X8_AB_BA_FACTORY_WHITE_V1_BA_COMMENTED_SOURCE_COLUMNS",
     "62d2400ca7b885473d10192ad6dfe679fe17c452f205462735c044e516925d9c",
     "d3bea074e004774447adc6310d5ab310ce7b92e1c4f8fc6fd12208f2689209fe",
     "fe420d9010e95b0347e7c468d18fb2283f4d5ede420a1ca811dafe9a1ebab853",
     "8aae76f672eb482772dd40b53840f70171db753477bb887cffb6b80dbb94dc74",
     "8aae76f672eb482772dd40b53840f70171db753477bb887cffb6b80dbb94dc74",
     0x5A43EDC5UL, 0x1E3045C5UL, 0x1E3045C5UL,
     {48256, 48256, 48256, 48256, 48256, 48256, 48256, 276608}},
    {"BA_ACTIVE_TARGET_ROWS",
     "L535_MULTI_TARGET_HISTORY_8X8_AB_BA_FACTORY_WHITE_V1_BA_ACTIVE_TARGET_ROWS",
     "206da743f3973446689cf82793e45de2e57172215149ed854d5398ac01694523",
     "2b1dc1ff19809de09efe0873ff15aaa1d4c39a5b11473021634c2380e88db388",
     "5d9d3fa7a873128c12ee4e2ab55e88ddf4e2388b6efd90a041c48b05f51e2dc3",
     "bfed84706002d390db5e5cc69b5111304e8fd5f6cdd251f6092229af3bc09f81",
     "bfed84706002d390db5e5cc69b5111304e8fd5f6cdd251f6092229af3bc09f81",
     0x199F2BC5UL, 0xA0586A45UL, 0xA0586A45UL,
     {48256, 48256, 48256, 48256, 48256, 48256, 48256, 276608}},
};

static_assert(kGridRows == 8 && kGridColumns == 8 && kSeparatorCode == 7,
              "multi-target grid contract changed");
static_assert(kFactoryWhiteFrameFillByte == 0x11,
              "factory white frame identity changed");
static_assert(kGridX1Exclusive <= 512 && kGridY1Exclusive <= 600 &&
                  (kGridX0 & 1U) == 0 && (kCellWidth & 1U) == 0 &&
                  (kGapX & 1U) == 0 && !kCs2VerticalMirror,
              "multi-target packed-grid geometry changed");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kRoleIdentityCount,
              "multi-target role identities changed");

}  // namespace mf1750_runtime_lut_multi_target_history_v1
