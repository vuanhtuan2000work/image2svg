"""Optional ML landmark backends."""

from image2svg.analyze.ml.landmarks import infer_frame_ml_landmarks, merge_ml_into_candidates

__all__ = ["infer_frame_ml_landmarks", "merge_ml_into_candidates"]
