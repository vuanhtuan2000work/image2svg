"""Allow `python -m image2svg`."""

from __future__ import annotations

import sys

from image2svg.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
