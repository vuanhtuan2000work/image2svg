"""Multi-pass SVG analyzer orchestrator."""

from __future__ import annotations

from time import perf_counter
from typing import Any, Callable, Iterable

from svg_analyze.compiler.pass0_normalize import normalize_svg
from svg_analyze.compiler.pass1_raster import extract_raster_evidence, foreground_bbox_from_paths
from svg_analyze.compiler.pass2_frames import assign_paths_to_frames, generate_frame_candidates, select_frame_split
from svg_analyze.compiler.pass3_scene_graph import build_scene_graph, cluster_visual_components
from svg_analyze.compiler.pass4_core_view import detect_core_body_region, estimate_view_state
from svg_analyze.compiler.pass5_skeleton import fit_skeleton_with_constraints, generate_landmark_candidates
from svg_analyze.compiler.pass5b_ml_landmarks import ml_landmarks_enabled, mmpose_enabled
from svg_analyze.compiler.pass6_parts import infer_semantic_parts
from svg_analyze.compiler.pass7_temporal import (
    apply_temporal_label_repair,
    build_temporal_analysis,
    track_parts_across_frames,
)
from svg_analyze.compiler.pass8_export import export_analysis
from svg_analyze.correction_memory import apply_correction_priors
from svg_analyze.legacy_pipeline import _quality_report
from svg_analyze.types import CompilerState

ProgressCallback = Callable[[dict[str, Any]], None]


def compile_svg(
    svg_text: str,
    source_file: str,
    *,
    enable_ml_landmarks: bool | None = None,
    enable_mmpose: bool | None = None,
    focus_frames: Iterable[int] | None = None,
    progress: ProgressCallback | None = None,
) -> dict:
    """Run the multi-pass compiler and return analysis JSON v2.0."""
    started_at = perf_counter()

    def emit(step: str, message: str, **fields: Any) -> None:
        if progress is None:
            return
        progress(
            {
                "step": step,
                "message": message,
                "elapsedMs": round((perf_counter() - started_at) * 1000),
                **fields,
            }
        )

    emit("normalize", f"Normalize SVG: {source_file}")
    normalized_paths, meta = normalize_svg(svg_text, source_file)
    emit(
        "normalize",
        f"Normalized {len(normalized_paths)} drawable paths",
        pathCount=len(normalized_paths),
        width=meta["width"],
        height=meta["height"],
    )
    state = CompilerState(
        source_file=source_file,
        asset_id=meta["asset_id"],
        svg_text=svg_text,
        view_box=meta["view_box"],
        width=meta["width"],
        height=meta["height"],
        normalized_paths=normalized_paths,
        warnings=list(meta.get("warnings", [])),
    )

    if not normalized_paths:
        state.warnings.append("No paths found after normalization")
        state.selected_frame_split = select_frame_split([])
        emit("export", "No paths found; exporting empty analysis", level="warning")
        return export_analysis(state)

    emit("raster", "Render raster evidence for masks/color/frame splitting")
    state.raster = extract_raster_evidence(
        svg_text,
        state.view_box,
        normalized_paths,
        display_width=state.width,
        display_height=state.height,
    )
    state.warnings.extend(state.raster.warnings)
    emit(
        "raster",
        f"Raster ready: {state.raster.width}x{state.raster.height}",
        rasterWidth=state.raster.width,
        rasterHeight=state.raster.height,
        warnings=state.raster.warnings,
    )

    emit("frames", "Generate frame split candidates")
    state.frame_candidates, preferred_frames = generate_frame_candidates(
        normalized_paths,
        state.view_box,
        state.raster,
        svg_text,
        source_file,
        display_width=state.width,
        display_height=state.height,
    )
    emit("frames", f"Generated {len(state.frame_candidates)} frame split candidates")
    state.selected_frame_split = select_frame_split(
        state.frame_candidates,
        preferred_frame_count=preferred_frames,
    )
    emit(
        "frames",
        f"Selected {state.selected_frame_split.frame_count} frame(s) via {state.selected_frame_split.method}",
        frameCount=state.selected_frame_split.frame_count,
        method=state.selected_frame_split.method,
        score=round(state.selected_frame_split.score, 4),
    )
    state.path_buckets = assign_paths_to_frames(normalized_paths, state.selected_frame_split.frame_bboxes)

    emit("priors", "Apply saved correction priors")
    priors = apply_correction_priors(state.asset_id)
    frame_count = state.selected_frame_split.frame_count
    state.frame_component_rows = {}
    requested_focus = set()
    if focus_frames:
        requested_focus = {int(i) for i in focus_frames if isinstance(i, int) or str(i).lstrip("-").isdigit()}
    focus_frame_indices = {i for i in requested_focus if 0 <= i < frame_count}
    if requested_focus and focus_frame_indices:
        emit(
            "focus",
            f"Focused re-analysis for {len(focus_frame_indices)}/{frame_count} frame(s)",
            frameIndices=sorted(focus_frame_indices),
        )
    elif requested_focus:
        emit("focus", "No valid focused frames; running full analysis", level="warning")
    use_ml_landmarks = ml_landmarks_enabled(enable_ml_landmarks)
    use_mmpose = mmpose_enabled(enable_mmpose) if use_ml_landmarks else False
    ml_frame_indices = focus_frame_indices or set(range(frame_count))
    mmpose_status: dict[str, Any] | None = None
    if use_ml_landmarks:
        emit(
            "ml",
            "ML landmarks enabled: silhouette pass will run"
            + ("; checking MMPose readiness" if use_mmpose else "; MMPose disabled"),
            mmposeEnabled=use_mmpose,
        )
        if use_mmpose:
            from svg_analyze.ml.landmarks import get_mmpose_readiness

            mmpose_status = get_mmpose_readiness()
            emit(
                "ml",
                "MMPose ready" if mmpose_status.get("status") == "ready" else f"MMPose skipped: {mmpose_status.get('reason')}",
                mmposeStatus=mmpose_status,
                level="info" if mmpose_status.get("status") == "ready" else "warning",
            )
    else:
        emit("ml", "ML landmarks disabled")

    for frame_index in range(frame_count):
        emit(
            "frame",
            f"Frame {frame_index + 1}/{frame_count}: build scene graph",
            frameIndex=frame_index,
            frameCount=frame_count,
        )
        paths = state.path_buckets.get(frame_index, [])
        frame_bbox = state.selected_frame_split.frame_bboxes[frame_index]
        content_bbox = foreground_bbox_from_paths(paths, frame_bbox) or frame_bbox

        components = cluster_visual_components(paths, frame_index)
        state.frame_components[frame_index] = components
        state.frame_graphs[frame_index] = build_scene_graph(frame_index, paths, components)

        core = detect_core_body_region(content_bbox, paths, components, state.raster, state.view_box)
        state.frame_core_regions[frame_index] = core

        view = estimate_view_state(core, paths, content_bbox)
        state.frame_views[frame_index] = view

        emit("landmarks", f"Frame {frame_index + 1}/{frame_count}: generate heuristic landmarks", frameIndex=frame_index)
        lm_candidates = generate_landmark_candidates(frame_index, core, content_bbox, view, paths, components)
        for name, items in lm_candidates.items():
            for item in items:
                if name == "tailRoot" and item.source == "silhouetteBranch":
                    item.confidence *= priors.get("silhouetteBranch_tailRoot", 1.0)
                if "Eye" in name and item.source == "color":
                    item.confidence *= priors.get("color_eye", 1.0)
        state.frame_landmark_candidates[frame_index] = lm_candidates

        if use_ml_landmarks and frame_index in ml_frame_indices:
            from svg_analyze.ml.landmarks import infer_frame_ml_landmarks, merge_ml_into_candidates

            emit("ml", f"Frame {frame_index + 1}/{frame_count}: infer silhouette landmarks", frameIndex=frame_index)
            ml_result = infer_frame_ml_landmarks(
                frame_index=frame_index,
                frame_bbox=content_bbox,
                view_box=state.view_box,
                raster=state.raster,
                enable_mmpose=use_mmpose,
                mmpose_readiness=mmpose_status,
            )
            state.frame_ml_landmarks[frame_index] = ml_result
            lm_candidates = merge_ml_into_candidates(lm_candidates, ml_result)
            state.frame_landmark_candidates[frame_index] = lm_candidates
            emit(
                "ml",
                f"Frame {frame_index + 1}/{frame_count}: ML backend {ml_result.get('backend') or ml_result.get('status')}",
                frameIndex=frame_index,
                mlStatus=ml_result,
            )
        elif use_ml_landmarks:
            state.frame_ml_landmarks[frame_index] = {
                "status": "skipped",
                "backend": "focusFrames",
                "frameIndex": frame_index,
                "reason": "Skipped by focused re-analysis",
            }

        emit("skeleton", f"Frame {frame_index + 1}/{frame_count}: fit skeleton", frameIndex=frame_index)
        skeleton = fit_skeleton_with_constraints(view, lm_candidates, core)
        state.frame_skeletons[frame_index] = skeleton

        emit("parts", f"Frame {frame_index + 1}/{frame_count}: infer semantic parts", frameIndex=frame_index)
        semantic_parts, _labels, component_rows = infer_semantic_parts(
            frame_index, components, paths, core, skeleton, view
        )
        state.frame_semantic_parts[frame_index] = semantic_parts
        state.frame_component_rows[frame_index] = component_rows

    emit("temporal", "Apply temporal label repair and track parts")
    state.frame_semantic_parts = apply_temporal_label_repair(
        state.frame_semantic_parts,
        state.frame_component_rows,
    )
    state.temporal_tracks = track_parts_across_frames(state.frame_semantic_parts)

    frames_for_temporal = []
    for i in range(frame_count):
        frames_for_temporal.append(
            {
                "frameIndex": i,
                "landmarks": _pick_simple_landmarks(state.frame_landmark_candidates.get(i, {})),
                "semanticParts": state.frame_semantic_parts.get(i, []),
            }
        )
    state.temporal_analysis = build_temporal_analysis(frames_for_temporal, state.temporal_tracks)
    emit("quality", "Build quality report")
    state.quality_report = _quality_report(
        [_minimal_frame(i, state) for i in range(frame_count)],
        state.temporal_analysis,
        state.warnings,
    )
    state.quality_report["compilerVersion"] = "2.0"
    state.quality_report["frameSplitConfidence"] = round(state.selected_frame_split.score, 4)

    emit("export", "Analysis complete", level="success")
    return export_analysis(state)


def _pick_simple_landmarks(candidates: dict) -> dict:
    out = {}
    for name, items in candidates.items():
        if items:
            best = max(items, key=lambda c: c.confidence)
            out[name] = {"x": best.point.x, "y": best.point.y}
    return out


def _minimal_frame(index: int, state: CompilerState) -> dict:
    view = state.frame_views[index]
    return {
        "frameIndex": index,
        "view": {"bodyView": view.body_view_label, "headView": view.head_view_label},
        "quality": {"score": 0.7, "errors": [], "warnings": []},
        "skeleton": state.frame_skeletons[index],
        "landmarks": _pick_simple_landmarks(state.frame_landmark_candidates.get(index, {})),
        "semanticParts": state.frame_semantic_parts.get(index, []),
    }
