#include "ec5_power_qualifier_pon_pof_no_drf_v2.h"

#include <SPI.h>

#include <cstdio>
#include <cstring>

#include "epd_config.h"

#if !defined(MF1750_POWER_QUALIFIER_PON_POF_NO_DRF_V2_BUILD) || \
    MF1750_POWER_QUALIFIER_PON_POF_NO_DRF_V2_BUILD != 1
#error "This source is restricted to the isolated PON/POF qualifier build"
#endif

#if EPD_ENABLE_TEST_PATTERN != 0
#error "The PON/POF qualifier must never refresh at startup"
#endif

#if EPD_USE_3WIRE_9BIT
#error "Stable per-controller revision reads require documented 4-wire mode"
#endif

namespace {

// Deliberately minimal command allowlist.  There is no display-refresh,
// image-RAM, waveform-table, partial-window, or undocumented 0x86 constant in
// this translation unit.
enum : uint8_t {
  kCmdPanelSetting = 0x00,
  kCmdPowerSetting = 0x01,
  kCmdPowerOff = 0x02,
  kCmdPowerOffSequence = 0x03,
  kCmdPowerOn = 0x04,
  kCmdBoosterSoftStart1 = 0x05,
  kCmdBoosterSoftStart2 = 0x06,
  kCmdBoosterSoftStart3 = 0x08,
  kCmdPll = 0x30,
  kCmdVcomInterval = 0x50,
  kCmdTcon = 0x60,
  kCmdResolution = 0x61,
  kCmdRevision = 0x70,
  kCmdTvdcs = 0x84,
  kCmdCascade = 0xE0,
  kCmdPowerSaving = 0xE3,
  kCmdVendorUnlock = 0xAA,
};

static constexpr uint32_t kSpiHz = 1000000UL;
static constexpr uint32_t kResetIdleTimeoutMs = 3000UL;
static constexpr uint32_t kPreCommandIdleTimeoutMs = 3000UL;
static constexpr uint32_t kBusyAssertionGraceMs = 250UL;
static constexpr uint32_t kPowerStageTimeoutMs = 60000UL;
static constexpr uint32_t kReadinessHighStableMs = 50UL;

Ec5PowerQualifierV2ReadinessReport readinessReport;
Ec5PowerQualifierV2ProbeReport probeReport;
uint32_t operationCounter = 0;
bool spiStarted = false;
bool sameBootReadinessQualified = false;
bool activeCs1 = true;
bool activeCs2 = false;

void copyStage(char *destination, size_t size, const char *source) {
  if (size == 0) return;
  std::strncpy(destination, source, size - 1);
  destination[size - 1] = '\0';
}

void setPinIfConnected(int pin, uint8_t level) {
  if (pin >= 0) digitalWrite(pin, level);
}

uint8_t busyLevel() { return digitalRead(EPD_PIN_BUSY) ? 1U : 0U; }

void selectControllers(bool cs1, bool cs2) {
  activeCs1 = cs1;
  activeCs2 = cs2 && EPD_PIN_CS2 >= 0;
  if (!activeCs1) digitalWrite(EPD_PIN_CS, HIGH);
  if (!activeCs2) setPinIfConnected(EPD_PIN_CS2, HIGH);
}

void writeSelectedCs(uint8_t level) {
  if (activeCs1) digitalWrite(EPD_PIN_CS, level);
  if (activeCs2) setPinIfConnected(EPD_PIN_CS2, level);
}

void startSpi() {
  if (spiStarted) return;
  SPI.begin(EPD_PIN_SCK, -1, EPD_PIN_MOSI, EPD_PIN_CS);
  SPI.setFrequency(kSpiHz);
  SPI.setDataMode(SPI_MODE0);
  SPI.setBitOrder(MSBFIRST);
  spiStarted = true;
}

void stopSpi() {
  if (!spiStarted) return;
  SPI.end();
  spiStarted = false;
  pinMode(EPD_PIN_SCK, OUTPUT);
  pinMode(EPD_PIN_MOSI, OUTPUT);
}

void holdPanelPinsLow() {
  digitalWrite(EPD_PIN_SCK, LOW);
  digitalWrite(EPD_PIN_DC, LOW);
  digitalWrite(EPD_PIN_MOSI, LOW);
  digitalWrite(EPD_PIN_RST, LOW);
  digitalWrite(EPD_PIN_CS, LOW);
  setPinIfConnected(EPD_PIN_CS2, LOW);
  setPinIfConnected(EPD_PIN_SWC, LOW);
}

void releasePanelPinsIdle() {
  stopSpi();
  selectControllers(true, false);
  digitalWrite(EPD_PIN_CS, HIGH);
  setPinIfConnected(EPD_PIN_CS2, HIGH);
  digitalWrite(EPD_PIN_SCK, LOW);
  digitalWrite(EPD_PIN_DC, LOW);
  digitalWrite(EPD_PIN_MOSI, LOW);
  digitalWrite(EPD_PIN_RST, HIGH);
  setPinIfConnected(EPD_PIN_SWC, HIGH);
}

void resetControllers() {
  digitalWrite(EPD_PIN_RST, LOW);
  delay(40);
  digitalWrite(EPD_PIN_RST, HIGH);
  delay(40);
  digitalWrite(EPD_PIN_RST, LOW);
  delay(40);
  digitalWrite(EPD_PIN_RST, HIGH);
}

bool waitIdle(uint32_t timeoutMs, uint32_t *elapsedOut = nullptr) {
  const uint32_t started = millis();
  while (busyLevel() != 1U) {
    if (millis() - started > timeoutMs) {
      if (elapsedOut) *elapsedOut = millis() - started;
      return false;
    }
    delay(1);
  }
  if (elapsedOut) *elapsedOut = millis() - started;
  return true;
}

bool waitStableHigh(uint32_t stableMs, uint32_t timeoutMs) {
  const uint32_t started = millis();
  uint32_t highSince = 0;
  while (millis() - started <= timeoutMs) {
    if (busyLevel() == 1U) {
      if (highSince == 0) highSince = millis();
      if (millis() - highSince >= stableMs) return true;
    } else {
      highSince = 0;
    }
    delay(1);
  }
  return false;
}

void write8(uint8_t dcx, uint8_t value) {
  if (probeReport.running) {
    const uint8_t controllerMask =
        static_cast<uint8_t>((activeCs1 ? 1U : 0U) |
                             (activeCs2 ? 2U : 0U));
    probeReport.wireFnv1a ^= controllerMask;
    probeReport.wireFnv1a *= 16777619UL;
    probeReport.wireFnv1a ^= dcx;
    probeReport.wireFnv1a *= 16777619UL;
    probeReport.wireFnv1a ^= value;
    probeReport.wireFnv1a *= 16777619UL;
    ++probeReport.wireEventCount;
  }
  digitalWrite(EPD_PIN_DC, dcx ? HIGH : LOW);
  writeSelectedCs(LOW);
  SPI.transfer(value);
  writeSelectedCs(HIGH);
}

void command(uint8_t value) {
  if (probeReport.running &&
      probeReport.commandCount < sizeof(probeReport.commandTrace)) {
    probeReport.commandTrace[probeReport.commandCount++] = value;
  }
  write8(0, value);
}
void data(uint8_t value) { write8(1, value); }

void bitBangWrite8(uint8_t dcx, uint8_t value) {
  digitalWrite(EPD_PIN_DC, dcx ? HIGH : LOW);
  pinMode(EPD_PIN_MOSI, OUTPUT);
  digitalWrite(EPD_PIN_SCK, LOW);
  writeSelectedCs(LOW);
  delayMicroseconds(2);
  for (uint8_t mask = 0x80; mask; mask >>= 1) {
    digitalWrite(EPD_PIN_MOSI, (value & mask) ? HIGH : LOW);
    delayMicroseconds(2);
    digitalWrite(EPD_PIN_SCK, HIGH);
    delayMicroseconds(2);
    digitalWrite(EPD_PIN_SCK, LOW);
  }
  writeSelectedCs(HIGH);
}

uint8_t bitBangRead8() {
  uint8_t value = 0;
  digitalWrite(EPD_PIN_DC, HIGH);
  digitalWrite(EPD_PIN_SCK, LOW);
  pinMode(EPD_PIN_MOSI, INPUT);
  delayMicroseconds(2);
  writeSelectedCs(LOW);
  delayMicroseconds(4);
  for (uint8_t bit = 0; bit < 8; ++bit) {
    value <<= 1;
    digitalWrite(EPD_PIN_SCK, HIGH);
    delayMicroseconds(2);
    if (digitalRead(EPD_PIN_MOSI)) value |= 1U;
    digitalWrite(EPD_PIN_SCK, LOW);
    delayMicroseconds(2);
  }
  writeSelectedCs(HIGH);
  pinMode(EPD_PIN_MOSI, OUTPUT);
  digitalWrite(EPD_PIN_MOSI, LOW);
  digitalWrite(EPD_PIN_DC, LOW);
  return value;
}

bool prepareRevisionSession() {
  stopSpi();
  digitalWrite(EPD_PIN_CS, HIGH);
  setPinIfConnected(EPD_PIN_CS2, HIGH);
  digitalWrite(EPD_PIN_SCK, LOW);
  digitalWrite(EPD_PIN_DC, LOW);
  pinMode(EPD_PIN_MOSI, OUTPUT);
  digitalWrite(EPD_PIN_MOSI, LOW);
  digitalWrite(EPD_PIN_RST, HIGH);
  setPinIfConnected(EPD_PIN_SWC, HIGH);
  return true;
}

Ec5PowerQualifierV2RevisionSample readRevisionAfterOwnReset(
    bool secondController) {
  Ec5PowerQualifierV2RevisionSample sample;
  // Restore only the per-sample-reset dimension from the historical path.
  // V1 segmented-CS framing, timing, and MOSI-low posture are intentionally
  // unchanged, so a remaining trivial CS2 read cannot prove a failed slave.
  selectControllers(false, false);
  digitalWrite(EPD_PIN_SCK, LOW);
  digitalWrite(EPD_PIN_DC, LOW);
  pinMode(EPD_PIN_MOSI, OUTPUT);
  digitalWrite(EPD_PIN_MOSI, LOW);
  resetControllers();
  ++readinessReport.resetCount;
  sample.idle = waitIdle(kResetIdleTimeoutMs);
  if (!sample.idle) return sample;
  selectControllers(!secondController, secondController);
  bitBangWrite8(0, kCmdRevision);
  if (readinessReport.revisionReadCount <
      sizeof(readinessReport.revisionCommandTrace)) {
    readinessReport
        .revisionCommandTrace[readinessReport.revisionReadCount] =
        kCmdRevision;
  }
  ++readinessReport.revisionReadCount;
  for (uint8_t &value : sample.bytes) value = bitBangRead8();
  return sample;
}

bool equalRevision(const Ec5PowerQualifierV2RevisionSample &a,
                   const Ec5PowerQualifierV2RevisionSample &b) {
  return a.idle && b.idle &&
         std::memcmp(a.bytes, b.bytes, sizeof(a.bytes)) == 0;
}

bool nontrivialRevision(const Ec5PowerQualifierV2RevisionSample &sample) {
  const bool allZero = sample.bytes[0] == 0 && sample.bytes[1] == 0 &&
                       sample.bytes[2] == 0;
  const bool allOnes = sample.bytes[0] == 0xFF && sample.bytes[1] == 0xFF &&
                       sample.bytes[2] == 0xFF;
  return !allZero && !allOnes;
}

bool exactRevision010104(const Ec5PowerQualifierV2RevisionSample &sample) {
  return sample.idle && sample.bytes[0] == 0x01 && sample.bytes[1] == 0x01 &&
         sample.bytes[2] == 0x04;
}

bool initializePowerRegisters() {
  stopSpi();
  digitalWrite(EPD_PIN_RST, LOW);
  digitalWrite(EPD_PIN_SCK, LOW);
  digitalWrite(EPD_PIN_DC, LOW);
  pinMode(EPD_PIN_MOSI, OUTPUT);
  digitalWrite(EPD_PIN_MOSI, LOW);
  digitalWrite(EPD_PIN_CS, HIGH);
  setPinIfConnected(EPD_PIN_CS2, HIGH);
  setPinIfConnected(EPD_PIN_SWC, HIGH);
  setPinIfConnected(EPD_PIN_BS, HIGH);
  startSpi();
  selectControllers(true, true);
  resetControllers();
  if (!waitIdle(kResetIdleTimeoutMs)) return false;
  delay(40);

  command(kCmdVendorUnlock);
  for (uint8_t value : {0x49, 0x55, 0x20, 0x08, 0x09, 0x18}) data(value);
  command(kCmdPowerSetting);
  data(0x3F);
  command(kCmdPanelSetting);
  data(0x5F);
  data(0x69);
  command(kCmdBoosterSoftStart1);
  for (uint8_t value : {0x40, 0x1F, 0x1F, 0x2C}) data(value);
  command(kCmdBoosterSoftStart3);
  for (uint8_t value : {0x6F, 0x1F, 0x1F, 0x22}) data(value);
  command(kCmdBoosterSoftStart2);
  for (uint8_t value : {0x6F, 0x1F, 0x17, 0x17}) data(value);
  command(kCmdPowerOffSequence);
  for (uint8_t value : {0x00, 0x54, 0x00, 0x44}) data(value);
  command(kCmdTcon);
  data(0x02);
  data(0x00);
  command(kCmdPll);
  data(0x08);
  command(kCmdVcomInterval);
  data(0x3F);
  command(kCmdResolution);
  data(static_cast<uint8_t>(EPD_CONTROLLER_WIDTH >> 8));
  data(static_cast<uint8_t>(EPD_CONTROLLER_WIDTH & 0xFF));
  data(static_cast<uint8_t>(EPD_HEIGHT >> 8));
  data(static_cast<uint8_t>(EPD_HEIGHT & 0xFF));
  command(kCmdPowerSaving);
  data(0x2F);
  command(kCmdTvdcs);
  data(0x01);

  selectControllers(true, false);
  command(kCmdCascade);
  data(0x01);
  selectControllers(false, true);
  command(kCmdCascade);
  data(0x01);
  selectControllers(true, true);
  return true;
}

bool requireIdleBeforePowerCommand(const char *stage, uint8_t *entryOut) {
  const uint8_t entry = busyLevel();
  if (entryOut) *entryOut = entry;
  // The frozen contract is an entry gate, not a wait-until-convenient gate.
  // A LOW entry is already abnormal: PON must not be issued, while a POF-stage
  // failure is handled only by failProbe's single fail-safe POF cleanup.
  if (entry != 1U) {
    probeReport.preCommandIdleFailure = true;
    copyStage(probeReport.preCommandBusyStage,
              sizeof(probeReport.preCommandBusyStage), stage);
    return false;
  }
  if (waitIdle(kPreCommandIdleTimeoutMs)) return true;
  probeReport.preCommandIdleFailure = true;
  copyStage(probeReport.preCommandBusyStage,
            sizeof(probeReport.preCommandBusyStage), stage);
  return false;
}

bool waitBusyThenIdle(const char *stage, uint32_t *elapsedOut,
                      uint32_t *assertionLatencyOut, bool *busySeenOut) {
  const uint32_t started = millis();
  bool busySeen = busyLevel() == 0U;
  uint32_t assertionLatency = 0;
  while (!busySeen && millis() - started < kBusyAssertionGraceMs) {
    if (busyLevel() == 0U) {
      busySeen = true;
      assertionLatency = millis() - started;
      break;
    }
    delay(1);
  }
  if (!busySeen) {
    probeReport.busyAssertionMissing = true;
    copyStage(probeReport.busyMissingStage,
              sizeof(probeReport.busyMissingStage), stage);
    if (elapsedOut) *elapsedOut = millis() - started;
    if (assertionLatencyOut) *assertionLatencyOut = 0;
    if (busySeenOut) *busySeenOut = false;
    return false;
  }
  while (busyLevel() != 1U) {
    if (millis() - started > kPowerStageTimeoutMs) {
      probeReport.waitTimedOut = true;
      copyStage(probeReport.timeoutStage, sizeof(probeReport.timeoutStage),
                stage);
      if (elapsedOut) *elapsedOut = millis() - started;
      if (assertionLatencyOut) *assertionLatencyOut = assertionLatency;
      if (busySeenOut) *busySeenOut = true;
      return false;
    }
    delay(10);
  }
  if (elapsedOut) *elapsedOut = millis() - started;
  if (assertionLatencyOut) *assertionLatencyOut = assertionLatency;
  if (busySeenOut) *busySeenOut = true;
  return true;
}

void sampleAndHoldSafe() {
  probeReport.safeFinishBusyBeforePinsLow = busyLevel();
  stopSpi();
  holdPanelPinsLow();
  probeReport.safeFinishBusyAfterPinsLow = busyLevel();
  delay(5);
  probeReport.safeFinishBusyAfter5Ms = busyLevel();
}

void finishProbe(uint32_t started, bool ok) {
  probeReport.sequenceOk = ok;
  probeReport.totalMs = millis() - started;
  probeReport.finalBusy = busyLevel();
  probeReport.finalRst = digitalRead(EPD_PIN_RST) ? 1U : 0U;
  probeReport.finalCs1 = digitalRead(EPD_PIN_CS) ? 1U : 0U;
  probeReport.finalCs2 =
      EPD_PIN_CS2 >= 0 && digitalRead(EPD_PIN_CS2) ? 1U : 0U;
  probeReport.finalSck = digitalRead(EPD_PIN_SCK) ? 1U : 0U;
  probeReport.finalDc = digitalRead(EPD_PIN_DC) ? 1U : 0U;
  probeReport.finalMosi = digitalRead(EPD_PIN_MOSI) ? 1U : 0U;
  probeReport.running = false;
}

void failProbe(uint32_t started, const char *stage) {
  copyStage(probeReport.failureStage, sizeof(probeReport.failureStage), stage);
  if (probeReport.ponCommandSent && !probeReport.pofCommandSent) {
    // After PON, issue at most one POF. It is fail-safe cleanup and never a
    // retry of the probe or of a visible operation.
    selectControllers(true, true);
    startSpi();
    command(kCmdPowerOff);
    data(0x00);
    probeReport.pofCommandSent = true;
    delay(kBusyAssertionGraceMs);
    waitIdle(30000UL);
  }
  sampleAndHoldSafe();
  finishProbe(started, false);
}

String boolJson(bool value) { return value ? "true" : "false"; }

String revisionJson(const Ec5PowerQualifierV2RevisionSample &sample) {
  return String("{\"idle\":") + boolJson(sample.idle) +
         ",\"bytes\":[" + String(sample.bytes[0]) + "," +
         String(sample.bytes[1]) + "," + String(sample.bytes[2]) + "]}";
}

void finishReadinessFailure(uint32_t started, const char *stage) {
  copyStage(readinessReport.failureStage,
            sizeof(readinessReport.failureStage), stage);
  stopSpi();
  holdPanelPinsLow();
  readinessReport.finalBusy = busyLevel();
  readinessReport.finalRst = digitalRead(EPD_PIN_RST) ? 1U : 0U;
  readinessReport.finalCs1 = digitalRead(EPD_PIN_CS) ? 1U : 0U;
  readinessReport.finalCs2 =
      EPD_PIN_CS2 >= 0 && digitalRead(EPD_PIN_CS2) ? 1U : 0U;
  readinessReport.finalSck = digitalRead(EPD_PIN_SCK) ? 1U : 0U;
  readinessReport.finalDc = digitalRead(EPD_PIN_DC) ? 1U : 0U;
  readinessReport.finalMosi = digitalRead(EPD_PIN_MOSI) ? 1U : 0U;
  readinessReport.totalMs = millis() - started;
}

}  // namespace

void ec5PowerQualifierV2Begin() {
  pinMode(EPD_PIN_CS, OUTPUT);
  if (EPD_PIN_CS2 >= 0) pinMode(EPD_PIN_CS2, OUTPUT);
  pinMode(EPD_PIN_SCK, OUTPUT);
  pinMode(EPD_PIN_MOSI, OUTPUT);
  pinMode(EPD_PIN_RST, OUTPUT);
  pinMode(EPD_PIN_BUSY, INPUT);
  pinMode(EPD_PIN_DC, OUTPUT);
  if (EPD_PIN_BS >= 0) pinMode(EPD_PIN_BS, OUTPUT);
  if (EPD_PIN_SWC >= 0) pinMode(EPD_PIN_SWC, OUTPUT);
  setPinIfConnected(EPD_PIN_BS, HIGH);
  sameBootReadinessQualified = false;
  holdPanelPinsLow();
  delay(10);
}

void ec5PowerQualifierV2ForceSafeHold() {
  sameBootReadinessQualified = false;
  stopSpi();
  holdPanelPinsLow();
}

int ec5PowerQualifierV2ReadBusy() { return digitalRead(EPD_PIN_BUSY); }

bool ec5PowerQualifierV2RunReadinessOnce() {
  const uint32_t started = millis();
  readinessReport = Ec5PowerQualifierV2ReadinessReport{};
  readinessReport.valid = true;
  readinessReport.entryBusy = busyLevel();
  sameBootReadinessQualified = false;

  if (EPD_PIN_CS2 < 0) {
    finishReadinessFailure(started, "cs2_disabled");
    return false;
  }
  if (!prepareRevisionSession()) {
    finishReadinessFailure(started, "revision_session_prepare_failed");
    return false;
  }
  readinessReport.cs1[0] = readRevisionAfterOwnReset(false);
  if (!readinessReport.cs1[0].idle) {
    finishReadinessFailure(started, "cs1_sample1_reset_busy");
    return false;
  }
  readinessReport.cs1[1] = readRevisionAfterOwnReset(false);
  if (!readinessReport.cs1[1].idle) {
    finishReadinessFailure(started, "cs1_sample2_reset_busy");
    return false;
  }
  readinessReport.cs2[0] = readRevisionAfterOwnReset(true);
  if (!readinessReport.cs2[0].idle) {
    finishReadinessFailure(started, "cs2_sample1_reset_busy");
    return false;
  }
  readinessReport.cs2[1] = readRevisionAfterOwnReset(true);
  if (!readinessReport.cs2[1].idle) {
    finishReadinessFailure(started, "cs2_sample2_reset_busy");
    return false;
  }
  readinessReport.cs1Stable =
      equalRevision(readinessReport.cs1[0], readinessReport.cs1[1]);
  readinessReport.cs2Stable =
      equalRevision(readinessReport.cs2[0], readinessReport.cs2[1]);
  readinessReport.cs1Nontrivial =
      nontrivialRevision(readinessReport.cs1[1]);
  readinessReport.cs2Nontrivial =
      nontrivialRevision(readinessReport.cs2[1]);
  readinessReport.cs1Exact010104 =
      exactRevision010104(readinessReport.cs1[0]) &&
      exactRevision010104(readinessReport.cs1[1]);
  readinessReport.cs2Exact010104 =
      exactRevision010104(readinessReport.cs2[0]) &&
      exactRevision010104(readinessReport.cs2[1]);
  readinessReport.allRevisionSamplesExact010104 =
      readinessReport.cs1Exact010104 && readinessReport.cs2Exact010104;

  // A fifth and final shared reset removes controller-order history from the
  // qualified posture.  No power command is reachable unless BUSY is then
  // continuously HIGH for the full readiness stability window.
  selectControllers(false, false);
  digitalWrite(EPD_PIN_SCK, LOW);
  digitalWrite(EPD_PIN_DC, LOW);
  pinMode(EPD_PIN_MOSI, OUTPUT);
  digitalWrite(EPD_PIN_MOSI, LOW);
  resetControllers();
  ++readinessReport.resetCount;
  const bool finalResetIdle = waitIdle(kResetIdleTimeoutMs);
  releasePanelPinsIdle();
  const bool stableHigh = finalResetIdle &&
                          waitStableHigh(kReadinessHighStableMs,
                                         kResetIdleTimeoutMs);
  readinessReport.finalBusy = busyLevel();
  readinessReport.finalRst = digitalRead(EPD_PIN_RST) ? 1U : 0U;
  readinessReport.finalCs1 = digitalRead(EPD_PIN_CS) ? 1U : 0U;
  readinessReport.finalCs2 =
      EPD_PIN_CS2 >= 0 && digitalRead(EPD_PIN_CS2) ? 1U : 0U;
  readinessReport.finalSck = digitalRead(EPD_PIN_SCK) ? 1U : 0U;
  readinessReport.finalDc = digitalRead(EPD_PIN_DC) ? 1U : 0U;
  readinessReport.finalMosi = digitalRead(EPD_PIN_MOSI) ? 1U : 0U;
  readinessReport.finalHighStableMs =
      stableHigh ? kReadinessHighStableMs : 0;
  readinessReport.qualified = readinessReport.cs1Stable &&
                              readinessReport.cs2Stable &&
                              readinessReport.cs1Nontrivial &&
                              readinessReport.cs2Nontrivial &&
                              readinessReport.allRevisionSamplesExact010104 &&
                              readinessReport.resetCount == 5U && stableHigh &&
                              readinessReport.finalBusy == 1U &&
                              readinessReport.finalRst == 1U &&
                              readinessReport.finalCs1 == 1U &&
                              readinessReport.finalCs2 == 1U &&
                              readinessReport.finalSck == 0U &&
                              readinessReport.finalDc == 0U &&
                              readinessReport.finalMosi == 0U;
  if (!readinessReport.qualified) {
    const char *failure =
        !readinessReport.cs1Stable
            ? "cs1_revision_unstable"
            : (!readinessReport.cs2Stable
                   ? "cs2_revision_unstable"
                   : (!readinessReport.cs1Nontrivial
                          ? "cs1_revision_trivial"
                          : (!readinessReport.cs2Nontrivial
                                 ? "cs2_revision_trivial"
                                 : (!readinessReport.cs1Exact010104
                                        ? "cs1_revision_not_010104"
                                        : (!readinessReport.cs2Exact010104
                                               ? "cs2_revision_not_010104"
                                               : (!finalResetIdle
                                                      ? "final_reset_busy_not_idle_high"
                                                      : "busy_or_gpio_posture_not_qualified"))))));
    finishReadinessFailure(started, failure);
    sameBootReadinessQualified = false;
    return false;
  }
  readinessReport.totalMs = millis() - started;
  sameBootReadinessQualified = readinessReport.qualified;
  return readinessReport.qualified;
}

bool ec5PowerQualifierV2RunPonPofOnce() {
  const uint32_t started = millis();
  probeReport = Ec5PowerQualifierV2ProbeReport{};
  probeReport.valid = true;
  probeReport.running = true;
  probeReport.spiHz = kSpiHz;
  ++operationCounter;
  if (operationCounter == 0) ++operationCounter;
  probeReport.operationId = operationCounter;

  if (!sameBootReadinessQualified || !readinessReport.qualified) {
    failProbe(started, "same_boot_readiness_missing");
    return false;
  }
  sameBootReadinessQualified = false;
  if (!initializePowerRegisters()) {
    failProbe(started, "power_register_initialization");
    return false;
  }
  selectControllers(true, true);
  if (!requireIdleBeforePowerCommand("PON", &probeReport.ponGateEntry)) {
    failProbe(started, "pre_pon_idle");
    return false;
  }
  command(kCmdPowerOn);
  probeReport.ponCommandSent = true;
  if (!waitBusyThenIdle("PON", &probeReport.ponWaitMs,
                        &probeReport.ponAssertionLatencyMs,
                        &probeReport.ponBusySeen)) {
    failProbe(started, "pon_busy_idle");
    return false;
  }
  probeReport.ponIdleCompleted = true;
  if (!requireIdleBeforePowerCommand("POF", &probeReport.pofGateEntry)) {
    failProbe(started, "pre_pof_idle");
    return false;
  }
  // Do not rely on the selection state left behind by PON.  POF is an
  // independently qualified dual-controller power command.
  selectControllers(true, true);
  command(kCmdPowerOff);
  data(0x00);
  probeReport.pofCommandSent = true;
  if (!waitBusyThenIdle("POF", &probeReport.pofWaitMs,
                        &probeReport.pofAssertionLatencyMs,
                        &probeReport.pofBusySeen)) {
    failProbe(started, "pof_busy_idle");
    return false;
  }
  probeReport.pofIdleCompleted = true;
  delay(6000);
  selectControllers(true, true);
  startSpi();
  command(kCmdPanelSetting);
  data(0x4F);
  data(0x6E);
  probeReport.postPsrCommandSent = true;
  if (!waitIdle(kPowerStageTimeoutMs, &probeReport.postPsrWaitMs)) {
    failProbe(started, "post_pof_psr_idle");
    return false;
  }
  delay(1000);
  sampleAndHoldSafe();
  finishProbe(started, true);
  return true;
}

const Ec5PowerQualifierV2ReadinessReport &ec5PowerQualifierV2ReadinessReport() {
  return readinessReport;
}

const Ec5PowerQualifierV2ProbeReport &ec5PowerQualifierV2ProbeReport() {
  return probeReport;
}

String ec5PowerQualifierV2ReadinessJson() {
  return String("{\"valid\":") + boolJson(readinessReport.valid) +
         ",\"qualified\":" + boolJson(readinessReport.qualified) +
         ",\"entry_busy\":" + String(readinessReport.entryBusy) +
         ",\"final_busy\":" + String(readinessReport.finalBusy) +
         ",\"final_gpio\":{\"rst\":" +
         String(readinessReport.finalRst) + ",\"cs1\":" +
         String(readinessReport.finalCs1) + ",\"cs2\":" +
         String(readinessReport.finalCs2) + ",\"sck\":" +
         String(readinessReport.finalSck) + ",\"dc\":" +
         String(readinessReport.finalDc) + ",\"mosi\":" +
         String(readinessReport.finalMosi) + "}" +
         ",\"final_high_stable_ms\":" +
         String(readinessReport.finalHighStableMs) +
         ",\"reset_count\":" + String(readinessReport.resetCount) +
         ",\"revision_read_count\":" +
         String(readinessReport.revisionReadCount) +
         ",\"revision_command_trace\":[" +
         String(readinessReport.revisionCommandTrace[0]) + "," +
         String(readinessReport.revisionCommandTrace[1]) + "," +
         String(readinessReport.revisionCommandTrace[2]) + "," +
         String(readinessReport.revisionCommandTrace[3]) + "]" +
         ",\"total_ms\":" + String(readinessReport.totalMs) +
         ",\"cs1\":{\"sample1\":" +
         revisionJson(readinessReport.cs1[0]) + ",\"sample2\":" +
         revisionJson(readinessReport.cs1[1]) + ",\"stable\":" +
         boolJson(readinessReport.cs1Stable) + ",\"nontrivial\":" +
         boolJson(readinessReport.cs1Nontrivial) +
         ",\"exact_010104\":" +
         boolJson(readinessReport.cs1Exact010104) + "},\"cs2\":{" +
         "\"sample1\":" + revisionJson(readinessReport.cs2[0]) +
         ",\"sample2\":" + revisionJson(readinessReport.cs2[1]) +
         ",\"stable\":" + boolJson(readinessReport.cs2Stable) +
         ",\"nontrivial\":" + boolJson(readinessReport.cs2Nontrivial) +
         ",\"exact_010104\":" +
         boolJson(readinessReport.cs2Exact010104) +
         "},\"all_revision_samples_exact_010104\":" +
         boolJson(readinessReport.allRevisionSamplesExact010104) +
         ",\"failure_stage\":\"" + readinessReport.failureStage + "\"}";
}

String ec5PowerQualifierV2ProbeJson() {
  String output = "";
  for (uint8_t index = 0; index < probeReport.commandCount; ++index) {
    if (index != 0) output += ',';
    output += String(probeReport.commandTrace[index]);
  }
  return String("{\"valid\":") + boolJson(probeReport.valid) +
         ",\"running\":" + boolJson(probeReport.running) +
         ",\"sequence_ok\":" + boolJson(probeReport.sequenceOk) +
         ",\"operation_id\":" + String(probeReport.operationId) +
         ",\"spi_hz\":" + String(probeReport.spiHz) +
         ",\"total_ms\":" + String(probeReport.totalMs) +
         ",\"wait_timeout\":" + boolJson(probeReport.waitTimedOut) +
         ",\"busy_assertion_missing\":" +
         boolJson(probeReport.busyAssertionMissing) +
         ",\"pre_command_idle_failure\":" +
         boolJson(probeReport.preCommandIdleFailure) +
         ",\"pon_busy_seen\":" + boolJson(probeReport.ponBusySeen) +
         ",\"pof_busy_seen\":" + boolJson(probeReport.pofBusySeen) +
         ",\"pon_command_sent\":" +
         boolJson(probeReport.ponCommandSent) +
         ",\"pof_command_sent\":" +
         boolJson(probeReport.pofCommandSent) +
         ",\"post_psr_command_sent\":" +
         boolJson(probeReport.postPsrCommandSent) +
         ",\"pon_idle_completed\":" +
         boolJson(probeReport.ponIdleCompleted) +
         ",\"pof_idle_completed\":" +
         boolJson(probeReport.pofIdleCompleted) +
         ",\"post_psr_payload_hex\":\"4f6e\"" +
         ",\"command_counts\":{\"pon\":" +
         String(probeReport.ponCommandSent ? 1 : 0) +
         ",\"pof\":" + String(probeReport.pofCommandSent ? 1 : 0) +
         ",\"drf\":0,\"dtm\":0,\"lut\":0,\"ptlw\":0," +
         "\"command_0x86\":0,\"visible_refresh_requests\":0}" +
         ",\"pon_ms\":" + String(probeReport.ponWaitMs) +
         ",\"pof_ms\":" + String(probeReport.pofWaitMs) +
         ",\"post_psr_ms\":" + String(probeReport.postPsrWaitMs) +
         ",\"pon_assertion_latency_ms\":" +
         String(probeReport.ponAssertionLatencyMs) +
         ",\"pof_assertion_latency_ms\":" +
         String(probeReport.pofAssertionLatencyMs) +
         ",\"pon_gate_entry\":" + String(probeReport.ponGateEntry) +
         ",\"pof_gate_entry\":" + String(probeReport.pofGateEntry) +
         ",\"timeout_stage\":\"" + probeReport.timeoutStage +
         "\",\"busy_missing_stage\":\"" +
         probeReport.busyMissingStage +
         "\",\"pre_command_busy_stage\":\"" +
         probeReport.preCommandBusyStage + "\",\"failure_stage\":\"" +
         probeReport.failureStage +
         "\",\"forbidden_commands\":{\"drf\":" +
         boolJson(probeReport.drfCommandSent) + ",\"dtm\":" +
         boolJson(probeReport.dtmCommandSent) + ",\"lut\":" +
         boolJson(probeReport.lutCommandSent) + ",\"ptlw\":" +
         boolJson(probeReport.ptlwCommandSent) + ",\"command_0x86\":" +
         boolJson(probeReport.command86Sent) +
         "},\"command_trace\":[" + output +
         "],\"wire_event_count\":" +
         String(probeReport.wireEventCount) + ",\"wire_fnv1a\":" +
         String(probeReport.wireFnv1a) +
         ",\"safe_finish\":{\"busy_before_pins_low\":" +
         String(probeReport.safeFinishBusyBeforePinsLow) +
         ",\"busy_after_pins_low\":" +
         String(probeReport.safeFinishBusyAfterPinsLow) +
         ",\"busy_after_5ms\":" +
         String(probeReport.safeFinishBusyAfter5Ms) +
         ",\"final_gpio\":{\"busy\":" + String(probeReport.finalBusy) +
         ",\"rst\":" + String(probeReport.finalRst) +
         ",\"cs1\":" + String(probeReport.finalCs1) +
         ",\"cs2\":" + String(probeReport.finalCs2) +
         ",\"sck\":" + String(probeReport.finalSck) +
         ",\"dc\":" + String(probeReport.finalDc) +
         ",\"mosi\":" + String(probeReport.finalMosi) + "}}}";
}
