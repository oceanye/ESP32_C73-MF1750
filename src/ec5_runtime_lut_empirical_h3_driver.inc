// Included only by epd_driver.cpp when
// MF1750_ENABLE_RUNTIME_LUT_EMPIRICAL_H3=1. This deliberately relies on the
// private, already panel-validated dual-controller helpers in that translation
// unit. The empirical sequence is cross-generation evidence, not a vendor-
// proven SPD1657 runtime-loader contract and not live authorization.

#if MF1750_RUNTIME_LUT_PROFILE_WF20_25 == 1
#include "generated/spd1657_wf20_25_empirical_h3.inc"
namespace h3_profile = mf1750::runtime_lut::wf20_25_empirical_h3;
#elif MF1750_RUNTIME_LUT_PROFILE_WF23_25 == 1
#include "generated/spd1657_wf23_25_empirical_h3.inc"
namespace h3_profile = mf1750::runtime_lut::wf23_25_empirical_h3;
#else
#error "No explicit empirical H3 profile selected"
#endif

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600,
              "empirical H3 fixture requires the frozen 1024x600 panel");
static_assert(EPD_CONTROLLER_WIDTH == 512 &&
                  EPD_CONTROLLER_FRAME_BYTES == 153600,
              "empirical H3 fixture requires two 512x600 controllers");
static_assert(EPD_CS1_SOURCE_HALF == 0 && !EPD_CS1_FLIP_X &&
                  !EPD_CS1_FLIP_Y && !EPD_CS1_NIBBLE_SWAP &&
                  EPD_CS2_SOURCE_HALF == 1 && !EPD_CS2_FLIP_X &&
                  !EPD_CS2_FLIP_Y && !EPD_CS2_NIBBLE_SWAP,
              "empirical H3 fixture requires MAP_ORIENT_V1");
static_assert(h3_profile::kEmpiricalH3 && !h3_profile::kLiveAuthorized &&
                  !h3_profile::kProfileAutoSelected &&
                  !h3_profile::kContainsHardwareIo,
              "selected profile lost its empirical/offline contract");
static_assert(!h3_profile::kPanelOrFplLimitsProven &&
                  !h3_profile::kH3HeaderBindingProven,
              "generated evidence must not claim vendor/live proof");
static_assert(h3_profile::kDecodedBytes == 800 &&
                  h3_profile::kHeaderBytes == 7 &&
                  h3_profile::kPowerPayloadBytes == 6 &&
                  h3_profile::kPllPayloadBytes == 1 &&
                  h3_profile::kR20PayloadBytes == 799 &&
                  h3_profile::kR21PayloadBytes == 704,
              "empirical H3 payload geometry changed");
static_assert(h3_profile::kR21IsAllFf &&
                  h3_profile::kDecodedPaddingSentinelWasZero,
              "empirical H3 padding contract changed");

namespace {

// The only runtime-register commands this fixture can originate directly.
// E0, DTM, PON, DRF and POF remain in the existing fixed cascade/refresh
// skeleton. There is deliberately no arbitrary-u8 command API here.
enum class H3FixedCommand : uint8_t {
  PanelSetting = 0x00,
  PowerSetting = 0x01,
  DataEntry = 0x10,
  LutR20 = 0x20,
  LutR21 = 0x21,
  Pll = 0x30,
  Resolution = 0x61,
  HiddenLutEnable = 0xE9,
};

static_assert(static_cast<uint8_t>(H3FixedCommand::PanelSetting) != 0x90 &&
                  static_cast<uint8_t>(H3FixedCommand::PanelSetting) != 0x91 &&
                  static_cast<uint8_t>(H3FixedCommand::PowerSetting) != 0x90 &&
                  static_cast<uint8_t>(H3FixedCommand::PowerSetting) != 0x91 &&
                  static_cast<uint8_t>(H3FixedCommand::DataEntry) != 0x90 &&
                  static_cast<uint8_t>(H3FixedCommand::DataEntry) != 0x91 &&
                  static_cast<uint8_t>(H3FixedCommand::LutR20) != 0x90 &&
                  static_cast<uint8_t>(H3FixedCommand::LutR20) != 0x91 &&
                  static_cast<uint8_t>(H3FixedCommand::LutR21) != 0x90 &&
                  static_cast<uint8_t>(H3FixedCommand::LutR21) != 0x91 &&
                  static_cast<uint8_t>(H3FixedCommand::Pll) != 0x90 &&
                  static_cast<uint8_t>(H3FixedCommand::Pll) != 0x91 &&
                  static_cast<uint8_t>(H3FixedCommand::Resolution) != 0x90 &&
                  static_cast<uint8_t>(H3FixedCommand::Resolution) != 0x91 &&
                  static_cast<uint8_t>(H3FixedCommand::HiddenLutEnable) != 0x90 &&
                  static_cast<uint8_t>(H3FixedCommand::HiddenLutEnable) != 0x91,
              "forbidden command entered the empirical H3 allowlist");

static constexpr uint16_t H3_PATCH_SIDE = 64;
static constexpr uint16_t H3_BORDER = 2;
static constexpr uint16_t H3_LOCAL_X[4] = {48, 160, 272, 384};
static constexpr uint16_t H3_Y0[2] = {190, 346};
static constexpr uint8_t H3_CS1_ORDER[8] = {0, 1, 2, 3, 4, 5, 6, 7};
static constexpr uint8_t H3_CS2_ORDER[8] = {7, 6, 5, 4, 3, 2, 1, 0};
static constexpr size_t H3_PAYLOAD_PIXELS_PER_CODE = 8192;

static constexpr const char *H3_FAILURE_NONE = "none";
static constexpr const char *H3_FAILURE_ALLOCATION = "allocation";
static constexpr const char *H3_FAILURE_PROFILE_CONTRACT = "profile_contract";
static constexpr const char *H3_FAILURE_PROFILE_HASH = "profile_hash";
static constexpr const char *H3_FAILURE_GLOBAL_CONFIG =
    "runtime_global_config";
static constexpr const char *H3_FAILURE_CS1_WAVEFORM =
    "runtime_cs1_waveform";
static constexpr const char *H3_FAILURE_CS2_WAVEFORM =
    "runtime_cs2_waveform";
static constexpr const char *H3_FAILURE_FRAME_BUILD = "frame_build";
static constexpr const char *H3_FAILURE_FULL_SHA = "full_sha";
static constexpr const char *H3_FAILURE_CS1_COMPUTE = "cs1_compute";
static constexpr const char *H3_FAILURE_CS2_COMPUTE = "cs2_compute";
static constexpr const char *H3_FAILURE_CS1_IDENTITY = "cs1_identity";
static constexpr const char *H3_FAILURE_CS2_IDENTITY = "cs2_identity";
static constexpr const char *H3_FAILURE_CASCADE_PREPARE = "cascade_prepare";
static constexpr const char *H3_FAILURE_STREAM_IDENTITY = "stream_identity";
static constexpr const char *H3_FAILURE_REFRESH_SEQUENCE = "refresh_sequence";

static constexpr char H3_ATLAS_FRAME_SHA256[] =
    "77454fe933f79b301ecb55b2a065276e0f4fe122bf8416746f71f9b92e90637b";
static constexpr char H3_ATLAS_CS1_DTM_SHA256[] =
    "85cd5683ae2d9c5bf9e97bea539a905cdf244983befaeba7e5321aa73ed774f7";
static constexpr char H3_ATLAS_CS2_DTM_SHA256[] =
    "cfb5bba82a9421e4c3a13ed10731105d78852a05238ca52ddf3bd9cdd099b943";
struct H3RoleIdentity {
  uint32_t frameFnv1a;
  uint32_t cs1Fnv1a;
  uint32_t cs2Fnv1a;
  const char *frameSha256;
  const char *cs1Sha256;
  const char *cs2Sha256;
  uint32_t histogram[8];
};

static const H3RoleIdentity H3_ROLE_IDENTITIES[1] = {
    {0xCE553145UL,
     0x639C1785UL,
     0x1BADB785UL,
     H3_ATLAS_FRAME_SHA256,
     H3_ATLAS_CS1_DTM_SHA256,
     H3_ATLAS_CS2_DTM_SHA256,
     {16640, 548608, 8192, 8192, 8192, 8192, 8192, 8192}},
};

struct H3DtmIdentity {
  uint32_t fnv1a = 0;
  uint8_t sha256[32] = {};
};

struct H3Validation {
  const char *failureStage = H3_FAILURE_NONE;
  int32_t failureCode = 0;
  uint32_t frameFnv1a = 0;
  H3DtmIdentity cs1;
  H3DtmIdentity cs2;
};

size_t h3RoleIndex(EpdEmpiricalH3Role role) {
  return static_cast<size_t>(role);
}

bool h3RoleValid(EpdEmpiricalH3Role role) { return h3RoleIndex(role) < 1; }

bool h3DigestMatchesHex(const uint8_t digest[32], const char *expected) {
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

bool h3ShaMatches(const uint8_t *data, size_t length, const char *expected,
                  int32_t *errorCode) {
  uint8_t digest[32] = {};
  const int result = mbedtls_sha256_ret(data, length, digest, 0);
  if (errorCode) *errorCode = result;
  return result == 0 && h3DigestMatchesHex(digest, expected);
}

bool h3DecodedShaMatches(int32_t *errorCode) {
  mbedtls_sha256_context context;
  mbedtls_sha256_init(&context);
  int result = mbedtls_sha256_starts_ret(&context, 0);
  if (result == 0) {
    result = mbedtls_sha256_update_ret(
        &context, h3_profile::kR20Payload, h3_profile::kR20PayloadBytes);
  }
  static constexpr uint8_t kDecodedSentinel = 0x00;
  if (result == 0) {
    result = mbedtls_sha256_update_ret(&context, &kDecodedSentinel, 1);
  }
  uint8_t digest[32] = {};
  if (result == 0) result = mbedtls_sha256_finish_ret(&context, digest);
  mbedtls_sha256_free(&context);
  if (errorCode) *errorCode = result;
  return result == 0 && h3DigestMatchesHex(
                            digest, h3_profile::kDecodedPlaintextSha256);
}

bool h3ValidateProfileContract(int32_t *errorCode) {
  if (errorCode) *errorCode = 0;
  if (!h3_profile::kEmpiricalH3 || h3_profile::kLiveAuthorized ||
      h3_profile::kProfileAutoSelected || h3_profile::kContainsHardwareIo ||
      h3_profile::kPanelOrFplLimitsProven ||
      h3_profile::kH3HeaderBindingProven ||
      h3_profile::kPowerCommand !=
          static_cast<uint8_t>(H3FixedCommand::PowerSetting) ||
      h3_profile::kPllCommand != static_cast<uint8_t>(H3FixedCommand::Pll) ||
      h3_profile::kR20Command !=
          static_cast<uint8_t>(H3FixedCommand::LutR20) ||
      h3_profile::kR21Command !=
          static_cast<uint8_t>(H3FixedCommand::LutR21) ||
      h3_profile::kDecodedBytes != 800 || h3_profile::kHeaderBytes != 7 ||
      h3_profile::kPowerPayloadBytes != 6 ||
      h3_profile::kPllPayloadBytes != 1 ||
      h3_profile::kR20PayloadBytes != 799 ||
      h3_profile::kR21PayloadBytes != 704 ||
      h3_profile::kRequestedGatePositiveMv != 20000 ||
      h3_profile::kRequestedGateNegativeMv != -20000 ||
      h3_profile::kRequestedFullSourcePositiveMv != 15000 ||
      h3_profile::kRequestedFullSourceNegativeMv != -15000 ||
      h3_profile::kRequestedVshLvMv !=
          3000 + 100 * h3_profile::kDecodedHeader[1] ||
      h3_profile::kRequestedVslLvMv !=
          -(3000 + 100 * h3_profile::kDecodedHeader[2]) ||
      h3_profile::kRequestedVshLv2Mv !=
          3000 + 100 * h3_profile::kDecodedHeader[3] ||
      h3_profile::kRequestedVslLv2Mv !=
          -(3000 + 100 * h3_profile::kDecodedHeader[4]) ||
      h3_profile::kRequestedFrameRateHz != 43 ||
      !h3_profile::kR21IsAllFf ||
      !h3_profile::kDecodedPaddingSentinelWasZero ||
      h3_profile::kDecodedPaddingOffset != h3_profile::kR20PayloadBytes ||
      h3_profile::kPowerPayload[0] != 0x0F ||
      std::memcmp(h3_profile::kPowerPayload + 1,
                  h3_profile::kDecodedHeader, 5) != 0 ||
      h3_profile::kPllPayload[0] != h3_profile::kDecodedHeader[6] ||
      std::memcmp(h3_profile::kR20Payload, h3_profile::kDecodedHeader,
                  h3_profile::kHeaderBytes) != 0) {
    return false;
  }
  for (size_t index = 0; index < h3_profile::kR21PayloadBytes; ++index) {
    if (h3_profile::kR21Payload[index] != 0xFF) return false;
  }
  return true;
}

bool h3ValidateProfileHashes(int32_t *errorCode) {
  return h3ShaMatches(h3_profile::kDecodedHeader,
                      h3_profile::kHeaderBytes,
                      h3_profile::kDecodedHeaderSha256, errorCode) &&
         h3ShaMatches(h3_profile::kPowerPayload,
                      h3_profile::kPowerPayloadBytes,
                      h3_profile::kPowerPayloadSha256, errorCode) &&
         h3ShaMatches(h3_profile::kPllPayload,
                      h3_profile::kPllPayloadBytes,
                      h3_profile::kPllPayloadSha256, errorCode) &&
         h3ShaMatches(h3_profile::kR20Payload,
                      h3_profile::kR20PayloadBytes,
                      h3_profile::kR20PayloadSha256, errorCode) &&
         h3ShaMatches(h3_profile::kR21Payload,
                      h3_profile::kR21PayloadBytes,
                      h3_profile::kR21PayloadSha256, errorCode) &&
         h3DecodedShaMatches(errorCode);
}

void h3FillRect(uint8_t *frame, uint16_t x0, uint16_t y0, uint16_t width,
                uint16_t height, uint8_t code) {
  static constexpr size_t kRowBytes = EPD_WIDTH / 2;
  const uint8_t pair = static_cast<uint8_t>((code << 4) | code);
  for (uint16_t y = y0; y < y0 + height; ++y) {
    std::memset(frame + static_cast<size_t>(y) * kRowBytes + x0 / 2, pair,
                width / 2);
  }
}

bool h3BuildFrame(EpdEmpiricalH3Role role, uint8_t *frame,
                  uint32_t *histogram) {
  if (!frame || !histogram || !h3RoleValid(role)) return false;
  std::memset(frame, 0x11, EPD_FRAME_BYTES);
  for (uint8_t controller = 0; controller < 2; ++controller) {
    const uint16_t halfOffset = controller ? EPD_CONTROLLER_WIDTH : 0;
    const uint8_t *order = controller ? H3_CS2_ORDER : H3_CS1_ORDER;
    for (uint8_t slot = 0; slot < 8; ++slot) {
      const uint8_t row = slot / 4;
      const uint8_t column = slot % 4;
      const uint16_t x0 = halfOffset + H3_LOCAL_X[column];
      const uint16_t y0 = H3_Y0[row];
      h3FillRect(frame, x0 - H3_BORDER, y0 - H3_BORDER,
                 H3_PATCH_SIDE + 2 * H3_BORDER,
                 H3_PATCH_SIDE + 2 * H3_BORDER, EPD_COLOR_BLACK);
      h3FillRect(frame, x0, y0, H3_PATCH_SIDE, H3_PATCH_SIDE, order[slot]);
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
  const H3RoleIdentity &wanted = H3_ROLE_IDENTITIES[h3RoleIndex(role)];
  if (std::memcmp(histogram, wanted.histogram, sizeof(wanted.histogram)) != 0)
    return false;
  for (uint8_t code = 0; code < 8; ++code) {
    size_t payloadPixels = 0;
    for (uint8_t controller = 0; controller < 2; ++controller) {
      const uint8_t *order = controller ? H3_CS2_ORDER : H3_CS1_ORDER;
      for (uint8_t slot = 0; slot < 8; ++slot) {
        if (order[slot] == code) {
          payloadPixels += H3_PATCH_SIDE * H3_PATCH_SIDE;
        }
      }
    }
    if (payloadPixels != H3_PAYLOAD_PIXELS_PER_CODE) return false;
  }
  return true;
}

bool h3ComputeDtmIdentity(const uint8_t *frame, bool secondController,
                          H3DtmIdentity *identity, int32_t *errorCode) {
  if (!frame || !identity || !errorCode) return false;
  *identity = H3DtmIdentity{};
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

bool h3ValidateRole(EpdEmpiricalH3Role role, uint8_t *frame,
                    H3Validation *validation) {
  if (!frame || !validation || !h3RoleValid(role)) return false;
  *validation = H3Validation{};
  uint32_t histogram[8] = {};
  if (!h3BuildFrame(role, frame, histogram)) {
    validation->failureStage = H3_FAILURE_FRAME_BUILD;
    return false;
  }
  const H3RoleIdentity &wanted = H3_ROLE_IDENTITIES[h3RoleIndex(role)];
  validation->frameFnv1a = fnv1a(frame, EPD_FRAME_BYTES);
  uint8_t frameDigest[32] = {};
  const int shaResult =
      mbedtls_sha256_ret(frame, EPD_FRAME_BYTES, frameDigest, 0);
  if (validation->frameFnv1a != wanted.frameFnv1a || shaResult != 0 ||
      !h3DigestMatchesHex(frameDigest, wanted.frameSha256)) {
    validation->failureStage = H3_FAILURE_FULL_SHA;
    validation->failureCode = shaResult;
    return false;
  }
  if (!h3ComputeDtmIdentity(frame, false, &validation->cs1,
                            &validation->failureCode)) {
    validation->failureStage = H3_FAILURE_CS1_COMPUTE;
    return false;
  }
  if (!h3ComputeDtmIdentity(frame, true, &validation->cs2,
                            &validation->failureCode)) {
    validation->failureStage = H3_FAILURE_CS2_COMPUTE;
    return false;
  }
  if (validation->cs1.fnv1a != wanted.cs1Fnv1a ||
      !h3DigestMatchesHex(validation->cs1.sha256, wanted.cs1Sha256)) {
    validation->failureStage = H3_FAILURE_CS1_IDENTITY;
    return false;
  }
  if (validation->cs2.fnv1a != wanted.cs2Fnv1a ||
      !h3DigestMatchesHex(validation->cs2.sha256, wanted.cs2Sha256)) {
    validation->failureStage = H3_FAILURE_CS2_IDENTITY;
    return false;
  }
  return true;
}

void h3EmitFixedCommand(H3FixedCommand command) {
  epdCommand(static_cast<uint8_t>(command));
}

void h3WriteFixedPayload(H3FixedCommand command, const uint8_t *payload,
                         size_t length) {
  h3EmitFixedCommand(command);
  for (size_t index = 0; index < length; ++index) {
    epdData(payload[index]);
    if ((index & 0xFFU) == 0xFFU) yield();
  }
}

bool h3ApplyFixedGlobalRuntimeConfigToBothControllers() {
  // Empirical cross-version hypothesis, intentionally fixed and explicit:
  // factory dual init/E0 first, then MCU LUT PSR, candidate PWR + idle gate,
  // candidate PLL, and TRES again (last-writer resolution rule), all ToBoth.
  setActiveControllers(true, true);
  static constexpr uint8_t kRuntimePsr[2] = {0x5F, 0xE9};
  h3WriteFixedPayload(H3FixedCommand::PanelSetting, kRuntimePsr,
                      sizeof(kRuntimePsr));
  h3WriteFixedPayload(H3FixedCommand::PowerSetting,
                      h3_profile::kPowerPayload,
                      h3_profile::kPowerPayloadBytes);
  if (!epdWaitIdle("runtime H3 PWR")) return false;
  h3WriteFixedPayload(H3FixedCommand::Pll, h3_profile::kPllPayload,
                      h3_profile::kPllPayloadBytes);
  static constexpr uint8_t kControllerTres[4] = {0x02, 0x00, 0x02, 0x58};
  h3WriteFixedPayload(H3FixedCommand::Resolution, kControllerTres,
                      sizeof(kControllerTres));
  return true;
}

bool h3UploadFixedWaveformToController(bool secondController) {
  // Only E9/20/21 are per-controller. Fixed order is CS1 then CS2; there is
  // no broadcast fallback, strategy switch, retry, or readback.
  setActiveControllers(!secondController, secondController);
  static constexpr uint8_t kHiddenEnable[1] = {0x01};
  h3WriteFixedPayload(H3FixedCommand::HiddenLutEnable, kHiddenEnable,
                      sizeof(kHiddenEnable));
  if (!epdWaitIdle(secondController ? "runtime H3 CS2 E9"
                                    : "runtime H3 CS1 E9")) {
    return false;
  }
  h3WriteFixedPayload(H3FixedCommand::LutR20, h3_profile::kR20Payload,
                      h3_profile::kR20PayloadBytes);
  h3WriteFixedPayload(H3FixedCommand::LutR21, h3_profile::kR21Payload,
                      h3_profile::kR21PayloadBytes);
  return true;
}

}  // namespace

const EpdEmpiricalH3ProfileManifest &epdGetEmpiricalH3ProfileManifest() {
  static const EpdEmpiricalH3ProfileManifest manifest = {
      h3_profile::kProfileId,
      h3_profile::kSourceArtifactSha256,
      h3_profile::kDecodedPlaintextSha256,
      h3_profile::kDecodedHeaderSha256,
      h3_profile::kPowerPayloadSha256,
      h3_profile::kPllPayloadSha256,
      h3_profile::kR20PayloadSha256,
      h3_profile::kR21PayloadSha256,
      h3_profile::kApparentTemperatureMinC,
      h3_profile::kApparentTemperatureMaxC,
      h3_profile::kRequestedGatePositiveMv,
      h3_profile::kRequestedGateNegativeMv,
      h3_profile::kRequestedFullSourcePositiveMv,
      h3_profile::kRequestedFullSourceNegativeMv,
      h3_profile::kRequestedVshLvMv,
      h3_profile::kRequestedVslLvMv,
      h3_profile::kRequestedVshLv2Mv,
      h3_profile::kRequestedVslLv2Mv,
      h3_profile::kRequestedFrameRateHz,
      true,
      false,
      false,
      false,
      false,
      false,
  };
  return manifest;
}

bool epdValidateCompiledEmpiricalH3Fixtures() {
  int32_t profileError = 0;
  if (!h3ValidateProfileContract(&profileError) ||
      !h3ValidateProfileHashes(&profileError)) {
    return false;
  }
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) return false;
  H3Validation validation;
  const bool valid = h3ValidateRole(
      EpdEmpiricalH3Role::RuntimeEightCodeAtlas, frame, &validation);
  std::free(frame);
  return valid;
}

bool epdDisplayCompiledEmpiricalH3(EpdEmpiricalH3Role role) {
  // epdBeginOperation is diagnostic-only. All profile, header, waveform,
  // frame, and both mapped-DTM identities are checked before cascade init,
  // SPI startup, reset, controller selection, or any panel command.
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  diagnosticReport.freePsramBefore = ESP.getFreePsram();
  diagnosticReport.largestPsramBlockBefore =
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
  if (!h3RoleValid(role))
    return epdRejectBeforePanelIo(started, H3_FAILURE_FRAME_BUILD);

  int32_t profileError = 0;
  if (!h3ValidateProfileContract(&profileError))
    return epdRejectBeforePanelIo(started, H3_FAILURE_PROFILE_CONTRACT,
                                  profileError);
  if (!h3ValidateProfileHashes(&profileError))
    return epdRejectBeforePanelIo(started, H3_FAILURE_PROFILE_HASH,
                                  profileError);

  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame)
    return epdRejectBeforePanelIo(started, H3_FAILURE_ALLOCATION);
  H3Validation validation;
  const bool identityOk = h3ValidateRole(role, frame, &validation);
  diagnosticReport.inputFrameFnv1a = validation.frameFnv1a;
  diagnosticReport.cs1DtmFnv1a = validation.cs1.fnv1a;
  diagnosticReport.cs2DtmFnv1a = validation.cs2.fnv1a;
  if (!identityOk) {
    std::free(frame);
    return epdRejectBeforePanelIo(started, validation.failureStage,
                                  validation.failureCode);
  }

  // Enter the already validated dual-controller factory init. That path
  // performs the hard reset, PSR 5F,69, TRES 512x600, then writes E0=01
  // separately to CS1 and CS2.
  if (!epdPrepareCascade(EPD_SPI_DEFAULT_HZ)) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started,
                                        H3_FAILURE_CASCADE_PREPARE);
  }
  if (!h3ApplyFixedGlobalRuntimeConfigToBothControllers()) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started, H3_FAILURE_GLOBAL_CONFIG);
  }
  // Fixed order: write E9/20/21 to CS1, then write the same E9/20/21 payload
  // to CS2. There is no broadcast fallback, retry, readback, or switch.
  // The board's single BUSY wire observes only the master-visible signal and
  // cannot prove that CS2 accepted its profile payload.
  if (!h3UploadFixedWaveformToController(false)) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started, H3_FAILURE_CS1_WAVEFORM);
  }
  if (!h3UploadFixedWaveformToController(true)) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started, H3_FAILURE_CS2_WAVEFORM);
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

  const H3RoleIdentity &wanted = H3_ROLE_IDENTITIES[h3RoleIndex(role)];
  if (diagnosticReport.cs1DtmFnv1a != wanted.cs1Fnv1a ||
      diagnosticReport.cs2DtmFnv1a != wanted.cs2Fnv1a) {
    return epdFinishFailedOperationSafe(started,
                                        H3_FAILURE_STREAM_IDENTITY);
  }
  setActiveControllers(true, true);
  const bool ok = epdSecondSettingAndRefresh();
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  if (!ok) epdRecordFailure(H3_FAILURE_REFRESH_SEQUENCE);
  return epdFinishOperation(started, ok);
}
