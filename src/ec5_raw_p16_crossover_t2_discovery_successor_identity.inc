#pragma once

#if defined(MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V5_BUILD)
#include "ec5_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v5_identity.inc"
#elif defined(MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V4_BUILD)
#include "ec5_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v4_identity.inc"
#elif defined(MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V3_BUILD)
#include "ec5_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v3_identity.inc"
#elif defined(MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V2_BUILD)
#include "ec5_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v2_identity.inc"
#elif defined(MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_V1_BUILD)
#include "ec5_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_v1_identity.inc"
#elif defined(MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2_BUILD)
#include "ec5_raw_p16_crossover_t3_ac_profile_following_successor_v2_identity.inc"
#elif defined(MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_BUILD)
#include "ec5_raw_p16_crossover_t3_ac_profile_following_successor_identity.inc"
#elif defined(MF1750_RAW_P16_CROSSOVER_T2_DISCOVERY_SUCCESSOR_V2_BUILD)
#include "ec5_raw_p16_crossover_t2_discovery_successor_v2_identity.inc"
#else

#if !defined(MF1750_RAW_P16_CROSSOVER_T2_DISCOVERY_SUCCESSOR_BUILD)
#error "T2 coarse-discovery identity requires its isolated build macro"
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
    "EXPERIMENTAL_COARSE_DISCOVERY_ONLY_T2_CA_PROFILE_SWAP_"
    "NOT_FORMAL_GATE_NOT_COLOUR_QUALIFICATION_ZERO_QUALIFIED_COLOURS";
static constexpr char kDeviceApiVersion[] =
    "MF1750_EC5_RAW_P16_CROSSOVER_T2_DISCOVERY_DEVICE_V1";
static constexpr char kIdentityRevision[] =
    "raw-p16-crossover-t2-ca-coarse-discovery-successor-v1";
static constexpr char kProfileSource[] =
    "legacy_complete_535_cross_controller_tuple";
static constexpr char kBaselineRole[] =
    "EXTERNAL_FACTORY_OTP_WHITE_BEFORE_AND_AFTER_REQUIRED";
static constexpr char kArmIntent[] =
    "ARM_ONE_FIXED_RAW_P16_T2_CA_COARSE_DISCOVERY_ACTION_"
    "NOT_HARDWARE_AUTHORIZATION";
static constexpr char kExecuteIntent[] =
    "EXECUTE_ONE_ARMED_RAW_P16_T2_CA_COARSE_DISCOVERY_ACTION_ONCE";

// Full-frame only. The inherited driver never emits this as a PTLW window.
static constexpr Window kWindows[1] = {{20, 44, 52, 100, 0, 0}};

// Exact reviewed T2-CA tuple: commented global header, commented CS1 R20,
// active CS2 R20. Only the campaign identity and screening boundary are new.
static constexpr bool kGlobalUseCommented = true;
static constexpr bool kCs1UseCommented = true;
static constexpr bool kCs2UseCommented = false;
static constexpr char kVariantKey[] =
    "L535_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_"
    "SUCCESSOR_V1_2026-08-30";
static constexpr char kTestId[] =
    "EC5-RAW-P16-CROSSOVER-T2-CA-COARSE-DISCOVERY-SUCCESSOR-V1";
static constexpr char kCampaignId[] =
    "EC5_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_V1";
static constexpr char kContractId[] =
    "464481375c0ec26034c235fcebd7091bff20f6c32b29c7cc86a9f41afbf69398";
static constexpr char kNvsNamespace[] = "p16t2d_v1";
static constexpr char kNvsKey[] = "cur_t2d1";
static constexpr char kNvsBootKey[] = "boot_t2d1";
static constexpr char kBootLabel[] =
    "EC5 RAW-P16 T2 CA coarse discovery successor";
static constexpr char kApiKindPrefix[] =
    "mf1750-ec5-raw-p16-crossover-t2-ca-coarse-discovery-successor-v1";
static constexpr char kBaseRoute[] =
    "/api/ec5/raw-p16-crossover-t2-ca-coarse-discovery-successor-v1";
static constexpr char kRole[] =
    "RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_ATLAS";
static constexpr char kBranch[] =
    "L535_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_V1_"
    "RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_ATLAS";
static constexpr char kDescriptorId[] =
    "4b24c2d4272b8e9c89d603154984f55d1704edf0848a447c63b9a8acbc8e7209";
static constexpr char kActionId[] =
    "6ca102bdd7190cba9e524a7d8d8afa0fd6f1e57a73cb913d55aa40976912383a";
static constexpr char kProfileId[] =
    "LEGACY_COMMENTED_HEADER__CS1_COMMENTED535__CS2_ACTIVE535";
static constexpr char kGlobalHeader[] = "commented";
static constexpr char kGlobalTupleId[] =
    "f88f007f11acab3aeec216ef9b0c30b794b5fcbb121ed859e629c488232471ed";
static constexpr uint8_t kRound = 1;

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

#endif  // MF1750_RAW_P16_CROSSOVER_T2_DISCOVERY_SUCCESSOR_V2_BUILD
