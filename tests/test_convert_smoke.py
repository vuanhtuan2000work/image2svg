"""Smoke tests for the convert pipeline using the sample asset."""

from __future__ import annotations

import platform
import sys
from pathlib import Path

import pytest

from image2svg.convert import (
    convert_embedded_svg_bytes,
    convert_image_bytes,
    load_recipes,
    preprocess_image,
    recipe_for,
)

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "assets" / "raw" / "eye" / "eye_purple_01.png"


def _vtracer_supported() -> bool:
    """vtracer 0.6.x native wheels can hard-crash on newer CPython builds."""
    if sys.version_info >= (3, 14):
        return False
    if sys.version_info >= (3, 13) and platform.system() == "Windows":
        return False
    return True


@pytest.fixture(scope="module")
def sample_png() -> bytes:
    if not SAMPLE.is_file():
        pytest.skip(f"sample asset missing: {SAMPLE}")
    return SAMPLE.read_bytes()


def test_preprocess_trim_and_upscale(sample_png: bytes) -> None:
    out, size = preprocess_image(sample_png, upscale=2, trim=True)
    assert out.startswith(b"\x89PNG")
    assert size[0] > 0 and size[1] > 0


def test_convert_embedded_svg(sample_png: bytes) -> None:
    svg, report, optimizer, elapsed = convert_embedded_svg_bytes(
        sample_png,
        smoothing="none",
        sharpness=0,
        remove_bg=False,
        trim=True,
    )
    assert "<svg" in svg
    assert report["svg_mode"] == "embedded"
    assert optimizer == "none"
    assert elapsed >= 0


@pytest.mark.skipif(not _vtracer_supported(), reason="vtracer native binding unsafe on this Python/OS")
def test_convert_vector_svg_smoke(sample_png: bytes) -> None:
    recipes = load_recipes()
    params = recipe_for("eye", recipes)
    assert params.get("colormode") == "color"

    svg, report, _optimizer, elapsed = convert_image_bytes(
        sample_png,
        part="eye",
        suffix=".png",
        optimizer="none",
        recipes=recipes,
        smoothing="none",
        sharpness=0,
        remove_bg=False,
        trim=True,
    )
    assert "<svg" in svg.lower()
    assert "path" in svg.lower() or "polygon" in svg.lower() or "<image" in svg.lower()
    assert report["smoothing"] == "none"
    assert elapsed >= 0
