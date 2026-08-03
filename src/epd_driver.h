#pragma once

#include <Arduino.h>

static constexpr const char *EPD_DRIVER_API_VERSION = "MF1750_R16_CASCADE_V1";

struct EpdOperationReport {
  bool valid = false;
  bool running = false;
  bool sequenceOk = false;
  bool waitTimedOut = false;
  bool mappingApplied = false;
  uint32_t spiHz = 0;
  uint32_t inputFrameFnv1a = 0;
  uint32_t cs1DtmFnv1a = 0;
  uint32_t cs2DtmFnv1a = 0;
  uint32_t totalMs = 0;
  uint32_t cs1UploadMs = 0;
  uint32_t cs2UploadMs = 0;
  uint32_t lastWaitMs = 0;
  char lastWaitStage[32] = "none";
  char timeoutStage[32] = "none";
};

void epdBegin();
int epdReadBusy();
const EpdOperationReport &epdGetLastOperationReport();
bool epdDisplayFrame(const uint8_t *frame, size_t len);
bool epdDisplayFrameAtFrequency(const uint8_t *frame, size_t len, uint32_t spiHz);
bool epdClearWhite();
bool epdClearBlack();
