// Included only by epd_driver.cpp when
// MF1750_ENABLE_OTP_TRANSITION_MATRIX=1. This fixture uses the already
// validated factory-OTP cascade path. It never accepts caller-controlled
// pixels, LUT bytes, voltage values, waveform parameters, or refresh timing.

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600 &&
                  EPD_FRAME_BYTES == 307200 &&
                  EPD_CONTROLLER_WIDTH == 512 &&
                  EPD_CONTROLLER_FRAME_BYTES == 153600,
              "OTP transition matrix requires frozen 1024x600 packed 4bpp");
static_assert(EPD_CS1_SOURCE_HALF == 0 && !EPD_CS1_FLIP_X &&
                  !EPD_CS1_FLIP_Y && !EPD_CS1_NIBBLE_SWAP &&
                  EPD_CS2_SOURCE_HALF == 1 && !EPD_CS2_FLIP_X &&
                  !EPD_CS2_FLIP_Y && !EPD_CS2_NIBBLE_SWAP,
              "OTP transition identities require MAP_ORIENT_V1");

namespace {

static constexpr uint8_t OTM_CODE_COUNT = 8;
static constexpr uint16_t OTM_CELL_WIDTH = 56;
static constexpr uint16_t OTM_CELL_HEIGHT = 64;
static constexpr uint16_t OTM_GRID_X0 = 32;
static constexpr uint16_t OTM_GRID_Y0 = 44;
static constexpr uint8_t OTM_CS1_ORDER[OTM_CODE_COUNT] = {
    0, 1, 2, 3, 4, 5, 6, 7,
};
static constexpr uint8_t OTM_CS2_ORDER[OTM_CODE_COUNT] = {
    7, 6, 5, 4, 3, 2, 1, 0,
};
static constexpr size_t OTM_PIXELS_PER_CODE =
    2U * OTM_CODE_COUNT * OTM_CELL_WIDTH * OTM_CELL_HEIGHT;
static constexpr size_t OTM_GRID_PIXELS =
    OTM_CODE_COUNT * OTM_PIXELS_PER_CODE;

static_assert((OTM_GRID_X0 & 1U) == 0 && (OTM_CELL_WIDTH & 1U) == 0,
              "OTP transition packed rectangles must be byte aligned");
static_assert(OTM_GRID_X0 + OTM_CODE_COUNT * OTM_CELL_WIDTH == 480U &&
                  480U <= EPD_CONTROLLER_WIDTH,
              "OTP transition grid exceeds a controller half");
static_assert(OTM_GRID_Y0 + OTM_CODE_COUNT * OTM_CELL_HEIGHT == 556U &&
                  556U <= EPD_HEIGHT,
              "OTP transition grid exceeds panel height");
static_assert(OTM_GRID_PIXELS == 458752U,
              "OTP transition grid pixel count changed");
static_assert(OTM_CS1_ORDER[0] == 0 && OTM_CS1_ORDER[1] == 1 &&
                  OTM_CS1_ORDER[2] == 2 && OTM_CS1_ORDER[3] == 3 &&
                  OTM_CS1_ORDER[4] == 4 && OTM_CS1_ORDER[5] == 5 &&
                  OTM_CS1_ORDER[6] == 6 && OTM_CS1_ORDER[7] == 7,
              "OTP transition CS1 order changed");
static_assert(OTM_CS2_ORDER[0] == 7 && OTM_CS2_ORDER[1] == 6 &&
                  OTM_CS2_ORDER[2] == 5 && OTM_CS2_ORDER[3] == 4 &&
                  OTM_CS2_ORDER[4] == 3 && OTM_CS2_ORDER[5] == 2 &&
                  OTM_CS2_ORDER[6] == 1 && OTM_CS2_ORDER[7] == 0,
              "OTP transition CS2 order changed");

static constexpr char OTM_PRIMER_FRAME_SHA256[] =
    "01529ea97197e5435370a0eb77a9cabff167c129237952b7a627a0f4903744dc";
static constexpr char OTM_PRIMER_CS1_DTM_SHA256[] =
    "208c3d8e03329bbba08bb54cb5f84a9568349295ed750c749aad0e29f259017f";
static constexpr char OTM_PRIMER_CS2_DTM_SHA256[] =
    "d66c999e89ace23dd3a112c53e9ca1f7bbbc984772e08af4359dcd843740cb1c";
static constexpr char OTM_TARGET_FRAME_SHA256[] =
    "e3f476f24176e4b5d0f196e6c3d912dabf5044f2cbac0a59bf63806d8d051a38";
static constexpr char OTM_TARGET_CS1_DTM_SHA256[] =
    "4a980b33107b1d0c1da6282952d5adf8c32334af46be8f2e82aceb4c30a94387";
static constexpr char OTM_TARGET_CS2_DTM_SHA256[] =
    "70d4f642ec98bb034de65fb350d51285e7f644dd42c5aa3e89de5b607f4643c3";
static constexpr char OTM_WHITE_FRAME_SHA256[] =
    "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d";
static constexpr char OTM_WHITE_DTM_SHA256[] =
    "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158";

static_assert(sizeof(OTM_PRIMER_FRAME_SHA256) == 65 &&
                  sizeof(OTM_PRIMER_CS1_DTM_SHA256) == 65 &&
                  sizeof(OTM_PRIMER_CS2_DTM_SHA256) == 65 &&
                  sizeof(OTM_TARGET_FRAME_SHA256) == 65 &&
                  sizeof(OTM_TARGET_CS1_DTM_SHA256) == 65 &&
                  sizeof(OTM_TARGET_CS2_DTM_SHA256) == 65 &&
                  sizeof(OTM_WHITE_FRAME_SHA256) == 65 &&
                  sizeof(OTM_WHITE_DTM_SHA256) == 65,
              "OTP transition SHA-256 identity length changed");

static constexpr const char *OTM_FAILURE_NONE = "none";
static constexpr const char *OTM_FAILURE_ALLOCATION = "allocation";
static constexpr const char *OTM_FAILURE_TRANSITION_DESIGN =
    "transition_design";
static constexpr const char *OTM_FAILURE_FRAME_BUILD = "frame_build";
static constexpr const char *OTM_FAILURE_FULL_SHA = "full_sha";
static constexpr const char *OTM_FAILURE_CS1_COMPUTE = "cs1_compute";
static constexpr const char *OTM_FAILURE_CS2_COMPUTE = "cs2_compute";
static constexpr const char *OTM_FAILURE_CS1_IDENTITY = "cs1_identity";
static constexpr const char *OTM_FAILURE_CS2_IDENTITY = "cs2_identity";
static constexpr const char *OTM_FAILURE_CASCADE_PREPARE =
    "cascade_prepare";
static constexpr const char *OTM_FAILURE_STREAM_IDENTITY =
    "stream_identity";
static constexpr const char *OTM_FAILURE_REFRESH_SEQUENCE =
    "refresh_sequence";

struct OtmRoleIdentity {
  uint32_t frameFnv1a;
  uint32_t cs1DtmFnv1a;
  uint32_t cs2DtmFnv1a;
  const char *frameSha256;
  const char *cs1DtmSha256;
  const char *cs2DtmSha256;
  uint32_t histogram[OTM_CODE_COUNT];
};

static constexpr OtmRoleIdentity OTM_IDENTITIES[3] = {
    {0x6FC94DC5UL,
     0x7DB815C5UL,
     0x3DB815C5UL,
     OTM_PRIMER_FRAME_SHA256,
     OTM_PRIMER_CS1_DTM_SHA256,
     OTM_PRIMER_CS2_DTM_SHA256,
     {57344, 212992, 57344, 57344, 57344, 57344, 57344, 57344}},
    {0x51794DC5UL,
     0x577715C5UL,
     0x645955C5UL,
     OTM_TARGET_FRAME_SHA256,
     OTM_TARGET_CS1_DTM_SHA256,
     OTM_TARGET_CS2_DTM_SHA256,
     {57344, 212992, 57344, 57344, 57344, 57344, 57344, 57344}},
    {0x13340DC5UL,
     0xB7A855C5UL,
     0xB7A855C5UL,
     OTM_WHITE_FRAME_SHA256,
     OTM_WHITE_DTM_SHA256,
     OTM_WHITE_DTM_SHA256,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
};

struct OtmDtmIdentity {
  uint32_t fnv1a = 0;
  uint8_t sha256[32] = {};
};

struct OtmValidation {
  const char *failureStage = OTM_FAILURE_NONE;
  int32_t failureCode = 0;
  uint32_t frameFnv1a = 0;
  OtmDtmIdentity cs1;
  OtmDtmIdentity cs2;
};

size_t otmRoleIndex(EpdOtpTransitionMatrixRole role) {
  return static_cast<size_t>(role);
}

bool otmRoleValid(EpdOtpTransitionMatrixRole role) {
  return otmRoleIndex(role) < 3;
}

bool otmOrderIsPermutation(const uint8_t *order) {
  if (!order) return false;
  bool seen[OTM_CODE_COUNT] = {};
  for (uint8_t index = 0; index < OTM_CODE_COUNT; ++index) {
    const uint8_t code = order[index];
    if (code >= OTM_CODE_COUNT || seen[code]) return false;
    seen[code] = true;
  }
  return true;
}

bool otmValidateTransitionDesign() {
  const uint8_t *orders[2] = {OTM_CS1_ORDER, OTM_CS2_ORDER};
  for (const uint8_t *order : orders) {
    if (!otmOrderIsPermutation(order)) return false;
    uint8_t coverage[OTM_CODE_COUNT][OTM_CODE_COUNT] = {};
    for (uint8_t row = 0; row < OTM_CODE_COUNT; ++row) {
      for (uint8_t column = 0; column < OTM_CODE_COUNT; ++column) {
        ++coverage[order[row]][order[column]];
      }
    }
    for (uint8_t oldCode = 0; oldCode < OTM_CODE_COUNT; ++oldCode) {
      for (uint8_t newCode = 0; newCode < OTM_CODE_COUNT; ++newCode) {
        if (coverage[oldCode][newCode] != 1) return false;
      }
    }
  }
  return true;
}

void otmFillRect(uint8_t *frame, uint16_t x0, uint16_t y0, uint8_t code) {
  static constexpr size_t kRowBytes = EPD_WIDTH / 2;
  const uint8_t pair = static_cast<uint8_t>((code << 4) | code);
  for (uint16_t y = y0; y < y0 + OTM_CELL_HEIGHT; ++y) {
    std::memset(frame + static_cast<size_t>(y) * kRowBytes + x0 / 2, pair,
                OTM_CELL_WIDTH / 2);
  }
}

bool otmBuildFrame(EpdOtpTransitionMatrixRole role, uint8_t *frame,
                   uint32_t *histogram) {
  if (!frame || !histogram || !otmRoleValid(role) ||
      !otmValidateTransitionDesign()) {
    return false;
  }
  std::memset(frame, 0x11, EPD_FRAME_BYTES);
  if (role != EpdOtpTransitionMatrixRole::White) {
    for (uint8_t controller = 0; controller < 2; ++controller) {
      const uint16_t halfOffset = controller ? EPD_CONTROLLER_WIDTH : 0;
      const uint8_t *order = controller ? OTM_CS2_ORDER : OTM_CS1_ORDER;
      for (uint8_t row = 0; row < OTM_CODE_COUNT; ++row) {
        for (uint8_t column = 0; column < OTM_CODE_COUNT; ++column) {
          const uint8_t code =
              role == EpdOtpTransitionMatrixRole::Primer ? order[row]
                                                         : order[column];
          const uint16_t x0 =
              halfOffset + OTM_GRID_X0 + column * OTM_CELL_WIDTH;
          const uint16_t y0 = OTM_GRID_Y0 + row * OTM_CELL_HEIGHT;
          otmFillRect(frame, x0, y0, code);
        }
      }
    }
  }

  std::memset(histogram, 0, OTM_CODE_COUNT * sizeof(uint32_t));
  for (size_t index = 0; index < EPD_FRAME_BYTES; ++index) {
    const uint8_t high = frame[index] >> 4;
    const uint8_t low = frame[index] & 0x0F;
    if (high >= OTM_CODE_COUNT || low >= OTM_CODE_COUNT) return false;
    ++histogram[high];
    ++histogram[low];
  }
  const OtmRoleIdentity &wanted = OTM_IDENTITIES[otmRoleIndex(role)];
  return std::memcmp(histogram, wanted.histogram, sizeof(wanted.histogram)) ==
         0;
}

bool otmDigestMatchesHex(const uint8_t digest[32], const char *expected) {
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

bool otmComputeDtmIdentity(const uint8_t *frame, bool secondController,
                           OtmDtmIdentity *identity, int32_t *errorCode) {
  if (!frame || !identity || !errorCode) return false;
  *identity = OtmDtmIdentity{};
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

bool otmValidateRole(EpdOtpTransitionMatrixRole role, uint8_t *frame,
                     OtmValidation *validation) {
  if (!frame || !validation || !otmRoleValid(role)) return false;
  *validation = OtmValidation{};
  if (!otmValidateTransitionDesign()) {
    validation->failureStage = OTM_FAILURE_TRANSITION_DESIGN;
    return false;
  }
  uint32_t histogram[OTM_CODE_COUNT] = {};
  if (!otmBuildFrame(role, frame, histogram)) {
    validation->failureStage = OTM_FAILURE_FRAME_BUILD;
    return false;
  }
  const OtmRoleIdentity &wanted = OTM_IDENTITIES[otmRoleIndex(role)];
  validation->frameFnv1a = fnv1a(frame, EPD_FRAME_BYTES);
  uint8_t frameDigest[32] = {};
  const int frameShaResult =
      mbedtls_sha256_ret(frame, EPD_FRAME_BYTES, frameDigest, 0);
  if (validation->frameFnv1a != wanted.frameFnv1a || frameShaResult != 0 ||
      !otmDigestMatchesHex(frameDigest, wanted.frameSha256)) {
    validation->failureStage = OTM_FAILURE_FULL_SHA;
    validation->failureCode = frameShaResult;
    return false;
  }
  if (!otmComputeDtmIdentity(frame, false, &validation->cs1,
                             &validation->failureCode)) {
    validation->failureStage = OTM_FAILURE_CS1_COMPUTE;
    return false;
  }
  if (!otmComputeDtmIdentity(frame, true, &validation->cs2,
                             &validation->failureCode)) {
    validation->failureStage = OTM_FAILURE_CS2_COMPUTE;
    return false;
  }
  if (validation->cs1.fnv1a != wanted.cs1DtmFnv1a ||
      !otmDigestMatchesHex(validation->cs1.sha256, wanted.cs1DtmSha256)) {
    validation->failureStage = OTM_FAILURE_CS1_IDENTITY;
    return false;
  }
  if (validation->cs2.fnv1a != wanted.cs2DtmFnv1a ||
      !otmDigestMatchesHex(validation->cs2.sha256, wanted.cs2DtmSha256)) {
    validation->failureStage = OTM_FAILURE_CS2_IDENTITY;
    return false;
  }
  return true;
}

}  // namespace

bool epdValidateCompiledOtpTransitionMatrixFixtures() {
  if (!otmValidateTransitionDesign()) return false;
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) return false;
  static constexpr EpdOtpTransitionMatrixRole kRoles[] = {
      EpdOtpTransitionMatrixRole::Primer,
      EpdOtpTransitionMatrixRole::Target,
      EpdOtpTransitionMatrixRole::White,
  };
  bool valid = true;
  for (const EpdOtpTransitionMatrixRole role : kRoles) {
    OtmValidation validation;
    valid = otmValidateRole(role, frame, &validation);
    if (!valid) break;
  }
  std::free(frame);
  return valid;
}

bool epdDisplayCompiledOtpTransitionMatrix(
    EpdOtpTransitionMatrixRole role) {
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  diagnosticReport.freePsramBefore = ESP.getFreePsram();
  diagnosticReport.largestPsramBlockBefore =
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
  if (!otmRoleValid(role)) {
    return epdRejectBeforePanelIo(started, OTM_FAILURE_FRAME_BUILD);
  }
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) {
    return epdRejectBeforePanelIo(started, OTM_FAILURE_ALLOCATION);
  }

  OtmValidation validation;
  const bool identityOk = otmValidateRole(role, frame, &validation);
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
                                        OTM_FAILURE_CASCADE_PREPARE);
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

  const OtmRoleIdentity &wanted = OTM_IDENTITIES[otmRoleIndex(role)];
  if (diagnosticReport.cs1DtmFnv1a != wanted.cs1DtmFnv1a ||
      diagnosticReport.cs2DtmFnv1a != wanted.cs2DtmFnv1a) {
    return epdFinishFailedOperationSafe(started,
                                        OTM_FAILURE_STREAM_IDENTITY);
  }
  setActiveControllers(true, true);
  const bool ok = epdSecondSettingAndRefresh();
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  if (!ok) epdRecordFailure(OTM_FAILURE_REFRESH_SEQUENCE);
  return epdFinishOperation(started, ok);
}
