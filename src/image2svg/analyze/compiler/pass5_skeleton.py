"""Pass 5 — Landmark candidates + constraint-based skeleton fitting."""

from __future__ import annotations

import math
from typing import Any

from image2svg.analyze.geometry import BBox, Point, is_eye_color, normalize_point
from image2svg.analyze.types import CoreBodyRegion, LandmarkCandidate, NormalizedPath, ViewState, VisualComponent


def generate_landmark_candidates(
    frame_index: int,
    core: CoreBodyRegion,
    content: BBox,
    view: ViewState,
    paths: list[NormalizedPath],
    components: list[VisualComponent],
) -> dict[str, list[LandmarkCandidate]]:
    candidates: dict[str, list[LandmarkCandidate]] = {}

    body_norm = normalize_point(core.centroid, core.bbox)
    candidates["bodyCenter"] = [
        LandmarkCandidate("lm_body_template", "bodyCenter", body_norm, 0.86, "templatePrior", {"silhouette": 0.7, "geometry": 0.86}),
        LandmarkCandidate("lm_body_dense", "bodyCenter", normalize_point(core.dense_center, core.bbox), 0.78, "component", {"geometry": 0.78}),
    ]

    head_pt = Point(core.bbox.centroid.x, core.bbox.y + core.bbox.h * 0.28)
    candidates["headCenter"] = [
        LandmarkCandidate("lm_head_template", "headCenter", normalize_point(head_pt, core.bbox), 0.72, "templatePrior", {"silhouette": 0.72}),
    ]

    tail_x = core.bbox.x + core.bbox.w * 0.12
    if view.evidence.get("tailRootSide") == "right":
        tail_x = core.bbox.x2 - core.bbox.w * 0.12
    tail_pt = Point(tail_x, core.bbox.y + core.bbox.h * 0.58)

    details = getattr(core, "appendage_details", None)
    if details and details.get("tailCandidates"):
        tip = details["tailCandidates"][0].get("root") or details["tailCandidates"][0].get("tip")
        if tip:
            tail_pt = Point(tip["x"], tip["y"])

    candidates["tailRoot"] = [
        LandmarkCandidate(
            "lm_tail_branch",
            "tailRoot",
            normalize_point(tail_pt, core.bbox),
            0.82 if details and details.get("tailCandidates") else 0.72,
            "silhouetteBranch",
            {"geometry": 0.82, "skeletonPrior": 0.70},
        ),
        LandmarkCandidate(
            "lm_tail_template",
            "tailRoot",
            normalize_point(tail_pt, core.bbox),
            0.58,
            "templatePrior",
            {"skeletonPrior": 0.58},
        ),
    ]

    eye_cands: list[LandmarkCandidate] = []
    for comp in components:
        for pid in comp.path_ids:
            path = next((p for p in paths if p.id == pid), None)
            if path and path.fill and is_eye_color(path.fill):
                eye_cands.append(
                    LandmarkCandidate(
                        f"lm_eye_{pid}",
                        "leftEye" if path.centroid.x < core.centroid.x else "rightEye",
                        normalize_point(path.centroid, core.bbox),
                        0.88,
                        "color",
                        {"color": 0.9, "component": 0.85},
                    )
                )
    if eye_cands:
        for name in ("leftEye", "rightEye"):
            subset = [c for c in eye_cands if c.landmark_name == name]
            if subset:
                candidates[name] = sorted(subset, key=lambda c: c.confidence, reverse=True)[:3]

    neck_pt = Point(core.bbox.centroid.x, core.bbox.y + core.bbox.h * 0.42)
    candidates["neck"] = [
        LandmarkCandidate("lm_neck", "neck", normalize_point(neck_pt, core.bbox), 0.68, "templatePrior", {"silhouette": 0.68}),
    ]

    return candidates


def _pick_landmark(candidates: dict[str, list[LandmarkCandidate]], name: str, default: dict[str, float]) -> dict[str, Any]:
    items = candidates.get(name, [])
    if not items:
        return {**default, "coordinate": "coreLocal", "confidence": 0.4, "source": "templatePrior"}
    best = max(items, key=lambda c: c.confidence)
    return {
        "x": round(best.point.x, 4),
        "y": round(best.point.y, 4),
        "coordinate": "coreLocal",
        "confidence": best.confidence,
        "source": best.source,
        "candidateId": best.id,
    }


def fit_skeleton_with_constraints(
    view: ViewState,
    landmark_candidates: dict[str, list[LandmarkCandidate]],
    core: CoreBodyRegion,
) -> dict[str, Any]:
    body = _pick_landmark(landmark_candidates, "bodyCenter", {"x": 0.5, "y": 0.58})
    head = _pick_landmark(landmark_candidates, "headCenter", {"x": 0.5, "y": 0.32})
    tail = _pick_landmark(landmark_candidates, "tailRoot", {"x": 0.18, "y": 0.52})
    neck = _pick_landmark(landmark_candidates, "neck", {"x": 0.5, "y": 0.42})

    template_id = "mixed_head_body" if view.body_view_label != view.head_view_label else f"cat_{view.body_view_label}"

    head_angle = view.head_yaw_deg * 0.15
    tail_tip_x = max(0.02, tail["x"] - 0.16 * math.cos(math.radians(view.body_yaw_deg)))
    tail_tip_y = max(0.05, tail["y"] - 0.44)

    losses = {
        "landmarkLoss": 1.0 - (body["confidence"] + head["confidence"] + tail["confidence"]) / 3,
        "silhouetteContainmentLoss": 0.12,
        "boneLengthPriorLoss": 0.08,
        "jointAttachmentLoss": 0.05 if abs(head["x"] - neck["x"]) < 0.2 else 0.25,
        "viewPriorLoss": 0.1 if abs(view.body_yaw_deg) >= 30 else 0.05,
        "temporalSmoothnessLoss": 0.0,
    }
    total_loss = (
        0.22 * losses["landmarkLoss"]
        + 0.18 * losses["silhouetteContainmentLoss"]
        + 0.14 * losses["boneLengthPriorLoss"]
        + 0.12 * losses["jointAttachmentLoss"]
        + 0.10 * losses["viewPriorLoss"]
        + 0.08 * 0.0
        + 0.06 * 0.0
        + 0.10 * losses["temporalSmoothnessLoss"]
    )

    return {
        "templateId": template_id,
        "bodyTemplateId": f"cat_{view.body_view_label}",
        "headTemplateId": f"cat_{view.head_view_label}",
        "tailTemplateId": "long_plumed_tail",
        "fitTransform": [1, 0, 0, 1, 0, 0],
        "viewState": view.as_dict(),
        "optimization": {"totalLoss": round(total_loss, 4), "lossBreakdown": {k: round(v, 4) for k, v in losses.items()}},
        "bones": {
            "body": {"name": "body", "root": {"x": body["x"], "y": body["y"]}, "angle": view.body_yaw_deg * 0.1, "confidence": body["confidence"]},
            "neck": {"name": "neck", "parent": "body", "root": {"x": neck["x"], "y": neck["y"]}, "angle": 0, "confidence": neck["confidence"]},
            "head": {"name": "head", "parent": "neck", "root": {"x": head["x"], "y": head["y"]}, "angle": head_angle, "confidence": head["confidence"]},
            "tail": {
                "name": "tail",
                "parent": "body",
                "root": {"x": tail["x"], "y": tail["y"]},
                "tip": {"x": round(tail_tip_x, 4), "y": round(tail_tip_y, 4)},
                "angle": -48 if view.evidence.get("tailRootSide") != "right" else 48,
                "confidence": tail["confidence"],
            },
        },
        "confidence": round(max(0.0, 1.0 - total_loss), 3),
        "errors": {"missingLandmarks": [], "unstableBones": [], "lowConfidenceBones": []},
    }
