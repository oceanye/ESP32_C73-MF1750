#pragma once

#include <Arduino.h>

// Isolated, non-visible high-voltage power-path qualifier.  Its only panel
// command path is RESET/REV readiness followed by one PON -> POF probe.
// No image RAM, waveform table, partial-window, or display-refresh API exists
// in this header.

struct Ec5PowerQualifierRevisionSample {
  bool idle = false;
  uint8_t bytes[3] = {0, 0, 0};
};

struct Ec5PowerQualifierReadinessReport {
  bool valid = false;
  bool qualified = false;
  bool cs1Stable = false;
  bool cs2Stable = false;
  bool cs1Nontrivial = false;
  bool cs2Nontrivial = false;
  uint8_t entryBusy = 0xFF;
  uint8_t finalBusy = 0xFF;
  uint8_t finalRst = 0xFF;
  uint8_t finalCs1 = 0xFF;
  uint8_t finalCs2 = 0xFF;
  uint8_t finalSck = 0xFF;
  uint8_t finalDc = 0xFF;
  uint8_t finalMosi = 0xFF;
  uint32_t finalHighStableMs = 0;
  uint32_t totalMs = 0;
  uint8_t resetCount = 0;
  uint8_t revisionReadCount = 0;
  uint8_t revisionCommandTrace[4] = {};
  Ec5PowerQualifierRevisionSample cs1[2];
  Ec5PowerQualifierRevisionSample cs2[2];
  char failureStage[40] = "none";
};

struct Ec5PowerQualifierProbeReport {
  bool valid = false;
  bool running = false;
  bool sequenceOk = false;
  bool waitTimedOut = false;
  bool busyAssertionMissing = false;
  bool preCommandIdleFailure = false;
  bool ponBusySeen = false;
  bool pofBusySeen = false;
  bool ponIdleCompleted = false;
  bool pofIdleCompleted = false;
  bool drfCommandSent = false;
  bool dtmCommandSent = false;
  bool lutCommandSent = false;
  bool ptlwCommandSent = false;
  bool command86Sent = false;
  bool ponCommandSent = false;
  bool pofCommandSent = false;
  bool postPsrCommandSent = false;
  uint32_t operationId = 0;
  uint32_t spiHz = 0;
  uint32_t totalMs = 0;
  uint32_t ponWaitMs = 0;
  uint32_t pofWaitMs = 0;
  uint32_t ponAssertionLatencyMs = 0;
  uint32_t pofAssertionLatencyMs = 0;
  uint32_t postPsrWaitMs = 0;
  uint8_t ponGateEntry = 0xFF;
  uint8_t pofGateEntry = 0xFF;
  uint8_t safeFinishBusyBeforePinsLow = 0xFF;
  uint8_t safeFinishBusyAfterPinsLow = 0xFF;
  uint8_t safeFinishBusyAfter5Ms = 0xFF;
  uint8_t finalBusy = 0xFF;
  uint8_t finalRst = 0xFF;
  uint8_t finalCs1 = 0xFF;
  uint8_t finalCs2 = 0xFF;
  uint8_t finalSck = 0xFF;
  uint8_t finalDc = 0xFF;
  uint8_t finalMosi = 0xFF;
  uint8_t commandCount = 0;
  uint8_t commandTrace[24] = {};
  uint16_t wireEventCount = 0;
  uint32_t wireFnv1a = 2166136261UL;
  char timeoutStage[24] = "none";
  char busyMissingStage[24] = "none";
  char preCommandBusyStage[24] = "none";
  char failureStage[40] = "none";
};

void ec5PowerQualifierBegin();
void ec5PowerQualifierForceSafeHold();
int ec5PowerQualifierReadBusy();
bool ec5PowerQualifierRunReadinessOnce();
bool ec5PowerQualifierRunPonPofOnce();
const Ec5PowerQualifierReadinessReport &ec5PowerQualifierReadinessReport();
const Ec5PowerQualifierProbeReport &ec5PowerQualifierProbeReport();
String ec5PowerQualifierReadinessJson();
String ec5PowerQualifierProbeJson();
