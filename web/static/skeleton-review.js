/**
 * Skeleton Review Preview — per-frame grid with overlay (does not modify source SVG).
 */

const LANDMARK_KEYS = [
  "bodyCenter",
  "headCenter",
  "neck",
  "leftEye",
  "rightEye",
  "nose",
  "muzzleCenter",
  "leftEarTip",
  "rightEarTip",
  "leftEarBase",
  "rightEarBase",
  "tailRoot",
  "tailMid",
  "tailTip",
  "frontLeftShoulder",
  "frontRightShoulder",
  "backLeftHip",
  "backRightHip",
  "frontLeftPaw",
  "frontRightPaw",
  "backLeftPaw",
  "backRightPaw",
];

const PART_ZONE_KEYS = [
  "headBase",
  "bodySet",
  "earSet",
  "eyeSet",
  "faceSet",
  "tailSet",
  "frontLegSet",
  "backLegSet",
];

const DEFAULT_TOGGLES = {
  skeleton: true,
  landmarks: true,
  mlLandmarks: true,
  gameRect: true,
  coreBodyBBox: false,
  frameBBox: false,
  contentBBox: true,
  silhouetteBBox: false,
  partZones: false,
  confidenceLabels: true,
};

const STRIP_PREVIEW_MAX_W = 960;
const STRIP_PREVIEW_MAX_H = 320;
const GAME_RECT_COLORS = ["#7cffb2", "#56d4ff", "#ffd56a", "#c792ff", "#ff9f7a", "#9fd4ff"];

const REVIEW_STATUSES = [
  "Not Reviewed",
  "Needs Review",
  "Auto Accepted",
  "Manually Corrected",
  "Rejected",
];

const FRAME_CARD_MAX_W = 520;
const FRAME_CARD_MAX_H = 420;

function toFrameLocalPoint(point, frame) {
  const frameBBox = frame.bounds.frameBBox;
  const coreBodyBBox = frame.bounds.coreBodyBBox;
  const coord = point.coordinate || inferCoordinate(point);

  let x = point.x;
  let y = point.y;

  if (coord === "coreLocal" && coreBodyBBox) {
    x = coreBodyBBox.x + point.x * coreBodyBBox.w - frameBBox.x;
    y = coreBodyBBox.y + point.y * coreBodyBBox.h - frameBBox.y;
  } else if (coord === "globalSvg") {
    x = point.x - frameBBox.x;
    y = point.y - frameBBox.y;
  } else if (coreBodyBBox && point.x <= 1.05 && point.y <= 1.05 && point.x >= 0 && point.y >= 0) {
    x = coreBodyBBox.x + point.x * coreBodyBBox.w - frameBBox.x;
    y = coreBodyBBox.y + point.y * coreBodyBBox.h - frameBBox.y;
  }

  return { x, y };
}

function inferCoordinate(point) {
  if (point.coordinate) return point.coordinate;
  if (point.x <= 1.05 && point.y <= 1.05 && point.x >= -0.05 && point.y >= -0.05) {
    return "coreLocal";
  }
  return "globalSvg";
}

function toFrameLocalBBox(bbox, frame, coordinate = "globalSvg") {
  const frameBBox = frame.bounds.frameBBox;
  const coreBodyBBox = frame.bounds.coreBodyBBox;

  if (coordinate === "coreLocal" && coreBodyBBox) {
    return {
      x: coreBodyBBox.x + bbox.x * coreBodyBBox.w - frameBBox.x,
      y: coreBodyBBox.y + bbox.y * coreBodyBBox.h - frameBBox.y,
      w: bbox.w * coreBodyBBox.w,
      h: bbox.h * coreBodyBBox.h,
    };
  }

  return {
    x: bbox.x - frameBBox.x,
    y: bbox.y - frameBBox.y,
    w: bbox.w,
    h: bbox.h,
  };
}

function toOverlayPoint(point, frame) {
  return toFrameLocalPoint(point, frame);
}

function boneTip(bone, frame) {
  if (bone.tip) {
    return toOverlayPoint({ ...bone.tip, coordinate: bone.tip.coordinate || "coreLocal" }, frame);
  }
  const root = toOverlayPoint({ ...bone.root, coordinate: bone.root.coordinate || "coreLocal" }, frame);
  const angle = ((bone.angle ?? 0) * Math.PI) / 180;
  const core = frame.bounds.coreBodyBBox || frame.bounds.contentBBox || frame.bounds.frameBBox;
  const length = (bone.length ?? 0.12) * Math.max(core.w, core.h);
  return {
    x: root.x + Math.cos(angle) * length,
    y: root.y + Math.sin(angle) * length,
  };
}

function nsEl(tag, attrs = {}) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attrs)) {
    el.setAttribute(key, String(value));
  }
  return el;
}

function computeFrameScale(frameBBox) {
  return Math.min(FRAME_CARD_MAX_W / frameBBox.w, FRAME_CARD_MAX_H / frameBBox.h, 2.5);
}

function renderSkeletonForFrame(svg, frame, options, visualScale = 1) {
  const bones = frame.skeleton?.bones;
  if (!bones || !options.skeleton) return;

  const wrapper = nsEl("g", { class: "current-skeleton-layer" });
  svg.appendChild(wrapper);

  const strokeWidth = Math.max(2.5, 3 * visualScale);
  const jointR = Math.max(4, 3.5 * visualScale);

  for (const bone of Object.values(bones)) {
    const root = toOverlayPoint({ ...bone.root, coordinate: bone.root.coordinate || "coreLocal" }, frame);
    const tip = boneTip(bone, frame);
    const confidence = bone.confidence ?? 0.5;

    wrapper.appendChild(
      nsEl("line", {
        x1: root.x,
        y1: root.y,
        x2: tip.x,
        y2: tip.y,
        stroke: "#56d4ff",
        "stroke-width": strokeWidth,
        "stroke-linecap": "round",
        "stroke-dasharray": confidence < 0.6 ? "8 5" : undefined,
        opacity: Math.max(0.35, confidence),
      }),
    );
    wrapper.appendChild(
      nsEl("circle", {
        cx: root.x,
        cy: root.y,
        r: jointR,
        fill: "#56d4ff",
        opacity: Math.max(0.45, confidence),
      }),
    );
    if (options.confidenceLabels) {
      const label = nsEl("text", {
        x: root.x + jointR + 2,
        y: root.y - jointR,
        fill: "#b8ecff",
        "font-size": Math.max(11, 10 * visualScale),
      });
      label.textContent = `${bone.name} ${Math.round(confidence * 100)}%`;
      wrapper.appendChild(label);
    }
  }
}

function renderLandmarkOverlay(svg, frame, options, visualScale = 1) {
  const landmarks = frame.landmarks;
  if (!landmarks || !options.landmarks) return;

  const group = nsEl("g", { class: "landmark-overlay" });
  const pointR = Math.max(5, 4 * visualScale);

  for (const key of LANDMARK_KEYS) {
    const raw = landmarks[key];
    if (!raw || typeof raw !== "object" || raw.x == null || raw.y == null) continue;

    const point = toOverlayPoint(raw, frame);
    const confidence = raw.confidence ?? 0.5;
    let stroke = "#ffd56a";
    let fill = "#ffd56a";
    let dash;
    let opacity = 0.95;

    if (confidence >= 0.8) {
      opacity = 1;
    } else if (confidence >= 0.5) {
      opacity = 0.7;
    } else {
      stroke = "#ff7b7b";
      fill = "transparent";
      dash = "3 2";
    }

    group.appendChild(
      nsEl("circle", {
        cx: point.x,
        cy: point.y,
        r: pointR,
        fill,
        stroke,
        "stroke-width": Math.max(1.5, visualScale),
        "stroke-dasharray": dash,
        opacity,
      }),
    );

    if (options.confidenceLabels) {
      const label = nsEl("text", {
        x: point.x + pointR + 2,
        y: point.y + 4,
        fill: "#ffe9a8",
        "font-size": Math.max(10, 9 * visualScale),
      });
      label.textContent = key;
      group.appendChild(label);
    }
  }

  svg.appendChild(group);
}

function renderBBoxOverlay(svg, frame, options, visualScale = 1) {
  const group = nsEl("g", { class: "bbox-overlay" });
  const strokeWidth = Math.max(1.5, 1.5 * visualScale);
  const specs = [
    { key: "frameBBox", enabled: options.frameBBox, stroke: "#7c9cff", dash: "8 4" },
    { key: "contentBBox", enabled: options.contentBBox, stroke: "#56d4a0", dash: undefined },
    { key: "silhouetteBBox", enabled: options.silhouetteBBox, stroke: "#c8a0ff", dash: "4 3" },
    { key: "coreBodyBBox", enabled: options.coreBodyBBox, stroke: "#ff9f43", dash: undefined },
  ];

  for (const spec of specs) {
    if (!spec.enabled) continue;
    const bbox = frame.bounds[spec.key];
    if (!bbox) continue;
    const local = toFrameLocalBBox(bbox, frame, "globalSvg");
    group.appendChild(
      nsEl("rect", {
        x: local.x,
        y: local.y,
        width: local.w,
        height: local.h,
        fill: "none",
        stroke: spec.stroke,
        "stroke-width": strokeWidth,
        "stroke-dasharray": spec.dash,
        opacity: 0.9,
      }),
    );
  }

  if (group.childNodes.length) svg.appendChild(group);
}

function renderPartZoneOverlay(svg, frame, options) {
  if (!options.partZones) return;
  const zones = frame.partZones?.zones;
  if (!zones) return;

  const colors = {
    headBase: "rgba(124,156,255,0.18)",
    bodySet: "rgba(86,212,160,0.16)",
    earSet: "rgba(200,160,255,0.16)",
    eyeSet: "rgba(86,212,255,0.22)",
    faceSet: "rgba(255,180,120,0.16)",
    tailSet: "rgba(255,123,123,0.16)",
    frontLegSet: "rgba(255,220,120,0.14)",
    backLegSet: "rgba(180,255,120,0.14)",
  };

  const group = nsEl("g", { class: "part-zone-overlay" });
  for (const key of PART_ZONE_KEYS) {
    const zone = zones[key];
    if (!zone?.bbox) continue;
    const local = toFrameLocalBBox(zone.bbox, frame, "coreLocal");
    group.appendChild(
      nsEl("rect", {
        x: local.x,
        y: local.y,
        width: local.w,
        height: local.h,
        fill: colors[key] || "rgba(255,255,255,0.08)",
        stroke: "rgba(255,255,255,0.25)",
        "stroke-width": 1,
      }),
    );
  }
  svg.appendChild(group);
}

function getGameFrameEntry(gameManifest, frameIndex) {
  const frames = gameManifest?.animations?.run?.frames;
  if (!Array.isArray(frames)) return null;
  return frames.find((item) => {
    const match = String(item.frame || "").match(/(\d+)/);
    return match ? Number(match[1]) === frameIndex : false;
  }) || frames[frameIndex] || null;
}

function gameRectToViewBox(rect) {
  if (!rect) return null;
  return {
    x: Number(rect.x) || 0,
    y: Number(rect.y) || 0,
    w: Number(rect.width ?? rect.w) || 0,
    h: Number(rect.height ?? rect.h) || 0,
  };
}

function parseSvgViewBox(svgSource) {
  const doc = new DOMParser().parseFromString(svgSource, "image/svg+xml");
  const root = doc.documentElement;
  if (root.tagName?.toLowerCase() !== "svg") return null;
  const vb = root.getAttribute("viewBox");
  if (vb) {
    const parts = vb.trim().split(/[\s,]+/).map(Number);
    if (parts.length >= 4) return { x: parts[0], y: parts[1], w: parts[2], h: parts[3] };
  }
  const w = Number(root.getAttribute("width"));
  const h = Number(root.getAttribute("height"));
  if (w && h) return { x: 0, y: 0, w, h };
  return null;
}

function renderGameRectOverlay(svg, frame, gameManifest, options, visualScale = 1) {
  if (!options.gameRect || !gameManifest) return;
  const entry = getGameFrameEntry(gameManifest, frame.frameIndex);
  if (!entry) return;

  const rect = gameRectToViewBox(entry.contentRect || entry.rect);
  if (!rect) return;

  const local = toFrameLocalBBox(rect, frame, "globalSvg");
  const color = GAME_RECT_COLORS[frame.frameIndex % GAME_RECT_COLORS.length];
  const group = nsEl("g", { class: "game-rect-overlay" });
  group.appendChild(
    nsEl("rect", {
      x: local.x,
      y: local.y,
      width: local.w,
      height: local.h,
      fill: `${color}22`,
      stroke: color,
      "stroke-width": Math.max(2, 2 * visualScale),
      "stroke-dasharray": "6 4",
    }),
  );
  if (options.confidenceLabels) {
    const label = nsEl("text", {
      x: local.x + 4,
      y: local.y + 14,
      fill: color,
      "font-size": Math.max(10, 9 * visualScale),
    });
    label.textContent = `Phaser ${Math.round(rect.w)}×${Math.round(rect.h)}`;
    group.appendChild(label);
  }
  svg.appendChild(group);
}

function renderMlLandmarkOverlay(svg, frame, options, visualScale = 1) {
  const ml = frame.mlLandmarks;
  if (!options.mlLandmarks || !ml || ml.status !== "ok") return;

  const group = nsEl("g", { class: "ml-landmark-overlay" });
  const pointR = Math.max(6, 5 * visualScale);

  for (const kp of ml.keypoints || []) {
    if (kp.x == null || kp.y == null) continue;
    const point = toOverlayPoint({ x: kp.x, y: kp.y, coordinate: "globalSvg" }, frame);
    group.appendChild(
      nsEl("circle", {
        cx: point.x,
        cy: point.y,
        r: pointR,
        fill: "transparent",
        stroke: "#c792ff",
        "stroke-width": Math.max(2, 1.5 * visualScale),
        "stroke-dasharray": "4 3",
        opacity: Math.max(0.5, kp.confidence ?? 0.5),
      }),
    );
    if (options.confidenceLabels) {
      const label = nsEl("text", {
        x: point.x + pointR + 2,
        y: point.y + 4,
        fill: "#e2c4ff",
        "font-size": Math.max(10, 9 * visualScale),
      });
      label.textContent = kp.name || "ml";
      group.appendChild(label);
    }
  }

  svg.appendChild(group);
}

function renderFrameOverlays(svg, frame, options, visualScale, gameManifest) {
  svg.replaceChildren();
  renderPartZoneOverlay(svg, frame, options);
  renderBBoxOverlay(svg, frame, options, visualScale);
  renderGameRectOverlay(svg, frame, gameManifest, options, visualScale);
  renderSkeletonForFrame(svg, frame, options, visualScale);
  renderLandmarkOverlay(svg, frame, options, visualScale);
  renderMlLandmarkOverlay(svg, frame, options, visualScale);
}

function buildStripPreview(svgSource, analysisResult, options, onFrameClick) {
  const viewBox = parseSvgViewBox(svgSource);
  if (!viewBox) return null;

  const scale = Math.min(STRIP_PREVIEW_MAX_W / viewBox.w, STRIP_PREVIEW_MAX_H / viewBox.h, 1.5);
  const displayW = viewBox.w * scale;
  const displayH = viewBox.h * scale;
  const gameManifest = analysisResult.gameManifest;

  const wrap = document.createElement("div");
  wrap.className = "strip-preview-inner";
  wrap.style.width = `${displayW}px`;
  wrap.style.height = `${displayH}px`;

  const doc = new DOMParser().parseFromString(svgSource, "image/svg+xml");
  const source = doc.documentElement;
  const baseSvg = document.createElementNS(SVG_NS, "svg");
  baseSvg.setAttribute("viewBox", `${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`);
  baseSvg.setAttribute("width", String(displayW));
  baseSvg.setAttribute("height", String(displayH));
  baseSvg.classList.add("strip-base-svg");
  for (const child of source.childNodes) {
    if (child.nodeType === Node.ELEMENT_NODE) {
      baseSvg.appendChild(child.cloneNode(true));
    }
  }
  wrap.appendChild(baseSvg);

  const overlay = document.createElementNS(SVG_NS, "svg");
  overlay.classList.add("strip-overlay-svg");
  overlay.setAttribute("viewBox", `${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`);
  overlay.setAttribute("width", String(displayW));
  overlay.setAttribute("height", String(displayH));

  for (const frame of analysisResult.frameAnalysis || []) {
    const idx = frame.frameIndex;
    const color = GAME_RECT_COLORS[idx % GAME_RECT_COLORS.length];
    const frameBBox = frame.bounds?.frameBBox;
    if (frameBBox && options.frameBBox) {
      overlay.appendChild(
        nsEl("rect", {
          x: frameBBox.x,
          y: frameBBox.y,
          width: frameBBox.w,
          height: frameBBox.h,
          fill: "none",
          stroke: "#7c9cff",
          "stroke-width": Math.max(1.5, 2 / scale),
          "stroke-dasharray": "8 4",
          opacity: 0.85,
        }),
      );
    }

    const entry = getGameFrameEntry(gameManifest, idx);
    const gameRect = gameRectToViewBox(entry?.contentRect || entry?.rect);
    if (gameRect && options.gameRect) {
      overlay.appendChild(
        nsEl("rect", {
          x: gameRect.x,
          y: gameRect.y,
          width: gameRect.w,
          height: gameRect.h,
          fill: `${color}18`,
          stroke: color,
          "stroke-width": Math.max(2, 2.5 / scale),
        }),
      );
    }

    if (frameBBox) {
      const hit = nsEl("rect", {
        x: frameBBox.x,
        y: frameBBox.y,
        width: frameBBox.w,
        height: frameBBox.h,
        fill: "transparent",
        stroke: "none",
        "data-frame-hit": String(idx),
        style: "pointer-events: all; cursor: pointer;",
      });
      if (onFrameClick) {
        hit.addEventListener("click", () => onFrameClick(idx));
      }
      overlay.appendChild(hit);

      const label = nsEl("text", {
        x: frameBBox.x + 6,
        y: frameBBox.y + 18,
        fill: color,
        "font-size": Math.max(12, 14 / scale),
        "font-weight": "600",
      });
      label.textContent = `F${idx}`;
      overlay.appendChild(label);
    }
  }

  overlay.style.pointerEvents = onFrameClick ? "auto" : "none";
  wrap.appendChild(overlay);
  return { wrap, scale, viewBox };
}

function buildPreviewBanner(analysisResult) {
  const banner = document.createElement("div");
  banner.className = "preview-banner-inner";

  const manifest = analysisResult.gameManifest;
  const validation = manifest?.validation || {};
  const stack = analysisResult.stackRecommendation?.chosen || "phaser-svg-frame-strip";
  const mlFrames = (analysisResult.frameAnalysis || []).filter((f) => f.mlLandmarks?.status === "ok").length;
  const mlBackend = analysisResult.frameAnalysis?.find((f) => f.mlLandmarks?.backend)?.mlLandmarks?.backend;

  const chips = [
    { label: "Stack", value: stack, tone: "info" },
    { label: "Frames", value: String(analysisResult.stripAnalysis?.frameCount ?? 0), tone: "info" },
    {
      label: "Game export",
      value: validation.readyForGame ? "Ready" : "Check issues",
      tone: validation.readyForGame ? "ok" : "warn",
    },
  ];
  if (mlBackend) {
    chips.push({ label: "ML", value: `${mlBackend} (${mlFrames} frames)`, tone: "ml" });
  }

  for (const chip of chips) {
    const el = document.createElement("span");
    el.className = `preview-chip ${chip.tone}`;
    el.innerHTML = `<em>${chip.label}</em>${chip.value}`;
    banner.append(el);
  }

  if (validation.issues?.length) {
    const issues = document.createElement("p");
    issues.className = "preview-banner-issues";
    issues.textContent = validation.issues.join(" · ");
    banner.append(issues);
  }

  return banner;
}

function buildFrameExportMeta(frame, gameManifest) {
  const entry = getGameFrameEntry(gameManifest, frame.frameIndex);
  const rect = entry?.contentRect || entry?.rect;
  const ml = frame.mlLandmarks;
  const parts = [];

  if (rect) {
    const scaleX = gameManifest?.displayScale?.x ?? 1;
    const scaleY = gameManifest?.displayScale?.y ?? scaleX;
    const displayW = Math.round(rect.width * scaleX);
    const displayH = Math.round(rect.height * scaleY);
    parts.push(`export ${displayW}×${displayH}px`);
    if (Math.abs(scaleX - 1) > 0.01) {
      parts.push(`svg ${Math.round(rect.width)}×${Math.round(rect.height)}`);
    }
  }
  if (ml?.status === "ok") {
    parts.push(`ml: ${ml.backend || "ok"}`);
  } else if (ml?.status === "skipped") {
    parts.push(`ml: ${ml.reason || "skipped"}`);
  } else if (ml?.backend) {
    parts.push(`ml: ${ml.backend}`);
  }
  if (!parts.length) return null;

  const meta = document.createElement("div");
  meta.className = "frame-export-meta";
  meta.textContent = parts.join(" · ");
  return meta;
}

const SVG_NS = "http://www.w3.org/2000/svg";

function createCroppedFrameSvg(svgSource, frameBBox, displayW, displayH) {
  const doc = new DOMParser().parseFromString(svgSource, "image/svg+xml");
  const source = doc.documentElement;
  if (source.tagName?.toLowerCase() !== "svg") {
    return null;
  }

  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", `${frameBBox.x} ${frameBBox.y} ${frameBBox.w} ${frameBBox.h}`);
  svg.setAttribute("width", String(displayW));
  svg.setAttribute("height", String(displayH));
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  svg.classList.add("svg-frame-layer");

  for (const child of source.childNodes) {
    if (child.nodeType !== Node.ELEMENT_NODE) continue;
    const tag = child.localName?.toLowerCase();
    if (tag === "defs" || tag === "style") {
      svg.appendChild(child.cloneNode(true));
    }
  }

  for (const child of source.childNodes) {
    if (child.nodeType !== Node.ELEMENT_NODE) continue;
    const tag = child.localName?.toLowerCase();
    if (tag !== "defs" && tag !== "style") {
      svg.appendChild(child.cloneNode(true));
    }
  }

  return svg;
}

function collectQualityWarnings(frame, temporalAnalysis) {
  const items = [];
  const push = (issue) => {
    if (issue) items.push(issue);
  };

  for (const issue of frame.quality?.errors || []) push(issue);
  for (const issue of frame.quality?.warnings || []) push(issue);

  const skErr = frame.skeleton?.errors;
  if (skErr) {
    for (const name of skErr.missingLandmarks || []) {
      push({ code: "MISSING_LANDMARK", severity: "warning", message: `Missing landmark: ${name}` });
    }
    for (const name of skErr.unstableBones || []) {
      push({ code: "PART_JUMP", severity: "warning", message: `Unstable bone: ${name}` });
    }
    for (const name of skErr.lowConfidenceBones || []) {
      push({ code: "LOW_CONFIDENCE_PART", severity: "warning", message: `Low confidence bone: ${name}` });
    }
  }

  for (const msg of temporalAnalysis?.warnings || []) {
    if (String(msg).toLowerCase().includes(String(frame.frameIndex))) {
      push({ code: "MUTATED_PART", severity: "warning", message: String(msg) });
    }
  }

  return items;
}

function buildFrameWarnings(frame, temporalAnalysis) {
  const warnings = collectQualityWarnings(frame, temporalAnalysis);
  const wrap = document.createElement("div");
  wrap.className = "frame-review-warnings";

  if (!warnings.length) {
    const empty = document.createElement("p");
    empty.className = "warning-empty";
    empty.textContent = "No warnings.";
    wrap.append(empty);
    return wrap;
  }

  const list = document.createElement("ul");
  for (const issue of warnings.slice(0, 4)) {
    const li = document.createElement("li");
    li.innerHTML = `<strong>${issue.code || "ISSUE"}</strong>${issue.message || ""}`;
    list.append(li);
  }
  wrap.append(list);
  return wrap;
}

function buildFrameCard(
  svgSource,
  frame,
  options,
  reviewByFrame,
  temporalAnalysis,
  gameManifest,
  isActive,
  onSelect,
  onReviewChange,
) {
  const frameBBox = frame.bounds.frameBBox;
  const cropBBox = frame.bounds.contentBBox || frameBBox;
  const scale = computeFrameScale(cropBBox);
  const displayW = cropBBox.w * scale;
  const displayH = cropBBox.h * scale;

  const card = document.createElement("article");
  card.className = `frame-review-card${isActive ? " active" : ""}`;
  card.dataset.frame = String(frame.frameIndex);

  const header = document.createElement("header");
  header.className = "frame-review-header";

  const title = document.createElement("h3");
  title.textContent = `Frame ${frame.frameIndex}`;

  const meta = document.createElement("span");
  meta.className = "frame-review-meta";
  const bodyView = frame.view?.bodyView || "unknown";
  const headView = frame.view?.headView || "unknown";
  const score = frame.quality?.score ?? "—";
  meta.textContent = `body: ${bodyView} · head: ${headView} · score ${score}`;

  const status = document.createElement("select");
  status.className = "frame-review-status";
  for (const label of REVIEW_STATUSES) {
    const opt = document.createElement("option");
    opt.value = label;
    opt.textContent = label;
    status.append(opt);
  }
  status.value = reviewByFrame[frame.frameIndex] || "Not Reviewed";
  status.addEventListener("change", () => {
    const previous = reviewByFrame[frame.frameIndex] || "Not Reviewed";
    onReviewChange(frame.frameIndex, status.value);
    if (window.SkeletonReview?.recordReviewStatus) {
      window.SkeletonReview.recordReviewStatus(frame.frameIndex, status.value, previous);
    }
  });
  status.addEventListener("click", (event) => event.stopPropagation());

  header.append(title, meta, status);

  const stageWrap = document.createElement("div");
  stageWrap.className = "frame-review-stage-wrap";

  const stage = document.createElement("div");
  stage.className = "frame-review-stage";
  stage.style.width = `${displayW}px`;
  stage.style.height = `${displayH}px`;

  const frameSvg = createCroppedFrameSvg(svgSource, cropBBox, displayW, displayH);
  if (frameSvg) {
    stage.appendChild(frameSvg);
  }

  const overlay = document.createElementNS(SVG_NS, "svg");
  overlay.classList.add("analysis-overlay-layer");
  overlay.setAttribute("viewBox", `0 0 ${cropBBox.w} ${cropBBox.h}`);
  overlay.setAttribute("width", String(displayW));
  overlay.setAttribute("height", String(displayH));
  overlay.setAttribute("preserveAspectRatio", "xMidYMid meet");

  const overlayFrame = {
    ...frame,
    bounds: {
      ...frame.bounds,
      frameBBox: {
        x: cropBBox.x,
        y: cropBBox.y,
        w: cropBBox.w,
        h: cropBBox.h,
      },
    },
  };

  renderFrameOverlays(overlay, overlayFrame, options, scale, gameManifest);

  stage.appendChild(overlay);
  stageWrap.append(stage);

  const exportMeta = buildFrameExportMeta(frame, gameManifest);
  card.append(header, stageWrap);
  if (exportMeta) card.append(exportMeta);
  card.append(buildFrameWarnings(frame, temporalAnalysis));
  card.addEventListener("click", () => onSelect(frame.frameIndex));

  return card;
}

const SkeletonReview = {
  rootEl: null,
  gridEl: null,
  timelineEl: null,
  reviewStatusEl: null,
  stripPreviewPanel: null,
  stripPreviewStage: null,
  stripPreviewMeta: null,
  previewBanner: null,
  overlayLegend: null,

  svgSource: "",
  analysisResult: null,
  frameIndex: 0,
  toggles: { ...DEFAULT_TOGGLES },
  reviewByFrame: {},
  pendingCorrections: [],
  onMoveLandmark: undefined,

  init(root) {
    if (this._initialized) return;
    this._initialized = true;
    this.rootEl = root;
    this.gridEl = root.querySelector("#frameCardsGrid");
    this.timelineEl = root.querySelector("#frameTimeline");
    this.reviewStatusEl = root.querySelector("#reviewStatusSelect");
    this.stripPreviewPanel = root.querySelector("#stripPreviewPanel");
    this.stripPreviewStage = root.querySelector("#stripPreviewStage");
    this.stripPreviewMeta = root.querySelector("#stripPreviewMeta");
    this.previewBanner = root.querySelector("#previewBanner");
    this.overlayLegend = root.querySelector("#overlayLegend");

    root.querySelectorAll("[data-toggle]").forEach((input) => {
      input.addEventListener("change", () => {
        this.toggles[input.dataset.toggle] = input.checked;
        this.render();
      });
    });

    this.reviewStatusEl?.addEventListener("change", () => {
      const previous = this.reviewByFrame[this.frameIndex] || "Not Reviewed";
      this.reviewByFrame[this.frameIndex] = this.reviewStatusEl.value;
      this.recordReviewStatus(this.frameIndex, this.reviewStatusEl.value, previous);
      this.render();
    });
  },

  setData({ svgSource, analysisResult, onMoveLandmark }) {
    this.svgSource = svgSource || "";
    this.analysisResult = analysisResult;
    this.onMoveLandmark = onMoveLandmark;
    this.frameIndex = 0;
    this.pendingCorrections = [];

    const hasMl = analysisResult?.frameAnalysis?.some(
      (f) => f.mlLandmarks?.status === "ok" || f.mlLandmarks?.backend,
    );
    if (hasMl) {
      this.toggles.mlLandmarks = true;
      const mlToggle = this.rootEl?.querySelector('[data-toggle="mlLandmarks"]');
      if (mlToggle) mlToggle.checked = true;
    }

    this.renderBanner();
    this.renderTimeline();
    this.render();
  },

  renderBanner() {
    if (!this.previewBanner || !this.analysisResult) return;
    this.previewBanner.hidden = false;
    this.previewBanner.replaceChildren(buildPreviewBanner(this.analysisResult));
    if (this.overlayLegend) this.overlayLegend.hidden = false;
  },

  renderStripPreview() {
    if (!this.stripPreviewPanel || !this.stripPreviewStage || !this.analysisResult) return;

    this.stripPreviewPanel.hidden = false;
    const strip = this.analysisResult.stripAnalysis;
    const manifest = this.analysisResult.gameManifest;
    const method = strip?.selectedSplitMethod || "—";
    const score = strip?.splitConfidence ?? "—";
    if (this.stripPreviewMeta) {
      this.stripPreviewMeta.textContent = `${strip?.frameCount ?? 0} frames · ${strip?.layout?.direction || "horizontal"} · split ${method} (${score})`;
    }

    this.stripPreviewStage.replaceChildren();
    const built = buildStripPreview(
      this.svgSource,
      this.analysisResult,
      { ...this.toggles, frameBBox: true },
      (index) => this.setFrame(index),
    );
    if (built) {
      this.stripPreviewStage.appendChild(built.wrap);
      this.stripPreviewStage.style.minHeight = `${built.wrap.style.height}`;
    }
  },

  queueCorrection(entry) {
    this.pendingCorrections.push(entry);
    this.flushCorrections();
  },

  async flushCorrections() {
    if (!this.analysisResult?.assetAnalysis?.assetId || !this.pendingCorrections.length) return;
    const batch = this.pendingCorrections.splice(0, this.pendingCorrections.length);
    try {
      await fetch("/api/corrections", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          assetId: this.analysisResult.assetAnalysis.assetId,
          corrections: batch,
        }),
      });
    } catch {
      this.pendingCorrections.unshift(...batch);
    }
  },

  recordReviewStatus(frameIndex, status, previous) {
    if (previous === status) return;
    this.queueCorrection({
      frameIndex,
      targetType: "review",
      targetId: `frame_${frameIndex}`,
      before: previous,
      after: status,
      reason: "Skeleton review status change",
    });
  },

  setFrame(index) {
    this.frameIndex = index;
    this.renderTimeline();
    this.render();
    const card = this.gridEl?.querySelector(`[data-frame="${index}"]`);
    card?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    this.rootEl?.dispatchEvent(new CustomEvent("skeleton-frame-change", { detail: { frameIndex: index } }));
  },

  renderTimeline() {
    if (!this.timelineEl || !this.analysisResult) return;
    this.timelineEl.replaceChildren();
    for (const frame of this.analysisResult.frameAnalysis) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `frame-chip${frame.frameIndex === this.frameIndex ? " active" : ""}`;
      btn.dataset.frame = String(frame.frameIndex);
      btn.textContent = `Frame ${frame.frameIndex}`;
      btn.addEventListener("click", () => this.setFrame(frame.frameIndex));
      this.timelineEl.append(btn);
    }
    if (this.reviewStatusEl) {
      this.reviewStatusEl.value = this.reviewByFrame[this.frameIndex] || "Not Reviewed";
    }
  },

  render() {
    if (!this.gridEl || !this.analysisResult?.frameAnalysis?.length || !this.svgSource) return;

    this.renderStripPreview();

    const temporal = this.analysisResult.temporalAnalysis;
    const gameManifest = this.analysisResult.gameManifest;
    this.gridEl.replaceChildren();

    for (const frame of this.analysisResult.frameAnalysis) {
      this.gridEl.append(
        buildFrameCard(
          this.svgSource,
          frame,
          this.toggles,
          this.reviewByFrame,
          temporal,
          gameManifest,
          frame.frameIndex === this.frameIndex,
          (index) => this.setFrame(index),
          (index, value) => {
            this.reviewByFrame[index] = value;
            if (index === this.frameIndex && this.reviewStatusEl) {
              this.reviewStatusEl.value = value;
            }
          },
        ),
      );
    }
  },
};

window.SkeletonReview = SkeletonReview;
window.SkeletonReviewUtils = {
  toFrameLocalPoint,
  toFrameLocalBBox,
  toOverlayPoint,
};
