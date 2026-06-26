"""Multi-pass SVG analyzer orchestrator."""

from __future__ import annotations

from svg_analyze.compiler.pass0_normalize import normalize_svg
from svg_analyze.compiler.pass1_raster import extract_raster_evidence
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


def compile_svg(
    svg_text: str,
    source_file: str,
    *,
    enable_ml_landmarks: bool | None = None,
    enable_mmpose: bool | None = None,
) -> dict:
    """Run the multi-pass compiler and return analysis JSON v2.0."""

    normalized_paths, meta = normalize_svg(svg_text, source_file)
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
        return export_analysis(state)

    state.raster = extract_raster_evidence(
        svg_text,
        state.view_box,
        normalized_paths,
        display_width=state.width,
        display_height=state.height,
    )
    state.warnings.extend(state.raster.warnings)

    state.frame_candidates, preferred_frames = generate_frame_candidates(
        normalized_paths,
        state.view_box,
        state.raster,
        svg_text,
        source_file,
        display_width=state.width,
        display_height=state.height,
    )
    state.selected_frame_split = select_frame_split(
        state.frame_candidates,
        preferred_frame_count=preferred_frames,
    )
    state.path_buckets = assign_paths_to_frames(normalized_paths, state.selected_frame_split.frame_bboxes)

    priors = apply_correction_priors(state.asset_id)
    frame_count = state.selected_frame_split.frame_count
    state.frame_component_rows = {}

    for frame_index in range(frame_count):
        paths = state.path_buckets.get(frame_index, [])
        frame_bbox = state.selected_frame_split.frame_bboxes[frame_index]

        components = cluster_visual_components(paths, frame_index)
        state.frame_components[frame_index] = components
        state.frame_graphs[frame_index] = build_scene_graph(frame_index, paths, components)

        core = detect_core_body_region(frame_bbox, paths, components, state.raster, state.view_box)
        state.frame_core_regions[frame_index] = core

        view = estimate_view_state(core, paths, frame_bbox)
        state.frame_views[frame_index] = view

        lm_candidates = generate_landmark_candidates(frame_index, core, frame_bbox, view, paths, components)
        for name, items in lm_candidates.items():
            for item in items:
                if name == "tailRoot" and item.source == "silhouetteBranch":
                    item.confidence *= priors.get("silhouetteBranch_tailRoot", 1.0)
                if "Eye" in name and item.source == "color":
                    item.confidence *= priors.get("color_eye", 1.0)
        state.frame_landmark_candidates[frame_index] = lm_candidates

        if ml_landmarks_enabled(enable_ml_landmarks):
            from svg_analyze.ml.landmarks import infer_frame_ml_landmarks, merge_ml_into_candidates
            from svg_analyze.compiler.pass5b_ml_landmarks import mmpose_enabled

            ml_result = infer_frame_ml_landmarks(
                frame_index=frame_index,
                frame_bbox=frame_bbox,
                view_box=state.view_box,
                raster=state.raster,
                enable_mmpose=mmpose_enabled(enable_mmpose),
            )
            state.frame_ml_landmarks[frame_index] = ml_result
            state.frame_landmark_candidates[frame_index] = merge_ml_into_candidates(lm_candidates, ml_result)

        skeleton = fit_skeleton_with_constraints(view, lm_candidates, core)
        state.frame_skeletons[frame_index] = skeleton

        semantic_parts, _labels, component_rows = infer_semantic_parts(
            frame_index, components, paths, core, skeleton, view
        )
        state.frame_semantic_parts[frame_index] = semantic_parts
        state.frame_component_rows[frame_index] = component_rows

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
    state.quality_report = _quality_report(
        [_minimal_frame(i, state) for i in range(frame_count)],
        state.temporal_analysis,
        state.warnings,
    )
    state.quality_report["compilerVersion"] = "2.0"
    state.quality_report["frameSplitConfidence"] = round(state.selected_frame_split.score, 4)

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
