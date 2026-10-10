#include "ec5_chroma_grid_epd_driver.h"

#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>

// Isolated A/B transport comparison.  The shared driver supplies the proven
// cascade initialization, factory-OTP white action, and safe power finish;
// all treatment-specific transport remains in the private include below.
#include "epd_driver.cpp"
#include "ec5_runtime_lut_ptlw_fullframe_ab_v1_driver.inc"

