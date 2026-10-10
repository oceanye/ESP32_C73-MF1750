#include "ec5_chroma_grid_epd_driver.h"

#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>

// Mechanical payload reuse from the sealed V1B experiment, compiled under a
// fresh identity.  The per-action qualifier is included in this translation
// unit so it can explicitly stop the shared SPI state before bit-bang REV.
#include "epd_driver.cpp"
#include "ec5_runtime_lut_ptlw_fullframe_ab_v2_driver.inc"
#include "ec5_runtime_lut_ptlw_fullframe_ab_v2_qualifier.inc"
