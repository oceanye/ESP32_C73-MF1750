#include "epd_driver.h"

#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>

// Compile the sealed shared driver without its original single-profile H3
// implementation, then attach the isolated dual-R20 candidate below.  The
// public H3 declarations remain enabled through the build flags seen by
// epd_driver.h.
#undef MF1750_ENABLE_RUNTIME_LUT_EMPIRICAL_H3
#define MF1750_ENABLE_RUNTIME_LUT_EMPIRICAL_H3 0
#include "epd_driver.cpp"

#undef MF1750_ENABLE_RUNTIME_LUT_EMPIRICAL_H3
#define MF1750_ENABLE_RUNTIME_LUT_EMPIRICAL_H3 1
#include "ec5_controller_code_map_driver.inc"
