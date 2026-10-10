// This isolated translation-unit wrapper deliberately reuses the exact private
// factory-init, cascade, mapped-DTM, BUSY, refresh, and safe-finish helpers from
// epd_driver.cpp without modifying the already frozen V4 H3/recovery sources.
// The PlatformIO environment excludes epd_driver.cpp as a standalone source,
// so there is exactly one copy of the common driver implementation.

#include "ec5_h3_matched_control_driver.h"

#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>

#include "epd_driver.cpp"
#include "ec5_h3_matched_control_driver.inc"
