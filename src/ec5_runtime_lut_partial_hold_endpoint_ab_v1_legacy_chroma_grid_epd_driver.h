#pragma once

#include "epd_driver.h"

// Extension-only declarations deliberately live outside epd_driver.h so the
// shared V10/core fixture surface remains byte-for-byte frozen.  Only the
// dedicated PlatformIO environment includes this header.
#if !defined(MF1750_ENABLE_CHROMA_GRID) || \
    MF1750_ENABLE_CHROMA_GRID != 1
#error "Chroma grid declarations require the isolated build"
#endif

enum class EpdChromaGridRole : uint8_t {
  White = 0,
  Source = 1,
  Mid = 2,
  Target = 3,
};

bool epdValidateCompiledChromaGridFixtures();
bool epdDisplayCompiledChromaGrid(EpdChromaGridRole role);
