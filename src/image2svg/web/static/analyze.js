const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const sourceName = document.getElementById("sourceName");
const previewRow = document.getElementById("previewRow");
const svgPreview = document.getElementById("svgPreview");
const summaryCards = document.getElementById("summaryCards");
const analyzeBtn = document.getElementById("analyzeBtn");
const exportGameBtn = document.getElementById("exportGameBtn");
const downloadJsonBtn = document.getElementById("downloadJsonBtn");
const downloadManifestBtn = document.getElementById("downloadManifestBtn");
const copyJsonBtn = document.getElementById("copyJsonBtn");
const resultsPanel = document.getElementById("resultsPanel");
const jsonView = document.getElementById("jsonView");
const analyzeStatus = document.getElementById("analyzeStatus");
const frameToolbar = document.getElementById("frameToolbar");
const frameSelect = document.getElementById("frameSelect");
const layerTabs = document.querySelectorAll(".layer-tab");
const toast = document.getElementById("toast");
const skeletonReviewPanel = document.getElementById("skeletonReviewPanel");
const mlLandmarksToggle = document.getElementById("mlLandmarksToggle");
const mmposeToggle = document.getElementById("mmposeToggle");
const assetPathInput = document.getElementById("assetPathInput");
const gameRootInput = document.getElementById("gameRootInput");
const exportStatus = document.getElementById("exportStatus");
const terminalSummary = document.getElementById("terminalSummary");
const terminalLog = document.getElementById("terminalLog");
const clearTerminalBtn = document.getElementById("clearTerminalBtn");

let selectedFile = null;
let svgSourceText = "";
let analysisResult = null;
let activeLayer = "assetAnalysis";
let analyzing = false;
let exporting = false;
let defaultGameRoot = "";

function formatElapsed(ms = 0) {
  return `${(Number(ms || 0) / 1000).toFixed(2)}s`;
}

function terminalDetail(event) {
  const parts = [];
  if (event.frameIndex !== undefined && event.frameCount) {
    parts.push(`frame ${Number(event.frameIndex) + 1}/${event.frameCount}`);
  }
  if (event.method) parts.push(`method=${event.method}`);
  if (event.score !== undefined) parts.push(`score=${event.score}`);
  if (event.pathCount !== undefined) parts.push(`paths=${event.pathCount}`);
  if (event.rasterWidth && event.rasterHeight) {
    parts.push(`raster=${event.rasterWidth}x${event.rasterHeight}`);
  }
  if (event.mmposeStatus?.reason) {
    parts.push(`mmpose=${event.mmposeStatus.reason}`);
  }
  if (event.warnings?.length) {
    parts.push(`warnings=${event.warnings.length}`);
  }
  return parts.length ? ` · ${parts.join(" · ")}` : "";
}

function appendTerminal(event) {
  const line = document.createElement("div");
  const level = event.level || (event.type === "error" ? "error" : "info");
  line.className = `terminal-line ${level}`;

  const time = document.createElement("span");
  time.className = "terminal-time";
  time.textContent = formatElapsed(event.elapsedMs);

  const step = document.createElement("span");
  step.className = "terminal-step";
  step.textContent = event.step || event.type || "log";

  const message = document.createElement("span");
  message.className = "terminal-message";
  message.textContent = `${event.message || event.detail || ""}${terminalDetail(event)}`;

  line.append(time, step, message);
  terminalLog.append(line);
  terminalLog.scrollTop = terminalLog.scrollHeight;
  terminalSummary.textContent = message.textContent || "running";
}

function resetTerminal(message = "idle") {
  terminalLog.replaceChildren();
  terminalSummary.textContent = message;
}

function handleStreamEvent(event) {
  if (!event || typeof event !== "object") return null;
  if (event.type === "log") {
    appendTerminal(event);
    return null;
  }
  if (event.type === "error") {
    appendTerminal({ ...event, level: "error", step: "error", message: event.detail || "Phân tích thất bại" });
    throw new Error(event.detail || "Phân tích thất bại");
  }
  if (event.type === "result") {
    appendTerminal({ type: "log", level: "success", step: "done", message: "Analysis result received" });
    return event.result;
  }
  return null;
}

async function readNdjsonStream(res) {
  if (!res.body) {
    throw new Error("Trình duyệt không hỗ trợ stream response");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const maybeResult = handleStreamEvent(JSON.parse(line));
      if (maybeResult) finalResult = maybeResult;
    }
  }

  if (buffer.trim()) {
    const maybeResult = handleStreamEvent(JSON.parse(buffer));
    if (maybeResult) finalResult = maybeResult;
  }

  if (!finalResult) {
    throw new Error("Stream kết thúc nhưng không có kết quả phân tích");
  }
  return finalResult;
}

function showToast(message, isError = false) {
  toast.textContent = message;
  toast.hidden = false;
  toast.classList.toggle("error", isError);
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => {
    toast.hidden = true;
  }, 2800);
}

function setExportStatus(message, isError = false) {
  if (!message) {
    exportStatus.hidden = true;
    exportStatus.textContent = "";
    exportStatus.classList.remove("error");
    return;
  }
  exportStatus.hidden = false;
  exportStatus.textContent = message;
  exportStatus.classList.toggle("error", isError);
}

function guessAssetPath(filename) {
  if (!filename) return "";
  const match = filename.match(/^(\d+)-(.+)-(lengend|legend)\.svg$/i);
  if (!match) return filename;
  const [, num, name, suffix] = match;
  const folderOrder = assetPathInput.dataset.folderOrder;
  if (folderOrder) {
    return `${folderOrder}-${name}-${suffix}/${filename}`;
  }
  return filename;
}

function buildAnalyzeFormData(focusFrames = []) {
  const form = new FormData();
  form.append("file", selectedFile);
  form.append("ml_landmarks", mlLandmarksToggle.checked ? "true" : "false");
  form.append("mmpose", mmposeToggle.checked ? "true" : "false");
  if (focusFrames.length) {
    form.append("focus_frames", focusFrames.join(","));
  }
  return form;
}

function setFile(file) {
  if (!file) return;
  selectedFile = file;
  sourceName.textContent = file.name;
  assetPathInput.value = guessAssetPath(file.name);
  previewRow.hidden = false;
  svgPreview.innerHTML = "";
  const reader = new FileReader();
  reader.onload = () => {
    svgSourceText = reader.result;
    svgPreview.innerHTML = svgSourceText;
  };
  reader.readAsText(file);
  analyzeBtn.disabled = analyzing;
  exportGameBtn.disabled = analyzing || exporting;
  analyzeStatus.textContent = "Sẵn sàng phân tích";
  resultsPanel.hidden = true;
  skeletonReviewPanel.hidden = true;
  previewRow.hidden = false;
  analysisResult = null;
  downloadJsonBtn.disabled = true;
  downloadManifestBtn.disabled = true;
  copyJsonBtn.disabled = true;
  setExportStatus("");
  resetTerminal("ready");
  appendTerminal({ step: "file", message: `Loaded ${file.name}`, elapsedMs: 0 });
}

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});

fileInput.addEventListener("change", () => {
  const file = fileInput.files?.[0];
  if (file) setFile(file);
  fileInput.value = "";
});

dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropzone.classList.add("dragover");
});

dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));

dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropzone.classList.remove("dragover");
  const file = event.dataTransfer.files?.[0];
  if (file) setFile(file);
});

function renderSummary(result) {
  const asset = result.assetAnalysis;
  const strip = result.stripAnalysis;
  const quality = result.qualityReport;
  const manifest = result.gameManifest;
  const validation = manifest?.validation || {};
  const mlBackend = result.frameAnalysis?.[0]?.mlLandmarks?.backend;

  const cards = [
    ["Asset ID", asset.assetId],
    ["Frames", String(strip.frameCount)],
    ["Paths", String(asset.svg.pathCount)],
    ["Quality", String(quality.score)],
  ];

  if (manifest) {
    cards.push(["Game ready", validation.readyForGame ? "Yes" : "No"]);
  }
  if (mlBackend) {
    cards.push(["ML backend", mlBackend]);
  }

  summaryCards.replaceChildren();
  for (const [label, value] of cards) {
    const card = document.createElement("div");
    card.className = "summary-card";
    if (label === "Game ready") {
      card.classList.add(value === "Yes" ? "ready" : "warn");
    }
    card.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
    summaryCards.append(card);
  }
}

function populateFrameSelect(result) {
  frameSelect.replaceChildren();
  for (const frame of result.frameAnalysis) {
    const opt = document.createElement("option");
    opt.value = String(frame.frameIndex);
    opt.textContent = `Frame ${frame.frameIndex}`;
    frameSelect.append(opt);
  }
}

function currentLayerPayload() {
  if (!analysisResult) return null;
  if (activeLayer === "full") return analysisResult;
  if (activeLayer === "frameAnalysis") {
    const idx = Number(frameSelect.value || 0);
    return analysisResult.frameAnalysis.find((frame) => frame.frameIndex === idx) ?? analysisResult.frameAnalysis[0];
  }
  return analysisResult[activeLayer];
}

function renderJsonView() {
  const payload = currentLayerPayload();
  jsonView.textContent = payload ? JSON.stringify(payload, null, 2) : "";
  frameToolbar.hidden = activeLayer !== "frameAnalysis";
}

function afterAnalysis(data) {
  analysisResult = data;
  resultsPanel.hidden = false;
  skeletonReviewPanel.hidden = false;
  previewRow.hidden = true;
  renderSummary(data);
  populateFrameSelect(data);
  renderJsonView();

  SkeletonReview.setData({
    svgSource: svgSourceText,
    analysisResult: data,
    onMoveLandmark: undefined,
  });

  downloadJsonBtn.disabled = false;
  downloadManifestBtn.disabled = !data.gameManifest;
  copyJsonBtn.disabled = false;
  exportGameBtn.disabled = false;

  const validation = data.gameManifest?.validation;
  const ready = validation?.readyForGame ? "ready" : "check";
  analyzeStatus.textContent = `Score ${data.qualityReport.score} · ${data.stripAnalysis.frameCount} frames · game ${ready}`;
}

async function runAnalysis({ focusFrames = [] } = {}) {
  if (!selectedFile || analyzing) return;

  analyzing = true;
  analyzeBtn.disabled = true;
  exportGameBtn.disabled = true;
  analyzeBtn.textContent = "Đang phân tích…";
  analyzeStatus.textContent = "Đang phân tích…";
  setExportStatus("");
  resetTerminal("running");
  appendTerminal({
    step: "request",
    message: `POST /api/analyze-stream · ML=${mlLandmarksToggle.checked ? "on" : "off"} · MMPose=${mmposeToggle.checked ? "on" : "off"}${focusFrames.length ? ` · focus frames=${focusFrames.join(",")}` : ""}`,
    elapsedMs: 0,
  });

  try {
    const res = await fetch("/api/analyze-stream", { method: "POST", body: buildAnalyzeFormData(focusFrames) });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      const detail = Array.isArray(data.detail)
        ? data.detail.map((item) => item.msg).join(", ")
        : data.detail;
      throw new Error(detail || "Phân tích thất bại");
    }

    const data = await readNdjsonStream(res);
    afterAnalysis(data);
    if (focusFrames.length && window.SkeletonReview?.setSelectedFrames) {
      window.SkeletonReview.setSelectedFrames(focusFrames);
    }
    showToast("Phân tích xong");
  } catch (err) {
    showToast(err.message, true);
    analyzeStatus.textContent = "Lỗi phân tích";
  } finally {
    analyzing = false;
    analyzeBtn.disabled = !selectedFile;
    exportGameBtn.disabled = !selectedFile || exporting;
    analyzeBtn.textContent = "Phân tích";
  }
}

async function exportGameManifest() {
  if (!selectedFile || exporting) return;

  exporting = true;
  exportGameBtn.disabled = true;
  exportGameBtn.textContent = "Đang export…";
  setExportStatus("Đang ghi manifest vào game…");

  const form = new FormData();
  form.append("file", selectedFile);
  form.append("ml_landmarks", mlLandmarksToggle.checked ? "true" : "false");
  form.append("mmpose", mmposeToggle.checked ? "true" : "false");
  form.append("asset_path", assetPathInput.value.trim() || selectedFile.name);
  form.append("game_root", gameRootInput.value.trim());

  try {
    const res = await fetch("/api/export-game-manifest", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) {
      const detail = Array.isArray(data.detail)
        ? data.detail.map((item) => item.msg).join(", ")
        : data.detail;
      throw new Error(detail || "Export thất bại");
    }

    if (data.analysis) {
      afterAnalysis(data.analysis);
    } else if (data.gameManifest && analysisResult) {
      analysisResult.gameManifest = data.gameManifest;
      if (data.stackRecommendation) {
        analysisResult.stackRecommendation = data.stackRecommendation;
      }
      renderSummary(analysisResult);
      downloadManifestBtn.disabled = false;
      if (activeLayer === "gameManifest") renderJsonView();
    }

    setExportStatus(`Đã ghi: ${data.written}`);
    showToast("Export game manifest xong");
  } catch (err) {
    setExportStatus(err.message, true);
    showToast(err.message, true);
  } finally {
    exporting = false;
    exportGameBtn.disabled = !selectedFile;
    exportGameBtn.textContent = "Export game manifest";
  }
}

analyzeBtn.addEventListener("click", runAnalysis);
exportGameBtn.addEventListener("click", exportGameManifest);

downloadJsonBtn.addEventListener("click", () => {
  if (!analysisResult) return;
  const payload = {
    ...analysisResult,
    reviewState: SkeletonReview.reviewByFrame,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${analysisResult.assetAnalysis.assetId}.analysis.json`;
  anchor.click();
  URL.revokeObjectURL(url);
  showToast("Đã tải JSON");
});

downloadManifestBtn.addEventListener("click", () => {
  if (!analysisResult?.gameManifest) return;
  const blob = new Blob([JSON.stringify(analysisResult.gameManifest, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${analysisResult.assetAnalysis.assetId}.game-manifest.json`;
  anchor.click();
  URL.revokeObjectURL(url);
  showToast("Đã tải game manifest");
});

copyJsonBtn.addEventListener("click", async () => {
  if (!analysisResult) return;
  const text = JSON.stringify(analysisResult, null, 2);
  try {
    await navigator.clipboard.writeText(text);
    showToast("Đã copy JSON");
  } catch {
    jsonView.textContent = text;
    const range = document.createRange();
    range.selectNodeContents(jsonView);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    document.execCommand("copy");
    showToast("Đã copy JSON");
  }
});

layerTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    layerTabs.forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");
    activeLayer = tab.dataset.layer;
    renderJsonView();
  });
});

frameSelect.addEventListener("change", () => {
  renderJsonView();
  if (analysisResult && frameSelect.value !== "") {
    SkeletonReview.setFrame(Number(frameSelect.value));
  }
});

clearTerminalBtn.addEventListener("click", () => resetTerminal());

skeletonReviewPanel.addEventListener("skeleton-frame-change", (event) => {
  frameSelect.value = String(event.detail.frameIndex);
  if (activeLayer === "frameAnalysis") {
    renderJsonView();
  }
});

skeletonReviewPanel.addEventListener("skeleton-reanalyze-selected", (event) => {
  const frameIndices = event.detail?.frameIndices || [];
  runAnalysis({ focusFrames: frameIndices });
});

async function loadAnalyzeMeta() {
  try {
    const res = await fetch("/api/meta");
    const data = await res.json();
    const analyze = data.analyze || {};
    if (analyze.defaultGameRoot) {
      defaultGameRoot = analyze.defaultGameRoot;
      gameRootInput.placeholder = analyze.defaultGameRoot;
    }
  } catch {
    /* optional */
  }
}

SkeletonReview.init(skeletonReviewPanel);
loadAnalyzeMeta();
