"""Functional tests for the Python skill installer."""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL_PY = ROOT / "skills" / "installer" / "install.py"


def _load_installer():
    spec = importlib.util.spec_from_file_location("open_source_repo_skill_install", INSTALL_PY)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_skill_source_resolves() -> None:
    installer = _load_installer()
    src = installer.skill_source()
    assert (src / "SKILL.md").is_file()
    assert src.name in {"skill", "open-source-repo"}


def test_install_uninstall_roundtrip(tmp_path: Path) -> None:
    agents = "cursor,claude"
    proc = subprocess.run(
        [sys.executable, str(INSTALL_PY), "install", "--cwd", str(tmp_path), "--agents", agents],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    for folder in (".cursor", ".claude"):
        skill_md = tmp_path / folder / "skills" / "open-source-repo" / "SKILL.md"
        assert skill_md.is_file()
        text = skill_md.read_text(encoding="utf-8")
        assert "name: open-source-repo" in text
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert len(digest) == 64

    proc = subprocess.run(
        [sys.executable, str(INSTALL_PY), "uninstall", "--cwd", str(tmp_path), "--agents", agents],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert not (tmp_path / ".cursor" / "skills" / "open-source-repo").exists()
    assert not (tmp_path / ".claude" / "skills" / "open-source-repo").exists()


def test_rejects_unknown_agent(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(INSTALL_PY), "install", "--cwd", str(tmp_path), "--agents", "evil"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0


def test_destination_stays_under_cwd(tmp_path: Path) -> None:
    installer = _load_installer()
    dest = installer.target_dir("gemini", global_install=False, cwd=tmp_path)
    assert dest == tmp_path / ".gemini" / "skills" / "open-source-repo"
    resolved = dest.resolve()
    assert Path(os_path_common(tmp_path.resolve(), resolved)) == tmp_path.resolve()


def os_path_common(a: Path, b: Path) -> str:
    import os

    return os.path.commonpath([str(a), str(b)])
