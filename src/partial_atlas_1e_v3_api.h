#pragma once

#include <cstddef>
#include <cstdint>

// Partial-block route A V3 (P0 re-verification with normalization + probes):
// every action is a fixed compiled identity validated before any panel I/O.
// This API accepts no frame, coordinate, colour code, LUT, voltage, timing,
// SPI-frequency, retry, or recovery parameter.  Actions are never chained
// automatically; each runs only on its own explicit endpoint.
enum class EpdPartialAtlasV3Role : std::uint8_t {
  Normalize = 0,
  ProbeCode7 = 1,
  ProbeCode1 = 2,
  AtlasV2 = 3,
  WhiteRecovery = 4,
};

struct EpdPartialAtlasV3StepReport {
  std::uint32_t ponMs;
  std::uint32_t drfMs;
  std::uint32_t pofMs;
  std::uint32_t totalMs;
  bool ok;
};

bool epdValidateCompiledPartialAtlasV3Fixtures();
bool epdDisplayCompiledPartialAtlasV3(EpdPartialAtlasV3Role role);
const EpdPartialAtlasV3StepReport *epdGetPartialAtlasV3StepReports(
    std::size_t *count);
