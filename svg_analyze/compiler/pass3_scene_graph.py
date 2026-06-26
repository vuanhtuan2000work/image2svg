"""Pass 3 — Per-frame scene graph + visual component clustering."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from svg_analyze.geometry import BBox, Point, distance, is_eye_color, union_bbox
from svg_analyze.types import NormalizedPath, SceneEdge, VisualComponent


def _path_edge_score(a: NormalizedPath, b: NormalizedPath) -> float:
    overlap = a.bbox.overlap_ratio(b.bbox)
    dist = distance(a.centroid, b.centroid)
    spatial = max(0.0, 1.0 - dist / max(max(a.bbox.w, a.bbox.h, b.bbox.w, b.bbox.h), 1.0))
    color_sim = 1.0 if a.fill and b.fill and a.fill.lower() == b.fill.lower() else 0.0
    z_prox = 1.0 - min(1.0, abs(a.z_index - b.z_index) / 50.0)
    containment = 1.0 if a.bbox.contains_point(b.centroid) or b.bbox.contains_point(a.centroid) else 0.0
    curv_sim = 0.0
    if a.curvature and b.curvature:
        curv_sim = max(0.0, 1.0 - abs(a.curvature.mean - b.curvature.mean))

    return (
        0.25 * overlap
        + 0.20 * spatial
        + 0.15 * color_sim
        + 0.10 * z_prox
        + 0.10 * containment
        + 0.10 * (1.0 if overlap > 0.05 else spatial * 0.5)
        + 0.10 * curv_sim
    )


def cluster_visual_components(paths: list[NormalizedPath], frame_index: int) -> list[VisualComponent]:
    if not paths:
        return []

    edges: list[tuple[int, int, float]] = []
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            score = _path_edge_score(paths[i], paths[j])
            if score >= 0.42:
                edges.append((i, j, score))

    parent = list(range(len(paths)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, j, _ in edges:
        union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(paths)):
        groups[find(i)].append(i)

    components: list[VisualComponent] = []
    for comp_idx, indices in enumerate(groups.values()):
        group_paths = [paths[i] for i in indices]
        merged = union_bbox(p.bbox for p in group_paths)
        if merged is None:
            continue
        fills = [p.fill for p in group_paths if p.fill]
        dominant = fills[0] if fills else None
        z_vals = [p.z_index for p in group_paths]
        elongated = merged.aspect_ratio if merged.aspect_ratio >= 1 else 1 / max(merged.aspect_ratio, 1e-6)
        components.append(
            VisualComponent(
                id=f"frame_{frame_index}_component_{comp_idx:03d}",
                path_ids=[p.id for p in group_paths],
                bbox=merged,
                centroid=merged.centroid,
                area=sum(p.area for p in group_paths),
                dominant_color_cluster=dominant,
                z_range=(min(z_vals), max(z_vals)),
                features={
                    "aspectRatio": merged.aspect_ratio,
                    "compactness": sum(p.compactness for p in group_paths) / len(group_paths),
                    "elongatedness": elongated,
                    "curvatureScore": sum((p.curvature.mean if p.curvature else 0) for p in group_paths) / len(group_paths),
                    "boundaryContactScore": 0.0,
                    "insideCoreScore": 0.0,
                },
            )
        )
    return components


def build_scene_graph(
    frame_index: int,
    paths: list[NormalizedPath],
    components: list[VisualComponent],
) -> dict[str, Any]:
    path_nodes = [{"id": p.id, "type": "PathNode", "path": p.as_dict()} for p in paths]
    component_nodes = [{"id": c.id, "type": "ComponentNode", "component": c.as_dict()} for c in components]

    edges: list[SceneEdge] = []
    path_by_id = {p.id: p for p in paths}
    for comp in components:
        for pid in comp.path_ids:
            edges.append(SceneEdge(f"path:{pid}", comp.id, "candidateForPart", 1.0))

    for i in range(len(components)):
        for j in range(i + 1, len(components)):
            ca, cb = components[i], components[j]
            overlap = ca.bbox.overlap_ratio(cb.bbox)
            dist = distance(ca.centroid, cb.centroid)
            near = dist < max(ca.bbox.w, ca.bbox.h, cb.bbox.w, cb.bbox.h) * 0.35
            if overlap > 0.05:
                edges.append(SceneEdge(ca.id, cb.id, "overlaps", overlap))
            elif near:
                edges.append(SceneEdge(ca.id, cb.id, "near", max(0.0, 1.0 - dist / 100.0)))
            if ca.dominant_color_cluster and ca.dominant_color_cluster == cb.dominant_color_cluster:
                edges.append(SceneEdge(ca.id, cb.id, "sameColorCluster", 0.8))

    for p in paths:
        if p.fill and is_eye_color(p.fill):
            for comp in components:
                if p.id in comp.path_ids:
                    edges.append(SceneEdge(comp.id, "landmark:eyeCandidate", "candidateForPart", 0.9))

    return {
        "frameIndex": frame_index,
        "nodes": {
            "paths": path_nodes,
            "components": component_nodes,
            "regions": [],
            "landmarkCandidates": [],
            "bones": [],
            "semanticParts": [],
        },
        "edges": [{"from": e.from_id, "to": e.to_id, "relation": e.relation, "weight": round(e.weight, 4)} for e in edges],
    }
