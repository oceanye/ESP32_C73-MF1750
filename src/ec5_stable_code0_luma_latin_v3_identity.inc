#pragma once

namespace mf1750_stable_code0_luma_latin_v3 {

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
static constexpr uint8_t kSourceCode = 7;
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
    "ACTIVE_CODE0_CS2_RED_FAMILY_PRIMARY_CS1_CONTROLLER_SPECIFIC_"
    "INTERNAL_CONTROL_UNCALIBRATED";
static constexpr char kVariantKey[] = "STABLE_CODE0_LUMA_LATIN_V3";
static constexpr char kBuildTag[] =
    "MF1750_EC5_STABLE_CODE0_LUMA_LATIN_V3_2026-09-01";
static constexpr char kTestId[] = "EC5-STABLE-CODE0-LUMA-LATIN-V3";
static constexpr char kCampaignId[] = "EC5_STABLE_CODE0_LUMA_LATIN_V3";
static constexpr char kContractId[] =
    "472cb28efa39538963cc94da3d8442f2a0e35603fdd41f38eb973bcb600f8302";
static constexpr char kNvsNamespace[] = "scllat_v3";
static constexpr char kNvsBootKey[] = "boot_scl3";

// L4 is a distinct host action with an identical L3 target payload.  These
// markers are referenced by main_config so the final binary carries the L4
// identity even though the driver role table intentionally reuses Target.
static constexpr char kL4DescriptorId[] =
    "d5210a30fcc40fab1265490c24661f011d98f6f76e81a84fd105f54f21e653dd";
static constexpr char kL4ActionId[] =
    "9ea8538c301c53651ee0270c884caf34ce8d5592ba7ee3e6d4ba2f5a0e7420ec";
static constexpr char kL4PriorActionId[] =
    "185d103527cebf9bd36153ca9d0ba4eb6152c57d39dbf177ecd5a24d6309d4a5";
static constexpr char kL4FrameSha256[] =
    "9c771f6a89f72bdd64c38ddd99489accad9c5ed554d1841740517ea1100f7af4";
static constexpr char kL4Cs1DtmSha256[] =
    "f36eeda01f7cdd5cda9147cece0a543009a217235c38b1ab3f636f24b2e4f4aa";
static constexpr char kL4Cs2DtmSha256[] =
    "f36eeda01f7cdd5cda9147cece0a543009a217235c38b1ab3f636f24b2e4f4aa";
static constexpr uint32_t kL4FrameFnv1a = 0x2CC36BC5UL;
static constexpr uint32_t kL4Cs1DtmFnv1a = 0x4FA004C5UL;
static constexpr uint32_t kL4Cs2DtmFnv1a = 0x4FA004C5UL;
static constexpr char kL4EffectiveProfile[] =
    "ACTIVE_GLOBAL__CS1_ACTIVE535__CS2_COMMENTED535";

// Valid dummy windows satisfy the inherited geometry guard.  This campaign
// streams full frames only and never issues PTLW/0x83.
static constexpr Window kWindows[3] = {
    {48, 64, 160, 120, 7, 7},
    {304, 240, 160, 120, 0, 0},
    {48, 416, 160, 120, 0, 0},
};

// Indexed by White/Source/Mid/Target.  White is a fixture-only self-check and
// is not exposed as an action in this four-action main campaign.  L4 retains a
// distinct action identity in main_config while reusing the Target payload.
static constexpr ActionIdentity kActions[kRoleIdentityCount] = {
    {"FACTORY_OTP_WHITE_FIXTURE_ONLY_NOT_MAIN_ACTION",
     "STABLE_CODE0_LUMA_LATIN_V3_FACTORY_OTP_WHITE_FIXTURE_ONLY",
     "0000000000000000000000000000000000000000000000000000000000000000",
     "0000000000000000000000000000000000000000000000000000000000000000",
     "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
     0x13340DC5UL,
     0xB7A855C5UL,
     0xB7A855C5UL,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {"L1_FIXED_ACTIVE_SOURCE_CODE7",
     "STABLE_CODE0_LUMA_LATIN_V3_L1_FIXED_ACTIVE_SOURCE_CODE7",
     "6056c7ba401c3abe2ff022a126c6a54cfec9d8594dc5e8faee8785c9b5556eee",
     "83b0e955ff0d88076737e8e13946602c696829bcef159691ce4ef074abfaf62e",
     "f27255891c2b00350b2f7aca6f0719116c6a29262008b7621ef4b7df66b099f2",
     "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     0x7C918DC5UL,
     0x285715C5UL,
     0x285715C5UL,
     {0, 0, 0, 0, 0, 0, 0, 614400}},
    {"L2_COMMENTED_MIDDLE_LATIN_C0_C7",
     "STABLE_CODE0_LUMA_LATIN_V3_L2_COMMENTED_MIDDLE_LATIN_C0_C7",
     "61c5c9ebc88279e1015106e06b9702a725c0ebaa09af3a802f2939bd30b15615",
     "c7606fc0d16eed0e7dc9d211441da551579a168d85bcba336c32e724396c2ad8",
     "03265f52002f241e4681631d5efd2686045a533c3a8ab8977bcd2bbd01961416",
     "890ea1f455e80bfe262ae53f6741409d1737603ff5a642f1d58f241ab258e1f3",
     "b28a0b79555000bed6c9a991e0ca3e8317661e38adaf7cb1293b9f3b5510c253",
     0x41A370C5UL,
     0x02229BC5UL,
     0xA4741A45UL,
     {48256, 48256, 48256, 48256, 48256, 48256, 48256, 276608}},
    {"L3_FIXED_ACTIVE_TARGET_CODE0",
     "STABLE_CODE0_LUMA_LATIN_V3_L3_FIXED_ACTIVE_TARGET_CODE0",
     "371a59e807fde7515027870c69707a5aaa29997925c571d3176b65d8ec3a2cd2",
     "185d103527cebf9bd36153ca9d0ba4eb6152c57d39dbf177ecd5a24d6309d4a5",
     "9c771f6a89f72bdd64c38ddd99489accad9c5ed554d1841740517ea1100f7af4",
     "f36eeda01f7cdd5cda9147cece0a543009a217235c38b1ab3f636f24b2e4f4aa",
     "f36eeda01f7cdd5cda9147cece0a543009a217235c38b1ab3f636f24b2e4f4aa",
     0x2CC36BC5UL,
     0x4FA004C5UL,
     0x4FA004C5UL,
     {386048, 0, 0, 0, 0, 0, 0, 228352}},
};

static_assert(kGridRows == 8 && kGridColumns == 8 && kSourceCode == 7 &&
                  kTargetCode == 0,
              "stable-code0 Latin recipe changed");
static_assert(kSeparatorCode == 7 && kFactoryWhiteFrameFillByte == 0x11,
              "separator/factory-white fixture identities changed");
static_assert(kGridX1Exclusive <= 512 && kGridY1Exclusive <= 600 &&
                  (kGridX0 & 1U) == 0 && (kCellWidth & 1U) == 0 &&
                  (kGapX & 1U) == 0 && !kCs2VerticalMirror,
              "stable-code0 packed-grid geometry changed");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kRoleIdentityCount,
              "stable-code0 role identities changed");

}  // namespace mf1750_stable_code0_luma_latin_v3
