#include "ec5_chroma_grid_epd_driver.h"

#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>

// epd_driver.cpp supplies the validated factory-OTP 0x11 white entry point.
// The shared repeat-PTLW include supplies the three cropped L535 actions.
#include "epd_driver.cpp"
#include "ec5_runtime_lut_partial_hold_repeat_ptlw_v1_driver.inc"
