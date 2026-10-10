#include "ec5_chroma_grid_epd_driver.h"

#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>

// The guard transaction is frozen in an isolated include so later experiments
// cannot displace the already-executed Endpoint V1 source or artifact binding.
#include "epd_driver.cpp"
#include "ec5_runtime_lut_partial_hold_guard_direction_ab_v1_driver.inc"
