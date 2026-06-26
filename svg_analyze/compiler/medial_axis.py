"""Medial axis / skeletonization for silhouette appendage detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from svg_analyze.geometry import BBox, Point


@dataclass
class SkeletonBranch:
    id: str
    points: list[tuple[int, int]]
    length_px: float
    mean_thickness: float
    endpoint_a: tuple[int, int]
    endpoint_b: tuple[int, int]
    junction: tuple[int, int] | None = None
    kind: str = "unknown"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "lengthPx": round(self.length_px, 2),
            "meanThickness": round(self.mean_thickness, 3),
            "endpointA": list(self.endpoint_a),
            "endpointB": list(self.endpoint_b),
            "junction": list(self.junction) if self.junction else None,
            "kind": self.kind,
        }


@dataclass
class MedialAxisResult:
    skeleton_mask: np.ndarray
    branches: list[SkeletonBranch] = field(default_factory=list)
    endpoints: list[tuple[int, int]] = field(default_factory=list)
    junctions: list[tuple[int, int]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "branchCount": len(self.branches),
            "branches": [b.as_dict() for b in self.branches],
            "endpoints": [list(p) for p in self.endpoints],
            "junctions": [list(p) for p in self.junctions],
        }


def _neighbors8(y: int, x: int, h: int, w: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w:
                out.append((ny, nx))
    return out


def _zhang_suen_thinning(mask: np.ndarray, max_iters: int = 200) -> np.ndarray:
    """Binary skeletonization via Zhang-Suen thinning."""
    skel = mask.astype(bool).copy()
    h, w = skel.shape
    changed = True
    iters = 0
    while changed and iters < max_iters:
        changed = False
        iters += 1
        for phase in (0, 1):
            to_remove: list[tuple[int, int]] = []
            for y in range(1, h - 1):
                for x in range(1, w - 1):
                    if not skel[y, x]:
                        continue
                    p2 = skel[y - 1, x]
                    p3 = skel[y - 1, x + 1]
                    p4 = skel[y, x + 1]
                    p5 = skel[y + 1, x + 1]
                    p6 = skel[y + 1, x]
                    p7 = skel[y + 1, x - 1]
                    p8 = skel[y, x - 1]
                    p9 = skel[y - 1, x - 1]
                    neighbors = [p2, p3, p4, p5, p6, p7, p8, p9]
                    count = sum(neighbors)
                    if count < 2 or count > 6:
                        continue
                    transitions = sum(
                        1 for i in range(8) if neighbors[i] == 0 and neighbors[(i + 1) % 8] == 1
                    )
                    if transitions != 1:
                        continue
                    if phase == 0:
                        if p2 and p4 and p6:
                            continue
                        if p4 and p6 and p8:
                            continue
                    else:
                        if p2 and p4 and p8:
                            continue
                        if p2 and p6 and p8:
                            continue
                    to_remove.append((y, x))
            if to_remove:
                changed = True
                for y, x in to_remove:
                    skel[y, x] = False
    return skel


def _skeleton_degree(skel: np.ndarray, y: int, x: int) -> int:
    return sum(1 for ny, nx in _neighbors8(y, x, *skel.shape) if skel[ny, nx])


def _trace_branch(skel: np.ndarray, start: tuple[int, int], visited_edges: set[tuple[tuple[int, int], tuple[int, int]]]) -> list[tuple[int, int]]:
    path = [start]
    prev = None
    current = start
    while True:
        y, x = current
        nbrs = [(ny, nx) for ny, nx in _neighbors8(y, x, *skel.shape) if skel[ny, nx] and (ny, nx) != prev]
        if not nbrs:
            break
        if len(nbrs) > 1 and len(path) > 1:
            break
        nxt = nbrs[0]
        edge = (current, nxt) if current < nxt else (nxt, current)
        if edge in visited_edges:
            break
        visited_edges.add(edge)
        prev, current = current, nxt
        path.append(current)
    return path


def _extract_branches(skel: np.ndarray, dist: np.ndarray) -> MedialAxisResult:
    h, w = skel.shape
    endpoints: list[tuple[int, int]] = []
    junctions: list[tuple[int, int]] = []
    for y in range(h):
        for x in range(w):
            if not skel[y, x]:
                continue
            deg = _skeleton_degree(skel, y, x)
            if deg <= 1:
                endpoints.append((y, x))
            elif deg >= 3:
                junctions.append((y, x))

    visited_edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    branches: list[SkeletonBranch] = []
    seeds = endpoints + junctions
    bid = 0
    for seed in seeds:
        path = _trace_branch(skel, seed, visited_edges)
        if len(path) < 4:
            continue
        thickness = float(np.mean([dist[y, x] for y, x in path if dist[y, x] > 0] or [1.0]))
        length = float(len(path))
        branches.append(
            SkeletonBranch(
                id=f"branch_{bid:03d}",
                points=path,
                length_px=length,
                mean_thickness=thickness,
                endpoint_a=path[0],
                endpoint_b=path[-1],
                junction=seed if seed in junctions else None,
            )
        )
        bid += 1
    return MedialAxisResult(skeleton_mask=skel, branches=branches, endpoints=endpoints, junctions=junctions)


def compute_medial_axis(alpha_mask: np.ndarray, density_map: np.ndarray | None = None) -> MedialAxisResult:
    if alpha_mask is None or alpha_mask.size == 0:
        return MedialAxisResult(skeleton_mask=np.zeros((1, 1), dtype=bool))

    opened = alpha_mask.copy()
    h, w = opened.shape
    for _ in range(1):
        eroded = opened.copy()
        for y in range(h):
            for x in range(w):
                if not opened[y, x]:
                    continue
                for ny, nx in _neighbors8(y, x, h, w):
                    if not opened[ny, nx]:
                        eroded[y, x] = False
                        break
        opened = eroded

    skel = _zhang_suen_thinning(opened)
    if density_map is None:
        dist = np.zeros_like(alpha_mask, dtype=np.float32)
        dist[alpha_mask] = 1.0
    else:
        dist = density_map.astype(np.float32)
    return _extract_branches(skel, dist)


def _mask_to_svg_point(py: int, px: int, view: BBox, rw: int, rh: int) -> Point:
    return Point(view.x + (px / max(rw, 1)) * view.w, view.y + (py / max(rh, 1)) * view.h)


def classify_appendages(
    axis: MedialAxisResult,
    core: BBox,
    content: BBox,
    raster_w: int,
    raster_h: int,
) -> dict[str, list[dict[str, Any]]]:
    """Classify skeleton branches as tail / ear / leg / whisker candidates."""
    result: dict[str, list[dict[str, Any]]] = {
        "tailCandidates": [],
        "earCandidates": [],
        "legCandidates": [],
        "whiskerCandidates": [],
    }
    core_c = core.centroid
    for branch in axis.branches:
        ay, ax = branch.endpoint_a
        by, bx = branch.endpoint_b
        pa = _mask_to_svg_point(ay, ax, content, raster_w, raster_h)
        pb = _mask_to_svg_point(by, bx, content, raster_w, raster_h)
        far = pa if pa.x < pb.x else pb
        near = pb if pa.x < pb.x else pa
        length = branch.length_px
        thin = branch.mean_thickness < 3.5
        elongated = length >= max(raster_w, raster_h) * 0.12

        entry = {
            "branchId": branch.id,
            "tip": far.as_dict(),
            "root": near.as_dict(),
            "lengthPx": branch.length_px,
            "meanThickness": branch.mean_thickness,
            "confidence": min(0.95, 0.45 + length / max(raster_w, 1) * 0.5),
        }

        if elongated and not thin and far.x < core.x + core.w * 0.25:
            branch.kind = "tail"
            entry["kind"] = "tail"
            result["tailCandidates"].append(entry)
        elif thin and elongated and length >= raster_w * 0.08:
            if min(pa.y, pb.y) < core.y + core.h * 0.35:
                branch.kind = "whisker"
                entry["kind"] = "whisker"
                result["whiskerCandidates"].append(entry)
            else:
                branch.kind = "leg"
                entry["kind"] = "leg"
                result["legCandidates"].append(entry)
        elif length >= raster_h * 0.06 and max(pa.y, pb.y) < core.y + core.h * 0.25:
            branch.kind = "ear"
            entry["kind"] = "ear"
            result["earCandidates"].append(entry)

    for key in result:
        result[key].sort(key=lambda item: item["confidence"], reverse=True)
    return result
