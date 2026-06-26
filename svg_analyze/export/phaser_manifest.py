"""Export analysis results to feed-your-pet / Phaser-compatible game manifest."""

from __future__ import annotations

from typing import Any


def display_scale_for_svg(svg_meta: dict[str, Any]) -> dict[str, float]:
    view_box = svg_meta.get("viewBox") or [0, 0, 1, 1]
    vb_w = float(view_box[2]) if len(view_box) >= 4 else float(svg_meta.get("width") or 1)
    vb_h = float(view_box[3]) if len(view_box) >= 4 else float(svg_meta.get("height") or 1)
    display_w = float(svg_meta.get("width") or vb_w)
    display_h = float(svg_meta.get("height") or vb_h)
    return {
        "x": display_w / max(vb_w, 1.0),
        "y": display_h / max(vb_h, 1.0),
        "viewBoxWidth": vb_w,
        "viewBoxHeight": vb_h,
        "displayWidth": display_w,
        "displayHeight": display_h,
    }


def build_game_manifest_from_export(full_export: dict[str, Any]) -> dict[str, Any]:
    """Build game manifest from final analyze_svg() JSON (pass8 output)."""
    asset = full_export.get("assetAnalysis", {})
    strip = full_export.get("stripAnalysis", {})
    frames_analysis = full_export.get("frameAnalysis", [])
    asset_id = asset.get("assetId", "asset")
    animation_key = "run"
    texture_key = f"cat_{asset_id}_{animation_key}"

    frames: list[dict[str, Any]] = []
    issues: list[str] = []

    for fa in frames_analysis:
        idx = fa.get("frameIndex", 0)
        fb = fa.get("bounds", {}).get("frameBBox", {})
        cb = fa.get("bounds", {}).get("contentBBox", fb)
        rect = {
            "x": round(fb.get("x", 0)),
            "y": round(fb.get("y", 0)),
            "width": round(fb.get("w", 0)),
            "height": round(fb.get("h", 0)),
        }
        if rect["width"] <= 0 or rect["height"] <= 0:
            issues.append(f"Frame {idx}: invalid rect")
        frames.append(
            {
                "key": f"{texture_key}_f{idx}",
                "textureKey": texture_key,
                "frame": f"frame_{idx}",
                "rect": rect,
                "contentRect": {
                    "x": round(cb.get("x", rect["x"])),
                    "y": round(cb.get("y", rect["y"])),
                    "width": round(cb.get("w", rect["width"])),
                    "height": round(cb.get("h", rect["height"])),
                },
                "qualityScore": fa.get("quality", {}).get("score"),
                "view": fa.get("view"),
                "skeletonConfidence": fa.get("skeleton", {}).get("confidence"),
            }
        )

    expected = strip.get("frameCount", len(frames))
    if len(frames) != expected:
        issues.append(f"Frame count mismatch: expected {expected}, got {len(frames)}")

    svg_meta = asset.get("svg", {})
    display_scale = display_scale_for_svg(svg_meta)

    return {
        "format": "phaser-svg-frame-strip",
        "compatibleWith": "feed-your-pet PetAssetManifest",
        "runtimeNote": "Phaser 3 SVG sprite animation — frame rects, not bone rig.",
        "displayScale": display_scale,
        "petType": "cat",
        "variantId": asset_id,
        "enabled": True,
        "sources": [
            {
                "key": texture_key,
                "url": f"/assets/pet/cat_actions/{animation_key}/{asset_id}.svg",
                "format": "svg",
                "width": asset.get("svg", {}).get("width"),
                "height": asset.get("svg", {}).get("height"),
                "viewBox": asset.get("svg", {}).get("viewBox"),
            }
        ],
        "animations": {
            animation_key: {
                "key": animation_key,
                "frameRate": 9,
                "repeat": -1,
                "frames": frames,
            }
        },
        "stripAnalysis": {
            "frameCount": strip.get("frameCount"),
            "direction": strip.get("layout", {}).get("direction"),
            "method": strip.get("selectedSplitMethod"),
            "score": strip.get("splitConfidence"),
        },
        "validation": {
            "readyForGame": len(issues) == 0,
            "issues": issues,
            "recommendedStack": "phaser-svg-frames",
            "notRecommended": ["spine-runtimes", "DragonBonesJS"],
            "optionalMlLandmarks": "mmpose or deeplabcut (rendered PNG pass only)",
        },
    }
