#pragma once

namespace mf1750_raw_p16_endpoint_gallery_v1 {

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
static constexpr uint8_t kGridColumns = 2;
static constexpr uint16_t kGridX0 = 36;
static constexpr uint16_t kGridY0 = 36;
static constexpr uint16_t kGridXByColumn[2] = {36, 276};
static constexpr uint16_t kGridYByRow[4] = {36, 180, 324, 468};
static constexpr uint8_t kCodeRows[4][2] = {
    {0, 1}, {2, 3}, {4, 5}, {6, 7},
};
static constexpr uint16_t kCellWidth = 200;
static constexpr uint16_t kCellHeight = 96;
static constexpr uint16_t kGapX = 40;
static constexpr uint16_t kGapY = 48;
static constexpr uint16_t kGridX1Exclusive = 476;
static constexpr uint16_t kGridY1Exclusive = 564;
static constexpr char kActiveProfileId[] =
    "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";
static constexpr char kCommentedProfileId[] =
    "LEGACY_COMMENTED_HEADER__CS1_ACTIVE535__CS2_COMMENTED535";
static constexpr char kVariantKey[] =
    "L535_ACTIVE_RAW_P16_ENDPOINT_GALLERY_2X4_V1";
static constexpr char kBuildTag[] =
    "MF1750_EC5_RAW_P16_ENDPOINT_GALLERY_V1_2026-08-28";
static constexpr char kTestId[] = "EC5-RAW-P16-ENDPOINT-GALLERY-V1";
static constexpr char kCampaignId[] = "EC5_RAW_P16_ENDPOINT_GALLERY_V1";
static constexpr char kContractId[] =
    "f9b1f6b8052322bedc6b702cb895425e7c3dc5e2d1b7d9ae6e68edaa1ffc409d";
static constexpr char kNvsNamespace[] = "rp16g_v1";
static constexpr char kNvsBootKey[] = "boot_p16g";

// Full-frame only; the inherited type is never emitted as PTLW.
static constexpr Window kWindows[1] = {{36, 36, 200, 96, 0, 0}};

static constexpr ActionIdentity kActions[kRoleIdentityCount] = {{
    "RAW_P16_ACTIVE_ENDPOINT_GALLERY",
    "L535_ACTIVE_RAW_P16_ENDPOINT_GALLERY_2X4_V1_ACTIVE_GLOBAL_CODE0_TO_7_BOTH_CONTROLLERS",
    "146bbe7c331c10d410375c90d8879816427337ef21008c3e666ff74fe50b47e4",
    "9f5b84a12ac93c85898d2e843db6a5a4d174daa6ce0f18ffd8da974737f0a088",
    "46e86cf0ca6c537aaf694dda7eaf599a39992e0eac004858e413b6821bff94d9",
    "d141dbb111518bf45d74ab644fb804a6d2f8272ec13cfce13b6de061e6a53606",
    "d141dbb111518bf45d74ab644fb804a6d2f8272ec13cfce13b6de061e6a53606",
    0xA47049C5UL,
    0xED2673C5UL,
    0xED2673C5UL,
    {38400, 38400, 38400, 38400, 38400, 38400, 38400, 345600},
}};

static_assert(kGridRows == 4 && kGridColumns == 2,
              "RAW-P16 endpoint atlas geometry changed");
static_assert(kGridX1Exclusive <= 512 && kGridY1Exclusive <= 600 &&
                  (kGridX0 & 1U) == 0 && (kCellWidth & 1U) == 0 &&
                  (kGapX & 1U) == 0 && !kCs2VerticalMirror,
              "RAW-P16 packed-grid geometry changed");
static_assert(sizeof(kActions) / sizeof(kActions[0]) == kRoleIdentityCount,
              "RAW-P16 action identity changed");

}  // namespace mf1750_raw_p16_endpoint_gallery_v1
