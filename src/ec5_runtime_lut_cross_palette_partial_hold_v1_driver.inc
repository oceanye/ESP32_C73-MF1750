// Included only by the isolated partial-HOLD driver wrappers.  The original
// build remains a fixed-input factory-OTP PTLW (0x83) probe.  The explicitly
// guarded runtime-LUT build combines the same PTLW transport with the exact
// fixed active/commented L535 global-header profiles; neither path accepts caller-
// controlled coordinates, colour codes, SPI frequency, commands, or pixels.

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600 &&
                  EPD_FRAME_BYTES == 307200 &&
                  EPD_CONTROLLER_WIDTH == 512 &&
                  EPD_CONTROLLER_FRAME_BYTES == 153600,
              "partial HOLD requires frozen 1024x600 packed 4bpp");
static_assert(EPD_CS1_SOURCE_HALF == 0 && !EPD_CS1_FLIP_X &&
                  !EPD_CS1_FLIP_Y && !EPD_CS1_NIBBLE_SWAP &&
                  EPD_CS2_SOURCE_HALF == 1 && !EPD_CS2_FLIP_X &&
                  !EPD_CS2_FLIP_Y && !EPD_CS2_NIBBLE_SWAP,
              "partial HOLD identities require MAP_ORIENT_V1");
static_assert(EPD_SPI_DEFAULT_HZ == 1000000,
              "partial HOLD is frozen to the proven 1 MHz path");

#if defined(MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_BUILD)
#include "ec5_runtime_lut_cross_palette_partial_hold_v1_identity.inc"
#include "generated/spd1657_legacy_535_reference.inc"
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
    defined(MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_BUILD)
#include "ec5_runtime_lut_partial_hold_repeat_ptlw_v3_identity.inc"
#include "generated/spd1657_legacy_535_reference.inc"
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD)
#include "ec5_runtime_lut_partial_hold_repeat_ptlw_v2_identity.inc"
#include "generated/spd1657_legacy_535_reference.inc"
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V1_BUILD)
#include "ec5_runtime_lut_partial_hold_repeat_ptlw_v1_identity.inc"
#include "generated/spd1657_legacy_535_reference.inc"
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_V4_BUILD)
#include "ec5_runtime_lut_partial_hold_v4_identity.inc"
#include "generated/spd1657_legacy_535_reference.inc"
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_V3_BUILD)
#include "ec5_runtime_lut_partial_hold_v3_identity.inc"
#include "generated/spd1657_legacy_535_reference.inc"
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_V2_BUILD)
#include "ec5_runtime_lut_partial_hold_v2_identity.inc"
#include "generated/spd1657_legacy_535_reference.inc"
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD)
#include "ec5_runtime_lut_partial_hold_identity.inc"
#include "generated/spd1657_legacy_535_reference.inc"
#else
#include "ec5_partial_hold_identity.inc"
#endif

namespace {

#if defined(MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_BUILD)
namespace ph = mf1750_runtime_lut_cross_palette_partial_hold_v1;
namespace ph_lut = mf1750::runtime_lut::legacy_reference;
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
    defined(MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_BUILD)
namespace ph = mf1750_runtime_lut_partial_hold_repeat_ptlw_v3;
namespace ph_lut = mf1750::runtime_lut::legacy_reference;
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD)
namespace ph = mf1750_runtime_lut_partial_hold_repeat_ptlw_v2;
namespace ph_lut = mf1750::runtime_lut::legacy_reference;
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V1_BUILD)
namespace ph = mf1750_runtime_lut_partial_hold_repeat_ptlw_v1;
namespace ph_lut = mf1750::runtime_lut::legacy_reference;
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_V4_BUILD)
namespace ph = mf1750_runtime_lut_partial_hold_v4;
namespace ph_lut = mf1750::runtime_lut::legacy_reference;
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_V3_BUILD)
namespace ph = mf1750_runtime_lut_partial_hold_v3;
namespace ph_lut = mf1750::runtime_lut::legacy_reference;
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_V2_BUILD)
namespace ph = mf1750_runtime_lut_partial_hold_v2;
namespace ph_lut = mf1750::runtime_lut::legacy_reference;
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD)
namespace ph = mf1750_runtime_lut_partial_hold;
namespace ph_lut = mf1750::runtime_lut::legacy_reference;
#else
namespace ph = mf1750_partial_hold;
#endif

static constexpr uint8_t PH_CODE_COUNT = 8;
static constexpr uint8_t PH_WINDOW_COUNT = 3;
static constexpr uint8_t PH_ROLE_COUNT = 4;
static constexpr const char *PH_FAILURE_NONE = "none";
static constexpr const char *PH_FAILURE_ROLE = "role";
static constexpr const char *PH_FAILURE_WINDOW = "window";
static constexpr const char *PH_FAILURE_ALLOCATION = "allocation";
static constexpr const char *PH_FAILURE_FRAME = "frame";
static constexpr const char *PH_FAILURE_HISTOGRAM = "histogram";
static constexpr const char *PH_FAILURE_FRAME_IDENTITY = "frame_identity";
static constexpr const char *PH_FAILURE_DTM_IDENTITY = "dtm_identity";
static constexpr const char *PH_FAILURE_CASCADE_PREPARE = "cascade_prepare";
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD)
static constexpr const char *PH_FAILURE_PROFILE_CONTRACT = "profile_contract";
static constexpr const char *PH_FAILURE_PROFILE_HASH = "profile_hash";
static constexpr const char *PH_FAILURE_GLOBAL_CONFIG = "global_config";
static constexpr const char *PH_FAILURE_CS1_WAVEFORM = "cs1_waveform";
static constexpr const char *PH_FAILURE_CS2_WAVEFORM = "cs2_waveform";
#endif
static constexpr const char *PH_FAILURE_STREAM_IDENTITY = "stream_identity";
static constexpr const char *PH_FAILURE_REFRESH_SEQUENCE =
    "refresh_sequence";

struct PhValidation {
  const char *failureStage = PH_FAILURE_NONE;
  int32_t failureCode = 0;
  uint32_t frameFnv1a = 0;
  uint32_t cs1DtmFnv1a = 0;
  uint32_t cs2DtmFnv1a = 0;
};

size_t phRoleIndex(EpdChromaGridRole role) {
  return static_cast<size_t>(role);
}

bool phRoleValid(EpdChromaGridRole role) {
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V1_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
    defined(MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_BUILD)
  return role == EpdChromaGridRole::Source ||
         role == EpdChromaGridRole::Mid ||
         role == EpdChromaGridRole::Target;
#else
  return phRoleIndex(role) < PH_ROLE_COUNT;
#endif
}

size_t phActionIndexForRole(EpdChromaGridRole role) {
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V1_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
    defined(MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_BUILD)
  return phRoleIndex(role) - 1;
#else
  return phRoleIndex(role);
#endif
}

bool phWindowValid(const ph::Window &window) {
  const uint16_t cs2Y = ph::kCs2VerticalMirror
                            ? static_cast<uint16_t>(
                                  EPD_HEIGHT - window.y - window.height)
                            : window.y;
  return window.width > 0 && window.height > 0 &&
         (window.x & 1U) == 0 && (window.width & 1U) == 0 &&
         static_cast<uint32_t>(window.x) + window.width <=
             EPD_CONTROLLER_WIDTH &&
         static_cast<uint32_t>(window.y) + window.height
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD)
             <=
#else
             <
#endif
             EPD_HEIGHT &&
         static_cast<uint32_t>(cs2Y) + window.height
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD)
             <=
#else
             <
#endif
             EPD_HEIGHT &&
         window.cs1Code < PH_CODE_COUNT && window.cs2Code < PH_CODE_COUNT;
}

bool phLayoutValid() {
  if (ph::kPartialWindowCommand != 0x83 ||
      ph::kPartialWindowPayloadBytes != 9 ||
      ph::kPartialWindowMode != 0x01 ||
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
    defined(MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD)
      ph::kWhiteCode != 7 || ph::kExternalFactoryWhiteAnchorRequired ||
      !ph::kFactoryOtpAnchorActionsReachable ||
      !ph::kRepeatPtlwAfterPonBusy || ph::kRuntimeCode7ActionReachable
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V1_BUILD)
      ph::kWhiteCode != 7 || !ph::kExternalFactoryWhiteAnchorRequired ||
      !ph::kRepeatPtlwAfterPonBusy || ph::kRuntimeCode7ActionReachable
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_V4_BUILD)
      ph::kWhiteCode != 7
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_V3_BUILD)
      ph::kWhiteCode != 7
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_V2_BUILD)
      ph::kWhiteCode != 1
#elif defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD)
      ph::kWhiteCode != 3
#else
      ph::kWhiteCode != 1
#endif
  ) {
    return false;
  }
  for (const ph::Window &window : ph::kWindows) {
    if (!phWindowValid(window)) return false;
  }
  return true;
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

#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD)
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
#endif

void phApplyWindow(uint8_t *frame, const ph::Window &window) {
  const size_t rowBytes = EPD_WIDTH / 2;
  for (uint8_t controller = 0; controller < 2; ++controller) {
    const uint8_t code = controller == 0 ? window.cs1Code : window.cs2Code;
    const uint8_t pair = static_cast<uint8_t>((code << 4) | code);
    const uint16_t globalX =
        static_cast<uint16_t>(controller * EPD_CONTROLLER_WIDTH + window.x);
    const uint16_t yStart =
        controller == 1 && ph::kCs2VerticalMirror
            ? static_cast<uint16_t>(EPD_HEIGHT - window.y - window.height)
            : window.y;
    for (uint16_t y = yStart; y < yStart + window.height; ++y) {
      std::memset(frame + static_cast<size_t>(y) * rowBytes + globalX / 2,
                  pair, window.width / 2);
    }
  }
}

bool phBuildExpectedFrame(EpdChromaGridRole role, uint8_t *frame,
                          uint32_t histogram[PH_CODE_COUNT]) {
  if (!frame || !histogram || !phRoleValid(role) || !phLayoutValid()) {
    return false;
  }
  const uint8_t whitePair =
      static_cast<uint8_t>((ph::kWhiteCode << 4) | ph::kWhiteCode);
  std::memset(frame, whitePair, EPD_FRAME_BYTES);
  const size_t windowsToApply = phRoleIndex(role);
  for (size_t index = 0; index < windowsToApply; ++index) {
    phApplyWindow(frame, ph::kWindows[index]);
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
  *errorCode = 0;
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
  if (result != 0) {
    *errorCode = result;
    return false;
  }
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
  const ph::ActionIdentity &wanted =
      ph::kActions[phActionIndexForRole(role)];
  if (std::memcmp(histogram, wanted.histogram, sizeof(histogram)) != 0) {
    validation->failureStage = PH_FAILURE_HISTOGRAM;
    return false;
  }
  validation->frameFnv1a = fnv1a(frame, EPD_FRAME_BYTES);
  uint8_t frameDigest[32] = {};
  int result = mbedtls_sha256_ret(frame, EPD_FRAME_BYTES, frameDigest, 0);
  if (result != 0 || validation->frameFnv1a != wanted.frameFnv1a ||
      !phDigestMatchesHex(frameDigest, wanted.frameSha256)) {
    validation->failureStage = PH_FAILURE_FRAME_IDENTITY;
    validation->failureCode = result;
    return false;
  }
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V1_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
    defined(MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_BUILD)
  const ph::Window *window = &ph::kWindows[phRoleIndex(role) - 1];
  const size_t dtmBytes =
      static_cast<size_t>(window->width) * window->height / 2;
  const uint8_t cs1Code = window->cs1Code;
  const uint8_t cs2Code = window->cs2Code;
#else
  const bool fullWhite = role == EpdChromaGridRole::White;
  const ph::Window *window =
      fullWhite ? nullptr : &ph::kWindows[phRoleIndex(role) - 1];
  const size_t dtmBytes = fullWhite
                              ? EPD_CONTROLLER_FRAME_BYTES
                              : static_cast<size_t>(window->width) *
                                    window->height / 2;
  const uint8_t cs1Code = fullWhite ? ph::kWhiteCode : window->cs1Code;
  const uint8_t cs2Code = fullWhite ? ph::kWhiteCode : window->cs2Code;
#endif
  uint8_t digest[32] = {};
  if (!phUniformDtmIdentity(dtmBytes, cs1Code, &validation->cs1DtmFnv1a,
                            digest, &validation->failureCode) ||
      validation->cs1DtmFnv1a != wanted.cs1DtmFnv1a ||
      !phDigestMatchesHex(digest, wanted.cs1DtmSha256)) {
    validation->failureStage = PH_FAILURE_DTM_IDENTITY;
    return false;
  }
  std::memset(digest, 0, sizeof(digest));
  if (!phUniformDtmIdentity(dtmBytes, cs2Code, &validation->cs2DtmFnv1a,
                            digest, &validation->failureCode) ||
      validation->cs2DtmFnv1a != wanted.cs2DtmFnv1a ||
      !phDigestMatchesHex(digest, wanted.cs2DtmSha256)) {
    validation->failureStage = PH_FAILURE_DTM_IDENTITY;
    return false;
  }
  return true;
}

void phWritePartialWindowAt(const ph::Window &window, uint16_t y,
                            bool cs1, bool cs2) {
  const uint16_t xe = static_cast<uint16_t>(window.x + window.width - 1);
  const uint16_t ye = static_cast<uint16_t>(
      y + window.height - (ph::kPtlwYEndOneMore ? 0U : 1U));
  setActiveControllers(cs1, cs2);
  epdCommand(ph::kPartialWindowCommand);
  epdData(window.x >> 8);
  epdData(window.x & 0xFF);
  epdData(xe >> 8);
  epdData(xe & 0xFF);
  epdData(y >> 8);
  epdData(y & 0xFF);
  epdData(ye >> 8);
  epdData(ye & 0xFF);
  epdData(ph::kPartialWindowMode);
}

void phWritePartialWindow(const ph::Window &window) {
  if (!ph::kSeparateCsWindowCommands) {
    phWritePartialWindowAt(window, window.y, true, true);
    return;
  }
  const uint16_t cs2Y = ph::kCs2VerticalMirror
                            ? static_cast<uint16_t>(
                                  EPD_HEIGHT - window.y - window.height)
                            : window.y;
  phWritePartialWindowAt(window, window.y, true, false);
  phWritePartialWindowAt(window, cs2Y, false, true);
}

uint32_t phStreamUniformDtm(bool secondController, size_t byteCount,
                            uint8_t code) {
  const uint8_t pair = static_cast<uint8_t>((code << 4) | code);
  setActiveControllers(!secondController, secondController);
  epdCommand(DTM);
  epdStreamFillBytes(byteCount, pair);
  uint32_t hash = FNV1A_OFFSET_BASIS;
  for (size_t index = 0; index < byteCount; ++index) {
    hash = fnv1aUpdate(hash, pair);
  }
  return hash;
}

#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V1_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
    defined(MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_BUILD)
bool phSecondSettingAndRefreshRepeatPtlw(const ph::Window &window) {
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

  // GxEPD2's specified-area sequence re-latches the identical partial RAM
  // area only after power-on is complete.  Send one independent inclusive
  // 0x83 payload per controller, then select both controllers for the
  // unchanged floating-border and refresh sequence.
  phWritePartialWindow(window);
  setActiveControllers(true, true);
  epdCommand(CDI);
  epdData(0xFF);

  epdCommand(BTST2);
  epdData(0x6F);
  epdData(0x1F);
  epdData(0x17);
  epdData(0x49);

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
#endif

}  // namespace

bool epdValidateCompiledChromaGridFixtures() {
  if (!phLayoutValid()) return false;
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD)
  int32_t profileError = 0;
  if (!phValidateRuntimeLutProfile(&profileError)) return false;
#endif
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) return false;
  static constexpr EpdChromaGridRole kRoles[] = {
#if !defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V1_BUILD) && \
    !defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD) && \
    !defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) && \
    !defined(MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_BUILD)
      EpdChromaGridRole::White,
#endif
      EpdChromaGridRole::Source,
      EpdChromaGridRole::Mid,
      EpdChromaGridRole::Target,
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
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD)
  int32_t profileError = 0;
  if (!phValidateRuntimeLutProfile(&profileError)) {
    std::free(frame);
    return epdRejectBeforePanelIo(started, PH_FAILURE_PROFILE_HASH,
                                  profileError);
  }
#endif
  if (!epdPrepareCascade(EPD_SPI_DEFAULT_HZ)) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started,
                                        PH_FAILURE_CASCADE_PREPARE);
  }
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD)
  const bool useCommentedGlobal = role == EpdChromaGridRole::Mid;
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
#endif

  const size_t roleIndex = phRoleIndex(role);
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V1_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
    defined(MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_BUILD)
  const ph::Window *window = &ph::kWindows[roleIndex - 1];
  const size_t dtmBytes =
      static_cast<size_t>(window->width) * window->height / 2;
  phWritePartialWindow(*window);
  const uint8_t cs1Code = window->cs1Code;
  const uint8_t cs2Code = window->cs2Code;
#else
  const bool fullWhite = role == EpdChromaGridRole::White;
  const ph::Window *window =
      fullWhite ? nullptr : &ph::kWindows[roleIndex - 1];
  const size_t dtmBytes = fullWhite
                              ? EPD_CONTROLLER_FRAME_BYTES
                              : static_cast<size_t>(window->width) *
                                    window->height / 2;
  if (!fullWhite) phWritePartialWindow(*window);
  const uint8_t cs1Code = fullWhite ? ph::kWhiteCode : window->cs1Code;
  const uint8_t cs2Code = fullWhite ? ph::kWhiteCode : window->cs2Code;
#endif
  const uint32_t cs1Started = millis();
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V1_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
    defined(MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_BUILD)
  diagnosticReport.cs1DtmFnv1a =
      phStreamUniformDtm(false, dtmBytes, cs1Code);
#else
  diagnosticReport.cs1DtmFnv1a = fullWhite
                                      ? epdStreamPackedFrameController(frame,
                                                                       false)
                                      : phStreamUniformDtm(false, dtmBytes,
                                                           cs1Code);
#endif
  diagnosticReport.cs1UploadMs = millis() - cs1Started;
  const uint32_t cs2Started = millis();
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V1_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
    defined(MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_BUILD)
  diagnosticReport.cs2DtmFnv1a =
      phStreamUniformDtm(true, dtmBytes, cs2Code);
#else
  diagnosticReport.cs2DtmFnv1a = fullWhite
                                      ? epdStreamPackedFrameController(frame,
                                                                       true)
                                      : phStreamUniformDtm(true, dtmBytes,
                                                           cs2Code);
#endif
  diagnosticReport.cs2UploadMs = millis() - cs2Started;
  std::free(frame);
  diagnosticReport.mappingApplied = true;
  const ph::ActionIdentity &wanted =
      ph::kActions[phActionIndexForRole(role)];
  if (diagnosticReport.cs1DtmFnv1a != wanted.cs1DtmFnv1a ||
      diagnosticReport.cs2DtmFnv1a != wanted.cs2DtmFnv1a) {
    return epdFinishFailedOperationSafe(started,
                                        PH_FAILURE_STREAM_IDENTITY);
  }

  setActiveControllers(true, true);
#if defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V1_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V2_BUILD) || \
    defined(MF1750_RUNTIME_LUT_PARTIAL_HOLD_REPEAT_PTLW_V3_BUILD) || \
    defined(MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_BUILD)
  // Preserve V4's pre-PON CDI write.  The isolated helper adds the reference
  // post-PON PTLW + CDI latch sequence before the unchanged BTST2/DRF/POF.
  epdCommand(CDI);
  epdData(0xFF);
  const bool ok = phSecondSettingAndRefreshRepeatPtlw(*window);
#else
  if (!fullWhite) {
    // Cross-checked specified-area implementations float the border before
    // issuing the ordinary OTP display-refresh sequence.
    epdCommand(CDI);
    epdData(0xFF);
  }
  const bool ok = epdSecondSettingAndRefresh();
#endif
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  if (!ok) epdRecordFailure(PH_FAILURE_REFRESH_SEQUENCE);
  return epdFinishOperation(started, ok);
}
