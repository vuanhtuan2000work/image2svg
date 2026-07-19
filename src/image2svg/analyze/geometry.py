from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable

from svg.path import Arc, CubicBezier, Line, QuadraticBezier, parse_path


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def as_dict(self) -> dict:
        return {"x": round(self.x, 4), "y": round(self.y, 4)}


@dataclass(frozen=True)
class BBox:
    x: float
    y: float
    w: float
    h: float

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h

    @property
    def area(self) -> float:
        return max(0.0, self.w) * max(0.0, self.h)

    @property
    def centroid(self) -> Point:
        return Point(self.x + self.w / 2, self.y + self.h / 2)

    @property
    def aspect_ratio(self) -> float:
        if self.h <= 0:
            return 0.0
        return self.w / self.h

    def as_dict(self) -> dict:
        return {
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "w": round(self.w, 2),
            "h": round(self.h, 2),
        }

    def expand(self, px: float) -> BBox:
        return BBox(self.x - px, self.y - px, self.w + 2 * px, self.h + 2 * px)

    def intersects(self, other: BBox) -> bool:
        return not (
            self.x2 <= other.x
            or other.x2 <= self.x
            or self.y2 <= other.y
            or other.y2 <= self.y
        )

    def overlap_ratio(self, other: BBox) -> float:
        if not self.intersects(other):
            return 0.0
        ix = min(self.x2, other.x2) - max(self.x, other.x)
        iy = min(self.y2, other.y2) - max(self.y, other.y)
        inter = max(0.0, ix) * max(0.0, iy)
        union = self.area + other.area - inter
        if union <= 0:
            return 0.0
        return inter / union

    def contains_point(self, point: Point) -> bool:
        return self.x <= point.x <= self.x2 and self.y <= point.y <= self.y2


def union_bbox(boxes: Iterable[BBox]) -> BBox | None:
    items = [b for b in boxes if b.w > 0 and b.h > 0]
    if not items:
        return None
    x1 = min(b.x for b in items)
    y1 = min(b.y for b in items)
    x2 = max(b.x2 for b in items)
    y2 = max(b.y2 for b in items)
    return BBox(x1, y1, x2 - x1, y2 - y1)


def normalize_point(point: Point, bbox: BBox) -> Point:
    if bbox.w <= 0 or bbox.h <= 0:
        return Point(0.5, 0.5)
    return Point((point.x - bbox.x) / bbox.w, (point.y - bbox.y) / bbox.h)


def matrix_translate(dx: float, dy: float) -> list[float]:
    return [1.0, 0.0, 0.0, 1.0, dx, dy]


def matrix_scale(sx: float, sy: float) -> list[float]:
    return [sx, 0.0, 0.0, sy, 0.0, 0.0]


def frame_to_core_matrix(frame_bbox: BBox, core_bbox: BBox) -> list[float]:
    if core_bbox.w <= 0 or core_bbox.h <= 0:
        return matrix_translate(-frame_bbox.x, -frame_bbox.y)
    sx = 1.0 / core_bbox.w
    sy = 1.0 / core_bbox.h
    return [
        round(sx, 5),
        0.0,
        0.0,
        round(sy, 5),
        round(-(core_bbox.x - frame_bbox.x) * sx, 5),
        round(-(core_bbox.y - frame_bbox.y) * sy, 5),
    ]


def parse_numbers(text: str) -> list[float]:
    return [float(v) for v in re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", text)]


def _clamp01(t: float) -> float:
    return max(0.0, min(1.0, t))


def _quadratic_roots_in_interval(a: float, b: float, c: float) -> list[float]:
    roots: list[float] = []
    if abs(a) < 1e-12:
        if abs(b) > 1e-12:
            t = -c / b
            if 0.0 <= t <= 1.0:
                roots.append(t)
        return roots
    disc = b * b - 4 * a * c
    if disc < 0:
        return roots
    sqrt_disc = math.sqrt(disc)
    for sign in (-1, 1):
        t = (-b + sign * sqrt_disc) / (2 * a)
        if 0.0 <= t <= 1.0:
            roots.append(t)
    return roots


def _cubic_value(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    u = 1.0 - t
    return u * u * u * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t * p3


def _collect_bezier_extrema_coords(
    xs: list[float],
    ys: list[float],
    p0: complex,
    p1: complex,
    p2: complex,
    p3: complex,
) -> None:
    for dim, coords in ((0, (p0.real, p1.real, p2.real, p3.real)), (1, (p0.imag, p1.imag, p2.imag, p3.imag))):
        c0, c1, c2, c3 = coords
        a = 3 * (-c0 + 3 * c1 - 3 * c2 + c3)
        b = 6 * (c0 - 2 * c1 + c2)
        c = 3 * (c1 - c0)
        for t in _quadratic_roots_in_interval(a, b, c):
            val = _cubic_value(c0, c1, c2, c3, t)
            if dim == 0:
                xs.append(val)
            else:
                ys.append(val)


def _collect_quadratic_extrema_coords(
    xs: list[float],
    ys: list[float],
    p0: complex,
    p1: complex,
    p2: complex,
) -> None:
    for dim, coords in ((0, (p0.real, p1.real, p2.real)), (1, (p0.imag, p1.imag, p2.imag))):
        c0, c1, c2 = coords
        denom = c2 - 2 * c1 + c0
        if abs(denom) < 1e-12:
            continue
        t = _clamp01((c0 - c1) / denom)
        val = (1 - t) ** 2 * c0 + 2 * (1 - t) * t * c1 + t * t * c2
        if dim == 0:
            xs.append(val)
        else:
            ys.append(val)


def _bbox_from_coords(xs: list[float], ys: list[float]) -> BBox | None:
    if not xs or not ys:
        return None
    x1, x2 = min(xs), max(xs)
    y1, y2 = min(ys), max(ys)
    return BBox(x1, y1, max(1e-6, x2 - x1), max(1e-6, y2 - y1))


def path_bbox_exact_from_d(d: str) -> BBox | None:
    """Exact axis-aligned bbox using Bézier control-point extrema."""
    try:
        parsed = parse_path(d)
    except Exception:
        return None

    xs: list[float] = []
    ys: list[float] = []
    for segment in parsed:
        xs.extend([segment.start.real, segment.end.real])
        ys.extend([segment.start.imag, segment.end.imag])
        if isinstance(segment, Line):
            continue
        if isinstance(segment, QuadraticBezier):
            _collect_quadratic_extrema_coords(xs, ys, segment.start, segment.control, segment.end)
        elif isinstance(segment, CubicBezier):
            _collect_bezier_extrema_coords(xs, ys, segment.start, segment.control1, segment.control2, segment.end)
        elif isinstance(segment, Arc):
            for step in range(17):
                t = step / 16
                pt = segment.point(t)
                xs.append(pt.real)
                ys.append(pt.imag)
        else:
            if hasattr(segment, "control1"):
                xs.append(segment.control1.real)
                ys.append(segment.control1.imag)
            if hasattr(segment, "control2"):
                xs.append(segment.control2.real)
                ys.append(segment.control2.imag)

    return _bbox_from_coords(xs, ys)


def path_bbox_from_d(d: str) -> BBox | None:
    exact = path_bbox_exact_from_d(d)
    if exact is not None:
        return exact
    nums = parse_numbers(d)
    if len(nums) < 2:
        return None
    xs = nums[0::2]
    ys = nums[1::2]
    if not xs or not ys:
        return None
    x1, x2 = min(xs), max(xs)
    y1, y2 = min(ys), max(ys)
    if x2 - x1 <= 0 and y2 - y1 <= 0:
        return BBox(x1, y1, 1.0, 1.0)
    return BBox(x1, y1, max(1.0, x2 - x1), max(1.0, y2 - y1))


def parse_view_box(raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    parts = parse_numbers(raw)
    if len(parts) != 4:
        return None
    return parts[0], parts[1], parts[2], parts[3]


def parse_length(raw: str | None, fallback: float) -> float | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw or raw.endswith("%"):
        return None
    nums = parse_numbers(raw)
    if not nums:
        return None
    return nums[0] if abs(nums[0]) > 0 else fallback


def parse_svg_color(raw: str | None) -> tuple[int, int, int] | None:
    """Parse SVG/CSS color to RGB. Returns None for unsupported values."""
    if not raw:
        return None

    value = raw.strip().lower()
    if value in {"none", "transparent", "currentcolor", "inherit"}:
        return None
    if value.startswith("url("):
        return None

    named = {
        "silver": (192, 192, 192),
        "gray": (128, 128, 128),
        "grey": (128, 128, 128),
        "white": (255, 255, 255),
        "black": (0, 0, 0),
        "red": (255, 0, 0),
        "green": (0, 128, 0),
        "blue": (0, 0, 255),
        "cyan": (0, 255, 255),
        "yellow": (255, 255, 0),
        "orange": (255, 165, 0),
        "purple": (128, 0, 128),
        "pink": (255, 192, 203),
        "brown": (165, 42, 42),
        "gold": (255, 215, 0),
        "navy": (0, 0, 128),
        "teal": (0, 128, 128),
        "lime": (0, 255, 0),
        "aqua": (0, 255, 255),
        "fuchsia": (255, 0, 255),
        "maroon": (128, 0, 0),
        "olive": (128, 128, 0),
    }
    if value in named:
        return named[value]

    if value.startswith("rgb"):
        nums = parse_numbers(value)
        if len(nums) >= 3:
            return int(nums[0]), int(nums[1]), int(nums[2])
        return None

    color = value[1:] if value.startswith("#") else value
    if re.fullmatch(r"[0-9a-f]{3}", color):
        color = "".join(ch * 2 for ch in color)
    if not re.fullmatch(r"[0-9a-f]{6}", color):
        return None

    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def color_luminance(color: str) -> float:
    rgb = parse_svg_color(color)
    if rgb is None:
        return 0.5
    r, g, b = (channel / 255 for channel in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def is_eye_color(color: str) -> bool:
    rgb = parse_svg_color(color)
    if rgb is None:
        return False
    r, g, b = rgb
    return b > 120 and b > r and g > 80


def distance(a: Point, b: Point) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)
