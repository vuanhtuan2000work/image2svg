const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const fileListPanel = document.getElementById("fileListPanel");
const fileList = document.getElementById("fileList");
const fileCount = document.getElementById("fileCount");
const clearFilesBtn = document.getElementById("clearFilesBtn");
const partSelect = document.getElementById("partSelect");
const svgModeSelect = document.getElementById("svgModeSelect");
const outputTypeSelect = document.getElementById("outputTypeSelect");
const languageSelect = document.getElementById("languageSelect");
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
let runtimeMeta = null;
let currentLang = localStorage.getItem("image2svg.lang") || "en";

const I18N = {
  en: {
    "nav.convert": "Convert",
    "hero.subtitle": "Convert images, remove backgrounds, preview instantly, export clean files",
    "language.label": "Language",
    "dropzone.aria": "Choose or drop images",
    "dropzone.choose": "Choose images",
    "dropzone.drop": "or drop them here",
    "dropzone.hint": "PNG, JPG, WebP, HEIC, TIFF · multiple files supported",
    "files.selected": "Selected images",
    "actions.clear": "Clear all",
    "actions.download": "Download file",
    "actions.exportAll": "Export all (ZIP)",
    "actions.exportAllCount": "Export all ({count}) ZIP",
    "actions.exportFile": "Export file",
    "actions.convert": "Convert",
    "actions.convertCount": "Convert ({count})",
    "actions.converting": "Converting…",
    "actions.convertingStep": "Converting {current}/{total}…",
    "actions.downloadFormat": "Download {format}",
    "actions.exportFormat": "Export {format}",
    "actions.exportingZip": "Creating ZIP…",
    "controls.part": "Part type",
    "controls.svgMode": "SVG mode",
    "controls.output": "Output format",
    "controls.smoothing": "Edge smoothing",
    "controls.color": "Color precision",
    "controls.sharpness": "Sharpness",
    "options.svgEmbedded": "Preserve image/colors",
    "options.svgVector": "Vector path (vtracer)",
    "options.smoothingNone": "none — direct conversion (fast)",
    "options.smoothingLow": "low — upscale 2x",
    "options.smoothingMedium": "medium — upscale 3x (recommended)",
    "options.smoothingHigh": "high — upscale 4x (smoothest, slower)",
    "options.disabledSuffix": "(Cloudflare: disabled)",
    "values.auto": "auto",
    "toggles.removeBg": "Remove background (transparent)",
    "toggles.trim": "Trim padding (fit content)",
    "preview.source": "Source image",
    "status.pending": "Queued",
    "status.converting": "Converting…",
    "status.done": "Done",
    "status.error": "Error",
    "toast.duplicate": "Image is already in the list",
    "toast.added": "Added {count} image(s)",
    "toast.convertDone": "Converted {count} image(s)",
    "toast.convertFailed": "Conversion failed for {count} image(s)",
    "toast.convertMixed": "Done {done} image(s) · failed {failed}",
    "toast.exported": "Exported {filename}",
    "toast.exportedZip": "Exported {count} files into ZIP",
    "errors.convertFailed": "Conversion failed",
    "errors.zipFailed": "ZIP export failed",
    "preview.unsupported": "{format} preview is not supported. You can still download the file.",
    "preview.notConverted": "Not converted yet.",
    "stats.type": "type",
    "stats.svg": "svg",
    "stats.smoothing": "smooth",
    "stats.color": "color",
    "stats.sharpness": "sharp",
    "stats.removeBg": "remove-bg",
    "stats.engine": "engine",
    "stats.background": "background",
    "stats.trim": "trim",
  },
  vi: {
    "nav.convert": "Convert",
    "hero.subtitle": "Chuyển đổi ảnh, xóa nền, preview ngay, export file sạch",
    "language.label": "Ngôn ngữ",
    "dropzone.aria": "Chọn hoặc kéo thả ảnh",
    "dropzone.choose": "Chọn ảnh",
    "dropzone.drop": "hoặc kéo thả vào đây",
    "dropzone.hint": "PNG, JPG, WebP, HEIC, TIFF · chọn nhiều ảnh cùng lúc",
    "files.selected": "Ảnh đã chọn",
    "actions.clear": "Xóa tất cả",
    "actions.download": "Tải file",
    "actions.exportAll": "Export tất cả (ZIP)",
    "actions.exportAllCount": "Export tất cả ({count}) ZIP",
    "actions.exportFile": "Export file",
    "actions.convert": "Convert",
    "actions.convertCount": "Convert ({count})",
    "actions.converting": "Đang convert…",
    "actions.convertingStep": "Đang convert {current}/{total}…",
    "actions.downloadFormat": "Tải {format}",
    "actions.exportFormat": "Export {format}",
    "actions.exportingZip": "Đang tạo ZIP…",
    "controls.part": "Loại part",
    "controls.svgMode": "Kiểu SVG",
    "controls.output": "Định dạng output",
    "controls.smoothing": "Độ mịn rìa",
    "controls.color": "Màu sắc chuẩn xác",
    "controls.sharpness": "Độ rõ nét",
    "options.svgEmbedded": "Giữ nguyên ảnh/màu",
    "options.svgVector": "Vector path (vtracer)",
    "options.smoothingNone": "none — convert thẳng (nhanh)",
    "options.smoothingLow": "low — upscale 2x",
    "options.smoothingMedium": "medium — upscale 3x (khuyên dùng)",
    "options.smoothingHigh": "high — upscale 4x (mịn nhất, chậm)",
    "options.disabledSuffix": "(Cloudflare: tắt)",
    "values.auto": "tự động",
    "toggles.removeBg": "Xóa nền (trong suốt)",
    "toggles.trim": "Cắt padding (ôm sát nội dung)",
    "preview.source": "Ảnh gốc",
    "status.pending": "Chờ",
    "status.converting": "Đang convert…",
    "status.done": "Xong",
    "status.error": "Lỗi",
    "toast.duplicate": "Ảnh đã có trong danh sách",
    "toast.added": "Đã thêm {count} ảnh",
    "toast.convertDone": "Convert xong {count} ảnh",
    "toast.convertFailed": "Convert thất bại {count} ảnh",
    "toast.convertMixed": "Xong {done} ảnh · lỗi {failed}",
    "toast.exported": "Đã export {filename}",
    "toast.exportedZip": "Đã export {count} file vào ZIP",
    "errors.convertFailed": "Convert thất bại",
    "errors.zipFailed": "Export ZIP thất bại",
    "preview.unsupported": "Preview không hỗ trợ {format}. Vẫn có thể tải file.",
    "preview.notConverted": "Chưa convert.",
    "stats.type": "type",
    "stats.svg": "svg",
    "stats.smoothing": "mịn",
    "stats.color": "màu",
    "stats.sharpness": "nét",
    "stats.removeBg": "xóa-nền",
    "stats.engine": "engine",
    "stats.background": "nền",
    "stats.trim": "trim",
  },
};

function t(key, vars = {}) {
  const template = I18N[currentLang]?.[key] || I18N.en[key] || key;
  return template.replace(/\{(\w+)\}/g, (_match, name) => vars[name] ?? "");
}

function applyTranslations() {
  document.documentElement.lang = currentLang;
  for (const node of document.querySelectorAll("[data-i18n]")) {
    node.textContent = t(node.dataset.i18n);
  }
  for (const node of document.querySelectorAll("[data-i18n-aria-label]")) {
    node.setAttribute("aria-label", t(node.dataset.i18nAriaLabel));
  }
  for (const node of document.querySelectorAll("[data-i18n-alt]")) {
    node.setAttribute("alt", t(node.dataset.i18nAlt));
  }
  colorRange.dispatchEvent(new Event("input"));
  if (runtimeMeta) applyRuntimeMeta(runtimeMeta);
  renderFileList();
  updateActionButtons();
}

function setLanguage(lang) {
  currentLang = I18N[lang] ? lang : "en";
  localStorage.setItem("image2svg.lang", currentLang);
  languageSelect.value = currentLang;
  applyTranslations();
}

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

function base64ToBytes(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

function blobForResult(result) {
  if (result?.svg) {
    return new Blob([result.svg], { type: result.mime || "image/svg+xml" });
  }
  if (result?.dataBase64) {
    return new Blob([base64ToBytes(result.dataBase64)], {
      type: result.mime || "application/octet-stream",
    });
  }
  return null;
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
    const baseText = option.dataset.i18n ? t(option.dataset.i18n) : (option.dataset.baseText || option.textContent);
    option.dataset.baseText = baseText;
    option.disabled = isDisabled;
    option.hidden = false;
    option.textContent = isDisabled ? `${baseText} ${t("options.disabledSuffix")}` : baseText;
    if (!isDisabled && !firstEnabled) firstEnabled = option.value;
  }

  if (select.selectedOptions[0]?.disabled && firstEnabled) {
    select.value = firstEnabled;
  }
}

function applyRuntimeMeta(data) {
  runtimeMeta = data;
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
  for (const control of [partSelect, colorRange]) {
    control.disabled = !vectorMode;
  }
  smoothingSelect.disabled = false;
  sharpRange.disabled = false;
  removeBg.disabled = false;
  trimPad.disabled = false;
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
  downloadBtn.textContent = active?.result
    ? t("actions.downloadFormat", { format: activeFormat.toUpperCase() })
    : t("actions.download");
  exportSvgBtn.textContent = active?.result
    ? t("actions.exportFormat", { format: activeFormat.toUpperCase() })
    : t("actions.exportFile");
  exportAllBtn.disabled = doneCount === 0;
  exportAllBtn.textContent =
    doneCount > 1 ? t("actions.exportAllCount", { count: doneCount }) : t("actions.exportAll");
  if (!converting) {
    convertBtn.textContent =
      fileEntries.length > 1 ? t("actions.convertCount", { count: fileEntries.length }) : t("actions.convert");
  }
}

function formatStats(data) {
  const p = data.params || {};
  const flags = [];
  if (data.format) flags.push(`${t("stats.type")}:${data.format}`);
  if (p.svg_mode) flags.push(`${t("stats.svg")}:${p.svg_mode}`);
  if (p.source) flags.push(p.source);
  if (p.smoothing) flags.push(`${t("stats.smoothing")}:${p.smoothing}`);
  if (p.color_precision) flags.push(`${t("stats.color")}:${p.color_precision}`);
  if (p.sharpness) flags.push(`${t("stats.sharpness")}:${p.sharpness}`);
  if (p.remove_bg) flags.push(t("stats.removeBg"));
  if (p.remove_bg_engine) flags.push(`${t("stats.engine")}:${p.remove_bg_engine}`);
  if (p.flattened_background) flags.push(`${t("stats.background")}:${p.flattened_background}`);
  if (p.trim) flags.push(t("stats.trim"));
  return `${data.filename} · ${(data.sizeBytes / 1024).toFixed(1)} KB · ${data.elapsed}s · ${data.optimizer} · ${flags.join(" · ")}`;
}

function statusLabel(status) {
  switch (status) {
    case "pending":
      return t("status.pending");
    case "converting":
      return t("status.converting");
    case "done":
      return t("status.done");
    case "error":
      return t("status.error");
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
    removeBtn.title = t("actions.clear");
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
        svgPreview.textContent = t("preview.unsupported", {
          format: entry.result.format?.toUpperCase() || "format",
        });
      }, { once: true });
      svgPreview.append(img);
    }
    statsLine.textContent = formatStats(entry.result);
  } else {
    svgPreview.replaceChildren();
    statsLine.textContent = entry.error || t("preview.notConverted");
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
    showToast(t("toast.duplicate"));
    return;
  }

  if (!activeEntryId) {
    activeEntryId = fileEntries[0].id;
  }

  renderFileList();
  showPreview(activeEntry());
  showToast(t("toast.added", { count: added }));
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
  form.append("smoothing", smoothingSelect.value);
  form.append("sharpness", sharpRange.value);
  form.append("remove_bg", removeBg.checked ? "true" : "false");
  form.append("trim", trimPad.checked ? "true" : "false");
  if (isSvgOutput()) {
    form.append("svg_mode", svgModeSelect.value);
    if (isVectorSvgMode()) {
      form.append("part", partSelect.value);
      form.append("color_precision", colorRange.value);
    }
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
      throw new Error(detail || t("errors.convertFailed"));
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
  convertBtn.textContent = t("actions.converting");
  updateActionButtons();

  let done = 0;
  let failed = 0;

  for (const entry of fileEntries) {
    convertBtn.textContent = t("actions.convertingStep", {
      current: done + failed + 1,
      total: fileEntries.length,
    });
    await convertEntry(entry);
    if (entry.status === "done") done += 1;
    else failed += 1;
  }

  converting = false;
  convertBtn.textContent =
    fileEntries.length > 1 ? t("actions.convertCount", { count: fileEntries.length }) : t("actions.convert");
  updateActionButtons();

  if (failed === 0) {
    showToast(t("toast.convertDone", { count: done }));
  } else if (done === 0) {
    showToast(t("toast.convertFailed", { count: failed }), true);
  } else {
    showToast(t("toast.convertMixed", { done, failed }), true);
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

  const blob = blobForResult(entry.result);
  if (!blob) {
    showToast(t("errors.convertFailed"), true);
    return;
  }

  const anchor = document.createElement("a");
  const url = URL.createObjectURL(blob);
  const filename = exportFilename(entry.result);
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  showToast(t("toast.exported", { filename }));
}

async function exportAllFiles() {
  const entries = successfulEntries();
  if (!entries.length) return;

  if (entries.length === 1) {
    exportFile(entries[0]);
    return;
  }

  exportAllBtn.disabled = true;
  exportAllBtn.textContent = t("actions.exportingZip");

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
      throw new Error(detail || t("errors.zipFailed"));
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "image-export.zip";
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    showToast(t("toast.exportedZip", { count: entries.length }));
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
  colorVal.textContent = colorRange.value === "0" ? t("values.auto") : colorRange.value;
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
languageSelect.addEventListener("change", () => setLanguage(languageSelect.value));

setLanguage(currentLang);
loadMeta().catch((err) => showToast(err.message, true));
