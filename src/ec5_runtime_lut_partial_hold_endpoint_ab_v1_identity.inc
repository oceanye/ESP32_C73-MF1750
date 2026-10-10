#pragma once

namespace mf1750_runtime_lut_partial_hold_endpoint_ab_v1 {

struct Window {
  uint16_t x;
  uint16_t y;
  uint16_t width;
  uint16_t height;
  uint8_t cs1Code;
  uint8_t cs2Code;
  bool cs1YEndOneMore;
  bool cs2YEndOneMore;
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
static constexpr uint8_t kPartialWindowCommand = 0x83;
static constexpr uint8_t kPartialWindowPayloadBytes = 9;
static constexpr uint8_t kPartialWindowMode = 0x01;
static constexpr bool kCs2VerticalMirror = false;
static constexpr bool kSeparateCsWindowCommands = true;
static constexpr bool kExternalFactoryWhiteAnchorRequired = false;
static constexpr bool kFactoryOtpAnchorActionsReachable = true;
static constexpr bool kRepeatPtlwAfterPonBusy = true;
static constexpr bool kRuntimeCode7ActionReachable = false;
static constexpr char kVariantKey[] =
    "L535_FACTORY_WHITE_PTLW_YEND_CONTROLLER_SWAP_AB_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_RUNTIME_LUT_PTLW_YEND_AB_V1_2026-08-24";
static constexpr char kTestId[] = "EC5-RUNTIME-LUT-PTLW-YEND-AB-V1";
static constexpr char kCampaignId[] = "EC5_RUNTIME_LUT_PTLW_YEND_AB_V1";
static constexpr char kContractId[] =
    "e1ab72d894a791cab52c68377e63486440bbe3887d999e45b85fd0a828e251c8";
static constexpr char kNvsNamespace[] = "rlph_yeab_v1";
static constexpr char kProfileId[] =
    "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";

// The exact SPD1657A local manual supports y+h-1.  y+h is retained only as an
// adjacent-Gx experimental comparator, never as a predicted fix.  The DTM
// stream is 160*120/2 = 9600 bytes for every controller; these booleans change
// only the 16-bit PTLW Y-end field before DTM and after PON.
static constexpr Window kWindows[kActionCount] = {
    {176, 240, 160, 120, 5, 5, false, true},
    {176, 240, 160, 120, 5, 5, true, false},
};

static constexpr ActionIdentity kActions[kActionCount] = {
    {"PATCH_A",
     "CODE5_BLUE_CS1_YH_MINUS1_CS2_YH_SWAP_A",
     "5dafe2e79d645c5a6ff05ddfd314ff6c071018a2aa291943d720219e19e3843f",
     "3d357e09b350888772be8f233158b09b704601e1419ab831b5d3356e4ec76268",
     "c0b69123df2d5f80702d75301b453b1c46ff9fa945bea99fdcf75f298c2f9576",
     "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3",
     "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3",
     0x2E339DC5UL, 0x77244145UL, 0x77244145UL,
     {0, 0, 0, 0, 0, 38400, 0, 576000}},
    {"PATCH_B",
     "CODE5_BLUE_CS1_YH_CS2_YH_MINUS1_SWAP_B",
     "99425ad8387363060dc46e4040905f3687a0f69b378ef8828edfa0a483174beb",
     "b5c9e0a00b386e8281b9b59e67a90a38ed96b9ddb5a400a905da4b9d43eb032d",
     "c0b69123df2d5f80702d75301b453b1c46ff9fa945bea99fdcf75f298c2f9576",
     "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3",
     "b264fbc2a6dbe46f40eac30ba477bee77b36b18dedfce73bb170a5e332cdf3f3",
     0x2E339DC5UL, 0x77244145UL, 0x77244145UL,
     {0, 0, 0, 0, 0, 38400, 0, 576000}},
};

static_assert(sizeof(kWindows) / sizeof(kWindows[0]) == kActionCount,
              "endpoint A/B requires exactly two partial windows");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kActionCount,
              "endpoint A/B requires exactly two partial identities");
static_assert(!kExternalFactoryWhiteAnchorRequired &&
                  kFactoryOtpAnchorActionsReachable &&
                  kRepeatPtlwAfterPonBusy && !kRuntimeCode7ActionReachable,
              "endpoint A/B palette/anchor contract changed");

}  // namespace mf1750_runtime_lut_partial_hold_endpoint_ab_v1
