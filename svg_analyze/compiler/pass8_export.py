"""Pass 8 — Evidence-based JSON export + legacy UI adapter."""

from __future__ import annotations

from typing import Any

from svg_analyze.compiler.pass1_raster import foreground_bbox_from_paths, tight_content_bbox_for_frame
from svg_analyze.geometry import BBox, frame_to_core_matrix, union_bbox
from svg_analyze.export.phaser_manifest import build_game_manifest_from_export
from svg_analyze.legacy_pipeline import _frame_quality, _guess_background
from svg_analyze.types import CompilerState, FrameSplitCandidate, FrameSplitScoreBreakdown, LandmarkCandidate

AP10K_EDGES = [
    ("Nose", "Neck"),
    ("Neck", "L_Shoulder"),
    ("Neck", "R_Shoulder"),
    ("L_Shoulder", "L_Elbow"),
    ("L_Elbow", "L_F_Paw"),
    ("R_Shoulder", "R_Elbow"),
    ("R_Elbow", "R_F_Paw"),
    ("Neck", "Root_of_tail"),
    ("Root_of_tail", "Tail"),
    ("Root_of_tail", "L_Hip"),
    ("Root_of_tail", "R_Hip"),
    ("L_Hip", "L_Knee"),
    ("L_Knee", "L_B_Paw"),
    ("R_Hip", "R_Knee"),
    ("R_Knee", "R_B_Paw"),
    ("Nose", "L_Eye"),
    ("Nose", "R_Eye"),
]

LANDMARK_TO_AP10K = {
    "leftEye": "L_Eye",
    "rightEye": "R_Eye",
    "nose": "Nose",
    "neck": "Neck",
    "tailRoot": "Root_of_tail",
    "tailTip": "Tail",
    "frontLeftShoulder": "L_Shoulder",
    "frontRightShoulder": "R_Shoulder",
    "frontLeftPaw": "L_F_Paw",
    "frontRightPaw": "R_F_Paw",
    "backLeftHip": "L_Hip",
    "backRightHip": "R_Hip",
    "backLeftPaw": "L_B_Paw",
    "backRightPaw": "R_B_Paw",
}


AP10K_EDGE_LIMITS = {
    ("Nose", "Neck"): 0.34,
    ("Nose", "L_Eye"): 0.24,
    ("Nose", "R_Eye"): 0.24,
    ("Neck", "Root_of_tail"): 0.76,
    ("Root_of_tail", "Tail"): 0.46,
}

AP10K_EDGE_MIN_CONFIDENCE = 0.38


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


def _core_point_to_global(point: dict[str, Any], core_bbox: BBox) -> dict[str, float]:
    return {
        "x": core_bbox.x + float(point.get("x", 0.5)) * core_bbox.w,
        "y": core_bbox.y + float(point.get("y", 0.5)) * core_bbox.h,
    }


def _point_in_bbox(point: dict[str, float], bbox: BBox, *, margin_ratio: float = 0.08) -> bool:
    margin = max(bbox.w, bbox.h) * margin_ratio
    return (
        bbox.x - margin <= point["x"] <= bbox.x2 + margin
        and bbox.y - margin <= point["y"] <= bbox.y2 + margin
    )


def _edge_is_plausible(a: dict[str, Any], b: dict[str, Any], content_bbox: BBox, frame_bbox: BBox) -> bool:
    if min(float(a.get("confidence", 0.0)), float(b.get("confidence", 0.0))) < AP10K_EDGE_MIN_CONFIDENCE:
        return False
    if not _point_in_bbox(a, frame_bbox, margin_ratio=0.02) or not _point_in_bbox(b, frame_bbox, margin_ratio=0.02):
        return False
    distance = ((float(a["x"]) - float(b["x"])) ** 2 + (float(a["y"]) - float(b["y"])) ** 2) ** 0.5
    diagonal = max(1.0, (content_bbox.w**2 + content_bbox.h**2) ** 0.5)
    limit = AP10K_EDGE_LIMITS.get((a["label"], b["label"]), 0.62)
    return distance <= diagonal * limit


def _add_pose_keypoint(
    keypoints: dict[str, dict[str, Any]],
    *,
    label: str,
    point: dict[str, float],
    confidence: float,
    source: str,
    frame_bbox: BBox,
    priority: int,
    generated: bool = False,
) -> None:
    if not label or point.get("x") is None or point.get("y") is None:
        return
    if not _point_in_bbox(point, frame_bbox, margin_ratio=0.04):
        return
    prev = keypoints.get(label)
    if prev and int(prev.get("_priority", 0)) > priority:
        return
    if prev and int(prev.get("_priority", 0)) == priority and float(prev.get("confidence", 0.0)) >= confidence:
        return
    keypoints[label] = {
        "label": label,
        "x": round(float(point["x"]), 2),
        "y": round(float(point["y"]), 2),
        "coordinate": "globalSvg",
        "confidence": round(confidence, 4),
        "source": source,
        "generated": generated,
        "_priority": priority,
    }


def _pose_preview(
    frame_index: int,
    landmarks: dict[str, Any],
    skeleton: dict[str, Any],
    core_bbox: BBox,
    content_bbox: BBox,
    frame_bbox: BBox,
    ml_landmarks: dict[str, Any] | None,
) -> dict[str, Any]:
    keypoints: dict[str, dict[str, Any]] = {}

    ml_backend = (ml_landmarks or {}).get("backend") or ""
    ml_is_pose_backend = "mmpose" in ml_backend.lower()
    ml_points = (ml_landmarks or {}).get("keypoints", []) if (ml_landmarks or {}).get("status") == "ok" and ml_is_pose_backend else []
    for kp in ml_points:
        raw_label = kp.get("sourceLabel") or kp.get("label") or LANDMARK_TO_AP10K.get(kp.get("name"))
        label = LANDMARK_TO_AP10K.get(raw_label, raw_label)
        if label not in {label for edge in AP10K_EDGES for label in edge}:
            continue
        _add_pose_keypoint(
            keypoints,
            label=label,
            point={"x": float(kp.get("x", 0.0)), "y": float(kp.get("y", 0.0))},
            confidence=float(kp.get("confidence", 0.5)),
            source=ml_backend,
            frame_bbox=frame_bbox,
            priority=100,
        )

    for name, label in LANDMARK_TO_AP10K.items():
        raw = landmarks.get(name)
        if not isinstance(raw, dict) or raw.get("x") is None or label in keypoints:
            continue
        if not ml_is_pose_backend and label not in {"L_Eye", "R_Eye", "Neck", "Nose"}:
            continue
        point = _core_point_to_global(raw, core_bbox) if raw.get("coordinate") == "coreLocal" else raw
        _add_pose_keypoint(
            keypoints,
            label=label,
            point={"x": float(point.get("x", 0.0)), "y": float(point.get("y", 0.0))},
            confidence=float(raw.get("confidence", 0.45)),
            source=raw.get("source", "compiler"),
            frame_bbox=frame_bbox,
            priority=70,
        )

    bones = skeleton.get("bones") or {}
    fallback_bones = (("neck", "Neck"), ("tail", "Root_of_tail")) if ml_is_pose_backend else (("neck", "Neck"),)
    for bone_name, label in fallback_bones:
        bone = bones.get(bone_name) or {}
        root = bone.get("root")
        if isinstance(root, dict) and label not in keypoints:
            point = _core_point_to_global(root, core_bbox)
            _add_pose_keypoint(
                keypoints,
                label=label,
                point=point,
                confidence=float(bone.get("confidence", 0.4)),
                source="skeleton",
                frame_bbox=frame_bbox,
                priority=55,
                generated=True,
            )

    if "Nose" not in keypoints and isinstance(landmarks.get("headCenter"), dict):
        raw_head = landmarks["headCenter"]
        point = _core_point_to_global(raw_head, core_bbox) if raw_head.get("coordinate") == "coreLocal" else raw_head
        _add_pose_keypoint(
            keypoints,
            label="Nose",
            point={"x": float(point.get("x", 0.0)), "y": float(point.get("y", 0.0))},
            confidence=min(0.36, float(raw_head.get("confidence", 0.36))),
            source="estimatedHeadCenter",
            frame_bbox=frame_bbox,
            priority=30,
            generated=True,
        )

    available_edges = [
        {
            "from": a,
            "to": b,
            "confidence": round(min(float(keypoints[a].get("confidence", 0.0)), float(keypoints[b].get("confidence", 0.0))), 4),
        }
        for a, b in AP10K_EDGES
        if a in keypoints and b in keypoints and _edge_is_plausible(keypoints[a], keypoints[b], content_bbox, frame_bbox)
    ]

    public_keypoints = []
    for item in keypoints.values():
        item = dict(item)
        item.pop("_priority", None)
        public_keypoints.append(item)

    return {
        "profile": "AP-10K compatible Animal 2D Keypoint preview",
        "dataset": "AP10KDataset",
        "frameIndex": frame_index,
        "backend": ml_backend if ml_is_pose_backend else "compiler-heuristic",
        "keypoints": sorted(public_keypoints, key=lambda item: item["label"]),
        "edges": available_edges,
        "missingLabels": sorted({label for edge in AP10K_EDGES for label in edge} - set(keypoints)),
    }


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

    path_content = foreground_bbox_from_paths(paths, frame_bbox) or union_bbox(p.bbox for p in paths) or frame_bbox
    content = path_content
    if state.raster is not None:
        raster_content = tight_content_bbox_for_frame(state.raster, frame_bbox, state.view_box)
        if raster_content is not None:
            raster_is_full_frame = raster_content.area >= frame_bbox.area * 0.92
            path_is_tighter = path_content.area < raster_content.area * 0.92
            content = path_content if raster_is_full_frame and path_is_tighter else raster_content
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
        "posePreview": _pose_preview(
            frame_index,
            landmarks,
            skeleton,
            core.bbox,
            content,
            frame_bbox,
            state.frame_ml_landmarks.get(frame_index),
        ),
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
