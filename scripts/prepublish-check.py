#!/usr/bin/env python3
"""Pre-publish / pre-push gate for the open-source-repo Agent Skill.

Exit 0 only when skill structure, sync, and tests pass.
Do not push or npm-publish when this script fails.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "open-source-repo" / "SKILL.md"
PACKAGED = ROOT / "skills" / "installer" / "skill" / "SKILL.md"
VENDORED = [
    ROOT / ".agents" / "skills" / "open-source-repo" / "SKILL.md",
    ROOT / ".cursor" / "skills" / "open-source-repo" / "SKILL.md",
]
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr)


def _ok(msg: str) -> None:
    print(f"[OK] {msg}")


def check_skill_md() -> bool:
    if not SKILL.is_file():
        _fail(f"missing {SKILL}")
        return False
    text = SKILL.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        _fail("SKILL.md missing YAML frontmatter")
        return False
    if "name: open-source-repo" not in match.group(1):
        _fail("SKILL.md name must be open-source-repo")
        return False
    if "description:" not in match.group(1):
        _fail("SKILL.md missing description")
        return False
    name_line = next((ln for ln in match.group(1).splitlines() if ln.startswith("name:")), "")
    name = name_line.split(":", 1)[1].strip()
    if not NAME_RE.match(name):
        _fail("SKILL.md name format invalid")
        return False
    body = FRONTMATTER_RE.sub("", text, count=1)
    if len(body.splitlines()) >= 500:
        _fail("SKILL.md body must stay under 500 lines")
        return False
    if "Non-goals" not in body and "non-goals" not in body.lower():
        _fail("SKILL.md should document non-goals / safety limits")
        return False
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    _ok(f"SKILL.md valid (sha256={digest[:16]}...)")
    return True


def check_sync() -> bool:
    if not PACKAGED.is_file():
        _fail("skills/installer/skill/SKILL.md missing — run scripts/sync-agent-skills.py")
        return False
    canonical = SKILL.read_bytes()
    if canonical != PACKAGED.read_bytes():
        _fail("canonical skill != installer/skill — run scripts/sync-agent-skills.py")
        return False
    for path in VENDORED:
        if not path.is_file():
            _fail(f"missing vendored skill {path.relative_to(ROOT)}")
            return False
        if path.read_bytes() != canonical:
            _fail(f"vendored skill drift: {path.relative_to(ROOT)}")
            return False
    _ok("installer + .agents/.cursor skill copies match canonical")
    return True


def _python() -> str:
    candidates = [
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def run_pytest() -> bool:
    py = _python()
    cmd = [py, "-m", "pytest", "-q"]
    proc = subprocess.run(cmd, cwd=ROOT, check=False)
    if proc.returncode != 0:
        _fail(f"pytest failed (python={py})")
        return False
    _ok(f"pytest passed (python={py})")
    return True


def main() -> int:
    print("=== image2svg skill prepublish gate ===")
    checks = [
        check_skill_md(),
        check_sync(),
        run_pytest(),
    ]
    if all(checks):
        print("\nGATE PASS — OK to commit/push. Prefer trusted-clone or version-pinned npm installs.")
        return 0
    print("\nGATE FAIL — do not push until fixed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
