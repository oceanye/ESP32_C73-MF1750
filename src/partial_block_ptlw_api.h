#pragma once

#include <cstdint>

// Partial-block route B (P1-P3): clean-PTLW cross-waveform partial-window
// fixture plus the factory-OTP white anchor/recovery actions.  Every action is
// a fixed compiled identity validated before any panel I/O.  This API accepts
// no frame, coordinate, colour code, LUT, voltage, timing, SPI-frequency,
// retry, or recovery parameter.  Actions are never chained automatically.
enum class EpdPartialBlockPtlwRole : std::uint8_t {
  FactoryWhite = 0,
  PatchA1E = 1,
  PatchB0E = 2,
  PatchC1C = 3,
  WhiteRecovery = 4,
};
bool epdValidateCompiledPartialBlockPtlwFixtures();
bool epdDisplayCompiledPartialBlockPtlw(EpdPartialBlockPtlwRole role);
