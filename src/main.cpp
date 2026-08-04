#include <Arduino.h>
#include <SPI.h>
#include <WiFi.h>
#include <WebServer.h>

#include "epd_driver.h"
#include "epd_diagnostics.h"
#include "epd_config.h"

WebServer server(80);

static constexpr const char *FW_BUILD_TAG =
    "MF1750_DRIVER_RC2C_R16_CCSET_MAPHASH_COLORGUARD_JOBTRACE_PSRFIX_2026-08-04";
static constexpr uint32_t FNV1A_OFFSET_BASIS = 2166136261UL;
static constexpr uint32_t FNV1A_PRIME = 16777619UL;
static constexpr uint32_t MAP_ORIENT_V1_EXPECTED_FNV1A = 2634290221UL;
static uint8_t *frameBuffer = nullptr;
static size_t frameBufferSize = 0;
static size_t frameUploadReceived = 0;
static uint32_t frameUploadHash = FNV1A_OFFSET_BASIS;
static bool frameUploadAccepted = false;
static bool frameUploadComplete = false;
static String frameUploadError;
static size_t frameUploadInvalidPixel = static_cast<size_t>(-1);
static uint8_t frameUploadInvalidCode = 0;
enum class PendingEpdAction : uint8_t {
  None,
  UploadedFrame,
  Test,
  Black,
  White,
  Bars,
  BarsSwap,
  BarsHorizontal,
  Bars8bpp,
  BarsCs2Probe,
  Bars800x480,
  White800x480,
  Black800x480,
  Bars512x600,
  White512x600,
  Black512x600,
  HalvesWhiteBlack,
  DiagWhite512Slow,
  DiagBlack512Slow,
  DiagWhite800Slow,
  DiagWhite1024ShortSlow,
  DiagWhite512LongSlow,
  DiagWhite1024FullSlow,
  DiagCs1BarsIsolated,
  DiagCascadeWhiteBlackSlow,
  DiagCascadeBlackWhiteSlow,
  DiagCascadeDualBarsSlow,
  DiagCascadeGlobalBarsSlow,
  DiagCascadeGlobalHorizontalBarsSlow,
  DiagMapOrientV1Slow,
  DiagDualWhiteBlackSlow,
  DiagDualBlackWhiteSlow,
  DiagDualWhiteWhiteSlow,
};
static volatile PendingEpdAction pendingEpdAction = PendingEpdAction::None;

enum class EpdJobState : uint8_t {
  Idle,
  Queued,
  Running,
  Completed,
  Failed,
};

static EpdJobState epdJobState = EpdJobState::Idle;
static uint32_t epdJobId = 0;
static const char *epdJobName = "none";
static uint32_t epdJobQueuedAtMs = 0;
static uint32_t epdJobStartedAtMs = 0;
static uint32_t epdJobFinishedAtMs = 0;
static bool epdJobResultKnown = false;
static bool epdJobResult = false;
static uint32_t epdJobFrameHash = 0;
// Published as one immutable String only after a result-bearing job has a
// fresh, completed driver report. Later Test/REV diagnostics may update the
// driver's live report, but cannot relabel or mutate this job snapshot.
static uint32_t epdPublishedOperationId = 0;
static String epdPublishedReportJson =
    "{\"schema_version\":2,\"valid\":false,\"error\":\"no_completed_job_report\"}";
static uint32_t generatedFrameHash = 0;

static bool ensureFrameBuffer(size_t requiredSize);
static bool queueEpdJob(PendingEpdAction action, const char *name, uint32_t frameHash = 0);
static String epdJobStatusJson();
static String epdDiagnosticReportWithJobJson();
static String epdBuildCompletedJobReportJson(const String &driverReport,
                                             uint32_t operationId);

static constexpr char INDEX_HTML[] PROGMEM = R"HTML(
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>ESP32-S3 eInk Uploader</title>
  <style>
    :root { color-scheme: light; --ink:#17211b; --paper:#f3efe1; --line:#c8b98e; --accent:#d45b2c; }
    body { margin:0; min-height:100vh; font-family: Georgia, "Noto Serif SC", serif; color:var(--ink);
      background: radial-gradient(circle at 15% 10%, #fff8d8 0 18rem, transparent 18.5rem),
                  linear-gradient(135deg, #eee4c8, #faf7ec 55%, #d8e0d0); }
    main { width:min(920px, calc(100% - 32px)); margin:0 auto; padding:42px 0; }
    h1 { font-size:clamp(2rem, 7vw, 5rem); line-height:.92; margin:0 0 18px; letter-spacing:-.05em; }
    .panel { border:2px solid var(--ink); background:rgba(255,252,238,.76); box-shadow:10px 10px 0 rgba(23,33,27,.18);
      padding:22px; display:grid; gap:18px; }
    .controls { display:flex; flex-wrap:wrap; gap:12px; align-items:center; }
    button, input::file-selector-button { border:2px solid var(--ink); background:var(--accent); color:white; padding:10px 14px;
      font-weight:700; cursor:pointer; }
    input, label { font-size:1rem; }
    canvas { max-width:100%; border:2px solid var(--line); background:white; image-rendering:pixelated; }
    code { background:#fff4c6; padding:2px 5px; }
    #status { font-weight:700; min-height:1.4em; }
  </style>
</head>
<body>
<main>
  <h1>ESP32-S3<br>eInk Upload</h1>
  <section class="panel">
    <p>选择图片后会在浏览器端缩放到 <code id="size"></code>，量化为 6 色 E Ink 调色板，再发送到 ESP32 刷新墨水屏。</p>
    <div class="controls">
      <input id="file" type="file" accept="image/*">
      <label><input id="crop" type="checkbox" checked> 居中裁剪填满</label>
      <button id="send" disabled>上传并刷新</button>
      <button id="test">MAP_ORIENT_V1 驱动验收</button>
    </div>
    <canvas id="preview"></canvas>
    <div id="status"></div>
  </section>
</main>
<script>
const W = %EPD_WIDTH%, H = %EPD_HEIGHT%;
const UPLOAD_W = %UPLOAD_WIDTH%;
const canvas = document.getElementById('preview');
const ctx = canvas.getContext('2d');
const statusEl = document.getElementById('status');
const fileEl = document.getElementById('file');
const sendEl = document.getElementById('send');
const cropEl = document.getElementById('crop');
document.getElementById('size').textContent = `${UPLOAD_W} x ${H}`;
canvas.width = UPLOAD_W; canvas.height = H;
let packed = null;
let loadedImage = null;

function setStatus(text) { statusEl.textContent = text; }
function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

async function readJsonResponse(resp) {
  const text = await resp.text();
  let data;
  try { data = JSON.parse(text); }
  catch (_) { throw new Error(`HTTP ${resp.status}: ${text}`); }
  if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
  return data;
}

async function waitForJob(jobId) {
  setStatus(`任务 ${jobId} 已排队，等待屏幕刷新完成...`);
  while (true) {
    await sleep(1000);
    const job = await readJsonResponse(await fetch('/api/job'));
    if (job.job_id !== jobId) throw new Error(`任务编号已变化：${job.job_id}`);
    if (job.state === 'completed') {
      setStatus(`任务 ${jobId} 已完成，序列结果：${job.result === null ? '未提供' : job.result}`);
      return;
    }
    if (job.state === 'failed') throw new Error(`任务 ${jobId} 刷新失败`);
  }
}

const palette = [
  { code: 0x0, rgb: [0, 0, 0] },
  { code: 0x1, rgb: [255, 255, 255] },
  { code: 0x2, rgb: [245, 205, 0] },
  { code: 0x3, rgb: [210, 35, 35] },
  { code: 0x5, rgb: [45, 85, 200] },
  { code: 0x6, rgb: [40, 150, 80] },
];

function nearestColor(r, g, b) {
  let best = palette[0], bestDist = Infinity;
  for (const item of palette) {
    const dr = r - item.rgb[0], dg = g - item.rgb[1], db = b - item.rgb[2];
    const dist = dr * dr + dg * dg + db * db;
    if (dist < bestDist) {
      bestDist = dist;
      best = item;
    }
  }
  return best.code;
}

function quantizeAndPack() {
  const img = ctx.getImageData(0, 0, UPLOAD_W, H);
  const out = new Uint8Array(Math.ceil(UPLOAD_W * H / 2));
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < UPLOAD_W; x++) {
      const pixel = y * UPLOAD_W + x;
      const rgba = pixel * 4;
      const code = nearestColor(img.data[rgba], img.data[rgba + 1], img.data[rgba + 2]) & 0x0f;
      const byteIndex = pixel >> 1;
      if (pixel & 1) out[byteIndex] = (out[byteIndex] & 0xf0) | code;
      else out[byteIndex] = (code << 4) | (out[byteIndex] & 0x0f);
    }
  }
  return out;
}

function renderLoadedImage() {
  const img = loadedImage;
  if (!img) return;
    ctx.fillStyle = 'white';
    ctx.fillRect(0, 0, UPLOAD_W, H);
    if (cropEl.checked) {
      const srcRatio = img.width / img.height;
      const dstRatio = UPLOAD_W / H;
      let sx = 0, sy = 0, sw = img.width, sh = img.height;
      if (srcRatio > dstRatio) {
        sw = Math.round(img.height * dstRatio);
        sx = Math.floor((img.width - sw) / 2);
      } else {
        sh = Math.round(img.width / dstRatio);
        sy = Math.floor((img.height - sh) / 2);
      }
      ctx.drawImage(img, sx, sy, sw, sh, 0, 0, UPLOAD_W, H);
    } else {
      const scale = Math.min(UPLOAD_W / img.width, H / img.height);
      const dw = Math.round(img.width * scale);
      const dh = Math.round(img.height * scale);
      ctx.drawImage(img, Math.floor((UPLOAD_W - dw) / 2), Math.floor((H - dh) / 2), dw, dh);
    }
    packed = quantizeAndPack();
    sendEl.disabled = false;
    setStatus(`已生成 ${packed.length} 字节 6-color raw frame`);
}

fileEl.addEventListener('change', async () => {
  const file = fileEl.files[0];
  if (!file) return;
  const img = new Image();
  img.onload = () => {
    loadedImage = img;
    renderLoadedImage();
  };
  img.src = URL.createObjectURL(file);
});

cropEl.addEventListener('change', renderLoadedImage);

sendEl.addEventListener('click', async () => {
  if (!packed) return;
  sendEl.disabled = true;
  try {
    setStatus('上传 307200 字节中...');
    const data = await readJsonResponse(await fetch('/api/frame', {
      method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: packed
    }));
    await waitForJob(data.job_id);
  } catch (error) {
    setStatus(`失败：${error.message}`);
  } finally {
    sendEl.disabled = false;
  }
});

document.getElementById('test').addEventListener('click', async () => {
  const button = document.getElementById('test');
  button.disabled = true;
  try {
    setStatus('请求 MAP_ORIENT_V1 低速驱动验收...');
    const data = await readJsonResponse(await fetch('/api/diagnostic/map-orient-v1-slow', { method: 'POST' }));
    await waitForJob(data.job.job_id);
  } catch (error) {
    setStatus(`失败：${error.message}`);
  } finally {
    button.disabled = false;
  }
});
</script>
</body>
</html>
)HTML";

static String indexPage() {
  String html(FPSTR(INDEX_HTML));
  html.replace("%EPD_WIDTH%", String(EPD_WIDTH));
  html.replace("%EPD_HEIGHT%", String(EPD_HEIGHT));
  html.replace("%UPLOAD_WIDTH%", String(EPD_WIDTH));
  return html;
}

static void setPixel(uint8_t *buffer, uint16_t x, uint16_t y, uint8_t color) {
  if (x >= EPD_WIDTH || y >= EPD_HEIGHT) return;
  const size_t pixel = static_cast<size_t>(y) * EPD_WIDTH + x;
  const size_t byteIndex = pixel >> 1;
  color &= 0x0F;
  if (pixel & 1) buffer[byteIndex] = (buffer[byteIndex] & 0xF0) | color;
  else buffer[byteIndex] = (color << 4) | (buffer[byteIndex] & 0x0F);
}

static void drawLine(uint8_t *buffer, int x0, int y0, int x1, int y1, uint8_t color) {
  const int dx = abs(x1 - x0);
  const int sx = x0 < x1 ? 1 : -1;
  const int dy = -abs(y1 - y0);
  const int sy = y0 < y1 ? 1 : -1;
  int err = dx + dy;
  while (true) {
    setPixel(buffer, x0, y0, color);
    if (x0 == x1 && y0 == y1) break;
    const int e2 = 2 * err;
    if (e2 >= dy) {
      err += dy;
      x0 += sx;
    }
    if (e2 <= dx) {
      err += dx;
      y0 += sy;
    }
  }
}

static void drawRect(uint8_t *buffer, uint16_t x, uint16_t y, uint16_t w, uint16_t h, uint8_t color) {
  drawLine(buffer, x, y, x + w - 1, y, color);
  drawLine(buffer, x, y + h - 1, x + w - 1, y + h - 1, color);
  drawLine(buffer, x, y, x, y + h - 1, color);
  drawLine(buffer, x + w - 1, y, x + w - 1, y + h - 1, color);
}

static void fillRect(uint8_t *buffer,
                     uint16_t x,
                     uint16_t y,
                     uint16_t w,
                     uint16_t h,
                     uint8_t color) {
  const uint16_t xEnd = static_cast<uint32_t>(x) + w < EPD_WIDTH ? x + w : EPD_WIDTH;
  const uint16_t yEnd = static_cast<uint32_t>(y) + h < EPD_HEIGHT ? y + h : EPD_HEIGHT;
  for (uint16_t py = y; py < yEnd; ++py) {
    for (uint16_t px = x; px < xEnd; ++px) setPixel(buffer, px, py, color);
  }
}

static uint32_t fnv1a(const uint8_t *data, size_t len) {
  uint32_t hash = FNV1A_OFFSET_BASIS;
  for (size_t i = 0; i < len; ++i) {
    hash ^= data[i];
    hash *= FNV1A_PRIME;
  }
  return hash;
}

// MAP_ORIENT_V1 is intentionally asymmetric and deterministic. One image identifies:
// - which physical half receives CS1/CS2;
// - horizontal or vertical mirroring;
// - whether the two halves meet correctly at x=511/512;
// - adjacent-pixel nibble phase in two magnifiable probe regions.
// Pixel rectangles use half-open coordinates [x0,x1), [y0,y1).
static bool generateMapOrientV1() {
  if (!ensureFrameBuffer(EPD_FRAME_BYTES)) return false;
  memset(frameBuffer, 0x11, EPD_FRAME_BYTES);

  static constexpr uint8_t edgeColors[] = {
      EPD_COLOR_BLACK, EPD_COLOR_RED, EPD_COLOR_YELLOW, EPD_COLOR_BLUE, EPD_COLOR_GREEN,
  };
  for (uint16_t inset = 0; inset < 20; ++inset) {
    drawRect(frameBuffer, inset, inset, EPD_WIDTH - 2 * inset, EPD_HEIGHT - 2 * inset,
             edgeColors[inset / 4]);
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
      fillRect(frameBuffer, halfBase + block.localX, block.y, 80, 80, block.color);
      for (uint8_t tick = 0; tick < block.ticks; ++tick) {
        fillRect(frameBuffer, halfBase + block.localX + 8 + 16 * tick,
                 block.y + 32, 8, 16, EPD_COLOR_BLACK);
      }
    }
  }

  // Source-half identity: one black stroke on red for CS1, two white strokes
  // on blue for CS2. Geometry still identifies the halves if colors are poor.
  fillRect(frameBuffer, 176, 200, 160, 80, EPD_COLOR_RED);
  fillRect(frameBuffer, 248, 216, 16, 48, EPD_COLOR_BLACK);
  fillRect(frameBuffer, EPD_CONTROLLER_WIDTH + 176, 200, 160, 80, EPD_COLOR_BLUE);
  fillRect(frameBuffer, EPD_CONTROLLER_WIDTH + 224, 216, 16, 48, EPD_COLOR_WHITE);
  fillRect(frameBuffer, EPD_CONTROLLER_WIDTH + 272, 216, 16, 48, EPD_COLOR_WHITE);

  for (uint16_t halfBase : {uint16_t(0), EPD_CONTROLLER_WIDTH}) {
    // Upper 0x01 probe: black anchor, alternating black/white, white anchor.
    fillRect(frameBuffer, halfBase + 156, 320, 200, 60, EPD_COLOR_RED);
    fillRect(frameBuffer, halfBase + 160, 324, 32, 52, EPD_COLOR_BLACK);
    fillRect(frameBuffer, halfBase + 320, 324, 32, 52, EPD_COLOR_WHITE);
    for (uint16_t y = 324; y < 376; ++y) {
      for (uint16_t u = 192; u < 320; ++u) {
        setPixel(frameBuffer, halfBase + u, y, (u & 1U) ? EPD_COLOR_WHITE : EPD_COLOR_BLACK);
      }
    }

    // Lower 0x10 probe: white anchor, alternating white/black, black anchor.
    fillRect(frameBuffer, halfBase + 156, 396, 200, 60, EPD_COLOR_BLUE);
    fillRect(frameBuffer, halfBase + 160, 400, 32, 52, EPD_COLOR_WHITE);
    fillRect(frameBuffer, halfBase + 320, 400, 32, 52, EPD_COLOR_BLACK);
    for (uint16_t y = 400; y < 452; ++y) {
      for (uint16_t u = 192; u < 320; ++u) {
        setPixel(frameBuffer, halfBase + u, y, (u & 1U) ? EPD_COLOR_BLACK : EPD_COLOR_WHITE);
      }
    }
  }

  static constexpr uint8_t seamColors[] = {
      EPD_COLOR_BLACK, EPD_COLOR_RED, EPD_COLOR_BLUE, EPD_COLOR_YELLOW, EPD_COLOR_GREEN,
      EPD_COLOR_WHITE, EPD_COLOR_BLUE, EPD_COLOR_GREEN, EPD_COLOR_RED, EPD_COLOR_YELLOW,
  };
  for (uint8_t index = 0; index < 10; ++index) {
    fillRect(frameBuffer, 492 + 4 * index, 20, 4, 560, seamColors[index]);
  }
  fillRect(frameBuffer, 440, 169, 144, 8, EPD_COLOR_BLACK);
  fillRect(frameBuffer, 456, 409, 112, 12, EPD_COLOR_RED);

  generatedFrameHash = fnv1a(frameBuffer, EPD_FRAME_BYTES);
  uint32_t pixelCounts[7] = {};
  bool countsOk = true;
  for (size_t i = 0; i < EPD_FRAME_BYTES; ++i) {
    const uint8_t high = (frameBuffer[i] >> 4) & 0x0F;
    const uint8_t low = frameBuffer[i] & 0x0F;
    if (high < 7) ++pixelCounts[high];
    else countsOk = false;
    if (low < 7) ++pixelCounts[low];
    else countsOk = false;
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
    // Allocate and complete a rejected driver operation too, so every
    // result-bearing job has a fresh report even if host-frame generation
    // fails before panel I/O.
    return epdDisplayFrameAtFrequency(nullptr, 0, spiHz);
  }
  epdJobFrameHash = generatedFrameHash;
  return epdDisplayFrameAtFrequency(frameBuffer, EPD_FRAME_BYTES, spiHz);
}

static void setControllerPixel(uint8_t *buffer, uint16_t x, uint16_t y, uint8_t color) {
  if (x >= EPD_CONTROLLER_WIDTH || y >= EPD_HEIGHT) return;
  const size_t pixel = static_cast<size_t>(y) * EPD_CONTROLLER_WIDTH + x;
  const size_t byteIndex = pixel >> 1;
  color &= 0x0F;
  if (pixel & 1) buffer[byteIndex] = (buffer[byteIndex] & 0xF0) | color;
  else buffer[byteIndex] = (color << 4) | (buffer[byteIndex] & 0x0F);
}

static void drawControllerLine(uint8_t *buffer, int x0, int y0, int x1, int y1, uint8_t color) {
  const int dx = abs(x1 - x0);
  const int sx = x0 < x1 ? 1 : -1;
  const int dy = -abs(y1 - y0);
  const int sy = y0 < y1 ? 1 : -1;
  int err = dx + dy;
  while (true) {
    setControllerPixel(buffer, x0, y0, color);
    if (x0 == x1 && y0 == y1) break;
    const int e2 = 2 * err;
    if (e2 >= dy) {
      err += dy;
      x0 += sx;
    }
    if (e2 <= dx) {
      err += dx;
      y0 += sy;
    }
  }
}

static void drawControllerRect(uint8_t *buffer, uint16_t x, uint16_t y, uint16_t w, uint16_t h, uint8_t color) {
  drawControllerLine(buffer, x, y, x + w - 1, y, color);
  drawControllerLine(buffer, x, y + h - 1, x + w - 1, y + h - 1, color);
  drawControllerLine(buffer, x, y, x, y + h - 1, color);
  drawControllerLine(buffer, x + w - 1, y, x + w - 1, y + h - 1, color);
}

static void drawTestPattern() {
  if (!ensureFrameBuffer(EPD_FRAME_BYTES)) {
    Serial.println("Full-frame buffer allocation failed; fallback to streaming color bars");
    epdDisplayColorBars();
    return;
  }
  memset(frameBuffer, 0x11, EPD_FRAME_BYTES);
  drawRect(frameBuffer, 0, 0, EPD_WIDTH, EPD_HEIGHT, EPD_COLOR_BLACK);
  drawRect(frameBuffer, 24, 24, EPD_WIDTH - 48, EPD_HEIGHT - 48, EPD_COLOR_RED);
  drawLine(frameBuffer, 0, 0, EPD_WIDTH - 1, EPD_HEIGHT - 1, EPD_COLOR_BLUE);
  drawLine(frameBuffer, EPD_WIDTH - 1, 0, 0, EPD_HEIGHT - 1, EPD_COLOR_GREEN);
  for (uint16_t x = 64; x < EPD_WIDTH - 64; x += 64) {
    drawLine(frameBuffer, x, 96, x, 180, EPD_COLOR_YELLOW);
  }
  for (uint16_t y = 240; y < EPD_HEIGHT - 80; y += 32) {
    drawLine(frameBuffer, 80, y, EPD_WIDTH - 80, y, EPD_COLOR_BLACK);
  }
  epdDisplayFrame(frameBuffer, EPD_FRAME_BYTES);
}

static bool ensureFrameBuffer(size_t requiredSize) {
  if (frameBuffer && frameBufferSize >= requiredSize) return true;
  if (frameBuffer) {
    free(frameBuffer);
    frameBuffer = nullptr;
    frameBufferSize = 0;
  }
  frameBufferSize = requiredSize;
  Serial.printf("Allocating frame buffer: %u bytes\n", static_cast<unsigned>(frameBufferSize));
  Serial.printf("Free heap before allocation: %u bytes\n", static_cast<unsigned>(ESP.getFreeHeap()));
  Serial.printf("Free PSRAM before allocation: %u bytes\n", static_cast<unsigned>(ESP.getFreePsram()));
  if (!psramFound() || ESP.getFreePsram() < requiredSize) {
    Serial.println("Frame buffer allocation rejected: full-frame web adapter requires PSRAM");
    frameBufferSize = 0;
    return false;
  }
  frameBuffer = static_cast<uint8_t *>(ps_malloc(frameBufferSize));
  if (frameBuffer) {
    Serial.println("Frame buffer allocation OK");
  } else {
    Serial.println("Frame buffer allocation FAILED");
  }
  return frameBuffer != nullptr;
}

static const char *epdJobStateName(EpdJobState state) {
  switch (state) {
    case EpdJobState::Idle: return "idle";
    case EpdJobState::Queued: return "queued";
    case EpdJobState::Running: return "running";
    case EpdJobState::Completed: return "completed";
    case EpdJobState::Failed: return "failed";
  }
  return "unknown";
}

static bool epdJobActive() {
  return epdJobState == EpdJobState::Queued || epdJobState == EpdJobState::Running;
}

static bool queueEpdJob(PendingEpdAction action, const char *name, uint32_t frameHash) {
  if (action == PendingEpdAction::None || epdJobActive() ||
      pendingEpdAction != PendingEpdAction::None) {
    return false;
  }
  ++epdJobId;
  if (epdJobId == 0) ++epdJobId;
  epdJobName = name;
  epdJobQueuedAtMs = millis();
  epdJobStartedAtMs = 0;
  epdJobFinishedAtMs = 0;
  epdJobResultKnown = false;
  epdJobResult = false;
  epdJobFrameHash = frameHash;
  epdJobState = EpdJobState::Queued;
  pendingEpdAction = action;
  return true;
}

static String epdJobStatusJson() {
  const String result = epdJobResultKnown ? (epdJobResult ? "true" : "false") : "null";
  return String("{\"job_id\":") + String(epdJobId) +
         ",\"action\":\"" + epdJobName +
         "\",\"state\":\"" + epdJobStateName(epdJobState) +
         "\",\"result\":" + result +
         ",\"queued_at_ms\":" + String(epdJobQueuedAtMs) +
         ",\"started_at_ms\":" + String(epdJobStartedAtMs) +
         ",\"finished_at_ms\":" + String(epdJobFinishedAtMs) +
         ",\"frame_fnv1a\":" + String(epdJobFrameHash) + "}";
}

static String epdDiagnosticReportWithJobJson() {
  return epdPublishedReportJson;
}

static String epdBuildCompletedJobReportJson(const String &completedDriverReport,
                                             uint32_t operationId) {
  String driverReport = completedDriverReport;
  if (!driverReport.startsWith("{")) {
    return "{\"schema_version\":2,\"valid\":false,\"error\":\"invalid_driver_report\"}";
  }
  driverReport.remove(0, 1);
  return String("{\"schema_version\":2,\"firmware_build_tag\":\"") + FW_BUILD_TAG +
         "\",\"driver_api_version\":\"" + EPD_DRIVER_API_VERSION +
         "\",\"job_id\":" + String(epdJobId) +
         ",\"job_action\":\"" + epdJobName +
         "\",\"job_state\":\"" + epdJobStateName(epdJobState) +
         "\",\"job_result\":" + String(epdJobResult ? "true" : "false") +
         ",\"job_operation_id\":" + String(operationId) +
         ",\"job_queued_at_ms\":" + String(epdJobQueuedAtMs) +
         ",\"job_started_at_ms\":" + String(epdJobStartedAtMs) +
         ",\"job_finished_at_ms\":" + String(epdJobFinishedAtMs) +
         "," + driverReport;
}

static void queueEpdJobAndRespond(PendingEpdAction action, const char *name) {
  if (!queueEpdJob(action, name)) {
    server.send(409, "application/json",
                String("{\"ok\":false,\"error\":\"epd_action_pending\",\"current\":") +
                    epdJobStatusJson() + "}");
    return;
  }
  server.send(202, "application/json",
              String("{\"ok\":true,\"job\":") + epdJobStatusJson() + "}");
}

static bool isRawFrameRequest() {
  String contentType = server.header("Content-Type");
  contentType.toLowerCase();
  return contentType.startsWith("application/octet-stream");
}

static void handleFrameUploadRaw() {
  HTTPRaw &raw = server.raw();
  if (raw.status == RAW_START) {
    frameUploadReceived = 0;
    frameUploadHash = FNV1A_OFFSET_BASIS;
    frameUploadComplete = false;
    frameUploadError = "";
    frameUploadInvalidPixel = static_cast<size_t>(-1);
    frameUploadInvalidCode = 0;
    if (server.clientContentLength() != static_cast<int>(EPD_FRAME_BYTES)) {
      frameUploadAccepted = false;
      frameUploadError = "frame_size_mismatch";
      return;
    }
    const bool actionPending = epdJobActive() ||
                               pendingEpdAction != PendingEpdAction::None;
    frameUploadAccepted = !actionPending && ensureFrameBuffer(EPD_FRAME_BYTES);
    if (!frameUploadAccepted) {
      frameUploadError = actionPending ? "epd_action_pending"
                                       : "frame_buffer_allocation_failed";
    }
    return;
  }

  if (raw.status == RAW_WRITE) {
    const size_t offset = raw.totalSize - raw.currentSize;
    if (!frameUploadAccepted) return;
    if (offset + raw.currentSize > EPD_FRAME_BYTES) {
      frameUploadAccepted = false;
      frameUploadError = "frame_too_large";
      return;
    }
    for (size_t i = 0; i < raw.currentSize; ++i) {
      const uint8_t packed = raw.buf[i];
      const uint8_t high = (packed >> 4) & 0x0F;
      const uint8_t low = packed & 0x0F;
      if (!epdIsSupportedColorCode(high) || !epdIsSupportedColorCode(low)) {
        frameUploadAccepted = false;
        frameUploadComplete = false;
        frameUploadError = "unsupported_color_code";
        const bool highInvalid = !epdIsSupportedColorCode(high);
        frameUploadInvalidPixel = (offset + i) * 2 + (highInvalid ? 0 : 1);
        frameUploadInvalidCode = highInvalid ? high : low;
        frameUploadReceived = offset + i;
        return;
      }
    }
    memcpy(frameBuffer + offset, raw.buf, raw.currentSize);
    for (size_t i = 0; i < raw.currentSize; ++i) {
      frameUploadHash ^= raw.buf[i];
      frameUploadHash *= FNV1A_PRIME;
    }
    frameUploadReceived = offset + raw.currentSize;
    return;
  }

  if (raw.status == RAW_END) {
    if (frameUploadAccepted) frameUploadReceived = raw.totalSize;
    frameUploadComplete = frameUploadAccepted && raw.totalSize == EPD_FRAME_BYTES;
    if (!frameUploadComplete && frameUploadError.length() == 0) {
      frameUploadError = "frame_size_mismatch";
    }
    return;
  }

  frameUploadAccepted = false;
  frameUploadComplete = false;
  frameUploadError = "upload_aborted";
}

// WebServer 2.0.0 reuses the fourth server.on() callback for raw bodies and
// multipart uploads. Never dereference server.raw() for a multipart request.
static void handleFrameUploadBody() {
  if (!isRawFrameRequest()) {
    frameUploadAccepted = false;
    frameUploadComplete = false;
    frameUploadReceived = 0;
    frameUploadError = "unsupported_content_type";
    return;
  }
  handleFrameUploadRaw();
}

static void finishFrameUpload(bool enqueueRefresh) {
  if (!isRawFrameRequest()) {
    server.send(415, "application/json",
                "{\"ok\":false,\"error\":\"content_type_must_be_application_octet_stream\"}");
    return;
  }
  if (!frameUploadComplete) {
    const int status = frameUploadError == "epd_action_pending" ? 409 : 400;
    String errorResult = String("{\"ok\":false,\"error\":\"") + frameUploadError +
                         "\",\"received\":" + String(frameUploadReceived) +
                         ",\"expected\":" + String(EPD_FRAME_BYTES);
    if (frameUploadInvalidPixel != static_cast<size_t>(-1)) {
      errorResult += ",\"invalid_pixel\":" + String(frameUploadInvalidPixel) +
                     ",\"invalid_code\":" + String(frameUploadInvalidCode);
    }
    errorResult += "}";
    server.send(status, "application/json", errorResult);
    return;
  }

  const String result = String("{\"ok\":true,\"bytes\":") + String(frameUploadReceived) +
                        ",\"fnv1a\":" + String(frameUploadHash) +
                        ",\"free_psram\":" + String(ESP.getFreePsram()) + "}";
  if (!enqueueRefresh) {
    String ingressResult = result;
    ingressResult.remove(ingressResult.length() - 1);
    ingressResult += ",\"epd_action\":\"none\"}";
    server.send(200, "application/json", ingressResult);
    return;
  }
  if (!queueEpdJob(PendingEpdAction::UploadedFrame, "uploaded_frame", frameUploadHash)) {
    server.send(409, "application/json",
                String("{\"ok\":false,\"error\":\"epd_action_pending\",\"current\":") +
                    epdJobStatusJson() + "}");
    return;
  }
  String queuedResult = result;
  queuedResult.remove(queuedResult.length() - 1);
  queuedResult += ",\"job_id\":" + String(epdJobId) + "}";
  server.send(202, "application/json", queuedResult);
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
  Serial.printf("WiFi AP SSID: %s IP: %s\n",
                WIFI_AP_SSID, WiFi.softAPIP().toString().c_str());
}

static void startServer() {
  static const char *requestHeaders[] = {"Content-Type"};
  server.collectHeaders(requestHeaders, 1);
  server.on("/", HTTP_GET, []() {
    server.send(200, "text/html; charset=utf-8", indexPage());
  });
  server.on("/api/version", HTTP_GET, []() {
    server.send(200, "text/plain; charset=utf-8",
                 String(FW_BUILD_TAG) + "\nPanel: " + String(EPD_WIDTH) + "x" + String(EPD_HEIGHT) +
                     "\nDriver API: " + String(EPD_DRIVER_API_VERSION) +
                     "\nFrame bytes: " + String(EPD_FRAME_BYTES) +
                     "\nRefresh SPI Hz: " + String(EPD_SPI_DEFAULT_HZ) +
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
  server.on("/api/diagnostic/revisions", HTTP_POST, []() {
    if (pendingEpdAction != PendingEpdAction::None) {
      server.send(409, "application/json", "{\"error\":\"epd_action_pending\"}");
      return;
    }
    server.send(200, "application/json", epdDiagnosticReadRevisionsJson());
  });
  server.on("/api/diagnostic/report", HTTP_GET, []() {
    server.send(200, "application/json", epdDiagnosticReportWithJobJson());
  });
  server.on("/api/diagnostic/map-orient-v1-generate", HTTP_POST, []() {
    if (epdJobActive() || pendingEpdAction != PendingEpdAction::None) {
      server.send(409, "application/json",
                  String("{\"ok\":false,\"error\":\"epd_action_pending\",\"current\":") +
                      epdJobStatusJson() + "}");
      return;
    }
    if (!generateMapOrientV1()) {
      server.send(500, "application/json",
                  "{\"ok\":false,\"error\":\"map_generation_failed\"}");
      return;
    }
    server.send(200, "application/json",
                String("{\"ok\":true,\"bytes\":") + String(EPD_FRAME_BYTES) +
                    ",\"fnv1a\":" + String(generatedFrameHash) +
                    ",\"expected_fnv1a\":" + String(MAP_ORIENT_V1_EXPECTED_FNV1A) +
                    ",\"epd_action\":\"none\"}");
  });
  server.on("/api/job", HTTP_GET, []() {
    server.send(200, "application/json", epdJobStatusJson());
  });
  server.on("/api/diagnostic/reset", HTTP_POST, []() {
    const int before = epdReadBusy();
    Serial.printf("EPD diagnostic reset: BUSY before=%d\n", before);
    epdResetOnly();
    const int after = epdReadBusy();
    Serial.printf("EPD diagnostic reset: BUSY after=%d\n", after);
    server.send(200, "application/json",
                String("{\"busy_before\":") + String(before) +
                    ",\"busy_after\":" + String(after) + "}");
  });
  server.on("/api/diagnostic/cs-high", HTTP_POST, []() {
    epdDiagnosticSetCsLevel(true);
    server.send(200, "application/json",
                String("{\"cs\":") + String(digitalRead(EPD_PIN_CS)) +
                    ",\"cs2\":" + String(digitalRead(EPD_PIN_CS2)) +
                    ",\"sck\":" + String(digitalRead(EPD_PIN_SCK)) +
                    ",\"dc\":" + String(digitalRead(EPD_PIN_DC)) + "}");
  });
  server.on("/api/diagnostic/cs-low", HTTP_POST, []() {
    epdDiagnosticSetCsLevel(false);
    server.send(200, "application/json",
                String("{\"cs\":") + String(digitalRead(EPD_PIN_CS)) +
                    ",\"cs2\":" + String(digitalRead(EPD_PIN_CS2)) +
                    ",\"sck\":" + String(digitalRead(EPD_PIN_SCK)) +
                    ",\"dc\":" + String(digitalRead(EPD_PIN_DC)) + "}");
  });
  server.on("/api/diagnostic/cs2-low", HTTP_POST, []() {
    epdDiagnosticSetCs2Level(false);
    server.send(200, "application/json",
                String("{\"cs\":") + String(digitalRead(EPD_PIN_CS)) +
                    ",\"cs2\":" + String(digitalRead(EPD_PIN_CS2)) +
                    ",\"sck\":" + String(digitalRead(EPD_PIN_SCK)) +
                    ",\"dc\":" + String(digitalRead(EPD_PIN_DC)) + "}");
  });
  server.on("/api/diagnostic/release", HTTP_POST, []() {
    epdDiagnosticReleasePins();
    server.send(200, "application/json",
                String("{\"cs\":") + String(digitalRead(EPD_PIN_CS)) +
                    ",\"rst\":" + String(digitalRead(EPD_PIN_RST)) + "}");
  });
  server.on("/api/test", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::Test, "legacy_test_pattern");
  });
  server.on("/api/black", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::Black, "cascade_black");
  });
  server.on("/api/white", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::White, "cascade_white");
  });
  server.on("/api/bars", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::Bars, "cascade_global_vertical_bars");
  });
  server.on("/api/halves-wb", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::HalvesWhiteBlack, "cascade_halves_white_black");
  });
  server.on("/api/bars-800x480", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::Bars800x480, "legacy_bars_800x480");
  });
  server.on("/api/white-800x480", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::White800x480, "legacy_white_800x480");
  });
  server.on("/api/black-800x480", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::Black800x480, "legacy_black_800x480");
  });
  server.on("/api/bars-512x600", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::Bars512x600, "legacy_bars_512x600");
  });
  server.on("/api/white-512x600", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::White512x600, "legacy_white_512x600");
  });
  server.on("/api/black-512x600", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::Black512x600, "legacy_black_512x600");
  });
  server.on("/api/bars-swap", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::BarsSwap, "cascade_adjacent_nibble_swap_bars");
  });
  server.on("/api/bars-h", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::BarsHorizontal, "cascade_global_horizontal_bars");
  });
  server.on("/api/bars-8bpp", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::Bars8bpp, "legacy_8bpp_probe");
  });
  server.on("/api/bars-cs2-test", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::BarsCs2Probe,
                          "deprecated_alias_cascade_global_vertical_bars");
  });
  server.on("/api/diagnostic/white-512-slow", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::DiagWhite512Slow, "legacy_white_512_slow");
  });
  server.on("/api/diagnostic/black-512-slow", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::DiagBlack512Slow, "legacy_black_512_slow");
  });
  server.on("/api/diagnostic/white-800-slow", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::DiagWhite800Slow, "legacy_white_800_slow");
  });
  server.on("/api/diagnostic/white-1024-short-slow", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::DiagWhite1024ShortSlow,
                          "legacy_white_1024_short_slow");
  });
  server.on("/api/diagnostic/white-512-long-slow", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::DiagWhite512LongSlow,
                          "legacy_white_512_long_slow");
  });
  server.on("/api/diagnostic/white-1024-full-slow", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::DiagWhite1024FullSlow,
                          "legacy_white_1024_full_slow");
  });
  server.on("/api/diagnostic/cs1-bars-isolated", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::DiagCs1BarsIsolated,
                          "legacy_cs1_bars_isolated");
  });
  server.on("/api/diagnostic/cascade-white-black-slow", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::DiagCascadeWhiteBlackSlow,
                          "cascade_cs1_white_cs2_black_slow");
  });
  server.on("/api/diagnostic/cascade-black-white-slow", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::DiagCascadeBlackWhiteSlow,
                          "cascade_cs1_black_cs2_white_slow");
  });
  server.on("/api/diagnostic/cascade-dual-bars-slow", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::DiagCascadeDualBarsSlow,
                          "cascade_repeated_half_bars_slow");
  });
  server.on("/api/diagnostic/cascade-global-bars-slow", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::DiagCascadeGlobalBarsSlow,
                          "cascade_global_vertical_bars_slow");
  });
  server.on("/api/diagnostic/cascade-global-horizontal-bars-slow", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::DiagCascadeGlobalHorizontalBarsSlow,
                          "cascade_global_horizontal_bars_slow");
  });
  server.on("/api/diagnostic/map-orient-v1-slow", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::DiagMapOrientV1Slow, "map_orient_v1_slow");
  });
  server.on("/api/diagnostic/dual-white-black-slow", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::DiagDualWhiteBlackSlow,
                          "legacy_no_ccset_cs1_white_cs2_black_slow");
  });
  server.on("/api/diagnostic/dual-black-white-slow", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::DiagDualBlackWhiteSlow,
                          "legacy_no_ccset_cs1_black_cs2_white_slow");
  });
  server.on("/api/diagnostic/dual-white-white-slow", HTTP_POST, []() {
    queueEpdJobAndRespond(PendingEpdAction::DiagDualWhiteWhiteSlow,
                          "legacy_no_ccset_dual_white_slow");
  });
  server.on("/api/frame", HTTP_POST,
            []() { finishFrameUpload(true); }, handleFrameUploadBody);
  server.on("/api/diagnostic/frame-ingress", HTTP_POST,
            []() { finishFrameUpload(false); }, handleFrameUploadBody);
  server.onNotFound([]() {
    server.send(404, "text/plain; charset=utf-8", "Not found");
  });
  server.begin();
}

void setup() {
  Serial.begin(115200);
  delay(2000);
  Serial.println("\nESP32-S3 eInk server booting");
  Serial.printf("Firmware: %s\n", FW_BUILD_TAG);
  Serial.printf("Panel: %u x %u, frame bytes: %u\n",
                EPD_WIDTH, EPD_HEIGHT, static_cast<unsigned>(EPD_FRAME_BYTES));
  Serial.printf("Controller: %u x %u, frame bytes per controller: %u\n",
                EPD_CONTROLLER_WIDTH, EPD_HEIGHT, static_cast<unsigned>(EPD_CONTROLLER_FRAME_BYTES));
  Serial.printf("PSRAM: total=%u, free=%u bytes\n",
                static_cast<unsigned>(ESP.getPsramSize()),
                static_cast<unsigned>(ESP.getFreePsram()));
  Serial.printf("Pins BUSY=%d RST=%d CS=%d CS2=%d DC=%d SCK=%d SDI=%d BS=%d SWC=%d\n",
                EPD_PIN_BUSY, EPD_PIN_RST, EPD_PIN_CS, EPD_PIN_CS2, EPD_PIN_DC,
                EPD_PIN_SCK, EPD_PIN_MOSI, EPD_PIN_BS, EPD_PIN_SWC);

  Serial.println("EPD GPIO init");
  epdBegin();

  Serial.println("WiFi init");
  startWiFi();
  startServer();
  Serial.println("HTTP server started");

#if EPD_ENABLE_TEST_PATTERN
  Serial.println("Drawing boot test pattern");
  drawTestPattern();
  Serial.println("Boot test pattern done");
#endif
}

void loop() {
  server.handleClient();
  const PendingEpdAction action = pendingEpdAction;
  if (action != PendingEpdAction::None) {
    pendingEpdAction = PendingEpdAction::None;
    epdJobState = EpdJobState::Running;
    epdJobStartedAtMs = millis();
    const uint32_t operationIdBefore = epdGetLastOperationReport().operationId;
    bool resultKnown = false;
    bool result = false;
    Serial.printf("Running EPD job %lu action %u (%s)\n",
                  static_cast<unsigned long>(epdJobId),
                  static_cast<unsigned>(action), epdJobName);
    switch (action) {
      case PendingEpdAction::UploadedFrame:
        result = epdDisplayFrame(frameBuffer, EPD_FRAME_BYTES);
        resultKnown = true;
        break;
      case PendingEpdAction::Test:
        drawTestPattern();
        break;
      case PendingEpdAction::Black:
        result = epdClearBlack();
        resultKnown = true;
        break;
      case PendingEpdAction::White:
        result = epdClearWhite();
        resultKnown = true;
        break;
      case PendingEpdAction::Bars:
        result = epdDisplayColorBars();
        resultKnown = true;
        break;
      case PendingEpdAction::BarsSwap:
        result = epdDisplayColorBarsSwapped();
        resultKnown = true;
        break;
      case PendingEpdAction::BarsHorizontal:
        result = epdDisplayHorizontalBars();
        resultKnown = true;
        break;
      case PendingEpdAction::Bars8bpp:
        epdDisplayColorBars8bpp();
        break;
      case PendingEpdAction::BarsCs2Probe:
        result = epdDisplayColorBarsCs2Probe();
        resultKnown = true;
        break;
      case PendingEpdAction::Bars800x480:
        epdDisplayColorBars800x480();
        break;
      case PendingEpdAction::White800x480:
        epdClearWhite800x480();
        break;
      case PendingEpdAction::Black800x480:
        epdClearBlack800x480();
        break;
      case PendingEpdAction::Bars512x600:
        epdDisplayColorBars512x600();
        break;
      case PendingEpdAction::White512x600:
        epdClearWhite512x600();
        break;
      case PendingEpdAction::Black512x600:
        epdClearBlack512x600();
        break;
      case PendingEpdAction::HalvesWhiteBlack:
        result = epdDisplayHalfWhiteHalfBlack();
        resultKnown = true;
        break;
      case PendingEpdAction::DiagWhite512Slow:
        result = epdDiagnosticSolid(512, 600, 153600, 0x11, EPD_SPI_DIAGNOSTIC_HZ);
        resultKnown = true;
        break;
      case PendingEpdAction::DiagBlack512Slow:
        result = epdDiagnosticSolid(512, 600, 153600, 0x00, EPD_SPI_DIAGNOSTIC_HZ);
        resultKnown = true;
        break;
      case PendingEpdAction::DiagWhite800Slow:
        result = epdDiagnosticSolid(800, 480, 192000, 0x11, EPD_SPI_DIAGNOSTIC_HZ);
        resultKnown = true;
        break;
      case PendingEpdAction::DiagWhite1024ShortSlow:
        result = epdDiagnosticSolid(1024, 600, 153600, 0x11, EPD_SPI_DIAGNOSTIC_HZ);
        resultKnown = true;
        break;
      case PendingEpdAction::DiagWhite512LongSlow:
        result = epdDiagnosticSolid(512, 600, EPD_FRAME_BYTES, 0x11, EPD_SPI_DIAGNOSTIC_HZ);
        resultKnown = true;
        break;
      case PendingEpdAction::DiagWhite1024FullSlow:
        result = epdDiagnosticSolid(1024, 600, EPD_FRAME_BYTES, 0x11, EPD_SPI_DIAGNOSTIC_HZ);
        resultKnown = true;
        break;
      case PendingEpdAction::DiagCs1BarsIsolated:
        result = epdDiagnosticCs1ColorBars(EPD_SPI_DIAGNOSTIC_HZ);
        resultKnown = true;
        break;
      case PendingEpdAction::DiagCascadeWhiteBlackSlow:
        result = epdDiagnosticDualCascadeSolid(0x11, 0x00, EPD_SPI_DIAGNOSTIC_HZ);
        resultKnown = true;
        break;
      case PendingEpdAction::DiagCascadeBlackWhiteSlow:
        result = epdDiagnosticDualCascadeSolid(0x00, 0x11, EPD_SPI_DIAGNOSTIC_HZ);
        resultKnown = true;
        break;
      case PendingEpdAction::DiagCascadeDualBarsSlow:
        result = epdDiagnosticDualCascadeColorBars(EPD_SPI_DIAGNOSTIC_HZ);
        resultKnown = true;
        break;
      case PendingEpdAction::DiagCascadeGlobalBarsSlow:
        result = epdDiagnosticCascadeGlobalColorBars(EPD_SPI_DIAGNOSTIC_HZ);
        resultKnown = true;
        break;
      case PendingEpdAction::DiagCascadeGlobalHorizontalBarsSlow:
        result = epdDiagnosticCascadeGlobalHorizontalBars(EPD_SPI_DIAGNOSTIC_HZ);
        resultKnown = true;
        break;
      case PendingEpdAction::DiagMapOrientV1Slow:
        result = drawAndDisplayMapOrientV1(EPD_SPI_DIAGNOSTIC_HZ);
        resultKnown = true;
        break;
      case PendingEpdAction::DiagDualWhiteBlackSlow:
        result = epdDiagnosticDualSolid(0x11, 0x00, EPD_SPI_DIAGNOSTIC_HZ);
        resultKnown = true;
        break;
      case PendingEpdAction::DiagDualBlackWhiteSlow:
        result = epdDiagnosticDualSolid(0x00, 0x11, EPD_SPI_DIAGNOSTIC_HZ);
        resultKnown = true;
        break;
      case PendingEpdAction::DiagDualWhiteWhiteSlow:
        result = epdDiagnosticDualSolid(0x11, 0x11, EPD_SPI_DIAGNOSTIC_HZ);
        resultKnown = true;
        break;
      case PendingEpdAction::None:
        break;
    }
    bool freshCompletedReport = false;
    uint32_t completedOperationId = 0;
    String completedDriverReport;
    if (resultKnown) {
      const EpdOperationReport &report = epdGetLastOperationReport();
      freshCompletedReport = report.valid && !report.running &&
                             report.operationId > operationIdBefore &&
                             report.operationId > epdPublishedOperationId &&
                             report.sequenceOk == result;
      if (freshCompletedReport) {
        completedOperationId = report.operationId;
        completedDriverReport = epdDiagnosticReportJson();
        if (!completedDriverReport.startsWith("{\"operation_id\":")) {
          freshCompletedReport = false;
          result = false;
          Serial.println("EPD job rejected: completed report serialization failed");
        }
      } else {
        // Never publish or return success for an action that reused, omitted,
        // or left a report running. The previous immutable snapshot remains
        // bound to its original job.
        Serial.printf("EPD job %lu rejected: missing fresh completed driver report\n",
                      static_cast<unsigned long>(epdJobId));
        result = false;
      }
    }
    epdJobResultKnown = resultKnown;
    epdJobResult = result;
    epdJobFinishedAtMs = millis();
    epdJobState = resultKnown && !result ? EpdJobState::Failed : EpdJobState::Completed;
    if (freshCompletedReport) {
      const String completedJobSnapshot =
          epdBuildCompletedJobReportJson(completedDriverReport, completedOperationId);
      // One assignment publishes the complete job+driver snapshot. GET never
      // reads the driver's mutable live global.
      epdPublishedReportJson = completedJobSnapshot;
      epdPublishedOperationId = completedOperationId;
    }
    Serial.printf("EPD job %lu finished: state=%s result_known=%d result=%d\n",
                  static_cast<unsigned long>(epdJobId), epdJobStateName(epdJobState),
                  resultKnown ? 1 : 0, result ? 1 : 0);
  }
  delay(2);
}
