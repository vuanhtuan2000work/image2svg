import { strToU8, zipSync } from "fflate";
import * as UPNG from "upng-js";

const OUTPUT_FORMATS = ["jpg", "jpeg", "png", "webp", "avif", "svg"];
const DISABLED_OUTPUT_FORMATS = ["gif", "bmp", "tiff", "heic"];
const SVG_MODES = ["embedded"];
const SMOOTHING_LEVELS = ["none", "low", "medium", "high"];
const NO_ALPHA_OUTPUTS = new Set(["jpg", "jpeg"]);

const MIME_BY_FORMAT = {
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
  avif: "image/avif",
  svg: "image/svg+xml",
};

const IMAGE_OUTPUT_BY_FORMAT = {
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
  avif: "image/avif",
};

function json(data, init = {}) {
  return new Response(JSON.stringify(data), {
    ...init,
    headers: {
      "content-type": "application/json; charset=utf-8",
      ...(init.headers || {}),
    },
  });
}

function error(status, detail) {
  return json({ detail }, { status });
}

function basename(filename) {
  const clean = String(filename || "asset").split(/[\\/]/).pop() || "asset";
  return clean.replace(/\.[^.]+$/, "") || "asset";
}

function extensionFor(format) {
  return format === "jpeg" ? "jpeg" : format;
}

function filenameFor(originalName, format) {
  return `${basename(originalName)}.${extensionFor(format)}`;
}

function bytesToBase64(bytes) {
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}

function base64ToBytes(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

function escapeAttr(value) {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

function decodePng(pngBytes) {
  const decoded = UPNG.decode(pngBytes.buffer.slice(pngBytes.byteOffset, pngBytes.byteOffset + pngBytes.byteLength));
  const rgba = new Uint8Array(UPNG.toRGBA8(decoded)[0]);
  return { width: decoded.width, height: decoded.height, rgba };
}

function encodePng(width, height, rgba) {
  return new Uint8Array(UPNG.encode([rgba.buffer], width, height, 0));
}

function trimPngToAlpha(pngBytes) {
  const { width, height, rgba } = decodePng(pngBytes);
  let minX = width;
  let minY = height;
  let maxX = -1;
  let maxY = -1;

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const alpha = rgba[(y * width + x) * 4 + 3];
      if (alpha > 0) {
        if (x < minX) minX = x;
        if (y < minY) minY = y;
        if (x > maxX) maxX = x;
        if (y > maxY) maxY = y;
      }
    }
  }

  if (maxX < minX || maxY < minY) {
    return { bytes: pngBytes, width, height, trimmed: false };
  }

  if (minX === 0 && minY === 0 && maxX === width - 1 && maxY === height - 1) {
    return { bytes: pngBytes, width, height, trimmed: false };
  }

  const outWidth = maxX - minX + 1;
  const outHeight = maxY - minY + 1;
  const out = new Uint8Array(outWidth * outHeight * 4);
  for (let y = 0; y < outHeight; y += 1) {
    const srcStart = ((minY + y) * width + minX) * 4;
    const dstStart = y * outWidth * 4;
    out.set(rgba.subarray(srcStart, srcStart + outWidth * 4), dstStart);
  }

  return {
    bytes: encodePng(outWidth, outHeight, out),
    width: outWidth,
    height: outHeight,
    trimmed: true,
  };
}

async function transformImage(env, source, { outputFormat, removeBg = false, sharpness = 0 }) {
  const imageFormat = IMAGE_OUTPUT_BY_FORMAT[outputFormat];
  if (!imageFormat) {
    throw new Error(`Định dạng output không hỗ trợ trên Cloudflare: ${outputFormat}`);
  }

  let pipeline = env.IMAGES.input(source.stream());
  if (removeBg) {
    pipeline = pipeline.transform({ segment: "foreground" });
  }
  if (sharpness > 0) {
    pipeline = pipeline.transform({ sharpen: Math.max(0, Math.min(10, sharpness / 25)) });
  }

  const outputOptions = { format: imageFormat };
  if (outputFormat !== "png") {
    outputOptions.quality = 95;
  }
  const output = await pipeline.output(outputOptions);
  const response = output.response();
  if (!response.ok) {
    throw new Error(`Cloudflare Images xử lý thất bại (${response.status})`);
  }
  return new Uint8Array(await response.arrayBuffer());
}

function svgEmbedPng(pngBytes, width, height) {
  const href = bytesToBase64(pngBytes);
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}">` +
    `<image href="data:image/png;base64,${escapeAttr(href)}" width="${width}" height="${height}" preserveAspectRatio="xMidYMid meet"/>` +
    "</svg>"
  );
}

async function handleMeta() {
  return json({
    parts: ["default"],
    optimizer: "cloudflare-images",
    outputTypes: OUTPUT_FORMATS,
    disabledOutputTypes: DISABLED_OUTPUT_FORMATS,
    svgModes: SVG_MODES,
    defaultRecipe: {},
    smoothingLevels: SMOOTHING_LEVELS,
    defaultSmoothing: "medium",
    cloudflare: {
      mode: "worker-native",
      vectorSvg: false,
      removeBackground: "cloudflare-images:segment=foreground",
      disabledOutputTypes: DISABLED_OUTPUT_FORMATS,
    },
  });
}

async function handleConvert(request, env) {
  const t0 = performance.now();
  const form = await request.formData();
  const file = form.get("file");
  if (!(file instanceof File) || file.size === 0) {
    return error(400, "File rỗng.");
  }

  const outputType = String(form.get("output_type") || "svg").toLowerCase();
  if (DISABLED_OUTPUT_FORMATS.includes(outputType)) {
    return error(400, `Định dạng ${outputType.toUpperCase()} không hỗ trợ trên Cloudflare mode.`);
  }
  if (!OUTPUT_FORMATS.includes(outputType)) {
    return error(400, `Định dạng output không hỗ trợ: ${outputType}`);
  }

  const svgMode = String(form.get("svg_mode") || "embedded");
  const smoothing = String(form.get("smoothing") || "medium");
  const sharpness = Math.max(0, Math.min(250, Number(form.get("sharpness") || 0)));
  const removeBg = String(form.get("remove_bg") || "false") === "true";
  const trim = String(form.get("trim") || "false") === "true";
  if (outputType === "svg" && svgMode !== "embedded") {
    return error(400, "Cloudflare mode chỉ hỗ trợ SVG embedded; vector/vtracer là local-only.");
  }

  if (outputType === "svg") {
    let pngBytes = await transformImage(env, file, { outputFormat: "png", removeBg, sharpness });
    let { width, height } = decodePng(pngBytes);
    let trimmed = false;
    if (trim) {
      const result = trimPngToAlpha(pngBytes);
      pngBytes = result.bytes;
      width = result.width;
      height = result.height;
      trimmed = result.trimmed;
    }

    const svg = svgEmbedPng(pngBytes, width, height);
    return json({
      filename: filenameFor(file.name, "svg"),
      extension: "svg",
      format: "svg",
      svg,
      params: {
        svg_mode: "embedded",
        source: "cloudflare-images",
        smoothing,
        sharpness,
        remove_bg: removeBg,
        remove_bg_engine: removeBg ? "cloudflare-images:segment=foreground" : undefined,
        trim,
        trim_applied: trimmed,
      },
      optimizer: "cloudflare-images",
      elapsed: Number(((performance.now() - t0) / 1000).toFixed(2)),
      sizeBytes: strToU8(svg).length,
    });
  }

  const outputFormat = outputType === "jpg" ? "jpg" : outputType;
  let bytes;
  let trimApplied = false;
  if (trim) {
    const pngBytes = await transformImage(env, file, { outputFormat: "png", removeBg, sharpness });
    const result = trimPngToAlpha(pngBytes);
    trimApplied = result.trimmed;
    if (outputFormat === "png") {
      bytes = result.bytes;
    } else {
      bytes = await transformImage(env, new Blob([result.bytes], { type: "image/png" }), {
        outputFormat,
        removeBg: false,
        sharpness: 0,
      });
    }
  } else {
    bytes = await transformImage(env, file, { outputFormat, removeBg, sharpness });
  }
  const dataBase64 = bytesToBase64(bytes);
  const mime = MIME_BY_FORMAT[outputType];
  const params = {
    format: outputType,
    source: "cloudflare-images",
    smoothing,
    sharpness,
    remove_bg: removeBg,
    trim,
    trim_applied: trimApplied,
  };
  if (removeBg) {
    params.remove_bg_engine = "cloudflare-images:segment=foreground";
  }
  if (NO_ALPHA_OUTPUTS.has(outputType)) {
    params.flattened_background = "cloudflare-default";
  }

  return json({
    filename: filenameFor(file.name, outputType),
    extension: extensionFor(outputType),
    format: outputType,
    mime,
    dataBase64,
    dataUrl: `data:${mime};base64,${dataBase64}`,
    params,
    optimizer: "cloudflare-images",
    elapsed: Number(((performance.now() - t0) / 1000).toFixed(2)),
    sizeBytes: bytes.byteLength,
  });
}

async function handleExportZip(request) {
  const payload = await request.json();
  if (!payload?.files?.length) {
    return error(400, "Không có file để export.");
  }

  const used = new Map();
  const zipEntries = {};
  for (const item of payload.files) {
    const format = String(item.format || (item.svg ? "svg" : "bin")).toLowerCase();
    const name = uniqueName(filenameFor(item.filename, format), used);
    if (item.svg) {
      zipEntries[name] = strToU8(item.svg);
    } else if (item.dataBase64) {
      zipEntries[name] = base64ToBytes(item.dataBase64);
    } else {
      return error(400, `File thiếu dữ liệu: ${item.filename}`);
    }
  }

  const zipped = zipSync(zipEntries, { level: 6 });
  return new Response(zipped, {
    headers: {
      "content-type": "application/zip",
      "content-disposition": 'attachment; filename="image-export.zip"',
    },
  });
}

function uniqueName(filename, used) {
  const clean = filename.split(/[\\/]/).pop() || "asset.bin";
  const dot = clean.lastIndexOf(".");
  const stem = dot > 0 ? clean.slice(0, dot) : clean;
  const ext = dot > 0 ? clean.slice(dot) : "";
  const count = used.get(clean) || 0;
  used.set(clean, count + 1);
  if (count === 0) return clean;
  return `${stem}-${count + 1}${ext}`;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      if (url.pathname === "/api/meta") return handleMeta();
      if (url.pathname === "/api/convert" && request.method === "POST") return handleConvert(request, env);
      if (url.pathname === "/api/export-zip" && request.method === "POST") return handleExportZip(request);
      if (url.pathname.startsWith("/api/")) return error(404, "API này là local-only trên Cloudflare mode.");
      return env.ASSETS.fetch(request);
    } catch (err) {
      return error(500, err?.message || "Cloudflare Worker lỗi.");
    }
  },
};
