"""Deprecated shim — import from `image2svg.background` instead."""

from __future__ import annotations

import warnings

warnings.warn(
    "Importing background_removal is deprecated. Use `from image2svg.background import ...`.",
    DeprecationWarning,
    stacklevel=1,
)

from image2svg.background import get_last_background_engine, refine_alpha, remove_background

__all__ = ["get_last_background_engine", "refine_alpha", "remove_background"]
