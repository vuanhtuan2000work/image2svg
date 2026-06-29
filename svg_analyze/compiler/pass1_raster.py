"""Pass 1 — Raster evidence extraction (cairo / rsvg / path-density fallback)."""

from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from svg_analyze.geometry import BBox, union_bbox
from svg_analyze.types import NormalizedPath, RasterEvidence

try:
    import numpy as np

    _HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore
    _HAS_NUMPY = False

try:
    import cairosvg

    _HAS_CAIRO = True
except (ImportError, OSError):
    cairosvg = None  # type: ignore
    _HAS_CAIRO = False

_HAS_RASTER = _HAS_NUMPY
RasterBackend = Literal["cairo", "rsvg-convert", "path-density"]


def _rgb_to_lab(r: int, g: int, b: int) -> tuple[float, float, float]:
    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0

    def pivot(c: float) -> float:
        return ((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92

    rf, gf, bf = pivot(rf), pivot(gf), pivot(bf)
    x = rf * 0.4124564 + gf * 0.3575761 + bf * 0.1804375
    y = rf * 0.2126729 + gf * 0.7151522 + bf * 0.0721750
    z = rf * 0.0193339 + gf * 0.1191920 + bf * 0.9503041
    x, y, z = x / 0.95047, y / 1.0, z / 1.08883
    fx = x ** (1 / 3) if x > 0.008856 else (7.787 * x) + (16 / 116)
    fy = y ** (1 / 3) if y > 0.008856 else (7.787 * y) + (16 / 116)
    fz = z ** (1 / 3) if z > 0.008856 else (7.787 * z) + (16 / 116)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def _kmeans_lab(pixels: list[tuple[float, float, float]], k: int, iters: int = 8) -> list[tuple[float, float, float]]:
    if not pixels:
        return []
    k = min(k, len(pixels))
    step = max(1, len(pixels) // k)
    centers = [pixels[i * step] for i in range(k)]
    for _ in range(iters):
        buckets: list[list[tuple[float, float, float]]] = [[] for _ in range(k)]
        for px in pixels:
            best = min(range(k), key=lambda i: sum((px[j] - centers[i][j]) ** 2 for j in range(3)))
            buckets[best].append(px)
        for i, bucket in enumerate(buckets):
            if bucket:
                centers[i] = (
                    sum(p[0] for p in bucket) / len(bucket),
                    sum(p[1] for p in bucket) / len(bucket),
                    sum(p[2] for p in bucket) / len(bucket),
                )
    return centers


def _connected_components_2d(mask: Any) -> list[tuple[int, int, int, int, int]]:
    """Return list of (label, x, y, w, h, area) for 4-connected components."""
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    current = 0
    components: list[tuple[int, int, int, int, int, int]] = []

    for y in range(h):
        for x in range(w):
            if not mask[y, x] or labels[y, x]:
                continue
            current += 1
            stack = [(x, y)]
            min_x = max_x = x
            min_y = max_y = y
            area = 0
            labels[y, x] = current
            while stack:
                cx, cy = stack.pop()
                area += 1
                min_x, max_x = min(min_x, cx), max(max_x, cx)
                min_y, max_y = min(min_y, cy), max(max_y, cy)
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if 0 <= nx < w and 0 <= ny < h and mask[ny, nx] and labels[ny, nx] == 0:
                        labels[ny, nx] = current
                        stack.append((nx, ny))
            components.append((current, min_x, min_y, max_x - min_x + 1, max_y - min_y + 1, area))
    return components


def _distance_transform(mask: Any) -> Any:
    h, w = mask.shape
    inf = h + w + 1
    dist = np.where(mask, inf, 0).astype(np.float32)
    for y in range(h):
        for x in range(w):
            if mask[y, x]:
                dist[y, x] = min(dist[y, x], dist[y - 1, x] + 1 if y else inf, dist[y, x - 1] + 1 if x else inf)
    for y in range(h - 1, -1, -1):
        for x in range(w - 1, -1, -1):
            if mask[y, x]:
                dist[y, x] = min(
                    dist[y, x],
                    dist[y + 1, x] + 1 if y + 1 < h else inf,
                    dist[y, x + 1] + 1 if x + 1 < w else inf,
                )
    return dist


def _morphological_opening(mask: Any, radius: int = 1) -> Any:
    if radius <= 0:
        return mask
    h, w = mask.shape
    eroded = mask.copy()
    for _ in range(radius):
        tmp = eroded.copy()
        for y in range(h):
            for x in range(w):
                if not eroded[y, x]:
                    continue
                for dy in range(-1, 2):
                    for dx in range(-1, 2):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < h and 0 <= nx < w and not eroded[ny, nx]:
                            tmp[y, x] = False
                            break
        eroded = tmp
    return eroded


def _path_density_raster(
    paths: list[NormalizedPath],
    view_box: tuple[float, float, float, float],
    width: int,
    height: int,
) -> Any:
    vx, vy, vw, vh = view_box
    mask = np.zeros((height, width), dtype=bool)
    for path in paths:
        bx = path.bbox
        x1 = int(max(0, min(width - 1, (bx.x - vx) / max(vw, 1) * width)))
        x2 = int(max(0, min(width, (bx.x2 - vx) / max(vw, 1) * width)))
        y1 = int(max(0, min(height - 1, (bx.y - vy) / max(vh, 1) * height)))
        y2 = int(max(0, min(height, (bx.y2 - vy) / max(vh, 1) * height)))
        if x2 > x1 and y2 > y1:
            mask[y1:y2, x1:x2] = True
    return mask


def _render_with_rsvg(svg_text: str, width: int, height: int) -> tuple[Any, Any, RasterBackend] | None:
    rsvg = shutil.which("rsvg-convert")
    if not rsvg:
        return None
    try:
        from PIL import Image

        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp:
            tmp.write(svg_text.encode("utf-8"))
            svg_path = tmp.name
        out_path = svg_path + ".png"
        subprocess.run(
            [rsvg, "-w", str(width), "-h", str(height), "-o", out_path, svg_path],
            check=True,
            capture_output=True,
            timeout=30,
        )
        img = Image.open(out_path).convert("RGBA")
        arr = np.array(img)
        Path(svg_path).unlink(missing_ok=True)
        Path(out_path).unlink(missing_ok=True)
        return arr[:, :, 3] > 8, arr[:, :, :3], "rsvg-convert"
    except Exception:
        return None


def _render_alpha_rgb(
    svg_text: str,
    width: int,
    height: int,
    paths: list[NormalizedPath],
    view_box: tuple[float, float, float, float],
) -> tuple[Any, Any | None, RasterBackend, list[str]]:
    render_warnings: list[str] = []
    if _HAS_CAIRO and cairosvg is not None:
        try:
            from PIL import Image

            png_bytes = cairosvg.svg2png(
                bytestring=svg_text.encode("utf-8"),
                output_width=width,
                output_height=height,
            )
            img = Image.open(BytesIO(png_bytes)).convert("RGBA")
            arr = np.array(img)
            return arr[:, :, 3] > 8, arr[:, :, :3], "cairo", render_warnings
        except Exception as exc:
            render_warnings.append(f"Cairo render failed: {exc}")

    rsvg_result = _render_with_rsvg(svg_text, width, height)
    if rsvg_result is not None:
        alpha, rgb, backend = rsvg_result
        return alpha, rgb, backend, render_warnings

    render_warnings.append("Using path-density fallback (install cairo or rsvg-convert for accurate masks)")
    alpha = _path_density_raster(paths, view_box, width, height)
    return alpha, None, "path-density", render_warnings


def _raster_render_scale(
    view_box: tuple[float, float, float, float],
    content: BBox,
    *,
    max_dim: int = 512,
    display_width: float | None = None,
    display_height: float | None = None,
) -> float:
    """Pick raster scale that preserves frame gaps (viewBox units often >> display px)."""
    vx, vy, vw, vh = view_box
    scale = min(max_dim / max(vw, vh), max_dim / max(content.w, content.h, 1.0), 4.0)
    if display_width and display_width > 0:
        # Match SVG width/height attrs — enough to keep adjacent run frames as separate CCs.
        scale = max(scale, display_width / max(vw, 1.0))
    if display_height and display_height > 0:
        scale = max(scale, display_height / max(vh, 1.0))
    return scale


def extract_raster_evidence(
    svg_text: str,
    view_box: tuple[float, float, float, float],
    paths: list[NormalizedPath],
    *,
    max_dim: int = 512,
    display_width: float | None = None,
    display_height: float | None = None,
) -> RasterEvidence:
    vx, vy, vw, vh = view_box
    content = union_bbox(p.bbox for p in paths) or BBox(vx, vy, vw, vh)
    scale = _raster_render_scale(
        view_box,
        content,
        max_dim=max_dim,
        display_width=display_width,
        display_height=display_height,
    )
    width = max(32, int(math.ceil(vw * scale)))
    height = max(32, int(math.ceil(vh * scale)))
    warnings: list[str] = []

    if not _HAS_RASTER:
        warnings.append("Raster pass skipped: install numpy for mask evidence")
        return RasterEvidence(
            width=width,
            height=height,
            scale=scale,
            content_bbox=content,
            alpha_mask=None,
            color_label_mask=None,
            edge_mask=None,
            density_map=None,
            warnings=warnings,
        )

    alpha, rgb, backend, render_warnings = _render_alpha_rgb(svg_text, width, height, paths, view_box)
    warnings.extend(render_warnings)
    warnings.append(f"Raster backend: {backend}")
    alpha_open = _morphological_opening(alpha, radius=1)

    fg_pixels: list[tuple[float, float, float]] = []
    if rgb is not None:
        ys, xs = np.where(alpha)
        for y, x in zip(ys[::3], xs[::3], strict=False):
            r, g, b = int(rgb[y, x, 0]), int(rgb[y, x, 1]), int(rgb[y, x, 2])
            fg_pixels.append(_rgb_to_lab(r, g, b))

    centers = _kmeans_lab(fg_pixels, k=min(12, max(2, len(fg_pixels) // 200)))
    color_label = np.zeros((height, width), dtype=np.int16)
    if centers and rgb is not None and width * height <= 120_000:
        lab_map = np.zeros((height, width, 3), dtype=np.float32)
        for y in range(height):
            for x in range(width):
                if alpha[y, x]:
                    lab_map[y, x] = _rgb_to_lab(int(rgb[y, x, 0]), int(rgb[y, x, 1]), int(rgb[y, x, 2]))
        for y in range(height):
            for x in range(width):
                if not alpha[y, x]:
                    continue
                px = lab_map[y, x]
                best = min(range(len(centers)), key=lambda i: sum((px[j] - centers[i][j]) ** 2 for j in range(3)))
                color_label[y, x] = best + 1

    edge = np.zeros((height, width), dtype=bool)
    edge[1:, :] |= alpha[1:, :] & ~alpha[:-1, :]
    edge[:, 1:] |= alpha[:, 1:] & ~alpha[:, :-1]
    edge[:-1, :] |= alpha[:-1, :] & ~alpha[1:, :]
    edge[:, :-1] |= alpha[:, :-1] & ~alpha[:, 1:]

    density = _distance_transform(alpha_open)
    if density.max() > 0:
        density = density / density.max()

    clusters: list[dict[str, Any]] = []
    for i, center in enumerate(centers):
        clusters.append({"clusterId": i + 1, "lab": [round(c, 2) for c in center], "roleGuess": "unknown"})

    return RasterEvidence(
        width=width,
        height=height,
        scale=scale,
        content_bbox=content,
        alpha_mask=alpha,
        color_label_mask=color_label,
        edge_mask=edge,
        density_map=density,
        rgb_image=rgb,
        color_clusters=clusters,
        warnings=warnings,
    )


def crop_alpha_to_bbox(
    raster: RasterEvidence,
    bbox: BBox,
    view_box: tuple[float, float, float, float],
) -> np.ndarray | None:
    if raster.alpha_mask is None:
        return None
    x1, y1, x2, y2 = _mask_slice_for_bbox(raster, bbox, view_box)
    if x2 <= x1 or y2 <= y1:
        return None
    return raster.alpha_mask[y1:y2, x1:x2].copy()


def crop_rgb_to_bbox(
    raster: RasterEvidence,
    bbox: BBox,
    view_box: tuple[float, float, float, float],
) -> np.ndarray | None:
    if raster.rgb_image is None:
        return None
    x1, y1, x2, y2 = _mask_slice_for_bbox(raster, bbox, view_box)
    if x2 <= x1 or y2 <= y1:
        return None
    return raster.rgb_image[y1:y2, x1:x2].copy()


def crop_rgba_to_bbox(
    raster: RasterEvidence,
    bbox: BBox,
    view_box: tuple[float, float, float, float],
) -> np.ndarray | None:
    rgb = crop_rgb_to_bbox(raster, bbox, view_box)
    alpha = crop_alpha_to_bbox(raster, bbox, view_box)
    if rgb is None or alpha is None:
        return None
    rgba = np.zeros((rgb.shape[0], rgb.shape[1], 4), dtype=np.uint8)
    rgba[:, :, :3] = rgb
    rgba[:, :, 3] = np.where(alpha, 255, 0).astype(np.uint8)
    return rgba


def rgba_crop_to_png_bytes(rgba: np.ndarray) -> bytes:
    from io import BytesIO

    from PIL import Image

    img = Image.fromarray(rgba, mode="RGBA")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _mask_slice_for_bbox(
    raster: RasterEvidence,
    bbox: BBox,
    view_box: tuple[float, float, float, float],
) -> tuple[int, int, int, int]:
    vx, vy, vw, vh = view_box
    rw, rh = raster.width, raster.height
    x1 = int(max(0, (bbox.x - vx) / max(vw, 1) * rw))
    x2 = int(min(rw, (bbox.x2 - vx) / max(vw, 1) * rw))
    y1 = int(max(0, (bbox.y - vy) / max(vh, 1) * rh))
    y2 = int(min(rh, (bbox.y2 - vy) / max(vh, 1) * rh))
    return x1, y1, x2, y2


def crop_density_to_bbox(
    raster: RasterEvidence,
    bbox: BBox,
    view_box: tuple[float, float, float, float],
) -> np.ndarray | None:
    if raster.density_map is None:
        return None
    x1, y1, x2, y2 = _mask_slice_for_bbox(raster, bbox, view_box)
    if x2 <= x1 or y2 <= y1:
        return None
    return raster.density_map[y1:y2, x1:x2].copy()


def alpha_projection(raster: RasterEvidence, axis: str = "x") -> list[float]:
    if raster.alpha_mask is None:
        return []
    mask = raster.alpha_mask
    if axis == "x":
        return [float(mask[:, x].sum()) for x in range(mask.shape[1])]
    return [float(mask[y, :].sum()) for y in range(mask.shape[0])]


def svg_to_mask_bbox(component: tuple[int, int, int, int, int, int], raster: RasterEvidence, view_box: tuple[float, float, float, float]) -> BBox:
    _, x, y, w, h, _ = component
    vx, vy, vw, vh = view_box
    rw, rh = raster.width, raster.height
    return BBox(vx + (x / rw) * vw, vy + (y / rh) * vh, (w / rw) * vw, (h / rh) * vh)


def _mask_bbox_to_svg(x1: int, y1: int, x2: int, y2: int, raster: RasterEvidence, view_box: tuple[float, float, float, float]) -> BBox:
    vx, vy, vw, vh = view_box
    rw, rh = raster.width, raster.height
    return BBox(
        vx + (x1 / rw) * vw,
        vy + (y1 / rh) * vh,
        max(1.0, ((x2 - x1) / rw) * vw),
        max(1.0, ((y2 - y1) / rh) * vh),
    )


def _clamp_bbox_to_frame(bbox: BBox, frame: BBox) -> BBox:
    x1 = max(frame.x, bbox.x)
    y1 = max(frame.y, bbox.y)
    x2 = min(frame.x2, bbox.x2)
    y2 = min(frame.y2, bbox.y2)
    return BBox(x1, y1, max(1.0, x2 - x1), max(1.0, y2 - y1))


def _looks_like_frame_background(path: NormalizedPath, frame: BBox) -> bool:
    bbox = path.bbox
    covers_width = bbox.x <= frame.x + frame.w * 0.04 and bbox.x2 >= frame.x2 - frame.w * 0.04
    covers_height = bbox.y <= frame.y + frame.h * 0.04 and bbox.y2 >= frame.y2 - frame.h * 0.04
    covers_area = bbox.area >= frame.area * 0.62
    overwide = bbox.w >= frame.w * 0.92 and bbox.h >= frame.h * 0.82
    return covers_area and overwide and covers_width and covers_height


def foreground_bbox_from_paths(
    paths: list[NormalizedPath],
    frame: BBox,
    *,
    padding_ratio: float = 0.035,
) -> BBox | None:
    """Tight path bounds for the animal/object, excluding sheet backgrounds."""
    frame_area = max(frame.area, 1.0)
    foreground: list[BBox] = []

    for path in paths:
        if path.bbox.area <= frame_area * 0.00015:
            continue
        if _looks_like_frame_background(path, frame):
            continue
        if path.bbox.w > frame.w * 1.08 and (
            path.bbox.area > frame_area * 0.03 or path.bbox.h < frame.h * 0.08
        ):
            continue
        if path.bbox.h > frame.h * 1.08 and (
            path.bbox.area > frame_area * 0.03 or path.bbox.w < frame.w * 0.08
        ):
            continue
        foreground.append(_clamp_bbox_to_frame(path.bbox, frame))

    if not foreground:
        fallback = [_clamp_bbox_to_frame(path.bbox, frame) for path in paths if path.bbox.area > 0]
        if not fallback:
            return None
        foreground = fallback

    tight = union_bbox(foreground)
    if tight is None:
        return None

    pad_x = tight.w * padding_ratio
    pad_y = tight.h * padding_ratio
    return _clamp_bbox_to_frame(tight.expand(max(pad_x, pad_y)), frame)


def _component_touches_edge(component: tuple[int, int, int, int, int, int], crop_w: int, crop_h: int, pad: int = 1) -> bool:
    _, x, y, w, h, _ = component
    return x <= pad or y <= pad or x + w >= crop_w - pad or y + h >= crop_h - pad


def _selected_content_components(crop: Any) -> list[tuple[int, int, int, int, int, int]]:
    """Keep the dominant in-frame silhouette while dropping small adjacent-frame leaks."""
    components = _connected_components_2d(crop)
    if not components:
        return []

    crop_h, crop_w = crop.shape
    components.sort(key=lambda c: c[5], reverse=True)
    primary = components[0]
    primary_area = max(primary[5], 1)
    selected = [primary]

    for comp in components[1:]:
        _, x, y, w, h, area = comp
        area_ratio = area / primary_area
        edge_sliver = (
            _component_touches_edge(comp, crop_w, crop_h)
            and area_ratio < 0.22
            and (w < crop_w * 0.22 or h < crop_h * 0.22)
        )
        if edge_sliver:
            continue
        if area_ratio >= 0.08:
            selected.append(comp)

    return selected


def tight_content_bbox_for_frame(
    raster: RasterEvidence | None,
    frame_bbox: BBox,
    view_box: tuple[float, float, float, float],
    *,
    padding_ratio: float = 0.04,
) -> BBox | None:
    """Tight alpha bounds inside a frame slot (ignores strip-spanning path unions)."""
    if raster is None or raster.alpha_mask is None:
        return None

    sx1, sy1, sx2, sy2 = _mask_slice_for_bbox(raster, frame_bbox, view_box)
    if sx2 <= sx1 or sy2 <= sy1:
        return None

    crop = raster.alpha_mask[sy1:sy2, sx1:sx2].copy()
    if crop is None or not crop.any():
        return None

    selected = _selected_content_components(crop)
    if selected:
        x1 = min(c[1] for c in selected)
        y1 = min(c[2] for c in selected)
        x2 = max(c[1] + c[3] for c in selected)
        y2 = max(c[2] + c[4] for c in selected)
    else:
        ys, xs = np.where(crop)
        y1, y2 = int(ys.min()), int(ys.max()) + 1
        x1, x2 = int(xs.min()), int(xs.max()) + 1

    tight = _mask_bbox_to_svg(sx1 + x1, sy1 + y1, sx1 + x2, sy1 + y2, raster, view_box)

    pad_x = tight.w * padding_ratio
    pad_y = tight.h * padding_ratio
    x = max(frame_bbox.x, tight.x - pad_x)
    y = max(frame_bbox.y, tight.y - pad_y)
    x2 = min(frame_bbox.x2, tight.x2 + pad_x)
    y2 = min(frame_bbox.y2, tight.y2 + pad_y)
    return BBox(
        x,
        y,
        max(1.0, x2 - x),
        max(1.0, y2 - y),
    )


def top_alpha_components(
    raster: RasterEvidence,
    *,
    min_area_ratio: float = 0.04,
) -> list[tuple[int, int, int, int, int, int]]:
    if raster.alpha_mask is None:
        return []
    total = float(raster.alpha_mask.sum())
    if total <= 0:
        return []
    components = _connected_components_2d(raster.alpha_mask)
    min_area = total * min_area_ratio
    return sorted([c for c in components if c[5] >= min_area], key=lambda c: c[1])


def frame_bboxes_from_top_components(
    raster: RasterEvidence,
    view_box: tuple[float, float, float, float],
    frame_count: int,
    *,
    padding_px: int = 2,
) -> list[BBox] | None:
    """Game-style split: largest N alpha blobs left-to-right (feed-your-pet run strips)."""
    components = top_alpha_components(raster)
    if len(components) < frame_count:
        return None

    main = sorted(components[:frame_count], key=lambda c: c[1])
    vx, vy, vw, vh = view_box
    rw, rh = raster.width, raster.height
    pad_x = (padding_px / rw) * vw
    pad_y = (padding_px / rh) * vh

    bboxes: list[BBox] = []
    for _, x, y, w, h, _ in main:
        bbox = svg_to_mask_bbox((0, x, y, w, h, 0), raster, view_box)
        x1 = max(vx, bbox.x - pad_x)
        y1 = max(vy, bbox.y - pad_y)
        x2 = min(vx + vw, bbox.x2 + pad_x)
        y2 = min(vy + vh, bbox.y2 + pad_y)
        bboxes.append(
            BBox(
                x1,
                y1,
                max(1.0, x2 - x1),
                max(1.0, y2 - y1),
            )
        )
    return bboxes


def infer_pet_strip_frame_count(
    view_box: tuple[float, float, float, float],
    raster: RasterEvidence | None,
    display_width: float | None = None,
) -> int | None:
    """Guess run-strip frame count from viewBox/display ratio and alpha blobs."""
    vx, vy, vw, vh = view_box
    aspect = vw / max(vh, 1.0)
    if aspect < 2.2:
        return None

    if display_width and display_width > 0:
        unit_ratio = vw / display_width
        if unit_ratio >= 1.5:
            nearest = round(unit_ratio)
            if abs(unit_ratio - nearest) <= 0.25 and 2 <= nearest <= 16:
                return nearest

    if raster and raster.alpha_mask is not None:
        components = top_alpha_components(raster, min_area_ratio=0.06)
        if 2 <= len(components) <= 16:
            return len(components)

    if display_width and display_width > 0 and vw > display_width * 1.5:
        guess = max(2, min(16, int(round(vw / max(vh, 1.0)))))
        for preferred in (4, 6, 8, guess):
            frame_w = vw / preferred
            frame_aspect = frame_w / max(vh, 1.0)
            if 0.75 <= frame_aspect <= 1.8:
                return preferred
    return max(2, min(16, int(round(aspect / 1.35))))
