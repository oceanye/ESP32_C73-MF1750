// Included only by ec5_single_pixel_cube_epd_driver.cpp.  This is the exact
// compiled counterpart of tools/mf1750_ec5_single_pixel_cube.py.  One global
// full-screen factory-OTP sequence displays
// white -> source -> mid -> target -> white.  The 512 source/mid/target
// histories are split evenly between the two controllers; every 40x22 ROI is
// a spatially uniform native code.  The remaining eight ROIs per controller
// are code 0..7 references.  There is deliberately no partial/window command,
// 0x86 use, LUT upload, interrupted refresh, power cut, SPI sweep, retry,
// recovery, or auto-chain path here.

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600 &&
                  EPD_FRAME_BYTES == 307200 &&
                  EPD_CONTROLLER_WIDTH == 512 &&
                  EPD_CONTROLLER_FRAME_BYTES == 153600,
              "single-pixel cube requires frozen 1024x600 packed 4bpp");
static_assert(EPD_CS1_SOURCE_HALF == 0 && !EPD_CS1_FLIP_X &&
                  !EPD_CS1_FLIP_Y && !EPD_CS1_NIBBLE_SWAP &&
                  EPD_CS2_SOURCE_HALF == 1 && !EPD_CS2_FLIP_X &&
                  !EPD_CS2_FLIP_Y && !EPD_CS2_NIBBLE_SWAP,
              "single-pixel cube identities require MAP_ORIENT_V1");
static_assert(EPD_SPI_DEFAULT_HZ == 1000000,
              "single-pixel cube is frozen to the proven 1 MHz path");

namespace {

static constexpr uint8_t SPC_ROLE_COUNT = 4;
static constexpr uint8_t SPC_CODE_COUNT = 8;
static constexpr uint8_t SPC_CONTROLLER_COUNT = 2;
static constexpr uint8_t SPC_BACKGROUND_CODE = 1;
static constexpr uint8_t SPC_COLUMNS = 11;
static constexpr uint8_t SPC_ROWS = 24;
static constexpr uint16_t SPC_CELL_WIDTH = 40;
static constexpr uint16_t SPC_CELL_HEIGHT = 22;
static constexpr uint16_t SPC_GAP_X = 4;
static constexpr uint16_t SPC_GAP_Y = 2;
static constexpr uint16_t SPC_X0 = 16;
static constexpr uint16_t SPC_Y0 = 13;
static constexpr uint16_t SPC_SLOTS_PER_CONTROLLER =
    SPC_COLUMNS * SPC_ROWS;
static constexpr uint16_t SPC_RECIPE_COUNT =
    SPC_CODE_COUNT * SPC_CODE_COUNT * SPC_CODE_COUNT;
static constexpr uint16_t SPC_RECIPES_PER_CONTROLLER =
    SPC_RECIPE_COUNT / SPC_CONTROLLER_COUNT;
static constexpr uint16_t SPC_REFERENCE_COUNT = SPC_CODE_COUNT;
static constexpr uint32_t SPC_CELL_PIXELS =
    SPC_CELL_WIDTH * SPC_CELL_HEIGHT;

static_assert((SPC_X0 & 1U) == 0 && (SPC_CELL_WIDTH & 1U) == 0,
              "single-pixel cube cells must be packed-byte aligned");
static_assert(SPC_SLOTS_PER_CONTROLLER == 264 &&
                  SPC_RECIPES_PER_CONTROLLER + SPC_REFERENCE_COUNT ==
                      SPC_SLOTS_PER_CONTROLLER,
              "single-pixel cube slot count changed");
static_assert(SPC_X0 + SPC_COLUMNS * SPC_CELL_WIDTH +
                      (SPC_COLUMNS - 1) * SPC_GAP_X ==
                  496 &&
                  496 <= EPD_CONTROLLER_WIDTH,
              "single-pixel cube exceeds a controller half");
static_assert(SPC_Y0 + SPC_ROWS * SPC_CELL_HEIGHT +
                      (SPC_ROWS - 1) * SPC_GAP_Y ==
                  587 &&
                  587 <= EPD_HEIGHT,
              "single-pixel cube exceeds panel height");
static_assert(2U * SPC_SLOTS_PER_CONTROLLER * SPC_CELL_PIXELS == 464640U,
              "single-pixel cube coloured pixel count changed");

static constexpr char SPC_WHITE_FRAME_SHA256[] =
    "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d";
static constexpr char SPC_WHITE_DTM_SHA256[] =
    "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158";
static constexpr char SPC_SOURCE_FRAME_SHA256[] =
    "f472140380c1ab2630bc888d9ab0cb5e7d1f55c66f2be43b1ca89be3749927f6";
static constexpr char SPC_SOURCE_DTM_SHA256[] =
    "eda5cc0e7bc4a947b5186f13ce6bebced9e0e3ac0b5b49c5c27cf70c44a407d4";
static constexpr char SPC_MID_FRAME_SHA256[] =
    "0387640a8bf2ec344199b3602580aafa29a67f5c3e830fc9101251280e8fd28a";
static constexpr char SPC_MID_DTM_SHA256[] =
    "21c6eced681bc5b6068aadfd7a3fb77cc58ebcb65b161f7d8bcc61f33003c8da";
static constexpr char SPC_TARGET_FRAME_SHA256[] =
    "f5a8a0add6fb9f955b14165ae529176512d01c99c4607d8ea2a242b56c0b0254";
static constexpr char SPC_TARGET_CS1_DTM_SHA256[] =
    "0ac4db5cd20921c99cf87b0cbcc526a067af716d8ef805f8583d5f80d027085d";
static constexpr char SPC_TARGET_CS2_DTM_SHA256[] =
    "5ecd431192b23f7f3d74a03b72fc436a01906db24b74c486b17091602a7136c5";

static constexpr const char *SPC_FAILURE_NONE = "none";
static constexpr const char *SPC_FAILURE_ALLOCATION = "allocation";
static constexpr const char *SPC_FAILURE_LAYOUT_DESIGN = "layout_design";
static constexpr const char *SPC_FAILURE_FRAME_BUILD = "frame_build";
static constexpr const char *SPC_FAILURE_HISTOGRAM = "histogram";
static constexpr const char *SPC_FAILURE_FULL_SHA = "full_sha";
static constexpr const char *SPC_FAILURE_CS1_COMPUTE = "cs1_compute";
static constexpr const char *SPC_FAILURE_CS2_COMPUTE = "cs2_compute";
static constexpr const char *SPC_FAILURE_CS1_IDENTITY = "cs1_identity";
static constexpr const char *SPC_FAILURE_CS2_IDENTITY = "cs2_identity";
static constexpr const char *SPC_FAILURE_CASCADE_PREPARE =
    "cascade_prepare";
static constexpr const char *SPC_FAILURE_STREAM_IDENTITY =
    "stream_identity";
static constexpr const char *SPC_FAILURE_REFRESH_SEQUENCE =
    "refresh_sequence";

struct SpcRoleIdentity {
  uint32_t frameFnv1a;
  uint32_t cs1DtmFnv1a;
  uint32_t cs2DtmFnv1a;
  const char *frameSha256;
  const char *cs1DtmSha256;
  const char *cs2DtmSha256;
  uint32_t histogram[SPC_CODE_COUNT];
};

static constexpr SpcRoleIdentity SPC_IDENTITIES[SPC_ROLE_COUNT] = {
    {0x13340DC5UL, 0xB7A855C5UL, 0xB7A855C5UL,
     SPC_WHITE_FRAME_SHA256, SPC_WHITE_DTM_SHA256, SPC_WHITE_DTM_SHA256,
     {0, 614400, 0, 0, 0, 0, 0, 0}},
    {0xBA072E05UL, 0x5F79C545UL, 0x5F79C545UL,
     SPC_SOURCE_FRAME_SHA256, SPC_SOURCE_DTM_SHA256, SPC_SOURCE_DTM_SHA256,
     {58080, 207840, 58080, 58080, 58080, 58080, 58080, 58080}},
    {0xD39B6105UL, 0x54111345UL, 0x54111345UL,
     SPC_MID_FRAME_SHA256, SPC_MID_DTM_SHA256, SPC_MID_DTM_SHA256,
     {58080, 207840, 58080, 58080, 58080, 58080, 58080, 58080}},
    {0xA5587785UL, 0x64CB96E5UL, 0xA3EFEDA5UL,
     SPC_TARGET_FRAME_SHA256, SPC_TARGET_CS1_DTM_SHA256,
     SPC_TARGET_CS2_DTM_SHA256,
     {58080, 207840, 58080, 58080, 58080, 58080, 58080, 58080}},
};

struct SpcRecipe {
  uint8_t source = 0;
  uint8_t mid = 0;
  uint8_t target = 0;
  bool reference = false;
};

struct SpcDtmIdentity {
  uint32_t fnv1a = 0;
  uint8_t sha256[32] = {};
};

struct SpcValidation {
  const char *failureStage = SPC_FAILURE_NONE;
  int32_t failureCode = 0;
  uint32_t frameFnv1a = 0;
  SpcDtmIdentity cs1;
  SpcDtmIdentity cs2;
};

size_t spcRoleIndex(EpdChromaGridRole role) {
  return static_cast<size_t>(role);
}

bool spcRoleValid(EpdChromaGridRole role) {
  return spcRoleIndex(role) < SPC_ROLE_COUNT;
}

uint16_t spcRecipeIndex(uint8_t source, uint8_t mid, uint8_t target) {
  return static_cast<uint16_t>(
      (static_cast<uint16_t>(source) * SPC_CODE_COUNT + mid) *
          SPC_CODE_COUNT +
      target);
}

bool spcRecipeForSlot(uint8_t controller, uint16_t slot, SpcRecipe *recipe) {
  if (!recipe || controller >= SPC_CONTROLLER_COUNT ||
      slot >= SPC_SLOTS_PER_CONTROLLER) {
    return false;
  }
  if (slot >= SPC_RECIPES_PER_CONTROLLER) {
    const uint8_t code =
        static_cast<uint8_t>(slot - SPC_RECIPES_PER_CONTROLLER);
    if (code >= SPC_CODE_COUNT) return false;
    recipe->source = code;
    recipe->mid = code;
    recipe->target = code;
    recipe->reference = true;
    return true;
  }
  uint16_t matched = 0;
  for (uint8_t source = 0; source < SPC_CODE_COUNT; ++source) {
    for (uint8_t mid = 0; mid < SPC_CODE_COUNT; ++mid) {
      for (uint8_t target = 0; target < SPC_CODE_COUNT; ++target) {
        if (((source + mid + target) & 1U) != controller) continue;
        if (matched++ != slot) continue;
        recipe->source = source;
        recipe->mid = mid;
        recipe->target = target;
        recipe->reference = false;
        return true;
      }
    }
  }
  return false;
}

bool spcValidateLayoutDesign() {
  if (SPC_BACKGROUND_CODE >= SPC_CODE_COUNT) return false;
  uint8_t coverage[SPC_RECIPE_COUNT] = {};
  for (uint8_t controller = 0; controller < SPC_CONTROLLER_COUNT;
       ++controller) {
    uint8_t sourceCounts[SPC_CODE_COUNT] = {};
    uint8_t midCounts[SPC_CODE_COUNT] = {};
    uint8_t targetCounts[SPC_CODE_COUNT] = {};
    uint8_t referenceCounts[SPC_CODE_COUNT] = {};
    for (uint16_t slot = 0; slot < SPC_SLOTS_PER_CONTROLLER; ++slot) {
      SpcRecipe recipe;
      if (!spcRecipeForSlot(controller, slot, &recipe)) return false;
      if (recipe.source >= SPC_CODE_COUNT || recipe.mid >= SPC_CODE_COUNT ||
          recipe.target >= SPC_CODE_COUNT) {
        return false;
      }
      if (recipe.reference) {
        if (recipe.source != recipe.mid || recipe.mid != recipe.target) {
          return false;
        }
        ++referenceCounts[recipe.source];
        continue;
      }
      if (((recipe.source + recipe.mid + recipe.target) & 1U) !=
          controller) {
        return false;
      }
      const uint16_t index =
          spcRecipeIndex(recipe.source, recipe.mid, recipe.target);
      if (++coverage[index] != 1) return false;
      ++sourceCounts[recipe.source];
      ++midCounts[recipe.mid];
      ++targetCounts[recipe.target];
    }
    for (uint8_t code = 0; code < SPC_CODE_COUNT; ++code) {
      if (sourceCounts[code] != 32 || midCounts[code] != 32 ||
          targetCounts[code] != 32 || referenceCounts[code] != 1) {
        return false;
      }
    }
  }
  for (uint16_t index = 0; index < SPC_RECIPE_COUNT; ++index) {
    if (coverage[index] != 1) return false;
  }
  return true;
}

void spcFillCell(uint8_t *frame, uint8_t controller, uint16_t slot,
                 uint8_t code) {
  const size_t rowBytes = EPD_WIDTH / 2;
  const uint16_t row = slot / SPC_COLUMNS;
  const uint16_t column = slot % SPC_COLUMNS;
  const uint16_t x0 = controller * EPD_CONTROLLER_WIDTH + SPC_X0 +
                      column * (SPC_CELL_WIDTH + SPC_GAP_X);
  const uint16_t y0 = SPC_Y0 + row * (SPC_CELL_HEIGHT + SPC_GAP_Y);
  const uint8_t pair = static_cast<uint8_t>((code << 4) | code);
  for (uint16_t y = y0; y < y0 + SPC_CELL_HEIGHT; ++y) {
    std::memset(frame + static_cast<size_t>(y) * rowBytes + x0 / 2, pair,
                SPC_CELL_WIDTH / 2);
  }
}

bool spcBuildFrame(EpdChromaGridRole role, uint8_t *frame,
                   uint32_t *histogram) {
  if (!frame || !histogram || !spcRoleValid(role) ||
      !spcValidateLayoutDesign()) {
    return false;
  }
  std::memset(frame, 0x11, EPD_FRAME_BYTES);
  if (role != EpdChromaGridRole::White) {
    for (uint8_t controller = 0; controller < SPC_CONTROLLER_COUNT;
         ++controller) {
      for (uint16_t slot = 0; slot < SPC_SLOTS_PER_CONTROLLER; ++slot) {
        SpcRecipe recipe;
        if (!spcRecipeForSlot(controller, slot, &recipe)) return false;
        uint8_t code = recipe.source;
        if (role == EpdChromaGridRole::Mid) {
          code = recipe.mid;
        } else if (role == EpdChromaGridRole::Target) {
          code = recipe.target;
        }
        spcFillCell(frame, controller, slot, code);
      }
    }
  }
  std::memset(histogram, 0, SPC_CODE_COUNT * sizeof(uint32_t));
  for (size_t index = 0; index < EPD_FRAME_BYTES; ++index) {
    const uint8_t high = frame[index] >> 4;
    const uint8_t low = frame[index] & 0x0F;
    if (high >= SPC_CODE_COUNT || low >= SPC_CODE_COUNT) return false;
    ++histogram[high];
    ++histogram[low];
  }
  return true;
}

bool spcDigestMatchesHex(const uint8_t digest[32], const char *expected) {
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

bool spcComputeDtmIdentity(const uint8_t *frame, bool secondController,
                           SpcDtmIdentity *identity, int32_t *errorCode) {
  if (!frame || !identity || !errorCode) return false;
  *identity = SpcDtmIdentity{};
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

bool spcValidateRole(EpdChromaGridRole role, uint8_t *frame,
                     SpcValidation *validation) {
  if (!frame || !validation || !spcRoleValid(role)) return false;
  *validation = SpcValidation{};
  if (!spcValidateLayoutDesign()) {
    validation->failureStage = SPC_FAILURE_LAYOUT_DESIGN;
    return false;
  }
  uint32_t histogram[SPC_CODE_COUNT] = {};
  if (!spcBuildFrame(role, frame, histogram)) {
    validation->failureStage = SPC_FAILURE_FRAME_BUILD;
    return false;
  }
  const SpcRoleIdentity &wanted = SPC_IDENTITIES[spcRoleIndex(role)];
  if (std::memcmp(histogram, wanted.histogram, sizeof(wanted.histogram)) !=
      0) {
    validation->failureStage = SPC_FAILURE_HISTOGRAM;
    return false;
  }
  validation->frameFnv1a = fnv1a(frame, EPD_FRAME_BYTES);
  uint8_t frameDigest[32] = {};
  const int frameShaResult =
      mbedtls_sha256_ret(frame, EPD_FRAME_BYTES, frameDigest, 0);
  if (validation->frameFnv1a != wanted.frameFnv1a || frameShaResult != 0 ||
      !spcDigestMatchesHex(frameDigest, wanted.frameSha256)) {
    validation->failureStage = SPC_FAILURE_FULL_SHA;
    validation->failureCode = frameShaResult;
    return false;
  }
  if (!spcComputeDtmIdentity(frame, false, &validation->cs1,
                             &validation->failureCode)) {
    validation->failureStage = SPC_FAILURE_CS1_COMPUTE;
    return false;
  }
  if (!spcComputeDtmIdentity(frame, true, &validation->cs2,
                             &validation->failureCode)) {
    validation->failureStage = SPC_FAILURE_CS2_COMPUTE;
    return false;
  }
  if (validation->cs1.fnv1a != wanted.cs1DtmFnv1a ||
      !spcDigestMatchesHex(validation->cs1.sha256, wanted.cs1DtmSha256)) {
    validation->failureStage = SPC_FAILURE_CS1_IDENTITY;
    return false;
  }
  if (validation->cs2.fnv1a != wanted.cs2DtmFnv1a ||
      !spcDigestMatchesHex(validation->cs2.sha256, wanted.cs2DtmSha256)) {
    validation->failureStage = SPC_FAILURE_CS2_IDENTITY;
    return false;
  }
  return true;
}

}  // namespace

bool epdValidateCompiledChromaGridFixtures() {
  if (!spcValidateLayoutDesign()) return false;
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
    SpcValidation validation;
    valid = spcValidateRole(role, frame, &validation);
    if (!valid) break;
  }
  std::free(frame);
  return valid;
}

bool epdDisplayCompiledChromaGrid(EpdChromaGridRole role) {
  // Diagnostics start here, but GPIO/SPI/panel setup remains behind the full
  // allocation, layout, histogram, SHA-256, FNV-1a and DTM identity gate.
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  diagnosticReport.freePsramBefore = ESP.getFreePsram();
  diagnosticReport.largestPsramBlockBefore =
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
  if (!spcRoleValid(role)) {
    return epdRejectBeforePanelIo(started, SPC_FAILURE_FRAME_BUILD);
  }
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) {
    return epdRejectBeforePanelIo(started, SPC_FAILURE_ALLOCATION);
  }
  SpcValidation validation;
  const bool identityOk = spcValidateRole(role, frame, &validation);
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
                                        SPC_FAILURE_CASCADE_PREPARE);
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
  const SpcRoleIdentity &wanted = SPC_IDENTITIES[spcRoleIndex(role)];
  if (diagnosticReport.cs1DtmFnv1a != wanted.cs1DtmFnv1a ||
      diagnosticReport.cs2DtmFnv1a != wanted.cs2DtmFnv1a) {
    return epdFinishFailedOperationSafe(started,
                                        SPC_FAILURE_STREAM_IDENTITY);
  }
  setActiveControllers(true, true);
  const bool ok = epdSecondSettingAndRefresh();
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  if (!ok) epdRecordFailure(SPC_FAILURE_REFRESH_SEQUENCE);
  return epdFinishOperation(started, ok);
}
