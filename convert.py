"""Deprecated shim — use `image2svg` or `python -m image2svg`."""

from __future__ import annotations

import sys
import warnings

warnings.warn(
    "Running convert.py is deprecated. Use `image2svg` or `python -m image2svg` after `pip install -e .`.",
    DeprecationWarning,
    stacklevel=1,
)

from image2svg.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
