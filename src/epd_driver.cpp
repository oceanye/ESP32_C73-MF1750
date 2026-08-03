#include "epd_driver.h"

#include <SPI.h>
#include <cstdio>
#include <cstring>

#include "epd_config.h"

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

static constexpr uint32_t FNV1A_OFFSET_BASIS = 2166136261UL;
static constexpr uint32_t FNV1A_PRIME = 16777619UL;

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

bool epdWaitIdle(const char *stage, uint32_t timeoutMs = 60000) {
  // The supplied sample waits for BUSY_N to become HIGH. The panel datasheet
  // text says the opposite, but reset/refresh measurements on this panel show
  // LOW while busy and HIGH while idle. Keep the empirical/sample-code polarity
  // and log whether a real busy interval was observed.
  delay(5);
  const uint32_t started = millis();
  bool sawBusy = digitalRead(EPD_PIN_BUSY) != EPD_BUSY_IDLE_LEVEL;
  Serial.printf("EPD wait idle: %s, BUSY=%d, idle=%d\n",
                stage, digitalRead(EPD_PIN_BUSY), EPD_BUSY_IDLE_LEVEL);
  uint32_t lastLog = started;
  while (digitalRead(EPD_PIN_BUSY) != EPD_BUSY_IDLE_LEVEL) {
    sawBusy = true;
    if (millis() - started > timeoutMs) {
      diagnosticReport.lastWaitMs = millis() - started;
      copyStage(diagnosticReport.lastWaitStage, sizeof(diagnosticReport.lastWaitStage), stage);
      if (diagnosticReport.running && !diagnosticReport.waitTimedOut) {
        diagnosticReport.waitTimedOut = true;
        copyStage(diagnosticReport.timeoutStage, sizeof(diagnosticReport.timeoutStage), stage);
      }
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
  diagnosticReport.lastWaitMs = millis() - started;
  copyStage(diagnosticReport.lastWaitStage, sizeof(diagnosticReport.lastWaitStage), stage);
  return true;
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
  epdCommand(PSR);
  epdData(0x4F);
  epdData(0x6E);
  const bool psrIdle = epdWaitIdle("post-display PSR");
  delay(1000);
  // Rev A1 leaves the ESP32 powered from USB when J2-1 is removed.  Hold every
  // panel-facing digital output LOW so the unpowered panel cannot be back-fed;
  // DC is a separate pin in 4-wire mode and must not be left HIGH.
  epdStopHardwareSpi();
  epdHoldPanelPinsLow();
  return psrIdle;
}

bool epdSecondSettingAndRefresh() {
  Serial.println("EPD power on");
  epdCommand(PON);
  if (!epdWaitIdle("PON")) {
    Serial.println("EPD abort: PON timeout; requesting power off");
    epdCommand(POF);
    epdData(0x00);
    epdWaitIdle("POF after PON timeout", 30000);
    epdStopHardwareSpi();
    epdHoldPanelPinsLow();
    return false;
  }

  epdCommand(BTST2);
  epdData(0x6F);
  epdData(0x1F);
  epdData(0x17);
  epdData(0x49);

  Serial.println("EPD display refresh");
  epdCommand(DRF);
  epdData(0x00);
  if (!epdWaitIdle("DRF")) {
    Serial.println("EPD abort: DRF timeout; requesting power off");
    epdCommand(POF);
    epdData(0x00);
    epdWaitIdle("POF after DRF timeout", 30000);
    epdStopHardwareSpi();
    epdHoldPanelPinsLow();
    return false;
  }

  Serial.println("EPD power off");
  epdCommand(POF);
  epdData(0x00);
  if (!epdWaitIdle("POF")) {
    Serial.println("EPD abort: POF timeout");
    epdStopHardwareSpi();
    epdHoldPanelPinsLow();
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
  String json = "{\"valid\":" + String(diagnosticReport.valid ? "true" : "false") +
                ",\"running\":" + String(diagnosticReport.running ? "true" : "false") +
                ",\"sequence_ok\":" + String(diagnosticReport.sequenceOk ? "true" : "false") +
                ",\"wait_timeout\":" + String(diagnosticReport.waitTimedOut ? "true" : "false") +
                ",\"mapping_applied\":" + String(diagnosticReport.mappingApplied ? "true" : "false") +
                ",\"spi_hz\":" + String(diagnosticReport.spiHz) +
                ",\"input_fnv1a\":" + String(diagnosticReport.inputFrameFnv1a) +
                ",\"cs1_dtm_fnv1a\":" + String(diagnosticReport.cs1DtmFnv1a) +
                ",\"cs2_dtm_fnv1a\":" + String(diagnosticReport.cs2DtmFnv1a) +
                ",\"total_ms\":" + String(diagnosticReport.totalMs) +
                ",\"cs1_upload_ms\":" + String(diagnosticReport.cs1UploadMs) +
                ",\"cs2_upload_ms\":" + String(diagnosticReport.cs2UploadMs) +
                ",\"last_wait_ms\":" + String(diagnosticReport.lastWaitMs) +
                ",\"last_wait_stage\":\"" + String(diagnosticReport.lastWaitStage) +
                "\",\"timeout_stage\":\"" + String(diagnosticReport.timeoutStage) +
                "\",\"mapping\":{" +
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
  if (tresWidth == 0 || tresHeight == 0 || streamBytes == 0 ||
      streamBytes > EPD_FRAME_BYTES) {
    Serial.println("EPD diagnostic rejected: invalid TRES or byte count");
    return false;
  }

  Serial.println("EPD DIAGNOSTIC: use one test per cold panel power cycle");
  Serial.printf("EPD diagnostic solid: TRES=%ux%u, bytes=%u, fill=0x%02X, SPI=%lu Hz\n",
                tresWidth, tresHeight, static_cast<unsigned>(streamBytes), fillByte,
                static_cast<unsigned long>(spiHz));
  epdSetSpiFrequency(spiHz);
  if (!epdInitResolution(tresWidth, tresHeight)) {
    epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
    epdDiagnosticReleasePins();
    return false;
  }

  setActiveControllers(true, false);
  epdCommand(DTM);
  const uint32_t uploadStarted = millis();
  epdStreamFillBytes(streamBytes, fillByte);
  Serial.printf("EPD diagnostic upload done after %lu ms\n",
                static_cast<unsigned long>(millis() - uploadStarted));

  setActiveControllers(true, false);
  const bool ok = epdSecondSettingAndRefresh();
  Serial.printf("EPD diagnostic result: %s\n", ok ? "PASS_SEQUENCE" : "FAILED_SEQUENCE");
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  return ok;
}

bool epdDiagnosticCs1ColorBars(uint32_t spiHz) {
  diagnosticReport = EpdOperationReport{};
  diagnosticReport.valid = true;
  diagnosticReport.running = true;
  diagnosticReport.spiHz = spiHz;
  const uint32_t diagnosticStarted = millis();

  Serial.println("EPD TRUE CS1-ONLY DIAGNOSTIC: cold panel power cycle required");
  Serial.println("Only CS1 is selected for reset follow-up, init, DTM, PON, DRF and POF");
  epdSetSpiFrequency(spiHz);
  if (!epdInitResolutionSelected(EPD_CONTROLLER_WIDTH, EPD_HEIGHT, true, false)) {
    diagnosticReport.totalMs = millis() - diagnosticStarted;
    diagnosticReport.running = false;
    epdStopHardwareSpi();
    epdHoldPanelPinsLow();
    return false;
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
  diagnosticReport.sequenceOk = ok;
  diagnosticReport.totalMs = millis() - diagnosticStarted;
  diagnosticReport.running = false;
  Serial.printf("EPD true CS1-only result: %s\n", ok ? "PASS_SEQUENCE" : "FAILED_SEQUENCE");
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  return ok;
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
  if (EPD_PIN_CS2 < 0) {
    Serial.println("EPD dual-CS diagnostic rejected: CS2 pin disabled");
    return false;
  }

  diagnosticReport = EpdOperationReport{};
  diagnosticReport.valid = true;
  diagnosticReport.running = true;
  diagnosticReport.spiHz = spiHz;
  const uint32_t diagnosticStarted = millis();

  Serial.println("EPD DUAL-CS DIAGNOSTIC: use one test per cold panel power cycle");
  Serial.printf("EPD dual solid: each TRES=%ux%u, each bytes=%u, CS1 fill=0x%02X, CS2 fill=0x%02X, SPI=%lu Hz, cascade_trial=%d\n",
                EPD_CONTROLLER_WIDTH, EPD_HEIGHT,
                static_cast<unsigned>(EPD_CONTROLLER_FRAME_BYTES),
                firstFillByte, secondFillByte,
                static_cast<unsigned long>(spiHz), enableCascade ? 1 : 0);
  epdSetSpiFrequency(spiHz);
  if (!epdInitResolution(EPD_CONTROLLER_WIDTH, EPD_HEIGHT)) {
    epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
    epdDiagnosticReleasePins();
    diagnosticReport.totalMs = millis() - diagnosticStarted;
    diagnosticReport.running = false;
    return false;
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
  diagnosticReport.sequenceOk = ok;
  diagnosticReport.totalMs = millis() - diagnosticStarted;
  diagnosticReport.running = false;
  Serial.printf("EPD dual-CS diagnostic result: %s\n",
                ok ? "PASS_SEQUENCE" : "FAILED_SEQUENCE");
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  return ok;
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
  if (EPD_PIN_CS2 < 0) {
    Serial.println("EPD dual cascade bars rejected: CS2 pin disabled");
    return false;
  }

  diagnosticReport = EpdOperationReport{};
  diagnosticReport.valid = true;
  diagnosticReport.running = true;
  diagnosticReport.spiHz = spiHz;
  const uint32_t diagnosticStarted = millis();
  Serial.println("EPD DUAL CASCADE SIX-COLOR BARS: cold panel power cycle required");
  epdSetSpiFrequency(spiHz);
  if (!epdInitResolutionSelected(EPD_CONTROLLER_WIDTH, EPD_HEIGHT, true, true)) {
    diagnosticReport.totalMs = millis() - diagnosticStarted;
    diagnosticReport.running = false;
    epdStopHardwareSpi();
    epdHoldPanelPinsLow();
    return false;
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
  diagnosticReport.sequenceOk = ok;
  diagnosticReport.totalMs = millis() - diagnosticStarted;
  diagnosticReport.running = false;
  Serial.printf("EPD dual cascade six-color result: %s\n",
                ok ? "PASS_SEQUENCE" : "FAILED_SEQUENCE");
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  return ok;
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

bool epdDisplayFrameAtFrequency(const uint8_t *frame, size_t len, uint32_t spiHz) {
  diagnosticReport = EpdOperationReport{};
  diagnosticReport.valid = true;
  diagnosticReport.running = true;
  diagnosticReport.spiHz = spiHz;
  diagnosticReport.mappingApplied = true;
  const uint32_t started = millis();
  if (!frame || len != EPD_FRAME_BYTES) {
    Serial.printf("Invalid EPD frame length: %u, expected %u\n",
                  static_cast<unsigned>(len), static_cast<unsigned>(EPD_FRAME_BYTES));
    diagnosticReport.totalMs = millis() - started;
    diagnosticReport.running = false;
    return false;
  }
  if (spiHz == 0) {
    Serial.println("Invalid EPD SPI frequency: 0 Hz");
    diagnosticReport.totalMs = millis() - started;
    diagnosticReport.running = false;
    return false;
  }
  diagnosticReport.inputFrameFnv1a = fnv1a(frame, len);

  if (!epdPrepareCascade(spiHz)) {
    diagnosticReport.totalMs = millis() - started;
    diagnosticReport.running = false;
    return false;
  }
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
  Serial.printf("EPD full frame CS2 upload done after %lu ms, DTM FNV-1a=%lu\n",
                static_cast<unsigned long>(diagnosticReport.cs2UploadMs),
                static_cast<unsigned long>(diagnosticReport.cs2DtmFnv1a));
  setActiveControllers(true, true);
  const bool ok = epdSecondSettingAndRefresh();
  diagnosticReport.sequenceOk = ok;
  diagnosticReport.totalMs = millis() - started;
  diagnosticReport.running = false;
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  Serial.printf("EPD full-frame cascade refresh: %s\n", ok ? "PASS" : "FAILED");
  return ok;
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

  diagnosticReport = EpdOperationReport{};
  diagnosticReport.valid = true;
  diagnosticReport.running = true;
  diagnosticReport.spiHz = spiHz;
  const uint32_t started = millis();
  Serial.printf("EPD global cascade bars: 1024x600, swapped=%d, horizontal=%d, SPI=%lu Hz\n",
                swappedNibbles, horizontal, static_cast<unsigned long>(spiHz));
  if (!epdPrepareCascade(spiHz)) {
    diagnosticReport.totalMs = millis() - started;
    diagnosticReport.running = false;
    return false;
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
  diagnosticReport.sequenceOk = ok;
  diagnosticReport.totalMs = millis() - started;
  diagnosticReport.running = false;
  epdSetSpiFrequency(EPD_SPI_DEFAULT_HZ);
  Serial.printf("EPD global cascade bars result: %s\n", ok ? "PASS" : "FAILED");
  return ok;
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
