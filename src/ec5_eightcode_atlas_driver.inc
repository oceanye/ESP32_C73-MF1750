// Included only by epd_driver.cpp when MF1750_ENABLE_EIGHTCODE_ATLAS=1.
// This file deliberately relies on the private cascade helpers in that
// translation unit. No raw frame, caller-selected code, LUT, retry, or
// recovery path is exposed.

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600,
              "eight-code atlas requires the frozen 1024x600 panel");
static_assert(EPD_CS1_SOURCE_HALF == 0 && !EPD_CS1_FLIP_X &&
                  !EPD_CS1_FLIP_Y && !EPD_CS1_NIBBLE_SWAP &&
                  EPD_CS2_SOURCE_HALF == 1 && !EPD_CS2_FLIP_X &&
                  !EPD_CS2_FLIP_Y && !EPD_CS2_NIBBLE_SWAP,
              "eight-code atlas requires MAP_ORIENT_V1");

namespace {

static constexpr uint16_t EC8_PATCH_SIDE = 64;
static constexpr uint16_t EC8_BORDER = 2;
static constexpr uint16_t EC8_LOCAL_X[4] = {48, 160, 272, 384};
static constexpr uint16_t EC8_Y0[2] = {190, 346};
static constexpr uint8_t EC8_CS1_ORDER[8] = {0, 1, 2, 3, 4, 5, 6, 7};
static constexpr uint8_t EC8_CS2_ORDER[8] = {7, 6, 5, 4, 3, 2, 1, 0};
static constexpr size_t EC8_PAYLOAD_PIXELS_PER_CODE = 8192;

// Runtime-addressable ELF symbols. The offline gate reads these exact local
// objects from .symtab; equal bytes elsewhere in the image are irrelevant.
static const uint8_t EC8_ATLAS_FRAME_SHA256[32] = {
    0x77, 0x45, 0x4F, 0xE9, 0x33, 0xF7, 0x9B, 0x30,
    0x1E, 0xCB, 0x55, 0xB2, 0xA0, 0x65, 0x27, 0x6E,
    0x0F, 0x4F, 0xE1, 0x22, 0xBF, 0x84, 0x16, 0x74,
    0x6F, 0x71, 0xF9, 0xB9, 0x2E, 0x90, 0x63, 0x7B,
};
static const uint8_t EC8_ATLAS_CS1_DTM_SHA256[32] = {
    0x85, 0xCD, 0x56, 0x83, 0xAE, 0x2D, 0x9C, 0x5B,
    0xF9, 0xE9, 0x7B, 0xEA, 0x53, 0x9A, 0x90, 0x5C,
    0xDF, 0x24, 0x49, 0x83, 0xBE, 0xFA, 0xEB, 0xA7,
    0xE5, 0x32, 0x1A, 0xA7, 0x3E, 0xD7, 0x74, 0xF7,
};
static const uint8_t EC8_ATLAS_CS2_DTM_SHA256[32] = {
    0xCF, 0xB5, 0xBB, 0xA8, 0x2A, 0x94, 0x21, 0xE4,
    0xC3, 0xA1, 0x3E, 0xD1, 0x07, 0x31, 0x10, 0x5D,
    0x78, 0x85, 0x2A, 0x05, 0x23, 0x8C, 0xA5, 0x2D,
    0xDF, 0x3B, 0xD9, 0xCD, 0xD0, 0x99, 0xB9, 0x43,
};
static const uint8_t EC8_U04_FRAME_SHA256[32] = {
    0x25, 0x34, 0x0F, 0x6A, 0x4A, 0x0B, 0xC7, 0x1E,
    0xC9, 0x5B, 0x74, 0xE3, 0x49, 0xE7, 0x9B, 0x4A,
    0x9E, 0x31, 0x7C, 0x41, 0x56, 0x16, 0xB6, 0xE0,
    0x8F, 0x43, 0xA5, 0x4D, 0xB6, 0x2B, 0x8F, 0x22,
};
static const uint8_t EC8_U04_DTM_SHA256[32] = {
    0xBA, 0x8C, 0xFA, 0x2F, 0xF4, 0xE0, 0xC4, 0xC4,
    0xB4, 0x33, 0x02, 0x55, 0x1D, 0xE0, 0x97, 0xCF,
    0xA8, 0x90, 0x20, 0x07, 0xB8, 0xC8, 0xED, 0xBD,
    0x60, 0xB8, 0xAC, 0x86, 0x25, 0x00, 0x1F, 0xBF,
};
static const uint8_t EC8_U07_FRAME_SHA256[32] = {
    0xFD, 0x02, 0x3D, 0x9B, 0x61, 0x8F, 0xF4, 0x64,
    0xCC, 0x48, 0x92, 0x8E, 0x0B, 0x8C, 0x59, 0x8E,
    0xB1, 0xAD, 0xFA, 0x9E, 0xE0, 0x45, 0x1A, 0xE0,
    0x7E, 0x46, 0x66, 0xD4, 0xA8, 0x3F, 0xE7, 0x2C,
};
static const uint8_t EC8_U07_DTM_SHA256[32] = {
    0x67, 0x15, 0xDA, 0xAD, 0x28, 0xD5, 0xB7, 0xE2,
    0x18, 0x92, 0x22, 0x1D, 0x17, 0x8E, 0x30, 0x11,
    0xB3, 0xC5, 0x57, 0x4B, 0x34, 0x1F, 0x9F, 0x30,
    0x02, 0x7A, 0xAE, 0x39, 0x4F, 0x79, 0x5E, 0xD9,
};
static const uint8_t EC8_WHITE_FRAME_SHA256[32] = {
    0x91, 0xF1, 0xED, 0x45, 0xBF, 0x60, 0x9A, 0x23,
    0xFB, 0xDC, 0xFD, 0x03, 0x70, 0x27, 0xC2, 0xE2,
    0x71, 0x48, 0x4F, 0x58, 0x32, 0x1A, 0x47, 0x07,
    0xE8, 0x89, 0xD1, 0x18, 0x59, 0xD8, 0x45, 0x3D,
};
static const uint8_t EC8_WHITE_DTM_SHA256[32] = {
    0x8B, 0x8F, 0xE0, 0x4D, 0x4D, 0x48, 0xAB, 0x9D,
    0x1A, 0xBB, 0x4A, 0x85, 0x8F, 0x68, 0x54, 0x41,
    0x64, 0xD1, 0xA0, 0x91, 0x99, 0x86, 0x64, 0xEE,
    0xF0, 0x68, 0x69, 0xC0, 0x98, 0xA7, 0x81, 0x58,
};

static constexpr const char *EC8_FAILURE_NONE = "none";
static constexpr const char *EC8_FAILURE_ALLOCATION = "allocation";
static constexpr const char *EC8_FAILURE_FRAME_BUILD = "frame_build";
static constexpr const char *EC8_FAILURE_FULL_SHA = "full_sha";
static constexpr const char *EC8_FAILURE_CS1_COMPUTE = "cs1_compute";
static constexpr const char *EC8_FAILURE_CS2_COMPUTE = "cs2_compute";
static constexpr const char *EC8_FAILURE_CS1_IDENTITY = "cs1_identity";
static constexpr const char *EC8_FAILURE_CS2_IDENTITY = "cs2_identity";
static constexpr const char *EC8_FAILURE_CASCADE_PREPARE =
    "cascade_prepare";
static constexpr const char *EC8_FAILURE_STREAM_IDENTITY =
    "stream_identity";
static constexpr const char *EC8_FAILURE_REFRESH_SEQUENCE =
    "refresh_sequence";

struct EightCodeRoleIdentity {
  uint32_t frameFnv1a;
  uint32_t cs1Fnv1a;
  uint32_t cs2Fnv1a;
  const uint8_t *frameSha256;
  const uint8_t *cs1Sha256;
  const uint8_t *cs2Sha256;
  uint32_t histogram[8];
};

static const EightCodeRoleIdentity EC8_IDENTITIES[4] = {
    {0xCE553145UL,
     0x639C1785UL,
     0x1BADB785UL,
     EC8_ATLAS_FRAME_SHA256,
     EC8_ATLAS_CS1_DTM_SHA256,
     EC8_ATLAS_CS2_DTM_SHA256,
     {16640, 548608, 8192, 8192, 8192, 8192, 8192, 8192}},
    {0x7DFB1145UL,
     0x21B7D785UL,
     0x21B7D785UL,
     EC8_U04_FRAME_SHA256,
     EC8_U04_DTM_SHA256,
     EC8_U04_DTM_SHA256,
     {8448, 540416, 0, 0, 65536, 0, 0, 0}},
    {0x050A9145UL,
     0x253F9785UL,
     0x253F9785UL,
     EC8_U07_FRAME_SHA256,
     EC8_U07_DTM_SHA256,
     EC8_U07_DTM_SHA256,
     {8448, 540416, 0, 0, 0, 0, 0, 65536}},
    {0x13340DC5UL,
     0xB7A855C5UL,
     0xB7A855C5UL,
     EC8_WHITE_FRAME_SHA256,
     EC8_WHITE_DTM_SHA256,
     EC8_WHITE_DTM_SHA256,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
};

struct EightCodeDtmIdentity {
  uint32_t fnv1a = 0;
  uint8_t sha256[32] = {};
};

struct EightCodeValidation {
  const char *failureStage = EC8_FAILURE_NONE;
  int32_t failureCode = 0;
  uint32_t frameFnv1a = 0;
  EightCodeDtmIdentity cs1;
  EightCodeDtmIdentity cs2;
};

size_t ec8RoleIndex(EpdEightCodeAtlasRole role) {
  return static_cast<size_t>(role);
}

bool ec8RoleValid(EpdEightCodeAtlasRole role) {
  return ec8RoleIndex(role) < 4;
}

void ec8FillRect(uint8_t *frame, uint16_t x0, uint16_t y0, uint16_t width,
                 uint16_t height, uint8_t code) {
  static constexpr size_t kRowBytes = EPD_WIDTH / 2;
  const uint8_t pair = static_cast<uint8_t>((code << 4) | code);
  for (uint16_t y = y0; y < y0 + height; ++y) {
    std::memset(frame + static_cast<size_t>(y) * kRowBytes + x0 / 2, pair,
                width / 2);
  }
}

bool ec8BuildFrame(EpdEightCodeAtlasRole role, uint8_t *frame,
                   uint32_t *histogram) {
  if (!frame || !histogram || !ec8RoleValid(role)) return false;
  std::memset(frame, 0x11, EPD_FRAME_BYTES);
  if (role != EpdEightCodeAtlasRole::White) {
    for (uint8_t controller = 0; controller < 2; ++controller) {
      const uint16_t halfOffset = controller ? EPD_CONTROLLER_WIDTH : 0;
      const uint8_t *order = controller ? EC8_CS2_ORDER : EC8_CS1_ORDER;
      for (uint8_t slot = 0; slot < 8; ++slot) {
        const uint8_t row = slot / 4;
        const uint8_t column = slot % 4;
        const uint16_t x0 = halfOffset + EC8_LOCAL_X[column];
        const uint16_t y0 = EC8_Y0[row];
        ec8FillRect(frame, x0 - EC8_BORDER, y0 - EC8_BORDER,
                    EC8_PATCH_SIDE + 2 * EC8_BORDER,
                    EC8_PATCH_SIDE + 2 * EC8_BORDER, EPD_COLOR_BLACK);
        uint8_t code = order[slot];
        if (role == EpdEightCodeAtlasRole::TargetU04) code = 4;
        if (role == EpdEightCodeAtlasRole::TargetU07) code = 7;
        ec8FillRect(frame, x0, y0, EC8_PATCH_SIDE, EC8_PATCH_SIDE, code);
      }
    }
  }

  std::memset(histogram, 0, 8 * sizeof(uint32_t));
  for (size_t index = 0; index < EPD_FRAME_BYTES; ++index) {
    const uint8_t high = frame[index] >> 4;
    const uint8_t low = frame[index] & 0x0F;
    if (high > 7 || low > 7) return false;
    ++histogram[high];
    ++histogram[low];
  }
  const EightCodeRoleIdentity &wanted = EC8_IDENTITIES[ec8RoleIndex(role)];
  for (uint8_t code = 0; code < 8; ++code) {
    if (histogram[code] != wanted.histogram[code]) return false;
  }
  if (role == EpdEightCodeAtlasRole::Atlas) {
    // Payload equality is independent of background/outline histogram.
    for (uint8_t code = 0; code < 8; ++code) {
      size_t payload = 0;
      for (uint8_t controller = 0; controller < 2; ++controller) {
        const uint8_t *order = controller ? EC8_CS2_ORDER : EC8_CS1_ORDER;
        for (uint8_t slot = 0; slot < 8; ++slot) {
          if (order[slot] == code) payload += EC8_PATCH_SIDE * EC8_PATCH_SIDE;
        }
      }
      if (payload != EC8_PAYLOAD_PIXELS_PER_CODE) return false;
    }
  }
  return true;
}

bool ec8ComputeDtmIdentity(const uint8_t *frame, bool secondController,
                           EightCodeDtmIdentity *identity,
                           int32_t *errorCode) {
  if (!frame || !identity || !errorCode) return false;
  *identity = EightCodeDtmIdentity{};
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
      if (mapping.flipX != mapping.nibbleSwap)
        value = static_cast<uint8_t>((value << 4) | (value >> 4));
      mappedRow[outputByte] = value;
      dtmHash = fnv1aUpdate(dtmHash, value);
    }
    const int result =
        mbedtls_sha256_update_ret(&context, mappedRow, sizeof(mappedRow));
    if (result != 0) {
      *errorCode = result;
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

bool ec8ValidateRole(EpdEightCodeAtlasRole role, uint8_t *frame,
                     EightCodeValidation *validation) {
  if (!frame || !validation || !ec8RoleValid(role)) return false;
  *validation = EightCodeValidation{};
  uint32_t histogram[8] = {};
  if (!ec8BuildFrame(role, frame, histogram)) {
    validation->failureStage = EC8_FAILURE_FRAME_BUILD;
    return false;
  }
  const EightCodeRoleIdentity &wanted = EC8_IDENTITIES[ec8RoleIndex(role)];
  validation->frameFnv1a = fnv1a(frame, EPD_FRAME_BYTES);
  uint8_t frameDigest[32] = {};
  const int fullShaResult =
      mbedtls_sha256_ret(frame, EPD_FRAME_BYTES, frameDigest, 0);
  if (validation->frameFnv1a != wanted.frameFnv1a || fullShaResult != 0 ||
      std::memcmp(frameDigest, wanted.frameSha256, sizeof(frameDigest)) != 0) {
    validation->failureStage = EC8_FAILURE_FULL_SHA;
    validation->failureCode = fullShaResult;
    return false;
  }
  if (!ec8ComputeDtmIdentity(frame, false, &validation->cs1,
                             &validation->failureCode)) {
    validation->failureStage = EC8_FAILURE_CS1_COMPUTE;
    return false;
  }
  if (!ec8ComputeDtmIdentity(frame, true, &validation->cs2,
                             &validation->failureCode)) {
    validation->failureStage = EC8_FAILURE_CS2_COMPUTE;
    return false;
  }
  if (validation->cs1.fnv1a != wanted.cs1Fnv1a ||
      std::memcmp(validation->cs1.sha256, wanted.cs1Sha256, 32) != 0) {
    validation->failureStage = EC8_FAILURE_CS1_IDENTITY;
    return false;
  }
  if (validation->cs2.fnv1a != wanted.cs2Fnv1a ||
      std::memcmp(validation->cs2.sha256, wanted.cs2Sha256, 32) != 0) {
    validation->failureStage = EC8_FAILURE_CS2_IDENTITY;
    return false;
  }
  return true;
}

}  // namespace

bool epdValidateCompiledEightCodeAtlasFixtures() {
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) return false;
  bool valid = true;
  for (uint8_t index = 0; valid && index < 4; ++index) {
    EightCodeValidation validation;
    valid = ec8ValidateRole(static_cast<EpdEightCodeAtlasRole>(index), frame,
                            &validation);
  }
  std::free(frame);
  return valid;
}

bool epdDisplayCompiledEightCodeAtlas(EpdEightCodeAtlasRole role) {
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  diagnosticReport.freePsramBefore = ESP.getFreePsram();
  diagnosticReport.largestPsramBlockBefore =
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
  if (!ec8RoleValid(role))
    return epdRejectBeforePanelIo(started, EC8_FAILURE_FRAME_BUILD);
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame)
    return epdRejectBeforePanelIo(started, EC8_FAILURE_ALLOCATION);

  EightCodeValidation validation;
  const bool identityOk = ec8ValidateRole(role, frame, &validation);
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
                                        EC8_FAILURE_CASCADE_PREPARE);
  }
  const uint32_t cs1Started = millis();
  diagnosticReport.cs1DtmFnv1a = epdStreamPackedFrameController(frame, false);
  diagnosticReport.cs1UploadMs = millis() - cs1Started;
  const uint32_t cs2Started = millis();
  diagnosticReport.cs2DtmFnv1a = epdStreamPackedFrameController(frame, true);
  diagnosticReport.cs2UploadMs = millis() - cs2Started;
  diagnosticReport.mappingApplied = true;
  std::free(frame);

  const EightCodeRoleIdentity &wanted = EC8_IDENTITIES[ec8RoleIndex(role)];
  if (diagnosticReport.cs1DtmFnv1a != wanted.cs1Fnv1a ||
      diagnosticReport.cs2DtmFnv1a != wanted.cs2Fnv1a) {
    return epdFinishFailedOperationSafe(started,
                                        EC8_FAILURE_STREAM_IDENTITY);
  }
  setActiveControllers(true, true);
  const bool ok = epdSecondSettingAndRefresh();
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  if (!ok) epdRecordFailure(EC8_FAILURE_REFRESH_SEQUENCE);
  return epdFinishOperation(started, ok);
}
