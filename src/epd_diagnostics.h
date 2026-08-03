#pragma once

#include "epd_driver.h"

// Bring-up and historical matrix functions. Application code should include
// epd_driver.h only and should not call these routes during normal operation.
void epdResetOnly();
void epdDiagnosticSetCsLevel(bool high);
void epdDiagnosticSetCs2Level(bool high);
void epdDiagnosticReleasePins();
String epdDiagnosticReportJson();
String epdDiagnosticReadRevisionsJson();
bool epdDiagnosticSolid(uint16_t tresWidth,
                        uint16_t tresHeight,
                        size_t streamBytes,
                        uint8_t fillByte,
                        uint32_t spiHz);
bool epdDiagnosticCs1ColorBars(uint32_t spiHz);
bool epdDiagnosticDualSolid(uint8_t firstFillByte,
                            uint8_t secondFillByte,
                            uint32_t spiHz);
bool epdDiagnosticDualCascadeSolid(uint8_t firstFillByte,
                                   uint8_t secondFillByte,
                                   uint32_t spiHz);
bool epdDiagnosticDualCascadeColorBars(uint32_t spiHz);
bool epdDiagnosticCascadeGlobalColorBars(uint32_t spiHz);
bool epdDiagnosticCascadeGlobalHorizontalBars(uint32_t spiHz);
bool epdDisplayColorBars();
bool epdDisplayHalfWhiteHalfBlack();
void epdDisplayColorBars800x480();
void epdDisplayColorBars512x600();
bool epdDisplayColorBarsSwapped();
bool epdDisplayHorizontalBars();
void epdDisplayColorBars8bpp();
bool epdDisplayColorBarsCs2Probe();
void epdClearWhite800x480();
void epdClearBlack800x480();
void epdClearWhite512x600();
void epdClearBlack512x600();
