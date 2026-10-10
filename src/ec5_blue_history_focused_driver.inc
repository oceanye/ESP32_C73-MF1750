// Included only by ec5_blue_history_focused_epd_driver.cpp.  These five
// frames are the exact compiled counterparts of host/static_photo/
// blue_history.py.  They exercise 16 source->blue-target histories using the
// unchanged factory-OTP refresh path.  No caller supplied frame, LUT,
// waveform, electrical parameter, timing, retry, recovery, or auto-chain is
// exposed.

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600 &&
                  EPD_FRAME_BYTES == 307200 &&
                  EPD_CONTROLLER_WIDTH == 512 &&
                  EPD_CONTROLLER_FRAME_BYTES == 153600,
              "blue history focused requires frozen 1024x600 packed 4bpp");
static_assert(EPD_CS1_SOURCE_HALF == 0 && !EPD_CS1_FLIP_X &&
                  !EPD_CS1_FLIP_Y && !EPD_CS1_NIBBLE_SWAP &&
                  EPD_CS2_SOURCE_HALF == 1 && !EPD_CS2_FLIP_X &&
                  !EPD_CS2_FLIP_Y && !EPD_CS2_NIBBLE_SWAP,
              "blue history focused identities require MAP_ORIENT_V1");

namespace {

static constexpr uint8_t BHF_ROLE_COUNT = 5;
static constexpr uint8_t BHF_CODE_COUNT = 8;
static constexpr uint8_t BHF_BACKGROUND_CODE = 1;
static constexpr uint16_t BHF_CELL_WIDTH = 220;
static constexpr uint16_t BHF_CELL_HEIGHT = 128;
static constexpr uint16_t BHF_CELL_GAP_X = 8;
static constexpr uint16_t BHF_CELL_GAP_Y = 8;
static constexpr uint16_t BHF_HALF_MARGIN_X = 32;
static constexpr uint16_t BHF_MARGIN_Y = 32;

static_assert(BHF_HALF_MARGIN_X + 2 * BHF_CELL_WIDTH + BHF_CELL_GAP_X <=
                  EPD_CONTROLLER_WIDTH &&
                  BHF_MARGIN_Y + 4 * BHF_CELL_HEIGHT +
                          3 * BHF_CELL_GAP_Y <=
                      EPD_HEIGHT,
              "blue history focused grid exceeds the panel");

static constexpr char BHF_A_PRIMER_FRAME_SHA256[] =
    "6fef23f683694f434b3cb06209a5e77d458248b46c7a9c49932c503b725f9527";
static constexpr char BHF_A_PRIMER_DTM_SHA256[] =
    "f99960532731f22224ad88302f9518cc6d15c159a40e3116f52ab7f23e658980";
static constexpr char BHF_A_TARGET_FRAME_SHA256[] =
    "b5350449a22c5a77315c5e2148aa3a84a9b84411445579f349c8f888f1fe6a5a";
static constexpr char BHF_TARGET4_DTM_SHA256[] =
    "faecfc32d3f9a1f3d5ea82a5f81754bb281e0245dc2d4da8de9011aba4395e94";
static constexpr char BHF_TARGET7_DTM_SHA256[] =
    "962d9e8d678e7626837a08f69c25998206056201744c138d39fbd4c7bf8efa29";
static constexpr char BHF_WHITE_FRAME_SHA256[] =
    "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d";
static constexpr char BHF_WHITE_DTM_SHA256[] =
    "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158";
static constexpr char BHF_APRIME_PRIMER_FRAME_SHA256[] =
    "2d43f6da6ebdf58afaceff41c2359d7c82f336884df5f8fcf3d52574f8d8c186";
static constexpr char BHF_APRIME_PRIMER_DTM_SHA256[] =
    "2c25744b8e0df4cf6f0cc7b2a9bbfa3052c96eda4900ae48a1ba67bf75b2162f";
static constexpr char BHF_APRIME_TARGET_FRAME_SHA256[] =
    "1c547c7e4f18c7712450866dfe50e2afff069cd12901d39a343af83281e3f72c";

static constexpr const char *BHF_FAILURE_NONE = "none";
static constexpr const char *BHF_FAILURE_ALLOCATION = "allocation";
static constexpr const char *BHF_FAILURE_LAYOUT_DESIGN = "layout_design";
static constexpr const char *BHF_FAILURE_FRAME_BUILD = "frame_build";
static constexpr const char *BHF_FAILURE_HISTOGRAM = "histogram";
static constexpr const char *BHF_FAILURE_FULL_SHA = "full_sha";
static constexpr const char *BHF_FAILURE_CS1_COMPUTE = "cs1_compute";
static constexpr const char *BHF_FAILURE_CS2_COMPUTE = "cs2_compute";
static constexpr const char *BHF_FAILURE_CS1_IDENTITY = "cs1_identity";
static constexpr const char *BHF_FAILURE_CS2_IDENTITY = "cs2_identity";
static constexpr const char *BHF_FAILURE_CASCADE_PREPARE =
    "cascade_prepare";
static constexpr const char *BHF_FAILURE_STREAM_IDENTITY =
    "stream_identity";
static constexpr const char *BHF_FAILURE_REFRESH_SEQUENCE =
    "refresh_sequence";

struct BhfRoleIdentity {
  uint32_t frameFnv1a;
  uint32_t cs1DtmFnv1a;
  uint32_t cs2DtmFnv1a;
  const char *frameSha256;
  const char *cs1DtmSha256;
  const char *cs2DtmSha256;
  uint32_t histogram[BHF_CODE_COUNT];
};

static constexpr BhfRoleIdentity BHF_IDENTITIES[BHF_ROLE_COUNT] = {
    {0x539AF5C5UL, 0xA21BC9C5UL, 0xA21BC9C5UL,
     BHF_A_PRIMER_FRAME_SHA256, BHF_A_PRIMER_DTM_SHA256,
     BHF_A_PRIMER_DTM_SHA256,
     {56320, 220160, 56320, 56320, 56320, 56320, 56320, 56320}},
    {0x6BD595C5UL, 0x90821DC5UL, 0x8337A5C5UL,
     BHF_A_TARGET_FRAME_SHA256, BHF_TARGET4_DTM_SHA256,
     BHF_TARGET7_DTM_SHA256,
     {0, 163840, 0, 0, 225280, 0, 0, 225280}},
    {0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     BHF_WHITE_FRAME_SHA256, BHF_WHITE_DTM_SHA256, BHF_WHITE_DTM_SHA256,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {0x5760B5C5UL, 0x99FEA9C5UL, 0x99FEA9C5UL,
     BHF_APRIME_PRIMER_FRAME_SHA256, BHF_APRIME_PRIMER_DTM_SHA256,
     BHF_APRIME_PRIMER_DTM_SHA256,
     {56320, 220160, 56320, 56320, 56320, 56320, 56320, 56320}},
    {0x093595C5UL, 0x8337A5C5UL, 0x90821DC5UL,
     BHF_APRIME_TARGET_FRAME_SHA256, BHF_TARGET7_DTM_SHA256,
     BHF_TARGET4_DTM_SHA256,
     {0, 163840, 0, 0, 225280, 0, 0, 225280}},
};

struct BhfDtmIdentity {
  uint32_t fnv1a = 0;
  uint8_t sha256[32] = {};
};

struct BhfValidation {
  const char *failureStage = BHF_FAILURE_NONE;
  int32_t failureCode = 0;
  uint32_t frameFnv1a = 0;
  BhfDtmIdentity cs1;
  BhfDtmIdentity cs2;
};

size_t bhfRoleIndex(EpdBlueHistoryFocusedRole role) {
  return static_cast<size_t>(role);
}

bool bhfRoleValid(EpdBlueHistoryFocusedRole role) {
  return bhfRoleIndex(role) < BHF_ROLE_COUNT;
}

bool bhfValidateLayoutDesign() {
  return BHF_BACKGROUND_CODE < BHF_CODE_COUNT &&
         BHF_HALF_MARGIN_X + 2 * BHF_CELL_WIDTH + BHF_CELL_GAP_X <=
             EPD_CONTROLLER_WIDTH &&
         BHF_MARGIN_Y + 4 * BHF_CELL_HEIGHT + 3 * BHF_CELL_GAP_Y <=
             EPD_HEIGHT;
}

void bhfSetPixel(uint8_t *frame, uint16_t x, uint16_t y, uint8_t code) {
  const size_t offset = static_cast<size_t>(y) * (EPD_WIDTH / 2) + x / 2;
  if (x & 1U) {
    frame[offset] = static_cast<uint8_t>((frame[offset] & 0xF0U) | code);
  } else {
    frame[offset] =
        static_cast<uint8_t>((frame[offset] & 0x0FU) | (code << 4));
  }
}

void bhfFillCell(uint8_t *frame, uint8_t controller, uint8_t slot,
                 uint8_t code) {
  const uint16_t halfOffset =
      controller == 0 ? 0 : EPD_CONTROLLER_WIDTH;
  const uint16_t x0 = halfOffset + BHF_HALF_MARGIN_X +
                      (slot % 2) * (BHF_CELL_WIDTH + BHF_CELL_GAP_X);
  const uint16_t y0 = BHF_MARGIN_Y +
                      (slot / 2) * (BHF_CELL_HEIGHT + BHF_CELL_GAP_Y);
  for (uint16_t y = y0; y < y0 + BHF_CELL_HEIGHT; ++y) {
    for (uint16_t x = x0; x < x0 + BHF_CELL_WIDTH; ++x) {
      bhfSetPixel(frame, x, y, code);
    }
  }
}

bool bhfBuildFrame(EpdBlueHistoryFocusedRole role, uint8_t *frame,
                   uint32_t *histogram) {
  if (!frame || !histogram || !bhfRoleValid(role) ||
      !bhfValidateLayoutDesign()) {
    return false;
  }
  std::memset(frame, 0x11, EPD_FRAME_BYTES);
  if (role != EpdBlueHistoryFocusedRole::White) {
    const bool prime =
        role == EpdBlueHistoryFocusedRole::APrimePrimer ||
        role == EpdBlueHistoryFocusedRole::APrimeTarget;
    const bool target = role == EpdBlueHistoryFocusedRole::ATarget ||
                        role == EpdBlueHistoryFocusedRole::APrimeTarget;
    for (uint8_t controller = 0; controller < 2; ++controller) {
      const uint8_t targetCode = prime ? (controller == 0 ? 7 : 4)
                                       : (controller == 0 ? 4 : 7);
      for (uint8_t slot = 0; slot < 8; ++slot) {
        const uint8_t sourceCode = prime ? 7 - slot : slot;
        bhfFillCell(frame, controller, slot,
                    target ? targetCode : sourceCode);
      }
    }
  }

  std::memset(histogram, 0, BHF_CODE_COUNT * sizeof(uint32_t));
  for (size_t index = 0; index < EPD_FRAME_BYTES; ++index) {
    const uint8_t high = frame[index] >> 4;
    const uint8_t low = frame[index] & 0x0F;
    if (high >= BHF_CODE_COUNT || low >= BHF_CODE_COUNT) return false;
    ++histogram[high];
    ++histogram[low];
  }
  return true;
}

bool bhfDigestMatchesHex(const uint8_t digest[32], const char *expected) {
  if (!digest || !expected || std::strlen(expected) != 64) return false;
  static constexpr char kHex[] = "0123456789abcdef";
  for (size_t index = 0; index < 32; ++index) {
    if (expected[index * 2] != kHex[digest[index] >> 4] ||
        expected[index * 2 + 1] != kHex[digest[index] & 0x0F]) {
      return false;
    }
  }
  return true;
}

bool bhfComputeDtmIdentity(const uint8_t *frame, bool secondController,
                           BhfDtmIdentity *identity, int32_t *errorCode) {
  if (!frame || !identity || !errorCode) return false;
  *identity = BhfDtmIdentity{};
  *errorCode = 0;
  static constexpr size_t kFullRowBytes = EPD_WIDTH / 2;
  static constexpr size_t kControllerRowBytes = EPD_CONTROLLER_WIDTH / 2;
  uint8_t mappedRow[kControllerRowBytes] = {};
  const ControllerMapping &mapping =
      CONTROLLER_MAPPINGS[secondController ? 1 : 0];
  mbedtls_sha256_context context;
  mbedtls_sha256_init(&context);
  const int startsResult = mbedtls_sha256_starts_ret(&context, 0);
  if (startsResult != 0) {
    *errorCode = startsResult;
    mbedtls_sha256_free(&context);
    return false;
  }
  uint32_t dtmHash = FNV1A_OFFSET_BASIS;
  for (uint16_t outputY = 0; outputY < EPD_HEIGHT; ++outputY) {
    const uint16_t sourceY =
        mapping.flipY ? EPD_HEIGHT - 1 - outputY : outputY;
    const size_t rowOffset = static_cast<size_t>(sourceY) * kFullRowBytes;
    const size_t halfOffset =
        static_cast<size_t>(mapping.sourceHalf) * kControllerRowBytes;
    const uint8_t *row = frame + rowOffset + halfOffset;
    for (size_t outputByte = 0; outputByte < kControllerRowBytes;
         ++outputByte) {
      const size_t sourceByte = mapping.flipX
                                    ? kControllerRowBytes - 1 - outputByte
                                    : outputByte;
      uint8_t value = row[sourceByte];
      if (mapping.flipX != mapping.nibbleSwap) {
        value = static_cast<uint8_t>((value << 4) | (value >> 4));
      }
      mappedRow[outputByte] = value;
      dtmHash = fnv1aUpdate(dtmHash, value);
    }
    const int updateResult =
        mbedtls_sha256_update_ret(&context, mappedRow, sizeof(mappedRow));
    if (updateResult != 0) {
      *errorCode = updateResult;
      mbedtls_sha256_free(&context);
      return false;
    }
  }
  const int finishResult =
      mbedtls_sha256_finish_ret(&context, identity->sha256);
  mbedtls_sha256_free(&context);
  if (finishResult != 0) {
    *errorCode = finishResult;
    return false;
  }
  identity->fnv1a = dtmHash;
  return true;
}

bool bhfValidateRole(EpdBlueHistoryFocusedRole role, uint8_t *frame,
                     BhfValidation *validation) {
  if (!frame || !validation || !bhfRoleValid(role)) return false;
  *validation = BhfValidation{};
  if (!bhfValidateLayoutDesign()) {
    validation->failureStage = BHF_FAILURE_LAYOUT_DESIGN;
    return false;
  }
  uint32_t histogram[BHF_CODE_COUNT] = {};
  if (!bhfBuildFrame(role, frame, histogram)) {
    validation->failureStage = BHF_FAILURE_FRAME_BUILD;
    return false;
  }
  const BhfRoleIdentity &wanted = BHF_IDENTITIES[bhfRoleIndex(role)];
  if (std::memcmp(histogram, wanted.histogram, sizeof(wanted.histogram)) !=
      0) {
    validation->failureStage = BHF_FAILURE_HISTOGRAM;
    return false;
  }

  validation->frameFnv1a = fnv1a(frame, EPD_FRAME_BYTES);
  uint8_t frameDigest[32] = {};
  const int frameShaResult =
      mbedtls_sha256_ret(frame, EPD_FRAME_BYTES, frameDigest, 0);
  if (validation->frameFnv1a != wanted.frameFnv1a || frameShaResult != 0 ||
      !bhfDigestMatchesHex(frameDigest, wanted.frameSha256)) {
    validation->failureStage = BHF_FAILURE_FULL_SHA;
    validation->failureCode = frameShaResult;
    return false;
  }
  if (!bhfComputeDtmIdentity(frame, false, &validation->cs1,
                             &validation->failureCode)) {
    validation->failureStage = BHF_FAILURE_CS1_COMPUTE;
    return false;
  }
  if (!bhfComputeDtmIdentity(frame, true, &validation->cs2,
                             &validation->failureCode)) {
    validation->failureStage = BHF_FAILURE_CS2_COMPUTE;
    return false;
  }
  if (validation->cs1.fnv1a != wanted.cs1DtmFnv1a ||
      !bhfDigestMatchesHex(validation->cs1.sha256, wanted.cs1DtmSha256)) {
    validation->failureStage = BHF_FAILURE_CS1_IDENTITY;
    return false;
  }
  if (validation->cs2.fnv1a != wanted.cs2DtmFnv1a ||
      !bhfDigestMatchesHex(validation->cs2.sha256, wanted.cs2DtmSha256)) {
    validation->failureStage = BHF_FAILURE_CS2_IDENTITY;
    return false;
  }
  return true;
}

}  // namespace

bool epdValidateCompiledBlueHistoryFocusedFixtures() {
  if (!bhfValidateLayoutDesign()) return false;
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) return false;
  static constexpr EpdBlueHistoryFocusedRole kRoles[] = {
      EpdBlueHistoryFocusedRole::APrimer,
      EpdBlueHistoryFocusedRole::ATarget,
      EpdBlueHistoryFocusedRole::White,
      EpdBlueHistoryFocusedRole::APrimePrimer,
      EpdBlueHistoryFocusedRole::APrimeTarget,
  };
  bool valid = true;
  for (const EpdBlueHistoryFocusedRole role : kRoles) {
    BhfValidation validation;
    valid = bhfValidateRole(role, frame, &validation);
    if (!valid) break;
  }
  std::free(frame);
  return valid;
}

bool epdDisplayCompiledBlueHistoryFocused(EpdBlueHistoryFocusedRole role) {
  // epdBeginOperation initializes diagnostics only.  GPIO/SPI/panel setup is
  // still behind the complete allocation and identity gate below.
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  diagnosticReport.freePsramBefore = ESP.getFreePsram();
  diagnosticReport.largestPsramBlockBefore =
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
  if (!bhfRoleValid(role)) {
    return epdRejectBeforePanelIo(started, BHF_FAILURE_FRAME_BUILD);
  }
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) {
    return epdRejectBeforePanelIo(started, BHF_FAILURE_ALLOCATION);
  }

  BhfValidation validation;
  const bool identityOk = bhfValidateRole(role, frame, &validation);
  diagnosticReport.inputFrameFnv1a = validation.frameFnv1a;
  diagnosticReport.cs1DtmFnv1a = validation.cs1.fnv1a;
  diagnosticReport.cs2DtmFnv1a = validation.cs2.fnv1a;
  if (!identityOk) {
    std::free(frame);
    return epdRejectBeforePanelIo(started, validation.failureStage,
                                  validation.failureCode);
  }

  if (!epdPrepareCascade(EPD_SPI_DEFAULT_HZ)) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started,
                                        BHF_FAILURE_CASCADE_PREPARE);
  }
  const uint32_t cs1Started = millis();
  diagnosticReport.cs1DtmFnv1a =
      epdStreamPackedFrameController(frame, false);
  diagnosticReport.cs1UploadMs = millis() - cs1Started;
  const uint32_t cs2Started = millis();
  diagnosticReport.cs2DtmFnv1a =
      epdStreamPackedFrameController(frame, true);
  diagnosticReport.cs2UploadMs = millis() - cs2Started;
  diagnosticReport.mappingApplied = true;
  std::free(frame);

  const BhfRoleIdentity &wanted = BHF_IDENTITIES[bhfRoleIndex(role)];
  if (diagnosticReport.cs1DtmFnv1a != wanted.cs1DtmFnv1a ||
      diagnosticReport.cs2DtmFnv1a != wanted.cs2DtmFnv1a) {
    return epdFinishFailedOperationSafe(started,
                                        BHF_FAILURE_STREAM_IDENTITY);
  }
  setActiveControllers(true, true);
  const bool ok = epdSecondSettingAndRefresh();
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  if (!ok) epdRecordFailure(BHF_FAILURE_REFRESH_SEQUENCE);
  return epdFinishOperation(started, ok);
}
