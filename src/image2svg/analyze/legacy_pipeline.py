from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from image2svg.analyze.geometry import (
    BBox,
    Point,
    color_luminance,
    distance,
    frame_to_core_matrix,
    is_eye_color,
    matrix_translate,
    normalize_point,
    parse_length,
    parse_view_box,
    path_bbox_from_d,
    union_bbox,
)

SVG_NS = "http://www.w3.org/2000/svg"
CAT_PARTS = (
    "bodySet",
    "headBase",
    "earSet",
    "eyeSet",
    "faceSet",
    "frontLegSet",
    "backLegSet",
    "tailSet",
    "patternOverlay",
    "furDetail",
    "outline",
    "shadow",
    "unknown",
)


@dataclass
class ParsedPath:
    path_id: str
    original_index: int
    d: str
    d_hash: str
    fill: str | None
    stroke: str | None
    opacity: float
    bbox: BBox
    centroid: Point
    has_transform: bool
    element_id: str | None


@dataclass
class SvgDocument:
    source_file: str
    asset_id: str
    view_box: tuple[float, float, float, float]
    width: float | None
    height: float | None
    paths: list[ParsedPath]
    group_count: int
    has_ids: bool
    has_groups: bool
    has_metadata: bool
    has_transforms: bool
    warnings: list[str] = field(default_factory=list)


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _asset_id_from_filename(filename: str) -> str:
    stem = re.sub(r"[^\w\-]+", "_", filename.rsplit(".", 1)[0].lower())
    return stem.strip("_") or "asset"


def _parse_paths(root: ET.Element) -> tuple[list[ParsedPath], int, bool, bool, bool, bool]:
    paths: list[ParsedPath] = []
    group_count = 0
    has_ids = False
    has_groups = False
    has_metadata = False
    has_transforms = False
    index = 0

    for elem in root.iter():
        tag = _local(elem.tag)
        if tag == "metadata":
            has_metadata = True
        if tag == "g":
            group_count += 1
            has_groups = True
        if elem.get("id"):
            has_ids = True
        if elem.get("transform"):
            has_transforms = True
        if tag != "path":
            continue
        d = elem.get("d")
        if not d:
            continue
        bbox = path_bbox_from_d(d)
        if bbox is None:
            continue
        fill = elem.get("fill")
        if fill == "none":
            fill = None
        stroke = elem.get("stroke")
        opacity_raw = elem.get("opacity") or elem.get("fill-opacity") or "1"
        try:
            opacity = float(opacity_raw)
        except ValueError:
            opacity = 1.0
        path_id = elem.get("id") or f"path_{index:04d}"
        d_hash = hashlib.sha1(d.encode("utf-8")).hexdigest()[:12]
        paths.append(
            ParsedPath(
                path_id=path_id,
                original_index=index,
                d=d,
                d_hash=d_hash,
                fill=fill,
                stroke=stroke,
                opacity=opacity,
                bbox=bbox,
                centroid=bbox.centroid,
                has_transform=bool(elem.get("transform")),
                element_id=elem.get("id"),
            )
        )
        index += 1

    return paths, group_count, has_ids, has_groups, has_metadata, has_transforms


def parse_svg(svg_text: str, source_file: str) -> SvgDocument:
    root = ET.fromstring(svg_text)
    view_box = parse_view_box(root.get("viewBox"))
    if view_box is None:
        w = parse_length(root.get("width"), 0.0) or 0.0
        h = parse_length(root.get("height"), 0.0) or 0.0
        view_box = (0.0, 0.0, w or 1.0, h or 1.0)
    width = parse_length(root.get("width"), view_box[2])
    height = parse_length(root.get("height"), view_box[3])
    paths, group_count, has_ids, has_groups, has_metadata, has_transforms = _parse_paths(root)
    warnings: list[str] = []
    if not paths:
        warnings.append("No path elements found in SVG")
    if not has_groups:
        warnings.append("Raw traced SVG has no semantic groups")
    if not has_ids:
        warnings.append("Paths have no stable ids — synthetic path ids were generated")
    warnings.append("Path order cannot be trusted as frame order")
    warnings.append("Frame coordinates must be normalized per frame")
    return SvgDocument(
        source_file=source_file,
        asset_id=_asset_id_from_filename(source_file),
        view_box=view_box,
        width=width,
        height=height,
        paths=paths,
        group_count=group_count,
        has_ids=has_ids,
        has_groups=has_groups,
        has_metadata=has_metadata,
        has_transforms=has_transforms,
        warnings=warnings,
    )


def _smooth(values: list[float], window: int = 5) -> list[float]:
    if not values:
        return []
    half = window // 2
    out: list[float] = []
    for i in range(len(values)):
        start = max(0, i - half)
        end = min(len(values), i + half + 1)
        out.append(sum(values[start:end]) / (end - start))
    return out


def _merge_peaks(indices: list[int], min_distance: int) -> list[int]:
    if not indices:
        return []
    merged = [indices[0]]
    for idx in indices[1:]:
        if idx - merged[-1] >= min_distance:
            merged.append(idx)
        elif idx > merged[-1]:
            merged[-1] = idx
    return merged


def _frame_count_from_histogram(paths: list[ParsedPath], content: BBox) -> int:
    """Count modality peaks in horizontal path density."""
    if not paths:
        return 1

    n_bins = min(96, max(24, int(content.w / max(content.h * 0.2, 16))))
    hist = [0.0] * n_bins
    for path in paths:
        rel = (path.centroid.x - content.x) / max(content.w, 1.0)
        rel = min(0.999999, max(0.0, rel))
        hist[int(rel * n_bins)] += max(1.0, path.bbox.area ** 0.5)

    smoothed = _smooth(hist, 5)
    peak_threshold = max(smoothed) * 0.18
    peaks: list[int] = []
    for i in range(1, len(smoothed) - 1):
        if smoothed[i] >= peak_threshold and smoothed[i] >= smoothed[i - 1] and smoothed[i] >= smoothed[i + 1]:
            peaks.append(i)

    min_peak_distance = max(3, n_bins // 10)
    peaks = _merge_peaks(peaks, min_peak_distance)
    return max(1, len(peaks))


def _score_equal_split(paths: list[ParsedPath], content: BBox, frame_count: int) -> tuple[int, float, int]:
    """Return (empty_slices, boundary_crossings, -avg_overlap) for sorting."""
    if frame_count <= 0:
        return (999, 999, 0.0)

    slice_w = content.w / frame_count
    counts = [0] * frame_count
    crossings = 0
    overlap_sum = 0.0

    for path in paths:
        left = path.bbox.x - content.x
        right = min(path.bbox.x2 - content.x, content.w - 1e-6)
        start_slice = min(frame_count - 1, max(0, int(left / slice_w)))
        end_slice = min(frame_count - 1, max(0, int(right / slice_w)))
        if start_slice != end_slice:
            crossings += 1

        cx = path.centroid.x
        idx = min(frame_count - 1, max(0, int((cx - content.x) / slice_w)))
        counts[idx] += 1
        slice_bbox = BBox(content.x + idx * slice_w, content.y, slice_w, content.h)
        overlap_sum += path.bbox.overlap_ratio(slice_bbox)

    empty = sum(1 for count in counts if count == 0)
    avg_overlap = overlap_sum / max(1, len(paths))
    return (empty, crossings, -avg_overlap)


def _frame_count_from_equal_split(paths: list[ParsedPath], content: BBox) -> int:
    """Pick frame count whose equal-width columns best explain path layout."""
    aspect = content.w / max(content.h, 1.0)
    if aspect < 1.4:
        return 1

    max_frames = min(16, max(2, int(aspect * 1.6)))
    best_n = 1
    best_key: tuple[int, float, float] | None = None

    for n in range(1, max_frames + 1):
        empty, crossings, neg_overlap = _score_equal_split(paths, content, n)
        slice_w = content.w / n
        frame_aspect = slice_w / max(content.h, 1.0)
        aspect_penalty = abs(frame_aspect - 0.85) * 0.15
        key = (empty, crossings + aspect_penalty * len(paths), neg_overlap)
        if best_key is None or key < best_key:
            best_key = key
            best_n = n

    return best_n


def _viewbox_bbox(doc: SvgDocument) -> BBox:
    vb = doc.view_box
    return BBox(vb[0], vb[1], vb[2], vb[3])


def _content_within_viewbox(content: BBox, view: BBox, tolerance: float = 0.35) -> bool:
    return (
        content.x >= view.x - view.w * tolerance
        and content.y >= view.y - view.h * tolerance
        and content.x2 <= view.x2 + view.w * tolerance
        and content.y2 <= view.y2 + view.h * tolerance
    )


def _frame_count_from_viewbox(view: BBox) -> int:
    aspect = view.w / max(view.h, 1.0)
    if aspect < 1.8:
        return 1

    best_n = 1
    best_diff = float("inf")
    for n in range(1, min(17, int(aspect * 1.4) + 2)):
        frame_w = view.w / n
        frame_aspect = frame_w / max(view.h, 1.0)
        diff = abs(frame_aspect - 0.85)
        if diff < best_diff:
            best_diff = diff
            best_n = n
    return max(1, best_n)


def _strip_content_bbox(doc: SvgDocument, paths: list[ParsedPath]) -> BBox:
    """Use viewBox for film sheets; fall back when path bounds are unreliable."""
    view = _viewbox_bbox(doc)
    content = union_bbox(p.bbox for p in paths)
    if content is None:
        return view

    if not _content_within_viewbox(content, view):
        return view

    if content.w >= view.w * 0.8:
        return BBox(view.x, view.y, view.w, view.h)
    return content


def _detect_frame_count(paths: list[ParsedPath], content: BBox, view: BBox | None = None) -> int:
    if not paths:
        return 1

    if view is not None:
        view_count = _frame_count_from_viewbox(view)
        view_aspect = view.w / max(view.h, 1.0)
        if view_aspect >= 2.5 and view_count >= 2:
            empty, _, _ = _score_equal_split(paths, view, view_count)
            if empty == 0:
                return view_count

    aspect = content.w / max(content.h, 1.0)
    if aspect < 1.25:
        return 1

    hist_count = _frame_count_from_histogram(paths, content)
    split_count = _frame_count_from_equal_split(paths, content)

    if hist_count == split_count:
        return hist_count

    hist_empty, _, _ = _score_equal_split(paths, content, hist_count)
    split_empty, _, _ = _score_equal_split(paths, content, split_count)

    if split_empty == 0 and hist_empty > 0:
        return split_count
    if hist_empty == 0 and split_empty > 0:
        return hist_count

    return max(hist_count, split_count)


def _detect_frame_count_vertical(paths: list[ParsedPath], content: BBox) -> int:
    if not paths:
        return 1

    aspect = content.h / max(content.w, 1.0)
    if aspect < 1.4:
        return 1

    n_bins = min(96, max(24, int(content.h / max(content.w * 0.2, 16))))
    hist = [0.0] * n_bins
    for path in paths:
        rel = (path.centroid.y - content.y) / max(content.h, 1.0)
        rel = min(0.999999, max(0.0, rel))
        hist[int(rel * n_bins)] += max(1.0, path.bbox.area ** 0.5)

    smoothed = _smooth(hist, 5)
    peak_threshold = max(smoothed) * 0.18
    peaks: list[int] = []
    for i in range(1, len(smoothed) - 1):
        if smoothed[i] >= peak_threshold and smoothed[i] >= smoothed[i - 1] and smoothed[i] >= smoothed[i + 1]:
            peaks.append(i)

    min_peak_distance = max(3, n_bins // 10)
    hist_count = max(1, len(_merge_peaks(peaks, min_peak_distance)))

    max_frames = min(16, max(2, int(aspect * 1.6)))
    best_n = 1
    best_key: tuple[int, float, float] | None = None
    for n in range(1, max_frames + 1):
        slice_h = content.h / n
        counts = [0] * n
        crossings = 0
        overlap_sum = 0.0
        for path in paths:
            top = path.bbox.y - content.y
            bottom = min(path.bbox.y2 - content.y, content.h - 1e-6)
            start_slice = min(n - 1, max(0, int(top / slice_h)))
            end_slice = min(n - 1, max(0, int(bottom / slice_h)))
            if start_slice != end_slice:
                crossings += 1
            cy = path.centroid.y
            idx = min(n - 1, max(0, int((cy - content.y) / slice_h)))
            counts[idx] += 1
            slice_bbox = BBox(content.x, content.y + idx * slice_h, content.w, slice_h)
            overlap_sum += path.bbox.overlap_ratio(slice_bbox)
        empty = sum(1 for count in counts if count == 0)
        avg_overlap = overlap_sum / max(1, len(paths))
        frame_aspect = (content.w / max(slice_h, 1.0))
        aspect_penalty = abs(frame_aspect - 0.85) * 0.15
        key = (empty, crossings + aspect_penalty * len(paths), -avg_overlap)
        if best_key is None or key < best_key:
            best_key = key
            best_n = n

    split_count = best_n
    if hist_count == split_count:
        return hist_count
    hist_empty, _, _ = _score_equal_split_vertical(paths, content, hist_count)
    split_empty, _, _ = _score_equal_split_vertical(paths, content, split_count)
    if split_empty == 0 and hist_empty > 0:
        return split_count
    if hist_empty == 0 and split_empty > 0:
        return hist_count
    return max(hist_count, split_count)


def _score_equal_split_vertical(paths: list[ParsedPath], content: BBox, frame_count: int) -> tuple[int, float, float]:
    if frame_count <= 0:
        return (999, 999, 0.0)
    slice_h = content.h / frame_count
    counts = [0] * frame_count
    crossings = 0
    overlap_sum = 0.0
    for path in paths:
        top = path.bbox.y - content.y
        bottom = min(path.bbox.y2 - content.y, content.h - 1e-6)
        start_slice = min(frame_count - 1, max(0, int(top / slice_h)))
        end_slice = min(frame_count - 1, max(0, int(bottom / slice_h)))
        if start_slice != end_slice:
            crossings += 1
        cy = path.centroid.y
        idx = min(frame_count - 1, max(0, int((cy - content.y) / slice_h)))
        counts[idx] += 1
        slice_bbox = BBox(content.x, content.y + idx * slice_h, content.w, slice_h)
        overlap_sum += path.bbox.overlap_ratio(slice_bbox)
    empty = sum(1 for count in counts if count == 0)
    avg_overlap = overlap_sum / max(1, len(paths))
    return (empty, crossings, -avg_overlap)


def _detect_strip(
    doc: SvgDocument,
) -> tuple[int, str, list[BBox], list[float], BBox | None]:
    view = _viewbox_bbox(doc)
    content = _strip_content_bbox(doc, doc.paths)

    frame_count = _detect_frame_count(doc.paths, content, view)
    direction = "horizontal"
    if content.w <= content.h * 0.8 and frame_count <= 1:
        direction = "vertical" if content.h > content.w * 1.5 else "unknown"
    elif frame_count <= 1:
        direction = "unknown"
    elif content.w < content.h * 1.25:
        direction = "vertical"
        frame_count = _detect_frame_count_vertical(doc.paths, content)

    frame_bboxes: list[BBox] = []
    gaps: list[float] = []
    if frame_count <= 1:
        frame_bboxes = [BBox(content.x, content.y, content.w, content.h)]
    elif direction == "horizontal":
        slice_w = content.w / frame_count
        for i in range(frame_count):
            frame_bboxes.append(BBox(content.x + i * slice_w, content.y, slice_w, content.h))
            if i > 0:
                gaps.append(slice_w)
    elif direction == "vertical":
        slice_h = content.h / frame_count
        for i in range(frame_count):
            frame_bboxes.append(BBox(content.x, content.y + i * slice_h, content.w, slice_h))
            if i > 0:
                gaps.append(slice_h)
    else:
        frame_bboxes = [BBox(content.x, content.y, content.w, content.h)]

    return frame_count, direction, frame_bboxes, gaps, content


def _assign_paths_to_frame(paths: list[ParsedPath], frame_bboxes: list[BBox]) -> dict[int, list[ParsedPath]]:
    buckets: dict[int, list[ParsedPath]] = defaultdict(list)
    for path in paths:
        best_idx = 0
        best_score = -1.0
        for idx, frame in enumerate(frame_bboxes):
            overlap = path.bbox.overlap_ratio(frame)
            center_score = 1.0 if frame.contains_point(path.centroid) else 0.0
            score = overlap * 0.7 + center_score * 0.3
            if score > best_score:
                best_score = score
                best_idx = idx
        buckets[best_idx].append(path)
    return buckets


def _estimate_core_body(content: BBox, paths: list[ParsedPath]) -> BBox:
    if not paths:
        return content
    trim_x = content.w * 0.12
    trim_y = content.h * 0.08
    core = BBox(
        content.x + trim_x,
        content.y + trim_y,
        content.w - trim_x * 2,
        content.h - trim_y * 2,
    )
    dense: list[tuple[BBox, float]] = []
    for path in paths:
        if path.bbox.area <= 0:
            continue
        if path.bbox.w > content.w * 0.55 and path.bbox.h > content.h * 0.55:
            dense.append((path.bbox, path.bbox.area))
    if dense:
        dense.sort(key=lambda item: item[1], reverse=True)
        merged = union_bbox(item[0] for item in dense[:6])
        if merged is not None:
            core = BBox(
                max(content.x, merged.x),
                max(content.y, merged.y),
                min(content.w, merged.w * 0.92),
                min(content.h * 0.72, merged.h * 0.85),
            )
    return core


def _guess_background(paths: list[ParsedPath]) -> str:
    fills = [p.fill for p in paths if p.fill]
    if not fills:
        return "transparent"
    transparentish = sum(1 for f in fills if f.lower() in {"none", "transparent"})
    if transparentish / max(1, len(fills)) > 0.5:
        return "transparent"
    top = Counter(fills).most_common(1)
    if top and top[0][1] / len(fills) > 0.6:
        return "solid"
    return "mixed"


def _analyze_colors(paths: list[ParsedPath]) -> dict[str, Any]:
    fills = [p.fill.lower() for p in paths if p.fill and p.fill.lower() not in {"none", "transparent"}]
    counter = Counter(fills)
    palette = []
    for color, count in counter.most_common(24):
        area = sum(p.bbox.area for p in paths if (p.fill or "").lower() == color)
        role = "unknown"
        lum = color_luminance(color)
        if is_eye_color(color):
            role = "eyeBlue"
        elif lum < 0.15:
            role = "outline" if count < len(paths) * 0.05 else "darkPoint"
        elif lum > 0.85:
            role = "highlight"
        elif 0.35 <= lum <= 0.75:
            role = "mainFur"
        palette.append(
            {
                "color": color,
                "count": count,
                "areaApprox": round(area, 2),
                "roleGuess": role,
            }
        )
    return {
        "palette": palette,
        "dominantFurColors": [c["color"] for c in palette if c["roleGuess"] == "mainFur"][:5],
        "eyeCandidateColors": [c["color"] for c in palette if c["roleGuess"] == "eyeBlue"][:5],
        "darkPointColors": [c["color"] for c in palette if c["roleGuess"] == "darkPoint"][:5],
        "outlineColors": [c["color"] for c in palette if c["roleGuess"] == "outline"][:5],
        "colorClusters": [],
    }


def _view_analysis(core: BBox, paths: list[ParsedPath]) -> dict[str, Any]:
    eye_paths = [p for p in paths if p.fill and is_eye_color(p.fill)]
    eye_count = len(eye_paths)
    aspect = core.aspect_ratio
    body_view = "unknown"
    if aspect >= 1.55:
        left_mass = sum(p.bbox.area for p in paths if p.centroid.x < core.centroid.x)
        right_mass = sum(p.bbox.area for p in paths if p.centroid.x >= core.centroid.x)
        body_view = "right" if right_mass >= left_mass else "left"
    elif aspect <= 0.95:
        body_view = "front"
    elif 0.95 < aspect < 1.25:
        body_view = "front"

    head_view = body_view
    if eye_count >= 2 and body_view in {"right", "left"}:
        head_view = "frontRight" if body_view == "right" else "frontLeft"

    tail_paths = [p for p in paths if p.centroid.x < core.x or p.centroid.x > core.x2]
    tail_view = "unknown"
    if tail_paths:
        avg_y = sum(p.centroid.y for p in tail_paths) / len(tail_paths)
        if avg_y < core.centroid.y:
            tail_view = "upCurve"
        elif avg_y > core.y2 - core.h * 0.15:
            tail_view = "horizontal"
        else:
            tail_view = "leftSide" if tail_paths[0].centroid.x < core.centroid.x else "rightSide"

    return {
        "bodyView": body_view,
        "headView": head_view,
        "tailView": tail_view,
        "confidence": {
            "body": round(0.55 + min(0.35, aspect / 4), 2),
            "head": round(0.5 + min(0.4, eye_count * 0.15), 2),
            "tail": 0.55 if tail_paths else 0.25,
        },
        "evidence": {
            "eyeCountVisible": eye_count,
            "bodyAspectRatio": round(aspect, 2),
            "tailRootSide": (
                "left"
                if any(p.centroid.x < core.x for p in tail_paths)
                else "right"
                if tail_paths
                else "unknown"
            ),
            "pawArrangement": "symmetric" if body_view == "front" else "sideStaggered",
        },
    }


def _landmarks(core: BBox, content: BBox, view: dict[str, Any]) -> dict[str, Any]:
    body_center = normalize_point(core.centroid, core)
    head_center = Point(core.centroid.x, core.y + core.h * 0.28)
    neck = Point(core.centroid.x, core.y + core.h * 0.42)
    tail_root = Point(core.x + core.w * 0.12, core.y + core.h * 0.58)
    if view["evidence"].get("tailRootSide") == "right":
        tail_root = Point(core.x2 - core.w * 0.12, core.y + core.h * 0.58)

    def lm(point: Point, confidence: float, source: str) -> dict[str, Any]:
        norm = normalize_point(
            Point(core.x + point.x * core.w if point.x <= 1 else point.x, core.y + point.y * core.h if point.y <= 1 else point.y),
            core,
        )
        return {
            "x": round(norm.x, 4),
            "y": round(norm.y, 4),
            "coordinate": "coreLocal",
            "confidence": confidence,
            "source": source,
        }

    return {
        "headCenter": lm(normalize_point(head_center, core), 0.72, "silhouette"),
        "bodyCenter": lm(body_center, 0.86, "silhouette"),
        "neck": lm(normalize_point(neck, core), 0.68, "silhouette"),
        "tailRoot": lm(normalize_point(tail_root, core), 0.62, "skeletonFit"),
        "baseline": {
            "y": round(content.y2, 2),
            "confidence": 0.6,
            "contactPoints": [Point(content.x + content.w * 0.25, content.y2).as_dict(), Point(content.x + content.w * 0.75, content.y2).as_dict()],
        },
    }


def _skeleton_fit(view: dict[str, Any], landmarks: dict[str, Any]) -> dict[str, Any]:
    body_template = f"cat_{view['bodyView']}" if view["bodyView"] != "unknown" else "cat_front"
    head_template = f"cat_{view['headView']}" if view["headView"] != "unknown" else "cat_front"
    template_id = "mixed_head_body" if body_template != head_template else body_template.replace("cat_", "cat_")
    if view["bodyView"] != view["headView"]:
        template_id = "mixed_head_body"
    else:
        template_id = body_template

    body = landmarks.get("bodyCenter", {"x": 0.5, "y": 0.58})
    head = landmarks.get("headCenter", {"x": 0.5, "y": 0.32})
    tail = landmarks.get("tailRoot", {"x": 0.18, "y": 0.52})
    return {
        "templateId": template_id,
        "bodyTemplateId": body_template,
        "headTemplateId": head_template,
        "tailTemplateId": "long_plumed_tail",
        "fitTransform": [1, 0, 0, 1, 0, 0],
        "bones": {
            "body": {
                "name": "body",
                "root": {"x": body["x"], "y": body["y"]},
                "angle": 0,
                "confidence": 0.86,
            },
            "head": {
                "name": "head",
                "parent": "body",
                "root": {"x": head["x"], "y": head["y"]},
                "angle": 8 if view["headView"].endswith("Right") else -8 if view["headView"].endswith("Left") else 0,
                "confidence": 0.78,
            },
            "tail": {
                "name": "tail",
                "parent": "body",
                "root": {"x": tail["x"], "y": tail["y"]},
                "tip": {"x": max(0.02, tail["x"] - 0.16), "y": max(0.05, tail["y"] - 0.44)},
                "angle": -48,
                "confidence": 0.7,
            },
        },
        "confidence": 0.78,
        "errors": {
            "missingLandmarks": [],
            "unstableBones": [],
            "lowConfidenceBones": [],
        },
    }


def _part_zones(core: BBox, skeleton: dict[str, Any], frame_index: int) -> dict[str, Any]:
    def zone(part: str, x: float, y: float, w: float, h: float, bones: list[str]) -> dict[str, Any]:
        return {
            "zoneId": f"frame_{frame_index}_{part}_zone",
            "part": part,
            "shape": "ellipse",
            "bbox": {"x": round(x, 3), "y": round(y, 3), "w": round(w, 3), "h": round(h, 3)},
            "center": {"x": round(x + w / 2, 3), "y": round(y + h / 2, 3)},
            "generatedFromBones": bones,
            "overlapRules": {
                "minOverlapRatio": 0.28,
                "distanceWeight": 0.35,
                "colorWeight": 0.2,
                "zOrderWeight": 0.1,
            },
        }

    return {
        "zones": {
            "headBase": zone("headBase", 0.32, 0.08, 0.36, 0.32, ["head"]),
            "eyeSet": zone("eyeSet", 0.34, 0.18, 0.32, 0.14, ["head"]),
            "bodySet": zone("bodySet", 0.22, 0.34, 0.56, 0.42, ["body"]),
            "tailSet": zone("tailSet", 0.0, 0.08, 0.24, 0.55, ["tail"]),
            "frontLegSet": zone("frontLegSet", 0.28, 0.62, 0.22, 0.28, ["body"]),
            "backLegSet": zone("backLegSet", 0.48, 0.62, 0.22, 0.28, ["body"]),
        }
    }


def _assign_path_part(path: ParsedPath, core: BBox, zones: dict[str, Any], z_norm: float) -> dict[str, Any]:
    norm = normalize_point(path.centroid, core)
    candidates: list[dict[str, Any]] = []
    best_part = "unknown"
    best_score = 0.0
    for part, zone in zones["zones"].items():
        zb = zone["bbox"]
        zone_bbox = BBox(zb["x"], zb["y"], zb["w"], zb["h"])
        center = Point(zb["x"] + zb["w"] / 2, zb["y"] + zb["h"] / 2)
        dist_score = max(0.0, 1.0 - distance(norm, center) * 1.4)
        overlap = path.bbox.overlap_ratio(
            BBox(core.x + zone_bbox.x * core.w, core.y + zone_bbox.y * core.h, zone_bbox.w * core.w, zone_bbox.h * core.h)
        )
        color_score = 0.35 if path.fill and is_eye_color(path.fill) and part == "eyeSet" else 0.0
        score = dist_score * 0.45 + overlap * 0.35 + color_score
        reason = []
        if dist_score > 0.4:
            reason.append("centroidInZone")
        if overlap > 0.1:
            reason.append("bboxOverlap")
        if color_score:
            reason.append("eyeColor")
        candidates.append({"part": part, "score": round(score, 3), "reason": reason or ["heuristic"]})
        if score > best_score:
            best_score = score
            best_part = part

    if path.fill and color_luminance(path.fill) < 0.12 and path.bbox.area < core.area * 0.02:
        best_part = "outline"
        best_score = max(best_score, 0.55)

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return {
        "pathId": path.path_id,
        "originalIndex": path.original_index,
        "dHash": path.d_hash,
        "style": {"fill": path.fill, "stroke": path.stroke, "opacity": path.opacity},
        "geometry": {
            "bbox": path.bbox.as_dict(),
            "centroid": path.centroid.as_dict(),
            "areaApprox": round(path.bbox.area, 2),
            "aspectRatio": round(path.bbox.aspect_ratio, 3),
            "isThin": path.bbox.aspect_ratio > 4 or path.bbox.aspect_ratio < 0.25,
            "isLarge": path.bbox.area > core.area * 0.08,
            "isDark": bool(path.fill and color_luminance(path.fill) < 0.2),
        },
        "zOrder": {"originalIndex": path.original_index, "normalizedZ": round(z_norm, 4)},
        "frameAssignment": {
            "frameIndex": 0,
            "confidence": 0.8,
            "reason": "bboxOverlap",
        },
        "candidates": candidates[:4],
        "finalPart": best_part if best_score >= 0.25 else "unknown",
    }


def _semantic_parts(frame_index: int, path_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in path_rows:
        part = row.get("finalPart") or "unknown"
        groups[part].append(row)
    semantic: list[dict[str, Any]] = []
    for part, rows in groups.items():
        if part == "unknown":
            continue
        boxes = [BBox(**row["geometry"]["bbox"]) for row in rows]
        merged = union_bbox(boxes)
        if merged is None:
            continue
        colors = Counter(row["style"].get("fill") for row in rows if row["style"].get("fill"))
        z_vals = [row["zOrder"]["originalIndex"] for row in rows]
        semantic.append(
            {
                "part": part,
                "frameIndex": frame_index,
                "pathIds": [row["pathId"] for row in rows],
                "bbox": merged.as_dict(),
                "centroid": merged.centroid.as_dict(),
                "dominantColors": [c for c, _ in colors.most_common(4)],
                "zRange": {"min": min(z_vals), "max": max(z_vals)},
                "confidence": round(min(0.95, 0.45 + len(rows) * 0.04), 2),
                "visibility": "visible" if len(rows) >= 1 else "missing",
                "role": "outline" if part == "outline" else "base",
            }
        )
    return semantic


def _frame_quality(
    frame_index: int,
    semantic_parts: list[dict[str, Any]],
    view: dict[str, Any],
    path_rows: list[dict[str, Any]],
    core: BBox,
    content: BBox,
) -> dict[str, Any]:
    parts = {p["part"] for p in semantic_parts}
    unassigned = sum(1 for row in path_rows if row["finalPart"] == "unknown")
    warnings: list[dict[str, Any]] = []
    if view["bodyView"] != view["headView"] and view["bodyView"] != "unknown" and view["headView"] != "unknown":
        warnings.append(
            {
                "code": "VIEW_AMBIGUOUS",
                "severity": "warning",
                "part": "headBase",
                "message": "Body and head views differ — use mixed skeleton template.",
                "suggestedFix": f"Set bodyView={view['bodyView']} and headView={view['headView']}.",
            }
        )
    if content.w > core.w * 1.35:
        warnings.append(
            {
                "code": "TAIL_BREAKS_BBOX",
                "severity": "warning",
                "part": "tailSet",
                "message": "Tail or appendages extend beyond core body — exclude from scale normalization.",
            }
        )
    if unassigned:
        warnings.append(
            {
                "code": "PATH_UNASSIGNED",
                "severity": "info",
                "frameIndex": frame_index,
                "message": f"{unassigned} paths remain unassigned.",
            }
        )
    score = 0.82
    score -= 0.05 * len(warnings)
    score -= min(0.2, unassigned * 0.01)
    return {
        "score": round(max(0.0, score), 2),
        "errors": [],
        "warnings": warnings,
        "checks": {
            "hasBody": "bodySet" in parts,
            "hasHead": "headBase" in parts,
            "hasEyes": "eyeSet" in parts,
            "hasTail": "tailSet" in parts,
            "hasLegs": "frontLegSet" in parts or "backLegSet" in parts,
            "baselineStable": True,
            "scaleStable": True,
            "partCountReasonable": len(semantic_parts) >= 3,
            "viewRecognized": view["bodyView"] != "unknown",
            "skeletonFitOk": True,
        },
    }


def _build_frame_analysis(
    frame_index: int,
    frame_bbox: BBox,
    paths: list[ParsedPath],
    total_paths: int,
) -> dict[str, Any]:
    content = union_bbox(p.bbox for p in paths) or frame_bbox
    silhouette = union_bbox(p.bbox for p in paths) or content
    core = _estimate_core_body(content, paths)
    view = _view_analysis(core, paths)
    landmarks = _landmarks(core, content, view)
    skeleton = _skeleton_fit(view, landmarks)
    part_zones = _part_zones(core, skeleton, frame_index)
    z_max = max(1, total_paths - 1)
    path_rows = []
    for path in paths:
        row = _assign_path_part(path, core, part_zones, path.original_index / z_max)
        row["frameAssignment"]["frameIndex"] = frame_index
        path_rows.append(row)
    semantic_parts = _semantic_parts(frame_index, path_rows)
    quality = _frame_quality(frame_index, semantic_parts, view, path_rows, core, content)

    return {
        "frameIndex": frame_index,
        "bounds": {
            "frameBBox": frame_bbox.as_dict(),
            "contentBBox": content.as_dict(),
            "silhouetteBBox": silhouette.as_dict(),
            "coreBodyBBox": core.as_dict(),
        },
        "coordinateSystems": {
            "globalToFrame": matrix_translate(-frame_bbox.x, -frame_bbox.y),
            "frameToCore": frame_to_core_matrix(frame_bbox, core),
            "coreToCanonical": [1, 0, 0, 1, 0, 0],
        },
        "silhouette": {
            "area": round(silhouette.area, 2),
            "contourCount": len(paths),
            "bbox": silhouette.as_dict(),
            "centroid": silhouette.centroid.as_dict(),
            "orientation": {
                "majorAxisAngle": 0,
                "minorAxisAngle": 90,
                "elongation": round(silhouette.aspect_ratio, 3),
            },
            "symmetry": {
                "verticalSymmetryScore": 0.55,
                "horizontalSymmetryScore": 0.48,
                "likelyFacing": view["bodyView"] if view["bodyView"] != "unknown" else "unknown",
            },
            "extremities": {
                "topMost": Point(content.x + content.w / 2, content.y).as_dict(),
                "bottomMost": Point(content.x + content.w / 2, content.y2).as_dict(),
                "leftMost": Point(content.x, content.y + content.h / 2).as_dict(),
                "rightMost": Point(content.x2, content.y + content.h / 2).as_dict(),
            },
            "appendages": {
                "possibleTailRegions": [BBox(content.x, content.y, content.w * 0.18, content.h).as_dict()],
                "possibleLegRegions": [BBox(content.x + content.w * 0.2, content.y2 - content.h * 0.25, content.w * 0.6, content.h * 0.25).as_dict()],
                "possibleEarRegions": [BBox(core.x + core.w * 0.15, core.y, core.w * 0.7, core.h * 0.25).as_dict()],
                "possibleWhiskerRegions": [],
            },
        },
        "coreBody": {
            "method": "largestDenseRegion",
            "bbox": core.as_dict(),
            "centroid": core.centroid.as_dict(),
            "area": round(core.area, 2),
            "excludedRegions": {
                "tail": [BBox(content.x, content.y, max(0.0, core.x - content.x), content.h).as_dict()],
                "whiskers": [],
                "furTips": [],
                "detachedNoise": [],
            },
            "bodyMass": {
                "center": core.centroid.as_dict(),
                "radiusX": round(core.w / 2, 2),
                "radiusY": round(core.h / 2, 2),
                "confidence": 0.74,
            },
            "headMass": {
                "center": normalize_point(Point(core.centroid.x, core.y + core.h * 0.28), core).as_dict(),
                "radiusX": round(core.w * 0.22, 2),
                "radiusY": round(core.h * 0.18, 2),
                "confidence": 0.68,
            },
        },
        "view": view,
        "pose": {
            "poseType": "idle",
            "bodyPose": {"spineAngle": 0, "bodySquash": 1, "bodyStretch": 1, "bodyLean": 0},
            "headPose": {"tilt": 0, "offsetX": 0, "offsetY": 0},
            "legPose": {
                "frontLeft": {"contact": "grounded", "extension": "neutral"},
                "frontRight": {"contact": "grounded", "extension": "neutral"},
                "backLeft": {"contact": "grounded", "extension": "neutral"},
                "backRight": {"contact": "grounded", "extension": "neutral"},
            },
            "tailPose": {
                "curveType": view["tailView"] if view["tailView"] != "unknown" else "unknown",
                "rootAngle": -48,
                "lengthClass": "long",
            },
        },
        "landmarks": landmarks,
        "skeleton": skeleton,
        "partZones": part_zones,
        "pathAssignments": path_rows,
        "semanticParts": semantic_parts,
        "quality": quality,
    }


def _part_analysis(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for frame in frames:
        idx = frame["frameIndex"]
        for group in frame["semanticParts"]:
            rows.append(
                {
                    "part": group["part"],
                    "frameIndex": idx,
                    "pathIds": group["pathIds"],
                    "bbox": group["bbox"],
                    "centroid": group["centroid"],
                    "dominantColors": group["dominantColors"],
                    "confidence": group["confidence"],
                    "visibility": group["visibility"],
                    "role": group["role"],
                }
            )
    return rows


def _temporal_analysis(frames: list[dict[str, Any]]) -> dict[str, Any]:
    if len(frames) < 2:
        return {
            "frameCount": len(frames),
            "framePairs": [],
            "partTracks": {},
            "motionSummary": {
                "loopable": len(frames) >= 2,
                "smoothnessScore": 1.0 if len(frames) <= 1 else 0.75,
                "baselineStability": 1.0,
                "scaleStability": 1.0,
                "viewConsistency": 1.0,
            },
            "warnings": [],
        }

    tracks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for frame in frames:
        idx = frame["frameIndex"]
        for group in frame["semanticParts"]:
            tracks[group["part"]].append(
                {
                    "frameIndex": idx,
                    "groupId": f"{group['part']}_{idx}",
                    "bbox": group["bbox"],
                    "centroid": group["centroid"],
                    "confidence": group["confidence"],
                    "visible": group["visibility"] == "visible",
                }
            )

    part_tracks: dict[str, Any] = {}
    warnings: list[str] = []
    for part, entries in tracks.items():
        areas = [e["bbox"]["w"] * e["bbox"]["h"] for e in entries]
        area_consistency = 1.0
        if len(areas) > 1 and areas[0] > 0:
            max_delta = max(abs(a - areas[0]) / areas[0] for a in areas[1:])
            area_consistency = max(0.0, 1.0 - max_delta)
            if max_delta > 1.5:
                warnings.append(f"{part} area changed more than 150% across frames")
        part_tracks[part] = {
            "part": part,
            "frames": entries,
            "stability": {
                "areaConsistency": round(area_consistency, 3),
                "colorConsistency": 0.8,
                "motionContinuity": 0.72,
                "identityConfidence": 0.76,
            },
            "issues": [w for w in warnings if w.startswith(part)],
        }

    pairs: list[dict[str, Any]] = []
    for i in range(len(frames) - 1):
        a = frames[i]
        b = frames[i + 1]
        part_deltas: dict[str, Any] = {}
        b_parts = {g["part"]: g for g in b["semanticParts"]}
        for group in a["semanticParts"]:
            part = group["part"]
            other = b_parts.get(part)
            if not other:
                part_deltas[part] = {
                    "bboxDelta": 1.0,
                    "centroidDelta": 999,
                    "areaDeltaRatio": 1.0,
                    "zOrderChanged": True,
                    "visibilityChanged": True,
                }
                continue
            ca = Point(**group["centroid"])
            cb = Point(**other["centroid"])
            part_deltas[part] = {
                "bboxDelta": round(abs(group["bbox"]["w"] - other["bbox"]["w"]), 2),
                "centroidDelta": round(distance(ca, cb), 2),
                "areaDeltaRatio": round(
                    abs(group["bbox"]["w"] * group["bbox"]["h"] - other["bbox"]["w"] * other["bbox"]["h"])
                    / max(1.0, group["bbox"]["w"] * group["bbox"]["h"]),
                    3,
                ),
                "zOrderChanged": group["zRange"]["min"] != other["zRange"]["min"],
                "visibilityChanged": group["visibility"] != other["visibility"],
            }
        pairs.append(
            {
                "fromFrame": a["frameIndex"],
                "toFrame": b["frameIndex"],
                "registration": {
                    "coreTransform": [1, 0, 0, 1, 0, 0],
                    "estimatedMotion": "smallDelta",
                },
                "anchorDeltas": {
                    "bodyCenter": {
                        "dx": round(b["landmarks"]["bodyCenter"]["x"] - a["landmarks"]["bodyCenter"]["x"], 4),
                        "dy": round(b["landmarks"]["bodyCenter"]["y"] - a["landmarks"]["bodyCenter"]["y"], 4),
                        "distance": round(
                            distance(
                                Point(a["landmarks"]["bodyCenter"]["x"], a["landmarks"]["bodyCenter"]["y"]),
                                Point(b["landmarks"]["bodyCenter"]["x"], b["landmarks"]["bodyCenter"]["y"]),
                            ),
                            4,
                        ),
                    }
                },
                "partDeltas": part_deltas,
            }
        )

    core_areas = [f["bounds"]["coreBodyBBox"]["w"] * f["bounds"]["coreBodyBBox"]["h"] for f in frames]
    scale_stability = 1.0
    if len(core_areas) > 1 and core_areas[0] > 0:
        scale_stability = max(0.0, 1.0 - max(abs(a - core_areas[0]) / core_areas[0] for a in core_areas[1:]))

    views = [f["view"]["bodyView"] for f in frames]
    view_consistency = len(set(views)) == 1

    return {
        "frameCount": len(frames),
        "framePairs": pairs,
        "partTracks": part_tracks,
        "motionSummary": {
            "loopable": len(frames) >= 2,
            "smoothnessScore": round(0.65 + scale_stability * 0.25, 2),
            "baselineStability": 0.78,
            "scaleStability": round(scale_stability, 3),
            "viewConsistency": 1.0 if view_consistency else 0.55,
        },
        "warnings": warnings,
    }


def _quality_report(frames: list[dict[str, Any]], temporal: dict[str, Any], asset_warnings: list[str]) -> dict[str, Any]:
    frame_scores = [f["quality"]["score"] for f in frames]
    overall = sum(frame_scores) / max(1, len(frame_scores))
    issues: list[dict[str, Any]] = []
    for frame in frames:
        issues.extend(frame["quality"]["warnings"])
    for warning in temporal.get("warnings", []):
        issues.append(
            {
                "code": "MUTATED_PART",
                "severity": "warning",
                "message": warning,
            }
        )
    for warning in asset_warnings:
        issues.append({"code": "PATH_UNASSIGNED", "severity": "info", "message": warning})
    return {
        "score": round(overall, 2),
        "frameScores": frame_scores,
        "issueCount": len(issues),
        "errors": [i for i in issues if i.get("severity") == "error"],
        "warnings": [i for i in issues if i.get("severity") == "warning"],
        "info": [i for i in issues if i.get("severity") == "info"],
        "summary": {
            "framesAnalyzed": len(frames),
            "criticalIssues": sum(1 for i in issues if i.get("severity") == "error"),
            "needsManualReview": overall < 0.7 or bool(temporal.get("warnings")),
        },
    }


def analyze_svg(svg_text: str, source_file: str) -> dict[str, Any]:
    doc = parse_svg(svg_text, source_file)
    frame_count, direction, frame_bboxes, gaps, content_bbox = _detect_strip(doc)
    path_buckets = _assign_paths_to_frame(doc.paths, frame_bboxes)
    color_analysis = _analyze_colors(doc.paths)

    asset_analysis = {
        "assetId": doc.asset_id,
        "sourceFile": doc.source_file,
        "svg": {
            "viewBox": list(doc.view_box),
            "width": doc.width,
            "height": doc.height,
            "pathCount": len(doc.paths),
            "groupCount": doc.group_count,
            "hasIds": doc.has_ids,
            "hasGroups": doc.has_groups,
            "hasMetadata": doc.has_metadata,
            "hasTransforms": doc.has_transforms,
        },
        "content": {
            "detectedObjectCount": frame_count,
            "estimatedFrameCount": frame_count,
            "stripDirection": direction if direction != "unknown" else "horizontal" if frame_count > 1 else "unknown",
            "backgroundType": _guess_background(doc.paths),
        },
        "colorAnalysis": color_analysis,
        "warnings": doc.warnings,
    }

    strip_analysis = {
        "frameCount": frame_count,
        "layout": {
            "direction": direction if frame_count > 1 else "horizontal" if direction == "horizontal" else direction,
            "frameOrder": "leftToRight" if direction == "horizontal" else "topToBottom" if direction == "vertical" else "unknown",
            "spacingMode": "equal" if frame_count > 1 else "unknown",
        },
        "globalBounds": {
            "contentBBox": (content_bbox or BBox(*doc.view_box)).as_dict(),
            "frameBBoxes": [b.as_dict() for b in frame_bboxes],
            "gaps": [round(g, 2) for g in gaps],
            "baseline": (content_bbox.y2 if content_bbox else doc.view_box[1] + doc.view_box[3]),
        },
        "estimatedAnimationType": "idle" if frame_count <= 4 else "unknown",
        "normalizationStrategy": {
            "useFullFrameBBox": False,
            "useCoreBodyBBox": True,
            "ignoreTailForScale": True,
            "ignoreWhiskersForScale": True,
        },
    }

    frames = [
        _build_frame_analysis(i, frame_bboxes[i], path_buckets.get(i, []), len(doc.paths))
        for i in range(frame_count)
    ]
    part_analysis = _part_analysis(frames)
    temporal_analysis = _temporal_analysis(frames)
    quality_report = _quality_report(frames, temporal_analysis, doc.warnings)

    return {
        "version": "1.0",
        "assetAnalysis": asset_analysis,
        "stripAnalysis": strip_analysis,
        "frameAnalysis": frames,
        "partAnalysis": part_analysis,
        "temporalAnalysis": temporal_analysis,
        "qualityReport": quality_report,
        "exportPlan": {
            "semanticSvg": f"{doc.asset_id}.semantic.svg",
            "animationJson": f"{doc.asset_id}.animation.json",
            "debugPreview": f"{doc.asset_id}.debug.png",
        },
    }
