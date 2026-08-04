"use strict";

const $ = (id) => document.getElementById(id);
const state = {
  config: null,
  file: null,
  artifactReady: false,
  uploadAuthorized: false,
  connectionAllowed: false,
  armed: false,
  refreshLocked: false,
};

function badge(id, value) {
  const element = $(id);
  element.textContent = value ? "YES" : "PENDING";
  element.className = `badge ${value ? "yes" : "pending"}`;
}

function setError(error, recoverable = false) {
  const detail = $("errorDetail");
  detail.hidden = false;
  detail.textContent = error instanceof Error ? error.message : String(error);
  $("recoverButton").hidden = !recoverable;
}

function clearError() {
  $("errorDetail").hidden = true;
  $("errorDetail").textContent = "";
  $("recoverButton").hidden = true;
}

function updateButtons() {
  $("generateButton").disabled = !state.file || state.refreshLocked;
  $("preflightButton").disabled = !state.connectionAllowed || state.refreshLocked;
  $("armButton").disabled = !state.connectionAllowed || state.refreshLocked;
  $("refreshButton").disabled = !(
    state.artifactReady && state.uploadAuthorized && state.armed && !state.refreshLocked
  );
  $("allowConnection").disabled = state.connectionAllowed || state.refreshLocked;
  $("cancelButton").disabled = !state.refreshLocked;
  $("abortButton").disabled = !state.refreshLocked;
}

async function jsonRequest(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    const error = new Error(data.detail || `HTTP ${response.status}`);
    error.kind = data.error || "ApplicationError";
    throw error;
  }
  return data;
}

async function postJson(path, body) {
  return jsonRequest(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body),
  });
}

function parseMapping(id) {
  const fields = $(id).value.split(",").map((field) => field.trim());
  if (fields.length !== 4 || fields.some((field) => field !== "0" && field !== "1")) {
    throw new Error(`${id} 必须显式填写四个逗号分隔的 0/1`);
  }
  return fields.map(Number);
}

function mappingBody() {
  return {cs1: parseMapping("cs1Mapping"), cs2: parseMapping("cs2Mapping")};
}

async function sha256Hex(buffer) {
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function normalizedRgba(file, fit) {
  const bitmap = await createImageBitmap(file, {imageOrientation: "from-image"});
  const canvas = $("workCanvas");
  const context = canvas.getContext("2d", {willReadFrequently: true});
  context.clearRect(0, 0, canvas.width, canvas.height);
  let sx = 0, sy = 0, sw = bitmap.width, sh = bitmap.height;
  let dx = 0, dy = 0, dw = canvas.width, dh = canvas.height;
  if (fit === "contain") {
    const scale = Math.min(canvas.width / bitmap.width, canvas.height / bitmap.height);
    dw = bitmap.width * scale;
    dh = bitmap.height * scale;
    dx = (canvas.width - dw) / 2;
    dy = (canvas.height - dh) / 2;
  } else if (fit === "cover") {
    const sourceRatio = bitmap.width / bitmap.height;
    const targetRatio = canvas.width / canvas.height;
    if (sourceRatio > targetRatio) {
      sw = bitmap.height * targetRatio;
      sx = (bitmap.width - sw) / 2;
    } else {
      sh = bitmap.width / targetRatio;
      sy = (bitmap.height - sh) / 2;
    }
  }
  context.imageSmoothingEnabled = false;
  context.drawImage(bitmap, sx, sy, sw, sh, dx, dy, dw, dh);
  bitmap.close();
  return context.getImageData(0, 0, canvas.width, canvas.height).data;
}

function renderReport(report) {
  $("dimensions").textContent = `${report.output.width} × ${report.output.height}`;
  $("frameBytes").textContent = String(report.output.bytes);
  $("inputHash").textContent = report.input.sha256;
  $("frameHash").textContent = report.output.sha256;
  $("paletteSummary").textContent = `${report.palette_provenance.id} · calibrated=${report.palette_provenance.calibrated}`;
  const colours = {black: "#111", white: "#b9b9b0", yellow: "#ba8b00", red: "#a62e2e", blue: "#315f7d", green: "#39713a"};
  $("usage").replaceChildren(...report.output.usage.map((item) => {
    const element = document.createElement("div");
    element.style.background = colours[item.name] || "#555";
    element.textContent = `${item.code} ${item.name} ${(item.ratio * 100).toFixed(2)}%`;
    return element;
  }));
  state.artifactReady = report.offline_verified === true;
  state.uploadAuthorized = report.formal_upload_authorized === true;
  badge("offlineBadge", state.artifactReady);
  updateButtons();
}

async function generatePreview() {
  clearError();
  state.refreshLocked = true;
  updateButtons();
  try {
    const sourceBuffer = await state.file.arrayBuffer();
    const sourceHash = await sha256Hex(sourceBuffer);
    const fit = $("fitPolicy").value;
    const rgba = await normalizedRgba(state.file, fit);
    const response = await fetch("/application/convert", {
      method: "POST",
      headers: {
        "Content-Type": "application/octet-stream",
        "X-Input-SHA256": sourceHash,
        "X-Input-Media-Type": state.file.type || "application/octet-stream",
        "X-Fit-Policy": fit,
        "X-Dither-Mode": $("ditherMode").value,
        "X-Text-Mode": String($("textMode").checked),
        "X-White-Protection": String($("whiteProtection").checked),
      },
      body: rgba,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    $("previewImage").src = `data:image/png;base64,${data.preview_png_base64}`;
    renderReport(data.report);
  } catch (error) {
    setError(error);
  } finally {
    state.refreshLocked = false;
    updateButtons();
  }
}

async function allowConnection() {
  clearError();
  try {
    await postJson("/application/device/allow", {allow: true});
    state.connectionAllowed = true;
    $("jobState").textContent = "connection_allowed";
  } catch (error) { setError(error); }
  updateButtons();
}

async function preflight() {
  clearError();
  try {
    const data = await postJson("/application/device/preflight", mappingBody());
    $("jobState").textContent = "preflight_verified";
    $("jobDetail").textContent = `${data.result.build_tag} · ${data.result.driver_api}`;
  } catch (error) { setError(error); }
}

async function arm() {
  clearError();
  try {
    await postJson("/application/device/arm", {confirmation: $("armPhrase").value});
    state.armed = true;
    $("jobState").textContent = "armed_one_shot";
  } catch (error) { setError(error); }
  updateButtons();
}

async function enqueueRefresh() {
  clearError();
  state.refreshLocked = true;
  state.armed = false;
  updateButtons();
  try {
    const data = await postJson("/application/device/enqueue", mappingBody());
    $("jobState").textContent = data.result.state;
    $("jobDetail").textContent = data.result.statement;
    await pollUntilTerminal();
  } catch (error) {
    setError(error, error.kind === "AdapterNetworkError");
  }
}

async function pollUntilTerminal() {
  while (state.refreshLocked) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    try {
      const result = await jsonRequest("/application/device/job");
      $("jobState").textContent = result.state;
      $("jobDetail").textContent = `job_id=${result.job.job_id}; HTTP 202 本身不计完成`;
      if (result.state === "completed_pending_report") {
        const final = await jsonRequest("/application/device/report");
        $("jobState").textContent = final.state;
        $("jobDetail").textContent = "协议证据闭环；仍需人工确认屏幕/CV/电流/温度。";
        badge("protocolBadge", final.protocol_verified === true);
        state.refreshLocked = false;
        clearError();
        updateButtons();
        return;
      }
    } catch (error) {
      setError(error, error.kind === "AdapterNetworkError");
      return;
    }
  }
}

async function recover() {
  try {
    const data = await postJson("/application/device/recover", {});
    clearError();
    $("jobState").textContent = data.result.state;
    await pollUntilTerminal();
  } catch (error) { setError(error, true); }
}

async function queryCancel() {
  try {
    const data = await postJson("/application/device/cancel", {});
    $("jobDetail").textContent = `cancel=${data.result.status}; remote_job_may_continue=${data.result.remote_job_may_continue}`;
  } catch (error) { setError(error); }
}

async function localAbort() {
  try {
    const data = await postJson("/application/device/local-abort", {});
    state.refreshLocked = false;
    $("jobState").textContent = "local_aborted";
    $("jobDetail").textContent = `仅清除本地状态；remote_cancelled=${data.result.remote_cancelled}`;
    updateButtons();
  } catch (error) { setError(error); }
}

async function initialize() {
  try {
    state.config = await jsonRequest("/application/config");
    $("ditherMode").replaceChildren(...state.config.dither_modes.map((mode) => {
      const option = document.createElement("option"); option.value = mode; option.textContent = mode; return option;
    }));
    const paletteOption = document.createElement("option");
    paletteOption.value = state.config.palette.id;
    paletteOption.textContent = `${state.config.palette.id} · calibrated=${state.config.palette.calibrated}`;
    $("paletteMode").replaceChildren(paletteOption);
    $("paletteSummary").textContent = state.config.palette.id;
    $("paletteWarning").textContent = state.config.palette.calibrated
      ? `已加载 calibrated palette：${state.config.palette.source}`
      : "REFERENCE PALETTE 未校准：只允许明确的离线预览，不能授权正式整屏上传。";
    $("adapterNotice").textContent = state.config.device_adapter === "OfflineAdapter"
      ? "当前为 OfflineAdapter：不会产生网络请求。重启本地服务并显式提供设备参数后才可连接。"
      : "HTTP adapter 已由启动参数启用，但尚未获得 UI 连接许可，当前不会发送请求。";
  } catch (error) { setError(error); }
  updateButtons();
}

$("imageInput").addEventListener("change", (event) => {
  state.file = event.target.files[0] || null;
  $("fileSummary").textContent = state.file ? `${state.file.name} · ${state.file.size} bytes` : "尚未选择图片";
  updateButtons();
});
$("generateButton").addEventListener("click", generatePreview);
$("allowConnection").addEventListener("click", allowConnection);
$("preflightButton").addEventListener("click", preflight);
$("armButton").addEventListener("click", arm);
$("refreshButton").addEventListener("click", enqueueRefresh);
$("recoverButton").addEventListener("click", recover);
$("cancelButton").addEventListener("click", queryCancel);
$("abortButton").addEventListener("click", localAbort);
initialize();
