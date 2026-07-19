from __future__ import annotations

from image2svg.convert import list_part_types, load_recipes, recipe_for
from image2svg.paths import package_dir, recipes_path, repo_root, web_dir


def test_repo_layout_files_exist() -> None:
    root = repo_root()
    assert (root / "pyproject.toml").is_file()
    assert (root / "configs" / "recipes.yaml").is_file()
    assert recipes_path().is_file()
    assert (package_dir() / "config" / "recipes.yaml").is_file()
    assert (web_dir() / "index.html").is_file()
    assert (web_dir() / "static" / "app.js").is_file()


def test_recipes_load_and_merge() -> None:
    recipes = load_recipes()
    parts = list_part_types(recipes)
    assert "eye" in parts
    eye = recipe_for("eye", recipes)
    assert eye["colormode"] == "color"
    assert eye["filter_speckle"] == 3
