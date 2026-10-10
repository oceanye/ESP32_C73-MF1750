#pragma once

#include "epd_driver.h"

// Extension-only declarations deliberately live outside epd_driver.h so the
// shared V10/core fixture surface remains byte-for-byte frozen.  Only the
// dedicated PlatformIO environment includes this header.
#if !defined(MF1750_ENABLE_BLUE_HISTORY_FOCUSED) || \
    MF1750_ENABLE_BLUE_HISTORY_FOCUSED != 1
#error "Blue history focused declarations require the isolated build"
#endif

enum class EpdBlueHistoryFocusedRole : uint8_t {
  APrimer = 0,
  ATarget = 1,
  White = 2,
  APrimePrimer = 3,
  APrimeTarget = 4,
};

bool epdValidateCompiledBlueHistoryFocusedFixtures();
bool epdDisplayCompiledBlueHistoryFocused(
    EpdBlueHistoryFocusedRole role);
