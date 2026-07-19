#!/usr/bin/env python3
"""Analyze an SVG frame strip and write a game manifest JSON file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from image2svg.analyze import analyze_svg
from image2svg.analyze.export.write_game_manifest import resolve_game_root, write_sheet_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Export game manifest from SVG frame strip analysis")
    parser.add_argument("svg", type=Path, help="Path to SVG sheet (e.g. 1-Balinese-lengend.svg)")
    parser.add_argument(
        "--game-root",
        type=Path,
        default=None,
        help="Game project root (default: IMAGE2SVG_GAME_ROOT or sibling feed-your-pet path)",
    )
    parser.add_argument(
        "--analysis-out",
        type=Path,
        default=None,
        help="Optional path to write full analysis JSON",
    )
    parser.add_argument(
        "--ml-landmarks",
        action="store_true",
        help="Enable silhouette ML landmark pass",
    )
    parser.add_argument(
        "--mmpose",
        action="store_true",
        help="Also try MMPose if installed (see requirements-ml.txt)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze only; do not write into the game directory",
    )
    args = parser.parse_args()

    svg_path = args.svg.expanduser().resolve()
    if not svg_path.is_file():
        print(f"SVG not found: {svg_path}", file=sys.stderr)
        return 1

    svg_text = svg_path.read_text(encoding="utf-8")
    analysis = analyze_svg(
        svg_text,
        svg_path.name,
        enable_ml_landmarks=args.ml_landmarks or None,
        enable_mmpose=args.mmpose or None,
    )

    if args.analysis_out:
        args.analysis_out.parent.mkdir(parents=True, exist_ok=True)
        args.analysis_out.write_text(
            json.dumps(analysis, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote analysis: {args.analysis_out}")

    if args.dry_run:
        manifest = analysis.get("gameManifest", {})
        frames = manifest.get("animations", {}).get("run", {}).get("frames", [])
        print(json.dumps({"frameCount": len(frames), "validation": manifest.get("validation")}, indent=2))
        return 0

    game_root = resolve_game_root(args.game_root)
    out_path = write_sheet_manifest(analysis, svg_path, game_root=game_root)
    print(f"Wrote game manifest: {out_path}")
    print(f"Merged overlay: {game_root / 'public/assets/pet/cat_actions/analysis'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
