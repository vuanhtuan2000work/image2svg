"""Write game manifest JSON files for feed-your-pet integration."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from svg_analyze.export.phaser_manifest import build_game_manifest_from_export, display_scale_for_svg

FOLDER_PATTERN = re.compile(r"^(\d+)-(.+)-(lengend|legend)$", re.IGNORECASE)
FILE_PATTERN = re.compile(r"^(\d+)-(.+)-(lengend|legend)\.svg$", re.IGNORECASE)

RUN_SOURCE_FILES: dict[int, str] = {
    1: "run_down",
    2: "run_right",
    3: "run_down_right",
    4: "run_up_right",
    5: "run_up",
    6: "run_up_left",
    7: "run_left",
    8: "run_down_left",
}

DEFAULT_GAME_ROOT = Path(__file__).resolve().parents[2].parent / "game-2d" / "feed-your-pet"


def parse_game_asset_path(svg_path: Path) -> dict[str, Any]:
    """Parse feed-your-pet run sheet path into variant + direction metadata."""
    folder_match = FOLDER_PATTERN.match(svg_path.parent.name)
    file_match = FILE_PATTERN.match(svg_path.name)
    if not folder_match or not file_match:
        raise ValueError(f"Path does not match game asset naming: {svg_path}")

    folder_order, raw_name, folder_suffix = folder_match.groups()
    file_number_text, file_name, file_suffix = file_match.groups()
    file_number = int(file_number_text)
    variant_id = raw_name.strip().replace("-", "_").replace(" ", "_").lower()
    variant_id = re.sub(r"_+", "_", variant_id)
    run_file_stem = f"{file_name}-{file_suffix}"
    run_source_key = RUN_SOURCE_FILES.get(file_number)
    if run_source_key is None:
        raise ValueError(f"Unsupported run file number {file_number} in {svg_path.name}")

    return {
        "variantId": variant_id,
        "variantOrder": int(folder_order),
        "runFolder": svg_path.parent.name,
        "runFileStem": run_file_stem,
        "fileNumber": file_number,
        "runSourceKey": run_source_key,
        "sourceFile": svg_path.name,
    }


def frame_rects_from_manifest(manifest: dict[str, Any]) -> list[dict[str, int]]:
    frames = manifest.get("animations", {}).get("run", {}).get("frames", [])
    scale = manifest.get("displayScale") or {"x": 1.0, "y": 1.0}
    sx, sy = float(scale.get("x", 1.0)), float(scale.get("y", 1.0))
    rects: list[dict[str, int]] = []
    for frame in frames:
        rect = frame.get("contentRect") or frame.get("rect")
        if not rect:
            continue
        rects.append(
            {
                "x": round(float(rect["x"]) * sx),
                "y": round(float(rect["y"]) * sy),
                "width": max(1, round(float(rect["width"]) * sx)),
                "height": max(1, round(float(rect["height"]) * sy)),
            }
        )
    return rects


def build_sheet_manifest(analysis: dict[str, Any], asset_meta: dict[str, Any]) -> dict[str, Any]:
    game_manifest = analysis.get("gameManifest") or build_game_manifest_from_export(analysis)
    svg = analysis.get("assetAnalysis", {}).get("svg", {})
    display_scale = display_scale_for_svg(svg)
    game_manifest = {**game_manifest, "displayScale": display_scale}
    rects = frame_rects_from_manifest(game_manifest)
    return {
        "format": "feed-your-pet-sheet-analysis",
        "generatedAt": datetime.now(UTC).isoformat(),
        "analysisVersion": analysis.get("version", "2.0"),
        "variantId": asset_meta["variantId"],
        "runFolder": asset_meta["runFolder"],
        "runFileStem": asset_meta["runFileStem"],
        "fileNumber": asset_meta["fileNumber"],
        "runSourceKey": asset_meta["runSourceKey"],
        "sourceFile": asset_meta["sourceFile"],
        "sheetSize": {
            "width": display_scale["displayWidth"],
            "height": display_scale["displayHeight"],
        },
        "displayScale": display_scale,
        "frameRects": rects,
        "gameManifest": game_manifest,
        "mlLandmarks": [
            {
                "frameIndex": fa.get("frameIndex"),
                "mlLandmarks": fa.get("mlLandmarks"),
            }
            for fa in analysis.get("frameAnalysis", [])
            if fa.get("mlLandmarks")
        ],
        "validation": game_manifest.get("validation", {}),
    }


def sheet_manifest_path(game_root: Path, asset_meta: dict[str, Any]) -> Path:
    analysis_dir = (
        game_root
        / "public"
        / "assets"
        / "pet"
        / "cat_actions"
        / "run"
        / asset_meta["runFolder"]
        / "analysis"
    )
    filename = f"{asset_meta['fileNumber']}-{asset_meta['runFileStem']}.game-manifest.json"
    return analysis_dir / filename


def variant_manifest_path(game_root: Path, variant_id: str) -> Path:
    return (
        game_root
        / "public"
        / "assets"
        / "pet"
        / "cat_actions"
        / "analysis"
        / f"{variant_id}.runFrameRects.json"
    )


def write_sheet_manifest(
    analysis: dict[str, Any],
    svg_path: Path,
    *,
    game_root: Path | None = None,
    asset_meta: dict[str, Any] | None = None,
) -> Path:
    root = game_root or DEFAULT_GAME_ROOT
    meta = asset_meta or parse_game_asset_path(svg_path.resolve())
    payload = build_sheet_manifest(analysis, meta)
    out_path = sheet_manifest_path(root, meta)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    merge_variant_run_frame_rects(root, meta["variantId"], meta["runFolder"])
    return out_path


def merge_variant_run_frame_rects(game_root: Path, variant_id: str, run_folder: str) -> Path:
    """Merge all sheet manifests in a variant folder into one runFrameRects overlay."""
    analysis_dir = game_root / "public" / "assets" / "pet" / "cat_actions" / "run" / run_folder / "analysis"
    merged: dict[str, list[dict[str, int]]] = {}
    sources: dict[str, dict[str, Any]] = {}

    if analysis_dir.is_dir():
        for path in sorted(analysis_dir.glob("*.game-manifest.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            source_key = data.get("runSourceKey")
            rects = data.get("frameRects") or frame_rects_from_manifest(data.get("gameManifest", {}))
            if source_key and rects:
                merged[source_key] = rects
                sources[source_key] = {
                    "sourceFile": data.get("sourceFile"),
                    "sheetSize": data.get("sheetSize"),
                    "generatedAt": data.get("generatedAt"),
                }

    out_path = variant_manifest_path(game_root, variant_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "format": "feed-your-pet-runFrameRects-overlay",
                "variantId": variant_id,
                "runFolder": run_folder,
                "generatedAt": datetime.now(UTC).isoformat(),
                "runFrameRects": merged,
                "sources": sources,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return out_path


def resolve_game_root(explicit: str | Path | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = Path(os.environ.get("IMAGE2SVG_GAME_ROOT", "")).expanduser() if os.environ.get("IMAGE2SVG_GAME_ROOT") else None
    if env and env.is_dir():
        return env.resolve()
    return DEFAULT_GAME_ROOT.resolve()
