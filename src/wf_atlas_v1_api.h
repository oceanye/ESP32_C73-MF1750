#pragma once

#include <cstddef>
#include <cstdint>

// Waveform-variant atlas (layer-1 stable-colour expansion): the V4 compact
// atlas frame refreshed once per pinned profile.  Every action is a fixed
// compiled identity validated before any panel I/O.  This API accepts no
// frame, coordinate, colour code, LUT, voltage, timing, SPI-frequency,
// profile, retry, or recovery parameter.  Actions are never chained
// automatically.
enum class EpdWfAtlasRole : std::uint8_t {
  Variant0E = 0,
  Variant1C = 1,
  Variant1E = 2,
  Variant1D = 3,
  Variant0ER0R1 = 4,
  WhiteRecovery = 5,
};

struct EpdWfAtlasStepReport {
  std::uint8_t variant;
  std::uint32_t ponMs;
  std::uint32_t drfMs;
  std::uint32_t pofMs;
  std::uint32_t totalMs;
  bool ok;
};

bool epdValidateCompiledWfAtlasFixtures();
bool epdDisplayCompiledWfAtlas(EpdWfAtlasRole role);
const EpdWfAtlasStepReport *epdGetWfAtlasStepReports(std::size_t *count);
