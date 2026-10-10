#include "ec5_chroma_grid_epd_driver.h"

#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>

// Factory-OTP white and the three cropped L535 actions share the validated
// base driver. V3 changes identities and adds BUSY qualification in main only.
#include "epd_driver.cpp"
#include "ec5_runtime_lut_partial_hold_repeat_ptlw_v1_driver.inc"
