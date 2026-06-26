"""Shared types for the multi-pass SVG analyzer compiler."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from svg_analyze.geometry import BBox, Point

FrameSplitMethod = Literal[
    "connectedComponents",
    "rasterComponents",
    "alphaProjection",
    "dynamicProgramming",
    "equalWidth",
    "viewBoxAspect",
    "hybrid",
    "legacyHistogram",
]

SceneRelation = Literal[
    "overlaps",
    "contains",
    "near",
    "sameColorCluster",
    "sameZBand",
    "touches",
    "insideSilhouette",
    "nearBone",
    "candidateForPart",
    "temporalMatch",
]

LandmarkSource = Literal[
    "color",
    "component",
    "silhouetteBranch",
    "templatePrior",
    "temporalPrediction",
    "manual",
]

CatPartName = Literal[
    "bodySet",
    "headBase",
    "earSet",
    "eyeSet",
    "faceSet",
    "frontLegSet",
    "backLegSet",
    "tailSet",
    "patternOverlay",
    "furDetail",
    "outline",
    "shadow",
    "unknown",
]


@dataclass
class CurvatureStats:
    mean: float = 0.0
    max: float = 0.0
    std: float = 0.0


@dataclass
class NormalizedPath:
    id: str
    original_index: int
    d: str
    d_hash: str
    fill: str | None
    stroke: str | None
    opacity: float
    fill_rule: str
    bbox: BBox
    exact_bbox: BBox | None
    sampled_bbox: BBox | None
    centroid: Point
    area: float
    perimeter: float
    path_length: float
    closed: bool
    aspect_ratio: float
    thinness: float
    compactness: float
    convexity: float
    curvature: CurvatureStats | None = None
    z_index: int = 0
    z_normalized: float = 0.0
    element_id: str | None = None
    source_tag: str = "path"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "originalIndex": self.original_index,
            "dHash": self.d_hash,
            "style": {
                "fill": self.fill,
                "stroke": self.stroke,
                "opacity": self.opacity,
                "fillRule": self.fill_rule,
            },
            "geometry": {
                "bbox": self.bbox.as_dict(),
                "exactBBox": self.exact_bbox.as_dict() if self.exact_bbox else None,
                "sampledBBox": self.sampled_bbox.as_dict() if self.sampled_bbox else None,
                "centroid": self.centroid.as_dict(),
                "area": round(self.area, 2),
                "perimeter": round(self.perimeter, 2),
                "pathLength": round(self.path_length, 2),
                "closed": self.closed,
                "aspectRatio": round(self.aspect_ratio, 3),
                "thinness": round(self.thinness, 3),
                "compactness": round(self.compactness, 4),
                "convexity": round(self.convexity, 3),
            },
            "z": {"index": self.z_index, "normalized": round(self.z_normalized, 4)},
            "sourceTag": self.source_tag,
        }


@dataclass
class MaskRef:
    width: int
    height: int
    scale: float
    offset_x: float
    offset_y: float
    kind: Literal["alpha", "colorLabel", "edge", "density"]


@dataclass
class RasterEvidence:
    width: int
    height: int
    scale: float
    content_bbox: BBox
    alpha_mask: Any  # numpy bool array
    color_label_mask: Any | None
    edge_mask: Any | None
    density_map: Any | None
    rgb_image: Any | None = None  # HxWx3 uint8, optional full-sheet RGB
    color_clusters: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class FrameSplitScoreBreakdown:
    gap_score: float = 0.0
    cut_penalty: float = 0.0
    component_containment: float = 0.0
    aspect_consistency: float = 0.0
    path_crossing_penalty: float = 0.0
    content_coverage: float = 0.0

    @property
    def total(self) -> float:
        return (
            0.20 * self.gap_score
            + 0.20 * (1.0 - min(1.0, self.cut_penalty))
            + 0.18 * self.component_containment
            + 0.15 * self.aspect_consistency
            + 0.17 * (1.0 - min(1.0, self.path_crossing_penalty))
            + 0.10 * self.content_coverage
        )


@dataclass
class FrameSplitCandidate:
    method: FrameSplitMethod
    frame_count: int
    frame_bboxes: list[BBox]
    direction: Literal["horizontal", "vertical", "unknown"]
    score: float
    score_breakdown: FrameSplitScoreBreakdown
    split_positions: list[float] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "frameCount": self.frame_count,
            "frameBBoxes": [b.as_dict() for b in self.frame_bboxes],
            "direction": self.direction,
            "score": round(self.score, 4),
            "scoreBreakdown": {
                "gapScore": round(self.score_breakdown.gap_score, 4),
                "cutPenalty": round(self.score_breakdown.cut_penalty, 4),
                "componentContainment": round(self.score_breakdown.component_containment, 4),
                "aspectConsistency": round(self.score_breakdown.aspect_consistency, 4),
                "pathCrossingPenalty": round(self.score_breakdown.path_crossing_penalty, 4),
                "contentCoverage": round(self.score_breakdown.content_coverage, 4),
            },
            "splitPositions": [round(v, 2) for v in self.split_positions],
        }


@dataclass
class VisualComponent:
    id: str
    path_ids: list[str]
    bbox: BBox
    centroid: Point
    area: float
    dominant_color_cluster: str | None
    z_range: tuple[int, int]
    features: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pathIds": self.path_ids,
            "bbox": self.bbox.as_dict(),
            "centroid": self.centroid.as_dict(),
            "area": round(self.area, 2),
            "dominantColorCluster": self.dominant_color_cluster,
            "zRange": list(self.z_range),
            "features": {k: round(v, 4) for k, v in self.features.items()},
        }


@dataclass
class SceneEdge:
    from_id: str
    to_id: str
    relation: SceneRelation
    weight: float


@dataclass
class LandmarkCandidate:
    id: str
    landmark_name: str
    point: Point
    confidence: float
    source: LandmarkSource
    evidence: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "landmarkName": self.landmark_name,
            "point": self.point.as_dict(),
            "confidence": round(self.confidence, 4),
            "source": self.source,
            "evidence": {k: round(v, 4) for k, v in self.evidence.items()},
        }


@dataclass
class ViewState:
    body_yaw_deg: float
    head_yaw_deg: float
    tail_plane_deg: float | None
    body_view_label: str
    head_view_label: str
    confidence: dict[str, float]
    evidence: dict[str, Any]
    candidates: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "bodyYawDeg": round(self.body_yaw_deg, 2),
            "headYawDeg": round(self.head_yaw_deg, 2),
            "tailPlaneDeg": round(self.tail_plane_deg, 2) if self.tail_plane_deg is not None else None,
            "bodyViewLabel": self.body_view_label,
            "headViewLabel": self.head_view_label,
            "confidence": {k: round(v, 4) for k, v in self.confidence.items()},
            "evidence": self.evidence,
            "candidates": self.candidates,
        }


@dataclass
class CoreBodyRegion:
    bbox: BBox
    centroid: Point
    dense_center: Point
    confidence: float
    excluded_appendages: dict[str, list[str]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "bbox": self.bbox.as_dict(),
            "centroid": self.centroid.as_dict(),
            "denseCenter": self.dense_center.as_dict(),
            "confidence": round(self.confidence, 4),
            "excludedAppendages": self.excluded_appendages,
        }


@dataclass
class PartTrack:
    part: str
    track_id: str
    observations: list[dict[str, Any]]
    smoothed: dict[str, Any]
    correction_suggestions: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "part": self.part,
            "trackId": self.track_id,
            "observations": self.observations,
            "smoothed": self.smoothed,
            "correctionSuggestions": self.correction_suggestions,
        }


@dataclass
class CompilerState:
    source_file: str
    asset_id: str
    svg_text: str
    view_box: tuple[float, float, float, float]
    width: float | None
    height: float | None
    normalized_paths: list[NormalizedPath] = field(default_factory=list)
    raster: RasterEvidence | None = None
    frame_candidates: list[FrameSplitCandidate] = field(default_factory=list)
    selected_frame_split: FrameSplitCandidate | None = None
    path_buckets: dict[int, list[NormalizedPath]] = field(default_factory=dict)
    frame_graphs: dict[int, dict[str, Any]] = field(default_factory=dict)
    frame_components: dict[int, list[VisualComponent]] = field(default_factory=dict)
    frame_core_regions: dict[int, CoreBodyRegion] = field(default_factory=dict)
    frame_views: dict[int, ViewState] = field(default_factory=dict)
    frame_landmark_candidates: dict[int, dict[str, list[LandmarkCandidate]]] = field(default_factory=dict)
    frame_ml_landmarks: dict[int, dict[str, Any]] = field(default_factory=dict)
    frame_skeletons: dict[int, dict[str, Any]] = field(default_factory=dict)
    frame_semantic_parts: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    frame_component_rows: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    temporal_tracks: list[PartTrack] = field(default_factory=list)
    temporal_analysis: dict[str, Any] = field(default_factory=dict)
    quality_report: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
