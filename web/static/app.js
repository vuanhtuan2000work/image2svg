const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const fileListPanel = document.getElementById("fileListPanel");
const fileList = document.getElementById("fileList");
const fileCount = document.getElementById("fileCount");
const clearFilesBtn = document.getElementById("clearFilesBtn");
const partSelect = document.getElementById("partSelect");
const svgModeSelect = document.getElementById("svgModeSelect");
const outputTypeSelect = document.getElementById("outputTypeSelect");
const smoothingSelect = document.getElementById("smoothingSelect");
const colorRange = document.getElementById("colorRange");
const colorVal = document.getElementById("colorVal");
const sharpRange = document.getElementById("sharpRange");
const sharpVal = document.getElementById("sharpVal");
const removeBg = document.getElementById("removeBg");
const trimPad = document.getElementById("trimPad");
const exportSvgBtn = document.getElementById("exportSvgBtn");
const convertBtn = document.getElementById("convertBtn");
const downloadBtn = document.getElementById("downloadBtn");
const exportAllBtn = document.getElementById("exportAllBtn");
const previewGrid = document.getElementById("previewGrid");
const sourcePreview = document.getElementById("sourcePreview");
const sourceName = document.getElementById("sourceName");
const svgPreview = document.getElementById("svgPreview");
const statsLine = document.getElementById("statsLine");
const optimizerBadge = document.getElementById("optimizerBadge");
const toast = document.getElementById("toast");

/** @type {Array<{ id: string, file: File, previewUrl: string, status: string, result: object | null, error: string | null }>} */
let fileEntries = [];
let activeEntryId = null;
let converting = false;

function showToast(message, isError = false) {
  toast.textContent = message;
  toast.hidden = false;
  toast.classList.toggle("error", isError);
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => {
    toast.hidden = true;
  }, 2400);
}

function entryIdFor(file) {
  return `${file.name}-${file.size}-${file.lastModified}`;
}

function activeEntry() {
  return fileEntries.find((entry) => entry.id === activeEntryId) ?? null;
}

function successfulEntries() {
  return fileEntries.filter((entry) => entry.status === "done" && entry.result);
}

function extensionForResult(result) {
  const format = (result?.format || "").toLowerCase();
  const extension = (result?.extension || "").toLowerCase();
  if (extension) return extension.startsWith(".") ? extension : `.${extension}`;
  if (format === "jpg") return ".jpg";
  if (format === "jpeg") return ".jpeg";
  return format ? `.${format}` : ".bin";
}

function exportFilename(result) {
  const rawName = result?.filename || "asset";
  const cleanName = rawName.split(/[\\/]/).pop() || "asset";
  const stem = cleanName.replace(/\.[^.]+$/, "") || "asset";
  return `${stem}${extensionForResult(result)}`;
}

function isSvgOutput() {
  return outputTypeSelect.value === "svg";
}

function isVectorSvgMode() {
  return isSvgOutput() && svgModeSelect.value === "vector";
}

function applyOptionAvailability(select, allowedValues = [], disabledValues = []) {
  const allowed = new Set(allowedValues);
  const disabled = new Set(disabledValues);
  let firstEnabled = null;

  for (const option of select.options) {
    const isAllowed = allowed.size === 0 || allowed.has(option.value);
    const isDisabled = !isAllowed || disabled.has(option.value);
    option.disabled = isDisabled;
    option.hidden = false;
    if (isDisabled) {
      option.textContent = option.textContent.replace(/\s+\(Cloudflare: tắt\)$/, "");
      option.textContent = `${option.textContent} (Cloudflare: tắt)`;
    } else {
      option.textContent = option.textContent.replace(/\s+\(Cloudflare: tắt\)$/, "");
      if (!firstEnabled) firstEnabled = option.value;
    }
  }

  if (select.selectedOptions[0]?.disabled && firstEnabled) {
    select.value = firstEnabled;
  }
}

function applyRuntimeMeta(data) {
  if (Array.isArray(data.outputTypes)) {
    applyOptionAvailability(outputTypeSelect, data.outputTypes, data.disabledOutputTypes || []);
  }
  if (Array.isArray(data.svgModes)) {
    applyOptionAvailability(svgModeSelect, data.svgModes, []);
  }
  updateFormatControls();
}

function updateFormatControls() {
  const svgMode = isSvgOutput();
  const vectorMode = isVectorSvgMode();
  svgModeSelect.disabled = !svgMode;
  for (const control of [partSelect, smoothingSelect, colorRange, sharpRange]) {
    control.disabled = !vectorMode;
  }
  for (const control of [removeBg, trimPad]) {
    control.disabled = !svgMode;
  }
}

function updateActionButtons() {
  updateFormatControls();
  const hasFiles = fileEntries.length > 0;
  const active = activeEntry();
  const doneCount = successfulEntries().length;

  convertBtn.disabled = !hasFiles || converting;
  downloadBtn.disabled = !active?.result;
  exportSvgBtn.disabled = !active?.result;
  const activeFormat = active?.result?.format || outputTypeSelect.value;
  downloadBtn.textContent = active?.result ? `Tải ${activeFormat.toUpperCase()}` : "Tải file";
  exportSvgBtn.textContent = active?.result ? `Export ${activeFormat.toUpperCase()}` : "Export file";
  exportAllBtn.disabled = doneCount === 0;
  exportAllBtn.textContent =
    doneCount > 1 ? `Export tất cả (${doneCount}) ZIP` : "Export tất cả (ZIP)";
  if (!converting) {
    convertBtn.textContent =
      fileEntries.length > 1 ? `Convert (${fileEntries.length})` : "Convert";
  }
}

function formatStats(data) {
  const p = data.params || {};
  const flags = [];
  if (data.format) flags.push(`type:${data.format}`);
  if (p.svg_mode) flags.push(`svg:${p.svg_mode}`);
  if (p.source) flags.push(p.source);
  if (p.smoothing) flags.push(`mịn:${p.smoothing}`);
  if (p.color_precision) flags.push(`màu:${p.color_precision}`);
  if (p.sharpness) flags.push(`nét:${p.sharpness}`);
  if (p.remove_bg) flags.push("xóa-nền");
  if (p.remove_bg_engine) flags.push(`engine:${p.remove_bg_engine}`);
  if (p.flattened_background) flags.push(`nền:${p.flattened_background}`);
  if (p.trim) flags.push("trim");
  return `${data.filename} · ${(data.sizeBytes / 1024).toFixed(1)} KB · ${data.elapsed}s · ${data.optimizer} · ${flags.join(" · ")}`;
}

function statusLabel(status) {
  switch (status) {
    case "pending":
      return "Chờ";
    case "converting":
      return "Đang convert…";
    case "done":
      return "Xong";
    case "error":
      return "Lỗi";
    default:
      return status;
  }
}

function renderFileList() {
  fileCount.textContent = String(fileEntries.length);
  fileListPanel.hidden = fileEntries.length === 0;
  fileList.replaceChildren();

  for (const entry of fileEntries) {
    const item = document.createElement("li");
    item.className = "file-item";
    if (entry.id === activeEntryId) item.classList.add("active");
    item.dataset.id = entry.id;

    const thumb = document.createElement("img");
    thumb.className = "file-thumb";
    thumb.src = entry.previewUrl;
    thumb.alt = "";

    const meta = document.createElement("div");
    meta.className = "file-meta";

    const name = document.createElement("span");
    name.className = "file-item-name";
    name.textContent = entry.file.name;

    const status = document.createElement("span");
    status.className = `file-status status-${entry.status}`;
    status.textContent = entry.error || statusLabel(entry.status);

    meta.append(name, status);

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn small file-remove";
    removeBtn.textContent = "×";
    removeBtn.title = "Xóa ảnh";
    removeBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      removeEntry(entry.id);
    });

    item.append(thumb, meta, removeBtn);
    item.addEventListener("click", () => selectEntry(entry.id));
    fileList.append(item);
  }

  updateActionButtons();
}

function showPreview(entry) {
  if (!entry) {
    previewGrid.hidden = true;
    sourcePreview.removeAttribute("src");
    sourceName.textContent = "";
    svgPreview.replaceChildren();
    statsLine.textContent = "";
    return;
  }

  previewGrid.hidden = false;
  sourcePreview.src = entry.result?.previewDataUrl || entry.previewUrl;
  sourceName.textContent = entry.file.name;

  if (entry.result) {
    svgPreview.replaceChildren();
    if (entry.result.svg) {
      svgPreview.innerHTML = entry.result.svg;
    } else if (entry.result.dataUrl) {
      const img = document.createElement("img");
      img.src = entry.result.dataUrl;
      img.alt = entry.result.filename || "Output";
      img.addEventListener("error", () => {
        svgPreview.textContent = `Preview không hỗ trợ ${entry.result.format?.toUpperCase() || "format"} này. Vẫn có thể tải file.`;
      }, { once: true });
      svgPreview.append(img);
    }
    statsLine.textContent = formatStats(entry.result);
  } else {
    svgPreview.replaceChildren();
    statsLine.textContent = entry.error || "Chưa convert.";
  }

  updateActionButtons();
}

function selectEntry(id) {
  activeEntryId = id;
  renderFileList();
  showPreview(activeEntry());
}

function removeEntry(id) {
  const entry = fileEntries.find((item) => item.id === id);
  if (!entry) return;

  URL.revokeObjectURL(entry.previewUrl);
  fileEntries = fileEntries.filter((item) => item.id !== id);

  if (activeEntryId === id) {
    activeEntryId = fileEntries[0]?.id ?? null;
  }

  renderFileList();
  showPreview(activeEntry());
}

function clearAllFiles() {
  for (const entry of fileEntries) {
    URL.revokeObjectURL(entry.previewUrl);
  }
  fileEntries = [];
  activeEntryId = null;
  fileInput.value = "";
  renderFileList();
  showPreview(null);
}

function addFiles(files) {
  const incoming = Array.from(files || []).filter((file) =>
    file.type.startsWith("image/"),
  );
  if (!incoming.length) return;

  let added = 0;
  for (const file of incoming) {
    const id = entryIdFor(file);
    if (fileEntries.some((entry) => entry.id === id)) continue;

    fileEntries.push({
      id,
      file,
      previewUrl: URL.createObjectURL(file),
      status: "pending",
      result: null,
      error: null,
    });
    added += 1;
  }

  if (!added) {
    showToast("Ảnh đã có trong danh sách");
    return;
  }

  if (!activeEntryId) {
    activeEntryId = fileEntries[0].id;
  }

  renderFileList();
  showPreview(activeEntry());
  showToast(`Đã thêm ${added} ảnh`);
}

async function loadMeta() {
  const res = await fetch("/api/meta");
  const data = await res.json();
  optimizerBadge.textContent = data.cloudflare?.mode
    ? `optimizer: ${data.optimizer} · ${data.cloudflare.mode}`
    : `optimizer: ${data.optimizer}`;

  applyRuntimeMeta(data);

  for (const part of data.parts) {
    const opt = document.createElement("option");
    opt.value = part;
    opt.textContent = part;
    partSelect.appendChild(opt);
  }
}

function buildConvertForm(file) {
  const form = new FormData();
  form.append("file", file);
  form.append("output_type", outputTypeSelect.value);
  if (isSvgOutput()) {
    form.append("svg_mode", svgModeSelect.value);
    if (isVectorSvgMode()) {
      form.append("part", partSelect.value);
      form.append("smoothing", smoothingSelect.value);
      form.append("color_precision", colorRange.value);
      form.append("sharpness", sharpRange.value);
    }
    form.append("remove_bg", removeBg.checked ? "true" : "false");
    form.append("trim", trimPad.checked ? "true" : "false");
  }
  return form;
}

async function convertEntry(entry) {
  entry.status = "converting";
  entry.error = null;
  renderFileList();

  try {
    const res = await fetch("/api/convert", {
      method: "POST",
      body: buildConvertForm(entry.file),
    });
    const data = await res.json();
    if (!res.ok) {
      const detail = Array.isArray(data.detail)
        ? data.detail.map((item) => item.msg).join(", ")
        : data.detail;
      throw new Error(detail || "Convert thất bại");
    }

    entry.status = "done";
    entry.result = data;
  } catch (err) {
    entry.status = "error";
    entry.result = null;
    entry.error = err.message;
  }

  if (entry.id === activeEntryId) {
    showPreview(entry);
  }
  renderFileList();
}

async function convertAll() {
  if (!fileEntries.length || converting) return;

  converting = true;
  convertBtn.textContent = "Đang convert…";
  updateActionButtons();

  let done = 0;
  let failed = 0;

  for (const entry of fileEntries) {
    convertBtn.textContent = `Đang convert ${done + failed + 1}/${fileEntries.length}…`;
    await convertEntry(entry);
    if (entry.status === "done") done += 1;
    else failed += 1;
  }

  converting = false;
  convertBtn.textContent =
    fileEntries.length > 1 ? `Convert (${fileEntries.length})` : "Convert";
  updateActionButtons();

  if (failed === 0) {
    showToast(`Convert xong ${done} ảnh`);
  } else if (done === 0) {
    showToast(`Convert thất bại ${failed} ảnh`, true);
  } else {
    showToast(`Xong ${done} ảnh · lỗi ${failed} ảnh`, true);
  }
}

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});

fileInput.addEventListener("change", () => {
  if (fileInput.files?.length) addFiles(fileInput.files);
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
  if (event.dataTransfer.files?.length) addFiles(event.dataTransfer.files);
});

clearFilesBtn.addEventListener("click", clearAllFiles);
convertBtn.addEventListener("click", convertAll);

function exportFile(entry = activeEntry()) {
  if (!entry?.result) return;

  const anchor = document.createElement("a");
  if (entry.result.svg) {
    const blob = new Blob([entry.result.svg], { type: "image/svg+xml" });
    anchor.href = URL.createObjectURL(blob);
    anchor.addEventListener("click", () => {
      setTimeout(() => URL.revokeObjectURL(anchor.href), 0);
    }, { once: true });
  } else {
    anchor.href = entry.result.dataUrl;
  }
  const filename = exportFilename(entry.result);
  anchor.download = filename;
  anchor.click();
  showToast(`Đã export ${filename}`);
}

async function exportAllFiles() {
  const entries = successfulEntries();
  if (!entries.length) return;

  if (entries.length === 1) {
    exportFile(entries[0]);
    return;
  }

  exportAllBtn.disabled = true;
  exportAllBtn.textContent = "Đang tạo ZIP…";

  try {
    const res = await fetch("/api/export-zip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        files: entries.map((entry) => ({
          filename: exportFilename(entry.result),
          format: entry.result.format,
          svg: entry.result.svg,
          dataBase64: entry.result.dataBase64,
        })),
      }),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      const detail = Array.isArray(data.detail)
        ? data.detail.map((item) => item.msg).join(", ")
        : data.detail;
      throw new Error(detail || "Export ZIP thất bại");
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "image-export.zip";
    anchor.click();
    URL.revokeObjectURL(url);
    showToast(`Đã export ${entries.length} file vào ZIP`);
  } catch (err) {
    showToast(err.message, true);
  } finally {
    updateActionButtons();
  }
}

downloadBtn.addEventListener("click", exportFile);
exportSvgBtn.addEventListener("click", exportFile);
exportAllBtn.addEventListener("click", exportAllFiles);

colorRange.addEventListener("input", () => {
  colorVal.textContent = colorRange.value === "0" ? "tự động" : colorRange.value;
});
sharpRange.addEventListener("input", () => {
  sharpVal.textContent = sharpRange.value;
});
outputTypeSelect.addEventListener("change", () => {
  updateActionButtons();
  showPreview(activeEntry());
});
svgModeSelect.addEventListener("change", () => {
  updateActionButtons();
  showPreview(activeEntry());
});

loadMeta().catch((err) => showToast(err.message, true));
