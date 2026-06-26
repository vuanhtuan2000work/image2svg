"""Pass 0 — SVG normalization: all shapes → paths + geometry metrics."""

from __future__ import annotations

import hashlib
import math
import re
import xml.etree.ElementTree as ET
from typing import Any

from svg.path import Arc, CubicBezier, Line, QuadraticBezier, parse_path

from svg_analyze.geometry import BBox, Point, parse_length, parse_view_box, path_bbox_exact_from_d, path_bbox_from_d
from svg_analyze.types import CurvatureStats, NormalizedPath

SVG_NS = "http://www.w3.org/2000/svg"
_SAMPLE_STEPS = 12


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _asset_id_from_filename(filename: str) -> str:
    stem = re.sub(r"[^\w\-]+", "_", filename.rsplit(".", 1)[0].lower())
    return stem.strip("_") or "asset"


def _parse_style(elem: ET.Element) -> tuple[str | None, str | None, float, str]:
    fill = elem.get("fill")
    stroke = elem.get("stroke")
    opacity_raw = elem.get("opacity") or elem.get("fill-opacity") or "1"
    try:
        opacity = float(opacity_raw)
    except ValueError:
        opacity = 1.0
    fill_rule = (elem.get("fill-rule") or "nonzero").lower()
    if fill == "none":
        fill = None
    return fill, stroke, opacity, fill_rule


def _rect_to_path(elem: ET.Element) -> str | None:
    x = float(elem.get("x", 0))
    y = float(elem.get("y", 0))
    w = float(elem.get("width", 0))
    h = float(elem.get("height", 0))
    if w <= 0 or h <= 0:
        return None
    rx = float(elem.get("rx", 0) or elem.get("ry", 0) or 0)
    if rx > 0:
        rx = min(rx, w / 2, h / 2)
        return (
            f"M{x + rx},{y} H{x + w - rx} A{rx},{rx} 0 0 1 {x + w},{y + rx} "
            f"V{y + h - rx} A{rx},{rx} 0 0 1 {x + w - rx},{y + h} "
            f"H{x + rx} A{rx},{rx} 0 0 1 {x},{y + h - rx} V{y + rx} "
            f"A{rx},{rx} 0 0 1 {x + rx},{y} Z"
        )
    return f"M{x},{y} H{x + w} V{y + h} H{x} Z"


def _circle_to_path(elem: ET.Element) -> str | None:
    cx = float(elem.get("cx", 0))
    cy = float(elem.get("cy", 0))
    r = float(elem.get("r", 0))
    if r <= 0:
        return None
    return f"M{cx - r},{cy} A{r},{r} 0 1 0 {cx + r},{cy} A{r},{r} 0 1 0 {cx - r},{cy} Z"


def _ellipse_to_path(elem: ET.Element) -> str | None:
    cx = float(elem.get("cx", 0))
    cy = float(elem.get("cy", 0))
    rx = float(elem.get("rx", 0))
    ry = float(elem.get("ry", 0))
    if rx <= 0 or ry <= 0:
        return None
    return f"M{cx - rx},{cy} A{rx},{ry} 0 1 0 {cx + rx},{cy} A{rx},{ry} 0 1 0 {cx - rx},{cy} Z"


def _line_to_path(elem: ET.Element) -> str | None:
    x1 = float(elem.get("x1", 0))
    y1 = float(elem.get("y1", 0))
    x2 = float(elem.get("x2", 0))
    y2 = float(elem.get("y2", 0))
    return f"M{x1},{y1} L{x2},{y2}"


def _poly_to_path(elem: ET.Element, close: bool) -> str | None:
    raw = elem.get("points", "").strip()
    if not raw:
        return None
    nums = [float(v) for v in re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", raw)]
    if len(nums) < 4:
        return None
    parts = [f"M{nums[0]},{nums[1]}"]
    for i in range(2, len(nums) - 1, 2):
        parts.append(f"L{nums[i]},{nums[i + 1]}")
    if close:
        parts.append("Z")
    return " ".join(parts)


def _shape_to_path(elem: ET.Element) -> tuple[str | None, str]:
    tag = _local(elem.tag)
    if tag == "path":
        return elem.get("d"), "path"
    if tag == "rect":
        return _rect_to_path(elem), "rect"
    if tag == "circle":
        return _circle_to_path(elem), "circle"
    if tag == "ellipse":
        return _ellipse_to_path(elem), "ellipse"
    if tag == "line":
        return _line_to_path(elem), "line"
    if tag == "polygon":
        return _poly_to_path(elem, close=True), "polygon"
    if tag == "polyline":
        return _poly_to_path(elem, close=False), "polyline"
    return None, tag


def _sample_path_points(d: str) -> tuple[list[Point], list[float], bool, float]:
    points: list[Point] = []
    curvatures: list[float] = []
    closed = d.strip().upper().endswith("Z")
    total_length = 0.0

    try:
        parsed = parse_path(d)
    except Exception:
        return points, curvatures, closed, total_length

    for segment in parsed:
        if isinstance(segment, Line):
            points.extend([Point(segment.start.real, segment.start.imag), Point(segment.end.real, segment.end.imag)])
            seg_len = abs(segment.length())
            total_length += seg_len
            curvatures.append(0.0)
        elif isinstance(segment, (QuadraticBezier, CubicBezier)):
            for t in range(_SAMPLE_STEPS + 1):
                pt = segment.point(t / _SAMPLE_STEPS)
                points.append(Point(pt.real, pt.imag))
            seg_len = abs(segment.length(error=1e-3))
            total_length += seg_len
            curvatures.append(0.35)
        elif isinstance(segment, Arc):
            for t in range(_SAMPLE_STEPS + 1):
                pt = segment.point(t / _SAMPLE_STEPS)
                points.append(Point(pt.real, pt.imag))
            seg_len = abs(segment.length(error=1e-3))
            total_length += seg_len
            curvatures.append(0.5)
        else:
            points.append(Point(segment.end.real, segment.end.imag))
            total_length += 1.0

    return points, curvatures, closed, total_length


def _polygon_area(points: list[Point]) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    for i in range(len(points)):
        j = (i + 1) % len(points)
        area += points[i].x * points[j].y - points[j].x * points[i].y
    return abs(area) / 2.0


def _convex_hull_area(points: list[Point]) -> float:
    if len(points) < 3:
        return 0.0
    pts = sorted(set((p.x, p.y) for p in points))

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    return _polygon_area([Point(x, y) for x, y in hull])


def _path_metrics(d: str, bbox: BBox) -> dict[str, Any]:
    points, curvatures, closed, path_length = _sample_path_points(d)
    perimeter = path_length
    area = _polygon_area(points) if closed and len(points) >= 3 else bbox.area * 0.35
    hull_area = _convex_hull_area(points) if len(points) >= 3 else bbox.area
    compactness = area / max(perimeter * perimeter, 1e-6)
    thinness = min(bbox.w, bbox.h) / max(max(bbox.w, bbox.h), 1e-6)
    convexity = area / max(hull_area, 1e-6)
    curvature = None
    if curvatures:
        mean = sum(curvatures) / len(curvatures)
        variance = sum((c - mean) ** 2 for c in curvatures) / len(curvatures)
        curvature = CurvatureStats(mean=mean, max=max(curvatures), std=math.sqrt(variance))

    return {
        "centroid": bbox.centroid,
        "area": area,
        "perimeter": perimeter,
        "path_length": path_length,
        "closed": closed,
        "aspect_ratio": bbox.aspect_ratio,
        "thinness": thinness,
        "compactness": compactness,
        "convexity": min(1.0, convexity),
        "curvature": curvature,
        "sampled_bbox": bbox,
    }


def _hash_d(d: str) -> str:
    return hashlib.sha1(d.encode("utf-8")).hexdigest()[:12]


def normalize_svg(svg_text: str, source_file: str) -> tuple[list[NormalizedPath], dict[str, Any]]:
    root = ET.fromstring(svg_text)
    if _local(root.tag) != "svg":
        raise ValueError("Root element must be <svg>")

    view_box = parse_view_box(root.get("viewBox"))
    if view_box is None:
        w = parse_length(root.get("width"), 100.0) or 100.0
        h = parse_length(root.get("height"), 100.0) or 100.0
        view_box = (0.0, 0.0, w, h)

    width = parse_length(root.get("width"), view_box[2])
    height = parse_length(root.get("height"), view_box[3])
    asset_id = _asset_id_from_filename(source_file)

    warnings: list[str] = []
    normalized: list[NormalizedPath] = []
    index = 0

    for elem in root.iter():
        tag = _local(elem.tag)
        if tag in {"defs", "metadata", "style", "clipPath", "mask", "symbol"}:
            continue
        d, source_tag = _shape_to_path(elem)
        if not d:
            continue

        bbox = path_bbox_from_d(d)
        exact_bbox = path_bbox_exact_from_d(d)
        if bbox is None:
            warnings.append(f"Skip {tag} index {index}: invalid bbox")
            continue

        fill, stroke, opacity, fill_rule = _parse_style(elem)
        metrics = _path_metrics(d, bbox)
        path_id = elem.get("id") or f"path_{index:04d}"

        normalized.append(
            NormalizedPath(
                id=path_id,
                original_index=index,
                d=d,
                d_hash=_hash_d(d),
                fill=fill,
                stroke=stroke,
                opacity=opacity,
                fill_rule=fill_rule,
                bbox=bbox,
                exact_bbox=exact_bbox or bbox,
                sampled_bbox=metrics["sampled_bbox"],
                centroid=metrics["centroid"],
                area=metrics["area"],
                perimeter=metrics["perimeter"],
                path_length=metrics["path_length"],
                closed=metrics["closed"],
                aspect_ratio=metrics["aspect_ratio"],
                thinness=metrics["thinness"],
                compactness=metrics["compactness"],
                convexity=metrics["convexity"],
                curvature=metrics["curvature"],
                z_index=index,
                z_normalized=0.0,
                element_id=elem.get("id"),
                source_tag=source_tag,
            )
        )
        index += 1

    total = max(1, len(normalized) - 1)
    for i, path in enumerate(normalized):
        path.z_normalized = i / total

    meta = {
        "asset_id": asset_id,
        "source_file": source_file,
        "view_box": view_box,
        "width": width,
        "height": height,
        "warnings": warnings,
        "path_count": len(normalized),
    }
    return normalized, meta
