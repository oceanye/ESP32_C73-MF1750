#pragma once

#include <Arduino.h>

#include "epd_driver.h"

#ifndef MF1750_ENABLE_H3_C23_MATCHED_NO_R20_R21
#define MF1750_ENABLE_H3_C23_MATCHED_NO_R20_R21 0
#endif

#ifndef MF1750_H3_C23_MATCHED_CONTROL_PROFILE_WF23_25
#define MF1750_H3_C23_MATCHED_CONTROL_PROFILE_WF23_25 0
#endif

#if MF1750_ENABLE_H3_C23_MATCHED_NO_R20_R21 != 1
#error "C23 matched driver requires its explicit fixture flag"
#endif

#if MF1750_H3_C23_MATCHED_CONTROL_PROFILE_WF23_25 != 1
#error "C23 matched driver requires the frozen WF23_25 profile"
#endif

#if MF1750_ENABLE_UNKNOWN_PROBE || MF1750_ENABLE_SIXSTATE_PROBE || \
    MF1750_ENABLE_U04_U05_COMPARE || MF1750_ENABLE_EIGHTCODE_ATLAS || \
    MF1750_ENABLE_COLOR_LAB || MF1750_ENABLE_OTP_TRANSITION_MATRIX || \
    MF1750_ENABLE_DITHER_COLOR_ATLAS || \
    MF1750_ENABLE_RUNTIME_LUT_EMPIRICAL_H3 || \
    MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY || \
    MF1750_RUNTIME_LUT_PROFILE_WF20_25 || \
    MF1750_RUNTIME_LUT_PROFILE_WF23_25 || \
    MF1750_OTP_WHITE_FOR_PROFILE_WF20_25 || \
    MF1750_OTP_WHITE_FOR_PROFILE_WF23_25 || \
    MF1750_ENABLE_H3_MATCHED_NO_R20_R21 || \
    MF1750_H3_MATCHED_CONTROL_PROFILE_WF20_25 || \
    MF1750_ENABLE_H3_C23_MATCHED_WHITE
#error "C23 matched control must be isolated from every other fixture"
#endif

enum class EpdH3C23MatchedControlRole : uint8_t {
  EightCodeAtlasWithoutR20R21 = 0,
};

struct EpdH3C23MatchedControlManifest {
  const char *profileId;
  const char *sourceArtifactSha256;
  const char *decodedHeaderSha256;
  const char *powerPayloadSha256;
  const char *pllPayloadSha256;
  const char *atlasFrameSha256;
  const char *atlasCs1DtmSha256;
  const char *atlasCs2DtmSha256;
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
  bool empiricalCrossVersion;
  bool matchedNegativeControl;
  bool r20CommandPresent;
  bool r21CommandPresent;
  bool runtimePayloadPresent;
  bool vendorProvenSequence;
  bool liveAuthorized;
  bool profileAutoSelected;
};

const EpdH3C23MatchedControlManifest &
epdGetH3C23MatchedControlManifest();
bool epdValidateCompiledH3C23MatchedControlFixture();
bool epdDisplayCompiledH3C23MatchedControl(EpdH3C23MatchedControlRole role);

