"""SVG animation strip analysis — multi-pass compiler entry point."""

from svg_analyze.compiler.orchestrator import compile_svg as _compile_svg


def analyze_svg(
    svg_text: str,
    source_file: str,
    *,
    enable_ml_landmarks: bool | None = None,
    enable_mmpose: bool | None = None,
) -> dict:
    return _compile_svg(
        svg_text,
        source_file,
        enable_ml_landmarks=enable_ml_landmarks,
        enable_mmpose=enable_mmpose,
    )


__all__ = ["analyze_svg"]
