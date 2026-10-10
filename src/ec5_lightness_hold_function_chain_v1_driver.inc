// Fixed five-action lightness-construction/local-HOLD driver for MF1750.
//
// L1--L3 retain the frozen V3 packed-frame behavior.  H1/H2 retain the clean
// cross-LUT HOLD V2 transport: full code-7 SRAM prestage without refresh,
// exactly one inclusive PTLW per controller, exactly one cropped uniform DTM,
// then PON/DRF00/POF00.  No caller controls coordinates, codes, commands,
// waveform data, timing, or SPI frequency.

#if !defined(MF1750_LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_BUILD) || \
    MF1750_LIGHTNESS_HOLD_FUNCTION_CHAIN_V1_BUILD != 1
#error "lightness/HOLD driver requires its isolated V1 build"
#endif

#if !defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD) || \
    MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD != 1
#error "fullframe/PTLW A/B driver requires the frozen L535 build gate"
#endif

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600 &&
                  EPD_FRAME_BYTES == 307200 &&
                  EPD_CONTROLLER_WIDTH == 512 &&
                  EPD_CONTROLLER_FRAME_BYTES == 153600,
              "fullframe/PTLW A/B requires frozen 1024x600 packed 4bpp");
static_assert(EPD_CS1_SOURCE_HALF == 0 && !EPD_CS1_FLIP_X &&
                  !EPD_CS1_FLIP_Y && !EPD_CS1_NIBBLE_SWAP &&
                  EPD_CS2_SOURCE_HALF == 1 && !EPD_CS2_FLIP_X &&
                  !EPD_CS2_FLIP_Y && !EPD_CS2_NIBBLE_SWAP,
              "fullframe/PTLW A/B identities require MAP_ORIENT_V1");
static_assert(EPD_SPI_DEFAULT_HZ == 1000000,
              "fullframe/PTLW A/B is frozen to the proven 1 MHz path");

#include "ec5_lightness_hold_function_chain_v1_identity.inc"
#include "generated/spd1657_legacy_535_reference.inc"

namespace {

namespace ph = mf1750_lightness_hold_function_chain_v1;
namespace ph_lut = mf1750::runtime_lut::legacy_reference;

static constexpr uint8_t PH_CODE_COUNT = 8;

static constexpr const char *PH_FAILURE_NONE = "none";
static constexpr const char *PH_FAILURE_ROLE = "role";
static constexpr const char *PH_FAILURE_WINDOW = "window";
static constexpr const char *PH_FAILURE_ALLOCATION = "allocation";
static constexpr const char *PH_FAILURE_FRAME = "frame";
static constexpr const char *PH_FAILURE_HISTOGRAM = "histogram";
static constexpr const char *PH_FAILURE_FRAME_IDENTITY = "frame_identity";
static constexpr const char *PH_FAILURE_PRELOAD_IDENTITY = "preload_identity";
static constexpr const char *PH_FAILURE_TARGET_IDENTITY = "target_identity";
static constexpr const char *PH_FAILURE_DTM_IDENTITY = "dtm_identity";
static constexpr const char *PH_FAILURE_CASCADE_PREPARE = "cascade_prepare";
static constexpr const char *PH_FAILURE_PROFILE_HASH = "profile_hash";
static constexpr const char *PH_FAILURE_GLOBAL_CONFIG = "global_config";
static constexpr const char *PH_FAILURE_CS1_WAVEFORM = "cs1_waveform";
static constexpr const char *PH_FAILURE_CS2_WAVEFORM = "cs2_waveform";
static constexpr const char *PH_FAILURE_PRELOAD_STREAM_IDENTITY =
    "preload_stream_identity";
static constexpr const char *PH_FAILURE_STREAM_IDENTITY = "stream_identity";
static constexpr const char *PH_FAILURE_REFRESH_SEQUENCE =
    "refresh_sequence";

struct PhValidation {
  const char *failureStage = PH_FAILURE_NONE;
  int32_t failureCode = 0;
  uint32_t frameFnv1a = 0;
  uint32_t preloadDtmFnv1a = 0;
  uint32_t cs1DtmFnv1a = 0;
  uint32_t cs2DtmFnv1a = 0;
};

bool phRoleValid(EpdChromaGridRole role) {
  return role == EpdChromaGridRole::Source ||
         role == EpdChromaGridRole::Mid ||
         role == EpdChromaGridRole::Target ||
         role == EpdChromaGridRole::ReverseSource ||
         role == EpdChromaGridRole::ReverseTarget;
}

size_t phRoleIndex(EpdChromaGridRole role) {
  return static_cast<size_t>(role);
}

bool phIsHoldRole(EpdChromaGridRole role) {
  return role == EpdChromaGridRole::ReverseSource ||
         role == EpdChromaGridRole::ReverseTarget;
}

size_t phHoldIndex(EpdChromaGridRole role) {
  return role == EpdChromaGridRole::ReverseSource ? 0U : 1U;
}

bool phDigestMatchesHex(const uint8_t digest[32], const char *expected) {
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

bool phLayoutValid() {
  if (ph::kRoleCount != 6 || ph::kRoleIdentityCount != 6 ||
      ph::kHoldActionCount != 2 ||
      sizeof(ph::kActions) / sizeof(ph::kActions[0]) != 6 ||
      ph::kSeparatorCode != 7 || ph::kSourceCode != 7 ||
      ph::kTargetCode != 0 || ph::kPreloadCode != 7 ||
      ph::kFullControllerDtmBytes != EPD_CONTROLLER_FRAME_BYTES ||
      ph::kCroppedDtmBytes != 4608 || ph::kPartialWindowCommand != 0x83 ||
      ph::kPartialWindowPayloadBytes != 9 ||
      sizeof(ph::kPtlwPayloads) !=
          ph::kHoldActionCount * ph::kPartialWindowPayloadBytes ||
      ph::kPartialWindowMode != 0x01 || ph::kCs2VerticalMirror ||
      !ph::kSeparateCsWindowCommands || ph::kPtlwYEndOneMore ||
      !ph::kRuntimeCode7PrestageReachable ||
      ph::kRepeatPtlwAfterPonBusy || ph::kActionStageCdi ||
      ph::kActionStageBtst2 || ph::kCommand0x86Reachable ||
      !ph::kSourceAuthoritySealed || ph::kGridRows != 8 ||
      ph::kGridColumns != 8 || ph::kGridX0 != 20 || ph::kGridY0 != 40 ||
      ph::kGridX1Exclusive != 492 || ph::kGridY1Exclusive != 560) {
    return false;
  }
  static constexpr uint16_t kExpected[2][6] = {
      {64, 8, 384, 24, 5, 5},
      {64, 568, 384, 24, 6, 6},
  };
  for (size_t index = 0; index < ph::kHoldActionCount; ++index) {
    const ph::Window &window = ph::kHoldWindows[index];
    if (window.x != kExpected[index][0] ||
        window.y != kExpected[index][1] ||
        window.width != kExpected[index][2] ||
        window.height != kExpected[index][3] ||
        window.cs1Code != kExpected[index][4] ||
        window.cs2Code != kExpected[index][5] || (window.x & 1U) != 0 ||
        (window.width & 1U) != 0 ||
        static_cast<uint32_t>(window.x) + window.width >
            EPD_CONTROLLER_WIDTH ||
        static_cast<uint32_t>(window.y) + window.height > EPD_HEIGHT ||
        ph::kCroppedDtmBytes !=
            static_cast<size_t>(window.width) * window.height / 2) {
      return false;
    }
    const uint16_t xEnd =
        static_cast<uint16_t>(window.x + window.width - 1U);
    const uint16_t yEnd =
        static_cast<uint16_t>(window.y + window.height - 1U);
    const uint8_t expectedPayload[ph::kPartialWindowPayloadBytes] = {
        static_cast<uint8_t>(window.x >> 8),
        static_cast<uint8_t>(window.x & 0xFF),
        static_cast<uint8_t>(xEnd >> 8),
        static_cast<uint8_t>(xEnd & 0xFF),
        static_cast<uint8_t>(window.y >> 8),
        static_cast<uint8_t>(window.y & 0xFF),
        static_cast<uint8_t>(yEnd >> 8),
        static_cast<uint8_t>(yEnd & 0xFF),
        ph::kPartialWindowMode,
    };
    if (std::memcmp(expectedPayload, ph::kPtlwPayloads[index],
                    sizeof(expectedPayload)) != 0) {
      return false;
    }
    const bool overlapsGrid =
        !(window.x + window.width <= ph::kGridX0 ||
          ph::kGridX1Exclusive <= window.x ||
          window.y + window.height <= ph::kGridY0 ||
          ph::kGridY1Exclusive <= window.y);
    if (overlapsGrid) return false;
  }
  for (size_t leftIndex = 0; leftIndex < ph::kHoldActionCount; ++leftIndex) {
    const ph::Window &left = ph::kHoldWindows[leftIndex];
    for (size_t rightIndex = leftIndex + 1;
         rightIndex < ph::kHoldActionCount;
         ++rightIndex) {
      const ph::Window &right = ph::kHoldWindows[rightIndex];
      if (!(left.x + left.width <= right.x ||
            right.x + right.width <= left.x ||
            left.y + left.height <= right.y ||
            right.y + right.height <= left.y)) {
        return false;
      }
    }
  }
  return true;
}

static_assert(ph_lut::active::kDecodedBytes == 800 &&
                  ph_lut::active::kHeaderBytes == 7 &&
                  ph_lut::active::kPowerPayloadBytes == 6 &&
                  ph_lut::active::kPllPayloadBytes == 1 &&
                  ph_lut::active::kR20PayloadBytes == 799 &&
                  ph_lut::active::kTransmittedR20PrefixBytes == 535 &&
                  ph_lut::active::kR21PayloadBytes == 704 &&
                  ph_lut::commented::kR20PayloadBytes == 799 &&
                  ph_lut::commented::kTransmittedR20PrefixBytes == 535 &&
                  ph_lut::commented::kR21PayloadBytes == 704,
              "L535 runtime-LUT payload geometry changed");
static_assert(ph_lut::active::kLegacyCompleteTablePreserved &&
                  ph_lut::commented::kLegacyCompleteTablePreserved &&
                  ph_lut::active::kR21IsAllFf &&
                  ph_lut::commented::kR21IsAllFf,
              "L535 reference evidence contract changed");

bool phPayloadShaMatches(const uint8_t *payload, size_t length,
                         const char *expected, int32_t *errorCode) {
  if (!payload || length == 0 || !errorCode) return false;
  uint8_t digest[32] = {};
  *errorCode = mbedtls_sha256_ret(payload, length, digest, 0);
  return *errorCode == 0 && phDigestMatchesHex(digest, expected);
}

bool phValidateRuntimeLutProfile(int32_t *errorCode) {
  if (!errorCode || ph_lut::active::kPowerCommand != 0x01 ||
      ph_lut::active::kPllCommand != 0x30 ||
      ph_lut::active::kR20Command != 0x20 ||
      ph_lut::active::kR21Command != 0x21 ||
      ph_lut::commented::kPowerCommand != 0x01 ||
      ph_lut::commented::kPllCommand != 0x30 ||
      ph_lut::commented::kR20Command != 0x20 ||
      ph_lut::commented::kR21Command != 0x21 ||
      std::memcmp(ph_lut::active::kR20Payload,
                  ph_lut::active::kDecodedHeader,
                  ph_lut::active::kHeaderBytes) != 0 ||
      std::memcmp(ph_lut::commented::kR20Payload,
                  ph_lut::commented::kDecodedHeader,
                  ph_lut::commented::kHeaderBytes) != 0) {
    return false;
  }
  return phPayloadShaMatches(
             ph_lut::active::kPowerPayload,
             ph_lut::active::kPowerPayloadBytes,
             ph_lut::active::kPowerPayloadSha256, errorCode) &&
         phPayloadShaMatches(
             ph_lut::active::kPllPayload,
             ph_lut::active::kPllPayloadBytes,
             ph_lut::active::kPllPayloadSha256, errorCode) &&
         phPayloadShaMatches(
             ph_lut::commented::kPowerPayload,
             ph_lut::commented::kPowerPayloadBytes,
             ph_lut::commented::kPowerPayloadSha256, errorCode) &&
         phPayloadShaMatches(
             ph_lut::commented::kPllPayload,
             ph_lut::commented::kPllPayloadBytes,
             ph_lut::commented::kPllPayloadSha256, errorCode) &&
         phPayloadShaMatches(
             ph_lut::active::kR20Payload,
             ph_lut::active::kTransmittedR20PrefixBytes,
             ph_lut::active::kTransmittedR20PrefixSha256, errorCode) &&
         phPayloadShaMatches(
             ph_lut::commented::kR20Payload,
             ph_lut::commented::kTransmittedR20PrefixBytes,
             ph_lut::commented::kTransmittedR20PrefixSha256, errorCode) &&
         phPayloadShaMatches(ph_lut::active::kR21Payload,
                             ph_lut::active::kR21PayloadBytes,
                             ph_lut::active::kR21PayloadSha256, errorCode) &&
         phPayloadShaMatches(ph_lut::commented::kR21Payload,
                             ph_lut::commented::kR21PayloadBytes,
                             ph_lut::commented::kR21PayloadSha256, errorCode);
}

void phWriteFixedPayload(uint8_t command, const uint8_t *payload,
                         size_t length) {
  epdCommand(command);
  for (size_t index = 0; index < length; ++index) {
    epdData(payload[index]);
    if ((index & 0xFFU) == 0xFFU) yield();
  }
}

bool phApplyRuntimeLutGlobalConfig(bool useCommentedGlobal) {
  setActiveControllers(true, true);
  static constexpr uint8_t kRuntimePsr[2] = {0x5F, 0xE9};
  static constexpr uint8_t kControllerTres[4] = {0x02, 0x00, 0x02, 0x58};
  const uint8_t *powerPayload = useCommentedGlobal
                                    ? ph_lut::commented::kPowerPayload
                                    : ph_lut::active::kPowerPayload;
  const size_t powerBytes = useCommentedGlobal
                                ? ph_lut::commented::kPowerPayloadBytes
                                : ph_lut::active::kPowerPayloadBytes;
  const uint8_t *pllPayload = useCommentedGlobal
                                  ? ph_lut::commented::kPllPayload
                                  : ph_lut::active::kPllPayload;
  const size_t pllBytes = useCommentedGlobal
                              ? ph_lut::commented::kPllPayloadBytes
                              : ph_lut::active::kPllPayloadBytes;
  phWriteFixedPayload(0x00, kRuntimePsr, sizeof(kRuntimePsr));
  phWriteFixedPayload(0x01, powerPayload, powerBytes);
  if (!epdWaitIdle(useCommentedGlobal ? "runtime L535 commented PWR"
                                      : "runtime L535 active PWR")) {
    return false;
  }
  phWriteFixedPayload(0x30, pllPayload, pllBytes);
  phWriteFixedPayload(0x61, kControllerTres, sizeof(kControllerTres));
  return true;
}

bool phUploadRuntimeLutToController(bool secondController) {
  setActiveControllers(!secondController, secondController);
  static constexpr uint8_t kHiddenEnable[1] = {0x01};
  phWriteFixedPayload(0xE9, kHiddenEnable, sizeof(kHiddenEnable));
  if (!epdWaitIdle(secondController ? "runtime L535 CS2 E9"
                                    : "runtime L535 CS1 E9")) {
    return false;
  }
  if (secondController) {
    phWriteFixedPayload(0x20, ph_lut::commented::kR20Payload,
                        ph_lut::commented::kTransmittedR20PrefixBytes);
    phWriteFixedPayload(0x21, ph_lut::commented::kR21Payload,
                        ph_lut::commented::kR21PayloadBytes);
  } else {
    phWriteFixedPayload(0x20, ph_lut::active::kR20Payload,
                        ph_lut::active::kTransmittedR20PrefixBytes);
    phWriteFixedPayload(0x21, ph_lut::active::kR21Payload,
                        ph_lut::active::kR21PayloadBytes);
  }
  return true;
}

void phApplyWindow(uint8_t *frame, const ph::Window &window) {
  const size_t fullRowBytes = EPD_WIDTH / 2;
  for (uint8_t controller = 0; controller < 2; ++controller) {
    const uint8_t code =
        controller == 0 ? window.cs1Code : window.cs2Code;
    const uint8_t pair = static_cast<uint8_t>((code << 4) | code);
    const uint16_t globalX =
        static_cast<uint16_t>(controller * EPD_CONTROLLER_WIDTH + window.x);
    for (uint16_t y = window.y; y < window.y + window.height; ++y) {
      std::memset(frame + static_cast<size_t>(y) * fullRowBytes + globalX / 2,
                  pair, window.width / 2);
    }
  }
}

bool phBuildExpectedFrame(EpdChromaGridRole role, uint8_t *frame,
                          uint32_t histogram[PH_CODE_COUNT]) {
  if (!frame || !histogram || !phRoleValid(role) || !phLayoutValid()) {
    return false;
  }
  const uint8_t separatorPair = static_cast<uint8_t>(
      (ph::kSeparatorCode << 4) | ph::kSeparatorCode);
  std::memset(frame, separatorPair, EPD_FRAME_BYTES);
  static constexpr size_t kFullRowBytes = EPD_WIDTH / 2;
  for (uint8_t controller = 0; controller < 2; ++controller) {
    for (uint8_t row = 0; row < ph::kGridRows; ++row) {
      for (uint8_t column = 0; column < ph::kGridColumns; ++column) {
        uint8_t code = ph::kTargetCode;
        if (role == EpdChromaGridRole::Source) {
          code = ph::kSourceCode;
        } else if (role == EpdChromaGridRole::Mid) {
          // This is byte-for-byte the frozen V3 physical packed-grid rule.
          code = controller == 0
                     ? static_cast<uint8_t>((row + column) & 0x07U)
                     : static_cast<uint8_t>((6U - row - column) & 0x07U);
        }
        const uint8_t pair = static_cast<uint8_t>((code << 4) | code);
        const uint16_t x = static_cast<uint16_t>(
            controller * EPD_CONTROLLER_WIDTH + ph::kGridX0 +
            column * (ph::kCellWidth + ph::kGapX));
        const uint16_t y = static_cast<uint16_t>(
            ph::kGridY0 + row * (ph::kCellHeight + ph::kGapY));
        for (uint16_t py = y; py < y + ph::kCellHeight; ++py) {
          std::memset(frame + static_cast<size_t>(py) * kFullRowBytes + x / 2,
                      pair, ph::kCellWidth / 2);
        }
      }
    }
  }
  if (role == EpdChromaGridRole::ReverseSource ||
      role == EpdChromaGridRole::ReverseTarget) {
    phApplyWindow(frame, ph::kHoldWindows[0]);
  }
  if (role == EpdChromaGridRole::ReverseTarget) {
    phApplyWindow(frame, ph::kHoldWindows[1]);
  }

  std::memset(histogram, 0, PH_CODE_COUNT * sizeof(uint32_t));
  for (size_t index = 0; index < EPD_FRAME_BYTES; ++index) {
    const uint8_t high = frame[index] >> 4;
    const uint8_t low = frame[index] & 0x0F;
    if (high >= PH_CODE_COUNT || low >= PH_CODE_COUNT) return false;
    ++histogram[high];
    ++histogram[low];
  }
  return true;
}

bool phUniformDtmIdentity(size_t byteCount, uint8_t code,
                          uint32_t *fnvOut, uint8_t digest[32],
                          int32_t *errorCode) {
  if (!fnvOut || !digest || !errorCode || code >= PH_CODE_COUNT ||
      byteCount == 0) {
    return false;
  }
  const uint8_t pair = static_cast<uint8_t>((code << 4) | code);
  uint8_t block[256];
  std::memset(block, pair, sizeof(block));
  mbedtls_sha256_context context;
  mbedtls_sha256_init(&context);
  int result = mbedtls_sha256_starts_ret(&context, 0);
  uint32_t hash = FNV1A_OFFSET_BASIS;
  size_t remaining = byteCount;
  while (result == 0 && remaining > 0) {
    const size_t chunk = remaining < sizeof(block) ? remaining : sizeof(block);
    result = mbedtls_sha256_update_ret(&context, block, chunk);
    for (size_t index = 0; index < chunk; ++index) {
      hash = fnv1aUpdate(hash, pair);
    }
    remaining -= chunk;
  }
  if (result == 0) result = mbedtls_sha256_finish_ret(&context, digest);
  mbedtls_sha256_free(&context);
  *errorCode = result;
  if (result != 0) return false;
  *fnvOut = hash;
  return true;
}

bool phTreatmentDtmIdentity(EpdChromaGridRole role, const uint8_t *frame,
                            bool secondController, bool includePreload,
                            uint32_t *fnvOut, uint8_t digest[32],
                            int32_t *errorCode) {
  if (!frame || !fnvOut || !digest || !errorCode) return false;
  if (!phRoleValid(role)) return false;
  uint8_t uniformBlock[256];
  std::memset(uniformBlock, 0x77, sizeof(uniformBlock));
  mbedtls_sha256_context context;
  mbedtls_sha256_init(&context);
  int result = mbedtls_sha256_starts_ret(&context, 0);
  uint32_t hash = FNV1A_OFFSET_BASIS;
  size_t preloadRemaining =
      includePreload ? ph::kFullControllerDtmBytes : 0U;
  while (result == 0 && preloadRemaining > 0) {
    const size_t chunk = preloadRemaining < sizeof(uniformBlock)
                             ? preloadRemaining
                             : sizeof(uniformBlock);
    result = mbedtls_sha256_update_ret(&context, uniformBlock, chunk);
    for (size_t index = 0; index < chunk; ++index) {
      hash = fnv1aUpdate(hash, 0x77);
    }
    preloadRemaining -= chunk;
  }

  if (!phIsHoldRole(role)) return false;
  const size_t actionIndex = phHoldIndex(role);
  const ph::Window &window = ph::kHoldWindows[actionIndex];
  const uint8_t targetCode =
      secondController ? window.cs2Code : window.cs1Code;
  std::memset(uniformBlock,
              static_cast<uint8_t>((targetCode << 4) | targetCode),
              sizeof(uniformBlock));
  size_t croppedRemaining = ph::kCroppedDtmBytes;
  while (result == 0 && croppedRemaining > 0) {
    const size_t chunk = croppedRemaining < sizeof(uniformBlock)
                             ? croppedRemaining
                             : sizeof(uniformBlock);
    result = mbedtls_sha256_update_ret(&context, uniformBlock, chunk);
    for (size_t index = 0; index < chunk; ++index) {
      hash = fnv1aUpdate(hash, uniformBlock[0]);
    }
    croppedRemaining -= chunk;
  }
  if (result == 0) result = mbedtls_sha256_finish_ret(&context, digest);
  mbedtls_sha256_free(&context);
  *errorCode = result;
  if (result != 0) return false;
  *fnvOut = hash;
  return true;
}

bool phTargetDtmIdentity(EpdChromaGridRole role, const uint8_t *frame,
                         bool secondController, uint32_t *fnvOut,
                         uint8_t digest[32], int32_t *errorCode) {
  return phTreatmentDtmIdentity(role, frame, secondController, false, fnvOut,
                                digest, errorCode);
}

bool phCombinedDtmIdentity(EpdChromaGridRole role, const uint8_t *frame,
                           bool secondController, uint32_t *fnvOut,
                           uint8_t digest[32], int32_t *errorCode) {
  return phTreatmentDtmIdentity(role, frame, secondController, true, fnvOut,
                                digest, errorCode);
}

bool phValidatePreloadIdentity(PhValidation *validation) {
  uint8_t digest[32] = {};
  if (!phUniformDtmIdentity(ph::kFullControllerDtmBytes, ph::kPreloadCode,
                            &validation->preloadDtmFnv1a, digest,
                            &validation->failureCode) ||
      validation->preloadDtmFnv1a != ph::kPreloadDtmFnv1a ||
      !phDigestMatchesHex(digest, ph::kPreloadDtmSha256)) {
    validation->failureStage = PH_FAILURE_PRELOAD_IDENTITY;
    return false;
  }
  return true;
}

bool phPackedFrameDtmIdentity(const uint8_t *frame, bool secondController,
                              uint32_t *fnvOut, uint8_t digest[32],
                              int32_t *errorCode) {
  if (!frame || !fnvOut || !digest || !errorCode) return false;
  static constexpr size_t kFullRowBytes = EPD_WIDTH / 2;
  static constexpr size_t kControllerRowBytes = EPD_CONTROLLER_WIDTH / 2;
  const ControllerMapping &mapping =
      CONTROLLER_MAPPINGS[secondController ? 1 : 0];
  uint8_t mappedRow[kControllerRowBytes] = {};
  mbedtls_sha256_context context;
  mbedtls_sha256_init(&context);
  int result = mbedtls_sha256_starts_ret(&context, 0);
  uint32_t hash = FNV1A_OFFSET_BASIS;
  for (uint16_t outputY = 0; result == 0 && outputY < EPD_HEIGHT; ++outputY) {
    const uint16_t sourceY =
        mapping.flipY ? EPD_HEIGHT - 1 - outputY : outputY;
    const size_t rowOffset = static_cast<size_t>(sourceY) * kFullRowBytes;
    const size_t halfOffset =
        static_cast<size_t>(mapping.sourceHalf) * kControllerRowBytes;
    const uint8_t *row = frame + rowOffset + halfOffset;
    for (size_t outputByte = 0; outputByte < kControllerRowBytes;
         ++outputByte) {
      const size_t sourceByte =
          mapping.flipX ? kControllerRowBytes - 1 - outputByte : outputByte;
      uint8_t value = row[sourceByte];
      if (mapping.flipX != mapping.nibbleSwap) {
        value = static_cast<uint8_t>((value << 4) | (value >> 4));
      }
      mappedRow[outputByte] = value;
      hash = fnv1aUpdate(hash, value);
    }
    result = mbedtls_sha256_update_ret(&context, mappedRow, sizeof(mappedRow));
  }
  if (result == 0) result = mbedtls_sha256_finish_ret(&context, digest);
  mbedtls_sha256_free(&context);
  *errorCode = result;
  if (result != 0) return false;
  *fnvOut = hash;
  return true;
}

bool phValidateRole(EpdChromaGridRole role, uint8_t *frame,
                    PhValidation *validation) {
  if (!validation) return false;
  *validation = PhValidation{};
  if (!phRoleValid(role)) {
    validation->failureStage = PH_FAILURE_ROLE;
    return false;
  }
  if (!phLayoutValid()) {
    validation->failureStage = PH_FAILURE_WINDOW;
    return false;
  }

  uint32_t histogram[PH_CODE_COUNT] = {};
  if (!phBuildExpectedFrame(role, frame, histogram)) {
    validation->failureStage = PH_FAILURE_FRAME;
    return false;
  }
  const ph::ActionIdentity &wanted = ph::kActions[phRoleIndex(role)];
  if (std::memcmp(histogram, wanted.histogram, sizeof(histogram)) != 0) {
    validation->failureStage = PH_FAILURE_HISTOGRAM;
    return false;
  }

  validation->frameFnv1a = fnv1a(frame, EPD_FRAME_BYTES);
  uint8_t digest[32] = {};
  int result = mbedtls_sha256_ret(frame, EPD_FRAME_BYTES, digest, 0);
  if (result != 0 || validation->frameFnv1a != wanted.frameFnv1a ||
      !phDigestMatchesHex(digest, wanted.frameSha256)) {
    validation->failureStage = PH_FAILURE_FRAME_IDENTITY;
    validation->failureCode = result;
    return false;
  }
  if (!phIsHoldRole(role)) {
    std::memset(digest, 0, sizeof(digest));
    if (!phPackedFrameDtmIdentity(frame, false, &validation->cs1DtmFnv1a,
                                  digest, &validation->failureCode) ||
        validation->cs1DtmFnv1a != wanted.cs1DtmFnv1a ||
        !phDigestMatchesHex(digest, wanted.cs1DtmSha256)) {
      validation->failureStage = PH_FAILURE_DTM_IDENTITY;
      return false;
    }
    std::memset(digest, 0, sizeof(digest));
    if (!phPackedFrameDtmIdentity(frame, true, &validation->cs2DtmFnv1a,
                                  digest, &validation->failureCode) ||
        validation->cs2DtmFnv1a != wanted.cs2DtmFnv1a ||
        !phDigestMatchesHex(digest, wanted.cs2DtmSha256)) {
      validation->failureStage = PH_FAILURE_DTM_IDENTITY;
      return false;
    }
    return true;
  }

  if (!phValidatePreloadIdentity(validation)) return false;
  const size_t actionIndex = phHoldIndex(role);
  const uint32_t wantedTargetFnv = ph::kTargetDtmFnv1a[actionIndex];
  const char *wantedTargetSha = ph::kTargetDtmSha256[actionIndex];
  uint32_t targetFnv = 0;
  std::memset(digest, 0, sizeof(digest));
  if (!phTargetDtmIdentity(role, frame, false, &targetFnv, digest,
                           &validation->failureCode) ||
      targetFnv != wantedTargetFnv ||
      !phDigestMatchesHex(digest, wantedTargetSha)) {
    validation->failureStage = PH_FAILURE_TARGET_IDENTITY;
    return false;
  }
  targetFnv = 0;
  std::memset(digest, 0, sizeof(digest));
  if (!phTargetDtmIdentity(role, frame, true, &targetFnv, digest,
                           &validation->failureCode) ||
      targetFnv != wantedTargetFnv ||
      !phDigestMatchesHex(digest, wantedTargetSha)) {
    validation->failureStage = PH_FAILURE_TARGET_IDENTITY;
    return false;
  }

  std::memset(digest, 0, sizeof(digest));
  const bool cs1IdentityOk = phCombinedDtmIdentity(
      role, frame, false, &validation->cs1DtmFnv1a, digest,
      &validation->failureCode);
  if (!cs1IdentityOk ||
      validation->cs1DtmFnv1a != wanted.cs1DtmFnv1a ||
      !phDigestMatchesHex(digest, wanted.cs1DtmSha256)) {
    validation->failureStage = PH_FAILURE_DTM_IDENTITY;
    return false;
  }

  std::memset(digest, 0, sizeof(digest));
  const bool cs2IdentityOk = phCombinedDtmIdentity(
      role, frame, true, &validation->cs2DtmFnv1a, digest,
      &validation->failureCode);
  if (!cs2IdentityOk ||
      validation->cs2DtmFnv1a != wanted.cs2DtmFnv1a ||
      !phDigestMatchesHex(digest, wanted.cs2DtmSha256)) {
    validation->failureStage = PH_FAILURE_DTM_IDENTITY;
    return false;
  }
  return true;
}

void phWritePartialWindow(const ph::Window &window, size_t actionIndex,
                          bool secondController) {
  setActiveControllers(!secondController, secondController);
  epdCommand(ph::kPartialWindowCommand);
  for (uint8_t value : ph::kPtlwPayloads[actionIndex]) epdData(value);
  (void)window;
}

uint32_t phStreamUniformDtm(bool secondController, size_t byteCount,
                            uint8_t code,
                            uint32_t hash = FNV1A_OFFSET_BASIS) {
  const uint8_t pair = static_cast<uint8_t>((code << 4) | code);
  setActiveControllers(!secondController, secondController);
  epdCommand(DTM);
  epdStreamFillBytes(byteCount, pair);
  for (size_t index = 0; index < byteCount; ++index) {
    hash = fnv1aUpdate(hash, pair);
  }
  return hash;
}

uint32_t phStreamPackedControllerDtm(const uint8_t *frame,
                                     bool secondController,
                                     uint32_t hash) {
  static constexpr size_t kFullRowBytes = EPD_WIDTH / 2;
  static constexpr size_t kControllerRowBytes = EPD_CONTROLLER_WIDTH / 2;
  const ControllerMapping &mapping =
      CONTROLLER_MAPPINGS[secondController ? 1 : 0];
  setActiveControllers(!secondController, secondController);
  epdCommand(DTM);
  for (uint16_t outputY = 0; outputY < EPD_HEIGHT; ++outputY) {
    const uint16_t sourceY =
        mapping.flipY ? EPD_HEIGHT - 1 - outputY : outputY;
    const size_t rowOffset = static_cast<size_t>(sourceY) * kFullRowBytes;
    const size_t halfOffset =
        static_cast<size_t>(mapping.sourceHalf) * kControllerRowBytes;
    const uint8_t *row = frame + rowOffset + halfOffset;
    for (size_t outputByte = 0; outputByte < kControllerRowBytes;
         ++outputByte) {
      const size_t sourceByte =
          mapping.flipX ? kControllerRowBytes - 1 - outputByte : outputByte;
      uint8_t value = row[sourceByte];
      if (mapping.flipX != mapping.nibbleSwap) {
        value = static_cast<uint8_t>((value << 4) | (value >> 4));
      }
      epdData(value);
      hash = fnv1aUpdate(hash, value);
    }
    if ((outputY & 0x0FU) == 0x0FU) yield();
  }
  return hash;
}

bool phRefreshTreatmentsIdentically() {
  setActiveControllers(true, true);

  Serial.println("EPD power on");
  if (!epdRequireIdleBeforeCommand("PON")) {
    Serial.println(
        "EPD abort: BUSY not idle before PON; requesting safe power off");
    epdRequestFailSafePowerOff("POF cleanup after pre-PON busy");
    return false;
  }
  epdCommand(PON);
  if (!epdWaitBusyThenIdle("PON")) {
    Serial.println("EPD abort: PON BUSY failure; requesting safe power off");
    epdRequestFailSafePowerOff("POF cleanup after PON failure");
    return false;
  }

  Serial.println("EPD display refresh");
  if (!epdRequireIdleBeforeCommand("DRF")) {
    Serial.println(
        "EPD abort: BUSY not idle before DRF; requesting safe power off");
    epdRequestFailSafePowerOff("POF cleanup after pre-DRF busy");
    return false;
  }
  epdCommand(DRF);
  epdData(0x00);
  if (!epdWaitBusyThenIdle("DRF")) {
    Serial.println("EPD abort: DRF BUSY failure; requesting safe power off");
    epdRequestFailSafePowerOff("POF cleanup after DRF failure");
    return false;
  }

  Serial.println("EPD power off");
  if (!epdRequireIdleBeforeCommand("POF")) {
    Serial.println(
        "EPD abort: BUSY not idle before POF; requesting safe power off");
    epdRequestFailSafePowerOff("POF cleanup after pre-POF busy");
    return false;
  }
  epdCommand(POF);
  epdData(0x00);
  if (!epdWaitBusyThenIdle("POF")) {
    Serial.println("EPD abort: POF BUSY failure");
    diagnosticReport.safeFinishBusyBeforePinsLow = readBusyLevel();
    epdStopHardwareSpi();
    epdHoldPanelPinsLow();
    diagnosticReport.safeFinishBusyAfterPinsLow = readBusyLevel();
    delay(5);
    diagnosticReport.safeFinishBusyAfter5Ms = readBusyLevel();
    return false;
  }
  delay(10);
  return epdPostDisplayPowerCut();
}

}  // namespace

bool epdValidateCompiledChromaGridFixtures() {
  if (!phLayoutValid()) return false;
  int32_t profileError = 0;
  if (!phValidateRuntimeLutProfile(&profileError)) return false;

  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) return false;
  static constexpr EpdChromaGridRole kRoles[] = {
      EpdChromaGridRole::Source,
      EpdChromaGridRole::Mid,
      EpdChromaGridRole::Target,
      EpdChromaGridRole::ReverseSource,
      EpdChromaGridRole::ReverseTarget,
  };
  bool valid = true;
  for (const EpdChromaGridRole role : kRoles) {
    PhValidation validation;
    if (!phValidateRole(role, frame, &validation)) {
      valid = false;
      break;
    }
  }
  std::free(frame);
  return valid;
}

bool epdDisplayCompiledChromaGrid(EpdChromaGridRole role) {
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  diagnosticReport.freePsramBefore = ESP.getFreePsram();
  diagnosticReport.largestPsramBlockBefore =
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);

  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) {
    return epdRejectBeforePanelIo(started, PH_FAILURE_ALLOCATION);
  }

  PhValidation validation;
  const bool identityOk = phValidateRole(role, frame, &validation);
  diagnosticReport.inputFrameFnv1a = validation.frameFnv1a;
  diagnosticReport.cs1DtmFnv1a = validation.cs1DtmFnv1a;
  diagnosticReport.cs2DtmFnv1a = validation.cs2DtmFnv1a;
  if (!identityOk) {
    std::free(frame);
    return epdRejectBeforePanelIo(started, validation.failureStage,
                                  validation.failureCode);
  }

  int32_t profileError = 0;
  if (!phValidateRuntimeLutProfile(&profileError)) {
    std::free(frame);
    return epdRejectBeforePanelIo(started, PH_FAILURE_PROFILE_HASH,
                                  profileError);
  }
  if (!epdPrepareCascade(EPD_SPI_DEFAULT_HZ)) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started,
                                        PH_FAILURE_CASCADE_PREPARE);
  }
  // The first three actions are byte-for-byte the V3 L1/L2/L3 path.  H1
  // returns to active and H2 switches to commented, while both retain the
  // same frozen CS1-active/CS2-commented LUT upload pairing.
  const bool useCommentedGlobal =
      role == EpdChromaGridRole::Mid ||
      role == EpdChromaGridRole::ReverseTarget;
  if (!phApplyRuntimeLutGlobalConfig(useCommentedGlobal)) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started, PH_FAILURE_GLOBAL_CONFIG);
  }
  if (!phUploadRuntimeLutToController(false)) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started, PH_FAILURE_CS1_WAVEFORM);
  }
  if (!phUploadRuntimeLutToController(true)) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started, PH_FAILURE_CS2_WAVEFORM);
  }

  const ph::ActionIdentity &wanted = ph::kActions[phRoleIndex(role)];
  bool ok = false;
  if (!phIsHoldRole(role)) {
    // Preserve the V3 path exactly: no prestage, no PTLW, one packed DTM per
    // controller, then the established second-setting refresh sequence.
    const uint32_t cs1Started = millis();
    diagnosticReport.cs1DtmFnv1a =
        epdStreamPackedFrameController(frame, false);
    diagnosticReport.cs1UploadMs = millis() - cs1Started;
    const uint32_t cs2Started = millis();
    diagnosticReport.cs2DtmFnv1a =
        epdStreamPackedFrameController(frame, true);
    diagnosticReport.cs2UploadMs = millis() - cs2Started;
    std::free(frame);
    frame = nullptr;
    diagnosticReport.mappingApplied = true;
    if (diagnosticReport.cs1DtmFnv1a != validation.cs1DtmFnv1a ||
        diagnosticReport.cs2DtmFnv1a != validation.cs2DtmFnv1a ||
        diagnosticReport.cs1DtmFnv1a != wanted.cs1DtmFnv1a ||
        diagnosticReport.cs2DtmFnv1a != wanted.cs2DtmFnv1a) {
      return epdFinishFailedOperationSafe(started,
                                          PH_FAILURE_STREAM_IDENTITY);
    }
    ok = epdSecondSettingAndRefresh();
  } else {
    // Clean cross-LUT HOLD V2 transport: full code-7 SRAM prestage without a
    // refresh, one inclusive PTLW per controller, one cropped DTM, then only
    // PON / DRF 00 / POF 00.  No post-PON PTLW, CDI, BTST2, or command 0x86.
    const size_t holdIndex = phHoldIndex(role);
    const ph::Window &window = ph::kHoldWindows[holdIndex];
    const uint32_t cs1PreloadStarted = millis();
    const uint32_t cs1PreloadFnv = phStreamUniformDtm(
        false, ph::kFullControllerDtmBytes, ph::kPreloadCode,
        FNV1A_OFFSET_BASIS);
    const uint32_t cs1PreloadMs = millis() - cs1PreloadStarted;
    const uint32_t cs2PreloadStarted = millis();
    const uint32_t cs2PreloadFnv = phStreamUniformDtm(
        true, ph::kFullControllerDtmBytes, ph::kPreloadCode,
        FNV1A_OFFSET_BASIS);
    const uint32_t cs2PreloadMs = millis() - cs2PreloadStarted;
    if (cs1PreloadFnv != ph::kPreloadDtmFnv1a ||
        cs2PreloadFnv != ph::kPreloadDtmFnv1a ||
        cs1PreloadFnv != validation.preloadDtmFnv1a ||
        cs2PreloadFnv != validation.preloadDtmFnv1a) {
      std::free(frame);
      return epdFinishFailedOperationSafe(
          started, PH_FAILURE_PRELOAD_STREAM_IDENTITY);
    }

    const uint32_t cs1ActionStarted = millis();
    phWritePartialWindow(window, holdIndex, false);
    const uint32_t cs1CombinedFnv = phStreamUniformDtm(
        false, ph::kCroppedDtmBytes, window.cs1Code, cs1PreloadFnv);
    const uint32_t cs1ActionMs = millis() - cs1ActionStarted;
    const uint32_t cs2ActionStarted = millis();
    phWritePartialWindow(window, holdIndex, true);
    const uint32_t cs2CombinedFnv = phStreamUniformDtm(
        true, ph::kCroppedDtmBytes, window.cs2Code, cs2PreloadFnv);
    const uint32_t cs2ActionMs = millis() - cs2ActionStarted;
    std::free(frame);
    frame = nullptr;

    diagnosticReport.cs1DtmFnv1a = cs1CombinedFnv;
    diagnosticReport.cs2DtmFnv1a = cs2CombinedFnv;
    diagnosticReport.cs1UploadMs = cs1PreloadMs + cs1ActionMs;
    diagnosticReport.cs2UploadMs = cs2PreloadMs + cs2ActionMs;
    diagnosticReport.mappingApplied = true;
    if (cs1CombinedFnv != validation.cs1DtmFnv1a ||
        cs2CombinedFnv != validation.cs2DtmFnv1a ||
        cs1CombinedFnv != wanted.cs1DtmFnv1a ||
        cs2CombinedFnv != wanted.cs2DtmFnv1a) {
      return epdFinishFailedOperationSafe(started,
                                          PH_FAILURE_STREAM_IDENTITY);
    }
    ok = phRefreshTreatmentsIdentically();
  }
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  if (!ok) epdRecordFailure(PH_FAILURE_REFRESH_SEQUENCE);
  return epdFinishOperation(started, ok);
}
