#pragma once

#include "epd_driver.h"

#if !defined(MF1750_PARTIAL_HOLD_WARM_SESSION_V1_BUILD) || \
    MF1750_PARTIAL_HOLD_WARM_SESSION_V1_BUILD != 1
#error "Warm-session declarations require the isolated V1 build"
#endif

enum class EpdPartialHoldWarmRole : uint8_t {
  WhiteBaseline = 0,
  RedA = 1,
  BlueB = 2,
  GreenC = 3,
  WhiteRecovery = 4,
};

enum class EpdPartialHoldWarmState : uint8_t {
  Cold = 0,
  WarmExpectRed = 1,
  WarmExpectBlue = 2,
  WarmExpectGreen = 3,
  WarmExpectRecovery = 4,
  Closed = 5,
  Fault = 6,
};

bool epdValidateCompiledPartialHoldWarmSessionFixtures();
bool epdDisplayCompiledPartialHoldWarmSession(EpdPartialHoldWarmRole role);
bool epdServicePartialHoldWarmSession();
bool epdAbortPartialHoldWarmSession(const char *failureStage);
EpdPartialHoldWarmState epdGetPartialHoldWarmSessionState();
uint32_t epdGetPartialHoldWarmSessionRemainingMs();
