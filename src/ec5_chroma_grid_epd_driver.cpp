// Dedicated translation-unit wrapper for the fixed chroma-history grid.
// The shared driver is included verbatim and the extension is appended only in
// this build, leaving src/epd_driver.cpp and src/epd_driver.h untouched for all
// core firmware identities.

#include "ec5_chroma_grid_epd_driver.h"

#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>

#include "epd_driver.cpp"
#include "ec5_chroma_grid_driver.inc"
