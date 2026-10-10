// Isolated D1-512 translation-unit wrapper.  It reuses the frozen production
// driver and appends only the fixed single-pixel history-cube fixture.

#include "ec5_chroma_grid_epd_driver.h"

#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>

#include "epd_driver.cpp"
#include "ec5_single_pixel_cube_driver.inc"
