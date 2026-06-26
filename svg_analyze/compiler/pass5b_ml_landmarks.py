"""Optional pass — ML landmarks on raster frame crops (MMPose + silhouette fallback)."""

from __future__ import annotations

import os

from svg_analyze.ml.landmarks import infer_frame_ml_landmarks, merge_ml_into_candidates
from svg_analyze.types import CompilerState


def ml_landmarks_enabled(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return explicit
    return os.environ.get("IMAGE2SVG_ML_LANDMARKS", "").strip().lower() in {"1", "true", "yes", "on"}


def mmpose_enabled(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return explicit
    return os.environ.get("IMAGE2SVG_MMPOSE", "").strip().lower() in {"1", "true", "yes", "on"}


def apply_ml_landmarks(state: CompilerState, *, enable: bool | None = None, enable_mmpose: bool | None = None) -> None:
    """Populate state.frame_ml_landmarks and merge into landmark candidates."""
    if not ml_landmarks_enabled(enable):
        return
    if state.selected_frame_split is None or state.raster is None:
        return

    use_mmpose = mmpose_enabled(enable_mmpose)
    for frame_index, frame_bbox in enumerate(state.selected_frame_split.frame_bboxes):
        ml_result = infer_frame_ml_landmarks(
            frame_index=frame_index,
            frame_bbox=frame_bbox,
            view_box=state.view_box,
            raster=state.raster,
            enable_mmpose=use_mmpose,
        )
        state.frame_ml_landmarks[frame_index] = ml_result
        candidates = state.frame_landmark_candidates.get(frame_index, {})
        state.frame_landmark_candidates[frame_index] = merge_ml_into_candidates(candidates, ml_result)
