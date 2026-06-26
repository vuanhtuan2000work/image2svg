"""Pass 8 — Evidence-based JSON export + legacy UI adapter."""

from __future__ import annotations

from typing import Any

from svg_analyze.compiler.pass1_raster import tight_content_bbox_for_frame
from svg_analyze.geometry import BBox, frame_to_core_matrix, union_bbox
from svg_analyze.export.phaser_manifest import build_game_manifest_from_export
from svg_analyze.legacy_pipeline import _frame_quality, _guess_background
from svg_analyze.types import CompilerState, FrameSplitCandidate, FrameSplitScoreBreakdown, LandmarkCandidate


def _selected_landmarks(candidates: dict[str, list[LandmarkCandidate]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, items in candidates.items():
        if not items:
            continue
        best = max(items, key=lambda c: c.confidence)
        out[name] = {
            "x": round(best.point.x, 4),
            "y": round(best.point.y, 4),
            "coordinate": "coreLocal",
            "confidence": best.confidence,
            "source": best.source,
        }
        out[f"{name}Candidates"] = [c.as_dict() for c in sorted(items, key=lambda c: c.confidence, reverse=True)[:5]]
    return out


def _build_frame_analysis_legacy(
    state: CompilerState,
    frame_index: int,
    semantic_parts: list[dict[str, Any]],
) -> dict[str, Any]:
    split = state.selected_frame_split
    if not split:
        raise ValueError("No frame split selected")

    frame_bbox = split.frame_bboxes[frame_index]
    paths = state.path_buckets.get(frame_index, [])
    core = state.frame_core_regions[frame_index]
    view = state.frame_views[frame_index]
    skeleton = state.frame_skeletons[frame_index]
    lm_candidates = state.frame_landmark_candidates.get(frame_index, {})
    landmarks = _selected_landmarks(lm_candidates)
    components = state.frame_components.get(frame_index, [])

    content_paths = paths
    path_content = union_bbox(p.bbox for p in content_paths) or frame_bbox
    content = path_content
    if state.raster is not None:
        raster_content = tight_content_bbox_for_frame(state.raster, frame_bbox, state.view_box)
        if raster_content is not None:
            content = raster_content
        elif path_content.w > frame_bbox.w * 1.2:
            content = frame_bbox
    silhouette = content

    view_dict = {
        "bodyView": view.body_view_label,
        "headView": view.head_view_label,
    }
    path_rows = state.frame_component_rows.get(frame_index, [])
    quality = _frame_quality(
        frame_index,
        semantic_parts,
        view_dict,
        path_rows,
        core.bbox,
        content,
    )

    graph = state.frame_graphs.get(frame_index, {})
    component_rows = []
    for comp in components:
        row = next((r for r in state.frame_component_rows.get(frame_index, []) if r["componentId"] == comp.id), None)
        if row:
            component_rows.append(row)

    return {
        "frameIndex": frame_index,
        "bounds": {
            "frameBBox": frame_bbox.as_dict(),
            "contentBBox": content.as_dict(),
            "silhouetteBBox": silhouette.as_dict(),
            "coreBodyBBox": core.bbox.as_dict(),
            "coreBodyRegion": {
                **core.as_dict(),
                "medialAxis": getattr(core, "medial_axis", {}),
                "appendageDetails": getattr(core, "appendage_details", {}),
            },
        },
        "transforms": {
            "frameToCoreMatrix": frame_to_core_matrix(frame_bbox, core.bbox),
        },
        "view": {
            "bodyView": view.body_view_label,
            "headView": view.head_view_label,
            "tailView": view.evidence.get("tailRootSide", "unknown"),
            "viewState": view.as_dict(),
            "headViewCandidates": [c for c in view.candidates if c.get("kind") == "head"],
            "bodyViewCandidates": [c for c in view.candidates if c.get("kind") == "body"],
            "confidence": view.confidence,
            "evidence": view.evidence,
        },
        "landmarks": landmarks,
        "landmarkCandidates": {k: [c.as_dict() for c in v] for k, v in lm_candidates.items()},
        "mlLandmarks": state.frame_ml_landmarks.get(frame_index),
        "skeleton": skeleton,
        "partZones": {"zones": {}},
        "semanticParts": semantic_parts,
        "visualComponents": [c.as_dict() for c in components],
        "componentInference": component_rows,
        "sceneGraph": graph,
        "paths": [p.as_dict() for p in paths[:200]],
        "quality": quality,
    }


def export_analysis(state: CompilerState) -> dict[str, Any]:
    split = state.selected_frame_split
    if not split:
        split = FrameSplitCandidate(
            "equalWidth",
            1,
            [BBox(*state.view_box)],
            "unknown",
            0.0,
            FrameSplitScoreBreakdown(),
        )

    frame_count = split.frame_count
    content_bbox = union_bbox(split.frame_bboxes) or BBox(*state.view_box)

    frames = []
    for i in range(frame_count):
        semantic = state.frame_semantic_parts.get(i, [])
        frames.append(_build_frame_analysis_legacy(state, i, semantic))

    temporal = state.temporal_analysis or {}
    quality = state.quality_report

    result = {
        "version": "2.0",
        "compiler": {
            "passes": [
                "pass0_normalize",
                "pass1_raster",
                "pass2_frame_hypotheses",
                "pass3_scene_graph",
                "pass4_core_view",
                "pass5_skeleton_constraints",
                "pass5b_ml_landmarks",
                "pass6_semantic_parts",
                "pass7_temporal",
                "pass8_export",
            ],
            "frameSplitCandidates": [c.as_dict() for c in state.frame_candidates],
            "selectedFrameSplit": split.as_dict() if hasattr(split, "as_dict") else split,
            "rasterWarnings": state.raster.warnings if state.raster else [],
            "warnings": state.warnings,
        },
        "assetAnalysis": {
            "assetId": state.asset_id,
            "sourceFile": state.source_file,
            "svg": {
                "viewBox": list(state.view_box),
                "width": state.width,
                "height": state.height,
                "pathCount": len(state.normalized_paths),
                "normalizedPathCount": len(state.normalized_paths),
            },
            "content": {
                "detectedObjectCount": frame_count,
                "estimatedFrameCount": frame_count,
                "stripDirection": split.direction,
                "backgroundType": _guess_background_legacy(state.normalized_paths),
            },
            "warnings": state.warnings,
        },
        "stripAnalysis": {
            "frameCount": frame_count,
            "layout": {
                "direction": split.direction,
                "frameOrder": "leftToRight" if split.direction == "horizontal" else "topToBottom",
                "spacingMode": "variable" if split.method in {"dynamicProgramming", "alphaProjection", "connectedComponents"} else "equal",
            },
            "globalBounds": {
                "contentBBox": content_bbox.as_dict(),
                "frameBBoxes": [b.as_dict() for b in split.frame_bboxes],
                "gaps": split.split_positions,
            },
            "selectedSplitMethod": split.method,
            "splitConfidence": round(split.score, 4),
        },
        "frameAnalysis": frames,
        "partAnalysis": _part_analysis_from_frames(frames),
        "temporalAnalysis": temporal,
        "temporalTracks": [t.as_dict() for t in state.temporal_tracks],
        "qualityReport": quality,
        "exportPlan": {
            "analysisJson": f"{state.asset_id}.analysis.json",
            "gameManifestJson": f"{state.asset_id}.game-manifest.json",
            "semanticSvg": f"{state.asset_id}.semantic.svg",
            "skeletonJson": f"{state.asset_id}.skeleton.json",
            "temporalTracksJson": f"{state.asset_id}.temporalTracks.json",
            "debugPreview": f"{state.asset_id}.debug.png",
        },
    }
    result["gameManifest"] = build_game_manifest_from_export(result)
    result["stackRecommendation"] = _stack_recommendation()
    return result


def _stack_recommendation() -> dict[str, Any]:
    return {
        "chosen": "phaser-svg-frame-strip",
        "reason": "feed-your-pet uses Phaser 3 + SVG sprite frame rects, not bone runtime.",
        "landmarkDetection": {
            "primary": "compiler-heuristic (medial-axis + constraint skeleton)",
            "optionalPhase2": "mmpose animal model on rendered PNG if ML landmarks needed",
            "notNow": "deeplabcut full training pipeline — heavy, needs labeled video",
        },
        "rigValidation": {
            "primary": "gameManifest.frameRects + skeleton review in /analyze",
            "notApplicable": ["spine-runtimes", "DragonBonesJS"],
            "whyNotSpineDragonBones": "Game animates SVG frame strips; no bone mesh deformation at runtime.",
        },
    }


def _guess_background_legacy(paths) -> str:
    from svg_analyze.legacy_pipeline import ParsedPath

    legacy = [
        ParsedPath(
            path_id=p.id,
            original_index=p.original_index,
            d=p.d,
            d_hash=p.d_hash,
            fill=p.fill,
            stroke=p.stroke,
            opacity=p.opacity,
            bbox=p.bbox,
            centroid=p.centroid,
            has_transform=False,
            element_id=p.element_id,
        )
        for p in paths
    ]
    return _guess_background(legacy)


def _part_analysis_from_frames(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from collections import defaultdict

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for frame in frames:
        for part in frame.get("semanticParts", []):
            groups[part["part"]].append(part)
    out: list[dict[str, Any]] = []
    for part, entries in groups.items():
        out.append(
            {
                "part": part,
                "frameCoverage": len(entries),
                "avgConfidence": round(sum(e.get("confidence", 0) for e in entries) / max(1, len(entries)), 3),
                "frames": [e["frameIndex"] for e in entries],
            }
        )
    return out
