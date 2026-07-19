"""Deprecated shim — use `image2svg serve` or `image2svg-server`."""

from __future__ import annotations

import warnings

warnings.warn(
    "Running server.py is deprecated. Use `image2svg serve` or `image2svg-server` after `pip install -e .`.",
    DeprecationWarning,
    stacklevel=1,
)

from image2svg.web.app import main


if __name__ == "__main__":
    main()
