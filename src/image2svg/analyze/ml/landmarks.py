"""Optional ML landmark backends (MMPose when installed, silhouette fallback)."""

from __future__ import annotations

from typing import Any

from image2svg.analyze.geometry import BBox, Point
from image2svg.analyze.types import LandmarkCandidate, RasterEvidence

__all__ = ["get_mmpose_readiness", "infer_frame_ml_landmarks", "merge_ml_into_candidates"]


def get_mmpose_readiness() -> dict[str, Any]:
    try:
        from image2svg.analyze.ml.mmpose_backend import mmpose_readiness
    except ImportError as exc:
        return {"status": "skipped", "reason": f"mmpose_backend unavailable: {exc}"}
    return mmpose_readiness()


def infer_frame_ml_landmarks(
    *,
    frame_index: int,
    frame_bbox: BBox,
    view_box: tuple[float, float, float, float],
    raster: RasterEvidence | None,
    enable_mmpose: bool,
    mmpose_readiness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run optional ML landmark inference on a cropped frame render."""
    if raster is None:
        return {"status": "skipped", "backend": None, "reason": "no_raster"}

    from image2svg.analyze.compiler.pass1_raster import crop_alpha_to_bbox, crop_rgba_to_bbox, rgba_crop_to_png_bytes

    alpha = crop_alpha_to_bbox(raster, frame_bbox, view_box)
    if alpha is None or not alpha.any():
        return {"status": "skipped", "backend": None, "reason": "empty_frame_crop"}

    silhouette = _silhouette_landmarks(alpha, frame_bbox)
    result: dict[str, Any] = {
        "status": "ok",
        "backend": "silhouette",
        "frameIndex": frame_index,
        "keypoints": silhouette["keypoints"],
        "confidence": silhouette["confidence"],
    }

    if not enable_mmpose:
        result["mmpose"] = {"status": "disabled"}
        return result

    readiness = mmpose_readiness or get_mmpose_readiness()
    if readiness.get("status") != "ready":
        result["mmpose"] = readiness
        return result

    rgba = crop_rgba_to_bbox(raster, frame_bbox, view_box)
    if rgba is None:
        result["mmpose"] = {"status": "skipped", "reason": "no_rgb_crop"}
        return result

    png_bytes = rgba_crop_to_png_bytes(rgba)
    mmpose_result = _try_mmpose(png_bytes, frame_bbox)
    result["mmpose"] = mmpose_result

    if mmpose_result.get("status") == "ok":
        result["backend"] = "mmpose+silhouette"
        merged = _merge_keypoints(silhouette["keypoints"], mmpose_result.get("keypoints", []))
        result["keypoints"] = merged
        result["confidence"] = max(silhouette["confidence"], mmpose_result.get("confidence", 0.0))

    return result


def merge_ml_into_candidates(
    candidates: dict[str, list[LandmarkCandidate]],
    ml_result: dict[str, Any],
) -> dict[str, list[LandmarkCandidate]]:
    """Add ML keypoints as extra landmark candidates (lower priority than heuristics)."""
    if ml_result.get("status") != "ok":
        return candidates

    out = {k: list(v) for k, v in candidates.items()}
    backend = ml_result.get("backend") or "ml"
    for kp in ml_result.get("keypoints", []):
        name = kp.get("name")
        if not name:
            continue
        point = Point(float(kp["x"]), float(kp["y"]))
        confidence = float(kp.get("confidence", 0.35))
        item = LandmarkCandidate(
            id=f"ml_{backend}_{name}",
            landmark_name=name,
            point=point,
            confidence=confidence,
            source="templatePrior",
            evidence={"mlBackend": 1.0, "rawScore": confidence},
        )
        out.setdefault(name, []).append(item)
    return out


def _silhouette_landmarks(alpha: Any, frame_bbox: BBox) -> dict[str, Any]:
    import numpy as np

    ys, xs = np.where(alpha)
    if len(xs) == 0:
        return {"keypoints": [], "confidence": 0.0}

    h, w = alpha.shape
    cx = float(xs.mean())
    cy = float(ys.mean())
    top_y = float(ys.min())
    bottom_y = float(ys.max())
    left_x = float(xs.min())
    right_x = float(xs.max())

    # Map crop-local pixels back to SVG coordinates.
    scale_x = frame_bbox.w / max(w, 1)
    scale_y = frame_bbox.h / max(h, 1)

    def to_svg(lx: float, ly: float) -> tuple[float, float]:
        return frame_bbox.x + lx * scale_x, frame_bbox.y + ly * scale_y

    head_x, head_y = to_svg(cx, top_y + (cy - top_y) * 0.35)
    body_x, body_y = to_svg(cx, cy)
    tail_x, tail_y = to_svg(right_x if cx > w / 2 else left_x, cy)
    root_x, root_y = to_svg(cx, bottom_y * 0.92 + cy * 0.08)

    keypoints = [
        {"name": "headCenter", "x": head_x, "y": head_y, "confidence": 0.42},
        {"name": "bodyCenter", "x": body_x, "y": body_y, "confidence": 0.45},
        {"name": "tailRoot", "x": tail_x, "y": tail_y, "confidence": 0.38},
        {"name": "root", "x": root_x, "y": root_y, "confidence": 0.40},
    ]
    return {"keypoints": keypoints, "confidence": 0.42}


def _merge_keypoints(base: list[dict[str, Any]], extra: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {kp["name"]: dict(kp) for kp in base if kp.get("name")}
    for kp in extra:
        name = kp.get("name")
        if not name:
            continue
        prev = by_name.get(name)
        if prev is None or float(kp.get("confidence", 0)) > float(prev.get("confidence", 0)):
            by_name[name] = dict(kp)
    return list(by_name.values())


def _try_mmpose(png_bytes: bytes, frame_bbox: BBox) -> dict[str, Any]:
    try:
        from image2svg.analyze.ml.mmpose_backend import infer_animal_pose
    except ImportError as exc:
        return {"status": "skipped", "reason": f"mmpose_backend unavailable: {exc}"}

    try:
        raw = infer_animal_pose(png_bytes)
    except Exception as exc:  # noqa: BLE001 — optional backend
        return {"status": "error", "reason": str(exc)}

    if raw.get("status") != "ok":
        return raw

    mapped: list[dict[str, Any]] = []
    for kp in raw.get("keypoints", []):
        lx, ly = float(kp["x"]), float(kp["y"])
        scale_x = frame_bbox.w / max(float(raw.get("imageWidth", 1)), 1.0)
        scale_y = frame_bbox.h / max(float(raw.get("imageHeight", 1)), 1.0)
        mapped.append(
            {
                "name": kp.get("name", kp.get("label", "unknown")),
                "x": frame_bbox.x + lx * scale_x,
                "y": frame_bbox.y + ly * scale_y,
                "confidence": float(kp.get("confidence", 0.5)),
                "sourceLabel": kp.get("label"),
            }
        )
    return {
        "status": "ok",
        "model": raw.get("model"),
        "keypoints": mapped,
        "confidence": float(raw.get("confidence", 0.5)),
    }
