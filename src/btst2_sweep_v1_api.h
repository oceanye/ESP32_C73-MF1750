#pragma once

#include <cstddef>
#include <cstdint>

// BTST2[3] ladder sweep: four compile-time-pinned rung actions plus the
// factory-OTP white recovery.  Every action is a fixed compiled identity
// validated before any panel I/O.  This API accepts no frame, coordinate,
// colour code, LUT, voltage, timing, SPI-frequency, rung value, retry, or
// recovery parameter.  Actions are never chained automatically.
enum class EpdBtst2SweepRole : std::uint8_t {
  RungS17 = 0,
  RungS29 = 1,
  RungS39 = 2,
  RungS49 = 3,
  WhiteRecovery = 4,
};

struct EpdBtst2SweepStepReport {
  std::uint8_t rung;
  std::uint32_t ponMs;
  std::uint32_t drfMs;
  std::uint32_t pofMs;
  std::uint32_t totalMs;
  bool ok;
};

bool epdValidateCompiledBtst2SweepFixtures();
bool epdDisplayCompiledBtst2Sweep(EpdBtst2SweepRole role);
const EpdBtst2SweepStepReport *epdGetBtst2SweepStepReports(
    std::size_t *count);
