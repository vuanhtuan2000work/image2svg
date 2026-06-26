const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const fileListPanel = document.getElementById("fileListPanel");
const fileList = document.getElementById("fileList");
const fileCount = document.getElementById("fileCount");
const clearFilesBtn = document.getElementById("clearFilesBtn");
const partSelect = document.getElementById("partSelect");
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

function updateActionButtons() {
  const hasFiles = fileEntries.length > 0;
  const active = activeEntry();
  const doneCount = successfulEntries().length;

  convertBtn.disabled = !hasFiles || converting;
  downloadBtn.disabled = !active?.result;
  exportSvgBtn.disabled = !active?.result;
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
  if (p.smoothing) flags.push(`mịn:${p.smoothing}`);
  if (p.color_precision) flags.push(`màu:${p.color_precision}`);
  if (p.sharpness) flags.push(`nét:${p.sharpness}`);
  if (p.remove_bg) flags.push("xóa-nền");
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
    svgPreview.innerHTML = entry.result.svg;
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
  optimizerBadge.textContent = `optimizer: ${data.optimizer}`;

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
  form.append("part", partSelect.value);
  form.append("smoothing", smoothingSelect.value);
  form.append("color_precision", colorRange.value);
  form.append("sharpness", sharpRange.value);
  form.append("remove_bg", removeBg.checked ? "true" : "false");
  form.append("trim", trimPad.checked ? "true" : "false");
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

function exportSvg() {
  const entry = activeEntry();
  if (!entry?.result) return;

  const blob = new Blob([entry.result.svg], { type: "image/svg+xml" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = entry.result.filename;
  anchor.click();
  URL.revokeObjectURL(url);
  showToast(`Đã export ${entry.result.filename}`);
}

async function exportAllSvg() {
  const entries = successfulEntries();
  if (!entries.length) return;

  if (entries.length === 1) {
    const entry = entries[0];
    const blob = new Blob([entry.result.svg], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = entry.result.filename;
    anchor.click();
    URL.revokeObjectURL(url);
    showToast(`Đã export ${entry.result.filename}`);
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
          filename: entry.result.filename,
          svg: entry.result.svg,
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
    anchor.download = "svg-export.zip";
    anchor.click();
    URL.revokeObjectURL(url);
    showToast(`Đã export ${entries.length} SVG vào ZIP`);
  } catch (err) {
    showToast(err.message, true);
  } finally {
    updateActionButtons();
  }
}

downloadBtn.addEventListener("click", exportSvg);
exportSvgBtn.addEventListener("click", exportSvg);
exportAllBtn.addEventListener("click", exportAllSvg);

colorRange.addEventListener("input", () => {
  colorVal.textContent = colorRange.value === "0" ? "tự động" : colorRange.value;
});
sharpRange.addEventListener("input", () => {
  sharpVal.textContent = sharpRange.value;
});

loadMeta().catch((err) => showToast(err.message, true));
