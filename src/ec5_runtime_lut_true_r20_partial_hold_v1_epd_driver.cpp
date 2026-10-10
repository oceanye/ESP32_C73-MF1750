#include "ec5_chroma_grid_epd_driver.h"

#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>

// Reuse only the live-proven clean-PTLW transport and exact per-action REV
// qualifier. The compile-time branch below selects complete active/commented
// PWR/PLL/R20/R21 tuples symmetrically for both controllers.
#include "epd_driver.cpp"
#include "ec5_runtime_lut_true_r20_partial_hold_v1_driver.inc"
#include "ec5_runtime_lut_true_r20_partial_hold_v1_qualifier.inc"
