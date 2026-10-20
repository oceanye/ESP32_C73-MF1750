// Dedicated translation unit for partial-block route A V4: the compact
// atlas layout collects all eight transport-code cells into the current
// camera's visible window (safe rectangle x in [16,520], y in [170,580], all
// on CS1's left half).  The two probe actions are dropped; NORMALIZE and
// WHITE_RECOVERY are byte-identical to the sealed V3 paths.  Per-action the
// driver switches between the factory-OTP path, the pinned legacy-active
// runtime tuple (maximal charge reset), and the wf_wmask_1E GrayExt tuple
// (base 0x0E plus the whole records 0-3 group; the family label is not a
// bitmask).  Every tuple's R20/PWR/PLL/R21/PSR bytes are the same compiled
// objects as their sealed sources; the runtime tail below is byte-identical
// to the pinned R2G template.  Production, the wf_wmask_*, and the V1/V2/V3
// translation units stay untouched.
#include "epd_driver.h"

#include <SPI.h>
#if defined(MF1750_PARTIAL_BLOCK_ATLAS_1E_V4_BUILD)
#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>
#endif
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "epd_config.h"
#include "partial_atlas_1e_v4_api.h"

#if !defined(MF1750_L535_FRAME_PATH_BUILD) || MF1750_L535_FRAME_PATH_BUILD != 1
#error "route A V4 requires the frozen L535 frame path build"
#endif
#if !defined(MF1750_PARTIAL_BLOCK_ATLAS_1E_V4_BUILD) || \
    MF1750_PARTIAL_BLOCK_ATLAS_1E_V4_BUILD != 1
#error "route A V4 requires MF1750_PARTIAL_BLOCK_ATLAS_1E_V4_BUILD=1"
#endif
#if !defined(MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY) || \
    MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY != 1
#error "route A V4 requires the factory-OTP fixture for its white steps"
#endif
#if !defined(MF1750_OTP_WHITE_FOR_PROFILE_WF23_25) || \
    MF1750_OTP_WHITE_FOR_PROFILE_WF23_25 != 1 || \
    MF1750_OTP_WHITE_FOR_PROFILE_WF20_25 != 0
#error "route A V4 binds the WF23_25 factory-OTP white profile exactly"
#endif

#include "generated/spd1657_legacy_535_reference.inc"
namespace l535_lut = mf1750::runtime_lut::legacy_reference;
#include "generated/spd1657_wf_wmask_1E.inc"
namespace pb_profile_1e = mf1750::runtime_lut::wf_wmask_1E;
// The inherited full-frame path (unused by every V4 action) binds the 1E
// tuple so the byte-identical runtime tail compiles unchanged.
namespace l535_variant = mf1750::runtime_lut::wf_wmask_1E;
#include "generated/partial_atlas_1e_v4_contract.inc"
namespace pbv4 = mf1750::partial_block::atlas_v4;

constexpr bool pbv4Profile1EUseCommented(std::size_t index) {
  return (index >= 183 && index < 194) ||
          (index >= 194 && index < 205) ||
          (index >= 205 && index < 216) ||
          (index >= 216 && index < 227) ||
          (index >= 238 && index < 249) ||
          (index >= 249 && index < 260) ||
          (index >= 260 && index < 271);
}

// C++11 compile-time proof for every one of the 535 transmitted R20 bytes.
template <std::size_t INDEX>
struct Pbv4Profile1ERecordsMatch {
  static constexpr bool value =
      (pb_profile_1e::kR20Payload[INDEX] ==
       (pbv4Profile1EUseCommented(INDEX)
            ? l535_lut::commented::kR20Payload[INDEX]
            : l535_lut::active::kR20Payload[INDEX])) &&
      Pbv4Profile1ERecordsMatch<INDEX + 1>::value;
};
template <>
struct Pbv4Profile1ERecordsMatch<535> {
  static constexpr bool value = true;
};
static_assert(Pbv4Profile1ERecordsMatch<0>::value,
              "route A V4 1E R20 sources do not match the preregistered composition");

static_assert(pb_profile_1e::kPowerPayload[0] == l535_lut::active::kPowerPayload[0] &&
                  pb_profile_1e::kPowerPayload[1] == l535_lut::active::kPowerPayload[1] &&
                  pb_profile_1e::kPowerPayload[2] == l535_lut::active::kPowerPayload[2] &&
                  pb_profile_1e::kPowerPayload[3] == l535_lut::active::kPowerPayload[3] &&
                  pb_profile_1e::kPowerPayload[4] == l535_lut::active::kPowerPayload[4] &&
                  pb_profile_1e::kPowerPayload[5] == l535_lut::active::kPowerPayload[5],
              "route A V4 1E PWR payload differs from active");
static_assert(pb_profile_1e::kR20Payload[1] == pb_profile_1e::kPowerPayload[2] &&
                  pb_profile_1e::kR20Payload[2] == pb_profile_1e::kPowerPayload[3] &&
                  pb_profile_1e::kR20Payload[3] == pb_profile_1e::kPowerPayload[4] &&
                  pb_profile_1e::kR20Payload[4] == pb_profile_1e::kPowerPayload[5],
              "route A V4 1E R20[1:5] != PWR[2:6]: active header/PWR mirror broken");
static_assert(pb_profile_1e::kPllPayload[0] == 0x02 &&
                  pb_profile_1e::kPllPayload[0] == l535_lut::active::kPllPayload[0] &&
                  pb_profile_1e::kR20Payload[6] == pb_profile_1e::kPllPayload[0],
              "route A V4 1E R20[6] != PLL[0] == active 0x02");

// The driver uploads l535_lut::active::kR21Payload directly.  Prove its full
// 704-byte active identity rather than sampling only the endpoints.
template <std::size_t INDEX>
struct Pbv4ActiveR21Unchanged {
  static constexpr bool value =
      l535_lut::active::kR21Payload[INDEX] == 0xFF &&
      Pbv4ActiveR21Unchanged<INDEX + 1>::value;
};
template <>
struct Pbv4ActiveR21Unchanged<704> {
  static constexpr bool value = true;
};
static_assert(l535_lut::active::kR21PayloadBytes == 704 &&
                  l535_lut::active::kR21IsAllFf &&
                  Pbv4ActiveR21Unchanged<0>::value,
              "route A V4: active R21 is no longer the sealed 704 x 0xFF payload");

namespace {

enum : uint8_t {
  PSR = 0x00,
  PWR = 0x01,
  POF = 0x02,
  POFS = 0x03,
  PON = 0x04,
  BTST1 = 0x05,
  BTST2 = 0x06,
  DSLP = 0x07,
  BTST3 = 0x08,
  DTM = 0x10,
  DRF = 0x12,
  PLL = 0x30,
  CDI = 0x50,
  TCON = 0x60,
  TRES = 0x61,
  REV = 0x70,
  T_VDCS = 0x84,
  CCSET = 0xE0,
  PWS = 0xE3,
};

static bool activeCs1 = true;
static bool activeCs2 = false;
static uint32_t activeSpiHz = EPD_SPI_DEFAULT_HZ;
static bool hardwareSpiStarted = false;

static EpdOperationReport diagnosticReport;
static uint32_t operationIdCounter = 0;

static constexpr uint32_t FNV1A_OFFSET_BASIS = 2166136261UL;
static constexpr uint32_t FNV1A_PRIME = 16777619UL;
static constexpr uint32_t EPD_BUSY_ASSERT_GRACE_MS = 250;
static constexpr uint32_t EPD_PRE_COMMAND_IDLE_TIMEOUT_MS = 3000;

struct ControllerMapping {
  uint8_t sourceHalf;
  bool flipX;
  bool flipY;
  bool nibbleSwap;
};

static constexpr ControllerMapping CONTROLLER_MAPPINGS[] = {
    {EPD_CS1_SOURCE_HALF, EPD_CS1_FLIP_X, EPD_CS1_FLIP_Y, EPD_CS1_NIBBLE_SWAP},
    {EPD_CS2_SOURCE_HALF, EPD_CS2_FLIP_X, EPD_CS2_FLIP_Y, EPD_CS2_NIBBLE_SWAP},
};

static_assert(EPD_CS1_SOURCE_HALF <= 1 && EPD_CS2_SOURCE_HALF <= 1,
              "EPD controller source half must be 0 or 1");
static_assert(EPD_CS1_SOURCE_HALF != EPD_CS2_SOURCE_HALF,
              "CS1 and CS2 must consume different logical halves");

inline uint32_t fnv1aUpdate(uint32_t hash, uint8_t value) {
  hash ^= value;
  return hash * FNV1A_PRIME;
}

uint32_t fnv1a(const uint8_t *data, size_t len) {
  uint32_t hash = FNV1A_OFFSET_BASIS;
  for (size_t i = 0; i < len; ++i) hash = fnv1aUpdate(hash, data[i]);
  return hash;
}

void copyStage(char *destination, size_t destinationSize, const char *stage) {
  if (destinationSize == 0) return;
  std::strncpy(destination, stage, destinationSize - 1);
  destination[destinationSize - 1] = '\0';
}

uint8_t readBusyLevel() {
  return digitalRead(EPD_PIN_BUSY) ? 1U : 0U;
}

EpdBusyStageEvidence *busyStageEvidence(const char *stage) {
  if (!diagnosticReport.running) return nullptr;
  if (std::strcmp(stage, "reset") == 0) return &diagnosticReport.resetBusy;
  if (std::strcmp(stage, "PON") == 0) return &diagnosticReport.ponBusy;
  if (std::strcmp(stage, "DRF") == 0) return &diagnosticReport.drfBusy;
  if (std::strcmp(stage, "POF") == 0) return &diagnosticReport.pofBusy;
  if (std::strcmp(stage, "post-display PSR") == 0) {
    return &diagnosticReport.postPsrBusy;
  }
  return nullptr;
}

bool epdRequireIdleBeforeCommand(const char *stage) {
  EpdBusyStageEvidence *evidence = busyStageEvidence(stage);
  const uint32_t started = millis();
  const uint8_t entryLevel = readBusyLevel();
  if (evidence) evidence->gateEntryLevel = entryLevel;
  while (readBusyLevel() != EPD_BUSY_IDLE_LEVEL) {
    if (millis() - started > EPD_PRE_COMMAND_IDLE_TIMEOUT_MS) {
      const uint32_t elapsed = millis() - started;
      const uint8_t level = readBusyLevel();
      if (evidence) {
        evidence->preCommandLevel = level;
        evidence->preCommandWaitMs = elapsed;
        evidence->preCommandIdleOk = false;
      }
      if (diagnosticReport.running) {
        diagnosticReport.preCommandIdleFailure = true;
        copyStage(diagnosticReport.preCommandBusyStage,
                  sizeof(diagnosticReport.preCommandBusyStage), stage);
      }
      Serial.printf(
          "EPD pre-command idle timeout: %s after %lu ms, entry=%u, BUSY=%u\n",
          stage, static_cast<unsigned long>(elapsed), entryLevel, level);
      return false;
    }
    delay(1);
  }
  const uint32_t elapsed = millis() - started;
  const uint8_t level = readBusyLevel();
  if (evidence) {
    evidence->preCommandLevel = level;
    evidence->preCommandWaitMs = elapsed;
    evidence->preCommandIdleOk = true;
  }
  Serial.printf(
      "EPD pre-command idle: %s after %lu ms, entry=%u, before_command=%u\n",
      stage, static_cast<unsigned long>(elapsed), entryLevel, level);
  return true;
}

void epdRecordInformationalCommandEntry(const char *stage) {
  EpdBusyStageEvidence *evidence = busyStageEvidence(stage);
  if (!evidence) return;
  const uint8_t level = readBusyLevel();
  evidence->gateEntryLevel = level;
  evidence->preCommandLevel = level;
  evidence->preCommandIdleOk = level == EPD_BUSY_IDLE_LEVEL;
}

void epdRecordWaitTrace(const char *stage,
                        uint8_t exitLevel,
                        bool assertionAfterIdle,
                        uint32_t assertionLatencyMs,
                        uint32_t waitMs) {
  EpdBusyStageEvidence *evidence = busyStageEvidence(stage);
  if (!evidence) return;
  evidence->waitExitLevel = exitLevel;
  evidence->assertionAfterIdle = assertionAfterIdle;
  evidence->assertionLatencyMs = assertionLatencyMs;
  evidence->waitMs = waitMs;
}

String epdBusyStageEvidenceJson(const EpdBusyStageEvidence &evidence) {
  return String("{\"gate_entry_level\":") +
         String(static_cast<unsigned>(evidence.gateEntryLevel)) +
         ",\"pre_command_level\":" +
         String(static_cast<unsigned>(evidence.preCommandLevel)) +
         ",\"wait_entry_level\":" +
         String(static_cast<unsigned>(evidence.waitEntryLevel)) +
         ",\"wait_exit_level\":" +
         String(static_cast<unsigned>(evidence.waitExitLevel)) +
         ",\"pre_command_idle_ok\":" +
         String(evidence.preCommandIdleOk ? "true" : "false") +
         ",\"assertion_after_idle\":" +
         String(evidence.assertionAfterIdle ? "true" : "false") +
         ",\"pre_command_wait_ms\":" + String(evidence.preCommandWaitMs) +
         ",\"wait_ms\":" + String(evidence.waitMs) +
         ",\"assertion_latency_ms\":" +
         String(evidence.assertionLatencyMs) + "}";
}

void recordWaitEvidence(const char *stage, uint32_t elapsedMs, bool busySeen) {
  if (!diagnosticReport.running) return;
  if (std::strcmp(stage, "PON") == 0) {
    diagnosticReport.ponWaitMs = elapsedMs;
    diagnosticReport.ponBusySeen = busySeen;
  } else if (std::strcmp(stage, "DRF") == 0) {
    diagnosticReport.drfWaitMs = elapsedMs;
    diagnosticReport.drfBusySeen = busySeen;
  } else if (std::strcmp(stage, "POF") == 0) {
    diagnosticReport.pofWaitMs = elapsedMs;
    diagnosticReport.pofBusySeen = busySeen;
  } else if (std::strcmp(stage, "post-display PSR") == 0) {
    diagnosticReport.postPsrWaitMs = elapsedMs;
    diagnosticReport.postPsrBusySeen = busySeen;
  }
}

uint32_t epdBeginOperation(uint32_t spiHz) {
  ++operationIdCounter;
  if (operationIdCounter == 0) ++operationIdCounter;
  diagnosticReport = EpdOperationReport{};
  diagnosticReport.operationId = operationIdCounter;
  diagnosticReport.valid = true;
  diagnosticReport.running = true;
  diagnosticReport.spiHz = spiHz;
  return millis();
}

bool epdFinishOperation(uint32_t startedAtMs, bool sequenceOk) {
  diagnosticReport.sequenceOk = sequenceOk;
  diagnosticReport.totalMs = millis() - startedAtMs;
  diagnosticReport.finalBusyLevel = readBusyLevel();
  diagnosticReport.finalRstLevel = digitalRead(EPD_PIN_RST) ? 1U : 0U;
  diagnosticReport.finalCs1Level = digitalRead(EPD_PIN_CS) ? 1U : 0U;
  diagnosticReport.finalCs2Level =
      EPD_PIN_CS2 >= 0 && digitalRead(EPD_PIN_CS2) ? 1U : 0U;
  diagnosticReport.finalSckLevel = digitalRead(EPD_PIN_SCK) ? 1U : 0U;
  diagnosticReport.finalDcLevel = digitalRead(EPD_PIN_DC) ? 1U : 0U;
  diagnosticReport.finalMosiLevel = digitalRead(EPD_PIN_MOSI) ? 1U : 0U;
  diagnosticReport.running = false;
  return sequenceOk;
}

void epdRecordFailure(const char *stage, int32_t code = 0) {
  if (!diagnosticReport.running) return;
  copyStage(diagnosticReport.failureStage,
            sizeof(diagnosticReport.failureStage), stage);
  diagnosticReport.failureCode = code;
}

inline void setPinIfConnected(int pin, uint8_t value) {
  if (pin >= 0) digitalWrite(pin, value);
}

void setActiveControllers(bool cs1, bool cs2) {
  activeCs1 = cs1;
  activeCs2 = cs2 && EPD_PIN_CS2 >= 0;
  if (!activeCs1) digitalWrite(EPD_PIN_CS, HIGH);
  if (!activeCs2) setPinIfConnected(EPD_PIN_CS2, HIGH);
}

void writeSelectedCs(uint8_t value) {
  if (activeCs1) digitalWrite(EPD_PIN_CS, value);
  if (activeCs2) digitalWrite(EPD_PIN_CS2, value);
}

inline void epdDelayTick() {
  delayMicroseconds(2);
}

void epdHoldPanelPinsLow() {
  // Safe state while the ESP32 remains powered over USB but J2-1/panel VDD is
  // absent: no high GPIO can back-feed the unpowered display controller.
  digitalWrite(EPD_PIN_SCK, LOW);
  digitalWrite(EPD_PIN_DC, LOW);
  digitalWrite(EPD_PIN_MOSI, LOW);
  digitalWrite(EPD_PIN_RST, LOW);
  digitalWrite(EPD_PIN_CS, LOW);
  setPinIfConnected(EPD_PIN_CS2, LOW);
  setPinIfConnected(EPD_PIN_SWC, LOW);
}

void epdStartHardwareSpi() {
  if (EPD_USE_3WIRE_9BIT || hardwareSpiStarted) return;
  SPI.begin(EPD_PIN_SCK, -1, EPD_PIN_MOSI, EPD_PIN_CS);
  SPI.setFrequency(activeSpiHz);
  SPI.setDataMode(SPI_MODE0);
  SPI.setBitOrder(MSBFIRST);
  hardwareSpiStarted = true;
}

void epdStopHardwareSpi() {
  if (EPD_USE_3WIRE_9BIT || !hardwareSpiStarted) return;
  SPI.end();
  hardwareSpiStarted = false;
  pinMode(EPD_PIN_SCK, OUTPUT);
  pinMode(EPD_PIN_MOSI, OUTPUT);
}

bool epdFinishFailedOperationSafe(uint32_t startedAtMs,
                                  const char *failureStage,
                                  int32_t failureCode = 0) {
  epdRecordFailure(failureStage, failureCode);
  diagnosticReport.safeFinishBusyBeforePinsLow = readBusyLevel();
  epdStopHardwareSpi();
  epdHoldPanelPinsLow();
  diagnosticReport.safeFinishBusyAfterPinsLow = readBusyLevel();
  delay(5);
  diagnosticReport.safeFinishBusyAfter5Ms = readBusyLevel();
  return epdFinishOperation(startedAtMs, false);
}

bool epdRejectBeforePanelIo(uint32_t startedAtMs,
                            const char *failureStage,
                            int32_t failureCode = 0) {
  // The callers of this wrapper have not selected a controller, clocked SPI,
  // reset the panel, or issued a panel command. The shared safe finisher may
  // only preserve the already-established LOW state and sample BUSY.
  return epdFinishFailedOperationSafe(startedAtMs, failureStage, failureCode);
}

void epdWrite9(uint8_t dcx, uint8_t value) {
  writeSelectedCs(LOW);
  epdDelayTick();

  digitalWrite(EPD_PIN_MOSI, dcx ? HIGH : LOW);
  digitalWrite(EPD_PIN_SCK, HIGH);
  epdDelayTick();
  digitalWrite(EPD_PIN_SCK, LOW);
  epdDelayTick();

  for (uint8_t mask = 0x80; mask; mask >>= 1) {
    digitalWrite(EPD_PIN_MOSI, (value & mask) ? HIGH : LOW);
    epdDelayTick();
    digitalWrite(EPD_PIN_SCK, HIGH);
    epdDelayTick();
    digitalWrite(EPD_PIN_SCK, LOW);
    epdDelayTick();
  }

  digitalWrite(EPD_PIN_MOSI, LOW);
  epdDelayTick();
  writeSelectedCs(HIGH);
  epdDelayTick();
}

void epdWrite8(uint8_t dcx, uint8_t value) {
  digitalWrite(EPD_PIN_DC, dcx ? HIGH : LOW);
  writeSelectedCs(LOW);
  SPI.transfer(value);
  writeSelectedCs(HIGH);
}

void epdCommand(uint8_t command) {
  if (EPD_USE_3WIRE_9BIT) epdWrite9(0, command);
  else epdWrite8(0, command);
}

void epdData(uint8_t data) {
  if (EPD_USE_3WIRE_9BIT) epdWrite9(1, data);
  else epdWrite8(1, data);
}

void epdBitBangWrite8(uint8_t dcx, uint8_t value) {
  digitalWrite(EPD_PIN_DC, dcx ? HIGH : LOW);
  pinMode(EPD_PIN_MOSI, OUTPUT);
  digitalWrite(EPD_PIN_SCK, LOW);
  writeSelectedCs(LOW);
  epdDelayTick();
  for (uint8_t mask = 0x80; mask; mask >>= 1) {
    digitalWrite(EPD_PIN_MOSI, (value & mask) ? HIGH : LOW);
    epdDelayTick();
    digitalWrite(EPD_PIN_SCK, HIGH);
    epdDelayTick();
    digitalWrite(EPD_PIN_SCK, LOW);
  }
  epdDelayTick();
  writeSelectedCs(HIGH);
  epdDelayTick();
}

uint8_t epdBitBangRead8() {
  uint8_t value = 0;
  digitalWrite(EPD_PIN_DC, HIGH);
  digitalWrite(EPD_PIN_SCK, LOW);
  // SI0/SDA is bidirectional in the panel's documented 4-wire read mode.
  // Release GPIO11 before selecting the controller so the two outputs can
  // never contend.
  pinMode(EPD_PIN_MOSI, INPUT);
  epdDelayTick();
  writeSelectedCs(LOW);
  delayMicroseconds(4);
  for (uint8_t bit = 0; bit < 8; ++bit) {
    value <<= 1;
    digitalWrite(EPD_PIN_SCK, HIGH);
    epdDelayTick();
    if (digitalRead(EPD_PIN_MOSI)) value |= 0x01;
    digitalWrite(EPD_PIN_SCK, LOW);
    epdDelayTick();
  }
  writeSelectedCs(HIGH);
  epdDelayTick();
  pinMode(EPD_PIN_MOSI, OUTPUT);
  digitalWrite(EPD_PIN_MOSI, LOW);
  digitalWrite(EPD_PIN_DC, LOW);
  return value;
}

bool epdWaitIdle(const char *stage,
                 uint32_t timeoutMs = 60000,
                 bool requireBusyAssertion = false) {
  // The supplied sample waits for BUSY_N to become HIGH. The panel datasheet
  // text says the opposite, but reset/refresh measurements on this panel show
  // LOW while busy and HIGH while idle. Formal high-voltage stages first wait
  // for BUSY to assert, then wait for it to return idle. This prevents an
  // unplugged/miswired BUSY input from turning an immediate idle level into a
  // false successful refresh.
  const uint32_t started = millis();
  EpdBusyStageEvidence *stageEvidence = busyStageEvidence(stage);
  const uint8_t waitEntryLevel = readBusyLevel();
  if (stageEvidence) stageEvidence->waitEntryLevel = waitEntryLevel;
  bool sawBusy = waitEntryLevel != EPD_BUSY_IDLE_LEVEL;
  bool assertionAfterIdle =
      requireBusyAssertion && sawBusy && stageEvidence &&
      stageEvidence->preCommandIdleOk &&
      stageEvidence->preCommandLevel == EPD_BUSY_IDLE_LEVEL;
  uint32_t assertionLatencyMs = 0;
  if (requireBusyAssertion && !sawBusy) {
    while (millis() - started < EPD_BUSY_ASSERT_GRACE_MS) {
      if (digitalRead(EPD_PIN_BUSY) != EPD_BUSY_IDLE_LEVEL) {
        sawBusy = true;
        assertionAfterIdle =
            stageEvidence && stageEvidence->preCommandIdleOk &&
            stageEvidence->preCommandLevel == EPD_BUSY_IDLE_LEVEL;
        assertionLatencyMs = millis() - started;
        break;
      }
      delay(1);
    }
    if (!sawBusy) {
      const uint32_t elapsed = millis() - started;
      if (diagnosticReport.running) {
        diagnosticReport.lastWaitMs = elapsed;
        copyStage(diagnosticReport.lastWaitStage,
                  sizeof(diagnosticReport.lastWaitStage), stage);
        recordWaitEvidence(stage, elapsed, false);
        diagnosticReport.busyAssertionMissing = true;
        copyStage(diagnosticReport.busyMissingStage,
                  sizeof(diagnosticReport.busyMissingStage), stage);
      }
      epdRecordWaitTrace(stage, readBusyLevel(), false, 0, elapsed);
      Serial.printf("EPD busy assertion missing at %s after %lu ms, BUSY=%d\n",
                    stage, static_cast<unsigned long>(elapsed),
                    digitalRead(EPD_PIN_BUSY));
      return false;
    }
  } else if (!requireBusyAssertion) {
    delay(5);
    sawBusy = sawBusy || digitalRead(EPD_PIN_BUSY) != EPD_BUSY_IDLE_LEVEL;
  }
  Serial.printf("EPD wait idle: %s, BUSY=%d, idle=%d\n",
                stage, digitalRead(EPD_PIN_BUSY), EPD_BUSY_IDLE_LEVEL);
  uint32_t lastLog = started;
  while (digitalRead(EPD_PIN_BUSY) != EPD_BUSY_IDLE_LEVEL) {
    sawBusy = true;
    if (millis() - started > timeoutMs) {
      const uint32_t elapsed = millis() - started;
      if (diagnosticReport.running) {
        diagnosticReport.lastWaitMs = elapsed;
        copyStage(diagnosticReport.lastWaitStage,
                  sizeof(diagnosticReport.lastWaitStage), stage);
        recordWaitEvidence(stage, elapsed, sawBusy);
        if (!diagnosticReport.waitTimedOut) {
          diagnosticReport.waitTimedOut = true;
          copyStage(diagnosticReport.timeoutStage,
                    sizeof(diagnosticReport.timeoutStage), stage);
        }
      }
      epdRecordWaitTrace(stage, readBusyLevel(), assertionAfterIdle,
                         assertionLatencyMs, elapsed);
      Serial.printf("EPD busy timeout at %s, BUSY=%d, busy_seen=%d\n",
                    stage, digitalRead(EPD_PIN_BUSY), sawBusy);
      return false;
    }
    if (millis() - lastLog > 5000) {
      lastLog = millis();
      Serial.printf("EPD still busy at %s: %lu ms, BUSY=%d\n",
                    stage, static_cast<unsigned long>(millis() - started), digitalRead(EPD_PIN_BUSY));
    }
    delay(10);
  }
  Serial.printf("EPD idle: %s after %lu ms, busy_seen=%d\n",
                stage, static_cast<unsigned long>(millis() - started), sawBusy);
  const uint32_t elapsed = millis() - started;
  if (diagnosticReport.running) {
    diagnosticReport.lastWaitMs = elapsed;
    copyStage(diagnosticReport.lastWaitStage,
              sizeof(diagnosticReport.lastWaitStage), stage);
    recordWaitEvidence(stage, elapsed, sawBusy);
  }
  epdRecordWaitTrace(stage, readBusyLevel(), assertionAfterIdle,
                     assertionLatencyMs, elapsed);
  return true;
}

bool epdWaitBusyThenIdle(const char *stage, uint32_t timeoutMs = 60000) {
  return epdWaitIdle(stage, timeoutMs, true);
}

void epdRequestFailSafePowerOff(const char *cleanupStage) {
  epdCommand(POF);
  epdData(0x00);
  // If BUSY assertion itself is the broken signal, still give the controller
  // an assertion-sized window to accept POF before disconnecting its GPIOs.
  delay(EPD_BUSY_ASSERT_GRACE_MS);
  epdWaitIdle(cleanupStage, 30000);
  diagnosticReport.safeFinishBusyBeforePinsLow = readBusyLevel();
  epdStopHardwareSpi();
  epdHoldPanelPinsLow();
  diagnosticReport.safeFinishBusyAfterPinsLow = readBusyLevel();
  delay(5);
  diagnosticReport.safeFinishBusyAfter5Ms = readBusyLevel();
}

void epdReset() {
  // Official sample uses dual reset.
  digitalWrite(EPD_PIN_RST, LOW);
  delay(40);
  digitalWrite(EPD_PIN_RST, HIGH);
  delay(40);
  digitalWrite(EPD_PIN_RST, LOW);
  delay(40);
  digitalWrite(EPD_PIN_RST, HIGH);
}

bool epdPostDisplayPowerCut() {
  delay(6000);
  epdRecordInformationalCommandEntry("post-display PSR");
  epdCommand(PSR);
  epdData(0x4F);
  epdData(0x6E);
  // The vendor sequence writes this power-saving register after POF, waits
  // one second, and cuts the panel interface.  Rev A1 hardware confirmation
  // on 2026-08-04 showed valid PON/DRF/POF BUSY pulses and a perfect frame,
  // but no additional BUSY assertion for this post-POF register write.  Keep
  // the idle/timing evidence informational; requiring a new assertion here
  // creates a false failure after an otherwise completed safe refresh.
  const bool psrIdle = epdWaitIdle("post-display PSR");
  delay(1000);
  // Rev A1 leaves the ESP32 powered from USB when J2-1 is removed.  Hold every
  // panel-facing digital output LOW so the unpowered panel cannot be back-fed;
  // DC is a separate pin in 4-wire mode and must not be left HIGH.
  diagnosticReport.safeFinishBusyBeforePinsLow = readBusyLevel();
  epdStopHardwareSpi();
  epdHoldPanelPinsLow();
  diagnosticReport.safeFinishBusyAfterPinsLow = readBusyLevel();
  delay(5);
  diagnosticReport.safeFinishBusyAfter5Ms = readBusyLevel();
  return psrIdle;
}

bool epdSecondSettingAndRefresh() {
  Serial.println("EPD power on");
  if (!epdRequireIdleBeforeCommand("PON")) {
    Serial.println("EPD abort: BUSY not idle before PON; requesting safe power off");
    epdRequestFailSafePowerOff("POF cleanup after pre-PON busy");
    return false;
  }
  epdCommand(PON);
  if (!epdWaitBusyThenIdle("PON")) {
    Serial.println("EPD abort: PON BUSY failure; requesting safe power off");
    epdRequestFailSafePowerOff("POF cleanup after PON failure");
    return false;
  }

  epdCommand(BTST2);
  epdData(0x6F);
  epdData(0x1F);
  epdData(0x17);
  epdData(0x49);

  Serial.println("EPD display refresh");
  if (!epdRequireIdleBeforeCommand("DRF")) {
    Serial.println("EPD abort: BUSY not idle before DRF; requesting safe power off");
    epdRequestFailSafePowerOff("POF cleanup after pre-DRF busy");
    return false;
  }
  epdCommand(DRF);
  epdData(0x00);
  if (!epdWaitBusyThenIdle("DRF")) {
    Serial.println("EPD abort: DRF BUSY failure; requesting safe power off");
    epdRequestFailSafePowerOff("POF cleanup after DRF failure");
    return false;
  }

  Serial.println("EPD power off");
  if (!epdRequireIdleBeforeCommand("POF")) {
    Serial.println("EPD abort: BUSY not idle before POF; requesting safe power off");
    epdRequestFailSafePowerOff("POF cleanup after pre-POF busy");
    return false;
  }
  epdCommand(POF);
  epdData(0x00);
  if (!epdWaitBusyThenIdle("POF")) {
    Serial.println("EPD abort: POF BUSY failure");
    diagnosticReport.safeFinishBusyBeforePinsLow = readBusyLevel();
    epdStopHardwareSpi();
    epdHoldPanelPinsLow();
    diagnosticReport.safeFinishBusyAfterPinsLow = readBusyLevel();
    delay(5);
    diagnosticReport.safeFinishBusyAfter5Ms = readBusyLevel();
    return false;
  }
  delay(10);

  return epdPostDisplayPowerCut();
}

struct RevisionSample {
  bool idle = false;
  uint8_t bytes[3] = {0, 0, 0};
};

RevisionSample epdReadRevisionOnce(bool secondController) {
  RevisionSample sample;
  digitalWrite(EPD_PIN_CS, HIGH);
  setPinIfConnected(EPD_PIN_CS2, HIGH);
  digitalWrite(EPD_PIN_SCK, LOW);
  digitalWrite(EPD_PIN_DC, LOW);
  pinMode(EPD_PIN_MOSI, OUTPUT);
  digitalWrite(EPD_PIN_MOSI, HIGH);
  digitalWrite(EPD_PIN_RST, HIGH);
  epdReset();
  sample.idle = epdWaitIdle(secondController ? "REV CS2 reset" : "REV CS1 reset", 3000);
  if (!sample.idle) return sample;

  setActiveControllers(!secondController, secondController);
  epdBitBangWrite8(0, REV);
  for (uint8_t &value : sample.bytes) value = epdBitBangRead8();
  return sample;
}

} // namespace

bool epdIsSupportedColorCode(uint8_t color) {
#if defined(MF1750_L535_FRAME_PATH_BUILD)
  // L535 frame path: all eight nibbles are drive codes (white=7).
  return color <= 7;
#endif
  switch (color) {
    case EPD_COLOR_BLACK:
    case EPD_COLOR_WHITE:
    case EPD_COLOR_YELLOW:
    case EPD_COLOR_RED:
    case EPD_COLOR_BLUE:
    case EPD_COLOR_GREEN:
      return true;
    default:
      return false;
  }
}

bool epdValidateFrameColors(const uint8_t *frame, size_t len,
                            size_t *invalidPixel, uint8_t *invalidCode) {
  if (!frame) return false;
  for (size_t byteIndex = 0; byteIndex < len; ++byteIndex) {
    const uint8_t high = (frame[byteIndex] >> 4) & 0x0F;
    const uint8_t low = frame[byteIndex] & 0x0F;
    if (!epdIsSupportedColorCode(high) || !epdIsSupportedColorCode(low)) {
      const bool highInvalid = !epdIsSupportedColorCode(high);
      if (invalidPixel) *invalidPixel = byteIndex * 2 + (highInvalid ? 0 : 1);
      if (invalidCode) *invalidCode = highInvalid ? high : low;
      return false;
    }
  }
  return true;
}

void epdBegin() {
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
  // USB may be connected while panel VDD is deliberately absent. Keep every
  // panel-facing GPIO low until an explicit diagnostic starts.
  epdHoldPanelPinsLow();
  delay(10);
}

int epdReadBusy() {
  return digitalRead(EPD_PIN_BUSY);
}

void epdResetOnly() {
  // Diagnostic reset only: do not send SPI commands or start the high-voltage rails.
  digitalWrite(EPD_PIN_CS, HIGH);
  setPinIfConnected(EPD_PIN_CS2, HIGH);
  digitalWrite(EPD_PIN_SCK, LOW);
  digitalWrite(EPD_PIN_DC, LOW);
  epdReset();
  delay(100);
}

String epdDiagnosticReadRevisionsJson() {
  if (EPD_USE_3WIRE_9BIT) {
    return "{\"safe_no_hv\":false,\"error\":\"requires_4wire_mode\"}";
  }
  if (EPD_PIN_CS2 < 0) {
    return "{\"safe_no_hv\":false,\"error\":\"cs2_disabled\"}";
  }

  Serial.println("EPD REV diagnostic start: command 0x70 only; PON/DRF are forbidden");
  epdStopHardwareSpi();
  const RevisionSample cs1First = epdReadRevisionOnce(false);
  const RevisionSample cs1Second = epdReadRevisionOnce(false);
  const RevisionSample cs2First = epdReadRevisionOnce(true);
  const RevisionSample cs2Second = epdReadRevisionOnce(true);

  const bool cs1Stable = cs1First.idle && cs1Second.idle &&
                         std::memcmp(cs1First.bytes, cs1Second.bytes, sizeof(cs1First.bytes)) == 0;
  const bool cs2Stable = cs2First.idle && cs2Second.idle &&
                         std::memcmp(cs2First.bytes, cs2Second.bytes, sizeof(cs2First.bytes)) == 0;
  char json[640];
  std::snprintf(
      json, sizeof(json),
      "{\"safe_no_hv\":true,\"command\":112,"
      "\"cs1\":{\"idle1\":%s,\"sample1\":[%u,%u,%u],\"idle2\":%s,"
      "\"sample2\":[%u,%u,%u],\"stable\":%s,\"revision\":%u},"
      "\"cs2\":{\"idle1\":%s,\"sample1\":[%u,%u,%u],\"idle2\":%s,"
      "\"sample2\":[%u,%u,%u],\"stable\":%s,\"revision\":%u}}",
      cs1First.idle ? "true" : "false",
      cs1First.bytes[0], cs1First.bytes[1], cs1First.bytes[2],
      cs1Second.idle ? "true" : "false",
      cs1Second.bytes[0], cs1Second.bytes[1], cs1Second.bytes[2],
      cs1Stable ? "true" : "false", cs1Second.bytes[2],
      cs2First.idle ? "true" : "false",
      cs2First.bytes[0], cs2First.bytes[1], cs2First.bytes[2],
      cs2Second.idle ? "true" : "false",
      cs2Second.bytes[0], cs2Second.bytes[1], cs2Second.bytes[2],
      cs2Stable ? "true" : "false", cs2Second.bytes[2]);
  Serial.printf("EPD REV diagnostic result: %s\n", json);
  epdHoldPanelPinsLow();
  return String(json);
}

void epdDiagnosticSetCsLevel(bool high) {
  // Static CS1 level only: CS2 remains HIGH and SCK remains LOW, so no
  // command/data bit can be clocked.
  setActiveControllers(true, false);
  digitalWrite(EPD_PIN_SCK, LOW);
  digitalWrite(EPD_PIN_DC, LOW);
  digitalWrite(EPD_PIN_MOSI, LOW);
  digitalWrite(EPD_PIN_CS, high ? HIGH : LOW);
  setPinIfConnected(EPD_PIN_CS2, HIGH);
  Serial.printf("EPD static CS1 diagnostic: CS1=%d, CS2=1, SCK=0, DC=0, MOSI=0\n",
                high ? 1 : 0);
}

void epdDiagnosticSetCs2Level(bool high) {
  // Static CS2 level only: CS1 remains HIGH and SCK remains LOW.
  if (EPD_PIN_CS2 < 0) {
    Serial.println("EPD static CS2 diagnostic unavailable: CS2 pin disabled");
    return;
  }
  setActiveControllers(false, true);
  digitalWrite(EPD_PIN_SCK, LOW);
  digitalWrite(EPD_PIN_DC, LOW);
  digitalWrite(EPD_PIN_MOSI, LOW);
  digitalWrite(EPD_PIN_CS, HIGH);
  digitalWrite(EPD_PIN_CS2, high ? HIGH : LOW);
  Serial.printf("EPD static CS2 diagnostic: CS1=1, CS2=%d, SCK=0, DC=0, MOSI=0\n",
                high ? 1 : 0);
}

void epdDiagnosticReleasePins() {
  setActiveControllers(true, false);
  digitalWrite(EPD_PIN_CS, HIGH);
  setPinIfConnected(EPD_PIN_CS2, HIGH);
  digitalWrite(EPD_PIN_SCK, LOW);
  digitalWrite(EPD_PIN_DC, LOW);
  digitalWrite(EPD_PIN_MOSI, HIGH);
  digitalWrite(EPD_PIN_RST, HIGH);
  Serial.println("EPD diagnostic pins released to idle");
}

String epdDiagnosticReportJson() {
  String json = "{\"operation_id\":" + String(diagnosticReport.operationId) +
                ",\"valid\":" + String(diagnosticReport.valid ? "true" : "false") +
                ",\"running\":" + String(diagnosticReport.running ? "true" : "false") +
                ",\"sequence_ok\":" + String(diagnosticReport.sequenceOk ? "true" : "false") +
                ",\"wait_timeout\":" + String(diagnosticReport.waitTimedOut ? "true" : "false") +
                ",\"busy_assertion_missing\":" +
                String(diagnosticReport.busyAssertionMissing ? "true" : "false") +
                ",\"busy_assert_grace_ms\":" + String(EPD_BUSY_ASSERT_GRACE_MS) +
                ",\"mapping_applied\":" + String(diagnosticReport.mappingApplied ? "true" : "false") +
                ",\"pon_busy_seen\":" + String(diagnosticReport.ponBusySeen ? "true" : "false") +
                ",\"drf_busy_seen\":" + String(diagnosticReport.drfBusySeen ? "true" : "false") +
                ",\"pof_busy_seen\":" + String(diagnosticReport.pofBusySeen ? "true" : "false") +
                ",\"post_psr_busy_seen\":" + String(diagnosticReport.postPsrBusySeen ? "true" : "false") +
                ",\"pre_command_idle_failure\":" +
                String(diagnosticReport.preCommandIdleFailure ? "true" : "false") +
                ",\"failure_stage\":\"" +
                String(diagnosticReport.failureStage) +
                "\",\"failure_code\":" +
                String(diagnosticReport.failureCode) +
                ",\"spi_hz\":" + String(diagnosticReport.spiHz) +
                ",\"free_psram_before\":" +
                String(diagnosticReport.freePsramBefore) +
                ",\"largest_psram_block_before\":" +
                String(diagnosticReport.largestPsramBlockBefore) +
                ",\"input_fnv1a\":" + String(diagnosticReport.inputFrameFnv1a) +
                ",\"cs1_dtm_fnv1a\":" + String(diagnosticReport.cs1DtmFnv1a) +
                ",\"cs2_dtm_fnv1a\":" + String(diagnosticReport.cs2DtmFnv1a) +
                ",\"total_ms\":" + String(diagnosticReport.totalMs) +
                ",\"cs1_upload_ms\":" + String(diagnosticReport.cs1UploadMs) +
                ",\"cs2_upload_ms\":" + String(diagnosticReport.cs2UploadMs) +
                ",\"pon_ms\":" + String(diagnosticReport.ponWaitMs) +
                ",\"drf_ms\":" + String(diagnosticReport.drfWaitMs) +
                ",\"pof_ms\":" + String(diagnosticReport.pofWaitMs) +
                ",\"post_psr_ms\":" + String(diagnosticReport.postPsrWaitMs) +
                ",\"last_wait_ms\":" + String(diagnosticReport.lastWaitMs) +
                ",\"last_wait_stage\":\"" + String(diagnosticReport.lastWaitStage) +
                "\",\"timeout_stage\":\"" + String(diagnosticReport.timeoutStage) +
                "\",\"busy_missing_stage\":\"" + String(diagnosticReport.busyMissingStage) +
                "\",\"pre_command_busy_stage\":\"" +
                String(diagnosticReport.preCommandBusyStage) +
                "\",\"busy_trace_schema_version\":1,\"busy_trace\":{" +
                "\"idle_level\":" + String(EPD_BUSY_IDLE_LEVEL) +
                ",\"pre_command_idle_timeout_ms\":" +
                String(EPD_PRE_COMMAND_IDLE_TIMEOUT_MS) +
                ",\"assert_grace_ms\":" + String(EPD_BUSY_ASSERT_GRACE_MS) +
                ",\"reset\":" + epdBusyStageEvidenceJson(diagnosticReport.resetBusy) +
                ",\"pon\":" + epdBusyStageEvidenceJson(diagnosticReport.ponBusy) +
                ",\"drf\":" + epdBusyStageEvidenceJson(diagnosticReport.drfBusy) +
                ",\"pof\":" + epdBusyStageEvidenceJson(diagnosticReport.pofBusy) +
                ",\"post_psr\":" + epdBusyStageEvidenceJson(diagnosticReport.postPsrBusy) +
                ",\"safe_finish\":{\"busy_before_pins_low\":" +
                String(static_cast<unsigned>(diagnosticReport.safeFinishBusyBeforePinsLow)) +
                ",\"busy_after_pins_low\":" +
                String(static_cast<unsigned>(diagnosticReport.safeFinishBusyAfterPinsLow)) +
                ",\"busy_after_5ms\":" +
                String(static_cast<unsigned>(diagnosticReport.safeFinishBusyAfter5Ms)) +
                "},\"final_gpio\":{\"busy\":" +
                String(static_cast<unsigned>(diagnosticReport.finalBusyLevel)) +
                ",\"rst\":" +
                String(static_cast<unsigned>(diagnosticReport.finalRstLevel)) +
                ",\"cs\":" +
                String(static_cast<unsigned>(diagnosticReport.finalCs1Level)) +
                ",\"cs2\":" +
                String(static_cast<unsigned>(diagnosticReport.finalCs2Level)) +
                ",\"sck\":" +
                String(static_cast<unsigned>(diagnosticReport.finalSckLevel)) +
                ",\"dc\":" +
                String(static_cast<unsigned>(diagnosticReport.finalDcLevel)) +
                ",\"mosi\":" +
                String(static_cast<unsigned>(diagnosticReport.finalMosiLevel)) +
                "}},\"mapping\":{" +
                "\"cs1_source_half\":" + String(EPD_CS1_SOURCE_HALF) +
                ",\"cs1_flip_x\":" + String(EPD_CS1_FLIP_X ? "true" : "false") +
                ",\"cs1_flip_y\":" + String(EPD_CS1_FLIP_Y ? "true" : "false") +
                ",\"cs1_nibble_swap\":" + String(EPD_CS1_NIBBLE_SWAP ? "true" : "false") +
                ",\"cs2_source_half\":" + String(EPD_CS2_SOURCE_HALF) +
                ",\"cs2_flip_x\":" + String(EPD_CS2_FLIP_X ? "true" : "false") +
                ",\"cs2_flip_y\":" + String(EPD_CS2_FLIP_Y ? "true" : "false") +
                ",\"cs2_nibble_swap\":" + String(EPD_CS2_NIBBLE_SWAP ? "true" : "false") + "}}";
  return json;
}

const EpdOperationReport &epdGetLastOperationReport() {
  return diagnosticReport;
}

static void epdSetSpiFrequency(uint32_t hz) {
  activeSpiHz = hz;
  if (!EPD_USE_3WIRE_9BIT && hardwareSpiStarted) SPI.setFrequency(activeSpiHz);
  Serial.printf("EPD SPI frequency: %lu Hz\n", static_cast<unsigned long>(activeSpiHz));
}

static bool epdInitResolutionSelected(uint16_t width,
                                      uint16_t height,
                                      bool selectCs1,
                                      bool selectCs2) {
  Serial.printf("EPD init start: TRES=%ux%u, SPI=%lu Hz\n",
                width, height, static_cast<unsigned long>(activeSpiHz));
  // Safe idle holds reset and both chip-selects LOW. While reset remains
  // asserted, release both selects as plain GPIO before attaching the SPI
  // matrix, eliminating any selected-controller edge during SPI startup.
  digitalWrite(EPD_PIN_RST, LOW);
  digitalWrite(EPD_PIN_SCK, LOW);
  digitalWrite(EPD_PIN_DC, LOW);
  pinMode(EPD_PIN_MOSI, OUTPUT);
  digitalWrite(EPD_PIN_MOSI, LOW);
  digitalWrite(EPD_PIN_CS, HIGH);
  setPinIfConnected(EPD_PIN_CS2, HIGH);
  delayMicroseconds(10);
  epdStartHardwareSpi();
  digitalWrite(EPD_PIN_CS, HIGH);
  setPinIfConnected(EPD_PIN_CS2, HIGH);
  setActiveControllers(selectCs1, selectCs2);
  setPinIfConnected(EPD_PIN_SWC, HIGH);
  setPinIfConnected(EPD_PIN_BS, HIGH);
  digitalWrite(EPD_PIN_SCK, LOW);
  digitalWrite(EPD_PIN_DC, LOW);
  digitalWrite(EPD_PIN_MOSI, HIGH);
  delay(1);

  epdReset();
  if (!epdWaitIdle("reset")) {
    Serial.println("EPD init abort: reset timeout");
    return false;
  }
  delay(40);

  epdCommand(0xAA);
  epdData(0x49);
  epdData(0x55);
  epdData(0x20);
  epdData(0x08);
  epdData(0x09);
  epdData(0x18);

  epdCommand(PWR);
  epdData(0x3F);

  epdCommand(PSR);
  epdData(0x5F);
  epdData(0x69);

  epdCommand(BTST1);
  epdData(0x40);
  epdData(0x1F);
  epdData(0x1F);
  epdData(0x2C);

  epdCommand(BTST3);
  epdData(0x6F);
  epdData(0x1F);
  epdData(0x1F);
  epdData(0x22);

  epdCommand(BTST2);
  epdData(0x6F);
  epdData(0x1F);
  epdData(0x17);
  epdData(0x17);

  epdCommand(POFS);
  epdData(0x00);
  epdData(0x54);
  epdData(0x00);
  epdData(0x44);

  epdCommand(TCON);
  epdData(0x02);
  epdData(0x00);

  epdCommand(PLL);
  epdData(0x08);

  epdCommand(CDI);
  epdData(0x3F);

  epdCommand(TRES);
  epdData(width >> 8);
  epdData(width & 0xFF);
  epdData(height >> 8);
  epdData(height & 0xFF);

  epdCommand(PWS);
  epdData(0x2F);

  epdCommand(T_VDCS);
  epdData(0x01);
  Serial.println("EPD init done");
  return true;
}

static bool epdInitResolution(uint16_t width, uint16_t height) {
  return epdInitResolutionSelected(width, height, true, true);
}

static void epdStreamFillBytes(size_t streamBytes, uint8_t fillByte) {
  for (size_t i = 0; i < streamBytes; ++i) {
    epdData(fillByte);
    if ((i & 0x03FFU) == 0x03FFU) yield();
  }
}

static void epdStreamVerticalColorBars(uint16_t width, uint16_t height) {
  static constexpr uint8_t colors[] = {
      EPD_COLOR_WHITE,
      EPD_COLOR_BLACK,
      EPD_COLOR_RED,
      EPD_COLOR_YELLOW,
      EPD_COLOR_BLUE,
      EPD_COLOR_GREEN,
  };
  for (uint16_t y = 0; y < height; ++y) {
    for (uint16_t x = 0; x < width; x += 2) {
      const uint8_t first = colors[(static_cast<uint32_t>(x) * 6) / width] & 0x0F;
      const uint8_t second = colors[(static_cast<uint32_t>(x + 1) * 6) / width] & 0x0F;
      epdData((first << 4) | second);
    }
    if ((y & 0x0FU) == 0x0FU) yield();
  }
}

bool epdDiagnosticSolid(uint16_t tresWidth,
                        uint16_t tresHeight,
                        size_t streamBytes,
                        uint8_t fillByte,
                        uint32_t spiHz) {
  const uint32_t diagnosticStarted = epdBeginOperation(spiHz);
  if (tresWidth == 0 || tresHeight == 0 || streamBytes == 0 ||
      streamBytes > EPD_FRAME_BYTES) {
    Serial.println("EPD diagnostic rejected: invalid TRES or byte count");
    return epdFinishOperation(diagnosticStarted, false);
  }

  Serial.println("EPD DIAGNOSTIC: use one test per cold panel power cycle");
  Serial.printf("EPD diagnostic solid: TRES=%ux%u, bytes=%u, fill=0x%02X, SPI=%lu Hz\n",
                tresWidth, tresHeight, static_cast<unsigned>(streamBytes), fillByte,
                static_cast<unsigned long>(spiHz));
  epdSetSpiFrequency(spiHz);
  if (!epdInitResolution(tresWidth, tresHeight)) {
    epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
    epdStopHardwareSpi();
    epdHoldPanelPinsLow();
    return epdFinishOperation(diagnosticStarted, false);
  }

  setActiveControllers(true, false);
  epdCommand(DTM);
  const uint32_t uploadStarted = millis();
  epdStreamFillBytes(streamBytes, fillByte);
  diagnosticReport.cs1UploadMs = millis() - uploadStarted;
  Serial.printf("EPD diagnostic upload done after %lu ms\n",
                static_cast<unsigned long>(diagnosticReport.cs1UploadMs));

  setActiveControllers(true, false);
  const bool ok = epdSecondSettingAndRefresh();
  Serial.printf("EPD diagnostic result: %s\n", ok ? "PASS_SEQUENCE" : "FAILED_SEQUENCE");
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  return epdFinishOperation(diagnosticStarted, ok);
}

bool epdDiagnosticCs1ColorBars(uint32_t spiHz) {
  const uint32_t diagnosticStarted = epdBeginOperation(spiHz);

  Serial.println("EPD TRUE CS1-ONLY DIAGNOSTIC: cold panel power cycle required");
  Serial.println("Only CS1 is selected for reset follow-up, init, DTM, PON, DRF and POF");
  epdSetSpiFrequency(spiHz);
  if (!epdInitResolutionSelected(EPD_CONTROLLER_WIDTH, EPD_HEIGHT, true, false)) {
    epdStopHardwareSpi();
    epdHoldPanelPinsLow();
    return epdFinishOperation(diagnosticStarted, false);
  }

  setActiveControllers(true, false);
  epdCommand(DTM);
  const uint32_t uploadStarted = millis();
  epdStreamVerticalColorBars(EPD_CONTROLLER_WIDTH, EPD_HEIGHT);
  diagnosticReport.cs1UploadMs = millis() - uploadStarted;
  Serial.printf("EPD isolated CS1 six-color upload done after %lu ms\n",
                static_cast<unsigned long>(diagnosticReport.cs1UploadMs));

  setActiveControllers(true, false);
  const bool ok = epdSecondSettingAndRefresh();
  Serial.printf("EPD true CS1-only result: %s\n", ok ? "PASS_SEQUENCE" : "FAILED_SEQUENCE");
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  return epdFinishOperation(diagnosticStarted, ok);
}

static void epdEnableCascadeOnBothControllers() {
  setActiveControllers(true, false);
  epdCommand(CCSET);
  epdData(0x01);
  setActiveControllers(false, true);
  epdCommand(CCSET);
  epdData(0x01);
  Serial.println("EPD cascade enabled: CCSET 0xE0=0x01 written to CS1 and CS2");
}

static bool epdPrepareCascade(uint32_t spiHz) {
  epdSetSpiFrequency(spiHz);
  if (!epdInitResolutionSelected(EPD_CONTROLLER_WIDTH, EPD_HEIGHT, true, true)) {
    epdStopHardwareSpi();
    epdHoldPanelPinsLow();
    return false;
  }
  epdEnableCascadeOnBothControllers();
  return true;
}

static bool epdDiagnosticDualSolidImpl(uint8_t firstFillByte,
                                       uint8_t secondFillByte,
                                       uint32_t spiHz,
                                       bool enableCascade) {
  const uint32_t diagnosticStarted = epdBeginOperation(spiHz);
  if (EPD_PIN_CS2 < 0) {
    Serial.println("EPD dual-CS diagnostic rejected: CS2 pin disabled");
    epdStopHardwareSpi();
    epdHoldPanelPinsLow();
    return epdFinishOperation(diagnosticStarted, false);
  }

  Serial.println("EPD DUAL-CS DIAGNOSTIC: use one test per cold panel power cycle");
  Serial.printf("EPD dual solid: each TRES=%ux%u, each bytes=%u, CS1 fill=0x%02X, CS2 fill=0x%02X, SPI=%lu Hz, cascade_trial=%d\n",
                EPD_CONTROLLER_WIDTH, EPD_HEIGHT,
                static_cast<unsigned>(EPD_CONTROLLER_FRAME_BYTES),
                firstFillByte, secondFillByte,
                static_cast<unsigned long>(spiHz), enableCascade ? 1 : 0);
  epdSetSpiFrequency(spiHz);
  if (!epdInitResolution(EPD_CONTROLLER_WIDTH, EPD_HEIGHT)) {
    epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
    epdStopHardwareSpi();
    epdHoldPanelPinsLow();
    return epdFinishOperation(diagnosticStarted, false);
  }

  if (enableCascade) {
    // Initially inferred from SPD1656, then validated on the actual MF-1750:
    // white/black reversal, repeated half-bars, and continuous global six-color
    // bars all require this bit. Write it separately to both SPD1657B devices.
    epdEnableCascadeOnBothControllers();
  }

  setActiveControllers(true, false);
  epdCommand(DTM);
  const uint32_t firstUploadStarted = millis();
  epdStreamFillBytes(EPD_CONTROLLER_FRAME_BYTES, firstFillByte);
  diagnosticReport.cs1UploadMs = millis() - firstUploadStarted;
  Serial.printf("EPD CS1 upload done after %lu ms\n",
                static_cast<unsigned long>(diagnosticReport.cs1UploadMs));

  setActiveControllers(false, true);
  epdCommand(DTM);
  const uint32_t secondUploadStarted = millis();
  epdStreamFillBytes(EPD_CONTROLLER_FRAME_BYTES, secondFillByte);
  diagnosticReport.cs2UploadMs = millis() - secondUploadStarted;
  Serial.printf("EPD CS2 upload done after %lu ms\n",
                static_cast<unsigned long>(diagnosticReport.cs2UploadMs));

  // Power and refresh both controllers together so their gate/source waveform
  // timing remains synchronized through the panel cascade signals.
  setActiveControllers(true, true);
  const bool ok = epdSecondSettingAndRefresh();
  Serial.printf("EPD dual-CS diagnostic result: %s\n",
                ok ? "PASS_SEQUENCE" : "FAILED_SEQUENCE");
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  return epdFinishOperation(diagnosticStarted, ok);
}


bool epdDiagnosticDualSolid(uint8_t firstFillByte,
                            uint8_t secondFillByte,
                            uint32_t spiHz) {
  return epdDiagnosticDualSolidImpl(firstFillByte, secondFillByte, spiHz, false);
}

bool epdDiagnosticDualCascadeSolid(uint8_t firstFillByte,
                                   uint8_t secondFillByte,
                                   uint32_t spiHz) {
  return epdDiagnosticDualSolidImpl(firstFillByte, secondFillByte, spiHz, true);
}

bool epdDiagnosticDualCascadeColorBars(uint32_t spiHz) {
  const uint32_t diagnosticStarted = epdBeginOperation(spiHz);
  if (EPD_PIN_CS2 < 0) {
    Serial.println("EPD dual cascade bars rejected: CS2 pin disabled");
    epdStopHardwareSpi();
    epdHoldPanelPinsLow();
    return epdFinishOperation(diagnosticStarted, false);
  }
  Serial.println("EPD DUAL CASCADE SIX-COLOR BARS: cold panel power cycle required");
  epdSetSpiFrequency(spiHz);
  if (!epdInitResolutionSelected(EPD_CONTROLLER_WIDTH, EPD_HEIGHT, true, true)) {
    epdStopHardwareSpi();
    epdHoldPanelPinsLow();
    return epdFinishOperation(diagnosticStarted, false);
  }

  epdEnableCascadeOnBothControllers();
  setActiveControllers(true, false);
  epdCommand(DTM);
  const uint32_t cs1Started = millis();
  epdStreamVerticalColorBars(EPD_CONTROLLER_WIDTH, EPD_HEIGHT);
  diagnosticReport.cs1UploadMs = millis() - cs1Started;
  Serial.printf("EPD CS1 six-color upload done after %lu ms\n",
                static_cast<unsigned long>(diagnosticReport.cs1UploadMs));

  setActiveControllers(false, true);
  epdCommand(DTM);
  const uint32_t cs2Started = millis();
  epdStreamVerticalColorBars(EPD_CONTROLLER_WIDTH, EPD_HEIGHT);
  diagnosticReport.cs2UploadMs = millis() - cs2Started;
  Serial.printf("EPD CS2 six-color upload done after %lu ms\n",
                static_cast<unsigned long>(diagnosticReport.cs2UploadMs));

  setActiveControllers(true, true);
  const bool ok = epdSecondSettingAndRefresh();
  Serial.printf("EPD dual cascade six-color result: %s\n",
                ok ? "PASS_SEQUENCE" : "FAILED_SEQUENCE");
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  return epdFinishOperation(diagnosticStarted, ok);
}

void epdStreamControllerFrame(bool secondController, uint8_t fillByte) {
  setActiveControllers(!secondController, secondController);
  epdCommand(DTM);
  for (size_t i = 0; i < EPD_CONTROLLER_FRAME_BYTES; ++i) {
    epdData(fillByte);
  }
}

static void epdStreamSolidFrame(uint16_t width, uint16_t height, uint8_t fillByte) {
  setActiveControllers(true, false);
  epdCommand(DTM);
  const size_t bytes = (static_cast<size_t>(width) * height) / 2;
  for (size_t i = 0; i < bytes; ++i) {
    epdData(fillByte);
  }
}

static uint32_t epdStreamPackedFrameController(const uint8_t *frame, bool secondController) {
  static constexpr size_t kFullRowBytes = EPD_WIDTH / 2;
  static constexpr size_t kControllerRowBytes = EPD_CONTROLLER_WIDTH / 2;
  const uint8_t controllerIndex = secondController ? 1 : 0;
  const ControllerMapping &mapping = CONTROLLER_MAPPINGS[controllerIndex];
  setActiveControllers(!secondController, secondController);
  epdCommand(DTM);
  uint32_t dtmHash = FNV1A_OFFSET_BASIS;
  for (uint16_t outputY = 0; outputY < EPD_HEIGHT; ++outputY) {
    const uint16_t sourceY = mapping.flipY ? EPD_HEIGHT - 1 - outputY : outputY;
    const size_t rowOffset = static_cast<size_t>(sourceY) * kFullRowBytes;
    const size_t halfOffset = static_cast<size_t>(mapping.sourceHalf) * kControllerRowBytes;
    const uint8_t *row = frame + rowOffset + halfOffset;
    for (size_t outputByte = 0; outputByte < kControllerRowBytes; ++outputByte) {
      const size_t sourceByte = mapping.flipX ? kControllerRowBytes - 1 - outputByte : outputByte;
      uint8_t value = row[sourceByte];
      // Reversing a 512-pixel row requires reversing bytes and swapping the
      // two pixels in every byte. An independent nibble correction composes
      // with that swap, hence XOR.
      if (mapping.flipX != mapping.nibbleSwap) value = (value << 4) | (value >> 4);
      dtmHash = fnv1aUpdate(dtmHash, value);
      epdData(value);
    }
    if ((outputY & 0x0FU) == 0x0FU) yield();
  }
  return dtmHash;
}

#if MF1750_ENABLE_UNKNOWN_PROBE

#ifndef MF1750_UNKNOWN_PROBE_CODE
#error "Experimental unknown-probe build requires MF1750_UNKNOWN_PROBE_CODE"
#endif

#if MF1750_UNKNOWN_PROBE_CODE != 4 && MF1750_UNKNOWN_PROBE_CODE != 7
#error "MF1750_UNKNOWN_PROBE_CODE must be exactly 4 or 7"
#endif

static_assert(EPD_CS1_SOURCE_HALF == 0 && !EPD_CS1_FLIP_X &&
                  !EPD_CS1_FLIP_Y && !EPD_CS1_NIBBLE_SWAP &&
                  EPD_CS2_SOURCE_HALF == 1 && !EPD_CS2_FLIP_X &&
                  !EPD_CS2_FLIP_Y && !EPD_CS2_NIBBLE_SWAP,
              "EC5 probe identities require the frozen MAP_ORIENT_V1 mapping");

namespace {

static constexpr uint8_t EC5_UNKNOWN_CODE = MF1750_UNKNOWN_PROBE_CODE;
static constexpr uint16_t EC5_ROI_Y0 = 268;
static constexpr uint16_t EC5_ROI_Y1 = 332;
static constexpr uint16_t EC5_LEFT_X0 = 224;
static constexpr uint16_t EC5_LEFT_X1 = 288;
static constexpr uint16_t EC5_RIGHT_X0 = 736;
static constexpr uint16_t EC5_RIGHT_X1 = 800;
static constexpr size_t EC5_UNKNOWN_PIXELS = 2U * 64U * 64U;
static constexpr size_t EC5_WHITE_PIXELS =
    static_cast<size_t>(EPD_WIDTH) * EPD_HEIGHT - EC5_UNKNOWN_PIXELS;

#if MF1750_UNKNOWN_PROBE_CODE == 4
static constexpr uint32_t EC5_FRAME_FNV1A = 0x68533DC5UL;
static constexpr uint32_t EC5_DTM_FNV1A = 0x15B7EDC5UL;
static constexpr uint8_t EC5_FRAME_SHA256[32] = {
    0x5A, 0x2E, 0x79, 0x7E, 0xA0, 0x58, 0x79, 0x7F,
    0x01, 0xFE, 0xFE, 0x6D, 0x07, 0x3B, 0xBB, 0x28,
    0xF3, 0x9B, 0xBB, 0xF7, 0x1C, 0x07, 0x8C, 0x1A,
    0xF7, 0x2D, 0xBB, 0x8F, 0xC3, 0xE5, 0x87, 0x7E,
};
static constexpr uint8_t EC5_DTM_SHA256[32] = {
    0xA8, 0x05, 0x6C, 0xDD, 0x45, 0x0F, 0x70, 0x70,
    0x9E, 0xC7, 0x5A, 0x0A, 0x04, 0x00, 0x0D, 0xFB,
    0xFB, 0x1F, 0x06, 0x00, 0x0A, 0xE5, 0x96, 0x42,
    0x09, 0x02, 0x15, 0x6B, 0xEC, 0x7B, 0xAB, 0x00,
};
static_assert(
    EC5_DTM_SHA256[0] == 0xA8 && EC5_DTM_SHA256[1] == 0x05 &&
        EC5_DTM_SHA256[2] == 0x6C && EC5_DTM_SHA256[3] == 0xDD &&
        EC5_DTM_SHA256[4] == 0x45 && EC5_DTM_SHA256[5] == 0x0F &&
        EC5_DTM_SHA256[6] == 0x70 && EC5_DTM_SHA256[7] == 0x70 &&
        EC5_DTM_SHA256[8] == 0x9E && EC5_DTM_SHA256[9] == 0xC7 &&
        EC5_DTM_SHA256[10] == 0x5A && EC5_DTM_SHA256[11] == 0x0A &&
        EC5_DTM_SHA256[12] == 0x04 && EC5_DTM_SHA256[13] == 0x00 &&
        EC5_DTM_SHA256[14] == 0x0D && EC5_DTM_SHA256[15] == 0xFB &&
        EC5_DTM_SHA256[16] == 0xFB && EC5_DTM_SHA256[17] == 0x1F &&
        EC5_DTM_SHA256[18] == 0x06 && EC5_DTM_SHA256[19] == 0x00 &&
        EC5_DTM_SHA256[20] == 0x0A && EC5_DTM_SHA256[21] == 0xE5 &&
        EC5_DTM_SHA256[22] == 0x96 && EC5_DTM_SHA256[23] == 0x42 &&
        EC5_DTM_SHA256[24] == 0x09 && EC5_DTM_SHA256[25] == 0x02 &&
        EC5_DTM_SHA256[26] == 0x15 && EC5_DTM_SHA256[27] == 0x6B &&
        EC5_DTM_SHA256[28] == 0xEC && EC5_DTM_SHA256[29] == 0x7B &&
        EC5_DTM_SHA256[30] == 0xAB && EC5_DTM_SHA256[31] == 0x00,
    "U04 compiled DTM SHA-256 bytes differ from the frozen host identity");
#else
static constexpr uint32_t EC5_FRAME_FNV1A = 0xA1C5ADC5UL;
static constexpr uint32_t EC5_DTM_FNV1A = 0x97F125C5UL;
static constexpr uint8_t EC5_FRAME_SHA256[32] = {
    0xD9, 0xD4, 0x38, 0x88, 0xC6, 0x8B, 0x48, 0x37,
    0x76, 0xBB, 0x43, 0xA5, 0x3C, 0xC1, 0x08, 0x4B,
    0x85, 0x49, 0xD0, 0x0D, 0x9F, 0xF7, 0x0E, 0xF2,
    0xF1, 0x22, 0x7F, 0xAF, 0xE0, 0xAC, 0x7B, 0x3E,
};
static constexpr uint8_t EC5_DTM_SHA256[32] = {
    0x2E, 0x21, 0x71, 0x2A, 0xEC, 0xA3, 0xEE, 0xEC,
    0x9E, 0x24, 0xD9, 0x31, 0x2F, 0x4A, 0x60, 0x1C,
    0x7B, 0x02, 0x12, 0x79, 0x2F, 0x7D, 0x34, 0x19,
    0xA1, 0x50, 0x44, 0x2C, 0xC8, 0x0E, 0xA6, 0xAC,
};
static_assert(
    EC5_DTM_SHA256[0] == 0x2E && EC5_DTM_SHA256[1] == 0x21 &&
        EC5_DTM_SHA256[2] == 0x71 && EC5_DTM_SHA256[3] == 0x2A &&
        EC5_DTM_SHA256[4] == 0xEC && EC5_DTM_SHA256[5] == 0xA3 &&
        EC5_DTM_SHA256[6] == 0xEE && EC5_DTM_SHA256[7] == 0xEC &&
        EC5_DTM_SHA256[8] == 0x9E && EC5_DTM_SHA256[9] == 0x24 &&
        EC5_DTM_SHA256[10] == 0xD9 && EC5_DTM_SHA256[11] == 0x31 &&
        EC5_DTM_SHA256[12] == 0x2F && EC5_DTM_SHA256[13] == 0x4A &&
        EC5_DTM_SHA256[14] == 0x60 && EC5_DTM_SHA256[15] == 0x1C &&
        EC5_DTM_SHA256[16] == 0x7B && EC5_DTM_SHA256[17] == 0x02 &&
        EC5_DTM_SHA256[18] == 0x12 && EC5_DTM_SHA256[19] == 0x79 &&
        EC5_DTM_SHA256[20] == 0x2F && EC5_DTM_SHA256[21] == 0x7D &&
        EC5_DTM_SHA256[22] == 0x34 && EC5_DTM_SHA256[23] == 0x19 &&
        EC5_DTM_SHA256[24] == 0xA1 && EC5_DTM_SHA256[25] == 0x50 &&
        EC5_DTM_SHA256[26] == 0x44 && EC5_DTM_SHA256[27] == 0x2C &&
        EC5_DTM_SHA256[28] == 0xC8 && EC5_DTM_SHA256[29] == 0x0E &&
        EC5_DTM_SHA256[30] == 0xA6 && EC5_DTM_SHA256[31] == 0xAC,
    "U07 compiled DTM SHA-256 bytes differ from the frozen host identity");
#endif

static constexpr const char *EC5_FAILURE_NONE = "none";
static constexpr const char *EC5_FAILURE_ALLOCATION = "allocation";
static constexpr const char *EC5_FAILURE_FRAME_BUILD = "frame_build";
static constexpr const char *EC5_FAILURE_FULL_SHA = "full_sha";
static constexpr const char *EC5_FAILURE_CS1_COMPUTE = "cs1_compute";
static constexpr const char *EC5_FAILURE_CS2_COMPUTE = "cs2_compute";
static constexpr const char *EC5_FAILURE_CS1_IDENTITY = "cs1_identity";
static constexpr const char *EC5_FAILURE_CS2_IDENTITY = "cs2_identity";
static constexpr const char *EC5_FAILURE_CASCADE_PREPARE = "cascade_prepare";
static constexpr const char *EC5_FAILURE_STREAM_IDENTITY = "stream_identity";
static constexpr const char *EC5_FAILURE_REFRESH_SEQUENCE = "refresh_sequence";

struct Ec5DtmIdentity {
  uint32_t fnv1a = 0;
  uint8_t sha256[32] = {};
};

struct Ec5FixtureValidation {
  const char *failureStage = EC5_FAILURE_NONE;
  int32_t failureCode = 0;
  uint32_t frameFnv1a = 0;
  Ec5DtmIdentity cs1;
  Ec5DtmIdentity cs2;
};

bool ec5PixelIsUnknown(uint16_t x, uint16_t y) {
  if (y < EC5_ROI_Y0 || y >= EC5_ROI_Y1) return false;
  return (x >= EC5_LEFT_X0 && x < EC5_LEFT_X1) ||
         (x >= EC5_RIGHT_X0 && x < EC5_RIGHT_X1);
}

bool ec5BuildAndValidateFrame(uint8_t *frame, uint32_t *frameFnv1a) {
  if (!frame || !frameFnv1a) return false;
  std::memset(frame, 0x11, EPD_FRAME_BYTES);
  const uint8_t unknownPair =
      static_cast<uint8_t>((EC5_UNKNOWN_CODE << 4) | EC5_UNKNOWN_CODE);
  static constexpr size_t kRowBytes = EPD_WIDTH / 2;
  for (uint16_t y = EC5_ROI_Y0; y < EC5_ROI_Y1; ++y) {
    std::memset(frame + static_cast<size_t>(y) * kRowBytes + EC5_LEFT_X0 / 2,
                unknownPair, (EC5_LEFT_X1 - EC5_LEFT_X0) / 2);
    std::memset(frame + static_cast<size_t>(y) * kRowBytes + EC5_RIGHT_X0 / 2,
                unknownPair, (EC5_RIGHT_X1 - EC5_RIGHT_X0) / 2);
  }

  size_t unknownCount = 0;
  size_t whiteCount = 0;
  bool layoutOk = true;
  for (uint16_t y = 0; layoutOk && y < EPD_HEIGHT; ++y) {
    const size_t rowOffset = static_cast<size_t>(y) * kRowBytes;
    for (uint16_t x = 0; x < EPD_WIDTH; x += 2) {
      const uint8_t value = frame[rowOffset + x / 2];
      const uint8_t high = static_cast<uint8_t>(value >> 4);
      const uint8_t low = static_cast<uint8_t>(value & 0x0F);
      const bool highUnknown = ec5PixelIsUnknown(x, y);
      const bool lowUnknown = ec5PixelIsUnknown(static_cast<uint16_t>(x + 1), y);
      const uint8_t expectedHigh = highUnknown ? EC5_UNKNOWN_CODE : EPD_COLOR_WHITE;
      const uint8_t expectedLow = lowUnknown ? EC5_UNKNOWN_CODE : EPD_COLOR_WHITE;
      if (high != expectedHigh || low != expectedLow) {
        layoutOk = false;
        break;
      }
      unknownCount += static_cast<size_t>(highUnknown) +
                      static_cast<size_t>(lowUnknown);
      whiteCount += static_cast<size_t>(!highUnknown) +
                    static_cast<size_t>(!lowUnknown);
    }
  }
  *frameFnv1a = fnv1a(frame, EPD_FRAME_BYTES);
  return layoutOk && unknownCount == EC5_UNKNOWN_PIXELS &&
         whiteCount == EC5_WHITE_PIXELS && *frameFnv1a == EC5_FRAME_FNV1A;
}

bool ec5ComputeDtmIdentity(const uint8_t *frame,
                           bool secondController,
                           Ec5DtmIdentity *identity,
                           int32_t *errorCode) {
  if (!frame || !identity || !errorCode) return false;
  *identity = Ec5DtmIdentity{};
  *errorCode = 0;
  static constexpr size_t kFullRowBytes = EPD_WIDTH / 2;
  static constexpr size_t kControllerRowBytes = EPD_CONTROLLER_WIDTH / 2;
  uint8_t mappedRow[kControllerRowBytes] = {};
  const uint8_t controllerIndex = secondController ? 1 : 0;
  const ControllerMapping &mapping = CONTROLLER_MAPPINGS[controllerIndex];
  mbedtls_sha256_context context;
  mbedtls_sha256_init(&context);
  const int startsResult = mbedtls_sha256_starts_ret(&context, 0);
  if (startsResult != 0) {
    *errorCode = startsResult;
    mbedtls_sha256_free(&context);
    return false;
  }
  uint32_t dtmHash = FNV1A_OFFSET_BASIS;
  for (uint16_t outputY = 0; outputY < EPD_HEIGHT; ++outputY) {
    const uint16_t sourceY = mapping.flipY ? EPD_HEIGHT - 1 - outputY : outputY;
    const size_t rowOffset = static_cast<size_t>(sourceY) * kFullRowBytes;
    const size_t halfOffset =
        static_cast<size_t>(mapping.sourceHalf) * kControllerRowBytes;
    const uint8_t *row = frame + rowOffset + halfOffset;
    for (size_t outputByte = 0; outputByte < kControllerRowBytes; ++outputByte) {
      const size_t sourceByte =
          mapping.flipX ? kControllerRowBytes - 1 - outputByte : outputByte;
      uint8_t value = row[sourceByte];
      if (mapping.flipX != mapping.nibbleSwap) value = (value << 4) | (value >> 4);
      mappedRow[outputByte] = value;
      dtmHash = fnv1aUpdate(dtmHash, value);
    }
    const int updateResult =
        mbedtls_sha256_update_ret(&context, mappedRow, sizeof(mappedRow));
    if (updateResult != 0) {
      *errorCode = updateResult;
      mbedtls_sha256_free(&context);
      return false;
    }
  }
  const int finishResult =
      mbedtls_sha256_finish_ret(&context, identity->sha256);
  mbedtls_sha256_free(&context);
  if (finishResult != 0) {
    *errorCode = finishResult;
    return false;
  }
  identity->fnv1a = dtmHash;
  return true;
}

bool ec5IdentityMatches(const Ec5DtmIdentity &identity) {
  return identity.fnv1a == EC5_DTM_FNV1A &&
         std::memcmp(identity.sha256, EC5_DTM_SHA256,
                      sizeof(identity.sha256)) == 0;
}

bool ec5ValidateFixture(uint8_t *frame, Ec5FixtureValidation *validation) {
  if (!frame || !validation) return false;
  *validation = Ec5FixtureValidation{};
  if (!ec5BuildAndValidateFrame(frame, &validation->frameFnv1a)) {
    validation->failureStage = EC5_FAILURE_FRAME_BUILD;
    return false;
  }

  uint8_t frameDigest[32] = {};
  const int fullShaResult =
      mbedtls_sha256_ret(frame, EPD_FRAME_BYTES, frameDigest, 0);
  if (fullShaResult != 0 ||
      std::memcmp(frameDigest, EC5_FRAME_SHA256, sizeof(frameDigest)) != 0) {
    validation->failureStage = EC5_FAILURE_FULL_SHA;
    validation->failureCode = fullShaResult;
    return false;
  }

  if (!ec5ComputeDtmIdentity(frame, false, &validation->cs1,
                             &validation->failureCode)) {
    validation->failureStage = EC5_FAILURE_CS1_COMPUTE;
    return false;
  }
  if (!ec5ComputeDtmIdentity(frame, true, &validation->cs2,
                             &validation->failureCode)) {
    validation->failureStage = EC5_FAILURE_CS2_COMPUTE;
    return false;
  }
  if (!ec5IdentityMatches(validation->cs1)) {
    validation->failureStage = EC5_FAILURE_CS1_IDENTITY;
    return false;
  }
  if (!ec5IdentityMatches(validation->cs2)) {
    validation->failureStage = EC5_FAILURE_CS2_IDENTITY;
    return false;
  }
  return true;
}

}  // namespace

bool epdValidateCompiledUnknownProbeFixture() {
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) return false;
  Ec5FixtureValidation validation;
  const bool valid = ec5ValidateFixture(frame, &validation);
  std::free(frame);
  return valid;
}

bool epdDisplayCompiledUnknownProbe() {
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  Serial.printf(
      "EC5 EXPERIMENTAL fixed unknown-code probe: code=0x%X, no retry\n",
      static_cast<unsigned>(EC5_UNKNOWN_CODE));
  diagnosticReport.freePsramBefore = ESP.getFreePsram();
  diagnosticReport.largestPsramBlockBefore =
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) {
    Serial.println("EC5 probe rejected before panel I/O: PSRAM allocation failed");
    return epdRejectBeforePanelIo(started, EC5_FAILURE_ALLOCATION);
  }

  Ec5FixtureValidation validation;
  const bool identityOk = ec5ValidateFixture(frame, &validation);
  diagnosticReport.inputFrameFnv1a = validation.frameFnv1a;
  diagnosticReport.cs1DtmFnv1a = validation.cs1.fnv1a;
  diagnosticReport.cs2DtmFnv1a = validation.cs2.fnv1a;
  if (!identityOk) {
    Serial.printf(
        "EC5 probe rejected before panel I/O: stage=%s, error_code=%ld\n",
        validation.failureStage,
        static_cast<long>(validation.failureCode));
    std::free(frame);
    return epdRejectBeforePanelIo(started, validation.failureStage,
                                  validation.failureCode);
  }

  if (!epdPrepareCascade(EPD_SPI_DEFAULT_HZ)) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started, EC5_FAILURE_CASCADE_PREPARE);
  }
  const uint32_t cs1Started = millis();
  diagnosticReport.cs1DtmFnv1a = epdStreamPackedFrameController(frame, false);
  diagnosticReport.cs1UploadMs = millis() - cs1Started;
  const uint32_t cs2Started = millis();
  diagnosticReport.cs2DtmFnv1a = epdStreamPackedFrameController(frame, true);
  diagnosticReport.cs2UploadMs = millis() - cs2Started;
  diagnosticReport.mappingApplied = true;
  std::free(frame);

  if (diagnosticReport.cs1DtmFnv1a != EC5_DTM_FNV1A ||
      diagnosticReport.cs2DtmFnv1a != EC5_DTM_FNV1A) {
    Serial.println("EC5 probe aborted before PON: streamed DTM identity mismatch");
    return epdFinishFailedOperationSafe(started, EC5_FAILURE_STREAM_IDENTITY);
  }
  setActiveControllers(true, true);
  const bool ok = epdSecondSettingAndRefresh();
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  Serial.printf("EC5 fixed probe refresh: %s\n", ok ? "PASS" : "FAILED");
  if (!ok) epdRecordFailure(EC5_FAILURE_REFRESH_SEQUENCE);
  return epdFinishOperation(started, ok);
}

#endif  // MF1750_ENABLE_UNKNOWN_PROBE

#if MF1750_ENABLE_U04_U05_COMPARE

static_assert(EPD_CS1_SOURCE_HALF == 0 && !EPD_CS1_FLIP_X &&
                  !EPD_CS1_FLIP_Y && !EPD_CS1_NIBBLE_SWAP &&
                  EPD_CS2_SOURCE_HALF == 1 && !EPD_CS2_FLIP_X &&
                  !EPD_CS2_FLIP_Y && !EPD_CS2_NIBBLE_SWAP,
              "EC5 U04/U05 comparison requires MAP_ORIENT_V1 mapping");

namespace {

static constexpr uint16_t COMPARE_TOP_Y0 = 188;
static constexpr uint16_t COMPARE_TOP_Y1 = 252;
static constexpr uint16_t COMPARE_BOTTOM_Y0 = 348;
static constexpr uint16_t COMPARE_BOTTOM_Y1 = 412;
static constexpr uint16_t COMPARE_CS1_X0 = 224;
static constexpr uint16_t COMPARE_CS1_X1 = 288;
static constexpr uint16_t COMPARE_CS2_X0 = 736;
static constexpr uint16_t COMPARE_CS2_X1 = 800;
static constexpr uint8_t COMPARE_U04_CODE = 0x4;
static constexpr uint8_t COMPARE_U05_CODE = EPD_COLOR_BLUE;
static constexpr size_t COMPARE_PIXELS_PER_CODE = 2U * 64U * 64U;
static constexpr size_t COMPARE_WHITE_PIXELS =
    static_cast<size_t>(EPD_WIDTH) * EPD_HEIGHT -
    2U * COMPARE_PIXELS_PER_CODE;

static constexpr uint32_t COMPARE_FRAME_FNV1A = 0x9A7A3DC5UL;
static constexpr uint32_t COMPARE_CS1_DTM_FNV1A = 0x65B20DC5UL;
static constexpr uint32_t COMPARE_CS2_DTM_FNV1A = 0xD9B20DC5UL;

// These are deliberately runtime-addressable local objects. The offline ELF
// gate reads the exact symbols from .symtab; matching bytes elsewhere do not
// satisfy the compiled-identity contract.
static const uint8_t EC5_FRAME_SHA256[32] = {
    0xC3, 0xF1, 0xD1, 0x9A, 0xDB, 0x80, 0x16, 0x93,
    0x39, 0xD3, 0x2A, 0x7E, 0x7E, 0x61, 0xBB, 0x5F,
    0x3A, 0x0D, 0xB9, 0xE2, 0xE8, 0x23, 0x08, 0x04,
    0x12, 0xEA, 0x91, 0x22, 0x7E, 0xAA, 0x31, 0x0D,
};
static const uint8_t EC5_CS1_DTM_SHA256[32] = {
    0x58, 0x3A, 0x45, 0xA8, 0x3F, 0x38, 0x13, 0x9E,
    0xA8, 0x23, 0x29, 0x4A, 0x1A, 0x0D, 0x6F, 0x41,
    0x75, 0xBE, 0xD4, 0x48, 0x76, 0xEC, 0x94, 0xD8,
    0x83, 0xFC, 0xC0, 0x43, 0x29, 0xDF, 0xDB, 0x50,
};
static const uint8_t EC5_CS2_DTM_SHA256[32] = {
    0xA9, 0xC4, 0xCE, 0xD5, 0x4F, 0xC4, 0x56, 0xF4,
    0x24, 0xF6, 0x15, 0xC6, 0x88, 0x5D, 0xD6, 0x61,
    0x51, 0x7E, 0xBD, 0xC8, 0xA1, 0x2E, 0xE9, 0x58,
    0x1D, 0x14, 0x20, 0xE1, 0xA9, 0x99, 0x6A, 0xD3,
};

static constexpr const char *COMPARE_FAILURE_NONE = "none";
static constexpr const char *COMPARE_FAILURE_ALLOCATION = "allocation";
static constexpr const char *COMPARE_FAILURE_FRAME_BUILD = "frame_build";
static constexpr const char *COMPARE_FAILURE_FULL_SHA = "full_sha";
static constexpr const char *COMPARE_FAILURE_CS1_COMPUTE = "cs1_compute";
static constexpr const char *COMPARE_FAILURE_CS2_COMPUTE = "cs2_compute";
static constexpr const char *COMPARE_FAILURE_CS1_IDENTITY = "cs1_identity";
static constexpr const char *COMPARE_FAILURE_CS2_IDENTITY = "cs2_identity";
static constexpr const char *COMPARE_FAILURE_CASCADE_PREPARE =
    "cascade_prepare";
static constexpr const char *COMPARE_FAILURE_STREAM_IDENTITY =
    "stream_identity";
static constexpr const char *COMPARE_FAILURE_REFRESH_SEQUENCE =
    "refresh_sequence";

struct CompareDtmIdentity {
  uint32_t fnv1a = 0;
  uint8_t sha256[32] = {};
};

struct CompareFixtureValidation {
  const char *failureStage = COMPARE_FAILURE_NONE;
  int32_t failureCode = 0;
  uint32_t frameFnv1a = 0;
  CompareDtmIdentity cs1;
  CompareDtmIdentity cs2;
};

bool compareInside(uint16_t x, uint16_t x0, uint16_t x1) {
  return x >= x0 && x < x1;
}

uint8_t compareExpectedCode(uint16_t x, uint16_t y) {
  const bool top = y >= COMPARE_TOP_Y0 && y < COMPARE_TOP_Y1;
  const bool bottom = y >= COMPARE_BOTTOM_Y0 && y < COMPARE_BOTTOM_Y1;
  const bool cs1 = compareInside(x, COMPARE_CS1_X0, COMPARE_CS1_X1);
  const bool cs2 = compareInside(x, COMPARE_CS2_X0, COMPARE_CS2_X1);
  if ((cs1 && top) || (cs2 && bottom)) {
    return COMPARE_U04_CODE;
  }
  if ((cs1 && bottom) || (cs2 && top)) {
    return COMPARE_U05_CODE;
  }
  return EPD_COLOR_WHITE;
}

void compareFillRoi(uint8_t *frame, uint16_t x0, uint16_t x1, uint16_t y0,
                    uint16_t y1, uint8_t code) {
  static constexpr size_t kRowBytes = EPD_WIDTH / 2;
  const uint8_t pair = static_cast<uint8_t>((code << 4) | code);
  for (uint16_t y = y0; y < y1; ++y) {
    std::memset(frame + static_cast<size_t>(y) * kRowBytes + x0 / 2, pair,
                (x1 - x0) / 2);
  }
}

bool compareBuildAndValidateFrame(uint8_t *frame, uint32_t *frameFnv1a) {
  if (!frame || !frameFnv1a) return false;
  std::memset(frame, 0x11, EPD_FRAME_BYTES);
  compareFillRoi(frame, COMPARE_CS1_X0, COMPARE_CS1_X1, COMPARE_TOP_Y0,
                 COMPARE_TOP_Y1, COMPARE_U04_CODE);
  compareFillRoi(frame, COMPARE_CS1_X0, COMPARE_CS1_X1, COMPARE_BOTTOM_Y0,
                 COMPARE_BOTTOM_Y1, COMPARE_U05_CODE);
  compareFillRoi(frame, COMPARE_CS2_X0, COMPARE_CS2_X1, COMPARE_TOP_Y0,
                 COMPARE_TOP_Y1, COMPARE_U05_CODE);
  compareFillRoi(frame, COMPARE_CS2_X0, COMPARE_CS2_X1, COMPARE_BOTTOM_Y0,
                 COMPARE_BOTTOM_Y1, COMPARE_U04_CODE);

  size_t histogram[16] = {};
  bool layoutOk = true;
  static constexpr size_t kRowBytes = EPD_WIDTH / 2;
  for (uint16_t y = 0; layoutOk && y < EPD_HEIGHT; ++y) {
    const size_t rowOffset = static_cast<size_t>(y) * kRowBytes;
    for (uint16_t x = 0; x < EPD_WIDTH; x += 2) {
      const uint8_t value = frame[rowOffset + x / 2];
      const uint8_t high = static_cast<uint8_t>(value >> 4);
      const uint8_t low = static_cast<uint8_t>(value & 0x0F);
      if (high != compareExpectedCode(x, y) ||
          low != compareExpectedCode(static_cast<uint16_t>(x + 1), y)) {
        layoutOk = false;
        break;
      }
      ++histogram[high];
      ++histogram[low];
    }
  }
  *frameFnv1a = fnv1a(frame, EPD_FRAME_BYTES);
  return layoutOk && histogram[EPD_COLOR_WHITE] == COMPARE_WHITE_PIXELS &&
         histogram[COMPARE_U04_CODE] == COMPARE_PIXELS_PER_CODE &&
         histogram[COMPARE_U05_CODE] == COMPARE_PIXELS_PER_CODE &&
         histogram[0] + histogram[2] + histogram[3] + histogram[6] +
                 histogram[7] + histogram[8] + histogram[9] + histogram[10] +
                 histogram[11] + histogram[12] + histogram[13] +
                 histogram[14] + histogram[15] ==
             0 &&
         *frameFnv1a == COMPARE_FRAME_FNV1A;
}

bool compareComputeDtmIdentity(const uint8_t *frame, bool secondController,
                               CompareDtmIdentity *identity,
                               int32_t *errorCode) {
  if (!frame || !identity || !errorCode) return false;
  *identity = CompareDtmIdentity{};
  *errorCode = 0;
  static constexpr size_t kFullRowBytes = EPD_WIDTH / 2;
  static constexpr size_t kControllerRowBytes = EPD_CONTROLLER_WIDTH / 2;
  uint8_t mappedRow[kControllerRowBytes] = {};
  const ControllerMapping &mapping =
      CONTROLLER_MAPPINGS[secondController ? 1 : 0];
  mbedtls_sha256_context context;
  mbedtls_sha256_init(&context);
  const int startsResult = mbedtls_sha256_starts_ret(&context, 0);
  if (startsResult != 0) {
    *errorCode = startsResult;
    mbedtls_sha256_free(&context);
    return false;
  }
  uint32_t dtmHash = FNV1A_OFFSET_BASIS;
  for (uint16_t outputY = 0; outputY < EPD_HEIGHT; ++outputY) {
    const uint16_t sourceY = mapping.flipY ? EPD_HEIGHT - 1 - outputY : outputY;
    const size_t rowOffset = static_cast<size_t>(sourceY) * kFullRowBytes;
    const size_t halfOffset =
        static_cast<size_t>(mapping.sourceHalf) * kControllerRowBytes;
    const uint8_t *row = frame + rowOffset + halfOffset;
    for (size_t outputByte = 0; outputByte < kControllerRowBytes;
         ++outputByte) {
      const size_t sourceByte = mapping.flipX
                                    ? kControllerRowBytes - 1 - outputByte
                                    : outputByte;
      uint8_t value = row[sourceByte];
      if (mapping.flipX != mapping.nibbleSwap)
        value = static_cast<uint8_t>((value << 4) | (value >> 4));
      mappedRow[outputByte] = value;
      dtmHash = fnv1aUpdate(dtmHash, value);
    }
    const int updateResult =
        mbedtls_sha256_update_ret(&context, mappedRow, sizeof(mappedRow));
    if (updateResult != 0) {
      *errorCode = updateResult;
      mbedtls_sha256_free(&context);
      return false;
    }
  }
  const int finishResult =
      mbedtls_sha256_finish_ret(&context, identity->sha256);
  mbedtls_sha256_free(&context);
  if (finishResult != 0) {
    *errorCode = finishResult;
    return false;
  }
  identity->fnv1a = dtmHash;
  return true;
}

bool compareIdentityMatches(const CompareDtmIdentity &identity,
                            bool secondController) {
  const uint32_t expectedFnv = secondController ? COMPARE_CS2_DTM_FNV1A
                                                : COMPARE_CS1_DTM_FNV1A;
  const uint8_t *expectedSha = secondController ? EC5_CS2_DTM_SHA256
                                                : EC5_CS1_DTM_SHA256;
  return identity.fnv1a == expectedFnv &&
         std::memcmp(identity.sha256, expectedSha, sizeof(identity.sha256)) ==
             0;
}

bool compareValidateFixture(uint8_t *frame,
                            CompareFixtureValidation *validation) {
  if (!frame || !validation) return false;
  *validation = CompareFixtureValidation{};
  if (!compareBuildAndValidateFrame(frame, &validation->frameFnv1a)) {
    validation->failureStage = COMPARE_FAILURE_FRAME_BUILD;
    return false;
  }
  uint8_t frameDigest[32] = {};
  const int fullShaResult =
      mbedtls_sha256_ret(frame, EPD_FRAME_BYTES, frameDigest, 0);
  if (fullShaResult != 0 ||
      std::memcmp(frameDigest, EC5_FRAME_SHA256, sizeof(frameDigest)) != 0) {
    validation->failureStage = COMPARE_FAILURE_FULL_SHA;
    validation->failureCode = fullShaResult;
    return false;
  }
  if (!compareComputeDtmIdentity(frame, false, &validation->cs1,
                                 &validation->failureCode)) {
    validation->failureStage = COMPARE_FAILURE_CS1_COMPUTE;
    return false;
  }
  if (!compareComputeDtmIdentity(frame, true, &validation->cs2,
                                 &validation->failureCode)) {
    validation->failureStage = COMPARE_FAILURE_CS2_COMPUTE;
    return false;
  }
  if (!compareIdentityMatches(validation->cs1, false)) {
    validation->failureStage = COMPARE_FAILURE_CS1_IDENTITY;
    return false;
  }
  if (!compareIdentityMatches(validation->cs2, true)) {
    validation->failureStage = COMPARE_FAILURE_CS2_IDENTITY;
    return false;
  }
  return true;
}

}  // namespace

bool epdValidateCompiledU04U05CompareFixture() {
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) return false;
  CompareFixtureValidation validation;
  const bool valid = compareValidateFixture(frame, &validation);
  std::free(frame);
  return valid;
}

bool epdDisplayCompiledU04U05Compare() {
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  Serial.println("EC5 fixed U04/U05 four-ROI comparison, no dither/retry");
  diagnosticReport.freePsramBefore = ESP.getFreePsram();
  diagnosticReport.largestPsramBlockBefore =
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) {
    return epdRejectBeforePanelIo(started, COMPARE_FAILURE_ALLOCATION);
  }

  CompareFixtureValidation validation;
  const bool identityOk = compareValidateFixture(frame, &validation);
  diagnosticReport.inputFrameFnv1a = validation.frameFnv1a;
  diagnosticReport.cs1DtmFnv1a = validation.cs1.fnv1a;
  diagnosticReport.cs2DtmFnv1a = validation.cs2.fnv1a;
  if (!identityOk) {
    std::free(frame);
    return epdRejectBeforePanelIo(started, validation.failureStage,
                                  validation.failureCode);
  }

  if (!epdPrepareCascade(EPD_SPI_DEFAULT_HZ)) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started,
                                        COMPARE_FAILURE_CASCADE_PREPARE);
  }
  const uint32_t cs1Started = millis();
  diagnosticReport.cs1DtmFnv1a = epdStreamPackedFrameController(frame, false);
  diagnosticReport.cs1UploadMs = millis() - cs1Started;
  const uint32_t cs2Started = millis();
  diagnosticReport.cs2DtmFnv1a = epdStreamPackedFrameController(frame, true);
  diagnosticReport.cs2UploadMs = millis() - cs2Started;
  diagnosticReport.mappingApplied = true;
  std::free(frame);

  if (diagnosticReport.cs1DtmFnv1a != COMPARE_CS1_DTM_FNV1A ||
      diagnosticReport.cs2DtmFnv1a != COMPARE_CS2_DTM_FNV1A) {
    return epdFinishFailedOperationSafe(started,
                                        COMPARE_FAILURE_STREAM_IDENTITY);
  }
  setActiveControllers(true, true);
  const bool ok = epdSecondSettingAndRefresh();
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  if (!ok) epdRecordFailure(COMPARE_FAILURE_REFRESH_SEQUENCE);
  return epdFinishOperation(started, ok);
}

#endif  // MF1750_ENABLE_U04_U05_COMPARE

#if MF1750_ENABLE_SIXSTATE_PROBE

#ifndef MF1750_UNKNOWN_PROBE_CODE
#error "Six-state experimental build requires MF1750_UNKNOWN_PROBE_CODE"
#endif

#if MF1750_UNKNOWN_PROBE_CODE != 4 && MF1750_UNKNOWN_PROBE_CODE != 7
#error "Six-state candidate must be exactly 4 or 7"
#endif

static_assert(EPD_WIDTH == 1024 && EPD_HEIGHT == 600 &&
                  EPD_FRAME_BYTES == 307200,
              "Six-state fixtures are frozen for 1024x600 packed 4bpp");
static_assert(EPD_CS1_SOURCE_HALF == 0 && !EPD_CS1_FLIP_X &&
                  !EPD_CS1_FLIP_Y && !EPD_CS1_NIBBLE_SWAP &&
                  EPD_CS2_SOURCE_HALF == 1 && !EPD_CS2_FLIP_X &&
                  !EPD_CS2_FLIP_Y && !EPD_CS2_NIBBLE_SWAP,
              "Six-state identities require frozen MAP_ORIENT_V1 mapping");

namespace {

static constexpr uint8_t SIXSTATE_CANDIDATE = MF1750_UNKNOWN_PROBE_CODE;
static constexpr uint16_t SIXSTATE_ROI_SIDE = 24;
static constexpr uint16_t SIXSTATE_LEFT_X0 = 244;
static constexpr uint16_t SIXSTATE_RIGHT_X0 = 756;
static constexpr uint16_t SIXSTATE_Y0[6] = {48, 144, 240, 336, 432, 528};
static constexpr uint8_t SIXSTATE_INITIAL_CODE[6] = {
    EPD_COLOR_WHITE, EPD_COLOR_BLACK, EPD_COLOR_RED,
    EPD_COLOR_YELLOW, EPD_COLOR_BLUE, EPD_COLOR_GREEN,
};
static constexpr size_t SIXSTATE_ROI_COUNT = 12;
static constexpr size_t SIXSTATE_TARGET_PIXELS =
    SIXSTATE_ROI_COUNT * SIXSTATE_ROI_SIDE * SIXSTATE_ROI_SIDE;

struct SixStateIdentity {
  uint32_t frameFnv1a;
  uint32_t dtmFnv1a;
  const char *frameSha256;
  const char *dtmSha256;
  uint32_t histogram[16];
};

static constexpr SixStateIdentity SIXSTATE_PRIMER_IDENTITY = {
    0xE4F04785UL,
    0x58214425UL,
    "94ee82ae66fe8372e8c1d977a158dc60d55c36da86fc44f8b2a9a01c6d47ab0e",
    "f5bb17a5726f851da2bf322ffea8f0ea791f70788184ada4261b89aa43dc39af",
    {1152, 608640, 1152, 1152, 0, 1152, 1152, 0,
     0, 0, 0, 0, 0, 0, 0, 0},
};

#if MF1750_UNKNOWN_PROBE_CODE == 4
static constexpr SixStateIdentity SIXSTATE_TARGET_IDENTITY = {
    0x263BD845UL,
    0xEF6ED905UL,
    "81b0ed1b715551ddb2546d4f123c5c3d479bc8802ff9d2570e38d9b57b4645e6",
    "c4efd83606b72c49b7c0d67865e4df98ef31e5d40f071299558e10c5a212dd0f",
    {0, 607488, 0, 0, 6912, 0, 0, 0,
     0, 0, 0, 0, 0, 0, 0, 0},
};
#else
static constexpr SixStateIdentity SIXSTATE_TARGET_IDENTITY = {
    0xF93BD8C5UL,
    0xE4D43B45UL,
    "149ba0f5c3fd779d6870f655b53d726d6d1297e016331de4d394e411410e0e21",
    "139a0aa919d78a1aa572db49a7c90fe3a4f29476ab4d80ba3bb0f439f0191b3d",
    {0, 607488, 0, 0, 0, 0, 0, 6912,
     0, 0, 0, 0, 0, 0, 0, 0},
};
#endif

static constexpr SixStateIdentity SIXSTATE_WHITE_IDENTITY = {
    0x13340DC5UL,
    0xB7A855C5UL,
    "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
    "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
    {0, 614400, 0, 0, 0, 0, 0, 0,
     0, 0, 0, 0, 0, 0, 0, 0},
};

const SixStateIdentity *sixStateIdentity(EpdSixStateRole role) {
  switch (role) {
    case EpdSixStateRole::Primer:
      return &SIXSTATE_PRIMER_IDENTITY;
    case EpdSixStateRole::Target:
      return &SIXSTATE_TARGET_IDENTITY;
    case EpdSixStateRole::White:
      return &SIXSTATE_WHITE_IDENTITY;
  }
  return nullptr;
}

const char *sixStateRoleName(EpdSixStateRole role) {
  switch (role) {
    case EpdSixStateRole::Primer:
      return "primer";
    case EpdSixStateRole::Target:
      return "target";
    case EpdSixStateRole::White:
      return "white";
  }
  return "invalid";
}

int sixStateRoiIndex(uint16_t x, uint16_t y) {
  const bool inX =
      (x >= SIXSTATE_LEFT_X0 && x < SIXSTATE_LEFT_X0 + SIXSTATE_ROI_SIDE) ||
      (x >= SIXSTATE_RIGHT_X0 && x < SIXSTATE_RIGHT_X0 + SIXSTATE_ROI_SIDE);
  if (!inX) return -1;
  for (uint8_t index = 0; index < 6; ++index) {
    if (y >= SIXSTATE_Y0[index] &&
        y < SIXSTATE_Y0[index] + SIXSTATE_ROI_SIDE) {
      return index;
    }
  }
  return -1;
}

uint8_t sixStateExpectedPixel(EpdSixStateRole role, uint16_t x, uint16_t y) {
  const int roi = sixStateRoiIndex(x, y);
  if (role == EpdSixStateRole::White || roi < 0) return EPD_COLOR_WHITE;
  if (role == EpdSixStateRole::Target) return SIXSTATE_CANDIDATE;
  return SIXSTATE_INITIAL_CODE[roi];
}

bool sixStateShaMatches(const uint8_t *data, size_t length,
                        const char *expectedHex) {
  if (!data || !expectedHex || std::strlen(expectedHex) != 64) return false;
  uint8_t digest[32] = {};
  if (mbedtls_sha256_ret(data, length, digest, 0) != 0) return false;
  static constexpr char kHex[] = "0123456789abcdef";
  for (size_t index = 0; index < sizeof(digest); ++index) {
    if (expectedHex[index * 2] != kHex[digest[index] >> 4] ||
        expectedHex[index * 2 + 1] != kHex[digest[index] & 0x0F]) {
      return false;
    }
  }
  return true;
}

bool sixStateBuildAndValidateFrame(EpdSixStateRole role, uint8_t *frame) {
  const SixStateIdentity *identity = sixStateIdentity(role);
  if (!identity || !frame) return false;
  std::memset(frame, 0x11, EPD_FRAME_BYTES);
  static constexpr size_t kRowBytes = EPD_WIDTH / 2;
  if (role != EpdSixStateRole::White) {
    for (uint8_t roi = 0; roi < 6; ++roi) {
      const uint8_t code = role == EpdSixStateRole::Target
                               ? SIXSTATE_CANDIDATE
                               : SIXSTATE_INITIAL_CODE[roi];
      const uint8_t pair = static_cast<uint8_t>((code << 4) | code);
      for (uint16_t y = SIXSTATE_Y0[roi];
           y < SIXSTATE_Y0[roi] + SIXSTATE_ROI_SIDE; ++y) {
        std::memset(frame + static_cast<size_t>(y) * kRowBytes +
                              SIXSTATE_LEFT_X0 / 2,
                    pair, SIXSTATE_ROI_SIDE / 2);
        std::memset(frame + static_cast<size_t>(y) * kRowBytes +
                              SIXSTATE_RIGHT_X0 / 2,
                    pair, SIXSTATE_ROI_SIDE / 2);
      }
    }
  }

  uint32_t histogram[16] = {};
  size_t roiPixels = 0;
  for (uint16_t y = 0; y < EPD_HEIGHT; ++y) {
    const size_t rowOffset = static_cast<size_t>(y) * kRowBytes;
    for (uint16_t x = 0; x < EPD_WIDTH; x += 2) {
      const uint8_t packed = frame[rowOffset + x / 2];
      const uint8_t high = packed >> 4;
      const uint8_t low = packed & 0x0F;
      if (high != sixStateExpectedPixel(role, x, y) ||
          low != sixStateExpectedPixel(role, static_cast<uint16_t>(x + 1), y)) {
        return false;
      }
      ++histogram[high];
      ++histogram[low];
      roiPixels += static_cast<size_t>(sixStateRoiIndex(x, y) >= 0);
      roiPixels +=
          static_cast<size_t>(sixStateRoiIndex(static_cast<uint16_t>(x + 1), y) >= 0);
    }
  }
  if (roiPixels != SIXSTATE_TARGET_PIXELS ||
      std::memcmp(histogram, identity->histogram, sizeof(histogram)) != 0 ||
      fnv1a(frame, EPD_FRAME_BYTES) != identity->frameFnv1a ||
      !sixStateShaMatches(frame, EPD_FRAME_BYTES, identity->frameSha256)) {
    return false;
  }
  return true;
}

bool sixStateComputeDtmIdentity(const uint8_t *frame, bool secondController,
                                uint32_t *fnvOut, uint8_t shaOut[32]) {
  if (!frame || !fnvOut || !shaOut) return false;
  static constexpr size_t kFullRowBytes = EPD_WIDTH / 2;
  static constexpr size_t kControllerRowBytes = EPD_CONTROLLER_WIDTH / 2;
  uint8_t mappedRow[kControllerRowBytes] = {};
  const ControllerMapping &mapping = CONTROLLER_MAPPINGS[secondController ? 1 : 0];
  mbedtls_sha256_context context;
  mbedtls_sha256_init(&context);
  if (mbedtls_sha256_starts_ret(&context, 0) != 0) {
    mbedtls_sha256_free(&context);
    return false;
  }
  uint32_t hash = FNV1A_OFFSET_BASIS;
  for (uint16_t outputY = 0; outputY < EPD_HEIGHT; ++outputY) {
    const uint16_t sourceY = mapping.flipY ? EPD_HEIGHT - 1 - outputY : outputY;
    const uint8_t *row = frame + static_cast<size_t>(sourceY) * kFullRowBytes +
                         static_cast<size_t>(mapping.sourceHalf) * kControllerRowBytes;
    for (size_t outputByte = 0; outputByte < kControllerRowBytes; ++outputByte) {
      const size_t sourceByte = mapping.flipX
                                    ? kControllerRowBytes - 1 - outputByte
                                    : outputByte;
      uint8_t value = row[sourceByte];
      if (mapping.flipX != mapping.nibbleSwap) value = (value << 4) | (value >> 4);
      mappedRow[outputByte] = value;
      hash = fnv1aUpdate(hash, value);
    }
    if (mbedtls_sha256_update_ret(&context, mappedRow, sizeof(mappedRow)) != 0) {
      mbedtls_sha256_free(&context);
      return false;
    }
  }
  const bool ok = mbedtls_sha256_finish_ret(&context, shaOut) == 0;
  mbedtls_sha256_free(&context);
  *fnvOut = hash;
  return ok;
}

bool sixStateDtmMatches(const uint8_t *frame, bool secondController,
                        const SixStateIdentity &identity) {
  uint32_t hash = 0;
  uint8_t digest[32] = {};
  if (!sixStateComputeDtmIdentity(frame, secondController, &hash, digest) ||
      hash != identity.dtmFnv1a) {
    return false;
  }
  static constexpr char kHex[] = "0123456789abcdef";
  for (size_t index = 0; index < sizeof(digest); ++index) {
    if (identity.dtmSha256[index * 2] != kHex[digest[index] >> 4] ||
        identity.dtmSha256[index * 2 + 1] != kHex[digest[index] & 0x0F]) {
      return false;
    }
  }
  return true;
}

}  // namespace

bool epdValidateCompiledSixStateFixtures() {
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) return false;
  static constexpr EpdSixStateRole kRoles[] = {
      EpdSixStateRole::Primer, EpdSixStateRole::Target,
      EpdSixStateRole::White,
  };
  bool ok = true;
  for (const EpdSixStateRole role : kRoles) {
    const SixStateIdentity *identity = sixStateIdentity(role);
    ok = identity && sixStateBuildAndValidateFrame(role, frame) &&
         sixStateDtmMatches(frame, false, *identity) &&
         sixStateDtmMatches(frame, true, *identity);
    if (!ok) break;
  }
  std::free(frame);
  return ok;
}

bool epdDisplayCompiledSixState(EpdSixStateRole role) {
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  const SixStateIdentity *identity = sixStateIdentity(role);
  if (!identity) {
    Serial.println("EC5 six-state rejected: invalid compiled role");
    return epdFinishOperation(started, false);
  }
  Serial.printf("EC5 six-state fixed role=%s candidate=0x%X; no retry\n",
                sixStateRoleName(role),
                static_cast<unsigned>(SIXSTATE_CANDIDATE));
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) {
    Serial.println("EC5 six-state rejected before panel I/O: PSRAM allocation failed");
    return epdFinishOperation(started, false);
  }
  const bool identityOk =
      sixStateBuildAndValidateFrame(role, frame) &&
      sixStateDtmMatches(frame, false, *identity) &&
      sixStateDtmMatches(frame, true, *identity);
  if (!identityOk) {
    Serial.println("EC5 six-state rejected before panel I/O: frozen identity mismatch");
    std::free(frame);
    return epdFinishOperation(started, false);
  }
  diagnosticReport.inputFrameFnv1a = identity->frameFnv1a;
  if (!epdPrepareCascade(EPD_SPI_DEFAULT_HZ)) {
    std::free(frame);
    return epdFinishOperation(started, false);
  }
  const uint32_t cs1Started = millis();
  diagnosticReport.cs1DtmFnv1a = epdStreamPackedFrameController(frame, false);
  diagnosticReport.cs1UploadMs = millis() - cs1Started;
  const uint32_t cs2Started = millis();
  diagnosticReport.cs2DtmFnv1a = epdStreamPackedFrameController(frame, true);
  diagnosticReport.cs2UploadMs = millis() - cs2Started;
  diagnosticReport.mappingApplied = true;
  std::free(frame);
  if (diagnosticReport.cs1DtmFnv1a != identity->dtmFnv1a ||
      diagnosticReport.cs2DtmFnv1a != identity->dtmFnv1a) {
    Serial.println("EC5 six-state aborted before PON: streamed DTM mismatch");
    epdStopHardwareSpi();
    epdHoldPanelPinsLow();
    return epdFinishOperation(started, false);
  }
  setActiveControllers(true, true);
  const bool ok = epdSecondSettingAndRefresh();
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  Serial.printf("EC5 six-state fixed refresh: %s\n", ok ? "PASS" : "FAILED");
  return epdFinishOperation(started, ok);
}

#endif  // MF1750_ENABLE_SIXSTATE_PROBE

#if defined(MF1750_L535_FRAME_PATH_BUILD)
static void epdWriteL535Payload(uint8_t command, const uint8_t *payload,
                                size_t length) {
  epdCommand(command);
  for (size_t index = 0; index < length; ++index) {
    epdData(payload[index]);
    if ((index & 0xFFU) == 0xFFU) yield();
  }
}

// L535 frame path: upload the audited L535 active runtime LUT after cascade
// init and before the DTM frame write. Sequence copied verbatim from the
// sealed PAL1 chain driver (pal1_cal_v5_driver.inc
// phApplyRuntimeLutGlobalConfig + phUploadRuntimeLutToController).
static bool epdLoadL535RuntimeLut() {
  setActiveControllers(true, true);
  static constexpr uint8_t kRuntimePsr[2] = {0x5F, 0xE9};
  static constexpr uint8_t kControllerTres[4] = {0x02, 0x00, 0x02, 0x58};
  epdWriteL535Payload(0x00, kRuntimePsr, sizeof(kRuntimePsr));
  epdWriteL535Payload(0x01, l535_variant::kPowerPayload,
                      l535_lut::active::kPowerPayloadBytes);
  if (!epdWaitIdle("L535 PWR")) return false;
  epdWriteL535Payload(0x30, l535_variant::kPllPayload,
                      l535_lut::active::kPllPayloadBytes);
  epdWriteL535Payload(0x61, kControllerTres, sizeof(kControllerTres));
  for (const bool second : {false, true}) {
    setActiveControllers(!second, second);
    static constexpr uint8_t kHiddenEnable[1] = {0x01};
    epdWriteL535Payload(0xE9, kHiddenEnable, sizeof(kHiddenEnable));
    if (!epdWaitIdle(second ? "L535 CS2 E9" : "L535 CS1 E9")) return false;
    epdWriteL535Payload(0x20, l535_variant::kR20Payload,
                        l535_lut::active::kTransmittedR20PrefixBytes);
    epdWriteL535Payload(0x21, l535_lut::active::kR21Payload,
                        l535_lut::active::kR21PayloadBytes);
  }
  setActiveControllers(true, true);
  return true;
}
#endif

bool epdDisplayFrameAtFrequency(const uint8_t *frame, size_t len, uint32_t spiHz) {
  const uint32_t started = epdBeginOperation(spiHz);
  if (!frame || len != EPD_FRAME_BYTES) {
    Serial.printf("Invalid EPD frame length: %u, expected %u\n",
                  static_cast<unsigned>(len), static_cast<unsigned>(EPD_FRAME_BYTES));
    return epdFinishOperation(started, false);
  }
  if (spiHz == 0) {
    Serial.println("Invalid EPD SPI frequency: 0 Hz");
    return epdFinishOperation(started, false);
  }
  size_t invalidPixel = 0;
  uint8_t invalidCode = 0;
  if (!epdValidateFrameColors(frame, len, &invalidPixel, &invalidCode)) {
    Serial.printf("Invalid EPD frame color at pixel %u: 0x%X\n",
                  static_cast<unsigned>(invalidPixel), invalidCode);
    return epdFinishOperation(started, false);
  }
  diagnosticReport.inputFrameFnv1a = fnv1a(frame, len);

  if (!epdPrepareCascade(spiHz)) {
    return epdFinishOperation(started, false);
  }
#if defined(MF1750_L535_FRAME_PATH_BUILD)
  if (!epdLoadL535RuntimeLut()) {
    Serial.println("EPD abort: L535 runtime LUT load failed");
    return epdFinishOperation(started, false);
  }
#endif
  Serial.printf("EPD full frame mapping: CS1 source_half=%u flip_x=%d flip_y=%d nibble_swap=%d; "
                "CS2 source_half=%u flip_x=%d flip_y=%d nibble_swap=%d\n",
                EPD_CS1_SOURCE_HALF, EPD_CS1_FLIP_X, EPD_CS1_FLIP_Y, EPD_CS1_NIBBLE_SWAP,
                EPD_CS2_SOURCE_HALF, EPD_CS2_FLIP_X, EPD_CS2_FLIP_Y, EPD_CS2_NIBBLE_SWAP);
  const uint32_t cs1Started = millis();
  diagnosticReport.cs1DtmFnv1a = epdStreamPackedFrameController(frame, false);
  diagnosticReport.cs1UploadMs = millis() - cs1Started;
  Serial.printf("EPD full frame CS1 upload done after %lu ms, DTM FNV-1a=%lu\n",
                static_cast<unsigned long>(diagnosticReport.cs1UploadMs),
                static_cast<unsigned long>(diagnosticReport.cs1DtmFnv1a));
  const uint32_t cs2Started = millis();
  diagnosticReport.cs2DtmFnv1a = epdStreamPackedFrameController(frame, true);
  diagnosticReport.cs2UploadMs = millis() - cs2Started;
  diagnosticReport.mappingApplied = true;
  Serial.printf("EPD full frame CS2 upload done after %lu ms, DTM FNV-1a=%lu\n",
                static_cast<unsigned long>(diagnosticReport.cs2UploadMs),
                static_cast<unsigned long>(diagnosticReport.cs2DtmFnv1a));
  setActiveControllers(true, true);
  const bool ok = epdSecondSettingAndRefresh();
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  Serial.printf("EPD full-frame cascade refresh: %s\n", ok ? "PASS" : "FAILED");
  return epdFinishOperation(started, ok);
}

bool epdDisplayFrame(const uint8_t *frame, size_t len) {
  return epdDisplayFrameAtFrequency(frame, len, EPD_SPI_DEFAULT_HZ);
}

bool epdDisplayHalfWhiteHalfBlack() {
  return epdDiagnosticDualCascadeSolid(0x11, 0x00, EPD_SPI_DEFAULT_HZ);
}

static bool epdDisplayCascadeBars(bool swappedNibbles, bool horizontal, uint32_t spiHz) {
  static constexpr uint8_t colors[] = {
      EPD_COLOR_WHITE,
      EPD_COLOR_BLACK,
      EPD_COLOR_RED,
      EPD_COLOR_YELLOW,
      EPD_COLOR_BLUE,
      EPD_COLOR_GREEN,
  };

  const uint32_t started = epdBeginOperation(spiHz);
  Serial.printf("EPD global cascade bars: 1024x600, swapped=%d, horizontal=%d, SPI=%lu Hz\n",
                swappedNibbles, horizontal, static_cast<unsigned long>(spiHz));
  if (!epdPrepareCascade(spiHz)) {
    return epdFinishOperation(started, false);
  }

  for (uint8_t controller = 0; controller < 2; ++controller) {
    setActiveControllers(controller == 0, controller == 1);
    epdCommand(DTM);
    const uint32_t uploadStarted = millis();
    uint32_t dtmHash = FNV1A_OFFSET_BASIS;
    const uint16_t globalXOffset = controller ? EPD_CONTROLLER_WIDTH : 0;
    for (uint16_t y = 0; y < EPD_HEIGHT; ++y) {
      for (uint16_t localX = 0; localX < EPD_CONTROLLER_WIDTH; localX += 2) {
        const uint16_t globalX0 = globalXOffset + localX;
        const uint16_t globalX1 = globalX0 + 1;
        const uint8_t index0 = horizontal
                                   ? (static_cast<uint32_t>(y) * 6) / EPD_HEIGHT
                                   : (static_cast<uint32_t>(globalX0) * 6) / EPD_WIDTH;
        const uint8_t index1 = horizontal
                                   ? (static_cast<uint32_t>(y) * 6) / EPD_HEIGHT
                                   : (static_cast<uint32_t>(globalX1) * 6) / EPD_WIDTH;
        const uint8_t c0 = colors[index0] & 0x0F;
        const uint8_t c1 = colors[index1] & 0x0F;
        const uint8_t value = swappedNibbles ? ((c1 << 4) | c0) : ((c0 << 4) | c1);
        dtmHash = fnv1aUpdate(dtmHash, value);
        epdData(value);
      }
      if ((y & 0x0FU) == 0x0FU) yield();
    }
    const uint32_t elapsed = millis() - uploadStarted;
    if (controller == 0) {
      diagnosticReport.cs1UploadMs = elapsed;
      diagnosticReport.cs1DtmFnv1a = dtmHash;
    } else {
      diagnosticReport.cs2UploadMs = elapsed;
      diagnosticReport.cs2DtmFnv1a = dtmHash;
    }
    Serial.printf("EPD global bars CS%u upload done after %lu ms, DTM FNV-1a=%lu\n",
                  controller + 1, static_cast<unsigned long>(elapsed),
                  static_cast<unsigned long>(dtmHash));
  }

  setActiveControllers(true, true);
  const bool ok = epdSecondSettingAndRefresh();
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  Serial.printf("EPD global cascade bars result: %s\n", ok ? "PASS" : "FAILED");
  return epdFinishOperation(started, ok);
}

static void epdDisplayBarsResolution(uint16_t width, uint16_t height, bool swappedNibbles, bool horizontal) {
  static constexpr uint8_t colors[] = {
      EPD_COLOR_WHITE,
      EPD_COLOR_BLACK,
      EPD_COLOR_RED,
      EPD_COLOR_YELLOW,
      EPD_COLOR_BLUE,
      EPD_COLOR_GREEN,
  };

  if (!epdInitResolution(width, height)) return;
  const size_t bytes = (static_cast<size_t>(width) * height) / 2;
  Serial.printf("EPD streaming 6-color bars custom resolution, %u x %u, bytes=%u, swapped=%d, horizontal=%d\n",
                width, height, static_cast<unsigned>(bytes), swappedNibbles, horizontal);
  setActiveControllers(true, false);
  epdCommand(DTM);
  for (uint16_t y = 0; y < height; ++y) {
    for (uint16_t x = 0; x < width; x += 2) {
      const uint8_t index0 = horizontal
                                 ? (static_cast<uint32_t>(y) * 6) / height
                                 : (static_cast<uint32_t>(x) * 6) / width;
      const uint8_t index1 = horizontal
                                 ? (static_cast<uint32_t>(y) * 6) / height
                                 : (static_cast<uint32_t>(x + 1) * 6) / width;
      const uint8_t c0 = colors[index0] & 0x0F;
      const uint8_t c1 = colors[index1] & 0x0F;
      epdData(swappedNibbles ? ((c1 << 4) | c0) : ((c0 << 4) | c1));
    }
  }
  Serial.println("EPD custom color bars upload done");
  setActiveControllers(true, false);
  epdSecondSettingAndRefresh();
  Serial.println("EPD custom color bars done");
}

bool epdDisplayColorBars() {
  return epdDisplayCascadeBars(false, false, EPD_SPI_DEFAULT_HZ);
}

void epdDisplayColorBars800x480() {
  epdDisplayBarsResolution(800, 480, false, false);
}

void epdDisplayColorBars512x600() {
  epdDisplayBarsResolution(512, 600, false, false);
}

bool epdDisplayColorBarsSwapped() {
  return epdDisplayCascadeBars(true, false, EPD_SPI_DEFAULT_HZ);
}

bool epdDisplayHorizontalBars() {
  return epdDisplayCascadeBars(false, true, EPD_SPI_DEFAULT_HZ);
}

bool epdDisplayColorBarsCs2Probe() {
  return epdDisplayCascadeBars(false, false, EPD_SPI_DEFAULT_HZ);
}

bool epdDiagnosticCascadeGlobalColorBars(uint32_t spiHz) {
  return epdDisplayCascadeBars(false, false, spiHz);
}

bool epdDiagnosticCascadeGlobalHorizontalBars(uint32_t spiHz) {
  return epdDisplayCascadeBars(false, true, spiHz);
}

void epdDisplayColorBars8bpp() {
  static constexpr uint8_t colors[] = {
      0x11,
      0x00,
      0x33,
      0x22,
      0x55,
      0x66,
  };

  if (!epdInitResolution(EPD_WIDTH, EPD_HEIGHT)) return;
  Serial.println("EPD streaming 6-color bars, 8bpp test");
  setActiveControllers(true, false);
  epdCommand(DTM);
  for (uint16_t y = 0; y < EPD_HEIGHT; ++y) {
    for (uint16_t x = 0; x < EPD_WIDTH; ++x) {
      epdData(colors[(static_cast<uint32_t>(x) * 6) / EPD_WIDTH]);
    }
  }
  Serial.println("EPD 8bpp color bars upload done");
  setActiveControllers(true, false);
  epdSecondSettingAndRefresh();
  Serial.println("EPD 8bpp color bars done");
}

bool epdClearWhite() {
  return epdDiagnosticDualCascadeSolid(0x11, 0x11, EPD_SPI_DEFAULT_HZ);
}

bool epdClearBlack() {
  return epdDiagnosticDualCascadeSolid(0x00, 0x00, EPD_SPI_DEFAULT_HZ);
}

void epdClearWhite800x480() {
  if (!epdInitResolution(800, 480)) return;
  Serial.println("EPD streaming white frame custom resolution, 800 x 480, bytes=192000");
  epdStreamSolidFrame(800, 480, 0x11);
  setActiveControllers(true, false);
  epdSecondSettingAndRefresh();
  Serial.println("EPD custom white frame done");
}

void epdClearBlack800x480() {
  if (!epdInitResolution(800, 480)) return;
  Serial.println("EPD streaming black frame custom resolution, 800 x 480, bytes=192000");
  epdStreamSolidFrame(800, 480, 0x00);
  setActiveControllers(true, false);
  epdSecondSettingAndRefresh();
  Serial.println("EPD custom black frame done");
}

void epdClearWhite512x600() {
  if (!epdInitResolution(512, 600)) return;
  Serial.println("EPD streaming white frame custom resolution, 512 x 600, bytes=153600");
  epdStreamSolidFrame(512, 600, 0x11);
  setActiveControllers(true, false);
  epdSecondSettingAndRefresh();
  Serial.println("EPD custom white frame done");
}

void epdClearBlack512x600() {
  if (!epdInitResolution(512, 600)) return;
  Serial.println("EPD streaming black frame custom resolution, 512 x 600, bytes=153600");
  epdStreamSolidFrame(512, 600, 0x00);
  setActiveControllers(true, false);
  epdSecondSettingAndRefresh();
  Serial.println("EPD custom black frame done");
}

#if MF1750_ENABLE_EIGHTCODE_ATLAS
#include "ec5_eightcode_atlas_driver.inc"
#endif

#if MF1750_ENABLE_COLOR_LAB
#include "ec5_color_lab_driver.inc"
#endif

#if MF1750_ENABLE_OTP_TRANSITION_MATRIX
#include "ec5_otp_transition_matrix_driver.inc"
#endif

#if MF1750_ENABLE_DITHER_COLOR_ATLAS
#include "ec5_dither_color_atlas_driver.inc"
#endif

#if MF1750_ENABLE_RUNTIME_LUT_EMPIRICAL_H3
#include "ec5_runtime_lut_empirical_h3_driver.inc"
#endif

#if MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY
#include "ec5_factory_otp_white_recovery_driver.inc"
#endif

// ===========================================================================
// Route A V4 fixture: the V3 normalization + white-recovery paths plus the
// compact atlas action.  The two V3 probe actions are dropped (saves two
// refreshes).  Every identity is validated before any panel I/O; no
// caller-controlled frame, coordinate, code, LUT, voltage, timing, retry, or
// recovery parameter is accepted.
#if defined(MF1750_PARTIAL_BLOCK_ATLAS_1E_V4_BUILD)

namespace {

constexpr const char *PBV4_FAILURE_ALLOCATION = "allocation";
constexpr const char *PBV4_FAILURE_ROLE = "role";
constexpr const char *PBV4_FAILURE_TUPLE_IDENTITY = "tuple_identity";
constexpr const char *PBV4_FAILURE_FRAME_IDENTITY = "frame_identity";
constexpr const char *PBV4_FAILURE_CASCADE_PREPARE = "cascade_prepare";
constexpr const char *PBV4_FAILURE_TUPLE_LOAD = "tuple_load";
constexpr const char *PBV4_FAILURE_STREAM_IDENTITY = "stream_identity";
constexpr const char *PBV4_FAILURE_REFRESH_SEQUENCE = "refresh_sequence";
constexpr const char *PBV4_FAILURE_NORMALIZE_STEP = "normalize_step";

EpdPartialAtlasV4StepReport pbv4StepReports[8];
size_t pbv4StepReportCount = 0;

bool pbv4DigestMatchesHex(const uint8_t digest[32], const char *expected) {
  if (!digest || !expected || std::strlen(expected) != 64) return false;
  static constexpr char kHex[] = "0123456789abcdef";
  for (size_t index = 0; index < 32; ++index) {
    if (expected[index * 2] != kHex[digest[index] >> 4] ||
        expected[index * 2 + 1] != kHex[digest[index] & 0x0F]) {
      return false;
    }
  }
  return true;
}

bool pbv4PayloadShaMatches(const uint8_t *payload, size_t length,
                           const char *expected, int32_t *errorCode) {
  if (!payload || length == 0 || !errorCode) return false;
  uint8_t digest[32] = {};
  *errorCode = mbedtls_sha256_ret(payload, length, digest, 0);
  return *errorCode == 0 && pbv4DigestMatchesHex(digest, expected);
}

bool pbv4ValidateTuples(int32_t *errorCode) {
  return pbv4PayloadShaMatches(l535_lut::active::kR20Payload, 535,
                               pbv4::kActiveR20Sha256, errorCode) &&
         pbv4PayloadShaMatches(pb_profile_1e::kR20Payload, 535,
                               pbv4::kProfile1ER20Sha256, errorCode) &&
         pbv4PayloadShaMatches(l535_lut::active::kPowerPayload, 6,
                               pbv4::kActivePwrSha256, errorCode) &&
         pbv4PayloadShaMatches(pb_profile_1e::kPowerPayload, 6,
                               pbv4::kActivePwrSha256, errorCode) &&
         pbv4PayloadShaMatches(l535_lut::active::kPllPayload, 1,
                               pbv4::kActivePllSha256, errorCode) &&
         pbv4PayloadShaMatches(pb_profile_1e::kPllPayload, 1,
                               pbv4::kActivePllSha256, errorCode) &&
         pbv4PayloadShaMatches(l535_lut::active::kR21Payload, 704,
                               pbv4::kActiveR21Sha256, errorCode);
}

bool pbv4LoadRuntimeTuple(const uint8_t *r20) {
  // Byte-identical command sequence to the sealed epdLoadL535RuntimeLut, with
  // the R20 payload selected per action.  PWR/PLL/R21 are the pinned active
  // payloads shared by every WMASK profile.
  setActiveControllers(true, true);
  static constexpr uint8_t kRuntimePsr[2] = {0x5F, 0xE9};
  static constexpr uint8_t kControllerTres[4] = {0x02, 0x00, 0x02, 0x58};
  epdWriteL535Payload(0x00, kRuntimePsr, sizeof(kRuntimePsr));
  epdWriteL535Payload(0x01, l535_lut::active::kPowerPayload, 6);
  if (!epdWaitIdle("V4 PWR")) return false;
  epdWriteL535Payload(0x30, l535_lut::active::kPllPayload, 1);
  epdWriteL535Payload(0x61, kControllerTres, sizeof(kControllerTres));
  for (const bool second : {false, true}) {
    setActiveControllers(!second, second);
    static constexpr uint8_t kHiddenEnable[1] = {0x01};
    epdWriteL535Payload(0xE9, kHiddenEnable, sizeof(kHiddenEnable));
    if (!epdWaitIdle(second ? "V4 CS2 E9" : "V4 CS1 E9")) return false;
    epdWriteL535Payload(0x20, r20, 535);
    epdWriteL535Payload(0x21, l535_lut::active::kR21Payload, 704);
  }
  setActiveControllers(true, true);
  return true;
}

uint32_t pbv4StreamUniformControllerDtm(bool secondController, uint8_t code,
                                        uint32_t hash) {
  const uint8_t pair = static_cast<uint8_t>((code << 4) | code);
  setActiveControllers(!secondController, secondController);
  epdCommand(DTM);
  epdStreamFillBytes(EPD_CONTROLLER_FRAME_BYTES, pair);
  for (uint32_t index = 0; index < EPD_CONTROLLER_FRAME_BYTES; ++index) {
    hash = fnv1aUpdate(hash, pair);
  }
  return hash;
}

bool pbv4RefreshFullFrame() {
  setActiveControllers(true, true);
  const bool ok = epdSecondSettingAndRefresh();
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  return ok;
}

bool pbv4OtpWhiteStep() {
  // Byte-identical to the sealed factory-OTP white fixture path: cascade init
  // (PSR 5F,69 selects the OTP LUT), full 0x11 frame to both controllers, then
  // the sealed refresh.
  if (!epdPrepareCascade(EPD_SPI_DEFAULT_HZ)) return false;
  const uint32_t cs1Fnv = pbv4StreamUniformControllerDtm(false, 0x01, FNV1A_OFFSET_BASIS);
  const uint32_t cs2Fnv = pbv4StreamUniformControllerDtm(true, 0x01, FNV1A_OFFSET_BASIS);
  diagnosticReport.cs1DtmFnv1a = cs1Fnv;
  diagnosticReport.cs2DtmFnv1a = cs2Fnv;
  diagnosticReport.mappingApplied = true;
  if (cs1Fnv != pbv4::kWhiteStreamFnv1a || cs2Fnv != pbv4::kWhiteStreamFnv1a) {
    return false;
  }
  return pbv4RefreshFullFrame();
}

bool pbv4ActiveUniformStep(uint8_t code) {
  if (!epdPrepareCascade(EPD_SPI_DEFAULT_HZ)) return false;
  if (!pbv4LoadRuntimeTuple(l535_lut::active::kR20Payload)) return false;
  const uint32_t expected =
      code == 0x00 ? pbv4::kBlackStreamFnv1a : pbv4::kWhiteStreamFnv1a;
  const uint32_t cs1Fnv = pbv4StreamUniformControllerDtm(false, code, FNV1A_OFFSET_BASIS);
  const uint32_t cs2Fnv = pbv4StreamUniformControllerDtm(true, code, FNV1A_OFFSET_BASIS);
  diagnosticReport.cs1DtmFnv1a = cs1Fnv;
  diagnosticReport.cs2DtmFnv1a = cs2Fnv;
  diagnosticReport.mappingApplied = true;
  if (cs1Fnv != expected || cs2Fnv != expected) return false;
  return pbv4RefreshFullFrame();
}

bool pbv4RunNormalize() {
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  diagnosticReport.freePsramBefore = ESP.getFreePsram();
  diagnosticReport.largestPsramBlockBefore =
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
  pbv4StepReportCount = 0;
  for (size_t index = 0; index < pbv4::kNormalizeStepCount; ++index) {
    pbv4StepReports[index] = EpdPartialAtlasV4StepReport{};
  }
  int32_t identityError = 0;
  if (!pbv4ValidateTuples(&identityError)) {
    return epdRejectBeforePanelIo(started, PBV4_FAILURE_TUPLE_IDENTITY,
                                  identityError);
  }
  for (size_t step = 0; step < pbv4::kNormalizeStepCount; ++step) {
    const pbv4::V4NormalizeStep &current = pbv4::kNormalizeSteps[step];
    const uint32_t stepStarted = millis();
    const bool ok = current.kind == pbv4::pbv4_step_kind::FACTORY_OTP_WHITE
                        ? pbv4OtpWhiteStep()
                        : pbv4ActiveUniformStep(current.code);
    pbv4StepReports[step].ponMs = diagnosticReport.ponWaitMs;
    pbv4StepReports[step].drfMs = diagnosticReport.drfWaitMs;
    pbv4StepReports[step].pofMs = diagnosticReport.pofWaitMs;
    pbv4StepReports[step].totalMs = millis() - stepStarted;
    pbv4StepReports[step].ok = ok;
    pbv4StepReportCount = step + 1;
    if (!ok) {
      epdRecordFailure(PBV4_FAILURE_NORMALIZE_STEP,
                       static_cast<int32_t>(step) + 1);
      return epdFinishOperation(started, false);
    }
  }
  return epdFinishOperation(started, true);
}

bool pbv4RunAtlas() {
  const uint32_t started = epdBeginOperation(EPD_SPI_DEFAULT_HZ);
  diagnosticReport.freePsramBefore = ESP.getFreePsram();
  diagnosticReport.largestPsramBlockBefore =
      heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
  int32_t identityError = 0;
  if (!pbv4ValidateTuples(&identityError)) {
    return epdRejectBeforePanelIo(started, PBV4_FAILURE_TUPLE_IDENTITY,
                                  identityError);
  }
  uint8_t *frame = static_cast<uint8_t *>(ps_malloc(EPD_FRAME_BYTES));
  if (!frame) {
    return epdRejectBeforePanelIo(started, PBV4_FAILURE_ALLOCATION);
  }
  const uint8_t backgroundPair = static_cast<uint8_t>(
      (pbv4::kBackgroundCode << 4) | pbv4::kBackgroundCode);
  std::memset(frame, backgroundPair, EPD_FRAME_BYTES);
  for (size_t index = 0; index < pbv4::kRoiCount; ++index) {
    const pbv4::AtlasRoi &roi = pbv4::kRois[index];
    const uint8_t pair = static_cast<uint8_t>((roi.code << 4) | roi.code);
    for (uint16_t y = roi.y; y < roi.y + roi.height; ++y) {
      std::memset(frame + static_cast<size_t>(y) * (EPD_WIDTH / 2) + roi.x / 2,
                  pair, roi.width / 2);
    }
  }
  const uint32_t frameFnv = fnv1a(frame, EPD_FRAME_BYTES);
  uint8_t digest[32] = {};
  const int shaResult = mbedtls_sha256_ret(frame, EPD_FRAME_BYTES, digest, 0);
  diagnosticReport.inputFrameFnv1a = frameFnv;
  if (shaResult != 0 || frameFnv != pbv4::kAtlasFrameFnv1a ||
      !pbv4DigestMatchesHex(digest, pbv4::kAtlasFrameSha256)) {
    std::free(frame);
    return epdRejectBeforePanelIo(started, PBV4_FAILURE_FRAME_IDENTITY,
                                  shaResult);
  }
  if (!epdPrepareCascade(EPD_SPI_DEFAULT_HZ)) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started, PBV4_FAILURE_CASCADE_PREPARE);
  }
  if (!pbv4LoadRuntimeTuple(pb_profile_1e::kR20Payload)) {
    std::free(frame);
    return epdFinishFailedOperationSafe(started, PBV4_FAILURE_TUPLE_LOAD);
  }
  const uint32_t cs1Started = millis();
  diagnosticReport.cs1DtmFnv1a = epdStreamPackedFrameController(frame, false);
  diagnosticReport.cs1UploadMs = millis() - cs1Started;
  const uint32_t cs2Started = millis();
  diagnosticReport.cs2DtmFnv1a = epdStreamPackedFrameController(frame, true);
  diagnosticReport.cs2UploadMs = millis() - cs2Started;
  diagnosticReport.mappingApplied = true;
  std::free(frame);
  if (diagnosticReport.cs1DtmFnv1a != pbv4::kAtlasCs1StreamFnv1a ||
      diagnosticReport.cs2DtmFnv1a != pbv4::kAtlasCs2StreamFnv1a) {
    return epdFinishFailedOperationSafe(started, PBV4_FAILURE_STREAM_IDENTITY);
  }
  const bool ok = pbv4RefreshFullFrame();
  if (!ok) epdRecordFailure(PBV4_FAILURE_REFRESH_SEQUENCE);
  return epdFinishOperation(started, ok);
}

}  // namespace

bool epdValidateCompiledPartialAtlasV4Fixtures() {
  int32_t errorCode = 0;
  return pbv4ValidateTuples(&errorCode) &&
         epdValidateCompiledFactoryOtpWhiteRecoveryFixture();
}

bool epdDisplayCompiledPartialAtlasV4(EpdPartialAtlasV4Role role) {
  switch (role) {
    case EpdPartialAtlasV4Role::Normalize:
      return pbv4RunNormalize();
    case EpdPartialAtlasV4Role::Atlas:
      return pbv4RunAtlas();
    case EpdPartialAtlasV4Role::WhiteRecovery:
      return epdDisplayCompiledFactoryOtpWhiteRecovery();
  }
  return false;
}

const EpdPartialAtlasV4StepReport *epdGetPartialAtlasV4StepReports(
    std::size_t *count) {
  if (count) *count = pbv4StepReportCount;
  return pbv4StepReports;
}

#endif  // MF1750_PARTIAL_BLOCK_ATLAS_1E_V4_BUILD
