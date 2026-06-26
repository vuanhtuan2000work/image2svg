"""Pass 6 — Semantic part inference via ILP / graph-cut global optimization."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from svg_analyze.compiler.part_solver import solve_part_labels_ilp
from svg_analyze.geometry import BBox, Point, color_luminance, distance, is_eye_color, normalize_point, union_bbox
from svg_analyze.types import CoreBodyRegion, NormalizedPath, ViewState, VisualComponent

CAT_PARTS = (
    "bodySet",
    "headBase",
    "earSet",
    "eyeSet",
    "faceSet",
    "frontLegSet",
    "backLegSet",
    "tailSet",
    "outline",
    "patternOverlay",
    "shadow",
    "unknown",
)

SOLVER_LABELS = [p for p in CAT_PARTS if p != "unknown"]

PART_ZONES = {
    "headBase": (0.32, 0.08, 0.36, 0.32),
    "eyeSet": (0.34, 0.18, 0.32, 0.14),
    "faceSet": (0.30, 0.24, 0.40, 0.18),
    "earSet": (0.28, 0.0, 0.44, 0.18),
    "bodySet": (0.22, 0.34, 0.56, 0.42),
    "tailSet": (0.0, 0.08, 0.24, 0.55),
    "frontLegSet": (0.28, 0.62, 0.22, 0.28),
    "backLegSet": (0.48, 0.62, 0.22, 0.28),
}


def _bone_points(skeleton: dict[str, Any]) -> dict[str, Point]:
    out: dict[str, Point] = {}
    for name, bone in skeleton.get("bones", {}).items():
        root = bone.get("root", {})
        out[name] = Point(root.get("x", 0.5), root.get("y", 0.5))
    return out


def _unary_score(component: VisualComponent, part: str, core: CoreBodyRegion, skeleton: dict[str, Any], view: ViewState) -> dict[str, float]:
    norm = normalize_point(component.centroid, core.bbox)
    zone = PART_ZONES.get(part)
    zone_overlap = 0.0
    if zone:
        zx, zy, zw, zh = zone
        zone_bbox = BBox(core.bbox.x + zx * core.bbox.w, core.bbox.y + zy * core.bbox.h, zw * core.bbox.w, zh * core.bbox.h)
        zone_overlap = component.bbox.overlap_ratio(zone_bbox)

    bones = _bone_points(skeleton)
    bone_dist = 0.0
    if part == "tailSet" and "tail" in bones:
        bone_dist = max(0.0, 1.0 - distance(norm, bones["tail"]) * 2.5)
    elif part in {"headBase", "faceSet", "eyeSet", "earSet"} and "head" in bones:
        bone_dist = max(0.0, 1.0 - distance(norm, bones["head"]) * 2.0)
    elif part == "bodySet" and "body" in bones:
        bone_dist = max(0.0, 1.0 - distance(norm, bones["body"]) * 2.0)

    color_role = 0.0
    if component.dominant_color_cluster:
        lum = color_luminance(component.dominant_color_cluster)
        if part == "eyeSet" and is_eye_color(component.dominant_color_cluster):
            color_role = 0.95
        elif part == "outline" and lum < 0.15:
            color_role = 0.85
        elif part == "bodySet" and 0.3 <= lum <= 0.8:
            color_role = 0.7

    shape_prior = 0.0
    elongated = component.features.get("elongatedness", 1.0)
    if part == "tailSet" and elongated > 1.8:
        shape_prior = 0.88
    elif part == "eyeSet" and component.features.get("compactness", 0) > 0.02:
        shape_prior = 0.75
    elif part == "bodySet" and component.area > core.bbox.area * 0.08:
        shape_prior = 0.7

    view_prior = 0.5
    if part == "tailSet" and view.evidence.get("tailRootSide") == "left" and norm.x < 0.35:
        view_prior = 0.8

    evidence = {
        "adaptivePartHeatmap": zone_overlap,
        "skeletonBoneDistance": bone_dist,
        "regionOverlap": zone_overlap,
        "colorRoleMatch": color_role,
        "shapePrior": shape_prior,
        "zOrderPrior": 0.5,
        "viewPrior": view_prior,
        "temporalPrior": 0.0,
        "containmentPrior": 0.0,
    }
    score = (
        0.18 * evidence["adaptivePartHeatmap"]
        + 0.16 * evidence["skeletonBoneDistance"]
        + 0.14 * evidence["regionOverlap"]
        + 0.12 * evidence["colorRoleMatch"]
        + 0.10 * evidence["shapePrior"]
        + 0.10 * evidence["zOrderPrior"]
        + 0.08 * evidence["viewPrior"]
        + 0.08 * evidence["temporalPrior"]
        + 0.04 * evidence["containmentPrior"]
    )
    evidence["total"] = score
    return evidence


def _build_pairwise(components: list[VisualComponent], core: CoreBodyRegion) -> list[tuple[str, str, float, float]]:
    pairs: list[tuple[str, str, float, float]] = []
    for i in range(len(components)):
        for j in range(i + 1, len(components)):
            a, b = components[i], components[j]
            overlap = a.bbox.overlap_ratio(b.bbox)
            dist = distance(a.centroid, b.centroid)
            dist_norm = dist / max(core.bbox.w, core.bbox.h, 1.0)
            if overlap > 0.02 or dist_norm < 0.5:
                pairs.append((a.id, b.id, overlap, dist_norm))
    return pairs


def infer_semantic_parts(
    frame_index: int,
    components: list[VisualComponent],
    paths: list[NormalizedPath],
    core: CoreBodyRegion,
    skeleton: dict[str, Any],
    view: ViewState,
) -> tuple[list[dict[str, Any]], dict[str, str], list[dict[str, Any]]]:
    if not components:
        return [], {}, []

    unary_costs: dict[str, dict[str, float]] = {}
    candidate_rows: dict[str, list[dict[str, Any]]] = {}

    for comp in components:
        scored: list[dict[str, Any]] = []
        costs: dict[str, float] = {}
        for part in SOLVER_LABELS:
            evidence = _unary_score(comp, part, core, skeleton, view)
            costs[part] = evidence["total"]
            scored.append(
                {
                    "part": part,
                    "score": round(evidence["total"], 4),
                    "evidence": {k: round(v, 4) for k, v in evidence.items() if k != "total"},
                }
            )
        scored.sort(key=lambda item: item["score"], reverse=True)
        unary_costs[comp.id] = costs
        candidate_rows[comp.id] = scored

    pairwise = _build_pairwise(components, core)

    # ILP on largest components; small fragments inherit via neighbor voting
    ranked = sorted(components, key=lambda c: c.area, reverse=True)
    ilp_ids = {c.id for c in ranked[:35]}
    ilp_components = [c for c in components if c.id in ilp_ids]
    small_components = [c for c in components if c.id not in ilp_ids]

    ilp_pairwise = [(a, b, o, d) for a, b, o, d in pairwise if a in ilp_ids and b in ilp_ids]
    ilp_labels, solver_name = solve_part_labels_ilp(
        [c.id for c in ilp_components],
        SOLVER_LABELS,
        unary_costs,
        ilp_pairwise,
    )
    component_labels = dict(ilp_labels)

    for comp in small_components:
        best_label = "unknown"
        best_score = -1.0
        for label in SOLVER_LABELS:
            score = unary_costs.get(comp.id, {}).get(label, 0.0)
            if score > best_score:
                best_score = score
                best_label = label
        if best_score >= 0.25:
            component_labels[comp.id] = best_label
        else:
            component_labels[comp.id] = "unknown"

    component_rows: list[dict[str, Any]] = []
    for comp in components:
        label = component_labels.get(comp.id, "unknown")
        scored = candidate_rows[comp.id]
        best = next((s for s in scored if s["part"] == label), scored[0])
        reasons: list[str] = ["Global ILP/graph-cut assignment"]
        if best["evidence"].get("shapePrior", 0) > 0.6:
            reasons.append("Shape matches part prior")
        if best["evidence"].get("colorRoleMatch", 0) > 0.6:
            reasons.append("Color role matches part")
        component_rows.append(
            {
                "componentId": comp.id,
                "finalPart": label,
                "confidence": best["score"],
                "candidates": scored[:4],
                "reason": reasons,
                "solver": solver_name,
            }
        )

    path_by_id = {p.id: p for p in paths}
    semantic_groups: dict[str, list[VisualComponent]] = defaultdict(list)
    for comp in components:
        semantic_groups[component_labels.get(comp.id, "unknown")].append(comp)

    semantic_parts: list[dict[str, Any]] = []
    for part, group in semantic_groups.items():
        if part == "unknown":
            continue
        merged = union_bbox(c.bbox for c in group)
        if merged is None:
            continue
        path_ids = [pid for c in group for pid in c.path_ids]
        colors = Counter(path_by_id[pid].fill for pid in path_ids if pid in path_by_id and path_by_id[pid].fill)
        semantic_parts.append(
            {
                "part": part,
                "frameIndex": frame_index,
                "componentIds": [c.id for c in group],
                "pathIds": path_ids,
                "bbox": merged.as_dict(),
                "centroid": merged.centroid.as_dict(),
                "dominantColors": [c for c, _ in colors.most_common(4)],
                "confidence": round(
                    sum(r["confidence"] for r in component_rows if r["finalPart"] == part) / max(1, len(group)),
                    3,
                ),
                "visibility": "visible",
                "zRange": {"min": min(c.z_range[0] for c in group), "max": max(c.z_range[1] for c in group)},
            }
        )

    return semantic_parts, component_labels, component_rows
