#include "ec5_chroma_grid_epd_driver.h"

#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>

// Reuse the live-proven Fullframe/PTLW V2 action transport and per-action REV
// qualifier under a fresh cross-profile HOLD identity.
#include "epd_driver.cpp"
#include "ec5_runtime_lut_cross_palette_partial_hold_v2_driver.inc"
#include "ec5_runtime_lut_ptlw_fullframe_ab_v2_qualifier.inc"
