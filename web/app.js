"use strict";

const $ = (id) => document.getElementById(id);
const TOKEN_STORAGE_KEY = "mf1750.applicationToken";
const state = {
  token: null,
  config: null,
  file: null,
  artifactRevision: 0,
  artifactReady: false,
  artifactVisible: false,
  uploadAuthorized: false,
  connectionAllowed: false,
  preflightVerified: false,
  armed: false,
  generationActive: false,
  refreshLocked: false,
  localAbortQuarantine: false,
  previewUrls: [],
};
let invalidationTail = Promise.resolve();
let operationWatchActive = false;

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
  const busy = state.generationActive || state.refreshLocked;
  $("generateButton").disabled = !state.file || busy;
  $("preflightButton").disabled = !(
    state.connectionAllowed && state.artifactReady && state.artifactVisible && !busy
  );
  $("armButton").disabled = !(
    state.connectionAllowed && state.preflightVerified && state.uploadAuthorized &&
    state.artifactVisible && !busy
  );
  $("refreshButton").disabled = !(
    state.artifactReady && state.uploadAuthorized && state.preflightVerified &&
    state.armed && state.artifactVisible && !busy
  );
  $("allowConnection").disabled = state.connectionAllowed || busy;
  $("cancelButton").disabled = !state.refreshLocked || state.localAbortQuarantine;
  $("abortButton").disabled = !state.refreshLocked || state.localAbortQuarantine;
  for (const id of [
    "imageInput", "fitPolicy", "rotationDegrees", "gamutProfile", "ditherMode",
    "paletteMode", "textMode", "whiteProtection", "algorithmSeed",
    "cs1Mapping", "cs2Mapping",
  ]) {
    $(id).disabled = busy;
  }
  const mappingOff = $("gamutProfile").value === "none";
  $("renderingIntent").disabled = busy || mappingOff;
  $("mappingStrength").disabled = busy || mappingOff;
  const capability = state.config?.halftone_algorithms?.find(
    (item) => item.id === $("ditherMode").value
  );
  $("optimizationBudget").disabled = busy || capability?.supports_budget !== true;
}

async function authorizedFetch(path, options = {}) {
  if (!state.token) throw new Error("缺少本地应用会话 token；请使用服务启动时打印的完整 URL");
  const headers = {...(options.headers || {}), "X-Application-Token": state.token};
  return fetch(path, {...options, headers});
}

async function jsonRequest(path, options = {}) {
  const response = await authorizedFetch(path, options);
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

function captureApplicationToken() {
  const fragment = new URLSearchParams(window.location.hash.slice(1));
  const supplied = fragment.get("token");
  if (supplied) sessionStorage.setItem(TOKEN_STORAGE_KEY, supplied);
  state.token = supplied || sessionStorage.getItem(TOKEN_STORAGE_KEY);
  if (window.location.hash) {
    history.replaceState(null, document.title, window.location.pathname);
  }
  if (!state.token) {
    throw new Error("URL 中没有应用会话 token；请重新打开服务启动时打印的完整地址");
  }
}

function clearArtifactUi() {
  state.artifactReady = false;
  state.artifactVisible = false;
  state.uploadAuthorized = false;
  state.preflightVerified = false;
  state.armed = false;
  badge("offlineBadge", false);
  badge("protocolBadge", false);
  for (const url of state.previewUrls) URL.revokeObjectURL(url);
  state.previewUrls = [];
  for (const id of [
    "sourcePreviewImage", "mappedPreviewImage", "previewImage", "modelPreviewImage",
  ]) {
    $(id).removeAttribute("src");
  }
  $("inputHash").textContent = "—";
  $("frameHash").textContent = "—";
  $("mappedHash").textContent = "—";
  $("mappingSummary").textContent = "—";
  $("algorithmSummary").textContent = "—";
  $("modelScore").textContent = "—";
  $("usage").replaceChildren();
  updateButtons();
}

function queueServerInvalidation(reason) {
  const request = invalidationTail.then(() =>
    postJson("/application/artifact/invalidate", {reason})
  );
  invalidationTail = request.catch(() => undefined);
  return request;
}

function invalidateArtifact(reason, notify = true) {
  state.artifactRevision += 1;
  clearArtifactUi();
  if (!notify || !state.token) return Promise.resolve();
  return queueServerInvalidation(reason);
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

function base64UrlJson(value) {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function preparationMetadata(sourceHash, mediaType) {
  const profileId = $("gamutProfile").value;
  const profile = state.config.gamut_profiles.find((item) => item.id === profileId);
  const algorithm = $("ditherMode").value;
  const capability = state.config.halftone_algorithms.find((item) => item.id === algorithm);
  const requestedBudget = Number($("optimizationBudget").value);
  return {
    schema: "mf1750-prepare-request",
    version: 2,
    source: {expected_sha256: sourceHash, media_type: mediaType},
    geometry: {
      fit: $("fitPolicy").value,
      rotation_degrees: Number($("rotationDegrees").value),
    },
    mapping: {
      algorithm: profileId === "none" ? "none" : "spectra6-xyz-convex-v1",
      profile_id: profile?.id || null,
      profile_sha256: profile?.canonical_sha256 || null,
      intent: $("renderingIntent").value,
      strength: Number($("mappingStrength").value),
    },
    halftone: {
      algorithm,
      seed: Number($("algorithmSeed").value),
      budget: capability?.supports_budget === true ? {
        kind: "deterministic-work-v1",
        max_evaluations: requestedBudget,
        max_accepted_moves: Math.max(1, Math.floor(requestedBudget / 4)),
        stagnation_evaluations: Math.max(1, Math.floor(requestedBudget / 2)),
      } : null,
    },
    protections: {
      white: $("whiteProtection").checked,
      edge: true,
      text: $("textMode").checked,
    },
    purpose: "offline_preview",
  };
}

async function loadPreview(stage, metadata, imageId) {
  if (!metadata || typeof metadata.url !== "string") {
    throw new Error(`响应缺少 ${stage} 预览`);
  }
  const target = new URL(metadata.url, window.location.origin);
  if (
    target.origin !== window.location.origin || target.search || target.hash ||
    !/^\/application\/artifact\/[0-9a-f]{64}\/preview\/(source|mapped|final|model)$/.test(target.pathname)
  ) {
    throw new Error(`${stage} 预览 URL 不属于当前本地工件`);
  }
  const response = await authorizedFetch(target.pathname);
  if (!response.ok) throw new Error(`${stage} 预览 HTTP ${response.status}`);
  const buffer = await response.arrayBuffer();
  const actual = await sha256Hex(buffer);
  if (actual !== metadata.sha256) throw new Error(`${stage} 预览 SHA-256 不匹配`);
  const objectUrl = URL.createObjectURL(new Blob([buffer], {type: "image/png"}));
  state.previewUrls.push(objectUrl);
  $(imageId).src = objectUrl;
}

function renderReport(report, serverStatus = {}) {
  $("dimensions").textContent = `${report.output.width} × ${report.output.height}`;
  $("frameBytes").textContent = String(report.output.bytes);
  $("inputHash").textContent = report.input.sha256;
  $("frameHash").textContent = report.output.sha256;
  const paletteId = report.palette_provenance.id || report.palette_provenance.palette_id;
  $("paletteSummary").textContent = `${paletteId} · calibrated=${report.palette_provenance.calibrated}`;
  const simulation = report.simulation_report || {};
  const mapping = simulation.mapping || {};
  const mappingReport = mapping.report || mapping;
  const mappedRaster = mappingReport.mapped_raster || {};
  const halftone = simulation.halftone || {};
  $("mappedHash").textContent = mappedRaster.canonical_sha256 || mappedRaster.encoded_sha256 || "—";
  $("mappingSummary").textContent = [
    mappingReport.mapper?.algorithm || mapping.algorithm,
    mappingReport.options?.intent,
    mappingReport.options?.strength,
  ].filter((value) => value !== undefined && value !== null).join(" · ") || "—";
  $("algorithmSummary").textContent = halftone.algorithm || report.quantization_options?.dither || "—";
  $("modelScore").textContent = halftone.report?.loss?.final?.total ?? "仅显示器近似";
  const colours = {black: "#111", white: "#b9b9b0", yellow: "#ba8b00", red: "#a62e2e", blue: "#315f7d", green: "#39713a"};
  $("usage").replaceChildren(...report.output.usage.map((item) => {
    const element = document.createElement("div");
    element.style.background = colours[item.name] || "#555";
    element.textContent = `${item.code} ${item.name} ${(item.ratio * 100).toFixed(2)}%`;
    return element;
  }));
  state.artifactReady = report.offline_verified === true;
  state.artifactVisible = true;
  state.uploadAuthorized = report.formal_upload_authorized === true || (
    (serverStatus.n6_formal_mode === true ||
      serverStatus.n6_physical_production_mode === true) &&
    serverStatus.formal_upload_authorized === true
  );
  state.preflightVerified = false;
  state.armed = false;
  badge("offlineBadge", state.artifactReady);
  updateButtons();
}

async function generatePreview() {
  clearError();
  state.generationActive = true;
  updateButtons();
  try {
    const selectedFile = state.file;
    if (!selectedFile) throw new Error("请先选择图片");
    await invalidateArtifact("generation_started");
    const generationRevision = state.artifactRevision;
    const sourceBuffer = await selectedFile.arrayBuffer();
    const sourceHash = await sha256Hex(sourceBuffer);
    const mediaType = selectedFile.type;
    if (!["image/png", "image/jpeg", "image/webp"].includes(mediaType)) {
      throw new Error("G1/S1 路径仅接受 PNG、JPEG 或 WebP 原始文件");
    }
    const preparation = preparationMetadata(sourceHash, mediaType);
    const data = await jsonRequest("/application/convert-v2", {
      method: "POST",
      headers: {
        "Content-Type": mediaType,
        "X-MF1750-Preparation": base64UrlJson(preparation),
      },
      body: sourceBuffer,
    });
    if (generationRevision !== state.artifactRevision || selectedFile !== state.file) {
      throw new Error("图片或量化设置在生成期间发生变化，旧结果已丢弃");
    }
    await Promise.all([
      loadPreview("source", data.previews.source, "sourcePreviewImage"),
      loadPreview("mapped", data.previews.mapped, "mappedPreviewImage"),
      loadPreview("final", data.previews.final, "previewImage"),
      loadPreview("model", data.previews.model, "modelPreviewImage"),
    ]);
    renderReport(data.report, data.status);
  } catch (error) {
    try {
      await invalidateArtifact("generation_failed");
      setError(error);
    } catch (invalidationError) {
      setError(`${error instanceof Error ? error.message : error}; 清除服务端旧帧失败：${invalidationError}`);
    }
  } finally {
    state.generationActive = false;
    updateButtons();
  }
}

async function allowConnection() {
  clearError();
  try {
    await postJson("/application/device/allow", {allow: true});
    state.connectionAllowed = true;
    state.preflightVerified = false;
    state.armed = false;
    $("jobState").textContent = "connection_allowed";
  } catch (error) { setError(error); }
  updateButtons();
}

async function preflight() {
  clearError();
  state.preflightVerified = false;
  state.armed = false;
  updateButtons();
  try {
    const data = await postJson("/application/device/preflight", mappingBody());
    state.preflightVerified = true;
    state.armed = false;
    $("jobState").textContent = "preflight_verified";
    $("jobDetail").textContent = `${data.result.build_tag} · ${data.result.driver_api}`;
  } catch (error) { setError(error); }
  updateButtons();
}

async function arm() {
  clearError();
  try {
    await postJson("/application/device/arm", {
      confirmation: $("armPhrase").value,
      panel_plan_confirmation: $("panelPlanPhrase").value,
      profile_confirmation: $("profilePhrase").value,
    });
    state.armed = true;
    $("jobState").textContent = "armed_one_shot";
  } catch (error) { setError(error); }
  updateButtons();
}

async function enqueueRefresh() {
  clearError();
  state.refreshLocked = true;
  state.preflightVerified = false;
  state.armed = false;
  updateButtons();
  try {
    const data = await postJson("/application/device/enqueue", mappingBody());
    $("jobState").textContent = data.result.state;
    $("jobDetail").textContent = data.result.statement;
    await pollUntilTerminal();
  } catch (error) {
    await reconcileAfterMutationError(error);
  }
}

async function pollUntilTerminal() {
  while (state.refreshLocked) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    try {
      const data = await postJson("/application/device/job", {});
      const result = data.result;
      $("jobState").textContent = result.state;
      $("jobDetail").textContent = `job_id=${result.job.job_id}; HTTP 202 本身不计完成`;
      if (result.state === "completed_pending_report") {
        await retrieveDiagnostic();
        return;
      }
    } catch (error) {
      await reconcileAfterMutationError(error);
      return;
    }
  }
}

async function retrieveDiagnostic() {
  const data = await postJson("/application/device/report", {});
  const final = data.result;
  $("jobState").textContent = final.state;
  $("jobDetail").textContent = "协议证据闭环；仍需人工确认屏幕/CV/电流/温度。";
  badge("protocolBadge", final.protocol_verified === true);
  state.refreshLocked = false;
  clearError();
  updateButtons();
}

function statusHasActiveRefresh(status) {
  return status.operation_in_progress === true || status.refresh_locked === true || [
    "queued", "running", "completed_pending_report",
  ].includes(status.state);
}

async function reconcileInvisibleArtifact(status) {
  if (
    status.artifact_available === true &&
    !statusHasActiveRefresh(status) &&
    !state.artifactVisible
  ) {
    await postJson("/application/artifact/invalidate", {
      reason: "page_reload_without_visible_artifact",
    });
    return jsonRequest("/application/status");
  }
  return status;
}

async function reconcileAfterMutationError(error) {
  try {
    const status = await jsonRequest("/application/status");
    applyStatusFields(status);
    setError(error, status.recovery_available === true);
    resumeStatus(status);
  } catch (statusError) {
    // Neither the failed mutation nor its remote outcome can be trusted when
    // authoritative status is unavailable.  Keep every mutation closed.
    state.refreshLocked = true;
    const primary = error instanceof Error ? error.message : String(error);
    const secondary = statusError instanceof Error ? statusError.message : String(statusError);
    setError(`${primary}; 无法重新读取服务端状态：${secondary}`);
  }
  updateButtons();
}

async function watchOperationCompletion() {
  if (operationWatchActive) return;
  operationWatchActive = true;
  try {
    let status;
    do {
      await new Promise((resolve) => setTimeout(resolve, 250));
      status = await jsonRequest("/application/status");
      applyStatusFields(status);
      updateButtons();
    } while (status.operation_in_progress === true);

    status = await reconcileInvisibleArtifact(status);
    applyStatusFields(status);
    resumeStatus(status);
    updateButtons();
  } catch (error) {
    // The operation outcome is unknown.  Keep every mutating control closed;
    // a reload can resume status reconciliation after the local service is back.
    state.refreshLocked = true;
    setError(error);
    updateButtons();
  } finally {
    operationWatchActive = false;
  }
}

function resumeStatus(status) {
  const current = status.state;
  $("jobState").textContent = current;
  if (status.operation_in_progress === true) {
    state.refreshLocked = true;
    state.armed = false;
    updateButtons();
    void watchOperationCompletion();
  } else if (current === "queued" || current === "running") {
    state.refreshLocked = true;
    updateButtons();
    void pollUntilTerminal();
  } else if (current === "completed_pending_report") {
    state.refreshLocked = true;
    updateButtons();
    void retrieveDiagnostic().catch((error) => reconcileAfterMutationError(error));
  } else if (current === "network_error") {
    state.refreshLocked = status.refresh_locked === true;
    setError(status.error || "设备通信中断，可尝试恢复", status.recovery_available === true);
    updateButtons();
  } else if (current === "local_aborted" && status.local_abort_quarantine === true) {
    state.refreshLocked = true;
    state.localAbortQuarantine = true;
    $("jobDetail").textContent = status.remote_job_may_continue === true
      ? "本地监控已停止，但远端刷新结果未知；本进程禁止再次提交。请确认设备空闲和安全收尾后再重启本地服务。"
      : "远端任务已知结束，但诊断/安全收尾证据被本地中止；本进程禁止再次提交。请人工复核后再重启本地服务。";
    updateButtons();
  }
}

function applyStatusFields(status) {
  state.artifactReady = status.offline_verified === true;
  state.uploadAuthorized = status.formal_upload_authorized === true;
  state.connectionAllowed = status.connection_allowed === true;
  state.preflightVerified = status.preflight_verified === true;
  state.armed = status.armed === true || status.state === "armed";
  state.refreshLocked = status.refresh_locked === true;
  state.localAbortQuarantine = status.local_abort_quarantine === true;
  badge("offlineBadge", state.artifactReady);
  badge("protocolBadge", status.protocol_verified === true);
}

async function recover() {
  try {
    const data = await postJson("/application/device/recover", {});
    clearError();
    const recovered = data.result;
    $("jobState").textContent = recovered.state;
    if (recovered.state === "queued" || recovered.state === "running") {
      state.refreshLocked = true;
      updateButtons();
      await pollUntilTerminal();
    } else if (recovered.state === "completed_pending_report") {
      state.refreshLocked = true;
      updateButtons();
      await retrieveDiagnostic();
    } else {
      state.refreshLocked = false;
      state.preflightVerified = recovered.state === "armed";
      state.armed = recovered.state === "armed";
      updateButtons();
    }
  } catch (error) { await reconcileAfterMutationError(error); }
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
    state.refreshLocked = data.result.new_submission_locked === true;
    state.localAbortQuarantine = state.refreshLocked;
    state.preflightVerified = false;
    state.armed = false;
    $("jobState").textContent = "local_aborted";
    $("jobDetail").textContent = state.localAbortQuarantine
      ? (data.result.remote_job_may_continue === true
        ? "仅清除本地监控；远端刷新可能仍在运行，本进程保持提交锁。请确认设备空闲和安全收尾后再重启本地服务。"
        : "远端任务已结束，但诊断/安全收尾证据未闭环，本进程保持提交锁。请人工复核后再重启本地服务。")
      : `仅清除本地状态；remote_cancelled=${data.result.remote_cancelled}`;
    updateButtons();
  } catch (error) { setError(error); }
}

async function initialize() {
  try {
    captureApplicationToken();
    const [config, initialStatus] = await Promise.all([
      jsonRequest("/application/config"),
      jsonRequest("/application/status"),
    ]);
    let status = initialStatus;
    status = await reconcileInvisibleArtifact(status);
    state.config = config;
    $("ditherMode").replaceChildren(...state.config.halftone_algorithms.map((algorithm) => {
      const option = document.createElement("option");
      option.value = algorithm.id;
      option.textContent = `${algorithm.label}${algorithm.simulation_only ? " · simulation" : ""}`;
      return option;
    }));
    $("ditherMode").value = state.config.defaults.halftone_algorithm;
    const noProfile = document.createElement("option");
    noProfile.value = "none";
    noProfile.textContent = "none / legacy C2";
    $("gamutProfile").replaceChildren(noProfile, ...state.config.gamut_profiles.map((profile) => {
      const option = document.createElement("option");
      option.value = profile.id;
      option.textContent = `${profile.id} · ${profile.characterization_level} · simulation`;
      return option;
    }));
    $("gamutProfile").value = state.config.defaults.gamut_profile_id;
    $("renderingIntent").replaceChildren(...state.config.rendering_intents.map((intent) => {
      const option = document.createElement("option");
      option.value = intent.id;
      option.textContent = intent.label;
      return option;
    }));
    $("renderingIntent").value = state.config.defaults.rendering_intent;
    $("mappingStrength").value = String(state.config.defaults.mapping_strength);
    $("mappingStrengthValue").value = Number($("mappingStrength").value).toFixed(2);
    $("algorithmSeed").value = String(state.config.defaults.seed);
    const paletteOption = document.createElement("option");
    paletteOption.value = state.config.palette.id;
    paletteOption.textContent = `${state.config.palette.id} · calibrated=${state.config.palette.calibrated}`;
    $("paletteMode").replaceChildren(paletteOption);
    $("paletteSummary").textContent = state.config.palette.id;
    $("paletteWarning").textContent = state.config.n6_formal_execution_materialized === true
      ? "N6 fixed formal envelope 已物化：工件仍保留 offline report；外部测量/评审/claim 是独立授权边界。"
      : (state.config.palette.calibrated
        ? `已加载 calibrated palette：${state.config.palette.source}`
        : "REFERENCE PALETTE 与 synthetic gamut profile 未校准：本页面只生成显示器模拟，不能授权正式整屏上传。");
    $("adapterNotice").textContent = state.config.n6_formal_execution_materialized === true
      ? "N6 固定一次执行：preflight 仅本地；原子 claim 后才访问设备；最多一个 /api/frame POST，无 retry/recovery。"
      : (state.config.device_adapter === "OfflineAdapter"
      ? "当前为 OfflineAdapter：不会产生网络请求。重启本地服务并显式提供设备参数后才可连接。"
      : (status.connection_allowed === true
        ? "HTTP adapter 已启用并保留本进程的显式连接许可。"
        : "HTTP adapter 已由启动参数启用，但尚未获得 UI 连接许可，当前不会发送请求。"));
    applyStatusFields(status);
    resumeStatus(status);
  } catch (error) { setError(error); }
  updateButtons();
}

$("imageInput").addEventListener("change", (event) => {
  state.file = event.target.files[0] || null;
  $("fileSummary").textContent = state.file ? `${state.file.name} · ${state.file.size} bytes` : "尚未选择图片";
  void invalidateArtifact("input_file_changed").catch((error) => setError(error));
});
for (const id of [
  "fitPolicy", "rotationDegrees", "gamutProfile", "renderingIntent", "ditherMode",
  "algorithmSeed", "optimizationBudget", "paletteMode", "textMode", "whiteProtection",
]) {
  $(id).addEventListener("change", () => {
    updateButtons();
    void invalidateArtifact(`${id}_changed`).catch((error) => setError(error));
  });
}
$("mappingStrength").addEventListener("input", () => {
  $("mappingStrengthValue").value = Number($("mappingStrength").value).toFixed(2);
});
$("mappingStrength").addEventListener("change", () => {
  void invalidateArtifact("mappingStrength_changed").catch((error) => setError(error));
});
for (const id of ["cs1Mapping", "cs2Mapping"]) {
  $(id).addEventListener("change", () => {
    state.preflightVerified = false;
    state.armed = false;
    updateButtons();
  });
}
$("generateButton").addEventListener("click", generatePreview);
$("allowConnection").addEventListener("click", allowConnection);
$("preflightButton").addEventListener("click", preflight);
$("armButton").addEventListener("click", arm);
$("refreshButton").addEventListener("click", enqueueRefresh);
$("recoverButton").addEventListener("click", recover);
$("cancelButton").addEventListener("click", queryCancel);
$("abortButton").addEventListener("click", localAbort);
initialize();
