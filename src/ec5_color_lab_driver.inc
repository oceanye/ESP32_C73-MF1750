// Included after ec5_eightcode_atlas_driver.inc by epd_driver.cpp when the
// single-flash EC5 COLOR_LAB fixture is enabled. Atlas and authoritative white
// roles delegate to that exact compiled driver; this block adds the isolated
// U07 and the audited Stage-B six-initial-state roles for both candidates.

namespace {

static constexpr uint16_t CL_ISOLATED_X0[2] = {224, 736};
static constexpr uint16_t CL_ISOLATED_Y0 = 268;
static constexpr uint16_t CL_ISOLATED_SIDE = 64;
static constexpr uint16_t CL_SIXSTATE_X0[2] = {244, 756};
static constexpr uint16_t CL_SIXSTATE_Y0[6] = {48, 144, 240, 336, 432, 528};
static constexpr uint8_t CL_SIXSTATE_INITIAL[6] = {1, 0, 3, 2, 5, 6};
static constexpr uint16_t CL_SIXSTATE_SIDE = 24;

// Exact runtime ELF identity symbols for the roles not owned by the atlas
// include. Shared primer bytes intentionally have one symbol/identity.
static const uint8_t CL_U07_ISOLATED_FRAME_SHA256[32] = {
    0xD9, 0xD4, 0x38, 0x88, 0xC6, 0x8B, 0x48, 0x37,
    0x76, 0xBB, 0x43, 0xA5, 0x3C, 0xC1, 0x08, 0x4B,
    0x85, 0x49, 0xD0, 0x0D, 0x9F, 0xF7, 0x0E, 0xF2,
    0xF1, 0x22, 0x7F, 0xAF, 0xE0, 0xAC, 0x7B, 0x3E,
};
static const uint8_t CL_U07_ISOLATED_DTM_SHA256[32] = {
    0x2E, 0x21, 0x71, 0x2A, 0xEC, 0xA3, 0xEE, 0xEC,
    0x9E, 0x24, 0xD9, 0x31, 0x2F, 0x4A, 0x60, 0x1C,
    0x7B, 0x02, 0x12, 0x79, 0x2F, 0x7D, 0x34, 0x19,
    0xA1, 0x50, 0x44, 0x2C, 0xC8, 0x0E, 0xA6, 0xAC,
};
static const uint8_t CL_SIXSTATE_PRIMER_FRAME_SHA256[32] = {
    0x94, 0xEE, 0x82, 0xAE, 0x66, 0xFE, 0x83, 0x72,
    0xE8, 0xC1, 0xD9, 0x77, 0xA1, 0x58, 0xDC, 0x60,
    0xD5, 0x5C, 0x36, 0xDA, 0x86, 0xFC, 0x44, 0xF8,
    0xB2, 0xA9, 0xA0, 0x1C, 0x6D, 0x47, 0xAB, 0x0E,
};
static const uint8_t CL_SIXSTATE_PRIMER_DTM_SHA256[32] = {
    0xF5, 0xBB, 0x17, 0xA5, 0x72, 0x6F, 0x85, 0x1D,
    0xA2, 0xBF, 0x32, 0x2F, 0xFE, 0xA8, 0xF0, 0xEA,
    0x79, 0x1F, 0x70, 0x78, 0x81, 0x84, 0xAD, 0xA4,
    0x26, 0x1B, 0x89, 0xAA, 0x43, 0xDC, 0x39, 0xAF,
};
static const uint8_t CL_U04_TARGET_FRAME_SHA256[32] = {
    0x81, 0xB0, 0xED, 0x1B, 0x71, 0x55, 0x51, 0xDD,
    0xB2, 0x54, 0x6D, 0x4F, 0x12, 0x3C, 0x5C, 0x3D,
    0x47, 0x9B, 0xC8, 0x80, 0x2F, 0xF9, 0xD2, 0x57,
    0x0E, 0x38, 0xD9, 0xB5, 0x7B, 0x46, 0x45, 0xE6,
};
static const uint8_t CL_U04_TARGET_DTM_SHA256[32] = {
    0xC4, 0xEF, 0xD8, 0x36, 0x06, 0xB7, 0x2C, 0x49,
    0xB7, 0xC0, 0xD6, 0x78, 0x65, 0xE4, 0xDF, 0x98,
    0xEF, 0x31, 0xE5, 0xD4, 0x0F, 0x07, 0x12, 0x99,
    0x55, 0x8E, 0x10, 0xC5, 0xA2, 0x12, 0xDD, 0x0F,
};
static const uint8_t CL_U07_TARGET_FRAME_SHA256[32] = {
    0x14, 0x9B, 0xA0, 0xF5, 0xC3, 0xFD, 0x77, 0x9D,
    0x68, 0x70, 0xF6, 0x55, 0xB5, 0x3D, 0x72, 0x6D,
    0x6D, 0x12, 0x97, 0xE0, 0x16, 0x33, 0x1D, 0xE4,
    0xD3, 0x94, 0xE4, 0x11, 0x41, 0x0E, 0x0E, 0x21,
};
static const uint8_t CL_U07_TARGET_DTM_SHA256[32] = {
    0x13, 0x9A, 0x0A, 0xA9, 0x19, 0xD7, 0x8A, 0x1A,
    0xA5, 0x72, 0xDB, 0x49, 0xA7, 0xC9, 0x0F, 0xE3,
    0xA4, 0xF2, 0x94, 0x76, 0xAB, 0x4D, 0x80, 0xBA,
    0x3B, 0xB0, 0xF4, 0x39, 0xF0, 0x19, 0x1B, 0x3D,
};

struct ColorLabRoleIdentity {
  uint32_t frameFnv1a;
  uint32_t dtmFnv1a;
  const uint8_t *frameSha256;
  const uint8_t *dtmSha256;
};

enum class ColorLabOwnedRole : uint8_t {
  U07Isolated = 0,
  SixStatePrimer = 1,
  U04Target = 2,
  U07Target = 3,
};

static const ColorLabRoleIdentity CL_IDENTITIES[4] = {
    {0xA1C5ADC5UL, 0x97F125C5UL, CL_U07_ISOLATED_FRAME_SHA256,
     CL_U07_ISOLATED_DTM_SHA256},
    {0xE4F04785UL, 0x58214425UL, CL_SIXSTATE_PRIMER_FRAME_SHA256,
     CL_SIXSTATE_PRIMER_DTM_SHA256},
    {0x263BD845UL, 0xEF6ED905UL, CL_U04_TARGET_FRAME_SHA256,
     CL_U04_TARGET_DTM_SHA256},
    {0xF93BD8C5UL, 0xE4D43B45UL, CL_U07_TARGET_FRAME_SHA256,
     CL_U07_TARGET_DTM_SHA256},
};

bool clOwnedRoleValid(ColorLabOwnedRole role) {
  return static_cast<size_t>(role) < 4;
}

void clFillRect(uint8_t *frame, uint16_t x0, uint16_t y0, uint16_t side,
                uint8_t code) {
  static constexpr size_t kRowBytes = EPD_WIDTH / 2;
  const uint8_t pair = static_cast<uint8_t>((code << 4) | code);
  for (uint16_t y = y0; y < y0 + side; ++y) {
    std::memset(frame + static_cast<size_t>(y) * kRowBytes + x0 / 2, pair,
                side / 2);
  }
}

bool clBuildOwnedFrame(ColorLabOwnedRole role, uint8_t *frame) {
  if (!frame || !clOwnedRoleValid(role)) return false;
  std::memset(frame, 0x11, EPD_FRAME_BYTES);
  if (role == ColorLabOwnedRole::U07Isolated) {
    for (uint8_t controller = 0; controller < 2; ++controller) {
      clFillRect(frame, CL_ISOLATED_X0[controller], CL_ISOLATED_Y0,
                 CL_ISOLATED_SIDE, 7);
    }
    return true;
  }
  for (uint8_t initial = 0; initial < 6; ++initial) {
    uint8_t code = CL_SIXSTATE_INITIAL[initial];
    if (role == ColorLabOwnedRole::U04Target) code = 4;
    if (role == ColorLabOwnedRole::U07Target) code = 7;
    for (uint8_t controller = 0; controller < 2; ++controller) {
      clFillRect(frame, CL_SIXSTATE_X0[controller], CL_SIXSTATE_Y0[initial],
                 CL_SIXSTATE_SIDE, code);
    }
  }
  return true;
}

bool clValidateOwnedRole(ColorLabOwnedRole role, uint8_t *frame,
                         EightCodeValidation *validation) {
  if (!frame || !validation || !clOwnedRoleValid(role)) return false;
  *validation = EightCodeValidation{};
  if (!clBuildOwnedFrame(role, frame)) {
    validation->failureStage = EC8_FAILURE_FRAME_BUILD;
    return false;
  }
  const ColorLabRoleIdentity &wanted =
      CL_IDENTITIES[static_cast<size_t>(role)];
  validation->frameFnv1a = fnv1a(frame, EPD_FRAME_BYTES);
  uint8_t digest[32] = {};
  const int shaResult = mbedtls_sha256_ret(frame, EPD_FRAME_BYTES, digest, 0);
  if (shaResult != 0 || validation->frameFnv1a != wanted.frameFnv1a ||
      std::memcmp(digest, wanted.frameSha256, 32) != 0) {
    validation->failureStage = EC8_FAILURE_FULL_SHA;
    validation->failureCode = shaResult;
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
  if (validation->cs1.fnv1a != wanted.dtmFnv1a ||
      std::memcmp(validation->cs1.sha256, wanted.dtmSha256, 32) != 0) {
    validation->failureStage = EC8_FAILURE_CS1_IDENTITY;
    return false;
  }
  if (validation->cs2.fnv1a != wanted.dtmFnv1a ||
      std::memcmp(validation->cs2.sha256, wanted.dtmSha256, 32) != 0) {
    validation->failureStage = EC8_FAILURE_CS2_IDENTITY;
    return false;
  }
  return true;
}

bool clMapPublicRole(EpdColorLabRole role, ColorLabOwnedRole *owned) {
  if (!owned) return false;
  switch (role) {
    case EpdColorLabRole::U07Isolated:
      *owned = ColorLabOwnedRole::U07Isolated;
      return true;
    case EpdColorLabRole::U04SixStatePrimer:
    case EpdColorLabRole::U07SixStatePrimer:
      *owned = ColorLabOwnedRole::SixStatePrimer;
      return true;
    case EpdColorLabRole::U04SixStateTarget:
      *owned = ColorLabOwnedRole::U04Target;
      return true;
    case EpdColorLabRole::U07SixStateTarget:
      *owned = ColorLabOwnedRole::U07Target;
      return true;
    default:
      return false;
  }
}

}  // namespace

bool epdValidateCompiledColorLabFixtures() {
  if (!epdValidateCompiledEightCodeAtlasFixtures()) return false;
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) return false;
  bool valid = true;
  for (uint8_t index = 0; valid && index < 4; ++index) {
    EightCodeValidation validation;
    valid = clValidateOwnedRole(static_cast<ColorLabOwnedRole>(index), frame,
                                &validation);
  }
  std::free(frame);
  return valid;
}

bool epdDisplayCompiledColorLab(EpdColorLabRole role) {
  if (role == EpdColorLabRole::White)
    return epdDisplayCompiledEightCodeAtlas(EpdEightCodeAtlasRole::White);
  if (role == EpdColorLabRole::Atlas)
    return epdDisplayCompiledEightCodeAtlas(EpdEightCodeAtlasRole::Atlas);

  ColorLabOwnedRole owned;
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  diagnosticReport.freePsramBefore = ESP.getFreePsram();
  diagnosticReport.largestPsramBlockBefore =
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
  if (!clMapPublicRole(role, &owned))
    return epdRejectBeforePanelIo(started, EC8_FAILURE_FRAME_BUILD);
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame)
    return epdRejectBeforePanelIo(started, EC8_FAILURE_ALLOCATION);
  EightCodeValidation validation;
  const bool valid = clValidateOwnedRole(owned, frame, &validation);
  diagnosticReport.inputFrameFnv1a = validation.frameFnv1a;
  diagnosticReport.cs1DtmFnv1a = validation.cs1.fnv1a;
  diagnosticReport.cs2DtmFnv1a = validation.cs2.fnv1a;
  if (!valid) {
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
  const ColorLabRoleIdentity &wanted =
      CL_IDENTITIES[static_cast<size_t>(owned)];
  if (diagnosticReport.cs1DtmFnv1a != wanted.dtmFnv1a ||
      diagnosticReport.cs2DtmFnv1a != wanted.dtmFnv1a) {
    return epdFinishFailedOperationSafe(started,
                                        EC8_FAILURE_STREAM_IDENTITY);
  }
  setActiveControllers(true, true);
  const bool ok = epdSecondSettingAndRefresh();
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  if (!ok) epdRecordFailure(EC8_FAILURE_REFRESH_SEQUENCE);
  return epdFinishOperation(started, ok);
}
