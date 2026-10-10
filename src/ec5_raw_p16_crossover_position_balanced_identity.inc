#pragma once

#if (defined(MF1750_RAW_P16_CROSSOVER_T1_AC_BUILD) + \
     defined(MF1750_RAW_P16_CROSSOVER_T2_CA_BUILD) + \
     defined(MF1750_RAW_P16_CROSSOVER_T3_AC_REPEAT_BUILD)) != 1
#error "RAW-P16 crossover build must select exactly one fresh stage"
#endif

namespace mf1750_raw_p16_crossover_position_balanced {

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
    {6, 7, 0, 1, 2, 3, 4, 5},
    {5, 4, 7, 6, 1, 0, 3, 2},
    {3, 2, 5, 4, 7, 6, 1, 0},
};
static constexpr uint16_t kCellWidth = 52;
static constexpr uint16_t kCellHeight = 100;
static constexpr uint16_t kGapX = 8;
static constexpr uint16_t kGapY = 36;
static constexpr uint16_t kGridX1Exclusive = 492;
static constexpr uint16_t kGridY1Exclusive = 552;
static constexpr char kActiveR20Sha256[] =
    "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b";
static constexpr char kCommentedR20Sha256[] =
    "2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26";
static constexpr char kClassification[] =
    "EXPERIMENTAL_POSITION_BALANCED_CROSSOVER_R20_ENDPOINT_COMPARISON_"
    "NOT_ABSOLUTE_COLOUR_QUALIFICATION";
static constexpr char kDeviceApiVersion[] =
    "MF1750_EC5_RAW_P16_CROSSOVER_POSBAL_DEVICE_V1";
static constexpr char kIdentityRevision[] =
    "raw-p16-crossover-position-balanced-v1";
static constexpr char kProfileSource[] =
    "legacy_complete_535_cross_controller_tuple";
static constexpr char kBaselineRole[] =
    "EXTERNAL_FACTORY_OTP_WHITE_BEFORE_AND_AFTER_REQUIRED";
static constexpr char kArmIntent[] =
    "ARM_ONE_FIXED_RAW_P16_CROSSOVER_POSITION_BALANCED_ACTION_"
    "NOT_HARDWARE_AUTHORIZATION";
static constexpr char kExecuteIntent[] =
    "EXECUTE_ONE_ARMED_RAW_P16_CROSSOVER_POSITION_BALANCED_ACTION_ONCE";

// Full-frame only. This inherited driver type is never emitted as PTLW.
static constexpr Window kWindows[1] = {{20, 44, 52, 100, 0, 0}};

#if defined(MF1750_RAW_P16_CROSSOVER_T1_AC_BUILD)
static constexpr bool kGlobalUseCommented = false;
static constexpr bool kCs1UseCommented = false;
static constexpr bool kCs2UseCommented = true;
static constexpr char kVariantKey[] =
    "L535_RAW_P16_CROSSOVER_POSITION_BALANCED_T1_AC_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_RAW_P16_CROSSOVER_POSBAL_T1_AC_V1_2026-08-30";
static constexpr char kTestId[] =
    "EC5-RAW-P16-CROSSOVER-POSBAL-T1-AC-V1";
static constexpr char kCampaignId[] =
    "EC5_RAW_P16_CROSSOVER_POSBAL_T1_AC_V1";
static constexpr char kContractId[] =
    "6ea93bbd9be1d75e12bc6656614ac335faeb97aa1079ff04733b8babe7a247d7";
static constexpr char kNvsNamespace[] = "p16x_t1ac_v1";
static constexpr char kNvsKey[] = "cur_t1ac";
static constexpr char kNvsBootKey[] = "boot_t1ac";
static constexpr char kBootLabel[] = "EC5 RAW-P16 crossover T1 AC";
static constexpr char kApiKindPrefix[] =
    "mf1750-ec5-raw-p16-crossover-posbal-t1-ac-v1";
static constexpr char kBaseRoute[] =
    "/api/ec5/raw-p16-crossover-posbal-t1-ac-v1";
static constexpr char kRole[] =
    "RAW_P16_CROSSOVER_POSITION_BALANCED_T1_AC_ATLAS";
static constexpr char kBranch[] =
    "L535_RAW_P16_CROSSOVER_POSITION_BALANCED_T1_AC_V1_"
    "RAW_P16_CROSSOVER_POSITION_BALANCED_T1_AC_ATLAS";
static constexpr char kDescriptorId[] =
    "8daa4e2c47213f2815ad72c7908c288d1091c76d6eafa311851f8e56ecb1bd1b";
static constexpr char kActionId[] =
    "73ff6d58686acdd88929b9c0d9e983818c75abb7ad7f1ccebf34219dd82a7c72";
static constexpr char kProfileId[] =
    "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";
static constexpr char kGlobalHeader[] = "active";
static constexpr char kGlobalTupleId[] =
    "3b5252e50f7d5194f4a772c03e440638c06cb2db42891bec2d5d50ffcde8207b";
static constexpr uint8_t kRound = 1;
#elif defined(MF1750_RAW_P16_CROSSOVER_T2_CA_BUILD)
static constexpr bool kGlobalUseCommented = true;
static constexpr bool kCs1UseCommented = true;
static constexpr bool kCs2UseCommented = false;
static constexpr char kVariantKey[] =
    "L535_RAW_P16_CROSSOVER_POSITION_BALANCED_T2_CA_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_RAW_P16_CROSSOVER_POSBAL_T2_CA_V1_2026-08-30";
static constexpr char kTestId[] =
    "EC5-RAW-P16-CROSSOVER-POSBAL-T2-CA-V1";
static constexpr char kCampaignId[] =
    "EC5_RAW_P16_CROSSOVER_POSBAL_T2_CA_V1";
static constexpr char kContractId[] =
    "ddcde0da8f5fec1b73924131a9a3e92fbee632430a041a72c56eea8a32b9d3cf";
static constexpr char kNvsNamespace[] = "p16x_t2ca_v1";
static constexpr char kNvsKey[] = "cur_t2ca";
static constexpr char kNvsBootKey[] = "boot_t2ca";
static constexpr char kBootLabel[] = "EC5 RAW-P16 crossover T2 CA";
static constexpr char kApiKindPrefix[] =
    "mf1750-ec5-raw-p16-crossover-posbal-t2-ca-v1";
static constexpr char kBaseRoute[] =
    "/api/ec5/raw-p16-crossover-posbal-t2-ca-v1";
static constexpr char kRole[] =
    "RAW_P16_CROSSOVER_POSITION_BALANCED_T2_CA_ATLAS";
static constexpr char kBranch[] =
    "L535_RAW_P16_CROSSOVER_POSITION_BALANCED_T2_CA_V1_"
    "RAW_P16_CROSSOVER_POSITION_BALANCED_T2_CA_ATLAS";
static constexpr char kDescriptorId[] =
    "5945f3c49f3da63b676f263ff1fc746eb750b294d065831bdb2113384bbb7f1c";
static constexpr char kActionId[] =
    "d38f77df0f02d1eb65641d2b8836bce46db2b563b75d711d86b2da1ebe989470";
static constexpr char kProfileId[] =
    "LEGACY_COMMENTED_HEADER__CS1_COMMENTED535__CS2_ACTIVE535";
static constexpr char kGlobalHeader[] = "commented";
static constexpr char kGlobalTupleId[] =
    "f88f007f11acab3aeec216ef9b0c30b794b5fcbb121ed859e629c488232471ed";
static constexpr uint8_t kRound = 2;
#else
static constexpr bool kGlobalUseCommented = false;
static constexpr bool kCs1UseCommented = false;
static constexpr bool kCs2UseCommented = true;
static constexpr char kVariantKey[] =
    "L535_RAW_P16_CROSSOVER_POSITION_BALANCED_T3_AC_REPEAT_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_RAW_P16_CROSSOVER_POSBAL_T3_AC_REPEAT_V1_2026-08-30";
static constexpr char kTestId[] =
    "EC5-RAW-P16-CROSSOVER-POSBAL-T3-AC-REPEAT-V1";
static constexpr char kCampaignId[] =
    "EC5_RAW_P16_CROSSOVER_POSBAL_T3_AC_REPEAT_V1";
static constexpr char kContractId[] =
    "60f27623af8527f240173e457060ba008e61083f985e2b4a6ad4914a1f3705a0";
static constexpr char kNvsNamespace[] = "p16x_t3ar_v1";
static constexpr char kNvsKey[] = "cur_t3ar";
static constexpr char kNvsBootKey[] = "boot_t3ar";
static constexpr char kBootLabel[] = "EC5 RAW-P16 crossover T3 AC repeat";
static constexpr char kApiKindPrefix[] =
    "mf1750-ec5-raw-p16-crossover-posbal-t3-ac-repeat-v1";
static constexpr char kBaseRoute[] =
    "/api/ec5/raw-p16-crossover-posbal-t3-ac-repeat-v1";
static constexpr char kRole[] =
    "RAW_P16_CROSSOVER_POSITION_BALANCED_T3_AC_REPEAT_ATLAS";
static constexpr char kBranch[] =
    "L535_RAW_P16_CROSSOVER_POSITION_BALANCED_T3_AC_REPEAT_V1_"
    "RAW_P16_CROSSOVER_POSITION_BALANCED_T3_AC_REPEAT_ATLAS";
static constexpr char kDescriptorId[] =
    "8ac6a7f14364966d0b1b9e447eb0ce4e1f39eb29d57ec5ce25b6a2c835cfb2ed";
static constexpr char kActionId[] =
    "4a7c3d2816aca50e124049e048c7d7dbeec32a8c7bb825b9cd5294fdd23f144a";
static constexpr char kProfileId[] =
    "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";
static constexpr char kGlobalHeader[] = "active";
static constexpr char kGlobalTupleId[] =
    "3b5252e50f7d5194f4a772c03e440638c06cb2db42891bec2d5d50ffcde8207b";
static constexpr uint8_t kRound = 3;
#endif

static constexpr char kFrameSha256[] =
    "1ff9588f4f7d00d7e9dd0a89d2c4fb08c25db7e6e044ee467af6187b3270ad23";
static constexpr char kDtmSha256[] =
    "2edcd090619b3a690b1d23db70df9b7648bad40b0512887df8a380a6f53fd1cb";
static constexpr uint32_t kFrameFnv1a = 0x7F8C2EC5UL;
static constexpr uint32_t kDtmFnv1a = 0x8BA37FC5UL;

static constexpr ActionIdentity kActions[kRoleIdentityCount] = {{
    kRole,
    kBranch,
    kDescriptorId,
    kActionId,
    kFrameSha256,
    kDtmSha256,
    kDtmSha256,
    kFrameFnv1a,
    kDtmFnv1a,
    kDtmFnv1a,
    {41600, 41600, 41600, 41600, 41600, 41600, 41600, 323200},
}};

static_assert(kGridRows == 4 && kGridColumns == 8,
              "position-balanced atlas geometry changed");
static_assert(kGridX1Exclusive <= 512 && kGridY1Exclusive <= 600 &&
                  (kGridX0 & 1U) == 0 && (kCellWidth & 1U) == 0 &&
                  (kGapX & 1U) == 0 && !kCs2VerticalMirror,
              "position-balanced packed-grid geometry changed");
static_assert(kCs1UseCommented != kCs2UseCommented,
              "crossover requires opposite controller R20 profiles");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kRoleIdentityCount,
              "position-balanced role identity changed");

}  // namespace mf1750_raw_p16_crossover_position_balanced

namespace mf1750_raw_p16_crossover_position_balanced_current =
    mf1750_raw_p16_crossover_position_balanced;
