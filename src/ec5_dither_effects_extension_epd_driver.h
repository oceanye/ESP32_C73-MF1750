#pragma once

#include "epd_driver.h"

// Extension-only declarations deliberately live outside epd_driver.h so the
// shared V10/core fixture surface remains byte-for-byte frozen.  Only the
// dedicated PlatformIO environment includes this header.
#if !defined(MF1750_ENABLE_DITHER_EFFECTS_EXTENSION) || \
    MF1750_ENABLE_DITHER_EFFECTS_EXTENSION != 1
#error "Dither effects extension declarations require the isolated build"
#endif

enum class EpdDitherEffectsExtensionRole : uint8_t {
  PairGradients = 0,
  EffectsChart = 1,
  White = 2,
};

bool epdValidateCompiledDitherEffectsExtensionFixtures();
bool epdDisplayCompiledDitherEffectsExtension(
    EpdDitherEffectsExtensionRole role);
