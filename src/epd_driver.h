#pragma once

#include <Arduino.h>

static constexpr const char *EPD_DRIVER_API_VERSION = "MF1750_R16_CASCADE_V2";

struct EpdOperationReport {
  // Non-zero u32 sequence for this boot. A new value is allocated before
  // every result-bearing driver operation, including rejected operations;
  // main.cpp rejects a wrap instead of binding it as fresh.
  uint32_t operationId = 0;
  bool valid = false;
  bool running = false;
  bool sequenceOk = false;
  bool waitTimedOut = false;
  bool busyAssertionMissing = false;
  bool mappingApplied = false;
  bool ponBusySeen = false;
  bool drfBusySeen = false;
  bool pofBusySeen = false;
  bool postPsrBusySeen = false;
  uint32_t spiHz = 0;
  uint32_t inputFrameFnv1a = 0;
  uint32_t cs1DtmFnv1a = 0;
  uint32_t cs2DtmFnv1a = 0;
  uint32_t totalMs = 0;
  uint32_t cs1UploadMs = 0;
  uint32_t cs2UploadMs = 0;
  uint32_t ponWaitMs = 0;
  uint32_t drfWaitMs = 0;
  uint32_t pofWaitMs = 0;
  uint32_t postPsrWaitMs = 0;
  uint32_t lastWaitMs = 0;
  char lastWaitStage[32] = "none";
  char timeoutStage[32] = "none";
  char busyMissingStage[32] = "none";
};

void epdBegin();
int epdReadBusy();
const EpdOperationReport &epdGetLastOperationReport();
// Canonical physical frame codes are 0/1/2/3/5/6. Both helpers are side-effect
// free; every display entry point also validates before any panel I/O.
bool epdIsSupportedColorCode(uint8_t color);
bool epdValidateFrameColors(const uint8_t *frame, size_t len,
                            size_t *invalidPixel = nullptr,
                            uint8_t *invalidCode = nullptr);
bool epdDisplayFrame(const uint8_t *frame, size_t len);
bool epdDisplayFrameAtFrequency(const uint8_t *frame, size_t len, uint32_t spiHz);
bool epdClearWhite();
bool epdClearBlack();
