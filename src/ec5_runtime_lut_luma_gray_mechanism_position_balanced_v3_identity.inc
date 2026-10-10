#pragma once

namespace mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3 {

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
static constexpr uint8_t kSourceCode = 7;
static constexpr uint8_t kTargetCodes[2] = {3, 7};
static constexpr uint8_t kFactoryWhiteFrameFillByte = 0x11;
static constexpr uint8_t kPartialWindowCommand = 0x83;
static constexpr uint8_t kPartialWindowPayloadBytes = 9;
static constexpr uint8_t kPartialWindowMode = 0x01;
static constexpr bool kCs2VerticalMirror = false;
static constexpr bool kSeparateCsWindowCommands = true;
static constexpr bool kPtlwYEndOneMore = false;
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
    "L535_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3";
static constexpr char kBuildTag[] =
    "MF1750_EC5_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3_2026-09-01";
static constexpr char kTestId[] =
    "EC5-LUMA-GRAY-MECHANISM-POSITION-BALANCED-V3";
static constexpr char kCampaignId[] =
    "EC5_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3";
static constexpr char kContractId[] =
    "a114a46bec02b5de80c1f63757723e90cf8e101a81429a8f47eabadc471e3b88";
static constexpr char kNvsNamespace[] = "lgmpb_v3";
static constexpr char kNvsBootKey[] = "boot_lgmpb3";

// Dummy windows preserve inherited compile-time guards only.  Every V3 action
// streams one packed full frame and never issues PTLW/cropped DTM commands.
static constexpr Window kWindows[3] = {
    {68, 64, 120, 96, 7, 7},
    {196, 252, 120, 96, 7, 7},
    {324, 440, 120, 96, 7, 7},
};

// Indexed by White/Source/Mid/Target/ReverseSource.  White is an internal
// fixture only.  Target and ReverseSource have byte-identical frames but fresh
// action identities, making G4 an explicit optional repeat rather than a chain.
static constexpr ActionIdentity kActions[kRoleIdentityCount] = {
    {"INTERNAL_FACTORY_OTP_WHITE_FIXTURE", "LGMPB3_INTERNAL_WHITE_FIXTURE",
     "20cb164d908ec7a78c06945ce09865dcf0a9cd1febf8f30991d2c54c95dc1e86",
     "1c3a6165af977ab3be822be13055810a4966f599ff359c555b6a34f1e19fcfd3",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {"G1_ACTIVE_C7_SOURCE",
     "L535_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3_G1_ACTIVE_C7_SOURCE",
     "24b3f55d5026075fb21307bf4626e4a45e051ce5a5e23638ed8efb8ef5c6639f",
     "05aac5db9363a666f52144fe7c41eaacfc4f3860c41c7fa3af016baf1379b4b8",
     "f27255891c2b00350b2f7aca6f0719116c6a29262008b7621ef4b7df66b099f2",
     "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     0x7C918DC5UL, 0x285715C5UL, 0x285715C5UL,
     {0, 0, 0, 0, 0, 0, 0, 614400}},
    {"G2_COMMENTED_C0_TO_C7_POSITION_BALANCED_MIDDLE",
     "L535_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3_G2_COMMENTED_C0_TO_C7_POSITION_BALANCED_MIDDLE",
     "05d74bf882d2dcec84541ff528b1de2c6db43a8bec0931c758acf1f0963b9a22",
     "76d277a2d3833e6d208331b5eafea98eadb90ca90329fd4fca25864eb0de3866",
     "297b30361ab0afa88bc47f8b5acf3835974610fb39aee2efaba3b6d9e9b610bd",
     "1f7040ffa8c18d8b67cf1908bb161c21b8a21d1dd5d504f4dddf6d5ec7a0002a",
     "b1295d5b0a0865bd0ecdd3d1aaa2548de407b947e16f67d8ccfbd8d4bd82b2ec",
     0x510CAFC5UL, 0x63478BC5UL, 0x1C01EE45UL,
     {33280, 33280, 33280, 33280, 33280, 33280, 33280, 381440}},
    {"G3_ACTIVE_C3_C7_TARGET",
     "L535_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3_G3_ACTIVE_C3_C7_TARGET",
     "094f11ac566bf1f2d4fd0105ad52f1b463cb85605a41c1969b560dcb1982d775",
     "f6c6bb92ae708ac325c4bca53ed12d82f19f41fa84adb1ddd8c68e35c40b86ee",
     "82f40036c115b3dea4d00099ef915aa693007abf73e1ddcf4d436f72807e1a1c",
     "4e308b31900ba1e8d5d4c3a0a3a3d837771b45865a6eb5adb2b5c17f6cf5a428",
     "77e6c478da1b3f17950da85fac2759bca95fb80a6654fd3f83e2f3af719abcf1",
     0xDC41DAC5UL, 0xCF468BC5UL, 0xC06314C5UL,
     {0, 0, 0, 133120, 0, 0, 0, 481280}},
    {"G4_ACTIVE_C3_C7_IDENTICAL_TARGET_REPEAT_MANUAL_ONLY",
     "L535_LUMA_GRAY_MECHANISM_POSITION_BALANCED_V3_G4_ACTIVE_C3_C7_IDENTICAL_TARGET_REPEAT_MANUAL_ONLY",
     "6e76dfed0d2dc2f5c4dfbb82db5f44a918fdaacdf099e03e66b3fcfe8276d9f1",
     "a7d2d3390c6c0803eb5f4098592022c344f49c06141ca798f97fcb40ef1c3947",
     "82f40036c115b3dea4d00099ef915aa693007abf73e1ddcf4d436f72807e1a1c",
     "4e308b31900ba1e8d5d4c3a0a3a3d837771b45865a6eb5adb2b5c17f6cf5a428",
     "77e6c478da1b3f17950da85fac2759bca95fb80a6654fd3f83e2f3af719abcf1",
     0xDC41DAC5UL, 0xCF468BC5UL, 0xC06314C5UL,
     {0, 0, 0, 133120, 0, 0, 0, 481280}},
};

static_assert(kGridX1Exclusive <= 512 && kGridY1Exclusive <= 600 &&
                  (kGridX0 & 1U) == 0 && (kCellWidth & 1U) == 0 &&
                  (kGapX & 1U) == 0 && !kCs2VerticalMirror,
              "LUMA/GRAY mechanism V3 grid geometry changed");
static_assert(sizeof(kRecipeAtCellCs1) == 64 &&
                  sizeof(kRecipeAtCellCs2) == 64 &&
                  kRoleIdentityCount == 5,
              "LUMA/GRAY mechanism V3 identity cardinality changed");

}  // namespace mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3

