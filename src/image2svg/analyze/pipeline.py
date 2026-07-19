"""SVG animation strip analysis — multi-pass compiler entry point."""

from typing import Any, Callable

from image2svg.analyze.compiler.orchestrator import compile_svg as _compile_svg

ProgressCallback = Callable[[dict[str, Any]], None]


def analyze_svg(
    svg_text: str,
    source_file: str,
    *,
    enable_ml_landmarks: bool | None = None,
    enable_mmpose: bool | None = None,
    focus_frames: list[int] | None = None,
    progress: ProgressCallback | None = None,
) -> dict:
    return _compile_svg(
        svg_text,
        source_file,
        enable_ml_landmarks=enable_ml_landmarks,
        enable_mmpose=enable_mmpose,
        focus_frames=focus_frames,
        progress=progress,
    )


__all__ = ["analyze_svg"]
