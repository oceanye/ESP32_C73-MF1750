#include "ec5_chroma_grid_epd_driver.h"

#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>

// Reuse the reviewed repeat-PTLW transaction.  The isolated identity adds
// per-controller Y-end treatments; no runtime coordinate/code ingress exists.
#include "epd_driver.cpp"
#include "ec5_runtime_lut_partial_hold_repeat_ptlw_v1_driver.inc"
