#pragma once

namespace mf1750_runtime_lut_cross_palette_v1 {

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
static constexpr uint8_t kActionCount = 5;
static constexpr uint8_t kWhiteCode = 7;
static constexpr uint8_t kPartialWindowCommand = 0x83;
static constexpr uint8_t kPartialWindowPayloadBytes = 9;
static constexpr uint8_t kPartialWindowMode = 0x01;
static constexpr bool kCs2VerticalMirror = false;
static constexpr bool kSeparateCsWindowCommands = true;
static constexpr bool kPtlwYEndOneMore = false;
static constexpr uint16_t kSourceRowHeight = 75;
static constexpr uint16_t kTargetColumnWidth = 64;
static constexpr char kActiveProfileId[] =
    "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";
static constexpr char kCommentedProfileId[] =
    "LEGACY_COMMENTED_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";

// Kept only to satisfy the shared compile-time geometry guard. Cross-palette
// builds never issue PTLW and never read these as transport windows.
static constexpr Window kWindows[3] = {
    {48, 64, 160, 120, 3, 3},
    {304, 240, 160, 120, 5, 5},
    {48, 416, 160, 120, 6, 6},
};

#define CROSS_COMMON_FRAME_IDENTITIES                                        \
  "f27255891c2b00350b2f7aca6f0719116c6a29262008b7621ef4b7df66b099f2", \
      "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd", \
      "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd", \
      0x7C918DC5UL, 0x285715C5UL, 0x285715C5UL,                         \
      {0, 0, 0, 0, 0, 0, 0, 614400}

#define CROSS_SOURCE_FRAME_IDENTITIES                                        \
  "06be3a9df65efdf86dc1552015daf16d6e2c59c06747a5291957c9c816d746e3", \
      "2dca869c3aa632a935dae5ac6128739ea1f20ccd40dc2fa624ff38a43e438727", \
      "2dca869c3aa632a935dae5ac6128739ea1f20ccd40dc2fa624ff38a43e438727", \
      0xDA9655C5UL, 0xCAE179C5UL, 0xCAE179C5UL,                         \
      {76800, 76800, 76800, 76800, 76800, 76800, 76800, 76800}

#define CROSS_TARGET_FRAME_IDENTITIES                                        \
  "c645344fa4daa0429d47626ca35e9be770e78684fac47f7bc9ebdb2fa10b85f8", \
      "d7f6b57a34ada52393719946c89d76934a5f802a8b95a0a8d8cf61d750df7196", \
      "d7f6b57a34ada52393719946c89d76934a5f802a8b95a0a8d8cf61d750df7196", \
      0xB52D15C5UL, 0x5FE4D9C5UL, 0x5FE4D9C5UL,                         \
      {76800, 76800, 76800, 76800, 76800, 76800, 76800, 76800}

namespace ab {
using mf1750_runtime_lut_cross_palette_v1::ActionIdentity;
using mf1750_runtime_lut_cross_palette_v1::Window;
using mf1750_runtime_lut_cross_palette_v1::kCs2VerticalMirror;
using mf1750_runtime_lut_cross_palette_v1::kPartialWindowCommand;
using mf1750_runtime_lut_cross_palette_v1::kPartialWindowMode;
using mf1750_runtime_lut_cross_palette_v1::kPartialWindowPayloadBytes;
using mf1750_runtime_lut_cross_palette_v1::kPtlwYEndOneMore;
using mf1750_runtime_lut_cross_palette_v1::kSeparateCsWindowCommands;
using mf1750_runtime_lut_cross_palette_v1::kWhiteCode;
using mf1750_runtime_lut_cross_palette_v1::kWindows;
static constexpr bool kDirectionAb = true;
static constexpr char kVariantKey[] = "L535_CROSS_PALETTE_8X8_AB_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_RUNTIME_LUT_CROSS_PALETTE_AB_V1_2026-08-23";
static constexpr char kTestId[] = "EC5-RUNTIME-LUT-CROSS-PALETTE-AB-V1";
static constexpr char kCampaignId[] =
    "EC5_RUNTIME_LUT_CROSS_PALETTE_AB_V1";
static constexpr char kContractId[] =
    "0f5e0c8906d1e5c022bdb9678992d7e1ccfc6f4300f5f5d1ba358db5dfa141ff";
static constexpr char kNvsNamespace[] = "rlx535ab_v1";
static constexpr char kProfileId[] =
    "LEGACY_ACTIVE_TO_COMMENTED_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";
static constexpr ActionIdentity kActions[kActionCount] = {
    {"RUNTIME_LUT_WHITE_BASELINE",
     "L535_CROSS_PALETTE_8X8_AB_V1_RUNTIME_LUT_WHITE_BASELINE_ACTIVE",
     "e4d021fa13d1b3c4564c7d9dbe64508a86f4874e71f1c3df0f2b6219a6359754",
     "1e2b9f14de2fb4a531688313e69ed4187df178a37b0e82697fa7a63e5cbd6eea",
     CROSS_COMMON_FRAME_IDENTITIES},
    {"CROSS_PALETTE_SOURCE_ROWS",
     "L535_CROSS_PALETTE_8X8_AB_V1_CROSS_PALETTE_SOURCE_ROWS_ACTIVE",
     "6590d124805051efebe63501058480ee66f9bb833ba649b7fa3777fa3da8d215",
     "a22ab86820a5bc329b6d4025f407fdb51073acda32a35b176f5a8b245e181f97",
     CROSS_SOURCE_FRAME_IDENTITIES},
    {"CROSS_PALETTE_TARGET_COLUMNS",
     "L535_CROSS_PALETTE_8X8_AB_V1_CROSS_PALETTE_TARGET_COLUMNS_COMMENTED",
     "5911ef86cf7f47d05407dd756bdd4e139fd5270d2fb0a17f8b8099eae0281322",
     "b90f137ce1cf3ea74f4ccdc75eae9668341ced3835ee17f30db5df283801f244",
     CROSS_TARGET_FRAME_IDENTITIES},
    {"CROSS_PALETTE_TARGET_REPEAT",
     "L535_CROSS_PALETTE_8X8_AB_V1_CROSS_PALETTE_TARGET_REPEAT_COMMENTED",
     "2a761f230f2a847f5b36ba16a44dc3acbf79d5d260d129281d752e16cec9448a",
     "63f153bf1decc2856e4ea7098304cbc4355f97c33b93d1db7b21351b63fb8f04",
     CROSS_TARGET_FRAME_IDENTITIES},
    {"RUNTIME_LUT_WHITE_RECOVERY",
     "L535_CROSS_PALETTE_8X8_AB_V1_RUNTIME_LUT_WHITE_RECOVERY_ACTIVE",
     "9b2ced912ac3ed5b6e821f2788a1973864b91341ab8702fd51b5d85468be1aa9",
     "06e75f77f37f5095d462ca959cccf7c438cca8ebe7afa13a437ca82918e7b5fa",
     CROSS_COMMON_FRAME_IDENTITIES},
};
}  // namespace ab

namespace ba {
using mf1750_runtime_lut_cross_palette_v1::ActionIdentity;
using mf1750_runtime_lut_cross_palette_v1::Window;
using mf1750_runtime_lut_cross_palette_v1::kCs2VerticalMirror;
using mf1750_runtime_lut_cross_palette_v1::kPartialWindowCommand;
using mf1750_runtime_lut_cross_palette_v1::kPartialWindowMode;
using mf1750_runtime_lut_cross_palette_v1::kPartialWindowPayloadBytes;
using mf1750_runtime_lut_cross_palette_v1::kPtlwYEndOneMore;
using mf1750_runtime_lut_cross_palette_v1::kSeparateCsWindowCommands;
using mf1750_runtime_lut_cross_palette_v1::kWhiteCode;
using mf1750_runtime_lut_cross_palette_v1::kWindows;
static constexpr bool kDirectionAb = false;
static constexpr char kVariantKey[] = "L535_CROSS_PALETTE_8X8_BA_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_RUNTIME_LUT_CROSS_PALETTE_BA_V1_2026-08-23";
static constexpr char kTestId[] = "EC5-RUNTIME-LUT-CROSS-PALETTE-BA-V1";
static constexpr char kCampaignId[] =
    "EC5_RUNTIME_LUT_CROSS_PALETTE_BA_V1";
static constexpr char kContractId[] =
    "4a7716184fe3e01ea8d65b4558899d17a4dd6b3e36795575039d997636d3b9cf";
static constexpr char kNvsNamespace[] = "rlx535ba_v1";
static constexpr char kProfileId[] =
    "LEGACY_COMMENTED_TO_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";
static constexpr ActionIdentity kActions[kActionCount] = {
    {"RUNTIME_LUT_WHITE_BASELINE",
     "L535_CROSS_PALETTE_8X8_BA_V1_RUNTIME_LUT_WHITE_BASELINE_ACTIVE",
     "eaf32346561363ffd60a2939cf39821987d981bf652e2dcca68b06b3428ab127",
     "86942710bcadb4c1a589483e8ab78af1d8fe53cd537508cd1bba147fc2184fd3",
     CROSS_COMMON_FRAME_IDENTITIES},
    {"CROSS_PALETTE_SOURCE_ROWS",
     "L535_CROSS_PALETTE_8X8_BA_V1_CROSS_PALETTE_SOURCE_ROWS_COMMENTED",
     "8280fd1df648b53cb7480066945f0a79c2d63b06aab82c801fab36cd37b98109",
     "debc98dda40a7a319aee73df6b718e30d59b7ddfac6f1c0c503c9e762776765c",
     CROSS_SOURCE_FRAME_IDENTITIES},
    {"CROSS_PALETTE_TARGET_COLUMNS",
     "L535_CROSS_PALETTE_8X8_BA_V1_CROSS_PALETTE_TARGET_COLUMNS_ACTIVE",
     "88a13f7e843f8440e56b42a6d19031ff7cfa4830d1c7c779f596d766416b132d",
     "ca6bb01b1d776fbf10d704bf2f481bc18e146e089f98a05dbb8016f0dacde29f",
     CROSS_TARGET_FRAME_IDENTITIES},
    {"CROSS_PALETTE_TARGET_REPEAT",
     "L535_CROSS_PALETTE_8X8_BA_V1_CROSS_PALETTE_TARGET_REPEAT_ACTIVE",
     "f34f0cd431acc2ec5d29ceabcea206d2eff3320ddccb29476dc7f73ff863ab06",
     "bb58fa6281e77e36b97046124b4162aa92bdbaf6892650a0bfe39e82ee92c8a1",
     CROSS_TARGET_FRAME_IDENTITIES},
    {"RUNTIME_LUT_WHITE_RECOVERY",
     "L535_CROSS_PALETTE_8X8_BA_V1_RUNTIME_LUT_WHITE_RECOVERY_ACTIVE",
     "bfef30ecd5a0d1f3685240265eaf7d28032e319a317af665e51e4037ed911490",
     "0510cde93bd1a77db4554e9bb558543847cd32e5e3cee6933992f9808a5895d2",
     CROSS_COMMON_FRAME_IDENTITIES},
};
}  // namespace ba

#undef CROSS_COMMON_FRAME_IDENTITIES
#undef CROSS_SOURCE_FRAME_IDENTITIES
#undef CROSS_TARGET_FRAME_IDENTITIES

static_assert(sizeof(ab::kActions) / sizeof(ab::kActions[0]) == kActionCount,
              "cross-palette AB requires five actions");
static_assert(sizeof(ba::kActions) / sizeof(ba::kActions[0]) == kActionCount,
              "cross-palette BA requires five actions");

}  // namespace mf1750_runtime_lut_cross_palette_v1
