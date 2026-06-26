"""MMPose inference adapter (optional — requires torch + mmpose)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

# AP-10K style animal keypoint names (subset mapped to our skeleton vocabulary).
_AP10K_TO_GAME = {
    "L_Eye": "leftEye",
    "R_Eye": "rightEye",
    "Nose": "nose",
    "Neck": "neck",
    "Withers": "shoulder",
    "Tail": "tailTip",
    "Root_of_tail": "tailRoot",
    "L_Elbow": "frontElbowLeft",
    "R_Elbow": "frontElbowRight",
    "L_Knee": "backKneeLeft",
    "R_Knee": "backKneeRight",
    "L_F_Paw": "frontPawLeft",
    "R_F_Paw": "frontPawRight",
    "L_B_Paw": "backPawLeft",
    "R_B_Paw": "backPawRight",
}

_MODEL_CACHE: dict[str, Any] = {}


def _python_openmmlab_supported() -> bool:
    import sys

    return sys.version_info[:2] in {(3, 10), (3, 11)}


def infer_animal_pose(png_bytes: bytes) -> dict[str, Any]:
    """Run top-down animal pose inference when mmpose is installed."""
    import importlib.util
    import sys

    if not _python_openmmlab_supported():
        return {
            "status": "skipped",
            "reason": (
                f"OpenMMLab/MMPose does not support Python {sys.version_info.major}.{sys.version_info.minor}. "
                "Use Python 3.10 or 3.11 in .venv-ml (see scripts/install-ml-deps.sh). "
                "Silhouette landmarks (--ml-landmarks) still work on Python 3.13."
            ),
        }

    if importlib.util.find_spec("mmpose") is None:
        return {
            "status": "skipped",
            "reason": "mmpose not installed — run ./scripts/install-ml-deps.sh (not pip install -r requirements-ml.txt)",
        }

    model = _get_model()
    if model is None:
        return {"status": "skipped", "reason": "mmpose model not configured"}

    config, pose_model, device = model
    from mmpose.apis import inference_topdown

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(png_bytes)
        tmp_path = tmp.name

    try:
        results = inference_topdown(pose_model, tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if not results:
        return {"status": "skipped", "reason": "no detections"}

    best = max(results, key=lambda item: float(getattr(item, "score", 0.0) or 0.0))
    pred = getattr(best, "pred_instances", None)
    if pred is None:
        return {"status": "skipped", "reason": "empty pred_instances"}

    keypoints = pred.keypoints[0].tolist() if hasattr(pred, "keypoints") else []
    scores = pred.keypoint_scores[0].tolist() if hasattr(pred, "keypoint_scores") else []
    labels = _keypoint_labels(config)

    from PIL import Image
    from io import BytesIO

    img = Image.open(BytesIO(png_bytes))
    w, h = img.size

    mapped: list[dict[str, Any]] = []
    confidences: list[float] = []
    for idx, (xy, score) in enumerate(zip(keypoints, scores, strict=False)):
        if float(score) < 0.2:
            continue
        label = labels[idx] if idx < len(labels) else f"kp_{idx}"
        name = _AP10K_TO_GAME.get(label, label)
        mapped.append({"label": label, "name": name, "x": float(xy[0]), "y": float(xy[1]), "confidence": float(score)})
        confidences.append(float(score))

    if not mapped:
        return {"status": "skipped", "reason": "all keypoints below threshold"}

    return {
        "status": "ok",
        "model": os.environ.get("IMAGE2SVG_MMPOSE_CONFIG", "mmpose animal default"),
        "imageWidth": w,
        "imageHeight": h,
        "keypoints": mapped,
        "confidence": sum(confidences) / len(confidences),
    }


def _get_model() -> tuple[Any, Any, str] | None:
    cache_key = "default"
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]

    config_path = os.environ.get("IMAGE2SVG_MMPOSE_CONFIG")
    checkpoint_path = os.environ.get("IMAGE2SVG_MMPOSE_CHECKPOINT")
    device = os.environ.get("IMAGE2SVG_MMPOSE_DEVICE", "cpu")

    if not config_path or not checkpoint_path:
        return None

    from mmpose.apis import init_model

    pose_model = init_model(config_path, checkpoint_path, device=device)
    loaded = (config_path, pose_model, device)
    _MODEL_CACHE[cache_key] = loaded
    return loaded


def _keypoint_labels(config_path: str) -> list[str]:
    try:
        from mmengine.config import Config

        cfg = Config.fromfile(config_path)
        meta = getattr(cfg, "metainfo", None) or {}
        if isinstance(meta, dict):
            info = meta.get("keypoint_info") or meta.get("keypoints_info")
            if isinstance(info, dict):
                return [info[k]["name"] for k in sorted(info.keys(), key=lambda x: int(x))]
            names = meta.get("keypoint_names")
            if isinstance(names, list):
                return [str(n) for n in names]
    except Exception:
        pass
    return []
