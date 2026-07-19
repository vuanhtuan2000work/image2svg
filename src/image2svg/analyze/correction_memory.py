"""Correction memory — persist manual review corrections for future priors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from image2svg.paths import data_dir

MEMORY_PATH = data_dir() / "correction_memory.json"


def load_correction_memory() -> dict[str, Any]:
    if not MEMORY_PATH.exists():
        return {"assets": {}}
    try:
        return json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"assets": {}}


def save_correction(entry: dict[str, Any]) -> dict[str, Any]:
    memory = load_correction_memory()
    asset_id = entry.get("assetId", "unknown")
    assets = memory.setdefault("assets", {})
    bucket = assets.setdefault(asset_id, {"corrections": []})
    bucket["corrections"].append(entry)
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(memory, indent=2), encoding="utf-8")
    return entry


def save_corrections_batch(asset_id: str, corrections: list[dict[str, Any]]) -> dict[str, Any]:
    saved: list[dict[str, Any]] = []
    for entry in corrections:
        entry = {**entry, "assetId": asset_id}
        saved.append(save_correction(entry))
    return {"assetId": asset_id, "saved": len(saved), "corrections": saved}


def list_corrections(asset_id: str | None = None) -> dict[str, Any]:
    memory = load_correction_memory()
    if asset_id:
        return memory.get("assets", {}).get(asset_id, {"corrections": []})
    return memory


def apply_correction_priors(asset_id: str) -> dict[str, float]:
    memory = load_correction_memory()
    corrections = memory.get("assets", {}).get(asset_id, {}).get("corrections", [])
    priors = {
        "silhouetteBranch_tailRoot": 1.0,
        "templatePrior_tailRoot": 1.0,
        "color_eye": 1.0,
        "frameSplit_dynamicProgramming": 1.0,
        "part_tailSet": 1.0,
    }
    for corr in corrections:
        target_type = corr.get("targetType")
        target_id = str(corr.get("targetId", ""))
        if target_type == "landmark" and target_id == "tailRoot":
            priors["silhouetteBranch_tailRoot"] = min(2.0, priors["silhouetteBranch_tailRoot"] + 0.15)
            priors["templatePrior_tailRoot"] = max(0.5, priors["templatePrior_tailRoot"] - 0.1)
        if target_type == "landmark" and "Eye" in target_id:
            priors["color_eye"] = min(2.0, priors["color_eye"] + 0.1)
        if target_type == "part" and target_id == "tailSet":
            priors["part_tailSet"] = min(2.0, priors["part_tailSet"] + 0.12)
        if target_type == "frameSplit":
            priors["frameSplit_dynamicProgramming"] = min(2.0, priors["frameSplit_dynamicProgramming"] + 0.1)
    return priors
