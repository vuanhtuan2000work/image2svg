"""Shared constants for the convert pipeline."""

from __future__ import annotations

VTRACER_KEYS = {
    "colormode",
    "hierarchical",
    "mode",
    "filter_speckle",
    "color_precision",
    "layer_difference",
    "corner_threshold",
    "length_threshold",
    "max_iterations",
    "splice_threshold",
    "path_precision",
}

# Edge smoothing via Lanczos upscale only (no Gaussian blur by default).
SMOOTHING_PRESETS = {
    "none": {"upscale": 1, "blur": 0.0},
    "low": {"upscale": 2, "blur": 0.0},
    "medium": {"upscale": 3, "blur": 0.0},
    "high": {"upscale": 4, "blur": 0.0},
}
DEFAULT_SMOOTHING = "medium"
DEFAULT_SHARPNESS = 80
OUTPUT_FORMATS = ("jpg", "jpeg", "png", "webp", "avif", "gif", "svg", "bmp", "tiff", "heic")
SVG_MODES = ("embedded", "vector")
RASTER_OUTPUT_FORMATS = tuple(fmt for fmt in OUTPUT_FORMATS if fmt != "svg")
RASTER_MIME_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "avif": "image/avif",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "tiff": "image/tiff",
    "heic": "image/heic",
}
PIL_SAVE_FORMATS = {
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "png": "PNG",
    "webp": "WEBP",
    "avif": "AVIF",
    "gif": "GIF",
    "bmp": "BMP",
    "tiff": "TIFF",
    "heic": "HEIF",
}
NO_ALPHA_OUTPUTS = {"jpg", "jpeg", "bmp"}
