#!/usr/bin/env python3
"""Sync canonical skills/open-source-repo into committed agent skill locations.

Canonical source: skills/open-source-repo/
Committed copies: .agents/skills/ + .cursor/skills/
Other agents: run `python skills/installer/install.py install`
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "skills" / "open-source-repo"
PACKAGED = ROOT / "skills" / "installer" / "skill"
TARGETS = [
    ROOT / ".agents" / "skills" / "open-source-repo",
    ROOT / ".cursor" / "skills" / "open-source-repo",
]


def copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest)


def main() -> int:
    if not (SRC / "SKILL.md").is_file():
        print(f"Missing canonical skill: {SRC}", file=sys.stderr)
        return 1

    copy_tree(SRC, PACKAGED)
    for dest in TARGETS:
        copy_tree(SRC, dest)
        print(f"synced -> {dest.relative_to(ROOT)}")
    print(f"synced -> {PACKAGED.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
