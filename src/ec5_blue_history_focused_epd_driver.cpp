// Dedicated translation-unit wrapper for the fixed blue-history branch.
// The shared driver is included verbatim and the extension is appended only in
// this build, leaving src/epd_driver.cpp and src/epd_driver.h untouched for all
// core firmware identities.

#include "ec5_blue_history_focused_epd_driver.h"

#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>

#include "epd_driver.cpp"
#include "ec5_blue_history_focused_driver.inc"
