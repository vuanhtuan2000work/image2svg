"""Frame candidate scoring and content-aware frame boxes."""

from __future__ import annotations

import math
from typing import Literal

from svg_analyze.compiler.pass1_raster import alpha_projection, tight_content_bbox_for_frame
from svg_analyze.geometry import BBox, union_bbox
from svg_analyze.types import FrameSplitCandidate, FrameSplitScoreBreakdown, NormalizedPath, RasterEvidence


def _smooth(values: list[float], window: int = 7) -> list[float]:
    if not values:
        return []
    half = window // 2
    out: list[float] = []
    for i in range(len(values)):
        start = max(0, i - half)
        end = min(len(values), i + half + 1)
        out.append(sum(values[start:end]) / (end - start))
    return out


def _raster_slot_fit_score(
    raster: RasterEvidence | None,
    frame_bboxes: list[BBox],
    view_box: tuple[float, float, float, float],
) -> float:
    if raster is None or not frame_bboxes:
        return 0.0
    fits = 0
    for fb in frame_bboxes:
        tight = tight_content_bbox_for_frame(raster, fb, view_box, padding_ratio=0.02)
        if tight is None:
            continue
        ratio = tight.w / max(fb.w, 1.0)
        if 0.35 <= ratio <= 1.15:
            fits += 1
    return fits / len(frame_bboxes)


def _view_bbox(view_box: tuple[float, float, float, float]) -> BBox:
    return BBox(view_box[0], view_box[1], view_box[2], view_box[3])


def _clamp_bbox_to_bounds(bbox: BBox, bounds: BBox) -> BBox:
    x1 = max(bounds.x, bbox.x)
    y1 = max(bounds.y, bbox.y)
    x2 = min(bounds.x2, bbox.x2)
    y2 = min(bounds.y2, bbox.y2)
    return BBox(x1, y1, max(1.0, x2 - x1), max(1.0, y2 - y1))


def _intersection_area(a: BBox, b: BBox) -> float:
    if not a.intersects(b):
        return 0.0
    w = min(a.x2, b.x2) - max(a.x, b.x)
    h = min(a.y2, b.y2) - max(a.y, b.y)
    return max(0.0, w) * max(0.0, h)


def _axis_center(bbox: BBox, direction: Literal["horizontal", "vertical"]) -> float:
    return bbox.centroid.x if direction == "horizontal" else bbox.centroid.y


def _axis_start(bbox: BBox, direction: Literal["horizontal", "vertical"]) -> float:
    return bbox.x if direction == "horizontal" else bbox.y


def _axis_end(bbox: BBox, direction: Literal["horizontal", "vertical"]) -> float:
    return bbox.x2 if direction == "horizontal" else bbox.y2


def _axis_size(bbox: BBox, direction: Literal["horizontal", "vertical"]) -> float:
    return bbox.w if direction == "horizontal" else bbox.h


def _looks_like_strip_background(path: NormalizedPath, bounds: BBox, frame_count: int) -> bool:
    if frame_count <= 1:
        return False
    bbox = path.bbox
    covers_width = bbox.x <= bounds.x + bounds.w * 0.04 and bbox.x2 >= bounds.x2 - bounds.w * 0.04
    covers_height = bbox.y <= bounds.y + bounds.h * 0.04 and bbox.y2 >= bounds.y2 - bounds.h * 0.04
    return covers_width and covers_height and bbox.area >= bounds.area * 0.45


def _paths_for_frame_scan(
    paths: list[NormalizedPath],
    bounds: BBox,
    frame_count: int,
    direction: Literal["horizontal", "vertical"],
) -> list[NormalizedPath]:
    if frame_count <= 1:
        return paths

    min_area = max(bounds.area * 0.00002, 1.0)
    avg_axis = _axis_size(bounds, direction) / max(frame_count, 1)
    kept: list[NormalizedPath] = []

    for path in paths:
        bbox = path.bbox
        if bbox.area <= min_area:
            continue
        if _looks_like_strip_background(path, bounds, frame_count):
            continue

        axis_span = _axis_size(bbox, direction)
        cross_span = bbox.h if direction == "horizontal" else bbox.w
        bounds_cross = bounds.h if direction == "horizontal" else bounds.w

        thin_separator = axis_span >= avg_axis * 1.45 and cross_span <= bounds_cross * 0.10
        broad_sheet_band = axis_span >= _axis_size(bounds, direction) * 0.72 and cross_span >= bounds_cross * 0.48
        if thin_separator or broad_sheet_band:
            continue
        kept.append(path)

    return kept or [p for p in paths if not _looks_like_strip_background(p, bounds, frame_count)]


def _bbox_within(bbox: BBox, frame: BBox, tolerance: float) -> bool:
    return (
        bbox.x >= frame.x - tolerance
        and bbox.y >= frame.y - tolerance
        and bbox.x2 <= frame.x2 + tolerance
        and bbox.y2 <= frame.y2 + tolerance
    )


def _actual_frame_fit_metrics(
    paths: list[NormalizedPath],
    frame_bboxes: list[BBox],
    content: BBox,
    direction: Literal["horizontal", "vertical"],
) -> tuple[float, float, float, float]:
    if not frame_bboxes:
        return 0.0, 1.0, 1.0, 0.0

    scan_paths = _paths_for_frame_scan(paths, content, len(frame_bboxes), direction)
    if not scan_paths:
        return 0.0, 1.0, 1.0, 0.0

    frame_has_content = [False for _ in frame_bboxes]
    coverage_sum = 0.0
    crossing_count = 0
    clipped_count = 0
    scored_count = 0

    for path in scan_paths:
        bbox = path.bbox
        path_area = max(bbox.area, 1.0)
        hits: list[tuple[int, float]] = []
        for idx, frame in enumerate(frame_bboxes):
            inter_ratio = _intersection_area(bbox, frame) / path_area
            if inter_ratio > 0.01 or frame.contains_point(path.centroid):
                hits.append((idx, inter_ratio))

        if not hits:
            clipped_count += 1
            scored_count += 1
            continue

        best_idx, best_ratio = max(hits, key=lambda item: item[1])
        frame_has_content[best_idx] = True
        coverage_sum += min(1.0, best_ratio)
        scored_count += 1

        meaningful_hits = sum(1 for _, ratio in hits if ratio > 0.08)
        tolerance = max(frame_bboxes[best_idx].w, frame_bboxes[best_idx].h) * 0.012
        if meaningful_hits > 1 and best_ratio < 0.92:
            crossing_count += 1
        if best_ratio < 0.96 and not _bbox_within(bbox, frame_bboxes[best_idx], tolerance):
            clipped_count += 1

    non_empty = sum(1 for value in frame_has_content if value)
    coverage = coverage_sum / max(scored_count, 1)
    component_containment = (non_empty / max(len(frame_bboxes), 1)) * coverage
    crossing_penalty = crossing_count / max(scored_count, 1)
    clip_penalty = clipped_count / max(scored_count, 1)
    return component_containment, crossing_penalty, clip_penalty, coverage


def _frame_tightness_score(
    paths: list[NormalizedPath],
    frame_bboxes: list[BBox],
    raster: RasterEvidence | None,
    view_box: tuple[float, float, float, float],
    direction: Literal["horizontal", "vertical"],
) -> float:
    if not frame_bboxes:
        return 0.0

    scores: list[float] = []
    for frame in frame_bboxes:
        tight = tight_content_bbox_for_frame(raster, frame, view_box, padding_ratio=0.02) if raster else None
        if tight is None:
            assigned = [
                p.bbox
                for p in paths
                if frame.contains_point(p.centroid) or _intersection_area(p.bbox, frame) / max(p.bbox.area, 1.0) > 0.05
            ]
            tight = union_bbox(assigned)
        if tight is None:
            scores.append(0.0)
            continue

        axis_ratio = _axis_size(tight, direction) / max(_axis_size(frame, direction), 1.0)
        area_ratio = tight.area / max(frame.area, 1.0)
        axis_score = min(1.0, axis_ratio / 0.72)
        area_score = min(1.0, math.sqrt(max(0.0, area_ratio)) / 0.75)
        scores.append(axis_score * 0.65 + area_score * 0.35)

    return sum(scores) / len(scores)


def score_candidate(
    paths: list[NormalizedPath],
    content: BBox,
    frame_bboxes: list[BBox],
    raster: RasterEvidence | None,
    direction: Literal["horizontal", "vertical"],
    view_box: tuple[float, float, float, float],
) -> FrameSplitScoreBreakdown:
    if not frame_bboxes:
        return FrameSplitScoreBreakdown()

    frame_count = len(frame_bboxes)
    component_containment, crossing_penalty, clip_penalty, coverage = _actual_frame_fit_metrics(
        paths,
        frame_bboxes,
        content,
        direction,
    )

    aspects = [b.w / max(b.h, 1.0) for b in frame_bboxes]
    mean_aspect = sum(aspects) / len(aspects)
    aspect_var = sum((a - mean_aspect) ** 2 for a in aspects) / len(aspects)

    gap_score = 0.0
    if raster and raster.alpha_mask is not None and direction == "horizontal":
        proj = alpha_projection(raster, "x")
        if proj:
            smoothed = _smooth(proj)
            for i in range(1, frame_count):
                prev = frame_bboxes[i - 1]
                curr = frame_bboxes[i]
                split_x = curr.x if curr.x >= prev.x2 else (prev.x2 + curr.x) / 2
                cut_x = int((split_x - content.x) / max(content.w, 1) * len(smoothed))
                cut_x = min(len(smoothed) - 1, max(0, cut_x))
                valley = smoothed[cut_x] / max(max(smoothed), 1.0)
                gap_score += 1.0 - valley
            gap_score /= max(1, frame_count - 1)

    slot_fit = _raster_slot_fit_score(raster, frame_bboxes, view_box)
    tightness = _frame_tightness_score(paths, frame_bboxes, raster, view_box, direction)

    return FrameSplitScoreBreakdown(
        gap_score=min(1.0, gap_score),
        cut_penalty=min(1.0, clip_penalty),
        component_containment=component_containment,
        aspect_consistency=max(0.0, 1.0 - aspect_var),
        path_crossing_penalty=min(1.0, crossing_penalty),
        content_coverage=min(1.0, coverage * 0.45 + tightness * 0.40 + slot_fit * 0.15),
    )


def _contiguous_quantile_clusters(
    ordered: list[NormalizedPath],
    frame_count: int,
) -> list[list[NormalizedPath]]:
    clusters: list[list[NormalizedPath]] = []
    n = len(ordered)
    for i in range(frame_count):
        start = round(i * n / frame_count)
        end = round((i + 1) * n / frame_count)
        clusters.append(ordered[start:end])
    return clusters


def _cluster_paths_by_axis(
    paths: list[NormalizedPath],
    frame_count: int,
    direction: Literal["horizontal", "vertical"],
) -> list[list[NormalizedPath]] | None:
    if frame_count <= 0 or not paths:
        return None
    if frame_count == 1:
        return [paths]

    ordered = sorted(paths, key=lambda p: (_axis_center(p.bbox, direction), p.original_index))
    if len(ordered) < frame_count:
        return None

    centers: list[float] = []
    for i in range(frame_count):
        idx = min(len(ordered) - 1, max(0, int((i + 0.5) * len(ordered) / frame_count)))
        centers.append(_axis_center(ordered[idx].bbox, direction))

    clusters: list[list[NormalizedPath]] = []
    for _ in range(16):
        clusters = [[] for _ in range(frame_count)]
        for path in ordered:
            axis = _axis_center(path.bbox, direction)
            idx = min(range(frame_count), key=lambda i: abs(axis - centers[i]))
            clusters[idx].append(path)

        if any(not cluster for cluster in clusters):
            clusters = _contiguous_quantile_clusters(ordered, frame_count)
            break

        next_centers: list[float] = []
        for cluster in clusters:
            weighted_sum = 0.0
            total_weight = 0.0
            for path in cluster:
                weight = max(1.0, min(128.0, math.sqrt(max(path.bbox.area, 1.0))))
                weighted_sum += _axis_center(path.bbox, direction) * weight
                total_weight += weight
            next_centers.append(weighted_sum / max(total_weight, 1.0))

        next_centers.sort()
        if max(abs(a - b) for a, b in zip(centers, next_centers, strict=False)) < 0.5:
            break
        centers = next_centers

    if any(not cluster for cluster in clusters):
        return None

    clusters.sort(key=lambda cluster: sum(_axis_center(p.bbox, direction) for p in cluster) / len(cluster))
    return clusters


def _expand_content_box(box: BBox, bounds: BBox) -> BBox:
    pad = max(box.w, box.h) * 0.045
    return _clamp_bbox_to_bounds(box.expand(pad), bounds)


def _split_positions_from_boxes(
    boxes: list[BBox],
    direction: Literal["horizontal", "vertical"],
) -> list[float]:
    positions: list[float] = []
    for i in range(1, len(boxes)):
        prev = boxes[i - 1]
        curr = boxes[i]
        prev_end = _axis_end(prev, direction)
        curr_start = _axis_start(curr, direction)
        positions.append(curr_start if curr_start >= prev_end else (prev_end + curr_start) / 2)
    return positions


def candidate_content_clusters(
    paths: list[NormalizedPath],
    content: BBox,
    raster: RasterEvidence | None,
    view_box: tuple[float, float, float, float],
    frame_count: int,
    direction: Literal["horizontal", "vertical"] = "horizontal",
) -> FrameSplitCandidate | None:
    if frame_count < 2 or frame_count > 16:
        return None

    bounds = _view_bbox(view_box)
    scan_paths = _paths_for_frame_scan(paths, bounds, frame_count, direction)
    clusters = _cluster_paths_by_axis(scan_paths, frame_count, direction)
    if clusters is None:
        return None

    boxes: list[BBox] = []
    for cluster in clusters:
        box = union_bbox(p.bbox for p in cluster)
        if box is None:
            return None
        boxes.append(_expand_content_box(box, bounds))

    boxes.sort(key=lambda box: _axis_start(box, direction))
    if len(boxes) != frame_count:
        return None

    breakdown = score_candidate(paths, content, boxes, raster, direction, view_box)
    return FrameSplitCandidate(
        method="hybrid",
        frame_count=frame_count,
        frame_bboxes=boxes,
        direction=direction,
        score=breakdown.total,
        score_breakdown=breakdown,
        split_positions=_split_positions_from_boxes(boxes, direction),
    )
