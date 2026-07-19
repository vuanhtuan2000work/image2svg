"""Filesystem helpers for project-relative paths."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def package_dir() -> Path:
    """Return the installed/editable `image2svg` package directory."""
    return Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def repo_root() -> Path:
    """Best-effort repository root (works for editable installs)."""
    # src/image2svg/paths.py -> parents[1] == repo root
    candidate = package_dir().parents[1]
    if (candidate / "pyproject.toml").exists() or (candidate / "configs" / "recipes.yaml").exists():
        return candidate
    return Path.cwd()


def recipes_path() -> Path:
    override = os.getenv("IMAGE2SVG_RECIPES")
    if override:
        return Path(override).expanduser().resolve()

    # Prefer the checked-in configs/ copy when developing from a git checkout.
    repo_recipes = repo_root() / "configs" / "recipes.yaml"
    if repo_recipes.exists():
        return repo_recipes

    packaged = package_dir() / "config" / "recipes.yaml"
    if packaged.exists():
        return packaged

    return Path.cwd() / "configs" / "recipes.yaml"


def assets_root() -> Path:
    override = os.getenv("IMAGE2SVG_ASSETS_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return repo_root() / "assets"


def raw_assets_dir() -> Path:
    return assets_root() / "raw"


def out_assets_dir() -> Path:
    return assets_root() / "out"


def data_dir() -> Path:
    override = os.getenv("IMAGE2SVG_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return repo_root() / "data"


def web_dir() -> Path:
    return package_dir() / "web"
