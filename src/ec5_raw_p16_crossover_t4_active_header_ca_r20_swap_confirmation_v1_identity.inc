#pragma once

#if !defined(MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_V1_BUILD)
#error "T4 active-header CA R20 swap confirmation requires its isolated build macro"
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
    "EXPERIMENTAL_HUMAN_PRIMARY_MATCHED_R20_SWAP_CONFIRMATION_ONLY_"
    "ACTIVE_HEADER_CA_NOT_FORMAL_GATE_NOT_COLOUR_QUALIFICATION_"
    "ZERO_QUALIFIED_COLOURS";
static constexpr char kDeviceApiVersion[] =
    "MF1750_EC5_RAW_P16_CROSSOVER_T4_MATCHED_SWAP_DEVICE_V1";
static constexpr char kIdentityRevision[] =
    "raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-v1";
static constexpr char kProfileSource[] =
    "legacy_complete_535_cross_controller_tuple";
static constexpr char kBaselineRole[] =
    "EXTERNAL_FACTORY_OTP_WHITE_BEFORE_AND_AFTER_REQUIRED";
static constexpr char kArmIntent[] =
    "ARM_ONE_FIXED_RAW_P16_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_"
    "ACTION_NOT_HARDWARE_AUTHORIZATION";
static constexpr char kExecuteIntent[] =
    "EXECUTE_ONE_ARMED_RAW_P16_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_"
    "ACTION_ONCE";

// Full-frame only. The inherited driver never emits this as a PTLW window.
static constexpr Window kWindows[1] = {{20, 44, 52, 100, 0, 0}};

// Matched counterpart to T3 V2: the active global header and every display
// byte stay fixed; only complete controller R20 assignments exchange sides.
static constexpr bool kGlobalUseCommented = false;
static constexpr bool kCs1UseCommented = true;
static constexpr bool kCs2UseCommented = false;
static constexpr char kVariantKey[] =
    "L535_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_"
    "SWAP_CONFIRMATION_V1_2026-08-31";
static constexpr char kTestId[] =
    "EC5-RAW-P16-CROSSOVER-T4-ACTIVE-HEADER-CA-R20-SWAP-CONFIRMATION-V1";
static constexpr char kCampaignId[] =
    "EC5_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_V1";
static constexpr char kContractId[] =
    "08fe1fda76a28444a0fa49b6427d2c4f31266ab06208b21376f61e4490b342e6";
static constexpr char kNvsNamespace[] = "p16t4ca_v1";
static constexpr char kNvsKey[] = "cur_t4ca1";
static constexpr char kNvsBootKey[] = "boot_t4ca1";
static constexpr char kBootLabel[] =
    "EC5 RAW-P16 T4 active-header CA matched R20 swap confirmation";
static constexpr char kApiKindPrefix[] =
    "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-v1";
static constexpr char kBaseRoute[] =
    "/api/ec5/raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-v1";
static constexpr char kRole[] =
    "RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_ATLAS";
static constexpr char kBranch[] =
    "L535_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_V1_"
    "RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_ATLAS";
static constexpr char kDescriptorId[] =
    "3acce00e0b0ed8ffb14fe68d69bd393b89120152a27c957e6cc33f7370723a7f";
static constexpr char kActionId[] =
    "c9a88f5b4cae0589279d3d874f81492c17d6ba4afc2f5da256fec56bec9b36a1";
static constexpr char kPriorActionId[] =
    "73f6e97b49b5bd8c46edbba9edffde99967dcb170be6150082dc7c68100fada5";
static constexpr char kProfileId[] =
    "LEGACY_ACTIVE_HEADER__CS1_COMMENTED535__CS2_ACTIVE535";
static constexpr char kGlobalHeader[] = "active";
static constexpr char kGlobalTupleId[] =
    "3c033d3649587e17f33eca74afd278a773f056b73da53c0885981caeb19ef721";
static constexpr uint8_t kRound = 4;

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
static_assert(kGlobalUseCommented == false && kCs1UseCommented &&
                  !kCs2UseCommented,
              "T4 requires active global with CA controller R20 assignment");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kRoleIdentityCount,
              "position-balanced role identity changed");

}  // namespace mf1750_raw_p16_crossover_t2_discovery_successor
