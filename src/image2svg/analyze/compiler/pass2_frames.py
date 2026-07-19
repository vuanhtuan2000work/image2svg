"""Pass 2 — Multi-hypothesis frame split generation and selection."""

from __future__ import annotations

from typing import Literal

from image2svg.analyze.compiler.frame_fit import candidate_content_clusters, score_candidate
from image2svg.analyze.compiler.pass1_raster import (
    _connected_components_2d,
    alpha_projection,
    frame_bboxes_from_top_components,
    infer_pet_strip_frame_count,
    svg_to_mask_bbox,
)
from image2svg.analyze.geometry import BBox, union_bbox
from image2svg.analyze.legacy_pipeline import _detect_strip
from image2svg.analyze.legacy_pipeline import parse_svg as legacy_parse_svg
from image2svg.analyze.types import FrameSplitCandidate, FrameSplitScoreBreakdown, NormalizedPath, RasterEvidence


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


def _strip_content_bbox(
    paths: list[NormalizedPath],
    view_box: tuple[float, float, float, float],
) -> BBox:
    """Use viewBox for full-width film sheets; path union when content is inset."""
    vx, vy, vw, vh = view_box
    view = BBox(vx, vy, vw, vh)
    content = union_bbox(p.bbox for p in paths)
    if content is None:
        return view
    if content.w >= view.w * 0.75 and content.h >= view.h * 0.5:
        return view
    return content


def _candidate_connected_components(
    paths: list[NormalizedPath],
    content: BBox,
    raster: RasterEvidence | None,
    view_box: tuple[float, float, float, float],
) -> FrameSplitCandidate | None:
    if raster is None or raster.alpha_mask is None:
        return None

    components = _connected_components_2d(raster.alpha_mask)
    large = [c for c in components if c[5] >= raster.alpha_mask.sum() * 0.08]
    if len(large) < 2:
        return None

    large.sort(key=lambda c: c[1])
    frame_bboxes = [svg_to_mask_bbox(c, raster, view_box) for c in large]
    breakdown = score_candidate(paths, content, frame_bboxes, raster, "horizontal", view_box)
    return FrameSplitCandidate(
        method="connectedComponents",
        frame_count=len(frame_bboxes),
        frame_bboxes=frame_bboxes,
        direction="horizontal",
        score=breakdown.total,
        score_breakdown=breakdown,
        split_positions=[b.x for b in frame_bboxes[1:]],
    )


def _candidate_alpha_projection(
    paths: list[NormalizedPath],
    content: BBox,
    raster: RasterEvidence | None,
    view_box: tuple[float, float, float, float],
    direction: Literal["horizontal", "vertical"] = "horizontal",
) -> FrameSplitCandidate | None:
    if raster is None or raster.alpha_mask is None:
        return None

    proj = alpha_projection(raster, "x" if direction == "horizontal" else "y")
    if len(proj) < 8:
        return None

    smoothed = _smooth(proj, 9)
    threshold = max(smoothed) * 0.12
    valleys: list[int] = []
    for i in range(1, len(smoothed) - 1):
        if smoothed[i] <= threshold and smoothed[i] <= smoothed[i - 1] and smoothed[i] <= smoothed[i + 1]:
            valleys.append(i)

    if not valleys:
        return None

    merged: list[int] = [valleys[0]]
    min_dist = max(4, len(smoothed) // 12)
    for v in valleys[1:]:
        if v - merged[-1] >= min_dist:
            merged.append(v)
        elif smoothed[v] < smoothed[merged[-1]]:
            merged[-1] = v

    frame_count = len(merged) + 1
    if frame_count < 2 or frame_count > 16:
        return None

    vx, vy, vw, vh = content.x, content.y, content.w, content.h
    if direction == "horizontal":
        cuts = [vx + (v / len(smoothed)) * vw for v in merged]
        frame_bboxes: list[BBox] = []
        prev = vx
        for cut in cuts + [vx + vw]:
            frame_bboxes.append(BBox(prev, vy, cut - prev, vh))
            prev = cut
    else:
        cuts = [vy + (v / len(smoothed)) * vh for v in merged]
        frame_bboxes = []
        prev = vy
        for cut in cuts + [vy + vh]:
            frame_bboxes.append(BBox(vx, prev, vw, cut - prev))
            prev = cut

    breakdown = score_candidate(paths, content, frame_bboxes, raster, direction, view_box)
    return FrameSplitCandidate(
        method="alphaProjection",
        frame_count=frame_count,
        frame_bboxes=frame_bboxes,
        direction=direction,
        score=breakdown.total,
        score_breakdown=breakdown,
        split_positions=cuts,
    )


def _segment_cost(proj: list[float], start: int, end: int) -> float:
    if end <= start:
        return 999.0
    segment = proj[start:end]
    if not segment:
        return 999.0
    mass = sum(segment)
    if mass <= 0:
        return 50.0
    boundary = (proj[start - 1] if start > 0 else 0) + (proj[end] if end < len(proj) else 0)
    boundary_alpha = boundary / max(max(proj), 1.0)
    emptiness = 1.0 - (mass / max(sum(proj), 1.0)) * (len(proj) / max(end - start, 1))
    return 0.35 * boundary_alpha + 0.15 * emptiness


def _projection_prefix(values: list[float]) -> list[float]:
    prefix = [0.0]
    total = 0.0
    for value in values:
        total += value
        prefix.append(total)
    return prefix


def _segment_cost_fast(
    proj: list[float],
    prefix: list[float],
    start: int,
    end: int,
    *,
    max_proj: float,
    total_mass: float,
) -> float:
    if end <= start:
        return 999.0
    mass = prefix[end] - prefix[start]
    if mass <= 0:
        return 50.0
    boundary = (proj[start - 1] if start > 0 else 0) + (proj[end] if end < len(proj) else 0)
    boundary_alpha = boundary / max(max_proj, 1.0)
    emptiness = 1.0 - (mass / max(total_mass, 1.0)) * (len(proj) / max(end - start, 1))
    return 0.35 * boundary_alpha + 0.15 * emptiness


def _candidate_dynamic_programming(
    paths: list[NormalizedPath],
    content: BBox,
    raster: RasterEvidence | None,
    view_box: tuple[float, float, float, float],
    direction: Literal["horizontal", "vertical"] = "horizontal",
    max_frames: int = 16,
) -> FrameSplitCandidate | None:
    if raster is None or raster.alpha_mask is None:
        return None

    proj = alpha_projection(raster, "x" if direction == "horizontal" else "y")
    n = len(proj)
    if n < 16:
        return None

    max_k = min(max_frames, 12)
    prefix = _projection_prefix(proj)
    max_proj = max(proj) if proj else 1.0
    total_mass = prefix[-1]
    dp: dict[tuple[int, int], float] = {(0, 0): 0.0}
    prev: dict[tuple[int, int], int] = {}

    for k in range(1, max_k + 1):
        for i in range(4, n + 1):
            best = float("inf")
            best_j = -1
            for j in range(k - 1, i):
                if (j, k - 1) not in dp:
                    continue
                cost = dp[(j, k - 1)] + _segment_cost_fast(
                    proj,
                    prefix,
                    j,
                    i,
                    max_proj=max_proj,
                    total_mass=total_mass,
                )
                if cost < best:
                    best = cost
                    best_j = j
            if best_j >= 0:
                dp[(i, k)] = best
                prev[(i, k)] = best_j

    best_k = 1
    best_cost = float("inf")
    for k in range(2, max_k + 1):
        if (n, k) in dp and dp[(n, k)] < best_cost:
            best_cost = dp[(n, k)]
            best_k = k

    if best_k < 2:
        return None

    cuts_idx: list[int] = []
    i, k = n, best_k
    while k > 1 and (i, k) in prev:
        j = prev[(i, k)]
        cuts_idx.append(j)
        i, k = j, k - 1
    cuts_idx.reverse()

    vx, vy, vw, vh = content.x, content.y, content.w, content.h
    if direction == "horizontal":
        cuts = [vx + (c / n) * vw for c in cuts_idx]
        frame_bboxes: list[BBox] = []
        prev_x = vx
        for cut in cuts + [vx + vw]:
            frame_bboxes.append(BBox(prev_x, vy, cut - prev_x, vh))
            prev_x = cut
    else:
        cuts = [vy + (c / n) * vh for c in cuts_idx]
        frame_bboxes = []
        prev_y = vy
        for cut in cuts + [vy + vh]:
            frame_bboxes.append(BBox(vx, prev_y, vw, cut - prev_y))
            prev_y = cut

    breakdown = score_candidate(paths, content, frame_bboxes, raster, direction, view_box)
    return FrameSplitCandidate(
        method="dynamicProgramming",
        frame_count=best_k,
        frame_bboxes=frame_bboxes,
        direction=direction,
        score=breakdown.total,
        score_breakdown=breakdown,
        split_positions=cuts,
    )


def _candidate_equal_width(
    paths: list[NormalizedPath],
    content: BBox,
    frame_count: int,
    direction: str,
    view_box: tuple[float, float, float, float],
    raster: RasterEvidence | None = None,
) -> FrameSplitCandidate:
    frame_bboxes: list[BBox] = []
    if direction == "vertical":
        slice_h = content.h / frame_count
        for i in range(frame_count):
            frame_bboxes.append(BBox(content.x, content.y + i * slice_h, content.w, slice_h))
    else:
        slice_w = content.w / frame_count
        for i in range(frame_count):
            frame_bboxes.append(BBox(content.x + i * slice_w, content.y, slice_w, content.h))

    breakdown = score_candidate(
        paths,
        content,
        frame_bboxes,
        raster,
        direction if direction in {"horizontal", "vertical"} else "horizontal",
        view_box,
    )
    return FrameSplitCandidate(
        method="equalWidth",
        frame_count=frame_count,
        frame_bboxes=frame_bboxes,
        direction=direction if direction in {"horizontal", "vertical"} else "horizontal",
        score=breakdown.total,
        score_breakdown=breakdown,
    )


def _candidate_viewbox_aspect(view_box: tuple[float, float, float, float], paths: list[NormalizedPath], content: BBox) -> FrameSplitCandidate:
    vx, vy, vw, vh = view_box
    aspect = vw / max(vh, 1.0)
    frame_count = 1
    if aspect >= 1.8:
        best_diff = float("inf")
        for n in range(2, min(17, int(aspect * 1.2) + 2)):
            frame_w = vw / n
            diff = abs(frame_w / max(vh, 1.0) - 1.2)
            if diff < best_diff:
                best_diff = diff
                frame_count = n

    slice_w = vw / frame_count
    frame_bboxes = [BBox(vx + i * slice_w, vy, slice_w, vh) for i in range(frame_count)]
    breakdown = score_candidate(paths, content, frame_bboxes, None, "horizontal", view_box)
    return FrameSplitCandidate(
        method="viewBoxAspect",
        frame_count=frame_count,
        frame_bboxes=frame_bboxes,
        direction="horizontal",
        score=breakdown.total,
        score_breakdown=breakdown,
    )


def _candidate_raster_top_components(
    paths: list[NormalizedPath],
    content: BBox,
    raster: RasterEvidence | None,
    view_box: tuple[float, float, float, float],
    frame_count: int,
) -> FrameSplitCandidate | None:
    if raster is None or raster.alpha_mask is None:
        return None

    frame_bboxes = frame_bboxes_from_top_components(raster, view_box, frame_count)
    if not frame_bboxes:
        return None

    breakdown = score_candidate(paths, content, frame_bboxes, raster, "horizontal", view_box)
    return FrameSplitCandidate(
        method="rasterComponents",
        frame_count=len(frame_bboxes),
        frame_bboxes=frame_bboxes,
        direction="horizontal",
        score=breakdown.total,
        score_breakdown=breakdown,
    )


def _candidate_viewbox_equal(
    view_box: tuple[float, float, float, float],
    paths: list[NormalizedPath],
    content: BBox,
    frame_count: int,
    raster: RasterEvidence | None,
) -> FrameSplitCandidate:
    vx, vy, vw, vh = view_box
    slice_w = vw / frame_count
    frame_bboxes = [BBox(vx + i * slice_w, vy, slice_w, vh) for i in range(frame_count)]
    breakdown = score_candidate(paths, content, frame_bboxes, raster, "horizontal", view_box)
    return FrameSplitCandidate(
        method="equalWidth",
        frame_count=frame_count,
        frame_bboxes=frame_bboxes,
        direction="horizontal",
        score=breakdown.total,
        score_breakdown=breakdown,
    )


def generate_frame_candidates(
    paths: list[NormalizedPath],
    view_box: tuple[float, float, float, float],
    raster: RasterEvidence | None,
    svg_text: str,
    source_file: str,
    *,
    display_width: float | None = None,
    display_height: float | None = None,
) -> list[FrameSplitCandidate]:
    content = _strip_content_bbox(paths, view_box)
    view_aspect = view_box[2] / max(view_box[3], 1.0)
    content_aspect = content.w / max(content.h, 1.0)
    horizontal_strip_like = max(view_aspect, content_aspect) >= 1.6
    candidates: list[FrameSplitCandidate] = []

    pet_count = infer_pet_strip_frame_count(view_box, raster, display_width)
    if pet_count and pet_count >= 2:
        try:
            cand = _candidate_raster_top_components(paths, content, raster, view_box, pet_count)
            if cand:
                candidates.append(cand)
        except Exception:
            pass
        try:
            cand = candidate_content_clusters(paths, content, raster, view_box, pet_count, "horizontal")
            if cand:
                candidates.append(cand)
        except Exception:
            pass
        candidates.append(_candidate_viewbox_equal(view_box, paths, content, pet_count, raster))

    for builder in (
        lambda: _candidate_connected_components(paths, content, raster, view_box),
        lambda: _candidate_alpha_projection(paths, content, raster, view_box, "horizontal"),
        lambda: _candidate_dynamic_programming(paths, content, raster, view_box, "horizontal"),
        lambda: _candidate_viewbox_aspect(view_box, paths, content),
    ):
        try:
            cand = builder()
            if cand and cand.frame_count >= 1:
                candidates.append(cand)
        except Exception:
            pass

    legacy_doc = legacy_parse_svg(svg_text, source_file)
    legacy_count, legacy_dir, legacy_bboxes, _, _ = _detect_strip(legacy_doc)
    if legacy_count >= 1:
        candidates.append(
            FrameSplitCandidate(
                method="legacyHistogram",
                frame_count=legacy_count,
                frame_bboxes=legacy_bboxes,
                direction=legacy_dir if legacy_dir in {"horizontal", "vertical"} else "horizontal",
                score=0.0,
                score_breakdown=FrameSplitScoreBreakdown(),
            )
        )
        if legacy_count >= 2 and (horizontal_strip_like or legacy_dir == "vertical"):
            try:
                cand = candidate_content_clusters(
                    paths,
                    content,
                    raster,
                    view_box,
                    legacy_count,
                    legacy_dir if legacy_dir in {"horizontal", "vertical"} else "horizontal",
                )
                if cand:
                    candidates.append(cand)
            except Exception:
                pass
        candidates.append(_candidate_equal_width(paths, content, legacy_count, legacy_dir, view_box, raster))

    aspect = content_aspect
    max_equal = min(9, int(aspect) + 1)
    for n in range(2, max_equal + 1):
        if horizontal_strip_like and (not pet_count or abs(n - pet_count) <= 1):
            try:
                cand = candidate_content_clusters(paths, content, raster, view_box, n, "horizontal")
                if cand:
                    candidates.append(cand)
            except Exception:
                pass
        candidates.append(_candidate_equal_width(paths, content, n, "horizontal", view_box, raster))
    if pet_count and pet_count not in range(2, max_equal + 1):
        candidates.append(_candidate_viewbox_equal(view_box, paths, content, pet_count, raster))

    seen: set[tuple[int, tuple[float, ...]]] = set()
    unique: list[FrameSplitCandidate] = []
    for cand in candidates:
        key = (
            cand.frame_count,
            tuple(round(value, 1) for b in cand.frame_bboxes for value in (b.x, b.y, b.w, b.h)),
        )
        if key in seen:
            continue
        seen.add(key)
        direction = cand.direction if cand.direction in {"horizontal", "vertical"} else "horizontal"
        cand.score = score_candidate(paths, content, cand.frame_bboxes, raster, direction, view_box).total
        unique.append(cand)

    method_priority = {"hybrid": 3, "rasterComponents": 2, "connectedComponents": 1}
    unique.sort(key=lambda c: (c.score, method_priority.get(c.method, 0), c.frame_count), reverse=True)
    return unique[:16], pet_count


def select_frame_split(
    candidates: list[FrameSplitCandidate],
    *,
    preferred_frame_count: int | None = None,
) -> FrameSplitCandidate:
    if not candidates:
        content = BBox(0, 0, 100, 100)
        return FrameSplitCandidate(
            method="equalWidth",
            frame_count=1,
            frame_bboxes=[content],
            direction="unknown",
            score=0.0,
            score_breakdown=FrameSplitScoreBreakdown(),
        )

    best = candidates[0]

    if preferred_frame_count and preferred_frame_count >= 2:
        preferred = [c for c in candidates if c.frame_count == preferred_frame_count]
        if preferred:
            top_preferred = max(preferred, key=lambda c: c.score)
            if top_preferred.score >= best.score - 0.035:
                return top_preferred

    allow_multi_override = best.frame_count >= 2 or bool(preferred_frame_count and preferred_frame_count >= 2)

    raster_hits = [c for c in candidates if c.method == "rasterComponents" and c.frame_count >= 2]
    if allow_multi_override and raster_hits:
        top_raster = max(raster_hits, key=lambda c: (c.score, c.frame_count))
        if top_raster.score >= best.score - 0.06:
            return top_raster

    content_hits = [c for c in candidates if c.method == "hybrid" and c.frame_count >= 2]
    if allow_multi_override and content_hits:
        top_content = max(content_hits, key=lambda c: (c.score, c.frame_count))
        if top_content.score >= best.score - 0.06:
            return top_content

    tied = [c for c in candidates if c.score >= best.score - 0.015]
    if len(tied) > 1:
        tied.sort(key=lambda c: (c.score, 1 if c.method == "hybrid" else 0, c.frame_count), reverse=True)
        return tied[0]

    return best


def assign_paths_to_frames(
    paths: list[NormalizedPath],
    frame_bboxes: list[BBox],
) -> dict[int, list[NormalizedPath]]:
    buckets: dict[int, list[NormalizedPath]] = {i: [] for i in range(len(frame_bboxes))}
    if not frame_bboxes:
        return buckets

    equal_width = len(frame_bboxes) > 1 and all(
        abs(b.w - frame_bboxes[0].w) < 1.0 and abs(b.h - frame_bboxes[0].h) < 1.0 for b in frame_bboxes
    )
    horizontal = frame_bboxes[0].w >= frame_bboxes[0].h

    for path in paths:
        if equal_width and horizontal and len(frame_bboxes) > 1:
            origin = frame_bboxes[0]
            slot_w = origin.w
            idx = int((path.centroid.x - origin.x) / max(slot_w, 1e-6))
            idx = min(len(frame_bboxes) - 1, max(0, idx))
            buckets[idx].append(path)
            continue

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
