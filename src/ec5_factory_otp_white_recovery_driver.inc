// Included only by epd_driver.cpp when
// MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY=1. This binary contains one fixed
// factory-OTP white action and no generated runtime-waveform include.

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600 &&
                  EPD_FRAME_BYTES == 307200 &&
                  EPD_CONTROLLER_FRAME_BYTES == 153600,
              "factory-OTP white recovery requires frozen panel geometry");
static_assert(EPD_CS1_SOURCE_HALF == 0 && !EPD_CS1_FLIP_X &&
                  !EPD_CS1_FLIP_Y && !EPD_CS1_NIBBLE_SWAP &&
                  EPD_CS2_SOURCE_HALF == 1 && !EPD_CS2_FLIP_X &&
                  !EPD_CS2_FLIP_Y && !EPD_CS2_NIBBLE_SWAP,
              "factory-OTP white recovery requires MAP_ORIENT_V1");

namespace {

static constexpr char FOWR_FRAME_SHA256[] =
    "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d";
static constexpr char FOWR_DTM_SHA256[] =
    "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158";
static constexpr uint32_t FOWR_FRAME_FNV1A = 0x13340DC5UL;
static constexpr uint32_t FOWR_DTM_FNV1A = 0xB7A855C5UL;
static constexpr const char *FOWR_FAILURE_ALLOCATION = "allocation";
static constexpr const char *FOWR_FAILURE_FRAME_IDENTITY = "full_sha";
static constexpr const char *FOWR_FAILURE_CS1_COMPUTE = "cs1_compute";
static constexpr const char *FOWR_FAILURE_CS2_COMPUTE = "cs2_compute";
static constexpr const char *FOWR_FAILURE_DTM_IDENTITY = "dtm_identity";
static constexpr const char *FOWR_FAILURE_CASCADE_PREPARE = "cascade_prepare";
static constexpr const char *FOWR_FAILURE_STREAM_IDENTITY = "stream_identity";
static constexpr const char *FOWR_FAILURE_REFRESH_SEQUENCE =
    "refresh_sequence";

struct FowrDtmIdentity {
  uint32_t fnv1a = 0;
  uint8_t sha256[32] = {};
};

struct FowrValidation {
  const char *failureStage = "none";
  int32_t failureCode = 0;
  uint32_t frameFnv1a = 0;
  FowrDtmIdentity cs1;
  FowrDtmIdentity cs2;
};

bool fowrDigestMatchesHex(const uint8_t digest[32], const char *expected) {
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

bool fowrComputeDtmIdentity(const uint8_t *frame, bool secondController,
                            FowrDtmIdentity *identity, int32_t *errorCode) {
  if (!frame || !identity || !errorCode) return false;
  *identity = FowrDtmIdentity{};
  *errorCode = 0;
  static constexpr size_t kFullRowBytes = EPD_WIDTH / 2;
  static constexpr size_t kControllerRowBytes = EPD_CONTROLLER_WIDTH / 2;
  uint8_t mappedRow[kControllerRowBytes] = {};
  const ControllerMapping &mapping =
      CONTROLLER_MAPPINGS[secondController ? 1 : 0];
  mbedtls_sha256_context context;
  mbedtls_sha256_init(&context);
  int result = mbedtls_sha256_starts_ret(&context, 0);
  uint32_t dtmHash = FNV1A_OFFSET_BASIS;
  for (uint16_t outputY = 0; result == 0 && outputY < EPD_HEIGHT; ++outputY) {
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
    result = mbedtls_sha256_update_ret(&context, mappedRow, sizeof(mappedRow));
  }
  if (result == 0)
    result = mbedtls_sha256_finish_ret(&context, identity->sha256);
  mbedtls_sha256_free(&context);
  if (result != 0) {
    *errorCode = result;
    return false;
  }
  identity->fnv1a = dtmHash;
  return true;
}

bool fowrValidateFrame(uint8_t *frame, FowrValidation *validation) {
  if (!frame || !validation) return false;
  *validation = FowrValidation{};
  std::memset(frame, 0x11, EPD_FRAME_BYTES);
  validation->frameFnv1a = fnv1a(frame, EPD_FRAME_BYTES);
  uint8_t frameDigest[32] = {};
  const int shaResult =
      mbedtls_sha256_ret(frame, EPD_FRAME_BYTES, frameDigest, 0);
  if (validation->frameFnv1a != FOWR_FRAME_FNV1A || shaResult != 0 ||
      !fowrDigestMatchesHex(frameDigest, FOWR_FRAME_SHA256)) {
    validation->failureStage = FOWR_FAILURE_FRAME_IDENTITY;
    validation->failureCode = shaResult;
    return false;
  }
  if (!fowrComputeDtmIdentity(frame, false, &validation->cs1,
                              &validation->failureCode)) {
    validation->failureStage = FOWR_FAILURE_CS1_COMPUTE;
    return false;
  }
  if (!fowrComputeDtmIdentity(frame, true, &validation->cs2,
                              &validation->failureCode)) {
    validation->failureStage = FOWR_FAILURE_CS2_COMPUTE;
    return false;
  }
  if (validation->cs1.fnv1a != FOWR_DTM_FNV1A ||
      validation->cs2.fnv1a != FOWR_DTM_FNV1A ||
      !fowrDigestMatchesHex(validation->cs1.sha256, FOWR_DTM_SHA256) ||
      !fowrDigestMatchesHex(validation->cs2.sha256, FOWR_DTM_SHA256)) {
    validation->failureStage = FOWR_FAILURE_DTM_IDENTITY;
    return false;
  }
  return true;
}

}  // namespace

bool epdValidateCompiledFactoryOtpWhiteRecoveryFixture() {
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) return false;
  FowrValidation validation;
  const bool valid = fowrValidateFrame(frame, &validation);
  std::free(frame);
  return valid;
}

bool epdDisplayCompiledFactoryOtpWhiteRecovery() {
  // epdBeginOperation is diagnostic-only. Frame and both DTM identities are
  // checked before SPI startup, controller selection, reset, or any command.
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  diagnosticReport.freePsramBefore = ESP.getFreePsram();
  diagnosticReport.largestPsramBlockBefore =
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame)
    return epdRejectBeforePanelIo(started, FOWR_FAILURE_ALLOCATION);
  FowrValidation validation;
  const bool identityOk = fowrValidateFrame(frame, &validation);
  diagnosticReport.inputFrameFnv1a = validation.frameFnv1a;
  diagnosticReport.cs1DtmFnv1a = validation.cs1.fnv1a;
  diagnosticReport.cs2DtmFnv1a = validation.cs2.fnv1a;
  if (!identityOk) {
    std::free(frame);
    return epdRejectBeforePanelIo(started, validation.failureStage,
                                  validation.failureCode);
  }

  // This is the existing validated factory ToBoth path: hardware reset,
  // PSR 5F,69, TRES 512x600 and E0=01 per controller. No runtime profile,
  // hidden LUT command, LUT register, voltage sweep, or timing override exists
  // in this fixture.
  if (!epdPrepareCascade(EPD_SPI_DEFAULT_HZ)) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started,
                                        FOWR_FAILURE_CASCADE_PREPARE);
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
  if (diagnosticReport.cs1DtmFnv1a != FOWR_DTM_FNV1A ||
      diagnosticReport.cs2DtmFnv1a != FOWR_DTM_FNV1A) {
    return epdFinishFailedOperationSafe(started,
                                        FOWR_FAILURE_STREAM_IDENTITY);
  }
  setActiveControllers(true, true);
  const bool ok = epdSecondSettingAndRefresh();
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  if (!ok) epdRecordFailure(FOWR_FAILURE_REFRESH_SEQUENCE);
  return epdFinishOperation(started, ok);
}
