#include "ec5_runtime_lut_ptlw_fullframe_ab_v2_qualifier.h"

#if (!defined(MF1750_RUNTIME_LUT_PTLW_FULLFRAME_AB_V2_BUILD) || \
     MF1750_RUNTIME_LUT_PTLW_FULLFRAME_AB_V2_BUILD != 1) && \
    (!defined(MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V2_BUILD) || \
     MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V2_BUILD != 1)
#error "clean-PTLW V2 qualifier requires an isolated build"
#endif

#if EPD_USE_3WIRE_9BIT
#error "Per-action dual-controller REV qualification requires 4-wire mode"
#endif

namespace {

static constexpr uint8_t FFABV2_REV = 0x70;
static constexpr uint32_t FFABV2_RESET_IDLE_TIMEOUT_MS = 3000UL;
static constexpr uint32_t FFABV2_STABLE_HIGH_MS = 50UL;

Ec5FullframePtlwV2ReadinessReport ffabV2Readiness;
uint32_t ffabV2ReadinessOperationCounter = 0;

void ffabV2CopyStage(char *destination, size_t size, const char *source) {
  if (size == 0) return;
  std::strncpy(destination, source, size - 1);
  destination[size - 1] = '\0';
}

void ffabV2WriteSelectedCs(uint8_t level) {
  if (activeCs1) digitalWrite(EPD_PIN_CS, level);
  if (activeCs2) setPinIfConnected(EPD_PIN_CS2, level);
}

void ffabV2BitBangWrite8(uint8_t dcx, uint8_t value) {
  digitalWrite(EPD_PIN_DC, dcx ? HIGH : LOW);
  pinMode(EPD_PIN_MOSI, OUTPUT);
  digitalWrite(EPD_PIN_SCK, LOW);
  ffabV2WriteSelectedCs(LOW);
  delayMicroseconds(2);
  for (uint8_t mask = 0x80; mask; mask >>= 1) {
    digitalWrite(EPD_PIN_MOSI, (value & mask) ? HIGH : LOW);
    delayMicroseconds(2);
    digitalWrite(EPD_PIN_SCK, HIGH);
    delayMicroseconds(2);
    digitalWrite(EPD_PIN_SCK, LOW);
  }
  ffabV2WriteSelectedCs(HIGH);
}

uint8_t ffabV2BitBangRead8() {
  uint8_t value = 0;
  digitalWrite(EPD_PIN_DC, HIGH);
  digitalWrite(EPD_PIN_SCK, LOW);
  pinMode(EPD_PIN_MOSI, INPUT);
  delayMicroseconds(2);
  ffabV2WriteSelectedCs(LOW);
  delayMicroseconds(4);
  for (uint8_t bit = 0; bit < 8; ++bit) {
    value <<= 1;
    digitalWrite(EPD_PIN_SCK, HIGH);
    delayMicroseconds(2);
    if (digitalRead(EPD_PIN_MOSI)) value |= 1U;
    digitalWrite(EPD_PIN_SCK, LOW);
    delayMicroseconds(2);
  }
  ffabV2WriteSelectedCs(HIGH);
  pinMode(EPD_PIN_MOSI, OUTPUT);
  digitalWrite(EPD_PIN_MOSI, LOW);
  digitalWrite(EPD_PIN_DC, LOW);
  return value;
}

bool ffabV2WaitIdle(uint32_t timeoutMs) {
  const uint32_t started = millis();
  while (readBusyLevel() != 1U) {
    if (millis() - started > timeoutMs) return false;
    delay(1);
  }
  return true;
}

bool ffabV2WaitStableHigh(uint32_t stableMs, uint32_t timeoutMs) {
  const uint32_t started = millis();
  uint32_t highSince = 0;
  while (millis() - started <= timeoutMs) {
    if (readBusyLevel() == 1U) {
      if (highSince == 0) highSince = millis();
      if (millis() - highSince >= stableMs) return true;
    } else {
      highSince = 0;
    }
    delay(1);
  }
  return false;
}

void ffabV2PrepareRevisionSession() {
  epdStopHardwareSpi();
  digitalWrite(EPD_PIN_CS, HIGH);
  setPinIfConnected(EPD_PIN_CS2, HIGH);
  digitalWrite(EPD_PIN_SCK, LOW);
  digitalWrite(EPD_PIN_DC, LOW);
  pinMode(EPD_PIN_MOSI, OUTPUT);
  digitalWrite(EPD_PIN_MOSI, LOW);
  digitalWrite(EPD_PIN_RST, HIGH);
  setPinIfConnected(EPD_PIN_SWC, HIGH);
}

Ec5FullframePtlwV2RevisionSample ffabV2ReadRevisionAfterOwnReset(
    bool secondController) {
  Ec5FullframePtlwV2RevisionSample sample;
  // Reproduce the live-proven power-qualifier V2 transaction: per-sample
  // reset, MOSI-low pre-reset, and unchanged segmented-CS framing.
  setActiveControllers(false, false);
  digitalWrite(EPD_PIN_SCK, LOW);
  digitalWrite(EPD_PIN_DC, LOW);
  pinMode(EPD_PIN_MOSI, OUTPUT);
  digitalWrite(EPD_PIN_MOSI, LOW);
  epdReset();
  ++ffabV2Readiness.resetCount;
  sample.idle = ffabV2WaitIdle(FFABV2_RESET_IDLE_TIMEOUT_MS);
  if (!sample.idle) return sample;
  setActiveControllers(!secondController, secondController);
  ffabV2BitBangWrite8(0, FFABV2_REV);
  if (ffabV2Readiness.revisionReadCount < 4) {
    ffabV2Readiness.revisionCommandTrace[
        ffabV2Readiness.revisionReadCount] = FFABV2_REV;
  }
  ++ffabV2Readiness.revisionReadCount;
  for (uint8_t &byte : sample.bytes) byte = ffabV2BitBangRead8();
  return sample;
}

bool ffabV2Equal(const Ec5FullframePtlwV2RevisionSample &a,
                 const Ec5FullframePtlwV2RevisionSample &b) {
  return a.idle && b.idle &&
         std::memcmp(a.bytes, b.bytes, sizeof(a.bytes)) == 0;
}

bool ffabV2Nontrivial(const Ec5FullframePtlwV2RevisionSample &sample) {
  const bool zeros = sample.bytes[0] == 0 && sample.bytes[1] == 0 &&
                     sample.bytes[2] == 0;
  const bool ones = sample.bytes[0] == 0xFF && sample.bytes[1] == 0xFF &&
                    sample.bytes[2] == 0xFF;
  return !zeros && !ones;
}

bool ffabV2Exact010104(const Ec5FullframePtlwV2RevisionSample &sample) {
  return sample.idle && sample.bytes[0] == 0x01 &&
         sample.bytes[1] == 0x01 && sample.bytes[2] == 0x04;
}

void ffabV2SampleFinalGpio() {
  ffabV2Readiness.finalBusy = readBusyLevel();
  ffabV2Readiness.finalRst = digitalRead(EPD_PIN_RST) ? 1U : 0U;
  ffabV2Readiness.finalCs1 = digitalRead(EPD_PIN_CS) ? 1U : 0U;
  ffabV2Readiness.finalCs2 =
      EPD_PIN_CS2 >= 0 && digitalRead(EPD_PIN_CS2) ? 1U : 0U;
  ffabV2Readiness.finalSck = digitalRead(EPD_PIN_SCK) ? 1U : 0U;
  ffabV2Readiness.finalDc = digitalRead(EPD_PIN_DC) ? 1U : 0U;
  ffabV2Readiness.finalMosi = digitalRead(EPD_PIN_MOSI) ? 1U : 0U;
}

void ffabV2Fail(uint32_t started, const char *stage) {
  ffabV2CopyStage(ffabV2Readiness.failureStage,
                  sizeof(ffabV2Readiness.failureStage), stage);
  epdStopHardwareSpi();
  epdHoldPanelPinsLow();
  ffabV2SampleFinalGpio();
  ffabV2Readiness.totalMs = millis() - started;
}

String ffabV2Bool(bool value) { return value ? "true" : "false"; }

String ffabV2RevisionJson(const Ec5FullframePtlwV2RevisionSample &sample) {
  return String("{\"idle\":") + ffabV2Bool(sample.idle) +
         ",\"bytes\":[" + String(sample.bytes[0]) + "," +
         String(sample.bytes[1]) + "," + String(sample.bytes[2]) + "]}";
}

}  // namespace

void ec5FullframePtlwV2ForceSafeHold() {
  epdStopHardwareSpi();
  epdHoldPanelPinsLow();
}

void ec5FullframePtlwV2ResetReadinessEvidence() {
  ffabV2Readiness = Ec5FullframePtlwV2ReadinessReport{};
}

bool ec5FullframePtlwV2RunPerActionReadinessOnce(uint8_t ordinal) {
  const uint32_t started = millis();
  ffabV2Readiness = Ec5FullframePtlwV2ReadinessReport{};
  ffabV2Readiness.valid = true;
  ffabV2Readiness.ordinal = ordinal;
  ffabV2Readiness.entryBusy = readBusyLevel();
  ++ffabV2ReadinessOperationCounter;
  if (ffabV2ReadinessOperationCounter == 0) ++ffabV2ReadinessOperationCounter;
  ffabV2Readiness.operationId = ffabV2ReadinessOperationCounter;

  if (EPD_PIN_CS2 < 0) {
    ffabV2Fail(started, "cs2_disabled");
    return false;
  }
  ffabV2PrepareRevisionSession();
  ffabV2Readiness.cs1[0] = ffabV2ReadRevisionAfterOwnReset(false);
  if (!ffabV2Readiness.cs1[0].idle) {
    ffabV2Fail(started, "cs1_sample1_reset_busy");
    return false;
  }
  ffabV2Readiness.cs1[1] = ffabV2ReadRevisionAfterOwnReset(false);
  if (!ffabV2Readiness.cs1[1].idle) {
    ffabV2Fail(started, "cs1_sample2_reset_busy");
    return false;
  }
  ffabV2Readiness.cs2[0] = ffabV2ReadRevisionAfterOwnReset(true);
  if (!ffabV2Readiness.cs2[0].idle) {
    ffabV2Fail(started, "cs2_sample1_reset_busy");
    return false;
  }
  ffabV2Readiness.cs2[1] = ffabV2ReadRevisionAfterOwnReset(true);
  if (!ffabV2Readiness.cs2[1].idle) {
    ffabV2Fail(started, "cs2_sample2_reset_busy");
    return false;
  }

  ffabV2Readiness.cs1Stable =
      ffabV2Equal(ffabV2Readiness.cs1[0], ffabV2Readiness.cs1[1]);
  ffabV2Readiness.cs2Stable =
      ffabV2Equal(ffabV2Readiness.cs2[0], ffabV2Readiness.cs2[1]);
  ffabV2Readiness.cs1Nontrivial = ffabV2Nontrivial(ffabV2Readiness.cs1[1]);
  ffabV2Readiness.cs2Nontrivial = ffabV2Nontrivial(ffabV2Readiness.cs2[1]);
  ffabV2Readiness.cs1Exact010104 =
      ffabV2Exact010104(ffabV2Readiness.cs1[0]) &&
      ffabV2Exact010104(ffabV2Readiness.cs1[1]);
  ffabV2Readiness.cs2Exact010104 =
      ffabV2Exact010104(ffabV2Readiness.cs2[0]) &&
      ffabV2Exact010104(ffabV2Readiness.cs2[1]);
  ffabV2Readiness.allRevisionSamplesExact010104 =
      ffabV2Readiness.cs1Exact010104 && ffabV2Readiness.cs2Exact010104;

  setActiveControllers(false, false);
  digitalWrite(EPD_PIN_SCK, LOW);
  digitalWrite(EPD_PIN_DC, LOW);
  pinMode(EPD_PIN_MOSI, OUTPUT);
  digitalWrite(EPD_PIN_MOSI, LOW);
  epdReset();
  ++ffabV2Readiness.resetCount;
  const bool finalResetIdle = ffabV2WaitIdle(FFABV2_RESET_IDLE_TIMEOUT_MS);
  epdStopHardwareSpi();
  setActiveControllers(false, false);
  digitalWrite(EPD_PIN_CS, HIGH);
  setPinIfConnected(EPD_PIN_CS2, HIGH);
  digitalWrite(EPD_PIN_SCK, LOW);
  digitalWrite(EPD_PIN_DC, LOW);
  pinMode(EPD_PIN_MOSI, OUTPUT);
  digitalWrite(EPD_PIN_MOSI, LOW);
  digitalWrite(EPD_PIN_RST, HIGH);
  setPinIfConnected(EPD_PIN_SWC, HIGH);
  const bool stableHigh = finalResetIdle &&
      ffabV2WaitStableHigh(FFABV2_STABLE_HIGH_MS,
                           FFABV2_RESET_IDLE_TIMEOUT_MS);
  ffabV2SampleFinalGpio();
  ffabV2Readiness.finalHighStableMs =
      stableHigh ? FFABV2_STABLE_HIGH_MS : 0;
  ffabV2Readiness.qualified =
      ffabV2Readiness.cs1Stable && ffabV2Readiness.cs2Stable &&
      ffabV2Readiness.cs1Nontrivial && ffabV2Readiness.cs2Nontrivial &&
      ffabV2Readiness.allRevisionSamplesExact010104 &&
      ffabV2Readiness.resetCount == 5U && stableHigh &&
      ffabV2Readiness.finalBusy == 1U &&
      ffabV2Readiness.finalRst == 1U &&
      ffabV2Readiness.finalCs1 == 1U &&
      ffabV2Readiness.finalCs2 == 1U &&
      ffabV2Readiness.finalSck == 0U &&
      ffabV2Readiness.finalDc == 0U &&
      ffabV2Readiness.finalMosi == 0U;
  if (!ffabV2Readiness.qualified) {
    const char *failure =
        !ffabV2Readiness.cs1Stable
            ? "cs1_revision_unstable"
            : (!ffabV2Readiness.cs2Stable
                   ? "cs2_revision_unstable"
                   : (!ffabV2Readiness.cs1Nontrivial
                          ? "cs1_revision_trivial"
                          : (!ffabV2Readiness.cs2Nontrivial
                                 ? "cs2_revision_trivial"
                                 : (!ffabV2Readiness.cs1Exact010104
                                        ? "cs1_revision_not_010104"
                                        : (!ffabV2Readiness.cs2Exact010104
                                               ? "cs2_revision_not_010104"
                                               : (!finalResetIdle
                                                      ? "final_reset_busy_not_idle_high"
                                                      : "busy_or_gpio_posture_not_qualified"))))));
    ffabV2Fail(started, failure);
    return false;
  }
  ffabV2Readiness.totalMs = millis() - started;
  return true;
}

const Ec5FullframePtlwV2ReadinessReport &
ec5FullframePtlwV2GetReadinessReport() {
  return ffabV2Readiness;
}

String ec5FullframePtlwV2ReadinessJson() {
  return String("{\"valid\":") + ffabV2Bool(ffabV2Readiness.valid) +
         ",\"qualified\":" + ffabV2Bool(ffabV2Readiness.qualified) +
         ",\"operation_id\":" + String(ffabV2Readiness.operationId) +
         ",\"ordinal\":" + String(ffabV2Readiness.ordinal) +
         ",\"entry_busy\":" + String(ffabV2Readiness.entryBusy) +
         ",\"final_busy\":" + String(ffabV2Readiness.finalBusy) +
         ",\"final_gpio\":{\"rst\":" + String(ffabV2Readiness.finalRst) +
         ",\"cs1\":" + String(ffabV2Readiness.finalCs1) +
         ",\"cs2\":" + String(ffabV2Readiness.finalCs2) +
         ",\"sck\":" + String(ffabV2Readiness.finalSck) +
         ",\"dc\":" + String(ffabV2Readiness.finalDc) +
         ",\"mosi\":" + String(ffabV2Readiness.finalMosi) + "}" +
         ",\"final_high_stable_ms\":" +
         String(ffabV2Readiness.finalHighStableMs) +
         ",\"reset_count\":" + String(ffabV2Readiness.resetCount) +
         ",\"revision_read_count\":" +
         String(ffabV2Readiness.revisionReadCount) +
         ",\"revision_command_trace\":[" +
         String(ffabV2Readiness.revisionCommandTrace[0]) + "," +
         String(ffabV2Readiness.revisionCommandTrace[1]) + "," +
         String(ffabV2Readiness.revisionCommandTrace[2]) + "," +
         String(ffabV2Readiness.revisionCommandTrace[3]) + "]" +
         ",\"total_ms\":" + String(ffabV2Readiness.totalMs) +
         ",\"cs1\":{\"sample1\":" +
         ffabV2RevisionJson(ffabV2Readiness.cs1[0]) +
         ",\"sample2\":" + ffabV2RevisionJson(ffabV2Readiness.cs1[1]) +
         ",\"stable\":" + ffabV2Bool(ffabV2Readiness.cs1Stable) +
         ",\"nontrivial\":" + ffabV2Bool(ffabV2Readiness.cs1Nontrivial) +
         ",\"exact_010104\":" +
         ffabV2Bool(ffabV2Readiness.cs1Exact010104) + "},\"cs2\":{" +
         "\"sample1\":" + ffabV2RevisionJson(ffabV2Readiness.cs2[0]) +
         ",\"sample2\":" + ffabV2RevisionJson(ffabV2Readiness.cs2[1]) +
         ",\"stable\":" + ffabV2Bool(ffabV2Readiness.cs2Stable) +
         ",\"nontrivial\":" + ffabV2Bool(ffabV2Readiness.cs2Nontrivial) +
         ",\"exact_010104\":" +
         ffabV2Bool(ffabV2Readiness.cs2Exact010104) +
         "},\"all_revision_samples_exact_010104\":" +
         ffabV2Bool(ffabV2Readiness.allRevisionSamplesExact010104) +
         ",\"failure_stage\":\"" + ffabV2Readiness.failureStage + "\"}";
}
