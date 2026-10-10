#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>

#include "epd_config.h"
#include "epd_diagnostics.h"
#include "epd_driver.h"

#if EPD_ENABLE_TEST_PATTERN
#error "The N7 fixed sweep build must never refresh during boot"
#endif

WebServer server(80);

static constexpr const char *N7_FIRMWARE_BUILD_TAG =
    "MF1750_DRIVER_N7_SPI_SWEEP_R16_MAPHASH_JOBTRACE_BUSYEDGE_2026-08-07";
static constexpr uint32_t FNV1A_OFFSET_BASIS = 2166136261UL;
static constexpr uint32_t FNV1A_PRIME = 16777619UL;
static constexpr uint32_t MAP_ORIENT_V1_EXPECTED_FNV1A = 2634290221UL;
static constexpr uint32_t N7_SPI_SWEEP_1MHZ = 1000000UL;
static constexpr uint32_t N7_SPI_SWEEP_2MHZ = 2000000UL;
static constexpr uint32_t N7_SPI_SWEEP_4MHZ = 4000000UL;
static constexpr uint32_t N7_SPI_SWEEP_8MHZ = 8000000UL;
static constexpr uint32_t N7_SPI_SWEEP_10MHZ = 10000000UL;

enum class N7JobState : uint8_t {
  Idle,
  Queued,
  Running,
  Completed,
  Failed,
};

static uint8_t *frameBuffer = nullptr;
static size_t frameBufferSize = 0;
static uint32_t generatedFrameHash = 0;
static volatile bool n7Pending = false;
static uint32_t n7PendingSpiHz = 0;
static N7JobState n7JobState = N7JobState::Idle;
static uint32_t n7JobId = 0;
static uint32_t n7JobQueuedAtMs = 0;
static uint32_t n7JobStartedAtMs = 0;
static uint32_t n7JobFinishedAtMs = 0;
static bool n7JobResultKnown = false;
static bool n7JobResult = false;
static uint32_t n7JobFrameHash = 0;
static uint32_t n7PublishedOperationId = 0;
static String n7PublishedReportJson =
    "{\"schema_version\":2,\"valid\":false,\"error\":\"no_completed_job_report\"}";

static const char *n7JobStateName(N7JobState state) {
  switch (state) {
    case N7JobState::Idle:
      return "idle";
    case N7JobState::Queued:
      return "queued";
    case N7JobState::Running:
      return "running";
    case N7JobState::Completed:
      return "completed";
    case N7JobState::Failed:
      return "failed";
  }
  return "unknown";
}

static bool n7AllowedFrequency(uint32_t spiHz) {
  switch (spiHz) {
    case N7_SPI_SWEEP_1MHZ:
    case N7_SPI_SWEEP_2MHZ:
    case N7_SPI_SWEEP_4MHZ:
    case N7_SPI_SWEEP_8MHZ:
    case N7_SPI_SWEEP_10MHZ:
      return true;
    default:
      return false;
  }
}

static bool ensureFrameBuffer(size_t requiredSize) {
  if (frameBuffer && frameBufferSize >= requiredSize) return true;
  if (frameBuffer) {
    free(frameBuffer);
    frameBuffer = nullptr;
    frameBufferSize = 0;
  }
  frameBufferSize = requiredSize;
  Serial.printf("Allocating frame buffer: %u bytes\n",
                static_cast<unsigned>(frameBufferSize));
  Serial.printf("Free heap before allocation: %u bytes\n",
                static_cast<unsigned>(ESP.getFreeHeap()));
  Serial.printf("Free PSRAM before allocation: %u bytes\n",
                static_cast<unsigned>(ESP.getFreePsram()));
  if (!psramFound() || ESP.getFreePsram() < requiredSize) {
    Serial.println("Frame buffer allocation rejected: N7 requires PSRAM");
    frameBufferSize = 0;
    return false;
  }
  frameBuffer = static_cast<uint8_t *>(ps_malloc(frameBufferSize));
  Serial.println(frameBuffer ? "Frame buffer allocation OK"
                             : "Frame buffer allocation FAILED");
  return frameBuffer != nullptr;
}

static void setPixel(uint8_t *buffer, uint16_t x, uint16_t y, uint8_t color) {
  if (x >= EPD_WIDTH || y >= EPD_HEIGHT) return;
  const size_t pixel = static_cast<size_t>(y) * EPD_WIDTH + x;
  const size_t byteIndex = pixel >> 1;
  color &= 0x0F;
  if (pixel & 1) {
    buffer[byteIndex] = (buffer[byteIndex] & 0xF0) | color;
  } else {
    buffer[byteIndex] = (color << 4) | (buffer[byteIndex] & 0x0F);
  }
}

static void drawLine(uint8_t *buffer, int x0, int y0, int x1, int y1,
                     uint8_t color) {
  const int dx = abs(x1 - x0);
  const int sx = x0 < x1 ? 1 : -1;
  const int dy = -abs(y1 - y0);
  const int sy = y0 < y1 ? 1 : -1;
  int error = dx + dy;
  while (true) {
    setPixel(buffer, x0, y0, color);
    if (x0 == x1 && y0 == y1) break;
    const int twiceError = 2 * error;
    if (twiceError >= dy) {
      error += dy;
      x0 += sx;
    }
    if (twiceError <= dx) {
      error += dx;
      y0 += sy;
    }
  }
}

static void drawRect(uint8_t *buffer, uint16_t x, uint16_t y, uint16_t width,
                     uint16_t height, uint8_t color) {
  drawLine(buffer, x, y, x + width - 1, y, color);
  drawLine(buffer, x, y + height - 1, x + width - 1, y + height - 1, color);
  drawLine(buffer, x, y, x, y + height - 1, color);
  drawLine(buffer, x + width - 1, y, x + width - 1, y + height - 1, color);
}

static void fillRect(uint8_t *buffer, uint16_t x, uint16_t y, uint16_t width,
                     uint16_t height, uint8_t color) {
  const uint16_t xEnd =
      static_cast<uint32_t>(x) + width < EPD_WIDTH ? x + width : EPD_WIDTH;
  const uint16_t yEnd =
      static_cast<uint32_t>(y) + height < EPD_HEIGHT ? y + height : EPD_HEIGHT;
  for (uint16_t pixelY = y; pixelY < yEnd; ++pixelY) {
    for (uint16_t pixelX = x; pixelX < xEnd; ++pixelX) {
      setPixel(buffer, pixelX, pixelY, color);
    }
  }
}

static uint32_t fnv1a(const uint8_t *data, size_t length) {
  uint32_t hash = FNV1A_OFFSET_BASIS;
  for (size_t index = 0; index < length; ++index) {
    hash ^= data[index];
    hash *= FNV1A_PRIME;
  }
  return hash;
}

// Exact duplicate of the accepted MAP_ORIENT_V1 generator.  It is kept in the
// isolated diagnostic entry point so the default RC2G compilation unit and
// binary remain byte-for-byte unchanged.
static bool generateMapOrientV1() {
  if (!ensureFrameBuffer(EPD_FRAME_BYTES)) return false;
  memset(frameBuffer, 0x11, EPD_FRAME_BYTES);

  static constexpr uint8_t edgeColors[] = {
      EPD_COLOR_BLACK, EPD_COLOR_RED, EPD_COLOR_YELLOW, EPD_COLOR_BLUE,
      EPD_COLOR_GREEN,
  };
  for (uint16_t inset = 0; inset < 20; ++inset) {
    drawRect(frameBuffer, inset, inset, EPD_WIDTH - 2 * inset,
             EPD_HEIGHT - 2 * inset, edgeColors[inset / 4]);
  }

  struct CornerBlock {
    uint16_t localX;
    uint16_t y;
    uint8_t color;
    uint8_t ticks;
  };
  static constexpr CornerBlock cornerBlocks[] = {
      {32, 32, EPD_COLOR_RED, 1},
      {400, 32, EPD_COLOR_YELLOW, 2},
      {32, 488, EPD_COLOR_BLUE, 3},
      {400, 488, EPD_COLOR_GREEN, 4},
  };
  for (uint16_t halfBase : {uint16_t(0), EPD_CONTROLLER_WIDTH}) {
    for (const CornerBlock &block : cornerBlocks) {
      fillRect(frameBuffer, halfBase + block.localX, block.y, 80, 80,
               block.color);
      for (uint8_t tick = 0; tick < block.ticks; ++tick) {
        fillRect(frameBuffer, halfBase + block.localX + 8 + 16 * tick,
                 block.y + 32, 8, 16, EPD_COLOR_BLACK);
      }
    }
  }

  fillRect(frameBuffer, 176, 200, 160, 80, EPD_COLOR_RED);
  fillRect(frameBuffer, 248, 216, 16, 48, EPD_COLOR_BLACK);
  fillRect(frameBuffer, EPD_CONTROLLER_WIDTH + 176, 200, 160, 80,
           EPD_COLOR_BLUE);
  fillRect(frameBuffer, EPD_CONTROLLER_WIDTH + 224, 216, 16, 48,
           EPD_COLOR_WHITE);
  fillRect(frameBuffer, EPD_CONTROLLER_WIDTH + 272, 216, 16, 48,
           EPD_COLOR_WHITE);

  for (uint16_t halfBase : {uint16_t(0), EPD_CONTROLLER_WIDTH}) {
    fillRect(frameBuffer, halfBase + 156, 320, 200, 60, EPD_COLOR_RED);
    fillRect(frameBuffer, halfBase + 160, 324, 32, 52, EPD_COLOR_BLACK);
    fillRect(frameBuffer, halfBase + 320, 324, 32, 52, EPD_COLOR_WHITE);
    for (uint16_t y = 324; y < 376; ++y) {
      for (uint16_t x = 192; x < 320; ++x) {
        setPixel(frameBuffer, halfBase + x, y,
                 (x & 1U) ? EPD_COLOR_WHITE : EPD_COLOR_BLACK);
      }
    }

    fillRect(frameBuffer, halfBase + 156, 396, 200, 60, EPD_COLOR_BLUE);
    fillRect(frameBuffer, halfBase + 160, 400, 32, 52, EPD_COLOR_WHITE);
    fillRect(frameBuffer, halfBase + 320, 400, 32, 52, EPD_COLOR_BLACK);
    for (uint16_t y = 400; y < 452; ++y) {
      for (uint16_t x = 192; x < 320; ++x) {
        setPixel(frameBuffer, halfBase + x, y,
                 (x & 1U) ? EPD_COLOR_BLACK : EPD_COLOR_WHITE);
      }
    }
  }

  static constexpr uint8_t seamColors[] = {
      EPD_COLOR_BLACK, EPD_COLOR_RED,   EPD_COLOR_BLUE,  EPD_COLOR_YELLOW,
      EPD_COLOR_GREEN, EPD_COLOR_WHITE, EPD_COLOR_BLUE,  EPD_COLOR_GREEN,
      EPD_COLOR_RED,   EPD_COLOR_YELLOW,
  };
  for (uint8_t index = 0; index < 10; ++index) {
    fillRect(frameBuffer, 492 + 4 * index, 20, 4, 560, seamColors[index]);
  }
  fillRect(frameBuffer, 440, 169, 144, 8, EPD_COLOR_BLACK);
  fillRect(frameBuffer, 456, 409, 112, 12, EPD_COLOR_RED);

  generatedFrameHash = fnv1a(frameBuffer, EPD_FRAME_BYTES);
  uint32_t pixelCounts[7] = {};
  bool countsOk = true;
  for (size_t index = 0; index < EPD_FRAME_BYTES; ++index) {
    const uint8_t high = (frameBuffer[index] >> 4) & 0x0F;
    const uint8_t low = frameBuffer[index] & 0x0F;
    if (high < 7) {
      ++pixelCounts[high];
    } else {
      countsOk = false;
    }
    if (low < 7) {
      ++pixelCounts[low];
    } else {
      countsOk = false;
    }
  }
  static constexpr uint32_t expectedCounts[] = {
      39536, 425808, 29280, 47072, 0, 44192, 28512,
  };
  for (uint8_t color = 0; color < 7; ++color) {
    if (pixelCounts[color] != expectedCounts[color]) countsOk = false;
  }
  Serial.printf("MAP_ORIENT_V1 frame FNV-1a: %lu (expected %lu), counts=%s\n",
                static_cast<unsigned long>(generatedFrameHash),
                static_cast<unsigned long>(MAP_ORIENT_V1_EXPECTED_FNV1A),
                countsOk ? "PASS" : "FAILED");
  if (generatedFrameHash != MAP_ORIENT_V1_EXPECTED_FNV1A || !countsOk) {
    Serial.println("MAP_ORIENT_V1 generation mismatch; refresh rejected");
    return false;
  }
  return true;
}

static bool drawAndDisplayMapOrientV1(uint32_t spiHz) {
  if (!generateMapOrientV1()) {
    return epdDisplayFrameAtFrequency(nullptr, 0, spiHz);
  }
  n7JobFrameHash = generatedFrameHash;
  return epdDisplayFrameAtFrequency(frameBuffer, EPD_FRAME_BYTES, spiHz);
}

static bool n7JobActive() {
  return n7JobState == N7JobState::Queued ||
         n7JobState == N7JobState::Running;
}

static bool queueN7Job(uint32_t spiHz) {
  if (!n7AllowedFrequency(spiHz) || n7JobActive() || n7Pending) return false;
  ++n7JobId;
  if (n7JobId == 0) ++n7JobId;
  n7JobQueuedAtMs = millis();
  n7JobStartedAtMs = 0;
  n7JobFinishedAtMs = 0;
  n7JobResultKnown = false;
  n7JobResult = false;
  n7JobFrameHash = MAP_ORIENT_V1_EXPECTED_FNV1A;
  n7JobState = N7JobState::Queued;
  n7PendingSpiHz = spiHz;
  n7Pending = true;
  return true;
}

static String n7JobStatusJson() {
  const String result =
      n7JobResultKnown ? (n7JobResult ? "true" : "false") : "null";
  const char *action = n7JobId == 0 ? "none" : "map_orient_v1_sweep";
  return String("{\"job_id\":") + String(n7JobId) +
         ",\"action\":\"" + action + "\",\"state\":\"" +
         n7JobStateName(n7JobState) + "\",\"result\":" + result +
         ",\"queued_at_ms\":" + String(n7JobQueuedAtMs) +
         ",\"started_at_ms\":" + String(n7JobStartedAtMs) +
         ",\"finished_at_ms\":" + String(n7JobFinishedAtMs) +
         ",\"frame_fnv1a\":" + String(n7JobFrameHash) + "}";
}

static String n7BuildCompletedJobReportJson(const String &completedDriverReport,
                                            uint32_t operationId) {
  String driverReport = completedDriverReport;
  if (!driverReport.startsWith("{")) {
    return "{\"schema_version\":2,\"valid\":false,\"error\":\"invalid_driver_report\"}";
  }
  driverReport.remove(0, 1);
  return String("{\"schema_version\":2,\"firmware_build_tag\":\"") +
         N7_FIRMWARE_BUILD_TAG + "\",\"driver_api_version\":\"" +
         EPD_DRIVER_API_VERSION + "\",\"job_id\":" + String(n7JobId) +
         ",\"job_action\":\"map_orient_v1_sweep\",\"job_state\":\"" +
         n7JobStateName(n7JobState) + "\",\"job_result\":" +
         String(n7JobResult ? "true" : "false") +
         ",\"job_operation_id\":" + String(operationId) +
         ",\"job_queued_at_ms\":" + String(n7JobQueuedAtMs) +
         ",\"job_started_at_ms\":" + String(n7JobStartedAtMs) +
         ",\"job_finished_at_ms\":" + String(n7JobFinishedAtMs) + "," +
         driverReport;
}

static bool requestHasPayloadOrArguments() {
  if (server.args() != 0 || server.hasArg("plain")) return true;
  if (server.hasHeader("Transfer-Encoding")) return true;
  if (!server.hasHeader("Content-Length")) return false;
  const String length = server.header("Content-Length");
  return length.length() == 0 || length != "0";
}

static void queueN7SpiSweepAndRespond(uint32_t spiHz) {
  if (requestHasPayloadOrArguments() || !n7AllowedFrequency(spiHz)) {
    server.send(400, "application/json",
                "{\"ok\":false,\"error\":\"n7_sweep_arguments_forbidden\"}");
    return;
  }
  if (!queueN7Job(spiHz)) {
    server.send(409, "application/json",
                String("{\"ok\":false,\"error\":\"epd_action_pending\",\"current\":") +
                    n7JobStatusJson() + "}");
    return;
  }
  server.send(202, "application/json",
              String("{\"ok\":true,\"job\":") + n7JobStatusJson() + "}");
}

static void startWiFi() {
  if (strlen(WIFI_STA_SSID) > 0) {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_STA_SSID, WIFI_STA_PASSWORD);
    Serial.printf("Connecting to WiFi SSID: %s\n", WIFI_STA_SSID);
    const uint32_t started = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - started < 15000) {
      delay(250);
      Serial.print('.');
    }
    Serial.println();
    if (WiFi.status() == WL_CONNECTED) {
      Serial.printf("WiFi STA IP: %s\n", WiFi.localIP().toString().c_str());
      return;
    }
  }
  WiFi.mode(WIFI_AP);
  WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASSWORD);
  Serial.printf("WiFi AP SSID: %s IP: %s\n", WIFI_AP_SSID,
                WiFi.softAPIP().toString().c_str());
}

static void startN7Server() {
  static const char *requestHeaders[] = {
      "Content-Length", "Transfer-Encoding",
  };
  server.collectHeaders(requestHeaders, 2);
  server.on("/", HTTP_GET, []() {
    server.send(200, "text/plain; charset=utf-8",
                "MF-1750 N7 fixed SPI sweep diagnostic build\n"
                "No browser upload or arbitrary-frequency route is available.\n");
  });
  server.on("/api/version", HTTP_GET, []() {
    server.send(200, "text/plain; charset=utf-8",
                String(N7_FIRMWARE_BUILD_TAG) + "\nPanel: " + String(EPD_WIDTH) +
                    "x" + String(EPD_HEIGHT) + "\nDriver API: " +
                    String(EPD_DRIVER_API_VERSION) + "\nFrame bytes: " +
                    String(EPD_FRAME_BYTES) + "\nRefresh SPI Hz: " +
                    String(EPD_SPI_DEFAULT_HZ) +
                    "\nN7 Sweep SPI Hz: 1000000,2000000,4000000,8000000,10000000" +
                    "\nCS1 Mapping: " + String(EPD_CS1_SOURCE_HALF) + "," +
                    String(EPD_CS1_FLIP_X ? 1 : 0) + "," +
                    String(EPD_CS1_FLIP_Y ? 1 : 0) + "," +
                    String(EPD_CS1_NIBBLE_SWAP ? 1 : 0) +
                    "\nCS2 Mapping: " + String(EPD_CS2_SOURCE_HALF) + "," +
                    String(EPD_CS2_FLIP_X ? 1 : 0) + "," +
                    String(EPD_CS2_FLIP_Y ? 1 : 0) + "," +
                    String(EPD_CS2_NIBBLE_SWAP ? 1 : 0) +
                    "\nPSRAM bytes: " + String(ESP.getPsramSize()) +
                    "\nFree PSRAM: " + String(ESP.getFreePsram()));
  });
  server.on("/api/diagnostic/status", HTTP_GET, []() {
    server.send(200, "application/json",
                String("{\"busy\":") + String(epdReadBusy()) +
                    ",\"rst\":" + String(digitalRead(EPD_PIN_RST)) +
                    ",\"cs\":" + String(digitalRead(EPD_PIN_CS)) +
                    ",\"cs2\":" + String(digitalRead(EPD_PIN_CS2)) + "}");
  });
  server.on("/api/job", HTTP_GET, []() {
    server.send(200, "application/json", n7JobStatusJson());
  });
  server.on("/api/diagnostic/report", HTTP_GET, []() {
    server.send(200, "application/json", n7PublishedReportJson);
  });
  server.on("/api/diagnostic/map-orient-v1-sweep-1mhz", HTTP_POST, []() {
    queueN7SpiSweepAndRespond(N7_SPI_SWEEP_1MHZ);
  });
  server.on("/api/diagnostic/map-orient-v1-sweep-2mhz", HTTP_POST, []() {
    queueN7SpiSweepAndRespond(N7_SPI_SWEEP_2MHZ);
  });
  server.on("/api/diagnostic/map-orient-v1-sweep-4mhz", HTTP_POST, []() {
    queueN7SpiSweepAndRespond(N7_SPI_SWEEP_4MHZ);
  });
  server.on("/api/diagnostic/map-orient-v1-sweep-8mhz", HTTP_POST, []() {
    queueN7SpiSweepAndRespond(N7_SPI_SWEEP_8MHZ);
  });
  server.on("/api/diagnostic/map-orient-v1-sweep-10mhz", HTTP_POST, []() {
    queueN7SpiSweepAndRespond(N7_SPI_SWEEP_10MHZ);
  });
  server.onNotFound([]() {
    server.send(404, "application/json",
                "{\"ok\":false,\"error\":\"n7_route_not_allowlisted\"}");
  });
  server.begin();
}

void setup() {
  Serial.begin(115200);
  delay(2000);
  Serial.println("\nESP32-S3 MF-1750 N7 sweep server booting");
  Serial.printf("Firmware: %s\n", N7_FIRMWARE_BUILD_TAG);
  Serial.printf("Panel: %u x %u, frame bytes: %u\n", EPD_WIDTH, EPD_HEIGHT,
                static_cast<unsigned>(EPD_FRAME_BYTES));
  Serial.printf("Controller: %u x %u, frame bytes per controller: %u\n",
                EPD_CONTROLLER_WIDTH, EPD_HEIGHT,
                static_cast<unsigned>(EPD_CONTROLLER_FRAME_BYTES));
  Serial.printf("PSRAM: total=%u, free=%u bytes\n",
                static_cast<unsigned>(ESP.getPsramSize()),
                static_cast<unsigned>(ESP.getFreePsram()));
  Serial.printf("Pins BUSY=%d RST=%d CS=%d CS2=%d DC=%d SCK=%d SDI=%d BS=%d SWC=%d\n",
                EPD_PIN_BUSY, EPD_PIN_RST, EPD_PIN_CS, EPD_PIN_CS2, EPD_PIN_DC,
                EPD_PIN_SCK, EPD_PIN_MOSI, EPD_PIN_BS, EPD_PIN_SWC);
  epdBegin();
  startWiFi();
  startN7Server();
  Serial.println("N7 fixed SPI sweep HTTP server started");
}

void loop() {
  server.handleClient();
  if (n7Pending) {
    n7Pending = false;
    n7JobState = N7JobState::Running;
    n7JobStartedAtMs = millis();
    const uint32_t operationIdBefore = epdGetLastOperationReport().operationId;
    const uint32_t spiHz = n7PendingSpiHz;
    bool result = false;
    Serial.printf("Running EPD job %lu action 1 (map_orient_v1_sweep)\n",
                  static_cast<unsigned long>(n7JobId));
    if (n7AllowedFrequency(spiHz)) {
      result = drawAndDisplayMapOrientV1(spiHz);
    } else {
      Serial.println("N7 job rejected: frequency is outside the fixed allowlist");
    }

    bool freshCompletedReport = false;
    uint32_t completedOperationId = 0;
    String completedDriverReport;
    const EpdOperationReport &report = epdGetLastOperationReport();
    freshCompletedReport = report.valid && !report.running &&
                           report.operationId > operationIdBefore &&
                           report.operationId > n7PublishedOperationId &&
                           report.sequenceOk == result;
    if (freshCompletedReport) {
      completedOperationId = report.operationId;
      completedDriverReport = epdDiagnosticReportJson();
      if (!completedDriverReport.startsWith("{\"operation_id\":")) {
        freshCompletedReport = false;
        result = false;
        Serial.println("N7 job rejected: completed report serialization failed");
      }
    } else {
      result = false;
      Serial.printf("EPD job %lu rejected: missing fresh completed driver report\n",
                    static_cast<unsigned long>(n7JobId));
    }

    n7JobResultKnown = true;
    n7JobResult = result;
    n7JobFinishedAtMs = millis();
    n7JobState = result ? N7JobState::Completed : N7JobState::Failed;
    if (freshCompletedReport) {
      n7PublishedReportJson = n7BuildCompletedJobReportJson(
          completedDriverReport, completedOperationId);
      n7PublishedOperationId = completedOperationId;
    }
    n7PendingSpiHz = 0;
    Serial.printf("EPD job %lu finished: state=%s result_known=1 result=%d\n",
                  static_cast<unsigned long>(n7JobId),
                  n7JobStateName(n7JobState), result ? 1 : 0);
  }
  delay(2);
}
