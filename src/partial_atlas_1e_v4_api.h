#pragma once

#include <cstddef>
#include <cstdint>

// Partial-block route A V4 (compact atlas in the visible camera window):
// every action is a fixed compiled identity validated before any panel I/O.
// This API accepts no frame, coordinate, colour code, LUT, voltage, timing,
// SPI-frequency, retry, or recovery parameter.  Actions are never chained
// automatically; each runs only on its own explicit endpoint.
enum class EpdPartialAtlasV4Role : std::uint8_t {
  Normalize = 0,
  Atlas = 1,
  WhiteRecovery = 2,
};

struct EpdPartialAtlasV4StepReport {
  std::uint32_t ponMs;
  std::uint32_t drfMs;
  std::uint32_t pofMs;
  std::uint32_t totalMs;
  bool ok;
};

bool epdValidateCompiledPartialAtlasV4Fixtures();
bool epdDisplayCompiledPartialAtlasV4(EpdPartialAtlasV4Role role);
const EpdPartialAtlasV4StepReport *epdGetPartialAtlasV4StepReports(
    std::size_t *count);
