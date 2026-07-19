"""Pass 4 — Core body region + medial axis appendages + continuous view."""

from __future__ import annotations

from typing import Any

from image2svg.analyze.compiler.pass1_raster import crop_alpha_to_bbox, crop_density_to_bbox
from image2svg.analyze.compiler.medial_axis import classify_appendages, compute_medial_axis
from image2svg.analyze.geometry import BBox, Point, is_eye_color, union_bbox
from image2svg.analyze.types import CoreBodyRegion, NormalizedPath, RasterEvidence, ViewState


def _label_from_yaw(yaw: float) -> str:
    yaw = ((yaw + 180) % 360) - 180
    if -22.5 <= yaw < 22.5:
        return "front"
    if 22.5 <= yaw < 67.5:
        return "frontRight"
    if 67.5 <= yaw < 112.5:
        return "right"
    if 112.5 <= yaw < 157.5:
        return "backRight"
    if yaw >= 157.5 or yaw < -157.5:
        return "back"
    if -157.5 <= yaw < -112.5:
        return "backLeft"
    if -112.5 <= yaw < -67.5:
        return "left"
    return "frontLeft"


def detect_core_body_region(
    content: BBox,
    paths: list[NormalizedPath],
    components: list[Any],
    raster: RasterEvidence | None,
    view_box: tuple[float, float, float, float] | None = None,
) -> CoreBodyRegion:
    trim_x = content.w * 0.10
    trim_y = content.h * 0.08
    core = BBox(content.x + trim_x, content.y + trim_y, content.w - 2 * trim_x, content.h - 2 * trim_y)

    dense_paths = sorted(
        [p for p in paths if p.bbox.area > content.area * 0.02 and p.thinness > 0.08],
        key=lambda p: p.bbox.area,
        reverse=True,
    )[:8]
    if dense_paths:
        merged = union_bbox(p.bbox for p in dense_paths)
        if merged:
            core = BBox(
                max(content.x, merged.x),
                max(content.y, merged.y),
                min(content.w * 0.92, merged.w),
                min(content.h * 0.78, merged.h),
            )

    dense_center = core.centroid
    medial_meta: dict[str, Any] = {}
    appendages: dict[str, list[Any]] = {
        "tailCandidates": [],
        "earCandidates": [],
        "legCandidates": [],
        "whiskerCandidates": [],
        "furTipCandidates": [],
        "detachedNoise": [],
    }

    if raster and raster.alpha_mask is not None and view_box is not None:
        try:
            import numpy as np

            frame_alpha = crop_alpha_to_bbox(raster, content, view_box)
            frame_density = crop_density_to_bbox(raster, content, view_box)
            if frame_alpha is not None and frame_alpha.size > 0:
                occupancy = float(frame_alpha.mean())
                if occupancy > 0.92:
                    raise ValueError("skip_medial_axis_full_background_crop")
                # Downsample large masks for faster Zhang-Suen
                fh, fw = frame_alpha.shape
                step = max(1, max(fh, fw) // 128)
                if step > 1:
                    frame_alpha = frame_alpha[::step, ::step]
                    frame_density = frame_density[::step, ::step] if frame_density is not None else None

                dm = frame_density if frame_density is not None else raster.density_map
                if dm is not None and frame_density is None:
                    peak_idx = np.unravel_index(np.argmax(dm), dm.shape)
                    rh, rw = dm.shape
                    dense_center = Point(
                        content.x + (peak_idx[1] / rw) * content.w,
                        content.y + (peak_idx[0] / rh) * content.h,
                    )
                elif frame_density is not None:
                    peak_idx = np.unravel_index(np.argmax(frame_density), frame_density.shape)
                    rh, rw = frame_density.shape
                    dense_center = Point(
                        content.x + (peak_idx[1] / rw) * content.w,
                        content.y + (peak_idx[0] / rh) * content.h,
                    )

                axis = compute_medial_axis(frame_alpha, frame_density)
                medial_meta = axis.as_dict()
                classified = classify_appendages(
                    axis, core, content, frame_alpha.shape[1], frame_alpha.shape[0]
                )
                appendages["tailCandidates"] = classified["tailCandidates"]
                appendages["earCandidates"] = classified["earCandidates"]
                appendages["legCandidates"] = classified["legCandidates"]
                appendages["whiskerCandidates"] = classified["whiskerCandidates"]
        except Exception:
            pass
    elif raster and raster.density_map is not None:
        try:
            import numpy as np

            dm = raster.density_map
            peak_idx = np.unravel_index(np.argmax(dm), dm.shape)
            rh, rw = dm.shape
            dense_center = Point(
                content.x + (peak_idx[1] / rw) * content.w,
                content.y + (peak_idx[0] / rh) * content.h,
            )
        except Exception:
            pass

    if not appendages["tailCandidates"]:
        for comp in components:
            elongated = comp.features.get("elongatedness", 1.0)
            if elongated > 2.5 and comp.centroid.x < core.x + core.w * 0.2:
                appendages["tailCandidates"].append({"componentId": comp.id, "confidence": 0.55, "source": "heuristic"})
            elif comp.area < content.area * 0.005:
                appendages["detachedNoise"].append(comp.id)

    region = CoreBodyRegion(
        bbox=core,
        centroid=core.centroid,
        dense_center=dense_center,
        confidence=0.78 if dense_paths else 0.45,
        excluded_appendages={
            "tailCandidates": [c.get("branchId") or c.get("componentId", str(c)) for c in appendages["tailCandidates"]],
            "whiskerCandidates": [c.get("branchId") or c.get("componentId", str(c)) for c in appendages["whiskerCandidates"]],
            "furTipCandidates": appendages.get("furTipCandidates", []),
            "detachedNoise": appendages.get("detachedNoise", []),
        },
    )
    region.medial_axis = medial_meta  # type: ignore[attr-defined]
    region.appendage_details = appendages  # type: ignore[attr-defined]
    return region


def estimate_view_state(
    core: CoreBodyRegion,
    paths: list[NormalizedPath],
    content: BBox,
) -> ViewState:
    eye_paths = [p for p in paths if p.fill and is_eye_color(p.fill)]
    eye_count = len(eye_paths)
    aspect = core.bbox.aspect_ratio

    left_mass = sum(p.bbox.area for p in paths if p.centroid.x < core.centroid.x)
    right_mass = sum(p.bbox.area for p in paths if p.centroid.x >= core.centroid.x)
    asym = (right_mass - left_mass) / max(left_mass + right_mass, 1.0)

    body_yaw = 0.0
    if aspect >= 1.35:
        body_yaw = 70.0 if asym >= 0 else -70.0
    elif aspect <= 0.95:
        body_yaw = 0.0
    else:
        body_yaw = 35.0 if asym >= 0 else -35.0

    head_yaw = body_yaw * 0.45
    if eye_count >= 2 and abs(body_yaw) >= 45:
        head_yaw = body_yaw * 0.35

    body_label = _label_from_yaw(body_yaw)
    head_label = _label_from_yaw(head_yaw)

    candidates = [
        {"label": body_label, "kind": "body", "score": round(0.55 + min(0.35, abs(asym)), 3)},
        {"label": _label_from_yaw(body_yaw + 25), "kind": "body", "score": round(0.35 + abs(asym) * 0.2, 3)},
        {"label": _label_from_yaw(body_yaw - 25), "kind": "body", "score": round(0.30 + abs(asym) * 0.15, 3)},
        {"label": head_label, "kind": "head", "score": round(0.5 + min(0.4, eye_count * 0.12), 3)},
        {"label": "front", "kind": "head", "score": round(0.35 + (0.25 if eye_count >= 2 else 0.0), 3)},
    ]
    candidates.sort(key=lambda c: c["score"], reverse=True)

    tail_side = "unknown"
    details = getattr(core, "appendage_details", None)
    if details and details.get("tailCandidates"):
        tip = details["tailCandidates"][0].get("tip", {})
        tail_side = "left" if tip.get("x", core.centroid.x) < core.centroid.x else "right"
    else:
        tail_paths = [p for p in paths if p.centroid.x < core.bbox.x or p.centroid.x > core.bbox.x2]
        if tail_paths:
            tail_side = "left" if sum(1 for p in tail_paths if p.centroid.x < core.centroid.x) >= len(tail_paths) / 2 else "right"

    return ViewState(
        body_yaw_deg=body_yaw,
        head_yaw_deg=head_yaw,
        tail_plane_deg=-30.0 if tail_side == "left" else 30.0 if tail_side == "right" else None,
        body_view_label=body_label,
        head_view_label=head_label,
        confidence={"bodyYaw": 0.62, "headYaw": 0.55, "tailPlane": 0.45 if tail_side != "unknown" else 0.2},
        evidence={
            "silhouetteAspect": round(aspect, 3),
            "bodyMassAsymmetry": round(asym, 3),
            "headBodyOffsetX": round((core.dense_center.x - core.centroid.x) / max(core.bbox.w, 1), 3),
            "eyeVisibility": {"count": eye_count, "pairDistance": 0.0, "symmetry": 0.0},
            "tailRootSide": tail_side,
            "pawStagger": "sideStaggered" if abs(body_yaw) >= 45 else "symmetric",
            "medialAxisBranches": getattr(core, "medial_axis", {}).get("branchCount", 0),
        },
        candidates=candidates[:6],
    )
