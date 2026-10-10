#pragma once

namespace mf1750_runtime_lut_ptlw_fullframe_ab_v2 {

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

static constexpr uint8_t kRoleCount = 2;
static constexpr uint8_t kActionCount = 2;
static constexpr uint8_t kWhiteCode = 7;
static constexpr uint8_t kBlueCode = 5;
static constexpr uint32_t kFullControllerDtmBytes = 153600;
static constexpr uint32_t kCroppedDtmBytes = 9600;
static constexpr uint8_t kPartialWindowCommand = 0x83;
static constexpr uint8_t kPartialWindowPayloadBytes = 9;
static constexpr uint8_t kPartialWindowMode = 0x01;
static constexpr bool kCs2VerticalMirror = false;
static constexpr bool kSeparateCsWindowCommands = true;
static constexpr bool kPtlwYEndOneMore = false;
static constexpr bool kExternalFactoryWhiteAnchorRequired = false;
static constexpr bool kFactoryOtpAnchorActionsReachable = true;
static constexpr bool kRuntimeCode7ActionReachable = false;
static constexpr bool kRuntimeCode7PrestageReachable = true;
static constexpr bool kRepeatPtlwAfterPonBusy = false;
static constexpr bool kActionStageCdi = false;
static constexpr bool kActionStageBtst2 = false;
static constexpr bool kCommand0x86Reachable = false;

static constexpr char kVariantKey[] =
    "L535_FACTORY_WHITE_PTLW_FULLFRAME_AB_V2";
static constexpr char kBuildTag[] =
    "MF1750_EC5_RUNTIME_LUT_PTLW_FULLFRAME_AB_V2_2026-08-26";
static constexpr char kTestId[] =
    "EC5-RUNTIME-LUT-PTLW-FULLFRAME-AB-V2";
static constexpr char kCampaignId[] =
    "EC5_RUNTIME_LUT_PTLW_FULLFRAME_AB_V2";
static constexpr char kContractId[] =
    "8ca2c5df3f293a237a299a06ca48d643c154285dcfb4e22192745dfbc2267111";
static constexpr char kNvsNamespace[] = "rlpffab_v2";
static constexpr char kNvsKey[] = "cursor_ab2";
static constexpr char kProfileId[] =
    "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";

// One controller-local 160x120 ROI.  Both controllers use the same local
// coordinates.  PTLW endpoints are inclusive: xe=x+w-1 and ye=y+h-1.
static constexpr Window kWindow = {176, 240, 160, 120, 5, 5};
static constexpr uint8_t kPtlwPayload[kPartialWindowPayloadBytes] = {
    0x00, 0xB0, 0x01, 0x4F, 0x00, 0xF0, 0x01, 0x67, 0x01,
};

static constexpr char kPreloadDtmSha256[] =
    "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd";
static constexpr uint32_t kPreloadDtmFnv1a = 0x285715C5UL;
static constexpr char kFullCompositeDtmSha256[] =
    "352e61d15eb963fe2e1b37a07664be885ec6c8a0e1383bb3e96869fe517ca3ed";
static constexpr uint32_t kFullCompositeDtmFnv1a = 0x2FA81DC5UL;
static constexpr char kCroppedDtmSha256[] =
    "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3";
static constexpr uint32_t kCroppedDtmFnv1a = 0x77244145UL;
static constexpr char kTreatmentACombinedDtmSha256[] =
    "5f592d3f581cddb9b625a17a1507b7df4a01e16da8e8fefc94783910a33bc190";
static constexpr uint32_t kTreatmentACombinedDtmFnv1a = 0x83E295C5UL;
static constexpr char kTreatmentBCombinedDtmSha256[] =
    "a84b59d945284e204a5d1b3d4d7a139a3e429d6cc557ec7645cabfb1cc48146f";
static constexpr uint32_t kTreatmentBCombinedDtmFnv1a = 0xD92EB945UL;
static constexpr char kLogicalFrameSha256[] =
    "c0b69123df2d5f80702d75301b453b1c46ff9fa945bea99fdcf75f298c2f9576";
static constexpr uint32_t kLogicalFrameFnv1a = 0x2E339DC5UL;

// A and B have identical final controller SRAM and identical logical pixels.
// Only their addressing transport differs: A uploads the complete composite
// controller plane without PTLW; B uploads the code-5 crop under one PTLW.
// Each action's cs1/cs2 DTM identity covers its complete transmitted stream,
// prestage || target, not merely the target component.
static constexpr ActionIdentity kActions[kActionCount] = {
    {"TREATMENT_A_FULLFRAME_COMPOSITE",
     "L535_CODE7_PRESTAGE_THEN_FULLFRAME_COMPOSITE_NO_PTLW",
     "71ac9664e43d630243fc0675e1b6a41ad3fea90ec789d86a6b607934f7c70f0b",
     "4fd836603acaf06d28985b96049fa3b0753c02373b35dbc6ebcabc5d12ee6ad1",
     kLogicalFrameSha256, kTreatmentACombinedDtmSha256,
     kTreatmentACombinedDtmSha256, kLogicalFrameFnv1a,
     kTreatmentACombinedDtmFnv1a, kTreatmentACombinedDtmFnv1a,
     {0, 0, 0, 0, 0, 38400, 0, 576000}},
    {"TREATMENT_B_INCLUSIVE_PTLW_CROP",
     "L535_CODE7_PRESTAGE_THEN_INCLUSIVE_PTLW_CODE5_CROP",
     "cd758ace217487557d8edf193c5b1e547a040f77eab954cfc6f3bd37760f8767",
     "15bf776e63b37cedd86a5d92e0886cd635de03aa4db6d8e679964bd17f9b57fb",
     kLogicalFrameSha256, kTreatmentBCombinedDtmSha256,
     kTreatmentBCombinedDtmSha256, kLogicalFrameFnv1a,
     kTreatmentBCombinedDtmFnv1a, kTreatmentBCombinedDtmFnv1a,
     {0, 0, 0, 0, 0, 38400, 0, 576000}},
};

static_assert(kWindow.x + kWindow.width - 1 == 0x014F &&
                  kWindow.y + kWindow.height - 1 == 0x0167,
              "full-frame/PTLW A/B inclusive endpoint changed");
static_assert(sizeof(kPtlwPayload) == kPartialWindowPayloadBytes &&
                  kPtlwPayload[8] == kPartialWindowMode,
              "full-frame/PTLW A/B PTLW payload changed");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kActionCount,
              "full-frame/PTLW A/B requires exactly two treatments");
static_assert(!kExternalFactoryWhiteAnchorRequired &&
                  kFactoryOtpAnchorActionsReachable &&
                  kRuntimeCode7PrestageReachable &&
                  !kRuntimeCode7ActionReachable &&
                  !kRepeatPtlwAfterPonBusy && !kActionStageCdi &&
                  !kActionStageBtst2 && !kCommand0x86Reachable,
              "full-frame/PTLW A/B action-stage contract changed");

}  // namespace mf1750_runtime_lut_ptlw_fullframe_ab_v2
