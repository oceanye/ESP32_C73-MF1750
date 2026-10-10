// Included only by ec5_h3_c23_matched_control_driver.cpp. This is the
// header-matched negative control for the frozen WF23_25 empirical H3 action.
// It has no runtime-waveform command, payload, loader, ingress, or selector.

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600,
              "C23 matched control requires the frozen 1024x600 panel");
static_assert(EPD_CONTROLLER_WIDTH == 512 &&
                  EPD_CONTROLLER_FRAME_BYTES == 153600,
              "C23 matched control requires two 512x600 controllers");
static_assert(EPD_CS1_SOURCE_HALF == 0 && !EPD_CS1_FLIP_X &&
                  !EPD_CS1_FLIP_Y && !EPD_CS1_NIBBLE_SWAP &&
                  EPD_CS2_SOURCE_HALF == 1 && !EPD_CS2_FLIP_X &&
                  !EPD_CS2_FLIP_Y && !EPD_CS2_NIBBLE_SWAP,
              "C23 matched control requires MAP_ORIENT_V1");

namespace {

enum class H3C23FixedCommand : uint8_t {
  PanelSetting = 0x00,
  PowerSetting = 0x01,
  Pll = 0x30,
  Resolution = 0x61,
  HiddenLutEnable = 0xE9,
};

static constexpr uint8_t H3C23_RUNTIME_PSR[2] = {0x5F, 0xE9};
static constexpr uint8_t H3C23_POWER_PAYLOAD[6] = {0x0F, 0x00, 0x2A,
                                                   0x36, 0x34, 0x44};
static constexpr uint8_t H3C23_PLL_PAYLOAD[1] = {0x02};
static constexpr uint8_t H3C23_CONTROLLER_TRES[4] = {0x02, 0x00, 0x02, 0x58};
static constexpr uint8_t H3C23_HIDDEN_ENABLE[1] = {0x01};

static constexpr char H3C23_PROFILE_ID[] = "WF23_25";
static constexpr char H3C23_SOURCE_ARTIFACT_SHA256[] =
    "c75d23a0f290deb8416619028284c53726bd399921a2dc0ffe043bef7f227c5d";
static constexpr char H3C23_DECODED_HEADER_SHA256[] =
    "082e520524ebe6c5667d778a1c51407a37d459cc34f8db76b54ba26e93732185";
static constexpr char H3C23_POWER_PAYLOAD_SHA256[] =
    "dcad961ff7dde220b68567cbf3f90ec38f3521c1dbaf63707705f65492145fb4";
static constexpr char H3C23_PLL_PAYLOAD_SHA256[] =
    "dbc1b4c900ffe48d575b5da5c638040125f65db0fe3e24494b76ea986457d986";
static constexpr char H3C23_ATLAS_FRAME_SHA256[] =
    "77454fe933f79b301ecb55b2a065276e0f4fe122bf8416746f71f9b92e90637b";
static constexpr char H3C23_ATLAS_CS1_DTM_SHA256[] =
    "85cd5683ae2d9c5bf9e97bea539a905cdf244983befaeba7e5321aa73ed774f7";
static constexpr char H3C23_ATLAS_CS2_DTM_SHA256[] =
    "cfb5bba82a9421e4c3a13ed10731105d78852a05238ca52ddf3bd9cdd099b943";

static constexpr uint16_t H3C23_PATCH_SIDE = 64;
static constexpr uint16_t H3C23_BORDER = 2;
static constexpr uint16_t H3C23_LOCAL_X[4] = {48, 160, 272, 384};
static constexpr uint16_t H3C23_Y0[2] = {190, 346};
static constexpr uint8_t H3C23_CS1_ORDER[8] = {0, 1, 2, 3, 4, 5, 6, 7};
static constexpr uint8_t H3C23_CS2_ORDER[8] = {7, 6, 5, 4, 3, 2, 1, 0};
static constexpr size_t H3C23_PAYLOAD_PIXELS_PER_CODE = 8192;

static constexpr const char *H3C23_FAILURE_NONE = "none";
static constexpr const char *H3C23_FAILURE_ALLOCATION = "allocation";
static constexpr const char *H3C23_FAILURE_PROFILE = "profile_contract";
static constexpr const char *H3C23_FAILURE_FRAME_BUILD = "frame_build";
static constexpr const char *H3C23_FAILURE_FULL_SHA = "full_sha";
static constexpr const char *H3C23_FAILURE_CS1_COMPUTE = "cs1_compute";
static constexpr const char *H3C23_FAILURE_CS2_COMPUTE = "cs2_compute";
static constexpr const char *H3C23_FAILURE_CS1_IDENTITY = "cs1_identity";
static constexpr const char *H3C23_FAILURE_CS2_IDENTITY = "cs2_identity";
static constexpr const char *H3C23_FAILURE_CASCADE = "cascade_prepare";
static constexpr const char *H3C23_FAILURE_GLOBAL_CONFIG =
    "c23_matched_global_config";
static constexpr const char *H3C23_FAILURE_CS1_E9 = "c23_matched_cs1_e9";
static constexpr const char *H3C23_FAILURE_CS2_E9 = "c23_matched_cs2_e9";
static constexpr const char *H3C23_FAILURE_STREAM_IDENTITY = "stream_identity";
static constexpr const char *H3C23_FAILURE_REFRESH = "refresh_sequence";

struct H3C23Identity {
  uint32_t frameFnv1a;
  uint32_t cs1Fnv1a;
  uint32_t cs2Fnv1a;
  uint32_t histogram[8];
};

static constexpr H3C23Identity H3C23_IDENTITY = {
    0xCE553145UL,
    0x639C1785UL,
    0x1BADB785UL,
    {16640, 548608, 8192, 8192, 8192, 8192, 8192, 8192},
};

struct H3C23DtmIdentity {
  uint32_t fnv1a = 0;
  uint8_t sha256[32] = {};
};

struct H3C23Validation {
  const char *failureStage = H3C23_FAILURE_NONE;
  int32_t failureCode = 0;
  uint32_t frameFnv1a = 0;
  H3C23DtmIdentity cs1;
  H3C23DtmIdentity cs2;
};

bool h3c23RoleValid(EpdH3C23MatchedControlRole role) {
  return role == EpdH3C23MatchedControlRole::EightCodeAtlasWithoutR20R21;
}

bool h3c23DigestMatchesHex(const uint8_t digest[32], const char *expected) {
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

bool h3c23ShaMatches(const uint8_t *data, size_t length,
                     const char *expected, int32_t *errorCode) {
  uint8_t digest[32] = {};
  const int result = mbedtls_sha256_ret(data, length, digest, 0);
  if (errorCode) *errorCode = result;
  return result == 0 && h3c23DigestMatchesHex(digest, expected);
}

bool h3c23ValidateProfile(int32_t *errorCode) {
  if (errorCode) *errorCode = 0;
  static constexpr uint8_t kDecodedHeader[7] = {0x00, 0x2A, 0x36, 0x34,
                                                0x44, 0x14, 0x02};
  return H3C23_POWER_PAYLOAD[0] == 0x0F &&
         std::memcmp(H3C23_POWER_PAYLOAD + 1, kDecodedHeader, 5) == 0 &&
         H3C23_PLL_PAYLOAD[0] == kDecodedHeader[6] &&
         h3c23ShaMatches(kDecodedHeader, sizeof(kDecodedHeader),
                         H3C23_DECODED_HEADER_SHA256, errorCode) &&
         h3c23ShaMatches(H3C23_POWER_PAYLOAD, sizeof(H3C23_POWER_PAYLOAD),
                         H3C23_POWER_PAYLOAD_SHA256, errorCode) &&
         h3c23ShaMatches(H3C23_PLL_PAYLOAD, sizeof(H3C23_PLL_PAYLOAD),
                         H3C23_PLL_PAYLOAD_SHA256, errorCode);
}

void h3c23FillRect(uint8_t *frame, uint16_t x0, uint16_t y0,
                   uint16_t width, uint16_t height, uint8_t code) {
  static constexpr size_t kRowBytes = EPD_WIDTH / 2;
  const uint8_t pair = static_cast<uint8_t>((code << 4) | code);
  for (uint16_t y = y0; y < y0 + height; ++y) {
    std::memset(frame + static_cast<size_t>(y) * kRowBytes + x0 / 2, pair,
                width / 2);
  }
}

bool h3c23BuildFrame(EpdH3C23MatchedControlRole role, uint8_t *frame,
                     uint32_t *histogram) {
  if (!frame || !histogram || !h3c23RoleValid(role)) return false;
  std::memset(frame, 0x11, EPD_FRAME_BYTES);
  for (uint8_t controller = 0; controller < 2; ++controller) {
    const uint16_t halfOffset = controller ? EPD_CONTROLLER_WIDTH : 0;
    const uint8_t *order = controller ? H3C23_CS2_ORDER : H3C23_CS1_ORDER;
    for (uint8_t slot = 0; slot < 8; ++slot) {
      const uint8_t row = slot / 4;
      const uint8_t column = slot % 4;
      const uint16_t x0 = halfOffset + H3C23_LOCAL_X[column];
      const uint16_t y0 = H3C23_Y0[row];
      h3c23FillRect(frame, x0 - H3C23_BORDER, y0 - H3C23_BORDER,
                    H3C23_PATCH_SIDE + 2 * H3C23_BORDER,
                    H3C23_PATCH_SIDE + 2 * H3C23_BORDER, EPD_COLOR_BLACK);
      h3c23FillRect(frame, x0, y0, H3C23_PATCH_SIDE, H3C23_PATCH_SIDE,
                    order[slot]);
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
  if (std::memcmp(histogram, H3C23_IDENTITY.histogram,
                  sizeof(H3C23_IDENTITY.histogram)) != 0) {
    return false;
  }
  for (uint8_t code = 0; code < 8; ++code) {
    size_t payloadPixels = 0;
    for (uint8_t controller = 0; controller < 2; ++controller) {
      const uint8_t *order =
          controller ? H3C23_CS2_ORDER : H3C23_CS1_ORDER;
      for (uint8_t slot = 0; slot < 8; ++slot) {
        if (order[slot] == code)
          payloadPixels += H3C23_PATCH_SIDE * H3C23_PATCH_SIDE;
      }
    }
    if (payloadPixels != H3C23_PAYLOAD_PIXELS_PER_CODE) return false;
  }
  return true;
}

bool h3c23ComputeDtmIdentity(const uint8_t *frame, bool secondController,
                             H3C23DtmIdentity *identity,
                             int32_t *errorCode) {
  if (!frame || !identity || !errorCode) return false;
  *identity = H3C23DtmIdentity{};
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

bool h3c23ValidateRole(EpdH3C23MatchedControlRole role, uint8_t *frame,
                       H3C23Validation *validation) {
  if (!frame || !validation || !h3c23RoleValid(role)) return false;
  *validation = H3C23Validation{};
  uint32_t histogram[8] = {};
  if (!h3c23BuildFrame(role, frame, histogram)) {
    validation->failureStage = H3C23_FAILURE_FRAME_BUILD;
    return false;
  }
  validation->frameFnv1a = fnv1a(frame, EPD_FRAME_BYTES);
  uint8_t frameDigest[32] = {};
  const int shaResult =
      mbedtls_sha256_ret(frame, EPD_FRAME_BYTES, frameDigest, 0);
  if (validation->frameFnv1a != H3C23_IDENTITY.frameFnv1a ||
      shaResult != 0 ||
      !h3c23DigestMatchesHex(frameDigest, H3C23_ATLAS_FRAME_SHA256)) {
    validation->failureStage = H3C23_FAILURE_FULL_SHA;
    validation->failureCode = shaResult;
    return false;
  }
  if (!h3c23ComputeDtmIdentity(frame, false, &validation->cs1,
                               &validation->failureCode)) {
    validation->failureStage = H3C23_FAILURE_CS1_COMPUTE;
    return false;
  }
  if (!h3c23ComputeDtmIdentity(frame, true, &validation->cs2,
                               &validation->failureCode)) {
    validation->failureStage = H3C23_FAILURE_CS2_COMPUTE;
    return false;
  }
  if (validation->cs1.fnv1a != H3C23_IDENTITY.cs1Fnv1a ||
      !h3c23DigestMatchesHex(validation->cs1.sha256,
                            H3C23_ATLAS_CS1_DTM_SHA256)) {
    validation->failureStage = H3C23_FAILURE_CS1_IDENTITY;
    return false;
  }
  if (validation->cs2.fnv1a != H3C23_IDENTITY.cs2Fnv1a ||
      !h3c23DigestMatchesHex(validation->cs2.sha256,
                            H3C23_ATLAS_CS2_DTM_SHA256)) {
    validation->failureStage = H3C23_FAILURE_CS2_IDENTITY;
    return false;
  }
  return true;
}

void h3c23EmitFixedCommand(H3C23FixedCommand command) {
  epdCommand(static_cast<uint8_t>(command));
}

void h3c23WriteFixedPayload(H3C23FixedCommand command,
                            const uint8_t *payload, size_t length) {
  h3c23EmitFixedCommand(command);
  for (size_t index = 0; index < length; ++index) epdData(payload[index]);
}

bool h3c23ApplyMatchedGlobalConfig() {
  setActiveControllers(true, true);
  h3c23WriteFixedPayload(H3C23FixedCommand::PanelSetting,
                         H3C23_RUNTIME_PSR, sizeof(H3C23_RUNTIME_PSR));
  h3c23WriteFixedPayload(H3C23FixedCommand::PowerSetting,
                         H3C23_POWER_PAYLOAD, sizeof(H3C23_POWER_PAYLOAD));
  if (!epdWaitIdle("C23 matched control PWR")) return false;
  h3c23WriteFixedPayload(H3C23FixedCommand::Pll, H3C23_PLL_PAYLOAD,
                         sizeof(H3C23_PLL_PAYLOAD));
  h3c23WriteFixedPayload(H3C23FixedCommand::Resolution,
                         H3C23_CONTROLLER_TRES,
                         sizeof(H3C23_CONTROLLER_TRES));
  return true;
}

bool h3c23ApplyHiddenEnableToController(bool secondController) {
  setActiveControllers(!secondController, secondController);
  h3c23WriteFixedPayload(H3C23FixedCommand::HiddenLutEnable,
                         H3C23_HIDDEN_ENABLE,
                         sizeof(H3C23_HIDDEN_ENABLE));
  return epdWaitIdle(secondController ? "C23 matched control CS2 E9"
                                      : "C23 matched control CS1 E9");
}

}  // namespace

const EpdH3C23MatchedControlManifest &epdGetH3C23MatchedControlManifest() {
  static const EpdH3C23MatchedControlManifest manifest = {
      H3C23_PROFILE_ID,
      H3C23_SOURCE_ARTIFACT_SHA256,
      H3C23_DECODED_HEADER_SHA256,
      H3C23_POWER_PAYLOAD_SHA256,
      H3C23_PLL_PAYLOAD_SHA256,
      H3C23_ATLAS_FRAME_SHA256,
      H3C23_ATLAS_CS1_DTM_SHA256,
      H3C23_ATLAS_CS2_DTM_SHA256,
      23,
      25,
      20000,
      -20000,
      15000,
      -15000,
      7200,
      -8400,
      8200,
      -9800,
      43,
      true,
      true,
      false,
      false,
      false,
      false,
      false,
      false,
  };
  return manifest;
}

bool epdValidateCompiledH3C23MatchedControlFixture() {
  int32_t profileError = 0;
  if (!h3c23ValidateProfile(&profileError)) return false;
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) return false;
  H3C23Validation validation;
  const bool valid = h3c23ValidateRole(
      EpdH3C23MatchedControlRole::EightCodeAtlasWithoutR20R21, frame,
      &validation);
  std::free(frame);
  return valid;
}

bool epdDisplayCompiledH3C23MatchedControl(
    EpdH3C23MatchedControlRole role) {
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  diagnosticReport.freePsramBefore = ESP.getFreePsram();
  diagnosticReport.largestPsramBlockBefore =
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
  if (!h3c23RoleValid(role))
    return epdRejectBeforePanelIo(started, H3C23_FAILURE_FRAME_BUILD);

  int32_t profileError = 0;
  if (!h3c23ValidateProfile(&profileError))
    return epdRejectBeforePanelIo(started, H3C23_FAILURE_PROFILE,
                                  profileError);
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame)
    return epdRejectBeforePanelIo(started, H3C23_FAILURE_ALLOCATION);
  H3C23Validation validation;
  const bool identityOk = h3c23ValidateRole(role, frame, &validation);
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
    return epdFinishFailedOperationSafe(started, H3C23_FAILURE_CASCADE);
  }
  if (!h3c23ApplyMatchedGlobalConfig()) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started,
                                        H3C23_FAILURE_GLOBAL_CONFIG);
  }
  if (!h3c23ApplyHiddenEnableToController(false)) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started, H3C23_FAILURE_CS1_E9);
  }
  if (!h3c23ApplyHiddenEnableToController(true)) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started, H3C23_FAILURE_CS2_E9);
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

  if (diagnosticReport.cs1DtmFnv1a != H3C23_IDENTITY.cs1Fnv1a ||
      diagnosticReport.cs2DtmFnv1a != H3C23_IDENTITY.cs2Fnv1a) {
    return epdFinishFailedOperationSafe(started,
                                        H3C23_FAILURE_STREAM_IDENTITY);
  }
  setActiveControllers(true, true);
  const bool ok = epdSecondSettingAndRefresh();
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  if (!ok) epdRecordFailure(H3C23_FAILURE_REFRESH);
  return epdFinishOperation(started, ok);
}

