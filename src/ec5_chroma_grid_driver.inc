// Included only by ec5_chroma_grid_epd_driver.cpp.  These four unique frames
// are exact compiled counterparts of tools/mf1750_ec5_chroma_grid.py.  The
// five-action sequence is white -> source -> mid -> target -> white.  It
// covers source 0..7, mid 4/7 and target 2/3/5/6 once per controller using the
// unchanged factory-OTP refresh path.  No caller-supplied frame, LUT,
// waveform, electrical parameter, timing, retry, recovery or auto-chain is
// exposed.

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600 &&
                  EPD_FRAME_BYTES == 307200 &&
                  EPD_CONTROLLER_WIDTH == 512 &&
                  EPD_CONTROLLER_FRAME_BYTES == 153600,
              "chroma grid requires frozen 1024x600 packed 4bpp");
static_assert(EPD_CS1_SOURCE_HALF == 0 && !EPD_CS1_FLIP_X &&
                  !EPD_CS1_FLIP_Y && !EPD_CS1_NIBBLE_SWAP &&
                  EPD_CS2_SOURCE_HALF == 1 && !EPD_CS2_FLIP_X &&
                  !EPD_CS2_FLIP_Y && !EPD_CS2_NIBBLE_SWAP,
              "chroma grid identities require MAP_ORIENT_V1");

namespace {

static constexpr uint8_t CG_ROLE_COUNT = 4;
static constexpr uint8_t CG_CODE_COUNT = 8;
static constexpr uint8_t CG_BACKGROUND_CODE = 1;
static constexpr uint16_t CG_CELL_WIDTH = 52;
static constexpr uint16_t CG_CELL_HEIGHT = 64;
static constexpr uint16_t CG_CELL_GAP_X = 4;
static constexpr uint16_t CG_CELL_GAP_Y = 4;
static constexpr uint16_t CG_GRID_X0 = 34;
static constexpr uint16_t CG_GRID_Y0 = 30;
static constexpr uint8_t CG_SOURCE_ORDER_CS1[CG_CODE_COUNT] = {
    0, 1, 2, 3, 4, 5, 6, 7,
};
static constexpr uint8_t CG_SOURCE_ORDER_CS2[CG_CODE_COUNT] = {
    7, 6, 5, 4, 3, 2, 1, 0,
};
static constexpr uint8_t CG_MID_CODES[CG_CODE_COUNT] = {
    4, 4, 4, 4, 7, 7, 7, 7,
};
static constexpr uint8_t CG_TARGET_CODES[CG_CODE_COUNT] = {
    2, 3, 5, 6, 2, 3, 5, 6,
};
static constexpr size_t CG_CELL_PIXELS = CG_CELL_WIDTH * CG_CELL_HEIGHT;
static constexpr size_t CG_GRID_PIXELS =
    2U * CG_CODE_COUNT * CG_CODE_COUNT * CG_CELL_PIXELS;

static_assert((CG_GRID_X0 & 1U) == 0 && (CG_CELL_WIDTH & 1U) == 0,
              "chroma grid packed cells must be byte aligned");
static_assert(CG_GRID_X0 + 8 * CG_CELL_WIDTH + 7 * CG_CELL_GAP_X == 478 &&
                  478 <= EPD_CONTROLLER_WIDTH,
              "chroma grid exceeds a controller half");
static_assert(CG_GRID_Y0 + 8 * CG_CELL_HEIGHT + 7 * CG_CELL_GAP_Y == 570 &&
                  570 <= EPD_HEIGHT,
              "chroma grid exceeds panel height");
static_assert(CG_GRID_PIXELS == 425984U,
              "chroma grid coloured pixel count changed");

static constexpr char CG_WHITE_FRAME_SHA256[] =
    "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d";
static constexpr char CG_WHITE_DTM_SHA256[] =
    "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158";
static constexpr char CG_SOURCE_FRAME_SHA256[] =
    "213d3eab11966579f8cab7577dff315897f96a72e9030a236f60ca899295b8de";
static constexpr char CG_SOURCE_CS1_DTM_SHA256[] =
    "0eba448b460d31d3d28a6d9e6d62fa0193f6eaabe769d9fc846658c4b0ac64e2";
static constexpr char CG_SOURCE_CS2_DTM_SHA256[] =
    "8ae4ae3058ab1ffab4152f4c2e714e88fce7a0c4ace3bf472c59b7a520119079";
static constexpr char CG_MID_FRAME_SHA256[] =
    "8047a36612272c3e5e03717b00184e151d16fe67caf972c70ff0caea88d63054";
static constexpr char CG_MID_CS1_DTM_SHA256[] =
    "c2143d36c7a2be633c6e0fa63bf2e63cc08533a428cf219e3246891e2d18b987";
static constexpr char CG_MID_CS2_DTM_SHA256[] =
    "b17caf38ae1aefcd01b63675cf0f4027850bc65c8f3f590339aa29a55c53b8cd";
static constexpr char CG_TARGET_FRAME_SHA256[] =
    "c2e5289bfa44ffba8daf374edd70e34216ea13e08a3e58764feed9f13efa2036";
static constexpr char CG_TARGET_CS1_DTM_SHA256[] =
    "26535f9244d6af9c0899ec851cb84b469f01d949baf9602988d98c2377e1a72f";
static constexpr char CG_TARGET_CS2_DTM_SHA256[] =
    "3430064d6abd1273837db198e2901f20512726794b64e6f32886c5e9fbb5b57c";

static constexpr const char *CG_FAILURE_NONE = "none";
static constexpr const char *CG_FAILURE_ALLOCATION = "allocation";
static constexpr const char *CG_FAILURE_LAYOUT_DESIGN = "layout_design";
static constexpr const char *CG_FAILURE_FRAME_BUILD = "frame_build";
static constexpr const char *CG_FAILURE_HISTOGRAM = "histogram";
static constexpr const char *CG_FAILURE_FULL_SHA = "full_sha";
static constexpr const char *CG_FAILURE_CS1_COMPUTE = "cs1_compute";
static constexpr const char *CG_FAILURE_CS2_COMPUTE = "cs2_compute";
static constexpr const char *CG_FAILURE_CS1_IDENTITY = "cs1_identity";
static constexpr const char *CG_FAILURE_CS2_IDENTITY = "cs2_identity";
static constexpr const char *CG_FAILURE_CASCADE_PREPARE =
    "cascade_prepare";
static constexpr const char *CG_FAILURE_STREAM_IDENTITY =
    "stream_identity";
static constexpr const char *CG_FAILURE_REFRESH_SEQUENCE =
    "refresh_sequence";

struct CgRoleIdentity {
  uint32_t frameFnv1a;
  uint32_t cs1DtmFnv1a;
  uint32_t cs2DtmFnv1a;
  const char *frameSha256;
  const char *cs1DtmSha256;
  const char *cs2DtmSha256;
  uint32_t histogram[CG_CODE_COUNT];
};

static constexpr CgRoleIdentity CG_IDENTITIES[CG_ROLE_COUNT] = {
    {0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     CG_WHITE_FRAME_SHA256, CG_WHITE_DTM_SHA256, CG_WHITE_DTM_SHA256,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {0xD1A5ADC5UL, 0xF9AFC5C5UL, 0x0AAFC5C5UL,
     CG_SOURCE_FRAME_SHA256, CG_SOURCE_CS1_DTM_SHA256,
     CG_SOURCE_CS2_DTM_SHA256,
     {53248, 241664, 53248, 53248, 53248, 53248, 53248, 53248}},
    {0x6163EDC5UL, 0x33D245C5UL, 0x23AE45C5UL,
     CG_MID_FRAME_SHA256, CG_MID_CS1_DTM_SHA256,
     CG_MID_CS2_DTM_SHA256,
     {0, 188416, 0, 0, 212992, 0, 0, 212992}},
    {0xD3FE2DC5UL, 0x9E5C65C5UL, 0xD0BE65C5UL,
     CG_TARGET_FRAME_SHA256, CG_TARGET_CS1_DTM_SHA256,
     CG_TARGET_CS2_DTM_SHA256,
     {0, 188416, 106496, 106496, 0, 106496, 106496, 0}},
};

struct CgDtmIdentity {
  uint32_t fnv1a = 0;
  uint8_t sha256[32] = {};
};

struct CgValidation {
  const char *failureStage = CG_FAILURE_NONE;
  int32_t failureCode = 0;
  uint32_t frameFnv1a = 0;
  CgDtmIdentity cs1;
  CgDtmIdentity cs2;
};

size_t cgRoleIndex(EpdChromaGridRole role) {
  return static_cast<size_t>(role);
}

bool cgRoleValid(EpdChromaGridRole role) {
  return cgRoleIndex(role) < CG_ROLE_COUNT;
}

bool cgValidateLayoutDesign() {
  if (CG_BACKGROUND_CODE >= CG_CODE_COUNT) return false;
  for (uint8_t controller = 0; controller < 2; ++controller) {
    uint8_t coverage[CG_CODE_COUNT][2][4] = {};
    const uint8_t *sourceOrder =
        controller == 0 ? CG_SOURCE_ORDER_CS1 : CG_SOURCE_ORDER_CS2;
    for (uint8_t row = 0; row < CG_CODE_COUNT; ++row) {
      for (uint8_t column = 0; column < CG_CODE_COUNT; ++column) {
        const uint8_t combination =
            controller == 0 ? column : CG_CODE_COUNT - 1 - column;
        const uint8_t midIndex = combination < 4 ? 0 : 1;
        const uint8_t targetIndex = combination % 4;
        ++coverage[sourceOrder[row]][midIndex][targetIndex];
      }
    }
    for (uint8_t source = 0; source < CG_CODE_COUNT; ++source) {
      for (uint8_t mid = 0; mid < 2; ++mid) {
        for (uint8_t target = 0; target < 4; ++target) {
          if (coverage[source][mid][target] != 1) return false;
        }
      }
    }
  }
  return true;
}

void cgFillCell(uint8_t *frame, uint8_t controller, uint8_t row,
                uint8_t column, uint8_t code) {
  const size_t rowBytes = EPD_WIDTH / 2;
  const uint16_t halfOffset = controller * EPD_CONTROLLER_WIDTH;
  const uint16_t x0 = halfOffset + CG_GRID_X0 +
                      column * (CG_CELL_WIDTH + CG_CELL_GAP_X);
  const uint16_t y0 =
      CG_GRID_Y0 + row * (CG_CELL_HEIGHT + CG_CELL_GAP_Y);
  const uint8_t pair = static_cast<uint8_t>((code << 4) | code);
  for (uint16_t y = y0; y < y0 + CG_CELL_HEIGHT; ++y) {
    std::memset(frame + static_cast<size_t>(y) * rowBytes + x0 / 2,
                pair, CG_CELL_WIDTH / 2);
  }
}

bool cgBuildFrame(EpdChromaGridRole role, uint8_t *frame,
                   uint32_t *histogram) {
  if (!frame || !histogram || !cgRoleValid(role) ||
      !cgValidateLayoutDesign()) {
    return false;
  }
  std::memset(frame, 0x11, EPD_FRAME_BYTES);
  if (role != EpdChromaGridRole::White) {
    for (uint8_t controller = 0; controller < 2; ++controller) {
      const uint8_t *sourceOrder =
          controller == 0 ? CG_SOURCE_ORDER_CS1 : CG_SOURCE_ORDER_CS2;
      for (uint8_t row = 0; row < CG_CODE_COUNT; ++row) {
        for (uint8_t column = 0; column < CG_CODE_COUNT; ++column) {
          const uint8_t combination =
              controller == 0 ? column : CG_CODE_COUNT - 1 - column;
          uint8_t code = sourceOrder[row];
          if (role == EpdChromaGridRole::Mid) {
            code = CG_MID_CODES[combination];
          } else if (role == EpdChromaGridRole::Target) {
            code = CG_TARGET_CODES[combination];
          }
          cgFillCell(frame, controller, row, column, code);
        }
      }
    }
  }

  std::memset(histogram, 0, CG_CODE_COUNT * sizeof(uint32_t));
  for (size_t index = 0; index < EPD_FRAME_BYTES; ++index) {
    const uint8_t high = frame[index] >> 4;
    const uint8_t low = frame[index] & 0x0F;
    if (high >= CG_CODE_COUNT || low >= CG_CODE_COUNT) return false;
    ++histogram[high];
    ++histogram[low];
  }
  return true;
}

bool cgDigestMatchesHex(const uint8_t digest[32], const char *expected) {
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

bool cgComputeDtmIdentity(const uint8_t *frame, bool secondController,
                           CgDtmIdentity *identity, int32_t *errorCode) {
  if (!frame || !identity || !errorCode) return false;
  *identity = CgDtmIdentity{};
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

bool cgValidateRole(EpdChromaGridRole role, uint8_t *frame,
                     CgValidation *validation) {
  if (!frame || !validation || !cgRoleValid(role)) return false;
  *validation = CgValidation{};
  if (!cgValidateLayoutDesign()) {
    validation->failureStage = CG_FAILURE_LAYOUT_DESIGN;
    return false;
  }
  uint32_t histogram[CG_CODE_COUNT] = {};
  if (!cgBuildFrame(role, frame, histogram)) {
    validation->failureStage = CG_FAILURE_FRAME_BUILD;
    return false;
  }
  const CgRoleIdentity &wanted = CG_IDENTITIES[cgRoleIndex(role)];
  if (std::memcmp(histogram, wanted.histogram, sizeof(wanted.histogram)) !=
      0) {
    validation->failureStage = CG_FAILURE_HISTOGRAM;
    return false;
  }

  validation->frameFnv1a = fnv1a(frame, EPD_FRAME_BYTES);
  uint8_t frameDigest[32] = {};
  const int frameShaResult =
      mbedtls_sha256_ret(frame, EPD_FRAME_BYTES, frameDigest, 0);
  if (validation->frameFnv1a != wanted.frameFnv1a || frameShaResult != 0 ||
      !cgDigestMatchesHex(frameDigest, wanted.frameSha256)) {
    validation->failureStage = CG_FAILURE_FULL_SHA;
    validation->failureCode = frameShaResult;
    return false;
  }
  if (!cgComputeDtmIdentity(frame, false, &validation->cs1,
                             &validation->failureCode)) {
    validation->failureStage = CG_FAILURE_CS1_COMPUTE;
    return false;
  }
  if (!cgComputeDtmIdentity(frame, true, &validation->cs2,
                             &validation->failureCode)) {
    validation->failureStage = CG_FAILURE_CS2_COMPUTE;
    return false;
  }
  if (validation->cs1.fnv1a != wanted.cs1DtmFnv1a ||
      !cgDigestMatchesHex(validation->cs1.sha256, wanted.cs1DtmSha256)) {
    validation->failureStage = CG_FAILURE_CS1_IDENTITY;
    return false;
  }
  if (validation->cs2.fnv1a != wanted.cs2DtmFnv1a ||
      !cgDigestMatchesHex(validation->cs2.sha256, wanted.cs2DtmSha256)) {
    validation->failureStage = CG_FAILURE_CS2_IDENTITY;
    return false;
  }
  return true;
}

}  // namespace

bool epdValidateCompiledChromaGridFixtures() {
  if (!cgValidateLayoutDesign()) return false;
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) return false;
  static constexpr EpdChromaGridRole kRoles[] = {
      EpdChromaGridRole::White,
      EpdChromaGridRole::Source,
      EpdChromaGridRole::Mid,
      EpdChromaGridRole::Target,
  };
  bool valid = true;
  for (const EpdChromaGridRole role : kRoles) {
    CgValidation validation;
    valid = cgValidateRole(role, frame, &validation);
    if (!valid) break;
  }
  std::free(frame);
  return valid;
}

bool epdDisplayCompiledChromaGrid(EpdChromaGridRole role) {
  // epdBeginOperation initializes diagnostics only.  GPIO/SPI/panel setup is
  // still behind the complete allocation and identity gate below.
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  diagnosticReport.freePsramBefore = ESP.getFreePsram();
  diagnosticReport.largestPsramBlockBefore =
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
  if (!cgRoleValid(role)) {
    return epdRejectBeforePanelIo(started, CG_FAILURE_FRAME_BUILD);
  }
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) {
    return epdRejectBeforePanelIo(started, CG_FAILURE_ALLOCATION);
  }

  CgValidation validation;
  const bool identityOk = cgValidateRole(role, frame, &validation);
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
                                        CG_FAILURE_CASCADE_PREPARE);
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

  const CgRoleIdentity &wanted = CG_IDENTITIES[cgRoleIndex(role)];
  if (diagnosticReport.cs1DtmFnv1a != wanted.cs1DtmFnv1a ||
      diagnosticReport.cs2DtmFnv1a != wanted.cs2DtmFnv1a) {
    return epdFinishFailedOperationSafe(started,
                                        CG_FAILURE_STREAM_IDENTITY);
  }
  setActiveControllers(true, true);
  const bool ok = epdSecondSettingAndRefresh();
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  if (!ok) epdRecordFailure(CG_FAILURE_REFRESH_SEQUENCE);
  return epdFinishOperation(started, ok);
}
