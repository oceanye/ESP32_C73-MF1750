#pragma once

#include <Arduino.h>

#ifndef MF1750_ENABLE_UNKNOWN_PROBE
#define MF1750_ENABLE_UNKNOWN_PROBE 0
#endif

#ifndef MF1750_ENABLE_SIXSTATE_PROBE
#define MF1750_ENABLE_SIXSTATE_PROBE 0
#endif

#ifndef MF1750_ENABLE_U04_U05_COMPARE
#define MF1750_ENABLE_U04_U05_COMPARE 0
#endif

#ifndef MF1750_ENABLE_EIGHTCODE_ATLAS
#define MF1750_ENABLE_EIGHTCODE_ATLAS 0
#endif

#ifndef MF1750_ENABLE_COLOR_LAB
#define MF1750_ENABLE_COLOR_LAB 0
#endif

#ifndef MF1750_ENABLE_OTP_TRANSITION_MATRIX
#define MF1750_ENABLE_OTP_TRANSITION_MATRIX 0
#endif

#ifndef MF1750_ENABLE_DITHER_COLOR_ATLAS
#define MF1750_ENABLE_DITHER_COLOR_ATLAS 0
#endif

#ifndef MF1750_ENABLE_RUNTIME_LUT_EMPIRICAL_H3
#define MF1750_ENABLE_RUNTIME_LUT_EMPIRICAL_H3 0
#endif

#ifndef MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY
#define MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY 0
#endif

#ifndef MF1750_RUNTIME_LUT_PROFILE_WF20_25
#define MF1750_RUNTIME_LUT_PROFILE_WF20_25 0
#endif

#ifndef MF1750_RUNTIME_LUT_PROFILE_WF23_25
#define MF1750_RUNTIME_LUT_PROFILE_WF23_25 0
#endif

#ifndef MF1750_OTP_WHITE_FOR_PROFILE_WF20_25
#define MF1750_OTP_WHITE_FOR_PROFILE_WF20_25 0
#endif

#ifndef MF1750_OTP_WHITE_FOR_PROFILE_WF23_25
#define MF1750_OTP_WHITE_FOR_PROFILE_WF23_25 0
#endif

#if MF1750_ENABLE_UNKNOWN_PROBE && MF1750_ENABLE_SIXSTATE_PROBE
#error "EC5 experimental driver fixtures are mutually exclusive"
#endif

#if MF1750_ENABLE_U04_U05_COMPARE && \
    (MF1750_ENABLE_UNKNOWN_PROBE || MF1750_ENABLE_SIXSTATE_PROBE)
#error "EC5 experimental driver fixtures are mutually exclusive"
#endif

#if MF1750_ENABLE_EIGHTCODE_ATLAS && \
    (MF1750_ENABLE_UNKNOWN_PROBE || MF1750_ENABLE_SIXSTATE_PROBE || \
     MF1750_ENABLE_U04_U05_COMPARE)
#error "EC5 atlas/color-lab driver is isolated from historical fixtures"
#endif

#if MF1750_ENABLE_COLOR_LAB && !MF1750_ENABLE_EIGHTCODE_ATLAS
#error "EC5 COLOR_LAB requires its compiled eight-code atlas fixture"
#endif

#if MF1750_ENABLE_OTP_TRANSITION_MATRIX && \
    (MF1750_ENABLE_UNKNOWN_PROBE || MF1750_ENABLE_SIXSTATE_PROBE || \
     MF1750_ENABLE_U04_U05_COMPARE || MF1750_ENABLE_EIGHTCODE_ATLAS || \
     MF1750_ENABLE_COLOR_LAB)
#error "Factory-OTP transition matrix is isolated from other fixtures"
#endif

#if MF1750_ENABLE_DITHER_COLOR_ATLAS && \
    (MF1750_ENABLE_UNKNOWN_PROBE || MF1750_ENABLE_SIXSTATE_PROBE || \
     MF1750_ENABLE_U04_U05_COMPARE || MF1750_ENABLE_EIGHTCODE_ATLAS || \
     MF1750_ENABLE_COLOR_LAB || MF1750_ENABLE_OTP_TRANSITION_MATRIX)
#error "Factory-OTP dither color atlas is isolated from other fixtures"
#endif

#if MF1750_ENABLE_RUNTIME_LUT_EMPIRICAL_H3 && \
    (MF1750_ENABLE_UNKNOWN_PROBE || MF1750_ENABLE_SIXSTATE_PROBE || \
     MF1750_ENABLE_U04_U05_COMPARE || MF1750_ENABLE_EIGHTCODE_ATLAS || \
     MF1750_ENABLE_COLOR_LAB || MF1750_ENABLE_OTP_TRANSITION_MATRIX || \
     MF1750_ENABLE_DITHER_COLOR_ATLAS)
#error "Empirical H3 runtime-LUT fixture is isolated from every other fixture"
#endif

#if MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY && \
    (MF1750_ENABLE_UNKNOWN_PROBE || MF1750_ENABLE_SIXSTATE_PROBE || \
     MF1750_ENABLE_U04_U05_COMPARE || MF1750_ENABLE_EIGHTCODE_ATLAS || \
     MF1750_ENABLE_COLOR_LAB || MF1750_ENABLE_OTP_TRANSITION_MATRIX || \
     MF1750_ENABLE_DITHER_COLOR_ATLAS || \
     MF1750_ENABLE_RUNTIME_LUT_EMPIRICAL_H3)
#error "Factory-OTP white recovery is isolated from every other fixture"
#endif

#if MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY && \
    ((MF1750_OTP_WHITE_FOR_PROFILE_WF20_25 + \
      MF1750_OTP_WHITE_FOR_PROFILE_WF23_25) != 1)
#error "Factory-OTP white recovery must bind exactly one campaign profile"
#endif

#if !MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY && \
    (MF1750_OTP_WHITE_FOR_PROFILE_WF20_25 || \
     MF1750_OTP_WHITE_FOR_PROFILE_WF23_25)
#error "OTP-white campaign profile is forbidden outside its isolated fixture"
#endif

#if MF1750_ENABLE_RUNTIME_LUT_EMPIRICAL_H3 && \
    ((MF1750_RUNTIME_LUT_PROFILE_WF20_25 + \
      MF1750_RUNTIME_LUT_PROFILE_WF23_25) != 1)
#error "Empirical H3 build must select exactly one explicit vendor profile"
#endif

#if !MF1750_ENABLE_RUNTIME_LUT_EMPIRICAL_H3 && \
    (MF1750_RUNTIME_LUT_PROFILE_WF20_25 || \
     MF1750_RUNTIME_LUT_PROFILE_WF23_25)
#error "Runtime-LUT profile selection is forbidden outside the isolated H3 fixture"
#endif

static constexpr const char *EPD_DRIVER_API_VERSION = "MF1750_R16_CASCADE_V3";

struct EpdBusyStageEvidence {
  // 0/1 are raw GPIO levels. 0xFF means that the sample was not reached.
  uint8_t gateEntryLevel = 0xFF;
  uint8_t preCommandLevel = 0xFF;
  uint8_t waitEntryLevel = 0xFF;
  uint8_t waitExitLevel = 0xFF;
  bool preCommandIdleOk = false;
  bool assertionAfterIdle = false;
  uint32_t preCommandWaitMs = 0;
  uint32_t waitMs = 0;
  uint32_t assertionLatencyMs = 0;
};

struct EpdOperationReport {
  // Non-zero u32 sequence for this boot. A new value is allocated before
  // every result-bearing driver operation, including rejected operations;
  // main.cpp rejects a wrap instead of binding it as fresh.
  uint32_t operationId = 0;
  bool valid = false;
  bool running = false;
  bool sequenceOk = false;
  bool waitTimedOut = false;
  bool busyAssertionMissing = false;
  bool mappingApplied = false;
  bool ponBusySeen = false;
  bool drfBusySeen = false;
  bool pofBusySeen = false;
  bool postPsrBusySeen = false;
  bool preCommandIdleFailure = false;
  // Stable machine-readable reason for a rejected operation. "none" means
  // that no failure has been recorded. EC5 pre-panel validation uses the
  // frozen values allocation/frame_build/full_sha/cs1_compute/cs2_compute/
  // cs1_identity/cs2_identity so a consumed one-shot can be adjudicated
  // without relying on a transient serial log.
  int32_t failureCode = 0;
  uint32_t spiHz = 0;
  uint32_t freePsramBefore = 0;
  uint32_t largestPsramBlockBefore = 0;
  uint32_t inputFrameFnv1a = 0;
  uint32_t cs1DtmFnv1a = 0;
  uint32_t cs2DtmFnv1a = 0;
  uint32_t totalMs = 0;
  uint32_t cs1UploadMs = 0;
  uint32_t cs2UploadMs = 0;
  uint32_t ponWaitMs = 0;
  uint32_t drfWaitMs = 0;
  uint32_t pofWaitMs = 0;
  uint32_t postPsrWaitMs = 0;
  uint32_t lastWaitMs = 0;
  EpdBusyStageEvidence resetBusy;
  EpdBusyStageEvidence ponBusy;
  EpdBusyStageEvidence drfBusy;
  EpdBusyStageEvidence pofBusy;
  EpdBusyStageEvidence postPsrBusy;
  uint8_t safeFinishBusyBeforePinsLow = 0xFF;
  uint8_t safeFinishBusyAfterPinsLow = 0xFF;
  uint8_t safeFinishBusyAfter5Ms = 0xFF;
  uint8_t finalBusyLevel = 0xFF;
  uint8_t finalRstLevel = 0xFF;
  uint8_t finalCs1Level = 0xFF;
  uint8_t finalCs2Level = 0xFF;
  uint8_t finalSckLevel = 0xFF;
  uint8_t finalDcLevel = 0xFF;
  uint8_t finalMosiLevel = 0xFF;
  char lastWaitStage[32] = "none";
  char timeoutStage[32] = "none";
  char busyMissingStage[32] = "none";
  char preCommandBusyStage[32] = "none";
  char failureStage[32] = "none";
};

void epdBegin();
int epdReadBusy();
const EpdOperationReport &epdGetLastOperationReport();
// Canonical physical frame codes are 0/1/2/3/5/6. Both helpers are side-effect
// free; every display entry point also validates before any panel I/O.
bool epdIsSupportedColorCode(uint8_t color);
bool epdValidateFrameColors(const uint8_t *frame, size_t len,
                            size_t *invalidPixel = nullptr,
                            uint8_t *invalidCode = nullptr);
bool epdDisplayFrame(const uint8_t *frame, size_t len);
bool epdDisplayFrameAtFrequency(const uint8_t *frame, size_t len, uint32_t spiHz);
#if MF1750_ENABLE_UNKNOWN_PROBE
// Experimental builds only. The candidate code and complete frame layout are
// compiled into the binary; no caller-controlled pixel data or code is
// accepted. The public six-colour validators above remain unchanged.
// This performs the exact same panel-I/O-free fixture validation used by the
// action path, but never initializes GPIO/SPI or issues panel commands.
bool epdValidateCompiledUnknownProbeFixture();
bool epdDisplayCompiledUnknownProbe();
#endif
#if MF1750_ENABLE_SIXSTATE_PROBE
// Stage-B-only fixed fixtures. No raw frame or caller-controlled colour enters
// this API: the selected role is generated and deeply validated in the driver
// before panel I/O. Candidate 0x4/0x7 remains a compile-time build identity.
enum class EpdSixStateRole : uint8_t { Primer = 0, Target = 1, White = 2 };
bool epdValidateCompiledSixStateFixtures();
bool epdDisplayCompiledSixState(EpdSixStateRole role);
#endif
#if MF1750_ENABLE_U04_U05_COMPARE
// Dedicated no-dither U04/U05 comparison fixture. The complete white-backed
// four-ROI frame is compiled into the binary and independently guarded before
// any panel I/O. No caller-controlled pixel data or colour code is accepted.
bool epdValidateCompiledU04U05CompareFixture();
bool epdDisplayCompiledU04U05Compare();
#endif
#if MF1750_ENABLE_EIGHTCODE_ATLAS
enum class EpdEightCodeAtlasRole : uint8_t {
  Atlas = 0,
  TargetU04 = 1,
  TargetU07 = 2,
  White = 3,
};
bool epdValidateCompiledEightCodeAtlasFixtures();
bool epdDisplayCompiledEightCodeAtlas(EpdEightCodeAtlasRole role);
#endif
#if MF1750_ENABLE_COLOR_LAB
enum class EpdColorLabRole : uint8_t {
  White = 0,
  U07Isolated = 1,
  Atlas = 2,
  U04SixStatePrimer = 3,
  U04SixStateTarget = 4,
  U07SixStatePrimer = 5,
  U07SixStateTarget = 6,
};
bool epdValidateCompiledColorLabFixtures();
bool epdDisplayCompiledColorLab(EpdColorLabRole role);
#endif
#if MF1750_ENABLE_OTP_TRANSITION_MATRIX
// Factory-OTP-only 8x8 old-to-new transition fixture. The full frame, both
// controller mappings, and all three role identities are compiled in and
// validated before panel I/O. This API never accepts a caller-provided frame,
// colour code, LUT, voltage, or refresh parameter.
enum class EpdOtpTransitionMatrixRole : uint8_t {
  Primer = 0,
  Target = 1,
  White = 2,
};
bool epdValidateCompiledOtpTransitionMatrixFixtures();
bool epdDisplayCompiledOtpTransitionMatrix(
    EpdOtpTransitionMatrixRole role);
#endif
#if MF1750_ENABLE_DITHER_COLOR_ATLAS
// Factory-OTP-only spatial dither fixture. Both complete frame roles and both
// mapped controller streams have frozen compiled identities that are checked
// before panel I/O. The API accepts no frame, colour code, LUT, voltage,
// waveform, SPI frequency, phase, timing, retry, or recovery parameter.
enum class EpdDitherColorAtlasRole : uint8_t {
  Atlas = 0,
  White = 1,
};
bool epdValidateCompiledDitherColorAtlasFixtures();
bool epdDisplayCompiledDitherColorAtlas(EpdDitherColorAtlasRole role);
#endif
#if MF1750_ENABLE_RUNTIME_LUT_EMPIRICAL_H3
// Isolated, empirical cross-generation H3 experiment. Each binary embeds one
// and only one generated vendor-profile candidate selected by the build. The
// API accepts no frame, profile, LUT, command, voltage, timing, SPI-frequency,
// retry, recovery, or controller-selection parameter.
enum class EpdEmpiricalH3Role : uint8_t {
  RuntimeEightCodeAtlas = 0,
};

struct EpdEmpiricalH3ProfileManifest {
  const char *profileId;
  const char *sourceArtifactSha256;
  const char *decodedPlaintextSha256;
  const char *decodedHeaderSha256;
  const char *powerPayloadSha256;
  const char *pllPayloadSha256;
  const char *r20PayloadSha256;
  const char *r21PayloadSha256;
  int apparentTemperatureMinC;
  int apparentTemperatureMaxC;
  int requestedGatePositiveMv;
  int requestedGateNegativeMv;
  int requestedFullSourcePositiveMv;
  int requestedFullSourceNegativeMv;
  int requestedVshLvMv;
  int requestedVslLvMv;
  int requestedVshLv2Mv;
  int requestedVslLv2Mv;
  unsigned requestedFrameRateHz;
  bool empiricalH3;
  bool panelOrFplLimitsProven;
  bool h3HeaderBindingProven;
  bool vendorProvenSequence;
  bool liveAuthorized;
  bool profileAutoSelected;
};

const EpdEmpiricalH3ProfileManifest &epdGetEmpiricalH3ProfileManifest();
bool epdValidateCompiledEmpiricalH3Fixtures();
bool epdDisplayCompiledEmpiricalH3(EpdEmpiricalH3Role role);
#endif
#if MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY
// Dedicated one-action recovery surface. The fixed white frame and both
// controller streams are validated before the hard-reset factory-OTP path.
// No runtime waveform/profile data or caller-selected parameter is accepted.
bool epdValidateCompiledFactoryOtpWhiteRecoveryFixture();
bool epdDisplayCompiledFactoryOtpWhiteRecovery();
#endif
bool epdClearWhite();
bool epdClearBlack();
