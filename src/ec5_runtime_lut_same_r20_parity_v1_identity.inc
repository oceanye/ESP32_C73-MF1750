#pragma once

namespace mf1750_runtime_lut_same_r20_parity_v1 {

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

static constexpr uint8_t kRoleCount = 3;
static constexpr uint8_t kRoleIdentityCount = 3;
static constexpr uint8_t kSeparatorCode = 7;
static constexpr uint8_t kTargetCode = 0;
static constexpr uint8_t kFactoryWhiteFrameFillByte = 0x11;
static constexpr uint8_t kPartialWindowCommand = 0x83;
static constexpr uint8_t kPartialWindowPayloadBytes = 9;
static constexpr uint8_t kPartialWindowMode = 0x01;
static constexpr bool kCs2VerticalMirror = false;
static constexpr bool kSeparateCsWindowCommands = true;
static constexpr bool kPtlwYEndOneMore = false;
static constexpr uint8_t kGridRows = 2;
static constexpr uint8_t kGridColumns = 4;
static constexpr uint16_t kGridX0 = 40;
static constexpr uint16_t kGridY0 = 120;
static constexpr uint16_t kCellWidth = 96;
static constexpr uint16_t kCellHeight = 120;
static constexpr uint16_t kGapX = 20;
static constexpr uint16_t kGapY = 40;
static constexpr uint16_t kGridX1Exclusive = 484;
static constexpr uint16_t kGridY1Exclusive = 400;
static constexpr char kActiveProfileId[] =
    "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_ACTIVE535";
static constexpr char kCommentedProfileId[] =
    "LEGACY_COMMENTED_HEADER__CS1_COMMENTED535__CS2_COMMENTED535";
static constexpr char kVariantKey[] =
    "L535_SAME_R20_DUAL_CONTROLLER_PARITY_2X4_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_SAME_R20_PARITY_2X4_V1_2026-08-28";
static constexpr char kTestId[] = "EC5-SAME-R20-PARITY-2X4-V1";
static constexpr char kCampaignId[] = "EC5_SAME_R20_PARITY_2X4_V1";
static constexpr char kContractId[] =
    "718d6cf628cd14a869b73f77f6414fcdd8a5b364863849899403afde2f3463f8";
static constexpr char kNvsNamespace[] = "sr20p_v1";
static constexpr char kNvsBootKey[] = "boot_srp1";

// Full-frame only. Dummy windows satisfy inherited geometry guards and are
// never emitted as PTLW commands by this campaign.
static constexpr Window kWindows[3] = {
    {48, 64, 160, 120, 0, 0},
    {304, 240, 160, 120, 5, 5},
    {48, 416, 160, 120, 6, 6},
};

// Indexed by White/Source/Mid. Both white ordinals reuse White; AA/CC share
// one identical DTM while selecting different symmetric tuples.
static constexpr ActionIdentity kActions[kRoleIdentityCount] = {
    {"FACTORY_OTP_WHITE",
     "L535_SAME_R20_DUAL_CONTROLLER_PARITY_2X4_V1_FACTORY_OTP_WHITE",
     "becf21026a58d964c576698dd007904c600b1a5f46a3d02d241d83b7583da7b3",
     "f4d447808e151be7860e3a59afe41e5030072fabdb51a566c83c83a642318816",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL,
     0xB7A855C5UL,
     0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {"SAME_R20_ACTIVE_ACTIVE_ATLAS",
     "L535_SAME_R20_DUAL_CONTROLLER_PARITY_2X4_V1_SAME_R20_ACTIVE_ACTIVE_ATLAS",
     "246de22c2a8f450752a960230bd88de7a62ce42300c7f6401bbb562d07ef76ba",
     "7dd101c61553c9a10b97beeb7c3c8ce26e79c410d3b2ac3040db572065fd49f4",
     "79182e188e32cd320cdaec36dee4410d06d603b1a155c8328bb63cfbdfbab2d6",
     "f85f377c573d9747821c0264ec3b59e488cd99732c566e54b3454486813682da",
     "f85f377c573d9747821c0264ec3b59e488cd99732c566e54b3454486813682da",
     0x93B39DC5UL,
     0xA1E81DC5UL,
     0xA1E81DC5UL,
     {23040, 23040, 23040, 23040, 23040, 23040, 23040, 453120}},
    {"SAME_R20_COMMENTED_COMMENTED_ATLAS",
     "L535_SAME_R20_DUAL_CONTROLLER_PARITY_2X4_V1_SAME_R20_COMMENTED_COMMENTED_ATLAS",
     "556b730c7c115dc956f7b547064df0145ccfdfc55cd2bf8dd7e170718cbb2af2",
     "e62b7b784ddd4108f18606d9b34b0341c41bc82225576fa4ae0849117de2b381",
     "79182e188e32cd320cdaec36dee4410d06d603b1a155c8328bb63cfbdfbab2d6",
     "f85f377c573d9747821c0264ec3b59e488cd99732c566e54b3454486813682da",
     "f85f377c573d9747821c0264ec3b59e488cd99732c566e54b3454486813682da",
     0x93B39DC5UL,
     0xA1E81DC5UL,
     0xA1E81DC5UL,
     {23040, 23040, 23040, 23040, 23040, 23040, 23040, 453120}},
};

static_assert(kGridRows == 2 && kGridColumns == 4,
              "same-R20 atlas geometry changed");
static_assert(kSeparatorCode == 7 && kFactoryWhiteFrameFillByte == 0x11,
              "separator/factory-white identities changed");
static_assert(kGridX1Exclusive <= 512 && kGridY1Exclusive <= 600 &&
                  (kGridX0 & 1U) == 0 && (kCellWidth & 1U) == 0 &&
                  (kGapX & 1U) == 0 && !kCs2VerticalMirror,
              "same-R20 packed-grid geometry changed");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kRoleIdentityCount,
              "same-R20 role identities changed");

}  // namespace mf1750_runtime_lut_same_r20_parity_v1
