// The environment excludes epd_driver.cpp as a standalone source, so this
// isolated translation unit owns exactly one copy of the common implementation.

#include "ec5_h3_c23_matched_control_driver.h"

#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>

#include "epd_driver.cpp"
#include "ec5_h3_c23_matched_control_driver.inc"

