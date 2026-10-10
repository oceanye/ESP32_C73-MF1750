#pragma once

#include <Arduino.h>

struct Ec5FullframePtlwV2RevisionSample {
  bool idle = false;
  uint8_t bytes[3] = {0, 0, 0};
};

struct Ec5FullframePtlwV2ReadinessReport {
  bool valid = false;
  bool qualified = false;
  bool cs1Stable = false;
  bool cs2Stable = false;
  bool cs1Nontrivial = false;
  bool cs2Nontrivial = false;
  bool cs1Exact010104 = false;
  bool cs2Exact010104 = false;
  bool allRevisionSamplesExact010104 = false;
  uint8_t ordinal = 0;
  uint8_t entryBusy = 0xFF;
  uint8_t finalBusy = 0xFF;
  uint8_t finalRst = 0xFF;
  uint8_t finalCs1 = 0xFF;
  uint8_t finalCs2 = 0xFF;
  uint8_t finalSck = 0xFF;
  uint8_t finalDc = 0xFF;
  uint8_t finalMosi = 0xFF;
  uint8_t resetCount = 0;
  uint8_t revisionReadCount = 0;
  uint8_t revisionCommandTrace[4] = {};
  uint32_t operationId = 0;
  uint32_t finalHighStableMs = 0;
  uint32_t totalMs = 0;
  Ec5FullframePtlwV2RevisionSample cs1[2];
  Ec5FullframePtlwV2RevisionSample cs2[2];
  char failureStage[48] = "none";
};

bool ec5FullframePtlwV2RunPerActionReadinessOnce(uint8_t ordinal);
void ec5FullframePtlwV2ResetReadinessEvidence();
const Ec5FullframePtlwV2ReadinessReport &
ec5FullframePtlwV2GetReadinessReport();
String ec5FullframePtlwV2ReadinessJson();
void ec5FullframePtlwV2ForceSafeHold();
