#pragma once

#if !defined(MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2_BUILD)
#error "T3 AC profile-following successor V2 requires its isolated build macro"
#endif

namespace mf1750_raw_p16_crossover_t2_discovery_successor {

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
    "EXPERIMENTAL_HUMAN_PRIMARY_PROFILE_FOLLOWING_REVIEW_ONLY_T3_AC_SWAP_"
    "SUCCESSOR_V2_AFTER_FAILED_UNMUTATED_V1_NOT_FORMAL_GATE_NOT_COLOUR_"
    "QUALIFICATION_ZERO_QUALIFIED_COLOURS";
static constexpr char kDeviceApiVersion[] =
    "MF1750_EC5_RAW_P16_CROSSOVER_T3_PROFILE_FOLLOWING_DEVICE_V2";
static constexpr char kIdentityRevision[] =
    "raw-p16-crossover-t3-ac-profile-following-successor-v2";
static constexpr char kProfileSource[] =
    "legacy_complete_535_cross_controller_tuple";
static constexpr char kBaselineRole[] =
    "EXTERNAL_FACTORY_OTP_WHITE_BEFORE_AND_AFTER_REQUIRED";
static constexpr char kArmIntent[] =
    "ARM_ONE_FIXED_RAW_P16_T3_AC_PROFILE_FOLLOWING_REVIEW_V2_ACTION_"
    "NOT_HARDWARE_AUTHORIZATION";
static constexpr char kExecuteIntent[] =
    "EXECUTE_ONE_ARMED_RAW_P16_T3_AC_PROFILE_FOLLOWING_REVIEW_V2_ACTION_ONCE";

// Full-frame only. The inherited driver never emits this as a PTLW window.
static constexpr Window kWindows[1] = {{20, 44, 52, 100, 0, 0}};

// Preserve the reviewed V1 atlas/profile bytes; only campaign identity is fresh.
static constexpr bool kGlobalUseCommented = false;
static constexpr bool kCs1UseCommented = false;
static constexpr bool kCs2UseCommented = true;
static constexpr char kVariantKey[] =
    "L535_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2";
static constexpr char kBuildTag[] =
    "MF1750_EC5_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2_2026-08-31";
static constexpr char kTestId[] =
    "EC5-RAW-P16-CROSSOVER-T3-AC-PROFILE-FOLLOWING-SUCCESSOR-V2";
static constexpr char kCampaignId[] =
    "EC5_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2";
static constexpr char kContractId[] =
    "cc33b55a64fc2d54884f9c6ca65e117d6767fab0f0c60c3e5f55fac3554e5729";
static constexpr char kNvsNamespace[] = "p16t3pf_v2";
static constexpr char kNvsKey[] = "cur_t3pf2";
static constexpr char kNvsBootKey[] = "boot_t3pf2";
static constexpr char kBootLabel[] =
    "EC5 RAW-P16 T3 AC profile-following review successor V2";
static constexpr char kApiKindPrefix[] =
    "mf1750-ec5-raw-p16-crossover-t3-ac-profile-following-successor-v2";
static constexpr char kBaseRoute[] =
    "/api/ec5/raw-p16-crossover-t3-ac-profile-following-successor-v2";
static constexpr char kRole[] =
    "RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_REVIEW_V2_ATLAS";
static constexpr char kBranch[] =
    "L535_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2_"
    "RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_REVIEW_V2_ATLAS";
static constexpr char kDescriptorId[] =
    "c2e40c4c59cf6cca3f6ff4fd8c568a5ddee59e8c2100a9cf5d50c007317a148a";
static constexpr char kActionId[] =
    "73f6e97b49b5bd8c46edbba9edffde99967dcb170be6150082dc7c68100fada5";
// V1 never executed; the last completed atlas action remains the T2 V2 action.
static constexpr char kPriorActionId[] =
    "c184e610cc2ac464ca152eb1af7a0a9f746e5d92c38da53b673de9c0dcdcfd1f";
static constexpr char kProfileId[] =
    "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";
static constexpr char kGlobalHeader[] = "active";
static constexpr char kGlobalTupleId[] =
    "3b5252e50f7d5194f4a772c03e440638c06cb2db42891bec2d5d50ffcde8207b";
static constexpr uint8_t kRound = 3;

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

}  // namespace mf1750_raw_p16_crossover_t2_discovery_successor
