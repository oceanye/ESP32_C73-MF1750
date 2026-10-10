#pragma once

// Side-effect-free Stage III-B frame generator.  This is not a partial-
// refresh implementation.  A future selected palette A writes BaseRows;
// selected palette B then writes OverlayColumns, producing all 8x8
// source-state -> target-code transitions per controller in one full scan.

#include <cstddef>
#include <cstdint>
#include <cstring>

enum class EpdHoldMatrixRole : uint8_t { BaseRows = 0, OverlayColumns = 1 };

static constexpr uint16_t HOLD_MATRIX_ROWS = 8;
static constexpr uint16_t HOLD_MATRIX_COLUMNS_PER_CONTROLLER = 8;
static constexpr uint16_t HOLD_MATRIX_CELL_WIDTH = 64;
static constexpr uint16_t HOLD_MATRIX_CELL_HEIGHT = 75;
static constexpr size_t HOLD_MATRIX_PIXELS_PER_CODE = 76800;
static constexpr char HOLD_MATRIX_BASE_FRAME_SHA256[] =
    "06be3a9df65efdf86dc1552015daf16d6e2c59c06747a5291957c9c816d746e3";
static constexpr char HOLD_MATRIX_OVERLAY_FRAME_SHA256[] =
    "c645344fa4daa0429d47626ca35e9be770e78684fac47f7bc9ebdb2fa10b85f8";
static constexpr char HOLD_MATRIX_BASE_DTM_SHA256[] =
    "2dca869c3aa632a935dae5ac6128739ea1f20ccd40dc2fa624ff38a43e438727";
static constexpr char HOLD_MATRIX_OVERLAY_DTM_SHA256[] =
    "d7f6b57a34ada52393719946c89d76934a5f802a8b95a0a8d8cf61d750df7196";
static constexpr uint32_t HOLD_MATRIX_BASE_FRAME_FNV1A = 0xDA9655C5UL;
static constexpr uint32_t HOLD_MATRIX_OVERLAY_FRAME_FNV1A = 0xB52D15C5UL;
static constexpr uint32_t HOLD_MATRIX_BASE_DTM_FNV1A = 0xCAE179C5UL;
static constexpr uint32_t HOLD_MATRIX_OVERLAY_DTM_FNV1A = 0x5FE4D9C5UL;

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600 &&
                  EPD_FRAME_BYTES == 307200 &&
                  EPD_CONTROLLER_WIDTH == 512,
              "hold matrix requires the frozen MF1750 geometry");
static_assert(HOLD_MATRIX_COLUMNS_PER_CONTROLLER * HOLD_MATRIX_CELL_WIDTH ==
                  EPD_CONTROLLER_WIDTH &&
                  HOLD_MATRIX_ROWS * HOLD_MATRIX_CELL_HEIGHT == EPD_HEIGHT,
              "hold matrix must cover both halves without gaps");

bool epdBuildHoldMatrixFrame(EpdHoldMatrixRole role, uint8_t *frame,
                             uint32_t histogram[8]) {
  if (!frame || !histogram) return false;
  std::memset(histogram, 0, 8 * sizeof(uint32_t));
  static constexpr size_t kRowBytes = EPD_WIDTH / 2;
  for (uint16_t y = 0; y < EPD_HEIGHT; ++y) {
    const uint8_t sourceCode = static_cast<uint8_t>(y / HOLD_MATRIX_CELL_HEIGHT);
    for (uint16_t x = 0; x < EPD_WIDTH; x += 2) {
      const uint16_t localX = x % EPD_CONTROLLER_WIDTH;
      const uint8_t targetCode =
          static_cast<uint8_t>(localX / HOLD_MATRIX_CELL_WIDTH);
      const uint8_t code = role == EpdHoldMatrixRole::BaseRows
                               ? sourceCode
                               : targetCode;
      frame[static_cast<size_t>(y) * kRowBytes + x / 2] =
          static_cast<uint8_t>((code << 4) | code);
      histogram[code] += 2;
    }
  }
  for (uint8_t code = 0; code < 8; ++code) {
    if (histogram[code] != HOLD_MATRIX_PIXELS_PER_CODE) return false;
  }
  return true;
}

