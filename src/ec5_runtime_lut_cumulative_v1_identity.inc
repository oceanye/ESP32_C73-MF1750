#pragma once

namespace mf1750_runtime_lut_cumulative_v1 {

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
static constexpr char kVariantKey[] =
    "L535_ACTIVE_GLOBAL_CUMULATIVE_PACKED_FRAME_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_RUNTIME_LUT_CUMULATIVE_L535_ACTIVE_V1_2026-08-23";
static constexpr char kTestId[] =
    "EC5-RUNTIME-LUT-CUMULATIVE-L535-ACTIVE-V1";
static constexpr char kCampaignId[] =
    "EC5_RUNTIME_LUT_CUMULATIVE_L535_ACTIVE_V1";
static constexpr char kContractId[] =
    "0ed058f2251876c6ed11bbf118499e693a7924878f8a33f4199160e5aa24938b";
static constexpr char kNvsNamespace[] = "rlcum535_v1";
static constexpr char kProfileId[] =
    "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";

static constexpr Window kWindows[3] = {
    {48, 64, 160, 120, 3, 3},
    {304, 240, 160, 120, 5, 5},
    {48, 416, 160, 120, 6, 6},
};

static constexpr ActionIdentity kActions[kActionCount] = {
    {"RUNTIME_LUT_WHITE_BASELINE",
     "L535_ACTIVE_GLOBAL_CUMULATIVE_CODE7_WHITE",
     "86ee8373496ff38db09df445e356375c5c78415cbe2677e746221eecc397ef3d",
     "7ba705150cc78e4d98f102b83c5ca70bf06328136a7747b3c460c300a9b25945",
     "f27255891c2b00350b2f7aca6f0719116c6a29262008b7621ef4b7df66b099f2",
     "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     0x7C918DC5UL, 0x285715C5UL, 0x285715C5UL,
     {0, 0, 0, 0, 0, 0, 0, 614400}},
    {"PATCH_A",
     "L535_ACTIVE_GLOBAL_FULL_FRAME_CODE3_A",
     "8999ab9aa421e2780a6ae158a5cf2f4cd8f6327d38731fe4510ced0c21277d30",
     "8e95ff898596538d02c0da216a99b661dc7ebe94864d9c41b1cbf10cf1645409",
     "89696fbebcc192494863d1e83f95b3a76a810def6a1a3efc8526f989c04f47a7",
     "6d46158eb54b29b88e8c5fff417aa089ca450785612cf18794c73dd6dd1246bd",
     "6d46158eb54b29b88e8c5fff417aa089ca450785612cf18794c73dd6dd1246bd",
     0xC30B65C5UL, 0xBE5401C5UL, 0xBE5401C5UL,
     {0, 0, 0, 38400, 0, 0, 0, 576000}},
    {"PATCH_B",
     "L535_ACTIVE_GLOBAL_FULL_FRAME_CODE3_A_CODE5_B",
     "0872c1773c8700bc12dabcfc46ea606b2b9c43895690b4714ee5f4f95f562042",
     "9aef62495834c6767fcd45aec55f53ce91e333b8ea08e4cf3dc7bf9a20e8d2e2",
     "a604bb9d01b47d520c1c6cac9311f5f4761cd7e30361e3f13c79602c545e6f3a",
     "f67ef0edc603da72227df0bf89360cfbf41a3e34f14fb42d5c24ed03f9cdfed5",
     "f67ef0edc603da72227df0bf89360cfbf41a3e34f14fb42d5c24ed03f9cdfed5",
     0x0D48B5C5UL, 0x03F2A9C5UL, 0x03F2A9C5UL,
     {0, 0, 0, 38400, 0, 38400, 0, 537600}},
    {"PATCH_C",
     "L535_ACTIVE_GLOBAL_FULL_FRAME_CODE3_A_CODE5_B_CODE6_C",
     "93c0250760dd547abe6e208396075fd4f85af54dab171034ff859f7de578bf49",
     "5784cb047dfef5987892e74a5191f0dc3ad0e94ba618cde8a55bccb5a017b01e",
     "92c0c0a116e2bf1f78a652bbfb56f3705d254df104dd4b9d36a56907f1d1b4b7",
     "791e5f7e120ee0cea182e6fe7ff279d0817496330002c654680d8a98e131a681",
     "791e5f7e120ee0cea182e6fe7ff279d0817496330002c654680d8a98e131a681",
     0x302E12C5UL, 0x358D5845UL, 0x358D5845UL,
     {0, 0, 0, 38400, 0, 38400, 38400, 499200}},
    {"RUNTIME_LUT_WHITE_RECOVERY",
     "L535_ACTIVE_GLOBAL_CUMULATIVE_CODE7_WHITE_RECOVERY",
     "90903ad58e1f24fc00a06022950bc43751b9012a4436fc3ccddf4315cd67b6ca",
     "67b444ee1d21ee9e72eeaec169d3f22500e4d978ef121358fddac9a5bfbfc3b9",
     "f27255891c2b00350b2f7aca6f0719116c6a29262008b7621ef4b7df66b099f2",
     "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     "3a70abe1f95b3d4d86d81a259c3528122e23f0a220fea1d3db75585daae20abd",
     0x7C918DC5UL, 0x285715C5UL, 0x285715C5UL,
     {0, 0, 0, 0, 0, 0, 0, 614400}},
};

static_assert(sizeof(kWindows) / sizeof(kWindows[0]) == 3,
              "cumulative fallback requires three visual ROIs");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kActionCount,
              "cumulative fallback requires five actions");

}  // namespace mf1750_runtime_lut_cumulative_v1
