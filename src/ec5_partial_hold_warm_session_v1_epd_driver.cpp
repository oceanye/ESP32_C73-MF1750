// Fully isolated warm-session driver.  The exact reviewed V4 PTLW helpers are
// compiled under unreachable renamed cold entry points, then the warm-only
// public state machine is appended.

#include "ec5_partial_hold_warm_session_v1_epd_driver.h"
#include "ec5_chroma_grid_epd_driver.h"

#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>

#include "epd_driver.cpp"

#define epdValidateCompiledChromaGridFixtures \
  epdValidateColdV4FixturesUnreachable
#define epdDisplayCompiledChromaGrid epdDisplayColdV4Unreachable
#include "ec5_runtime_lut_partial_hold_v4_driver.inc"
#undef epdDisplayCompiledChromaGrid
#undef epdValidateCompiledChromaGridFixtures

#include "ec5_partial_hold_warm_session_v1_driver.inc"
